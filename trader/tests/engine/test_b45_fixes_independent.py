"""WP-B4/B5 fix round (mentor review b45_review.md, required fixes 1-9) bagimsiz regresyon testleri.

Yalniz kamusal giris noktalarindan (Engine.start/live_tick/_submit_exit, LiveReconciler.run/protect_first) ve sahte borsa
gozleminden yazildi; engine.py / order_manager.py / reconcile_live.py gerceklemesine BAKILMADI. Sentetik veri, ag yok.
Duzenekler: LiveEnv (test_engine_live_spec) ve Rig (test_reconcile_live_spec); modul adlariyla import edilir (test toplama
cogalmasin diye `import *` yok). Test adlari `test_b45ind_` onekiyle benzersizdir.
"""
from __future__ import annotations

import sys
from datetime import timedelta
from pathlib import Path

import pytest

import test_engine_live_spec as T
import test_reconcile_live_spec as R
from fake_exchange import FakeResp
from trader_engine.errors import EngineExit

LiveEnv, DEC, SYM, XRP = T.LiveEnv, T.DEC, T.SYM, T.XRP
entry_post, exit_post, raising, cid_of, Crash = T.entry_post, T.exit_post, T.raising, T.cid_of, T.Crash


# ------------------------------------------------------------------------------------------------ duzenek
@pytest.fixture
def mk(tmp_path):
    made = []

    def f(**kw):
        e = LiveEnv(tmp_path, **kw)
        made.append(e)
        return e

    f.made = made
    yield f
    for e in made:
        e.close()


@pytest.fixture
def rig(tmp_path):
    r = R.Rig(tmp_path)
    R.set_t(r.clock, R.T0 + timedelta(seconds=5))
    yield r
    r.state.close()


def is_query(r):
    return r.method == "GET" and r.path == "/fapi/v1/order"


def holds(e):
    return [h.reason for h in e.engine.pause.holds()]


def real_startup_gate(request=None):
    """tests/conftest.py kapiyi varsayilan olarak etkisiz kilar; bu testte gercek kapi calissin."""
    found = False
    mods = list(sys.modules.values())
    if request is not None:                                   # importlib kipi: conftest sys.modules'ta olmayabilir
        mods += list(request.config.pluginmanager.get_plugins())
    for mod in mods:              # ayni conftest birden cok adla yuklenmis olabilir
        f = getattr(mod, "__file__", None) or ""
        if f.endswith("conftest.py") and isinstance(getattr(mod, "_REAL", None), dict):
            mod._REAL["on"] = True
            found = True
    if not found:
        raise RuntimeError("tests/conftest.py (_REAL) bulunamadi")


def kill_on(e):
    Path(e.cfg.kill_file).parent.mkdir(parents=True, exist_ok=True)
    Path(e.cfg.kill_file).write_text("{}")


def uncertain_exit(e, tid, reason="regime_flip"):
    """Strateji cikisi: POST iletilmez (zaman asimi), emir sorgusu 'yok' doner -> belirsiz cikis."""
    e.wire.on(exit_post, before=raising(TimeoutError("x")))
    e.engine._submit_exit(e.state.get_position(tid), reason, DEC)


# ================================================================================================ FIX 1
def test_b45ind_f1_uncertain_exit_returns_position_to_open_and_counts_retry(mk):
    e = mk(reconcile_open_s=15.0).boot()
    pos = e.enter()
    tid = pos.trade_id
    uncertain_exit(e, tid)
    p = e.state.get_position(tid)
    assert p.status == "open", f"belirsiz cikis sonrasi pozisyon {p.status!r} (closing'de takildi)"
    assert len(e.stops()) == 1 and e.ex_qty() > 0
    assert e.kv(f"exit_retry:{tid}"), "F16: exit_retry sayaci artmali"


def test_b45ind_f1_after_revert_kill_can_close_position(mk):
    e = mk(reconcile_open_s=15.0).boot()
    pos = e.enter()
    uncertain_exit(e, pos.trade_id)
    kill_on(e)
    for _ in range(4):
        e.tick(6)
    p = e.state.get_position(pos.trade_id)
    assert p.status == "closed" and e.ex_qty() == 0, (p.status, e.ex_qty())


