"""Engine (05 §5): paper, backtest ve (Faz B) canli icin ayni dongu. Fark yalniz Broker/MarketView/Clock/SignalSource
enjeksiyonudur. Sira her karar adiminda: parametre yenile -> cikislar -> stop guncelle -> girisler. Risk sayisi yoktur."""
from __future__ import annotations

import logging
import os
from collections import Counter
from contextlib import nullcontext
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
from .errors import ClockError, ConfigError, EngineExit, FailClosed, StateError
from .holdout import check_holdout
from .gates import EntryGate, EntryOutcome, FileVeto, NoVeto, VetoSource, entry_leverage
from .killswitch import Killswitch
from .pause import EntryPause
from .marketdata.sources import MarketView, MinuteStep
from .order_manager import EXIT_RETRY_LIMIT, OrderManager
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
from .types import BrokerEvent, Fill, Intent, Position

log = logging.getLogger("engine")

ENGINE_VERSION = "05.1"
_REASONS = ("stop", "target", "trail_stop", "regime_flip", "time_stop", "manual", "force_exit", "liquidation", "other")
_STATUS_COUNTERS = ("callback_errors", "data_gaps", "ledger_errors", "outbox_failed", "unknown_orders", "mark_fallbacks",
                    "minute_gaps", "funding_missing", "exit_data_gap")
