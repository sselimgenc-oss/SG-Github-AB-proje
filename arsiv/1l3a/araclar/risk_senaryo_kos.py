"""Risk senaryosu - işlem listesi üretici (yalnız geliştirme dönemi; sonuclar/risk_senaryo/PLAN.md).

20 paper stratejisini mevcut ayarlarıyla bir kez koşar (x1, x2), işlemleri sonuclar/risk_senaryo/islemler/<id>.parquet
olarak yazar (+ sembol sütunu). Portföy (pf__) için günlük getiri serisi yazılır.
Kullanım: python araclar/risk_senaryo_kos.py [--isci 4]
"""
from __future__ import annotations

import argparse
import json
import multiprocessing as mp
import re
import sys
import time
from pathlib import Path

KOK = Path(__file__).resolve().parents[1]
if str(KOK) not in sys.path:
    sys.path.insert(0, str(KOK))

import pandas as pd  # noqa: E402

from araclar import kapanis_kosu_listesi as kl  # noqa: E402
from motor.arastirma import wf_evren as we  # noqa: E402
from motor.arastirma.kapanis.tek_grafik import tek_ham_kos  # noqa: E402
from motor.arastirma.v2 import ham as hm  # noqa: E402
from motor.arastirma.v2 import sabit  # noqa: E402

CIKTI = KOK / "sonuclar" / "risk_senaryo" / "islemler"
TABLO = KOK / "sonuclar" / "evren" / "v2" / "maliyet_tablosu_v2.csv"
SET = KOK / "stratejiler" / "paper_v2_seti.json"
KAPANIS = KOK / "sonuclar" / "kapanis"


def guvenli(x: str) -> str:
    return re.sub(r"[^A-Za-z0-9_.-]+", "_", x)


def hesap_listesi() -> list:
    """-> [{id, kaynak, ad|satir, tf, evren, tur}]"""
    s = json.loads(SET.read_text())
    out = []
    listeler = {}
    for k in s["stratejiler"]:
        if k.get("kaynak") == "kapanis":
            if k["liste"] not in listeler:
                listeler[k["liste"]] = {r["kimlik"]: r for r in kl._csv_oku(KAPANIS / k["liste"])}
            satir = listeler[k["liste"]][k["kimlik"]]
            out.append({"id": "kap_" + guvenli(k["kimlik"]), "kaynak": "kapanis", "satir": satir, "tf": k["tf"],
                        "evren": k["evren"], "tur": k["tur"], "etiket": k["etiket"], "ad": satir["sinif"]})
        else:
            out.append({"id": guvenli(k["strateji"]), "kaynak": "v2", "ad": k["strateji"], "tf": k["tf"],
                        "evren": k["evren"], "tur": k["tur"], "etiket": k["etiket"]})
    return out


def _kur(h: dict):
    if h["kaynak"] == "kapanis":
        st, pf = kl.strateji_kur(h["satir"]["sinif"], h["satir"]["modul"], json.loads(h["satir"]["parametreler"]))
        assert not pf
        return st
    return hm.varsayilan_strateji(h["ad"])[1]


def _baslat():
    we.veri_ayarla(None, sabit.DONEM)


def gorev(a):
    h, sembol, carpan = a
    t0 = time.perf_counter()
    try:
        try:
            hm.veri_oku(sembol, h["tf"])
        except (FileNotFoundError, ValueError) as e:
            return (h["id"], sembol, carpan, None, f"veri_yok {type(e).__name__}", 0.0)
        ham, _, _ = tek_ham_kos(_kur(h), sembol, h["tf"], carpan, TABLO)
        ham = ham.copy()
        ham["sembol"] = sembol
        return (h["id"], sembol, carpan, ham, "", time.perf_counter() - t0)
    except hm.HoldoutSizintisi:
        raise
    except Exception as e:  # noqa: BLE001
        return (h["id"], sembol, carpan, None, f"HATA {type(e).__name__}: {e}"[:300], time.perf_counter() - t0)


def pf_kos(h: dict, carpan: float):
    from motor.arastirma.v2 import maliyet
    tablo = TABLO
    import hashlib  # noqa: F401
    cikti = KOK / "sonuclar" / "risk_senaryo" / "_pf_gecici"
    from motor.arastirma import evren_maliyet
    th = evren_maliyet.tablo_hash(pd.read_csv(tablo)) if False else ""
    meta = hm.pf_gorev(h["ad"], carpan, cikti, tablo, th, h["evren"])
    if meta.get("hata"):
        raise RuntimeError(meta["hata"])
    return pd.read_parquet(hm.dosya_yolu(cikti / "ham" / hm.carpan_adi(carpan), h["ad"], "1d", hm.PF_SEMBOL))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--isci", type=int, default=4)
    ap.add_argument("--sadece", default="")
    a = ap.parse_args()
    CIKTI.mkdir(parents=True, exist_ok=True)
    hesaplar = hesap_listesi()
    if a.sadece:
        hesaplar = [h for h in hesaplar if a.sadece in h["id"]]
    gor = []
    for h in hesaplar:
        if h["tur"] == "pf":
            continue
        for s in sabit.evren_listesi("kripto" if h["evren"] in ("kripto", "kripto13") else "genel"):
            for c in (1.0, 2.0):
                gor.append((h, s, c))
    print(f"{len(gor)} görev", flush=True)
    topla: dict = {}
    notlar: dict = {}
    t0 = time.time()
    with mp.Pool(a.isci, initializer=_baslat) as p:
        for i, (hid, s, c, ham, msg, sn) in enumerate(p.imap_unordered(gorev, gor, chunksize=1), 1):
            if ham is not None:
                topla.setdefault((hid, c), []).append(ham)
            notlar.setdefault(hid, []).append(f"{s} x{c:g}: {msg or 'ok'} ({sn:.1f}s)")
            if i % 50 == 0:
                print(f"{i}/{len(gor)} {time.time()-t0:.0f}s", flush=True)
    for h in hesaplar:
        if h["tur"] == "pf":
            continue
        for c in (1.0, 2.0):
            parcalar = [d for d in topla.get((h["id"], c), []) if len(d)]
            df = pd.concat(parcalar, ignore_index=True).sort_values("giris_zamani", kind="stable") if parcalar else pd.DataFrame()
            df.to_parquet(CIKTI / f"{h['id']}__x{int(c)}.parquet")
    (CIKTI.parent / "kos_notlari.json").write_text(json.dumps(notlar, ensure_ascii=False, indent=1))
    print("bitti", time.time() - t0, flush=True)


if __name__ == "__main__":
    main()
