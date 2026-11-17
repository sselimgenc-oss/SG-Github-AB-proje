"""trader-feed: REST yoklama ile market.sqlite'i dolduran TEK yazar (01 §5). pandas/numpy/requests import etmez.

Saat yalnizca enjekte edilen Clock'tan okunur; sleep da Clock.sleep. Tasarim yalniz fikir olarak alinmistir; kod kopyalanmamistir.
"""
from __future__ import annotations

import argparse
import fcntl
import hashlib
import json
import logging
import os
import signal
import sys
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from datetime import datetime, timedelta

from trader_engine.bars import (aggregate_minutes, expected_opens, floor_tf, from_ms, last_closed_open,
                                tf_delta, to_ms)
from trader_engine.clock import Clock
from trader_engine.errors import ClockError, DataError, FailClosed
from trader_engine.exchange.rules import RulesError, extract_all_rules, spec_to_json
from trader_engine.fileio import atomic_write_json, fmt_ts
from trader_engine.marketdata.rest_public import ExchangeBan, ExchangeError, PublicRestClient, rows_to_bars
from trader_engine.marketdata.store import MarketStore
from trader_engine.types import Bar, FundingPoint, MinuteBar, canon_pair, pair_symbol

log = logging.getLogger("engine.feed")

SERIES_TFS = ("1m", "15m", "1h", "4h")
TF_CLOSE_TFS = ("15m", "1h", "4h")
EXIT_BAN = 3
EXIT_STORE = 4
EXIT_RULES = 5          # acilista kurallar (retry sonrasi) alinamadi
EXIT_GEOBLOCK = 6       # HTTP 451: bu makineden Binance vadeli erisimi yok (tekrar denemek anlamsiz)
MAX_CONSEC_BANS = 6
MAX_CONSEC_STORE_FAIL = 3
CLOCK_WARN_MS = 60_000
CLOCK_FATAL_MS = 300_000
RETRY_THROTTLE_MS = 5_000
TF_GIVEUP_MS = 60_000
FUNDING_FIRST_LOOKBACK_MS = 30 * 86_400_000
_DAY_MS = 86_400_000
_FUNDING_GRID_MS = 8 * 3_600_000


def _floor_funding_ms(ms: int) -> int:
    """fundingTime'i 8h izgaraya (00/08/16 UTC) tabana yuvarla: saat basini birkac ms gecen ham deger dusmesin."""
    return ms - ms % _FUNDING_GRID_MS


def _next_funding_boundary_ms(now_ms: int) -> int:
    """now_ms'den SONRAKI 00/08/16 UTC siniri."""
    return _floor_funding_ms(now_ms) + _FUNDING_GRID_MS


def _default_backfill() -> Mapping[str, int]:
    return {"1m": 4320, "15m": 5000, "1h": 1500, "4h": 1500}


@dataclass(frozen=True)
class FeedConfig:
    pairs: tuple[str, ...]
    db_path: str
    lock_path: str
    status_path: str
    grace_s: float = 3.0
    minute_fetch_limit: int = 5
    backfill_bars: Mapping[str, int] = field(default_factory=_default_backfill)
    funding_refresh_s: float = 3600.0      # yedek periyodik cekim
    funding_boundary_delay_s: float = 5.0  # 00/08/16 UTC + birkac saniye
    rules_refresh_s: float = 3600.0
    retention_1m_days: int = 14
    rules_start_backoff_s: tuple[float, ...] = (5.0, 15.0, 45.0)   # acilis kural cekimi: len+1 deneme, sonra cikis


class RulesFetchError(FailClosed):
    """Acilista borsa kurallari alinamadi (feed baslamaz; surec sifirdan farkli kodla cikar)."""

    def __init__(self, message: str, *, geoblock: bool = False) -> None:
        super().__init__(message)
        self.geoblock = geoblock

    @property
    def exit_code(self) -> int:
        return EXIT_GEOBLOCK if self.geoblock else EXIT_RULES


