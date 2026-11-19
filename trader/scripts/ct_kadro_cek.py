#!/usr/bin/env python3
"""C1 CT kadro okuyucu (belirtim: docs/motor/c1-ct-kadro-spec.md bolum 1). Anahtar/parola yok (herkese acik adres).

Her calistirmada adresi ceker (zaman asimi 20 sn, en fazla 1 MB; HTTP 200 disi -> hata), `ct.kadro_yon.v1` seklini dogrular.
Basarida `<var>/ct/kadro_yon.json` aynen yazilir (atomik). Her kosuda `<var>/ct/durum.json` yazilir; saglik uyarisi buradan okur.
Cikis: 0 (basarili ya da islenmis hata: durum.json'da kaydedilir), 2 (yerel yazma hatasi).
"""
from __future__ import annotations

import argparse
import json
import socket
import sys
import urllib.error
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path

_HERE = Path(__file__).resolve()
ROOT = _HERE.parent.parent
sys.path.insert(0, str(ROOT / "src"))

from trader_core import ct_kadro as CK  # noqa: E402
from trader_engine.fileio import atomic_write_text  # noqa: E402

KADRO_URL = "https://raw.githubusercontent.com/sselimgenc-oss/CT-Proje/canli-durum/durum/paylasim/kadro_yon_v1.json"
TIMEOUT_S = 20
MAX_BYTES = 1_000_000
EXIT_OK = 0
EXIT_YAZMA = 2


class CekHatasi(Exception):
    """Ag/HTTP/boyut hatasi: durum.json'a `son_hata` olarak yazilir."""


def getir(url: str, *, allow_http: bool = False) -> bytes:
    """Adresi ceker. Yalniz https (test stub'i icin `allow_http`). HTTP 200 disi, zaman asimi ya da 1 MB ustu -> CekHatasi."""
    if not allow_http and not url.startswith("https://"):
        raise CekHatasi("adres https degil")
    req = urllib.request.Request(url, headers={"User-Agent": "trader-ct-kadro/1", "Accept": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT_S) as r:    # noqa: S310 (adres https; yukarida denetlendi)
            if r.status != 200:
                raise CekHatasi(f"http {r.status}")
            data = r.read(MAX_BYTES + 1)
    except urllib.error.HTTPError as e:
        raise CekHatasi(f"http {e.code}") from None
    except (urllib.error.URLError, socket.timeout, TimeoutError, OSError) as e:
        raise CekHatasi(f"ag hatasi: {type(e).__name__}") from None
    if len(data) > MAX_BYTES:
        raise CekHatasi("yanit 1 MB sinirini asti")
    return data


def _durum_oku(path: Path) -> dict:
    try:
        d = json.loads(path.read_text(encoding="utf-8"))
        return d if isinstance(d, dict) else {}
    except (OSError, ValueError):
        return {}


def kos(url: str, var_dir: Path, now: datetime, *, allow_http: bool = False) -> int:
    """Bir tur: cek, dogrula, yaz. Basari = gecerli belge VE uretildi_utc en fazla 45 dk eski (aksi halde son_hata)."""
    ct = var_dir / "ct"
    ct.mkdir(parents=True, exist_ok=True)
    onceki = _durum_oku(ct / "durum.json")
    son_basari = onceki.get("son_basari") if isinstance(onceki.get("son_basari"), str) else None
    durum: dict = {"son_deneme": CK.zaman_yaz(now), "son_basari": son_basari, "son_hata": None, "gecersiz_oge": 0}
    try:
        raw = getir(url, allow_http=allow_http)
        text = raw.decode("utf-8")
        doc = json.loads(text)
        uretildi, _, gecersiz = CK.dogrula_belge(doc)
        durum["gecersiz_oge"] = gecersiz
        atomic_write_text(ct / "kadro_yon.json", text)
        if now - uretildi > timedelta(minutes=CK.AZAMI_YAS_DK):
            durum["son_hata"] = f"uretildi_utc bayat: {CK.zaman_yaz(uretildi)}"
        else:
            durum["son_basari"] = CK.zaman_yaz(now)
    except (CekHatasi, ValueError, CK.KadroHatasi) as e:      # UnicodeDecodeError, JSONDecodeError ValueError'dur
        durum["son_hata"] = str(e)[:200] or type(e).__name__
    try:
        atomic_write_text(ct / "durum.json", json.dumps(durum, ensure_ascii=False, sort_keys=True) + "\n")
    except OSError:
        return EXIT_YAZMA
    return EXIT_OK


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="C1 CT kadro okuyucu (5 dakikada bir; ag: yalniz https okuma)")
    ap.add_argument("--var-dir", type=Path, default=ROOT / "var", help="cikti koku; <var>/ct altina yazar")
    ap.add_argument("--url", default=KADRO_URL, help="kaynak adresi (varsayilan: CT yayini)")
    a = ap.parse_args(argv)
    try:
        return kos(a.url, a.var_dir, datetime.now(timezone.utc))
    except OSError:
        print("ct_kadro_cek: yerel yazma hatasi", file=sys.stderr)
        return EXIT_YAZMA


if __name__ == "__main__":
    sys.exit(main())
