"""DD-7 (ban kalicilik) gerceklestirme testleri: P, M, F, T, G, S. Yalniz sahteler; ag yok.
(Sartname testleri `test_dd7_spec.py`te ayri ajan tarafindan; bu dosya gerceklemenin kendi sinamasidir.)"""
from __future__ import annotations

import ast
import json
import os
import sys
import urllib.error
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from fake_exchange import KEY, SECRET, FakeExchange, FakeResp
from test_live_broker_impl_smoke import DOGE, XRP, T0, build, req
from trader_core import ban_store as BS
from trader_core import health as H
from trader_engine.brokers.binance_futures import LiveBroker
from trader_engine.clock import SimClock
from trader_engine.config import LiveSettings
from trader_engine.errors import EngineExit
from trader_engine.exchange.binance_rest import BASES, SignedRestClient
from trader_engine.marketdata import oi_collector as C
from trader_engine.marketdata.rest_public import ExchangeBan, PublicRestClient

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))
UTC = timezone.utc
NOW = 1_800_000_000_000


# ============================================================================================ P
def test_p1_write_read_roundtrip(tmp_path):
    p = BS.ban_path(str(tmp_path), "https://fapi.binance.com")
    assert BS.write_ban(p, until_ms=NOW + 120_000, http=418, source="feed", now_ms=NOW) is True
    d = json.loads(Path(p).read_text())
    assert set(d) == {"v", "host", "until_ms", "http", "source", "written_ms"} and d["v"] == 1
    r = BS.read_ban(p, NOW)
    assert (r.until_ms, r.http, r.source, r.corrupt) == (NOW + 120_000, 418, "feed", False)
    assert BS.read_ban(p, NOW + 121_000) is None and os.path.exists(p)
    assert oct(os.stat(p).st_mode & 0o777) == "0o644"


def test_p2_short_windows_not_persisted(tmp_path):
    p = BS.ban_path(str(tmp_path), "https://fapi.binance.com")
    assert BS.write_ban(p, until_ms=NOW + 9_000, http=429, source="feed", now_ms=NOW) is True
    assert not os.path.exists(p)
    assert BS.write_ban(p, until_ms=NOW + 10_000, http=429, source="feed", now_ms=NOW) is True
    assert os.path.exists(p)


def test_p3_never_shortens(tmp_path):
    p = BS.ban_path(str(tmp_path), "https://fapi.binance.com")
    BS.write_ban(p, until_ms=NOW + 600_000, http=418, source="feed", now_ms=NOW)
    before = Path(p).read_bytes()
    assert BS.write_ban(p, until_ms=NOW + 60_000, http=429, source="oi", now_ms=NOW) is True
    assert Path(p).read_bytes() == before
    BS.write_ban(p, until_ms=NOW + 900_000, http=429, source="oi", now_ms=NOW)
    assert BS.read_ban(p, NOW).http == 429


@pytest.mark.parametrize("content", ["{", "[]", '{"v":1,"host":"fapi.binance.com","until_ms":"x","http":null,"source":"a","written_ms":1}',
                                     '{"v":1,"host":"fapi.binance.com","until_ms":true,"http":null,"source":"a","written_ms":1}',
                                     '{"v":2,"host":"fapi.binance.com","until_ms":9,"http":null,"source":"a","written_ms":1}',
                                     '{"v":1,"host":"other","until_ms":9,"http":null,"source":"a","written_ms":1}',
                                     "FUTURE"])
def test_p4_corrupt_fail_closed(tmp_path, content):
    p = BS.ban_path(str(tmp_path), "https://fapi.binance.com")
    if content == "FUTURE":
        content = json.dumps({"v": 1, "host": "fapi.binance.com", "until_ms": NOW + 10**6, "http": None, "source": "x",
                              "written_ms": NOW + 300_000})
    Path(p).write_text(content)
    os.utime(p, (NOW / 1000, NOW / 1000))
    r = BS.read_ban(p, NOW)
    assert r.corrupt and r.http is None and r.until_ms == NOW + 900_000
    os.utime(p, ((NOW - 901_000) / 1000, (NOW - 901_000) / 1000))
    assert BS.read_ban(p, NOW) is None


