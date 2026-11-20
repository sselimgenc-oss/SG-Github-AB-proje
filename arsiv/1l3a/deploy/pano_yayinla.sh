#!/usr/bin/env bash
# Sunucudaki pano.html'i Cloudflare Workers'a yayımlar; pano bir Worker'ın ARKASINDADIR (Cloudflare Access JWT doğrulaması).
# Gerekli ortam değişkenleri (/etc/1l3a-pano.env, chmod 600; asla repoya girmez): CLOUDFLARE_API_TOKEN, CLOUDFLARE_ACCOUNT_ID.
# İsteğe bağlı: PANO_AD (varsayılan 1l3a-pano), ACCESS_AUD (Access uygulaması AUD etiketi), ACCESS_TAKIM (varsayılan slmgncortak).
# PANO_SIFRE kaldırıldı (Basic Auth yok); eski PANO_SIFRE Worker secret'ı kalmışsa bir kez silinmeye çalışılır.
# Açık günlük özet AYRI Worker'dır (PANO_ACIK_AD, varsayılan 1l3a-pano-acik; yalnız /gunluk_ozet_v1.json ve /mutabakat_v1.json; dosya yoksa atlanır):
# workers.dev'de Access yol bazında Bypass desteklemez, o yüzden ana pano Worker'ı tamamen kilitli kalır.
# PANO_KILITSIZ=1 ise pano Worker kilidi OLMADAN yayımlanır (yalnız statik sayfa; açık tercih).
set -euo pipefail
: "${CLOUDFLARE_API_TOKEN:?CLOUDFLARE_API_TOKEN tanımlı değil (/etc/1l3a-pano.env)}"
: "${CLOUDFLARE_ACCOUNT_ID:?CLOUDFLARE_ACCOUNT_ID tanımlı değil (/etc/1l3a-pano.env)}"
kilitsiz=0
[ "${PANO_KILITSIZ:-0}" = "1" ] && kilitsiz=1
# PANO_SIFRE artık kullanılmaz (varsa yok sayılır).
# ACCESS_AUD / ACCESS_TAKIM (isteğe bağlı, gizli değil) Worker'a wrangler "vars" olarak geçer; yalnız güvenli karakterler.
vars=""
for d in ACCESS_AUD ACCESS_TAKIM; do
  v="${!d:-}"
  [ -z "$v" ] && continue
  [[ "$v" =~ ^[A-Za-z0-9._-]+$ ]] || { echo "HATA: $d yalnız harf, rakam, . _ - içerebilir" >&2; exit 1; }
  vars="$vars\"$d\": \"$v\", "
done
[ -n "$vars" ] && vars=$',\n  "vars": { '"${vars%, }"' }'
ad="${PANO_AD:-1l3a-pano}"
kaynak="${PANO_DOSYA:-/var/lib/1l3a-paper/durum/pano.html}"
[ -s "$kaynak" ] || { echo "HATA: $kaynak yok ya da boş (1l3a-pano.timer çalışıyor mu?)" >&2; exit 1; }
hash_dosya="${PANO_SIFRE_HASH_DOSYA:-/var/lib/1l3a-paper/yayin-ev/pano_sifre.sha256}"
betik_dizin="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
gecici="$(mktemp -d)"
trap 'rm -rf "$gecici"' EXIT
mkdir "$gecici/site"
cp "$kaynak" "$gecici/site/index.html"
# ortak günlük özet (motor/canli/gunluk_ozet.py): pano.html ile aynı dizinde; yoksa açık yayın atlanır. Ana Worker'ın site/ klasörüne KOPYALANMAZ.
ozet_json="${PANO_OZET_DOSYA:-$(dirname "$kaynak")/gunluk_ozet_v1.json}"
acik_ad="${PANO_ACIK_AD:-1l3a-pano-acik}"
cd "$gecici"
export WRANGLER_SEND_METRICS=false
acik_yayinla() {
  local mut_json="${PANO_MUTABAKAT_DOSYA:-$(dirname "$kaynak")/mutabakat_v1.json}"
  [ -s "$ozet_json" ] || [ -s "$mut_json" ] || { echo "günlük özet ve mutabakat yok, açık yayın atlandı"; return 0; }
  local d="$gecici/acik"
  mkdir -p "$d/site"
  [ -s "$ozet_json" ] && cp "$ozet_json" "$d/site/gunluk_ozet_v1.json"
  [ -s "$mut_json" ] && cp "$mut_json" "$d/site/mutabakat_v1.json"
  cp "$betik_dizin/pano_acik_worker.js" "$d/pano_acik_worker.js"
  cat > "$d/wrangler.jsonc" <<JSON
{
  "name": "$acik_ad",
  "main": "pano_acik_worker.js",
  "compatibility_date": "2026-11-01",
  "workers_dev": true,
  "assets": { "directory": "site", "binding": "ASSETS", "run_worker_first": true }
}
JSON
  (cd "$d" && timeout -k 10 180 wrangler deploy --config wrangler.jsonc)
  echo "açık günlük özet yayımlandı ($acik_ad): $(date -u +%FT%TZ)"
}
if [ "$kilitsiz" = 1 ]; then
  # şifresiz: yalnız statik sayfa; önbelleğe alınmasın, arama motoru dizinlemesin
  printf '/*\n  Cache-Control: private, no-store\n  X-Robots-Tag: noindex\n  Content-Security-Policy: frame-ancestors '\''self'\'' https://orkestra-kapi.sselimgenc-c18.workers.dev\n' > "$gecici/site/_headers"
  cat > "$gecici/wrangler.jsonc" <<JSON
{
  "name": "$ad",
  "compatibility_date": "2026-11-01",
  "workers_dev": true,
  "assets": { "directory": "site" }
}
JSON
  timeout -k 10 180 wrangler deploy --config wrangler.jsonc
  echo "pano yayımlandı (ŞİFRESİZ, PANO_KILITSIZ=1): $(date -u +%FT%TZ)"
  acik_yayinla
  exit 0
fi
cp "$betik_dizin/pano_worker.js" "$gecici/pano_worker.js"
cat > "$gecici/wrangler.jsonc" <<JSON
{
  "name": "$ad",
  "main": "pano_worker.js",
  "compatibility_date": "2026-11-01",
  "workers_dev": true,
  "assets": { "directory": "site", "binding": "ASSETS", "run_worker_first": true }$vars
}
JSON
timeout -k 10 180 wrangler deploy --config wrangler.jsonc
if [ -f "$hash_dosya" ]; then
  # eski Basic Auth secret'ı: kalmışsa zararsız; bir kez silmeyi dene, hatayı yut
  timeout -k 10 120 wrangler secret delete PANO_SIFRE --name "$ad" </dev/null >/dev/null 2>&1 || true
  rm -f "$hash_dosya"
fi
echo "pano yayımlandı: $(date -u +%FT%TZ)"
acik_yayinla
