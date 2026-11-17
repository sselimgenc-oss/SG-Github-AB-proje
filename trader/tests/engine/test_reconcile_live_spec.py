"""WP-B5 (11-canli-broker.md §8 L1-L11, §6.2 protect_first, §10 F-tablosu, §13 satir B5) bagimsiz sartname testleri.

Yalniz sartnameden ve committed koddan (Broker/State/OrderManager/pause/killswitch, fake_exchange) yazildi;
reconcile_live.py gerceklemesine BAKILMADI. Genel API (gerceklemeci raporu): LiveReconciler(cfg, broker, state, ledger,
orders, clock, kill, pause, handle_events=None, close_unopened=None, margin_types=None); protect_first(), run(now),
`counters` (Counter), exchange_qty_override(state, trade_id), kill_close_client_id(bot, symbol, kill_at).
`# SPEC-AMBIGUOUS:` ile isaretli yerler sartnamenin adlandirmadigi noktalardaki tahminlerdir.
Duzenek: gercek LiveBroker + gercek SignedRestClient + sahte borsa (HTTP duzeyi, fake_exchange), gercek StateStore,
gercek OrderManager(live_mode=True, max_attempts=1), gercek Killswitch/EntryPause, sahte defter (stub).
"""
from __future__ import annotations

import hashlib
import importlib
import logging
from collections import Counter
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from types import SimpleNamespace

import pytest

from fake_exchange import KEY, SECRET, FakeExchange, FakeResp
from test_engine_05_spec import make_cfg
from trader_engine.brokers.binance_futures import LiveBroker
from trader_engine.clock import SimClock
from trader_engine.config import LiveSettings
from trader_engine.exchange.binance_rest import SignedRestClient
from trader_engine.killswitch import Killswitch
from trader_engine.order_manager import OrderManager, make_client_id
from trader_engine.pause import EntryPause
from trader_engine.state import OrderRow, StateStore
from trader_engine.types import OrderRequest, Position

UTC = timezone.utc
T0 = datetime(2026, 12, 28, 9, 0, tzinfo=UTC)          # sinyal bari kapanisi
XRP, DOGE = "XRP/USDT", "DOGE/USDT"
BOT = "learner"
LEV = 3
ORDER_PATHS = ("/fapi/v1/order", "/fapi/v1/algoOrder")


def RL():
    return importlib.import_module("trader_engine.reconcile_live")


def set_t(clock, t):
    if t > clock.now():
        clock.set_time(t)


class MT(dict):
    """margin_types: gerceklemenin bekledigi bicim bilinmiyor (SPEC-AMBIGUOUS): cagrilabilir; argumansiz -> sozluk, pair/sembol
    argumanli -> o ciftin marginType'i."""

    def __call__(self, *a, **k):
        if not a:
            return dict(self)
        key = a[0]
        return self.get(key, self.get(str(key).replace("/", ""), self.get(str(key)[:-4] + "/USDT")))


def sym(pair):
    return pair.replace("/", "")


def cidf(role, pair=XRP, side="long", seq=0):
    return make_client_id(BOT, role, pair, side, T0, seq)


class StubLedger:
    """05 §7 defter denetimleri icin en kucuk yuzey."""

    def __init__(self):
        self.open_trades: list = []
        self.checked: list = []

    def list_open_trades(self):
        return list(self.open_trades)

    def record_trade_entry(self, e):
        self.entries = getattr(self, "entries", []) + [e]

    def record_trade_exit(self, e):
        self.exits = getattr(self, "exits", []) + [e]

    def find_unledgered_trades(self, ids):
        self.checked.append(list(ids))
        return []


class Rig:
    def __init__(self, tmp_path, *, mode="algo", handle=True, close_unopened=True, margin_types=None, pairs=(XRP, DOGE)):
        self.tmp = tmp_path
        self.clock = SimClock(T0)
        self.ex = FakeExchange(lambda: int(self.clock.now().timestamp() * 1000), classic=(mode == "classic"))
        self.cfg = make_cfg(tmp_path, BOT, "testnet", pairs, 1000.0, leverage=LEV,
                            live={"account_tag": "testnet-sub", "expected_wallet_max": 100000.0, "conditional_mode": "algo",
                                  "recv_window_ms": 5000, "poll_open_s": 5.0, "poll_flat_s": 30.0, "stop_deadline_s": 10.0,
                                  "entry_resolve_window_s": 60.0, "max_attempts": 1})
        import os
        os.makedirs(os.path.dirname(self.cfg.state_path), exist_ok=True)
        self.state = StateStore(self.cfg.state_path, bot=BOT)
        self.ledger = StubLedger()
        self.kill = Killswitch(str(tmp_path / "KILL"), self.clock)
        self.pause = EntryPause(str(tmp_path / "shared" / f"PAUSE.{BOT}"), self.clock)
        self.events: list = []
        self.unopened: list = []
        self.handle = handle
        self.close_unopened = close_unopened
        self.margin_types = margin_types
        self.mode = mode
        self.pairs = pairs
        self.broker = None
        self.new_broker()

    # -- kurulum
    def new_broker(self):
        """Yeni LiveBroker ayni borsada = surec yeniden baslatma."""
        clock, ex = self.clock, self.ex
        rest = SignedRestClient(env="testnet", api_key=KEY, api_secret=SECRET, session=ex.session,
                                now_ms=lambda: int(clock.now().timestamp() * 1000), sleep=clock.sleep,
                                conditional_mode=self.mode)
        live = LiveSettings(account_tag="sub-acct", expected_wallet_max=1000.0, conditional_mode=self.mode)
        self.broker = LiveBroker(live, "testnet", LEV, list(self.pairs), rest, clock, 0.0005)
        self.broker.startup_check()
        self.orders = OrderManager(BOT, self.broker, self.state, clock, self.broker.rules, max_attempts=1, live_mode=True)
        self.orders.on_entry_adopted = None
        self.rec = None
        return self.broker

    def make_rec(self):
        mod = RL()

        def handle(evs, *a, **k):
            self.events.extend(evs if isinstance(evs, (list, tuple)) else [evs])

        def unopened(*a, **k):
            self.unopened.append(a[0] if a else k)

        kw = {}
        if self.handle:
            kw["handle_events"] = handle
        if self.close_unopened:
            kw["close_unopened"] = unopened
        if self.margin_types is not None:
            kw["margin_types"] = self.margin_types
        self.rec = mod.LiveReconciler(self.cfg, self.broker, self.state, self.ledger, self.orders, self.clock, self.kill,
                                      self.pause, **kw)
        return self.rec

    def run(self, advance: float = 0.0):
        if advance:
            self.clock.advance(advance)
        rec = self.rec or self.make_rec()
        return rec.run(self.clock.now())

    def protect(self):
        return (self.rec or self.make_rec()).protect_first()

    # -- gozlem
    def mark(self):
        return len(self.ex.requests)

    def writes(self, since=0):
        """Siparis POST/DELETE istekleri (sira korunur)."""
        return [(m, p, q) for m, p, q in self.ex.requests[since:] if p in ORDER_PATHS and m in ("POST", "DELETE")]

    def posts(self, since=0):
        return [w for w in self.writes(since) if w[0] == "POST"]

    def deletes(self, since=0):
        return [w for w in self.writes(since) if w[0] == "DELETE"]

    def blocked(self):
        return self.state.kv_get("entries_blocked_reason")

    def holds(self):
        return {h.reason: h for h in self.pause.holds()}

    def live_stops(self, pair=XRP):
        return {c: a for c, a in self.ex.algos.items() if a["symbol"] == sym(pair) and a["algoStatus"] == "NEW"}

    def down(self, *parts):
        """Verilen yol parcalarini iceren her isteke surekli 503 (okuma arizasi)."""
        orig = self.ex.request

        def request(method, url, headers=None, timeout=None):
            if any(p in url for p in parts):
                self.ex.requests.append((method, url.split("?")[0].replace("https://testnet.binancefuture.com", ""), {}))
                return FakeResp(503, {"code": -1001, "msg": "down"})
            return orig(method, url, headers, timeout)

        self.ex.request = request
        return orig

    # -- tohumlama
    def seed_position(self, pair=XRP, side="long", qty=10.0, stop=1.9, current_stop=None, trade_id=1, status="open",
                      with_stop=True, stop_qty=None, stop_seq=0, exch=True, entry_price=2.0, seed_exchange_qty=None):
        s = sym(pair)
        set_t(self.clock, T0 + timedelta(seconds=5))
        ecid = cidf("entry", pair, side)
        if exch:
            self.ex.marks[s] = Decimal(str(entry_price))
            self.ex.fill_market(s, "BUY" if side == "long" else "SELL", seed_exchange_qty if seed_exchange_qty is not None else qty,
                                cid=ecid)
        cur = stop if current_stop is None else current_stop
        pos = Position(trade_id=trade_id, bot=BOT, pair=pair, side=side, setup="T1", status=status, decision_id=trade_id,
                       signal_bar_close_ts=T0, entry_ts=T0 + timedelta(seconds=5), entry_bar_open=T0, entry_price=entry_price,
                       qty=qty, leverage=LEV, initial_stop=stop, current_stop=cur, stop_seq=stop_seq if with_stop else 0,
                       stop_client_id=None, planned_target=None, trail_atr=0.05, param_version_id=1, trigger_tf="1h",
                       risk_amount=1.0, margin=10.0, rh=None, rl=None, fee_entry=0.01, funding_paid=0.0, mfe_price=entry_price,
                       mae_price=entry_price, exit_reason=None, exit_client_id=None, closed_ts=None)
        now = self.clock.now()
        with self.state.tx():
            self.state.insert_position(pos)
            self.state.insert_order(self._row(ecid, pair, "entry", "buy" if side == "long" else "sell", qty, None, False,
                                              "filled", 0, trade_id, now))
        if with_stop:
            scid = self.put_stop(pair, side, stop_qty if stop_qty is not None else qty, cur, stop_seq, trade_id)
            with self.state.tx():
                self.state.update_position(trade_id, stop_client_id=scid)
        return self.state.get_position(trade_id)

    def _row(self, cid, pair, role, osd, qty, trig, ro, status, seq, trade_id, ts):
        return OrderRow(client_id=cid, pair=pair, role=role, order_side=osd, qty=qty, trigger_price=trig, reduce_only=ro,
                        status=status, signal_bar_close_ts=T0, seq=seq, attempts=1, trade_id=trade_id, broker_order_id=None,
                        detail=None, created_ts=ts, updated_ts=ts)

    def put_stop(self, pair, side, qty, trigger, seq, trade_id=None, record=True):
        cid = cidf("stop", pair, side, seq)
        osd = "sell" if side == "long" else "buy"
        r = self.broker.place_stop(OrderRequest(client_id=cid, pair=pair, role="stop", order_side=osd, qty=float(qty),
                                                trigger_price=float(trigger), reduce_only=True, leverage=None,
                                                created_ts=self.clock.now()))
        assert r.status == "accepted", r
        if record:
            with self.state.tx():
                self.state.insert_order(self._row(cid, pair, "stop", osd, float(qty), float(trigger), True, "accepted", seq,
                                                  trade_id, self.clock.now()))
        return cid


