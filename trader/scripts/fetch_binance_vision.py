#!/usr/bin/env python3
"""Binance public archive (data.binance.vision) -> freqtrade 2026.10 feather data.

Indirir (USDT-M vadeli): klines (15m 1h 4h 1d), markPriceKlines (1h), fundingRate.
Aylik zip'ler; aylik dosya henuz yayinlanmamissa gunluk zip'lere duser (klines/mark).
fundingRate icin gunluk arsiv yoktur; icinde bulunulan ayin funding verisi ay sonu
yayinlanana kadar eksiktir (backtest'te `futures_funding_rate` ile doldurulabilir).

Cikti (freqtrade 2026.10 adlandirmasi, --datadir user_data/data/binance):
  futures/BTC_USDT_USDT-1h-futures.feather        (date, open, high, low, close, volume)
  futures/BTC_USDT_USDT-1h-mark.feather           (ayni kolonlar)
  futures/BTC_USDT_USDT-1h-funding_rate.feather   (date, funding_rate)

Idempotent: ham zip'ler user_data/data/_vision_raw altinda onbelleklenir, var olan
dosyalar tekrar indirilmez. .CHECKSUM (sha256) dogrulanir. Yalniz data.binance.vision.

1m eklentisi (06 §5): `--tfs 1m` (ya da `--only-1m`) klines 1m (last) ve markPriceKlines 1m (mark) indirir:
  futures/BTC_USDT_USDT-1m-futures.feather, futures/BTC_USDT_USDT-1m-mark.feather
  (date, open, high, low, close, volume; compression="uncompressed": HistoricalSource memory_map ile okur).
Boyut: ~1,05 M satir x 6 sutun x 8 bayt ~ 50 MB / dosya / cift. `--end YYYY-MM` son ayi (dahil) sinirlar.

Kullanim: python scripts/fetch_binance_vision.py [--start 2024-11] [--end 2026-04] [--pairs BTC,ETH] [--workers 8]
          [--tfs 15m,1h,4h,1d,1m] [--only-1m]
"""
from __future__ import annotations

import argparse
import hashlib
import io
import json
import sys
import time
import urllib.error
import urllib.request
import zipfile
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
BASE_URL = "https://data.binance.vision/data/futures/um"
KLINE_TFS = ["15m", "1h", "4h", "1d"]
DEFAULT_TFS = "15m,1h,4h,1d"  # 1m yalniz acikca istenince (boyut)
MARK_TF = "1h"  # binance: mark_ohlcv_timeframe = funding_fee_timeframe = 1h (freqtrade 2026.10)
FUNDING_TF = "1h"
OHLCV = ["date", "open", "high", "low", "close", "volume"]


def load_pairs(config: Path) -> list[str]:
    return json.loads(config.read_text())["exchange"]["pair_whitelist"]


def vision_symbol(pair: str) -> str:  # BTC/USDT:USDT -> BTCUSDT
    return pair.split(":")[0].replace("/", "")


def file_stem(pair: str) -> str:  # BTC/USDT:USDT -> BTC_USDT_USDT
    return pair.replace("/", "_").replace(":", "_")


def http_get(url: str, retries: int = 5) -> bytes | None:
    """Bytes; None on 404. Retries other errors with backoff."""
    for attempt in range(retries):
        try:
            with urllib.request.urlopen(url, timeout=60) as r:
                return r.read()
        except urllib.error.HTTPError as e:
            if e.code == 404:
                return None
            err = e
        except Exception as e:  # noqa: BLE001
            err = e
        time.sleep(min(2**attempt, 20))
    raise RuntimeError(f"GET {url} failed: {err}")


def fetch_zip(url: str, dest: Path) -> str:
    """Download+verify one archive. Returns 'cached' | 'ok' | 'missing' | 'nochecksum'."""
    if dest.exists():
        return "cached"
    data = http_get(url)
    if data is None:
        return "missing"
    status = "ok"
    chk = http_get(url + ".CHECKSUM")
    if chk is None:
        status = "nochecksum"
    else:
        want = chk.split()[0].decode()
        got = hashlib.sha256(data).hexdigest()
        if want != got:
            raise RuntimeError(f"checksum mismatch {url}: {got} != {want}")
    dest.parent.mkdir(parents=True, exist_ok=True)
    tmp = dest.with_suffix(".part")
    tmp.write_bytes(data)
    tmp.rename(dest)
    return status