GEOBLOCK_MSG = ("HTTP 451: Binance vadeli (fapi) bu makinenin bulundugu konumdan engelli; kurallar alinamaz. "
                "Sunucuyu/bolgeyi degistirmeden feed ve paper baslatilamaz")


@dataclass(frozen=True)
class BackfillReport:
    bars_written: int = 0
    duplicates: int = 0
    conflicts: int = 0
    gaps_marked: int = 0
    errors: int = 0
    skipped_pairs: tuple[str, ...] = ()


@dataclass(frozen=True)
class FeedTick:
    now_ms: int
    bars_written: int = 0
    errors: int = 0
    gaps: int = 0
    conflicts: int = 0
    banned: bool = False
    skipped: str | None = None


class RulesSnapshot(dict):
    """{pair: spec_json}; basarisiz ciftler `errors`'ta (pair -> mesaj), `exit_code` 0 | 1."""

    def __init__(self, *a, **k):
        super().__init__(*a, **k)
        self.errors: dict[str, str] = {}

    @property
    def exit_code(self) -> int:
        return 1 if self.errors else 0


def snapshot_rules(rest: PublicRestClient, pairs: Sequence[str], clock: Clock, *, store: MarketStore | None = None,
                   out_json_path: str | None = None) -> dict[str, str]:
    """exchangeInfo -> extract_all_rules -> {pair: spec_json}. RulesError veren cift atlanir (sonuc.errors, exit_code=1)."""
    info = rest.exchange_info()
    cpairs = [canon_pair(p) for p in pairs]
    res = extract_all_rules(info, [pair_symbol(p) for p in cpairs])
    out = RulesSnapshot()
    now_ms = to_ms(clock.now())
    for p in cpairs:
        r = res[pair_symbol(p)]
        if isinstance(r, RulesError):
            out.errors[p] = str(r)
            log.warning("kural alinamadi %s: %s", p, r)
            continue
        out[p] = spec_to_json(r)
        if store is not None:
            store.put_rules(p, out[p], now_ms)
    if out_json_path is not None:
        atomic_write_json(out_json_path, dict(out))
    return out


def _rel(a: float, b: float) -> float:
    return abs(a - b) / max(abs(a), abs(b), 1e-300)


