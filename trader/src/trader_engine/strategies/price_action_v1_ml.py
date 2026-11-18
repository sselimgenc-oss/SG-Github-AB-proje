"""PriceActionV1Ml: price_action_v1 (v1b) sarmalayici + ML meta-etiket FILTRESI (ML-0a, 19a; 05 §13.4a).

Yalniz KALDIRIR: aday ekleyemez; fiyat/stop/hedef/boyut/kaldirac degistirmez (`post_filter` sozlesmesi: signal True -> False).
`ml_mode`: off (varsayilan; v1b ile BIREBIR ayni cikti), shadow (puani `reasons`a `ml:p=` yazar, hicbir adayi elemez),
active (puan < esik => `signal=False, skip_reason='ml_filter'`; model yok/suresi dolmus/puanlanamamis => ayni eleme, yani
yeni giris yok = fail-closed; cikislar ve kapi zinciri etkilenmez). Puan `compute`ta (saf: yalniz ctx.bars/ctx.model'e bagli)
hesaplanir ve `reasons` basina yazilir; `post_filter` yalniz `ctx.model.threshold` ile karsilastirir (bars gerektirmez,
precomputed yolunda da calisir). Ozellikler `trader_core.ml_features` (egitim hattiyla AYNI kod) ile uretilir."""
from __future__ import annotations

import dataclasses
import logging
from collections.abc import Mapping
from datetime import datetime

import numpy as np
import pandas as pd

from trader_core.ml_features import FEATURE_NAMES, feature_frame
from trader_core.ml_package import MlModelView, load_model_view, ml_score_from_reasons

from .base import ExitPolicy, StrategyContext, StrategyError
from .price_action_v1 import PriceActionV1, make_v1b

log = logging.getLogger("engine.strategy.ml")
ML_MODES = ("off", "shadow", "active")


def load_engine_model(path: str | None, ml_mode: str, now: datetime,
                      expected_features=None, *, experimental: bool = False) -> tuple[MlModelView | None, str | None]:
    """Motor tarafi yukleme: kapi (gate_passed True) + hash + 21 gun + ozellik listesi (+ active icin kullanici onayi).
    `experimental=True` (yalniz shadow; aksi ValueError -> (None, kod)): kapi denetimi atlanir, hash/sure kalir.
    Hata -> (None, kod): `active`te yeni giris yok, `shadow`da yalniz uyari (log + sayac)."""
    if not path:
        return None, "ml_model_path_missing"
    try:
        if experimental:
            log.info("ML modeli DENEYSEL yukleniyor (ml_exp=1, kapi atlandi, yalniz shadow): %s", path)
        return load_model_view(path, expected_features=FEATURE_NAMES if expected_features is None else expected_features, ml_mode=ml_mode, now=now,
                                experimental=experimental), None
    except (OSError, ValueError, KeyError, TypeError) as e:
        log.warning("ML modeli yuklenemedi (%s): %s: %s", ml_mode, type(e).__name__, e)
        return None, f"{type(e).__name__}: {e}"


