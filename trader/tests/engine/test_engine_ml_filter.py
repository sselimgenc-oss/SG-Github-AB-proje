"""19a / 19d: `price_action_v1_ml` (ML filtresi, yalniz kaldirir) + motor baglam alani + `ml_filter` defter nedeni.

Kapsam: off modu v1b ile BIREBIR ayni karar akisi; shadow kararlari degistirmez (yalniz ml_score yazar); active esik altini
`skip_reason=ml_filter` ile eler, fail-closed (model yok / suresi dolmus / puanlanamamis => yeni giris yok); model yukleme
kurallari (gate_passed, hash, 21 gun, ozellik listesi, active icin kullanici onayi); ctx.model salt okunur; yapilandirma."""
from __future__ import annotations

import dataclasses
import functools
import json
import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from trader_core import ledger as L
from trader_core import risk as K
from trader_core import signals as S
from trader_core.ml_features import FEATURE_NAMES
from trader_core.ml_package import (MODEL_EXPIRY_DAYS, PackageError, canon, feature_list_hash, load_model_view,
                                    load_package, sha256_text, view_from_package)
from trader_engine.brokers.paper import PaperBroker, PaperConfig
from trader_engine.clock import SimClock
from trader_engine.config import ConfigError, apply_overrides, load_engine_config
from trader_engine.engine import Engine
from trader_engine.gates import NoVeto
from trader_engine.killswitch import Killswitch
from trader_engine.state import StateStore
from trader_engine.status import StatusWriter
from trader_engine.strategies.base import StrategyContext, StrategyError
from trader_engine.strategies.price_action_v1_ml import load_engine_model, make_v1b_ml
from trader_engine.strategies.registry import get_strategy
from trader_engine.strategy_runner import WindowedSignalSource, ml_score_from_reasons

ROOT = Path(__file__).resolve().parents[2]
DATA = ROOT / "var" / "history"
UTC = timezone.utc
needs_data = pytest.mark.skipif(not DATA.exists(), reason="var/history yok")
START, END = datetime(2026, 3, 1, tzinfo=UTC), datetime(2026, 3, 11, tzinfo=UTC)
END_SHORT = datetime(2026, 3, 8, tzinfo=UTC)
PAIRS = ["BTC/USDT", "ETH/USDT", "SOL/USDT"]


# ------------------------------------------------------------------------------------------------ model yapisi
def make_pkg(*, intercept=0.0, coef_atr=0.0, threshold=0.5, created=None, gate=True, approved=True, features=None,
             expires=None):
    names = list(features or FEATURE_NAMES)
    n = len(names)
    coef = [0.0] * n
    if "f_atr_ratio" in names:
        coef[names.index("f_atr_ratio")] = coef_atr
    model = {"kind": "logistic", "n_features": n, "coef": coef, "intercept": intercept,
             "mean": [0.0] * n, "std": [1.0] * n, "fill": [0.0] * n}
    cal = {"a": 1.0, "b": 0.0}
    body = {"model": model, "calibration": cal, "threshold": threshold}
    created = created or datetime(2026, 3, 1, tzinfo=UTC)
    meta = {"version": "test", "created_at": created.isoformat(),
            "expires_at": (expires or created + timedelta(days=MODEL_EXPIRY_DAYS)).isoformat(),
            "features": names, "feature_list_hash": feature_list_hash(names), "model_hash": sha256_text(canon(body))}
    if gate is not None:
        meta["gate_passed"] = gate
    if approved:
        meta["user_approved"] = True
    return {"meta": meta, **body}


NOW = datetime(2026, 3, 5, tzinfo=UTC)


