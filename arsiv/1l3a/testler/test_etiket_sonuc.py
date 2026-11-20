"""Etiket × sonuç kartı (etiket_sonuc.py): saf tablo, birim seçimi, gizli hesap adı, haftalık satır, paper kancası bağlantısı."""
import json
from pathlib import Path

import pandas as pd

from motor.canli import etiket_sonuc as es
from motor.canli import gunluk_ozet as go
from motor.canli import paper_v2 as v2

SIMDI = pd.Timestamp("2026-11-22 18:30", tz="UTC")          # Pazar, TSİ 21:30 (haftalık özet anı)
GUN = "2026-11-22"
SET = json.loads(v2.SET_YOLU.read_text(encoding="utf-8"))
HESAPLAR = [(v2.hesap_adi(k), v2.hesap_dizin_adi(v2.hesap_adi(k)), v2.gorunur_mu(k)) for k in SET["stratejiler"]]
GIZLI_AD = [ad for ad, _, g in HESAPLAR if not g]


HISSE = sorted(__import__("motor.canli.paper_takvim", fromlist=["x"]).ABD_HISSELERI)[0]


def _t(r=None, net=None, yon="long", etiketler=None, seans=None, sembol=None, zaman="2026-11-21T10:00:00Z"):
    t = {"yon": yon, "zaman": zaman}
    if sembol is not None:
        t["sembol"] = sembol
    if r is not None:
        t["r"] = r
    if net is not None:
        t["net_pnl_yerel"] = net
    if etiketler is not None:
        t["etiketler"] = etiketler
    if seans is not None:
        t["seans_dilimi"] = seans
    return t


def _satir(tablo, ad, deger):
    return next(s for s in tablo[ad] if s["deger"] == deger)


# ----------------------------------------------------------------------------------------------- saf tablo
def test_rejim_gruplari_ve_r_toplamlari():
    islemler = [
        _t(r=2.0, etiketler={"rejim_ml_1d": "trend_up"}),
        _t(r=2.2, etiketler={"rejim_ml_1d": "trend_up"}),
        _t(r=-1.0, etiketler={"rejim_ml_1d": "trend_down"}, yon="short"),
        _t(r=0.5),                                     # etiket yok -> bilinmiyor
    ]
    tab = es.etiket_tablosu(islemler)
    up = _satir(tab, "rejim_ml_1d", "trend_up")
    assert (up["islem"], up["kazanan"], up["isabet_yuzde"], up["toplam"], up["ort"]) == (2, 2, 100.0, 4.2, 2.1)
    assert _satir(tab, "rejim_ml_1d", "trend_down")["kazanan"] == 0
    bil = _satir(tab, "rejim_ml_1d", "bilinmiyor")
    assert bil["islem"] == 1 and bil["toplam"] == 0.5
    # bilinmiyor her zaman sonda
    assert tab["rejim_ml_1d"][-1]["deger"] == "bilinmiyor"


def test_birim_r_yoksa_usd():
    islemler = [_t(r=1.0, net=10.0), _t(net=-5.0)]          # bir işlemde R yok -> tüm tablo USD
    assert es.birim_sec(islemler) == "USD"
    tab = es.etiket_tablosu(islemler)
    assert _satir(tab, "rejim_ml_1d", "bilinmiyor")["toplam"] == 5.0    # net 10 + (-5); R (1.0) kullanılmadı
    assert es.birim_sec([_t(r=1.0), _t(r=-2.0)]) == "R"


def test_olculemeyen_islem_tabloya_girmez():
    islemler = [_t(r=None, net=None, etiketler={"rejim_ml_1d": "trend_up"})]
    tab = es.etiket_tablosu(islemler)
    assert tab["rejim_ml_1d"] == []
    assert es.kart(islemler, "x", GUN)["olculemeyen"] == 1


def test_korku_dilimleri_siniri():
    cases = {0: "0-25", 24.9: "0-25", 25: "25-50", 50: "50-75", 74: "50-75", 75: "75-100", 100: "75-100", None: "bilinmiyor", 101: "bilinmiyor"}
    for v, beklenen in cases.items():
        assert es._korku_dilimi(v) == beklenen, v


