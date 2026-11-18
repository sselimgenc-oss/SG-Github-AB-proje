"""DD-6 (canli dongu ve giris kapisi): O1, O3, D1, D11, D17. Yalniz sahteler (FakeExchange, SimClock, sentetik gorunum); ag yok.

Duzenek test_engine_live_spec.LiveEnv / test_b45_kill_multi.LiveEnv2'dir (dosyalarina dokunulmaz).
"""
from __future__ import annotations

from datetime import timedelta
from pathlib import Path

import numpy as np
import pytest

import test_engine_live_spec as T
from test_b45_kill_multi import DOGE, DSYM, LiveEnv2
from test_engine_05_spec import make_frame
from trader_engine.engine import EngineExit
from trader_engine.errors import DataError
from trader_engine.order_manager import make_client_id
from trader_engine.position_manager import ExitContext
from trader_engine.types import OrderResult

REAL_STARTUP_GATE = True       # tests/conftest.py: acilis kapisi bu modulde gercekten calisir


class DataErrFeed(T.FeedView):
    """`err=True` iken her okuma DataError verir (market.sqlite okuma hatasi benzetimi)."""
    err = False

    def _chk(self):
        if self.err:
            raise DataError("market.sqlite okunamadi (sahte)")

    def minute_steps(self, pairs, start, end):
        self._chk()
        return super().minute_steps(pairs, start, end)

    def last_closed_minute(self, pair):
        self._chk()
        return super().last_closed_minute(pair)

    def data_range(self, pair, tf):
        self._chk()
        return super().data_range(pair, tf)


def _kill(e):
    Path(e.cfg.kill_file).parent.mkdir(parents=True, exist_ok=True)
    Path(e.cfg.kill_file).write_text("{}")


def _env(tmp_path, cls=T.LiveEnv):
    e = cls(tmp_path)
    e.view = DataErrFeed(e.cfg.pairs, T.DEC - timedelta(days=3), T.DEC + timedelta(days=4), mode="flat", base=2.0,
                         clock=e.clock)
    e.engine.view = e.view
    return e.boot()


# ============================================================================================ O1
def test_dd6_o1_data_error_does_not_exit_and_kill_still_closes(tmp_path):
    e = _env(tmp_path)
    try:
        pos = e.enter()
        assert pos is not None and pos.status == "open"
        e.view.err = True
        _kill(e)
        e.tick(6)                                    # DataError tum okumalarda; live_tick cikmaz
        assert e.engine.counters()["advance_errors"] >= 1
        assert len(e.posted("x")) == 1, "KILL cikisi ilk turda gitmeli"
        e.tick(6)
        e.tick(6)
        assert e.ex_qty() == 0
    finally:
        e.close()


def test_dd6_o1_backoff_then_entries_closed_after_n_errors_then_recovers(tmp_path):
    e = _env(tmp_path)
    try:
        e.enter()                                    # imlecler kurulsun: advance_to gorunume dokunur
        e.view.err = True
        n_ticks = 0
        for _ in range(3):
            e.tick(1)                                # 1 sn adimlar: geri cekilme yuzunden her tur advance denemez
            n_ticks += 1
        errs = e.engine.counters()["advance_errors"]
        assert 1 <= errs < n_ticks + 1 and errs <= 2, errs
        assert e.kv("entries_blocked_reason") is None
        for _ in range(12):
            e.tick(35)                               # her tur geri cekilme penceresini asar
        assert e.engine.counters()["advance_errors"] >= 5
        assert e.kv("entries_blocked_reason") == "engine_errors"
        e.view.err = False
        e.tick(35)
        assert e.engine._adv_errors == 0 and e.engine._adv_next_try is None
    finally:
        e.close()


def test_dd6_o1_startup_gate_honours_kill_while_waiting(tmp_path):
    e = _env(tmp_path)
    try:
        pos = e.enter()
        assert pos is not None and pos.status == "open"
        e.view.dead = True                           # taze veri yok: kapi bekler
        _kill(e)
        with pytest.raises(EngineExit):
            e.engine._startup_gate()                 # bekleme suresi dolunca EngineExit(7)
        assert len(e.posted("x")) == 1 and e.ex_qty() == 0, "KILL kapi beklerken islenmeli"
    finally:
        e.close()


# ============================================================================================ O3
def _rej(call, req):
    return OrderResult("rejected", req.client_id, reason="filter:-1111")


