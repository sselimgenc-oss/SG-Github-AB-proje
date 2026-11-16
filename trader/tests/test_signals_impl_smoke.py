"""Uygulama sanity testleri (spec testleri test_signals_spec.py'dedir)."""
import math

import numpy as np
import pandas as pd
import pytest

from trader_core import ledger, regime, signals as S


def _t1_data(side="long", pullback=20):
    idx = pd.date_range("2025-01-01", periods=20, freq="1h", tz="UTC")
    df = pd.DataFrame({"open": 100.0, "high": 101.0, "low": 99.0, "close": 100.0}, index=idx)
    if side == "long":
        df.iloc[19] = [99.5, 101.0, 99.0, 100.5]
        lab = "trend_up"
    else:
        df.iloc[19] = [100.5, 101.0, 99.0, 99.5]
        lab = "trend_down"
    r = pd.DataFrame({"regime": lab, "rh": np.nan, "rl": np.nan, "rh_touches": 0, "rl_touches": 0,
                      "atr": 4.0, "atr_ratio": 1.0}, index=idx)
    return df, r


def test_params_match_ledger_and_regime():
    p = S.DEFAULT_SIGNAL_PARAMS
    for k, spec in ledger.PARAM_SPECS.items():
        if spec["kind"] == "float":
            assert S._FLOAT_SPECS[k] == (spec["lo"], spec["hi"]) or k == "pullback_ema"
    assert {k: getattr(p, k) for k in ledger.PARAM_KEYS}  # all 9 exist
    ledger._norm_params({k: getattr(p, k) for k in ledger.PARAM_KEYS})
    assert p.regime_params() == regime.DEFAULT_PARAMS


def test_params_validation():
    with pytest.raises(ValueError):
        S.SignalParams(pullback_ema=30)
    with pytest.raises(ValueError):
        S.SignalParams(pullback_ema="50")
    with pytest.raises(ValueError):
        S.SignalParams(rr_min=True)
    with pytest.raises(ValueError):
        S.SignalParams(trail_atr=float("nan"))
    with pytest.raises(ValueError):
        S.SignalParams(trigger_tf="4h")
    assert S.SignalParams(pullback_ema=50.0).pullback_ema == 50
    d = {k: getattr(S.DEFAULT_SIGNAL_PARAMS, k) for k in ledger.PARAM_KEYS}
    assert S.SignalParams.from_mapping(d) == S.DEFAULT_SIGNAL_PARAMS
    d2 = dict(d)
    d2.pop("rr_min")
    with pytest.raises(ValueError):
        S.SignalParams.from_mapping(d2)


def test_t1_long_example():
    df, r = _t1_data("long")
    out = S.compute_signals(df, r, S.SignalParams(pullback_ema=20))
    row = out.iloc[19]
    assert row["setup"] == "T1" and row["side"] == "long" and bool(row["signal"])
    assert row["planned_entry"] == 100.5
    assert row["planned_stop"] == pytest.approx(98.4)
    assert math.isnan(row["planned_target"])
    assert row["stop_dist_atr"] == pytest.approx(1.05)
    assert row["ema_value"] == pytest.approx(100 + 1 / 21)
    assert row["reasons"] == "T1_long:trend_up,ema_touch,bull_body,stop_ok"
    assert list(out.columns) == S.SIGNAL_COLUMNS
    assert (out.iloc[:19]["reasons"] == "no_history").all()
    assert not out.iloc[:19]["signal"].any()
    assert out["pullback_ema"].dtype == np.int64 and out["signal"].dtype == bool
    # default pullback 50 -> all no_history
    out50 = S.compute_signals(df, r)
    assert (out50["reasons"] == "no_history").all()


def test_t1_short_example():
    df, r = _t1_data("short")
    row = S.compute_signals(df, r, S.SignalParams(pullback_ema=20)).iloc[19]
    assert row["side"] == "short" and row["planned_stop"] == pytest.approx(101.6)
    assert row["reasons"] == "T1_short:trend_down,ema_touch,bear_body,stop_ok"


def test_no_lookahead_prefix():
    rng = np.random.default_rng(1)
    n = 300
    idx = pd.date_range("2025-01-01", periods=n, freq="1h", tz="UTC")
    c = 100 + np.cumsum(rng.normal(0, 0.5, n))
    o = np.r_[c[0], c[:-1]]
    h = np.maximum(o, c) + rng.random(n) * 0.5
    l = np.minimum(o, c) - rng.random(n) * 0.5
    df = pd.DataFrame({"open": o, "high": h, "low": l, "close": c}, index=idx)
    r = pd.DataFrame({"regime": rng.choice(["trend_up", "trend_down", "range", "volatile"], n),
                      "rh": c + 1.0, "rl": c - 1.0, "rh_touches": 2, "rl_touches": 2,
                      "atr": 1.0, "atr_ratio": 1.0}, index=idx)
    p = S.SignalParams(pullback_ema=20)
    full = S.compute_signals(df, r, p)
    for k in (30, 100, 200):
        pd.testing.assert_frame_equal(full.iloc[:k], S.compute_signals(df.iloc[:k], r.iloc[:k], p))
    assert full["signal"].sum() > 0


