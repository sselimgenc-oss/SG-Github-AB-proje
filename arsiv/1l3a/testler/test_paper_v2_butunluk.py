"""Paper v2: bütünlük kontrolü v2 setine göre (guven profil 'v2') + evrenden düşen sembollerin tek satıra indirilmesi."""
import json
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd
import pytest

from motor.canli import durum as d
from motor.canli import guven as gv
from motor.canli import pano
from motor.canli import paper as pp
from motor.canli import paper_v2 as v2
from testler.test_paper_v2 import SEM, kos, tanim, veri

KOK = Path(__file__).resolve().parents[1]
NEDEN = "DK_JNJ Binance USDⓈ-M exchangeInfo'da yok"
SIMDI_PANO = datetime(2026, 11, 12, 12, 0, tzinfo=timezone.utc)


def _tanimlar(n=7, ekstra=None):
    out = []
    for i in range(n):
        t = tanim(f"dis__s{i}", SEM)
        t.disarida = {"DK_JNJ": NEDEN, "DK_MA": NEDEN.replace("JNJ", "MA")}
        if ekstra and i == 0:
            t.disarida.update(ekstra)
        out.append(t)
    return out


# ---------------------------------------------------------------------------- gruplama
def test_disarida_beklenen_semboller_tek_bilgi_satiri():
    bilgi, uyari = pp.disarida_metinleri(pp.disarida_gruplari(_tanimlar()))
    assert bilgi == "DK_JNJ, DK_MA: Binance'te karşılığı yok → 7 stratejinin evreninden çıkarıldı (beklenen, kalıcı)"
    assert uyari == []


def test_disarida_beklenmeyen_sembol_gizlenmez_uyari_kalir():
    g = pp.disarida_gruplari(_tanimlar(ekstra={"DK_AAPL": "AAPLUSDT durumu BREAK (TRADING değil)", "BTCUSDT": "yerel veri yok: FileNotFoundError"}))
    bilgi, uyari = pp.disarida_metinleri(g)
    assert "BTCUSDT" not in bilgi and "7 stratejinin" in bilgi
    assert "DK_AAPL: borsada işleme kapandı" in bilgi                                  # TRADING dışı: uyarı değil, bilgi
    assert len(uyari) == 1 and uyari[0].startswith("BEKLENMEYEN") and "BTCUSDT" in uyari[0]    # asıl beklenmeyen neden (yerel veri yok) uyarı kalır
    # beklenen sembol ama FARKLI neden (ör. artık listede ama durumu değişti) = beklenmeyen
    g2 = pp.disarida_gruplari(_tanimlar(1, ekstra={"DK_JNJ": "DK_JNJ durumu BREAK (TRADING değil)"}))
    assert not next(x for x in g2 if x["sembol"] == "DK_JNJ")["beklenen"]


def test_disarida_bildir_olay_telegrama_gitmez_beklenmeyen_gider():
    class Sahte:
        def __init__(self):
            self.uyarilar, self.olaylar = [], []

        def olay_ekle(self, tur, mesaj, zaman=None, bildir=True):
            self.olaylar.append((tur, mesaj, bildir))
    p = Sahte()
    pp.disarida_bildir(p, _tanimlar(ekstra={"DK_AAPL": "AAPLUSDT durumu BREAK (TRADING değil)", "BTCUSDT": "yerel veri yok: FileNotFoundError"}), None)
    assert [o for o in p.olaylar if o[0] == "evren_bilgi"] == [("evren_bilgi", p.olaylar[0][1], False)] and len(p.olaylar) == 3
    assert ("evren_kapali", "AAPLUSDT borsada işleme kapandı, listeden çıkarıldı", True) in p.olaylar
    assert p.olaylar[2][0] == "veri_yok" and p.olaylar[2][2] is True and "BTCUSDT" in p.olaylar[2][1]
    assert len(p.uyarilar) == 2 and p.uyarilar[0].startswith(pp.BILGI_ONEKI)