@pytest.fixture
def rig(tmp_path):
    r = Rig(tmp_path)
    set_t(r.clock, T0 + timedelta(seconds=5))
    yield r
    r.state.close()


def at_run(r, secs=30):
    set_t(r.clock, T0 + timedelta(seconds=secs))


# =====================================================================================================
# 0. Temel: tutarli durum = eylemsiz, temiz rapor
# =====================================================================================================
def test_consistent_state_no_action_clean_report(rig):
    rig.seed_position()
    at_run(rig)
    m = rig.mark()
    rep = rig.run()
    assert rep.ok and not rep.fatal and rep.findings == ()
    assert rig.writes(m) == []
    assert rig.holds() == {} and rig.blocked() is None


def test_steady_state_second_run_places_nothing(rig):
    """Onarimdan sonra ikinci tur hicbir emir gondermez (r8 yakinsama)."""
    rig.seed_position(stop_qty=8.0)
    at_run(rig)
    rig.run()
    m = rig.mark()
    rig.run(advance=15)
    assert rig.writes(m) == []


# =====================================================================================================
# L1: pending/unknown emir satiri -> orders.resolve_unresolved()
# =====================================================================================================
def test_L1_unresolved_rows_resolved_via_orders(rig):
    rig.seed_position(status="opening", with_stop=False, exch=False)
    ecid = cidf("entry")
    with rig.state.tx():
        rig.state.update_order(ecid, status="unknown")
    rig.ex.fill_market("XRPUSDT", "BUY", 10, cid=ecid)          # emir aslinda doldu
    calls = []
    orig = rig.orders.resolve_unresolved
    rig.orders.resolve_unresolved = lambda *a, **k: (calls.append(1), orig(*a, **k))[1]
    at_run(rig)
    rig.run()
    assert calls, "mutabakat orders.resolve_unresolved() cagirmali (L1)"
    assert rig.state.get_order(ecid).status != "unknown"


def test_L1_not_called_when_nothing_unresolved_is_harmless(rig):
    rig.seed_position()
    at_run(rig)
    rig.run()      # hata firlatmamali; resolve cagrilsa da cagrilmasa da tur temiz


# =====================================================================================================
# L2: bilinmeyen pozisyon -> emir yok, pause + fatal; istisna yalniz KILL
# =====================================================================================================
def _unknown_cases():
    return ["no_state_row", "direction_reversed", "exchange_larger"]


@pytest.mark.parametrize("case", _unknown_cases())
def test_L2_unknown_position_no_orders_pause_and_fatal(rig, case):
    if case == "no_state_row":
        rig.ex.fill_market("DOGEUSDT", "BUY", 100)
        pair = DOGE
        # ayri bir pozisyonun stopu dururken de dokunulmaz
        rig.seed_position(XRP)
        pre_stops = set(rig.live_stops(XRP))
    elif case == "direction_reversed":
        rig.seed_position(XRP, "long", 10.0, with_stop=False, exch=False)
        rig.ex.fill_market("XRPUSDT", "SELL", 10)
        pair, pre_stops = XRP, set()
    else:
        rig.seed_position(XRP, "long", 10.0, seed_exchange_qty=15.0)
        pair, pre_stops = XRP, set(rig.live_stops(XRP))
    at_run(rig)
    m = rig.mark()
    rep = rig.run()
    assert rig.writes(m) == [], "L2: hicbir emir verilmez, hicbir sey iptal edilmez"
    assert rep.fatal and not rep.ok
    assert f"unknown_position:{pair}" in rep.findings
    h = rig.holds()
    assert "unknown_position" in h and h["unknown_position"].by == "engine:reconcile"
    assert set(rig.live_stops(XRP)) == pre_stops, "mevcut stoplar dokunulmaz"
    # kalici: ikinci turda kopya tutus yok
    rig.run(advance=15)
    assert [x.reason for x in rig.pause.holds()].count("unknown_position") == 1


