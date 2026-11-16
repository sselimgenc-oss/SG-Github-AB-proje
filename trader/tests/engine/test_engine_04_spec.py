"""Bagimsiz sartname testi: motor birimi 04 (state / OrderManager / PositionManager).

Kaynak: trader/docs/motor/04-order-position.md (+ 00-index.md). Gerceklemeye bakilmadan yazildi.
Broker arayuzu (03 §3) bu belgedeki kullanimlardan cikarildi: prepare, market_order, place_stop,
place_target, cancel, query, is_simulated. Sahte broker imzalara karsi toleransli yazildi
(OrderRequest'i argumanlar arasindan bulur).
"""
from __future__ import annotations

import dataclasses
import hashlib
import math
import random
import re
from collections import deque
from datetime import datetime, timedelta, timezone

import numpy as np
import pytest

from trader_core import signals
from trader_core.ledger import _EXIT_REASONS, LedgerError, TradeEntry, TradeExit
from trader_engine.bars import floor_tf
from trader_engine.clock import SimClock
from trader_engine.errors import BrokerError, BrokerUncertain, StateError
from trader_engine.order_manager import OrderManager, OrderRow, make_client_id
from trader_engine.position_manager import (ExitContext, apply_entry_fill, apply_exit_fill, apply_funding,
                                            build_trade_entry, build_trade_exit, evaluate_exit,
                                            exit_reason_for_stop_fill, trail_stop_value, update_excursion)
from trader_engine.state import StateStore
from trader_engine.types import (BrokerEvent, BrokerOrder, Fill, Intent, MinuteBar, OrderRequest, OrderResult,
                                 Position, SymbolRules)

UTC = timezone.utc
T0 = datetime(2026, 12, 1, 9, 0, tzinfo=UTC)
PAIR = "BTC/USDT"
TICK = 0.01


def iso(dt: datetime) -> str:
    return dt.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def as_dt(v):
    if isinstance(v, datetime):
        return v
    return datetime.strptime(v, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=UTC)


def rules_fn(pair: str) -> SymbolRules:
    return SymbolRules(pair=pair, symbol=pair.replace("/", ""), tick=TICK, step=0.001, min_qty=0.001,
                       max_qty=1000.0, min_notional=5.0)


# ---------------------------------------------------------------------------------------------
# Sahte broker (03 §3 arayuzu; davranislar betiklenebilir)
# ---------------------------------------------------------------------------------------------
class FakeBroker:
    """script[name] kuyruk ogeleri: 'ok' | 'reject:<neden>' | 'unknown_not_executed' | 'unknown_executed'
    | 'unknown_result_not_executed' | 'unknown_result_executed'. Bos kuyruk = 'ok'."""

    is_simulated = False

    def __init__(self, price: float = 100.0, clock: SimClock | None = None):
        self.price = price
        self.clock = clock
        self.orders: dict[str, BrokerOrder] = {}
        self.calls: list[tuple[str, str | None, object]] = []
        self.script: dict[str, deque] = {k: deque() for k in ("market_order", "place_stop", "place_target", "cancel")}
        self.query_script: deque = deque()   # 'none' -> None, 'real' -> gercek
        self.hooks: dict[str, callable] = {}
        self.cancel_raises = False

    # -- yardimcilar
    @staticmethod
    def _req(args, kw) -> OrderRequest:
        for a in list(args) + list(kw.values()):
            if isinstance(a, OrderRequest):
                return a
        raise AssertionError("OrderRequest bulunamadi")

    @staticmethod
    def _cid(args, kw) -> str | None:
        for a in list(args) + list(kw.values()):
            if isinstance(a, str) and re.match(r"^tr[LT][estx]-", a):
                return a
        return None

    def names(self, *wanted):
        return [c[0] for c in self.calls if c[0] in wanted]

    def count(self, name):
        return sum(1 for c in self.calls if c[0] == name)

    def reqs(self, name):
        return [c[2] for c in self.calls if c[0] == name]

    def now(self):
        return self.clock.now() if self.clock else T0

    def _record(self, req: OrderRequest, market: bool):
        st = "filled" if market else "new"
        self.orders[req.client_id] = BrokerOrder(
            client_id=req.client_id, pair=req.pair, role=req.role, order_side=req.order_side, qty=req.qty,
            trigger_price=req.trigger_price, reduce_only=req.reduce_only, status=st,
            filled_qty=req.qty if market else 0.0, avg_price=self.price if market else None,
            created_ts=self.now(), updated_ts=self.now())

    def _place(self, name, args, kw, market):
        req = self._req(args, kw)
        self.calls.append((name, req.client_id, req))
        if name in self.hooks:
            self.hooks[name](req)
        step = self.script[name].popleft() if self.script[name] else "ok"
        if step.startswith("reject:"):
            return OrderResult(status="rejected", client_id=req.client_id, reason=step.split(":", 1)[1], ts=self.now())
        executed = step.endswith("_executed") and not step.endswith("not_executed")
        if step.startswith("unknown"):
            if executed:
                self._record(req, market)
            if "result" in step:
                return OrderResult(status="unknown", client_id=req.client_id, ts=self.now())
            raise BrokerUncertain("zaman asimi")
        if req.client_id in self.orders:
            return OrderResult(status="rejected", client_id=req.client_id, reason="duplicate_client_id", ts=self.now())
        self._record(req, market)
        if market:
            return OrderResult(status="filled", client_id=req.client_id, order_id="b-" + req.client_id,
                               filled_qty=req.qty, avg_price=self.price, fee=0.0, ts=self.now())
        return OrderResult(status="accepted", client_id=req.client_id, order_id="b-" + req.client_id, ts=self.now())

    # -- arayuz
    def prepare(self, *a, **kw):
        self.calls.append(("prepare", None, a))

    def market_order(self, *a, **kw):
        return self._place("market_order", a, kw, True)

    def place_stop(self, *a, **kw):
        return self._place("place_stop", a, kw, False)

    def place_target(self, *a, **kw):
        return self._place("place_target", a, kw, False)

    def cancel(self, *a, **kw):
        cid = self._cid(a, kw)
        self.calls.append(("cancel", cid, a))
        if "cancel" in self.hooks:
            self.hooks["cancel"](cid)
        if self.cancel_raises:
            raise BrokerError("iptal basarisiz")
        o = self.orders.get(cid)
        if o is not None and o.status == "new":
            self.orders[cid] = dataclasses.replace(o, status="canceled")

    def query(self, *a, **kw):
        cid = self._cid(a, kw)
        self.calls.append(("query", cid, a))
        if self.query_script and self.query_script.popleft() == "none":
            return None
        return self.orders.get(cid)

    def active_stops(self, pair=PAIR):
        return [o for o in self.orders.values() if o.role == "stop" and o.pair == pair and o.status == "new"]


# ---------------------------------------------------------------------------------------------
# Fixture / yardimcilar
# ---------------------------------------------------------------------------------------------
@pytest.fixture
def clock():
    return SimClock(T0 + timedelta(minutes=15))


@pytest.fixture
def state(tmp_path):
    s = StateStore(str(tmp_path / "state.sqlite"), bot="learner")
    yield s
    try:
        s.close()
    except Exception:
        pass


@pytest.fixture
def broker(clock):
    return FakeBroker(clock=clock)


def mk_om(state, broker, clock, **kw) -> OrderManager:
    return OrderManager("learner", broker, state, clock, rules_fn, **kw)


def mkpos(**kw) -> Position:
    d = dict(trade_id=1, bot="learner", pair=PAIR, side="long", setup="T1", status="open", decision_id=1,
             signal_bar_close_ts=T0, entry_ts=T0 + timedelta(minutes=15), entry_bar_open=T0, entry_price=100.02,
             qty=6.369, leverage=3, initial_stop=98.0, current_stop=98.0, stop_seq=0, stop_client_id=None,
             planned_target=None, trail_atr=3.0, param_version_id=1, trigger_tf="1h", risk_amount=13.999062,
             margin=200.0, rh=None, rl=None, fee_entry=0.0, funding_paid=0.0, mfe_price=100.02, mae_price=100.02,
             exit_reason=None, exit_client_id=None, closed_ts=None)
    d.update(kw)
    return Position(**d)


def put_pos(state, pos: Position) -> Position:
    with state.tx():
        state.insert_position(pos)
    return state.get_position(pos.trade_id)


def mkintent(**kw) -> Intent:
    d = dict(kind="entry", bot="learner", pair=PAIR, side="long", signal_bar_close_ts=T0, setup="T1", qty=6.369,
             leverage=3, planned_entry=100.0, stop_price=98.0, target_price=None, reason="test", decision_id=1)
    d.update(kw)
    return Intent(**d)


