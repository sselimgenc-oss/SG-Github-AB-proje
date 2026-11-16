"""Sinyal kaynagi (05 §3): MarketView'dan pencere cekip stratejiyi calistirir (eski adaptorun populate_indicators
karsiligi). Hata o cifte ozgudur; giris yok, cikislar etkilenmez."""
from __future__ import annotations

import logging
import math
from collections import Counter
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import datetime
from typing import Literal, Protocol

import numpy as np
import pandas as pd

from trader_core import ledger as L
from trader_core.ml_package import MlModelView, ml_score_from_reasons
from trader_core.signals import SignalParams

from .bars import tf_delta
from .marketdata.sources import MarketView
from .position_manager import ExitContext
from .strategies.base import Strategy, StrategyContext, StrategyError, validate_row, validate_table
from .types import Position

log = logging.getLogger("engine.runner")
_OHLC = ["open", "high", "low", "close"]


@dataclass(frozen=True)
class SignalRow:
    pair: str
    bar_open_ts: datetime
    bar_close_ts: datetime
    signal: bool
    setup: str | None
    side: str | None
    skip_reason: str | None
    planned_entry: float
    planned_stop: float
    planned_target: float | None
    rr: float | None
    stop_dist_atr: float | None
    atr_tf: float | None
    atr_4h: float | None
    atr_ratio: float | None
    regime: str
    rh: float | None
    rl: float | None
    rh_touches: int
    rl_touches: int
    ema_value: float | None
    body_ratio: float | None
    wick_ratio: float | None
    edge_dist_atr: float | None
    pullback_ema: int
    reasons: str
    param_version_id: int
    ml_score: float | None = None          # ML-0a: reasons'taki `ml:p=` etiketinden; ML'siz stratejide None


@dataclass(frozen=True)
class SignalFrame:
    pair: str
    status: Literal["ok", "no_history", "data_gap", "error"]
    detail: str | None
    last: SignalRow | None
    table: pd.DataFrame | None


class SignalSource(Protocol):
    def frame(self, pair: str, D: datetime, params: SignalParams, version_id: int) -> SignalFrame: ...

    def exit_context(self, pair: str, pos: Position, D: datetime) -> ExitContext | None: ...


def _opt(x) -> float | None:
    try:
        v = float(x)
    except (TypeError, ValueError):
        return None
    return v if math.isfinite(v) else None


def _int0(x) -> int:
    v = _opt(x)
    return int(v) if v is not None else 0


def _text(x, default: str | None = None) -> str | None:
    return x if isinstance(x, str) else default


def _to_row(pair: str, open_ts: datetime, close_ts: datetime, r: pd.Series, version_id: int) -> SignalRow:
    pe, ps = _opt(r["planned_entry"]), _opt(r["planned_stop"])
    return SignalRow(
        pair=pair, bar_open_ts=open_ts, bar_close_ts=close_ts, signal=bool(r["signal"]),
        setup=_text(r["setup"]), side=_text(r["side"]), skip_reason=_text(r["skip_reason"]),
        planned_entry=pe if pe is not None else float("nan"), planned_stop=ps if ps is not None else float("nan"),
        planned_target=_opt(r["planned_target"]), rr=_opt(r["rr"]), stop_dist_atr=_opt(r["stop_dist_atr"]),
        atr_tf=_opt(r["atr_tf"]), atr_4h=_opt(r["atr_4h"]), atr_ratio=_opt(r["atr_ratio"]),
        regime=_text(r["regime"], "unclear"), rh=_opt(r["rh"]), rl=_opt(r["rl"]),
        rh_touches=_int0(r["rh_touches"]), rl_touches=_int0(r["rl_touches"]), ema_value=_opt(r["ema_value"]),
        body_ratio=_opt(r["body_ratio"]), wick_ratio=_opt(r["wick_ratio"]), edge_dist_atr=_opt(r["edge_dist_atr"]),
        pullback_ema=_int0(r["pullback_ema"]), reasons=_text(r["reasons"], "") or "", param_version_id=int(version_id),
        ml_score=ml_score_from_reasons(_text(r["reasons"], "")))


def _params_map(params) -> Mapping[str, object]:
    if isinstance(params, SignalParams):
        return {k: getattr(params, k) for k in L.PARAM_KEYS}
    return params


