"""ML-G3 gecmis indirme araci (scripts/fetch_binance_vision.py): AGSIZ, yerel sentetik zip fixture'lari (tests/fixtures/vision)."""
from __future__ import annotations

import hashlib
import importlib
import json
import os
import sys
import urllib.request
import zipfile
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd
import pyarrow as pa
import pyarrow.feather as pf
import pytest

from trader_engine.holdout import HOLDOUT

REPO = Path(__file__).resolve().parents[1]
FIX = REPO / "tests" / "fixtures" / "vision"
sys.path.insert(0, str(REPO / "tests" / "fixtures"))
sys.path.insert(0, str(REPO / "scripts"))
F = importlib.import_module("fetch_binance_vision")
MK = importlib.import_module("make_vision_fixtures")
sys.path.pop(0)
sys.path.pop(0)
H = HOLDOUT[0]
UTC = timezone.utc


class Archive:
    """data.binance.vision taklidi: fixture dizini + bellek ici ek dosyalar; her istegi kaydeder; ag yok."""

    def __init__(self) -> None:
        self.extra: dict[str, bytes] = {}
        self.seen: list[str] = []
        self.fail_after: int | None = None
        self.ok_count = 0

    def __call__(self, url: str, retries: int = 5):
        assert url.startswith(F.BASE_URL + "/"), url
        self.seen.append(url)
        rel = url[len(F.BASE_URL) + 1:]
        if self.fail_after is not None and self.ok_count >= self.fail_after:
            raise RuntimeError("simule ag hatasi")
        if rel in self.extra:
            self.ok_count += 1
            return self.extra[rel]
        p = FIX / rel
        if p.exists():
            self.ok_count += 1
            return p.read_bytes()
        return None

    def add_zip(self, rel: str, name: str, csv: str, checksum: bool = True) -> None:
        blob = MK.make_zip(name, csv)
        self.extra[rel] = blob
        if checksum:
            self.extra[rel + ".CHECKSUM"] = f"{hashlib.sha256(blob).hexdigest()}  {Path(rel).name}\n".encode()


@pytest.fixture
def arch(monkeypatch):
    a = Archive()
    monkeypatch.setattr(F, "http_get", a)

    def no_net(*_a, **_k):
        raise AssertionError("ag erisimi yasak")
    monkeypatch.setattr(urllib.request, "urlopen", no_net)
    return a


def run(tmp_path, *extra, pairs="BTC", tfs="1h", start="2021-01", end="2021-02"):
    argv = ["--pairs", pairs, "--tfs", tfs, "--start", start, "--end", end, "--workers", "1",
            "--history-dir", str(tmp_path / "hist"), "--raw-dir", str(tmp_path / "raw"),
            "--report", str(tmp_path / "rep" / "gap.json"), *extra]
    return F.main(argv)


def table(tmp_path, name):
    return pf.read_table(str(tmp_path / "hist" / name))


def make_feather(path: Path, hours: list[datetime], base: float = 7.0, funding=False) -> None:
    ts = pd.to_datetime(hours, utc=True).as_unit("ms")
    if funding:
        df = pd.DataFrame({"date": ts, "funding_rate": [base] * len(ts)})
    else:
        df = pd.DataFrame({"date": ts, **{c: [base + i for i in range(len(ts))] for c in ("open", "high", "low", "close", "volume")}})
    path.parent.mkdir(parents=True, exist_ok=True)
    df.to_feather(path, compression="lz4", compression_level=9)


# ----------------------------------------------------------------------------------------- sabitler
def test_holdout_constants_match_engine():
    assert F.HOLDOUT_START == HOLDOUT[0] and F.HOLDOUT_END == HOLDOUT[1]
    assert F.LAST_ALLOWED_MONTH == "2026-04"


# ----------------------------------------------------------------------------------------- checksum
def test_checksum_mismatch_rejected(tmp_path, arch):
    dest = tmp_path / "raw" / "z.zip"
    url = f"{F.BASE_URL}/monthly/klines/ETHUSDT/1h/ETHUSDT-1h-2021-01.zip"
    with pytest.raises(F.ChecksumError):
        F.fetch_zip(url, dest)
    assert not dest.exists() and not dest.with_suffix(".part").exists()


