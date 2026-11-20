"""Boşluk maruziyeti: açık hisse/emtia pozisyonlarının fiyat boşluğunda (kapanış -> açılış) kaybı. YALNIZ ÖLÇÜM ve BİLDİRİM.

Limit, boyut, kaldıraç, strateji ve emirlere dokunmaz; pozisyon açmaz/kapatmaz. Hata paper'ı düşürmez.
  - Formül: pozisyon nominali x g, ters yönde (yön fark etmez: en kötü durum). g = BOSLUK_G = %20 (sabit).
  - "Tarihsel en kötü": sonuclar/olcum/bosluk_seans/OZET.md ölçümü (yalnız geliştirme dönemi): hisse en büyük boşluk %37,6 (AMD 2025-10-06),
    emtia NATGAS hariç en büyük %35,25 (WTI 2020-04-19).
  - Kripto 7/24 işlem görür: boşluk YOK sayılır; ayrı tek satır, kayba katılmaz.
  - Eşik: hesap kill / strateji kill (CANLI_LIMITLER) ve paper kill (SERT_LIMITLER); en düşüğü alınır. Eşiği kod okur, burada sayı yazılı değil.
  - Uyarı: seans "normal"den "kapalı/genişletilmiş"e geçmeden önceki son 30 dk içinde, herhangi bir hesabın %20 boşluk kaybı eşiği aşarsa
    Telegram WARN (aynı uyarı 6 saatte bir); risk eşiğin altına inince tek INFO. Gizli hesaplar adsız: "gizli_hesaplar (N)".
  - Çıktı: durum dizininde `bosluk_maruziyet_v1.json` (pano kartı ve günlük özet okur; her turda yazılır).
"""
from __future__ import annotations

import json
import logging
import os
from datetime import timedelta
from decimal import Decimal
from pathlib import Path
from typing import Optional

import pandas as pd

from motor.canli import paper_takvim as pt

log = logging.getLogger("bosluk_maruziyet")
SEMA = "bosluk_maruziyet.v1"
DOSYA = "bosluk_maruziyet_v1.json"
DURUM_DOSYASI = "bosluk_maruziyet_durum.json"
BOSLUK_G = 0.20                       # sabit: kapanış öncesi stres boşluğu
PENCERE_DK = 30                       # seans değişiminden önceki son 30 dk
TEKRAR_SN = 6 * 3600                  # aynı uyarı en çok 6 saatte bir
TARIHSEL_EN_KOTU = {"hisse": 0.3758, "emtia": 0.3525}      # OZET.md: hisse maks %37,58; emtia (NATGAS hariç) hafta sonu maks %35,25
GIZLI_AD = "Diğer hesaplar"
KRIPTO_NOT = "Kripto 7/24 işlem görür: boşluk yok sayıldı, kayba katılmadı."
ANAHTAR = "bosluk_riski"


def esik_oran() -> float:
    """Hesap/strateji kill eşiklerinin en düşüğü (kesir). Kaynak: CANLI_LIMITLER ve SERT_LIMITLER (burada sayı yazılı değil)."""
    from motor.canli.borsa.canli_limitler import CANLI_LIMITLER as C
    from motor.risk.limitler import SERT_LIMITLER as S
    return min(float(C.strateji_kill_oran), float(C.hesap_kill_oran), float(S.kill_switch_dusus_yuzde) / 100.0)


def pencerede_mi(sembol: str, simdi) -> bool:
    """Hisse/emtia: şimdi 'normal' seans ve PENCERE_DK dk sonra normal değil (kapanış/genişletilmişe geçiş, hafta sonu/tatil öncesi dahil)."""
    if pt.tur(sembol) == "kripto":
        return False
    t = pd.Timestamp(simdi)
    return pt.seans_dilimi(sembol, t) == "normal" and pt.seans_dilimi(sembol, t + timedelta(minutes=PENCERE_DK)) != "normal"


