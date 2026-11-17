"""WP-B1 (11-canli-broker.md §3.2, §4, §16) imzalı Binance vadeli REST istemcisi: şartname testleri.

Bağımsız test ajanı; yalnız şartnameden yazıldı. Gerçek ağ/saat/uyku/anahtar yok.
`# SPEC-AMBIGUOUS:` ile işaretli yerler şartnamenin adlandırmadığı noktalardaki en gerçek okumadır.
"""
from __future__ import annotations

import hashlib
import hmac
import json
import logging
import time
import traceback
from decimal import Decimal
from urllib.parse import parse_qsl, urlencode, urlsplit

import pytest

from trader_engine.exchange import binance_rest as B
from trader_engine.marketdata.rest_public import ExchangeBan, ExchangeError

# ----------------------------------------------------------------------------- sabitler
SECRET = "SIZMA-TESTI-" + "g" * 24            # gizli değer (>= 32 karakter)
API_KEY = "ANAHTAR-SIZMA-TESTI-" + "k" * 16     # anahtar değeri (>= 32 karakter)
T0 = 1_798_449_600_000                          # §16.1 zaman damgası


# ----------------------------------------------------------------------------- test araçları
class Resp:
    def __init__(self, status=200, body=None, headers=None, text=None):
        self.status_code = status
        self._b = body
        self.headers = headers or {}
        self.text = text if text is not None else (json.dumps(body) if body is not None else "")
        self.content = self.text.encode()

    @property
    def ok(self):
        return self.status_code < 400

    def json(self):
        if self._b is None:
            raise ValueError("no json")
        return self._b


def err(http, code, msg="hata", headers=None):
    return Resp(http, {"code": code, "msg": msg}, headers)


class Clock:
    """now_ms ve sleep enjekte edilir; uyku saati ilerletir."""

    def __init__(self, ms=T0):
        self.ms = ms
        self.sleeps = []
        self.events = []

    def now_ms(self):
        return self.ms

    def sleep(self, s):
        self.sleeps.append(s)
        self.events.append(("sleep", s))
        self.ms += int(round(s * 1000))


class Sess:
    """Sahte requests.Session. SPEC-AMBIGUOUS: oturum arayüzü şartnamede yok; `request(method, url, ...)` ile
    get/post/delete/put kısayolları desteklenir. Sorgu dizgesi url'de ya da `params=` içinde olabilir."""

    def __init__(self, seq, clock=None, latency_ms=0):
        self.seq = list(seq)
        self.calls = []
        self.clock = clock
        self.latency_ms = latency_ms

    def request(self, method, url, **kw):
        if self.clock is not None:
            self.clock.events.append(("call", urlsplit(url).path))
        c = dict(method=method.upper(), url=url, kw=kw, at=self.clock.ms if self.clock else None)
        c["path"] = urlsplit(url).path
        c["base"] = "%s://%s" % (urlsplit(url).scheme, urlsplit(url).netloc)
        c["query"] = self._query(url, kw)
        c["headers"] = {k.lower(): v for k, v in (kw.get("headers") or {}).items()}
        self.calls.append(c)
        if not self.seq:
            raise AssertionError("beklenmeyen ek istek: %s %s" % (method, url))
        x = self.seq.pop(0)
        if self.clock is not None and self.latency_ms:
            self.clock.ms += self.latency_ms
        if callable(x) and not isinstance(x, Exception):
            x = x(c)
        if isinstance(x, BaseException):
            raise x
        return x

    @staticmethod
    def _query(url, kw):
        q = urlsplit(url).query
        p = kw.get("params")
        if not q and p:
            q = p if isinstance(p, str) else urlencode(p)
        return q

    def get(self, url, **kw):
        return self.request("GET", url, **kw)

    def post(self, url, **kw):
        return self.request("POST", url, **kw)

    def delete(self, url, **kw):
        return self.request("DELETE", url, **kw)

    def put(self, url, **kw):
        return self.request("PUT", url, **kw)


def qd(call):
    return dict(parse_qsl(call["query"], keep_blank_values=True))


def mk(seq, env="live", clock=None, latency_ms=0, **kw):
    clk = clock or Clock()
    s = Sess(seq, clk, latency_ms)
    cl = B.SignedRestClient(env=env, api_key=API_KEY, api_secret=SECRET, session=s,
                            now_ms=clk.now_ms, sleep=clk.sleep, **kw)
    return cl, s, clk


def sig_ok(call, secret=SECRET):
    q = call["query"]
    head, _, sig = q.rpartition("&signature=")
    assert head, "signature en sona eklenmeli: %r" % q
    return hmac.new(secret.encode(), head.encode(), hashlib.sha256).hexdigest() == sig


@pytest.fixture(autouse=True)
def no_real_time(monkeypatch):
    """Gerçek saat/uyku yasak. logging'in kendi kayıt zamanı (time.time_ns) istisnadır; çağıran logging ise geçer."""
    import sys

    def mk_forbid(name, real):
        def forbid(*a, **k):
            mod = sys._getframe(1).f_globals.get("__name__", "")
            if mod.split(".")[0] in ("logging", "_pytest", "pluggy"):
                return real(*a, **k)
            raise AssertionError("gerçek saat/uyku çağrıldı: time.%s (%s)" % (name, mod))
        return forbid
    for n in ("time", "sleep", "monotonic", "time_ns", "perf_counter"):
        monkeypatch.setattr(time, n, mk_forbid(n, getattr(time, n)))


# ----------------------------------------------------------------------------- 1. imza (§16.1, §4.1)
SIGNED_QS_HEAD = ("symbol=XRPUSDT&side=BUY&type=MARKET&quantity=10&newClientOrderId=trLe-df350276c5ff969f6d18cd15"
                  "&newOrderRespType=RESULT&recvWindow=5000&timestamp=1798449600000")
SIGNED_EXPECTED = "b4ecba7924301b8e54b162bcfd1acfb2c42f5b30d0b083b2bab9ce3af8a737e9"


def test_signature_example_16_1_exact_via_request():
    # §16.1 gizli anahtarı `ornek-gizli-anahtar`; offset 0 (sync çağrılmadı).
    # SPEC-AMBIGUOUS: ilk istekte kendiliğinden sync_time() çağrılmadığı varsayıldı (şartname: açılışta LiveBroker çağırır).
    clk = Clock(T0)
    s = Sess([Resp(200, {"orderId": 1})], clk)
    cl = B.SignedRestClient(env="live", api_key=API_KEY, api_secret="ornek-gizli-anahtar", session=s,
                            now_ms=clk.now_ms, sleep=clk.sleep)
    params = {"symbol": "XRPUSDT", "side": "BUY", "type": "MARKET", "quantity": "10",
              "newClientOrderId": "trLe-df350276c5ff969f6d18cd15", "newOrderRespType": "RESULT"}
    cl.request("POST", "/fapi/v1/order", params, kind="order")
    (c,) = s.calls
    assert c["query"] == SIGNED_QS_HEAD + "&signature=" + SIGNED_EXPECTED
    assert c["headers"]["x-mbx-apikey"] == API_KEY
    assert c["method"] == "POST" and c["path"] == "/fapi/v1/order"


