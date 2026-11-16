#!/usr/bin/env bash
# Trader kaldirma: yalniz trader-* birimlerini durdurur/kaldirir. Veri ve kullanici kalir; --purge hepsini siler.
# Baska projeye, takasa, paketlere dokunmaz.
set -euo pipefail

TRADER_USER="trader"
TG_GROUP="trader-tg"
REPO_DIR="/home/${TRADER_USER}/SG-Github-AB-proje"
UNIT_DIR="/etc/systemd/system"
PURGE=0
for arg in "$@"; do
  case "$arg" in
    --purge) PURGE=1 ;;
    *) echo "Bilinmeyen secenek: $arg (kullanim: uninstall.sh [--purge])" >&2; exit 2 ;;
  esac
done
[ "$(id -u)" -eq 0 ] || { echo "HATA: root olarak calistirin." >&2; exit 1; }

echo "==> trader-* birimleri durduruluyor"
for u in $(systemctl list-unit-files 'trader-*' --no-legend --plain 2>/dev/null | awk '{print $1}'); do
  case "$u" in trader-*) systemctl disable --now "$u" >/dev/null 2>&1 || true ;; esac
done
for f in "$UNIT_DIR"/trader-*.service "$UNIT_DIR"/trader-*.timer; do
  [ -e "$f" ] && rm -f "$f"
done
rm -f /etc/sysctl.d/99-trader-swappiness.conf
systemctl daemon-reload
systemctl reset-failed >/dev/null 2>&1 || true
echo "Birimler kaldirildi. Veri ($REPO_DIR, /etc/trader-*.env, /var/backups/trader) korunuyor."

if [ "$PURGE" -eq 1 ]; then
  echo "==> --purge: veri siliniyor"
  rm -rf "$REPO_DIR" /var/backups/trader /var/lib/trader-health
  rm -f /etc/trader-health.env /etc/trader-lesson.env /etc/trader-telegram.env /etc/trader-veto.env
  id "$TRADER_USER" >/dev/null 2>&1 && userdel -r "$TRADER_USER" 2>/dev/null || true
  getent group "$TG_GROUP" >/dev/null && groupdel "$TG_GROUP" 2>/dev/null || true
  echo "Takas dosyasi (/swapfile) bilerek silinmedi (baska proje kullaniyor olabilir)."
fi
echo "Bitti."
