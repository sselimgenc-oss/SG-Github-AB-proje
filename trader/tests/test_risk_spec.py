"""Independent spec-based tests for trader_core.risk  (spec v2, 16 Kasim 2026).

Written ONLY from docs/risk-kilidi-spec.md (not from the implementation).

Default config: max_trade_risk 2%, target 1.4%, fee 0.05% + slippage 0.05%
(=> 0.001 per side), daily_max_loss 5% (of day-start equity), max_open_risk 6%,
max_same_dir_risk 4%, leverage 3..5, mmr 0.4%, liq_safety_factor 1.5,
max_notional_ratio 1.0.

Because the daily budget (5% of day-start) is tighter than the total open-risk
cap (6%), rule 8 can only be isolated with a custom (tighter) config; tests
below do that explicitly.
"""
import dataclasses
import inspect
import math
import numbers
import random
from fractions import Fraction
from types import SimpleNamespace

import pytest

import trader_core.risk as risk
from trader_core.risk import (
    HARD_LIMITS,
    LOCKED_CFG,
    AccountState,
    Candidate,
    Decision,
    OpenPosition,
    RiskConfig,
    SizeResult,
    check_entry,
    liquidation_price,
    loss_at_stop,
    size_position,
)

BTC = "BTC/USDT:USDT"
ETH = "ETH/USDT:USDT"
SOL = "SOL/USDT:USDT"
XRP = "XRP/USDT:USDT"
CFG = RiskConfig()
REL = 1e-9
NAN = float("nan")
INF = float("inf")


# --------------------------------------------------------------------------
# helpers
# --------------------------------------------------------------------------
def mk_state(equity=1000.0, day_start=1000.0, open_positions=()):
    return AccountState(
        equity=equity,
        day_start_equity=day_start,
        open_positions=list(open_positions),
    )


def mk_cand(pair=BTC, side="long", entry=60000.0, stop=59100.0, leverage=5, qty_step=None, min_notional=0.0):
    return Candidate(
        pair=pair,
        side=side,
        entry=entry,
        stop=stop,
        leverage=leverage,
        qty_step=qty_step,
        min_notional=min_notional,
    )


def pos(pair, side, risk_amount, margin=0.0):
    return OpenPosition(pair=pair, side=side, risk_amount=risk_amount, margin=margin)


def assert_denied(dec):
    assert isinstance(dec, Decision)
    assert dec.allowed is False
    assert isinstance(dec.reason, str) and dec.reason.strip() != ""


def reason_of(state, cand, cfg=CFG):
    dec = check_entry(state, cand, cfg)
    assert_denied(dec)
    return dec.reason


def is_allowed(state, cand, cfg=CFG):
    dec = check_entry(state, cand, cfg)
    assert isinstance(dec, Decision)
    return dec.allowed is True


# Candidate used where the position is small and every rule other than the
# targeted one passes: ETH 100 -> 90 long 5x.
#   per-unit loss = 10 + (100 + 90)*0.001 = 10.19 ; qty = 14/10.19 ~= 1.3739
#   notional ~= 137.39 (<< 1000, cap inactive) ; margin ~= 27.5
#   liq (5x long) = 80.4 -> dist 19.6 >= 1.5*10 = 15  OK
def eth_cand(**kw):
    base = dict(pair=ETH, side="long", entry=100.0, stop=90.0, leverage=5)
    base.update(kw)
    return mk_cand(**base)


# --------------------------------------------------------------------------
# RiskConfig / HARD_LIMITS / LOCKED_CFG
# --------------------------------------------------------------------------
def test_riskconfig_defaults():
    c = RiskConfig()
    assert c.max_trade_risk == 0.02
    assert c.target_trade_risk == 0.014
    assert c.fee_rate == 0.0005
    assert c.slippage_rate == 0.0005
    assert c.daily_max_loss == 0.05
    assert c.max_open_risk == 0.06
    assert c.max_same_dir_risk == 0.04
    assert c.min_leverage == 3
    assert c.max_leverage == 5
    assert c.maint_margin_rate == 0.004
    assert c.liq_safety_factor == 1.5
    assert c.max_notional_ratio == 1.0


def test_riskconfig_is_frozen():
    c = RiskConfig()
    with pytest.raises(dataclasses.FrozenInstanceError):
        c.max_trade_risk = 0.5


def test_hard_limits_values():
    assert isinstance(HARD_LIMITS, dict)
    assert HARD_LIMITS["max_trade_risk"] == 0.02
    assert HARD_LIMITS["target_trade_risk"] == 0.014
    assert HARD_LIMITS["daily_max_loss"] == 0.05
    assert HARD_LIMITS["max_open_risk"] == 0.06
    assert HARD_LIMITS["max_same_dir_risk"] == 0.04
    assert HARD_LIMITS["max_leverage"] == 5
    assert HARD_LIMITS["min_leverage"] == 1
    assert HARD_LIMITS["max_notional_ratio"] == 1.0


def test_locked_cfg_equals_defaults():
    assert isinstance(LOCKED_CFG, RiskConfig)
    assert LOCKED_CFG == RiskConfig()
    for f in dataclasses.fields(RiskConfig):
        assert getattr(LOCKED_CFG, f.name) == getattr(RiskConfig(), f.name)


def test_check_entry_default_cfg_is_locked_cfg():
    default = inspect.signature(check_entry).parameters["cfg"].default
    assert default is LOCKED_CFG or default == LOCKED_CFG
    # behaviour: omitted cfg == explicit LOCKED_CFG
    st, c = mk_state(), mk_cand()
    a, b = check_entry(st, c), check_entry(st, c, LOCKED_CFG)
    assert a.allowed is b.allowed is True
    assert a.size == b.size
    # and an unsafe candidate is denied by default as well
    assert_denied(check_entry(mk_state(), mk_cand(leverage=10)))


@pytest.mark.parametrize(
    "kwargs",
    [
        {"max_trade_risk": 0.021},  # > 0.02
        {"max_trade_risk": 0.5},
        {"target_trade_risk": 0.015},  # > 0.014 (still <= max_trade_risk 0.02)
        {"target_trade_risk": 0.02},
        {"daily_max_loss": 0.051},  # > 0.05
        {"daily_max_loss": 0.5},
        {"max_open_risk": 0.061},  # > 0.06
        {"max_open_risk": 1.0},
        {"max_same_dir_risk": 0.041},  # > 0.04
        {"max_same_dir_risk": 0.5},
        {"max_leverage": 6},  # > 5
        {"max_leverage": 10},
        {"min_leverage": 0},  # < 1
        {"min_leverage": -1},
        {"max_notional_ratio": 1.01},  # > 1.0
        {"max_notional_ratio": 3.0},
    ],
)
def test_hard_limits_looser_raises(kwargs):
    with pytest.raises(ValueError):
        RiskConfig(**kwargs)


@pytest.mark.parametrize(
    "kwargs",
    [
        {"max_trade_risk": 0.015},  # target 0.014 <= 0.015
        {"max_trade_risk": 0.014},
        {"target_trade_risk": 0.01},
        {"daily_max_loss": 0.03},
        {"max_open_risk": 0.05},
        {"max_same_dir_risk": 0.03},
        {"max_leverage": 4},  # min 3 <= 4
        {"max_leverage": 3},
        {"min_leverage": 1},  # >= 1 allowed
        {"min_leverage": 2},
        {"min_leverage": 5},  # == max_leverage 5
        {"max_notional_ratio": 0.5},
        {"fee_rate": 0.001, "slippage_rate": 0.002},
        {"liq_safety_factor": 2.0},
    ],
)
def test_tighter_configs_allowed(kwargs):
    c = RiskConfig(**kwargs)
    for k, v in kwargs.items():
        assert getattr(c, k) == v


def test_exactly_at_hard_limits_allowed():
    c = RiskConfig(
        max_trade_risk=0.02,
        target_trade_risk=0.014,
        daily_max_loss=0.05,
        max_open_risk=0.06,
        max_same_dir_risk=0.04,
        min_leverage=1,
        max_leverage=5,
        max_notional_ratio=1.0,
    )
    assert c.max_leverage == 5


@pytest.mark.parametrize(
    "kwargs",
    [
        {"max_trade_risk": -0.01},
        {"target_trade_risk": -0.01},
        {"fee_rate": -0.0005},
        {"slippage_rate": -0.0005},
        {"daily_max_loss": -0.05},
        {"max_open_risk": -0.06},
        {"max_same_dir_risk": -0.04},
        {"maint_margin_rate": -0.004},
        {"liq_safety_factor": -1.5},
        {"max_trade_risk": NAN},
        {"target_trade_risk": NAN},
        {"fee_rate": NAN},
        {"slippage_rate": INF},
        {"daily_max_loss": INF},
        {"max_open_risk": NAN},
        {"max_same_dir_risk": INF},
        {"maint_margin_rate": NAN},
        {"liq_safety_factor": INF},
        {"max_notional_ratio": NAN},
        # target > max (default target 0.014 > max 0.01)
        {"max_trade_risk": 0.01},
        # min_leverage > max_leverage
        {"min_leverage": 6, "max_leverage": 5},
        {"min_leverage": 4, "max_leverage": 3},
        # mmr >= 1
        {"maint_margin_rate": 1.0},
        {"maint_margin_rate": 1.5},
    ],
)
def test_riskconfig_invalid_raises_valueerror(kwargs):
    with pytest.raises(ValueError):
        RiskConfig(**kwargs)


