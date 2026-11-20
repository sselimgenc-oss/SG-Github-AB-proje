"""Canlı istemci sertleştirme: belirsiz yanıtlar, ortak yasak, sayfalama, kural/ayar/kayıt/atomik yazım."""
import hashlib
import json
import os
import time
from decimal import Decimal as D

import numpy as np
import pandas as pd
import pytest

from motor.canli import durum as dr
from motor.canli import paper_veri as pv
from motor.canli.borsa import binance_futures as bf
from motor.canli.borsa import canli_ayar as ca
from motor.canli.borsa import canli_kayit as ck
from motor.canli.borsa import kurallar as kr
from motor.canli.borsa.binance_futures import BinanceFutures, BorsaHata, BorsaYasagi


class Y:
    def __init__(self, kod=200, g=None, b=None):
        self.status_code, self._g, self.headers, self.text = kod, g if g is not None else {}, b or {}, ""

    def json(self):
        if isinstance(self._g, Exception):
            raise self._g
        return self._g


class O:
    def __init__(self, ys):
        self.ys, self.n = list(ys), 0

    def request(self, yontem, url, headers=None, timeout=None):
        self.n += 1
        return self.ys.pop(0)


ZAMAN = Y(200, {"serverTime": 1_700_000_000_000})


def ist(ys, **kw):
    o = O(ys)
    u = []
    return BinanceFutures("testnet", "k" * 10, "g" * 10, oturum=o, uyku=u.append, saat=lambda: 1_700_000_000.0, **kw), o, u


@pytest.fixture(autouse=True)
def _temiz():
    bf.yasak_sifirla()
    yield
    bf.yasak_sifirla()


# ---- O5
def test_200_json_degil_belirsiz():
    c, o, _ = ist([ZAMAN, Y(200, ValueError("x"))])
    with pytest.raises(BorsaHata) as e:
        c.piyasa("BTCUSDT", "BUY", D(1), "id")
    assert e.value.belirsiz


def test_norm_eksik_alan_belirsiz():
    c, o, _ = ist([ZAMAN, Y(200, {"symbol": "BTCUSDT"})])
    with pytest.raises(BorsaHata) as e:
        c.piyasa("BTCUSDT", "BUY", D(1), "id")
    assert e.value.belirsiz


def test_norm_nan_ve_bozuk_sayi_belirsiz():
    g = {"orderId": 1, "symbol": "A", "side": "BUY", "origQty": "abc"}
    with pytest.raises(BorsaHata) as e:
        BinanceFutures._norm(g, False)
    assert e.value.belirsiz
    with pytest.raises(BorsaHata):
        BinanceFutures._norm({**g, "origQty": "NaN"}, False)


@pytest.mark.parametrize("cagri,g", [("bakiye", {"totalMarginBalance": "1"}), ("bakiye", {"totalMarginBalance": "x", "availableBalance": "1", "totalWalletBalance": "1"}),
                                     ("pozisyonlar", [{"symbol": "A"}]), ("pozisyonlar", [{"symbol": "A", "positionAmt": "1", "entryPrice": "Infinity", "markPrice": "1"}])])
def test_okuma_ayristirma_borsahata(cagri, g):
    c, o, _ = ist([ZAMAN, Y(200, g)])
    with pytest.raises(BorsaHata):
        getattr(c, cagri)()


def test_mark_fiyat_bozuk():
    c, o, _ = ist([Y(200, {"markPrice": "0"})])
    with pytest.raises(BorsaHata):
        c.mark_fiyat("A")
    c, o, _ = ist([Y(200, {})])
    with pytest.raises(BorsaHata):
        c.mark_fiyat("A")


# ---- O8
@pytest.mark.parametrize("http,kod", [(400, -1007), (200 + 200, -1006), (400, -1008), (408, None), (503, None)])
def test_belirsiz_kodlar_emirde_tekrarsiz(http, kod):
    c, o, _ = ist([ZAMAN, Y(http, {"code": kod} if kod else {}), Y(200, {})])
    with pytest.raises(BorsaHata) as e:
        c.piyasa("BTCUSDT", "BUY", D(1), "id")
    assert e.value.belirsiz and o.n == 2            # zaman + tek POST


# ---- D16 / D3
def test_429_uyumaz_yasak_koyar():
    c, o, u = ist([ZAMAN, Y(429, {}, {"Retry-After": "30"})])
    with pytest.raises(BorsaYasagi):
        c._get("/fapi/v2/account")
    assert u == [] and c.yasak_bitis == 1_700_000_030.0


