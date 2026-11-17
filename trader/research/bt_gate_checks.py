#!/usr/bin/env python3
"""Capraz dogrulama kapisi yardimcilari (tasarim-kararlari.md "Capraz dogrulama kapisi", 17 Kasim; yalniz tani, salt okunur).
  fee      : ucret / nominal, anahtari eslesen islemlerde ref ve motor (adim 1)
  funding  : anahtari eslesen islemlerde funding toplami, `funding_boundary` satirlari haric (adim 2)
  stakecut : freqtrade'in kendi stake kisma kurali, referans veriden (adim 5; uygulanmaz)
  closing  : native defterde `closing` pozisyon varken reddedilen giris sayisi (adim 6)
Kullanim: python research/bt_gate_checks.py fee|funding --engine-root var/bt_lag
          python research/bt_gate_checks.py stakecut
          python research/bt_gate_checks.py closing --ledger var/backtests/1h_IS_f1_s0_native_mark/ledger.sqlite
HOLDOUT'a dokunmaz; freqtrade calistirilmaz."""
from __future__ import annotations

import argparse
import json
import sqlite3
import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(Path(__file__).resolve().parent))
import bt_crosscheck as X  # noqa: E402
import bt_chainfree_diag as C  # noqa: E402

RUNS = ["1h_IS_f1_s0", "1h_WF_f1_s0", "15m_IS_f1_s0", "1h_IS_f2_s5"]


def _matched(run: str, eng_root: Path) -> pd.DataFrame:
    ref = X.REF_ROOT / run
    _, rt = X.read_ledger(ref)
    _, et = X.read_ledger(eng_root / f"{run}_compat")
    for d in (rt, et):
        d["key"] = list(zip(d["pair"], d["side"], pd.to_datetime(d["entry_ts"], utc=True)))
    m = rt.merge(et, on="key", suffixes=("_r", "_e"))
    return m


def fee(eng_root: Path) -> list[dict]:
    out = []
    for run in RUNS:
        m = _matched(run, eng_root)
        rn = m["qty_r"] * (m["entry_price_r"] + m["exit_price_r"])
        en = m["qty_e"] * (m["entry_price_e"] + m["exit_price_e"])
        rr = (m["fee_entry_r"] + m["fee_exit_r"]) / rn
        er = (m["fee_entry_e"] + m["fee_exit_e"]) / en
        legs_r = pd.concat([m["fee_entry_r"] / (m["qty_r"] * m["entry_price_r"]), m["fee_exit_r"] / (m["qty_r"] * m["exit_price_r"])])
        legs_e = pd.concat([m["fee_entry_e"] / (m["qty_e"] * m["entry_price_e"]), m["fee_exit_e"] / (m["qty_e"] * m["exit_price_e"])])
        out.append(dict(run=run, n_matched=len(m), ref_rate_min=float(rr.min()), ref_rate_max=float(rr.max()),
                        eng_rate_min=float(er.min()), eng_rate_max=float(er.max()), max_abs_rate_diff=float((rr - er).abs().max()),
                        leg_ref_min=float(legs_r.min()), leg_ref_max=float(legs_r.max()), leg_eng_min=float(legs_e.min()),
                        leg_eng_max=float(legs_e.max())))
    return out


def funding(eng_root: Path, xc_dir: Path) -> list[dict]:
    out = []
    for run in RUNS:
        m = _matched(run, eng_root)
        j = json.loads((xc_dir / f"{run}.json").read_text())
        fb = set()
        for d in j["diffs"]:
            if d.get("cls") == "funding_boundary":
                fb.add(d["key"])
        keystr = [str((k[0], k[1], k[2].strftime("%Y-%m-%dT%H:%M:%S.000Z"))) for k in m["key"]]
        m["is_fb"] = [k in fb for k in keystr]
        keep = m[~m["is_fb"]]
        r, e = float(keep["funding_paid_r"].sum()), float(keep["funding_paid_e"].sum())
        same = keep[(keep["qty_r"] - keep["qty_e"]).abs() <= 0.005 * keep["qty_r"]]
        rs, es = float(same["funding_paid_r"].sum()), float(same["funding_paid_e"].sum())
        es_scaled = float((keep["funding_paid_e"] * keep["qty_r"] / keep["qty_e"]).sum())    # motor funding'i referans miktarina olcekli
        out.append(dict(run=run, n_matched=len(m), n_boundary_excluded=int(m["is_fb"].sum()), ref=r, eng=e,
                        eng_scaled_to_ref_qty=es_scaled, rel_scaled=(es_scaled - r) / abs(r) if r else None,
                        rel=(e - r) / abs(r) if r else None, n_same_qty=len(same), ref_same=rs, eng_same=es,
                        rel_same=(es - rs) / abs(rs) if rs else None,
                        all_matched_ref=float(m["funding_paid_r"].sum()), all_matched_eng=float(m["funding_paid_e"].sum())))
    return out