def mkctx(highs, lows, atrs=None, regime=None, last_close=100.0, D=None):
    n = len(highs)
    return ExitContext(bar_close_ts=D or T0 + timedelta(hours=n), highs=np.array(highs, float),
                       lows=np.array(lows, float), atrs=np.array(atrs if atrs is not None else [1.0] * n, float),
                       regime_last=regime, last_close=last_close, n_closed=n)


def mkbar(h, l, ts=None, step=60, pair=PAIR):
    return MinuteBar(pair=pair, open_ts=ts or T0 + timedelta(minutes=15), step_s=step, last_o=(h + l) / 2, last_h=h,
                     last_l=l, last_c=(h + l) / 2, mark_o=None, mark_h=None, mark_l=None, mark_c=None)


def mkfill(cid="x", price=100.02, qty=6.369, side="buy", role="entry", reason="market", fee=0.0, ts=None):
    return Fill(client_id=cid, pair=PAIR, role=role, order_side=side, qty=qty, price=price, fee=fee,
                ts=ts or T0 + timedelta(minutes=15), reason=reason)


# ---------------------------------------------------------------------------------------------
# Client id
# ---------------------------------------------------------------------------------------------
def test_u04_client_id_handchecked_examples():
    D = datetime(2026, 12, 1, 9, 0, tzinfo=UTC)
    assert make_client_id("learner", "entry", PAIR, "long", D, 0) == "trLe-078ebfcdd4a5354100a0c4fe"
    assert make_client_id("learner", "stop", PAIR, "long", D, 0) == "trLs-922b299d97c813c28fdda499"
    assert make_client_id("learner", "stop", PAIR, "long", D, 1) == "trLs-aa09899007fc9705496b85e4"
    assert make_client_id("learner", "exit", PAIR, "long", D, 0) == "trLx-9de262c42db2e08b0098b1c6"
    assert make_client_id("learner", "target", PAIR, "long", D, 0) == "trLt-d6a7eb9d18daedc978d108c1"
    assert make_client_id("twin", "entry", PAIR, "long", D, 0) == "trTe-b299042c99b76bbc1d2e36be"


@pytest.mark.parametrize("role,letter", [("entry", "e"), ("stop", "s"), ("target", "t"), ("exit", "x")])
def test_u04_client_id_formula_and_charset(role, letter):
    D = datetime(2026, 12, 1, 9, 0, tzinfo=UTC)
    cid = make_client_id("learner", role, PAIR, "short", D, 3)
    digest = hashlib.sha1(f"learner|{PAIR}|short|2026-12-01T09:00:00Z|{letter}|3".encode()).hexdigest()[:24]
    assert cid == f"trL{letter}-{digest}"
    assert len(cid) == 29 and re.fullmatch(r"[A-Za-z0-9-]+", cid)


def test_u04_client_id_deterministic_and_distinct():
    D = datetime(2026, 12, 1, 9, 0, tzinfo=UTC)
    a = make_client_id("learner", "entry", PAIR, "long", D, 0)
    assert a == make_client_id("learner", "entry", PAIR, "long", D, 0)
    assert a != make_client_id("learner", "entry", PAIR, "long", D + timedelta(hours=1), 0)
    assert a != make_client_id("learner", "entry", PAIR, "short", D, 0)
    assert a != make_client_id("learner", "entry", "ETH/USDT", "long", D, 0)


# ---------------------------------------------------------------------------------------------
# submit_entry: gonderim protokolu
# ---------------------------------------------------------------------------------------------
def test_u04_submit_entry_happy_path(state, broker, clock):
    om = mk_om(state, broker, clock)
    seen = {}

    def hook(req):  # POST aninda pending satir COMMIT edilmis olmali
        row = state.get_order(req.client_id)
        seen["status"] = row.status if row else None

    broker.hooks["market_order"] = hook
    out = om.submit_entry(mkintent(), 1)
    assert out.ok and out.status == "filled"
    assert seen["status"] == "pending"
    cid = "trLe-078ebfcdd4a5354100a0c4fe"
    req = broker.reqs("market_order")[0]
    assert (req.client_id, req.role, req.order_side, req.qty, req.reduce_only) == (cid, "entry", "buy", 6.369, False)
    assert req.pair == PAIR
    assert state.get_order(cid).status == "filled"
    prep = [c for c in broker.calls if c[0] == "prepare"]
    assert prep and PAIR in prep[0][2] and 3 in prep[0][2]
    assert broker.names("prepare", "market_order") == ["prepare", "market_order"]


def test_u04_submit_entry_short_side_is_sell(state, broker, clock):
    om = mk_om(state, broker, clock)
    om.submit_entry(mkintent(side="short", stop_price=102.0), 1)
    assert broker.reqs("market_order")[0].order_side == "sell"


def test_u04_submit_entry_rejects_off_step_qty(state, broker, clock):
    om = mk_om(state, broker, clock)
    try:
        out = om.submit_entry(mkintent(qty=6.3695), 1)
        assert not out.ok
    except ValueError:
        pass
    assert broker.count("market_order") == 0


def test_u04_same_signal_bar_gives_same_id_no_double_entry(state, broker, clock):
    om = mk_om(state, broker, clock)
    o1 = om.submit_entry(mkintent(), 1)
    o2 = om.submit_entry(mkintent(), 1)
    assert o1.order.client_id == o2.order.client_id
    # ikinci gonderim borsada duplicate -> benimsenir; borsada tek emir
    assert len([o for o in broker.orders.values() if o.role == "entry"]) == 1
    assert o2.ok and o2.note == "duplicate_adopted"


def test_u04_duplicate_client_id_is_adopted(state, broker, clock):
    om = mk_om(state, broker, clock)
    cid = make_client_id("learner", "entry", PAIR, "long", T0, 0)
    broker._record(OrderRequest(cid, PAIR, "entry", "buy", 6.369, None, False, 3), True)
    out = om.submit_entry(mkintent(), 1)
    assert out.note == "duplicate_adopted" and out.ok
    assert state.get_order(cid).status == "filled"
    assert broker.count("market_order") == 1


def test_u04_rejected_entry_recorded(state, broker, clock):
    broker.script["market_order"].append("reject:insufficient_margin")
    out = mk_om(state, broker, clock).submit_entry(mkintent(), 1)
    assert not out.ok and out.status == "rejected"
    row = state.get_order(out.order.client_id)
    assert row.status == "rejected" and "insufficient_margin" in (row.detail or "")
    assert broker.count("market_order") == 1


# ---------------------------------------------------------------------------------------------
# Belirsizlik yolu ve yeniden gonderim kurali
# ---------------------------------------------------------------------------------------------
@pytest.mark.parametrize("style", ["unknown_not_executed", "unknown_result_not_executed"])
def test_u04_unknown_not_executed_resends_once_same_id(state, broker, clock, style):
    broker.script["market_order"].append(style)
    t0 = clock.now()
    out = mk_om(state, broker, clock).submit_entry(mkintent(), 1)
    assert out.ok and out.note == "resent_once"
    # sira: POST -> query(None) -> bekle -> query(None) -> ayni kimlikle tek yeniden POST
    assert broker.names("market_order", "query") == ["market_order", "query", "query", "market_order"]
    posts = broker.reqs("market_order")
    assert len(posts) == 2 and posts[0].client_id == posts[1].client_id
    assert (clock.now() - t0).total_seconds() >= 2.0
    row = state.get_order(out.order.client_id)
    assert row.attempts == 1 and row.status == "filled"
    assert len([o for o in broker.orders.values() if o.role == "entry"]) == 1


@pytest.mark.parametrize("style", ["unknown_executed", "unknown_result_executed"])
def test_u04_unknown_executed_adopted_no_resend(state, broker, clock, style):
    broker.script["market_order"].append(style)
    out = mk_om(state, broker, clock).submit_entry(mkintent(), 1)
    assert out.ok and out.note == "adopted_after_unknown"
    assert broker.count("market_order") == 1
    assert state.get_order(out.order.client_id).status == "filled"
    assert state.unresolved_orders() == []


def test_u04_one_no_order_query_is_not_enough(state, broker, clock):
    """Ilk query None, ikincisi emri bulur -> yeniden gonderim YOK."""
    broker.script["market_order"].append("unknown_executed")
    broker.query_script.extend(["none", "real"])
    out = mk_om(state, broker, clock).submit_entry(mkintent(), 1)
    assert broker.count("market_order") == 1
    assert out.ok and out.note == "adopted_after_unknown"
    assert broker.count("query") == 2