def test_kalabalik_esikleri_yon_bagimli():
    kalabalik = {"fonlama_orani": 0.0005, "oi_degisim_24s": 0.10}
    assert es._kalabalik(_t(yon="long", etiketler=kalabalik)) == "kalabalik"
    assert es._kalabalik(_t(yon="short", etiketler=kalabalik)) == "degil"
    assert es._kalabalik(_t(yon="short", etiketler={"fonlama_orani": -0.0005, "oi_degisim_24s": 0.10})) == "kalabalik"
    assert es._kalabalik(_t(yon="long", etiketler={"fonlama_orani": 0.0004, "oi_degisim_24s": 0.5})) == "degil"
    assert es._kalabalik(_t(yon="long", etiketler={"fonlama_orani": 0.001, "oi_degisim_24s": None})) == "bilinmiyor"
    assert es._kalabalik(_t(yon="long")) == "bilinmiyor"


def test_takvim_yok_ve_bilinmiyor_ayrimi():
    islemler = [_t(r=1, etiketler={"takvim_bayragi": None}), _t(r=1, etiketler={"takvim_bayragi": "CPI"}), _t(r=1, etiketler={})]
    tab = es.etiket_tablosu(islemler)
    assert _satir(tab, "takvim_bayragi", "yok")["islem"] == 1
    assert _satir(tab, "takvim_bayragi", "CPI")["islem"] == 1
    assert _satir(tab, "takvim_bayragi", "bilinmiyor")["islem"] == 1


def test_seans_dilimi_kripto_haric_ve_tum_etiket_adlari_var():
    islemler = [_t(r=1, seans="acik", sembol=HISSE), _t(r=-1, sembol=HISSE), _t(r=3, sembol="BTCUSDT", seans="acik")]
    tab = es.etiket_tablosu(islemler)
    assert set(tab) == set(es.ETIKET_ADLARI)
    assert _satir(tab, "seans_dilimi", "acik")["islem"] == 1          # kripto (BTCUSDT) tabloya girmez
    assert _satir(tab, "seans_dilimi", "bilinmiyor")["islem"] == 1    # yalnız hisse/emtia, alanı eksik
    assert sum(s["islem"] for s in tab["seans_dilimi"]) == 2
    assert sum(s["islem"] for s in tab["rejim_ml_1d"]) == 3           # diğer etiketlerde kripto dahil


def test_rejim_karsit_sayisi():
    islemler = [_t(r=1, yon="long", etiketler={"rejim_ml_1d": "trend_down"}),
                _t(r=1, yon="short", etiketler={"rejim_ml_4h": "trend_up"}),
                _t(r=1, yon="long", etiketler={"rejim_ml_1d": "trend_up"})]
    assert es.rejim_karsit_sayisi(islemler) == 2


# ----------------------------------------------------------------------------------------------- haftalık satır
def test_haftalik_satir_biçimi():
    islemler = [_t(r=1.0, yon="long", etiketler={"rejim_ml_1d": "trend_up"}) for _ in range(8)]
    islemler += [_t(r=-0.5, yon="long", etiketler={"rejim_ml_1d": "trend_up"}) for _ in range(4)]
    islemler += [_t(r=0.2, yon="long", etiketler={"rejim_ml_1d": "range"})]
    e = es.kart(islemler, "x", GUN)
    assert es.haftalik_satir(e) == "Etiket: rejim karşıtı yok; en iyi rejim trend_up +6,0R (12 işlem)"


def test_haftalik_satir_karsit_ve_bos():
    e = es.kart([_t(r=1.0, yon="long", etiketler={"rejim_ml_1d": "trend_down"})], "x", GUN)
    assert es.haftalik_satir(e) == "Etiket: rejim karşıtı 1 işlem; en iyi rejim trend_down +1,0R (1 işlem)"
    sadece_bilinmiyor = es.kart([_t(r=1.0)], "x", GUN)
    assert es.haftalik_satir(sadece_bilinmiyor).endswith("en iyi rejim verisi yok")
    assert es.haftalik_satir(es.kart([], "x", GUN)) == "Etiket: son 7 günde kapanan işlem yok"