# --------------------------------------------------------------------------
# liquidation_price
# --------------------------------------------------------------------------
def test_liq_long_5x():
    # 100 * (1 - 1/5 + 0.004) = 100 * 0.804 = 80.4
    assert liquidation_price(100.0, "long", 5, 0.004) == pytest.approx(80.4, rel=REL)


def test_liq_short_5x():
    # 100 * (1 + 1/5 - 0.004) = 100 * 1.196 = 119.6
    assert liquidation_price(100.0, "short", 5, 0.004) == pytest.approx(119.6, rel=REL)


def test_liq_btc_levels():
    # 60000 * 0.804 = 48240 ; 60000 * 1.196 = 71760
    assert liquidation_price(60000.0, "long", 5, 0.004) == pytest.approx(48240.0, rel=REL)
    assert liquidation_price(60000.0, "short", 5, 0.004) == pytest.approx(71760.0, rel=REL)


def test_liq_3x():
    # long: 100 * (1 - 1/3 + 0.004) = 67.0666667 ; short: 100 * (1 + 1/3 - 0.004) = 132.9333333
    assert liquidation_price(100.0, "long", 3, 0.004) == pytest.approx(67.0666667, rel=1e-7)
    assert liquidation_price(100.0, "short", 3, 0.004) == pytest.approx(132.9333333, rel=1e-7)


def test_liq_zero_mmr():
    # mmr = 0, L = 4: long 200*(1-0.25)=150 ; short 200*(1+0.25)=250
    assert liquidation_price(200.0, "long", 4, 0.0) == pytest.approx(150.0, rel=REL)
    assert liquidation_price(200.0, "short", 4, 0.0) == pytest.approx(250.0, rel=REL)


def test_liq_sides_on_correct_side_of_entry():
    assert liquidation_price(100.0, "long", 5, 0.004) < 100.0
    assert liquidation_price(100.0, "short", 5, 0.004) > 100.0


# --------------------------------------------------------------------------
# loss_at_stop
# --------------------------------------------------------------------------
def test_loss_at_stop_long():
    # qty 2, entry 100, stop 95, cost 0.001/side
    # price loss 2*5 = 10 ; entry cost 2*100*0.001 = 0.2 ; stop cost 2*95*0.001 = 0.19 -> 10.39
    assert loss_at_stop(2.0, 100.0, 95.0, CFG) == pytest.approx(10.39, rel=REL)


def test_loss_at_stop_short_uses_abs():
    # qty 1, entry 100, stop 105: 5 + 0.1 + 0.105 = 5.205
    assert loss_at_stop(1.0, 100.0, 105.0, CFG) == pytest.approx(5.205, rel=REL)


def test_loss_at_stop_custom_costs():
    cfg = RiskConfig(fee_rate=0.001, slippage_rate=0.002)  # 0.003 per side
    # qty 1, entry 100, stop 90: 10 + 100*0.003 + 90*0.003 = 10.57
    assert loss_at_stop(1.0, 100.0, 90.0, cfg) == pytest.approx(10.57, rel=REL)


def test_loss_at_stop_btc_unit():
    # qty 1, 60000 -> 59100: 900 + 60 + 59.1 = 1019.1
    assert loss_at_stop(1.0, 60000.0, 59100.0, CFG) == pytest.approx(1019.1, rel=REL)


def test_loss_at_stop_linear_in_qty():
    a = loss_at_stop(1.0, 100.0, 95.0, CFG)
    b = loss_at_stop(3.0, 100.0, 95.0, CFG)
    assert b == pytest.approx(3 * a, rel=REL)


# --------------------------------------------------------------------------
# size_position
# --------------------------------------------------------------------------
def test_size_realistic_long_btc():
    # equity 1000, entry 60000, stop 59100, lev 5
    # per-unit loss = 900 + (60000 + 59100)*0.001 = 1019.1 ; target 14
    # qty_risk = 14/1019.1 ~= 0.0137376 ; qty_cap = 1000/60000 = 0.016667 (inactive)
    # notional = 840000/1019.1 ~= 824.257 ; margin ~= 164.851
    r = size_position(1000.0, 60000.0, 59100.0, "long", 5, CFG)
    assert isinstance(r, SizeResult)
    assert r.qty == pytest.approx(14 / 1019.1, rel=1e-6)
    assert r.notional == pytest.approx(840000 / 1019.1, rel=1e-6)
    assert r.margin == pytest.approx(r.notional / 5, rel=REL)
    assert r.risk_amount == pytest.approx(14.0, rel=1e-6)
    assert r.risk_amount <= 0.02 * 1000.0
    assert r.risk_amount == pytest.approx(loss_at_stop(r.qty, 60000.0, 59100.0, CFG), rel=REL)


def test_size_realistic_short_btc():
    # entry 60000, stop 60900: 900 + 120.9 = 1020.9 ; qty = 14/1020.9
    r = size_position(1000.0, 60000.0, 60900.0, "short", 5, CFG)
    assert r.qty == pytest.approx(14 / 1020.9, rel=1e-6)
    assert r.notional == pytest.approx(840000 / 1020.9, rel=1e-6)
    assert r.margin == pytest.approx(r.notional / 5, rel=REL)
    assert r.risk_amount == pytest.approx(14.0, rel=1e-6)


def test_size_wide_stop_unaffected_by_notional_cap():
    # entry 100, stop 90: per-unit 10.19 ; qty = 14/10.19 = 1.37390 ; notional 137.39 << 1000
    # cap inactive -> risk still exactly the 1.4% target
    r = size_position(1000.0, 100.0, 90.0, "long", 5, CFG)
    assert r.qty == pytest.approx(14 / 10.19, rel=1e-6)
    assert r.notional == pytest.approx(1400 / 10.19, rel=1e-6)
    assert r.risk_amount == pytest.approx(14.0, rel=1e-6)


def test_size_tight_stop_notional_cap_binds():
    # equity 1000, entry 100, stop 99.7 (0.3%), 5x
    # per-unit = 0.3 + (100 + 99.7)*0.001 = 0.4997
    # qty_risk = 14/0.4997 = 28.017 -> notional 2801.7 > 1000 ; qty_cap = 1000/100 = 10
    # qty = 10 -> notional 1000, risk = 10*0.4997 = 4.997 (< 14), margin = 1000/5 = 200
    r = size_position(1000.0, 100.0, 99.7, "long", 5, CFG)
    assert r.qty == pytest.approx(10.0, rel=1e-9)
    assert r.notional <= 1000.0 * (1 + REL)
    assert r.notional == pytest.approx(1000.0, rel=1e-9)
    assert r.risk_amount == pytest.approx(4.997, rel=1e-9)
    assert r.risk_amount < 14.0
    assert r.margin == pytest.approx(200.0, rel=1e-9)


def test_size_very_tight_stop_notional_cap_binds():
    # entry 100, stop 99.9 (0.1%): per-unit = 0.1 + 0.1999 = 0.2999
    # qty_risk = 14/0.2999 = 46.68 ; cap qty = 10 -> risk = 10*0.2999 = 2.999
    r = size_position(1000.0, 100.0, 99.9, "long", 5, CFG)
    assert r.notional == pytest.approx(1000.0, rel=1e-9)
    assert r.risk_amount == pytest.approx(2.999, rel=1e-9)


def test_size_tight_stop_short_cap():
    # entry 100, stop 100.3: per-unit = 0.3 + (100 + 100.3)*0.001 = 0.5003 ; cap qty 10 -> risk 5.003
    r = size_position(1000.0, 100.0, 100.3, "short", 5, CFG)
    assert r.notional == pytest.approx(1000.0, rel=1e-9)
    assert r.risk_amount == pytest.approx(5.003, rel=1e-9)


def test_size_btc_tight_stop_cap():
    # entry 60000, stop 59994: per-unit = 6 + (60000+59994)*0.001 = 125.994
    # qty_risk = 0.1111 (notional 6667) ; cap qty = 1000/60000 = 0.0166667 -> notional 1000
    # risk = 0.0166667*125.994 = 2.0999 ; margin at 5x = 200 (<= equity: no ValueError any more)
    r = size_position(1000.0, 60000.0, 59994.0, "long", 5, CFG)
    assert r.notional == pytest.approx(1000.0, rel=1e-9)
    assert r.risk_amount == pytest.approx(1000.0 / 60000.0 * 125.994, rel=1e-9)
    assert r.margin == pytest.approx(200.0, rel=1e-9)


def test_size_custom_notional_ratio():
    cfg = RiskConfig(max_notional_ratio=0.5)
    # entry 100, stop 99.7: cap qty = 0.5*1000/100 = 5 -> notional 500, risk = 5*0.4997 = 2.4985
    r = size_position(1000.0, 100.0, 99.7, "long", 5, cfg)
    assert r.notional == pytest.approx(500.0, rel=1e-9)
    assert r.risk_amount == pytest.approx(2.4985, rel=1e-9)


