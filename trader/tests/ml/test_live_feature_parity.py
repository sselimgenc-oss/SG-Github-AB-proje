"""19a/19d: karar anindaki (canli yol) ozellikler == egitim yolundaki ozellikler (ayni bar, ayni kod).

Canli yol: motor stratejisi `price_action_v1_ml.compute` -> `trader_core.ml_features.feature_frame` (pencereli mumlar).
Egitim yolu: `trader_ml.features.feature_frame` (tum gecmis) -> `candidate_rows`. Ikisi de AYNI cekirdek fonksiyonu cagirir;
fark yalniz pencere (EMA/ATR isinma etkisi) ve tablo duzeyindeki `f_bars_since_exit` (canlida NaN; bkz. 05 §13.4a)."""
from __future__ import annotations

from datetime import timedelta

import numpy as np
import pandas as pd
import pytest

from trader_core import ml_features as core_feat
from trader_core.signals import DEFAULT_SIGNAL_PARAMS
from trader_core import ledger as L
from trader_engine.bars import WINDOW_4H, WINDOW_TRIGGER
from trader_engine.strategies.base import StrategyContext
from trader_engine.strategies.price_action_v1_ml import make_v1b_ml
from trader_ml import features as train_feat
from trader_ml.features import FEATURE_NAMES, candidate_rows, feature_frame

PAIR = "SOL/USDT:USDT"
BSE = FEATURE_NAMES.index("f_bars_since_exit")
OHLC = {"open": "first", "high": "max", "low": "min", "close": "last"}


class _CaptureModel:
    """MlModelView benzeri (duck-typed): puanlamaya giren X'i yakalar."""
    threshold = 0.5
    features = tuple(FEATURE_NAMES)
    user_approved = True

    def __init__(self):
        self.X = None

    def expired(self, now):
        return False

    def score(self, X):
        self.X = np.array(X, dtype=float)
        return np.full(len(X), 0.6)


def _ctx(df, open_t, model):
    d1 = df.loc[:open_t, ["open", "high", "low", "close"]].tail(WINDOW_TRIGGER["1h"])
    D = open_t + timedelta(hours=1)
    h4 = df.loc[:open_t, ["open", "high", "low", "close"]].resample("4h", label="left", closed="left").agg(OHLC).dropna()
    h4 = h4[h4.index + timedelta(hours=4) <= D].tail(WINDOW_4H)
    params = {k: getattr(DEFAULT_SIGNAL_PARAMS, k) for k in L.PARAM_KEYS}
    return StrategyContext(pair="SOL/USDT", D=D.to_pydatetime(), tf="1h", params=params,
                           bars={"1h": d1, "4h": h4}, last_exit=None, model=model)


def test_core_and_training_feature_frames_are_the_same_function(candles):
    df = candles[PAIR].iloc[:5000]
    a = core_feat.feature_frame(df)
    b = train_feat.feature_frame(df)
    pd.testing.assert_frame_equal(a, b, check_exact=True)
    assert train_feat.FEATURE_NAMES is core_feat.FEATURE_NAMES


def test_live_path_features_equal_training_path_for_same_bar(candles):
    df = candles[PAIR]
    full = candidate_rows(feature_frame(df, None, None), PAIR)           # egitim yolu (tum gecmis)
    full = full[full["ts"] >= df.index[0] + pd.Timedelta(hours=2500)]
    assert len(full) >= 5
    strat = make_v1b_ml()
    strat.set_ml_mode("shadow")
    checked = 0
    for _, r in full.head(25).iterrows():
        open_t = r["ts"] - pd.Timedelta(hours=1)
        model = _CaptureModel()
        ctx = _ctx(df, open_t, model)
        out = strat.compute(ctx)
        if not bool(out["signal"].iloc[-1]):
            continue                                                       # pencere farki adayi dusurdu: karsilastirilmaz
        assert model.X is not None and model.X.shape == (1, len(FEATURE_NAMES))
        live = model.X[0]
        train = r[FEATURE_NAMES].to_numpy(dtype=float)
        nan_l, nan_t = np.isnan(live), np.isnan(train)
        nan_l[BSE], nan_t[BSE] = False, False
        assert (nan_l == nan_t).all(), "NaN deseni ayni olmali (BTC/ETH/fonlama canlida NaN, egitimde BTC/ETH yok -> ayni)"
        for j, nm in enumerate(FEATURE_NAMES):
            if j == BSE or nan_l[j]:
                continue
            # 1g egimi ATR(14) Wilder ozyinelemesi: 1500 saatlik canli pencerede (62 gun) isinma farki <= ~%2 (belgeli sinir)
            tol = 3e-2 if nm == "f_slope_1d" else 1e-6
            np.testing.assert_allclose(live[j], train[j], rtol=tol, atol=tol, err_msg=nm)
        assert np.isnan(live[BSE])    # canlida tablo duzeyinde bilinmez (belgeli sinir)
        assert str(out["reasons"].iloc[-1]).startswith("ml:p=0.600000|")
        checked += 1
    assert checked >= 3


def test_live_path_never_leaks_future(candles):
    """Karar barindan sonraki mumlar canli yolda yok; bozulsalar bile ozellik ayni (egitim kati nedensel testinin canli esi)."""
    df = candles[PAIR]
    full = candidate_rows(feature_frame(df, None, None), PAIR)
    r = full[full["ts"] >= df.index[0] + pd.Timedelta(hours=2500)].iloc[0]
    open_t = r["ts"] - pd.Timedelta(hours=1)
    strat = make_v1b_ml()
    strat.set_ml_mode("shadow")
    m1, m2 = _CaptureModel(), _CaptureModel()
    c1 = _ctx(df, open_t, m1)
    strat.compute(c1)
    df2 = df.copy()
    df2.loc[df2.index > open_t, ["open", "high", "low", "close"]] *= 3.0
    strat.compute(_ctx(df2, open_t, m2))
    np.testing.assert_array_equal(m1.X, m2.X)
