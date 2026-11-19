"""Statik kilit: research/holdout_muhur.py'yi `muhurle`/`dogrula` disinda kullanan research betigi yok
(modul holdout satirlarini yalniz hash icin okur; baska betik bunu veri okumak icin kullanamaz)."""
from __future__ import annotations

import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
RESEARCH = ROOT / "research"


def _refs(text: str) -> bool:
    tree = ast.parse(text)
    for n in ast.walk(tree):
        if isinstance(n, ast.Import) and any("holdout_muhur" in a.name for a in n.names):
            return True
        if isinstance(n, ast.ImportFrom) and ("holdout_muhur" in (n.module or "") or any("holdout_muhur" in a.name for a in n.names)):
            return True
        if isinstance(n, ast.Constant) and isinstance(n.value, str) and "holdout_muhur" in n.value:
            return True
    return False


def test_self_flags_synthetic_snippets():
    assert _refs("import holdout_muhur")
    assert _refs("from research import holdout_muhur as m")
    assert _refs("spec_from_file_location('x', 'research/holdout_muhur.py')")
    assert not _refs("import json\nx = 1\n")


def test_no_other_research_script_uses_holdout_muhur():
    bad = [p.relative_to(ROOT).as_posix() for p in sorted(RESEARCH.rglob("*.py"))
           if p.name != "holdout_muhur.py" and _refs(p.read_text(encoding="utf-8"))]
    assert not bad, f"holdout_muhur yalniz kendi CLI'sinden calisir: {bad}"


def test_muhur_module_exposes_only_hash_reads():
    tree = ast.parse((RESEARCH / "holdout_muhur.py").read_text(encoding="utf-8"))
    reads = [n.lineno for n in ast.walk(tree) if isinstance(n, ast.Call) and getattr(n.func, "attr", "") in ("read_feather", "read_parquet", "read_csv")]
    assert len(reads) == 1          # tek okuma noktasi: hash_file
