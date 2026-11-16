"""07 gerçekleme dumanı: kopyalar yalnız stdlib + trader_engine çekirdeğiyle içe aktarılır, ağır modül yüklemez."""
import json
import subprocess
import sys
from pathlib import Path

SRC = Path(__file__).resolve().parents[2] / "src"


def test_copied_modules_import_light():
    code = ("import sys, json; sys.path.insert(0, %r)\n"
            "import trader_engine.fileio, trader_engine.exchange.rules, trader_engine.marketdata.rest_public\n"
            "print(json.dumps(sorted(m for m in sys.modules if m.split('.')[0] in {'pandas','numpy','requests','pyarrow'})))"
            % str(SRC))
    out = subprocess.run([sys.executable, "-I", "-c", code], capture_output=True, text=True, timeout=30)
    assert out.returncode == 0, out.stderr
    assert json.loads(out.stdout) == []
