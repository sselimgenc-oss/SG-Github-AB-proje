"""GENEL DENETİM grup D (emir, boyut, stop/risk, kill, karantina). KIRMIZI testler: her biri bir bulguyu gösterir (kaynak kod değişmedi).
Çalıştır: python -m pytest testler/denetim_D_test.py -q -p no:cacheprovider
"""
import inspect
from decimal import Decimal
from types import SimpleNamespace

import numpy as np
import pandas as pd
import pytest

from motor.canli import bosluk_maruziyet as bm
from motor.canli import cikis_karsi_olgu as cko
from motor.canli import paper as pp
from testler.test_karantina import KOL_A, KOL_B, Bozuk, Gec, _kolu, _paper, _t, _veri
from testler.test_paper_motor import tanim


# ---------------------------------------------------------------------------- D1: canlı yolda otomatik çıkış değişikliği bağlanıyor
def test_D1_cikis_karsi_olgu_canli_yolda_baglanmaz():
    """Beklenen: alinsaydi_gevsetme gibi, onaysız ÇIKIŞ değiştiren cikis_karsi_olgu canlı yürütücü servisinde bağlanmaz ("canlıda kendini değiştiren kod yok")."""
    kaynak = inspect.getsource(pp._canli_calistir_kilitli)
    satir = next(x for x in kaynak.splitlines() if "cikis_karsi_olgu.bagla(" in x)
    assert "canli" in satir, satir.strip()
    assert "canli" in inspect.signature(cko.bagla).parameters


# ---------------------------------------------------------------------------- D2: strateji kodundaki ZeroDivisionError karantina yerine tüm turu düşürür
def test_D2_strateji_zerodivision_karantinaya_alinir_diger_strateji_surer():
    mum = _veri()
    a = tanim(KOL_A, "AUSDT", grup="g1", pay="0.5", stop_yuzde=1.0)
    a.nesne = Bozuk(stop_yuzde=1.0)
    a.nesne.patla = 8
    a.nesne.hata = ZeroDivisionError("float division by zero")      # strateji içi bölme hatası: ağ/veri değil, programlama hatası
    b = tanim(KOL_B, "BUSDT", grup="g2", pay="0.5", stop_yuzde=1.0)
    b.nesne = Gec(stop_yuzde=1.0)
    b.nesne.basla = 8
    p = _paper([a, b], mum)
    p.baslat(_t(mum, 3))
    p.adim(_t(mum, 12))                                              # gerçek: ZeroDivisionError yükselir, B de işlenmez
    assert p.karantina.get(KOL_A, {}).get("durum") == "aktif"
    ib, ab = _kolu(p, KOL_B)
    assert ab or ib


# ---------------------------------------------------------------------------- D3: karantinada gün sonu kapanışı kayboluyor
class GunIci(Bozuk):
    """Gün içi strateji: her mumda long ister ve her mumun kapanışında pozisyonu kapatır (gun_sonu_kapanis=True)."""
    ad = "test__gun_ici"

    def sinyaller(self, mumlar):
        sig = super().sinyaller(mumlar)
        sig["gun_sonu_kapanis"] = True
        return sig


def test_D3_karantinada_gun_ici_pozisyon_gece_tasinmaz():
    mum = _veri()
    a = tanim(KOL_A, "AUSDT", grup="g1", pay="0.5", stop_yuzde=1.0)
    a.nesne = GunIci(stop_yuzde=1.0)
    a.nesne.patla = 8
    b = tanim(KOL_B, "BUSDT", grup="g2", pay="0.5", stop_yuzde=1.0)
    b.nesne = Gec(stop_yuzde=1.0)
    b.nesne.basla = 10 ** 9
    p = _paper([a, b], mum)
    p.baslat(_t(mum, 3))
    p.adim(_t(mum, 7))
    assert all(x["cikis_nedeni"] == "gun_sonu" for x in _kolu(p, KOL_A)[0])   # karantinadan önce her gün kapanıyor
    p.adim(_t(mum, 12))                                                       # bar 8: karar patlar -> karantina
    assert p.motor.karantina == {KOL_A}
    assert not _kolu(p, KOL_A)[1], "gün içi stratejinin pozisyonu karantinada günlerce açık kaldı (gün sonu kapanışı uygulanmadı)"


