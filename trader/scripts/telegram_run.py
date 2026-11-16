#!/usr/bin/env python3
"""Telegram calistiricisi (docs/telegram-spec.md): `daemon` | `send` | `report`.

Cikis: 0 basarili (spool'a dusme dahil); 1 yapilandirma/kullanim hatasi. Token hicbir yere yazilmaz.
Test icin `main(argv, env=, http_post=, now_fn=, sleep=, stop=)` enjekte edilebilir.
"""
from __future__ import annotations

import argparse
import logging
import os
import signal
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

_HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(_HERE.parent / "src"))

from trader_core import telegram as T  # noqa: E402

EXIT_OK, EXIT_CONFIG = 0, 1


def main(argv=None, *, env=None, http_post=None, now_fn=None, sleep=time.sleep, stop=None, runner=None) -> int:
    ap = argparse.ArgumentParser(prog="telegram_run.py")
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("daemon")
    sp = sub.add_parser("send")
    sp.add_argument("--severity", choices=T.SEVERITIES, default="INFO")
    sp.add_argument("--dedup-key", required=True)
    sp.add_argument("text")
    sub.add_parser("report")
    try:
        args = ap.parse_args(argv)
    except SystemExit as e:
        return EXIT_CONFIG if e.code else EXIT_OK
    env = os.environ if env is None else env
    logging.basicConfig(stream=sys.stderr, level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    cfg = T.TelegramConfig.from_env(env)
    if cfg is None:
        print("telegram yapilandirilmamis (TELEGRAM_BOT_TOKEN / TELEGRAM_CHAT_ID)", file=sys.stderr)
        return EXIT_CONFIG
    now_fn = now_fn or (lambda: datetime.now(timezone.utc))
    client = T.TelegramClient(cfg.token, http_post, sleep)
    try:
        if args.cmd == "send":
            n = T.TelegramNotifier(client, cfg.chat_id, T.Outbox(cfg.var_dir, now_fn), now_fn, sleep)
            ok = n.send_text(args.text, args.severity, args.dedup_key)
            print("sent" if ok else "spooled")
            return EXIT_OK
        if args.cmd == "report":
            n = T.TelegramNotifier(client, cfg.chat_id, T.Outbox(cfg.var_dir, now_fn), now_fn, sleep)
            print(T.run_report(cfg, n, now_fn()))
            return EXIT_OK
        d = T.TelegramDaemon(cfg, client, now_fn=now_fn, sleep=sleep, runner=runner,
                             report_fn=lambda: T.build_report(cfg, now_fn(), now_fn().astimezone(T.TR).date().isoformat(),
                                                       T.default_sections(cfg, now_fn(), now_fn().astimezone(T.TR).date().isoformat())))
        flag = {"stop": False}
        signal.signal(signal.SIGTERM, lambda *_: flag.update(stop=True))
        d.run_forever(stop or (lambda: flag["stop"]))
        return EXIT_OK
    except Exception as e:  # noqa: BLE001  token sizmasin
        print(f"telegram_run: hata: {T.mask(type(e).__name__, cfg.token)}", file=sys.stderr)
        return EXIT_CONFIG


if __name__ == "__main__":
    sys.exit(main())
