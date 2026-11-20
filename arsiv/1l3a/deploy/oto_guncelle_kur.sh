#!/usr/bin/env bash
# 1L3A otomatik güncellemeyi BİR KEZ kurar (root). Kullanım: cd /opt/1l3a && git pull && bash deploy/oto_guncelle_kur.sh
set -euo pipefail
cd /opt/1l3a
[ "$(id -u)" -eq 0 ] || { echo "root olarak çalıştırın (sudo)"; exit 1; }
git -c safe.directory=/opt/1l3a pull --ff-only || true
chown -R l3a:l3a /opt/1l3a
for b in 1l3a-guncelle.service 1l3a-guncelle.timer 1l3a-guncelle-istek.path 1l3a-guncelle-istek.service; do
  cp "deploy/$b" /etc/systemd/system/
done
mkdir -p /var/lib/1l3a-guncelle && chmod 755 /var/lib/1l3a-guncelle
systemctl daemon-reload
systemctl enable --now 1l3a-guncelle.timer 1l3a-guncelle-istek.path
for s in 1l3a-paper 1l3a-ct-paper 1l3a-telegram 1l3a-canli; do
  if systemctl is-active --quiet "$s"; then systemctl restart "$s"; fi
done
sleep 5
systemctl list-timers 1l3a-guncelle.timer --no-pager || true
for s in 1l3a-paper 1l3a-ct-paper 1l3a-telegram 1l3a-canli 1l3a-guncelle.timer 1l3a-guncelle-istek.path; do
  printf '%-28s %s\n' "$s" "$(systemctl is-active "$s" || true)"
done
cd /opt/1l3a
echo "Tamam. Telegram a kurulum mesajı gitmez; /durum yazıp kod satırını kontrol edin."