# ---------------------------------------------------------------------------- D4: boşluk eşiği '>' (kill '>=')
def test_D4_bosluk_esik_esitlikte_ihlal():
    o = bm.hesapla([{"ad": "h", "gizli": False, "kasa": 1000.0, "pozisyonlar": [{"sembol": "DK_AAPL", "nominal": 1000.0}]}],
                   pd.Timestamp("2026-11-18T20:45Z"), esik=0.20)
    assert o["hesaplar"][0]["kayip_yuzde"] == pytest.approx(0.20)
    assert o["hesaplar"][0]["ihlal"], "kayıp tam kill eşiğinde (kill >= ile tetiklenir) ama uyarı yok"


# ---------------------------------------------------------------------------- D5: boşluk riski mevcut zirveden düşüşü yok sayıyor
def test_D5_bosluk_mevcut_dususle_kill_tetikleyecekse_ihlal():
    poz = SimpleNamespace(sembol="DK_AAPL", miktar=Decimal(25))
    motor = SimpleNamespace(acik={"x": poz}, son_kap={"DK_AAPL": 100.0}, zirve=Decimal(10000),
                            ozsermaye=lambda: Decimal(8500))         # zirveden -%15
    p = SimpleNamespace(motor=motor)
    o = bm.hesapla(bm.hesaplari_cikar(p), pd.Timestamp("2026-11-18T20:45Z"), esik=0.20)
    # %20 boşluk: 2500 x 0.2 = 500 kayıp -> özsermaye 8000 = zirveden -%20 -> KILL. Uyarı beklenir.
    assert o["hesaplar"][0]["ihlal"], f"kill tetiklenecek ama ihlal yok (kayip_yuzde={o['hesaplar'][0]['kayip_yuzde']:.3f})"


# ---------------------------------------------------------------------------- D6: sonsuz_dene: mesajı değişen kod hatası hiç durmaz
class _Dur(BaseException):
    pass


def test_D6_sonsuz_dene_ardisik_kod_hatasi_mesaj_degisse_de_durur():
    n = [0]

    def fn():
        n[0] += 1
        if n[0] > 30:
            raise _Dur()
        raise KeyError(f"sembol_{n[0]}")                           # aynı programlama hatası, değişen anahtar
    with pytest.raises(KeyError):
        pp.sonsuz_dene(fn, "test", uyku=lambda s: None, saat=lambda: 0.0)
    assert n[0] == pp.KOD_HATASI_SINIRI


# ---------------------------------------------------------------------------- D7: genel kesinti tespiti yalnız "bu turda sırası gelen" serileri sayıyor
def test_D7_guncelle_denenen_tum_seriler_hataliysa_yukselir():
    from motor.canli import paper_canli as pc
    from motor.canli import paper_veri as pv
    from testler.test_paper_motor import duz
    k = object.__new__(pc.CanliKaynak)
    h1 = duz(48, 100.0)
    h1.index = pd.date_range("2026-11-18", periods=48, freq="h", tz="UTC", name="zaman")
    d1 = duz(10, 100.0)
    d1.index = pd.date_range("2026-11-10", periods=10, freq="D", tz="UTC", name="zaman")
    k.seriler = [("XUSDT", "1h"), ("YUSDT", "1d")]
    k.mumlar = {("XUSDT", "1h"): h1, ("YUSDT", "1d"): d1}
    k.son_kontrol, k.funding_son, k.semboller = {}, {"t": pd.Timestamp("2026-11-20T02:20Z")}, ["XUSDT", "YUSDT"]
    k._veri_hata_olay, k.son_mum_bozuk, k.olay = {}, {}, lambda t, m: None

    def patla(*a, **kw):
        raise pv.BinanceHata("503 genel kesinti")
    k._mum_al = patla
    simdi = pd.Timestamp("2026-11-20T02:30Z")       # 1h serinin sırası geldi (Binance tamamen kapalı); 1d serinin sırası gelmedi
    with pytest.raises(pv.BinanceHata):
        k.guncelle(simdi)
