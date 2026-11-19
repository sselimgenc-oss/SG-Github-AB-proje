"""Spec-driven tests for the per-arm virtual bankroll report.

Source of truth: docs/motor/sanal-kasa-spec.md (written independently of the
implementation). Covers arm_virtual_bankroll and the "kasa" key that
arm_scorecard adds to every arm block.
"""

import pytest

from trader_core.counterfactual import arm_scorecard, arm_virtual_bankroll

T1 = "T1@1h"
T2 = "T2@4h"


def _c(arm_id, ts, r, taken=True, asset_class="crypto", decision_id=None):
    return {
        "arm_id": arm_id,
        "asset_class": asset_class,
        "taken": taken,
        "ts": ts,
        "r": r,
        "decision_id": decision_id or f"{arm_id}-{ts}",
    }


def _kasa_by_arm(scorecard):
    """Map arm_id -> kasa value from an arm_scorecard result.

    Accepts either a dict keyed by arm_id or a list of blocks carrying "arm_id".
    """
    if isinstance(scorecard, dict):
        return {arm: block["kasa"] for arm, block in scorecard.items()}
    return {block["arm_id"]: block["kasa"] for block in scorecard}


# --- compounding -----------------------------------------------------------

def test_compounding_risk_001_two_steps():
    # 1000 * 1.02 * 0.99 = 1009.8
    cands = [
        _c(T1, "2026-11-19T10:00:00Z", 2.0),
        _c(T1, "2026-11-19T11:00:00Z", -1.0),
    ]
    out = arm_virtual_bankroll(cands)
    taken = out[T1]["taken"]
    assert taken["n"] == 2
    assert taken["equity"] == pytest.approx(1009.8)
    assert taken["return_pct"] == pytest.approx(0.98)
    # peak 1020 -> trough 1009.8 => 1.00 %
    assert taken["max_dd_pct"] == pytest.approx(1.0)


def test_custom_start_and_risk_are_honoured():
    # 500 * (1 + 0.1 * 1) = 550
    cands = [_c(T1, "2026-11-19T10:00:00Z", 1.0)]
    out = arm_virtual_bankroll(cands, start=500.0, risk=0.1)
    assert out[T1]["taken"]["equity"] == pytest.approx(550.0)
    assert out[T1]["taken"]["return_pct"] == pytest.approx(10.0)


# --- taken vs counterfactual series ----------------------------------------

def test_taken_and_cf_series_differ_as_specified():
    cands = [
        _c(T1, "2026-11-19T10:00:00Z", 1.0, taken=True),
        _c(T1, "2026-11-19T11:00:00Z", -2.0, taken=False),
    ]
    out = arm_virtual_bankroll(cands)

    taken = out[T1]["taken"]
    assert taken["n"] == 1
    assert taken["equity"] == pytest.approx(1010.0)
    assert taken["return_pct"] == pytest.approx(1.0)
    assert taken["max_dd_pct"] == pytest.approx(0.0)

    cf = out[T1]["cf"]
    # 1000 * 1.01 * 0.98 = 989.8, drawdown from peak 1010 is 2.00 %
    assert cf["n"] == 2
    assert cf["equity"] == pytest.approx(989.8)
    assert cf["return_pct"] == pytest.approx(-1.02)
    assert cf["max_dd_pct"] == pytest.approx(2.0)


def test_taken_series_requires_taken_is_true():
    # Spec: taken series uses only `taken is True`; truthy non-bool is excluded
    # from "taken" but still belongs to the counterfactual series.
    cands = [_c(T1, "2026-11-19T10:00:00Z", 1.0, taken=1)]
    out = arm_virtual_bankroll(cands)
    assert out[T1]["taken"]["n"] == 0
    assert out[T1]["cf"]["n"] == 1


# --- r None is ignored ------------------------------------------------------