class Feed:
    def __init__(self, cfg: FeedConfig, rest: PublicRestClient, store: MarketStore, clock: Clock) -> None:
        self.cfg = cfg
        self.rest = rest
        self.store = store
        self.clock = clock
        self.pairs = tuple(canon_pair(p) for p in cfg.pairs)
        self.offset_ms = 0
        self._clock_fatal = False
        self._lock_fd: int | None = None
        self._started = False
        self._c = {"requests": 0, "errors": 0, "gaps": 0, "conflicts": 0, "agg_mismatch": 0, "bans": 0, "bars_written": 0}
        self._last_ok: dict[str, str] = {}
        self._retry_at: dict[tuple, int] = {}
        self._tf_done: dict[tuple[str, str], int] = {}
        self._next_funding_ms = 0
        self._next_rules_ms = 0
        self._next_prune_ms = 0
        self._ban_streak = 0
        self._store_fail_streak = 0
        self._tick_store_err = False

    # ------------------------------------------------------------------ zaman
    def _now_server(self) -> datetime:
        return self.clock.now() + timedelta(milliseconds=self.offset_ms)

    def _measure_offset(self) -> None:
        st = self._rest(self.rest.server_time_ms)
        self.offset_ms = int(st) - to_ms(self.clock.now())
        self.store.meta_set("server_offset_ms", str(self.offset_ms))
        a = abs(self.offset_ms)
        self._clock_fatal = a > CLOCK_FATAL_MS
        if self._clock_fatal:
            log.error("%s", ClockError(f"yerel saat sunucudan {self.offset_ms} ms farkli (> 5 dk): bar yazilmaz"))
        elif a > CLOCK_WARN_MS:
            log.warning("yerel saat sunucudan %d ms farkli; suzgec sunucu saatine gore", self.offset_ms)

    # ------------------------------------------------------------------- REST
    def _rest(self, fn, *a, **k):
        self._c["requests"] += 1
        try:
            return fn(*a, **k)
        except ExchangeBan:
            self._c["bans"] += 1
            raise
        except ExchangeError:
            self._c["errors"] += 1
            raise

    # ------------------------------------------------------------------ acilis
    def start(self) -> None:
        if self._lock_fd is None:
            lock_dir = os.path.dirname(self.cfg.lock_path)
            if lock_dir:
                os.makedirs(lock_dir, exist_ok=True)
            fd = os.open(self.cfg.lock_path, os.O_CREAT | os.O_RDWR, 0o644)
            try:
                fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except OSError:
                os.close(fd)
                raise FailClosed(f"locked: baska bir feed sureci calisiyor ({self.cfg.lock_path})") from None
            self._lock_fd = fd
        self._measure_offset()
        self.store.meta_set("started_ms", str(to_ms(self.clock.now())))
        self._fetch_rules_at_start()
        self._started = True
        if not self._clock_fatal:
            self.backfill()

    def _fetch_rules_at_start(self) -> None:
        """Acilis kural cekimi: sinirli geri cekilmeyle yeniden dener; olmazsa RulesFetchError (10/10 ya da hicbiri)."""
        waits = tuple(self.cfg.rules_start_backoff_s)
        last = ""
        for attempt in range(len(waits) + 1):
            try:
                self._refresh_rules(strict=True)
                return
            except ExchangeBan as e:
                if e.http == 451:
                    raise RulesFetchError(GEOBLOCK_MSG, geoblock=True) from e
                raise
            except (ExchangeError, DataError, RulesError) as e:
                last = str(e)
                log.warning("acilista kurallar cekilemedi (%d/%d): %s", attempt + 1, len(waits) + 1, e)
            if attempt < len(waits):
                self.clock.sleep(waits[attempt])
        raise RulesFetchError(f"acilista borsa kurallari {len(waits) + 1} denemede alinamadi: {last}")

    def close(self) -> None:
        if self._lock_fd is not None:
            try:
                fcntl.flock(self._lock_fd, fcntl.LOCK_UN)
                os.close(self._lock_fd)
            finally:
                self._lock_fd = None

    # --------------------------------------------------------------- yazma yolu
    def _write(self, pair: str, tf: str, kind: str, rows: Sequence[Sequence], now_ms: int):
        bars, bad = rows_to_bars(pair, kind, tf, rows, now_ms)  # type: ignore[arg-type]
        gaps = 0
        for b in bad:
            self.store.mark_gap(kind, pair, tf, b.open_ms, "abnormal_close", now_ms)
            gaps += 1
            log.warning("anormal satir %s %s %s %d (%s)", pair, tf, kind, b.open_ms, b.reason)
        res = self.store.put_bars(bars, now_ms=now_ms)
        self._c["gaps"] += gaps + res.conflicts
        self._c["conflicts"] += res.conflicts
        self._c["bars_written"] += res.inserted
        return bars, res, gaps

    def _ok(self, pair: str, tf: str, kind: str, now_ms: int) -> None:
        k = f"{pair}:{tf}:{kind}"
        self._last_ok[k] = fmt_ts(from_ms(now_ms))
        self.store.meta_set(f"last_ok:{k}", str(now_ms))

    # ---------------------------------------------------------------- backfill
    def backfill(self) -> BackfillReport:
        now = self._now_server()
        now_ms = to_ms(now)
        w = d = c = g = e = 0
        skipped: list[str] = []
        for pair in self.pairs:
            sym = pair_symbol(pair)
            got_any = False
            for tf in SERIES_TFS:
                for kind in (("last", "mark") if tf == "1m" else ("last",)):
                    try:
                        r = self._backfill_series(pair, sym, tf, kind, now, now_ms)
                    except ExchangeBan:
                        raise
                    except ExchangeError:
                        e += 1
                        continue
                    except DataError as ex:
                        e += 1
                        self._c["errors"] += 1
                        self._tick_store_err = True
                        log.error("backfill store hatasi: %s", ex)
                        continue
                    except Exception as ex:  # noqa: BLE001
                        e += 1
                        self._c["errors"] += 1
                        log.exception("backfill %s %s %s: %s", pair, tf, kind, ex)
                        continue
                    w, d, c, g = w + r[0], d + r[1], c + r[2], g + r[3]
                    got_any = got_any or r[4]
            if not got_any:
                skipped.append(pair)
                log.warning("backfill: %s icin hic veri yok; atlandi", pair)
        return BackfillReport(w, d, c, g, e, tuple(skipped))

    def _backfill_series(self, pair, sym, tf, kind, now: datetime, now_ms: int):
        tf_ms = int(tf_delta(tf).total_seconds() * 1000)
        last = self.store.last_open_ms(kind, pair, tf)
        end_open = to_ms(floor_tf(now, tf))                  # [.., end_open) kapanmis
        if last is None:
            start_ms = end_open - int(self.cfg.backfill_bars.get(tf, 0)) * tf_ms
            if self.cfg.backfill_bars.get(tf, 0) <= 0:
                return (0, 0, 0, 0, False)
        else:
            start_ms = last + 1
        fn = self.rest.klines_all if kind == "last" else self.rest.mark_price_klines_all
        rows = self._rest(fn, sym, tf, max(start_ms, 0))
        bars, res, gaps = self._write(pair, tf, kind, rows, now_ms)
        first = self.store.first_open_ms(kind, pair, tf)
        has = first is not None
        if has:
            lo = max(start_ms, first)
            exp = [to_ms(t) for t in expected_opens(from_ms(lo), from_ms(end_open), tf)]
            if exp:
                have = {b.open_ts for b in self.store.query_range(kind, pair, tf, exp[0], exp[-1] + 1)}
                for om in exp:
                    if from_ms(om) not in have:
                        self.store.mark_gap(kind, pair, tf, om, "missing", now_ms)
                        gaps += 1
                        self._c["gaps"] += 1
            self._ok(pair, tf, kind, now_ms)
        return (res.inserted, res.duplicates_equal, res.conflicts, gaps, has)

    # ----------------------------------------------------------------- run_once
    def run_once(self) -> FeedTick:
        before = dict(self._c)
        now = self._now_server()
        now_ms = to_ms(now)
        self._tick_store_err = False
        banned = False
        skipped = None
        if not self._started:
            skipped = "not_started"
        elif self._clock_fatal:
            skipped = "clock_skew"
        if skipped is None:
            try:
                self._tick(now, now_ms)
                self._ban_streak = 0
            except ExchangeBan as b:
                banned = True
                self._ban_streak += 1
                wait = b.retry_after_s if b.retry_after_s is not None else 60
                log.error("ban/kisit (HTTP %s): %d sn uyunuyor (%d/%d)", b.http, wait, self._ban_streak, MAX_CONSEC_BANS)
                self._write_status(now_ms)
                if self._ban_streak >= MAX_CONSEC_BANS:
                    raise SystemExit(EXIT_BAN) from None
                self.clock.sleep(wait)
        if self._tick_store_err:
            self._store_fail_streak += 1
            if self._store_fail_streak >= MAX_CONSEC_STORE_FAIL:
                self._write_status(now_ms)
                raise SystemExit(EXIT_STORE)
        else:
            self._store_fail_streak = 0
        if not banned:
            self._write_status(now_ms)
        d = {k: self._c[k] - before[k] for k in self._c}
        return FeedTick(now_ms, d["bars_written"], d["errors"], d["gaps"], d["conflicts"], banned, skipped)

    def run_forever(self, *, max_ticks: int | None = None) -> None:
        n = 0
        while max_ticks is None or n < max_ticks:
            self.run_once()
            self.clock.sleep(1.0)
            n += 1

    def _guard(self, what: str, fn, *a):
        """Bir cift/seri hatasi dongu olduruz (ExchangeBan ve SystemExit disinda)."""
        try:
            return fn(*a)
        except ExchangeBan:
            raise
        except ExchangeError as e:
            log.warning("%s: %s", what, e)
        except DataError as e:
            self._c["errors"] += 1
            self._tick_store_err = True
            log.error("%s: store hatasi: %s", what, e)
        except Exception as e:  # noqa: BLE001
            self._c["errors"] += 1
            log.exception("%s: beklenmeyen hata: %s", what, e)
        return None

    def _tick(self, now: datetime, now_ms: int) -> None:
        grace_ms = int(self.cfg.grace_s * 1000)
        m_open = last_closed_open(now, "1m")
        m_close_ms = to_ms(m_open) + 60_000
        for pair in self.pairs:
            sym = pair_symbol(pair)
            if now_ms >= m_close_ms + grace_ms:
                for kind in ("last", "mark"):
                    self._guard(f"{pair} 1m {kind}", self._minute, pair, sym, kind, to_ms(m_open), now_ms)
            for tf in TF_CLOSE_TFS:                 # kapanis siniri: floor_tf(now, tf); grace sonrasi (kendini iyilestirir)
                b_ms = to_ms(floor_tf(now, tf))
                if now_ms >= b_ms + grace_ms:
                    self._guard(f"{pair} {tf}", self._tf_close, pair, sym, tf, b_ms, now_ms)
        if now_ms >= self._next_rules_ms:
            self._guard("rules", self._refresh_rules)
            self._next_rules_ms = now_ms + int(self.cfg.rules_refresh_s * 1000)
        if now_ms >= self._next_funding_ms:
            for pair in self.pairs:
                self._guard(f"{pair} funding", self._funding, pair, pair_symbol(pair), now_ms)
            self._next_funding_ms = min(now_ms + int(self.cfg.funding_refresh_s * 1000),
                                        _next_funding_boundary_ms(now_ms) + int(self.cfg.funding_boundary_delay_s * 1000))
            self._guard("offset", self._measure_offset)
        if now_ms >= self._next_prune_ms:
            self._guard("prune", lambda: self.store.prune(now_ms, self.cfg.retention_1m_days))
            self._next_prune_ms = now_ms + 3_600_000

    def _minute(self, pair, sym, kind, m_ms, now_ms) -> None:
        if (self.store.last_open_ms(kind, pair, "1m") or -1) >= m_ms:
            return
        key = (pair, "1m", kind)
        if now_ms < self._retry_at.get(key, 0):
            return
        fn = self.rest.klines if kind == "last" else self.rest.mark_price_klines
        rows = self._rest(fn, sym, "1m", limit=self.cfg.minute_fetch_limit)
        bars, res, _ = self._write(pair, "1m", kind, rows, now_ms)
        if any(to_ms(b.open_ts) >= m_ms for b in bars):
            self._ok(pair, "1m", kind, now_ms)
            self._retry_at.pop(key, None)
        else:
            self._retry_at[key] = now_ms + RETRY_THROTTLE_MS

    def _tf_close(self, pair, sym, tf, boundary_ms, now_ms) -> None:
        tf_ms = int(tf_delta(tf).total_seconds() * 1000)
        want = boundary_ms - tf_ms
        key = (pair, tf)
        if self._tf_done.get(key) == boundary_ms:
            return
        if (self.store.last_open_ms("last", pair, tf) or -1) >= want:
            self._tf_done[key] = boundary_ms
            return
        if now_ms < self._retry_at.get((pair, tf, "last"), 0):
            return
        rows = self._rest(self.rest.klines, sym, tf, limit=2)
        bars, res, _ = self._write(pair, tf, "last", rows, now_ms)
        for b in res.inserted_bars:
            self._check_aggregate(b, now_ms)
        if any(to_ms(b.open_ts) >= want for b in bars):
            self._tf_done[key] = boundary_ms
            self._retry_at.pop((pair, tf, "last"), None)
            self._ok(pair, tf, "last", now_ms)
        elif now_ms >= boundary_ms + TF_GIVEUP_MS:
            self._tf_done[key] = boundary_ms
            log.warning("%s %s bari %d yayinlanmadi; vazgecildi", pair, tf, want)
        else:
            self._retry_at[(pair, tf, "last")] = now_ms + RETRY_THROTTLE_MS

    # -------------------------------------------------------- bar builder (§5.4)
    def _check_aggregate(self, bar: Bar, now_ms: int) -> None:
        s, e = to_ms(bar.open_ts), to_ms(bar.close_ts)
        mins = self.store.query_range("last", bar.pair, "1m", s, e)
        n = (e - s) // 60_000
        if len(mins) < n:
            self.store.mark_gap("last", bar.pair, bar.tf, s, "minute_missing", now_ms)
            self._c["gaps"] += 1
            log.warning("minute_missing %s %s %d (%d/%d dakika)", bar.pair, bar.tf, s, len(mins), n)
            return
        mb = [MinuteBar(m.pair, m.open_ts, 60, m.o, m.h, m.l, m.c, None, None, None, None, m.v) for m in mins]
        agg = aggregate_minutes(mb, bar.tf, "last")
        bad = any(_rel(a, b) > 1e-9 for a, b in ((agg.o, bar.o), (agg.h, bar.h), (agg.l, bar.l), (agg.c, bar.c))) \
            or _rel(agg.v, bar.v) > 1e-6
        if bad:
            self.store.mark_gap("last", bar.pair, bar.tf, s, "agg_mismatch", now_ms)
            self._c["agg_mismatch"] += 1
            self._c["gaps"] += 1
            log.warning("agg_mismatch %s %s %d: 1m toplami REST barindan farkli", bar.pair, bar.tf, s)

    # -------------------------------------------------------- kurallar, funding
    def _refresh_rules(self, *, strict: bool = False) -> None:
        """exchangeInfo -> rules tablosu. Basari `rules_fetched_at`; her deneme `rules_attempt_at`; hata `rules_last_error`
        (feed_meta). strict (acilis): eksik cift de hata sayilir. Saatlik yenilemede hata yalniz WARN (`_guard`)."""
        now_ms = to_ms(self._now_server())
        self.store.meta_set("rules_attempt_at", str(now_ms))
        try:
            res = snapshot_rules(self.rest, self.pairs, self.clock, store=self.store)
            self._c["requests"] += 1
            if strict and res.errors:
                raise DataError("kural eksik: " + "; ".join(f"{p}: {m}" for p, m in sorted(res.errors.items())))
        except Exception as e:  # noqa: BLE001
            try:
                self.store.meta_set("rules_last_error", str(e)[:300])
            except Exception:  # noqa: BLE001
                pass
            raise
        self.store.meta_set("rules_fetched_at", str(now_ms))
        self.store.meta_set("rules_last_error", "")

    def _mark_at(self, pair: str, ts_ms: int) -> float | None:
        m0 = ts_ms - ts_ms % 60_000
        r = self.store.query_range("mark", pair, "1m", m0, m0 + 60_000)
        return r[0].o if r else None

    def _funding(self, pair: str, sym: str, now_ms: int) -> None:
        ex = self.store.query_funding(pair, 0, now_ms + _DAY_MS)
        last = to_ms(ex[-1].ts) if ex else now_ms - FUNDING_FIRST_LOOKBACK_MS
        rows = self._rest(self.rest.funding_rates, sym, start_ms=last + 1)
        pts = []
        for x in rows:
            ts = _floor_funding_ms(int(x["fundingTime"]))
            pts.append(FundingPoint(pair, from_ms(ts), float(x["fundingRate"]), self._mark_at(pair, ts)))
        # bos mark'lari doldurmayi dene (son 3 gun)
        have = {p.ts for p in pts}
        for p in self.store.query_funding(pair, now_ms - 3 * _DAY_MS, now_ms):
            if p.mark is None and p.ts not in have:
                mk = self._mark_at(pair, to_ms(p.ts))
                if mk is not None:
                    pts.append(FundingPoint(pair, p.ts, p.rate, mk))
        if pts:
            self.store.put_funding(pts)
        self._ok(pair, "funding", "last", now_ms)

    # ------------------------------------------------------------------- durum
    def stats(self) -> dict:
        d = dict(self._c)
        d["last_ok"] = dict(self._last_ok)
        return d

    def _write_status(self, now_ms: int) -> None:
        try:
            st = {"schema": "engine/feed-status/1", "ts": fmt_ts(from_ms(now_ms)), "server_offset_ms": self.offset_ms,
                  "pairs": list(self.pairs), "counters": {k: v for k, v in self._c.items()},
                  "last_ok": dict(self._last_ok), "clock_skew_fatal": self._clock_fatal}
            atomic_write_json(self.cfg.status_path, st)
            self.store.meta_set("counters", json.dumps(self._c, sort_keys=True))
        except Exception as e:  # noqa: BLE001  (durum yazilamamasi feed'i dusurmez)
            log.warning("durum yazilamadi: %s", e)


