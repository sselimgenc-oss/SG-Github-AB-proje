"""Saglik uygulamasi duman testleri (spec ornekleri 13.x'in alt kumesi)."""
import importlib.util
import json
import sqlite3
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from trader_core import health as H
from trader_core.health import (ApiProbe, ContainerProbe, HealthConfig, HealthSnapshot, LedgerProbe, Status)

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))


def _load(name):
    spec = importlib.util.spec_from_file_location(name, ROOT / "scripts" / f"{name}.py")
    m = importlib.util.module_from_spec(spec)
    sys.modules[name] = m
    spec.loader.exec_module(m)
    return m


NOW = datetime(2026, 11, 16, 12, 30, tzinfo=timezone.utc)
GIB, MIB = 1024 ** 3, 1024 ** 2


def t(h, m, s=0):
    return datetime(2026, 11, 16, h, m, s, tzinfo=timezone.utc)


def snap(**kw):
    api = {b: ApiProbe(True, t(12, 29, 30), t(12, 0), (), True) for b in ("learner", "twin")}
    led = {b: LedgerProbe(t(12, 0, 2), 0, (), (), True, True, 0) for b in ("learner", "twin")}
    cont = {f"trader-{b}": ContainerProbe("running", 4, t(1, 0), False) for b in ("learner", "twin")}
    base = dict(now=NOW, timeframe_s=3600, api=api, ledger=led, disk_free_bytes=20 * GIB,
                mem_available_bytes=900 * MIB, swap_total_bytes=2048 * MIB, swap_used_bytes=205 * MIB,
                containers=cont, prev_restart_counts={"trader-learner": 4, "trader-twin": 4},
                last_backup_at=t(3, 10))
    base.update(kw)
    return HealthSnapshot(**base)


def res(rep, name):
    return next(r for r in rep.results if r.name == name)


def test_all_ok():
    rep = H.evaluate(snap())
    assert rep.overall is Status.OK and rep.healthy
    assert res(rep, "veto_file_age").status is Status.SKIPPED
    assert res(rep, "budget_status").status is Status.SKIPPED
    assert H.should_send_ok(rep)


@pytest.mark.parametrize("candle,status", [(t(10, 30), Status.OK), (t(10, 29), Status.OK),
                                           (t(10, 27), Status.WARN), (t(9, 27), Status.CRIT),
                                           (t(9, 30), Status.WARN)])
def test_candle(candle, status):
    s = snap()
    api = dict(s.api)
    api["learner"] = ApiProbe(True, t(12, 29, 30), candle, (), True)
    r = res(H.evaluate(snap(api=api)), "candle_age:learner")
    assert r.status is status
    if status is Status.CRIT:
        assert r.code == "stale_candle"


def test_api_none_unknown_no_heartbeat():
    api = dict(snap().api)
    api["learner"] = ApiProbe()
    rep = H.evaluate(snap(api=api))
    assert rep.overall is Status.UNKNOWN and not rep.healthy and not H.should_send_ok(rep)


def test_disk_mem_swap():
    assert res(H.evaluate(snap(disk_free_bytes=3 * GIB)), "disk_free").status is Status.OK
    assert res(H.evaluate(snap(disk_free_bytes=int(2.5 * GIB))), "disk_free").status is Status.WARN
    r = res(H.evaluate(snap(disk_free_bytes=int(0.9 * GIB))), "disk_free")
    assert r.status is Status.CRIT and r.code == "disk_low"
    assert res(H.evaluate(snap(mem_available_bytes=250 * MIB)), "memory").status is Status.OK
    assert res(H.evaluate(snap(mem_available_bytes=249 * MIB)), "memory").status is Status.WARN
    assert res(H.evaluate(snap(mem_available_bytes=119 * MIB)), "memory").status is Status.CRIT
    assert res(H.evaluate(snap(swap_used_bytes=1100 * MIB)), "swap").status is Status.WARN
    assert res(H.evaluate(snap(swap_used_bytes=1700 * MIB)), "swap").status is Status.CRIT
    assert res(H.evaluate(snap(swap_total_bytes=0, swap_used_bytes=0)), "swap").status is Status.SKIPPED


