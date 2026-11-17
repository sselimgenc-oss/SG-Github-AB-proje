"""Motor tarafi veri okuyucular (01 §6): StoreSource (canli) ve HistoricalSource (feather). pandas burada serbest;
feed bu modulu import etmez. Saat okumaz; ileriye bakma yok (until zorunlu)."""
from __future__ import annotations

import json
import logging
import os
from collections.abc import Iterator, Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path
from typing import Protocol

import numpy as np
import pandas as pd

from trader_engine.bars import from_ms, to_ms
from trader_engine.errors import DataError
from trader_engine.exchange.rules import RulesError, spec_from_json, to_symbol_rules
from trader_engine.marketdata.store import TF_MS, MarketStore
from trader_engine.types import FundingPoint, Kind, MinuteBar, SymbolRules, canon_pair, pair_stem, pair_symbol, require_utc

log = logging.getLogger("engine.sources")

_COLS = ("open", "high", "low", "close", "volume")
_DAY_MS = 86_400_000


@dataclass(frozen=True)
class MinuteStep:
    ts: datetime
    bars: Mapping[str, MinuteBar]


class MarketView(Protocol):
    def bars(self, pair: str, tf: str, until: datetime, n: int | None = None, kind: Kind = "last") -> pd.DataFrame: ...
    def contiguous_tail(self, pair: str, tf: str, until: datetime, max_n: int = 5000) -> int: ...
    def minute_steps(self, pairs: Sequence[str], start: datetime, end: datetime) -> Iterator[MinuteStep]: ...
    def funding(self, pair: str, start: datetime, end: datetime) -> list[FundingPoint]: ...
    def rules(self, pair: str) -> SymbolRules: ...
    def last_closed_minute(self, pair: str) -> datetime | None: ...
    def data_range(self, pair: str, tf: str) -> tuple[datetime, datetime] | None: ...
    def step_seconds(self) -> int: ...


# ------------------------------------------------------------------ ortak yardimcilar
def _check_tf(tf: str) -> int:
    try:
        return TF_MS[tf]
    except (KeyError, TypeError):
        raise DataError(f"bilinmeyen tf: {tf!r}") from None


def _check_kind(kind: str, tf: str) -> None:
    if kind not in ("last", "mark"):
        raise DataError(f"gecersiz kind: {kind!r}")
    if kind == "mark" and tf != "1m":
        raise DataError("mark bari yalniz 1m icin tutulur")


def _utc(dt: datetime, name: str) -> datetime:
    try:
        return require_utc(dt, name)
    except ValueError as e:
        raise DataError(str(e)) from e


def _frame(ms, o, h, l, c, v) -> pd.DataFrame:
    idx = pd.DatetimeIndex(pd.to_datetime(np.asarray(ms, dtype="int64"), unit="ms", utc=True), name="date")
    return pd.DataFrame({"open": np.asarray(o, dtype="float64"), "high": np.asarray(h, dtype="float64"),
                         "low": np.asarray(l, dtype="float64"), "close": np.asarray(c, dtype="float64"),
                         "volume": np.asarray(v, dtype="float64")}, index=idx)


def _missing_opens(ms: Sequence[int], tf_ms: int) -> list[int]:
    out: list[int] = []
    for a, b in zip(ms[:-1], ms[1:]):
        t = a + tf_ms
        while t < b:
            out.append(int(t))
            t += tf_ms
    return out


def _tail_run(ms: Sequence[int], tf_ms: int) -> int:
    k = len(ms)
    if k == 0:
        return 0
    n = 1
    for i in range(k - 1, 0, -1):
        if ms[i] - ms[i - 1] != tf_ms:
            break
        n += 1
    return n


_HOLDOUT_START = datetime(2026, 5, 1, tzinfo=timezone.utc)
_SYNTH_MIN_NOTIONAL = {"BTC/USDT": 100.0, "ETH/USDT": 20.0}


def _step_dec(values) -> float:
    dec = 0
    for v in values:
        e = Decimal(repr(round(float(v), 10))).as_tuple().exponent
        dec = max(dec, -e)
    return 10.0 ** -min(dec, 8)


