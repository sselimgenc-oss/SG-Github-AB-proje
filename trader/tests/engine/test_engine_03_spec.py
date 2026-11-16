"""Independent spec tests for engine unit 03 (docs/motor/03-paper-broker.md).

Hand-computed numbers come from the spec section 9 examples.  Written
without looking at the implementation.
"""
from __future__ import annotations

import json
import math
import random
from datetime import datetime, timedelta, timezone

import pytest

from trader_engine.bars import funding_times
from trader_engine.clock import SimClock
from trader_engine.config import CostModel
from trader_engine.errors import BrokerError, BrokerUncertain
from trader_engine.numeric import floor_step
from trader_engine.types import FundingPoint, MinuteBar, OrderRequest, SymbolRules

from trader_engine.brokers.paper import PaperBroker, PaperConfig  # noqa: E402

try:  # FaultPlan home is not pinned by the spec text
    from trader_engine.brokers.paper import FaultPlan, FaultRule
except ImportError:  # pragma: no cover
    from trader_engine.brokers.base import FaultPlan, FaultRule

from trader_engine import funding as F

PAIR = "BTC/USDT"
UTC = timezone.utc
T0 = datetime(2026, 12, 1, 9, 0, tzinfo=UTC)
RULES = SymbolRules(pair=PAIR, symbol="BTCUSDT", tick=0.01, step=0.001,
                    min_qty=0.001, max_qty=1000.0, min_notional=5.0)
A = pytest.approx


def approx(x, tol=1e-9):
    return pytest.approx(x, rel=tol, abs=1e-9)


def mb(ts, last=(100.0, 100.5, 99.5, 100.0), mark="same", step_s=60, pair=PAIR):
    if mark == "same":
        mark = last
    mo, mh, ml, mc = mark if mark else (None,) * 4
    return MinuteBar(pair=pair, open_ts=ts, step_s=step_s, last_o=last[0], last_h=last[1],
                     last_l=last[2], last_c=last[3], mark_o=mo, mark_h=mh, mark_l=ml, mark_c=mc)


def req(cid, role, side, qty, trig=None, reduce_only=False, lev=3, pair=PAIR):
    return OrderRequest(client_id=cid, pair=pair, role=role, order_side=side, qty=qty,
                        trigger_price=trig, reduce_only=reduce_only,
                        leverage=lev if role == "entry" else None)


class Env:
    def __init__(self, cost=None, mmr=0.004, wallet=1000.0, funding=(), fault=None,
                 step_s=60, start=T0):
        self.cost = cost or CostModel()
        self.points = list(funding)
        self.clock = SimClock(start)
        self.step_s = step_s
        cfg = PaperConfig(cost=self.cost, mmr=mmr, wallet_start=wallet)
        self.b = PaperBroker(cfg, lambda p: RULES, self._ff, self.clock, fault)
        self.b.prepare(PAIR, 3)
        self.events = []

    def _ff(self, pair, start, end):
        return [p for p in self.points if p.pair == pair and (start is None or p.ts > start) and p.ts <= end]

    def step(self, bar, between=None):
        bars = {bar.pair: bar} if bar is not None else {}
        self.b.advance(bars, "fills")
        ev1 = self.b.poll(bar.close_ts if bar else self.clock.now())
        if between:
            between(ev1)
        self.b.advance(bars, "triggers")
        ev2 = self.b.poll(bar.close_ts if bar else self.clock.now())
        self.events += ev1 + ev2
        return ev1, ev2


def fills_of(evs, reason=None):
    # a liquidation fill may be carried by a kind="liquidation" event or a kind="fill" event
    return [e.fill for e in evs if e.kind in ("fill", "liquidation") and e.fill is not None
            and (reason is None or e.fill.reason == reason)]


def long_pos(env=None, stop=98.0, ts=T0, **kw):
    """Spec example A: long 6.369 @100.02, optional stop."""
    env = env or Env(**kw)

    def btw(_):
        if stop is not None:
            r = env.b.place_stop(req("stp1", "stop", "sell", 6.369, stop, True))
            assert r.status == "accepted", r

    assert env.b.market_order(req("ent1", "entry", "buy", 6.369)).status == "accepted"
    env.step(mb(ts), btw)
    return env


# ---------------------------------------------------------------- market fills

def test_market_order_accepted_then_fills_next_step_not_immediately():
    env = Env()
    r = env.b.market_order(req("ent1", "entry", "buy", 6.369))
    assert r.status == "accepted" and r.order_id == "P1" or r.order_id.startswith("P")
    assert env.b.positions() == []
    assert env.b.query(PAIR, "ent1").status == "new"
    assert [o.client_id for o in env.b.open_orders(PAIR)] == ["ent1"]


def test_example_a_long_entry_numbers():
    env = long_pos(stop=None)
    f = fills_of(env.events)
    assert len(f) == 1 and f[0].reason == "market" and f[0].role == "entry"
    assert f[0].price == approx(100.02)
    assert f[0].fee == approx(0.31851369)
    acc = env.b.account()
    assert acc.wallet == approx(999.68148631)
    assert acc.used_margin == approx(212.34246)
    assert acc.available == approx(999.68148631 - 212.34246)
    (p,) = env.b.positions()
    assert p.side == "long" and p.qty == 6.369 and p.entry_price == approx(100.02)
    assert p.margin == approx(212.34246) and p.liq_price == approx(67.08008)
    assert p.leverage == 3
    # last_mark = mark_c = 100 -> unrealized = (100-100.02)*6.369
    assert acc.unrealized == approx(-0.02 * 6.369, 1e-6)
    assert acc.equity == approx(acc.wallet + acc.unrealized)
    assert env.b.query(PAIR, "ent1").status == "filled"