def test_container_and_warmup():
    def cont(**kw):
        d = dict(state="running", restart_count=4, started_at=t(1, 0), oom_killed=False)
        d.update(kw)
        return {"trader-learner": ContainerProbe(**d), "trader-twin": ContainerProbe("running", 4, t(1, 0), False)}
    n = "container_restarts:trader-learner"
    assert res(H.evaluate(snap(containers=cont())), n).status is Status.OK
    assert res(H.evaluate(snap(containers=cont(restart_count=5))), n).status is Status.WARN
    assert res(H.evaluate(snap(containers=cont(restart_count=7))), n).status is Status.CRIT
    assert res(H.evaluate(snap(containers=cont(state="restarting"))), n).status is Status.CRIT
    r = res(H.evaluate(snap(containers=cont(oom_killed=True))), n)
    assert r.code == "oom_killed"
    # isinma: bayat mum CRIT -> WARN, api_reachable gevsemez
    api = dict(snap().api)
    api["learner"] = ApiProbe(False, t(12, 29, 30), t(9, 27), (), True)
    rep = H.evaluate(snap(api=api, containers=cont(started_at=t(12, 25))))
    assert res(rep, "candle_age:learner").code == "stale_candle_warmup"
    assert res(rep, "candle_age:learner").status is Status.WARN
    assert res(rep, "api_reachable:learner").status is Status.CRIT


def test_gate():
    led = dict(snap().ledger)
    led["learner"] = LedgerProbe(t(12, 0, 2), 1, (), (), True, True, 0)
    rep = H.evaluate(snap(ledger=led))
    assert res(rep, "ledger_gate:learner").code == "spool_pending" and rep.overall is Status.CRIT
    led["learner"] = LedgerProbe(t(12, 0, 2), 0, (), (31,), True, True, 0)
    rep = H.evaluate(snap(ledger=led))
    assert res(rep, "ledger_gate:learner").code == "orphan_decisions" and rep.healthy
    led["learner"] = LedgerProbe(t(12, 0, 2), None, (), (), True, True, 0)
    assert res(H.evaluate(snap(ledger=led)), "ledger_gate:learner").status is Status.UNKNOWN


def test_combine_missing_skew_placeholders():
    R = lambda s: H.CheckResult("x", s, "c", "d")  # noqa: E731
    assert H.combine([R(Status.OK), R(Status.OK), R(Status.SKIPPED), R(Status.WARN)]) is Status.WARN
    assert H.combine([R(Status.OK), R(Status.UNKNOWN), R(Status.WARN)]) is Status.UNKNOWN
    assert H.combine([R(Status.SKIPPED)]) is Status.UNKNOWN and H.combine([]) is Status.UNKNOWN
    rep = H.evaluate(snap(ledger={}))
    assert res(rep, "ledger_gate:learner").code == "missing_check" and rep.overall is Status.UNKNOWN
    api = dict(snap().api)
    api["learner"] = ApiProbe(True, t(12, 31), t(12, 0), (), True)
    assert res(H.evaluate(snap(api=api)), "bot_loop_age:learner").code == "clock_skew"
    cfg = HealthConfig(veto_max_age_s=900)
    assert res(H.evaluate(snap(veto_file_mtime=NOW - timedelta(seconds=1000)), cfg), "veto_file_age").status is Status.WARN
    assert res(H.evaluate(snap(veto_file_mtime=NOW - timedelta(seconds=2800)), cfg), "veto_file_age").status is Status.CRIT
    cfg = HealthConfig(budget_check_enabled=True)
    assert res(H.evaluate(snap(budget_state="exhausted"), cfg), "budget_status").status is Status.CRIT
    assert res(H.evaluate(snap(budget_state="weird"), cfg), "budget_status").status is Status.UNKNOWN


def test_backup_age():
    for hrs, st in ((25, Status.OK), (27, Status.WARN), (51, Status.CRIT)):
        r = res(H.evaluate(snap(last_backup_at=NOW - timedelta(hours=hrs))), "backup_age")
        assert r.status is st
    assert res(H.evaluate(snap(last_backup_at=None, installed_at=NOW - timedelta(hours=1))), "backup_age").status is Status.SKIPPED


def test_naive_now_and_bad_cfg():
    with pytest.raises(ValueError):
        HealthSnapshot(now=datetime(2026, 1, 1))
    with pytest.raises(ValueError):
        HealthConfig(loop_warn_s=500)


def _rep(status, code="stale_candle", name="candle_age:learner"):
    r = H.CheckResult(name, status, code, "d")
    return H.HealthReport(NOW, (r,), status, status in (Status.OK, Status.WARN))


