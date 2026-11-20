#!/usr/bin/env python3
"""Holdout muhru (docs/ml/pbo-holdout-muhur-spec.md bolum 1). Yalniz rapor/kayit: karar kapisi degildir.

  python research/holdout_muhur.py muhurle                      # bir kez; muhur.json varsa reddeder (yeniden bayragi yok)
  python research/holdout_muhur.py dogrula                      # ayni hesabi tekrarlar; yalniz esit/farkli + farkli dosya adlari
  python research/holdout_muhur.py ac --aday-kumesi AD --gerekce "metin"   # bir kez; yalniz kayit tutar, degerlendirme yapmaz

Bu modul holdout satirlarina YALNIZ hash icin dokunur (satir sayisi, ilk/son zaman damgasi, kanonik bayt sha256). Fiyat, getiri,
ortalama gibi hicbir icerik degeri hesaplanmaz, yazdirilmaz. Baska hicbir research betigi bu modulu holdout verisi okumak icin
kullanmaz (tests/research/test_holdout_muhur_guard.py).
"""
from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from trader_engine.holdout import HOLDOUT  # noqa: E402  (donuk dosya; yalniz ice aktarilir)

HISTORY_DIR = ROOT / "var" / "history"
MUHUR_PATH = ROOT / "research" / "holdout" / "muhur.json"
ON_KAYIT_PATH = ROOT / "research" / "holdout" / "on_kayit_gunlugu.jsonl"
TIME_COL = "date"


class MuhurError(Exception):
    pass


def _col_bytes(s: pd.Series) -> bytes:
    """Sutunun kanonik baytlari: sayisal -> ham dizi; zaman -> UTC ns int64; digeri -> metin."""
    if s.dtype.kind == "M" or str(s.dtype).startswith("datetime64") or isinstance(s.dtype, pd.DatetimeTZDtype):
        t = pd.DatetimeIndex(s)
        t = t.tz_localize("UTC") if t.tz is None else t.tz_convert("UTC")
        return np.ascontiguousarray(t.tz_localize(None).to_numpy(dtype="datetime64[ns]").astype("int64")).tobytes()
    if s.dtype.kind in "biuf":
        return np.ascontiguousarray(s.to_numpy()).tobytes()
    return "\x1f".join(map(str, s.tolist())).encode("utf-8")


def _canonical_sha(df: pd.DataFrame) -> str:
    h = hashlib.sha256()
    for name in df.columns:                     # sutun sirasi dosyadaki gibi sabit
        s = df[name]
        h.update(str(name).encode("utf-8") + b"\x00" + str(s.dtype).encode("utf-8") + b"\x00")
        h.update(_col_bytes(s))
    return h.hexdigest()


def _iso(ts) -> str | None:
    if ts is None or pd.isna(ts):
        return None
    ts = pd.Timestamp(ts)
    ts = ts.tz_localize("UTC") if ts.tzinfo is None else ts.tz_convert("UTC")
    return ts.strftime("%Y-%m-%dT%H:%M:%SZ")


def hash_file(path: Path) -> dict:
    """Tek dosyanin holdout dilimi: yalniz {dosya, satir, ilk_ts, son_ts, sha256}."""
    df = pd.read_feather(path)
    if TIME_COL not in df.columns:
        raise MuhurError(f"{path.name}: '{TIME_COL}' sutunu yok")
    t = pd.DatetimeIndex(df[TIME_COL])
    t = t.tz_localize("UTC") if t.tz is None else t.tz_convert("UTC")
    lo, hi = pd.Timestamp(HOLDOUT[0]), pd.Timestamp(HOLDOUT[1])
    sl = df[(t >= lo) & (t < hi)]
    st = pd.DatetimeIndex(sl[TIME_COL])
    return {"dosya": path.name, "satir": int(len(sl)),
            "ilk_ts": _iso(st.min()) if len(sl) else None, "son_ts": _iso(st.max()) if len(sl) else None,
            "sha256": _canonical_sha(sl.reset_index(drop=True))}


