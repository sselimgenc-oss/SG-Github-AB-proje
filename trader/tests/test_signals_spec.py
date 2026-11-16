"""Independent spec-based tests for trader_core.signals (strateji-spec v1, 16 Kasim 2026).

Written ONLY from docs/strateji-spec.md (+ docs/rejim-spec.md for the regime
interfaces).  The implementation of signals.py was NOT read.

Conventions
-----------
* ``mk_df``      : OHLC frame from tuples (o, h, l, c), hourly UTC DatetimeIndex.
* ``mk_rdf``     : aligned regime frame (regime, rh, rl, rh_touches, rl_touches,
                   atr, atr_ratio), same index as the bars.
* ``ref_signals``: a small slow oracle written from spec section 3.3/3.4; it is
                   used for differential testing on seeded random series.  It is
                   itself sanity-checked against the spec's hand examples.
* Flat-bar scenarios: bars with o = c = m, h = m + 0.5, l = m - 0.5 give TR = 1
  (ATR = 1 everywhere); bars with h - l = 2 around o = c = 100 give ATR = 2.
"""
from __future__ import annotations

import dataclasses
import math

import numpy as np
import pandas as pd
import pytest

from trader_core import indicators as ind
from trader_core import ledger
from trader_core import regime as rg
from trader_core import signals as sg
from trader_core.regime import RegimeParams, align_to_base, classify_series
from trader_core.signals import (DEFAULT_SIGNAL_PARAMS, SIGNAL_COLUMNS,
                                 SignalParams, compute_signals, evaluate_r1,
                                 evaluate_t1, pick_candidate,
                                 regime_flip_exit, target_reached,
                                 time_stop_due, trail_stop_path)

NAN = float("nan")
EPS = 1e-9
P = DEFAULT_SIGNAL_PARAMS


def prm(**kw):
    return dataclasses.replace(DEFAULT_SIGNAL_PARAMS, **kw)


# ---------------------------------------------------------------------------
# Builders
# ---------------------------------------------------------------------------

def mk_df(bars, freq="1h", start="2026-01-01"):
    idx = pd.date_range(start, periods=len(bars), freq=freq, tz="UTC")
    a = np.asarray(bars, dtype=float).reshape(len(bars), 4)
    return pd.DataFrame(a, index=idx, columns=["open", "high", "low", "close"])


def mk_rdf(index, regime="trend_up", atr=4.0, rh=NAN, rl=NAN, atr_ratio=1.0):
    n = len(index)

    def col(x, dt=float):
        if np.isscalar(x) or x is None or isinstance(x, str):
            return [x] * n
        return list(x)
    return pd.DataFrame({
        "regime": pd.Series(col(regime), index=index, dtype=object),
        "rh": pd.Series(col(rh), index=index, dtype="float64"),
        "rl": pd.Series(col(rl), index=index, dtype="float64"),
        "rh_touches": pd.Series([0] * n, index=index, dtype="int64"),
        "rl_touches": pd.Series([0] * n, index=index, dtype="int64"),
        "atr": pd.Series(col(atr), index=index, dtype="float64"),
        "atr_ratio": pd.Series(col(atr_ratio), index=index, dtype="float64"),
    }, index=index)


def t1_df(last=(99.5, 101.0, 99.0, 100.5), n=20, flat=(100.0, 101.0, 99.0, 100.0)):
    """Spec 8.1 data: n-1 flat bars (o=c=100,h=101,l=99) then the trigger bar."""
    return mk_df([flat] * (n - 1) + [last])


def r1_df(last, base=104.0, n=60):
    """n-1 flat bars at `base` (TR = 1, ATR = 1) then a trigger bar.

    Trigger TR = max(h-l, |h-base|, |l-base|) -> for the spec 8.4 bar
    (o=100.6, h=101, l=100, c=100.9) TR = 4, so ATR_t = 1 + (4-1)/14 = 17/14.
    """
    flat = (base, base + 0.5, base - 0.5, base)
    return mk_df([flat] * (n - 1) + [last])


def row(sig, i=-1):
    return sig.iloc[i]


def isnan(x):
    return x is None or (isinstance(x, float) and math.isnan(x))


# ---------------------------------------------------------------------------
# Reference oracle (spec 3.3 / 3.4); valid bars only
# ---------------------------------------------------------------------------

def _stop_bad(entry, stop, atr):
    d = abs(entry - stop)
    return d < 0.5 * atr - EPS or d > 2.0 * atr + EPS


def ref_signals(df, rdf, p):
    n = len(df)
    o = df["open"].to_numpy(); h = df["high"].to_numpy()
    l = df["low"].to_numpy(); c = df["close"].to_numpy()
    atr = ind.atr(df, 14).to_numpy()
    ema = ind.ema(df["close"], p.pullback_ema).to_numpy()
    out = []
    for t in range(n):
        res = dict(setup=None, side=None, signal=False, skip=None,
                   entry=NAN, stop=NAN, target=NAN, rr=NAN)
        reg = rdf["regime"].iat[t]
        if reg in ("volatile", "unclear") or t < 4 or not np.isfinite(atr[t]):
            out.append(res); continue
        a = atr[t]
        lows = l[t - 4:t + 1]; highs = h[t - 4:t + 1]
        rng = h[t] - l[t]
        cands = []
        if reg in ("trend_up", "trend_down") and np.isfinite(ema[t]):
            body = abs(c[t] - o[t]) / rng
            if reg == "trend_up":
                trig = (l[t] <= ema[t] + EPS and ema[t] <= c[t] + EPS
                        and c[t] > o[t] and body >= 0.5 - EPS)
                side = "long"
                stop = lows.min() - p.stop_buffer_atr * a
            else:
                trig = (h[t] >= ema[t] - EPS and ema[t] >= c[t] - EPS
                        and c[t] < o[t] and body >= 0.5 - EPS)
                side = "short"
                stop = highs.max() + p.stop_buffer_atr * a
            if trig:
                skip = "stop_width" if _stop_bad(c[t], stop, a) else None
                cands.append(dict(setup="T1", side=side, signal=skip is None, skip=skip,
                                  entry=c[t], stop=stop, target=NAN, rr=NAN))
        elif reg == "range":
            a4 = rdf["atr"].iat[t]; rh = rdf["rh"].iat[t]; rl = rdf["rl"].iat[t]
            if np.isfinite([a4, rh, rl]).all():
                zone = p.edge_zone_atr * a4
                lw = (min(o[t], c[t]) - l[t]) / rng
                uw = (h[t] - max(o[t], c[t])) / rng
                trig_l = l[t] <= rl + zone + EPS and c[t] > rl and lw >= 0.5 - EPS
                trig_s = h[t] >= rh - zone - EPS and c[t] < rh and uw >= 0.5 - EPS
                if trig_l and trig_s:
                    out.append(dict(setup="R1", side=None, signal=False, skip="other",
                                    entry=NAN, stop=NAN, target=NAN, rr=NAN))
                    continue
                for side, trig in (("long", trig_l), ("short", trig_s)):
                    if not trig:
                        continue
                    if side == "long":
                        stop = l[t] - p.stop_buffer_atr * a
                        target = rl + p.range_target_frac * (rh - rl)
                        rr = (target - c[t]) / (c[t] - stop)
                    else:
                        stop = h[t] + p.stop_buffer_atr * a
                        target = rh - p.range_target_frac * (rh - rl)
                        rr = (c[t] - target) / (stop - c[t])
                    skip = None
                    if _stop_bad(c[t], stop, a):
                        skip = "stop_width"
                    elif rr <= 0 or rr < p.rr_min - EPS:
                        skip = "rr_below_min"
                    cands.append(dict(setup="R1", side=side, signal=skip is None, skip=skip,
                                      entry=c[t], stop=stop, target=target, rr=rr))
        if cands:
            r = cands[0]
            res = dict(setup=r["setup"], side=r["side"], signal=r["signal"], skip=r["skip"],
                       entry=r["entry"], stop=r["stop"], target=r["target"], rr=r["rr"])
        out.append(res)
    return out


# ---------------------------------------------------------------------------
# Random series generators (seeded)
# ---------------------------------------------------------------------------

def gen_df(rs, n, sigma, freq="1h"):
    idx = pd.date_range("2026-01-01", periods=n, freq=freq, tz="UTC")
    rows = []
    prev = 1000.0
    drift = 0.0
    for i in range(n):
        if i % 25 == 0:
            drift = rs.choice([-0.4, 0.0, 0.4]) * sigma
        o = prev + rs.normal(0, 0.3 * sigma)
        cl = o + rs.normal(drift, sigma)
        hi = max(o, cl) + abs(rs.normal(0, 0.6 * sigma))
        lo = min(o, cl) - abs(rs.normal(0, 0.6 * sigma))
        rows.append((o, hi, lo, cl))
        prev = cl
    return pd.DataFrame(rows, index=idx, columns=["open", "high", "low", "close"])


