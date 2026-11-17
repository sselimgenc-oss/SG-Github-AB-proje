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
    df = pd.DataFrame({"ts": ts, "pair": pr, "side": ["long", "short"] * 4}, index=range(10, 18))
    px = _make()
    ent = np.array([px[p]["close"].iloc[k] for p, k in zip(pr, pos)])           # sinyal mumu kapanisi
    df["planned_entry"] = ent
    df["planned_stop"] = np.where(df["side"] == "long", ent * 0.985, ent * 1.015)
    return df


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
    f = full["r02"]                                       # f_stop_dist_atr artik planned_entry/stop'tan: hep dolu
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
    past = fr[fr.index < row["ts"]]                       # KESINLIKLE < ts (mentor G4-3)
    win = fr[(fr.index > row["ts"] - pd.Timedelta(hours=24)) & (fr.index < row["ts"])]
    sgn = 1.0 if row["side"] == "long" else -1.0
    assert full["r02"].loc[cands.index[0], "f_funding_last"] == pytest.approx(sgn * past.iloc[-1])
    assert full["r02"].loc[cands.index[0], "f_funding_sum3"] == pytest.approx(sgn * win.sum())


def test_rank_breadth_ranges_and_same_bar(full, data):
    cands = data[2]
    f = full["r02"]
    for c in ("f_rank_ret_24h", "f_rank_ret_7d"):
        assert f[c].between(0, 1).all()
    for r in full.values():
        assert r["f_breadth"].between(0, 1).all()
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


# ------------------------------------------------------------------ mentor G4 duzeltmeleri (17 Kas)
def _long_data(days=260, seed=21):
    n = days * 24
    rng = np.random.default_rng(seed)
    idx = pd.date_range("2024-01-01", periods=n, freq="1h", tz="UTC")
    common = rng.normal(0, 0.004, n)
    out = {}
    for i, p in enumerate(PAIRS):
        c = 100 * (i + 1) * np.exp(np.cumsum(common * (1 + 0.1 * i) + rng.normal(0, 0.006, n)))
        o = np.concatenate([[c[0]], c[:-1]])
        h = np.maximum(o, c) * (1 + np.abs(rng.normal(0, 0.003, n)))
        l = np.minimum(o, c) * (1 - np.abs(rng.normal(0, 0.003, n)))
        out[p] = pd.DataFrame({"open": o, "high": h, "low": l, "close": c, "volume": rng.uniform(50, 150, n)}, index=idx)
    return out


def _cand_rows(pairs, tss, pair=BTC, side="long"):
    rows = []
    for ts in tss:
        e = float(pairs[pair]["close"].loc[ts - BAR])
        rows.append({"ts": ts, "pair": pair, "side": side, "planned_entry": e, "planned_stop": e * 0.99})
    return pd.DataFrame(rows)


ONE_D = ["f_btc_slope_1d", "f_btc_vol_1d", "f_eth_slope_1d", "f_slope_1d", "f_vol_1d"]


def test_g4_1_daily_context_identical_when_history_before_200d_dropped():
    pairs = _long_data()
    t0 = pairs[BTC].index[0]
    tss = [t0 + pd.Timedelta(days=d, hours=h) for d, h in ((230, 5), (240, 0), (250, 23), (255, 13))]
    for pair in (BTC, "SOL/USDT:USDT"):
        cands = _cand_rows(pairs, tss, pair)
        full2 = feature_frame_v2(pairs, cands, recipe="r02")
        full3 = feature_frame_v2(pairs, cands, recipe="r03")
        for i, ts in enumerate(tss):
            cut = {k: v[v.index >= ts - pd.Timedelta(days=200)] for k, v in pairs.items()}
            sub = cands.iloc[[i]]
            a2 = feature_frame_v2(cut, sub, recipe="r02")
            a3 = feature_frame_v2(cut, sub, recipe="r03")
            for c in ONE_D:
                np.testing.assert_allclose(a2[c].to_numpy(), full2.loc[[i], c].to_numpy(), rtol=1e-12, atol=1e-14)
            np.testing.assert_allclose(a3[["f_btc_slope_1d", "f_btc_vol_1d_pct90"]].to_numpy(),
                                       full3.loc[[i], ["f_btc_slope_1d", "f_btc_vol_1d_pct90"]].to_numpy(),
                                       rtol=1e-12, atol=1e-14)
    assert np.isfinite(full3["f_btc_vol_1d_pct90"]).all() and np.isfinite(full2[ONE_D].to_numpy()).all()


def test_g4_2_percentile_divides_by_nonnan_count():
    from trader_core.ml_features_v2 import _pct_last
    v = np.r_[np.full(60, np.nan), np.arange(35.0)]            # 35 gecerli, son = en buyuk
    assert _pct_last(v) == 1.0                                 # eski: 35/90
    v2 = np.r_[np.full(60, np.nan), np.arange(35.0)[::-1]]     # son = en kucuk
    assert _pct_last(v2) == pytest.approx(1 / 35)
    assert np.isnan(_pct_last(np.r_[np.full(80, np.nan), np.arange(10.0)]))   # < 30 gecerli
    assert _pct_last(np.arange(100.0)) == 1.0