def test_dd6_o3_second_pair_skipped_after_first_stop_failed_same_step(tmp_path):
    e = LiveEnv2(tmp_path).boot()
    try:
        e.broker.hooks["place_stop"] = [_rej, _rej]          # ilk cift: stop/0 ve stop/1 reddedilir
        e.enter_both()
        assert len(e.posted("e")) == 1, "aralarinda kapi kapanmali: tek giris emri"
        assert e.state.position_for_pair(DOGE) is None and e.amt(DSYM) == 0
        assert e.kv("entries_blocked_reason") == "stop_failed"
        assert e.engine.gate.counters["skip:stop_failed"] == 1, "ikinci cift gate:stop_failed ile atlanmali"
        assert list(e.state.kv_get("stop_failed_log")) == ["1"]
        assert not e.engine.pause.active(), "tek stop_failed kalici duraklatma uretmez"
    finally:
        e.close()


def test_dd6_o3_second_stop_failed_within_24h_pauses_permanently(tmp_path):
    e = T.LiveEnv(tmp_path).boot()
    try:
        e.engine._note_stop_failed(1)
        e.engine._note_stop_failed(1)                        # ayni pozisyon: tek olay
        assert not e.engine.pause.active()
        e.engine._note_stop_failed(2)
        assert e.engine.pause.active()
        assert [h.reason for h in e.engine.pause.holds()] == ["stop_failed_repeat"]
        assert e.engine.gate.pre(T.DEC, "1h", True, "1h").code == "paused"
    finally:
        e.close()


def test_dd6_o3_second_stop_failed_after_24h_does_not_pause(tmp_path):
    e = T.LiveEnv(tmp_path).boot()
    try:
        e.engine._note_stop_failed(1)
        e.clock.advance(25 * 3600)
        e.engine._note_stop_failed(2)
        assert not e.engine.pause.active()
        assert list(e.state.kv_get("stop_failed_log")) == ["2"]
    finally:
        e.close()


def test_dd6_o3_stop_failed_still_auto_clears_but_pause_stays(tmp_path):
    from trader_engine.reconcile import _AUTO_CLEAR
    assert "stop_failed" in _AUTO_CLEAR                      # blokaj kendiliginden kalkar; kalici tutus ayri ve kalir
    e = T.LiveEnv(tmp_path).boot()
    try:
        e.engine._note_stop_failed(1)
        e.engine._note_stop_failed(2)
        e.engine._block("stop_failed")
        e.tick(31)
        e.tick(31)
        assert e.kv("entries_blocked_reason") is None
        assert e.engine.pause.active(), "mutabakat EntryPause tutuslarini asla kaldirmaz"
    finally:
        e.close()


# ============================================================================================ D1
def test_dd6_d1_watchdog_protects_opening_position_filled_after_uncertain_entry(tmp_path):
    e = T.LiveEnv(tmp_path).boot()
    try:
        e.wire.on(T.entry_post, before=T.raising(TimeoutError("x")))
        e.signal(T.DEC)
        e.decide()
        p = e.state.get_position(1)
        assert p.status == "opening" and not e.stops()
        row = e.state.orders_for_trade(1)[0]
        e.ex.fill_market(T.SYM, "BUY", str(row.qty), cid=row.client_id)   # kendi giris emri sonradan doldu
        e.clock.advance(1)
        e.engine._stop_watchdog(e.clock.now())               # mutabakat turu BEKLENMEDEN
        cur = e.state.get_position(1)
        assert cur.status == "open" and len(e.stops()) == 1
        assert e.engine.counters()["opening_protect"] == 1
    finally:
        e.close()


def test_dd6_d1_watchdog_ignores_opening_when_exchange_flat(tmp_path):
    e = T.LiveEnv(tmp_path).boot()
    try:
        e.wire.on(T.entry_post, before=T.raising(TimeoutError("x")))
        e.signal(T.DEC)
        e.decide()
        e.clock.advance(1)
        e.engine._stop_watchdog(e.clock.now())
        assert e.engine.counters().get("opening_protect", 0) == 0
        assert not e.stops()
    finally:
        e.close()


# ============================================================================================ D11
def _failing_frames(e, fail_times):
    real = e.src.frame
    calls = {"n": 0}

    def frame(pair, D, params, vid):
        calls["n"] += 1
        if calls["n"] <= fail_times:
            raise RuntimeError("frame hatasi (sahte)")
        return real(pair, D, params, vid)
    e.src.frame = frame
    return calls


def _exit_ctx(D):
    return ExitContext(bar_close_ts=D, highs=np.array([2.02]), lows=np.array([1.85]), atrs=np.array([0.02]),
                       regime_last="trend_down", last_close=1.86, n_closed=1)


