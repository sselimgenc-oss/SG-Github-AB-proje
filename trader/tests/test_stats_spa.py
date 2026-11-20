"""Hansen SPA: bilinen kucuk durumlar (sentetik, sabit tohum)."""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from trader_core.stats.spa import hansen_spa  # noqa: E402


def _x(seed, n, mu, sd=1.0):
    return np.random.default_rng(seed).normal(mu, sd, n)


def test_guclu_sinyal_nulu_reddeder():
    r = hansen_spa({"iyi": _x(1, 500, 0.5), "gurultu": _x(2, 500, 0.0)}, n_boot=1000, mean_block=5, seed=7)
    assert r["p"] < 0.01 and r["en_iyi"] == "iyi" and r["T"] > 3
    assert r["p_alt"] <= r["p"] + 1e-12 <= r["p_ust"] + 1e-9            # alt <= tutarli <= ust


def test_saf_gurultu_reddedilmez():
    ps = [hansen_spa({f"m{k}": _x(100 * s + k, 300, 0.0) for k in range(5)}, n_boot=500, mean_block=5, seed=s)["p_ust"] for s in range(20)]
    assert np.mean(np.array(ps) < 0.05) <= 0.15                          # ~%5 beklenir; kucuk orneklem payi
    assert 0.2 < np.mean(ps) < 0.9


def test_hepsi_negatifse_p_bir():
    r = hansen_spa({"a": _x(3, 400, -0.5), "b": _x(4, 400, -0.4)}, n_boot=500, mean_block=5, seed=1)
    assert r["T"] == 0.0 and r["p"] == 1.0 and r["p_ust"] == 1.0


def test_kotu_model_eklemek_tutarli_p_yi_sisirmez_ama_ust_sisirir():
    iyi = {"iyi": _x(1, 400, 0.15)}
    kotu = {**iyi, **{f"k{i}": _x(50 + i, 400, -0.6) for i in range(30)}}
    a, b = hansen_spa(iyi, n_boot=800, mean_block=5, seed=2), hansen_spa(kotu, n_boot=800, mean_block=5, seed=2)
    assert b["p"] <= a["p"] + 0.05            # tutarli: asiri kotu modeller dislanir
    assert b["p_ust"] >= b["p"]


def test_sabit_seri_sayilir_tohum_deterministik():
    s = {"sifir": np.zeros(100), "x": _x(5, 100, 0.0)}
    r1, r2 = hansen_spa(s, seed=3), hansen_spa(s, seed=3)
    assert r1 == r2 and r1["n_sabit"] == 1 and r1["en_iyi"] == "x"
    assert hansen_spa({"s": np.zeros(50)})["p"] == 1.0


def test_benchmark_ve_dizi_girisi_ve_hatalar():
    x = _x(6, 300, 0.3)
    assert hansen_spa(x, benchmark=x, n_boot=200)["p"] == 1.0            # d = 0
    assert hansen_spa(np.column_stack([x, x * 0.5]), n_boot=200, seed=1)["n_model"] == 2
    with pytest.raises(ValueError):
        hansen_spa(np.array([1.0, 2.0]))
    with pytest.raises(ValueError):
        hansen_spa(np.array([1.0, np.nan, 2.0, 3.0]))
