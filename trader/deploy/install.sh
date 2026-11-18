#!/usr/bin/env bash
# Trader sunucu kurulumu (Ubuntu 22.04+/24.04, root olarak, etkilesimsiz, tekrar calistirilabilir).
# Kullanim: bash install.sh [--no-twin]   (ikiz (twin) VARSAYILAN ACIK; --with-twin geriye uyumluluk icin kabul edilir, etkisizdir)
# Yalniz "trader" kullanicisina ve trader-* systemd birimlerine dokunur; baska projeye, guvenlik duvarina, acik porta dokunmaz.
set -euo pipefail
SELF_SUM_AT_START="$(sha256sum "$0" 2>/dev/null | cut -d" " -f1 || true)"   # depo guncellenince yeni betikle yeniden baslamak icin

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
  # github.com ana makine anahtarlari sabit (TOFU/accept-new yok). Kaynak: GitHub "SSH key fingerprints" belgesi ve
  # https://api.github.com/meta (ssh_keys); parmak izleri: ed25519 SHA256:+DiY3wvvV6TuJJhbpZisF/zLDA0zPMSvHdkr4UvCOqU,
  # ecdsa SHA256:p2QAMXNIC1TJYWeIOttrVc98/R1BUFWu3/LiyKgUfQM, rsa SHA256:uNiVztksCsDhcc0u9e8BujQXVUpKZIDTMczCvj3tD2s
  GH_KNOWN_HOSTS="${HOME_DIR}/.ssh/github_known_hosts"
  cat > "$GH_KNOWN_HOSTS" <<'KEYS'
github.com ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAIOMqqnkVzrm0SdG6UOoqKLsabgH5C9okWi0dh2l9GKJl
github.com ecdsa-sha2-nistp256 AAAAE2VjZHNhLXNoYTItbmlzdHAyNTYAAAAIbmlzdHAyNTYAAABBBEmKSENjQEezOmxkZMy7opKgwFB9nkt5YRrYMjNuG5N87uRgg6CLrbo5wAdT/y6v0mKV0U2w0WZ2YB/++Tpockg=
github.com ssh-rsa AAAAB3NzaC1yc2EAAAADAQABAAABgQCj7ndNxQowgcQnjshcLrqPEiiphnt+VTTvDP6mHBL9j1aNUkY4Ue1gvwnGLVlOhGeYrnZaMgRK6+PKCUXaDbC7qtbW8gIkhL7aGCsOr/C56SJMy/BCZfxd1nWzAOxSDPgVsmerOBYfNqltV9/hWCqBywINIR+5dIg6JTJ72pcEpEjcYgXkE2YEFXV1JHnsKgbLWNlhScqb2UmyRkQyytRLtL+38TGxkxCflmO+5Z8CSSNY7GidjMIZ7Q4zMjA2n1nGrlTDkzwDCsw+wqFPGQA179cnfGWOWRVruj16z6XyvxvjJwbz0wQZ75XK5tKSb7FNyeIEs4TT4jk+S4dhPeAUC5y+bDYirYgM4GC7uEnztnZyaVWQ7B381AK4Qdrwt51ZqExKbQpTUNn+EjqoTwvqNj4kqx5QUCI0ThS/YkOxJCXmPUWZbhjpCg56i+2aB6CmK2JGhn57K5mj0MNdBXA4/WnwH6XoPWJzK5Nyu2zB3nAZp+S5hpQs+p1vN1/wsjk=
KEYS
  chown "$TRADER_USER:$TRADER_USER" "$GH_KNOWN_HOSTS"; chmod 644 "$GH_KNOWN_HOSTS"
  export GIT_SSH_COMMAND="ssh -i ${DEPLOY_KEY} -o IdentitiesOnly=yes -o StrictHostKeyChecking=yes -o UserKnownHostsFile=${GH_KNOWN_HOSTS}"
  CLONE_URL="$REPO_SSH_URL"
  echo "Deploy anahtari bulundu; SSH ile cekiliyor."
else
  CLONE_URL="$REPO_URL"
fi
# WP-3 (defter sema 4): sema goci YALNIZ motor sureciyle (yazar, premigrate yedegi) yapilir; okuyucular (saglik, ders, sapma,
# karsi-olgu, telegram, pano) salt okunur acar ve gocu calistirmaz. Bu yuzden kod degistiyse calisan motorlar sonda yeniden
# baslatilir. Eski kodun HEAD'i yeniden-calistirmada (exec) kaybolmasin diye ortamda tasinir.
CODE_CHANGED=0
if [ -d "$REPO_DIR/.git" ]; then
  OLD_HEAD="${TRADER_OLD_HEAD:-$(as_trader git -C "$REPO_DIR" rev-parse HEAD 2>/dev/null || true)}"
  export TRADER_OLD_HEAD="$OLD_HEAD"
