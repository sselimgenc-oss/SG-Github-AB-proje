"""Independent spec tests for engine unit 01 (docs/motor/01-feed.md, market feed).

Written from the spec only (without reading store/feed/sources).  All HTTP is
faked; no network.  Hand-checkable numbers follow spec section 9.
"""
from __future__ import annotations

import json
import os
import random
import sqlite3
import subprocess
import sys
import threading
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from trader_engine.bars import from_ms, to_ms, tf_delta
from trader_engine.clock import SimClock
from trader_engine.errors import ClockError, DataError, EngineError
from trader_engine.exchange.rules import extract_rules, spec_from_json, spec_to_json, to_symbol_rules
from trader_engine.marketdata.rest_public import ExchangeBan, ExchangeError, PublicRestClient, rows_to_bars
from trader_engine.types import Bar, FundingPoint, pair_stem

from trader_engine.marketdata.store import MarketStore  # noqa: E402
from trader_engine.marketdata.feed import Feed, FeedConfig, snapshot_rules  # noqa: E402

UTC = timezone.utc
BTC, ETH = "BTC/USDT", "ETH/USDT"
ALL_MS = (0, 10**15)
REPO = Path(__file__).resolve().parents[2]


def dt(y, mo, d, h=0, mi=0, s=0, ms=0):
    return datetime(y, mo, d, h, mi, s, ms * 1000, tzinfo=UTC)


def mk(pair, kind, tf, open_dt, o=100.0, h=101.0, l=99.0, c=100.5, v=1.0):
    return Bar(pair, kind, tf, open_dt, o, h, l, c, v)


def mins(start, n):
    return [start + timedelta(minutes=i) for i in range(n)]


# --------------------------------------------------------------------------- fake Binance
class Resp:
    def __init__(self, status=200, body=None, headers=None):
        self.status_code, self._b, self.headers = status, body, headers or {}
        self.text = json.dumps(body) if body is not None else ""

    def json(self):
        return self._b


def _minute(k):
    o = 100.0 + (k % 97) * 0.01
    c = o + ((k % 5) - 2) * 0.01
    return o, max(o, c) + 0.02, min(o, c) - 0.02, c, 1.0 + k % 7


def _mark_minute(k):
    o = 100.5 + (k % 31) * 0.01
    c = o + ((k % 3) - 1) * 0.01
    return o, max(o, c) + 0.01, min(o, c) - 0.01, c


ORIGIN_MS = to_ms(dt(2026, 11, 1))