# ------------------------------------------------------------------------------------------------ model yukleme (motor)
class TestModelLoading:
    def test_ok(self):
        v = load_model_view(make_pkg(), expected_features=FEATURE_NAMES, ml_mode="active", now=NOW)
        assert v.threshold == 0.5 and v.features == tuple(FEATURE_NAMES) and v.user_approved
        assert v.expired(NOW + timedelta(days=17)) and not v.expired(NOW)
        assert float(v.score(np.zeros((1, len(FEATURE_NAMES))))[0]) == pytest.approx(0.5)

    @pytest.mark.parametrize("gate", [False, None, "yes", 1])
    def test_refuses_gate_not_true(self, gate):
        with pytest.raises(PackageError, match="kapidan"):
            load_model_view(make_pkg(gate=gate), expected_features=FEATURE_NAMES, ml_mode="shadow", now=NOW)
        with pytest.raises(PackageError):
            load_package(make_pkg(gate=gate), now=NOW)

    def test_refuses_expired_21_days(self):
        pkg = make_pkg(created=datetime(2026, 2, 1, tzinfo=UTC))
        with pytest.raises(PackageError, match="suresi"):
            load_model_view(pkg, expected_features=FEATURE_NAMES, ml_mode="shadow", now=datetime(2026, 2, 23, tzinfo=UTC))
        load_model_view(pkg, expected_features=FEATURE_NAMES, ml_mode="shadow", now=datetime(2026, 2, 21, tzinfo=UTC))

    def test_extended_expires_at_cannot_dodge_21_days(self):
        pkg = make_pkg(created=datetime(2026, 2, 1, tzinfo=UTC), expires=datetime(2027, 2, 1, tzinfo=UTC))
        with pytest.raises(PackageError, match="suresi"):
            load_model_view(pkg, expected_features=FEATURE_NAMES, ml_mode="shadow", now=datetime(2026, 2, 25, tzinfo=UTC))

    def test_refuses_tampered_hash_and_feature_mismatch_and_no_threshold(self):
        pkg = make_pkg()
        pkg["threshold"] = 0.1
        with pytest.raises(PackageError, match="hash"):
            load_model_view(pkg, expected_features=FEATURE_NAMES, ml_mode="shadow", now=NOW)
        with pytest.raises(PackageError, match="ozellik"):
            load_model_view(make_pkg(features=FEATURE_NAMES[:-1]), expected_features=FEATURE_NAMES, ml_mode="shadow", now=NOW)
        with pytest.raises(PackageError, match="esigi"):
            load_model_view(make_pkg(threshold=None), expected_features=FEATURE_NAMES, ml_mode="shadow", now=NOW)

    def test_active_needs_user_approval_shadow_does_not(self):
        pkg = make_pkg(approved=False)
        load_model_view(pkg, expected_features=FEATURE_NAMES, ml_mode="shadow", now=NOW)
        with pytest.raises(PackageError, match="onay"):
            load_model_view(pkg, expected_features=FEATURE_NAMES, ml_mode="active", now=NOW)

    def test_load_engine_model_returns_error_codes_not_exceptions(self, tmp_path):
        assert load_engine_model(None, "active", NOW) == (None, "ml_model_path_missing")
        assert load_engine_model(str(tmp_path / "yok.json"), "shadow", NOW)[0] is None
        bad = tmp_path / "bad.json"
        bad.write_text("{not json")
        assert load_engine_model(str(bad), "shadow", NOW)[0] is None
        ok = tmp_path / "ok.json"
        ok.write_text(json.dumps(make_pkg()))
        v, err = load_engine_model(str(ok), "active", NOW)
        assert err is None and v is not None
        g = tmp_path / "g.json"
        g.write_text(json.dumps(make_pkg(gate=False)))
        v, err = load_engine_model(str(g), "shadow", NOW)
        assert v is None and "kapidan" in err


# ------------------------------------------------------------------------------------------------ sozlesme: ctx.model, kayit, config
def test_strategy_context_model_field_is_optional_and_readonly():
    ctx = StrategyContext(pair="BTC/USDT", D=NOW, tf="1h", params={}, bars={})
    assert ctx.model is None
    with pytest.raises(dataclasses.FrozenInstanceError):
        ctx.model = object()                                   # type: ignore[misc]
    v = view_from_package(make_pkg())
    with pytest.raises(dataclasses.FrozenInstanceError):
        v.threshold = 0.0                                      # type: ignore[misc]
    assert dataclasses.replace(ctx, model=v).model is v


