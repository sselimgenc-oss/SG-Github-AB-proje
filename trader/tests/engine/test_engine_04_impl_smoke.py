"""04 gerceklemesi icin duman testleri (sahte broker; bagimsiz sartname testleri ayri)."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import numpy as np
import pytest

from trader_engine.clock import SimClock
from trader_engine.errors import BrokerUncertain, StateError
from trader_engine.order_manager import OrderManager, make_client_id
from trader_engine.position_manager import (ExitContext, apply_exit_fill, build_trade_exit, evaluate_exit,
                                            exit_reason_for_stop_fill, update_excursion)
from trader_engine.state import StateStore
from trader_engine.types import BrokerOrder, Fill, Intent, MinuteBar, OrderResult, Position, SymbolRules

T0 = datetime(2026, 12, 1, 9, tzinfo=timezone.utc)
RULES = SymbolRules("BTC/USDT", "BTCUSDT", 0.01, 0.001, 0.001, 1000.0, 5.0)


class FakeBroker:
    is_simulated = True

    def __init__(self, faults=None):
        self.faults = faults or {}      # (method, nth) -> effect
        self.calls = []
        self.orders = {}
        self.n = {}

    def prepare(self, pair, leverage):
        self.calls.append(("prepare", pair))

    def _fault(self, m):
        self.n[m] = self.n.get(m, 0) + 1
        return self.faults.get((m, self.n[m]))

    def _do(self, m, req, status):
        self.calls.append((m, req.client_id))
        f = self._fault(m)
        if f == "raise":
            raise BrokerUncertain("x")
        if req.client_id in self.orders:
            return OrderResult("rejected", req.client_id, reason="duplicate_client_id")
        if f == "rejected":
            return OrderResult("rejected", req.client_id, reason="would_trigger")
        if f != "unknown_not_executed":
            self.orders[req.client_id] = BrokerOrder(req.client_id, req.pair, req.role, req.order_side, req.qty,
                                                     req.trigger_price, req.reduce_only,
                                                     "filled" if status == "filled" else "new", 0, None, T0, T0)
        if f and f.startswith("unknown"):
            return OrderResult("unknown", req.client_id)
        return OrderResult(status, req.client_id, order_id="o" + req.client_id[-4:])

    def market_order(self, req):
        return self._do("market_order", req, "filled")

    def place_stop(self, req):
        return self._do("place_stop", req, "accepted")

    def place_target(self, req):
        return self._do("place_target", req, "accepted")

    def cancel(self, pair, cid):
        self.calls.append(("cancel", cid))

    def query(self, pair, cid):
        self.calls.append(("query", cid))
        return self.orders.get(cid)


def mkpos(**kw) -> Position:
    d = dict(trade_id=1, bot="learner", pair="BTC/USDT", side="long", setup="T1", status="open", decision_id=7,
             signal_bar_close_ts=T0, entry_ts=T0, entry_bar_open=T0, entry_price=100.02, qty=6.369, leverage=3,
             initial_stop=98.0, current_stop=98.0, stop_seq=0, stop_client_id=None, planned_target=None,
             trail_atr=3.0, param_version_id=1, trigger_tf="1h", risk_amount=14.0, margin=200.0, rh=None, rl=None,
             fee_entry=0.1, funding_paid=0.0, mfe_price=100.02, mae_price=100.02, exit_reason=None,
             exit_client_id=None, closed_ts=None)
    d.update(kw)
    return Position(**d)


@pytest.fixture
def env(tmp_path):
    st = StateStore(str(tmp_path / "s.sqlite"), bot="learner")
    clock = SimClock(T0)

    def make(faults=None, **kw):
        b = FakeBroker(faults)
        return b, OrderManager("learner", b, st, clock, lambda p: RULES, **kw)
    yield st, clock, make
    st.close()


def test_client_ids():
    assert make_client_id("learner", "entry", "BTC/USDT", "long", T0, 0) == "trLe-078ebfcdd4a5354100a0c4fe"
    assert make_client_id("learner", "stop", "BTC/USDT", "long", T0, 0) == "trLs-922b299d97c813c28fdda499"
    assert make_client_id("learner", "exit", "BTC/USDT", "long", T0, 0) == "trLx-9de262c42db2e08b0098b1c6"
    assert make_client_id("learner", "target", "BTC/USDT", "long", T0, 0) == "trLt-d6a7eb9d18daedc978d108c1"
    assert make_client_id("twin", "entry", "BTC/USDT", "long", T0, 0) == "trTe-b299042c99b76bbc1d2e36be"


def test_state_basics(tmp_path):
    p = str(tmp_path / "a.sqlite")
    st = StateStore(p, bot="learner")
    with pytest.raises(StateError):
        StateStore(p, bot="learner")                 # ikinci yazar reddedilir
    with pytest.raises(StateError):
        st.kv_set("a", 1)                            # tx disinda yazma yok
    with st.tx():
        assert st.next_trade_id() == 1 and st.next_trade_id() == 2
        st.insert_position(mkpos())
        assert st.mark_decided("BTC/USDT", T0, "x") and not st.mark_decided("BTC/USDT", T0, "y")
        st.set_cursor("BTC/USDT", "minute", T0)
        st.kv_set("k", {"a": [1, 2]})
    with pytest.raises(StateError):
        with st.tx():
            st.set_cursor("BTC/USDT", "minute", T0 - timedelta(minutes=1))
    with pytest.raises(StateError):
        with st.tx():
            st.insert_position(mkpos(trade_id=2))    # ayni cift icin ikinci canli kayit
    assert st.get_position(1) == mkpos()
    assert st.position_for_pair("BTC/USDT").trade_id == 1 and st.get_position(2) is None
    assert st.kv_get("k") == {"a": [1, 2]} and st.integrity_check()
    with pytest.raises(ValueError):
        with st.tx():
            st.update_position(1, bogus=1)
    st.close()
    st2 = StateStore(p, bot="learner")               # yeniden acilis
    assert st2.get_position(1) is not None
    st2.close()


def test_outbox_drain_idempotent(tmp_path):
    class L:
        def __init__(self):
            self.entries, self.exits = [], []

        def record_trade_entry(self, e):
            self.entries.append(e)

        def record_trade_exit(self, x):
            self.exits.append(x)
    st = StateStore(str(tmp_path / "o.sqlite"), bot="learner")
    pos = mkpos()
    from trader_engine.position_manager import build_trade_entry
    with st.tx():
        st.outbox_add("entry", 1, build_trade_entry(pos))
    led = L()
    r = st.drain_outbox(led)
    assert (r.written, r.failed) == (1, 0) and led.entries[0].entry_ts == T0
    assert st.drain_outbox(led).written == 0 and len(led.entries) == 1
    st.close()


def test_evaluate_exit_examples():
    pos = mkpos()
    hi = np.array([101, 102.5, 103.0, 102.0])
    lo = np.array([99.5, 100.5, 101.5, 100.8])
    at = np.ones(4)

    def ctx(n, lc, reg=None):
        return ExitContext(T0, hi[:n], lo[:n], at[:n], reg, lc, n)
    assert evaluate_exit(pos, ctx(1, 100.0)).kind == "none"
    d = evaluate_exit(pos, ctx(2, 101.0))
    assert d.kind == "stop_update" and d.new_stop == pytest.approx(99.5)
    assert evaluate_exit(mkpos(current_stop=100.0), ctx(4, 100.5)).kind == "none"
    d = evaluate_exit(mkpos(current_stop=100.0), ctx(4, 99.9))
    assert (d.kind, d.reason) == ("exit", "trail_stop")
    assert evaluate_exit(pos, ctx(1, 100.0, "trend_down")).reason == "regime_flip"
    assert evaluate_exit(pos, ctx(1, 100.0, "range")).kind == "none"
    assert evaluate_exit(pos, None).reason == "force_exit"
    assert evaluate_exit(mkpos(setup=None), ctx(1, 100.0)).reason == "force_exit"
    assert evaluate_exit(pos, ctx(0, 100.0)).kind == "none"
    r1 = mkpos(setup="R1", planned_target=104.0)
    h = np.array([103.0, 104.2]); z = np.ones(2)
    d = evaluate_exit(r1, ExitContext(T0, h, h - 1, z, None, 103, 2))
    assert (d.reason, d.planned_exit) == ("target", 104.0)
    big = np.full(48, 100.0)
    assert evaluate_exit(r1, ExitContext(T0, big, big - 1, big, None, 100, 48)).reason == "time_stop"
    assert evaluate_exit(r1, ExitContext(T0, big[:47], big[:47] - 1, big[:47], None, 100, 47)).kind == "none"


def test_exit_fill_excursion_and_reason():
    pos = mkpos(mfe_price=100.8, mae_price=97.9)
    assert exit_reason_for_stop_fill(pos) == "stop"
    assert exit_reason_for_stop_fill(mkpos(current_stop=100.0)) == "trail_stop"
    bar = MinuteBar("BTC/USDT", T0, 60, 100, 100.5, 97.95, 98, None, None, None, None)
    fill = Fill("c", "BTC/USDT", "exit", "sell", 6.369, 97.95, 0.3, T0, "stop")
    c = apply_exit_fill(pos, fill, bar, T0)
    assert (c.exit_reason, c.planned_exit, c.excursion_tf) == ("stop", 98.0, "1m")
    assert c.max_favorable_price == 100.8 and c.max_adverse_price == 97.9
    d = build_trade_exit(pos, c, "1m")
    assert d["exit_ts"].endswith("Z") and d["excursion_tf"] == "1m"
    p2 = update_excursion(mkpos(side="short", mfe_price=100.0, mae_price=100.0), bar)
    assert (p2.mfe_price, p2.mae_price) == (97.95, 100.5)


def test_entry_unknown_not_executed_resends_once(env):
    st, clock, make = env
    b, om = make({("market_order", 1): "unknown_not_executed"})
    it = Intent("entry", "learner", "BTC/USDT", "long", T0, "T1", 0.5, 3, 100.0, 98.0, None, "t")
    o = om.submit_entry(it, 1)
    assert o.ok and o.note == "resent_once" and o.order.attempts == 1
    assert len([c for c in b.calls if c[0] == "market_order"]) == 2
    assert len({c[1] for c in b.calls if c[0] == "market_order"}) == 1   # ayni kimlik
    with pytest.raises(ValueError):
        om.submit_entry(Intent("entry", "learner", "BTC/USDT", "long", T0, "T1", 0.5005, 3, 100.0, 98.0, None, "t"), 1)


def test_entry_unknown_executed_adopts(env):
    st, clock, make = env
    b, om = make({("market_order", 1): "unknown_executed"})
    it = Intent("entry", "learner", "BTC/USDT", "long", T0, "T1", 0.5, 3, 100.0, 98.0, None, "t")
    o = om.submit_entry(it, 1)
    assert o.ok and o.note == "adopted_after_unknown" and o.status == "filled"
    assert len([c for c in b.calls if c[0] == "market_order"]) == 1


def test_entry_failed_closes_opening_and_blocks(env):
    st, clock, make = env
    b, om = make({("market_order", 1): "unknown_not_executed", ("market_order", 2): "unknown_not_executed"})
    with st.tx():
        st.insert_position(mkpos(status="opening", entry_ts=None, entry_bar_open=None, entry_price=None, qty=None))
    it = Intent("entry", "learner", "BTC/USDT", "long", T0, "T1", 0.5, 3, 100.0, 98.0, None, "t")
    o = om.submit_entry(it, 1)
    assert not o.ok and o.status == "failed" and o.order.status == "failed"
    assert st.get_position(1).status == "closed" and st.kv_get("entries_blocked_reason") == "order_unknown"


def test_crash_recovery_pending(env):
    st, clock, make = env
    b, om = make()
    it = Intent("entry", "learner", "BTC/USDT", "long", T0, "T1", 0.5, 3, 100.0, 98.0, None, "t")
    om.submit_entry(it, 1)
    cid = make_client_id("learner", "entry", "BTC/USDT", "long", T0, 0)
    with st.tx():
        st.update_order(cid, status="pending")
    outs = om.resolve_unresolved()
    assert outs[0].note == "adopted_after_unknown" and len([c for c in b.calls if c[0] == "market_order"]) == 1


def test_replace_stop_order_and_noop(env):
    st, clock, make = env
    b, om = make()
    pos = mkpos(stop_client_id="old", stop_seq=0)
    with st.tx():
        st.insert_position(pos)
    assert om.replace_stop(pos, 97.0).note == "not_tighter"
    o = om.replace_stop(pos, 99.5)
    assert o.ok
    kinds = [c[0] for c in b.calls]
    assert kinds.index("place_stop") < kinds.index("cancel") and ("cancel", "old") in b.calls
    p = st.get_position(1)
    assert p.current_stop == 99.5 and p.stop_seq == 1 and p.stop_client_id == o.order.client_id
    again = om.replace_stop(pos, 99.5)             # ayni D: ayni kimlik -> benimse
    assert again.ok and again.note == "duplicate_adopted"


def test_replace_stop_would_trigger(env):
    st, clock, make = env
    b, om = make({("place_stop", 1): "rejected"})
    pos = mkpos(stop_client_id="old")
    with st.tx():
        st.insert_position(pos)
    o = om.replace_stop(pos, 99.5)
    assert not o.ok and o.note == "would_trigger" and st.get_position(1).current_stop == 98.0


def test_two_stop_rejections_close_position(env):
    st, clock, make = env
    b, om = make({("place_stop", 1): "rejected", ("place_stop", 2): "rejected"})
    pos = mkpos()
    with st.tx():
        st.insert_position(pos)
    o = om.place_initial_stop(pos)
    assert not o.ok and o.note == "stop_failed_closed"
    assert any(c[0] == "market_order" for c in b.calls)
    assert st.get_position(1).status == "closing" and st.kv_get("entries_blocked_reason") == "stop_failed"


def test_submit_exit_marks_closing(env):
    st, clock, make = env
    b, om = make()
    pos = mkpos()
    with st.tx():
        st.insert_position(pos)
    o = om.submit_exit(pos, "target", T0)
    p = st.get_position(1)
    assert o.ok and p.status == "closing" and p.exit_client_id == o.order.client_id and p.exit_reason == "target"
    assert len(o.order.client_id) == 29