def test_p5_horizon_cap(tmp_path):
    p = BS.ban_path(str(tmp_path), "https://fapi.binance.com")
    Path(p).write_text(json.dumps({"v": 1, "host": "fapi.binance.com", "until_ms": NOW + 10 * 86_400_000, "http": 418,
                                   "source": "x", "written_ms": NOW}))
    assert BS.read_ban(p, NOW).until_ms == NOW + 259_200_000


def test_p6_errors_never_raise(tmp_path):
    d = tmp_path / "ban.fapi.binance.com.json"
    d.mkdir()
    assert BS.read_ban(str(d), NOW) is None
    assert BS.write_ban(str(tmp_path / "nodir" / "ban.x.json"), until_ms=NOW + 60_000, http=418, source="s", now_ms=NOW) is False


def test_p7_overwrites_corrupt(tmp_path):
    p = BS.ban_path(str(tmp_path), "https://fapi.binance.com")
    Path(p).write_text("{")
    assert BS.write_ban(p, until_ms=NOW + 120_000, http=418, source="feed", now_ms=NOW)
    assert BS.read_ban(p, NOW).corrupt is False


def test_p8_paths():
    assert BS.ban_path("/x/var", "https://FAPI.binance.com") == "/x/var/ban.fapi.binance.com.json"
    d = BS.ban_dir_for("var/market.sqlite")
    assert os.path.isabs(d) and d.endswith("var")


def test_p9_guard_refresh(tmp_path):
    p = BS.ban_path(str(tmp_path), "https://fapi.binance.com")
    t = [NOW]
    g1, g2 = BS.BanGuard(p, "feed", lambda: t[0]), BS.BanGuard(p, "oi", lambda: t[0])
    assert g1.active() is None
    assert g2.note(NOW + 120_000, 418)
    t[0] += 500
    assert g1.active() is None
    t[0] += 500
    assert g1.active().http == 418
    assert g2.active().source == "oi"


def test_p10_shared_dir_across_processes():
    import health_run  # noqa: F401
    import oi_collect
    from trader_engine.config import load_cli_config
    from trader_engine.marketdata.feed import feed_config_from_base
    cfg_dir = ROOT / "config"
    cwd = os.getcwd()
    os.chdir(ROOT)
    try:
        a = os.path.realpath(BS.ban_dir_for(feed_config_from_base(str(cfg_dir)).db_path))
        b = os.path.realpath(BS.ban_dir_for(oi_collect.load_pairs_and_db(cfg_dir)[1]))
        c = os.path.realpath(BS.ban_dir_for(load_cli_config(cfg_dir, "learner", "testnet").market_db))
    finally:
        os.chdir(cwd)
    assert a == b == c


def test_p11_stdlib_only():
    tree = ast.parse((ROOT / "src/trader_core/ban_store.py").read_text())
    mods = set()
    for n in ast.walk(tree):
        if isinstance(n, ast.Import):
            mods |= {a.name.split(".")[0] for a in n.names}
        elif isinstance(n, ast.ImportFrom) and n.module:
            mods.add(n.module.split(".")[0])
    assert mods <= set(sys.stdlib_module_names) | {"__future__"}


# ============================================================================================ M
def _rest(tmp_path, ex, clock, guard=True, env="testnet"):
    g = None
    if guard:
        g = BS.BanGuard(BS.ban_path(str(tmp_path), BASES[env]), "engine:learner",
                        lambda: int(clock.now().timestamp() * 1000))
    return SignedRestClient(env=env, api_key=KEY, api_secret=SECRET, session=ex.session,
                            now_ms=lambda: int(clock.now().timestamp() * 1000), sleep=clock.sleep, ban_guard=g)


