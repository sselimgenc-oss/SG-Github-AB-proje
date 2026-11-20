"""Dış nabız (dead-man): sunucunun sağlığını Cloudflare Worker'a (deploy/nabiz_worker.js) 5 dakikada bir bildirir.

Worker sunucu DIŞINDA koşar; nabız kesilirse Telegram'a uyarı o gönderir. Bu modül yalnız POST eder:
  durum "iyi"           -> 1l3a-paper aktif ve paper kalp atışı <= 10 dk taze
  durum "paper_sorunlu" -> servis aktif değil ya da kalp bayat (kısa `neden` ile); 1l3a-canli aktifse `canli` bilgisi eklenir
Anahtar (NABIZ_ANAHTAR) ve adres (NABIZ_URL) YALNIZ ortamdan okunur; komut satırında/URL'de görünmez, başlıkla gider.
Ağ hatası loglanır ve çıkış kodu 0 kalır (systemd OnFailure seli olmasın).
Çalıştırma: python -m motor.canli.nabiz
"""
from __future__ import annotations

import json
import logging
import os
import subprocess
import sys
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, Optional

from motor.canli import kalp_atisi as kh

log = logging.getLogger("nabiz")
BAYAT_SN = 600
DURUM_DIZIN = "/var/lib/1l3a-paper/durum"


def servis_aktif_mi(ad: str) -> bool:
    try:
        r = subprocess.run(["systemctl", "is-active", "--quiet", ad], timeout=10)
        return r.returncode == 0
    except Exception as e:  # noqa: BLE001
        log.warning("systemctl is-active %s başarısız: %s", ad, e)
        return False


def _utc(z: str) -> datetime:
    return datetime.strptime(z, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)


def govde_uret(simdi: datetime, paper_aktif: bool, canli_aktif: bool, durum_dizin=DURUM_DIZIN) -> dict:
    """Saf mantık: -> Worker'a gidecek gövde sözlüğü."""
    govde = {"proje": "1l3a", "zaman": simdi.strftime("%Y-%m-%dT%H:%M:%SZ"), "durum": "iyi"}
    neden = None
    if not paper_aktif:
        neden = "1l3a-paper servisi aktif değil"
    else:
        try:
            k = kh.oku(durum_dizin)
            if k is None:
                neden = "kalp atışı dosyası yok"
            else:
                yas = int((simdi - _utc(k["zaman"])).total_seconds())
                if yas > BAYAT_SN:
                    neden = f"kalp bayat {yas // 60} dk"
        except Exception as e:  # noqa: BLE001  (bozuk dosya vb.: sağlıksız say, nedenini yaz)
            neden = f"kalp atışı okunamadı ({type(e).__name__})"
    if neden:
        govde["durum"], govde["neden"] = "paper_sorunlu", neden
    if canli_aktif:
        govde["canli"] = "aktif"
    return govde


def gonder(govde: dict, url: str, anahtar: str, acici: Optional[Callable] = None) -> bool:
    istek = urllib.request.Request(url.rstrip("/") + "/nabiz", data=json.dumps(govde).encode(), method="POST",
                                   headers={"Content-Type": "application/json", "X-Nabiz-Anahtar": anahtar,
                                            "User-Agent": "1l3a-nabiz/1.0"})   # Cloudflare varsayılan Python-urllib kimliğini engelliyor
    try:
        with (acici or urllib.request.urlopen)(istek, timeout=20) as y:
            ok = 200 <= y.status < 300
        if not ok:
            log.warning("nabız reddedildi: HTTP %s", y.status)
        return ok
    except Exception as e:  # noqa: BLE001
        log.warning("nabız gönderilemedi (%s)", type(e).__name__)   # URL/anahtar loga yazılmaz
        return False


def main(env=None) -> int:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    env = os.environ if env is None else env
    url, anahtar = env.get("NABIZ_URL", "").strip(), env.get("NABIZ_ANAHTAR", "").strip()
    if not url or not anahtar:
        log.warning("NABIZ_URL / NABIZ_ANAHTAR tanımlı değil; nabız gönderilmedi")
        return 0
    govde = govde_uret(datetime.now(timezone.utc), servis_aktif_mi("1l3a-paper"), servis_aktif_mi("1l3a-canli"),
                       env.get("NABIZ_DURUM_DIZIN", DURUM_DIZIN))
    if gonder(govde, url, anahtar):
        log.info("nabız gönderildi: %s", govde["durum"])
    return 0   # ağ hatası servisi başarısız saymaz


if __name__ == "__main__":
    sys.exit(main())
