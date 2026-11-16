"""Independent spec-based tests for trader_core.indicators / trader_core.regime
(spec v1, 16 Kasim 2026).

Written ONLY from docs/rejim-spec.md (the implementation was not read).

Test data conventions
---------------------
* ``from_mid(m, half)``: open = close = m, high = m + half, low = m - half.
  If |m_t - m_{t-1}| <= 1 and half = 1, then TR_t = 2 on every row
  (max(2, |m+1-m'| <= 2, |m-1-m'| <= 2) = 2), so ATR == 2 and atr_ratio == 1.
* ``stair``       = spec example 3a (up staircase), ATR == 2.
* ``tri``         = spec example 3c (triangle wave, period 8), ATR == 2.
* ``_ref_classify`` is a small, slow oracle written from the spec text; it is
  itself validated against the spec's hand-worked examples (3a/3b/3c) below.
"""
from __future__ import annotations

import dataclasses
import math

import numpy as np
import pandas as pd
import pytest

from trader_core import indicators as ind
from trader_core import regime as rg
from trader_core.regime import (DEFAULT_PARAMS, LESSON_BOUNDS, Regime,
                                RegimeParams, RegimeResult, align_to_base,
                                classify_last, classify_series,
                                count_edge_touches)

NAN = float("nan")
LABELS = {"trend_up", "trend_down", "range", "volatile", "unclear"}
COLS = ["regime", "rh", "rl", "rh_touches", "rl_touches", "atr", "atr_ratio"]


# --------------------------------------------------------------------------
# builders
# --------------------------------------------------------------------------
def ohlc(o, h, l, c, index=None):
    return pd.DataFrame({"open": np.asarray(o, float), "high": np.asarray(h, float),
                         "low": np.asarray(l, float), "close": np.asarray(c, float)},
                        index=index)


def from_mid(m, half=1.0):
    m = np.asarray(m, float)
    half = np.broadcast_to(np.asarray(half, float), m.shape)
    return ohlc(m, m + half, m - half, m)


def stair(n=150):
    """Spec 3a. open=100+t, close=101+t, high=close+0.5, low=open-0.5."""
    t = np.arange(n)
    return ohlc(100 + t, 101.5 + t, 99.5 + t, 101 + t)


def stair_down(n=150):
    """Mirror of 3a. open=300-t, close=299-t, high=open+0.5, low=close-0.5.
    TR_t (t>=1) = max(2, |high-pc|=|300.5-t-(300-t)|=0.5, |low-pc|=1.5) = 2."""
    t = np.arange(n)
    return ohlc(300 - t, 300.5 - t, 298.5 - t, 299 - t)


PAT8 = np.array([100, 101, 102, 103, 104, 103, 102, 101])


def tri(n=150):
    """Spec 3c."""
    return from_mid(PAT8[np.arange(n) % 8])


def tri_period(n, amp):
    """Triangle wave 100..100+amp..100 with period 2*amp (steps of 1)."""
    p = 2 * amp
    k = np.arange(n) % p
    return from_mid(100 + np.where(k <= amp, k, p - k))


def volatile_df():
    """Spec 3b: 3a for t<=148, then a spike candle at t=149."""
    d = stair(150)
    d.loc[149, ["open", "low", "high", "close"]] = [249.0, 249.0, 279.0, 270.0]
    return d


def cases():
    return {"stair": stair(150), "stair_down": stair_down(150), "tri": tri(150),
            "volatile": volatile_df(), "tri12": tri_period(158, 6)}


# --------------------------------------------------------------------------
# independent oracle (clean data only)
# --------------------------------------------------------------------------
def _runs(flags):
    n, prev = 0, False
    for f in flags:
        if f and not prev:
            n += 1
        prev = bool(f)
    return n


def _ref_touches(highs, lows, rh, rl, zone):
    h = np.asarray(highs, float)
    l = np.asarray(lows, float)
    return _runs(h >= rh - zone), _runs(l <= rl + zone)


def _ref_classify(df, vol=1.5, width=4.0, edge=0.25):
    h, l, c = df["high"], df["low"], df["close"]
    pc = c.shift(1)
    tr = pd.concat([h - l, (h - pc).abs(), (l - pc).abs()], axis=1).max(axis=1)
    atr = tr.ewm(alpha=1 / 14, adjust=False).mean()
    atr.iloc[:13] = np.nan
    e20 = c.ewm(span=20, adjust=False).mean()
    e50 = c.ewm(span=50, adjust=False).mean()
    e100 = c.ewm(span=100, adjust=False).mean()
    avg = atr.rolling(100, min_periods=100).mean()
    ratio = atr / avg
    rows = []
    for t in range(len(df)):
        rec = dict(regime="unclear", rh=NAN, rl=NAN, rh_touches=0, rl_touches=0)
        if t >= 112 and atr.iloc[t] > 0 and avg.iloc[t] > 0:
            if ratio.iloc[t] > vol:
                rec["regime"] = "volatile"
            else:
                sl = slice(t - 19, t + 1)
                RH, RL = h.iloc[sl].max(), l.iloc[sl].min()
                a = atr.iloc[t]
                nh, nl = _ref_touches(h.iloc[sl], l.iloc[sl], RH, RL, edge * a)
                if (RH - RL) / a <= width and nh >= 2 and nl >= 2:
                    rec.update(regime="range", rh=RH, rl=RL, rh_touches=nh, rl_touches=nl)
                elif c.iloc[t] > e100.iloc[t] and e20.iloc[t] > e50.iloc[t]:
                    rec["regime"] = "trend_up"
                elif c.iloc[t] < e100.iloc[t] and e20.iloc[t] < e50.iloc[t]:
                    rec["regime"] = "trend_down"
        rows.append(rec)
    out = pd.DataFrame(rows, index=df.index)
    out["atr"] = atr.values
    out["atr_ratio"] = ratio.values
    return out, (e20, e50, e100)


def assert_matches_ref(df, got, **kw):
    ref, _ = _ref_classify(df, **kw)
    assert list(got["regime"]) == list(ref["regime"])
    np.testing.assert_allclose(got["rh"].to_numpy(float), ref["rh"].to_numpy(float), equal_nan=True)
    np.testing.assert_allclose(got["rl"].to_numpy(float), ref["rl"].to_numpy(float), equal_nan=True)
    assert list(got["rh_touches"]) == list(ref["rh_touches"])
    assert list(got["rl_touches"]) == list(ref["rl_touches"])
    np.testing.assert_allclose(got["atr"].to_numpy(float), ref["atr"].to_numpy(float), equal_nan=True, rtol=1e-9)
    np.testing.assert_allclose(got["atr_ratio"].to_numpy(float), ref["atr_ratio"].to_numpy(float),
                               equal_nan=True, rtol=1e-9)


def assert_prefix_equal(df, full, k, params=DEFAULT_PARAMS):
    part = classify_series(df.iloc[:k], params)
    pd.testing.assert_frame_equal(part, full.iloc[:k], check_exact=True)


