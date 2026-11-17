"""17 Kasim mentor karari: yalniz `legacy_compat`'ta iz suren stop guncellemesini bir bar geciktirme bayragi.
Varsayilan kapali; native/paper yolu degismez (native defter ozeti: test_engine_compat_equity.py)."""
from __future__ import annotations

import dataclasses
from datetime import timedelta

import numpy as np
import pytest

from tests.engine.test_engine_04_spec import A_HIGHS, A_LOWS, mkctx, mkpos
from trader_engine.backtest import BacktestArgError, build_parser, spec_from_args
from trader_engine.position_manager import ExitContext, evaluate_exit, trail_stop_value


def test_trail_lag_default_off_and_dataclass_field():
    ctx = mkctx(A_HIGHS, A_LOWS)
    assert ctx.trail_lag is False
    assert [f.name for f in dataclasses.fields(ExitContext)][-1] == "trail_lag"     # sona eklendi: konumsal kurucular bozulmaz


def test_trail_lag_off_is_unchanged_path_value():
    pos = mkpos()
    full = trail_stop_value(pos, mkctx(A_HIGHS, A_LOWS))
    off = trail_stop_value(pos, dataclasses.replace(mkctx(A_HIGHS, A_LOWS), trail_lag=False))
    assert full == off


def test_trail_lag_uses_previous_bar_value():
    pos = mkpos()
    for k in range(2, len(A_HIGHS) + 1):
        lagged = trail_stop_value(pos, dataclasses.replace(mkctx(A_HIGHS[:k], A_LOWS[:k]), trail_lag=True))
        prev = trail_stop_value(pos, mkctx(A_HIGHS[:k - 1], A_LOWS[:k - 1]))
        assert lagged == prev                                  # bir bar eski ATR/uc ile ayni yol degeri


def test_trail_lag_single_bar_returns_initial_stop_unarmed():
    pos = mkpos()
    stop, armed = trail_stop_value(pos, dataclasses.replace(mkctx([110.0], [100.0]), trail_lag=True))
    assert (stop, armed) == (pos.initial_stop, False)
    assert evaluate_exit(pos, dataclasses.replace(mkctx([110.0], [100.0]), trail_lag=True)).kind == "none"


def test_trail_lag_flag_requires_legacy_compat():
    ap = build_parser()
    base = ["--id", "x", "--period", "IS"]
    a = ap.parse_args(base + ["--fill-model", "native", "--compat-trail-lag"])
    with pytest.raises(BacktestArgError):
        spec_from_args(a, [])
    a = ap.parse_args(base + ["--fill-model", "legacy_compat", "--granularity", "15m", "--compat-trail-lag"])
    assert spec_from_args(a, []).compat_trail_lag is True
    for fm in (["--fill-model", "native"], ["--fill-model", "legacy_compat", "--granularity", "15m"]):
        assert spec_from_args(ap.parse_args(base + fm), []).compat_trail_lag is False     # varsayilan kapali
