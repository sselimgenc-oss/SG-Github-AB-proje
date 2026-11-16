import numpy as np
import pandas as pd
import pytest

from trader_core.indicators import atr, ema, sma, true_range
from trader_core.regime import (Regime, RegimeParams, align_to_base, classify_last,
                                classify_series, count_edge_touches)


def stairs(n=150):
    t = np.arange(n)
    o = 100.0 + t
    c = 101.0 + t
    return pd.DataFrame({"open": o, "high": c + 0.5, "low": o - 0.5, "close": c})


def tri(n=150):
    m = np.array([100, 101, 102, 103, 104, 103, 102, 101], dtype=float)[np.arange(n) % 8]
    return pd.DataFrame({"open": m, "high": m + 1, "low": m - 1, "close": m})


def test_indicators_examples():
    e = ema(pd.Series([2, 4, 8, 6]), 3)
    assert e.isna().tolist() == [True, True, False, False]
    assert e.iloc[2:].tolist() == [5.5, 5.75]
    df = pd.DataFrame({"high": [10, 11, 13, 15], "low": [8, 9, 10, 14], "close": [9, 10, 12, 14.5]})
    assert true_range(df).tolist() == [2, 2, 3, 3]
    a = atr(df, 3)
    assert a.iloc[:2].isna().all()
    assert a.iloc[2] == pytest.approx(7 / 3) and a.iloc[3] == pytest.approx(23 / 9)
    assert sma(pd.Series([1.0, 2, 3, 4]), 2).tolist()[1:] == [1.5, 2.5, 3.5]
    with pytest.raises(ValueError):
        ema(pd.Series([1.0, np.inf]), 2)


def test_touches_examples():
    h = [10, 9.9, 9.0, 9.8, 10, 9.0, 9.95, 9.2]
    l = [8.0, 8.5, 8.4, 8.2, 8.9, 8.1, 8.8, 8.0]
    assert count_edge_touches(h, l, 10, 8, 0.3) == (3, 4)
    assert count_edge_touches([10, 10, 10], [1, 1, 1], 10, 0, 0)[0] == 1
    assert count_edge_touches([10, 9, 10], [1, 1, 1], 10, 0, 0)[0] == 2
    assert count_edge_touches([], [], 10, 8, 0.3) == (0, 0)


def test_end_to_end_labels():
    up = classify_series(stairs())
    assert up["regime"].iloc[149] == "trend_up" and np.isnan(up["rh"].iloc[149])
    assert (up["regime"].iloc[:112] == "unclear").all()
    dn = classify_series(stairs().rsub(400.0).rename(columns={"high": "low", "low": "high"})[
        ["open", "high", "low", "close"]])
    assert dn["regime"].iloc[149] == "trend_down"
    v = stairs()
    v.loc[149] = [249.0, 279.0, 249.0, 270.0]
    r = classify_series(v)
    assert r["regime"].iloc[149] == "volatile" and r["regime"].iloc[148] == "trend_up"
    assert r["atr_ratio"].iloc[149] == pytest.approx(4 / 2.02)
    rg = classify_series(tri())
    row = rg.iloc[149]
    assert (row["regime"], row["rh"], row["rl"], row["rh_touches"], row["rl_touches"]) == ("range", 105, 99, 3, 2)
    assert classify_series(tri(), RegimeParams(range_width_atr=3.0))["regime"].iloc[149] == "range"
    flat = pd.DataFrame({k: [100.0] * 150 for k in ("open", "high", "low", "close")})
    assert classify_series(flat)["regime"].iloc[-1] == "unclear"
    assert (classify_series(tri().iloc[:112])["regime"] == "unclear").all()


def test_no_lookahead_and_last():
    rng = np.random.default_rng(1)
    c = 100 + np.cumsum(rng.normal(0, 1, 260))
    df = pd.DataFrame({"open": c, "high": c + 1, "low": c - 1, "close": c})
    full = classify_series(df)
    for k in (1, 50, 113, 200):
        pd.testing.assert_frame_equal(full.iloc[:k], classify_series(df.iloc[:k]))
    res = classify_last(df)
    assert res.regime.value == full["regime"].iloc[-1]
    assert classify_last(df.drop(columns="close")).regime is Regime.UNCLEAR
    assert classify_last(df.iloc[:0]).tradeable is False
    bad = df.copy()
    bad.loc[200, "high"] = np.nan
    assert (classify_series(bad)["regime"].iloc[200:300] == "unclear").all()


def test_params_validation():
    for kw in ({"range_width_atr": 2.9}, {"vol_ratio_max": True}, {"edge_zone_atr": float("nan")},
               {"vol_ratio_max": None}, {"vol_ratio_max": "1.5"}):
        with pytest.raises(ValueError):
            RegimeParams(**kw)
    assert RegimeParams(vol_ratio_max=np.float32(1.5)).vol_ratio_max == 1.5


def test_align():
    idx4 = pd.date_range("2026-01-01 00:00", periods=3, freq="4h")  # 00,04,08 -> C 04,08,12
    rd = pd.DataFrame({"regime": ["trend_up", "range", "volatile"], "rh": [np.nan, 5.0, np.nan],
                       "rl": [np.nan, 1.0, np.nan], "rh_touches": [0, 2, 0], "rl_touches": [0, 2, 0],
                       "atr": [1.0, 1, 1], "atr_ratio": [1.0, 1, 1]}, index=idx4)
    base = pd.date_range("2026-01-01 03:00", "2026-01-01 20:00", freq="1h")
    out = align_to_base(rd, base)
    g = lambda s: out.loc[pd.Timestamp("2026-01-01 " + s), "regime"]
    assert g("03:00") == "unclear" and g("04:00") == "trend_up" and g("07:00") == "trend_up"
    assert g("08:00") == "range" and out.loc[pd.Timestamp("2026-01-01 08:00"), "rh"] == 5.0
    assert g("12:00") == "volatile" and g("15:00") == "volatile"
    assert g("16:00") == "unclear" and g("20:00") == "unclear"
    with pytest.raises(ValueError):
        align_to_base(rd, base.tz_localize("UTC"))
