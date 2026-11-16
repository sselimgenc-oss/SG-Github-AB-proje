"""market.sqlite: tek yazar (feed), cok okuyucu (01 §3-§4). pandas/numpy YOK; saat okumaz (zaman parametre)."""
from __future__ import annotations

import logging
import math
import sqlite3
from collections.abc import Sequence
from dataclasses import dataclass, field
from pathlib import Path

from trader_engine.bars import from_ms, to_ms
from trader_engine.errors import DataError
from trader_engine.types import Bar, FundingPoint

log = logging.getLogger("engine.store")

SCHEMA_VERSION = 1
TF_MS = {"1m": 60_000, "15m": 900_000, "1h": 3_600_000, "4h": 14_400_000}
GAP_REASONS = ("missing", "minute_missing", "agg_mismatch", "conflict", "abnormal_close")
GAP_RETENTION_DAYS = 90
_DAY_MS = 86_400_000

_SCHEMA = """
CREATE TABLE IF NOT EXISTS bars(
  kind TEXT NOT NULL CHECK(kind IN ('last','mark')),
  pair TEXT NOT NULL,
  tf   TEXT NOT NULL CHECK(tf IN ('1m','15m','1h','4h')),
  open_ms INTEGER NOT NULL,
  o REAL NOT NULL, h REAL NOT NULL, l REAL NOT NULL, c REAL NOT NULL,
  v REAL NOT NULL DEFAULT 0,
  written_ms INTEGER NOT NULL,
  PRIMARY KEY(kind, pair, tf, open_ms)) WITHOUT ROWID;
CREATE TABLE IF NOT EXISTS funding(
  pair TEXT NOT NULL, ts_ms INTEGER NOT NULL, rate REAL NOT NULL, mark REAL,
  PRIMARY KEY(pair, ts_ms)) WITHOUT ROWID;
CREATE TABLE IF NOT EXISTS rules(pair TEXT PRIMARY KEY, json TEXT NOT NULL, fetched_ms INTEGER NOT NULL);
CREATE TABLE IF NOT EXISTS gaps(
  kind TEXT NOT NULL, pair TEXT NOT NULL, tf TEXT NOT NULL, open_ms INTEGER NOT NULL,
  reason TEXT NOT NULL,
  detected_ms INTEGER NOT NULL, PRIMARY KEY(kind, pair, tf, open_ms, reason)) WITHOUT ROWID;
CREATE TABLE IF NOT EXISTS feed_meta(k TEXT PRIMARY KEY, v TEXT NOT NULL);
"""


@dataclass(frozen=True)
class PutResult:
    inserted: int = 0
    duplicates_equal: int = 0
    conflicts: int = 0
    invalid: tuple[DataError, ...] = field(default=())
    inserted_bars: tuple[Bar, ...] = field(default=())


def _rel_diff(a: float, b: float) -> float:
    return abs(a - b) / max(abs(a), abs(b), 1e-300)


def _validate(b: Bar) -> DataError | None:
    tf_ms = TF_MS.get(b.tf)
    if tf_ms is None:
        return DataError(f"bilinmeyen tf: {b.tf!r}")
    if b.kind not in ("last", "mark"):
        return DataError(f"gecersiz kind: {b.kind!r}")
    vals = (b.o, b.h, b.l, b.c)
    if not all(isinstance(x, (int, float)) and math.isfinite(x) and x > 0 for x in vals):
        return DataError(f"{b.pair} {b.tf} {b.open_ts}: o/h/l/c sonlu ve > 0 olmali")
    if b.h < max(b.o, b.c, b.l) or b.l > min(b.o, b.c, b.h):
        return DataError(f"{b.pair} {b.tf} {b.open_ts}: h/l tutarsiz")
    if b.kind == "last" and not (math.isfinite(b.v) and b.v >= 0):
        return DataError(f"{b.pair} {b.tf} {b.open_ts}: hacim gecersiz")
    try:
        if to_ms(b.open_ts) % tf_ms:
            return DataError(f"{b.pair} {b.tf} {b.open_ts}: acilis tf'ye hizali degil")
    except ValueError as e:
        return DataError(str(e))
    return None


