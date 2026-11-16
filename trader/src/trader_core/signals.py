"""Strateji v1 sinyal cekirdegi (T1 trend geri cekilmesi, R1 range donusu).

Saf pandas/numpy; freqtrade, risk.py ve ledger.py import edilmez. Kurallar
docs/strateji-spec.md ile birebir aynidir. Ileriye bakmaz: satir t yalnizca 0..t
satirlarina baglidir.
"""
from __future__ import annotations

import math
import numbers
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field

import numpy as np
import pandas as pd

from .indicators import atr, ema
from .regime import RegimeParams

# ---------------------------------------------------------------------------
# Sabitler (taranmaz)
# ---------------------------------------------------------------------------

ATR_LEN = 14
STOP_LOOKBACK = 5
BODY_RATIO_MIN = 0.5
WICK_RATIO_MIN = 0.5
STOP_DIST_MIN_ATR = 0.5
STOP_DIST_MAX_ATR = 2.0
TRAIL_START_R = 1.0
TIME_STOP_BARS = 48
EPS = 1e-9

SETUPS = ("T1", "R1")
SIDES = ("long", "short")
_TRADEABLE = ("trend_up", "trend_down", "range")

SIGNAL_COLUMNS = [
    "setup", "side", "signal", "skip_reason",
    "planned_entry", "planned_stop", "planned_target", "rr", "stop_dist_atr",
    "atr_tf", "atr_4h", "atr_ratio",
    "regime", "rh", "rl", "rh_touches", "rl_touches",
    "ema_value", "body_ratio", "wick_ratio", "edge_dist_atr", "pullback_ema",
    "reasons",
]

_REGIME_COLUMNS = ["regime", "rh", "rl", "rh_touches", "rl_touches", "atr", "atr_ratio"]


# ---------------------------------------------------------------------------
# Yardimcilar
# ---------------------------------------------------------------------------

def _num(x, name: str = "deger") -> float:
    """int/float/numbers.Real -> float; bool, None, metin, NaN, inf gecersiz."""
    if isinstance(x, bool) or not isinstance(x, numbers.Real):
        raise ValueError(f"{name} sayi olmali: {x!r}")
    v = float(x)
    if not math.isfinite(v):
        raise ValueError(f"{name} sonlu olmali: {x!r}")
    return v


def _side(side) -> str:
    if not isinstance(side, str) or side not in SIDES:
        raise ValueError(f"yon 'long' veya 'short' olmali: {side!r}")
    return side


# ---------------------------------------------------------------------------
# Parametreler
# ---------------------------------------------------------------------------

_FLOAT_SPECS = {
    "range_width_atr": (3.0, 6.0),
    "vol_ratio_max": (1.25, 2.0),
    "edge_zone_atr": (0.15, 0.50),
    "stop_buffer_atr": (0.1, 1.0),
    "trail_atr": (2.0, 4.0),
    "range_target_frac": (0.5, 1.0),
    "rr_min": (1.0, 2.0),
}
_PARAM_KEYS = ("range_width_atr", "vol_ratio_max", "edge_zone_atr", "pullback_ema", "stop_buffer_atr",
               "trail_atr", "range_target_frac", "rr_min", "trigger_tf")
_TRIGGER_TFS = ("1h", "15m")


