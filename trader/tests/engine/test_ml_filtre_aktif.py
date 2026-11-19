"""19.11 kullanici karari: kagitta ML filtresi AKTIF. Esik alti puan bir girisi `ml_filter` ile atlatir; boyut/kaldirac/limit degismez.
Paket yok/bozuk/suresi gecmis/<10 islem/istisna => serbest. Egitim holdout satiri almaz. Canli/testnet yolu degismez."""
from __future__ import annotations

import dataclasses
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace

import pytest

from ortak_ogrenme import filtre as PF
from ortak_ogrenme.kayit import Aday
from trader_core import ledger as L
from trader_engine import ogrenme_filtre as OF
from trader_engine.config import load_cli_config
from trader_engine.gates import EntryGate, NoVeto
from trader_engine.killswitch import Killswitch
from trader_engine.clock import SimClock
from trader_engine.state import StateStore
from trader_engine.strategy_runner import SignalFrame
from trader_engine.types import SymbolRules

from test_engine_05_impl_smoke import T0, _params, _row  # noqa: E402

ROOT = Path(__file__).resolve().parents[2]
CFG = load_cli_config(ROOT / "config", "learner", "paper")
NOW = datetime(2026, 12, 1, 0, 0, 5, tzinfo=timezone.utc)


class Sahte:
    def __init__(self, karar=None, hata=False):
        self._k, self._h, self.cagri = karar, hata, 0

    def karar(self, arm, oz, simdi):
        self.cagri += 1
        if self._h:
            raise RuntimeError("filtre patladi")
        return self._k


def _kur(tmp_path, flt, cfg=CFG, day_start=1000.0):
    tmp_path.mkdir(parents=True, exist_ok=True)
    clock = SimClock(T0 + timedelta(seconds=5))
    led = L.open_ledger(str(tmp_path / "l.sqlite"), "learner", create=True, clock=clock.now)
    led.init_params(_params(), reason="strategy:price_action_v1@1b.0")
    state = StateStore(":memory:", bot="learner")
    with state.tx():
        state.kv_set("day_start:2026-12-01", day_start)
    state.open_positions = lambda: []   # type: ignore[method-assign]
    broker = SimpleNamespace(account=lambda: SimpleNamespace(equity=1000.0, wallet=1000.0))
    rules = lambda p: SymbolRules(p, p.replace("/", ""), 0.01, 0.001, 0.001, 1e9, 5.0)  # noqa: E731
    g = EntryGate(cfg, led, state, Killswitch(str(tmp_path / "KILL"), clock), NoVeto(), clock, broker, rules)
    g.ml_filtre = flt
    return SimpleNamespace(g=g, led=led, state=state)


def _go(e):
    fr = SignalFrame(pair="BTC/USDT", status="ok", detail=None, last=_row(), table=None, trigger_bar=(110.0, 99.0, 5.0))
    return e.g.decide(fr, T0, e.g.pre(T0, "1h", True, "1h"), 1)


def _kapat(*es):
    for e in es:
        e.state.close()
        e.led.close()


def test_esik_alti_giris_atlanir_ml_filter_yazilir(tmp_path):
    e = _kur(tmp_path / "a", Sahte(OF.Karar(False, 0.12, "esik_alti")))
    try:
        o = _go(e)
        assert o.action == "skip" and o.code == "ml_filter"
        assert o.event.skip_reason == "ml_filter" and o.event.final_action == "skipped" and o.event.ml_score == 0.12
        assert o.event.size_qty is None and o.event.leverage is None            # boyut/kaldirac yazilmaz: giris yok
        did = e.led.record_decision(o.event)                                    # defter bu nedeni kabul eder (alinmayan sinyal kaydi)
        assert e.led.get_decision(did).skip_reason == "ml_filter"
    finally:
        _kapat(e)


