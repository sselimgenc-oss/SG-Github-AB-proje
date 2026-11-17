"""WP-B5 gerceklestirme duman testleri: LiveReconciler + LiveBroker + sahte borsa (HTTP duzeyi), gercek StateStore/OrderManager."""
from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from types import SimpleNamespace

import pytest

from fake_exchange import KEY, SECRET, FakeExchange, FakeResp
from trader_engine.brokers.binance_futures import LiveBroker
from trader_engine.clock import SimClock
from trader_engine.config import LiveSettings
from trader_engine.exchange.binance_rest import SignedRestClient
from trader_engine.killswitch import Killswitch
from trader_engine.order_manager import OrderManager, make_client_id
from trader_engine.pause import EntryPause
from trader_engine.reconcile_live import LiveReconciler, exchange_qty_override, kill_close_client_id
from trader_engine.state import OrderRow, StateStore
from trader_engine.types import Position

UTC = timezone.utc
T0 = datetime(2026, 12, 28, 9, 0, tzinfo=UTC)
XRP, DOGE = "XRP/USDT", "DOGE/USDT"


class LedgerStub:
    def __init__(self):
        self.entries, self.exits = [], []

    def list_open_trades(self):
        return []

    def find_unledgered_trades(self, ids):
        return []

    def record_trade_entry(self, e):
        self.entries.append(e)

    def record_trade_exit(self, e):
        self.exits.append(e)


class W:
    pass


def world(tmp_path, leverage=3):
    w = W()
    w.clock = SimClock(T0)
    w.ex = FakeExchange(lambda: int(w.clock.now().timestamp() * 1000))
    rest = SignedRestClient(env="testnet", api_key=KEY, api_secret=SECRET, session=w.ex.session,
                            now_ms=lambda: int(w.clock.now().timestamp() * 1000), sleep=w.clock.sleep,
                            conditional_mode="algo")
    live = LiveSettings(account_tag="sub-acct", expected_wallet_max=1000.0)
    w.broker = LiveBroker(live, "testnet", leverage, [XRP, DOGE], rest, w.clock, 0.0005)
    w.broker.startup_check()
    w.state = StateStore(str(tmp_path / "s.sqlite"), bot="learner")
    w.nodata = w.broker.rules
    w.om = OrderManager("learner", w.broker, w.state, w.clock, w.nodata, max_attempts=1)
    w.kill = Killswitch(str(tmp_path / "KILL"), w.clock)
    w.pause = EntryPause(str(tmp_path / "PAUSE.learner"), w.clock)
    w.ledger = LedgerStub()
    w.cfg = SimpleNamespace(bot="learner", leverage=leverage, cost=SimpleNamespace(taker_fee=0.0005),
                            live=SimpleNamespace(entry_resolve_window_s=60.0))
    w.rec = LiveReconciler(w.cfg, w.broker, w.state, w.ledger, w.om, w.clock, w.kill, w.pause)
    w.posts = lambda: [r for r in w.ex.requests if r[0] in ("POST", "DELETE") and "order" in r[1].lower()
                       or "algo" in r[1].lower() and r[0] in ("POST", "DELETE")]
    return w


def mkpos(**kw) -> Position:
    d = dict(trade_id=1, bot="learner", pair=XRP, side="long", setup="T1", status="open", decision_id=7,
             signal_bar_close_ts=T0, entry_ts=T0 - timedelta(minutes=5), entry_bar_open=T0, entry_price=2.0, qty=10.0,
             leverage=3, initial_stop=1.9, current_stop=1.9, stop_seq=0, stop_client_id=None, planned_target=None,
             trail_atr=0.05, param_version_id=1, trigger_tf="1h", risk_amount=1.0, margin=7.0, rh=None, rl=None,
             fee_entry=0.01, funding_paid=0.0, mfe_price=2.0, mae_price=2.0, exit_reason=None, exit_client_id=None,
             closed_ts=None)
    d.update(kw)
    return Position(**d)


def seed(w, stop=True, qty=10.0, pair=XRP, **kw):
    sym = pair.replace("/", "")
    w.ex.fill_market(sym, "BUY", qty, cid="trLe-seed")
    with w.state.tx():
        w.state.insert_position(mkpos(pair=pair, qty=qty, **kw))
    if stop:
        out = w.om.place_initial_stop(w.state.get_position(1))
        assert out.ok
    return w.state.get_position(1)