def test_checksum_mismatch_end_to_end(tmp_path, arch):
    rc = run(tmp_path, pairs="ETH")
    assert rc == 2
    assert not list((tmp_path / "raw").rglob("*.zip"))
    assert not (tmp_path / "hist" / "ETH_USDT_USDT-1h-futures.feather").exists()
    rep = json.loads((tmp_path / "rep" / "gap.json").read_text())
    assert rep["download_counts"]["checksum_mismatch"] == 1
    assert any("checksum" in e for d in rep["datasets"] for e in d["errors"])


def test_missing_checksum_policy(tmp_path, arch):
    url = f"{F.BASE_URL}/monthly/klines/XRPUSDT/1h/XRPUSDT-1h-2021-01.zip"
    assert F.fetch_zip(url, tmp_path / "a.zip") == "nochecksum"
    with pytest.raises(F.ChecksumError):
        F.fetch_zip(url, tmp_path / "b.zip", require_checksum=True)
    assert not (tmp_path / "b.zip").exists()


def test_malformed_checksum_rejected(tmp_path, arch):
    rel = "monthly/klines/BTCUSDT/1h/BTCUSDT-1h-2021-03.zip"
    arch.add_zip(rel, "x", MK.kline_csv(2021, 3, 1, 1))
    arch.extra[rel + ".CHECKSUM"] = b"nothex  file.zip\n"
    with pytest.raises(F.ChecksumError):
        F.fetch_zip(f"{F.BASE_URL}/{rel}", tmp_path / "c.zip")


def test_corrupt_cached_zip_is_redownloaded(tmp_path, arch):
    url = f"{F.BASE_URL}/monthly/klines/BTCUSDT/1h/BTCUSDT-1h-2021-01.zip"
    dest = tmp_path / "raw" / "monthly" / "klines" / "BTCUSDT-1h-2021-01.zip"
    assert F.fetch_zip(url, dest) == "ok" and F.fetch_zip(url, dest) == "cached"
    good = dest.read_bytes()
    dest.write_bytes(b"corrupt")
    assert F.fetch_zip(url, dest) == "redownloaded" and dest.read_bytes() == good


# ----------------------------------------------------------------------------------------- sema
def test_schema_conversion_all_kinds(tmp_path, arch):
    assert run(tmp_path) == 0
    k = table(tmp_path, "BTC_USDT_USDT-1h-futures.feather")           # Ocak (baslikli) + Subat (basliksiz)
    assert k.column_names == ["date", "open", "high", "low", "close", "volume"]
    assert str(k.schema.field("date").type) == "timestamp[ms, tz=UTC]"
    assert all(str(k.schema.field(c).type) == "double" for c in k.column_names[1:])
    df = k.to_pandas()
    assert len(df) == (31 + 28) * 24 and df["date"].is_monotonic_increasing and df["date"].is_unique
    assert df["date"].iloc[0] == pd.Timestamp("2021-01-01", tz="UTC") and df["open"].iloc[0] == 1001.0
    m = table(tmp_path, "BTC_USDT_USDT-1h-mark.feather").to_pandas()
    assert len(m) == 31 * 24 and m["open"].iloc[0] == 1002.0
    f = table(tmp_path, "BTC_USDT_USDT-1h-funding_rate.feather")
    assert f.column_names == ["date", "funding_rate"]
    fd = f.to_pandas()
    assert len(fd) == 31 * 3 and (fd["date"].dt.minute == 0).all() and (fd["date"].dt.second == 0).all()   # :00:00.005 -> :00:00


