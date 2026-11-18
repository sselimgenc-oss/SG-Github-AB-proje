"""DD-11 (docs/motor/dd11-sifir-dolum-spec.md): sifir fiyat/miktar dolumu — bagimsiz sartname testleri Z-T1..Z-T6.

Yalniz sartnameden ve onceden var olan duzeneklerden yazildi (test_live_broker_impl_smoke.build/req, test_engine_live_spec.LiveEnv,
test_reconcile_live_spec.Rig, test_dd2_impl unblock-CLI deseni); gerceklemeye / farka BAKILMADI. Ag yok, sahte borsa.
Test adlari `test_dd11z_` onekiyle benzersizdir. Sayac adi `bad_fill`, CLI alt komutu `outbox-quarantine` (--dry-run varsayilan,
--apply) sartnamedendir; karantina tablosunun ic adi KULLANILMAZ (davranis: outbox'ta satir kalmaz).
"""
from __future__ import annotations

import argparse
import logging
from datetime import timedelta
from decimal import Decimal

import pytest

import test_engine_live_spec as T
import test_reconcile_live_spec as R
from fake_exchange import FakeResp
from test_live_broker_impl_smoke import XRP, build, req
from trader_engine import cli
from trader_engine.state import StateStore
from trader_engine.types import BrokerEvent, BrokerOrder, Fill


# ================================================================================================ ortak: broker
def _body(cid, *, status="FILLED", executed="10", avg="0.00", cum="0", oid=5555, ts=0):
    return {"clientOrderId": cid, "symbol": "XRPUSDT", "side": "BUY", "type": "MARKET", "reduceOnly": False,
            "origQty": "10", "time": ts, "updateTime": ts, "orderId": oid, "status": status, "executedQty": executed,
            "avgPrice": avg, "cumQuote": cum}


def _post_bad(b, ex, clock, body_kw, *, trades=(), seq=0):
    """Giris POST yanitini bozuk govdeyle degistir (borsa durumu da ayni bozuk govdeyi sorgularda dondurur)."""
    r = req("entry", 10.0, seq=seq)
    ms = int(clock.now().timestamp() * 1000)
    body = _body(r.client_id, ts=ms, **body_kw)
    ex.orders[r.client_id] = dict(body)
    ex.inject("/fapi/v1/order", FakeResp(200, dict(body)))
    for i, (px, qty) in enumerate(trades):
        ex.trades.append({"id": 9000 + i, "orderId": body["orderId"], "symbol": "XRPUSDT", "side": "BUY", "price": str(px),
                          "qty": str(qty), "quoteQty": str(Decimal(str(px)) * Decimal(str(qty))), "commission": "0.001",
                          "commissionAsset": "USDT", "realizedPnl": "0", "time": ms})
    b.prepare(XRP, 3)
    return r, b.market_order(r)


def _fills(evs):
    return [e for e in evs if e.kind == "fill" and e.fill is not None]


def _all_fills(b, clock, n=3):
    out = []
    for _ in range(n):
        clock.advance(1)
        out += _fills(b.poll(clock.now()))
    return out


def _assert_sane(fills):
    for e in fills:
        f = e.fill
        assert f.price > 0 and f.qty > 0 and f.price == f.price and f.qty == f.qty


# -- Z-T1
@pytest.mark.parametrize("avg", ["0.00", "0", "0.00000000"])
def test_dd11z_t1_zero_avgprice_uses_cumquote_over_executedqty(avg):
    b, ex, clock = build()
    r, res = _post_bad(b, ex, clock, dict(executed="10", avg=avg, cum="20.00"))
    assert res.status == "filled" and res.avg_price == pytest.approx(2.0) and res.filled_qty == pytest.approx(10.0)
    f = _fills(b.poll(clock.now()))
    assert len(f) == 1 and f[0].fill.price == pytest.approx(2.0) and f[0].fill.qty == pytest.approx(10.0)
    assert r.client_id not in b._pending_market


