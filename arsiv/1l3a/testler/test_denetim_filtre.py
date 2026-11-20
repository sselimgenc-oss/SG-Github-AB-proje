"""Denetim düzeltmeleri (2026-11-20): E1 CT MAX_POZ bekleyen girişleri sayar, E5 hesap dizin adı çakışması, B1 fren toplamı, B5 haber tonu kelime sınırı,
B6 bayat haber önbelleği. Kaynak: raporlar/denetim_testleri/ (kırmızı testler düzeltmeyle yeşil)."""
import json

import pandas as pd
import pytest

from motor.canli import aday_paper as ap
from motor.canli import alinsaydi_gevsetme as ag
from motor.canli import haber_etiketi as he

T0 = pd.Timestamp("2026-11-01T00:00:00Z")
SIMDI = pd.Timestamp("2026-11-20T00:00:00Z")


def _servis(tmp_path, islemler):
    """islemler: {neden: [R,...]}; her işlem için bir geçiş + 1 saat sonra açılan işlem (3 gün arayla). Nedenler aktif yapılır."""
    g = ag.AlinsaydiGevsetme(tmp_path, gonder=lambda m: None, saat=lambda: SIMDI, kapali_=False)
    isl, gec = {}, []
    for n, rs in islemler.items():
        g.durum["aktif"][n] = {"zaman": T0.isoformat(), "kanit": {}}
        k = ag._kh(n)
        for i, r in enumerate(rs):
            t = T0 + pd.Timedelta(days=3 * i + 1)
            gec.append({"neden": n, "k": k, "t": t.isoformat()})
            isl.setdefault(k, []).append((t + pd.Timedelta(hours=1), r))
    g.durum["gecisler"] = gec
    g._islemler = lambda: isl
    return g


# ---------------------------------------------------------------------------------------------- E1: CT MAX_POZ
ESL5 = {"ADA": ("ADAUSDT", 1.0), "BTC": ("BTCUSDT", 1.0), "ETH": ("ETHUSDT", 1.0), "SOL": ("SOLUSDT", 1.0), "XRP": ("XRPUSDT", 1.0)}


def test_E1_ct_max_poz_bekleyen_dolumlar_sayilir(monkeypatch):
    """Gerçek paper: aynı barda birimler sırayla işlenir; önceki barın henüz dolmamış girişleri de MAX_POZ'a sayılır (açık + bekleyen <= 3)."""
    import testler.test_ct_kadro as tk
    from motor.canli import ct_kadro as ck
    from testler.test_ct_kadro import coin, kapanis, ozet, paper_kur

    def genis(n=400, fiyat=100.0):
        idx = pd.date_range(tk.T0 - pd.Timedelta(minutes=15 * 100), periods=n, freq="15min", tz="UTC", name="zaman")
        return pd.DataFrame({"acilis": fiyat, "yuksek": fiyat * 1.02, "dusuk": fiyat * 0.98, "kapanis": fiyat, "hacim": 1000.0,
                             "quote_hacim": 1e5, "islem_sayisi": 10}, index=idx)
    monkeypatch.setattr(tk, "duz_mumlar", genis)
    s1 = ozet(kapanis(110), [coin("BTC", 8, 1, 5e6), coin("ETH", 8, 1, 4e6), coin("SOL", 8, 1, 3e6)])
    s2 = ozet(kapanis(111), [coin("BTC", 8, 1, 5e6), coin("ETH", 8, 1, 4e6), coin("SOL", 8, 1, 3e6), coin("ADA", 8, 1, 9e6), coin("XRP", 8, 1, 8e6)])
    p, _ = paper_kur(s1, s2, esl=ESL5)
    p.baslat(kapanis(105))
    p.adim(kapanis(114))
    acik = sorted(x.sembol for x in p.motor.acik.values())
    assert len(acik) <= ck.MAX_POZ, f"{len(acik)} açık pozisyon (MAX_POZ={ck.MAX_POZ}): {acik}"


# ---------------------------------------------------------------------------------------------- E5: hesap dizin adı çakışması
def test_E5_aday_hesap_dizinleri_cakisamaz(tmp_path):
    f = tmp_path / "liste.json"
    f.write_text(json.dumps([{"id": "swing__a:b__x", "kart_yolu": "k.json"}, {"id": "swing__a_b__x", "kart_yolu": "k.json"}]), encoding="utf-8")
    with pytest.raises(ap.AdayHatasi, match="aynı hesap dizin adına"):
        ap.liste_yukle(f)


def test_E5_cakismayan_kimlikler_yuklenir_ve_dizin_adi_degismez(tmp_path):
    f = tmp_path / "liste.json"
    f.write_text(json.dumps([{"id": "swing__a-b__x", "kart_yolu": "k.json"}, {"id": "swing__c__x", "kart_yolu": "k.json"}]), encoding="utf-8")
    assert len(ap.liste_yukle(f)) == 2
    from motor.canli.paper_v2 import hesap_dizin_adi
    assert hesap_dizin_adi("HAM:X005:664#v1") == "HAM_X005_664_v1" and hesap_dizin_adi("dis__x") == "dis__x"


