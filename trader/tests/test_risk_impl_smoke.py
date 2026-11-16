import pytest

from trader_core.risk import (HARD_LIMITS, LOCKED_CFG, AccountState, Candidate,
                              OpenPosition, RiskConfig, check_entry, loss_at_stop,
                              size_position)

CFG = RiskConfig()
NAN = float("nan")


def test_size_hits_target():
    r = size_position(1000, 100, 90, "long", 3, CFG)
    assert r.risk_amount == pytest.approx(0.014 * 1000, rel=1e-9)
    assert r.risk_amount == pytest.approx(loss_at_stop(r.qty, 100, 90, CFG))


def test_allowed_and_rules():
    st = AccountState(1000, 1000, [])
    d = check_entry(st, Candidate("A", "long", 100, 95, 3))
    assert d.allowed and d.size
    assert not check_entry(st, Candidate("A", "long", 100, 105, 3)).allowed
    assert not check_entry(st, Candidate("A", "long", 100, 95, 9)).allowed
    assert not check_entry(AccountState(950, 1000, []), Candidate("A", "long", 100, 95, 3)).allowed
    st2 = AccountState(1000, 1000, [OpenPosition("a:usdt", "long", 1.0, 10.0)])
    assert not check_entry(st2, Candidate("A", "long", 100, 95, 3)).allowed


def test_fail_closed_and_config():
    d = check_entry(None, Candidate("A", "long", 100, 95, 3), CFG)
    assert not d.allowed and d.reason.startswith("iç hata")
    with pytest.raises(ValueError):
        RiskConfig(target_trade_risk=0.03)
    with pytest.raises(ValueError):
        RiskConfig(max_leverage=10)
    with pytest.raises(ValueError):
        RiskConfig(max_notional_ratio=1.5)
    assert LOCKED_CFG == RiskConfig() and HARD_LIMITS["max_leverage"] == 5


def test_nan_open_risk_denied():
    st = AccountState(1000, 1000, [OpenPosition("B/USDT", "long", NAN, 0.0)])
    assert not check_entry(st, Candidate("A", "long", 100, 95, 3)).allowed


def test_upper_side_counts_same_direction():
    # 0.03 * 1000 = 30 aynı yönde açık risk; yeni ~14 -> 44 > 40 red
    st = AccountState(1000, 1000, [OpenPosition("B", "LONG", 30.0, 10.0)])
    d = check_entry(st, Candidate("A", "long", 100, 95, 3))
    assert not d.allowed and "aynı yön" in d.reason
    st = AccountState(1000, 1000, [OpenPosition("B", "short", 30.0, 10.0)])
    assert check_entry(st, Candidate("A", "long", 100, 95, 3)).allowed


def test_tight_stop_notional_capped():
    r = size_position(1000, 100, 99.7, "long", 5, CFG)
    assert r.notional <= 1000
    assert r.risk_amount <= 0.014 * 1000
    d = check_entry(AccountState(1000, 1000, []), Candidate("A", "long", 100, 99.7, 5))
    assert d.allowed and d.size.notional <= 1000


def test_step_rounding_never_increases_risk():
    base = size_position(1000, 100, 95, "long", 3, CFG)
    for step in (0.001, 0.1, 0.3, 1.0):
        r = size_position(1000, 100, 95, "long", 3, CFG, qty_step=step)
        assert r.qty <= base.qty and r.risk_amount <= base.risk_amount
    with pytest.raises(ValueError):
        size_position(1000, 100, 95, "long", 3, CFG, qty_step=100.0)
    with pytest.raises(ValueError):
        size_position(1000, 100, 95, "long", 3, CFG, min_notional=10_000)


def test_daily_budget_and_margin_sum():
    # bugünkü kayıp 40 + yeni ~14 > 50
    assert not check_entry(AccountState(960, 1000, []), Candidate("A", "long", 100, 95, 3)).allowed
    # teminat toplamı equity'yi aşar
    st = AccountState(1000, 1000, [OpenPosition("B", "short", 1.0, 990.0)])
    assert not check_entry(st, Candidate("A", "long", 100, 95, 3)).allowed