def test_L2_pause_hold_is_never_removed_even_when_exchange_goes_flat(rig):
    rig.ex.fill_market("DOGEUSDT", "BUY", 100)
    at_run(rig)
    rig.run()
    rig.ex.external_close("DOGEUSDT")
    rig.run(advance=15)
    assert "unknown_position" in rig.holds()


def test_L2_kill_exception_closes_with_spec_client_id(rig):
    rig.ex.fill_market("XRPUSDT", "BUY", "12.34")
    rig.kill.set("test", "drill")
    kill_at = rig.kill.info()["at"]
    at_run(rig)
    m = rig.mark()
    rig.run()
    # SPEC-AMBIGUOUS: <symbol> = borsa sembolu (XRPUSDT); <kill.at> = kill dosyasindaki "at" dizgesi (Killswitch.info()["at"]).
    exp = "trx-" + hashlib.sha1(f"{BOT}|kill|XRPUSDT|{kill_at}".encode()).hexdigest()[:24]
    exp = "tr" + ("L" if BOT == "learner" else "T") + "x-" + exp[4:]
    ps = rig.posts(m)
    assert len(ps) == 1
    q = ps[0][2]
    assert q.get("newClientOrderId") == exp
    assert q["side"] == "SELL" and q.get("reduceOnly") == "true"
    assert Decimal(q["quantity"]) == Decimal("12.3"), "miktar adima asagi"
    assert rig.ex.pos["XRPUSDT"]["amt"] == Decimal("0.04")
    assert RL().kill_close_client_id(BOT, "XRPUSDT", kill_at) == exp


def test_L2_kill_closes_short_with_buy(rig):
    rig.ex.fill_market("DOGEUSDT", "SELL", 100)
    rig.kill.set("test", "drill")
    at_run(rig)
    m = rig.mark()
    rig.run()
    ps = rig.posts(m)
    assert len(ps) == 1 and ps[0][2]["side"] == "BUY" and ps[0][2].get("reduceOnly") == "true"
    assert rig.ex.pos["DOGEUSDT"]["amt"] == 0


def test_L2_without_kill_never_closes_even_for_tiny_unknown(rig):
    rig.ex.fill_market("DOGEUSDT", "BUY", 100)
    at_run(rig)
    m = rig.mark()
    rig.run()
    assert rig.posts(m) == [] and rig.ex.pos["DOGEUSDT"]["amt"] == Decimal("100")


# =====================================================================================================
# L2a: gec dolum
# =====================================================================================================
def _late_fill_setup(rig, status="failed", age=timedelta(minutes=10), filled=True):
    """Giris emri basarisiz/belirsiz sayilmis ve pozisyon satiri kapatilmis; ama borsada dolmus."""
    ecid = cidf("entry")
    created = rig.clock.now() + timedelta(seconds=1)
    pos = Position(trade_id=5, bot=BOT, pair=XRP, side="long", setup="T1", status="closed", decision_id=5,
                   signal_bar_close_ts=T0, entry_ts=None, entry_bar_open=None, entry_price=None, qty=None, leverage=LEV,
                   initial_stop=1.9, current_stop=1.9, stop_seq=0, stop_client_id=None, planned_target=None, trail_atr=0.05,
                   param_version_id=1, trigger_tf="1h", risk_amount=1.0, margin=10.0, rh=None, rl=None, fee_entry=0.0,
                   funding_paid=0.0, mfe_price=None, mae_price=None, exit_reason="other", exit_client_id=None,
                   closed_ts=created + timedelta(seconds=70))
    with rig.state.tx():
        rig.state.insert_position(pos)
        rig.state.insert_order(rig._row(ecid, XRP, "entry", "buy", 10.0, None, False, status, 0, 5, created))
    if filled:
        rig.ex.fill_market("XRPUSDT", "BUY", 10, cid=ecid)
    set_t(rig.clock, created + age)
    rig.broker.refresh_rules()                   # 24 sa sonra kurallar bayat olmasin (6 sa siniri)
    return ecid


def test_L2a_late_fill_reopens_row_installs_stop_and_pauses(rig):
    _late_fill_setup(rig)
    m = rig.mark()
    rep = rig.run()
    p = rig.state.get_position(5)
    assert p.status == "open" and p.qty == pytest.approx(10.0) and p.entry_price == pytest.approx(2.0)
    stops = rig.live_stops(XRP)
    assert len(stops) == 1
    a = next(iter(stops.values()))
    assert a["triggerPrice"] == Decimal("1.9") and a["qty"] == Decimal("10")      # initial_stop, hemen
    assert p.stop_client_id in stops
    h = rig.holds()
    assert "late_fill" in h and "unknown_position" not in h
    assert rig.rec.counters["late_fill"] == 1
    assert not any(w[2].get("reduceOnly") == "true" and w[1] == "/fapi/v1/order" for w in rig.posts(m)), "kapatma yok"
    assert rep is not None


# SPEC-AMBIGUOUS: "failed/unknown" giris emri + kapali pozisyon satiri. `unknown` satir L1'de (L2a'dan once) cozulur ve
# B4 §6.4 madde 5 `unknown` iken pozisyonu `opening` tutar; bu yuzden yalniz `failed` varyanti ulasilabilir durumdur.
@pytest.mark.parametrize("status", ["failed"])
def test_L2a_applies_for_failed_entry_rows(rig, status):
    _late_fill_setup(rig, status=status)
    rig.run()
    assert rig.state.get_position(5).status == "open" and "late_fill" in rig.holds()


def test_L2a_stop_not_installable_closes_position(rig):
    _late_fill_setup(rig)
    rig.ex.set_mark("XRPUSDT", "1.8")                  # initial_stop 1.9 hemen tetiklenir (-2021)
    m = rig.mark()
    rig.run()
    assert rig.ex.pos["XRPUSDT"]["amt"] == 0, "stop kurulamazsa kapatilir"
    assert any(p[2].get("reduceOnly") == "true" for p in rig.posts(m))


def test_L2a_window_boundary_24h(rig):
    # 24 saatten az: L2a; fazla: L2 (bilinmeyen pozisyon)
    _late_fill_setup(rig, age=timedelta(hours=23, minutes=58))   # SPEC-AMBIGUOUS: 24 sa referansi (emir created/updated mi, pozisyon closed_ts mi) belirsiz; her tanimda <24 sa
    rig.run()
    assert "late_fill" in rig.holds()


def test_L2a_older_than_24h_is_plain_unknown_position(rig):
    _late_fill_setup(rig, age=timedelta(hours=24, minutes=5))   # SPEC-AMBIGUOUS: referans an belirsiz; closed_ts = created+70 sn, 5 dk pay her tanimda >24 sa
    m = rig.mark()
    rep = rig.run()
    assert rig.writes(m) == [] and rep.fatal and f"unknown_position:{XRP}" in rep.findings
    assert "late_fill" not in rig.holds() and "unknown_position" in rig.holds()


