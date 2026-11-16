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
"""Rejim etiketi (trend_up / trend_down / range / volatile / unclear).

Kurallar docs/rejim-spec.md ile birebir aynidir. Ileriye bakmaz; hata durumunda
classify_last her zaman UNCLEAR (kapali) doner.
"""
from __future__ import annotations

import math
import numbers
from dataclasses import dataclass
from enum import Enum

import numpy as np
import pandas as pd

from .indicators import atr, ema, sma

ATR_LEN = 14
EMA_FAST, EMA_MID, EMA_SLOW = 20, 50, 100
RANGE_WINDOW = 20
MIN_EDGE_TOUCHES = 2
VOL_AVG_WINDOW = 100
MIN_BARS = 113

_OUT_COLUMNS = ["regime", "rh", "rl", "rh_touches", "rl_touches", "atr", "atr_ratio"]


class Regime(str, Enum):
    TREND_UP = "trend_up"
    TREND_DOWN = "trend_down"
    RANGE = "range"
    VOLATILE = "volatile"
    UNCLEAR = "unclear"


def _as_float(name: str, v) -> float:
    if isinstance(v, bool) or not isinstance(v, (int, float, numbers.Real)):
        raise ValueError(f"{name} sayi olmali: {v!r}")
    try:
        f = float(v)
    except Exception as e:  # pragma: no cover
        raise ValueError(f"{name} sayiya cevrilemedi: {v!r}") from e
    if not math.isfinite(f):
        raise ValueError(f"{name} sonlu olmali: {v!r}")
    return f


@dataclass(frozen=True)
class RegimeParams:
    range_width_atr: float = 4.0
    vol_ratio_max: float = 1.5
    edge_zone_atr: float = 0.25

    def __post_init__(self):
        for name, lo, hi in (("range_width_atr", 3.0, 6.0),
                             ("vol_ratio_max", 1.25, 2.0),
                             ("edge_zone_atr", 0.15, 0.50)):
            f = _as_float(name, getattr(self, name))
            if not (lo <= f <= hi):
                raise ValueError(f"{name} {lo}-{hi} disinda: {f}")
            object.__setattr__(self, name, f)


DEFAULT_PARAMS = RegimeParams()
LESSON_BOUNDS = {"vol_ratio_max": (1.3, 1.7)}


@dataclass(frozen=True)
class RegimeResult:
    regime: Regime
    rh: float | None
    rl: float | None
    rh_touches: int
    rl_touches: int
    atr: float | None
    atr_ratio: float | None
    reason: str

    @property
    def tradeable(self) -> bool:
        return self.regime in (Regime.TREND_UP, Regime.TREND_DOWN, Regime.RANGE)


def _runs(mask: np.ndarray) -> int:
    if mask.size == 0:
        return 0
    prev = np.concatenate(([False], mask[:-1]))
    return int(np.count_nonzero(mask & ~prev))


def count_edge_touches(highs, lows, rh, rl, zone) -> tuple[int, int]:
    h = np.asarray(highs, dtype=float)
    l = np.asarray(lows, dtype=float)
    if h.ndim != 1 or l.ndim != 1:
        raise ValueError("highs/lows 1 boyutlu olmali")
    if h.shape != l.shape:
        raise ValueError("highs ve lows ayni uzunlukta olmali")
    z = _as_float("zone", zone)
    if z < 0:
        raise ValueError("zone >= 0 olmali")
    if h.size == 0:
        return (0, 0)
    return (_runs(h >= rh - z), _runs(l <= rl + z))


def _check_structure(df) -> None:
    if not isinstance(df, pd.DataFrame):
        raise ValueError("df pandas.DataFrame olmali")
    if len(df) == 0:
        return
    missing = [c for c in ("open", "high", "low", "close") if c not in df.columns]
    if missing:
        raise ValueError(f"zorunlu sutun yok: {missing}")
    if not (df.index.is_monotonic_increasing and df.index.is_unique):
        raise ValueError("indeks kesin artan ve tekrarsiz olmali")


def _empty_result(index) -> pd.DataFrame:
    return pd.DataFrame({
        "regime": pd.Series([], index=index, dtype=object),
        "rh": pd.Series([], index=index, dtype="float64"),
        "rl": pd.Series([], index=index, dtype="float64"),
        "rh_touches": pd.Series([], index=index, dtype="int64"),
        "rl_touches": pd.Series([], index=index, dtype="int64"),
        "atr": pd.Series([], index=index, dtype="float64"),
        "atr_ratio": pd.Series([], index=index, dtype="float64"),
    })


def _fmt(x: float) -> str:
    return f"{x:.4g}"


