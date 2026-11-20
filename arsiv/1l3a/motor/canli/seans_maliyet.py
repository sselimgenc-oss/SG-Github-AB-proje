"""Seans bazlı kayma çarpanı (ABD hisse / emtia perp'leri). Tablo: stratejiler/seans_maliyet.json (ön kayıt, ölçüm yok = varsayım).

Çarpan yalnız kayma (kayma_bps, stop_kayma_bps) bileşenine uygulanır; komisyon, funding ve boyutlandırma değişmez. Kripto: 1.0.
Dosya okunamazsa / bozuksa ÇARPAN 1.0 DEĞİL, aşağıdaki sabit varsayılan tablo kullanılır (muhafazakâr yön).
"""
from __future__ import annotations

import functools
import json
import logging
from decimal import Decimal
from pathlib import Path

import pandas as pd

from motor.canli.paper_takvim import seans_dilimi, tur

log = logging.getLogger(__name__)
YOL = Path(__file__).resolve().parents[2] / "stratejiler" / "seans_maliyet.json"
VARSAYILAN = {"hisse": {"normal": 1.0, "genisletilmis": 2.0, "kapali": 3.0}, "emtia": {"normal": 1.0, "kapali": 2.0}}
_onbellek: dict = {}


def tablo() -> dict:
    if "t" not in _onbellek:
        try:
            d = json.loads(YOL.read_text(encoding="utf-8"))
            t = {k: {a: float(b) for a, b in d[k].items()} for k in ("hisse", "emtia")}
            if any(v < 1.0 for k in t.values() for v in k.values()):
                raise ValueError("çarpan < 1")
        except Exception:  # noqa: BLE001
            log.exception("seans_maliyet.json okunamadı; varsayılan tablo")
            t = VARSAYILAN
        _onbellek["t"] = t
    return _onbellek["t"]


@functools.lru_cache(maxsize=8192)
def _dilim(sembol: str, zaman) -> str:
    return seans_dilimi(sembol, zaman)


def dilim_ve_carpan(sembol: str, zaman) -> tuple:
    """-> (seans_dilimi, kayma_carpani Decimal). Kripto: ('normal', 1). Dilim hesabı önbelleklidir (motor satır başına çok kez sorar)."""
    tr = tur(sembol)
    if tr == "kripto" or zaman is None:
        return "normal", Decimal(1)
    d = _dilim(sembol, pd.Timestamp(zaman))
    return d, Decimal(str(tablo()[tr].get(d, 1.0)))