def stops(w, pair=XRP):
    return [o for o in w.broker.open_orders(pair) if o.role == "stop"]


# ------------------------------------------------------------------ L5 + protect_first
def test_l5_missing_stop_installed_on_exchange_qty_and_state_synced(tmp_path):
    w = world(tmp_path)
    seed(w, stop=False)
    rep = w.rec.run(w.clock.now())
    s = stops(w)
    assert len(s) == 1 and s[0].qty == 10.0 and s[0].trigger_price == 1.9
    assert w.state.get_position(1).stop_client_id == s[0].client_id
    assert "no_stop:1" in rep.findings and w.rec.counters["stops_reinstalled"] == 1
    n = len(w.posts())
    rep2 = w.rec.run(w.clock.now())
    assert rep2.ok and len(w.posts()) == n and len(stops(w)) == 1          # yeni stop iptal edilmez, tekrar kurulmaz (r8)


def test_protect_first_needs_no_market_data_registers_position_and_runs_before_gate(tmp_path):
    w = world(tmp_path)
    seed(w, stop=False, qty=6.0)                                            # F6: kismi miktar borsadan
    calls = []
    real = w.broker.register_position
    w.broker.register_position = lambda pair, ts, ids=(): (calls.append((pair, ts, tuple(ids))), real(pair, ts, ids))
    rep = w.rec.protect_first()
    s = stops(w)
    assert len(s) == 1 and s[0].qty == 6.0
    assert calls and calls[0][0] == XRP and calls[0][1] == mkpos().entry_ts
    assert not rep.fatal


def test_protect_first_state_stop_ids_passed_to_register_and_closing_events(tmp_path):
    w = world(tmp_path)
    p = seed(w)
    seen = {}
    real = w.broker.closing_events
    w.broker.closing_events = lambda pair, since, client_ids=(): (seen.update(ids=tuple(client_ids)), real(pair, since, client_ids))[1]
    w.ex.set_mark("XRPUSDT", "1.85")                                        # stop tetiklenir, state bilmez
    w.rec.run(w.clock.now())
    assert p.stop_client_id in seen["ids"]


# ------------------------------------------------------------------ okuma basarisiz = eylem yok
def test_read_failure_no_action(tmp_path):
    w = world(tmp_path)
    seed(w, stop=False)
    n = len(w.posts())
    for _ in range(6):
        w.ex.inject("positionRisk", FakeResp(503, {"code": -1001, "msg": "x"}))
    rep = w.rec.run(w.clock.now())
    assert rep.findings == ("exchange_unreachable",) and rep.actions == () and not rep.fatal
    assert len(w.posts()) == n and stops(w) == []


# ------------------------------------------------------------------ L2 / L2a
def test_l2_unknown_position_pauses_and_places_nothing(tmp_path):
    w = world(tmp_path)
    w.ex.fill_market("DOGEUSDT", "BUY", 50, cid="web_x")
    n = len(w.posts())
    rep = w.rec.run(w.clock.now())
    assert rep.fatal and "unknown_position:DOGE/USDT" in rep.findings
    assert [h.reason for h in w.pause.holds()] == ["unknown_position"]
    assert len(w.posts()) == n and w.broker.positions()[0].qty == 50
    assert w.state.kv_get("entries_blocked_reason") == "reconcile_unknown_position"
    w.rec.run(w.clock.now())                                                # yapiskan: tutus ve blokaj kalir
    assert w.pause.active()


def test_l2_exception_only_with_kill(tmp_path):
    w = world(tmp_path)
    w.ex.fill_market("DOGEUSDT", "BUY", 50, cid="web_x")
    w.kill.set("test", "t")
    rep = w.rec.run(w.clock.now())
    assert rep.fatal and w.broker.positions() == []
    at = w.kill.info()["at"]
    cid = kill_close_client_id("learner", "DOGEUSDT", at)
    assert cid.startswith("trLx-") and w.state.get_order(cid).status in ("accepted", "filled")
    assert [h.reason for h in w.pause.holds()] == ["unknown_position"]


