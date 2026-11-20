"""Seans bazlı kayma çarpanı (2026-11-19, kullanıcı onaylı): ABD hisse/emtia perp'lerinde dayanak kapalıyken kayma büyür.
Çarpan yalnız kayma bileşenine uygulanır (komisyon değişmez); kripto 1.0; işlem kaydına seans_dilimi/kayma_carpani (yalnız hisse/emtia)."""
import json
from decimal import Decimal

import pandas as pd
import pytest

from motor.arastirma import evren_maliyet as em
from motor.canli import paper as pp
from motor.canli import seans_maliyet as sm
from motor.canli.paper_motor import PaperMotor
from motor.canli.paper_takvim import seans_dilimi
from motor.portfoy.motor import PortfoyAyarlari
from testler.test_maliyet_dahil_risk import INCE, KASA
from testler.test_paper_motor import tanim


def utc(ny: str) -> pd.Timestamp:
    return pd.Timestamp(ny, tz="America/New_York").tz_convert("UTC")


# ------------------------------------------------------------------ dilim sınırları
@pytest.mark.parametrize("ny,beklenen", [
    ("2025-01-08 03:59", "kapali"), ("2025-01-08 04:00", "genisletilmis"), ("2025-01-08 09:29", "genisletilmis"),
    ("2025-01-08 09:30", "normal"), ("2025-01-08 15:59", "normal"), ("2025-01-08 16:00", "genisletilmis"),
    ("2025-01-08 19:59", "genisletilmis"), ("2025-01-08 20:00", "kapali"), ("2025-01-08 23:00", "kapali"),
    ("2025-01-11 12:00", "kapali"),      # Cumartesi
    ("2025-01-12 12:00", "kapali"),      # Pazar
    ("2025-01-20 11:00", "kapali"),      # MLK tatili
    ("2025-01-20 06:00", "kapali"),      # tatilde genişletilmiş seans yok
    ("2025-11-28 12:59", "normal"), ("2025-11-28 13:00", "genisletilmis"), ("2025-11-28 16:59", "genisletilmis"),
    ("2025-11-28 17:00", "kapali"),      # erken kapanış günü
])
def test_hisse_dilimleri(ny, beklenen):
    assert seans_dilimi("DK_NVDA", utc(ny)) == beklenen


def test_emtia_ve_kripto_dilimleri():
    assert seans_dilimi("DK_XAU", utc("2025-01-08 11:00")) == "normal"
    assert seans_dilimi("DK_XAU", utc("2025-01-08 17:30")) == "kapali"      # günlük mola
    assert seans_dilimi("DK_XAU", utc("2025-01-11 11:00")) == "kapali"      # Cumartesi
    assert seans_dilimi("DK_XAU", utc("2025-01-08 05:00")) == "normal"      # emtia gece de açık
    for ny in ("2025-01-08 03:00", "2025-01-11 12:00", "2025-01-20 11:00"):
        assert seans_dilimi("BTCUSDT", utc(ny)) == "normal"


def test_tablo_ve_carpanlar():
    d = json.loads(sm.YOL.read_text(encoding="utf-8"))
    assert d["hisse"] == {"normal": 1.0, "genisletilmis": 2.0, "kapali": 3.0} and d["emtia"] == {"normal": 1.0, "kapali": 2.0}
    assert "OLCUM YOK" in d["_kaynak"]
    assert sm.dilim_ve_carpan("DK_NVDA", utc("2025-01-11 12:00")) == ("kapali", Decimal(3))
    assert sm.dilim_ve_carpan("DK_NVDA", utc("2025-01-08 05:00")) == ("genisletilmis", Decimal(2))
    assert sm.dilim_ve_carpan("DK_NVDA", utc("2025-01-08 11:00")) == ("normal", Decimal(1))
    assert sm.dilim_ve_carpan("DK_XAU", utc("2025-01-11 12:00")) == ("kapali", Decimal(2))
    assert sm.dilim_ve_carpan("BTCUSDT", utc("2025-01-11 12:00")) == ("normal", Decimal(1))


# ------------------------------------------------------------------ motor
def _motor(**kw):
    return PaperMotor(PortfoyAyarlari(baslangic_sermaye=KASA, limit_modu="uygula", **kw), {})