def test_microsecond_timestamps_and_1m_uncompressed(tmp_path, arch):
    t0 = MK.ms(2021, 1, 1)
    rows = "\n".join(f"{(t0 + i * 60000) * 1000},1,2,0.5,1.5,10,0,0,0,0,0,0" for i in range(31 * 1440))
    arch.add_zip("monthly/klines/BTCUSDT/1m/BTCUSDT-1m-2021-01.zip", "x", rows)
    arch.add_zip("monthly/markPriceKlines/BTCUSDT/1m/BTCUSDT-1m-2021-01.zip", "x", rows)
    assert F.main(["--pairs", "BTC", "--only-1m", "--start", "2021-01", "--end", "2021-01", "--workers", "1",
                   "--history-dir", str(tmp_path / "hist"), "--raw-dir", str(tmp_path / "raw"),
                   "--report", str(tmp_path / "rep" / "gap.json")]) == 0
    for sfx in ("futures", "mark"):
        p = tmp_path / "hist" / f"BTC_USDT_USDT-1m-{sfx}.feather"
        t = pf.read_table(str(p))
        assert t.num_rows == 31 * 1440 and t.column("date")[0].as_py() == datetime(2021, 1, 1, tzinfo=UTC)
        assert os.path.getsize(p) > 0.9 * t.num_rows * 8 * 6


# ----------------------------------------------------------------------------------------- birlestirme
def _spanning_existing(path: Path):
    """Subat basindan baslayan; kilitli donemi kesen mevcut dosya (sentetik)."""
    hrs = [datetime(2021, 2, 1, h, tzinfo=UTC) for h in range(0, 24)]
    hrs += [datetime(2026, 4, 30, 22, tzinfo=UTC), datetime(2026, 4, 30, 23, tzinfo=UTC)]
    hrs += [datetime(2026, 5, 1, 0, tzinfo=UTC), datetime(2026, 5, 1, 1, tzinfo=UTC), datetime(2026, 8, 1, tzinfo=UTC),
            datetime(2026, 11, 15, tzinfo=UTC)]
    make_feather(path, hrs)
    return hrs


def test_merge_prepend_dedup_and_tail_preserved(tmp_path, arch):
    path = tmp_path / "hist" / "BTC_USDT_USDT-1h-futures.feather"
    _spanning_existing(path)
    before = pf.read_table(str(path)).to_pandas()
    tail_before = before[before["date"] >= pd.Timestamp(H)].reset_index(drop=True)
    assert run(tmp_path) == 0
    after = pf.read_table(str(path)).to_pandas()
    assert after["date"].is_monotonic_increasing and after["date"].is_unique
    # kilitli donem satirlari birebir ayni
    tail_after = after[after["date"] >= pd.Timestamp(H)].reset_index(drop=True)
    assert tail_after.equals(tail_before) and len(tail_after) == 4
    # Ocak eklendi (31*24), Subat'in 1. gunu mevcut dosyadan (7.0 degerli) korundu (mevcut kazanir)
    assert (after["date"] < pd.Timestamp("2021-02-01", tz="UTC")).sum() == 31 * 24
    feb1 = after[(after["date"] >= pd.Timestamp("2021-02-01", tz="UTC")) & (after["date"] < pd.Timestamp("2021-02-02", tz="UTC"))]
    assert len(feb1) == 24 and feb1["open"].iloc[0] == 7.0
    # Subat'in kalan 27 gunu zip'ten
    assert (after["date"].between(pd.Timestamp("2021-02-02", tz="UTC"), pd.Timestamp("2021-02-28 23:00", tz="UTC"))).sum() == 27 * 24
    # 2026-04-30 22-23 (kilitli donem oncesi) mevcut satirlar duruyor
    assert (after["date"] == pd.Timestamp("2026-04-30 23:00", tz="UTC")).sum() == 1
    assert pf.read_table(str(path)).schema.equals(pf.read_table(str(path)).schema)


def test_rerun_is_idempotent_no_rewrite_no_network(tmp_path, arch):
    path = tmp_path / "hist" / "BTC_USDT_USDT-1h-futures.feather"
    _spanning_existing(path)
    assert run(tmp_path) == 0
    b1, m1 = path.read_bytes(), path.stat().st_mtime_ns
    n_fetch = len(arch.seen)
    assert run(tmp_path) == 0
    assert path.read_bytes() == b1 and path.stat().st_mtime_ns == m1          # dokunulmadi
    rep = json.loads((tmp_path / "rep" / "gap.json").read_text())
    assert any(d["feather"].endswith(":unchanged") for d in rep["datasets"] if d["kind"] == "klines")
    # onbellekten: tekrar indirme yok (yalniz bos/404 gunluk-aylik yoklamalari olabilir, zip'ler yeniden istenmez)
    again = arch.seen[n_fetch:]
    assert not any(u.endswith("BTCUSDT-1h-2021-01.zip") for u in again)