def test_alert_timeline_and_recovery():
    st = None
    out = {}
    for i in range(0, 41):
        now = NOW + timedelta(minutes=5 * i)
        rep = _rep(Status.CRIT) if i < 40 else _rep(Status.OK)
        alerts, st = H.plan_alerts(rep, st, now)
        out[i] = alerts
    assert out[0] == []
    assert len(out[1]) == 1
    assert all(out[i] == [] for i in range(2, 37))
    assert len(out[37]) == 1 and out[37][0].level is Status.CRIT  # 5 + 180 dk
    assert len(out[40]) == 1 and out[40][0].level is Status.OK


def test_immediate_and_multiple_and_failed_send():
    a0, st0 = H.plan_alerts(_rep(Status.CRIT, "disk_low", "disk_free"), None, NOW)
    assert a0 == []                                   # kirmizi cift dogrulama: ilk tur sari
    a, st = H.plan_alerts(_rep(Status.CRIT, "disk_low", "disk_free"), st0, NOW + timedelta(minutes=5))
    assert len(a) == 1
    # gonderim basarisiz -> geri al -> sonraki turda yeniden denenir
    st2 = H.revert_failed_alerts(st, st0, a)
    a2, _ = H.plan_alerts(_rep(Status.CRIT, "disk_low", "disk_free"), st2, NOW + timedelta(minutes=10))
    assert len(a2) == 1
    rs = tuple(H.CheckResult(f"c{i}", Status.CRIT, "disk_low", "d") for i in range(5))
    rep = H.HealthReport(NOW, rs, Status.CRIT, False)
    _, s3 = H.plan_alerts(rep, None, NOW)
    a3, _ = H.plan_alerts(rep, s3, NOW + timedelta(minutes=5))
    assert len(a3) == 1 and a3[0].code == "multiple" and a3[0].body and "c0" not in a3[0].body and "disk_low" not in a3[0].body
    # bakim penceresi
    a4, _ = H.plan_alerts(rep, None, NOW, maintenance_until=NOW + timedelta(hours=1))
    assert a4 == []


def test_notifiers():
    n = H.NullNotifier()
    al = H.Alert(Status.WARN, "x", "t", "b", "f", NOW)
    assert n.send(al) and n.sent == [al]
    assert H.LogNotifier().send(al) is True


class _Resp:
    def __init__(self, code):
        self.status = code

    def getcode(self):
        return self.status

    def close(self):
        pass


def test_heartbeat():
    with pytest.raises(ValueError):
        H.HttpsHeartbeat("http://x")
    calls, sleeps = [], []
    seq = [TimeoutError("x"), _Resp(200)]

    def opener(req, timeout):
        calls.append(req.full_url)
        v = seq.pop(0)
        if isinstance(v, Exception):
            raise v
        return v
    hb = H.HttpsHeartbeat("https://hc.example/ping/secret", opener=opener, sleep=sleeps.append)
    assert hb.ok(_rep(Status.OK)) is True and sleeps == [2.0]
    assert hb.fail(_rep(Status.CRIT)) is False  # fail url yok
    assert hb.ok(_rep(Status.CRIT)) is False  # CRIT'te nabiz asla
    assert "secret" not in repr(hb)

    def always_fail(req, timeout):
        raise TimeoutError()
    s2 = []
    hb = H.HttpsHeartbeat("https://hc.example/p", opener=always_fail, sleep=s2.append)
    assert hb.ok(_rep(Status.WARN)) is False and s2 == [2.0, 5.0]


def test_env_parse():
    assert H.parse_env_text("# c\n\nA=1\nB=http://x:1\n") == {"A": "1", "B": "http://x:1"}
    for bad in ("A=1 # n", "A = 1", 'A="1"', "a=1", "junk"):
        with pytest.raises(ValueError):
            H.parse_env_text(bad)


def test_health_import_is_pure():
    import subprocess
    code = ("import sys; sys.path.insert(0,'src'); import trader_core.health; "
            "print([m for m in ('pandas','numpy','freqtrade','docker') if m in sys.modules])")
    out = subprocess.run([sys.executable, "-c", code], cwd=ROOT, capture_output=True, text=True).stdout
    assert out.strip() == "[]"


# ----------------------------------------------------------------------------- yedek
def _mk_ledger(p, bot):
    from trader_core.ledger import open_ledger
    led = open_ledger(str(p), bot)
    led.close()


def _mk_ft(p):
    c = sqlite3.connect(p)
    c.execute("CREATE TABLE positions (id INTEGER PRIMARY KEY)")
    c.execute("INSERT INTO positions VALUES (1)")
    c.commit()
    c.close()