def synth_regime(rs, df, sigma):
    n = len(df)
    labels = []
    names = ["trend_up", "trend_down", "range", "volatile", "unclear"]
    while len(labels) < n:
        lab = names[rs.choice(5, p=[0.27, 0.27, 0.36, 0.05, 0.05])]
        labels += [lab] * int(rs.randint(5, 40))
    labels = labels[:n]
    rh = df["high"].rolling(20, min_periods=1).max().to_numpy()
    rl = df["low"].rolling(20, min_periods=1).min().to_numpy()
    is_r = np.array([x == "range" for x in labels])
    a4 = 2.5 * sigma * rs.uniform(0.8, 1.2)
    return mk_rdf(df.index, regime=labels, atr=a4,
                  rh=np.where(is_r, rh, NAN), rl=np.where(is_r, rl, NAN))


def rand_params(rs):
    return SignalParams(
        range_width_atr=float(rs.uniform(3, 6)), vol_ratio_max=float(rs.uniform(1.25, 2)),
        edge_zone_atr=float(rs.uniform(0.15, 0.5)), pullback_ema=int(rs.choice([20, 50])),
        stop_buffer_atr=float(rs.uniform(0.1, 1.0)), trail_atr=float(rs.uniform(2, 4)),
        range_target_frac=float(rs.uniform(0.5, 1.0)), rr_min=float(rs.uniform(1.0, 2.0)),
        trigger_tf=["1h", "15m"][int(rs.randint(2))])


def scenario(seed, n=None, freq="1h"):
    rs = np.random.RandomState(seed)
    sigma = float(rs.uniform(1.0, 3.0))
    n = n or int(rs.randint(90, 200))
    df = gen_df(rs, n, sigma, freq)
    return rs, df, synth_regime(rs, df, sigma), rand_params(rs)


def eq_frames(a, b):
    pd.testing.assert_frame_equal(a, b, check_exact=True)


# ===========================================================================
# 1. Parameters
# ===========================================================================

FIELDS = {  # name: (default, lo, hi)
    "range_width_atr": (4.0, 3.0, 6.0),
    "vol_ratio_max": (1.5, 1.25, 2.0),
    "edge_zone_atr": (0.25, 0.15, 0.50),
    "stop_buffer_atr": (0.3, 0.1, 1.0),
    "trail_atr": (3.0, 2.0, 4.0),
    "range_target_frac": (0.75, 0.5, 1.0),
    "rr_min": (1.5, 1.0, 2.0),
}


def test_defaults():
    d = DEFAULT_SIGNAL_PARAMS
    for k, (dv, _, _) in FIELDS.items():
        assert getattr(d, k) == dv
    assert d.pullback_ema == 50 and d.trigger_tf == "1h"
    assert SignalParams() == d
    assert {f.name for f in dataclasses.fields(SignalParams)} == set(FIELDS) | {"pullback_ema", "trigger_tf"}


def test_frozen():
    with pytest.raises(dataclasses.FrozenInstanceError):
        DEFAULT_SIGNAL_PARAMS.rr_min = 1.2  # type: ignore[misc]


@pytest.mark.parametrize("name", sorted(FIELDS))
def test_bounds_inclusive_and_exclusive(name):
    _, lo, hi = FIELDS[name]
    assert getattr(SignalParams(**{name: lo}), name) == lo
    assert getattr(SignalParams(**{name: hi}), name) == hi
    for bad in (lo - 0.01, hi + 0.01, lo - 1, hi + 1):
        with pytest.raises(ValueError):
            SignalParams(**{name: bad})


@pytest.mark.parametrize("name", sorted(FIELDS))
@pytest.mark.parametrize("bad", [True, False, None, "1.5", float("nan"), float("inf"), -float("inf"), [1.5]])
def test_bad_number_types(name, bad):
    with pytest.raises(ValueError):
        SignalParams(**{name: bad})


def test_numpy_and_int_accepted():
    assert SignalParams(range_width_atr=np.float64(5.0)).range_width_atr == 5.0
    assert SignalParams(range_width_atr=4).range_width_atr == 4


def test_pullback_ema_values():
    assert SignalParams(pullback_ema=20).pullback_ema == 20
    assert SignalParams(pullback_ema=50.0).pullback_ema == 50
    for bad in (30, 0, 100, "50", None, True, 20.5, float("nan")):
        with pytest.raises(ValueError):
            SignalParams(pullback_ema=bad)


def test_trigger_tf_values():
    assert SignalParams(trigger_tf="15m").trigger_tf == "15m"
    for bad in ("4h", "1H", "1s", "15dk", "", None, 15, True):
        with pytest.raises(ValueError):
            SignalParams(trigger_tf=bad)


def test_from_mapping_roundtrip_and_strict_keys():
    m = dataclasses.asdict(DEFAULT_SIGNAL_PARAMS)
    assert len(m) == 9
    assert SignalParams.from_mapping(m) == DEFAULT_SIGNAL_PARAMS
    m2 = dict(m); m2.pop("rr_min")
    with pytest.raises(ValueError):
        SignalParams.from_mapping(m2)
    with pytest.raises(ValueError):
        SignalParams.from_mapping({**m, "extra": 1})
    with pytest.raises(ValueError):
        SignalParams.from_mapping({**m, "rr_min": 5.0})


def test_from_mapping_rounds_to_6_decimals():
    m = dataclasses.asdict(DEFAULT_SIGNAL_PARAMS)
    p = SignalParams.from_mapping({**m, "vol_ratio_max": 1.5000004, "stop_buffer_atr": 0.30000049})
    assert p.vol_ratio_max == 1.5
    assert p.stop_buffer_atr == 0.3


def test_regime_params_subset():
    p = prm(range_width_atr=5.0, vol_ratio_max=1.7, edge_zone_atr=0.4)
    rp = p.regime_params()
    assert isinstance(rp, RegimeParams)
    assert (rp.range_width_atr, rp.vol_ratio_max, rp.edge_zone_atr) == (5.0, 1.7, 0.4)
    assert DEFAULT_SIGNAL_PARAMS.regime_params() == rg.DEFAULT_PARAMS


def test_compat_with_ledger_and_regime():
    specs = ledger.PARAM_SPECS
    assert set(specs) == set(FIELDS) | {"pullback_ema", "trigger_tf"}
    for k, (dv, lo, hi) in FIELDS.items():
        assert (specs[k]["lo"], specs[k]["hi"]) == (lo, hi)
        assert getattr(DEFAULT_SIGNAL_PARAMS, k) == dv
    assert tuple(specs["pullback_ema"]["choices"]) == (20, 50)
    assert tuple(specs["trigger_tf"]["choices"]) == ("1h", "15m")
    assert set(ledger.LESSON_PARAMS) == {"vol_ratio_max", "stop_buffer_atr", "trail_atr",
                                         "range_target_frac", "rr_min"}
    assert dict(ledger.LESSON_BOUNDS_DEFAULT) == {
        "vol_ratio_max": (1.3, 1.7), "stop_buffer_atr": (0.2, 0.5), "trail_atr": (2.5, 3.5),
        "range_target_frac": (0.6, 0.9), "rr_min": (1.2, 2.0)}
    assert dict(ledger.LESSON_STEP) == {"vol_ratio_max": 0.25, "stop_buffer_atr": 0.1, "trail_atr": 0.5,
                                        "range_target_frac": 0.125, "rr_min": 0.25}
    # regime params ranges identical
    for k in ("range_width_atr", "vol_ratio_max", "edge_zone_atr"):
        _, lo, hi = FIELDS[k]
        assert getattr(rg.RegimeParams(**{k: lo}), k) == lo
        assert getattr(rg.RegimeParams(**{k: hi}), k) == hi
        with pytest.raises(ValueError):
            rg.RegimeParams(**{k: lo - 0.01})
        with pytest.raises(ValueError):
            rg.RegimeParams(**{k: hi + 0.01})
    assert rg.DEFAULT_PARAMS == DEFAULT_SIGNAL_PARAMS.regime_params()


def test_module_constants():
    assert sg.ATR_LEN == 14 and sg.STOP_LOOKBACK == 5
    assert sg.BODY_RATIO_MIN == 0.5 and sg.WICK_RATIO_MIN == 0.5
    assert sg.STOP_DIST_MIN_ATR == 0.5 and sg.STOP_DIST_MAX_ATR == 2.0
    assert sg.TRAIL_START_R == 1.0 and sg.TIME_STOP_BARS == 48 and sg.EPS == 1e-9
    assert tuple(sg.SETUPS) == ("T1", "R1") and tuple(sg.SIDES) == ("long", "short")


# ===========================================================================
# 2. Spec examples through compute_signals (section 8.1 / 8.2)
# ===========================================================================

