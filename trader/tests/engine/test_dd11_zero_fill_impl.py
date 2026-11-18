"""DD-11 sifir dolum: gerceklestirme duman testleri (bagimsiz Z-T testleri baska dosyada)."""
from __future__ import annotations

import argparse
import json
import logging
from datetime import datetime, timezone
from decimal import Decimal as D
from types import SimpleNamespace

import test_engine_live_spec as T
from trader_core import ledger as L
from trader_engine import cli
from trader_engine.brokers import binance_futures as BF
from trader_engine.state import StateStore


class _Stub:
    """_settle icin asgari broker govdesi."""
    _ctr = {k: 0 for k in BF._COUNTERS}
    _open_pairs: set = set()
    _last_pos: dict = {}
    _pos_since: dict = {}
    _entry_fee: dict = {}
    _order_ids: dict = {}
    _taker_rate = lambda self, p: 0.0004   # noqa: E731
    _now = lambda self: datetime(2026, 1, 1, tzinfo=timezone.utc)   # noqa: E731
    _symbol = lambda self, p: "XRPUSDT"   # noqa: E731

    def __init__(self, trades=None):
        self.events = []
        self._trades = trades or []
        self._ctr = {k: 0 for k in BF._COUNTERS}
        self._open_pairs, self._last_pos, self._pos_since, self._entry_fee, self._order_ids = set(), {}, {}, {}, {}
        self._zero_fill, self._zero_fill_last, self.findings, self._blocks = {}, {}, [], set()
        self._live = SimpleNamespace(poll_open_s=5.0)

    def _block(self, r):
        self._blocks.add(r)

    def _push(self, e):
        self.events.append(e)

    def _rc(self, name, *a, **k):
        assert name == "user_trades"
        return self._trades

    _recover_entry_price = BF.LiveBroker._recover_entry_price
    _zero_fill_wait = BF.LiveBroker._zero_fill_wait


def _settle(stub, body):
    info = BF._Pending("XRP/USDT", "entry", "buy")
    return BF.LiveBroker._settle(stub, info, "cid1", body)


def test_zero_avg_uses_cumquote():
    s = _Stub()
    out, q, avg, _ = _settle(s, {"status": "FILLED", "executedQty": "10", "avgPrice": "0.00", "cumQuote": "25"})
    assert out == "filled" and q == 10.0 and avg == 2.5 and s.events[0].fill.price == 2.5


def test_zero_avg_zero_cum_uses_user_trades_else_pending():
    body = {"status": "FILLED", "executedQty": "10", "avgPrice": "0", "cumQuote": "0", "orderId": 7}
    s = _Stub()
    assert _settle(s, body)[0] == "pending" and not s.events
    s = _Stub([{"orderId": 7, "qty": "4", "price": "2"}, {"orderId": 7, "qty": "6", "price": "3"}, {"orderId": 8, "qty": "1", "price": "9"}])
    out, _, avg, _ = _settle(s, body)
    assert out == "filled" and abs(avg - 2.6) < 1e-12


def test_zero_executed_qty_pending():
    s = _Stub()
    assert _settle(s, {"status": "FILLED", "executedQty": "0", "avgPrice": "2", "cumQuote": "0"})[0] == "pending"
    assert not s.events


def test_engine_bad_fill_leaves_opening(tmp_path, caplog):
    e = T.LiveEnv(tmp_path).boot()
    try:
        pos = SimpleNamespace(status="opening")
        e.state.position_for_pair = lambda pair: pos            # type: ignore[method-assign]
        fill = SimpleNamespace(price=0.0, qty=5.0, client_id="c")
        with caplog.at_level(logging.CRITICAL):
            e.engine._on_entry_fill(SimpleNamespace(fill=fill, pair="XRP/USDT"), None, e.clock.now())
        assert e.engine._c["bad_fill"] == 1 and e.state.outbox_pending() == []
        assert not e.state.block_has("outbox_stuck")
    finally:
        e.close()