def test_g4_3_funding_strictly_before_ts_and_24h_window(data):
    pairs, _, cands = data
    ts = cands["ts"].iloc[1]
    sub = cands.iloc[[1]].copy()
    ft = pd.date_range(ts - pd.Timedelta(hours=40), ts + pd.Timedelta(hours=16), freq="8h")   # ts uzerinde bir olay var
    assert ts in ft
    rates = pd.Series(np.arange(1.0, len(ft) + 1.0) * 1e-4, index=ft)
    fund = {p: pd.DataFrame({"funding_rate": rates}) for p in pairs}
    out = feature_frame_v2(pairs, sub, funding=fund, recipe="r02")
    sgn = -1.0 if sub["side"].iloc[0] == "short" else 1.0
    before = rates[rates.index < ts]
    assert out["f_funding_last"].iloc[0] == pytest.approx(sgn * before.iloc[-1])           # ts'deki olay HARIC
    in_win = rates[(rates.index > ts - pd.Timedelta(hours=24)) & (rates.index < ts)]
    assert len(in_win) == 2                                    # ts-16s, ts-8s (ts-24s ve ts haric)
    assert out["f_funding_sum3"].iloc[0] == pytest.approx(sgn * in_win.sum())
    fund2 = {p: d.copy() for p, d in fund.items()}
    for d in fund2.values():
        d.loc[ts, "funding_rate"] = 9.9                        # ts'deki olay degisse sonuc ayni
    out2 = feature_frame_v2(pairs, sub, funding=fund2, recipe="r02")
    assert out2[["f_funding_last", "f_funding_sum3"]].equals(out[["f_funding_last", "f_funding_sum3"]])


def test_g4_4_funding_column_required(data):
    pairs, fund, cands = data
    sub = cands.iloc[[0]]
    a = feature_frame_v2(pairs, sub, funding=fund, recipe="r02")                         # `rate`
    fr = {p: d.rename(columns={"rate": "funding_rate"}) for p, d in fund.items()}
    b = feature_frame_v2(pairs, sub, funding=fr, recipe="r02")
    pd.testing.assert_frame_equal(a, b)
    bad = {p: d.rename(columns={"rate": "oran"}) for p, d in fund.items()}
    with pytest.raises(ValueError, match="funding_rate"):
        feature_frame_v2(pairs, sub, funding=bad, recipe="r02")


def test_g4_5_breadth_fraction_and_min_valid_pairs(data, full):
    pairs, fund, cands = data
    b = full["r02"]["f_breadth"]
    assert np.allclose(b * 5, np.round(b * 5)) and b.between(0, 1).all()
    # son cift 30 Nis'tan once verisiz: erken adaylarda 4 gecerli cift -> NaN (genislik ve siralama), sonra dolu
    late = {k: (v[v.index >= pd.Timestamp("2024-04-30", tz="UTC")] if k == PAIRS[4] else v) for k, v in pairs.items()}
    sub = cands[cands["pair"] != PAIRS[4]]
    out = feature_frame_v2(late, sub, recipe="r02")
    early = (sub["ts"] < pd.Timestamp("2024-05-03", tz="UTC")).to_numpy()
    assert early.any() and (~early).any()
    assert out.loc[early, "f_breadth"].isna().all() and out.loc[~early, "f_breadth"].notna().all()
    assert out.loc[early, "f_rank_ret_7d"].isna().all() and out.loc[~early, "f_rank_ret_7d"].notna().all()
    # tamamen 4 cift -> hep NaN
    only4 = {k: v for k, v in pairs.items() if k != PAIRS[4]}
    o4 = feature_frame_v2(only4, cands[cands["pair"] != PAIRS[4]], recipe="r03")
    assert o4["f_breadth"].isna().all()


def test_g4_6_stop_dist_from_planned_entry_stop(data, full):
    from trader_core.indicators import atr
    pairs, _, cands = data
    f = full["r02"]["f_stop_dist_atr"]
    for i, r in cands.iterrows():
        a = atr(pairs[r["pair"]], 14).loc[r["ts"] - BAR]
        assert f.loc[i] == pytest.approx(abs(r["planned_entry"] - r["planned_stop"]) / a)
    with pytest.raises(ValueError, match="planned_entry"):
        feature_frame_v2(pairs, cands.drop(columns=["planned_entry", "planned_stop"]), recipe="r02")
    feature_frame_v2(pairs, cands.drop(columns=["planned_entry", "planned_stop"]), recipe="r03")   # r03 gerekmez


def test_g4_7_volume_zscore_no_inf_on_flat_volume(data):
    pairs, _, cands = data
    p2 = {k: v.copy() for k, v in pairs.items()}
    for v in p2.values():
        v["volume"] = 100.0                                    # std = 0
    out = feature_frame_v2(p2, cands, recipe="r02")
    assert not np.isinf(out.to_numpy(float)).any()
    assert out["f_vol_z_24"].isna().all() and out["f_vol_z_168"].isna().all()