def test_entry_slippage_rounds_adverse_buy_up_sell_down():
    env = Env()
    env.b.market_order(req("e1", "entry", "buy", 1.0))
    env.step(mb(T0, (100.123, 100.5, 99.5, 100.0)))
    # 100.123*1.0002 = 100.1430246 -> ceil tick 100.15
    assert env.b.positions()[0].entry_price == approx(100.15)

    env2 = Env()
    env2.b.market_order(req("e1", "entry", "sell", 1.0))
    env2.step(mb(T0, (100.123, 100.5, 99.5, 100.0)))
    # 100.123*0.9998 = 100.1029754 -> floor tick 100.10
    assert env2.b.positions()[0].entry_price == approx(100.10)


def test_short_entry_numbers_and_liq_above_entry():
    env = Env()
    env.b.market_order(req("s1", "entry", "sell", 6.357))
    env.step(mb(T0))
    (f,) = fills_of(env.events)
    assert f.price == approx(99.98)  # 100*0.9998
    assert f.fee == approx(6.357 * 99.98 * 0.0005)
    p = env.b.positions()[0]
    assert p.side == "short" and p.liq_price > p.entry_price
    assert p.margin == approx(6.357 * 99.98 / 3)
    assert env.b.account().wallet == approx(1000 - 6.357 * 99.98 * 0.0005)


def test_market_exit_long_pnl_and_cancels_stop():
    env = long_pos(stop=98.0)
    env.b.market_order(req("ex1", "exit", "sell", 6.369, None, True))
    assert env.b.positions()  # not yet
    env.step(mb(T0 + timedelta(minutes=1), (101.0, 101.5, 100.5, 101.0)))
    (f,) = [x for x in fills_of(env.events) if x.role == "exit"]
    assert f.price == approx(100.97)  # 101*0.9998=100.9798 -> floor
    gross = 6.369 * (100.97 - 100.02)
    fee = 6.369 * 100.97 * 0.0005
    assert env.b.account().wallet == approx(999.68148631 + gross - fee)
    assert env.b.positions() == []
    assert env.b.query(PAIR, "stp1").status == "canceled"
    assert any(e.kind == "order_canceled" and e.client_id == "stp1" for e in env.events)
    assert env.b.open_orders(PAIR) == []


def test_short_exit_pnl():
    env = Env()
    env.b.market_order(req("s1", "entry", "sell", 6.357))
    env.step(mb(T0))
    env.b.market_order(req("x1", "exit", "buy", 6.357, None, True))
    env.step(mb(T0 + timedelta(minutes=1), (99.0, 99.5, 98.5, 99.0)))
    (f,) = [x for x in fills_of(env.events) if x.role == "exit"]
    assert f.price == approx(99.02)  # 99*1.0002=99.0198 -> ceil
    w = 1000 - 6.357 * 99.98 * 0.0005 + 6.357 * (99.98 - 99.02) - 6.357 * 99.02 * 0.0005
    assert env.b.account().wallet == approx(w)
    assert env.b.positions() == []


# ---------------------------------------------------------------- stops

def test_example_2_stop_trigger_on_mark_no_gap():
    env = long_pos(stop=98.0)
    env.step(mb(T0 + timedelta(minutes=1), last=(99.2, 99.5, 97.0, 98.5),
                mark=(99.20, 99.5, 97.90, 98.5)))
    (f,) = fills_of(env.events, "stop")
    assert f.price == approx(97.95)  # 98*0.9995=97.951 -> floor
    assert f.fee == approx(0.311921775)
    assert env.b.account().wallet == approx(986.185734535)
    assert env.b.positions() == []
    r = (-13.18383 - 0.31851369 - 0.311921775) / 13.999062
    assert r == A(-0.9868, abs=2e-4)
    assert env.b.query(PAIR, "stp1").status == "filled"


def test_stop_trigger_uses_mark_not_last():
    env = long_pos(stop=98.0)
    # last low pierces stop but mark low does not -> no fill
    env.step(mb(T0 + timedelta(minutes=1), last=(99.2, 99.5, 97.0, 98.5), mark=(99.2, 99.5, 98.5, 99.0)))
    assert fills_of(env.events, "stop") == [] and env.b.positions()


def test_stop_not_triggered_when_mark_low_above_stop():
    env = long_pos(stop=98.0)
    env.step(mb(T0 + timedelta(minutes=1), mark=(99.0, 99.5, 98.01, 99.0), last=(99.0, 99.5, 97.0, 99.0)))
    assert env.b.positions()


def test_example_3_gap_stop_fills_at_last_open():
    env = long_pos(stop=98.0)
    env.step(mb(T0 + timedelta(minutes=1), last=(97.60, 97.8, 97.0, 97.5),
                mark=(97.50, 97.7, 97.0, 97.4)))
    (f,) = fills_of(env.events, "stop")
    assert f.price == approx(97.55)  # 97.60*0.9995=97.5512 -> floor


def test_gap_mark_open_beyond_stop_but_last_open_above_fills_at_last_open():
    env = long_pos(stop=98.0)
    env.step(mb(T0 + timedelta(minutes=1), last=(98.50, 98.6, 97.0, 98.0),
                mark=(97.90, 98.0, 97.0, 97.5)))
    (f,) = fills_of(env.events, "stop")
    assert f.price == approx(floor_step(98.5 * 0.9995, 0.01))  # 98.45


