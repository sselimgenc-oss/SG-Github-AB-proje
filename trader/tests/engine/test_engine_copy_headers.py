"""08 §4.5: 1l3a kopya başlıkları ve kopya-dışı sızıntı yasakları."""
from __future__ import annotations

import ast
import datetime
import os
import re
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
ENGINE = "src/trader_engine"
COPIED = {"exchange/rules.py": "motor/canli/borsa/kurallar.py", "marketdata/rest_public.py": "motor/canli/paper_veri.py",
          "fileio.py": "motor/canli/durum.py", "exchange/binance_rest.py": "motor/canli/borsa/binance_futures.py"}
_SRC_NAME = "1l3" + "a"
_SRC_HOST = "ssel" + "imgenc"
CUT_NAMES = ["ESLEME", "tradfi", "boyutlandir", "Boyut", "canli_limitler", "paper_takvim", "TekrarKaynagi", "BinanceHata", "FapiIstemci"]
MOTOR_TEXT = ["motor." + x for x in ("canli", "backtest", "veri", "portfoy")]
MIN_DATE = datetime.date(2026, 11, 16)
H2 = re.compile(r"^# Kopya tarihi: (\d{4}-\d{2}-\d{2})   Kaynak commit: (\S+)")
H3 = re.compile(r"^# Çalışma zamanında kaynak depo import edilmez/mount edilmez\. Değişiklikler: \S.*")


def check_header(text: str, source: str) -> list[str]:
    v = []
    ls = text.splitlines()[:3]
    if len(ls) < 3:
        return ["header shorter than 3 lines"]
    if not (ls[0].startswith(f"# Kopyalandı: {_SRC_NAME}-proje/{source}") and "(kullanıcının kendi kodu; lisans engeli yok)" in ls[0]):
        v.append("line1")
    m = H2.match(ls[1])
    if not m:
        v.append("line2")
    else:
        try:
            if datetime.date.fromisoformat(m.group(1)) < MIN_DATE:
                v.append("date too early")
        except ValueError:
            v.append("bad date")
    if not H3.match(ls[2]):
        v.append("line3")
    return v


def _py(base: Path):
    for d, dirs, files in os.walk(base):
        dirs[:] = [x for x in dirs if x != "__pycache__"]
        for f in sorted(files):
            if f.endswith(".py"):
                yield Path(d) / f


def scan_leaks(root: Path) -> list[str]:
    v = []
    base = Path(root) / ENGINE
    if not base.exists():
        return v
    for p in _py(base):
        rel = str(p.relative_to(base))
        text = p.read_text(encoding="utf-8")
        if rel in COPIED:
            v += [f"{rel}: header {h}" for h in check_header(text, COPIED[rel])]
        for n in ast.walk(ast.parse(text)):       # başlık dışı sabit metin (docstring dahil)
            if isinstance(n, ast.Constant) and isinstance(n.value, str) and _SRC_NAME in n.value:
                v.append(f"{rel}:{n.lineno}: constant mentions source repo")
        for t in MOTOR_TEXT:
            if t in text:
                v.append(f"{rel}: {t}")
        if rel in COPIED:
            for name in CUT_NAMES:
                if (re.search(name, text, re.I) if name == "tradfi" else re.search(rf"\b{name}\b", text)):
                    v.append(f"{rel}: cut name {name}")
    for sub in ("src", "tests/engine", "config"):
        for d, dirs, files in os.walk(Path(root) / sub):
            dirs[:] = [x for x in dirs if x not in ("__pycache__",)]
            for f in files:
                if f.endswith((".py", ".json", ".toml")):
                    try:
                        t = (Path(d) / f).read_text(encoding="utf-8")
                    except UnicodeDecodeError:
                        continue
                    if _SRC_HOST in t:
                        v.append(f"{Path(d, f).relative_to(root)}: source repo path")
    return v


def test_real_tree_headers_and_leaks():
    assert scan_leaks(REPO) == []


def test_copied_files_exist_with_header():
    for rel in COPIED:
        assert (REPO / ENGINE / rel).exists(), rel


def _good(src):
    return (f"# Kopyalandı: {_SRC_NAME}-proje/{src} (kullanıcının kendi kodu; lisans engeli yok)\n"
            "# Kopya tarihi: 2026-11-16   Kaynak commit: 2dd2dce\n"
            "# Çalışma zamanında kaynak depo import edilmez/mount edilmez. Değişiklikler: x.\nx = 1\n")


def test_header_boundaries(tmp_path):
    base = tmp_path / ENGINE
    (base / "exchange").mkdir(parents=True)
    f = base / "exchange" / "rules.py"
    src = COPIED["exchange/rules.py"]
    f.write_text(_good(src))
    assert scan_leaks(tmp_path) == []
    f.write_text(_good("motor/yanlis.py"))
    assert scan_leaks(tmp_path)
    f.write_text(_good(src).replace("2026-11-16", "16.11.2026"))
    assert scan_leaks(tmp_path)
    f.write_text(_good(src).replace("2026-11-16", "2026-11-15"))
    assert scan_leaks(tmp_path)
    f.write_text(_good(src) + f"'''{_SRC_NAME} burada'''\n")
    assert scan_leaks(tmp_path)
    f.write_text(_good(src) + "import " + MOTOR_TEXT[0] + "\n")
    assert scan_leaks(tmp_path)
    f.write_text(_good(src) + "ESLEME = {}\n")
    assert scan_leaks(tmp_path)
    f.write_text(_good(src) + f"P = '/home/x/{_SRC_HOST}-oss'\n")
    assert scan_leaks(tmp_path)
    f.write_text(_good(src).replace("# Çalışma", "# Calisma"))
    assert scan_leaks(tmp_path)