def hesapla(hesaplar: list, simdi, esik: Optional[float] = None, g: float = BOSLUK_G) -> dict:
    """Saf hesap. hesaplar: [{"ad", "gizli": bool, "kasa": sayı, "pozisyonlar": [{"sembol", "nominal"}]}]. -> çıktı sözlüğü (şema SEMA)."""
    esik = esik_oran() if esik is None else esik
    satirlar, gizliler, kripto_nom, pencere = [], [], 0.0, False
    for h in hesaplar:
        he = tar = 0.0
        for x in h.get("pozisyonlar", []):
            nom, s = abs(float(x["nominal"])), x["sembol"]
            sinif = pt.tur(s)
            if sinif == "kripto":
                kripto_nom += nom
                continue
            he += nom
            tar += nom * TARIHSEL_EN_KOTU[sinif]
            pencere = pencere or pencerede_mi(s, simdi)
        kasa = float(h.get("kasa") or 0.0)
        zirve = float(h.get("zirve") or 0.0)
        zirve = max(zirve, kasa)                       # zirve bilinmiyorsa/kasadan düşükse kasa: mevcut düşüş 0 sayılır
        kill = ((zirve - kasa) + he * g) / zirve if zirve > 0 and kasa > 0 else None     # %g boşluktan sonra zirveden düşüş (kill ölçüsü)
        r = {"ad": h["ad"], "gizli": bool(h.get("gizli")), "kasa": kasa, "hisse_emtia_nominal": he,
             "kayip_yuzde": (he * g / kasa if kasa > 0 else None), "tarihsel_yuzde": (tar / kasa if kasa > 0 else None),
             "zirve": zirve, "kill_yuzde": kill}
        r["ihlal"] = kill is not None and kill >= esik - 1e-12      # kill ">=" ile tetiklenir; mevcut zirveden düşüş de sayılır
        (gizliler if r["gizli"] else satirlar).append(r)
    if gizliler:                                   # gizli hesaplar adsız tek satır: en kötü hesabın değerleri
        w = max(gizliler, key=lambda r: (r["kill_yuzde"] or 0.0, r["kayip_yuzde"] or 0.0))
        satirlar.append({**w, "ad": f"{GIZLI_AD} ({len(gizliler)})", "ihlal": any(r["ihlal"] for r in gizliler)})
    tum = [r for r in satirlar if r["kayip_yuzde"] is not None]
    return {"sema": SEMA, "zaman": pd.Timestamp(simdi).isoformat(), "boslukg": g, "esik_yuzde": esik, "pencerede": pencere,
            "hesaplar": satirlar, "en_kotu_kayip_yuzde": max((r["kayip_yuzde"] for r in tum), default=None),
            "en_kotu_tarihsel_yuzde": max((r["tarihsel_yuzde"] for r in tum), default=None),
            "kripto": {"nominal": kripto_nom, "not": KRIPTO_NOT},
            "tarihsel_kaynak": "sonuclar/olcum/bosluk_seans/OZET.md: hisse maks %37,6; emtia (NATGAS hariç) maks %35,3"}


def _yuzde(x) -> str:
    return "—" if x is None else f"{x * 100:.1f}".replace(".", ",")


def uyari_metni(o: dict) -> str:
    from motor.canli import telegram as tg
    satir = [f"Kapanış öncesi boşluk riski: {tg.e(r['ad'])} açık hisse/emtia pozisyonları %{BOSLUK_G * 100:g} boşlukta kasanın "
             f"%{_yuzde(r['kayip_yuzde'])}'ini kaybettirir (kill eşiği %{_yuzde(o['esik_yuzde'])})" for r in o["hesaplar"] if r["ihlal"]]
    return "\n".join([tg.ust("WARN")] + satir)


def duzeldi_metni() -> str:
    from motor.canli import telegram as tg
    return f"{tg.ust('INFO')} Boşluk riski düzeldi"


