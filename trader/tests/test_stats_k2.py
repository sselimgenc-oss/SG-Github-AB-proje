"""K2 rastgele-giris simulasyonu: sentetik veri, bilinen durumlar."""
from __future__ import annotations

import math
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from trader_core.stats import adjust_pvalues  # noqa: E402
from trader_core.stats import k2_simulasyon as K  # noqa: E402


def test_p_degeri_formul_ve_nan():
    assert K.p_degeri(5.0, [1, 2, 3, 4]) == 1 / 5
    assert K.p_degeri(0.0, [1, 2, 3, 4]) == 1.0
    assert K.p_degeri(2.0, [2, 2, 1]) == (1 + 2) / 4          # esitlik sayilir
    assert math.isnan(K.p_degeri(math.nan, [1.0]))
    assert K.p_degeri(1.0, [math.nan, 0.0]) == 1 / 3


def test_ceyrek_sinirlari_ve_alt_sinir():
    gi = pd.to_datetime(["2026-02-15", "2026-05-02"], utc=True)
    b, e = K.ceyrek_sinirlari(gi)
    assert list(b) == list(pd.to_datetime(["2026-01-01", "2026-04-01"], utc=True))
    assert list(e) == list(pd.to_datetime(["2026-04-01", "2026-07-01"], utc=True))
    b2, _ = K.ceyrek_sinirlari(gi, alt_sinir="2026-05-01")
    assert b2[1] == pd.Timestamp("2026-05-01", tz="UTC") and b2[0] == pd.Timestamp("2026-05-01", tz="UTC")


def _mumlar(trend: float, n=400, seed=0):
    rng = np.random.default_rng(seed)
    c = 100 + np.cumsum(rng.normal(trend, 0.5, n))
    d = pd.date_range("2026-01-01", periods=n, freq="6h", tz="UTC")
    return pd.DataFrame({"date": d, "open": np.r_[c[0], c[:-1]], "high": c + 0.6, "low": c - 0.6, "close": c})


def _islemler(m, idx, yon=1):
    return pd.DataFrame({"giris_zamani": [m["date"].iat[i] for i in idx], "yon": yon, "stop_carpan": 2.0, "tutma": 10})


def test_tek_islem_r_stop_ve_zaman():
    n = 30
    o = np.full(n, 100.0); h = o + 1; l = o - 1; c = o.copy(); a = np.full(n, 1.0)
    m = K.K2Maliyet(0, 0, 0)
    l2 = l.copy(); l2[5] = 90          # stop (98) vurulur -> R = -1
    assert K.tek_islem_r(o, h, l2, c, a, 3, 1, 10, 2.0, m) == pytest.approx(-1.0)
    assert K.tek_islem_r(o, h, l, c, a, 3, 1, 10, 2.0, m) == pytest.approx(0.0)       # zaman cikisi, fiyat degismedi
    assert K.tek_islem_r(o, h, l, c, np.full(n, np.nan), 3, 1, 10, 2.0, m) is None


def test_simule_deterministik_ve_trend_pdegeri():
    m = _mumlar(0.0, seed=1)
    isl = _islemler(m, [50, 120, 200, 300])
    r1 = K.k2_simule(isl, m, 200, 11)
    r2 = K.k2_simule(isl, m, 200, 11)
    assert np.array_equal(r1["toplam_r"], r2["toplam_r"]) and r1["toplam_r"].shape == (200,)
    assert not np.array_equal(r1["toplam_r"], K.k2_simule(isl, m, 200, 12)["toplam_r"])
    # gercek T cok yuksekse p kucuk, cok dusukse p ~1
    assert K.p_degeri(100.0, r1["toplam_r"]) == pytest.approx(1 / 201)
    assert K.p_degeri(-100.0, r1["toplam_r"]) == 1.0


def test_iki_asama_gecis():
    sim = lambda n, t: np.random.default_rng(t).normal(0, 1, n)   # noqa: E731
    dusuk = K.k2_testi(-1.0, sim, 5)
    assert dusuk["asama"] == 1 and dusuk["B"] == 500 and dusuk["p"] > 0.5
    yuksek = K.k2_testi(50.0, sim, 5, b1=100, b2=300)
    assert yuksek["asama"] == 2 and yuksek["p"] == pytest.approx(1 / 301) and yuksek["p1"] == pytest.approx(1 / 101)


def test_bh_adjust_pvalues_ile_baglanti():
    p = {"a": 0.001, "b": 0.02, "c": 0.5, "d": math.nan}
    r = K.k2_duzelt(p, "bh", 0.10)
    ref = adjust_pvalues([0.001, 0.02, 0.5, 1.0], "bh")
    assert [r["p_duz"][k] for k in "abcd"] == pytest.approx(list(ref))
    assert r["kesif"] == ["a", "b"] and r["p_duz"]["d"] == 1.0


def test_eksik_sutun_hatasi():
    with pytest.raises(ValueError):
        K.k2_simule(pd.DataFrame({"yon": [1]}), _mumlar(0.0), 10, 1)
