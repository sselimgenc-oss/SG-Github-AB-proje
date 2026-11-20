"""ct_konsensus: ML filtre + ders + etiket kuralları (korku/açgözlülük dahil) ct hesabının girişine de bağlı; kendi durum dizini; ön kayıt sabitleri aynı."""
import json

import pytest

from motor.canli import ct_kadro as ck
from motor.canli import ct_paper as cp
from motor.canli import etiket_kurallari as ek
from motor.canli import ogrenme_adaptor as oa
from testler.test_ct_kadro import coin, kapanis, ozet, paper_kur
from testler.test_kayit_etiketleri import kayit, satirlar


def _kur(tmp_path, korku=50):
    s1 = ozet(kapanis(110), [coin("BTC", 8, 1, 2e6)])
    p, _ = paper_kur(s1, tmp_path=tmp_path / "kadro")
    ct_dizin = tmp_path / "ct"
    ct_dizin.mkdir()
    p.kayit_ac(kayit(ct_dizin, fng_fn=lambda: [(__import__("pandas").Timestamp("2026-01-01", tz="UTC") + __import__("pandas").Timedelta(days=i), korku)
                                              for i in range(400)]))
    return p, ct_dizin


def test_ct_etiket_kurali_korku_acgozluluk_girisi_atlatir_ve_kaydeder(tmp_path):
    p, ct_dizin = _kur(tmp_path, korku=90)                       # aşırı açgözlülük: long atlanır
    assert ek.bagla(p)
    p.baslat(kapanis(105))
    p.adim(kapanis(112))
    assert not p.motor.acik
    assert "etiket:korku_acgozluluk" in [s["neden"] for s in satirlar(ct_dizin)]


def test_ct_serbest_korkuda_giris_acilir_on_kayit_sabitleri_ayni(tmp_path):
    p, ct_dizin = _kur(tmp_path, korku=50)
    ek.bagla(p)
    p.baslat(kapanis(105))
    p.adim(kapanis(112))
    assert {x.sembol for x in p.motor.acik.values()} == {"BTCUSDT"}
    assert (ck.MIN_TRADER, ck.MIN_ORAN, ck.MAX_POZ, ck.STOP_ATR, ck.HEDEF_ATR) == (5, 0.70, 3, 2.0, 3.0)      # ön kayıt sabitleri değişmedi


def test_ct_gercek_ozellik_yolu_hatasiz_calisir(tmp_path):
    p, ct_dizin = _kur(tmp_path, korku=50)
    og = oa.Ogrenme(ct_dizin, gonder=lambda m: True)
    og.bagla(p)                                                   # varsayılan ozellik_uret (mum/ATR/etiket) ct hesabında da çalışır
    ek.bagla(p)
    p.baslat(kapanis(105))
    p.adim(kapanis(112))
    assert {x.sembol for x in p.motor.acik.values()} == {"BTCUSDT"}    # süzgeçler izin verdi (veri/ders yok), hata fail-open değil gerçek yol


def test_ct_ders_girisi_atlatir_kendi_durum_dizininde(tmp_path):
    p, ct_dizin = _kur(tmp_path, korku=50)
    kim = p.tanimlar[0].kimlik
    ad = oa.temiz_ad(kim)
    (ct_dizin / oa.DERS_DOSYASI).write_text(json.dumps({f"yuksek_vol:{ad}": {"status": "candidate", "born": "2026-01-01", "effect": None, "n": 0}}))
    og = oa.Ogrenme(ct_dizin, gonder=lambda m: True)
    og.bagla(p)
    p.motor.ozellik_kancasi = lambda t, e: {"atr_ratio": 2.0}
    p.baslat(kapanis(105))
    p.adim(kapanis(112))
    assert not p.motor.acik
    assert "ders:yuksek_vol" in [s["neden"] for s in satirlar(ct_dizin)]
    assert not (tmp_path / "kadro" / oa.DERS_DOSYASI).exists()    # kayıt yalnız ct dizininde
