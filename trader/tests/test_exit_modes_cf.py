"""docs/cikis-kipleri-spec.md 6: karsi-olgu gece isine cikis kipleri (exitcf-v2). Sentetik, elle hesapli yollar; kilitli donem disi."""
from __future__ import annotations

import csv
import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from exit_cf_support import HR, M15, NOW_MS, T0, T0_MS, FakeMarket, build, hour_to_15m, trade
from trader_core import exit_counterfactual as EC
from trader_core import exit_modes as XM

NOW = datetime(2025, 6, 1, tzinfo=timezone.utc)
COST = {"taker_fee": 0.0, "slip_exit_bps": 0.0, "slip_stop_bps": 0.0}
BE = XM.from_flags(True, False)
PT = XM.from_flags(False, True)
ROOT = Path(__file__).resolve().parents[1]


def replay(side, hours, *, trail=3.0, entry=100.0, stop=98.0, atr=2.0, modes=None, slip_exit=0.0, regime="trend_up"):
    h1, m15 = build(hours, atr=atr, regime=regime)
    return EC.replay_trail(side=side, entry_price=entry, initial_stop=stop, entry_ms=T0_MS, trail_atr=trail, h1=h1, m15=m15,
                           now_ms=NOW_MS, slip_exit_bps=slip_exit, slip_stop_bps=0.0, modes=modes)


def net(res, **kw):
    return EC.price_result(res, trade(**kw), taker_fee=0.0, funding_of=lambda a, b: (0.0, None))


# atr=2, trail=3: iz stopu (zirve-6) ilk stopun altinda kalir -> iz kurulmaz; fark yalniz kiplerden gelir
LONG = [(100, 103, 100.5, 102.5), (102.5, 103, 99, 99.5), (99.5, 99.5, 90, 90)]     # 3. saat: ilk stopu (98) vurur


def test_off_is_identical_to_default_and_none():
    a = replay("long", LONG)
    b = replay("long", LONG, modes=None)
    assert (a.reason, a.exit_price, a.exit_ms, a.partial_ms) == (b.reason, b.exit_price, b.exit_ms, None)
    assert a.reason == "stop" and a.exit_price == 98.0


def test_breakeven_exits_at_entry_plus_cost_when_price_returns():
    off = replay("long", LONG)
    on = replay("long", LONG, modes=BE)
    assert off.reason == "stop" and off.exit_price == 98.0                      # kipsiz: 3. saatte ilk stopta -1 R
    assert on.reason == "trail_stop" and on.exit_price == pytest.approx(100.0 * 1.0015)
    assert on.exit_ms == T0_MS + HR + 2 * M15                                   # dip 3. 15 dk mumunda; acilis stopun uzerinde
    assert net(on)["net_r"] == pytest.approx(0.15 / 2)                          # (100,15 - 100) / R=2
    assert on.partial_ms is None


def test_breakeven_not_reached_below_1r():
    hours = [(100, 101.9, 100.5, 101.0), (101.0, 101.5, 99, 99.5), (99.5, 99.5, 99.5, 99.5)]
    assert replay("long", hours, modes=BE).exit_price == replay("long", hours).exit_price


def test_breakeven_short_mirror():
    hours = [(100, 99.5, 97, 97.5), (97.5, 100, 97.4, 99.9), (99.9, 104, 99.9, 104)]
    r = replay("short", hours, stop=102.0, modes=BE, regime="trend_down")
    assert r.reason == "trail_stop" and r.exit_price == pytest.approx(100.0 * (1 - 0.0015))
    off = replay("short", hours, stop=102.0, regime="trend_down")
    assert off.reason == "stop" and off.exit_price == 102.0


def test_partial_takes_fraction_at_next_open_then_remainder_stops():
    hours = [(100, 103, 100.5, 102.5), (102.5, 103, 97, 97.5), (97.5, 97.5, 97.5, 97.5)]
    r = replay("long", hours, modes=PT)
    assert (r.partial_ms, r.partial_price, r.partial_frac) == (T0_MS + HR, 102.5, 0.5)      # D_0'dan sonraki ilk acilis
    assert r.reason == "stop" and r.exit_price == 98.0
    # elle: 0,5*(102,5-100) + 0,5*(98-100) = 0,25 R'nin 2 katı brut; R=2, adet 1
    assert net(r)["net_r"] == pytest.approx((0.5 * 2.5 + 0.5 * -2.0) / 2)
    assert net(r)["gross_r"] == pytest.approx(0.125)
    assert replay("long", hours).exit_price == 98.0 and replay("long", hours).partial_ms is None


