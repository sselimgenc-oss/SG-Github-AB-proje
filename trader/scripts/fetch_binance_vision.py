#!/usr/bin/env python3
"""Binance public archive (data.binance.vision) -> feather history files (`var/history`).  [ML-G3 gecmis indirme araci]

Indirir (USDT-M vadeli): klines (15m 1h 4h 1d [1m]), markPriceKlines (1h [1m]), fundingRate.
Aylik zip'ler; aylik dosya yayinlanmamissa gunluk zip'lere duser (klines/mark). fundingRate icin gunluk arsiv yoktur.

Cikti (dosya adlandirmasi bizim sozlesmemizdir; --history-dir, varsayilan var/history; yalniz pyarrow ile okunur):
  BTC_USDT_USDT-1h-futures.feather        (date, open, high, low, close, volume)   date = timestamp[ms, UTC]
  BTC_USDT_USDT-1h-mark.feather           (ayni kolonlar)
  BTC_USDT_USDT-1h-funding_rate.feather   (date, funding_rate)
  BTC_USDT_USDT-1m-futures.feather / -1m-mark.feather  (1m: compression="uncompressed"; HistoricalSource memory_map okur)

KILITLI DONEM (HOLDOUT 2026-05-01 -> 2026-11-01, trader_engine.holdout ile ayni):
  * Bu arac kilitli doneme ait HICBIR arsiv dosyasini istemez/indirmez (periyodu >= 2026-05-01 olan URL uretilmez;
    --end en gec 2026-04'e kirpilir; guard ayrica HoldoutViolation ile reddeder).
  * Mevcut feather dosyasi kilitli donemi kapsiyorsa: satirlar IPC batch seviyesinde okunur; kilitli doneme ait satirlar
    degistirilmeden (deger bazinda ayni) oldugu gibi geri yazilir, yeni satirlar yalniz kilitli donemin ONCESINE eklenir.
    Dosya sozlesmesi tek dosya/cift/tf oldugu icin eklenti (ornegin 2021-01 -> 2024-10) dosyanin basina girer: dosya
    atomik (tmp + rename) yeniden yazilir. Eklenecek bir sey yoksa dosyaya HIC dokunulmaz (bayt/mtime ayni).
    Tamamen kilitli donemde kalan dosyaya, o dataset icin yeni satir yoksa dokunulmaz.

Guvenlik: her zip icin .CHECKSUM (sha256) dogrulanir; uyusmazlikta zip kaydedilmez (exit 2). --require-checksum eksik
.CHECKSUM'i da reddeder (varsayilan: uyari + raporda "nochecksum"). Onbellekteki zip yanindaki .zip.CHECKSUM ile
tekrar dogrulanir; bozuksa silinip yeniden indirilir.

Yeniden baslatilabilir/idempotent: ham zip'ler --raw-dir altinda onbelleklenir (atomik .part+rename); var olan dosyalar
tekrar indirilmez; degisiklik yoksa feather'a dokunulmaz. --rate istek/sn sinirlar. Kosu sonunda bosluk raporu:
--report (varsayilan var/gap_report.json + .md): cift/kind/tf basina eksik aylar, eksik gunler, kismi gunler.

Kullanim:
  python scripts/fetch_binance_vision.py --start 2021-01 --tfs all [--end 2026-04] [--pairs BTC,ETH] [--workers 4]
         [--rate 4] [--require-checksum] [--dry-run] [--only-1m]
  --tfs: virgullu 15m,1h,4h,1d,1m ya da `all`. --only-1m: yalniz 1m last + 1m mark.
"""
from __future__ import annotations

