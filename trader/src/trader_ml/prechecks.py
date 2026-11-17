"""Kosu oncesi korumalar (ML-G1, plan bolum J): ozellik sagligi + guc on hesabi. Kapi esikleri/mantigi DEGISMEZ.

Karar (plan J: "bos/sabit/kopya -> kosu reddi"): GERCEK kosuda saglıksiz ozellik OTOMATIK ATILMAZ, kosu REDDEDILIR
(FeatureHealthError); ozellik listesi sessizce degisirse tarif (ozellik listesi ad ad on kayitli) degismis olur.
Sentetik/test kipinde yalniz rapora uyari yazilir (fixture'in sabit ozellikleri boru hatti dumanini engellemesin).
"""
from __future__ import annotations

import math

import numpy as np
import pandas as pd

from trader_core.stats import deflated_sharpe

from .config import GATE
from .schema import feature_columns
from .walkforward import make_folds


def _cdf(x: float) -> float:
    return 0.5 * (1.0 + math.erf(x / math.sqrt(2.0)))


class FeatureHealthError(ValueError):
    """Bos / sabit / kopya ozellik: gercek kosu reddedilir."""


def feature_health(df: pd.DataFrame, names: list[str] | None = None, *, recipe=None) -> dict:
    """{'all_nan': [...], 'constant': [...], 'duplicate': [(kopya, asil), ...], 'healthy': [...], 'ok': bool}.
    Sabit = en fazla 1 farkli bos-olmayan deger (kismen bos olup sabit kalan dahil). Kopya = baska bir
    ozellikle birebir ayni sutun (NaN konumlari dahil); ilk gorulen asil sayilir. Bos/sabit olanlar kopya aramasina girmez."""
    if names is None and recipe is not None and recipe.features:
        names = list(recipe.features)                       # tarifin ad ad listesi (eksik sutun KeyError: sessiz atlama yok)
    names = list(names) if names is not None else feature_columns(df)
    all_nan, const, dup, seen = [], [], [], {}
    for c in names:
        s = df[c]
        if s.isna().all():
            all_nan.append(c)
            continue
        if s.nunique(dropna=True) <= 1:
            const.append(c)
            continue
        key = (s.isna().to_numpy().tobytes(), s.fillna(0.0).to_numpy(float).tobytes())
        if key in seen:
            dup.append((c, seen[key]))
        else:
            seen[key] = c
    bad = set(all_nan) | set(const) | {d for d, _ in dup}
    return {"all_nan": all_nan, "constant": const, "duplicate": dup,
            "healthy": [c for c in names if c not in bad], "n_features": len(names), "ok": not bad}


def assert_feature_health(h: dict) -> None:
    if not h["ok"]:
        raise FeatureHealthError(
            f"ozellik sagligi basarisiz (kosu reddedildi; sessizce atilmaz): bos={h['all_nan']}, sabit={h['constant']}, "
            f"kopya={[f'{a}=={b}' for a, b in h['duplicate']]}")


def required_sr_for_dsr(n_days: int, n_trials: int, *, skew: float = 0.0, kurt: float = 3.0,
                        dsr_min: float = GATE["dsr_min"]) -> float:
    """Kapinin kendi deflated_sharpe fonksiyonuyla DSR >= dsr_min icin gereken GUNLUK Sharpe (ikili arama)."""
    if n_days < 3:
        return float("inf")
    lo, hi = 0.0, 5.0
    if deflated_sharpe(hi, n_days, skew, kurt, n_trials=n_trials) < dsr_min:
        return float("inf")
    for _ in range(80):
        mid = (lo + hi) / 2
        if deflated_sharpe(mid, n_days, skew, kurt, n_trials=n_trials) >= dsr_min:
            hi = mid
        else:
            lo = mid
    return hi


def required_ic_rho(n_days: int, t_min: float = GATE["ic_min_t"]) -> float:
    """gate.rho_t(rho, n) = rho*sqrt((n-2)/(1-rho^2)) >= t_min  =>  rho >= t/sqrt(t^2 + n - 2)."""
    return float("inf") if n_days <= 2 else t_min / math.sqrt(t_min ** 2 + n_days - 2)


