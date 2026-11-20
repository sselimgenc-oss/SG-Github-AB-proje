"""Denetim (20.11) mutasyon sagkalanlari: exit_modes bayrak varsayilanlari, partial_due, reached_r, _best NaN suzgeci,
tighter EPS kenari, partial_qty sinirlari, parse_section sinirlari."""
from __future__ import annotations

import math

import pytest

from trader_core import exit_modes as XM
from trader_core.exit_modes import EPS, ExitModeError, ExitModes

NAN = float("nan")


# ---- resolve: ders bayraklari
def test_lesson_flags_missing_key_and_zero_do_not_enable():
    assert XM.resolve(None, "T1", "1h", {"baska": 1}) is None
    assert XM.resolve(None, "T1", "1h", {XM.PARAM_BREAKEVEN: 0, XM.PARAM_PARTIAL: 0}) is None
    m = XM.resolve(None, "T1", "1h", {XM.PARAM_PARTIAL: 1})
    assert m is not None and m.partial and not m.breakeven          # eksik breakeven anahtari varsayilan 0
    m = XM.resolve(None, "T1", "1h", {XM.PARAM_BREAKEVEN: 1})
    assert m is not None and m.breakeven and not m.partial          # eksik partial anahtari varsayilan 0


def test_lesson_flags_only_for_t1_and_never_override_config():
    assert XM.resolve(None, "T2", "1h", {XM.PARAM_BREAKEVEN: 1, XM.PARAM_PARTIAL: 1}) is None
    cfg = XM.build_config({"default": {"breakeven": {"trigger_r": 2.0}}})
    m = XM.resolve(cfg, "T1", "1h", {XM.PARAM_BREAKEVEN: 1})
    assert m.be_trigger_r == 2.0                                    # yapilandirilmis kip bayrakla ezilmez
    m = XM.resolve(cfg, "T1", "1h", {XM.PARAM_BREAKEVEN: 0})
    assert m.be_trigger_r == 2.0
    m = XM.resolve(cfg, "T1", "1h", {XM.PARAM_PARTIAL: 1})
    assert m.be_trigger_r == 2.0 and m.partial                      # partial yapilandirmada kapali: bayrak acar


def test_any_property_single_mode():
    assert ExitModes(be_trigger_r=1.0).any and ExitModes(pt_trigger_r=1.5).any
    assert not ExitModes().any


# ---- partial_due / reached_r
def test_partial_due_requires_modes_and_partial_on():
    assert XM.partial_due("long", 100.0, 90.0, 200.0, None) is False
    be_only = ExitModes(be_trigger_r=1.0)
    assert XM.partial_due("long", 100.0, 90.0, 200.0, be_only) is False
    assert XM.partial_due("long", 100.0, 90.0, 200.0, ExitModes(pt_trigger_r=1.5)) is True


def test_reached_r_none_best_and_zero_distance_false():
    assert XM.reached_r("long", 100.0, 90.0, None, 1.0) is False
    assert XM.reached_r("short", 100.0, 110.0, None, 1.0) is False
    assert XM.reached_r("long", 100.0, 100.0, 105.0, 1.0) is False        # r == 0
    assert XM.reached_r("short", 100.0, 100.0, 95.0, 1.0) is False
    assert XM.reached_r("long", 100.0, 99.5, 100.5, 1.0) is True           # kucuk ama pozitif r


def test_reached_r_eps_edges_long_and_short():
    t = 100.0 + 1.0 * 10.0 - EPS
    assert XM.reached_r("long", 100.0, 90.0, 110.0, 1.0)
    assert XM.reached_r("long", 100.0, 90.0, t, 1.0)                        # tam EPS kenari dahil
    assert XM.reached_r("long", 100.0, 90.0, 110.0 - EPS / 2, 1.0)
    assert not XM.reached_r("long", 100.0, 90.0, 110.0 - 3 * EPS, 1.0)
    ts = 100.0 - 1.0 * 10.0 + EPS
    assert XM.reached_r("short", 100.0, 110.0, 90.0, 1.0)
    assert XM.reached_r("short", 100.0, 110.0, ts, 1.0)
    assert XM.reached_r("short", 100.0, 110.0, 90.0 + EPS / 2, 1.0)
    assert not XM.reached_r("short", 100.0, 110.0, 90.0 + 3 * EPS, 1.0)


# ---- _best NaN suzgeci
def test_best_extreme_filters_nan_and_none():
    assert XM.best_extreme("long", [NAN, 5.0, 3.0], [1.0]) == 5.0
    assert XM.best_extreme("long", [5.0, NAN], [1.0]) == 5.0
    assert XM.best_extreme("long", [None, 4.0, NAN], [1.0]) == 4.0
    assert XM.best_extreme("short", [9.0], [NAN, 2.0, 3.0]) == 2.0
    assert XM.best_extreme("short", [9.0], [2.0, NAN]) == 2.0
    assert XM.best_extreme("short", [9.0], [None, 3.0, NAN]) == 3.0
    assert XM.best_extreme("long", [NAN, None], [1.0]) is None
    assert XM.best_extreme("short", [1.0], [NAN]) is None
    assert XM.best_extreme("long", [], []) is None


