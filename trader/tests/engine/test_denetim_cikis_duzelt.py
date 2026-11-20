"""Denetim duzeltmeleri (20.11): kismi cikis sonrasi `slippage_exit` SON bacaktan, kismi cikis emri `orders` tablosunda,
kismi dolumun ikinci teslimi yok sayilir. Gercek kayit yolu (motor -> outbox -> defter); yalniz sentetik veri."""
from __future__ import annotations

import numpy as np
import pytest
from test_engine_05_spec import BTC, H, M1, T0, Env  # noqa: F401  (sentetik motor duzenegi)

from trader_engine.position_manager import ExitContext
from trader_engine.types import BrokerEvent, Fill

D1 = T0 + H
PT = {"default": {"partial": {"trigger_r": 1.5, "frac": 0.5}}}


def _ctx(high, last, D=D1, low=100.5):
    return ExitContext(bar_close_ts=D, highs=np.array([high]), lows=np.array([low]), atrs=np.array([1.0]),
                       regime_last="trend_up", last_close=last, n_closed=1)


def _partial_done(tmp_path, modes=PT):
    env = Env(tmp_path, mode="paper", exit_modes=modes)
    env.start()
    p = env.open_pos(BTC, T0, entry=100.0, stop=98.0)
    for k in range(1, 60):
        env.step(T0 + k * M1, pairs=(BTC,), price=104.0, hi=104.0, lo=104.0)
    env.src.ctx[(BTC, D1)] = _ctx(104.0, 104.0)
    env.decide(D1)
    env.step(D1, pairs=(BTC,), price=104.0, hi=104.0, lo=104.0)
    return env, p


def test_slippage_exit_uses_final_leg_not_blended_price(tmp_path):
    env, p = _partial_done(tmp_path)
    stop = env.state.get_position(p.trade_id).current_stop
    env.step(D1 + M1, pairs=(BTC,), price=stop + 0.5, hi=stop + 0.5, lo=stop - 1.0)        # bosluksuz stop vurusu
    t = env.real_ledger.get_trade(p.trade_id)
    pk = env.state.kv_get(f"partial:{p.trade_id}")
    q1, p1 = pk["qty"], pk["price"]
    leg2 = (t.exit_price * t.qty - q1 * p1) / (t.qty - q1)
    assert leg2 == pytest.approx(stop * (1 - 0.0005), rel=1e-9) or leg2 < stop       # son bacak stopun altinda dolar
    true_slip = (t.planned_exit - leg2) / t.planned_exit
    assert 0 <= true_slip * 1e4 <= 10
    assert t.slippage_exit == pytest.approx(true_slip, abs=1e-9)
    # karma fiyata gore hesap cok farkli olurdu (kismi kar icinde): regresyon ayirt edici
    blended = (t.planned_exit - t.exit_price) / t.planned_exit
    assert abs(blended - true_slip) > 1e-3
    # karma cikis fiyati ve gerceklesen PnL davranisi degismedi: brut = tam adet * (karma - giris)
    assert t.gross_pnl == pytest.approx(t.qty * (t.exit_price - t.entry_price))


def test_slippage_exit_without_partial_unchanged(tmp_path):
    env = Env(tmp_path, mode="paper")
    env.start()
    p = env.open_pos(BTC, T0, entry=100.0, stop=98.0)
    for k in range(1, 5):
        env.step(T0 + k * M1, pairs=(BTC,), price=100.5, hi=100.5, lo=100.5)
    env.step(T0 + 6 * M1, pairs=(BTC,), price=98.4, hi=98.4, lo=97.5)
    t = env.real_ledger.get_trade(p.trade_id)
    assert t.planned_exit == pytest.approx(98.0)
    assert t.slippage_exit == pytest.approx((t.planned_exit - t.exit_price) / t.planned_exit)


def test_partial_order_recorded_in_orders_table(tmp_path):
    env, p = _partial_done(tmp_path)
    pk = env.state.kv_get(f"partial:{p.trade_id}")
    assert pk["state"] == "done"
    row = env.state.get_order(pk["cid"])
    assert row is not None and row.role == "exit" and row.trade_id == p.trade_id
    assert row.status == "filled" and row.qty == pytest.approx(pk["qty"])
    pos = env.state.get_position(p.trade_id)
    assert pos.status == "open"                      # kismi emir pozisyonu `closing`e gecirmez


def test_duplicate_partial_fill_event_is_ignored(tmp_path):
    env, p = _partial_done(tmp_path)
    pk = env.state.kv_get(f"partial:{p.trade_id}")
    before = env.state.get_position(p.trade_id)
    ev = BrokerEvent(kind="fill", ts=D1, pair=BTC, client_id=pk["cid"], fill=Fill(
        client_id=pk["cid"], pair=BTC, role="exit", order_side="sell", qty=pk["qty"], price=pk["price"], fee=pk["fee"],
        ts=D1, reason="market", ref_price=104.0))
    n = env.engine._c["duplicate_fill_ignored"]
    env.engine._on_exit_fill(ev, None, D1)
    after = env.state.get_position(p.trade_id)
    assert after.status == "open" and after.qty == pytest.approx(before.qty)
    assert env.engine._c["duplicate_fill_ignored"] == n + 1
    assert env.state.kv_get(f"partial:{p.trade_id}")["state"] == "done"
    assert env.real_ledger.get_trade(p.trade_id).exit_price is None          # defterde cikis satiri yok
