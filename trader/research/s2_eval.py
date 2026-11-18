#!/usr/bin/env python3
"""S2 olcum araci (docs/ml/s2-on-kayit.md §2, §4): bir motor kosu dizininden CANLI-K1 madde 1-3 kontrollerini
ve maliyet dokumunu hesaplar; `<kosu>/s2_eval.json` yazar.

Kullanim: PYTHONPATH=src python research/s2_eval.py <kosu_dizini> --n-registered <k>
"""
from __future__ import annotations

import argparse
import json
import math
import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from trader_core.stats.stats import (  # noqa: E402
    deflated_sharpe,
    optimal_block_length,
    return_moments,
    stationary_bootstrap_indices,
)
from trader_engine.metrics import loss_at_stop  # noqa: E402

SCHEMA = "s2-eval/1"
FULL_START = pd.Timestamp("2021-01-01", tz="UTC")
FULL_END = pd.Timestamp("2026-05-01", tz="UTC")
EXAM_START = pd.Timestamp("2022-01-06", tz="UTC")
EXAM_END = FULL_END
SLICE_BOUNDS = [pd.Timestamp(x, tz="UTC") for x in
                ("2022-01-06", "2023-02-04", "2024-03-04", "2025-04-02", "2026-05-01")]
EXPLORE_CUT = pd.Timestamp("2024-01-01", tz="UTC")
N_BOOT = 2000
CODES = ["K1-1a", "K1-1b", "K1-1c", "K1-1d", "K1-1e", "K1-1f", "K1-1g", "K1-2", "K1-3"]


def n_trials(k: int) -> int:
    return max(10, 1 + int(k))


def _ts(x) -> pd.Timestamp:
    t = pd.Timestamp(x)
    return t.tz_localize("UTC") if t.tzinfo is None else t.tz_convert("UTC")


def exam_slice(entry_ts) -> int | None:
    t = _ts(entry_ts)
    if not (SLICE_BOUNDS[0] <= t < SLICE_BOUNDS[-1]):
        return None
    for i in range(4):
        if SLICE_BOUNDS[i] <= t < SLICE_BOUNDS[i + 1]:
            return i
    return None


def _load_trades(run_dir: Path) -> pd.DataFrame:
    t = pd.read_csv(run_dir / "trades.csv")
    t = t[t["exit_ts"].notna() & (t["exit_ts"].astype(str).str.len() > 0)].copy()
    t["entry_dt"] = pd.to_datetime(t["entry_ts"], utc=True, format="ISO8601")
    for c in ("qty", "entry_price", "exit_price", "planned_stop", "realized_pnl", "gross_pnl", "fee_entry",
              "fee_exit", "funding_paid", "slip_cost"):
        t[c] = pd.to_numeric(t[c], errors="coerce")
    den = np.array([loss_at_stop(q, e, s) for q, e, s in zip(t["qty"], t["entry_price"], t["planned_stop"])],
                   dtype=float)
    if len(den) and not (np.isfinite(den).all() and (den > 0).all()):
        raise ValueError("loss_at_stop non-positive or non-finite for some trade")
    t["den"] = den
    t["R"] = t["realized_pnl"].to_numpy(float) / den if len(den) else np.array([], dtype=float)
    return t.reset_index(drop=True)


def _mean(x) -> float:
    x = np.asarray(x, dtype=float)
    return float(x.mean()) if x.size else float("nan")


def _pf(pnl) -> float:
    pnl = np.asarray(pnl, dtype=float)
    w = float(pnl[pnl > 0].sum())
    l = float(-pnl[pnl < 0].sum())
    if l == 0:
        return float("inf") if w > 0 else 0.0
    return w / l


