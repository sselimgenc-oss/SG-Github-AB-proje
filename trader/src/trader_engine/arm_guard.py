"""DD-12 WP-04 (spec §4.1/§4.2): saf yardimcilar - kume uyeligi, tavan sayimi, `session_tag`, tatil/duz bar.
Girdi/cikti yalniz deger; G/C, saat, durum yok. Seans yuzunden giris ENGELLENMEZ: etiket yalniz kayittir;
`session_closed` ancak dersin kapattigi seans icindir (gates.py)."""
from __future__ import annotations

import math
from collections.abc import Collection, Mapping, Sequence
from datetime import datetime, time, timezone
from zoneinfo import ZoneInfo

from .config import ClusterSpec

_NY = ZoneInfo("America/New_York")
EQUITY_CLUSTER = "hisse"
COMMODITY_CLUSTERS = ("metal", "enerji_sanayi")
CLASS_CRYPTO, CLASS_EQUITY, CLASS_COMMODITY = "kripto", "hisse", "emtia"


def clusters_of(pair: str, clusters: Mapping[str, ClusterSpec]) -> list[str]:
    """Cift hangi kumelerin uyesi (yapilandirma sirasiyla; birden cok olabilir)."""
    return [name for name, spec in clusters.items() if pair in spec.pairs]


def count_in_cluster(held_pairs: Collection[str] | Sequence[str], spec: ClusterSpec) -> int:
    return sum(1 for p in held_pairs if p in spec.pairs)


def full_cluster(pair: str, held_pairs: Sequence[str], clusters: Mapping[str, ClusterSpec]) -> str | None:
    """Giris icin yeri olmayan ilk kume adi (acik + acilmakta pozisyonlar `held_pairs`); hepsinde yer varsa None."""
    for name in clusters_of(pair, clusters):
        if count_in_cluster(held_pairs, clusters[name]) >= clusters[name].max_positions:
            return name
    return None


def account_full(n_open: int, max_positions: int | None) -> bool:
    return max_positions is not None and n_open >= max_positions


def asset_class(pair: str, clusters: Mapping[str, ClusterSpec]) -> str:
    """kripto | hisse | emtia; kume adlarindan (`hisse`, `metal`, `enerji_sanayi`) cikarilir, aksi kripto."""
    for name in clusters_of(pair, clusters):
        if name == EQUITY_CLUSTER:
            return CLASS_EQUITY
        if name in COMMODITY_CLUSTERS:
            return CLASS_COMMODITY
    return CLASS_CRYPTO


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


def is_flat_bar(high: float | None, low: float | None, volume: float | None) -> bool:
    """Tatil/olu mum: volume == 0 ya da high == low. Veri yoksa (None/NaN) False (karar verilemez)."""
    def ok(x) -> bool:
        return isinstance(x, (int, float)) and not isinstance(x, bool) and math.isfinite(float(x))
    if ok(volume) and float(volume) == 0.0:
        return True
    return ok(high) and ok(low) and float(high) == float(low)


def session_closed_by_lesson(session_off: Mapping[str, Collection[str]] | None, cls: str, pair: str, tag: str) -> bool:
    """Ders `session_off`: anahtar varlik sinifi ya da cift adi, deger kapatilan etiketler. Varsayilan: hepsi acik."""
    if not session_off:
        return False
    return tag in (session_off.get(cls) or ()) or tag in (session_off.get(pair) or ())


# ---------------------------------------------------------------------------------------------------------------------
# DD-12 WP-11 (D-T16): kurulum (arm) basina acik pozisyon tavani. Saf yardimcilar (durum/saat yok).
# ---------------------------------------------------------------------------------------------------------------------
def arm_id_of(setup: str | None, tf: str | None) -> str:
    """`<kurulum>@<zaman dilimi>`; kurulum/tf yoksa `?` (tavan sayiminda eslesmez)."""
    return f"{setup or '?'}@{tf or '?'}"


def arm_cap(caps: Mapping[str, int] | None, arm_id: str, setup: str | None) -> int | None:
    """Tavan arama sirasi: tam arm_id, kurulum kodu, `default`; hicbiri yoksa None (tavan yok)."""
    if not caps:
        return None
    for key in (arm_id, setup, "default"):
        if key is not None and key in caps:
            return int(caps[key])
    return None


def arm_full(held_arm_ids: Sequence[str], arm_id: str, cap: int | None) -> bool:
    """`held_arm_ids`: acik + acilmakta pozisyonlarin arm_id'leri. cap None => dolu degil."""
    return cap is not None and sum(1 for a in held_arm_ids if a == arm_id) >= cap
