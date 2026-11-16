"""03 implementasyon saglamlik testleri (paper broker, funding). Bagimsiz spec suite'i ayri dosyadadir."""
from __future__ import annotations

import json
import random
from datetime import datetime, timedelta, timezone

import pytest

from trader_engine.brokers.paper import FaultPlan, FaultRule, PaperBroker, PaperConfig
from trader_engine.clock import SimClock
from trader_engine.config import CostModel
from trader_engine.errors import BrokerError, BrokerUncertain
from trader_engine.funding import accrue, due_funding_times, funding_payment
from trader_engine.types import FundingPoint, MinuteBar, OrderRequest, SymbolRules

P = "BTC/USDT"
T0 = datetime(2026, 12, 1, 9, 0, tzinfo=timezone.utc)
RULES = SymbolRules(pair=P, symbol="BTCUSDT", tick=0.01, step=0.001, min_qty=0.001, max_qty=1000.0, min_notional=5.0)


def bar(i, lo=None, o=100.0, h=None, c=None, mo="same", ml=None, mh=None, mc="same", lo_last=None, pair=P):
    ts = T0 + timedelta(minutes=i)
    c = o if c is None else c
    h = max(o, c) if h is None else h
    l = min(o, c) if lo is None else lo
    return MinuteBar(pair=pair, open_ts=ts, step_s=60, last_o=o, last_h=h, last_l=l if lo_last is None else lo_last,
                     last_c=c, mark_o=o if mo == "same" else mo, mark_h=h if mh is None else mh,
                     mark_l=l if ml is None else ml, mark_c=c if mc == "same" else mc)


def mk(cost=None, fpts=None, plan=None, mmr=0.004):
    clock = SimClock(T0)
    b = PaperBroker(PaperConfig(cost=cost or CostModel(), mmr=mmr), lambda p: RULES,
                    lambda p, a, z: [x for x in (fpts or []) if a < x.ts <= z], clock, plan)
    return b, clock


def req(cid, role, side, qty, trig=None, lev=3, ro=None):
    return OrderRequest(client_id=cid, pair=P, role=role, order_side=side, qty=qty, trigger_price=trig,
                        reduce_only=(role != "entry") if ro is None else ro, leverage=lev if role == "entry" else None)


def step(b, bars, between=None):
    b.advance(bars, "fills")
    ev = b.poll(T0)
    if between:
        between()
    b.advance(bars, "triggers")
    return ev + b.poll(T0)


def enter(b, q=6.369):
    b.prepare(P, 3)
    assert b.market_order(req("e1", "entry", "buy", q)).status == "accepted"
    return step(b, {P: bar(0)})


def test_example_long_entry_and_stop():
    b, _ = mk()
    ev = enter(b)
    f = ev[0].fill
    assert f.price == 100.02 and f.reason == "market"
    assert f.fee == pytest.approx(0.31851369)
    pos = b.positions()[0]
    assert pos.margin == pytest.approx(212.34246) and pos.liq_price == pytest.approx(67.08008)
    assert b.account().wallet == pytest.approx(999.68148631)
    assert b.place_stop(req("s1", "stop", "sell", 6.369, 98.0)).status == "accepted"
    ev = step(b, {P: bar(1, o=99.2, lo=97.9, h=99.5, c=98.5)})
    assert [e.kind for e in ev] == ["fill"] and ev[0].fill.price == 97.95 and ev[0].fill.reason == "stop"
    assert b.account().wallet == pytest.approx(986.185734535)
    assert b.positions() == []


def test_gap_stop_uses_last_open():
    b, _ = mk()
    enter(b)
    b.place_stop(req("s1", "stop", "sell", 6.369, 98.0))
    ev = step(b, {P: bar(1, o=97.6, lo=97.0, h=97.8, c=97.5, mo=97.5, ml=97.0, mh=97.7)})
    assert ev[0].fill.price == 97.55


def test_stop_and_target_same_step_stop_wins():
    b, _ = mk()
    enter(b)
    b.place_stop(req("s1", "stop", "sell", 6.369, 98.0))
    b.place_target(req("t1", "target", "sell", 6.369, 104.0))
    ev = step(b, {P: bar(1, o=100, lo=97.9, h=105, c=100)})
    kinds = [(e.kind, e.fill.reason if e.fill else None) for e in ev]
    assert kinds == [("fill", "stop"), ("order_canceled", None)]
    assert b.query(P, "t1").status == "canceled"


def test_liquidation_loses_exact_margin():
    b, _ = mk()
    enter(b)
    w0 = b.account().wallet
    margin = b.positions()[0].margin
    ev = step(b, {P: bar(1, o=70, lo=66.0, h=70, c=68)})
    assert ev[0].kind == "liquidation" and ev[0].fill.price == pytest.approx(67.08008)
    assert b.account().wallet == pytest.approx(w0 - margin)