def decimals_of(values) -> int:
    """freqtrade `get_pair_precision`: her deger 10 ondaliga yuvarlanir, sonra ondalik hane sayisi (float repr'ine
    dayanikli; sondaki sifirlar sayilmaz); tum degerlerin en buyugu."""
    dec = 0
    for v in np.unique(np.round(np.asarray(values, dtype="float64"), 10)):
        e = Decimal(repr(float(v))).normalize().as_tuple().exponent
        dec = max(dec, -int(e))
    return dec


def monthly_ticks(ms: np.ndarray, o: np.ndarray, h: np.ndarray, l: np.ndarray, c: np.ndarray) -> dict[tuple[int, int], float]:
    """freqtrade `get_tick_size_over_time`: (yil, ay UTC) -> 10^-(OHLC ondalik hane sayisinin ayi icindeki en buyugu)."""
    out: dict[tuple[int, int], float] = {}
    if len(ms) == 0:
        return out
    mo = ms.astype("int64").astype("datetime64[ms]").astype("datetime64[M]")
    for m in np.unique(mo):
        k = mo == m
        dec = decimals_of(np.concatenate([o[k], h[k], l[k], c[k]]))
        y, mm = divmod(int(m.astype("int64")), 12)
        out[(1970 + y, mm + 1)] = float(Decimal(1).scaleb(-dec))
    return out