def test_size_cap_scales_with_equity():
    # equity 2000, entry 100, stop 99.7: cap qty = 20, notional 2000, risk = 20*0.4997 = 9.994
    r = size_position(2000.0, 100.0, 99.7, "long", 5, CFG)
    assert r.notional == pytest.approx(2000.0, rel=1e-9)
    assert r.risk_amount == pytest.approx(9.994, rel=1e-9)


def test_size_margin_over_equity_rejected_only_with_sub_unit_leverage():
    # notional <= equity, so margin = notional/L <= equity for L >= 1.
    # With L = 0.5 (outside any valid config) margin = 1000/0.5 = 2000 > 1000 -> ValueError
    with pytest.raises(ValueError):
        size_position(1000.0, 100.0, 99.7, "long", 0.5, CFG)


def test_size_leverage_only_changes_margin():
    a = size_position(1000.0, 60000.0, 59100.0, "long", 3, CFG)
    b = size_position(1000.0, 60000.0, 59100.0, "long", 5, CFG)
    assert a.qty == pytest.approx(b.qty, rel=REL)
    assert a.margin == pytest.approx(a.notional / 3, rel=REL)
    assert b.margin == pytest.approx(b.notional / 5, rel=REL)
    assert a.margin / b.margin == pytest.approx(5 / 3, rel=1e-6)


def test_size_scales_with_equity():
    a = size_position(1000.0, 60000.0, 59100.0, "long", 5, CFG)
    b = size_position(2000.0, 60000.0, 59100.0, "long", 5, CFG)
    assert b.qty == pytest.approx(2 * a.qty, rel=1e-6)
    assert b.risk_amount == pytest.approx(28.0, rel=1e-6)  # 0.014*2000


def test_size_custom_target():
    cfg = RiskConfig(target_trade_risk=0.01)  # 10 on equity 1000
    # entry 100 stop 90: per-unit 10.19 ; qty = 10/10.19
    r = size_position(1000.0, 100.0, 90.0, "long", 5, cfg)
    assert r.qty == pytest.approx(10 / 10.19, rel=1e-6)
    assert r.risk_amount == pytest.approx(10.0, rel=1e-6)


# ---- qty_step: floor rounding ---------------------------------------------
def test_size_step_floor_hand_case():
    # entry 100, stop 90 ; unrounded qty = 14/10.19 = 1.373896
    # step 0.1 -> floor(13.73) = 13 -> qty 1.3 ; notional 130 ; risk 1.3*10.19 = 13.247 ; margin 26
    r = size_position(1000.0, 100.0, 90.0, "long", 5, CFG, qty_step=0.1)
    assert r.qty == pytest.approx(1.3, rel=1e-9)
    assert r.notional == pytest.approx(130.0, rel=1e-9)
    assert r.risk_amount == pytest.approx(13.247, rel=1e-9)
    assert r.margin == pytest.approx(26.0, rel=1e-9)


def test_size_step_never_rounds_up():
    # 1.373896 with step 0.5 -> 1.0 (NOT 1.5): risk 10.19
    r = size_position(1000.0, 100.0, 90.0, "long", 5, CFG, qty_step=0.5)
    assert r.qty == pytest.approx(1.0, rel=1e-9)
    assert r.risk_amount == pytest.approx(10.19, rel=1e-9)
    # step 0.001 -> 1.373 ; risk 1.373*10.19 = 13.99087 (< 14)
    r2 = size_position(1000.0, 100.0, 90.0, "long", 5, CFG, qty_step=0.001)
    assert r2.qty == pytest.approx(1.373, rel=1e-9)
    assert r2.risk_amount == pytest.approx(13.99087, rel=1e-9)
    assert r2.risk_amount < 14.0


@pytest.mark.parametrize("step", [1e-5, 0.001, 0.01, 0.07, 0.1, 0.3, 0.5, 1.0])
@pytest.mark.parametrize(
    "entry,stop,side",
    [(100.0, 90.0, "long"), (100.0, 110.0, "short"), (60000.0, 59100.0, "long"), (3.0, 2.9, "long")],
)
def test_size_step_properties(step, entry, stop, side):
    try:
        base = size_position(1000.0, entry, stop, side, 5, CFG)
    except ValueError:
        pytest.skip("base sizing not feasible")
    try:
        r = size_position(1000.0, entry, stop, side, 5, CFG, qty_step=step)
    except ValueError:
        # step so large that floor gives 0 -> must be rejected; check that is the case
        assert base.qty < step * (1 + 1e-9)
        return
    # never rounds up, risk never increases
    assert r.qty <= base.qty * (1 + 1e-12)
    assert r.risk_amount <= base.risk_amount * (1 + 1e-12)
    # at most one step lost
    assert r.qty > base.qty - step * (1 + 1e-9)
    # multiple of step within float tolerance
    k = r.qty / step
    assert abs(k - round(k)) < 1e-6
    assert r.risk_amount <= 0.02 * 1000.0


def test_size_step_float_safe_exact_multiple():
    # equity 300, entry 1000, stop 997 (0.3%), 5x: per-unit = 3 + 1.997 = 4.997
    # qty_risk = 4.2/4.997 = 0.8405 ; qty_cap = 300/1000 = 0.3 (binds)
    # step 0.1: 0.3/0.1 = 2.9999999999999996 in floats; a naive floor gives 0.2.
    # float-safe floor must keep qty = 0.3 (3 steps)
    r = size_position(300.0, 1000.0, 997.0, "long", 5, CFG, qty_step=0.1)
    assert r.qty == pytest.approx(0.3, rel=1e-9)
    assert r.notional == pytest.approx(300.0, rel=1e-9)
    assert r.risk_amount == pytest.approx(0.3 * 4.997, rel=1e-9)


def test_size_step_larger_than_qty_rejected():
    # qty 1.3739 with step 5 -> floor = 0 -> ValueError
    with pytest.raises(ValueError):
        size_position(1000.0, 100.0, 90.0, "long", 5, CFG, qty_step=5.0)


def test_size_step_none_no_rounding():
    r = size_position(1000.0, 100.0, 90.0, "long", 5, CFG, qty_step=None)
    assert r.qty == pytest.approx(14 / 10.19, rel=1e-9)


# ---- min_notional -----------------------------------------------------------
def test_size_min_notional_rejection():
    # unrounded notional = 1400/10.19 = 137.39
    size_position(1000.0, 100.0, 90.0, "long", 5, CFG, min_notional=137.0)
    with pytest.raises(ValueError):
        size_position(1000.0, 100.0, 90.0, "long", 5, CFG, min_notional=138.0)


def test_size_min_notional_checked_after_step_rounding():
    # step 0.1 -> notional 130 (see hand case): 129 ok, 131 rejected
    size_position(1000.0, 100.0, 90.0, "long", 5, CFG, qty_step=0.1, min_notional=129.0)
    with pytest.raises(ValueError):
        size_position(1000.0, 100.0, 90.0, "long", 5, CFG, qty_step=0.1, min_notional=131.0)


def test_size_min_notional_checked_after_cap():
    # tight stop: capped notional 1000: 999 ok, 1000.5 rejected (even though uncapped would be 2801)
    size_position(1000.0, 100.0, 99.7, "long", 5, CFG, min_notional=999.0)
    with pytest.raises(ValueError):
        size_position(1000.0, 100.0, 99.7, "long", 5, CFG, min_notional=1000.5)


def test_size_realized_risk_never_above_2pct_grid():
    for entry in (0.5, 3.0, 100.0, 60000.0):
        for frac in (0.001, 0.003, 0.005, 0.02, 0.1, 0.3):
            for side in ("long", "short"):
                for lev in (1, 3, 5):
                    for step in (None, 0.001, 0.37):
                        stop = entry * (1 - frac) if side == "long" else entry * (1 + frac)
                        try:
                            r = size_position(1000.0, entry, stop, side, lev, CFG, qty_step=step)
                        except ValueError:
                            continue
                        assert r.risk_amount <= 0.014 * 1000.0 * (1 + REL)
                        assert r.risk_amount <= 0.02 * 1000.0
                        assert r.notional <= 1000.0 * (1 + REL)
                        assert r.margin <= 1000.0 * (1 + REL)
                        assert r.risk_amount == pytest.approx(
                            loss_at_stop(r.qty, entry, stop, CFG), rel=1e-9
                        )


# --------------------------------------------------------------------------
# check_entry : happy path (rule 12)
# --------------------------------------------------------------------------
def test_entry_allowed_realistic():
    d = check_entry(mk_state(), mk_cand(), CFG)
    assert isinstance(d, Decision)
    assert d.allowed is True
    assert isinstance(d.reason, str)
    assert isinstance(d.size, SizeResult)
    assert d.size.risk_amount == pytest.approx(14.0, rel=1e-6)
    assert d.size.notional <= 1000.0
    assert d.size.margin <= 1000.0


def test_entry_allowed_short():
    # short: liq = 60000*1.196 = 71760 -> dist 11760 >= 1.5*900 = 1350
    d = check_entry(mk_state(), mk_cand(side="short", stop=60900.0), CFG)
    assert d.allowed is True and d.size is not None


def test_entry_allowed_tight_stop_is_notional_capped():
    # entry 100 stop 99.7 5x -> notional 1000 (cap), risk 4.997 (< 14)
    d = check_entry(mk_state(), mk_cand(pair=ETH, entry=100.0, stop=99.7), CFG)
    assert d.allowed is True
    assert d.size.notional <= 1000.0 * (1 + REL)
    assert d.size.risk_amount == pytest.approx(4.997, rel=1e-9)
    assert d.size.risk_amount < 14.0