def _costs(t: pd.DataFrame) -> dict:
    n = len(t)
    comm = float((t["fee_entry"] + t["fee_exit"]).sum())
    slip = float(t["slip_cost"].sum())
    fund = float(t["funding_paid"].sum())
    gross = float((t["gross_pnl"] + t["slip_cost"]).sum())
    net = float(t["realized_pnl"].sum())
    notional = float((t["qty"] * t["entry_price"]).sum())

    def bp(x):
        return x / notional * 1e4 if notional > 0 else float("nan")

    def rr(s):
        return _mean(s / t["den"]) if n else float("nan")

    return {
        "commission_usd": comm, "slippage_usd": slip, "funding_usd": fund, "gross_pre_slip_usd": gross,
        "net_usd": net, "n_trades": n,
        "bp_per_round_trip": {"commission": bp(comm), "slippage": bp(slip), "funding": bp(fund)},
        "r_per_trade": {
            "commission": rr(t["fee_entry"] + t["fee_exit"]), "slippage": rr(t["slip_cost"]),
            "funding": rr(t["funding_paid"]), "gross_pre_slip": rr(t["gross_pnl"] + t["slip_cost"]),
            "net": rr(t["realized_pnl"]),
        },
    }


def _full_period(t: pd.DataFrame) -> dict:
    return {"n_trades": len(t), "mean_R": _mean(t["R"]),
            "median_R": float(np.median(t["R"])) if len(t) else float("nan"),
            "profit_factor": _pf(t["realized_pnl"]), "net_usd": float(t["realized_pnl"].sum())}


def _daily(w: pd.DataFrame):
    days = pd.date_range(EXAM_START, EXAM_END - pd.Timedelta(days=1), freq="D", tz="UTC")
    d = w["entry_dt"].dt.floor("D")
    s = w.groupby(d)["R"].sum().reindex(days, fill_value=0.0).to_numpy(float)
    n = w.groupby(d)["R"].count().reindex(days, fill_value=0).to_numpy(float)
    return s, n


def _k11b(s: np.ndarray, n: np.ndarray) -> tuple[float, float]:
    """(%10 yuzdelik, %5 yuzdelik) of sum(s)/sum(n) under stationary bootstrap (seed 0)."""
    L = optimal_block_length(s)["stationary"]
    mb = max(1.0, float(L)) if np.isfinite(L) else 1.0
    rng = np.random.default_rng(0)
    idx = stationary_bootstrap_indices(len(s), N_BOOT, mb, rng)
    S = s[idx].sum(axis=1)
    N = n[idx].sum(axis=1)
    ok = N > 0
    if not ok.any():
        return float("nan"), float("nan")
    stat = S[ok] / N[ok]
    return float(np.percentile(stat, 10)), float(np.percentile(stat, 5))


def _chk(code, value, threshold, ok, **extra) -> dict:
    v = None if (isinstance(value, float) and math.isinf(value)) else value
    d = {"code": code, "value": v, "threshold": threshold, "ok": bool(ok)}
    d.update(extra)
    return d


def _checks(t: pd.DataFrame, pairs: list[str], n_tr: int) -> list[dict]:
    w = t[(t["entry_dt"] >= EXAM_START) & (t["entry_dt"] < EXAM_END)]
    out = []
    mean_r = _mean(w["R"])
    out.append(_chk("K1-1a", mean_r, "> 0", mean_r > 0))
    s, n = _daily(w)
    p10, p05 = _k11b(s, n)
    out.append(_chk("K1-1b", p10, "> 0", p10 > 0, p05=p05))
    pf = _pf(w["realized_pnl"])
    out.append(_chk("K1-1c", pf, "> 1", pf > 1))
    sl = w["entry_dt"].map(exam_slice)
    pos = sum(1 for i in range(4) if _mean(w.loc[sl == i, "R"]) > 0)
    out.append(_chk("K1-1d", pos, ">= 3", pos >= 3))
    late = w[w["entry_dt"] >= EXPLORE_CUT]
    m_late = _mean(late["R"])
    out.append(_chk("K1-1e", m_late, "> 0", m_late > 0))
    out.append(_chk("K1-1f", len(w), ">= 800", len(w) >= 800))
    per_pair = {p: _mean(w.loc[w["pair"] != p, "R"]) for p in pairs}
    mn = min(per_pair.values()) if per_pair else float("nan")
    out.append(_chk("K1-1g", mn, "> 0 for all 10 leave-one-out", bool(per_pair) and all(v > 0 for v in per_pair.values()),
                    per_pair=per_pair))
    extra = (w["fee_entry"] + w["fee_exit"]) + 0.0005 * w["qty"] * (w["entry_price"] + w["exit_price"])
    r_stress = _mean((w["realized_pnl"] - extra) / w["den"])
    out.append(_chk("K1-2", r_stress, ">= -0.05", r_stress >= -0.05))
    sd = float(np.std(s, ddof=1)) if len(s) > 1 else 0.0
    sr = float(np.mean(s) / sd) if sd > 0 else 0.0
    skew, kurt = return_moments(s)
    dsr = float(deflated_sharpe(sr, len(s), skew, kurt, n_trials=n_tr))
    out.append(_chk("K1-3", dsr, ">= 0.95", dsr >= 0.95, sr=sr, n_days=len(s)))
    return out


