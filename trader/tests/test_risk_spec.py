"""Independent spec-based tests for trader_core.risk.

Written ONLY from docs/risk-kilidi-spec.md (not from the implementation).
Default config: max_trade_risk 2%, target 1.4%, fee 0.05%, slippage 0.05%
(=> 0.1% = 0.001 per side), daily_max_loss 5%, max_open_risk 6%,
max_same_dir_risk 4%, leverage 3..5, mmr 0.4%, liq_safety_factor 1.5.
"""
import dataclasses
import math
import random

import pytest

import trader_core.risk as risk
from trader_core.risk import (
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


# --------------------------------------------------------------------------
# helpers
# --------------------------------------------------------------------------
def mk_state(equity=1000.0, day_start=1000.0, open_positions=()):
    return AccountState(
        equity=equity,
        day_start_equity=day_start,
        open_positions=list(open_positions),
    )


def mk_cand(pair=BTC, side="long", entry=60000.0, stop=59100.0, leverage=5):
    return Candidate(pair=pair, side=side, entry=entry, stop=stop, leverage=leverage)


def pos(pair, side, risk_amount):
    return OpenPosition(pair=pair, side=side, risk_amount=risk_amount)


def assert_denied(dec):
    assert isinstance(dec, Decision)
    assert dec.allowed is False
    assert isinstance(dec.reason, str) and dec.reason.strip() != ""


def reason_of(state, cand, cfg=CFG):
    dec = check_entry(state, cand, cfg)
    assert_denied(dec)
    return dec.reason


# --------------------------------------------------------------------------
# RiskConfig
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


def test_riskconfig_is_frozen():
    c = RiskConfig()
    with pytest.raises(dataclasses.FrozenInstanceError):
        c.max_trade_risk = 0.5


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
        {"min_leverage": -3},
        # target > max (default target 0.014 > max 0.01)
        {"max_trade_risk": 0.01},
        {"target_trade_risk": 0.03},  # 0.03 > default max 0.02
        # min_leverage > max_leverage
        {"min_leverage": 6, "max_leverage": 5},
        {"min_leverage": 4, "max_leverage": 3},
    ],
)
def test_riskconfig_invalid_raises_valueerror(kwargs):
    with pytest.raises(ValueError):
        RiskConfig(**kwargs)


def test_riskconfig_valid_custom_ok():
    c = RiskConfig(max_trade_risk=0.03, target_trade_risk=0.02, min_leverage=2, max_leverage=10)
    assert c.max_leverage == 10 and c.target_trade_risk == 0.02


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
    # long: 100 * (1 - 1/3 + 0.004) = 100 * 0.6706667 = 67.066667
    assert liquidation_price(100.0, "long", 3, 0.004) == pytest.approx(100 * (1 - 1 / 3 + 0.004), rel=REL)
    assert liquidation_price(100.0, "long", 3, 0.004) == pytest.approx(67.0666667, rel=1e-7)
    # short: 100 * (1 + 1/3 - 0.004) = 132.933333
    assert liquidation_price(100.0, "short", 3, 0.004) == pytest.approx(132.9333333, rel=1e-7)


def test_liq_zero_mmr():
    # mmr = 0: long 200*(1-0.25)=150 ; short 200*(1+0.25)=250 (leverage 4)
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
    # price loss 2*5 = 10 ; entry fee 2*100*0.001 = 0.2 ; stop fee 2*95*0.001 = 0.19
    # total 10.39
    assert loss_at_stop(2.0, 100.0, 95.0, CFG) == pytest.approx(10.39, rel=REL)


def test_loss_at_stop_short_uses_abs():
    # qty 1, entry 100, stop 105: 5 + 0.1 + 0.105 = 5.205
    assert loss_at_stop(1.0, 100.0, 105.0, CFG) == pytest.approx(5.205, rel=REL)