def test_signature_example_matches_independent_hmac():
    assert hmac.new(b"ornek-gizli-anahtar", SIGNED_QS_HEAD.encode(), hashlib.sha256).hexdigest() == SIGNED_EXPECTED


def test_new_market_wrapper_produces_16_1_query():
    # SPEC-AMBIGUOUS: new_market(reduce_only=False) `reduceOnly` parametresini hiç göndermez (§5.3: yalnız çıkışta).
    clk = Clock(T0)
    s = Sess([Resp(200, {"status": "FILLED"})], clk)
    cl = B.SignedRestClient(env="live", api_key=API_KEY, api_secret="ornek-gizli-anahtar", session=s,
                            now_ms=clk.now_ms, sleep=clk.sleep)
    cl.new_market("XRPUSDT", "BUY", "10", "trLe-df350276c5ff969f6d18cd15", False)
    assert s.calls[0]["query"] == SIGNED_QS_HEAD + "&signature=" + SIGNED_EXPECTED


def test_params_in_query_string_body_empty_and_signature_last():
    cl, s, _ = mk([Resp(200, {})])
    cl.request("POST", "/fapi/v1/order", {"symbol": "XRPUSDT", "quantity": "1"}, kind="order")
    c = s.calls[0]
    assert not c["kw"].get("data") and not c["kw"].get("json")
    keys = [k for k, _ in parse_qsl(c["query"])]
    assert keys == ["symbol", "quantity", "recvWindow", "timestamp", "signature"]
    assert sig_ok(c)


def test_recv_window_configurable_and_default():
    cl, s, _ = mk([Resp(200, {}), Resp(200, {})], recv_window_ms=7000)
    cl.request("GET", "/fapi/v2/account", None, kind="read")
    assert qd(s.calls[0])["recvWindow"] == "7000"
    cl2, s2, _ = mk([Resp(200, {})])
    cl2.request("GET", "/fapi/v2/account", None, kind="read")
    assert qd(s2.calls[0])["recvWindow"] == "5000"


def test_unsigned_request_has_no_signature_or_timestamp():
    cl, s, _ = mk([Resp(200, {"symbols": []})])
    cl.exchange_info()
    c = s.calls[0]
    assert c["path"] == "/fapi/v1/exchangeInfo"
    assert "signature" not in c["query"] and "timestamp" not in c["query"]


def test_base_urls_by_env():
    cl, s, _ = mk([Resp(200, {})], env="live")
    cl.request("GET", "/fapi/v1/time", None, kind="read", signed=False)
    assert s.calls[0]["base"] == "https://fapi.binance.com"
    cl, s, _ = mk([Resp(200, {})], env="testnet")
    cl.request("GET", "/fapi/v1/time", None, kind="read", signed=False)
    # [V-2] testnet tabanı
    assert s.calls[0]["base"] == "https://testnet.binancefuture.com"


def test_api_restrictions_uses_spot_base_on_live():
    cl, s, _ = mk([Resp(200, {"enableReading": True})], env="live")
    cl.api_restrictions()
    assert s.calls[0]["base"] == "https://api.binance.com"
    assert s.calls[0]["path"] == "/sapi/v1/account/apiRestrictions"
    assert sig_ok(s.calls[0])


# ----------------------------------------------------------------------------- 2. sayı biçimleme (§4.1)
@pytest.mark.parametrize("val,expected", [
    (1e-05, "0.00001"),
    (1e-07, "0.0000001"),
    (10.0, "10"),
    (2.50, "2.5"),
    (0.1, "0.1"),
    (1.5e20, "150000000000000000000"),
    (Decimal("1E-7"), "0.0000001"),
    (Decimal("1E+2"), "100"),
    (Decimal("100E+3"), "100000"),
    (Decimal("2.5000"), "2.5"),
    (Decimal("0.00010000"), "0.0001"),
    (5, "5"),
])
def test_number_formatting_no_exponent_no_trailing_zeros(val, expected):
    cl, s, _ = mk([Resp(200, {})])
    cl.request("POST", "/fapi/v1/order", {"quantity": val}, kind="order")
    q = qd(s.calls[0])
    assert q["quantity"] == expected
    assert "e" not in q["quantity"].lower() and "E" not in q["quantity"]


def test_float_goes_through_decimal_repr():
    # `Decimal(repr(x))`: 0.30000000000000004 olduğu gibi (float ikili artığı kırpılmaz, ama üstel de yok)
    cl, s, _ = mk([Resp(200, {})])
    cl.request("POST", "/fapi/v1/order", {"price": 0.1 + 0.2}, kind="order")
    assert qd(s.calls[0])["price"] == "0.30000000000000004"


def test_bool_formats_lowercase():
    # SPEC-AMBIGUOUS: bool biçimi şartnamede yalnız `reduceOnly=true` örneğiyle geçer; küçük harf varsayıldı.
    cl, s, _ = mk([Resp(200, {})])
    cl.request("POST", "/fapi/v1/order", {"reduceOnly": True, "priceProtect": False}, kind="order")
    q = qd(s.calls[0])
    assert q["reduceOnly"] == "true" and q["priceProtect"] == "false"


def test_set_leverage_and_int_params():
    cl, s, _ = mk([Resp(200, {"leverage": 3})])
    cl.set_leverage("XRPUSDT", 3)
    c = s.calls[0]
    assert c["method"] == "POST" and c["path"] == "/fapi/v1/leverage"
    assert qd(c)["leverage"] == "3" and qd(c)["symbol"] == "XRPUSDT"


def test_mark_price_returns_decimal_unsigned():
    cl, s, _ = mk([Resp(200, {"symbol": "XRPUSDT", "markPrice": "2.03457000"})])
    p = cl.mark_price("XRPUSDT")
    assert isinstance(p, Decimal) and p == Decimal("2.03457")
    assert s.calls[0]["path"] == "/fapi/v1/premiumIndex" and "signature" not in s.calls[0]["query"]


# ----------------------------------------------------------------------------- 3. saat (§4.2) ve -1021 (§4.3)
def test_sync_time_midpoint_offset_and_used_in_timestamp():
    # istemci t0=T, yanıt T+100'de gelir; sunucu saati (T+50)+2500 => offset 2500
    clk = Clock(T0)
    s = Sess([lambda c: Resp(200, {"serverTime": T0 + 50 + 2500}), Resp(200, {})], clk, latency_ms=100)
    cl = B.SignedRestClient(env="live", api_key=API_KEY, api_secret=SECRET, session=s,
                            now_ms=clk.now_ms, sleep=clk.sleep)
    off = cl.sync_time()
    # SPEC-AMBIGUOUS: dönüş değeri "ms" = offset kabul edildi (imza `-> int # ms`, yorum "offset = serverTime − (t0+t1)/2").
    assert off == 2500
    assert cl.health()["clock_offset_ms"] == 2500
    assert s.calls[0]["method"] == "GET" and s.calls[0]["path"] == "/fapi/v1/time"
    assert "signature" not in s.calls[0]["query"]
    cl.request("GET", "/fapi/v2/account", None, kind="read")
    # kesin kontrol: timestamp = now_ms() (istek anı) + offset; istek anında saat clk.ms - latency (yanıt gecikmesi sonradan eklenir)
    assert int(qd(s.calls[1])["timestamp"]) - 2500 == s.calls[1]["at"]