def test_backup_rotation_idempotent(tmp_path):
    B = _load("health_backup")
    var, bk = tmp_path / "var", tmp_path / "bk"
    for b in ("learner", "twin"):
        (var / b).mkdir(parents=True)
        _mk_ledger(var / b / "ledger.sqlite", b)
        _mk_ft(var / b / "state.sqlite")
    code, m = B.run_backup(bk, var, 14, now=NOW, bots=("learner", "twin"))
    assert code == 0 and m["ok"], m
    day = bk / "2026-11-16"
    assert (day / "ledger_learner.sqlite").exists() and not list(day.glob("*.partial"))
    assert m["files"]["state_twin.sqlite"]["positions"] == 1
    mf = json.loads((day / "MANIFEST.json").read_text())
    assert len(mf["files"]["ledger_learner.sqlite"]["sha256"]) == 64
    code2, _ = B.run_backup(bk, var, 14, now=NOW + timedelta(minutes=1), bots=("learner", "twin"))
    assert code2 == 0 and not list(bk.glob("*.failed*"))
    assert B.latest_ok_backup(bk) == NOW.replace(minute=30, second=0)
    # rotation
    for d in range(1, 16):
        p = bk / f"2026-11-{d:02d}"
        p.mkdir(exist_ok=True)
        (p / "MANIFEST.json").write_text(json.dumps({"ok": True}))
    (bk / "notes").mkdir()
    removed = B.rotate_backups(bk, 14, "2026-11-16")
    assert sorted(removed) == ["2026-11-01", "2026-11-02"] and (bk / "notes").exists()
    (day / "MANIFEST.json").write_text(json.dumps({"ok": False}))
    assert B.rotate_backups(bk, 3, "2026-11-16") == []
    with pytest.raises(ValueError):
        B.parse_keep_days("2")


def test_backup_failures(tmp_path):
    B = _load("health_backup")
    var, bk = tmp_path / "var", tmp_path / "bk"
    for b in ("learner", "twin"):
        (var / b).mkdir(parents=True)
        _mk_ledger(var / b / "ledger.sqlite", b)
        _mk_ft(var / b / "state.sqlite")
    code, m = B.run_backup(bk, var, 14, now=NOW, free_bytes=lambda: int(0.8 * GIB), bots=("learner", "twin"))
    assert code == 20 and all(f["error"] == "disk_low" for f in m["files"].values())
    # bozuk kaynak
    (var / "twin" / "ledger.sqlite").write_bytes(b"not a database" * 100)
    code, m = B.run_backup(bk, var, 14, now=NOW + timedelta(minutes=3), bots=("learner", "twin"))
    assert code == 20 and m["files"]["ledger_twin.sqlite"]["ok"] is False
    assert list(bk.glob("2026-11-16.failed-*"))


# ----------------------------------------------------------------------------- runner
def test_runner_run_once(tmp_path):
    R = _load("health_run")
    sent = []

    class S:
        def ok(self, rep):
            sent.append("ok")
            return True

        def fail(self, rep):
            sent.append("fail")
            return False
    import dataclasses
    env = {"HEARTBEAT_URL": "https://h.example/x"}
    sp = tmp_path / "state.json"
    fresh = lambda **kw: dataclasses.replace(snap(**kw), veto_file_mtime=NOW - timedelta(minutes=5))  # noqa: E731
    code = R.run_once(env, now=NOW, state_path=sp, notifier=H.NullNotifier(), sender=S(),
                      snapshot_fn=lambda e, s, n: fresh())
    assert code == 0 and sent == ["ok"]
    st = json.loads(sp.read_text())
    assert st["last_overall"] == "OK" and "installed_at" in st
    api = dict(snap().api)
    api["learner"] = ApiProbe()
    sent.clear()
    code = R.run_once(env, now=NOW, state_path=sp, notifier=H.NullNotifier(), sender=S(),
                      snapshot_fn=lambda e, s, n: fresh(api=api))
    assert code == 10 and sent == ["fail"]
    sp.write_text("{bozuk")
    state, reset = R.load_state(sp)
    assert reset and state["fingerprints"] == {}


def test_fail_sh_skips_without_url():
    import subprocess
    r = subprocess.run(["bash", str(ROOT / "scripts" / "health_fail.sh"), "x.service"], env={"PATH": "/usr/bin:/bin"},
                       capture_output=True, text=True)
    assert r.returncode == 0
