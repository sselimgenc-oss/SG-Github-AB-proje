"""08 §4.8: test dosya adları tekil (pytest prepend modunda çakışma olmaması)."""
from __future__ import annotations

import os
from collections import Counter
from pathlib import Path

TESTS = Path(__file__).resolve().parents[1]


def duplicate_names(tests_dir: Path) -> list[str]:
    names = []
    for d, dirs, files in os.walk(tests_dir):
        dirs[:] = [x for x in dirs if x not in ("__pycache__", "fixtures")]
        names += [f for f in files if f.startswith("test_") and f.endswith(".py")]
    return sorted(n for n, c in Counter(names).items() if c > 1)


def conftests(tests_dir: Path) -> list[Path]:
    out = []
    for d, dirs, files in os.walk(tests_dir):
        dirs[:] = [x for x in dirs if x not in ("__pycache__", "fixtures")]
        out += [Path(d) / f for f in files if f == "conftest.py"]
    return out


def test_unique_test_file_names():
    assert duplicate_names(TESTS) == []


def test_no_engine_package_init():
    assert not (TESTS / "engine" / "__init__.py").exists()


def test_conftest_is_path_independent():
    for p in conftests(TESTS):
        assert "sys.path" not in p.read_text(encoding="utf-8"), p


def test_detector_boundary(tmp_path):
    (tmp_path / "engine").mkdir()
    (tmp_path / "test_a.py").write_text("")
    (tmp_path / "engine" / "test_b.py").write_text("")
    assert duplicate_names(tmp_path) == []
    (tmp_path / "engine" / "test_a.py").write_text("")
    assert duplicate_names(tmp_path) == ["test_a.py"]