def test_r1_examples():
    p = S.DEFAULT_SIGNAL_PARAMS
    c = S.evaluate_r1("long", 100.6, 101.0, 100.0, 100.9, 108, 100, 1.0, 2.0, p)
    assert c.signal and c.target == pytest.approx(106.0) and c.rr == pytest.approx(4.25)
    assert c.reasons == "R1_long:range,edge_zone,reject_wick,stop_ok,rr_ok"
    c = S.evaluate_r1("long", 100.6, 101.0, 100.0, 100.9, 102, 100, 1.0, 2.0, p)
    assert c.skip_reason == "rr_below_min"
    c = S.evaluate_r1("long", 100.6, 101.0, 100.0, 100.9, 103.6, 100, 1.0, 2.0, p)
    assert c.skip_reason is None
    assert S.evaluate_r1("long", 100.6, 101.0, 100.6, 100.9, 108, 100, 1.0, 2.0, p) is None
    s = S.evaluate_r1("short", 107.4, 108.0, 107.0, 107.1, 108, 100, 1.0, 2.0, p)
    assert s.signal and s.stop == pytest.approx(108.3) and s.target == pytest.approx(102.0)


def test_t1_stop_width():
    p = S.SignalParams(stop_buffer_atr=0.1)
    c = S.evaluate_t1("long", 100.2, 100.6, 100.0, 100.5, 100.2, [100.0, 100.1, 100.2, 100.1, 100.0], 2.0, p)
    assert c.skip_reason == "stop_width"
    c = S.evaluate_t1("long", 100.2, 100.6, 100.0, 100.5, 100.2, [95, 100.1, 100.2, 100.1, 100.0], 2.0,
                      S.DEFAULT_SIGNAL_PARAMS)
    assert c.skip_reason == "stop_width"


def test_pick_candidate():
    p = S.DEFAULT_SIGNAL_PARAMS
    rl, rh = 100.0, 100.8
    args = (100.4, 100.8, 100.0, 100.4, rh, rl, 0.2, 2.0, p)
    lg, sh = S.evaluate_r1("long", *args), S.evaluate_r1("short", *args)
    assert lg is not None and sh is not None
    pk = S.pick_candidate([lg, sh])
    assert pk.side is None and not pk.signal and pk.skip_reason == "other"
    assert pk.reasons == "conflict:long_short"
    t1 = S.evaluate_t1("long", 100.2, 100.6, 100.0, 100.5, 100.2, [100.0] * 5, 2.0, p)
    assert S.pick_candidate([lg, t1]) is t1
    assert S.pick_candidate([None, None]) is None


def test_exit_helpers():
    s = S.trail_stop_path("long", 100.5, 98.4, [102.0, 103.0, 102.8], [0, 0, 0], [1.0, 1.0, 2.0], 3.0)
    assert list(s) == pytest.approx([98.4, 100.0, 100.0])
    s = S.trail_stop_path("short", 99.5, 101.6, [0, 0, 0], [98.0, 97.0, 97.2], [1.0, 1.0, 2.0], 3.0)
    assert list(s) == pytest.approx([101.6, 100.0, 100.0])
    assert not S.time_stop_due(47) and S.time_stop_due(48)
    assert not S.target_reached("long", 106.0, 105.9, 0) and S.target_reached("long", 106.0, 106.0, 0)
    assert not S.target_reached("short", 102.0, 999, 102.1) and S.target_reached("short", 102.0, 999, 102.0)
    assert S.regime_flip_exit("long", "trend_down") and not S.regime_flip_exit("long", "range")
    assert S.regime_flip_exit("short", "trend_up")


def test_input_validation():
    df, r = _t1_data()
    with pytest.raises(ValueError):
        S.compute_signals(df, r.iloc[:-1])
    with pytest.raises(ValueError):
        S.compute_signals(df.iloc[::-1], r.iloc[::-1])
    with pytest.raises(ValueError):
        S.compute_signals(df, r, params={"a": 1})
    with pytest.raises(ValueError):
        S.compute_signals(df.drop(columns="close"), r)


def test_bad_bar_and_blocked():
    df, r = _t1_data()
    df = df.copy()
    df.iloc[19, df.columns.get_loc("high")] = np.nan
    out = S.compute_signals(df, r, S.SignalParams(pullback_ema=20))
    assert out.iloc[19]["reasons"] == "bad_bar" and not out.iloc[19]["signal"]
    df, r = _t1_data()
    r = r.copy()
    r["regime"] = "volatile"
    out = S.compute_signals(df, r, S.SignalParams(pullback_ema=20))
    assert (out["reasons"] == "regime_blocked").all()
