"""Telegram (/kurulumlar, /ders) ve pano kartlarının ORTAK okuyucusu: yalnız durum dosyalarını OKUR (hesap yapmaz, uydurmaz, hiçbir şey yazmaz).

Hesap grupları: 6 görünür hesap (kısa adla), gizli hesaplar TEK satır ("gizli_hesaplar (N)"; adları hiçbir çıktıda yok, kurulum adları ve
ders kimlikleri de süzülür), ct_konsensus, aday hesapları (aday_paper). Öğrenme verisi (ogrenme_adaptor.py durum dosyaları): ogrenme_ders.json,
ogrenme_durum.json (drift, eğitim), ogrenme_modeller/ (filtre), ogrenme_karne.json, alinmayan_sinyaller.jsonl. Her okuma hata verirse None/boş döner.
"""
from __future__ import annotations

import os
from datetime import datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Optional

from motor.canli import gunluk_ozet as go

UTC = timezone.utc
VARSAYILAN_ADAY = "/var/lib/1l3a-paper/durum/adaylar"
EMEKLI_GUN = 7


def ct_dizini(env=None) -> Path:
    env = os.environ if env is None else env
    return Path(env.get("L3A_CT_DURUM") or env.get("L3A_CT_DURUM_DIZIN") or go.CT_VARSAYILAN)


def aday_dizini(env=None) -> Path:
    env = os.environ if env is None else env
    return Path(env.get("L3A_ADAY_DURUM") or VARSAYILAN_ADAY)


def _dec(x) -> Optional[Decimal]:
    try:
        return None if x is None else Decimal(str(x))
    except (InvalidOperation, ValueError):
        return None


def _zaman(s) -> Optional[datetime]:
    try:
        z = datetime.fromisoformat(str(s).replace("Z", "+00:00"))
        return z if z.tzinfo else z.replace(tzinfo=UTC)
    except (TypeError, ValueError):
        return None


def yas_sn(s, simdi: datetime) -> Optional[float]:
    z = _zaman(s)
    return None if z is None else max(0.0, (simdi - z).total_seconds())


# ----------------------------------------------------------------------------------------------- öğrenme (tek durum dizini)
def ogrenme_oku(dizin, simdi: Optional[datetime] = None) -> dict:
    """Bir durum dizinindeki adaptör dosyaları -> {ders, drift, filtre, karne, esleme, alinmayan, veri_var}. Dosya yoksa ilgili alan boş/None."""
    from motor.canli import ogrenme_adaptor as oa
    dizin = Path(dizin)
    ders = go._json(dizin / oa.DERS_DOSYASI)
    durum = go._json(dizin / oa.DURUM_DOSYASI)
    karne = go._json(dizin / oa.KARNE_DOSYASI)
    esleme = go._json(dizin / oa.ESLEME_DOSYASI)
    modeller = dizin / oa.MODEL_DIZINI
    filtre_var = sorted(p.stem for p in modeller.glob("*.json")) if modeller.is_dir() else []
    alinmayan: dict = {}
    for s in go._jsonl(dizin / "alinmayan_sinyaller.jsonl"):
        n = str(s.get("neden") or "bilinmiyor")
        alinmayan[n] = alinmayan.get(n, 0) + 1
    fren = go._json(dizin / oa.FREN_DOSYASI)
    return {"ders": ders if isinstance(ders, dict) else None, "fren": fren if isinstance(fren, dict) else None, "durum": durum if isinstance(durum, dict) else None,
            "karne": karne if isinstance(karne, dict) else None, "esleme": esleme if isinstance(esleme, dict) else {},
            "filtre": filtre_var, "alinmayan": alinmayan, "alinmayan_toplam": sum(alinmayan.values()),
            "veri_var": any(x is not None for x in (ders, durum, karne))}


def kurulum_adi(esleme: dict, kimlik: str) -> str:
    from motor.canli import ogrenme_adaptor as oa
    return esleme.get(kimlik) or oa.temiz_ad(kimlik)


def gizli_kurulumlar(set_yolu=None, esleme: Optional[dict] = None) -> set:
    """Gizli hesapların kurulum adları (çıktılardan süzülür)."""
    out = set()
    for kimlik, _klasor, gorunur in go._set_kayitlari(set_yolu) or []:
        if not gorunur:
            out.add(kurulum_adi(esleme or {}, kimlik))
    return out


def dersler(og: dict, gizli: set, simdi: datetime) -> dict:
    """{aktif: [(kimlik, durum, etki, n)], emekli: [(kimlik, gün)], gizli_adet}. Emekli: son EMEKLI_GUN günde emekli olanlar. Gizli kurulum dersleri sayıya düşer."""
    st = og.get("ders")
    if st is None:
        return {"aktif": [], "emekli": [], "gizli_adet": 0, "veri": False}
    esik = (simdi - timedelta(days=EMEKLI_GUN)).date().isoformat()
    aktif, emekli, gizli_adet = [], [], 0
    for kimlik, v in sorted(st.items()):
        if not isinstance(v, dict):
            continue
        if kimlik.partition(":")[2] in gizli:
            gizli_adet += 1
            continue
        if v.get("status") in ("alive", "candidate"):
            aktif.append((kimlik, v.get("status"), v.get("effect"), v.get("n")))
        elif v.get("status") == "retired" and str(v.get("retired_day") or "") >= esik:
            emekli.append((kimlik, v.get("retired_day")))
    aktif.sort(key=lambda x: (x[1] != "alive", x[0]))
    return {"aktif": aktif, "emekli": emekli, "gizli_adet": gizli_adet, "veri": True}