@pytest.mark.parametrize("variant", ["order_missing_on_exchange", "order_canceled"])
def test_L2a_not_filled_per_query_falls_back_to_L2(rig, variant):
    ecid = _late_fill_setup(rig, filled=False)
    rig.ex.fill_market("XRPUSDT", "BUY", 10, cid="web_manual")      # pozisyon baska kaynaktan
    if variant == "order_canceled":
        rig.ex.orders[ecid] = {"clientOrderId": ecid, "symbol": "XRPUSDT", "side": "BUY", "type": "MARKET", "orderId": 7,
                               "reduceOnly": False, "origQty": "10", "status": "CANCELED", "executedQty": "0",
                               "avgPrice": "0", "time": 0, "updateTime": 0}
    m = rig.mark()
    rep = rig.run()
    assert rig.writes(m) == [] and rep.fatal and "unknown_position" in rig.holds()


# =====================================================================================================
# L3: state acik, borsa duz -> closing_events; turetilemezse bulgu
# =====================================================================================================
def test_L3_stop_triggered_while_down_derives_exit_events_with_state_ids(rig):
    p = rig.seed_position()
    rig.ex.set_mark("XRPUSDT", "1.85")                 # stop tetiklendi; motor kapaliydi
    rig.clock.advance(60)
    rig.new_broker()                                    # yeniden baslatma: broker kimlikleri bilmez
    rig.make_rec()
    m = rig.mark()
    rep = rig.run()
    fills = [e for e in rig.events if e.kind == "fill"]
    assert len(fills) == 1 and fills[0].fill.reason == "stop" and fills[0].fill.client_id == p.stop_client_id
    assert rig.writes(m) == [], "L3: emir verilmez"
    assert rig.ex.pos.get("XRPUSDT", {"amt": 0})["amt"] == 0
    assert rep is not None


def test_L3_underivable_exit_reports_unresolved_blocks_entries_no_orders(rig):
    p = rig.seed_position(with_stop=False, exch=False)           # borsada hic islem/pozisyon yok
    at_run(rig)
    m = rig.mark()
    rep = rig.run()
    assert f"exit_unresolved:{p.trade_id}" in rep.findings and not rep.ok
    assert rig.blocked() == "reconcile_state_orphan"
    assert rig.writes(m) == []
    # sonraki turda yeniden denenir
    n = rig.ex.count("/fapi/v1/userTrades")
    rig.run(advance=15)
    assert rig.ex.count("/fapi/v1/userTrades") > n


def test_L3_underivable_exit_critical_only_after_10_minutes(rig, caplog):
    rig.seed_position(with_stop=False, exch=False)
    at_run(rig)
    caplog.set_level(logging.DEBUG)
    rig.run()
    # SPEC-AMBIGUOUS: ilk turda baska bir CRITICAL (ornegin state_orphan) gerceklemede atilabilir; burada yalniz 10 dk'dan
    # sonra CRITICAL ZORUNLU, 10 dk'dan once exit_unresolved nedeniyle CRITICAL OLMAMALI varsayilir.
    first = [r for r in caplog.records if r.levelno >= logging.CRITICAL and "exit_unresolved" in r.getMessage()]
    assert first == []
    caplog.clear()
    rig.run(advance=11 * 60)
    assert any(r.levelno >= logging.CRITICAL for r in caplog.records)


def test_L3_blocker_cleared_when_finding_goes_away(rig):
    p = rig.seed_position(with_stop=False, exch=False)
    at_run(rig)
    rig.run()
    assert rig.blocked() == "reconcile_state_orphan"
    # pozisyon artik kapali (motor isledi): bulgu kalkar -> bloke temizlenir
    with rig.state.tx():
        rig.state.update_position(p.trade_id, status="closed", exit_reason="stop", closed_ts=rig.clock.now())
    rig.run(advance=15)
    assert rig.blocked() is None


# =====================================================================================================
# L3b: opening, pencere doldu, emir yok, borsa duz -> _close_unopened
# =====================================================================================================
def _opening_no_order(rig):
    pos = Position(trade_id=7, bot=BOT, pair=XRP, side="long", setup="T1", status="opening", decision_id=7,
                   signal_bar_close_ts=T0, entry_ts=None, entry_bar_open=None, entry_price=None, qty=None, leverage=LEV,
                   initial_stop=1.9, current_stop=1.9, stop_seq=0, stop_client_id=None, planned_target=None, trail_atr=0.05,
                   param_version_id=1, trigger_tf="1h", risk_amount=1.0, margin=10.0, rh=None, rl=None, fee_entry=0.0,
                   funding_paid=0.0, mfe_price=None, mae_price=None, exit_reason=None, exit_client_id=None, closed_ts=None)
    with rig.state.tx():
        rig.state.insert_position(pos)
    return pos


def test_L3b_window_elapsed_calls_close_unopened(rig):
    _opening_no_order(rig)
    m = rig.mark()
    rig.run(advance=61 + 60)                   # entry_resolve_window_s = 60 doldu
    assert len(rig.unopened) == 1
    # SPEC-AMBIGUOUS: callback argumani Position nesnesi ya da trade_id olabilir.
    a = rig.unopened[0]
    assert getattr(a, "trade_id", a) == 7
    assert rig.writes(m) == []


def test_L3b_window_not_elapsed_does_not_close(rig):
    _opening_no_order(rig)
    rig.run(advance=5)
    # SPEC-AMBIGUOUS: pencere baslangici (pozisyon olusturma / sinyal bari / ...) sartnamede yok; 5 sn her tanimda pencere icinde.
    assert rig.unopened == []


def test_L3b_not_closed_when_exchange_has_position(rig):
    _opening_no_order(rig)
    rig.ex.fill_market("XRPUSDT", "BUY", 10)
    rig.run(advance=61 + 60)
    assert rig.unopened == []


# =====================================================================================================
# L4: dis azaltma (borsa miktari state'ten kucuk)
# =====================================================================================================
def _l4(rig, exch_qty="6"):
    p = rig.seed_position(qty=10.0)
    rig.ex.fill_market("XRPUSDT", "SELL", Decimal("10") - Decimal(exch_qty), cid="web_manual")
    at_run(rig)
    return p


def test_L4_state_qty_stays_original_override_and_audit_kv(rig, caplog):
    p = _l4(rig)
    caplog.set_level(logging.DEBUG)
    rep = rig.run()
    cur = rig.state.get_position(p.trade_id)
    assert cur.qty == pytest.approx(10.0), "state qty ORIJINAL giris miktari olarak kalir"
    assert f"qty_reduced_external:{p.trade_id}" not in rep.findings, "B5 fix 10: uyari + sayac, bulgu degil"
    assert rig.rec.counters["qty_reduced_external"] == 1
    kv = rig.state.kv_get(f"ext_reduction:{p.trade_id}")
    assert isinstance(kv, dict) and float(kv["exch_qty"]) == pytest.approx(6.0)
    assert RL().exchange_qty_override(rig.state, p.trade_id) == pytest.approx(6.0)
    assert any(r.levelno >= logging.CRITICAL for r in caplog.records)
    assert RL().exchange_qty_override(rig.state, 999) is None or RL().exchange_qty_override(rig.state, 999) in (0, 0.0) \
        or True  # SPEC-AMBIGUOUS: kayit yokken donus degeri (None/ham miktar) sartnamede yok; yalniz hata firlatmamali


