"""BT-1 (mentor, 18 Kasim 2026): kagit/geri test yolunda `would_trigger` ilk stop reddi pozisyonu piyasada kapatir,
`stop_failed` giris kilidi YAZMAZ, ikinci deneme yapilmaz. Gercek stop arizasi (baska ret nedeni) kilidi aynen yazar.
Sentetik veri; var/history okunmaz."""
from __future__ import annotations

import pandas as pd
import pytest

pytest.importorskip("pyarrow")

from tests.engine.test_engine_04_impl_smoke import T0, FakeBroker, env, mkpos  # noqa: E402,F401
from tests.engine.test_engine_06_impl_smoke import BASE, _bt, _Fake, _tpl, _wf, ws  # noqa: E402,F401
from trader_engine.strategies import registry as REG  # noqa: E402


def _market_orders(b):
    return [c for c in b.calls if c[0] == "market_order"]


def test_paper_would_trigger_closes_without_latch(env):
    st, clock, make = env
    b, om = make({("place_stop", 1): "rejected"})          # FakeBroker "rejected" = would_trigger
    pos = mkpos()
    with st.tx():
        st.insert_position(pos)
    o = om.place_initial_stop(pos)
    assert not o.ok and o.note == "would_trigger_closed"
    assert len(_market_orders(b)) == 1
    assert len([c for c in b.calls if c[0] == "place_stop"]) == 1      # ikinci deneme yok
    assert st.get_position(1).status == "closing"
    assert st.kv_get("entries_blocked_reason") is None


def test_paper_would_trigger_on_second_attempt_also_no_latch(env):
    st, clock, make = env
    b, om = make({("place_stop", 1): "rejected_other", ("place_stop", 2): "rejected"})
    pos = mkpos()
    with st.tx():
        st.insert_position(pos)
    o = om.place_initial_stop(pos)
    assert not o.ok and o.note == "would_trigger_closed" and len(_market_orders(b)) == 1
    assert st.kv_get("entries_blocked_reason") is None


def test_paper_genuine_double_reject_still_latches(env):
    st, clock, make = env
    b, om = make({("place_stop", 1): "rejected_other", ("place_stop", 2): "rejected_other"})
    pos = mkpos()
    seen = []
    om.on_stop_failed = lambda tid=None: seen.append(tid)
    with st.tx():
        st.insert_position(pos)
    o = om.place_initial_stop(pos)
    assert not o.ok and o.note == "stop_failed_closed" and len(_market_orders(b)) == 1
    assert len([c for c in b.calls if c[0] == "place_stop"]) == 2
    assert st.kv_get("entries_blocked_reason") == "stop_failed"
    assert seen == [1]


class _Wrong(_Fake):
    """Her sinyalde stop giris kapanisinin hemen altinda: sonraki barin kapanisi stopun altindaysa would_trigger."""

    def compute(self, ctx):
        df = super().compute(ctx)
        df["planned_stop"] = (df["planned_entry"] * 0.9999).where(df["signal"])
        return df


def test_backtest_entries_continue_after_would_trigger_close(ws, monkeypatch):
    monkeypatch.setitem(REG._FACTORIES, "wrong_stop", lambda: _Wrong("wrong_stop", False))
    args = ["--period", "20250301-20250306", "--tf", "1h", "--fill-model", "native", "--granularity", "15m",
            "--synthetic-rules", "--no-record-filtered", "--strategy", "wrong_stop"]
    assert _bt("--id", "w1", *args) == 0
    t = pd.read_csv(ws / "var/backtests/w1/trades.csv")
    other = t[t["exit_reason"] == "other"]
    assert len(other) >= 1, t["exit_reason"].value_counts().to_dict()
    assert len(t) > len(other)
    import sqlite3
    con = sqlite3.connect(f"file:{ws / 'var/backtests/w1/ledger.sqlite'}?mode=ro", uri=True)
    try:
        assert con.execute("SELECT COUNT(*) FROM v_decisions WHERE skip_reason='entry_gate_closed'").fetchone()[0] == 0
    finally:
        con.close()
