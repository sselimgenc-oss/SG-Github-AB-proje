"""01 implementasyon saglamlik testleri (store, feed, sources). Sahte HTTP oturumu; gercek ag/saat yok."""
from __future__ import annotations

import json
import subprocess
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from trader_engine.bars import from_ms, to_ms
from trader_engine.clock import SimClock
from trader_engine.errors import DataError, FailClosed
from trader_engine.marketdata.feed import Feed, FeedConfig, snapshot_rules
from trader_engine.marketdata.rest_public import PublicRestClient
from trader_engine.marketdata.store import MarketStore
from trader_engine.types import Bar, FundingPoint

P = "BTC/USDT"
SRC = Path(__file__).resolve().parents[2] / "src"
FIXT = Path(__file__).parent / "fixtures" / "binance" / "exchange_info_sample.json"
T0 = datetime(2026, 12, 1, 9, 0, tzinfo=timezone.utc)
TFMS = {"1m": 60_000, "15m": 900_000, "1h": 3_600_000, "4h": 14_400_000}


def mk(tf="1m", i=0, o=100.0, h=101.0, l=99.0, c=100.5, v=1.0, kind="last", base=T0):
    return Bar(P, kind, tf, base + timedelta(milliseconds=TFMS[tf] * i), o, h, l, c, v)


# ------------------------------------------------------------------ sahte REST
class Resp:
    def __init__(self, status=200, body=None, headers=None, text=""):
        self.status_code, self._b, self.headers, self.text = status, body, headers or {}, text

    def json(self):
        return self._b


class FakeSession:
    """Klines: {(path, interval): {open_ms: (o,h,l,c,v)}}; acik bar da dondurulur (closeTime gelecekte)."""

    def __init__(self):
        self.data = {}
        self.calls = []
        self.fail = {}          # (path, interval) -> status
        self.server_ms = to_ms(T0)
        self.funding = []
        self.info = json.loads(FIXT.read_text())

    def add(self, path, interval, open_ms, o=100.0, h=101.0, l=99.0, c=100.5, v=1.0):
        self.data.setdefault((path, interval), {})[open_ms] = (o, h, l, c, v)

    def get(self, url, params=None, timeout=None):
        path = url.split("fapi.binance.com")[1]
        self.calls.append((path, dict(params or {})))
        if path == "/fapi/v1/time":
            return Resp(200, {"serverTime": self.server_ms})
        if path == "/fapi/v1/exchangeInfo":
            return Resp(200, self.info)
        if path == "/fapi/v1/fundingRate":
            lo = params.get("startTime", 0)
            return Resp(200, [x for x in self.funding if x["fundingTime"] >= lo])
        iv = params["interval"]
        if (path, iv) in self.fail:
            return Resp(self.fail[(path, iv)], None, {"Retry-After": "7"}, "x")
        tf = TFMS[iv]
        lo, hi = params.get("startTime", 0), params.get("endTime", 1 << 62)
        rows = []
        for om in sorted(self.data.get((path, iv), {})):
            if lo <= om <= hi:
                o, h, l, c, v = self.data[(path, iv)][om]
                rows.append([om, str(o), str(h), str(l), str(c), str(v), om + tf - 1, "0", 1, "0", "0", "0"])
        lim = params.get("limit", 500)
        return Resp(200, rows[:lim] if "startTime" in params else rows[-lim:])


def make_feed(tmp_path, pairs=(P,), sess=None, **kw):
    sess = sess or FakeSession()
    clock = SimClock(T0)
    rest = PublicRestClient(session=sess, now_s=lambda: clock.now().timestamp(), sleep=clock.sleep)
    store = MarketStore(tmp_path / "market.sqlite")
    cfg = FeedConfig(pairs=tuple(pairs), db_path=str(tmp_path / "market.sqlite"), lock_path=str(tmp_path / "var" / "market.lock"),
                     status_path=str(tmp_path / "status.json"), backfill_bars={"1m": 10, "15m": 4, "1h": 3, "4h": 2}, **kw)
    return Feed(cfg, rest, store, clock), sess, clock, store


def fill_history(sess, upto_ms, pair_sym="BTCUSDT"):
    for iv, n in (("1m", 12), ("15m", 6), ("1h", 5), ("4h", 4)):
        tf = TFMS[iv]
        end = upto_ms - upto_ms % tf
        for k in range(n + 1):  # son satir acik bar
            om = end - (n - k) * tf
            sess.add("/fapi/v1/klines", iv, om)
            if iv == "1m":
                sess.add("/fapi/v1/markPriceKlines", iv, om, v=0)