# -- Z-T2
def test_dd11z_t2_zero_avg_and_cumquote_falls_back_to_user_trades_vwap():
    b, ex, clock = build()
    r, res = _post_bad(b, ex, clock, dict(executed="10", avg="0.00", cum="0"), trades=[("2.0", "4"), ("3.0", "6")])
    assert res.status == "filled" and res.avg_price == pytest.approx(2.6)     # (4*2 + 6*3) / 10
    f = _fills(b.poll(clock.now()))
    assert len(f) == 1 and f[0].fill.price == pytest.approx(2.6) and f[0].fill.qty == pytest.approx(10.0)


def test_dd11z_t2_no_user_trades_stays_pending_then_fills_when_valid_response_arrives():
    b, ex, clock = build()
    r, res = _post_bad(b, ex, clock, dict(executed="10", avg="0.00", cum="0"))
    assert res.status == "accepted" and r.client_id in b._pending_market
    assert _all_fills(b, clock) == [], "fiyat bilinmezken dolum olayi uretilmemeli"
    assert r.client_id in b._pending_market and b.positions() is not None
    # sonraki sorguda gecerli yanit
    ms = int(clock.now().timestamp() * 1000)
    ex.orders[r.client_id] = _body(r.client_id, executed="10", avg="2.0", cum="20.0", ts=ms)
    clock.advance(1)
    f = _fills(b.poll(clock.now()))
    assert len(f) == 1 and f[0].fill.price == pytest.approx(2.0) and f[0].fill.qty == pytest.approx(10.0)
    assert r.client_id not in b._pending_market


# -- Z-T3
@pytest.mark.parametrize("avg,cum", [("0.00", "0"), ("2.0", "0"), ("2.0", "20.0")])
def test_dd11z_t3_filled_with_zero_executedqty_is_pending_no_fill(avg, cum):
    b, ex, clock = build()
    r, res = _post_bad(b, ex, clock, dict(executed="0", avg=avg, cum=cum))
    assert res.status == "accepted" and res.filled_qty == 0.0 and r.client_id in b._pending_market
    assert _all_fills(b, clock) == []
    # gecerli yanit gelince dolar
    ms = int(clock.now().timestamp() * 1000)
    ex.orders[r.client_id] = _body(r.client_id, executed="10", avg="2.0", cum="20.0", ts=ms)
    clock.advance(1)
    f = _fills(b.poll(clock.now()))
    assert len(f) == 1 and f[0].fill.qty == pytest.approx(10.0) and f[0].fill.price == pytest.approx(2.0)


def test_dd11z_t3_regression_valid_fill_unchanged():
    b, ex, clock = build()
    b.prepare(XRP, 3)
    r = b.market_order(req("entry", 10.0))
    assert r.status == "filled" and r.avg_price == 2.0
    f = _fills(b.poll(clock.now()))
    assert len(f) == 1 and f[0].fill.price == 2.0 and f[0].fill.qty == 10.0


# ================================================================================================ ortak: motor
def _bad_fill_event(env, pos, *, price, qty):
    cid = T.cid_of("entry")
    fill = Fill(client_id=cid, pair=T.XRP, role="entry", order_side="buy", qty=qty, price=price, fee=0.0, ts=env.clock.now(),
                reason="market")
    return BrokerEvent("fill", fill.ts, T.XRP, cid, fill)


@pytest.fixture
def env(tmp_path):
    e = T.LiveEnv(tmp_path).boot()
    yield e
    e.close()


def _opening_env(env, monkeypatch):
    """Karar ver, ama giris emri 'accepted' donsun: pozisyon `opening` kalir (dolum olayini biz besleriz)."""
    from trader_engine.types import OrderResult
    real = env.broker.market_order

    def accepted(rq):
        return OrderResult("accepted", rq.client_id, None, 0.0, None, 0.0, None, env.clock.now())
    monkeypatch.setattr(env.broker, "market_order", accepted)
    pos = env.enter()
    monkeypatch.setattr(env.broker, "market_order", real)
    assert pos is not None and pos.status == "opening", pos
    return pos


