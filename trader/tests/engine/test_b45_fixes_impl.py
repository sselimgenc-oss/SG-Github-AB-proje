"""WP-B4/B5 duzeltme turu (mentor incelemesi) gerceklestirme testleri: 11 §6.3, §8 (L1, L2a, L2b, L3c), §10 F8-F11/F16.
Bagimsiz regresyon testleri ayri dosyadadir; buradakiler gerceklemeyi senaryo duzeyinde sabitler."""
from __future__ import annotations

from datetime import timedelta
from pathlib import Path

import pytest

from fake_exchange import FakeResp
from test_engine_live_spec import (DEC, SYM, XRP, Crash, LiveEnv, cid_of, entry_post, exit_post, raising, restart)
from trader_engine.errors import EngineExit
from trader_engine.state import OrderRow


REAL_STARTUP_GATE = True          # tests/conftest.py: bu modulde gercek acilis kapisi calisir


def is_query(r):
    return r.method == "GET" and r.path == "/fapi/v1/order"


# ------------------------------------------------------------------ fix 1: kilitli `closing`
def test_b45i_uncertain_exit_not_found_reverts_to_open_and_counts(tmp_path):
    e = LiveEnv(tmp_path, reconcile_open_s=15.0).boot()
    try:
        pos = e.enter()
        tid = pos.trade_id
        e.wire.on(exit_post, before=raising(TimeoutError("x")))
        e.engine._submit_exit(e.state.get_position(tid), "regime_flip", DEC)      # iki sorgu: emir yok
        cur = e.state.get_position(tid)
        assert cur.status == "open" and cur.exit_client_id is None
        assert int(e.kv(f"exit_retry:{tid}")) == 1
        assert e.ex_qty() > 0
    finally:
        e.close()


def test_b45i_exit_retry_limit_counts_every_failed_attempt(tmp_path):
    e = LiveEnv(tmp_path, reconcile_open_s=15.0).boot()
    try:
        pos = e.enter()
        tid = pos.trade_id
        e.wire.on(exit_post, before=raising(TimeoutError("x")), once=False)
        for i in range(3):
            e.engine._submit_exit(e.state.get_position(tid), "regime_flip", DEC + timedelta(minutes=i + 1))
        assert int(e.kv(f"exit_retry:{tid}")) == 3
        assert e.kv("entries_blocked_reason") == "exit_unknown"
    finally:
        e.close()


def test_b45i_closing_with_gone_accepted_exit_reverts_each_round(tmp_path):
    """L3c: `accepted` ama borsada olmayan piyasa cikisi -> `open`a doner; sorgu HATASI eylemsiz."""
    e = LiveEnv(tmp_path, reconcile_open_s=15.0).boot()
    try:
        pos = e.enter()
        tid = pos.trade_id
        cid = cid_of("exit", D=DEC + timedelta(minutes=5))
        now = e.clock.now()
        with e.state.tx():
            e.state.insert_order(OrderRow(client_id=cid, pair=XRP, role="exit", order_side="sell", qty=pos.qty,
                                          trigger_price=None, reduce_only=True, status="accepted",
                                          signal_bar_close_ts=DEC, seq=0, attempts=0, trade_id=tid,
                                          broker_order_id=None, detail=None, created_ts=now, updated_ts=now))
            e.state.update_position(tid, status="closing", exit_client_id=cid, exit_reason="manual")
        e.wire.on(is_query, before=raising(TimeoutError("q")))
        e.engine.orders.resolve_unresolved()
        assert e.state.get_position(tid).status == "closing", "sorgu hatasinda eylem yok"
        e.engine.orders.resolve_unresolved()
        cur = e.state.get_position(tid)
        assert cur.status == "open" and e.order_status(cid) == "failed" and int(e.kv(f"exit_retry:{tid}")) == 1
    finally:
        e.close()


# ------------------------------------------------------------------ fix 2: acilis kapisi + dakikalik girdi kontrolu
def test_b45i_live_startup_gate_runs_after_protect_first(tmp_path):
    e = LiveEnv(tmp_path, dead=True)
    e.broker.startup_check()
    try:
        with pytest.raises(EngineExit) as ei:
            e.engine.start()
        assert ei.value.code == 7
    finally:
        e.close()