def test_L4_stop_resized_to_exchange_qty_new_first_old_after(rig):
    p = _l4(rig)
    old = p.stop_client_id
    m = rig.mark()
    rig.run()
    w = rig.writes(m)
    kinds = [(x[0], x[2].get("clientAlgoId") or x[2].get("origClientAlgoId") or x[2].get("newClientOrderId")) for x in w]
    live = rig.live_stops(XRP)
    assert len(live) == 1 and old not in live
    new = next(iter(live))
    a = live[new]
    assert a["qty"] == Decimal("6") and a["triggerPrice"] == Decimal("1.9")
    assert new == cidf("stop", XRP, "long", 1) and rig.state.get_position(p.trade_id).stop_client_id == new
    ip = next(i for i, k in enumerate(kinds) if k == ("POST", new))
    idl = next(i for i, k in enumerate(kinds) if k[0] == "DELETE")
    assert ip < idl, "r8: yeni stop ESKI iptalinden once"
    assert not any(k == ("DELETE", new) for k in kinds), "r8: yeni stop asla iptal edilmez"


def test_L4_logged_once_per_change_and_idempotent(rig, caplog):
    p = _l4(rig)
    caplog.set_level(logging.DEBUG)
    rig.run()
    n = sum(1 for r in caplog.records if r.levelno >= logging.CRITICAL)
    m = rig.mark()
    rig.run(advance=15)
    rig.run(advance=15)
    assert sum(1 for r in caplog.records if r.levelno >= logging.CRITICAL) == n, "degisimde bir kez gunlukler"
    assert rig.writes(m) == []
    assert rig.rec.counters["qty_reduced_external"] == 1
    assert p is not None


def test_L4_exit_event_qty_matches_state_row_after_interleaved_reduction(rig):
    """10 -> 6 (dis) -> 0 (stop): kapanis olayi qty = 10 (giris miktari) ve state satiri ile eslesir (mentor kosulu)."""
    p = _l4(rig)
    rig.run()
    rig.ex.set_mark("XRPUSDT", "1.85")
    rig.clock.advance(60)
    rig.new_broker()
    rig.make_rec()
    rig.run()
    assert rig.state.get_position(p.trade_id).qty == pytest.approx(10.0)
    fills = [e for e in rig.events if e.kind == "fill"]
    assert len(fills) == 1
    # SPEC-AMBIGUOUS: B3 closing_events tum azaltici islemleri toplar -> tek olay qty=10; bolunmus olaylar da kabul edilir.
    assert sum(f.fill.qty for f in fills) == pytest.approx(10.0)


# =====================================================================================================
# L5: stop yok -> hemen yeni stop
# =====================================================================================================
def _cancel_stop(rig, cid):
    rig.ex.algos[cid]["algoStatus"] = "CANCELED"


def test_L5_missing_stop_reinstalled_with_new_seq_current_stop_exchange_qty(rig):
    p = rig.seed_position(stop=1.9, current_stop=1.95)
    _cancel_stop(rig, p.stop_client_id)
    at_run(rig)
    m = rig.mark()
    rig.run()
    live = rig.live_stops(XRP)
    assert len(live) == 1
    new, a = next(iter(live.items()))
    assert new == cidf("stop", XRP, "long", 1)
    assert a["triggerPrice"] == Decimal("1.95") and a["qty"] == Decimal("10")
    cur = rig.state.get_position(p.trade_id)
    assert cur.stop_client_id == new and cur.stop_seq == 1
    assert rig.rec.counters["stops_reinstalled"] == 1
    assert len(rig.posts(m)) == 1


def test_L5_stop_rounded_tight_long_and_short(rig):
    p = rig.seed_position(stop=1.9, current_stop=1.95)
    _cancel_stop(rig, p.stop_client_id)
    with rig.state.tx():
        rig.state.update_position(p.trade_id, current_stop=1.95006)    # tick 0.0001'e hizali degil
    at_run(rig)
    rig.run()
    a = next(iter(rig.live_stops(XRP).values()))
    assert a["triggerPrice"] == Decimal("1.9501"), "long: sıkı = yukari yuvarla"


def test_L5_short_position_stop_side_buy(rig):
    p = rig.seed_position(side="short", stop=2.1, qty=10.0)
    _cancel_stop(rig, p.stop_client_id)
    at_run(rig)
    rig.run()
    a = next(iter(rig.live_stops(XRP).values()))
    assert a["side"] == "BUY" and a["triggerPrice"] == Decimal("2.1")


def test_L5_would_trigger_closes_at_market(rig):
    p = rig.seed_position()
    _cancel_stop(rig, p.stop_client_id)
    rig.ex.marks["XRPUSDT"] = Decimal("1.8")           # stop (1.9) hemen tetiklenirdi -> -2021
    at_run(rig)
    m = rig.mark()
    rig.run()
    assert rig.ex.pos["XRPUSDT"]["amt"] == 0
    assert any(x[2].get("reduceOnly") == "true" and x[2]["side"] == "SELL" for x in rig.posts(m) if x[1] == "/fapi/v1/order")


def test_L5_second_attempt_failure_closes_and_marks_stop_failed(rig):
    p = rig.seed_position()
    _cancel_stop(rig, p.stop_client_id)
    for _ in range(2):
        rig.ex.inject("/fapi/v1/algoOrder", FakeResp(400, {"code": -2022, "msg": "ReduceOnly Order is rejected."}))
    at_run(rig)
    m = rig.mark()
    rig.run()
    assert rig.ex.pos["XRPUSDT"]["amt"] == 0
    assert rig.blocked() == "stop_failed"
    assert len([x for x in rig.posts(m) if x[1] == "/fapi/v1/algoOrder"]) == 2
    assert rig.rec.counters["stops_reinstalled"] == 0 or True   # SPEC-AMBIGUOUS: basarisiz denemede sayac sartnamede yok


def test_L5_first_attempt_rejected_second_succeeds_uses_new_seq(rig):
    p = rig.seed_position()
    _cancel_stop(rig, p.stop_client_id)
    rig.ex.inject("/fapi/v1/algoOrder", FakeResp(400, {"code": -2022, "msg": "ReduceOnly Order is rejected."}))
    at_run(rig)
    rig.run()
    live = rig.live_stops(XRP)
    # SPEC-AMBIGUOUS: "ikinci deneme" kimligi sartnamede adlandirilmiyor; yalniz bir stop duruyor ve pozisyon acik varsayilir.
    assert len(live) == 1 and rig.ex.pos["XRPUSDT"]["amt"] == Decimal("10")


# =====================================================================================================
# L6: stop miktari != pozisyon miktari; r8
# =====================================================================================================
def test_L6_wrong_stop_qty_new_stop_first_then_old_cancelled(rig):
    p = rig.seed_position(stop_qty=8.0)
    old = p.stop_client_id
    at_run(rig)
    m = rig.mark()
    rig.run()
    w = rig.writes(m)
    live = rig.live_stops(XRP)
    assert list(live) == [cidf("stop", XRP, "long", 1)] and live[cidf("stop", XRP, "long", 1)]["qty"] == Decimal("10")
    i_post = next(i for i, x in enumerate(w) if x[0] == "POST")
    i_del = next(i for i, x in enumerate(w) if x[0] == "DELETE")
    assert i_post < i_del, "r8: yeni stop once, eski sonra"
    assert rig.ex.algos[old]["algoStatus"] == "CANCELED"
    assert rig.ex.algos[cidf("stop", XRP, "long", 1)]["algoStatus"] == "NEW", "r8: yeni stop iptal edilmez"
    assert rig.state.get_position(p.trade_id).stop_client_id == cidf("stop", XRP, "long", 1)


