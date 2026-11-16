"""Terfi kapisi (§3.4) ve Turkce rapor. Esikler config.GATE'te DONDURULMUSTUR.

Girdi: `oof` tablosu -- yalniz test dilimlerinden (modelin egitimde gormedigi donem) satirlar:
  ts, pair, fold, taken, label, net_r, cost_r, base_rate (o dilimin egitim taban orani) ve model basina
  kalibre olasilik sutunu (p_logit, p_lgbm ...).
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field

import numpy as np
import pandas as pd

from trader_core.stats import (adjust_pvalues, deflated_sharpe, optimal_block_length, pbo_cscv, return_moments,
                               stationary_bootstrap_indices)

from .config import FEE_RATE, GATE, SLIPPAGE_RATE, THRESHOLD_GRID


# ------------------------------------------------------------------------------------- yardimcilar
def rankdata(x: np.ndarray) -> np.ndarray:
    """Ortalama sira (bagli degerler ortalama)."""
    x = np.asarray(x, dtype=float)
    order = np.argsort(x, kind="mergesort")
    r = np.empty(len(x))
    xs = x[order]
    i = 0
    while i < len(x):
        j = i
        while j + 1 < len(x) and xs[j + 1] == xs[i]:
            j += 1
        r[order[i:j + 1]] = (i + j) / 2.0 + 1.0
        i = j + 1
    return r


def spearman(a, b) -> float:
    if len(a) < 3:
        return float("nan")
    ra, rb = rankdata(a), rankdata(b)
    if ra.std() == 0 or rb.std() == 0:
        return float("nan")
    return float(np.corrcoef(ra, rb)[0, 1])


def rho_t(rho: float, n: int) -> float:
    if not np.isfinite(rho) or n < 3:
        return float("nan")
    return float(rho * math.sqrt((n - 2) / max(1e-12, 1.0 - rho * rho)))


def select_threshold(p: np.ndarray, r: np.ndarray, min_frac: float = GATE["min_taken_frac"]):
    """(esik|None, ayrinti). [0,45-0,70] izgarasinda alinan oran >= min_frac sartiyla filtreli ortalama
    net R'yi enyukselten esik (esitlikte dusuk). Uygun esik yoksa None."""
    best = None
    for th in THRESHOLD_GRID:
        m = p >= th
        if m.mean() < min_frac or m.sum() == 0:
            continue
        v = float(r[m].mean())
        if best is None or v > best[1] + 1e-12:
            best = (th, v)
    return (best[0] if best else None), best


def _day(ts) -> pd.Series:
    return pd.Series(pd.to_datetime(ts, utc=True)).dt.floor("D").reset_index(drop=True)


def daily_mean(ts, *cols) -> list[np.ndarray]:
    """Ayni gun (UTC) satirlarini ortalayarak bagimsiz-olmayan (ayni mum/gun) gozlemleri tek gozleme indirir."""
    d = _day(ts)
    frame = pd.DataFrame({f"c{i}": np.asarray(c, dtype=float) for i, c in enumerate(cols)})
    g = frame.groupby(d.to_numpy()).mean()
    return [g[f"c{i}"].to_numpy() for i in range(len(cols))]


def daily_pnl(ts, r: np.ndarray, span) -> np.ndarray:
    """Filtreli islemlerin gunluk net R toplami; span=(ilk gun, son gun) takvimi boyunca (islemsiz gun = 0)."""
    s = pd.Series(np.asarray(r, dtype=float)).groupby(_day(ts).to_numpy()).sum()
    days = pd.date_range(span[0], span[1], freq="D")
    return s.reindex(days, fill_value=0.0).to_numpy()


def max_drawdown(r: np.ndarray) -> float:
    c = np.cumsum(r)
    return float(np.max(np.maximum.accumulate(np.r_[0.0, c])[1:] - c)) if len(r) else 0.0


def stress_r(df: pd.DataFrame) -> np.ndarray:
    """Komisyon x2 + 5 bp TARAF BASINA (tur basina 10 bp) kolu: ek maliyet = notional orani * (entry/R).
    cost_r yalniz komisyon+kayma oldugundan entry/R onunla geri cikarilir (schema.py)."""
    entry_over_r = df["cost_r"].to_numpy() / (2.0 * (FEE_RATE + SLIPPAGE_RATE))
    extra = ((GATE["stress_fee_mult"] - 1.0) * 2.0 * FEE_RATE
             + 2.0 * GATE["stress_extra_bp_per_side"] * 1e-4) * entry_over_r
    return df["net_r"].to_numpy() - extra