# ====================================================================== giris noktalari
RULES_SOURCE_PATH = "/fapi/v1/exchangeInfo"


def _read_base(config_dir: str) -> dict:
    """engine.base.json'dan yalniz feed'in ihtiyaci olan alanlar (EngineConfig/pandas yuklenmez; bot gerekmez)."""
    path = os.path.join(config_dir, "engine.base.json")
    try:
        with open(path, encoding="utf-8") as fh:
            raw = json.load(fh)
    except (OSError, ValueError) as e:
        raise FailClosed(f"engine.base.json okunamadi: {path}: {e}") from e
    pairs = raw.get("pairs")
    if not isinstance(pairs, list) or not pairs:
        raise FailClosed(f"{path}: pairs bos olmayan liste olmali")
    for k in ("var_dir", "market_db", "history_dir"):
        if not isinstance(raw.get(k), str) or not raw[k]:
            raise FailClosed(f"{path}: {k} bos olmayan str olmali")
    return raw


def feed_config_from_base(config_dir: str) -> FeedConfig:
    raw = _read_base(config_dir)
    var = raw["var_dir"].rstrip("/")
    return FeedConfig(pairs=tuple(canon_pair(p) for p in raw["pairs"]), db_path=raw["market_db"],
                      lock_path=f"{var}/feed.lock", status_path=f"{var}/feed-status.json")