def test_u04_resend_also_unknown_becomes_failed_and_no_third_post(state, broker, clock):
    broker.script["market_order"].extend(["unknown_not_executed", "unknown_not_executed"])
    out = mk_om(state, broker, clock).submit_entry(mkintent(), 1)
    assert not out.ok and out.status == "failed"
    assert broker.count("market_order") == 2
    assert state.get_order(out.order.client_id).status == "failed"
    assert state.kv_get("entries_blocked_reason") == "order_unknown"


def test_u04_max_attempts_1_never_resends(state, broker, clock):
    broker.script["market_order"].append("unknown_not_executed")
    out = mk_om(state, broker, clock, max_attempts=1).submit_entry(mkintent(), 1)
    assert not out.ok and out.status == "failed"
    assert broker.count("market_order") == 1
    assert state.get_order(out.order.client_id).status == "failed"
    assert state.kv_get("entries_blocked_reason") == "order_unknown"


def test_u04_max_attempts_1_still_adopts_executed(state, broker, clock):
    broker.script["market_order"].append("unknown_executed")
    out = mk_om(state, broker, clock, max_attempts=1).submit_entry(mkintent(), 1)
    assert out.ok and out.note == "adopted_after_unknown" and broker.count("market_order") == 1


def test_u04_custom_grace_is_waited(state, broker, clock):
    broker.script["market_order"].append("unknown_not_executed")
    t0 = clock.now()
    mk_om(state, broker, clock, unknown_grace_s=7.0).submit_entry(mkintent(), 1)
    assert (clock.now() - t0).total_seconds() >= 7.0


def test_u04_failed_entry_does_not_leak_exception(state, broker, clock):
    broker.script["market_order"].append("unknown_not_executed")
    out = mk_om(state, broker, clock, max_attempts=1).submit_entry(mkintent(), 1)
    assert out.status == "failed" and out.note


def test_u04_crash_after_pending_before_post_sends_exactly_once(state, broker, clock):
    cid = make_client_id("learner", "entry", PAIR, "long", T0, 0)
    row = OrderRow(client_id=cid, pair=PAIR, role="entry", order_side="buy", qty=6.369, trigger_price=None,
                   reduce_only=False, status="pending", signal_bar_close_ts=T0, seq=0, attempts=0, trade_id=1,
                   broker_order_id=None, detail=None, created_ts=clock.now(), updated_ts=clock.now())
    with state.tx():
        state.insert_order(row)
    assert [r.client_id for r in state.unresolved_orders()] == [cid]
    outs = mk_om(state, broker, clock).resolve_unresolved()
    assert len(outs) == 1
    assert broker.names("query", "market_order")[0] == "query"
    assert broker.count("market_order") == 1
    assert broker.reqs("market_order")[0].client_id == cid
    assert state.unresolved_orders() == []


def test_u04_crash_after_post_query_finds_order_no_resend(state, broker, clock):
    cid = make_client_id("learner", "entry", PAIR, "long", T0, 0)
    row = OrderRow(client_id=cid, pair=PAIR, role="entry", order_side="buy", qty=6.369, trigger_price=None,
                   reduce_only=False, status="pending", signal_bar_close_ts=T0, seq=0, attempts=0, trade_id=1,
                   broker_order_id=None, detail=None, created_ts=clock.now(), updated_ts=clock.now())
    with state.tx():
        state.insert_order(row)
    broker._record(OrderRequest(cid, PAIR, "entry", "buy", 6.369, None, False, 3), True)
    mk_om(state, broker, clock).resolve_unresolved()
    assert broker.count("market_order") == 0
    assert state.get_order(cid).status == "filled"


def test_u04_never_two_posts_without_two_no_order_queries(state, broker, clock):
    """Pending satir icin yalniz TEK 'emir yok' sorgusu varsa (ikincisi bulur) gonderim olmaz."""
    cid = make_client_id("learner", "entry", PAIR, "long", T0, 0)
    row = OrderRow(client_id=cid, pair=PAIR, role="entry", order_side="buy", qty=6.369, trigger_price=None,
                   reduce_only=False, status="pending", signal_bar_close_ts=T0, seq=0, attempts=0, trade_id=1,
                   broker_order_id=None, detail=None, created_ts=clock.now(), updated_ts=clock.now())
    with state.tx():
        state.insert_order(row)
    broker._record(OrderRequest(cid, PAIR, "entry", "buy", 6.369, None, False, 3), True)
    broker.query_script.extend(["none", "real"])
    mk_om(state, broker, clock).resolve_unresolved()
    assert broker.count("market_order") == 0


# ---------------------------------------------------------------------------------------------
# submit_exit: kapisiz cikis, closing, stop korunur
# ---------------------------------------------------------------------------------------------
def test_u04_submit_exit_reduce_only_market_marks_closing(state, broker, clock):
    om = mk_om(state, broker, clock)
    pos = put_pos(state, mkpos(stop_client_id="trLs-aaaaaaaaaaaaaaaaaaaaaaaa"))
    D = T0 + timedelta(hours=5)
    out = om.submit_exit(pos, "target", D)
    assert out.ok
    req = broker.reqs("market_order")[0]
    cid = make_client_id("learner", "exit", PAIR, "long", D, 0)
    assert (req.client_id, req.role, req.order_side, req.qty, req.reduce_only) == (cid, "exit", "sell", pos.qty, True)
    p = state.get_position(1)
    assert p.status == "closing" and p.exit_client_id == cid
    assert p.exit_reason == "target"
    assert broker.count("cancel") == 0     # stop, cikis dolmadan iptal edilmez


def test_u04_submit_exit_short_is_buy(state, broker, clock):
    pos = put_pos(state, mkpos(side="short", initial_stop=102.0, current_stop=102.0, entry_price=100.0))
    mk_om(state, broker, clock).submit_exit(pos, "regime_flip", T0 + timedelta(hours=3))
    assert broker.reqs("market_order")[0].order_side == "buy"


def test_u04_exit_not_blocked_by_entry_block_flag(state, broker, clock):
    with state.tx():
        state.kv_set("entries_blocked_reason", "order_unknown")
    pos = put_pos(state, mkpos())
    out = mk_om(state, broker, clock).submit_exit(pos, "force_exit", T0 + timedelta(hours=2))
    assert out.ok and broker.count("market_order") == 1


def test_u04_exit_unknown_not_executed_resent_once_same_id(state, broker, clock):
    broker.script["market_order"].append("unknown_not_executed")
    pos = put_pos(state, mkpos())
    out = mk_om(state, broker, clock).submit_exit(pos, "time_stop", T0 + timedelta(hours=48))
    assert out.ok and out.note == "resent_once"
    a, b = broker.reqs("market_order")
    assert a.client_id == b.client_id and a.reduce_only and b.reduce_only


def test_u04_exit_failed_keeps_position_unclosed(state, broker, clock):
    broker.script["market_order"].append("unknown_not_executed")
    pos = put_pos(state, mkpos())
    out = mk_om(state, broker, clock, max_attempts=1).submit_exit(pos, "time_stop", T0 + timedelta(hours=48))
    assert not out.ok and out.status == "failed"
    assert state.get_position(1).status in ("open", "closing")
    assert broker.count("market_order") == 1


def test_u04_cancel_resting_cancels_stop_after_exit(state, broker, clock):
    om = mk_om(state, broker, clock)
    pos = put_pos(state, mkpos())
    om.place_initial_stop(pos)
    pos = state.get_position(1)
    om.cancel_resting(pos)
    assert broker.active_stops() == []


# ---------------------------------------------------------------------------------------------
# Koruyucu stop: giris -> hemen stop; basarisizsa kapat
# ---------------------------------------------------------------------------------------------
def test_u04_place_initial_stop_long_tight_rounding(state, broker, clock):
    pos = put_pos(state, mkpos(initial_stop=98.004, current_stop=98.004))
    out = mk_om(state, broker, clock).place_initial_stop(pos)
    assert out.ok
    req = broker.reqs("place_stop")[0]
    assert req.client_id == make_client_id("learner", "stop", PAIR, "long", T0, 0)
    assert (req.role, req.order_side, req.qty, req.reduce_only) == ("stop", "sell", pos.qty, True)
    assert req.trigger_price == pytest.approx(98.01)    # long: yukari (giris yonune) yuvarla
    assert state.get_position(1).stop_client_id == req.client_id