class WindowedSignalSource:
    """Paper/canli: her karar adiminda pencere cek, stratejiyi calistir."""

    def __init__(self, view: MarketView, strategy: Strategy, *, strict: bool = False,
                 last_exit_fn: Callable[[str, datetime], tuple[datetime, str] | None] | None = None,
                 ml_model: MlModelView | None = None, ml_error: str | None = None) -> None:
        self.view = view
        self.strategy = strategy
        self.strict = strict
        self.last_exit_fn = last_exit_fn
        self.ml_model = ml_model            # 05 §13.2: stratejiye ctx.model olarak SALT OKUNUR verilir
        self.ml_error = ml_error
        self.counters: Counter = Counter()
        self._cache: dict[tuple[str, datetime, int], SignalFrame] = {}
        self._latest: dict[tuple[str, datetime], SignalFrame] = {}
        self._cache_d: datetime | None = None

    # ------------------------------------------------------------------ frame
    def frame(self, pair: str, D: datetime, params, version_id: int) -> SignalFrame:
        if self._cache_d != D:
            self._cache.clear()
            self._latest.clear()
            self._cache_d = D
        key = (pair, D, int(version_id))
        hit = self._cache.get(key)
        if hit is not None:
            return hit
        fr = self._build(pair, D, _params_map(params), int(version_id))
        self._cache[key] = fr
        self._latest[(pair, D)] = fr
        return fr

    def _bad(self, pair: str, status: str, detail: str, *, error: bool = False) -> SignalFrame:
        self.counters["errors" if error else status] += 1
        log.log(logging.CRITICAL if error else logging.WARNING, "sinyal karesi %s: %s (%s)", pair, status, detail)
        return SignalFrame(pair=pair, status=status, detail=detail, last=None, table=None)  # type: ignore[arg-type]

    def _build(self, pair: str, D: datetime, params: Mapping[str, object], version_id: int) -> SignalFrame:
        info = self.strategy.info
        try:
            tf = str(params["trigger_tf"])
            if tf not in info.allowed_trigger_tfs:
                raise StrategyError("bad_table", f"trigger_tf izinli degil: {tf}")
            names = {("trigger" if t == "trigger" else t): (tf if t == "trigger" else t) for t in info.timeframes}
            bars: dict[str, pd.DataFrame] = {}
            for key, real in names.items():
                bars[real] = self.view.bars(pair, real, D, info.window_bars[real])
            trig = bars[tf]
            for key, real in names.items():
                if len(bars[real]) < info.warmup_bars[real]:
                    return self._bad(pair, "no_history", f"{real}:{len(bars[real])}<{info.warmup_bars[real]}")
            if len(trig) == 0 or trig.index[-1].to_pydatetime() != D - tf_delta(tf):
                return self._bad(pair, "data_gap", "trigger_bar_missing")
            for key, real in names.items():
                need = info.min_contiguous.get(key)
                if need is not None and self.view.contiguous_tail(pair, real, D) < need:
                    return self._bad(pair, "data_gap", "hole")
            ctx = StrategyContext(pair=pair, D=D, tf=tf, params=params, bars=bars, last_exit=None, model=self.ml_model)
            sig = self.strategy.compute(ctx)
            validate_table(sig, info, trig.index)
            last_exit = self.last_exit_fn(pair, D) if self.last_exit_fn is not None else None
            fctx = StrategyContext(pair=pair, D=D, tf=tf, params=params, bars=bars, last_exit=last_exit,
                                   model=self.ml_model)
            last_row = self.strategy.post_filter(sig.iloc[-1], fctx)
            validate_row(last_row, info)
            if bool(last_row["signal"]) and not bool(sig.iloc[-1]["signal"]):
                raise StrategyError("bad_table", "post_filter aday ekleyemez")
            if bool(last_row["signal"]):
                for k in ("planned_entry", "planned_stop", "planned_target", "setup", "side"):
                    a, b = last_row[k], sig.iloc[-1][k]
                    same = (a == b) or (isinstance(a, float) and isinstance(b, float) and math.isnan(a) and math.isnan(b))
                    if not same:
                        raise StrategyError("bad_table", f"post_filter {k} degistiremez")
            table = sig.join(trig[_OHLC])
            for c in ("signal", "skip_reason", "reasons"):
                table.iloc[-1, table.columns.get_loc(c)] = last_row[c]
            open_ts = trig.index[-1].to_pydatetime()
            row = _to_row(pair, open_ts, D, table.iloc[-1], version_id)
            return SignalFrame(pair=pair, status="ok", detail=None, last=row, table=table)
        except Exception as e:  # noqa: BLE001
            if self.strict:
                raise
            self.counters["callback_errors"] += 1
            return self._bad(pair, "error", f"{type(e).__name__}: {e}", error=True)

    # ------------------------------------------------------------------ ml durumu (status.json / kapi gorunurlugu)
    def ml_status(self, now: datetime) -> dict | None:
        """ML'siz strateji -> None. state: off | ok | no_model | expired (active iken no_model/expired => giris yok)."""
        mode = getattr(self.strategy, "ml_mode", None)
        if mode is None:
            return None
        m = self.ml_model
        if mode == "off":
            state = "off"
        elif m is None:
            state = "no_model"
        elif m.expired(now):
            state = "expired"
        else:
            state = "ok"
        return {"mode": mode, "state": state, "model_id": None if m is None else m.model_id,
                "threshold": None if m is None else m.threshold,
                "expires_at": None if m is None else m.expires_at.isoformat(), "error": self.ml_error,
                "entries_blocked": mode == "active" and state in ("no_model", "expired")}

    # ------------------------------------------------------------------ exit_context
    def exit_context(self, pair: str, pos: Position, D: datetime) -> ExitContext | None:
        fr = self._latest.get((pair, D))
        if fr is None or fr.status != "ok" or fr.table is None or pos.entry_bar_open is None:
            return None
        t = fr.table
        sl = t[t.index >= pd.Timestamp(pos.entry_bar_open)]
        return ExitContext(bar_close_ts=D, highs=sl["high"].to_numpy(dtype=float), lows=sl["low"].to_numpy(dtype=float),
                           atrs=sl["atr_tf"].to_numpy(dtype=float), regime_last=_text(t["regime"].iloc[-1]),
                           last_close=float(t["close"].iloc[-1]), n_closed=len(sl))
