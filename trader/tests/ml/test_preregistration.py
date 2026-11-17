"""On kayit (17 Kasim ML 19b/19c): IC bagleyici evreni = alinan satirlar; tum-satir IC tani; gercek kosuda lightgbm zorunlu;
deneme defteri n_trials = 4."""
import builtins
import csv
import sys

import numpy as np
import pandas as pd
import pytest

from trader_ml import config, pipeline
from trader_ml.gate import run_gate
from trader_ml.registry import DEFAULT_REGISTRY, n_trials_from_registry


def _oof(n=1200, seed=0, taken_skill=True):
    """Alinan satirlarda puan ~ net R iliskili (ya da degil); alinmayanlarda tersi: iki evren zit isaretli IC verir."""
    rng = np.random.default_rng(seed)
    ts = pd.date_range("2025-09-01", periods=n, freq="5h", tz="UTC")
    taken = rng.random(n) < 0.5
    net = rng.normal(0, 1, n)
    sign = np.where(taken, 1.0 if taken_skill else -1.0, -1.0 if taken_skill else 1.0)
    p = np.clip(0.5 + 0.12 * sign * np.tanh(net) + rng.normal(0, 0.02, n), 0.01, 0.99)
    lab = (rng.random(n) < p).astype(float)
    return pd.DataFrame({"ts": ts, "pair": rng.choice(list("ABC"), n), "fold": np.repeat([0, 1, 2, 3], n // 4),
                         "taken": taken, "label": lab, "net_r": net, "cost_r": 0.2, "base_rate": 0.45, "p_m": p})


def _ic(r):
    return next(c for c in r.checks if c.name.startswith("1."))


def test_ic_binding_universe_is_taken_rows_only():
    good = run_gate(_oof(taken_skill=True), ["p_m"], selected="p_m", parity_max_abs_diff=0.0, n_trials=4, n_boot=100)
    assert _ic(good).ok is True and good.metrics["ic"]["universe"] == "taken"
    assert good.metrics["ic"]["n_rows"] < good.metrics["ic_all_rows"]["n_rows"]
    # alinanlarda IC negatif, alinmayanlarda pozitif -> bagleyici evren alinanlar oldugundan KALIR
    bad = run_gate(_oof(taken_skill=False), ["p_m"], selected="p_m", parity_max_abs_diff=0.0, n_trials=4, n_boot=100)
    assert _ic(bad).ok is False and bad.metrics["ic"]["rho"] < 0


def test_all_rows_ic_is_diagnostic_and_cannot_flip_pass_fail():
    base = _oof(taken_skill=True)
    a = run_gate(base, ["p_m"], selected="p_m", parity_max_abs_diff=0.0, n_trials=4, n_boot=100)
    # alinmayan satirlari tamamen bozmak (tum-satir IC'yi cokertmek) IC adiminin sonucunu degistirmez
    b2 = base.copy()
    nt = ~b2["taken"]
    b2.loc[nt, "net_r"] = -b2.loc[nt, "net_r"] * 3
    b = run_gate(b2, ["p_m"], selected="p_m", parity_max_abs_diff=0.0, n_trials=4, n_boot=100)
    assert a.metrics["ic_all_rows"]["rho"] != pytest.approx(b.metrics["ic_all_rows"]["rho"])
    assert _ic(a).ok == _ic(b).ok is True
    assert a.metrics["ic"]["rho"] == pytest.approx(b.metrics["ic"]["rho"])
    # tersi: tum-satir IC cok iyi, alinanlar kotu -> yine KALDI
    c = run_gate(_oof(taken_skill=False), ["p_m"], selected="p_m", parity_max_abs_diff=0.0, n_trials=4, n_boot=100)
    assert c.metrics["ic_all_rows"]["rho"] is not None and _ic(c).ok is False


def test_real_mode_hard_fails_without_lightgbm(monkeypatch, table, tmp_path):
    real_import = builtins.__import__

    def fake(name, *a, **k):
        if name == "lightgbm" or name.startswith("lightgbm."):
            raise ImportError("blocked for test")
        return real_import(name, *a, **k)

    for m in [m for m in sys.modules if m == "lightgbm" or m.startswith("lightgbm.")]:
        monkeypatch.delitem(sys.modules, m)
    monkeypatch.setattr(builtins, "__import__", fake)
    assert pipeline.lightgbm_version() is None
    with pytest.raises(pipeline.LightGBMRequired):
        pipeline.run(table, tmp_path, synthetic=False, n_trials=4, n_boot=50)
    X = table[[c for c in table.columns if c.startswith("f_")]].to_numpy(float)[:200]
    y = np.arange(200) % 2
    with pytest.raises(pipeline.LightGBMRequired):
        pipeline._fold_models(X, y.astype(float), np.ones(200), np.arange(200))
    # acik parametre: sentetik/test kipi lojistige dusebilir
    assert set(pipeline._fold_models(X, y.astype(float), np.ones(200), np.arange(200), require_lightgbm=False)) == {"logistic"}


def test_registry_n_trials_is_four_and_recipe_registered():
    assert config.RECIPE_ID == "ml1-r01-v1b-native33"
    with DEFAULT_REGISTRY.open(encoding="utf-8", newline="") as fh:
        ids = [r["recipe_id"] for r in csv.DictReader(fh)]
    assert ids == ["ml0c-baseline-v1", "ml1-r01-v1b-native33"]
    assert n_trials_from_registry() == 4


def test_native33_feature_count_and_report_fields(table, tmp_path):
    pytest.importorskip("lightgbm")
    from trader_core.ml_features import FEATURE_NAMES
    assert len(FEATURE_NAMES) == 33
    s = pipeline.run(table, tmp_path, synthetic=True, n_boot=100, n_trials=4, corpus_sha256="ab" * 32)
    md = (tmp_path / "gate_report.md").read_text(encoding="utf-8")
    for needle in ("BAĞLAYICI", "TANI, tüm satırlar", "ab" * 32, config.RECIPE_ID, "n_trials): 4", "lightgbm sürümü: 4."):
        assert needle in md, needle
    assert s["recipe_id"] == config.RECIPE_ID and "ic_all_rows_diagnostic" in s
