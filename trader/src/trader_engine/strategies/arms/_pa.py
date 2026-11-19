"""DD-12 WP-12a: TF1 ve B1 ortak yardimcilari (kurulum dosyasi DEGIL; `_` onekli, `discover` yok sayar).

Saf hesap: girdi yalniz `ArmInput` (trig, core(), params, tf). Iki yon tek kodla yazilir: short, long'un fiyat aynasidir
(o,h,l,c) -> (-o,-l,-h,-c). Aynadaki long mantigi gercek short adayini verir; fiyatlar isaretle geri cevrilir (SIGN).
Bitisik bar penceresi yalniz `t`'ye kadar bakar (D-T17); pencereler `shift(1)` ile `t`'yi icermez (HC, RH, A, kutu)."""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

from trader_core import indicators as I
from trader_core.signals import SIGNAL_COLUMNS

from . import ArmInput

ATR_LEN = 14
SIDES = ("long", "short")
SIGN = {"long": 1.0, "short": -1.0}
CAND_FLOATS = ("planned_entry", "planned_stop", "planned_target", "rr", "stop_dist_atr", "ema_value", "body_ratio",
               "wick_ratio", "edge_dist_atr")


@dataclass(frozen=True)
class Prep:
    core: pd.DataFrame        # ortak tablo (yalniz bağlam sütunları kopyalanır; adaylar bu kurulumda yeniden yazılır)
    o: np.ndarray
    h: np.ndarray
    l: np.ndarray
    c: np.ndarray
    atr: np.ndarray           # indicators.atr(trig, 14): yalniz kapanmis barlardan (Wilder, nedensel)
    ok: np.ndarray            # bar gecerli: sonlu OHLC+ATR, h-l > 0, ATR > 0
    regime: np.ndarray        # 4s rejimi (ortak tablodan, tetik barina hizali)


def prepare(inp: ArmInput) -> Prep:
    trig = inp.trig
    core = inp.core()
    o = trig["open"].to_numpy(dtype=float)
    h = trig["high"].to_numpy(dtype=float)
    lo = trig["low"].to_numpy(dtype=float)
    c = trig["close"].to_numpy(dtype=float)
    atr = I.atr(trig[["high", "low", "close"]], ATR_LEN).to_numpy(dtype=float)
    with np.errstate(invalid="ignore"):
        ok = (np.isfinite(o) & np.isfinite(h) & np.isfinite(lo) & np.isfinite(c) & np.isfinite(atr)
              & (h - lo > 0) & (atr > 0))
    regime = core["regime"].to_numpy(dtype=object)
    return Prep(core=core, o=o, h=h, l=lo, c=c, atr=atr, ok=ok, regime=regime)


def mirror(p: Prep, side: str):
    """(o, h, l, c) yonlu koordinatta: long = gercek, short = fiyat aynasi."""
    if side == "long":
        return p.o, p.h, p.l, p.c
    return -p.o, -p.l, -p.h, -p.c


class Table:
    """Aday tablosu: bağlam sütunları ortak tablodan (core kopyasi), aday sütunlari bu kurulumda yazilir."""

    def __init__(self, core: pd.DataFrame) -> None:
        self.core = core
        n = len(core)
        self.setup = np.full(n, None, dtype=object)
        self.side = np.full(n, None, dtype=object)
        self.signal = np.zeros(n, dtype=bool)
        self.skip = np.full(n, None, dtype=object)
        self.reasons = np.full(n, "", dtype=object)
        self.f = {k: np.full(n, np.nan) for k in CAND_FLOATS}
        self.pb = core["pullback_ema"].to_numpy(dtype="int64").copy()

    def put(self, t: int, *, setup: str, side: str, skip: str | None, labels: list[str], entry: float, stop: float,
            target: float | None, rr: float, sda: float, ema: float, body: float, wick: float, edge: float,
            pb: int) -> None:
        """Gerçek fiyatlarla (entry/stop/target) bir aday satiri. skip=None -> signal=True."""
        self.setup[t] = setup
        self.side[t] = side
        self.signal[t] = skip is None
        self.skip[t] = skip
        self.reasons[t] = f"{setup}_{side}:" + ",".join(labels + ([skip] if skip else []))
        f = self.f
        f["planned_entry"][t] = entry
        f["planned_stop"][t] = stop
        f["planned_target"][t] = np.nan if target is None else target
        f["rr"][t] = rr
        f["stop_dist_atr"][t] = sda
        f["ema_value"][t] = ema
        f["body_ratio"][t] = body
        f["wick_ratio"][t] = wick
        f["edge_dist_atr"][t] = edge
        self.pb[t] = pb

    def both(self, t: int, setup: str) -> None:
        """Ayni barda iki yon: aday yok (PA-K0 'both_sides')."""
        self.reasons[t] = f"{setup}:both_sides"

    def frame(self) -> pd.DataFrame:
        out = self.core.copy()
        ix = out.index
        out["setup"] = pd.Series(self.setup, index=ix, dtype=object)           # None korunur (NaN'a donmez)
        out["side"] = pd.Series(self.side, index=ix, dtype=object)
        out["signal"] = self.signal
        out["skip_reason"] = pd.Series(self.skip, index=ix, dtype=object)
        for k in CAND_FLOATS:
            out[k] = self.f[k]
        out["pullback_ema"] = self.pb
        out["reasons"] = pd.Series(self.reasons, index=ix, dtype=object)
        return out[SIGNAL_COLUMNS]