def test_sync_time_large_offset_warns():
    # SPEC-AMBIGUOUS: |offset|>1000 ms için WARNING'in istemcide mi motorda mı üretildiği belirsiz; istemcide varsayıldı.
    clk = Clock(T0)
    s = Sess([Resp(200, {"serverTime": T0 + 1500})], clk)
    cl = B.SignedRestClient(env="live", api_key=API_KEY, api_secret=SECRET, session=s,
                            now_ms=clk.now_ms, sleep=clk.sleep)
    import logging as _l
    recs = []

    class H(_l.Handler):
        def emit(self, r):
            recs.append(r)
    h = H(level=_l.DEBUG)
    root = _l.getLogger()
    root.addHandler(h)
    try:
        cl.sync_time()
    finally:
        root.removeHandler(h)
    assert any(r.levelno >= _l.WARNING for r in recs)


@pytest.mark.parametrize("kind,method,path", [("read", "GET", "/fapi/v2/account"), ("order", "POST", "/fapi/v1/order")])
def test_minus_1021_syncs_and_retries_once(kind, method, path):
    clk = Clock(T0)
    s = Sess([err(400, -1021, "Timestamp for this request is outside of the recvWindow."),
              Resp(200, {"serverTime": T0 + 3000}), Resp(200, {"ok": 1})], clk)
    cl = B.SignedRestClient(env="live", api_key=API_KEY, api_secret=SECRET, session=s,
                            now_ms=clk.now_ms, sleep=clk.sleep)
    assert cl.request(method, path, {"symbol": "XRPUSDT"}, kind=kind) == {"ok": 1}
    assert [c["path"] for c in s.calls] == [path, "/fapi/v1/time", path]
    first, again = s.calls[0], s.calls[2]
    assert int(qd(first)["timestamp"]) == T0
    assert int(qd(again)["timestamp"]) == T0 + 3000          # yeni offset uygulandı
    a, b = qd(first), qd(again)
    for k in ("timestamp", "signature"):
        a.pop(k), b.pop(k)
    assert a == b                                            # aynı parametreler (aynı newClientOrderId vb.)
    assert sig_ok(again)


@pytest.mark.parametrize("kind,method,path", [("read", "GET", "/fapi/v2/account"), ("order", "POST", "/fapi/v1/order")])
def test_minus_1021_twice_is_not_retried_again_for_order(kind, method, path):
    clk = Clock(T0)
    s = Sess([err(400, -1021), Resp(200, {"serverTime": T0 + 3000}), err(400, -1021),
              Resp(200, {"serverTime": T0 + 3000}), Resp(200, {})], clk)
    cl = B.SignedRestClient(env="live", api_key=API_KEY, api_secret=SECRET, session=s,
                            now_ms=clk.now_ms, sleep=clk.sleep)
    if kind == "order":
        with pytest.raises(ExchangeError):
            cl.request(method, path, {"symbol": "XRPUSDT"}, kind=kind)
        assert [c["path"] for c in s.calls].count(path) == 2     # tek tekrar
    else:
        # SPEC-AMBIGUOUS: okuma için ikinci -1021 sonrası davranış (max_attempts içinde tekrar mı) belirsiz; yalnız sonlanır.
        try:
            cl.request(method, path, {"symbol": "XRPUSDT"}, kind=kind)
        except ExchangeError:
            pass
        assert [c["path"] for c in s.calls].count(path) <= 4


def test_minus_1021_retry_then_5xx_on_order_is_uncertain_without_third_post():
    clk = Clock(T0)
    s = Sess([err(400, -1021), Resp(200, {"serverTime": T0 + 3000}), Resp(503, {})], clk)
    cl = B.SignedRestClient(env="live", api_key=API_KEY, api_secret=SECRET, session=s,
                            now_ms=clk.now_ms, sleep=clk.sleep)
    with pytest.raises(B.ExchangeUncertain):
        cl.request("POST", "/fapi/v1/order", {"symbol": "XRPUSDT"}, kind="order")
    assert [c["path"] for c in s.calls].count("/fapi/v1/order") == 2


# ----------------------------------------------------------------------------- 4. yeniden deneme (§4.3)
@pytest.mark.parametrize("fail", [
    ConnectionError("boom"), TimeoutError("zaman aşımı"), OSError("reset"),
    Resp(500, {}), Resp(502, {}), Resp(503, {}), Resp(504, {}),
    Resp(503, {"code": -1001, "msg": "Internal error"}), Resp(503, {"code": -1007, "msg": "Timeout waiting"}),
])
def test_order_post_never_retried_on_network_error_or_5xx(fail):
    cl, s, clk = mk([fail, Resp(200, {"orderId": 1})])
    with pytest.raises(B.ExchangeUncertain):
        cl.request("POST", "/fapi/v1/order", {"symbol": "XRPUSDT", "quantity": "1"}, kind="order")
    assert len(s.calls) == 1 and clk.sleeps == []


def test_order_uncertain_is_exchange_error_subclass_and_http_attr():
    cl, _, _ = mk([Resp(503, {})])
    with pytest.raises(B.ExchangeUncertain) as e:
        cl.request("POST", "/fapi/v1/order", {}, kind="order")
    assert isinstance(e.value, ExchangeError) and e.value.http == 503
    cl, _, _ = mk([ConnectionError("x")])
    with pytest.raises(B.ExchangeUncertain) as e:
        cl.request("POST", "/fapi/v1/order", {}, kind="order")
    assert e.value.http is None


def test_new_market_and_new_conditional_never_retried():
    for fn in (lambda c: c.new_market("XRPUSDT", "BUY", "10", "trLe-a", False),
               lambda c: c.new_market("XRPUSDT", "SELL", "10", "trLx-a", True),
               lambda c: c.new_conditional("XRPUSDT", "STOP_MARKET", "SELL", "10", "2.0346", "trLs-a", "MARK_PRICE")):
        cl, s, clk = mk([Resp(503, {}), Resp(200, {})])
        with pytest.raises(B.ExchangeUncertain):
            fn(cl)
        assert len(s.calls) == 1 and clk.sleeps == []


@pytest.mark.parametrize("kind,method,path", [
    ("read", "GET", "/fapi/v2/account"), ("cancel", "DELETE", "/fapi/v1/order"), ("setup", "POST", "/fapi/v1/leverage")])
