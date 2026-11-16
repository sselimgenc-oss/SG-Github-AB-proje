import os
import sqlite3
from datetime import datetime, timedelta, timezone

import pytest

from trader_core import ledger as L
from trader_core.ledger import (DecisionEvent, LedgerConflictError, LedgerSchemaError, LedgerStateError,
                                LedgerValidationError, TradeEntry, TradeExit, open_ledger)

UTC = timezone.utc
PARAMS = {"range_width_atr": 4.0, "vol_ratio_max": 1.5, "edge_zone_atr": 0.25, "pullback_ema": 50,
          "stop_buffer_atr": 0.3, "trail_atr": 3.0, "range_target_frac": 0.75, "rr_min": 1.5,
          "trigger_tf": "1h"}
T0 = datetime(2026, 12, 1, 12, 0, tzinfo=UTC)


class Clock:
    def __init__(self, t=T0):
        self.t = t

    def __call__(self):
        return self.t


@pytest.fixture
def clock():
    return Clock()


@pytest.fixture
def led(tmp_path, clock):
    lg = open_ledger(tmp_path / "l.sqlite", "learner", clock=clock)
    lg.init_params(PARAMS, reason="baslangic")
    yield lg
    lg.close()


def r1(bar=datetime(2026, 12, 1, 10, 0, tzinfo=UTC), **kw):
    base = dict(
        bar_close_ts=bar, trigger_tf="1h", pair="ETH/USDT", side="long", setup="R1", regime="range",
        atr_ratio=1.1, rh=2100.0, rl=1980.0, rh_touches=2, rl_touches=3,
        features={"atr_1h": 20.0, "stop_dist_atr": 2.0, "atr_4h": 40.0, "wick_ratio": 0.5, "rr": 2.5,
                  "edge_dist_atr": 0.1},
        planned_entry=2000.0, planned_stop=1960.0, planned_target=2100.0, param_version_id=1,
        veto_status="allowed", veto_reason=None, risk_allowed=True, risk_reason="ok", size_qty=0.3,
        size_notional=600.0, size_margin=200.0, size_risk_amount=13.188, leverage=3,
        final_action="entered", skip_reason=None)
    base.update(kw)
    return DecisionEvent(**base)


def test_hash_and_init(led):
    assert led.get_active_params().version_id == 1
    assert led.get_version(1).params_hash == "de6ff80013f1ae38fbe23322363fb0d0d6aa031569ef22ac2e7efd03da1c0514"
    assert L._hash_params(L._norm_params({**PARAMS, "pullback_ema": 50.0, "rr_min": 1.25})) == \
        "dc7f7c8cc75741d8b0673da580efecfcea977006d88b4bed12949ff011d7a3bf"
    with pytest.raises(LedgerStateError):
        led.init_params(PARAMS, reason="x")
    with pytest.raises(LedgerValidationError):
        L._norm_params({**PARAMS, "vol_ratio_max": 1.2})
    with pytest.raises(LedgerValidationError):
        L._norm_params({**PARAMS, "max_leverage": 3})


def test_decision_idempotent_conflict_and_append_only(led, tmp_path):
    a = led.record_decision(r1())
    assert a == 1 and led.record_decision(r1()) == 1
    with pytest.raises(LedgerConflictError):
        led.record_decision(r1(planned_stop=1961.0))
    with pytest.raises(LedgerValidationError):
        led.record_decision(r1(rh=None))
    with pytest.raises(LedgerValidationError):
        led.record_decision(r1(bar=datetime(2026, 12, 1, 10, 7, tzinfo=UTC), pair="X/USDT"))
    with pytest.raises(LedgerValidationError):
        led.record_decision(r1(bar=datetime(2026, 12, 1, 10, 0)))
    with pytest.raises(LedgerValidationError):
        led.record_decision(r1(veto_status="blocked", pair="Y/USDT"))
    b = led.record_decision(r1(final_action="skipped", skip_reason="order_failed", risk_allowed=True,
                               supersedes_id=a))
    assert b == 2
    assert [d.id for d in led.list_decisions()] == [2]
    con = sqlite3.connect(tmp_path / "l.sqlite")
    with pytest.raises(sqlite3.IntegrityError):
        con.execute("UPDATE decision_events SET pair='X'")
    con.close()


def _trade(led, clock, tid=7, bar=datetime(2026, 12, 1, 10, 0, tzinfo=UTC), **kw):
    did = led.record_decision(r1(bar=bar, **kw))
    led.record_trade_entry(TradeEntry(tid, did, datetime(2026, 12, 1, 10, 0, 3, tzinfo=UTC), 2001.0, 0.3, 3,
                                      0.30015))
    return did


def test_trade_math(led, clock):
    _trade(led, clock)
    x = TradeExit(7, datetime(2026, 12, 2, 9, tzinfo=UTC), 2079.0, "target", 2100.0, 0.31185, 0.1)
    clock.t = datetime(2026, 12, 2, 10, tzinfo=UTC)
    xid = led.record_trade_exit(x)
    assert led.record_trade_exit(x) == xid
    t = led.get_trade(7)
    assert t.slippage_entry == pytest.approx(0.0005)
    assert t.gross_pnl == pytest.approx(23.4)
    assert t.realized_pnl == pytest.approx(22.688)
    assert t.r_multiple == pytest.approx(1.720352, abs=1e-5)
    assert t.slippage_exit == pytest.approx(0.01)
    with pytest.raises(LedgerConflictError):
        led.record_trade_exit(TradeExit(7, datetime(2026, 12, 2, 9, tzinfo=UTC), 2080.0, "target", 2100.0, 0.3, 0.1))
    row = led.aggregate_trades(["setup"])[0]
    assert row.key == {"setup": "R1"} and row.n == 1 and row.wins == 1
    assert led.trades_since_version(1, exact=True)[0].trade_id == 7
    assert led.count_closed_trades(version_id=1, setup="T1") == 0
    with pytest.raises(LedgerValidationError):
        led.aggregate_trades([])


