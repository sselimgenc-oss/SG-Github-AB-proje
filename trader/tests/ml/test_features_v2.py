"""ML-G4: ozellik uretici v2 (r02/r03) -- kati nedensellik, sutun listeleri, yon isareti, aralik kontrolleri.
Yalniz sentetik veri (2024 zaman damgalari)."""
import numpy as np
import pandas as pd
import pytest

from trader_core.ml_features import BAR, BTC, ETH, MAX_FEATURES
from trader_core.ml_features_v2 import (R02_FEATURE_NAMES, R03_FEATURE_NAMES, efficiency_ratio, feature_frame_v2,
                                         variance_ratio)

PAIRS = [BTC, ETH, "SOL/USDT:USDT", "BNB/USDT:USDT", "XRP/USDT:USDT"]
N = 2000


def _make(seed=3):
    rng = np.random.default_rng(seed)
    idx = pd.date_range("2024-03-01", periods=N, freq="1h", tz="UTC")
    common = rng.normal(0, 0.004, N)
    out = {}
    for i, p in enumerate(PAIRS):
        r = common * (1 + 0.1 * i) + rng.normal(0.00002 * i, 0.006, N)
        c = 100 * (i + 1) * np.exp(np.cumsum(r))
        o = np.concatenate([[c[0]], c[:-1]])
        h = np.maximum(o, c) * (1 + np.abs(rng.normal(0, 0.003, N)))
        l = np.minimum(o, c) * (1 - np.abs(rng.normal(0, 0.003, N)))
        out[p] = pd.DataFrame({"open": o, "high": h, "low": l, "close": c, "volume": rng.uniform(50, 150, N)}, index=idx)
    return out


