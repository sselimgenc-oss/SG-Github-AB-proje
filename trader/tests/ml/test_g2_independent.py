"""ML-G2 bagimsiz spec testleri (sentetik veri, 2025 zaman damgalari; holdout okunmaz)."""
from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from trader_ml import config
from trader_ml.labels import label_candidates, multi_r_labels
from trader_ml.models import fit_platt
from trader_ml.weights import (average_uniqueness, sample_weights_v2, time_decay_weights,
                               uniqueness_weights)

T0 = pd.Timestamp("2025-03-01", tz="UTC")
H = pd.Timedelta(hours=1)


def ts(*hours):
    return pd.Series([T0 + h * H for h in hours])


# ---------------------------------------------------------------- average_uniqueness
def test_isolated_event_is_one():
    u = average_uniqueness(ts(0), ts(5))
    assert u.shape == (1,) and u[0] == pytest.approx(1.0)


def test_two_fully_overlapping():
    u = average_uniqueness(ts(0, 0), ts(4, 4))
    np.testing.assert_allclose(u, [0.5, 0.5])


def test_partial_overlap_hand_computed():
    # A: bars 0,1,2 ; B: bars 2,3 ; c = [1,1,2,1]
    u = average_uniqueness(ts(0, 2), ts(3, 4))
    np.testing.assert_allclose(u, [5 / 6, 0.75])


def test_end_le_start_occupies_one_bar():
    # A: end == start -> bar 0 only ; B: end < start -> bar 0 only ; both share bar 0
    u = average_uniqueness(ts(0, 0), ts(0, -3))
    np.testing.assert_allclose(u, [0.5, 0.5])
    # alone -> 1
    np.testing.assert_allclose(average_uniqueness(ts(7), ts(7)), [1.0])


def test_end_is_exclusive():
    # A: bars 0,1 ; B starts at bar 2 -> no overlap
    np.testing.assert_allclose(average_uniqueness(ts(0, 2), ts(2, 4)), [1.0, 1.0])


def test_start_floored_to_bar():
    s = pd.Series([T0 + pd.Timedelta(minutes=30), T0])
    e = pd.Series([T0 + 2 * H, T0 + 2 * H])
    # floor(A.start)=T0 -> bars 0,1 for both
    np.testing.assert_allclose(average_uniqueness(s, e), [0.5, 0.5])


def test_nat_raises():
    with pytest.raises(ValueError):
        average_uniqueness(pd.Series([T0, pd.NaT]), pd.Series([T0 + H, T0 + 2 * H]))
    with pytest.raises(ValueError):
        average_uniqueness(pd.Series([T0, T0]), pd.Series([T0 + H, pd.NaT]))


def test_empty_input():
    e = pd.Series([], dtype="datetime64[ns, UTC]")
    assert len(average_uniqueness(e, e)) == 0
    assert len(uniqueness_weights(e, e)) == 0
    assert len(time_decay_weights(np.array([]), e)) == 0


def test_cross_pair_overlap_counts():
    # rows come from different pairs but share bars: no pair column, all rows pooled
    s = pd.Series([T0, T0 + H, T0 + H])        # e.g. BTC, ETH, SOL
    e = pd.Series([T0 + 2 * H, T0 + 3 * H, T0 + 2 * H])
    # bars: 0:{0}, 1:{0,1,2}, 2:{1}
    # u0=(1+1/3)/2, u1=(1/3+1)/2, u2=1/3
    np.testing.assert_allclose(average_uniqueness(s, e), [2 / 3, 2 / 3, 1 / 3])


# ---------------------------------------------------------------- uniqueness_weights
def test_uniqueness_weights_mean_one():
    s, e = ts(0, 2, 5, 5), ts(3, 4, 9, 7)
    w = uniqueness_weights(s, e)
    assert w.mean() == pytest.approx(1.0, abs=1e-12)
    u = average_uniqueness(s, e)
    np.testing.assert_allclose(w, u * len(u) / u.sum())


# ---------------------------------------------------------------- time_decay_weights
def test_decay_three_event_hand_computed():
    u = np.array([1.0, 0.5, 0.5])
    w = time_decay_weights(u, ts(0, 1, 2), oldest=0.3)
    # x=[1,1.5,2], slope=0.35, const=0.3
    np.testing.assert_allclose(w, [0.65, 0.825, 1.0])


