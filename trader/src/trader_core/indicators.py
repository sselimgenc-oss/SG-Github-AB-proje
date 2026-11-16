# Portions of this file (indicator math and the regime-label interface skeleton)
# are adapted from regime-trading-bot (https://github.com/danny123-sudo/regime-trading-bot,
# commit 508d7d9), licensed under the MIT License.
#
# MIT License
#
# Copyright (c) 2026 danny123-sudo
#
# Permission is hereby granted, free of charge, to any person obtaining a copy
# of this software and associated documentation files (the "Software"), to deal
# in the Software without restriction, including without limitation the rights
# to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
# copies of the Software, and to permit persons to whom the Software is
# furnished to do so, subject to the following conditions:
#
# The above copyright notice and this permission notice shall be included in all
# copies or substantial portions of the Software.
#
# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
# IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
# FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
# AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
# LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
# OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
# SOFTWARE.
#
# Modifications: NaN warm-up, state-carrying NaN policy, label set and all
# classification rules are original to this project (see docs/rejim-spec.md).
"""Gosterge matematigi: EMA, SMA, true range, ATR (Wilder). Yalnizca pandas + numpy.

Formuller ve NaN/isinma kurallari docs/rejim-spec.md ile birebir aynidir.
"""
from __future__ import annotations

import numbers

import numpy as np
import pandas as pd


def _check_length(length) -> int:
    if isinstance(length, bool) or not isinstance(length, numbers.Integral) or int(length) < 1:
        raise ValueError(f"length tam sayi >= 1 olmali: {length!r}")
    return int(length)


def _to_float_series(series, name: str = "series") -> pd.Series:
    if not isinstance(series, pd.Series):
        raise ValueError(f"{name} pandas.Series olmali")
    s = pd.to_numeric(series, errors="coerce").astype("float64")
    if np.isinf(s.to_numpy()).any():
        raise ValueError(f"{name} sonsuz deger iceriyor")
    return s


def _recursive(x: np.ndarray, alpha: float, length: int, wilder: bool = False) -> np.ndarray:
    """e_t = e_{t-1} + alpha*(x_t - e_{t-1}); ilk gercek gozlem tohum; NaN'da durum tasinir."""
    out = np.full(len(x), np.nan)
    state = None
    count = 0
    for i, v in enumerate(x):
        if np.isnan(v):
            continue
        if state is None:
            state = v
        elif wilder:
            state = state + (v - state) / length
        else:
            state = alpha * v + (1.0 - alpha) * state
        count += 1
        if count >= length:
            out[i] = state
    return out


def ema(series: pd.Series, length: int) -> pd.Series:
    length = _check_length(length)
    s = _to_float_series(series)
    alpha = 2.0 / (length + 1)
    return pd.Series(_recursive(s.to_numpy(), alpha, length), index=s.index, name=series.name)


def sma(series: pd.Series, length: int) -> pd.Series:
    length = _check_length(length)
    s = _to_float_series(series)
    return s.rolling(length, min_periods=length).mean()


def true_range(df: pd.DataFrame) -> pd.Series:
    if not isinstance(df, pd.DataFrame):
        raise ValueError("df pandas.DataFrame olmali")
    for c in ("high", "low", "close"):
        if c not in df.columns:
            raise ValueError(f"zorunlu sutun yok: {c}")
    high = _to_float_series(df["high"], "high")
    low = _to_float_series(df["low"], "low")
    close = _to_float_series(df["close"], "close")
    prev = close.shift(1)
    parts = pd.concat([high - low, (high - prev).abs(), (low - prev).abs()], axis=1)
    tr = parts.max(axis=1, skipna=True)
    tr[high.isna() | low.isna()] = np.nan
    tr.name = None
    return tr


def atr(df: pd.DataFrame, length: int = 14) -> pd.Series:
    length = _check_length(length)
    tr = true_range(df)
    return pd.Series(_recursive(tr.to_numpy(), 1.0 / length, length, wilder=True), index=tr.index)
