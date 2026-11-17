"""WP-B1 gerçekleme duman testleri (11 §4, §16): SignedRestClient. Ağ yok; saat ve taşıma sahte."""
from __future__ import annotations

import logging
from decimal import Decimal
from urllib.parse import parse_qs, urlparse

import pytest

from trader_engine.exchange.binance_rest import (
    ExchangeAuth, ExchangeReject, ExchangeUncertain, SignedRestClient, fmt_num, sign)
from trader_engine.marketdata.rest_public import ExchangeBan

SECRET = "SIZMA-TESTI-gizli-0123456789abcdef"
KEY = "SIZMA-TESTI-anahtar-0123456789abcdef"


class Resp:
    def __init__(self, status=200, body=None, headers=None, text=""):
        self.status_code, self._b, self.headers, self.text = status, body, headers or {}, text

    def json(self):
        if self._b is None:
            raise ValueError("no json")
        return self._b


class Net:
    def __init__(self, script):
        self.script, self.calls = list(script), []

    def request(self, method, url, headers=None, timeout=None):
        self.calls.append((method, url, dict(headers or {}), timeout))
        r = self.script.pop(0)
        if isinstance(r, Exception):
            raise r
        return r


def mk(script, **kw):
    clock = {"t": 1_798_449_600_000, "sleeps": []}
    net = Net(script)

    def sleep(s):
        clock["sleeps"].append(s)
    c = SignedRestClient(env=kw.pop("env", "testnet"), api_key=KEY, api_secret=SECRET, session=net,
                         now_ms=lambda: clock["t"], sleep=sleep, **kw)
    return c, net, clock


def err(code, msg="x", status=400, headers=None):
    return Resp(status, {"code": code, "msg": msg}, headers)


def test_signature_example_16_1():
    q = ("symbol=XRPUSDT&side=BUY&type=MARKET&quantity=10&newClientOrderId=trLe-df350276c5ff969f6d18cd15"
         "&newOrderRespType=RESULT&recvWindow=5000&timestamp=1798449600000")
    assert sign(q, "ornek-gizli-anahtar") == "b4ecba7924301b8e54b162bcfd1acfb2c42f5b30d0b083b2bab9ce3af8a737e9"
    c, net, _ = mk([Resp(200, {"orderId": 1})])
    c.new_market("XRPUSDT", "BUY", "10", "trLe-df350276c5ff969f6d18cd15", False)
    m, url, h, to = net.calls[0]
    assert m == "POST" and h["X-MBX-APIKEY"] == KEY and to == (2.0, 3.0)
    qs = urlparse(url).query
    assert qs.startswith(q.rsplit("&recvWindow", 1)[0] + "&recvWindow=5000&timestamp=1798449600000&signature=")
    assert url.startswith("https://testnet.binancefuture.com/fapi/v1/order?")


def test_fmt_num_no_exponent():
    assert fmt_num(Decimal("1E+1")) == "10" and fmt_num(1e-7) == "0.0000001" and fmt_num(2.50) == "2.5"
    assert fmt_num(Decimal("0.000")) == "0" and fmt_num(True) == "true" and fmt_num(5) == "5"


def test_base_urls_fixed():
    c, net, _ = mk([Resp(200, {})], env="live")
    c.exchange_info()
    assert net.calls[0][1] == "https://fapi.binance.com/fapi/v1/exchangeInfo"
    assert "X-MBX-APIKEY" not in net.calls[0][2]


def test_time_sync_and_1021_single_retry_on_order():
    c, net, clock = mk([err(-1021), Resp(200, {"serverTime": clock_t() + 1000}), Resp(200, {"orderId": 1})])
    r = c.new_market("XRPUSDT", "BUY", "10", "cid", False)
    assert r == {"orderId": 1} and len(net.calls) == 3 and c.clock_offset_ms == 1000
    c2, net2, _ = mk([err(-1021), Resp(200, {"serverTime": clock_t()}), err(-1021)])
    with pytest.raises(ExchangeReject):
        c2.new_market("XRPUSDT", "BUY", "10", "cid", False)
    assert len(net2.calls) == 3


def clock_t():
    return 1_798_449_600_000