def test_u04_place_initial_stop_short_tight_rounding(state, broker, clock):
    pos = put_pos(state, mkpos(side="short", entry_price=100.0, initial_stop=101.996, current_stop=101.996))
    assert mk_om(state, broker, clock).place_initial_stop(pos).ok
    req = broker.reqs("place_stop")[0]
    assert req.order_side == "buy" and req.trigger_price == pytest.approx(101.99)


def test_u04_initial_stop_rejected_once_retries_with_seq1(state, broker, clock):
    broker.script["place_stop"].append("reject:invalid")
    pos = put_pos(state, mkpos())
    out = mk_om(state, broker, clock).place_initial_stop(pos)
    assert out.ok
    r0, r1 = broker.reqs("place_stop")
    assert r0.client_id == make_client_id("learner", "stop", PAIR, "long", T0, 0)
    assert r1.client_id == make_client_id("learner", "stop", PAIR, "long", T0, 1)
    assert broker.count("market_order") == 0


def test_u04_initial_stop_fails_twice_closes_position_immediately(state, broker, clock):
    broker.script["place_stop"].extend(["reject:invalid", "reject:invalid"])
    pos = put_pos(state, mkpos())
    out = mk_om(state, broker, clock).place_initial_stop(pos)
    assert not out.ok
    exits = [r for r in broker.reqs("market_order")]
    assert len(exits) == 1
    assert (exits[0].role, exits[0].reduce_only, exits[0].order_side, exits[0].qty) == ("exit", True, "sell", pos.qty)
    assert state.kv_get("entries_blocked_reason") == "stop_failed"
    assert state.get_position(1).exit_reason == "other"


# ---------------------------------------------------------------------------------------------
# replace_stop (§4.3 / ornek 9)
# ---------------------------------------------------------------------------------------------
def armed_pos(state, broker, clock, **kw):
    om = mk_om(state, broker, clock)
    pos = put_pos(state, mkpos(**kw))
    assert om.place_initial_stop(pos).ok
    return om, state.get_position(pos.trade_id)


def test_u04_replace_stop_order_new_before_old(state, broker, clock):
    om, pos = armed_pos(state, broker, clock)
    cid0 = pos.stop_client_id
    cid1 = make_client_id("learner", "stop", PAIR, "long", T0, 1)
    snap = {}

    def on_place(req):
        if req.client_id == cid1:
            p = state.get_position(1)
            snap["seq_at_post"] = p.stop_seq
            snap["stop_at_post"] = p.current_stop

    def on_cancel(cid):
        p = state.get_position(1)
        snap["cancel_cid"] = cid
        snap["cur_at_cancel"] = p.current_stop
        snap["cid_at_cancel"] = p.stop_client_id

    broker.hooks["place_stop"] = on_place
    broker.hooks["cancel"] = on_cancel
    out = om.replace_stop(pos, 99.5)
    assert out.ok
    assert snap["seq_at_post"] == 1 and snap["stop_at_post"] == pytest.approx(98.0)
    assert snap["cancel_cid"] == cid0 and snap["cur_at_cancel"] == pytest.approx(99.5)
    assert snap["cid_at_cancel"] == cid1
    seq = broker.names("place_stop", "cancel")
    assert seq == ["place_stop", "place_stop", "cancel"]     # [0]=ilk kurulum
    p = state.get_position(1)
    assert p.stop_seq == 1 and p.current_stop == pytest.approx(99.5) and p.stop_client_id == cid1
    assert [o.client_id for o in broker.active_stops()] == [cid1]
    last = broker.reqs("place_stop")[-1]
    assert last.trigger_price == pytest.approx(99.5) and last.reduce_only and last.qty == pos.qty


def test_u04_replace_stop_would_trigger_keeps_old(state, broker, clock):
    om, pos = armed_pos(state, broker, clock)
    broker.script["place_stop"].append("reject:would_trigger")
    n_cancel = broker.count("cancel")
    out = om.replace_stop(pos, 99.5)
    assert not out.ok and out.note == "would_trigger"
    assert state.get_position(1).current_stop == pytest.approx(98.0)
    assert broker.count("cancel") == n_cancel
    assert [o.client_id for o in broker.active_stops()] == [pos.stop_client_id]


def test_u04_replace_stop_other_reject_keeps_old_and_no_exception(state, broker, clock):
    om, pos = armed_pos(state, broker, clock)
    broker.script["place_stop"].append("reject:other_reason")
    out = om.replace_stop(pos, 99.5)
    assert not out.ok
    assert state.get_position(1).current_stop == pytest.approx(98.0)
    assert broker.count("cancel") == 0


@pytest.mark.parametrize("new", [97.0, 98.0])
def test_u04_replace_stop_never_loosens_long(state, broker, clock, new):
    om, pos = armed_pos(state, broker, clock)
    n = broker.count("place_stop")
    out = om.replace_stop(pos, new)
    assert out.ok and out.note == "not_tighter"
    assert broker.count("place_stop") == n and state.get_position(1).current_stop == pytest.approx(98.0)


@pytest.mark.parametrize("new", [103.0, 102.0])
def test_u04_replace_stop_never_loosens_short(state, broker, clock, new):
    om, pos = armed_pos(state, broker, clock, side="short", entry_price=100.0, initial_stop=102.0, current_stop=102.0)
    n = broker.count("place_stop")
    out = om.replace_stop(pos, new)
    assert out.ok and out.note == "not_tighter"
    assert broker.count("place_stop") == n


def test_u04_replace_stop_short_tightens_down(state, broker, clock):
    om, pos = armed_pos(state, broker, clock, side="short", entry_price=100.0, initial_stop=102.0, current_stop=102.0)
    assert om.replace_stop(pos, 100.5).ok
    p = state.get_position(1)
    assert p.current_stop == pytest.approx(100.5)
    assert broker.reqs("place_stop")[-1].order_side == "buy"


def test_u04_replace_stop_cancel_failure_is_harmless(state, broker, clock):
    om, pos = armed_pos(state, broker, clock)
    broker.cancel_raises = True
    out = om.replace_stop(pos, 99.5)
    assert out.ok and state.get_position(1).current_stop == pytest.approx(99.5)


def test_u04_replace_stop_sequence_ids_unique(state, broker, clock):
    om, pos = armed_pos(state, broker, clock)
    ids = {pos.stop_client_id}
    for new in (99.0, 99.5, 100.0):
        assert om.replace_stop(state.get_position(1), new).ok
        ids.add(state.get_position(1).stop_client_id)
    assert len(ids) == 4 and state.get_position(1).stop_seq == 3


def test_u04_replace_stop_tick_rounds_tight(state, broker, clock):
    om, pos = armed_pos(state, broker, clock)
    assert om.replace_stop(pos, 99.501).ok
    assert broker.reqs("place_stop")[-1].trigger_price == pytest.approx(99.51)


# ---------------------------------------------------------------------------------------------
# evaluate_exit: ornek A (T1 long) ve aynalar
# ---------------------------------------------------------------------------------------------
A_HIGHS = [101, 102.5, 103.0, 102.0]
A_LOWS = [99.5, 100.5, 101.5, 100.8]


def test_u04_trail_stop_value_example_a():
    pos = mkpos()
    exp = [(98.0, False), (99.5, True), (100.0, True), (100.0, True)]
    for k in range(1, 5):
        s, armed = trail_stop_value(pos, mkctx(A_HIGHS[:k], A_LOWS[:k]))
        assert s == pytest.approx(exp[k - 1][0]) and armed is exp[k - 1][1]


def test_u04_example_a_bar1_none_unarmed():
    d = evaluate_exit(mkpos(), mkctx(A_HIGHS[:1], A_LOWS[:1], last_close=100.5))
    assert d.kind == "none"


def test_u04_example_a_bar2_arms_after_1R_and_updates():
    # esik 100.02 + 2.02 = 102.04 ; hh=102.5 >= esik -> 102.5 - 3 = 99.5
    d = evaluate_exit(mkpos(), mkctx(A_HIGHS[:2], A_LOWS[:2], last_close=102.0))
    assert d.kind == "stop_update" and d.new_stop == pytest.approx(99.5)


def test_u04_not_armed_below_plus_1R():
    # hh = 102.03 < 102.04: iz suren stop devreye girmez
    d = evaluate_exit(mkpos(), mkctx([102.03], [99.0], last_close=101.0))
    assert d.kind == "none"
    s, armed = trail_stop_value(mkpos(), mkctx([102.03], [99.0]))
    assert armed is False and s == pytest.approx(98.0)


def test_u04_example_a_bar3_update_to_100():
    d = evaluate_exit(mkpos(current_stop=99.5), mkctx(A_HIGHS[:3], A_LOWS[:3], last_close=102.0))
    assert d.kind == "stop_update" and d.new_stop == pytest.approx(100.0)


