"""Engine (05 §5): paper, backtest ve (Faz B) canli icin ayni dongu. Fark yalniz Broker/MarketView/Clock/SignalSource
enjeksiyonudur. Sira her karar adiminda: parametre yenile -> cikislar -> stop guncelle -> girisler. Risk sayisi yoktur."""
from __future__ import annotations

import logging
import os
from collections import Counter
from collections.abc import Mapping
from dataclasses import asdict, dataclass, fields, replace
from datetime import datetime, timedelta
from pathlib import Path

from trader_core import ledger as L
from trader_core import risk as K
from trader_core import veto
from trader_core.signals import SignalParams

from .bars import floor_tf, is_tf_close, tf_delta
from .brokers.base import Broker
from .clock import Clock
from .config import EngineConfig
from .errors import ClockError, FailClosed, StateError
from .holdout import check_holdout
from .gates import EntryGate, EntryOutcome, FileVeto, NoVeto, VetoSource, entry_leverage
from .killswitch import Killswitch
from .pause import EntryPause
from .marketdata.sources import MarketView, MinuteStep
from .order_manager import OrderManager
from .position_manager import (apply_entry_fill, apply_exit_fill, apply_funding, build_trade_entry,
                               build_trade_exit, close_position, evaluate_exit, fill_risk_violation,
                               update_excursion)
from .reconcile import Reconciler, ReconcileReport
from .state import StateStore, iso_z
from .status import StatusWriter
from .strategies.base import Strategy, StrategyError
from .strategies.price_action_v1_ml import load_engine_model
from .strategies.registry import check_param_keys, get_strategy, make_label, parse_label
from .strategy_runner import SignalFrame, SignalSource, WindowedSignalSource
from .types import Intent, Position

log = logging.getLogger("engine")

ENGINE_VERSION = "05.1"
_REASONS = ("stop", "target", "trail_stop", "regime_flip", "time_stop", "manual", "force_exit", "liquidation", "other")
_STATUS_COUNTERS = ("callback_errors", "data_gaps", "ledger_errors", "outbox_failed", "unknown_orders", "mark_fallbacks",
                    "minute_gaps", "funding_missing", "exit_data_gap")
STARTUP_MAX_AGE_S = 300          # acilis kapisi: son kapanmis 1m (last+mark) en fazla bu kadar eski olabilir
EXIT_STARTUP_GATE = 7


class EngineExit(Exception):
    """Surec cikisi (systemd yeniden baslatir). `code` cikis kodu."""

    def __init__(self, code: int, message: str = "") -> None:
        super().__init__(message or f"exit {code}")
        self.code = code


@dataclass(frozen=True)
class RecoveryReport:
    replayed_minutes: int
    replayed_decisions: int
    unresolved_orders: int
    reconcile: ReconcileReport


@dataclass(frozen=True)
class RunSummary:
    steps: int
    decisions: int
    trades_opened: int
    trades_closed: int
    open_at_end: tuple[int, ...]
    counters: dict


