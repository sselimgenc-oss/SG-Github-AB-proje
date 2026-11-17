"""Giris kapisi (05 §4): kapi zinciri, veto kaynaklari, hesap durumu ve risk. Risk sayisi yoktur: tek kaynak
trader_core.risk.LOCKED_CFG (cfg.risk_config: yalniz daha siki target_trade_risk). Strateji yalniz SignalRow verir; kapi kararini ve boyutu etkileyemez."""
from __future__ import annotations

import logging
import math
from collections import Counter
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import datetime
from typing import Literal, Protocol

from trader_core import ledger as L
from trader_core import risk as K
from trader_core import veto

from .bars import tf_delta
from .brokers.base import Broker
from .clock import Clock
from .config import EngineConfig
from .errors import DataError
from .killswitch import Killswitch
from .pause import EntryPause
from .state import StateStore, parse_iso_z
from .strategy_runner import SignalFrame, SignalRow
from .types import SymbolRules

log = logging.getLogger("engine.gates")

_FILTERED_SKIPS = ("stop_width", "rr_below_min", "ml_filter")


class VetoSource(Protocol):
    def begin_step(self, now: datetime) -> None: ...

    def lookup(self, pair: str, side: str, now: datetime) -> veto.VetoLookup: ...


class FileVeto:
    """paper/canli: veto_mode="required". Anahtar yok/dosya bozuk/bayat -> lookup missing|stale (giris yok)."""

    def __init__(self, vcfg: veto.VetoConfig, env: Mapping[str, str]) -> None:
        self.cfg = vcfg
        self._key = env.get(vcfg.hmac_key_env)
        self._state: veto.VetoState | None = None

    def begin_step(self, now: datetime) -> None:
        self._state = veto.read_veto_file(self.cfg.veto_path, self._key, now, self.cfg)

    def lookup(self, pair: str, side: str, now: datetime) -> veto.VetoLookup:
        if self._state is None:
            return veto.VetoLookup("missing", "not_loaded", True)
        return veto.lookup(self._state, pair, side, now)


class NoVeto:
    """Yalniz backtest (veto_mode="off")."""

    def begin_step(self, now: datetime) -> None:
        return None

    def lookup(self, pair: str, side: str, now: datetime) -> veto.VetoLookup:
        return veto.VetoLookup("allowed", "not_evaluated:backtest", False)


@dataclass(frozen=True)
class GateVerdict:
    ok: bool
    code: str
    skip_reason: str | None   # "entry_gate_closed" | "other" | None


@dataclass(frozen=True)
class EntryOutcome:
    action: Literal["enter", "skip", "ignore"]
    event: L.DecisionEvent | None
    size: K.SizeResult | None
    leverage: int | None
    code: str
    mandatory_record: bool
    mark_decided: bool = True


def entry_leverage() -> int:
    """Kaldirac her zaman risk kilidinin alt sinirindan (eski adaptor `leverage()` ile ayni kural)."""
    return int(max(1, K.LOCKED_CFG.min_leverage))


def _fin(x) -> bool:
    return isinstance(x, (int, float)) and not isinstance(x, bool) and math.isfinite(float(x))


def _features(row: SignalRow) -> dict:
    keys = ["atr_tf", "stop_dist_atr", "atr_4h"]
    keys += (["pullback_ema", "ema_value", "body_ratio"] if row.setup == "T1"
             else ["wick_ratio", "rr", "edge_dist_atr"])
    keys += ["rh_touches", "rl_touches"]
    out: dict = {}
    for k in keys:
        v = getattr(row, k)
        if _fin(v):
            out[k] = int(v) if k in ("pullback_ema", "rh_touches", "rl_touches") else float(v)
    return out


def _tf_of(row: SignalRow) -> str:
    secs = int((row.bar_close_ts - row.bar_open_ts).total_seconds())
    for name, v in (("15m", 900), ("1h", 3600), ("4h", 14400)):
        if secs == v:
            return name
    raise ValueError(f"tetik tf cozulemedi: {secs}s")


def build_decision_event(row: SignalRow, tf: str, **override) -> L.DecisionEvent:
    is_range = row.regime == "range"
    base = dict(
        bar_close_ts=row.bar_close_ts, trigger_tf=tf, pair=row.pair, side=row.side, setup=row.setup,
        regime=row.regime, atr_ratio=row.atr_ratio, rh=row.rh if is_range else None, rl=row.rl if is_range else None,
        rh_touches=int(row.rh_touches), rl_touches=int(row.rl_touches), features=_features(row),
        planned_entry=float(row.planned_entry), planned_stop=float(row.planned_stop),
        planned_target=row.planned_target, param_version_id=int(row.param_version_id),
        veto_status="not_evaluated", veto_reason=None, risk_allowed=None, risk_reason=None,
        size_qty=None, size_notional=None, size_margin=None, size_risk_amount=None, leverage=None,
        final_action="skipped", skip_reason=None, ml_score=row.ml_score)
    base.update(override)
    return L.DecisionEvent(**base)