def test_u04_example_a_bar4_none_when_already_at_stop():
    d = evaluate_exit(mkpos(current_stop=100.0), mkctx(A_HIGHS, A_LOWS, last_close=100.5))
    assert d.kind == "none"


def test_u04_example_a_bar4_trail_exit_when_price_through_stop():
    d = evaluate_exit(mkpos(current_stop=100.0), mkctx(A_HIGHS, A_LOWS, last_close=99.9))
    assert d.kind == "exit" and d.reason == "trail_stop" and d.planned_exit is None


def test_u04_trail_exit_at_exactly_stop_equals_close():
    d = evaluate_exit(mkpos(current_stop=100.0), mkctx(A_HIGHS, A_LOWS, last_close=100.0))
    assert d.kind == "exit" and d.reason == "trail_stop"


def test_u04_trail_ratchets_only_toward_price():
    """Fiyat dusse bile iz suren stop geri cekilmez; yol monoton."""
    highs = [101, 102.5, 103.0, 102.0, 101.0, 100.5]
    lows = [99.5, 100.5, 101.5, 100.8, 99.0, 98.5]
    path = [trail_stop_value(mkpos(), mkctx(highs[:k], lows[:k]))[0] for k in range(1, 7)]
    assert path == sorted(path) and path[-1] == pytest.approx(100.0)


def test_u04_trail_short_mirror():
    pos = mkpos(side="short", entry_price=100.0, initial_stop=102.0, current_stop=102.0)
    highs, lows = [101.0, 100.5, 99.0], [99.0, 97.5, 97.0]
    s1, a1 = trail_stop_value(pos, mkctx(highs[:1], lows[:1]))
    assert (s1, a1) == (pytest.approx(102.0), False)
    # esik 100 - 2 = 98 ; ll = 97.5 -> 97.5 + 3 = 100.5
    s2, a2 = trail_stop_value(pos, mkctx(highs[:2], lows[:2]))
    assert s2 == pytest.approx(100.5) and a2
    d = evaluate_exit(pos, mkctx(highs[:2], lows[:2], last_close=99.0))
    assert d.kind == "stop_update" and d.new_stop == pytest.approx(100.5)
    d = evaluate_exit(mkpos(side="short", entry_price=100.0, initial_stop=102.0, current_stop=100.5),
                      mkctx(highs[:2], lows[:2], last_close=100.8))
    assert d.kind == "exit" and d.reason == "trail_stop"


def test_u04_regime_flip_long_only_on_trend_down():
    pos = mkpos()
    ex = evaluate_exit(pos, mkctx([101], [99.5], regime="trend_down", last_close=100.5))
    assert ex.kind == "exit" and ex.reason == "regime_flip" and ex.planned_exit is None
    for r in ("range", "volatile", "unclear", "trend_up", None):
        assert evaluate_exit(pos, mkctx([101], [99.5], regime=r, last_close=100.5)).kind == "none"


def test_u04_regime_flip_short_only_on_trend_up():
    pos = mkpos(side="short", entry_price=100.0, initial_stop=102.0, current_stop=102.0)
    assert evaluate_exit(pos, mkctx([100.5], [99.0], regime="trend_up", last_close=99.5)).reason == "regime_flip"
    assert evaluate_exit(pos, mkctx([100.5], [99.0], regime="trend_down", last_close=99.5)).kind == "none"


def test_u04_t1_regime_flip_beats_trail_exit():
    d = evaluate_exit(mkpos(current_stop=100.0), mkctx(A_HIGHS, A_LOWS, regime="trend_down", last_close=99.9))
    assert d.kind == "exit" and d.reason == "regime_flip"


def test_u04_t1_has_no_time_stop_or_target():
    d = evaluate_exit(mkpos(planned_target=101.0), mkctx([100.0] * 60, [99.5] * 60, last_close=100.0))
    assert d.kind == "none"


# -- R1: hedef / zaman durdurma ----------------------------------------------------------------
def r1(**kw):
    return mkpos(setup="R1", planned_target=104.0, trail_atr=3.0, **kw)


def test_u04_r1_target_reached_exit_with_planned_exit():
    d = evaluate_exit(r1(), mkctx([101, 102, 104.2], [99.5, 100, 101], last_close=103.0))
    assert d.kind == "exit" and d.reason == "target" and d.planned_exit == pytest.approx(104.0)


def test_u04_r1_target_hit_on_earlier_bar_still_exits():
    d = evaluate_exit(r1(), mkctx([104.0, 101, 101], [99.5, 100, 100], last_close=100.5))
    assert d.reason == "target"


def test_u04_r1_target_exact_touch_counts():
    assert evaluate_exit(r1(), mkctx([104.0], [100.0], last_close=102.0)).reason == "target"


def test_u04_r1_time_stop_at_48_not_47():
    h = [101.0] * 48
    l = [99.5] * 48
    d = evaluate_exit(r1(), mkctx(h, l, last_close=100.5))
    assert d.kind == "exit" and d.reason == "time_stop" and d.planned_exit is None
    assert evaluate_exit(r1(), mkctx(h[:47], l[:47], last_close=100.5)).kind == "none"


def test_u04_r1_target_precedes_time_stop():
    h = [101.0] * 47 + [104.5]
    d = evaluate_exit(r1(), mkctx(h, [99.5] * 48, last_close=100.5))
    assert d.reason == "target" and d.planned_exit == pytest.approx(104.0)


def test_u04_r1_ignores_regime_flip_and_trail():
    d = evaluate_exit(r1(), mkctx([103.0] * 5, [99.5] * 5, regime="trend_down", last_close=100.0))
    assert d.kind == "none"


def test_u04_r1_short_target_mirror():
    pos = mkpos(side="short", setup="R1", entry_price=100.0, initial_stop=102.0, current_stop=102.0,
                planned_target=96.0)
    assert evaluate_exit(pos, mkctx([100.5, 99], [98, 95.9], last_close=97)).reason == "target"
    assert evaluate_exit(pos, mkctx([100.5] * 48, [98] * 48, last_close=99)).reason == "time_stop"


def test_u04_time_stop_counts_trigger_tf_bars_not_15m_units():
    """1s tetik tf'de 48 bar = 192 adet 15 dk; zaman durdurma n_closed (tetik tf) sayar."""
    pos = r1(trigger_tf="1h")
    assert evaluate_exit(pos, mkctx([101.0] * 12, [99.5] * 12, last_close=100.5)).kind == "none"   # 12 x 1h = 48 x 15m
    assert evaluate_exit(pos, mkctx([101.0] * 48, [99.5] * 48, last_close=100.5)).reason == "time_stop"


# -- fail-closed / saflik ----------------------------------------------------------------------
def test_u04_missing_ctx_is_force_exit():
    d = evaluate_exit(mkpos(), None)
    assert d.kind == "exit" and d.reason == "force_exit"


def test_u04_missing_exit_data_is_force_exit():
    ctx = mkctx([101], [99.5])
    assert evaluate_exit(mkpos(initial_stop=float("nan")), ctx).reason == "force_exit"
    assert evaluate_exit(mkpos(entry_bar_open=None), ctx).reason == "force_exit"
    assert evaluate_exit(mkpos(initial_stop=float("inf")), ctx).reason == "force_exit"


def test_u04_n_closed_zero_is_none():
    ctx = ExitContext(bar_close_ts=T0, highs=np.array([]), lows=np.array([]), atrs=np.array([]), regime_last="trend_down",
                      last_close=100.0, n_closed=0)
    assert evaluate_exit(mkpos(), ctx).kind == "none"
    assert evaluate_exit(r1(), ctx).kind == "none"


def test_u04_evaluate_exit_is_pure():
    pos, ctx = mkpos(current_stop=99.0), mkctx(A_HIGHS, A_LOWS, last_close=102.0)
    assert evaluate_exit(pos, ctx) == evaluate_exit(pos, ctx)
    snap = (ctx.highs.copy(), ctx.lows.copy())
    evaluate_exit(pos, ctx)
    assert np.array_equal(ctx.highs, snap[0]) and np.array_equal(ctx.lows, snap[1])


def test_u04_frozen_trail_atr_is_used_not_global():
    p3 = mkpos(trail_atr=3.0)
    p1 = mkpos(trail_atr=1.0)
    c = mkctx(A_HIGHS[:2], A_LOWS[:2])
    assert trail_stop_value(p3, c)[0] == pytest.approx(99.5)
    assert trail_stop_value(p1, c)[0] == pytest.approx(101.5)


