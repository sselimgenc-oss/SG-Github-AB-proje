"""A: bir serinin geçici veri hatası diğer serileri engellemez. B: sonsuz_dene programlama hatasını geçici saymaz."""
import pandas as pd
import pytest

from motor.canli import paper as pp
from motor.canli import paper_canli as pc
from motor.canli import paper_veri as pv
from testler.test_paper_canli import SahteIstemci
from testler.test_paper_motor import sentetik


class Iki(SahteIstemci):
    def __init__(self, seri, bozuk=None, hata=None):
        super().__init__(seri)
        self.bozuk, self.hata, self.ac = bozuk, hata, False

    def klines(self, sembol, aralik, bas=None, bit=None, simdi=None):
        if sembol == self.bozuk and self.hata is not None and self.ac:
            raise self.hata
        return super().klines(sembol, aralik, bas, bit, simdi)


class FakeTan:
    def __init__(self, tf, semboller):
        self.tf, self.veri_semboller = tf, semboller


def _kaynak(hata, olaylar):
    a, b = sentetik(60, "1d", 1), sentetik(60, "1d", 2)
    ist = Iki({("AAAUSDT", "1d"): a, ("BBBUSDT", "1d"): b}, bozuk="AAAUSDT", hata=hata)
    k = pc.CanliKaynak(ist, [FakeTan("1d", ["AAAUSDT", "BBBUSDT"])], {"1d": 30}, None, lambda t, m: olaylar.append(t))
    t0 = a.index[40] + pd.Timedelta(days=1, seconds=10)
    k.baslat(t0)
    ist.ac = True
    return k, t0


def test_a_gecici_hata_diger_seriyi_engellemez():
    olay = []
    k, t0 = _kaynak(pv.BinanceHata("503"), olay)
    onceki = k.mumlar[("BBBUSDT", "1d")].index[-1]
    n = k.guncelle(t0 + pd.Timedelta(days=3))       # AAA hatalı (sıralamada önce), BBB yine de güncellenir
    assert n >= 1 and k.mumlar[("BBBUSDT", "1d")].index[-1] > onceki
    assert olay.count("veri_cekme_hatasi") == 1
    k.guncelle(t0 + pd.Timedelta(days=3, minutes=1))
    assert olay.count("veri_cekme_hatasi") == 1      # olay saatte en çok bir


def test_a_genel_kesinti_yukselir():
    k, t0 = _kaynak(pv.BinanceHata("503"), [])
    k.seriler = [("AAAUSDT", "1d")]
    with pytest.raises(pv.BinanceHata):
        k.guncelle(t0 + pd.Timedelta(days=3))


def test_a_kod_hatasi_izole_edilmez():
    k, t0 = _kaynak(TypeError("bug"), [])
    with pytest.raises(TypeError):
        k.guncelle(t0 + pd.Timedelta(days=3))


def test_b_kod_hatasi_gecici_sayilmaz():
    uyk, bild = [], []

    def f():
        raise AttributeError("x")
    with pytest.raises(AttributeError):
        pp.sonsuz_dene(f, "x", uyku=uyk.append, bildir=bild.append)
    assert len(uyk) == pp.KOD_HATASI_SINIRI - 1 and len(bild) == pp.KOD_HATASI_SINIRI - 1


def test_b_ag_hatasi_gecici_kalir_ve_kod_sayaci_sifirlanir():
    n = [0]

    def f():
        n[0] += 1
        if n[0] in (1, 3):
            raise TypeError("t")
        if n[0] < 8:
            raise OSError("ag")
        return 1
    assert pp.sonsuz_dene(f, "x", uyku=lambda s: None) == 1
