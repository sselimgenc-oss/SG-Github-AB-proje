"""Denetim A (muhasebe/mutabakat) KIRMIZI testleri. Çalıştır: python -m pytest testler/denetim_A_muhasebe.py -q
(dosya adı test_ ile başlamadığı için yol açıkça verilir)."""
import json
from pathlib import Path

import pandas as pd
import pytest

from araclar import islem_mutabakat as im
from motor.canli import gunluk_ozet as go
from motor.canli import pano
from testler.test_islem_mutabakat import CT, GAUSS, GIZLI, _isl, _poz, _t, kurulum  # noqa: F401  (fixture yeniden kullanılır)


# --- A1: gizli hesabın kapanan işlemi ham motor karşılaştırmasında sahte uyuşmazlık + gizli işlem sızıntısı
def test_A1_gizli_hesap_ham_islemi_sahte_uyusmazlik_uretmez(kurulum):
    durum, ct = kurulum
    tum = [json.loads(x) for x in (durum / "islemler.jsonl").read_text(encoding="utf-8").splitlines()]
    gorunur = [x for x in tum if x["kimlik"] != GIZLI]
    gizli = [x for x in tum if x["kimlik"] == GIZLI]
    # GERÇEK yerleşim: üst düzey islemler.jsonl/maruziyet yalnız GÖRÜNÜR hesapları içerir (ToplamMotor), paper_state.json ise hepsini
    (durum / "islemler.jsonl").write_text("\n".join(json.dumps(x) for x in gorunur) + "\n", encoding="utf-8")
    mz = json.loads((durum / "maruziyet.json").read_text(encoding="utf-8"))
    mz["pozisyonlar"] = [p for p in mz["pozisyonlar"] if p["kimlik"] != GIZLI]
    (durum / "maruziyet.json").write_text(json.dumps(mz), encoding="utf-8")

    def ham(x):
        return {"sembol": x["sembol"], "yon": 1 if x["yon"] == "long" else -1, "giris_zamani": {"__T": x["giris_zamani"]}, "cikis_zamani": {"__T": x["cikis_zamani"]},
                "net_pnl": float(x["net_pnl_yerel"]), "miktar": float(x["miktar"]), "kol": "k"}
    acik = {"0": {"sembol": "SOLUSDT", "yon": -1, "giris": 150.0, "miktar": 1.0, "zaman": {"__T": _t(720)}, "kol": "k"}}
    st = {"hesaplar": {GAUSS: {"motor": {"islemler": [ham(x) for x in gorunur], "acik": acik}}, GIZLI: {"motor": {"islemler": [ham(x) for x in gizli], "acik": {}}}}}
    (durum / "paper_state.json").write_text(json.dumps(st), encoding="utf-8")
    c = im.hesapla(durum, ct)
    sahte = [u for u in c["ozet"]["uyusmazliklar"] if "ham motor işlemi durum dosyasında yok" in u["mesaj"]]
    assert not sahte, sahte          # beklenen: gizli hesabın işlemi kapsam dışı (ne uyuşmazlık, ne açık yayındaki mutabakat_v1.json'da coin/zaman)


# --- A4: gizli hesap listesi bir kez okunamazsa boş küme süreç boyu önbellekte kalır -> gizli adlar pano/Telegram'da açık görünür
def test_A4_gizli_liste_okunamazsa_bos_kume_kalici_onbelleklenmez(monkeypatch, tmp_path):
    from motor.canli import paper_v2 as v2
    gercek = v2.SET_YOLU
    monkeypatch.setattr(pano, "_GIZLI", None)
    monkeypatch.setattr(v2, "SET_YOLU", tmp_path / "yok.json")
    pano._gizli_adlar()                                   # set dosyası geçici okunamadı
    monkeypatch.setattr(v2, "SET_YOLU", gercek)           # dosya geri geldi
    assert pano._gizli_adlar(), "gizli hesap kümesi boş kaldı: gizli hesap adları panoda/Telegram'da görünür"


# --- A5: kasa kontrolü hiç yapılmadıysa (ozet.json yok) Telegram özeti yine de 'kasa tutuyor ✅' der
def test_A5_kasa_kontrolu_yoksa_tutuyor_denmez():
    from motor.canli import mutabakat_telegram as mt
    c = {"uretim": "2026-11-20T10:00:00Z", "satirlar": [],
         "ozet": {"islem_sayisi": 0, "kapanan_islem": 0, "acik_pozisyon": 0, "uyusmazlik_sayisi": 0, "uyusmazliklar": [], "short": {"sayi": 0}, "kasa_kontrolleri": []}}
    metin = mt.metin_uret(c)
    assert "✅" not in metin, metin


# --- A2: günün son saati tarihçe satırına girmez (saatlik yazım 23:00 sonrası durur; yeni gün satırı eskiyi güncellemez)
def test_A2_gun_son_saati_tarihcede_kaybolmaz(tmp_path, monkeypatch):
    from types import SimpleNamespace
    from testler.test_gunluk_ozet import KAYITLAR, _hesap, _islem
    d = tmp_path / "durum"
    for i, (_, klasor, _) in enumerate(KAYITLAR):
        _hesap(d / "hesaplar" / klasor, 10100, 5 + i, 100, islemler=[_islem("2026-11-19T05:00:00Z", "2026-11-19T08:00:00Z", "1")])
    ct = tmp_path / "ct"
    env = {"L3A_REJIM_KAPALI": "1", "L3A_DURDUR_DOSYA": str(d / "DURDUR")}
    p = SimpleNamespace(son_haftalik=None)
    go.paper_kancasi(p, d, pd.Timestamp("2026-11-19 20:05", tz="UTC"), False, lambda m: True, ct_dizin=ct, env=env)     # 23:05 TSİ
    for i, (_, klasor, _) in enumerate(KAYITLAR):                                                                         # 23:50'ye kadar +10 USD daha
        _hesap(d / "hesaplar" / klasor, 10110, 15 + i, 110, islemler=[_islem("2026-11-19T05:00:00Z", "2026-11-19T08:00:00Z", "1")])
    go.paper_kancasi(p, d, pd.Timestamp("2026-11-19 20:50", tz="UTC"), False, lambda m: True, ct_dizin=ct, env=env)     # 23:50 TSİ (dosya 45 dk: yazılmaz)
    go.paper_kancasi(p, d, pd.Timestamp("2026-11-19 21:10", tz="UTC"), False, lambda m: True, ct_dizin=ct, env=env)     # 00:10 TSİ, yeni gün
    satir = {x["gun"]: x for x in go.gecmis_oku(d)}["2026-11-19"]
    assert satir["kasa"]["gun_pnl"] == sum(15 + i for i in range(10)), satir["kasa"]["gun_pnl"]      # beklenen 195.0 (günün son bilinen değeri), gerçek 95.0
