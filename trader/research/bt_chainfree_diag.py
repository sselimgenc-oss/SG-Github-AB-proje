#!/usr/bin/env python3
"""Zincirsiz tani (06-crosscheck-sonuc.md, mentor karari adim 4): B duzeyindeki boyut farklarinin SAF zincir (ozsermaye
sapmasi) oldugunu kanitlar. Her referans girisi icin motorun boyutlandirmasi (`risk.check_entry`, giris ani acik
pozisyonlar referanstan) REFERANSIN kendi `equity_entry_est` degeriyle yeniden hesaplanir ve freqtrade stake->miktar kesmesi
uygulanir. Sonuc referans `amount` ile >= %99.5 uyusuyorsa, motor-referans boyut farki yalniz ozsermaye farkindan gelir.
Kullanim: python research/bt_chainfree_diag.py --id 1h_IS_f1_s0 [--engine-dir D] [--out-dir D]
Cikti: <out>/<id>_chainfree.json + ozet satiri. Freqtrade calistirilmaz."""
from __future__ import annotations

import argparse
import json
import math
import sys
from decimal import ROUND_DOWN, Decimal
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from trader_core import risk as K  # noqa: E402
from trader_engine.marketdata.sources import HistoricalSource  # noqa: E402
import bt_crosscheck as X  # noqa: E402

SIZE_TOL = 0.005


def trunc_step(x: float, step: float) -> float:
    d, q = Decimal(repr(float(x))), Decimal(repr(float(step)))
    return float((d / q).to_integral_value(rounding=ROUND_DOWN) * q)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(allow_abbrev=False)
    ap.add_argument("--id", required=True)
    ap.add_argument("--engine-dir", default=None)
    ap.add_argument("--out-dir", default=str(ROOT / "research" / "crosscheck"))
    ap.add_argument("--history-dir", default=str(ROOT / "user_data" / "data" / "binance" / "futures"))
    a = ap.parse_args(argv)
    ref = ROOT / "user_data" / "backtest_results" / a.id
    eng = Path(a.engine_dir) if a.engine_dir else ROOT / "var" / "backtests" / f"{a.id}_compat"
    t = pd.read_csv(ref / "trades_enriched.csv")
    t["pairc"] = t["pair"].map(X.canon)
    t["open_ts"] = pd.to_datetime(t["open_date"], utc=True)
    t["close_ts"] = pd.to_datetime(t["close_date"], utc=True)
    t = t.sort_values("open_ts").reset_index(drop=True)
    rdec, _ = X.read_ledger(ref)
    rdec = rdec[rdec["final_action"] == "entered"]
    dmargin = {(X.canon(p), side, pd.Timestamp(ts)): m
               for p, side, ts, m in zip(rdec["pair"], rdec["side"], rdec["bar_close_ts"], rdec["size_margin"])}
    et = pd.read_csv(eng / "trades.csv")
    et["key"] = list(zip(et["pair"], et["side"], pd.to_datetime(et["entry_ts"], utc=True)))
    emap = {k: q for k, q in zip(et["key"], et["qty"])}
    src = HistoricalSource(a.history_dir, granularity="15m", synthetic_rules=True)
    lev = K.LOCKED_CFG.min_leverage
    rows, n_pred, n_eng = [], 0, 0
    n_ek = 0
    n_cut = 0
    for r in t.itertuples():
        side = "short" if r.is_short else "long"
        eq = float(r.equity_entry_est)
        opens = t[(t["open_ts"] < r.open_ts) & (t["close_ts"] > r.open_ts)]
        pos = [K.OpenPosition(o.pairc, "short" if o.is_short else "long", float(o.planned_risk), float(o.stake_amount))
               for o in opens.itertuples()]
        rules = src.rules(r.pairc)
        cand = K.Candidate(r.pairc, side, float(r.open_rate), float(r.planned_stop), float(lev), rules.step, rules.min_notional)
        dec = K.check_entry(K.AccountState(equity=eq, day_start_equity=eq, open_positions=pos), cand, K.LOCKED_CFG)
        pred = trunc_step((dec.size.margin / float(r.open_rate)) * lev, rules.step) if dec.allowed else None
        ok = pred is not None and abs(pred - r.amount) <= SIZE_TOL * max(r.amount, 1e-12) + 1e-12
        n_pred += bool(ok)
        eq_q = emap.get((r.pairc, side, r.open_ts))
        if eq_q is not None:
            n_ek += 1
            n_eng += abs(eq_q - r.amount) <= SIZE_TOL * max(r.amount, 1e-12) + 1e-12
        # referansin KENDI karar marjininden beklenen miktar (ledger size_margin): daha azsa freqtrade stake'i kesmistir
        dm = dmargin.get((r.pairc, side, r.open_ts))
        own = trunc_step((dm / float(r.open_rate)) * lev, rules.step) if dm else None
        cut = own is not None and r.amount < own * (1 - SIZE_TOL) - 1e-12
        n_cut += bool(cut and not ok)
        rows.append(dict(pair=r.pairc, side=side, entry_ts=str(r.open_ts), ref_amount=float(r.amount), pred_amount=pred,
                         ref_own_decision_amount=own, engine_amount=eq_q, allowed=bool(dec.allowed), ok=bool(ok),
                         ref_stake_cut=bool(cut)))
    n = len(t)
    out = dict(id=a.id, n_ref=n, n_pred_match=int(n_pred), pred_match_pct=100.0 * n_pred / n, n_ref_stake_cut=int(n_cut),
               explained_pct=100.0 * (n_pred + n_cut) / n, n_engine_key=n_ek,
               n_engine_match=int(n_eng), engine_match_of_ref_pct=100.0 * n_eng / n,
               engine_match_of_keyed_pct=100.0 * n_eng / max(n_ek, 1),
               unmatched=[x for x in rows if not x["ok"] and not x["ref_stake_cut"]][:80])
    Path(a.out_dir).mkdir(parents=True, exist_ok=True)
    (Path(a.out_dir) / f"{a.id}_chainfree.json").write_text(json.dumps(out, indent=1, default=str))
    print(f"[{a.id}] ref={n} zincirsiz-tahmin eslesme {n_pred}/{n} ({out['pred_match_pct']:.2f}%) + referans stake kesmesi {n_cut} "
          f"=> aciklanan {out['explained_pct']:.2f}%; motor boyutu (anahtar eslesen {n_ek}) "
          f"{n_eng}/{n} ({out['engine_match_of_ref_pct']:.2f}%)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
