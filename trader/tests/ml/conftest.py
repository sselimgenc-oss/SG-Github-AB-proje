import pytest


@pytest.fixture(scope="session")
def candles():
    from trader_ml.fixture import synthetic_candles
    return synthetic_candles()


@pytest.fixture(scope="session")
def table(candles):
    from trader_ml.fixture import build_candidate_table
    return build_candidate_table(candles)
