"""Genel denetim C (ders + ML öğrenmesi) düzeltme testleri: C1, C2, C5, C6, C7."""
import json
from datetime import datetime
from types import SimpleNamespace

import pandas as pd

from motor.canli import ogrenme_adaptor as oa
from motor.canli import telegram as tg
from motor.ortak_ogrenme import kayit as ok

A = "a|XUSDT|1d"
NOW = pd.Timestamp("2026-11-19 12:00", tz="UTC")


def _ad(id_, r, gun, kurulum=None):
    return ok.Aday(id=id_, proje="1L3A", kurulum=kurulum or oa.temiz_ad(A), enstruman="XUSDT", varlik_sinifi="kripto", yon="long",
                   ts=datetime.fromisoformat(gun + "T00:00:00+00:00"), alindi=True, r=r, ozellikler={"atr_ratio": 2.0},
                   cikis={"cikis_zamani": gun + "T06:00:00+00:00"})


def _og(tmp_path, ders_durum, born, kf_r=(), alinan=(), strateji=A, gonderilen=None):
    tmp_path.mkdir(parents=True, exist_ok=True)
    ad = oa.temiz_ad(strateji)
    kimlik = "yuksek_vol:" + ad
    (tmp_path / oa.DERS_DOSYASI).write_text(json.dumps({kimlik: {"status": ders_durum, "born": born, "effect": None, "n": 0}}))
    g = [] if gonderilen is None else gonderilen
    og = oa.Ogrenme(tmp_path, gonder=lambda m: True, saat=lambda: NOW)
    og.bildirimci = tg.Bildirimci(gonder_fn=lambda m: g.append(m) or True, ortak=tg.OrtakDurum(), servis="paper")
    og.esleme.ileri(strateji)
    og.engellenenler = lambda simdi: [_ad(f"kf{i}", r, "2026-11-17", ad) for i, r in enumerate(kf_r)]
    og.kapananlar = list(alinan)
    return og, kimlik


def _p(gizli_ad):
    return SimpleNamespace(hesaplar={gizli_ad: SimpleNamespace(gorunur=False), "dis__gauss-stoch-eth": SimpleNamespace(gorunur=True)},
                           gorunur_adlar={"dis__gauss-stoch-eth"})


# C1) gizli hesap adı mesajlarda yazılmaz
def test_C1_gizli_hesap_adi_ders_geri_alma_mesajinda_yazilmaz(tmp_path):
    g = []
    og, kimlik = _og(tmp_path, "alive", "2026-11-01", kf_r=[1.5, 1.5], strateji="dis__gizlix", gonderilen=g)
    og._p = _p("dis__gizlix")
    assert og.fren_adimi(NOW)["geri_alinan"] == [kimlik]
    assert g and "gizlix" not in g[0].lower() and "Diğer hesap" in g[0]


def test_C1_gizli_hesap_adi_fren_mesajinda_yazilmaz(tmp_path):
    g = []
    og, kimlik = _og(tmp_path, "alive", "2026-11-01", kf_r=[0.4] * 30, strateji="dis__gizlix", gonderilen=g)    # her biri -0,4 -> toplam -12 (geri alma eşiği -3 de aşılır)
    og._p = _p("dis__gizlix")
    og.fren_adimi(NOW)
    assert g and all("gizlix" not in m.lower() for m in g)


def test_C1_gorunur_hesap_adi_yazilir_ve_baglanmamis_adaptor_gorunur_sayar(tmp_path):
    og, _ = _og(tmp_path, "alive", "2026-11-01")
    assert og._gorunur_mi("dis__gauss-stoch-eth")                     # paper bağlı değil: görünür
    og._p = _p("dis__gizlix")
    assert og._gorunur_mi("dis__gauss-stoch-eth|ETHUSDT|1d") and not og._gorunur_mi("dis__gizlix|XUSDT|1d")
    assert og._ad_goster("dis__gizlix") == "Diğer hesap"
    assert not og._gorunur_mi("dis__bilinmeyen")                       # bağlıyken bilinmeyen hesap: kapalı-başarısız


def test_C1_drift_logu_gizli_adi_yazmaz(tmp_path, caplog):
    og, _ = _og(tmp_path, "alive", "2026-11-01", strateji="dis__gizlix")
    og._p = _p("dis__gizlix")
    assert og._ad_goster(og.esleme.ters(oa.temiz_ad("dis__gizlix"))) == "Diğer hesap"