class PriceActionV1Ml:
    def __init__(self, inner: PriceActionV1, *, name: str, version: str) -> None:
        self._inner = inner
        self.ml_mode = "off"
        self.score_history = False                          # True: tablodaki TUM aday satirlari puanlanir (onhesapli backtest)
        self.counters = inner.counters                      # ayni Counter: shadow_r1/shadow_reentry + ml_* tek yerde
        self.info = dataclasses.replace(inner.info, name=name, version=version)

    def set_ml_mode(self, mode: str) -> None:
        if mode not in ML_MODES:
            raise StrategyError("bad_ml_mode", f"ml_mode gecersiz: {mode!r} (izinli: {ML_MODES})")
        self.ml_mode = mode

    def __getattr__(self, item: str):                       # setups_enabled, block_same_bar_reentry ...
        if item == "_inner":
            raise AttributeError(item)
        return getattr(self._inner, item)

    def label(self) -> str:
        return f"strategy:{self.info.name}@{self.info.version}"

    def validate_params(self, m: Mapping) -> Mapping:
        return self._inner.validate_params(m)

    def exit_policy(self) -> ExitPolicy | None:
        return self._inner.exit_policy()

    # ------------------------------------------------------------------ compute (puanlama)
    def compute(self, ctx: StrategyContext) -> pd.DataFrame:
        sig = self._inner.compute(ctx)
        if self.ml_mode == "off":
            return sig
        cand = sig["signal"].astype(bool)
        if not self.score_history:                          # canli yol: yalniz karar barinin adayi puanlanir (maliyet)
            cand = cand & (sig.index == sig.index[-1])
        if not bool(cand.any()):
            return sig
        model = ctx.model
        if model is None or model.expired(ctx.D):
            return sig                                      # etiket yok; post_filter durumu (shadow: uyari, active: eleme) belirler
        try:
            if ctx.ml_v2 is not None:                       # ML-G5 (bayrakli): r02/r03, motor hesapladi (iki gecisli)
                X = self._x_v2(ctx, model, sig.index[cand])
            else:
                fr = feature_frame(ctx.bars[ctx.tf][["open", "high", "low", "close"]])
                X = fr.loc[sig.index[cand], list(model.features)].to_numpy(dtype=float)
            p = np.asarray(model.score(X), dtype=float)
            if not np.isfinite(p).all():
                raise ValueError("puan sonlu degil")
        except Exception as e:  # noqa: BLE001 - puanlanamayan aday etiketsiz kalir (active: elenir, shadow: gecer)
            self.counters["ml_score_errors"] += 1
            log.error("ML puanlama hatasi: %s: %s", type(e).__name__, e)
            return sig
        out = sig.copy()
        reasons = out["reasons"].astype(object).copy()
        exp = "ml_exp=1|" if getattr(model, "experimental", False) else ""     # golge deneyi: kapidan gecmemis paket
        tags = pd.Series([f"ml:p={float(v):.6f}|{exp}" for v in p], index=sig.index[cand], dtype=object)
        reasons.loc[cand] = tags + reasons.loc[cand].astype(str)
        out["reasons"] = reasons
        return out

    def native_candidate(self, ctx: StrategyContext) -> dict | None:
        """ML-G5 birinci gecis: yerel v1b adayi (ML'siz `inner.compute`, karar mumu) ya da None. Yalniz okur."""
        sig = self._inner.compute(ctx)
        last = sig.iloc[-1]
        if not bool(last["signal"]) or last["side"] not in ("long", "short"):
            return None
        return {"side": last["side"], "planned_entry": float(last["planned_entry"]),
                "planned_stop": float(last["planned_stop"])}

    @staticmethod
    def _x_v2(ctx: StrategyContext, model: MlModelView, idx) -> np.ndarray:
        bf = ctx.ml_v2
        if getattr(bf, "error", None):
            raise ValueError(f"ml_v2: {bf.error}")
        if len(idx) != 1:
            raise ValueError("ml_v2 yalniz karar mumunun tek adayini puanlar")
        row = bf.rows[ctx.pair]
        return np.array([[row[n] for n in model.features]], dtype=float)

    # ------------------------------------------------------------------ post_filter (yalniz kaldirma)
    def post_filter(self, row: pd.Series, ctx: StrategyContext) -> pd.Series:
        row = self._inner.post_filter(row, ctx)
        if self.ml_mode == "off" or not bool(row["signal"]):
            return row
        model = ctx.model
        if model is None:
            return self._decide(row, "no_model")
        if model.expired(ctx.D):
            return self._decide(row, "expired")
        p = ml_score_from_reasons(str(row["reasons"]))
        if p is None:
            return self._decide(row, "unscored")
        if self.ml_mode == "active" and p < model.threshold:
            return self._decide(row, "filter")
        self.counters["ml_pass" if self.ml_mode == "active" else "ml_shadow_scored"] += 1
        return row

    def _decide(self, row: pd.Series, why: str) -> pd.Series:
        """why: no_model | expired | unscored | filter. shadow'da yalniz sayac/uyari; active'te aday notrlenir."""
        self.counters[f"ml_{why}"] += 1
        if self.ml_mode != "active":
            return row
        r = row.copy()
        r["signal"] = False
        r["skip_reason"] = "ml_filter"
        r["reasons"] = f"ml:{why}|" + str(row["reasons"])
        return r


def make_v1b_ml() -> PriceActionV1Ml:
    return PriceActionV1Ml(make_v1b(), name="price_action_v1_ml", version="1b.0-ml0")