def combined_sha(files: list[dict]) -> str:
    h = hashlib.sha256()
    for f in sorted(files, key=lambda x: x["dosya"]):
        h.update(f"{f['dosya']}\x00{f['satir']}\x00{f['sha256']}\n".encode("utf-8"))
    return h.hexdigest()


def compute(history_dir: Path) -> list[dict]:
    paths = sorted(Path(history_dir).glob("*.feather"))
    if not paths:
        raise MuhurError(f"{history_dir}: feather dosyasi yok")
    return [hash_file(p) for p in paths]


def _window() -> dict:
    return {"baslangic": HOLDOUT[0].strftime("%Y-%m-%d"), "bitis": HOLDOUT[1].strftime("%Y-%m-%d")}


def muhurle(history_dir: Path = HISTORY_DIR, out: Path = MUHUR_PATH, *, now: datetime | None = None,
            kayit: dict | None = None) -> dict:
    """`kayit` (istege bagli): `kayit_olustur` ciktisi; verilirse muhura "kayit" anahtari eklenir. Verilmezse bicim ESKISIYLE AYNIDIR."""
    out = Path(out)
    if out.exists():
        raise MuhurError(f"muhur zaten var: {out.name}; ikinci muhur basilmaz (yeniden bayragi yok)")
    files = compute(history_dir)
    doc = {"muhur_tarihi": (now or datetime.now(timezone.utc)).strftime("%Y-%m-%dT%H:%M:%SZ"),
           "holdout": _window(), "dosya_sayisi": len(files), "dosyalar": files,
           "birlesik_sha256": combined_sha(files), "acildi": False}
    if kayit is not None:
        doc["kayit"] = kayit
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(doc, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return doc


# ---------------------------------------------------------------------------------------------------------------------------
# Strateji/ayar/kod hash'i + on kayit gunlugu (1L3A motor/arastirma/v2/holdout.py `muhur_yaz`/`muhur_kontrol` ve `sabit.py`'dan
# uyarlandi). YALNIZ rapor/kayit: karar kapisi degildir; canli/paper motoruna etkisi yoktur. Eski muhur (kayit yok) `dogrula` ile
# AYNEN ESIT kalir; `dogrula` bu bolumu hic okumaz. Bicim geriye uyumlu: yeni alanlar istege bagli ("kayit", ayri gunluk dosyasi).
#
# Budama ("budama": kapi gecerse holdout neti <= 0 veya K2 p yuksek stratejiyi setten cikarma) UYGULANMADI: o mantik holdout
# SONUCUNU okuyup mühürlü seti degistirir; bu modulun "holdout icerigine hic dokunma" sozlesmesiyle ve muhurlu veri anlamiyla
# celisir. Yalniz belgelenir (docs/ml/pbo-holdout-muhur-spec.md ek not): holdout degerlendirmesi
# `holdout_degerlendir.py`'de kalir, setten cikarma karari insan/yeni on kayit gerektirir.
# ---------------------------------------------------------------------------------------------------------------------------
def sha256_dosya(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for blok in iter(lambda: f.read(1 << 20), b""):
            h.update(blok)
    return h.hexdigest()


def _git_commit() -> str | None:
    try:
        r = subprocess.run(["git", "rev-parse", "HEAD"], cwd=ROOT, capture_output=True, text=True, timeout=10)
        return r.stdout.strip() if r.returncode == 0 and r.stdout.strip() else None
    except (OSError, subprocess.SubprocessError):
        return None


def _goreli(p: Path) -> str:
    try:
        return Path(p).resolve().relative_to(ROOT).as_posix()
    except ValueError:
        return Path(p).as_posix()


def _hash_haritasi(yollar: list) -> dict:
    out = {}
    for p in sorted(Path(x) for x in yollar):
        if not p.is_file():
            raise MuhurError(f"hash'lenecek dosya yok: {p}")
        out[_goreli(p)] = sha256_dosya(p)
    return out


def kayit_olustur(stratejiler: list[str], ayar_dosyalari: list, kod_dosyalari: list, *, olcek: dict | None = None,
                  not_: str = "") -> dict:
    """Strateji listesi + ayar dosyalari sha256 + kod dosyalari sha256 + git commit (+ istege bagli olcek). Veri okumaz."""
    if not stratejiler or any(not str(s).strip() for s in stratejiler):
        raise MuhurError("strateji listesi bos olamaz")
    return {"surum": 1, "stratejiler": sorted(map(str, stratejiler)), "ayar_sha256": _hash_haritasi(ayar_dosyalari),
            "kod_sha256": _hash_haritasi(kod_dosyalari), "olcek": olcek or {}, "git_commit": _git_commit(), "not": not_}


def _zincir_sha(onceki: str, govde: dict) -> str:
    return hashlib.sha256((onceki + "\n" + json.dumps(govde, sort_keys=True, ensure_ascii=False)).encode("utf-8")).hexdigest()


def gunluk_oku(path: Path = ON_KAYIT_PATH) -> list[dict]:
    path = Path(path)
    if not path.exists():
        return []
    return [json.loads(x) for x in path.read_text(encoding="utf-8").splitlines() if x.strip()]


def on_kayit_yaz(kayit: dict, path: Path = ON_KAYIT_PATH, *, now: datetime | None = None) -> dict:
    """On kayit gunlugune (yalniz-ekleme, hash zincirli JSONL) bir kayit ekler. Holdout degerlendirmesinden ONCE cagrilmali;
    veri okumaz. Zincir: her satirin `zincir_sha256`'i onceki satirin degerine baglidir (arada degisiklik `gunluk_dogrula` ile bulunur)."""
    path = Path(path)
    onceki = gunluk_oku(path)
    onceki_sha = onceki[-1]["zincir_sha256"] if onceki else ""
    govde = {"olay": "on_kayit", "zaman": (now or datetime.now(timezone.utc)).strftime("%Y-%m-%dT%H:%M:%SZ"), "kayit": kayit}
    satir = {**govde, "onceki_sha256": onceki_sha, "zincir_sha256": _zincir_sha(onceki_sha, govde)}
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "a", encoding="utf-8") as f:
        f.write(json.dumps(satir, ensure_ascii=False) + "\n")
    return satir


def gunluk_dogrula(path: Path = ON_KAYIT_PATH) -> list[str]:
    """Zincir bozuklugu aciklamalari (bos liste = saglam)."""
    hata, onceki = [], ""
    for i, s in enumerate(gunluk_oku(path)):
        govde = {k: s[k] for k in ("olay", "zaman", "kayit") if k in s}
        if s.get("onceki_sha256") != onceki:
            hata.append(f"satir {i}: onceki_sha256 uyusmuyor")
        if s.get("zincir_sha256") != _zincir_sha(onceki, govde):
            hata.append(f"satir {i}: zincir_sha256 uyusmuyor")
        onceki = s.get("zincir_sha256", "")
    return hata


def kayit_dogrula(kayit: dict) -> list[str]:
    """Kayittaki ayar/kod hash'lerini simdiki dosyalarla karsilastirir -> farkli/eksik dosya aciklamalari (bos = ayni)."""
    fark = []
    for alan in ("ayar_sha256", "kod_sha256"):
        for yol, sha in kayit.get(alan, {}).items():
            p = ROOT / yol
            if not p.is_file():
                fark.append(f"{alan}: {yol} yok")
            elif sha256_dosya(p) != sha:
                fark.append(f"{alan}: {yol} degismis")
    return fark


def _load(out: Path) -> dict:
    out = Path(out)
    if not out.exists():
        raise MuhurError(f"muhur yok: {out.name}")
    return json.loads(out.read_text(encoding="utf-8"))


def dogrula(history_dir: Path = HISTORY_DIR, out: Path = MUHUR_PATH) -> tuple[bool, list[str]]:
    """-> (esit, farkli_dosya_adlari). Eksik/fazla dosya da farkli sayilir."""
    doc = _load(out)
    sealed = {f["dosya"]: f for f in doc["dosyalar"]}
    now = {f["dosya"]: f for f in compute(history_dir)}
    diff = sorted(n for n in set(sealed) | set(now) if sealed.get(n) != now.get(n))
    return (not diff and combined_sha(list(now.values())) == doc["birlesik_sha256"]), diff


def ac(aday_kumesi: str, gerekce: str, out: Path = MUHUR_PATH, *, now: datetime | None = None) -> dict:
    if not aday_kumesi.strip() or not gerekce.strip():
        raise MuhurError("aday kumesi ve gerekce bos olamaz")
    doc = _load(out)
    if doc.get("acildi"):
        raise MuhurError("muhur zaten acildi; ikinci acilis yok")
    doc["acildi"] = True
    doc["acilis"] = {"zaman": (now or datetime.now(timezone.utc)).strftime("%Y-%m-%dT%H:%M:%SZ"),
                     "aday_kumesi": aday_kumesi, "gerekce": gerekce, "birlesik_sha256": doc["birlesik_sha256"]}
    Path(out).write_text(json.dumps(doc, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return doc


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(allow_abbrev=False)
    sub = ap.add_subparsers(dest="cmd", required=True)
    for name in ("muhurle", "dogrula"):
        p = sub.add_parser(name)
        p.add_argument("--history-dir", default=str(HISTORY_DIR))
        p.add_argument("--muhur", default=str(MUHUR_PATH))
    p = sub.add_parser("ac")
    p.add_argument("--aday-kumesi", required=True)
    p.add_argument("--gerekce", required=True)
    p.add_argument("--muhur", default=str(MUHUR_PATH))
    p = sub.add_parser("on-kayit", help="strateji/ayar/kod hash'li on kayit gunlugu satiri ekler (veri okumaz)")
    p.add_argument("--strateji", action="append", required=True)
    p.add_argument("--ayar", action="append", default=[])
    p.add_argument("--kod", action="append", default=[])
    p.add_argument("--gunluk", default=str(ON_KAYIT_PATH))
    p = sub.add_parser("kayit-dogrula", help="gunluk zincirini ve son kaydin hash'lerini simdiki dosyalarla karsilastirir")
    p.add_argument("--gunluk", default=str(ON_KAYIT_PATH))
    a = ap.parse_args(argv)
    try:
        if a.cmd == "on-kayit":
            s = on_kayit_yaz(kayit_olustur(a.strateji, a.ayar, a.kod), Path(a.gunluk))
            print(f"on kayit eklendi: {s['zincir_sha256']}")
            return 0
        if a.cmd == "kayit-dogrula":
            satirlar = gunluk_oku(Path(a.gunluk))
            sorun = gunluk_dogrula(Path(a.gunluk)) + (kayit_dogrula(satirlar[-1]["kayit"]) if satirlar else ["gunluk bos"])
            print("ESIT" if not sorun else "FARKLI")
            for x in sorun:
                print(f"  {x}")
            return 0 if not sorun else 1
        if a.cmd == "muhurle":
            d = muhurle(Path(a.history_dir), Path(a.muhur))
            print(f"muhur basildi: {d['dosya_sayisi']} dosya, birlesik sha256 {d['birlesik_sha256']}")
        elif a.cmd == "dogrula":
            ok, diff = dogrula(Path(a.history_dir), Path(a.muhur))
            print("ESIT" if ok else "FARKLI")
            for n in diff:
                print(f"  farkli: {n}")
            return 0 if ok else 1
        else:
            d = ac(a.aday_kumesi, a.gerekce, Path(a.muhur))
            print(f"muhur acildi: {d['acilis']['zaman']} aday kumesi={a.aday_kumesi}")
    except MuhurError as e:
        print(f"RED: {e}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