class EntryGate:
    def __init__(self, cfg: EngineConfig, ledger: L.Ledger, state: StateStore, kill: Killswitch, veto: VetoSource,
                 clock: Clock, broker: Broker, rules_fn: Callable[[str], SymbolRules],
                 entry_ref_fn: Callable[[str, datetime, SignalRow], float] | None = None,
                 pause: EntryPause | None = None) -> None:
        self.cfg = cfg
        self.pause = pause
        self.ledger = ledger
        self.state = state
        self.kill = kill
        self.veto = veto
        self.clock = clock
        self.broker = broker
        self.rules_fn = rules_fn
        self.entry_ref_fn = entry_ref_fn
        self.counters: Counter = Counter()

    # ------------------------------------------------------------------ cift-bagimsiz kapilar (4-8)
    def pre(self, D: datetime, tf: str, params_ok: bool, active_tf: str) -> GateVerdict:
        closed = "entry_gate_closed"
        if not params_ok:
            return GateVerdict(False, "params_unavailable", closed)
        if active_tf != tf:
            return GateVerdict(False, "trigger_tf_changed", closed)
        try:
            h = self.ledger.entries_allowed()
            if not h.ok:
                return GateVerdict(False, h.code, closed)
        except Exception as e:  # noqa: BLE001 - fail-closed
            log.error("entries_allowed hatasi: %s", e)
            return GateVerdict(False, "degraded", closed)
        reason = self.state.kv_get("entries_blocked_reason")
        if reason:
            return GateVerdict(False, str(reason), closed)
        if self.kill.active():
            return GateVerdict(False, "kill", closed)
        if self.pause is not None and self.pause.active():          # 11 §9.3: kill'den sonra, stale_data'dan once
            return GateVerdict(False, self.pause.code() or "paused", closed)
        if self.clock.now() - D > self.cfg.stale_factor * tf_delta(tf):
            return GateVerdict(False, "stale_data", "other")
        return GateVerdict(True, "ok", None)

    # ------------------------------------------------------------------ hesap durumu (§4.2)
    def account_state(self, D: datetime) -> K.AccountState | None:
        day = D.strftime("%Y-%m-%d")
        ds = self.state.kv_get(f"day_start:{day}")
        if ds is None:
            init = self.state.kv_get("initialized_at")
            fresh = True
            if isinstance(init, str) and init != "unset":
                try:
                    fresh = parse_iso_z(init).strftime("%Y-%m-%d") >= day
                except ValueError:
                    fresh = False
            if not fresh:
                return None
            ds = self.cfg.wallet_start
        positions = [K.OpenPosition(p.pair, p.side, float(p.risk_amount), float(p.margin))
                     for p in self.state.open_positions()]
        return K.AccountState(equity=float(self.broker.account().equity), day_start_equity=float(ds),
                              open_positions=positions)

    # ------------------------------------------------------------------ karar
    def _ignore(self, code: str) -> EntryOutcome:
        self.counters["ignore:" + code] += 1
        return EntryOutcome("ignore", None, None, None, code, False, False)

    def _skip(self, row: SignalRow, tf: str, code: str, *, mark: bool = True, **ev) -> EntryOutcome:
        self.counters["skip:" + code] += 1
        return EntryOutcome("skip", build_decision_event(row, tf, **ev), None, None, code, False, mark)

    def decide(self, frame: SignalFrame, D: datetime, pre: GateVerdict, active_version: int) -> EntryOutcome:
        if frame.status != "ok" or frame.last is None:                                  # 0
            return self._ignore(frame.status)
        row = frame.last
        pair = row.pair
        tf = _tf_of(row)
        if not row.signal:                                                              # 1 / 1b
            if (row.setup and row.side and row.skip_reason in _FILTERED_SKIPS
                    and self.cfg.record_filtered_candidates and row.param_version_id >= 1):
                return self._skip(row, tf, row.skip_reason, mark=False, skip_reason=row.skip_reason)
            return self._ignore("no_signal")
        if self.state.is_decided(pair, D):                                              # 2
            return self._ignore("already_decided")
        if self.state.position_for_pair(pair) is not None:                              # 3
            return self._ignore("position_exists")
        if row.param_version_id < 1:
            return self._ignore("no_param_version")
        if not pre.ok:                                                                  # 4-8
            return self._skip(row, tf, pre.code, skip_reason=pre.skip_reason, veto_reason="gate:" + pre.code)
        try:                                                                            # 9
            rules = self.rules_fn(pair)
        except Exception as e:  # noqa: BLE001 - DataError/RulesError/baska: fail-closed
            if not isinstance(e, DataError):
                log.error("rules_fn beklenmeyen hata %s: %r", pair, e)
            return self._skip(row, tf, "rules_missing", skip_reason="other", veto_reason="gate:rules_missing")
        now = self.clock.now()
        lk = self.veto.lookup(pair, row.side, now)                                      # 10
        if lk.blocks:
            return self._skip(row, tf, f"veto_{lk.status}", skip_reason=f"veto_{lk.status}",
                              veto_status=lk.status, veto_reason=lk.reason)
        acct = self.account_state(D)                                                    # 11
        if acct is None:
            return self._skip(row, tf, "day_start_missing", skip_reason="entry_gate_closed",
                              veto_reason="gate:day_start_missing")
        lev = entry_leverage()
        ref = self.entry_ref_fn(pair, D, row) if self.entry_ref_fn is not None else row.planned_entry
        cand = K.Candidate(pair, row.side, float(ref), float(row.planned_stop), float(lev),
                           rules.step, rules.min_notional)
        dec = K.check_entry(acct, cand, self.cfg.risk_config)
        if not dec.allowed:
            return self._skip(row, tf, "risk_denied", skip_reason="risk_denied", veto_status="allowed",
                              veto_reason=lk.reason, risk_allowed=False, risk_reason=dec.reason)
        size = dec.size                                                                 # 12
        self.counters["enter"] += 1
        ev = build_decision_event(
            row, tf, veto_status="allowed", veto_reason=lk.reason, risk_allowed=True, risk_reason=dec.reason,
            size_qty=size.qty, size_notional=size.notional, size_margin=size.margin,
            size_risk_amount=size.risk_amount, leverage=lev, final_action="entered", skip_reason=None)
        return EntryOutcome("enter", ev, size, lev, "entered", True)
