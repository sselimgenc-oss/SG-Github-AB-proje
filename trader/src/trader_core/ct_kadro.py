"""C1: CT kadro uzlasisi (`ct.kadro_yon.v1`) dogrulama, eslestirme ve okuma. Saf: ag yok, yan etki yok.

Yayin: `scripts/ct_kadro_cek.py` (5 dk'da bir) `var/ct/kadro_yon.json` dosyasini yazar; bu modul o dosyayi okur.
Belirtim: docs/motor/c1-ct-kadro-spec.md (bolum 1-2).
"""
from __future__ import annotations

import json
import math
import re
from datetime import datetime, timedelta, timezone
from pathlib import Path

SEMA = "ct.kadro_yon.v1"
NET_YONLER = ("long", "short", "notr")
AZAMI_YAS_DK = 45
GELECEK_TOLERANS_DK = 5
_ZAMAN_RE = re.compile(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(\.\d{1,6})?Z")
_TABAN_RE = re.compile(r"[A-Z][A-Z0-9]*")
_KPREFIX_RE = re.compile(r"k([A-Z][A-Z0-9]*)")
_DEX_RE = re.compile(r"[a-z][a-z0-9]*")


class KadroHatasi(ValueError):
    """Dosya ust duzeyi gecersiz (sema, zaman, coinler): tum dosya reddedilir."""


def zaman_ayristir(s) -> datetime:
    """ISO-8601 `...Z` (UTC) zamanini tz-farkindalikli datetime yapar; bicim tutmazsa KadroHatasi."""
    if not isinstance(s, str) or not _ZAMAN_RE.fullmatch(s):
        raise KadroHatasi(f"uretildi_utc bicimi gecersiz: {s!r}")
    try:
        return datetime.fromisoformat(s[:-1] + "+00:00").astimezone(timezone.utc)
    except ValueError as e:
        raise KadroHatasi(f"uretildi_utc ayristirilamadi: {s!r}") from e


def zaman_yaz(dt: datetime) -> str:
    """UTC datetime -> `YYYY-MM-DDTHH:MM:SSZ`."""
    return dt.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _tam_sayi(v) -> bool:
    return isinstance(v, int) and not isinstance(v, bool) and v >= 0


def _kayit_gecerli(oge) -> bool:
    """Tek coin ogesinin sema denetimi (belirtim bolum 1)."""
    if not isinstance(oge, dict):
        return False
    coin = oge.get("coin")
    if not isinstance(coin, str) or not coin.strip():
        return False
    if not (_tam_sayi(oge.get("long_trader")) and _tam_sayi(oge.get("short_trader"))):
        return False
    if oge.get("net_yon") not in NET_YONLER:
        return False
    nom = oge.get("net_nominal_usd")
    if nom is None:
        return True
    return isinstance(nom, (int, float)) and not isinstance(nom, bool) and math.isfinite(float(nom))


def dogrula_belge(doc) -> tuple[datetime, list[dict], int]:
    """Ham belgeyi dogrular: (uretildi_utc, gecerli ogeler, gecersiz oge sayisi). Ust duzey hata -> KadroHatasi."""
    if not isinstance(doc, dict):
        raise KadroHatasi("belge bir nesne degil")
    if doc.get("sema") != SEMA:
        raise KadroHatasi(f"sema farkli: {doc.get('sema')!r}")
    uretildi = zaman_ayristir(doc.get("uretildi_utc"))
    coinler = doc.get("coinler")
    if not isinstance(coinler, list):
        raise KadroHatasi("coinler liste degil")
    gecerli = [o for o in coinler if _kayit_gecerli(o)]
    return uretildi, gecerli, len(coinler) - len(gecerli)


def hl_to_binance(coin, evren=None) -> str | None:
    """Hyperliquid coin adini Binance USDT paritesine cevirir; bilinmeyen/evren disi -> None.

    `dex:NVDA` / `xyz:NVDA` -> NVDA/USDT (HIP-3 dex adi: kucuk harfli on ek bir kez atilir); `kPEPE` -> 1000PEPE/USDT
    (kucuk k + buyuk harf); `BTC` -> BTC/USDT. `evren` verilirse (parite kumesi) sonuc yalniz o kumede ise doner; None ise
    uyelik denetlenmez.
    """
    if not isinstance(coin, str):
        return None
    s = coin.strip()
    if ":" in s:
        prefix, _, s = s.partition(":")
        if not _DEX_RE.fullmatch(prefix) or not s:
            return None
    m = _KPREFIX_RE.fullmatch(s)
    if m is not None:
        taban = "1000" + m.group(1)
    elif _TABAN_RE.fullmatch(s):
        taban = s
    else:
        return None
    cift = f"{taban}/USDT"
    if evren is not None and cift not in evren:
        return None
    return cift


def kadro_belgeden(doc, simdi: datetime, *, azami_yas_dk: float = AZAMI_YAS_DK, evren=None) -> dict | None:
    """Dogrulanmis ham belgeden {cift: kayit} (+ "_uretildi": datetime). Bayat/gelecek/ust duzey hata -> None.

    Ayni parite birden cok coin'den eslesirse ilk gelen kazanir. `simdi` UTC'ye cevrilir (tz'siz -> UTC).
    """
    try:
        uretildi, ogeler, _ = dogrula_belge(doc)
    except KadroHatasi:
        return None
    simdi = simdi.replace(tzinfo=timezone.utc) if simdi.tzinfo is None else simdi.astimezone(timezone.utc)
    yas = simdi - uretildi
    if yas > timedelta(minutes=azami_yas_dk) or yas < -timedelta(minutes=GELECEK_TOLERANS_DK):
        return None
    out: dict = {"_uretildi": uretildi}
    for oge in ogeler:
        cift = hl_to_binance(oge["coin"], evren)
        if cift is None or cift in out:
            continue
        nom = oge.get("net_nominal_usd")
        out[cift] = {"long": oge["long_trader"], "short": oge["short_trader"], "net_yon": oge["net_yon"],
                     "net_nominal_usd": None if nom is None else float(nom),
                     "veri_yasi_sn": yas.total_seconds()}
    return out


def yukle(yol) -> dict | None:
    """Dosyayi okur ve sema denetimli ham belgeyi dondurur; yok/bozuk/sema farkli -> None (sessiz)."""
    try:
        doc = json.loads(Path(yol).read_text(encoding="utf-8"))
        dogrula_belge(doc)
    except (OSError, ValueError, KadroHatasi):
        return None
    return doc


def oku(yol, simdi: datetime, *, azami_yas_dk: float = AZAMI_YAS_DK, evren=None) -> dict | None:
    """Dosyayi okuyup {cift: kayit} dondurur (bkz. `kadro_belgeden`). Dosya yok/bozuk/bayat -> None."""
    doc = yukle(yol)
    return None if doc is None else kadro_belgeden(doc, simdi, azami_yas_dk=azami_yas_dk, evren=evren)
