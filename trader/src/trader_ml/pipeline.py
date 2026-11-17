"""Uctan uca egitim hatti + kapi (ML-0c): aday tablosu -> purged walk-forward OOF -> model secimi ->
nihai model -> JSON paketi -> kapi -> Turkce rapor.

Kullanim:  python -m trader_ml.pipeline --synthetic --out DIR
           python -m trader_ml.pipeline --candidates 19b_candidates.parquet --out DIR [--limits]
"""
from __future__ import annotations

import argparse
import dataclasses
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

from . import config, diagnostics, models, prechecks, recipes
from .config import BURN_IN_THRESHOLD, GATE
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


class CalibrationClamped(RuntimeError):
    """Paket duzeyi Platt egimi kisitlandi (a<0 -> a=0): sinyalsiz model, paket URETILMEZ (mentor G2-4).
    run() once gate_report.md + gate_result.json (passed=false, neden + OOF olculeri) yazar, sonra bunu firlatir;
    `summary` yazilan sonuc sozlugudur."""
    summary: dict | None = None


# CLI cikis kodlari: 0 tamam, 2 lightgbm yok, 3 ozellik sagligi, 4 CalibrationClamped (RED), 5 sha256 uyusmazligi,
# 6 manifest/katman butunlugu, 7 sira korumasi (r03 icin r02 sonucu), 8 guc on hesabi vetosu (kosulmadi)
EXIT_SHA, EXIT_MANIFEST, EXIT_ORDER, EXIT_POWER = 5, 6, 7, 8


class LightGBMRequired(RuntimeError):
    """Gercek (sentetik olmayan) kosuda lightgbm yuklenemedi: kosu BASARISIZ sayilir (sessizce lojistige dusmez)."""


lightgbm_version = models.lightgbm_version


def _resolve_recipe(recipe, weight_scheme=None) -> recipes.Recipe:
    """None = r01 (config'in o anki degerleri). weight_scheme (eski kwarg) yalniz None tarifte gecerlidir."""
    if recipe is None:
        r = recipes.default_recipe()
        if weight_scheme is not None:
            r = dataclasses.replace(r, weight_scheme=weight_scheme)
        return r
    return recipe


def _fold_models(X, y, w, tr, ts=None, ends=None, *, require_lightgbm: bool = True, recipe: recipes.Recipe | None = None):
    recipe = _resolve_recipe(recipe)
    out = {"logistic": models.fit_logistic(X[tr], y[tr], w[tr], **recipe.logit_params)}
    try:
        booster, best = models.fit_lgbm(X[tr], y[tr], w[tr], ts=None if ts is None else ts[tr],
                                        label_end=None if ends is None else ends[tr], params=recipe.lgbm_params)
        out["lgbm"] = (booster, best)
    except ImportError as e:
        if require_lightgbm:                              # on kayit: gercek kosuda sessiz dusus YOK
            raise LightGBMRequired(f"lightgbm yuklenemedi, gercek kosu basarisiz: {e}") from e
        # yalniz sentetik/test kipi: lightgbm yok -> yalniz lojistik
    return out


def run_oof(t: pd.DataFrame, names: list[str], *, require_lightgbm: bool = True, weight_scheme: str | None = None,
            recipe: recipes.Recipe | None = None):
    recipe = _resolve_recipe(recipe, weight_scheme)
    X, y = t[names].to_numpy(float), t["label"].to_numpy(float)
    folds = make_folds(t, **recipe.wf)
    ts_arr, ends_arr = t["ts"].to_numpy("datetime64[ns]"), t["label_end_ts"].to_numpy("datetime64[ns]")
    rows, last, bests = [], None, []
    for f in folds:
        tr, te = f["train_rows"], f["test_rows"]
        if len(tr) < 100 or len(te) == 0:
            continue
        w = models.training_weights(t.iloc[tr], recipe.weight_scheme)   # dilimin EGITIM satirlari (arindirma sonrasi)
        fm = _fold_models(X, y, w, tr, ts_arr, ends_arr, require_lightgbm=require_lightgbm, recipe=recipe)
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


