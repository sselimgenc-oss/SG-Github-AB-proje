"""Alinmayan sinyallerin varsayimsal sonucu (plan 25a; docs/alinmayan-sinyal-spec.md).

Atlanan her karar (`final_action='skipped'`, her `skip_reason`), karar mumunun kapanisindan sonraki 1 saatlik mumlarda
yeniden oynatilir: (a) `barrier` = ML etiketiyle AYNI uclu bariyer (trader_ml.labels.label_candidates; -1R stop, +2R hedef,
72 mum zaman), (b) `plan` = defterdeki planned_stop/planned_target ile ayni ufukta. Sonuc `counterfactual.sqlite`'e
(var/<bot>/, bu isin TEK yazari) yazilir. Defter ve market.sqlite yalnizca `mode=ro` acilir. Saf standart kutuphane:
trader_engine / trader_ml / pandas ice aktarilmaz (formul trader_ml.labels'ten kopyadir; esitlik tests/test_counterfactual.py).

Sizinti kurali: bir karar ancak ufku (72 mum) TAMAMEN dolduktan ve pencere mumlari kapanis sonrasi yazilmis, eksiksiz
bulunduktan sonra hesaplanir; erken bariyer vurusu bile beklenir. Bir kez yazilan satir degismez (idempotent).
"""
from __future__ import annotations

import math
import os
import sqlite3
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from urllib.parse import quote

__all__ = ["VERSION", "HORIZON_BARS", "TARGET_R", "FEE_RATE", "SLIPPAGE_RATE", "replay", "cost_in_r", "CounterfactualStore",
           "run_once", "summary", "RunResult", "CounterfactualError"]

VERSION = 1
# --- trader_ml.config'in KOPYASI (parite testi esitligi kilitler); ML etiketi degisirse VERSION artar
HORIZON_BARS = 72
TARGET_R = 2.0
FEE_RATE = 0.0005                     # taraf basina
SLIPPAGE_RATE = 0.0005                # taraf basina
HOLDOUT_START = datetime(2026, 5, 1, tzinfo=timezone.utc)
HOLDOUT_END = datetime(2026, 11, 1, tzinfo=timezone.utc)
GAP_GRACE = timedelta(hours=24)       # ufuk dolduktan sonra bu kadar bekleyip hala eksik mum varsa 'data_gap' yazilir
BAR_MS = 3_600_000
METHODS = ("barrier", "plan")
MARKET_SCHEMA_VERSION = 1             # trader_engine.marketdata.store.SCHEMA_VERSION'in kopyasi (salt okunur dogrulama)
STORE_SCHEMA_VERSION = 1


class CounterfactualError(Exception):
    def __init__(self, message: str, code: str = "error"):
        super().__init__(message)
        self.code = code


def cost_in_r(entry: float, stop: float, fee_rate: float = FEE_RATE, slippage_rate: float = SLIPPAGE_RATE) -> float:
    return 2.0 * (fee_rate + slippage_rate) * entry / abs(entry - stop)


# ------------------------------------------------------------------------------------------------ saf hesap
def replay(highs: Sequence[float], lows: Sequence[float], closes: Sequence[float], side: str, entry: float, stop: float,
           target: float | None, *, horizon: int = HORIZON_BARS, fee_rate: float = FEE_RATE,
           slippage_rate: float = SLIPPAGE_RATE) -> dict | None:
    """Tek yonlu bariyer taramasi. `target=None` -> hedef yok (yalniz stop/zaman). Ayni mumda iki bariyer de degerse STOP
    once sayilir. Pencere `horizon` mumdan kisaysa ve bariyer degmediyse None (cozulmemis). Doner: {outcome (1 hedef,
    0 stop/zaman), exit_reason, r_gross, r_net, cost_r, bars_held}. R = |entry-stop|."""
    rr = abs(entry - stop)
    sgn = 1.0 if side == "long" else -1.0
    cost = 2.0 * (fee_rate + slippage_rate) * entry / rr
    n = min(len(highs), horizon)
    i_stop = i_up = None
    for i in range(n):
        h, l = highs[i], lows[i]
        if i_stop is None and ((l <= stop) if side == "long" else (h >= stop)):
            i_stop = i
        if target is not None and i_up is None and ((h >= target) if side == "long" else (l <= target)):
            i_up = i
        if i_stop is not None and i_up is not None:
            break
    t_r = abs(target - entry) / rr if target is not None else 0.0
    if i_stop is not None and (i_up is None or i_stop <= i_up):
        out, why, g, j = 0, "stop", -1.0, i_stop
    elif i_up is not None:
        out, why, g, j = 1, "target", t_r, i_up
    elif n == horizon:
        out, why, g, j = 0, "time", sgn * (closes[horizon - 1] - entry) / rr, horizon - 1
    else:
        return None
    return {"outcome": out, "exit_reason": why, "r_gross": g, "r_net": g - cost, "cost_r": cost, "bars_held": j + 1}


