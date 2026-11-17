import numpy as np
import pandas as pd
import pytest

from trader_ml import config, models
from trader_ml.config import BAR
from trader_ml.labels import label_candidates, multi_r_labels
from trader_ml.weights import (average_uniqueness, sample_weights_v2, time_decay_weights,
                               uniqueness_weights)

T0 = pd.Timestamp("2025-03-01", tz="UTC")


def H(*h):
    return pd.Series([T0 + pd.Timedelta(hours=x) for x in h])


def test_afml_hand_example():
    # A [0,3), B [2,4), C [3,5): c = 1,1,2,2,1
    u = average_uniqueness(H(0, 2, 3), H(3, 4, 5))
    assert u == pytest.approx([5 / 6, 0.5, 0.75])
    w = uniqueness_weights(H(0, 2, 3), H(3, 4, 5))
    assert w.mean() == pytest.approx(1.0)
    assert w == pytest.approx(np.array([5 / 6, 0.5, 0.75]) * 3 / 2.0833333333333335)


def test_isolated_empty_nat_and_floor():
    assert average_uniqueness(H(0), H(5))[0] == 1.0
    assert average_uniqueness(H(2), H(2))[0] == 1.0           # bos aralik -> tek mum
    assert average_uniqueness([], []).size == 0
    with pytest.raises(ValueError):
        average_uniqueness(pd.Series([pd.NaT]), H(1))
    # start 0:30 -> bar 0; end 1:30 -> bars 0,1; other event occupies bar 1 only
    s = pd.Series([T0 + pd.Timedelta(minutes=30), T0 + pd.Timedelta(hours=1)])
    e = pd.Series([T0 + pd.Timedelta(minutes=90), T0 + pd.Timedelta(hours=1)])
    assert average_uniqueness(s, e) == pytest.approx([0.75, 0.5])


def test_time_decay():
    u = np.ones(5)
    ts = H(4, 0, 3, 1, 2)                                      # karisik giris sirasi
    w = time_decay_weights(u, ts, 0.3)
    assert w[0] == pytest.approx(1.0)                          # en yeni
    order = np.argsort(ts.to_numpy())
    assert np.all(np.diff(w[order]) >= 0)
    assert w[order][0] == pytest.approx(1 - 0.7 * 4 / 5)
    assert np.all(time_decay_weights(u, ts, 1.0) == 1.0)
    for bad in (-0.1, 1.1):
        with pytest.raises(ValueError):
            time_decay_weights(u, ts, bad)
    assert time_decay_weights([], [], 0.3).size == 0


def test_sample_weights_v2():
    df = pd.DataFrame({"source": ["real", "paper", "backtest"], "ts": H(0, 2, 3), "label_end_ts": H(3, 4, 5)})
    u = average_uniqueness(df["ts"], df["label_end_ts"])
    exp = (np.array([1.0, 0.7, 0.3]) * uniqueness_weights(df["ts"], df["label_end_ts"])
           * time_decay_weights(u, df["ts"], 0.3))
    assert sample_weights_v2(df) == pytest.approx(exp)


def _candles(n=300, seed=3):
    rng = np.random.default_rng(seed)
    idx = pd.date_range("2025-03-01", periods=n, freq="1h", tz="UTC")
    close = 100 + np.cumsum(rng.normal(0, 0.4, n))
    hi = close + rng.uniform(0.05, 0.8, n)
    lo = close - rng.uniform(0.05, 0.8, n)
    return pd.DataFrame({"open": close, "high": hi, "low": lo, "close": close}, index=idx)


def _cands(df, bars):
    rows = []
    for i, b in enumerate(bars):
        long = i % 2 == 0
        e = float(df["close"].iloc[b])
        rows.append({"ts": df.index[b] + BAR, "side": "long" if long else "short", "planned_entry": e,
                     "planned_stop": e - 1.0 if long else e + 1.0, "planned_target": np.nan})
    return pd.DataFrame(rows, index=pd.RangeIndex(100, 100 + len(rows)))


def test_multi_r_equals_label_candidates():
    df = _candles()
    c = _cands(df, list(range(5, 299, 7)) + [299])               # sonlar cozulmemis kalir
    m = multi_r_labels(df, c)
    assert list(m.columns) == [f"{k}_{t}" for t in ("1r", "1p5r", "2r")
                               for k in ("label", "label_end_ts", "barrier_net_r")]
    assert m.index.equals(c.index)
    for r, t in ((1.0, "1r"), (1.5, "1p5r"), (2.0, "2r")):
        ref = label_candidates(df, c, target_r=r)
        for k in ("label", "label_end_ts", "barrier_net_r"):
            pd.testing.assert_series_equal(m[f"{k}_{t}"], ref[k], check_names=False)
    assert m["label_1r"].isna().any() and m["label_1r"].notna().any()


@pytest.mark.parametrize("rs", [(1.0, 1.0), (0.0, 1.0), (-1.0,), (1.0, 1.0000)])
def test_multi_r_bad_targets(rs):
    df = _candles()
    with pytest.raises(ValueError):
        multi_r_labels(df, _cands(df, [5]), target_rs=rs)


def test_platt_nonneg():
    rng = np.random.default_rng(0)
    z = rng.normal(size=500)
    y = (rng.uniform(size=500) < 1 / (1 + np.exp(1.5 * z))).astype(float)   # egim negatif
    base = models.fit_platt(z, y)
    assert base["a"] < 0
    assert models.fit_platt(z, y, nonneg_slope=False) == base
    c = models.fit_platt(z, y, nonneg_slope=True)
    m = y.mean()
    assert c["a"] == 0.0 and c["b"] == pytest.approx(np.log(m / (1 - m)))
    yp = 1.0 - y                                                # pozitif egim -> degismez
    assert models.fit_platt(z, yp, nonneg_slope=True) == models.fit_platt(z, yp)
    assert models.fit_platt(z[:5], y[:5], nonneg_slope=True) == {"a": 1.0, "b": 0.0}


def test_config_default():
    assert config.PLATT_NONNEG_SLOPE is False
