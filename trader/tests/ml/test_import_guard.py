"""trader_engine ve trader_core lightgbm/sklearn/scipy ice aktarmaz; motor yoluna ML kutuphanesi girmez."""
import ast
import tomllib
from pathlib import Path

SRC = Path(__file__).resolve().parents[2] / "src"
ROOT = SRC.parent
FORBIDDEN = {"lightgbm", "sklearn", "scipy", "xgboost", "catboost", "torch"}


def _imports(py: Path) -> set[str]:
    tree = ast.parse(py.read_text(encoding="utf-8"))
    out = set()
    for n in ast.walk(tree):
        if isinstance(n, ast.Import):
            out |= {a.name.split(".")[0] for a in n.names}
        elif isinstance(n, ast.ImportFrom) and n.level == 0 and n.module:
            out.add(n.module.split(".")[0])
    return out


def _scan(pkg: str) -> dict[str, set[str]]:
    return {str(p.relative_to(SRC)): _imports(p) for p in (SRC / pkg).rglob("*.py")}


def test_engine_and_core_never_import_ml_libs():
    for pkg in ("trader_engine", "trader_core"):
        files = _scan(pkg)
        assert files, pkg
        bad = {f: i & FORBIDDEN for f, i in files.items() if i & FORBIDDEN}
        assert not bad, bad


def test_engine_and_core_do_not_import_trader_ml():
    for pkg in ("trader_engine", "trader_core"):
        bad = [f for f, i in _scan(pkg).items() if "trader_ml" in i]
        assert not bad, bad


def test_tree_evaluator_is_numpy_only():
    """ML-0a: degerlendirici trader_core'a tasindi (motor trader_ml'e bagimli olmaz); trader_ml.treeeval geri-export eder."""
    imps = _imports(SRC / "trader_core" / "ml_eval.py")
    assert imps <= {"__future__", "math", "numpy"}, imps
    assert _imports(SRC / "trader_ml" / "treeeval.py") <= {"__future__", "trader_core"}
    pkg = _imports(SRC / "trader_core" / "ml_package.py")                    # motor tarafi paket okuyucu: stdlib + numpy
    assert pkg <= {"__future__", "hashlib", "json", "re", "dataclasses", "datetime", "pathlib", "numpy"}, pkg
    import trader_ml.treeeval as te
    from trader_core import ml_eval
    assert te.TreeModel is ml_eval.TreeModel


def test_engine_imports_only_core_for_ml():
    """Motor ML icin yalniz trader_core.ml_* kullanir (trader_ml'e hic dokunmaz)."""
    for f, imps in _scan("trader_engine").items():
        assert "trader_ml" not in imps, f


def test_lightgbm_only_in_training_modules():
    users = {f for f, i in _scan("trader_ml").items() if "lightgbm" in i}
    assert users <= {"trader_ml/models.py"}, users


def test_runtime_dependencies_unchanged_and_ml_pinned_separately():
    d = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    deps = " ".join(d["project"]["dependencies"]).lower()
    opt = " ".join(x for v in d["project"].get("optional-dependencies", {}).values() for x in v).lower()
    for lib in ("lightgbm", "scikit-learn", "sklearn", "scipy"):
        assert lib not in deps and lib not in opt
    req = (ROOT / "requirements-ml.txt").read_text(encoding="utf-8")
    assert "lightgbm==4.6.0" in req and "--hash=sha256:" in req
