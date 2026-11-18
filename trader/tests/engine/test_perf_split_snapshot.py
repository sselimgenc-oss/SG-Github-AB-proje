"""Performans duzeltmesi: bolunmus paper-broker snapshot'i (terminal emirler `broker_order:<cid>` satirlari,
govde `broker_snapshot` yalniz canli emirler). Gercek `Engine._save_broker/_restore_broker` surulur."""
from __future__ import annotations

import json
import random
from datetime import timedelta

import pytest
from test_engine_03_impl_smoke import P, bar, mk, req, step
from test_engine_05_spec import BTC, ETH, M1, T0 as T0_ENG, Env

from trader_engine.engine import Engine
from trader_engine.state import StateStore

BO = "broker_order:"


class E:
    """Gercek `_save_broker/_restore_broker`i kullanan minimal Engine yerine-gecen."""
    _BO = Engine._BO
    _save_broker = Engine._save_broker
    _restore_broker = Engine._restore_broker

    def __init__(self, state, broker):
        self.state, self.broker = state, broker


def norm(s):
    return json.dumps(s, sort_keys=True)


def make_bars(seed, n):
    rnd = random.Random(seed)
    px, bars = 100.0, []
    for i in range(n):
        o = px
        px = max(10.0, round(px * (1 + rnd.uniform(-0.012, 0.012)), 2))
        bars.append(bar(i, o=o, h=round(max(o, px) * 1.003, 2), lo=round(min(o, px) * 0.997, 2), c=px))
    return bars


def ops(b, i, bars, rnd):
    ev = step(b, {P: bars[i]})
    r = rnd.random()
    if not b.positions() and r < 0.5:
        b.market_order(req(f"e{i}", "entry", "buy" if rnd.random() < .5 else "sell", 1.0))
    elif b.positions():
        long = b.positions()[0].side == "long"
        side = "sell" if long else "buy"
        m = bars[i].mark_c
        if r < 0.3:
            b.place_stop(req(f"s{i}", "stop", side, 1.0, round(m * (0.985 if long else 1.015), 2)))
        elif r < 0.5:
            b.place_target(req(f"t{i}", "target", side, 1.0, round(m * (1.01 if long else 0.99), 2)))
        elif r < 0.6:
            b.market_order(req(f"x{i}", "exit", side, 1.0))
        elif r < 0.7:
            oo = b.open_orders()
            if oo:
                b.cancel(P, rnd.choice(oo).client_id)
    return ev


def n_terminal(b):
    return sum(1 for o in b._orders.values() if o.status != "new")


def new_store(tmp_path, name="s.sqlite"):
    return StateStore(str(tmp_path / name), bot="t")


def same(a, b, order=True):
    # order=False: kv_set `sort_keys=True` yazar, bu yuzden tek-blob yolu (eski/yedek) emir sirasini koruyamaz (onceden
    # de boyleydi); yalniz icerik karsilastirilir.
    assert norm(a.snapshot()) == norm(b.snapshot())
    if order:
        assert list(a._orders) == list(b._orders)
        assert list(a.snapshot()["orders"]) == list(b.snapshot()["orders"])


# ------------------------------------------------------------------------------------------ 1. bolunmus gidis-donus
@pytest.mark.parametrize("seed", [0, 1, 2, 3])
def test_split_roundtrip_random_ops_with_failures_and_restarts(tmp_path, seed):
    n = 300
    bars = make_bars(seed, n)
    ref, _ = mk()
    ref.prepare(P, 3)
    b, _ = mk()
    b.prepare(P, 3)
    st = new_store(tmp_path)
    e = E(st, b)
    r1, r2, r3 = random.Random(seed + 1000), random.Random(seed + 1000), random.Random(seed + 5)
    evr, evb = [], []
    with st.tx():
        e._save_broker()
    for i in range(n):
        evr += ops(ref, i, bars, r1)
        mode = r3.random()
        if mode < 0.15:        # basarisiz adim: degistir, tx icinde kaydet, geri al, geri yukle, sonra tekrar oyna
            stt = r2.getstate()
            try:
                with st.tx():
                    ops(b, i, bars, r2)
                    e._save_broker()
                    raise RuntimeError("x")
            except RuntimeError:
                pass
            e._restore_broker(st.kv_get("broker_snapshot"))
            r2.setstate(stt)
        elif mode < 0.25:      # yeniden baslatma
            b, _ = mk()
            e.broker = b
            e._restore_broker(st.kv_get("broker_snapshot"))
        with st.tx():
            evb += ops(b, i, bars, r2)
            e._save_broker()
        assert [o.client_id for o in b.open_orders()] == [o.client_id for o in ref.open_orders()], (seed, i)
    assert evr == evb
    same(b, ref)
    fresh, _ = mk()
    e.broker = fresh
    e._restore_broker(st.kv_get("broker_snapshot"))
    same(fresh, ref)
    assert len(st.kv_prefix(BO)) == n_terminal(ref) > 0
    body = st.kv_get("broker_snapshot")
    assert all(o["status"] == "new" for o in body["orders"].values())