def boot_delta(r: np.ndarray, m: np.ndarray, n_boot: int = 2000, seed: int = 0) -> dict:
    """Filtreli - filtresiz ortalama net R icin durağan bootstrap (tek tarafli %90 alt sinir, p)."""
    n = len(r)
    if n < 10 or m.sum() == 0:
        return {"lower": float("nan"), "p": 1.0, "delta": float("nan")}
    rng = np.random.default_rng(seed)
    mb = max(1.0, optimal_block_length(r)["stationary"])
    idx = stationary_bootstrap_indices(n, n_boot, mb, rng)
    rb, mbk = r[idx], m[idx]
    cnt = mbk.sum(axis=1)
    filt = np.divide((rb * mbk).sum(axis=1), cnt, out=np.zeros(n_boot), where=cnt > 0)
    d = filt - rb.mean(axis=1)
    return {"lower": float(np.quantile(d, GATE["bootstrap_alpha_two_sided"] / 2.0)),
            "p": float(np.mean(d <= 0.0)), "delta": float(r[m].mean() - r.mean()), "mean_block": mb}


# ------------------------------------------------------------------------------------- model degerlendirme
@dataclass
class Check:
    name: str
    ok: bool | None            # None = atlandi
    value: str
    rule: str
    detail: str = ""


@dataclass
class GateResult:
    model: str
    passed: bool
    threshold: float | None
    checks: list[Check] = field(default_factory=list)
    metrics: dict = field(default_factory=dict)

    @property
    def first_failure(self) -> Check | None:
        return next((c for c in self.checks if c.ok is False), None)


def model_metrics(oof: pd.DataFrame, pcol: str, n_boot: int = 2000) -> dict:
    """Bir model icin esik secimi ve Bolum 1 olculeri (evren = stratejinin aldigi adaylar)."""
    U = oof[oof["taken"]].sort_values(["ts", "pair"], kind="mergesort")
    p, r = U[pcol].to_numpy(), U["net_r"].to_numpy()
    th, best = select_threshold(p, r)
    feasible = th is not None
    th_used = th if feasible else float(np.quantile(p, 1.0 - GATE["min_taken_frac"]))   # yalniz rapor icin
    tcol = "th_" + pcol[2:] if pcol.startswith("p_") else None
    if tcol is not None and tcol in U.columns:
        # ILERI YONLU esik: her satirin esigi yalniz o satirdan once bilinen dilimlerle secildi (NaN = esik yok -> alinmaz)
        m = p >= U[tcol].to_numpy(float)
    else:
        m = p >= th_used
    out = {"threshold": th, "threshold_used": th_used, "feasible": feasible, "n": int(len(U)),
           "taken_frac": float(m.mean()), "mean_all": float(r.mean()),
           "mean_filtered": float(r[m].mean()) if m.any() else float("nan")}
    out.update(boot_delta(r, m, n_boot))
    # DSR: gunluk toplulastirilmis filtreli net R serisi (ayni mum/gun adaylari bagimsiz sayilmaz)
    rf = r[m]
    ts_u = U["ts"].to_numpy()
    rd = daily_pnl(ts_u[m], rf, (_day(ts_u).min(), _day(ts_u).max())) if m.any() else np.array([])
    sr = float(rd.mean() / rd.std(ddof=1)) if len(rd) > 2 and rd.std(ddof=1) > 0 else float("nan")
    g3, g4 = return_moments(rd) if len(rd) > 2 else (0.0, 3.0)
    out["sr_per_trade"], out["n_filtered"], out["n_days"] = sr, int(m.sum()), int(len(rd))
    out["dd_all"], out["dd_filtered"] = max_drawdown(r), max_drawdown(rf)
    out["skew"], out["kurt"] = g3, g4
    # tek cift cikarilinca
    loo = {}
    for pair in sorted(U["pair"].unique()):
        k = (U["pair"] != pair).to_numpy()
        if k.sum() > 5 and m[k].any():
            loo[pair] = float(r[k & m].mean() - r[k].mean())
        else:
            loo[pair] = float("nan")
    out["leave_one_pair_delta"] = loo
    # maliyet stresi
    rs = stress_r(U)
    out["stress_filtered"] = float(rs[m].mean()) if m.any() else float("nan")
    out["_U_index"] = U.index
    return out