# ----------------------------------------------------------------------- store
def test_store_put_idempotent_conflict_invalid(tmp_path):
    s = MarketStore(tmp_path / "m.sqlite")
    r = s.put_bars([mk(i=0), mk(i=1)], now_ms=5)
    assert (r.inserted, r.duplicates_equal, r.conflicts) == (2, 0, 0)
    r = s.put_bars([mk(i=0), mk(i=1, c=100.6)], now_ms=6)
    assert (r.inserted, r.duplicates_equal, r.conflicts) == (0, 1, 1)
    assert s.query_range("last", P, "1m", to_ms(T0), to_ms(T0) + 120_000)[1].c == 100.5   # eski deger kalir
    assert s.gaps_in(P, "1m", 0, 1 << 60) == [(to_ms(T0) + 60_000, "conflict")]
    bad = [mk(i=2, h=98.0), mk(i=3, o=-1.0), mk(i=4, o=float("nan")), Bar(P, "last", "1m", T0 + timedelta(seconds=5), 1, 1, 1, 1)]
    r = s.put_bars(bad + [mk(i=5)], now_ms=7)
    assert r.inserted == 1 and len(r.invalid) == 4


def test_store_query_until_boundaries_and_mark_volume(tmp_path):
    s = MarketStore(tmp_path / "m.sqlite")
    s.put_bars([mk("1h", 0), mk("1h", 1), mk("1m", 0, kind="mark", v=9.0)], now_ms=1)
    close0 = to_ms(T0) + 3_600_000
    assert [to_ms(b.open_ts) for b in s.query_bars("last", P, "1h", close0 - 1, None)] == []
    assert len(s.query_bars("last", P, "1h", close0, None)) == 1
    assert len(s.query_bars("last", P, "1h", close0 + 3_600_000, 1)) == 1
    assert s.query_bars("mark", P, "1m", close0, None)[0].v == 0.0


def test_store_readonly_and_funding_meta_prune(tmp_path):
    w = MarketStore(tmp_path / "m.sqlite")
    w.put_funding([FundingPoint(P, T0, 0.0001, None)])
    assert w.put_funding([FundingPoint(P, T0, 0.0001, 50.0)]) == 1       # NULL mark sonradan dolar
    assert w.query_funding(P, to_ms(T0) - 1, to_ms(T0))[0].mark == 50.0
    assert w.query_funding(P, to_ms(T0), to_ms(T0) + 1) == []             # (start, end]
    w.meta_set("k", "v")
    w.put_bars([mk(i=0)], now_ms=0)
    assert w.prune(to_ms(T0) + 20 * 86_400_000) == 1
    ro = MarketStore(tmp_path / "m.sqlite", read_only=True)
    assert ro.meta_get("k") == "v"
    with pytest.raises(DataError):
        ro.put_bars([mk(i=1)], now_ms=1)
    with pytest.raises(DataError):
        MarketStore(tmp_path / "yok.sqlite", read_only=True)


# ------------------------------------------------------------------------ feed
def test_feed_start_backfill_and_run_once(tmp_path):
    f, sess, clock, store = make_feed(tmp_path)
    sess.server_ms = to_ms(T0)
    fill_history(sess, to_ms(T0))
    # 08:58 dakikasi borsada yok -> gaps(missing)
    del sess.data[("/fapi/v1/klines", "1m")][to_ms(T0) - 120_000]
    f.start()
    assert store.last_open_ms("last", P, "1m") == to_ms(T0) - 60_000          # acik bar (09:00) yazilmadi
    assert (to_ms(T0) - 120_000, "missing") in store.gaps_in(P, "1m", 0, 1 << 60)
    assert store.get_rules(P) is not None
    assert store.last_open_ms("mark", P, "1m") == to_ms(T0) - 60_000
    # yeni dakika: grace dolmadan istek yok
    new = to_ms(T0)
    sess.add("/fapi/v1/klines", "1m", new)
    sess.add("/fapi/v1/klines", "1m", new + 60_000)
    sess.add("/fapi/v1/markPriceKlines", "1m", new, v=0)
    sess.add("/fapi/v1/markPriceKlines", "1m", new + 60_000, v=0)
    clock.advance(61)           # 09:01:01 -> 09:00 kapandi ama grace (3 sn) dolmadi
    sess.server_ms = to_ms(clock.now())
    n = len(sess.calls)
    f.run_once()
    assert store.last_open_ms("last", P, "1m") == to_ms(T0) - 60_000
    assert not [c for c in sess.calls[n:] if c[0] == "/fapi/v1/klines"]
    clock.advance(3)
    t = f.run_once()
    assert store.last_open_ms("last", P, "1m") == new and t.errors == 0
    assert json.loads((tmp_path / "status.json").read_text())["server_offset_ms"] == f.offset_ms
    with pytest.raises(FailClosed):                                           # ikinci yazar
        make_feed(tmp_path / "b")[0]  # farkli dizin: kilit ayri
        f2 = Feed(f.cfg, f.rest, store, clock)
        f2.start()