@dataclass(frozen=True)
class SignalParams:
    range_width_atr: float = 4.0
    vol_ratio_max: float = 1.5
    edge_zone_atr: float = 0.25
    pullback_ema: int = 50
    stop_buffer_atr: float = 0.3
    trail_atr: float = 3.0
    range_target_frac: float = 0.75
    rr_min: float = 1.5
    trigger_tf: str = "1h"

    def __post_init__(self):
        for name, (lo, hi) in _FLOAT_SPECS.items():
            f = _num(getattr(self, name), name)
            if not (lo <= f <= hi):
                raise ValueError(f"{name} {lo}-{hi} disinda: {f}")
            object.__setattr__(self, name, f)
        pe = _num(self.pullback_ema, "pullback_ema")
        if pe not in (20.0, 50.0):
            raise ValueError(f"pullback_ema 20 veya 50 olmali: {self.pullback_ema!r}")
        object.__setattr__(self, "pullback_ema", int(pe))
        if not isinstance(self.trigger_tf, str) or self.trigger_tf not in _TRIGGER_TFS:
            raise ValueError(f"trigger_tf '1h' veya '15m' olmali: {self.trigger_tf!r}")

    @classmethod
    def from_mapping(cls, m) -> "SignalParams":
        if not isinstance(m, Mapping):
            raise ValueError("params Mapping olmali")
        keys = set(m)
        if keys != set(_PARAM_KEYS):
            missing = sorted(set(_PARAM_KEYS) - keys, key=str)
            extra = sorted((k for k in keys if k not in _PARAM_KEYS), key=str)
            raise ValueError(f"params 9 anahtar olmali; eksik={missing} fazla={extra}")
        vals = {}
        for k in _PARAM_KEYS:
            v = m[k]
            if k == "trigger_tf":
                vals[k] = v
            elif k == "pullback_ema":
                vals[k] = round(_num(v, k), 6)
            else:
                vals[k] = round(_num(v, k), 6)
        return cls(**vals)

    def regime_params(self) -> RegimeParams:
        return RegimeParams(range_width_atr=self.range_width_atr, vol_ratio_max=self.vol_ratio_max,
                            edge_zone_atr=self.edge_zone_atr)


DEFAULT_SIGNAL_PARAMS = SignalParams()


# ---------------------------------------------------------------------------
# Aday
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class SetupCandidate:
    setup: str
    side: str | None
    entry: float
    stop: float
    target: float | None
    rr: float | None
    stop_dist_atr: float
    skip_reason: str | None
    reasons: str
    features: Mapping = field(default_factory=dict)

    @property
    def signal(self) -> bool:
        return self.side is not None and self.skip_reason is None


def _finite(*xs) -> bool:
    return all(isinstance(x, (int, float, np.floating, np.integer)) and math.isfinite(float(x)) for x in xs)


def _check_params(params) -> None:
    if not isinstance(params, SignalParams):
        raise ValueError("params SignalParams olmali")


def _stop_width_bad(dist: float, atr_tf: float) -> bool:
    return dist < STOP_DIST_MIN_ATR * atr_tf - EPS or dist > STOP_DIST_MAX_ATR * atr_tf + EPS


def evaluate_t1(side, o, h, l, c, ema_value, recent_lows_or_highs, atr_tf, params) -> SetupCandidate | None:
    """T1 tetik mumu degerlendirmesi. Tetik yoksa (veya girdi gecersizse) None."""
    side = _side(side)
    _check_params(params)
    try:
        recent = [float(x) for x in recent_lows_or_highs]
    except (TypeError, ValueError):
        return None
    recent = recent[-STOP_LOOKBACK:]
    if len(recent) < STOP_LOOKBACK:
        return None
    try:
        vals = (float(o), float(h), float(l), float(c), float(ema_value), float(atr_tf))
    except (TypeError, ValueError):
        return None
    if not _finite(*vals, *recent):
        return None
    o, h, l, c, e, a = vals
    rng = h - l
    if not (a > 0 and rng > 0):
        return None
    body = abs(c - o) / rng
    if side == "long":
        trig = (l <= e + EPS and e <= c + EPS and c > o and body >= BODY_RATIO_MIN - EPS)
    else:
        trig = (h >= e - EPS and e >= c - EPS and c < o and body >= BODY_RATIO_MIN - EPS)
    if not trig:
        return None
    if side == "long":
        stop = min(recent) - params.stop_buffer_atr * a
        dist = c - stop
        tag = "T1_long:trend_up,ema_touch,bull_body"
    else:
        stop = max(recent) + params.stop_buffer_atr * a
        dist = stop - c
        tag = "T1_short:trend_down,ema_touch,bear_body"
    sda = dist / a
    if not _finite(stop, dist, sda):
        return None
    if _stop_width_bad(dist, a):
        skip, reasons = "stop_width", tag + ",stop_width"
    else:
        skip, reasons = None, tag + ",stop_ok"
    feats = {"atr_tf": a, "stop_dist_atr": sda, "pullback_ema": params.pullback_ema,
             "ema_value": e, "body_ratio": body}
    return SetupCandidate("T1", side, c, stop, None, None, sda, skip, reasons, feats)