# ----------------------------------------------------------------------------------------------- hesap özeti
def hesap_ozeti(dizin) -> Optional[dict]:
    """ozet.json + stratejiler.json + islemler.jsonl -> {ozsermaye, toplam_pnl, acik, kapanan, son_islem, yazim}. ozet.json yoksa None."""
    dizin = Path(dizin)
    oz = go._json(dizin / "ozet.json")
    if not isinstance(oz, dict):
        return None
    sayac = oz.get("sayaclar") or {}
    acik = sayac.get("acik_pozisyon")
    if acik is None:
        st = go._json(dizin / "stratejiler.json") or {}
        acik = sum(len(s.get("acik_pozisyonlar") or []) for s in (st.get("stratejiler") or []) if isinstance(s, dict))
    son = None
    for x in go._jsonl(dizin / "islemler.jsonl"):
        z = x.get("cikis_zamani") or x.get("zaman")
        if z and (son is None or str(z) > son):
            son = str(z)
    return {"ozsermaye": _dec(oz.get("ozsermaye")), "toplam_pnl": _dec(oz.get("toplam_pnl")), "acik": acik, "kapanan": sayac.get("kapanan_islem"),
            "son_islem": son, "yazim": oz.get("yazim_zamani") or oz.get("zaman")}


def _durum_alanlari(og: dict, kurulum: Optional[str] = None) -> dict:
    """Filtre/drift durumu: filtre True/False/None (veri yok), drift 'uyari'/'normal'/None. kurulum None: hesap düzeyi (herhangi bir kurulum)."""
    if not og.get("veri_var"):
        return {"filtre": None, "drift": None}
    drift = (og.get("durum") or {}).get("drift_uyari")
    if kurulum is None:
        return {"filtre": bool(og["filtre"]), "drift": None if drift is None else ("uyari" if drift else "normal")}
    return {"filtre": kurulum in og["filtre"], "drift": None if drift is None else ("uyari" if kurulum in drift else "normal")}


def hesaplar(durum_dizini, ct=None, aday=None, set_yolu=None, env=None) -> dict:
    """-> {gorunur: [satır], gizli: satır|None, ct: satır|None, adaylar: [satır], gizli_kurulum: set}. Satır: {ad, kurulum, ozsermaye, toplam_pnl, acik, kapanan,
    son_islem, yazim, filtre, drift}. Hiçbir dizin okunamazsa listeler boş (çağıran 'henüz veri yok' yazar)."""
    dizin = Path(durum_dizini)
    og_ana = ogrenme_oku(dizin)
    esl = og_ana["esleme"]
    gorunur, gizli_rows, gizli_adet = [], [], 0
    for kimlik, klasor, g in go._set_kayitlari(set_yolu) or []:
        r = hesap_ozeti(dizin / "hesaplar" / klasor)
        if not g:
            gizli_adet += 1
        if r is None:
            continue
        if g:
            k = kurulum_adi(esl, kimlik)
            gorunur.append({"ad": go.kisa_ad(kimlik), "kurulum": k, **r, **_durum_alanlari(og_ana, k)})
        else:
            gizli_rows.append(r)
    gizli = None
    if gizli_adet and gizli_rows:
        gizli = {"ad": f"{go.GIZLI_AD} ({gizli_adet})", "kurulum": None, "ozsermaye": None, "filtre": None, "drift": None,
                 "toplam_pnl": sum((r["toplam_pnl"] for r in gizli_rows if r["toplam_pnl"] is not None), Decimal(0)) if gizli_rows else None,
                 "acik": sum(int(r["acik"]) for r in gizli_rows if r["acik"] is not None) if gizli_rows else None,
                 "kapanan": None, "son_islem": max((r["son_islem"] for r in gizli_rows if r["son_islem"]), default=None), "yazim": None}
    ctd = Path(ct) if ct is not None else ct_dizini(env)
    ct_satir = None
    r = hesap_ozeti(ctd) if ctd.is_dir() else None
    if r is not None:
        og = ogrenme_oku(ctd)
        kayitlar = go._jsonl(ctd / "ct_kadro" / "kadro_yon.jsonl")
        kadro = ((kayitlar[-1].get("veri") or {}).get("uretildi_utc") if kayitlar else None)
        ct_satir = {"ad": go.hg.CT_HESABI, "kurulum": "ct_konsensus", **r, **_durum_alanlari(og), "og": og, "kadro_uretildi": kadro}
    adaylar = []
    ad = Path(aday) if aday is not None else aday_dizini(env)
    if ad.is_dir():
        adlar = {}
        try:
            from motor.canli import aday_paper as ap
            from motor.canli.paper_v2 import hesap_dizin_adi
            adlar = {hesap_dizin_adi(k["id"]): go.kisa_ad(k["id"]) for k in ap.liste_yukle()}
        except Exception:  # noqa: BLE001
            adlar = {}
        for alt in sorted(p for p in ad.iterdir() if p.is_dir()):
            r = hesap_ozeti(alt)
            if r is None:
                continue
            og = ogrenme_oku(alt)
            adaylar.append({"ad": adlar.get(alt.name) or go.hg.okunur_ad(alt.name), "kurulum": alt.name, **r, **_durum_alanlari(og), "og": og})
    return {"gorunur": gorunur, "gizli": gizli, "ct": ct_satir, "adaylar": adaylar, "ana_ogrenme": og_ana,
            "gizli_kurulum": gizli_kurulumlar(set_yolu, esl)}
