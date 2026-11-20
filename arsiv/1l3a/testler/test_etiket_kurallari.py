"""Etiket kuralları (ön kayıt): rejim_karsiti / takvim_olayi / kalabalik yalnız girişi atlatır; OI etiketi lookahead'siz, hata -> null. Ağ yok (sahte)."""
import json
from pathlib import Path

import pandas as pd
import pytest

from motor.canli import etiket_kurallari as ek
from motor.canli import kayit_etiketleri as ke
from motor.canli import oi_istemci as oi
from motor.canli import ogrenme_adaptor as oa
from testler.test_kayit_etiketleri import _paper, kayit, satirlar

T0 = pd.Timestamp("2025-03-10 12:00", tz="UTC")
BOS = {"fonlama_orani": None, "oi_usd": None, "oi_degisim_24s": None, "korku_acgozluluk": 50, "takvim_bayragi": None,
       "rejim_ml_4h": None, "rejim_ml_1d": None}


def et(**kw):
    return {**BOS, **kw}


# ---------------------------------------------------------------------------- kural sınırları
def test_rejim_yon_eslesmesi_ve_1d_oncelik_4h_yedek():
    assert ek.degerlendir("long", et(rejim_ml_1d="trend_down")) == "etiket:rejim_karsiti"
    assert ek.degerlendir("short", et(rejim_ml_1d="trend_up")) == "etiket:rejim_karsiti"
    assert ek.degerlendir("long", et(rejim_ml_1d="trend_up")) is None
    assert ek.degerlendir("short", et(rejim_ml_1d="trend_down")) is None
    assert ek.degerlendir("long", et(rejim_ml_1d="range")) is None
    assert ek.degerlendir("long", et(rejim_ml_4h="trend_down")) == "etiket:rejim_karsiti"     # 1d yok -> 4h
    assert ek.degerlendir("long", et(rejim_ml_1d="trend_up", rejim_ml_4h="trend_down")) is None  # 1d varsa 4h bakılmaz


def test_takvim_kurali():
    assert ek.degerlendir("long", et(takvim_bayragi="FOMC")) == "etiket:takvim_olayi"
    assert ek.degerlendir("short", et(takvim_bayragi="FOMC")) == "etiket:takvim_olayi"
    assert ek.degerlendir("long", et(takvim_bayragi=None)) is None


@pytest.mark.parametrize("yon,f,oi_d,beklenen", [
    ("long", 0.0005, 0.10, "etiket:kalabalik"),                 # eşit -> atla
    ("long", 0.0006, 0.50, "etiket:kalabalik"),
    ("long", 0.00049, 0.10, None),                              # fonlama altında
    ("long", 0.0005, 0.0999, None),                             # OI altında
    ("long", -0.0005, 0.50, None),                              # long'da negatif fonlama kalabalık değil
    ("short", -0.0005, 0.10, "etiket:kalabalik"),
    ("short", -0.00049, 0.10, None),
    ("short", -0.0005, 0.0999, None),
    ("short", 0.0005, 0.50, None),
])
def test_kalabalik_sinirlari(yon, f, oi_d, beklenen):
    assert ek.degerlendir(yon, et(fonlama_orani=f, oi_degisim_24s=oi_d)) == beklenen


def test_null_etiket_kural_uygulamaz():
    assert ek.degerlendir("long", None) is None and ek.degerlendir("long", {}) is None
    assert ek.degerlendir("long", et(fonlama_orani=0.01, oi_degisim_24s=None)) is None
    assert ek.degerlendir("long", et(fonlama_orani=None, oi_degisim_24s=0.9)) is None
    assert ek.degerlendir("long", et()) is None