# ==========================================================================
# 1. indicators: formulas, warm-up, NaN
# ==========================================================================
class TestEMA:
    def test_spec_example(self):
        # alpha = 2/(3+1) = 0.5 ; e0=2 ; e1=.5*4+.5*2=3 ; e2=.5*8+.5*3=5.5 ; e3=.5*6+.5*5.5=5.75
        out = ind.ema(pd.Series([2.0, 4.0, 8.0, 6.0]), 3)
        np.testing.assert_allclose(out.to_numpy(), [NAN, NAN, 5.5, 5.75], equal_nan=True)

    def test_length_one_is_identity_no_warmup(self):
        # alpha = 2/2 = 1 -> e_t = x_t ; warm-up = length-1 = 0 values
        x = pd.Series([3.0, 1.0, 4.0, 1.5])
        np.testing.assert_allclose(ind.ema(x, 1).to_numpy(), x.to_numpy())

    def test_length2_hand(self):
        # alpha = 2/3 ; x=[3,6,0] : e0=3 ; e1=2/3*6+1/3*3=5 ; e2=2/3*0+1/3*5=5/3
        out = ind.ema(pd.Series([3.0, 6.0, 0.0]), 2)
        np.testing.assert_allclose(out.to_numpy(), [NAN, 5.0, 5 / 3], equal_nan=True)

    def test_constant_series_stays_constant(self):
        out = ind.ema(pd.Series([7.0] * 10), 4)
        assert out.iloc[:3].isna().all()
        np.testing.assert_allclose(out.iloc[3:].to_numpy(), 7.0)

    def test_index_preserved_and_input_untouched(self):
        idx = pd.date_range("2026-01-01", periods=4, freq="4h")
        x = pd.Series([2.0, 4.0, 8.0, 6.0], index=idx)
        before = x.copy()
        out = ind.ema(x, 3)
        assert out.index.equals(idx)
        pd.testing.assert_series_equal(x, before)

    def test_leading_nan_skipped_and_warmup_counts_real_observations(self):
        # x=[NaN,2,4,8,6]: recursion starts at idx1: e=2,3,5.5,5.75 ; valid once 3 real obs (idx3)
        out = ind.ema(pd.Series([NAN, 2.0, 4.0, 8.0, 6.0]), 3)
        np.testing.assert_allclose(out.to_numpy(), [NAN, NAN, NAN, 5.5, 5.75], equal_nan=True)

    def test_mid_nan_output_nan_state_carried(self):
        # x=[2,4,8,NaN,6]: e=2,3,5.5 ; idx3 NaN (state kept 5.5) ; idx4 = .5*6+.5*5.5 = 5.75
        out = ind.ema(pd.Series([2.0, 4.0, 8.0, NAN, 6.0]), 3)
        np.testing.assert_allclose(out.to_numpy(), [NAN, NAN, 5.5, NAN, 5.75], equal_nan=True)

    def test_nan_inside_warmup_delays_validity(self):
        # x=[2,NaN,4,8]: real obs at idx0,2,3 -> e=2,3,5.5 ; third real obs at idx3
        out = ind.ema(pd.Series([2.0, NAN, 4.0, 8.0]), 3)
        np.testing.assert_allclose(out.to_numpy(), [NAN, NAN, NAN, 5.5], equal_nan=True)

    def test_matches_pandas_ewm_beyond_warmup(self):
        rng = np.random.default_rng(1)
        x = pd.Series(100 + rng.normal(size=80).cumsum())
        ref = x.ewm(span=10, adjust=False).mean()
        out = ind.ema(x, 10)
        assert out.iloc[:9].isna().all()
        np.testing.assert_allclose(out.iloc[9:].to_numpy(), ref.iloc[9:].to_numpy(), rtol=1e-12)

    @pytest.mark.parametrize("bad", [0, -1, 1.5, "3", None])
    def test_bad_length(self, bad):
        with pytest.raises(ValueError):
            ind.ema(pd.Series([1.0, 2.0, 3.0]), bad)

    @pytest.mark.parametrize("bad", [float("inf"), float("-inf")])
    def test_inf_input_rejected(self, bad):
        with pytest.raises(ValueError):
            ind.ema(pd.Series([1.0, bad, 3.0]), 2)

    def test_no_lookahead(self):
        rng = np.random.default_rng(2)
        x = pd.Series(rng.normal(size=60).cumsum() + 50)
        full = ind.ema(x, 7)
        for k in (8, 20, 45):
            pd.testing.assert_series_equal(ind.ema(x.iloc[:k], 7), full.iloc[:k], check_exact=True)


class TestSMA:
    def test_hand(self):
        # length 3: (1+2+3)/3=2, (2+3+4)/3=3, (3+4+5)/3=4
        out = ind.sma(pd.Series([1.0, 2.0, 3.0, 4.0, 5.0]), 3)
        np.testing.assert_allclose(out.to_numpy(), [NAN, NAN, 2, 3, 4], equal_nan=True)

    def test_nan_in_window_gives_nan(self):
        # windows: [1,NaN,3] NaN ; [NaN,3,4] NaN ; [3,4,5] = 4
        out = ind.sma(pd.Series([1.0, NAN, 3.0, 4.0, 5.0]), 3)
        np.testing.assert_allclose(out.to_numpy(), [NAN, NAN, NAN, NAN, 4.0], equal_nan=True)

    def test_length_one(self):
        np.testing.assert_allclose(ind.sma(pd.Series([5.0, 6.0]), 1).to_numpy(), [5.0, 6.0])

    @pytest.mark.parametrize("bad", [0, -2, 2.5])
    def test_bad_length(self, bad):
        with pytest.raises(ValueError):
            ind.sma(pd.Series([1.0, 2.0]), bad)


class TestTrueRange:
    DF = ohlc([9, 10, 12, 14], [10, 11, 13, 15], [8, 9, 10, 14], [9, 10, 12, 14.5])

    def test_spec_example(self):
        # t0: no prev close -> 10-8=2
        # t1: max(11-9=2, |11-9|=2, |9-9|=0)=2
        # t2: max(13-10=3, |13-10|=3, |10-10|=0)=3
        # t3: max(15-14=1, |15-12|=3, |14-12|=2)=3
        np.testing.assert_allclose(ind.true_range(self.DF).to_numpy(), [2, 2, 3, 3])

    def test_no_warmup_and_index(self):
        idx = pd.date_range("2026-01-01", periods=4, freq="h")
        d = self.DF.copy()
        d.index = idx
        tr = ind.true_range(d)
        assert tr.index.equals(idx)
        assert not tr.isna().any()

    def test_gap_down_uses_prev_close(self):
        # prev close 20, bar high 12 low 10: max(2, |12-20|=8, |10-20|=10) = 10
        d = ohlc([20, 11], [21, 12], [19, 10], [20, 11])
        np.testing.assert_allclose(ind.true_range(d).to_numpy(), [2, 10])

    def test_nan_prev_close_falls_back_to_range(self):
        # row1 close NaN (high,low ok): TR1 = max(12-9=3, |12-9|=3, |9-9|=0) = 3
        # row2 prev close NaN: TR2 = high-low = 13-11 = 2
        d = ohlc([9, 10, 12], [10, 12, 13], [8, 9, 11], [9, NAN, 12])
        np.testing.assert_allclose(ind.true_range(d).to_numpy(), [2, 3, 2])

    def test_nan_high_or_low_gives_nan(self):
        d = ohlc([9, 10, 12], [10, NAN, 13], [8, 9, NAN], [9, 10, 12])
        out = ind.true_range(d).to_numpy()
        assert out[0] == 2 and math.isnan(out[1]) and math.isnan(out[2])

    def test_input_not_mutated(self):
        d = self.DF.copy()
        ind.true_range(d)
        pd.testing.assert_frame_equal(d, self.DF)