STARTUP_MAX_AGE_S = 300          # acilis kapisi: son kapanmis 1m (last+mark) en fazla bu kadar eski olabilir
EXIT_STARTUP_GATE = 7
FEED_MODES = ("paper", "testnet", "live")        # 11 §6.1: "feed'li canli dongu" (benzetimli broker ayrimi: is_paper)
_BROKER_REASONS = ("exchange_auth", "exchange_unknown_code", "working_type_unverified", "exchange_unreachable",
                   "exchange_rate_limited")


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
                 strict: bool = False, tick_fn=None, pause: EntryPause | None = None, reconciler=None) -> None:
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
        live = cfg.live
        self.orders = orders or OrderManager(cfg.bot, broker, state, clock, rules_fn)
        if not getattr(broker, "is_simulated", False):
            # 11 §6: canli yol (OrderManager bayraklari; kagit/backtest'te dokunulmaz)
            self.orders.live_mode = True
            self.orders.max_attempts = max(1, int(live.max_attempts)) if live is not None else 1
            if live is not None:
                self.orders.stop_deadline_s = float(live.stop_deadline_s)
                self.orders.entry_resolve_window_s = float(live.entry_resolve_window_s)
            self.orders.on_entry_adopted = self._on_adopted_entry
            self.orders.on_ban = self._note_ban
            self.orders.exit_fn = self._submit_exit                 # 11 §6.4/§8: piyasa cikislari tek yoldan (poll + ban penceresi)
            self.orders.close_unopened_fn = self._close_unopened    # giris penceresi kapanisi: defter duzeltmesi + _entry_events
        if tick_fn is not None:
            self.orders.tick_fn = tick_fn                    # legacy_compat: giris-ayi tarihsel tick
        self.gate = EntryGate(cfg, ledger, state, kill, veto, clock, broker, rules_fn, entry_ref_fn, pause)
        self.reconciler = reconciler if reconciler is not None else self._make_reconciler()
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
        self._consec: dict[str, int] = {}                       # canli: adim etiketi basina ardisik hata (merdiven)
        self._ban_seen: tuple | None = None                     # son islenen broker.last_ban belirteci
        self._stop = False
        self._last_now: datetime | None = None
        self._last_minute: datetime | None = None
        self._last_decision: datetime | None = None
        self._last_candle_open: datetime | None = None
        self._last_pre = None
        self._last_reconcile: datetime | None = None
        self._entry_events: dict[int, object] = {}
        self._started = False
        self._ban_until: datetime | None = None
        self._exit_throttle: dict[int, datetime] = {}
        self._naked_rows: list[dict] = []
        self._in_drain = 0

    def _make_reconciler(self):
        if self.is_paper:
            return Reconciler(self.cfg, self.broker, self.state, self.ledger, self.orders, self.clock)
        try:
            from .reconcile_live import LiveReconciler
        except ImportError:
            log.warning("reconcile_live yok: canli mutabakat kagit alt kumesiyle (B5 bekleniyor)")
            return Reconciler(self.cfg, self.broker, self.state, self.ledger, self.orders, self.clock)
        return LiveReconciler(self.cfg, self.broker, self.state, self.ledger, self.orders, self.clock, self.kill,
                              self.pause, handle_events=lambda evs, now: self._handle_events(evs, None, now),
                              close_unopened=self._close_unopened)

    # ================================================================== yardimcilar
    def _set_clock(self, t: datetime) -> None:
        if hasattr(self.clock, "set_time") and t > self.clock.now():
            self.clock.set_time(t)                              # type: ignore[attr-defined]

    def _persist(self, old: Position, new: Position) -> None:
        diff = {f.name: getattr(new, f.name) for f in fields(Position)
                if f.name != "trade_id" and getattr(new, f.name) != getattr(old, f.name)}
        if diff:
            with self.state.tx():
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
        with self.state.tx():
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

    def _outer_tx(self):
        """11 §6.1: benzetimli brokerda tek dis tx aynen; canlida YOK (her yazma grubu kendi tx'i)."""
        return self.state.tx() if self.is_paper else nullcontext()

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
            **({} if self.is_paper else {"exchange": self._exchange_status()}),
        }

    def _exchange_status(self) -> dict:
        h = {}
        try:
            h = dict(self.broker.health())
        except Exception:  # noqa: BLE001
            pass
        h["naked"] = list(self._naked_rows)
        return h

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
        pre = None
        if not self.is_paper and self.state.kv_get("day_start_date") != day:
            pre = self.broker.account().equity                 # canli: ag okumasi tx disinda
        with self.state.tx():
            cur = self.state.kv_get("day_start_date")
            if cur == day:
                return
            fresh = cur is None
            self.state.kv_set("day_start:" + day, pre if pre is not None else self.broker.account().equity)
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

    def protect_first(self):
        """11 §6.2 adim 2: veri kapisindan ONCE, piyasa verisi gerektirmez (yalniz canli). Stopsuz pozisyonu korur."""
        if self.is_paper:
            return None
        pf = getattr(self.reconciler, "protect_first", None)
        if pf is None:
            self.orders.resolve_unresolved()
            rep = None
        else:
            rep = pf()
        self._recover_orphan_opening()
        self._mirror_broker_blocks()
        return rep

    def _recover_orphan_opening(self) -> None:
        """G1 ile emir satiri arasinda cokme (11 §6.4 madde 6): `opening` + emir satiri yok + borsada pozisyon yok => kapat."""
        for p in self.state.open_positions():
            if p.status != "opening" or self.state.orders_for_trade(p.trade_id):
                continue
            if not self.orders._exchange_has_position(p.pair):   # noqa: SLF001
                self._close_unopened(p, self.clock.now())

    def start(self) -> RecoveryReport:
        cfg = self.cfg
        live_loop = not self.is_paper and cfg.mode in FEED_MODES
        if live_loop:
            self._clear_broker_latches()
        if cfg.mode in ("testnet", "live") and not self.is_paper:
            if not self.state.integrity_check():
                raise StateError("state integrity_check basarisiz")
            self.protect_first()
        if cfg.mode == "paper" or (live_loop and cfg.mode in ("testnet", "live")):
            self._startup_gate()                                  # 11 §6.2: canlida protect_first'ten SONRA, ayni 10/10 kapisi
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
        lev = entry_leverage(cfg)
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
        if cfg.mode in FEED_MODES and self._init_cursors():
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
        if not self.is_paper:
            self._after_live_reconcile(rep)
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
        self._consec[label] = 0
        return True

    def _after_failure(self, label: str, e: Exception) -> None:
        self._c["callback_errors"] += 1
        if self.is_paper:
            self._consec_errors += 1                          # kagit/backtest: eski davranis (herhangi bir basari sifirlar)
        else:
            # canli: basarili bir alt adim baska adimin hata sayacini sifirlayamaz (etiket basina sayac)
            self._consec[label] = self._consec.get(label, 0) + 1
            self._consec_errors = max(self._consec.values())
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
        if not self.is_paper:
            self._process_step_live(step, ts)
            return
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

    def _process_step_live(self, step, ts: datetime) -> None:
        """Canli dakika adimi (11 §6.2 madde 4): yalniz gun basi, MFE/MAE ve imlec. Olay/KILL live_tick'te."""
        self.ensure_day_start(ts)
        for p in self.state.open_positions():
            bar = step.bars.get(p.pair)
            if bar is not None and p.status in ("open", "closing"):
                self._persist(p, update_excursion(p, bar))
        with self.state.tx():
            for pair in self.cfg.pairs:
                c = self.state.get_cursor(pair, "minute")
                if c is None or ts > c:
                    self.state.set_cursor(pair, "minute", ts)
        self._last_minute = ts
        self._c["steps"] += 1

    def _kill_step(self, now: datetime) -> None:
        if self.kill.active():
            if self.state.kv_get("kill_seen_at") is None:
                with self.state.tx():
                    self.state.kv_set("kill_seen_at", iso_z(now))
                log.critical("KILL etkin: girisler kapali, acik pozisyonlar kapatiliyor")
            for p in self.state.open_positions():
                if p.status == "open" and p.qty:
                    self._submit_exit(p, "force_exit", now)
        elif self.state.kv_get("kill_seen_at") is not None:
            with self.state.tx():
                self.state.kv_set("kill_seen_at", None)
            log.warning("KILL kalkti: girisler bir sonraki karar adiminda yeniden acilir")

    def _submit_exit(self, pos: Position, reason: str, at: datetime):
        """Piyasa cikisi; canlida hemen poll (11 §5.3 not 2) ve olaylari isle."""
        if not self.is_paper and self._ban_until is not None and self.clock.now() < self._ban_until:
            self._c["ban_skipped_exits"] += 1          # pencere icinde gonderim zaten reddedilir; yeni kimlik/satir uretme
            return None
        if not self.is_paper and self.cfg.live is not None:
            # Fix 5: deneme limiti doldu (exit_unknown) -> KILL/watchdog her dakika degil `reconcile_open_s`te BIR gonderim
            n = int(self.state.kv_get(f"exit_retry:{pos.trade_id}", 0) or 0)
            if n >= EXIT_RETRY_LIMIT:
                now = self.clock.now()
                last = self._exit_throttle.get(pos.trade_id)
                if last is not None and (now - last).total_seconds() < float(self.cfg.reconcile_open_s):
                    self._c["exit_throttled"] += 1
                    return None
                self._exit_throttle[pos.trade_id] = now
        out = self.orders.submit_exit(pos, reason, at)
        if not self.is_paper:
            self._register(pos.trade_id)
            self._drain_events()
        return out

    def _drain_events(self) -> None:
        now = self.clock.now()
        self._handle_events(self.broker.poll(now), None, now)

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
                    self._persist(p, apply_funding(p, e))   # _persist kendi tx'ini acar
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
        t_fill = self.clock.now()
        newp = apply_entry_fill(pos, fill, step.bars.get(e.pair) if step is not None else None, now)
        with self.state.tx():                                   # G2: pozisyon open + emir filled + outbox
            self._persist(pos, newp)
            self._mark_order(fill.client_id, "filled")
            self.state.outbox_add("entry", pos.trade_id, build_trade_entry(newp))
        self._c["trades_opened"] += 1
        eq = self.state.kv_get(f"eq:{pos.trade_id}")
        tick = self.orders.stop_tick(newp)
        viol = fill_risk_violation(newp, float(eq), tick) if eq else None
        cur = self.state.get_position(pos.trade_id) or newp
        live = not self.is_paper
        if live:
            self._register(pos.trade_id)
        if viol:
            log.critical("dolum sonrasi risk ihlali (%s) trade %s: cikis", viol, pos.trade_id)
            self._c["fill_risk_violation"] += 1
            if live:
                # 11 §6.4 madde 4: once stop, sonra cikis (stopsuz `closing` pozisyon kalmaz)
                self.orders.place_initial_stop(cur, t_fill)
                self._register(pos.trade_id)
                cur = self.state.get_position(pos.trade_id) or cur
                if cur.status == "open":
                    self._submit_exit(cur, "other", now)
            else:
                self.orders.submit_exit(cur, "other", now)
        elif live:
            self.orders.place_initial_stop(cur, t_fill)
            self._register(pos.trade_id)
        else:
            self.orders.place_initial_stop(cur)

    def _on_exit_fill(self, e, step, now: datetime) -> None:
        fill = e.fill
        pos = self.state.position_for_pair(e.pair)
        if self._duplicate_exit(fill):
            self._c["duplicate_fill_ignored"] += 1
            return
        if pos is None or pos.status == "opening" or pos.entry_price is None:
            self._c["unexpected_fills"] += 1
            log.critical("beklenmeyen cikis dolumu %s", e.pair)
            return
        closed = apply_exit_fill(pos, fill, step.bars.get(e.pair) if step is not None else None, now)
        if e.detail == "foreign_close":                          # 11 §5.5 madde 3: bizim olmayan kapanis
            closed = replace(closed, exit_reason="manual")
            log.critical("yabanci kapanis %s trade %s: exit_reason=manual", e.pair, pos.trade_id)
        newp = close_position(pos, closed)
        with self.state.tx():                                   # G3
            self._persist(pos, newp)
            self.state.outbox_add("exit", pos.trade_id, build_trade_exit(pos, closed))
            self._mark_order(fill.client_id, "filled")
        self._c["trades_closed"] += 1
        if not self.is_paper and self.state.kv_get(f"naked:{pos.trade_id}") is not None:
            with self.state.tx():
                self.state.kv_set(f"naked:{pos.trade_id}", None)
        self.orders.cancel_resting(pos)

    def _duplicate_exit(self, fill) -> bool:
        """11 §6.6: ayni kapanis iki kez teslim edilirse (emir satiri filled, sahibi pozisyon closed) sessizce yok say."""
        row = self.state.get_order(fill.client_id) if fill.client_id else None
        if row is None or row.trade_id is None or row.status != "filled":
            return False
        owner = self.state.get_position(row.trade_id)
        return owner is not None and owner.status == "closed"

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
            with self.state.tx():
                self.state.update_position(pos.trade_id, status="open", exit_client_id=None, exit_reason=None)
            if not self.is_paper:
                self.orders._count_exit_failure(pos.trade_id)       # noqa: SLF001  F16: reddedilen cikis de sayilir
        elif row.role == "stop" and pos.status == "open":
            log.critical("stop reddedildi trade %s (%s): mutabakat yeniden kuracak", pos.trade_id, e.detail)
            self._block("stop_failed")

    def _close_unopened(self, pos: Position, now: datetime) -> None:
        with self.state.tx():
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
        with self._outer_tx():
            self.ensure_day_start(D)
            self._kill_step(now)
            if self.cfg.mode in FEED_MODES:
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
            with self.state.tx():                                   # G4: imecler
                for pair in self.cfg.pairs:
                    c = self.state.get_cursor(pair, "decision")
                    if c is None or D > c:
                        self.state.set_cursor(pair, "decision", D)
                if self.is_paper:
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
                    self._submit_exit(pos, dec.reason, D)
                elif dec.kind == "stop_update":
                    out = self.orders.replace_stop(pos, dec.new_stop)
                    if out.note == "would_trigger":
                        cur = self.state.get_position(pos.trade_id) or pos
                        if cur.status == "open":
                            self._submit_exit(cur, "trail_stop", D)
                    elif out.ok and not self.is_paper:
                        self._register(pos.trade_id)
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
            with self.state.tx():
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
        with self.state.tx():                                   # G1: giris niyeti (POST'tan once commit)
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
        if not self.is_paper:
            self._drain_events()                                # 11 §6.4: dolum ayni cagri zincirinde -> stop
            if res.status == "failed" and res.order.status == "unknown":
                return                                          # belirsiz giris: satir/pozisyon pencere boyunca kalir
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
                    if not self.is_paper and nxt < floor_tf(now, self.tf):
                        # 11 §6.2 madde 4: kacan karar barlari yeniden oynatilmaz; yalniz en son kapanmis bar degerlendirilir
                        self._c["skipped_decisions"] += 1
                        with self.state.tx():
                            for p in self.cfg.pairs:
                                c = self.state.get_cursor(p, "decision")
                                if c is None or nxt > c:
                                    self.state.set_cursor(p, "decision", nxt)
                    else:
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
                if not self.is_paper and self.cfg.mode in ("testnet", "live"):
                    self.live_tick(now)
                    self.clock.sleep(self.cfg.loop_sleep_s)
                    continue
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
        if self.cfg.mode not in ("paper", "testnet", "live"):
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
                with self._outer_tx():
                    self._reconcile(now)
            except StateError:
                raise
            except Exception as e:  # noqa: BLE001
                log.error("mutabakat hatasi: %r", e)

    def shutdown(self, reason: str) -> None:
        log.info("kapaniyor: %s", reason)
        if self.status is not None:
            self.status.write(self, force=True, stopped=True)


    # ================================================================== canli yol (11 §6)
    def live_tick(self, now: datetime) -> None:
        """Her dongude, veri akisindan bagimsiz: KILL -> olaylar -> stop bekcisi -> mutabakat -> advance_to -> status."""
        self._set_clock(now)
        self._guard("kill", lambda: self._kill_step(now))
        self._guard("events", lambda: self._drain_events())
        self._post_commit()
        self._guard("watchdog", lambda: self._stop_watchdog(self.clock.now()))
        self._guard("bans", self._sync_bans)
        self._mirror_broker_blocks()
        self._periodic_input_check(now)                        # 11 §6.3: kural/veri sayaclari dakikada bir
        every = self.cfg.reconcile_open_s if self.state.open_positions() or self.state.unresolved_orders() \
            else self.cfg.reconcile_flat_s
        if self._last_reconcile is None or (now - self._last_reconcile).total_seconds() >= every:
            self._guard("reconcile", lambda: self._reconcile(now))
        try:
            self.advance_to(now)
        except ClockError as e:
            log.critical("%s", e)
        if self.status is not None:
            self.status.write(self)

    def _stop_watchdog(self, now: datetime) -> None:
        """11 §6.5: borsada kabul edilmis stopu olmayan open/closing pozisyon stop_deadline_s'i (>) asarsa reduceOnly piyasa."""
        deadline = float(self.cfg.live.stop_deadline_s) if self.cfg.live is not None else 10.0
        rows: list[dict] = []
        for p in self.state.open_positions():
            if p.status not in ("open", "closing"):
                continue
            row = self.state.get_order(p.stop_client_id) if p.stop_client_id else None
            if row is not None and row.status == "accepted":
                if self.state.kv_get(f"naked:{p.trade_id}") is not None:
                    with self.state.tx():
                        self.state.kv_set(f"naked:{p.trade_id}", None)
                continue
            since_s = self.state.kv_get(f"naked:{p.trade_id}")
            if since_s is None:
                with self.state.tx():
                    self.state.kv_set(f"naked:{p.trade_id}", iso_z(now))
                since = now
            else:
                from .state import parse_iso_z
                since = parse_iso_z(since_s)
            secs = (now - since).total_seconds()
            rows.append({"trade_id": p.trade_id, "pair": p.pair, "seconds": secs})
            if secs > deadline:
                self._c["naked_closes"] += 1
                log.critical("stopsuz pozisyon %.1f sn (trade %s): piyasada kapatiliyor", secs, p.trade_id)
                if p.status == "open" and p.qty:
                    self._block("stop_failed")
                    self._submit_exit(p, "other", now)
        self._naked_rows = rows
        sn = getattr(self.broker, "set_naked", None)
        if callable(sn):
            sn(list(rows))

    def _register(self, trade_id: int) -> None:
        """LiveBroker.register_position: yetkili acilis zamani + pozisyona ait kimlikler (best-effort)."""
        reg = getattr(self.broker, "register_position", None)
        if not callable(reg):
            return
        try:
            p = self.state.get_position(trade_id)
            if p is None or p.entry_ts is None or p.status == "closed":
                return
            cids = [r.client_id for r in self.state.orders_for_trade(trade_id)]
            reg(p.pair, p.entry_ts, tuple(cids))
        except StateError:
            raise
        except Exception as e:  # noqa: BLE001
            log.warning("register_position basarisiz: %r", e)

    def _on_adopted_entry(self, row, bo) -> None:
        """Sorguyla (belirsizlik/yeniden baslatma sonrasi) bulunan dolu giris: dolum olayi uydur -> G2 + stop."""
        pos = self.state.get_position(row.trade_id) if row.trade_id is not None else None
        if pos is None or pos.status != "opening":
            return
        qty = bo.filled_qty if bo.filled_qty and bo.filled_qty > 0 else row.qty
        price = bo.avg_price
        if price is None:
            try:
                price = next((bp.entry_price for bp in self.broker.positions() if bp.pair == row.pair), None)
            except Exception:  # noqa: BLE001
                price = None
        if price is None or not qty:
            log.critical("bulunan giris dolumunun fiyati yok (%s): mutabakat cozecek", row.client_id)
            return
        now = self.clock.now()
        fee = float(qty) * float(price) * self.cfg.cost.taker_fee
        fill = Fill(client_id=row.client_id, pair=row.pair, role="entry", order_side=row.order_side, qty=float(qty),
                    price=float(price), fee=fee, ts=bo.updated_ts or now, reason="market")
        with self.state.tx():
            self.state.kv_set(f"entry_fee_estimated:{row.trade_id}", True)      # ucret tahmini (gercek komisyon bilinmiyor)
        self._on_entry_fill(BrokerEvent("fill", fill.ts, row.pair, row.client_id, fill), None, now)

    def _ban_token(self) -> tuple:
        lb = getattr(self.broker, "last_ban", None)
        bans = 0
        bc = getattr(self.broker, "counters", None)
        if callable(bc):
            try:
                bans = int(bc().get("exchange_bans", 0))
            except Exception:  # noqa: BLE001
                bans = 0
        return (lb, bans)

    def _note_ban(self) -> None:
        """exchange_ban / rate_limited reti hemen sonrasi (emir yolu)."""
        self._apply_ban()
        self._ban_seen = self._ban_token()

    def _sync_bans(self) -> None:
        """11 §10 F8-F11: ban HER yolda (okuma dahil) gorulur: her live_tick'te broker.last_ban son gorulenle karsilastirilir."""
        tok = self._ban_token()
        if tok == self._ban_seen:
            return
        self._ban_seen = tok
        if tok[0] is not None or tok[1]:
            self._apply_ban()

    def _apply_ban(self) -> None:
        """broker.last_ban'dan (http, retry_after_s) zamanla: 429 -> engel + pencere; 418/403/451 -> exchange_ban tutusu."""
        now = self.clock.now()
        lb = getattr(self.broker, "last_ban", None)
        http, ra = (lb if lb else (None, None))
        until = now + timedelta(seconds=float(ra if ra else 1.0))
        if self._ban_until is None or until > self._ban_until:
            self._ban_until = until
        self._c["exchange_ban_rejects"] += 1
        if http == 429 and not self.state.kv_get("entries_blocked_reason"):
            self._block("exchange_rate_limited")
        elif http in (418, 403, 451) and self.pause is not None:
            try:
                self.pause.add("exchange_ban", by="engine:orders", note=f"http={http} retry_after={ra}")
            except Exception as e:  # noqa: BLE001
                log.error("pause.add basarisiz: %r", e)

    def _clear_broker_latches(self) -> None:
        """Temiz yeniden baslatma: brokerin bellek-ici yapiskan nedenleri sifirlanir; kv'ye yansiyanlar da (11 §5)."""
        cur = self.state.kv_get("entries_blocked_reason")
        if cur in _BROKER_REASONS:
            with self.state.tx():
                self.state.kv_set("entries_blocked_reason", None)

    def _mirror_broker_blocks(self) -> None:
        """Brokerin giris engeli (exchange_auth, ...) kapi icin kv'ye yansitilir (baska nedeni ezmez). exchange_auth ayrica
        yapiskan duraklatma tutusu olarak EKLENIR (11 §10 F9; kaldirma yalniz cli)."""
        brs = tuple(getattr(self.broker, "entries_blocked_reasons", ()) or ())
        if "exchange_auth" in brs and self.pause is not None:
            try:
                self.pause.add("exchange_auth", by="engine:broker", note="broker exchange_auth")
            except Exception as e:  # noqa: BLE001
                log.error("pause.add basarisiz: %r", e)
        br = getattr(self.broker, "entries_blocked_reason", None)
        if not br:
            return
        cur = self.state.kv_get("entries_blocked_reason")
        if cur is None:
            self._block(str(br))

    def _after_live_reconcile(self, rep) -> None:
        """B4'un kendi exchange_unreachable mandali: yalniz temiz mutabakattan sonra, broker kendininkini kaldirdiysa temizlenir."""
        cur = self.state.kv_get("entries_blocked_reason")
        reasons = tuple(getattr(self.broker, "entries_blocked_reasons", ()) or ())
        if "exchange_unreachable" in reasons or "exchange_unreachable" in getattr(rep, "findings", ()):
            if cur is None:
                self._block("exchange_unreachable")
            return
        # tur okumalarini tamamladi (temiz mutabakat = okumalar bitti; bulgu varligi temizlemeyi engellemez, 11 §8)
        if cur == "exchange_unreachable" or (cur == "exchange_rate_limited" and (
                self._ban_until is None or self.clock.now() >= self._ban_until)):
            with self.state.tx():
                self.state.kv_set("entries_blocked_reason", None)
        self._mirror_broker_blocks()

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
        if self.cfg.mode not in FEED_MODES:
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
def _build_live_broker(cfg: EngineConfig, clock: Clock | None, env: Mapping[str, str]):
    """11 §6.2 adim 1: load_keys -> SignedRestClient -> LiveBroker -> startup_check (EngineExit 8/5)."""
    from .brokers.binance_futures import LiveBroker
    from .clock import SystemClock
    from .config import check_live_confirm, load_keys
    from .exchange.binance_rest import SignedRestClient
    if cfg.live is None:
        raise ConfigError("live blogu yok")
    check_live_confirm(cfg, env)                     # kanonik sira: once onay, sonra anahtarlar (11 §3)
    key, secret = load_keys(env)                     # ConfigError("keys_missing: ...") aynen
    clk = clock or SystemClock()
    rest = SignedRestClient(env=cfg.mode, api_key=key, api_secret=secret,
                            now_ms=lambda: int(clk.now().timestamp() * 1000), sleep=clk.sleep,
                            recv_window_ms=cfg.live.recv_window_ms, conditional_mode=cfg.live.conditional_mode)
    broker = LiveBroker(cfg.live, cfg.mode, cfg.leverage, cfg.pairs, rest, clk, cfg.cost.taker_fee, environ=env)
    broker.startup_check()
    return broker


