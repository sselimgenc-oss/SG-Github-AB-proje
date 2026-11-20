"""ETİKET × SONUÇ KARTI (2026-11-19): kapanan paper işlemlerini kayıt etiketlerine göre kırar. YALNIZ OKUR.

Hiçbir kural, strateji, limit ya da karar bu modülden etkilenmez; çıktı yalnız `etiket_sonuc_v1.json` (şema `etiket_sonuc.v1`)
ve haftalık Telegram özetinin tek satırıdır. Etiketi olmayan işlem "bilinmiyor" grubuna girer.

Etiketler: rejim_ml_4h, rejim_ml_1d, takvim_bayragi, kalabalik (etiket_kurallari eşikleriyle), korku_acgozluluk (dilim),
seans_dilimi (yalnız hisse/emtia; kripto işlemlerinde alan yoksa "bilinmiyor").

Birim: tüm işlemlerde R (`r`) varsa R, aksi halde net USD (`net_pnl_yerel`). Ölçülemeyen (birimi olmayan) işlem tabloya girmez,
`olculemeyen` sayısında yazılır. Gizli hesapların adı hiçbir çıktıda yazılmaz; işlemleri toplamlara girer.
"""
from __future__ import annotations

import json
import logging
import math
from pathlib import Path
from typing import Optional

from motor.canli import etiket_kurallari as ek

log = logging.getLogger("etiket_sonuc")
SEMA = "etiket_sonuc.v1"
DOSYA = "etiket_sonuc_v1.json"
BILINMIYOR = "bilinmiyor"
ETIKET_ADLARI = ("rejim_ml_4h", "rejim_ml_1d", "takvim_bayragi", "kalabalik", "korku_acgozluluk", "seans_dilimi")


# ----------------------------------------------------------------------------------------------- etiket değerleri
def _sayi(x) -> Optional[float]:
    try:
        v = float(x)
    except (TypeError, ValueError):
        return None
    return v if math.isfinite(v) else None


def _etiketler(t: dict) -> dict:
    e = t.get("etiketler")
    return e if isinstance(e, dict) else {}


def _korku_dilimi(x) -> str:
    v = _sayi(x)
    if v is None or not 0 <= v <= 100:
        return BILINMIYOR
    if v >= 75:
        return "75-100"
    if v >= 50:
        return "50-75"
    if v >= 25:
        return "25-50"
    return "0-25"


def _kalabalik(t: dict) -> str:
    """etiket_kurallari ile aynı eşikler: long fonlama >= +eşik, short fonlama <= -eşik, VE oi_degisim_24s >= eşik."""
    e = _etiketler(t)
    f, oi = _sayi(e.get("fonlama_orani")), _sayi(e.get("oi_degisim_24s"))
    if f is None or oi is None:
        return BILINMIYOR
    yon = t.get("yon")
    kalabalik = oi >= ek.KALABALIK_OI_DEGISIM_24S and (
        (yon == "long" and f >= ek.KALABALIK_FONLAMA) or (yon == "short" and f <= -ek.KALABALIK_FONLAMA))
    return "kalabalik" if kalabalik else "degil"


def _etiket_degeri(t: dict, ad: str) -> str:
    e = _etiketler(t)
    if ad == "seans_dilimi":
        v = t.get("seans_dilimi")
        return str(v) if v else BILINMIYOR
    if ad == "kalabalik":
        return _kalabalik(t)
    if ad == "korku_acgozluluk":
        return _korku_dilimi(e.get("korku_acgozluluk"))
    if ad == "takvim_bayragi":                 # anahtar var ama null = takvim olayı yok (geçerli bir değer)
        if "takvim_bayragi" not in e:
            return BILINMIYOR
        v = e["takvim_bayragi"]
        return "yok" if v is None else str(v)
    v = e.get(ad)
    return str(v) if v else BILINMIYOR


# ----------------------------------------------------------------------------------------------- tablo
def birim_sec(islemler: list) -> str:
    """Tüm işlemlerde R varsa "R", aksi halde "USD" (net_pnl_yerel)."""
    return "R" if all(_sayi(t.get("r")) is not None for t in islemler) else "USD"


def _deger(t: dict, birim: str) -> Optional[float]:
    return _sayi(t.get("r")) if birim == "R" else _sayi(t.get("net_pnl_yerel"))


def _satir(deger: str, vs: list) -> dict:
    n = len(vs)
    toplam = sum(vs)
    return {"deger": deger, "islem": n, "kazanan": sum(1 for v in vs if v > 0), "isabet_yuzde": round(100 * sum(1 for v in vs if v > 0) / n, 1),
            "toplam": round(toplam, 2), "ort": round(toplam / n, 2)}


def _kripto(t: dict) -> bool:
    """Sembol var ve hisse/emtia listesinde yok -> kripto (paper_takvim.tur ile aynı ayrım)."""
    from motor.canli.paper_takvim import tur
    s = t.get("sembol")
    return bool(s) and tur(s) == "kripto"


