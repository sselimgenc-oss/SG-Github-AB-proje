"""Risk kademe denetimi calisma zamani sarmalayicisi (docs/motor/12-risk-kademe.md §8): `RiskLadder`.

Motor bu sinifi her karar adiminda ve canli dongude `tick` ile besler; kapi (`gate_code`), etkin risk (`risk_config`) ve
durum (`status`) buradan okunur. Risk sayisi YOKTUR: basamaklar/esikler `trader_core.risk_ladder` kod sabitleridir.
Motor yalniz `step_down`/`review_stop`/`floor_stop`/`peak` satirlari yazar ve duraklatma tutusu KURAR; tutus kaldirmak,
sermaye/devam/yeniden baslatma satiri yazmak yalniz CLI'nin (ve Telegram'in) isidir. Paper kipi GOZLEM'dir (enforce=False).
"""
from __future__ import annotations

import logging
from collections import Counter
from collections.abc import Callable, Sequence
from datetime import datetime, timedelta
from typing import Any

from trader_core import risk_ladder as RL
from trader_core.risk import RiskConfig

from .clock import Clock
from .config import EngineConfig
from .errors import ConfigError
from .pause import EntryPause

log = logging.getLogger("engine.ladder")

BY = "engine:rk1"
COUNTERS_EVERY_S = 600.0
GATE_ORDER = ("capital_missing", "ladder_invalid", "equity_unreadable", "capital_mismatch", "capital_unverified")


def _ok_num(x: Any) -> bool:
    return RL.finite_number(x)