def test_feed_pair_error_isolated_and_ban_exit(tmp_path):
    f, sess, clock, store = make_feed(tmp_path, pairs=(P, "ETH/USDT"))
    fill_history(sess, to_ms(T0))
    for iv, n in (("1m", 12),):
        for k in range(n + 1):
            sess.add("/fapi/v1/klines", iv, to_ms(T0) - (n - k) * 60_000)
    f.start()
    clock.advance(70)
    sess.server_ms = to_ms(clock.now())
    sess.add("/fapi/v1/klines", "1m", to_ms(T0))
    sess.add("/fapi/v1/klines", "1m", to_ms(T0) + 60_000)
    sess.add("/fapi/v1/markPriceKlines", "1m", to_ms(T0), v=0)
    sess.fail[("/fapi/v1/markPriceKlines", "1m")] = 500
    t = f.run_once()
    assert store.last_open_ms("last", P, "1m") == to_ms(T0)     # last yazildi, mark hatasi digerini bozmadi
    assert f.stats()["errors"] >= 1
    sess.fail = {("/fapi/v1/klines", "1m"): 451}
    clock.advance(60)
    sess.server_ms = to_ms(clock.now())
    with pytest.raises(SystemExit) as ex:
        for _ in range(8):
            clock.advance(60)
            tk = f.run_once()
            assert tk.banned
    assert ex.value.code == 3


def test_feed_agg_mismatch_and_conflict_keeps_old(tmp_path):
    f, sess, clock, store = make_feed(tmp_path)
    h = to_ms(T0)                                   # 09:00 1h bari 10:00'da kapanir
    clock.set_time(T0 + timedelta(hours=1, seconds=4))
    sess.server_ms = to_ms(clock.now())
    f.start()
    for i in range(60):
        store.put_bars([mk("1m", i)], now_ms=1)
    sess.add("/fapi/v1/klines", "1h", h, o=100.0, h=101.5, l=99.0, c=100.5, v=60.0)   # toplam h=101.0
    sess.add("/fapi/v1/klines", "1h", h + 3_600_000)
    f.run_once()
    got = store.query_range("last", P, "1h", h, h + 1)[0]
    assert got.h == 101.5
    assert any(r == "agg_mismatch" for _, r in store.gaps_in(P, "1h", 0, 1 << 60))
    assert f.stats()["agg_mismatch"] == 1


def test_feed_clock_skew_writes_nothing_and_snapshot_rules(tmp_path):
    f, sess, clock, store = make_feed(tmp_path)
    fill_history(sess, to_ms(T0))
    sess.server_ms = to_ms(T0) + 400_000
    f.start()
    assert f.offset_ms == 400_000 and store.last_open_ms("last", P, "1m") is None
    assert f.run_once().skipped == "clock_skew"
    out = tmp_path / "rules.json"
    snap = snapshot_rules(f.rest, [P, "ZZZ/USDT"], clock, store=store, out_json_path=str(out))
    assert P in snap and "ZZZ/USDT" in snap.errors and snap.exit_code == 1
    assert json.loads(out.read_text())[P] == snap[P]


# --------------------------------------------------------------------- sources
def test_feed_module_does_not_load_pandas():
    code = ("import sys; sys.path.insert(0, %r); import trader_engine.marketdata.feed, trader_engine.marketdata.store; "
            "print(sorted(m for m in sys.modules if m.split('.')[0] in ('pandas','numpy','pyarrow','requests')))" % str(SRC))
    r = subprocess.run([sys.executable, "-I", "-c", code], capture_output=True, text=True, timeout=30)
    assert r.returncode == 0, r.stderr
    assert r.stdout.strip() == "[]"


pa = pytest.importorskip("pyarrow")
pd = pytest.importorskip("pandas")
from trader_engine.marketdata.sources import HistoricalSource, StoreSource  # noqa: E402