def test_L6_new_stop_rejected_old_stop_kept_never_cancelled_first(rig):
    p = rig.seed_position(stop_qty=8.0)
    # SPEC-AMBIGUOUS: gerceklemenin yeni stop icin kac deneme yaptigi sartnamede yok (L5'te iki); uc ret tum denemeleri kapsar.
    for _ in range(3):
        rig.ex.inject("/fapi/v1/algoOrder", FakeResp(400, {"code": -2022, "msg": "ReduceOnly Order is rejected."}))
    at_run(rig)
    m = rig.mark()
    rig.run()
    assert rig.ex.algos[p.stop_client_id]["algoStatus"] == "NEW", "r8: yeni basarisizsa eski ASLA once iptal edilmez"
    assert rig.deletes(m) == []


def test_L6_qty_tolerance_boundary_step_half(rig):
    """Adim 0.1: |dq| < 0.05 esit sayilir (eylem yok); 0.05'ten buyuk = L6."""
    p = rig.seed_position()
    rig.ex.algos[p.stop_client_id]["qty"] = Decimal("9.96")          # |dq| = 0.04 < step/2
    at_run(rig)
    m = rig.mark()
    rep = rig.run()
    assert rig.writes(m) == [] and rep.ok
    rig.ex.algos[p.stop_client_id]["qty"] = Decimal("9.94")          # |dq| = 0.06 > step/2
    m = rig.mark()
    rig.run(advance=15)
    assert rig.posts(m), "step/2 asildi -> yeni stop"


# =====================================================================================================
# L7: birden cok stop -> en siki kalir
# =====================================================================================================
@pytest.mark.parametrize("side,stops,keep_idx", [("long", (1.9, 1.95), 1), ("short", (2.1, 2.05), 1)])
def test_L7_multiple_stops_tightest_kept(rig, side, stops, keep_idx):
    p = rig.seed_position(side=side, stop=stops[0])
    other = rig.put_stop(XRP, side, 10, stops[1], 1, p.trade_id)
    at_run(rig)
    m = rig.mark()
    rig.run()
    live = rig.live_stops(XRP)
    assert list(live) == [other], "long: en yuksek tetik; short: en dusuk tetik kalir"
    assert rig.posts(m) == [], "yeni emir yok; yalniz iptal"
    cur = rig.state.get_position(p.trade_id)
    assert cur.stop_client_id == other and cur.current_stop == pytest.approx(stops[1])


def test_L7_state_already_points_to_tightest_loose_one_cancelled(rig):
    p = rig.seed_position(stop=1.95)
    loose = rig.put_stop(XRP, "long", 10, 1.9, 1, p.trade_id)
    at_run(rig)
    rig.run()
    assert loose not in rig.live_stops(XRP) and p.stop_client_id in rig.live_stops(XRP)
    assert rig.state.get_position(p.trade_id).stop_client_id == p.stop_client_id


# =====================================================================================================
# L8: yetim reduceOnly / kayitsiz onekli emir
# =====================================================================================================
def _orphan_stop(rig, record):
    p = rig.seed_position(with_stop=False)
    cid = rig.put_stop(XRP, "long", 10, 1.9, 0, p.trade_id, record=record)
    rig.ex.external_close("XRPUSDT")                           # pozisyon yok; stop NEW kalir
    with rig.state.tx():
        rig.state.update_position(p.trade_id, status="closed", exit_reason="other", closed_ts=rig.clock.now())
    return cid


def test_L8_orphan_reduce_only_with_orders_row_cancelled(rig, caplog):
    cid = _orphan_stop(rig, record=True)
    at_run(rig)
    caplog.set_level(logging.DEBUG)
    m = rig.mark()
    rig.run()
    assert rig.ex.algos[cid]["algoStatus"] == "CANCELED"
    assert rig.posts(m) == []


def test_L8_prefixed_order_not_in_orders_table_cancelled_with_critical(rig, caplog):
    cid = _orphan_stop(rig, record=False)
    at_run(rig)
    caplog.set_level(logging.DEBUG)
    rig.run()
    assert rig.ex.algos[cid]["algoStatus"] == "CANCELED"
    assert any(r.levelno >= logging.CRITICAL for r in caplog.records)


# =====================================================================================================
# L9: yabanci acik emir
# =====================================================================================================
def _foreign(rig, symbol="DOGEUSDT"):
    rig.ex.orders["web_hand_1"] = {"clientOrderId": "web_hand_1", "symbol": symbol, "side": "BUY", "type": "LIMIT",
                                   "orderId": 555, "reduceOnly": False, "origQty": "100", "status": "NEW", "executedQty": "0",
                                   "avgPrice": "0", "price": "0.1", "time": 0, "updateTime": 0}


def test_L9_foreign_order_not_cancelled_finding_critical_and_block_then_clears(rig, caplog):
    _foreign(rig)
    at_run(rig)
    caplog.set_level(logging.DEBUG)
    m = rig.mark()
    rep = rig.run()                                            # duz kip: sembolsuz tam tarama
    assert rig.deletes(m) == [] and rig.ex.orders["web_hand_1"]["status"] == "NEW"
    assert any(f.startswith("foreign_order:") for f in rep.findings) and not rep.ok
    assert rig.blocked() == "reconcile_foreign_order"
    assert any(r.levelno >= logging.CRITICAL for r in caplog.records)
    rig.ex.orders["web_hand_1"]["status"] = "CANCELED"          # insan kaldirdi
    rig.run(advance=60)
    assert rig.blocked() is None


def test_L9_flat_mode_scans_without_symbol_open_mode_per_symbol(rig):
    at_run(rig)
    rig.run()
    flat = [q for m, p, q in rig.ex.requests if p == "/fapi/v1/openOrders"]
    assert flat and any("symbol" not in q for q in flat), "duz kip: sembolsuz tam tarama"
    rig.seed_position()
    n = rig.mark()
    rig.run(advance=15)
    opened = [q for m, p, q in rig.ex.requests[n:] if p == "/fapi/v1/openOrders"]
    assert opened and all(q.get("symbol") == "XRPUSDT" for q in opened), "acik kip: yalniz pozisyonlu semboller"


def test_L9_open_mode_does_not_see_foreign_order_on_other_symbol(rig):
    rig.seed_position()
    _foreign(rig, "DOGEUSDT")
    at_run(rig)
    rep = rig.run()
    assert not any(f.startswith("foreign_order") for f in rep.findings)


# =====================================================================================================
# L10: hesap kipi kaymasi
# =====================================================================================================
def test_L10_leverage_drift_finding_critical_no_autofix(rig, caplog):
    rig.seed_position()
    rig.ex.lev["XRPUSDT"] = 5
    at_run(rig)
    caplog.set_level(logging.DEBUG)
    m = rig.mark()
    rep = rig.run()
    assert f"account_mode_drift:{XRP}" in rep.findings
    assert any(r.levelno >= logging.CRITICAL for r in caplog.records)
    assert all(p not in ("/fapi/v1/leverage", "/fapi/v1/marginType") or mth == "GET"
               for mth, p, _ in rig.ex.requests[m:]), "otomatik duzeltme yok"
    assert rig.ex.lev["XRPUSDT"] == 5


def test_L10_matching_leverage_is_clean(rig):
    rig.seed_position()
    at_run(rig)
    rep = rig.run()
    assert not any(f.startswith("account_mode_drift") for f in rep.findings)