def _day_chunks(start_ms: int, end_ms: int) -> Iterator[tuple[int, int]]:
    cur = start_ms
    while cur < end_ms:
        nxt = min((cur // _DAY_MS + 1) * _DAY_MS, end_ms)
        yield cur, nxt
        cur = nxt


# --------------------------------------------------------------------------- StoreSource
class StoreSource:
    """Canli: market.sqlite salt okunur. Her cagri yeni okuma (WAL tutarli goruntu)."""

    def __init__(self, db_path) -> None:
        self.db_path = str(db_path)
        self._store = MarketStore(self.db_path, read_only=True)

    def close(self) -> None:
        self._store.close()

    def bars(self, pair: str, tf: str, until: datetime, n: int | None = None, kind: Kind = "last") -> pd.DataFrame:
        tf_ms = _check_tf(tf)
        _check_kind(kind, tf)
        until = _utc(until, "until")
        rows = self._store.query_bars(kind, canon_pair(pair), tf, to_ms(until), n)
        ms = [to_ms(b.open_ts) for b in rows]
        df = _frame(ms, [b.o for b in rows], [b.h for b in rows], [b.l for b in rows], [b.c for b in rows],
                    [b.v for b in rows])
        miss = _missing_opens(ms, tf_ms)
        if miss:
            df.attrs["gaps"] = miss
        return df

    def contiguous_tail(self, pair: str, tf: str, until: datetime, max_n: int = 5000) -> int:
        tf_ms = _check_tf(tf)
        until = _utc(until, "until")
        rows = self._store.query_bars("last", canon_pair(pair), tf, to_ms(until), max_n)
        return _tail_run([to_ms(b.open_ts) for b in rows], tf_ms)

    def minute_steps(self, pairs: Sequence[str], start: datetime, end: datetime) -> Iterator[MinuteStep]:
        start, end = _utc(start, "start"), _utc(end, "end")
        cp = [canon_pair(p) for p in pairs]
        return self._steps(cp, to_ms(start), to_ms(end))

    def _steps(self, pairs: list[str], s_ms: int, e_ms: int) -> Iterator[MinuteStep]:
        for a, b in _day_chunks(s_ms, e_ms):
            by_ts: dict[int, dict[str, MinuteBar]] = {}
            for p in pairs:
                last = self._store.query_range("last", p, "1m", a, b)
                mark = {to_ms(m.open_ts): m for m in self._store.query_range("mark", p, "1m", a, b)}
                for x in last:
                    t = to_ms(x.open_ts)
                    m = mark.get(t)
                    by_ts.setdefault(t, {})[p] = MinuteBar(
                        p, x.open_ts, 60, x.o, x.h, x.l, x.c,
                        None if m is None else m.o, None if m is None else m.h,
                        None if m is None else m.l, None if m is None else m.c, x.v)
            for t in sorted(by_ts):
                yield MinuteStep(from_ms(t), by_ts[t])

    def funding(self, pair: str, start: datetime, end: datetime) -> list[FundingPoint]:
        return self._store.query_funding(canon_pair(pair), to_ms(_utc(start, "start")), to_ms(_utc(end, "end")))

    def rules(self, pair: str) -> SymbolRules:
        p = canon_pair(pair)
        r = self._store.get_rules(p)
        if r is None:
            raise DataError(f"{p}: kural yok")
        try:
            return to_symbol_rules(p, spec_from_json(r[0]))
        except RulesError as e:
            raise DataError(f"{p}: kural bozuk: {e}") from e

    def last_closed_minute(self, pair: str) -> datetime | None:
        m = self._store.last_open_ms("last", canon_pair(pair), "1m")
        return None if m is None else from_ms(m)

    def data_range(self, pair: str, tf: str) -> tuple[datetime, datetime] | None:
        _check_tf(tf)
        p = canon_pair(pair)
        a, b = self._store.first_open_ms("last", p, tf), self._store.last_open_ms("last", p, tf)
        return None if a is None or b is None else (from_ms(a), from_ms(b))

    def step_seconds(self) -> int:
        return 60


# ----------------------------------------------------------------------- HistoricalSource
class _Series:
    __slots__ = ("ms", "o", "h", "l", "c", "v")

    def __init__(self, ms, o, h, l, c, v) -> None:
        self.ms, self.o, self.h, self.l, self.c, self.v = ms, o, h, l, c, v


class HistoricalSource:
    """Backtest/test: freqtrade adlandirmali feather dosyalari (pyarrow ile okunur)."""

    def __init__(self, history_dir, *, granularity: str = "1m", synthetic_rules: bool = False) -> None:
        if granularity not in ("1m", "15m"):
            raise DataError(f"granularity 1m|15m olmali: {granularity!r}")
        self.dir = Path(history_dir)
        self.granularity = granularity
        self.synthetic_rules = synthetic_rules
        self._cache: dict[tuple[str, str], _Series] = {}
        self._funding_cache: dict[str, tuple[np.ndarray, np.ndarray]] = {}
        self._rules_json: dict | None = None
        self.main_tf = "1h"                                  # tick_at: ana (strateji) zaman dilimi; backtest ayarlar
        self._tick_tab: dict[str, dict[tuple[int, int], float]] = {}

    # -- dosya
    def _path(self, pair: str, suffix: str) -> Path:
        return self.dir / f"{pair_stem(pair)}-{suffix}.feather"

    def _read(self, path: Path, cols: Sequence[str]):
        import pyarrow as pa
        import pyarrow.feather as pf
        try:
            t = pf.read_table(str(path), columns=list(cols), memory_map=True)
        except (OSError, pa.ArrowException, KeyError) as e:
            raise DataError(f"{path.name} okunamadi: {e}") from e
        col = t.column("date")
        unit = col.type.unit
        raw = col.combine_chunks().cast(pa.int64()).to_numpy(zero_copy_only=False)
        ms = {"ms": raw, "s": raw * 1000, "us": raw // 1000, "ns": raw // 1_000_000}[unit].astype("int64", copy=False)
        if len(ms) > 1 and not bool(np.all(np.diff(ms) > 0)):
            raise DataError(f"{path.name}: tarih sirali/tekil degil")
        if t.num_rows > 100_000:
            try:
                if os.path.getsize(path) < 0.9 * t.num_rows * 8 * len(cols):
                    log.warning("%s sikistirilmis gorunuyor (1m dosyalari uncompressed olmali); tam okundu", path.name)
            except OSError:  # pragma: no cover
                pass
        return t, ms

    def _series(self, pair: str, key: str) -> _Series:
        """key: '<tf>' (last) | '1m-mark' | '1h-mark'."""
        p = canon_pair(pair)
        ck = (p, key)
        s = self._cache.get(ck)
        if s is None:
            suffix = f"{key}-futures" if key in TF_MS else key
            path = self._path(p, suffix)
            if not path.exists():
                raise DataError(f"veri dosyasi yok: {path.name}")
            t, ms = self._read(path, ("date",) + _COLS)
            arrs = [t.column(c).combine_chunks().to_numpy(zero_copy_only=False).astype("float64", copy=False) for c in _COLS]
            s = _Series(ms, *arrs)
            self._cache[ck] = s
        return s

    def _maybe_series(self, pair: str, key: str) -> _Series | None:
        try:
            return self._series(pair, key)
        except DataError:
            if self._path(canon_pair(pair), f"{key}-futures" if key in TF_MS else key).exists():
                raise
            return None

    @property
    def _step_tf(self) -> str:
        return "1m" if self.granularity == "1m" else "15m"

    # -- MarketView
    def bars(self, pair: str, tf: str, until: datetime, n: int | None = None, kind: Kind = "last") -> pd.DataFrame:
        tf_ms = _check_tf(tf)
        _check_kind(kind, tf)
        until_ms = to_ms(_utc(until, "until"))
        s = self._series(pair, "1m-mark" if kind == "mark" else tf)
        hi = int(np.searchsorted(s.ms, until_ms - tf_ms, side="right"))
        lo = 0 if n is None else max(0, hi - max(int(n), 0))
        sl = slice(lo, hi)
        df = _frame(s.ms[sl], s.o[sl], s.h[sl], s.l[sl], s.c[sl], s.v[sl] if kind == "last" else np.zeros(hi - lo))
        miss = _missing_opens(s.ms[sl], tf_ms)
        if miss:
            df.attrs["gaps"] = miss
        return df

    def contiguous_tail(self, pair: str, tf: str, until: datetime, max_n: int = 5000) -> int:
        tf_ms = _check_tf(tf)
        until_ms = to_ms(_utc(until, "until"))
        s = self._series(pair, tf)
        hi = int(np.searchsorted(s.ms, until_ms - tf_ms, side="right"))
        return _tail_run(s.ms[max(0, hi - max_n):hi], tf_ms)

    def step_seconds(self) -> int:
        return 60 if self.granularity == "1m" else 900

    def minute_steps(self, pairs: Sequence[str], start: datetime, end: datetime) -> Iterator[MinuteStep]:
        s_ms, e_ms = to_ms(_utc(start, "start")), to_ms(_utc(end, "end"))
        cp = [canon_pair(p) for p in pairs]
        step = self._step_tf
        last = {p: self._series(p, step) for p in cp}           # eksik dosya -> DataError (sessiz dusus yok)
        mark = {p: (self._maybe_series(p, "1m-mark") if step == "1m" else None) for p in cp}
        return self._steps(cp, last, mark, s_ms, e_ms)

    def _steps(self, pairs, last, mark, s_ms, e_ms) -> Iterator[MinuteStep]:
        step_s = self.step_seconds()
        for a, b in _day_chunks(s_ms, e_ms):
            by_ts: dict[int, dict[str, MinuteBar]] = {}
            for p in pairs:
                L = last[p]
                i, j = int(np.searchsorted(L.ms, a, "left")), int(np.searchsorted(L.ms, b, "left"))
                M = mark[p]
                for k in range(i, j):
                    t = int(L.ms[k])
                    mo = mh = ml = mc = None
                    if M is not None:
                        q = int(np.searchsorted(M.ms, t, "left"))
                        if q < len(M.ms) and int(M.ms[q]) == t:
                            mo, mh, ml, mc = float(M.o[q]), float(M.h[q]), float(M.l[q]), float(M.c[q])
                    by_ts.setdefault(t, {})[p] = MinuteBar(p, from_ms(t), step_s, float(L.o[k]), float(L.h[k]), float(L.l[k]),
                                                           float(L.c[k]), mo, mh, ml, mc, float(L.v[k]))
            for t in sorted(by_ts):
                yield MinuteStep(from_ms(t), by_ts[t])

    def _funding_arrays(self, p: str) -> tuple[np.ndarray, np.ndarray]:
        f = self._funding_cache.get(p)
        if f is None:
            path = self._path(p, "1h-funding_rate")
            if not path.exists():
                raise DataError(f"funding dosyasi yok: {path.name}")
            t, ms = self._read(path, ("date", "funding_rate"))
            f = (ms, t.column("funding_rate").combine_chunks().to_numpy(zero_copy_only=False).astype("float64"))
            self._funding_cache[p] = f
        return f

    def funding(self, pair: str, start: datetime, end: datetime) -> list[FundingPoint]:
        p = canon_pair(pair)
        a, b = to_ms(_utc(start, "start")), to_ms(_utc(end, "end"))
        ms, rate = self._funding_arrays(p)
        i, j = int(np.searchsorted(ms, a, "right")), int(np.searchsorted(ms, b, "right"))
        if i >= j:
            return []
        m1 = self._maybe_series(p, "1m-mark")
        m60 = self._maybe_series(p, "1h-mark")
        out = []
        for k in range(i, j):
            t = int(ms[k])
            mk = None
            for M in (m1, m60):
                if M is not None:
                    q = int(np.searchsorted(M.ms, t, "left"))
                    if q < len(M.ms) and int(M.ms[q]) == t:
                        mk = float(M.o[q])
                        break
            out.append(FundingPoint(p, from_ms(t), float(rate[k]), mk))
        return out

    def rules(self, pair: str) -> SymbolRules:
        p = canon_pair(pair)
        if self.synthetic_rules:
            return self._synthetic_rules(p)
        if self._rules_json is None:
            path = self.dir / "rules.json"
            if not path.exists():
                raise DataError(f"rules.json yok: {path}")
            try:
                d = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError) as e:
                raise DataError(f"rules.json okunamadi: {e}") from e
            if not isinstance(d, dict):
                raise DataError("rules.json {pair: spec_json} olmali")
            self._rules_json = d
        v = self._rules_json.get(p)
        if v is None:
            raise DataError(f"{p}: rules.json'da kural yok")
        try:
            return to_symbol_rules(p, spec_from_json(v if isinstance(v, str) else json.dumps(v)))
        except RulesError as e:
            raise DataError(f"{p}: kural bozuk: {e}") from e

    def tick_at(self, pair: str, ts: datetime) -> float:
        """legacy_compat: `ts`'nin UTC ayina ait tarihsel tick (ana tf mumlarinin OHLC ondaligi, `monthly_ticks`);
        ayda veri yoksa sentetik/gercek kural tick'i. Gelecek veriye bakar: yalniz uyum kipi (GuardedView kilitler)."""
        p = canon_pair(pair)
        tab = self._tick_tab.get(p)
        if tab is None:
            s = self._maybe_series(p, self.main_tf)
            tab = {} if s is None else monthly_ticks(s.ms, s.o, s.h, s.l, s.c)
            self._tick_tab[p] = tab
        t = _utc(ts, "ts")
        v = tab.get((t.year, t.month))
        return v if v is not None else self.rules(p).tick

    def _synthetic_rules(self, p: str) -> SymbolRules:
        """SENTETIK kurallar (gercek borsa kurallari degil; raporda etiketlenmeli): ondaliklar KILITLI DONEM ONCESI
        (ms < 2026-05-01) son 2000 1h bardan; dosya sonu (kilitli doneme uzanan veri) hicbir zaman okunmaz -> deterministik.
        min_notional muhafazakar: BTC/USDT 100, ETH/USDT 20, digerleri 5."""
        s = self._series(p, "1h")
        cut = int(np.searchsorted(s.ms, to_ms(_HOLDOUT_START), "left"))
        if cut <= 0:
            raise DataError(f"{p}: sentetik kural icin kilitli donem oncesi 1h bar yok")
        k = slice(max(0, cut - 2000), cut)
        tick = _step_dec(np.concatenate([s.o[k], s.c[k], s.h[k], s.l[k]]))
        lot = _step_dec(s.v[k])
        return SymbolRules(pair=p, symbol=pair_symbol(p), tick=tick, step=lot, min_qty=lot, max_qty=1e12,
                           min_notional=_SYNTH_MIN_NOTIONAL.get(p, 5.0))

    def data_range(self, pair: str, tf: str) -> tuple[datetime, datetime] | None:
        _check_tf(tf)
        s = self._maybe_series(pair, tf)
        if s is None or len(s.ms) == 0:
            return None
        return from_ms(int(s.ms[0])), from_ms(int(s.ms[-1]))

    def last_closed_minute(self, pair: str) -> datetime | None:
        s = self._series(pair, self._step_tf)
        return from_ms(int(s.ms[-1])) if len(s.ms) else None

    def open_at(self, pair: str, ts: datetime) -> float:
        t = to_ms(_utc(ts, "ts"))
        step_ms = self.step_seconds() * 1000
        if t % step_ms:
            raise DataError(f"open_at: {ts} adim barina hizali degil")
        s = self._series(pair, self._step_tf)
        q = int(np.searchsorted(s.ms, t, "left"))
        if q >= len(s.ms) or int(s.ms[q]) != t:
            raise DataError(f"open_at: {pair} {ts} icin bar yok")
        return float(s.o[q])