def test_short_stop_no_gap_and_gap():
    def setup():
        env = Env()
        env.b.market_order(req("s1", "entry", "sell", 6.357))

        def btw(_):
            assert env.b.place_stop(req("st", "stop", "buy", 6.357, 102.0, True)).status == "accepted"
        env.step(mb(T0), btw)
        return env
    env = setup()
    env.step(mb(T0 + timedelta(minutes=1), last=(101, 103, 100.5, 102), mark=(101.0, 102.1, 100.5, 102)))
    (f,) = fills_of(env.events, "stop")
    assert f.price == approx(102.06)  # 102*1.0005=102.051 -> ceil
    gross = 6.357 * (99.98 - 102.06)
    assert env.b.account().wallet == approx(1000 - 6.357 * 99.98 * 0.0005 + gross - 6.357 * 102.06 * 0.0005)
    env = setup()
    env.step(mb(T0 + timedelta(minutes=1), last=(102.6, 103, 102, 102.5), mark=(102.5, 103, 102, 102.5)))
    (f,) = fills_of(env.events, "stop")
    assert f.price == approx(102.66)  # 102.6*1.0005=102.6513 -> ceil


def test_example_6_stop_and_target_same_step_stop_wins():
    env = long_pos(stop=98.0)
    assert env.b.place_target(req("tgt", "target", "sell", 6.369, 104.0, True)).status == "accepted"
    env.step(mb(T0 + timedelta(minutes=1), last=(100, 105, 97, 100), mark=(100.0, 105.0, 97.9, 100.0)))
    fs = fills_of(env.events)
    assert [f.reason for f in fs if f.role != "entry"] == ["stop"]
    assert [f for f in fs if f.reason == "stop"][0].price == approx(97.95)
    assert env.b.query(PAIR, "tgt").status == "canceled"
    assert env.b.positions() == []


def test_target_fill_and_gap_target():
    env = long_pos(stop=98.0)
    env.b.place_target(req("tgt", "target", "sell", 6.369, 104.0, True))
    env.step(mb(T0 + timedelta(minutes=1), last=(100, 105, 99.5, 104.5), mark=(100.0, 104.5, 99.5, 104.2)))
    (f,) = fills_of(env.events, "target")
    assert f.price == approx(103.97)  # 104*0.9998=103.9792 -> floor
    assert env.b.query(PAIR, "stp1").status == "canceled"
    env = long_pos(stop=98.0)
    env.b.place_target(req("tgt", "target", "sell", 6.369, 104.0, True))
    env.step(mb(T0 + timedelta(minutes=1), last=(105.0, 106, 104.5, 105.5), mark=(105.0, 106, 104.5, 105.5)))
    (f,) = fills_of(env.events, "target")
    assert f.price == approx(104.97)  # 105*0.9998=104.979


def test_entry_step_stop_checked_against_same_step_mark_range():
    env = Env()
    env.b.market_order(req("ent1", "entry", "buy", 6.369))

    def btw(_):
        assert env.b.place_stop(req("st", "stop", "sell", 6.369, 98.0, True)).status == "accepted"
    # same bar: entry at 100, closes 99.5 (mark_c > 98), mark low 97.5 pierces stop
    env.step(mb(T0, last=(100, 100.5, 97.0, 99.5), mark=(100, 100.5, 97.5, 99.5)), btw)
    assert len(fills_of(env.events, "stop")) == 1
    assert env.b.positions() == []


def test_pending_exit_beats_stop_in_same_step():
    env = long_pos(stop=98.0)
    env.b.market_order(req("ex1", "exit", "sell", 6.369, None, True))
    env.step(mb(T0 + timedelta(minutes=1), last=(100, 100.5, 96, 99), mark=(100, 100.5, 96, 99)))
    assert fills_of(env.events, "stop") == []
    assert [f.role for f in fills_of(env.events) if f.role != "entry"] == ["exit"]
    assert env.b.query(PAIR, "stp1").status == "canceled"


# ---------------------------------------------------------------- stop management

def test_two_stops_tightest_triggers_and_new_before_old_replace():
    env = long_pos(stop=98.0)
    # new-before-old: place tighter new stop, old still standing, then cancel old
    assert env.b.place_stop(req("stp2", "stop", "sell", 6.369, 99.0, True)).status == "accepted"
    assert {o.client_id for o in env.b.open_orders(PAIR)} == {"stp1", "stp2"}
    env.b.cancel(PAIR, "stp1")
    assert env.b.query(PAIR, "stp1").status == "canceled"
    assert [o.client_id for o in env.b.open_orders(PAIR)] == ["stp2"]
    env.step(mb(T0 + timedelta(minutes=1), mark=(100.0, 100.0, 98.5, 99.0), last=(100, 100, 98.5, 99)))
    (f,) = fills_of(env.events, "stop")
    assert f.client_id == "stp2" and f.price == approx(98.95)  # 99*.9995=98.9505


def test_two_stops_both_standing_tightest_wins_then_other_canceled():
    env = long_pos(stop=98.0)
    env.b.place_stop(req("stp2", "stop", "sell", 6.369, 99.0, True))
    env.step(mb(T0 + timedelta(minutes=1), mark=(100.0, 100.0, 97.0, 98.0), last=(100, 100, 97, 98)))
    (f,) = fills_of(env.events, "stop")
    assert f.client_id == "stp2"
    assert env.b.query(PAIR, "stp1").status == "canceled"
    assert env.b.open_orders(PAIR) == []


def test_cancel_noop_cases():
    env = Env()
    env.b.cancel(PAIR, "nonexistent")  # no error
    env = long_pos(stop=98.0)
    env.b.cancel(PAIR, "ent1")  # already filled: no-op
    assert env.b.query(PAIR, "ent1").status == "filled"
    env.b.cancel(PAIR, "stp1")
    env.b.cancel(PAIR, "stp1")  # twice
    assert env.b.query(PAIR, "stp1").status == "canceled"
    assert env.b.query(PAIR, "nope") is None


def test_cancel_emits_event():
    env = long_pos(stop=98.0)
    env.b.cancel(PAIR, "stp1")
    evs = env.b.poll(T0 + timedelta(minutes=2))
    assert any(e.kind == "order_canceled" and e.client_id == "stp1" for e in evs)