def test_entry_allowed_01pct_stop():
    d = check_entry(mk_state(), mk_cand(pair=ETH, entry=100.0, stop=99.9), CFG)
    assert d.allowed is True
    assert d.size.notional <= 1000.0 * (1 + REL)
    assert d.size.risk_amount == pytest.approx(2.999, rel=1e-9)


def test_entry_uses_step_and_min_notional():
    d = check_entry(mk_state(), eth_cand(qty_step=0.1), CFG)
    assert d.allowed is True
    assert d.size.qty == pytest.approx(1.3, rel=1e-9)
    # min_notional above the achievable 130 -> rule 6 denial
    assert_denied(check_entry(mk_state(), eth_cand(qty_step=0.1, min_notional=131.0), CFG))
    assert is_allowed(mk_state(), eth_cand(qty_step=0.1, min_notional=129.0))


# --------------------------------------------------------------------------
# Number acceptance
# --------------------------------------------------------------------------
def test_ints_accepted():
    st = AccountState(equity=1000, day_start_equity=1000, open_positions=[])
    c = Candidate(pair=ETH, side="long", entry=100, stop=90, leverage=5)
    d = check_entry(st, c, CFG)
    assert d.allowed is True
    assert d.size.risk_amount == pytest.approx(14.0, rel=1e-6)


def test_numbers_real_fraction_accepted():
    # fractions.Fraction is a numbers.Real
    assert isinstance(Fraction(1), numbers.Real)
    st = AccountState(equity=Fraction(1000), day_start_equity=Fraction(1000), open_positions=[])
    c = Candidate(pair=ETH, side="long", entry=Fraction(100), stop=Fraction(90), leverage=5)
    d = check_entry(st, c, CFG)
    assert d.allowed is True
    assert d.size.risk_amount == pytest.approx(14.0, rel=1e-6)


def test_numpy_numbers_accepted():
    np = pytest.importorskip("numpy")
    st = AccountState(equity=np.float64(1000.0), day_start_equity=np.float64(1000.0), open_positions=[])
    c = Candidate(
        pair=ETH, side="long", entry=np.float64(100.0), stop=np.float64(90.0), leverage=np.int64(5)
    )
    d = check_entry(st, c, CFG)
    assert d.allowed is True
    c2 = Candidate(pair=ETH, side="long", entry=np.float32(100.0), stop=np.float32(90.0), leverage=np.int32(5))
    assert check_entry(st, c2, CFG).allowed is True


def test_bool_rejected_everywhere():
    # Each baseline below is otherwise VALID if True were taken as 1.
    # equity True (=1), day_start 1.0 : tiny but feasible account
    assert_denied(check_entry(mk_state(equity=True, day_start=1.0), mk_cand(), CFG))
    assert_denied(check_entry(mk_state(equity=1.0, day_start=True), mk_cand(), CFG))
    # entry True (=1), stop 0.9 long
    assert_denied(check_entry(mk_state(), mk_cand(entry=True, stop=0.9), CFG))
    # stop True (=1) with short entry 0.9
    assert_denied(check_entry(mk_state(), mk_cand(side="short", entry=0.9, stop=True), CFG))
    # leverage bool
    assert_denied(check_entry(mk_state(), mk_cand(leverage=True), CFG))
    assert_denied(check_entry(mk_state(), mk_cand(leverage=False), CFG))
    # qty_step True (=1): 1.37 -> 1 would be feasible
    assert_denied(check_entry(mk_state(), eth_cand(qty_step=True), CFG))
    # min_notional True / False (=1 / 0) would be satisfied
    assert_denied(check_entry(mk_state(), eth_cand(min_notional=True), CFG))
    assert_denied(check_entry(mk_state(), eth_cand(min_notional=False), CFG))
    # sanity: the same baselines are fine with real numbers
    assert is_allowed(mk_state(equity=1.0, day_start=1.0), mk_cand())
    assert is_allowed(mk_state(), mk_cand(entry=1.0, stop=0.9))
    assert is_allowed(mk_state(), mk_cand(side="short", entry=0.9, stop=1.0))
    assert is_allowed(mk_state(), eth_cand(qty_step=1.0))
    assert is_allowed(mk_state(), eth_cand(min_notional=1.0))


@pytest.mark.parametrize("bad", [None, "1000", "abc", NAN, INF, -INF])
def test_bad_numbers_in_state_denied(bad):
    assert_denied(check_entry(mk_state(equity=bad), mk_cand(), CFG))
    assert_denied(check_entry(mk_state(day_start=bad), mk_cand(), CFG))


@pytest.mark.parametrize("bad", [None, "100", "abc", NAN, INF, -INF])
def test_bad_numbers_in_candidate_denied(bad):
    assert_denied(check_entry(mk_state(), eth_cand(entry=bad), CFG))
    assert_denied(check_entry(mk_state(), eth_cand(stop=bad), CFG))
    assert_denied(check_entry(mk_state(), eth_cand(leverage=bad), CFG))


@pytest.mark.parametrize("bad", ["0.1", "abc", NAN, INF, -INF])
def test_bad_numbers_in_step_and_min_notional_denied(bad):
    assert_denied(check_entry(mk_state(), eth_cand(qty_step=bad), CFG))
    assert_denied(check_entry(mk_state(), eth_cand(min_notional=bad), CFG))


@pytest.mark.parametrize("bad", ["5", "five", 4.5, NAN, INF, None])
def test_non_integer_leverage_denied(bad):
    assert_denied(check_entry(mk_state(), mk_cand(leverage=bad), CFG))


# --------------------------------------------------------------------------
# Normalization
# --------------------------------------------------------------------------
@pytest.mark.parametrize("side", ["long", "LONG", " Long ", "  long", "Long  "])
def test_side_long_variants_accepted(side):
    d = check_entry(mk_state(), mk_cand(side=side), CFG)
    assert d.allowed is True


@pytest.mark.parametrize("side", ["short", "SHORT", " Short ", "  sHoRt"])
def test_side_short_variants_accepted(side):
    d = check_entry(mk_state(), mk_cand(side=side, stop=60900.0), CFG)
    assert d.allowed is True


@pytest.mark.parametrize("side", ["buy", "sell", "", "  ", "both", "lon g", None, 1, True])
def test_side_invalid_denied(side):
    assert_denied(check_entry(mk_state(), mk_cand(side=side), CFG))


def test_side_variants_count_in_same_direction_totals():
    # longs (messy spelling) 13.0 + 13.1 = 26.1 ; + new long 14 = 40.1 > 40 -> rule 9 denial
    messy = [pos(ETH, "LONG", 13.0), pos(SOL, " Long ", 13.1)]
    clean = [pos(ETH, "long", 13.0), pos(SOL, "long", 13.1)]
    r_messy = reason_of(mk_state(open_positions=messy), mk_cand(side="long"))
    r_clean = reason_of(mk_state(open_positions=clean), mk_cand(side="long"))
    assert r_messy == r_clean
    # candidate side messy too
    assert reason_of(mk_state(open_positions=messy), mk_cand(side=" LONG ")) == r_clean
    # the same book is fine for the opposite direction: same-dir = 14, total 40.1 <= 50
    assert is_allowed(mk_state(open_positions=messy), mk_cand(side=" Short ", stop=60900.0))


def test_side_variants_short_totals_mirror():
    messy = [pos(ETH, "SHORT", 13.0), pos(SOL, " short", 13.1)]
    assert_denied(check_entry(mk_state(open_positions=messy), mk_cand(side="SHORT", stop=60900.0), CFG))
    assert is_allowed(mk_state(open_positions=messy), mk_cand(side=" LONG "))


def test_pair_normalization_duplicate():
    base = reason_of(mk_state(open_positions=[pos(BTC, "long", 5.0)]), mk_cand(pair=BTC))
    for open_pair, cand_pair in [
        ("btc/usdt", "BTC/USDT:USDT"),
        ("BTC/USDT:USDT", "btc/usdt"),
        (" Btc/Usdt ", "BTC/USDT:USDT"),
        ("BTC/USDT:USDT", " btc/usdt:usdt "),
        ("BTC/USDT", "btc/usdt:usdc"),  # everything after ':' is dropped
    ]:
        st = mk_state(open_positions=[pos(open_pair, "long", 5.0)])
        assert reason_of(st, mk_cand(pair=cand_pair)) == base, (open_pair, cand_pair)


def test_pair_normalization_not_over_eager():
    st = mk_state(open_positions=[pos("eth/usdt", "long", 5.0)])
    assert is_allowed(st, mk_cand(pair="BTC/USDT:USDT"))


# --------------------------------------------------------------------------
# Rule 1: invalid input
# --------------------------------------------------------------------------
@pytest.mark.parametrize("entry", [NAN, INF, -INF, 0.0, -1.0])
def test_rule1_bad_entry(entry):
    assert_denied(check_entry(mk_state(), mk_cand(entry=entry), CFG))


@pytest.mark.parametrize("stop", [NAN, INF, -INF, 0.0, -5.0])
def test_rule1_bad_stop(stop):
    assert_denied(check_entry(mk_state(), mk_cand(stop=stop), CFG))
    assert_denied(check_entry(mk_state(), mk_cand(side="short", stop=stop), CFG))


