"""CI duman betigi (scripts/ci_duman.py) ve is akisi baglantisi."""
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]


def test_duman_betigi_gecer():
    pytest.importorskip("pyarrow")
    r = subprocess.run([sys.executable, str(ROOT / "scripts" / "ci_duman.py")], capture_output=True, text=True, timeout=240, cwd=ROOT)
    assert r.returncode == 0, r.stdout + r.stderr
    assert "DUMAN GECTI" in r.stdout


def test_is_akisinda_duman_isi_var():
    wf = (ROOT.parent / ".github" / "workflows" / "tests.yml").read_text(encoding="utf-8")
    assert "  duman:" in wf and "python scripts/ci_duman.py" in wf and "  tests:" in wf