def test_propose_apply_rollback(led, clock):
    cases = [({"trail_atr": 4.0}, "out_of_bounds"), ({"stop_buffer_atr": 0.5}, "step_too_large"),
             ({"range_width_atr": 3.5}, "immutable_param"), ({"rr_min": True}, "bad_value"),
             ({"rr_min": 1.5}, "no_change"), ({"max_leverage": 4}, "unknown_param"),
             ({"rr_min": 1.25, "trail_atr": 3.5}, "multiple_changes"), ({"vol_ratio_max": 1.75}, "out_of_bounds")]
    for ch, code in cases:
        r = led.propose_change(base_version_id=1, changes=ch, rationale="r", claimed_evidence={}, source="t")
        assert (r.ok, r.code) == (False, code), ch
    assert led.propose_change(base_version_id=3, changes={"rr_min": 1.25}, rationale="r",
                              claimed_evidence={}, source="t").code == "stale_base"
    assert led.propose_change(base_version_id=1, changes={"vol_ratio_max": 1.7}, rationale="r",
                              claimed_evidence={}, source="t").status == "needs_user"
    p = led.propose_change(base_version_id=1, changes={"rr_min": 1.25}, rationale="r",
                           claimed_evidence={"n_closed": 99}, source="t")
    assert p.status == "proposed"
    r = led.apply_proposal(p.proposal_id, actor="lesson", reason="x")
    assert (r.ok, r.code) == (False, "insufficient_evidence")
    assert led.get_proposal(p.proposal_id).status == "proposed"
    for i in range(20):
        _trade(led, clock, tid=100 + i, bar=datetime(2026, 12, 1, 0, 0, tzinfo=UTC) + timedelta(hours=i))
        clock.t += timedelta(hours=1)
        led.record_trade_exit(TradeExit(100 + i, clock.t, 2010.0, "stop", 2000.0, 0.3, 0.0))
    r = led.apply_proposal(p.proposal_id, actor="lesson", reason="x")
    assert r.ok and r.version_id == 2
    v = led.get_version(2)
    assert v.params["rr_min"] == 1.25 and v.evidence["n_closed"] == 20 and v.evidence["claimed_mismatch"]
    assert led.get_proposal(p.proposal_id).status == "applied"
    # haftalik sinir
    p2 = led.propose_change(base_version_id=2, changes={"rr_min": 1.5}, rationale="r", claimed_evidence={},
                            source="t")
    assert p2.status == "proposed"
    rb = led.rollback(actor="user", reason="geri")
    assert rb.ok and rb.version_id == 1
    assert led.rollback(1, actor="user", reason="x").code == "already_active"
    assert led.rollback(99, actor="user", reason="x").code == "unknown_version"
    assert led.rollback(actor="user", reason="ileri").version_id == 2
    assert len(led.list_versions()) == 2


def test_twin_and_readonly_and_schema(tmp_path, clock):
    p = tmp_path / "t.sqlite"
    tw = open_ledger(p, "twin", clock=clock)
    tw.init_params(PARAMS, reason="x")
    with pytest.raises(LedgerStateError):
        tw.propose_change(base_version_id=1, changes={"rr_min": 1.25}, rationale="r", claimed_evidence={},
                          source="s")
    with pytest.raises(LedgerStateError):
        tw.rollback(actor="user", reason="x")
    tw.close()
    with pytest.raises(LedgerSchemaError):
        open_ledger(p, "learner")
    ro = open_ledger(p, "twin", read_only=True)
    with pytest.raises(LedgerStateError):
        ro.record_decision(r1())
    assert ro.get_active_params().version_id == 1
    ro.close()
    with pytest.raises(LedgerValidationError):
        open_ledger(p, "twin", min_evidence_trades=10)
    con = sqlite3.connect(p)
    con.execute("DROP TRIGGER trg_trade_exits_no_delete")
    con.commit()
    con.close()
    with pytest.raises(LedgerSchemaError):
        open_ledger(p, "twin")


def test_health_and_spool(led, clock, monkeypatch):
    assert led.entries_allowed().ok
    st = os.statvfs(".")

    class Low:
        f_bavail, f_frsize = 1, 4096
    monkeypatch.setattr(os, "statvfs", lambda p: Low())
    assert led.check_writable().code == "disk_low"
    assert led.entries_allowed().code == "degraded"
    monkeypatch.undo()
    assert led.check_writable().ok and led.entries_allowed().ok
    did = led.record_decision(r1())
    led._spool_append({"type": "entry", "trade_id": 7, "decision_id": did, "entry_ts": "2026-12-01T10:00:03.000Z",
                       "entry_price": 2001.0, "qty": 0.3, "leverage": 3, "fee_entry": 0.3, "supersedes_id": None})
    assert led.entries_allowed().ok is True  # entries_allowed spool'u bosaltir
    assert led.get_trade(7) is not None
    assert led.find_unledgered_trades([7, 8, 9]) == [8, 9]
    assert led.entries_allowed().code == "unledgered_trades"
    clock.t += timedelta(hours=2)
    assert led.find_orphan_decisions() == []
    assert st is not None