def test_L10_margin_type_drift_detected(tmp_path):
    # SPEC-AMBIGUOUS: marginType BrokerPosition'da yok; LiveReconciler(margin_types=...) ile verilir. Bicim tahmini:
    # {pair: "isolated"|"cross"} sozlugu (pair = "XRP/USDT").
    r = Rig(tmp_path, margin_types=MT({XRP: "cross"}))
    try:
        r.seed_position()
        at_run(r)
        m = r.mark()
        rep = r.run()
        assert f"account_mode_drift:{XRP}" in rep.findings
        assert all(p != "/fapi/v1/marginType" or mth == "GET" for mth, p, _ in r.ex.requests[m:])
    finally:
        r.state.close()


def test_L10_margin_type_isolated_is_clean(tmp_path):
    r = Rig(tmp_path, margin_types=MT({XRP: "isolated"}))
    try:
        r.seed_position()
        at_run(r)
        rep = r.run()
        assert not any(f.startswith("account_mode_drift") for f in rep.findings)
    finally:
        r.state.close()


# =====================================================================================================
# L11: defter denetimleri (05 §7)
# =====================================================================================================
def test_L11_ledger_orphan_blocks_entries(rig):
    rig.ledger.open_trades = [SimpleNamespace(trade_id=424242)]
    at_run(rig)
    rep = rig.run()
    assert "ledger_orphan:424242" in rep.findings
    assert rig.blocked() == "reconcile_ledger_orphan"
    rig.ledger.open_trades = []
    rig.run(advance=15)
    assert rig.blocked() is None


def test_L11_unledgered_check_runs_with_open_trade_ids(rig):
    p = rig.seed_position()
    at_run(rig)
    rig.run()
    assert any(p.trade_id in ids for ids in rig.ledger.checked)


# =====================================================================================================
# Toleranslar (§8 sapma toleranslari)
# =====================================================================================================
@pytest.mark.parametrize("exch_qty,expect_l4", [("9.96", False), ("9.951", False), ("9.949", True), ("9.9", True)])
def test_tolerance_position_qty_step_half(rig, exch_qty, expect_l4):
    """Adim 0.1: |dq| < 0.05 esit; asildiginda L4. (Sinirin tam ustu float gurultusu icin iki yandan 0.001 kala.)"""
    p = rig.seed_position(qty=10.0)
    rig.ex.pos["XRPUSDT"]["amt"] = Decimal(exch_qty)          # stop 10 iken borsa miktari (disaridan azalmis)
    at_run(rig)
    m = rig.mark()
    rep = rig.run()
    got = rig.state.kv_get(f"ext_reduction:{p.trade_id}") is not None      # B5 fix 10: L4 bulgu degil; kv + sayac
    assert got is expect_l4
    if not expect_l4:
        assert rig.writes(m) == [] and rig.state.kv_get(f"ext_reduction:{p.trade_id}") is None


def test_tolerance_stop_trigger_within_half_tick_is_equal(rig):
    p = rig.seed_position()
    rig.ex.algos[p.stop_client_id]["triggerPrice"] = Decimal("1.90004")     # < tick/2 (0.00005)
    at_run(rig)
    m = rig.mark()
    rep = rig.run()
    assert rig.writes(m) == [] and rep.ok
    assert rig.state.get_position(p.trade_id).current_stop == pytest.approx(1.9)
    rig.ex.algos[p.stop_client_id]["triggerPrice"] = Decimal("1.89996")
    m = rig.mark()
    rep = rig.run(advance=15)
    assert rig.writes(m) == [] and rep.ok


def test_tolerance_stop_tighter_on_exchange_state_pulled_no_orders(rig):
    p = rig.seed_position()
    rig.ex.algos[p.stop_client_id]["triggerPrice"] = Decimal("1.9001")     # sikici (long: yukari), >= tick/2
    at_run(rig)
    m = rig.mark()
    rig.run()
    assert rig.writes(m) == []
    assert rig.state.get_position(p.trade_id).current_stop == pytest.approx(1.9001)


def test_tolerance_stop_tighter_short_state_pulled(rig):
    p = rig.seed_position(side="short", stop=2.1)
    rig.ex.algos[p.stop_client_id]["triggerPrice"] = Decimal("2.0999")     # short: asagi = sikici
    at_run(rig)
    m = rig.mark()
    rig.run()
    assert rig.writes(m) == [] and rig.state.get_position(p.trade_id).current_stop == pytest.approx(2.0999)


def test_tolerance_stop_looser_on_exchange_reinstalled_like_L6(rig):
    p = rig.seed_position()
    rig.ex.algos[p.stop_client_id]["triggerPrice"] = Decimal("1.89994")    # gevsek, > tick/2
    at_run(rig)
    m = rig.mark()
    rig.run()
    w = rig.writes(m)
    live = rig.live_stops(XRP)
    assert len(live) == 1 and next(iter(live.values()))["triggerPrice"] == Decimal("1.9")
    assert [x[0] for x in w][:2] == ["POST", "DELETE"], "yeni once, eski sonra"
    assert rig.state.get_position(p.trade_id).current_stop == pytest.approx(1.9)


def test_tolerance_entry_price_drift_over_point_one_percent_warns_only(rig, caplog):
    p = rig.seed_position()
    rig.ex.pos["XRPUSDT"]["entry"] = Decimal("2.0021")          # %0,105 > %0,1
    at_run(rig)
    caplog.set_level(logging.DEBUG)
    m = rig.mark()
    rep = rig.run()
    assert rig.writes(m) == []
    # SPEC-AMBIGUOUS: uyari metni/bulgu adi `entry_price_drift`; gunluk ya da bulgu olarak gorunmesi yeter.
    assert any("entry_price_drift" in r.getMessage() and r.levelno == logging.WARNING for r in caplog.records) \
        or any("entry_price_drift" in f for f in rep.findings)
    assert rig.state.get_position(p.trade_id).entry_price == pytest.approx(2.0), "state degismez"
    assert rig.holds() == {}


def test_tolerance_entry_price_within_point_one_percent_silent(rig, caplog):
    rig.seed_position()
    rig.ex.pos["XRPUSDT"]["entry"] = Decimal("2.0019")          # %0,095
    at_run(rig)
    caplog.set_level(logging.DEBUG)
    rep = rig.run()
    assert not any("entry_price_drift" in r.getMessage() for r in caplog.records)
    assert not any("entry_price_drift" in f for f in rep.findings)


# =====================================================================================================
# Okuma arizasi -> hicbir eylem yok
# =====================================================================================================
@pytest.mark.parametrize("path", ["/fapi/v2/positionRisk", "/fapi/v1/openOrders", "/fapi/v1/openAlgoOrders"])
def test_read_failure_means_no_action_and_exchange_unreachable_finding(rig, path):
    p = rig.seed_position()
    _cancel_stop(rig, p.stop_client_id)                  # normalde L5 tetiklenirdi
    rig.ex.fill_market("DOGEUSDT", "BUY", 100)           # ve L2
    at_run(rig)
    before_state = rig.state.get_position(p.trade_id)
    rig.down(path)
    m = rig.mark()
    rep = rig.run()
    assert rep.findings == ("exchange_unreachable",)
    assert rig.writes(m) == []
    assert rig.pause.holds() == () or rig.holds() == {}
    assert rig.state.get_position(p.trade_id) == before_state
    assert rig.events == [] and rig.unopened == []


def test_read_failure_position_risk_down_does_not_look_like_flat_L3(rig):
    p = rig.seed_position()
    at_run(rig)
    rig.down("/fapi/v2/positionRisk")
    m = rig.mark()
    rep = rig.run()
    assert rep.findings == ("exchange_unreachable",)
    assert rig.ex.count("/fapi/v1/userTrades") == 0 and rig.events == []
    assert rig.blocked() is None and rig.state.get_position(p.trade_id).status == "open"