def classify_series(df: pd.DataFrame, params: RegimeParams = DEFAULT_PARAMS) -> pd.DataFrame:
    _check_structure(df)
    if not isinstance(params, RegimeParams):
        raise ValueError("params RegimeParams olmali")
    n = len(df)
    if n == 0:
        return _empty_result(df.index)

    o = pd.to_numeric(df["open"], errors="coerce").astype("float64").to_numpy()
    h = pd.to_numeric(df["high"], errors="coerce").astype("float64").to_numpy()
    lo = pd.to_numeric(df["low"], errors="coerce").astype("float64").to_numpy()
    c = pd.to_numeric(df["close"], errors="coerce").astype("float64").to_numpy()

    with np.errstate(invalid="ignore"):
        valid = (np.isfinite(o) & np.isfinite(h) & np.isfinite(lo) & np.isfinite(c)
                 & (o > 0) & (h > 0) & (lo > 0) & (c > 0) & (h >= lo)
                 & (c <= h) & (c >= lo) & (o <= h) & (o >= lo))

    clean = pd.DataFrame({
        "open": np.where(valid, o, np.nan), "high": np.where(valid, h, np.nan),
        "low": np.where(valid, lo, np.nan), "close": np.where(valid, c, np.nan),
    }, index=df.index)

    atr_s = atr(clean, ATR_LEN)
    e20 = ema(clean["close"], EMA_FAST).to_numpy()
    e50 = ema(clean["close"], EMA_MID).to_numpy()
    e100 = ema(clean["close"], EMA_SLOW).to_numpy()
    avg_s = sma(atr_s, VOL_AVG_WINDOW)
    atr_a = atr_s.to_numpy()
    avg_a = avg_s.to_numpy()
    hs, ls = clean["high"], clean["low"]
    rh_roll = hs.rolling(RANGE_WINDOW, min_periods=RANGE_WINDOW).max().to_numpy()
    rl_roll = ls.rolling(RANGE_WINDOW, min_periods=RANGE_WINDOW).min().to_numpy()
    ch, cl, cc = clean["high"].to_numpy(), clean["low"].to_numpy(), clean["close"].to_numpy()

    with np.errstate(invalid="ignore", divide="ignore"):
        ratio_a = np.where(np.isfinite(atr_a) & np.isfinite(avg_a) & (avg_a > 0),
                           atr_a / avg_a, np.nan)

    reg = np.full(n, Regime.UNCLEAR.value, dtype=object)
    rh_o = np.full(n, np.nan)
    rl_o = np.full(n, np.nan)
    rht = np.zeros(n, dtype="int64")
    rlt = np.zeros(n, dtype="int64")

    for t in range(MIN_BARS - 1, n):
        if not valid[t]:
            continue
        a, av = atr_a[t], avg_a[t]
        if not (np.isfinite(a) and np.isfinite(av) and np.isfinite(e20[t])
                and np.isfinite(e50[t]) and np.isfinite(e100[t])
                and np.isfinite(rh_roll[t]) and np.isfinite(rl_roll[t])):
            continue
        if a <= 0 or av <= 0:
            continue
        if ratio_a[t] > params.vol_ratio_max:
            reg[t] = Regime.VOLATILE.value
            continue
        RH, RL = rh_roll[t], rl_roll[t]
        width = (RH - RL) / a
        if width <= params.range_width_atr:
            zone = params.edge_zone_atr * a
            lo_i = t - RANGE_WINDOW + 1
            ta, tb = count_edge_touches(ch[lo_i:t + 1], cl[lo_i:t + 1], RH, RL, zone)
            if ta >= MIN_EDGE_TOUCHES and tb >= MIN_EDGE_TOUCHES:
                reg[t] = Regime.RANGE.value
                rh_o[t], rl_o[t], rht[t], rlt[t] = RH, RL, ta, tb
                continue
        if cc[t] > e100[t] and e20[t] > e50[t]:
            reg[t] = Regime.TREND_UP.value
        elif cc[t] < e100[t] and e20[t] < e50[t]:
            reg[t] = Regime.TREND_DOWN.value

    return pd.DataFrame({
        "regime": pd.Series(reg, index=df.index, dtype=object),
        "rh": rh_o, "rl": rl_o, "rh_touches": rht, "rl_touches": rlt,
        "atr": atr_a, "atr_ratio": ratio_a,
    }, index=df.index)[_OUT_COLUMNS]


def _reason(df: pd.DataFrame, row, params: RegimeParams) -> str:
    n = len(df)
    r = row["regime"]
    ratio = row["atr_ratio"]
    if r == Regime.VOLATILE.value:
        return f"ATR oranı {_fmt(ratio)} > {_fmt(params.vol_ratio_max)}"
    if r == Regime.RANGE.value:
        return (f"range: RH {_fmt(row['rh'])} RL {_fmt(row['rl'])}, "
                f"dokunuş {int(row['rh_touches'])}/{int(row['rl_touches'])}")
    if r == Regime.TREND_UP.value:
        return "close > EMA100 ve EMA20 > EMA50"
    if r == Regime.TREND_DOWN.value:
        return "close < EMA100 ve EMA20 < EMA50"
    if n < MIN_BARS:
        return f"yetersiz geçmiş ({n} < {MIN_BARS} mum)"
    return "belirsiz: veri geçersiz/yetersiz veya trend/range koşulu yok"