# -- Z-T4
@pytest.mark.parametrize("price,qty", [(0.0, 10.0), (2.0, 0.0), (0.0, 0.0), (float("nan"), 10.0), (2.0, float("inf")),
                                       (-1.0, 10.0)])
def test_dd11z_t4_engine_rejects_invalid_fill_no_outbox_no_stuck_stays_opening(env, monkeypatch, caplog, price, qty):
    pos = _opening_env(env, monkeypatch)
    ev = _bad_fill_event(env, pos, price=price, qty=qty)
    caplog.set_level(logging.CRITICAL)
    env.engine._on_entry_fill(ev, None, env.clock.now())    # dogrudan: tick/mutabakat pozisyonsuz `opening`i ayrica kapatabilir
    env.engine._post_commit()
    assert env.state.outbox_pending() == []
    assert not env.state.block_has("outbox_stuck") and env.kv("entries_blocked_reason") != "outbox_stuck"
    assert env.state.get_position(pos.trade_id).status == "opening"
    assert env.engine.counters().get("bad_fill", 0) == 1
    assert any(r.levelno >= logging.CRITICAL for r in caplog.records)
    assert env.engine.counters().get("outbox_failed", 0) == 0


def test_dd11z_t4_engine_valid_fill_still_opens_and_queues_entry(env, monkeypatch):
    pos = _opening_env(env, monkeypatch)
    ev = _bad_fill_event(env, pos, price=2.0, qty=10.0)
    env.engine._on_entry_fill(ev, None, env.clock.now())
    assert env.state.get_position(pos.trade_id).status in ("open", "closing", "closed")
    assert env.engine.counters().get("bad_fill", 0) == 0


# -- Z-T5
def _zero_entry_exchange(rig, ecid):
    """Borsa pozisyonu var ama entryPrice 0; emir sorgusunda avgPrice 0 (-> BrokerOrder.avg_price None)."""
    rig.ex.pos["XRPUSDT"]["entry"] = Decimal(0)
    rig.ex.orders[ecid]["avgPrice"] = "0"
    rig.ex.orders[ecid]["cumQuote"] = "0"


def test_dd11z_t5_late_fill_with_zero_entry_price_is_not_adopted(rig_):
    ecid = _late_fill_zero(rig_)
    rig_.run()
    p = rig_.state.get_position(5)
    assert p.status != "open", "fiyat bilinmeyen gec dolum benimsenmemeli"
    assert rig_.state.outbox_pending() == [] and getattr(rig_.ledger, "entries", []) == []
    assert not rig_.state.block_has("outbox_stuck")
    assert ecid


def test_dd11z_t5_adopt_opening_with_zero_entry_price_is_not_adopted(rig_):
    pos = R._opening_no_order(rig_)
    ecid = R.cidf("entry")
    with rig_.state.tx():
        rig_.state.insert_order(rig_._row(ecid, R.XRP, "entry", "buy", 10.0, None, False, "unknown", 0, pos.trade_id,
                                          rig_.clock.now()))
    R.at_run(rig_, 8)
    rig_.ex.fill_market("XRPUSDT", "BUY", 10, cid=ecid)
    _zero_entry_exchange(rig_, ecid)
    rig_.run()
    assert rig_.state.get_position(pos.trade_id).status == "opening"
    assert rig_.state.outbox_pending() == [] and getattr(rig_.ledger, "entries", []) == []


def _late_fill_zero(rig):
    ecid = R._late_fill_setup(rig)
    _zero_entry_exchange(rig, ecid)
    return ecid


@pytest.fixture
def rig_(tmp_path):
    r = R.Rig(tmp_path)
    R.set_t(r.clock, R.T0 + timedelta(seconds=5))
    yield r
    r.state.close()