def test_non_order_kinds_retry_with_exponential_backoff(kind, method, path):
    # max_attempts=4 => 3 bekleme: 1, 2, 4 sn
    cl, s, clk = mk([Resp(503, {}), ConnectionError("x"), Resp(500, {}), Resp(200, {"ok": 1})], max_attempts=4)
    assert cl.request(method, path, {"symbol": "XRPUSDT"}, kind=kind) == {"ok": 1}
    assert len(s.calls) == 4
    assert clk.sleeps == [1, 2, 4]
    # her tekrarda yeni imza/zaman damgası geçerli
    assert all(sig_ok(c) for c in s.calls)


@pytest.mark.parametrize("kind,method,path", [("read", "GET", "/fapi/v2/account"), ("cancel", "DELETE", "/fapi/v1/order")])
def test_retry_exhausted_raises_uncertain(kind, method, path):
    cl, s, _ = mk([Resp(503, {})] * 4, max_attempts=4)
    with pytest.raises(B.ExchangeUncertain):
        cl.request(method, path, None, kind=kind)
    assert len(s.calls) == 4


def test_read_retries_minus_1001_and_1007():
    cl, s, _ = mk([Resp(503, {"code": -1001, "msg": "x"}), Resp(503, {"code": -1007, "msg": "y"}), Resp(200, {"ok": 1})])
    assert cl.request("GET", "/fapi/v2/account", None, kind="read") == {"ok": 1}
    assert len(s.calls) == 3


def test_timeouts_passed_per_kind():
    # SPEC-AMBIGUOUS: oturuma `timeout=` anahtar sözcüğüyle geçtiği varsayıldı; emir için (bağlan, oku) = (2.0, 3.0).
    cl, s, _ = mk([Resp(200, {}), Resp(200, {})])
    cl.request("POST", "/fapi/v1/order", {}, kind="order")
    cl.request("GET", "/fapi/v2/account", None, kind="read")
    assert tuple(s.calls[0]["kw"]["timeout"]) == (2.0, 3.0)
    assert s.calls[1]["kw"]["timeout"] == 10.0


def test_other_4xx_with_code_is_reject_no_retry_with_attrs():
    cl, s, clk = mk([err(400, -2019, "Margin is insufficient."), Resp(200, {})])
    with pytest.raises(B.ExchangeReject) as e:
        cl.request("POST", "/fapi/v1/order", {"symbol": "XRPUSDT"}, kind="order")
    assert (e.value.code, e.value.http) == (-2019, 400) and "insufficient" in e.value.msg
    assert len(s.calls) == 1 and clk.sleeps == []
    cl, s, _ = mk([err(400, -4164, "x"), Resp(200, {})])
    with pytest.raises(B.ExchangeReject):
        cl.request("GET", "/fapi/v2/account", None, kind="read")
    assert len(s.calls) == 1


def test_reject_message_format_and_truncation():
    # SPEC-AMBIGUOUS: biçim `yöntem yol http=<kod> code=<kod> msg=<≤200>` birebir kabul edildi.
    cl, _, _ = mk([err(400, -1102, "m" * 500)])
    with pytest.raises(B.ExchangeReject) as e:
        cl.request("POST", "/fapi/v1/order", {"symbol": "XRPUSDT"}, kind="order")
    t = str(e.value)
    assert t.startswith("POST /fapi/v1/order http=400 code=-1102 msg=")
    assert t.endswith("m" * 200) and "m" * 201 not in t
    assert "XRPUSDT" not in t


def test_cancel_idempotent_codes_are_success():
    for code in (-2011, -2013):
        cl, s, _ = mk([err(400, code, "Unknown order sent.")])
        cl.cancel_order("XRPUSDT", "trLx-a")                    # istisna yok
        assert s.calls[0]["method"] == "DELETE" and s.calls[0]["path"] == "/fapi/v1/order"
        cl, s, _ = mk([err(400, code, "Unknown order sent.")])
        cl.request("DELETE", "/fapi/v1/order", {"symbol": "XRPUSDT"}, kind="cancel")   # başarı sayılır
        assert len(s.calls) == 1


def test_cancel_conditional_idempotent():
    cl, s, _ = mk([err(400, -2011)])
    cl.cancel_conditional("XRPUSDT", "trLs-a")
    # [V-1] algo ucu
    assert s.calls[0]["method"] == "DELETE" and s.calls[0]["path"] == "/fapi/v1/algoOrder"


def test_setup_idempotent_codes_are_success():
    cl, s, _ = mk([err(400, -4046, "No need to change margin type.")])
    cl.set_isolated("XRPUSDT")
    assert qd(s.calls[0])["marginType"] == "ISOLATED" and s.calls[0]["path"] == "/fapi/v1/marginType"
    cl, s, _ = mk([err(400, -4059, "No need to change position side.")])
    cl.set_one_way()
    assert s.calls[0]["path"] == "/fapi/v1/positionSide/dual" and qd(s.calls[0])["dualSidePosition"] == "false"
    # başka kodlar başarı sayılmaz
    cl, _, _ = mk([err(400, -4046 - 1)])
    with pytest.raises(B.ExchangeReject):
        cl.request("POST", "/fapi/v1/marginType", {}, kind="setup")


def test_minus_4046_is_not_success_for_order_kind():
    cl, _, _ = mk([err(400, -4046)])
    with pytest.raises(B.ExchangeReject):
        cl.request("POST", "/fapi/v1/order", {}, kind="order")


def test_query_order_unknown_returns_none():
    cl, s, _ = mk([err(400, -2013, "Order does not exist.")])
    assert cl.query_order("XRPUSDT", "trLe-a") is None
    assert s.calls[0]["method"] == "GET" and s.calls[0]["path"] == "/fapi/v1/order"
    cl, _, _ = mk([err(400, -2013)])
    assert cl.query_conditional("XRPUSDT", "trLs-a") is None


def test_conditional_modes_endpoints_and_params():
    # §5.4 / [V-1]
    cl, s, _ = mk([Resp(200, {})], conditional_mode="algo")
    cl.new_conditional("XRPUSDT", "STOP_MARKET", "SELL", "10", "2.0346", "trLs-f506d5650826460114e3bf1b", "MARK_PRICE")
    c = s.calls[0]
    assert c["method"] == "POST" and c["path"] == "/fapi/v1/algoOrder"
    # SPEC-AMBIGUOUS: parametre sırası belirtilmedi; sözlük olarak karşılaştırılır. `side`'ın pozisyonun tersi olması çağırana ait.
    d = qd(c)
    for k, v in dict(algoType="CONDITIONAL", symbol="XRPUSDT", side="SELL", type="STOP_MARKET", quantity="10",
                     triggerPrice="2.0346", workingType="MARK_PRICE", reduceOnly="true", priceProtect="false",
                     clientAlgoId="trLs-f506d5650826460114e3bf1b").items():
        assert d[k] == v, k
    cl, s, _ = mk([Resp(200, {})], conditional_mode="classic")
    cl.new_conditional("XRPUSDT", "STOP_MARKET", "SELL", "10", "2.0346", "trLs-f506d5650826460114e3bf1b", "MARK_PRICE")
    c = s.calls[0]
    assert c["path"] == "/fapi/v1/order"
    d = qd(c)
    for k, v in dict(symbol="XRPUSDT", side="SELL", type="STOP_MARKET", quantity="10", stopPrice="2.0346",
                     workingType="MARK_PRICE", reduceOnly="true",
                     newClientOrderId="trLs-f506d5650826460114e3bf1b").items():
        assert d[k] == v, k


