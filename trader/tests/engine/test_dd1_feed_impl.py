"""DD-1 (feed dayanikliligi): calisirken bosluk doldurma, suresiz acilis denemesi, bozuk JSON, ban ust siniri,
bozuk mum (h<l) icin istek firtinasi yok. Sahte oturum/saat; ag ve gercek uyku yok."""
from __future__ import annotations

import dataclasses
from datetime import timedelta

import pytest

from test_engine_01_spec import BTC, ETH, T_START, Resp, dt, make_env, raw
from trader_engine.bars import to_ms
from trader_engine.marketdata import feed as F
from trader_engine.marketdata.feed import Feed
from trader_engine.marketdata.rest_public import ExchangeBan, ExchangeError, PublicRestClient


# ----------------------------------------------------------------------------- rest_public
class _Sess:
    def __init__(self, seq):
        self.seq, self.n = list(seq), 0

    def get(self, url, params=None, timeout=None):
        self.n += 1
        x = self.seq.pop(0)
        if isinstance(x, Exception):
            raise x
        return x


class _BadJson(Resp):
    def json(self):
        raise ValueError("Expecting value: line 1 column 1 (char 0)")


def _client(seq, **kw):
    sl = []
    return PublicRestClient(session=_Sess(seq), now_s=lambda: 1000.0, sleep=sl.append, **kw), sl


def test_bad_json_becomes_exchange_error_not_valueerror():
    c, sl = _client([_BadJson(200)] * 3, max_attempts=3)
    with pytest.raises(ExchangeError) as ei:
        c.get("/x")
    assert not isinstance(ei.value, ValueError) and "JSON" in str(ei.value)
    assert sl == [2, 4, 8]


def test_bad_json_then_ok_recovers():
    c, sl = _client([_BadJson(200), Resp(200, {"serverTime": 7})])
    assert c.server_time_ms() == 7 and sl == [2]


def test_jitter_is_additive_and_bounded_and_default_off():
    c, sl = _client([ConnectionError("x"), Resp(503), Resp(200, {"ok": 1})], jitter=lambda: 1.0)
    assert c.get("/x") == {"ok": 1}
    assert sl == [2 * 1.25, 4 * 1.25]                       # asla kisalmaz, en fazla %25 uzar
    c2, sl2 = _client([ConnectionError("x"), Resp(200, {"ok": 1})])
    c2.get("/x")
    assert sl2 == [2]                                        # jitter verilmezse deterministik


# ----------------------------------------------------------------------------- acilis
def _forever(e, rng=lambda: 0.5):
    cfg = dataclasses.replace(e.cfg, startup_retry_forever=True)
    e.feed = Feed(cfg, e.rest, e.store, e.clock, rng=rng)
    return e


def _fail_first(path_part, n, status=503):
    cnt = [0]

    def inj(path, p):
        if path_part in path:
            cnt[0] += 1
            if cnt[0] <= n:
                return Resp(status, {"msg": "down"})
        return None
    return inj, cnt


def test_startup_forever_survives_long_outage_with_capped_exponential_backoff(tmp_path):
    e = _forever(make_env(tmp_path, T_START, pairs=(BTC,), max_attempts=1))
    inj, cnt = _fail_first("/fapi/v1/time", 25)              # 25 ardisik hata (eski sinirli kod ~4 denemede cikardi)
    e.srv.inject.append(inj)
    t0 = e.clock.now()
    e.feed.start()
    assert e.feed._started and e.store.last_open_ms("last", BTC, "1m") is not None
    waited = (e.clock.now() - t0).total_seconds()
    assert waited > 25 * 2.5                                  # gercekten bekledi
    assert all(w <= e.cfg.startup_backoff_cap_s for w in [e.feed._startup_delay_s(n) for n in range(40)])
    assert e.feed._startup_delay_s(0) == 5.0 * 0.75 and e.feed._startup_delay_s(39) == 300.0 * 0.75