def classify_last(df: pd.DataFrame, params: RegimeParams = DEFAULT_PARAMS) -> RegimeResult:
    try:
        if isinstance(df, pd.DataFrame) and len(df) == 0:
            return RegimeResult(Regime.UNCLEAR, None, None, 0, 0, None, None, "boş veri")
        res = classify_series(df, params)
        row = res.iloc[-1]
        regime = Regime(row["regime"])
        is_range = regime == Regime.RANGE
        a = row["atr"]
        ratio = row["atr_ratio"]
        reason = _reason(df, row, params)
        if regime == Regime.UNCLEAR and len(df) >= MIN_BARS:
            reason = _unclear_reason(df, row)
        return RegimeResult(
            regime,
            float(row["rh"]) if is_range else None,
            float(row["rl"]) if is_range else None,
            int(row["rh_touches"]) if is_range else 0,
            int(row["rl_touches"]) if is_range else 0,
            float(a) if np.isfinite(a) else None,
            float(ratio) if np.isfinite(ratio) else None,
            reason,
        )
    except Exception as e:
        return RegimeResult(Regime.UNCLEAR, None, None, 0, 0, None, None, f"iç hata: {e}")


def _unclear_reason(df: pd.DataFrame, row) -> str:
    if not np.isfinite(row["atr"]) or not np.isfinite(row["atr_ratio"]):
        return "belirsiz: ATR/ATR ortalaması hesaplanamadı veya sıfır, ya da geçersiz mum"
    return "belirsiz: ne range ne trend koşulu sağlandı"


def align_to_base(regime_df: pd.DataFrame, base_index, informative_hours=4) -> pd.DataFrame:
    if not isinstance(regime_df, pd.DataFrame):
        raise ValueError("regime_df DataFrame olmali")
    if not isinstance(regime_df.index, pd.DatetimeIndex):
        raise ValueError("regime_df indeksi DatetimeIndex olmali")
    if not isinstance(base_index, pd.DatetimeIndex):
        raise ValueError("base_index DatetimeIndex olmali")
    missing = [c for c in _OUT_COLUMNS if c not in regime_df.columns]
    if missing:
        raise ValueError(f"regime_df sutunlari eksik: {missing}")
    hrs = _as_float("informative_hours", informative_hours)
    if hrs <= 0:
        raise ValueError("informative_hours > 0 olmali")
    if (regime_df.index.tz is None) != (base_index.tz is None) or \
            (regime_df.index.tz is not None and str(regime_df.index.tz) != str(base_index.tz)):
        raise ValueError("saat dilimi/naiflik uyuşmuyor")
    if not (base_index.is_monotonic_increasing and base_index.is_unique):
        raise ValueError("base_index kesin artan olmali")
    if not (regime_df.index.is_monotonic_increasing and regime_df.index.is_unique):
        raise ValueError("regime_df indeksi kesin artan olmali")

    m = len(base_index)
    delta = pd.Timedelta(hours=hrs)
    out_reg = np.full(m, Regime.UNCLEAR.value, dtype=object)
    out_f = {k: np.full(m, np.nan) for k in ("rh", "rl", "atr", "atr_ratio")}
    out_i = {k: np.zeros(m, dtype="int64") for k in ("rh_touches", "rl_touches")}

    if m and len(regime_df):
        close_t = regime_df.index + delta
        pos = close_t.searchsorted(base_index, side="right") - 1
        ok = pos >= 0
        posc = np.where(ok, pos, 0)
        age = base_index.to_numpy() - close_t.to_numpy()[posc]
        ok &= age < delta.to_timedelta64()
        idx = np.nonzero(ok)[0]
        src = posc[idx]
        out_reg[idx] = regime_df["regime"].to_numpy(dtype=object)[src]
        for k in out_f:
            out_f[k][idx] = regime_df[k].to_numpy(dtype=float)[src]
        for k in out_i:
            out_i[k][idx] = regime_df[k].to_numpy(dtype="int64")[src]

    res = pd.DataFrame({
        "regime": pd.Series(out_reg, index=base_index, dtype=object),
        "rh": out_f["rh"], "rl": out_f["rl"],
        "rh_touches": out_i["rh_touches"], "rl_touches": out_i["rl_touches"],
        "atr": out_f["atr"], "atr_ratio": out_f["atr_ratio"],
    }, index=base_index)
    return res[_OUT_COLUMNS]