def test_b45ind_f1_exit_queries_failing_then_network_heals_kill_closes(mk):
    e = mk(reconcile_open_s=15.0).boot()
    pos = e.enter()
    kill_on(e)
    e.wire.on(exit_post, before=raising(TimeoutError("x")))
    e.wire.on(is_query, before=raising(TimeoutError("q")), once=False)
    e.tick(6)
    e.tick(16)
    e.wire.hooks.clear()
    for _ in range(8):
        e.tick(16)
    p = e.state.get_position(pos.trade_id)
    assert p.status == "closed" and e.ex_qty() == 0, (p.status, e.ex_qty())


def test_b45ind_f1_exit_never_delivered_reaches_exit_unknown_after_limit(mk):
    e = mk(reconcile_open_s=15.0).boot()
    pos = e.enter()
    kill_on(e)
    e.wire.on(exit_post, before=raising(TimeoutError("x")), once=False)
    seen = False
    for _ in range(25):
        e.tick(16)
        if e.kv("entries_blocked_reason") == "exit_unknown":
            seen = True
            break
    assert seen, "exit_unknown (F16) siniri sonrasi kurulmadi"
    assert e.state.get_position(pos.trade_id).status in ("open", "closing")


def test_b45ind_f1_kill_still_closes_after_exit_unknown_when_exchange_heals(mk):
    e = mk(reconcile_open_s=15.0).boot()
    pos = e.enter()
    kill_on(e)
    e.wire.on(exit_post, before=raising(TimeoutError("x")), once=False)
    for _ in range(25):
        e.tick(16)
        if e.kv("entries_blocked_reason") == "exit_unknown":
            break
    e.wire.hooks.clear()
    for _ in range(8):
        e.tick(16)
    p = e.state.get_position(pos.trade_id)
    assert p.status == "closed" and e.ex_qty() == 0, (p.status, e.ex_qty())


def test_b45ind_f1_rejected_exits_count_toward_retry_limit(mk):
    e = mk(reconcile_open_s=15.0).boot()
    e.enter()
    kill_on(e)
    e.wire.on(exit_post, before=lambda rec: FakeResp(400, {"code": -2022, "msg": "ReduceOnly Order is rejected."}),
              once=False)
    seen = False
    for _ in range(25):
        e.tick(16)
        if e.kv("entries_blocked_reason") == "exit_unknown":
            seen = True
            break
    assert seen, "reddedilen cikislar _EXIT_RETRY_LIMIT'e sayilmali (exit_unknown + CRIT)"


def _closing_with_exit_row(rig, status):
    p = rig.seed_position(status="closing")
    xcid = R.cidf("exit")
    now = rig.clock.now()
    with rig.state.tx():
        rig.state.insert_order(rig._row(xcid, R.XRP, "exit", "sell", 10.0, None, True, status, 0, p.trade_id, now))
        rig.state.update_position(p.trade_id, exit_client_id=xcid)
    R.at_run(rig)
    return p, xcid


@pytest.mark.parametrize("status", ["failed", "rejected", "canceled", "expired"])
def test_b45ind_f1_reconcile_reverts_closing_with_dead_exit_row_to_open(rig, status):
    p, _ = _closing_with_exit_row(rig, status)
    rig.run()
    assert rig.state.get_position(p.trade_id).status == "open"


def test_b45ind_f1_reconcile_reverts_closing_when_accepted_exit_is_gone_on_exchange(rig):
    p, xcid = _closing_with_exit_row(rig, "accepted")      # borsada bu kimlikli emir yok
    rig.run()
    assert rig.state.get_position(p.trade_id).status == "open"


def test_b45ind_f1_reconcile_reverts_closing_when_accepted_exit_is_terminal_unfilled(rig):
    p, xcid = _closing_with_exit_row(rig, "accepted")
    rig.ex.orders[xcid] = {"clientOrderId": xcid, "symbol": "XRPUSDT", "side": "SELL", "type": "MARKET", "orderId": 9,
                           "reduceOnly": True, "origQty": "10", "status": "CANCELED", "executedQty": "0",
                           "avgPrice": "0", "time": 0, "updateTime": 0}
    rig.run()
    assert rig.state.get_position(p.trade_id).status == "open"


def test_b45ind_f1_reconcile_query_error_takes_no_action_on_closing(rig):
    p, _ = _closing_with_exit_row(rig, "accepted")
    rig.down("/fapi/v1/order")
    m = rig.mark()
    rig.run()
    assert rig.state.get_position(p.trade_id).status == "closing"
    assert rig.posts(m) == []


