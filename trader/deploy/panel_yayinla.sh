#!/usr/bin/env bash
# Panelin anlik goruntusunu uretir ve Cloudflare Workers'a yayimlar (Basic Auth arkasinda; bkz. docs/panel-spec.md §13).
# Fikir/yapi 1L3A deploy/pano_yayinla.sh'den uyarlandi (kullanicinin kendi kodu).
# Anahtarlar /etc/trader-panel-cf.env dosyasindan (systemd EnvironmentFile) gelir; bu betik onlari asla yazdirmaz.
# Parola Worker secret'idir (PANEL_SIFRE) ve bu betikten gecmez: kurulumda `wrangler secret put` ile bir kez konur.
# Istege bagli: TRADER_PANEL_WORKER (varsayilan trader-pano), TRADER_DIR, WRANGLER_BIN.
set -euo pipefail
: "${CLOUDFLARE_API_TOKEN:?CLOUDFLARE_API_TOKEN tanimli degil (/etc/trader-panel-cf.env)}"
: "${CLOUDFLARE_ACCOUNT_ID:?CLOUDFLARE_ACCOUNT_ID tanimli degil (/etc/trader-panel-cf.env)}"
export CLOUDFLARE_API_TOKEN CLOUDFLARE_ACCOUNT_ID
ad="${TRADER_PANEL_WORKER:-trader-pano}"
case "$ad" in *[!a-z0-9-]*|"") echo "HATA: Worker adi yalniz a-z 0-9 - olabilir" >&2; exit 1 ;; esac
betik_dizin="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
trader_dir="${TRADER_DIR:-$(cd "$betik_dizin/.." && pwd)}"
py="${TRADER_PY:-$trader_dir/.venv/bin/python}"
wrangler="${WRANGLER_BIN:-$trader_dir/var/wrangler/node_modules/.bin/wrangler}"
[ -x "$wrangler" ] || { echo "HATA: wrangler bulunamadi: $wrangler (install.sh calistirildi mi?)" >&2; exit 1; }
gecici="$(mktemp -d)"
trap 'rm -rf "$gecici"' EXIT
mkdir "$gecici/site"
cd "$trader_dir"
if ! PYTHONPATH="$trader_dir/src" "$py" -m trader_panel --config "$trader_dir/config/panel.json" snapshot --out "$gecici/site/index.html"; then
  echo "HATA: anlik goruntu uretilemedi $(date -u +%FT%TZ)" >&2
  exit 1
fi
[ -s "$gecici/site/index.html" ] || { echo "HATA: anlik goruntu bos" >&2; exit 1; }
cp "$betik_dizin/panel_worker.js" "$gecici/panel_worker.js"
cat > "$gecici/wrangler.jsonc" <<JSON
{
  "name": "$ad",
  "main": "panel_worker.js",
  "compatibility_date": "2026-11-01",
  "workers_dev": true,
  "assets": { "directory": "site", "binding": "ASSETS", "run_worker_first": true }
}
JSON
cd "$gecici"
export WRANGLER_SEND_METRICS=false
if ! timeout -k 10 180 "$wrangler" deploy --config wrangler.jsonc >"$gecici/cikti.log" 2>&1; then
  # wrangler ciktisi anahtar icermez ama yine de yalniz son satirlar yazilir
  tail -n 5 "$gecici/cikti.log" >&2 || true
  echo "HATA: wrangler deploy basarisiz $(date -u +%FT%TZ)" >&2
  exit 1
fi
echo "panel yayimlandi: $(date -u +%FT%TZ)"