def test_decay_returned_in_input_order_when_unsorted():
    u = np.array([0.5, 0.5, 1.0])
    w = time_decay_weights(u, ts(2, 1, 0), oldest=0.3)
    np.testing.assert_allclose(w, [1.0, 0.825, 0.65])


def test_decay_newest_one_and_monotone():
    rng = np.random.default_rng(3)
    n = 30
    u = rng.uniform(0.1, 1.0, n)
    t = pd.Series(T0 + pd.to_timedelta(rng.permutation(n), unit="h"))
    w = time_decay_weights(u, t, oldest=0.2)
    order = np.argsort(t.to_numpy(), kind="stable")
    ws = w[order]
    assert ws[-1] == pytest.approx(1.0)
    assert np.all(np.diff(ws) >= -1e-12)
    assert w.min() >= 0.0


def test_decay_oldest_one_all_ones():
    w = time_decay_weights(np.array([0.3, 0.9, 0.5]), ts(0, 1, 2), oldest=1.0)
    np.testing.assert_allclose(w, np.ones(3))


@pytest.mark.parametrize("bad", [-0.1, 1.5])
def test_decay_oldest_out_of_range(bad):
    with pytest.raises(ValueError):
        time_decay_weights(np.array([1.0, 1.0]), ts(0, 1), oldest=bad)


def test_decay_oldest_zero_endpoint_ok():
    w = time_decay_weights(np.array([1.0, 1.0]), ts(0, 1), oldest=0.0)
    np.testing.assert_allclose(w, [0.5, 1.0])


# ---------------------------------------------------------------- sample_weights_v2
def test_sample_weights_v2_small_frame():
    df = pd.DataFrame({
        "source": ["real", "backtest"],
        "ts": [T0, T0],
        "label_end_ts": [T0 + 2 * H, T0 + 2 * H],
    })
    # u=[.5,.5]; uniqueness weight [1,1]; decay: same-ts tie rule (mentor G2-1) -> both get end-of-group value 1.0
    # (was [.65, 1.0] with row-order-dependent cumulation)
    w = sample_weights_v2(df, oldest=0.3)
    np.testing.assert_allclose(w, [config.SOURCE_WEIGHTS["real"] * 1.0,
                                   config.SOURCE_WEIGHTS["backtest"] * 1.0])


def test_sample_weights_v2_composition():
    df = pd.DataFrame({
        "source": ["paper", "real", "counterfactual", "real"],
        "ts": [T0, T0 + 2 * H, T0 + 3 * H, T0 + 6 * H],
        "label_end_ts": [T0 + 3 * H, T0 + 4 * H, T0 + 5 * H, T0 + 8 * H],
    })
    u = average_uniqueness(df["ts"], df["label_end_ts"])
    expected = (df["source"].map(config.SOURCE_WEIGHTS).to_numpy()
                * uniqueness_weights(df["ts"], df["label_end_ts"])
                * time_decay_weights(u, df["ts"], 0.5))
    np.testing.assert_allclose(sample_weights_v2(df, oldest=0.5), expected)


# ---------------------------------------------------------------- multi_r_labels
def _candles(n=240, seed=11):
    rng = np.random.default_rng(seed)
    idx = pd.date_range("2025-02-01", periods=n, freq="1h", tz="UTC")
    close = 100 + np.cumsum(rng.normal(0, 0.6, n))
    op = np.r_[close[0], close[:-1]]
    hi = np.maximum(op, close) + rng.uniform(0.05, 0.7, n)
    lo = np.minimum(op, close) - rng.uniform(0.05, 0.7, n)
    return pd.DataFrame({"open": op, "high": hi, "low": lo, "close": close}, index=idx)


def _cands(candles):
    rows = []
    n = len(candles)
    for k, (bar, side) in enumerate([(5, "long"), (20, "short"), (40, "long"), (60, "short"),
                                     (90, "long"), (120, "short"), (150, "long"), (n - 4, "long"),
                                     (n - 3, "short")]):
        e = float(candles["close"].iloc[bar])
        risk = 1.0 + 0.2 * (k % 3)
        s = e - risk if side == "long" else e + risk
        tg = e + 2 * risk if side == "long" else e - 2 * risk
        rows.append({"ts": candles.index[bar] + H, "side": side, "planned_entry": e,
                     "planned_stop": s, "planned_target": tg})
    return pd.DataFrame(rows, index=pd.Index(range(100, 100 + len(rows))))


