"""Kilitli donem (2026-05 -> 2026-10) egitim kodunca okunamaz."""
import pandas as pd
import pytest

from trader_ml import fixture, pipeline
from trader_ml.features import feature_frame
from trader_ml.guards import HoldoutViolation, assert_pre_holdout
from trader_ml.labels import label_candidates
from trader_ml.schema import validate_candidates
from trader_ml.walkforward import make_folds


def test_assert_pre_holdout_boundary():
    assert_pre_holdout(pd.to_datetime(["2026-04-30 23:00"], utc=True))
    with pytest.raises(HoldoutViolation):
        assert_pre_holdout(pd.to_datetime(["2026-05-01 00:00"], utc=True))
    with pytest.raises(HoldoutViolation):
        assert_pre_holdout(pd.DatetimeIndex(["2026-07-01"]))        # naif -> UTC kabul


def test_synthetic_fixture_stops_before_holdout(candles):
    assert max(d.index.max() for d in candles.values()) < pd.Timestamp("2026-05-01", tz="UTC")


def test_candles_in_holdout_rejected(candles):
    c = candles["BTC/USDT:USDT"]
    bad = pd.concat([c, c.iloc[-5:].set_axis(pd.date_range("2026-05-01", periods=5, freq="1h", tz="UTC"))])
    with pytest.raises(HoldoutViolation):
        feature_frame(bad)
    with pytest.raises(HoldoutViolation):
        label_candidates(bad, pd.DataFrame({"ts": [], "side": [], "planned_entry": [], "planned_stop": [],
                                            "planned_target": []}))


def test_candidate_table_rows_in_holdout_rejected(table):
    bad = table.copy()
    bad.loc[bad.index[-1], "ts"] = pd.Timestamp("2026-06-01", tz="UTC")
    with pytest.raises(HoldoutViolation):
        validate_candidates(bad)
    bad2 = table.copy()                                            # etiket ufku kilitli doneme tasarsa da
    bad2.loc[bad2.index[-1], "label_end_ts"] = pd.Timestamp("2026-05-02", tz="UTC")
    with pytest.raises(HoldoutViolation):
        validate_candidates(bad2)


def test_pipeline_and_folds_refuse_holdout(table, tmp_path):
    bad = table.copy()
    bad.loc[bad.index[-1], "ts"] = pd.Timestamp("2026-05-15", tz="UTC")
    with pytest.raises(HoldoutViolation):
        pipeline.run(bad, tmp_path)
    with pytest.raises(HoldoutViolation):
        make_folds(bad)


def test_no_fold_reaches_holdout(table):
    for f in make_folds(table):
        assert f["test_end"] <= pd.Timestamp("2026-05-01", tz="UTC")
