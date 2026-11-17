"""Statik kilit: gercek piyasa verisi okuyan test dosyalari kilitli donemde (2026-05-01 -> 2026-11-01) tarih iceremez."""
from __future__ import annotations

import ast
import re
from pathlib import Path

TESTS = Path(__file__).resolve().parents[1]
BAD_MONTHS = range(5, 11)
STR_RE = re.compile(r"2026-(0[5-9]|10)-\d\d|2026(0[5-9]|10)\d\d")
DT_NAMES = {"datetime", "dt"}
# var/history: "var/history", Path / "var" / "history", ("var", "history") ve benzeri yazimlar
_HISTORY_RE = re.compile(r"""var["']?\s*[/,]\s*["']?history""")
# {dosya (tests/ altinda goreli): gerekce}; baslangicta bos.
ALLOWED: dict[str, str] = {}


def is_real_data_source(text: str, tree: ast.AST) -> bool:
    if "binance" in text and "user_data" in text:        # eski konum (user_data/data/binance/futures)
        return True
    if _HISTORY_RE.search(text):                         # var/history (feather gecmis veri)
        return True
    for n in ast.walk(tree):
        if isinstance(n, ast.Call) and getattr(n.func, "id", getattr(n.func, "attr", None)) == "HistoricalSource" and n.args:
            a = n.args[0]
            if not (isinstance(a, ast.Name) and "tmp" in a.id.lower()) and "tmp" not in ast.unparse(a).lower() and "hist" not in ast.unparse(a).lower():
                return True
    return False


def violations(text: str) -> list[str]:
    tree = ast.parse(text)
    if not is_real_data_source(text, tree):
        return []
    out = []
    for n in ast.walk(tree):
        if isinstance(n, ast.Call) and isinstance(n.func, ast.Name) and n.func.id in DT_NAMES and len(n.args) >= 2:
            y, m = n.args[0], n.args[1]
            if all(isinstance(x, ast.Constant) and isinstance(x.value, int) for x in (y, m)) and y.value == 2026 and m.value in BAD_MONTHS:
                out.append(f"line {n.lineno}: {n.func.id}(2026, {m.value}, ...)")
        elif isinstance(n, ast.Constant) and isinstance(n.value, str) and STR_RE.search(n.value):
            out.append(f"line {n.lineno}: string {n.value[:40]!r}")
    return out


def test_self_flags_synthetic_snippet():
    snippet = 'from datetime import datetime\nDATA = "user_data/data/binance/futures"\nx = datetime(2026, 10, 1)\n'
    assert violations(snippet)
    assert violations('DATA = "user_data/data/binance"\ns = "2026-07-15"\n')
    assert violations('DATA = "user_data/data/binance"\ns = "20260801"\n')
    assert not violations('DATA = "user_data/data/binance"\nx = dt(2026, 3, 1)\ns = "2026-04-30"\n')
    assert not violations("from datetime import datetime\nx = datetime(2026, 10, 1)\n")   # gercek veri yok
    # var/history (yeni konum): uc yazim bicimi de gercek-veri kaynagi sayilir
    assert violations('DATA = "var/history"\ns = "2026-07-15"\n')
    assert violations('DATA = ROOT / "var" / "history"\ns = "20260801"\n')
    assert violations('DATA = os.path.join("var", "history")\nx = dt(2026, 6, 1)\n')
    assert not violations('DATA = "var/history"\nx = dt(2026, 3, 1)\ns = "2026-04-30"\n')


def test_no_holdout_dates_in_real_data_tests():
    bad = {}
    for p in sorted(TESTS.rglob("*.py")):
        rel = p.relative_to(TESTS).as_posix()
        if p.name == Path(__file__).name or rel in ALLOWED:
            continue
        v = violations(p.read_text(encoding="utf-8"))
        if v:
            bad[rel] = v
    assert not bad, f"kilitli donem tarihi (gercek-veri testi): {bad}"