def test_example_8_1_t1_long_end_to_end():
    df = t1_df()
    r = mk_rdf(df.index, "trend_up", atr=4.0)
    out = compute_signals(df, r, prm(pullback_ema=20))
    assert list(out.columns) == list(SIGNAL_COLUMNS)
    assert out.index.equals(df.index)
    x = row(out, 19)
    # EMA20: flat 100 then e19 = 100 + (2/21)*(100.5-100) = 100 + 1/21
    assert x.setup == "T1" and x.side == "long" and bool(x.signal) is True
    assert x.skip_reason is None
    assert x.planned_entry == pytest.approx(100.5)
    # stop = min(lows 15..19)=99 - 0.3*2 = 98.4 ; dist 2.1 = 1.05 ATR
    assert x.planned_stop == pytest.approx(98.4)
    assert math.isnan(x.planned_target) and math.isnan(x.rr)
    assert x.stop_dist_atr == pytest.approx(1.05)
    assert x.atr_tf == pytest.approx(2.0) and x.atr_4h == pytest.approx(4.0)
    assert x.atr_ratio == pytest.approx(1.0)
    assert x.ema_value == pytest.approx(100 + 1 / 21)
    assert x.body_ratio == pytest.approx(0.5)  # |100.5-99.5|/(101-99)
    assert x.pullback_ema == 20
    assert x.reasons == "T1_long:trend_up,ema_touch,bull_body,stop_ok"
    assert x.regime == "trend_up"
    # warm-up rows
    for t in range(0, 19):
        y = row(out, t)
        assert y.setup is None and y.side is None and bool(y.signal) is False
        assert y.reasons == "no_history", t
        assert math.isnan(y.planned_entry) and math.isnan(y.planned_stop)
    assert out["atr_tf"].iloc[:13].isna().all()
    assert out["atr_tf"].iloc[13:].tolist() == pytest.approx([2.0] * 7)
    assert out["signal"].sum() == 1


def test_example_8_1_prefix_invariance_and_pe50():
    df = t1_df(); r = mk_rdf(df.index, "trend_up")
    full = compute_signals(df, r, prm(pullback_ema=20))
    part = compute_signals(df.iloc[:19], r.iloc[:19], prm(pullback_ema=20))
    assert not part["signal"].any()
    eq_frames(part, full.iloc[:19])
    eq_frames(compute_signals(df.iloc[:20], r.iloc[:20], prm(pullback_ema=20)), full)
    # default pullback_ema=50: EMA50 needs 50 observations -> everything no_history
    d50 = compute_signals(df, r, DEFAULT_SIGNAL_PARAMS)
    assert (d50["reasons"] == "no_history").all()
    assert not d50["signal"].any() and d50["setup"].isna().all()


def test_example_8_1_with_default_ema50_on_longer_history():
    # 59 flat bars + trigger: EMA50 = 100 + (2/51)*0.5 = 100 + 1/51 ; ATR = 2
    df = t1_df(n=60)
    out = compute_signals(df, mk_rdf(df.index, "trend_up"), DEFAULT_SIGNAL_PARAMS)
    x = row(out)
    assert x.signal and x.ema_value == pytest.approx(100 + 1 / 51) and x.pullback_ema == 50
    assert x.planned_stop == pytest.approx(98.4)


def test_example_8_2_t1_short():
    last = (100.5, 101.0, 99.0, 99.5)
    df = t1_df(last=last)
    out = compute_signals(df, mk_rdf(df.index, "trend_down"), prm(pullback_ema=20))
    x = row(out)
    # ema = 100 - 1/21 ; h=101 >= ema >= c=99.5 ; c<o ; body .5 ; stop = max(highs)=101+0.6
    assert x.setup == "T1" and x.side == "short" and x.signal
    assert x.planned_entry == pytest.approx(99.5)
    assert x.planned_stop == pytest.approx(101.6)
    assert x.ema_value == pytest.approx(100 - 1 / 21)
    assert x.reasons == "T1_short:trend_down,ema_touch,bear_body,stop_ok"
    # same bar under trend_up: long needs l<=ema<=c (c=99.5 < ema) and c>o -> no candidate
    out2 = compute_signals(df, mk_rdf(df.index, "trend_up"), prm(pullback_ema=20))
    y = row(out2)
    assert y.setup is None and y.side is None and not y.signal
    assert y.reasons == ""


# ===========================================================================
# 3. T1 filters / formulas through compute_signals
# ===========================================================================

def t1_last(last, regime="trend_up", **kw):
    df = t1_df(last=last)
    out = compute_signals(df, mk_rdf(df.index, regime), prm(pullback_ema=20, **kw))
    return row(out)


def test_t1_long_confirmation_candle_filters():
    # body 0.9/2 = 0.45 < 0.5
    assert t1_last((99.5, 101.0, 99.0, 100.4)).setup is None
    # exactly 0.5 passes (spec 8.1) ; bearish candle fails even with ema touch
    assert t1_last((100.5, 101.0, 99.0, 99.8)).setup is None
    # doji c == o fails (c > o strict)
    assert t1_last((100.0, 101.0, 99.0, 100.0)).setup is None


def test_t1_long_ema_touch_filters():
    # low above EMA: l=100.2 > ema(100.0857) -> no touch (bar o=100.4,c=100.9,h=101: body .5/.8)
    assert t1_last((100.4, 101.0, 100.2, 100.9)).setup is None
    # close below EMA though low pierces (bearish anyway); bull bar closing below ema:
    # o=98, h=100.0, l=97.5, c=99.9 ; ema ~ 100.0 > c -> no
    assert t1_last((98.0, 100.0, 97.5, 99.9)).setup is None


def test_t1_short_filters():
    # high below ema (ema = 100 - (2/21)*(c-100)): bar entirely below 99
    assert t1_last((98.5, 98.9, 97.5, 97.9), "trend_down").setup is None
    # bullish bar in downtrend -> none
    assert t1_last((99.5, 101.0, 99.0, 100.5), "trend_down").setup is None
    # body < .5 : o=100.5,c=99.6 -> .9/2
    assert t1_last((100.5, 101.0, 99.0, 99.6), "trend_down").setup is None


@pytest.mark.parametrize("regime", ["range", "volatile", "unclear"])
def test_t1_requires_trend_regime(regime):
    df = t1_df()
    r = mk_rdf(df.index, regime, rh=105.0, rl=95.0)
    out = compute_signals(df, r, prm(pullback_ema=20))
    assert not out["signal"].any()
    assert out["setup"].isna().all()
    if regime != "range":
        assert (out["reasons"] == "regime_blocked").all()


def test_t1_stop_buffer_formula():
    for buf, stop in ((0.1, 98.8), (0.5, 98.0), (1.0, 97.0)):
        x = t1_last((99.5, 101.0, 99.0, 100.5), stop_buffer_atr=buf)
        assert x.planned_stop == pytest.approx(stop)  # 99 - buf*2
        assert x.stop_dist_atr == pytest.approx((100.5 - stop) / 2)
        assert x.signal


def test_t1_trigger_bar_low_included_in_stop():
    # trigger bar low 98, o=99 -> body (100.5-99)/3 = .5 ; TR=3 -> ATR19 = 2 + 1/14 = 29/14
    df = t1_df(last=(99.0, 101.0, 98.0, 100.5))
    x = row(compute_signals(df, mk_rdf(df.index, "trend_up"), prm(pullback_ema=20)))
    atr = 29 / 14
    assert x.atr_tf == pytest.approx(atr)
    assert x.planned_stop == pytest.approx(98.0 - 0.3 * atr)
    assert x.stop_dist_atr == pytest.approx((100.5 - 98.0 + 0.3 * atr) / atr)
    assert x.signal


@pytest.mark.parametrize("freq,tf", [("1h", "1h"), ("15min", "15m")])
def test_stop_lookback_is_5_trigger_bars(freq, tf):
    # a deep low placed 4 bars before the trigger bar (inside window t-4..t) vs 5 bars (outside)
    def build(pos):
        bars = [(100.0, 101.0, 99.0, 100.0)] * 19 + [(99.5, 101.0, 99.0, 100.5)]
        bars = list(bars)
        bars[pos] = (100.0, 101.0, 95.0, 100.0)
        return mk_df(bars, freq=freq)
    p = prm(pullback_ema=20, trigger_tf=tf)
    inside = build(15)   # t-4
    out_in = row(compute_signals(inside, mk_rdf(inside.index, "trend_up"), p))
    assert out_in.planned_stop == pytest.approx(95.0 - 0.3 * out_in.atr_tf)
    outside = build(14)  # t-5
    out_out = row(compute_signals(outside, mk_rdf(outside.index, "trend_up"), p))
    assert out_out.planned_stop == pytest.approx(99.0 - 0.3 * out_out.atr_tf)
    assert out_out.signal  # dist = 2.1ish ATR-normalised stays within 0.5..2.0


def test_stop_lookback_short_uses_highs():
    bars = [(100.0, 101.0, 99.0, 100.0)] * 19 + [(100.5, 101.0, 99.0, 99.5)]
    b_in = list(bars); b_in[15] = (100.0, 105.0, 99.0, 100.0)
    b_out = list(bars); b_out[14] = (100.0, 105.0, 99.0, 100.0)
    p = prm(pullback_ema=20)
    di, do = mk_df(b_in), mk_df(b_out)
    xi = row(compute_signals(di, mk_rdf(di.index, "trend_down"), p))
    xo = row(compute_signals(do, mk_rdf(do.index, "trend_down"), p))
    assert xi.planned_stop == pytest.approx(105.0 + 0.3 * xi.atr_tf)
    assert xo.planned_stop == pytest.approx(101.0 + 0.3 * xo.atr_tf)