def test_merge_into_history_fresh_file(tmp_path):
    new = pd.DataFrame({"date": pd.to_datetime(["2021-01-01", "2021-01-02"], utc=True).as_unit("ms"), "open": [1.0, 2.0], "high": [1.0, 2.0],
                        "low": [1.0, 2.0], "close": [1.0, 2.0], "volume": [1.0, 2.0]})
    st, merged = F.merge_into_history(tmp_path / "x.feather", new, "1h")
    assert st == "created" and len(merged) == 2
    st, _ = F.merge_into_history(tmp_path / "x.feather", new, "1h")
    assert st == "unchanged"


# ----------------------------------------------------------------------------------------- kilitli donem
def test_holdout_only_file_untouched(tmp_path, arch):
    """Tamamen kilitli donemdeki dosya (ayri cift/tf) hicbir kosuda degismez: bayt + mtime."""
    hold = tmp_path / "hist" / "SOL_USDT_USDT-1h-futures.feather"
    make_feather(hold, [datetime(2026, 5, 1, h, tzinfo=UTC) for h in range(5)] + [datetime(2026, 9, 1, tzinfo=UTC)])
    b0, m0 = hold.read_bytes(), hold.stat().st_mtime_ns
    os.utime(hold, ns=(m0, m0))
    assert run(tmp_path, pairs="BTC,SOL") == 0                          # SOL icin arsivde veri yok
    assert hold.read_bytes() == b0 and hold.stat().st_mtime_ns == m0
    # ayni dosya, yeni veri gelse bile kilitli satirlar degismez
    arch.add_zip("monthly/klines/SOLUSDT/1h/SOLUSDT-1h-2021-01.zip", "s", MK.kline_csv(2021, 1, 31, 5))
    assert run(tmp_path, pairs="SOL") == 0
    df = pf.read_table(str(hold)).to_pandas()
    assert df[df["date"] >= pd.Timestamp(H)]["open"].tolist() == [7.0, 8.0, 9.0, 10.0, 11.0, 12.0]
    assert len(df) == 31 * 24 + 6


def test_no_holdout_urls_requested_and_end_clamped(tmp_path, arch):
    assert run(tmp_path, end="2026-11") == 0
    periods = [F.period_start(u) for u in arch.seen if not u.endswith(".CHECKSUM")]
    assert periods and all(p < H.date() for p in periods), max(periods)
    assert max(periods) >= datetime(2026, 4, 1).date()                  # 2026-04'e kadar yoklandi
    # raw onbellekte kilitli donem zip'i varsa bile okunmaz
    raw = tmp_path / "raw" / "monthly" / "klines"
    bad = raw / ("BTCUSDT-1h-2026-" + "06.zip")
    bad.write_bytes(b"not a zip")
    assert run(tmp_path, end="2026-11") == 0
    assert bad.read_bytes() == b"not a zip"


def test_guard_rejects_holdout_request(tmp_path, arch):
    with pytest.raises(F.HoldoutViolation):
        F.fetch_zip(f"{F.BASE_URL}/monthly/klines/BTCUSDT/1h/BTCUSDT-1h-{H.year}-{H.month:02d}.zip", tmp_path / "z.zip")
    with pytest.raises(F.HoldoutViolation):
        F.fetch_zip(f"{F.BASE_URL}/daily/klines/BTCUSDT/1h/BTCUSDT-1h-{H.year}-07-04.zip", tmp_path / "z.zip")
    assert not arch.seen


