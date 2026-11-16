#!/usr/bin/env python3
"""freqtrade'i Binance API'ye erismeden (HTTP 451 ortami) calistirir: backtesting vb.

freqtrade acilista `exchangeInfo` ile market listesi ister. Bu sarmalayici o cagriyi
yerel veriden turetilmis SENTETIK marketlerle degistirir (fiyat/miktar adimi son
mumlardan cikarilir, min notional 5 USDT, contractSize 1). Kaldirac kademeleri
freqtrade'in paketindeki binance_leverage_tiers.json'dan gelir (dry_run). Sentetik
precision/limit degerleri yaklasiktir: sonuclar gercek borsa kurallariyla birebir degil.
Yalnizca backtesting / list-data icin; canli/dry-run icin KULLANMAYIN.

Kullanim: .venv-ft/bin/python scripts/freqtrade_offline.py backtesting --config ... (freqtrade argumanlari)
"""
from __future__ import annotations

import json
import sys
from decimal import Decimal
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
FUT = ROOT / "user_data/data/binance/futures"


def _step(values) -> float:
    dec = 0
    for v in values:
        e = Decimal(repr(round(float(v), 10))).as_tuple().exponent
        dec = max(dec, -e)
    return 10.0 ** -min(dec, 8)


def synthetic_markets(pairs: list[str]) -> list[dict]:
    out = []
    for pair in pairs:
        base = pair.split("/")[0]
        f = FUT / f"{pair.replace('/', '_').replace(':', '_')}-1h-futures.feather"
        tail = pd.read_feather(f).tail(2000)
        tick = _step(pd.concat([tail["open"], tail["close"], tail["high"], tail["low"]]))
        lot = _step(tail["volume"])
        out.append(
            {
                "id": f"{base}USDT", "symbol": pair, "base": base, "quote": "USDT", "settle": "USDT",
                "baseId": base, "quoteId": "USDT", "settleId": "USDT", "type": "swap",
                "spot": False, "margin": False, "swap": True, "future": False, "option": False,
                "contract": True, "linear": True, "inverse": False, "contractSize": 1.0,
                "active": True, "taker": 0.0005, "maker": 0.0002,
                "precision": {"amount": lot, "price": tick},
                "limits": {
                    "amount": {"min": lot, "max": None}, "price": {"min": tick, "max": None},
                    "cost": {"min": 5.0, "max": None}, "leverage": {"min": 1, "max": 20},
                },
                "info": {},
            }
        )
    return out


ALLOWED_SUBCOMMANDS = {"backtesting", "list-data", "lookahead-analysis",
                       "recursive-analysis", "hyperopt", "backtesting-analysis"}


def main() -> None:
    # Sentetik marketler gerçek emir için asla kullanılmamalı: yalnız izinli alt komutlar.
    sub = next((a for a in sys.argv[1:] if not a.startswith("-")), None)
    if sub not in ALLOWED_SUBCOMMANDS:
        sys.exit(f"freqtrade_offline: '{sub}' izinli değil; yalnız {sorted(ALLOWED_SUBCOMMANDS)}")
    from freqtrade.exchange import Exchange

    def _load_async_markets(self, reload: bool = False) -> None:
        pairs = self._config["exchange"]["pair_whitelist"]
        self._api_async.set_markets(synthetic_markets(pairs))

    Exchange._load_async_markets = _load_async_markets
    from freqtrade.main import main as ft_main

    sys.argv[0] = "freqtrade"
    ft_main()


if __name__ == "__main__":
    main()