else
  OLD_HEAD=""
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
NEW_HEAD="$(as_trader git -C "$REPO_DIR" rev-parse HEAD 2>/dev/null || true)"
if [ -z "$OLD_HEAD" ] || [ "$OLD_HEAD" != "$NEW_HEAD" ]; then CODE_CHANGED=1; fi
# Bash calisan betigi bellekte eski haliyle surdurur; depo guncellemesi install.sh'i degistirdiyse yeni surumle bastan calistir (bir kez).
NEW_SELF="$TRADER_DIR/deploy/install.sh"
if [ -z "${TRADER_INSTALL_REEXEC:-}" ] && [ -f "$NEW_SELF" ] && [ "$(sha256sum "$NEW_SELF" | cut -d" " -f1)" != "$SELF_SUM_AT_START" ]; then
  say "install.sh guncellendi; yeni surumle yeniden baslatiliyor"
  export TRADER_INSTALL_REEXEC=1
  exec bash "$NEW_SELF" "$@"
fi

# ---- 5. python ortami (yalniz calisma bagimliliklari) -----------------------------
say "Python ortami (birkac dakika surebilir)"
[ -x "$TRADER_DIR/.venv/bin/python" ] || as_trader "$PY_BIN" -m venv "$TRADER_DIR/.venv"
as_trader "$TRADER_DIR/.venv/bin/python" -m pip install --quiet --disable-pip-version-check --upgrade pip
# trader/src ve trader/scripts icindeki iceri aktarmalardan: requests pandas numpy pyarrow anthropic (ccxt YOK: dis cati yasak)
# (dis ticaret cercevesi, pytest ve diger gelistirme paketleri KURULMAZ)
# Surum + sha256 sabit: requirements.lock (CPython 3.12, linux x86_64); --require-hashes kaymayi/degisikligi reddeder.
as_trader "$TRADER_DIR/.venv/bin/python" -m pip install --quiet --disable-pip-version-check \
  --require-hashes -r "$TRADER_DIR/requirements.lock"

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
  "$TRADER_DIR/user_data" "$TRADER_DIR/var/history" \
  "$TRADER_DIR/var/telegram" "$TRADER_DIR/var-testnet" "$TRADER_DIR/shared/testnet"
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
# testnet golge motoru anahtarlari: AYRI dosya (canli anahtar dosyasi degil); anahtarlar bos kalirsa birim acilmaz (WP-B8)
copy_env "$TRADER_DIR/deploy/trader-testnet.env.example"  /etc/trader-testnet.env  "root:root"           0600
chmod 0600 /etc/trader-testnet.env; chown root:root /etc/trader-testnet.env
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
# sapma izleyicisi kancasi (saglik-spec 16.6): izleyici birimleri kuruldugu icin drift_check_enabled acilir; bos/eksik ise 1 yazilir, kullanici degeri korunur
if ! grep -q '^DRIFT_CHECK_ENABLED=' /etc/trader-health.env; then
  # dosya sonunda satir sonu yoksa once ekle (son satirin sonuna yapismasin)
  if [ -s /etc/trader-health.env ] && [ -n "$(tail -c1 /etc/trader-health.env)" ]; then echo >> /etc/trader-health.env; fi
  echo "DRIFT_CHECK_ENABLED=1" >> /etc/trader-health.env
fi
sed -i "s#^DRIFT_CHECK_ENABLED=\$#DRIFT_CHECK_ENABLED=1#" /etc/trader-health.env
# beklenen motorlar (ikiz varsayilan acik); her calistirmada guncellenir: --no-twin ile learner
if [ "$WITH_TWIN" -eq 1 ]; then HEALTH_BOTS_VAL="learner,twin"; else HEALTH_BOTS_VAL="learner"; fi
if grep -q '^HEALTH_BOTS=' /etc/trader-health.env; then
  sed -i "s#^HEALTH_BOTS=.*#HEALTH_BOTS=${HEALTH_BOTS_VAL}#" /etc/trader-health.env
else
  echo "HEALTH_BOTS=${HEALTH_BOTS_VAL}" >> /etc/trader-health.env
fi
# /durdur her beklenen botun PAUSE dosyasina yazar (11 §9.5): --no-twin ile yalniz learner (olmayan ikize dosya acilmaz)
if grep -q '^PAUSE_BOTS=' /etc/trader-telegram.env; then
  sed -i "s#^PAUSE_BOTS=.*#PAUSE_BOTS=${HEALTH_BOTS_VAL}#" /etc/trader-telegram.env