def power_precheck(n_days_dsr: int, n_days_ic: int, n_trials: int, *, expected_daily_sr: float | None = None,
                   expected_ic: float | None = None) -> dict:
    """Gereken t (DSR ve IC) ve rho; beklenen etki verilirse ulasilabilirlik + yaklasik guc (normal yaklasim)."""
    sr_req = required_sr_for_dsr(n_days_dsr, n_trials)
    out = {"n_days_dsr": int(n_days_dsr), "n_days_ic": int(n_days_ic), "n_trials": int(n_trials),
           "required_daily_sr": sr_req,
           "required_t_dsr": sr_req * math.sqrt(n_days_dsr) if math.isfinite(sr_req) else float("inf"),
           "required_ic_rho": required_ic_rho(n_days_ic), "required_t_ic": GATE["ic_min_t"],
           "expected_daily_sr": expected_daily_sr, "expected_ic": expected_ic}
    if expected_daily_sr is not None:
        t = expected_daily_sr * math.sqrt(n_days_dsr)
        out["expected_t_dsr"] = t
        out["dsr_reachable"] = bool(t >= out["required_t_dsr"])
        out["dsr_power_approx"] = float(_cdf(t - out["required_t_dsr"]))
    if expected_ic is not None:
        t = expected_ic * math.sqrt((n_days_ic - 2) / max(1e-12, 1 - expected_ic ** 2)) if n_days_ic > 2 else 0.0
        out["expected_t_ic"] = t
        out["ic_reachable"] = bool(t >= GATE["ic_min_t"])
        out["ic_power_approx"] = float(_cdf(t - GATE["ic_min_t"]))
    return out


def corpus_power(t: pd.DataFrame, n_trials: int, *, recipe=None, fold_kwargs: dict | None = None, **kw) -> dict:
    """Aday tablosundan sinav (OOF) gun sayilarini kestirir: DSR = test dilimlerinin takvim gunu; IC = alinan satiri olan gun.
    Pencere: fold_kwargs (make_folds kwarg'lari) ya da recipe.wf; ikisi de yoksa r01 penceresi."""
    wf = fold_kwargs if fold_kwargs is not None else (recipe.wf if recipe is not None else {})
    folds = make_folds(t, **wf)
    days = sum(max(0, int((f["test_end"] - f["test_start"]) / pd.Timedelta(days=1))) for f in folds if len(f["test_rows"]))
    rows = np.concatenate([f["test_rows"] for f in folds if len(f["test_rows"])]) if folds else np.array([], int)
    sub = t.iloc[rows]
    sub = sub[sub["taken"].astype(bool) & sub["label"].notna()]
    ic_days = int(pd.to_datetime(sub["ts"], utc=True).dt.floor("D").nunique())
    return power_precheck(days, ic_days, n_trials, **kw)


def power_lines(p: dict) -> list[str]:
    f = lambda v, nd=2: "yok" if v is None or not math.isfinite(v) else f"{v:.{nd}f}"
    L = [f"Guc on hesabi (n_trials={p['n_trials']}): DSR icin {p['n_days_dsr']} gun -> gereken t={f(p['required_t_dsr'])} "
         f"(gunluk SR>={f(p['required_daily_sr'], 4)}); IC icin {p['n_days_ic']} gun -> t>={f(p['required_t_ic'])} "
         f"<=> rho>={f(p['required_ic_rho'], 3)}"]
    if "expected_t_dsr" in p:
        L.append(f"  beklenen gunluk SR={p['expected_daily_sr']} -> t={f(p['expected_t_dsr'])}: "
                 f"{'ulasilabilir' if p['dsr_reachable'] else 'ULASILAMAZ'} (yaklasik guc {f(p['dsr_power_approx'])})")
    if "expected_t_ic" in p:
        L.append(f"  beklenen IC={p['expected_ic']} -> t={f(p['expected_t_ic'])}: "
                 f"{'ulasilabilir' if p['ic_reachable'] else 'ULASILAMAZ'} (yaklasik guc {f(p['ic_power_approx'])})")
    return L