def test_loss_at_stop_custom_costs():
    cfg = RiskConfig(fee_rate=0.001, slippage_rate=0.002)  # 0.003 per side
    # qty 1, entry 100, stop 90: 10 + 100*0.003 + 90*0.003 = 10 + 0.3 + 0.27 = 10.57
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
    # per-unit loss = 900 + (60000 + 59100)*0.001 = 900 + 119.1 = 1019.1
    # target = 0.014*1000 = 14 -> qty = 14/1019.1 ~= 0.0137376
    # notional = qty*60000 = 840000/1019.1 ~= 824.257 ; margin = notional/5 ~= 164.851
    r = size_position(1000.0, 60000.0, 59100.0, "long", 5, CFG)
    assert isinstance(r, SizeResult)
    assert r.qty == pytest.approx(14 / 1019.1, rel=1e-6)
    assert r.notional == pytest.approx(840000 / 1019.1, rel=1e-6)
    assert r.margin == pytest.approx(r.notional / 5, rel=REL)
    assert r.margin == pytest.approx(840000 / 1019.1 / 5, rel=1e-6)
    assert r.risk_amount == pytest.approx(14.0, rel=1e-6)
    assert r.risk_amount <= 14.0 * (1 + REL)
    assert r.risk_amount <= 0.02 * 1000.0
    assert r.risk_amount == pytest.approx(loss_at_stop(r.qty, 60000.0, 59100.0, CFG), rel=REL)


def test_size_realistic_short_btc():
    # entry 60000, stop 60900: 900 + (60000+60900)*0.001 = 900 + 120.9 = 1020.9
    # qty = 14/1020.9 ; notional = 840000/1020.9
    r = size_position(1000.0, 60000.0, 60900.0, "short", 5, CFG)
    assert r.qty == pytest.approx(14 / 1020.9, rel=1e-6)
    assert r.notional == pytest.approx(840000 / 1020.9, rel=1e-6)
    assert r.margin == pytest.approx(r.notional / 5, rel=REL)
    assert r.risk_amount == pytest.approx(14.0, rel=1e-6)
    assert r.risk_amount <= 14.0 * (1 + REL)


def test_size_tight_stop_fees_dominate():
    # equity 1000, entry 100, stop 99.9, lev 5
    # per-unit = 0.1 + (100 + 99.9)*0.001 = 0.1 + 0.1999 = 0.2999
    # qty = 14/0.2999 ~= 46.682 ; notional = 1400/0.2999 ~= 4668.22 ; margin ~= 933.64 (< 1000)
    r = size_position(1000.0, 100.0, 99.9, "long", 5, CFG)
    assert r.qty == pytest.approx(14 / 0.2999, rel=1e-6)
    assert r.notional == pytest.approx(1400 / 0.2999, rel=1e-6)
    assert r.margin == pytest.approx(1400 / 0.2999 / 5, rel=1e-6)
    assert r.margin <= 1000.0
    assert r.risk_amount == pytest.approx(14.0, rel=1e-6)
    # a fee-blind sizing (14/0.1 = 140 units) would blow the risk budget
    assert r.qty < 14 / 0.1
    assert r.risk_amount <= 0.02 * 1000.0


def test_size_margin_exceeding_equity_rejected():
    # entry 60000, stop 59994, lev 5: per-unit = 6 + 119.994 = 125.994
    # qty = 14/125.994 ; notional = 840000/125.994 ~= 6667.0 ; margin ~= 1333.4 > 1000
    with pytest.raises(Exception):
        size_position(1000.0, 60000.0, 59994.0, "long", 5, CFG)


def test_size_margin_just_ok_vs_rejected_by_leverage():
    # entry 100, stop 99.9 : notional ~= 4668.2
    # lev 5 -> margin ~933.6 <= 1000 OK ; lev 3 -> margin ~1556.1 > 1000 rejected
    ok = size_position(1000.0, 100.0, 99.9, "long", 5, CFG)
    assert ok.margin <= 1000.0
    with pytest.raises(Exception):
        size_position(1000.0, 100.0, 99.9, "long", 3, CFG)


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
    # entry 100 stop 90: per-unit 10 + 0.19*1000/1000... = 10 + (190*0.001)= 10.19
    # qty = 10/10.19
    r = size_position(1000.0, 100.0, 90.0, "long", 5, cfg)
    assert r.qty == pytest.approx(10 / 10.19, rel=1e-6)
    assert r.risk_amount == pytest.approx(10.0, rel=1e-6)


def test_size_never_exceeds_max_across_grid():
    for entry in (0.5, 3.0, 100.0, 60000.0):
        for frac in (0.001, 0.005, 0.02, 0.1):
            for side in ("long", "short"):
                stop = entry * (1 - frac) if side == "long" else entry * (1 + frac)
                try:
                    r = size_position(1000.0, entry, stop, side, 5, CFG)
                except Exception:
                    continue  # margin > equity rejections are allowed
                assert r.risk_amount <= 0.014 * 1000.0 * (1 + REL)
                assert r.risk_amount <= 0.02 * 1000.0
                assert r.margin <= 1000.0 * (1 + REL)