else
  echo "PAUSE_BOTS=${HEALTH_BOTS_VAL}" >> /etc/trader-telegram.env
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
HIST="$TRADER_DIR/var/history"
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
# kod degistiyse yeniden baslatilacak, su an CALISAN motor birimleri (enable_now'dan once alinir; yeni acilanlar zaten yeni kodla baslar)
ACTIVE_ENGINES=""
if [ "$CODE_CHANGED" -eq 1 ]; then
  ACTIVE_ENGINES="$(systemctl list-units 'trader-engine@*.service' 'trader-engine-testnet.service' --state=active --no-legend --plain 2>/dev/null | awk '{print $1}' || true)"
fi
enable_now() { systemctl enable --now "$1" >/dev/null 2>&1 && echo "Etkin: $1" || echo "UYARI: $1 baslatilamadi (systemctl status $1)"; }

enable_now trader-feed.service     # veri akisi once: motor kural + taze veri gormeden baslamaz (acilis kapisi)
enable_now trader-engine@learner.service
if [ "$WITH_TWIN" -eq 1 ]; then enable_now trader-engine@twin.service; else echo "Ikiz (twin) kapali (--no-twin): acmak icin 'bash $TRADER_DIR/deploy/install.sh' (varsayilan acik)."; fi
enable_now trader-health.timer
enable_now trader-engine-retry@learner.timer   # acilis kapisi (cikis 7) yeniden deneme: besleme saglikliyse, saatte en fazla 6
if [ "$WITH_TWIN" -eq 1 ]; then enable_now trader-engine-retry@twin.timer; fi
enable_now trader-backup.timer
enable_now trader-oi.timer   # ML-G7: OI/long-short orani toplayici (5 dk; salt okunur Binance uclari, anahtar yok); var/market.sqlite positioning_5m
drift_first_run() { # var/<bot> dizinini hazirla ve ilk olcumu hemen al (yoksa saglik 20:20'ye kadar yanlis drift_missing der)
  install -d -o "$TRADER_USER" -g "$TRADER_USER" "$TRADER_DIR/var/$1"
  systemctl start "trader-drift@$1.service" || true
}
enable_now trader-drift@learner.timer; drift_first_run learner   # gunluk sapma izleyicisi (WP-2; 20:20 TSI, salt okunur; var/<bot>/drift.json tek yazar; Telegram'a mesaj atmaz)
enable_now trader-counterfactual@learner.timer   # alinmayan sinyal gece isi (23:10 UTC); defter/market salt okunur, var/<bot>/counterfactual.sqlite tek yazar
if [ "$WITH_TWIN" -eq 1 ]; then enable_now trader-counterfactual@twin.timer; enable_now trader-drift@twin.timer; drift_first_run twin; fi
enable_now trader-panel.service   # salt okunur pano: yalniz 127.0.0.1:8787, anahtar gerekmez

# WP-3: motor (yazar) yeni kodla yeniden baslar => defter sema gocu motor icinde, premigrate yedegiyle olur
if [ "$CODE_CHANGED" -eq 1 ] && [ -n "$ACTIVE_ENGINES" ]; then
  say "Kod degisti: calisan motorlar yeniden baslatiliyor (defter sema gocu motor icinde yapilir)"
  for u in $ACTIVE_ENGINES; do
    systemctl restart "$u" >/dev/null 2>&1 && echo "Yeniden baslatildi: $u" || echo "UYARI: $u yeniden baslatilamadi (systemctl status $u)"
  done
fi

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

# Testnet golge motoru (WP-B8): BINANCE_API_KEY ve BINANCE_API_SECRET ikisi de doluysa acilir (gercek para yok; yalniz testnet.binancefuture.com)
if has_value /etc/trader-testnet.env BINANCE_API_KEY && has_value /etc/trader-testnet.env BINANCE_API_SECRET; then
  # saglik denetcisi golge motoru da izler (stopsuz pozisyon / borsa erisimi); kullanici degeri korunur
  grep -q '^HEALTH_SHADOW_VAR_DIR=' /etc/trader-health.env || echo "HEALTH_SHADOW_VAR_DIR=" >> /etc/trader-health.env
  sed -i "s#^HEALTH_SHADOW_VAR_DIR=\$#HEALTH_SHADOW_VAR_DIR=${TRADER_DIR}/var-testnet#" /etc/trader-health.env
  enable_now trader-engine-testnet.service
else MISSING+=("/etc/trader-testnet.env  -> BINANCE_API_KEY ve BINANCE_API_SECRET (Binance Futures TESTNET anahtari; testnet golge motoru, ikisi de dolu olmadan acilmaz)"); fi

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