def test_startup_forever_rules_network_errors_do_not_consume_attempts(tmp_path):
    e = _forever(make_env(tmp_path, T_START, pairs=(BTC,), max_attempts=1))
    inj, _ = _fail_first("/fapi/v1/exchangeInfo", 12)
    e.srv.inject.append(inj)
    e.feed.start()
    assert e.store.get_rules(BTC) is not None


def test_startup_forever_bad_json_on_time_endpoint_retries(tmp_path):
    e = _forever(make_env(tmp_path, T_START, pairs=(BTC,), max_attempts=1))
    n = [0]

    def inj(path, p):
        if path == "/fapi/v1/time":
            n[0] += 1
            if n[0] <= 3:
                return _BadJson(200)
        return None
    e.srv.inject.append(inj)
    e.feed.start()
    assert e.feed._started and n[0] == 4


def test_startup_forever_missing_pair_is_config_error_still_bounded(tmp_path):
    e = _forever(make_env(tmp_path, T_START, pairs=(BTC, "SOL/USDT"), max_attempts=1))
    with pytest.raises(F.RulesFetchError):
        e.feed.start()


@pytest.mark.parametrize("code", [418, 451])
def test_startup_forever_never_retries_ban_or_geoblock(tmp_path, code):
    e = _forever(make_env(tmp_path, T_START, pairs=(BTC,), max_attempts=1))
    e.srv.inject.append(lambda path, p: Resp(code, {"msg": "x"}, {"Retry-After": "60"}) if path == "/fapi/v1/time" else None)
    t0 = e.clock.now()
    with pytest.raises(ExchangeBan):
        e.feed.start()
    assert e.clock.now() == t0 and len([c for c in e.srv.calls if c[0] == "/fapi/v1/time"]) == 1


def test_main_startup_retry_flag_forever_vs_bounded(tmp_path):
    import json
    from test_feed_entrypoints import _cfg_dir, _rest, _Session
    from trader_engine.clock import SimClock
    d = _cfg_dir(tmp_path)
    clock = SimClock(T_START)
    sess = _Session(to_ms(T_START))
    state = {"n": 0}
    orig = sess.get

    def flaky(url, params=None, timeout=None):
        if url.endswith("/fapi/v1/exchangeInfo"):
            state["n"] += 1
            if state["n"] <= 30:                              # 30 x 2 deneme: sinirli mod bunu asla asamazdi
                return type(sess.get(url.replace("exchangeInfo", "time"))).__call__(
                    type(sess.get(url.replace("exchangeInfo", "time"))), 503, None, "x")
        return orig(url, params, timeout)
    sess.get = flaky
    rc = F.main(["--config-dir", str(d), "--startup-retry", "forever"], rest=_rest(sess, clock), clock=clock, max_ticks=1)
    assert rc == 0 and state["n"] > 30
    assert json.loads((tmp_path / "var" / "feed-status.json").read_text())["schema"]


# ----------------------------------------------------------------------------- ban ust siniri
def _ban_env(tmp_path, retry_after):
    e = make_env(tmp_path, T_START, pairs=(BTC,))
    e.feed.start()
    e.srv.inject.append(lambda path, p: Resp(418, {}, {"Retry-After": str(retry_after)}) if "klines" in path.lower() else None)
    e.clock.set_time(dt(2026, 12, 1, 9, 0, 3))
    return e


def test_ban_wait_at_cap_sleeps_full_hour_and_survives(tmp_path):
    e = _ban_env(tmp_path, 3600)
    t0 = e.clock.now()
    e.feed.run_once()
    assert (e.clock.now() - t0).total_seconds() >= 3600


def test_ban_wait_above_cap_exits_3_without_sleeping(tmp_path):
    e = _ban_env(tmp_path, 3601)
    t0 = e.clock.now()
    with pytest.raises(SystemExit) as ei:
        e.feed.run_once()
    assert ei.value.code == F.EXIT_BAN == 3
    assert e.clock.now() == t0                               # yasak uzatilmaz: uyumadan cikis


def test_unit_file_blocks_restart_on_3_and_6():
    from pathlib import Path
    u = (Path(__file__).resolve().parents[2] / "deploy" / "trader-feed.service").read_text(encoding="utf-8")
    assert "RestartPreventExitStatus=3 6" in u and "--startup-retry forever" in u


