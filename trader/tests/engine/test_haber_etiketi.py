"""Haber/duygu etiketi (features["duygu"], features["haber"]) yalniz kayit: hicbir karari/boyutu/riski degistirmez."""
from __future__ import annotations

import dataclasses
from datetime import timedelta
from pathlib import Path
from types import SimpleNamespace

import pytest

from trader_core import haber as HB
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
SIMDI = int((T0 + timedelta(seconds=5)).timestamp() * 1000)
ETIKET = {"duygu": {"deger": 28, "sinif": "Fear"}, "haber": {"BTC": {"adet_24s": 3, "ton": "pozitif"}}}


def _kur(tmp_path, etiket):
    clock = SimClock(T0 + timedelta(seconds=5))
    led = L.open_ledger(str(tmp_path / "l.sqlite"), "learner", create=True, clock=clock.now)
    led.init_params(_params(), reason="strategy:price_action_v1@1b.0")
    state = StateStore(":memory:", bot="learner")
    with state.tx():
        state.kv_set("day_start:2026-12-01", 1000.0)
    held: list[str] = []
    state.open_positions = lambda: [SimpleNamespace(pair=p, side="long", risk_amount=0.01, margin=0.1) for p in held]   # type: ignore[method-assign]
    broker = SimpleNamespace(account=lambda: SimpleNamespace(equity=1000.0, wallet=1000.0))
    rules = lambda p: SymbolRules(p, p.replace("/", ""), 0.01, 0.001, 0.001, 1e9, 5.0)  # noqa: E731
    g = EntryGate(CFG, led, state, Killswitch(str(tmp_path / "KILL"), clock), NoVeto(), clock, broker, rules)
    g.haber_etiket = etiket
    return SimpleNamespace(g=g, held=held, led=led, state=state)


@pytest.fixture
def cift(tmp_path):
    """(etiketsiz, etiketli) iki ayri ama ayni kurulum: ayni girdiler ayni kararlari vermeli."""
    (tmp_path / "a").mkdir()
    (tmp_path / "b").mkdir()
    a, b = _kur(tmp_path / "a", None), _kur(tmp_path / "b", lambda pair, ms: ETIKET)
    yield a, b
    for e in (a, b):
        e.state.close()
        e.led.close()


def _go(e, pair="BTC/USDT", bar=(110.0, 99.0, 5.0)):
    fr = SignalFrame(pair=pair, status="ok", detail=None, last=_row(pair=pair), table=None, trigger_bar=bar)
    return e.g.decide(fr, T0, e.g.pre(T0, "1h", True, "1h"), 1)


def _karar(out):
    """Karar ozeti: etiketi tasiyan `features` disindaki her seyi (boyut, risk, kod, eylem...) icerir."""
    ev = dataclasses.asdict(out.event) if out.event is not None else None
    if ev is not None:
        ev.pop("features")
    return (out.action, out.code, ev, out.ticket if hasattr(out, "ticket") else None)


SENARYOLAR = [
    dict(),                                              # giris
    dict(pair="NVDA/USDT"),                              # giris (seans etiketi)
    dict(bar=(100.0, 100.0, 5.0)),                       # flat_bar: alinmayan aday
    dict(bar=(110.0, 99.0, 0.0)),                        # flat_bar
]


def test_etiketli_ve_etiketsiz_ayni_kararlar(cift):
    a, b = cift
    for sen in SENARYOLAR:
        oa, ob = _go(a, **sen), _go(b, **sen)
        assert _karar(oa) == _karar(ob), sen
    a.held[:] = b.held[:] = [f"X{i}" for i in range(16)]                      # max_positions: alinmayan sinyal
    oa, ob = _go(a, "XRP/USDT"), _go(b, "XRP/USDT")
    assert oa.code == ob.code == "max_positions" and _karar(oa) == _karar(ob)
    a.held[:] = b.held[:] = ["NVDA/USDT", "MSFT/USDT", "AAPL/USDT"]           # cluster_cap
    oa, ob = _go(a, "GOOGL/USDT"), _go(b, "GOOGL/USDT")
    assert oa.code == ob.code == "cluster_cap" and _karar(oa) == _karar(ob)