# ------------------------------------------------------------------------------------------ 2. basarisiz adim
def test_failed_step_rolls_back_rows_and_replay_commits_once(tmp_path):
    ref, _ = mk()
    b, _ = mk()
    for x in (ref, b):
        x.prepare(P, 3)
        x.market_order(req("e1", "entry", "buy", 1.0))
        step(x, {P: bar(0)})
        x.place_stop(req("s1", "stop", "sell", 1.0, 98.0))
    st = new_store(tmp_path)
    e = E(st, b)
    with st.tx():
        e._save_broker()
    pre = norm(b.snapshot())
    assert set(st.kv_prefix(BO)) == {BO + "e1"}
    crash = bar(1, o=99.2, lo=96.0, h=99.5, c=97.0)
    with pytest.raises(RuntimeError):
        with st.tx():
            step(b, {P: crash})
            assert b._orders["s1"].status == "filled"
            e._save_broker()
            raise RuntimeError("boom")
    e._restore_broker(st.kv_get("broker_snapshot"))
    assert norm(b.snapshot()) == pre and b._orders["s1"].status == "new"
    assert BO + "s1" not in st.kv_prefix(BO) and set(st.kv_prefix(BO)) == {BO + "e1"}
    # tekrar oynat + commit
    step(ref, {P: crash})
    with st.tx():
        step(b, {P: crash})
        e._save_broker()
    rows = st.kv_prefix(BO)
    assert [k for k in rows if k == BO + "s1"] == [BO + "s1"] and len(rows) == n_terminal(ref) == 2
    same(b, ref)
    with st.tx():
        e._save_broker()                                  # ikinci kayit satiri cogaltmaz / bozmaz
    assert len(st.kv_prefix(BO)) == 2
    fresh, _ = mk()
    e.broker = fresh
    e._restore_broker(st.kv_get("broker_snapshot"))
    same(fresh, ref)


# ------------------------------------------------------------------------------------------ 3. eski tek-blob
def test_legacy_single_blob_restores_and_upgrades(tmp_path):
    bars = make_bars(7, 300)
    ref, _ = mk()
    ref.prepare(P, 3)
    rnd = random.Random(7)
    for i in range(300):
        ops(ref, i, bars, rnd)
    nt = n_terminal(ref)
    assert nt > 0
    st = new_store(tmp_path)
    with st.tx():
        st.kv_set("broker_snapshot", ref.snapshot())
    assert st.kv_prefix(BO) == {}
    b, _ = mk()
    e = E(st, b)
    e._restore_broker(st.kv_get("broker_snapshot"))
    same(b, ref, order=False)
    with st.tx():
        e._save_broker()
    body = st.kv_get("broker_snapshot")
    assert "order_idx" in body and all(o["status"] == "new" for o in body["orders"].values())
    assert set(body["order_idx"]) == set(body["orders"])
    assert len(st.kv_prefix(BO)) == nt
    b2, _ = mk()
    e.broker = b2
    e._restore_broker(st.kv_get("broker_snapshot"))
    same(b2, ref, order=False)
    assert list(b2._orders) == list(b._orders)          # yukseltmeden sonra sira, ilk geri yuklemeyle ayni


# ------------------------------------------------------------------------------------------ 4. sira korunumu
def test_live_order_creation_order_survives_split_restore(tmp_path):
    b, _ = mk()
    b.prepare(P, 3)
    b.market_order(req("m_entry", "entry", "buy", 2.0))
    step(b, {P: bar(0)})
    b.place_stop(req("z_stop", "stop", "sell", 1.0, 95.0))      # once olusturuldu, sonra siralanir
    b.place_stop(req("a_stop", "stop", "sell", 1.0, 94.0))
    b.market_order(req("b_exit", "exit", "sell", 0.5))
    step(b, {P: bar(1)})                                        # b_exit terminal olur; stoplar canli kalir
    assert [o.client_id for o in b.open_orders()] == ["z_stop", "a_stop"]
    st = new_store(tmp_path)
    with st.tx():
        E(st, b)._save_broker()
    fresh, _ = mk()
    e = E(st, fresh)
    e._restore_broker(st.kv_get("broker_snapshot"))
    assert [o.client_id for o in fresh.open_orders()] == ["z_stop", "a_stop"]
    assert list(fresh._orders) == list(b._orders) == ["m_entry", "z_stop", "a_stop", "b_exit"]
    same(fresh, b)
    # restore sonrasi yeni emirler sona eklenir
    fresh.place_stop(req("0_new", "stop", "sell", 0.5, 93.0))
    assert list(fresh._orders)[-1] == "0_new"