def test_korku_acgozluluk_kurali():
    assert ek.degerlendir("long", et(korku_acgozluluk=75)) == "etiket:korku_acgozluluk"
    assert ek.degerlendir("long", et(korku_acgozluluk=100)) == "etiket:korku_acgozluluk"
    assert ek.degerlendir("long", et(korku_acgozluluk=74)) is None
    assert ek.degerlendir("short", et(korku_acgozluluk=25)) == "etiket:korku_acgozluluk"
    assert ek.degerlendir("short", et(korku_acgozluluk=0)) == "etiket:korku_acgozluluk"
    assert ek.degerlendir("short", et(korku_acgozluluk=26)) is None
    assert ek.degerlendir("short", et(korku_acgozluluk=95)) is None      # aşırı açgözlülükte short serbest
    assert ek.degerlendir("long", et(korku_acgozluluk=5)) is None        # aşırı korkuda long serbest
    assert ek.degerlendir("long", et(korku_acgozluluk=None)) is None     # veri yok = engel yok


# ---------------------------------------------------------------------------- motora bağlı
def _bagli(tmp_path, etiket, bagla=True):
    p, mum, bas = _paper(tmp_path)
    if etiket is not None:
        p.kayit.etiketler = lambda *a, **k: dict(etiket)
    if bagla:
        assert ek.bagla(p, env={})
    return p, mum


def _kos(p, mum):
    p.adim(mum[("XUSDT", "1d")].index[8])
    return p


def _durum(p):
    m = p.motor
    return ([(k, str(x.miktar), str(x.stop), str(x.giris)) for k, x in sorted(m.acik.items())], str(m.ozsermaye()), len(m.islemler))


def test_atlanan_giris_nedeniyle_kayda_yazilir(tmp_path):
    for ad, e, neden in [("a", et(rejim_ml_1d="trend_down"), "etiket:rejim_karsiti"), ("b", et(takvim_bayragi="CPI"), "etiket:takvim_olayi"),
                         ("c", et(fonlama_orani=0.001, oi_degisim_24s=0.2), "etiket:kalabalik")]:
        d = tmp_path / ad
        p, mum = _bagli(d, e)
        _kos(p, mum)
        assert not p.motor.acik and not p.motor.islemler
        assert neden in [s["neden"] for s in satirlar(d)]


def test_kurallar_boyutu_degistirmez_izinli_ile_kapali_ayni(tmp_path):
    p0, m0 = _bagli(tmp_path / "0", None, bagla=False)                       # kanca yok
    p1, m1 = _bagli(tmp_path / "1", et(rejim_ml_1d="trend_up"))              # long + trend_up: izinli
    p2, m2 = _bagli(tmp_path / "2", et(fonlama_orani=0.001, oi_degisim_24s=0.05))   # OI altında: izinli
    d0, d1, d2 = (_durum(_kos(p, m)) for p, m in ((p0, m0), (p1, m1), (p2, m2)))
    assert d0[0] and d0 == d1 == d2


def test_ml_ders_ile_zincir_biri_reddederse_atlar(tmp_path):
    p, mum = _bagli(tmp_path / "x", et())                                    # etiket izinli
    p.motor.giris_suzgeci = lambda *a: (False, "ml_filtre")                  # ML/ders reddeder
    _kos(p, mum)
    assert not p.motor.acik and "ml_filtre" in [s["neden"] for s in satirlar(tmp_path / "x")]
    p, mum = _bagli(tmp_path / "y", et(takvim_bayragi="FOMC"))
    p.motor.giris_suzgeci = lambda *a: (True, "")                            # ML izinli, etiket reddeder
    _kos(p, mum)
    assert not p.motor.acik and "etiket:takvim_olayi" in [s["neden"] for s in satirlar(tmp_path / "y")]


def test_kanca_hatasi_giris_serbest(tmp_path, caplog):
    p0, m0 = _bagli(tmp_path / "0", None, bagla=False)
    p1, m1 = _bagli(tmp_path / "1", et(), bagla=False)
    p1.motor.etiket_suzgeci = lambda *a: 1 / 0
    d0, d1 = _durum(_kos(p0, m0)), _durum(_kos(p1, m1))
    assert d0[0] and d0 == d1
    assert any("etiket süzgeci hatası" in r.message for r in caplog.records)


