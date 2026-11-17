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

from . import config, diagnostics, models, prechecks
from .config import BURN_IN_THRESHOLD, GATE, RECIPE_ID
from .gate import GateResult, model_metrics, run_gate, select_threshold
from .guards import assert_pre_holdout
from .package import build_package, data_hash, load_package, save_package
from .registry import DEFAULT_REGISTRY, n_trials_from_registry
from .report import render_report
from .resources import apply_limits, peak_rss_mb
from .schema import feature_columns, validate_candidates
from .treeeval import TreeModel
from .walkforward import make_folds

MODELS = ("logistic", "lgbm")


class LightGBMRequired(RuntimeError):
    """Gercek (sentetik olmayan) kosuda lightgbm yuklenemedi: kosu BASARISIZ sayilir (sessizce lojistige dusmez)."""


lightgbm_version = models.lightgbm_version


def _fold_models(X, y, w, tr, ts=None, ends=None, *, require_lightgbm: bool = True):
    out = {"logistic": models.fit_logistic(X[tr], y[tr], w[tr])}
    try:
        booster, best = models.fit_lgbm(X[tr], y[tr], w[tr], ts=None if ts is None else ts[tr],
                                        label_end=None if ends is None else ends[tr])
        out["lgbm"] = (booster, best)
    except ImportError as e:
        if require_lightgbm:                              # on kayit: gercek kosuda sessiz dusus YOK
            raise LightGBMRequired(f"lightgbm yuklenemedi, gercek kosu basarisiz: {e}") from e
        # yalniz sentetik/test kipi: lightgbm yok -> yalniz lojistik
    return out


def run_oof(t: pd.DataFrame, names: list[str], *, require_lightgbm: bool = True):
    X, y = t[names].to_numpy(float), t["label"].to_numpy(float)
    folds = make_folds(t)
    ts_arr, ends_arr = t["ts"].to_numpy("datetime64[ns]"), t["label_end_ts"].to_numpy("datetime64[ns]")
    rows, last, bests = [], None, []
    for f in folds:
        tr, te = f["train_rows"], f["test_rows"]
        if len(tr) < 100 or len(te) == 0:
            continue
        w = models.sample_weights(t.iloc[tr], t["ts"].iloc[tr].max())
        fm = _fold_models(X, y, w, tr, ts_arr, ends_arr, require_lightgbm=require_lightgbm)
        d = t.iloc[te][["ts", "pair", "taken", "label", "net_r", "cost_r", "label_end_ts", "exit_ts"]].copy()
        d["fold"] = f["fold"]
        d["test_start"] = f["test_start"]
        d["base_rate"] = float(np.average(y[tr], weights=w))
        d["z_logistic"] = TreeModel(fm["logistic"]).predict_raw(X[te])
        if "lgbm" in fm:
            d["z_lgbm"] = fm["lgbm"][0].predict(X[te], raw_score=True)
            bests.append(fm["lgbm"][1])
        rows.append(d)
        last = (f, fm, te)
    if not rows:
        raise ValueError("hicbir dilim degerlendirilemedi (egitim satiri < 100 ya da bos test)")
    return folds, pd.concat(rows), last, bests


def forward_calibrate(oof: pd.DataFrame, kinds: list[str]) -> None:
    """Platt ve esik ILERI YONLU uydurulur: k. dilimin satirlari icin yalniz, etiketi/cikisi k. dilimin
    baslangicindan ONCE bilinen onceki dilim satirlari kullanilir (gate'in kendi test satirlarina uydurma yok).
    Ilk dilim: Platt = ozdeslik (a=1,b=0), esik = BURN_IN_THRESHOLD (onceden yazili sabit). Onceki veri var ama
    uygun esik yoksa esik NaN (o dilimde islem alinmaz). Sonuc oof'a yazilir: p_<m> (ileri
    yonlu kalibre olasilik) ve th_<m> (satira ozgu ileri yonlu esik)."""
    oof["known_ts"] = oof[["label_end_ts", "exit_ts"]].max(axis=1)
    for m in kinds:
        z = oof[f"z_{m}"].to_numpy()
        p = np.full(len(oof), np.nan)
        th = np.full(len(oof), np.nan)
        for k in sorted(oof["fold"].unique()):
            cur = (oof["fold"] == k).to_numpy()
            t0 = oof.loc[cur, "test_start"].iloc[0]
            prior = (oof["fold"] < k).to_numpy() & (oof["known_ts"] < t0).to_numpy()
            if prior.sum() == 0:
                a, b, th[cur] = 1.0, 0.0, BURN_IN_THRESHOLD
                p[cur] = 1.0 / (1.0 + np.exp(-(a * z[cur] + b)))
                continue
            c = models.fit_platt(z[prior], oof["label"].to_numpy()[prior], nonneg_slope=config.PLATT_NONNEG_SLOPE)
            p[cur] = 1.0 / (1.0 + np.exp(-(c["a"] * z[cur] + c["b"])))
            pt = prior & oof["taken"].to_numpy()
            thr, _ = select_threshold(p[pt], oof["net_r"].to_numpy()[pt]) if pt.any() else (None, None)
            th[cur] = np.nan if thr is None else thr
        oof[f"p_{m}"], oof[f"th_{m}"] = p, th