def _check_rules_drift(broker, view, cfg: EngineConfig) -> None:
    chk = getattr(broker, "check_rules_drift", None)
    if cfg.mode != "live" or not callable(chk):
        return
    try:
        feed = {p: view.rules(p) for p in cfg.pairs}
        for d in chk(feed):
            log.warning("%s", d)
    except Exception as e:  # noqa: BLE001
        log.warning("kural karsilastirmasi yapilamadi: %r", e)


def build_engine(cfg: EngineConfig, *, clock: Clock | None = None, view: MarketView | None = None,
                 broker: Broker | None = None, env: Mapping[str, str] | None = None) -> Engine:
    from .brokers.paper import PaperBroker, PaperConfig
    from .clock import SystemClock
    from .marketdata.sources import StoreSource

    env = os.environ if env is None else env
    if cfg.mode == "live":
        from .config import check_live_confirm
        check_live_confirm(cfg, env)                 # ag oncesi cift onay (11 §3.1)
    if cfg.mode in ("testnet", "live") and broker is None:
        from .config import load_keys
        load_keys(env)                               # ConfigError("keys_missing: ...") aynen (11 §3.2)
    live_broker_new = False
    if cfg.mode in ("testnet", "live") and broker is None:
        broker, live_broker_new = _build_live_broker(cfg, clock, env), True
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
    ml_v2 = None
    v2_on = getattr(strategy, "ml_mode", "off") != "off" and cfg.ml_features != "v1"     # ML-G5 bayragi (varsayilan kapali)
    if getattr(strategy, "ml_mode", "off") != "off":
        if v2_on:
            from trader_core.ml_live_v2 import RECIPE_NAMES, LiveContextV2, funding_frame_from_points
            ml_model, ml_error = load_engine_model(cfg.ml_model_path, strategy.ml_mode, clock.now(),
                                                   expected_features=RECIPE_NAMES[cfg.ml_features])
            # >= 200 gun kapanmis 1s mum (r02/r03 1g baglam): cift basina 5000 mum tutulur (~2 MB / 10 cift); ilk karar adiminda yuklenir
            ml_v2 = LiveContextV2(
                cfg.ml_features, cfg.pairs,
                lambda p, D, n: view.bars(p, "1h", D, n),
                lambda p, a, b: funding_frame_from_points(view.funding(p, a, b)))
            try:
                ml_v2.refresh(clock.now())                # baslangic yuklemesi (best-effort; karar adiminda yeniden denenir)
            except Exception as e:  # noqa: BLE001
                log.warning("ML v2 baslangic gecmisi yuklenemedi: %s: %s", type(e).__name__, e)
        else:
            ml_model, ml_error = load_engine_model(cfg.ml_model_path, strategy.ml_mode, clock.now())
    signals = WindowedSignalSource(view, strategy, strict=False, ml_model=ml_model, ml_error=ml_error,
                                   ml_v2=ml_v2, pairs=cfg.pairs if ml_v2 is not None else None)
    if live_broker_new:
        _check_rules_drift(broker, view, cfg)
    return Engine(cfg, clock=clock, view=view, broker=broker, ledger=led, state=state, signals=signals,
                  strategy=strategy, veto=vsrc, kill=kill, status=status, pause=pause)
