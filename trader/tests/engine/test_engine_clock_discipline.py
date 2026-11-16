"""08 §4.2: duvar saati, SQL içi saat ve rastgelelik yasağı (src/trader_engine/**, statik AST)."""
from __future__ import annotations

import ast
import os
import re
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
ENGINE = "src/trader_engine"

FORBIDDEN_CALLS = {
    "datetime.datetime.now", "datetime.datetime.utcnow", "datetime.datetime.today", "datetime.date.today",
    "time.time", "time.time_ns", "time.sleep", "time.monotonic", "time.perf_counter",
    "pandas.Timestamp.now", "pandas.Timestamp.utcnow", "pandas.Timestamp.today", "os.times", "asyncio.sleep",
}
# dosya (src/trader_engine'e göre) -> (izinli çağrılar, zorunlu üst sınıf ya da None)
ALLOWED_WALL_CLOCK = {
    "clock.py": ({"datetime.datetime.now", "time.sleep"}, "SystemClock"),
    "backtest.py": ({"time.perf_counter"}, None),
}
RANDOM_PREFIXES = ("random.", "numpy.random.", "secrets.")
RANDOM_EXACT = {"uuid.uuid4"}
SQL_WORDS = re.compile(r"\b(CREATE|INSERT|UPDATE|SELECT)\b", re.I)
SQL_CLOCK = re.compile(r"CURRENT_TIMESTAMP|datetime\(\s*'now'|julianday\(\s*'now'|strftime\([^)]*'now'", re.I)


def _aliases(tree):
    m = {}
    for n in ast.walk(tree):
        if isinstance(n, ast.Import):
            for a in n.names:
                m[a.asname or a.name.split(".")[0]] = a.name if a.asname else a.name.split(".")[0]
        elif isinstance(n, ast.ImportFrom) and n.level == 0 and n.module:
            for a in n.names:
                m[a.asname or a.name] = f"{n.module}.{a.name}"
    return m


def _dotted(node, al):
    parts = []
    while isinstance(node, ast.Attribute):
        parts.append(node.attr)
        node = node.value
    if isinstance(node, ast.Name):
        parts.append(al.get(node.id, node.id))
        return ".".join(reversed(parts))
    return None


def _calls_with_class(tree):
    """(Call, en yakın çevreleyen sınıf adı | None)"""
    out = []

    def visit(n, cls):
        if isinstance(n, ast.ClassDef):
            cls = n.name
        if isinstance(n, ast.Call):
            out.append((n, cls))
        for c in ast.iter_child_nodes(n):
            visit(c, cls)
    visit(tree, None)
    return out


def scan_clock(root: Path) -> list[str]:
    v = []
    base = Path(root) / ENGINE
    if not base.exists():
        return v
    for d, dirs, files in os.walk(base):
        dirs[:] = [x for x in dirs if x != "__pycache__"]
        for f in sorted(files):
            if not f.endswith(".py"):
                continue
            p = Path(d) / f
            rel = str(p.relative_to(base))
            src = p.read_text(encoding="utf-8")
            tree = ast.parse(src)
            al = _aliases(tree)
            lines = src.splitlines()
            allowed, need_cls = ALLOWED_WALL_CLOCK.get(rel, (set(), None))

            def add(n, why):
                v.append(f"{rel}:{n.lineno}:{lines[n.lineno - 1].strip()[:80]} [{why}]")
            for call, cls in _calls_with_class(tree):
                name = _dotted(call.func, al) or ""
                if name in FORBIDDEN_CALLS:
                    if name in allowed and (need_cls is None or cls == need_cls):
                        continue
                    add(call, name)
                elif name == "random.Random" and rel == "backtest.py":
                    if not call.args and not call.keywords:
                        add(call, "random.Random() without seed")
                elif name in RANDOM_EXACT or name.startswith(RANDOM_PREFIXES):
                    add(call, "randomness " + name)
            for n in ast.walk(tree):
                if isinstance(n, ast.Constant) and isinstance(n.value, str) and SQL_WORDS.search(n.value) and SQL_CLOCK.search(n.value):
                    add(n, "SQL clock")
    return v


def test_real_tree_clock_discipline():
    assert scan_clock(REPO) == []


def _w(root, rel, text):
    p = Path(root) / ENGINE / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(text, encoding="utf-8")


def test_scanner_boundaries(tmp_path):
    clean = tmp_path / "clean"
    _w(clean, "clock.py", "import time\nfrom datetime import datetime, timezone\nclass SystemClock:\n"
                          "    def now(self): return datetime.now(timezone.utc)\n    def sleep(self, s): time.sleep(s)\n")
    _w(clean, "backtest.py", "import time, random\nt = time.perf_counter()\nr = random.Random(42)\n")
    _w(clean, "x.py", "'''docstring mentions datetime.now() and time.time()'''\nfrom datetime import datetime\nd = datetime(2026, 1, 1)\n")
    assert scan_clock(clean) == []
    bad = {
        "engine.py": "from datetime import datetime, timezone\nx = datetime.now(timezone.utc)\n",
        "a.py": "from time import sleep as nap\nnap(1)\n",
        "b.py": "import time as t\nt.time()\n",
        "c.py": "import datetime as dt\ndt.datetime.utcnow()\n",
        "d.py": "import pandas as pd\npd.Timestamp.now()\n",
        "e.py": "import numpy as np\nnp.random.rand()\n",
        "f.py": "import uuid\nuuid.uuid4()\n",
        "g.py": "import random\nrandom.random()\n",
        "h.py": "Q = 'CREATE TABLE t (ts TEXT DEFAULT CURRENT_TIMESTAMP)'\n",
        "i.py": "Q = \"SELECT datetime('now')\"\n",
        "clock.py": "from datetime import datetime\ndef helper(): return datetime.now()\n",
        "backtest.py": "import random\nr = random.Random()\n",
        "j.py": "import asyncio\nasyncio.sleep(1)\n",
    }
    for rel, code in bad.items():
        root = tmp_path / ("bad_" + rel.replace(".", "_"))
        _w(root, rel, code)
        assert scan_clock(root), rel
    # docstring SQL-saat yakalanır, ama yalnız SQL anahtar sözcüğü varsa
    root = tmp_path / "doc"
    _w(root, "k.py", '"""SELECT x -- CURRENT_TIMESTAMP"""\n')
    assert scan_clock(root)
    root = tmp_path / "doc2"
    _w(root, "k.py", '"""CURRENT_TIMESTAMP yasak"""\n')
    assert scan_clock(root) == []
    # izinli dosyada izinli olmayan çağrı yine ihlal
    root = tmp_path / "perf"
    _w(root, "clock.py", "import time\nclass SystemClock:\n    def f(self): return time.perf_counter()\n")
    assert scan_clock(root)