import argparse
import fcntl
import hashlib
import io
import json
import os
import re
import sys
import threading
import time
import urllib.error
import urllib.request
import zipfile
from collections import Counter
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
BASE_URL = "https://data.binance.vision/data/futures/um"
KLINE_TFS = ["15m", "1h", "4h", "1d"]
DEFAULT_TFS = "15m,1h,4h,1d"  # 1m yalniz acikca istenince (boyut)
ALL_TFS = "15m,1h,4h,1d,1m"
MARK_TF = "1h"  # binance: mark_ohlcv_timeframe = funding_fee_timeframe = 1h
FUNDING_TF = "1h"
OHLCV = ["date", "open", "high", "low", "close", "volume"]
# trader_engine.holdout.HOLDOUT ile ayni (testle sabitlenir); bu arac yalniz < HOLDOUT_START ile ilgilenir.
HOLDOUT_START = datetime(2026, 5, 1, tzinfo=timezone.utc)
HOLDOUT_END = datetime(2026, 11, 1, tzinfo=timezone.utc)
HOLDOUT_START_MS = int(HOLDOUT_START.timestamp() * 1000)
LAST_ALLOWED_MONTH = "2026-04"
MAX_GAP_FILL_DAYS = 7


class ChecksumError(RuntimeError):
    pass


class HoldoutViolation(RuntimeError):
    pass


# ------------------------------------------------------------------------------------------- yardimcilar
def load_pairs(config: Path) -> list[str]:
    """engine.base.json `pairs` ("BTC/USDT") -> dosya sozlesmesi icin "BTC/USDT:USDT"."""
    return [p if ":" in p else f"{p}:USDT" for p in json.loads(config.read_text())["pairs"]]


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


class RateLimiter:
    """Tum is parcaciklari icin ortak asgari istek araligi (saniyede en fazla `rate` istek). rate<=0: sinirsiz."""

    def __init__(self, rate: float, clock=time.monotonic, sleep=time.sleep) -> None:
        self.interval = 1.0 / rate if rate and rate > 0 else 0.0
        self._clock, self._sleep = clock, sleep
        self._lock = threading.Lock()
        self._next = 0.0

    def acquire(self) -> None:
        if not self.interval:
            return
        with self._lock:
            now = self._clock()
            wait = self._next - now
            self._next = max(now, self._next) + self.interval
        if wait > 0:
            self._sleep(wait)


LIMITER = RateLimiter(0)


def _get(url: str) -> bytes | None:
    LIMITER.acquire()
    return http_get(url)  # global arama: testlerde monkeypatch edilebilir


_PERIOD_RE = re.compile(r"(\d{4})-(\d{2})(?:-(\d{2}))?(?:\.zip)?(?:\.CHECKSUM)?$")


def period_start(name: str) -> date | None:
    """'.../BTCUSDT-1h-2021-01.zip[.CHECKSUM]' -> date(2021,1,1); gunluk -> o gun."""
    m = _PERIOD_RE.search(name)
    if not m:
        return None
    return date(int(m[1]), int(m[2]), int(m[3]) if m[3] else 1)


def guard_not_holdout(url_or_name: str) -> None:
    d = period_start(url_or_name)
    if d is None or datetime(d.year, d.month, d.day, tzinfo=timezone.utc) >= HOLDOUT_START:
        raise HoldoutViolation(f"kilitli donem / periyodu belirsiz arsiv istegi reddedildi: {url_or_name}")


def _sidecar(dest: Path) -> Path:
    return dest.with_name(dest.name + ".CHECKSUM")


def _parse_checksum(raw: bytes) -> str:
    tok = raw.split()[0].decode("ascii", "replace").lower() if raw.split() else ""
    if not re.fullmatch(r"[0-9a-f]{64}", tok):
        raise ChecksumError(f"bozuk .CHECKSUM icerigi: {raw[:80]!r}")
    return tok


def fetch_zip(url: str, dest: Path, require_checksum: bool = False) -> str:
    """Download+verify one archive. Returns 'cached' | 'ok' | 'missing' | 'nochecksum' | 'redownloaded'.

    Raises ChecksumError (zip kaydedilmez), HoldoutViolation."""
    guard_not_holdout(url)
    redo = False
    if dest.exists():
        sc = _sidecar(dest)
        if not sc.exists():
            return "cached"
        want = sc.read_text().split()[0]
        if hashlib.sha256(dest.read_bytes()).hexdigest() == want:
            return "cached"
        dest.unlink()  # onbellek bozulmus: yeniden indir
        sc.unlink()
        redo = True
    data = _get(url)
    if data is None:
        return "missing"
    chk = _get(url + ".CHECKSUM")
    status = "ok"
    want = None
    if chk is None:
        if require_checksum:
            raise ChecksumError(f".CHECKSUM yok (--require-checksum): {url}")
        status = "nochecksum"
    else:
        want = _parse_checksum(chk)
        got = hashlib.sha256(data).hexdigest()
        if want != got:
            raise ChecksumError(f"checksum mismatch {url}: {got} != {want}")
    dest.parent.mkdir(parents=True, exist_ok=True)
    tmp = dest.with_suffix(".part")
    tmp.write_bytes(data)
    if want:
        _sidecar(dest).write_text(f"{want}  {dest.name}\n")
    tmp.rename(dest)
    return "redownloaded" if redo and status == "ok" else status


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


