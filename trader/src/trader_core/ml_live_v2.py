"""ML-G5: r02/r03 v2 ozelliklerinin MOTOR (canli/paper) tarafi -- egitimle AYNI kod (`ml_features_v2.feature_frame_v2`).

Saf: dosya/ag/saat yok. Motor `bars_fn` / `funding_fn` verir; bu sinif yalniz motorun ELINDE tuttugu mumlari (cift basina
son WINDOW_1H_V2 kapanmis 1s mum) `feature_frame_v2`ye verir. Egitim yolu tum gecmisi verir; esitlik (1e-9) testle sabitlenir
(`tests/ml/test_g5_parity.py`). Bayrak: motor yapilandirmasi `ml_features` (varsayilan "v1" = hicbir sey degismez).

Bellek maliyeti (belgeli): 10 cift x 5000 mum x 5 sutun x 8 bayt ~ 2 MB (+ ayni boyutta gecici kopyalar; her aday mumunda
`feature_frame_v2` pencere uzerinde ~birkac yuz ms). 200 gunluk 1g baglam icin 4800 1s mum gerekir (24 x 200); 5000 = pay.

Iki gecisli ayni-mum sayimi: `features_for_bar` TUM yerel adaylari (10 cift, iki yon, alinmis/alinmamis) bir kerede alir;
`f_same_bar_signals` bu listedeki ayni-ts aday sayisidir (feature_frame_v2 icinde cands.groupby(ts)).

Kapsam disi (mentor 3.2.1-1: r02 tam olarak R02_FEATURE_NAMES): acik aday sayisi, son cikistan bu yana mum sayisi, f_eth_vol_1d
ozellik listesine EKLENMEZ."""
from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone

import numpy as np
import pandas as pd

from .ml_features import BAR, BTC, ETH
from .ml_features_v2 import LOOKBACK_1D_DAYS, R02_FEATURE_NAMES, R03_FEATURE_NAMES, RECIPES, feature_frame_v2

__all__ = ["WINDOW_1H_V2", "MIN_1H_BARS", "RECIPE_NAMES", "LiveContextV2", "BarFeatures", "HistoryShort", "internal_key"]

MIN_1H_BARS = 24 * LOOKBACK_1D_DAYS      # 4800: 200 gunluk 1g baglam
WINDOW_1H_V2 = 5000                      # motorun cift basina tuttugu 1s mum (4800 + ~8 gun pay)
FUNDING_LOOKBACK = timedelta(days=10)    # son fonlama olayi icin geri bakis (8s aralik; bosluklara dayanikli)
RECIPE_NAMES = {"r02": tuple(R02_FEATURE_NAMES), "r03": tuple(R03_FEATURE_NAMES)}


class HistoryShort(RuntimeError):
    """Motorun elindeki 1s gecmis 200 gunluk baglam icin yetmiyor (canli ozellikler egitimdekilerle ayni olmazdi)."""


def internal_key(pair: str) -> str:
    """Motor 'SOL/USDT' -> egitim 'SOL/USDT:USDT'."""
    s = pair.strip().upper()
    return s if ":" in s else s + ":USDT"


@dataclass(frozen=True)
class BarFeatures:
    """Bir karar mumu icin hesaplanmis ozellikler: rows[motor_cifti] = {ozellik: deger}; hata varsa error dolu."""
    D: datetime
    recipe: str
    rows: Mapping[str, Mapping[str, float]] = field(default_factory=dict)
    error: str | None = None


BarsFn = Callable[[str, datetime, int], pd.DataFrame]          # (motor cifti, D, n) -> 1s OHLCV (indeks = acilis, UTC)
FundingFn = Callable[[str, datetime, datetime], "pd.DataFrame | None"]   # (cift, bas, bit) -> indeks=olay zamani, 'funding_rate'


