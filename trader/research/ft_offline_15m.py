#!/usr/bin/env python3
"""scripts/freqtrade_offline.py + startup-candle korumasini atlayan yama (YALNIZ backtest/analiz).

TraderV1 15m'de 4800 mum isitma ister (300*4/0.25). freqtrade `Exchange.validate_required_startup_candles`
Binance 15m icin en fazla 2494 mumu kabul eder ve ConfigurationError firlatir (canli/dry-run'da mum
borsadan cekildigi icin). Backtest'te veri diskten okundugu icin bu sinirin anlami yoktur; burada yalniz
bu kontrol atlanir. Bulgu: canli 15m tetik bu haliyle BASLAMAZ (rapora yazildi).
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
import freqtrade_offline as fo  # noqa: E402
from freqtrade.exchange import Exchange  # noqa: E402

Exchange.validate_required_startup_candles = lambda self, startup_candles, timeframe: startup_candles

if __name__ == "__main__":
    fo.main()
