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


# ------------------------------------------------------------------ mentor G2 duzeltmeleri (17 Kas)
def test_decay_same_ts_permutation_invariant():                 # G2-1
    rng = np.random.default_rng(5)
    ts = H(*([0] * 4 + [3] * 3 + [5] + [9] * 2))
    end = ts + pd.Timedelta(hours=4)
    df = pd.DataFrame({"source": "backtest", "ts": ts, "label_end_ts": end})
    w = sample_weights_v2(df)
    for _ in range(10):
        p = rng.permutation(len(df))
        wp = sample_weights_v2(df.iloc[p].reset_index(drop=True))
        inv = np.empty(len(df))
        inv[p] = wp
        np.testing.assert_allclose(inv, w, atol=1e-12)
    # esit-ts grubundaki her olay ayni azalma carpanina sahip; en yeni grup = 1
    u = np.ones(len(ts))
    d = time_decay_weights(u, ts, 0.3)
    assert len(set(np.round(d[:4], 12))) == 1 and len(set(np.round(d[4:7], 12))) == 1
    assert d[-2:] == pytest.approx([1.0, 1.0])
    assert d[0] == pytest.approx(1 - 0.7 * 6 / 10)               # grup sonu kumulatifi 4/10 -> 1-.7*(10-4)/10


def test_sample_weights_v2_must_be_per_training_fold():         # G2-2
    assert "EGITIM" in sample_weights_v2.__doc__ and "arindirma" in sample_weights_v2.__doc__
    ts = H(*range(0, 40, 2))
    df = pd.DataFrame({"source": "real", "ts": ts, "label_end_ts": ts + pd.Timedelta(hours=10)})
    full = sample_weights_v2(df)
    sub = df.iloc[:10]
    # tum tabloda hesaplayip dilime kesmek != dilimin kendi satirlarinda hesaplamak (gelecek bilgisi sizar)
    assert not np.allclose(full[:10], sample_weights_v2(sub))
    assert sample_weights_v2(sub).mean() == pytest.approx(sample_weights_v2(sub).mean())
    assert uniqueness_weights(sub["ts"], sub["label_end_ts"]).mean() == pytest.approx(1.0)


def _labelled(table):
    return table[table["label"].notna()].reset_index(drop=True)


def test_recipe_weight_switch_default_is_old_weights(table, monkeypatch):    # G2-3
    from trader_ml import pipeline, weights
    assert config.WEIGHT_SCHEME == "age_decay"
    t = _labelled(table)
    names = [c for c in t.columns if c.startswith("f_")]
    calls = []
    orig = weights.sample_weights_v2
    monkeypatch.setattr(weights, "sample_weights_v2", lambda df, **k: (calls.append(df), orig(df, **k))[1])
    pipeline.run_oof(t, names, require_lightgbm=False)
    assert calls == []                                            # r01: eski agirliklar
    old = models.training_weights(t)
    np.testing.assert_array_equal(old, models.sample_weights(t, t["ts"].max()))
    folds, *_ = pipeline.run_oof(t, names, require_lightgbm=False, weight_scheme="uniq_decay")
    assert len(calls) >= 1
    trains = [f["train_rows"] for f in folds if len(f["train_rows"]) >= 100 and len(f["test_rows"])]
    assert [len(c) for c in calls] == [len(tr) for tr in trains]
    for c, tr in zip(calls, trains):
        assert c.index.equals(t.iloc[tr].index)                   # yalniz dilimin egitim satirlari
    with pytest.raises(ValueError):
        models.training_weights(t, "nope")


def _oof_negative_slope(n=600, seed=2):
    rng = np.random.default_rng(seed)
    fold = np.repeat([0, 1, 2, 3], n // 4)
    z = rng.normal(size=n)
    lab = (rng.uniform(size=n) < 1 / (1 + np.exp(1.5 * z))).astype(float)      # z arttikca etiket AZALIR
    ts = pd.Timestamp("2025-03-01", tz="UTC") + pd.to_timedelta(np.arange(n) * 3, unit="h")
    df = pd.DataFrame({"ts": ts, "fold": fold, "taken": True, "label": lab, "net_r": rng.normal(0, 1, n), "z_m": z})
    df["label_end_ts"] = df["ts"] + 5 * BAR
    df["exit_ts"] = df["ts"] + 3 * BAR
    df["test_start"] = df.groupby("fold")["ts"].transform("min")
    return df


def test_platt_clamped_flag_and_forward_count(monkeypatch):    # G2-4
    z = np.random.default_rng(0).normal(size=400)
    y = (np.random.default_rng(1).uniform(size=400) < 1 / (1 + np.exp(1.5 * z))).astype(float)
    cal, cl = models.fit_platt_info(z, y, nonneg_slope=True)
    assert cl is True and cal["a"] == 0.0
    assert models.fit_platt_info(z, y, nonneg_slope=False)[1] is False
    assert models.fit_platt_info(z, 1.0 - y, nonneg_slope=True)[1] is False
    assert models.fit_platt_info(z[:5], y[:5], nonneg_slope=True)[1] is False
    from trader_ml import pipeline
    oof = _oof_negative_slope()
    assert pipeline.forward_calibrate(oof, ["m"]) == {"m": 0}      # varsayilan: kisit yok -> sayim 0
    monkeypatch.setattr(config, "PLATT_NONNEG_SLOPE", True)
    oof2 = _oof_negative_slope()
    counts = pipeline.forward_calibrate(oof2, ["m"])
    assert counts["m"] == 3                                        # dilim 1..3 (dilim 0 ozdeslik/yanma)
    f1 = oof2[oof2["fold"] == 1]["p_m"]
    assert f1.nunique() == 1                                       # sabit p = onceki taban oran
    t0 = oof2.loc[oof2["fold"] == 1, "test_start"].iloc[0]
    prior = oof2[(oof2["fold"] == 0) & (oof2["known_ts"] < t0)]
    assert f1.iloc[0] == pytest.approx(prior["label"].mean(), abs=1e-5)


def test_report_counts_clamped_folds_and_package_refused(table, tmp_path, monkeypatch):    # G2-4
    pytest.importorskip("lightgbm")
    from trader_ml import pipeline
    real = models.fit_platt_info
    monkeypatch.setattr(config, "PLATT_NONNEG_SLOPE", True)
    monkeypatch.setattr(pipeline.models, "fit_platt_info", lambda z, y, *a, **k: (real(z, y, *a, **k)[0], True))
    with pytest.raises(pipeline.CalibrationClamped):
        pipeline.run(table, tmp_path / "a", synthetic=True, n_boot=50, n_trials=2)
    assert not (tmp_path / "a" / "model_candidate.json").exists()
    # rapor: sayim satiri
    from trader_ml.report import render_report  # noqa: F401  (imza: calibration=)
    import inspect
    assert "calibration" in inspect.signature(render_report).parameters


def test_report_and_summary_list_clamped_folds(table, tmp_path):    # G2-4
    pytest.importorskip("lightgbm")
    from trader_ml import pipeline
    s = pipeline.run(table, tmp_path, synthetic=True, n_boot=50, n_trials=2)
    assert set(s["platt_clamped_folds"]) >= {"logistic"} and s["weight_scheme"] == "age_decay"
    md = (tmp_path / "gate_report.md").read_text(encoding="utf-8")
    assert "kısıtlanan" in md and "age_decay" in md