# --------------------------------------------------------------------------
# check_entry : happy path (rule 10)
# --------------------------------------------------------------------------
def test_entry_allowed_realistic():
    d = check_entry(mk_state(), mk_cand(), CFG)
    assert isinstance(d, Decision)
    assert d.allowed is True
    assert isinstance(d.reason, str)
    assert isinstance(d.size, SizeResult)
    assert d.size.risk_amount == pytest.approx(14.0, rel=1e-6)
    assert d.size.risk_amount <= 0.02 * 1000.0
    assert d.size.margin <= 1000.0


def test_entry_allowed_short():
    # short: liq = 60000*1.196 = 71760 -> dist 11760 >= 1.5*900 = 1350
    d = check_entry(mk_state(), mk_cand(side="short", stop=60900.0), CFG)
    assert d.allowed is True and d.size is not None


def test_entry_allowed_tight_stop():
    d = check_entry(mk_state(), mk_cand(pair=ETH, entry=100.0, stop=99.9), CFG)
    assert d.allowed is True
    assert d.size.risk_amount == pytest.approx(14.0, rel=1e-6)


# --------------------------------------------------------------------------
# Rule 1: invalid input
# --------------------------------------------------------------------------
@pytest.mark.parametrize("entry", [float("nan"), float("inf"), float("-inf"), 0.0, -1.0])
def test_rule1_bad_entry(entry):
    assert_denied(check_entry(mk_state(), mk_cand(entry=entry), CFG))


@pytest.mark.parametrize("stop", [float("nan"), float("inf"), float("-inf"), 0.0, -5.0])
def test_rule1_bad_stop(stop):
    assert_denied(check_entry(mk_state(), mk_cand(stop=stop), CFG))
    assert_denied(check_entry(mk_state(), mk_cand(side="short", stop=stop), CFG))


@pytest.mark.parametrize("equity", [0.0, -10.0, float("nan"), float("inf")])
def test_rule1_bad_equity(equity):
    assert_denied(check_entry(mk_state(equity=equity), mk_cand(), CFG))


@pytest.mark.parametrize("side", ["buy", "LONG", "Short", "", "both", None])
def test_rule1_bad_side(side):
    assert_denied(check_entry(mk_state(), mk_cand(side=side), CFG))


# --------------------------------------------------------------------------
# Rule 2: stop on wrong side
# --------------------------------------------------------------------------
@pytest.mark.parametrize("stop", [60000.0, 60001.0, 65000.0])
def test_rule2_long_stop_not_below_entry(stop):
    assert_denied(check_entry(mk_state(), mk_cand(side="long", stop=stop), CFG))


@pytest.mark.parametrize("stop", [60000.0, 59999.0, 55000.0])
def test_rule2_short_stop_not_above_entry(stop):
    assert_denied(check_entry(mk_state(), mk_cand(side="short", stop=stop), CFG))


# --------------------------------------------------------------------------
# Rule 3: leverage range
# --------------------------------------------------------------------------
@pytest.mark.parametrize("lev", [0, -5, 1, 2, 6, 10, 125])
def test_rule3_leverage_out_of_range(lev):
    assert_denied(check_entry(mk_state(), mk_cand(leverage=lev), CFG))


@pytest.mark.parametrize("lev", [3, 4, 5])
def test_rule3_leverage_in_range_ok(lev):
    # lev 3 margin: notional ~824.26 /3 = 274.8 <= 1000 ; liq dist at 3x = 60000*(1/3-0.004)=19760 >= 1350
    assert check_entry(mk_state(), mk_cand(leverage=lev), CFG).allowed is True


# --------------------------------------------------------------------------
# Rule 4: daily loss
# --------------------------------------------------------------------------
def test_rule4_daily_loss_exactly_minus_5pct_denied():
    # (950 - 1000)/1000 = -0.05 <= -0.05 -> denied
    assert_denied(check_entry(mk_state(equity=950.0, day_start=1000.0), mk_cand(), CFG))


def test_rule4_daily_loss_beyond_denied():
    # (900-1000)/1000 = -0.10
    assert_denied(check_entry(mk_state(equity=900.0, day_start=1000.0), mk_cand(), CFG))


