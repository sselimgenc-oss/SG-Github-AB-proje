#!/usr/bin/env python3
"""ML 19b: tarihsel aday seti (NATIVE kip) -- motor backtester'indan (v1b = price_action_v1, paper yapilandirmasi).

Akis: (1) `trader_engine.backtest` ile [2024-11-01, 2026-05-01) araligini kosar (KILITLI DONEM 2026-05..10 okunmaz/kosulmaz),
(2) ledger'daki TUM karar olaylarini (alinan + atlanan; `v_decisions`) toplar, (3) alinan islemlerin GERCEK cikis zamani
ve net R'sini (`v_trades.r_multiple`: komisyon+kayma+funding sonrasi) yazar, (4) tum adaylara `trader_ml.labels`
ile uclu bariyer etiketi, (5) ozellikleri `trader_ml.features` (egitim hatti; canli ile ayni kod) ile uretir,
(6) `trader_ml.schema` semasinda parquet + damgali manifest yazar. Model egitilmez, kapi calistirilmaz.

Bellek: backtest ayri surec (stream); ozellik/etiket cift basina islenir, tum mumlar tutulmaz (tepe << 2 GB).

Kullanim (uzun kosu arka planda):
  PYTHONPATH=src nohup .venv/bin/python research/ml_build_candidates.py > research/logs/ml_build.log 2>&1 &
  --run-dir var/backtests/<id>   hazir bir kosuyu kullan (backtest'i atla)
"""
from __future__ import annotations

import argparse
import hashlib
import json
import resource
import sqlite3
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from trader_ml.config import BAR, DATA_START, HOLDOUT_START  # noqa: E402
from trader_ml.features import feature_frame  # noqa: E402
from trader_ml.guards import assert_pre_holdout  # noqa: E402
from trader_ml.labels import cost_in_r, label_candidates  # noqa: E402
from trader_ml.schema import REQUIRED, feature_columns, validate_candidates  # noqa: E402

RUN_ID = "ml_cand_v1b_native"
PERIOD = "20241101-20260501"                      # bitis dislayici = HOLDOUT_START
OUT_DIR = ROOT / "research" / "ml"
HISTORY = ROOT / "user_data" / "data" / "binance" / "futures"
BT_ARGS = ["--period", PERIOD, "--tf", "1h", "--fill-model", "native", "--strategy", "price_action_v1", "--synthetic-rules"]


def to_ml_pair(p: str) -> str:
    return p if ":" in p else f"{p}:{p.split('/')[1]}"


def load_pre_holdout_candles(pair: str) -> pd.DataFrame:
    """1s mumlar; kilitli donem satirlari DOSYA OKUMASINDA filtrelenir (hic yuklenmez)."""
    import pyarrow as pa
    import pyarrow.dataset as ds
    stem = pair.replace("/", "_").replace(":", "_")
    path = HISTORY / f"{stem}-1h-futures.feather"
    cut = pa.scalar(HOLDOUT_START.to_pydatetime(), type=pa.timestamp("ms", tz="UTC"))
    t = ds.dataset(str(path), format="feather").to_table(
        columns=["date", "open", "high", "low", "close", "volume"], filter=ds.field("date") < cut)
    df = t.to_pandas()
    df["date"] = pd.to_datetime(df["date"], utc=True)
    df = df.set_index("date").sort_index()
    assert_pre_holdout(df.index, f"{pair} mum")
    return df


def prefilter_rows(frame: pd.DataFrame, pair: str) -> pd.DataFrame:
    """Yonu ve planli girisi olan TUM satirlar (sinyal True + stop_width gibi on-filtreyle elenenler); `signal` korunur.
    (`candidate_rows` yalniz sinyal True satirlari verir; ledger ise on-filtreyle elenenleri de karar olayi olarak yazar.)"""
    m = frame["side"].notna() & frame["planned_entry"].notna()
    r = frame[m].copy()
    r.insert(0, "pair", pair)
    r.insert(1, "ts", r.index + BAR)
    return r.reset_index(drop=True)


def run_backtest(run_dir: Path) -> None:
    cmd = [sys.executable, "-m", "trader_engine.backtest", "--id", run_dir.name, "--out-root", str(run_dir.parent), *BT_ARGS]
    env = {**__import__("os").environ, "PYTHONPATH": str(ROOT / "src")}
    print("backtest:", " ".join(cmd), flush=True)
    r = subprocess.run(cmd, cwd=ROOT, env=env)
    if r.returncode != 0:
        raise SystemExit(f"backtest basarisiz (kod {r.returncode})")