# ---- tighter
def test_tighter_eps_band_long_and_short():
    cur = 100.0
    assert not XM.tighter("long", cur + EPS, cur)                           # tam esitlik/EPS kenari: sikilasma degil
    assert not XM.tighter("long", cur + EPS / 2, cur)
    assert not XM.tighter("long", cur - EPS / 2, cur)
    assert not XM.tighter("long", cur, cur)
    assert XM.tighter("long", cur + 3 * EPS, cur)
    assert not XM.tighter("short", cur - EPS, cur)
    assert not XM.tighter("short", cur - EPS / 2, cur)
    assert not XM.tighter("short", cur + EPS / 2, cur)
    assert not XM.tighter("short", cur, cur)
    assert XM.tighter("short", cur - 3 * EPS, cur)


# ---- partial_qty
def test_partial_qty_invalid_inputs_none():
    assert XM.partial_qty(0.0, 0.5, 1.0, 0.0, 0.0, 100.0) is None
    assert XM.partial_qty(10.0, 0.5, 0.0, 0.0, 0.0, 100.0) is None          # step 0: bolme hatasi degil None
    assert XM.partial_qty(-1.0, 0.5, 1.0, 0.0, 0.0, 100.0) is None
    assert XM.partial_qty(0.5, 0.5, 1.0, 0.0, 0.0, 100.0) is None           # q == 0


def test_partial_qty_min_qty_equality_and_tolerance():
    assert XM.partial_qty(10.0, 0.5, 1.0, 5.0, 0.0, 0.0) == 5.0             # q == rest == min_qty: izinli
    assert XM.partial_qty(10.0, 0.5, 1.0, 5.0 + 5e-13, 0.0, 0.0) == 5.0     # 1e-12 payi icinde
    assert XM.partial_qty(10.0, 0.5, 1.0, 5.0 + 1.5e-12, 0.0, 0.0) is None  # payin disinda
    assert XM.partial_qty(10.0, 0.5, 1.0, 5.5, 0.0, 0.0) is None


def test_partial_qty_rest_and_q_below_min_isolated():
    assert XM.partial_qty(10.0, 0.9, 1.0, 2.0, 0.0, 0.0) is None            # q=9 yeterli, rest=1 < 2
    assert XM.partial_qty(10.0, 0.1, 1.0, 2.0, 0.0, 0.0) is None            # q=1 < 2, rest=9 yeterli
    assert XM.partial_qty(10.0, 0.5, 1.0, 2.0, 0.0, 0.0) == 5.0


def test_partial_qty_min_notional_edges():
    assert XM.partial_qty(10.0, 0.5, 1.0, 0.0, 50.0, 10.0) == 5.0           # q*p == rest*p == min_notional: izinli
    assert XM.partial_qty(10.0, 0.2, 1.0, 0.0, 20.0, 10.0) == 2.0           # q*p == 20 tam esit, rest buyuk
    assert XM.partial_qty(10.0, 0.8, 1.0, 0.0, 20.0, 10.0) == 8.0           # rest*p == 20 tam esit, q buyuk
    assert XM.partial_qty(10.0, 0.2, 1.0, 0.0, 30.0, 10.0) is None          # yalniz q dusuk
    assert XM.partial_qty(10.0, 0.8, 1.0, 0.0, 30.0, 10.0) is None          # yalniz rest dusuk
    assert XM.partial_qty(10.0, 0.5, 1.0, 0.0, 50.5, 10.0) is None
    assert XM.partial_qty(10.0, 0.5, 1.0, 0.0, 50.0, 0.0) == 5.0            # fiyat 0: notional denetimi atlanir
    assert XM.partial_qty(10.0, 0.5, 1.0, 0.0, 50.0, None) == 5.0           # fiyat yok: atlanir
    assert XM.partial_qty(10.0, 0.5, 1.0, 0.0, 3.0, 0.5) is None            # kucuk (0<p<1) fiyatta denetim calisir
    assert XM.partial_qty(10.0, 0.5, 1.0, 0.0, 2.0, 0.5) == 5.0


def test_partial_qty_float_rounding_fudge():
    qty, frac, step = 1.4, 0.5, 0.1                                         # 1.4*0.5/0.1 = 6.999999999999999 -> adim 7
    assert math.floor(qty * frac / step) == 6
    q = XM.partial_qty(qty, frac, step, 0.0, 0.0, 0.0)
    assert q == pytest.approx(0.7, abs=1e-9)


# ---- parse_section / sinirlar
def test_parse_section_bounds_inclusive_and_type_guard():
    lo, hi = XM.TRIGGER_R_BOUNDS
    assert XM.parse_section("breakeven", {"trigger_r": lo})["trigger_r"] == lo
    assert XM.parse_section("breakeven", {"trigger_r": hi})["trigger_r"] == hi
    assert XM.parse_section("partial", {"frac": XM.FRAC_BOUNDS[0]})["frac"] == XM.FRAC_BOUNDS[0]
    assert XM.parse_section("partial", {"frac": XM.FRAC_BOUNDS[1]})["frac"] == XM.FRAC_BOUNDS[1]
    assert XM.parse_section("breakeven", {"offset_bps": 0.0})["offset_bps"] == 0.0
    assert XM.parse_section("breakeven", {"offset_bps": 100.0})["offset_bps"] == 100.0
    for bad in ({"trigger_r": lo - 0.01}, {"trigger_r": hi + 0.01}, {"trigger_r": "1"}, {"trigger_r": True},
                {"trigger_r": NAN}, {"trigger_r": math.inf}, {"offset_bps": 100.01}):
        with pytest.raises(ExitModeError):
            XM.parse_section("breakeven", bad)
