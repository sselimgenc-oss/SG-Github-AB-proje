"""Genel denetim (muhasebe/mutabakat/pano/özet/boşluk) düzeltme testleri: A1, A2, A3, A4, B4, D4, D5."""
import json
from decimal import Decimal
from types import SimpleNamespace

import pandas as pd
import pytest

from araclar import islem_mutabakat as im
from motor.canli import bosluk_maruziyet as bm
from motor.canli import gunluk_ozet as go
from motor.canli import pano
from testler.test_islem_mutabakat import CT, GAUSS, GIZLI, _isl, _poz, _t, kurulum  # noqa: F401  (fixture yeniden kullanılır)


# --- A1: gizli hesabın kapanan işlemi ham motor karşılaştırmasında sahte uyuşmazlık / iz üretmez
def test_A1_gizli_hesap_ham_islemi_sahte_uyusmazlik_uretmez(kurulum):
    durum, ct = kurulum
    tum = [json.loads(x) for x in (durum / "islemler.jsonl").read_text(encoding="utf-8").splitlines()]
    gorunur = [x for x in tum if x["kimlik"] != GIZLI]
    gizli = [x for x in tum if x["kimlik"] == GIZLI]
    assert gizli
    (durum / "islemler.jsonl").write_text("\n".join(json.dumps(x) for x in gorunur) + "\n", encoding="utf-8")
    mz = json.loads((durum / "maruziyet.json").read_text(encoding="utf-8"))
    mz["pozisyonlar"] = [p for p in mz["pozisyonlar"] if p["kimlik"] != GIZLI]
    (durum / "maruziyet.json").write_text(json.dumps(mz), encoding="utf-8")
    oz = json.loads((durum / "ozet.json").read_text(encoding="utf-8"))
    oz["sayaclar"]["acik_pozisyon"] = 1                                   # üst düzey sayaç yalnız görünür hesapları sayar
    (durum / "ozet.json").write_text(json.dumps(oz), encoding="utf-8")

    def ham(x):
        return {"sembol": x["sembol"], "yon": 1 if x["yon"] == "long" else -1, "giris_zamani": {"__T": x["giris_zamani"]}, "cikis_zamani": {"__T": x["cikis_zamani"]},
                "net_pnl": float(x["net_pnl_yerel"]), "miktar": float(x["miktar"]), "kol": "k"}
    acik = {"0": {"sembol": "SOLUSDT", "yon": -1, "giris": 150.0, "miktar": 1.0, "zaman": {"__T": _t(720)}, "kol": "k"}}
    st = {"hesaplar": {GAUSS: {"motor": {"islemler": [ham(x) for x in gorunur], "acik": acik}}, GIZLI: {"motor": {"islemler": [ham(x) for x in gizli], "acik": {}}}}}
    (durum / "paper_state.json").write_text(json.dumps(st), encoding="utf-8")
    c = im.hesapla(durum, ct)
    sahte = [u for u in c["ozet"]["uyusmazliklar"] if "ham motor işlemi durum dosyasında yok" in u["mesaj"]]
    assert not sahte, sahte
    assert c["ozet"]["uyusmazlik_sayisi"] == 0, c["ozet"]["uyusmazliklar"]
    cikti = json.dumps(c, ensure_ascii=False)
    assert "XRP" not in cikti and gizli[0]["cikis_zamani"] not in cikti          # gizli hesabın coin'i/zamanı çıktıda yok


def test_A1_ham_motor_gizli_hesabi_atlar(tmp_path):
    st = {"hesaplar": {"gor": {"motor": {"islemler": [{"sembol": "SOLUSDT", "yon": 1, "net_pnl": 1.0}], "acik": {}}},
                       "dis__gizlix": {"motor": {"islemler": [{"sembol": "XRPUSDT", "yon": 1, "net_pnl": 2.0}], "acik": {}}}}}
    (tmp_path / "paper_state.json").write_text(json.dumps(st), encoding="utf-8")
    ham = im.ham_motor(tmp_path, {"dis__gizlix"})
    assert [x["sembol"] for x in ham["islemler"]] == ["SOLUSDT"]
    assert len(im.ham_motor(tmp_path, None)["islemler"]) == 2                    # süzgeç yoksa (ct/aday) hepsi