# ---------------------------------------------------------------------------- pano: bilgi düzeyi + SAĞLIK ayrıntısı
def _durum(tmp_path, tanimlar):
    mum = veri()
    p = kos(tanimlar, mum, kapat=False)
    pp.disarida_bildir(p, p.tanimlar, None)
    simdi = mum[("BTCUSDT", "1d")].index[-1] + pd.Timedelta(days=1)
    return p, simdi


def test_pano_dusen_semboller_bilgi_duzeyinde_tek_satir_ve_saglik_ayrintisi(tmp_path):
    tans = _tanimlar(3)
    p, simdi = _durum(tmp_path, tans)
    v2.durum_yaz(p, p.kaynak, tmp_path, simdi, kaynak_adi="paper", veri_dizini=tmp_path)
    sg = json.loads((tmp_path / "saglik.json").read_text())
    assert sg["uyarilar"] == [] or all("evrenden düşen" not in u for u in sg["uyarilar"])
    assert len(sg["bilgiler"]) == 1 and sg["bilgiler"][0].startswith("DK_JNJ, DK_MA:")
    assert [x["sembol"] for x in sg["evren_disi"]] == ["DK_JNJ", "DK_MA"] and sg["evren_disi"][0]["stratejiler"] == ["dis__s0", "dis__s1", "dis__s2"]
    veri_, sorun = pano.yukle(tmp_path)
    u = pano.uyarilar(veri_, sorun, SIMDI_PANO)
    dusen = [(sev, m) for sev, m in u if "DK_JNJ" in m]
    assert dusen == []                                                          # 2026-11-14: beklenen/kalıcı düşme ÜST bantta yok, yalnız SAĞLIK
    html = pano.html_olustur(veri_, sorun, SIMDI_PANO)
    assert "beklenen, kalıcı" in html and "DK_JNJ" not in html
    oz = json.loads((tmp_path / "ozet.json").read_text())
    assert sum("DK_JNJ" in n for n in oz["notlar"]) == 1


def test_pano_beklenmeyen_dusme_uyari_kalir(tmp_path):
    tans = _tanimlar(2, ekstra={"DK_AAPL": "yerel veri yok: FileNotFoundError"})
    p, simdi = _durum(tmp_path, tans)
    v2.durum_yaz(p, p.kaynak, tmp_path, simdi, kaynak_adi="paper", veri_dizini=tmp_path)
    veri_, sorun = pano.yukle(tmp_path)
    u = pano.uyarilar(veri_, sorun, SIMDI_PANO)
    assert any(sev == "uyari" and "BEKLENMEYEN" in m and "DK_AAPL" in m for sev, m in u)
    assert not any("DK_JNJ" in m for sev, m in u)                              # beklenen düşme üst bantta yok


# ---------------------------------------------------------------------------- bütünlük: v2 profili
def test_v2_kaydi_depoyla_eslesir_ve_sert_limitler_guncel_kayit_yeni_arsiv_eski():
    mal = v2.cevrimdisi_maliyet_modeli()
    assert len(mal) == 10                                                      # 2026-11-14 odak seti (6 görünür + 4 gizli); kayıt butunluk_kayit_v2_10.json
    b = gv.butunluk("paper", "2026-11-12T00:00:00Z", None, profil="v2", maliyet=mal, onbellek_sn=0)
    assert b["genel_durum"] == "eslesti", [(x["id"], x["durum"]) for x in b["dosyalar"] + b["sanal"] if x["durum"] != "eslesti"]
    ids = {x["id"]: x for x in b["dosyalar"]}
    assert ids["set_dosyasi"]["yol"] == "stratejiler/paper_v2_seti.json"
    assert ids["maliyet_tablosu"]["yol"] == "sonuclar/evren/v2/maliyet_tablosu_v2.csv"
    assert ids["maliyet_tablosu"]["kayit_kaynagi"] == "sonuclar/evren/v2/maliyet_tablosu_v2.sha256"
    # SERT_LIMITLER günlük %3 -> %5 (kullanıcı kararı 2026-11-19): güncel v2_10 kaydı yeni özeti, mühürlü eski kayıt eski (%3) özeti taşır
    eski = json.loads((KOK / "sonuclar/final/butunluk_kayit.json").read_text())["sanal"]["sert_limitler"]["sha256"]
    yeni = json.loads((KOK / "stratejiler/butunluk_kayit_v2_10.json").read_text())["sanal"]["sert_limitler"]["sha256"]
    assert eski == gv.sha256_sozluk({**gv.sert_limitler(), "gunluk_max_kayip_yuzde": 3.0})
    assert yeni == gv.sha256_sozluk(gv.sert_limitler()) != eski


