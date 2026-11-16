#!/usr/bin/env python3
"""Terfi kapisi betigi (ML-0c): egitim + kapi + Turkce rapor. Ornek:
    .venv/bin/python scripts/ml_gate.py --synthetic --out var/ml/synthetic
    .venv/bin/python scripts/ml_gate.py --candidates <19b.parquet> --out var/ml/run1 [--limits]
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from trader_ml.pipeline import main  # noqa: E402

if __name__ == "__main__":
    sys.exit(main())