def test_open_conditionals_algo_path():
    cl, s, _ = mk([Resp(200, [])], conditional_mode="algo")
    assert cl.open_conditionals("XRPUSDT") == []
    assert s.calls[0]["path"] == "/fapi/v1/openAlgoOrders" and qd(s.calls[0])["symbol"] == "XRPUSDT"


def test_wrapper_paths():
    cl, s, _ = mk([Resp(200, {}), Resp(200, []), Resp(200, []), Resp(200, {"takerCommissionRate": "0.0004"})])
    cl.account()
    cl.position_risk("XRPUSDT")
    cl.open_orders()
    cl.commission_rate("XRPUSDT")
    assert [c["path"] for c in s.calls] == ["/fapi/v2/account", "/fapi/v2/positionRisk", "/fapi/v1/openOrders",
                                           "/fapi/v1/commissionRate"]
    assert all(c["method"] == "GET" and sig_ok(c) for c in s.calls)
    assert "symbol" not in qd(s.calls[2])      # sembolsüz tam tarama


def test_user_trades_split_into_7_day_windows():
    # SPEC-AMBIGUOUS: pencere sınırı `endTime - startTime <= 7 gün` ve startTime/endTime adları (Binance sözleşmesi) varsayıldı.
    day = 86_400_000
    start, end = T0, T0 + 15 * day
    cl, s, _ = mk([Resp(200, [])] * 5)
    assert cl.user_trades("XRPUSDT", start, end) == []
    ut = [c for c in s.calls if c["path"] == "/fapi/v1/userTrades"]
    assert len(ut) >= 3
    for c in ut:
        q = qd(c)
        assert int(q["endTime"]) - int(q["startTime"]) <= 7 * day
    assert int(qd(ut[0])["startTime"]) <= start and max(int(qd(c)["endTime"]) for c in ut) >= end


# ----------------------------------------------------------------------------- 5. 429 sessizliği, 418/451/403/401
def calls_after(s, t_ms):
    return [c for c in s.calls if c["at"] >= t_ms]


def test_429_read_waits_retry_after_then_retries():
    cl, s, clk = mk([err(429, -1003, "Too many", {"Retry-After": "7"}), Resp(200, {"ok": 1})])
    assert cl.request("GET", "/fapi/v2/account", None, kind="read") == {"ok": 1}
    assert sum(clk.sleeps) >= 7
    assert s.calls[1]["at"] - s.calls[0]["at"] >= 7000     # sessizlik: tekrar en erken Retry-After sonra


def test_429_order_is_reject_without_retry_and_code_none():
    cl, s, clk = mk([Resp(429, {"code": -1003, "msg": "Too many requests"}, {"Retry-After": "30"}), Resp(200, {})])
    with pytest.raises(B.ExchangeReject) as e:
        cl.request("POST", "/fapi/v1/order", {"symbol": "XRPUSDT"}, kind="order")
    assert e.value.code is None and e.value.http == 429
    assert len(s.calls) == 1


@pytest.mark.parametrize("protective", [False, True])
@pytest.mark.parametrize("kind,method,path", [("read", "GET", "/fapi/v2/positionRisk"), ("order", "POST", "/fapi/v1/order")])
def test_429_silence_applies_to_everything_including_protective(protective, kind, method, path):
    cl, s, clk = mk([Resp(429, {"code": -1003, "msg": "x"}, {"Retry-After": "30"}),
                     Resp(200, {}), Resp(200, {}), Resp(200, {})])
    t429 = None
    try:
        cl.request("POST", "/fapi/v1/order", {"symbol": "XRPUSDT"}, kind="order")
    except ExchangeError:
        pass
    t429 = s.calls[0]["at"]
    clk.ms += 10_000                      # pencere (30 sn) içindeyiz
    try:
        cl.request(method, path, {"symbol": "XRPUSDT"}, kind=kind, protective=protective)
    except ExchangeError:
        pass                              # sessizlik hata olarak da yansıyabilir
    # SPEC-AMBIGUOUS: sessizlik sırasındaki istek ya bekler (sleep) ya hata yükseltir; her iki halde pencere bitmeden
    # borsaya hiçbir istek gitmemeli.
    for c in s.calls[1:]:
        assert c["at"] >= t429 + 30_000


def test_418_raises_ban_with_retry_after_and_no_requests_until_window_ends():
    cl, s, clk = mk([Resp(418, {"code": -1003, "msg": "banned"}, {"Retry-After": "120"}), Resp(200, {}), Resp(200, {})])
    with pytest.raises(ExchangeBan) as e:
        cl.request("GET", "/fapi/v2/account", None, kind="read")
    assert e.value.http == 418 and e.value.retry_after_s == 120
    assert len(s.calls) == 1
    t = s.calls[0]["at"]
    assert cl.health()["ban_until_ms"] == t + 120_000
    clk.ms += 5_000
    for kind, protective in (("read", False), ("order", True)):
        try:
            cl.request("POST" if kind == "order" else "GET", "/fapi/v1/order", {}, kind=kind, protective=protective)
        except ExchangeError:
            pass
    # SPEC-AMBIGUOUS: pencere içi istekler bekletilebilir ya da ExchangeBan olabilir; borsaya gitmemeli.
    for c in s.calls[1:]:
        assert c["at"] >= t + 120_000


def test_418_for_order_is_also_ban_not_reject():
    cl, s, _ = mk([Resp(418, {}, {"Retry-After": "60"})])
    with pytest.raises(ExchangeBan) as e:
        cl.request("POST", "/fapi/v1/order", {}, kind="order")
    assert e.value.http == 418 and len(s.calls) == 1


def test_requests_resume_after_ban_window():
    cl, s, clk = mk([Resp(418, {}, {"Retry-After": "60"}), Resp(200, {"ok": 1})])
    with pytest.raises(ExchangeBan):
        cl.request("GET", "/fapi/v2/account", None, kind="read")
    clk.ms += 61_000
    assert cl.request("GET", "/fapi/v2/account", None, kind="read") == {"ok": 1}


@pytest.mark.parametrize("kind,method", [("read", "GET"), ("order", "POST"), ("cancel", "DELETE"), ("setup", "POST")])
def test_451_is_ban_no_retry(kind, method):
    cl, s, clk = mk([Resp(451, {"code": 0, "msg": "Service unavailable from a restricted location"}), Resp(200, {})])
    with pytest.raises(ExchangeBan) as e:
        cl.request(method, "/fapi/v1/time", None, kind=kind, signed=False)
    assert e.value.http == 451 and len(s.calls) == 1 and clk.sleeps == []