class TestATR:
    DF = TestTrueRange.DF

    def test_spec_example(self):
        # TR=[2,2,3,3], alpha=1/3: A0=2, A1=2, A2=2+(3-2)/3=7/3, A3=7/3+(3-7/3)/3=23/9
        out = ind.atr(self.DF, 3)
        np.testing.assert_allclose(out.to_numpy(), [NAN, NAN, 7 / 3, 23 / 9], equal_nan=True)

    def test_not_sma_seeded(self):
        # Classical Wilder would seed ATR2 = mean(2,2,3) = 7/3 too, but ATR3 differs
        # only by seed history; with TR=[1,5,1,1] : ours A=1,1+(5-1)/3=7/3, 7/3+(1-7/3)/3=29/... use numbers:
        # A0=1 ; A1=1+4/3=7/3 ; A2=7/3+(1-7/3)/3=7/3-4/9=17/9 (ours). SMA seed would give 7/3.
        d = ohlc([10, 10, 10], [11, 15, 11], [10, 10, 10], [10, 10, 10])
        # TR: t0 = 1 ; t1 = max(5, |15-10|=5, 0)=5?? (high-low=5) ; t2 = max(1,1,0)=1
        np.testing.assert_allclose(ind.true_range(d).to_numpy(), [1, 5, 1])
        # A0=1 ; A1=1+(5-1)/3=7/3 ; A2=7/3+(1-7/3)/3=7/3-4/9=17/9
        out = ind.atr(d, 3)
        assert math.isclose(out.iloc[2], 17 / 9, rel_tol=1e-12)

    def test_length_one_equals_tr(self):
        # alpha = 1 -> ATR = TR, no warm-up
        np.testing.assert_allclose(ind.atr(self.DF, 1).to_numpy(), [2, 2, 3, 3])

    def test_default_length_14_first_valid_index_13(self):
        d = from_mid(np.full(30, 100.0))        # TR = 2 on every row
        out = ind.atr(d)
        assert out.iloc[:13].isna().all()
        assert out.iloc[13] == pytest.approx(2.0)
        assert out.iloc[29] == pytest.approx(2.0)

    def test_nan_row_carries_state(self):
        # rows (h,l,c): (10,8,9) TR2 ; (11,9,10) TR2 ; all-NaN row ; (13,10,12) TR=3 (prev close NaN
        # -> high-low) ; (15,14,14.5) TR=max(1,3,2)=3.  length 3, alpha=1/3
        # obs: A0=2, A1=2, NaN skipped, A=2+(3-2)/3=7/3 (3rd real obs -> valid), then 23/9
        d = ohlc([9, 10, NAN, 11, 14.5], [10, 11, NAN, 13, 15], [8, 9, NAN, 10, 14], [9, 10, NAN, 12, 14.5])
        out = ind.atr(d, 3)
        np.testing.assert_allclose(out.to_numpy(), [NAN, NAN, NAN, 7 / 3, 23 / 9], equal_nan=True)

    def test_matches_recursion_on_random_data(self):
        rng = np.random.default_rng(3)
        c = 100 + rng.normal(size=60).cumsum()
        o = np.r_[c[0], c[:-1]]
        h = np.maximum(o, c) + rng.random(60)
        l = np.minimum(o, c) - rng.random(60)
        d = ohlc(o, h, l, c)
        tr = ind.true_range(d).to_numpy()
        a = np.empty(60)
        a[0] = tr[0]
        for i in range(1, 60):
            a[i] = a[i - 1] + (tr[i] - a[i - 1]) / 14
        out = ind.atr(d, 14)
        assert out.iloc[:13].isna().all()
        np.testing.assert_allclose(out.iloc[13:].to_numpy(), a[13:], rtol=1e-10)

    def test_no_lookahead(self):
        d = tri(60)
        full = ind.atr(d, 14)
        for k in (14, 30, 59):
            pd.testing.assert_series_equal(ind.atr(d.iloc[:k], 14), full.iloc[:k], check_exact=True)

    @pytest.mark.parametrize("bad", [0, -1, 2.5])
    def test_bad_length(self, bad):
        with pytest.raises(ValueError):
            ind.atr(self.DF, bad)


# ==========================================================================
# 2. count_edge_touches
# ==========================================================================
class TestEdgeTouches:
    def test_spec_example_2(self):
        # rh=10 rl=8 zone=.3 ; upper >= 9.7 ; lower <= 8.3
        highs = [10, 9.9, 9.0, 9.8, 10, 9.0, 9.95, 9.2]   # T T F T T F T F -> runs [0,1],[3,4],[6] = 3
        lows = [8.0, 8.5, 8.4, 8.2, 8.9, 8.1, 8.8, 8.0]   # T F F T F T F T -> 4 runs
        assert count_edge_touches(highs, lows, 10, 8, 0.3) == (3, 4)

    def test_consecutive_bars_are_one_touch(self):
        assert count_edge_touches([10, 10, 10], [9, 9, 9], 10, 5, 0.1) == (1, 0)

    def test_one_bar_separation_makes_two_touches(self):
        # zone=0 : [10,9,10] -> T F T = 2 upper runs
        assert count_edge_touches([10, 9, 10], [8, 8, 8], 10, 0, 0.0)[0] == 2

    def test_boundary_is_inclusive(self):
        # rh=10 zone=.5 -> threshold 9.5 exactly counts; rl=0 zone=.5 -> threshold 0.5 counts
        assert count_edge_touches([9.5], [0.5], 10, 0, 0.5) == (1, 1)
        assert count_edge_touches([9.4999], [0.5001], 10, 0, 0.5) == (0, 0)

    def test_run_at_window_start_counts_once(self):
        # first two bars already in zone (run began before window): counted as 1; then out; then in = 2
        assert count_edge_touches([10, 10, 5, 10], [1, 1, 1, 1], 10, 0.5, 0.0)[0] == 2

    def test_empty(self):
        assert count_edge_touches([], [], 10, 8, 0.3) == (0, 0)

    def test_length_mismatch(self):
        with pytest.raises(ValueError):
            count_edge_touches([1, 2, 3], [1, 2], 3, 1, 0.1)

    def test_bar_in_both_zones_counts_on_both_sides(self):
        # rh=10, rl=9.8, zone=.5: bar (high 10, low 9.8) is in upper zone (>=9.5) and lower (<=10.3)
        assert count_edge_touches([10], [9.8], 10, 9.8, 0.5) == (1, 1)

    def test_accepts_numpy_and_series(self):
        h = np.array([10.0, 9.0, 10.0])
        l = np.array([8.0, 8.0, 8.0])
        assert count_edge_touches(h, l, 10, 8, 0.0) == (2, 3 - 2)  # lows all in lower zone -> 1 run
        assert count_edge_touches(pd.Series(h), pd.Series(l), 10, 8, 0.0) == (2, 1)

    def test_not_limited_to_20(self):
        highs = [10, 9] * 50                       # 50 separate touches
        assert count_edge_touches(highs, [1] * 100, 10, 1, 0.0) == (50, 1)


# ==========================================================================
# 3. params, enum, constants
# ==========================================================================
class TestParams:
    def test_defaults(self):
        p = RegimeParams()
        assert (p.range_width_atr, p.vol_ratio_max, p.edge_zone_atr) == (4.0, 1.5, 0.25)
        assert DEFAULT_PARAMS == RegimeParams()

    def test_frozen(self):
        with pytest.raises(dataclasses.FrozenInstanceError):
            DEFAULT_PARAMS.vol_ratio_max = 1.4

    @pytest.mark.parametrize("kw", [
        {"range_width_atr": 3.0}, {"range_width_atr": 6.0},
        {"vol_ratio_max": 1.25}, {"vol_ratio_max": 2.0},
        {"edge_zone_atr": 0.15}, {"edge_zone_atr": 0.50},
    ])
    def test_bounds_inclusive(self, kw):
        RegimeParams(**kw)

    @pytest.mark.parametrize("kw", [
        {"range_width_atr": 2.999}, {"range_width_atr": 6.001},
        {"vol_ratio_max": 1.249}, {"vol_ratio_max": 2.001},
        {"edge_zone_atr": 0.149}, {"edge_zone_atr": 0.501},
        {"range_width_atr": 0}, {"vol_ratio_max": -1.5}, {"edge_zone_atr": 100},
    ])
    def test_out_of_range(self, kw):
        with pytest.raises(ValueError):
            RegimeParams(**kw)

    @pytest.mark.parametrize("field", ["range_width_atr", "vol_ratio_max", "edge_zone_atr"])
    @pytest.mark.parametrize("bad", [float("nan"), float("inf"), float("-inf"), True, False, None, "4.0", [4.0]])
    def test_non_numeric_or_non_finite(self, field, bad):
        with pytest.raises(ValueError):
            RegimeParams(**{field: bad})

    def test_numpy_and_int_accepted_and_converted(self):
        p = RegimeParams(range_width_atr=np.int64(5), vol_ratio_max=np.float64(1.4), edge_zone_atr=np.float32(0.25))
        assert p.range_width_atr == 5.0 and isinstance(p.range_width_atr, float)
        assert p.vol_ratio_max == 1.4
        assert RegimeParams(range_width_atr=4).range_width_atr == 4.0

    def test_lesson_bounds(self):
        assert LESSON_BOUNDS == {"vol_ratio_max": (1.3, 1.7)}

    def test_lesson_bounds_not_enforced_by_params(self):
        # backtest must be able to scan 1.25..2.0
        assert RegimeParams(vol_ratio_max=1.25).vol_ratio_max == 1.25
        assert RegimeParams(vol_ratio_max=2.0).vol_ratio_max == 2.0

    def test_constants(self):
        assert rg.ATR_LEN == 14
        assert (rg.EMA_FAST, rg.EMA_MID, rg.EMA_SLOW) == (20, 50, 100)
        assert rg.RANGE_WINDOW == 20
        assert rg.MIN_EDGE_TOUCHES == 2
        assert rg.VOL_AVG_WINDOW == 100
        assert rg.MIN_BARS == 113
        # constants are not parameters
        assert not {"atr_len", "range_window", "min_edge_touches"} & {f.name for f in dataclasses.fields(RegimeParams)}


