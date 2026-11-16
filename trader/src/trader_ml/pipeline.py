"""Uctan uca egitim hatti + kapi (ML-0c): aday tablosu -> purged walk-forward OOF -> model secimi ->
nihai model -> JSON paketi -> kapi -> Turkce rapor.

Kullanim:  python -m trader_ml.pipeline --synthetic --out DIR
           python -m trader_ml.pipeline --candidates 19b_candidates.parquet --out DIR [--limits]
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

from . import models
from .config import GATE, RECIPE_ID
from .gate import GateResult, model_metrics, run_gate
from .guards import assert_pre_holdout
from .package import build_package, data_hash, load_package, save_package
from .report import render_report
from .resources import apply_limits, peak_rss_mb
from .schema import feature_columns, validate_candidates
from .treeeval import TreeModel
from .walkforward import make_folds

MODELS = ("logistic", "lgbm")


def _fold_models(X, y, w, tr):
    out = {"logistic": models.fit_logistic(X[tr], y[tr], w[tr])}
    try:
        booster, best = models.fit_lgbm(X[tr], y[tr], w[tr])
        out["lgbm"] = (booster, best)
    except ImportError:                                   # lightgbm yok -> yalniz lojistik
        pass
    return out


def run_oof(t: pd.DataFrame, names: list[str]):
    X, y = t[names].to_numpy(float), t["label"].to_numpy(float)
    folds = make_folds(t)
    rows, last, bests = [], None, []
    for f in folds:
        tr, te = f["train_rows"], f["test_rows"]
        if len(tr) < 100 or len(te) == 0:
            continue
        w = models.sample_weights(t.iloc[tr], t["ts"].iloc[tr].max())
        fm = _fold_models(X, y, w, tr)
        d = t.iloc[te][["ts", "pair", "taken", "label", "net_r", "cost_r"]].copy()
        d["fold"] = f["fold"]
        d["base_rate"] = float(np.average(y[tr], weights=w))
        d["z_logistic"] = TreeModel(fm["logistic"]).predict_raw(X[te])
        if "lgbm" in fm:
            d["z_lgbm"] = fm["lgbm"][0].predict(X[te], raw_score=True)
            bests.append(fm["lgbm"][1])
        rows.append(d)
        last = (f, fm, te)
    return folds, pd.concat(rows), last, bests


def run(t: pd.DataFrame, out_dir: str | Path, *, synthetic: bool = False, n_trials: int = 2, n_boot: int = 2000,
        now: datetime | None = None) -> dict:
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    t = validate_candidates(t)
    assert_pre_holdout(t["ts"], "egitim girdisi")
    t = t[t["label"].notna()].reset_index(drop=True)
    names = feature_columns(t)
    X, y = t[names].to_numpy(float), t["label"].to_numpy(float)
    folds, oof, last, bests = run_oof(t, names)
    kinds = [m for m in MODELS if f"z_{m}" in oof.columns]

    cal = {}
    for m in kinds:                                          # Platt: yalniz test dilimleri (§3.3 adim 4)
        cal[m] = models.fit_platt(oof[f"z_{m}"].to_numpy(), oof["label"].to_numpy())
        a, b = cal[m]["a"], cal[m]["b"]
        oof[f"p_{m}"] = 1.0 / (1.0 + np.exp(-(a * oof[f"z_{m}"] + b)))
    pcols = [f"p_{m}" for m in kinds]

    # model secimi: LightGBM net R'de lojistigi gecemezse lojistik (§3.3 adim 3)
    pm = {m: model_metrics(oof, f"p_{m}", n_boot=200) for m in kinds}
    selected, reason = "logistic", "taban"
    if "lgbm" in kinds:
        a_, b_ = pm["lgbm"]["mean_filtered"], pm["logistic"]["mean_filtered"]
        if np.isfinite(a_) and (not np.isfinite(b_) or a_ > b_):
            selected, reason = "lgbm", f"filtreli net R {a_:+.4f} > lojistik {b_:+.4f}"
        else:
            reason = f"LightGBM lojistigi net R'de gecemedi ({_fmt(a_)} <= {_fmt(b_)})"
    th = pm[selected]["threshold"]

    # nihai model: tum egitim penceresi (kilitli donem yok)
    w_all = models.sample_weights(t, t["ts"].max())
    if selected == "lgbm":
        booster, _ = models.fit_lgbm(X, y, w_all, num_rounds=max(10, int(np.median(bests))))
        model = models.lgbm_dump(booster)
    else:
        booster, model = None, models.fit_logistic(X, y, w_all)
    pkg = build_package(model, cal[selected], th,
                        names, X, t["ts"].min(), t["ts"].max(), data_hash(t),
                        created_at=now, extra={"selected_reason": reason, "threshold_feasible": th is not None,
                                               "synthetic": synthetic, "n_trials": n_trials})
    pkg_path = save_package(pkg, out_dir / "model_candidate.json")
    pkg = load_package(pkg_path, now=now)                     # hash'ler tutuyor mu (gidis-donus)

    # esleme: motor okuyucusu == egitim kutuphanesi, tutulan (test) satirlarda
    f_last, fm_last, te_last = last
    Xte = X[te_last]
    if selected == "lgbm":
        ref = fm_last["lgbm"][0].predict(Xte, raw_score=True)
        ev = TreeModel(models.lgbm_dump(fm_last["lgbm"][0])).predict_raw(Xte)
        ev2 = TreeModel(pkg["model"]).predict_raw(Xte)
        ref2 = booster.predict(Xte, raw_score=True)
        parity = float(max(np.max(np.abs(ev - ref)), np.max(np.abs(ev2 - ref2)),
                           np.max(np.abs(TreeModel(pkg["model"], pkg["calibration"]).predict_uncalibrated(Xte)
                                         - booster.predict(Xte)))))
    else:
        ref = models.logistic_predict_raw(pkg["model"], Xte)
        parity = float(np.max(np.abs(TreeModel(pkg["model"]).predict_raw(Xte) - ref)))

    res = run_gate(oof, pcols, selected=f"p_{selected}", parity_max_abs_diff=parity, n_trials=n_trials, n_boot=n_boot)
    res.model = selected
    md = render_report(res, meta=pkg["meta"], folds=folds, peak_rss_mb=peak_rss_mb(), synthetic=synthetic,
                       selected_reason=reason)
    (out_dir / "gate_report.md").write_text(md, encoding="utf-8")
    summary = {"passed": res.passed, "model": selected, "threshold": th, "parity_max_abs_diff": parity,
               "checks": [{"name": c.name, "ok": c.ok, "value": c.value} for c in res.checks],
               "package": str(pkg_path), "report": str(out_dir / "gate_report.md"), "peak_rss_mb": peak_rss_mb(),
               "n_candidates": int(len(t)), "n_oof": int(len(oof))}
    (out_dir / "gate_result.json").write_text(json.dumps(summary, indent=1, default=str), encoding="utf-8")
    oof.to_parquet(out_dir / "oof_predictions.parquet")
    return summary


def _fmt(v):
    return f"{v:+.4f}" if isinstance(v, float) and np.isfinite(v) else "-"


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="ML-0c egitim hatti + terfi kapisi")
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--candidates", help="19b ciktisi (parquet/csv)")
    g.add_argument("--synthetic", action="store_true", help="sentetik fixture ile uctan uca")
    ap.add_argument("--out", required=True)
    ap.add_argument("--limits", action="store_true", help="sunucu modu: nice 19, tek cekirdek, 450 MB tavan")
    ap.add_argument("--n-trials", type=int, default=2, help="DSR deneme sayisi (deneme defterinden)")
    a = ap.parse_args(argv)
    if a.limits:
        apply_limits()
    if a.synthetic:
        from .fixture import build_candidate_table, synthetic_candles
        t = build_candidate_table(synthetic_candles())
    else:
        from .schema import load_candidates
        t = load_candidates(a.candidates)
    s = run(t, a.out, synthetic=a.synthetic, n_trials=a.n_trials)
    print(f"{'KABUL' if s['passed'] else 'RED'}: rapor {s['report']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