def test_rule4_daily_loss_just_inside_allowed():
    # (950.5-1000)/1000 = -0.0495 > -0.05 -> allowed
    assert check_entry(mk_state(equity=950.5, day_start=1000.0), mk_cand(), CFG).allowed is True


def test_rule4_daily_gain_allowed():
    # (1100-1000)/1000 = +0.10
    assert check_entry(mk_state(equity=1100.0, day_start=1000.0), mk_cand(), CFG).allowed is True


def test_rule4_custom_limit():
    cfg = RiskConfig(daily_max_loss=0.03)
    # (970-1000)/1000 = -0.03 <= -0.03 -> denied ; 971 -> -0.029 allowed
    assert_denied(check_entry(mk_state(equity=970.0), mk_cand(), cfg))
    assert check_entry(mk_state(equity=971.0), mk_cand(), cfg).allowed is True


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
    # total 5 + 14 = 19 <= 60 ; same-dir 19 <= 40
    assert check_entry(st, mk_cand(pair=BTC), CFG).allowed is True


# --------------------------------------------------------------------------
# Rule 6: sizing failure
# --------------------------------------------------------------------------
def test_rule6_sizing_rejection_denied():
    # margin ~1333 > equity 1000 (see size test); liq dist 11760 >= 1.5*6 so only rule 6 hits
    assert_denied(check_entry(mk_state(), mk_cand(stop=59994.0), CFG))


# --------------------------------------------------------------------------
# Rule 7: liquidation safety
# --------------------------------------------------------------------------
def test_rule7_wide_stop_5x_long_denied():
    # entry 100, stop 80, 5x: liq = 80.4, |100-80.4| = 19.6 < 1.5*20 = 30 -> denied
    assert_denied(check_entry(mk_state(), mk_cand(pair=ETH, entry=100.0, stop=80.0, leverage=5), CFG))


def test_rule7_wide_stop_5x_short_denied():
    # entry 100, stop 120, 5x: liq = 119.6, dist 19.6 < 30 -> denied
    assert_denied(
        check_entry(mk_state(), mk_cand(pair=ETH, side="short", entry=100.0, stop=120.0, leverage=5), CFG)
    )


def test_rule7_same_stop_ok_at_3x():
    # 3x long: liq = 67.0667, dist 32.933 >= 30 -> allowed (same candidate denied at 5x)
    assert check_entry(mk_state(), mk_cand(pair=ETH, entry=100.0, stop=80.0, leverage=3), CFG).allowed is True
    assert_denied(check_entry(mk_state(), mk_cand(pair=ETH, entry=100.0, stop=80.0, leverage=5), CFG))


def test_rule7_boundary_5x_long():
    # liq dist 19.6 ; threshold stop dist d* = 19.6/1.5 = 13.0667 (stop 86.9333)
    # stop 87 -> d=13 -> 19.5 <= 19.6 allowed ; stop 86.8 -> d=13.2 -> 19.8 > 19.6 denied
    assert check_entry(mk_state(), mk_cand(pair=ETH, entry=100.0, stop=87.0, leverage=5), CFG).allowed is True
    assert_denied(check_entry(mk_state(), mk_cand(pair=ETH, entry=100.0, stop=86.8, leverage=5), CFG))


def test_rule7_boundary_5x_short():
    # symmetric: stop 113 -> d=13 allowed ; stop 113.2 -> d=13.2 denied
    assert (
        check_entry(mk_state(), mk_cand(pair=ETH, side="short", entry=100.0, stop=113.0, leverage=5), CFG).allowed
        is True
    )
    assert_denied(
        check_entry(mk_state(), mk_cand(pair=ETH, side="short", entry=100.0, stop=113.2, leverage=5), CFG)
    )


# --------------------------------------------------------------------------
# Rule 8: total open risk (cap 6% of 1000 = 60; new trade risk ~= 14)
# --------------------------------------------------------------------------
def test_rule8_total_open_risk_inside_cap_allowed():
    # three shorts 3 * 15.3 = 45.9 ; + 14 = 59.9 <= 60 ; long same-dir = 14 <= 40
    opens = [pos(ETH, "short", 15.3), pos(SOL, "short", 15.3), pos(XRP, "short", 15.3)]
    assert check_entry(mk_state(open_positions=opens), mk_cand(), CFG).allowed is True


def test_rule8_total_open_risk_over_cap_denied():
    # 3 * 15.4 = 46.2 ; + 14 = 60.2 > 60
    opens = [pos(ETH, "short", 15.4), pos(SOL, "short", 15.4), pos(XRP, "short", 15.4)]
    assert_denied(check_entry(mk_state(open_positions=opens), mk_cand(), CFG))