class TestEnumAndResult:
    def test_values(self):
        assert {m.name: m.value for m in Regime} == {
            "TREND_UP": "trend_up", "TREND_DOWN": "trend_down", "RANGE": "range",
            "VOLATILE": "volatile", "UNCLEAR": "unclear"}

    def test_str_enum(self):
        assert Regime.RANGE == "range"
        assert Regime("trend_up") is Regime.TREND_UP

    @pytest.mark.parametrize("reg,ok", [
        (Regime.TREND_UP, True), (Regime.TREND_DOWN, True), (Regime.RANGE, True),
        (Regime.VOLATILE, False), (Regime.UNCLEAR, False)])
    def test_tradeable(self, reg, ok):
        r = RegimeResult(reg, None, None, 0, 0, None, None, "x")
        assert r.tradeable is ok

    def test_result_is_frozen(self):
        r = RegimeResult(Regime.UNCLEAR, None, None, 0, 0, None, None, "x")
        with pytest.raises(dataclasses.FrozenInstanceError):
            r.reason = "y"


# ==========================================================================
# 4. labels on deterministic synthetic data
# ==========================================================================
class TestOracleValidatedAgainstSpecExamples:
    """The oracle used in differential tests must reproduce the spec's hand values."""

    def test_3a(self):
        r, _ = _ref_classify(stair())
        assert r.regime.iloc[149] == "trend_up"

    def test_3b(self):
        r, _ = _ref_classify(volatile_df())
        assert r.regime.iloc[149] == "volatile" and r.regime.iloc[148] == "trend_up"

    def test_3c(self):
        r, _ = _ref_classify(tri())
        x = r.iloc[149]
        assert (x.regime, x.rh, x.rl, x.rh_touches, x.rl_touches) == ("range", 105, 99, 3, 2)


class TestLabelsSpecExample3:
    def test_3a_trend_up(self):
        # ATR=2 every bar; width=(250.5-229.5)/2=10.5>4 -> not range; close>EMA100 & EMA20>EMA50
        res = classify_series(stair())
        row = res.iloc[149]
        assert row["regime"] == "trend_up"
        assert math.isnan(row["rh"]) and math.isnan(row["rl"])
        assert row["rh_touches"] == 0 and row["rl_touches"] == 0
        assert row["atr"] == pytest.approx(2.0)
        assert row["atr_ratio"] == pytest.approx(1.0)

    def test_3a_mirror_trend_down(self):
        res = classify_series(stair_down())
        assert res["regime"].iloc[149] == "trend_down"
        assert res["atr"].iloc[149] == pytest.approx(2.0)

    def test_3b_volatile(self):
        # TR149=30 ; ATR149=2+(30-2)/14=4 ; avgATR=(99*2+4)/100=2.02 ; ratio=1.9802>1.5
        res = classify_series(volatile_df())
        row = res.iloc[149]
        assert row["regime"] == "volatile"
        assert row["atr"] == pytest.approx(4.0)
        assert row["atr_ratio"] == pytest.approx(4 / 2.02)
        assert math.isnan(row["rh"]) and math.isnan(row["rl"])
        assert row["rh_touches"] == 0 and row["rl_touches"] == 0
        assert res["regime"].iloc[148] == "trend_up"

    def test_3c_range(self):
        # t=149 W=130..149 ; peaks 132,140,148 (high 105) ; troughs 144,136 (low 99) ; width=6/2=3
        # zone=.25*2=.5 -> upper >=104.5 only m=104 -> 3 touches ; lower <=99.5 only m=100 -> 2 touches
        res = classify_series(tri())
        row = res.iloc[149]
        assert row["regime"] == "range"
        assert row["rh"] == 105.0 and row["rl"] == 99.0
        assert row["rh_touches"] == 3 and row["rl_touches"] == 2
        assert row["atr"] == pytest.approx(2.0)
        assert row["atr_ratio"] == pytest.approx(1.0)

    def test_3c_width_equality_included(self):
        # width = 3 exactly ; range_width_atr=3.0 (lower bound) -> still range
        res = classify_series(tri(), RegimeParams(range_width_atr=3.0))
        assert res["regime"].iloc[149] == "range"

    def test_3c_edge_zone_015_same_result(self):
        # zone .3: upper >=104.7 only m=104 ; lower <=99.3 only m=100
        row = classify_series(tri(), RegimeParams(edge_zone_atr=0.15)).iloc[149]
        assert (row["regime"], row["rh_touches"], row["rl_touches"]) == ("range", 3, 2)

    def test_3c_edge_zone_050(self):
        # zone=1: upper high>=104 -> m in {103,104,103} runs 131-133,139-141,147-149 = 3
        #         lower low<=100 -> m in {101,100,101} runs 135-137,143-145 = 2
        row = classify_series(tri(), RegimeParams(edge_zone_atr=0.50)).iloc[149]
        assert (row["regime"], row["rh_touches"], row["rl_touches"]) == ("range", 3, 2)

    @pytest.mark.parametrize("name", ["stair", "stair_down", "tri", "volatile", "tri12"])
    def test_first_112_rows_unclear(self, name):
        res = classify_series(cases()[name])
        assert (res["regime"].iloc[:112] == "unclear").all()
        assert (res["rh_touches"].iloc[:112] == 0).all()
        assert res["rh"].iloc[:112].isna().all()

    def test_exactly_112_rows_all_unclear(self):
        assert (classify_series(stair().iloc[:112])["regime"] == "unclear").all()

    def test_113_rows_last_row_classifiable(self):
        # index 112 is the first row where ATR14 and sma(ATR,100) exist ; stair -> trend_up
        res = classify_series(stair().iloc[:113])
        assert res["regime"].iloc[112] == "trend_up"
        assert res["atr"].iloc[112] == pytest.approx(2.0)

    def test_flat_prices_unclear_atr_zero(self):
        d = ohlc(*[np.full(150, 100.0)] * 4)
        res = classify_series(d)
        assert (res["regime"] == "unclear").all()
        assert classify_last(d).regime is Regime.UNCLEAR

    def test_unclear_when_trend_conditions_mixed(self):
        # up 120 steps (100..219) then down 30 steps (218..189), 150 bars, ATR=2.
        # close(189) > EMA100 but EMA20 < EMA50 -> neither trend group; width = 32/2=16 -> not range.
        m = np.r_[100 + np.arange(120), 219 - np.arange(1, 31)]
        d = from_mid(m)
        res = classify_series(d)
        _, (e20, e50, e100) = _ref_classify(d)
        assert d["close"].iloc[149] > e100.iloc[149] and e20.iloc[149] < e50.iloc[149]
        assert res["regime"].iloc[149] == "unclear"
        assert classify_last(d).regime is Regime.UNCLEAR

    def test_non_range_rows_have_clean_range_columns(self):
        res = classify_series(stair())
        nr = res[res["regime"] != "range"]
        assert nr["rh"].isna().all() and nr["rl"].isna().all()
        assert (nr["rh_touches"] == 0).all() and (nr["rl_touches"] == 0).all()


