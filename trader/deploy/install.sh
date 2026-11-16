#!/usr/bin/env bash
# Trader sunucu kurulumu (Ubuntu 22.04+/24.04, root olarak, etkilesimsiz, tekrar calistirilabilir).
# Kullanim: bash install.sh [--with-twin]
# Yalniz "trader" kullanicisina ve trader-* systemd birimlerine dokunur; baska projeye, guvenlik duvarina, acik porta dokunmaz.
set -euo pipefail

# ---- ayarlar (gerekirse degistirin) ---------------------------------------
REPO_URL="${REPO_URL:-https://github.com/sselimgenc-oss/SG-Github-AB-proje.git}"
REPO_SSH_URL="${REPO_SSH_URL:-git@github.com:sselimgenc-oss/SG-Github-AB-proje.git}"
BRANCH="${BRANCH:-claude/charming-hawking-ab5w5q}"
TRADER_USER="trader"
TG_GROUP="trader-tg"
HOME_DIR="/home/${TRADER_USER}"
REPO_DIR="${HOME_DIR}/SG-Github-AB-proje"
TRADER_DIR="${REPO_DIR}/trader"
DEPLOY_KEY="${HOME_DIR}/.ssh/deploy_key"
SWAP_FILE="/swapfile"
SWAP_SIZE="4G"
UNIT_DIR="/etc/systemd/system"
WITH_TWIN=0

for arg in "$@"; do
  case "$arg" in
    --with-twin) WITH_TWIN=1 ;;
    *) echo "Bilinmeyen secenek: $arg (kullanim: install.sh [--with-twin])" >&2; exit 2 ;;
  esac
done

say()  { printf '\n==> %s\n' "$*"; }
fail() { printf '\nHATA: %s\n' "$*" >&2; exit 1; }

[ "$(id -u)" -eq 0 ] || fail "Bu betik root olarak calistirilmali (DigitalOcean konsolunda zaten rootsunuz)."

# ---- 0. Ubuntu / python kontrolu -------------------------------------------
say "Sistem kontrolu"
command -v apt-get >/dev/null || fail "Bu betik Ubuntu/Debian icindir."
command -v systemctl >/dev/null || fail "systemd bulunamadi."
PY_BIN="$(command -v python3 || true)"
if [ -z "$PY_BIN" ]; then
  DEBIAN_FRONTEND=noninteractive apt-get update -qq
  DEBIAN_FRONTEND=noninteractive apt-get install -y -qq python3
  PY_BIN="$(command -v python3)"
fi
if ! "$PY_BIN" -c 'import sys; sys.exit(0 if sys.version_info >= (3, 11) else 1)'; then
  fail "Sunucudaki Python surumu cok eski ($("$PY_BIN" --version 2>&1)); en az 3.11 gerekir (Ubuntu 24.04 uygundur). Hicbir sey kurulmadi/degistirilmedi. Lutfen bana bildirin, birlikte cozelim."
fi
echo "Python: $("$PY_BIN" --version 2>&1)"

# ---- 1. swap ------------------------------------------------------------------
say "Takas (swap)"
if [ -n "$(swapon --show --noheadings 2>/dev/null)" ]; then
  echo "Takas zaten var, dokunulmadi."
else
  if [ ! -e "$SWAP_FILE" ]; then
    fallocate -l "$SWAP_SIZE" "$SWAP_FILE" 2>/dev/null || dd if=/dev/zero of="$SWAP_FILE" bs=1M count=4096 status=none
    chmod 600 "$SWAP_FILE"
    mkswap "$SWAP_FILE" >/dev/null
  fi
  swapon "$SWAP_FILE"
  grep -qs "^${SWAP_FILE} " /etc/fstab || echo "${SWAP_FILE} none swap sw 0 0" >> /etc/fstab
  echo "4 GB takas olusturuldu."
fi
echo "vm.swappiness=10" > /etc/sysctl.d/99-trader-swappiness.conf
sysctl -q -p /etc/sysctl.d/99-trader-swappiness.conf >/dev/null || true

# ---- 2. kullanici ve gruplar --------------------------------------------------
say "Kullanici ve gruplar"
getent group "$TG_GROUP" >/dev/null || groupadd --system "$TG_GROUP"
if ! id "$TRADER_USER" >/dev/null 2>&1; then
  useradd --create-home --home-dir "$HOME_DIR" --shell /usr/sbin/nologin "$TRADER_USER"
fi
usermod -aG "$TG_GROUP" "$TRADER_USER"
install -d -m 0750 -o "$TRADER_USER" -g "$TRADER_USER" "$HOME_DIR"

# ---- 3. paketler -----------------------------------------------------------------
say "Paketler (python3-venv, git, sqlite3)"
export DEBIAN_FRONTEND=noninteractive
apt-get update -qq
apt-get install -y -qq python3-venv git sqlite3 ca-certificates

