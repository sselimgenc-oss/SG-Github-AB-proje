"""Ucluk bariyer etiketi (spec 5.3): giris = sinyal barinin kapanisi; stop 1,5 ATR ters; hedef 3 ATR lehte; 48 bar zaman durdurma.
Etiket 1 = hedef once; 0 = stop once, ayni barda iki bariyer de vurulursa stop (muhafazakar), ya da zaman durdurma.
Etiket yalniz GELECEK barlara bakar; ozellik degildir. Yeterli gelecek bar yoksa None (satir egitime girmez)."""
from __future__ import annotations

from datetime import datetime

import numpy as np

from . import features as F


def triple_barrier(h, l, c, i: int, side: str, atr: float):
    """-> (y, j) ya da None. j: bariyerin vuruldugu (ya da zaman durdurmanin) bar indeksi."""
    n = len(c)
    if not (np.isfinite(atr) and atr > 0) or i + F.HORIZON > n - 1:
        return None
    s = F.SIDE_SIGN[side]
    entry = float(c[i])
    stop = entry - s * F.STOP_ATR * atr
    tgt = entry + s * F.TARGET_ATR * atr
    for j in range(i + 1, i + F.HORIZON + 1):
        if s > 0:
            hit_stop, hit_tgt = l[j] <= stop, h[j] >= tgt
        else:
            hit_stop, hit_tgt = h[j] >= stop, l[j] <= tgt
        if hit_stop:
            return 0, j
        if hit_tgt:
            return 1, j
    return 0, i + F.HORIZON


def label_rows(o, h, l, c, ts, *, sides=("long", "short")) -> list[dict]:
    """Tek bir cift/zaman dilimi icin egitim satirlari: {ts, ts_end, side, x (ndarray), y}. ts: kapanmis bar zamanlari (tz-li)."""
    rows = []
    n = len(c)
    for i in range(F.WINDOW - 1, n):
        for side in sides:
            x = F.feature_vector(o, h, l, c, i, side)
            if x is None:
                continue
            lab = triple_barrier(h, l, c, i, side, F.atr_at(h, l, c, i))
            if lab is None:
                continue
            y, j = lab
            rows.append({"ts": ts[i], "ts_end": ts[j], "side": side, "x": x, "y": y})
    return rows


def paper_row(x: np.ndarray, side: str, ts: datetime, ts_end: datetime | None, r: float) -> dict | None:
    """Kagit kaydi (alinan/alinmayan aday sonucu): etiket = R > 0 (spec 5.3: kâgıt kayitlari ayni hedefi tasir)."""
    if x is None or not np.isfinite(r):
        return None
    return {"ts": ts, "ts_end": ts_end or ts, "side": side, "x": np.asarray(x, dtype=np.float64), "y": 1 if r > 0 else 0}