@pytest.mark.parametrize("equity", [0.0, -10.0, NAN, INF])
def test_rule1_bad_equity(equity):
    assert_denied(check_entry(mk_state(equity=equity), mk_cand(), CFG))


@pytest.mark.parametrize("ds", [0.0, -10.0, NAN, INF])
def test_rule1_bad_day_start_equity(ds):
    assert_denied(check_entry(mk_state(day_start=ds), mk_cand(), CFG))


@pytest.mark.parametrize("pair", ["", "   ", None, 5, 1.5, ["BTC/USDT"]])
def test_rule1_bad_pair(pair):
    assert_denied(check_entry(mk_state(), mk_cand(pair=pair), CFG))


# ---- invalid open positions: previously fail-open bugs ----------------------
BAD_AMOUNTS = [NAN, -1.0, -0.0001, INF, -INF, "x", None, True]


def _state_with_corrupted_open(field, value):
    p = pos(ETH, "short", 1.0, 100.0)
    object.__setattr__(p, field, value)  # works for frozen and plain dataclasses
    return mk_state(open_positions=[p])


@pytest.mark.parametrize("value", BAD_AMOUNTS)
def test_rule1_open_position_bad_risk_amount_denied(value):
    assert_denied(check_entry(_state_with_corrupted_open("risk_amount", value), mk_cand(), CFG))


@pytest.mark.parametrize("value", BAD_AMOUNTS)
def test_rule1_open_position_bad_margin_denied(value):
    assert_denied(check_entry(_state_with_corrupted_open("margin", value), mk_cand(), CFG))


@pytest.mark.parametrize("value", ["buy", "", None, 5, "flat"])
def test_rule1_open_position_bad_side_denied(value):
    assert_denied(check_entry(_state_with_corrupted_open("side", value), mk_cand(), CFG))


def test_rule1_negative_open_risk_would_otherwise_unlock_capacity():
    # a -100 risk would make total/same-dir/daily sums negative (fail-open) -> must be denied
    st = mk_state(open_positions=[pos(ETH, "long", 5.0, 10.0)])
    p = st.open_positions[0]
    object.__setattr__(p, "risk_amount", -100.0)
    assert_denied(check_entry(st, mk_cand(), CFG))


def test_rule1_nan_open_risk_would_otherwise_pass_comparisons():
    # NaN > cap is False for every cap: a naive implementation would allow
    st = mk_state(open_positions=[pos(ETH, "long", 5.0, 10.0)])
    object.__setattr__(st.open_positions[0], "risk_amount", NAN)
    assert_denied(check_entry(st, mk_cand(), CFG))
    st2 = mk_state(open_positions=[pos(ETH, "long", 5.0, 10.0)])
    object.__setattr__(st2.open_positions[0], "margin", NAN)
    assert_denied(check_entry(st2, mk_cand(), CFG))


def test_rule1_invalid_open_position_at_construction_fails_closed():
    # Spec: risk_amount/margin must be finite and >= 0. Either the constructor refuses
    # (ValueError/TypeError) or check_entry must deny.
    for kw in (
        dict(risk_amount=NAN, margin=1.0),
        dict(risk_amount=-1.0, margin=1.0),
        dict(risk_amount=INF, margin=1.0),
        dict(risk_amount=1.0, margin=NAN),
        dict(risk_amount=1.0, margin=-1.0),
        dict(risk_amount=1.0, margin=INF),
    ):
        try:
            p = OpenPosition(pair=ETH, side="short", **kw)
        except (ValueError, TypeError):
            continue
        assert_denied(check_entry(mk_state(open_positions=[p]), mk_cand(), CFG))


def test_rule1_valid_open_position_zero_values_ok():
    # 0 is finite and >= 0 -> valid
    assert is_allowed(mk_state(open_positions=[pos(ETH, "short", 0.0, 0.0)]), mk_cand())


# --------------------------------------------------------------------------
# Rule 2: stop on wrong side
# --------------------------------------------------------------------------
@pytest.mark.parametrize("stop", [60000.0, 60001.0, 65000.0])
def test_rule2_long_stop_not_below_entry(stop):
    assert_denied(check_entry(mk_state(), mk_cand(side="long", stop=stop), CFG))


@pytest.mark.parametrize("stop", [60000.0, 59999.0, 55000.0])
def test_rule2_short_stop_not_above_entry(stop):
    assert_denied(check_entry(mk_state(), mk_cand(side="short", stop=stop), CFG))


def test_rule2_right_side_allowed():
    assert is_allowed(mk_state(), mk_cand(side="long", stop=59100.0))
    assert is_allowed(mk_state(), mk_cand(side="short", stop=60900.0))


# --------------------------------------------------------------------------
# Rule 3: leverage range
# --------------------------------------------------------------------------
@pytest.mark.parametrize("lev", [0, -5, 1, 2, 6, 10, 125])
def test_rule3_leverage_out_of_range(lev):
    assert_denied(check_entry(mk_state(), mk_cand(leverage=lev), CFG))


@pytest.mark.parametrize("lev", [3, 4, 5])
def test_rule3_leverage_in_range_ok(lev):
    # lev 3 margin: 824.26/3 = 274.8 <= 1000 ; liq dist at 3x = 60000*(1/3-0.004) = 19760 >= 1350
    assert is_allowed(mk_state(), mk_cand(leverage=lev))


def test_rule3_custom_range():
    cfg = RiskConfig(min_leverage=1, max_leverage=2)
    assert is_allowed(mk_state(), mk_cand(leverage=1), cfg)
    assert is_allowed(mk_state(), mk_cand(leverage=2), cfg)
    assert_denied(check_entry(mk_state(), mk_cand(leverage=3), cfg))


# --------------------------------------------------------------------------
# Rule 4: daily loss already hit
# --------------------------------------------------------------------------
def test_rule4_daily_loss_exactly_minus_5pct_denied():
    # (950 - 1000)/1000 = -0.05 <= -0.05 -> denied
    assert_denied(check_entry(mk_state(equity=950.0, day_start=1000.0), mk_cand(), CFG))


def test_rule4_daily_loss_beyond_denied():
    assert_denied(check_entry(mk_state(equity=900.0, day_start=1000.0), mk_cand(), CFG))


def test_rule4_just_inside_is_a_different_rule():
    # (950.5-1000)/1000 = -0.0495 > -0.05 -> passes rule 4, but rule 10 blocks:
    # loss 49.5 + new 13.3 = 62.8 > 50. Reason must differ from the rule 4 reason.
    r4 = reason_of(mk_state(equity=950.0, day_start=1000.0), mk_cand())
    r_inside = reason_of(mk_state(equity=950.5, day_start=1000.0), mk_cand())
    assert r4 != r_inside


def test_rule4_loss_inside_budget_allowed():
    # eq 964, ds 1000: loss 36; new risk 0.014*964 = 13.496 ; 36 + 13.496 = 49.496 <= 50 -> allowed
    assert is_allowed(mk_state(equity=964.0, day_start=1000.0), mk_cand())
    # eq 963: loss 37 + 13.482 = 50.482 > 50 -> denied (rule 10)
    assert_denied(check_entry(mk_state(equity=963.0, day_start=1000.0), mk_cand(), CFG))


def test_rule4_daily_gain_allowed():
    # (1100-1000)/1000 = +0.10 ; loss = 0 ; new risk 15.4 <= 50
    assert is_allowed(mk_state(equity=1100.0, day_start=1000.0), mk_cand())


def test_rule4_custom_limit():
    cfg = RiskConfig(daily_max_loss=0.03)
    # eq 970: (970-1000)/1000 = -0.03 <= -0.03 -> rule 4 denial
    r4 = reason_of(mk_state(equity=970.0), mk_cand(), cfg)
    # eq 971: loss 29 + 13.594 = 42.6 > 30 -> a different (rule 10) denial
    assert reason_of(mk_state(equity=971.0), mk_cand(), cfg) != r4
    # eq 990: loss 10 + 13.86 = 23.86 <= 30 -> allowed
    assert is_allowed(mk_state(equity=990.0), mk_cand(), cfg)


# --------------------------------------------------------------------------
# Rule 5: duplicate pair
# --------------------------------------------------------------------------
def test_rule5_duplicate_pair_same_side_denied():
    st = mk_state(open_positions=[pos(BTC, "long", 5.0)])
    assert_denied(check_entry(st, mk_cand(side="long"), CFG))


def test_rule5_duplicate_pair_opposite_side_denied():
    st = mk_state(open_positions=[pos(BTC, "long", 5.0)])
    assert_denied(check_entry(st, mk_cand(side="short", stop=60900.0), CFG))


def test_rule5_different_pair_allowed():
    st = mk_state(open_positions=[pos(ETH, "long", 5.0)])
    # total 5 + 14 = 19 <= 50 ; same-dir 19 <= 40
    assert is_allowed(st, mk_cand(pair=BTC))


# --------------------------------------------------------------------------
# Rule 6: sizing failure
# --------------------------------------------------------------------------
def test_rule6_min_notional_denied():
    # notional ~137.4 < 500 -> size_position raises -> denied; same candidate without it passes
    assert is_allowed(mk_state(), eth_cand())
    assert_denied(check_entry(mk_state(), eth_cand(min_notional=500.0), CFG))