def run(t: pd.DataFrame, out_dir: str | Path, *, n_trials: int, synthetic: bool = False, n_boot: int = 2000,
        now: datetime | None = None, corpus_sha256: str | None = None, health_strict: bool | None = None,
        expected_daily_sr: float | None = None, expected_ic: float | None = None) -> dict:
    """n_trials ZORUNLU (varsayilan yok): kayitli tarif sayisi x 2 model (registry.n_trials_from_registry).
    synthetic=False (gercek kosu): lightgbm yuklenemezse LightGBMRequired (lojistige dusmez).
    ML-G1: ozellik sagligi (bos/sabit/kopya) gercek kosuda REDDEDER (health_strict varsayilan = not synthetic), sentetikte
    yalniz raporlar; guc on hesabi egitimden once yazdirilir ve rapora/gate_result.json'a yazilir. Kapi mantigi degismez."""
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    t = validate_candidates(t)
    assert_pre_holdout(t["ts"], "egitim girdisi")
    t = t[t["label"].notna()].reset_index(drop=True)
    names = feature_columns(t)
    if not synthetic and lightgbm_version() is None:
        raise LightGBMRequired("lightgbm yuklenemedi, gercek kosu basarisiz")
    health = prechecks.feature_health(t, names)
    if (not synthetic if health_strict is None else health_strict):
        prechecks.assert_feature_health(health)
    power = prechecks.corpus_power(t, n_trials, expected_daily_sr=expected_daily_sr, expected_ic=expected_ic)
    for ln in prechecks.power_lines(power):
        print(ln, flush=True)
    X, y = t[names].to_numpy(float), t["label"].to_numpy(float)
    folds, oof, last, bests = run_oof(t, names, require_lightgbm=not synthetic)
    kinds = [m for m in MODELS if f"z_{m}" in oof.columns]

    # kapi icin ILERI YONLU Platt + esik (A1); paket icin tum-OOF Platt asagida ayrica uydurulur
    forward_calibrate(oof, kinds)
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

    # paket kalibrasyonu + esigi: tum OOF'a uydurulur (uretim artefakti; kapi bunu SKORLAMAZ)
    z_sel = oof[f"z_{selected}"].to_numpy()
    cal_pkg = models.fit_platt(z_sel, oof["label"].to_numpy(), nonneg_slope=config.PLATT_NONNEG_SLOPE)
    p_pkg = 1.0 / (1.0 + np.exp(-(cal_pkg["a"] * z_sel + cal_pkg["b"])))
    tk = oof["taken"].to_numpy()
    th, _ = select_threshold(p_pkg[tk], oof["net_r"].to_numpy()[tk])

    # nihai model: tum egitim penceresi (kilitli donem yok)
    w_all = models.sample_weights(t, t["ts"].max())
    if selected == "lgbm":
        booster, _ = models.fit_lgbm(X, y, w_all, num_rounds=max(10, int(np.median(bests))))
        model = models.lgbm_dump(booster)
    else:
        booster, model = None, models.fit_logistic(X, y, w_all)
    created = now or datetime.now(timezone.utc)
    extra = {"selected_reason": reason, "threshold_feasible": th is not None, "synthetic": synthetic,
             "n_trials": n_trials, "gate_passed": None}
    args = (model, cal_pkg, th, names, X, t["ts"].min(), t["ts"].max(), data_hash(t))
    pkg0 = build_package(*args, created_at=created, extra=extra)
    # gidis-donus (JSON) -- henuz kapi sonucu yok, bu yuzden require_gate=False
    pkg = load_package(json.loads(json.dumps(pkg0, allow_nan=False)), now=now, require_gate=False)

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
    passed = bool(res.passed and th is not None)               # esiksiz paket asla kabul edilmez (A3)
    res.passed, res.threshold = passed, th
    extra["gate_passed"] = passed
    pkg_path = save_package(build_package(*args, created_at=created, extra=extra), out_dir / "model_candidate.json")
    pkg = load_package(pkg_path, now=now, require_gate=False)  # hash'ler tutuyor mu
    diag = diagnostics.compute(oof, f"p_{selected}")
    md = render_report(res, meta=pkg["meta"], folds=folds, peak_rss_mb=peak_rss_mb(), synthetic=synthetic,
                       selected_reason=reason, n_trials=n_trials, lightgbm_version=lightgbm_version(),
                       corpus_sha256=corpus_sha256, diagnostics=diag, health=health, power=power)
    (out_dir / "gate_report.md").write_text(md, encoding="utf-8")
    summary = {"passed": res.passed, "model": selected, "threshold": th, "parity_max_abs_diff": parity,
               "checks": [{"name": c.name, "ok": c.ok, "value": c.value} for c in res.checks],
               "package": str(pkg_path), "report": str(out_dir / "gate_report.md"), "peak_rss_mb": peak_rss_mb(),
               "n_candidates": int(len(t)), "n_oof": int(len(oof)), "n_trials": n_trials,
               "recipe_id": RECIPE_ID, "lightgbm_version": lightgbm_version(), "corpus_sha256": corpus_sha256,
               "feature_health": health, "power_precheck": power, "diagnostics": diag, "ic_taken": res.metrics["ic"], "ic_all_rows_diagnostic": res.metrics["ic_all_rows"]}
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
    ap.add_argument("--research", action="store_true",
                    help="sunucu DISI arastirma: kaynak limitleri UYGULANMAZ (varsayilan: nice 19, tek cekirdek, 450 MB)")
    ap.add_argument("--limits", action="store_true", help=argparse.SUPPRESS)      # eski bayrak: artik varsayilan
    ap.add_argument("--registry", default=str(DEFAULT_REGISTRY), help="deneme defteri (n_trials = tarif x 2 model)")
    ap.add_argument("--n-trials", type=int, default=None,
                    help="deftere ek olarak ACIK deneme sayisi (defter miktarindan kucuk olamaz)")
    ap.add_argument("--expected-sr", type=float, default=None, help="guc on hesabi: beklenen GUNLUK Sharpe (filtreli seri)")
    ap.add_argument("--expected-ic", type=float, default=None, help="guc on hesabi: beklenen gunluk sira korelasyonu")
    ap.add_argument("--precheck-only", action="store_true",
                    help="yalniz ozellik sagligi + guc on hesabi yazdir; egitim/kapi KOSULMAZ")
    a = ap.parse_args(argv)
    if not a.research:
        apply_limits()
    n_trials = n_trials_from_registry(a.registry)
    if a.n_trials is not None:
        if a.n_trials < n_trials:
            ap.error(f"--n-trials {a.n_trials} < defterden gelen {n_trials}: deneme sayisi kucultulemez")
        n_trials = a.n_trials
    corpus_sha = None
    if a.synthetic:
        from .fixture import build_candidate_table, synthetic_candles
        t = build_candidate_table(synthetic_candles())
    else:
        import hashlib
        from .schema import load_candidates
        t = load_candidates(a.candidates)
        corpus_sha = hashlib.sha256(Path(a.candidates).read_bytes()).hexdigest()
    if a.precheck_only:
        tl = t[t["label"].notna()].reset_index(drop=True)
        h = prechecks.feature_health(tl)
        print(f"Ozellik sagligi: bos={h['all_nan']} sabit={h['constant']} kopya={h['duplicate']} -> {'TEMIZ' if h['ok'] else 'SAGLIKSIZ'}")
        for ln in prechecks.power_lines(prechecks.corpus_power(tl, n_trials, expected_daily_sr=a.expected_sr, expected_ic=a.expected_ic)):
            print(ln)
        return 0 if (h["ok"] or a.synthetic) else 3
    try:
        s = run(t, a.out, synthetic=a.synthetic, n_trials=n_trials, corpus_sha256=corpus_sha,
                expected_daily_sr=a.expected_sr, expected_ic=a.expected_ic)
    except prechecks.FeatureHealthError as e:
        print(f"REDDEDILDI: {e}", file=sys.stderr)
        return 3
    except LightGBMRequired as e:
        print(f"BASARISIZ: {e}", file=sys.stderr)
        return 2
    print(f"{'KABUL' if s['passed'] else 'RED'}: rapor {s['report']} (n_trials={n_trials})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
