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


def _read_v3_skipped(path: str, bot: str, since) -> list:
    """Sema 3 dosya (goc henuz olmadi): `v_decisions` salt okunur ham SQL ile okunur. Baska surum ya da bozuk dosya
    `LedgerSchemaError` olarak yukselir (bozulmus calisma)."""
    import sqlite3
    from urllib.parse import quote
    try:
        c = sqlite3.connect("file:" + quote(os.path.abspath(path)) + "?mode=ro", uri=True, timeout=5.0)
        c.row_factory = sqlite3.Row
        try:
            if c.execute("PRAGMA user_version").fetchone()[0] != 3:
                raise L.LedgerSchemaError("sema surumu 3 degil")
            sql = "SELECT * FROM v_decisions WHERE bot=? AND final_action='skipped'"
            args: list = [bot]
            if since is not None:
                sql += " AND bar_close_ts>=?"
                args.append(L._fmt_ts(since))
            sql += " ORDER BY bar_close_ts, id"
            return [L.Ledger._decision_from(r) for r in c.execute(sql, args).fetchall()]
        finally:
            c.close()
    except sqlite3.Error as e:
        raise L.LedgerSchemaError(f"sema 3 defter okunamadi: {e}") from e


def main(argv=None, *, now_fn=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--bot", required=True, choices=("learner",))
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
        shadows: list = []
        try:
            led = L.open_ledger(ledger_path, args.bot, create=False, read_only=True, migrate=False)
            try:
                decisions = led.list_decisions(since_ts=since, final_action="skipped")
                shadows = led.list_shadow(since_ts=since)           # WP-3 7: sema 4; ayri tablo, ayri sonuc
            finally:
                led.close()
        except L.LedgerSchemaError:
            decisions = _read_v3_skipped(ledger_path, args.bot, since)   # gecis donemi: sema 3 defter okunur, golge adimi atlanir
        if args.dry_run:                                    # dry-run: depoya yazilmaz (yoksa bos bellek deposu)
            store = CF.CounterfactualStore(out_path, read_only=True) if os.path.exists(out_path) \
                else CF.CounterfactualStore(":memory:")
        else:
            store = CF.CounterfactualStore(out_path)
        try:
            r = CF.run_once(bot=args.bot, decisions=decisions, market_path=market_path, store=store, now=now,
                            dry_run=args.dry_run)
            sr = CF.run_shadow(bot=args.bot, shadows=shadows, market_path=market_path, store=store, now=now,
                               dry_run=args.dry_run) if shadows else CF.ShadowRunResult()
        finally:
            store.close()
    except (CF.CounterfactualError, L.LedgerError) as e:
        log.error("bozulmus calisma: %s", getattr(e, "code", type(e).__name__))
        print(json.dumps({"bot": args.bot, "status": "degraded", "code": getattr(e, "code", type(e).__name__)}))
        return EXIT_DEGRADED
    print(json.dumps({"bot": args.bot, "status": "ok", "dry_run": args.dry_run, **vars(r), **vars(sr)}))
    return EXIT_OK


if __name__ == "__main__":
    sys.exit(main())
