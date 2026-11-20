"""WP-1 (docs/saglik-spec.md 16): ML paketi suresi/tazeligi, runner meta okuma, rapor satiri, sapma kancasi. Uygulama testleri."""
import hashlib
import importlib.util
import json
import subprocess
import sys
from dataclasses import replace
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from trader_core import health as H
from trader_core import telegram as T

UTC = timezone.utc
NOW = datetime(2026, 12, 10, 12, 0, tzinfo=UTC)
ROOT = Path(__file__).resolve().parent.parent
D = timedelta(days=1)


def _runner():
    spec = importlib.util.spec_from_file_location("health_run_ml", ROOT / "scripts" / "health_run.py")
    m = importlib.util.module_from_spec(spec)
    sys.path.insert(0, str(ROOT / "scripts"))
    spec.loader.exec_module(m)
    return m


R = _runner()


def ev(probe=None, cfg=H.DEFAULT_CFG, prev=None, **kw):
    snap = H.HealthSnapshot(now=NOW, ml={"learner": probe} if probe is not None else None,
                            prev_ml_score_errors=prev or {}, **kw)
    return {r.name: r for r in H.evaluate(snap, cfg).results}, H.evaluate(snap, cfg)


def mlp(**kw):
    base = dict(present=True, mode="active", state="ok", expires_at=NOW + 10 * D, model_id="r02@aaaaaaaaaaaa")
    base.update(kw)
    return H.MlProbe(**base)


def get(probe, **kw):
    return ev(probe, **kw)[0]["ml_package:learner"]


def test_opt_in_and_required_unchanged():
    res, rep = ev(None)
    assert not [n for n in res if n.startswith("ml_package")]
    assert "ml_package" not in H.REQUIRED_CHECKS


def test_off_and_unreadable():
    assert get(H.MlProbe(present=False)).code == "ml_off"
    assert get(H.MlProbe(present=True, mode="off")).status is H.Status.SKIPPED
    r = get(H.MlProbe(present=None))
    assert (r.status, r.code) == (H.Status.UNKNOWN, "ml_status_unreadable")


@pytest.mark.parametrize("delta,code", [
    (7 * D + timedelta(seconds=1), None), (7 * D, "ml_expiring_7d"), (3 * D + timedelta(seconds=1), "ml_expiring_7d"),
    (3 * D, "ml_expiring_3d"), (1 * D, "ml_expiring_1d"), (timedelta(seconds=1), "ml_expiring_1d")])
def test_expiry_thresholds(delta, code):
    r = get(mlp(expires_at=NOW + delta))
    assert r.code == (code or "ok")
    assert r.status is (H.Status.WARN if code else H.Status.OK)


def test_active_expired_no_model_and_shadow():
    r = get(mlp(state="expired", expires_at=None))
    assert (r.status, r.code) == (H.Status.CRIT, "ml_expired")
    assert "ml_expired" in H.IMMEDIATE_CODES and "ml_no_model" in H.IMMEDIATE_CODES
    r = get(mlp(state="no_model", expires_at=None, error="PackageError: model suresi dolmus"))
    assert r.code == "ml_no_model" and "model suresi dolmus" in r.detail
    for st in ("expired", "no_model"):
        r = get(mlp(mode="shadow", state=st, expires_at=None))
        assert (r.status, r.code) == (H.Status.WARN, "ml_shadow_down")
    assert get(mlp(mode="shadow", expires_at=NOW + 2 * D)).code == "ml_expiring_3d"


def test_invalid():
    assert get(mlp(expires_at=None)).code == "ml_status_invalid"
    assert get(mlp(mode="turbo")).status is H.Status.UNKNOWN


def _file(**kw):
    d = dict(file_state="ok", file_model_id="r02@bbbbbbbbbbbb", file_created_at=NOW - D, file_expires_at=NOW + 20 * D,
             file_gate_passed=True, file_user_approved=True)
    d.update(kw)
    return d


