"""ML-G5: r02/r03 v2 ozellik sarmalayicisi (egitim yolu). `trader_core.ml_features_v2.feature_frame_v2`i cagirmadan once HER cift
cercevesinde, fonlamada ve aday zamanlarinda kilitli donem korumasini (`assert_pre_holdout`) calistirir (mentor 3.2.1, G5-b)."""
from __future__ import annotations

import pandas as pd

from trader_core import ml_features_v2 as _v2
from trader_core.ml_features_v2 import R02_FEATURE_NAMES, R03_FEATURE_NAMES, RECIPES  # noqa: F401

from .guards import assert_pre_holdout


def feature_frame_v2(pairs: dict[str, pd.DataFrame], cands: pd.DataFrame, *,
                     funding: dict[str, pd.DataFrame] | None = None, recipe: str) -> pd.DataFrame:
    """Kilitli donem korumali v2 ozellik uretici; cikti `trader_core.ml_features_v2.feature_frame_v2` ile ayni."""
    for p, df in pairs.items():
        assert_pre_holdout(df.index, f"mum verisi {p}")
    for p, f in (funding or {}).items():
        if f is not None and len(f):
            assert_pre_holdout(f.index, f"fonlama {p}")
    if len(cands):
        assert_pre_holdout(pd.DatetimeIndex(pd.to_datetime(cands["ts"], utc=True)), "aday zamani")
    return _v2.feature_frame_v2(pairs, cands, funding=funding, recipe=recipe)
