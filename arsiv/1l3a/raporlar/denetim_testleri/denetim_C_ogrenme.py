"""Genel denetim C (ders + ML öğrenmesi): KIRMIZI testler. Kaynak koda dokunmaz."""
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


# 1) Gizli hesap adı Telegram'a sızar (ogrenme_adaptor.py:512,549: hesap_adi gorunur=True varsayılanı, gizlilik denetimi yok)
def test_gizli_hesap_adi_ders_geri_alma_mesajinda_yazilmaz(tmp_path):
    g = []
    og, kimlik = _og(tmp_path, "alive", "2026-11-01", kf_r=[1.5, 1.5], strateji="dis__gizlix", gonderilen=g)
    og._p = SimpleNamespace(hesaplar={"dis__gizlix": SimpleNamespace(gorunur=False)}, gorunur_adlar={"dis__gauss-stoch-eth"})
    assert og.fren_adimi(NOW)["geri_alinan"] == [kimlik]
    assert g and "gizlix" not in g[0].lower()


# 2) Fren/geri alma penceresi ders doğum gününü yok sayar (ogrenme_adaptor.py:482-499 + ders.py:_pencere_etkisi):
#    dersin doğmasına yol açan, doğumdan ÖNCEKİ kaybeden işlemler etkiyi + yapar, doğum sonrası -6R'yi maskeler.
def test_fren_penceresi_dogumdan_onceki_islemleri_saymaz(tmp_path):
    eski = [_ad(f"e{i}", -1.5, "2026-11-05") for i in range(4)]          # doğumdan önce: etki +6
    og, kimlik = _og(tmp_path, "alive", "2026-11-15", kf_r=[2.0, 2.0, 2.0], alinan=eski)   # doğumdan sonra engellenen kaçan +6R: etki -6
    assert og.fren_adimi(NOW)["geri_alinan"] == [kimlik]                    # beklenen: -6 <= -3 -> emekli; gerçek: net 0 -> hiçbir şey


# 3) Yaşam döngüsü boşluğu: aday ders girişi engelleyince gece_adimi yalnız ALINMIŞ işleme bakar (n=0) -> aday sonsuza dek aday kalır;
#    karşı-olgusal etki -2R (fren -10 ve geri alma -3'ün altında) olan ders ne alive ne retired olur, sonsuza dek engeller.
def test_negatif_kontrafaktuel_etkili_aday_ders_sonsuza_dek_aday_kalmaz(tmp_path):
    og, kimlik = _og(tmp_path, "candidate", "2026-11-01", kf_r=[1.0, 1.0])
    og.gunluk(NOW)
    assert json.loads((tmp_path / oa.DERS_DOSYASI).read_text())[kimlik]["status"] != "candidate"


# 4) gece_adimi etki <= 0 -> emekli (geri dönmez); fren eşiği -3R. Drift çarpanıyla sızan TEK kazanan işlem (+0.3R) dersi kalıcı emekli eder.
def test_tek_sizan_kucuk_kazanc_dersi_kalici_emekli_etmez(tmp_path):
    og, kimlik = _og(tmp_path, "candidate", "2026-11-01", alinan=[_ad("w", 0.3, "2026-11-10")])
    og.gunluk(NOW)
    assert json.loads((tmp_path / oa.DERS_DOSYASI).read_text())[kimlik]["status"] != "retired"   # -0.3R > -3R eşiği


# 5) gece_adimi try/except dışında (ogrenme_adaptor.py:421): hata drift + karneyi atlar ve gün işaretli olduğu için o gün bir daha denenmez.
def test_gece_adimi_hatasi_drift_ve_karneyi_atlatmaz(tmp_path, monkeypatch):
    og, _ = _og(tmp_path, "candidate", "2026-11-01")
    monkeypatch.setattr(oa.ders, "gece_adimi", lambda *a, **k: 1 / 0)
    og.gunluk(NOW)                                                          # gerçek: ZeroDivisionError yükselir
    assert (tmp_path / oa.KARNE_DOSYASI).exists()


# 6) Aday dosyasında TEK bozuk satır tüm geçmişi siler (ogrenme_adaptor.py:228-231 + kayit.oku_jsonl): kapananlar=[] -> sonraki yazım dosyayı ezer.
def test_bozuk_tek_satir_butun_aday_gecmisini_kaybettirmez(tmp_path):
    ok.yaz_jsonl(tmp_path / oa.ADAY_DOSYASI, [_ad("1", 1.0, "2026-11-01"), _ad("2", -1.0, "2026-11-02")])
    with open(tmp_path / oa.ADAY_DOSYASI, "a", encoding="utf-8") as f:
        f.write("{bozuk\n")
    og = oa.Ogrenme(tmp_path, gonder=lambda m: True, saat=lambda: NOW)
    assert len(og.kapananlar) == 2


# 7) Eğitim HATA verirse son-eğitim kaydı yazılmaz (ogrenme_adaptor.py:383-385) -> her paper adımında yeniden denenir (CPU + log seli).
def test_egitim_hatasi_her_turda_yeniden_denenmez(tmp_path, monkeypatch):
    og, _ = _og(tmp_path, "alive", "2026-11-01")
    og.kapananlar = [_ad(f"t{i}", 1.0 if i % 2 else -1.0, f"2026-11-{i + 1:02d}") for i in range(12)]
    sayac = []
    monkeypatch.setattr(oa.filtre, "egit", lambda *a, **k: sayac.append(1) or 1 / 0)
    og._egit_kontrol(NOW)
    og._egit_kontrol(NOW + pd.Timedelta(minutes=1))
    assert len(sayac) == 1
