#!/usr/bin/env bash
# Trader sunucu kurulumu (Ubuntu 22.04+/24.04, root olarak, etkilesimsiz, tekrar calistirilabilir).
# Kullanim: bash install.sh [--no-twin]   (ikiz (twin) VARSAYILAN ACIK; --with-twin geriye uyumluluk icin kabul edilir, etkisizdir)
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
WITH_TWIN=1

for arg in "$@"; do
  case "$arg" in
    --with-twin) WITH_TWIN=1 ;;   # geriye uyumluluk: varsayilan zaten acik
    --no-twin) WITH_TWIN=0 ;;
    *) echo "Bilinmeyen secenek: $arg (kullanim: install.sh [--no-twin])" >&2; exit 2 ;;
  esac
done

say()  { printf '\n==> %s\n' "$*"; }
fail() { printf '\nHATA: %s\n' "$*" >&2; exit 1; }

[ "$(id -u)" -eq 0 ] || fail "Bu betik root olarak calistirilmali (DigitalOcean konsolunda zaten rootsunuz)."

# ---- 0. Ubuntu / python kontrolu -------------------------------------------
say "Sistem kontrolu"
echo "Bellek (kurulumdan once; diger projenin payini dusunun):"
free -m | awk 'NR==1 || /Mem:|Swap:/ {print "  " $0}'
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
say "Paketler (python3-venv, git, sqlite3, openssl)"
export DEBIAN_FRONTEND=noninteractive
apt-get update -qq
apt-get install -y -qq python3-venv git sqlite3 ca-certificates openssl

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

# ---- 5b. Node + wrangler (yalniz panel yayini icin; yalniz eksikse kurulur, global degil) ------------------
say "Node/npm ve wrangler (Cloudflare yayini)"
WRANGLER_VERSION="3.114.0"      # sabit surum (kayan 'latest' yok)
WRANGLER_DIR="$TRADER_DIR/var/wrangler"
if ! command -v node >/dev/null 2>&1 || ! command -v npm >/dev/null 2>&1; then
  apt-get install -y -qq nodejs npm
