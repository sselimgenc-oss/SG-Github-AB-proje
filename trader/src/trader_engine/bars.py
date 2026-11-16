"""Bar aritmetigi (02 §7). Yalniz standart kutuphane."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Iterator, Sequence

from .errors import DataError
from .types import Bar, Kind, MinuteBar, require_utc

TF_SECONDS = {"1m": 60, "15m": 900, "1h": 3600, "4h": 14400}
TRIGGER_TFS = ("1h", "15m")
WINDOW_TRIGGER = {"1h": 1500, "15m": 5000}
WINDOW_4H = 1500
STARTUP_BARS = {"1h": 1200, "15m": 4800}
STARTUP_BARS_4H = 300

_EPOCH = datetime(1970, 1, 1, tzinfo=timezone.utc)
_FUNDING_HOURS = (0, 8, 16)


def tf_delta(tf: str) -> timedelta:
    try:
        return timedelta(seconds=TF_SECONDS[tf])
    except (KeyError, TypeError):
        raise ValueError(f"bilinmeyen tf: {tf!r}") from None


def floor_tf(ts: datetime, tf: str) -> datetime:
    require_utc(ts)
    d = tf_delta(tf)
    return ts - ((ts - _EPOCH) % d)


def is_tf_close(ts: datetime, tf: str) -> bool:
    return ts == floor_tf(ts, tf)


def closing_tfs(ts: datetime, tfs: Sequence[str] = ("15m", "1h", "4h")) -> list[str]:
    return [tf for tf in tfs if is_tf_close(ts, tf)]


def last_closed_open(now: datetime, tf: str) -> datetime:
    return floor_tf(now, tf) - tf_delta(tf)


def bar_close_ts(open_ts: datetime, tf: str) -> datetime:
    require_utc(open_ts, "open_ts")
    return open_ts + tf_delta(tf)


def expected_opens(start: datetime, end: datetime, tf: str) -> Iterator[datetime]:
    require_utc(start, "start")
    require_utc(end, "end")
    d = tf_delta(tf)
    t = floor_tf(start, tf)
    if t < start:
        t += d
    while t < end:
        yield t
        t += d


def to_ms(ts: datetime) -> int:
    require_utc(ts)
    return (ts - _EPOCH) // timedelta(milliseconds=1)


def from_ms(ms: int) -> datetime:
    if isinstance(ms, bool) or not isinstance(ms, int):
        raise ValueError(f"ms int olmali: {ms!r}")
    return _EPOCH + timedelta(milliseconds=ms)


def aggregate_minutes(minutes: Sequence[MinuteBar], tf: str, kind: Kind = "last") -> Bar:
    if kind not in ("last", "mark"):
        raise ValueError(f"gecersiz kind: {kind!r}")
    d = tf_delta(tf)
    n = int(d.total_seconds() // 60)
    if len(minutes) != n:
        raise DataError(f"{tf} icin {n} dakika gerekir, {len(minutes)} geldi")
    first = minutes[0]
    require_utc(first.open_ts, "open_ts")
    if floor_tf(first.open_ts, tf) != first.open_ts:
        raise DataError(f"ilk dakika {tf}'ye hizali degil: {first.open_ts}")
    step = timedelta(seconds=60)
    for i, m in enumerate(minutes):
        if m.pair != first.pair or m.step_s != 60 or m.open_ts != first.open_ts + i * step:
            raise DataError(f"dakika serisi ardisik/sirali/tek cift degil (indeks {i})")
    p = kind + "_"
    try:
        os_ = [getattr(m, p + "o") for m in minutes]
        hs = [getattr(m, p + "h") for m in minutes]
        ls = [getattr(m, p + "l") for m in minutes]
        cs = [getattr(m, p + "c") for m in minutes]
    except AttributeError:  # pragma: no cover
        raise DataError("bozuk dakika") from None
    if any(x is None for x in os_ + hs + ls + cs):
        raise DataError(f"{kind} fiyati eksik dakika var")
    return Bar(pair=first.pair, kind=kind, tf=tf, open_ts=first.open_ts,
               o=os_[0], h=max(hs), l=min(ls), c=cs[-1], v=sum(m.volume for m in minutes))


def funding_times(start: datetime, end: datetime) -> list[datetime]:
    start = require_utc(start, "start").astimezone(timezone.utc)
    end = require_utc(end, "end").astimezone(timezone.utc)
    out: list[datetime] = []
    day = datetime(start.year, start.month, start.day, tzinfo=timezone.utc)
    while day <= end:
        for h in _FUNDING_HOURS:
            t = day + timedelta(hours=h)
            if start < t <= end:
                out.append(t)
        day += timedelta(days=1)
    return out
