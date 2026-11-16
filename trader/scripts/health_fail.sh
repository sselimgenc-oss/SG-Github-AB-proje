#!/bin/bash
# OnFailure alarm betigi (docs/saglik-spec.md 8.4). Kullanim: health_fail.sh <basarisiz-birim>
# Yalniz logger + (varsa) HEARTBEAT_FAIL_URL'e GET. Adres komut satirina konmaz (curl --config stdin).
# Yapilandirma yoksa "atlandi" yazip 0 ile cikar: alarm zinciri ikinci hata uretmesin.
unit="${1:-bilinmeyen}"
unit="${unit//[^A-Za-z0-9@._:-]/_}"
logger -t trader-health-fail -p daemon.crit "birim basarisiz: ${unit}" 2>/dev/null || echo "birim basarisiz: ${unit}" >&2
url="${HEARTBEAT_FAIL_URL:-}"
if [ -z "$url" ]; then
  echo "trader-health-fail: HEARTBEAT_FAIL_URL yok, dis bildirim atlandi" >&2
  exit 0
fi
case "$url" in
  https://*) ;;
  *) echo "trader-health-fail: gecersiz adres, atlandi" >&2; exit 0 ;;
esac
if command -v curl >/dev/null 2>&1; then
  printf 'url = "%s"\n' "$url" | curl -sS --max-time 10 --max-redirs 0 -o /dev/null -K - >/dev/null 2>&1 \
    || echo "trader-health-fail: dis bildirim gonderilemedi" >&2
else
  echo "trader-health-fail: curl yok, atlandi" >&2
fi
exit 0