def test_restart_needed():
    assert get(mlp(**_file())).code == "ml_restart_needed"
    assert get(mlp(**_file(file_user_approved=False))).status is H.Status.OK
    assert get(mlp(mode="shadow", **_file(file_user_approved=False))).code == "ml_restart_needed"
    assert get(mlp(**_file(file_expires_at=NOW))).status is H.Status.OK
    assert get(mlp(**_file(file_gate_passed=None))).status is H.Status.OK
    # ayni model: tetiklemez
    assert get(mlp(**_file(file_model_id="r02@aaaaaaaaaaaa"))).status is H.Status.OK


def test_worst_wins_and_detail_lists_all():
    r = get(mlp(state="expired", **_file()))
    assert r.status is H.Status.CRIT and r.code == "ml_expired" and "ml_restart_needed" in r.detail


def test_file_invalid():
    for kw in (dict(file_state="missing"), dict(file_state="unreadable"),
               _file(file_created_at=NOW + timedelta(minutes=6)), _file(file_model_id=None)):
        assert get(mlp(**kw)).code == "ml_file_invalid"
    assert get(mlp(**_file(file_model_id="r02@aaaaaaaaaaaa", file_created_at=NOW + timedelta(minutes=4)))).status is H.Status.OK
    r = get(mlp())
    assert r.status is H.Status.OK and "paket yolu bilinmiyor" in r.detail


def test_stale_flag_and_absolute_age():
    same = _file(file_model_id="r02@aaaaaaaaaaaa")
    assert get(mlp(file_stale=True, **same)).code == "ml_stale_data"
    far = dict(same, file_created_at=NOW - D, file_train_end=NOW - D - 220 * D)
    assert get(mlp(**far)).status is H.Status.OK
    cfg = replace(H.DEFAULT_CFG, ml_data_max_age_days=14)
    assert get(mlp(**dict(far, file_train_end=NOW - D - 15 * D)), cfg=cfg).code == "ml_stale_data"
    assert get(mlp(**dict(far, file_train_end=NOW - D - 14 * D)), cfg=cfg).status is H.Status.OK


def test_score_errors():
    assert get(mlp(score_errors=5), prev={"learner": 3}).code == "ml_score_errors"
    assert get(mlp(score_errors=5)).status is H.Status.OK
    assert get(mlp(score_errors=0), prev={"learner": 5}).status is H.Status.OK
    r = get(mlp(score_errors=None), prev={"learner": 5})
    assert r.status is H.Status.OK and "sayaç okunamadı" in r.detail


def test_crit_cuts_heartbeat_warn_does_not():
    assert not H.should_send_ok(ev(mlp(state="expired"))[1])
    rep = ev(mlp(expires_at=NOW + 2 * D))[1]
    assert H.combine([r for r in rep.results if r.name.startswith("ml_package")]) is H.Status.WARN


def test_alert_texts_and_thresholds():
    def alerts(code_probe, state=None, now=NOW):
        rep = ev(code_probe)[1]
        return H.plan_alerts(rep, state, now, replace(H.DEFAULT_CFG, multiple_threshold=100))
    a0, st0 = alerts(mlp(state="expired"))
    assert not a0                                  # kirmizi cift dogrulama: ilk tur mesaj yok
    a, st = alerts(mlp(state="expired"), st0, NOW + timedelta(minutes=5))
    ml = [x for x in a if x.code == "ml_expired"]
    assert ml and "Modelin süresi doldu" in ml[0].title
    for x in a:
        for raw in ("ml_expired", "ml_package", "r02@"):
            assert raw not in x.title + x.body
    # 7g uyari 2. turda; 3g yeni uyari
    p7 = mlp(expires_at=NOW + 7 * D)
    a1, s1 = alerts(p7)
    a2, s2 = alerts(p7, s1)
    assert any(x.code == "ml_expiring_7d" for x in a2)
    a3, s3 = alerts(p7, s2)
    assert not any(x.code == "ml_expiring_7d" for x in a3)
    p3 = mlp(expires_at=NOW + 3 * D)
    a4, s4 = alerts(p3, s3)
    a5, s5 = alerts(p3, s4)
    assert any(x.code == "ml_expiring_3d" for x in a4 + a5)
    a6, _ = alerts(mlp(), s5)
    assert any("Düzeldi" in x.title and "Model yenilendi" in x.title for x in a6)
    # golge kipte anlam cumlesi
    sh = [x for x in alerts(mlp(mode="shadow", expires_at=NOW + 2 * D))[0]]
    a2, _ = alerts(mlp(mode="shadow", expires_at=NOW + 2 * D), alerts(mlp(mode="shadow", expires_at=NOW + 2 * D))[1])
    assert any("gölge izleme durur" in x.body for x in a2)
    # DD-12: ikiz eki yok
    assert "ikiz" not in H._health_tr("ml_package:twin", "ml_restart_needed")[0]
    for code, (s_, d_, _a) in H._HEALTH_TR_CODE.items():
        assert len(s_) <= 68 and len(d_) <= 68, code