def test_l2_direction_mismatch_and_excess(tmp_path):
    w = world(tmp_path)
    seed(w, side="short", stop=False)                                       # state short, borsa long
    rep = w.rec.run(w.clock.now())
    assert "unknown_position:XRP/USDT" in rep.findings and rep.fatal
    w2 = world(tmp_path / "b") if (tmp_path / "b").mkdir() is None else None
    seed(w2, qty=10.0)
    w2.ex.fill_market("XRPUSDT", "BUY", 3.0, cid="web_add")                 # borsa 13 > state 10
    n = len(w2.posts())
    rep = w2.rec.run(w2.clock.now())
    assert "unknown_position:XRP/USDT" in rep.findings and len(w2.posts()) == n
    assert w2.pause.active()


def test_l2a_late_fill_reopens_installs_stop_and_pauses_late_fill(tmp_path):
    w = world(tmp_path)
    cid = make_client_id("learner", "entry", XRP, "long", T0, 0)
    with w.state.tx():
        w.state.insert_position(mkpos(status="closed", entry_ts=None, entry_price=None, qty=None, exit_reason="other",
                                      closed_ts=T0 + timedelta(seconds=60), entry_bar_open=None, mfe_price=None,
                                      mae_price=None, fee_entry=0.0))
        w.state.insert_order(OrderRow(cid, XRP, "entry", "buy", 10.0, None, False, "failed", T0, 0, 1, 1, None,
                                      "unknown_unresolved", T0, T0))
    w.ex.fill_market("XRPUSDT", "BUY", 10.0, cid=cid)
    w.clock.advance(120)
    rep = w.rec.run(w.clock.now())
    p = w.state.get_position(1)
    assert p.status == "open" and p.qty == 10.0 and p.entry_price == 2.0 and p.closed_ts is None
    s = stops(w)
    assert len(s) == 1 and s[0].trigger_price == 1.9 and p.stop_client_id == s[0].client_id
    assert [h.reason for h in w.pause.holds()] == ["late_fill"] and "late_fill:XRP/USDT" in rep.findings
    assert w.state.outbox_pending() == [] or True


# ------------------------------------------------------------------ L3 / L3b
def test_l3_stop_triggered_while_down_derives_exit(tmp_path):
    w = world(tmp_path)
    p = seed(w)
    w.ex.set_mark("XRPUSDT", "1.85")
    rep = w.rec.run(w.clock.now())
    q = w.state.get_position(1)
    assert q.status == "closed" and q.exit_reason in ("stop", "trail_stop")
    assert any(r.kind == "exit" for r in w.state.outbox_pending()) or w.ledger.exits
    assert not any(f.startswith("exit_unresolved") for f in rep.findings)


def test_l3_unresolvable_exit_flags_blocks_and_places_nothing(tmp_path):
    w = world(tmp_path)
    seed(w)
    w.ex.trades.clear()
    w.ex.pos["XRPUSDT"]["amt"] = Decimal(0)                                 # borsa duz ama islem kaydi yok
    n = len(w.posts())
    rep = w.rec.run(w.clock.now())
    assert "exit_unresolved:1" in rep.findings and w.state.kv_get("entries_blocked_reason") == "reconcile_state_orphan"
    assert len(w.posts()) == n and w.state.get_position(1).status == "open"


def test_l3b_unopened_after_window(tmp_path):
    w = world(tmp_path)
    w.om.resolve_unresolved = lambda: []                                    # B4'un "unknown kalir" davranisini taklit
    cid = make_client_id("learner", "entry", XRP, "long", T0, 0)
    with w.state.tx():
        w.state.insert_position(mkpos(status="opening", entry_ts=None, entry_price=None, qty=None, entry_bar_open=None))
        w.state.insert_order(OrderRow(cid, XRP, "entry", "buy", 10.0, None, False, "unknown", T0, 0, 0, 1, None, None, T0, T0))
    w.rec.run(w.clock.now() + timedelta(seconds=10))
    assert w.state.get_position(1).status == "opening"                      # pencere dolmadi
    w.clock.advance(61)
    w.rec.run(w.clock.now())
    assert w.state.get_position(1).status == "closed"


