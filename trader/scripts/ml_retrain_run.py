#!/usr/bin/env python3
"""Gece kurulum suzgeci egitimi (DD-12 WP-10; D-T26). 03:10 UTC, tek oneshot birim (MemoryMax). Yalniz numpy; ag yok.

Defteri salt okunur acar (yazmaz); `models/setup_filter/<arm>.json` (+ `.prev.json` yedek) yazar; `research/paper_models.csv`'ye
gunluk tek `nightly` satiri ekler. Kilit donemi (2026-05-01..2026-11-01) satirlari egitimden DUSURULUR (sayilir).
Cikis: 0 basarili (model olusmayan kol hata degil: `ml_no_model`); 1 kullanim; 3 defter acilamadi/yazma hatasi.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

_HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(_HERE.parent / "src"))

from trader_core import ledger as L  # noqa: E402
from trader_ml.setup_filter import package as P  # noqa: E402
from trader_ml.setup_filter import train as T  # noqa: E402


def _resolve(p: str) -> str:
    q = Path(p)
    return str(q if q.is_absolute() else _HERE.parent / q)


def main(argv=None, *, now_fn=None, env=None) -> int:
    ap = argparse.ArgumentParser(prog="ml_retrain_run.py")
    ap.add_argument("--once", action="store_true", required=True)
    ap.add_argument("--ledger")
    ap.add_argument("--cf")
    ap.add_argument("--models-dir", default="models/setup_filter")
    ap.add_argument("--paper-models-csv", default="research/paper_models.csv")
    ap.add_argument("--max-rows", type=int, default=T.MAX_ROWS)
    try:
        args = ap.parse_args(argv)
    except SystemExit as e:
        return 1 if e.code else 0
    env = os.environ if env is None else env
    now = (now_fn or (lambda: datetime.now(timezone.utc)))()
    lp = _resolve(args.ledger or env.get("LEDGER_PATH") or "var/learner/ledger.sqlite")
    cf = _resolve(args.cf) if args.cf else str(Path(lp).with_name("counterfactual.sqlite"))
    try:
        led = L.open_ledger(lp, "learner", create=False, read_only=True, migrate=False)
    except Exception as e:  # noqa: BLE001
        print(f"defter acilamadi: {type(e).__name__}", file=sys.stderr)
        return 3
    try:
        rows = T.collect_rows(led, cf if os.path.exists(cf) else None)
        pkgs, rep = T.train_all(rows, created_at=now, max_rows=args.max_rows)
        mdir = _resolve(args.models_dir)
        for pkg in pkgs.values():
            P.save_package(pkg, mdir)
        csvp = Path(_resolve(args.paper_models_csv))
        csvp.parent.mkdir(parents=True, exist_ok=True)
        new = not csvp.exists()
        digest = hashlib.sha256("".join(sorted(p["meta"]["model_hash"] for p in pkgs.values())).encode()).hexdigest()
        with open(csvp, "a", newline="", encoding="utf-8") as fh:
            w = csv.writer(fh)
            if new:
                w.writerow(["ad", "sinif", "tarif", "veri_penceresi", "commit", "sha256", "tarih"])
            w.writerow([f"setup_filter_nightly_{now.date().isoformat()}", "nightly", f"ridge_logistic;arms={len(pkgs)}",
                        f"rows={len(rows)};lock_dropped={rep['lock_dropped']}", "", digest, now.isoformat()])
    except Exception as e:  # noqa: BLE001
        print(f"egitim hatasi: {type(e).__name__}: {e}", file=sys.stderr)
        return 3
    finally:
        led.close()
    print(json.dumps({"status": "ok", "rows": len(rows), "models": sorted(pkgs), **rep}, sort_keys=True, default=str))
    return 0


if __name__ == "__main__":
    sys.exit(main())