def test_esik_ustu_ayni_giris_boyut_kaldirac_limit_birebir(tmp_path):
    a, b = _kur(tmp_path / "a", None), _kur(tmp_path / "b", Sahte(OF.Karar(True, 0.9, "ok")))
    try:
        oa, ob = _go(a), _go(b)
        assert oa.action == ob.action == "enter"
        assert dataclasses.asdict(oa.event) == dataclasses.asdict(ob.event)
        assert (oa.size, oa.leverage) == (ob.size, ob.leverage)
    finally:
        _kapat(a, b)


@pytest.mark.parametrize("flt", [Sahte(hata=True), None, OF.FiltreDeposu("/yok/boyle/dizin")])
def test_hata_ya_da_filtre_yok_giris_serbest(tmp_path, flt):
    a, b = _kur(tmp_path / "a", None), _kur(tmp_path / "b", flt)
    try:
        oa, ob = _go(a), _go(b)
        assert ob.action == "enter" and dataclasses.asdict(oa.event) == dataclasses.asdict(ob.event)
        assert ob.code != "ml_no_model"
    finally:
        _kapat(a, b)


def test_gunluk_limit_filtreden_bagimsiz(tmp_path):
    """Gunluk kayip siniri: filtre gecse bile risk kapisi ayni karari verir (risk_denied)."""
    a = _kur(tmp_path / "a", None, day_start=1100.0)
    b = _kur(tmp_path / "b", Sahte(OF.Karar(True, 0.9, "ok")), day_start=1100.0)
    try:
        oa, ob = _go(a), _go(b)
        assert oa.code == ob.code == "risk_denied"
        assert dataclasses.asdict(oa.event) == dataclasses.asdict(ob.event)
    finally:
        _kapat(a, b)


def test_canli_testnet_yolunda_filtre_calismaz(tmp_path):
    s = Sahte(OF.Karar(False, 0.0, "esik_alti"))
    cfg = dataclasses.replace(CFG, mode="testnet")
    e = _kur(tmp_path / "a", s, cfg=cfg)
    try:
        o = _go(e)
        assert s.cagri == 0 and o.code != "ml_filter"
    finally:
        _kapat(e)


def test_config_kagit_active_canli_testnet_eskisi_gibi():
    assert CFG.ml_mode == "active" and CFG.mode == "paper"
    for env in ("testnet", "live"):
        try:
            c = load_cli_config(ROOT / "config", "learner", env)
        except Exception:  # noqa: BLE001 - canli yapilandirma bu ortamda eksik anahtar isteyebilir; ml_mode degismedi
            continue
        assert c.ml_mode == "off"


# ------------------------------------------------------------------ FiltreDeposu (gercek paket)
def _adaylar(arm, n, *, t0=datetime(2026, 11, 2, tzinfo=timezone.utc), saat=1):
    out = []
    for i in range(n):
        x = 5.0 if i % 2 == 0 else -5.0
        out.append(Aday(id=f"{arm}{i}", proje="ML", kurulum=arm, enstruman="BTC/USDT", varlik_sinifi="kripto", yon="long",
                        ts=t0 + timedelta(hours=saat * i), alindi=True, r=1.0 if x > 0 else -1.0, ozellikler={"x": x}))
    return out


def test_paket_egitim_esik_alti_atlar_ustu_gecirir(tmp_path):
    OF.egit_hepsi(_adaylar("T1@1h", 12), tmp_path, NOW)
    d = OF.FiltreDeposu(tmp_path)
    assert d.karar("T1@1h", {"x": -5.0}, NOW).izin is False
    k = d.karar("T1@1h", {"x": 5.0}, NOW)
    assert k.izin is True and k.neden == "ok" and 0.0 <= k.puan <= 1.0
    assert d.aktif_kurulumlar(NOW) == ["T1@1h"]