def test_r_none_is_ignored_in_both_series():
    cands = [
        _c(T1, "2026-11-19T10:00:00Z", None, taken=True),
        _c(T1, "2026-11-19T11:00:00Z", None, taken=False),
        _c(T1, "2026-11-19T12:00:00Z", 1.0, taken=True),
    ]
    out = arm_virtual_bankroll(cands)
    assert out[T1]["taken"]["n"] == 1
    assert out[T1]["taken"]["equity"] == pytest.approx(1010.0)
    assert out[T1]["cf"]["n"] == 1
    assert out[T1]["cf"]["equity"] == pytest.approx(1010.0)


def test_arm_with_only_r_none_is_empty():
    cands = [_c(T2, "2026-11-19T10:00:00Z", None, taken=True)]
    out = arm_virtual_bankroll(cands)
    empty = {"n": 0, "equity": 1000.0, "return_pct": 0.0, "max_dd_pct": 0.0}
    assert out[T2]["taken"] == empty
    assert out[T2]["cf"] == empty


# --- ts ordering ------------------------------------------------------------

def test_unsorted_input_is_sorted_by_ts_before_compounding():
    # Sorted by ts: -5 (10:00), +10 (11:00), -5 (12:00)
    #   path 1000 -> 950 -> 1045 -> 992.75 ; max dd from peak 1045 = 5.00 %
    # Input order (unsorted): -5 (12:00), -5 (10:00), +10 (11:00)
    #   would give 1000 -> 950 -> 902.5 -> ... with max dd 9.75 %.
    cands = [
        _c(T1, "2026-11-19T12:00:00Z", -5.0, decision_id="late"),
        _c(T1, "2026-11-19T10:00:00Z", -5.0, decision_id="early"),
        _c(T1, "2026-11-19T11:00:00Z", 10.0, decision_id="mid"),
    ]
    out = arm_virtual_bankroll(cands)
    taken = out[T1]["taken"]
    assert taken["n"] == 3
    assert taken["equity"] == pytest.approx(992.75)
    assert taken["max_dd_pct"] == pytest.approx(5.0)


# --- stable tie order -------------------------------------------------------

def test_equal_ts_keeps_input_order():
    # Same timestamp: input order must be preserved.
    # Path -5, +10, -5 : 1000 -> 950 -> 1045 -> 992.75, max dd 5.00 %.
    # (Any reordering of these ties yields max dd 9.75 %.)
    ts = "2026-11-19T11:00:00Z"
    cands = [
        _c(T1, ts, -5.0, decision_id="a"),
        _c(T1, ts, 10.0, decision_id="b"),
        _c(T1, ts, -5.0, decision_id="c"),
    ]
    out = arm_virtual_bankroll(cands)
    assert out[T1]["taken"]["equity"] == pytest.approx(992.75)
    assert out[T1]["taken"]["max_dd_pct"] == pytest.approx(5.0)


# --- max drawdown -----------------------------------------------------------

def test_max_dd_measured_from_start_when_first_step_is_loss():
    cands = [_c(T1, "2026-11-19T10:00:00Z", -10.0)]
    out = arm_virtual_bankroll(cands)
    assert out[T1]["taken"]["equity"] == pytest.approx(900.0)
    assert out[T1]["taken"]["return_pct"] == pytest.approx(-10.0)
    assert out[T1]["taken"]["max_dd_pct"] == pytest.approx(10.0)


def test_max_dd_zero_when_no_drawdown():
    cands = [
        _c(T1, "2026-11-19T10:00:00Z", 1.0),
        _c(T1, "2026-11-19T11:00:00Z", 2.0),
    ]
    out = arm_virtual_bankroll(cands)
    assert out[T1]["taken"]["max_dd_pct"] == 0.0


# --- no-negative floor ------------------------------------------------------

def test_equity_floors_at_zero_and_stays_there():
    # risk 0.5, r -3 => factor 1 + 0.5 * -3 = -0.5 => equity clamped to 0.
    # Later positive r must not revive it.
    cands = [
        _c(T1, "2026-11-19T10:00:00Z", -3.0),
        _c(T1, "2026-11-19T11:00:00Z", 10.0),
    ]
    out = arm_virtual_bankroll(cands, risk=0.5)
    taken = out[T1]["taken"]
    assert taken["n"] == 2
    assert taken["equity"] == 0.0
    assert taken["return_pct"] == pytest.approx(-100.0)
    assert taken["max_dd_pct"] == pytest.approx(100.0)


