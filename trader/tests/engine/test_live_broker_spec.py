"""WP-B3 (11-canli-broker.md §5, §3.4, §13 satir B3) LiveBroker sartname testleri.

Bagimsiz test ajani; yalniz sartnameden ve committed koddan (Broker protokolu, types, binance_rest istisnalari,
exchange/rules.py) yazildi. Gercek ag/saat yok: sahte REST istemcisi (FakeRest) bu dosyadadir.
`# SPEC-AMBIGUOUS:` ile isaretli yerler sartnamenin adlandirmadigi noktalardaki tahminlerdir.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest

from trader_engine.brokers import binance_futures as BF
from trader_engine.config import LiveSettings
from trader_engine.clock import SimClock
from trader_engine.engine import EngineExit
from trader_engine.errors import BrokerError, BrokerUncertain, DataError
from trader_engine.exchange.binance_rest import ExchangeAuth, ExchangeReject, ExchangeUncertain
from trader_engine.marketdata.rest_public import ExchangeBan
from trader_engine.order_manager import make_client_id
from trader_engine.types import OrderRequest

UTC = timezone.utc
T0 = datetime(2026, 12, 28, 9, 0, tzinfo=UTC)
SIG = T0                                   # sinyal bari kapanisi (kimlikler icin)
XRP, DOGE = "XRP/USDT", "DOGE/USDT"
FEE = 0.0004                               # takerCommissionRate (sahte borsa)
FALLBACK_FEE = 0.0005


def ms(dt: datetime) -> int:
    return int(dt.timestamp() * 1000)


def cid(role, side="long", seq=0, pair=XRP, bot="learner"):
    return make_client_id(bot, role, pair, side, SIG, seq)


# --------------------------------------------------------------------------------------------- sahte REST
class FakeRest:
    """SignedRestClient sarmalayici yuzeyini taklit eder; cagrilari kaydeder, betikli yanit/istisna dondurur."""

    def __init__(self, clock: SimClock, env="testnet"):
        self.clock, self.env = clock, env
        self.calls: list[tuple[str, tuple, dict]] = []
        self.script: dict[str, list] = {}           # ad -> sirayla tuketilen istisna (ya da ("val", x))
        self.sticky: dict[str, Exception] = {}      # ad -> surekli istisna
        self.info = exchange_info()
        self.acct = {"canTrade": True, "totalWalletBalance": "100.0", "totalUnrealizedProfit": "1.5",
                     "totalMarginBalance": "101.5", "totalInitialMargin": "20.0", "availableBalance": "80.0"}
        self.pos = {"XRPUSDT": pr("XRPUSDT", "0"), "DOGEUSDT": pr("DOGEUSDT", "0")}
        self.restr = {"enableReading": True, "enableFutures": True, "enableWithdrawals": False,
                      "enableInternalTransfer": False, "permitsUniversalTransfer": False, "ipRestrict": True}
        self.dual, self.multi = False, False
        self.open_normal: list[dict] = []
        self.open_cond: list[dict] = []
        self.mark = Decimal("2.05")
        self.order_store: dict[str, dict] = {}
        self.query_seq: dict[str, list[dict | None]] = {}
        self.cond_store: dict[str, dict] = {}
        self.market_resp: list = []                 # betikli new_market yanitlari (dict ya da istisna)
        self.cond_resp: list = []
        self.on_market = None                       # fn(params) -> yan etki (pozisyon sifirla, islem ekle...)
        self.trades: list[dict] = []
        self.incomes: list[dict] = []
        self._oid = 1000

    # -- yardimci
    def _rec(self, name, a, kw):
        self.calls.append((name, a, kw))
        q = self.script.get(name)
        if q:
            x = q.pop(0)
            if isinstance(x, Exception):
                raise x
            if isinstance(x, tuple) and x[0] == "val":
                return ("val", x[1])
        if name in self.sticky:
            raise self.sticky[name]
        return None

    def n(self, name):
        return sum(1 for c in self.calls if c[0] == name)

    def of(self, name):
        return [c for c in self.calls if c[0] == name]

    def idx(self, name):
        for i, c in enumerate(self.calls):
            if c[0] == name:
                return i
        return None

    def _ret(self, r, default):
        return r[1] if isinstance(r, tuple) else default

    # -- uclar
    def sync_time(self):
        r = self._rec("sync_time", (), {})
        return self._ret(r, ms(self.clock.now()))

    def exchange_info(self):
        r = self._rec("exchange_info", (), {})
        return self._ret(r, self.info)

    def mark_price(self, symbol):
        r = self._rec("mark_price", (symbol,), {})
        return self._ret(r, self.mark)

    def account(self, **kw):
        r = self._rec("account", (), kw)
        return self._ret(r, dict(self.acct))

    def position_risk(self, symbol=None, **kw):
        r = self._rec("position_risk", (symbol,), kw)
        rows = [dict(v) for k, v in self.pos.items() if symbol in (None, k)]
        return self._ret(r, rows)

    def open_orders(self, symbol=None, **kw):
        r = self._rec("open_orders", (symbol,), kw)
        return self._ret(r, list(self.open_normal))

    def open_conditionals(self, symbol=None, **kw):
        r = self._rec("open_conditionals", (symbol,), kw)
        return self._ret(r, list(self.open_cond))

    def new_market(self, symbol, side, qty, client_id, reduce_only, **kw):
        r = self._rec("new_market", (symbol, side, qty, client_id, reduce_only), kw)
        if self.on_market:
            self.on_market(dict(symbol=symbol, side=side, qty=qty, client_id=client_id, reduce_only=reduce_only))
        if self.market_resp:
            x = self.market_resp.pop(0)
            if isinstance(x, Exception):
                raise x
            resp = x
        else:
            q = Decimal(str(qty))
            resp = order_resp(client_id, "FILLED", q, "2.05")
        resp.setdefault("clientOrderId", client_id)
        self.order_store[client_id] = resp
        return resp

    def new_conditional(self, symbol, order_type, side, qty, trigger, client_id, working_type, **kw):
        r = self._rec("new_conditional", (symbol, order_type, side, qty, trigger, client_id, working_type), kw)
        if self.cond_resp:
            x = self.cond_resp.pop(0)
            if isinstance(x, Exception):
                raise x
            resp = x
        else:
            resp = {"clientAlgoId": client_id, "clientOrderId": client_id, "algoStatus": "NEW", "status": "NEW",
                    "workingType": working_type, "algoId": self._oid}
        self._oid += 1
        self.cond_store[client_id] = resp
        return resp

    def query_order(self, symbol, client_id, **kw):
        self._rec("query_order", (symbol, client_id), kw)
        seq = self.query_seq.get(client_id)
        if seq:
            return seq.pop(0) if len(seq) > 1 else seq[0]
        return self.order_store.get(client_id)

    def query_conditional(self, symbol, client_id, **kw):
        self._rec("query_conditional", (symbol, client_id), kw)
        return self.cond_store.get(client_id)

    def cancel_order(self, symbol, client_id, **kw):
        self._rec("cancel_order", (symbol, client_id), kw)

    def cancel_conditional(self, symbol, client_id, **kw):
        self._rec("cancel_conditional", (symbol, client_id), kw)

    def user_trades(self, symbol, start_ms, end_ms=None):
        r = self._rec("user_trades", (symbol, start_ms, end_ms), {})
        return self._ret(r, [dict(t) for t in self.trades if t["symbol"] == symbol])

    def income(self, symbol, income_type, start_ms, end_ms):
        r = self._rec("income", (symbol, income_type, start_ms, end_ms), {})
        return self._ret(r, [dict(x) for x in self.incomes])

    def commission_rate(self, symbol):
        r = self._rec("commission_rate", (symbol,), {})
        return self._ret(r, {"symbol": symbol, "takerCommissionRate": str(FEE), "makerCommissionRate": "0.0002"})

    def api_restrictions(self):
        r = self._rec("api_restrictions", (), {})
        return self._ret(r, dict(self.restr))

    def position_mode(self):
        r = self._rec("position_mode", (), {})
        return self._ret(r, self.dual)

    def set_one_way(self):
        self._rec("set_one_way", (), {})
        self.dual = False

    def multi_assets(self):
        r = self._rec("multi_assets", (), {})
        return self._ret(r, self.multi)

    def set_single_asset(self):
        self._rec("set_single_asset", (), {})
        self.multi = False

    def set_isolated(self, symbol):
        self._rec("set_isolated", (symbol,), {})

    def set_leverage(self, symbol, leverage):
        self._rec("set_leverage", (symbol, leverage), {})

    def health(self):
        return {"used_weight": 0, "order_count_10s": 0, "order_count_1m": 0, "clock_offset_ms": 0,
                "ban_until_ms": 0, "last_ok_ms": ms(self.clock.now())}


def pr(symbol, amt, entry="0", lev="3", margin_type="isolated", mark="2.05", upd=None, liq="0", unreal="0",
       iso_margin="0"):
    return {"symbol": symbol, "positionAmt": str(amt), "entryPrice": str(entry), "leverage": str(lev),
            "marginType": margin_type, "markPrice": str(mark), "updateTime": upd if upd is not None else ms(T0),
            "liquidationPrice": str(liq), "unRealizedProfit": str(unreal), "isolatedMargin": str(iso_margin),
            "positionSide": "BOTH"}


def exchange_info(include_doge=True):
    def sym(name, tick, step, notional):
        return {"symbol": name, "status": "TRADING", "contractType": "PERPETUAL", "filters": [
            {"filterType": "PRICE_FILTER", "tickSize": tick},
            {"filterType": "LOT_SIZE", "stepSize": step, "minQty": step, "maxQty": "1000000"},
            {"filterType": "MARKET_LOT_SIZE", "stepSize": step, "minQty": step, "maxQty": "1000000"},
            {"filterType": "MIN_NOTIONAL", "notional": notional}]}
    syms = [sym("XRPUSDT", "0.0001", "0.1", "5")]
    if include_doge:
        syms.append(sym("DOGEUSDT", "0.00001", "1", "5"))
    return {"symbols": syms}


def order_resp(client_id, status, executed, avg, oid=None, cum=None):
    executed = Decimal(str(executed))
    return {"orderId": oid or 5000, "clientOrderId": client_id, "status": status, "executedQty": str(executed),
            "avgPrice": str(avg), "cumQuote": str(cum if cum is not None else executed * Decimal(str(avg))),
            "origQty": str(executed), "updateTime": ms(T0)}


def trade(i, oid, side, qty, price, commission, t, symbol="XRPUSDT", asset="USDT", **extra):
    d = {"id": i, "orderId": oid, "symbol": symbol, "side": side, "qty": str(qty), "price": str(price),
         "commission": str(commission), "commissionAsset": asset, "time": ms(t), "realizedPnl": "0"}
    d.update(extra)
    return d


# --------------------------------------------------------------------------------------------- kurulum
def make_broker(env="testnet", startup=True, rest=None, pairs=(XRP, DOGE), **live_kw):
    clock = SimClock(T0)
    rest = rest or FakeRest(clock, env)
    live = LiveSettings(account_tag="sub-acct", expected_wallet_max=1000.0, **live_kw)
    # SPEC-AMBIGUOUS: kurucu anahtar sozcukle cagrilir (§5 imzasi: live, env, leverage, pairs, rest, clock, taker_fee_fallback)
    b = BF.LiveBroker(live=live, env=env, leverage=3, pairs=list(pairs), rest=rest, clock=clock,
                      taker_fee_fallback=FALLBACK_FEE)
    if startup:
        b.startup_check()
    return b, rest, clock


def req(role="entry", side="long", qty=10.0, trigger=None, pair=XRP, seq=0, reduce_only=None, wt="MARK_PRICE", lev=3):
    osd = {"entry": "buy" if side == "long" else "sell"}.get(role, "sell" if side == "long" else "buy")
    ro = (role != "entry") if reduce_only is None else reduce_only
    return OrderRequest(client_id=cid(role, side, seq, pair), pair=pair, role=role, order_side=osd, qty=qty,
                        trigger_price=trigger, reduce_only=ro, leverage=lev if role == "entry" else None,
                        working_type=wt, created_ts=T0)


def d(x):
    return Decimal(str(x))


# ============================================================================================ §5.1 eslik tablosu
def test_flags_and_protocol_surface():
    b, _, _ = make_broker()
    assert b.is_simulated is False
    for m in ("advance", "snapshot", "restore"):
        assert not hasattr(b, m)
    for m in ("rules", "account", "positions", "open_orders", "prepare", "market_order", "place_stop", "place_target",
              "cancel", "query", "poll", "startup_check", "closing_events", "foreign_open_orders", "health"):
        assert callable(getattr(b, m))


def test_rules_from_own_exchange_info_and_missing_pair_is_dataerror():
    b, rest, _ = make_broker()
    r = b.rules(XRP)
    assert (r.pair, r.symbol, r.tick, r.step, r.min_qty, r.max_qty, r.min_notional) == \
           (XRP, "XRPUSDT", 0.0001, 0.1, 0.1, 1000000.0, 5.0)
    assert rest.n("exchange_info") >= 1
    with pytest.raises(DataError):
        b.rules("ETH/USDT")


def test_rules_missing_for_one_pair_blocks_only_that_pair():
    clock = SimClock(T0)
    rest = FakeRest(clock)
    rest.info = exchange_info(include_doge=False)
    b, _, _ = make_broker(rest=rest)          # baslamali (rules_missing = o cifte giris yok, motor ayakta)
    assert b.rules(XRP).symbol == "XRPUSDT"
    with pytest.raises(DataError):
        b.rules(DOGE)


def test_account_mapping_and_2s_cache():
    b, rest, clock = make_broker()
    a = b.account()
    assert (a.wallet, a.unrealized, a.equity, a.used_margin, a.available) == (100.0, 1.5, 101.5, 20.0, 80.0)
    n0 = rest.n("account")
    b.account()
    clock.advance(1.0)
    b.account()
    assert rest.n("account") == n0                       # 2 sn icinde onbellek
    clock.advance(1.5)                                   # toplam 2.5 sn
    rest.acct["totalWalletBalance"] = "90.0"
    assert b.account().wallet == 90.0
    assert rest.n("account") == n0 + 1


def test_positions_mapping_long_and_short_skip_zero():
    b, rest, _ = make_broker()
    rest.pos["XRPUSDT"] = pr("XRPUSDT", "10", entry="2.05", lev="3", mark="2.1", upd=ms(T0), liq="1.4", unreal="0.5",
                             iso_margin="6.9")
    rest.pos["DOGEUSDT"] = pr("DOGEUSDT", "-300", entry="0.1", mark="0.11", liq="0.13", iso_margin="10")
    ps = {p.pair: p for p in b.positions()}
    x, g = ps[XRP], ps[DOGE]
    assert (x.side, x.qty, x.entry_price, x.leverage, x.margin, x.liq_price, x.mark_price, x.unrealized) == \
           ("long", 10.0, 2.05, 3, 6.9, 1.4, 2.1, 0.5)
    assert (x.funding_paid, x.fee_paid_entry) == (0.0, 0.0)
    assert x.opened_ts == T0
    assert (g.side, g.qty) == ("short", 300.0)
    rest.pos["DOGEUSDT"] = pr("DOGEUSDT", "0")
    assert [p.pair for p in b.positions()] == [XRP]


def test_open_orders_only_own_prefixes_and_role_from_letter_and_foreign_listed():
    b, rest, _ = make_broker()
    own_stop, own_entry = cid("stop"), cid("entry", seq=1)
    # SPEC-AMBIGUOUS: acik emir satirlari Binance alanlariyla (clientOrderId/clientAlgoId, origQty/quantity, stopPrice/triggerPrice)
    rest.open_normal = [
        {"symbol": "XRPUSDT", "clientOrderId": own_entry, "side": "BUY", "origQty": "10", "executedQty": "0",
         "price": "0", "stopPrice": "0", "reduceOnly": False, "status": "NEW", "type": "MARKET",
         "time": ms(T0), "updateTime": ms(T0)},
        {"symbol": "XRPUSDT", "clientOrderId": "web_abc123", "side": "BUY", "origQty": "5", "executedQty": "0",
         "price": "1.5", "stopPrice": "0", "reduceOnly": False, "status": "NEW", "type": "LIMIT",
         "time": ms(T0), "updateTime": ms(T0)}]
    rest.open_cond = [
        {"symbol": "XRPUSDT", "clientAlgoId": own_stop, "side": "SELL", "quantity": "10", "triggerPrice": "2.0346",
         "reduceOnly": True, "algoStatus": "NEW", "workingType": "MARK_PRICE", "algoType": "CONDITIONAL",
         "type": "STOP_MARKET", "createTime": ms(T0), "updateTime": ms(T0)}]
    got = {o.client_id: o for o in b.open_orders()}
    assert set(got) == {own_entry, own_stop}
    assert got[own_stop].role == "stop" and got[own_entry].role == "entry"
    assert got[own_stop].trigger_price == 2.0346 and got[own_stop].reduce_only is True
    assert got[own_stop].pair == XRP and got[own_stop].order_side == "sell"
    only = b.open_orders(XRP)
    assert {o.client_id for o in only} == {own_entry, own_stop}
    assert b.open_orders(DOGE) == []
    fo = b.foreign_open_orders()
    assert len(fo) == 1 and "web_abc123" in repr(fo[0])


def test_prepare_is_networkless_after_startup_check_and_rejects_other_leverage():
    b, rest, _ = make_broker()
    n = len(rest.calls)
    b.prepare(XRP, 3)
    b.prepare(XRP, 3)
    b.prepare(DOGE, 3)
    assert len(rest.calls) == n
    with pytest.raises(BrokerError):
        b.prepare(XRP, 5)
    assert len(rest.calls) == n


def test_prepare_before_startup_check_raises_brokererror_without_network():
    # SPEC-AMBIGUOUS: startup_check gecmeden prepare -> BrokerError ("startup_check adim 6 gectiyse" kosulu)
    b, rest, _ = make_broker(startup=False)
    with pytest.raises(BrokerError):
        b.prepare(XRP, 3)
    assert rest.calls == []


def test_prepare_for_pair_with_unfixable_account_mode_raises_but_startup_continues():
    clock = SimClock(T0)
    rest = FakeRest(clock)
    rest.pos["XRPUSDT"] = pr("XRPUSDT", "10", entry="2.05", lev="5", margin_type="cross")   # duzeltilemez
    b, _, _ = make_broker(rest=rest)                  # §3.4 adim 6: motor baslar
    with pytest.raises(BrokerError):
        b.prepare(XRP, 3)
    b.prepare(DOGE, 3)                                # diger cift etkilenmez


# ============================================================================================ §5.1 query / cancel
@pytest.mark.parametrize("raw,expected", [("NEW", "new"), ("PARTIALLY_FILLED", "new"), ("FILLED", "filled"),
                                          ("CANCELED", "canceled"), ("REJECTED", "rejected"), ("EXPIRED", "expired")])
def test_query_normal_status_mapping(raw, expected):
    b, rest, _ = make_broker()
    c = cid("entry")
    rest.order_store[c] = order_resp(c, raw, "10", "2.05")
    o = b.query(XRP, c)
    assert o is not None and o.status == expected and o.client_id == c and o.role == "entry"


@pytest.mark.parametrize("raw,expected", [("NEW", "new"), ("TRIGGERED", "filled"), ("FINISHED", "filled"),
                                          ("CANCELED", "canceled"), ("EXPIRED", "expired"), ("REJECTED", "rejected")])
def test_query_conditional_status_mapping_by_role_letter(raw, expected):
    b, rest, _ = make_broker()
    c = cid("stop")
    # SPEC-AMBIGUOUS: koruyucu emir durum alani adi algoStatus (classic kipte status); ikisi de verilir
    rest.cond_store[c] = {"clientAlgoId": c, "clientOrderId": c, "algoStatus": raw, "status": raw,
                          "workingType": "MARK_PRICE", "quantity": "10", "origQty": "10", "triggerPrice": "2.0346",
                          "stopPrice": "2.0346", "side": "SELL", "reduceOnly": True}
    o = b.query(XRP, c)
    assert o is not None and o.status == expected and o.role == "stop"
    assert rest.n("query_conditional") >= 1


def test_query_missing_returns_none():
    b, _, _ = make_broker()
    assert b.query(XRP, cid("entry", seq=9)) is None
    assert b.query(XRP, cid("stop", seq=9)) is None


def test_cancel_routes_by_role_letter_and_is_noop_when_missing():
    b, rest, _ = make_broker()
    b.cancel(XRP, cid("stop"))
    b.cancel(XRP, cid("target"))
    b.cancel(XRP, cid("entry"))
    b.cancel(XRP, cid("exit"))
    assert [c[1][1] for c in rest.of("cancel_conditional")] == [cid("stop"), cid("target")]
    assert [c[1][1] for c in rest.of("cancel_order")] == [cid("entry"), cid("exit")]


def test_cancel_uncertain_raises_brokeruncertain():
    b, rest, _ = make_broker()
    rest.script["cancel_conditional"] = [ExchangeUncertain("x")]
    with pytest.raises(BrokerUncertain):
        b.cancel(XRP, cid("stop"))


# ============================================================================================ §5.3 piyasa emri
def test_market_entry_filled_result_fee_and_queued_fill_event():
    b, rest, _ = make_broker()
    r = req("entry", qty=10.0)
    res = b.market_order(r)
    assert (res.status, res.client_id, res.filled_qty, res.avg_price) == ("filled", r.client_id, 10.0, 2.05)
    assert res.fee == pytest.approx(20.5 * FEE)                      # cumQuote x takerCommissionRate (§3.4 adim 8)
    (_, a, kw), = rest.of("new_market")
    assert a[0] == "XRPUSDT" and a[1].upper() == "BUY" and d(a[2]) == d("10") and a[3] == r.client_id and not a[4]
    evs = b.poll(T0)
    fills = [e for e in evs if e.kind == "fill"]
    assert len(fills) == 1 and fills[0].fill.reason == "market" and fills[0].fill.qty == 10.0
    assert fills[0].fill.client_id == r.client_id and fills[0].client_id == r.client_id
    assert b.poll(T0) == []                                          # bir kez teslim


def test_market_entry_uses_fallback_fee_when_commission_rate_unavailable():
    clock = SimClock(T0)
    rest = FakeRest(clock)
    rest.sticky["commission_rate"] = ExchangeUncertain("x")
    b, _, _ = make_broker(rest=rest)
    res = b.market_order(req("entry", qty=10.0))
    assert res.fee == pytest.approx(20.5 * FALLBACK_FEE)
    # SPEC-AMBIGUOUS: fee_rate_fallback sayaci health() icinde gorunur
    assert b.health().get("fee_rate_fallback", 0) >= 1


def test_market_entry_short_side_param():
    b, rest, _ = make_broker()
    b.market_order(req("entry", side="short", qty=10.0))
    assert rest.of("new_market")[0][1][1].upper() == "SELL"


def test_market_entry_new_then_filled_after_query():
    b, rest, _ = make_broker()
    r = req("entry", qty=10.0)
    rest.market_resp = [order_resp(r.client_id, "NEW", "0", "0")]
    rest.query_seq[r.client_id] = [order_resp(r.client_id, "NEW", "0", "0"),
                                   order_resp(r.client_id, "FILLED", "10", "2.05")]
    res = b.market_order(r)
    assert res.status == "filled" and res.filled_qty == 10.0 and res.avg_price == 2.05
    assert rest.n("query_order") >= 1


def test_market_entry_still_open_after_wait_is_accepted_and_pending_event_later():
    b, rest, clock = make_broker()
    r = req("entry", qty=10.0)
    rest.market_resp = [order_resp(r.client_id, "NEW", "0", "0")]
    rest.query_seq[r.client_id] = [order_resp(r.client_id, "NEW", "0", "0")]
    t_before = clock.now()
    res = b.market_order(r)
    assert res.status == "accepted"
    assert clock.now() - t_before <= timedelta(seconds=3.5)          # fill_wait_s = 3
    assert [e for e in b.poll(clock.now()) if e.kind == "fill"] == []
    rest.query_seq[r.client_id] = [order_resp(r.client_id, "FILLED", "10", "2.05")]
    rest.pos["XRPUSDT"] = pr("XRPUSDT", "10", entry="2.05")
    clock.advance(6)                                                 # > poll_open_s
    fills = [e for e in b.poll(clock.now()) if e.kind == "fill"]
    assert len(fills) == 1 and fills[0].fill.qty == 10.0 and fills[0].fill.reason == "market"


@pytest.mark.parametrize("status", ["EXPIRED", "CANCELED"])
def test_market_entry_partial_terminal_is_filled_with_executed_qty(status):
    b, rest, _ = make_broker()
    r = req("entry", qty=10.0)
    rest.market_resp = [order_resp(r.client_id, status, "4", "2.05")]
    res = b.market_order(r)
    assert res.status == "filled" and res.filled_qty == 4.0 and res.avg_price == 2.05


@pytest.mark.parametrize("status", ["EXPIRED", "CANCELED"])
def test_market_entry_zero_exec_terminal_is_order_rejected_event(status):
    b, rest, _ = make_broker()
    r = req("entry", qty=10.0)
    rest.market_resp = [order_resp(r.client_id, status, "0", "0")]
    b.market_order(r)          # SPEC-AMBIGUOUS: donus durumu belirtilmemis; yalniz olay denetlenir
    evs = [e for e in b.poll(T0) if e.kind == "order_rejected"]
    assert len(evs) == 1 and evs[0].detail == "expired_unfilled" and evs[0].client_id == r.client_id


def _exit_setup(b, rest, qty="10"):
    rest.pos["XRPUSDT"] = pr("XRPUSDT", qty, entry="2.05")
    b.positions()                                                    # son bilinen pozisyon miktari


def test_market_exit_partial_terminal_yields_order_rejected_partial_exit_no_fill():
    b, rest, _ = make_broker()
    _exit_setup(b, rest)
    r = req("exit", qty=10.0)
    rest.market_resp = [order_resp(r.client_id, "EXPIRED", "4", "2.03")]
    b.market_order(r)
    evs = b.poll(T0)
    assert [e for e in evs if e.kind == "fill"] == []
    rej = [e for e in evs if e.kind == "order_rejected"]
    assert len(rej) == 1 and rej[0].detail in ("partial_exit:4", "partial_exit:4.0")
    a = rest.of("new_market")[0][1]
    assert a[4] is True                                              # reduceOnly


def test_market_exit_zero_exec_terminal_yields_expired_unfilled():
    b, rest, _ = make_broker()
    _exit_setup(b, rest)
    r = req("exit", qty=10.0)
    rest.market_resp = [order_resp(r.client_id, "CANCELED", "0", "0")]
    b.market_order(r)
    rej = [e for e in b.poll(T0) if e.kind == "order_rejected"]
    assert len(rej) == 1 and rej[0].detail == "expired_unfilled"


def test_market_exit_filled_is_accepted_and_fill_comes_via_closing_events_with_exact_fee():
    b, rest, clock = make_broker()
    _exit_setup(b, rest)
    r = req("exit", qty=10.0)

    def flat(_p):
        rest.pos["XRPUSDT"] = pr("XRPUSDT", "0")
        rest.trades = [trade(1, 4000, "BUY", 10, "2.05", "0.0082", T0 - timedelta(minutes=5)),
                       trade(2, 5000, "SELL", 10, "2.03", "0.00812", T0 + timedelta(seconds=1))]
    rest.on_market = flat
    rest.market_resp = [order_resp(r.client_id, "FILLED", "10", "2.03", oid=5000)]
    res = b.market_order(r)
    assert res.status == "accepted"
    fills = [e for e in b.poll(clock.now()) if e.kind == "fill"]
    assert len(fills) == 1
    f = fills[0].fill
    assert (f.reason, f.client_id, f.qty, f.fee) == ("market", r.client_id, 10.0, pytest.approx(0.00812))
    assert f.price == pytest.approx(2.03)


def test_market_order_exchange_reject_becomes_rejected_result():
    b, rest, _ = make_broker()
    r = req("entry")
    rest.market_resp = [ExchangeReject("m", code=-2019, http=400, msg="Margin is insufficient")]
    res = b.market_order(r)
    assert res.status == "rejected" and res.reason == "insufficient_margin" and res.client_id == r.client_id


def test_market_order_uncertain_raises_brokeruncertain_and_does_not_resend():
    b, rest, _ = make_broker()
    rest.market_resp = [ExchangeUncertain("t")]
    with pytest.raises(BrokerUncertain):
        b.market_order(req("entry"))
    assert rest.n("new_market") == 1


@pytest.mark.parametrize("code,http,msg,reason", [
    (-2021, 400, "", "would_trigger"),
    (-4116, 400, "", "duplicate_client_id"),
    (-2019, 400, "", "insufficient_margin"),
    (-4164, 400, "", "min_notional"),
    (-2022, 400, "", "reduce_only_exceeds"),
    (-1111, 400, "", "filter:-1111"),
    (-1013, 400, "", "filter:-1013"),
    (-4003, 400, "", "filter:-4003"),
    (-4005, 400, "", "filter:-4005"),
    (-4131, 400, "", "filter:-4131"),
    (None, 429, "", "rate_limited"),
    (None, 0, "order_rate_cap", "order_rate_cap"),
    (-9999, 400, "weird", "exchange_-9999"),
])
def test_reject_name_mapping_market(code, http, msg, reason):
    b, rest, _ = make_broker()
    r = req("entry")
    rest.market_resp = [ExchangeReject("m", code=code, http=http, msg=msg)]
    res = b.market_order(r)
    assert (res.status, res.reason) == ("rejected", reason)


def test_filter_reject_refreshes_rules_immediately():
    b, rest, _ = make_broker()
    n = rest.n("exchange_info")
    rest.market_resp = [ExchangeReject("m", code=-1111, http=400)]
    b.market_order(req("entry"))
    assert rest.n("exchange_info") == n + 1


def test_unknown_reject_code_counts_and_reason_keeps_code():
    b, rest, _ = make_broker()
    rest.market_resp = [ExchangeReject("m", code=-7777, http=400)]
    res = b.market_order(req("entry"))
    assert res.reason == "exchange_-7777"
    # SPEC-AMBIGUOUS: sayac health() sozlugunde "unknown_reject_codes" anahtariyla
    assert b.health().get("unknown_reject_codes", 0) >= 1


def test_reject_mapping_applies_to_stop_too():
    b, rest, _ = make_broker()
    rest.cond_resp = [ExchangeReject("m", code=-2021, http=400)]
    res = b.place_stop(req("stop", qty=10.0, trigger=2.04))
    assert (res.status, res.reason) == ("rejected", "would_trigger")


# -- yerel dogrulama (ag cagrisi yok, paper ile ayni adlar)
@pytest.mark.parametrize("kw,reason", [
    (dict(qty=10.05), "step"),
    (dict(qty=2000000.0), "max_qty"),
    (dict(qty=2.0), "min_notional"),                    # 2.0 x 2.05 = 4.1 < 5 (referans = son mark)
    (dict(qty=0.0), "qty"),
    (dict(qty=float("nan")), "qty"),
])
def test_local_validation_entry_rejects_without_network(kw, reason):
    b, rest, _ = make_broker()
    res = b.market_order(req("entry", **kw))
    assert (res.status, res.reason) == ("rejected", reason)
    assert rest.n("new_market") == 0


def test_local_validation_stop_trigger_not_tick_multiple_and_flags():
    b, rest, _ = make_broker()
    # SPEC-AMBIGUOUS: tick-disi tetik -> yerel ret; ad "tick" (paper adlari). Tight rounding (§16.3) ise tetigi
    # yuvarlar; bu test yalniz ret VARSA ag cagrisi olmadigini ve adin tick oldugunu kabul eder, yuvarlama varsa atlanir.
    res = b.place_stop(req("stop", qty=10.0, trigger=2.03457, reduce_only=False))
    assert res.status == "rejected" and res.reason == "not_reduce_only"
    assert rest.n("new_conditional") == 0
    res = b.place_stop(req("stop", qty=10.0, trigger=2.0346, wt="CONTRACT_PRICE"))
    assert res.status == "rejected" and res.reason == "bad_working_type"
    assert rest.n("new_conditional") == 0


# ============================================================================================ §5.4 koruyucu emir
def test_place_stop_params_long_and_tight_rounding_example():
    b, rest, _ = make_broker()
    r = req("stop", side="long", qty=10.0, trigger=2.03457)
    res = b.place_stop(r)
    assert res.status == "accepted" and res.client_id == r.client_id
    (_, a, _kw), = rest.of("new_conditional")
    assert a[0] == "XRPUSDT" and a[1] == "STOP_MARKET" and a[2].upper() == "SELL"
    assert d(a[3]) == d("10") and d(a[4]) == d("2.0346")            # §16.3: long yukari
    assert a[5] == r.client_id and a[6] == "MARK_PRICE"


def test_place_stop_short_rounds_down_and_buy_side():
    b, rest, _ = make_broker()
    b.place_stop(req("stop", side="short", qty=10.0, trigger=2.03457))
    a = rest.of("new_conditional")[0][1]
    assert a[2].upper() == "BUY" and d(a[4]) == d("2.0345")


def test_place_stop_working_type_mismatch_cancels_and_rejects():
    b, rest, _ = make_broker()
    r = req("stop", qty=10.0, trigger=2.0346)
    rest.cond_resp = [{"clientAlgoId": r.client_id, "clientOrderId": r.client_id, "algoStatus": "NEW", "status": "NEW",
                       "workingType": "CONTRACT_PRICE", "algoId": 1}]
    res = b.place_stop(r)
    assert (res.status, res.reason) == ("rejected", "working_type_mismatch")
    assert [c[1][1] for c in rest.of("cancel_conditional")] == [r.client_id]


def test_place_stop_uncertain_raises():
    b, rest, _ = make_broker()
    rest.cond_resp = [ExchangeUncertain("t")]
    with pytest.raises(BrokerUncertain):
        b.place_stop(req("stop", qty=10.0, trigger=2.0346))
    assert rest.n("new_conditional") == 1


def test_place_target_uses_take_profit_market_and_easy_rounding():
    b, rest, _ = make_broker()
    res = b.place_target(req("target", side="long", qty=10.0, trigger=2.30457))
    assert res.status == "accepted"
    a = rest.of("new_conditional")[0][1]
    assert a[1] == "TAKE_PROFIT_MARKET" and d(a[4]) == d("2.3045")   # long hedef asagi (kolay dolum)
    assert a[6] == "MARK_PRICE"


# ============================================================================================ §7 poll / _sync
def test_poll_respects_flat_interval_and_single_position_risk_call():
    b, rest, clock = make_broker()
    b.poll(clock.now())
    n = rest.n("position_risk")
    clock.advance(10)
    b.poll(clock.now())
    assert rest.n("position_risk") == n                              # duz: poll_flat_s = 30
    clock.advance(25)
    b.poll(clock.now())
    assert rest.n("position_risk") == n + 1                          # tek cagri, tum semboller
    assert rest.of("position_risk")[-1][1][0] is None


def test_poll_open_interval_when_position_watched_and_close_detected():
    b, rest, clock = make_broker()
    b.market_order(req("entry", qty=10.0))
    rest.pos["XRPUSDT"] = pr("XRPUSDT", "10", entry="2.05")
    b.poll(clock.now())
    stop_c = cid("stop")
    b.place_stop(req("stop", qty=10.0, trigger=2.0346))
    n = rest.n("position_risk")
    clock.advance(4)
    b.poll(clock.now())
    assert rest.n("position_risk") == n                              # poll_open_s = 5 dolmadi
    # stop tetiklendi, pozisyon sifir
    rest.cond_store[stop_c] = {"clientAlgoId": stop_c, "algoStatus": "TRIGGERED", "actualOrderId": 900,
                               "workingType": "MARK_PRICE"}
    rest.pos["XRPUSDT"] = pr("XRPUSDT", "0")
    rest.trades = [trade(1, 800, "BUY", 10, "2.05", "0.0082", T0),
                   trade(2, 900, "SELL", 10, "2.03", "0.00812", T0 + timedelta(seconds=4))]
    clock.advance(2)
    evs = b.poll(clock.now())
    fills = [e for e in evs if e.kind == "fill"]
    assert len(fills) == 1 and fills[0].fill.reason == "stop" and fills[0].fill.client_id == stop_c


def test_poll_unreachable_returns_empty_and_health_not_reachable_then_recovers():
    b, rest, clock = make_broker()
    rest.sticky["position_risk"] = ExchangeUncertain("down")
    clock.advance(31)
    assert b.poll(clock.now()) == []
    assert b.health()["reachable"] is False
    del rest.sticky["position_risk"]
    clock.advance(31)
    b.poll(clock.now())
    assert b.health()["reachable"] is True


def test_poll_amount_decrease_not_zero_makes_no_event():
    b, rest, clock = make_broker()
    rest.pos["XRPUSDT"] = pr("XRPUSDT", "10", entry="2.05")
    b.positions()
    clock.advance(31)
    b.poll(clock.now())
    rest.pos["XRPUSDT"] = pr("XRPUSDT", "5", entry="2.05")
    clock.advance(31)
    assert b.poll(clock.now()) == []


def test_health_fields():
    b, _, _ = make_broker()
    h = b.health()
    for k in ("used_weight", "reachable", "last_sync_ts", "naked"):
        assert k in h


# ============================================================================================ §5.5 closing_events
def _closed_world(rest, b, stop_cid=None):
    """Pozisyon 10 XRP long biliniyor; borsa simdi duz."""
    rest.pos["XRPUSDT"] = pr("XRPUSDT", "10", entry="2.05")
    b.positions()


def _stop_world(b, rest, order_id=900):
    s = cid("stop")
    b.place_stop(req("stop", qty=10.0, trigger=2.0346))
    rest.cond_store[s] = {"clientAlgoId": s, "clientOrderId": s, "algoStatus": "TRIGGERED", "status": "TRIGGERED",
                          "actualOrderId": order_id, "workingType": "MARK_PRICE", "algoId": 77}
    return s


def test_closing_events_vwap_fee_sum_reason_stop_example_16_4():
    b, rest, _ = make_broker()
    _closed_world(rest, b)
    s = _stop_world(b, rest)
    t1, t2 = T0 + timedelta(seconds=10), T0 + timedelta(seconds=12)
    rest.pos["XRPUSDT"] = pr("XRPUSDT", "0")
    rest.trades = [trade(1, 800, "BUY", 10, "2.05", "0.0082", T0),
                   trade(2, 900, "SELL", 4, "2.0300", "0.00406", t1),
                   trade(3, 900, "SELL", 6, "2.0280", "0.006084", t2)]
    evs = b.closing_events(XRP, T0)
    fills = [e for e in evs if e.kind in ("fill", "liquidation")]
    assert len(fills) == 1
    f = fills[0].fill
    assert f.qty == pytest.approx(10.0)
    assert f.price == pytest.approx(2.0288)
    assert f.fee == pytest.approx(0.010144)
    assert f.ts == t2 and f.reason == "stop" and f.client_id == s
    assert f.order_side == "sell"
    # since_ms - 1000 ile okunur
    assert rest.of("user_trades")[0][1][1] == ms(T0) - 1000


def test_closing_events_excludes_entry_side_trades():
    b, rest, _ = make_broker()
    _closed_world(rest, b)
    _stop_world(b, rest)
    rest.pos["XRPUSDT"] = pr("XRPUSDT", "0")
    rest.trades = [trade(1, 800, "BUY", 10, "2.05", "0.0082", T0),
                   trade(2, 900, "SELL", 10, "2.03", "0.00812", T0 + timedelta(seconds=3))]
    f = [e for e in b.closing_events(XRP, T0) if e.kind == "fill"][0].fill
    assert f.qty == pytest.approx(10.0) and f.fee == pytest.approx(0.00812) and f.price == pytest.approx(2.03)


def test_closing_events_reason_exit_when_our_x_order_closed_it():
    b, rest, _ = make_broker()
    _closed_world(rest, b)
    x = req("exit", qty=10.0)
    rest.market_resp = [order_resp(x.client_id, "NEW", "0", "0", oid=901)]      # simdi sonlanmamis; sonra bulunur
    rest.query_seq[x.client_id] = [order_resp(x.client_id, "NEW", "0", "0", oid=901)]
    b.market_order(x)
    rest.order_store[x.client_id] = order_resp(x.client_id, "FILLED", "10", "2.03", oid=901)
    rest.query_seq[x.client_id] = [rest.order_store[x.client_id]]
    rest.pos["XRPUSDT"] = pr("XRPUSDT", "0")
    rest.trades = [trade(2, 901, "SELL", 10, "2.03", "0.00812", T0 + timedelta(seconds=2))]
    f = [e for e in b.closing_events(XRP, T0) if e.kind == "fill"][0]
    assert f.fill.reason == "market" and f.fill.client_id == x.client_id and f.detail != "foreign_close"


def test_closing_events_reason_liquidation_by_autoclose_prefix():
    b, rest, _ = make_broker()
    _closed_world(rest, b)
    rest.pos["XRPUSDT"] = pr("XRPUSDT", "0")
    # SPEC-AMBIGUOUS: likidasyon emri kimligi userTrades satirinda clientOrderId olarak gelir (gercekte emir sorgusuyla
    # cozulur; sartname yalniz "kimlik autoclose- ile baslar" der).
    rest.trades = [trade(2, 999, "SELL", 10, "1.40", "0.0056", T0 + timedelta(seconds=2),
                         clientOrderId="autoclose-1234567")]
    evs = b.closing_events(XRP, T0)
    liq = [e for e in evs if e.kind == "liquidation"]
    assert len(liq) == 1 and liq[0].fill.reason == "liquidation"
    assert liq[0].fill.qty == pytest.approx(10.0)


def test_closing_events_reason_liquidation_adl_prefix():
    b, rest, _ = make_broker()
    _closed_world(rest, b)
    rest.pos["XRPUSDT"] = pr("XRPUSDT", "0")
    rest.trades = [trade(2, 999, "SELL", 10, "1.40", "0.0056", T0 + timedelta(seconds=2),
                         clientOrderId="adl_autoclose")]
    assert [e.kind for e in b.closing_events(XRP, T0) if e.kind != "funding"] == ["liquidation"]


def test_closing_events_foreign_close_is_market_with_detail():
    b, rest, _ = make_broker()
    _closed_world(rest, b)
    rest.pos["XRPUSDT"] = pr("XRPUSDT", "0")
    rest.trades = [trade(2, 31337, "SELL", 10, "2.00", "0.008", T0 + timedelta(seconds=2))]
    fills = [e for e in b.closing_events(XRP, T0) if e.kind == "fill"]
    assert len(fills) == 1 and fills[0].fill.reason == "market" and fills[0].detail == "foreign_close"


def test_closing_events_short_position_uses_buy_trades_as_reducing():
    b, rest, _ = make_broker()
    rest.pos["XRPUSDT"] = pr("XRPUSDT", "-10", entry="2.05")
    b.positions()
    rest.pos["XRPUSDT"] = pr("XRPUSDT", "0")
    rest.trades = [trade(1, 800, "SELL", 10, "2.05", "0.0082", T0),
                   trade(2, 31337, "BUY", 10, "2.10", "0.0084", T0 + timedelta(seconds=2))]
    f = [e for e in b.closing_events(XRP, T0) if e.kind == "fill"][0].fill
    assert f.qty == pytest.approx(10.0) and f.price == pytest.approx(2.10) and f.order_side == "buy"


def test_closing_events_missing_trades_returns_empty_after_three_rereads_then_retries_later():
    b, rest, clock = make_broker()
    _closed_world(rest, b)
    rest.pos["XRPUSDT"] = pr("XRPUSDT", "0")
    rest.trades = [trade(2, 31337, "SELL", 4, "2.00", "0.0032", T0 + timedelta(seconds=2))]     # 4 < 10
    assert b.closing_events(XRP, T0) == []
    assert rest.n("user_trades") == 4                                # 1 okuma + en fazla 3 yeniden okuma
    rest.trades.append(trade(3, 31337, "SELL", 6, "2.00", "0.0048", T0 + timedelta(seconds=3)))
    evs = [e for e in b.closing_events(XRP, T0) if e.kind == "fill"]      # sonraki turda yeniden denenir
    assert len(evs) == 1 and evs[0].fill.qty == pytest.approx(10.0)


def test_closing_events_no_trades_at_all_returns_empty():
    b, rest, _ = make_broker()
    _closed_world(rest, b)
    rest.pos["XRPUSDT"] = pr("XRPUSDT", "0")
    rest.trades = []
    assert b.closing_events(XRP, T0) == []


def test_closing_events_no_double_delivery():
    b, rest, _ = make_broker()
    _closed_world(rest, b)
    _stop_world(b, rest)
    rest.pos["XRPUSDT"] = pr("XRPUSDT", "0")
    rest.trades = [trade(2, 900, "SELL", 10, "2.03", "0.00812", T0 + timedelta(seconds=3))]
    first = b.closing_events(XRP, T0)
    assert len([e for e in first if e.kind == "fill"]) == 1
    assert b.closing_events(XRP, T0) == []


def test_closing_events_non_usdt_commission_uses_taker_rate_estimate():
    b, rest, _ = make_broker()
    _closed_world(rest, b)
    rest.pos["XRPUSDT"] = pr("XRPUSDT", "0")
    rest.trades = [trade(2, 31337, "SELL", 10, "2.00", "0.00001", T0 + timedelta(seconds=2), asset="BNB")]
    f = [e for e in b.closing_events(XRP, T0) if e.kind == "fill"][0].fill
    assert f.fee == pytest.approx(10 * 2.00 * FEE)
    # SPEC-AMBIGUOUS: sayac health() icinde
    assert b.health().get("fee_asset_unexpected", 0) >= 1


def test_closing_events_funding_events_precede_exit_and_sign_flipped():
    b, rest, _ = make_broker()
    _closed_world(rest, b)
    _stop_world(b, rest)
    t_exit = T0 + timedelta(hours=8, seconds=3)
    rest.pos["XRPUSDT"] = pr("XRPUSDT", "0")
    rest.trades = [trade(2, 900, "SELL", 10, "2.03", "0.00812", t_exit)]
    rest.incomes = [{"symbol": "XRPUSDT", "incomeType": "FUNDING_FEE", "income": "-0.0123", "asset": "USDT",
                     "time": ms(T0 + timedelta(hours=8))},
                    {"symbol": "XRPUSDT", "incomeType": "FUNDING_FEE", "income": "0.005", "asset": "USDT",
                     "time": ms(T0 + timedelta(hours=16))}]
    evs = b.closing_events(XRP, T0)
    kinds = [e.kind for e in evs]
    assert kinds == ["funding", "funding", "fill"]
    assert [e.funding_paid for e in evs[:2]] == [pytest.approx(0.0123), pytest.approx(-0.005)]   # pozitif = odenen
    inc = rest.of("income")[0][1]
    assert inc[0] == "XRPUSDT" and inc[1] == "FUNDING_FEE" and inc[2] == ms(T0) and inc[3] == ms(t_exit) + 5000
    assert all(e.pair == XRP for e in evs)


def test_closing_events_funding_unreadable_retries_then_gives_up_after_60s_with_zero():
    b, rest, clock = make_broker()
    _closed_world(rest, b)
    _stop_world(b, rest)
    rest.pos["XRPUSDT"] = pr("XRPUSDT", "0")
    rest.trades = [trade(2, 900, "SELL", 10, "2.03", "0.00812", T0 + timedelta(seconds=3))]
    rest.sticky["income"] = ExchangeUncertain("down")
    first = b.closing_events(XRP, T0)
    # SPEC-AMBIGUOUS: ilk turda bos donmesi ve sonra yeniden denenmesi (60 sn) - yalniz 60 sn sonrasi sabit kabul edilir
    clock.advance(30)
    mid = b.closing_events(XRP, T0)
    clock.advance(31)
    last = b.closing_events(XRP, T0)
    everything = first + mid + last
    fills = [e for e in everything if e.kind == "fill"]
    assert len(fills) == 1                                           # tek teslim
    assert [e for e in everything if e.kind == "funding"] == []
    assert rest.n("income") >= 2                                     # tekrar denendi


# ============================================================================================ §5.2 kurallar yenileme
def test_rules_refresh_hourly():
    b, rest, clock = make_broker()
    n = rest.n("exchange_info")
    clock.advance(1800)
    b.poll(clock.now())
    b.rules(XRP)
    assert rest.n("exchange_info") == n                              # 1 saat dolmadi
    clock.advance(1900)                                              # toplam > 3600
    b.poll(clock.now())
    b.rules(XRP)
    assert rest.n("exchange_info") > n


def test_rules_stale_after_6h_dataerror_but_exits_still_work():
    b, rest, clock = make_broker()
    rest.sticky["exchange_info"] = ExchangeUncertain("down")
    clock.advance(5 * 3600 + 3000)
    b.poll(clock.now())
    assert b.rules(XRP).symbol == "XRPUSDT"                          # < 6 saat: son bilinen
    clock.advance(3600)                                              # > 6 saat
    b.poll(clock.now())
    with pytest.raises(DataError):
        b.rules(XRP)
    # cikis son bilinen kuralla surer
    rest.pos["XRPUSDT"] = pr("XRPUSDT", "10", entry="2.05")
    b.positions()
    res = b.market_order(req("exit", qty=10.0))
    assert res.status in ("accepted", "filled")
    assert rest.n("new_market") == 1


def test_rules_refresh_success_resets_staleness():
    b, rest, clock = make_broker()
    clock.advance(5 * 3600 + 3000)
    b.poll(clock.now())                                              # basarili yenileme
    clock.advance(2 * 3600)
    b.poll(clock.now())
    assert b.rules(XRP).symbol == "XRPUSDT"


# ============================================================================================ §3.4 startup_check
def test_startup_check_sequence_and_per_pair_setup_testnet_skips_restrictions():
    b, rest, _ = make_broker("testnet")
    assert rest.n("api_restrictions") == 0
    order = [c[0] for c in rest.calls]
    assert order.index("sync_time") < order.index("account") < order.index("multi_assets") \
        < order.index("position_mode") < order.index("set_isolated")
    for sym in ("XRPUSDT", "DOGEUSDT"):
        assert any(c[1][0] == sym for c in rest.of("set_isolated"))
        assert any(c[1] == (sym, 3) for c in rest.of("set_leverage"))
    assert rest.n("position_risk") >= 1                              # dogrulama
    assert rest.n("commission_rate") == 2
    assert rest.n("exchange_info") >= 1


def test_startup_check_live_runs_restrictions_after_time_before_account():
    b, rest, _ = make_broker("live")
    order = [c[0] for c in rest.calls]
    assert order.index("sync_time") < order.index("api_restrictions") < order.index("account")


@pytest.mark.parametrize("field,val", [("enableReading", False), ("enableFutures", False),
                                       ("enableWithdrawals", True), ("enableInternalTransfer", True),
                                       ("permitsUniversalTransfer", True), ("ipRestrict", False)])
def test_startup_check_live_key_permission_failures_exit_8(field, val):
    clock = SimClock(T0)
    rest = FakeRest(clock, "live")
    rest.restr[field] = val
    b, _, _ = make_broker("live", startup=False, rest=rest)
    with pytest.raises(EngineExit) as ei:
        b.startup_check()
    assert ei.value.code == 8 and f"key_permission:{field}" in str(ei.value)


def test_startup_check_live_unreadable_restrictions_uncertain_is_retryable_exit_5():
    """DD-8 O6 ile degisti (eski: ag/zaman asimi -> 8 key_permission_unverifiable): okunamayan yanit ag sorunudur -> cikis 5
    (yeniden denenir); kalici ret/bozuk govde -> 8 (asagidaki testler). Beyan yolu yok."""
    clock = SimClock(T0)
    rest = FakeRest(clock, "live")
    rest.sticky["api_restrictions"] = ExchangeUncertain("down")
    b, _, _ = make_broker("live", startup=False, rest=rest)
    with pytest.raises(EngineExit) as ei:
        b.startup_check()
    assert ei.value.code == 5 and "exchange_unreachable" in str(ei.value)


def test_startup_check_live_unrecognised_restrictions_shape_exit_8():
    clock = SimClock(T0)
    rest = FakeRest(clock, "live")
    rest.restr = {"foo": 1}
    b, _, _ = make_broker("live", startup=False, rest=rest)
    with pytest.raises(EngineExit) as ei:
        b.startup_check()
    assert ei.value.code == 8


def test_startup_check_region_blocked_exit_8_and_unreachable_exit_5():
    clock = SimClock(T0)
    rest = FakeRest(clock)
    rest.sticky["sync_time"] = ExchangeBan("451", http=451)
    b, _, _ = make_broker(startup=False, rest=rest)
    with pytest.raises(EngineExit) as ei:
        b.startup_check()
    assert ei.value.code == 8 and "region_blocked" in str(ei.value)

    rest2 = FakeRest(SimClock(T0))
    rest2.sticky["sync_time"] = ExchangeUncertain("down")
    b2, _, _ = make_broker(startup=False, rest=rest2)
    with pytest.raises(EngineExit) as ei2:
        b2.startup_check()
    assert ei2.value.code == 5 and "exchange_unreachable" in str(ei2.value)


def test_startup_check_auth_failure_exit_8():
    # SPEC-AMBIGUOUS: ExchangeAuth herhangi bir adimda -> cikis kodu 8 (§3.3 "anahtar gecersiz")
    clock = SimClock(T0)
    rest = FakeRest(clock)
    rest.sticky["account"] = ExchangeAuth("bad", code=-2015, http=401)
    b, _, _ = make_broker(startup=False, rest=rest)
    with pytest.raises(EngineExit) as ei:
        b.startup_check()
    assert ei.value.code == 8


def test_startup_check_account_cannot_trade_and_wallet_above_expected():
    clock = SimClock(T0)
    rest = FakeRest(clock)
    rest.acct["canTrade"] = False
    b, _, _ = make_broker(startup=False, rest=rest)
    with pytest.raises(EngineExit) as ei:
        b.startup_check()
    assert ei.value.code == 8 and "account_cannot_trade" in str(ei.value)

    rest2 = FakeRest(SimClock(T0), "live")
    rest2.acct["totalWalletBalance"] = "5000.0"                      # expected_wallet_max = 1000
    b2, _, _ = make_broker("live", startup=False, rest=rest2)
    b2.startup_check()                                               # DD-8 O4: istisna YOK (eski: EngineExit 8); bulgu motor tutusuna donusur
    assert b2.startup_findings == ("wallet_above_expected",)


def test_startup_check_wallet_above_expected_finding_on_testnet_too():
    """DD-8 O4 ile degisti (eski: tavan denetimi yalniz live): testnet de denetler; asim istisna degil bulgudur."""
    clock = SimClock(T0)
    rest = FakeRest(clock)
    rest.acct["totalWalletBalance"] = "5000.0"
    b, _, _ = make_broker(startup=True, rest=rest)
    assert b.startup_findings == ("wallet_above_expected",)


def test_startup_check_multi_asset_flat_is_switched_off_with_positions_exits():
    clock = SimClock(T0)
    rest = FakeRest(clock)
    rest.multi = True
    make_broker(rest=rest)
    assert rest.n("set_single_asset") == 1

    rest2 = FakeRest(SimClock(T0))
    rest2.multi = True
    rest2.pos["XRPUSDT"] = pr("XRPUSDT", "10", entry="2.05")
    b2, _, _ = make_broker(startup=False, rest=rest2)
    with pytest.raises(EngineExit) as ei:
        b2.startup_check()
    assert ei.value.code == 8 and "multi_asset_mode" in str(ei.value)
    assert rest2.n("set_single_asset") == 0


def test_startup_check_hedge_mode_flat_switched_with_positions_or_orders_exits():
    clock = SimClock(T0)
    rest = FakeRest(clock)
    rest.dual = True
    make_broker(rest=rest)
    assert rest.n("set_one_way") == 1

    rest2 = FakeRest(SimClock(T0))
    rest2.dual = True
    rest2.pos["XRPUSDT"] = pr("XRPUSDT", "10", entry="2.05")
    b2, _, _ = make_broker(startup=False, rest=rest2)
    with pytest.raises(EngineExit) as ei:
        b2.startup_check()
    assert ei.value.code == 8 and "hedge_mode_with_positions" in str(ei.value)
    assert rest2.n("set_one_way") == 0