def _make_rest(clock: Clock) -> PublicRestClient:
    return PublicRestClient(now_s=lambda: clock.now().timestamp(), sleep=clock.sleep)


def _parse(argv: Sequence[str] | None, prog: str, extra=None) -> argparse.Namespace:
    ap = argparse.ArgumentParser(prog=prog)
    ap.add_argument("--config-dir", default="config")
    if extra:
        extra(ap)
    return ap.parse_args(list(argv) if argv is not None else None)


def _on_term(signum, frame) -> None:
    raise SystemExit(0)


def main(argv: Sequence[str] | None = None, *, rest: PublicRestClient | None = None, clock: Clock | None = None,
         max_ticks: int | None = None) -> int:
    """`trader_engine feed`: kilidi al, kurallari cek (10/10), backfill, sonra run_forever. Donus = cikis kodu."""
    a = _parse(argv, "trader_engine feed")
    from trader_engine.clock import SystemClock
    clock = clock or SystemClock()
    try:
        cfg = feed_config_from_base(a.config_dir)
    except FailClosed as e:
        log.critical("feed baslamadi: %s", e)
        return EXIT_STORE
    rest = rest or _make_rest(clock)
    try:
        store = MarketStore(cfg.db_path)
    except DataError as e:
        log.critical("feed baslamadi: %s", e)
        return EXIT_STORE
    feed = Feed(cfg, rest, store, clock)
    prev = {}
    for sig in (signal.SIGTERM, signal.SIGINT):
        try:
            prev[sig] = signal.signal(sig, _on_term)
        except ValueError:      # ana is parcacigi degil (test)
            pass
    try:
        feed.start()
        feed.run_forever(max_ticks=max_ticks)
        return 0
    except RulesFetchError as e:
        log.critical("feed baslamadi: %s", e)
        return e.exit_code
    except ExchangeBan as e:
        log.critical("feed durdu: ban/kisit (HTTP %s): %s", e.http, e)
        return EXIT_GEOBLOCK if e.http == 451 else EXIT_BAN
    except FailClosed as e:
        log.critical("feed baslamadi: %s", e)
        return EXIT_STORE
    except (ExchangeError, DataError, RulesError) as e:     # acilista ag/borsa/veri hatasi (traceback yok)
        log.critical("feed baslamadi: borsa/ag hatasi: %s", type(e).__name__)
        return EXIT_RULES
    except SystemExit as e:
        return int(e.code or 0)
    finally:
        feed.close()
        store.close()
        for sig, h in prev.items():
            signal.signal(sig, h)


