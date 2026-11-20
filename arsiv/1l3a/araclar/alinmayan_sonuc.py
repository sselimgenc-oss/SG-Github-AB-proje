"""Alınmayan sinyaller: "alınsaydı ne olurdu" (YALNIZ ANALİZ; motoru/riski etkilemez).

Girdi: durum dizinindeki `alinmayan_sinyaller.jsonl` (+ `.1`). Her satır karar anından SONRAKİ mumlarla simüle edilir (lookahead yok:
yalnız açılış zamanı >= karar anı olan mumlar kullanılır). Giriş = satırdaki `fiyat`. Mum içinde stop ve hedef birlikte değerse STOP sayılır (kötümser).
Açılışta stop/hedef ötesine atlama (gap) açılış fiyatından kapanır. `zaman_cikisi_mum` varsa motorla aynı kural (`cikislar.zaman_doldu`): giriş mumu dahil
N mum kapanınca sonraki açılışta çıkış. Maliyet/kayma/funding YOK (brüt R). Veri yetmezse sonuç `acik` (çözülmedi).

Kullanım: python araclar/alinmayan_sonuc.py [DURUM_DIZINI] [--veri-dizin DIZIN]
"""
from __future__ import annotations

import argparse
import json
import sys
from collections import defaultdict
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from motor.strateji.cikislar import zaman_doldu  # noqa: E402

DOSYA = "alinmayan_sinyaller.jsonl"


def satirlari_oku(dizin) -> list:
    out = []
    for ad in (DOSYA + ".1", DOSYA):
        yol = Path(dizin) / ad
        if yol.exists():
            out += [json.loads(s) for s in yol.read_text(encoding="utf-8").splitlines() if s.strip()]
    return out


def _f(x):
    return None if x is None else float(x)


def simule(satir: dict, mum: pd.DataFrame) -> dict:
    """mum: UTC açılış indeksli acilis/yuksek/dusuk/kapanis. -> {sonuc: stop|hedef|zaman|acik|gecersiz, r, cikis_fiyati, cikis_zamani}."""
    yon = 1 if satir["yon"] == "long" else -1
    giris, stop, hedef = _f(satir["fiyat"]), _f(satir.get("stop")), _f(satir.get("hedef"))
    if giris is None or stop is None or (giris - stop) * yon <= 0:
        return {"sonuc": "gecersiz", "r": None, "cikis_fiyati": None, "cikis_zamani": None}
    z = pd.Timestamp(satir["zaman"])
    z = z.tz_localize("UTC") if z.tzinfo is None else z.tz_convert("UTC")
    m = mum[mum.index >= z]                              # YALNIZ karar anından sonraki mumlar
    risk, zc = abs(giris - stop), satir.get("zaman_cikisi_mum")

    def bitir(sonuc, fiyat, zaman):
        return {"sonuc": sonuc, "r": (fiyat - giris) * yon / risk, "cikis_fiyati": fiyat, "cikis_zamani": str(zaman)}
    for n, (zaman, b) in enumerate(m.iterrows(), start=1):
        a, h, l = float(b["acilis"]), float(b["yuksek"]), float(b["dusuk"])
        if n > 1:                                         # giriş mumunun açılışı giriştir; sonrakilerde açılış boşluğu kontrol edilir
            if (a - stop) * yon <= 0:
                return bitir("stop", a, zaman)
            if hedef is not None and (a - hedef) * yon >= 0:
                return bitir("hedef", a, zaman)
        if (stop - (l if yon == 1 else h)) * yon >= 0:
            return bitir("stop", stop, zaman)
        if hedef is not None and ((h if yon == 1 else l) - hedef) * yon >= 0:
            return bitir("hedef", hedef, zaman)
        if zaman_doldu(n, zc):
            sonraki = m.iloc[n:n + 1]
            if len(sonraki):
                return bitir("zaman", float(sonraki["acilis"].iloc[0]), sonraki.index[0])
            return {"sonuc": "acik", "r": None, "cikis_fiyati": None, "cikis_zamani": None}
    return {"sonuc": "acik", "r": None, "cikis_fiyati": None, "cikis_zamani": None}


def ozet(sonuclar: list) -> list:
    """[(satır, sonuç)] -> neden bazında özet satırları."""
    g = defaultdict(list)
    for s, r in sonuclar:
        g[s["neden"]].append(r)
    out = []
    for neden, rs in sorted(g.items()):
        c = [x["r"] for x in rs if x["r"] is not None]
        out.append({"neden": neden, "sinyal": len(rs), "cozulen": len(c), "kazanan": sum(1 for x in c if x > 0),
                    "ort_r": sum(c) / len(c) if c else None, "toplam_r": sum(c)})
    return out


def tablo(satirlar: list) -> str:
    bas = f"{'neden':26}{'sinyal':>8}{'cozulen':>9}{'kazanan':>9}{'ort_R':>9}{'toplam_R':>10}"
    gov = [bas, "-" * len(bas)]
    for o in satirlar:
        gov.append(f"{o['neden']:26}{o['sinyal']:>8}{o['cozulen']:>9}{o['kazanan']:>9}"
                   f"{'-' if o['ort_r'] is None else format(o['ort_r'], '.2f'):>9}{o['toplam_r']:>10.2f}")
    return "\n".join(gov)


def calistir(dizin, mum_getir) -> list:
    """mum_getir(sembol, tf) -> DataFrame | None. -> [(satır, sonuç)]"""
    onbellek, out = {}, []
    for s in satirlari_oku(dizin):
        k = (s["sembol"], s.get("tf"))
        if k not in onbellek:
            try:
                onbellek[k] = mum_getir(*k)
            except Exception:  # noqa: BLE001
                onbellek[k] = None
        m = onbellek[k]
        out.append((s, simule(s, m) if m is not None else {"sonuc": "acik", "r": None, "cikis_fiyati": None, "cikis_zamani": None}))
    return out


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("dizin", nargs="?", default="durum")
    ap.add_argument("--veri-dizin", default=None)
    a = ap.parse_args(argv)
    from motor.veri import depo

    def getir(sembol, tf):
        return depo.mum_oku(sembol, tf, dizin=Path(a.veri_dizin) if a.veri_dizin else None, kilit_ac=True,
                            gerekce="alinmayan sinyal sonuc analizi (paper donemi, karar sonrasi mumlar)")
    sonuc = calistir(a.dizin, getir)
    print(tablo(ozet(sonuc)) if sonuc else "alınmayan sinyal kaydı yok")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