def test_drift_placeholder_and_enabled():
    res = {r.name: r for r in H.evaluate(H.HealthSnapshot(now=NOW)).results}
    assert res["drift_monitor:learner"].status is H.Status.SKIPPED and res["drift_monitor:learner"].code == "placeholder"
    cfg = replace(H.DEFAULT_CFG, drift_check_enabled=True)

    def dr(probe):
        snap = H.HealthSnapshot(now=NOW, drift={"learner": probe} if probe else {})
        return {r.name: r for r in H.evaluate(snap, cfg).results}["drift_monitor:learner"]
    assert dr(None).code == "drift_missing"
    assert dr(H.DriftProbe("ok", NOW - timedelta(hours=36), "OK")).status is H.Status.OK
    assert dr(H.DriftProbe("ok", NOW - timedelta(hours=36, seconds=1), "OK")).code == "drift_stale"
    r = dr(H.DriftProbe("ok", NOW, "UYARI", ("R1",)))
    assert r.code == "drift_alert" and "R1" in r.detail
    for o in ("IZLE", "YETERSIZ", "OK"):
        assert dr(H.DriftProbe("ok", NOW, o)).status is H.Status.OK
    assert dr(H.DriftProbe("ok", NOW, "CRIT")).code == "drift_unreadable"
    assert dr(H.DriftProbe("unreadable")).code == "drift_unreadable"
    for pr in (None, H.DriftProbe("ok", NOW, "UYARI"), H.DriftProbe("ok", NOW, "CRIT")):
        assert dr(pr).status not in (H.Status.CRIT, H.Status.UNKNOWN)
    a, _ = H.plan_alerts(H.evaluate(H.HealthSnapshot(now=NOW, drift={"learner": H.DriftProbe("ok", NOW, "UYARI")}), cfg),
                         None, NOW)
    assert all("drift" not in x.title.lower() for x in a)


def test_health_stdlib_only():
    code = ("import sys; import trader_core.health; "
            "bad=[m for m in ('numpy','trader_core.ml_package','trader_engine') if m in sys.modules]; print(bad)")
    out = subprocess.run([sys.executable, "-c", code], cwd=ROOT, capture_output=True, text=True,
                         env={"PYTHONPATH": str(ROOT / "src"), "PATH": "/usr/bin"}).stdout.strip()
    assert out == "[]"


# ------------------------------------------------------------------ runner
def pkg(tmp_path, created, **meta_kw):
    meta = {"version": "r02", "created_at": created, "expires_at": created, "model_hash": "c" * 64,
            "data_hash": "dh1", "train_window": {"start": "2025-01-01T00:00:00", "end": "2026-04-30T00:00:00"},
            "gate_passed": True, "user_approved": True}
    meta.update(meta_kw)
    p = tmp_path / "m.json"
    p.write_text(json.dumps({"meta": meta, "model": {}}))
    return p


def test_read_meta_tz_and_expiry_cap(tmp_path):
    created = datetime(2026, 12, 1, 0, 0)
    p = pkg(tmp_path, created.isoformat(), expires_at=(created + 40 * D).isoformat())
    before = hashlib.sha256(p.read_bytes()).hexdigest()
    f = R.read_package_meta(str(p))
    assert f["file_state"] == "ok" and f["file_created_at"].tzinfo is not None
    assert f["file_expires_at"] == created.replace(tzinfo=UTC) + 21 * D
    assert f["file_model_id"] == "r02@" + "c" * 12
    assert f["file_train_end"] == datetime(2026, 4, 30, tzinfo=UTC)
    assert hashlib.sha256(p.read_bytes()).hexdigest() == before
    p2 = pkg(tmp_path, created.isoformat(), data_snapshot_at="2026-11-30T00:00:00Z")
    assert R.read_package_meta(str(p2))["file_train_end"] == datetime(2026, 11, 30, tzinfo=UTC)