@pytest.mark.parametrize("status,ra,http,left", [(418, "120", 418, 120_000), (429, "60", 429, 60_000), (403, None, 403, 300_000)])
def test_m1_client_persists_window(tmp_path, status, ra, http, left):
    clock = SimClock(T0)
    ex = FakeExchange(lambda: int(clock.now().timestamp() * 1000))
    rest = _rest(tmp_path, ex, clock)
    ex.inject("positionRisk", FakeResp(status, {"code": -1003, "msg": "x"}, {"Retry-After": ra} if ra else {}))
    now = int(clock.now().timestamp() * 1000)
    with pytest.raises(ExchangeBan):
        rest.position_risk()
    rec = BS.read_ban(BS.ban_path(str(tmp_path), BASES["testnet"]), now)
    assert (rec.http, rec.until_ms, rec.source) == (http, now + left, "engine:learner")


def test_m2_m3_short_429_and_451_not_persisted(tmp_path):
    clock = SimClock(T0)
    ex = FakeExchange(lambda: int(clock.now().timestamp() * 1000))
    rest = _rest(tmp_path, ex, clock)
    ex.inject("positionRisk", FakeResp(429, {"code": -1003, "msg": "x"}, {"Retry-After": "2"}))
    assert isinstance(rest.position_risk(), list)                      # satir ici bekleme + tekrar
    ex.inject("positionRisk", FakeResp(451, {"code": 0, "msg": "x"}))
    with pytest.raises(ExchangeBan):
        rest.position_risk()
    assert not os.path.exists(BS.ban_path(str(tmp_path), BASES["testnet"]))


def test_m4_seed_and_zero_requests(tmp_path):
    clock = SimClock(T0)
    now = int(clock.now().timestamp() * 1000)
    BS.write_ban(BS.ban_path(str(tmp_path), BASES["testnet"]), until_ms=now + 120_000, http=418, source="feed", now_ms=now)
    ex = FakeExchange(lambda: now)
    rest = _rest(tmp_path, ex, clock)
    assert rest.health()["ban_until_ms"] == now + 120_000 and rest.counters["ban_file_seeded"] == 1
    for kw in ({"protective": True}, {}):
        with pytest.raises(ExchangeBan) as e:
            rest.position_risk(**kw)
        assert e.value.http == 418
    assert ex.requests == []


def test_m10_unwritable_dir_counts_and_keeps_window(tmp_path):
    clock = SimClock(T0)
    ex = FakeExchange(lambda: int(clock.now().timestamp() * 1000))
    g = BS.BanGuard(str(tmp_path / "nodir" / "ban.testnet.binancefuture.com.json"), "engine:learner",
                    lambda: int(clock.now().timestamp() * 1000))
    rest = SignedRestClient(env="testnet", api_key=KEY, api_secret=SECRET, session=ex.session,
                            now_ms=lambda: int(clock.now().timestamp() * 1000), sleep=clock.sleep, ban_guard=g)
    ex.inject("positionRisk", FakeResp(418, {"code": -1003, "msg": "x"}, {"Retry-After": "120"}))
    with pytest.raises(ExchangeBan):
        rest.position_risk()
    assert rest.counters["ban_persist_failed"] == 1
    n = len(ex.requests)
    with pytest.raises(ExchangeBan):
        rest.position_risk()
    assert len(ex.requests) == n


def test_m5_m6_startup_exit_5(tmp_path):
    for http, left, sleep_s in ((418, 120, 122), (403, 120, 122), (418, 1000, 300)):
        clock = SimClock(T0)
        now = int(clock.now().timestamp() * 1000)
        BS.write_ban(BS.ban_path(str(tmp_path), BASES["testnet"]), until_ms=now + left * 1000, http=http, source="feed", now_ms=now)
        ex = FakeExchange(lambda: now)
        rest = _rest(tmp_path, ex, clock)
        slept = []
        clock.sleep = lambda s: slept.append(s)
        live = LiveSettings(account_tag="sub-acct", expected_wallet_max=1000.0)
        b = LiveBroker(live, "testnet", 3, [XRP, DOGE], rest, clock, 0.0005)
        with pytest.raises(EngineExit) as e:
            b.startup_check()
        assert e.value.code == 5 and "exchange_ban_persisted" in str(e.value)
        assert slept == [sleep_s] and ex.requests == []
        os.unlink(BS.ban_path(str(tmp_path), BASES["testnet"]))


