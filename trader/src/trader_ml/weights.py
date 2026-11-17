# SPDX-License-Identifier: MIT
# Copyright (c) 2025 zero-was-here (Aurum v2)
#
# Source: Aurum v2 aurum/labels/triple_barrier.py lines 618-687 (average_uniqueness,
# uniqueness_weights, time_decay_weights), commit 49f073dfdb2f8831e2fcb39b321c1a02bc4bba5f,
# MIT licensed; see THIRD_PARTY_NOTICES.md. Local changes: spans are timestamps on the 1h BAR
# grid (bar occupies floor(start) <= t < end), uniqueness normalised to mean exactly 1,
# time decay takes an `oldest` weight and orders by ts; no scipy/new dependency.
"""Ornek benzersizligi (AFML 4.4) ve zaman azalmasi (AFML 4.5) agirliklari. Opt-in (ML-G2)."""
from __future__ import annotations

import numpy as np
import pandas as pd

from .config import BAR, SOURCE_WEIGHTS

_BAR_NS = int(BAR.value)


def _to_ns(x, name: str) -> np.ndarray:
    idx = pd.DatetimeIndex(pd.to_datetime(pd.Series(np.asarray(x) if not isinstance(x, pd.Series) else x.to_numpy())))
    if idx.isna().any():
        raise ValueError(f"{name}: NaT yasak")
    if idx.tz is not None:
        idx = idx.tz_convert("UTC").tz_localize(None)
    return idx.as_unit("ns").asi8.astype(np.int64)


def average_uniqueness(start, end) -> np.ndarray:
    s_ns, e_ns = _to_ns(start, "start"), _to_ns(end, "end")
    if s_ns.shape != e_ns.shape:
        raise ValueError("start ve end ayni uzunlukta olmali")
    if s_ns.size == 0:
        return np.empty(0)
    s = np.floor_divide(s_ns, _BAR_NS)
    e = -np.floor_divide(-e_ns, _BAR_NS)            # ceil: son mum t < end (end dislayici)
    e = np.maximum(e, s + 1)                        # bos aralik -> tek mum floor(start)
    base = int(s.min())
    n = int(e.max()) - base
    diff = np.zeros(n + 1, dtype=np.int64)
    np.add.at(diff, s - base, 1)
    np.add.at(diff, e - base, -1)
    c = np.cumsum(diff)[:n]
    inv = np.where(c > 0, 1.0 / np.maximum(c, 1), 0.0)
    cs = np.r_[0.0, np.cumsum(inv)]
    total = cs[e - base] - cs[s - base]
    return total / (e - s).astype(float)


def uniqueness_weights(start, end) -> np.ndarray:
    u = average_uniqueness(start, end)
    if u.size == 0:
        return u
    return u * u.size / u.sum()


def time_decay_weights(uniqueness, ts, oldest: float = 0.3) -> np.ndarray:
    if not 0.0 <= oldest <= 1.0:
        raise ValueError("oldest [0, 1] araliginda olmali")
    u = np.asarray(uniqueness, dtype=float)
    if u.size == 0:
        return u
    t = _to_ns(ts, "ts")
    order = np.argsort(t, kind="stable")
    x = np.cumsum(u[order])
    slope = (1.0 - oldest) / x[-1]
    const = 1.0 - slope * x[-1]
    w_sorted = np.maximum(const + slope * x, 0.0)
    out = np.empty_like(w_sorted)
    out[order] = w_sorted
    return out


def sample_weights_v2(df: pd.DataFrame, *, oldest: float = 0.3) -> np.ndarray:
    base = df["source"].map(SOURCE_WEIGHTS).to_numpy(float)
    ts, end = df["ts"], df["label_end_ts"]
    u = average_uniqueness(ts, end)
    return base * uniqueness_weights(ts, end) * time_decay_weights(u, ts, oldest)
