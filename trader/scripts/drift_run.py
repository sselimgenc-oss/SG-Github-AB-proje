#!/usr/bin/env python3
"""Gunluk sapma izleyicisi (docs/kagit-degerlendirme-plani.md Bolum 4). systemd timer `--once` calistirir.

Defteri yalnizca SALT OKUNUR acar; yalnizca <var>/<bot>/drift.json ve drift_state.json yazar. Telegram'a mesaj atmaz (tek gonderici:
saglik kontrolunun drift_alert sonucu). Geri test calistirmaz, kilitli donem verisine dokunmaz.
Cikis kodlari: 0 basarili (UYARI dahil; defter yoksa YETERSIZ yazilir); 1 kullanim; 3 bozulmus calisma (defter okunamadi ya da
cikti yazilamadi): systemd icin BASARISIZ => OnFailure.
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

from trader_core import drift_monitor as D  # noqa: E402

EXIT_OK, EXIT_CONFIG, EXIT_DEGRADED = 0, 1, 3
log = logging.getLogger("trader.drift.run")


def _var_dir(arg: str | None) -> str:
    v = arg or (os.environ.get("ENGINE_VAR_DIR") or "").strip() or "var"
    p = Path(v)
    return str(p if p.is_absolute() else _HERE.parent / p)


def main(argv=None, *, now_fn=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--bot", required=True, choices=("learner", "twin"))
    ap.add_argument("--once", action="store_true", help="tek tur (tek kullanim modu)")
    ap.add_argument("--var-dir", "--var", dest="var_dir", help="varsayilan ENGINE_VAR_DIR, yoksa <repo>/var")
    ap.add_argument("--now", help="sabit zaman (UTC, ISO; testler icin); varsayilan simdi")
    ap.add_argument("--dry-run", action="store_true", help="hesapla, dosya yazma")
    args = ap.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(message)s", stream=sys.stderr)
    if not args.once:
        print("yalniz --once desteklenir", file=sys.stderr)
        return EXIT_CONFIG
    now = (now_fn or (lambda: datetime.now(timezone.utc)))()
    if args.now:
        try:
            now = D.parse_ts(args.now)
        except Exception:  # noqa: BLE001
            now = None
        if now is None:
            print("--now: ISO zaman bekleniyor", file=sys.stderr)
            return EXIT_CONFIG
    ref = _HERE.parent / D.REF_DIR
    if ref.is_dir():   # istege bagli: sabitlerin dayandigi kosu degismis mi (yeniden hesap yok)
        bad = [k for k, v in D.verify_reference(str(ref)).items() if v is False]
        if bad:
            log.warning("referans kosu sha256 uyusmuyor: %s (sabitler plandan geldigi icin hesap degismez)", ",".join(bad))
    try:
        body, broken = D.run_bot(_var_dir(args.var_dir), args.bot, now, write=not args.dry_run)
    except Exception as e:  # noqa: BLE001
        log.error("drift calismasi basarisiz: %r", e)
        return EXIT_DEGRADED
    lv = {k: r["level"] for k, r in body["rules"].items()}
    print(json.dumps({"bot": args.bot, "overall": body["overall"], "n": body["window"]["n"], "rules": lv,
                      "skipped_rows": body["skipped_rows"]}, ensure_ascii=False))
    for ln in body.get("report_lines", []):
        print(ln)
    return EXIT_DEGRADED if broken else EXIT_OK


if __name__ == "__main__":
    sys.exit(main())
