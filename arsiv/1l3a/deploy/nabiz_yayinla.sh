#!/usr/bin/env bash
# Dış nabız (dead-man) Worker'ını Cloudflare'e yayımlar (deploy/nabiz_worker.js; cron */10, KV binding NABIZ).
# Ortam: /etc/1l3a-pano.env (CLOUDFLARE_API_TOKEN, CLOUDFLARE_ACCOUNT_ID) + /etc/1l3a-nabiz.env (NABIZ_ANAHTAR >= 32 karakter, ops. NABIZ_AD)
#        + /etc/1l3a-paper.env (TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID). Hiçbiri repoya girmez.
# Secret'lar stdin'den ve yalnız değişince (sha256'ları 600 izinli dosyada) konur. KV namespace yoksa oluşturulur, id'si 600 izinli dosyada tutulur.
set -euo pipefail
: "${CLOUDFLARE_API_TOKEN:?CLOUDFLARE_API_TOKEN tanımlı değil (/etc/1l3a-pano.env)}"
: "${CLOUDFLARE_ACCOUNT_ID:?CLOUDFLARE_ACCOUNT_ID tanımlı değil (/etc/1l3a-pano.env)}"
: "${NABIZ_ANAHTAR:?NABIZ_ANAHTAR tanımlı değil (/etc/1l3a-nabiz.env; openssl rand -hex 32)}"
: "${TELEGRAM_BOT_TOKEN:?TELEGRAM_BOT_TOKEN tanımlı değil (/etc/1l3a-paper.env)}"
: "${TELEGRAM_CHAT_ID:?TELEGRAM_CHAT_ID tanımlı değil (/etc/1l3a-paper.env)}"
[ "${#NABIZ_ANAHTAR}" -ge 32 ] || { echo "HATA: NABIZ_ANAHTAR en az 32 karakter olmalı" >&2; exit 1; }
ad="${NABIZ_AD:-1l3a-nabiz}"
ev="${NABIZ_EV:-/var/lib/1l3a-paper/yayin-ev}"
betik_dizin="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
mkdir -p "$ev"
export WRANGLER_SEND_METRICS=false
gecici="$(mktemp -d)"
trap 'rm -rf "$gecici"' EXIT
cd "$gecici"

# KV namespace: yoksa oluştur, id'yi 600 izinli dosyada tut
kv_dosya="$ev/nabiz_kv_id"
kv_id="$(cat "$kv_dosya" 2>/dev/null || true)"
if [ -z "$kv_id" ]; then
  cikti="$(timeout -k 10 120 wrangler kv namespace create "${ad}-kv")"
  kv_id="$(printf '%s' "$cikti" | grep -oE '[0-9a-f]{32}' | head -n1 || true)"
  [ -n "$kv_id" ] || { echo "HATA: KV namespace id'si alınamadı (API token'ında Workers KV Storage: Edit izni var mı?)" >&2; exit 1; }
  ( umask 077; printf '%s\n' "$kv_id" > "$kv_dosya" )
  chmod 600 "$kv_dosya"
  echo "KV namespace oluşturuldu"
fi

cp "$betik_dizin/nabiz_worker.js" "$gecici/nabiz_worker.js"
cat > "$gecici/wrangler.jsonc" <<JSON
{
  "name": "$ad",
  "main": "nabiz_worker.js",
  "compatibility_date": "2026-11-01",
  "workers_dev": true,
  "triggers": { "crons": ["*/10 * * * *"] },
  "kv_namespaces": [{ "binding": "NABIZ", "id": "$kv_id" }]
}
JSON
timeout -k 10 180 wrangler deploy --config wrangler.jsonc

# secret'lar: stdin'den, yalnız değişince
secret_koy() {
  local isim="$1" deger="$2" hash_dosya="$ev/nabiz_${1}.sha256" yeni eski
  yeni="$(printf '%s' "$deger" | sha256sum | cut -d' ' -f1)"
  eski="$(cat "$hash_dosya" 2>/dev/null || true)"
  if [ "$yeni" != "$eski" ]; then
    printf '%s' "$deger" | timeout -k 10 120 wrangler secret put "$isim" --name "$ad"
    ( umask 077; printf '%s\n' "$yeni" > "$hash_dosya" )
    chmod 600 "$hash_dosya"
    echo "$isim secret'ı güncellendi"
  fi
}
secret_koy NABIZ_ANAHTAR "$NABIZ_ANAHTAR"
secret_koy TELEGRAM_BOT_TOKEN "$TELEGRAM_BOT_TOKEN"
secret_koy TELEGRAM_CHAT_ID "$TELEGRAM_CHAT_ID"
echo "nabız Worker'ı yayımlandı: $(date -u +%FT%TZ) (adres: https://$ad.<hesap-alt-alanı>.workers.dev; NABIZ_URL'e yazın)"