def test_b45i_live_tick_refreshes_input_counters(tmp_path):
    e = LiveEnv(tmp_path).boot()
    try:
        e.view.dead = True
        e.tick(61)
        assert e.engine.counters()["data_stale"] == 1
    finally:
        e.close()


# ------------------------------------------------------------------ fix 3: opening benimseme kaniti
def test_b45i_opening_without_order_row_does_not_adopt_foreign_position(tmp_path):
    import sqlite3
    e = LiveEnv(tmp_path).boot()
    e.wire.on(entry_post, before=raising(Crash()))
    e.signal(DEC)
    with pytest.raises(Crash):
        e.decide()
    e.hard_close()
    con = sqlite3.connect(e.cfg.state_path)
    con.execute("DELETE FROM orders")
    con.commit()
    con.close()
    e.ex.fill_market(SYM, "BUY", "7")                       # yabanci elle pozisyon, ayni yon
    e2 = LiveEnv(e.tmp, ex=e.ex, clock=e.clock).boot()
    try:
        p = e2.state.get_position(1)
        assert p.status == "opening" and p.qty is None
        assert len(e2.stops()) == 0
        assert [h.reason for h in e2.engine.pause.holds()] == ["unknown_position"]
    finally:
        e2.close()


def test_b45i_opening_opposite_side_position_is_unknown_not_adopted(tmp_path):
    e = LiveEnv(tmp_path).boot()
    try:
        e.wire.on(entry_post, before=raising(TimeoutError("x")))
        e.signal(DEC)
        e.decide()
        e.ex.fill_market(SYM, "SELL", "7")
        e.tick(16)
        e.tick(16)
        p = e.state.get_position(1)
        assert p.status == "opening" and p.qty is None
        assert [h.reason for h in e.engine.pause.holds()] == ["unknown_position"]
        assert not e.posted("x") and not e.stops()
    finally:
        e.close()


# ------------------------------------------------------------------ fix 5: once coz sonra oku
def test_b45i_resolve_before_read(tmp_path):
    e = LiveEnv(tmp_path).boot()
    try:
        e.wire.on(entry_post, before=raising(TimeoutError("x")))
        e.signal(DEC)
        e.decide()
        n0 = len(e.wire.log)
        e.tick(16)
        paths = [r.path for r in e.wire.log[n0:] if r.method == "GET"]
        q = paths.index("/fapi/v1/order")
        reads = [i for i, pth in enumerate(paths) if pth == "/fapi/v2/positionRisk" or pth.endswith("positionRisk")]
        assert reads and q < reads[0] or not reads
    finally:
        e.close()


# ------------------------------------------------------------------ fix 6 / 7: ban ve rate-limit
def test_b45i_rate_limited_clears_after_window_and_reconcile(tmp_path):
    e = LiveEnv(tmp_path).boot()
    try:
        e.enter()
        Path(e.cfg.kill_file).write_text("{}")
        e.wire.on(exit_post, before=lambda rec: FakeResp(429, {"code": -1003, "msg": "Too many"}, {"Retry-After": "30"}))
        e.tick(6)
        assert e.kv("entries_blocked_reason") == "exchange_rate_limited"
        assert e.engine._ban_until is not None
        Path(e.cfg.kill_file).unlink()
        for _ in range(8):
            e.tick(16)
        assert e.kv("entries_blocked_reason") is None
    finally:
        e.close()


def test_b45i_read_path_ban_adds_exchange_ban_hold(tmp_path):
    e = LiveEnv(tmp_path).boot()
    try:
        e.enter()
        e.wire.on(lambda r: r.method == "GET" and "positionRisk" in r.path,
                  before=lambda rec: FakeResp(418, {"code": -1003, "msg": "banned"}, {"Retry-After": "120"}))
        for _ in range(4):
            e.tick(6)
        assert "exchange_ban" in [h.reason for h in e.engine.pause.holds()]
    finally:
        e.close()