def forward_calibrate(oof: pd.DataFrame, kinds: list[str], recipe: recipes.Recipe | None = None) -> dict[str, int]:
    """Platt ve esik ILERI YONLU uydurulur: k. dilimin satirlari icin yalniz, etiketi/cikisi k. dilimin
    baslangicindan ONCE bilinen onceki dilim satirlari kullanilir (gate'in kendi test satirlarina uydurma yok).
    Ilk dilim: Platt = ozdeslik (a=1,b=0), esik = BURN_IN_THRESHOLD (onceden yazili sabit). Onceki veri var ama
    uygun esik yoksa esik NaN (o dilimde islem alinmaz). Sonuc oof'a yazilir: p_<m> (ileri
    yonlu kalibre olasilik) ve th_<m> (satira ozgu ileri yonlu esik)."""
    recipe = _resolve_recipe(recipe)
    oof["known_ts"] = oof[["label_end_ts", "exit_ts"]].max(axis=1)
    n_clamped = {m: 0 for m in kinds}
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
            c, clamped = models.fit_platt_info(z[prior], oof["label"].to_numpy()[prior],
                                               nonneg_slope=recipe.platt_nonneg)
            n_clamped[m] += int(clamped)
            p[cur] = 1.0 / (1.0 + np.exp(-(c["a"] * z[cur] + c["b"])))
            pt = prior & oof["taken"].to_numpy()
            thr, _ = select_threshold(p[pt], oof["net_r"].to_numpy()[pt]) if pt.any() else (None, None)
            th[cur] = np.nan if thr is None else thr
        oof[f"p_{m}"], oof[f"th_{m}"] = p, th
    return n_clamped