def pbo_for(oof: pd.DataFrame, pcols: list[str]) -> dict:
    """Yapilandirma = model x esik; satir = gun (alinan islemlerin gunluk net R toplami)."""
    U = oof[oof["taken"]]
    days = pd.date_range(U["ts"].min().floor("D"), U["ts"].max().floor("D"), freq="D")
    cols = {}
    for pc in pcols:
        for th in (0.45, 0.50, 0.55, 0.60, 0.65, 0.70):
            s = U["net_r"].where(U[pc] >= th, 0.0).groupby(U["ts"].dt.floor("D")).sum()
            cols[f"{pc}@{th:.2f}"] = s.reindex(days, fill_value=0.0).to_numpy()
    M = np.column_stack(list(cols.values()))
    keep = M.std(axis=0) > 0
    if keep.sum() < 2 or len(days) < 32:
        return {"pbo": float("nan"), "n_configs": int(keep.sum()), "T": len(days)}
    res = pbo_cscv(M[:, keep], n_splits=16, max_combinations=2000, seed=0)
    return {"pbo": float(res.pbo), "n_configs": int(keep.sum()), "T": len(days)}


def run_gate(oof: pd.DataFrame, pcols: list[str], *, selected: str, parity_max_abs_diff: float | None,
             n_trials: int, incumbent_filtered_mean: float | None = None, n_boot: int = 2000) -> GateResult:
    """Bolum 3.4: sirayla IC, kalibrasyon, Bolum 1 olculeri, maliyet, esleme, gorevdekine karsi."""
    G = GATE
    met = {pc: model_metrics(oof, pc, n_boot) for pc in pcols}
    mm = met[selected]
    res = GateResult(model=selected, passed=False, threshold=mm["threshold"], metrics={"per_model": met})
    C = res.checks

    # 1) IC kapisi: gunluk toplulastirma (ayni gun/mum adaylari bagimsiz sayilmaz), tam 4 dilim, >= 3 pozitif
    L = oof[oof["label"].notna()]
    ds, dr = daily_mean(L["ts"], L[selected], L["net_r"])
    rho = spearman(ds, dr)
    t = rho_t(rho, len(ds))
    all_folds = sorted(oof["fold"].unique())
    fr = {}
    for f in all_folds:
        Lf = L[L["fold"] == f]
        a_, b_ = daily_mean(Lf["ts"], Lf[selected], Lf["net_r"]) if len(Lf) else ([], [])
        fr[int(f)] = spearman(a_, b_)
    pos = sum(1 for v in fr.values() if np.isfinite(v) and v > 0)
    need, want = G["ic_min_pos_folds"], G["required_folds"]
    ok = bool(len(all_folds) == want and np.isfinite(rho) and rho > 0 and t >= G["ic_min_t"] and pos >= need)
    C.append(Check("1. IC kapisi", ok, f"rho={rho:.4f}, t={t:.2f} (n={len(ds)} gun), pozitif dilim {pos}/{len(all_folds)}",
                   f"tam {want} dilim degerlendirilmis, rho>0, t>={G['ic_min_t']}, en az {need} dilim pozitif (gunluk toplulastirma)",
                   "dilim rho: " + ", ".join(f"{k}:{v:+.3f}" for k, v in fr.items())))
    res.metrics["ic"] = {"rho": rho, "t": t, "fold_rho": fr, "n_days": int(len(ds))}

    # 2) kalibrasyon
    brier = float(np.mean((L[selected] - L["label"]) ** 2))
    brier0 = float(np.mean((L["base_rate"] - L["label"]) ** 2))
    C.append(Check("2. Kalibrasyon (Brier)", brier < brier0, f"model={brier:.5f}, sabit taban={brier0:.5f}",
                   "model Brier < sabit taban orani Brier"))
    res.metrics["brier"] = {"model": brier, "base": brier0}

    # 3) Bolum 1 olculeri
    C.append(Check("3a. Esik bulundu", mm["feasible"],
                   f"esik={mm['threshold']}" if mm["feasible"] else f"yok (rapor esigi={mm['threshold_used']:.3f})",
                   f"[0,45-0,70] izgarasinda alinan oran >= {G['min_taken_frac']:.0%}"))
    C.append(Check("3b. Net R farki (filtreli-filtresiz)", bool(mm["delta"] >= G["delta_net_r_min"]
                   and mm["lower"] > 0), f"fark={mm['delta']:+.4f} R, boot %90 alt sinir={mm['lower']:+.4f}",
                   f"fark >= +{G['delta_net_r_min']} R ve alt sinir > 0"))
    C.append(Check("3c. Filtreli net beklenti", bool(mm["mean_filtered"] > G["filtered_expectancy_min"]),
                   f"{mm['mean_filtered']:+.4f} R (filtresiz {mm['mean_all']:+.4f})", "> 0 R"))
    dsr = (deflated_sharpe(mm["sr_per_trade"], mm["n_days"], mm["skew"], mm["kurt"], n_trials=n_trials)
           if np.isfinite(mm["sr_per_trade"]) else float("nan"))
    C.append(Check("3d. Deflated Sharpe", bool(np.isfinite(dsr) and dsr >= G["dsr_min"]),
                   f"DSR={dsr:.4f} (deneme sayisi {n_trials}, {mm['n_days']} gunluk gozlem)", f">= {G['dsr_min']}"))
    pbo = pbo_for(oof, pcols)
    C.append(Check("3e. PBO (CSCV)", bool(np.isfinite(pbo["pbo"]) and pbo["pbo"] <= G["pbo_max"]),
                   f"PBO={pbo['pbo']:.3f} ({pbo['n_configs']} yapilandirma, {pbo['T']} gun)", f"<= {G['pbo_max']}"))
    C.append(Check("3f. En buyuk dusus", bool(mm["dd_filtered"] <= mm["dd_all"] + 1e-12),
                   f"filtreli={mm['dd_filtered']:.2f} R, filtresiz={mm['dd_all']:.2f} R", "filtreli <= filtresiz"))
    loo = mm["leave_one_pair_delta"]
    loo_ok = all(np.isfinite(v) and v > 0 for v in loo.values()) if loo else False
    C.append(Check("3g. Dejenerasyon korumasi", bool(mm["taken_frac"] >= G["min_taken_frac"] - 1e-12 and loo_ok),
                   f"alinan oran={mm['taken_frac']:.1%}; tek cift cikarilinca en kotu fark="
                   f"{min(loo.values()) if loo else float('nan'):+.4f} R",
                   f"alinan >= {G['min_taken_frac']:.0%} ve her tek-cift-cikarmada fark > 0"))
    ps = [met[c]["p"] for c in pcols]
    adj = adjust_pvalues(ps, "holm")
    padj = float(adj[pcols.index(selected)])
    C.append(Check("3h. Holm (coklu karsilastirma)", bool(padj <= G["holm_alpha"]),
                   f"duzeltilmis p={padj:.4f} ({len(pcols)} model)", f"<= {G['holm_alpha']}"))
    # 4) maliyet dayaniklilik
    C.append(Check("4. Maliyet dayanikliligi (komisyon x2 + 5 bp/taraf)", bool(mm["stress_filtered"] >= G["stress_expectancy_min"]),
                   f"{mm['stress_filtered']:+.4f} R", f">= {G['stress_expectancy_min']} R"))
    # 5) esleme
    if parity_max_abs_diff is None:
        C.append(Check("5. Esleme (motor okuyucusu = LightGBM)", None, "atlandi", "lojistik model: LightGBM yok"))
    else:
        C.append(Check("5. Esleme (motor okuyucusu = LightGBM)", bool(parity_max_abs_diff <= G["parity_tol"]),
                       f"en buyuk fark={parity_max_abs_diff:.3e}", f"<= {G['parity_tol']:.0e}"))
    # 6) gorevdekine karsi
    if incumbent_filtered_mean is None:
        C.append(Check("6. Gorevdeki modele karsi", None, "atlandi (etkin model yok)", "aday >= gorevdeki"))
    else:
        C.append(Check("6. Gorevdeki modele karsi", bool(mm["mean_filtered"] >= incumbent_filtered_mean),
                       f"aday={mm['mean_filtered']:+.4f} R, gorevdeki={incumbent_filtered_mean:+.4f} R",
                       "aday, gorevdekinden kotu degil"))
    res.metrics["pbo"], res.metrics["dsr"], res.metrics["holm_p"] = pbo, dsr, padj
    res.passed = all(c.ok is not False for c in C)
    return res