# ------------------------------------------------------------------------------------------------ depo
_DDL = """
CREATE TABLE IF NOT EXISTS meta (key TEXT PRIMARY KEY, value TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS cf_outcomes (
  bot TEXT NOT NULL CHECK (bot IN ('learner','twin')),
  decision_id INTEGER NOT NULL,
  method TEXT NOT NULL CHECK (method IN ('barrier','plan')),
  pair TEXT NOT NULL, side TEXT NOT NULL, setup TEXT, trigger_tf TEXT,
  skip_reason TEXT NOT NULL,
  decision_ts TEXT NOT NULL,
  planned_entry REAL NOT NULL, planned_stop REAL NOT NULL, planned_target REAL,
  window_start_ts TEXT NOT NULL, window_end_ts TEXT NOT NULL,
  hyp_outcome INTEGER CHECK (hyp_outcome IS NULL OR hyp_outcome IN (0,1)),
  hyp_r_gross REAL, hyp_r_net REAL, cost_r REAL,
  exit_reason TEXT NOT NULL CHECK (exit_reason IN ('target','stop','time','data_gap','invalid_plan')),
  bars_held INTEGER,
  computed_at TEXT NOT NULL,
  version INTEGER NOT NULL,
  PRIMARY KEY (bot, decision_id, method));
CREATE INDEX IF NOT EXISTS ix_cf_ts ON cf_outcomes (bot, decision_ts);
"""