def _funding(seed=4):
    rng = np.random.default_rng(seed)
    t = pd.date_range("2024-03-01", periods=N // 8, freq="8h", tz="UTC")
    return {p: pd.DataFrame({"rate": rng.normal(0.0001, 0.0003, len(t))}, index=t) for p in PAIRS}


def _cands():
    rng = np.random.default_rng(9)
    pos = [1300, 1301, 1500, 1500, 1730, 1731, 1900, 1990]
    ts = [pd.Timestamp("2024-03-01", tz="UTC") + (k + 1) * BAR for k in pos]   # kapanis zamani
    pr = [PAIRS[rng.integers(0, len(PAIRS))] for _ in pos]
    pr[2], pr[3] = PAIRS[2], PAIRS[3]
    return pd.DataFrame({"ts": ts, "pair": pr, "side": ["long", "short"] * 4}, index=range(10, 18))


@pytest.fixture(scope="module")
def data():
    return _make(), _funding(), _cands()


@pytest.fixture(scope="module")
def full(data):
    pairs, fund, cands = data
    return {r: feature_frame_v2(pairs, cands, funding=fund, recipe=r) for r in ("r02", "r03")}


def test_columns_and_count(full, data):
    assert len(R02_FEATURE_NAMES) <= MAX_FEATURES and len(R03_FEATURE_NAMES) == 8
    assert len(set(R02_FEATURE_NAMES)) == len(R02_FEATURE_NAMES)
    assert list(full["r02"].columns) == R02_FEATURE_NAMES and list(full["r03"].columns) == R03_FEATURE_NAMES
    assert full["r02"].index.equals(data[2].index)
    for f in full.values():
        assert len(f) == len(data[2])


def test_bad_recipe_and_missing_btc(data):
    pairs, _, cands = data
    with pytest.raises(ValueError):
        feature_frame_v2(pairs, cands, recipe="r99")
    with pytest.raises(ValueError):
        feature_frame_v2({k: v for k, v in pairs.items() if k != ETH}, cands, recipe="r03")


def test_features_mostly_finite(full):
    f = full["r02"].drop(columns=["f_stop_dist_atr"])     # stop_dist_atr yalniz v1 sinyal mumlarinda dolu
    assert f.notna().all().all()
    assert full["r03"].notna().all().all()
    assert np.isfinite(full["r02"].to_numpy(float)[~np.isnan(full["r02"].to_numpy(float))]).all()


def _truncate(pairs, fund, ts):
    p = {k: v[v.index + BAR <= ts] for k, v in pairs.items()}
    f = {k: v[v.index <= ts] for k, v in fund.items()}
    return p, f


@pytest.mark.parametrize("recipe", ["r02", "r03"])
def test_truncation_identical_every_feature(data, full, recipe):
    pairs, fund, cands = data
    for ts in cands["ts"].unique():
        sub = cands[cands["ts"] == ts]
        p, f = _truncate(pairs, fund, ts)
        got = feature_frame_v2(p, sub, funding=f, recipe=recipe)
        pd.testing.assert_frame_equal(got, full[recipe].loc[sub.index], check_exact=False, rtol=1e-9, atol=1e-12)


@pytest.mark.parametrize("recipe", ["r02", "r03"])
def test_perturbing_future_bars_never_changes_features(data, full, recipe):
    pairs, fund, cands = data
    rng = np.random.default_rng(11)
    for ts in list(cands["ts"].unique())[::2]:
        p = {k: v.copy() for k, v in pairs.items()}
        f = {k: v.copy() for k, v in fund.items()}
        for k, v in p.items():
            m = np.asarray(v.index + BAR > ts)
            for col in ("open", "high", "low", "close", "volume"):
                v.loc[m, col] = v.loc[m, col].to_numpy() * rng.uniform(0.5, 2.0, m.sum())
        for k, v in f.items():
            v.loc[v.index > ts, "rate"] = 9.9
        sub = cands[cands["ts"] == ts]
        got = feature_frame_v2(p, sub, funding=f, recipe=recipe)
        pd.testing.assert_frame_equal(got, full[recipe].loc[sub.index], check_exact=False, rtol=1e-9, atol=1e-12)


def test_side_signing(data):
    pairs, fund, cands = data
    flip = cands.copy()
    flip["side"] = flip["side"].map({"long": "short", "short": "long"})
    a = feature_frame_v2(pairs, cands, funding=fund, recipe="r02")
    b = feature_frame_v2(pairs, flip, funding=fund, recipe="r02")
    for c in ("f_side_sign", "f_slope_4h_aligned", "f_funding_last", "f_funding_sum3"):
        np.testing.assert_allclose(a[c], -b[c], atol=1e-15)
    np.testing.assert_allclose(a["f_rank_ret_24h"], 1 - b["f_rank_ret_24h"], atol=1e-12)
    np.testing.assert_allclose(a["f_rank_ret_7d"], 1 - b["f_rank_ret_7d"], atol=1e-12)
    pd.testing.assert_series_equal(a["f_slope_4h"], b["f_slope_4h"])
    r3a = feature_frame_v2(pairs, cands, recipe="r03")
    r3b = feature_frame_v2(pairs, flip, recipe="r03")
    np.testing.assert_allclose(r3a["f_side_x_btc_slope_1d"], -r3b["f_side_x_btc_slope_1d"], atol=1e-15)
    np.testing.assert_allclose(r3a["f_side_x_btc_slope_1d"],
                               a["f_side_sign"] * r3a["f_btc_slope_1d"], atol=1e-15)


def test_funding_values_and_nan_when_absent(data, full):
    pairs, fund, cands = data
    nof = feature_frame_v2(pairs, cands, recipe="r02")
    assert nof["f_funding_last"].isna().all() and nof["f_funding_sum3"].isna().all()
    assert nof.drop(columns=["f_funding_last", "f_funding_sum3"]).equals(
        full["r02"].drop(columns=["f_funding_last", "f_funding_sum3"]))
    row = cands.iloc[0]
    fr = fund[row["pair"]]["rate"]
    past = fr[fr.index <= row["ts"]]
    sgn = 1.0 if row["side"] == "long" else -1.0
    assert full["r02"].loc[cands.index[0], "f_funding_last"] == pytest.approx(sgn * past.iloc[-1])
    assert full["r02"].loc[cands.index[0], "f_funding_sum3"] == pytest.approx(sgn * past.iloc[-3:].sum())


def test_rank_breadth_ranges_and_same_bar(full, data):
    cands = data[2]
    f = full["r02"]
    for c in ("f_rank_ret_24h", "f_rank_ret_7d"):
        assert f[c].between(0, 1).all()
    for r in full.values():
        assert r["f_breadth"].between(0, len(PAIRS)).all()
    expect = cands.groupby("ts")["pair"].transform("size").astype(float)
    np.testing.assert_array_equal(f["f_same_bar_signals"], expect)
    assert f["f_same_bar_signals"].max() == 2


def test_er_vr_basic():
    s = pd.Series(np.arange(1.0, 200.0))
    assert efficiency_ratio(s, 24).dropna().eq(1.0).all()
    assert efficiency_ratio(pd.Series(np.ones(50)), 24).dropna().eq(0.0).all()
    rng = np.random.default_rng(1)
    lp = pd.Series(np.cumsum(rng.normal(0, 0.01, 5000)))
    assert 0.8 < variance_ratio(lp, 4, 2000).iloc[-1] < 1.2