# ================================================================================================ FIX 2
def test_b45ind_f2_testnet_start_runs_startup_gate_dead_feed_exits(mk, request):
    real_startup_gate(request)
    e = mk(dead=True)
    e.broker.startup_check()
    with pytest.raises(EngineExit):
        e.engine.start()


def test_b45ind_f2_live_tick_checks_inputs_about_once_a_minute(mk):
    e = mk().boot()
    base = {k: v for k, v in e.engine.counters().items() if "stale" in k or "missing" in k}
    e.view.dead = True                                     # besleme sonradan olur
    for _ in range(8):
        e.tick(20)                                         # ~160 sn
    now = {k: v for k, v in e.engine.counters().items() if "stale" in k or "missing" in k}
    grew = [k for k in now if now[k] > base.get(k, 0)]
    assert grew, f"live_tick girdi denetimi yapmadi: {base} -> {now}"


# ================================================================================================ FIX 3
def _opening_with_entry_row(rig, status="unknown"):
    pos = R._opening_no_order(rig)
    ecid = R.cidf("entry")
    with rig.state.tx():
        rig.state.insert_order(rig._row(ecid, R.XRP, "entry", "buy", 10.0, None, False, status, 0, pos.trade_id,
                                        rig.clock.now()))
    R.at_run(rig, 8)
    return pos, ecid


def test_b45ind_f3_control_entry_with_evidence_is_adopted(rig):
    pos, ecid = _opening_with_entry_row(rig)
    rig.ex.fill_market("XRPUSDT", "BUY", 10, cid=ecid)
    rig.run()
    assert rig.state.get_position(pos.trade_id).status == "open"
    assert len(rig.live_stops(R.XRP)) == 1


def test_b45ind_f3_foreign_position_without_entry_row_not_adopted(rig):
    pos = R._opening_no_order(rig)
    rig.ex.fill_market("XRPUSDT", "BUY", 10)               # elle/yabanci, ayni yon
    R.at_run(rig, 8)
    m = rig.mark()
    rep = rig.run()
    assert rig.state.get_position(pos.trade_id).status == "opening"
    assert rig.live_stops(R.XRP) == {}, "yabanci pozisyon icin stop kurulmamali"
    assert "unknown_position" in rig.holds()
    assert f"unknown_position:{R.XRP}" in rep.findings
    assert rig.posts(m) == []


def test_b45ind_f3_entry_row_but_exchange_says_no_such_order_not_adopted(rig):
    pos, ecid = _opening_with_entry_row(rig)
    rig.ex.fill_market("XRPUSDT", "BUY", 10)               # baska kimlikle; entry cid borsada yok
    rig.run()
    assert rig.state.get_position(pos.trade_id).status == "opening"
    assert rig.live_stops(R.XRP) == {}
    assert "unknown_position" in rig.holds()


def test_b45ind_f3_opposite_side_not_adopted(rig):
    pos, ecid = _opening_with_entry_row(rig)
    rig.ex.fill_market("XRPUSDT", "SELL", 10, cid=ecid)    # state long/BUY; borsada SHORT
    rig.run()
    assert rig.state.get_position(pos.trade_id).status == "opening"
    assert rig.live_stops(R.XRP) == {}
    assert "unknown_position" in rig.holds()


def test_b45ind_f3_exchange_qty_larger_than_entry_fill_not_adopted(rig):
    pos, ecid = _opening_with_entry_row(rig)
    rig.ex.fill_market("XRPUSDT", "BUY", 10, cid=ecid)
    rig.ex.fill_market("XRPUSDT", "BUY", 5)                # yabanci ek miktar: 15 > 10 + step/2
    rig.run()
    assert rig.state.get_position(pos.trade_id).status == "opening"
    assert "unknown_position" in rig.holds()


def test_b45ind_f3_query_error_gives_opening_unverified_finding_no_action(rig):
    pos, ecid = _opening_with_entry_row(rig)
    rig.ex.fill_market("XRPUSDT", "BUY", 10, cid=ecid)
    rig.down("/fapi/v1/order")
    m = rig.mark()
    rep = rig.run()
    assert f"opening_unverified:{pos.trade_id}" in rep.findings, rep.findings
    assert rig.state.get_position(pos.trade_id).status == "opening"
    assert rig.writes(m) == []
    # sorgu duzelince sonraki turda benimsenir
    rig.ex.request = rig.ex.__class__.request.__get__(rig.ex)
    rig.run(advance=15)
    assert rig.state.get_position(pos.trade_id).status == "open"


