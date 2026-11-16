"""Uclu bariyer etiketi (§3.1) ve referans net R. Etiket uretici modelden AYRIDIR.

Aday, `ts` anindaki (aday mumun kapanisi) planlanan giris/stop/hedefle tanimlidir; bariyerler
aday mumdan SONRAKI 72 adet 1 saatlik mumda taranir. Alt bariyer = planned_stop (-1 R), ust
bariyer = +2 R, zaman bariyeri = 72 mum. Ayni mumda iki bariyer de degerse STOP once sayilir
(muhafazakar). Ufuk veri sonuna tasarsa ve bariyer degmediyse etiket NaN (cozulmemis).
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from .config import BAR, EXIT_TIME_STOP_BARS, FEE_RATE, HORIZON_BARS, SLIPPAGE_RATE, TARGET_R
from .guards import assert_pre_holdout


def cost_in_r(entry, stop, fee_rate: float = FEE_RATE, slippage_rate: float = SLIPPAGE_RATE):
    """Tur (giris+cikis) maliyetinin R cinsinden payi: 2*(fee+slip)*entry/|entry-stop|."""
    entry = np.asarray(entry, dtype=float)
    r = np.abs(entry - np.asarray(stop, dtype=float))
    return 2.0 * (fee_rate + slippage_rate) * entry / r


def label_candidates(candles: pd.DataFrame, cands: pd.DataFrame, *, horizon: int = HORIZON_BARS,
                     target_r: float = TARGET_R, fee_rate: float = FEE_RATE,
                     slippage_rate: float = SLIPPAGE_RATE) -> pd.DataFrame:
    """candles: tek cift, indeks = mum ACILIS zamani (UTC). cands: ts, side, planned_entry,
    planned_stop, planned_target. Doner: label, label_end_ts, barrier_net_r, net_r (referans cikis), exit_ts (referans cikis zamani),
    cost_r, ayni indeksle."""
    assert_pre_holdout(candles.index, "mum verisi")
    idx = candles.index
    hi, lo, cl = (candles[c].to_numpy(float) for c in ("high", "low", "close"))
    n = len(candles)
    out = {k: np.full(len(cands), np.nan) for k in ("label", "barrier_net_r", "net_r", "cost_r")}
    exit_ts = np.full(len(cands), np.datetime64("NaT", "ns"), dtype="datetime64[ns]")
    end_ts = np.full(len(cands), np.datetime64("NaT", "ns"), dtype="datetime64[ns]")
    pos_all = idx.searchsorted(pd.DatetimeIndex(cands["ts"]) - BAR)
    for k, (side, e, s, tg, p) in enumerate(zip(cands["side"], cands["planned_entry"], cands["planned_stop"],
                                                 cands["planned_target"], pos_all)):
        rr = abs(e - s)
        sgn = 1.0 if side == "long" else -1.0
        cost = 2.0 * (fee_rate + slippage_rate) * e / rr
        out["cost_r"][k] = cost
        a, b = p + 1, min(p + 1 + horizon, n)
        if a >= n:
            continue
        h, l, c = hi[a:b], lo[a:b], cl[a:b]
        stop_hit = (l <= s) if side == "long" else (h >= s)
        up = e + sgn * target_r * rr
        up_hit = (h >= up) if side == "long" else (l <= up)
        i_stop = int(np.argmax(stop_hit)) if stop_hit.any() else None
        i_up = int(np.argmax(up_hit)) if up_hit.any() else None
        full = (b - a) == horizon
        # etiket
        if i_stop is not None and (i_up is None or i_stop <= i_up):
            lab, j, g = 0.0, i_stop, -1.0
        elif i_up is not None:
            lab, j, g = 1.0, i_up, target_r
        elif full:
            lab, j, g = 0.0, horizon - 1, sgn * (c[-1] - e) / rr
        else:
            continue                                            # cozulmemis
        out["label"][k] = lab
        out["barrier_net_r"][k] = g - cost
        end_ts[k] = (idx[a + j] + BAR).to_datetime64()
        # referans cikis (sentetik net_r): stop -1R, R1 hedefi, aksi halde 48 mumda zaman cikisi
        ts_ = EXIT_TIME_STOP_BARS
        h2, l2, c2 = h[:ts_], l[:ts_], c[:ts_]
        sh = (l2 <= s) if side == "long" else (h2 >= s)
        if np.isfinite(tg):
            th = (h2 >= tg) if side == "long" else (l2 <= tg)
            tR = abs(tg - e) / rr
        else:
            th, tR = np.zeros_like(sh), 0.0
        is_, it_ = (int(np.argmax(sh)) if sh.any() else None), (int(np.argmax(th)) if th.any() else None)
        if is_ is not None and (it_ is None or is_ <= it_):
            g2, x = -1.0, is_
        elif it_ is not None:
            g2, x = tR, it_
        elif len(c2) == ts_:
            g2, x = sgn * (c2[-1] - e) / rr, ts_ - 1
        else:
            continue
        out["net_r"][k] = g2 - cost
        exit_ts[k] = (idx[a + x] + BAR).to_datetime64()
    res = pd.DataFrame(out, index=cands.index)
    res["label_end_ts"] = pd.to_datetime(end_ts, utc=True)
    res["exit_ts"] = pd.to_datetime(exit_ts, utc=True)       # referans (gercek) cikis zamani
    return res
