"""Denetim E: CT konsensus MAX_POZ (en çok 3 açık pozisyon) gerçek paper motoruyla.
Plan, aynı bar satırındaki henüz dolmamış (bekleyen) girişleri açık sayar mı? Birim satırları sırayla işlenir: ilk birim planı
hesaplarken sonraki birimlerin bekleyen girişi `motor.acik`'ta yoktur."""
import testler.test_ct_kadro as tk
from testler.test_ct_kadro import ck, coin, kapanis, ozet, paper_kur

ESL5 = {"ADA": ("ADAUSDT", 1.0), "BTC": ("BTCUSDT", 1.0), "ETH": ("ETHUSDT", 1.0), "SOL": ("SOLUSDT", 1.0), "XRP": ("XRPUSDT", 1.0)}


def _kur(monkeypatch):
    def genis(n=400, fiyat=100.0):                       # ATR ~%4: stop uzak, nominal küçük (brüt kaldıraç tavanı devreye girmez)
        import pandas as pd
        idx = pd.date_range(tk.T0 - pd.Timedelta(minutes=15 * 100), periods=n, freq="15min", tz="UTC", name="zaman")
        return pd.DataFrame({"acilis": fiyat, "yuksek": fiyat * 1.02, "dusuk": fiyat * 0.98, "kapanis": fiyat, "hacim": 1000.0,
                             "quote_hacim": 1e5, "islem_sayisi": 10}, index=idx)
    monkeypatch.setattr(tk, "duz_mumlar", genis)
    s1 = ozet(kapanis(110), [coin("BTC", 8, 1, 5e6), coin("ETH", 8, 1, 4e6), coin("SOL", 8, 1, 3e6)])
    s2 = ozet(kapanis(111), [coin("BTC", 8, 1, 5e6), coin("ETH", 8, 1, 4e6), coin("SOL", 8, 1, 3e6),
                             coin("ADA", 8, 1, 9e6), coin("XRP", 8, 1, 8e6)])
    return paper_kur(s1, s2, esl=ESL5)


def test_max_poz_bekleyen_dolumlar_sayilir(monkeypatch):
    p, d = _kur(monkeypatch)
    p.baslat(kapanis(105))
    p.adim(kapanis(114))
    acik = sorted(x.sembol for x in p.motor.acik.values())
    assert len(acik) <= ck.MAX_POZ, f"{len(acik)} açık pozisyon (MAX_POZ={ck.MAX_POZ}): {acik}"