def test_quarantine_cli_dry_run_apply_and_lock(tmp_path, monkeypatch, capsys):
    cfg = T.make_live_cfg(tmp_path)
    monkeypatch.setattr(cli, "_load_cfg", lambda a: cfg)
    from pathlib import Path
    for p in (cfg.state_path, cfg.ledger_path):
        Path(p).parent.mkdir(parents=True, exist_ok=True)
    led = L.open_ledger(cfg.ledger_path, "learner", create=True)
    led.close()
    st = StateStore(cfg.state_path, bot="learner")
    with st.tx():
        st.outbox_add("entry", 1, {"entry_ts": "2026-01-01T00:00:00Z", "trade_id": 1, "decision_id": 1, "entry_price": 0.0,
                                   "qty": 1.0, "leverage": 1, "fee_entry": 0.0})
        st.outbox_add("exit", 1, {"exit_ts": "2026-01-01T01:00:00Z", "trade_id": 1, "exit_price": 1.0, "exit_reason": "stop",
                                  "planned_exit": None, "fee_exit": 0.0, "funding_paid": 0.0})
    ns = lambda **k: argparse.Namespace(**{"bot": "learner", "config_dir": "config", "env": None, "apply": False, **k})  # noqa: E731
    assert cli._cmd_outbox_quarantine(ns()) != 0                 # kilit tutuluyor (st acik)
    st.close()
    assert cli._cmd_outbox_quarantine(ns()) == 0
    st = StateStore(cfg.state_path, bot="learner")
    assert len(st.outbox_pending()) == 2
    st.close()
    capsys.readouterr()
    assert cli._cmd_outbox_quarantine(ns(apply=True)) == 0
    st = StateStore(cfg.state_path, bot="learner")
    try:
        assert st.outbox_pending() == []
        n = st._exec("SELECT COUNT(*) FROM ledger_outbox_quarantine").fetchone()[0]
        assert n == 2
    finally:
        st.close()


# ------------------------------------------------------------------ mentor D1-D5
class _Clk(_Stub):
    def __init__(self, *a, **k):
        super().__init__(*a, **k)
        self.t = datetime(2026, 1, 1, tzinfo=timezone.utc)
        self.findings, self._blocks = [], set()
        self._zero_fill, self._zero_fill_last = {}, {}
        self._live = SimpleNamespace(poll_open_s=5.0)
        self.calls = 0

    def _now(self):
        return self.t

    def _block(self, r):
        self._blocks.add(r)

    def _rc(self, name, *a, **k):
        self.calls += 1
        return self._trades

    _zero_fill_wait = BF.LiveBroker._zero_fill_wait


def test_d1_zero_fill_gives_up_without_order_rejected_and_throttles():
    from datetime import timedelta
    s = _Clk()
    body = {"status": "FILLED", "executedQty": "10", "avgPrice": "0", "cumQuote": "0", "orderId": 7}
    outs = []
    for _ in range(4):
        outs.append(_settle(s, body)[0])
        s.t += timedelta(seconds=11)
    assert outs[:3] == ["pending"] * 3 and outs[3] == "zero_fill_unresolved"
    assert s.findings == ["zero_fill_unresolved:cid1"] and "zero_fill_unresolved" in s._blocks
    assert not any(e.kind == "order_rejected" for e in s.events)


def test_d1_user_trades_throttled_per_poll_open():
    s = _Clk()
    body = {"status": "FILLED", "executedQty": "10", "avgPrice": "0", "cumQuote": "0", "orderId": 7}
    _settle(s, body)
    _settle(s, body)
    assert s.calls == 1


def test_d2_register_position_drops_pending_entries():
    s = _Clk()
    s._pending_market = {"a": BF._Pending("XRP/USDT", "entry", "buy"), "b": BF._Pending("DOGE/USDT", "entry", "buy")}
    s._pending_nf, s._registered, s._hints, s._exit_cids = {}, set(), {}, {}
    BF.LiveBroker.register_position(s, "XRP/USDT", s.t, ())
    assert list(s._pending_market) == ["b"]


def test_d4_dry_run_apply_mutually_exclusive():
    import pytest
    with pytest.raises(SystemExit):
        cli.main(["outbox-quarantine", "--dry-run", "--apply"])


def test_d4_malformed_payload_moves_nothing(tmp_path, monkeypatch):
    from pathlib import Path
    cfg = T.make_live_cfg(tmp_path)
    monkeypatch.setattr(cli, "_load_cfg", lambda a: cfg)
    for p in (cfg.state_path, cfg.ledger_path):
        Path(p).parent.mkdir(parents=True, exist_ok=True)
    L.open_ledger(cfg.ledger_path, "learner", create=True).close()
    st = StateStore(cfg.state_path, bot="learner")
    with st.tx():
        st.outbox_add("exit", 1, {"exit_ts": "2026-01-01T01:00:00Z"})      # eksik alanlar -> KeyError/TypeError
    st.close()
    ns = argparse.Namespace(bot="learner", config_dir="config", env=None, apply=True)
    assert cli._cmd_outbox_quarantine(ns) == cli.EXIT_ENGINE
    st = StateStore(cfg.state_path, bot="learner")
    try:
        assert len(st.outbox_pending()) == 1
    finally:
        st.close()
