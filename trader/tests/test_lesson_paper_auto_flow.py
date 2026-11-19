"""Ders Rev. 8 akis testleri (impl_smoke fiksturu): kagitta cikis kaniti onaysiz uygulanir, canlida sorulur; cooldown 0 / 28."""
from __future__ import annotations

from test_lesson_impl_smoke import RUN_NOW, env, mk_cfg, mk_service, r1_scenario  # noqa: F401

from trader_core import lesson as LS


def test_cooldown_zero_in_paper_28_in_live(env, tmp_path):
    r1_scenario(env)
    live, _ = mk_service(env, mk_cfg(tmp_path))
    paper, _ = mk_service(env, mk_cfg(tmp_path, paper_auto=True, exit_cf_reject_cooldown_days=0))
    assert live._exit_cooldown_days() == 28 and paper._exit_cooldown_days() == 0


def _force_exit_evidence(monkeypatch):
    monkeypatch.setattr(LS, "exit_cf_extra", lambda cf, mid: {"cf_exit_n": 40} if mid == "rr_min:up" else {})
    monkeypatch.setattr(LS, "build_exit_counterfactual", lambda cfg, as_of, path=None: {"available": True, "days": 120, "min_n": 30,
                                                                                         "weight": 0.5, "step": 0.5, "parity": {}, "by_alt": {}, "backtest": {}})


def test_exit_evidence_applied_without_approval_in_paper(env, tmp_path, monkeypatch):
    _force_exit_evidence(monkeypatch)
    r1_scenario(env)
    svc, store = mk_service(env, mk_cfg(tmp_path, paper_start_day="2026-10-01", paper_auto=True))
    assert svc.run_tick(RUN_NOW).status == "applied"
    assert store.open_requests() == []                                    # onay istegi yok
    store.close()


def test_exit_evidence_still_asks_in_live(env, tmp_path, monkeypatch):
    _force_exit_evidence(monkeypatch)
    r1_scenario(env)
    svc, store = mk_service(env, mk_cfg(tmp_path, paper_start_day="2026-10-01"))
    assert svc.run_tick(RUN_NOW).status == "needs_user"
    assert len(store.open_requests()) == 1
    store.close()