def test_registry_ml_strategy_and_mode_plumbing():
    s = get_strategy("price_action_v1_ml", mode="paper")
    assert (s.info.name, s.info.version, s.info.setups, s.info.paper_allowed) == ("price_action_v1_ml", "1b.0-ml0", ("T1",), True)
    assert s.ml_mode == "off"                                   # varsayilan OFF
    v1 = get_strategy("price_action_v1")
    assert s.info.param_specs == v1.info.param_specs and s.info.window_bars == v1.info.window_bars
    assert get_strategy("price_action_v1_ml", ml_mode="shadow").ml_mode == "shadow"
    with pytest.raises(StrategyError) as e:
        get_strategy("price_action_v1_ml", ml_mode="turbo")
    assert e.value.code == "bad_ml_mode"
    with pytest.raises(StrategyError) as e:                    # ML'siz strateji ML modu almaz
        get_strategy("price_action_v1", ml_mode="shadow")
    assert e.value.code == "ml_not_supported"
    assert get_strategy("price_action_v1", ml_mode="off").info.name == "price_action_v1"


def test_configs_ship_ml_mode_off_and_validation():
    for name in ("engine.base.json", "engine.learner.json"):
        raw = json.loads((ROOT / "config" / name).read_text())
        if name == "engine.base.json":
            assert raw["ml_mode"] == "off" and raw["ml_model_path"] is None
        else:
            assert raw.get("ml_mode", "off") == "off"
    for bot in ("learner",):
        cfg = load_engine_config(ROOT / "config" / "engine.base.json", ROOT / "config" / f"engine.{bot}.json")
        assert cfg.ml_mode == "off" and cfg.ml_model_path is None and cfg.strategy == "price_action_v1"
    assert apply_overrides(cfg, ml_mode="shadow", ml_model_path="m.json").ml_mode == "shadow"
    with pytest.raises(ConfigError):
        apply_overrides(cfg, ml_mode="on")
    with pytest.raises(ConfigError):
        apply_overrides(cfg, ml_model_path="")


def test_reasons_tag_parser():
    assert ml_score_from_reasons("ml:p=0.412300|v1b:x|") == pytest.approx(0.4123)
    assert ml_score_from_reasons("ml:filter|ml:p=0.100000|T1") == pytest.approx(0.1)
    assert ml_score_from_reasons("ml:p=1.500000|") is None
    assert ml_score_from_reasons("v1b:same_bar_reentry|") is None and ml_score_from_reasons(None) is None


# ------------------------------------------------------------------------------------------------ uc uca (gercek veri)
def _params():
    return {k: getattr(S.DEFAULT_SIGNAL_PARAMS, k) for k in L.PARAM_KEYS}


class _CachedSource:
    def __new__(cls, *a, **k):
        from trader_engine.marketdata.sources import HistoricalSource
        v = HistoricalSource(*a, **k)
        v.rules = functools.lru_cache(maxsize=None)(v.rules)
        return v


def _engine(tmp, name, *, ml_mode="off", model=None, ml_error=None, view=None):
    cfg = load_engine_config(ROOT / "config" / "engine.base.json", ROOT / "config" / "engine.learner.json")
    cfg = apply_overrides(cfg, mode="backtest", pairs=PAIRS, var_dir=str(tmp), kill_file=str(tmp / "KILL"),
                          veto_mode="off", cost=dict(fill_model="native", granularity="15m", trigger_source="last"))
    clock = SimClock(START)
    view = view or _CachedSource(str(DATA), granularity="15m", synthetic_rules=True)
    broker = PaperBroker(PaperConfig(cost=cfg.cost, mmr=K.LOCKED_CFG.maint_margin_rate, wallet_start=cfg.wallet_start),
                         view.rules, view.funding, clock)
    led = L.open_ledger(str(tmp / "ledger.sqlite"), "learner", create=True, clock=clock.now)
    strat = get_strategy(name, ml_mode=ml_mode if name.endswith("_ml") else None)
    led.init_params(_params(), reason=f"strategy:{strat.info.name}@{strat.info.version} ml-test")
    state = StateStore(str(tmp / "state.sqlite"), bot="learner", durability="off")
    src = WindowedSignalSource(view, strat, strict=True, ml_model=model, ml_error=ml_error)
    eng = Engine(cfg, clock=clock, view=view, broker=broker, ledger=led, state=state, signals=src, strategy=strat,
                 veto=NoVeto(), kill=Killswitch(cfg.kill_file, clock), status=StatusWriter(cfg.status_path, clock, cfg),
                 strict=True)
    return eng, cfg


