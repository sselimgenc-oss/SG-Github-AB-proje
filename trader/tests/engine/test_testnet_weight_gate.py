"""Testnet ağırlık başlığı muafiyeti (mentor: testnet ağırlık başlığı paylaşımlı/gürültülü). Sentetik; gerçek ağ/saat yok."""
from __future__ import annotations

import logging

import pytest

from trader_engine.exchange import binance_rest as B
from trader_engine.marketdata.rest_public import ExchangeBan

KEY, SEC = "k" * 32, "s" * 32
T0 = 1_798_449_600_000


class Resp:
    def __init__(self, status=200, body=None, headers=None):
        self.status_code, self._b, self.headers = status, body if body is not None else {}, headers or {}
        self.text = "{}"
        self.content = b"{}"

    @property
    def ok(self):
        return self.status_code < 400

    def json(self):
        return self._b


def _w(n):
    return {"X-MBX-USED-WEIGHT-1M": str(n)}


class Sess:
    def __init__(self, seq):
        self.seq, self.calls = list(seq), []

    def request(self, method, url, **kw):
        self.calls.append((method, url))
        return self.seq.pop(0)

    def get(self, url, **kw):
        return self.request("GET", url, **kw)

    def post(self, url, **kw):
        return self.request("POST", url, **kw)


class Clock:
    def __init__(self):
        self.ms = T0

    def now_ms(self):
        return self.ms

    def sleep(self, s):
        self.ms += int(s * 1000)


def mk(env, seq):
    clk, s = Clock(), Sess(seq)
    return B.SignedRestClient(env=env, api_key=KEY, api_secret=SEC, session=s, now_ms=clk.now_ms, sleep=clk.sleep), s, clk


def read(cl):
    return cl.request("GET", "/fapi/v2/account", None, kind="read")


def order(cl):
    return cl.request("POST", "/fapi/v1/order", {"symbol": "XRPUSDT"}, kind="order")


def test_testnet_ignores_header_weight():
    cl, s, _ = mk("testnet", [Resp(200, {}, _w(1211)), Resp(200, {}, _w(1900)), Resp(200, {}, _w(1900)), Resp(200, {})])
    read(cl)
    read(cl)                       # 1211 >= soft: yine de gider
    order(cl)                      # 1900 >= hard: yine de gider
    read(cl)
    assert len(s.calls) == 4
    assert cl.health()["used_weight"] == 1900     # başlık kaydedilmeye devam eder


def test_live_soft_gate_unchanged():
    cl, s, _ = mk("live", [Resp(200, {}, _w(1211))])
    read(cl)
    with pytest.raises(ExchangeBan, match="weight_soft"):
        read(cl)
    assert len(s.calls) == 1


def test_live_hard_gate_unchanged():
    cl, s, _ = mk("live", [Resp(200, {}, _w(1900))])
    read(cl)
    with pytest.raises(ExchangeBan, match="weight_hard"):
        order(cl)
    assert len(s.calls) == 1


def test_testnet_429_ban_window_still_enforced():
    cl, s, clk = mk("testnet", [Resp(429, {"code": -1003, "msg": "x"}, {"Retry-After": "30"}), Resp(200, {})])
    with pytest.raises(Exception):
        order(cl)
    clk.ms += 5_000
    with pytest.raises(ExchangeBan) as e:
        read(cl)
    assert e.value.http == 429 and len(s.calls) == 1


def test_testnet_warning_rate_limited(caplog):
    cl, s, clk = mk("testnet", [Resp(200, {}, _w(1500))] * 4)
    with caplog.at_level(logging.WARNING, logger="engine.binance_rest"):
        read(cl)                   # ağırlık henüz 0: uyarı yok
        read(cl)                   # 1500: uyarı
        clk.ms += 20_000
        read(cl)                   # 60 sn içinde: uyarı yok
    warns = [r for r in caplog.records if "yok sayılıyor" in r.getMessage()]
    assert len(warns) == 1
    assert len(s.calls) == 3
