"""WP-3 motor entegrasyon testleri (kagit kipi, sahte saat): emir ani alanlari, exit_regime, MtM, golge yalitimi."""
from __future__ import annotations

from datetime import timedelta

import pytest

from test_engine_05_spec import BTC, ETH, H, T0, Env, flip_ctx


def _run_exit(env):
    env.open_pos(BTC, T0, entry=100.0, stop=98.0)
    D2 = T0 + 2 * H
    env.signal(D2, signal=False, setup=None, side="short")          # hizali kosul: trend_down
    env.src.ctx[(BTC, D2)] = flip_ctx(D2)
    env.decide(D2)
    env.step(D2)
    env.engine._post_commit()
    return D2


def test_wp3_sim_entry_and_decision_exit_fields(tmp_path):
    e = Env(tmp_path, shadow_blocks=[])
    e.start()
    try:
        D2 = _run_exit(e)
        tr = e.real_ledger.get_trade(1)
        assert tr.entry_ref_price == 100.0 and tr.entry_ref_src == "sim_open" and tr.entry_ref_spread is None
        assert tr.entry_order_ack_ts is None and tr.entry_order_ts is not None
        assert 0.0002 - 1e-9 <= tr.slip_exec_entry <= 0.0002 + 0.01 / 100
        assert tr.exit_reason == "regime_flip" and tr.exit_decision_price == 108.0
        assert tr.exit_ref_src == "sim_open" and tr.slippage_exit is None and tr.exit_regime == "trend_down"
        assert tr.slip_decision_exit is not None
        assert not e.engine.orders.exec_meta                     # kullanilinca silinir
    finally:
        e.close()


def test_wp3_stop_fill_has_no_order_fields_and_no_leak(tmp_path):
    e = Env(tmp_path, shadow_blocks=[])
    e.start()
    try:
        e.open_pos(BTC, T0, entry=100.0, stop=98.0)
        e.step(T0 + timedelta(minutes=1), price=100.0, lo=90.0)
        e.engine._post_commit()
        tr = e.real_ledger.get_trade(1)
        assert tr.exit_reason == "stop" and tr.planned_exit is not None
        assert tr.exit_order_ts is None and tr.exit_ref_price is None and tr.exit_decision_price is None
        assert tr.exit_regime is not None                      # son karar adimi yas siniri icinde
    finally:
        e.close()


def test_wp3_exit_regime_null_when_stale(tmp_path):
    e = Env(tmp_path, shadow_blocks=[])
    e.start()
    try:
        e.open_pos(BTC, T0, entry=100.0, stop=98.0)
        e.step(T0 + timedelta(hours=1, minutes=30), price=100.0, lo=90.0)     # tf + 120 sn'den eski
        e.engine._post_commit()
        assert e.real_ledger.get_trade(1).exit_regime is None
    finally:
        e.close()


def test_wp3_mtm_marks_per_decision_and_toggle(tmp_path):
    e = Env(tmp_path, shadow_blocks=[])
    e.start()
    try:
        for k in range(3):
            e.decide(T0 + k * H)
        rows = e.real_ledger.list_equity_marks()
        assert [r.ts for r in rows] == [T0 + k * H for k in range(3)] and {r.src for r in rows} == {"sim"}
        assert all(r.equity_low <= r.equity and r.equity == r.wallet and r.n_open == 0 for r in rows)
        assert e.engine.records_block()["mtm"]["rows"] == 3
    finally:
        e.close()
    e2 = Env(tmp_path / "b", shadow_blocks=[], mtm_marks=False) if (tmp_path / "b").mkdir() is None else None
    e2.start()
    try:
        e2.decide(T0)
        assert e2.real_ledger.list_equity_marks() == []
    finally:
        e2.close()


def test_wp3_shadow_off_never_touches_ledger_or_15m(tmp_path):
    e = Env(tmp_path, shadow_blocks=[])
    e.start()
    calls = []
    e.real_ledger.record_shadow = lambda *a, **k: calls.append(a)
    orig = e.view.bars
    e.view.bars = lambda pair, tf, *a, **k: (calls.append(tf) if tf == "15m" else None) or orig(pair, tf, *a, **k)
    try:
        e.decide(T0)
        assert calls == []
    finally:
        e.close()