def test_funding_long_short_and_not_on_entry_step():
    pts = [FundingPoint(P, T0 + timedelta(hours=23), 0.0001, 101.0)]   # 08:00 ertesi gun
    b, _ = mk(fpts=pts)
    b.prepare(P, 3)
    b.market_order(req("e1", "entry", "buy", 6.369))
    step(b, {P: bar(0)})
    w0 = b.account().wallet
    ev = step(b, {P: bar(23 * 60, o=100)})   # 08:00 adimi
    fe = [e for e in ev if e.kind == "funding"]
    assert fe and fe[0].funding_paid == pytest.approx(0.0643269)
    assert b.account().wallet == pytest.approx(w0 - 0.0643269)
    assert funding_payment("short", 6.357, 101, 0.0001) == pytest.approx(-0.0642057)
    # giris adiminda funding yok
    b2, _ = mk(fpts=[FundingPoint(P, T0, 0.0001, 100.0)])
    b2.prepare(P, 3)
    b2.market_order(req("e1", "entry", "buy", 1.0))
    ev = step(b2, {P: bar(0)})
    assert not [e for e in ev if e.kind == "funding"]


def test_funding_missing_counter():
    b, _ = mk()
    enter(b)
    step(b, {P: bar(23 * 60)})
    # 16:00 ve 00:00 noktalari bekleme siniri (15 dk) asilmis -> eksik; 08:00 noktasi henuz bekliyor (imlec tutulur)
    assert b.counters()["funding_missing"] == 2
    step(b, {P: bar(23 * 60 + 16)})
    assert b.counters()["funding_missing"] == 3


def test_rejects_and_duplicates():
    b, _ = mk()
    r = lambda q=6.369, lev=3, cid="x": req(cid, "entry", "buy", q, lev=lev)
    assert b.market_order(r()).reason == "not_prepared"
    b.prepare(P, 3)
    assert b.market_order(r(lev=2)).reason == "leverage_mismatch"
    assert b.market_order(r(q=6.3695)).reason == "step"
    assert b.market_order(r(q=0.0)).reason == "qty"
    assert b.market_order(req("x", "exit", "sell", 1.0)).reason == "no_position"
    assert b.market_order(r(cid="e1")).status == "accepted"
    assert b.market_order(r(cid="e1")).reason == "duplicate_client_id"
    assert b.counters()["duplicates"] == 1
    step(b, {P: bar(0)})
    assert b.query(P, "e1").status == "filled"
    assert b.market_order(r(cid="e2")).reason == "position_exists"
    assert b.market_order(req("x1", "exit", "buy", 1.0)).reason == "wrong_side"
    assert b.market_order(req("x2", "exit", "sell", 99.0)).reason == "reduce_only_exceeds"
    assert b.place_stop(req("s", "stop", "sell", 6.369, 100.5)).reason == "would_trigger"
    assert b.place_stop(req("s", "stop", "sell", 6.369, 98.005)).reason == "tick"


def test_min_notional_and_insufficient_margin():
    b, _ = mk()
    b.prepare(P, 3)
    b.market_order(req("e1", "entry", "buy", 0.01))
    ev = step(b, {P: bar(0)})
    assert ev[0].kind == "order_rejected" and ev[0].detail == "min_notional"
    b.market_order(req("e2", "entry", "buy", 100.0))
    ev = step(b, {P: bar(1)})
    assert ev[0].detail == "insufficient_margin"


def test_two_stops_tightest_wins_and_market_exit():
    b, _ = mk()
    enter(b)
    b.place_stop(req("s1", "stop", "sell", 6.369, 95.0))
    b.place_stop(req("s2", "stop", "sell", 6.369, 98.0))
    ev = step(b, {P: bar(1, o=100, lo=97.0, h=100, c=99)})
    assert ev[0].fill.client_id == "s2" and ev[0].fill.price == 97.95
    assert b.query(P, "s1").status == "canceled"
    b2, _ = mk()
    enter(b2)
    b2.place_stop(req("s1", "stop", "sell", 6.369, 90.0))
    b2.market_order(req("x1", "exit", "sell", 6.369))
    ev = step(b2, {P: bar(1, o=101, lo=100, h=101, c=100)})
    assert ev[0].fill.reason == "market" and ev[0].fill.price == 100.97 and ev[1].kind == "order_canceled"


