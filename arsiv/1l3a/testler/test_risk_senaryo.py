"""araclar/risk_senaryo.py yeniden oynatma matematiği (sentetik işlem listesi)."""
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from araclar import risk_senaryo as rs  # noqa: E402

BAS, BIT = "2020-01-01", "2020-12-31"


def _t(gun):
    return pd.Timestamp("2020-01-01") + pd.Timedelta(days=gun)


def _df(satirlar):
    return pd.DataFrame([{"giris_zamani": _t(g), "cikis_zamani": _t(c), "r": r, "sf": sf} for g, c, r, sf in satirlar])


def _son(o):
    return o["olaylar"][-1][1]


def test_sabit_risk_ardisik_bilesik():
    # iki ardışık işlem: +2R sonra -1R, f=%1 -> 10000*1.02*0.99
    o = rs.oynat_islemler(_df([(1, 2, 2.0, 0.05), (3, 4, -1.0, 0.05)]), 0.01, kill=False, bas=BAS, bit=BIT)
    assert _son(o) == pytest.approx(10000 * 1.02 * 0.99)
    assert o["max_kaldirac"] == pytest.approx(0.01 / 0.05 * 1.0 * 1.0, rel=0.02)   # f/sf = 0.2x (ikinci işlemde 0.2*1.02/1.02)


def test_eszamanli_giris_aninda_ozsermayeye_gore():
    # iki işlem aynı anda açık: ikisi de 10000 üzerinden boyutlanır (biri diğerinin kârını görmez)
    o = rs.oynat_islemler(_df([(1, 5, 1.0, 0.1), (2, 3, 1.0, 0.1)]), 0.02, kill=False, bas=BAS, bit=BIT)
    assert _son(o) == pytest.approx(10000 + 200 + 200)
    assert o["max_kaldirac"] == pytest.approx(2 * 0.02 * 10000 / 0.1 / 10000 * 1.0, rel=0.05)  # ~0.4x


def test_cikis_ayni_anda_girisden_once():
    # t=3'te biri çıkıp biri girerse yeni giriş güncellenmiş özsermayeyi görür
    o = rs.oynat_islemler(_df([(1, 3, 1.0, 0.1), (3, 4, 1.0, 0.1)]), 0.1, kill=False, bas=BAS, bit=BIT)
    assert _son(o) == pytest.approx(10000 * 1.1 * 1.1)


def test_tam_kasa_notional_ozsermaye():
    # R=2, sf=%5 -> fiyat getirisi %10; tam kasa: 10000 -> 11000; sonra R=-1,sf=%5 -> -%5
    o = rs.oynat_islemler(_df([(1, 2, 2.0, 0.05), (3, 4, -1.0, 0.05)]), None, kill=False, bas=BAS, bit=BIT)
    assert _son(o) == pytest.approx(10000 * 1.10 * 0.95)
    assert o["max_kaldirac"] == pytest.approx(1.0)


def test_tam_kasa_eszamanli_kaldirac_ve_tasfiye():
    # iki eşzamanlı işlem her biri tam kasa -> kaldıraç 2; ikisi de -%80 -> özsermaye sıfıra iner, negatif olmaz
    o = rs.oynat_islemler(_df([(1, 5, -8.0, 0.1), (2, 6, -8.0, 0.1)]), None, kill=False, bas=BAS, bit=BIT)
    assert o["max_kaldirac"] == pytest.approx(2.0)
    assert _son(o) == 0.0


def test_kill_yeni_islem_acmaz_ve_tarih():
    # f=%10, R=-1 her işlem: -%10, -%10 ... zirve 10000; 4. kayıpta 10000*.9^4=6561 <= 7000 -> kill; sonrası işlemler atlanır
    satirlar = [(i * 2 + 1, i * 2 + 2, -1.0, 0.1) for i in range(8)]
    o = rs.oynat_islemler(_df(satirlar), 0.10, kill=True, bas=BAS, bit=BIT)
    assert o["kill_tarihi"] == _t(8)
    assert _son(o) == pytest.approx(10000 * 0.9 ** 4)  # 4 işlemde durur (0.9^3=7290 > 7000; 0.9^4 kill)
    assert o["n_atlanan"] == 4
    nk = rs.oynat_islemler(_df(satirlar), 0.10, kill=False, bas=BAS, bit=BIT)
    assert nk["kill_tarihi"] is None and _son(nk) == pytest.approx(10000 * 0.9 ** 8)


def test_pencere_disi_islem_dislanir():
    o = rs.oynat_islemler(_df([(-10, -5, 5.0, 0.1), (1, 2, 1.0, 0.1)]), 0.01, kill=False, bas=BAS, bit=BIT)
    assert _son(o) == pytest.approx(10100)


def test_metrikler_aylik_ve_dd():
    gun = pd.Series(10000.0, index=pd.date_range("2020-01-01", "2020-03-31"))
    gun["2020-01-31":"2020-02-14"] = 11000.0       # ocak sonu 11000
    gun["2020-02-15":] = 9900.0                    # şubat sonu 9900, mart sonu 9900
    m = rs.metrikler(gun)
    assert m["n_ay"] == 3
    assert m["ay_en_kotu"] == pytest.approx(9900 / 11000 - 1)
    assert m["max_dd"] == pytest.approx(9900 / 11000 - 1)
    assert m["ay_zarar_orani"] == pytest.approx(1 / 3)    # ocak +%10, şubat -%10, mart 0 -> yalnız şubat zarar


def test_kill_donuk_sonrasi_pnl_yok_sayilir():
    # uzun işlem (+10R, f=%10 -> +10000) gün 1'de açılır, gün 20'de kapanır; arada 5 kayıp (-%10): 4. kayıpta kill (gün 9)
    satirlar = [(1, 20, 10.0, 0.1)] + [(i * 2 + 2, i * 2 + 3, -1.0, 0.1) for i in range(5)]
    ac = rs.oynat_islemler(_df(satirlar), 0.10, kill=True, bas=BAS, bit=BIT)
    do = rs.oynat_islemler(_df(satirlar), 0.10, kill="donuk", bas=BAS, bit=BIT)
    assert ac["kill_tarihi"] == do["kill_tarihi"] == _t(9)
    assert _son(do) == pytest.approx(10000 * 0.9 ** 4)
    assert _son(ac) == pytest.approx(10000 * 0.9 ** 4 + 10000)


def test_veri_sonu_zorunlu_kapanis_haric():
    # bit=2020-12-31: çıkışı 2021-01-01 00:00 (veri sonu zorunlu kapanış) olan işlem hiçbir yerde sayılmaz
    d = pd.DataFrame([{"giris_zamani": _t(1), "cikis_zamani": _t(2), "r": 1.0, "sf": 0.1},
                      {"giris_zamani": _t(5), "cikis_zamani": pd.Timestamp("2021-01-01"), "r": 100.0, "sf": 0.1}])
    o = rs.oynat_islemler(d, 0.01, kill=False, bas=BAS, bit=BIT)
    assert o["n_alinan"] == 1 and _son(o) == pytest.approx(10100)
    o2 = rs.oynat_islemler(d, 0.01, kill=False, bas=BAS, bit="2021-01-01")
    assert o2["n_alinan"] == 2
