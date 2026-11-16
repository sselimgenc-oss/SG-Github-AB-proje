#!/usr/bin/env bash
# Sunucuda calistirilir: Binance vadeli herkese acik uclarina erisimi test eder.
# 200 beklenir; 451 = bolge engeli (ABD IP'si).
set -u
BASE="https://fapi.binance.com"
for path in /fapi/v1/ping /fapi/v1/exchangeInfo; do
  code=$(curl -s -o /dev/null -w '%{http_code}' --max-time 20 "$BASE$path" || echo "000")
  echo "$path -> HTTP $code"
done