@pytest.mark.parametrize("r,tag", [(1.0, "1r"), (1.5, "1p5r"), (2.0, "2r"), (2.5, "2p5r"), (3.0, "3r")])
def test_multi_r_matches_label_candidates(r, tag):
    c = _candles()
    cd = _cands(c)
    horizon = 12
    m = multi_r_labels(c, cd, target_rs=(1.0, 1.5, 2.0, 2.5, 3.0), horizon=horizon)
    ref = label_candidates(c, cd, horizon=horizon, target_r=r)
    assert m.index.equals(cd.index)
    for src, dst in (("label", f"label_{tag}"), ("label_end_ts", f"label_end_ts_{tag}"),
                     ("barrier_net_r", f"barrier_net_r_{tag}")):
        pd.testing.assert_series_equal(m[dst], ref[src], check_names=False, check_exact=True)


def test_multi_r_column_names_and_unresolved():
    c = _candles()
    cd = _cands(c)
    m = multi_r_labels(c, cd, horizon=12)        # default 1, 1.5, 2 ; default horizon 72 leaves tail unresolved
    for tag in ("1r", "1p5r", "2r"):
        for p in ("label", "label_end_ts", "barrier_net_r"):
            assert f"{p}_{tag}" in m.columns
    m12 = multi_r_labels(c, cd, target_rs=(1.0,), horizon=40)
    ref = label_candidates(c, cd, horizon=40, target_r=1.0)
    assert ref["label"].isna().any()             # sanity: unresolved candidate exists
    pd.testing.assert_series_equal(m12["label_1r"], ref["label"], check_names=False, check_exact=True)
    assert m12["label_1r"].isna().equals(ref["label"].isna())


def test_multi_r_default_horizon_and_defaults_match():
    c = _candles()
    cd = _cands(c)
    m = multi_r_labels(c, cd)
    ref = label_candidates(c, cd, target_r=1.5)
    pd.testing.assert_series_equal(m["label_1p5r"], ref["label"], check_names=False, check_exact=True)


@pytest.mark.parametrize("bad", [(1.0, 1.0), (1.0, 0.0), (-1.0, 2.0), (2.0, 2.0, 1.0)])
def test_multi_r_bad_targets(bad):
    c = _candles()
    with pytest.raises(ValueError):
        multi_r_labels(c, _cands(c), target_rs=bad, horizon=12)


# ---------------------------------------------------------------- fit_platt
def _logit(p):
    return float(np.log(p / (1 - p)))


def _sample(slope, n=400, seed=5):
    rng = np.random.default_rng(seed)
    z = rng.normal(0, 1, n)
    p = 1 / (1 + np.exp(-(slope * z - 0.3)))
    y = (rng.uniform(size=n) < p).astype(float)
    return z, y


def test_platt_default_unchanged():
    z, y = _sample(1.2)
    a = fit_platt(z, y)
    assert a == fit_platt(z, y, nonneg_slope=False)
    assert a["a"] > 0


def test_platt_default_unchanged_negative_slope():
    z, y = _sample(-1.2)
    a = fit_platt(z, y)
    assert a["a"] < 0
    assert a == fit_platt(z, y, nonneg_slope=False)


def test_platt_nonneg_inverse_relationship():
    z, y = _sample(-1.5)
    r = fit_platt(z, y, nonneg_slope=True)
    assert r["a"] == 0.0
    m = float(np.clip(np.mean(y), 1e-6, 1 - 1e-6))
    assert r["b"] == pytest.approx(_logit(m), abs=1e-9)


def test_platt_nonneg_positive_same_as_unconstrained():
    z, y = _sample(1.5)
    assert fit_platt(z, y, nonneg_slope=True) == fit_platt(z, y)


@pytest.mark.parametrize("flag", [False, True])
def test_platt_degenerate(flag):
    z = np.linspace(-1, 1, 20)
    assert fit_platt(z, np.ones(20), nonneg_slope=flag) == {"a": 1.0, "b": 0.0}
    assert fit_platt(z, np.zeros(20), nonneg_slope=flag) == {"a": 1.0, "b": 0.0}
    assert fit_platt(np.array([]), np.array([]), nonneg_slope=flag) == {"a": 1.0, "b": 0.0}


def test_config_platt_flag():
    assert hasattr(config, "PLATT_NONNEG_SLOPE")
    assert config.PLATT_NONNEG_SLOPE is False
