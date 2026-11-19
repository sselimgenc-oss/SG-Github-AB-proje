"""Yapisal HOLDOUT kilidi: backtest modunda Engine.run_range kilitli donemle kesisen araligi, bar okumadan once reddeder."""
from __future__ import annotations

from datetime import datetime, timezone
from types import SimpleNamespace

import pytest

from trader_engine.engine import Engine
from trader_engine.holdout import BacktestArgError

UTC = timezone.utc


class _Touched(Exception):
    pass


class _FailingView:
    def __getattr__(self, name):
        raise _Touched(name)


def _engine(mode: str) -> Engine:
    e = object.__new__(Engine)
    e.cfg = SimpleNamespace(mode=mode)
    e.view = _FailingView()
    e.tf = "1h"
    e.step_tf = "1h"                       # DD-12 WP-11: karar adimi tf (tekli stratejide tf ile ayni)
    return e


def _d(y, m, d):
    return datetime(y, m, d, tzinfo=UTC)


def test_backtest_run_range_inside_holdout_raises_before_reading():
    with pytest.raises(BacktestArgError) as ei:
        _engine("backtest").run_range(_d(2026, 10, 1), _d(2026, 10, 2))
    assert ei.value.code == "holdout_locked"


def test_backtest_run_range_overlapping_edges_raises():
    for s, e in ((_d(2026, 4, 30), _d(2026, 5, 2)), (_d(2026, 10, 31), _d(2026, 11, 2))):
        with pytest.raises(BacktestArgError):
            _engine("backtest").run_range(s, e)


def test_backtest_run_range_exact_boundaries_pass_the_guard():
    # kilit gecilir -> ilk view erisimi (_Touched) gelir; holdout_locked degil
    for s, e in ((_d(2026, 4, 1), _d(2026, 5, 1)), (_d(2026, 11, 1), _d(2026, 11, 2))):
        with pytest.raises(_Touched):
            _engine("backtest").run_range(s, e)


def test_paper_mode_not_guarded():
    with pytest.raises(_Touched):
        _engine("paper").run_range(_d(2026, 10, 1), _d(2026, 10, 2))