def test_trailing_stop_on_profit_side_allowed():
    env = long_pos(stop=98.0)
    # price rose to 105 -> stop 103 (above entry, below last_mark) allowed
    env.step(mb(T0 + timedelta(minutes=1), (105, 105.5, 104.5, 105)))
    assert env.b.place_stop(req("trail", "stop", "sell", 6.369, 103.0, True)).status == "accepted"


# ---------------------------------------------------------------- validation / rejects

def test_reject_not_prepared_and_leverage_mismatch():
    env = Env()
    r = env.b.market_order(OrderRequest("c", "ETH/USDT", "entry", "buy", 1.0, None, False, 3))
    # pair has different rules fn; not prepared -> rejected (rules_fn returns BTC rules)
    assert r.status == "rejected" and r.reason == "not_prepared"
    r = env.b.market_order(req("c2", "entry", "buy", 1.0, lev=5))
    assert r.status == "rejected" and r.reason == "leverage_mismatch"
    assert env.b.query(PAIR, "c2") is None or env.b.query(PAIR, "c2").status == "rejected"


def test_reject_step_qty_nonpositive_max():
    env = Env()
    assert env.b.market_order(req("a", "entry", "buy", 6.3695)).reason == "step"
    for i, q in enumerate([0.0, -1.0, float("nan"), float("inf")]):
        assert env.b.market_order(req(f"q{i}", "entry", "buy", q)).status == "rejected"
    assert env.b.market_order(req("big", "entry", "buy", 1001.0)).status == "rejected"
    assert env.b.positions() == [] and env.b.account().wallet == 1000.0


def test_reject_position_exists_and_reduce_only_rules():
    env = long_pos(stop=None)
    assert env.b.market_order(req("e2", "entry", "buy", 1.0)).reason == "position_exists"
    assert env.b.market_order(req("x1", "exit", "buy", 1.0, None, True)).reason == "wrong_side"
    assert env.b.market_order(req("x2", "exit", "sell", 7.0, None, True)).reason == "reduce_only_exceeds"
    env2 = Env()
    assert env2.b.market_order(req("x3", "exit", "sell", 1.0, None, True)).reason == "no_position"


def test_reject_no_partial_reduce_semantic_equal_ok():
    env = long_pos(stop=None)
    assert env.b.market_order(req("x1", "exit", "sell", 6.369, None, True)).status == "accepted"


def test_place_stop_validations():
    env = long_pos(stop=None)
    assert env.b.place_stop(req("s0", "stop", "sell", 6.369, 98.005, True)).reason == "tick"
    assert env.b.place_stop(req("s1", "stop", "sell", 7.0, 98.0, True)).status == "rejected"
    assert env.b.place_stop(req("s2", "stop", "sell", 6.369, 98.0, False)).status == "rejected"
    assert env.b.place_stop(req("s3", "stop", "sell", 6.369, 98.0, True)).status == "accepted"
    r = env.b.place_stop(req("s3", "stop", "sell", 6.369, 97.0, True))
    assert r.status == "rejected" and r.reason == "duplicate_client_id"
    assert Env().b.place_stop(req("s4", "stop", "sell", 1.0, 98.0, True)).status == "rejected"


def test_example_8_would_trigger_stop_and_target():
    env = long_pos(stop=None)
    r = env.b.place_stop(req("w", "stop", "sell", 6.369, 100.5, True))
    assert r.status == "rejected" and r.reason == "would_trigger"
    assert env.b.place_stop(req("w2", "stop", "sell", 6.369, 100.0, True)).reason == "would_trigger"  # >= last_mark
    assert env.b.place_target(req("t", "target", "sell", 6.369, 99.5, True)).reason == "would_trigger"
    short = Env()
    short.b.market_order(req("s", "entry", "sell", 6.357))
    short.step(mb(T0))
    assert short.b.place_stop(req("w", "stop", "buy", 6.357, 99.5, True)).reason == "would_trigger"
    assert short.b.place_target(req("t", "target", "buy", 6.357, 100.5, True)).reason == "would_trigger"


def test_example_7_duplicate_client_id():
    env = long_pos(stop=None)
    r = env.b.market_order(req("ent1", "entry", "buy", 6.369))
    assert r.status == "rejected" and r.reason == "duplicate_client_id"
    o = env.b.query(PAIR, "ent1")
    assert o.status == "filled" and o.qty == 6.369
    assert len(env.b.positions()) == 1 and env.b.positions()[0].qty == 6.369
    assert env.b.counters()["duplicates"] >= 1


def test_duplicate_while_pending_does_not_double_fill():
    env = Env()
    env.b.market_order(req("e", "entry", "buy", 1.0))
    assert env.b.market_order(req("e", "entry", "buy", 1.0)).reason == "duplicate_client_id"
    env.step(mb(T0))
    assert env.b.positions()[0].qty == 1.0


def test_min_notional_rejected_at_fill():
    env = Env()
    assert env.b.market_order(req("e", "entry", "buy", 0.001)).status == "accepted"  # 0.1 USDT notional
    env.step(mb(T0))
    assert env.b.positions() == [] and env.b.account().wallet == 1000.0
    assert env.b.query(PAIR, "e").status == "rejected"
    evs = [e for e in env.events if e.kind == "order_rejected"]
    assert len(evs) == 1 and "min_notional" in str(evs[0].detail)
    assert fills_of(env.events) == []


def test_insufficient_margin_rejected_at_fill():
    env = Env()
    env.b.market_order(req("e", "entry", "buy", 40.0))  # 4000 notional, margin 1333 > 1000
    env.step(mb(T0))
    assert env.b.positions() == [] and env.b.account().wallet == 1000.0
    assert env.b.query(PAIR, "e").status == "rejected"
    assert any(e.kind == "order_rejected" and "insufficient_margin" in str(e.detail) for e in env.events)
    assert env.b.counters()["rejects"] >= 0


