#!/usr/bin/env bash
# Sunucuda calistirilir (Binance erisimi gerekir). ~2 yillik vadeli veri indirir.
set -euo pipefail
cd "$(dirname "$0")/.."

PAIRS="BTC/USDT:USDT ETH/USDT:USDT BNB/USDT:USDT SOL/USDT:USDT XRP/USDT:USDT DOGE/USDT:USDT ADA/USDT:USDT TRX/USDT:USDT LINK/USDT:USDT AVAX/USDT:USDT"
TIMEFRAMES="15m 1h 4h 1d"
DAYS=730

# Veri learner dizinine iner; twin kendi dizinine kopyalanir (dizinler paylasilmaz).
# shellcheck disable=SC2086
docker compose run --rm --no-deps --entrypoint freqtrade learner download-data \
  --config /freqtrade/config/base.json \
  --trading-mode futures \
  --pairs $PAIRS \
  --timeframes $TIMEFRAMES \
  --days "$DAYS"

mkdir -p user_data/twin/data
cp -a user_data/learner/data/. user_data/twin/data/
echo "Tamam: veri user_data/learner/data ve user_data/twin/data altinda."
