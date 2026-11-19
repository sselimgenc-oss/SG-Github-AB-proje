"""Cikis karsi-olgusu: `trail_atr:up` kanit-yalniz girdisi icin ret sonrasi 28 gun bekleme (docs/cikis-karsi-olgu-spec.md 7.3)."""
from __future__ import annotations

from datetime import timedelta

from test_lesson_impl_smoke import RUN_NOW, env, mk_cfg, mk_service, r1_scenario  # noqa: F401
from trader_core import lesson as LS


def test_reject_cooldown_override_28_days_per_key(env, tmp_path, monkeypatch):
    # kagitta onay isteyen tek yol kanit-yalniz/cikis kanitli girdi: zorla cf_exit_n (needs_user), sonra kullanici reddi
    monkeypatch.setattr(LS, "exit_cf_extra", lambda cf, mid: {"cf_exit_n": 40} if mid == "rr_min:up" else {})
    monkeypatch.setattr(LS, "build_exit_counterfactual", lambda cfg, as_of, path=None: {"available": True, "days": 120, "min_n": 30,
                                                                                         "weight": 0.5, "step": 0.5, "parity": {}, "by_alt": {}, "backtest": {}})
    r1_scenario(env)
    cfg = mk_cfg(tmp_path, paper_start_day="2026-10-01")
    assert cfg.exit_cf_reject_cooldown_days == 28 and cfg.reject_cooldown_days == 7
    svc, store = mk_service(env, cfg)
    assert svc.run_tick(RUN_NOW).status == "needs_user"
    rid = store.open_requests()[0]["request_id"]
    assert svc.resolve_request(rid, False, "t").status == "rejected"
    base = store.rejection_cooldowns(7)[("rr_min", "up")]
    long = store.rejection_cooldowns(7, {("rr_min", "up"): 28})[("rr_min", "up")]
    assert LS.parse_ts(long) - LS.parse_ts(base) == timedelta(days=21)               # yalniz eslesen (param, yon) anahtari uzar
    assert store.rejection_cooldowns(7, {("trail_atr", "up"): 28})[("rr_min", "up")] == base
    assert store.rejection_cooldowns(0, {("trail_atr", "up"): 28}) == {}               # ret yoksa bekleme yok
    store.close()