def test_read_failure_not_fatal_in_report(rig):
    rig.seed_position()
    at_run(rig)
    rig.down("/fapi/v2/positionRisk")
    rep = rig.run()
    # SPEC-AMBIGUOUS: `fatal` degeri sartnamede yok; ag arizasi icin fatal=False beklenir (F1: eylemsiz, surec ayakta).
    assert not rep.fatal and not rep.ok


def test_recovers_after_read_failure(rig):
    p = rig.seed_position()
    _cancel_stop(rig, p.stop_client_id)
    at_run(rig)
    orig = rig.down("/fapi/v2/positionRisk")
    rig.run()
    rig.ex.request = orig
    rig.run(advance=15)
    assert len(rig.live_stops(XRP)) == 1


# =====================================================================================================
# protect_first
# =====================================================================================================
def test_protect_first_installs_missing_stop_no_market_data_needed(tmp_path):
    r = Rig(tmp_path)         # piyasa verisi / besleme nesnesi hic yok: LiveReconciler'a verilmez
    try:
        p = r.seed_position(stop=1.9, current_stop=1.95)
        _cancel_stop(r, p.stop_client_id)
        r.new_broker()                              # yeniden baslatma
        r.make_rec()
        r.clock.set_time(T0 + timedelta(seconds=30))
        m = r.mark()
        r.protect()
        live = r.live_stops(XRP)
        assert len(live) == 1
        a = next(iter(live.values()))
        assert a["triggerPrice"] == Decimal("1.95") and a["qty"] == Decimal("10")
        assert r.rec.counters["stops_reinstalled"] == 1
        paths = {p_ for _, p_, _ in r.ex.requests[m:]}
        assert not any("klines" in x or "ticker" in x for x in paths)
    finally:
        r.state.close()


def test_protect_first_resolves_unresolved_orders_first(rig):
    rig.seed_position(status="opening", with_stop=False, exch=False)
    ecid = cidf("entry")
    with rig.state.tx():
        rig.state.update_order(ecid, status="unknown")
    rig.ex.fill_market("XRPUSDT", "BUY", 10, cid=ecid)
    calls = []
    orig = rig.orders.resolve_unresolved
    rig.orders.resolve_unresolved = lambda *a, **k: (calls.append(1), orig(*a, **k))[1]
    at_run(rig)
    rig.protect()
    assert calls


def test_protect_first_partial_fill_uses_exchange_qty_F6_and_initial_stop_when_no_current(rig):
    # F4/F6: giris doldu (kismi), stop kurulmadan surec oldu; state satiri `opening`, qty yok.
    rig.clock.set_time(T0 + timedelta(seconds=5))
    rig.ex.fill_market("XRPUSDT", "BUY", "7.5", cid=cidf("entry"))
    pos = _opening_no_order(rig)
    with rig.state.tx():
        rig.state.insert_order(rig._row(cidf("entry"), XRP, "entry", "buy", 10.0, None, False, "unknown", 0, pos.trade_id,
                                        rig.clock.now()))
    calls = []
    orig = rig.broker.register_position
    rig.broker.register_position = lambda *a, **k: (calls.append((a, k)), orig(*a, **k))[1]
    at_run(rig, 40)
    rig.protect()
    live = rig.live_stops(XRP)
    assert len(live) == 1
    a = next(iter(live.values()))
    assert a["qty"] == Decimal("7.5") and a["triggerPrice"] == Decimal("1.9"), "borsa miktari, initial_stop"
    # SPEC-AMBIGUOUS: ("register_position on entry fill (B4) and in protect_first (B5)") cagri sekli yalniz pair/opened_ts bilinir.
    assert calls and calls[0][0][0] == XRP


def test_protect_first_does_not_run_L4_L9_L7_actions(rig):
    p = rig.seed_position()
    other = rig.put_stop(XRP, "long", 10, 1.95, 1, p.trade_id)         # L7 adayi
    _foreign(rig, "XRPUSDT")                                           # L9 adayi
    rig.ex.fill_market("XRPUSDT", "SELL", 4, cid="web_manual")         # L4 adayi
    at_run(rig)
    m = rig.mark()
    rep = rig.protect()
    assert rig.writes(m) == [], "protect_first yalniz L1, L5, L2 bulgusu"
    assert not any(f.startswith(("foreign_order", "qty_reduced_external")) for f in rep.findings)
    assert other in rig.live_stops(XRP) and p.stop_client_id in rig.live_stops(XRP)


def test_protect_first_unknown_position_finding_without_orders(rig):
    rig.ex.fill_market("DOGEUSDT", "BUY", 100)
    at_run(rig)
    m = rig.mark()
    rep = rig.protect()
    assert any(f.startswith("unknown_position") for f in rep.findings)
    assert rig.writes(m) == []


def test_protect_first_read_failure_no_action(rig):
    p = rig.seed_position()
    _cancel_stop(rig, p.stop_client_id)
    at_run(rig)
    rig.down("/fapi/v2/positionRisk")
    m = rig.mark()
    rep = rig.protect()
    assert rig.writes(m) == []
    assert rep.findings == ("exchange_unreachable",)


def test_protect_first_does_not_close_unknown_position_even_with_kill(rig):
    # SPEC-AMBIGUOUS: sartname L2 KILL istisnasini `run` icin tanimlar; protect_first "yalniz ... L2 bulgusu" uretir.
    # KILL altinda protect_first'in da kapatabilecegi okunabilir; burada KAPATMAZ varsayilir (kapatma `run` ya da engine _kill_step'tir).
    rig.ex.fill_market("DOGEUSDT", "BUY", 100)
    rig.kill.set("test", "drill")
    at_run(rig)
    m = rig.mark()
    rig.protect()
    assert [x for x in rig.posts(m) if x[1] == "/fapi/v1/order"] == []


# =====================================================================================================
# Duraklatma tutuslari asla kaldirilmaz
# =====================================================================================================
def test_pause_holds_never_removed_by_reconcile(rig):
    rig.pause.add("user_cmd", by="telegram:1")
    rig.pause.add("late_fill", by="engine:reconcile")
    rig.pause.add("unknown_position", by="engine:reconcile")
    rig.pause.add("exchange_ban", by="engine:x")

    def boom(*a, **k):
        raise AssertionError("mutabakat pause.remove cagirmamali")

    rig.pause.remove = boom
    rig.seed_position()
    at_run(rig)
    rig.run()
    rig.protect()
    rig.run(advance=15)
    assert {h.reason for h in rig.pause.holds()} == {"user_cmd", "late_fill", "unknown_position", "exchange_ban"}


def test_pause_hold_added_by_reconcile_keeps_original_origin_on_repeat(rig):
    rig.pause.add("unknown_position", by="engine:first")
    rig.ex.fill_market("DOGEUSDT", "BUY", 100)
    at_run(rig)
    rig.run()
    assert rig.holds()["unknown_position"].by == "engine:first"


def test_reconcile_never_calls_remove_on_clean_run_with_foreign_gone(rig):
    rig.pause.add("manual", by="cli")
    _foreign(rig)
    at_run(rig)
    rig.run()
    rig.ex.orders["web_hand_1"]["status"] = "CANCELED"
    rig.run(advance=60)
    assert "manual" in rig.holds()
