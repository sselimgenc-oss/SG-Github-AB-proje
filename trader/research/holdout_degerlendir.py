#!/usr/bin/env python3
"""Holdout degerlendirme betigi (docs/ml/holdout-degerlendirme-spec.md). HAZIRLANDI; muhur kapaliyken CALISTIRILAMAZ.

  python research/holdout_degerlendir.py --aday-kumesi "T1@4h,R1@4h"

KILIT NASIL KORUNUR (trader_engine/holdout.py donuk, DEGISTIRILMEDI; check_holdout hicbir yerde atlatilmaz/zayiflatilmaz):
  * check_holdout motor/backtest/arm_harness/egitim yollarinda aynen calisir; bu betik onlara hicbir yetki vermez.
  * Bu betik kendi okuyucusunu (`_oku`) tasir; holdout satirlari YALNIZCA bu okuyucu ile, YALNIZCA asagidaki kapilar gecildikten sonra
    okunur. Baska hicbir modul bu betigi iceri almaz (tests/research/test_holdout_degerlendir.py statik kilidi).
  * Kapilar (sirayla; ilk ikisi HIC veri okumaz, ucuncusu yalniz mühurdeki hash'in tekrar hesabidir):
      1. muhur dosyasi var, `acildi is True` ve acilis kaydi var;
      2. acilis kaydindaki aday kumesi == --aday-kumesi (kume olarak, sirasiz);
      3. muhur hash dogrulamasi ESIT (research muhur betigindeki `dogrula` ile ayni kanonik hesap; o modul baska betige
         iceri alinamadigi icin burada bagimsiz yeniden yazildi, esdegerligi testle sabittir). FARKLI ise veri degerlendirmeye girmez.
  * Gercek `var/history` yalniz gercek muhur dosyasiyla birlikte kabul edilir (sahte muhur ile gercek veriye yonlendirme yok).
  * Cikti dosyasi varsa reddeder: tek seferlik (sonuc gorulup tekrar denenmez).
Cikti: research/holdout/degerlendirme_<aday>.json + .md. Sonuc gorulmeden once yazilan olcular ve gecme olcutu: spec belgesi.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "research"))

import arm_harness as H  # noqa: E402  (ayni simulator, ayni maliyet izgarasi; modul-seviyesinde yalniz sabitler)
from trader_core.stats import deflated_sharpe, return_moments  # noqa: E402
from trader_engine.holdout import HOLDOUT  # noqa: E402  (donuk dosya; yalniz sabit ice aktarilir)

LO, HI = pd.Timestamp(HOLDOUT[0]), pd.Timestamp(HOLDOUT[1])
REAL_HISTORY = ROOT / "var" / "history"
MUHUR_PATH = ROOT / "research" / "holdout" / "muhur.json"
PBO_OZET = ROOT / "research" / "holdout" / "pbo_ozet.json"
OUT_DIR = ROOT / "research" / "holdout"
CONFIG = ROOT / "config" / "engine.paper.json"
TIME_COL = "date"
PRIMARY = "f1|s5"          # ana maliyet hucresi (taker x1 + 5 bp kayma), sonuctan once sabit
STRESS = "f2|s5"           # stres hucresi
SHARPE_MIN = 0.0
DSR_MIN = 0.95
ANN = math.sqrt(365.0)
VERSION = "holdout-deger-v1"


class Red(Exception):
    """Kapi reddi: hicbir (holdout) veri okunmadan durulur."""


# ----------------------------------------------------------------------------------------- aday kumesi
def parse_aday(s: str) -> tuple[str, ...]:
    """'T1@4h,R1@1d|trail_atr=2.5' -> sirali tekrarsiz ('R1@1d|trail_atr=2.5', 'T1@4h|def'). Gecersiz -> Red."""
    items = []
    for raw in (s or "").split(","):
        raw = raw.strip()
        if not raw:
            continue
        head, _, tag = raw.partition("|")
        setup, _, tf = head.partition("@")
        tag = tag or "def"
        if setup not in H.GRID or tf not in H.GRID[setup]["tfs"] or tag not in {v["tag"] for v in H.variants(setup)}:
            raise Red(f"gecersiz aday ogesi: {raw!r}")
        items.append(f"{setup}@{tf}|{tag}")
    if not items:
        raise Red("aday kumesi bos")
    return tuple(sorted(set(items)))


def slug(items: tuple[str, ...]) -> str:
    return re.sub(r"[^A-Za-z0-9._=-]+", "_", "+".join(items)).strip("_")


# ----------------------------------------------------------------------------------------- muhur hash (bagimsiz yeniden yazim)
def _col_bytes(s: pd.Series) -> bytes:
    if s.dtype.kind == "M" or str(s.dtype).startswith("datetime64") or isinstance(s.dtype, pd.DatetimeTZDtype):
        t = pd.DatetimeIndex(s)
        t = t.tz_localize("UTC") if t.tz is None else t.tz_convert("UTC")
        return np.ascontiguousarray(t.tz_localize(None).to_numpy(dtype="datetime64[ns]").astype("int64")).tobytes()
    if s.dtype.kind in "biuf":
        return np.ascontiguousarray(s.to_numpy()).tobytes()
    return "\x1f".join(map(str, s.tolist())).encode("utf-8")


def _canonical_sha(df: pd.DataFrame) -> str:
    h = hashlib.sha256()
    for name in df.columns:
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


def _hash_file(path: Path) -> dict:
    df = pd.read_feather(path)
    t = pd.DatetimeIndex(df[TIME_COL])
    t = t.tz_localize("UTC") if t.tz is None else t.tz_convert("UTC")
    sl = df[(t >= LO) & (t < HI)]
    st = pd.DatetimeIndex(sl[TIME_COL])
    return {"dosya": path.name, "satir": int(len(sl)), "ilk_ts": _iso(st.min()) if len(sl) else None,
            "son_ts": _iso(st.max()) if len(sl) else None, "sha256": _canonical_sha(sl.reset_index(drop=True))}


def _combined(files: list[dict]) -> str:
    h = hashlib.sha256()
    for f in sorted(files, key=lambda x: x["dosya"]):
        h.update(f"{f['dosya']}\x00{f['satir']}\x00{f['sha256']}\n".encode("utf-8"))
    return h.hexdigest()


def hash_esit(history_dir: Path, doc: dict) -> tuple[bool, list[str]]:
    paths = sorted(Path(history_dir).glob("*.feather"))
    if not paths:
        return False, ["<feather yok>"]
    now = {f["dosya"]: f for f in map(_hash_file, paths)}
    sealed = {f["dosya"]: f for f in doc["dosyalar"]}
    diff = sorted(n for n in set(sealed) | set(now) if sealed.get(n) != now.get(n))
    return (not diff and _combined(list(now.values())) == doc["birlesik_sha256"]), diff


# ----------------------------------------------------------------------------------------- kapilar
def kapi_1_2(muhur_path: Path, aday: tuple[str, ...]) -> dict:
    """Veri OKUMAZ. Muhur acik degil / acilis kaydi yok / aday kumesi eslesmiyor -> Red."""
    p = Path(muhur_path)
    if not p.exists():
        raise Red(f"muhur yok: {p.name}")
    doc = json.loads(p.read_text(encoding="utf-8"))
    if doc.get("acildi") is not True:
        raise Red("muhur KAPALI (acildi != true); degerlendirme yapilmaz")
    ac = doc.get("acilis")
    if not isinstance(ac, dict) or not ac.get("aday_kumesi"):
        raise Red("acilis kaydi yok")
    try:
        kayitli = parse_aday(ac["aday_kumesi"])
    except Red as e:
        raise Red(f"acilis kaydindaki aday kumesi cozulemedi: {e}") from None
    if kayitli != aday:
        raise Red(f"aday kumesi acilis kaydiyla eslesmiyor (kayit: {list(kayitli)}, arguman: {list(aday)})")
    if ac.get("birlesik_sha256") != doc.get("birlesik_sha256"):
        raise Red("acilis kaydindaki hash muhurdeki ile ayni degil")
    return doc


def kapi_3(history_dir: Path, doc: dict) -> None:
    ok, diff = hash_esit(history_dir, doc)
    if not ok:
        raise Red(f"muhur hash dogrulamasi FARKLI: {diff[:10]}")


# ----------------------------------------------------------------------------------------- veri / simulasyon
def _oku(history_dir: Path, pair: str, tf: str, hi: pd.Timestamp) -> pd.DataFrame | None:
    """[GRID_START, hi) mumlari. YALNIZ kapilar gecildikten sonra cagrilir (hi=HI) ya da holdout oncesi (hi=LO)."""
    import pyarrow as pa
    import pyarrow.dataset as ds
    path = Path(history_dir) / f"{H.history_stem(pair)}-{tf}-futures.feather"
    if not path.exists() and Path(history_dir) == H.HISTORY:
        path = H.HISTORY_PRE / path.name
    if not path.exists():
        return None
    typ = pa.timestamp("ms", tz="UTC")
    flt = (ds.field("date") < pa.scalar(hi, type=typ)) & (ds.field("date") >= pa.scalar(H.GRID_START, type=typ))
    df = ds.dataset(str(path), format="feather").to_table(columns=["date", *H.OHLC, "volume"], filter=flt).to_pandas()
    df["date"] = pd.to_datetime(df["date"], utc=True)
    return df.set_index("date").sort_index()


def _bars(history_dir: Path, pair: str, tf: str, hi: pd.Timestamp):
    from trader_engine.bars import aggregate_4h_to_1d
    h4 = _oku(history_dir, pair, "4h", hi)
    if h4 is None or len(h4) == 0:
        return None
    if tf == "4h":
        return h4, h4
    if tf == "1d":
        return aggregate_4h_to_1d(h4), h4
    trig = _oku(history_dir, pair, tf, hi)
    return None if trig is None else (trig, h4)


def islem_uret(history_dir: Path, pair: str, setup: str, tf: str, tag: str, hi: pd.Timestamp,
               entry_from: pd.Timestamp | None) -> dict[str, list[tuple[int, float]]] | None:
    """Bir (kurulum, tf, varyant, cift): {maliyet_anahtari: [(cikis_ns, r_net)]}. Simulator = arm_harness.simulate (ayni).
    entry_from: yalniz bu andan sonra GIRILEN islemler (ondan once giren pozisyon tasinmaz); cozulmemis islemler dusulur."""
    from trader_core import regime as R
    from trader_core import signals as S
    from trader_engine.bars import STARTUP_BARS_ARM
    from trader_engine.strategies.arms import find_arm
    got = _bars(history_dir, pair, tf, hi)
    if got is None or len(got[0]) < STARTUP_BARS_ARM[tf] + 100:
        return None
    trig, h4 = got
    if entry_from is not None and not (trig.index >= entry_from).any():
        return None
    var = next(v for v in H.variants(setup) if v["tag"] == tag)
    mod = find_arm(setup)
    sigd = {**H.BASE_PARAMS, **var["sig"]}
    params = S.SignalParams.from_mapping(sigd)
    reg4 = R.classify_series(h4[H.OHLC], S.SignalParams.from_mapping(H.BASE_PARAMS).regime_params())
    core = H.core_table(trig, reg4, params if getattr(mod, "CORE", False) else S.SignalParams.from_mapping(H.BASE_PARAMS))
    bars = H.Bars(trig, core["regime"].to_numpy(dtype=object), tf)
    with H.patched(mod, var["mod"]):
        rows = H.candidate_rows(setup, tf, pair, trig, h4, params, core, bars)
    if entry_from is not None:
        keep = trig.index >= entry_from
        rows = [r for r in rows if keep[r[0]]]
    out = {}
    for fm, sl in H.COSTS:
        tr = H.simulate(bars, rows, mod.EXIT_MODE, H.TAKER_FEE * fm, sl, params.trail_atr)
        out[f"f{fm:g}|s{sl:g}"] = [(int(t), float(r)) for t, r, _, _ in tr]
    return out


def uret_pencere(history_dir: Path, pairs: list[str], aday: tuple[str, ...], hi: pd.Timestamp,
                 entry_from: pd.Timestamp | None) -> tuple[dict, list[str]]:
    """-> ({oge: {maliyet: [(cikis_ns, r)]}}, atlanan_ciftler). Ciftler toplanir."""
    res: dict[str, dict[str, list]] = {}
    skipped: list[str] = []
    for item in aday:
        head, tag = item.split("|")
        setup, tf = head.split("@")
        acc: dict[str, list] = {f"f{fm:g}|s{sl:g}": [] for fm, sl in H.COSTS}
        for pair in pairs:
            r = islem_uret(history_dir, pair, setup, tf, tag, hi, entry_from)
            if r is None:
                if pair not in skipped:
                    skipped.append(pair)
                continue
            for k, v in r.items():
                acc[k].extend(v)
        res[item] = acc
    return res, skipped


# ----------------------------------------------------------------------------------------- olculer (sonuc gorulmeden sabit)
def gunluk(trades: list[tuple[int, float]], days: pd.DatetimeIndex) -> pd.Series:
    if not trades:
        return pd.Series(0.0, index=days)
    ts = pd.to_datetime([t for t, _ in trades], unit="ns", utc=True).floor("D")
    s = pd.Series([r for _, r in trades], index=ts).groupby(level=0).sum()
    return s.reindex(days, fill_value=0.0).astype(float)


def olc(daily: pd.Series, trades: list[tuple[int, float]]) -> dict:
    x = daily.to_numpy(float)
    n = len(x)
    sd = float(x.std(ddof=1)) if n > 1 else 0.0
    sr = float(x.mean() / sd) if sd > 0 else None
    cum = np.concatenate(([0.0], np.cumsum(x)))
    dd = float((np.maximum.accumulate(cum) - cum).max()) if n else 0.0
    rs = np.array([r for _, r in trades], float)
    return {"gun": n, "n_islem": int(len(rs)), "toplam_r": float(x.sum()), "ort_r_gun": float(x.mean()) if n else None,
            "sharpe_gun": sr, "sharpe_yillik": None if sr is None else sr * ANN, "max_dd_r": dd,
            "isabet": float((rs > 0).mean()) if len(rs) else None}


def dsr_of(daily: pd.Series, sr: float | None, n_trials: int) -> float | None:
    if sr is None:
        return None
    sk, ku = return_moments(daily.to_numpy(float))
    return float(deflated_sharpe(sr, len(daily), sk, ku, n_trials=int(n_trials)))


def dusus(pre: float | None, hold: float | None) -> float | None:
    """Holdout oncesine gore dusus orani = 1 - holdout/once (once > 0 degilse tanimsiz -> None)."""
    if pre is None or hold is None or not pre > 0:
        return None
    return float(1.0 - hold / pre)


def n_trials_toplam(pbo_ozet: Path) -> int:
    d = json.loads(Path(pbo_ozet).read_text(encoding="utf-8"))
    for a in d["aileler"]:
        if a.get("aile") == "TUM KUME":
            return int(a["n_yapilandirma"])
    raise Red("pbo_ozet.json icinde 'TUM KUME' ailesi yok (deneme sayisi bilinmiyor)")


def _set_series(per_item: dict, cost: str, days: pd.DatetimeIndex) -> tuple[pd.Series, list]:
    tot = pd.Series(0.0, index=days)
    trades: list = []
    for item in per_item:
        tr = per_item[item][cost]
        tot = tot + gunluk(tr, days)
        trades.extend(tr)
    return tot, trades


def hesapla(pre: dict, hold: dict, pre_days: pd.DatetimeIndex, hold_days: pd.DatetimeIndex, n_trials: int) -> dict:
    """Saf hesap: islem listelerinden tum olculer + gecme olcutu (oneri)."""
    costs = [f"f{fm:g}|s{sl:g}" for fm, sl in H.COSTS]
    kume = {}
    for c in costs:
        sh, th = _set_series(hold, c, hold_days)
        sp, tp = _set_series(pre, c, pre_days)
        mh, mp = olc(sh, th), olc(sp, tp)
        kume[c] = {"holdout": mh, "holdout_oncesi": mp, "dsr": dsr_of(sh, mh["sharpe_gun"], n_trials),
                   "dusus_orani_sharpe": dusus(mp["sharpe_gun"], mh["sharpe_gun"]),
                   "dusus_orani_ort_r_gun": dusus(mp["ort_r_gun"], mh["ort_r_gun"])}
    ogeler = {}
    for item in hold:
        ogeler[item] = {}
        for c in costs:
            dh, dp = gunluk(hold[item][c], hold_days), gunluk(pre[item][c], pre_days)
            ogeler[item][c] = {"holdout": olc(dh, hold[item][c]), "holdout_oncesi": olc(dp, pre[item][c])}
    p, st = kume[PRIMARY], kume[STRESS]
    sr = p["holdout"]["sharpe_gun"]
    olcut = {"H1_sharpe_gt_0": bool(sr is not None and sr > SHARPE_MIN),
             "H2_dsr_ge_0_95": bool(p["dsr"] is not None and p["dsr"] >= DSR_MIN),
             "H3_stres_toplam_r_gt_0": bool(st["holdout"]["toplam_r"] > 0)}
    return {"kume": kume, "ogeler": ogeler,
            "gecme_olcutu": {"tanim": "docs/ml/holdout-degerlendirme-spec.md bolum 4 (ONERI; kullanici onayi gerekir)",
                             "ana_maliyet": PRIMARY, "stres_maliyet": STRESS, "kontroller": olcut,
                             "sonuc_oneri": "GECTI" if all(olcut.values()) else "KALDI", "baglayici": False}}


# ----------------------------------------------------------------------------------------- orkestrasyon
def degerlendir(aday: tuple[str, ...], *, history_dir: Path, muhur_path: Path, out_dir: Path, pairs: list[str],
                pbo_ozet: Path, now: datetime | None = None) -> dict:
    out_dir = Path(out_dir)
    jp, mp = out_dir / f"degerlendirme_{slug(aday)}.json", out_dir / f"degerlendirme_{slug(aday)}.md"
    if jp.exists() or mp.exists():
        raise Red(f"cikti zaten var: {jp.name}; degerlendirme tek seferliktir")
    if Path(history_dir).resolve() == REAL_HISTORY.resolve() and Path(muhur_path).resolve() != MUHUR_PATH.resolve():
        raise Red("gercek tarihsel veri yalniz gercek muhur dosyasiyla kabul edilir")
    doc = kapi_1_2(muhur_path, aday)        # veri okumaz
    n_trials = n_trials_toplam(pbo_ozet)    # veri okumaz
    kapi_3(history_dir, doc)                # yalniz hash
    pre_days = pd.date_range(H.GRID_START, LO.floor("D") - pd.Timedelta(days=1), freq="D")
    hold_days = pd.date_range(LO.floor("D"), HI.floor("D") - pd.Timedelta(days=1), freq="D")
    pre, sk_pre = uret_pencere(history_dir, pairs, aday, LO, None)
    hold, sk_hold = uret_pencere(history_dir, pairs, aday, HI, LO)
    out = hesapla(pre, hold, pre_days, hold_days, n_trials)
    out.update({"surum": VERSION, "zaman": (now or datetime.now(timezone.utc)).strftime("%Y-%m-%dT%H:%M:%SZ"),
                "aday_kumesi": list(aday), "n_trials": n_trials, "muhur_birlesik_sha256": doc["birlesik_sha256"],
                "holdout": [str(hold_days[0].date()), str(hold_days[-1].date())],
                "holdout_oncesi": [str(pre_days[0].date()), str(pre_days[-1].date())],
                "ciftler": pairs, "atlanan_ciftler_oncesi": sk_pre, "atlanan_ciftler_holdout": sk_hold,
                "not": "R serisi = ogelerin cift ve oge toplami (esit agirlik); cikis gunune gore; holdout islemleri holdout baslangicindan sonra GIRILENLER"})
    out_dir.mkdir(parents=True, exist_ok=True)
    jp.write_text(json.dumps(out, indent=2, ensure_ascii=False, sort_keys=True) + "\n", encoding="utf-8")
    mp.write_text(ozet_md(out), encoding="utf-8")
    return out


def _f(x, nd=3):
    return "-" if x is None else f"{x:.{nd}f}"


def ozet_md(o: dict) -> str:
    L = [f"# Holdout degerlendirme: {', '.join(o['aday_kumesi'])}", "",
         f"Surum {o['surum']} | {o['zaman']} | holdout {o['holdout'][0]} -> {o['holdout'][1]} | deneme sayisi N = {o['n_trials']} | muhur {o['muhur_birlesik_sha256'][:12]}", "",
         "| Maliyet | donem | gun | islem | toplam R | Sharpe (gun) | Sharpe (yil) | max DD (R) | isabet | DSR | dusus (Sharpe) |", "|---|---|---|---|---|---|---|---|---|---|---|"]
    for c, v in o["kume"].items():
        for d, lab in (("holdout", "holdout"), ("holdout_oncesi", "oncesi")):
            m = v[d]
            ex = (_f(v["dsr"], 4), _f(v["dusus_orani_sharpe"], 3)) if d == "holdout" else ("", "")
            L.append(f"| {c} | {lab} | {m['gun']} | {m['n_islem']} | {_f(m['toplam_r'], 2)} | {_f(m['sharpe_gun'], 4)} | {_f(m['sharpe_yillik'], 2)} | {_f(m['max_dd_r'], 2)} | {_f(m['isabet'], 3)} | {ex[0]} | {ex[1]} |")
    g = o["gecme_olcutu"]
    L += ["", f"## Gecme olcutu (ONERI, baglayici degil; kullanici onayi gerekir): **{g['sonuc_oneri']}**", ""]
    L += [f"- {k}: {'gecti' if v else 'kaldi'}" for k, v in g["kontroller"].items()]
    L += ["", "Ana maliyet " + g["ana_maliyet"] + ", stres " + g["stres_maliyet"] + ". Ayrintilar: ayni adli .json."]
    return "\n".join(L) + "\n"


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(allow_abbrev=False)
    ap.add_argument("--aday-kumesi", required=True)
    ap.add_argument("--history-dir", default=str(REAL_HISTORY))
    ap.add_argument("--muhur", default=str(MUHUR_PATH))
    ap.add_argument("--out-dir", default=str(OUT_DIR))
    ap.add_argument("--pbo-ozet", default=str(PBO_OZET))
    ap.add_argument("--pairs", default="", help="virgullu; bos ise config/engine.paper.json pairs")
    a = ap.parse_args(argv)
    try:
        aday = parse_aday(a.aday_kumesi)
        pairs = [p for p in a.pairs.split(",") if p] or json.loads(CONFIG.read_text(encoding="utf-8"))["pairs"]
        o = degerlendir(aday, history_dir=Path(a.history_dir), muhur_path=Path(a.muhur), out_dir=Path(a.out_dir), pairs=pairs, pbo_ozet=Path(a.pbo_ozet))
    except Red as e:
        print(f"RED: {e}", file=sys.stderr)
        return 2
    print(f"degerlendirme yazildi; oneri: {o['gecme_olcutu']['sonuc_oneri']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