class LiveContextV2:
    def __init__(self, recipe: str, pairs: Sequence[str], bars_fn: BarsFn, funding_fn: FundingFn | None = None,
                 *, window: int = WINDOW_1H_V2) -> None:
        if recipe not in RECIPES:
            raise ValueError(f"recipe {RECIPES} icinde olmali: {recipe!r}")
        if window < MIN_1H_BARS:
            raise ValueError(f"window >= {MIN_1H_BARS} olmali")
        self.recipe = recipe
        self.names = RECIPE_NAMES[recipe]
        self.pairs = list(pairs)
        self._key = {p: internal_key(p) for p in self.pairs}
        if BTC not in self._key.values() or ETH not in self._key.values():
            raise ValueError("pairs BTC ve ETH icermeli")
        self.bars_fn, self.funding_fn, self.window = bars_fn, funding_fn, int(window)
        self._held: dict[str, pd.DataFrame] = {}

    # ------------------------------------------------------------------ bellek
    def held_rows(self) -> int:
        return sum(len(d) for d in self._held.values())

    def memory_bytes(self) -> int:
        return int(sum(d.memory_usage(deep=False).sum() for d in self._held.values()))

    # ------------------------------------------------------------------ mum penceresi (artimli)
    def _norm(self, df: pd.DataFrame) -> pd.DataFrame:
        df = df[["open", "high", "low", "close", "volume"]].astype(float)
        if df.index.tz is None:
            df = df.tz_localize("UTC")
        return df.sort_index()

    def refresh(self, D: datetime) -> None:
        """Her cift icin D'ye kadar KAPANMIS son `window` 1s mum. Ilk cagri tam yukler (baslangic yuklemesi);
        sonrakiler yalniz yeni mumlari (+24 mum ust uste binme: dolan/duzelen mumlar) ceker."""
        D = pd.Timestamp(D).tz_convert("UTC") if pd.Timestamp(D).tzinfo else pd.Timestamp(D, tz="UTC")
        for p in self.pairs:
            held = self._held.get(p)
            full = held is None or len(held) == 0
            if not full:
                last_close = held.index[-1] + BAR
                k = int((D - last_close) / BAR)
                if D < last_close or k >= self.window // 2:
                    full = True
                    held = None
            if full:
                new = self._norm(self.bars_fn(p, D.to_pydatetime(), self.window))
                self._held[p] = new.iloc[-self.window:]
            else:
                tail = self._norm(self.bars_fn(p, D.to_pydatetime(), k + 24))
                m = pd.concat([held[~held.index.isin(tail.index)], tail]).sort_index()
                self._held[p] = m.iloc[-self.window:]

    def check_history(self, D: datetime, pairs: Sequence[str]) -> None:
        """BTC/ETH ve verilen ciftler icin [floor(D,1g)-199g, D) mumlarinin elde oldugunu dogrular (aksi HistoryShort)."""
        Dt = pd.Timestamp(D).tz_convert("UTC") if pd.Timestamp(D).tzinfo else pd.Timestamp(D, tz="UTC")
        need_from = Dt.floor("1D") - pd.Timedelta(days=LOOKBACK_1D_DAYS - 1)
        for p in sorted({BTC, ETH, *(self._key[x] for x in pairs)}):
            raw = next(k for k, v in self._key.items() if v == p)
            h = self._held.get(raw)
            if h is None or len(h) == 0 or h.index[0] > need_from:
                have = "yok" if h is None or len(h) == 0 else str(h.index[0])
                raise HistoryShort(f"{raw}: 1s gecmis {need_from} oncesine uzanmiyor (ilk mum: {have}); >= {MIN_1H_BARS} mum gerekli")

    # ------------------------------------------------------------------ fonlama
    def _funding(self, D: datetime) -> dict[str, pd.DataFrame] | None:
        if self.funding_fn is None:
            return None
        out = {}
        for p in self.pairs:
            f = self.funding_fn(p, D - FUNDING_LOOKBACK, D)
            if f is not None and len(f):
                out[self._key[p]] = f
        return out

    # ------------------------------------------------------------------ ozellikler
    def features_for_bar(self, D: datetime, cands: pd.DataFrame) -> BarFeatures:
        """cands: motor cifti `pair`, `side`, `planned_entry`, `planned_stop` (HEPSI yerel adaylar; ikinci gecis).
        Bos cands -> bos rows (hesap yok)."""
        D = pd.Timestamp(D).tz_convert("UTC") if pd.Timestamp(D).tzinfo else pd.Timestamp(D, tz="UTC")
        if len(cands) == 0:
            return BarFeatures(D=D.to_pydatetime(), recipe=self.recipe)
        self.refresh(D.to_pydatetime())
        self.check_history(D.to_pydatetime(), list(cands["pair"]))
        frames = {self._key[p]: d for p, d in self._held.items() if len(d)}
        c = pd.DataFrame({
            "ts": [D] * len(cands), "pair": [self._key[p] for p in cands["pair"]], "side": cands["side"].to_numpy(),
            "planned_entry": cands["planned_entry"].to_numpy(float), "planned_stop": cands["planned_stop"].to_numpy(float)})
        ff = feature_frame_v2(frames, c, funding=self._funding(D.to_pydatetime()), recipe=self.recipe)
        rows = {}
        for i, p in enumerate(cands["pair"]):
            rows[p] = {n: float(ff[n].iloc[i]) for n in self.names}
        return BarFeatures(D=D.to_pydatetime(), recipe=self.recipe, rows=rows)


def funding_frame_from_points(points) -> pd.DataFrame | None:
    """Motor FundingPoint listesi -> feature_frame_v2 girdisi (olay zamani en yakin saate yuvarlanir; G3 ile ayni)."""
    if not points:
        return None
    idx = pd.DatetimeIndex([pd.Timestamp(p.ts).tz_convert("UTC") if pd.Timestamp(p.ts).tzinfo else pd.Timestamp(p.ts, tz="UTC")
                            for p in points]).round("1h")
    return pd.DataFrame({"funding_rate": np.array([float(p.rate) for p in points])}, index=idx)