def test_dd11z_t5_late_fill_with_valid_prices_still_adopted_regression(rig_):
    R._late_fill_setup(rig_)
    rig_.run()
    assert rig_.state.get_position(5).status == "open"
    ents = getattr(rig_.ledger, "entries", [])
    assert len(ents) == 1 and ents[0].entry_price == pytest.approx(2.0)     # outbox'a kuyruklandi ve bosaltildi


@pytest.mark.parametrize("avg,exch_entry", [(0.0, 0.0), (None, 0.0), (0.0, None)])
def test_dd11z_t5_on_adopted_entry_rejects_zero_price(env, monkeypatch, avg, exch_entry):
    pos = _opening_env(env, monkeypatch)
    row = env.state.get_order(T.cid_of("entry"))
    assert row is not None
    now = env.clock.now()
    bo = BrokerOrder(client_id=row.client_id, pair=row.pair, role="entry", order_side="buy", qty=row.qty,
                     trigger_price=None, reduce_only=False, status="filled", filled_qty=row.qty, avg_price=avg,
                     created_ts=now, updated_ts=now)
    bps = [] if exch_entry is None else [_bp(exch_entry, row.qty)]
    monkeypatch.setattr(env.broker, "positions", lambda: bps)
    env.engine._on_adopted_entry(row, bo)
    assert env.state.outbox_pending() == []
    assert env.state.get_position(pos.trade_id).status == "opening"
    assert not env.state.block_has("outbox_stuck")


def _bp(entry_price, qty):
    from trader_engine.types import BrokerPosition
    import dataclasses
    kw = {}
    for f in dataclasses.fields(BrokerPosition):
        kw[f.name] = {"pair": T.XRP, "side": "long", "qty": qty, "entry_price": entry_price, "mark_price": 2.0,
                      "leverage": 3, "liquidation_price": None, "margin_type": "isolated", "unrealized_pnl": 0.0,
                      "updated_ts": None}.get(f.name)
    return BrokerPosition(**kw)


# ================================================================================================ Z-T6: karantina CLI
ENTRY_BAD = dict(trade_id=2, decision_id=1, entry_ts="2026-12-28T10:00:05Z", entry_price=0.0, qty=7.25, leverage=3,
                 fee_entry=0.0, supersedes_id=None)
EXIT_OK = dict(trade_id=1, exit_ts="2026-12-28T11:00:00Z", exit_price=2.1, exit_reason="time_stop", planned_exit=None,
               fee_exit=0.01, funding_paid=0.0, supersedes_id=None, max_favorable_price=2.2, max_adverse_price=1.95,
               excursion_tf="1m")


def _ns(**kw):
    base = dict(bot="learner", config_dir="config", env=None, dry_run=False, apply=False)
    base.update(kw)
    return argparse.Namespace(**base)


def _run_cli(monkeypatch, cfg, *flags):
    monkeypatch.setattr(cli, "_load_cfg", lambda a: cfg)
    a = cli.build_parser().parse_args(["outbox-quarantine", "--bot", "learner", *flags])
    return a.fn(a)


def _seed(tmp_path, *, with_entry_trade=True):
    """Gercek defter + state: (istege bagli) trade 1 girisi defterde; outbox'ta [gecersiz giris(trade 2), gecerli cikis(trade 1)]."""
    e = T.LiveEnv(tmp_path).boot()
    if with_entry_trade:
        assert e.enter() is not None
        assert len(e.real_ledger.list_open_trades()) == 1
        assert e.state.outbox_pending() == []
    with e.state.tx():
        e.state.outbox_add("entry", 2, dict(ENTRY_BAD))
        e.state.outbox_add("exit", 1, dict(EXIT_OK))
    cfg = e.cfg
    e.hard_close()
    return e, cfg


def _pending(cfg):
    st = StateStore(cfg.state_path, bot="learner")
    try:
        return [(r.kind, r.trade_id) for r in st.outbox_pending()]
    finally:
        st.close()