# ----------------------------------------------------------------------------------------- bosluk raporu
def test_gap_report(tmp_path, arch):
    arch.add_zip("monthly/klines/BTCUSDT/1h/BTCUSDT-1h-2021-02.zip", "feb", MK.kline_csv(2021, 2, 28, 2000, skip_days=(10, 11)))
    # 2021-03 hic yok (aylik 404 + gunluk 404)
    assert run(tmp_path, end="2021-03") == 0
    rep = json.loads((tmp_path / "rep" / "gap.json").read_text())
    k = next(d for d in rep["datasets"] if d["kind"] == "klines")
    assert k["missing_months"] == ["2021-03"]
    assert "2021-02-10..2021-02-11" in k["missing_day_ranges"] and "2021-03-01..2021-03-31" in k["missing_day_ranges"]
    assert k["missing_days"] == 2 + 31 and k["missing_bars"] == (2 + 31) * 24
    fr = next(d for d in rep["datasets"] if d["kind"] == "fundingRate")
    assert fr["missing_months"] == ["2021-02", "2021-03"]
    assert rep["totals"]["datasets_with_gaps"] == 3
    md = (tmp_path / "rep" / "gap.md").read_text()
    assert "2021-03" in md and "BTC/USDT:USDT" in md


def test_gap_report_partial_day_and_stats():
    df = pd.DataFrame({"date": pd.to_datetime(["2021-01-01 00:00", "2021-01-01 01:00", "2021-01-03 00:00"], utc=True).as_unit("ms")})
    s = F.gap_stats(df, "1h", datetime(2021, 1, 1).date(), datetime(2021, 1, 3).date())
    assert s["missing_day_ranges"] == ["2021-01-02"] and s["partial_days"] == 2 and s["missing_bars"] == 22 + 23 + 24


# ----------------------------------------------------------------------------------------- resume / hiz siniri
def test_resume_after_failure(tmp_path, arch):
    arch.fail_after = 3                                                   # 3 basarili GET'ten sonra ag duser
    assert run(tmp_path) == 1
    cached = {p.relative_to(tmp_path / "raw").as_posix() for p in (tmp_path / "raw").rglob("*.zip")}
    assert 0 < len(cached) < 4
    arch.fail_after = None
    arch.seen.clear()
    assert run(tmp_path) == 0
    refetched = {u[len(F.BASE_URL) + 1:].replace("/BTCUSDT/1h/", "/").replace("/BTCUSDT/", "/") for u in arch.seen if u.endswith(".zip")}
    assert not (refetched & cached)                                       # kaldigi yerden: var olanlar yeniden istenmedi
    assert len(table(tmp_path, "BTC_USDT_USDT-1h-futures.feather").to_pandas()) == 59 * 24
    assert not list((tmp_path / "raw").rglob("*.part"))


def test_rate_limiter_spacing():
    now = [0.0]
    sleeps = []

    def clock():
        return now[0]

    def sleep(s):
        sleeps.append(s)
        now[0] += s
    rl = F.RateLimiter(4, clock=clock, sleep=sleep)
    for _ in range(5):
        rl.acquire()
    assert sleeps == pytest.approx([0.25] * 4) and now[0] == pytest.approx(1.0)
    F.RateLimiter(0, clock=clock, sleep=sleep).acquire()
    assert len(sleeps) == 4


def test_dry_run_writes_and_fetches_nothing(tmp_path, arch):
    assert run(tmp_path, "--dry-run") == 0
    assert not arch.seen and not (tmp_path / "hist").exists() and not (tmp_path / "raw").exists()


def test_corrupt_zip_in_cache_is_reported_not_fatal(tmp_path, arch):
    raw = tmp_path / "raw" / "monthly" / "klines"
    raw.mkdir(parents=True)
    (raw / "BTCUSDT-1h-2021-01.zip").write_bytes(b"garbage")              # sidecar yok -> "cached"; okunurken BadZipFile
    assert run(tmp_path, end="2021-01") == 0
    rep = json.loads((tmp_path / "rep" / "gap.json").read_text())
    k = next(d for d in rep["datasets"] if d["kind"] == "klines")
    assert any("okunamadi" in e for e in k["errors"]) and k["missing_months"] == ["2021-01"]
    assert zipfile.is_zipfile(FIX / "monthly/klines/BTCUSDT/1h/BTCUSDT-1h-2021-01.zip")