def evaluate_r1(side, o, h, l, c, rh, rl, atr_tf, atr_4h, params) -> SetupCandidate | None:
    """R1 tetik mumu degerlendirmesi. Tetik yoksa (veya girdi gecersizse) None."""
    side = _side(side)
    _check_params(params)
    try:
        vals = (float(o), float(h), float(l), float(c), float(rh), float(rl), float(atr_tf), float(atr_4h))
    except (TypeError, ValueError):
        return None
    if not _finite(*vals):
        return None
    o, h, l, c, rh, rl, a, a4 = vals
    rng = h - l
    if not (a > 0 and a4 > 0 and rng > 0 and rh > rl):
        return None
    zone = params.edge_zone_atr * a4
    if side == "long":
        wick = (min(o, c) - l) / rng
        trig = (l <= rl + zone + EPS and c > rl and wick >= WICK_RATIO_MIN - EPS)
    else:
        wick = (h - max(o, c)) / rng
        trig = (h >= rh - zone - EPS and c < rh and wick >= WICK_RATIO_MIN - EPS)
    if not trig:
        return None
    if side == "long":
        stop = l - params.stop_buffer_atr * a
        target = rl + params.range_target_frac * (rh - rl)
        dist = c - stop
        rr = (target - c) / (c - stop)
        edge = (c - rl) / a4
        tag = "R1_long:range,edge_zone,reject_wick"
    else:
        stop = h + params.stop_buffer_atr * a
        target = rh - params.range_target_frac * (rh - rl)
        dist = stop - c
        rr = (c - target) / (stop - c)
        edge = (rh - c) / a4
        tag = "R1_short:range,edge_zone,reject_wick"
    sda = dist / a
    if not _finite(stop, target, dist, sda, rr, edge):
        return None
    if _stop_width_bad(dist, a):
        skip, reasons = "stop_width", tag + ",stop_width"
    elif rr <= 0 or rr < params.rr_min - EPS:
        skip, reasons = "rr_below_min", tag + ",stop_ok,rr_below_min"
    else:
        skip, reasons = None, tag + ",stop_ok,rr_ok"
    feats = {"atr_tf": a, "stop_dist_atr": sda, "atr_4h": a4, "wick_ratio": wick, "rr": rr,
             "edge_dist_atr": edge}
    return SetupCandidate("R1", side, c, stop, target, rr, sda, skip, reasons, feats)


def pick_candidate(candidates) -> SetupCandidate | None:
    """Oncelik/cakisma: T1 > R1; ayni kurulumda iki yon -> hicbiri (conflict)."""
    cands = [c for c in candidates if c is not None]
    if not cands:
        return None
    for setup in SETUPS:  # T1 onceliklidir
        group = [c for c in cands if c.setup == setup]
        if not group:
            continue
        sides = {c.side for c in group}
        if len(sides) > 1:
            return SetupCandidate(setup, None, float("nan"), float("nan"), None, None, float("nan"),
                                  "other", "conflict:long_short", {})
        return group[0]
    return cands[0]


# ---------------------------------------------------------------------------
# Cikis yardimcilari
# ---------------------------------------------------------------------------

def trail_stop_path(side, fill_price, initial_stop, highs, lows, atrs, trail_atr) -> pd.Series:
    """T1 iz suren stop yolu (Bolum 5.2). Monoton: stop asla geri cekilmez."""
    side = _side(side)
    fill = _num(fill_price, "fill_price")
    init = _num(initial_stop, "initial_stop")
    tr = _num(trail_atr, "trail_atr")
    hi = np.asarray(highs, dtype=float)
    lo = np.asarray(lows, dtype=float)
    at = np.asarray(atrs, dtype=float)
    if not (hi.shape == lo.shape == at.shape) or hi.ndim != 1:
        raise ValueError("highs, lows ve atrs ayni uzunlukta 1 boyutlu olmali")
    index = highs.index if isinstance(highs, pd.Series) else pd.RangeIndex(len(hi))
    R = abs(fill - init)
    out = np.empty(len(hi))
    cur = init
    if side == "long":
        hh = -np.inf
        for k in range(len(hi)):
            if not np.isnan(hi[k]):
                hh = max(hh, hi[k])
            if hh >= fill + TRAIL_START_R * R - EPS and not np.isnan(at[k]):
                cand = hh - tr * at[k]
                if cand > cur:
                    cur = cand
            out[k] = cur
    else:
        ll = np.inf
        for k in range(len(lo)):
            if not np.isnan(lo[k]):
                ll = min(ll, lo[k])
            if ll <= fill - TRAIL_START_R * R + EPS and not np.isnan(at[k]):
                cand = ll + tr * at[k]
                if cand < cur:
                    cur = cand
            out[k] = cur
    return pd.Series(out, index=index, dtype="float64")


