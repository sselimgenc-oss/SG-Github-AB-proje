#!/usr/bin/env python3
"""Salt okunur rapor paketi CLI'si (docs/rapor-paketi-spec.md). Yalniz --out dizinine yazar.

Cikis kodlari: 0 basarili (bos veri dahil); 2 arguman/girdi hatasi; 3 holdout_locked.
Test icin `main(argv, now_fn=, notifier=)` enjekte edilebilir.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

_HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(_HERE.parent / "src"))

from trader_reports import inputs as I  # noqa: E402
from trader_reports import render as R  # noqa: E402

ROOT = _HERE.parent


def _p(s):
    if s is None:
        return None
    q = Path(s)
    return str(q if q.is_absolute() else ROOT / q)


def _iso(s: str, name: str) -> datetime:
    try:
        d = datetime.fromisoformat(s.replace("Z", "+00:00"))
    except ValueError:
        raise I.ReportError("arg_error", f"{name}: ISO zaman bekleniyor: {s}") from None
    return d.replace(tzinfo=timezone.utc) if d.tzinfo is None else d.astimezone(timezone.utc)


def _atomic(path: Path, text: str) -> None:
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(text, encoding="utf-8", newline="")
    os.replace(tmp, path)


def main(argv=None, *, now_fn=None, notifier=None) -> int:
    t0 = time.perf_counter()
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--bot", choices=("learner", "twin"))
    ap.add_argument("--run-dir")
    ap.add_argument("--history")
    ap.add_argument("--ledger")
    ap.add_argument("--cf")
    ap.add_argument("--market")
    ap.add_argument("--budget")
    ap.add_argument("--config", default="config/engine.base.json")
    ap.add_argument("--since")
    ap.add_argument("--until")
    ap.add_argument("--days", type=float)
    ap.add_argument("--now")
    ap.add_argument("--out", default="var/reports")
    ap.add_argument("--sections", default="exits,gates,regimes,sizing")
    ap.add_argument("--wallets", default="250,300,1000")
    ap.add_argument("--risk", type=float)
    ap.add_argument("--risk-usd", type=float)
    ap.add_argument("--compare-backtest")
    ap.add_argument("--synthetic-rules", action="store_true")
    ap.add_argument("--synthetic-step", action="append", default=[])
    ap.add_argument("--telegram", action="store_true")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args(argv)

    def fail(code, msg, rc=2):
        print(json.dumps({"status": "error", "code": code, "msg": msg}, ensure_ascii=False, sort_keys=True))
        return rc

    try:
        if bool(args.bot) == bool(args.run_dir):
            return fail("arg_error", "--bot ya da --run-dir (yalniz biri) verilmeli")
        if args.telegram and args.run_dir:
            return fail("arg_error", "--telegram backtest kipinde kullanilamaz")
        now = _iso(args.now, "--now") if args.now else (now_fn() if now_fn else datetime.now(timezone.utc))
        since = _iso(args.since, "--since") if args.since else None
        until = _iso(args.until, "--until") if args.until else None
        if args.days is not None and since is None:
            since = now - timedelta(days=args.days)
        secs = tuple(s.strip() for s in args.sections.split(",") if s.strip())
        if not secs or any(s not in R.SECTION_ORDER for s in secs):
            return fail("arg_error", f"--sections: {','.join(R.SECTION_ORDER)} icinden")
        try:
            wallets = tuple(float(x) for x in args.wallets.split(",") if x.strip())
        except ValueError:
            return fail("arg_error", "--wallets sayi listesi olmali")
        if args.risk is not None and not args.risk > 0:
            return fail("arg_error", "--risk > 0 olmali")
        bot = args.bot
        o = R.Options(mode="bot" if bot else "run", bot=bot,
                      ledger=_p(args.ledger or (f"var/{bot}/ledger.sqlite" if bot else None)),
                      cf=_p(args.cf or (f"var/{bot}/counterfactual.sqlite" if bot else None)),
                      market=_p(args.market or "var/market.sqlite"), budget=_p(args.budget or "user_data/budget.sqlite"),
                      run_dir=_p(args.run_dir), history=_p(args.history), since=since, until=until, now=now, sections=secs,
                      wallets=wallets, risk=args.risk, risk_usd=args.risk_usd, compare_backtest=_p(args.compare_backtest),
                      synthetic_rules=args.synthetic_rules, synthetic_steps=I.parse_synth_steps(args.synthetic_step),
                      config=_p(args.config))
        res = R.build_report(o)
    except I.ReportError as e:
        return fail(e.code, str(e))

    out_dir = Path(_p(args.out)) / res["target"] / now.strftime("%Y-%m-%d")
    locked = res["status"] == "holdout_locked"
    if not args.dry_run:
        out_dir.mkdir(parents=True, exist_ok=True)
        files = res["files"]
        if locked:
            files = {k: files[k] for k in ("rapor.json", "rapor.md")}
            files["rapor.md"] = "holdout_locked: kilitli dönem kesişimi, koşu okunmadı.\n"
        for name, text in files.items():
            _atomic(out_dir / name, text)
    if args.telegram and not locked and not args.dry_run:
        try:
            if notifier is None:
                from trader_core import telegram as T
                notifier = T.notifier_from_env(os.environ)
            if notifier is None:
                print("telegram yapilandirilmamis", file=sys.stderr)
            else:
                notifier.send_text(res["files"]["ozet.txt"].strip(), "INFO", dedup_key=f"rapor:{res['target']}:{now.strftime('%Y-%m-%d')}")
        except Exception as e:  # noqa: BLE001 gonderim hatasi raporu basarisiz kilmaz
            print(f"telegram gonderilemedi: {type(e).__name__}", file=sys.stderr)
    c = res["counters"]
    print(json.dumps({"status": res["status"], "out_dir": str(out_dir), "n_trades": res["n_trades"],
                      "n_decisions": res["n_decisions"], "holdout_skipped": c["holdout_skipped"], "pending": c["pending"],
                      "data_gap": c["data_gap"], "k_rapor": res["k_rapor"], "duration_s": round(time.perf_counter() - t0, 3)},
                     sort_keys=True))
    return 3 if locked else 0


if __name__ == "__main__":
    sys.exit(main())