@pytest.mark.parametrize("kind,method", [("read", "GET"), ("order", "POST")])
def test_403_ban_window_300_doubling_to_1800(kind, method):
    cl, s, clk = mk([Resp(403, {})] * 5)
    expected = [300, 600, 1200, 1800, 1800]
    for want in expected:
        with pytest.raises(ExchangeBan) as e:
            cl.request(method, "/fapi/v1/order", {}, kind=kind)
        assert e.value.http == 403
        # SPEC-AMBIGUOUS: pencere uzunluğu health()["ban_until_ms"] ile gözlenir (ban nesnesinde retry_after_s'e güvenilmez).
        assert cl.health()["ban_until_ms"] - clk.ms == want * 1000
        clk.ms = cl.health()["ban_until_ms"] + 1
    assert len(s.calls) == 5


@pytest.mark.parametrize("kind,method", [("read", "GET"), ("order", "POST")])
@pytest.mark.parametrize("resp", [Resp(401, {}), err(401, -2014, "API-key format invalid."),
                                  err(401, -2015, "Invalid API-key, IP, or permissions for action."),
                                  err(400, -1022, "Signature for this request is not valid.")])
def test_auth_errors_are_exchange_auth_no_retry(kind, method, resp):
    cl, s, clk = mk([resp, Resp(200, {})])
    with pytest.raises(B.ExchangeAuth) as e:
        cl.request(method, "/fapi/v2/account", None, kind=kind)
    assert isinstance(e.value, ExchangeError) and len(s.calls) == 1 and clk.sleeps == []


def test_error_class_hierarchy():
    assert issubclass(B.ExchangeReject, ExchangeError)
    assert issubclass(B.ExchangeUncertain, ExchangeError)
    assert issubclass(B.ExchangeAuth, ExchangeError)
    assert not issubclass(B.ExchangeUncertain, B.ExchangeReject)
    assert not issubclass(B.ExchangeAuth, B.ExchangeReject)


# ----------------------------------------------------------------------------- 6. ağırlık eşikleri ve `protective` (§4.3, §16.7)
def _w(n):
    return {"X-MBX-USED-WEIGHT-1M": str(n)}


def _events_before_call(clk, n_call):
    """n_call'ıncı (0 tabanlı) 'call' olayından önceki 'sleep' sayısı."""
    seen = 0
    sl = 0
    for ev, _ in clk.events:
        if ev == "call":
            if seen == n_call:
                return sl
            seen += 1
        else:
            sl += 1
    return None


def test_weight_below_soft_no_delay():
    cl, s, clk = mk([Resp(200, {}, _w(1199)), Resp(200, {})])
    cl.request("GET", "/fapi/v2/positionRisk", None, kind="read")
    cl.request("GET", "/fapi/v2/positionRisk", None, kind="read")
    assert clk.sleeps == [] and len(s.calls) == 2
    assert cl.health()["used_weight"] == 1199


@pytest.mark.parametrize("w", [1200, 1250])
def test_weight_soft_defers_non_protective_read(w):
    cl, s, clk = mk([Resp(200, {}, _w(w)), Resp(200, {})])
    cl.request("GET", "/fapi/v2/positionRisk", None, kind="read")
    cl.request("GET", "/fapi/v2/positionRisk", None, kind="read", protective=False)
    assert len(s.calls) == 2
    assert _events_before_call(clk, 1) >= 1                  # ikinci çağrıdan önce uyku (ertelendi)
    assert s.calls[1]["at"] > s.calls[0]["at"]


def test_weight_soft_protective_read_passes_immediately():
    cl, s, clk = mk([Resp(200, {}, _w(1250)), Resp(200, {})])
    cl.request("GET", "/fapi/v2/positionRisk", None, kind="read")
    cl.request("GET", "/fapi/v2/positionRisk", None, kind="read", protective=True)
    assert clk.sleeps == [] and len(s.calls) == 2


def test_weight_hard_only_protective_passes():
    cl, s, clk = mk([Resp(200, {}, _w(1850)), Resp(200, {}), Resp(200, {}), Resp(200, {})])
    cl.request("GET", "/fapi/v2/positionRisk", None, kind="read")
    n0 = len(s.calls)
    # koruyucu: bekleme yok
    cl.request("GET", "/fapi/v2/positionRisk", None, kind="read", protective=True)
    cl.request("POST", "/fapi/v1/algoOrder", {"symbol": "XRPUSDT"}, kind="order", protective=True)
    assert clk.sleeps == [] and len(s.calls) == n0 + 2
    # koruyucu olmayan: geçmez (bekletilir ya da hata); SPEC-AMBIGUOUS: biçim belirsiz, borsaya doğrudan gitmemeli
    cl2, s2, clk2 = mk([Resp(200, {}, _w(1850)), Resp(200, {})])
    cl2.request("GET", "/fapi/v2/positionRisk", None, kind="read")
    try:
        cl2.request("GET", "/fapi/v2/positionRisk", None, kind="read")
    except ExchangeError:
        assert len(s2.calls) == 1
    else:
        assert _events_before_call(clk2, 1) >= 1


def test_weight_custom_thresholds():
    cl, s, clk = mk([Resp(200, {}, _w(50)), Resp(200, {})], weight_soft=50, weight_hard=100)
    cl.request("GET", "/fapi/v2/positionRisk", None, kind="read")
    cl.request("GET", "/fapi/v2/positionRisk", None, kind="read")
    assert _events_before_call(clk, 1) >= 1


def test_weight_wrappers_protective_classification():
    # §4.3 son paragraf: stop kurma ve reduceOnly piyasa çıkışı koruyucudur; giriş değildir.
    # SPEC-AMBIGUOUS: sarmalayıcıların `protective`'i kendiliğinden kurduğu (parametre yok) varsayıldı.
    cl, s, clk = mk([Resp(200, {}, _w(1850)), Resp(200, {}), Resp(200, {})])
    cl.request("GET", "/fapi/v2/positionRisk", None, kind="read")
    cl.new_conditional("XRPUSDT", "STOP_MARKET", "SELL", "10", "2.0346", "trLs-a", "MARK_PRICE")
    cl.new_market("XRPUSDT", "SELL", "10", "trLx-a", True)
    assert clk.sleeps == [] and len(s.calls) == 3


def test_weight_read_from_error_response_too():
    cl, s, clk = mk([err(400, -2019, "x", _w(1300)), Resp(200, {})])
    with pytest.raises(B.ExchangeReject):
        cl.request("POST", "/fapi/v1/order", {}, kind="order")
    assert cl.health()["used_weight"] == 1300


# ----------------------------------------------------------------------------- 7. emir tavanı
def _oc(n10=None, n1m=None):
    h = {}
    if n10 is not None:
        h["X-MBX-ORDER-COUNT-10S"] = str(n10)
    if n1m is not None:
        h["X-MBX-ORDER-COUNT-1M"] = str(n1m)
    return h