def test_margin_plus_fee_boundary():
    # notional 2999.9.. at 3x: margin ~ 1000 - fee not enough
    env = Env()
    q = 29.99  # 29.99*100.02 = 2999.5998 ; margin 999.8666 ; fee 1.4998 -> margin+fee > 1000
    env.b.market_order(req("e", "entry", "buy", q))
    env.step(mb(T0))
    assert env.b.positions() == []


def test_prepare_rules():
    env = Env()
    env.b.prepare(PAIR, 3)  # idempotent
    with pytest.raises((BrokerError, ValueError, TypeError)):
        env.b.prepare(PAIR, 0)
    long_pos(env, stop=None)
    env.b.prepare(PAIR, 3)
    with pytest.raises(BrokerError):
        env.b.prepare(PAIR, 5)
    assert env.b.rules(PAIR) == RULES
    assert env.b.is_simulated is True


def test_positions_order_one_way_account_flat():
    env = Env()
    acc = env.b.account()
    assert (acc.wallet, acc.unrealized, acc.equity, acc.used_margin, acc.available) == (1000.0, 0.0, 1000.0, 0.0, 1000.0)
    assert env.b.positions() == []


# ---------------------------------------------------------------- funding

def fp(ts, rate, mark):
    return FundingPoint(PAIR, ts, rate, mark)


T_F = datetime(2026, 12, 1, 8, 0, tzinfo=UTC)


def funding_env(side="buy", qty=6.357, points=None, mark=101.0, rate=0.0001):
    pts = [fp(T_F, rate, mark)] if points is None else points
    env = Env(funding=pts, start=T_F - timedelta(minutes=1))
    env.b.market_order(req("e", "entry", side, qty))
    env.step(mb(T_F - timedelta(minutes=1)))
    return env


def test_example_4_funding_long_pays():
    env = funding_env("buy", 6.369)
    w0 = env.b.account().wallet
    env.step(mb(T_F))
    fe = [e for e in env.events if e.kind == "funding"]
    assert len(fe) == 1
    assert fe[0].funding_paid == approx(0.0643269) and fe[0].rate == 0.0001 and fe[0].mark == 101.0
    assert env.b.account().wallet == approx(w0 - 0.0643269)
    assert env.b.positions()[0].funding_paid == approx(0.0643269)


def test_example_4_funding_short_receives():
    env = funding_env("sell", 6.357)
    w0 = env.b.account().wallet
    env.step(mb(T_F))
    (fe,) = [e for e in env.events if e.kind == "funding"]
    assert fe.funding_paid == approx(-0.0642057)
    assert env.b.account().wallet == approx(w0 + 0.0642057)


def test_funding_negative_rate_long_receives():
    env = funding_env("buy", 6.369, rate=-0.0001)
    w0 = env.b.account().wallet
    env.step(mb(T_F))
    assert env.b.account().wallet == approx(w0 + 0.0643269)


def test_funding_not_paid_on_entry_step():
    env = Env(funding=[fp(T_F, 0.0001, 101.0)], start=T_F)
    env.b.market_order(req("e", "entry", "buy", 6.369))
    env.step(mb(T_F))
    assert [e for e in env.events if e.kind == "funding"] == []
    assert env.b.positions()[0].funding_paid == 0.0


def test_funding_no_position_no_payment_and_no_missing_count():
    env = Env(funding=[], start=T_F - timedelta(minutes=1))
    env.step(mb(T_F - timedelta(minutes=1)))
    env.step(mb(T_F))
    assert [e for e in env.events if e.kind == "funding"] == []
    assert env.b.counters()["funding_missing"] == 0
    assert env.b.account().wallet == 1000.0


def test_funding_missing_counted_when_position_open():
    env = funding_env("buy", 6.369, points=[])
    w0 = env.b.account().wallet
    env.step(mb(T_F))
    assert env.b.counters()["funding_missing"] == 0          # imlec bekler (sinirli)
    env.step(mb(T_F + timedelta(minutes=15)))
    assert env.b.counters()["funding_missing"] == 1
    assert env.b.account().wallet == w0


def test_funding_mark_fallback_to_bar_mark_open():
    env = funding_env("buy", 6.369, points=[fp(T_F, 0.0001, None)])
    env.step(mb(T_F, last=(110, 111, 109, 110), mark=(102.0, 103, 101, 102)))
    (fe,) = [e for e in env.events if e.kind == "funding"]
    assert fe.funding_paid == approx(6.369 * 102.0 * 0.0001)
    assert env.b.counters()["mark_fallbacks"] >= 1
    assert env.b.counters()["funding_missing"] == 0


def test_funding_only_once_per_time():
    env = funding_env("buy", 6.369)
    env.step(mb(T_F))
    env.step(mb(T_F + timedelta(minutes=1)))
    assert len([e for e in env.events if e.kind == "funding"]) == 1


def test_funding_module_payment_and_errors():
    assert F.funding_payment("long", 6.369, 101.0, 0.0001) == approx(0.0643269)
    assert F.funding_payment("short", 6.357, 101.0, 0.0001) == approx(-0.0642057)
    assert F.funding_payment("long", 1.0, 100.0, -0.0002) == approx(-0.02)
    with pytest.raises(ValueError):
        F.funding_payment("long", 1.0, 0.0, 0.0001)
    with pytest.raises(ValueError):
        F.funding_payment("long", 0.0, 100.0, 0.0001)
    with pytest.raises(ValueError):
        F.funding_payment("long", 1.0, 100.0, float("nan"))