def test_u04_evaluate_exit_independent_of_state_flags(state):
    """Cikis karari yalniz (pos, ctx)'e baglidir: kapi/kill bayraklari etkilemez."""
    with state.tx():
        state.kv_set("entries_blocked_reason", "stop_failed")
    d = evaluate_exit(r1(), mkctx([101] * 48, [99.5] * 48, last_close=100.5))
    assert d.reason == "time_stop"


# ---------------------------------------------------------------------------------------------
# Dolum / cikis dolumu / MFE-MAE / ledger yuku
# ---------------------------------------------------------------------------------------------
def test_u04_exit_reason_for_stop_fill():
    assert exit_reason_for_stop_fill(mkpos(current_stop=98.0, initial_stop=98.0)) == "stop"
    assert exit_reason_for_stop_fill(mkpos(current_stop=100.0, initial_stop=98.0)) == "trail_stop"


def test_u04_update_excursion_long_and_short():
    p = mkpos(mfe_price=100.5, mae_price=99.5)
    q = update_excursion(p, mkbar(101.2, 99.9))
    assert (q.mfe_price, q.mae_price) == (101.2, 99.5)
    q = update_excursion(q, mkbar(100.0, 99.0))
    assert (q.mfe_price, q.mae_price) == (101.2, 99.0)
    s = mkpos(side="short", entry_price=100.0, initial_stop=102.0, current_stop=102.0, mfe_price=99.5, mae_price=100.5)
    s2 = update_excursion(s, mkbar(100.8, 99.2))
    assert (s2.mfe_price, s2.mae_price) == (99.2, 100.8)


def test_u04_apply_entry_fill_opens_position():
    opening = mkpos(status="opening", entry_ts=None, entry_bar_open=None, entry_price=None, qty=None,
                    mfe_price=None, mae_price=None)
    ts = datetime(2026, 12, 1, 9, 15, tzinfo=UTC)
    bar = mkbar(100.40, 99.60, ts=ts)
    p = apply_entry_fill(opening, mkfill(price=100.02, qty=6.369, fee=0.31, ts=ts), bar, ts)
    assert p.status == "open" and p.entry_ts == ts and p.entry_price == 100.02 and p.qty == 6.369
    assert p.fee_entry == pytest.approx(0.31)
    assert p.entry_bar_open == floor_tf(ts, "1h") == datetime(2026, 12, 1, 9, 0, tzinfo=UTC)
    assert p.mfe_price == pytest.approx(100.40) and p.mae_price == pytest.approx(99.60)   # giris dakikasi dahil


def test_u04_apply_entry_fill_excursion_includes_entry_price_when_bar_narrow():
    opening = mkpos(status="opening", entry_ts=None, entry_bar_open=None, entry_price=None, qty=None,
                    mfe_price=None, mae_price=None)
    ts = T0 + timedelta(minutes=15)
    p = apply_entry_fill(opening, mkfill(price=100.02, ts=ts), mkbar(100.01, 100.00, ts=ts), ts)
    assert p.mfe_price == pytest.approx(100.02) and p.mae_price == pytest.approx(100.00)


def test_u04_apply_funding_accumulates():
    p = mkpos(funding_paid=0.5)
    ev = BrokerEvent(kind="funding", ts=T0 + timedelta(hours=8), pair=PAIR, funding_paid=0.25, rate=0.0001, mark=100.0)
    assert apply_funding(p, ev).funding_paid == pytest.approx(0.75)


def closing_pos(**kw):
    return mkpos(status="closing", exit_reason=kw.pop("exit_reason", None), **kw)


def test_u04_example6_mfe_mae_extremes_and_ledger_math():
    pos = closing_pos(mfe_price=100.50, mae_price=98.20, exit_reason="time_stop")
    exit_ts = datetime(2026, 12, 1, 13, 30, tzinfo=UTC)
    fill = mkfill(price=97.95, side="sell", role="exit", reason="market", ts=exit_ts, fee=0.4)
    closed = apply_exit_fill(pos, fill, mkbar(100.80, 97.90, ts=exit_ts), exit_ts)
    assert closed.max_favorable_price == pytest.approx(100.80)
    assert closed.max_adverse_price == pytest.approx(97.90)
    assert closed.excursion_tf == "1m"
    assert closed.fee_exit == pytest.approx(0.4) and closed.exit_price == pytest.approx(97.95)
    # defter formulu (elle): mfe_r = 0.78*6.369/13.999062 = 0.3549 ; mae_r = 2.12*6.369/13.999062 = 0.9645
    mfe_r = max(0.0, (closed.max_favorable_price - 100.02) * 6.369 / 13.999062)
    mae_r = (100.02 - closed.max_adverse_price) * 6.369 / 13.999062
    assert mfe_r == pytest.approx(0.3549, abs=5e-5) and mae_r == pytest.approx(0.9645, abs=5e-5)


def test_u04_exit_fill_extends_extremes_with_realized_prices_long():
    pos = closing_pos(mfe_price=100.0, mae_price=99.0, exit_reason="regime_flip")   # entry 100.02 disinda
    closed = apply_exit_fill(pos, mkfill(price=98.5, side="sell", role="exit", ts=T0), mkbar(99.8, 99.0), T0)
    assert closed.max_favorable_price == pytest.approx(100.02)      # max(mfp, entry, exit)
    assert closed.max_adverse_price == pytest.approx(98.5)          # min(map, entry, exit)


def test_u04_exit_fill_extremes_short_mirror():
    pos = closing_pos(side="short", entry_price=100.0, initial_stop=102.0, current_stop=102.0, mfe_price=98.5,
                      mae_price=102.0, exit_reason="time_stop")
    closed = apply_exit_fill(pos, mkfill(price=102.5, side="buy", role="exit"), mkbar(102.4, 98.0), T0)
    assert closed.max_favorable_price == pytest.approx(98.0)
    assert closed.max_adverse_price == pytest.approx(102.5)


def test_u04_excursion_tf_15m_for_coarse_step():
    pos = closing_pos(exit_reason="time_stop")
    closed = apply_exit_fill(pos, mkfill(price=99.0, side="sell", role="exit"), mkbar(101, 98.5, step=900), T0)
    assert closed.excursion_tf == "15m"


def test_u04_nonpositive_extremes_all_none():
    pos = closing_pos(mfe_price=100.5, mae_price=-1.0, exit_reason="time_stop")
    closed = apply_exit_fill(pos, mkfill(price=99.0, side="sell", role="exit"), mkbar(101, 99.5), T0)
    assert closed.max_favorable_price is None and closed.max_adverse_price is None


def test_u04_exit_fill_stop_untrailed():
    closed = apply_exit_fill(closing_pos(current_stop=98.0, initial_stop=98.0),
                             mkfill(price=97.9, side="sell", role="stop", reason="stop"), mkbar(100, 97.8), T0)
    assert closed.exit_reason == "stop" and closed.planned_exit == pytest.approx(98.0)


def test_u04_exit_fill_stop_trailed():
    closed = apply_exit_fill(closing_pos(current_stop=100.0, initial_stop=98.0),
                             mkfill(price=99.95, side="sell", role="stop", reason="stop"), mkbar(100.5, 99.9), T0)
    assert closed.exit_reason == "trail_stop" and closed.planned_exit == pytest.approx(100.0)


def test_u04_exit_fill_market_uses_decided_reason():
    for r in ("time_stop", "regime_flip", "trail_stop", "force_exit", "manual", "other"):
        closed = apply_exit_fill(closing_pos(exit_reason=r), mkfill(price=99.0, side="sell", role="exit"),
                                 mkbar(100, 98.9), T0)
        assert closed.exit_reason == r and closed.planned_exit is None


def test_u04_exit_fill_market_target_planned_exit():
    pos = closing_pos(setup="R1", planned_target=104.0, exit_reason="target")
    closed = apply_exit_fill(pos, mkfill(price=104.1, side="sell", role="exit"), mkbar(104.2, 103.9), T0)
    assert closed.exit_reason == "target" and closed.planned_exit == pytest.approx(104.0)


def test_u04_exit_fill_liquidation():
    closed = apply_exit_fill(closing_pos(), mkfill(price=90.0, side="sell", role="exit", reason="liquidation"),
                             mkbar(100, 89.0), T0)
    assert closed.exit_reason == "liquidation" and closed.planned_exit is None


def test_u04_exit_fill_carries_funding_and_fee():
    closed = apply_exit_fill(closing_pos(funding_paid=0.37, exit_reason="time_stop"),
                             mkfill(price=99.0, side="sell", role="exit", fee=0.55), mkbar(100, 98.5), T0)
    assert closed.funding_paid == pytest.approx(0.37) and closed.fee_exit == pytest.approx(0.55)
    assert closed.trade_id == 1