# ================================================================================================ FIX 4
def test_b45ind_f4_accepted_entry_market_row_requeried_opening_position_resolved(rig):
    pos, ecid = _opening_with_entry_row(rig, status="accepted")
    rig.ex.fill_market("XRPUSDT", "BUY", 10, cid=ecid)
    rig.run()
    p = rig.state.get_position(pos.trade_id)
    assert p.status == "open", f"opening'de takildi: {p.status}"
    assert len(rig.live_stops(R.XRP)) == 1


def test_b45ind_f4_accepted_exit_market_row_requeried_closing_position_resolved(rig):
    p, xcid = _closing_with_exit_row(rig, "accepted")
    rig.ex.fill_market("XRPUSDT", "SELL", 10, cid=xcid)    # cikis borsada dolmus, bildirim kacmis
    rig.run()
    cur = rig.state.get_position(p.trade_id)
    assert cur.status != "closing" or rig.events, "kabul edilmis cikis satiri yeniden sorgulanmadi"
    assert rig.state.get_order(xcid).status != "accepted" or rig.events


# ================================================================================================ FIX 5
def _first_idx(rig, m, method, part):
    for i, (mt, p, _) in enumerate(rig.ex.requests[m:]):
        if mt == method and part in p:
            return i
    return None


@pytest.mark.parametrize("entry", ["protect_first", "run"])
def test_b45ind_f5_resolve_before_read_and_single_stop(rig, entry):
    pos, ecid = _opening_with_entry_row(rig, status="unknown")
    rig.ex.fill_market("XRPUSDT", "BUY", 10, cid=ecid)
    m = rig.mark()
    if entry == "protect_first":
        rig.protect()
    else:
        rig.run()
    q = _first_idx(rig, m, "GET", "/fapi/v1/order")
    r = _first_idx(rig, m, "GET", "positionRisk")
    assert q is not None, "L1 cozumleme sorgusu yok"
    assert r is None or q < r, "L1 (cozumle) snapshot okumasindan once calismali"
    stops = [x for x in rig.posts(m) if x[1] == "/fapi/v1/algoOrder"]
    assert len(stops) <= 1 and len(rig.live_stops(R.XRP)) == 1


def test_b45ind_f5_f4_restart_posts_exactly_one_stop(mk):
    e = mk().boot()
    e.wire.on(entry_post, after=raising(Crash()))
    e.signal(DEC)
    with pytest.raises(Crash):
        e.decide()
    e2 = T.restart(e)
    mk.made.append(e2)
    assert len(e2.posted("s")) == 1, f"stop POST sayisi {len(e2.posted('s'))}"
    e2.tick(6)
    e2.tick(16)
    assert len(e2.posted("s")) == 1 and len(e2.stops()) == 1


# ================================================================================================ FIX 6
def _arm_429_then_clear(e):
    pos = e.enter()
    kill_on(e)
    e.wire.on(exit_post, before=lambda rec: FakeResp(429, {"code": -1003, "msg": "Too many"}, {"Retry-After": "30"}))
    e.tick(6)
    e.tick(6)
    assert e.kv("entries_blocked_reason") == "exchange_rate_limited"
    Path(e.cfg.kill_file).unlink()
    return pos


def test_b45ind_f6_rate_limited_block_clears_after_window_and_clean_reconcile(mk):
    e = mk().boot()
    _arm_429_then_clear(e)
    for _ in range(20):
        e.tick(16)
    assert e.kv("entries_blocked_reason") != "exchange_rate_limited", e.kv("entries_blocked_reason")


def test_b45ind_f6_rate_limited_block_clears_on_clean_restart(mk):
    e = mk().boot()
    _arm_429_then_clear(e)
    e.clock.advance(120)
    e2 = T.restart(e)
    mk.made.append(e2)
    e2.tick(6)
    e2.tick(16)
    assert e2.kv("entries_blocked_reason") != "exchange_rate_limited"


# ================================================================================================ FIX 7
@pytest.mark.parametrize("status", [418, 403, 451])
def test_b45ind_f7_ban_on_read_path_adds_exchange_ban_hold(mk, status):
    e = mk().boot()
    e.enter()
    e.wire.on(lambda r: r.method == "GET" and "positionRisk" in r.path,
              before=lambda rec: FakeResp(status, {"code": -1003, "msg": "banned"}, {"Retry-After": "120"}), once=False)
    for _ in range(6):
        e.tick(6)
    assert "exchange_ban" in holds(e), (status, holds(e))