def months(start: date, end: date) -> list[str]:
    out, y, m = [], start.year, start.month
    while (y, m) <= (end.year, end.month):
        out.append(f"{y:04d}-{m:02d}")
        y, m = (y + 1, 1) if m == 12 else (y, m + 1)
    return out


def days_of(month: str, last: date) -> list[str]:
    y, m = map(int, month.split("-"))
    d = date(y, m, 1)
    out = []
    while d.month == m and d <= last:
        out.append(d.isoformat())
        d += timedelta(days=1)
    return out


def to_ts(s: pd.Series) -> pd.Series:
    s = pd.to_numeric(s)
    if s.max() > 1e14:  # microseconds
        s = s // 1000
    return pd.to_datetime(s, unit="ms", utc=True).dt.as_unit("ms")


def read_kline_zip(path: Path) -> pd.DataFrame:
    with zipfile.ZipFile(path) as z:
        raw = z.read(z.namelist()[0])
    df = pd.read_csv(io.BytesIO(raw), header=None)
    if not str(df.iloc[0, 0]).isdigit():  # header row
        df = df.iloc[1:]
    df = df.iloc[:, :6]
    df.columns = ["date", "open", "high", "low", "close", "volume"]
    df["date"] = to_ts(df["date"])
    return df.astype({c: "float64" for c in OHLCV[1:]})


def read_funding_zip(path: Path) -> pd.DataFrame:
    with zipfile.ZipFile(path) as z:
        raw = z.read(z.namelist()[0])
    df = pd.read_csv(io.BytesIO(raw))  # calc_time,funding_interval_hours,last_funding_rate
    out = pd.DataFrame(
        {
            "date": to_ts(df["calc_time"]).dt.round("h"),  # 08:00:00.005 -> 08:00
            "funding_rate": df["last_funding_rate"].astype("float64"),
        }
    )
    return out