def test_m5_corrupt_and_expired(tmp_path):
    clock = SimClock(T0)
    now = int(clock.now().timestamp() * 1000)
    p = BS.ban_path(str(tmp_path), BASES["testnet"])
    Path(p).write_text("{")
    os.utime(p, (now / 1000, now / 1000))
    ex = FakeExchange(lambda: now)
    live = LiveSettings(account_tag="sub-acct", expected_wallet_max=1000.0)
    b = LiveBroker(live, "testnet", 3, [XRP, DOGE], _rest(tmp_path, ex, clock), clock, 0.0005)
    with pytest.raises(EngineExit) as e:
        b.startup_check()
    assert e.value.code == 5 and ex.requests == []
    # suresi dolmus kayit: acilis normal, dosya yerinde
    BS.write_ban(p, until_ms=now + 20_000, http=418, source="feed", now_ms=now - 100_000)
    clock2 = SimClock(T0 + timedelta(seconds=60))
    ex2 = FakeExchange(lambda: int(clock2.now().timestamp() * 1000))
    b2 = LiveBroker(live, "testnet", 3, [XRP, DOGE], _rest(tmp_path, ex2, clock2), clock2, 0.0005)
    b2.startup_check()
    assert os.path.exists(p)


# ============================================================================================ G
def _set_weight(b, w):
    b._rest._used_weight, b._rest._weight_ts_ms = w, b._rest.now_ms()


def test_g_entry_weight_gate_live():
    b, ex, clock = build(env="live")
    b.prepare(XRP, 3)
    _set_weight(b, 1200)
    n = len(ex.requests)
    r = b.market_order(req("entry", 10.0))
    assert r.status == "rejected" and r.reason == "weight_high"
    assert len(ex.requests) == n
    c = b.counters()
    assert c["entry_weight_rejects"] == 1 and c["account_mode_unverified"] == 0 and not b.entries_blocked_reasons
    # cikis ve stop: etkilenmez (once 1199'da giris)
    _set_weight(b, 1199)
    assert b.market_order(req("entry", 10.0, seq=1)).status == "filled"
    _set_weight(b, 1200)
    assert b.place_stop(req("stop", 10.0, 1.9)).status == "accepted"
    assert b.market_order(req("exit", 10.0, seq=2)).status in ("accepted", "filled")


def test_g_testnet_skipped_and_stale_header():
    b, ex, clock = build(env="testnet")
    b.prepare(XRP, 3)
    _set_weight(b, 1500)
    assert b.market_order(req("entry", 10.0)).status == "filled"
    b2, ex2, clock2 = build(env="live")
    b2.prepare(XRP, 3)
    _set_weight(b2, 1500)
    clock2.advance(61)
    assert b2.market_order(req("entry", 10.0)).status == "filled"


def test_g_fail_closed_health_error():
    b, ex, clock = build(env="live")
    b.prepare(XRP, 3)
    b._rest.health = lambda: (_ for _ in ()).throw(RuntimeError("x"))
    r = b.market_order(req("entry", 10.0))
    assert r.reason == "weight_high"


# ============================================================================================ F
class _Sess:
    def __init__(self, clock, status=200, headers=None):
        self.calls, self.status, self.headers, self.clock = 0, status, headers or {}, clock

    def get(self, url, params=None, timeout=None):
        self.calls += 1
        r = FakeResp(self.status, {"serverTime": int(self.clock.now().timestamp() * 1000)}, dict(self.headers))
        return r


def _pub(tmp_path, clock, sess, src="feed"):
    g = BS.BanGuard(BS.ban_path(str(tmp_path), "https://fapi.binance.com"), src, lambda: int(clock.now().timestamp() * 1000))
    return PublicRestClient(session=sess, now_s=lambda: clock.now().timestamp(), sleep=clock.sleep, ban_guard=g), g


