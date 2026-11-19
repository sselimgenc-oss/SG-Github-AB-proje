"""M1 ozellikleri: son 64 KAPANMIS bar, ATR'ye olceklenmis. Her indeks yalniz `[i-63 .. i]` penceresini okur (nedensel).

ATR burada pencere-ici 14 bar ortalama gercek aralik (SMA): egitim ve canli ayni dilim uzunlugunda ayni sayilari verir
(Wilder ATR'nin baslangica bagimliligi yok). Yon (`side`): fiyat tabanli ozellikler yonle isaretlenir (short = ayna)."""
from __future__ import annotations

import numpy as np

WINDOW = 64
ATR_LEN = 14
LAGS = (1, 2, 3, 4, 6, 8, 12, 16, 24, 32, 48, 63)
STOP_ATR = 1.5           # etiket ve aday stop mesafesi (spec 5.3)
TARGET_ATR = 3.0         # hedef mesafesi
HORIZON = 48             # zaman durdurma (bar)
FEATURE_NAMES = tuple([f"ret_{k}" for k in LAGS] + ["body", "wick_up", "wick_dn", "range_pos", "dist_hi50", "dist_lo50",
                                                    "slope_20_50", "squeeze", "dir"])
SIDE_SIGN = {"long": 1.0, "short": -1.0}


def atr_at(h, l, c, i: int) -> float:
    """Pencere-ici ATR (14 bar ortalama TR); i indeksi kapanmis son bar. Gecersizse NaN."""
    if i < WINDOW - 1:
        return float("nan")
    hw, lw, cw = h[i - WINDOW + 1:i + 1], l[i - WINDOW + 1:i + 1], c[i - WINDOW + 1:i + 1]
    tr = np.maximum(hw[1:] - lw[1:], np.maximum(np.abs(hw[1:] - cw[:-1]), np.abs(lw[1:] - cw[:-1])))
    return float(tr[-ATR_LEN:].mean())


def feature_vector(o, h, l, c, i: int, side: str):
    """Ozellik vektoru (FEATURE_NAMES sirasi) ya da None (pencere yetersiz / sonlu degil / ATR<=0)."""
    if i < WINDOW - 1 or side not in SIDE_SIGN:
        return None
    s = SIDE_SIGN[side]
    lo = i - WINDOW + 1
    ow, hw, lw, cw = o[lo:i + 1], h[lo:i + 1], l[lo:i + 1], c[lo:i + 1]
    atr = atr_at(h, l, c, i)
    rng = float(hw[-1] - lw[-1])
    if not (np.isfinite(atr) and atr > 0 and rng > 0):
        return None
    tr_mean = float(np.maximum(hw[1:] - lw[1:], np.maximum(np.abs(hw[1:] - cw[:-1]), np.abs(lw[1:] - cw[:-1]))).mean())
    last = float(cw[-1])
    rets = [s * (last - float(cw[-1 - k])) / atr for k in LAGS]
    body = s * (last - float(ow[-1])) / rng
    top, bot = max(float(ow[-1]), last), min(float(ow[-1]), last)
    wick_up = (float(hw[-1]) - top) / rng
    wick_dn = (bot - float(lw[-1])) / rng
    hi20, lo20 = float(hw[-20:].max()), float(lw[-20:].min())
    span = hi20 - lo20
    pos = (last - lo20) / span if span > 0 else 0.5
    pos = pos if s > 0 else 1.0 - pos
    dist_hi = s * (last - float(hw[-51:-1].max())) / atr
    dist_lo = s * (last - float(lw[-51:-1].min())) / atr
    slope = s * (float(cw[-20:].mean()) - float(cw[-50:].mean())) / atr
    squeeze = atr / tr_mean if tr_mean > 0 else float("nan")
    vec = np.array(rets + [body, wick_up, wick_dn, pos, dist_hi, dist_lo, slope, squeeze, s], dtype=np.float64)
    return vec if np.isfinite(vec).all() else None


def feature_matrix(o, h, l, c, idx, side: str) -> tuple[np.ndarray, np.ndarray]:
    """(X, mask): idx icin ozellik satirlari; mask False = o indeks gecersiz (X satiri yok)."""
    rows, ok = [], []
    for i in idx:
        v = feature_vector(o, h, l, c, int(i), side)
        ok.append(v is not None)
        if v is not None:
            rows.append(v)
    mask = np.array(ok, dtype=bool)
    X = np.vstack(rows) if rows else np.empty((0, len(FEATURE_NAMES)))
    return X, mask
