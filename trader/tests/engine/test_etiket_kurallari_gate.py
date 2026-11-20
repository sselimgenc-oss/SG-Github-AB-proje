"""Etiket kurallari giris kapisinda (kagit): atlama satiri + kod, boyut/risk degismez, kapali kural izlenir, veri yok serbest."""
from __future__ import annotations

import dataclasses
from datetime import timedelta
from pathlib import Path
from types import SimpleNamespace

import pytest

from trader_core import etiket_kurallari as EK
from trader_core import ledger as L
from trader_engine.clock import SimClock
from trader_engine.config import load_cli_config
from trader_engine.gates import EntryGate, NoVeto
from trader_engine.killswitch import Killswitch
from trader_engine.state import StateStore
from trader_engine.strategy_runner import SignalFrame
from trader_engine.types import SymbolRules

from test_engine_05_impl_smoke import T0, _params, _row  # noqa: E402

ROOT = Path(__file__).resolve().parents[2]
CFG = load_cli_config(ROOT / "config", "learner", "paper")
EKCFG = EK.build_config({"rejim": {}, "duygu": {}, "kalabalik": {}})


def _kur(tmp_path, *, cfg=EKCFG, acik=None, duygu=None, ct=None):
    clock = SimClock(T0 + timedelta(seconds=5))
    led = L.open_ledger(str(tmp_path / "l.sqlite"), "learner", create=True, clock=clock.now)
    led.init_params(_params(), reason="strategy:price_action_v1@1b.0")
    state = StateStore(":memory:", bot="learner")
    with state.tx():
        state.kv_set("day_start:2026-12-01", 1000.0)
    state.open_positions = lambda: []   # type: ignore[method-assign]
    broker = SimpleNamespace(account=lambda: SimpleNamespace(equity=1000.0, wallet=1000.0))
    rules = lambda p: SymbolRules(p, p.replace("/", ""), 0.01, 0.001, 0.001, 1e9, 5.0)  # noqa: E731
    g = EntryGate(CFG, led, state, Killswitch(str(tmp_path / "KILL"), clock), NoVeto(), clock, broker, rules)
    g.etiket_cfg = cfg
    g.etiket_durum = (lambda: acik) if acik is not None else None
    g.haber_etiket = (lambda pair, ms: {"duygu": duygu, "haber": None}) if duygu is not None else None
    g.ct_kadro = (lambda: {"BTC/USDT": ct}) if ct is not None else None
    return SimpleNamespace(g=g, led=led, state=state)


@pytest.fixture
def mk(tmp_path):
    made = []

    def f(**kw):
        d = tmp_path / f"e{len(made)}"
        d.mkdir()
        e = _kur(d, **kw)
        made.append(e)
        return e
    yield f
    for e in made:
        e.state.close()
        e.led.close()


def _go(e, **row):
    fr = SignalFrame(pair="BTC/USDT", status="ok", detail=None, last=_row(**row), table=None, trigger_bar=(110.0, 99.0, 5.0))
    return e.g.decide(fr, T0, e.g.pre(T0, "1h", True, "1h"), 1)


def test_rejim_karsiti_atlar_ve_satir_yazilir(mk):
    e = mk()
    o = _go(e, regime="trend_down", side="long")
    assert o.action == "skip" and o.code == "etiket_rejim" and o.event.skip_reason == "etiket_rejim"
    assert o.event.veto_reason.startswith("gate:etiket_rejim") and o.size is None
    did = e.led.record_decision(o.event)                                  # defter yeni kodu kabul eder
    assert e.led.get_decision(did).skip_reason == "etiket_rejim"
    assert e.g.counters["skip:etiket_rejim"] == 1 and e.g.counters["etiket_atladi:etiket_rejim"] == 1
    assert _go(e, regime="trend_up", side="long").action == "enter"
    assert _go(e, regime="trend_up", side="short", planned_stop=102.0).code == "etiket_rejim"


def test_duygu_ve_kalabalik_atlar(mk):
    e = mk(duygu={"deger": 10, "sinif": "Extreme Fear"})
    assert _go(e).code == "etiket_duygu"
    e = mk(ct={"long": 19, "short": 1, "net_yon": "long"})
    assert _go(e).code == "etiket_kalabalik"


def test_boyut_ve_risk_degismez_serbest_kararda(mk):
    a, b = mk(cfg=None), mk()                                              # kuralsiz vs kurallu: serbest giriste ayni karar
    oa, ob = _go(a), _go(b)
    assert oa.action == ob.action == "enter"
    ea, eb = dataclasses.asdict(oa.event), dataclasses.asdict(ob.event)
    assert ea == eb and (oa.size, oa.leverage) == (ob.size, ob.leverage)


def test_veri_yok_fail_open_ve_sayilir(mk):
    e = mk()                                                              # duygu/CT yok
    o = _go(e)
    assert o.action == "enter"
    assert e.g.counters["etiket_veri_yok:etiket_duygu"] == 1 and e.g.counters["etiket_veri_yok:etiket_kalabalik"] == 1


def test_hata_giris_serbest(mk):
    e = mk()
    e.g.ct_kadro = lambda: 1 / 0
    e.g.etiket_durum = lambda: 1 / 0
    assert _go(e, regime="trend_down").code == "etiket_rejim"             # durum okunamazsa kural acik sayilir
    e.g.etiket_cfg = {"rejim": 5}                                         # bozuk cfg: istisna yutulur
    assert _go(e, regime="trend_down").action == "enter"


def test_kapali_kural_atlamaz_ama_not_eder(mk):
    e = mk(acik={EK.REJIM: False, EK.DUYGU: True, EK.KALABALIK: True})
    o = _go(e, regime="trend_down")
    assert o.action == "enter" and o.event.features[EK.FEATURE_ANAHTAR] == EK.REJIM
    assert e.g.counters["etiket_atlardi:etiket_rejim"] == 1
    did = e.led.record_decision(o.event)
    assert e.led.get_decision(did).features[EK.FEATURE_ANAHTAR] == EK.REJIM
    # kapali + acik kural ayni anda: acik olan atlar
    e2 = mk(acik={EK.REJIM: False, EK.DUYGU: True, EK.KALABALIK: True}, duygu={"deger": 5, "sinif": "x"})
    o2 = _go(e2, regime="trend_down")
    assert o2.code == "etiket_duygu" and o2.event.features[EK.FEATURE_ANAHTAR] == EK.REJIM


def test_ml_filtre_sirasi_korunur_ve_testnet_live_kapisi_yok(mk):
    e = mk()
    e.g.ml_filtre = SimpleNamespace(karar=lambda *a, **k: SimpleNamespace(izin=False, neden="x", puan=0.1))
    assert _go(e, regime="trend_down").code == "ml_filter"                # ML once


def test_canli_testnet_etiket_kurali_calismaz(mk):
    e = mk()
    e.g.cfg = dataclasses.replace(CFG, mode="live")
    e.g._etiket_karari = lambda *a, **k: (_ for _ in ()).throw(AssertionError("canlida etiket kurali cagrilmamali"))
    o = _go(e, regime="trend_down")
    assert o.code != "etiket_rejim"
