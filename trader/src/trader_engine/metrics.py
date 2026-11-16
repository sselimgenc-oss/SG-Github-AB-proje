"""Backtest metrikleri (06 §4): `research/run_bt.py::analyze` anahtarlariyla ayni, freqtrade'e bagimsiz; ledger'dan turetilir.
Saf islevler (pandas serbest). Acik pozisyonlar (`exit_ts` bos) disarida birakilir."""
from __future__ import annotations

import math
import sqlite3
from collections.abc import Mapping

import numpy as np
import pandas as pd

from trader_core import risk as K

# run_bt.analyze anahtar kumesi (freqtrade_pf / unmatched_ledger_rows yerine `engine`)
METRIC_KEYS = (
    "n_trades", "expectancy_R", "n_R", "median_R", "profit_factor", "profit_abs", "profit_pct", "max_dd_pct",
    "max_dd_abs", "avg_duration", "avg_duration_min", "fees_total", "fee_only", "slip_approx", "funding_net",
    "funding_paid", "costs_total", "gross_pnl", "gross_winners", "costs_over_gross", "costs_over_gross_winners",
    "win_rate", "backtest_start", "backtest_end", "by_setup", "by_regime", "by_pair", "by_side", "by_exit",
    "riskcheck", "engine")
RISKCHECK_KEYS = ("n_viol_2pct", "max_loss_pct_eq", "n_loss_gt_1p1x_actual_risk", "n_R_lt_minus1", "min_R",
                  "viol", "over_plan")
TRADES_COLUMNS = (
    "trade_id", "pair", "side", "setup", "regime", "entry_ts", "exit_ts", "entry_price", "exit_price", "qty", "leverage",
    "planned_entry", "planned_stop", "planned_target", "exit_reason", "planned_exit", "planned_risk", "equity_at_entry",
    "gross_pnl", "fee_entry", "fee_exit", "funding_paid", "realized_pnl", "r_multiple", "mfe_r", "mae_r", "bars_held",
    "excursion_tf", "slippage_entry", "slippage_exit", "slip_cost", "decision_id", "param_version_id")


def pf(x: pd.Series) -> float:
    """Profit factor: toplam pozitif / -toplam negatif; ikisi de yoksa nan; kayip yoksa inf."""
    x = pd.Series(x, dtype=float)
    w, l = float(x[x > 0].sum()), -float(x[x < 0].sum())
    return w / l if l > 0 else (float("inf") if w > 0 else float("nan"))


def loss_at_stop(qty: float, entry: float, stop: float) -> float:
    return K.loss_at_stop(qty, entry, stop, K.LOCKED_CFG)


def max_drawdown(profits: pd.Series | np.ndarray, wallet_start: float) -> tuple[float, float]:
    """Gerceklesmis bakiye egrisi (`wallet_start + cumsum`) uzerinde tepe-dip: (pct, abs). Egri baslangic degerini icerir."""
    p = np.asarray(profits, dtype=float)
    curve = np.concatenate([[float(wallet_start)], float(wallet_start) + np.cumsum(p)])
    peak = np.maximum.accumulate(curve)
    dd_abs = peak - curve
    i = int(np.argmax(dd_abs)) if len(dd_abs) else 0
    if len(dd_abs) == 0 or dd_abs[i] <= 0:
        return 0.0, 0.0
    return float(dd_abs[i] / peak[i] * 100.0), float(dd_abs[i])


def read_ledger_trades(ledger_path) -> pd.DataFrame:
    """v_trades (v2) -> DataFrame; salt okunur."""
    c = sqlite3.connect(f"file:{ledger_path}?mode=ro", uri=True)
    try:
        return pd.read_sql("SELECT * FROM v_trades ORDER BY trade_id", c)
    finally:
        c.close()


def enrich_trades(t: pd.DataFrame, equity_at_entry: Mapping[int, float] | None = None) -> pd.DataFrame:
    """trades.csv sutunlari: `equity_at_entry` (karar ani) ve `slip_cost` (gercek dolum - ham fiyat farki) eklenir."""
    t = t.copy()
    eq = equity_at_entry or {}
    t["equity_at_entry"] = [float(eq[int(i)]) if int(i) in eq else float("nan") for i in t["trade_id"]]
    se = t["slippage_entry"].fillna(0.0)
    sx = t["slippage_exit"].fillna(0.0)
    pex = t["planned_exit"].where(t["planned_exit"].notna(), t["exit_price"]).fillna(0.0)
    t["slip_cost"] = t["qty"] * t["planned_entry"] * se + t["qty"] * pex * sx
    cols = [c for c in TRADES_COLUMNS if c in t.columns]
    return t[cols]


def _grp(t: pd.DataFrame, col: str) -> list[dict]:
    rows = []
    for k, g in t.groupby(col, dropna=False):
        rr = g["R"].dropna()
        rows.append(dict(key=str(k), n=int(len(g)), exp_R=float(rr.mean()) if len(rr) else None,
                         sum_R=float(rr.sum()) if len(rr) else None, pf=pf(g["profit_abs"]),
                         win_rate=float((g["profit_abs"] > 0).mean()), profit_abs=float(g["profit_abs"].sum()),
                         fees=float(g["fee_paid"].sum()), funding=float(g["funding"].sum())))
    return rows