def _run(tmp, name, end=END, **kw):
    eng, cfg = _engine(tmp, name, **kw)
    eng.start()
    eng.run_range(START, end)
    return eng, cfg


def _rows(eng, drop=("id", "ml_score", "recorded_at")):
    path = eng.ledger.path if hasattr(eng.ledger, "path") else None
    con = sqlite3.connect(str(path))
    con.row_factory = sqlite3.Row
    try:
        rows = [dict(r) for r in con.execute("SELECT * FROM v_decisions ORDER BY bar_close_ts, pair, side, setup")]
        trades = [tuple(r) for r in con.execute(
            "SELECT pair, side, entry_ts, entry_price, qty, exit_ts, exit_price, exit_reason, r_multiple "
            "FROM v_trades ORDER BY entry_ts, pair")]
    finally:
        con.close()
    return [{k: v for k, v in r.items() if k not in drop} for r in rows], trades, rows


def _med_model(shadow_rows):
    ps = sorted(r["ml_score"] for r in shadow_rows if r["ml_score"] is not None)
    assert len(ps) >= 4, f"yeterli aday yok: {len(ps)}"
    return ps[len(ps) // 2]


@pytest.fixture(scope="module")
def runs(tmp_path_factory):
    """v1b, ml/off, ml/shadow (degisken puanli model), ml/active (medyan esik) ayni veri diliminde."""
    out = {}
    out["v1"] = _run(tmp_path_factory.mktemp("v1"), "price_action_v1")
    out["off"] = _run(tmp_path_factory.mktemp("off"), "price_action_v1_ml", ml_mode="off")
    # puan = sigmoid(f_atr_ratio - 1.0): atr_ratio adaylar arasinda degisir => puanlar degisken
    mk = lambda thr: view_from_package(make_pkg(intercept=-1.0, coef_atr=1.0, threshold=thr))
    sh = _run(tmp_path_factory.mktemp("shadow"), "price_action_v1_ml", ml_mode="shadow", model=mk(0.5))
    out["shadow"] = sh
    thr = _med_model(_rows(sh[0])[2])
    out["thr"] = thr
    out["active"] = _run(tmp_path_factory.mktemp("active"), "price_action_v1_ml", ml_mode="active", model=mk(thr))
    return out


@needs_data
def test_off_mode_decision_stream_is_byte_identical_to_v1b(runs):
    d1, t1, raw1 = _rows(runs["v1"][0], drop=("id",))
    d0, t0, raw0 = _rows(runs["off"][0], drop=("id",))
    assert len(d1) >= 5 and t1
    assert json.dumps(d1, sort_keys=True, default=str) == json.dumps(d0, sort_keys=True, default=str)
    assert t1 == t0
    assert all(r["ml_score"] is None for r in raw0)
    assert runs["off"][0].signals.ml_status(START)["state"] == "off"
    assert runs["v1"][0].signals.ml_status(START) is None


@needs_data
def test_shadow_never_changes_decisions_but_writes_scores(runs):
    d1, t1, _ = _rows(runs["v1"][0])
    ds, ts_, raw = _rows(runs["shadow"][0])
    assert d1 == ds and t1 == ts_                              # ml_score/id/recorded_at disinda birebir ayni
    entered = [r for r in raw if r["final_action"] == "entered"]
    assert entered and all(r["ml_score"] is not None and 0 <= r["ml_score"] <= 1 for r in entered)
    assert not any(r["skip_reason"] == "ml_filter" for r in raw)
    c = runs["shadow"][0].counters()
    assert c.get("ml_shadow_scored", 0) >= len(entered) and c.get("ml_no_model", 0) == 0


@needs_data
def test_active_filters_below_threshold_remove_only(runs):
    thr = runs["thr"]
    _, _, shadow = _rows(runs["shadow"][0])
    _, _, act = _rows(runs["active"][0])
    filt = [r for r in act if r["skip_reason"] == "ml_filter"]
    assert filt, "esik medyan: en az bir aday elenmeli"
    for r in filt:
        assert r["final_action"] == "skipped" and r["veto_status"] == "not_evaluated" and r["risk_allowed"] is None
        assert r["ml_score"] is not None and r["ml_score"] < thr
        assert r["size_qty"] is None and r["leverage"] is None
    entered = [r for r in act if r["final_action"] == "entered"]
    assert entered and all(r["ml_score"] is not None and r["ml_score"] >= thr for r in entered)
    # filtre aday EKLEMEZ ve fiyat/stop/hedef/boyut degistirmez: ayni (cift, mum) icin planlar shadow ile ayni
    sh = {(r["pair"], r["bar_close_ts"], r["side"]): r for r in shadow}
    same_keys = ("planned_entry", "planned_stop", "planned_target", "setup", "regime", "features")
    for r in act:
        k = (r["pair"], r["bar_close_ts"], r["side"])
        if k in sh:
            assert all(sh[k][c] == r[c] for c in same_keys), k
    assert runs["active"][0].counters()["ml_filter"] == len(filt)


@needs_data
def test_active_without_model_or_expired_or_error_opens_no_entries(tmp_path_factory):
    expired_view = view_from_package(make_pkg(threshold=0.0, created=datetime(2026, 2, 1, tzinfo=UTC)))  # 03/01'de dolmus
    cases = {"no_model": dict(model=None, ml_error="ml_model_path_missing"),
             "expired": dict(model=expired_view),
             "unscored": dict(model=view_from_package(make_pkg(threshold=0.0, features=None)))}
    for tag, kw in cases.items():
        eng, cfg = _engine(tmp_path_factory.mktemp(tag), "price_action_v1_ml", ml_mode="active", **kw)
        if tag == "unscored":
            object.__setattr__(kw["model"], "score", lambda X: np.full(len(X), np.nan))   # puanlama sonlu degil -> etiket yok
        eng.start()
        eng.run_range(START, END_SHORT)
        _, _, raw = _rows(eng)
        assert raw, tag
        assert not [r for r in raw if r["final_action"] == "entered"], tag
        assert [r for r in raw if r["skip_reason"] == "ml_filter"], tag
        assert eng.summary().trades_opened == 0
        assert eng.signals.ml_status(END)["entries_blocked"] is (tag in ("no_model", "expired"))
        eng.shutdown("test")
        status = json.loads(Path(cfg.status_path).read_text())
        assert status["ml"]["mode"] == "active"
        if tag != "unscored":
            assert status["ml"]["entries_blocked"] is True and status["entries_open"] is False
            assert status["gate"]["ok"] is False and status["gate"]["code"].startswith("ml_")
        assert eng.counters().get("ml_" + {"no_model": "no_model", "expired": "expired", "unscored": "unscored"}[tag], 0) > 0


@needs_data
def test_shadow_without_model_never_blocks_only_warns(tmp_path_factory):
    d1, t1, _ = _rows(_run(tmp_path_factory.mktemp("v1b"), "price_action_v1", end=END_SHORT)[0])
    eng, cfg = _run(tmp_path_factory.mktemp("shnm"), "price_action_v1_ml", end=END_SHORT, ml_mode="shadow", model=None,
                    ml_error="ml_model_path_missing")
    ds, ts_, raw = _rows(eng)
    assert ds == d1 and ts_ == t1 and all(r["ml_score"] is None for r in raw)
    assert eng.counters().get("ml_no_model", 0) > 0                       # yalniz uyari sayaci
    st = eng.signals.ml_status(END)
    assert st["state"] == "no_model" and st["entries_blocked"] is False and st["error"] == "ml_model_path_missing"
    eng.shutdown("test")
    status = json.loads(Path(cfg.status_path).read_text())
    assert status["entries_open"] is True and status["gate"]["code"] == "ok"