# ---- 4. depo ------------------------------------------------------------------
say "Kod deposu"
as_trader() { runuser -u "$TRADER_USER" -- "$@"; }
if [ -f "$DEPLOY_KEY" ]; then
  chown "$TRADER_USER:$TRADER_USER" "$DEPLOY_KEY"; chmod 600 "$DEPLOY_KEY"
  export GIT_SSH_COMMAND="ssh -i ${DEPLOY_KEY} -o IdentitiesOnly=yes -o StrictHostKeyChecking=accept-new -o UserKnownHostsFile=${HOME_DIR}/.ssh/known_hosts"
  CLONE_URL="$REPO_SSH_URL"
  echo "Deploy anahtari bulundu; SSH ile cekiliyor."
else
  CLONE_URL="$REPO_URL"
fi
if [ -d "$REPO_DIR/.git" ]; then
  as_trader git -C "$REPO_DIR" fetch --quiet origin "$BRANCH"
  as_trader git -C "$REPO_DIR" checkout --quiet "$BRANCH" 2>/dev/null || as_trader git -C "$REPO_DIR" checkout --quiet -b "$BRANCH" "origin/$BRANCH"
  as_trader git -C "$REPO_DIR" merge --ff-only --quiet "origin/$BRANCH" || fail "Depo guncellenemedi (yerel degisiklik var?). $REPO_DIR icinde elle bakilmali."
else
  as_trader git clone --quiet --branch "$BRANCH" "$CLONE_URL" "$REPO_DIR" \
    || fail "Depo indirilemedi. Depo ozelse deploy anahtari gerekir: bkz. trader/docs/sunucu-kurulum.md"
fi
[ -d "$TRADER_DIR/deploy" ] || fail "$TRADER_DIR/deploy yok; dal/depo adi yanlis olabilir."

# ---- 5. python ortami (yalniz calisma bagimliliklari) -----------------------------
say "Python ortami (birkac dakika surebilir)"
[ -x "$TRADER_DIR/.venv/bin/python" ] || as_trader "$PY_BIN" -m venv "$TRADER_DIR/.venv"
as_trader "$TRADER_DIR/.venv/bin/python" -m pip install --quiet --disable-pip-version-check --upgrade pip
# trader/src ve trader/scripts icindeki iceri aktarmalardan: requests pandas numpy pyarrow anthropic (ccxt YOK: dis cati yasak)
# (freqtrade, pytest ve diger gelistirme paketleri KURULMAZ)
as_trader "$TRADER_DIR/.venv/bin/python" -m pip install --quiet --disable-pip-version-check \
  "requests>=2.31" "pandas>=2.2" "numpy>=1.26" "pyarrow>=15" "anthropic"

# ---- 6. dizinler -------------------------------------------------------------------
say "Dizinler"
install -d -m 0750 -o "$TRADER_USER" -g "$TRADER_USER" "$TRADER_DIR/var" "$TRADER_DIR/shared" "$TRADER_DIR/shared/veto" \
  "$TRADER_DIR/user_data" "$TRADER_DIR/user_data/data" "$TRADER_DIR/user_data/data/binance" "$TRADER_DIR/user_data/data/binance/futures" \
  "$TRADER_DIR/var/telegram"
install -d -m 2770 -o "$TRADER_USER" -g "$TG_GROUP" "$TRADER_DIR/var/telegram/outbox"
install -d -m 0750 -o root -g root /var/backups/trader

# ---- 7. env dosyalari (var olani asla ezme) -----------------------------------------
say "Ayar dosyalari (/etc/trader-*.env)"
copy_env() { # kaynak ornek, hedef, sahip:grup, mod
  local dst="$2"
  if [ -e "$dst" ]; then echo "Var, dokunulmadi: $dst"; return; fi
  install -m "$4" -o "${3%%:*}" -g "${3##*:}" "$1" "$dst"
  echo "Olusturuldu: $dst"
}
copy_env "$TRADER_DIR/deploy/trader-health.env.example"   /etc/trader-health.env   "root:${TG_GROUP}"    0640
copy_env "$TRADER_DIR/deploy/trader-lesson.env.example"   /etc/trader-lesson.env   "root:${TRADER_USER}" 0640
copy_env "$TRADER_DIR/deploy/trader-telegram.env.example" /etc/trader-telegram.env "root:${TG_GROUP}"    0640
copy_env "$TRADER_DIR/deploy/trader-veto.env.example"     /etc/trader-veto.env     "root:root"           0600
# yol alanlarini bu sunucunun gercek yoluna cevir (yalniz /opt/trader on eki ve bos ENGINE_VAR_DIR)
for f in /etc/trader-health.env /etc/trader-lesson.env /etc/trader-telegram.env; do
  sed -i "s#/opt/trader/#${TRADER_DIR}/#g" "$f"