class TestPrecedence:
    def test_volatile_beats_trend_and_range(self):
        # 3b: trend_up conditions hold on bar 149 (close 270 > EMA100, EMA20 > EMA50) yet volatile wins
        d = volatile_df()
        _, (e20, e50, e100) = _ref_classify(d)
        assert d["close"].iloc[149] > e100.iloc[149] and e20.iloc[149] > e50.iloc[149]
        assert classify_series(d)["regime"].iloc[149] == "volatile"

    def test_same_bar_becomes_trend_up_when_volatility_threshold_raised(self):
        # ratio = 1.9802 < 2.0 -> not volatile -> width=(279-229.5)/4=12.4>4 -> not range -> trend_up
        row = classify_series(volatile_df(), RegimeParams(vol_ratio_max=2.0)).iloc[149]
        assert row["regime"] == "trend_up"

    def test_range_beats_trend(self):
        # 100 up-steps (100..199) then triangle wave 200..204 (period 8), 150 bars, ATR=2.
        # At t=149 the trend group "up" is true (checked with independent EMAs) but the
        # 20-bar window k=30..49: peaks (m=204) 136,144 ; troughs (m=200) 132,140,148 ; width=(205-199)/2=3
        # -> range with rh=205 rl=199, touches (2,3).
        k = np.arange(50)
        m = np.r_[100 + np.arange(100), 200 + np.array([0, 1, 2, 3, 4, 3, 2, 1])[k % 8]]
        d = from_mid(m)
        _, (e20, e50, e100) = _ref_classify(d)
        assert d["close"].iloc[149] > e100.iloc[149] and e20.iloc[149] > e50.iloc[149]
        row = classify_series(d).iloc[149]
        assert row["regime"] == "range"
        assert (row["rh"], row["rl"], row["rh_touches"], row["rl_touches"]) == (205.0, 199.0, 2, 3)

    @staticmethod
    def _wide_tail():
        # triangle (period 8), half-range 1.0 for t<134 and 1.5 for t>=134 (TR 2 -> 3)
        # ATR149 = 3 - (13/14)^16 = 2.6945 ; avgATR(50..149)=(168+38.97)/100=2.0697 ; ratio=1.302
        # -> between 1.25 and 1.5. Range: RH=105.5 (t=140,148 and 132 @105), RL=98.5 ; width=7/2.69=2.6<=4
        # zone=.25*2.6945=.674 -> upper >=104.83 : 132(105),140,148 = 3 ; lower <=99.17 : 136(99),144(98.5) = 2
        m = PAT8[np.arange(150) % 8]
        half = np.where(np.arange(150) >= 134, 1.5, 1.0)
        return from_mid(m, half)

    def test_range_when_ratio_below_default_threshold(self):
        row = classify_series(self._wide_tail()).iloc[149]
        assert 1.25 < row["atr_ratio"] < 1.5
        assert row["atr_ratio"] == pytest.approx(1.302, abs=2e-3)
        assert row["regime"] == "range"
        assert (row["rh"], row["rl"], row["rh_touches"], row["rl_touches"]) == (105.5, 98.5, 3, 2)

    def test_volatile_beats_range_with_lower_threshold(self):
        row = classify_series(self._wide_tail(), RegimeParams(vol_ratio_max=1.25)).iloc[149]
        assert row["regime"] == "volatile"
        assert math.isnan(row["rh"]) and row["rh_touches"] == 0


class TestRangeRules:
    # tri12: triangle wave 100..106..100, period 12, width = (107-99)/2 = 4 exactly (ATR=2)
    def test_width_exactly_at_limit_is_range(self):
        # n=158 -> t=157 (W=138..157): upper runs at 138,150 ; lower runs at 144,156 -> (2,2)
        row = classify_series(tri_period(158, 6)).iloc[157]
        assert row["regime"] == "range"
        assert (row["rh"], row["rl"], row["rh_touches"], row["rl_touches"]) == (107.0, 99.0, 2, 2)

    def test_width_above_limit_not_range(self):
        row = classify_series(tri_period(158, 6), RegimeParams(range_width_atr=3.0)).iloc[157]
        assert row["regime"] != "range"
        assert math.isnan(row["rh"]) and row["rh_touches"] == 0 and row["rl_touches"] == 0

    def test_amplitude7_width_4_5_not_range_by_default(self):
        # m 100..107 -> RH=108, RL=99, width=9/2=4.5 > 4 for every t
        res = classify_series(tri_period(200, 7))
        assert (res["regime"] != "range").all()

    def test_single_upper_touch_blocks_range(self):
        # t=149 (n=150): window 130..149 has one peak run (138) -> rh_touches=1 (width ok =4)
        res = classify_series(tri_period(150, 6))
        row = res.iloc[149]
        assert row["regime"] != "range"
        assert math.isnan(row["rh"]) and row["rh_touches"] == 0 and row["rl_touches"] == 0

    def test_single_lower_touch_blocks_range(self):
        # t=152 (n=153): window 133..152: peaks 138,150 ; troughs only 144 -> rl_touches=1
        row = classify_series(tri_period(153, 6)).iloc[152]
        assert row["regime"] != "range"
        assert row["rl_touches"] == 0

    def test_differential_against_oracle_on_period12(self):
        d = tri_period(200, 6)
        assert_matches_ref(d, classify_series(d))

    @pytest.mark.parametrize("name", ["stair", "stair_down", "tri", "volatile", "tri12"])
    def test_differential_all_cases(self, name):
        d = cases()[name]
        assert_matches_ref(d, classify_series(d))

    def test_differential_non_default_params(self):
        d = tri_period(200, 6)
        p = RegimeParams(range_width_atr=3.5, vol_ratio_max=1.3, edge_zone_atr=0.4)
        assert_matches_ref(d, classify_series(d, p), vol=1.3, width=3.5, edge=0.4)


# ==========================================================================
# 5. classify_series schema / classify_last / robustness
# ==========================================================================
class TestSchemaAndInputs:
    def test_schema(self):
        d = tri()
        res = classify_series(d)
        assert res.index.equals(d.index)
        for c in COLS:
            assert c in res.columns
        assert res["regime"].dtype == object
        assert res["rh"].dtype == np.float64 and res["rl"].dtype == np.float64
        assert res["rh_touches"].dtype == np.int64 and res["rl_touches"].dtype == np.int64
        assert res["atr"].dtype == np.float64 and res["atr_ratio"].dtype == np.float64
        assert set(res["regime"]) <= LABELS
        assert not res["regime"].isna().any()

    def test_input_not_mutated(self):
        d = tri()
        before = d.copy()
        classify_series(d)
        classify_last(d)
        pd.testing.assert_frame_equal(d, before)

    def test_deterministic(self):
        d = stair()
        pd.testing.assert_frame_equal(classify_series(d), classify_series(d), check_exact=True)

    def test_volume_ignored_and_optional(self):
        d = tri()
        d2 = d.copy()
        d2["volume"] = np.random.default_rng(0).random(len(d)) * 1000
        pd.testing.assert_frame_equal(classify_series(d), classify_series(d2), check_exact=True)

    def test_datetime_index_works(self):
        d = tri()
        d.index = pd.date_range("2026-01-01", periods=len(d), freq="4h")
        res = classify_series(d)
        assert res.index.equals(d.index)
        assert res["regime"].iloc[149] == "range"

    def test_empty_frame(self):
        d = ohlc([], [], [], [])
        res = classify_series(d)
        assert len(res) == 0
        r = classify_last(d)
        assert r.regime is Regime.UNCLEAR and not r.tradeable

    def test_single_row(self):
        d = ohlc([10], [11], [9], [10])
        assert classify_series(d)["regime"].tolist() == ["unclear"]
        assert classify_last(d).regime is Regime.UNCLEAR

    def test_structural_errors_raise_in_series(self):
        with pytest.raises(ValueError):
            classify_series([1, 2, 3])
        with pytest.raises(ValueError):
            classify_series(tri().drop(columns=["low"]))
        d = tri()
        d.index = d.index[::-1]
        with pytest.raises(ValueError):
            classify_series(d)
        d = tri()
        d.index = [0] * len(d)
        with pytest.raises(ValueError):
            classify_series(d)

    @pytest.mark.parametrize("make_bad", ["notdf", "nocol", "desc", "dup"])
    def test_classify_last_never_raises_fail_closed(self, make_bad):
        d = tri()
        if make_bad == "notdf":
            d = [1, 2, 3]
        elif make_bad == "nocol":
            d = d.drop(columns=["close"])
        elif make_bad == "desc":
            d.index = d.index[::-1]
        else:
            d.index = [5] * len(d)
        r = classify_last(d)
        assert r.regime is Regime.UNCLEAR
        assert r.rh is None and r.rl is None and r.atr is None and r.atr_ratio is None
        assert (r.rh_touches, r.rl_touches) == (0, 0)
        assert isinstance(r.reason, str) and r.reason
        assert not r.tradeable