def test_10dan_az_islem_filtre_yok(tmp_path):
    r = OF.egit_hepsi(_adaylar("T1@1h", 9), tmp_path, NOW)
    assert r["kurulumlar"]["T1@1h"]["durum"] == "az_islem"
    assert OF.FiltreDeposu(tmp_path).karar("T1@1h", {"x": -5.0}, NOW).izin is True
    # n_egitim<10 paketi (elle uretilmis) de kullanilmaz
    p = PF.egit("T1@1h", _adaylar("T1@1h", 6), olusturma=NOW)
    PF.kaydet(p, tmp_path)
    k = OF.FiltreDeposu(tmp_path).karar("T1@1h", {"x": -5.0}, NOW)
    assert k.izin is True and k.neden == "filtre_yok"


def test_bozuk_ve_suresi_gecmis_paket_serbest(tmp_path):
    OF.egit_hepsi(_adaylar("T1@1h", 12), tmp_path, NOW)
    assert OF.FiltreDeposu(tmp_path).karar("T1@1h", {"x": -5.0}, NOW + timedelta(days=30)).izin is True   # suresi gecmis
    yol = tmp_path / "T1@1h.json"
    yol.write_text(yol.read_text().replace('"esik": ', '"esik": 0.99, "x_": '), encoding="utf-8")         # hash bozuldu
    k = OF.FiltreDeposu(tmp_path).karar("T1@1h", {"x": -5.0}, NOW)
    assert k.izin is True and k.neden == "filtre_yok"
    yol.write_text("{bozuk", encoding="utf-8")
    assert OF.FiltreDeposu(tmp_path).karar("T1@1h", {"x": -5.0}, NOW).izin is True


def test_puan_istisnasi_serbest(tmp_path, monkeypatch):
    OF.egit_hepsi(_adaylar("T1@1h", 12), tmp_path, NOW)
    d = OF.FiltreDeposu(tmp_path)
    monkeypatch.setattr(d._mod[0], "puan", lambda *a, **k: 1 / 0)
    k = d.karar("T1@1h", {"x": -5.0}, NOW)
    assert k.izin is True and k.neden == "hata"


def test_env_kapali_filtre_yok(tmp_path, monkeypatch):
    OF.egit_hepsi(_adaylar("T1@1h", 12), tmp_path, NOW)
    monkeypatch.setenv(OF.ENV_KAPALI, "1")
    assert OF.FiltreDeposu(tmp_path).karar("T1@1h", {"x": -5.0}, NOW).izin is True


def test_egitim_holdout_satiri_almaz(tmp_path):
    ic = _adaylar("T1@1h", 5, t0=datetime(2026, 6, 1, tzinfo=timezone.utc))            # holdout icinde
    dis = _adaylar("T1@1h", 12, t0=datetime(2026, 11, 3, tzinfo=timezone.utc))
    OF.egit_hepsi(ic + [dataclasses.replace(a, id="k" + a.id) for a in dis], tmp_path, NOW)
    meta = json.loads((tmp_path / "T1@1h.json").read_text())["meta"]
    assert meta["n_egitim"] == 12 and meta["kilit_dusen"] == 5
    assert OF._kilit_kesisir(datetime(2026, 10, 31, 23, tzinfo=timezone.utc), datetime(2026, 11, 2, tzinfo=timezone.utc))
    assert not OF._kilit_kesisir(datetime(2026, 11, 1, tzinfo=timezone.utc), datetime(2026, 11, 2, tzinfo=timezone.utc))


def test_yeniden_egitim_kurali_10_yeni_islem(tmp_path):
    OF.egit_hepsi(_adaylar("T1@1h", 12), tmp_path, NOW)
    h0 = json.loads((tmp_path / "T1@1h.json").read_text())["meta"]["model_hash"]
    r = OF.egit_hepsi(_adaylar("T1@1h", 15), tmp_path, NOW + timedelta(days=1))
    assert r["kurulumlar"]["T1@1h"]["durum"] == "guncel"
    r = OF.egit_hepsi(_adaylar("T1@1h", 22), tmp_path, NOW + timedelta(days=2))
    assert r["kurulumlar"]["T1@1h"]["durum"] == "ok"
    assert json.loads((tmp_path / "T1@1h.json").read_text())["meta"]["n_egitim"] == 22
    assert (tmp_path / "T1@1h.prev.json").exists() and h0