# ----------------------------------------------------------------------------- bosluk doldurma (O12)
def _contiguous(e, pair, tf, kind, upto_open):
    bars = e.store.query_range(kind, pair, tf, 0, 10**15)
    opens = [to_ms(b.open_ts) for b in bars]
    step = {"1m": 60_000, "15m": 900_000, "1h": 3_600_000, "4h": 14_400_000}[tf]
    return opens and opens[-1] == upto_open and opens == [opens[0] + step * i for i in range(len(opens))]


def _tick(e, seconds=2.1):
    e.clock.advance(seconds)
    e.srv  # noqa: B018
    return e.feed.run_once()


def test_outage_longer_than_five_minutes_is_healed_while_running(tmp_path):
    e = make_env(tmp_path, dt(2026, 12, 1, 8, 0, 30), pairs=(BTC,))
    e.feed.start()
    e.clock.set_time(dt(2026, 12, 1, 8, 59, 30))             # 1 saat kopma; servis YENIDEN BASLAMADI
    e.feed.run_once()
    n_before = len(e.srv.calls)
    for _ in range(40):
        _tick(e)
    last = e.store.last_open_ms("last", BTC, "1m")
    assert last >= to_ms(dt(2026, 12, 1, 8, 58))
    assert _contiguous(e, BTC, "1m", "last", last)
    assert _contiguous(e, BTC, "1m", "mark", e.store.last_open_ms("mark", BTC, "1m"))
    assert e.store.gaps_in(BTC, "1m", 0, 10**15) == []
    assert e.feed.stats()["conflicts"] == 0
    assert len(e.srv.calls) > n_before


def test_multi_tf_outage_healed_and_requests_bounded_and_paced(tmp_path):
    e = make_env(tmp_path, dt(2026, 12, 1, 0, 0, 30), pairs=(BTC,), backfill={"1m": 4000, "15m": 400, "1h": 100, "4h": 50})
    e.feed.start()
    e.clock.set_time(dt(2026, 12, 1, 11, 0, 30))             # 11 saat kopma
    n0 = len(e.srv.calls)
    times = []
    orig = e.srv.get

    def spy(url, params=None, timeout=None):
        if "klines" in url.lower() and (params or {}).get("limit") == e.cfg.heal_page_bars:
            times.append(e.clock.now())
        return orig(url, params, timeout)
    e.srv.get = spy
    e.feed.run_once()
    for _ in range(200):
        _tick(e)
    for tf, step in (("1m", 60_000), ("15m", 900_000), ("1h", 3_600_000)):
        last = e.store.last_open_ms("last", BTC, tf)
        assert _contiguous(e, BTC, tf, "last", last), tf
        assert last >= to_ms(e.clock.now()) // step * step - 2 * step, tf
    kl = [c for c in e.srv.calls[n0:] if "klines" in c[0].lower()]
    assert all(c[1].get("limit") in (e.cfg.heal_page_bars, 5, 2) for c in kl), "her istek sinirli (sayfa/5/2)"
    assert len(times) > 3 and len(times) < 60
    assert all((b - a).total_seconds() >= e.cfg.heal_min_interval_s for a, b in zip(times, times[1:])), "doldurma hizlanmadi"
    assert e.feed.rest.used_weight() < 1800


def test_no_heal_requests_in_steady_state(tmp_path):
    e = make_env(tmp_path, T_START, pairs=(BTC,))
    e.feed.start()
    n0 = len(e.srv.calls)
    for _ in range(200):
        _tick(e, 1.0)
    new = e.srv.calls[n0:]
    assert not [c for c in new if "klines" in c[0].lower() and c[1].get("limit", 0) > 5]