def stakecut(order: str = "pair") -> list[dict]:
    """Kural: miktar = trunc(min(karar marji, 0.99*cuzdan - acik stake'ler) * kaldirac / fiyat, adim); cuzdan = 1000 + kapanmis
    profit_abs; ayni mumda kapanan islemlerin sayimi `bt_chainfree_diag.SAME_CLOSE` (ampirik)."""
    hist = ROOT / "var" / "history"
    out = []
    for run in RUNS:
        tf = run.split("_")[0]
        ref = X.REF_ROOT / run
        t = C.load_ref(ref, tf)
        src = C.HistoricalSource(str(hist), granularity="15m", synthetic_rules=True)
        rdec, _ = X.read_ledger(ref)
        rdec = rdec[rdec["final_action"] == "entered"]
        dm = {(X.canon(p), s, pd.Timestamp(ts)): m for p, s, ts, m in zip(rdec["pair"], rdec["side"], rdec["bar_close_ts"], rdec["size_margin"])}
        px = C._prices(hist, tf)
        rows = []
        for k in range(len(t)):
            r = t.iloc[k]
            d = dm.get((r.pairc, r.side, r.open_ts))
            if d is None or not np.isfinite(d):
                continue
            rules = src.rules(r.pairc)
            st = C.ref_state(t, k, px, tf)
            wallet, tied = st["wallet"], st["tied"]
            avail = C.TRADABLE_RATIO * wallet - tied
            own = C.trunc_step(d / r.open_rate * 3, rules.step)
            pred = C.trunc_step(min(d, avail) / r.open_rate * 3, rules.step) if avail > 0 else 0.0
            cut = r.amount < own * (1 - 1e-9) - 1e-12
            rows.append(dict(i=k, pair=r.pairc, side=r.side, ts=str(r.open_ts), ref_amount=float(r.amount), own=own, pred=pred,
                             wallet=wallet, tied=tied, avail=avail, margin_dec=float(d), ref_stake=float(r.stake_amount),
                             cut=bool(cut), rule_binds=bool(avail < d), ok=abs(pred - r.amount) <= 1e-9 * max(r.amount, 1) + 1e-12))
        df = pd.DataFrame(rows)
        cuts = df[df["cut"]]
        out.append(dict(run=run, n=len(df), n_cut=len(cuts), n_cut_rule_exact=int(cuts["ok"].sum()),
                        n_rule_binds=int(df["rule_binds"].sum()),
                        n_binds_and_ref_cut=int((df["rule_binds"] & df["cut"]).sum()),
                        n_ref_cut_rule_not_binding=int((df["cut"] & ~df["rule_binds"]).sum()),
                        n_rule_binds_ref_not_cut=int((df["rule_binds"] & ~df["cut"]).sum()),
                        n_all_exact=int(df["ok"].sum()), sample=cuts.head(25).to_dict("records")))
    return out


def closing(ledger: Path) -> dict:
    c = sqlite3.connect(f"file:{ledger}?mode=ro", uri=True)
    d = pd.read_sql("SELECT * FROM v_decisions", c)
    t = pd.read_sql("SELECT * FROM v_trades", c)
    c.close()
    d["D"] = pd.to_datetime(d["bar_close_ts"], utc=True)
    t["xts"] = pd.to_datetime(t["exit_ts"], utc=True)
    # karar-kaynakli cikis (regime_flip/target/time_stop ve planli cikis fiyati olmayan trail_stop): emir D'de verilir
    # (pozisyon `closing`), dolum D dakikasinda; ayni adimdaki _entries kapisi pozisyonu hala aktif gorur
    dec = t["exit_reason"].isin(["regime_flip", "target", "time_stop"]) | ((t["exit_reason"] == "trail_stop") & t["planned_exit"].isna())
    cl = t[dec & (t["xts"] == t["xts"].dt.floor("1h"))]
    steps = set(cl["xts"])
    rej = d[d["D"].isin(steps) & (d["final_action"] == "skipped") & ~d["skip_reason"].isin(["stop_width", "rr_below_min"])]
    rows = []
    for r in rej.itertuples():
        g = cl[cl["xts"] == r.D]
        rows.append(dict(step=str(r.D), pair=r.pair, side=r.side, skip=r.skip_reason, risk_reason=r.risk_reason,
                         closing=[f"{p} {s}" for p, s in zip(g["pair"], g["side"])],
                         closing_same_side=bool((g["side"] == r.side).any())))
    return dict(ledger=str(ledger), n_decisions=len(d), n_closing_positions=len(cl), n_steps_with_closing=len(steps),
                n_rejected_while_closing=len(rows), n_same_side_closing=sum(r["closing_same_side"] for r in rows),
                reasons=pd.Series([r["risk_reason"] for r in rows]).value_counts().to_dict() if rows else {},
                n_max_positions_rejects_total=int((d["risk_reason"].fillna("").str.contains("pozisyon say")).sum()),
                n_risk_denied_total=int((d["skip_reason"] == "risk_denied").sum()), rows=rows)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(allow_abbrev=False)
    ap.add_argument("cmd", choices=["fee", "funding", "stakecut", "closing"])
    ap.add_argument("--engine-root", default=str(ROOT / "var" / "bt_lag"))
    ap.add_argument("--xc-dir", default=str(X.XC_REF_DIR))
    ap.add_argument("--ledger", default=str(ROOT / "var" / "backtests" / "1h_IS_f1_s0_native_mark" / "ledger.sqlite"))
    ap.add_argument("--out", default=None)
    a = ap.parse_args(argv)
    if a.cmd == "fee":
        res = fee(Path(a.engine_root))
    elif a.cmd == "funding":
        res = funding(Path(a.engine_root), Path(a.xc_dir))
    elif a.cmd == "stakecut":
        res = stakecut()
    else:
        res = closing(Path(a.ledger))
    if a.out:
        Path(a.out).write_text(json.dumps(res, indent=1, default=str))
    print(json.dumps(res, indent=1, default=str) if a.cmd != "stakecut" else json.dumps(
        [{k: v for k, v in r.items() if k != "sample"} for r in res], indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main())
