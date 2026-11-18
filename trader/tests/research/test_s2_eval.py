"""S2 0b: research/s2_eval.py ve research/s2_run.py (docs/ml/s2-on-kayit.md §2, §4; E-1..E-9).

Yalniz sentetik trades.csv; gercek veri / motor / research/trial_registry.csv kullanilmaz.
"""
from __future__ import annotations

import csv
import importlib.util
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from trader_core.stats import stats as core_stats
from trader_engine.metrics import loss_at_stop

ROOT = Path(__file__).resolve().parents[2]
RESEARCH = ROOT / "research"

FULL = ["2021-01-01T00:00:00.000Z", "2026-05-01T00:00:00.000Z"]
PAIRS = [f"P{i}/USDT:USDT" for i in range(10)]
CODES = ["K1-1a", "K1-1b", "K1-1c", "K1-1d", "K1-1e", "K1-1f", "K1-1g", "K1-2", "K1-3"]
COLUMNS = ("trade_id,pair,side,setup,regime,entry_ts,exit_ts,entry_price,exit_price,qty,leverage,planned_entry,"
           "planned_stop,planned_target,exit_reason,planned_exit,planned_risk,equity_at_entry,gross_pnl,fee_entry,"
           "fee_exit,funding_paid,realized_pnl,r_multiple,mfe_r,mae_r,bars_held,excursion_tf,slippage_entry,"
           "slippage_exit,slip_cost,decision_id,param_version_id").split(",")
WSTART = pd.Timestamp("2022-01-06T00:00:00Z")
WEND = pd.Timestamp("2026-05-01T00:00:00Z")
SLICES = ["2022-01-06", "2023-02-04", "2024-03-04", "2025-04-02", "2026-05-01"]


def _load(name: str):
    if str(RESEARCH) not in sys.path:
        sys.path.insert(0, str(RESEARCH))
    spec = importlib.util.spec_from_file_location(name, RESEARCH / f"{name}.py")
    m = importlib.util.module_from_spec(spec)
    sys.modules[name] = m
    spec.loader.exec_module(m)
    return m


@pytest.fixture(scope="module")
def ev():
    return _load("s2_eval")


@pytest.fixture()
def run_mod():
    _load("s2_eval")
    return _load("s2_run")


# ---------------------------------------------------------------- sentetik veri
def iso(ts) -> str:
    return pd.Timestamp(ts).tz_convert("UTC").strftime("%Y-%m-%dT%H:%M:%S.000Z") if pd.Timestamp(ts).tzinfo \
        else pd.Timestamp(ts).strftime("%Y-%m-%dT%H:%M:%S.000Z")


def trade(i, pair, entry_ts, r, *, qty=1.0, entry=100.0, stop=98.0, fee_entry=0.05, fee_exit=0.05, funding=0.01,
          slip=0.02, closed=True):
    """r = hedef net R; realized_pnl = r*loss_at_stop; gross = realized + fee + funding (tutarlilik)."""
    loss = loss_at_stop(qty, entry, stop)
    realized = r * loss
    gross = realized + fee_entry + fee_exit + funding
    ets = pd.Timestamp(entry_ts)
    ets = ets.tz_localize("UTC") if ets.tzinfo is None else ets
    d = dict.fromkeys(COLUMNS, "")
    d.update(trade_id=i, pair=pair, side="long", setup="x", regime="r", entry_ts=iso(ets),
             exit_ts=iso(ets + pd.Timedelta(hours=6)) if closed else "",
             entry_price=entry, exit_price=entry + gross / qty, qty=qty, leverage=1, planned_entry=entry,
             planned_stop=stop, planned_target=entry + 4, gross_pnl=gross, fee_entry=fee_entry, fee_exit=fee_exit,
             funding_paid=funding, realized_pnl=realized, slip_cost=slip, decision_id=i, param_version_id=1)
    if not closed:
        d.update(gross_pnl="", realized_pnl="", exit_price="")
    return d