def test_heal_backs_off_when_exchange_keeps_failing(tmp_path):
    e = make_env(tmp_path, dt(2026, 12, 1, 8, 0, 30), pairs=(BTC,))
    e.feed.start()
    e.clock.set_time(dt(2026, 12, 1, 8, 59, 30))
    e.srv.inject.append(lambda path, p: Resp(503, {}) if "klines" in path.lower() and p.get("limit", 0) > 5 else None)
    e.feed.run_once()
    for _ in range(100):
        _tick(e, 1.0)
    heal_calls = [c for c in e.srv.calls if "klines" in c[0].lower() and c[1].get("limit") == e.cfg.heal_page_bars]
    assert heal_calls
    per_series = {}
    for c in heal_calls:
        per_series[(c[0], c[1]["interval"])] = per_series.get((c[0], c[1]["interval"]), 0) + 1
    # max_attempts=2 istek/deneme; ustel bekleme (30,60,120..) -> ~100 sn'de seri basina en fazla birkac deneme
    assert max(per_series.values()) <= 2 * 10


def test_heal_ban_propagates_to_ban_handling(tmp_path):
    e = make_env(tmp_path, dt(2026, 12, 1, 8, 0, 30), pairs=(BTC,))
    e.feed.start()
    e.clock.set_time(dt(2026, 12, 1, 8, 59, 30))
    e.srv.inject.append(lambda path, p: Resp(418, {}, {"Retry-After": "30"}) if "klines" in path.lower() else None)
    t0 = e.clock.now()
    tick = e.feed.run_once()
    assert tick.banned and (e.clock.now() - t0).total_seconds() >= 30


# ----------------------------------------------------------------------------- bozuk mum (h<l)
@pytest.mark.parametrize("hover", [-1000.0, -5.0])     # -1000: h<=0 (bad_values, rows_to_bars); -5: h<l (store dogrulamasi)
def test_corrupt_candle_records_abnormal_close_and_no_request_storm(tmp_path, hover):
    e = make_env(tmp_path, T_START, pairs=(BTC,))
    e.feed.start()
    bad = to_ms(dt(2026, 12, 1, 9, 0))
    e.srv.hover[("BTCUSDT", "1m", bad)] = hover
    e.clock.set_time(dt(2026, 12, 1, 9, 1, 3))
    n0 = len([c for c in e.srv.calls if c[0] == "/fapi/v1/klines" and c[1].get("interval") == "1m"])
    for _ in range(40):                                       # 40 sn, 1 sn'lik turlar; ayni dakika icinde
        e.clock.advance(1.0)
        e.feed.run_once()
        if e.clock.now() >= dt(2026, 12, 1, 9, 1, 50):
            break
    n1 = len([c for c in e.srv.calls if c[0] == "/fapi/v1/klines" and c[1].get("interval") == "1m"])
    assert n1 - n0 <= 1, f"bozuk mum yuzunden istek firtinasi: {n1 - n0}"
    assert (bad, "abnormal_close") in e.store.gaps_in(BTC, "1m", 0, 10**15)
    assert e.store.last_open_ms("last", BTC, "1m") == to_ms(dt(2026, 12, 1, 8, 59))   # bozuk 09:00 mumu yazilmadi, uydurulmadi


def test_after_corrupt_candle_feed_continues_with_next_minute(tmp_path):
    e = make_env(tmp_path, T_START, pairs=(BTC,))
    e.feed.start()
    bad = to_ms(dt(2026, 12, 1, 9, 0))
    e.srv.hover[("BTCUSDT", "1m", bad)] = -1000.0
    for sec in range(0, 200):
        e.clock.set_time(dt(2026, 12, 1, 9, 0, 3) + timedelta(seconds=sec))
        e.feed.run_once()
    assert e.store.last_open_ms("last", BTC, "1m") == to_ms(dt(2026, 12, 1, 9, 2))
    gaps = e.store.gaps_in(BTC, "1m", 0, 10**15)
    assert (bad, "abnormal_close") in gaps