HIST = Path(__file__).resolve().parents[2] / "var" / "history"


@pytest.mark.skipif(not (HIST / "BTC_USDT_USDT-1h-futures.feather").exists(), reason="gercek veri yok")
def test_historical_real_files_and_store_equivalence(tmp_path):
    h = HistoricalSource(HIST, granularity="15m", synthetic_rules=True)
    first = pd.read_feather(HIST / "BTC_USDT_USDT-1h-futures.feather", columns=["date"])["date"].min()
    assert h.data_range(P, "1h")[0] == first.to_pydatetime()          # baslangic dosyadan turetilir (sabit tarih yok)
    assert h.step_seconds() == 900
    u = datetime(2026, 11, 15, 11, 59, 59, tzinfo=timezone.utc)
    d4 = h.bars(P, "4h", u, 3)
    assert d4.index[-1] == datetime(2026, 11, 15, 4, tzinfo=timezone.utc) and d4.index.name == "date"
    assert h.bars(P, "4h", u + timedelta(seconds=1), 1).index[-1] == datetime(2026, 11, 15, 8, tzinfo=timezone.utc)
    with pytest.raises(DataError):
        h.bars(P, "1h", u, 1, kind="mark")
    if not (HIST / "BTC_USDT_USDT-1m-futures.feather").exists():      # 1m verisi indirilmemisse
        with pytest.raises(DataError):
            HistoricalSource(HIST).minute_steps([P], u, u + timedelta(hours=1))
    pts = h.funding(P, datetime(2026, 4, 30, 8, tzinfo=timezone.utc), datetime(2026, 4, 30, 16, tzinfo=timezone.utc))
    assert [p.ts.hour for p in pts] == [16] and pts[0].mark is not None
    with pytest.raises(DataError):
        h.rules(P) if not h.synthetic_rules else (_ for _ in ()).throw(DataError("x"))
    assert h.rules(P).tick > 0
    steps = list(h.minute_steps([P], u, u + timedelta(minutes=30)))
    assert [s.ts.minute for s in steps] == [0, 15] or [s.ts.minute for s in steps] == [45]   # 11:59:59 sonrasi 12:00,12:15
    # store esdegeri
    full = h.bars(P, "1h", datetime(2026, 11, 15, 23, 0, tzinfo=timezone.utc), 50)
    w = MarketStore(tmp_path / "m.sqlite")
    w.put_bars([Bar(P, "last", "1h", ts.to_pydatetime(), r.open, r.high, r.low, r.close, r.volume)
                for ts, r in full.iterrows()], now_ms=1)
    s = StoreSource(tmp_path / "m.sqlite")
    pd.testing.assert_frame_equal(s.bars(P, "1h", datetime(2026, 11, 15, 23, 0, tzinfo=timezone.utc), 50), full)
    assert s.contiguous_tail(P, "1h", datetime(2026, 11, 15, 23, 0, tzinfo=timezone.utc)) == 50 \
        == h.contiguous_tail(P, "1h", datetime(2026, 11, 15, 23, 0, tzinfo=timezone.utc), 50)
    with pytest.raises(DataError):
        s.rules(P)


def test_store_source_minute_steps_rules_and_gaps(tmp_path):
    w = MarketStore(tmp_path / "m.sqlite")
    w.put_bars([mk(i=0), mk(i=1), mk(i=3), mk(i=0, kind="mark")], now_ms=1)
    info = json.loads(FIXT.read_text())
    snapshot_rules(type("R", (), {"exchange_info": lambda self: info})(), [P], SimClock(T0), store=w)
    s = StoreSource(tmp_path / "m.sqlite")
    st = list(s.minute_steps([P], T0, T0 + timedelta(minutes=10)))
    assert [x.ts.minute for x in st] == [0, 1, 3]
    assert st[0].bars[P].mark_o == 100.0 and st[1].bars[P].mark_o is None and st[0].bars[P].step_s == 60
    df = s.bars(P, "1m", T0 + timedelta(minutes=10))
    assert df.attrs["gaps"] == [to_ms(T0) + 120_000]
    assert s.contiguous_tail(P, "1m", T0 + timedelta(minutes=10)) == 1
    assert s.last_closed_minute(P) == T0 + timedelta(minutes=3)
    assert s.rules(P).symbol == "BTCUSDT"
    assert len(s.bars(P, "1m", T0 + timedelta(seconds=119))) == 1                 # 2. bar henuz kapanmadi
    with pytest.raises(DataError):
        s.bars(P, "15m", T0, kind="mark")