# ------------------------------------------------------------------ fix 8: giris penceresi kapanisi motor yolundan
def test_b45i_entry_window_expiry_supersedes_decision_and_drops_event(tmp_path):
    e = LiveEnv(tmp_path).boot()
    try:
        e.wire.on(entry_post, before=raising(TimeoutError("gitmedi")))
        e.signal(DEC)
        e.decide()
        t0 = e.state.get_order(cid_of("entry")).created_ts
        e.tick_at(t0 + timedelta(seconds=80))
        e.tick(16)
        assert e.state.get_position(1).status == "closed"
        assert not e.engine._entry_events
        ds = e.real_ledger.list_decisions()
        assert [(d.final_action, d.skip_reason) for d in ds][-1] == ("skipped", "order_failed")
    finally:
        e.close()


# ------------------------------------------------------------------ fix 9: L2a sorgu hatasi
def test_b45i_late_fill_query_failure_is_finding_without_hold(tmp_path):
    e = LiveEnv(tmp_path, reconcile_open_s=15.0).boot()
    try:
        pos = e.enter()
        tid = pos.trade_id
        with e.state.tx():                                   # state: giris `failed` + pozisyon kapali; borsada pozisyon var
            e.state.update_order(pos_entry_cid(e, tid), status="failed")
            e.state.update_position(tid, status="closed", exit_reason="other", closed_ts=e.clock.now())
        e.wire.on(is_query, before=raising(TimeoutError("q")), once=False)
        rep = e.engine.reconciler.run(e.clock.now())
        assert f"late_fill_unverified:{XRP}" in rep.findings
        assert not any(f.startswith("unknown_position") for f in rep.findings)
        assert not e.engine.pause.holds()
    finally:
        e.close()


def pos_entry_cid(e, tid):
    return next(r.client_id for r in e.state.orders_for_trade(tid) if r.role == "entry")


# ------------------------------------------------------------------ fix 11: dusuk maddeler
def test_b45i_kill_close_one_attempt_per_activation_and_mtime_fallback_without_at(tmp_path):
    """Fix 3: operatorun bos/`{}` KILL dosyasi (`at` yok) -> kimlik dosya mtime'indan; etkinlestirme basina TEK deneme."""
    e = LiveEnv(tmp_path).boot()
    try:
        e.ex.fill_market(SYM, "BUY", "7")                     # state'te olmayan pozisyon
        kf = Path(e.cfg.kill_file)
        kf.parent.mkdir(parents=True, exist_ok=True)
        kf.write_text("")                                     # `touch KILL`
        rep = e.engine.reconciler.run(e.clock.now())
        assert f"kill_close_refused:{XRP}" not in rep.actions
        assert len(e.posted("x")) == 1
        e.ex.fill_market(SYM, "BUY", "7")                     # pozisyon yeniden belirdi: ayni etkinlestirme, yeni deneme YOK
        rep = e.engine.reconciler.run(e.clock.now())
        assert f"kill_close_pending:{XRP}" in rep.actions and len(e.posted("x")) == 1
    finally:
        e.close()


def test_b45i_kill_close_refused_only_when_kill_file_unreadable(tmp_path):
    e = LiveEnv(tmp_path).boot()
    try:
        e.ex.fill_market(SYM, "BUY", "7")
        Path(e.cfg.kill_file).write_text("{}")
        e.engine.reconciler._kill_mtime_at = lambda: None     # noqa: SLF001  (stat hatasi)
        rep = e.engine.reconciler.run(e.clock.now())
        assert f"kill_close_refused:{XRP}" in rep.actions and not e.posted("x")
        del e.engine.reconciler._kill_mtime_at
        Path(e.cfg.kill_file).write_text('{"at": "2026-12-28T10:00:00Z"}')   # `at` varsa o kullanilir
        e.engine.reconciler.run(e.clock.now())
        assert len(e.posted("x")) == 1
    finally:
        e.close()