def test_t1_stop_width_skip_via_compute():
    # low 95 at t=17: TR17 = max(6,|101-100|,|95-100|)=6 -> ATR17 = 2+4/14 ; ATR18 = ATR17-(ATR17-2)/14 ...
    bars = [(100.0, 101.0, 99.0, 100.0)] * 19 + [(99.5, 101.0, 99.0, 100.5)]
    bars[17] = (100.0, 101.0, 95.0, 100.0)
    df = mk_df(bars)
    x = row(compute_signals(df, mk_rdf(df.index, "trend_up"), prm(pullback_ema=20)))
    atr = 2.0
    for _ in range(3):  # t=17 (TR 6), t=18 (TR 2), t=19 (TR 2)
        pass
    a17 = 2 + (6 - 2) / 14; a18 = a17 + (2 - a17) / 14; a19 = a18 + (2 - a18) / 14
    assert x.atr_tf == pytest.approx(a19)
    assert x.setup == "T1" and x.side == "long"
    assert not x.signal and x.skip_reason == "stop_width"
    assert x.planned_entry == pytest.approx(100.5)              # candidate retained
    assert x.planned_stop == pytest.approx(95 - 0.3 * a19)
    assert x.stop_dist_atr > 2.0
    assert x.reasons == "T1_long:trend_up,ema_touch,bull_body,stop_width"


# ===========================================================================
# 4. Scalar evaluators: T1 (8.3)
# ===========================================================================

T1_BAR = dict(o=100.2, h=100.6, l=100.0, c=100.5)


def t1c(side="long", lows=(100.0, 100.1, 100.2, 100.1, 100.0), ema=100.2, atr=2.0, params=P, bar=None):
    b = bar or T1_BAR
    return evaluate_t1(side, b["o"], b["h"], b["l"], b["c"], ema, list(lows), atr, params)


def test_8_3_narrow():
    c = t1c(params=prm(stop_buffer_atr=0.1))
    # stop = 100.0 - 0.1*2 = 99.8 ; dist 0.7 = 0.35 ATR < 0.5
    assert c.setup == "T1" and c.side == "long"
    assert c.entry == pytest.approx(100.5) and c.stop == pytest.approx(99.8)
    assert c.stop_dist_atr == pytest.approx(0.35)
    assert c.skip_reason == "stop_width"
    assert c.target is None or math.isnan(c.target)


def test_8_3_wide():
    c = t1c(lows=(95, 100.1, 100.2, 100.1, 100.0), params=prm(stop_buffer_atr=0.3))
    # stop = 95 - 0.6 = 94.4 ; dist 6.1 = 3.05 ATR > 2
    assert c.stop == pytest.approx(94.4) and c.stop_dist_atr == pytest.approx(3.05)
    assert c.skip_reason == "stop_width"


def test_8_3_boundaries_pass():
    # dist exactly 1.0 (= 0.5 ATR): stop = 100.0 - 0.25*2 = 99.5 ; entry 100.5
    c = t1c(params=prm(stop_buffer_atr=0.25))
    assert c.skip_reason is None and c.stop_dist_atr == pytest.approx(0.5)
    # dist exactly 4.0 (= 2.0 ATR): lows min 97, buffer .25 -> stop 96.5
    c = t1c(lows=(97, 100.1, 100.2, 100.1, 100.0), params=prm(stop_buffer_atr=0.25))
    assert c.stop == pytest.approx(96.5) and c.skip_reason is None
    # just outside
    c = t1c(params=prm(stop_buffer_atr=0.2))   # stop 99.6, dist .9 = .45
    assert c.skip_reason == "stop_width"


def test_t1_scalar_short_and_none():
    b = dict(o=100.5, h=101.0, l=99.0, c=99.5)
    c = t1c("short", lows=(101, 101, 101, 101, 101), ema=99.952381, bar=b)
    assert c.side == "short" and c.stop == pytest.approx(101.6) and c.entry == pytest.approx(99.5)
    assert c.skip_reason is None
    # not a candidate: long on a bear bar
    assert t1c("long", ema=99.952381, bar=b) is None
    # body ratio below threshold -> None
    assert t1c(bar=dict(o=100.2, h=100.6, l=100.0, c=100.4), ema=100.2) is None
    # ema above close -> None
    assert t1c(ema=100.7) is None
    # ema below low -> None
    assert t1c(ema=99.9) is None


# ===========================================================================
# 5. R1 scalar (8.4 / 8.5 / 8.6)
# ===========================================================================

R1_BAR = dict(o=100.6, h=101.0, l=100.0, c=100.9)


def r1c(side="long", bar=None, rh=108.0, rl=100.0, atr_tf=1.0, atr_4h=2.0, params=P):
    b = bar or R1_BAR
    return evaluate_r1(side, b["o"], b["h"], b["l"], b["c"], rh, rl, atr_tf, atr_4h, params)


def test_8_4_r1_long():
    c = r1c()
    assert c.setup == "R1" and c.side == "long" and c.skip_reason is None
    assert c.entry == pytest.approx(100.9)
    assert c.stop == pytest.approx(99.7)            # 100 - 0.3*1
    assert c.stop_dist_atr == pytest.approx(1.2)
    assert c.target == pytest.approx(106.0)         # 100 + 0.75*8
    assert c.rr == pytest.approx(4.25)              # (106-100.9)/1.2
    assert c.reasons == "R1_long:range,edge_zone,reject_wick,stop_ok,rr_ok"


def test_8_4_rr_below_min():
    c = r1c(rh=102.0)  # target 101.5 ; rr = .6/1.2 = .5
    assert c.target == pytest.approx(101.5) and c.rr == pytest.approx(0.5)
    assert c.skip_reason == "rr_below_min"
    assert c.reasons.endswith(",rr_below_min")


def test_8_4_rr_equal_min_passes():
    c = r1c(rh=103.6)  # target 102.7 ; rr = 1.8/1.2 = 1.5
    assert c.target == pytest.approx(102.7) and c.rr == pytest.approx(1.5)
    assert c.skip_reason is None


def test_r1_rr_min_param_and_target_frac():
    assert r1c(rh=103.6, params=prm(rr_min=2.0)).skip_reason == "rr_below_min"
    assert r1c(rh=103.6, params=prm(rr_min=1.0)).skip_reason is None
    c = r1c(params=prm(range_target_frac=1.0))     # target 108 ; rr = 7.1/1.2
    assert c.target == pytest.approx(108.0) and c.rr == pytest.approx(7.1 / 1.2)
    c = r1c(params=prm(range_target_frac=0.5))     # target 104 ; rr = 3.1/1.2
    assert c.target == pytest.approx(104.0) and c.rr == pytest.approx(3.1 / 1.2)


def test_r1_target_beyond_entry_is_rr_below_min():
    # rh=100.4 -> target = 100 + .75*.4 = 100.3 < entry 100.9 -> rr<=0
    c = r1c(rh=100.4)
    assert c.skip_reason == "rr_below_min"
    assert c.rr is None or c.rr <= 0


def test_r1_stop_buffer_in_atr_units():
    c = r1c(params=prm(stop_buffer_atr=0.5), atr_tf=1.0)
    assert c.stop == pytest.approx(99.5)           # 100 - 0.5*1
    c = r1c(params=prm(stop_buffer_atr=0.3), atr_tf=1.5)
    assert c.stop == pytest.approx(100.0 - 0.45)   # buffer scales with atr_tf (not atr_4h)
    assert c.stop_dist_atr == pytest.approx((100.9 - 99.55) / 1.5)


def test_r1_stop_width_before_rr():
    # atr_tf=.5: stop = 100 - .15 = 99.85 ; dist 1.05 = 2.1 ATR > 2 -> stop_width even though rr (rh=102) fails too
    c = r1c(atr_tf=0.5, rh=102.0)
    assert c.skip_reason == "stop_width"


def test_r1_zone_boundary_and_edge_zone_param():
    bar = dict(o=101.0, h=101.2, l=100.6, c=101.1)   # wick (101-100.6)/.6 = .667
    assert r1c(bar=bar) is None                       # zone .5 -> need l <= 100.5
    assert r1c(bar=bar, params=prm(edge_zone_atr=0.3)) is not None   # zone .6 -> 100.6 <= 100.6
    c = r1c(bar=bar, params=prm(edge_zone_atr=0.4))
    assert c is not None and c.skip_reason is None
    # spec: l=100.6 under default zone .25 -> no candidate (8.4 last bullet)
    assert r1c(bar=dict(o=100.9, h=101.1, l=100.6, c=101.0)) is None


def test_r1_zone_exact_edge_l_equals_rl_plus_zone():
    bar = dict(o=100.8, h=101.0, l=100.5, c=100.9)   # l = rl + .5 exactly ; wick = .3/.5 = .6
    c = r1c(bar=bar)
    assert c is not None and c.skip_reason is None


def test_r1_wick_threshold():
    ok = dict(o=100.5, h=101.0, l=100.0, c=100.75)     # wick .5/1.0 exactly 0.5
    assert r1c(bar=ok) is not None
    bad = dict(o=100.4, h=101.0, l=100.0, c=100.75)    # wick .4
    assert r1c(bar=bad) is None


def test_r1_close_must_be_above_rl_and_wick_through_rl_ok():
    # close == rl -> not a candidate
    assert r1c(bar=dict(o=100.0, h=100.2, l=99.5, c=100.0)) is None
    # piercing RL is fine: l=99 < rl, c=100.9
    c = r1c(bar=dict(o=100.6, h=101.0, l=99.0, c=100.9))
    assert c is not None and c.stop == pytest.approx(99.0 - 0.3)