def time_stop_due(bars_closed_since_entry, limit=TIME_STOP_BARS) -> bool:
    return bool(bars_closed_since_entry >= limit)


def target_reached(side, target, bar_high, bar_low) -> bool:
    side = _side(side)
    if side == "long":
        return bool(bar_high >= target - EPS)
    return bool(bar_low <= target + EPS)


def regime_flip_exit(side, aligned_regime) -> bool:
    side = _side(side)
    return (side == "long" and aligned_regime == "trend_down") or \
           (side == "short" and aligned_regime == "trend_up")


# ---------------------------------------------------------------------------
# compute_signals
# ---------------------------------------------------------------------------

def _check_inputs(df, regime_df, params) -> None:
    if not isinstance(df, pd.DataFrame):
        raise ValueError("df pandas.DataFrame olmali")
    if not isinstance(regime_df, pd.DataFrame):
        raise ValueError("regime_df pandas.DataFrame olmali")
    _check_params(params)
    miss = [c for c in ("open", "high", "low", "close") if c not in df.columns]
    if miss:
        raise ValueError(f"zorunlu sutun yok: {miss}")
    miss = [c for c in _REGIME_COLUMNS if c not in regime_df.columns]
    if miss:
        raise ValueError(f"regime_df sutunlari eksik: {miss}")
    if len(df) == 0 and len(regime_df) == 0:
        return
    if not isinstance(df.index, pd.DatetimeIndex):
        raise ValueError("df indeksi DatetimeIndex olmali")
    if not (df.index.is_monotonic_increasing and df.index.is_unique):
        raise ValueError("df indeksi kesin artan ve tekrarsiz olmali")
    if not df.index.equals(regime_df.index):
        raise ValueError("df ve regime_df indeksleri esit olmali")


def _empty_output(index) -> pd.DataFrame:
    dt = {"setup": object, "side": object, "signal": bool, "skip_reason": object, "regime": object,
          "reasons": object, "rh_touches": "int64", "rl_touches": "int64", "pullback_ema": "int64"}
    return pd.DataFrame({c: pd.Series([], index=index, dtype=dt.get(c, "float64"))
                         for c in SIGNAL_COLUMNS})[SIGNAL_COLUMNS]