def test_motor_kayma_carpani_komisyon_degismez():
    m = _motor()
    taban_ky, taban_sk, taban_tk = m._ky("DK_NVDA"), m._sk("DK_NVDA"), m._tk("DK_NVDA")          # _an yok: çarpan 1
    m._an = utc("2025-01-11 12:00")                                                                # hafta sonu
    assert m._ky("DK_NVDA") == taban_ky * 3 and m._sk("DK_NVDA") == taban_sk * 3
    assert m._tk("DK_NVDA") == taban_tk and m._mk("DK_NVDA") == m.maker               # komisyon aynı
    assert m._ky("BTCUSDT") == taban_ky and m._sk("BTCUSDT") == taban_sk               # kripto 1x
    assert m._ky("DK_XAU") == taban_ky * 2
    m._an = utc("2025-01-08 11:00")
    assert m._ky("DK_NVDA") == taban_ky
    # boyutlandırma: en kötü seans çarpanı (stop hangi seansta çalışacağı bilinmez; %1 risk limiti aşılmasın)
    assert m._sk_taban("DK_NVDA") == taban_sk * 3 and m._sk_taban("DK_XAU") == taban_sk * 2 and m._sk_taban("BTCUSDT") == taban_sk


def test_motor_kapali_degilse_carpan_1():
    m = PaperMotor(PortfoyAyarlari(baslangic_sermaye=KASA, limit_modu="uygula"), {}, tetikleyen_hemen_kapat=False)   # backtest eşleşme aracı
    m._an = utc("2025-01-11 12:00")
    assert m._ky("DK_NVDA") == m.kayma and m._sk_taban("DK_NVDA") == m.stop_kayma


def _stop_kosusu(sembol, baslangic_utc):
    idx = pd.date_range(baslangic_utc, periods=8, freq="D", tz="UTC", name="zaman")
    p = 1000.0
    sat = [(p, p, p, p)] * 4 + [(p, p * 1.001, p * 0.97, p * 0.975)] + [(p * 0.975,) * 4] * 3
    df = pd.DataFrame(sat, columns=["acilis", "yuksek", "dusuk", "kapanis"], index=idx)
    df["hacim"], df["quote_hacim"], df["islem_sayisi"] = 1.0, 1.0, 1
    t = tanim(f"a|{sembol}|1d", sembol, pay="1", stop_yuzde=2.0)
    mal = em.sembol_maliyeti("BTCUSDT" if sembol == "XUSDT" else sembol, 1.0)
    ay = PortfoyAyarlari(baslangic_sermaye=KASA, limit_modu="uygula", maliyet_sembol={sembol: mal})
    return pp.tekrar_calistir([t], {(sembol, "1d"): df}, {}, {sembol: INCE}, idx[3], kapat=False, ayarlar=ay).motor


def _oran(m, tur):
    """Toplam maliyet kaleminin işlem nominaline oranı (giriş nominali)."""
    isl = m.islemler[0]
    return sum(float(x["tutar"]) for x in m.maliyet_log if x["tur"] == tur) / (isl["miktar"] * isl["giris_fiyati"])


def test_hisse_kapali_kayma_3x_komisyon_ayni(monkeypatch):
    # 02:00 UTC günlük mumlar = 21:00 NY (önceki gün): hep 'kapali'
    m3 = _stop_kosusu("DK_AAPL", "2025-01-07 02:00")
    monkeypatch.setitem(sm._onbellek, "t", {"hisse": {"normal": 1.0, "genisletilmis": 1.0, "kapali": 1.0}, "emtia": {"normal": 1.0, "kapali": 1.0}})
    m1 = _stop_kosusu("DK_AAPL", "2025-01-07 02:00")
    assert m3.islemler[0]["cikis_nedeni"] == m1.islemler[0]["cikis_nedeni"] == "stop"
    assert _oran(m3, "ucret") == pytest.approx(_oran(m1, "ucret"), rel=1e-2)                 # komisyon oranı değişmez (fark yalnız kayma farklı çıkış fiyatından)
    assert _oran(m3, "kayma") == pytest.approx(3 * _oran(m1, "kayma"), rel=0.05)            # kayma 3x


def test_islem_kaydi_alanlari():
    isl = _stop_kosusu("DK_AAPL", "2025-01-07 02:00").islemler[0]
    assert isl["seans_dilimi"] == "kapali" and isl["kayma_carpani"] == 3.0
    assert isl["cikis_seans_dilimi"] == "kapali" and isl["cikis_kayma_carpani"] == 3.0
    # normal seans: 15:00 UTC (10:00 NY), hafta içi gün (Pzt-Cum): giriş ve çıkış normal -> çarpan 1
    isl2 = _stop_kosusu("DK_AAPL", "2025-01-06 15:00").islemler[0]
    assert isl2["seans_dilimi"] == "normal" and isl2["kayma_carpani"] == 1.0
    assert isl2["cikis_seans_dilimi"] in ("normal", "kapali") and isl2["cikis_kayma_carpani"] in (1.0, 3.0)


def test_kripto_kaydi_degismez():
    isl = _stop_kosusu("XUSDT", "2025-01-11 02:00").islemler[0]
    assert not {"seans_dilimi", "kayma_carpani", "cikis_seans_dilimi", "cikis_kayma_carpani"} & set(isl)