def read_ledger(run_dir: Path) -> tuple[pd.DataFrame, pd.DataFrame]:
    con = sqlite3.connect(f"file:{run_dir / 'ledger.sqlite'}?mode=ro", uri=True)
    try:
        dec = pd.read_sql("SELECT id, bar_close_ts, pair, side, setup, planned_entry, planned_stop, planned_target, "
                          "final_action, skip_reason FROM v_decisions", con)
        tr = pd.read_sql("SELECT decision_id, exit_ts, r_multiple, exit_reason FROM v_trades", con)
    finally:
        con.close()
    return dec, tr


def config_hash(run_dir: Path) -> tuple[str, dict]:
    meta = json.loads((run_dir / "meta.json").read_text())
    base = json.loads((ROOT / "config" / "engine.base.json").read_text())
    payload = {"engine_base": base, "cost": meta["cost"], "strategy": meta["strategy_label"], "tf": meta["trigger_tf"],
               "fill_model": meta["fill_model"], "granularity": meta["granularity"], "period": meta["period"],
               "rules_source": meta["rules_source"], "param_version_id": meta["param_version_id"],
               "bt_args": [a for a in meta["flags"]["argv"] if a not in ("--id", meta["id"])]}
    h = hashlib.sha256(json.dumps(payload, sort_keys=True, default=str).encode()).hexdigest()
    return h, payload


def build(run_dir: Path, out_name: str) -> tuple[pd.DataFrame, dict]:
    meta = json.loads((run_dir / "meta.json").read_text())
    if meta["fill_model"] != "native":
        raise SystemExit("yalniz native kip")
    end = pd.Timestamp(meta["period"][1])
    if end > HOLDOUT_START:
        raise SystemExit(f"kosu kilitli doneme giriyor: {end}")
    dec, tr = read_ledger(run_dir)
    dec["ts"] = pd.to_datetime(dec["bar_close_ts"], utc=True)
    dec = dec[dec["final_action"].isin(["entered", "skipped"]) & dec["side"].notna() & dec["planned_entry"].notna()]
    dec = dec.merge(tr, how="left", left_on="id", right_on="decision_id")
    dec["pair_ml"] = dec["pair"].map(to_ml_pair)
    stats = {"decisions_total": int(len(dec)), "entered_total": int((dec["final_action"] == "entered").sum())}
    parts, per_pair, dropped = [], {}, {"before_data_start": 0, "taken_open_at_end": 0, "no_feature_row": 0}
    for pair, g in dec.groupby("pair_ml", sort=True):
        df = load_pre_holdout_candles(pair)
        frame = prefilter_rows(feature_frame(df, None, None), pair)
        feats = [c for c in frame.columns if c.startswith("f_")]
        g = g[g["ts"] >= DATA_START].copy()
        m = g.merge(frame[["ts", "side", "signal", *feats]], how="left", on=["ts", "side"], indicator=True)
        dropped["no_feature_row"] += int((m["_merge"] == "left_only").sum())
        m = m[m["_merge"] == "both"].drop(columns="_merge")
        taken = m["final_action"].eq("entered")
        open_end = taken & m["exit_ts"].isna()
        dropped["taken_open_at_end"] += int(open_end.sum())
        m = m[~open_end].copy()
        taken = m["final_action"].eq("entered")
        cands = pd.DataFrame({"ts": m["ts"].to_numpy(), "side": m["side"].to_numpy(), "planned_entry": m["planned_entry"].to_numpy(),
                              "planned_stop": m["planned_stop"].to_numpy(), "planned_target": m["planned_target"].to_numpy(float)},
                             index=m.index)
        lab = label_candidates(df, cands)
        out = pd.DataFrame(index=m.index)
        out["pair"] = pair
        out["ts"] = m["ts"]
        out["setup"] = m["setup"]
        out["side"] = m["side"]
        for c in ("planned_entry", "planned_stop", "planned_target"):
            out[c] = m[c].astype(float)
        out["source"] = "backtest"
        out["taken"] = taken
        out["label"] = lab["label"]
        out["label_end_ts"] = lab["label_end_ts"]
        # alinan: GERCEK cikis (motor ledger); alinmayan: referans cikis net R'si (basit kural; gercek cikis yok), exit_ts yok
        out["net_r"] = np.where(taken, m["r_multiple"], lab["net_r"])
        bad = out["net_r"].isna()                         # veri sonuna yakin: referans cikis cozulmedi -> aday cozulmemis sayilir
        out.loc[bad, "label"] = np.nan
        out.loc[bad, "label_end_ts"] = pd.NaT
        out["cost_r"] = cost_in_r(out["planned_entry"], out["planned_stop"])
        out["exit_ts"] = pd.to_datetime(m["exit_ts"], utc=True).where(taken)
        for c in feats:
            out[c] = m[c]
        out["ml_eligible"] = m["signal"].astype(bool)           # canlida ML'in puanlayacagi aday (strateji sinyali True)
        out["exit_reason"] = m["exit_reason"].where(taken)
        out["skip_reason"] = m["skip_reason"].where(~taken)
        parts.append(out)
        per_pair[pair] = {"taken": int(taken.sum()), "skipped": int((~taken).sum()),
                          "label_pos": int((out["label"] == 1).sum()), "label_neg": int((out["label"] == 0).sum()),
                          "label_unresolved": int(out["label"].isna().sum())}
        del df, frame
    t = pd.concat(parts, ignore_index=True)
    # sema disi yardimci sutunlar (exit_reason/skip_reason) yuklemeyi bozmaz ama ozellik degildir; sema dogrulamasi:
    t = validate_candidates(t)
    stats.update(dropped=dropped, per_pair_all_decisions=per_pair)
    return t, stats


