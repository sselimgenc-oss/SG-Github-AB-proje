"""6c: etkin yapilandirma hash'i (ayar_surumu): kararli, degisiklikte degisir, kararin features'inda ve status'ta."""
from __future__ import annotations

from pathlib import Path

from trader_core import giris_izi as GI
from trader_engine.config import apply_overrides, load_engine_config

CFG = Path(__file__).resolve().parents[2] / "config"


def _c(**kw):
    return apply_overrides(load_engine_config(CFG / "engine.base.json", CFG / "engine.learner.json"), **kw)


def test_hash_kararli_ve_degisiklige_duyarli():
    a, b = _c(), _c()
    assert GI.ayar_sha256(a) == GI.ayar_sha256(b) and len(GI.ayar_sha256(a)) == 64
    assert GI.ayar_kisa(a) == GI.ayar_sha256(a)[:12]
    assert GI.ayar_sha256(_c(leverage=4)) != GI.ayar_sha256(a)


def test_karar_features_ve_status_icinde(monkeypatch):
    import datetime as dt
    from trader_engine import gates
    from trader_engine.strategy_runner import SignalRow
    import dataclasses
    fields = {f.name for f in dataclasses.fields(SignalRow)}
    assert "param_version_id" in fields
    # build_decision_event: hash verilirse features'a girer, verilmezse girmez
    class R:                                                    # SignalRow'un kullanilan alanlari
        regime = "trend"; setup = "T1"; side = "long"; pair = "BTC/USDT"; atr_ratio = 1.0; rh = None; rl = None
        rh_touches = 0; rl_touches = 0; planned_entry = 100.0; planned_stop = 99.0; planned_target = None
        param_version_id = 1; ml_score = None; arm_id = None; atr_tf = 1.0; stop_dist_atr = 1.0; atr_4h = 1.0
        bar_close_ts = dt.datetime(2026, 1, 1, tzinfo=dt.timezone.utc)
    monkeypatch.setattr(gates, "_features", lambda row: {"atr_tf": 1.0, "stop_dist_atr": 1.0, "atr_4h": 1.0})
    ev = gates.build_decision_event(R(), "1h", ayar_surumu="abc123def456")
    assert ev.features["ayar_surumu"] == "abc123def456"
    assert "ayar_surumu" not in gates.build_decision_event(R(), "1h").features