def test_order_post_never_retried_on_network_or_5xx():
    c, net, clock = mk([ConnectionError("boom")])
    with pytest.raises(ExchangeUncertain):
        c.new_market("X", "BUY", "1", "cid", False)
    assert len(net.calls) == 1 and clock["sleeps"] == []
    c, net, _ = mk([Resp(503, None, text="down")])
    with pytest.raises(ExchangeUncertain):
        c.new_conditional("X", "STOP_MARKET", "SELL", "1", "2", "cid", "MARK_PRICE")
    assert len(net.calls) == 1
    c, net, _ = mk([err(-1007, status=503)])
    with pytest.raises(ExchangeUncertain):
        c.new_market("X", "BUY", "1", "cid", False)


def test_read_retries_with_backoff():
    c, net, clock = mk([ConnectionError(), Resp(502), Resp(200, [])])
    assert c.open_orders() == []
    assert len(net.calls) == 3 and clock["sleeps"] == [1, 2]
    c, net, clock = mk([ConnectionError()] * 4)
    with pytest.raises(ExchangeUncertain):
        c.open_orders()
    assert len(net.calls) == 4 and clock["sleeps"] == [1, 2, 4]


def test_429_silence_window():
    c, net, clock = mk([Resp(429, {"code": -1003, "msg": "too many"}, {"Retry-After": "7"}), Resp(200, [])])
    assert c.open_orders() == [] and clock["sleeps"] == [7]
    c, net, clock = mk([Resp(429, None, {"Retry-After": "7"})])
    with pytest.raises(ExchangeReject) as ei:
        c.new_market("X", "BUY", "1", "cid", False)
    assert ei.value.http == 429 and ei.value.code is None
    with pytest.raises(ExchangeBan):
        c.position_risk(protective=True)           # koruyucu bile gitmez
    assert len(net.calls) == 1
    clock["t"] += 7001
    net.script.append(Resp(200, []))
    assert c.position_risk() == []


def test_ban_classes():
    c, net, clock = mk([Resp(418, None, {"Retry-After": "120"})])
    with pytest.raises(ExchangeBan) as ei:
        c.account()
    assert ei.value.http == 418
    with pytest.raises(ExchangeBan):
        c.account()
    assert len(net.calls) == 1
    c, _, _ = mk([Resp(451, None, text="blocked")])
    with pytest.raises(ExchangeBan) as ei:
        c.account()
    assert ei.value.http == 451
    c, net, clock = mk([Resp(403, None), Resp(403, None)])
    with pytest.raises(ExchangeBan):
        c.account()
    clock["t"] += 300_001
    with pytest.raises(ExchangeBan) as ei:
        c.account()
    assert ei.value.retry_after_s == 600
    for resp in (Resp(401, None), err(-2015), err(-1022), err(-2014)):
        c, _, _ = mk([resp])
        with pytest.raises(ExchangeAuth):
            c.account()


def test_idempotent_and_none_codes():
    c, _, _ = mk([err(-4046)])
    c.set_isolated("X")
    c, _, _ = mk([err(-2011)])
    c.cancel_order("X", "cid")
    c, _, _ = mk([err(-2013)])
    assert c.query_order("X", "cid") is None
    c, _, _ = mk([err(-2019, "margin")])
    with pytest.raises(ExchangeReject) as ei:
        c.new_market("X", "BUY", "1", "cid", False)
    assert ei.value.code == -2019 and ei.value.http == 400


def test_weight_thresholds_and_protective():
    c, net, clock = mk([Resp(200, [], {"X-MBX-USED-WEIGHT-1M": "1250"}), Resp(200, []), Resp(200, [])])
    c.account()
    c.position_risk()                                  # soft: ertelenir
    assert clock["sleeps"] and net.calls.__len__() == 2
    c.position_risk(protective=True)
    assert len(clock["sleeps"]) == 1
    c, net, clock = mk([Resp(200, [], {"X-MBX-USED-WEIGHT-1M": "1850"}), Resp(200, {"orderId": 1})])
    c.account()
    with pytest.raises(ExchangeBan):
        c.position_risk()
    assert len(net.calls) == 1
    c.new_conditional("X", "STOP_MARKET", "SELL", "1", "2", "cid", "MARK_PRICE")     # protective varsayılan
    assert len(net.calls) == 2


def test_order_cap():
    c, net, _ = mk([Resp(200, {})] * 30, order_cap_10s=3)
    for i in range(3):
        c.new_market("X", "BUY", "1", f"c{i}", False)
    with pytest.raises(ExchangeReject) as ei:
        c.new_market("X", "BUY", "1", "c9", False)
    assert ei.value.msg == "order_rate_cap" and len(net.calls) == 3
    c.new_market("X", "SELL", "1", "c10", True)           # reduceOnly koruyucu: borsa sınırının %80'ine kadar
    assert len(net.calls) == 4
    assert c.health()["order_count_10s"] == 4