def test_b45ind_f7_rate_limit_429_on_read_blocks_entries_and_silences_window(mk):
    e = mk().boot()
    e.enter()
    e.wire.on(lambda r: r.method == "GET" and "positionRisk" in r.path,
              before=lambda rec: FakeResp(429, {"code": -1003, "msg": "Too many"}, {"Retry-After": "60"}), once=False)
    e.tick(6)
    e.tick(6)
    assert e.kv("entries_blocked_reason") == "exchange_rate_limited"
    n = len(e.ex.requests)
    for _ in range(3):
        e.tick(6)                                          # ~18 sn: pencere (60 sn) icinde
    assert len(e.ex.requests) == n, "429 penceresi boyunca borsaya istek gitmemeli"


def test_b45ind_f7_exchange_auth_on_read_adds_exchange_auth_hold(mk):
    e = mk().boot()
    e.enter()
    e.wire.on(lambda r: r.method == "GET" and "positionRisk" in r.path,
              before=lambda rec: FakeResp(401, {"code": -2015, "msg": "Invalid API-key, IP, or permissions"}),
              once=False)
    for _ in range(6):
        e.tick(6)
    assert "exchange_auth" in holds(e), holds(e)


def test_b45ind_f7_429_on_exit_reject_arms_window_no_resend(mk):
    e = mk().boot()
    e.enter()
    kill_on(e)
    e.wire.on(exit_post, before=lambda rec: FakeResp(429, {"code": -1003, "msg": "Too many"}, {"Retry-After": "30"}),
              once=False)
    e.tick(6)
    for _ in range(3):
        e.tick(6)
    assert len(e.wire.writes(exit_post)) == 1, "ilk 429'dan sonra pencere acilmali; cikis tekrar gonderilmemeli"


# ================================================================================================ FIX 8
def _expire_entry(e):
    e.wire.on(entry_post, before=raising(TimeoutError("gitmedi")))
    e.signal(DEC)
    e.decide()
    t0 = e.state.get_order(cid_of("entry")).created_ts
    e.tick_at(t0 + timedelta(seconds=80))
    e.tick(16)


def test_b45ind_f8_entry_window_expiry_corrects_ledger_and_frees_entry_events(mk):
    e = mk().boot()
    _expire_entry(e)
    assert e.state.get_position(1).status == "closed"
    assert list(e.engine._entry_events) == [], "_entry_events[tid] sizdi"
    acts = [d.final_action for d in e.real_ledger.list_decisions()]
    assert acts == ["skipped"], f"karar duzeltmesi (entered -> skipped) yok: {acts}"


# ================================================================================================ FIX 9
def test_b45ind_f9_l2a_query_failure_finding_no_hold_no_kill_close(rig):
    ecid = R._late_fill_setup(rig)
    rig.kill.set("test", "drill")
    rig.down("/fapi/v1/order")
    m = rig.mark()
    rep = rig.run()
    assert f"late_fill_unverified:{R.XRP}" in rep.findings, rep.findings
    assert "unknown_position" not in rig.holds() and "late_fill" not in rig.holds()
    assert rig.posts(m) == [], "veri eksikken kill-kapatma yapilmamali"
    assert rig.state.get_position(5).status == "closed"


# ================================================================================================ EKSTRA
def test_b45ind_extra_l2a_reopened_trade_ledger_entry_drains_after_decision_superseded(mk):
    e = mk(reconcile_open_s=15.0).boot()
    _expire_entry(e)
    acts = [d.final_action for d in e.real_ledger.list_decisions()]
    assert acts == ["skipped"], acts
    # emir aslinda borsada dolmus (gec dolum): L2a kapali satiri yeniden acar
    e.ex.fill_market(SYM, "BUY", "7", cid=cid_of("entry"))
    for _ in range(8):
        e.tick(16)
    assert e.state.get_position(1).status in ("open",), e.state.get_position(1).status
    assert e.state.outbox_pending() == [], e.state.outbox_pending()
    assert e.engine.counters().get("outbox_failed", 0) == 0
    assert e.kv("entries_blocked_reason") != "outbox_stuck"
    assert len(e.real_ledger.list_open_trades()) == 1
