"""08 §4.1: dış çerçeve yasağı (statik AST taraması; taranan modül içe aktarılmaz)."""
from __future__ import annotations

import ast
import os
import re
import tomllib
from pathlib import Path

import pytest

FORBIDDEN_TOP = {"freqtrade", "freqtrade_client", "ccxt", "binance", "binance_connector", "python_binance", "pybit", "bybit",
                 "okx", "kucoin", "krakenex", "alpaca", "alpaca_trade_api", "ib_insync", "backtrader", "vectorbt", "vectorbtpro",
                 "zipline", "backtesting", "lean", "motor", "1l3a"}
FORBIDDEN_DEP_NAMES = FORBIDDEN_TOP | {"python-binance", "binance-connector"}
ALLOWED_DEPS = {"pandas", "numpy", "pyarrow", "requests"}
ALLOWED_OPTIONAL = {"dev": {"pytest", "pyyaml"}, "live": {"websockets"}}
SCAN_ROOTS = ("src/trader_engine", "src/trader_core")
ENGINE_ROOT = "src/trader_engine"
SUBPROCESS_ALLOW = {("backtest.py", "git")}
FREQTRADE_REMOVED = True
FREQTRADE_TEXT_ROOTS = ("scripts", "config", "deploy", "src")
_FT = "freq" + "trade"

REPO = Path(__file__).resolve().parents[2]          # .../trader
GIT_ROOT = REPO.parent


# ------------------------------------------------------------------------------------------------ tarayıcı
def _pyfiles(base: Path):
    for d, dirs, files in os.walk(base):
        dirs[:] = [x for x in dirs if x != "__pycache__"]
        for f in sorted(files):
            if f.endswith(".py"):
                yield Path(d) / f


def _aliases(tree: ast.AST) -> dict[str, str]:
    m: dict[str, str] = {}
    for n in ast.walk(tree):
        if isinstance(n, ast.Import):
            for a in n.names:
                m[a.asname or a.name.split(".")[0]] = a.name if a.asname else a.name.split(".")[0]
        elif isinstance(n, ast.ImportFrom) and n.level == 0 and n.module:
            for a in n.names:
                m[a.asname or a.name] = f"{n.module}.{a.name}"
    return m


def _dotted(node: ast.AST, al: dict[str, str]) -> str | None:
    parts = []
    while isinstance(node, ast.Attribute):
        parts.append(node.attr)
        node = node.value
    if isinstance(node, ast.Name):
        parts.append(al.get(node.id, node.id))
        return ".".join(reversed(parts))
    return None


def _strs(node: ast.AST) -> list[str]:
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return [node.value]
    if isinstance(node, (ast.List, ast.Tuple)):
        return [e.value for e in node.elts if isinstance(e, ast.Constant) and isinstance(e.value, str)]
    return []


def _scan_file(path: Path, rel: str, is_engine: bool) -> list[str]:
    v: list[str] = []
    src = path.read_text(encoding="utf-8")
    tree = ast.parse(src, filename=rel)
    al = _aliases(tree)
    lines = src.splitlines()

    def add(n, why):
        v.append(f"{rel}:{n.lineno}:{lines[n.lineno - 1].strip()[:80]} [{why}]")

    for n in ast.walk(tree):
        if isinstance(n, ast.Import):
            for a in n.names:
                if a.name.split(".")[0] in FORBIDDEN_TOP:
                    add(n, "forbidden import")
        elif isinstance(n, ast.ImportFrom) and n.level == 0 and n.module and n.module.split(".")[0] in FORBIDDEN_TOP:
            add(n, "forbidden import")
        elif isinstance(n, ast.Call):
            name = _dotted(n.func, al) or ""
            if name in ("importlib.import_module", "importlib.util.find_spec", "__import__", "builtins.__import__"):
                if not n.args or not (isinstance(n.args[0], ast.Constant) and isinstance(n.args[0].value, str)):
                    add(n, "dynamic import")
                elif n.args[0].value.split(".")[0] in FORBIDDEN_TOP:
                    add(n, "forbidden dynamic import")
            first = _strs(n.args[0]) if n.args else []
            if name.startswith("subprocess.") or name in ("os.system", "os.popen"):
                exe = (first[0].split()[0] if first and first[0].split() else "")
                if any(_FT in s.lower() or "docker" in s.lower() for s in first):
                    add(n, "forbidden process")
                elif (path.name, exe) not in SUBPROCESS_ALLOW:
                    add(n, "process call not allowed")
            elif name == "shutil.which" and any(_FT in s.lower() or "docker" in s.lower() for s in first):
                add(n, "forbidden process")
            if is_engine and name in ("sys.path.insert", "sys.path.append", "sys.path.extend", "site.addsitedir"):
                add(n, "path manipulation")
        elif is_engine and isinstance(n, (ast.Assign, ast.AugAssign, ast.AnnAssign)):
            targets = n.targets if isinstance(n, ast.Assign) else [n.target]
            for t in targets:
                if (isinstance(t, ast.Subscript) and isinstance(t.slice, ast.Constant) and t.slice.value == "PYTHONPATH"
                        and _dotted(t.value, al) == "os.environ"):
                    add(n, "PYTHONPATH assignment")
    return v