def evaluate(run_dir, n_registered: int) -> dict:
    run_dir = Path(run_dir)
    meta = json.loads((run_dir / "meta.json").read_text())
    start, end = _ts(meta["period"][0]), _ts(meta["period"][1])
    if end > FULL_END:
        raise ValueError(f"period end {end} is after {FULL_END} (locked window)")
    t = _load_trades(run_dir)
    N = n_trials(n_registered)
    res = {"schema": SCHEMA, "run_id": meta.get("id"), "git_commit": meta.get("git_commit"), "n_trials": N}
    if start == FULL_START and end == FULL_END:
        res["mode"] = "full"
        res["window"] = {"start": EXAM_START.isoformat(), "end": EXAM_END.isoformat(),
                         "slices": [[SLICE_BOUNDS[i].isoformat(), SLICE_BOUNDS[i + 1].isoformat()] for i in range(4)]}
        checks = _checks(t, list(meta["pairs"]), N)
        assert [c["code"] for c in checks] == CODES
        res["checks"] = checks
        res["passed"] = all(c["ok"] for c in checks)
        res["first_failure"] = next((c["code"] for c in checks if not c["ok"]), None)
        res["costs"] = _costs(t)
        res["full_period"] = _full_period(t)
        w = t[(t["entry_dt"] >= EXAM_START) & (t["entry_dt"] < EXAM_END)]
        res["exam_window"] = {"n_trades": len(w), "mean_R": _mean(w["R"])}
    else:
        res["mode"] = "explore"
        e = t[t["entry_dt"] < EXPLORE_CUT]
        res["window"] = {"start": start.isoformat(), "end": min(end, EXPLORE_CUT).isoformat()}
        res["costs"] = _costs(e)
        res["full_period"] = _full_period(e)
    (run_dir / "s2_eval.json").write_text(json.dumps(res, indent=1, default=float))
    return res


def format_table(res: dict) -> str:
    lines = [f"S2 eval  run={res['run_id']}  mode={res['mode']}  commit={res['git_commit']}  N={res['n_trials']}"]
    for c in res.get("checks", []):
        v = c["value"]
        vs = "inf" if v is None else (f"{v:.5f}" if isinstance(v, float) else str(v))
        lines.append(f"  {c['code']}  value={vs:>12}  thr={c['threshold']:<28} {'OK' if c['ok'] else 'FAIL'}")
    if "passed" in res:
        lines.append(f"  -> {'GECTI' if res['passed'] else 'KALDI'}  first_failure={res['first_failure']}")
    cs = res["costs"]
    lines.append(f"  costs: n={cs['n_trades']} commission={cs['commission_usd']:.2f} slippage={cs['slippage_usd']:.2f} "
                 f"funding={cs['funding_usd']:.2f} gross_pre_slip={cs['gross_pre_slip_usd']:.2f} net={cs['net_usd']:.2f}")
    lines.append(f"  bp/rt: {cs['bp_per_round_trip']}")
    lines.append(f"  R/trade: {cs['r_per_trade']}")
    lines.append(f"  full_period: {res['full_period']}")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(allow_abbrev=False)
    ap.add_argument("run_dir")
    ap.add_argument("--n-registered", type=int, required=True)
    try:
        a = ap.parse_args(argv)
    except SystemExit as e:
        return 2 if e.code not in (0, None) else 0
    try:
        if a.n_registered < 0:
            raise ValueError("--n-registered must be >= 0")
        res = evaluate(a.run_dir, a.n_registered)
    except (ValueError, OSError, KeyError) as e:
        print(f"s2_eval hata: {e}", file=sys.stderr)
        return 2
    print(format_table(res))
    return 0


if __name__ == "__main__":
    sys.exit(main())