def test_yasak_paylasimi_ve_dosya(tmp_path, monkeypatch):
    d = tmp_path / "yasak.json"
    simdi = time.time()
    bf.yasak_ayarla(simdi + 100, d)
    assert json.loads(d.read_text())["hostlar"]["fapi.binance.com"] == pytest.approx(simdi + 100)
    bf.yasak_sifirla()
    assert bf.yasak_yukle(d) == pytest.approx(simdi + 100)
    # FapiIstemci (gerçek saat) paylaşılan yasağı görür
    class Oturum:
        def get(self, *a, **k):
            raise AssertionError("istek gitmemeli")
    f = pv.FapiIstemci(oturum=Oturum())
    with pytest.raises(pv.BinanceHata, match="yasağı"):
        f.get("/x")
    # ve tersi: FapiIstemci 418 alınca BinanceFutures da bloklanır
    bf.yasak_sifirla()
    class O418:
        def get(self, *a, **k):
            return Y(418, {}, {"Retry-After": "50"})
    f = pv.FapiIstemci(oturum=O418())
    with pytest.raises(pv.BinanceHata):
        f.get("/x")
    c = BinanceFutures("canli", "k", "g", oturum=O([]))      # aynı host (fapi.binance.com) -> yasak paylaşılır
    with pytest.raises(BorsaYasagi):
        c._agirlik_bekle()


# ---- D17
def test_kullanici_islemleri_1000_sayfalama():
    def tr(i, t):
        return {"id": i, "orderId": 1, "side": "BUY", "price": "1", "qty": "1", "time": t}
    s1 = [tr(i, 1_700_000_000_000 - 5000 + i) for i in range(1000)]
    s2 = [s1[-1]] + [tr(1000 + i, 1_700_000_000_000 - 3000 + i) for i in range(5)]
    c, o, _ = ist([ZAMAN, Y(200, s1), Y(200, s2)])
    r = c.kullanici_islemleri("BTCUSDT", 1_700_000_000_000 - 10000, 1_700_000_000_000)
    assert len(r) == 1005


def test_funding_1000_sayfalama():
    def inc(i, t):
        return {"tranId": i, "time": t, "income": "-1"}
    s1 = [inc(i, 1_700_000_000_000 - 5000 + i) for i in range(1000)]
    s2 = [s1[-1], inc(1000, 1_700_000_000_000 - 100)]
    c, o, _ = ist([ZAMAN, Y(200, s1), Y(200, s2)])
    assert c.funding_gecmisi("BTCUSDT", 1_700_000_000_000 - 10000, 1_700_000_000_000) == D(-1001)


# ---- D9
def test_klines_inf_atilir():
    satir = [[0, "1", "2", "0.5", "1.5", "1", 59_999, "1", 1], [60_000, "1", "inf", "0.5", "1.5", "1", 119_999, "1", 1]]
    df = pv.klines_df(satir, pd.Timestamp("2025-01-01", tz="UTC"))
    assert len(df) == 1 and np.isfinite(df.to_numpy()).all()


# ---- D10
def _bilgi(status="TRADING", mn=True):
    f = [{"filterType": "PRICE_FILTER", "tickSize": "0.1"}, {"filterType": "LOT_SIZE", "stepSize": "0.001", "minQty": "0.001", "maxQty": "10"}]
    if mn:
        f.append({"filterType": "MIN_NOTIONAL", "notional": "5"})
    return {"symbols": [{"symbol": "BTCUSDT", "status": status, "filters": f}]}


def test_kural_min_notional_yok_ve_durum():
    assert kr.kural_cikar(_bilgi(), "BTCUSDT").min_notional == D(5)
    with pytest.raises(kr.KuralHatasi, match="MIN_NOTIONAL"):
        kr.kural_cikar(_bilgi(mn=False), "BTCUSDT")
    with pytest.raises(kr.KuralHatasi, match="TRADING"):
        kr.kural_cikar(_bilgi(status="BREAK"), "BTCUSDT")


# ---- D4 / D5
def test_atomik_yaz_dizin_fsync(tmp_path, monkeypatch):
    cagri = []
    gercek = os.fsync
    monkeypatch.setattr(os, "fsync", lambda fd: (cagri.append(fd), gercek(fd))[1])
    dr.atomik_yaz_metin(tmp_path / "a.txt", "x")
    assert len(cagri) == 2 and (tmp_path / "a.txt").read_text() == "x"


def test_satir_ekle_kesik_son_satir(tmp_path):
    y = tmp_path / "k.jsonl"
    y.write_text('{"a": 1}\n{"b"')
    ck.satir_ekle(y, {"c": 3})
    sat = y.read_text().split("\n")
    assert sat[0] == '{"a": 1}' and sat[1] == '{"b"' and json.loads(sat[2]) == {"c": 3}
    ck.satir_ekle(y, {"d": 4})
    assert y.read_text().count("\n") == 4


# ---- D7
def test_ayni_anahtar_degeri_farkli_env_reddedilir():
    h = {"mod": "testnet", "stratejiler": [
        {"id": "A", "api_key_env": "K1", "api_secret_env": "S1", "tahsis_usd": 100},
        {"id": "B", "api_key_env": "K2", "api_secret_env": "S2", "tahsis_usd": 100}]}
    with pytest.raises(ca.CanliAyarHatasi) as e:
        ca.coz(h, {"K1": "AYNI-DEGER", "S1": "s1", "K2": " AYNI-DEGER ", "S2": "s2"})
    assert "AYNI-DEGER" not in str(e.value)
    assert ca.coz(h, {"K1": "x1", "S1": "s1", "K2": "x2", "S2": "s2"}).mod == "testnet"