class Engine:
    def __init__(self, cfg: EngineConfig, *, clock: Clock, view: MarketView, broker: Broker, ledger: L.Ledger,
                 state: StateStore, signals: SignalSource, strategy: Strategy, veto: VetoSource, kill: Killswitch,
                 status: StatusWriter | None, orders: OrderManager | None = None, entry_ref_fn=None,
                 strict: bool = False, tick_fn=None, pause: EntryPause | None = None) -> None:
        self.cfg = cfg
        self.clock = clock
        self.view = view
        self.broker = broker
        self.ledger = ledger
        self.state = state
        self.signals = signals
        self.strategy = strategy
        self.veto = veto
        self.kill = kill
        if pause is None and cfg.mode != "backtest":
            # F10: goreli yol cwd'ye bagli kalmasin (systemd WorkingDirectory'ye guvenilmez): mutlak yola cevrilir
            pause = EntryPause(os.path.abspath(f"{cfg.pause_file}.{cfg.bot}"), clock,
                               audit_path=os.path.abspath(cfg.path("pause_audit.jsonl")), bot=cfg.bot)
        self.pause = pause
        self.status = status
        self.strict = strict
        rules_fn = broker.rules
        self.orders = orders or OrderManager(cfg.bot, broker, state, clock, rules_fn)
        if tick_fn is not None:
            self.orders.tick_fn = tick_fn                    # legacy_compat: giris-ayi tarihsel tick
        self.gate = EntryGate(cfg, ledger, state, kill, veto, clock, broker, rules_fn, entry_ref_fn, pause)
        self.reconciler = Reconciler(cfg, broker, state, ledger, self.orders, clock)
        if getattr(signals, "last_exit_fn", False) is None:
            signals.last_exit_fn = self._last_exit            # type: ignore[attr-defined]
        self._c: Counter = Counter()
        self.tf: str = strategy.info.allowed_trigger_tfs[0]
        self._params_map: dict | None = None
        self._act_id: int | None = None
        self._version_id = 0
        self._params_ok = False
        self._active_tf: str | None = None
        self._consec_errors = 0
        self._stop = False
        self._last_now: datetime | None = None
        self._last_minute: datetime | None = None
        self._last_decision: datetime | None = None
        self._last_candle_open: datetime | None = None
        self._last_pre = None
        self._last_reconcile: datetime | None = None
        self._entry_events: dict[int, object] = {}
        self._started = False

    # ================================================================== yardimcilar
    def _set_clock(self, t: datetime) -> None:
        if hasattr(self.clock, "set_time") and t > self.clock.now():
            self.clock.set_time(t)                              # type: ignore[attr-defined]

    def _persist(self, old: Position, new: Position) -> None:
        diff = {f.name: getattr(new, f.name) for f in fields(Position)
                if f.name != "trade_id" and getattr(new, f.name) != getattr(old, f.name)}
        if diff:
            self.state.update_position(old.trade_id, **diff)

    def _mark_order(self, cid: str | None, status: str, detail: str | None = None) -> None:
        if not cid:
            return
        row = self.state.get_order(cid)
        if row is None or row.status in ("filled", "rejected", "canceled", "failed"):
            return
        f = {"status": status, "updated_ts": self.clock.now()}
        if detail:
            f["detail"] = detail
        self.state.update_order(cid, **f)

    def _block(self, reason: str) -> None:
        with self.state.tx():
            self.state.kv_set("entries_blocked_reason", reason)

    def _last_exit(self, pair: str, D: datetime):
        since = D - tf_delta(self.tf)
        best = None
        for p in self.state.closed_positions_since(since):
            if p.pair == pair and p.closed_ts is not None and p.exit_reason and (best is None or p.closed_ts >= best[0]):
                best = (p.closed_ts, p.exit_reason)
        return best

    @property
    def is_paper(self) -> bool:
        return bool(getattr(self.broker, "is_simulated", False))

    # ================================================================== gozlem
    def counters(self) -> dict:
        out = {k: 0 for k in _STATUS_COUNTERS}
        out.update(self._c)
        for src in (self.gate.counters, getattr(self.signals, "counters", None),
                    getattr(self.strategy, "counters", None)):
            if src:
                for k, v in src.items():
                    out[k] = out.get(k, 0) + v
        bc = getattr(self.broker, "counters", None)
        if callable(bc):
            for k, v in bc().items():
                out[k] = out.get(k, 0) + v
        try:
            out["unknown_orders"] = len(self.state.unresolved_orders())
        except StateError:
            pass
        return out

    def _live_gate_code(self, blocked, killed: bool) -> str:
        """Anlik kapi durumu (cift-bagimsiz kapilar; bayatlik karar adimina ozgudur)."""
        if self._params_ok is False and self._started:      # 11 §9.3: ilk kapi
            return "params_unavailable"
        try:
            h = self.ledger.entries_allowed()
            if not h.ok:
                return h.code
        except Exception:  # noqa: BLE001
            return "degraded"
        if blocked:
            return str(blocked)
        if killed:
            return "kill"
        if self.pause is not None and self.pause.active():
            return self.pause.code() or "paused"
        return "ok"

    def kill_state(self) -> str | None:
        if not self.kill.active():
            return None
        return "flat" if not self.state.open_positions() else "exiting"

    def status_fields(self) -> dict:
        now = self.clock.now()
        acct = self.broker.account()
        ds = self.state.kv_get("day_start:" + now.strftime("%Y-%m-%d"))
        blocked = self.state.kv_get("entries_blocked_reason")
        killed = self.kill.active()
        code = self._live_gate_code(blocked, killed)
        cand = self._last_candle_open
        if cand is None:
            try:
                rng = self.view.data_range(self.cfg.pairs[0], self.tf)
                cand = rng[1] if rng else None
            except Exception:  # noqa: BLE001
                cand = None
        return {
            "tf": self.tf, "param_version_id": self._version_id, "strategy_name": self.strategy.info.name,
            "strategy_version": self.strategy.info.version, "entries_blocked_reason": blocked, "gate_code": code,
            "entries_open": code == "ok",
            "kill": killed, "kill_state": self.kill_state(), "wallet": acct.wallet, "equity": acct.equity,
            "day_start_equity": ds if ds is not None else acct.equity, "open_positions": self.state.open_positions(),
            "counters": {"rules_missing": 0, "data_stale": 0, **self.counters()}, "last_minute_ts": self._last_minute,
            "last_decision_close": self._last_decision, "last_candle_open": cand,
            "ml": self._ml_status(now),
            "pause": self._pause_status(),
        }

    def _pause_status(self) -> dict | None:
        if self.pause is None:
            return None
        return {"active": self.pause.active(), "holds": [asdict(h) for h in self.pause.holds()]}

    def _ml_status(self, now: datetime) -> dict | None:
        f = getattr(self.signals, "ml_status", None)
        return f(now) if callable(f) else None

    def summary(self) -> RunSummary:
        c = self.counters()
        return RunSummary(steps=c.get("steps", 0), decisions=c.get("decisions", 0),
                          trades_opened=c.get("trades_opened", 0), trades_closed=c.get("trades_closed", 0),
                          open_at_end=tuple(p.trade_id for p in self.state.open_positions()), counters=c)

    def stop(self) -> None:
        self._stop = True

    # ================================================================== gun basi
    def ensure_day_start(self, ts: datetime) -> None:
        day = ts.strftime("%Y-%m-%d")
        with self.state.tx():
            cur = self.state.kv_get("day_start_date")
            if cur == day:
                return
            fresh = cur is None
            self.state.kv_set("day_start:" + day, self.broker.account().equity)
            self.state.kv_set("day_start_date", day)
            reason = self.state.kv_get("entries_blocked_reason")
            if reason == "day_start_missing":
                self.state.kv_set("entries_blocked_reason", None)
            if not fresh and ts.replace(hour=0, minute=0, second=0, microsecond=0) != ts:
                self.state.kv_set("entries_blocked_reason", "day_start_missing")
                log.critical("gun basi anlik goruntusu kayip (%s): girisler kapali", day)

    # ================================================================== parametreler
    def _refresh_params(self) -> None:
        try:
            ap = self.ledger.get_active_params()
            if self._params_map is None or ap.activation_id != self._act_id:
                m = dict(ap.params)
                self.strategy.validate_params(m)
                self._params_map = m
                self._act_id = ap.activation_id
                log.info("parametre surumu %s etkin", ap.version_id)
            self._version_id = ap.version_id
            self._active_tf = str(ap.params["trigger_tf"])
            self._params_ok = True
        except Exception as e:  # noqa: BLE001 - fail-closed
            self._params_ok = False
            log.critical("etkin parametre kullanilamiyor (%s); girisler kapali (params_unavailable)", e)

    def _frame_params(self):
        m = dict(self._params_map) if self._params_map is not None else {
            p.name: p.default for p in self.strategy.info.param_specs}
        if m.get("trigger_tf") != self.tf:
            m["trigger_tf"] = self.tf
        try:
            return SignalParams.from_mapping(m)
        except Exception:  # noqa: BLE001
            return m

    # ================================================================== baslatma
    # ---------------------------------------------------------------- acilis kapisi (yalniz paper)
    def check_inputs(self) -> tuple[list[str], list[str]]:
        """(kurali eksik/bozuk ciftler, 1m last+mark verisi bayat/eksik ciftler). Kapi ve canli sayaclar kullanir."""
        now = self.clock.now()
        missing: list[str] = []
        for p in self.cfg.pairs:
            try:
                self.view.rules(p)
            except Exception:  # noqa: BLE001 - DataError/RulesError/baska: kural yok sayilir
                missing.append(p)
        fresh_last: dict[str, datetime] = {}
        fresh_mark: dict[str, datetime] = {}
        try:
            a = floor_tf(now - timedelta(seconds=STARTUP_MAX_AGE_S + 120), "1m")
            for st in self.view.minute_steps(self.cfg.pairs, a, now):
                for p, b in st.bars.items():
                    fresh_last[p] = max(fresh_last.get(p, b.open_ts), b.open_ts)
                    if b.mark_c is not None:
                        fresh_mark[p] = max(fresh_mark.get(p, b.open_ts), b.open_ts)
        except Exception as e:  # noqa: BLE001
            log.error("veri taze mi kontrolu okunamadi: %r", e)
        limit = timedelta(seconds=STARTUP_MAX_AGE_S)
        stale = [p for p in self.cfg.pairs
                 if not (p in fresh_last and p in fresh_mark
                         and now - (fresh_last[p] + timedelta(seconds=60)) <= limit
                         and now - (fresh_mark[p] + timedelta(seconds=60)) <= limit)]
        self._c["rules_missing"], self._c["data_stale"] = len(missing), len(stale)
        return missing, stale

    def _startup_gate(self) -> None:
        """10/10 ya da hicbiri: tum ciftlerde kural + taze 1m last/mark yoksa sinirli bekler, sonra EngineExit(7)."""
        waited = 0.0
        step = max(1.0, min(15.0, self.cfg.loop_sleep_s * 3))
        while True:
            missing, stale = self.check_inputs()
            if not missing and not stale:
                log.info("acilis kapisi tamam: %d/%d cift kural+taze veri", len(self.cfg.pairs), len(self.cfg.pairs))
                return
            if waited >= self.cfg.startup_wait_s:
                msg = (f"acilis kapisi: {self.cfg.startup_wait_s:.0f} sn sonra hazir degil; "
                       f"kural eksik={missing or '-'} veri bayat={stale or '-'}; motor baslamiyor (feed calisiyor mu?)")
                log.critical("%s", msg)
                raise EngineExit(EXIT_STARTUP_GATE, msg)
            if waited == 0.0:
                log.warning("acilis kapisi bekliyor: kural eksik=%s veri bayat=%s", missing or "-", stale or "-")
            self.clock.sleep(step)
            waited += step

    def start(self) -> RecoveryReport:
        cfg = self.cfg
        if cfg.mode == "paper":
            self._startup_gate()
        if cfg.bot == "twin" and cfg.start_delay_s > 0:
            self.clock.sleep(cfg.start_delay_s)
        if not self.state.integrity_check():
            raise StateError("state integrity_check basarisiz")
        now = self.clock.now()
        with self.state.tx():
            if self.state.kv_get("initialized_at") in (None, "unset"):
                self.state.kv_set("initialized_at", iso_z(now))
            self.state.kv_set("engine_version", ENGINE_VERSION)
        try:
            self.ledger.drain_spool()
        except Exception as e:  # noqa: BLE001
            log.error("spool bosaltilamadi: %s", e)
        self.state.drain_outbox(self.ledger)
        self._refresh_params()
        self._init_tf_and_strategy()
        if self.is_paper:
            snap = self.state.kv_get("broker_snapshot")
            if snap:
                self.broker.restore(snap)                        # type: ignore[attr-defined]
            else:
                with self.state.tx():
                    self.state.kv_set("broker_snapshot", self.broker.snapshot())   # type: ignore[attr-defined]
        lev = entry_leverage()
        for pair in cfg.pairs:
            try:
                self.broker.prepare(pair, lev)
            except Exception as e:  # noqa: BLE001
                log.error("prepare %s: %s", pair, e)
        self.orders.resolve_unresolved()
        rep = self._reconcile(now)
        if rep.fatal:
            log.critical("baslangic mutabakati ölümcül: girisler kapali; cikislar calisir")
        self._started = True
        mins, decs = 0, 0
        if cfg.mode == "paper" and self._init_cursors():
            c0 = self._c["decisions"]
            mins = self.advance_to(self.clock.now())
            decs = self._c["decisions"] - c0
        return RecoveryReport(replayed_minutes=mins, replayed_decisions=decs,
                              unresolved_orders=len(self.state.unresolved_orders()), reconcile=rep)

    def _init_tf_and_strategy(self) -> None:
        info = self.strategy.info
        kv_tf = self.state.kv_get("trigger_tf")
        want = self._active_tf if (self._params_ok and self._active_tf in ("1h", "15m", "4h")) else info.allowed_trigger_tfs[0]
        has_open = bool(self.state.open_positions())
        tf = kv_tf if (kv_tf and has_open) else want
        if kv_tf and kv_tf != want and has_open:
            log.critical("trigger_tf degisti (%s -> %s) acik pozisyon varken: girisler kapali", kv_tf, want)
        self.tf = tf
        with self.state.tx():
            self.state.kv_set("trigger_tf", tf)
        # strateji degisikligi / ledger uyumu (§13.2, §13.6)
        label = make_label(info.name, info.version)
        prev = self.state.kv_get("strategy")
        if prev and prev != label and self.state.open_positions():
            raise StrategyError("strategy_change_with_open_positions", f"{prev} -> {label}")
        with self.state.tx():
            self.state.kv_set("strategy", label)
        if self._params_ok:
            check_param_keys(self.strategy, self._params_map or {})
            try:
                reason = self.ledger.get_version(self._version_id).reason
            except Exception:  # noqa: BLE001
                reason = None
            name, ver = parse_label(reason)
            if name != info.name:
                raise StrategyError("strategy_mismatch", f"ledger etiketi {name}, calisan {info.name}")
            if ver is not None and ver != info.version:
                log.critical("strateji surumu uyusmuyor (ledger %s, calisan %s): girisler kapali", ver, info.version)
                self._block("strategy_mismatch")

    def _reconcile(self, now: datetime) -> ReconcileReport:
        self._last_reconcile = now
        rep = self.reconciler.run(now)
        self._c["reconciles"] += 1
        return rep

    def _init_cursors(self) -> bool:
        """True: imlec var (oynatma). Ilk kurulumda son kapanmis dakikaya ayarlanir, gecmis oynatilmaz."""
        cur = self._cursor("minute")
        if cur is not None:
            return True
        lasts = []
        for p in self.cfg.pairs:
            lm = self.view.last_closed_minute(p)
            if lm is None:
                return False
            lasts.append(lm)
        last = min(lasts)
        D = floor_tf(last + timedelta(seconds=self.view.step_seconds()), self.tf)
        with self.state.tx():
            for p in self.cfg.pairs:
                self.state.set_cursor(p, "minute", last)
                self.state.set_cursor(p, "decision", D)
        return False

    def _cursor(self, kind: str) -> datetime | None:
        cs = [self.state.get_cursor(p, kind) for p in self.cfg.pairs]
        if any(c is None for c in cs):
            return None
        return min(cs)

    # ================================================================== hata yonetimi
    def _guard(self, label: str, fn) -> bool:
        try:
            fn()
        except (StateError, EngineExit):
            raise
        except Exception as e:  # noqa: BLE001
            if self.strict:
                raise
            self._after_failure(label, e)
            return False
        self._consec_errors = 0
        return True

    def _after_failure(self, label: str, e: Exception) -> None:
        self._c["callback_errors"] += 1
        self._consec_errors += 1
        log.critical("%s adimi basarisiz (%d. ardisik): %r", label, self._consec_errors, e, exc_info=True)
        if self.is_paper:
            snap = self.state.kv_get("broker_snapshot")
            if snap:
                try:
                    self.broker.restore(snap)                      # type: ignore[attr-defined]
                except Exception as re_:  # noqa: BLE001
                    log.critical("broker geri yuklenemedi: %r", re_)
        if self._consec_errors >= 10:
            raise EngineExit(3, "10 ardisik hata")
        if self._consec_errors >= 3:
            self._block("engine_errors")

    # ================================================================== dakika adimi
    def process_step(self, step) -> None:
        if self._guard("minute", lambda: self._process_step(step)):
            self._post_commit()

    def _post_commit(self) -> None:
        try:
            res = self.state.drain_outbox(self.ledger)
            self._outbox_health(res)
        except StateError:
            raise
        except Exception as e:  # noqa: BLE001
            self._c["ledger_errors"] += 1
            log.error("outbox bosaltilamadi: %r", e)

    def _outbox_health(self, res) -> None:
        """Defter outbox'inda takili/gecersiz satir: say ve girisleri kapat (cozulene kadar; islem kapansa da kapali)."""
        cur = self.state.kv_get("entries_blocked_reason")
        if res.failed > 0:
            self._c["outbox_failed"] += 1
            log.error("outbox takili: %d satir yazilamadi (%s)", res.failed, res.first_error)
            if not cur:
                self._block("outbox_stuck")
        elif cur == "outbox_stuck":
            with self.state.tx():
                self.state.kv_set("entries_blocked_reason", None)

    def _process_step(self, step) -> None:
        ts = step.ts
        end = ts + timedelta(seconds=self.view.step_seconds())
        self._set_clock(end)
        with self.state.tx():
            self.ensure_day_start(ts)
            self.broker.advance(step.bars, "fills")             # type: ignore[attr-defined]
            self._handle_events(self.broker.poll(end), step, end)
            self.broker.advance(step.bars, "triggers")          # type: ignore[attr-defined]
            self._handle_events(self.broker.poll(end), step, end)
            self._kill_step(end)                                # kill emri bu adimda verilir, sonraki adimda dolar
            for p in self.state.open_positions():
                bar = step.bars.get(p.pair)
                if bar is not None and p.status in ("open", "closing"):
                    self._persist(p, update_excursion(p, bar))
            for pair in self.cfg.pairs:
                c = self.state.get_cursor(pair, "minute")
                if c is None or ts > c:
                    self.state.set_cursor(pair, "minute", ts)
            self.state.kv_set("broker_snapshot", self.broker.snapshot())   # type: ignore[attr-defined]
        self._last_minute = ts
        self._c["steps"] += 1

    def _kill_step(self, now: datetime) -> None:
        if self.kill.active():
            if self.state.kv_get("kill_seen_at") is None:
                self.state.kv_set("kill_seen_at", iso_z(now))
                log.critical("KILL etkin: girisler kapali, acik pozisyonlar kapatiliyor")
            for p in self.state.open_positions():
                if p.status == "open" and p.qty:
                    self.orders.submit_exit(p, "force_exit", now)
        elif self.state.kv_get("kill_seen_at") is not None:
            self.state.kv_set("kill_seen_at", None)
            log.warning("KILL kalkti: girisler bir sonraki karar adiminda yeniden acilir")

    # ------------------------------------------------------------------ broker olaylari
    def _handle_events(self, evs, step, now: datetime) -> None:
        for e in evs:
            if e.kind in ("fill", "liquidation") and e.fill is not None:
                if e.fill.role == "entry":
                    self._on_entry_fill(e, step, now)
                else:
                    self._on_exit_fill(e, step, now)
            elif e.kind == "funding":
                p = self.state.position_for_pair(e.pair)
                if p is not None and p.status in ("open", "closing"):
                    self._persist(p, apply_funding(p, e))
            elif e.kind == "order_rejected":
                self._on_rejected(e, now)
            elif e.kind == "order_canceled":
                self._mark_order(e.client_id, "canceled")

    def _on_entry_fill(self, e, step, now: datetime) -> None:
        fill = e.fill
        pos = self.state.position_for_pair(e.pair)
        if pos is None or pos.status != "opening":
            self._c["unexpected_fills"] += 1
            log.critical("beklenmeyen giris dolumu %s", e.pair)
            return
        newp = apply_entry_fill(pos, fill, step.bars.get(e.pair), now)
        self._persist(pos, newp)
        self._mark_order(fill.client_id, "filled")
        self.state.outbox_add("entry", pos.trade_id, build_trade_entry(newp))
        self._c["trades_opened"] += 1
        eq = self.state.kv_get(f"eq:{pos.trade_id}")
        tick = self.orders.stop_tick(newp)
        viol = fill_risk_violation(newp, float(eq), tick) if eq else None
        cur = self.state.get_position(pos.trade_id) or newp
        if viol:
            log.critical("dolum sonrasi risk ihlali (%s) trade %s: cikis", viol, pos.trade_id)
            self._c["fill_risk_violation"] += 1
            self.orders.submit_exit(cur, "other", now)
        else:
            self.orders.place_initial_stop(cur)

    def _on_exit_fill(self, e, step, now: datetime) -> None:
        fill = e.fill
        pos = self.state.position_for_pair(e.pair)
        if pos is None or pos.status == "opening" or pos.entry_price is None:
            self._c["unexpected_fills"] += 1
            log.critical("beklenmeyen cikis dolumu %s", e.pair)
            return
        closed = apply_exit_fill(pos, fill, step.bars.get(e.pair), now)
        newp = close_position(pos, closed)
        self._persist(pos, newp)
        self.state.outbox_add("exit", pos.trade_id, build_trade_exit(pos, closed))
        self._mark_order(fill.client_id, "filled")
        self._c["trades_closed"] += 1
        self.orders.cancel_resting(pos)

    def _on_rejected(self, e, now: datetime) -> None:
        row = self.state.get_order(e.client_id) if e.client_id else None
        if row is None:
            return
        self._mark_order(e.client_id, "rejected", e.detail)
        pos = self.state.get_position(row.trade_id) if row.trade_id is not None else None
        if pos is None:
            return
        if row.role == "entry" and pos.status == "opening":
            self._close_unopened(pos, now)
        elif row.role == "exit" and pos.status == "closing" and pos.exit_client_id == row.client_id:
            self.state.update_position(pos.trade_id, status="open", exit_client_id=None, exit_reason=None)
        elif row.role == "stop" and pos.status == "open":
            log.critical("stop reddedildi trade %s (%s): mutabakat yeniden kuracak", pos.trade_id, e.detail)
            self._block("stop_failed")

    def _close_unopened(self, pos: Position, now: datetime) -> None:
        self.state.update_position(pos.trade_id, status="closed", exit_reason="other", closed_ts=now)
        ev = self._entry_events.pop(pos.trade_id, None)
        if ev is not None:
            try:
                self.ledger.record_decision(replace(ev, final_action="skipped", skip_reason="order_failed",
                                                    supersedes_id=pos.decision_id))
            except Exception as err:  # noqa: BLE001 - best-effort
                self._c["ledger_errors"] += 1
                log.error("order_failed duzeltmesi yazilamadi: %r", err)

    # ================================================================== karar adimi
    def decision_step(self, D: datetime) -> None:
        if self._guard("decision", lambda: self._decision_step(D)):
            self._post_commit()
            if self.status is not None:
                self.status.write(self, force=True)

    def _decision_step(self, D: datetime) -> None:
        self._set_clock(D)
        now = self.clock.now()
        with self.state.tx():
            self.ensure_day_start(D)
            self._kill_step(now)
            if self.cfg.mode == "paper":
                self._reconcile(now)
            self._refresh_params()
            self.veto.begin_step(now)
            params = self._frame_params()
            frames: dict[str, SignalFrame] = {}
            for pair in self.cfg.pairs:
                fr = self.signals.frame(pair, D, params, self._version_id)
                frames[pair] = fr
                if fr.status == "data_gap":
                    self._c["data_gaps"] += 1
                if fr.status == "ok" and fr.last is not None:
                    c = fr.last.bar_open_ts
                    if self._last_candle_open is None or c > self._last_candle_open:
                        self._last_candle_open = c
            self._exits(D, frames)
            self._entries(D, frames)
            for pair in self.cfg.pairs:
                c = self.state.get_cursor(pair, "decision")
                if c is None or D > c:
                    self.state.set_cursor(pair, "decision", D)
            self.state.kv_set("broker_snapshot", self.broker.snapshot())   # type: ignore[attr-defined]
        self._last_decision = D
        self._c["decisions"] += 1

    # ------------------------------------------------------------------ cikislar (kapisiz)
    def _vet(self, pos: Position, dec):
        if dec.kind == "exit" and dec.reason not in _REASONS:
            log.critical("gecersiz cikis nedeni %r (trade %s): force_exit", dec.reason, pos.trade_id)
            return replace(dec, reason="force_exit")
        if dec.kind == "stop_update":
            ns = dec.new_stop
            ok = ns is not None and ((ns > pos.current_stop) if pos.side == "long" else (ns < pos.current_stop))
            if not ok:
                self._c["exit_policy_loosen"] += 1
                return replace(dec, kind="none")
        return dec

    def _exits(self, D: datetime, frames: Mapping[str, SignalFrame]) -> None:
        policy = self.strategy.exit_policy()
        for pos in self.state.open_positions():
            if pos.status != "open":
                continue
            fr = frames.get(pos.pair)
            if fr is None or fr.status != "ok":
                self._c["exit_data_gap"] += 1
                continue
            try:
                ctx = self.signals.exit_context(pos.pair, pos, D)
                dec = policy.evaluate(pos, ctx) if policy is not None else evaluate_exit(pos, ctx)
                dec = self._vet(pos, dec)
                if dec.kind == "exit":
                    self.orders.submit_exit(pos, dec.reason, D)
                elif dec.kind == "stop_update":
                    out = self.orders.replace_stop(pos, dec.new_stop)
                    if out.note == "would_trigger":
                        cur = self.state.get_position(pos.trade_id) or pos
                        if cur.status == "open":
                            self.orders.submit_exit(cur, "trail_stop", D)
            except StateError:
                raise
            except Exception as e:  # noqa: BLE001
                if self.strict:
                    raise
                self._c["callback_errors"] += 1
                log.critical("cikis degerlendirmesi hatasi trade %s: %r", pos.trade_id, e, exc_info=True)

    # ------------------------------------------------------------------ girisler (kapili)
    def _entries(self, D: datetime, frames: Mapping[str, SignalFrame]) -> None:
        pre = self.gate.pre(D, self.tf, self._params_ok, self._active_tf or self.tf)
        self._last_pre = pre
        for pair in self.cfg.pairs:
            try:
                out = self.gate.decide(frames[pair], D, pre, self._version_id)
                if out.action == "ignore":
                    continue
                if out.action == "skip":
                    self._record_skip(pair, D, out)
                else:
                    self._enter(pair, D, frames[pair], out)
            except StateError:
                raise
            except Exception as e:  # noqa: BLE001 - cift-bazli hata: giris yok
                if self.strict:
                    raise
                self._c["callback_errors"] += 1
                log.critical("giris degerlendirmesi hatasi %s: %r", pair, e, exc_info=True)

    def _record_skip(self, pair: str, D: datetime, out: EntryOutcome) -> None:
        try:
            self.ledger.record_decision(out.event)
        except Exception as e:  # noqa: BLE001 - skip kayitlari best-effort
            self._c["ledger_errors"] += 1
            log.error("skip karari yazilamadi (%s %s): %r", pair, out.code, e)
        if out.mark_decided:
            self.state.mark_decided(pair, D, "skipped:" + out.code)

    def _enter(self, pair: str, D: datetime, fr: SignalFrame, out: EntryOutcome) -> None:
        row = fr.last
        try:
            did = self.ledger.record_decision(out.event)
        except Exception as e:  # noqa: BLE001 - zorunlu kayit: yoksa giris yok
            self._c["ledger_errors"] += 1
            log.critical("entered karari yazilamadi (%s): %r; giris yok", pair, e)
            return
        size = out.size
        equity = float(self.broker.account().equity)
        tid = self.state.next_trade_id()
        info = self.strategy.info
        trail = float((self._params_map or {}).get("trail_atr", 0.0))
        pos = Position(
            trade_id=tid, bot=self.cfg.bot, pair=pair, side=row.side, setup=row.setup, status="opening",
            decision_id=did, signal_bar_close_ts=row.bar_close_ts, entry_ts=None, entry_bar_open=None,
            entry_price=None, qty=None, leverage=out.leverage, initial_stop=row.planned_stop,
            current_stop=row.planned_stop, stop_seq=0, stop_client_id=None, planned_target=row.planned_target,
            trail_atr=trail, param_version_id=row.param_version_id, trigger_tf=self.tf,
            risk_amount=size.risk_amount, margin=size.margin, rh=row.rh, rl=row.rl, fee_entry=0.0,
            funding_paid=0.0, mfe_price=None, mae_price=None, exit_reason=None, exit_client_id=None,
            closed_ts=None, strategy_name=info.name, strategy_version=info.version)
        self.state.insert_position(pos)
        self.state.mark_decided(pair, D, "entered")
        self.state.kv_set(f"eq:{tid}", equity)
        self._entry_events[tid] = out.event
        intent = Intent(kind="entry", bot=self.cfg.bot, pair=pair, side=row.side, signal_bar_close_ts=row.bar_close_ts,
                        setup=row.setup, qty=size.qty, leverage=out.leverage, planned_entry=row.planned_entry,
                        stop_price=row.planned_stop, target_price=row.planned_target, reason="entry", decision_id=did)
        res = self.orders.submit_entry(intent, tid)
        if res.status not in ("filled", "accepted"):
            cur = self.state.get_position(tid)
            if cur is not None and cur.status == "opening":
                self._close_unopened(cur, self.clock.now())
            elif cur is not None:
                self._entry_events.pop(tid, None)

    # ================================================================== canli dongu
    def advance_to(self, now: datetime) -> int:
        if self._last_now is not None and now < self._last_now:
            self._block("clock_skew")
            raise ClockError(f"saat geri gitti: {now} < {self._last_now}")
        self._last_now = now
        if self.state.kv_get("entries_blocked_reason") == "clock_skew":
            with self.state.tx():
                self.state.kv_set("entries_blocked_reason", None)
        step_s = self.view.step_seconds()
        n = 0
        while not self._stop:
            cur = self._cursor("minute")
            if cur is None:
                if not self._init_cursors():
                    return n
                cur = self._cursor("minute")
            nxt = cur + timedelta(seconds=step_s)
            if is_tf_close(nxt, self.tf):
                ld = self._cursor("decision")
                if ld is None or ld < nxt:
                    if not self._decision_ready(nxt, now):
                        return n
                    self.decision_step(nxt)
            end = nxt + timedelta(seconds=step_s)
            if now < end:
                return n
            steps = list(self.view.minute_steps(self.cfg.pairs, nxt, end))
            have = steps[0].bars if steps else {}
            if len(have) < len(self.cfg.pairs):
                if now < end + timedelta(seconds=self.cfg.minute_wait_s):
                    return n
                if not have:
                    latest = [self.view.last_closed_minute(p) for p in self.cfg.pairs]
                    if not any(t is not None and t > nxt for t in latest):
                        return n                                  # veri bayat: dakika ilerlemez
            self.process_step(steps[0] if steps else MinuteStep(nxt, {}))
            n += 1
        return n

    def _decision_ready(self, D: datetime, now: datetime) -> bool:
        if now < D:
            return False
        if now >= D + timedelta(seconds=self.cfg.bar_wait_s):
            return True
        for p in self.cfg.pairs:
            rng = self.view.data_range(p, self.tf)
            if rng is None or rng[1] < D - tf_delta(self.tf):
                return False
        return True

    def run_forever(self) -> None:
        self.start()
        try:
            while not self._stop:
                now = self.clock.now()
                try:
                    self.advance_to(now)
                except ClockError as e:
                    log.critical("%s", e)
                self._periodic_reconcile(now)
                self._periodic_input_check(now)
                if self.status is not None:
                    self.status.write(self)
                self.clock.sleep(self.cfg.loop_sleep_s)
        finally:
            self.shutdown("stop")

    def _periodic_input_check(self, now: datetime) -> None:
        """Calisirken kural/veri sayaclarini (`rules_missing`, `data_stale`) dakikada bir tazeler; karar vermez."""
        if self.cfg.mode != "paper":
            return
        last = getattr(self, "_last_input_check", None)
        if last is not None and (now - last).total_seconds() < 60:
            return
        self._last_input_check = now
        try:
            self.check_inputs()
        except Exception as e:  # noqa: BLE001
            log.error("girdi kontrolu hatasi: %r", e)

    def _periodic_reconcile(self, now: datetime) -> None:
        every = self.cfg.reconcile_open_s if self.state.open_positions() else self.cfg.reconcile_flat_s
        if self._last_reconcile is None or (now - self._last_reconcile).total_seconds() >= every:
            try:
                with self.state.tx():
                    self._reconcile(now)
            except StateError:
                raise
            except Exception as e:  # noqa: BLE001
                log.error("mutabakat hatasi: %r", e)

    def shutdown(self, reason: str) -> None:
        log.info("kapaniyor: %s", reason)
        if self.status is not None:
            self.status.write(self, force=True, stopped=True)

    # ================================================================== backtest surucusu
    def run_range(self, start: datetime, end: datetime, *, active_only: bool = True) -> RunSummary:
        if self.cfg.mode == "backtest":
            check_holdout(start, end)      # kilitli donem: hicbir bar okunmadan once reddedilir
        tf = self.tf
        step_s = self.view.step_seconds()
        D = floor_tf(start, tf)
        if D <= start:
            D += tf_delta(tf)
        cur = start
        while D <= end:
            self._run_steps(cur, D, active_only)
            cur = D
            self._set_clock(D)
            self.decision_step(D)
            D += tf_delta(tf)
        if end > cur:
            self._run_steps(cur, end, active_only)
        if self.cfg.mode != "paper":
            self._guard("reconcile", lambda: self._reconcile_tx(end))
        return self.summary()

    def _reconcile_tx(self, now: datetime) -> None:
        with self.state.tx():
            self._reconcile(now)

    def _run_steps(self, a: datetime, b: datetime, active_only: bool) -> None:
        if active_only:
            pairs = sorted({p.pair for p in self.state.open_positions()})
        else:
            pairs = list(self.cfg.pairs)
        if not pairs or b <= a:
            return
        for step in self.view.minute_steps(pairs, a, b):
            self.process_step(step)