def test_partial_not_triggered_below_threshold_and_not_after_exit_decision():
    hours = [(100, 102.9, 100.5, 102.0), (102.0, 102.9, 97, 97.5)]
    assert replay("long", hours, modes=PT).partial_ms is None                   # 1,45 R < 1,5 R
    flip = replay("long", [(100, 103, 100.5, 102.5), (102.5, 103, 102, 102.5)], modes=PT, regime="trend_down")
    assert flip.reason == "regime_flip" and flip.partial_ms is None             # cikis karari verilmisse kismi yok


def test_partial_fee_and_funding_split_by_quantity():
    hours = [(100, 103, 100.5, 102.5), (102.5, 103, 97, 97.5), (97.5, 97.5, 97.5, 97.5)]
    r = replay("long", hours, modes=PT)
    tr = trade(qty=2.0, planned_risk=4.0, fee_entry=0.0)
    out = EC.price_result(r, tr, taker_fee=0.001, funding_of=lambda a, b: (float(b - a) / HR, None))
    assert out["fee_r"] == pytest.approx(2.0 * (0.5 * 102.5 + 0.5 * 98.0) * 0.001 / 4.0)
    # partial_ms = entry+1h (1 birim), exit = entry+1h+30dk (1,5 birim): 0,5*1 + 0,5*1,5
    assert out["funding_r"] == pytest.approx((0.5 * 1.0 + 0.5 * 1.5) / 4.0)


def test_modes_use_engine_functions_not_copies():
    src = (ROOT / "src" / "trader_core" / "exit_counterfactual.py").read_text(encoding="utf-8")
    assert "XM.be_stop(" in src and "XM.partial_due(" in src and "XM.merge_stop(" in src
    pm = (ROOT / "src" / "trader_engine" / "position_manager.py").read_text(encoding="utf-8")
    assert "_xm.be_stop(" in pm and "_xm.partial_due(" in pm


# ----------------------------------------------------------------------------------------------- gece isi
@pytest.fixture(autouse=True)
def fake_prepare(monkeypatch):
    def fake(h1_rows, h4_rows, signal_params=None):
        return EC.H1Series([r[0] for r in h1_rows], [r[1] for r in h1_rows], [r[2] for r in h1_rows], [r[3] for r in h1_rows],
                           [r[4] for r in h1_rows], [2.0] * len(h1_rows), ["trend_up"] * len(h1_rows))
    monkeypatch.setattr(EC, "prepare_h1", fake)


def market(hours=LONG, start_ms=T0_MS):
    h1, m15 = build(hours, start_ms=start_ms, atr=2.0)
    h1r = [(m, h1.o[i], h1.h[i], h1.l[i], h1.c[i]) for i, m in enumerate(h1.ms)]
    m15r = sorted((k, *v) for k, v in m15.items())
    h4 = [(start_ms - (i + 1) * EC.H4_MS, 100.0, 101.0, 99.0, 100.0) for i in range(130)][::-1]
    return FakeMarket(h1r, m15r, h4, [])


def go(tmp_path, trades, mk, **kw):
    with EC.ExitCfStore(tmp_path / "x.sqlite") as st:
        return EC.run_modes_once(bot="learner", trades=trades, market=mk, store=st, now=NOW, active_value=3.0,
                                 cost_for=lambda t: COST, **kw)


def mrows(tmp_path):
    c = sqlite3.connect(tmp_path / "x.sqlite")
    c.row_factory = sqlite3.Row
    try:
        return [dict(r) for r in c.execute("SELECT * FROM ecf_modes ORDER BY trade_id, variant")]
    finally:
        c.close()


def test_run_modes_writes_three_variants_idempotently_and_deltas(tmp_path):
    tr = trade(actual_net_r=0.0)
    r1 = go(tmp_path, [tr], market())
    assert (r1.scanned, r1.computed, r1.rows_written, r1.already) == (1, 1, 3, 0)
    rs = mrows(tmp_path)
    assert [x["variant"] for x in rs] == ["breakeven", "off", "partial"]
    assert all(x["registry_id"] == "exitcf-v2" and x["version"] == EC.MODES_VERSION and x["trail_atr"] == 3.0 and x["grid_min"] == 15 for x in rs)
    by = {x["variant"]: x for x in rs}
    assert by["breakeven"]["net_r"] == pytest.approx(0.075) and by["breakeven"]["exit_reason_sim"] == "trail_stop"
    assert by["off"]["exit_reason_sim"] == "stop" and by["off"]["censored"] == 0 and by["off"]["net_r"] == pytest.approx(-1.0)
    assert by["partial"]["partial_ts_sim"] is not None and by["breakeven"]["partial_ts_sim"] is None
    r2 = go(tmp_path, [tr], market())
    assert (r2.already, r2.computed, r2.rows_written) == (1, 0, 0) and mrows(tmp_path) == rs
    d_be = EC.deltas_modes(tmp_path / "x.sqlite", "learner", now=NOW + timedelta(days=1), days=2000, mode="breakeven")
    assert len(d_be) == 1 and d_be[0]["delta_r"] == pytest.approx(by["breakeven"]["net_r"] - by["off"]["net_r"])
    assert d_be[0]["delta_r"] == pytest.approx(1.075) and d_be[0]["censored"] == 0 and d_be[0]["partial_fired"] == 0
    d_pt = EC.deltas_modes(tmp_path / "x.sqlite", "learner", now=NOW + timedelta(days=1), days=2000, mode="partial")
    assert d_pt[0]["partial_fired"] == 1
    with pytest.raises(EC.ExitCfError):
        EC.deltas_modes(tmp_path / "x.sqlite", "learner", now=NOW, mode="nope")