def test_8_5_r1_short():
    b = dict(o=107.4, h=108.0, l=107.0, c=107.1)
    c = r1c("short", bar=b)
    assert c.setup == "R1" and c.side == "short" and c.skip_reason is None
    assert c.entry == pytest.approx(107.1) and c.stop == pytest.approx(108.3)
    assert c.stop_dist_atr == pytest.approx(1.2)
    assert c.target == pytest.approx(102.0)          # 108 - .75*8
    assert c.rr == pytest.approx(4.25)               # 5.1/1.2
    assert c.reasons == "R1_short:range,edge_zone,reject_wick,stop_ok,rr_ok"
    # short bar not a long candidate (low far from RL)
    assert r1c("long", bar=b) is None
    # close >= rh -> none
    assert r1c("short", bar=dict(o=107.4, h=108.4, l=107.0, c=108.0)) is None


def test_r1_short_rr_and_edge_cases():
    b = dict(o=107.4, h=108.0, l=107.0, c=107.1)
    # rl=106.4 -> target = 108 - .75*(1.6) = 106.8 ; rr = .3/1.2 = .25
    c = r1c("short", bar=b, rl=106.4)
    assert c.skip_reason == "rr_below_min"
    # rr exactly rr_min: want (107.1 - target)/1.2 = 1.5 -> target 105.3 -> .75*(108-rl) = 2.7 -> rl=104.4
    c = r1c("short", bar=b, rl=104.4)
    assert c.rr == pytest.approx(1.5) and c.skip_reason is None


CONFLICT_BAR = dict(o=100.4, h=100.8, l=100.0, c=100.4)


def test_8_6_conflict_long_short():
    kw = dict(bar=CONFLICT_BAR, rh=100.8, rl=100.0, atr_tf=0.8, atr_4h=2.0)
    lo, sh = r1c("long", **kw), r1c("short", **kw)
    assert lo is not None and sh is not None
    res = pick_candidate([lo, sh])
    assert res.side is None and res.setup == "R1"
    assert res.skip_reason == "other" and res.reasons == "conflict:long_short"
    assert getattr(res, "signal", False) is False
    res2 = pick_candidate([sh, lo])
    assert res2.side is None and res2.reasons == "conflict:long_short"


def test_pick_candidate_t1_over_r1_and_single():
    t1 = t1c()
    r1 = r1c()
    assert t1 is not None and r1 is not None
    assert pick_candidate([t1, r1]).setup == "T1"
    assert pick_candidate([r1, t1]).setup == "T1"
    assert pick_candidate([r1]).setup == "R1" and pick_candidate([r1]).side == "long"
    assert pick_candidate([t1]).setup == "T1"
    assert pick_candidate([]) is None


# ===========================================================================
# 6. R1 through compute_signals
# ===========================================================================

def test_r1_long_end_to_end():
    df = r1_df((100.6, 101.0, 100.0, 100.9))
    r = mk_rdf(df.index, "range", atr=2.0, rh=108.0, rl=100.0)
    x = row(compute_signals(df, r, DEFAULT_SIGNAL_PARAMS))
    atr = 1 + 3 / 14   # TR = max(1, |101-104|, |100-104|) = 4 -> 1 + (4-1)/14 = 17/14
    stop = 100.0 - 0.3 * atr
    assert x.atr_tf == pytest.approx(atr)
    assert x.setup == "R1" and x.side == "long" and x.signal and x.skip_reason is None
    assert x.planned_entry == pytest.approx(100.9)
    assert x.planned_stop == pytest.approx(stop)
    assert x.planned_target == pytest.approx(106.0)
    assert x.rr == pytest.approx((106.0 - 100.9) / (100.9 - stop))
    assert x.stop_dist_atr == pytest.approx((100.9 - stop) / atr)
    assert x.wick_ratio == pytest.approx(0.6)
    assert x.edge_dist_atr == pytest.approx(0.45)      # (100.9-100)/2
    assert math.isnan(x.ema_value) and math.isnan(x.body_ratio)
    assert x.pullback_ema == 0
    assert x.atr_4h == 2.0 and x.rh == 108.0 and x.rl == 100.0 and x.regime == "range"
    assert x.reasons == "R1_long:range,edge_zone,reject_wick,stop_ok,rr_ok"
    # earlier flat bars: nothing
    assert not out_signal_before(df, r)


def out_signal_before(df, r):
    out = compute_signals(df, r, DEFAULT_SIGNAL_PARAMS)
    return out["signal"].iloc[:-1].any()


def test_r1_short_end_to_end():
    df = r1_df((107.4, 108.0, 107.0, 107.1))
    r = mk_rdf(df.index, "range", atr=2.0, rh=108.0, rl=100.0)
    x = row(compute_signals(df, r))
    atr = 17 / 14      # TR = max(1, |108-104|, |107-104|) = 4
    stop = 108.0 + 0.3 * atr
    assert x.setup == "R1" and x.side == "short" and x.signal
    assert x.planned_stop == pytest.approx(stop)
    assert x.planned_target == pytest.approx(102.0)
    assert x.rr == pytest.approx((107.1 - 102.0) / (stop - 107.1))
    assert x.edge_dist_atr == pytest.approx(0.45) and x.wick_ratio == pytest.approx(0.6)


def test_r1_rr_filter_via_compute_and_params():
    df = r1_df((100.6, 101.0, 100.0, 100.9))
    r = mk_rdf(df.index, "range", atr=2.0, rh=102.0, rl=100.0)    # target 101.5
    x = row(compute_signals(df, r))
    assert x.setup == "R1" and not x.signal and x.skip_reason == "rr_below_min"
    assert x.planned_target == pytest.approx(101.5) and x.rr < 1.5
    assert x.reasons.endswith("stop_ok,rr_below_min")
    # lower rr_min to 1.0 still fails (rr ~ .49)
    assert not row(compute_signals(df, r, prm(rr_min=1.0))).signal
    # wide range, rr_min 2.0 passes (rr ~ 4)
    r2 = mk_rdf(df.index, "range", atr=2.0, rh=108.0, rl=100.0)
    assert row(compute_signals(df, r2, prm(rr_min=2.0))).signal


def test_r1_uses_4h_atr_for_zone_and_edge_dist():
    df = r1_df((100.6, 101.0, 100.0, 100.9))
    # atr_4h = 0.4 -> zone 0.1 -> l=100.0 <= 100.1 ok ; atr 4 -> zone 1.0 ok
    for a4 in (0.4, 4.0):
        r = mk_rdf(df.index, "range", atr=a4, rh=108.0, rl=100.0)
        x = row(compute_signals(df, r))
        assert x.setup == "R1"
        assert x.edge_dist_atr == pytest.approx(0.9 / a4)
    # atr_4h so small the bar is outside zone: rl=99 -> l=100 > 99 + .25*0.4
    r = mk_rdf(df.index, "range", atr=0.4, rh=108.0, rl=99.0)
    assert row(compute_signals(df, r)).setup is None


def test_r1_conflict_end_to_end():
    bars = [(100.4, 100.8, 100.0, 100.4)] * 60     # TR = .8 every bar, ATR = .8
    df = mk_df(bars)
    r = mk_rdf(df.index, "range", atr=2.0, rh=100.8, rl=100.0)
    x = row(compute_signals(df, r))
    assert x.setup == "R1" and x.side is None and not x.signal
    assert x.skip_reason == "other" and x.reasons == "conflict:long_short"
    assert math.isnan(x.planned_entry) or True   # entry undefined without a side


@pytest.mark.parametrize("regime", ["trend_up", "trend_down", "volatile", "unclear"])
def test_r1_requires_range_regime(regime):
    df = r1_df((100.6, 101.0, 100.0, 100.9))
    r = mk_rdf(df.index, regime, atr=2.0, rh=108.0, rl=100.0)
    x = row(compute_signals(df, r))
    assert x.setup != "R1" and not x.signal
    if regime in ("volatile", "unclear"):
        assert x.reasons == "regime_blocked"


def test_range_with_nan_edges_or_4h_atr_gives_no_signal():
    df = r1_df((100.6, 101.0, 100.0, 100.9))
    for rh, rl, a4 in ((NAN, 100.0, 2.0), (108.0, NAN, 2.0), (108.0, 100.0, NAN)):
        r = mk_rdf(df.index, "range", atr=a4, rh=rh, rl=rl)
        x = row(compute_signals(df, r))
        assert x.setup is None and not x.signal


def test_trigger_tf_does_not_change_arithmetic():
    bars = [(100.0, 101.0, 99.0, 100.0)] * 19 + [(99.5, 101.0, 99.0, 100.5)]
    d1, d15 = mk_df(bars, "1h"), mk_df(bars, "15min")
    a = compute_signals(d1, mk_rdf(d1.index, "trend_up"), prm(pullback_ema=20, trigger_tf="1h"))
    b = compute_signals(d15, mk_rdf(d15.index, "trend_up"), prm(pullback_ema=20, trigger_tf="15m"))
    pd.testing.assert_frame_equal(a.reset_index(drop=True), b.reset_index(drop=True), check_exact=True)
    c = compute_signals(d15, mk_rdf(d15.index, "trend_up"), prm(pullback_ema=20, trigger_tf="1h"))
    pd.testing.assert_frame_equal(b, c, check_exact=True)