def test_etiket_uretimi_hatasi_giris_serbest(tmp_path):
    p, mum = _bagli(tmp_path / "e", et())
    p.kayit.etiketler = lambda *a, **k: 1 / 0
    p.motor.etiket_kancasi = None
    _kos(p, mum)
    assert p.motor.acik


def test_kapatma_bayragi(tmp_path):
    p, mum, _ = _paper(tmp_path)
    p.kayit.etiketler = lambda *a, **k: et(takvim_bayragi="FOMC")
    assert ek.bagla(p, env={"L3A_ETIKET_KURAL_KAPALI": "1"}) is False
    assert p.motor.etiket_suzgeci is None
    _kos(p, mum)
    assert p.motor.acik


def test_kayitsiz_hesapta_kural_yok(tmp_path):
    p, mum, _ = _paper(tmp_path, kay=False)
    ek.bagla(p, env={})
    _kos(p, mum)
    assert p.motor.acik


def test_ogrenme_ve_etiket_kancalari_birbirini_ezmez(tmp_path):
    p, mum, _ = _paper(tmp_path)
    p.kayit.etiketler = lambda *a, **k: et(takvim_bayragi="FOMC")
    og = oa.Ogrenme(tmp_path, saat=lambda: pd.Timestamp("2026-01-01", tz="UTC"), gonder=lambda m: True)
    og.bagla(p)
    ek.bagla(p, env={})
    _kos(p, mum)
    assert not p.motor.acik and p.motor.giris_suzgeci is not None and p.motor.etiket_suzgeci is not None
    assert "etiket:takvim_olayi" in [s["neden"] for s in satirlar(tmp_path)]


# ---------------------------------------------------------------------------- OI etiketi
class Yanit:
    def __init__(self, kod=200, veri=None, baslik=None):
        self.status_code, self._v, self.headers = kod, veri, baslik or {}

    def json(self):
        return self._v


def oi_satirlari(bitis, n=30, baz=1000.0, adim=10.0):
    """bitis: son damga; saatlik n satır; değer baz + adim*i (en eski i=0)."""
    return [{"timestamp": int((bitis - pd.Timedelta(hours=n - 1 - i)).timestamp() * 1000), "sumOpenInterest": "1",
             "sumOpenInterestValue": str(baz + adim * i)} for i in range(n)]


class Oturum:
    def __init__(self, yanit):
        self.yanit, self.cagri = yanit, []

    def get(self, url, params=None, timeout=None):
        self.cagri.append((url, params, timeout))
        if isinstance(self.yanit, Exception):
            raise self.yanit
        return self.yanit


def test_oi_lookahead_yok_ve_24s_degisim():
    son = pd.Timestamp("2025-03-10 11:00", tz="UTC")                 # son satır damgası 11:00
    o = Oturum(Yanit(veri=oi_satirlari(son)))
    ist = oi.OiIstemci(oturum=o, saat=lambda: 1.0)
    # karar 12:00: 11:00 damgalı satır (damga+1sa <= 12:00) kapanmış sayılır
    usd, deg = ist("BTCUSDT", pd.Timestamp("2025-03-10 12:00", tz="UTC"))
    assert usd == 1000.0 + 10 * 29 and deg == pytest.approx((1000 + 290) / (1000 + 10 * 5) - 1)
    # karar 11:30: 11:00 satırı henüz KAPANMAMIŞ -> bir önceki (10:00)
    usd2, _ = ist("BTCUSDT", pd.Timestamp("2025-03-10 11:30", tz="UTC"))
    assert usd2 == 1000.0 + 10 * 28
    # karar 10:59:59: 10:00 satırı da kapanmamış -> 09:00
    usd3, _ = ist("BTCUSDT", pd.Timestamp("2025-03-10 10:59:59", tz="UTC"))
    assert usd3 == 1000.0 + 10 * 27
    assert len(o.cagri) == 1 and o.cagri[0][2] == oi.ZAMAN_ASIMI_SN == 5.0       # önbellek: tek istek, 5 sn zaman aşımı