def test_deltas_modes_empty_when_table_or_file_missing(tmp_path):
    p = tmp_path / "old.sqlite"
    c = sqlite3.connect(p)
    c.executescript("PRAGMA user_version=1; CREATE TABLE meta(key TEXT PRIMARY KEY, value TEXT NOT NULL);"
                    "CREATE TABLE ecf_outcomes(bot TEXT);")
    c.commit()
    c.close()
    assert EC.deltas_modes(p, "learner", now=NOW, mode="partial") == []          # v1-only depo: kanit yok, hata yok
    with pytest.raises(EC.ExitCfError):
        EC.deltas_modes(tmp_path / "yok.sqlite", "learner", now=NOW, mode="partial")


def test_v1_rows_unchanged_by_modes_pass(tmp_path):
    """v1 tablosu ve satirlari modes gecisinden etkilenmez; kipsiz own_modes ile v1 oynatimi eski sonucla ayni."""
    tr = trade(own_value=3.0, actual_net_r=0.0)
    with EC.ExitCfStore(tmp_path / "x.sqlite") as st:
        EC.run_once(bot="learner", trades=[tr], market=market(), store=st, now=NOW, active_value=3.0, step=0.5,
                    bounds=(2.5, 3.5), cost_for=lambda t: COST)
    c = sqlite3.connect(tmp_path / "x.sqlite")
    before = c.execute("SELECT * FROM ecf_outcomes ORDER BY value").fetchall()
    c.close()
    go(tmp_path, [tr], market())
    c = sqlite3.connect(tmp_path / "x.sqlite")
    assert c.execute("SELECT * FROM ecf_outcomes ORDER BY value").fetchall() == before
    c.close()


def test_own_modes_make_v1_replay_follow_the_trade(tmp_path):
    """Kipli surumde kapanan islemin v1 oynatimi (parite) kendi kipleriyle yapilir."""
    tr = trade(own_value=3.0, own_modes=BE, actual_net_r=0.075)
    with EC.ExitCfStore(tmp_path / "x.sqlite") as st:
        EC.run_once(bot="learner", trades=[tr], market=market(), store=st, now=NOW, active_value=3.0, step=0.5,
                    bounds=(2.5, 3.5), cost_for=lambda t: COST)
    c = sqlite3.connect(tmp_path / "x.sqlite")
    c.row_factory = sqlite3.Row
    base = c.execute("SELECT * FROM ecf_outcomes WHERE role='base'").fetchone()
    c.close()
    assert base["net_r"] == pytest.approx(0.075) and base["parity_gap_r"] == pytest.approx(0.0)


def test_holdout_and_15m_and_excluded_reasons_skipped(tmp_path):
    hold = (datetime(2025, 1, 1, tzinfo=timezone.utc), datetime(2025, 2, 1, tzinfo=timezone.utc))
    mk = market()
    r = go(tmp_path, [trade(trade_id=1), trade(trade_id=2, trigger_tf="15m"), trade(trade_id=3, exit_reason="manual")], mk,
           holdout=hold)
    assert (r.holdout_skipped, r.skipped_15m, r.excluded_exit_reason, r.rows_written) == (1, 1, 1, 0)
    assert not [c for c in mk.calls if c[0] != "funding"]                         # kilitli pencere hic okunmadi


def test_modes_registry_row_and_csv():
    row = EC.modes_registry_row()
    assert row["id"] == "exitcf-v2" and row["n_trials"] == 2 and row["version"] == EC.MODES_VERSION
    assert EC.REGISTRY_ID == "exitcf-v1" and EC.VERSION == 1                       # v1 sabitleri degismez
    rows = list(csv.DictReader((ROOT / "research" / "trial_registry.csv").open(newline="", encoding="utf-8")))
    mine = [r for r in rows if r["id"].startswith("exitcf-v2")]
    assert mine and "kilitli" in mine[0]["notes"] and "n_trials" in mine[0]["notes"]
    assert any(r["id"].startswith("exitcf-v1") for r in rows)
    assert EC.registry_check(ROOT / "research" / "trial_registry.csv", "exitcf-v2") == (True, "ok")
    assert EC.registry_check(ROOT / "research" / "trial_registry.csv") == (True, "ok")
