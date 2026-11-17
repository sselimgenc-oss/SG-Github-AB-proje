#!/usr/bin/env python3
"""Gece isi: alinmayan sinyallerin varsayimsal sonucu (docs/alinmayan-sinyal-spec.md). systemd timer `--once` calistirir.

Defteri (var/<bot>/ledger.sqlite) ve var/market.sqlite'i yalnizca SALT OKUNUR acar; yalnizca var/<bot>/counterfactual.sqlite'e yazar.
Cikis kodlari: 0 basarili (hesaplanacak karar yoklugu ve defter yoklugu dahil); 1 kullanim/yapilandirma hatasi;
3 bozulmus calisma (market/defter/depo okunamadi ya da yazilamadi): systemd icin BASARISIZ => OnFailure.
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

from trader_core import counterfactual as CF  # noqa: E402
from trader_core import ledger as L  # noqa: E402

EXIT_OK, EXIT_CONFIG, EXIT_DEGRADED = 0, 1, 3
log = logging.getLogger("trader.counterfactual.run")


def _resolve(p: str) -> str:
    q = Path(p)
    return str(q if q.is_absolute() else _HERE.parent / q)


def _parse_since(s: str | None):
    if not s:
        return None
    try:
        d = datetime.fromisoformat(s.replace("Z", "+00:00"))
    except ValueError:
        raise SystemExit("--since: ISO zaman (UTC) bekleniyor, ornek 2026-12-01 ya da 2026-12-01T00:00:00Z") from None
    return d.replace(tzinfo=timezone.utc) if d.tzinfo is None else d.astimezone(timezone.utc)


def main(argv=None, *, now_fn=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--bot", required=True, choices=("learner", "twin"))
    ap.add_argument("--once", action="store_true", help="tek tur (tek kullanim modu)")
    ap.add_argument("--since", help="yalniz bu zamandan (UTC, ISO) sonraki kararlar")
    ap.add_argument("--dry-run", action="store_true", help="hesapla, yazma")
    ap.add_argument("--ledger", help="varsayilan var/<bot>/ledger.sqlite")
    ap.add_argument("--market", default="var/market.sqlite")
    ap.add_argument("--out", help="varsayilan var/<bot>/counterfactual.sqlite")
    args = ap.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(message)s", stream=sys.stderr)
    if not args.once:
        print("yalniz --once desteklenir", file=sys.stderr)
        return EXIT_CONFIG
    since = _parse_since(args.since)
    now = (now_fn or (lambda: datetime.now(timezone.utc)))()
    ledger_path = _resolve(args.ledger or f"var/{args.bot}/ledger.sqlite")
    out_path = _resolve(args.out or f"var/{args.bot}/counterfactual.sqlite")
    market_path = _resolve(args.market)
    if not os.path.exists(ledger_path):
        log.info("defter yok (%s kapali olabilir); yapilacak is yok", args.bot)
        print(json.dumps({"bot": args.bot, "status": "no_ledger"}))
        return EXIT_OK
    try:
        led = L.open_ledger(ledger_path, args.bot, create=False, read_only=True, migrate=False)
        try:
            decisions = led.list_decisions(since_ts=since, final_action="skipped")
        finally:
            led.close()
        if args.dry_run:                                    # dry-run: depoya yazilmaz (yoksa bos bellek deposu)
            store = CF.CounterfactualStore(out_path, read_only=True) if os.path.exists(out_path) \
                else CF.CounterfactualStore(":memory:")
        else:
            store = CF.CounterfactualStore(out_path)
        try:
            r = CF.run_once(bot=args.bot, decisions=decisions, market_path=market_path, store=store, now=now,
                            dry_run=args.dry_run)
        finally:
            store.close()
    except (CF.CounterfactualError, L.LedgerError) as e:
        log.error("bozulmus calisma: %s", getattr(e, "code", type(e).__name__))
        print(json.dumps({"bot": args.bot, "status": "degraded", "code": getattr(e, "code", type(e).__name__)}))
        return EXIT_DEGRADED
    print(json.dumps({"bot": args.bot, "status": "ok", "dry_run": args.dry_run, **vars(r)}))
    return EXIT_OK


if __name__ == "__main__":
    sys.exit(main())
