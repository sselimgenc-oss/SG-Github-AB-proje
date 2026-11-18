#!/usr/bin/env python3
"""ML-G7: OI / long-short orani toplayici (tek seferlik; trader-oi.timer her 5 dk calistirir).

Yalniz Binance USDⓈ-M herkese acik /futures/data/* GET uclari; anahtar yok. Cikti: var/market.sqlite -> positioning_5m.
Cikis kodlari: 0 tamam; 2 kismi hata (bazi cift/uc alinamadi; birim bunu basari sayar, gunluge yazilir);
3 IP yasagi/429; 6 HTTP 451 (konum kisiti); 1 beklenmeyen hata.
Kullanim: python scripts/oi_collect.py [--config-dir config] [--db yol] [--pairs BTC/USDT,ETH/USDT] [--max-requests 900]
"""
from __future__ import annotations

import argparse
import json
import logging
import sys
import time
from pathlib import Path

_HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(_HERE.parent / "src"))

from trader_core.ban_store import BanGuard, ban_dir_for, ban_path  # noqa: E402
from trader_engine.marketdata import oi_collector as C  # noqa: E402

log = logging.getLogger("trader.oi.run")
EXIT_OK, EXIT_CRASH, EXIT_PARTIAL, EXIT_BAN, EXIT_GEO = 0, 1, 2, 3, 6


def load_pairs_and_db(config_dir: Path) -> tuple[list[str], str]:
    cfg = json.loads((config_dir / "engine.base.json").read_text(encoding="utf-8"))
    db = cfg["market_db"]
    if not Path(db).is_absolute():
        db = str((config_dir.resolve().parent / db))
    return list(cfg["pairs"]), db


def main(argv=None, *, client=None, now_ms: int | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--config-dir", default=str(_HERE.parent / "config"))
    ap.add_argument("--db", default=None)
    ap.add_argument("--pairs", default=None, help="virgullu; varsayilan: engine.base.json pairs")
    ap.add_argument("--max-requests", type=int, default=900)
    ap.add_argument("--ban-dir", default=None, help="ban dosyasi dizini (varsayilan: market veritabaninin dizini)")
    a = ap.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
    try:
        pairs, db_path = load_pairs_and_db(Path(a.config_dir))
        if a.pairs:
            pairs = [p.strip() for p in a.pairs.split(",") if p.strip()]
        if a.db:
            db_path = a.db
        now = int(time.time() * 1000) if now_ms is None else now_ms
        clock = (lambda: now) if now_ms is not None else (lambda: int(time.time() * 1000))
        guard = BanGuard(ban_path(a.ban_dir or ban_dir_for(db_path), C.BASE_URL), source="oi", now_ms=clock)   # DD-7 §4
        rec = guard.active()
        if rec is not None:                      # yasak suruyor: istek YOK; alarmi saglik uretir (OnFailure gurultusu istenmez)
            left = max(1, -(-(rec.until_ms - clock()) // 1000))
            log.warning("event=ban_skip host=%s left_s=%d", rec.host, left)
            return EXIT_OK
        if client is None:
            client = C.HttpClient(ban_guard=guard, now_ms=clock)
        db = C.open_db(db_path)
        try:
            st = C.collect(db, client, pairs, now, max_requests=a.max_requests)
        finally:
            db.close()
    except C.GeoBlockError as e:
        log.error("event=geoblock err=%s", e)
        return EXIT_GEO
    except C.BanError as e:
        log.error("event=ban err=%s", e)
        return EXIT_BAN
    except Exception:  # noqa: BLE001
        log.exception("event=crash")
        return EXIT_CRASH
    log.info("event=done pairs=%d rows=%d requests=%d errors=%d budget_hit=%s used_weight=%s weight_stop=%s", len(pairs),
             st.rows, st.requests, st.errors, st.budget_hit, getattr(client, "last_used_weight", None), st.weight_stop)
    return EXIT_PARTIAL if st.errors else EXIT_OK


if __name__ == "__main__":
    sys.exit(main())