def _drain(cfg):
    from trader_core import ledger as L
    st = StateStore(cfg.state_path, bot="learner")
    led = L.open_ledger(cfg.ledger_path, "learner", create=False)
    try:
        res = st.drain_outbox(led)
        return res, st.outbox_pending(), led.list_open_trades()
    finally:
        led.close()
        st.close()


def test_dd11z_t6_parser_defaults_dry_run_and_apply_flag():
    a = cli.build_parser().parse_args(["outbox-quarantine", "--bot", "learner"])
    assert not a.apply
    b = cli.build_parser().parse_args(["outbox-quarantine", "--bot", "learner", "--apply"])
    assert b.apply


def test_dd11z_t6_dry_run_changes_nothing_and_reports_invalid_row(tmp_path, monkeypatch, capsys):
    _, cfg = _seed(tmp_path)
    before = _pending(cfg)
    assert before == [("entry", 2), ("exit", 1)]
    for flags in ((), ("--dry-run",)):
        rc = _run_cli(monkeypatch, cfg, *flags)
        assert rc == cli.EXIT_OK
        assert _pending(cfg) == before, "dry-run (varsayilan) hicbir sey degistirmemeli"
    out = capsys.readouterr().out
    assert "7.25" in out, out                                        # karantinaya alinacak satir ozeti (qty)


def test_dd11z_t6_apply_moves_only_invalid_row_then_drain_clears_outbox_and_ledger_consistent(tmp_path, monkeypatch, capsys):
    _, cfg = _seed(tmp_path)
    rc = _run_cli(monkeypatch, cfg, "--apply")
    assert rc == cli.EXIT_OK
    out = capsys.readouterr().out
    assert "7.25" in out, out
    assert _pending(cfg) == [("exit", 1)], "yalniz gecersiz giris satiri tasinmali; gecerli cikis dokunulmaz"
    res, pend, open_trades = _drain(cfg)
    assert not res.failed and res.first_error is None
    assert pend == [] and open_trades == [], "cikis defterde yazildi; outbox bos; defter tutarli"


def test_dd11z_t6_apply_valid_exit_without_entry_is_ledger_invalid_and_also_quarantined(tmp_path, monkeypatch, capsys):
    _, cfg = _seed(tmp_path, with_entry_trade=False)                 # trade 1'in girisi defterde yok -> cikis da dogrulama hatasi
    rc = _run_cli(monkeypatch, cfg, "--apply")
    assert rc == cli.EXIT_OK
    assert _pending(cfg) == []
    res, pend, _ = _drain(cfg)
    assert not res.failed and pend == []


def test_dd11z_t6_apply_is_idempotent_and_leaves_valid_rows(tmp_path, monkeypatch):
    _, cfg = _seed(tmp_path)
    assert _run_cli(monkeypatch, cfg, "--apply") == cli.EXIT_OK
    assert _run_cli(monkeypatch, cfg, "--apply") == cli.EXIT_OK
    assert _pending(cfg) == [("exit", 1)]


def test_dd11z_t6_refuses_while_engine_runs_lock_held(tmp_path, monkeypatch):
    _, cfg = _seed(tmp_path)
    before = _pending(cfg)
    held = StateStore(cfg.state_path, bot="learner")                 # motor calisiyor benzetimi: state kilidi tutuluyor
    try:
        for flags in (("--apply",), ()):
            assert _run_cli(monkeypatch, cfg, *flags) != cli.EXIT_OK
        assert [(r.kind, r.trade_id) for r in held.outbox_pending()] == before
    finally:
        held.close()
    assert _pending(cfg) == before