# --- A2: gizli liste okunamazsa önbelleğe yazılmaz, o turda hepsi gizli sayılır
def test_A2_gizli_liste_okunamazsa_bos_kume_kalici_onbelleklenmez(monkeypatch, tmp_path):
    from motor.canli import paper_v2 as v2
    gercek = v2.SET_YOLU
    monkeypatch.setattr(pano, "_GIZLI", None)
    monkeypatch.setattr(v2, "SET_YOLU", tmp_path / "yok.json")
    kapali = pano._gizli_adlar()                                    # set dosyası geçici okunamadı
    assert pano._GIZLI is None                                      # önbelleğe yazılmadı
    assert "dis__gizlix" in kapali and "dis__gauss-stoch-eth" in kapali      # kapalı-başarısız: her hesap gizli
    assert pano._ad_goster("dis__gizlix") == "Diğer hesap" and pano._ad_goster("dis__gauss-stoch-eth") == "Diğer hesap"
    monkeypatch.setattr(v2, "SET_YOLU", gercek)                     # dosya geri geldi
    assert pano._gizli_adlar(), "gizli hesap kümesi boş kaldı"
    assert pano._GIZLI is not None


def test_A2_mutabakat_gizli_okunamazsa_hepsi_gizli(monkeypatch):
    monkeypatch.setattr(pano, "_GIZLI", None)
    monkeypatch.setattr(pano, "_gizli_adlar", lambda: (_ for _ in ()).throw(OSError("x")))
    g = im._gizli()
    assert not im._pano_gorunur("dis__gizlix", g) and not im._tg_gorunur("dis__gizlix", g)


# --- A3: TSİ gün sınırı geçince önceki günün satırı son kez yazılır
def test_A3_gun_son_saati_tarihcede_kaybolmaz(tmp_path):
    from testler.test_gunluk_ozet import KAYITLAR, _hesap, _islem
    d = tmp_path / "durum"
    for i, (_, klasor, _) in enumerate(KAYITLAR):
        _hesap(d / "hesaplar" / klasor, 10100, 5 + i, 100, islemler=[_islem("2026-11-19T05:00:00Z", "2026-11-19T08:00:00Z", "1")])
    ct = tmp_path / "ct"
    env = {"L3A_REJIM_KAPALI": "1", "L3A_DURDUR_DOSYA": str(d / "DURDUR")}
    p = SimpleNamespace(son_haftalik=None)
    go.paper_kancasi(p, d, pd.Timestamp("2026-11-19 20:05", tz="UTC"), False, lambda m: True, ct_dizin=ct, env=env)     # 23:05 TSİ
    for i, (_, klasor, _) in enumerate(KAYITLAR):
        _hesap(d / "hesaplar" / klasor, 10110, 15 + i, 110, islemler=[_islem("2026-11-19T05:00:00Z", "2026-11-19T08:00:00Z", "1")])
    go.paper_kancasi(p, d, pd.Timestamp("2026-11-19 20:50", tz="UTC"), False, lambda m: True, ct_dizin=ct, env=env)     # 23:50 TSİ (yazılmaz)
    go.paper_kancasi(p, d, pd.Timestamp("2026-11-19 21:10", tz="UTC"), False, lambda m: True, ct_dizin=ct, env=env)     # 00:10 TSİ, yeni gün
    gecmis = {x["gun"]: x for x in go.gecmis_oku(d)}
    assert gecmis["2026-11-19"]["kasa"]["gun_pnl"] == sum(15 + i for i in range(10))
    assert "2026-11-20" in gecmis                                    # yeni günün satırı da yazıldı


# --- A4: kasa kontrolü yoksa "kasa tutuyor" denmez, sorun da sayılmaz
def test_A4_kasa_kontrolu_yoksa_tutuyor_denmez_sorun_sayilmaz():
    from motor.canli import mutabakat_telegram as mt
    c = {"uretim": "2026-11-20T10:00:00Z", "satirlar": [],
         "ozet": {"islem_sayisi": 0, "kapanan_islem": 0, "acik_pozisyon": 0, "uyusmazlik_sayisi": 0, "uyusmazliklar": [], "short": {"sayi": 0}, "kasa_kontrolleri": []}}
    assert not mt.sorun_var(c)
    assert mt.metin_uret(c) == ""
    c["ozet"]["kasa_kontrolleri"] = [{"hesap": "x", "tamam": False}]
    assert mt.sorun_var(c) and "tutuyor" not in mt.metin_uret(c).replace("tutmuyor", "")