def test_read_meta_failures(tmp_path, monkeypatch):
    assert R.read_package_meta(None)["file_state"] == "not_configured"
    assert R.read_package_meta(str(tmp_path / "yok.json"))["file_state"] == "missing"
    bad = tmp_path / "b.json"
    bad.write_text("{not json")
    assert R.read_package_meta(str(bad))["file_state"] == "unreadable"
    monkeypatch.setattr(R, "ML_PKG_MAX_BYTES", 10)
    big = pkg(tmp_path, "2026-12-01T00:00:00")
    assert R.read_package_meta(str(big))["file_state"] == "unreadable"


def test_model_path_resolution(tmp_path):
    cd = tmp_path / "cfg"
    cd.mkdir()
    (cd / "engine.base.json").write_text(json.dumps({"ml_model_path": "/a/base.json"}))
    (cd / "engine.twin.json").write_text(json.dumps({"ml_model_path": "/a/twin.json"}))
    env = {"ENGINE_CONFIG_DIR": str(cd)}
    assert R.ml_model_path(env, "learner") == "/a/base.json"
    assert R.ml_model_path(env, "twin") == "/a/twin.json"
    assert R.ml_model_path({**env, "ML_MODEL_PATH_LEARNER": "/x.json"}, "learner") == "/x.json"
    assert R.ml_model_path({}, "learner") is None


def _f(mid, created, dh, end):
    return {"file_model_id": mid, "file_created_at": created, "file_data_hash": dh, "file_train_end": end}


def test_stale_sequence():
    t0, e0 = NOW - 10 * D, NOW - 200 * D
    rec, stale = R.ml_stale_update(None, _f("a", t0, "h1", e0))
    assert not stale                                                       # a: taban
    rec2, stale = R.ml_stale_update(rec, _f("b", t0 + D, "h1", e0))
    assert stale                                                           # b: ayni hash+end
    _, stale = R.ml_stale_update(rec2, _f("b", t0 + D, "h1", e0))
    assert stale                                                           # f: devam
    _, stale = R.ml_stale_update(rec2, _f("c", t0 + 2 * D, "h2", e0 + 7 * D))
    assert not stale                                                       # c
    _, stale = R.ml_stale_update(rec2, _f("c", t0 + 2 * D, "h2", e0))
    assert not stale                                                       # d: hash farkli
    _, stale = R.ml_stale_update(rec2, _f("z", t0 - D, "h9", e0 + 50 * D))
    assert stale                                                           # e: eski paket


def _status(var, bot, ml, counters=None):
    d = var / bot
    d.mkdir(parents=True, exist_ok=True)
    (d / "status.json").write_text(json.dumps({"schema": "engine-status/1", "bot": bot, "ml": ml,
                                               "counters": counters or {}}))


def test_probe_ml_status(tmp_path):
    _status(tmp_path, "learner", {"mode": "active", "state": "ok", "model_id": "r02@x", "expires_at": "2026-12-20T00:00:00",
                                  "error": None, "v2_errors": 2}, {"ml_score_errors": 3})
    s = R.probe_ml_status(str(tmp_path / "learner" / "status.json"), "learner", NOW)
    assert s["present"] is True and s["score_errors"] == 5 and s["expires_at"].tzinfo is not None
    _status(tmp_path, "twin", None)
    assert R.probe_ml_status(str(tmp_path / "twin" / "status.json"), "twin", NOW)["present"] is False
    assert R.probe_ml_status(str(tmp_path / "yok.json"), "learner", NOW)["present"] is None