@pytest.mark.parametrize("hdr", [_oc(n10=25), _oc(n1m=150), _oc(n10=25, n1m=150)])
def test_order_cap_rejects_non_protective_without_sending(hdr):
    cl, s, clk = mk([Resp(200, {}, hdr), Resp(200, {})])
    cl.request("POST", "/fapi/v1/order", {"symbol": "XRPUSDT"}, kind="order", protective=True)
    n = len(s.calls)
    with pytest.raises(B.ExchangeReject) as e:
        cl.request("POST", "/fapi/v1/order", {"symbol": "XRPUSDT"}, kind="order")
    assert e.value.code is None and "order_rate_cap" in e.value.msg
    assert len(s.calls) == n                                  # gönderilmedi


def test_order_cap_boundary_at_limit():
    # SPEC-AMBIGUOUS: "aşılırsa" — sayaç == tavan iken bir sonraki emir tavanı aşacağından reddedildiği varsayıldı.
    cl, s, _ = mk([Resp(200, {}, _oc(n10=20)), Resp(200, {})])
    cl.request("POST", "/fapi/v1/order", {}, kind="order", protective=True)
    with pytest.raises(B.ExchangeReject):
        cl.request("POST", "/fapi/v1/order", {}, kind="order")
    cl, s, _ = mk([Resp(200, {}, _oc(n10=19, n1m=99)), Resp(200, {})])
    cl.request("POST", "/fapi/v1/order", {}, kind="order", protective=True)
    cl.request("POST", "/fapi/v1/order", {}, kind="order")    # 20. / 100. emir tavan içinde
    assert len(s.calls) == 2


def test_order_cap_custom_values():
    cl, s, _ = mk([Resp(200, {}, _oc(n10=6)), Resp(200, {})], order_cap_10s=5, order_cap_1m=50)
    cl.request("POST", "/fapi/v1/order", {}, kind="order", protective=True)
    with pytest.raises(B.ExchangeReject):
        cl.request("POST", "/fapi/v1/order", {}, kind="order")


def test_order_cap_protective_still_passes_over_local_cap():
    # SPEC-AMBIGUOUS: "borsa sınırının %80'ine kadar" — borsa sınırı şartnamede sayı olarak verilmedi; yalnız yerel tavanın
    # üstünde koruyucunun geçtiği sınanır.
    cl, s, _ = mk([Resp(200, {}, _oc(n10=25, n1m=150)), Resp(200, {}), Resp(200, {})])
    cl.request("POST", "/fapi/v1/order", {}, kind="order", protective=True)
    cl.request("POST", "/fapi/v1/algoOrder", {}, kind="order", protective=True)
    cl.new_conditional("XRPUSDT", "STOP_MARKET", "SELL", "10", "2.0346", "trLs-a", "MARK_PRICE")
    assert len(s.calls) == 3


def test_order_cap_does_not_affect_reads_cancels_and_wrapper_entry_is_capped():
    cl, s, _ = mk([Resp(200, {}, _oc(n10=25)), Resp(200, []), Resp(200, {})])
    cl.request("POST", "/fapi/v1/order", {}, kind="order", protective=True)
    cl.request("GET", "/fapi/v1/openOrders", None, kind="read")
    cl.cancel_order("XRPUSDT", "trLe-a")
    assert len(s.calls) == 3
    # SPEC-AMBIGUOUS: giriş new_market(reduce_only=False) koruyucu sayılmaz => tavana takılır.
    cl2, s2, _ = mk([Resp(200, {}, _oc(n10=25))])
    cl2.request("POST", "/fapi/v1/order", {}, kind="order", protective=True)
    with pytest.raises(B.ExchangeReject) as e:
        cl2.new_market("XRPUSDT", "BUY", "10", "trLe-a", False)
    assert "order_rate_cap" in e.value.msg and len(s2.calls) == 1


def test_health_fields():
    clk = Clock(T0)
    s = Sess([Resp(200, {}, {"X-MBX-USED-WEIGHT-1M": "77", "X-MBX-ORDER-COUNT-10S": "3", "X-MBX-ORDER-COUNT-1M": "9"})], clk)
    cl = B.SignedRestClient(env="live", api_key=API_KEY, api_secret=SECRET, session=s,
                            now_ms=clk.now_ms, sleep=clk.sleep)
    cl.request("POST", "/fapi/v1/order", {}, kind="order")
    h = cl.health()
    # SPEC-AMBIGUOUS: anahtar adları şartnamede `used_weight, order_count_10s/1m, ...` olarak kısaltılmış; `order_count_10s`
    # ve `order_count_1m` okundu.
    for k in ("used_weight", "order_count_10s", "order_count_1m", "clock_offset_ms", "ban_until_ms", "last_ok_ms"):
        assert k in h, k
    assert (h["used_weight"], h["order_count_10s"], h["order_count_1m"]) == (77, 3, 9)
    assert h["last_ok_ms"] == T0


# ----------------------------------------------------------------------------- 8. gizli değer sızma testi (§3.2)
def _scenarios():
    """(ad, yanıt dizisi, kind, protective). Hepsi hata yolu."""
    net = ConnectionError("HTTPSConnectionPool(host='fapi.binance.com'): url: /fapi/v1/order?symbol=X&signature=ab12 "
                          "headers X-MBX-APIKEY: %s secret %s" % (API_KEY, SECRET))
    return [
        ("net_read", [net] * 4, "read"),
        ("net_order", [net], "order"),
        ("5xx_read", [Resp(503, {"code": -1001, "msg": "Internal error"})] * 4, "read"),
        ("5xx_order", [Resp(502, {})], "order"),
        ("1021_twice", [err(400, -1021, "ts"), Resp(200, {"serverTime": T0 + 9000}), err(400, -1021, "ts"),
                        Resp(200, {"serverTime": T0 + 9000})], "order"),
        ("429_order", [Resp(429, {"code": -1003, "msg": "x"}, {"Retry-After": "5"})], "order"),
        ("418", [Resp(418, {}, {"Retry-After": "30"})], "read"),
        ("451", [Resp(451, {"msg": "restricted"})], "read"),
        ("403", [Resp(403, {})], "order"),
        ("401", [Resp(401, {})], "read"),
        ("-2014", [err(401, -2014, "API-key format invalid.")], "order"),
        ("-2015", [err(401, -2015, "Invalid API-key, IP, or permissions for action.")], "read"),
        ("-1022", [err(400, -1022, "Signature not valid.")], "order"),
        ("reject", [err(400, -2019, "Margin is insufficient.")], "order"),
        ("reject_longmsg", [err(400, -1102, "z" * 600)], "order"),
        ("nonjson_400", [Resp(400, None, text="<html>bad request ?symbol=XRPUSDT&signature=deadbeef</html>")], "order"),
        ("nonjson_200", [Resp(200, None, text="oops")], "read"),
    ]


