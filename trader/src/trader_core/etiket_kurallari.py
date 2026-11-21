"""Etiket kurallari (kagit): rejim etiketi bir girisi YALNIZ atlatabilir. Sabit kural (otomatik acma/kapama YOK).

Saf mantik (ag/dosya yok, motor bagimliligi yok). Belirtim: docs/etiket-kurallari-spec.md.
- Kural yalnizca "hayir" diyebilir: boyut/kaldirac/limit/stop degismez; yeni giris acilmaz.
- Rejim bilinmiyorsa kural engellemez (fail-open) ve bunu sayar.
- Duygu (Fear & Greed) / haber tonu hicbir karar girdisi degildir (kural, kapi, ML ozelligi): 21 Kasim 2026 kullanici karariyla SILINDI.
  Eski defter satirlarinda `skip_reason = etiket_duygu` kalabilir (sema degismez; yalniz okunur).
"""
from __future__ import annotations

from collections.abc import Mapping
from typing import Any

REJIM = "etiket_rejim"
KURALLAR = (REJIM,)
CFG_ANAHTAR = {"rejim": REJIM}
SADE_AD = {REJIM: "rejim karşıtı"}

VARSAYILAN = {
    "rejim": {"acik": True},
}


class EtiketConfigHatasi(ValueError):
    pass


def build_config(raw: Any) -> dict:
    """Ham `etiket_kurallari` -> dogrulanmis sozluk. Bos/None -> {} (kapali). Bilinmeyen anahtar reddedilir."""
    if raw in (None, {}):
        return {}
    if not isinstance(raw, Mapping):
        raise EtiketConfigHatasi(f"etiket_kurallari nesne olmali: {raw!r}")
    for k in raw:
        if k not in VARSAYILAN:
            raise EtiketConfigHatasi(f"etiket_kurallari bilinmeyen anahtar: {k!r}")
    sec = raw.get("rejim", {})
    if not isinstance(sec, Mapping):
        raise EtiketConfigHatasi("etiket_kurallari.rejim nesne olmali")
    for k in sec:
        if k not in VARSAYILAN["rejim"]:
            raise EtiketConfigHatasi(f"etiket_kurallari.rejim bilinmeyen anahtar: {k!r}")
    d = {**VARSAYILAN["rejim"], **sec}
    if not isinstance(d["acik"], bool):
        raise EtiketConfigHatasi("etiket_kurallari.rejim.acik bool olmali")
    return {"rejim": d}


def kural_acik_config(cfg: Mapping | None, kod: str) -> bool:
    if not cfg:
        return False
    sec = {v: k for k, v in CFG_ANAHTAR.items()}[kod]
    return bool(cfg.get(sec, {}).get("acik"))


def degerlendir(side: str, regime: str | None, cfg: Mapping | None) -> tuple[list[tuple[str, str]], list[str]]:
    """Doner: (tetiklenenler [(kural, ayrinti)], veri_yok [kural]). Yalniz config'te acik kural degerlendirilir.
    Rejim yoksa kural tetiklenmez (fail-open) ve `veri_yok`ta listelenir."""
    if not cfg or side not in ("long", "short"):
        return [], []
    tet: list[tuple[str, str]] = []
    yok: list[str] = []
    if kural_acik_config(cfg, REJIM):
        if regime in ("trend_up", "trend_down"):
            if (side == "long" and regime == "trend_down") or (side == "short" and regime == "trend_up"):
                tet.append((REJIM, f"{side}/{regime}"))
        elif regime is None:
            yok.append(REJIM)
    return tet, yok