def test_no_secret_leak(caplog):
    caplog.set_level(logging.DEBUG)
    leaky = f"bad key {KEY} secret {SECRET} signature=" + "ab" * 32
    cases = [(ConnectionError(f"https://x?signature=abc {SECRET}"),), (Resp(503, None, text=leaky),), (err(-1111, leaky),),
             (err(-2015, leaky),), (Resp(418, None, text=leaky),), (Resp(403, {"code": 1, "msg": leaky}),)]
    for (resp,) in cases:
        for call in (lambda c: c.new_market("X", "BUY", "1", "cid", False), lambda c: c.open_orders()):
            c, _, _ = mk([resp] * 5)
            try:
                call(c)
            except Exception as e:  # noqa: BLE001
                s = f"{e!s}|{e!r}"
                assert SECRET not in s and KEY not in s and "signature" not in s.replace("signature=***", "")
                assert len(str(e).split("msg=", 1)[-1]) <= 200
    text = caplog.text
    assert SECRET not in text and KEY not in text and "signature=ab" not in text
    c, _, _ = mk([])
    assert SECRET not in repr(c) and KEY not in repr(c) and SECRET not in str(c)
    c, _, _ = mk([err(-1111, "bad qty")])
    with pytest.raises(ExchangeReject) as ei:
        c.new_market("XRPUSDT", "BUY", "1", "cid", False)
    assert str(ei.value) == "POST /fapi/v1/order http=400 code=-1111 msg=bad qty"


def test_conditional_modes_and_paths():
    c, net, _ = mk([Resp(200, {}), Resp(200, {})])
    c.new_conditional("X", "STOP_MARKET", "SELL", "5", "2.0346", "cid", "MARK_PRICE")
    assert net.calls[0][1].startswith("https://testnet.binancefuture.com/fapi/v1/algoOrder?algoType=CONDITIONAL&symbol=X&side=SELL&type=STOP_MARKET&quantity=5&triggerPrice=2.0346&workingType=MARK_PRICE&reduceOnly=true&priceProtect=false&clientAlgoId=cid&")
    c.cancel_conditional("X", "cid")
    assert net.calls[1][0] == "DELETE" and "/fapi/v1/algoOrder?clientAlgoId=cid" in net.calls[1][1]
    c, net, _ = mk([Resp(200, {})], conditional_mode="classic")
    c.new_conditional("X", "STOP_MARKET", "SELL", "5", "2.0346", "cid", "MARK_PRICE")
    assert "/fapi/v1/order?symbol=X&side=SELL&type=STOP_MARKET&quantity=5&stopPrice=2.0346" in net.calls[0][1]
    with pytest.raises(ValueError):
        c.new_conditional("X", "LIMIT", "SELL", "5", "2", "cid", "MARK_PRICE")


def test_user_trades_windows_dedupe():
    day = 24 * 3600 * 1000
    t0 = 1_000_000
    c, net, _ = mk([Resp(200, [{"id": 1, "time": t0 + 5}]), Resp(200, [{"id": 1, "time": t0 + 5}, {"id": 2, "time": t0 + 8 * day}])])
    out = c.user_trades("X", t0, t0 + 9 * day)
    assert [x["id"] for x in out] == [1, 2] and len(net.calls) == 2


def test_api_restrictions_live_only_and_base():
    c, _, _ = mk([])
    with pytest.raises(Exception):
        c.api_restrictions()
    c, net, _ = mk([Resp(200, {"enableReading": True})], env="live")
    assert c.api_restrictions()["enableReading"] is True
    assert net.calls[0][1].startswith("https://api.binance.com/sapi/v1/account/apiRestrictions?")


def test_health_and_constructor_guards():
    c, _, clock = mk([Resp(200, {"serverTime": 1_798_449_600_000 + 2500})])
    assert c.sync_time() == 2500 and c.health()["clock_offset_ms"] == 2500
    with pytest.raises(ValueError):
        SignedRestClient(env="prod", api_key=KEY, api_secret=SECRET, now_ms=lambda: 0, sleep=lambda s: None)
    with pytest.raises(ValueError):
        SignedRestClient(env="live", api_key="", api_secret=SECRET, now_ms=lambda: 0, sleep=lambda s: None)
