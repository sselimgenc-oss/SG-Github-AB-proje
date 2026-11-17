"""19b: research/ml_build_candidates.py -- ledger (karar olaylari) -> semaya uygun aday tablosu (sentetik mini ledger)."""
from __future__ import annotations

import importlib.util
import json
import sqlite3
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from trader_ml.features import candidate_rows, feature_frame
from trader_ml.schema import feature_columns, load_candidates, validate_candidates
from trader_core import ml_features as core_feat

ROOT = Path(__file__).resolve().parents[2]
PAIR = "SOL/USDT:USDT"


@pytest.fixture(scope="module")
def mod():
    spec = importlib.util.spec_from_file_location("ml_build_candidates", ROOT / "research" / "ml_build_candidates.py")
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


def _fake_run(tmp_path, candles):
    df = candles[PAIR]
    rows = candidate_rows(feature_frame(df, None, None), PAIR)
    rows = rows[rows["ts"] >= df.index[0] + pd.Timedelta(hours=1600)].head(40).reset_index(drop=True)
    con = sqlite3.connect(tmp_path / "ledger.sqlite")
    con.execute("CREATE TABLE v_decisions (id INTEGER, bar_close_ts TEXT, pair TEXT, side TEXT, setup TEXT, planned_entry REAL,"
                " planned_stop REAL, planned_target REAL, final_action TEXT, skip_reason TEXT)")
    con.execute("CREATE TABLE v_trades (decision_id INTEGER, exit_ts TEXT, r_multiple REAL, exit_reason TEXT)")
    for i, r in rows.iterrows():
        taken = i % 3 == 0
        con.execute("INSERT INTO v_decisions VALUES (?,?,?,?,?,?,?,?,?,?)",
                    (i, r["ts"].strftime("%Y-%m-%dT%H:%M:%S.000Z"), "SOL/USDT", r["side"], r["setup"], r["planned_entry"],
                     r["planned_stop"], None if pd.isna(r["planned_target"]) else r["planned_target"],
                     "entered" if taken else "skipped", None if taken else "risk_denied"))
        if taken:
            con.execute("INSERT INTO v_trades VALUES (?,?,?,?)",
                        (i, (r["ts"] + pd.Timedelta(hours=5)).strftime("%Y-%m-%dT%H:%M:%S.000Z"), 1.25 if i % 2 else -1.0, "stop"))
    con.commit()
    con.close()
    meta = {"fill_model": "native", "period": ["2024-11-01T00:00:00.000Z", "2026-05-01T00:00:00.000Z"]}
    (tmp_path / "meta.json").write_text(json.dumps(meta))
    return rows


def test_build_candidates_schema_taken_skipped_and_labels(mod, candles, tmp_path, monkeypatch):
    rows = _fake_run(tmp_path, candles)
    monkeypatch.setattr(mod, "load_pre_holdout_candles", lambda pair: candles[pair])
    monkeypatch.setattr(mod, "DATA_START", candles[PAIR].index[0])
    t, stats = mod.build(tmp_path, "x")
    assert len(t) == len(rows) == stats["decisions_total"]
    assert int(t["taken"].sum()) == (len(rows) + 2) // 3 and (~t["taken"]).sum() == len(rows) - t["taken"].sum()
    # alinan: ledger gercek cikis + net R; alinmayan: exit_ts yok
    tk = t[t["taken"]]
    assert tk["exit_ts"].notna().all() and ((tk["exit_ts"] - tk["ts"]) == pd.Timedelta(hours=5)).all()
    assert set(tk["net_r"].round(6)) <= {1.25, -1.0}
    assert t.loc[~t["taken"], "exit_ts"].isna().all()
    # etiket: tum adaylar icin uclu bariyer (cozulmus satirlarda 0/1) ve sema gecerli, ozellikler tam
    assert t["label"].dropna().isin([0, 1]).all() and t["label"].notna().sum() > 0.8 * len(t)
    validate_candidates(t)
    assert set(feature_columns(t)) == set(core_feat.FEATURE_NAMES)
    assert not t[feature_columns(t)].isna().all().any()
    assert (t["pair"] == PAIR).all() and (t["source"] == "backtest").all()
    # kilitli donem: etiket/cikis zamani sinirin altinda
    assert t["label_end_ts"].dropna().max() < pd.Timestamp("2026-05-01", tz="UTC")


def test_holdout_rows_never_loaded(mod):
    # mum yukleyici dosya duzeyinde keser; sinir disindaki tarih HoldoutViolation ile reddedilir
    from trader_ml.guards import HoldoutViolation, assert_pre_holdout
    with pytest.raises(HoldoutViolation):
        assert_pre_holdout(pd.DatetimeIndex([pd.Timestamp("2026-05-01", tz="UTC")]))
    assert mod.PERIOD.endswith("20260501")


def test_real_candidate_file_loader_smoke():
    p = ROOT / "research" / "ml" / "candidates_v1b_native.parquet"
    mp = ROOT / "research" / "ml" / "candidates_v1b_native.manifest.json"
    if not p.exists():
        pytest.skip("gercek aday dosyasi yok (research/ml_build_candidates.py)")
    t = load_candidates(p)                       # sema + kilitli donem korumasi
    m = json.loads(mp.read_text())
    assert m["mode"] == "native" and m["holdout_read"] is False and m["rows"] == len(t)
    assert m["taken"] == int(t["taken"].sum())
    assert set(feature_columns(t)) == set(core_feat.FEATURE_NAMES)


def test_split_eligible_separates_prefiltered_rows(mod, candles, tmp_path, monkeypatch):
    rows = _fake_run(tmp_path, candles)
    monkeypatch.setattr(mod, "load_pre_holdout_candles", lambda pair: candles[pair])
    monkeypatch.setattr(mod, "DATA_START", candles[PAIR].index[0])
    t, _ = mod.build(tmp_path, "x")
    assert t["ml_eligible"].all()                       # sentetik ledger yalniz sinyal True satirlari icerir
    main, pre = mod.split_eligible(t)
    assert len(main) == len(t) and pre.empty
    t2 = t.copy()
    t2.loc[t2.index[:5], "ml_eligible"] = False
    main, pre = mod.split_eligible(t2)
    assert len(pre) == 5 and len(main) == len(t) - 5
