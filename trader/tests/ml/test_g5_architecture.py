"""ML-G5 mimari testi (mentor G5 fix 6): egitim/arastirma kodu (`trader_ml`, `scripts/`) `trader_core.ml_features_v2`yi (ozellikle
`feature_frame_v2`) DOGRUDAN iceri almaz; tek kapi `trader_ml/features_v2.py` (her cerceve ve fonlamada `assert_pre_holdout`).
Motor tarafi (`trader_core.ml_live_v2`) bu kuralin disindadir: kilitli donem verisi motora zaten girmez."""
from __future__ import annotations

import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
GATE = ROOT / "src" / "trader_ml" / "features_v2.py"
TARGET = "ml_features_v2"


def _violations(src: str) -> list[str]:
    out = []
    for n in ast.walk(ast.parse(src)):
        if isinstance(n, ast.Import):
            out += [a.name for a in n.names if TARGET in a.name]
        elif isinstance(n, ast.ImportFrom):
            if n.module and TARGET in n.module:
                out.append(n.module)
            out += [a.name for a in n.names if TARGET in a.name or a.name == "feature_frame_v2" and "features_v2" not in (n.module or "")]
        elif isinstance(n, ast.Constant) and isinstance(n.value, str) and TARGET in n.value and len(n.value) < 80:
            out.append(n.value)                                # importlib.import_module("...ml_features_v2")
    return out


def test_detector_catches_every_import_form():
    for src in ("from trader_core.ml_features_v2 import feature_frame_v2", "from trader_core import ml_features_v2",
                "import trader_core.ml_features_v2 as m", "from ..trader_core.ml_features_v2 import X",
                "import importlib; importlib.import_module('trader_core.ml_features_v2')",
                "from trader_core import feature_frame_v2"):
        assert _violations(src), src
    assert not _violations("from trader_ml.features_v2 import feature_frame_v2")
    assert not _violations("from .features_v2 import feature_frame_v2, R02_FEATURE_NAMES")


def test_training_and_scripts_only_use_the_guarded_wrapper():
    files = [p for p in sorted((ROOT / "src" / "trader_ml").rglob("*.py")) + sorted((ROOT / "scripts").rglob("*.py")) if p != GATE]
    assert len(files) > 10
    bad = {str(p.relative_to(ROOT)): v for p in files if (v := _violations(p.read_text(encoding="utf-8")))}
    assert not bad, f"trader_ml/scripts yalniz trader_ml.features_v2 uzerinden gecmeli: {bad}"


def test_gate_wrapper_checks_holdout_before_core_call():
    tree = ast.parse(GATE.read_text(encoding="utf-8"))
    fn = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == "feature_frame_v2")
    calls = [(c.lineno, ast.unparse(c.func)) for c in ast.walk(fn) if isinstance(c, ast.Call)]
    guards = [ln for ln, f in calls if f == "assert_pre_holdout"]
    core = [ln for ln, f in calls if f.endswith("feature_frame_v2")]
    assert len(guards) >= 3 and core and max(guards) < min(core)     # cerceve, fonlama, aday zamani; hepsi cekirdekten once