def compute_signals(df, regime_df, params=DEFAULT_SIGNAL_PARAMS) -> pd.DataFrame:
    _check_inputs(df, regime_df, params)
    n = len(df)
    if n == 0:
        return _empty_output(df.index)

    o = pd.to_numeric(df["open"], errors="coerce").astype("float64").to_numpy()
    h = pd.to_numeric(df["high"], errors="coerce").astype("float64").to_numpy()
    lo = pd.to_numeric(df["low"], errors="coerce").astype("float64").to_numpy()
    c = pd.to_numeric(df["close"], errors="coerce").astype("float64").to_numpy()
    with np.errstate(invalid="ignore"):
        valid = (np.isfinite(o) & np.isfinite(h) & np.isfinite(lo) & np.isfinite(c)
                 & (o > 0) & (h > 0) & (lo > 0) & (c > 0) & (h >= lo)
                 & (c <= h) & (c >= lo) & (o <= h) & (o >= lo))
    clean = pd.DataFrame({"open": np.where(valid, o, np.nan), "high": np.where(valid, h, np.nan),
                          "low": np.where(valid, lo, np.nan), "close": np.where(valid, c, np.nan)},
                         index=df.index)
    atr_tf = atr(clean, ATR_LEN).to_numpy()
    ema_a = ema(clean["close"], params.pullback_ema).to_numpy()
    cl, ch, cw = clean["close"].to_numpy(), clean["high"].to_numpy(), clean["low"].to_numpy()
    co = clean["open"].to_numpy()

    reg = regime_df["regime"].to_numpy(dtype=object)
    rh = regime_df["rh"].to_numpy(dtype=float)
    rl = regime_df["rl"].to_numpy(dtype=float)
    rht = np.nan_to_num(regime_df["rh_touches"].to_numpy(dtype=float)).astype("int64")
    rlt = np.nan_to_num(regime_df["rl_touches"].to_numpy(dtype=float)).astype("int64")
    atr4 = regime_df["atr"].to_numpy(dtype=float)
    ratio = regime_df["atr_ratio"].to_numpy(dtype=float)

    nan = np.nan
    f = {k: np.full(n, nan) for k in ("planned_entry", "planned_stop", "planned_target", "rr",
                                        "stop_dist_atr", "ema_value", "body_ratio", "wick_ratio",
                                        "edge_dist_atr")}
    setup_o = np.full(n, None, dtype=object)
    side_o = np.full(n, None, dtype=object)
    skip_o = np.full(n, None, dtype=object)
    signal_a = np.zeros(n, dtype=bool)
    reasons_o = np.full(n, "", dtype=object)
    pb = np.zeros(n, dtype="int64")

    for t in range(n):
        if not valid[t] or not (h[t] - lo[t] > 0):
            reasons_o[t] = "bad_bar"
            continue
        label = reg[t]
        if not isinstance(label, str) or label not in _TRADEABLE:
            reasons_o[t] = "regime_blocked"
            continue
        a, a4 = atr_tf[t], atr4[t]
        t1 = label != "range"
        win_lo = t - STOP_LOOKBACK + 1
        ok = (math.isfinite(a) and math.isfinite(a4) and win_lo >= 0
              and bool(np.all(np.isfinite(cw[win_lo:t + 1]))) and bool(np.all(np.isfinite(ch[win_lo:t + 1]))))
        if t1:
            ok = ok and math.isfinite(ema_a[t])
        else:
            ok = ok and math.isfinite(rh[t]) and math.isfinite(rl[t])
        if not ok:
            reasons_o[t] = "no_history"
            continue
        if t1:
            side = "long" if label == "trend_up" else "short"
            recent = cw[win_lo:t + 1] if side == "long" else ch[win_lo:t + 1]
            cands = [evaluate_t1(side, co[t], ch[t], cw[t], cl[t], ema_a[t], recent, a, params)]
        else:
            cands = [evaluate_r1(s, co[t], ch[t], cw[t], cl[t], rh[t], rl[t], a, a4, params)
                     for s in SIDES]
        cand = pick_candidate(cands)
        if cand is None:
            continue
        setup_o[t] = cand.setup
        side_o[t] = cand.side
        skip_o[t] = cand.skip_reason
        reasons_o[t] = cand.reasons
        signal_a[t] = cand.signal
        if cand.side is None:  # cakisma: planli alan yok
            continue
        ft = cand.features
        f["planned_entry"][t] = cand.entry
        f["planned_stop"][t] = cand.stop
        f["stop_dist_atr"][t] = cand.stop_dist_atr
        if cand.target is not None:
            f["planned_target"][t] = cand.target
            f["rr"][t] = cand.rr
            f["wick_ratio"][t] = ft["wick_ratio"]
            f["edge_dist_atr"][t] = ft["edge_dist_atr"]
        else:
            f["ema_value"][t] = ft["ema_value"]
            f["body_ratio"][t] = ft["body_ratio"]
            pb[t] = params.pullback_ema

    out = pd.DataFrame({
        "setup": pd.Series(setup_o, index=df.index, dtype=object),
        "side": pd.Series(side_o, index=df.index, dtype=object),
        "signal": signal_a,
        "skip_reason": pd.Series(skip_o, index=df.index, dtype=object),
        "planned_entry": f["planned_entry"], "planned_stop": f["planned_stop"],
        "planned_target": f["planned_target"], "rr": f["rr"], "stop_dist_atr": f["stop_dist_atr"],
        "atr_tf": atr_tf, "atr_4h": atr4, "atr_ratio": ratio,
        "regime": pd.Series(reg, index=df.index, dtype=object),
        "rh": rh, "rl": rl, "rh_touches": rht, "rl_touches": rlt,
        "ema_value": f["ema_value"], "body_ratio": f["body_ratio"], "wick_ratio": f["wick_ratio"],
        "edge_dist_atr": f["edge_dist_atr"], "pullback_ema": pb,
        "reasons": pd.Series(reasons_o, index=df.index, dtype=object),
    }, index=df.index)
    return out[SIGNAL_COLUMNS]