def test_b45i_error_ladder_counts_per_label(tmp_path):
    e = LiveEnv(tmp_path).boot()
    try:
        def bad():
            raise ValueError("x")
        for _ in range(3):
            e.engine._guard("watchdog", bad)
            assert e.engine._guard("kill", lambda: None)          # baska adimin basarisi sayaci sifirlamaz
        assert e.kv("entries_blocked_reason") == "engine_errors"
    finally:
        e.close()


def test_b45i_adopted_entry_sets_fee_estimated_flag(tmp_path):
    e = LiveEnv(tmp_path).boot()
    e.wire.on(entry_post, after=raising(Crash()))
    e.signal(DEC)
    with pytest.raises(Crash):
        e.decide()
    e2 = restart(e)
    try:
        assert e2.state.get_position(1).status == "open"
        assert e2.kv("entry_fee_estimated:1") is True
    finally:
        e2.close()


# ------------------------------------------------------------------ fix 4: filled giris satiri + opening + borsa duz
def test_b45i_opening_with_filled_entry_row_and_flat_exchange_is_closed_after_window(tmp_path):
    """Benimseme satiri `filled` yazdi, `on_entry_adopted` calismadan cokus, sonra dis kapanis: pozisyon `opening`da
    takilmamali; pencereden sonra dolum sorgudan uygulanir ve L3 kapatir."""
    e = LiveEnv(tmp_path, reconcile_open_s=15.0).boot()
    e.wire.on(entry_post, after=raising(Crash()))
    e.signal(DEC)
    with pytest.raises(Crash):
        e.decide()
    e.hard_close()
    e2 = LiveEnv(e.tmp, ex=e.ex, clock=e.clock)
    e2.broker.startup_check()
    e2.engine.orders.on_entry_adopted = lambda row, bo: (_ for _ in ()).throw(Crash())     # satir guncellendi, olay yok
    with pytest.raises(Crash):
        e2.engine.start()
    e2.hard_close()
    e.ex.fill_market(SYM, "SELL", str(e.ex.pos[SYM]["amt"]))   # dis kapanis: borsa duz
    assert e.ex_qty() == 0
    e3 = LiveEnv(e.tmp, ex=e.ex, clock=e.clock)
    try:
        assert e3.state.get_position(1).status == "opening"
        assert e3.order_status(pos_entry_cid(e3, 1)) == "filled"
        e3.broker.startup_check()
        e3.engine.start()
        for _ in range(12):
            e3.tick(16)
        assert e3.state.get_position(1).status == "closed", "filled satirli opening pozisyon takildi"
        assert e3.ex_qty() == 0
    finally:
        e3.close()


# ------------------------------------------------------------------ fix 5: cikis limiti dolunca yeniden gonderim kisitlamasi
def test_b45i_exit_repost_throttled_after_retry_limit_under_kill(tmp_path):
    e = LiveEnv(tmp_path, reconcile_open_s=30.0).boot()
    try:
        pos = e.enter()
        with e.state.tx():
            e.state.kv_set(f"exit_retry:{pos.trade_id}", 3)
        e.wire.on(exit_post, before=raising(TimeoutError("x")), once=False)
        Path(e.cfg.kill_file).write_text("{}")
        for _ in range(10):                                   # 60 sn, 6 sn'lik adimlar
            e.tick(6)
        n = len([r for r in e.wire.log if exit_post(r)])
        assert 1 <= n <= 3, f"limit sonrasi KILL cikisi reconcile_open_s basina 1 olmali, {n} POST"
        assert e.engine.counters().get("exit_throttled", 0) >= 5
    finally:
        e.close()


def test_b45i_exit_retry_limit_is_public_constant():
    import trader_engine.order_manager as om
    import trader_engine.reconcile_live as rl
    assert om.EXIT_RETRY_LIMIT == 3 and "EXIT_RETRY_LIMIT" in om.__all__
    assert rl.EXIT_RETRY_LIMIT is om.EXIT_RETRY_LIMIT or rl.EXIT_RETRY_LIMIT == om.EXIT_RETRY_LIMIT
    assert "_EXIT_RETRY_LIMIT" not in open(rl.__file__, encoding="utf-8").read().replace("`EXIT_RETRY_LIMIT`", "")
