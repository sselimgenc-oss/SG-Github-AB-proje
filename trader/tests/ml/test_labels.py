import numpy as np
import pandas as pd
import pytest

from trader_ml.config import BAR, FEE_RATE, SLIPPAGE_RATE
from trader_ml.labels import cost_in_r, label_candidates


def _candles(n=120, base=100.0):
    idx = pd.date_range("2025-03-01", periods=n, freq="1h", tz="UTC")
    return pd.DataFrame({"open": base, "high": base + 0.1, "low": base - 0.1, "close": base}, index=idx)


def _cand(df, side="long", entry=100.0, stop=99.0, target=np.nan, bar=10):
    return pd.DataFrame({"ts": [df.index[bar] + BAR], "side": [side], "planned_entry": [entry],
                         "planned_stop": [stop], "planned_target": [target]})


def test_cost_in_r_matches_design_range():
    c = cost_in_r(100.0, 99.0)          # %1 stop
    assert c == pytest.approx(2 * (FEE_RATE + SLIPPAGE_RATE) * 100)   # 0,2 R
    assert 0.18 <= float(c) <= 0.22


def test_upper_barrier_first_label_one():
    df = _candles()
    df.iloc[15, df.columns.get_loc("high")] = 102.5            # +2R (R=1) dokundu
    r = label_candidates(df, _cand(df))
    assert r["label"].iloc[0] == 1 and r["barrier_net_r"].iloc[0] == pytest.approx(2.0 - 0.2)
    assert r["label_end_ts"].iloc[0] == df.index[15] + BAR


def test_stop_first_and_same_bar_is_stop():
    df = _candles()
    df.iloc[13, df.columns.get_loc("low")] = 98.9
    df.iloc[13, df.columns.get_loc("high")] = 103.0            # ayni mumda iki bariyer -> stop once
    r = label_candidates(df, _cand(df))
    assert r["label"].iloc[0] == 0 and r["barrier_net_r"].iloc[0] == pytest.approx(-1.2)


def test_short_side():
    df = _candles()
    df.iloc[12, df.columns.get_loc("low")] = 97.9              # short +2R
    r = label_candidates(df, _cand(df, "short", 100.0, 101.0))
    assert r["label"].iloc[0] == 1


def test_time_barrier_zero_and_unresolved_nan():
    df = _candles(n=200)
    r = label_candidates(df, _cand(df))
    assert r["label"].iloc[0] == 0                              # 72 mum doldu, bariyer yok
    assert r["label_end_ts"].iloc[0] == df.index[10 + 72] + BAR
    r2 = label_candidates(df, _cand(df, bar=170))               # ufuk veri sonuna tasiyor
    assert np.isnan(r2["label"].iloc[0])


def test_label_uses_only_bars_after_candidate_bar():
    df = _candles()
    df.iloc[10, df.columns.get_loc("high")] = 110.0            # aday mumun kendisi: sayilmaz
    df.iloc[10, df.columns.get_loc("low")] = 90.0
    assert label_candidates(df, _cand(df))["label"].iloc[0] == 0


def test_reference_net_r_target_and_costs():
    df = _candles()
    df.iloc[14, df.columns.get_loc("high")] = 101.6
    r = label_candidates(df, _cand(df, target=101.5))
    assert r["net_r"].iloc[0] == pytest.approx(1.5 - 0.2)