done
sed -i "s#^ENGINE_VAR_DIR=\$#ENGINE_VAR_DIR=${TRADER_DIR}/var#" /etc/trader-health.env

# ---- 8. systemd birimleri ---------------------------------------------------------
say "systemd birimleri"
render() { # ornek birim yollarini bu sunucuya uyarla
  sed -e "s#/home/trader/trader/var#${TRADER_DIR}/var#g" \
      -e "s#/opt/trader#${TRADER_DIR}#g" \
      -e "s#/usr/bin/python3#${TRADER_DIR}/.venv/bin/python#g" "$1" > "$2"
  chmod 0644 "$2"
}
for f in "$TRADER_DIR"/deploy/trader-*.service "$TRADER_DIR"/deploy/trader-*.timer; do
  render "$f" "${UNIT_DIR}/$(basename "$f")"
done
systemctl daemon-reload

# ---- 9. veri ---------------------------------------------------------------------
say "Gecmis veri"
HIST="$TRADER_DIR/user_data/data/binance/futures"
if [ -z "$(find "$HIST" -maxdepth 1 -name '*.feather' -print -quit 2>/dev/null)" ]; then
  echo "Veri yok; Binance acik arsivinden indiriliyor (yavas olabilir, sunucuyu yormaz)."
  systemd-run --quiet --wait --collect --unit=trader-fetch -p User="$TRADER_USER" -p Nice=15 -p MemoryMax=450M \
    -p WorkingDirectory="$TRADER_DIR" "$TRADER_DIR/.venv/bin/python" "$TRADER_DIR/scripts/fetch_binance_vision.py" --workers 2 \
    || echo "UYARI: veri indirme tamamlanamadi; install.sh'i yeniden calistirirsaniz kaldigi yerden devam eder."
else
  echo "Veri zaten var, atlandi."
fi

# ---- 10. servisleri baslat --------------------------------------------------------
say "Servisler"
has_value() { # dosyada ANAHTAR= bos degilse 0
  grep -Eq "^$2=[^[:space:]]+" "$1" 2>/dev/null
}
MISSING=()
enable_now() { systemctl enable --now "$1" >/dev/null 2>&1 && echo "Etkin: $1" || echo "UYARI: $1 baslatilamadi (systemctl status $1)"; }

enable_now trader-engine@learner.service
if [ "$WITH_TWIN" -eq 1 ]; then enable_now trader-engine@twin.service; else echo "Ikiz (twin) kapali: sonra 'bash $TRADER_DIR/deploy/install.sh --with-twin'."; fi
enable_now trader-health.timer
enable_now trader-backup.timer

if has_value /etc/trader-lesson.env ANTHROPIC_API_KEY_LESSON; then
  enable_now trader-lesson.timer
else MISSING+=("/etc/trader-lesson.env  -> ANTHROPIC_API_KEY_LESSON  (ders servisi)"); fi
if has_value /etc/trader-veto.env ANTHROPIC_API_KEY_VETO && has_value /etc/trader-veto.env TRADER_VETO_HMAC_KEY; then
  enable_now trader-veto.timer
else MISSING+=("/etc/trader-veto.env    -> ANTHROPIC_API_KEY_VETO ve TRADER_VETO_HMAC_KEY (veto)"); fi
if has_value /etc/trader-telegram.env TELEGRAM_BOT_TOKEN && has_value /etc/trader-telegram.env TELEGRAM_CHAT_ID; then
  enable_now trader-telegram.service
  enable_now trader-telegram-report.timer
else MISSING+=("/etc/trader-telegram.env -> TELEGRAM_BOT_TOKEN ve TELEGRAM_CHAT_ID (Telegram)"); fi

# ---- 11. ozet ---------------------------------------------------------------------
say "OZET"
echo "Calisan Trader birimleri:"
systemctl list-units 'trader-*' --no-legend --plain 2>/dev/null | awk '{print "  " $1 "  " $3 "/" $4}' || true
echo
echo "Bellek:"
free -m | awk 'NR==1 || /Mem:|Swap:/ {print "  " $0}'
echo
if [ "${#MISSING[@]}" -gt 0 ]; then
  echo "YAPILACAKLAR (anahtarlar doldurulmadan bu zamanlayicilar KAPALI birakildi):"
  for m in "${MISSING[@]}"; do echo "  - $m"; done
  echo "  Doldurduktan sonra bu komutu tekrar calistirin: bash $TRADER_DIR/deploy/install.sh"
  echo "  (Anahtarlari sohbete yazmayin; dosyayi nano ile acip degeri yapistirin.)"
fi
echo
echo "Durum: systemctl status trader-engine@learner   |   Kayit: journalctl -u trader-engine@learner -n 50"
echo "Kurulum bitti."