def test_u04_all_exit_reasons_valid_for_ledger():
    reasons = {"stop", "trail_stop", "target", "time_stop", "regime_flip", "force_exit", "liquidation", "manual", "other"}
    assert reasons <= set(_EXIT_REASONS)
    for fr, pos_kw in [("stop", {}), ("liquidation", {}), ("market", {"exit_reason": "force_exit"})]:
        c = apply_exit_fill(closing_pos(**pos_kw), mkfill(price=99.0, side="sell", role="exit", reason=fr),
                            mkbar(100, 98.5), T0)
        assert c.exit_reason in _EXIT_REASONS


def ledger_bars_held(entry_ts: datetime, exit_ts: datetime) -> int:
    """Defter formulu: 15 dk birimi, taban farki (ledger._write_exit)."""
    return int(exit_ts.timestamp() // 900) - int(entry_ts.timestamp() // 900)


def test_u04_trade_exit_payload_and_bars_held_units():
    pos = closing_pos(mfe_price=100.50, mae_price=98.20, exit_reason="time_stop")
    exit_ts = datetime(2026, 12, 1, 13, 30, tzinfo=UTC)
    closed = apply_exit_fill(pos, mkfill(price=97.95, side="sell", role="exit", ts=exit_ts, fee=0.4),
                             mkbar(100.80, 97.90, ts=exit_ts), exit_ts)
    d = build_trade_exit(pos, closed, "1m")
    assert d["trade_id"] == 1 and d["exit_reason"] == "time_stop" and d["planned_exit"] is None
    assert d["exit_price"] == pytest.approx(97.95) and d["fee_exit"] == pytest.approx(0.4)
    assert d["max_favorable_price"] == pytest.approx(100.80) and d["max_adverse_price"] == pytest.approx(97.90)
    assert d["excursion_tf"] == "1m"
    assert as_dt(d["exit_ts"]) == exit_ts
    # 09:15 -> 13:30 = 17 adet 15 dk; tetik tf (1s) bar sayisi ise 4 bar kapanisi (10,11,12,13) -- ikisi farkli birim
    assert ledger_bars_held(pos.entry_ts, as_dt(d["exit_ts"])) == 17
    assert (as_dt(d["exit_ts"]) - pos.entry_ts) // timedelta(hours=1) == 4
    # uclu ledger dogrulamasindan gecer: mfp >= max(entry, exit), map <= min(entry, exit)
    assert d["max_favorable_price"] >= max(100.02, 97.95) and d["max_adverse_price"] <= min(100.02, 97.95)
    fields = {f.name for f in dataclasses.fields(TradeExit)}
    assert set(d) <= fields
    TradeExit(**{**d, "exit_ts": as_dt(d["exit_ts"])})   # ledger veri sinifina birebir oturur


def test_u04_trade_entry_payload():
    pos = mkpos(fee_entry=0.31)
    d = build_trade_entry(pos)
    assert d["trade_id"] == 1 and d["decision_id"] == 1 and d["entry_price"] == pytest.approx(100.02)
    assert d["qty"] == pytest.approx(6.369) and d["leverage"] == 3 and d["fee_entry"] == pytest.approx(0.31)
    assert as_dt(d["entry_ts"]) == pos.entry_ts
    assert set(d) <= {f.name for f in dataclasses.fields(TradeEntry)}
    TradeEntry(**{**d, "entry_ts": as_dt(d["entry_ts"])})


# ---------------------------------------------------------------------------------------------
# state: ledger kuyrugu, benzersizlik, tx, kalicilik
# ---------------------------------------------------------------------------------------------
class FakeLedger:
    def __init__(self, fail_on=None):
        self.calls = []
        self.fail_on = fail_on

    def record_trade_entry(self, e):
        self.calls.append(("entry", e))
        if self.fail_on == len(self.calls):
            raise LedgerError("yazilamadi")
        return len(self.calls)

    def record_trade_exit(self, x):
        self.calls.append(("exit", x))
        if self.fail_on == len(self.calls):
            raise LedgerError("yazilamadi")
        return len(self.calls)


def _n(x):
    return len(x) if hasattr(x, "__len__") else x


ENTRY_PAYLOAD = dict(trade_id=1, decision_id=7, entry_ts="2026-12-01T09:15:00Z", entry_price=100.02, qty=6.369,
                     leverage=3, fee_entry=0.31, supersedes_id=None)
EXIT_PAYLOAD = dict(trade_id=1, exit_ts="2026-12-01T13:30:00Z", exit_price=97.95, exit_reason="time_stop",
                    planned_exit=None, fee_exit=0.4, funding_paid=0.0, supersedes_id=None,
                    max_favorable_price=100.8, max_adverse_price=97.9, excursion_tf="1m")


def test_u04_outbox_drain_writes_in_order_with_same_payload(state):
    with state.tx():
        state.outbox_add("entry", 1, ENTRY_PAYLOAD)
        state.outbox_add("exit", 1, EXIT_PAYLOAD)
    assert len(state.outbox_pending()) == 2
    led = FakeLedger()
    res = state.drain_outbox(led)
    assert [k for k, _ in led.calls] == ["entry", "exit"]
    e, x = led.calls[0][1], led.calls[1][1]
    assert isinstance(e, TradeEntry) and isinstance(x, TradeExit)
    assert (e.trade_id, e.decision_id, e.entry_price, e.qty, e.leverage, e.fee_entry) == (1, 7, 100.02, 6.369, 3, 0.31)
    assert as_dt(e.entry_ts) == datetime(2026, 12, 1, 9, 15, tzinfo=UTC)
    assert (x.exit_reason, x.max_favorable_price, x.max_adverse_price, x.excursion_tf) == ("time_stop", 100.8, 97.9, "1m")
    assert _n(res.written) == 2 and not res.failed
    assert state.outbox_pending() == []
    state.drain_outbox(led)           # tekrar: yeni yazim yok
    assert len(led.calls) == 2


def test_u04_outbox_drain_stops_at_ledger_error_keeps_rest(state):
    with state.tx():
        state.outbox_add("entry", 1, ENTRY_PAYLOAD)
        state.outbox_add("exit", 1, EXIT_PAYLOAD)
    led = FakeLedger(fail_on=1)
    res = state.drain_outbox(led)
    assert len(led.calls) == 1                  # durur
    assert len(state.outbox_pending()) == 2
    assert res.first_error is not None and _n(res.written) == 0
    led.fail_on = None
    state.drain_outbox(led)
    assert state.outbox_pending() == []
    assert [k for k, _ in led.calls] == ["entry", "entry", "exit"]


def test_u04_outbox_add_outside_tx_raises(state):
    with pytest.raises(StateError):
        state.outbox_add("entry", 1, ENTRY_PAYLOAD)


def test_u04_unique_live_position_per_pair(state):
    put_pos(state, mkpos(trade_id=1))
    with pytest.raises(Exception):
        put_pos(state, mkpos(trade_id=2, decision_id=2))
    assert len(state.open_positions()) == 1 and state.position_for_pair(PAIR).trade_id == 1
    with state.tx():
        state.update_position(1, status="closed")
    put_pos(state, mkpos(trade_id=2, decision_id=2))      # kapaninca yenisi acilabilir
    assert state.position_for_pair(PAIR).trade_id == 2


def test_u04_tx_rollback_and_write_outside_tx(state):
    with pytest.raises(RuntimeError):
        with state.tx():
            state.insert_position(mkpos())
            raise RuntimeError("x")
    assert state.get_position(1) is None
    with pytest.raises(StateError):
        state.insert_position(mkpos())


def test_u04_mark_decided_once_and_cursor_monotone(state):
    with state.tx():
        assert state.mark_decided(PAIR, T0, "entered") is True
        assert state.mark_decided(PAIR, T0, "skipped") is False
        state.set_cursor(PAIR, "minute", T0)
    assert state.is_decided(PAIR, T0)
    with pytest.raises(StateError):
        with state.tx():
            state.set_cursor(PAIR, "minute", T0 - timedelta(minutes=1))
    assert state.get_cursor(PAIR, "minute") == T0


def test_u04_state_persists_across_reopen(tmp_path):
    path = str(tmp_path / "s.sqlite")
    s = StateStore(path, bot="learner")
    with s.tx():
        s.insert_position(mkpos())
        s.insert_order(OrderRow(client_id="trLe-aaaaaaaaaaaaaaaaaaaaaaaa", pair=PAIR, role="entry", order_side="buy",
                                qty=6.369, trigger_price=None, reduce_only=False, status="pending",
                                signal_bar_close_ts=T0, seq=0, attempts=0, trade_id=1, broker_order_id=None,
                                detail=None, created_ts=T0, updated_ts=T0))
        s.kv_set("entries_blocked_reason", "stop_failed")
    s.close()
    s2 = StateStore(path, bot="learner")
    try:
        assert s2.position_for_pair(PAIR).trade_id == 1
        assert [r.client_id for r in s2.unresolved_orders()] == ["trLe-aaaaaaaaaaaaaaaaaaaaaaaa"]
        assert s2.kv_get("entries_blocked_reason") == "stop_failed"
    finally:
        s2.close()


# ---------------------------------------------------------------------------------------------
# Ozellik testi: rastgele fiyat yollari uzerinde OrderManager + PositionManager
# ---------------------------------------------------------------------------------------------
def _run_path(seed: int, tmp_path):
    rng = random.Random(seed)
    clock = SimClock(T0)
    broker = FakeBroker(clock=clock)
    state = StateStore(str(tmp_path / f"p{seed}.sqlite"), bot="learner", durability="off")
    om = mk_om(state, broker, clock)
    n_bars = 160
    p = 100.0
    bars = []
    for i in range(n_bars):
        o = round(p, 2)
        c = round(max(5.0, o * (1 + rng.gauss(0, 0.012))), 2)
        h = round(max(o, c) * (1 + abs(rng.gauss(0, 0.004))), 2)
        l = round(min(o, c) * (1 - abs(rng.gauss(0, 0.004))), 2)
        bars.append((T0 + timedelta(hours=i), o, h, l, c))
        p = c
    pos: Position | None = None
    hist: list[tuple[float, float, float]] = []      # E..j (h, l, atr)
    placed: list[float] = []                         # bu islemin borsaya konan stop tetikleri
    entries = stops_ok = 0

    def check_invariants(j_close, last_close, stage):
        live = state.open_positions()
        assert len(live) <= 1, "bir cifte birden fazla acik pozisyon"
        assert len([x for x in live if x.pair == PAIR]) <= 1
        if pos is None:
            assert broker.active_stops() == [], f"{stage}: pozisyon yokken stop kaldi"
            return
        cur = state.get_position(pos.trade_id)
        act = broker.active_stops()
        assert len(act) == 1, f"{stage}: acik pozisyonda tam bir aktif stop olmali ({len(act)})"
        assert act[0].client_id == cur.stop_client_id and act[0].reduce_only and act[0].qty == cur.qty
        if cur.side == "long":
            assert act[0].order_side == "sell" and act[0].trigger_price < last_close + TICK + 1e-9
            assert all(b >= a - 1e-9 for a, b in zip(placed, placed[1:])), "long stop gevsedi"
        else:
            assert act[0].order_side == "buy" and act[0].trigger_price > last_close - TICK - 1e-9
            assert all(b <= a + 1e-9 for a, b in zip(placed, placed[1:])), "short stop gevsedi"

    for j in range(1, n_bars - 1):
        t_open, o, h, l, c = bars[j]
        D = t_open
        clock.set_time(max(clock.now(), t_open))
        if pos is None and rng.random() < 0.18:
            side = rng.choice(["long", "short"])
            setup = rng.choice(["T1", "R1"])
            fill = o
            atr = max(0.5, fill * 0.012)
            dist = rng.uniform(0.6, 2.0) * atr
            init = round(fill - dist, 2) if side == "long" else round(fill + dist, 2)
            tgt = None
            if setup == "R1":
                tgt = round(fill + 2 * dist, 2) if side == "long" else round(fill - 2 * dist, 2)
            with state.tx():
                tid = state.next_trade_id()
                state.insert_position(mkpos(
                    trade_id=tid, side=side, setup=setup, status="opening", decision_id=tid, signal_bar_close_ts=D,
                    entry_ts=None, entry_bar_open=None, entry_price=None, qty=None, initial_stop=init,
                    current_stop=init, planned_target=tgt, trail_atr=3.0, mfe_price=None, mae_price=None))
            broker.price = fill
            intent = mkintent(side=side, setup=setup, qty=2.0, signal_bar_close_ts=D, planned_entry=fill,
                              stop_price=init, target_price=tgt)
            out = om.submit_entry(intent, tid)
            assert out.ok
            bar = MinuteBar(PAIR, t_open, 60, fill, min(h, fill * 1.0005) if False else fill, fill, fill,
                            None, None, None, None)
            f = Fill(out.order.client_id, PAIR, "entry", "buy" if side == "long" else "sell", 2.0, fill, 0.0,
                     t_open, "market")
            opened = apply_entry_fill(state.get_position(tid), f, bar, t_open)
            with state.tx():
                state.update_position(tid, **{x.name: getattr(opened, x.name) for x in dataclasses.fields(opened)
                                              if x.name != "trade_id"})
            entries += 1
            so = om.place_initial_stop(state.get_position(tid))
            assert so.ok, "her giris icin stop kurulmali"
            stops_ok += 1
            pos = state.get_position(tid)
            hist = []
            placed = [broker.reqs("place_stop")[-1].trigger_price]
            if pos.side == "long":
                assert placed[0] < fill
            else:
                assert placed[0] > fill
        if pos is not None:
            cur = state.get_position(pos.trade_id)
            hist.append((h, l, max(0.5, c * 0.012)))
            stop = cur.current_stop
            hit = (l <= stop) if cur.side == "long" else (h >= stop)
            if hit:                                          # borsa stopu tetiklendi (surucu simule eder)
                sid = cur.stop_client_id
                broker.orders[sid] = dataclasses.replace(broker.orders[sid], status="filled")
                fl = Fill(sid, PAIR, "stop", "sell" if cur.side == "long" else "buy", cur.qty, stop, 0.0,
                          t_open, "stop")
                closed = apply_exit_fill(cur, fl, MinuteBar(PAIR, t_open, 60, o, h, l, c, None, None, None, None), t_open)
                assert closed.exit_reason in ("stop", "trail_stop")
                with state.tx():
                    state.update_position(cur.trade_id, status="closed", exit_reason=closed.exit_reason,
                                          closed_ts=closed.exit_ts)
                pos = None
                check_invariants(None, c, "stop_hit")
                continue
            ctx = ExitContext(bar_close_ts=D + timedelta(hours=1), highs=np.array([x[0] for x in hist]),
                              lows=np.array([x[1] for x in hist]), atrs=np.array([x[2] for x in hist]),
                              regime_last=rng.choice([None, "range", "trend_up", "trend_down"]), last_close=c,
                              n_closed=len(hist))
            dec = evaluate_exit(cur, ctx)
            if dec.kind == "stop_update":
                before = cur.current_stop
                assert dec.new_stop is not None
                if cur.side == "long":
                    assert dec.new_stop > before and dec.new_stop < c + 1e-9
                else:
                    assert dec.new_stop < before and dec.new_stop > c - 1e-9
                r = om.replace_stop(cur, dec.new_stop)
                after = state.get_position(cur.trade_id).current_stop
                if cur.side == "long":
                    assert after >= before - 1e-9
                else:
                    assert after <= before + 1e-9
                if r.ok and r.note != "not_tighter":
                    placed.append(broker.reqs("place_stop")[-1].trigger_price)
            elif dec.kind == "exit":
                broker.price = c
                r = om.submit_exit(cur, dec.reason, ctx.bar_close_ts)
                assert r.ok
                fl = Fill(r.order.client_id, PAIR, "exit", "sell" if cur.side == "long" else "buy", cur.qty, c, 0.0,
                          ctx.bar_close_ts, "market")
                cl = state.get_position(cur.trade_id)
                closed = apply_exit_fill(cl, fl, MinuteBar(PAIR, t_open, 60, o, h, l, c, None, None, None, None),
                                         ctx.bar_close_ts)
                assert closed.exit_reason in _EXIT_REASONS
                om.cancel_resting(cl)
                with state.tx():
                    state.update_position(cur.trade_id, status="closed", exit_reason=closed.exit_reason,
                                          closed_ts=closed.exit_ts)
                pos = None
            check_invariants(None, c, "bar_end")
    state.close()
    return entries, stops_ok


@pytest.mark.parametrize("seed", [1, 2, 3, 7, 11, 42, 99, 2026])
def test_u04_property_random_paths(seed, tmp_path):
    entries, stops_ok = _run_path(seed, tmp_path)
    assert entries == stops_ok
    # yol anlamli olsun: ince ayarla yeterince giris uretir
    assert entries >= 1
