"""Haber etiketi + haber_ters kuralı: sahte RSS, ağ YOK. Veri yok / hata -> null -> kural uygulanmaz."""
import pandas as pd
import pytest

from motor.canli import etiket_kurallari as ek
from motor.canli import haber_etiketi as he
from testler.test_kayit_etiketleri import kayit

T0 = pd.Timestamp("2026-11-19 12:00", tz="UTC")


def rss(*ogeler):
    """ogeler: (başlık, T0'dan kaç saat önce)."""
    x = "".join(f"<item><title>{b}</title><pubDate>{(T0 - pd.Timedelta(hours=h)).strftime('%a, %d %b %Y %H:%M:%S +0000')}</pubDate></item>" for b, h in ogeler)
    return f"<?xml version='1.0'?><rss><channel>{x}</channel></rss>".encode()


NEG2 = rss(("Bitcoin plunges as ETF outflow deepens", 2), ("BTC crash fears grow after hack", 5), ("Solana network upgrade approved", 3))


class Ag:
    def __init__(self, icerik=NEG2, hata=False):
        self.icerik, self.hata, self.cagri = icerik, hata, 0

    def __call__(self, url):
        self.cagri += 1
        if self.hata:
            raise OSError("ağ yok")
        return self.icerik


def mod(ag, t0=T0, **kw):
    sa = [t0.timestamp()]
    return he.HaberEtiketi(http=ag, saat=lambda: sa[0], kaynaklar=("u1",), **kw), sa


def test_ton_ve_eslesme():
    assert he.ton("Bitcoin surges to a record") == 1 and he.ton("Exchange hack, token plunges") == -1 and he.ton("Bitcoin holds steady") == 0
    assert he.eslesir("Bitcoin plunges", "BTC") and he.eslesir("BTC rally", "BTC") and not he.eslesir("Absolute rally", "SOL")   # SOL tam kelime
    assert he.eslesir("Solana upgrade", "SOL") and not he.eslesir("Solid quarter for banks", "SOL")
    assert he.temel_sembol("BTCUSDT") == "BTC" and he.temel_sembol("1000PEPEUSDT") == "PEPE" and he.temel_sembol("DK_AAPL") is None


def test_etiket_ton_ve_sayi_hisse_null_ve_baska_coin():
    m, _ = mod(Ag())
    assert m.etiket("BTCUSDT", T0) == (-1.0, 2)                 # iki başlık da negatif
    assert m.etiket("SOLUSDT", T0) == (1.0, 1)
    assert m.etiket("XRPUSDT", T0) == (None, 0)                 # eşleşen başlık yok
    assert m.etiket("DK_AAPL", T0) is None                      # hisse: eşleme yok -> null


def test_lookahead_ve_pencere_ve_gecmis_oynatma():
    m, _ = mod(Ag(rss(("Bitcoin rally", 30), ("Bitcoin crash", 1))))
    assert m.etiket("BTCUSDT", T0) == (-1.0, 1)                 # 30 saat önceki başlık pencere dışı
    assert m.etiket("BTCUSDT", T0 - pd.Timedelta(hours=1, minutes=30)) == (None, 0)   # karar anı 1.5 saat önce: sonraki başlık görülmez
    assert m.etiket("BTCUSDT", T0 - pd.Timedelta(days=3)) is None                     # geçmiş oynatma: null


def test_onbellek_15_dk_ve_hata_null():
    ag = Ag()
    m, sa = mod(ag)
    m.etiket("BTCUSDT", T0)
    sa[0] += 14 * 60
    m.etiket("BTCUSDT", pd.Timestamp(sa[0], unit="s", tz="UTC"))
    assert ag.cagri == 1
    sa[0] += 2 * 60
    m.etiket("BTCUSDT", pd.Timestamp(sa[0], unit="s", tz="UTC"))
    assert ag.cagri == 2
    bos, _ = mod(Ag(hata=True))
    assert bos.etiket("BTCUSDT", T0) is None and bos.etiket("ETHUSDT", T0) is None
    assert bos.http.cagri == 1                                   # hata sonrası 15 dk yeniden denenmez
    assert he.rss_coz(b"<!DOCTYPE x [<!ENTITY a 'b'>]><rss/>", T0) == [] and he.rss_coz(b"bozuk", T0) == []


def test_kayit_etiketlerine_eklenir_ve_hata_null(tmp_path):
    m, _ = mod(Ag())
    k = kayit(tmp_path, haber_fn=m.etiket)
    e = k.etiketler("BTCUSDT", T0)
    assert e["haber_tonu"] == -1.0 and e["haber_sayisi"] == 2
    e2 = k.etiketler("DK_AAPL", T0)
    assert e2["haber_tonu"] is None and e2["haber_sayisi"] is None
    patlak = kayit(tmp_path, haber_fn=lambda s, t: 1 / 0)
    e3 = patlak.etiketler("BTCUSDT", T0)
    assert e3["haber_tonu"] is None and e3["haber_sayisi"] is None
    assert "haber_tonu" not in kayit(tmp_path).etiketler("BTCUSDT", T0)         # bağlı değilse alan yok


@pytest.mark.parametrize("yon,ton,sayi,beklenen", [
    ("long", -0.5, 2, "etiket:haber_ters"), ("long", -0.2, 2, None), ("long", -0.21, 2, "etiket:haber_ters"), ("long", -0.5, 1, None),
    ("long", 0.9, 5, None), ("short", 0.5, 2, "etiket:haber_ters"), ("short", 0.2, 3, None), ("short", -0.9, 4, None),
    ("long", None, None, None), ("long", None, 0, None), ("long", -1.0, None, None),
])
def test_haber_ters_kurali(yon, ton, sayi, beklenen):
    assert ek.degerlendir(yon, {"haber_tonu": ton, "haber_sayisi": sayi}) == beklenen
    assert (ek.HABER_ESIK, ek.HABER_MIN_SAYI) == (0.2, 2)