def test_funding_module_due_times():
    d = lambda *a: datetime(*a, tzinfo=UTC)
    assert F.due_funding_times(d(2026, 12, 1, 0, 0), d(2026, 12, 2, 0, 0)) == [
        d(2026, 12, 1, 8), d(2026, 12, 1, 16), d(2026, 12, 2, 0)]
    assert F.due_funding_times(d(2026, 12, 1, 8, 0), d(2026, 12, 1, 8, 0)) == []  # start exclusive
    assert F.due_funding_times(d(2026, 12, 1, 7, 59), d(2026, 12, 1, 8, 0)) == [d(2026, 12, 1, 8)]
    assert F.due_funding_times(None, d(2026, 12, 1, 9, 0)) == [d(2026, 12, 1, 8)]
    assert F.due_funding_times(None, d(2026, 12, 1, 7, 0)) == [d(2026, 12, 1, 0)] or \
        F.due_funding_times(None, d(2026, 12, 1, 7, 0)) == []
    assert len(F.due_funding_times(None, d(2026, 12, 3, 5, 0))) <= 1


def test_funding_module_accrue():
    d = lambda *a: datetime(*a, tzinfo=UTC)
    pts = [fp(d(2026, 12, 1, 0), 0.0001, 100.0), fp(d(2026, 12, 1, 8), 0.0002, None),
           fp(d(2026, 12, 1, 16), 0.0001, 100.0)]
    tot, n = F.accrue(d(2026, 12, 1, 0), pts, "long", 2.0, 110.0)
    # first point skipped (opened_ts >= p.ts); 2*110*0.0002 + 2*100*0.0001
    assert n == 2 and tot == approx(0.044 + 0.02)
    tot, n = F.accrue(d(2026, 12, 1, 0), pts, "short", 2.0, 110.0)
    assert n == 2 and tot == approx(-(0.044 + 0.02))
    assert F.accrue(d(2026, 12, 2, 0), pts, "long", 2.0, 110.0) == (0.0, 0)


# ---------------------------------------------------------------- liquidation

def test_example_5_liquidation_loss_equals_margin():
    env = long_pos(stop=None)
    env.step(mb(T0 + timedelta(minutes=1), last=(70, 70.5, 65.5, 66.5), mark=(70.0, 70.5, 66.0, 66.5)))
    (f,) = fills_of(env.events, "liquidation")
    assert f.price == approx(67.08008)
    assert f.fee == approx(6.369 * 100.02 * 0.004)
    assert any(e.kind == "liquidation" for e in env.events)
    assert env.b.positions() == []
    gross = 6.369 * (67.08008 - 100.02)
    assert gross - f.fee == approx(-212.34246, 1e-7)
    assert env.b.account().wallet == approx(999.68148631 - 212.34246, 1e-8)


def test_liquidation_before_stop_when_stop_beyond_liq_flagged():
    env = long_pos(stop=60.0)
    env.step(mb(T0 + timedelta(minutes=1), last=(70, 70.5, 65.5, 66.5), mark=(70.0, 70.5, 66.0, 66.5)))
    assert len(fills_of(env.events, "liquidation")) == 1 and fills_of(env.events, "stop") == []
    assert any(e.detail == "liquidation_before_stop" for e in env.events)
    assert env.b.counters().get("anomalies", 1) >= 1


def test_liquidation_when_open_already_beyond_liq_beats_stop():
    env = long_pos(stop=98.0)
    env.step(mb(T0 + timedelta(minutes=1), last=(60, 61, 59, 60), mark=(60.0, 61, 59, 60)))
    assert len(fills_of(env.events, "liquidation")) == 1
    assert fills_of(env.events, "stop") == []
    assert env.b.query(PAIR, "stp1").status == "canceled"


def test_normal_stop_before_liquidation():
    env = long_pos(stop=98.0)
    env.step(mb(T0 + timedelta(minutes=1), last=(99, 99, 60, 60), mark=(99.0, 99.0, 60.0, 60)))
    assert len(fills_of(env.events, "stop")) == 1 and fills_of(env.events, "liquidation") == []


# ---------------------------------------------------------------- counters / edge steps

def test_mark_missing_falls_back_to_last_and_counts():
    env = long_pos(stop=98.0)
    env.step(mb(T0 + timedelta(minutes=1), last=(99, 99.5, 97.5, 98.0), mark=None))
    assert env.b.counters()["mark_fallbacks"] >= 1
    assert len(fills_of(env.events, "stop")) == 1  # last low 97.5 <= 98


def test_minute_gap_counted_and_position_untouched():
    env = long_pos(stop=98.0)
    env.step(None)
    assert env.b.counters()["minute_gaps"] >= 1
    assert env.b.positions()
    # next bar with gap-through stop is caught by gap rule
    env.step(mb(T0 + timedelta(minutes=5), last=(96, 96.5, 95, 95.5), mark=(96, 96.5, 95, 95.5)))
    (f,) = fills_of(env.events, "stop")
    assert f.price == approx(95.95)  # 96*0.9995=95.952 -> floor


def test_coarse_step_900_native():
    env = Env(step_s=900)
    env.b.market_order(req("e", "entry", "buy", 6.369))
    env.step(mb(T0, step_s=900))
    assert env.b.positions()[0].entry_price == approx(100.02)


# ---------------------------------------------------------------- legacy_compat

def legacy_env():
    cost = CostModel(fill_model="legacy_compat", taker_fee=0.0005, trigger_source="last", granularity="15m")
    return Env(cost=cost, step_s=900)