def scan_tree(root: Path) -> list[str]:
    """root: `trader/` kökü benzeri dizin. Denetim 1-3 (içe aktarma, süreç, yol)."""
    out: list[str] = []
    for sr in SCAN_ROOTS:
        base = Path(root) / sr
        if base.exists():
            for p in _pyfiles(base):
                out += _scan_file(p, str(p.relative_to(root)), sr == ENGINE_ROOT)
    return out


def _norm(dep: str) -> str:
    return re.split(r"[\s\[<>=!~;@(]", dep.strip(), maxsplit=1)[0].lower().replace("_", "-")


def check_pyproject(path: Path) -> list[str]:
    v: list[str] = []
    d = tomllib.loads(Path(path).read_text(encoding="utf-8"))
    deps = d.get("project", {}).get("dependencies", [])
    if {_norm(x) for x in deps} != ALLOWED_DEPS:
        v.append(f"dependencies {sorted(_norm(x) for x in deps)} != {sorted(ALLOWED_DEPS)}")
    opt = {k: {_norm(x) for x in xs} for k, xs in d.get("project", {}).get("optional-dependencies", {}).items()}
    if opt != ALLOWED_OPTIONAL:
        v.append(f"optional-dependencies {opt} != {ALLOWED_OPTIONAL}")
    allreqs = list(deps) + [x for xs in d.get("project", {}).get("optional-dependencies", {}).values() for x in xs] \
        + list(d.get("build-system", {}).get("requires", []))
    for r in allreqs:
        if any(t in r for t in ("@", "git+", "file:", "http")):
            v.append(f"url/path dependency: {r}")
        if _norm(r) in FORBIDDEN_DEP_NAMES:
            v.append(f"forbidden dependency: {r}")
    return v


def check_no_submodule_or_mount(repo: Path, git_root: Path) -> list[str]:
    v: list[str] = []
    gm = git_root / ".gitmodules"
    if gm.exists() and "1l3a" in gm.read_text(encoding="utf-8"):
        v.append(".gitmodules mentions 1l3a")
    for d, dirs, files in os.walk(repo):
        dirs[:] = [x for x in dirs if x not in (".venv", ".venv-ft", ".git", "__pycache__", ".pytest_cache")]
        for n in dirs + files:
            p = Path(d) / n
            if p.is_symlink() and ("1l3a" in os.readlink(p) or ("ssel" + "imgenc") in os.readlink(p)):
                v.append(f"symlink to 1l3a: {p}")
    dc = repo / "docker-compose.yml"
    if not FREQTRADE_REMOVED and dc.exists() and "1l3a" in dc.read_text(encoding="utf-8"):
        v.append("docker-compose.yml mentions 1l3a")
    return v


def scan_freqtrade_text(root: Path) -> list[str]:
    """Yalnız FREQTRADE_REMOVED=True kipinde (§6)."""
    v: list[str] = []
    for r in FREQTRADE_TEXT_ROOTS:
        for d, dirs, files in os.walk(Path(root) / r):
            dirs[:] = [x for x in dirs if x not in ("__pycache__", ".venv")]
            for f in files:
                p = Path(d) / f
                try:
                    t = p.read_text(encoding="utf-8")
                except (UnicodeDecodeError, OSError):
                    continue
                for i, ln in enumerate(t.splitlines(), 1):
                    if _FT in ln.lower():
                        v.append(f"{p.relative_to(root)}:{i}:{ln.strip()[:80]}")
    dc = Path(root) / "docker-compose.yml"
    if dc.exists() and (_FT + "org") in dc.read_text(encoding="utf-8"):
        v.append("docker-compose.yml: " + _FT + "org")
    for p in (Path(root) / "deploy").glob("*.service") if (Path(root) / "deploy").exists() else []:
        for ln in p.read_text(encoding="utf-8").splitlines():
            if ln.startswith("ExecStart") and (_FT in ln.lower() or "docker" in ln.lower()):
                v.append(f"{p.name}: {ln}")
    return v


# ------------------------------------------------------------------------------------------------ gerçek ağaç
def test_real_tree_has_no_forbidden_imports():
    assert scan_tree(REPO) == []