def test_rule6_step_too_big_denied():
    assert_denied(check_entry(mk_state(), eth_cand(qty_step=5.0), CFG))


def test_rule6_min_notional_vs_cap():
    # tight stop capped at notional 1000: min_notional 1500 can never be met
    assert_denied(check_entry(mk_state(), mk_cand(pair=ETH, entry=100.0, stop=99.7, min_notional=1500.0), CFG))


# --------------------------------------------------------------------------
# Rule 7: liquidation safety
# --------------------------------------------------------------------------
def test_rule7_wide_stop_5x_long_denied():
    # entry 100, stop 80, 5x: liq = 80.4, |100-80.4| = 19.6 < 1.5*20 = 30 -> denied
    assert_denied(check_entry(mk_state(), mk_cand(pair=ETH, entry=100.0, stop=80.0, leverage=5), CFG))


def test_rule7_wide_stop_5x_short_denied():
    # entry 100, stop 120, 5x: liq = 119.6, dist 19.6 < 30 -> denied
    assert_denied(check_entry(mk_state(), mk_cand(pair=ETH, side="short", entry=100.0, stop=120.0), CFG))


def test_rule7_same_stop_ok_at_3x():
    # 3x long: liq = 67.0667, dist 32.933 >= 30 -> allowed (same candidate denied at 5x)
    assert is_allowed(mk_state(), mk_cand(pair=ETH, entry=100.0, stop=80.0, leverage=3))
    assert_denied(check_entry(mk_state(), mk_cand(pair=ETH, entry=100.0, stop=80.0, leverage=5), CFG))


def test_rule7_boundary_5x_long():
    # liq dist 19.6 ; threshold stop dist d* = 19.6/1.5 = 13.0667 (stop 86.9333)
    # stop 87 -> d=13 -> 19.5 <= 19.6 allowed ; stop 86.8 -> d=13.2 -> 19.8 > 19.6 denied
    assert is_allowed(mk_state(), mk_cand(pair=ETH, entry=100.0, stop=87.0, leverage=5))
    assert_denied(check_entry(mk_state(), mk_cand(pair=ETH, entry=100.0, stop=86.8, leverage=5), CFG))


def test_rule7_boundary_5x_short():
    assert is_allowed(mk_state(), mk_cand(pair=ETH, side="short", entry=100.0, stop=113.0, leverage=5))
    assert_denied(check_entry(mk_state(), mk_cand(pair=ETH, side="short", entry=100.0, stop=113.2), CFG))


# --------------------------------------------------------------------------
# Rule 8: total open risk. Default cap 6% (60) is looser than the daily budget
# (50), so isolate it with max_open_risk=0.03 (cap 30; new risk 14).
# --------------------------------------------------------------------------
CFG8 = RiskConfig(max_open_risk=0.03)


def test_rule8_inside_cap_allowed():
    # short 15.9 + new 14 = 29.9 <= 30
    assert is_allowed(mk_state(open_positions=[pos(ETH, "short", 15.9)]), mk_cand(), CFG8)


def test_rule8_over_cap_denied():
    # 16.1 + 14 = 30.1 > 30 ; rule 10 would pass (30.1 <= 50), so this is rule 8
    st = mk_state(open_positions=[pos(ETH, "short", 16.1)])
    assert_denied(check_entry(st, mk_cand(), CFG8))
    # same book passes under the default cfg
    assert is_allowed(st, mk_cand(), CFG)


def test_rule8_cap_scales_with_equity():
    # equity 2000 -> cap 60 ; new risk 28 ; open 31.5 + 28 = 59.5 ok ; 32.5 + 28 = 60.5 denied
    assert is_allowed(mk_state(2000.0, 2000.0, [pos(ETH, "short", 31.5)]), mk_cand(), CFG8)
    assert_denied(check_entry(mk_state(2000.0, 2000.0, [pos(ETH, "short", 32.5)]), mk_cand(), CFG8))


def test_rule8_applies_across_directions():
    # a long book counts toward the total even for a short candidate
    st = mk_state(open_positions=[pos(ETH, "long", 16.1)])
    assert_denied(check_entry(st, mk_cand(side="short", stop=60900.0), CFG8))


# --------------------------------------------------------------------------
# Rule 9: same-direction risk (cap 4% of 1000 = 40)
# --------------------------------------------------------------------------
def test_rule9_same_dir_inside_cap_allowed():
    # longs 13 + 12 = 25 ; + 14 = 39 <= 40 ; total 39 <= 50
    opens = [pos(ETH, "long", 13.0), pos(SOL, "long", 12.0)]
    assert is_allowed(mk_state(open_positions=opens), mk_cand())


def test_rule9_same_dir_over_cap_denied():
    # longs 13 + 13.1 = 26.1 ; + 14 = 40.1 > 40 ; total 40.1 <= 50 so only rule 9
    opens = [pos(ETH, "long", 13.0), pos(SOL, "long", 13.1)]
    assert_denied(check_entry(mk_state(open_positions=opens), mk_cand(), CFG))


def test_rule9_opposite_direction_still_allowed():
    # three longs 3 * 10 = 30
    opens = [pos(ETH, "long", 10.0), pos(SOL, "long", 10.0), pos(XRP, "long", 10.0)]
    st = mk_state(open_positions=opens)
    # long candidate: same-dir 30 + 14 = 44 > 40 -> denied (rule 9; total 44 <= 50)
    assert_denied(check_entry(st, mk_cand(side="long"), CFG))
    # short candidate: same-dir 14 <= 40 ; total 44 <= 60 and 44 <= 50 -> allowed
    d = check_entry(st, mk_cand(side="short", stop=60900.0), CFG)
    assert d.allowed is True and d.size is not None


def test_rule9_mirror_for_shorts():
    opens = [pos(ETH, "short", 10.0), pos(SOL, "short", 10.0), pos(XRP, "short", 10.0)]
    st = mk_state(open_positions=opens)
    assert_denied(check_entry(st, mk_cand(side="short", stop=60900.0), CFG))
    assert is_allowed(st, mk_cand(side="long"))


# --------------------------------------------------------------------------
# Rule 10: daily budget  today_loss + open risk + new risk <= 5% * day_start
# today_loss = max(0, day_start - equity)
# --------------------------------------------------------------------------
def test_rule10_loss_30_open_6():
    # eq 970, ds 1000: loss 30 ; new risk 0.014*970 = 13.58
    # open (short) 6: 30 + 6 + 13.58 = 49.58 <= 50 allowed ; open 7: 50.58 > 50 denied
    assert is_allowed(mk_state(970.0, 1000.0, [pos(ETH, "short", 6.0)]), mk_cand())
    assert_denied(check_entry(mk_state(970.0, 1000.0, [pos(ETH, "short", 7.0)]), mk_cand(), CFG))


def test_rule10_loss_30_open_14_denied():
    # 30 + 14 + 13.58 = 57.58 > 50 -> denied, although each of rules 4, 8, 9 passes by itself
    st = mk_state(970.0, 1000.0, [pos(ETH, "short", 14.0)])
    assert_denied(check_entry(st, mk_cand(), CFG))
    # without the open position: 30 + 13.58 = 43.58 <= 50 -> allowed
    assert is_allowed(mk_state(970.0, 1000.0), mk_cand())


def test_rule10_gain_does_not_extend_budget_and_uses_day_start():
    # eq 1050, ds 1000: loss 0 ; new risk 14.7 ; budget = 5% of day_start = 50 (not of equity 52.5)
    # open short 35 + 14.7 = 49.7 <= 50 allowed ; 35.5 + 14.7 = 50.2 > 50 denied
    # (rule 8: 6% of 1050 = 63 passes ; rule 9: opposite direction)
    assert is_allowed(mk_state(1050.0, 1000.0, [pos(ETH, "short", 35.0)]), mk_cand())
    assert_denied(check_entry(mk_state(1050.0, 1000.0, [pos(ETH, "short", 35.5)]), mk_cand(), CFG))


def test_rule10_gain_not_negative_loss():
    # eq 1100, ds 1000: loss = max(0, -100) = 0 (a gain must not give extra budget)
    # new risk 15.4 ; open 34 -> 49.4 allowed ; open 35 -> 50.4 denied
    assert is_allowed(mk_state(1100.0, 1000.0, [pos(ETH, "short", 34.0)]), mk_cand())
    assert_denied(check_entry(mk_state(1100.0, 1000.0, [pos(ETH, "short", 35.0)]), mk_cand(), CFG))


def test_rule10_custom_budget():
    cfg = RiskConfig(daily_max_loss=0.02)  # budget 20 on ds 1000 ; new risk 14
    # open 5.9 -> 19.9 allowed ; open 6.2 -> 20.2 denied
    assert is_allowed(mk_state(open_positions=[pos(ETH, "short", 5.9)]), mk_cand(), cfg)
    assert_denied(check_entry(mk_state(open_positions=[pos(ETH, "short", 6.2)]), mk_cand(), cfg))


