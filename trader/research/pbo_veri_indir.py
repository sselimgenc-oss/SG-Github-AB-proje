#!/usr/bin/env python3
"""PBO kapsam genisletmesi: kagit evrenindeki, `var/history`te olmayan ciftlerin tarihsel mumlarini data.binance.vision'dan indirir.

  python research/pbo_veri_indir.py            # eksik ciftleri indirir; var olan cikti dosyalarini atlar (yeniden calistirilabilir)
  python research/pbo_veri_indir.py --yeniden  # ciktilari yeniden uretir (indirme sonucu deterministiktir)

Kurallar:
  - Holdout (2026-05-01 ->) ASLA istenmez: yalniz ay arsivleri BITIS_AY'a (2026-04) kadar indirilir ve satirlar ayrica `date < HOLDOUT[0]` suzulur.
  - `var/history` (80 dosya, holdout muhru) DEGISTIRILMEZ; yeni ciftler `var/history_pre/` altina (holdout satiri icermez) yazilir.
    Boylece muhur `dogrula` komutu (history dizinindeki fazla dosyayi "farkli" sayar) esit kalir. arm_harness iki dizine de bakar.
  - Yalniz USDS-M futures klines (15m,1h,4h,1d); her zip `.CHECKSUM` sha256 ile dogrulanir. fapi.binance.com KULLANILMAZ.
  - Arsivde bulunmayan sembol atlanir ve `research/arm_series/veri_indirme.json`a yazilir (uydurma yok). Kisa gecmis oldugu gibi kalir.
  - Bagimlilik: requests + stdlib + pandas/pyarrow.
"""
from __future__ import annotations

import argparse
import hashlib
import io
import json
import sys
import zipfile
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pandas as pd
import requests

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))
from trader_engine.holdout import HOLDOUT  # noqa: E402

BASE = "https://data.binance.vision/data/futures/um/monthly/klines"
HISTORY = ROOT / "var" / "history"
OUT = ROOT / "var" / "history_pre"
REPORT = ROOT / "research" / "arm_series" / "veri_indirme.json"
TFS = ("15m", "1h", "4h", "1d")
BASLANGIC = (2019, 9)      # en eski olasi USDS-M arsivi; olmayan aylar 404 -> atlanir
BITIS = (2026, 4)          # son istenen ay; holdout (2026-05) hic istenmez
assert (BITIS[0], BITIS[1] + 1) == (HOLDOUT[0].year, HOLDOUT[0].month)
COLS = ["open_time", "open", "high", "low", "close", "volume"]


def months() -> list[str]:
    y, m = BASLANGIC
    out = []
    while (y, m) <= BITIS:
        out.append(f"{y:04d}-{m:02d}")
        y, m = (y + 1, 1) if m == 12 else (y, m + 1)
    return out


def symbol(pair: str) -> str:
    return pair.split("/")[0] + "USDT"


def stem(pair: str) -> str:
    return pair.replace("/", "_") + "_USDT"


def _get(sess: requests.Session, url: str, tries: int = 4) -> bytes | None:
    for k in range(tries):
        try:
            r = sess.get(url, timeout=60)
            if r.status_code == 404:
                return None
            if r.status_code == 200:
                return r.content
        except requests.RequestException:
            pass
    raise RuntimeError(f"indirilemedi: {url}")


def fetch_month(sess: requests.Session, sym: str, tf: str, ym: str) -> pd.DataFrame | None:
    url = f"{BASE}/{sym}/{tf}/{sym}-{tf}-{ym}.zip"
    z = _get(sess, url)
    if z is None:
        return None
    chk = _get(sess, url + ".CHECKSUM")
    if chk is not None and hashlib.sha256(z).hexdigest() != chk.decode().split()[0]:
        raise RuntimeError(f"sha256 uyusmuyor: {url}")
    with zipfile.ZipFile(io.BytesIO(z)) as zf:
        raw = zf.read(zf.namelist()[0]).decode()
    first = raw.split("\n", 1)[0]
    df = pd.read_csv(io.StringIO(raw), header=0 if not first[:1].isdigit() else None, usecols=range(6), names=COLS if first[:1].isdigit() else None)
    if not first[:1].isdigit():
        df.columns = COLS
    return df


def build_one(args: tuple) -> dict:
    pair, tf = args
    sym = symbol(pair)
    sess = requests.Session()
    frames, got = [], []
    for ym in months():
        df = fetch_month(sess, sym, tf, ym)
        if df is not None:
            frames.append(df)
            got.append(ym)
    if not frames:
        return {"pair": pair, "tf": tf, "n": 0}
    d = pd.concat(frames, ignore_index=True)
    ot = d["open_time"].astype("int64")
    d["date"] = pd.to_datetime(ot, unit="ms", utc=True).astype("datetime64[ms, UTC]")
    d = d.drop(columns="open_time").drop_duplicates("date").sort_values("date")
    d = d[d["date"] < pd.Timestamp(HOLDOUT[0])]                          # holdout satiri asla yazilmaz
    d = d[["date", "open", "high", "low", "close", "volume"]].astype({c: "float64" for c in ("open", "high", "low", "close", "volume")})
    d = d.reset_index(drop=True)
    assert len(d) == 0 or d["date"].iloc[-1] < pd.Timestamp(HOLDOUT[0])
    OUT.mkdir(parents=True, exist_ok=True)
    d.to_feather(OUT / f"{stem(pair)}-{tf}-futures.feather")
    return {"pair": pair, "tf": tf, "n": int(len(d)), "ilk": str(d["date"].iloc[0]), "son": str(d["date"].iloc[-1]), "aylar": len(got)}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--yeniden", action="store_true")
    a = ap.parse_args(argv)
    cfg = json.loads((ROOT / "config" / "engine.paper.json").read_text(encoding="utf-8"))
    todo, mevcut = [], []
    for p in cfg["pairs"]:
        if (HISTORY / f"{stem(p)}-4h-futures.feather").exists():
            mevcut.append(p)
        else:
            todo.append(p)
    jobs = [(p, tf) for p in todo for tf in TFS if a.yeniden or not (OUT / f"{stem(p)}-{tf}-futures.feather").exists()]
    with ThreadPoolExecutor(32) as ex:
        list(ex.map(build_one, jobs))
    sonuc = []                                        # rapor, diskteki ciktilardan uretilir (kesilmis onceki kosular dahil)
    for p in todo:
        for tf in TFS:
            f = OUT / f"{stem(p)}-{tf}-futures.feather"
            if f.exists():
                d = pd.read_feather(f, columns=["date"])
                sonuc.append({"pair": p, "tf": tf, "n": int(len(d)), "ilk": str(d["date"].iloc[0]), "son": str(d["date"].iloc[-1])})
    eklenen = sorted({r["pair"] for r in sonuc if r["tf"] == "4h"})
    atlanan = {p: "data.binance.vision'da " + symbol(p) + " USDS-M klines arsivi yok (404)" for p in todo if p not in eklenen}
    doc = {"kaynak": BASE, "bitis_ay": f"{BITIS[0]}-{BITIS[1]:02d}", "mevcut_history_ciftleri": mevcut, "eklenen": eklenen,
           "atlanan": atlanan, "sonuclar": sonuc}
    REPORT.parent.mkdir(parents=True, exist_ok=True)
    REPORT.write_text(json.dumps(doc, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"eklenen={len(eklenen)} atlanan={len(atlanan)} {list(atlanan)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