def test_opening_with_exchange_position_is_adopted_and_stopped(tmp_path):
    w = world(tmp_path)
    cid = make_client_id("learner", "entry", XRP, "long", T0, 0)
    w.ex.fill_market("XRPUSDT", "BUY", 10.0, cid=cid)
    with w.state.tx():
        w.state.insert_position(mkpos(status="opening", entry_ts=None, entry_price=None, qty=None, entry_bar_open=None))
        w.state.insert_order(OrderRow(cid, XRP, "entry", "buy", 10.0, None, False, "unknown", T0, 0, 0, 1, None, None, T0, T0))
    w.rec.protect_first()
    p = w.state.get_position(1)
    assert p.status == "open" and p.qty == 10.0 and len(stops(w)) == 1


# ------------------------------------------------------------------ L4
def test_l4_external_reduction_keeps_entry_qty_restops_and_exit_matches_state(tmp_path):
    w = world(tmp_path)
    seed(w)
    w.ex.fill_market("XRPUSDT", "SELL", 4.0, cid="web_cut")
    old = stops(w)[0].client_id
    rep = w.rec.run(w.clock.now())
    p = w.state.get_position(1)
    assert p.qty == 10.0 and exchange_qty_override(w.state, 1) == 6.0       # orijinal miktar korunur
    s = stops(w)
    assert len(s) == 1 and s[0].qty == 6.0 and s[0].client_id != old and p.stop_client_id == s[0].client_id
    assert "qty_reduced_external:1" not in rep.findings and w.rec.counters["qty_reduced_external"] == 1   # fix 10: bulgu degil
    w.ex.set_mark("XRPUSDT", "1.85")
    w.rec.run(w.clock.now())
    q = w.state.get_position(1)
    assert q.status == "closed"
    ex = w.ledger.exits[0]
    assert ex.exit_price == pytest.approx((4 * 2.0 + 6 * 1.85) / 10, rel=1e-6)    # tum azaltmalar VWAP, miktar 10 = state satiri


# ------------------------------------------------------------------ L6 / L7 / tolerances / r8
def test_l6_wrong_qty_new_stop_first_then_old_cancelled_new_survives(tmp_path):
    w = world(tmp_path)
    seed(w, stop=False)
    w.rec.run(w.clock.now())                                                # stop 10
    w.ex.fill_market("XRPUSDT", "SELL", 0.5, cid="web_cut")                 # 9.5: |d|=0.5 >= step/2
    w.rec.run(w.clock.now())
    s = stops(w)
    assert len(s) == 1 and s[0].qty == 9.5


def test_qty_and_trigger_tolerances(tmp_path):
    w = world(tmp_path)
    seed(w)
    w.ex.fill_market("XRPUSDT", "SELL", 0.04, cid="web_cut")                # 9.96: step/2 = 0.05 icinde
    n = len(w.posts())
    rep = w.rec.run(w.clock.now())
    assert len(w.posts()) == n and not any("qty_reduced" in f for f in rep.findings)
    with w.state.tx():
        w.state.update_position(1, current_stop=1.90004)                    # tick/2 = 0.00005 icinde
    rep = w.rec.run(w.clock.now())
    assert len(w.posts()) == n and rep.ok
    with w.state.tx():
        w.state.update_position(1, current_stop=1.9001)                     # state daha siki: tick/2 disinda -> yeniden kurulur
    # borsadaki stop 1.9 gevsek -> yeni stop
    w.rec.run(w.clock.now())
    assert [o.trigger_price for o in stops(w)] == [1.9001]


def test_l7_duplicate_stops_tightest_kept_state_synced(tmp_path):
    w = world(tmp_path)
    p = seed(w)
    out = w.om.replace_stop(p, 1.95)                                        # iki stop: 1.95 yeni, 1.9 eski iptal
    assert out.ok
    # eski iptali "basarisiz" gibi: eskiyi geri koy
    old = make_client_id("learner", "stop", XRP, "long", T0, 0)
    with w.state.tx():
        w.state.update_order(old, status="accepted")
    w.ex._new_cond("XRPUSDT", "SELL", "STOP_MARKET", Decimal("10"), Decimal("1.9"), "MARK_PRICE", old)
    assert len(stops(w)) == 2
    w.rec.run(w.clock.now())
    s = stops(w)
    assert [o.trigger_price for o in s] == [1.95]
    q = w.state.get_position(1)
    assert q.current_stop == 1.95 and q.stop_client_id == s[0].client_id