def test_run_once_persists_ml_state(tmp_path):
    var = tmp_path / "var"
    _status(var, "learner", {"mode": "active", "state": "ok", "model_id": "r02@" + "c" * 12,
                             "expires_at": (NOW + 15 * D).isoformat(), "error": None, "v2_errors": 0})
    p = pkg(tmp_path, (NOW - 5 * D).isoformat())
    env = {"ENGINE_VAR_DIR": str(var), "BACKUP_DIR": str(tmp_path / "bk"), "ENGINE_BOTS": "learner",
           "ML_MODEL_PATH_LEARNER": str(p), "STATE_DIR": str(tmp_path / "st")}
    snap = R.collect(env, {}, NOW)
    assert snap.ml["learner"].file_state == "ok" and snap.ml["learner"].file_stale is False
    _status(var, "learner", None)
    assert R.collect({k: v for k, v in env.items() if k != "ML_MODEL_PATH_LEARNER"}, {}, NOW).ml is None


# ------------------------------------------------------------------ telegram
def mkcfg(tmp_path, ml, **extra):
    st = {"loop_at": NOW.strftime("%Y-%m-%dT%H:%M:%SZ"), "mode": "dry_run", "equity": 1000.0, "day_start_equity": 1000.0,
          "entries_open": True, "ml": ml}
    st.update(extra)
    (tmp_path / "status.json").write_text(json.dumps(st))
    hs = tmp_path / "hs.json"
    return T.TelegramConfig("1:tok", 5, str(tmp_path / "tg"), "", str(tmp_path / "status.json"), health_state=str(hs),
                            ledger_path=str(tmp_path / "l.sqlite"),
                            budget_config=str(tmp_path / "b.json"), lesson_store=str(tmp_path / "ls.sqlite"))


def report(cfg):
    # gunluk ozet kisa; model bolumu /rapor komutlarinda ve panelde: bolum cikisi dogrudan sinanir
    return T.rapor_model(cfg, NOW)


def iso(dt):
    return dt.strftime("%Y-%m-%dT%H:%M:%SZ")


@pytest.mark.parametrize("ml,expect", [
    (None, "🤖 Model filtresi kapalı (bot filtresiz çalışıyor)"),
    ({"mode": "shadow", "state": "ok", "expires_at": iso(NOW + 12 * D + timedelta(hours=5))},
     "🤖 Model gölgede izliyor, kararları etkilemiyor · süresi 12 gün sonra doluyor"),
    ({"mode": "active", "state": "ok", "expires_at": iso(NOW + 12 * D)}, "🤖 Model filtresi açık · süresi 12 gün sonra doluyor"),
    ({"mode": "active", "state": "ok", "expires_at": iso(NOW + 5 * D + timedelta(hours=23))},
     "⚠️ Model filtresi açık ama süresi 5 gün sonra doluyor; yenilenmezse yeni işlemler durur"),
    ({"mode": "active", "state": "ok", "expires_at": iso(NOW + timedelta(hours=20))}, "süresi 20 saat sonra doluyor"),
    ({"mode": "active", "state": "ok", "expires_at": iso(NOW + timedelta(minutes=20))}, "süresi 1 saat sonra doluyor"),
    ({"mode": "shadow", "state": "ok", "expires_at": iso(NOW + 5 * D)},
     "⚠️ Gölgedeki modelin süresi 5 gün sonra doluyor (işlemler etkilenmez)"),
    ({"mode": "active", "state": "expired"}, "🚨 Modelin süresi doldu: yeni işlem açılmıyor, açık pozisyonlar korunuyor"),
    ({"mode": "active", "state": "no_model"}, "🚨 Model yüklenemedi: yeni işlem açılmıyor, açık pozisyonlar korunuyor"),
    ({"mode": "shadow", "state": "no_model"}, "⚠️ Gölgedeki model çalışmıyor (işlemler etkilenmiyor)"),
    ({"mode": "shadow", "state": "expired"}, "⚠️ Gölgedeki model çalışmıyor (işlemler etkilenmiyor)")])
def test_report_lines(tmp_path, ml, expect):
    out = report(mkcfg(tmp_path, ml))
    assert expect in out
    assert "Bazı bilgiler okunamadı" not in out
    for raw in ("expired", "no_model", "shadow", "active", "model_id"):
        assert raw not in out


