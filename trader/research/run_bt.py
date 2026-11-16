#!/usr/bin/env python3
"""TraderV1 backtest kosucusu + metrik hesaplayici (arastirma; strateji koduna dokunmaz).

Kullanim (venv): PYTHONPATH=src .venv-ft/bin/python research/run_bt.py --id 1h_IS_f2_s2 --period IS \
    --fee-mult 2 --slip-bps 2 --tf 1h [--params '{"trail_atr":3.5}'] [--ledger] [--notes "..."]

Maliyet: freqtrade backtest'te kayma (slippage) secenegi yok; taraf basina kayma, --fee'ye eklenerek
yaklasiklanir: fee_eff = 0.0005*fee_mult + slip_bps/1e4 (giris ve cikis icin ayri uygulanir).
Cikti: user_data/backtest_results/<id>/ (gitignore'da), research/runs/<id>.json (ozet).
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))
from trader_core import risk as K  # noqa: E402

PERIODS = {"IS": "20241101-20251101", "WF": "20251101-20260501"}  # HOLDOUT (20260501-20261101) BILEREK YOK
BASE_FEE = 0.0005
RUNS = ROOT / "research" / "runs"
BT_DIR = ROOT / "user_data" / "backtest_results"
FUT = ROOT / "user_data/data/binance/futures"
TF_MIN = {"1h": 60, "15m": 15}


def git_commit() -> str:
    try:
        c = subprocess.run(["git", "rev-parse", "--short", "HEAD"], cwd=ROOT, capture_output=True, text=True).stdout.strip()
        d = subprocess.run(["git", "status", "--porcelain", "--", "src", "user_data/strategies", "config"], cwd=ROOT,
                           capture_output=True, text=True).stdout.strip()
        return c + ("+dirty" if d else "")
    except Exception:  # noqa: BLE001
        return "unknown"


def build_and_run(a) -> Path:
    rid = a.id
    out = BT_DIR / rid
    if out.exists():
        raise SystemExit(f"{out} zaten var")
    out.mkdir(parents=True)
    fee = round(BASE_FEE * a.fee_mult + a.slip_bps / 1e4, 8)
    params = json.loads(a.params) if a.params else {}
    params["trigger_tf"] = a.tf
    tv1 = {"params": params}
    tv1["ledger_path"] = str(out / "ledger.sqlite")  # gecici/yeni defter; tum kosularda (islemleri degistirmedigi dogrulandi)
    cfgp = out / "overlay.json"
    cfgp.write_text(json.dumps({"timeframe": a.tf, "trader_v1": tv1}, indent=1))
    tr = PERIODS.get(a.period, a.period)
    if tr.split("-")[1] > "20260501" and a.period not in PERIODS:
        raise SystemExit("HOLDOUT (>20260501) bu asamada calistirilamaz")
    cmd = [sys.executable, "scripts/freqtrade_offline.py" if a.tf == "1h" else "research/ft_offline_15m.py", "backtesting",
           "--config", "config/base.json", "--config", "config/backtest.json", "--config", str(cfgp),
           "--userdir", "user_data", "--datadir", "user_data/data/binance",
           "--strategy", "TraderV1", "--strategy-path", "user_data/strategies",
           "--timerange", tr, "--fee", str(fee), "--export", "trades", "--backtest-directory", str(out)]
    if a.tf == "1h":
        cmd += ["--timeframe-detail", "15m"]
    env = dict(os.environ, PYTHONPATH=str(ROOT / "src"))
    t0 = time.time()
    with open(out / "run.log", "w") as lg:
        p = subprocess.run(cmd, cwd=ROOT, env=env, stdout=lg, stderr=subprocess.STDOUT)
    if p.returncode != 0:
        raise SystemExit(f"backtest basarisiz rc={p.returncode}; bkz {out/'run.log'}")
    print(f"[{rid}] backtest {time.time()-t0:.0f}s", flush=True)
    return out


def pf(x: pd.Series) -> float:
    w, l = x[x > 0].sum(), -x[x < 0].sum()
    return float(w / l) if l > 0 else (float("inf") if w > 0 else float("nan"))


def loss_at_stop(qty, entry, stop):
    return K.loss_at_stop(qty, entry, stop, K.LOCKED_CFG)


def load_prices() -> dict:
    px = {}
    for f in FUT.glob("*-1h-futures.feather"):
        pair = f.name.split("-1h")[0]
        d = pd.read_feather(f)[["date", "close"]]
        px[pair] = d.set_index("date")["close"]
    return px


def analyze(out: Path, a, fee: float) -> dict:
    from freqtrade.data.btanalysis import load_backtest_data, load_backtest_stats
    stats = load_backtest_stats(out)["strategy"]["TraderV1"]
    t = load_backtest_data(out).copy()
    tfm = TF_MIN[a.tf]
    res = dict(n_trades=int(len(t)))
    if t.empty:
        return res
    import sqlite3
    led = pd.read_sql("SELECT pair, entry_ts, regime, planned_stop, planned_risk, r_multiple AS r_ledger, "
                      "realized_pnl AS pnl_ledger FROM v_trades", sqlite3.connect(out / "ledger.sqlite"))
    led["open_date"] = pd.to_datetime(led["entry_ts"], utc=True)
    led["pair"] = led["pair"].where(led["pair"].str.contains(":"), led["pair"] + ":USDT")
    t["open_date"] = pd.to_datetime(t["open_date"], utc=True)
    t = t.merge(led.drop(columns=["entry_ts"]), on=["pair", "open_date"], how="left")
    t["side"] = np.where(t["is_short"], "short", "long")
    # maliyetler
    t["fee_paid"] = t["amount"] * t["open_rate"] * t["fee_open"] + t["amount"] * t["close_rate"] * t["fee_close"]
    t["slip_paid"] = t["amount"] * (t["open_rate"] + t["close_rate"]) * (a.slip_bps / 1e4)
    t["fee_only"] = t["fee_paid"] - t["slip_paid"]
    t["funding"] = t["funding_fees"].fillna(0.0)  # + alinan, - odenen
    t["gross"] = t["profit_abs"] + t["fee_paid"] - t["funding"]
    # R
    t["risk_amt"] = [loss_at_stop(q, e, s) if np.isfinite(s) else np.nan
                     for q, e, s in zip(t["amount"], t["open_rate"], t["planned_stop"])]
    t["R"] = t["profit_abs"] / t["risk_amt"]
    r_ok = t["R"].notna()
    # risk kilidi: giriste ozsermaye tahmini
    px = load_prices()
    eqs = []
    tt = t.sort_values("open_date").reset_index(drop=True)
    for i, r in tt.iterrows():
        closed = tt.loc[tt["close_date"] <= r["open_date"], "profit_abs"].sum()
        openm = tt[(tt["open_date"] < r["open_date"]) & (tt["close_date"] > r["open_date"])]
        un = 0.0
        for _, o in openm.iterrows():
            s = px.get(o["pair"].replace("/", "_").replace(":", "_"))
            if s is None:
                continue
            ts = r["open_date"] - pd.Timedelta(hours=1)
            idx = s.index.searchsorted(ts, side="right") - 1
            if idx < 0:
                continue
            p = float(s.iloc[idx])
            un += o["amount"] * (p - o["open_rate"]) * (-1 if o["is_short"] else 1)
        eqs.append(stats["starting_balance"] + closed + un)
    tt["equity_entry_est"] = eqs
    tt["loss"] = -tt["profit_abs"]
    tt["loss_pct_eq"] = tt["loss"] / tt["equity_entry_est"]
    viol = tt[tt["loss_pct_eq"] > 0.02]
    over_plan = tt[tt["R"] < -1.1]
    t = tt
    costs = float(t["fee_paid"].sum() - t["funding"].sum())
    gross = float(t["gross"].sum())
    gross_win = float(t.loc[t["gross"] > 0, "gross"].sum())

    def grp(col):
        rows = []
        for k, g in t.groupby(col, dropna=False):
            rr = g["R"].dropna()
            rows.append(dict(key=str(k), n=int(len(g)), exp_R=float(rr.mean()) if len(rr) else None,
                             sum_R=float(rr.sum()) if len(rr) else None, pf=pf(g["profit_abs"]),
                             win_rate=float((g["profit_abs"] > 0).mean()), profit_abs=float(g["profit_abs"].sum()),
                             fees=float(g["fee_paid"].sum()), funding=float(g["funding"].sum())))
        return rows

    res.update(
        expectancy_R=float(t["R"].mean()), n_R=int(r_ok.sum()), median_R=float(t["R"].median()),
        profit_factor=pf(t["profit_abs"]), profit_abs=float(t["profit_abs"].sum()),
        profit_pct=float(stats["profit_total"] * 100),
        max_dd_pct=float(stats["max_drawdown_account"] * 100), max_dd_abs=float(stats["max_drawdown_abs"]),
        avg_duration=str(stats["holding_avg"]), avg_duration_min=float(stats["holding_avg_s"]) / 60,
        fees_total=float(t["fee_paid"].sum()), fee_only=float(t["fee_only"].sum()), slip_approx=float(t["slip_paid"].sum()),
        funding_net=float(t["funding"].sum()), funding_paid=float(-t["funding"].sum()),
        costs_total=costs, gross_pnl=gross, gross_winners=gross_win,
        costs_over_gross=(costs / gross if gross > 0 else None),
        costs_over_gross_winners=(costs / gross_win if gross_win > 0 else None),
        win_rate=float((t["profit_abs"] > 0).mean()), freqtrade_pf=float(stats["profit_factor"]),
        backtest_start=str(stats["backtest_start"]), backtest_end=str(stats["backtest_end"]),
        by_setup=grp("enter_tag"), by_regime=grp("regime"), by_pair=grp("pair"), by_side=grp("side"),
        by_exit=grp("exit_reason"),
        unmatched_ledger_rows=int((~r_ok).sum()),
        riskcheck=dict(
            n_viol_2pct=int(len(viol)), max_loss_pct_eq=float(t["loss_pct_eq"].max()),
            n_loss_gt_1p1x_actual_risk=int(len(over_plan)), n_R_lt_minus1=int((tt["R"] < -1.0).sum()), min_R=float(t["R"].min()),
            viol=viol[["pair", "side", "enter_tag", "open_date", "close_date", "exit_reason", "profit_abs", "equity_entry_est",
                       "loss_pct_eq", "R", "funding"]].astype(str).to_dict("records")[:50],
            over_plan=over_plan[["pair", "side", "enter_tag", "open_date", "exit_reason", "profit_abs", "R", "loss_pct_eq"]]
            .astype(str).to_dict("records")[:50]),
    )
    t.drop(columns=["orders"], errors="ignore").to_csv(out / "trades_enriched.csv", index=False)
    return res


def ledger_check(out: Path) -> dict:
    """Defter vs freqtrade islem listesi: sayi, PnL, R ve regime tutarliligi."""
    import sqlite3
    t = pd.read_csv(out / "trades_enriched.csv")
    c = sqlite3.connect(out / "ledger.sqlite")
    l = pd.read_sql("SELECT * FROM v_trades", c)
    d = dict(ft_trades=len(t), ledger_entries=len(l), ledger_closed=int(l["exit_ts"].notna().sum()),
             ledger_pnl=float(l["realized_pnl"].sum()), ft_pnl=float(t["profit_abs"].sum()),
             ledger_open_unclosed=int(l["exit_ts"].isna().sum()))
    d["pnl_total_diff"] = d["ledger_pnl"] - d["ft_pnl"]
    d["unmatched_ft"] = int(t["pnl_ledger"].isna().sum())
    d["unmatched_ledger"] = int(len(l) - t["pnl_ledger"].notna().sum())
    mm = t[t["pnl_ledger"].notna()].copy()
    mm["pnl_diff"] = mm["pnl_ledger"] - mm["profit_abs"]
    d["max_abs_pnl_diff"] = float(mm["pnl_diff"].abs().max())
    d["mean_abs_pnl_diff"] = float(mm["pnl_diff"].abs().mean())
    d["n_pnl_diff_gt_0.01"] = int((mm["pnl_diff"].abs() > 0.01).sum())
    d["n_pnl_diff_gt_0.10"] = int((mm["pnl_diff"].abs() > 0.10).sum())
    # fark kaynagi: funding anlik goruntusu mu?
    lf = l.copy()
    lf["open_date"] = pd.to_datetime(lf["entry_ts"], utc=True)
    lf["pair"] = lf["pair"].where(lf["pair"].str.contains(":"), lf["pair"] + ":USDT")
    mm["open_date"] = pd.to_datetime(mm["open_date"], utc=True)
    x = mm.merge(lf[["pair", "open_date", "funding_paid", "gross_pnl", "fee_entry", "fee_exit"]], on=["pair", "open_date"])
    d["max_abs_gross_diff"] = float((x["gross_pnl"] - x["gross"]).abs().max())
    d["max_abs_fee_diff"] = float((x["fee_entry"] + x["fee_exit"] - x["fee_paid"]).abs().max())
    d["max_abs_funding_diff"] = float((-x["funding_paid"] - x["funding"]).abs().max())
    d["R_ledger_vs_actual_mean_abs"] = float((mm["r_ledger"] - mm["R"]).abs().mean())
    d["R_ledger_vs_actual_max_abs"] = float((mm["r_ledger"] - mm["R"]).abs().max())
    d["ledger_exp_R"] = float(l["r_multiple"].mean())
    d["actual_exp_R"] = float(t["R"].mean())
    d["planned_risk_over_actual_minmax"] = [float((mm["planned_risk"] / mm["risk_amt"]).min()),
                                            float((mm["planned_risk"] / mm["risk_amt"]).max())]
    d["ledger_exit_reasons"] = l["exit_reason"].value_counts().to_dict()
    d["mismatch_rows"] = mm.loc[mm["pnl_diff"].abs() > 0.10, ["pair", "open_date", "profit_abs", "pnl_ledger", "pnl_diff"]] \
        .astype(str).head(20).to_dict("records")
    return d


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--id", required=True)
    ap.add_argument("--period", required=True, help="IS | WF | YYYYMMDD-YYYYMMDD")
    ap.add_argument("--fee-mult", type=float, default=2.0)
    ap.add_argument("--slip-bps", type=float, default=2.0)
    ap.add_argument("--tf", default="1h", choices=["1h", "15m"])
    ap.add_argument("--params", default="")
    ap.add_argument("--notes", default="")
    ap.add_argument("--analyze-only", action="store_true")
    a = ap.parse_args()
    RUNS.mkdir(exist_ok=True)
    fee = round(BASE_FEE * a.fee_mult + a.slip_bps / 1e4, 8)
    out = BT_DIR / a.id if a.analyze_only else build_and_run(a)
    res = analyze(out, a, fee)
    if True:
        res["ledger_check"] = ledger_check(out)
    meta = dict(id=a.id, timestamp=datetime.now(timezone.utc).isoformat(timespec="seconds"), git_commit=git_commit(),
                strategy="TraderV1", params=json.loads(a.params) if a.params else {}, period=a.period,
                timerange=PERIODS.get(a.period, a.period), fee_mult=a.fee_mult, slip_bps=a.slip_bps, fee_eff=fee,
                trigger_tf=a.tf, notes=a.notes)
    (RUNS / f"{a.id}.json").write_text(json.dumps({**meta, **res}, indent=1, default=str))
    print(f"[{a.id}] n={res.get('n_trades')} expR={res.get('expectancy_R')} PF={res.get('profit_factor')} "
          f"DD={res.get('max_dd_pct')}", flush=True)


if __name__ == "__main__":
    main()