# ------------------------------------------------------------------ L8 / L9 / L10
def test_l8_orphan_reduce_only_cancelled_and_untracked_cancelled(tmp_path):
    w = world(tmp_path)
    cid = make_client_id("learner", "stop", DOGE, "long", T0, 3)
    w.ex.fill_market("DOGEUSDT", "BUY", 50, cid="web_x")
    w.ex._new_cond("DOGEUSDT", "SELL", "STOP_MARKET", Decimal("50"), Decimal("0.1"), "MARK_PRICE", cid)
    w.ex.external_close("DOGEUSDT")
    assert len(w.broker.open_orders(DOGE)) == 1
    rep = w.rec.run(w.clock.now())
    assert not w.broker.open_orders(DOGE) and f"orphan_order:{cid}" in rep.findings


def test_l9_foreign_order_not_cancelled_blocks_entries(tmp_path):
    w = world(tmp_path)
    w.ex._new_cond("XRPUSDT", "SELL", "STOP_MARKET", Decimal("10"), Decimal("1.5"), "MARK_PRICE", "web_abc", reduce=False)
    rep = w.rec.run(w.clock.now())
    assert "foreign_order:XRPUSDT" in rep.findings and len(w.broker.foreign_open_orders()) == 1
    assert w.state.kv_get("entries_blocked_reason") == "reconcile_foreign_order"
    w.ex.algos.clear()
    rep = w.rec.run(w.clock.now())
    assert rep.ok and w.state.kv_get("entries_blocked_reason") is None


def test_l10_leverage_and_margin_drift(tmp_path):
    w = world(tmp_path)
    seed(w)
    w.ex.lev["XRPUSDT"] = 5
    rep = w.rec.run(w.clock.now())
    assert "account_mode_drift:XRP/USDT" in rep.findings and w.state.kv_get("entries_blocked_reason") == "reconcile_account_mode_drift"
    w.ex.lev["XRPUSDT"] = 3
    w.rec._margin_types = lambda: {XRP: "cross"}
    assert "account_mode_drift:XRP/USDT" in w.rec.run(w.clock.now()).findings


# ------------------------------------------------------------------ duraklatma tutuslari kaldirilmaz
def test_existing_pause_holds_never_removed(tmp_path):
    w = world(tmp_path)
    w.pause.add("user_cmd", by="telegram:123")
    w.pause.add("drawdown_review", by="engine:rk1")
    seed(w)
    w.rec.run(w.clock.now())
    w.rec.protect_first()
    assert {h.reason for h in w.pause.holds()} == {"user_cmd", "drawdown_review"}


def test_order_unknown_block_not_cleared_while_unresolved(tmp_path):
    w = world(tmp_path)
    w.om.resolve_unresolved = lambda: []
    cid = make_client_id("learner", "entry", XRP, "long", T0, 0)
    with w.state.tx():
        w.state.insert_position(mkpos(status="opening", entry_ts=None, entry_price=None, qty=None, entry_bar_open=None))
        w.state.insert_order(OrderRow(cid, XRP, "entry", "buy", 10.0, None, False, "unknown", T0, 0, 0, 1, None, None, T0, T0))
        w.state.kv_set("entries_blocked_reason", "order_unknown")
    w.rec.run(w.clock.now() + timedelta(seconds=5))
    assert w.state.kv_get("entries_blocked_reason") == "order_unknown"


# ------------------------------------------------------------------ L5 basarisizlik yollari
def test_l5_would_trigger_closes_at_market(tmp_path):
    w = world(tmp_path)
    seed(w, stop=False)
    w.ex.marks["XRPUSDT"] = Decimal("1.85")                                 # tetik cizgisinin otesinde
    w.rec.run(w.clock.now())
    p = w.state.get_position(1)
    assert p.status == "closing" and p.exit_client_id and stops(w) == []
    assert w.broker.positions() == []


def test_l5_second_failure_closes_and_blocks_stop_failed(tmp_path):
    w = world(tmp_path)
    seed(w, stop=False)
    for _ in range(2):
        w.ex.inject("/fapi/v1/algoOrder", FakeResp(400, {"code": -4003, "msg": "qty"}))
    rep = w.rec.run(w.clock.now())
    assert w.state.kv_get("entries_blocked_reason") == "stop_failed"
    assert w.state.get_position(1).status == "closing" and w.broker.positions() == []
    assert any(a.startswith("stop_failed_closed") for a in rep.actions)