# ---------------------------------------------------------------------------------------------- B1: fren toplamı geri alınanı saymaz
def test_B1_fren_toplami_geri_alinan_filtreyi_saymaz(tmp_path):
    g = _servis(tmp_path, {"etiket:rejim_karsiti": [-0.4] * 10,      # toplam -4.0 -> geri al
                           "etiket:takvim_olayi": [-0.15] * 10})     # toplam -1.5 -> kalır
    geri = g.izle(SIMDI)
    assert geri == ["etiket:rejim_karsiti"]
    assert "etiket:takvim_olayi" in g.aktif            # kalan aktif toplam -1.5 > -5: fren YOK, filtre aktif kalmalı
    assert not (g.durum["fren"] or {}).get("aktif")


# ---------------------------------------------------------------------------------------------- B5: haber tonu kelime sınırı
@pytest.mark.parametrize("baslik", ["Bank of America opens bitcoin trading desk", "Bitcoin issue tracker released by developers",
                                    "Enterprise firm unveils bitcoin custody", "Banner ad for bitcoin exchange"])
def test_B5_haber_tonu_kelime_sinirina_uyar(baslik):
    assert he.ton(baslik) == 0


@pytest.mark.parametrize("baslik,beklenen", [("SEC sues X over bitcoin", -1), ("SEC sued exchange", -1), ("Exchange banned in country", -1),
                                             ("Bitcoin price falls", -1), ("Exchange hacked", -1), ("Bitcoin surges to record", 1),
                                             ("ETF approved, bitcoin rising", 1), ("Bitcoin surged", 1), ("Market sell-off deepens", -1),
                                             ("Token delisted", -1), ("Bank ban lifted", -1)])
def test_B5_gercek_kelimeler_ve_ekler_hala_eslesir(baslik, beklenen):
    assert he.ton(baslik) == beklenen


def test_B5_issue_negatif_degil():
    assert he.ton("Issue resolved") == 0


# ---------------------------------------------------------------------------------------------- B6: bayat önbellek -> null
def test_B6_haber_bayat_onbellek_null():
    saat = [1_800_000_000.0]
    now = pd.Timestamp(saat[0], unit="s", tz="UTC")
    tarih = (now - pd.Timedelta(minutes=5)).strftime("%a, %d %b %Y %H:%M:%S +0000")
    xml = "<rss><channel>" + "".join(f"<item><title>Bitcoin crash hack</title><pubDate>{tarih}</pubDate></item>" for _ in range(3)) + "</channel></rss>"
    ok = [True]

    def http(url):
        if not ok[0]:
            raise OSError("ag yok")
        return xml.encode()
    h = he.HaberEtiketi(http=http, saat=lambda: saat[0], kaynaklar=("a",))
    assert h.etiket("BTCUSDT", now) == (-1.0, 3)
    ok[0] = False
    saat[0] += 3600                                          # 1 saat: önbellek hâlâ kullanılır (2 saat sınırı içinde)
    assert h._basliklar() is not None
    saat[0] += 9 * 3600                                      # 10 saattir veri yok: bayat -> null
    assert h._basliklar() is None
    assert h.etiket("BTCUSDT", pd.Timestamp(saat[0], unit="s", tz="UTC")) is None


# ---------------------------------------------------------------------------------------------- E4: bayat coin verisi -> yeni giriş yok
_BTC = {"coin": "BTC", "long_trader": 8, "short_trader": 1, "net_yon": "long", "nominal_long_usd": 1e6, "nominal_short_usd": 5e5, "net_nominal_usd": 5e5}


def test_E4_ct_bayat_coin_verisi_sinyal_yok_taze_sinyal_var():
    from motor.canli import ct_kadro as ck
    assert ck.sinyal_var({**_BTC, "veri_yasi_sn": 86400}) is None
    assert ck.sinyal_var({**_BTC, "veri_yasi_sn": ck.VERI_YASI_MAX_SN}) == 1           # tam eşik: serbest
    assert ck.sinyal_var({**_BTC, "veri_yasi_sn": ck.VERI_YASI_MAX_SN + 1}) is None
    assert ck.sinyal_var({**_BTC, "veri_yasi_sn": 30}) == 1


def test_E4_bayat_coin_acik_pozisyon_cikisi_etkilenmez():
    from motor.canli import ct_kadro as ck
    pl = ck.Plan(True, {}, {"BTCUSDT": ("long", {**_BTC, "veri_yasi_sn": 86400})})
    assert pl.cikis("BTCUSDT", 1) is False and pl.cikis("BTCUSDT", -1) is True       # çıkış mantığı veri yaşına bakmaz


# ---------------------------------------------------------------------------------------------- B2: fren asgari 5 işlem
@pytest.mark.parametrize("n,fren", [(4, False), (5, True)])
def test_B2_fren_asgari_ornek_5(tmp_path, n, fren):
    g = _servis(tmp_path, {"etiket:takvim_olayi": [-5.0 / n] * n})            # toplam tam -5R
    g.izle(SIMDI)
    assert bool((g.durum["fren"] or {}).get("aktif")) is fren
    assert ag.fren_gerekli(-5.0, 4) is False and ag.fren_gerekli(-5.0, 5) is True and ag.fren_gerekli(-4.9, 9) is False
