#!/usr/bin/env bash
# Binance acik arsivinden (data.binance.vision) ~2 yillik vadeli gecmis veriyi var/history/ altina indirir.
# Binance API erisimi gerekmez; idempotent (var olan zip'ler yeniden indirilmez, sha256 dogrulanir).
# Ayrintilar ve secenekler: scripts/fetch_binance_vision.py --help
set -euo pipefail
cd "$(dirname "$0")/.."

PYTHON="${PYTHON:-.venv/bin/python}"
"$PYTHON" scripts/fetch_binance_vision.py --start "${START:-2024-11}" "$@"
echo "Tamam: gecmis veri var/history altinda (ham zip onbellegi var/vision_raw)."