def test_f_public_client_blocks_and_persists(tmp_path):
    clock = SimClock(T0)
    now = int(clock.now().timestamp() * 1000)
    sess = _Sess(clock)
    rest, g = _pub(tmp_path, clock, sess)
    BS.write_ban(g.path, until_ms=now + 120_000, http=429, source="engine:learner", now_ms=now)
    clock.advance(1)
    with pytest.raises(ExchangeBan) as e:
        rest.get("/fapi/v1/time")
    assert e.value.http == 429 and sess.calls == 0
    # bozuk kayit -> 418
    Path(g.path).write_text("{")
    os.utime(g.path, ((now + 1000) / 1000,) * 2)
    clock.advance(1)
    with pytest.raises(ExchangeBan) as e2:
        rest.get("/fapi/v1/time")
    assert e2.value.http == 418 and sess.calls == 0


def test_f_public_418_persisted(tmp_path):
    clock = SimClock(T0)
    now = int(clock.now().timestamp() * 1000)
    sess = _Sess(clock, 418, {"Retry-After": "300"})
    rest, g = _pub(tmp_path, clock, sess)
    with pytest.raises(ExchangeBan):
        rest.get("/fapi/v1/time")
    rec = BS.read_ban(g.path, now)
    assert (rec.http, rec.until_ms, rec.source) == (418, now + 300_000, "feed")


def test_f_feed_start_waits_then_exit3(tmp_path):
    from trader_engine.marketdata import feed as F
    clock = SimClock(T0)
    now = int(clock.now().timestamp() * 1000)
    sess = _Sess(clock)
    rest, g = _pub(tmp_path, clock, sess)
    BS.write_ban(g.path, until_ms=now + 120_000, http=418, source="engine:learner", now_ms=now)
    f = F.Feed.__new__(F.Feed)
    f.rest, f.clock, f._c = rest, clock, {"bans": 0}
    slept = []
    clock.sleep = lambda s: slept.append(s)
    f._startup_ban_persisted()
    assert slept == [125] and sess.calls == 0 and f._c["bans"] == 1
    BS.write_ban(g.path, until_ms=now + 3_601_000, http=418, source="oi", now_ms=now)
    g._last_read_ms = None
    with pytest.raises(SystemExit) as e:
        f._startup_ban_persisted()
    assert e.value.code == F.EXIT_BAN and slept == [125]


def test_f_no_guard_noop():
    from trader_engine.marketdata import feed as F
    f = F.Feed.__new__(F.Feed)
    f.rest = object()
    f._startup_ban_persisted()


# ============================================================================================ T
class _Resp:
    def __init__(self, body, headers=None):
        self._b, self.headers = json.dumps(body).encode(), headers or {}

    def read(self):
        return self._b

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


def _http_err(code, ra=None):
    return urllib.error.HTTPError("u", code, "x", {"Retry-After": ra} if ra is not None else {}, None)


def test_t_client_blocked_by_guard(tmp_path, monkeypatch):
    p = BS.ban_path(str(tmp_path), C.BASE_URL)
    g = BS.BanGuard(p, "oi", lambda: NOW)
    BS.write_ban(p, until_ms=NOW + 120_000, http=418, source="feed", now_ms=NOW)
    calls = []
    monkeypatch.setattr(C.urllib.request, "urlopen", lambda *a, **k: calls.append(1))
    cl = C.HttpClient(ban_guard=g, now_ms=lambda: NOW, sleep=lambda s: None)
    with pytest.raises(C.BanError):
        cl.get_json("/x", {})
    assert calls == [] and cl.requests_made == 0


