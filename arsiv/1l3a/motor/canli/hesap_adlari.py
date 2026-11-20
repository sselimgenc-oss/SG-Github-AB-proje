"""Kullanıcıya görünen hesap adı ve coin yazımı: TEK kaynak (Telegram mesajları ve günlük özet/pano aynı fonksiyonu kullanır).

Kural (kullanıcı kararı, 2026-11-19): işlem mesajlarında hesap adı panodakiyle harfi harfine aynıdır. Gizli kâğıt hesabın adı ASLA yazılmaz:
"Diğer hesap" (çoğul toplam satırı: "Diğer hesaplar (N)"). Coin tek tip: "SOL", "BTC" (USDT eki yok).
"""
from __future__ import annotations

import csv
import functools
import re
from pathlib import Path

DIGER_HESAP = "Diğer hesap"
DIGER_HESAPLAR = "Diğer hesaplar"
CT_HESABI = "CT konsensüs hesabı"
BILINMEYEN_HESAP = "Hesap bilinmiyor"


def kisa_ad(kimlik: str) -> str:
    """Görünür hesabın kısa adı (panodaki hesap tablosu): dis__gauss-stoch-eth -> gauss; HAM:X005:664#v1 -> 664; dis__e0v1en -> e0v1en."""
    kimlik = str(kimlik)
    if kimlik.startswith("HAM:"):
        parca = kimlik.split(":")
        return parca[-1].split("#")[0] if len(parca) >= 3 else kimlik
    govde = kimlik.split("__", 1)[-1]
    return govde.split("|")[0].split("-")[0]


# kimlik -> okunur ad (kullanıcı dostu; kod adı yok)
AD = {"dis__dual-thrust|ETHUSDT|30m": "Dual Thrust · ETH 30 dk",
      "pf__kanarya|hisse_emtia|1d": "Kanarya · Hisse+Emtia",
      "pf__rotasyon|hepsi|1d": "Rotasyon · Tümü",
      "pf__kesit_ls|kripto|1d": "Kesit L/S · Kripto",
      "swing__cci-esik|SOLUSDT|1d": "CCI Eşik · SOL 1G",
      "swing__konsolidasyon-kirilim|SOLUSDT|4h": "Konsolidasyon Kırılımı · SOL 4S",
      "dis__fraktal-alligator-sky|DK_NVDA|4h": "Fraktal Alligator · NVDA 4S"}

_ZAMAN = {"d": "G", "h": "S", "w": "H"}


def _aralik(tf: str) -> str:
    """1d -> 1G, 4h -> 4S, 1h -> 1S, 15m -> 15 dk."""
    m = re.fullmatch(r"(\d+)([mhdw])", str(tf))
    if not m:
        return str(tf).replace("_", " ")
    return f"{m.group(1)} dk" if m.group(2) == "m" else f"{m.group(1)}{_ZAMAN[m.group(2)]}"


@functools.lru_cache(maxsize=1)
def _aciklamalar() -> dict:
    """stratejiler/havuz_v2_etiketler.csv: strateji kimliği -> Türkçe kısa açıklama (ilk bölüm). Dosya yoksa/bozuksa boş (ad kimlikten türetilir)."""
    out = {}
    try:
        with open(Path(__file__).resolve().parents[2] / "stratejiler" / "havuz_v2_etiketler.csv", encoding="utf-8", newline="") as f:
            for r in csv.DictReader(f):
                a = re.split(r"\s*(?:\+|,|;| ile )\s*", (r.get("gerekce") or "").strip(), maxsplit=1)[0].strip()
                if r.get("strateji") and len(a.split()) >= 2 and not re.search(r"[0-9<>/]", a):      # yalnız okunur açıklama (gösterge kodu değil)
                    out[r["strateji"]] = a[:34].rstrip(" -(/")
    except (OSError, csv.Error, UnicodeDecodeError):
        return {}
    return out


def okunur_ad(kimlik: str) -> str:
    """AD haritasında varsa o; yoksa kimliğin gövdesinden: "_" ve "-" boşluk, ilk harf büyük, "|SEMBOL|aralık" varsa " · SOL 4S". "_" içermez."""
    kimlik = str(kimlik)
    if kimlik in AD:
        return AD[kimlik]
    if kimlik.startswith("HAM:"):                       # HAM:X005:664#v1 -> "Ham 664 v1"
        govde = " ".join(["ham"] + kimlik.split(":")[2:]).replace("#", " ")
        ek = ""
    else:
        parca = kimlik.split("|")
        govde = "CT konsensüs" if kimlik.startswith("ct_konsensus") else parca[0].split("__", 1)[-1]
        ek = ""
        if len(parca) >= 3:
            ek = f" · {coin_adi(parca[-2])} {_aralik(parca[-1])}"
        elif len(parca) == 2:
            ek = f" · {coin_adi(parca[-1])}"
    acik = "" if kimlik.startswith(("HAM:", "ct_konsensus")) else _aciklamalar().get(kimlik.split("|")[0], "")      # kod adı yetmez: kısa Türkçe açıklama eklenir
    govde = " ".join(govde.replace("_", " ").replace("-", " ").split())
    govde = govde[:1].upper() + govde[1:]
    return (govde + (f" · {acik}" if acik else "") + ek).replace("_", " ")


def hesap_adi(kimlik: str, gorunur: bool = True) -> str:
    """Telegram/pano hesap adı. gorunur=False (gizli hesap): "Diğer hesap" (gerçek ad hiçbir yerde yazılmaz); CT: "CT konsensüs hesabı";
    diğerleri: AD haritası, yoksa gövdeden okunur ad (hiçbir zaman "_" içermez)."""
    if not gorunur:
        return DIGER_HESAP
    if kimlik is None or not str(kimlik).strip():
        return BILINMEYEN_HESAP                                  # boş kimlik: mesaj/pano "· " ile bitmez
    if str(kimlik).startswith("ct_konsensus"):
        return CT_HESABI
    return okunur_ad(kimlik) or BILINMEYEN_HESAP


def coin_adi(sembol: str) -> str:
    """BTCUSDT -> BTC; DK_NVDA -> NVDA; SOL -> SOL."""
    s = re.sub(r"^DK_", "", str(sembol))
    return re.sub(r"(USDT|USDC|BUSD|USD)$", "", s) or s
