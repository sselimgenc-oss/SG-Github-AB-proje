#!/usr/bin/env bash
# Canli duman testi sarmalayicisi (DD-9 §6.6). Root calistirir. Anahtar dosyasi 0600 root oldugundan trader kullanicisi onu OKUYAMAZ;
# bu yuzden duman testi systemd-run ile, anahtar dosyasi systemd tarafindan (root olarak) ortama yuklenerek trader kimliginde calisir.
# Bu betik anahtarlari OKUMAZ, YAZDIRMAZ. Kullanim: bash canli_duman.sh [smoke_live.py secenekleri]
set -euo pipefail

TRADER_DIR="${TRADER_DIR:-/home/trader/SG-Github-AB-proje/trader}"

[ "$(id -u)" -eq 0 ] || { echo "HATA: root olarak calistirin." >&2; exit 1; }
[ -f /etc/trader-live.env ] || { echo "HATA: /etc/trader-live.env yok (once install.sh ile kurun ve dosyayi nano ile doldurun)." >&2; exit 1; }

exec systemd-run --pty --wait --collect -p User=trader -p Group=trader -p WorkingDirectory="$TRADER_DIR" \
  -p EnvironmentFile=/etc/trader-live.env -p Environment=PYTHONPATH="$TRADER_DIR/src" \
  "$TRADER_DIR/.venv/bin/python" scripts/smoke_live.py --env live "$@"