def test_v2_maliyet_degisirse_uyusmuyor_gizlenmez():
    mal = v2.cevrimdisi_maliyet_modeli()
    k = next(iter(mal))
    mal[k] = {**mal[k], "kayma_bps": (mal[k]["kayma_bps"] or 0) + 1.0}
    b = gv.butunluk("paper", "2026-11-12T00:00:00Z", None, profil="v2", maliyet=mal, onbellek_sn=0)
    assert b["genel_durum"] == "uyusmuyor" and next(x for x in b["sanal"] if x["id"] == "maliyet_modeli")["durum"] == "uyusmuyor"


def test_pano_v2_butunluk_eslesti_bant_yok(tmp_path):
    tans = _tanimlar(2)
    p, simdi = _durum(tmp_path, tans)
    p.butunluk_maliyet = lambda: v2.cevrimdisi_maliyet_modeli()          # sunucudaki gerçek 10 hesabın modeli (çevrimdışı eşdeğeri)
    v2.durum_yaz(p, p.kaynak, tmp_path, simdi, kaynak_adi="paper", veri_dizini=tmp_path)
    b = d.ek_oku(tmp_path, "butunluk")
    assert b["profil"] == "v2" and b["genel_durum"] == "eslesti" and b["sayim"]["uyusmuyor"] == 0
    veri_, sorun = pano.yukle(tmp_path)
    assert not any("Backtest bütünlüğü" in m for _, m in pano.uyarilar(veri_, sorun, SIMDI_PANO))
    html = pano.html_olustur(veri_, sorun, SIMDI_PANO)
    assert "kayıtlı sha256 ile uyuşmuyor" not in html and "paper_v2_seti.json" not in html
    # hesap dizinlerindeki pano da aynı (hesap başına değil set başına model)
    bh = d.ek_oku(tmp_path / "hesaplar" / "dis__s0", "butunluk")
    assert bh["genel_durum"] == "eslesti"


def test_pano_v2_gercek_olmayan_hesaplar_uyusmuyor_gosterir(tmp_path):
    """Sentetik hesaplar (farklı maliyet modeli) kayıtla eşleşmez -> kontrol zayıflatılmadı."""
    p, simdi = _durum(tmp_path, _tanimlar(2))
    v2.durum_yaz(p, p.kaynak, tmp_path, simdi, kaynak_adi="paper", veri_dizini=tmp_path)
    assert d.ek_oku(tmp_path, "butunluk")["genel_durum"] == "uyusmuyor"


def test_disarida_bildir_eski_kopyalari_temizler():
    """Kayıtlı durumdan gelen eski strateji-başı satırlar ve önceki başlangıcın bilgi satırı yeniden başlatmada birikmez."""
    from types import SimpleNamespace
    from motor.canli import paper as pp

    olay = []
    p = SimpleNamespace(uyarilar=["dis__x: evrenden düşen semboller (Binance karşılığı yok/TRADING değil): DK_JNJ (yok)", "baska uyari"],
                        olay_ekle=lambda *a, **k: olay.append(a))
    t = SimpleNamespace(kimlik="dis__x", disarida={"DK_JNJ": "DK_JNJ Binance USDⓈ-M exchangeInfo'da yok"})
    pp.disarida_bildir(p, [t], "2026-11-10")
    pp.disarida_bildir(p, [t], "2026-11-10")
    assert "baska uyari" in p.uyarilar
    assert not any("evrenden düşen semboller (" in u for u in p.uyarilar)
    assert sum(u.startswith(pp.BILGI_ONEKI) for u in p.uyarilar) == 1