def test_etiket_features_icinde_yalniz_kayit(cift):
    a, b = cift
    oa, ob = _go(a), _go(b)
    assert oa.action == ob.action == "enter"
    assert "duygu" not in oa.event.features and "haber" not in oa.event.features
    assert ob.event.features["duygu"] == ETIKET["duygu"] and ob.event.features["haber"] == ETIKET["haber"]
    assert {k: v for k, v in ob.event.features.items() if k not in ("duygu", "haber")} == dict(oa.event.features)
    assert (ob.event.size_qty, ob.event.size_notional, ob.event.leverage) == (oa.event.size_qty, oa.event.size_notional, oa.event.leverage)
    sk = _go(b, bar=(100.0, 100.0, 5.0))                                       # alinmayan aday da etiketlenir
    assert sk.action == "skip" and sk.event.features["haber"] == ETIKET["haber"]


@pytest.mark.parametrize("etiket", [None, lambda p, ms: None, lambda p, ms: {}, lambda p, ms: 1 / 0])
def test_etiket_yok_ya_da_hata_features_degismez(tmp_path, etiket):
    x, y = tmp_path / "x", tmp_path / "y"
    x.mkdir()
    y.mkdir()
    a, b = _kur(x, None), _kur(y, etiket)
    try:
        oa, ob = _go(a), _go(b)
        assert _karar(oa) == _karar(ob) and dict(oa.event.features) == dict(ob.event.features)
    finally:
        for e in (a, b):
            e.state.close()
            e.led.close()


def test_defter_etiketi_yazar_okur_ve_yeniden_yazim_cakismaz(cift):
    _, b = cift
    ev = _go(b).event
    did = b.led.record_decision(ev)
    got = b.led.get_decision(did).features
    assert got["duygu"] == ETIKET["duygu"] and got["haber"] == ETIKET["haber"]
    # ayni karar, onbellek degismis etiketle yeniden yazilir: idempotent (ayni id), cakisma yok; yalniz-kayit alani karari etkilemez
    ev2 = dataclasses.replace(ev, features={**ev.features, "duygu": {"deger": 70, "sinif": "Greed"}, "haber": {"BTC": {"adet_24s": 0, "ton": None}}})
    assert b.led.record_decision(ev2) == did
    ev3 = dataclasses.replace(ev, features={k: v for k, v in ev.features.items() if k not in ("duygu", "haber")})
    assert b.led.record_decision(ev3) == did
    # ama baska bir ozellik degisirse cakisma hala yakalanir
    ev4 = dataclasses.replace(ev, features={**ev.features, "stop_dist_atr": ev.features["stop_dist_atr"] + 1.0})
    with pytest.raises(L.LedgerConflictError):
        b.led.record_decision(ev4)


def test_motor_kablolamasi_onbellek_dosyasindan(tmp_path, monkeypatch):
    """Motorun kullandigi `haber.etiket` dosyadan okur; dosya yoksa None (kayda alan eklenmez)."""
    p = tmp_path / "haber_v1.json"
    monkeypatch.setenv("TRADER_HABER", str(p))
    assert HB.etiket("BTC/USDT", SIMDI) is None
    anlik = HB.guncelle({}, SIMDI, lambda u: {"data": [{"value": "28", "value_classification": "Fear"}]}, lambda u: b"")
    p.write_text(__import__("json").dumps(HB.belge_yap(anlik, SIMDI)), encoding="utf-8")
    assert HB.etiket("BTC/USDT", SIMDI) == {"duygu": {"deger": 28, "sinif": "Fear"}, "haber": None}


def test_motor_kagitta_etiketi_baglar_canlida_baglamaz():
    src = (ROOT / "src" / "trader_engine" / "engine.py").read_text(encoding="utf-8")
    bag = src.index("self.gate.haber_etiket")
    assert 'if cfg.mode == "paper"' in src[:bag] and src[:bag].rindex('if cfg.mode == "paper"') > src[:bag].rindex("self.gate = EntryGate(")