def test_example_9_legacy_compat():
    env = legacy_env()
    env.b.market_order(req("e", "entry", "buy", 6.369))

    def btw(_):
        assert env.b.place_stop(req("st", "stop", "sell", 6.369, 98.0, True)).status == "accepted"
    env.step(mb(T0, (100.0, 100.5, 99.5, 100.0), mark=None, step_s=900), btw)
    assert env.b.positions()[0].entry_price == approx(100.00)
    env.step(mb(T0 + timedelta(minutes=15), (99.0, 99.5, 97.9, 98.5), mark=None, step_s=900))
    (f,) = fills_of(env.events, "stop")
    assert f.price == approx(98.00)
    fee_total = 6.369 * 100 * 0.0005 + 6.369 * 98 * 0.0005
    assert env.b.account().wallet == approx(1000 + 6.369 * (98 - 100) - fee_total)


def test_legacy_no_tick_rounding_and_gap_open():
    env = legacy_env()
    env.b.market_order(req("e", "entry", "buy", 1.0))
    env.step(mb(T0, (100.005, 100.5, 99.5, 100.0), mark=None, step_s=900))
    assert env.b.positions()[0].entry_price == approx(100.005)
    env.b.place_stop(req("st", "stop", "sell", 1.0, 98.0, True))
    env.step(mb(T0 + timedelta(minutes=15), (97.0, 97.5, 96.0, 96.5), mark=None, step_s=900))
    (f,) = fills_of(env.events, "stop")
    assert f.price == approx(97.0)


# ---------------------------------------------------------------- fault plan

def fault_env(method, nth, effect, reason=None):
    return Env(fault=FaultPlan([FaultRule(method, nth, effect, reason)]))


def test_fault_unknown_executed():
    env = fault_env("market_order", 1, "unknown_executed")
    r = env.b.market_order(req("e", "entry", "buy", 1.0))
    assert r.status == "unknown"
    assert env.b.query(PAIR, "e").status == "new"
    env.step(mb(T0))
    assert env.b.positions()


def test_fault_unknown_not_executed():
    env = fault_env("market_order", 1, "unknown_not_executed")
    assert env.b.market_order(req("e", "entry", "buy", 1.0)).status == "unknown"
    assert env.b.query(PAIR, "e") is None
    env.step(mb(T0))
    assert env.b.positions() == []


def test_fault_rejected_with_reason_and_nth():
    env = fault_env("market_order", 2, "rejected", "boom")
    assert env.b.market_order(req("e1", "entry", "buy", 1.0)).status == "accepted"
    r = env.b.market_order(req("e2", "entry", "buy", 1.0))
    assert r.status == "rejected" and r.reason == "boom"
    assert env.b.query(PAIR, "e2") is None
    assert env.b.market_order(req("e3", "entry", "buy", 1.0)).status == "accepted"


def test_fault_raise_uncertain():
    env = fault_env("market_order", 1, "raise_uncertain")
    with pytest.raises(BrokerUncertain):
        env.b.market_order(req("e", "entry", "buy", 1.0))


def test_fault_place_stop_and_cancel():
    env = Env(fault=FaultPlan([FaultRule("place_stop", 1, "unknown_executed"),
                               FaultRule("cancel", 1, "unknown_executed")]))
    env.b.market_order(req("e", "entry", "buy", 6.369))
    env.step(mb(T0))
    assert env.b.place_stop(req("s", "stop", "sell", 6.369, 98.0, True)).status == "unknown"
    assert env.b.query(PAIR, "s").status == "new"
    try:
        env.b.cancel(PAIR, "s")  # executed although uncertain
    except BrokerUncertain:
        pass
    assert env.b.query(PAIR, "s").status == "canceled"


# ---------------------------------------------------------------- random-path driver

def gen_bars(seed, n, vol=0.0012, t0=T0):
    rng = random.Random(seed)
    p = 100.0
    bars = []
    for i in range(n):
        o = round(p, 2)
        c = round(max(1.0, o * (1 + rng.gauss(0, vol))), 2)
        hi = round(max(o, c) * (1 + abs(rng.gauss(0, vol / 2))), 2)
        lo = round(min(o, c) * (1 - abs(rng.gauss(0, vol / 2))), 2)
        bars.append(mb(t0 + timedelta(minutes=i), (o, hi, lo, c)))
        p = c
    sched = [(rng.random(), rng.randint(1000, 5000) / 1000, rng.choice(["buy", "sell"]), rng.random())
             for _ in range(n)]
    return bars, sched


def rand_funding(pair, start, end):
    return [FundingPoint(pair, t, 0.0001, None) for t in funding_times(start, end)] if start else []


def new_broker(start=T0):
    clock = SimClock(start)
    b = PaperBroker(PaperConfig(cost=CostModel(), mmr=0.004), lambda p: RULES, rand_funding, clock)
    b.prepare(PAIR, 3)
    return b


def drive(b, bars, sched, lo, hi, stops=None, obs=None):
    """Stateless driver: behaviour depends only on step index and broker state."""
    stops = {} if stops is None else stops
    for i in range(lo, hi):
        bar = bars[i]
        r, q, side, r2 = sched[i]
        pos = b.positions()
        if not pos and r < 0.06 and not b.open_orders(PAIR):
            b.market_order(req(f"e{i}", "entry", side, q))
        elif pos and r2 < 0.01 and not any(o.role == "exit" for o in b.open_orders(PAIR)):
            p = pos[0]
            b.market_order(req(f"x{i}", "exit", "sell" if p.side == "long" else "buy", p.qty, None, True))
        b.advance({PAIR: bar}, "fills")
        ev1 = b.poll(bar.close_ts)
        for p in b.positions():
            if not any(o.role == "stop" for o in b.open_orders(PAIR)):
                if p.side == "long":
                    trig, osd = floor_step(p.entry_price * 0.995, 0.01), "sell"
                else:
                    trig, osd = round(floor_step(p.entry_price * 1.005, 0.01) + 0.01, 2), "buy"
                rr = b.place_stop(req(f"s{i}", "stop", osd, p.qty, trig, True))
                if rr.status == "accepted":
                    stops[f"s{i}"] = trig
        b.advance({PAIR: bar}, "triggers")
        ev2 = b.poll(bar.close_ts)
        if obs:
            obs(i, bar, ev1 + ev2, stops)