def rules_snapshot_main(argv: Sequence[str] | None = None, *, rest: PublicRestClient | None = None,
                        clock: Clock | None = None) -> int:
    """`trader_engine rules-snapshot`: exchangeInfo -> rules.json (+ `rules.json.meta.json`: fetched_at, sha256, kaynak).
    Cikis: 0 tamam, 1 bazi ciftler eksik (dosya yine de yazilir), 5 alinamadi, 6 HTTP 451."""
    def extra(ap):
        ap.add_argument("--out", default=None, help="varsayilan: <history_dir>/rules.json")
    a = _parse(argv, "trader_engine rules-snapshot", extra)
    from trader_engine.clock import SystemClock
    clock = clock or SystemClock()
    try:
        raw = _read_base(a.config_dir)
    except FailClosed as e:
        print(f"rules-snapshot: {e}", file=sys.stderr)
        return EXIT_STORE
    out = a.out or os.path.join(raw["history_dir"], "rules.json")
    pairs = [canon_pair(p) for p in raw["pairs"]]
    rest = rest or _make_rest(clock)
    try:
        res = snapshot_rules(rest, pairs, clock, out_json_path=out)
    except ExchangeBan as e:
        if e.http == 451:
            print(f"rules-snapshot: {GEOBLOCK_MSG}", file=sys.stderr)
            return EXIT_GEOBLOCK
        print(f"rules-snapshot: ban/kisit: {e}", file=sys.stderr)
        return EXIT_RULES
    except (ExchangeError, DataError, RulesError) as e:
        print(f"rules-snapshot: kurallar alinamadi: {e}", file=sys.stderr)
        return EXIT_RULES
    with open(out, "rb") as fh:
        digest = hashlib.sha256(fh.read()).hexdigest()
    meta = {"schema": "engine/rules-snapshot/1", "fetched_at": fmt_ts(clock.now()), "sha256": digest,
            "source_url": getattr(rest, "base_url", "") + RULES_SOURCE_PATH, "file": os.path.basename(out),
            "pairs": sorted(res), "errors": dict(res.errors)}
    atomic_write_json(out + ".meta.json", meta)
    print(f"rules-snapshot: {len(res)}/{len(pairs)} cift -> {out} (sha256 {digest[:12]})")
    for p, m in sorted(res.errors.items()):
        print(f"rules-snapshot: EKSIK {p}: {m}", file=sys.stderr)
    return res.exit_code