def run(t: pd.DataFrame, out_dir: str | Path, *, n_trials: int, synthetic: bool = False, n_boot: int = 2000,
        now: datetime | None = None, corpus_sha256: str | None = None, health_strict: bool | None = None,
        expected_daily_sr: float | None = None, expected_ic: float | None = None,
        weight_scheme: str | None = None, recipe: recipes.Recipe | None = None,
        overlay_sha256: str | None = None, extra_meta: dict | None = None) -> dict:
    """n_trials ZORUNLU (varsayilan yok): kayitli tarif sayisi x 2 model (registry.n_trials_from_registry).
    synthetic=False (gercek kosu): lightgbm yuklenemezse LightGBMRequired (lojistige dusmez).
    ML-G1: ozellik sagligi (bos/sabit/kopya) gercek kosuda REDDEDER (health_strict varsayilan = not synthetic), sentetikte
    yalniz raporlar; guc on hesabi egitimden once yazdirilir ve rapora/gate_result.json'a yazilir. Kapi mantigi degismez."""
    recipe = _resolve_recipe(recipe, weight_scheme)
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    t = validate_candidates(t)
    assert_pre_holdout(t["ts"], "egitim girdisi")
    t = t[t["label"].notna()].reset_index(drop=True)
    names = list(recipe.features) if recipe.features else feature_columns(t)     # r01: tablodaki tum f_* (sirali)
    if not synthetic and lightgbm_version() is None:
        raise LightGBMRequired("lightgbm yuklenemedi, gercek kosu basarisiz")
    health = prechecks.feature_health(t, names, recipe=recipe)
    if (not synthetic if health_strict is None else health_strict):
        prechecks.assert_feature_health(health)
    power = prechecks.corpus_power(t, n_trials, recipe=recipe, expected_daily_sr=expected_daily_sr, expected_ic=expected_ic)
    for ln in prechecks.power_lines(power):
        print(ln, flush=True)
    X, y = t[names].to_numpy(float), t["label"].to_numpy(float)
    folds, oof, last, bests = run_oof(t, names, require_lightgbm=not synthetic, recipe=recipe)
    kinds = [m for m in MODELS if f"z_{m}" in oof.columns]

    # kapi icin ILERI YONLU Platt + esik (A1); paket icin tum-OOF Platt asagida ayrica uydurulur
    n_clamped = forward_calibrate(oof, kinds, recipe)
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
    cal_pkg, pkg_clamped = models.fit_platt_info(z_sel, oof["label"].to_numpy(), nonneg_slope=recipe.platt_nonneg)
    if pkg_clamped:
        err = CalibrationClamped("paket kalibrasyonunda Platt egimi a<0 kisitlandi (sinyalsiz model): paket uretilmez")
        err.summary = _write_clamped(out_dir, oof, kinds, pm, selected, reason, recipe, n_trials, n_clamped, health, power,
                                     len(t), corpus_sha256, overlay_sha256, folds, synthetic)
        raise err
    p_pkg = 1.0 / (1.0 + np.exp(-(cal_pkg["a"] * z_sel + cal_pkg["b"])))
    tk = oof["taken"].to_numpy()
    th, _ = select_threshold(p_pkg[tk], oof["net_r"].to_numpy()[tk])

    # nihai model: tum egitim penceresi (kilitli donem yok)
    w_all = models.training_weights(t, recipe.weight_scheme)
    if selected == "lgbm":
        booster, _ = models.fit_lgbm(X, y, w_all, num_rounds=max(10, int(np.median(bests))), params=recipe.lgbm_params)
        model = models.lgbm_dump(booster)
    else:
        booster, model = None, models.fit_logistic(X, y, w_all, **recipe.logit_params)
    created = now or datetime.now(timezone.utc)
    extra = {"selected_reason": reason, "threshold_feasible": th is not None, "synthetic": synthetic,
             "n_trials": n_trials, "gate_passed": None}
    args = (model, cal_pkg, th, names, X, t["ts"].min(), t["ts"].max(), data_hash(t))
    pkg0 = build_package(*args, version=recipe.id, created_at=created, extra=extra)
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
    pkg_path = save_package(build_package(*args, version=recipe.id, created_at=created, extra=extra), out_dir / "model_candidate.json")
    pkg = load_package(pkg_path, now=now, require_gate=False)  # hash'ler tutuyor mu
    diag = diagnostics.compute(oof, f"p_{selected}")
    md = render_report(res, meta=pkg["meta"], folds=folds, peak_rss_mb=peak_rss_mb(), synthetic=synthetic,
                       selected_reason=reason, n_trials=n_trials, lightgbm_version=lightgbm_version(),
                       corpus_sha256=corpus_sha256, overlay_sha256=overlay_sha256, diagnostics=diag, health=health, power=power,
                       calibration={"nonneg_slope": recipe.platt_nonneg, "clamped_folds": n_clamped,
                                    "n_folds": int(oof["fold"].nunique()), "weight_scheme": recipe.weight_scheme})
    (out_dir / "gate_report.md").write_text(md, encoding="utf-8")
    summary = {"passed": res.passed, "model": selected, "threshold": th, "parity_max_abs_diff": parity,
               "checks": [{"name": c.name, "ok": c.ok, "value": c.value} for c in res.checks],
               "package": str(pkg_path), "report": str(out_dir / "gate_report.md"), "peak_rss_mb": peak_rss_mb(),
               "n_candidates": int(len(t)), "n_oof": int(len(oof)), "n_trials": n_trials,
               "recipe_id": recipe.id, "lightgbm_version": lightgbm_version(), "corpus_sha256": corpus_sha256,
               "overlay_sha256": overlay_sha256, "run_table_info": extra_meta,
               "feature_health": health, "power_precheck": power, "diagnostics": diag, "platt_clamped_folds": n_clamped, "weight_scheme": recipe.weight_scheme, "ic_taken": res.metrics["ic"], "ic_all_rows_diagnostic": res.metrics["ic_all_rows"]}
    (out_dir / "gate_result.json").write_text(json.dumps(summary, indent=1, default=str), encoding="utf-8")
    oof.to_parquet(out_dir / "oof_predictions.parquet")
    return summary


