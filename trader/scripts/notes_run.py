#!/usr/bin/env python3
"""Gece islem notu isi (DD-12 WP-09; spec 6.2 + 18 Kas 2026 eki). LLM YOK, ag YOK, maliyet 0.

`--once`: (1) notu olmayan her kapanan islem icin kodla bir not yazar (`model="code"`, `cost_usd=0`);
(2) aday dersleri dogurur/olcer/emekli eder (`lesson.lesson_lifecycle_hook`); (3) `--export` ile ML etiketlerini JSONL yazar.
Cikis: 0 basarili; 1 kullanim/yapilandirma; 3 defter acilamadi/yazilamadi (systemd basarisiz sayar).
Test icin `main(argv, now_fn=, env=)`.
"""
from __future__ import annotations

import argparse
import json
import logging
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

_HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(_HERE.parent / "src"))

from trader_core import ledger as L  # noqa: E402
from trader_core import lesson as LS  # noqa: E402
from trader_core import trade_notes as TN  # noqa: E402

log = logging.getLogger("trader.notes.run")


def _resolve(p: str) -> str:
    q = Path(p)
    return str(q if q.is_absolute() else _HERE.parent / q)


def main(argv=None, *, now_fn=None, env=None) -> int:
    ap = argparse.ArgumentParser(prog="notes_run.py")
    ap.add_argument("--once", action="store_true", required=True)
    ap.add_argument("--day", help="YYYY-MM-DD (varsayilan: bugun UTC)")
    ap.add_argument("--config")
    ap.add_argument("--ledger")
    ap.add_argument("--state", help="aday ders durum dosyasi (varsayilan: defterin yani: lesson_candidates.json)")
    ap.add_argument("--export", help="ML etiket satirlarini bu JSONL dosyasina yaz")
    try:
        args = ap.parse_args(argv)
    except SystemExit as e:
        return 1 if e.code else 0
    env = os.environ if env is None else env
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    try:
        cfg = LS.load_config(args.config)
    except LS.LessonConfigError as e:
        print(f"yapilandirma hatasi: {LS.scrub(e)}", file=sys.stderr)
        return 1
    if not cfg.notes_enabled:
        print(json.dumps({"status": "disabled"}))
        return 0
    now = (now_fn or (lambda: datetime.now(timezone.utc)))()
    day = args.day or now.date().isoformat()
    if not LS._valid_day(day):
        print("--day YYYY-MM-DD olmali", file=sys.stderr)
        return 1
    lp = _resolve(args.ledger or env.get("LEDGER_PATH") or cfg.ledger_path)
    state = _resolve(args.state) if args.state else str(Path(lp).with_name("lesson_candidates.json"))
    try:
        led = L.open_ledger(lp, "learner", create=False, read_only=False, migrate=False)
    except Exception as e:  # noqa: BLE001
        print(f"defter acilamadi: {LS.scrub(e)}", file=sys.stderr)
        return 3
    try:
        res = TN.write_nightly_notes(led, day)
        res["lessons"] = LS.lesson_lifecycle_hook(led, cfg, day, state)
        if args.export:
            rows = TN.export_ml_rows(led)
            with open(args.export, "w", encoding="utf-8") as fh:
                for r in rows:
                    fh.write(json.dumps(r, sort_keys=True) + "\n")
            res["exported"] = len(rows)
    except Exception as e:  # noqa: BLE001
        print(f"not isi hatasi: {LS.scrub(type(e).__name__)}: {LS.scrub(e)}", file=sys.stderr)
        return 3
    finally:
        close = getattr(led, "close", None)
        if close:
            close()
    print(json.dumps({"status": "ok", "day": day, **res}, sort_keys=True))
    return 0


if __name__ == "__main__":
    sys.exit(main())