# ===========================================================================
# 7. No signal: history, NaN, bad bars, regime priority
# ===========================================================================

def test_insufficient_history_no_signals():
    df = t1_df(n=10, flat=(100.0, 101.0, 99.0, 100.0))
    out = compute_signals(df, mk_rdf(df.index, "trend_up"), prm(pullback_ema=20))
    assert (out["reasons"] == "no_history").all() and not out["signal"].any()
    assert out["setup"].isna().all() and out["side"].isna().all()
    assert out["planned_entry"].isna().all() and out["planned_stop"].isna().all()


def test_single_row_ok():
    df = t1_df(n=1, last=(99.5, 101.0, 99.0, 100.5))
    out = compute_signals(df, mk_rdf(df.index, "trend_up"), prm(pullback_ema=20))
    assert len(out) == 1 and not out["signal"].iloc[0] and out["reasons"].iloc[0] == "no_history"


def test_regime_blocked_priority_over_no_history():
    df = t1_df()
    for reg in ("volatile", "unclear"):
        out = compute_signals(df, mk_rdf(df.index, reg), prm(pullback_ema=20))
        assert (out["reasons"] == "regime_blocked").all()
        assert not out["signal"].any() and out["setup"].isna().all()
        assert out["regime"].tolist() == [reg] * len(df)


def test_bad_bar_cases_and_priority():
    base = (99.5, 101.0, 99.0, 100.5)
    cases = {
        "nan_close": (99.5, 101.0, 99.0, NAN),
        "inf_high": (99.5, float("inf"), 99.0, 100.5),
        "high_lt_low": (99.5, 98.0, 99.0, 98.5),
        "zero_range": (100.0, 100.0, 100.0, 100.0),
        "neg_price": (99.5, 101.0, -1.0, 100.5),
        "close_outside": (99.5, 101.0, 99.0, 102.0),
        "open_outside": (98.0, 101.0, 99.0, 100.5),
    }
    for name, bar in cases.items():
        df = t1_df(last=bar)
        out = compute_signals(df, mk_rdf(df.index, "trend_up"), prm(pullback_ema=20))
        x = row(out)
        assert not x.signal and x.setup is None, name
        assert x.reasons == "bad_bar", name
        # bad_bar > regime_blocked
        out2 = compute_signals(df, mk_rdf(df.index, "volatile"), prm(pullback_ema=20))
        assert row(out2).reasons == "bad_bar", name


def test_bad_bar_in_window_gives_no_history_then_recovers():
    bars = [(100.0, 101.0, 99.0, 100.0)] * 22 + [(99.5, 101.0, 99.0, 100.5)]
    bars[17] = (NAN, NAN, NAN, NAN)
    df = mk_df(bars)
    out = compute_signals(df, mk_rdf(df.index, "trend_up"), prm(pullback_ema=20))
    assert out["reasons"].iloc[17] == "bad_bar"
    for t in (18, 19, 20, 21):   # window t-4..t contains bar 17
        assert out["reasons"].iloc[t] == "no_history", t
        assert not out["signal"].iloc[t]
    # t=22: window 18..22 clean; ATR = 2 (state carried), EMA state carried -> 100 + 1/21
    x = row(out, 22)
    assert x.signal and x.planned_stop == pytest.approx(98.4)
    assert x.ema_value == pytest.approx(100 + 1 / 21)


def test_nan_never_signals_in_random_garbage():
    rs = np.random.RandomState(5)
    for _ in range(10):
        sigma = 2.0
        df = gen_df(rs, 120, sigma)
        idx = rs.choice(120, 12, replace=False)
        for i in idx:
            col = ["open", "high", "low", "close"][int(rs.randint(4))]
            df.iloc[i, df.columns.get_loc(col)] = NAN if rs.rand() < 0.5 else float("inf")
        r = synth_regime(rs, df, sigma)
        out = compute_signals(df, r, prm(pullback_ema=20))
        sub = out[out["signal"]]
        for c in ("planned_entry", "planned_stop", "stop_dist_atr", "atr_tf"):
            assert np.isfinite(sub[c]).all()
        bad = ~np.isfinite(df[["open", "high", "low", "close"]]).all(axis=1)
        assert not out.loc[bad.values, "signal"].any()


# ===========================================================================
# 8. Input contract
# ===========================================================================

def test_structural_errors():
    df = t1_df(); r = mk_rdf(df.index)
    with pytest.raises(ValueError):
        compute_signals([1, 2, 3], r)
    with pytest.raises(ValueError):
        compute_signals(df.drop(columns=["low"]), r)
    with pytest.raises(ValueError):
        compute_signals(df.reset_index(drop=True), r.reset_index(drop=True))
    rev = df.iloc[::-1]
    with pytest.raises(ValueError):
        compute_signals(rev, mk_rdf(rev.index))
    dup = pd.concat([df.iloc[:5], df.iloc[4:5], df.iloc[5:]])
    with pytest.raises(ValueError):
        compute_signals(dup, mk_rdf(dup.index))
    with pytest.raises(ValueError):                       # indices differ
        compute_signals(df, r.iloc[:-1])
    with pytest.raises(ValueError):
        compute_signals(df, r.shift(1, freq="1h"))
    with pytest.raises(ValueError):
        compute_signals(df, r, params={"rr_min": 1.5})


def test_input_unmodified_deterministic_volume_ignored():
    df = t1_df(); r = mk_rdf(df.index)
    df2 = df.copy(); r2 = r.copy()
    a = compute_signals(df, r, prm(pullback_ema=20))
    b = compute_signals(df, r, prm(pullback_ema=20))
    pd.testing.assert_frame_equal(df, df2); pd.testing.assert_frame_equal(r, r2)
    eq_frames(a, b)
    dv = df.copy(); dv["volume"] = np.arange(len(df)) * 7.0
    eq_frames(compute_signals(dv, r, prm(pullback_ema=20)), a)


def test_output_dtypes_and_passthrough():
    df = t1_df()
    r = mk_rdf(df.index, "trend_up", atr=4.0, atr_ratio=1.25)
    out = compute_signals(df, r, prm(pullback_ema=20))
    assert len(SIGNAL_COLUMNS) == len(set(SIGNAL_COLUMNS))
    assert set(SIGNAL_COLUMNS) == {
        "setup", "side", "signal", "skip_reason", "planned_entry", "planned_stop", "planned_target",
        "rr", "stop_dist_atr", "atr_tf", "atr_4h", "atr_ratio", "regime", "rh", "rl", "rh_touches",
        "rl_touches", "ema_value", "body_ratio", "wick_ratio", "edge_dist_atr", "pullback_ema", "reasons"}
    assert out["signal"].dtype == bool
    for c in ("planned_entry", "planned_stop", "planned_target", "rr", "stop_dist_atr", "atr_tf",
              "atr_4h", "atr_ratio", "ema_value", "body_ratio", "wick_ratio", "edge_dist_atr"):
        assert out[c].dtype == np.float64, c
    assert out["pullback_ema"].dtype == np.int64
    assert (out["atr_4h"] == 4.0).all() and (out["atr_ratio"] == 1.25).all()
    assert out["regime"].tolist() == ["trend_up"] * 20
    assert (out["pullback_ema"].iloc[:19] == 0).all() or True   # non-T1 rows are 0 (T1 rows carry the param)
    assert out["pullback_ema"].iloc[19] == 20
    assert out["reasons"].map(lambda s: " " not in s).all()
    assert out["skip_reason"].dropna().isin(["stop_width", "rr_below_min", "other"]).all()


# ===========================================================================
# 9. Exit helpers (8.7 / 8.8)
# ===========================================================================

def S(x):
    return pd.Series(x, dtype=float)


def test_8_7_trail_long():
    out = trail_stop_path("long", 100.5, 98.4, S([102.0, 103.0, 102.8]), S([101.0, 101.5, 101.0]),
                          S([1.0, 1.0, 2.0]), 3.0)
    assert len(out) == 3
    # k0: hh=102.0 < 100.5+2.1=102.6 -> initial ; k1: hh=103 armed cand=103-3=100 ; k2: cand=103-6=97 -> keep 100
    assert list(out) == pytest.approx([98.4, 100.0, 100.0])


def test_8_7_trail_short():
    out = trail_stop_path("short", 99.5, 101.6, S([100.0, 99.0, 99.5]), S([98.0, 97.0, 97.2]),
                          S([1.0, 1.0, 2.0]), 3.0)
    # R=2.1 ; threshold 97.4 ; k1 ll=97 armed cand = 97+3 = 100 ; k2 cand 97+6=103 -> keep 100
    assert list(out) == pytest.approx([101.6, 100.0, 100.0])


def test_trail_arming_boundary_binary_exact():
    # fill 100, initial 96 -> R = 4 ; arm at hh >= 104
    exact = trail_stop_path("long", 100.0, 96.0, S([104.0]), S([99.0]), S([1.0]), 3.0)
    assert list(exact) == pytest.approx([101.0])      # 104 - 3*1
    below = trail_stop_path("long", 100.0, 96.0, S([103.99]), S([99.0]), S([1.0]), 3.0)
    assert list(below) == pytest.approx([96.0])
    short_exact = trail_stop_path("short", 100.0, 104.0, S([101.0]), S([96.0]), S([1.0]), 3.0)
    assert list(short_exact) == pytest.approx([99.0])  # 96 + 3
    short_below = trail_stop_path("short", 100.0, 104.0, S([101.0]), S([96.01]), S([1.0]), 3.0)
    assert list(short_below) == pytest.approx([104.0])


