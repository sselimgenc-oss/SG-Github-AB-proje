"""WP-B4 gerceklestirme duman testleri (11 §6): canli motor yolu. Duzenek bagimsiz test dosyasindan (LiveEnv: gercek LiveBroker +
SignedRestClient + FakeExchange) alinir; bagimsiz sartname testleri: test_engine_live_spec.py."""
from __future__ import annotations

from datetime import timedelta
from decimal import Decimal

from fake_exchange import FakeResp
from test_engine_live_spec import DEC, SYM, XRP, LiveEnv


def _stop_row(env, seq=0):
    from trader_engine.order_manager import make_client_id
    return env.state.get_order(make_client_id("learner", "stop", XRP, "long", DEC, seq))


def test_smoke_no_outer_tx_and_entry_to_stop_same_call(tmp_path):
    e = LiveEnv(tmp_path).boot()
    try:
        pos = e.enter()
        assert pos.status == "open" and [a["triggerPrice"] for a in e.stops()] == [Decimal("1.9")]
        assert e.wire.writes() and all(w.in_tx is False and w.cid_committed for w in e.wire.writes())
    finally:
        e.close()


def test_smoke_leverage_4_end_to_end(tmp_path):
    e = LiveEnv(tmp_path, leverage=4).boot()
    try:
        assert e.ex.lev[SYM] == 4 and e.ex.margin_type[SYM] == "isolated"
        pos = e.enter()
        assert pos.leverage == 4
    finally:
        e.close()


def test_smoke_stop_retry_within_deadline_then_ok(tmp_path):
    e = LiveEnv(tmp_path).boot()
    try:
        e.ex.inject("/fapi/v1/algoOrder", FakeResp(400, {"code": -1111, "msg": "x"}))
        pos = e.enter()
        assert pos.status == "open" and len(e.stops()) == 1
        assert _stop_row(e, 0).status == "rejected" and _stop_row(e, 1).status == "accepted"
    finally:
        e.close()


def test_smoke_two_stop_rejects_close_and_block(tmp_path):
    e = LiveEnv(tmp_path).boot()
    try:
        for _ in range(2):
            e.ex.inject("/fapi/v1/algoOrder", FakeResp(400, {"code": -1111, "msg": "x"}))
        e.enter()
        assert e.ex_qty() == 0 and not e.stops()
        assert e.state.kv_get("entries_blocked_reason") == "stop_failed"
    finally:
        e.close()


def test_smoke_watchdog_boundaries_9_10_11(tmp_path):
    e = LiveEnv(tmp_path).boot()
    try:
        pos = e.enter()
        # stopsuz durum: emir satiri accepted degil (borsadaki stop de iptal)
        for a in e.ex.algos.values():
            a["algoStatus"] = "CANCELED"
        with e.state.tx():
            e.state.update_order(pos.stop_client_id, status="canceled", updated_ts=e.clock.now())
        t0 = e.clock.now() + timedelta(seconds=1)
        e.engine._last_reconcile = t0 + timedelta(hours=1)           # mutabakat stopu yeniden kurmasin
        e.tick_at(t0)
        assert e.state.kv_get(f"naked:{pos.trade_id}") is not None
        for dt, closed in ((9, False), (10, False), (11, True)):
            e.tick_at(t0 + timedelta(seconds=dt))
            assert (e.state.get_position(pos.trade_id).status != "open") is closed, dt
    finally:
        e.close()


def test_smoke_kill_runs_without_feed(tmp_path):
    e = LiveEnv(tmp_path).boot()
    try:
        pos = e.enter()
        e.view.dead = True
        e.kill.set("t", "test")
        e.tick(6)
        assert e.ex_qty() == 0 and e.state.get_position(pos.trade_id).status == "closed"
        assert e.state.get_position(pos.trade_id).exit_reason == "force_exit"
    finally:
        e.close()


def test_smoke_duplicate_exit_fill_ignored(tmp_path):
    e = LiveEnv(tmp_path).boot()
    try:
        pos = e.enter()
        e.ex.set_mark(SYM, "1.85")
        e.clock.advance(6)
        evs = [x for x in e.broker.poll(e.clock.now()) if x.kind == "fill"]
        assert evs
        e.engine._handle_events(evs, None, e.clock.now())
        assert e.state.get_position(pos.trade_id).status == "closed"
        e.engine._handle_events(evs, None, e.clock.now())
        c = e.engine.counters()
        assert c["duplicate_fill_ignored"] == 1 and c.get("unexpected_fills", 0) == 0 and c["trades_closed"] == 1
    finally:
        e.close()


def test_smoke_uncertain_entry_stays_unknown_then_fails_after_window(tmp_path):
    e = LiveEnv(tmp_path).boot()
    try:
        e.ex.inject("/fapi/v1/order", FakeResp(503, {"code": -1001, "msg": "x"}))
        e.signal(DEC)
        e.decide()
        pos = e.pos()
        assert pos.status == "opening" and e.state.kv_get("entries_blocked_reason") == "order_unknown"
        e.tick(30)
        assert e.pos().status == "opening"
        e.tick(40)
        assert e.pos() is None
        assert e.engine.counters()["unknown_orders"] == 0
    finally:
        e.close()
