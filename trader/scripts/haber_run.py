#!/usr/bin/env python3
"""Haber/duygu toplayici (belirtim: docs/haber-etiketi-spec.md). Saatlik, tek seferlik; YALNIZ KAYIT (karar yoluna girmez).

Kaynaklar: alternative.me Fear & Greed + CoinDesk/Cointelegraph RSS (anahtarsiz, yalniz https okuma). Onbellegi
`<var>/durum/haber_v1.json` dosyasina atomik yazar. Kaynak hatasi yutulur, son onbellek korunur; hicbir kaynak
okunamazsa dosya yeniden yazilmaz (eski `uretim` bayatligi gosterir). Cikis: 0 (basarili ya da yutulmus hata), 2 (yerel yazma hatasi).
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

_HERE = Path(__file__).resolve()
ROOT = _HERE.parent.parent
sys.path.insert(0, str(ROOT / "src"))

from trader_core import haber as H  # noqa: E402
from trader_engine.fileio import atomic_write_text  # noqa: E402

EXIT_OK = 0
EXIT_YAZMA = 2


def kos(yol: Path, simdi_ms: int, getir_json=None, getir_metin=None) -> int:
    """Bir tur: onbellegi oku, kaynaklari oku, degisen varsa yaz."""
    onceki = H.dosya_oku(yol) or {}
    yeni = H.guncelle(onceki, simdi_ms, getir_json, getir_metin)
    if yeni == onceki:                      # hicbir kaynak okunamadi: dosyaya dokunma
        return EXIT_OK
    try:
        atomic_write_text(yol, json.dumps(H.belge_yap(yeni, simdi_ms), ensure_ascii=False, sort_keys=True) + "\n")
    except OSError:
        return EXIT_YAZMA
    return EXIT_OK


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Haber/duygu toplayici (saatlik; ag: yalniz https okuma; yalniz kayit)")
    ap.add_argument("--var-dir", type=Path, default=ROOT / "var", help="cikti koku; <var>/durum/haber_v1.json yazilir")
    a = ap.parse_args(argv)
    return kos(a.var_dir / "durum" / "haber_v1.json", int(datetime.now(timezone.utc).timestamp() * 1000))


if __name__ == "__main__":
    sys.exit(main())