def test_dd11z_t6_outbox_stuck_block_clears_after_apply_and_restart(tmp_path, monkeypatch):
    e = T.LiveEnv(tmp_path).boot()
    with e.state.tx():
        e.state.outbox_add("entry", 2, dict(ENTRY_BAD))
    e.engine._post_commit()
    assert e.state.block_has("outbox_stuck") and e.engine.counters()["outbox_failed"] == 1
    ex, clock, cfg = e.ex, e.clock, e.cfg
    e.hard_close()
    assert _run_cli(monkeypatch, cfg, "--apply") == cli.EXIT_OK
    e2 = T.LiveEnv(tmp_path, ex=ex, clock=clock).boot()
    try:
        e2.tick(6)
        e2.engine._post_commit()
        assert e2.state.outbox_pending() == []
        assert not e2.state.block_has("outbox_stuck")
        assert e2.kv("entries_blocked_reason") != "outbox_stuck"
    finally:
        e2.close()


# ================================================================================================ D1..D5 (mentor)
from fake_exchange import FakeResp as _FR  # noqa: E402


def _poll_until(b, clock, pred, *, step=1.0, limit_s=180.0):
    evs, t = [], 0.0
    while t < limit_s and not pred():
        clock.advance(step)
        t += step
        evs += b.poll(clock.now())
    return evs, t


# -- D1
def test_dd11z_d1_unrecoverable_price_is_throttled_then_given_up_with_finding_block_no_reject():
    b, ex, clock = build()
    r, res = _post_bad(b, ex, clock, dict(executed="10", avg="0.00", cum="0"))
    assert res.status == "accepted" and r.client_id in b._pending_market
    poll_s = b._live.poll_open_s
    n0 = ex.count("userTrades")
    evs, elapsed = _poll_until(b, clock, lambda: r.client_id not in b._pending_market)
    calls = ex.count("userTrades") - n0
    assert r.client_id not in b._pending_market, "vazgecilmeli"
    assert elapsed >= 30.0 and calls >= 2, (elapsed, calls)               # ilk deneme market_order'da (n0'dan once) + >= 2 yoklama
    assert calls <= int(elapsed / poll_s) + 1, f"{calls} userTrades cagrisi {elapsed:.0f} sn'de (poll_open_s={poll_s})"
    assert f"zero_fill_unresolved:{r.client_id}" in b.findings
    assert b.entries_blocked_reasons, "giris engeli kurulmali"
    assert [e for e in evs if e.kind == "order_rejected"] == []
    assert _fills(evs) == []


# -- D2
def test_dd11z_d2_register_position_drops_pending_entry_and_late_valid_response_does_not_overwrite():
    b, ex, clock = build()
    r, res = _post_bad(b, ex, clock, dict(executed="10", avg="0.00", cum="0"))
    assert r.client_id in b._pending_market
    ex.fill_market("XRPUSDT", "BUY", 10, cid="adopted_elsewhere")            # borsadaki gercek pozisyon (benimsenen)
    clock.advance(6)
    b.poll(clock.now())
    b.register_position(XRP, clock.now(), [])
    assert r.client_id not in b._pending_market
    assert XRP in b._open_pairs
    last = b._last_pos.get(XRP)
    ex.orders[r.client_id] = _body(r.client_id, executed="4", avg="2.5", cum="10", ts=int(clock.now().timestamp() * 1000))
    evs = []
    for _ in range(4):
        clock.advance(6)
        evs += b.poll(clock.now())
    assert [e for e in _fills(evs) if e.fill.client_id == r.client_id] == []
    assert XRP in b._open_pairs and b._last_pos.get(XRP) == last


# -- D3
def _l3b_rig(tmp_path, order_kw, on_adopted):
    rig = R.Rig(tmp_path)
    R.set_t(rig.clock, R.T0 + timedelta(seconds=5))
    pos = R._opening_no_order(rig)
    ecid = R.cidf("entry")
    with rig.state.tx():
        rig.state.insert_order(rig._row(ecid, R.XRP, "entry", "buy", 10.0, None, False, "accepted", 0, pos.trade_id,
                                        rig.clock.now()))
    rig.ex.orders[ecid] = {"clientOrderId": ecid, "symbol": "XRPUSDT", "side": "BUY", "type": "MARKET", "orderId": 9,
                           "reduceOnly": False, "origQty": "10", "status": "FILLED", "time": 0, "updateTime": 0, **order_kw}
    calls = []
    rig.orders.on_entry_adopted = lambda row, bo: (calls.append((row, bo)), on_adopted(rig, row, bo))[0]
    return rig, pos, ecid, calls