def etiket_tablosu(islemler: list) -> dict:
    """SAF: kapanan işlem listesi -> {etiket_adı: [satır, ...]}. Satır: deger, islem, kazanan, isabet_yuzde, toplam, ort (birim: birim_sec).
    seans_dilimi tablosunda kripto işlemleri yer almaz; "bilinmiyor" yalnız hisse/emtia işlemlerinde alan eksikse çıkar."""
    birim = birim_sec(islemler)
    olculen = [(t, v) for t, v in ((t, _deger(t, birim)) for t in islemler) if v is not None]
    out: dict = {}
    for ad in ETIKET_ADLARI:
        gruplar: dict = {}
        for t, v in olculen:
            if ad == "seans_dilimi" and _kripto(t):
                continue
            gruplar.setdefault(_etiket_degeri(t, ad), []).append(v)
        satirlar = [_satir(d, vs) for d, vs in gruplar.items()]
        out[ad] = sorted(satirlar, key=lambda s: (s["deger"] == BILINMIYOR, s["deger"]))
    return out


def rejim_karsit_sayisi(islemler: list) -> int:
    """Giriş yönü ML rejimin karşısında olan işlem sayısı (etiket_kurallari.REJIM_KARSITI; rejim_ml_1d yoksa 4h)."""
    n = 0
    for t in islemler:
        e = _etiketler(t)
        r = e.get("rejim_ml_1d") or e.get("rejim_ml_4h")
        if r is not None and r == ek.REJIM_KARSITI.get(t.get("yon")):
            n += 1
    return n


# ----------------------------------------------------------------------------------------------- okuma ve yazma
def islemleri_topla(durum_dizini, set_yolu=None) -> list:
    """Paper hesaplarının kapanan işlemleri (islemler.jsonl). Hesap adı döndürülmez. Hesap klasörü yoksa üst düzey dosya."""
    from motor.canli import gunluk_ozet as go
    dizin = Path(durum_dizini)
    kayitlar = go._set_kayitlari(set_yolu)
    if kayitlar is None:
        return go._jsonl(dizin / "islemler.jsonl")
    out: list = []
    for _kimlik, klasor, _gorunur in kayitlar:
        out.extend(go._jsonl(dizin / "hesaplar" / klasor / "islemler.jsonl"))
    return out


def son_7_gun_islemleri(islemler: list, gun: str) -> list:
    """Kapanış zamanı (TSİ günü) `gun` dahil son 7 gün içinde kapanan işlemler."""
    import pandas as pd
    from motor.canli import gunluk_ozet as go
    bas = str((pd.Timestamp(gun) - pd.Timedelta(days=6)).date())
    out = []
    for t in islemler:
        g = go._tsi_gun(t.get("zaman") or t.get("cikis_zamani"))
        if g and bas <= g <= gun:
            out.append(t)
    return out


def _bolum(islemler: list, kapsam: str) -> dict:
    birim = birim_sec(islemler)
    return {"kapsam": kapsam, "birim": birim, "islem_sayisi": len(islemler), "olculemeyen": sum(1 for t in islemler if _deger(t, birim) is None),
            "rejim_karsit": rejim_karsit_sayisi(islemler), "etiketler": etiket_tablosu(islemler)}


def kart(islemler: list, simdi_iso: str, gun: str) -> dict:
    """SAF: işlem listesi -> `etiket_sonuc.v1` sözlüğü. Üst düzey: tüm dönem; `son_7_gun`: kapanış TSİ günü `gun` dahil 7 gün."""
    return {"sema": SEMA, "proje": "1L3A", "uretim": simdi_iso, "gun": gun, **_bolum(islemler, "tum_kapanan_paper_islemleri"),
            "son_7_gun": _bolum(son_7_gun_islemleri(islemler, gun), "son_7_gun_kapanis")}


def yaz(durum_dizini, simdi, set_yolu=None) -> Optional[dict]:
    """Durum dizinine `etiket_sonuc_v1.json` (atomik). Hata paper'ı durdurmaz: yutulur, loglanır, None döner."""
    try:
        from motor.canli import gunluk_ozet as go
        from motor.canli.durum import atomik_yaz_metin
        o = kart(islemleri_topla(durum_dizini, set_yolu), go._iso(simdi), go._tsi_gun(simdi))
        atomik_yaz_metin(Path(durum_dizini) / DOSYA, json.dumps(o, ensure_ascii=False, indent=1, allow_nan=False) + "\n")
        return o
    except Exception:  # noqa: BLE001
        log.exception("etiket × sonuç kartı yazılamadı (paper sürer)")
        return None


# ----------------------------------------------------------------------------------------------- haftalık tek satır
def _isaretli(v: float, birim: str) -> str:
    if birim == "R":
        return f"{v:+.1f}R".replace(".", ",")
    return f"{v:+.2f} USD".replace(".", ",")


def haftalik_satir(e: Optional[dict]) -> Optional[str]:
    """Haftalık Telegram özetine tek satır (son 7 gün kapanışları), ör. "Etiket: rejim karşıtı yok; en iyi rejim trend_up +4,2R (12 işlem)"."""
    if not e:
        return None
    s7 = e.get("son_7_gun") or {}
    if not s7.get("islem_sayisi"):
        return "Etiket: son 7 günde kapanan işlem yok"
    s = "rejim karşıtı yok" if not s7.get("rejim_karsit") else f"rejim karşıtı {s7['rejim_karsit']} işlem"
    adaylar = [r for r in (s7.get("etiketler") or {}).get("rejim_ml_1d") or [] if r["deger"] != BILINMIYOR]
    if not adaylar:
        s += "; en iyi rejim verisi yok"
    else:
        en = max(adaylar, key=lambda r: r["toplam"])
        s += f"; en iyi rejim {en['deger']} {_isaretli(en['toplam'], s7['birim'])} ({en['islem']} işlem)"
    return "Etiket: " + s