class TestClassifyLast:
    def test_range(self):
        r = classify_last(tri())
        assert r.regime is Regime.RANGE and r.tradeable
        assert (r.rh, r.rl, r.rh_touches, r.rl_touches) == (105.0, 99.0, 3, 2)
        assert r.atr == pytest.approx(2.0) and r.atr_ratio == pytest.approx(1.0)
        assert isinstance(r.reason, str) and r.reason

    def test_trend_up_down(self):
        up = classify_last(stair())
        assert up.regime is Regime.TREND_UP and up.tradeable and up.rh is None and up.rl is None
        assert up.rh_touches == 0
        assert classify_last(stair_down()).regime is Regime.TREND_DOWN

    def test_volatile(self):
        r = classify_last(volatile_df())
        assert r.regime is Regime.VOLATILE and not r.tradeable
        assert r.rh is None and r.rl is None
        assert r.atr == pytest.approx(4.0) and r.atr_ratio == pytest.approx(4 / 2.02)

    def test_insufficient_history(self):
        r = classify_last(stair().iloc[:100])
        assert r.regime is Regime.UNCLEAR and not r.tradeable
        assert r.atr_ratio is None

    def test_params_passed_through(self):
        assert classify_last(volatile_df(), RegimeParams(vol_ratio_max=2.0)).regime is Regime.TREND_UP

    def test_equals_last_row_of_series(self):
        d = tri()
        row = classify_series(d).iloc[-1]
        r = classify_last(d)
        assert r.regime.value == row["regime"]


class TestInvalidCandles:
    @pytest.mark.parametrize("vals", [
        [100.0, 99.0, 101.0, 100.0],        # open,high,low,close : high < low
        [100.0, 101.0, 99.0, 102.0],        # close > high
        [100.0, 101.0, 99.0, 98.0],         # close < low
        [102.0, 101.0, 99.0, 100.0],        # open > high
        [98.0, 101.0, 99.0, 100.0],         # open < low
        [NAN, 101.0, 99.0, 100.0],
        [100.0, NAN, 99.0, 100.0],
        [100.0, 101.0, NAN, 100.0],
        [100.0, 101.0, 99.0, NAN],
        [100.0, float("inf"), 99.0, 100.0],
        [0.0, 101.0, 0.0, 100.0],           # non-positive prices
        [-1.0, 101.0, -2.0, 100.0],
    ])
    def test_invalid_last_candle_unclear_without_exception(self, vals):
        d = stair(150)
        d.loc[149, ["open", "high", "low", "close"]] = vals
        res = classify_series(d)
        assert res["regime"].iloc[149] == "unclear"
        assert math.isnan(res["rh"].iloc[149]) and res["rh_touches"].iloc[149] == 0
        assert res["regime"].iloc[148] == "trend_up"          # earlier row unaffected (no lookahead)
        assert classify_last(d).regime is Regime.UNCLEAR

    def test_nan_row_poisons_following_100_rows(self):
        # NaN at t=130 -> sma(ATR,100) window contains NaN for t=130..229 ; all unclear
        d = stair(300)
        d.loc[130, ["open", "high", "low", "close"]] = NAN
        res = classify_series(d)
        assert (res["regime"].iloc[112:130] == "trend_up").all()
        assert (res["regime"].iloc[130:230] == "unclear").all()
        assert res["regime"].iloc[130:230].map(lambda s: s in LABELS).all()

    def test_ema_does_not_stay_corrupted_after_nan(self):
        # after the poison window rows are classifiable again (not NaN-stuck forever)
        d = stair(400)
        d.loc[130, ["open", "high", "low", "close"]] = NAN
        res = classify_series(d)
        assert (res["regime"].iloc[-20:] != "unclear").any()

    def test_nan_in_window_only_effects(self):
        # a NaN high inside the 20-bar window makes that row unclear
        d = stair(150)
        d.loc[140, "high"] = NAN
        res = classify_series(d)
        assert (res["regime"].iloc[140:150] == "unclear").all()


# ==========================================================================
# 6. NO-LOOKAHEAD
# ==========================================================================
class TestNoLookahead:
    @pytest.mark.parametrize("name", ["stair", "stair_down", "tri", "volatile", "tri12"])
    def test_prefix_invariance_every_k(self, name):
        d = cases()[name]
        full = classify_series(d)
        for k in range(1, len(d) + 1, 3):
            assert_prefix_equal(d, full, k)
        assert_prefix_equal(d, full, len(d))

    def test_prefix_invariance_exactly_at_boundaries(self):
        d = tri(200)
        full = classify_series(d)
        for k in (1, 2, 13, 14, 19, 20, 99, 100, 111, 112, 113, 114, 150, 199, 200):
            assert_prefix_equal(d, full, k)

    def test_prefix_invariance_nonlinear_params(self):
        d = tri_period(200, 6)
        p = RegimeParams(range_width_atr=3.0, vol_ratio_max=1.25, edge_zone_atr=0.15)
        full = classify_series(d, p)
        for k in range(100, 201, 5):
            assert_prefix_equal(d, full, k, p)

    def test_prefix_invariance_with_invalid_rows(self):
        d = stair(260)
        d.loc[130, "close"] = NAN
        d.loc[200, ["high", "low"]] = [100.0, 101.0]   # high < low
        full = classify_series(d)
        for k in range(1, 261, 7):
            assert_prefix_equal(d, full, k)

    @pytest.mark.parametrize("name", ["stair", "tri", "volatile", "tri12"])
    @pytest.mark.parametrize("how", ["nan", "scale", "spike", "zero", "swap"])
    def test_mutating_future_never_changes_past(self, name, how):
        d = cases()[name]
        base = classify_series(d)
        n = len(d)
        for t in (60, 112, 113, 125, 140, n - 2):
            m = d.copy()
            fut = m.index[t + 1:]
            if how == "nan":
                m.loc[fut, ["open", "high", "low", "close"]] = NAN
            elif how == "scale":
                m.loc[fut, ["open", "high", "low", "close"]] = m.loc[fut, ["open", "high", "low", "close"]] * 3.7
            elif how == "spike":
                m.loc[fut, "high"] = 1e6
                m.loc[fut, "low"] = 1.0
            elif how == "zero":
                m.loc[fut, ["open", "high", "low", "close"]] = 0.0
            else:
                m.loc[fut, ["high", "low"]] = m.loc[fut, ["low", "high"]].to_numpy()
            got = classify_series(m)
            pd.testing.assert_frame_equal(got.iloc[:t + 1], base.iloc[:t + 1], check_exact=True)

    def test_mutating_bar_t_does_not_change_earlier_labels(self):
        d = tri(150)
        base = classify_series(d)
        m = d.copy()
        m.loc[130, ["high", "close"]] = [500.0, 500.0]
        got = classify_series(m)
        pd.testing.assert_frame_equal(got.iloc[:130], base.iloc[:130], check_exact=True)

    def test_appending_bars_keeps_last_label_of_old_prefix(self):
        d = tri(200)
        for t in range(112, 190, 7):
            assert classify_last(d.iloc[:t + 1]).regime.value == classify_series(d).iloc[t]["regime"]

    def test_classify_last_matches_series_at_every_prefix(self):
        d = stair(140)
        full = classify_series(d)
        for t in range(0, 140, 5):
            r = classify_last(d.iloc[:t + 1])
            assert r.regime.value == full["regime"].iloc[t]


# ==========================================================================
# 7. align_to_base : 4h -> 1h mapping
# ==========================================================================
T0 = pd.Timestamp("2026-03-01 00:00")
H = pd.Timedelta(hours=1)


