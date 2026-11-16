"""ML-0c mentor incelemesi A1-A6 + B: her madde icin duzeltmeden once KALAN, sonra GECEN test."""
import json
import subprocess
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

pytest.importorskip("lightgbm")

from trader_ml import models, pipeline
from trader_ml.config import BAR, BURN_IN_THRESHOLD
from trader_ml.gate import daily_mean, rho_t, run_gate, spearman
from trader_ml.registry import RegistryError, n_trials_from_registry
from trader_ml.schema import SchemaError, validate_candidates

ROOT = Path(__file__).resolve().parents[2]


# ----------------------------------------------------------------------------------------------- A1
def _drift_oof(n=3000, seed=0, skill=False):
    """4 dilim; taban oran zamanla YUKSELIR (0.20 -> 0.45); model BECERISIZ (z gurultu). Eski kod (tum-OOF
    Platt) egitim taban oranini Brier'de yener; ileri yonlu Platt yenemez."""
    rng = np.random.default_rng(seed)
    fold = np.repeat([0, 1, 2, 3], n // 4)
    base = np.array([0.20, 0.30, 0.38, 0.45])[fold]
    lab = (rng.random(len(fold)) < base).astype(float)
    ts = pd.Timestamp("2025-09-01", tz="UTC") + pd.to_timedelta(np.arange(len(fold)) * 2, unit="h")
    z = rng.normal(0, 0.05, len(fold)) + (2.0 * (lab - 0.35) if skill else 0.0)
    df = pd.DataFrame({"ts": ts, "pair": rng.choice(list("ABC"), len(fold)), "fold": fold, "taken": True, "label": lab,
                       "net_r": rng.normal(0, 1, len(fold)), "cost_r": 0.2, "z_m": z})
    df["label_end_ts"] = df["ts"] + 20 * BAR
    df["exit_ts"] = df["ts"] + 10 * BAR
    df["test_start"] = df.groupby("fold")["ts"].transform("min")
    df["base_rate"] = 0.20                                            # egitim taban orani (kaymadan once)
    return df


def test_skillless_model_does_not_beat_base_rate_via_forward_platt():
    oof = _drift_oof()
    # ESKI yontem (tum-OOF Platt) sahte beceri uretir
    c = models.fit_platt(oof["z_m"].to_numpy(), oof["label"].to_numpy())
    p_old = 1 / (1 + np.exp(-(c["a"] * oof["z_m"] + c["b"])))
    assert np.mean((p_old - oof["label"]) ** 2) < np.mean((oof["base_rate"] - oof["label"]) ** 2)
    # YENI: ileri yonlu -> Brier kontrolu KALIR
    pipeline.forward_calibrate(oof, ["m"])
    r = run_gate(oof, ["p_m"], selected="p_m", parity_max_abs_diff=0.0, n_trials=2, n_boot=100)
    assert next(c for c in r.checks if c.name.startswith("2.")).ok is False


def test_forward_calibration_uses_only_prior_known_rows():
    oof = _drift_oof(skill=True)
    pipeline.forward_calibrate(oof, ["m"])
    f0 = oof[oof["fold"] == 0]
    assert np.allclose(f0["p_m"], 1 / (1 + np.exp(-f0["z_m"]))) and (f0["th_m"] == BURN_IN_THRESHOLD).all()
    # 1. dilimin Platt'i yalniz 0. dilimden: 1. dilim etiketlerini bozmak 1. dilim p'sini DEGISTIRMEZ
    o2 = oof.copy()
    o2.loc[o2["fold"] == 1, "label"] = 1.0 - o2.loc[o2["fold"] == 1, "label"]
    pipeline.forward_calibrate(o2, ["m"])
    assert np.allclose(oof.loc[oof["fold"] == 1, "p_m"], o2.loc[o2["fold"] == 1, "p_m"])
    # test baslangicindan sonra bilinen onceki satirlar (label_end_ts) kullanilmaz
    o3 = oof.copy()
    late = (o3["fold"] == 0) & (o3["ts"] > o3.loc[o3["fold"] == 0, "ts"].max() - 5 * BAR)
    o3.loc[late, "label_end_ts"] = o3.loc[o3["fold"] == 1, "test_start"].iloc[0] + 10 * BAR
    o3.loc[late, "label"] = 1.0 - o3.loc[late, "label"]
    pipeline.forward_calibrate(o3, ["m"])
    assert np.allclose(oof.loc[oof["fold"] == 1, "p_m"], o3.loc[o3["fold"] == 1, "p_m"])


# ----------------------------------------------------------------------------------------------- A2
def _good_oof(n=2400, seed=2, folds=(0, 1, 2, 3)):
    rng = np.random.default_rng(seed)
    ts = pd.date_range("2025-09-01", periods=n, freq="7h", tz="UTC")
    s = rng.random(n) < 0.5
    net = np.where(s, 1.2, -0.7) + rng.normal(0, 0.4, n)
    lab = (rng.random(n) < np.where(s, 0.75, 0.10)).astype(float)
    df = pd.DataFrame({"ts": ts, "pair": rng.choice(list("ABCDEF"), n), "fold": np.repeat(list(folds), n // len(folds) + 1)[:n],
                       "taken": True, "label": lab, "net_r": net, "cost_r": 0.2, "base_rate": 0.42})
    df["p_g"] = np.clip(np.where(s, 0.62, 0.20) + rng.normal(0, 0.03, n), 0.01, 0.99)
    return df


def test_gate_fails_unless_exactly_four_folds_and_three_positive():
    ok = run_gate(_good_oof(), ["p_g"], selected="p_g", parity_max_abs_diff=0.0, n_trials=2, n_boot=100)
    assert next(c for c in ok.checks if c.name.startswith("1.")).ok is True
    three = run_gate(_good_oof(folds=(0, 1, 2)), ["p_g"], selected="p_g", parity_max_abs_diff=0.0, n_trials=2, n_boot=100)
    c1 = next(c for c in three.checks if c.name.startswith("1."))
    assert c1.ok is False and not three.passed                       # 3/3 pozitif ama yalniz 3 dilim: KALIR
    bad = _good_oof()
    f2 = bad["fold"] == 2                                            # 4 dilim, yalniz 2'si pozitif
    f3 = bad["fold"] == 3
    bad.loc[f2 | f3, "p_g"] = 1.0 - bad.loc[f2 | f3, "p_g"]
    two = run_gate(bad, ["p_g"], selected="p_g", parity_max_abs_diff=0.0, n_trials=2, n_boot=100)
    assert next(c for c in two.checks if c.name.startswith("1.")).ok is False


def test_run_oof_raises_when_no_fold_evaluable(table):
    t = table[table["ts"] < pd.Timestamp("2025-02-01", tz="UTC")].reset_index(drop=True)
    from trader_ml.schema import feature_columns
    with pytest.raises(Exception):
        pipeline.run_oof(t, feature_columns(t))


# ----------------------------------------------------------------------------------------------- A3
@pytest.fixture(scope="module")
def e2e(table, tmp_path_factory):
    out = tmp_path_factory.mktemp("rf")
    return out, pipeline.run(table, out, synthetic=True, n_boot=200, n_trials=2)


def test_package_meta_carries_gate_flag_and_loader_matches(e2e):
    from trader_ml.package import PackageError, load_package
    out, s = e2e
    pkg = json.loads((out / "model_candidate.json").read_text())
    assert pkg["meta"]["gate_passed"] is s["passed"]
    if s["passed"] and pkg["threshold"] is not None:
        assert load_package(out / "model_candidate.json", check_expiry=False)
    else:
        with pytest.raises(PackageError, match="kapidan gecmedi|esigi yok"):
            load_package(out / "model_candidate.json", check_expiry=False)


def test_thresholdless_package_is_never_marked_passed(table, tmp_path, monkeypatch):
    from trader_ml import gate as gate_mod
    from trader_ml.package import PackageError, load_package
    monkeypatch.setattr(pipeline, "select_threshold", lambda p, r, *a, **k: (None, None))
    s = pipeline.run(table, tmp_path, synthetic=True, n_boot=100, n_trials=2)
    assert s["passed"] is False and s["threshold"] is None
    with pytest.raises(PackageError):
        load_package(tmp_path / "model_candidate.json", check_expiry=False)


# ----------------------------------------------------------------------------------------------- A4
def test_schema_requires_exit_ts_for_taken_rows_and_orders_it(table):
    with pytest.raises(SchemaError, match="eksik"):
        validate_candidates(table.drop(columns=["exit_ts"]))
    bad = table.copy()
    bad.loc[bad.index[bad["taken"]][0], "exit_ts"] = pd.NaT
    with pytest.raises(SchemaError, match="exit_ts"):
        validate_candidates(bad)
    bad = table.copy()
    i = bad.index[bad["taken"]][0]
    bad.loc[i, "exit_ts"] = bad.loc[i, "ts"] - BAR
    with pytest.raises(SchemaError, match="exit_ts"):
        validate_candidates(bad)


# ----------------------------------------------------------------------------------------------- A5
def test_ic_t_stat_does_not_count_same_bar_pairs_as_independent():
    rng = np.random.default_rng(7)
    nb, k = 120, 6                                                   # 120 mum x 6 cift, mum basina ORTAK sok
    ts = np.repeat(pd.date_range("2025-09-01", periods=nb, freq="1D", tz="UTC"), k)
    c = rng.normal(0, 1, nb)
    score = np.repeat(c, k)                                          # ayni mumdaki cift ayni skor/sonuc (tam kumelenme)
    net = np.repeat(0.15 * c + rng.normal(0, 1, nb), k)
    rho_rows = spearman(score, net)
    t_rows = rho_t(rho_rows, nb * k)
    ds, dr = daily_mean(ts, score, net)
    assert len(ds) == nb
    t_daily = rho_t(spearman(ds, dr), len(ds))
    assert t_rows > 2.0 > t_daily and t_daily < t_rows / 2                         # eski: sisirilmis; yeni: kume basina


def test_dsr_uses_daily_series(table):
    from trader_ml.gate import model_metrics
    o = _good_oof()
    o["ts"] = pd.date_range("2025-09-01", periods=len(o), freq="1h", tz="UTC")    # gunde 24 islem
    m = model_metrics(o, "p_g", n_boot=50)
    assert m["n_days"] <= len(o) // 24 + 2 and m["n_days"] < m["n_filtered"] / 5


# ----------------------------------------------------------------------------------------------- A6
def test_n_trials_is_required_and_registry_derived():
    import inspect
    sig = inspect.signature(pipeline.run).parameters["n_trials"]
    assert sig.default is inspect.Parameter.empty and sig.kind is inspect.Parameter.KEYWORD_ONLY
    assert n_trials_from_registry() == 2                              # 1 kayitli tarif x 2 model
    with pytest.raises(RegistryError):
        n_trials_from_registry(ROOT / "research" / "yok.csv")


def test_registry_counts_recipes_times_two_and_rejects_unknown_recipe(tmp_path):
    f = tmp_path / "r.csv"
    f.write_text("recipe_id,registered_at,note\nml0c-baseline-v1,2026-11-16,a\nml0c-x,2026-11-20,b\n")
    assert n_trials_from_registry(f) == 4
    f.write_text("recipe_id,registered_at,note\nother,2026-11-16,a\n")
    with pytest.raises(RegistryError, match="kayitli degil"):
        n_trials_from_registry(f)


# ----------------------------------------------------------------------------------------------- B
def test_early_stopping_split_is_purged():
    rng = np.random.default_rng(0)
    n = 600
    X = rng.normal(size=(n, 3))
    y = (rng.random(n) < 0.4).astype(float)
    w = np.ones(n)
    ts = pd.date_range("2025-01-01", periods=n, freq="1h", tz="UTC").to_numpy("datetime64[ns]")
    ends = ts + np.timedelta64(72, "h")
    seen = {}
    import lightgbm as lgb
    orig = lgb.Dataset

    def spy(data, *a, **k):
        seen.setdefault("n", []).append(len(data))
        return orig(data, *a, **k)
    lgb.Dataset = spy
    try:
        models.fit_lgbm(X, y, w)
        models.fit_lgbm(X, y, w, ts=ts, label_end=ends)
    finally:
        lgb.Dataset = orig
    assert seen["n"][2] < seen["n"][0] - 90                           # ~72+24 satir arindirildi


def test_thread_env_preset_before_numpy_and_research_opt_out():
    code = ("import sys; sys.path.insert(0, {src!r}); from trader_ml._threads import preset_threads; "
            "r = preset_threads({argv!r}); import os; print(r, os.environ.get('OMP_NUM_THREADS'), 'numpy' in sys.modules)")
    src = str(ROOT / "src")
    a = subprocess.run([sys.executable, "-c", code.format(src=src, argv=["--synthetic"])], capture_output=True, text=True)
    assert a.stdout.split() == ["True", "1", "False"], a.stderr
    b = subprocess.run([sys.executable, "-c", code.format(src=src, argv=["--research"])], capture_output=True, text=True,
                       env={"PATH": "", "OMP_NUM_THREADS": ""})
    assert b.stdout.split()[0] == "False"
