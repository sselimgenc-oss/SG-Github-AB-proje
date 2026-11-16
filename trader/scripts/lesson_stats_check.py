#!/usr/bin/env python3
"""Ders servisi kontrol noktasi istatistikleri icin capraz kontrol raporu (YALNIZ RAPOR; karara etkisi yok).

`python3 -I scripts/lesson_stats_check.py --ledger PATH [--checkpoints 30,45,60] [--json] [--out PATH]`.
Defter SALT OKUNUR acilir; hicbir sey yazilmaz (yalniz `--out` raporu), LLM/butce kullanilmaz.

Her kapsam (tum islemler + her setup) ve kontrol noktasi `c` (kapsamda ilk `c` kapanmis islem, cikis sirasi) icin:
gun-kumelenmis `z_cl` (lesson.cluster_mean, ortalama R > 0; ders-spec 4.3), ondan tek yonlu p, islem bazli Sharpe/PSR
(carpiklik + basiklik duzeltmeli), MinTRL. Tum hucreler uzerinde Holm duzeltmesi ve DSR (N = hucre sayisi, varyans =
hucre Sharpe'larinin varyansi) hesaplanir. Cikti `trader_core.stats` (Bailey & Lopez de Prado) uzerinden; bu bir
bagimsiz tutarlilik kontroludur, kalibrasyonun (7.3) yerine gecmez. Cikis: 0 rapor uretildi, 1 kullanim/defter hatasi.
"""
from __future__ import annotations

import argparse
import json
import math
import sys
from pathlib import Path

_HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(_HERE.parent / "src"))

from trader_core import ledger as L  # noqa: E402
from trader_core import lesson as LS  # noqa: E402
from trader_core.stats import (  # noqa: E402
    adjust_pvalues, deflated_sharpe, min_track_record_length, probabilistic_sharpe, return_moments, sharpe,
)

DEFAULT_CHECKPOINTS = (30, 45, 60)


def load_rows(led) -> list[tuple[str, float, str]]:
    """Kapanmis islemler -> [(setup, r, cikis_gunu)], cikis sirasina gore (eskiden yeniye)."""
    recs = led.list_closed_trades(limit=led.LIST_CLOSED_MAX)
    recs = [t for t in recs if t.r_multiple is not None and t.exit_ts is not None]
    recs.sort(key=lambda t: (t.exit_ts, t.trade_id))
    return [(t.setup, float(t.r_multiple), LS.day_of(t.exit_ts)) for t in recs]


def build_report(rows, checkpoints=DEFAULT_CHECKPOINTS) -> dict:
    """Saf fonksiyon: `rows` = [(setup, r, gun)] (cikis sirasinda). Kararlari etkilemez."""
    scopes: dict[str, list] = {"ALL": list(rows)}
    for s, r, d in rows:
        scopes.setdefault(f"setup:{s}", []).append((s, r, d))
    cells = []
    for name, items in scopes.items():
        for c in checkpoints:
            if len(items) < c:
                continue
            sub = items[:c]
            rs = [r for _, r, _ in sub]
            z = LS.cluster_mean([(r, d) for _, r, d in sub], 0.0)
            sr = sharpe(rs, periods=1)
            sk, ku = return_moments(rs)
            p_cl = None if z.z is None else 0.5 * math.erfc(z.z / math.sqrt(2.0))
            cells.append({
                "scope": name, "c": c, "n": c, "days": z.g, "mean_r": z.d, "z_cl": z.z, "p_cl": p_cl,
                "sharpe_trade": None if math.isnan(sr) else sr, "skew": sk, "kurt": ku,
                "psr0": None if math.isnan(sr) else probabilistic_sharpe(sr, c, sk, ku, 0.0),
                "mintrl_95": None if math.isnan(sr) else min_track_record_length(sr, sk, ku, 0.0, 0.95),
            })
    pv = [(i, x["p_cl"]) for i, x in enumerate(cells) if x["p_cl"] is not None]
    if pv:
        adj = adjust_pvalues([p for _, p in pv], "holm")
        for (i, _), a in zip(pv, adj):
            cells[i]["p_holm"] = float(a)
    srs = [x["sharpe_trade"] for x in cells if x["sharpe_trade"] is not None]
    n_trials = len(srs)
    var = float(_var(srs)) if n_trials > 1 else None
    for x in cells:
        x.setdefault("p_holm", None)
        x["dsr"] = None
        if x["sharpe_trade"] is not None and n_trials > 1 and var is not None:
            x["dsr"] = deflated_sharpe(x["sharpe_trade"], x["n"], x["skew"], x["kurt"], n_trials=n_trials, trial_var=var)
    return {"n_closed": len(rows), "checkpoints": list(checkpoints), "n_cells": len(cells), "dsr_n_trials": n_trials,
            "dsr_trial_var": var, "cells": cells,
            "note": "capraz kontrol raporu; karara etkisi yok (ders-spec 7.3 kalibrasyonunun yerine gecmez)"}


def _var(xs) -> float:
    m = sum(xs) / len(xs)
    return sum((v - m) ** 2 for v in xs) / (len(xs) - 1)


def _f(v, fmt="{:.3f}") -> str:
    return "-" if v is None else fmt.format(v)


def render_text(rep: dict) -> str:
    out = [f"kapanmis islem: {rep['n_closed']}  hucre: {rep['n_cells']}  DSR N={rep['dsr_n_trials']}",
           f"{'kapsam':<18}{'c':>4}{'gun':>5}{'ort_R':>8}{'z_cl':>7}{'p_cl':>8}{'p_holm':>8}{'SR':>7}{'PSR0':>7}{'DSR':>7}"]
    for x in rep["cells"]:
        out.append(f"{x['scope']:<18}{x['c']:>4}{x['days']:>5}{_f(x['mean_r']):>8}{_f(x['z_cl'], '{:.2f}'):>7}"
                   f"{_f(x['p_cl'], '{:.4f}'):>8}{_f(x['p_holm'], '{:.4f}'):>8}{_f(x['sharpe_trade']):>7}"
                   f"{_f(x['psr0']):>7}{_f(x['dsr']):>7}")
    out.append(rep["note"])
    return "\n".join(out)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="lesson_stats_check.py")
    ap.add_argument("--ledger", required=True)
    ap.add_argument("--checkpoints", default=",".join(map(str, DEFAULT_CHECKPOINTS)))
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--out")
    try:
        args = ap.parse_args(argv)
    except SystemExit as e:
        return 1 if e.code else 0
    try:
        cps = tuple(int(x) for x in args.checkpoints.split(",") if x.strip())
        if not cps or any(c < 2 for c in cps):
            raise ValueError
    except ValueError:
        print("--checkpoints: virgullu tamsayilar (>= 2) olmali", file=sys.stderr)
        return 1
    try:
        led = L.open_ledger(args.ledger, "learner", create=False, read_only=True, migrate=False)
    except L.LedgerError as e:
        print(f"defter acilamadi: {e}", file=sys.stderr)
        return 1
    rep = build_report(load_rows(led), cps)
    text = json.dumps(rep, indent=2, ensure_ascii=False) if args.json else render_text(rep)
    if args.out:
        Path(args.out).write_text(text + "\n", encoding="utf-8")
    else:
        print(text)
    return 0


if __name__ == "__main__":
    sys.exit(main())