def test_legacy_compat_no_slip_no_round():
    cost = CostModel(fill_model="legacy_compat", trigger_source="last", granularity="15m", taker_fee=0.0005)
    b, _ = mk(cost)
    b.prepare(P, 3)
    b.market_order(req("e1", "entry", "buy", 6.369))
    ev = step(b, {P: bar(0)})
    assert ev[0].fill.price == 100.0
    b.place_stop(req("s1", "stop", "sell", 6.369, 98.0))
    ev = step(b, {P: bar(1, o=99, lo=97.9, h=99, c=98)})
    assert ev[0].fill.price == 98.0
    assert b.account().wallet == pytest.approx(1000 - 6.369 * 100 * 0.0005 - 6.369 * 98 * 0.0005 - 6.369 * 2)


def test_mark_fallback_and_minute_gap():
    b, _ = mk()
    enter(b)
    b.place_stop(req("s1", "stop", "sell", 6.369, 50.0))
    step(b, {P: bar(1, mo=None, ml=None, mh=None, mc=None)})
    assert b.counters()["mark_fallbacks"] >= 1
    b.advance({"ETH/USDT": bar(2, pair="ETH/USDT")}, "fills")
    assert b.counters()["minute_gaps"] == 1


def test_fault_plan_effects():
    plan = FaultPlan([FaultRule("market_order", 1, "unknown_executed"), FaultRule("market_order", 2, "unknown_not_executed"),
                      FaultRule("market_order", 3, "rejected", "boom"), FaultRule("market_order", 4, "raise_uncertain")])
    b, _ = mk(plan=plan)
    b.prepare(P, 3)
    assert b.market_order(req("a", "entry", "buy", 1.0)).status == "unknown" and b.query(P, "a").status == "new"
    assert b.market_order(req("b", "entry", "buy", 1.0)).status == "unknown" and b.query(P, "b") is None
    r = b.market_order(req("c", "entry", "buy", 1.0))
    assert (r.status, r.reason) == ("rejected", "boom") and b.query(P, "c") is None
    with pytest.raises(BrokerUncertain):
        b.market_order(req("d", "entry", "buy", 1.0))


def test_prepare_and_cancel_semantics():
    b, _ = mk()
    with pytest.raises(BrokerError):
        b.prepare(P, 0)
    enter(b)
    b.prepare(P, 3)
    with pytest.raises(BrokerError):
        b.prepare(P, 4)
    b.cancel(P, "nope")   # sessiz no-op
    b.place_stop(req("s1", "stop", "sell", 6.369, 90.0))
    b.cancel(P, "s1")
    assert [e.kind for e in b.poll(T0)] == ["order_canceled"] and b.poll(T0) == []


def _run(b, bars, lo, hi):
    out = []
    for i in range(lo, hi):
        out += step(b, {P: bars[i]})
        if i % 7 == 0 and not b.positions():
            b.market_order(req(f"e{i}", "entry", "buy", 1.0))
        elif i % 7 == 3 and b.positions():
            b.place_stop(req(f"s{i}", "stop", "sell", 1.0, round(bars[i].mark_c * 0.97, 2)))
    return out


def test_snapshot_restore_bit_identical():
    rnd = random.Random(7)
    px, bars = 100.0, []
    for i in range(300):
        o = px
        px = max(10.0, round(px * (1 + rnd.uniform(-0.01, 0.01)), 2))
        h, l = max(o, px) * 1.003, min(o, px) * 0.997
        bars.append(bar(i, o=o, h=round(h, 2), lo=round(l, 2), c=px))
    full, _ = mk()
    full.prepare(P, 3)
    ev_full = _run(full, bars, 0, 300)
    a, _ = mk()
    a.prepare(P, 3)
    ev_a = _run(a, bars, 0, 150)
    snap = json.loads(json.dumps(a.snapshot()))
    c, _ = mk()
    c.restore(snap)
    ev_c = _run(c, bars, 150, 300)
    assert ev_a + ev_c == ev_full
    assert json.dumps(c.snapshot(), sort_keys=True) == json.dumps(full.snapshot(), sort_keys=True)
    assert any(e.kind == "fill" for e in ev_full)
    with pytest.raises(BrokerError):
        c.restore({"wallet": 1.0})


def test_funding_module_edges():
    assert funding_payment("long", 2, 100, -0.001) == pytest.approx(-0.2)
    for args in (("long", 0, 1, 0.1), ("long", 1, 0, 0.1), ("long", 1, 1, float("nan"))):
        with pytest.raises(ValueError):
            funding_payment(*args)
    u = datetime(2026, 12, 1, 8, 0, tzinfo=timezone.utc)
    assert due_funding_times(None, u) == [u]
    assert due_funding_times(u, u) == []
    assert len(due_funding_times(u - timedelta(hours=24), u)) == 3
    pts = [FundingPoint(P, u, 0.001, None), FundingPoint(P, u - timedelta(hours=8), 0.001, 50.0)]
    tot, n = accrue(u - timedelta(hours=1), pts, "long", 1.0, 100.0)
    assert n == 1 and tot == pytest.approx(0.1)