# ====================================================================== insa
def build_engine(cfg: EngineConfig, *, clock: Clock | None = None, view: MarketView | None = None,
                 broker: Broker | None = None, env: Mapping[str, str] | None = None) -> Engine:
    from .brokers.paper import PaperBroker, PaperConfig
    from .clock import SystemClock
    from .marketdata.sources import StoreSource

    env = os.environ if env is None else env
    strategy = get_strategy(cfg.strategy, mode=cfg.mode, ml_mode=cfg.ml_mode)
    clock = clock or SystemClock()
    view = view or StoreSource(cfg.market_db)
    if broker is None:
        broker = PaperBroker(PaperConfig(cost=cfg.cost, mmr=K.LOCKED_CFG.maint_margin_rate,
                                         wallet_start=cfg.wallet_start),
                             view.rules, view.funding, clock)
    for p in (cfg.ledger_path, cfg.state_path, cfg.status_path, cfg.kill_file, f"{cfg.pause_file}.{cfg.bot}"):
        Path(p).parent.mkdir(parents=True, exist_ok=True)
    led = L.open_ledger(cfg.ledger_path, cfg.bot, create=True, clock=(None if cfg.mode == "paper" else clock.now))
    state = StateStore(cfg.state_path, bot=cfg.bot)
    vsrc: VetoSource = FileVeto(veto.load_config(cfg.veto_config), env) if cfg.veto_mode == "required" else NoVeto()
    kill = Killswitch(cfg.kill_file, clock)
    pause = EntryPause(f"{cfg.pause_file}.{cfg.bot}", clock, audit_path=cfg.path("pause_audit.jsonl"), bot=cfg.bot)
    status = StatusWriter(cfg.status_path, clock, cfg)
    ml_model, ml_error = None, None
    if getattr(strategy, "ml_mode", "off") != "off":
        ml_model, ml_error = load_engine_model(cfg.ml_model_path, strategy.ml_mode, clock.now())
    signals = WindowedSignalSource(view, strategy, strict=False, ml_model=ml_model, ml_error=ml_error)
    return Engine(cfg, clock=clock, view=view, broker=broker, ledger=led, state=state, signals=signals,
                  strategy=strategy, veto=vsrc, kill=kill, status=status, pause=pause)