def compute_metrics(trades: pd.DataFrame, *, wallet_start: float, slip_bps: float | None = None,
                    fill_model: str = "native", period: tuple[str, str] | None = None,
                    engine: Mapping | None = None) -> dict:
    """`slip_bps` verilirse (uyum kipi) kayma komisyona katilmistir ve `slip_paid = qty*(entry+exit)*slip_bps/1e4`;
    aksi halde (native) `slip_paid = trades.csv:slip_cost`."""
    t = trades[trades["exit_ts"].notna()].copy() if len(trades) else trades.copy()
    res: dict = dict(n_trades=int(len(t)))
    eng = dict(engine or {})
    eng.setdefault("fill_model", fill_model)
    if period:
        res["backtest_start"], res["backtest_end"] = period
    if t.empty:
        res["engine"] = eng
        return res
    t = t.sort_values(["exit_ts", "trade_id"]).reset_index(drop=True)
    t["profit_abs"] = t["realized_pnl"].astype(float)
    t["fee_paid"] = t["fee_entry"] + t["fee_exit"]
    if slip_bps is not None:
        t["slip_paid"] = t["qty"] * (t["entry_price"] + t["exit_price"]) * (slip_bps / 1e4)
    else:
        t["slip_paid"] = t["slip_cost"] if "slip_cost" in t else 0.0
    t["fee_only"] = t["fee_paid"] - t["slip_paid"]
    t["funding"] = -t["funding_paid"].astype(float)        # + alinan, - odenen (freqtrade funding_fees isareti)
    t["gross"] = t["gross_pnl"].astype(float)
    t["risk_amt"] = [loss_at_stop(q, e, s) if np.isfinite(s) else np.nan
                     for q, e, s in zip(t["qty"], t["entry_price"], t["planned_stop"])]
    t["R"] = t["profit_abs"] / t["risk_amt"]
    r_ok = t["R"].notna()
    eq = t["equity_at_entry"] if "equity_at_entry" in t else pd.Series(float(wallet_start), index=t.index)
    t["equity_at_entry"] = eq
    t["loss"] = -t["profit_abs"]
    t["loss_pct_eq"] = t["loss"] / eq
    viol = t[t["loss_pct_eq"] > 0.02]
    over_plan = t[t["R"] < -1.1]
    costs = float(t["fee_paid"].sum() - t["funding"].sum())
    gross = float(t["gross"].sum())
    gross_win = float(t.loc[t["gross"] > 0, "gross"].sum())
    dd_pct, dd_abs = max_drawdown(t["profit_abs"].to_numpy(), wallet_start)
    dur = pd.to_datetime(t["exit_ts"], utc=True) - pd.to_datetime(t["entry_ts"], utc=True)
    mean_dur = dur.mean()
    res.update(
        expectancy_R=float(t["R"].mean()), n_R=int(r_ok.sum()), median_R=float(t["R"].median()),
        profit_factor=pf(t["profit_abs"]), profit_abs=float(t["profit_abs"].sum()),
        profit_pct=float(t["profit_abs"].sum() / wallet_start * 100.0),
        max_dd_pct=dd_pct, max_dd_abs=dd_abs,
        avg_duration=str(mean_dur.floor("s").to_pytimedelta()), avg_duration_min=float(mean_dur.total_seconds() / 60.0),
        fees_total=float(t["fee_paid"].sum()), fee_only=float(t["fee_only"].sum()), slip_approx=float(t["slip_paid"].sum()),
        funding_net=float(t["funding"].sum()), funding_paid=float(-t["funding"].sum()),
        costs_total=costs, gross_pnl=gross, gross_winners=gross_win,
        costs_over_gross=(costs / gross if gross > 0 else None),
        costs_over_gross_winners=(costs / gross_win if gross_win > 0 else None),
        win_rate=float((t["profit_abs"] > 0).mean()),
        by_setup=_grp(t, "setup"), by_regime=_grp(t, "regime"), by_pair=_grp(t, "pair"), by_side=_grp(t, "side"),
        by_exit=_grp(t, "exit_reason"))
    vcols = ["pair", "side", "setup", "entry_ts", "exit_ts", "exit_reason", "profit_abs", "equity_at_entry",
             "loss_pct_eq", "R", "funding"]
    res["riskcheck"] = dict(
        n_viol_2pct=int(len(viol)),
        max_loss_pct_eq=float(t["loss_pct_eq"].max()),
        n_loss_gt_1p1x_actual_risk=int(len(over_plan)), n_R_lt_minus1=int((t["R"] < -1.0).sum()),
        min_R=float(t["R"].min()),
        viol=viol[vcols].astype(str).to_dict("records")[:50],
        over_plan=over_plan[["pair", "side", "setup", "entry_ts", "exit_reason", "profit_abs", "R", "loss_pct_eq"]]
        .astype(str).to_dict("records")[:50])
    if "backtest_start" not in res:
        res["backtest_start"], res["backtest_end"] = str(t["entry_ts"].min()), str(t["exit_ts"].max())
    res["engine"] = eng
    return res


def is_finite(x) -> bool:
    return isinstance(x, (int, float)) and math.isfinite(x)