@pytest.mark.parametrize("seed", [1, 7, 42])
def test_property_accounting_invariants(seed):
    bars, sched = gen_bars(seed, 700)
    b = new_broker()
    st = {"wallet": 1000.0, "entry": None, "nfills": 0, "nstops": 0}

    def obs(i, bar, evs, stops):
        for e in evs:
            if e.kind == "funding":
                st["wallet"] -= e.funding_paid
            if e.kind != "fill":
                continue
            f = e.fill
            assert f.fee >= 0 and f.qty > 0 and f.price > 0
            assert f.price == approx(round(f.price / 0.01) * 0.01, 1e-9) or f.reason == "liquidation"
            st["nfills"] += 1
            if f.role == "entry":
                st["entry"] = (f.order_side, f.price, f.qty)
                st["wallet"] -= f.fee
            else:
                side, ep, qty = st["entry"]
                sign = 1 if side == "buy" else -1
                st["wallet"] += sign * qty * (f.price - ep) - f.fee
                st["entry"] = None
                assert f.qty == qty
                if f.reason == "stop":
                    st["nstops"] += 1
                    trig = stops[f.client_id]
                    if f.order_side == "sell":
                        assert f.price <= trig + 1e-9 and bar.mark_l <= trig + 1e-9
                    else:
                        assert f.price >= trig - 1e-9 and bar.mark_h >= trig - 1e-9
                # no position and no standing reduce-only orders after close
                assert b.positions() == []
                assert b.open_orders(PAIR) == []
        acc = b.account()
        assert acc.wallet == approx(st["wallet"], 1e-9)
        assert acc.equity == approx(acc.wallet + acc.unrealized)
        ps = b.positions()
        assert len(ps) <= 1
        assert acc.used_margin == approx(sum(p.margin for p in ps))
        assert acc.available == approx(acc.wallet - acc.used_margin)
        for p in ps:
            assert p.qty > 0
            if p.side == "long":
                assert p.liq_price < p.entry_price
            else:
                assert p.liq_price > p.entry_price
        assert acc.wallet > 0 and math.isfinite(acc.equity)

    drive(b, bars, sched, 0, len(bars), obs=obs)
    assert st["nfills"] >= 4  # the path must actually trade


def test_property_fills_adverse_to_raw_open():
    bars, sched = gen_bars(3, 400)
    b = new_broker()
    seen = []

    def obs(i, bar, evs, stops):
        for e in evs:
            if e.kind == "fill" and e.fill.reason == "market":
                seen.append((e.fill.order_side, e.fill.price, bar.last_o))
    drive(b, bars, sched, 0, 400, obs=obs)
    assert seen
    for side, px, o in seen:
        assert (px >= o - 1e-9) if side == "buy" else (px <= o + 1e-9)


def test_determinism_same_inputs_same_events_and_snapshot():
    bars, sched = gen_bars(11, 400)
    runs = []
    for _ in range(2):
        b = new_broker()
        out = []
        drive(b, bars, sched, 0, 400, obs=lambda i, bar, evs, s: out.extend(evs))
        runs.append((out, json.dumps(b.snapshot(), sort_keys=True)))
    assert runs[0][0] == runs[1][0] and runs[0][1] == runs[1][1]
    assert len(runs[0][0]) > 0


def test_snapshot_restore_midway_equals_uninterrupted():
    n = 1000
    bars, sched = gen_bars(5, n)
    full = new_broker()
    out_full = []
    drive(full, bars, sched, 0, n, obs=lambda i, bar, evs, s: out_full.extend(evs))

    first = new_broker()
    out_a = []
    drive(first, bars, sched, 0, 500, obs=lambda i, bar, evs, s: out_a.extend(evs))
    snap = json.loads(json.dumps(first.snapshot()))  # must be JSON compatible
    second = new_broker(bars[499].close_ts)
    second.restore(snap)
    assert json.dumps(second.snapshot(), sort_keys=True) == json.dumps(first.snapshot(), sort_keys=True)
    out_b = []
    drive(second, bars, sched, 500, n, obs=lambda i, bar, evs, s: out_b.extend(evs))
    assert out_a + out_b == out_full
    assert json.dumps(second.snapshot(), sort_keys=True) == json.dumps(full.snapshot(), sort_keys=True)
    assert any(e.kind == "fill" for e in out_full)


def test_restore_invalid_is_broker_error():
    b = new_broker()
    for bad in ({}, {"wallet": 1.0}, {"junk": 1}):
        with pytest.raises(BrokerError):
            b.restore(bad)


def test_poll_delivers_each_event_once_in_order():
    env = long_pos(stop=98.0)
    assert env.b.poll(T0 + timedelta(hours=1)) == []
    env.b.cancel(PAIR, "stp1")
    evs = env.b.poll(T0 + timedelta(hours=1))
    assert len(evs) == 1
    assert env.b.poll(T0 + timedelta(hours=1)) == []
    ts = [e.ts for e in env.events]
    assert ts == sorted(ts)


def test_ledger_wallet_equals_sum_of_events_on_example_path():
    env = long_pos(stop=98.0)
    env.step(mb(T0 + timedelta(minutes=1), last=(99.2, 99.5, 97.0, 98.5), mark=(99.2, 99.5, 97.9, 98.5)))
    fs = fills_of(env.events)
    entry, stop = fs[0], fs[1]
    d = 6.369 * (stop.price - entry.price) - entry.fee - stop.fee
    assert env.b.account().wallet - 1000.0 == approx(d)
    assert entry.fee >= 0 and stop.fee >= 0
