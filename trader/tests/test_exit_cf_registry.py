"""docs/cikis-karsi-olgu-spec.md 0: on kayit. `research/trial_registry.csv` icinde `exitcf-v1` satiri olmadan ilk gercek kosu YASAK.
Sunucuda research/ yoktur; bu test depoda satirin varligini ve surum eslesmesini zorlar."""
from __future__ import annotations

import csv
import json
from pathlib import Path

from trader_core import exit_counterfactual as EC

ROOT = Path(__file__).resolve().parents[1]
CSV = ROOT / "research" / "trial_registry.csv"


def test_constants_and_row_shape():
    assert EC.REGISTRY_ID == "exitcf-v1" and EC.VERSION == 1 and EC.PARAM == "trail_atr"
    row = EC.registry_row()
    assert row["id"] == "exitcf-v1" and row["strategy"] == "TraderV1b" and row["n_trials"] == 2 and row["version"] == EC.VERSION
    assert json.loads(row["params"]) == {"grid": "cur±LESSON_STEP", "params": ["trail_atr"]}
    assert EC.ROLES == ("base", "up", "down", "own")


def test_registry_csv_has_the_preregistration_row():
    rows = list(csv.DictReader(CSV.open(newline="", encoding="utf-8")))
    mine = [r for r in rows if r["id"].strip().startswith(EC.REGISTRY_ID)]
    assert mine, "research/trial_registry.csv sonuna 'exitcf-v1' on kayit satiri eklenmeli (docs/cikis-karsi-olgu-spec.md 0)"
    r = mine[0]
    assert r["strategy"].startswith("TraderV1b") and "trail_atr" in r["params"]
    notes = r["notes"].lower()
    for word in ("n_trials", "2", "kilitli", "grid", "parite", "ufuk"):
        assert word in notes, word
    assert EC.registry_check(CSV) == (True, "ok")


def test_registry_check_helper(tmp_path):
    p = tmp_path / "r.csv"
    p.write_text("id,strategy\nbaska,X\n", encoding="utf-8")
    assert EC.registry_check(p) == (False, "exitcf-v1 satiri yok")
    p.write_text("id,strategy\nexitcf-v1,TraderV1b\n", encoding="utf-8")
    assert EC.registry_check(p) == (True, "ok")
    assert EC.registry_check(tmp_path / "yok.csv")[0] is False
