"""M1 ozellik tek kaynagi: egitim (trader_ml.pa_proposer.features) ve canli (trader_core.pa_features) ayni fonksiyon."""
import numpy as np

from trader_core import pa_features as CF
from trader_ml.pa_proposer import features as TF


def test_training_reexports_live_definitions():
    for name in ("feature_vector", "feature_matrix", "atr_at", "FEATURE_NAMES", "WINDOW", "STOP_ATR", "TARGET_ATR",
                 "HORIZON", "SIDE_SIGN"):
        assert getattr(TF, name) is getattr(CF, name), name


def test_numerically_identical_on_random_series():
    rng = np.random.default_rng(7)
    n = 200
    c = 100 + np.cumsum(rng.normal(0, 1, n))
    o = c + rng.normal(0, 0.3, n)
    h = np.maximum(o, c) + np.abs(rng.normal(0, 0.5, n))
    l = np.minimum(o, c) - np.abs(rng.normal(0, 0.5, n))
    for side in ("long", "short"):
        for i in (CF.WINDOW - 1, 120, n - 1):
            a, b = CF.feature_vector(o, h, l, c, i, side), TF.feature_vector(o, h, l, c, i, side)
            assert (a is None and b is None) or np.array_equal(a, b)
    assert CF.atr_at(h, l, c, n - 1) == TF.atr_at(h, l, c, n - 1)