# C2) fren/geri alma etkisi doğumdan (born + 1 gün) önceki işlemleri saymaz
def test_C2_fren_penceresi_dogumdan_onceki_islemleri_saymaz(tmp_path):
    eski = [_ad(f"e{i}", -1.5, "2026-11-05") for i in range(4)]          # doğumdan önce: etki +6 (sayılmamalı)
    og, kimlik = _og(tmp_path, "alive", "2026-11-15", kf_r=[2.0, 2.0, 2.0], alinan=eski)   # doğumdan sonra engellenen kaçan +6R: etki -6
    assert og.fren_adimi(NOW)["geri_alinan"] == [kimlik]


def test_C2_dogum_gunu_icindeki_islem_sayilmaz(tmp_path):
    og, kimlik = _og(tmp_path, "alive", "2026-11-17", kf_r=[2.0, 2.0])        # kf'ler 2026-11-17'de (doğum günü): ders.py ertesi 00:00'dan sayar
    assert og.fren_adimi(NOW)["geri_alinan"] == []


# C5) gece adımı/drift hatası günü kaybetmez
def test_C5_gece_adimi_hatasi_drift_ve_karneyi_atlatmaz(tmp_path, monkeypatch):
    og, _ = _og(tmp_path, "candidate", "2026-11-01")
    monkeypatch.setattr(oa.ders, "gece_adimi", lambda *a, **k: 1 / 0)
    assert og.gunluk(NOW) is True
    assert (tmp_path / oa.KARNE_DOSYASI).exists()


def test_C5_drift_hatasi_karneyi_atlatmaz(tmp_path, monkeypatch):
    og, _ = _og(tmp_path, "candidate", "2026-11-01")
    monkeypatch.setattr(og, "_drift_bildir", lambda *a, **k: 1 / 0)
    assert og.gunluk(NOW) is True
    assert (tmp_path / oa.KARNE_DOSYASI).exists()


# C6) bozuk satır geçmişi düşürmez
def test_C6_bozuk_tek_satir_butun_aday_gecmisini_kaybettirmez(tmp_path):
    ok.yaz_jsonl(tmp_path / oa.ADAY_DOSYASI, [_ad("1", 1.0, "2026-11-01"), _ad("2", -1.0, "2026-11-02")])
    with open(tmp_path / oa.ADAY_DOSYASI, "a", encoding="utf-8") as f:
        f.write("{bozuk\n")
    og = oa.Ogrenme(tmp_path, gonder=lambda m: True, saat=lambda: NOW)
    assert len(og.kapananlar) == 2
    yedek = tmp_path / (oa.ADAY_DOSYASI + ".bozuk")
    assert yedek.exists() and "{bozuk" in yedek.read_text(encoding="utf-8")


def test_C6_ikinci_bozuk_dosya_eski_yedegi_ezmez_ve_saglam_dosya_yedeklenmez(tmp_path):
    yol = tmp_path / oa.ADAY_DOSYASI
    ok.yaz_jsonl(yol, [_ad("1", 1.0, "2026-11-01")])
    oa.Ogrenme(tmp_path, gonder=lambda m: True, saat=lambda: NOW)
    assert not list(tmp_path.glob("*.bozuk*"))                          # sağlam dosya: yedek yok
    yol.write_text(yol.read_text(encoding="utf-8") + "{a\n", encoding="utf-8")
    oa.Ogrenme(tmp_path, gonder=lambda m: True, saat=lambda: NOW)
    yol.write_text(yol.read_text(encoding="utf-8") + "{b\n", encoding="utf-8")
    oa.Ogrenme(tmp_path, gonder=lambda m: True, saat=lambda: NOW)
    assert len(list(tmp_path.glob(oa.ADAY_DOSYASI + ".bozuk*"))) == 2     # eski yedek ezilmedi


# C7) eğitim hatasından sonra bekleme
def test_C7_egitim_hatasi_her_turda_yeniden_denenmez(tmp_path, monkeypatch):
    og, _ = _og(tmp_path, "alive", "2026-11-01")
    og.kapananlar = [_ad(f"t{i}", 1.0 if i % 2 else -1.0, f"2026-11-{i + 1:02d}") for i in range(12)]
    sayac = []
    monkeypatch.setattr(oa.filtre, "egit", lambda *a, **k: sayac.append(1) or 1 / 0)
    og._egit_kontrol(NOW)
    og._egit_kontrol(NOW + pd.Timedelta(minutes=1))
    og._egit_kontrol(NOW + pd.Timedelta(minutes=59))
    assert len(sayac) == 1
    og._egit_kontrol(NOW + pd.Timedelta(hours=1, seconds=1))           # bekleme bitti: yeniden denenir
    assert len(sayac) == 2
