import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))


@pytest.fixture(scope="session")
def candles():
    from trader_ml.fixture import synthetic_candles
    return synthetic_candles()


@pytest.fixture(scope="session")
def table(candles):
    from trader_ml.fixture import build_candidate_table
    return build_candidate_table(candles)