def _run_scenario(seq, kind):
    clk = Clock(T0)
    s = Sess(seq + [Resp(200, {})] * 6, clk)          # arta kalan yanıtlar tüketilmeyebilir
    cl = B.SignedRestClient(env="live", api_key=API_KEY, api_secret=SECRET, session=s,
                            now_ms=clk.now_ms, sleep=clk.sleep)
    caught = []
    for protective in (False, True):
        try:
            cl.request("POST" if kind == "order" else "GET", "/fapi/v1/order" if kind == "order" else "/fapi/v2/positionRisk",
                       {"symbol": "XRPUSDT", "quantity": "10"}, kind=kind, protective=protective)
        except Exception as e:  # noqa: BLE001
            caught.append(e)
        clk.ms += 3_600_000
    return cl, s, caught


def _chain(e):
    seen = []
    while e is not None and e not in seen:
        seen.append(e)
        e = e.__cause__ or e.__context__
    return seen


@pytest.mark.parametrize("name,seq,kind", _scenarios(), ids=[x[0] for x in _scenarios()])
def test_secret_never_leaks_in_logs_or_exceptions(name, seq, kind, caplog, capsys):
    caplog.set_level(logging.DEBUG)
    logging.getLogger().setLevel(logging.DEBUG)
    cl, s, caught = _run_scenario(seq, kind)
    sigs = [dict(parse_qsl(c["query"])).get("signature") for c in s.calls]
    sigs = [x for x in sigs if x]
    out = capsys.readouterr()
    log_text = "\n".join(r.getMessage() + " " + str(r.args) + " " + (r.exc_text or "") for r in caplog.records)
    exc_text = "\n".join(str(e) + " " + repr(e) + " " + " ".join(map(str, e.args)) for e in caught)
    queries = [c["query"] for c in s.calls if c["query"]]
    for blob in (log_text, exc_text, out.out, out.err):
        assert SECRET not in blob
        assert "SIZMA-TESTI" not in blob
        assert API_KEY not in blob
        assert "X-MBX-APIKEY".lower() not in blob.lower()
        if name != "nonjson_400":
            # SPEC-AMBIGUOUS: sunucunun kendi gövdesinde `signature=` yankılaması (nonjson_400) şartnamenin "istemcinin
            # ürettiği ileti" kapsamı dışı sayıldı; yalnız gerçek imza değerleri aşağıda denetlenir.
            assert "signature=" not in blob and "timestamp=" not in blob and "recvWindow" not in blob
        for sg in sigs:
            assert sg not in blob
        for q in queries:
            assert q not in blob
    assert caught or name == "nonjson_200"  # hata yolları gerçekten çalıştı


@pytest.mark.parametrize("name,seq,kind", _scenarios(), ids=[x[0] for x in _scenarios()])
def test_secret_never_leaks_in_exception_chain(name, seq, kind):
    # SPEC-AMBIGUOUS: "istisna metinleri" zincirdeki (__cause__/__context__) özgün ağ hatalarını da kapsıyor mu belirsiz;
    # kapsıyor kabul edildi (traceback'te sızmasın).
    _, s, caught = _run_scenario(seq, kind)
    for e in caught:
        text = "".join(traceback.format_exception(type(e), e, e.__traceback__))
        for x in _chain(e):
            text += str(x) + repr(x)
        assert SECRET not in text and API_KEY not in text and "SIZMA-TESTI" not in text
        if name != "nonjson_400":
            assert "signature=" not in text


def test_error_message_has_no_query_string_signature_key_or_header():
    cl, _, _ = mk([err(400, -2019, "Margin is insufficient.")])
    with pytest.raises(B.ExchangeReject) as e:
        cl.request("POST", "/fapi/v1/order", {"symbol": "XRPUSDT", "quantity": "10"}, kind="order")
    t = str(e.value)
    assert "?" not in t and "&" not in t and "quantity" not in t and "timestamp" not in t


def test_repr_and_str_hide_key_and_secret():
    cl, _, _ = mk([])
    for t in (repr(cl), str(cl), "%s" % cl, "%r" % cl, f"{cl!r}"):
        assert SECRET not in t and API_KEY not in t and "SIZMA-TESTI" not in t


def test_no_secret_in_logs_on_success_path_either(caplog):
    caplog.set_level(logging.DEBUG)
    cl, s, _ = mk([Resp(200, {"serverTime": T0 + 2000}), Resp(200, {"ok": 1})])
    cl.sync_time()
    cl.request("POST", "/fapi/v1/order", {"symbol": "XRPUSDT"}, kind="order")
    blob = "\n".join(r.getMessage() for r in caplog.records)
    assert SECRET not in blob and API_KEY not in blob and "signature=" not in blob


# ----------------------------------------------------------------------------- 9. saat/uyku enjeksiyonu
def test_constructor_requires_injected_clock_and_sleep():
    s = Sess([])
    clk = Clock()
    with pytest.raises(TypeError):
        B.SignedRestClient(env="live", api_key=API_KEY, api_secret=SECRET, session=s, sleep=clk.sleep)
    with pytest.raises(TypeError):
        B.SignedRestClient(env="live", api_key=API_KEY, api_secret=SECRET, session=s, now_ms=clk.now_ms)


def test_full_flow_uses_only_injected_clock(monkeypatch):
    # autouse fixture time.time/sleep/monotonic/... çağrılırsa AssertionError verir; datetime.now da yasak.
    import datetime as _dt

    class NoNow(_dt.datetime):
        @classmethod
        def now(cls, *a, **k):
            raise AssertionError("datetime.now çağrıldı")

        @classmethod
        def utcnow(cls):
            raise AssertionError("datetime.utcnow çağrıldı")

    monkeypatch.setattr(_dt, "datetime", NoNow)
    clk = Clock(T0)
    s = Sess([Resp(200, {"serverTime": T0 + 1200}), Resp(503, {}), Resp(200, {"ok": 1}),
              Resp(429, {}, {"Retry-After": "2"}), Resp(200, {"ok": 2}), err(400, -1021), Resp(200, {"serverTime": T0 + 1300}),
              Resp(200, {"ok": 3})], clk)
    cl = B.SignedRestClient(env="live", api_key=API_KEY, api_secret=SECRET, session=s,
                            now_ms=clk.now_ms, sleep=clk.sleep)
    cl.sync_time()
    assert cl.request("GET", "/fapi/v2/account", None, kind="read") == {"ok": 1}
    assert cl.request("GET", "/fapi/v2/account", None, kind="read") == {"ok": 2}
    assert cl.request("POST", "/fapi/v1/order", {}, kind="order") == {"ok": 3}
    assert clk.sleeps                                           # uyku yalnız enjekte edilen işlevle yapıldı


def test_timestamp_follows_injected_clock_exactly():
    clk = Clock(123_456_789_000)
    s = Sess([Resp(200, {}), Resp(200, {})], clk)
    cl = B.SignedRestClient(env="testnet", api_key=API_KEY, api_secret=SECRET, session=s,
                            now_ms=clk.now_ms, sleep=clk.sleep)
    cl.request("GET", "/fapi/v2/account", None, kind="read")
    clk.ms += 777
    cl.request("GET", "/fapi/v2/account", None, kind="read")
    assert int(qd(s.calls[0])["timestamp"]) == 123_456_789_000
    assert int(qd(s.calls[1])["timestamp"]) == 123_456_789_777