@pytest.mark.parametrize("code,ra,exp_http,exp_left", [(418, "300", 418, 300_000), (418, None, 418, 120_000), (429, "30", 429, 30_000)])
def test_t_client_persists(tmp_path, monkeypatch, code, ra, exp_http, exp_left):
    p = BS.ban_path(str(tmp_path), C.BASE_URL)
    g = BS.BanGuard(p, "oi", lambda: NOW)
    def boom(*a, **k):
        raise _http_err(code, ra)
    monkeypatch.setattr(C.urllib.request, "urlopen", boom)
    cl = C.HttpClient(ban_guard=g, now_ms=lambda: NOW, sleep=lambda s: None, max_attempts=1)
    with pytest.raises(C.BanError):
        cl.get_json("/x", {})
    rec = BS.read_ban(p, NOW)
    assert (rec.http, rec.until_ms, rec.source) == (exp_http, NOW + exp_left, "oi")


def test_t_weight_header(monkeypatch):
    seq = iter([_Resp([], {"X-MBX-USED-WEIGHT-1M": "1234"}), _Resp([], {}), _Resp([], {"X-MBX-USED-WEIGHT-1M": "abc"})])
    monkeypatch.setattr(C.urllib.request, "urlopen", lambda *a, **k: next(seq))
    cl = C.HttpClient(sleep=lambda s: None, min_interval_s=0)
    for _ in range(3):
        cl.get_json("/x", {})
        assert cl.last_used_weight == 1234


class _FakeClient:
    def __init__(self, stop_after=None, w=1200):
        self.requests_made, self.last_used_weight, self.stop_after, self.w = 0, None, stop_after, w

    def get_json(self, path, params):
        self.requests_made += 1
        if self.stop_after is not None and self.requests_made >= self.stop_after:
            self.last_used_weight = self.w
        return []


@pytest.mark.parametrize("w,stops", [(1200, True), (1199, False)])
def test_t_weight_ceiling(tmp_path, w, stops):
    db = C.open_db(tmp_path / "m.sqlite")
    cl = _FakeClient(stop_after=3, w=w)
    st = C.collect(db, cl, ["BTC/USDT", "ETH/USDT"], NOW)
    db.close()
    assert st.errors == 0
    if stops:
        assert cl.requests_made == 3 and st.budget_hit and st.weight_stop
    else:
        assert not st.weight_stop and cl.requests_made > 3


def test_t_main_skip_on_ban(tmp_path):
    import oi_collect
    BS.write_ban(BS.ban_path(str(tmp_path), C.BASE_URL), until_ms=NOW + 120_000, http=418, source="engine:learner", now_ms=NOW)

    class Boom:
        requests_made = 0

        def get_json(self, *a, **k):
            raise AssertionError("istek atilmamali")
    rc = oi_collect.main(["--db", str(tmp_path / "m.sqlite"), "--pairs", "BTC/USDT"], client=Boom(), now_ms=NOW)
    assert rc == oi_collect.EXIT_OK


def test_t_main_ban_exit_and_file(tmp_path, monkeypatch):
    import oi_collect

    def boom(*a, **k):
        raise _http_err(418, "300")
    monkeypatch.setattr(C.urllib.request, "urlopen", boom)
    monkeypatch.setattr(C.time, "sleep", lambda s: None)
    rc = oi_collect.main(["--db", str(tmp_path / "m.sqlite"), "--pairs", "BTC/USDT"], now_ms=NOW)
    assert rc == oi_collect.EXIT_BAN
    rec = BS.read_ban(BS.ban_path(str(tmp_path), C.BASE_URL), NOW)
    assert rec.http == 418 and rec.source == "oi" and rec.until_ms == NOW + 300_000


# ============================================================================================ S
HNOW = datetime(2026, 12, 1, 12, 0, tzinfo=UTC)


def _snap(bans, api=None):
    return H.HealthSnapshot(now=HNOW, api=api or {}, bans=bans)


def _ban_res(snap):
    return {r.name: r for r in H.evaluate(snap).results}.get("exchange_ban")