def degerlendir(o: dict, bld, durum: dict) -> dict:
    """Bildirim kararı. durum {"uyarildi": bool} (çağıran kalıcı tutar). Pozisyon/limit değiştirmez."""
    ihlal = any(r["ihlal"] for r in o["hesaplar"])
    if ihlal and o["pencerede"]:
        if bld.mesaj(ANAHTAR, uyari_metni(o), TEKRAR_SN):
            durum["uyarildi"] = True
    elif not ihlal and durum.get("uyarildi"):
        bld.gonder(duzeldi_metni())
        durum["uyarildi"] = False
    return durum


def hesaplari_cikar(p) -> list:
    """Paper nesnesinden hesap listesi (v2: p.hesaplar; tek hesap: p). Yalnız okur."""
    hs = getattr(p, "hesaplar", None)
    if hs:
        gorunur = getattr(p, "gorunur_adlar", set(hs))
        kaynak = [(k, h, k in gorunur) for k, h in hs.items()]
    else:
        kaynak = [("paper", p, True)]
    out = []
    for k, h, g in kaynak:
        m = h.motor
        poz = [{"sembol": x.sembol, "nominal": float(Decimal(m.son_kap[x.sembol]) * x.miktar)} for x in m.acik.values() if x.sembol in m.son_kap]
        ad = k
        if g:
            from motor.canli.gunluk_ozet import kisa_ad
            ad = kisa_ad(k)
        out.append({"ad": ad, "gizli": not g, "kasa": float(m.ozsermaye()), "zirve": float(getattr(m, "zirve", 0) or 0), "pozisyonlar": poz})
    return out


def _oku(yol: Path):
    try:
        return json.loads(Path(yol).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def _yaz(yol: Path, o: dict) -> None:
    tmp = Path(yol).with_name(f".{Path(yol).name}.tmp-{os.getpid()}")
    tmp.write_text(json.dumps(o, ensure_ascii=False, allow_nan=False), encoding="utf-8")
    os.replace(tmp, yol)


def oku(durum_dizini) -> Optional[dict]:
    """Pano / günlük özet için son ölçüm; yok/bozuksa None."""
    o = _oku(Path(durum_dizini) / DOSYA)
    return o if isinstance(o, dict) and o.get("sema") == SEMA else None


def tur_kancasi(p, simdi, durum_dizini, bld=None) -> Optional[dict]:
    """Paper turunda çağrılır: ölçer, dosyaya yazar, (bld verilmişse) uyarır. Hata paper'ı durdurmaz (None döner)."""
    try:
        d = Path(durum_dizini)
        o = hesapla(hesaplari_cikar(p), simdi)
        _yaz(d / DOSYA, o)
        if bld is not None:
            durum = _oku(d / DURUM_DOSYASI) or {}
            once = bool(durum.get("uyarildi"))
            durum = degerlendir(o, bld, durum)
            if bool(durum.get("uyarildi")) != once:
                _yaz(d / DURUM_DOSYASI, durum)
        return o
    except Exception:  # noqa: BLE001
        log.exception("boşluk maruziyeti hesaplanamadı (paper sürer)")
        return None


def _p100(x):
    return None if x is None else round(float(x) * 100, 2)


def ozet_alani(durum_dizini) -> Optional[dict]:
    """gunluk_ozet JSON'u için küçük alan."""
    o = oku(durum_dizini)
    if o is None:
        return None
    return {"bosluk_yuzde": BOSLUK_G * 100, "en_kotu_kayip_yuzde": _p100(o.get("en_kotu_kayip_yuzde")),
            "en_kotu_tarihsel_yuzde": _p100(o.get("en_kotu_tarihsel_yuzde")), "esik_yuzde": _p100(o.get("esik_yuzde")),
            "esik_asan_hesap": sum(1 for r in o.get("hesaplar", []) if r.get("ihlal"))}