def _write_clamped(out_dir, oof, kinds, pm, selected, reason, recipe, n_trials, n_clamped, health, power, n_candidates,
                   corpus_sha256, overlay_sha256, folds, synthetic) -> dict:
    """Paket kalibrasyonu kisitlandi: paket YOK; kapi KOSULMADI -> sonuc RED (passed=false), neden + OOF olculeri yazilir."""
    out_dir = Path(out_dir)
    reason_txt = "CalibrationClamped: paket duzeyi Platt egimi a<0 kisitlandi (sinyalsiz model); paket uretilmedi (cikis kodu 4)"
    L = ["# ML terfi kapısı raporu — RED", "",
         f"> **Neden:** {reason_txt}.", "",
         f"- Tarif: `{recipe.id}` | seçilen model: **{selected}** ({reason}) | deneme sayısı (n_trials): {n_trials}",
         f"- lightgbm sürümü: {lightgbm_version() or 'YOK'}",
         f"- Korpus sha256: `{corpus_sha256 or 'yok'}` | katman sha256: `{overlay_sha256 or 'yok'}`",
         f"- Eğimi kısıtlanan ileri yönlü dilim sayısı: " + (", ".join(f"{k}={v}/{int(oof['fold'].nunique())}" for k, v in n_clamped.items()) or "-"),
         "", "## OOF ölçüleri (yalnız bilgi; kapı koşulmadı)", "",
         "| Model | Alınan oran | Filtreli net R | Filtresiz net R | Fark |", "|---|---|---|---|---|"]
    for k, m in pm.items():
        L.append(f"| {k} | {m['taken_frac']:.1%} | {_fmt(m['mean_filtered'])} | {_fmt(m['mean_all'])} | {_fmt(m['delta'])} |")
    L += ["", "## Test dilimleri", "", "| Dilim | Eğitim satırı | Test satırı | Test başlangıcı | Test sonu |", "|---|---|---|---|---|"]
    for f in folds:
        L.append(f"| {f['fold']} | {len(f['train_rows'])} | {len(f['test_rows'])} | {f['test_start']:%Y-%m-%d} | {f['test_end']:%Y-%m-%d} |")
    L += ["", "RED geçerli bir sonuçtur, kayda geçer; ML `off`'ta kalır.", ""]
    (out_dir / "gate_report.md").write_text("\n".join(L), encoding="utf-8")
    summary = {"passed": False, "reason": reason_txt, "model": selected, "threshold": None, "package": None,
               "report": str(out_dir / "gate_report.md"), "checks": [], "n_candidates": int(n_candidates), "n_oof": int(len(oof)),
               "n_trials": n_trials, "recipe_id": recipe.id, "lightgbm_version": lightgbm_version(),
               "corpus_sha256": corpus_sha256, "overlay_sha256": overlay_sha256, "feature_health": health, "power_precheck": power,
               "platt_clamped_folds": n_clamped, "weight_scheme": recipe.weight_scheme, "synthetic": synthetic,
               "oof_metrics": {k: {kk: vv for kk, vv in m.items()} for k, m in pm.items()}}
    (out_dir / "gate_result.json").write_text(json.dumps(summary, indent=1, default=str), encoding="utf-8")
    oof.to_parquet(out_dir / "oof_predictions.parquet")
    return summary


def _fmt(v):
    return f"{v:+.4f}" if isinstance(v, float) and np.isfinite(v) else "-"


ORDER_GUARDED = {recipes.R03_ID: recipes.R02_ID}     # r03 yalniz r02 RED sonucundan sonra (on kayit 8, sira 3)
POWER_VETO_RHO = 0.08                                # on kayit 8: gereken gunluk IC rho > 0,08 -> tarif kosulmaz


def check_order_guard(recipe: recipes.Recipe, prior_result: str | Path | None) -> str | None:
    """Hata metni (kosu reddedilir) ya da None. r03: --prior-result r02 gate_result.json (recipe_id r02, passed == false)."""
    need = ORDER_GUARDED.get(recipe.id)
    if need is None:
        return None
    if not prior_result:
        return f"{recipe.id} icin --prior-result (r02 gate_result.json) zorunlu: yalniz {need} RED sonrasi kosulur"
    p = Path(prior_result)
    if not p.exists():
        return f"onceki sonuc dosyasi yok: {p}"
    try:
        d = json.loads(p.read_text(encoding="utf-8"))
    except (OSError, ValueError) as e:
        return f"onceki sonuc okunamadi: {e}"
    if d.get("recipe_id") != need:
        return f"onceki sonucun tarifi {d.get('recipe_id')!r}, beklenen {need!r}"
    if d.get("passed") is not False:
        return f"{need} sonucu passed={d.get('passed')!r}; {recipe.id} yalniz {need} KABUL DEGILSE kosulur"
    return None