def test_real_pyproject_is_closed_set():
    assert check_pyproject(REPO / "pyproject.toml") == []


def test_no_submodule_or_mount():
    assert check_no_submodule_or_mount(REPO, GIT_ROOT) == []


def test_freqtrade_text_gate():
    if not FREQTRADE_REMOVED:
        pytest.skip("FREQTRADE_REMOVED=False: silme kapısı kapalı (08 §6)")
    assert scan_freqtrade_text(REPO) == []


# ------------------------------------------------------------------------------------------------ kendi sınır testi
def _w(root: Path, rel: str, text: str):
    p = root / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(text, encoding="utf-8")


def test_scan_tree_clean_and_violations(tmp_path):
    clean = tmp_path / "clean"
    _w(clean, "src/trader_engine/a.py", "import json\nimport trader_core.risk\nfrom . import b\n'''import ccxt'''\n")
    _w(clean, "src/trader_core/b.py", "import pandas\n")
    _w(clean, "src/trader_engine/backtest.py", "import subprocess\nsubprocess.run(['git', 'rev-parse', 'HEAD'])\n")
    assert scan_tree(clean) == []
    cases = {
        "import ccxt\n": "foo.py:1:import ccxt",
        "from binance.client import Client\n": "forbidden import",
        "import importlib\nimportlib.import_module(name)\n": "dynamic import",
        "from importlib import import_module\nimport_module('ccxt')\n": "forbidden dynamic import",
        "__import__(x)\n": "dynamic import",
        "import subprocess\nsubprocess.run(['" + _FT + "', 'x'])\n": "forbidden process",
        "import os\nos.system('docker ps')\n": "forbidden process",
        "import subprocess\nsubprocess.run(['ls'])\n": "process call not allowed",
        "import sys\nsys.path.insert(0, 'x')\n": "path manipulation",
        "import os\nos.environ['PYTHONPATH'] = 'x'\n": "PYTHONPATH assignment",
    }
    for i, (code, why) in enumerate(cases.items()):
        bad = tmp_path / f"bad{i}"
        _w(bad, "src/trader_engine/foo.py", code)
        found = scan_tree(bad)
        assert found and why in found[0], (code, found)
    bad = tmp_path / "core"
    _w(bad, "src/trader_core/x.py", "import freqtrade.strategy\n")
    assert scan_tree(bad)
    # yol manipülasyonu yalnız motorda yasak
    ok = tmp_path / "okpath"
    _w(ok, "src/trader_core/x.py", "import sys\nsys.path.insert(0, 'x')\n")
    assert scan_tree(ok) == []


def test_check_pyproject_boundaries(tmp_path):
    good = '[project]\ndependencies = ["pandas>=2.2", "numpy>=1.26", "pyarrow>=15", "requests>=2.31"]\n' \
           '[project.optional-dependencies]\ndev = ["pytest", "pyyaml"]\nlive = ["websockets>=12"]\n' \
           '[build-system]\nrequires = ["setuptools>=68"]\n'
    p = tmp_path / "p.toml"
    p.write_text(good)
    assert check_pyproject(p) == []
    p.write_text(good.replace('"requests>=2.31"', '"requests>=2.31", "ccxt>=4"'))
    assert check_pyproject(p)
    p.write_text(good.replace('"requests>=2.31"', '"requests @ git+https://x/y"'))
    assert check_pyproject(p)
    p.write_text(good.replace("setuptools>=68", "freqtrade"))
    assert check_pyproject(p)
    p.write_text(good.replace('"websockets>=12"', '"websockets>=12", "x"'))
    assert check_pyproject(p)


def test_submodule_and_symlink_detection(tmp_path):
    repo = tmp_path / "trader"
    repo.mkdir()
    (tmp_path / ".gitmodules").write_text('[submodule "x"]\n path = 1l3a-proje\n')
    assert check_no_submodule_or_mount(repo, tmp_path)
    (tmp_path / ".gitmodules").unlink()
    os.symlink("/somewhere/1l3a-proje", repo / "link")
    assert check_no_submodule_or_mount(repo, tmp_path)


def test_freqtrade_text_scan_synthetic(tmp_path):
    _w(tmp_path, "scripts/a.py", "# " + _FT + " here\n")
    _w(tmp_path, "src/ok.py", "x = 1\n")
    _w(tmp_path, "deploy/a.service", "[Service]\nExecStart=docker run x\n")
    found = scan_freqtrade_text(tmp_path)
    assert any(f.startswith("scripts/a.py:1") for f in found) and any("ExecStart" in f for f in found)
    clean = tmp_path / "c"
    _w(clean, "src/ok.py", "x = 1\n")
    assert scan_freqtrade_text(clean) == []