def test_s_decision_table():
    ban = H.BanProbe("fapi.binance.com", HNOW + timedelta(seconds=120), 418, "feed")
    pos = {"learner": H.ApiProbe(has_exchange=True, open_trade_ids=(7,))}
    r = _ban_res(_snap((ban,), pos))
    assert (r.status, r.code) == (H.Status.CRIT, "exchange_ban_open_positions") and r.value == 120
    assert _ban_res(_snap((ban,), {"learner": H.ApiProbe(has_exchange=True, open_trade_ids=())})).code == "exchange_ban"
    assert _ban_res(_snap((ban,), {"learner": H.ApiProbe(has_exchange=True, open_trade_ids=None)})).status is H.Status.CRIT
    assert _ban_res(_snap((ban,))).status is H.Status.WARN
    old = H.BanProbe("fapi.binance.com", HNOW - timedelta(seconds=1), 418, "feed")
    assert _ban_res(_snap((old,), pos)).status is H.Status.OK
    assert _ban_res(_snap(())).status is H.Status.OK
    assert _ban_res(_snap(None)) is None
    cor = H.BanProbe("h", None, None, None, True)
    assert _ban_res(_snap((cor,))).code == "exchange_ban_file_corrupt"
    assert _ban_res(_snap((cor, ban))).code == "exchange_ban"
    assert H.evaluate(_snap((ban,), pos)).overall is H.Status.CRIT


def _only(snap):
    """Yalniz exchange_ban sonucunu tasiyan rapor (eksik-zorunlu-kontrol gurultusu `multiple` ozetine donusmesin)."""
    r = _ban_res(snap)
    return H.HealthReport(snap.now, (r,), r.status, r.status in (H.Status.OK, H.Status.WARN))


def test_s_alerts_and_text():
    ban = H.BanProbe("fapi.binance.com", HNOW + timedelta(seconds=120), 418, "feed")
    pos = {"learner": H.ApiProbe(has_exchange=True, open_trade_ids=(7,))}
    rep = _only(_snap((ban,), pos))
    alerts, st = H.plan_alerts(rep, None, HNOW)
    a = [x for x in alerts if x.code == "exchange_ban_open_positions"]
    assert a and "elle kapatın" in a[0].body and "fapi.binance.com" in a[0].body and "açık pozisyon var" in a[0].title
    warn = _only(_snap((ban,), {"learner": H.ApiProbe(has_exchange=True, open_trade_ids=())}))
    assert any(x.code == "exchange_ban" for x in H.plan_alerts(warn, None, HNOW)[0])
    later = HNOW + timedelta(minutes=10)
    ok = _only(H.HealthSnapshot(now=later, api=pos, bans=(ban,)))
    alerts2, _ = H.plan_alerts(ok, st, later)
    assert any("Borsa engeli kalktı" in x.title for x in alerts2)
    for code in ("exchange_ban_open_positions", "exchange_ban", "exchange_ban_file_corrupt"):
        assert code in H._HEALTH_TR_CODE


def test_s_probe_bans(tmp_path):
    import health_run as HR
    BS.write_ban(str(tmp_path / "ban.a.json"), until_ms=NOW + 120_000, http=418, source="feed", now_ms=NOW)
    (tmp_path / "ban.b.json").write_text("{")
    (tmp_path / "ban.a.json.lock").write_text("")
    (tmp_path / "ban.a.json.tmp.1").write_text("x")
    import time as _t
    real = int(_t.time() * 1000)
    BS.write_ban(str(tmp_path / "ban.c.json"), until_ms=real + 120_000, http=429, source="oi", now_ms=real)
    rows = {r.host: r for r in HR.probe_bans(str(tmp_path))}
    assert set(rows) == {"a", "b", "c"}
    assert rows["b"].corrupt and rows["b"].until is None
    assert rows["c"].http == 429 and rows["c"].source == "oi" and not rows["c"].corrupt
    assert HR.probe_bans(str(tmp_path / "yok")) == ()


def test_s_snapshot_backcompat():
    s = H.HealthSnapshot(now=HNOW)
    assert s.bans is None


# ============================================================================================ D1 / D2 (mentor)
def _status_engine(tmp_path, monkeypatch):
    import test_dd8_spec as D8
    from trader_engine.status import StatusWriter
    orig = D8.SignedRestClient

    def factory(*a, **k):
        k["ban_guard"] = BS.BanGuard(BS.ban_path(str(tmp_path), BASES[k["env"]]), source="engine:learner", now_ms=k["now_ms"])
        return orig(*a, **k)
    monkeypatch.setattr(D8, "SignedRestClient", factory)
    e = D8.DEnv(tmp_path, mode="testnet", wallet=100).boot()
    e.engine.status = StatusWriter(e.cfg.status_path, e.clock, e.cfg)
    return e