class FakeBinance:
    """Fake requests.Session emulating the Binance futures public endpoints."""

    def __init__(self, clock, offset_s=0.0):
        self.clock, self.offset_s = clock, offset_s
        self.calls = []
        self.omit = set()        # (symbol, interval, open_ms) -> row absent (kline & mark)
        self.scale = {}          # (symbol, interval, open_ms) -> factor on OHLC (last klines only)
        self.hover = {}          # (symbol, interval, open_ms) -> added to h of tf row
        self.inject = []         # callables (path, params) -> Resp | None
        self.symbols = ["BTCUSDT", "ETHUSDT"]

    def now_ms(self):
        return to_ms(self.clock.now()) + int(self.offset_s * 1000)

    def agg(self, tf, open_ms):
        n = int(tf_delta(tf).total_seconds() // 60)
        ks = [open_ms // 60000 + i for i in range(n)]
        ms = [_minute(k) for k in ks]
        return ms[0][0], max(m[1] for m in ms), min(m[2] for m in ms), ms[-1][3], sum(m[4] for m in ms)

    def row(self, path, sym, tf, open_ms):
        tfms = int(tf_delta(tf).total_seconds() * 1000)
        if "mark" in path:
            o, h, l, c = _mark_minute(open_ms // 60000)
            v = 0.0
        else:
            o, h, l, c, v = self.agg(tf, open_ms) if tf != "1m" else _minute(open_ms // 60000)
            f = self.scale.get((sym, tf, open_ms))
            if f:
                o, h, l, c = o * f, h * f, l * f, c * f
            h += self.hover.get((sym, tf, open_ms), 0.0)
        return [open_ms, str(o), str(h), str(l), str(c), str(v), open_ms + tfms - 1, "0", 0, "0", "0", "0"]

    def get(self, url, params=None, timeout=None):
        path = url.split("fapi.binance.com", 1)[1]
        params = dict(params or {})
        self.calls.append((path, params))
        for f in self.inject:
            r = f(path, params)
            if r is not None:
                return r
        now = self.now_ms()
        if path == "/fapi/v1/time":
            return Resp(200, {"serverTime": now})
        if path == "/fapi/v1/exchangeInfo":
            return Resp(200, {"symbols": [self._sym(s) for s in self.symbols]})
        if path == "/fapi/v1/fundingRate":
            sym, lim = params["symbol"], params.get("limit", 100)
            start = params.get("startTime", ORIGIN_MS)
            out, t = [], (max(start, ORIGIN_MS) + 8 * 3600000 - 1) // (8 * 3600000) * (8 * 3600000)
            while t <= now and len(out) < lim:
                out.append({"symbol": sym, "fundingTime": t, "fundingRate": "0.00010000", "markPrice": "100.1"})
                t += 8 * 3600000
            return Resp(200, out)
        if path in ("/fapi/v1/klines", "/fapi/v1/markPriceKlines"):
            sym, tf, lim = params["symbol"], params["interval"], params.get("limit", 500)
            tfms = int(tf_delta(tf).total_seconds() * 1000)
            last_open = now // tfms * tfms
            if params.get("startTime") is None:
                first = max(last_open - (lim - 1) * tfms, ORIGIN_MS // tfms * tfms)
            else:
                first = -(-max(params["startTime"], ORIGIN_MS) // tfms) * tfms
            rows = []
            for o in range(first, last_open + 1, tfms):
                if params.get("endTime") is not None and o > params["endTime"]:
                    break
                if (sym, tf, o) in self.omit:
                    continue
                rows.append(self.row(path, sym, tf, o))
                if len(rows) >= lim:
                    break
            return Resp(200, rows)
        return Resp(404, {"msg": "nope"})

    @staticmethod
    def _sym(s):
        return {"symbol": s, "status": "TRADING", "contractType": "PERPETUAL", "filters": [
            {"filterType": "PRICE_FILTER", "tickSize": "0.10"},
            {"filterType": "LOT_SIZE", "stepSize": "0.001", "minQty": "0.001", "maxQty": "1000"},
            {"filterType": "MARKET_LOT_SIZE", "stepSize": "0.001", "minQty": "0.001", "maxQty": "120"},
            {"filterType": "MIN_NOTIONAL", "notional": "100"}]}

    def kline_calls(self, interval, mark=False):
        p = "/fapi/v1/markPriceKlines" if mark else "/fapi/v1/klines"
        return [c for c in self.calls if c[0] == p and c[1].get("interval") == interval]


class Env:
    pass


def make_env(tmp_path, start, *, offset_s=0.0, backfill=None, pairs=(BTC, ETH), max_attempts=2):
    e = Env()
    e.clock = SimClock(start)
    e.srv = FakeBinance(e.clock, offset_s)
    e.rest = PublicRestClient(session=e.srv, now_s=lambda: e.clock.now().timestamp(), sleep=e.clock.sleep,
                              max_attempts=max_attempts)
    e.db = str(tmp_path / "market.sqlite")
    e.store = MarketStore(e.db)
    e.cfg = FeedConfig(pairs=tuple(pairs), db_path=e.db, lock_path=str(tmp_path / "market.lock"),
                       status_path=str(tmp_path / "status.json"),
                       backfill_bars=backfill or {"1m": 120, "15m": 8, "1h": 6, "4h": 4})
    e.feed = Feed(e.cfg, e.rest, e.store, e.clock)
    e.tmp = tmp_path
    return e


def raw(db, sql, args=()):
    con = sqlite3.connect(db)
    try:
        return con.execute(sql, args).fetchall()
    finally:
        con.close()


# =========================================================================== store: schema & writes
def test_schema_user_version_tables_pragmas(tmp_path):
    db = str(tmp_path / "m.sqlite")
    MarketStore(db).close()
    assert raw(db, "PRAGMA user_version")[0][0] == 1
    assert raw(db, "PRAGMA journal_mode")[0][0].lower() == "wal"
    tabs = {r[0] for r in raw(db, "SELECT name FROM sqlite_master WHERE type='table'")}
    assert {"bars", "funding", "rules", "gaps", "feed_meta"} <= tabs
    cols = [r[1] for r in raw(db, "PRAGMA table_info(bars)")]
    assert cols == ["kind", "pair", "tf", "open_ms", "o", "h", "l", "c", "v", "written_ms"]
    assert [r[1] for r in raw(db, "PRAGMA table_info(funding)")] == ["pair", "ts_ms", "rate", "mark"]
    assert [r[1] for r in raw(db, "PRAGMA table_info(gaps)")] == ["kind", "pair", "tf", "open_ms", "reason", "detected_ms"]


def test_put_bars_basic_and_written_ms(tmp_path):
    s = MarketStore(str(tmp_path / "m.sqlite"))
    t = dt(2026, 12, 1, 9)
    res = s.put_bars([mk(BTC, "last", "1m", t), mk(BTC, "last", "1m", t + timedelta(minutes=1))], now_ms=123456)
    assert (res.inserted, res.duplicates_equal, res.conflicts) == (2, 0, 0)
    rows = raw(s_path(tmp_path), "SELECT open_ms,o,h,l,c,v,written_ms FROM bars ORDER BY open_ms")
    assert rows[0] == (to_ms(t), 100.0, 101.0, 99.0, 100.5, 1.0, 123456)


def s_path(tmp_path):
    return str(tmp_path / "m.sqlite")


def test_put_bars_idempotent_equal_duplicates(tmp_path):
    s = MarketStore(s_path(tmp_path))
    b = mk(BTC, "last", "1h", dt(2026, 12, 1, 8))
    s.put_bars([b], now_ms=1)
    res = s.put_bars([b], now_ms=2)
    assert (res.inserted, res.duplicates_equal, res.conflicts) == (0, 1, 0)
    assert raw(s_path(tmp_path), "SELECT count(*), min(written_ms) FROM bars")[0] == (1, 1)
    assert raw(s_path(tmp_path), "SELECT count(*) FROM gaps")[0][0] == 0


def test_put_bars_conflict_keeps_old_and_marks_gap(tmp_path):
    s = MarketStore(s_path(tmp_path))
    t = dt(2026, 12, 1, 8)
    s.put_bars([mk(BTC, "last", "1h", t)], now_ms=1)
    res = s.put_bars([mk(BTC, "last", "1h", t, c=100.6)], now_ms=2)
    assert (res.inserted, res.duplicates_equal, res.conflicts) == (0, 0, 1)
    assert raw(s_path(tmp_path), "SELECT c FROM bars")[0][0] == 100.5
    assert (to_ms(t), "conflict") in s.gaps_in(BTC, "1h", *ALL_MS)


def test_put_bars_tolerances(tmp_path):
    s = MarketStore(s_path(tmp_path))
    t = dt(2026, 12, 1, 8)
    s.put_bars([mk(BTC, "last", "1h", t, c=100.0)], now_ms=1)
    assert s.put_bars([mk(BTC, "last", "1h", t, c=100.0 * (1 + 1e-10))], now_ms=2).duplicates_equal == 1  # < 1e-9
    assert s.put_bars([mk(BTC, "last", "1h", t, c=100.0 * (1 + 1e-7))], now_ms=3).conflicts == 1       # > 1e-9
    t2 = dt(2026, 12, 1, 9)
    s.put_bars([mk(BTC, "last", "1h", t2, v=1000.0)], now_ms=1)
    assert s.put_bars([mk(BTC, "last", "1h", t2, v=1000.0 * (1 + 1e-7))], now_ms=2).duplicates_equal == 1  # < 1e-6
    assert s.put_bars([mk(BTC, "last", "1h", t2, v=1000.0 * (1 + 1e-5))], now_ms=3).conflicts == 1        # > 1e-6


def test_put_bars_kinds_pairs_tfs_are_distinct_keys(tmp_path):
    s = MarketStore(s_path(tmp_path))
    t = dt(2026, 12, 1, 8)
    res = s.put_bars([mk(BTC, "last", "1m", t), mk(BTC, "mark", "1m", t), mk(ETH, "last", "1m", t),
                      mk(BTC, "last", "15m", t)], now_ms=1)
    assert res.inserted == 4 and res.conflicts == 0


@pytest.mark.parametrize("bad", [
    dict(h=99.5),                      # h < max(o,c)
    dict(l=100.2),                     # l > min(o,c)
    dict(o=-1.0, l=-2.0),              # non-positive
    dict(c=float("nan")),
    dict(h=float("inf")),
    dict(o=0.0, l=0.0),
])
def test_invalid_bar_not_written_batch_survives(tmp_path, bad):
    s = MarketStore(s_path(tmp_path))
    t = dt(2026, 12, 1, 9)
    good = mk(BTC, "last", "1m", t)
    badbar = mk(BTC, "last", "1m", t + timedelta(minutes=1), **bad)
    good2 = mk(BTC, "last", "1m", t + timedelta(minutes=2))
    res = s.put_bars([good, badbar, good2], now_ms=1)
    assert res.inserted == 2
    assert [r[0] for r in raw(s_path(tmp_path), "SELECT open_ms FROM bars ORDER BY open_ms")] == [to_ms(t), to_ms(t) + 120000]


def test_unaligned_open_rejected(tmp_path):
    s = MarketStore(s_path(tmp_path))
    s.put_bars([mk(BTC, "last", "15m", dt(2026, 12, 1, 9, 7)), mk(BTC, "last", "4h", dt(2026, 12, 1, 9)),
                mk(BTC, "last", "15m", dt(2026, 12, 1, 9, 15))], now_ms=1)
    assert [r[0] for r in raw(s_path(tmp_path), "SELECT open_ms FROM bars")] == [to_ms(dt(2026, 12, 1, 9, 15))]


def test_mark_bar_volume_ignored(tmp_path):
    s = MarketStore(s_path(tmp_path))
    s.put_bars([mk(BTC, "mark", "1m", dt(2026, 12, 1, 9), v=5.0)], now_ms=1)
    assert raw(s_path(tmp_path), "SELECT v FROM bars")[0][0] == 0


def test_read_only_store_rejects_writes_and_reads(tmp_path):
    w = MarketStore(s_path(tmp_path))
    t = dt(2026, 12, 1, 9)
    w.put_bars([mk(BTC, "last", "1m", t)], now_ms=1)
    r = MarketStore(s_path(tmp_path), read_only=True)
    assert r.last_open_ms("last", BTC, "1m") == to_ms(t)
    with pytest.raises(DataError):
        r.put_bars([mk(BTC, "last", "1m", t + timedelta(minutes=1))], now_ms=2)
    with pytest.raises(DataError):
        r.meta_set("a", "b")


def test_queries_until_boundaries_and_order(tmp_path):
    s = MarketStore(s_path(tmp_path))
    t = dt(2026, 12, 1, 9)
    s.put_bars([mk(BTC, "last", "1m", t + timedelta(minutes=i), o=100 + i, h=102 + i, l=99 + i, c=101 + i) for i in range(3)], now_ms=1)
    m0 = to_ms(t)
    assert [b.open_ts for b in s.query_bars("last", BTC, "1m", m0 + 119999, None)] == [t]          # 1 ms before close of 09:01
    assert [b.open_ts for b in s.query_bars("last", BTC, "1m", m0 + 120000, None)] == [t, t + timedelta(minutes=1)]
    assert [b.open_ts for b in s.query_bars("last", BTC, "1m", m0 + 59999, None)] == []
    assert [b.open_ts for b in s.query_bars("last", BTC, "1m", m0 + 10**9, 2)] == [t + timedelta(minutes=1), t + timedelta(minutes=2)]
    b = s.query_bars("last", BTC, "1m", m0 + 60000, None)[0]
    assert (b.pair, b.kind, b.tf, b.o, b.h, b.l, b.c) == (BTC, "last", "1m", 100, 102, 99, 101)
    assert s.query_bars("mark", BTC, "1m", m0 + 10**9, None) == []
    assert s.query_bars("last", ETH, "1m", m0 + 10**9, None) == []


def test_query_range_half_open_and_last_open(tmp_path):
    s = MarketStore(s_path(tmp_path))
    t = dt(2026, 12, 1, 9)
    assert s.last_open_ms("last", BTC, "1m") is None
    s.put_bars([mk(BTC, "last", "1m", t + timedelta(minutes=i)) for i in range(5)], now_ms=1)
    got = s.query_range("last", BTC, "1m", to_ms(t) + 60000, to_ms(t) + 3 * 60000)
    assert [b.open_ts for b in got] == [t + timedelta(minutes=1), t + timedelta(minutes=2)]
    assert s.last_open_ms("last", BTC, "1m") == to_ms(t + timedelta(minutes=4))
    assert s.last_open_ms("mark", BTC, "1m") is None


def test_funding_roundtrip_range_and_null_mark(tmp_path):
    s = MarketStore(s_path(tmp_path))
    t8, t16, t24 = dt(2026, 10, 31, 8), dt(2026, 10, 31, 16), dt(2026, 11, 1)
    pts = [FundingPoint(BTC, t8, 0.0001, 100.0), FundingPoint(BTC, t16, -0.0002, None), FundingPoint(BTC, t24, 0.0003, 101.0)]
    assert s.put_funding(pts) == 3
    s.put_funding(pts)
    assert raw(s_path(tmp_path), "SELECT count(*) FROM funding")[0][0] == 3
    got = s.query_funding(BTC, to_ms(t8), to_ms(t24))             # (start, end]
    assert [p.ts for p in got] == [t16, t24]
    assert got[0].mark is None and got[0].rate == -0.0002 and got[1].mark == 101.0
    assert s.query_funding(ETH, 0, 10**15) == []


def test_rules_meta_prune_and_gaps(tmp_path):
    s = MarketStore(s_path(tmp_path))
    assert s.get_rules(BTC) is None
    s.put_rules(BTC, '{"a":1}', 777)
    assert s.get_rules(BTC) == ('{"a":1}', 777)
    s.put_rules(BTC, '{"a":2}', 888)
    assert s.get_rules(BTC) == ('{"a":2}', 888)
    assert s.meta_get("k") is None
    s.meta_set("k", "v1")
    s.meta_set("k", "v2")
    assert s.meta_get("k") == "v2"
    s.mark_gap("last", BTC, "1m", 60000, "missing", 5)
    s.mark_gap("last", BTC, "1m", 60000, "missing", 6)     # idempotent per (key, reason)
    s.mark_gap("last", BTC, "1m", 60000, "agg_mismatch", 6)
    assert sorted(s.gaps_in(BTC, "1m", 0, 120000)) == [(60000, "agg_mismatch"), (60000, "missing")]
    assert s.gaps_in(BTC, "1m", 120000, 240000) == []
    assert s.gaps_in(BTC, "15m", 0, 120000) == []


def test_prune_only_old_1m(tmp_path):
    s = MarketStore(s_path(tmp_path))
    now = dt(2026, 12, 20)
    old, new = now - timedelta(days=15), now - timedelta(days=13)
    s.put_bars([mk(BTC, "last", "1m", old), mk(BTC, "mark", "1m", old), mk(BTC, "last", "1m", new),
                mk(BTC, "last", "15m", dt(2026, 11, 1)), mk(BTC, "last", "1h", dt(2026, 11, 1)),
                mk(BTC, "last", "4h", dt(2026, 11, 1))], now_ms=1)
    assert s.prune(to_ms(now), 14) == 2
    left = raw(s_path(tmp_path), "SELECT kind,tf,open_ms FROM bars ORDER BY tf,open_ms")
    assert len(left) == 4 and ("last", "1m", to_ms(new)) in left


# =========================================================================== corrupt data (fail closed)
def test_corrupt_sqlite_file_fails_closed(tmp_path):
    p = tmp_path / "m.sqlite"
    p.write_bytes(b"this is definitely not a sqlite database" * 50)
    with pytest.raises((DataError, sqlite3.DatabaseError)):
        s = MarketStore(str(p), read_only=True)
        s.last_open_ms("last", BTC, "1m")


def test_missing_db_read_only_fails_closed(tmp_path):
    with pytest.raises((DataError, sqlite3.Error)):
        s = MarketStore(str(tmp_path / "nope.sqlite"), read_only=True)
        s.last_open_ms("last", BTC, "1m")


# =========================================================================== concurrency
def test_multiple_readers_while_writer_writes(tmp_path):
    db = s_path(tmp_path)
    MarketStore(db).close()
    t0 = dt(2026, 12, 1)
    done = threading.Event()
    errors = []
    N_BATCH, PER = 60, 10

    def writer():
        try:
            w = MarketStore(db)
            for i in range(N_BATCH):
                w.put_bars([mk(BTC, "last", "1m", t0 + timedelta(minutes=i * PER + j)) for j in range(PER)], now_ms=i)
        except Exception as e:  # noqa: BLE001
            errors.append(("w", e))
        finally:
            done.set()

    def reader(idx):
        try:
            r = MarketStore(db, read_only=True)
            prev = -1
            while True:
                fin = done.is_set()
                bars = r.query_bars("last", BTC, "1m", to_ms(t0) + 10**10, None)
                opens = [to_ms(b.open_ts) for b in bars]
                assert opens == [to_ms(t0) + 60000 * k for k in range(len(opens))], "holes or disorder"
                assert len(opens) % PER == 0, "partial batch visible (transaction atomicity)"
                assert len(opens) >= prev
                prev = len(opens)
                if fin:
                    break
            assert prev == N_BATCH * PER
        except Exception as e:  # noqa: BLE001
            errors.append((idx, e))

    ths = [threading.Thread(target=reader, args=(i,)) for i in range(3)] + [threading.Thread(target=writer)]
    for t in ths:
        t.start()
    for t in ths:
        t.join(60)
    assert not errors, errors


# =========================================================================== rows_to_bars (07) / spec example 1
def _row(open_ms, tf_ms, o="100", h="101", l="99", c="100.5", v="2"):
    return [open_ms, o, h, l, c, v, open_ms + tf_ms - 1, "0", 0, "0", "0", "0"]


def test_rows_to_bars_drops_open_bar_example1():
    now = to_ms(dt(2026, 12, 1, 9, 0, 2))
    m859, m900 = to_ms(dt(2026, 12, 1, 8, 59)), to_ms(dt(2026, 12, 1, 9))
    bars, bad = rows_to_bars(BTC, "last", "1m", [_row(m859, 60000), _row(m900, 60000)], now)
    assert [b.open_ts for b in bars] == [dt(2026, 12, 1, 8, 59)] and bad == []
    # exactly at close: closeTime + 1 == now -> closed
    bars, _ = rows_to_bars(BTC, "last", "1m", [_row(m900, 60000)], m900 + 60000)
    assert len(bars) == 1
    bars, _ = rows_to_bars(BTC, "last", "1m", [_row(m900, 60000)], m900 + 59999)
    assert bars == []


def test_rows_to_bars_abnormal_close_and_bad_values():
    m = to_ms(dt(2026, 12, 1, 8))
    r = _row(m, 60000)
    r[6] = m + 60000          # wrong closeTime
    now = m + 10**9
    bars, bad = rows_to_bars(BTC, "last", "1m", [r, _row(m + 60000, 60000, o="-1")], now)
    assert bars == [] and sorted(x.reason for x in bad) == ["bad_close_time", "bad_values"]
    mb, _ = rows_to_bars(BTC, "mark", "1m", [_row(m, 60000, v="9")], now)
    assert mb[0].v == 0.0


# =========================================================================== feed: start / backfill / gaps
T_START = dt(2026, 12, 1, 8, 59, 30)


def test_start_backfills_only_closed_bars_and_rules(tmp_path):
    e = make_env(tmp_path, dt(2026, 12, 1, 9, 0, 2))
    e.feed.start()
    last = to_ms(dt(2026, 12, 1, 8, 59))
    for pair in (BTC, ETH):
        assert e.store.last_open_ms("last", pair, "1m") in (last,)  # 09:00 bar is open at 09:00:02 and must not be stored
        assert e.store.last_open_ms("mark", pair, "1m") == last
        n = len(e.store.query_range("last", pair, "1m", 0, 10**15))
        assert 119 <= n <= 121
        assert e.store.last_open_ms("last", pair, "15m") == to_ms(dt(2026, 12, 1, 8, 45))
        assert e.store.last_open_ms("last", pair, "1h") == to_ms(dt(2026, 12, 1, 8))
        assert e.store.last_open_ms("last", pair, "4h") == to_ms(dt(2026, 12, 1, 4))
    js, fetched = e.store.get_rules(BTC)
    assert spec_from_json(js) == extract_rules(e.srv.get("https://fapi.binance.com/fapi/v1/exchangeInfo").json(), "BTCUSDT")
    assert fetched > 0
    assert e.store.get_rules("XRP/USDT") is None
    # mark is stored only for 1m
    assert raw(e.db, "SELECT count(*) FROM bars WHERE kind='mark' AND tf!='1m'")[0][0] == 0
    # nothing beyond closed bars: every stored bar closed at or before server now
    now_ms = e.srv.now_ms()
    for o, tf in raw(e.db, "SELECT open_ms, tf FROM bars"):
        assert o + int(tf_delta(tf).total_seconds() * 1000) <= now_ms


def test_start_stores_funding_with_mark(tmp_path):
    e = make_env(tmp_path, T_START)
    e.feed.start()
    f = e.store.query_funding(BTC, 0, 10**15)
    assert f == [] or all(p.ts.hour % 8 == 0 and p.rate == 0.0001 for p in f)


def test_backfill_pagination_over_1500_and_contiguous(tmp_path):
    e = make_env(tmp_path, T_START, backfill={"1m": 2000, "15m": 8, "1h": 6, "4h": 4}, pairs=(BTC,))
    e.feed.start()
    bars = e.store.query_range("last", BTC, "1m", 0, 10**15)
    assert 1999 <= len(bars) <= 2001
    opens = [to_ms(b.open_ts) for b in bars]
    assert opens == [opens[0] + 60000 * i for i in range(len(opens))]
    assert all(c[1].get("limit", 0) <= 1500 for c in e.srv.calls if "klines" in c[0].lower())
    assert e.store.gaps_in(BTC, "1m", *ALL_MS) == []


def test_backfill_marks_missing_minute_and_never_invents(tmp_path):
    e = make_env(tmp_path, T_START, pairs=(BTC,))
    hole = to_ms(dt(2026, 12, 1, 8, 30))
    e.srv.omit.add(("BTCUSDT", "1m", hole))
    e.feed.start()
    assert (hole, "missing") in e.store.gaps_in(BTC, "1m", *ALL_MS)
    assert all(to_ms(b.open_ts) != hole for b in e.store.query_range("last", BTC, "1m", 0, 10**15))
    assert len(e.store.query_range("last", BTC, "1m", hole - 60000, hole + 120000)) == 2
    assert e.store.last_open_ms("last", BTC, "1m") == to_ms(dt(2026, 12, 1, 8, 58))


def test_restart_resumes_fills_gap_no_conflicts_no_rewrite(tmp_path):
    e = make_env(tmp_path, dt(2026, 12, 1, 8, 0, 30), pairs=(BTC,))
    e.feed.start()
    before = raw(e.db, "SELECT open_ms, written_ms FROM bars WHERE kind='last' AND tf='1m'")
    e.clock.set_time(dt(2026, 12, 1, 8, 59, 30))        # feed was down for an hour
    e.feed.backfill()
    bars = e.store.query_range("last", BTC, "1m", 0, 10**15)
    opens = [to_ms(b.open_ts) for b in bars]
    assert opens[-1] == to_ms(dt(2026, 12, 1, 8, 58))
    assert opens == [opens[0] + 60000 * i for i in range(len(opens))], "gap not backfilled"
    after = dict(raw(e.db, "SELECT open_ms, written_ms FROM bars WHERE kind='last' AND tf='1m'"))
    assert all(after[o] == w for o, w in before)         # previously written rows untouched
    assert e.feed.stats()["conflicts"] == 0
    assert raw(e.db, "SELECT count(*) FROM gaps WHERE reason='conflict'")[0][0] == 0
    e.feed.backfill()                                     # idempotent
    assert len(e.store.query_range("last", BTC, "1m", 0, 10**15)) == len(bars)


def test_grace_period_example1(tmp_path):
    e = make_env(tmp_path, T_START, pairs=(BTC,))
    e.feed.start()
    assert e.store.last_open_ms("last", BTC, "1m") == to_ms(dt(2026, 12, 1, 8, 58))
    e.clock.set_time(dt(2026, 12, 1, 9, 0, 2))
    n = len(e.srv.kline_calls("1m"))
    e.feed.run_once()
    assert len(e.srv.kline_calls("1m")) == n, "must not poll before close + grace_s"
    assert e.store.last_open_ms("last", BTC, "1m") == to_ms(dt(2026, 12, 1, 8, 58))
    e.clock.set_time(dt(2026, 12, 1, 9, 0, 3))
    e.feed.run_once()
    assert e.store.last_open_ms("last", BTC, "1m") == to_ms(dt(2026, 12, 1, 8, 59))   # 09:00 row is open: dropped
    assert e.store.last_open_ms("mark", BTC, "1m") == to_ms(dt(2026, 12, 1, 8, 59))
    # tf closes at 09:00: 15m 08:45 and 1h 08:00 written, never mark for them
    assert e.store.last_open_ms("last", BTC, "15m") == to_ms(dt(2026, 12, 1, 8, 45))
    assert e.store.last_open_ms("last", BTC, "1h") == to_ms(dt(2026, 12, 1, 8))
    assert e.store.last_open_ms("mark", BTC, "15m") is None and e.store.last_open_ms("mark", BTC, "1h") is None


def test_agg_mismatch_example2_rest_bar_wins(tmp_path):
    e = make_env(tmp_path, T_START, pairs=(BTC,))
    t8 = to_ms(dt(2026, 12, 1, 8))
    true_h = e.srv.agg("1h", t8)[1]
    e.srv.hover[("BTCUSDT", "1h", t8)] = 0.01
    e.feed.start()
    e.clock.set_time(dt(2026, 12, 1, 9, 0, 3))
    e.feed.run_once()
    stored = [b for b in e.store.query_range("last", BTC, "1h", t8, t8 + 1)]
    assert len(stored) == 1 and stored[0].h == pytest.approx(true_h + 0.01)
    assert (t8, "agg_mismatch") in e.store.gaps_in(BTC, "1h", *ALL_MS)
    assert e.feed.stats()["agg_mismatch"] >= 1
    # consistent data: no mismatch flagged for 15m bars
    assert not [g for g in e.store.gaps_in(BTC, "15m", *ALL_MS) if g[1] == "agg_mismatch"]


def test_agg_minute_missing_is_flagged_not_error(tmp_path):
    e = make_env(tmp_path, T_START, pairs=(BTC,))
    hole = to_ms(dt(2026, 12, 1, 8, 20))
    e.srv.omit.add(("BTCUSDT", "1m", hole))
    e.feed.start()
    e.clock.set_time(dt(2026, 12, 1, 9, 0, 3))
    e.feed.run_once()
    t8 = to_ms(dt(2026, 12, 1, 8))
    assert e.store.last_open_ms("last", BTC, "1h") == t8        # REST bar still valid
    assert (t8, "minute_missing") in e.store.gaps_in(BTC, "1h", *ALL_MS)


def test_conflict_from_rest_revision_keeps_old(tmp_path):
    e = make_env(tmp_path, T_START, pairs=(BTC,))
    e.feed.start()
    m858 = to_ms(dt(2026, 12, 1, 8, 58))
    orig = e.store.query_range("last", BTC, "1m", m858, m858 + 1)[0]
    e.srv.scale[("BTCUSDT", "1m", m858)] = 1.01
    e.clock.set_time(dt(2026, 12, 1, 9, 0, 3))
    e.feed.run_once()                          # self-heal fetch of last K=5 minutes re-reads 08:58
    now = e.store.query_range("last", BTC, "1m", m858, m858 + 1)[0]
    assert now == orig
    assert (m858, "conflict") in e.store.gaps_in(BTC, "1m", *ALL_MS)
    assert e.feed.stats()["conflicts"] >= 1


# =========================================================================== feed: errors, staleness, status
def test_one_pair_failing_does_not_stop_others_and_staleness_reported(tmp_path):
    e = make_env(tmp_path, T_START)
    e.feed.start()
    e.srv.inject.append(lambda path, p: Resp(500, {}) if p.get("symbol") == "ETHUSDT" and "klines" in path.lower() else None)
    e.clock.set_time(dt(2026, 12, 1, 9, 0, 3))
    e.feed.run_once()                                            # must not raise
    assert e.store.last_open_ms("last", BTC, "1m") == to_ms(dt(2026, 12, 1, 8, 59))
    assert e.store.last_open_ms("last", ETH, "1m") == to_ms(dt(2026, 12, 1, 8, 58)) or \
        e.store.last_open_ms("last", ETH, "1m") < to_ms(dt(2026, 12, 1, 8, 59))
    st = e.feed.stats()
    assert st["errors"] >= 1
    for k in ("requests", "gaps", "conflicts", "agg_mismatch", "last_ok"):
        assert k in st
    st_json = json.loads(Path(e.cfg.status_path).read_text())
    assert "server_offset_ms" in st_json
    assert e.store.meta_get(f"last_ok:{BTC}:1m:last") is not None
    assert e.store.meta_get(f"last_ok:{BTC}:1m:last") != e.store.meta_get(f"last_ok:{ETH}:1m:last")
    assert e.store.meta_get("server_offset_ms") is not None


def test_ban_418_sleeps_retry_after_and_does_not_crash(tmp_path):
    e = make_env(tmp_path, T_START, pairs=(BTC,))
    e.feed.start()
    e.srv.inject.append(lambda path, p: Resp(418, {"msg": "banned"}, {"Retry-After": "120"}) if "klines" in path.lower() else None)
    e.clock.set_time(dt(2026, 12, 1, 9, 0, 3))
    t_before = e.clock.now()
    e.feed.run_once()
    assert (e.clock.now() - t_before).total_seconds() >= 120
    assert e.store.last_open_ms("last", BTC, "1m") == to_ms(dt(2026, 12, 1, 8, 58))     # stale, nothing invented


def test_451_does_not_crash_and_writes_nothing_new(tmp_path):
    e = make_env(tmp_path, T_START, pairs=(BTC,))
    e.feed.start()
    e.srv.inject.append(lambda path, p: Resp(451, {"msg": "restricted location"}) if "klines" in path.lower() else None)
    e.clock.set_time(dt(2026, 12, 1, 9, 0, 3))
    e.feed.run_once()
    assert e.store.last_open_ms("last", BTC, "1m") == to_ms(dt(2026, 12, 1, 8, 58))


def test_six_consecutive_bans_exit_code_3(tmp_path):
    e = make_env(tmp_path, T_START, pairs=(BTC,))
    e.feed.start()
    n = [0]

    def inj(path, p):
        if "klines" in path.lower():
            n[0] += 1
            if n[0] > 2000:
                raise RuntimeError("runaway feed loop: never exited")
            return Resp(418, {}, {"Retry-After": "5"})
        return None

    e.srv.inject.append(inj)
    e.clock.set_time(dt(2026, 12, 1, 9, 0, 3))
    with pytest.raises(SystemExit) as ei:
        e.feed.run_forever()
    assert ei.value.code == 3


def test_three_consecutive_store_write_failures_exit(tmp_path):
    e = make_env(tmp_path, T_START, pairs=(BTC,))
    e.feed.start()

    def boom(*a, **k):
        raise DataError("disk full")

    e.store.put_bars = boom
    raised_at = None
    for i in range(3):
        e.clock.set_time(dt(2026, 12, 1, 9, 0, 3) + timedelta(minutes=i))
        try:
            e.feed.run_once()
        except SystemExit:
            raised_at = i
            break
    assert raised_at == 2, "must exit on 3rd consecutive failing turn"
    assert e.feed.stats()["errors"] >= 3


def test_clock_skew_over_5min_writes_no_bars(tmp_path):
    e = make_env(tmp_path, T_START, offset_s=400)
    try:
        e.feed.start()
        e.clock.set_time(dt(2026, 12, 1, 9, 0, 3))
        e.feed.run_once()
    except (ClockError, EngineError, SystemExit):
        pass
    assert raw(e.db, "SELECT count(*) FROM bars")[0][0] == 0


def test_server_offset_60s_filters_by_server_time(tmp_path, caplog):
    e = make_env(tmp_path, T_START, offset_s=90, pairs=(BTC,))
    e.feed.start()
    last = e.store.last_open_ms("last", BTC, "1m")
    assert last in (to_ms(dt(2026, 12, 1, 8, 59)), to_ms(dt(2026, 12, 1, 9, 0)))   # server now = 09:01:00 -> 09:01 bar still open
    for o, tf in raw(e.db, "SELECT open_ms, tf FROM bars"):
        assert o + int(tf_delta(tf).total_seconds() * 1000) <= e.srv.now_ms()
    off = int(float(e.store.meta_get("server_offset_ms")))
    assert abs(off - 90000) <= 1500
    assert any(r.levelname == "WARNING" for r in caplog.records)


def test_second_feed_cannot_take_lock(tmp_path):
    e = make_env(tmp_path, T_START, pairs=(BTC,))
    e.feed.start()
    f2 = Feed(e.cfg, e.rest, MarketStore(e.db), e.clock)
    with pytest.raises((SystemExit, EngineError, OSError)):
        f2.start()


def test_feed_modules_do_not_import_pandas():
    code = ("import sys, trader_engine.marketdata.store, trader_engine.marketdata.feed;"
            "assert 'pandas' not in sys.modules and 'numpy' not in sys.modules, sorted(m for m in sys.modules if m in ('pandas','numpy'))")
    env = dict(os.environ, PYTHONPATH=str(REPO / "src"))
    r = subprocess.run([sys.executable, "-c", code], env=env, capture_output=True, text=True)
    assert r.returncode == 0, r.stderr


def test_snapshot_rules_store_and_json_and_skips_bad_pair(tmp_path):
    e = make_env(tmp_path, T_START)
    out = tmp_path / "hist" / "rules.json"
    res = snapshot_rules(e.rest, [BTC, ETH, "XRP/USDT"], e.clock, store=e.store, out_json_path=str(out))
    assert set(res) >= {BTC, ETH} and "XRP/USDT" not in res
    info = e.srv.get("https://fapi.binance.com/fapi/v1/exchangeInfo").json()
    assert res[BTC] == spec_to_json(extract_rules(info, "BTCUSDT"))
    assert e.store.get_rules(BTC)[0] == res[BTC] and e.store.get_rules(ETH) is not None
    assert e.store.get_rules("XRP/USDT") is None
    on_disk = json.loads(out.read_text())
    assert spec_from_json(on_disk[BTC]) == extract_rules(info, "BTCUSDT")


# =========================================================================== PublicRestClient backoff (spec 5.5 / 07)
class Script:
    def __init__(self, *resps):
        self.resps, self.calls = list(resps), 0

    def get(self, url, params=None, timeout=None):
        self.calls += 1
        r = self.resps.pop(0) if len(self.resps) > 1 else self.resps[0]
        if isinstance(r, Exception):
            raise r
        return r


def client(sess, max_attempts=5, **kw):
    sl = []
    return PublicRestClient(session=sess, now_s=lambda: 0.0, sleep=sl.append, max_attempts=max_attempts, **kw), sl


def test_5xx_exponential_backoff_then_success():
    c, sl = client(Script(Resp(500), Resp(502), Resp(503), Resp(200, {"serverTime": 5})))
    assert c.server_time_ms() == 5
    assert sl == [2, 4, 8]


def test_5xx_exhausts_attempts_and_raises_never_silent():
    s = Script(Resp(500))
    c, sl = client(s, max_attempts=3)
    with pytest.raises(ExchangeError):
        c.get("/fapi/v1/time")
    assert s.calls == 3 and sl[:2] == [2, 4]


def test_429_honours_retry_after_then_succeeds():
    c, sl = client(Script(Resp(429, {}, {"Retry-After": "7"}), Resp(200, {"ok": 1})))
    assert c.get("/x") == {"ok": 1}
    assert sl == [7]


def test_429_total_wait_ceiling_raises_ban():
    c, sl = client(Script(Resp(429, {}, {"Retry-After": "200"})), max_attempts=10)
    with pytest.raises(ExchangeBan) as ei:
        c.get("/x")
    assert ei.value.http == 429 and sum(sl) <= 300


@pytest.mark.parametrize("code", [418, 451])
def test_418_451_never_retried(code):
    s = Script(Resp(code, {}, {"Retry-After": "30"}))
    c, sl = client(s)
    with pytest.raises(ExchangeBan) as ei:
        c.get("/x")
    assert ei.value.http == code and s.calls == 1 and sl == []


def test_network_error_backoff_and_raise():
    s = Script(ConnectionError("x"))
    c, sl = client(s, max_attempts=2)
    with pytest.raises(ExchangeError):
        c.get("/x")
    assert s.calls == 2 and sl == [2, 4]


def test_weight_threshold_waits_for_minute():
    s = Script(Resp(200, {"a": 1}, {"X-MBX-USED-WEIGHT-1M": "1900"}))
    c, sl = client(s)
    c.get("/x")
    c.get("/x")
    assert sl and sl[0] >= 1


# =========================================================================== sources
pd = pytest.importorskip("pandas")
pytest.importorskip("pyarrow")
import pandas.testing as pdt  # noqa: E402

from trader_engine.marketdata.sources import HistoricalSource, StoreSource  # noqa: E402

D0 = dt(2026, 11, 10)
NMIN = 720


def _agg(df, tf):
    g = df.groupby(df.index.floor({"15m": "15min", "1h": "1h", "4h": "4h"}[tf]))
    out = g.agg(open=("open", "first"), high=("high", "max"), low=("low", "min"), close=("close", "last"), volume=("volume", "sum"))
    out.index.name = "date"
    return out


def make_frames():
    idx = pd.DatetimeIndex([D0 + timedelta(minutes=i) for i in range(NMIN)], name="date")
    rows = [_minute(i + to_ms(D0) // 60000) for i in range(NMIN)]
    m1 = pd.DataFrame({"open": [r[0] for r in rows], "high": [r[1] for r in rows], "low": [r[2] for r in rows],
                       "close": [r[3] for r in rows], "volume": [r[4] for r in rows]}, index=idx)
    mrows = [_mark_minute(i + to_ms(D0) // 60000) for i in range(NMIN)]
    mk1 = pd.DataFrame({"open": [r[0] for r in mrows], "high": [r[1] for r in mrows], "low": [r[2] for r in mrows],
                        "close": [r[3] for r in mrows], "volume": 0.0}, index=idx)
    return {"1m": m1, "15m": _agg(m1, "15m"), "1h": _agg(m1, "1h"), "mark1m": mk1, "mark1h": _agg(mk1, "1h")}


def write_feather(path, df):
    d = df.reset_index()
    d["date"] = pd.to_datetime(d["date"], utc=True)
    d.to_feather(str(path), compression="uncompressed")


FUND_TS = [dt(2026, 11, 10, 0), dt(2026, 11, 10, 8)]


def write_history(hd, frames, *, with1m=True, drop_minute=None):
    hd.mkdir(parents=True, exist_ok=True)
    stem = pair_stem(BTC)
    assert stem == "BTC_USDT_USDT"
    m1, mk1 = frames["1m"], frames["mark1m"]
    if drop_minute is not None:
        m1 = m1.drop(index=pd.Timestamp(drop_minute))
    if with1m:
        write_feather(hd / f"{stem}-1m-futures.feather", m1)
        write_feather(hd / f"{stem}-1m-mark.feather", mk1)
    write_feather(hd / f"{stem}-15m-futures.feather", frames["15m"])
    write_feather(hd / f"{stem}-1h-futures.feather", frames["1h"])
    write_feather(hd / f"{stem}-1h-mark.feather", frames["mark1h"])
    fd = pd.DataFrame({"date": pd.to_datetime(FUND_TS, utc=True), "funding_rate": [0.0001, -0.0002]})
    fd.to_feather(str(hd / f"{stem}-1h-funding_rate.feather"))
    (hd / "rules.json").write_text(json.dumps({BTC: spec_to_json(extract_rules({"symbols": [FakeBinance._sym("BTCUSDT")]}, "BTCUSDT"))}))
    return m1


def fill_store(db, frames, drop_minute=None):
    s = MarketStore(db)
    m1 = frames["1m"] if drop_minute is None else frames["1m"].drop(index=pd.Timestamp(drop_minute))

    def bars(df, kind, tf):
        return [Bar(BTC, kind, tf, ts.to_pydatetime(), r.open, r.high, r.low, r.close, 0.0 if kind == "mark" else r.volume)
                for ts, r in df.iterrows()]
    for df, kind, tf in ((m1, "last", "1m"), (frames["mark1m"], "mark", "1m"), (frames["15m"], "last", "15m"),
                         (frames["1h"], "last", "1h")):
        res = s.put_bars(bars(df, kind, tf), now_ms=1)
        assert res.conflicts == 0 and res.inserted == len(df)
    mark_at = {FUND_TS[0]: frames["mark1m"].loc[pd.Timestamp(FUND_TS[0]), "open"],
               FUND_TS[1]: frames["mark1m"].loc[pd.Timestamp(FUND_TS[1]), "open"]}
    s.put_funding([FundingPoint(BTC, FUND_TS[0], 0.0001, mark_at[FUND_TS[0]]), FundingPoint(BTC, FUND_TS[1], -0.0002, mark_at[FUND_TS[1]])])
    s.put_rules(BTC, spec_to_json(extract_rules({"symbols": [FakeBinance._sym("BTCUSDT")]}, "BTCUSDT")), 1)
    s.close()


@pytest.fixture
def srcs(tmp_path):
    frames = make_frames()
    write_history(tmp_path / "hist", frames)
    db = str(tmp_path / "m.sqlite")
    fill_store(db, frames)
    return frames, StoreSource(db), HistoricalSource(str(tmp_path / "hist")), tmp_path


def test_real_freqtrade_file_naming_present():
    d = REPO / "user_data" / "data" / "binance" / "futures"
    if not d.is_dir():
        pytest.skip("no real data dir")
    stem = pair_stem(BTC)
    for name in (f"{stem}-1h-futures.feather", f"{stem}-1h-mark.feather", f"{stem}-1h-funding_rate.feather", f"{stem}-15m-futures.feather"):
        assert (d / name).exists(), name


def test_store_source_example3_4h_until_boundaries(tmp_path):
    db = str(tmp_path / "m.sqlite")
    s = MarketStore(db)
    s.put_bars([mk(BTC, "last", "4h", dt(2026, 12, 1, h)) for h in (0, 4, 8)], now_ms=1)
    src = StoreSource(db)
    df = src.bars(BTC, "4h", dt(2026, 12, 1, 11, 59, 59))
    assert df.index[-1] == pd.Timestamp(dt(2026, 12, 1, 4)) and len(df) == 2
    assert src.bars(BTC, "4h", dt(2026, 12, 1, 12)).index[-1] == pd.Timestamp(dt(2026, 12, 1, 8))
    assert len(src.bars(BTC, "4h", dt(2026, 12, 1, 12), n=2)) == 2


def test_dataframe_shape_and_kind_rules(srcs):
    frames, ss, hs, _ = srcs
    for src in (ss, hs):
        df = src.bars(BTC, "15m", D0 + timedelta(hours=3))
        assert list(df.columns) == ["open", "high", "low", "close", "volume"]
        assert df.index.name == "date" and str(df.index.tz) == "UTC"
        assert len(df) == 12 and df.index[0] == pd.Timestamp(D0)
        assert all(str(t) == "float64" for t in df.dtypes)
        assert len(src.bars(BTC, "15m", D0 + timedelta(hours=3), n=5)) == 5
        mk1 = src.bars(BTC, "1m", D0 + timedelta(minutes=10), kind="mark")
        assert len(mk1) == 10 and (mk1["volume"] == 0).all()
        with pytest.raises(DataError):
            src.bars(BTC, "1h", D0 + timedelta(hours=5), kind="mark")


def test_store_and_historical_return_identical_frames(srcs):
    frames, ss, hs, _ = srcs
    for tf in ("1m", "15m", "1h"):
        for until in (D0 + timedelta(hours=7), D0 + timedelta(hours=7, minutes=22, seconds=13)):
            for n in (None, 9):
                pdt.assert_frame_equal(ss.bars(BTC, tf, until, n), hs.bars(BTC, tf, until, n), check_freq=False)
    pdt.assert_frame_equal(ss.bars(BTC, "1m", D0 + timedelta(hours=2), kind="mark"),
                           hs.bars(BTC, "1m", D0 + timedelta(hours=2), kind="mark"), check_freq=False)
    # values equal the source frames
    got = hs.bars(BTC, "1h", D0 + timedelta(hours=12))
    assert got["high"].tolist() == frames["1h"]["high"].tolist()


def test_store_and_historical_minute_steps_funding_rules_equal(srcs):
    _, ss, hs, _ = srcs
    a = list(ss.minute_steps([BTC], D0 + timedelta(hours=1), D0 + timedelta(hours=1, minutes=30)))
    b = list(hs.minute_steps([BTC], D0 + timedelta(hours=1), D0 + timedelta(hours=1, minutes=30)))
    assert len(a) == 30 == len(b)
    assert [x.ts for x in a] == [D0 + timedelta(hours=1, minutes=i) for i in range(30)]
    for x, y in zip(a, b):
        assert x.ts == y.ts and x.bars == y.bars
        mb = x.bars[BTC]
        assert mb.step_s == 60 and mb.open_ts == x.ts and mb.mark_o is not None and mb.last_o > 0
    assert ss.funding(BTC, D0 - timedelta(hours=1), D0 + timedelta(hours=12)) == hs.funding(BTC, D0 - timedelta(hours=1), D0 + timedelta(hours=12))
    assert ss.rules(BTC) == hs.rules(BTC) == to_symbol_rules(BTC, extract_rules({"symbols": [FakeBinance._sym("BTCUSDT")]}, "BTCUSDT"))
    assert ss.last_closed_minute(BTC) == hs.last_closed_minute(BTC) == D0 + timedelta(minutes=NMIN - 1)
    assert ss.data_range(BTC, "1m") == hs.data_range(BTC, "1m") == (D0, D0 + timedelta(minutes=NMIN - 1))
    assert ss.step_seconds() == hs.step_seconds() == 60


def test_minute_steps_half_open_and_missing_mark(tmp_path):
    db = str(tmp_path / "m.sqlite")
    s = MarketStore(db)
    t = dt(2026, 12, 1, 9)
    s.put_bars([mk(BTC, "last", "1m", t + timedelta(minutes=i)) for i in range(4)] +
               [mk(ETH, "last", "1m", t + timedelta(minutes=1)), mk(BTC, "mark", "1m", t)], now_ms=1)
    steps = list(StoreSource(db).minute_steps([BTC, ETH], t, t + timedelta(minutes=3)))
    assert [x.ts for x in steps] == [t, t + timedelta(minutes=1), t + timedelta(minutes=2)]   # end exclusive
    assert set(steps[0].bars) == {BTC} and set(steps[1].bars) == {BTC, ETH}
    assert steps[0].bars[BTC].mark_o == 100.0 and steps[1].bars[BTC].mark_o is None and steps[1].bars[BTC].mark_c is None


def test_contiguous_tail_and_gaps_attr(tmp_path):
    frames = make_frames()
    hole = D0 + timedelta(minutes=100)
    write_history(tmp_path / "hist", frames, drop_minute=hole)
    db = str(tmp_path / "m.sqlite")
    fill_store(db, frames, drop_minute=hole)
    until = D0 + timedelta(minutes=NMIN)
    for src in (StoreSource(db), HistoricalSource(str(tmp_path / "hist"))):
        assert src.contiguous_tail(BTC, "1m", until) == NMIN - 101
        assert src.contiguous_tail(BTC, "1m", D0 + timedelta(minutes=50)) == 50
    df = StoreSource(db).bars(BTC, "1m", until, n=NMIN)
    assert to_ms(hole) in df.attrs["gaps"]


def test_funding_window_example4_and_mark_source(tmp_path):
    frames = make_frames()
    hd = tmp_path / "hist"
    write_history(hd, frames)
    stem = pair_stem(BTC)
    # funding file spanning 2026-10-31 08:00 / 16:00 / 24:00 against 1h mark only
    t8, t16 = dt(2026, 10, 31, 8), dt(2026, 10, 31, 16)
    idx = pd.DatetimeIndex([dt(2026, 10, 31, h) for h in range(24)], name="date")
    mk1h = pd.DataFrame({"open": [200.0 + h for h in range(24)], "high": 300.0, "low": 100.0, "close": 250.0, "volume": 0.0}, index=idx)
    h2 = tmp_path / "hist2"
    h2.mkdir()
    write_feather(h2 / f"{stem}-1h-mark.feather", mk1h)
    write_feather(h2 / f"{stem}-1h-futures.feather", mk1h)
    write_feather(h2 / f"{stem}-15m-futures.feather", mk1h)
    pd.DataFrame({"date": pd.to_datetime([dt(2026, 10, 31, 0), t8, t16], utc=True),
                  "funding_rate": [0.1, 0.2, 0.3]}).to_feather(str(h2 / f"{stem}-1h-funding_rate.feather"))
    hs = HistoricalSource(str(h2), granularity="15m")
    pts = hs.funding(BTC, t8, t16)
    assert [(p.ts, p.rate) for p in pts] == [(t16, 0.3)]
    assert pts[0].mark == 216.0                       # 1h mark open at 16:00 (no 1m mark file)
    assert hs.funding(BTC, dt(2026, 11, 5), dt(2026, 11, 6)) == []     # outside file range: empty, nothing invented
    # with 1m mark present, mark = that minute's open
    hs2 = HistoricalSource(str(hd))
    p = hs2.funding(BTC, FUND_TS[0], FUND_TS[1])
    assert len(p) == 1 and p[0].ts == FUND_TS[1] and p[0].mark == frames["mark1m"].loc[pd.Timestamp(FUND_TS[1]), "open"]


def test_historical_coarse_mode(tmp_path):
    frames = make_frames()
    write_history(tmp_path / "hist", frames, with1m=False)
    hs = HistoricalSource(str(tmp_path / "hist"), granularity="15m")
    assert hs.step_seconds() == 900
    steps = list(hs.minute_steps([BTC], D0, D0 + timedelta(hours=1)))
    assert [x.ts for x in steps] == [D0 + timedelta(minutes=15 * i) for i in range(4)]
    b = steps[1].bars[BTC]
    assert b.step_s == 900 and b.mark_o is None and b.mark_c is None
    assert b.last_o == frames["15m"].iloc[1]["open"] and b.last_c == frames["15m"].iloc[1]["close"]
    assert hs.last_closed_minute(BTC) == D0 + timedelta(minutes=15 * 47)
    assert hs.open_at(BTC, D0 + timedelta(minutes=30)) == frames["15m"].iloc[2]["open"]
    with pytest.raises(DataError):
        hs.open_at(BTC, D0 + timedelta(minutes=7))


def test_native_mode_without_1m_files_is_data_error_no_silent_fallback(tmp_path):
    frames = make_frames()
    write_history(tmp_path / "hist", frames, with1m=False)
    with pytest.raises(DataError):
        hs = HistoricalSource(str(tmp_path / "hist"))
        list(hs.minute_steps([BTC], D0, D0 + timedelta(hours=1)))
    with pytest.raises(DataError):
        HistoricalSource(str(tmp_path / "hist")).bars(BTC, "1m", D0 + timedelta(hours=1))


def test_historical_open_at_native(srcs):
    frames, _, hs, _ = srcs
    assert hs.open_at(BTC, D0 + timedelta(minutes=5)) == frames["1m"].iloc[5]["open"]
    with pytest.raises(DataError):
        hs.open_at(BTC, D0 + timedelta(minutes=5, seconds=1))


def test_no_data_invented_beyond_file_end(srcs):
    frames, ss, hs, _ = srcs
    far = D0 + timedelta(days=30)
    for src in (ss, hs):
        df = src.bars(BTC, "1m", far)
        assert len(df) == NMIN and df.index[-1] == pd.Timestamp(D0 + timedelta(minutes=NMIN - 1))
        assert len(list(src.minute_steps([BTC], D0, far))) == NMIN
        assert src.bars(BTC, "1m", D0 - timedelta(days=1)).empty


def test_historical_rules_missing_and_synthetic(tmp_path):
    frames = make_frames()
    hd = tmp_path / "hist"
    write_history(hd, frames)
    (hd / "rules.json").unlink()
    with pytest.raises(DataError):
        HistoricalSource(str(hd)).rules(BTC)
    # synthetic rules: prices with 2 decimals, volumes with 3 -> tick 0.01, step 0.001
    n = 300
    idx = pd.DatetimeIndex([D0 + timedelta(hours=i) for i in range(n)], name="date")
    df = pd.DataFrame({"open": [100.25 + (i % 7) for i in range(n)], "high": [105.5 + (i % 7) for i in range(n)],
                       "low": [99.75 + (i % 7) for i in range(n)], "close": [101.0 + (i % 7) for i in range(n)],
                       "volume": [12.345 + (i % 5) for i in range(n)]}, index=idx)
    h3 = tmp_path / "h3"
    h3.mkdir()
    write_feather(h3 / "BTC_USDT_USDT-1h-futures.feather", df)
    r = HistoricalSource(str(h3), granularity="15m", synthetic_rules=True).rules(BTC)
    assert r.tick == pytest.approx(0.01) and r.step == pytest.approx(0.001)
    assert r.min_notional == 5.0 and r.min_qty == pytest.approx(r.step) and r.max_qty == 1e12


@pytest.mark.parametrize("mode", ["garbage", "missing_column"])
def test_corrupt_feather_fails_closed(tmp_path, mode):
    frames = make_frames()
    hd = tmp_path / "hist"
    write_history(hd, frames)
    p = hd / "BTC_USDT_USDT-15m-futures.feather"
    if mode == "garbage":
        p.write_bytes(b"not an arrow file at all" * 100)
    else:
        d = frames["15m"].reset_index().drop(columns=["close"])
        d.to_feather(str(p))
    with pytest.raises(DataError):
        HistoricalSource(str(hd)).bars(BTC, "15m", D0 + timedelta(hours=3))


def test_store_source_missing_rules_and_corrupt_db_fail_closed(tmp_path):
    db = str(tmp_path / "m.sqlite")
    MarketStore(db).close()
    with pytest.raises(DataError):
        StoreSource(db).rules(BTC)
    bad = tmp_path / "bad.sqlite"
    bad.write_bytes(os.urandom(4096))
    with pytest.raises((DataError, sqlite3.DatabaseError)):
        StoreSource(str(bad)).bars(BTC, "1m", D0)


# =========================================================================== no-lookahead property
@pytest.mark.parametrize("seed", range(5))
def test_no_lookahead_bars_never_closed_after_until(srcs, seed):
    _, ss, hs, _ = srcs
    rng = random.Random(seed)
    for _ in range(25):
        until = D0 + timedelta(seconds=rng.randint(-600, NMIN * 60 + 600), milliseconds=rng.choice([0, 1, 999]))
        for src in (ss, hs):
            for tf in ("1m", "15m", "1h"):
                df = src.bars(BTC, tf, until)
                if len(df):
                    assert (df.index + pd.Timedelta(tf_delta(tf)) <= pd.Timestamp(until)).all(), (tf, until)
        steps = list(hs.minute_steps([BTC], D0, until)) if until > D0 else []
        assert all(x.ts < until for x in steps)


def test_reads_up_to_t_identical_when_future_data_removed(tmp_path):
    frames = make_frames()
    t = D0 + timedelta(hours=5, minutes=30)
    full_h, cut_h = tmp_path / "full", tmp_path / "cut"
    write_history(full_h, frames)
    cut = {k: v[v.index < pd.Timestamp(t)] for k, v in frames.items()}
    cut["15m"], cut["1h"] = cut["15m"][cut["15m"].index < pd.Timestamp(t)], cut["1h"][cut["1h"].index < pd.Timestamp(t)]
    write_history(cut_h, cut)
    dbf, dbc = str(tmp_path / "f.sqlite"), str(tmp_path / "c.sqlite")
    fill_store(dbf, frames)
    s = MarketStore(dbc)
    for tf in ("1m", "15m", "1h"):
        s.put_bars([Bar(BTC, "last", tf, ts.to_pydatetime(), r.open, r.high, r.low, r.close, r.volume) for ts, r in cut[tf].iterrows()], now_ms=1)
    s.put_bars([Bar(BTC, "mark", "1m", ts.to_pydatetime(), r.open, r.high, r.low, r.close, 0.0) for ts, r in cut["mark1m"].iterrows()], now_ms=1)
    s.close()
    pairs = [(StoreSource(dbf), StoreSource(dbc)), (HistoricalSource(str(full_h)), HistoricalSource(str(cut_h)))]
    for a, b in pairs:
        for tf in ("1m", "15m", "1h"):
            pdt.assert_frame_equal(a.bars(BTC, tf, t, 50), b.bars(BTC, tf, t, 50), check_freq=False)
        pdt.assert_frame_equal(a.bars(BTC, "1m", t, kind="mark"), b.bars(BTC, "1m", t, kind="mark"), check_freq=False)
        assert [(x.ts, x.bars) for x in a.minute_steps([BTC], D0, t)] == [(x.ts, x.bars) for x in b.minute_steps([BTC], D0, t)]