@pytest.mark.parametrize("hover", [-1000.0, -5.0])
def test_corrupt_tf_candle_no_retry_storm_and_gap_recorded(tmp_path, hover):
    e = make_env(tmp_path, dt(2026, 12, 1, 8, 59, 30), pairs=(BTC,))
    e.feed.start()
    bad = to_ms(dt(2026, 12, 1, 8, 45))                      # 15m mumu 09:00 sinirinda kapanir
    e.srv.hover[("BTCUSDT", "15m", bad)] = hover
    e.clock.set_time(dt(2026, 12, 1, 9, 0, 3))
    n0 = len(e.srv.kline_calls("15m"))
    for sec in range(40):
        e.clock.set_time(dt(2026, 12, 1, 9, 0, 3) + timedelta(seconds=sec))
        e.feed.run_once()
    assert len(e.srv.kline_calls("15m")) - n0 <= 1
    assert (bad, "abnormal_close") in e.store.gaps_in(BTC, "15m", 0, 10**15)


# ----------------------------------------------------------------------------- mentor RED duzeltmeleri
def _holes(e, tf, kind, step):
    rows = [r[0] for r in raw(e.db, "SELECT open_ms FROM bars WHERE kind=? AND pair=? AND tf=? ORDER BY open_ms", (kind, BTC, tf))]
    return [(a, b) for a, b in zip(rows, rows[1:]) if b - a != step]


@pytest.mark.parametrize("outage_min", [7, 20, 60])
def test_real_outage_503_on_all_paths_leaves_no_holes(tmp_path, outage_min):
    e = make_env(tmp_path, dt(2026, 12, 1, 8, 0, 30), pairs=(BTC,), backfill={"1m": 2000, "15m": 100, "1h": 50, "4h": 20})
    e.feed.start()
    down = [True]
    e.srv.inject.append(lambda path, p: Resp(503, {}) if down[0] else None)
    end = e.clock.now() + timedelta(minutes=outage_min)
    while e.clock.now() < end:
        e.clock.advance(1.0)
        e.feed.run_once()
    down[0] = False
    for _ in range(1500):
        e.clock.advance(1.0)
        e.feed.run_once()
    for tf, kind, step in (("1m", "last", 60_000), ("1m", "mark", 60_000), ("15m", "last", 900_000)):
        assert _holes(e, tf, kind, step) == [], (outage_min, tf, kind)
        last = e.store.last_open_ms(kind, BTC, tf)
        assert last >= to_ms(e.clock.now()) // step * step - 2 * step
    assert e.feed.stats()["conflicts"] == 0


def test_network_errors_do_not_count_toward_heal_giveup_and_recover_fast(tmp_path):
    e = make_env(tmp_path, dt(2026, 12, 1, 8, 0, 30), pairs=(BTC,), backfill={"1m": 2000, "15m": 100, "1h": 50, "4h": 20})
    e.feed.start()
    e.clock.set_time(dt(2026, 12, 1, 8, 59, 30))
    down = [True]
    e.srv.inject.append(lambda path, p: Resp(503, {}) if down[0] else None)
    for _ in range(600):
        e.clock.advance(1.0)
        e.feed.run_once()
    assert not e.feed._heal_fail                              # ag hatalari strike sayilmaz
    assert all(v <= 60_000 + e.clock.now().timestamp() * 1000 for v in e.feed._heal_net_at.values())
    down[0] = False
    t0 = e.clock.now()
    for _ in range(90):                                       # <= ~tavan(60 sn)+pay icinde toparlanir
        e.clock.advance(1.0)
        e.feed.run_once()
    assert e.store.last_open_ms("last", BTC, "1m") >= to_ms(dt(2026, 12, 1, 9, 9))
    assert _holes(e, "1m", "last", 60_000) == []
    assert (e.clock.now() - t0).total_seconds() == 90


def test_empty_heal_response_records_whole_range_as_missing_before_unblocking(tmp_path):
    e = make_env(tmp_path, dt(2026, 12, 1, 8, 0, 30), pairs=(BTC,))
    e.feed.start()
    old_last = e.store.last_open_ms("last", BTC, "1m")
    e.clock.set_time(dt(2026, 12, 1, 8, 59, 30))
    e.srv.inject.append(lambda path, p: Resp(200, []) if path == "/fapi/v1/klines" and p.get("interval") == "1m"
                        and p.get("limit") == e.cfg.heal_page_bars else None)
    for _ in range(400):
        e.clock.advance(1.0)
        e.feed.run_once()
    gaps = {o for o, r in e.store.gaps_in(BTC, "1m", 0, 10**15) if r == "missing"}
    hole = _holes(e, "1m", "last", 60_000)
    assert hole, "normal cekim deligi atladi (bos cevap)"
    for a, b in hole:
        assert set(range(a + 60_000, b, 60_000)) <= gaps, "atlanan her dakika 'missing' kayitli olmali"
    assert old_last + 60_000 in gaps