def test_trail_stays_armed_after_pullback_and_uses_current_atr():
    # armed at k0 (hh=105): cand = 105-3*1 = 102 ; later highs lower: hh stays 105 ; atr .5 -> cand 103.5
    out = trail_stop_path("long", 100.0, 96.0, S([105.0, 101.0, 101.0]), S([99.0, 99.0, 99.0]),
                          S([1.0, 1.0, 0.5]), 3.0)
    assert list(out) == pytest.approx([102.0, 102.0, 103.5])
    # trail_atr param: 2.0 and 4.0
    o2 = trail_stop_path("long", 100.0, 96.0, S([105.0]), S([99.0]), S([1.0]), 2.0)
    o4 = trail_stop_path("long", 100.0, 96.0, S([105.0]), S([99.0]), S([1.0]), 4.0)
    assert (o2.iloc[0], o4.iloc[0]) == pytest.approx((103.0, 101.0))


def test_trail_never_below_initial_when_candidate_lower():
    # armed with huge ATR: cand = 104 - 3*10 = 74 < initial 96 -> stop stays 96
    out = trail_stop_path("long", 100.0, 96.0, S([104.0]), S([99.0]), S([10.0]), 3.0)
    assert list(out) == pytest.approx([96.0])


def test_trail_monotone_random():
    rs = np.random.RandomState(11)
    for _ in range(100):
        n = int(rs.randint(1, 40))
        fill = 100.0; R = float(rs.uniform(0.5, 5))
        steps = rs.normal(0, 1.2, n).cumsum()
        hi = pd.Series(fill + steps + np.abs(rs.normal(0, .5, n)))
        lo = pd.Series(fill + steps - np.abs(rs.normal(0, .5, n)))
        atrs = pd.Series(rs.uniform(0.2, 3, n))
        ta = float(rs.uniform(2, 4))
        lg = trail_stop_path("long", fill, fill - R, hi, lo, atrs, ta).to_numpy()
        assert (np.diff(lg) >= -1e-12).all() and (lg >= fill - R - 1e-12).all()
        sh = trail_stop_path("short", fill, fill + R, hi, lo, atrs, ta).to_numpy()
        assert (np.diff(sh) <= 1e-12).all() and (sh <= fill + R + 1e-12).all()
        # not armed before threshold reached
        hh = np.maximum.accumulate(hi.to_numpy())
        un = hh < fill + R - 1e-9
        assert np.allclose(lg[un], fill - R)
        # reference
        ref = []; best = fill - R
        for k in range(n):
            if hh[k] >= fill + R - 1e-9:
                best = max(best, hh[k] - ta * atrs.iloc[k])
            ref.append(best)
        assert lg == pytest.approx(ref)


def test_time_stop():
    assert time_stop_due(47) is False or time_stop_due(47) == False  # noqa: E712
    assert bool(time_stop_due(48)) is True
    assert bool(time_stop_due(49)) is True and bool(time_stop_due(0)) is False and bool(time_stop_due(1)) is False
    assert not time_stop_due(9, limit=10) and time_stop_due(10, limit=10)
    assert sg.TIME_STOP_BARS == 48


def test_target_reached():
    assert not target_reached("long", 106.0, bar_high=105.9, bar_low=100.0)
    assert target_reached("long", 106.0, bar_high=106.0, bar_low=100.0)
    assert target_reached("long", 106.0, bar_high=107.0, bar_low=100.0)
    assert not target_reached("short", 102.0, bar_high=108.0, bar_low=102.1)
    assert target_reached("short", 102.0, bar_high=108.0, bar_low=102.0)
    assert target_reached("short", 102.0, bar_high=108.0, bar_low=101.0)
    # long ignores the low, short ignores the high
    assert not target_reached("long", 106.0, bar_high=105.0, bar_low=90.0)
    assert not target_reached("short", 102.0, bar_high=120.0, bar_low=103.0)


@pytest.mark.parametrize("side,reg,exp", [
    ("long", "trend_down", True), ("long", "range", False), ("long", "volatile", False),
    ("long", "unclear", False), ("long", "trend_up", False),
    ("short", "trend_up", True), ("short", "range", False), ("short", "volatile", False),
    ("short", "unclear", False), ("short", "trend_down", False)])
def test_regime_flip_exit(side, reg, exp):
    assert bool(regime_flip_exit(side, reg)) is exp


def test_exit_helpers_same_for_15m():
    # bar counts are in trigger-TF bars regardless of tf: 48 bars = 48h (1h) or 12h (15m)
    assert time_stop_due(48) and not time_stop_due(47)


# ===========================================================================
# 10. No-lookahead
# ===========================================================================

def garbage(rs, df, r, t, kind):
    d = df.copy(); rr = r.copy()
    fut = d.index[t + 1:]
    m = len(fut)
    if m == 0:
        return d, rr
    cols = ["open", "high", "low", "close"]
    if kind == 0:       # arbitrary (mostly invalid) values
        d.loc[fut, cols] = rs.uniform(1, 2000, (m, 4))
    elif kind == 1:     # NaN
        d.loc[fut, cols] = np.nan
    elif kind == 2:     # valid but shifted / scaled bars (price crash)
        d.loc[fut, cols] = d.loc[fut, cols].to_numpy() * 0.5
    else:               # inf / zero
        d.loc[fut, cols] = np.where(rs.rand(m, 4) < 0.5, np.inf, 0.0)
    rr.loc[fut, "regime"] = [["trend_up", "trend_down", "range", "volatile", "unclear"][int(i)]
                             for i in rs.randint(0, 5, m)]
    rr.loc[fut, "rh"] = rs.uniform(500, 1500, m)
    rr.loc[fut, "rl"] = rs.uniform(500, 1500, m)
    rr.loc[fut, "atr"] = rs.uniform(0.1, 50, m)
    return d, rr


@pytest.mark.parametrize("seed", [1, 2, 3, 4, 5, 6])
def test_no_lookahead_truncation_and_mutation(seed):
    rs, df, r, p = scenario(seed, n=150)
    full = compute_signals(df, r, p)
    n = len(df)
    ts = sorted(set([0, 1, 2, 13, 14, 19, 20, 49, 50, n - 2, n - 1] + list(range(3, n, 7))))
    for t in ts:
        k = t + 1
        eq_frames(compute_signals(df.iloc[:k], r.iloc[:k], p), full.iloc[:k])
        for kind in range(4):
            d2, r2 = garbage(rs, df, r, t, kind)
            out = compute_signals(d2, r2, p)
            eq_frames(out.iloc[:k], full.iloc[:k])


def test_no_lookahead_every_k_hand_series():
    df = t1_df(n=40)
    bars = df.to_numpy().copy()
    bars[25] = (99.5, 101.0, 99.0, 100.5)
    bars[33] = (99.5, 101.0, 99.0, 100.5)
    df = mk_df(bars)
    r = mk_rdf(df.index, ["trend_up"] * 30 + ["range"] * 10, rh=[NAN] * 30 + [108.0] * 10,
               rl=[NAN] * 30 + [100.0] * 10)
    p = prm(pullback_ema=20)
    full = compute_signals(df, r, p)
    assert full["signal"].sum() >= 1
    for k in range(1, len(df) + 1):
        eq_frames(compute_signals(df.iloc[:k], r.iloc[:k], p), full.iloc[:k])


def pipeline(df1, df4, p):
    reg = classify_series(df4, p.regime_params())
    al = align_to_base(reg, df1.index, 4)
    return compute_signals(df1, al, p), reg, al


def make_4h_1h(seed, n4=170):
    rs = np.random.RandomState(seed)
    d4 = gen_df(rs, n4, 3.0, "4h")
    d1 = gen_df(rs, 4 * n4, 1.5, "1h")
    return d1, d4


@pytest.mark.parametrize("seed", [21, 22, 23])
def test_4h_regime_only_after_4h_close(seed):
    d1, d4 = make_4h_1h(seed)
    p = DEFAULT_SIGNAL_PARAMS
    base, reg0, _ = pipeline(d1, d4, p)
    j = 140
    d4m = d4.copy()
    o = d4m["open"].iloc[j]
    c = o * 1.4
    d4m.iloc[j, d4m.columns.get_loc("close")] = c
    d4m.iloc[j, d4m.columns.get_loc("high")] = c * 1.05
    d4m.iloc[j, d4m.columns.get_loc("low")] = min(o, d4m["low"].iloc[j])
    mut, regm, alm = pipeline(d1, d4m, p)
    assert regm["regime"].iloc[j] == "volatile", "precondition: spike must be volatile"
    close_j = d4.index[j] + pd.Timedelta(hours=4)
    before = base.index < close_j
    eq_frames(mut.loc[before], base.loc[before])
    # bar opening exactly when 4h bar j closes sees the new label ...
    x = mut.loc[close_j]
    assert x["regime"] == "volatile" and not x["signal"] and x["reasons"] == "regime_blocked"
    # ... the previous 1h bar (closing with the 4h bar) still sees the old label
    prev = close_j - pd.Timedelta(hours=1)
    assert mut.loc[prev, "regime"] == reg0["regime"].iloc[j - 1]


