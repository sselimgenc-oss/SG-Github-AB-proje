"""08 §4.4: feed hafifliği. Alt süreçte içe aktarma; pandas/numpy/requests/pyarrow yüklenmemeli."""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

SRC = Path(__file__).resolve().parents[2] / "src"
HEAVY = {"pandas", "numpy", "requests", "pyarrow"}
LIGHT = ["trader_engine.types", "trader_engine.errors", "trader_engine.numeric", "trader_engine.clock", "trader_engine.bars",
         "trader_engine.config", "trader_engine.fileio", "trader_engine.exchange.rules", "trader_engine.marketdata.rest_public",
         "trader_engine.marketdata.store", "trader_engine.marketdata.feed", "trader_engine.cli"]
FREE = ["marketdata.sources", "strategy_runner", "engine", "gates", "backtest", "metrics", "precomputed"]   # bilgi: serbest küme

CODE = ("import sys, json\nsys.path.insert(0, {src!r})\nimport {mod}\n"
        "print(json.dumps(sorted(m for m in sys.modules if m.split('.')[0] in {heavy!r})))")


def heavy_loaded(mod: str, src: Path = SRC) -> list[str]:
    code = CODE.format(src=str(src), mod=mod, heavy=sorted(HEAVY))
    r = subprocess.run([sys.executable, "-I", "-c", code], capture_output=True, text=True, timeout=30)
    assert r.returncode == 0, r.stderr
    return json.loads(r.stdout)


def _exists(mod: str) -> bool:
    rel = Path(*mod.split("."))
    return (SRC / rel).with_suffix(".py").exists() or (SRC / rel / "__init__.py").exists()


@pytest.mark.parametrize("mod", LIGHT)
def test_light_modules_load_no_heavy(mod):
    if not _exists(mod):
        pytest.skip(f"{mod} henüz yok (başka birimin dosyası)")
    assert heavy_loaded(mod) == []


def test_requests_not_loaded_at_import():
    assert "requests" not in heavy_loaded("trader_engine.marketdata.rest_public")


def test_detector_boundary(tmp_path):
    pkg = tmp_path / "fakepkg"
    pkg.mkdir()
    (pkg / "__init__.py").write_text("")
    (pkg / "light.py").write_text("import json\n")
    (pkg / "heavy.py").write_text("import numpy\n")
    assert heavy_loaded("fakepkg.light", tmp_path) == []
    assert "numpy" in heavy_loaded("fakepkg.heavy", tmp_path)