def test_rule8_cap_scales_with_equity():
    # equity 2000 -> cap 120, new risk 28. opens 91 + 28 = 119 ok ; 93 + 28 = 121 denied
    ok = [pos(ETH, "short", 30.0), pos(SOL, "short", 30.0), pos(XRP, "short", 31.0)]
    bad = [pos(ETH, "short", 31.0), pos(SOL, "short", 31.0), pos(XRP, "short", 31.0)]
    assert check_entry(mk_state(2000.0, 2000.0, ok), mk_cand(), CFG).allowed is True
    assert_denied(check_entry(mk_state(2000.0, 2000.0, bad), mk_cand(), CFG))


# --------------------------------------------------------------------------
# Rule 9: same-direction risk (cap 4% of 1000 = 40)
# --------------------------------------------------------------------------
def test_rule9_same_dir_inside_cap_allowed():
    # longs 13 + 12 = 25 ; + 14 = 39 <= 40 ; total 39 <= 60
    opens = [pos(ETH, "long", 13.0), pos(SOL, "long", 12.0)]
    assert check_entry(mk_state(open_positions=opens), mk_cand(), CFG).allowed is True


def test_rule9_same_dir_over_cap_denied():
    # longs 13 + 13.1 = 26.1 ; + 14 = 40.1 > 40 ; total 40.1 <= 60 so only rule 9
    opens = [pos(ETH, "long", 13.0), pos(SOL, "long", 13.1)]
    assert_denied(check_entry(mk_state(open_positions=opens), mk_cand(), CFG))


def test_rule9_opposite_direction_still_allowed():
    # three longs 3 * 13.5 = 40.5 (already over the 40 same-dir cap on their own)
    opens = [pos(ETH, "long", 13.5), pos(SOL, "long", 13.5), pos(XRP, "long", 13.5)]
    st = mk_state(open_positions=opens)
    # long candidate: same-dir 40.5 + 14 = 54.5 > 40 -> denied
    assert_denied(check_entry(st, mk_cand(side="long"), CFG))
    # short candidate: same-dir = 14 <= 40 ; total 54.5 <= 60 -> allowed
    d = check_entry(st, mk_cand(side="short", stop=60900.0), CFG)
    assert d.allowed is True and d.size is not None


def test_rule9_mirror_for_shorts():
    opens = [pos(ETH, "short", 13.5), pos(SOL, "short", 13.5), pos(XRP, "short", 13.5)]
    st = mk_state(open_positions=opens)
    assert_denied(check_entry(st, mk_cand(side="short", stop=60900.0), CFG))
    assert check_entry(st, mk_cand(side="long"), CFG).allowed is True


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
    dup = [pos(BTC, "long", 5.0)]
    tight = mk_cand(stop=59994.0)  # margin > equity
    both = reason_of(mk_state(open_positions=dup), tight)
    only5 = reason_of(mk_state(open_positions=dup), mk_cand())
    only6 = reason_of(mk_state(), tight)
    assert both == only5
    assert both != only6


def test_precedence_rule7_over_rule8():
    wide = mk_cand(pair=SOL, entry=100.0, stop=80.0, leverage=5)  # liq unsafe
    shorts = [pos(ETH, "short", 50.0)]  # 50 + ~14 = 64 > 60
    both = reason_of(mk_state(open_positions=shorts), wide)
    only7 = reason_of(mk_state(), wide)
    only8 = reason_of(mk_state(open_positions=shorts), mk_cand(pair=SOL, entry=100.0, stop=90.0, leverage=5))
    assert both == only7
    assert both != only8


def test_precedence_rule8_and_9_both_violated_denied():
    # longs 30 + shorts 30 = 60 ; new long 14 -> total 74 > 60 (rule 8), same-dir 44 > 40 (rule 9)
    opens = [pos(ETH, "long", 30.0), pos(SOL, "short", 30.0)]
    assert_denied(check_entry(mk_state(open_positions=opens), mk_cand(), CFG))


# --------------------------------------------------------------------------
# Fail-closed
# --------------------------------------------------------------------------
def test_failclosed_size_position_raises(monkeypatch):
    def boom(*a, **k):
        raise RuntimeError("kaboom")

    monkeypatch.setattr(risk, "size_position", boom)
    d = check_entry(mk_state(), mk_cand(), CFG)
    assert_denied(d)