def build(files: list[Path], reader, errors: list[str] | None = None) -> pd.DataFrame:
    parts = []
    for f in files:
        try:
            parts.append(reader(f))
        except (zipfile.BadZipFile, ValueError, KeyError, IndexError, pd.errors.ParserError) as e:
            if errors is not None:
                errors.append(f"{f.name}: okunamadi ({type(e).__name__})")
    cols = ["date", "funding_rate"] if reader is read_funding_zip else OHLCV
    if not parts:
        return pd.DataFrame({c: pd.Series(dtype="datetime64[ms, UTC]" if c == "date" else "float64") for c in cols})
    df = pd.concat(parts, ignore_index=True)
    return df.drop_duplicates("date").sort_values("date").reset_index(drop=True)


def tf_step(tf: str) -> pd.Timedelta:
    if tf.endswith("m"):
        return pd.Timedelta(minutes=int(tf[:-1]))
    if tf.endswith("h"):
        return pd.Timedelta(hours=int(tf[:-1]))
    if tf.endswith("d"):
        return pd.Timedelta(days=int(tf[:-1]))          # 'd' birimi pandas'ta kullanimdan kalkiyor
    return pd.Timedelta(tf)


# ------------------------------------------------------------------------------------------- birlestirme
def _count_before(col, h_ms: int) -> int:
    import pyarrow as pa
    import pyarrow.compute as pc
    unit = col.type.unit
    h = {"s": h_ms // 1000, "ms": h_ms, "us": h_ms * 1000, "ns": h_ms * 1_000_000}[unit]
    return int(pc.sum(pc.less(col.cast(pa.int64()), h)).as_py() or 0)


def _write(table, path: Path, tf: str | None) -> None:
    import pyarrow.feather as pf
    tmp = path.with_name(path.name + ".part")
    if tf == "1m":
        pf.write_feather(table, str(tmp), compression="uncompressed")
    else:
        pf.write_feather(table, str(tmp), compression="lz4", compression_level=9)
    os.replace(tmp, path)


def merge_into_history(path: Path, new_df: pd.DataFrame, tf: str | None, dry_run: bool = False) -> tuple[str, pd.DataFrame]:
    """Yeni satirlari (zaten < HOLDOUT, ayri tekil) mevcut dosyayla birlestirir. Doner: (durum, birlesik <HOLDOUT df).

    durum: created | written | unchanged | empty | would_write. Mevcut satirlar kazanir (dedup keep=first).
    Kilitli doneme ait mevcut satirlar degistirilmeden geri yazilir; degisiklik yoksa dosyaya dokunulmaz."""
    import pyarrow as pa
    new_df = new_df[new_df["date"] < pd.Timestamp(HOLDOUT_START)]
    if not path.exists():
        if new_df.empty:
            return "empty", new_df
        if dry_run:
            return "would_write", new_df
        _write(pa.Table.from_pandas(new_df.reset_index(drop=True), preserve_index=False), path, tf)
        return "created", new_df
    with pa.OSFile(str(path)) as f:
        r = pa.ipc.open_file(f)
        schema = r.schema
        pre_parts, tail_parts, in_tail = [], [], False
        for i in range(r.num_record_batches):
            b = r.get_batch(i)
            if in_tail:
                tail_parts.append(b)
                continue
            n = _count_before(b.column(0), HOLDOUT_START_MS)
            if n == b.num_rows:
                pre_parts.append(b)
            elif n == 0:
                in_tail = True
                tail_parts.append(b)
            else:
                pre_parts.append(b.slice(0, n))
                tail_parts.append(b.slice(n))
                in_tail = True
        pre_df = pa.Table.from_batches(pre_parts, schema).to_pandas()
        if new_df.empty:
            merged = pre_df
        elif pre_df.empty:
            merged = new_df
        else:
            merged = pd.concat([pre_df, new_df], ignore_index=True)
        merged = merged.drop_duplicates("date", keep="first").sort_values("date").reset_index(drop=True)
        if len(merged) == len(pre_df):
            return "unchanged", merged
        if dry_run:
            return "would_write", merged
        parts = [pa.Table.from_pandas(merged, schema=schema, preserve_index=False)]
        if tail_parts:
            parts.append(pa.Table.from_batches(tail_parts, schema))
        final = pa.concat_tables(parts)
        _write(final, path, tf)
    return "written", merged


# ------------------------------------------------------------------------------------------- bosluk raporu
def _ranges(days: list[date]) -> list[str]:
    out, i = [], 0
    while i < len(days):
        j = i
        while j + 1 < len(days) and days[j + 1] - days[j] == timedelta(days=1):
            j += 1
        out.append(days[i].isoformat() if i == j else f"{days[i].isoformat()}..{days[j].isoformat()}")
        i = j + 1
    return out


def gap_stats(df: pd.DataFrame, tf: str | None, first_day: date, last_day: date) -> dict:
    """[first_day, last_day] (dahil) icin eksik ay/gun/kismi gun. tf None: funding (yalniz gun varligi)."""
    all_days = pd.date_range(first_day, last_day, freq="D", tz="UTC")
    if df.empty:
        counts = pd.Series(0, index=all_days)
    else:
        c = df["date"].dt.floor("D").value_counts()
        counts = c.reindex(all_days, fill_value=0)
    exp = 1 if tf is None else int(pd.Timedelta("1D") / tf_step(tf))
    missing = [d.date() for d in all_days[counts.values == 0]]
    partial = []
    missing_bars = 0
    if tf is not None:
        for d, n in counts.items():
            if 0 < n < exp:
                partial.append((d.date().isoformat(), int(exp - n)))
                missing_bars += int(exp - n)
        missing_bars += len(missing) * exp
    miss_set = set(missing)
    full_months = []
    for mo in months(first_day, last_day):
        ds = [date.fromisoformat(x) for x in days_of(mo, last_day) if date.fromisoformat(x) >= first_day]
        if ds and all(d in miss_set for d in ds):
            full_months.append(mo)
    return {
        "missing_months": full_months,
        "missing_day_ranges": _ranges(missing),
        "missing_days": len(missing),
        "partial_days": len(partial),
        "partial_day_examples": partial[:20],
        "missing_bars": missing_bars,
    }


def write_report(path: Path, report: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(report, indent=1, ensure_ascii=False) + "\n")
    lines = [
        "# Gecmis veri bosluk raporu",
        f"Pencere: {report['window']['start']} -> {report['window']['end']} (dahil); kilitli donem (>= {HOLDOUT_START:%Y-%m-%d}) istenmedi/yazilmadi.",
        f"Indirme: {report['download_counts']}",
        "",
        "| dataset | ilk | son | satir | eksik ay | eksik gun | kismi gun | eksik mum | feather |",
        "|---|---|---|---:|---|---:|---:|---:|---|",
    ]
    for d in report["datasets"]:
        lines.append(
            f"| {d['pair']} {d['kind']} {d['tf'] or ''} | {d['first'] or '-'} | {d['last'] or '-'} | {d['rows']} | "
            f"{','.join(d['missing_months']) or '-'} | {d['missing_days']} | {d['partial_days']} | {d['missing_bars']} | {d['feather']} |"
        )
    for d in report["datasets"]:
        if d["missing_day_ranges"] or d["errors"] or d["nochecksum"]:
            lines.append(f"\n**{d['pair']} {d['kind']} {d['tf'] or ''}**")
            if d["missing_day_ranges"]:
                lines.append("- eksik gunler: " + ", ".join(d["missing_day_ranges"][:40]) + (" ..." if len(d["missing_day_ranges"]) > 40 else ""))
            if d["nochecksum"]:
                lines.append(f"- .CHECKSUM'siz zip: {d['nochecksum']}")
            for e in d["errors"][:10]:
                lines.append(f"- hata: {e}")
    path.with_suffix(".md").write_text("\n".join(lines) + "\n")


# ------------------------------------------------------------------------------------------- ana akis
def _files_for(raw_dir: Path, kind: str, sym: str, tf: str | None, lo: date, hi: date) -> list[Path]:
    """Onbellekteki zip'ler; periyodu [lo, hi] disinda kalan (ozellikle kilitli donem) HIC okunmaz."""
    pat = f"{sym}-fundingRate-*.zip" if kind == "fundingRate" else f"{sym}-{tf}-*.zip"
    out = []
    for sub in ("monthly", "daily"):
        for f in sorted((raw_dir / sub / kind).glob(pat)):
            d = period_start(f.name)
            if d is not None and lo <= d <= hi and datetime(d.year, d.month, d.day, tzinfo=timezone.utc) < HOLDOUT_START:
                out.append(f)
    return out


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawTextHelpFormatter)
    ap.add_argument("--config", type=Path, default=ROOT / "config/engine.base.json")
    ap.add_argument("--start", default="2024-11", help="YYYY-MM (ML-G3 icin 2021-01)")
    ap.add_argument("--history-dir", type=Path, default=ROOT / "var/history", help="feather cikti dizini")
    ap.add_argument("--raw-dir", type=Path, default=ROOT / "var/vision_raw", help="ham zip onbellegi")
    ap.add_argument("--pairs", help="virgullu baz kisaltmalar (BTC,ETH); varsayilan: config")
    ap.add_argument("--workers", type=int, default=8)
    ap.add_argument("--rate", type=float, default=0.0, help="saniyede en fazla istek (0: sinirsiz; sunucuda 4 onerilir)")
    ap.add_argument("--end", default=None, help="YYYY-MM (dahil); en gec 2026-04 (kilitli donem oncesi)")
    ap.add_argument("--tfs", default=DEFAULT_TFS, help="virgullu: 15m,1h,4h,1d,1m ya da all (1m last+mark ekler)")
    ap.add_argument("--only-1m", action="store_true", help="yalniz 1m last + 1m mark")
    ap.add_argument("--require-checksum", action="store_true", help=".CHECKSUM eksikse zip'i reddet")
    ap.add_argument("--report", type=Path, default=ROOT / "var/gap_report.json", help="bosluk raporu (.json; yanina .md)")
    ap.add_argument("--dry-run", action="store_true", help="ag yok, yazma yok: yalniz plan")
    args = ap.parse_args(argv)

    global LIMITER
    LIMITER = RateLimiter(args.rate)
    pairs = load_pairs(args.config)
    if args.pairs:
        keep = {p.strip().upper() for p in args.pairs.split(",")}
        pairs = [p for p in pairs if p.split("/")[0] in keep]
    today = datetime.now(timezone.utc).date()
    start = date(int(args.start[:4]), int(args.start[5:7]), 1)
    last_ok = date(int(LAST_ALLOWED_MONTH[:4]), int(LAST_ALLOWED_MONTH[5:7]), 1)
    end_req = today if not args.end else date(int(args.end[:4]), int(args.end[5:7]), 1)
    end_d = min(end_req, last_ok)
    if end_d < end_req:
        print(f"NOT: --end {end_req:%Y-%m} kilitli doneme giriyor; {end_d:%Y-%m}'e kirpildi.", file=sys.stderr)
    mlist = months(start, end_d)
    last_day = (date(end_d.year + (end_d.month == 12), end_d.month % 12 + 1, 1)) - timedelta(days=1)
    daily_last = min(today, last_day)
    tfs = [t.strip() for t in (ALL_TFS if args.tfs == "all" else args.tfs).split(",") if t.strip()]
    if args.only_1m:
        tfs = ["1m"]
    for t in tfs:
        if t not in ("1m", *KLINE_TFS):
            ap.error(f"gecersiz tf: {t}")
    raw_dir, out_dir = args.raw_dir, args.history_dir

    # datasets: (kind, pair, tf)
    datasets = [("klines", p, tf) for p in pairs for tf in tfs]
    if not args.only_1m:
        datasets += [("markPriceKlines", p, MARK_TF) for p in pairs]
        datasets += [("fundingRate", p, None) for p in pairs]
    if "1m" in tfs:
        datasets += [("markPriceKlines", p, "1m") for p in pairs]

    def monthly_url(kind, sym, tf, mo):
        sub = f"{sym}/{tf}/{sym}-{tf}-{mo}" if tf else f"{sym}/{sym}-fundingRate-{mo}"
        return f"{BASE_URL}/monthly/{kind}/{sub}.zip", raw_dir / "monthly" / kind / f"{Path(sub).name}.zip"

    def daily_url(kind, sym, tf, day):
        sub = f"{sym}/{tf}/{sym}-{tf}-{day}"
        return f"{BASE_URL}/daily/{kind}/{sub}.zip", raw_dir / "daily" / kind / f"{Path(sub).name}.zip"

    def job(kind, pair, tf, mo):
        sym = vision_symbol(pair)
        url, dest = monthly_url(kind, sym, tf, mo)
        st = fetch_zip(url, dest, args.require_checksum)
        if st != "missing":
            return [st]
        if kind == "fundingRate":
            return ["missing"]
        res = []  # aylik yok -> gunluk (bugunun dosyasi yayinlanmamis olur: 404 normal)
        for day in days_of(mo, daily_last):
            u, d = daily_url(kind, sym, tf, day)
            res.append(fetch_zip(u, d, args.require_checksum))
        return res

    tasks = [(k, p, tf, mo) for (k, p, tf) in datasets for mo in mlist]
    print(f"plan: {len(datasets)} dataset, {len(mlist)} ay ({mlist[0]}..{mlist[-1]}), {len(tasks)} aylik gorev; "
          f"kilitli donem >= {HOLDOUT_START:%Y-%m-%d} istenmez")
    if args.dry_run:
        return 0

    raw_dir.mkdir(parents=True, exist_ok=True)
    out_dir.mkdir(parents=True, exist_ok=True)
    lock = open(raw_dir / ".fetch.lock", "w")  # noqa: SIM115 - kosu boyunca acik
    try:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError:
        print("HATA: baska bir indirme kosusu calisiyor (.fetch.lock)", file=sys.stderr)
        return 3

    counts: Counter = Counter()
    ds_err: dict[tuple, list[str]] = {}
    ds_nochk: Counter = Counter()
    exit_code = 0

    def run_task(t):
        try:
            return t, job(*t), None
        except ChecksumError as e:
            return t, ["checksum_mismatch"], str(e)
        except HoldoutViolation:
            raise
        except Exception as e:  # noqa: BLE001 - ag hatasi: tekrar kosuda kaldigi yerden devam
            return t, ["error"], f"{type(e).__name__}: {e}"

    with ThreadPoolExecutor(args.workers) as ex:
        futs = [ex.submit(run_task, t) for t in tasks]
        for i, f in enumerate(as_completed(futs), 1):
            (kind, pair, tf, mo), sts, err = f.result()
            for st in sts:
                counts[st] += 1
                if st == "nochecksum":
                    ds_nochk[(kind, pair, tf)] += 1
            if err:
                ds_err.setdefault((kind, pair, tf), []).append(f"{mo}: {err}")
                exit_code = max(exit_code, 2 if "checksum" in sts[0] else 1)
            if i % 200 == 0:
                print(f"  {i}/{len(tasks)} gorev", file=sys.stderr)
    print("indirme:", dict(counts))

    # 2) feather uretimi + birlestirme
    summary, rep_ds = [], []
    lo_ts = pd.Timestamp(start, tz="UTC")
    for kind, pair, tf in datasets:
        sym, stem = vision_symbol(pair), file_stem(pair)
        key = (kind, pair, tf)
        errs = list(ds_err.get(key, []))
        if kind == "fundingRate":
            reader, name = read_funding_zip, f"{stem}-{FUNDING_TF}-funding_rate.feather"
        else:
            reader = read_kline_zip
            name = f"{stem}-{tf}-{'futures' if kind == 'klines' else 'mark'}.feather"
        files = _files_for(raw_dir, kind, sym, tf, start, last_day)
        new = build(files, reader, errs)
        new = new[(new["date"] >= lo_ts) & (new["date"] < pd.Timestamp(HOLDOUT_START))]
        path = out_dir / name
        try:
            status, merged = merge_into_history(path, new, tf)
            if kind != "fundingRate" and tf and not merged.empty:
                # arsivde nadiren eksik gun olur: kucuk bosluklari gunluk zip ile doldur (yalniz < kilitli donem)
                m_pre = merged[(merged["date"] >= lo_ts)]
                step = tf_step(tf)
                gaps = m_pre["date"].diff() > step
                fetched = False
                for i in m_pre.index[gaps]:
                    pos = m_pre.index.get_loc(i)
                    d0, d1 = m_pre["date"].iloc[pos - 1].date(), m_pre["date"].iloc[pos].date()
                    if (d1 - d0).days > MAX_GAP_FILL_DAYS:
                        continue
                    d = d0
                    while d <= d1:
                        if d <= daily_last and d <= last_day:
                            u, dest = daily_url(kind, sym, tf, d.isoformat())
                            try:
                                fetched |= fetch_zip(u, dest, args.require_checksum) in ("ok", "nochecksum")
                            except ChecksumError as e:
                                errs.append(f"{d}: {e}")
                                exit_code = max(exit_code, 2)
                        d += timedelta(days=1)
                if fetched:
                    files = _files_for(raw_dir, kind, sym, tf, start, last_day)
                    new = build(files, reader, errs)
                    new = new[(new["date"] >= lo_ts) & (new["date"] < pd.Timestamp(HOLDOUT_START))]
                    status, merged = merge_into_history(path, new, tf)
        except Exception as e:  # noqa: BLE001 - bozuk mevcut dosya vb.: ustune yazma, raporla
            errs.append(f"merge: {type(e).__name__}: {e}")
            exit_code = max(exit_code, 1)
            status, merged = "error", new
        win = merged[merged["date"] >= lo_ts] if not merged.empty else merged
        stats = gap_stats(win, tf if kind != "fundingRate" else None, start, last_day)
        rep_ds.append({
            "pair": pair, "kind": kind, "tf": tf, "feather": f"{name}:{status}",
            "first": f"{win['date'].iloc[0]:%Y-%m-%d %H:%M}" if len(win) else None,
            "last": f"{win['date'].iloc[-1]:%Y-%m-%d %H:%M}" if len(win) else None,
            "rows": int(len(win)), "errors": errs, "nochecksum": int(ds_nochk.get(key, 0)), **stats,
        })
        if len(win):
            summary.append((name, status, win["date"].iloc[0], win["date"].iloc[-1], len(win)))
        else:
            print(f"UYARI: veri yok {pair} {kind} {tf}", file=sys.stderr)
    for name, status, a, b, n in summary:
        print(f"{name:42s} {status:9s} {a:%Y-%m-%d %H:%M} -> {b:%Y-%m-%d %H:%M}  {n:>8d}")

    report = {
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "window": {"start": start.isoformat(), "end": last_day.isoformat()},
        "holdout_not_requested_not_written": [HOLDOUT_START.isoformat(), HOLDOUT_END.isoformat()],
        "download_counts": dict(counts),
        "datasets": rep_ds,
        "totals": {
            "missing_bars": sum(d["missing_bars"] for d in rep_ds),
            "datasets_with_gaps": sum(1 for d in rep_ds if d["missing_days"] or d["partial_days"]),
            "errors": sum(len(d["errors"]) for d in rep_ds),
        },
    }
    write_report(args.report, report)
    print(f"bosluk raporu: {args.report} (+ .md); eksik mum toplami {report['totals']['missing_bars']}, hata {report['totals']['errors']}")
    return exit_code


if __name__ == "__main__":
    sys.exit(main())