def test_rule10_reason_differs_from_rule_9_and_4():
    r10 = reason_of(mk_state(970.0, 1000.0, [pos(ETH, "short", 14.0)]), mk_cand())
    r9 = reason_of(mk_state(open_positions=[pos(ETH, "long", 13.0), pos(SOL, "long", 13.1)]), mk_cand())
    r4 = reason_of(mk_state(940.0, 1000.0), mk_cand())
    assert len({r10, r9, r4}) == 3


# --------------------------------------------------------------------------
# Rule 11: margin
# --------------------------------------------------------------------------
# BTC 60000 -> 59100 5x equity 1000: new margin = 840000/1019.1/5 = 164.851
def test_rule11_margin_total_inside_allowed():
    # open margin 835 + 164.851 = 999.851 <= 1000 ; open risk 1 (tiny, all risk rules pass)
    assert is_allowed(mk_state(open_positions=[pos(ETH, "short", 1.0, 835.0)]), mk_cand())


def test_rule11_margin_total_over_denied():
    # 835.5 + 164.851 = 1000.351 > 1000
    st = mk_state(open_positions=[pos(ETH, "short", 1.0, 835.5)])
    assert_denied(check_entry(st, mk_cand(), CFG))


def test_rule11_sum_of_several_positions():
    ok = [pos(ETH, "short", 1.0, 300.0), pos(SOL, "short", 1.0, 300.0), pos(XRP, "short", 1.0, 235.0)]
    bad = [pos(ETH, "short", 1.0, 300.0), pos(SOL, "short", 1.0, 300.0), pos(XRP, "short", 1.0, 236.0)]
    # 835 + 164.851 = 999.851 ok ; 836 + 164.851 = 1000.851 denied
    assert is_allowed(mk_state(open_positions=ok), mk_cand())
    assert_denied(check_entry(mk_state(open_positions=bad), mk_cand(), CFG))


def test_rule11_uses_equity_scale():
    # equity 2000: new risk 28, notional 1648.51, margin 329.70
    # open margin 1670 -> 1999.70 ok ; 1671 -> 2000.70 denied
    assert is_allowed(mk_state(2000.0, 2000.0, [pos(ETH, "short", 1.0, 1670.0)]), mk_cand())
    assert_denied(check_entry(mk_state(2000.0, 2000.0, [pos(ETH, "short", 1.0, 1671.0)]), mk_cand(), CFG))


def test_rule11_reason_differs_from_risk_rules():
    r11 = reason_of(mk_state(open_positions=[pos(ETH, "short", 1.0, 900.0)]), mk_cand())
    r10 = reason_of(mk_state(open_positions=[pos(ETH, "short", 40.0, 100.0)]), mk_cand())
    assert r11 != r10


# --------------------------------------------------------------------------
# Precedence: with two violations the earlier rule is the reason.
# We compare reason strings across calls (no exact text asserted):
#   both == only-earlier  and  both != only-later
# --------------------------------------------------------------------------
def test_precedence_rule1_over_rule2():
    both = reason_of(mk_state(), mk_cand(entry=-100.0, stop=-50.0))  # bad price AND stop>=entry
    only1 = reason_of(mk_state(), mk_cand(entry=-100.0, stop=-150.0))  # bad price only
    only2 = reason_of(mk_state(), mk_cand(entry=100.0, stop=105.0))  # wrong-side stop only
    assert both == only1
    assert both != only2


def test_precedence_rule2_over_rule3():
    both = reason_of(mk_state(), mk_cand(stop=61000.0, leverage=10))
    only2 = reason_of(mk_state(), mk_cand(stop=61000.0, leverage=5))
    only3 = reason_of(mk_state(), mk_cand(leverage=10))
    assert both == only2
    assert both != only3


def test_precedence_rule3_over_rule4():
    loss = mk_state(equity=940.0, day_start=1000.0)
    both = reason_of(loss, mk_cand(leverage=10))
    only3 = reason_of(mk_state(), mk_cand(leverage=10))
    only4 = reason_of(loss, mk_cand(leverage=5))
    assert both == only3
    assert both != only4


def test_precedence_rule4_over_rule5():
    dup = [pos(BTC, "long", 5.0)]
    both = reason_of(mk_state(940.0, 1000.0, dup), mk_cand())
    only4 = reason_of(mk_state(940.0, 1000.0), mk_cand())
    only5 = reason_of(mk_state(1000.0, 1000.0, dup), mk_cand())
    assert both == only4
    assert both != only5


def test_precedence_rule5_over_rule6():
    dup = [pos(ETH, "long", 5.0)]
    bad_size = eth_cand(min_notional=500.0)  # rule 6 failure
    both = reason_of(mk_state(open_positions=dup), bad_size)
    only5 = reason_of(mk_state(open_positions=dup), eth_cand())
    only6 = reason_of(mk_state(), bad_size)
    assert both == only5
    assert both != only6


def test_precedence_rule6_over_rule7():
    # entry 100 stop 80 5x is liq-unsafe (rule 7) ; min_notional 500 makes sizing fail (rule 6)
    both = reason_of(mk_state(), mk_cand(pair=ETH, entry=100.0, stop=80.0, min_notional=500.0))
    only6 = reason_of(mk_state(), mk_cand(pair=ETH, entry=100.0, stop=90.0, min_notional=500.0))
    only7 = reason_of(mk_state(), mk_cand(pair=ETH, entry=100.0, stop=80.0))
    assert both == only6
    assert both != only7


def test_precedence_rule7_over_rule8():
    wide = mk_cand(pair=SOL, entry=100.0, stop=80.0, leverage=5)  # liq unsafe
    shorts = [pos(ETH, "short", 17.0)]  # 17 + 14 = 31 > 30 under CFG8
    both = reason_of(mk_state(open_positions=shorts), wide, CFG8)
    only7 = reason_of(mk_state(), wide, CFG8)
    only8 = reason_of(mk_state(open_positions=shorts), mk_cand(pair=SOL, entry=100.0, stop=90.0), CFG8)
    assert both == only7
    assert both != only8


def test_precedence_rule8_over_rule9():
    cfg = RiskConfig(max_open_risk=0.03, max_same_dir_risk=0.02)  # caps 30 / 20 ; new risk 14
    only9 = reason_of(mk_state(open_positions=[pos(ETH, "long", 7.0)]), mk_cand(), cfg)  # 21 > 20, total 21 <= 30
    only8 = reason_of(mk_state(open_positions=[pos(ETH, "short", 17.0)]), mk_cand(), cfg)  # 31 > 30, same-dir 14
    both = reason_of(mk_state(open_positions=[pos(ETH, "long", 17.0)]), mk_cand(), cfg)  # both violated
    assert both == only8
    assert both != only9


def test_precedence_rule8_over_rule10():
    # CFG8: cap 30. Loss 0 + shorts 17 : only rule 8 (31 > 30 ; 31 <= 50)
    only8 = reason_of(mk_state(open_positions=[pos(ETH, "short", 17.0)]), mk_cand(), CFG8)
    # eq 970 (loss 30; new 13.58; cap 29.1): shorts 10 -> 23.58 <= 29.1 ; 30 + 10 + 13.58 = 53.58 > 50 : only rule 10
    only10 = reason_of(mk_state(970.0, 1000.0, [pos(ETH, "short", 10.0)]), mk_cand(), CFG8)
    # eq 970 shorts 20 -> 33.58 > 29.1 and 63.58 > 50 : both
    both = reason_of(mk_state(970.0, 1000.0, [pos(ETH, "short", 20.0)]), mk_cand(), CFG8)
    assert both == only8
    assert both != only10


def test_precedence_rule9_over_rule10():
    # only9: longs 30 -> same-dir 44 > 40 ; total 44 <= 50
    only9 = reason_of(mk_state(open_positions=[pos(ETH, "long", 30.0)]), mk_cand())
    # only10: shorts 38 (opposite) -> same-dir 14 ; total 52 > 50, <= 60
    only10 = reason_of(mk_state(open_positions=[pos(ETH, "short", 38.0)]), mk_cand())
    # both: longs 38 -> same-dir 52 > 40 and total 52 > 50
    both = reason_of(mk_state(open_positions=[pos(ETH, "long", 38.0)]), mk_cand())
    assert both == only9
    assert both != only10


def test_precedence_rule10_over_rule11():
    only11 = reason_of(mk_state(open_positions=[pos(ETH, "short", 1.0, 900.0)]), mk_cand())
    only10 = reason_of(mk_state(open_positions=[pos(ETH, "short", 40.0, 100.0)]), mk_cand())
    both = reason_of(mk_state(open_positions=[pos(ETH, "short", 40.0, 900.0)]), mk_cand())
    assert both == only10
    assert both != only11


# --------------------------------------------------------------------------
# Fail-closed
# --------------------------------------------------------------------------
def test_failclosed_size_position_raises(monkeypatch):
    def boom(*a, **k):
        raise RuntimeError("kaboom")

    monkeypatch.setattr(risk, "size_position", boom)
    assert_denied(check_entry(mk_state(), mk_cand(), CFG))


@pytest.mark.parametrize("exc", [ZeroDivisionError, ArithmeticError, KeyError, TypeError, OverflowError, ValueError])
def test_failclosed_size_position_various_exceptions(monkeypatch, exc):
    def boom(*a, **k):
        raise exc("x")

    monkeypatch.setattr(risk, "size_position", boom)
    assert_denied(check_entry(mk_state(), mk_cand(), CFG))