def test_wp3_shadow_failure_is_isolated(tmp_path):
    ref = Env(tmp_path / "ref", shadow_blocks=[]) if (tmp_path / "ref").mkdir() is None else None
    e = Env(tmp_path / "x", shadow_blocks=["r1_disabled"]) if (tmp_path / "x").mkdir() is None else None
    for env in (ref, e):
        env.start()
    try:
        def boom(*a, **k):
            raise RuntimeError("yazilamiyor")
        e.real_ledger.record_shadow = boom
        for env in (ref, e):
            env.signal(T0, setup="R1", side="long", signal=False, regime="range", rh=105.0, rl=95.0,
                       planned_target=105.0, rr=2.0, wick_ratio=0.6, edge_dist_atr=0.2,
                       reasons="v1b:r1_disabled|R1_long:range,stop_ok,rr_ok")
            env.decide(T0)
        assert e.engine.records_block()["shadow"]["errors"] >= 1
        assert e.engine.counters() == ref.engine.counters()
        assert e.engine.ledger.entries_allowed().ok == ref.engine.ledger.entries_allowed().ok
    finally:
        for env in (ref, e):
            env.close()


def test_wp3_shadow_row_written_after_step_and_counters_unchanged(tmp_path):
    e = Env(tmp_path, shadow_blocks=["r1_disabled"])
    e.start()
    try:
        e.signal(T0, setup="R1", side="long", signal=False, regime="range", rh=105.0, rl=95.0, planned_target=105.0,
                 rr=2.0, wick_ratio=0.6, edge_dist_atr=0.2, reasons="v1b:r1_disabled|R1_long:range,stop_ok,rr_ok")
        e.decide(T0)
        rows = e.real_ledger.list_shadow()
        assert len(rows) == 1 and rows[0].block == "r1_disabled" and rows[0].pos_open is False
        assert rows[0].strategy == "fake_strategy@0.1"
        assert not any(k in e.engine.counters() for k in ("shadow", "mtm", "exec", "records"))
        assert e.decisions() == []                             # golge satir aday degildir
    finally:
        e.close()


def test_wp3_shadow_budget_skips_remaining_pairs(tmp_path):
    e = Env(tmp_path, shadow_blocks=["r1_disabled"])
    e.start()
    try:
        orig = e._shadow_pair if hasattr(e, "_shadow_pair") else None
        eng = e.engine

        def slow(pair, D, fr, sp, blocks, code):
            e.clock.set_time(e.clock.now() + timedelta(seconds=2))
        eng._shadow_pair = slow
        e.decide(T0)
        rec = eng.records_block()["shadow"]
        assert rec["budget_skips"] == len(eng.cfg.pairs) - 3 or len(eng.cfg.pairs) <= 3
        _ = orig
    finally:
        e.close()


def test_wp3_order_quote_helpers(tmp_path):
    e = Env(tmp_path, shadow_blocks=[])
    e.start()
    try:
        eng = e.engine
        eng.broker.book_ticker = lambda pair: (99.99, 100.01)
        q = eng._order_quote(BTC)
        assert q["order_ref_price"] == 100.0 and q["order_ref_src"] == "book" and abs(q["order_ref_spread"] - 0.0002) < 1e-12
        for bad in ((0.0, 1.0), (101.0, 100.0)):
            eng.broker.book_ticker = lambda pair, b=bad: b
            assert eng._order_quote(BTC) is None
        eng.broker.book_ticker = lambda pair: None                # yasak/agirlik: cagri yok, hata sayilmaz
        before = eng.records_block()["exec"]["quote_errors"]
        assert eng._order_quote(BTC) is None and eng.records_block()["exec"]["quote_errors"] == before
        def boom(pair):
            raise TimeoutError()
        eng.broker.book_ticker = boom
        assert eng._order_quote(BTC) is None and eng.records_block()["exec"]["quote_errors"] == before + 1
        assert e.engine.orders.quote_fn is None                    # paper: sorgu kod yolu kurulmaz
    finally:
        e.close()


def test_wp3_order_manager_meta_cap_and_quote_failure_does_not_block(tmp_path):
    e = Env(tmp_path, shadow_blocks=[])
    e.start()
    try:
        om = e.engine.orders
        for i in range(300):
            om._put_meta(f"c{i}", {"order_ts": T0})
        assert len(om.exec_meta) == 256 and "c0" not in om.exec_meta and "c299" in om.exec_meta
        om.quote_fn = lambda pair: (_ for _ in ()).throw(RuntimeError("x"))
        e.signal(T0, entry=100.0, stop=98.0)
        e.decide(T0)                                              # _enter quote=True; hata yutulur
        assert e.pos(BTC) is not None
    finally:
        e.close()
