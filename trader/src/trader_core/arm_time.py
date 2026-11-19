"""Kurulum (arm) zaman dilimi ve seans/kimlik yardimcilari; yalniz stdlib.

Tek kaynak: `trader_engine.bars` (ARM_TFS, ARM_TF_SECONDS, arm_tf_delta) ve `trader_engine.arm_guard`
(CLASS_*, session_tag, arm_id_of) bu modulu yeniden kullanir; `trader_core.counterfactual` da buradan alir
(trader_core -> trader_engine bagimliligi yasak, tests/engine/test_engine_dependency_direction.py).
Davranis degismez: degerler ve formuller onceki arm_guard/bars tanimlarinin aynisidir.
"""
from __future__ import annotations

from datetime import datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo

_NY = ZoneInfo("America/New_York")
CLASS_CRYPTO, CLASS_EQUITY, CLASS_COMMODITY = "kripto", "hisse", "emtia"

ARM_TFS = ("15m", "1h", "4h", "1d")                       # kucukten buyuge; oncelik buyuk zaman dilimindedir
ARM_TF_SECONDS = {"15m": 900, "1h": 3600, "4h": 14400, "1d": 86400}


def arm_tf_delta(tf: str) -> timedelta:
    try:
        return timedelta(seconds=ARM_TF_SECONDS[tf])
    except (KeyError, TypeError):
        raise ValueError(f"bilinmeyen kurulum zaman dilimi: {tf!r}") from None


def arm_id_of(setup: str | None, tf: str | None) -> str:
    """`<kurulum>@<zaman dilimi>`; kurulum/tf yoksa `?` (tavan sayiminda eslesmez)."""
    return f"{setup or '?'}@{tf or '?'}"


def session_tag(cls: str, ts: datetime) -> str:
    """open | closed | weekend (spec §4.2). `ts` tz-bilincli. Hisse: New York 09:30-16:00 Pzt-Cum open (DST'e gore),
    hafta ici dis closed, Cts-Paz weekend. Emtia: Paz 23:00 -> Cum 21:00 UTC open, Cum 21:00 -> Paz 23:00 weekend. Kripto: open."""
    if ts.tzinfo is None:
        raise ValueError("ts tz-bilincli olmali")
    if cls == CLASS_CRYPTO:
        return "open"
    if cls == CLASS_EQUITY:
        t = ts.astimezone(_NY)
        if t.weekday() >= 5:
            return "weekend"
        return "open" if time(9, 30) <= t.time() < time(16, 0) else "closed"
    if cls == CLASS_COMMODITY:
        u = ts.astimezone(timezone.utc)
        wd, hm = u.weekday(), u.time()
        if wd == 5 or (wd == 4 and hm >= time(21, 0)) or (wd == 6 and hm < time(23, 0)):
            return "weekend"
        return "open"
    raise ValueError(f"bilinmeyen varlik sinifi: {cls!r}")
