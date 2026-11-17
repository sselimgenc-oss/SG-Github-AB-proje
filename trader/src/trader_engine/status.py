"""status.json (05 §8.2): atomik yazim, kalp atisi. Yazma hatasi dongu bozmaz."""
from __future__ import annotations

import logging
import os
from datetime import datetime, timezone
from pathlib import Path

from .clock import Clock
from .config import EngineConfig
from .fileio import atomic_write_json, fmt_ts, heartbeat_read, heartbeat_write, FileIoError

log = logging.getLogger("engine.status")
SCHEMA = "engine-status/1"


def _z(t: datetime | None) -> str | None:
    return None if t is None else fmt_ts(t)


def _ms_to_z(ms) -> str | None:
    if isinstance(ms, bool) or not isinstance(ms, (int, float)) or ms <= 0:
        return None
    try:
        return fmt_ts(datetime.fromtimestamp(ms / 1000.0, tz=timezone.utc))
    except (OverflowError, OSError, ValueError):
        return None


def _exchange_block(engine, f: dict, mode: str) -> dict | None:
    """11 §9.4: canli kiplerde (testnet/live) `exchange` blogu; kagit kipinde yok. naked = [{trade_id, pair, seconds}]
    (saglik denetcisi bos degilse CRIT), reachable = borsa okunabiliyor mu, last_ban = broker'in son yasagi
    ({"http", "retry_after_s"}) ya da None. Eksik alan None; blok asla yazimi bozmaz."""
    ex = f.get("exchange")
    if not isinstance(ex, dict):
        return None
    naked = []
    for r in ex.get("naked") or []:
        try:
            naked.append({"trade_id": int(r["trade_id"]), "pair": str(r["pair"]), "seconds": float(r["seconds"])})
        except (KeyError, TypeError, ValueError):
            continue
    lb = getattr(getattr(engine, "broker", None), "last_ban", None)
    last_ban = None
    if isinstance(lb, (tuple, list)) and len(lb) == 2:
        last_ban = {"http": lb[0], "retry_after_s": lb[1]}
    reach = ex.get("reachable")
    return {"env": mode, "reachable": reach if isinstance(reach, bool) else None,
            "last_sync": ex.get("last_sync_ts"), "clock_offset_ms": ex.get("clock_offset_ms"),
            "used_weight": ex.get("used_weight"), "ban_until": _ms_to_z(ex.get("ban_until_ms")),
            "last_ban": last_ban, "naked": naked}


class StatusWriter:
    def __init__(self, path: str, clock: Clock, cfg: EngineConfig) -> None:
        self.path = str(path)
        self.clock = clock
        self.cfg = cfg
        self.started_at = clock.now()
        self._last_write: datetime | None = None
        self._hb_prev: str | None = None
        self._hb_read = False

    def build(self, engine) -> dict:
        now = self.clock.now()
        f = engine.status_fields()
        pos = [{"trade_id": p.trade_id, "pair": p.pair, "side": p.side, "qty": p.qty, "entry_price": p.entry_price,
                "stop": p.current_stop} for p in f["open_positions"] if p.status in ("open", "closing")]
        ids = [p.trade_id for p in f["open_positions"] if p.status in ("open", "closing")]
        blocked = f["entries_blocked_reason"]
        gate_code = f["gate_code"]
        ml = f.get("ml")
        ml_blocked = bool(ml and ml.get("entries_blocked"))          # active + model yok/suresi dolmus: giris yok (fail-closed)
        if ml_blocked and gate_code == "ok":
            gate_code = "ml_" + str(ml["state"])
        return {
            "schema": SCHEMA, "bot": self.cfg.bot, "mode": self.cfg.mode, "pid": os.getpid(),
            "started_at": _z(self.started_at), "loop_at": _z(now), "last_minute_ts": _z(f["last_minute_ts"]),
            "last_decision_bar_close": _z(f["last_decision_close"]), "last_candle_open": _z(f["last_candle_open"]),
            "trigger_tf": f["tf"], "param_version_id": f["param_version_id"],
            "strategy": {"name": f["strategy_name"], "version": f["strategy_version"]},
            "entries_open": bool(f["entries_open"]) and not ml_blocked, "gate": {"ok": gate_code == "ok", "code": gate_code},
            "kill": bool(f["kill"]), "kill_state": f["kill_state"], "entries_blocked_reason": blocked,
            "dry_run": self.cfg.mode != "live", "wallet": f["wallet"], "equity": f["equity"], "day_start_equity": f["day_start_equity"],
            "open_positions": pos, "open_trade_ids": ids, "counters": f["counters"], "ml": ml,
            **({"pause": f["pause"]} if f.get("pause") is not None else {}),
            **({"risk_ladder": f["risk_ladder"]} if f.get("risk_ladder") is not None else {}),   # 12 §10
            **({"exchange": xb} if (xb := _exchange_block(engine, f, self.cfg.mode)) is not None else {}),
        }

    def write(self, engine, *, force: bool = False, stopped: bool = False) -> bool:
        now = self.clock.now()
        if (not force and self._last_write is not None
                and (now - self._last_write).total_seconds() < self.cfg.loop_sleep_s):
            return False
        try:
            atomic_write_json(self.path, self.build(engine))
            self._last_write = now
        except Exception as e:  # noqa: BLE001 - yazma hatasi dongu bozmaz
            log.warning("status.json yazilamadi: %s", e)
            return False
        try:
            d = Path(self.path).parent
            if not self._hb_read:
                self._hb_read = True
                try:
                    prev = heartbeat_read(d)
                    self._hb_prev = prev["ts"] if prev else None
                except FileIoError as e:
                    log.warning("kalp atisi okunamadi: %s", e)
            heartbeat_write(d, now, self.started_at, self._hb_prev, stopped=stopped)
        except Exception as e:  # noqa: BLE001
            log.warning("kalp atisi yazilamadi: %s", e)
        return True