def test_dd6_d11_failed_decision_step_retries_software_exit_for_same_bar(tmp_path):
    e = _env(tmp_path)
    try:
        pos = e.enter()
        assert pos.status == "open"
        e.view.dead = True
        D2 = T.DEC + timedelta(hours=1)
        e.src.frames[(T.XRP, D2)] = make_frame(T.XRP, D2, version=e.version_id, entry=2.0, stop=1.9, atr_tf=0.05,
                                               atr_4h=0.1, stop_dist_atr=2.0)
        e.src.ctx[(T.XRP, D2)] = _exit_ctx(D2)
        _failing_frames(e, 1)                                # karar adiminin frame'i bir kez patlar
        e.clock.set_time(D2 + timedelta(seconds=5))
        e.engine.decision_step(D2)
        assert not e.posted("x") and e.engine.counters()["decision_failures"] == 1
        e.tick(6)                                            # yeniden deneme
        assert len(e.posted("x")) == 1, "ayni barin yazilim cikisi yeniden denemede gitmeli"
        assert e.engine._exit_retry is None
    finally:
        e.close()


def test_dd6_d11_retry_is_bounded(tmp_path):
    e = _env(tmp_path)
    try:
        e.enter()
        e.view.dead = True
        D2 = T.DEC + timedelta(hours=1)
        calls = _failing_frames(e, 10_000)
        e.clock.set_time(D2 + timedelta(seconds=5))
        e.engine.decision_step(D2)
        for _ in range(12):
            e.tick(40)
        assert e.engine._exit_retry is None
        assert calls["n"] == 1 + 3 * 1, calls                # 1 karar adimi + 3 deneme (tek cift)
        assert not e.posted("x")
    finally:
        e.close()


# ============================================================================================ D17
def test_dd6_d17_testnet_divergence_skips_entry(tmp_path):
    e = T.LiveEnv(tmp_path).boot()
    try:
        e.broker.book_ticker = lambda pair: (2.019, 2.021)   # ~%1 sapma (planned_entry 2.0)
        e.signal(T.DEC)
        e.decide()
        assert e.pos() is None and not e.posted("e")
        assert e.engine.counters()["testnet_price_divergence"] == 1
        assert e.state.is_decided(T.XRP, T.DEC)
    finally:
        e.close()


def test_dd6_d17_testnet_within_threshold_enters(tmp_path):
    e = T.LiveEnv(tmp_path).boot()
    try:
        e.broker.book_ticker = lambda pair: (2.004, 2.006)   # %0,25
        e.signal(T.DEC)
        e.decide()
        assert e.pos() is not None and len(e.posted("e")) == 1
        assert e.engine.counters().get("testnet_price_divergence", 0) == 0
    finally:
        e.close()


def test_dd6_d17_price_unreadable_does_not_block_entry(tmp_path):
    e = T.LiveEnv(tmp_path).boot()
    try:
        def boom(pair):
            raise DataError("ticker yok")
        e.broker.book_ticker = boom
        e.signal(T.DEC)
        e.decide()
        assert e.pos() is not None
        assert e.engine.counters()["testnet_price_unchecked"] == 1
    finally:
        e.close()


# ============================================================================================ mentor duzeltmeleri
def test_dd6_d1_throttle_applies_to_attempts_without_hit(tmp_path):
    e = T.LiveEnv(tmp_path).boot()
    try:
        e.wire.on(T.entry_post, before=T.raising(TimeoutError("x")))
        e.signal(T.DEC)
        e.decide()
        calls = {"n": 0}
        real = e.broker.positions

        def counting():
            calls["n"] += 1
            return real()
        e.broker.positions = counting
        e.clock.advance(1)
        e.engine._stop_watchdog(e.clock.now())
        e.clock.advance(1)
        e.engine._stop_watchdog(e.clock.now())               # 5 sn icinde: okuma yok
        assert calls["n"] == 1
        e.clock.advance(5)
        e.engine._stop_watchdog(e.clock.now())
        assert calls["n"] == 2
    finally:
        e.close()


def _would_trigger(call, req):
    return OrderResult("rejected", req.client_id, reason="would_trigger")


def test_dd6_o3_would_trigger_in_stop_deadline_path_is_not_counted(tmp_path):
    e = T.LiveEnv(tmp_path).boot()
    try:
        e.broker.hooks["place_stop"] = [_would_trigger]
        pos = e.enter()
        assert e.ex_qty() == 0, "would_trigger: piyasada kapatilmis olmali"
        assert e.state.kv_get("stop_failed_log") is None
        assert not e.engine.pause.active()
    finally:
        e.close()


def test_dd6_o3_would_trigger_in_reconcile_live_path_is_not_counted(tmp_path):
    e = T.LiveEnv(tmp_path).boot()
    try:
        pos = e.enter()
        assert pos.status == "open"
        e.ex.algos.clear()                                   # stop borsadan silindi
        e.ex.set_mark(T.SYM, "1.8")                          # yeni stop (1.9) hemen tetiklenirdi: -2021
        e.tick(16)
        e.tick(16)
        assert e.ex_qty() == 0, "L5 would_trigger: piyasada kapanmali"
        assert e.state.kv_get("stop_failed_log") is None
        assert not e.engine.pause.active()
    finally:
        e.close()