def test_dd11z_d3_accepted_entry_flat_exchange_filled_with_price_handled_like_l3b_filled(tmp_path):
    rig, pos, ecid, calls = _l3b_rig(tmp_path, dict(executedQty="10", avgPrice="2.0", cumQuote="20"), lambda *a: None)
    try:
        rig.run(advance=61 + 60)
        assert calls and all(c[1].avg_price == pytest.approx(2.0) and c[0].client_id == ecid for c in calls)   # L1 de cagirabilir
        assert not any(f.startswith("opening_unpriced") for f in rig.rec.__dict__.get("findings", []))
    finally:
        rig.state.close()


def test_dd11z_d3_accepted_entry_flat_exchange_filled_without_price_finding_and_pause(tmp_path):
    rig, pos, ecid, calls = _l3b_rig(tmp_path, dict(executedQty="10", avgPrice="0", cumQuote="0"), lambda *a: None)
    try:
        rep = rig.run(advance=61 + 60)
        assert f"opening_unpriced:{pos.trade_id}" in rep.findings, rep.findings
        assert rig.holds(), "duraklatma (pause) kurulmali"
        assert rig.state.outbox_pending() == [] and getattr(rig.ledger, "entries", []) == []
        assert rig.state.get_position(pos.trade_id).status == "opening"
    finally:
        rig.state.close()


# -- D4
def test_dd11z_d4_dry_run_and_apply_together_is_an_error_and_moves_nothing(tmp_path, monkeypatch):
    _, cfg = _seed(tmp_path)
    before = _pending(cfg)
    monkeypatch.setattr(cli, "_load_cfg", lambda a: cfg)
    try:
        a = cli.build_parser().parse_args(["outbox-quarantine", "--bot", "learner", "--dry-run", "--apply"])
    except SystemExit as e:
        assert e.code not in (0, None)
    else:
        assert a.fn(a) != cli.EXIT_OK
    assert _pending(cfg) == before


@pytest.mark.parametrize("raw", ["{not json", '{"unexpected": 1}'])
def test_dd11z_d4_malformed_payload_fails_cleanly_nothing_moved(tmp_path, monkeypatch, capsys, raw):
    import sqlite3
    _, cfg = _seed(tmp_path)
    con = sqlite3.connect(cfg.state_path)
    con.execute("INSERT INTO ledger_outbox(kind, trade_id, payload, done, created_ms) VALUES('entry', 3, ?, 0, 0)", (raw,))
    con.commit()
    con.close()

    def count():
        c = sqlite3.connect(cfg.state_path)
        try:
            return c.execute("SELECT COUNT(*) FROM ledger_outbox WHERE done=0").fetchone()[0]
        finally:
            c.close()
    n = count()
    for flags in (("--apply",), ()):
        rc = _run_cli(monkeypatch, cfg, *flags)                      # istisna sizmamali (traceback yok)
        assert rc != cli.EXIT_OK, flags
        assert count() == n, "hicbir satir tasinmamali"
    assert "Traceback" not in capsys.readouterr().err


# -- D5
def test_dd11z_d5_exchange_ban_in_user_trades_price_recovery_is_recorded():
    b, ex, clock = build()
    ex.inject("userTrades", _FR(418, {"code": -1003, "msg": "banned"}, {"Retry-After": "120"}))
    r, res = _post_bad(b, ex, clock, dict(executed="10", avg="0.00", cum="0"))
    assert res.status != "filled" and _all_fills(b, clock, 1) == []
    assert b.last_ban is not None and b.last_ban[0] == 418, b.last_ban
    assert b.counters()["exchange_bans"] >= 1