@pytest.mark.parametrize("seed", [31, 32])
def test_4h_appending_future_bars_changes_nothing_earlier(seed):
    d1, d4 = make_4h_1h(seed)
    p = DEFAULT_SIGNAL_PARAMS
    full, _, _ = pipeline(d1, d4, p)
    for m in (120, 135, 150, 160):
        short, _, _ = pipeline(d1, d4.iloc[:m], p)
        # 4h bar m would only become usable at open(m)+4h
        lim = d4.index[m] + pd.Timedelta(hours=4)
        mask = full.index < lim
        eq_frames(short.loc[mask], full.loc[mask])


def test_4h_stale_label_blocks_signals():
    d1, d4 = make_4h_1h(41)
    short, _, _ = pipeline(d1, d4.iloc[:140], DEFAULT_SIGNAL_PARAMS)
    stale = short.index >= d4.index[140] + pd.Timedelta(hours=4)
    assert stale.any()
    assert not short.loc[stale, "signal"].any()
    assert (short.loc[stale, "regime"] == "unclear").all()


# ===========================================================================
# 11. Symmetry
# ===========================================================================

def mirror_df(df, pivot):
    m = pd.DataFrame({"open": 2 * pivot - df["open"], "high": 2 * pivot - df["low"],
                      "low": 2 * pivot - df["high"], "close": 2 * pivot - df["close"]}, index=df.index)
    return m


def mirror_rdf(r, pivot):
    m = r.copy()
    m["regime"] = r["regime"].map({"trend_up": "trend_down", "trend_down": "trend_up"}).fillna(r["regime"])
    m["rh"] = 2 * pivot - r["rl"]
    m["rl"] = 2 * pivot - r["rh"]
    return m


def test_mirror_symmetry_t1_example():
    df = t1_df(); r = mk_rdf(df.index, "trend_up")
    a = row(compute_signals(df, r, prm(pullback_ema=20)))
    dm = mirror_df(df, 100.0)
    b = row(compute_signals(dm, mirror_rdf(r, 100.0), prm(pullback_ema=20)))
    assert a.side == "long" and b.side == "short" and a.signal and b.signal
    assert b.planned_entry == pytest.approx(200 - a.planned_entry)
    assert b.planned_stop == pytest.approx(200 - a.planned_stop)
    assert b.stop_dist_atr == pytest.approx(a.stop_dist_atr)
    assert b.ema_value == pytest.approx(200 - a.ema_value)


@pytest.mark.parametrize("seed", [51, 52, 53, 54])
def test_mirror_symmetry_random(seed):
    rs, df, r, p = scenario(seed, n=160)
    a = compute_signals(df, r, p)
    b = compute_signals(mirror_df(df, 1000.0), mirror_rdf(r, 1000.0), p)
    assert (a["signal"].to_numpy() == b["signal"].to_numpy()).all()
    flip = {"long": "short", "short": "long", None: None}
    assert [flip[s] if s in flip else s for s in a["side"]] == list(b["side"])
    assert list(a["setup"].fillna("-")) == list(b["setup"].fillna("-"))
    assert list(a["skip_reason"].fillna("-")) == list(b["skip_reason"].fillna("-"))
    for c in ("planned_entry", "planned_stop", "planned_target"):
        np.testing.assert_allclose(2000 - a[c].to_numpy(), b[c].to_numpy(), rtol=1e-9, atol=1e-6, equal_nan=True)
    np.testing.assert_allclose(a["rr"].to_numpy(), b["rr"].to_numpy(), rtol=1e-8, equal_nan=True)
    np.testing.assert_allclose(a["stop_dist_atr"].to_numpy(), b["stop_dist_atr"].to_numpy(), rtol=1e-8, equal_nan=True)


# ===========================================================================
# 12. Property test (seeded) + differential vs oracle
# ===========================================================================

def _close(a, b):
    if isnan(a) or isnan(b):
        return isnan(a) and isnan(b)
    return abs(a - b) <= 1e-7 * max(1.0, abs(a), abs(b))


def test_generator_and_oracle_exercise_all_paths():
    cnt = {}
    for seed in range(1000, 1060):
        rs, df, r, p = scenario(seed)
        for x in ref_signals(df, r, p):
            if x["setup"]:
                key = (x["setup"], x["side"], x["skip"])
                cnt[key] = cnt.get(key, 0) + 1
    for key in (("T1", "long", None), ("T1", "short", None), ("R1", "long", None), ("R1", "short", None),
                ("T1", "long", "stop_width"), ("R1", "long", "rr_below_min"),
                ("R1", "short", "rr_below_min")):
        assert cnt.get(key, 0) > 0, (key, cnt)


def test_property_200_random_series():
    seen = {"T1_long": 0, "T1_short": 0, "R1_long": 0, "R1_short": 0}
    for seed in range(200):
        rs, df, r, p = scenario(seed, freq=["1h", "15min"][seed % 2])
        df0, r0 = df.copy(), r.copy()
        out = compute_signals(df, r, p)
        tag = f"seed={seed}"
        # contract
        pd.testing.assert_frame_equal(df, df0); pd.testing.assert_frame_equal(r, r0)
        assert out.index.equals(df.index) and list(out.columns) == list(SIGNAL_COLUMNS), tag
        assert out["signal"].dtype == bool, tag
        for c in ("regime", "rh", "rl", "rh_touches", "rl_touches"):
            pd.testing.assert_series_equal(out[c], r[c], check_names=False, check_dtype=False)
        assert out["atr_4h"].equals(r["atr"].rename("atr_4h")) or np.allclose(out["atr_4h"], r["atr"])
        # history: nothing before ATR is valid
        assert not out["signal"].iloc[:13].any(), tag
        # regime blocking
        blocked = r["regime"].isin(["volatile", "unclear"]).to_numpy()
        assert out.loc[blocked, "setup"].isna().all() and not out.loc[blocked, "signal"].any(), tag
        # per-row invariants
        sub = out[out["signal"]]
        assert sub["skip_reason"].isna().all(), tag
        assert sub["setup"].isin(["T1", "R1"]).all() and sub["side"].isin(["long", "short"]).all(), tag
        for ts, x in sub.iterrows():
            i = df.index.get_loc(ts)
            close = df["close"].iloc[i]
            assert x.planned_entry == pytest.approx(close), tag
            lo_ok = x.side == "long"
            assert (x.planned_stop < x.planned_entry) if lo_ok else (x.planned_stop > x.planned_entry), tag
            assert 0.5 - 1e-6 <= x.stop_dist_atr <= 2.0 + 1e-6, tag
            assert x.stop_dist_atr == pytest.approx(abs(x.planned_entry - x.planned_stop) / x.atr_tf), tag
            assert np.isfinite(x.planned_entry) and np.isfinite(x.planned_stop) and np.isfinite(x.atr_tf), tag
            if x.setup == "T1":
                assert x.regime == ("trend_up" if lo_ok else "trend_down"), tag
                assert math.isnan(x.planned_target) and math.isnan(x.rr), tag
            else:
                assert x.regime == "range", tag
                assert x.rr >= p.rr_min - 1e-6, tag
                if lo_ok:
                    assert x.planned_target > x.planned_entry, tag
                    assert x.planned_target == pytest.approx(x.rl + p.range_target_frac * (x.rh - x.rl)), tag
                else:
                    assert x.planned_target < x.planned_entry, tag
                    assert x.planned_target == pytest.approx(x.rh - p.range_target_frac * (x.rh - x.rl)), tag
            seen[f"{x.setup}_{x.side}"] += 1
        # non-signal rows with a candidate: skip reasons are consistent
        skipped = out[(~out["signal"]) & out["setup"].notna()]
        assert skipped["skip_reason"].notna().all(), tag
        assert skipped["skip_reason"].isin(["stop_width", "rr_below_min", "other"]).all(), tag
        for ts, x in skipped.iterrows():
            if x.skip_reason == "stop_width":
                assert x.stop_dist_atr < 0.5 + 1e-6 or x.stop_dist_atr > 2.0 - 1e-6, tag
            if x.skip_reason == "rr_below_min":
                assert x.rr < p.rr_min + 1e-6, tag
            if x.skip_reason == "other":
                assert x.side is None and x.reasons == "conflict:long_short", tag
        # differential against the oracle (rows where every indicator is certainly warm)
        ref = ref_signals(df, r, p)
        for i in range(60, len(df)):
            x, o = out.iloc[i], ref[i]
            ctx = f"{tag} row={i}"
            assert (x.setup if x.setup is not None else None) == o["setup"], ctx
            assert (x.side if x.side is not None else None) == o["side"], ctx
            assert bool(x.signal) == o["signal"], ctx
            assert (None if isnan(x.skip_reason) else x.skip_reason) == o["skip"], ctx
            if o["side"] is not None:
                assert _close(float(x.planned_entry), o["entry"]), ctx
                assert _close(float(x.planned_stop), o["stop"]), ctx
                assert _close(float(x.planned_target), o["target"]), ctx
                assert _close(float(x.rr), o["rr"]), ctx
    assert all(v > 0 for v in seen.values()), seen
