"""Spec C7: gercek backtest kosusu uzerinde duman testi (lead: ayri dosya, cunku spec dosyasi kilit-yolu testleri icin
kilitli donem tarihlerini sentetik veride kullanir; tests/engine/test_no_holdout_in_tests.py gercek-veri dosyasinda buna izin vermez)."""
from __future__ import annotations

import json

import pytest

pytest.importorskip("trader_reports")

from test_reports_spec import NOW, ROOT, run_cli  # noqa: E402


def test_c7_real_backtest_smoke(tmp_path):
    run = ROOT / "var" / "backtests" / "1h_IS_f1_s0_native_last"
    hist = ROOT / "var" / "history"
    if not (run.is_dir() and hist.is_dir()):
        pytest.skip("gercek veri yok (spec C7: yoksa atlanir)")
    p = run_cli(["--run-dir", run, "--history", hist, "--synthetic-rules", "--now", NOW, "--out", tmp_path / "out"])
    assert p.returncode == 0, p.stdout + p.stderr
    assert json.loads(p.stdout.strip().splitlines()[-1])["n_trades"] == 610
