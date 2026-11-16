"""Uctan uca: sentetik aday tablosu -> egitim -> paket -> kapi -> Turkce rapor."""
import json
import subprocess
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

pytest.importorskip("lightgbm")

from trader_ml import pipeline
from trader_ml.package import load_package
from trader_ml.schema import SchemaError, feature_columns, load_candidates, validate_candidates
from trader_ml.treeeval import TreeModel

ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture(scope="module")
def run(table, tmp_path_factory):
    out = tmp_path_factory.mktemp("ml_run")
    return out, pipeline.run(table, out, synthetic=True, n_boot=300)


def test_end_to_end_artifacts_and_parity(run, table):
    out, s = run
    for f in ("model_candidate.json", "gate_report.md", "gate_result.json", "oof_predictions.parquet"):
        assert (out / f).exists()
    assert s["parity_max_abs_diff"] <= 1e-9
    pkg = load_package(out / "model_candidate.json", check_expiry=False)
    assert pkg["meta"]["features"] == feature_columns(table) and pkg["meta"]["expiry_days"] == 21
    assert pkg["meta"]["train_window"]["end"].startswith("2026-04-30")
    assert pkg["meta"]["synthetic"] is True
    # paket, motor okuyucusuyla egitim disi satirlarda olasilik verir
    X = table[pkg["meta"]["features"]].to_numpy(float)
    p = TreeModel(pkg["model"], pkg["calibration"]).predict_proba(X)
    assert np.all((p >= 0) & (p <= 1))


def test_report_is_turkish_and_complete(run):
    out, s = run
    md = (out / "gate_report.md").read_text(encoding="utf-8")
    for needle in ("ML terfi kapısı raporu", "Kapı adımları", "IC kapisi", "Deflated Sharpe", "PBO", "Holm",
                   "Esleme", "SENTETİK", "Kilitli dönem", "Tepe bellek"):
        assert needle in md, needle
    res = json.loads((out / "gate_result.json").read_text())
    assert res["passed"] == (not any(c["ok"] is False for c in res["checks"]))
    assert s["peak_rss_mb"] < 450                                      # §6 bellek tavani


def test_oof_never_contains_training_rows(run, table):
    out, _ = run
    oof = pd.read_parquet(out / "oof_predictions.parquet")
    assert oof["ts"].min() >= pd.Timestamp("2025-08-01", tz="UTC") and oof["fold"].nunique() == 4


def test_cli_script_synthetic(tmp_path):
    r = subprocess.run([sys.executable, str(ROOT / "scripts" / "ml_gate.py"), "--synthetic", "--out", str(tmp_path / "o"),
                        "--limits"], capture_output=True, text=True, timeout=600, cwd=ROOT)
    assert r.returncode == 0, r.stderr[-2000:]
    assert (tmp_path / "o" / "gate_report.md").exists()


def test_loader_reads_19b_style_parquet_and_csv(table, tmp_path):
    table.to_parquet(tmp_path / "c.parquet")
    table.to_csv(tmp_path / "c.csv", index=False)
    a, b = load_candidates(tmp_path / "c.parquet"), load_candidates(tmp_path / "c.csv")
    assert len(a) == len(b) == len(table) and feature_columns(a) == feature_columns(table)


def test_schema_validation_errors(table):
    with pytest.raises(SchemaError, match="eksik"):
        validate_candidates(table.drop(columns=["net_r"]))
    bad = table.copy()
    bad.loc[0, "planned_stop"] = bad.loc[0, "planned_entry"] * (1.01 if bad.loc[0, "side"] == "long" else 0.99)
    with pytest.raises(SchemaError, match="stop"):
        validate_candidates(bad)
    with pytest.raises(SchemaError, match="tekrarli"):
        validate_candidates(pd.concat([table, table.iloc[:1]]))