def test_haftalik_satir_yalniz_son_7_gun_kapanislari():
    eski = [_t(r=5.0, etiketler={"rejim_ml_1d": "trend_up"}, zaman="2026-11-01T10:00:00Z")]     # 21 gün önce kapanmış
    e = es.kart(eski, "x", GUN)
    assert e["islem_sayisi"] == 1 and e["etiketler"]["rejim_ml_1d"][0]["toplam"] == 5.0    # üst düzey: tüm dönem
    assert e["son_7_gun"]["islem_sayisi"] == 0
    assert es.haftalik_satir(e) == "Etiket: son 7 günde kapanan işlem yok"
    karisik = eski + [_t(r=1.0, etiketler={"rejim_ml_1d": "trend_up"}, zaman="2026-11-20T10:00:00Z")]
    s = es.haftalik_satir(es.kart(karisik, "x", GUN))
    assert s == "Etiket: rejim karşıtı yok; en iyi rejim trend_up +1,0R (1 işlem)"
    assert es.haftalik_satir(None) is None


def test_haftalik_satir_usd_birimi():
    e = es.kart([_t(net=12.345, etiketler={"rejim_ml_1d": "trend_up"})], "x", GUN)
    assert es.haftalik_satir(e).endswith("en iyi rejim trend_up +12,35 USD (1 işlem)")


# ----------------------------------------------------------------------------------------------- dosya ve gizlilik
def _hesap_dizinleri(durum: Path):
    for ad, klasor, _g in HESAPLAR:
        d = durum / "hesaplar" / klasor
        d.mkdir(parents=True, exist_ok=True)
        (d / "islemler.jsonl").write_text(json.dumps(_t(r=1.5, etiketler={"rejim_ml_1d": "trend_up"})) + "\n", encoding="utf-8")


def test_yaz_gizli_hesap_adi_yazmaz(tmp_path):
    _hesap_dizinleri(tmp_path)
    o = es.yaz(tmp_path, SIMDI)
    assert o is not None and o["sema"] == "etiket_sonuc.v1" and o["islem_sayisi"] == len(HESAPLAR)
    metin = (tmp_path / es.DOSYA).read_text(encoding="utf-8")
    for ad in GIZLI_AD:
        assert ad not in metin
    assert "gizli" not in metin.lower()
    assert json.loads(metin)["etiketler"]["rejim_ml_1d"][0]["islem"] == len(HESAPLAR)


def test_yaz_hata_paper_durdurmaz(tmp_path):
    dosya = tmp_path / "yol_dosya"
    dosya.write_text("x", encoding="utf-8")                    # dizin değil: yazım hata verir, None döner
    assert es.yaz(dosya, SIMDI) is None


def test_paper_kancasi_haftalik_satir_ekler(tmp_path, monkeypatch):
    _hesap_dizinleri(tmp_path)
    mesajlar = []

    class P:
        son_haftalik = None

    gonderildi = go.paper_kancasi(P(), tmp_path, SIMDI, gunluk_zamani=False, gonder=lambda m: mesajlar.append(m) or True)
    assert gonderildi is True
    assert (tmp_path / es.DOSYA).exists()
    assert any("Etiket: " in m for m in mesajlar)
    assert all(not any(ad in m for ad in GIZLI_AD) for m in mesajlar)


# ----------------------------------------------------------------------------------------------- pano kartı (yalnız çizer)
def test_pano_karti_veri_yok_ve_tablo():
    from motor.canli import pano

    assert "Etiket × sonuç" in pano._etiket_karti(None)
    e = es.kart([_t(r=2.0, yon="long", etiketler={"rejim_ml_1d": "trend_up"}), _t(r=-1.0, yon="long", etiketler={"rejim_ml_1d": "trend_up"})], "x", GUN)
    html = pano._etiket_karti(e)
    assert "Rejim (1 gün)" in html and "rejim_ml_1d" not in html
    assert "trend_up" in html and "2 işlem" in html


def test_pano_etiket_oku_bozuk_dosya(tmp_path):
    from motor.canli import pano

    assert pano._etiket_oku(tmp_path) is None
    (tmp_path / es.DOSYA).write_text("{bozuk", encoding="utf-8")
    assert pano._etiket_oku(tmp_path) is None
    (tmp_path / es.DOSYA).write_text(json.dumps({"sema": "baska"}), encoding="utf-8")
    assert pano._etiket_oku(tmp_path) is None