def test_oi_onbellek_15dk_sonra_yenilenir():
    son = pd.Timestamp("2025-03-10 11:00", tz="UTC")
    zaman = [100.0]
    o = Oturum(Yanit(veri=oi_satirlari(son)))
    ist = oi.OiIstemci(oturum=o, saat=lambda: zaman[0])
    t = pd.Timestamp("2025-03-10 12:00", tz="UTC")
    ist("BTCUSDT", t)
    zaman[0] += 899
    ist("BTCUSDT", t)
    assert len(o.cagri) == 1
    zaman[0] += 2
    ist("BTCUSDT", t)
    assert len(o.cagri) == 2


def test_oi_gunluk_veri_eksikse_degisim_null_ve_eski_veri_null():
    son = pd.Timestamp("2025-03-10 11:00", tz="UTC")
    ist = oi.OiIstemci(oturum=Oturum(Yanit(veri=oi_satirlari(son, n=10))), saat=lambda: 1.0)       # 24 saat önceki satır yok
    usd, deg = ist("BTCUSDT", pd.Timestamp("2025-03-10 12:00", tz="UTC"))
    assert usd is not None and deg is None
    assert ist("BTCUSDT", pd.Timestamp("2025-03-10 16:00", tz="UTC")) is None                     # son kapanmış değer >3 saat eski


@pytest.mark.parametrize("yanit", [Yanit(500), Yanit(418, baslik={"Retry-After": "60"}), Yanit(429), Yanit(200, veri={"bozuk": 1}), TimeoutError("x")])
def test_oi_ag_hatasi_null_ve_bekleme(yanit):
    o = Oturum(yanit)
    zaman = [1000.0]
    ist = oi.OiIstemci(oturum=o, saat=lambda: zaman[0])
    t = pd.Timestamp("2025-03-10 12:00", tz="UTC")
    assert ist("BTCUSDT", t) is None
    assert ist("ETHUSDT", t) is None and len(o.cagri) == 1        # hata sonrası bekleme: motor her kararda 5 sn beklemez


def test_oi_agirlik_esigi_asilirsa_istek_yok():
    son = pd.Timestamp("2025-03-10 11:00", tz="UTC")
    o = Oturum(Yanit(veri=oi_satirlari(son), baslik={"X-MBX-USED-WEIGHT-1M": "1900"}))
    ist = oi.OiIstemci(oturum=o, saat=lambda: 1.0)
    t = pd.Timestamp("2025-03-10 12:00", tz="UTC")
    assert ist("BTCUSDT", t) is not None
    assert ist("ETHUSDT", t) is None and len(o.cagri) == 1


def test_kayit_oi_alanlari_yalniz_kripto_ve_hata_null(tmp_path):
    cagri = []
    k = kayit(tmp_path, oi_fn=lambda s, t: (cagri.append((s, t)) or (5.0e9, 0.12)))
    e = k.etiketler("XUSDT", T0)
    assert e["oi_usd"] == 5.0e9 and e["oi_degisim_24s"] == 0.12 and cagri[0][1] == T0
    assert k.etiketler("DK_AAPL", T0)["oi_usd"] is None and len(cagri) == 1       # hisse: OI yok
    k2 = kayit(tmp_path, oi_fn=lambda s, t: 1 / 0)
    e2 = k2.etiketler("XUSDT", T0)
    assert e2["oi_usd"] is None and e2["oi_degisim_24s"] is None
    e3 = kayit(tmp_path).etiketler("XUSDT", T0)                                   # istemci bağlı değil
    assert e3["oi_usd"] is None and e3["oi_degisim_24s"] is None


def test_oi_alanlari_alinmayan_sinyal_satirinda(tmp_path):
    from motor.backtest.motor import SembolKurallari
    p, mum, _ = _paper(tmp_path, min_notional=1e9)
    p.kayit.oi_fn = lambda s, t: (7.0, 0.3)
    _kos(p, mum)
    s = satirlar(tmp_path)
    assert s and s[0]["oi_usd"] == 7.0 and s[0]["oi_degisim_24s"] == 0.3
