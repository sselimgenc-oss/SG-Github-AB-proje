"""S2-1 uygulama dumani (s2-on-kayit §5); bagimsiz H-1..H-12 testlerinden ayri."""
from __future__ import annotations

import numpy as np
import pandas as pd

from trader_core import signals as S
from trader_engine.strategies import registry as REG
from trader_engine.strategies.base import StrategyContext, validate_table
from trader_engine.strategies.price_action_v1_4h import H4ExitPolicy, make_v1b_4h


_P = {k: getattr(S.DEFAULT_SIGNAL_PARAMS, k) for k in S._PARAM_KEYS}


def _bars(n4=700, seed=3):
    rng = np.random.default_rng(seed)
    i1 = pd.date_range("2024-01-01", periods=n4 * 4, freq="1h", tz="UTC")
    c = 100 * np.exp(np.cumsum(rng.normal(0, 0.004, len(i1))))
    o = np.concatenate([[c[0]], c[:-1]])
    h = np.maximum(o, c) * (1 + np.abs(rng.normal(0, 0.002, len(i1))))
    l = np.minimum(o, c) * (1 - np.abs(rng.normal(0, 0.002, len(i1))))
    d1 = pd.DataFrame({"open": o, "high": h, "low": l, "close": c, "volume": 1.0}, index=i1)
    d4 = d1.resample("4h").agg({"open": "first", "high": "max", "low": "min", "close": "last", "volume": "sum"})
    return d1, d4


def test_compute_schema_grid_and_causality():
    st = make_v1b_4h()
    d1, d4 = _bars()
    ctx = StrategyContext(pair="X", D=d1.index[-1], tf="1h", params=_P, bars={"1h": d1, "4h": d4})
    sig = st.compute(ctx)
    validate_table(sig, st.info, d1.index)
    on = sig.index.hour % 4 == 3
    assert (sig.loc[~on, "reasons"] == "s2_1:off_grid").all() and not sig.loc[~on, "signal"].any()
    assert sig.loc[sig["signal"]].index.hour.isin([3, 7, 11, 15, 19, 23]).all()
    assert sig["signal"].any()
    k = 2000
    cut = st.compute(StrategyContext(pair="X", D=d1.index[k], tf="1h", params=_P,
                                     bars={"1h": d1.iloc[:k + 1], "4h": d4[d4.index + pd.Timedelta(hours=4) <= d1.index[k] + pd.Timedelta(hours=1)]}))
    pd.testing.assert_frame_equal(cut, sig.iloc[:k + 1])


def test_exit_policy_none_and_force():
    pol = make_v1b_4h().exit_policy()
    assert isinstance(pol, H4ExitPolicy)
    assert pol.evaluate(None, None).reason == "force_exit"


def test_static_registry_unchanged():
    assert "price_action_v1_4h" not in REG.list_strategies()