# ------------------------------------------------------------------------------------------ 5. motor duzeyi
def _run_engine(tmp_path, name, fail):
    (tmp_path / name).mkdir()
    e = Env(tmp_path / name)
    e.start()
    p = e.open_pos(BTC, T0_ENG)
    assert p is not None
    stop = [o for o in e.broker.open_orders(BTC) if o.role == "stop"][0]
    cid = stop.client_id
    ts1 = T0_ENG + M1
    if fail:
        eng = e.engine
        real = eng._kill_step
        hit = []

        def boom(end):
            if not hit:
                hit.append(1)
                assert e.broker._orders[cid].status == "filled"     # dolum zaten oldu
                raise RuntimeError("enjekte hata")
            return real(end)
        eng._kill_step = boom
        e.step(ts1, [BTC], price=97.0, hi=99.0, lo=96.0)
        assert hit and eng._c["callback_errors"] == 1
        # _after_failure: broker kv'den geri yuklendi, state tx geri alindi
        assert e.broker._orders[cid].status == "new" and e.pos(BTC).status == "open"
        assert BO + cid not in e.state.kv_prefix(BO)
        eng._kill_step = real
        e.step(ts1, [BTC], price=97.0, hi=99.0, lo=96.0)             # ayni adim tekrar
    else:
        e.step(ts1, [BTC], price=97.0, hi=99.0, lo=96.0)
    for k in range(2, 6):
        e.step(T0_ENG + k * M1, [BTC], price=100.0)
    return e, cid


def test_engine_failed_step_after_fill_matches_clean_run(tmp_path):
    ref, cid = _run_engine(tmp_path, "ref", fail=False)
    f, cid2 = _run_engine(tmp_path, "fail", fail=True)
    assert cid == cid2
    assert ref.broker._orders[cid].status == "filled"
    assert norm(f.broker.snapshot()) == norm(ref.broker.snapshot())
    assert list(f.broker._orders) == list(ref.broker._orders)

    def pos(e):
        return sorted((x.pair, x.status, x.side, x.qty, x.entry_price) for x in
                      [*e.state.open_positions(), *e.state.closed_positions_since(T0_ENG - timedelta(days=1))])
    assert pos(f) == pos(ref) and pos(ref)
    assert BO + cid in f.state.kv_prefix(BO)
    assert len(f.state.kv_prefix(BO)) == n_terminal(f.broker)
    # restart sonrasi da ayni
    from trader_engine.brokers.paper import PaperBroker
    nb = PaperBroker(f.broker._cfg, f.rules_fn, lambda p, s, e: [], f.clock)
    f.engine.broker = nb
    f.engine._restore_broker(f.state.kv_get("broker_snapshot"))
    assert norm(nb.snapshot()) == norm(ref.broker.snapshot()) and list(nb._orders) == list(ref.broker._orders)
    # terminal cid tekrar yerlestirilemez
    for br in (f.broker, nb):
        r = br.place_stop(req(cid, "stop", "sell", 1.0, 90.0))
        assert r.status == "rejected" and r.reason == "duplicate_client_id"
    f.close()
    ref.close()


# ------------------------------------------------------------------------------------------ 6. yedek yol
class NoSplit:
    """snapshot_split'i olmayan broker: `_save_broker` eski tek-blob yolunu kullanir."""

    def __init__(self, inner):
        self.inner = inner

    def snapshot(self):
        return self.inner.snapshot()

    def restore(self, snap):
        self.inner.restore(snap)


def test_broker_without_snapshot_split_uses_single_blob(tmp_path):
    bars = make_bars(3, 120)
    inner, _ = mk()
    inner.prepare(P, 3)
    rnd = random.Random(3)
    for i in range(120):
        ops(inner, i, bars, rnd)
    assert n_terminal(inner) > 0
    wrapped = NoSplit(inner)
    assert not hasattr(wrapped, "snapshot_split")
    st = new_store(tmp_path)
    e = E(st, wrapped)
    with st.tx():
        e._save_broker()
    assert st.kv_prefix(BO) == {}
    assert norm(st.kv_get("broker_snapshot")) == norm(inner.snapshot())
    assert len(st.kv_get("broker_snapshot")["orders"]) == len(inner._orders)
    other, _ = mk()
    e.broker = NoSplit(other)
    e._restore_broker(st.kv_get("broker_snapshot"))
    same(other, inner, order=False)
