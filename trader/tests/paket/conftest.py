"""Paket testleri: trader/paket yolunu ekler (ortak_ogrenme burada; trader_core src/ altinda, pyproject pythonpath)."""
import sys
from pathlib import Path

_PAKET = Path(__file__).resolve().parents[2] / "paket"
if str(_PAKET) not in sys.path:
    sys.path.insert(0, str(_PAKET))