def test_corrupt_heal_response_records_range_missing(tmp_path):
    e = make_env(tmp_path, dt(2026, 12, 1, 8, 0, 30), pairs=(BTC,))
    e.feed.start()
    old_last = e.store.last_open_ms("last", BTC, "1m")
    for k in range(1, 40):                                    # bozuk (h<l) mumlar: store reddeder, ilerleme yok
        e.srv.hover[("BTCUSDT", "1m", old_last + 60_000 * k)] = -5.0
    e.clock.set_time(dt(2026, 12, 1, 8, 20, 30))
    for _ in range(400):
        e.clock.advance(1.0)
        e.feed.run_once()
    gaps = {o for o, r in e.store.gaps_in(BTC, "1m", 0, 10**15) if r in ("missing", "abnormal_close")}
    for k in range(1, 20):
        assert old_last + 60_000 * k in gaps


def test_startup_consecutive_429_exits_3(tmp_path):
    e = _forever(make_env(tmp_path, T_START, pairs=(BTC,), max_attempts=10))
    # Retry-After 200: istemcinin toplam bekleme tavani (300 sn) 2. denemede asilir -> ExchangeBan(429)
    e.srv.inject.append(lambda path, p: Resp(429, {}, {"Retry-After": "200"}) if path == "/fapi/v1/time" else None)
    t0 = e.clock.now()
    with pytest.raises(SystemExit) as ei:
        e.feed.start()
    assert ei.value.code == F.EXIT_BAN
    assert (e.clock.now() - t0).total_seconds() >= (F.MAX_CONSEC_BANS - 1) * 200


def test_418_without_retry_after_sleeps_at_least_120_plus_margin(tmp_path):
    e = make_env(tmp_path, T_START, pairs=(BTC,))
    e.feed.start()
    e.srv.inject.append(lambda path, p: Resp(418, {}) if "klines" in path.lower() else None)
    e.clock.set_time(dt(2026, 12, 1, 9, 0, 3))
    t0 = e.clock.now()
    e.feed.run_once()
    assert (e.clock.now() - t0).total_seconds() >= 120 + F.BAN_MARGIN_S


def test_used_weight_is_zero_when_measurement_stale():
    t = [1000.0]
    c = PublicRestClient(session=_Sess([Resp(200, {"a": 1}, {"X-MBX-USED-WEIGHT-1M": "1500"})]), now_s=lambda: t[0], sleep=lambda s: None)
    c.get("/x")
    assert c.used_weight() == 1500
    t[0] += 61
    assert c.used_weight() == 0


def test_gap_deeper_than_backfill_bars_is_recorded_missing_and_warned(tmp_path, caplog):
    import logging
    e = make_env(tmp_path, dt(2026, 12, 1, 8, 0, 30), pairs=(BTC,), backfill={"1m": 30, "15m": 8, "1h": 6, "4h": 4})
    e.feed.start()
    old_last = e.store.last_open_ms("last", BTC, "1m")
    e.clock.set_time(dt(2026, 12, 1, 10, 0, 30))             # 2 saat > 30 bar
    with caplog.at_level(logging.WARNING):
        for _ in range(60):
            e.clock.advance(2.1)
            e.feed.run_once()
    assert any("derin" in r.getMessage() for r in caplog.records)
    gaps = {o for o, r in e.store.gaps_in(BTC, "1m", 0, 10**15) if r == "missing"}
    for a, b in _holes(e, "1m", "last", 60_000):
        assert set(range(a + 60_000, b, 60_000)) <= gaps
    assert old_last + 60_000 in gaps