def _load_v2_inputs(a, recipe, ap):
    """Derlem v2 + katman: sha256 beklentileri, manifest (on kayit 2.1) ve katman butunlugu dogrulanir; kosu tablosu kurulur.
    Doner (tablo, corpus_sha, overlay_sha, info) ya da (None, None, None, cikis_kodu)."""
    from . import corpus_v2
    for flag in ("corpus", "overlay", "manifest"):
        if not getattr(a, flag):
            ap.error(f"--recipe {recipe.id} icin --{flag} zorunlu")
    corpus_sha, overlay_sha = corpus_v2.sha256_path(a.corpus), corpus_v2.sha256_path(a.overlay)
    for name, got, want in (("corpus", corpus_sha, a.expect_corpus_sha256), ("overlay", overlay_sha, a.expect_overlay_sha256)):
        if want is None and not a.precheck_only:
            print(f"REDDEDILDI: gercek kosu --expect-{name}-sha256 ister (dondurma kaydi on kayit 10)", file=sys.stderr)
            return None, None, None, EXIT_SHA
        if want is not None and want.strip().lower() != got:
            print(f"REDDEDILDI: {name} sha256 uyusmuyor: dosya {got} beklenen {want}", file=sys.stderr)
            return None, None, None, EXIT_SHA
    errs, notes = corpus_v2.verify_corpus_manifest(corpus_v2.load_manifest(a.manifest), a.corpus)
    ov_man = Path(a.overlay_manifest) if a.overlay_manifest else Path(a.overlay).with_suffix(".manifest.json")
    if ov_man.exists():
        errs += corpus_v2.verify_overlay_manifest(corpus_v2.load_manifest(ov_man), a.overlay)
    elif not a.precheck_only:
        errs.append(f"katman manifesti yok: {ov_man}")
    for n in notes:
        print("NOT:", n)
    if errs:
        print("REDDEDILDI: manifest/katman dogrulamasi basarisiz:\n  " + "\n  ".join(errs), file=sys.stderr)
        return None, None, None, EXIT_MANIFEST
    try:
        t, info = corpus_v2.load_run_table(a.corpus, a.overlay, recipe)
    except corpus_v2.CorpusError as e:
        print(f"REDDEDILDI: {e}", file=sys.stderr)
        return None, None, None, EXIT_MANIFEST
    if info["overlay_unmatched_entered"] > 0:
        print(f"REDDEDILDI: derlemde karsiligi olmayan alinmis islem: {info['overlay_unmatched_entered']} (0 olmali)", file=sys.stderr)
        return None, None, None, EXIT_MANIFEST
    print("Kosu tablosu:", json.dumps(info), flush=True)
    return t, corpus_sha, overlay_sha, info


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="ML-0c egitim hatti + terfi kapisi")
    g = ap.add_mutually_exclusive_group(required=False)
    g.add_argument("--candidates", help="19b ciktisi (parquet/csv); yalniz r01")
    g.add_argument("--synthetic", action="store_true", help="sentetik fixture ile uctan uca; yalniz r01")
    ap.add_argument("--recipe", default=config.RECIPE_ID, help=f"tarif kimligi ({', '.join(sorted(recipes.RECIPES))})")
    ap.add_argument("--corpus", help="derlem v2 parquet (r02/r03)")
    ap.add_argument("--overlay", help="alinan-islem katmani parquet (r02/r03)")
    ap.add_argument("--manifest", help="derlem v2 manifesti (on kayit 2.1 alanlari dogrulanir)")
    ap.add_argument("--overlay-manifest", default=None, help="katman manifesti (varsayilan: <overlay>.manifest.json)")
    ap.add_argument("--expect-corpus-sha256", default=None, help="dondurulmus derlem sha256 (on kayit 10); uyusmazsa RED cikis 5")
    ap.add_argument("--expect-overlay-sha256", default=None, help="dondurulmus katman sha256; uyusmazsa cikis 5")
    ap.add_argument("--prior-result", default=None, help="r03 icin: r02 gate_result.json (passed=false olmali)")
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
    try:
        recipe = recipes.get(a.recipe)
    except KeyError as e:
        ap.error(str(e))
    v2 = bool(recipe.features)                         # r02/r03: derlem v2 + katman; r01: aday tablosu
    if v2 and (a.candidates or a.synthetic):
        ap.error(f"--recipe {recipe.id} derlem v2 ister (--corpus/--overlay/--manifest); --candidates/--synthetic yalniz r01")
    if not v2 and not (a.candidates or a.synthetic):
        ap.error("--candidates ya da --synthetic gerekli (r01)")
    msg = check_order_guard(recipe, a.prior_result)
    if msg:
        print(f"REDDEDILDI: sira korumasi: {msg}", file=sys.stderr)
        return EXIT_ORDER
    if not a.research:
        apply_limits()
    n_trials = n_trials_from_registry(a.registry, recipe_id=recipe.id)
    if a.n_trials is not None:
        if a.n_trials < n_trials:
            ap.error(f"--n-trials {a.n_trials} < defterden gelen {n_trials}: deneme sayisi kucultulemez")
        n_trials = a.n_trials
    corpus_sha = overlay_sha = info = None
    if v2:
        t, corpus_sha, overlay_sha, info = _load_v2_inputs(a, recipe, ap)
        if t is None:
            return info
    elif a.synthetic:
        from .fixture import build_candidate_table, synthetic_candles
        t = build_candidate_table(synthetic_candles())
    else:
        import hashlib
        from .schema import load_candidates
        t = load_candidates(a.candidates)
        corpus_sha = hashlib.sha256(Path(a.candidates).read_bytes()).hexdigest()
    if a.precheck_only:
        tl = t[t["label"].notna()].reset_index(drop=True)
        h = prechecks.feature_health(tl, recipe=recipe)
        print(f"Ozellik sagligi: bos={h['all_nan']} sabit={h['constant']} kopya={h['duplicate']} -> {'TEMIZ' if h['ok'] else 'SAGLIKSIZ'}")
        power = prechecks.corpus_power(tl, n_trials, recipe=recipe, expected_daily_sr=a.expected_sr, expected_ic=a.expected_ic)
        for ln in prechecks.power_lines(power):
            print(ln)
        print(f"Gereken IC rho = {power['required_ic_rho']:.4f} (IC gun sayisi {power['n_days_ic']}); "
              f"DSR icin gereken t = {power['required_t_dsr']:.2f}")
        veto = v2 and power["required_ic_rho"] > POWER_VETO_RHO
        if veto:
            print(f"GUC YETERSIZ (veto): gereken rho {power['required_ic_rho']:.4f} > {POWER_VETO_RHO}; tarif kosulmaz")
        return 0 if ((h["ok"] or a.synthetic) and not veto) else (3 if not h["ok"] else EXIT_POWER)
    if v2:
        power = prechecks.corpus_power(t[t["label"].notna()], n_trials, recipe=recipe)
        if power["required_ic_rho"] > POWER_VETO_RHO:
            out = Path(a.out)
            out.mkdir(parents=True, exist_ok=True)
            (out / "gate_report.md").write_text(
                f"# ML terfi kapısı raporu — KOŞULMADI (güç yetersiz)\n\nTarif `{recipe.id}`: gereken günlük sıra korelasyonu "
                f"{power['required_ic_rho']:.4f} > {POWER_VETO_RHO} (ön kayıt 8). Sonuç değildir; `gate_result.json` yazılmadı.\n", encoding="utf-8")
            print(f"REDDEDILDI: guc yetersiz (rho {power['required_ic_rho']:.4f} > {POWER_VETO_RHO})", file=sys.stderr)
            return EXIT_POWER
    try:
        s = run(t, a.out, synthetic=a.synthetic, n_trials=n_trials, corpus_sha256=corpus_sha, overlay_sha256=overlay_sha,
                expected_daily_sr=a.expected_sr, expected_ic=a.expected_ic, recipe=recipe, extra_meta=info)
    except prechecks.FeatureHealthError as e:
        print(f"REDDEDILDI: {e}", file=sys.stderr)
        return 3
    except CalibrationClamped as e:
        print(f"REDDEDILDI (RED): {e}", file=sys.stderr)
        return 4
    except LightGBMRequired as e:
        print(f"BASARISIZ: {e}", file=sys.stderr)
        return 2
    print(f"{'KABUL' if s['passed'] else 'RED'}: rapor {s['report']} (n_trials={n_trials})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
