import pytest

from trader_core.risk import (AccountState, Candidate, OpenPosition, RiskConfig,
                              check_entry, loss_at_stop, size_position)

CFG = RiskConfig()


def test_size_hits_target():
    r = size_position(1000, 100, 98, "long", 3, CFG)
    assert r.risk_amount == pytest.approx(0.014 * 1000, rel=1e-9)
    assert r.risk_amount == pytest.approx(loss_at_stop(r.qty, 100, 98, CFG))


def test_allowed_and_rules():
    st = AccountState(1000, 1000, [])
    d = check_entry(st, Candidate("A", "long", 100, 95, 3), CFG)
    assert d.allowed and d.size
    assert not check_entry(st, Candidate("A", "long", 100, 105, 3), CFG).allowed
    assert not check_entry(st, Candidate("A", "long", 100, 95, 9), CFG).allowed
    assert not check_entry(AccountState(940, 1000, []), Candidate("A", "long", 100, 95, 3), CFG).allowed
    st2 = AccountState(1000, 1000, [OpenPosition("A", "long", 1.0)])
    assert not check_entry(st2, Candidate("A", "long", 100, 95, 3), CFG).allowed


def test_fail_closed_and_config():
    d = check_entry(None, Candidate("A", "long", 100, 95, 3), CFG)
    assert not d.allowed and d.reason.startswith("iç hata")
    with pytest.raises(ValueError):
        RiskConfig(target_trade_risk=0.03)