# --- empty arms -------------------------------------------------------------

def test_arms_keyword_adds_empty_arm_entries():
    cands = [_c(T1, "2026-11-19T10:00:00Z", 1.0)]
    out = arm_virtual_bankroll(cands, arms=(T1, "T9@1h"))
    assert "T9@1h" in out
    empty = {"n": 0, "equity": 1000.0, "return_pct": 0.0, "max_dd_pct": 0.0}
    assert out["T9@1h"]["taken"] == empty
    assert out["T9@1h"]["cf"] == empty
    assert out[T1]["taken"]["n"] == 1


def test_arms_keyword_with_no_candidates_at_all():
    out = arm_virtual_bankroll([], arms=("T9@1h",))
    empty = {"n": 0, "equity": 1000.0, "return_pct": 0.0, "max_dd_pct": 0.0}
    assert out["T9@1h"] == {"taken": empty, "cf": empty}


# --- argument validation ----------------------------------------------------

@pytest.mark.parametrize("start", [0, 0.0, -1000.0])
def test_non_positive_start_raises(start):
    with pytest.raises(ValueError):
        arm_virtual_bankroll([_c(T1, "2026-11-19T10:00:00Z", 1.0)], start=start)


@pytest.mark.parametrize("risk", [0, 0.0, -0.01])
def test_non_positive_risk_raises(risk):
    with pytest.raises(ValueError):
        arm_virtual_bankroll([_c(T1, "2026-11-19T10:00:00Z", 1.0)], risk=risk)


# --- rounding ---------------------------------------------------------------

def test_values_rounded_to_two_decimals():
    # r = 1/3, risk 0.01 => equity 1000 * (1 + 0.01/3) = 1003.3333...
    cands = [_c(T1, "2026-11-19T10:00:00Z", 1.0 / 3.0)]
    out = arm_virtual_bankroll(cands)
    taken = out[T1]["taken"]
    assert taken["equity"] == 1003.33
    assert taken["return_pct"] == 0.33
    assert taken["max_dd_pct"] == 0.0

    # r = -1/3 => dd = 0.3333 % => 0.33
    cands_down = [_c(T1, "2026-11-19T10:00:00Z", -1.0 / 3.0)]
    out_down = arm_virtual_bankroll(cands_down)
    assert out_down[T1]["taken"]["max_dd_pct"] == 0.33
    assert out_down[T1]["taken"]["equity"] == 996.67


def test_output_numbers_have_at_most_two_decimals():
    cands = [
        _c(T1, "2026-11-19T10:00:00Z", 1.0 / 7.0),
        _c(T1, "2026-11-19T11:00:00Z", -2.0 / 9.0),
    ]
    out = arm_virtual_bankroll(cands)
    for series in out[T1].values():
        for key in ("equity", "return_pct", "max_dd_pct"):
            assert series[key] == round(series[key], 2)


# --- kasa key in arm_scorecard ---------------------------------------------

def test_scorecard_blocks_contain_kasa_equal_to_virtual_bankroll():
    cands = [
        _c(T1, "2026-11-19T10:00:00Z", 2.0, taken=True),
        _c(T1, "2026-11-19T11:00:00Z", -1.0, taken=False),
        _c(T2, "2026-11-19T12:00:00Z", -4.0, taken=True),
    ]
    bankroll = arm_virtual_bankroll(cands)
    kasa = _kasa_by_arm(arm_scorecard(cands))

    assert set(kasa) >= {T1, T2}
    for arm_id in (T1, T2):
        assert kasa[arm_id] == bankroll[arm_id]


def test_scorecard_kasa_uses_default_start_and_risk():
    cands = [_c(T1, "2026-11-19T10:00:00Z", 2.0)]
    kasa = _kasa_by_arm(arm_scorecard(cands))
    assert kasa[T1]["taken"]["equity"] == pytest.approx(1020.0)
    assert kasa[T1]["taken"]["return_pct"] == pytest.approx(2.0)