def make_rdf(opens, labels=None, tag0=1.0):
    """Synthetic classify_series-shaped frame; 'atr' = tag identifies the source 4h bar."""
    n = len(opens)
    labels = labels or ["trend_up", "range", "trend_down", "volatile", "unclear"] * (n // 5 + 1)
    labels = labels[:n]
    df = pd.DataFrame({
        "regime": pd.Series(labels, dtype=object),
        "rh": [110.0 + i if l == "range" else NAN for i, l in enumerate(labels)],
        "rl": [100.0 + i if l == "range" else NAN for i, l in enumerate(labels)],
        "rh_touches": [3 if l == "range" else 0 for l in labels],
        "rl_touches": [2 if l == "range" else 0 for l in labels],
        "atr": [tag0 + i for i in range(n)],
        "atr_ratio": [1.0] * n,
    })
    df.index = pd.DatetimeIndex(opens)
    return df


def hourly(start, end):
    return pd.date_range(start, end, freq="h")


class TestAlignExamples:
    def setup_method(self):
        # 4h bars opening 00:00, 04:00, 08:00 (closing 04:00, 08:00, 12:00)
        self.r = make_rdf(pd.date_range(T0, periods=3, freq="4h"))
        self.out = align_to_base(self.r, hourly(T0, T0 + pd.Timedelta(hours=23)))

    def tag(self, hour):
        return self.out.loc[T0 + pd.Timedelta(hours=hour), "atr"]

    def label(self, hour):
        return self.out.loc[T0 + pd.Timedelta(hours=hour), "regime"]

    def test_columns_and_index(self):
        assert list(self.out.columns) == list(self.r.columns)
        assert self.out.index.equals(hourly(T0, T0 + pd.Timedelta(hours=23)))

    def test_before_first_close_is_unclear(self):
        # 4h bar 00:00 closes 04:00 ; 1h bars 00..03 have no usable bar
        for h in (0, 1, 2, 3):
            row = self.out.loc[T0 + h * H]
            assert row["regime"] == "unclear"
            assert math.isnan(row["rh"]) and math.isnan(row["rl"])
            assert row["rh_touches"] == 0 and row["rl_touches"] == 0

    def test_first_hour_after_close_exposes_label(self):
        # spec table: 1h bar opening exactly at C (equality allowed) uses that 4h bar
        assert self.tag(4) == 1.0     # bar 00:00 (tag 1.0) visible from 04:00
        assert self.tag(8) == 2.0     # bar 04:00 visible from 08:00
        assert self.tag(12) == 3.0    # bar 08:00 visible from 12:00

    def test_1h_bar_closing_with_the_4h_bar_still_uses_old_label(self):
        # 1h bar opening 07:00 closes 08:00 (same instant as 4h bar 04:00) -> still bar 00:00
        assert self.tag(7) == 1.0
        assert self.tag(11) == 2.0
        assert self.tag(3) != 1.0     # nothing yet

    def test_spec_table_block(self):
        for h in (4, 5, 6, 7):
            assert self.tag(h) == 1.0
        for h in (8, 9, 10, 11):
            assert self.tag(h) == 2.0
        for h in (12, 13, 14, 15):
            assert self.tag(h) == 3.0

    def test_stale_label_not_carried_beyond_one_4h_period(self):
        # newest 4h bar opens 08:00 (C=12:00): valid for T in [12,16); 16:00 -> T-C=4h -> stale
        assert self.label(15) == "volatile" or self.label(15) == self.r["regime"].iloc[2]
        for h in (16, 17, 20, 23):
            row = self.out.loc[T0 + h * H]
            assert row["regime"] == "unclear"
            assert math.isnan(row["rh"]) and row["rh_touches"] == 0

    def test_values_carried_not_recomputed(self):
        r = make_rdf(pd.date_range(T0, periods=3, freq="4h"), ["unclear", "range", "range"])
        out = align_to_base(r, hourly(T0, T0 + pd.Timedelta(hours=15)))
        # 08:00 1h bar -> bar 04:00 (range, rh=111, rl=101, touches 3/2, atr tag 2.0)
        row = out.loc[T0 + 8 * H]
        assert (row["regime"], row["rh"], row["rl"], row["rh_touches"], row["rl_touches"], row["atr"]) == \
            ("range", 111.0, 101.0, 3, 2, 2.0)
        # 12:00 -> bar 08:00 (rh=112, rl=102)
        row = out.loc[T0 + 12 * H]
        assert (row["rh"], row["rl"]) == (112.0, 102.0)

    def test_gap_in_4h_data_gives_unclear_not_carry(self):
        # 4h bars open 00:00, 04:00, (08:00 missing), 12:00 -> closes 04,08,(12),16
        opens = [T0, T0 + 4 * H, T0 + 12 * H]
        r = make_rdf(opens)
        out = align_to_base(r, hourly(T0, T0 + pd.Timedelta(hours=23)))
        # bar 04:00 valid on [08,12) ; at 12..15 the newest usable is bar 04:00 with T-C = 4..7h -> stale
        for h in (8, 9, 10, 11):
            assert out.loc[T0 + h * H, "atr"] == 2.0
        for h in (12, 13, 14, 15):
            assert out.loc[T0 + h * H, "regime"] == "unclear"
        # bar 12:00 closes 16:00 -> valid 16..19
        for h in (16, 17, 18, 19):
            assert out.loc[T0 + h * H, "atr"] == 3.0
        for h in (20, 21):
            assert out.loc[T0 + h * H, "regime"] == "unclear"

    def test_other_informative_hours(self):
        # 2h informative bars: C=O+2h, valid for T in [C, C+2h)
        r = make_rdf(pd.date_range(T0, periods=3, freq="2h"))
        out = align_to_base(r, hourly(T0, T0 + pd.Timedelta(hours=9)), informative_hours=2)
        assert out.loc[T0 + 1 * H, "regime"] == "unclear"
        assert out.loc[T0 + 2 * H, "atr"] == 1.0 and out.loc[T0 + 3 * H, "atr"] == 1.0
        assert out.loc[T0 + 4 * H, "atr"] == 2.0
        assert out.loc[T0 + 6 * H, "atr"] == 3.0 and out.loc[T0 + 7 * H, "atr"] == 3.0
        assert out.loc[T0 + 8 * H, "regime"] == "unclear"

    def test_timezone_mismatch_raises(self):
        r = make_rdf(pd.date_range(T0, periods=3, freq="4h"))
        base = pd.date_range(T0, periods=10, freq="h", tz="UTC")
        with pytest.raises(ValueError):
            align_to_base(r, base)

    def test_matching_tz_aware_works(self):
        r = make_rdf(pd.date_range(T0, periods=3, freq="4h", tz="UTC"))
        base = pd.date_range(T0, periods=16, freq="h", tz="UTC")
        out = align_to_base(r, base)
        assert out.loc[pd.Timestamp("2026-03-01 04:00", tz="UTC"), "atr"] == 1.0

    def test_input_not_mutated(self):
        r = make_rdf(pd.date_range(T0, periods=3, freq="4h"))
        before = r.copy()
        align_to_base(r, hourly(T0, T0 + pd.Timedelta(hours=11)))
        pd.testing.assert_frame_equal(r, before)

    def test_every_output_label_in_set(self):
        assert set(self.out["regime"]) <= LABELS


def _real_4h(seed=7, n=260):
    rng = np.random.default_rng(seed)
    r = rng.normal(0, 0.006, n)
    c = 100 * np.exp(np.cumsum(r))
    o = np.r_[c[0], c[:-1]]
    h = np.maximum(o, c) * (1 + np.abs(rng.normal(0, 0.003, n)))
    l = np.minimum(o, c) * (1 - np.abs(rng.normal(0, 0.003, n)))
    return ohlc(o, h, l, c, index=pd.date_range(T0, periods=n, freq="4h"))


def _expected_source(opens, base, hours=4):
    """Index into opens of the 4h bar a 1h bar may use, or None. Independent of implementation."""
    closes = opens + pd.Timedelta(hours=hours)
    out = []
    for T in base:
        idx = closes.searchsorted(T, side="right") - 1
        if idx < 0 or (T - closes[idx]) >= pd.Timedelta(hours=hours):
            out.append(None)
        else:
            out.append(idx)
    return out


class TestAlignNoLookahead:
    def test_c_pipeline_label_source_is_last_closed_4h_bar(self):
        d4 = _real_4h()
        reg = classify_series(d4)
        base = hourly(d4.index[0], d4.index[-1] + 3 * H)
        out = align_to_base(reg, base)
        src = _expected_source(d4.index, base)
        for T, s in zip(base, src):
            row = out.loc[T]
            if s is None:
                assert row["regime"] == "unclear"
            else:
                assert row["regime"] == reg["regime"].iloc[s]
                assert (row["atr"] == reg["atr"].iloc[s]) or (math.isnan(row["atr"]) and math.isnan(reg["atr"].iloc[s]))
                # never uses a 4h bar that has not closed by T
                assert d4.index[s] + 4 * H <= T

    def test_c_label_for_4h_bar_appears_only_at_or_after_its_close(self):
        d4 = _real_4h()
        reg = classify_series(d4)
        reg["atr"] = np.arange(len(reg), dtype=float)       # tag each 4h bar
        base = hourly(d4.index[0], d4.index[-1] + 3 * H)
        out = align_to_base(reg, base)
        for j in (0, 1, 50, 120, 200, 258):
            C = d4.index[j] + 4 * H
            seen = out.index[out["atr"] == float(j)]
            assert len(seen) == 4
            assert seen[0] == C                       # first exposure: 1h bar opening at C
            assert seen[-1] == C + 3 * H
            assert (seen >= C).all()

    def test_c_future_4h_bars_cannot_change_earlier_1h_rows(self):
        d4 = _real_4h()
        full4 = classify_series(d4)
        base = hourly(d4.index[0], d4.index[-1] + 3 * H)
        out_full = align_to_base(full4, base)
        for j in (30, 113, 114, 150, 200):
            # classify only the first j+1 4h bars (a live system would not have more)
            part4 = classify_series(d4.iloc[:j + 1])
            out_part = align_to_base(part4, base)
            limit = d4.index[j] + 8 * H                # C_{j+1}: first instant bar j+1 may be used
            early = base[base < limit]
            pd.testing.assert_frame_equal(out_part.loc[early], out_full.loc[early], check_exact=True)
            # and beyond the limit the truncated data may only yield unclear (stale), never a guess
            late = base[base >= limit]
            assert (out_part.loc[late, "regime"] == "unclear").all()

    def test_c_mutated_future_4h_bars_do_not_change_aligned_past(self):
        d4 = _real_4h()
        out_full = align_to_base(classify_series(d4), hourly(d4.index[0], d4.index[-1] + 3 * H))
        base = hourly(d4.index[0], d4.index[-1] + 3 * H)
        j = 150
        m = d4.copy()
        m.iloc[j + 1:] = m.iloc[j + 1:] * 5.0
        m.iloc[j + 3, :] = NAN
        out_m = align_to_base(classify_series(m), base)
        early = base[base < d4.index[j] + 8 * H]
        pd.testing.assert_frame_equal(out_m.loc[early], out_full.loc[early], check_exact=True)

    def test_output_index_is_base_index(self):
        d4 = _real_4h(n=130)
        base = hourly(d4.index[0] + 5 * H, d4.index[-1])
        out = align_to_base(classify_series(d4), base)
        assert out.index.equals(base)
        assert list(out.columns) == list(classify_series(d4).columns)


# ==========================================================================
# 8. seeded random-walk property tests (200 series)
# ==========================================================================
def gen_series(seed):
    rng = np.random.default_rng(10_000 + seed)
    kind = seed % 4
    n = int(rng.integers(60, 330)) if seed % 17 == 0 else int(rng.integers(120, 330))
    if kind == 0:      # plain random walk
        x = np.cumsum(rng.normal(0, rng.uniform(0.002, 0.012), n))
        wick = 0.5
    elif kind == 1:    # mean reverting, tight (range prone)
        s = rng.uniform(0.001, 0.004)
        x = np.zeros(n)
        for i in range(1, n):
            x[i] = 0.85 * x[i - 1] + rng.normal(0, s)
        wick = 1.0
    elif kind == 2:    # volatility bursts
        sig = np.where(rng.random(n) < 0.06, 0.05, 0.004)
        x = np.cumsum(rng.normal(0, 1, n) * sig)
        wick = 0.5
    else:              # drift + noise
        x = np.cumsum(rng.normal(rng.choice([-0.003, 0.003]), 0.004, n))
        wick = 0.5
    c = 100 * np.exp(x)
    o = np.r_[c[0], c[:-1]]
    s = 0.004
    h = np.maximum(o, c) * (1 + wick * np.abs(rng.normal(0, s, n)))
    l = np.minimum(o, c) * (1 - wick * np.abs(rng.normal(0, s, n)))
    return ohlc(o, h, l, c)


class TestRandomWalkProperties:
    N = 200

    def test_generator_produces_valid_candles(self):
        for seed in range(0, self.N, 11):
            d = gen_series(seed)
            assert (d["high"] >= d[["open", "close"]].max(axis=1)).all()
            assert (d["low"] <= d[["open", "close"]].min(axis=1)).all()
            assert (d["low"] > 0).all()

    def test_properties_200_series(self):
        seen = {k: 0 for k in LABELS}
        for seed in range(self.N):
            d = gen_series(seed)
            res = classify_series(d)
            n = len(d)
            # label-set / schema invariants
            assert len(res) == n and res.index.equals(d.index)
            assert set(res["regime"]) <= LABELS, seed
            assert not res["regime"].isna().any()
            for lab, cnt in res["regime"].value_counts().items():
                seen[lab] += int(cnt)
            # rows < 112 unclear
            assert (res["regime"].iloc[:112] == "unclear").all(), seed
            rng_rows = res[res["regime"] == "range"]
            if len(rng_rows):
                assert (rng_rows["rh"] > rng_rows["rl"]).all(), seed
                assert (rng_rows["rh_touches"] >= 2).all() and (rng_rows["rl_touches"] >= 2).all()
                assert ((rng_rows["rh"] - rng_rows["rl"]) <= 4.0 * rng_rows["atr"] * (1 + 1e-9)).all()
            non = res[res["regime"] != "range"]
            assert non["rh"].isna().all() and non["rl"].isna().all()
            assert (non["rh_touches"] == 0).all() and (non["rl_touches"] == 0).all()
            vol = res[res["regime"] == "volatile"]
            assert (vol["atr_ratio"] > 1.5).all()
            nonvol_ok = res[res["regime"].isin(["range", "trend_up", "trend_down"])]
            assert (nonvol_ok["atr_ratio"] <= 1.5).all()
            # no-lookahead (a): prefixes, several cut points per series
            rs = np.random.default_rng(seed)
            cuts = {1, 112, 113, n // 2, n - 1, int(rs.integers(1, n)), int(rs.integers(min(113, n - 1), n))}
            for k in sorted(c for c in cuts if 1 <= c <= n):
                assert_prefix_equal(d, res, k)
            # no-lookahead (b): wreck the future after a random t
            t = int(rs.integers(min(113, n - 2), n - 1))
            m = d.copy()
            m.iloc[t + 1:] = m.iloc[t + 1:].to_numpy() * rs.uniform(0.2, 5.0, size=(n - t - 1, 4))
            pd.testing.assert_frame_equal(classify_series(m).iloc[:t + 1], res.iloc[:t + 1], check_exact=True)
            # last-row convenience wrapper agrees with the series result
            assert classify_last(d).regime.value == res["regime"].iloc[-1]
        # the generator mix must exercise the main labels
        for lab in ("trend_up", "trend_down", "volatile", "unclear"):
            assert seen[lab] > 0, (lab, seen)

    def test_differential_against_oracle(self):
        seen = {k: 0 for k in LABELS}
        for seed in range(0, self.N, 2):
            d = gen_series(seed)
            res = classify_series(d)
            assert_matches_ref(d, res)
            for lab, cnt in res["regime"].value_counts().items():
                seen[lab] += int(cnt)
        assert seen["range"] > 0, seen