def test_d1_stale_account_not_published_as_fresh(tmp_path, monkeypatch):
    e = _status_engine(tmp_path, monkeypatch)
    try:
        e.tick(6.0)
        ok = json.loads(Path(e.cfg.status_path).read_text())
        assert isinstance(ok["equity"], (int, float)) and not ok.get("account_stale")
        now = int(e.clock.now().timestamp() * 1000)
        until = now + 120_000
        assert BS.BanGuard(BS.ban_path(str(tmp_path), BASES["testnet"]), "feed", lambda: now).note(until, 418)
        e.tick(6.0)
        st = json.loads(Path(e.cfg.status_path).read_text())
        assert st["equity"] is None and st["wallet"] is None and st["account_stale"] is True
        assert st["exchange"]["ban_until_ms"] == until
        loop = datetime.strptime(st["loop_at"], "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=UTC)
        assert abs((e.clock.now() - loop).total_seconds()) < 30
        assert st.get("equity_last") == ok["equity"] and "account_at" in st
        # telegram: equity yok => loop_ok False; /kademe_devam reddi
        sys.path.insert(0, str(ROOT / "tests"))
        import test_telegram_ladder_impl as TL
        rig = TL.Rig(tmp_path / "tg")
        d = dict(st)
        d["loop_at"] = TL.z(TL.T0 - timedelta(seconds=5))
        d["risk_ladder"] = {"enforce": True, "state": "review", "gate_code": None, "counters": {}}
        rig.status_path.write_text(json.dumps(d))
        v = TL.T.ladder_view(rig.d.ladders["learner"], TL.T0)
        assert v["equity"] is None and v["loop_ok"] is False
        refusal, _ = rig.d._ladder_resume_refusal()
        assert refusal and refusal.startswith("Motor durumu okunamıyor")
        # pencere bitti ve okuma basarili: taze
        e.clock.advance(130)
        e.tick(6.0)
        e.tick(6.0)
        st2 = json.loads(Path(e.cfg.status_path).read_text())
        assert isinstance(st2["equity"], (int, float)) and not st2.get("account_stale")
    finally:
        e.close()


def test_d1_paper_account_error_propagates():
    from trader_engine.engine import Engine

    class Boom:
        is_simulated = True

        def account(self):
            raise RuntimeError("x")
    eng = Engine.__new__(Engine)
    eng.broker, eng.clock = Boom(), SimClock(T0)
    with pytest.raises(RuntimeError):
        eng.status_fields()


def test_d2_collect_bans_fallbacks(tmp_path):
    import health_run as HR
    now = int(__import__("time").time() * 1000)
    var = tmp_path / "var"
    var.mkdir()
    BS.write_ban(str(var / "ban.fapi.binance.com.json"), until_ms=now + 120_000, http=418, source="feed", now_ms=now)
    rows = HR.collect_bans({}, str(var))
    assert len(rows) == 1 and rows[0].host == "fapi.binance.com"
    snap = H.HealthSnapshot(now=datetime.now(UTC), bans=rows, api={"learner": H.ApiProbe(has_exchange=True, open_trade_ids=(1,))})
    assert _ban_res(snap).code == "exchange_ban_open_positions"
    other = tmp_path / "other"
    other.mkdir()
    assert HR.collect_bans({"MARKET_DB": str(other / "m.sqlite")}, str(var)) == ()          # MARKET_DB > var_dir
    assert len(HR.collect_bans({"MARKET_DB": str(other / "m.sqlite"), "HEALTH_BAN_DIR": str(var)}, str(other))) == 1   # HEALTH_BAN_DIR > MARKET_DB
    assert HR.collect_bans({}, str(tmp_path / "yok")) == ()