class MarketStore:
    def __init__(self, path, *, read_only: bool = False) -> None:
        self.path = str(path)
        self.read_only = read_only
        try:
            if read_only:
                if not Path(self.path).exists():
                    raise DataError(f"market.sqlite yok: {self.path}")
                uri = Path(self.path).resolve().as_uri() + "?mode=ro"
                self._db = sqlite3.connect(uri, uri=True, isolation_level=None, timeout=5.0)
                self._db.execute("PRAGMA busy_timeout=5000")
                ver = self._db.execute("PRAGMA user_version").fetchone()[0]
                if ver != SCHEMA_VERSION:
                    self._db.close()
                    raise DataError(f"market.sqlite user_version={ver}, beklenen {SCHEMA_VERSION}")
            else:
                Path(self.path).parent.mkdir(parents=True, exist_ok=True)
                self._db = sqlite3.connect(self.path, isolation_level=None, timeout=5.0)
                self._db.execute("PRAGMA busy_timeout=5000")
                self._db.execute("PRAGMA journal_mode=WAL")
                self._db.execute("PRAGMA synchronous=NORMAL")
                ver = self._db.execute("PRAGMA user_version").fetchone()[0]
                if ver not in (0, SCHEMA_VERSION):
                    self._db.close()
                    raise DataError(f"market.sqlite user_version={ver}, beklenen {SCHEMA_VERSION}")
                self._db.executescript(_SCHEMA)
                self._db.execute(f"PRAGMA user_version={SCHEMA_VERSION}")
        except sqlite3.Error as e:
            raise DataError(f"market.sqlite acilamadi: {e}") from e

    def close(self) -> None:
        try:
            self._db.close()
        except sqlite3.Error:  # pragma: no cover
            pass

    # ------------------------------------------------------------- yardimcilar
    def _need_write(self) -> None:
        if self.read_only:
            raise DataError("market.sqlite salt okunur; yazma yapilamaz")

    def _tx(self, fn):
        self._need_write()
        try:
            self._db.execute("BEGIN IMMEDIATE")
            try:
                r = fn()
                self._db.execute("COMMIT")
                return r
            except BaseException:
                try:
                    self._db.execute("ROLLBACK")
                except sqlite3.Error:  # pragma: no cover
                    pass
                raise
        except sqlite3.Error as e:
            raise DataError(f"market.sqlite yazma hatasi: {e}") from e

    def _q(self, sql: str, args: tuple = ()) -> list[tuple]:
        try:
            return self._db.execute(sql, args).fetchall()
        except sqlite3.Error as e:
            raise DataError(f"market.sqlite okuma hatasi: {e}") from e

    # ------------------------------------------------------------------ yazma
    def put_bars(self, bars: Sequence[Bar], *, now_ms: int) -> PutResult:
        invalid: list[DataError] = []
        good: list[Bar] = []
        for b in bars:
            err = _validate(b)
            if err is not None:
                invalid.append(err)
                log.warning("gecersiz bar yazilmadi: %s", err)
            else:
                good.append(b)
        if not good:
            self._need_write()
            return PutResult(invalid=tuple(invalid))

        def run() -> PutResult:
            ins = dup = con = 0
            inserted: list[Bar] = []
            for b in good:
                v = 0.0 if b.kind == "mark" else float(b.v)
                om = to_ms(b.open_ts)
                cur = self._db.execute(
                    "INSERT INTO bars(kind,pair,tf,open_ms,o,h,l,c,v,written_ms) VALUES(?,?,?,?,?,?,?,?,?,?) "
                    "ON CONFLICT DO NOTHING", (b.kind, b.pair, b.tf, om, b.o, b.h, b.l, b.c, v, now_ms))
                if cur.rowcount == 1:
                    ins += 1
                    inserted.append(b)
                    continue
                old = self._db.execute("SELECT o,h,l,c,v FROM bars WHERE kind=? AND pair=? AND tf=? AND open_ms=?",
                                       (b.kind, b.pair, b.tf, om)).fetchone()
                same = (all(_rel_diff(x, y) <= 1e-9 for x, y in zip((b.o, b.h, b.l, b.c), old[:4]))
                        and (b.kind == "mark" or _rel_diff(v, old[4]) <= 1e-6))
                if same:
                    dup += 1
                else:
                    con += 1
                    log.warning("bar cakismasi (eski deger korunur): %s %s %s %d", b.kind, b.pair, b.tf, om)
                    self._db.execute("INSERT OR IGNORE INTO gaps(kind,pair,tf,open_ms,reason,detected_ms) VALUES(?,?,?,?,?,?)",
                                     (b.kind, b.pair, b.tf, om, "conflict", now_ms))
            return PutResult(ins, dup, con, tuple(invalid), tuple(inserted))

        return self._tx(run)

    def put_funding(self, points: Sequence[FundingPoint]) -> int:
        def run() -> int:
            n = 0
            for p in points:
                cur = self._db.execute(
                    "INSERT INTO funding(pair,ts_ms,rate,mark) VALUES(?,?,?,?) ON CONFLICT(pair,ts_ms) DO UPDATE "
                    "SET mark=excluded.mark WHERE funding.mark IS NULL AND excluded.mark IS NOT NULL",
                    (p.pair, to_ms(p.ts), float(p.rate), None if p.mark is None else float(p.mark)))
                n += cur.rowcount
            return n
        return self._tx(run)

    def put_rules(self, pair: str, rules_json: str, now_ms: int) -> None:
        self._tx(lambda: self._db.execute(
            "INSERT INTO rules(pair,json,fetched_ms) VALUES(?,?,?) ON CONFLICT(pair) DO UPDATE SET json=excluded.json, "
            "fetched_ms=excluded.fetched_ms", (pair, rules_json, now_ms)))

    def mark_gap(self, kind, pair, tf, open_ms, reason, now_ms) -> None:
        if reason not in GAP_REASONS:
            raise DataError(f"gecersiz gap nedeni: {reason!r}")
        self._tx(lambda: self._db.execute(
            "INSERT OR IGNORE INTO gaps(kind,pair,tf,open_ms,reason,detected_ms) VALUES(?,?,?,?,?,?)",
            (kind, pair, tf, int(open_ms), reason, now_ms)))

    def prune(self, now_ms: int, retention_1m_days: int = 14) -> int:
        def run() -> int:
            c = self._db.execute("DELETE FROM bars WHERE tf='1m' AND open_ms < ?", (now_ms - retention_1m_days * _DAY_MS,))
            n = c.rowcount
            self._db.execute("DELETE FROM gaps WHERE detected_ms < ?", (now_ms - GAP_RETENTION_DAYS * _DAY_MS,))
            return n
        return self._tx(run)

    def meta_set(self, k: str, v: str) -> None:
        self._tx(lambda: self._db.execute(
            "INSERT INTO feed_meta(k,v) VALUES(?,?) ON CONFLICT(k) DO UPDATE SET v=excluded.v", (k, str(v))))

    def meta_get(self, k: str) -> str | None:
        r = self._q("SELECT v FROM feed_meta WHERE k=?", (k,))
        return r[0][0] if r else None

    # ----------------------------------------------------------------- okuma
    def last_open_ms(self, kind, pair, tf) -> int | None:
        r = self._q("SELECT MAX(open_ms) FROM bars WHERE kind=? AND pair=? AND tf=?", (kind, pair, tf))
        return r[0][0] if r and r[0][0] is not None else None

    def first_open_ms(self, kind, pair, tf) -> int | None:
        r = self._q("SELECT MIN(open_ms) FROM bars WHERE kind=? AND pair=? AND tf=?", (kind, pair, tf))
        return r[0][0] if r and r[0][0] is not None else None

    @staticmethod
    def _bar(kind, pair, tf, row) -> Bar:
        return Bar(pair, kind, tf, from_ms(row[0]), row[1], row[2], row[3], row[4], row[5])

    def query_bars(self, kind, pair, tf, until_ms: int, n: int | None) -> list[Bar]:
        tf_ms = TF_MS.get(tf)
        if tf_ms is None:
            raise DataError(f"bilinmeyen tf: {tf!r}")
        max_open = until_ms - tf_ms          # close_ms = open_ms + tf_ms <= until_ms
        sql = "SELECT open_ms,o,h,l,c,v FROM bars WHERE kind=? AND pair=? AND tf=? AND open_ms<=? ORDER BY open_ms DESC"
        args: tuple = (kind, pair, tf, max_open)
        if n is not None:
            if n <= 0:
                return []
            sql += " LIMIT ?"
            args += (int(n),)
        rows = self._q(sql, args)
        rows.reverse()
        return [self._bar(kind, pair, tf, r) for r in rows]

    def query_range(self, kind, pair, tf, start_ms: int, end_ms: int) -> list[Bar]:
        rows = self._q("SELECT open_ms,o,h,l,c,v FROM bars WHERE kind=? AND pair=? AND tf=? AND open_ms>=? AND open_ms<? "
                       "ORDER BY open_ms", (kind, pair, tf, start_ms, end_ms))
        return [self._bar(kind, pair, tf, r) for r in rows]

    def query_funding(self, pair, start_ms: int, end_ms: int) -> list[FundingPoint]:
        rows = self._q("SELECT ts_ms,rate,mark FROM funding WHERE pair=? AND ts_ms>? AND ts_ms<=? ORDER BY ts_ms",
                       (pair, start_ms, end_ms))
        return [FundingPoint(pair, from_ms(r[0]), r[1], r[2]) for r in rows]

    def get_rules(self, pair) -> tuple[str, int] | None:
        r = self._q("SELECT json,fetched_ms FROM rules WHERE pair=?", (pair,))
        return (r[0][0], r[0][1]) if r else None

    def gaps_in(self, pair, tf, start_ms: int, end_ms: int) -> list[tuple[int, str]]:
        rows = self._q("SELECT DISTINCT open_ms,reason FROM gaps WHERE pair=? AND tf=? AND open_ms>=? AND open_ms<? "
                       "ORDER BY open_ms,reason", (pair, tf, start_ms, end_ms))
        return [(r[0], r[1]) for r in rows]
