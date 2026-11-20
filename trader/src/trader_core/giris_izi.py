"""Ayar surumu izi (6c; 1L3A motor/canli/giris_izi.py'dan uyarlandi).

`ayar_surumu`: etkin yapilandirmanin (dataclass/Mapping) kanonik JSON'unun sha256'si. Risk/kol/evren/maliyet degisince hash degisir;
ayni yapilandirma her calismada ayni hash'i verir. Durumda tam hash, karar `features`'inda ilk 12 hane yazilir. YALNIZ KAYIT:
karar/boyut/risk yoluna girmez; metin oldugundan ML ozelligi olmaz. Defter semasi degismez (features sozlugu)."""
from __future__ import annotations

import dataclasses
import hashlib
import json
import math
from typing import Any, Mapping

ANAHTAR_SURUM = "ayar_surumu"
KISA = 12


def _jsonable(o: Any) -> Any:
    if dataclasses.is_dataclass(o) and not isinstance(o, type):
        return {f.name: _jsonable(getattr(o, f.name)) for f in dataclasses.fields(o)}
    if isinstance(o, Mapping):
        return {str(k): _jsonable(v) for k, v in sorted(o.items(), key=lambda kv: str(kv[0]))}
    if isinstance(o, (list, tuple)):
        return [_jsonable(v) for v in o]
    if isinstance(o, (set, frozenset)):
        return sorted(_jsonable(v) for v in o)
    if isinstance(o, float) and not math.isfinite(o):
        return repr(o)
    if o is None or isinstance(o, (str, int, float, bool)):
        return o
    return str(o)


def ayar_sha256(cfg: Any) -> str:
    """Etkin yapilandirmanin tam sha256 hex'i (anahtar sirasindan bagimsiz, kanonik JSON)."""
    ham = json.dumps(_jsonable(cfg), sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(ham.encode("utf-8")).hexdigest()


def ayar_kisa(cfg: Any) -> str:
    return ayar_sha256(cfg)[:KISA]