def _garbage_sizes():
    return [
        object(),
        None,
        42,
        "size",
        (1, 2, 3, 4),
        SimpleNamespace(),
        SimpleNamespace(qty=NAN, notional=NAN, margin=NAN, risk_amount=NAN),
        SimpleNamespace(qty=1.0, notional=100.0, margin=20.0, risk_amount=NAN),
        SimpleNamespace(qty=1.0, notional=100.0, margin=NAN, risk_amount=5.0),
        SimpleNamespace(qty=1.0, notional=100.0, margin=20.0, risk_amount=INF),
        SimpleNamespace(qty=1.0, notional=100.0, margin=20.0, risk_amount=-1000.0),
        SimpleNamespace(qty=1.0, notional=100.0, margin=-1000.0, risk_amount=5.0),
        SimpleNamespace(qty=1.0, notional=1e9, margin=20.0, risk_amount=5.0),
        SimpleNamespace(qty=1.0, notional=100.0, margin=1e9, risk_amount=5.0),
        SimpleNamespace(qty=1.0, notional=100.0, margin=20.0, risk_amount=1e9),
    ]


@pytest.mark.parametrize("idx", range(15))
def test_failclosed_size_position_returns_garbage(monkeypatch, idx):
    garbage = _garbage_sizes()[idx]
    monkeypatch.setattr(risk, "size_position", lambda *a, **k: garbage)
    assert_denied(check_entry(mk_state(), mk_cand(), CFG))


def test_failclosed_size_result_risk_above_2pct_denied(monkeypatch):
    # a size whose risk is 2.5% of equity (25 > 20) is denied: no cap should be bypassable
    monkeypatch.setattr(
        risk, "size_position", lambda *a, **k: SizeResult(qty=1.0, notional=100.0, margin=20.0, risk_amount=25.0)
    )
    assert_denied(check_entry(mk_state(), mk_cand(), CFG))


def test_failclosed_size_result_notional_above_equity_denied(monkeypatch):
    monkeypatch.setattr(
        risk, "size_position", lambda *a, **k: SizeResult(qty=1.0, notional=2000.0, margin=400.0, risk_amount=10.0)
    )
    assert_denied(check_entry(mk_state(), mk_cand(), CFG))


def test_failclosed_loss_at_stop_raises(monkeypatch):
    def boom(*a, **k):
        raise ArithmeticError("x")

    monkeypatch.setattr(risk, "loss_at_stop", boom)
    d = check_entry(mk_state(), mk_cand(), CFG)  # must not leak the exception
    assert isinstance(d, Decision)
    # size_position recomputes risk via loss_at_stop (spec step 5) -> must be denied
    assert_denied(d)


@pytest.mark.parametrize("garbage", [None, "x", NAN, INF, 1e12, object()])
def test_failclosed_loss_at_stop_returns_garbage(monkeypatch, garbage):
    monkeypatch.setattr(risk, "loss_at_stop", lambda *a, **k: garbage)
    d = check_entry(mk_state(), mk_cand(), CFG)
    assert isinstance(d, Decision)
    assert_denied(d)


def test_failclosed_never_raises_on_hostile_objects():
    hostile_states = [
        None,
        object(),
        42,
        "state",
        {},
        SimpleNamespace(),
        SimpleNamespace(equity=1000.0),
        SimpleNamespace(equity=1000.0, day_start_equity=1000.0),
        SimpleNamespace(equity=1000.0, day_start_equity=1000.0, open_positions=5),
        SimpleNamespace(equity=1000.0, day_start_equity=1000.0, open_positions="abc"),
    ]
    hostile_cands = [None, object(), 42, {}, SimpleNamespace(), SimpleNamespace(pair=BTC)]
    for s in hostile_states:
        assert_denied(check_entry(s, mk_cand(), CFG))
    for c in hostile_cands:
        assert_denied(check_entry(mk_state(), c, CFG))
    assert_denied(check_entry(None, None, CFG))


def test_failclosed_malformed_open_positions():
    assert_denied(check_entry(mk_state(open_positions=[object()]), mk_cand(), CFG))
    assert_denied(check_entry(mk_state(open_positions=[None]), mk_cand(), CFG))
    assert_denied(check_entry(mk_state(open_positions=[(ETH, "long", 1.0, 1.0)]), mk_cand(), CFG))
    assert_denied(check_entry(mk_state(open_positions=[pos(ETH, "short", 1.0, 1.0), object()]), mk_cand(), CFG))


def test_failclosed_open_positions_none():
    st = AccountState(equity=1000.0, day_start_equity=1000.0, open_positions=None)
    assert_denied(check_entry(st, mk_cand(), CFG))


def test_failclosed_non_numeric_fields():
    assert_denied(check_entry(mk_state(), mk_cand(entry="abc"), CFG))
    assert_denied(check_entry(mk_state(equity="lots"), mk_cand(), CFG))


def test_failclosed_zero_day_start_equity():
    # division by zero in the daily-loss ratio must not escape nor allow
    assert_denied(check_entry(mk_state(equity=1000.0, day_start=0.0), mk_cand(), CFG))


# --------------------------------------------------------------------------
# Property-style loop
# --------------------------------------------------------------------------
def _norm_pair(p):
    return p.strip().upper().split(":")[0]


def test_property_allowed_decisions_respect_caps():
    rng = random.Random(20261116)
    names = [f"P{i}" for i in range(8)]
    side_variants = {"long": ["long", "LONG", " Long "], "short": ["short", "SHORT", " short  "]}

    def pair_variant(i):
        n = names[i]
        return rng.choice([f"{n}/USDT:USDT", f"{n.lower()}/usdt", f" {n}/USDT "])

    allowed_n = denied_n = 0
    tol = 1 + 1e-9

    for _ in range(1000):
        equity = rng.uniform(100.0, 100_000.0)
        day_start = equity * rng.uniform(0.96, 1.04)
        n_open = rng.randint(0, 3)
        open_idx = rng.sample(range(8), n_open)
        opens = [
            pos(
                pair_variant(i),
                rng.choice(side_variants[rng.choice(["long", "short"])]),
                rng.uniform(0.0, 0.012) * equity,
                rng.uniform(0.0, 0.35) * equity,
            )
            for i in open_idx
        ]
        side = rng.choice(["long", "short"])
        entry = 10 ** rng.uniform(-2, 5)
        frac = 10 ** rng.uniform(-3, -0.7)  # 0.1% .. 20% stop distance
        stop = entry * (1 - frac) if side == "long" else entry * (1 + frac)
        lev = rng.choice([1, 2, 3, 4, 5, 5, 4, 3, 6])
        base_qty = equity / entry
        qty_step = None if rng.random() < 0.4 else base_qty * 10 ** rng.uniform(-4, -1)
        min_notional = rng.choice([0.0, 0.0, rng.uniform(0.0, 0.8) * equity])
        cand = mk_cand(
            pair=pair_variant(rng.randrange(8)),
            side=rng.choice(side_variants[side]),
            entry=entry,
            stop=stop,
            leverage=lev,
            qty_step=qty_step,
            min_notional=min_notional,
        )
        state = mk_state(equity, day_start, opens)

        dec = check_entry(state, cand, CFG)
        assert isinstance(dec.allowed, bool)
        assert isinstance(dec.reason, str)
        if not dec.allowed:
            denied_n += 1
            assert dec.reason.strip() != ""
            continue

        allowed_n += 1
        s = dec.size
        assert s is not None
        # per-trade realized loss <= 2% of equity (target 1.4%)
        assert s.risk_amount <= 0.02 * equity * tol
        assert s.risk_amount <= 0.014 * equity * tol
        assert s.risk_amount == pytest.approx(loss_at_stop(s.qty, entry, stop, CFG), rel=1e-6)
        # notional <= equity
        assert s.notional <= equity * tol
        assert s.notional == pytest.approx(s.qty * entry, rel=1e-9)
        # total open risk <= 6%
        total_open = sum(p.risk_amount for p in opens)
        assert total_open + s.risk_amount <= 0.06 * equity * tol
        # same-direction <= 4%
        same = sum(p.risk_amount for p in opens if p.side.strip().lower() == side)
        assert same + s.risk_amount <= 0.04 * equity * tol
        # daily budget: today's loss + open + new <= 5% of day_start
        today_loss = max(0.0, day_start - equity)
        assert today_loss + total_open + s.risk_amount <= 0.05 * day_start * tol
        # margins <= equity
        assert sum(p.margin for p in opens) + s.margin <= equity * tol
        assert s.margin == pytest.approx(s.notional / lev, rel=1e-9)
        # other allowed-implies invariants
        assert _norm_pair(cand.pair) not in {_norm_pair(p.pair) for p in opens}
        assert (equity - day_start) / day_start > -0.05
        assert 3 <= lev <= 5
        assert s.notional >= min_notional * (1 - 1e-9)
        if qty_step is not None:
            k = s.qty / qty_step
            assert abs(k - round(k)) < 1e-6
        liq = liquidation_price(entry, side, lev, 0.004)
        assert abs(entry - liq) >= 1.5 * abs(entry - stop) * (1 - 1e-9)

    # make sure the loop is not vacuous
    assert allowed_n >= 50, allowed_n
    assert denied_n >= 50, denied_n