fi
install -d -m 0750 -o "$TRADER_USER" -g "$TRADER_USER" "$TRADER_DIR/var" "$WRANGLER_DIR"
if [ "$(as_trader cat "$WRANGLER_DIR/node_modules/wrangler/package.json" 2>/dev/null | grep -o '"version": *"[^"]*"' | head -1 | grep -o '[0-9][0-9.]*')" != "$WRANGLER_VERSION" ]; then
  ( cd "$WRANGLER_DIR" && as_trader env HOME="$HOME_DIR" npm install --no-audit --no-fund --silent --prefix "$WRANGLER_DIR" "wrangler@${WRANGLER_VERSION}" ) \
    || echo "UYARI: wrangler kurulamadi; install.sh'i yeniden calistirin (panel yayini bu olmadan calismaz)."
else
  echo "wrangler ${WRANGLER_VERSION} zaten kurulu."
fi

# ---- 6. dizinler -------------------------------------------------------------------
say "Dizinler"
install -d -m 0750 -o "$TRADER_USER" -g "$TRADER_USER" "$TRADER_DIR/var" "$TRADER_DIR/shared" "$TRADER_DIR/shared/veto" \
  "$TRADER_DIR/user_data" "$TRADER_DIR/user_data/data" "$TRADER_DIR/user_data/data/binance" "$TRADER_DIR/user_data/data/binance/futures" \
  "$TRADER_DIR/var/telegram"
install -d -m 2770 -o "$TRADER_USER" -g "$TG_GROUP" "$TRADER_DIR/var/telegram/outbox"
install -d -m 0750 -o root -g root /var/backups/trader
# budget.sqlite'i trader sahipli onceden olustur (yoksa): ilk olusturan veto (root) olursa dosya root:root 0600 kalir ve ders/telegram acamaz (OPEN-8).
# Sifir bayt dosya gecerlidir: budget.py bos dosyayi 'ilk olusturma' sayip semayi kendisi kurar.
if [ ! -e "$TRADER_DIR/user_data/budget.sqlite" ]; then
  install -m 0600 -o "$TRADER_USER" -g "$TRADER_USER" /dev/null "$TRADER_DIR/user_data/budget.sqlite"
fi

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
copy_env "$TRADER_DIR/deploy/trader-veto-hmac.env.example" /etc/trader-veto-hmac.env "root:root"          0600
copy_env "$TRADER_DIR/deploy/trader-panel-cf.env.example" /etc/trader-panel-cf.env "root:root"           0600
# veto HMAC anahtari: bos ise otomatik uret (ekrana YAZILMAZ); veto birimi imzalar, motor dogrular
if ! grep -Eq '^TRADER_VETO_HMAC_KEY=[^[:space:]]+' /etc/trader-veto-hmac.env; then
  HMAC_NEW="$(openssl rand -hex 32)"
  sed -i '/^TRADER_VETO_HMAC_KEY=/d' /etc/trader-veto-hmac.env
  printf 'TRADER_VETO_HMAC_KEY=%s\n' "$HMAC_NEW" >> /etc/trader-veto-hmac.env
  unset HMAC_NEW
  chmod 0600 /etc/trader-veto-hmac.env
  echo "Uretildi: /etc/trader-veto-hmac.env (veto HMAC anahtari; gosterilmez)"
fi
# yol alanlarini bu sunucunun gercek yoluna cevir (yalniz /opt/trader on eki ve bos ENGINE_VAR_DIR)
for f in /etc/trader-health.env /etc/trader-lesson.env /etc/trader-telegram.env; do
  sed -i "s#/opt/trader/#${TRADER_DIR}/#g" "$f"
done
sed -i "s#^ENGINE_VAR_DIR=\$#ENGINE_VAR_DIR=${TRADER_DIR}/var#" /etc/trader-health.env
# piyasa verisi alarmlari varsayilan acik (bos ise doldur; kullanici degeri korunur)
sed -i "s#^MARKET_DB=\$#MARKET_DB=${TRADER_DIR}/var/market.sqlite#" /etc/trader-health.env
sed -i "s#^ENGINE_CONFIG_DIR=\$#ENGINE_CONFIG_DIR=${TRADER_DIR}/config#" /etc/trader-health.env
# beklenen motorlar (ikiz varsayilan acik); her calistirmada guncellenir: --no-twin ile learner
if [ "$WITH_TWIN" -eq 1 ]; then HEALTH_BOTS_VAL="learner,twin"; else HEALTH_BOTS_VAL="learner"; fi
if grep -q '^HEALTH_BOTS=' /etc/trader-health.env; then
  sed -i "s#^HEALTH_BOTS=.*#HEALTH_BOTS=${HEALTH_BOTS_VAL}#" /etc/trader-health.env
else
  echo "HEALTH_BOTS=${HEALTH_BOTS_VAL}" >> /etc/trader-health.env
fi

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
# trader.slice: tum birimlerin ortak bellek tavani (GECICI sayilar; soak'te 48 saatlik olcumle kesinlesir). 'trader-*' glob'una girmez, ayrica kurulur.
render "$TRADER_DIR/deploy/trader.slice" "${UNIT_DIR}/trader.slice"
systemctl daemon-reload

# ---- 9. veri ---------------------------------------------------------------------
say "Gecmis veri"
HIST="$TRADER_DIR/user_data/data/binance/futures"
if [ -z "$(find "$HIST" -maxdepth 1 -name '*.feather' -print -quit 2>/dev/null)" ]; then
  echo "Veri yok; Binance acik arsivinden indiriliyor (yavas olabilir, sunucuyu yormaz)."
  systemd-run --quiet --wait --collect --unit=trader-fetch -p User="$TRADER_USER" -p Nice=15 -p MemoryMax=450M -p Slice=trader.slice \
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

enable_now trader-feed.service     # veri akisi once: motor kural + taze veri gormeden baslamaz (acilis kapisi)
enable_now trader-engine@learner.service
if [ "$WITH_TWIN" -eq 1 ]; then enable_now trader-engine@twin.service; else echo "Ikiz (twin) kapali (--no-twin): acmak icin 'bash $TRADER_DIR/deploy/install.sh' (varsayilan acik)."; fi
enable_now trader-health.timer
enable_now trader-engine-retry@learner.timer   # acilis kapisi (cikis 7) yeniden deneme: besleme saglikliyse, saatte en fazla 6
if [ "$WITH_TWIN" -eq 1 ]; then enable_now trader-engine-retry@twin.timer; fi
enable_now trader-backup.timer
enable_now trader-counterfactual@learner.timer   # alinmayan sinyal gece isi (23:10 UTC); defter/market salt okunur, var/<bot>/counterfactual.sqlite tek yazar
if [ "$WITH_TWIN" -eq 1 ]; then enable_now trader-counterfactual@twin.timer; fi
enable_now trader-panel.service   # salt okunur pano: yalniz 127.0.0.1:8787, anahtar gerekmez

TG_OK=0
if has_value /etc/trader-telegram.env TELEGRAM_BOT_TOKEN && has_value /etc/trader-telegram.env TELEGRAM_CHAT_ID; then
  TG_OK=1
  enable_now trader-telegram.service
  enable_now trader-telegram-report.timer
  # saglik uyarilari Telegram'a: anahtarlar tamam oldugunda NOTIFIER=auto zaten telegram'i secer (ornek dosyada auto); log kalmissa auto yap
  sed -i 's#^NOTIFIER=log$#NOTIFIER=auto#' /etc/trader-health.env
else MISSING+=("/etc/trader-telegram.env -> TELEGRAM_BOT_TOKEN ve TELEGRAM_CHAT_ID (Telegram)"); fi
# ders: Anthropic anahtari VE Telegram anahtarlari (config/lesson.json notifier=telegram; bildirimcisiz cikis 1)
if has_value /etc/trader-lesson.env ANTHROPIC_API_KEY_LESSON && [ "$TG_OK" -eq 1 ]; then
  enable_now trader-lesson.timer
else MISSING+=("/etc/trader-lesson.env  -> ANTHROPIC_API_KEY_LESSON ve Telegram anahtarlari (ders servisi; ikisi de dolu olmadan acilmaz)"); fi
# veto: Anthropic anahtari VE HMAC anahtari (HMAC'i install.sh uretir)
if has_value /etc/trader-veto.env ANTHROPIC_API_KEY_VETO && has_value /etc/trader-veto-hmac.env TRADER_VETO_HMAC_KEY; then
  enable_now trader-veto.timer
else MISSING+=("/etc/trader-veto.env    -> ANTHROPIC_API_KEY_VETO (veto; HMAC anahtari /etc/trader-veto-hmac.env'e otomatik uretilir)"); fi

# Saglik birimi HEARTBEAT_URL (https) olmadan her turda cikis 1 ile coker (zorunlu ortam degiskeni): bos birakilirsa uyar
if ! has_value /etc/trader-health.env HEARTBEAT_URL; then
  MISSING+=("/etc/trader-health.env   -> HEARTBEAT_URL (https:// dis nabiz adresi; ZORUNLU: bos iken trader-health her 5 dk basarisiz olur)"); fi

# Panel yayini: Cloudflare anahtarlari yer tutucuyken zamanlayici ACILMAZ
CF_TODO=()
if has_value /etc/trader-panel-cf.env CLOUDFLARE_API_TOKEN && has_value /etc/trader-panel-cf.env CLOUDFLARE_ACCOUNT_ID; then
  enable_now trader-panel-publish.timer
else
  CF_TODO+=("Cloudflare'da API token olusturun (Workers duzenleme yetkisi: 'Edit Cloudflare Workers' sablonu); token ve hesap kimligini /etc/trader-panel-cf.env dosyasina nano ile yazin (sohbete yazmayin)")
  CF_TODO+=("Worker'i bir kez olusturun (parola yokken HER istek 401 doner, guvenli): systemctl start trader-panel-publish.service")
  CF_TODO+=("Worker parolasi (en az 32 karakter rastgele): cd $TRADER_DIR/var/wrangler && set -a && . /etc/trader-panel-cf.env && set +a && ./node_modules/.bin/wrangler secret put PANEL_SIFRE --name trader-pano   (parola istenince yapistirin; ekrana yazilmaz, Cloudflare'da Worker sirri olarak saklanir)")
  CF_TODO+=("Yayini acin: systemctl enable --now trader-panel-publish.timer (ya da install.sh'i yeniden calistirin); workers.dev adresini yer imine ekleyin")
fi

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
if [ "${#CF_TODO[@]}" -gt 0 ]; then
  echo
  echo "PANO YAYINI (Cloudflare) icin siradaki adimlar (zamanlayici bunlar bitene kadar KAPALI):"
  for m in "${CF_TODO[@]}"; do echo "  - $m"; done
  echo "  Sonra: bash $TRADER_DIR/deploy/install.sh   (zamanlayiciyi kendisi acar)"
fi
echo
echo "Pano (telefon/bilgisayar): ssh -L 8787:127.0.0.1:8787 <kullanici>@<sunucu>  sonra tarayicida http://127.0.0.1:8787"
echo "Durum: systemctl status trader-engine@learner   |   Kayit: journalctl -u trader-engine@learner -n 50"
echo "Kurulum bitti."