def split_eligible(t: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Ana set: canlida ML'in puanlayacagi adaylar (sinyal True: alinan + risk/emir reddi). On-filtreyle elenenler (stop_width)
    canlida ML'e hic gelmez; ayri dosyada tutulur (model/kapi bunlari gormez)."""
    e = t["ml_eligible"].astype(bool)
    return t[e].reset_index(drop=True), t[~e].reset_index(drop=True)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--run-dir", default=None)
    ap.add_argument("--out", default="candidates_v1b_native")
    a = ap.parse_args(argv)
    run_dir = Path(a.run_dir) if a.run_dir else ROOT / "var" / "backtests" / RUN_ID
    if not (run_dir / "ledger.sqlite").exists():
        run_backtest(run_dir)
    t, stats = build(run_dir, a.out)
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    t_all = t
    t, pre = split_eligible(t_all)
    pq = OUT_DIR / f"{a.out}.parquet"
    t.to_parquet(pq, index=False)
    pre.to_parquet(OUT_DIR / f"{a.out}_prefiltered.parquet", index=False)
    meta = json.loads((run_dir / "meta.json").read_text())
    chash, payload = config_hash(run_dir)
    lab = t["label"].dropna()
    taken = t["taken"]
    manifest = {
        "file": pq.name, "mode": "native", "source": "backtest", "schema": "trader_ml.schema (19b)",
        "engine_git_commit": meta["git_commit"], "engine_version": meta["engine_version"],
        "strategy": meta["strategy_label"], "config_hash_sha256": chash,
        "config": {k: payload[k] for k in ("cost", "tf", "fill_model", "granularity", "rules_source", "bt_args")},
        "backtest_period": meta["period"], "candidate_ts_min": str(t["ts"].min()), "candidate_ts_max": str(t["ts"].max()),
        "holdout_start": str(HOLDOUT_START), "holdout_read": False, "data_start": str(DATA_START),
        "built_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "rows": int(len(t)), "rows_all_decisions": int(len(t_all)), "taken": int(taken.sum()), "skipped": int((~taken).sum()),
        "label_balance": {"pos": int((lab == 1).sum()), "neg": int((lab == 0).sum()), "unresolved": int(t["label"].isna().sum()),
                          "pos_rate": round(float((lab == 1).mean()), 4)},
        "net_r_taken_mean": round(float(t.loc[taken, "net_r"].mean()), 4),
        "features": feature_columns(t), "n_features": len(feature_columns(t)),
        "extra_columns": [c for c in t.columns if not c.startswith("f_") and c not in REQUIRED],
        "notes": ["taken net_r = ledger r_multiple (komisyon+kayma+funding sonrasi, gercek cikis); skipped net_r = labels referans "
                  "cikisi (48 mum zaman cikisi / R1 hedefi; basit kural), exit_ts yok",
                  "alinan ama donem sonunda acik kalan islemler dislandi (exit_ts yok)",
                  "f_slope_1d: 1500 barlik canli pencereyle hesaplanir; BTC/ETH/funding/f_bars_since_exit aktif listede yok (karar 2a)",
                  "compat capraz dogrulamasi native davranisi degistirirse yeniden uretilir (karar 4)"],
        "per_pair": {k: {"taken": int(g["taken"].sum()), "skipped": int((~g["taken"]).sum()),
                         "label_pos": int((g["label"] == 1).sum()), "label_neg": int((g["label"] == 0).sum())}
                     for k, g in t.groupby("pair")},
        "prefiltered_file": f"{a.out}_prefiltered.parquet", "prefiltered_rows": int(len(pre)),
        "prefiltered_skip_reasons": pre["skip_reason"].value_counts().to_dict(),
        "skip_reasons_main": t.loc[~taken, "skip_reason"].value_counts().to_dict(),
        **stats,
        "peak_rss_mb": round(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024),
    }
    (OUT_DIR / f"{a.out}.manifest.json").write_text(json.dumps(manifest, indent=1, default=str))
    print(json.dumps({k: manifest[k] for k in ("rows", "taken", "skipped", "label_balance", "dropped", "prefiltered_rows",
                                               "per_pair", "peak_rss_mb")}, default=str),
          flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