def test_report_blocked_risk_text_and_order(tmp_path):
    cfg = mkcfg(tmp_path, {"mode": "active", "state": "expired"}, entries_open=False, gate={"code": "ml_expired"})
    out = T.build_report(cfg, NOW, "2026-12-10", {})
    assert "Yeni işlemler kapalı." in out and "hazır değil" not in out and "ml_expired" not in out
    assert T.neden_tr("ml_expired") == "modelin süresi doldu" and T.neden_tr("ml_no_model") == "model yüklenemedi"
    assert T.neden_tr("ml_other") == "yapay zekâ filtresi hazır değil"
    cfg = mkcfg(tmp_path, {"mode": "shadow", "state": "no_model"})
    assert "Yeni işlemler kapalı" not in T.build_report(cfg, NOW, "2026-12-10", {})


def test_report_health_suffix(tmp_path):
    cfg = mkcfg(tmp_path, {"mode": "active", "state": "ok", "expires_at": iso(NOW + 12 * D)})
    Path(cfg.health_state).write_text(json.dumps({"fingerprints": {"ml_package:learner|ml_restart_needed": {}},
                                                  "ml_seen": {"learner": {"stale": True}}}))
    out = report(cfg)
    assert " · yeni model hazır, motorun yeniden başlatılması gerekiyor" in out
    assert "yeni model eski veriyle üretilmiş görünüyor" in out


def test_report_bad_block_and_default_sections(tmp_path):
    cfg = mkcfg(tmp_path, ["bozuk"])
    with pytest.raises(T.SectionError):                      # bozuk blok bolumde SectionError; ozet yine uretilir
        report(cfg)
    out = T.build_report(cfg, NOW, "2026-12-10", {})
    assert "bozuk" not in out and "Günlük özet" in out
    cfg = mkcfg(tmp_path, None)
    assert "Model filtresi kapalı" in T.default_sections(cfg, NOW, "2026-12-10")["Model"]()
    secs = list(T.default_sections(cfg, NOW, "2026-12-10"))
    assert secs.index("Model") < secs.index("Davranış")


def test_opt_in_status_block_without_path(tmp_path):
    var = tmp_path / "var"
    _status(var, "learner", {"mode": "active", "state": "no_model", "model_id": None, "expires_at": None,
                             "error": "ml_model_path_missing", "v2_errors": 0})
    env = {"ENGINE_VAR_DIR": str(var), "BACKUP_DIR": str(tmp_path / "bk"), "HEALTH_BOTS": "learner"}
    snap = R.collect(env, {}, NOW)
    assert snap.ml is not None and snap.ml["learner"].file_state == "not_configured"
    rep = H.evaluate(snap)
    r = {x.name: x for x in rep.results}["ml_package:learner"]
    assert (r.status, r.code) == (H.Status.CRIT, "ml_no_model")
    assert not H.should_send_ok(rep)
    _status(var, "learner", {"mode": "off", "state": "off"})
    assert R.collect(env, {}, NOW).ml is None
    _status(var, "learner", None)
    assert R.collect(env, {}, NOW).ml is None


def test_score_errors_alert_immediate():
    assert "ml_score_errors" in H.IMMEDIATE_WARN_CODES and "ml_score_errors" not in H.IMMEDIATE_CODES
    rep = ev(mlp(score_errors=5), prev={"learner": 3})[1]
    a, _ = H.plan_alerts(rep, None, NOW, replace(H.DEFAULT_CFG, multiple_threshold=100))
    assert any(x.code == "ml_score_errors" and "puanlayamıyor" in x.title for x in a)


def test_version_not_required(tmp_path):
    p = pkg(tmp_path, "2026-12-01T00:00:00")
    d = json.loads(p.read_text())
    d["meta"].pop("version")
    p.write_text(json.dumps(d))
    f = R.read_package_meta(str(p))
    assert f["file_state"] == "ok" and f["file_model_id"].startswith("?@")
    d["meta"].pop("gate_passed")
    p.write_text(json.dumps(d))
    assert R.read_package_meta(str(p))["file_state"] == "unreadable"