def _fmt(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.000Z")


def _utc(dt: datetime) -> datetime:
    if dt.tzinfo is None:
        raise CounterfactualError("saat dilimi olmayan zaman", "bad_time")
    return dt.astimezone(timezone.utc)


class CounterfactualStore:
    """counterfactual.sqlite. Tek yazar: bu is. journal_mode=DELETE (WAL yok): salt okunur okuyucular (rapor, pano, ML derlemi)
    -shm yazmadan acar. `read_only=True` -> mode=ro URI, yazma yok."""

    def __init__(self, path, *, read_only: bool = False):
        self.path = os.fspath(path)
        self.read_only = read_only
        try:
            if read_only:
                if not os.path.exists(self.path):
                    raise CounterfactualError("depo yok", "store_missing")
                self._db = sqlite3.connect("file:" + quote(os.path.abspath(self.path)) + "?mode=ro", uri=True,
                                           timeout=5.0, isolation_level=None)
                self._db.execute("PRAGMA busy_timeout=5000")
                ver = self._db.execute("PRAGMA user_version").fetchone()[0]
                if ver != STORE_SCHEMA_VERSION:
                    raise CounterfactualError(f"depo sema surumu {ver}", "store_schema")
            else:
                self._db = sqlite3.connect(self.path, timeout=5.0, isolation_level=None)
                self._db.execute("PRAGMA busy_timeout=5000")
                self._db.execute("PRAGMA journal_mode=DELETE")
                self._db.execute("PRAGMA synchronous=FULL")
                ver = self._db.execute("PRAGMA user_version").fetchone()[0]
                if ver not in (0, STORE_SCHEMA_VERSION):
                    raise CounterfactualError(f"depo sema surumu {ver}, beklenen {STORE_SCHEMA_VERSION}", "store_schema")
                self._db.executescript(_DDL)
                self._db.execute(f"PRAGMA user_version={STORE_SCHEMA_VERSION}")
        except sqlite3.Error as e:
            raise CounterfactualError(f"depo acilamadi: {type(e).__name__}", "store_io") from e
        self._db.row_factory = sqlite3.Row

    def close(self) -> None:
        try:
            self._db.close()
        except sqlite3.Error:  # pragma: no cover
            pass

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close()

    def done_ids(self, bot: str) -> set[int]:
        """Her iki yontemi de yazilmis kararlar."""
        rows = self._db.execute("SELECT decision_id FROM cf_outcomes WHERE bot=? GROUP BY decision_id HAVING COUNT(*)=?",
                                (bot, len(METHODS))).fetchall()
        return {r[0] for r in rows}

    def insert(self, rows: Iterable[Mapping]) -> int:
        """Idempotent: ayni (bot, decision_id, method) varsa dokunmaz. Doner: yeni eklenen satir sayisi."""
        if self.read_only:
            raise CounterfactualError("depo salt okunur", "read_only")
        cols = ("bot", "decision_id", "method", "pair", "side", "setup", "trigger_tf", "skip_reason", "decision_ts",
                "planned_entry", "planned_stop", "planned_target", "window_start_ts", "window_end_ts", "hyp_outcome",
                "hyp_r_gross", "hyp_r_net", "cost_r", "exit_reason", "bars_held", "computed_at", "version")
        sql = (f"INSERT INTO cf_outcomes ({','.join(cols)}) VALUES ({','.join('?' * len(cols))}) "
               "ON CONFLICT (bot, decision_id, method) DO NOTHING")
        n = 0
        try:
            self._db.execute("BEGIN IMMEDIATE")
            try:
                for r in rows:
                    n += self._db.execute(sql, [r[c] for c in cols]).rowcount
                self._db.execute("COMMIT")
            except BaseException:
                self._db.execute("ROLLBACK")
                raise
        except sqlite3.Error as e:
            raise CounterfactualError(f"depo yazma hatasi: {type(e).__name__}", "store_io") from e
        return n


# ------------------------------------------------------------------------------------------------ piyasa (salt okunur)
class _Market:
    def __init__(self, path):
        if not os.path.exists(path):
            raise CounterfactualError("market.sqlite yok", "market_missing")
        try:
            self._db = sqlite3.connect("file:" + quote(os.path.abspath(path)) + "?mode=ro", uri=True, timeout=5.0,
                                       isolation_level=None)
            self._db.execute("PRAGMA busy_timeout=5000")
            ver = self._db.execute("PRAGMA user_version").fetchone()[0]
        except sqlite3.Error as e:
            raise CounterfactualError(f"market.sqlite acilamadi: {type(e).__name__}", "market_unreadable") from e
        if ver != MARKET_SCHEMA_VERSION:
            self._db.close()
            raise CounterfactualError(f"market.sqlite user_version={ver}", "market_schema")

    def close(self):
        self._db.close()

    def window(self, pair: str, start_ms: int, n: int) -> list[tuple]:
        """[start, start+n*1h) araligindaki 1h 'last' mumlari; yalniz kapanistan SONRA yazilmis olanlar."""
        try:
            return self._db.execute(
                "SELECT open_ms,h,l,c FROM bars WHERE kind='last' AND pair=? AND tf='1h' AND open_ms>=? AND open_ms<? "
                "AND written_ms>=open_ms+? ORDER BY open_ms", (pair, start_ms, start_ms + n * BAR_MS, BAR_MS)).fetchall()
        except sqlite3.Error as e:
            raise CounterfactualError(f"market okuma hatasi: {type(e).__name__}", "market_unreadable") from e


# ------------------------------------------------------------------------------------------------ is
@dataclass
class RunResult:
    scanned: int = 0          # taranan atlanmis karar
    already: int = 0          # zaten hesaplanmis
    computed: int = 0         # bu kosuda yazilan karar
    gap: int = 0              # bunlardan 'data_gap'
    pending: int = 0          # ufuk dolmadi / pencere eksik (bekliyor)
    holdout_skipped: int = 0
    rows_written: int = 0


def _ceil_hour_ms(dt: datetime) -> int:
    ms = int(dt.timestamp() * 1000)
    return -(-ms // BAR_MS) * BAR_MS


def _rows_for(bot, d, method, res, start, end, now, why_override=None) -> dict:
    base = {"bot": bot, "decision_id": d.id, "method": method, "pair": d.pair, "side": d.side, "setup": d.setup,
            "trigger_tf": d.trigger_tf, "skip_reason": d.skip_reason, "decision_ts": _fmt(d.bar_close_ts),
            "planned_entry": d.planned_entry, "planned_stop": d.planned_stop, "planned_target": d.planned_target,
            "window_start_ts": _fmt(start), "window_end_ts": _fmt(end), "computed_at": _fmt(now), "version": VERSION}
    if res is None:
        base.update(hyp_outcome=None, hyp_r_gross=None, hyp_r_net=None, cost_r=None, bars_held=None,
                    exit_reason=why_override or "data_gap")
    else:
        base.update(hyp_outcome=res["outcome"], hyp_r_gross=res["r_gross"], hyp_r_net=res["r_net"], cost_r=res["cost_r"],
                    bars_held=res["bars_held"], exit_reason=res["exit_reason"])
    return base


def run_once(*, bot: str, decisions: Sequence, market_path, store: CounterfactualStore, now: datetime,
             horizon: int = HORIZON_BARS, dry_run: bool = False) -> RunResult:
    """`decisions`: atlanmis DecisionRecord benzeri nesneler (id, pair, side, setup, trigger_tf, bar_close_ts, planned_*,
    skip_reason, final_action). `now` enjekte edilir (test/lookahead). Ufku dolmamis karar HIC islenmez."""
    now = _utc(now)
    res = RunResult()
    done = store.done_ids(bot)
    mk = _Market(market_path)
    try:
        batch: list[dict] = []
        for d in decisions:
            if d.final_action != "skipped" or not d.skip_reason:
                continue
            res.scanned += 1
            if d.id in done:
                res.already += 1
                continue
            start_ms = _ceil_hour_ms(_utc(d.bar_close_ts))
            start = datetime.fromtimestamp(start_ms / 1000, tz=timezone.utc)
            end = start + timedelta(milliseconds=horizon * BAR_MS)
            if start < HOLDOUT_END and end > HOLDOUT_START:           # kilitli donem: asla okunmaz
                res.holdout_skipped += 1
                continue
            if now < end:                                              # ufuk dolmadi: sizinti yok, bekle
                res.pending += 1
                continue
            e, s, tg = d.planned_entry, d.planned_stop, d.planned_target
            ok_plan = all(isinstance(x, (int, float)) and math.isfinite(x) for x in (e, s)) and e > 0 and e != s \
                and d.side in ("long", "short") and ((s < e) if d.side == "long" else (s > e))
            if not ok_plan:
                for m in METHODS:
                    batch.append(_rows_for(bot, d, m, None, start, end, now, "invalid_plan"))
                res.computed += 1
                continue
            bars = mk.window(d.pair, start_ms, horizon)
            expect = [start_ms + k * BAR_MS for k in range(horizon)]
            if [b[0] for b in bars] != expect:
                if now >= end + GAP_GRACE:                             # veri bosluğu kalici sayilir
                    for m in METHODS:
                        batch.append(_rows_for(bot, d, m, None, start, end, now, "data_gap"))
                    res.computed += 1
                    res.gap += 1
                else:
                    res.pending += 1
                continue
            hi, lo, cl = [b[1] for b in bars], [b[2] for b in bars], [b[3] for b in bars]
            sgn = 1.0 if d.side == "long" else -1.0
            up = e + sgn * TARGET_R * abs(e - s)
            plan_tg = tg if tg is not None and math.isfinite(tg) else None
            r_bar = replay(hi, lo, cl, d.side, e, s, up, horizon=horizon)
            r_plan = replay(hi, lo, cl, d.side, e, s, plan_tg, horizon=horizon)
            batch.append(_rows_for(bot, d, "barrier", r_bar, start, end, now))
            batch.append(_rows_for(bot, d, "plan", r_plan, start, end, now))
            res.computed += 1
        if batch and not dry_run:
            res.rows_written = store.insert(batch)
    finally:
        mk.close()
    return res


# ------------------------------------------------------------------------------------------------ okuma (rapor / ders)
def summary(path, bot: str, *, now: datetime, days: int = 7, method: str = "barrier") -> dict:
    """Son `days` gunde (karar zamanina gore) hesaplanmis sonuclar: {"n", "mean_r_net", "by_reason": {skip_reason: {"n",
    "mean_r_net"}}}. Veri bosluklu/gecersiz satirlar (r_net NULL) sayima girmez. Salt okunur; depo yoksa CounterfactualError."""
    if method not in METHODS:
        raise CounterfactualError("gecersiz yontem", "bad_method")
    since = _fmt(_utc(now) - timedelta(days=days))
    with CounterfactualStore(path, read_only=True) as st:
        try:
            rows = st._db.execute(
                "SELECT skip_reason, COUNT(*) n, AVG(hyp_r_net) m FROM cf_outcomes WHERE bot=? AND method=? "
                "AND hyp_r_net IS NOT NULL AND decision_ts>=? GROUP BY skip_reason ORDER BY skip_reason",
                (bot, method, since)).fetchall()
        except sqlite3.Error as e:
            raise CounterfactualError(f"depo okuma hatasi: {type(e).__name__}", "store_io") from e
    n = sum(r["n"] for r in rows)
    mean = sum(r["n"] * r["m"] for r in rows) / n if n else None
    return {"n": n, "mean_r_net": mean, "by_reason": {r["skip_reason"]: {"n": r["n"], "mean_r_net": r["m"]} for r in rows}}