# --- B4: alınsaydı gevşetme kartı okunur satırlar
def _gv(**kw):
    return {"veri": {"alinsaydi_gevsetme": kw}}


def test_B4_gevsetme_karti_okunur_satirlar():
    kart = pano._degisiklikler_karti(_gv(
        aktif={"etiket:haber_ters": {"zaman": "2026-11-19T01:00:00Z", "kanit": {"cozulen": 12, "toplam_r": 3.0, "ort_r": 0.25, "pencere_gun": 30}}},
        askida={"etiket:kalabalik": {"zaman": "x", "kanit": {}}}, kara_liste=["ml_filtre"], fren={}, gecisler=[{"neden": "etiket:haber_ters", "k": "abcdef123456", "t": "x"}])["veri"])
    assert "«ters haber akışı» filtresi gevşetildi · 12 sinyal · +3,00 R" in kart
    assert "«öğrenilmiş puan filtresi» filtresi geri alındı" in kart
    assert "«kalabalık pozisyon (fonlama/açık faiz)» filtresi askıda" in kart
    assert "abcdef123456" not in kart and "Henüz değişiklik yok" not in kart


def test_B4_hic_degisiklik_yoksa_henuz_degisiklik_yok():
    bos = {"aktif": {}, "askida": {}, "kara_liste": [], "fren": {}, "gecisler": [], "son_gun": None}
    assert "Henüz değişiklik yok" in pano._degisiklikler_karti({"alinsaydi_gevsetme": bos})
    assert "Henüz değişiklik yok" in pano._degisiklikler_karti({})


# --- D4/D5: boşluk riski eşik >= ve mevcut zirveden düşüş
def test_D4_bosluk_esik_esitlikte_ihlal():
    o = bm.hesapla([{"ad": "h", "gizli": False, "kasa": 1000.0, "pozisyonlar": [{"sembol": "DK_AAPL", "nominal": 1000.0}]}],
                   pd.Timestamp("2026-11-18T20:45Z"), esik=0.20)
    assert o["hesaplar"][0]["kayip_yuzde"] == pytest.approx(0.20)
    assert o["hesaplar"][0]["ihlal"]
    alti = bm.hesapla([{"ad": "h", "gizli": False, "kasa": 1000.0, "pozisyonlar": [{"sembol": "DK_AAPL", "nominal": 990.0}]}],
                      pd.Timestamp("2026-11-18T20:45Z"), esik=0.20)
    assert not alti["hesaplar"][0]["ihlal"]


def test_D5_bosluk_mevcut_dususle_kill_tetikleyecekse_ihlal():
    poz = SimpleNamespace(sembol="DK_AAPL", miktar=Decimal(25))
    motor = SimpleNamespace(acik={"x": poz}, son_kap={"DK_AAPL": 100.0}, zirve=Decimal(10000), ozsermaye=lambda: Decimal(8500))      # zirveden -%15
    o = bm.hesapla(bm.hesaplari_cikar(SimpleNamespace(motor=motor)), pd.Timestamp("2026-11-18T20:45Z"), esik=0.20)
    assert o["hesaplar"][0]["ihlal"]
    motor.ozsermaye = lambda: Decimal(9000)                       # zirveden -%10: 2250 x 0.2 = 450 -> -%14,5, ihlal yok
    o = bm.hesapla(bm.hesaplari_cikar(SimpleNamespace(motor=motor)), pd.Timestamp("2026-11-18T20:45Z"), esik=0.20)
    assert not o["hesaplar"][0]["ihlal"]
    motor.zirve = Decimal(9000)                                   # zirve = kasa: düşüş 0
    o = bm.hesapla(bm.hesaplari_cikar(SimpleNamespace(motor=motor)), pd.Timestamp("2026-11-18T20:45Z"), esik=0.20)
    assert not o["hesaplar"][0]["ihlal"]