class RiskLadder:
    def __init__(self, cfg: EngineConfig, clock: Clock, pause: EntryPause | None, *, log: RL.LadderLog,
                 enforce: bool, follow: RL.LadderLog | None = None,
                 transfers_fn: Callable[[datetime, datetime], list] | None = None,
                 trades_fn: Callable[[datetime], Sequence] | None = None) -> None:
        if enforce and pause is None:
            raise ConfigError("risk kademe zorlamasi icin duraklatma (pause) zorunlu")
        self.cfg = cfg
        self.clock = clock
        self.pause = pause
        self.log = log
        self.enforce = bool(enforce)
        self.follow = follow
        self.transfers_fn = transfers_fn
        self.trades_fn = trades_fn
        self.counters: Counter = Counter()
        self._last_eval: datetime | None = None
        self._st: RL.LadderState | None = None
        self._state_kind = "uninitialized"           # ok | review | floor | uninitialized | invalid
        self._loaded = False
        self._gate: str | None = None
        self._gate_since: datetime | None = None
        self._equity: float | None = None
        self._pend_key: tuple | None = None
        self._pend_n = 0
        self._xfers: list | None = None
        self._xfer_ok_at: datetime | None = None
        self._xfer_checked_at: datetime | None = None
        self._match: RL.MatchResult | None = None
        self._init_mismatch = False
        self._peak_day: str | None = None
        self._would: dict | None = None
        self._retry: tuple[str, dict] | None = None
        self._cnt: dict | None = None
        self._cnt_at: datetime | None = None
        self._follow_state: dict | None = None
        self._follow_cfg: RiskConfig | None = None

    # ================================================================== kapi / etkin risk
    def gate_code(self) -> str | None:
        return self._gate if self.enforce else None

    @property
    def risk_config(self) -> RiskConfig:
        base = self.cfg.risk_config
        if self.follow is not None:
            if self._follow_cfg is None:
                self._refresh_follow()
            return self._follow_cfg if self._follow_cfg is not None else base
        if not self.enforce:
            return base                                   # gozlem: kagit sonuclari bit-bit ayni
        if not self._loaded:
            self._load()
        if self._st is None:
            return base
        return RL.step_config(base, self._st.step)

    def _refresh_follow(self) -> None:
        base = self.cfg.risk_config
        try:
            fst = self.follow.state() if self.follow is not None else None
            if fst is None:
                raise RL.LadderLogError("izlenen gunluk bos/yok")
            step = fst.step if fst.status == "ok" else min(fst.step, 0)
            self._follow_cfg = RL.step_config(base, step)
            self._follow_state = {"step": step, "ok": True}
        except Exception:  # noqa: BLE001 - izlenen okunamiyor: yapilandirma riski
            self.counters["ladder_follow_unreadable"] += 1
            self._follow_cfg = base
            self._follow_state = {"step": None, "ok": False}

    # ================================================================== durum okuma
    def _load(self) -> list[dict] | None:
        """Gunlugu okur ve katlar; durum etiketini ayarlar. -> satirlar (ok) ya da None (yok/bozuk)."""
        self._loaded = True
        try:
            rows = self.log.rows()
            st = RL.fold(rows)
        except Exception as e:  # noqa: BLE001 - LadderLogError ya da okuma hatasi: fail-closed
            self._st = None
            self._state_kind = "invalid"
            if not isinstance(e, RL.LadderLogError):
                log.error("kademe gunlugu okunamadi: %r", e)
            return None
        self._st = st
        self._state_kind = "uninitialized" if st is None else st.status
        return rows if st is not None else None

    def _set_gate(self, code: str | None, now: datetime) -> None:
        if code != self._gate:
            self._gate = code
            self._gate_since = now if code is not None else None

    def _write(self, kind: str, now: datetime, **fields: Any) -> bool:
        """Satir yazar; yazilamazsa CRITICAL ve (stop/inis icin) sonraki degerlendirmede yeniden denenir."""
        try:
            self.log.append(kind, BY, now, **fields)
            return True
        except Exception as e:  # noqa: BLE001 - satir yazilamasa da tutus kurulur
            log.critical("kademe satiri yazilamadi (%s): %r", kind, e)
            self.counters["ladder_write_errors"] += 1
            if kind != "peak":
                self._retry = (kind, fields)
            return False

    # ================================================================== degerlendirme
    def tick(self, now: datetime, equity: float, wallet: float, *, flat: bool = False) -> None:
        """12 §8.2. Hicbir istisna disari sizmaz."""
        try:
            self._tick(now, equity, wallet, flat)
        except Exception as e:  # noqa: BLE001
            self.counters["ladder_errors"] += 1
            log.critical("kademe degerlendirmesi hatasi: %r", e, exc_info=True)
            self._state_kind = "invalid"
            self._set_gate("ladder_invalid", now)

    def _tick(self, now: datetime, equity: float, wallet: float, flat: bool) -> None:
        if self._last_eval is not None and (now - self._last_eval).total_seconds() < RL.EVAL_EVERY_S:
            return                                                                            # 1: kisma
        self._last_eval = now
        if self.follow is not None:
            self._refresh_follow()
        rows = self._load()                                                                   # 2: gunluk
        if self._state_kind == "uninitialized":
            self._pend_key, self._pend_n = None, 0
            self._set_gate("capital_missing", now)
            return
        if self._state_kind == "invalid" or rows is None or self._st is None:
            self._pend_key, self._pend_n = None, 0
            self._set_gate("ladder_invalid", now)
            return
        st = self._st
        self._equity = float(equity) if _ok_num(equity) and equity > 0 else None
        if self.enforce:                                                                      # 3: tutus degismezi
            self._hold_invariant(st)
        if st.status == "floor":
            self._pend_key, self._pend_n = None, 0
            self._set_gate(None, now)
            self._refresh_counters(now, st)
            return
        if self._retry is not None:
            st = self._do_retry(now, st) or st
            rows = self.log.rows() if self._st is not None else rows
        unverified, mismatch = False, False
        if self.enforce and self.transfers_fn is not None:                                    # 4: aktarim (yalniz canli)
            unverified, mismatch = self._transfers(now, rows, wallet, flat)
        if self._equity is None:                                                              # 5: ozsermaye
            self._pend_key, self._pend_n = None, 0
            self._set_gate("equity_unreadable", now)
            return
        if mismatch:                                                                          # 6: uyusmazlik
            self._pend_key, self._pend_n = None, 0
            self._set_gate("capital_mismatch", now)
            return
        self._set_gate("capital_unverified" if unverified else None, now)
        eq = self._equity
        if st.status == "ok":                                                                 # 7: tepe
            st = self._peak(now, st, eq)
        self._trigger(now, st, eq)                                                            # 8: tetik + onay
        self._refresh_counters(now, self._st or st)                                           # 9: sayaclar

    # -- 3 -----------------------------------------------------------------
    def _hold_invariant(self, st: RL.LadderState) -> None:
        if self.pause is None:
            return
        try:
            if st.status == "review":
                self.pause.add("drawdown_review", BY, f"base={st.base:.2f} (gunluk: inceleme)")
            elif st.status == "floor":
                self.pause.add("capital_floor", BY, f"dep_net={st.dep_net:.2f} (gunluk: taban)")
        except Exception as e:  # noqa: BLE001
            log.critical("kademe tutusu kurulamadi: %r", e)

    # -- 4 -----------------------------------------------------------------
    def _transfers(self, now: datetime, rows: list, wallet: float, flat: bool) -> tuple[bool, bool]:
        st = self._st
        assert st is not None and self.transfers_fn is not None
        if self._xfer_ok_at is None or (now - self._xfer_ok_at).total_seconds() >= RL.XFER_POLL_S:
            try:
                since = max(st.started_at, now - timedelta(seconds=RL.XFER_WINDOW_S))
                self._xfers = list(self.transfers_fn(since, now))
                self._xfer_ok_at = now
                self._xfer_checked_at = now
            except Exception as e:  # noqa: BLE001 - onceki sonuc korunur
                self.counters["transfer_poll_errors"] += 1
                log.warning("aktarim yoklamasi basarisiz: %r", e)
        unverified = self._xfers is None or self._xfer_ok_at is None or \
            (now - self._xfer_ok_at).total_seconds() > RL.XFER_STALE_S
        if self._xfers is not None:
            self._match = RL.match_transfers(rows, self._xfers, now)
        mismatch = self._match is not None and not self._match.ok
        self._init_mismatch = False
        if not mismatch and flat and RL.init_wallet_mismatch(rows, wallet) and not self._closed_since(st):
            self._init_mismatch = True
            mismatch = True
        return unverified, mismatch

    def _closed_since(self, st: RL.LadderState) -> bool:
        if self.trades_fn is None:
            return False
        try:
            return len(self.trades_fn(st.started_at)) > 0
        except Exception as e:  # noqa: BLE001 - belirsiz: denetim atlanir (yalniz gevsetir degil, sikilastirmaz)
            log.warning("kapanmis islem sayisi okunamadi: %r", e)
            return True

    # -- retry -------------------------------------------------------------
    def _do_retry(self, now: datetime, st: RL.LadderState) -> RL.LadderState | None:
        kind, fields = self._retry or (None, None)
        if kind is None:
            return None
        try:
            self.log.append(kind, BY, now, **fields)
        except RL.LadderLogError:
            self._retry = None                                   # durum bu arada degisti (CLI): satir gecersiz
            log.warning("kademe satiri yeniden denemesi gecersiz, birakildi: %s", kind)
        except Exception as e:  # noqa: BLE001
            log.critical("kademe satiri yeniden yazilamadi (%s): %r", kind, e)
            return None
        else:
            self._retry = None
        self._load()
        return self._st

    # -- 7 -----------------------------------------------------------------
    def _peak(self, now: datetime, st: RL.LadderState, eq: float) -> RL.LadderState:
        day = now.strftime("%Y-%m-%d")
        if self._peak_day == day:
            return st
        if eq > st.peak:
            if not self._write("peak", now, value=eq):
                return st
            self._load()
        self._peak_day = day
        return self._st or st

    # -- 8 -----------------------------------------------------------------
    def _trigger(self, now: datetime, st: RL.LadderState, eq: float) -> None:
        acts = RL.evaluate(st, eq)
        if not acts:
            self._pend_key, self._pend_n = None, 0
            return
        a = acts[0]
        key = (a.kind, a.trigger)
        self._pend_n = self._pend_n + 1 if key == self._pend_key else 1
        self._pend_key = key
        if self._pend_n < RL.CONFIRM_N:
            return
        self._pend_key, self._pend_n = None, 0
        self._apply(now, st, a, eq)

    def _apply(self, now: datetime, st: RL.LadderState, a: RL.Action, eq: float) -> None:
        if a.kind == "step_down":
            self._write("step_down", now, step=a.step, trigger=a.trigger, equity=eq, peak=st.peak)
            log.warning("kademe indi: %s -> %s (%s, ozsermaye %.2f, tepe %.2f)", RL.STEP_NAMES[st.step],
                        RL.STEP_NAMES[a.step], a.trigger, eq, st.peak)
        elif a.kind == "review_stop":
            self._write("review_stop", now, equity=eq, base=st.base)
            log.critical("-%%20 durma: ozsermaye %.2f <= taban %.2f x %.2f; giris kapali (inceleme)", eq, st.base,
                         RL.STOP_RATIO)
            if self.enforce and self.pause is not None:
                self._add_hold("drawdown_review", f"base={st.base:.2f} equity={eq:.2f}")
        elif a.kind == "floor_stop":
            self._write("floor_stop", now, equity=eq, dep_net=st.dep_net)
            log.critical("son taban: ozsermaye %.2f <= yatirilan %.2f x %.2f; giris kapali", eq, st.dep_net,
                         RL.FLOOR_RATIO)
            if self.enforce and self.pause is not None:
                self._add_hold("capital_floor", f"dep_net={st.dep_net:.2f} equity={eq:.2f}")
        self._would = {"kind": a.kind, "at": RL.fmt_at(now)} if not self.enforce else self._would
        self._load()

    def _add_hold(self, reason: str, note: str) -> None:
        try:
            self.pause.add(reason, BY, note)                     # type: ignore[union-attr]
        except Exception as e:  # noqa: BLE001
            log.critical("tutus kurulamadi %s: %r", reason, e)

    # -- 9 -----------------------------------------------------------------
    def _refresh_counters(self, now: datetime, st: RL.LadderState) -> None:
        if self.trades_fn is None:
            return
        if self._cnt_at is not None and (now - self._cnt_at).total_seconds() < COUNTERS_EVERY_S:
            return
        try:
            self._cnt = RL.counters(self.trades_fn(st.started_at), st, now)
            self._cnt_at = now
        except Exception as e:  # noqa: BLE001
            self.counters["ladder_counter_errors"] += 1
            log.warning("kademe sayaclari yenilenemedi: %r", e)

    # ================================================================== durum
    def status(self) -> dict:
        """12 §10 `risk_ladder` blogu."""
        if not self._loaded:
            self._load()
        st = self._st
        eq = self._equity
        kind = self._state_kind
        d: dict[str, Any] = {"enforce": self.enforce, "state": kind}
        if st is None:
            d.update({k: None for k in ("step", "step_name", "step_risk", "lowest_step", "step_since", "started_at",
                                        "dep_net", "base", "peak", "dd_base_pct", "dd_peak_pct", "stop_at", "floor_at",
                                        "near", "stopped_at", "last_down_at", "log_seq", "log_hash")})
            d["equity"] = eq
        else:
            d.update({
                "step": st.step, "step_name": RL.STEP_NAMES[st.step], "step_risk": RL.STEPS[st.step],
                "lowest_step": RL.lowest(st.dep_net), "step_since": RL.fmt_at(st.step_since),
                "started_at": RL.fmt_at(st.started_at), "dep_net": st.dep_net, "base": st.base, "peak": st.peak,
                "equity": eq,
                "dd_base_pct": None if eq is None else max(0.0, (st.base - eq) / st.base * 100.0),
                "dd_peak_pct": None if eq is None else max(0.0, (st.peak - eq) / st.peak * 100.0),
                "stop_at": round(RL.STOP_RATIO * st.base, 8), "floor_at": round(RL.FLOOR_RATIO * st.dep_net, 8),
                "near": None if eq is None else eq <= round(RL.NEAR_RATIO * st.base, 8),
                "stopped_at": None if st.stopped_at is None else RL.fmt_at(st.stopped_at),
                "last_down_at": None if st.last_down_at is None else RL.fmt_at(st.last_down_at),
                "log_seq": st.seq, "log_hash": st.head_hash[:8]})
        try:
            d["effective_risk"] = self.risk_config.target_trade_risk
        except Exception:  # noqa: BLE001
            d["effective_risk"] = None
        d["gate_code"] = self.gate_code()
        d["gate_since"] = None if self._gate_since is None or self.gate_code() is None else RL.fmt_at(self._gate_since)
        if self.transfers_fn is not None:
            d["transfer"] = {"checked_at": None if self._xfer_checked_at is None else RL.fmt_at(self._xfer_checked_at),
                             "ok": None if self._match is None else bool(self._match.ok) and not self._init_mismatch,
                             "unmatched": 0 if self._match is None else
                             len(self._match.unmatched_exchange) + len(self._match.unmatched_log),
                             "detail": "init_wallet" if self._init_mismatch else None}
        else:
            d["transfer"] = None
        d["pending"] = self._pend_key[0] if (self._pend_key is not None and self._pend_n > 0) else None
        d["would"] = None if self.enforce else self._would
        d["follow"] = self._follow_state if self.follow is not None else None
        d["counters"] = self._cnt
        return d