def build(files: list[Path], reader) -> pd.DataFrame:
    df = pd.concat([reader(f) for f in files], ignore_index=True)
    return df.drop_duplicates("date").sort_values("date").reset_index(drop=True)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawTextHelpFormatter)
    ap.add_argument("--config", type=Path, default=ROOT / "config/base.json")
    ap.add_argument("--start", default="2024-11", help="YYYY-MM")
    ap.add_argument("--data-dir", type=Path, default=ROOT / "user_data/data")
    ap.add_argument("--pairs", help="virgullu baz kisaltmalar (BTC,ETH); varsayilan: config")
    ap.add_argument("--workers", type=int, default=8)
    ap.add_argument("--end", default=None, help="YYYY-MM (dahil); varsayilan bugun")
    ap.add_argument("--tfs", default=DEFAULT_TFS, help="virgullu: 15m,1h,4h,1d,1m (1m last+mark ekler)")
    ap.add_argument("--only-1m", action="store_true", help="yalniz 1m last + 1m mark")
    args = ap.parse_args()

    pairs = load_pairs(args.config)
    if args.pairs:
        keep = {p.strip().upper() for p in args.pairs.split(",")}
        pairs = [p for p in pairs if p.split("/")[0] in keep]
    today = datetime.now(timezone.utc).date()
    start = date(int(args.start[:4]), int(args.start[5:7]), 1)
    end_d = today if not args.end else date(int(args.end[:4]), int(args.end[5:7]), 1)
    mlist = months(start, end_d)
    tfs = [t.strip() for t in args.tfs.split(",") if t.strip()]
    if args.only_1m:
        tfs = ["1m"]
    for t in tfs:
        if t not in ("1m", *KLINE_TFS):
            ap.error(f"gecersiz tf: {t}")
    raw_dir = args.data_dir / "_vision_raw"
    out_dir = args.data_dir / "binance" / "futures"
    out_dir.mkdir(parents=True, exist_ok=True)

    # datasets: (kind, pair, tf)
    datasets = [("klines", p, tf) for p in pairs for tf in tfs]
    if not args.only_1m:
        datasets += [("markPriceKlines", p, MARK_TF) for p in pairs]
        datasets += [("fundingRate", p, None) for p in pairs]
    if "1m" in tfs:
        datasets += [("markPriceKlines", p, "1m") for p in pairs]

    # 1) indirme gorevleri: (url, dest)
    def monthly_url(kind, sym, tf, mo):
        sub = f"{sym}/{tf}/{sym}-{tf}-{mo}" if tf else f"{sym}/{sym}-fundingRate-{mo}"
        return f"{BASE_URL}/monthly/{kind}/{sub}.zip", raw_dir / "monthly" / kind / f"{Path(sub).name}.zip"

    def daily_url(kind, sym, tf, day):
        sub = f"{sym}/{tf}/{sym}-{tf}-{day}"
        return f"{BASE_URL}/daily/{kind}/{sub}.zip", raw_dir / "daily" / kind / f"{Path(sub).name}.zip"

    def job(kind, pair, tf, mo):
        sym = vision_symbol(pair)
        url, dest = monthly_url(kind, sym, tf, mo)
        st = fetch_zip(url, dest)
        if st != "missing":
            return [st]
        if kind == "fundingRate":
            return ["missing"]
        # aylik yok -> gunluk (bugunun dosyasi yayinlanmamis olur: 404 normal)
        res = []
        for day in days_of(mo, today):
            u, d = daily_url(kind, sym, tf, day)
            res.append(fetch_zip(u, d))
        return res

    tasks = [(k, p, tf, mo) for (k, p, tf) in datasets for mo in mlist]
    counts: dict[str, int] = {}
    with ThreadPoolExecutor(args.workers) as ex:
        futs = {ex.submit(job, *t): t for t in tasks}
        for i, f in enumerate(as_completed(futs), 1):
            for st in f.result():
                counts[st] = counts.get(st, 0) + 1
            if i % 200 == 0:
                print(f"  {i}/{len(tasks)} gorev", file=sys.stderr)
    print("indirme:", counts)

    # 2) feather uretimi
    summary = []
    for kind, pair, tf in datasets:
        sym, stem = vision_symbol(pair), file_stem(pair)
        if kind == "fundingRate":
            files = sorted((raw_dir / "monthly" / kind).glob(f"{sym}-fundingRate-*.zip"))
            reader, name = read_funding_zip, f"{stem}-{FUNDING_TF}-funding_rate.feather"
        else:
            files = sorted((raw_dir / "monthly" / kind).glob(f"{sym}-{tf}-*.zip")) + sorted(
                (raw_dir / "daily" / kind).glob(f"{sym}-{tf}-*.zip")
            )
            reader = read_kline_zip
            suffix = "futures" if kind == "klines" else "mark"
            name = f"{stem}-{tf}-{suffix}.feather"
        if not files:
            print(f"UYARI: veri yok {pair} {kind} {tf}", file=sys.stderr)
            continue
        df = build(files, reader)
        if kind != "fundingRate":
            # arsivde nadiren eksik gun olur (ornegin mark 2026-06-29): gunluk zip ile doldur
            step = pd.Timedelta(tf.replace("m", "min")) if tf.endswith("m") else pd.Timedelta(tf)
            gaps = df["date"].diff() > step
            fetched = False
            for i in df.index[gaps]:
                d0, d1 = df["date"][i - 1].date(), df["date"][i].date()
                d = d0
                while d <= d1:
                    u, dest = daily_url(kind, sym, tf, d.isoformat())
                    fetched |= fetch_zip(u, dest) in ("ok", "nochecksum")
                    d += timedelta(days=1)
            if fetched:
                files = sorted((raw_dir / "monthly" / kind).glob(f"{sym}-{tf}-*.zip")) + sorted(
                    (raw_dir / "daily" / kind).glob(f"{sym}-{tf}-*.zip")
                )
                df = build(files, reader)
        if tf == "1m":
            df.to_feather(out_dir / name, compression="uncompressed")
        else:
            df.to_feather(out_dir / name, compression="lz4", compression_level=9)
        summary.append((name, df["date"].iloc[0], df["date"].iloc[-1], len(df)))
    for name, a, b, n in summary:
        print(f"{name:42s} {a:%Y-%m-%d %H:%M} -> {b:%Y-%m-%d %H:%M}  {n:>7d}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