def test_failclosed_size_position_returns_garbage(monkeypatch):
    monkeypatch.setattr(risk, "size_position", lambda *a, **k: object())
    d = check_entry(mk_state(), mk_cand(), CFG)
    assert_denied(d)


def test_failclosed_size_position_raises_zero_division(monkeypatch):
    def boom(*a, **k):
        raise ZeroDivisionError("x")

    monkeypatch.setattr(risk, "size_position", boom)
    assert_denied(check_entry(mk_state(), mk_cand(), CFG))


def test_failclosed_loss_at_stop_raises(monkeypatch):
    def boom(*a, **k):
        raise ArithmeticError("x")

    monkeypatch.setattr(risk, "loss_at_stop", boom)
    # may or may not be used internally; either way nothing may escape / allow
    d = check_entry(mk_state(), mk_cand(), CFG)
    assert isinstance(d, Decision)
    if not d.allowed:
        assert isinstance(d.reason, str) and d.reason


def test_failclosed_malformed_open_positions():
    st = mk_state(open_positions=[object()])
    assert_denied(check_entry(st, mk_cand(), CFG))


def test_failclosed_open_positions_none():
    st = AccountState(equity=1000.0, day_start_equity=1000.0, open_positions=None)
    assert_denied(check_entry(st, mk_cand(), CFG))


def test_failclosed_state_none():
    assert_denied(check_entry(None, mk_cand(), CFG))


def test_failclosed_candidate_none():
    assert_denied(check_entry(mk_state(), None, CFG))


def test_failclosed_non_numeric_fields():
    assert_denied(check_entry(mk_state(), mk_cand(entry="abc"), CFG))
    assert_denied(check_entry(mk_state(equity="lots"), mk_cand(), CFG))


def test_failclosed_zero_day_start_equity():
    # division by zero in the daily-loss ratio must not escape nor allow
    assert_denied(check_entry(mk_state(equity=1000.0, day_start=0.0), mk_cand(), CFG))


# --------------------------------------------------------------------------
# Property-style loop
# --------------------------------------------------------------------------
def test_property_allowed_decisions_respect_caps():
    rng = random.Random(20240601)
    pairs = [f"P{i}/USDT:USDT" for i in range(8)]
    allowed_n = denied_n = 0

    for _ in range(500):
        equity = rng.uniform(100.0, 100_000.0)
        day_start = equity * rng.uniform(0.95, 1.08)
        n_open = rng.randint(0, 4)
        open_idx = rng.sample(range(8), n_open)
        opens = [
            pos(pairs[i], rng.choice(["long", "short"]), rng.uniform(0.0, 0.015) * equity)
            for i in open_idx
        ]
        side = rng.choice(["long", "short"])
        entry = 10 ** rng.uniform(-2, 5)
        d = rng.uniform(0.002, 0.2)
        stop = entry * (1 - d) if side == "long" else entry * (1 + d)
        lev = rng.choice([3, 4, 5, 5, 4, 3, 2, 6])
        cand = mk_cand(pair=pairs[rng.randrange(8)], side=side, entry=entry, stop=stop, leverage=lev)
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
        # per-trade realized loss cap 2% (and target 1.4%)
        assert s.risk_amount <= 0.02 * equity
        assert s.risk_amount <= 0.014 * equity * (1 + REL)
        assert s.risk_amount == pytest.approx(loss_at_stop(s.qty, entry, stop, CFG), rel=1e-6)
        # total open risk cap 6%
        total = sum(p.risk_amount for p in opens) + s.risk_amount
        assert total <= 0.06 * equity * (1 + REL)
        # same-direction cap 4%
        same = sum(p.risk_amount for p in opens if p.side == side) + s.risk_amount
        assert same <= 0.04 * equity * (1 + REL)
        # other allowed-implies invariants
        assert cand.pair not in {p.pair for p in opens}
        assert (equity - day_start) / day_start > -0.05
        assert 3 <= lev <= 5
        assert s.margin <= equity * (1 + REL)
        assert s.margin == pytest.approx(s.notional / lev, rel=1e-6)
        liq = liquidation_price(entry, side, lev, 0.004)
        assert abs(entry - liq) >= 1.5 * abs(entry - stop) * (1 - 1e-9)

    # make sure the loop is not vacuous
    assert allowed_n >= 50
    assert denied_n >= 50