def make_run(tmp_path, rows, period=FULL, name="run", expectancy=None):
    d = tmp_path / name
    d.mkdir()
    with open(d / "trades.csv", "w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=COLUMNS)
        w.writeheader()
        w.writerows(rows)
    closed = [r for r in rows if r["exit_ts"] != ""]
    if expectancy is None:
        rs = [float(r["realized_pnl"]) / loss_at_stop(float(r["qty"]), float(r["entry_price"]), float(r["planned_stop"]))
              for r in closed]
        expectancy = float(np.mean(rs)) if rs else 0.0
    (d / "summary.json").write_text(json.dumps({"expectancy_R": expectancy, "n_trades": len(closed)}))
    (d / "meta.json").write_text(json.dumps({"id": "synthetic_run", "git_commit": "abc1234", "period": period,
                                             "pairs": PAIRS}))
    return d


def spaced(rs, *, start=WSTART, step_days=4, pairs=PAIRS, qty=1.0):
    """Her r icin bir islem; pencere icinde step_days arayla, ciftler donusumlu."""
    return [trade(i, pairs[i % len(pairs)], start + pd.Timedelta(days=step_days * i, hours=3), r, qty=qty)
            for i, r in enumerate(rs)]


def check(res, code):
    got = [c for c in res["checks"] if c["code"] == code]
    assert len(got) == 1, code
    return got[0]


def day_series(rows):
    """Penceredeki her takvim gunu icin R toplami ve sayisi (spec §2)."""
    days = pd.date_range(WSTART, WEND - pd.Timedelta(days=1), freq="D")
    s = pd.Series(0.0, index=days)
    n = pd.Series(0.0, index=days)
    for r in rows:
        if r["exit_ts"] == "":
            continue
        t = pd.Timestamp(r["entry_ts"])
        if not (WSTART <= t < WEND):
            continue
        k = pd.Timestamp(t.date(), tz="UTC")
        s[k] += float(r["realized_pnl"]) / loss_at_stop(float(r["qty"]), float(r["entry_price"]), float(r["planned_stop"]))
        n[k] += 1
    return s.to_numpy(), n.to_numpy()


# ---------------------------------------------------------------- E-1
def test_e1_exam_slice_boundaries(ev):
    f = ev.exam_slice
    assert f("2022-01-05T23:59:59.999Z") is None
    assert f("2022-01-06T00:00:00.000Z") == 0
    assert f("2023-02-03T23:59:59.999Z") == 0
    assert f("2023-02-04T00:00:00.000Z") == 1
    assert f("2024-03-03T23:59:59.999Z") == 1
    assert f("2024-03-04T00:00:00.000Z") == 2
    assert f("2025-04-01T23:59:59.999Z") == 2
    assert f("2025-04-02T00:00:00.000Z") == 3
    assert f("2026-04-30T23:59:59.999Z") == 3
    assert f("2026-05-01T00:00:00.000Z") is None
    assert f("2021-03-01T00:00:00.000Z") is None


def test_e1_exam_slice_accepts_timestamp(ev):
    assert ev.exam_slice(pd.Timestamp("2022-01-06T00:00:00Z")) == 0
    assert ev.exam_slice(pd.Timestamp("2025-04-02T00:00:00Z")) == 3
    assert ev.exam_slice(pd.Timestamp("2026-05-01T00:00:00Z")) is None


def test_e1_window_uses_entry_ts_not_exit_ts(ev, tmp_path):
    # girisi pencere oncesi, cikisi pencere icinde -> sayilmaz; giris 2026-04-30 23:00, cikis 2026-05-01 -> sayilir
    rows = [
        trade(0, PAIRS[0], "2022-01-05T20:00:00", 0.1),
        trade(1, PAIRS[1], "2022-01-06T00:00:00", 0.1),
        trade(2, PAIRS[2], "2026-04-30T23:00:00", 0.1),
        trade(3, PAIRS[3], "2021-06-01T00:00:00", 0.1),
    ]
    res = ev.evaluate(make_run(tmp_path, rows), 10)
    assert check(res, "K1-1f")["value"] == 2


def test_e1_slice_count_k11d(ev, tmp_path):
    # her dilime 3 islem; dilim ortalamalari: +,+,+,-  -> 3 (>=3 gecer)
    rows, i = [], 0
    for sl, r in zip(range(4), [0.2, 0.2, 0.2, -0.3]):
        start = pd.Timestamp(SLICES[sl], tz="UTC")
        for k in range(3):
            rows.append(trade(i, PAIRS[i % 10], start + pd.Timedelta(days=10 * k, hours=1), r))
            i += 1
    res = ev.evaluate(make_run(tmp_path, rows), 10)
    c = check(res, "K1-1d")
    assert c["value"] == 3 and c["ok"] is True
    # dilim siniri sol-kapali: 2023-02-04 00:00 islemi dilim 1'e ait, ortalamayi o belirler
    rows2 = [trade(0, PAIRS[0], "2023-02-03T23:59:59", 1.0), trade(1, PAIRS[1], "2023-02-04T00:00:00", -1.0)]
    res2 = ev.evaluate(make_run(tmp_path, rows2, name="r2"), 10)
    assert check(res2, "K1-1d")["value"] == 1  # yalniz dilim 0 pozitif; dilim 1 negatif


# ---------------------------------------------------------------- E-2
def test_e2_r_matches_summary_expectancy(ev, tmp_path):
    rng = np.random.default_rng(1)
    rows = []
    for i in range(60):
        qty = float(rng.uniform(0.5, 3))
        entry = float(rng.uniform(50, 500))
        stop = entry * float(rng.uniform(0.93, 0.99))
        ts = pd.Timestamp("2021-02-01", tz="UTC") + pd.Timedelta(days=25 * i)
        rows.append(trade(i, PAIRS[i % 10], ts, float(rng.normal(0, 1)), qty=qty, entry=entry, stop=stop))
    rows.append(trade(99, PAIRS[0], "2023-01-01T00:00:00", 5.0, closed=False))  # acik islem kumeye girmez
    res = ev.evaluate(make_run(tmp_path, rows), 10)
    summ = json.loads((tmp_path / "run" / "summary.json").read_text())
    assert res["full_period"]["n_trades"] == 60 == summ["n_trades"]
    assert abs(res["full_period"]["mean_R"] - summ["expectancy_R"]) < 1e-12
    expected_med = float(np.median([float(r["realized_pnl"]) / loss_at_stop(float(r["qty"]), float(r["entry_price"]),
                                                                            float(r["planned_stop"]))
                                    for r in rows if r["exit_ts"] != ""]))
    assert abs(res["full_period"]["median_R"] - expected_med) < 1e-12


def test_e2_denominator_is_loss_at_stop_not_planned_risk(ev, tmp_path):
    # r_multiple / planned_risk sutunlari zehirli: kullanilirsa sonuc bozulur
    rows = spaced([0.5, 0.5, 0.5, 0.5])
    for r in rows:
        r["r_multiple"] = 99.0
        r["planned_risk"] = 123456.0
    res = ev.evaluate(make_run(tmp_path, rows), 10)
    assert abs(check(res, "K1-1a")["value"] - 0.5) < 1e-12


def test_e2_a_means_net_r_and_k11c_pf(ev, tmp_path):
    rows = spaced([1.0, 1.0, -0.5, -0.5])
    res = ev.evaluate(make_run(tmp_path, rows), 10)
    a = check(res, "K1-1a")
    assert abs(a["value"] - 0.25) < 1e-12 and a["ok"] is True
    pf = check(res, "K1-1c")
    loss = loss_at_stop(1.0, 100.0, 98.0)
    assert abs(pf["value"] - 2.0 / 1.0) < 1e-9 and pf["ok"] is True
    assert loss > 0
    # negatif ortalama
    res2 = ev.evaluate(make_run(tmp_path, spaced([-1.0, 0.2, -0.5]), name="r2"), 10)
    assert check(res2, "K1-1a")["ok"] is False and check(res2, "K1-1c")["ok"] is False


def test_checks_order_and_first_failure(ev, tmp_path):
    res = ev.evaluate(make_run(tmp_path, spaced([-0.2] * 10)), 10)
    assert res["schema"] == "s2-eval/1" and res["mode"] == "full"
    assert [c["code"] for c in res["checks"]] == CODES
    for c in res["checks"]:
        assert {"code", "value", "threshold", "ok"} <= set(c)
    assert res["passed"] is False
    assert res["first_failure"] == "K1-1a"
    assert res["run_id"] == "synthetic_run" and res["git_commit"] == "abc1234"
    on_disk = json.loads((tmp_path / "run" / "s2_eval.json").read_text())
    assert on_disk["first_failure"] == "K1-1a" and on_disk["n_trials"] == 11  # k=10 -> max(10, 1 + 10)


# ---------------------------------------------------------------- E-3
def test_e3_bootstrap_deterministic(ev, tmp_path):
    rng = np.random.default_rng(7)
    rows = spaced(list(rng.normal(0.3, 1.0, 150)), step_days=7)
    a = ev.evaluate(make_run(tmp_path, rows, name="a"), 10)
    b = ev.evaluate(make_run(tmp_path, rows, name="b"), 10)
    assert check(a, "K1-1b")["value"] == check(b, "K1-1b")["value"]


def test_e3_all_positive_lower_bound_positive(ev, tmp_path):
    rs = [0.4 + 0.1 * np.sin(i) for i in range(200)]
    res = ev.evaluate(make_run(tmp_path, spaced(rs, step_days=5)), 10)
    c = check(res, "K1-1b")
    assert c["value"] > 0 and c["ok"] is True


def test_e3_symmetric_noise_lower_bound_not_positive(ev, tmp_path):
    rs = [1.0 if i % 2 == 0 else -1.0 for i in range(200)]
    res = ev.evaluate(make_run(tmp_path, spaced(rs, step_days=5)), 10)
    c = check(res, "K1-1b")
    assert c["value"] <= 0 and c["ok"] is False


def test_e3_uses_10th_percentile_and_seed0(ev, tmp_path, monkeypatch):
    """n_boot=2000, seed=0 ve ortalama blok = max(1, optimal_block_length(s_g)['stationary'])."""
    rng = np.random.default_rng(3)
    rows = spaced(list(rng.normal(0.2, 1.0, 120)), step_days=9)
    res = ev.evaluate(make_run(tmp_path, rows), 10)
    s, n = day_series(rows)
    blk = max(1.0, core_stats.optimal_block_length(s)["stationary"])
    idx = core_stats.stationary_bootstrap_indices(len(s), 2000, blk, np.random.default_rng(0))
    idx = np.asarray(idx)
    stat = s[idx].sum(axis=1) / n[idx].sum(axis=1)
    assert abs(check(res, "K1-1b")["value"] - np.percentile(stat, 10)) < 1e-9


# ---------------------------------------------------------------- E-4
def _200(rfun):
    return [trade(i, PAIRS[i % 10], WSTART + pd.Timedelta(days=7 * i, hours=2), rfun(i)) for i in range(200)]


def test_e4_single_pair_carries_all_profit_fails(ev, tmp_path):
    rows = _200(lambda i: 1.0 if i % 10 == 0 else -0.01)
    res = ev.evaluate(make_run(tmp_path, rows), 10)
    assert check(res, "K1-1a")["ok"] is True  # toplam ortalama > 0
    g = check(res, "K1-1g")
    assert g["ok"] is False
    assert abs(g["value"] - (-0.01)) < 1e-9  # P0 cikarilinca kalan ortalama = en kucuk
    assert res["passed"] is False


def test_e4_balanced_pairs_pass(ev, tmp_path):
    res = ev.evaluate(make_run(tmp_path, _200(lambda i: 0.1)), 10)
    g = check(res, "K1-1g")
    assert g["ok"] is True and abs(g["value"] - 0.1) < 1e-9


def test_e4_uses_meta_pairs_list(ev, tmp_path):
    # 10 cift meta'da; her cift cikarildiginda en kotu durum alinir (en kucuk ortalama R)
    rows = _200(lambda i: 0.5 if i % 10 != 3 else -0.4)
    res = ev.evaluate(make_run(tmp_path, rows), 10)
    # P3 cikarilinca kalan ortalama 0.5; baska bir cift cikarilinca daha dusuk -> min < 0.5
    v = check(res, "K1-1g")["value"]
    mean_all = (180 * 0.5 + 20 * -0.4) / 200
    expected_min = (200 * mean_all - 20 * 0.5) / 180  # 0.5'lik bir cift cikarildi
    assert abs(v - expected_min) < 1e-9


# ---------------------------------------------------------------- E-5
def test_e5_cost_stress_hand_computed(ev, tmp_path):
    rows = [
        trade(0, PAIRS[0], "2022-03-01T00:00:00", 0.30, qty=2.0, entry=100.0, stop=95.0, fee_entry=0.10, fee_exit=0.12),
        trade(1, PAIRS[1], "2022-03-05T00:00:00", -1.0, qty=1.0, entry=50.0, stop=48.0, fee_entry=0.03, fee_exit=0.03),
    ]
    run = make_run(tmp_path, rows)
    res = ev.evaluate(run, 10)
    tot = []
    for r in rows:
        q, e, x = float(r["qty"]), float(r["entry_price"]), float(r["exit_price"])
        ek = float(r["fee_entry"]) + float(r["fee_exit"]) + 0.0005 * q * (e + x)
        tot.append((float(r["realized_pnl"]) - ek) / loss_at_stop(q, e, float(r["planned_stop"])))
    c = check(res, "K1-2")
    assert abs(c["value"] - float(np.mean(tot))) < 1e-12
    assert "threshold" in c  # bicim (sayi/metin) belirtimde sabit degil
    assert c["ok"] is bool(np.mean(tot) >= -0.05)


def test_e5_maker_entry_doubles_paid_commission_only(ev, tmp_path):
    # maker giris: fee_entry dusuk (2 bp). ek = odenen komisyon + 5bp x qty x (giris+cikis); taker varsayimi YOK.
    q, e, stop = 1.0, 100.0, 98.0
    fee_in, fee_out = 0.02 * 1.0, 0.05 * 1.0  # 2 bp maker giris, 5 bp taker cikis (notional 100 civari)
    row = trade(0, PAIRS[0], "2022-06-01T00:00:00", 0.0, qty=q, entry=e, stop=stop, fee_entry=fee_in, fee_exit=fee_out)
    res = ev.evaluate(make_run(tmp_path, [row]), 10)
    x = float(row["exit_price"])
    ek = fee_in + fee_out + 0.0005 * q * (e + x)
    expected = (float(row["realized_pnl"]) - ek) / loss_at_stop(q, e, stop)
    assert abs(check(res, "K1-2")["value"] - expected) < 1e-12
    # ayni islem taker girisle (fee_entry=0.05) olsaydi deger farkli olmali
    row2 = trade(0, PAIRS[0], "2022-06-01T00:00:00", 0.0, qty=q, entry=e, stop=stop, fee_entry=0.05, fee_exit=fee_out)
    res2 = ev.evaluate(make_run(tmp_path, [row2], name="r2"), 10)
    assert check(res2, "K1-2")["value"] < check(res, "K1-2")["value"]


def test_e5_stress_threshold_boundary(ev, tmp_path):
    # cok kotu stres: ortalama R_stres < -0.05 -> ok False; cok iyi -> True
    bad = ev.evaluate(make_run(tmp_path, spaced([-0.5] * 5)), 10)
    assert check(bad, "K1-2")["ok"] is False
    good = ev.evaluate(make_run(tmp_path, spaced([2.0] * 5), name="g"), 10)
    assert check(good, "K1-2")["ok"] is True


# ---------------------------------------------------------------- E-6
def test_e6_n_trials_function(ev):
    assert ev.n_trials(0) == 10
    assert ev.n_trials(2) == 10
    assert ev.n_trials(8) == 10
    assert ev.n_trials(9) == 10
    assert ev.n_trials(10) == 11
    assert ev.n_trials(12) == 13


@pytest.mark.parametrize("k,expected", [(12, 13), (3, 10), (9, 10), (10, 11)])
def test_e6_deflated_sharpe_called_with_n_trials(ev, tmp_path, monkeypatch, k, expected):
    calls = []
    real = core_stats.deflated_sharpe

    def spy(*a, **kw):
        calls.append((a, kw))
        return real(*a, **kw)

    monkeypatch.setattr(core_stats, "deflated_sharpe", spy)
    monkeypatch.setattr(ev, "deflated_sharpe", spy, raising=False)
    rng = np.random.default_rng(5)
    rows = spaced(list(rng.normal(0.2, 1.0, 100)), step_days=9)
    res = ev.evaluate(make_run(tmp_path, rows), k)
    assert res["n_trials"] == expected
    assert calls, "deflated_sharpe cagrilmadi"
    a, kw = calls[-1]
    nt = kw.get("n_trials", a[5] if len(a) > 5 else None)
    assert nt == expected


def test_e6_dsr_value_matches_reference(ev, tmp_path):
    rng = np.random.default_rng(11)
    rows = spaced(list(rng.normal(0.3, 1.0, 150)), step_days=9)
    res = ev.evaluate(make_run(tmp_path, rows), 12)
    s, _ = day_series(rows)
    sr = s.mean() / s.std(ddof=1)
    skew, kurt = core_stats.return_moments(s)
    ref = core_stats.deflated_sharpe(sr, len(s), skew, kurt, n_trials=13)
    c = check(res, "K1-3")
    assert abs(c["value"] - ref) < 1e-9
    assert "threshold" in c
    assert c["ok"] is bool(ref >= 0.95)


# ---------------------------------------------------------------- E-7
def _explore_rows():
    rows = []
    for i in range(12):
        rows.append(trade(i, PAIRS[i % 10], pd.Timestamp("2021-02-01", tz="UTC") + pd.Timedelta(days=80 * i), 0.2))
    # 2024-01-01 ve sonrasi: dokumlere girmemeli (zehirli ucret)
    rows.append(trade(100, PAIRS[0], "2024-01-01T00:00:00", 0.2, fee_entry=1000.0, fee_exit=1000.0, funding=500.0,
                      slip=700.0))
    rows.append(trade(101, PAIRS[1], "2024-02-10T00:00:00", 0.2, fee_entry=1000.0, fee_exit=1000.0, funding=500.0,
                      slip=700.0))
    return rows


def test_e7_explore_mode_keys_and_filter(ev, tmp_path):
    rows = _explore_rows()
    period = ["2021-01-01T00:00:00.000Z", "2024-03-01T00:00:00.000Z"]
    res = ev.evaluate(make_run(tmp_path, rows, period=period), 10)
    assert res["mode"] == "explore"
    for k in ("passed", "checks", "first_failure"):
        assert k not in res
    pre = rows[:12]
    c = res["costs"]
    assert c["n_trades"] == 12
    assert abs(c["commission_usd"] - sum(float(r["fee_entry"]) + float(r["fee_exit"]) for r in pre)) < 1e-9
    assert abs(c["slippage_usd"] - sum(float(r["slip_cost"]) for r in pre)) < 1e-9
    assert abs(c["funding_usd"] - sum(float(r["funding_paid"]) for r in pre)) < 1e-9
    on_disk = json.loads((tmp_path / "run" / "s2_eval.json").read_text())
    assert on_disk["mode"] == "explore" and "passed" not in on_disk


def test_e7_other_period_with_same_end_is_explore(ev, tmp_path):
    # tam donemin baslangici farkli -> kesif
    period = ["2022-01-01T00:00:00.000Z", "2026-05-01T00:00:00.000Z"]
    res = ev.evaluate(make_run(tmp_path, spaced([0.1] * 5), period=period), 10)
    assert res["mode"] == "explore" and "passed" not in res


def test_e7_period_end_after_lock_raises(ev, tmp_path):
    period = ["2021-01-01T00:00:00.000Z", "2026-05-02T00:00:00.000Z"]
    run = make_run(tmp_path, spaced([0.1] * 3), period=period)
    with pytest.raises(ValueError):
        ev.evaluate(run, 10)
    assert ev.main([str(run), "--n-registered", "10"]) == 2


def test_e7_main_success_returns_zero_even_when_failed(ev, tmp_path, capsys):
    run = make_run(tmp_path, spaced([-0.3] * 6))
    assert ev.main([str(run), "--n-registered", "12"]) == 0
    assert json.loads((run / "s2_eval.json").read_text())["n_trials"] == 13
    assert capsys.readouterr().out.strip() != ""  # tablo ekrana yazilir


# ---------------------------------------------------------------- E-8
def test_e8_cost_identity_and_components(ev, tmp_path):
    rng = np.random.default_rng(21)
    rows = []
    for i in range(40):
        rows.append(trade(i, PAIRS[i % 10], pd.Timestamp("2022-02-01", tz="UTC") + pd.Timedelta(days=30 * i),
                          float(rng.normal(0, 1)), qty=float(rng.uniform(0.5, 4)), entry=float(rng.uniform(20, 300)),
                          stop=None or 15.0, fee_entry=float(rng.uniform(0.01, 0.2)), fee_exit=float(rng.uniform(0.01, 0.2)),
                          funding=float(rng.normal(0, 0.1)), slip=float(rng.uniform(0, 0.3))))
    res = ev.evaluate(make_run(tmp_path, rows), 10)
    c = res["costs"]
    assert abs(c["net_usd"] - (c["gross_pre_slip_usd"] - c["commission_usd"] - c["slippage_usd"] - c["funding_usd"])) < 1e-9
    f = lambda k: sum(float(r[k]) for r in rows)
    assert abs(c["commission_usd"] - (f("fee_entry") + f("fee_exit"))) < 1e-9
    assert abs(c["slippage_usd"] - f("slip_cost")) < 1e-9
    assert abs(c["funding_usd"] - f("funding_paid")) < 1e-9
    assert abs(c["net_usd"] - f("realized_pnl")) < 1e-9
    assert abs(c["gross_pre_slip_usd"] - (f("gross_pnl") + f("slip_cost"))) < 1e-9
    assert c["n_trades"] == 40


def test_e8_per_trade_ratios(ev, tmp_path):
    rows = [trade(i, PAIRS[i], f"2022-0{i + 2}-10T00:00:00", 0.1 * i, qty=1.0 + i, entry=100.0 + 10 * i,
                  stop=90.0 + 10 * i, fee_entry=0.1, fee_exit=0.2, funding=0.05, slip=0.03) for i in range(5)]
    res = ev.evaluate(make_run(tmp_path, rows), 10)
    c = res["costs"]
    loss = [loss_at_stop(float(r["qty"]), float(r["entry_price"]), float(r["planned_stop"])) for r in rows]
    rp = c["r_per_trade"]
    assert abs(rp["commission"] - np.mean([0.3 / l for l in loss])) < 1e-12
    assert abs(rp["slippage"] - np.mean([0.03 / l for l in loss])) < 1e-12
    assert abs(rp["funding"] - np.mean([0.05 / l for l in loss])) < 1e-12
    assert abs(rp["net"] - np.mean([float(r["realized_pnl"]) / l for r, l in zip(rows, loss)])) < 1e-12
    assert abs(rp["gross_pre_slip"] - np.mean([(float(r["gross_pnl"]) + 0.03) / l for r, l in zip(rows, loss)])) < 1e-12
    assert abs(rp["net"] - (rp["gross_pre_slip"] - rp["commission"] - rp["slippage"] - rp["funding"])) < 1e-12
    # bp: payda sum(qty*entry_price); tur basina baz puan (x 1e4)
    notional = sum(float(r["qty"]) * float(r["entry_price"]) for r in rows)
    bp = c["bp_per_round_trip"]
    assert abs(bp["commission"] - 1.5 / notional * 1e4) < 1e-9
    assert abs(bp["slippage"] - 0.15 / notional * 1e4) < 1e-9
    assert abs(bp["funding"] - 0.25 / notional * 1e4) < 1e-9


def test_e8_open_trades_excluded_from_costs(ev, tmp_path):
    rows = spaced([0.1, 0.1, 0.1]) + [trade(50, PAIRS[0], "2023-01-01T00:00:00", 0.0, closed=False)]
    res = ev.evaluate(make_run(tmp_path, rows), 10)
    assert res["costs"]["n_trades"] == 3


# ---------------------------------------------------------------- K1-1e / K1-1f
def test_k11e_post_2024_mean(ev, tmp_path):
    pre = [trade(i, PAIRS[i % 10], pd.Timestamp("2022-02-01", tz="UTC") + pd.Timedelta(days=20 * i), 0.5)
           for i in range(20)]
    post_bad = [trade(100 + i, PAIRS[i % 10], pd.Timestamp("2024-02-01", tz="UTC") + pd.Timedelta(days=20 * i), -0.1)
                for i in range(5)]
    res = ev.evaluate(make_run(tmp_path, pre + post_bad), 10)
    e = check(res, "K1-1e")
    assert abs(e["value"] + 0.1) < 1e-12 and e["ok"] is False
    # tam 2024-01-01 00:00 giris post sayilir
    r2 = ev.evaluate(make_run(tmp_path, pre + [trade(200, PAIRS[0], "2024-01-01T00:00:00", -0.2)], name="r2"), 10)
    assert abs(check(r2, "K1-1e")["value"] + 0.2) < 1e-12


def test_k11f_threshold_800(ev, tmp_path):
    rows = [trade(i, PAIRS[i % 10], WSTART + pd.Timedelta(hours=40 * i), 0.1) for i in range(800)]
    res = ev.evaluate(make_run(tmp_path, rows), 10)
    f = check(res, "K1-1f")
    assert f["value"] == 800 and f["ok"] is True
    res2 = ev.evaluate(make_run(tmp_path, rows[:799], name="r2"), 10)
    assert check(res2, "K1-1f")["ok"] is False


# ---------------------------------------------------------------- E-9 (s2_run)
REG_COLS = ["id", "timestamp", "git_commit", "strategy", "params", "period", "cost_arm", "trigger_tf", "trades",
            "expectancy_R", "PF", "maxDD", "notes"]


@pytest.fixture()
def sandbox(run_mod, tmp_path, monkeypatch):
    """REPO_ROOT/REGISTRY_PATH/OUT_ROOT tmp'ye; _git_clean temiz; _run_backtest cagrilirsa kaydeder."""
    reg = tmp_path / "trial_registry.csv"
    out = tmp_path / "backtests"
    out.mkdir()
    state = {"calls": [], "clean": True}

    def fake_bt(argv):
        state["calls"].append(list(argv))
        return 0

    monkeypatch.setattr(run_mod, "REPO_ROOT", tmp_path, raising=False)
    monkeypatch.setattr(run_mod, "REGISTRY_PATH", reg, raising=False)
    monkeypatch.setattr(run_mod, "OUT_ROOT", out, raising=False)
    monkeypatch.setattr(run_mod, "_git_clean", lambda *a, **k: state["clean"], raising=False)
    monkeypatch.setattr(run_mod, "_run_backtest", fake_bt, raising=False)
    state.update(reg=reg, out=out, mod=run_mod)
    return state


def write_registry(path, ids):
    with open(path, "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=REG_COLS)
        w.writeheader()
        for n, i in enumerate(ids, 1):
            row = dict.fromkeys(REG_COLS, "")
            row["id"] = f"{n:03d}:{i}"
            w.writerow(row)


def run_main(mod, argv):
    try:
        rc = mod.main(argv)
    except SystemExit as e:  # argparse reddi de ret sayilir
        rc = e.code
    return rc


def registry_text(path):
    return Path(path).read_text(encoding="utf-8") if Path(path).exists() else ""


@pytest.mark.parametrize("rng", ["20230101-20240201", "20201201-20230101", "20240101-20240301", "20260501-20260801"])
def test_e9_explore_out_of_range_rejected(sandbox, rng):
    write_registry(sandbox["reg"], ["S2-1_onkayit"])
    before = registry_text(sandbox["reg"])
    rc = run_main(sandbox["mod"], ["--explore", rng])
    assert rc not in (0, None)
    assert sandbox["calls"] == []
    assert registry_text(sandbox["reg"]) == before


def test_e9_explore_with_trial_out_of_range_rejected(sandbox):
    rc = run_main(sandbox["mod"], ["--explore", "20230101-20240201", "--trial", "S2-1"])
    assert rc not in (0, None) and sandbox["calls"] == []


def test_e9_s2_trial_without_prereg_rejected(sandbox):
    write_registry(sandbox["reg"], ["lookahead_x", "S2-2_onkayit"])  # S2-2 onkayit S2-1'i karsilamaz
    before = registry_text(sandbox["reg"])
    rc = run_main(sandbox["mod"], ["--trial", "S2-1"])
    assert rc not in (0, None)
    assert sandbox["calls"] == []
    assert registry_text(sandbox["reg"]) == before


def test_e9_s2_trial_empty_or_missing_registry_rejected(sandbox):
    assert not sandbox["reg"].exists()
    rc = run_main(sandbox["mod"], ["--trial", "S2-2"])
    assert rc not in (0, None) and sandbox["calls"] == []


@pytest.mark.parametrize("argv", [["--trial", "S2-1"], ["--trial", "S2-2"], ["--trial", "BASE"]])
def test_e9_dirty_tree_rejected(sandbox, argv):
    write_registry(sandbox["reg"], ["S2-1_onkayit", "S2-2_onkayit"])
    sandbox["clean"] = False
    before = registry_text(sandbox["reg"])
    rc = run_main(sandbox["mod"], argv)
    assert rc not in (0, None)
    assert sandbox["calls"] == []
    assert registry_text(sandbox["reg"]) == before


def test_e9_dirty_tree_rejected_in_explore_full_range_edges(sandbox):
    sandbox["clean"] = False
    rc = run_main(sandbox["mod"], ["--explore", "20230101-20230301"])
    assert rc not in (0, None) and sandbox["calls"] == []


def test_e9_dirty_tree_checked_before_prereg(sandbox):
    # kirli agac + onkayit yok: yine de ret, motor yok
    sandbox["clean"] = False
    rc = run_main(sandbox["mod"], ["--trial", "S2-1"])
    assert rc not in (0, None) and sandbox["calls"] == []


def test_e9_existing_output_dir_rejected(sandbox):
    (sandbox["out"] / "s2_base_v1b").mkdir()
    rc = run_main(sandbox["mod"], ["--trial", "BASE"])
    assert rc not in (0, None) and sandbox["calls"] == []


def test_e9_unknown_trial_or_missing_args_rejected(sandbox):
    assert run_main(sandbox["mod"], ["--trial", "S2-9"]) not in (0, None)
    assert run_main(sandbox["mod"], []) not in (0, None)
    assert run_main(sandbox["mod"], ["--explore", "garbage"]) not in (0, None)
    assert sandbox["calls"] == []


def test_e9_base_needs_no_prereg_and_never_touches_registry(sandbox):
    """BASE: on kayit satiri istemez (ret nedeni olamaz); registry'ye satir eklenmez."""
    write_registry(sandbox["reg"], ["lookahead_x"])
    before = registry_text(sandbox["reg"])
    try:
        run_main(sandbox["mod"], ["--trial", "BASE"])
    except Exception:
        pass  # sahte motor cikti uretmedigi icin sonraki asamada hata olabilir; onemli olan registry
    assert registry_text(sandbox["reg"]) == before
