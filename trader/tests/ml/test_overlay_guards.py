"""Katman korumalari (BT-1 karari, 18 Kasim 2026): taken_per_fold/gate_closed_skips manifest alanlari, cikis kodu 4,
verify_overlay_manifest sartlari. Sentetik manifest/defter; backtest KOSULMAZ."""
from __future__ import annotations

import json
import sqlite3

import pandas as pd
import pytest

from trader_ml import corpus_v2
from test_build_corpus_v2_overlay import ROWS, clean, corpus_for, make_run, mod  # noqa: F401

FOLD_STARTS = ["2022-01-06", "2023-02-04", "2024-03-04", "2025-04-02"]


def _build(mod, tmp_path, rows=ROWS, gate_rows=()):
    rd = make_run(tmp_path, rows)
    if gate_rows:
        con = sqlite3.connect(rd / "ledger.sqlite")
        for i, (vr, ts) in enumerate(gate_rows, 100):
            con.execute("INSERT INTO v_decisions VALUES (?,?,?,?,?,?,?,?,?,?,?)",
                        (i, ts, "BTC/USDT", "long", "T1", 1.0, 0.9, None, "skipped", "entry_gate_closed", vr))
        con.commit()
        con.close()
    corpus = corpus_for(tmp_path, rows)
    out = tmp_path / "out"
    rc = mod.run(["--run-dir", str(rd), "--corpus", str(corpus), "--out-dir", str(out)])
    man = json.loads((out / "corpus_v2_taken.manifest.json").read_text())
    return rc, man, out / "corpus_v2_taken.parquet", corpus


def test_manifest_has_fold_year_and_entry_fields(mod, clean, tmp_path):
    rc, man, ovp, corpus = _build(mod, tmp_path)
    assert rc == 0
    tpf = man["taken_per_fold"]
    assert [e["test_start"][:10] for e in tpf] == FOLD_STARTS and tpf[-1]["test_end"][:10] == "2026-05-01"
    assert [e["fold"] for e in tpf] == [0, 1, 2, 3] and [e["taken"] for e in tpf] == [3, 1, 1, 1]
    assert man["taken_per_year"] == {"2022": 3, "2023": 1, "2024": 1, "2025": 1}
    assert man["first_entry_ts"].startswith("2022-03-01T10:00") and man["last_entry_ts"].startswith("2025-06-01T10:00")
    assert man["gate_closed_skips"] == {}
    assert corpus_v2.verify_overlay_manifest(man, ovp, corpus) == []


def test_empty_fold_fails_with_guard_exit_but_writes_files(mod, clean, tmp_path, capsys):
    rc, man, ovp, corpus = _build(mod, tmp_path, rows=ROWS[:5])        # yalniz dilim 0'da alinan
    assert rc == mod.GUARD_EXIT == 4 and mod.GUARD_EXIT != mod.UNMATCHED_EXIT
    assert ovp.exists() and [e["taken"] for e in man["taken_per_fold"]] == [3, 0, 0, 0]
    assert "alinan islem 0" in capsys.readouterr().err
    assert corpus_v2.verify_overlay_manifest(man, ovp, corpus)


def test_gate_closed_skip_fails_and_is_counted_by_veto_reason(mod, clean, tmp_path, capsys):
    rc, man, ovp, corpus = _build(mod, tmp_path, gate_rows=[("v1", "2022-05-01T00:00:00+00:00"), ("v1", "2022-05-02T00:00:00+00:00"), (None, "2022-05-03T00:00:00+00:00")])
    assert rc == mod.GUARD_EXIT and ovp.exists()
    assert man["gate_closed_skips"] == {"none": 1, "v1": 2}
    assert "entry_gate_closed" in capsys.readouterr().err
    assert any("gate_closed_skips" in e for e in corpus_v2.verify_overlay_manifest(man, ovp, corpus))


def test_other_skip_reasons_not_counted(mod, clean, tmp_path):
    rc, man, *_ = _build(mod, tmp_path)                                  # ROWS'taki atlamalar skip_reason='risk'
    assert rc == 0 and man["gate_closed_skips"] == {}


def test_verify_requires_fields_and_positive_folds(mod, clean, tmp_path):
    rc, good, ovp, corpus = _build(mod, tmp_path)
    assert corpus_v2.verify_overlay_manifest(good, ovp, corpus) == []
    no_tpf = {k: v for k, v in good.items() if k != "taken_per_fold"}
    no_gcs = {k: v for k, v in good.items() if k != "gate_closed_skips"}
    three = {**good, "taken_per_fold": good["taken_per_fold"][:3]}
    zero = {**good, "taken_per_fold": [good["taken_per_fold"][0], {**good["taken_per_fold"][1], "taken": 0}, *good["taken_per_fold"][2:]]}
    gated = {**good, "gate_closed_skips": {"none": 1}}
    for name, m in (("no_tpf", no_tpf), ("no_gcs", no_gcs), ("three", three), ("zero", zero), ("gated", gated)):
        assert corpus_v2.verify_overlay_manifest(m, ovp, corpus), name
    assert corpus_v2.OVERLAY_VERSION == "corpus_v2_taken"
