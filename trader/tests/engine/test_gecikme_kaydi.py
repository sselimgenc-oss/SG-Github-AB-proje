"""Kagit: sinyal -> dolum SURE gecikmesi (`gecikme:<trade_id>` kv). Yalniz kayit; enjekte saat; defter semasi degismez."""
from __future__ import annotations

from datetime import timedelta

from test_engine_05_spec import BTC, H, T0, Env, flip_ctx
from test_wp3_engine_impl import _run_exit


def _lat(e, tid=1):
    return e.engine.state.kv_get(f"gecikme:{tid}")


def test_entry_latency_from_injected_clock(tmp_path):
    e = Env(tmp_path, shadow_blocks=[])
    e.start()
    try:
        e.open_pos(BTC, T0, entry=100.0, stop=98.0)
        lat = _lat(e)
        assert lat is not None
        v = lat["dolum_gecikme_sn"]
        assert isinstance(v, float) and v >= 0.0
        assert v == (e.clock.now() - T0).total_seconds() == 60.0          # dolum T0 mumunun adiminda islendi (enjekte saat T0+60 sn)
        assert "cikis_gecikme_sn" not in lat
    finally:
        e.close()


def test_exit_latency_recorded_for_decision_exit(tmp_path):
    e = Env(tmp_path, shadow_blocks=[])
    e.start()
    try:
        D2 = _run_exit(e)
        lat = _lat(e)
        assert lat["dolum_gecikme_sn"] >= 0.0
        assert lat["cikis_gecikme_sn"] == (e.clock.now() - D2).total_seconds() == 60.0
    finally:
        e.close()


def test_stop_fill_has_no_exit_latency(tmp_path):
    e = Env(tmp_path, shadow_blocks=[])
    e.start()
    try:
        e.open_pos(BTC, T0, entry=100.0, stop=98.0)
        e.step(T0 + timedelta(minutes=1), price=100.0, lo=90.0)
        e.engine._post_commit()
        assert "cikis_gecikme_sn" not in _lat(e)
    finally:
        e.close()


def test_latency_never_negative_and_missing_is_absent(tmp_path):
    e = Env(tmp_path, shadow_blocks=[])
    e.start()
    try:
        eng = e.engine
        now = eng.clock.now()
        assert eng._latency_sn(now + timedelta(hours=1)) == 0.0          # saat geri/ileri: asla negatif
        assert eng._latency_sn(now - timedelta(seconds=12.5)) == 12.5
        assert eng._latency_sn(None) is None and eng._latency_sn("x") is None
        with eng.state.tx():
            eng._store_latency(99, "dolum_gecikme_sn", None)
        assert eng.state.kv_get("gecikme:99") is None                    # eksik -> alan yok
    finally:
        e.close()
