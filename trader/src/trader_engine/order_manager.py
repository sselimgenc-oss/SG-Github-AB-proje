"""Idempotent emir yoneticisi (04 §4): pending-once, belirsizlik yolu, stop degistirme."""
from __future__ import annotations

import hashlib
import logging
from dataclasses import dataclass
from datetime import datetime
from typing import Callable, Literal

from .clock import Clock
from .errors import BrokerUncertain, StateError
from .numeric import is_multiple, round_tight
from .state import OrderRow, StateStore, iso_z
from .types import (BrokerOrder, Intent, OrderRequest, OrderResult, Position, Role, Side, SymbolRules,
                    order_side_for, require_utc)

log = logging.getLogger(__name__)

_ROLE_LETTER = {"entry": "e", "stop": "s", "target": "t", "exit": "x"}
_BO_STATUS = {"filled": "filled", "new": "accepted", "canceled": "canceled", "rejected": "rejected",
              "expired": "expired"}
_OK = ("accepted", "filled")
_EXIT_RETRY_LIMIT = 3

__all__ = ["make_client_id", "OrderRow", "SubmitOutcome", "OrderManager"]


def make_client_id(bot: str, role: Role, pair: str, side: Side, signal_bar_close_ts: datetime, seq: int) -> str:
    if role not in _ROLE_LETTER:
        raise ValueError(f"gecersiz role: {role!r}")
    if side not in ("long", "short"):
        raise ValueError(f"gecersiz side: {side!r}")
    if isinstance(seq, bool) or not isinstance(seq, int) or seq < 0:
        raise ValueError(f"seq >= 0 tamsayi olmali: {seq!r}")
    require_utc(signal_bar_close_ts, "signal_bar_close_ts")
    letter = _ROLE_LETTER[role]
    raw = f"{bot}|{pair}|{side}|{iso_z(signal_bar_close_ts)}|{letter}|{seq}"
    h = hashlib.sha1(raw.encode("utf-8")).hexdigest()[:24]
    return "tr" + ("L" if bot == "learner" else "T") + letter + "-" + h


@dataclass(frozen=True)
class SubmitOutcome:
    ok: bool
    status: Literal["filled", "accepted", "rejected", "failed"]
    order: OrderRow
    result: OrderResult | None
    note: str | None


class OrderManager:
    def __init__(self, bot: str, broker, state: StateStore, clock: Clock,
                 rules_fn: Callable[[str], SymbolRules], unknown_grace_s: float = 2.0, max_attempts: int = 2) -> None:
        self.bot = bot
        self.broker = broker
        self.state = state
        self.clock = clock
        self.rules_fn = rules_fn
        self.unknown_grace_s = unknown_grace_s
        self.max_attempts = max(1, int(max_attempts))
        self.tick_fn: Callable[[str, datetime], float] | None = None   # yalniz legacy_compat: giris-ayi tarihsel tick

    def stop_tick(self, pos: Position) -> float:
        """Stop yuvarlama tick'i: native = borsa kurali; legacy_compat = pozisyonun GIRIS ayinin tarihsel tick'i."""
        if self.tick_fn is not None and pos.entry_ts is not None:
            return self.tick_fn(pos.pair, pos.entry_ts)
        return self.rules_fn(pos.pair).tick
    # ------------------------------------------------------------------ yardimcilar
    def _call(self, req: OrderRequest) -> OrderResult:
        if req.role in ("entry", "exit"):
            return self.broker.market_order(req)
        if req.role == "stop":
            return self.broker.place_stop(req)
        return self.broker.place_target(req)

    def _send(self, req: OrderRequest) -> OrderResult | None:
        """POST oncesi commit citi; belirsizlikte None (= unknown)."""
        self.state.barrier(allow_outer=bool(getattr(self.broker, "is_simulated", False)))
        try:
            res = self._call(req)
        except StateError:
            raise
        except BrokerUncertain:
            return None
        except Exception as e:  # noqa: BLE001 - bilinmeyen hata = belirsiz (kor tekrar yok)
            log.warning("broker istisnasi %s: %r", req.client_id, e)
            return None
        if res.status == "unknown":
            return None
        return res

    def _query(self, pair: str, cid: str) -> tuple[bool, BrokerOrder | None]:
        """(sorgu_basarili, emir). Basarisiz sorgu 'emir yok' teyidi degildir."""
        try:
            return True, self.broker.query(pair, cid)
        except StateError:
            raise
        except Exception as e:  # noqa: BLE001
            log.warning("query hatasi %s: %r", cid, e)
            return False, None

    def _upd(self, cid: str, **f) -> OrderRow:
        with self.state.tx():
            self.state.update_order(cid, updated_ts=self.clock.now(), **f)
        row = self.state.get_order(cid)
        assert row is not None
        return row

    def _pupd(self, trade_id: int, **f) -> None:
        """Pozisyon satiri varsa gunceller (yoksa sessiz)."""
        with self.state.tx():
            if self.state.get_position(trade_id) is not None:
                self.state.update_position(trade_id, **f)

    def _req_from_row(self, row: OrderRow) -> OrderRequest:
        lev = None
        if row.role == "entry" and row.trade_id is not None:
            p = self.state.get_position(row.trade_id)
            lev = p.leverage if p else None
        return OrderRequest(client_id=row.client_id, pair=row.pair, role=row.role, order_side=row.order_side,
                            qty=row.qty, trigger_price=row.trigger_price, reduce_only=row.reduce_only, leverage=lev,
                            signal_bar_close_ts=row.signal_bar_close_ts, created_ts=row.created_ts)

    def _outcome(self, row: OrderRow, result: OrderResult | None, note: str | None) -> SubmitOutcome:
        if row.status in _OK:
            return SubmitOutcome(True, row.status, row, result, note)  # type: ignore[arg-type]
        st = "failed" if row.status in ("failed", "unknown", "pending") else "rejected"
        return SubmitOutcome(False, st, row, result, note)  # type: ignore[arg-type]

    def _apply_result(self, row: OrderRow, res: OrderResult, note: str | None) -> SubmitOutcome:
        if res.status == "filled":
            row = self._upd(row.client_id, status="filled", broker_order_id=res.order_id)
        elif res.status == "accepted":
            row = self._upd(row.client_id, status="accepted", broker_order_id=res.order_id)
        else:  # rejected
            if res.reason == "duplicate_client_id":
                ok, bo = self._query(row.pair, row.client_id)
                if bo is not None:
                    return self._adopt(row, bo, "duplicate_adopted")
            row = self._upd(row.client_id, status="rejected", detail=res.reason)
            if note is None and res.reason == "would_trigger":
                note = "would_trigger"
            elif note is None:
                note = res.reason
        return self._outcome(row, res, note)

    def _adopt(self, row: OrderRow, bo: BrokerOrder, note: str) -> SubmitOutcome:
        st = _BO_STATUS.get(bo.status, "accepted")
        row = self._upd(row.client_id, status=st, broker_order_id=row.broker_order_id)
        return self._outcome(row, None, note)

    # ------------------------------------------------------------------ ortak gonderim
    def _submit(self, req: OrderRequest, seq: int, trade_id: int | None) -> SubmitOutcome:
        cid = req.client_id
        existing = self.state.get_order(cid)
        if existing is not None:
            return self._existing(existing)
        now = self.clock.now()
        row = OrderRow(client_id=cid, pair=req.pair, role=req.role, order_side=req.order_side, qty=req.qty,
                       trigger_price=req.trigger_price, reduce_only=req.reduce_only, status="pending",
                       signal_bar_close_ts=req.signal_bar_close_ts, seq=seq, attempts=0, trade_id=trade_id,
                       broker_order_id=None, detail=None, created_ts=now, updated_ts=now)
        with self.state.tx():
            self.state.insert_order(row)          # POST'tan once commit
        res = self._send(req)
        if res is None:
            return self._unknown_path(row, req)
        out = self._apply_result(row, res, None)
        return self._after(out, trade_id)

    def _existing(self, row: OrderRow) -> SubmitOutcome:
        if row.status in ("pending", "unknown"):
            out = self._resolve_row(row)
            return out
        o = self._outcome(row, None, "duplicate_adopted" if row.status in _OK else None)
        return o

    def _unknown_path(self, row: OrderRow, req: OrderRequest) -> SubmitOutcome:
        row = self._upd(row.client_id, status="unknown")
        attempts = row.attempts
        while True:
            ok, bo = self._query(req.pair, req.client_id)
            if not ok:
                self._block("order_unknown")
                return self._outcome(row, None, "query_uncertain")
            if bo is not None:
                return self._after(self._adopt(row, bo, "adopted_after_unknown"), row.trade_id)
            if attempts >= self.max_attempts - 1:
                return self._fail(row)
            self.clock.sleep(self.unknown_grace_s)
            ok, bo = self._query(req.pair, req.client_id)
            if not ok:
                self._block("order_unknown")
                return self._outcome(row, None, "query_uncertain")
            if bo is not None:
                return self._after(self._adopt(row, bo, "adopted_after_unknown"), row.trade_id)
            attempts += 1
            row = self._upd(row.client_id, attempts=attempts)
            res = self._send(req)
            if res is not None:
                return self._after(self._apply_result(row, res, "resent_once"), row.trade_id)
            if attempts >= self.max_attempts - 1:
                return self._fail(row)

    def _fail(self, row: OrderRow) -> SubmitOutcome:
        row = self._upd(row.client_id, status="failed", detail=row.detail or "unknown_unresolved")
        out = self._outcome(row, None, "failed")
        return self._after(out, row.trade_id)

    def _block(self, reason: str) -> None:
        with self.state.tx():
            self.state.kv_set("entries_blocked_reason", reason)

    def _after(self, out: SubmitOutcome, trade_id: int | None) -> SubmitOutcome:
        """Rol bazli yan etkiler (basarisizlik ve kabul)."""
        row = out.order
        if row.role == "entry" and out.status == "failed" and row.status == "failed":
            self._entry_failed(row)
        elif row.role == "exit":
            self._exit_effects(row, out)
        return out

    def _entry_failed(self, row: OrderRow) -> None:
        with self.state.tx():
            if row.trade_id is not None:
                p = self.state.get_position(row.trade_id)
                if p is not None and p.status == "opening":
                    self.state.update_position(p.trade_id, status="closed", exit_reason="other", closed_ts=self.clock.now())
            self.state.kv_set("entries_blocked_reason", "order_unknown")
        log.error("giris emri basarisiz: %s", row.client_id)

    def _exit_effects(self, row: OrderRow, out: SubmitOutcome) -> None:
        if row.trade_id is None:
            return
        p = self.state.get_position(row.trade_id)
        if p is None or p.status == "closed":
            return
        if out.ok or out.status == "failed":
            # kabul: closing; basarisiz: closing kalir, resolve_unresolved yeniden dener
            if p.status != "closing" or p.exit_client_id != row.client_id:
                with self.state.tx():
                    self.state.update_position(p.trade_id, status="closing", exit_client_id=row.client_id)

    def _resolve_row(self, row: OrderRow) -> SubmitOutcome:
        req = self._req_from_row(row)
        out = self._unknown_path(row, req)
        return out

    # ------------------------------------------------------------------ giris / cikis
    def submit_entry(self, intent: Intent, trade_id: int) -> SubmitOutcome:
        if intent.kind != "entry":
            raise ValueError("intent.kind 'entry' olmali")
        if intent.qty is None or not intent.qty > 0:
            raise ValueError("qty > 0 olmali")
        rules = self.rules_fn(intent.pair)
        if not is_multiple(intent.qty, rules.step):
            raise ValueError(f"qty adimin kati degil: {intent.qty} / {rules.step}")
        cid = make_client_id(self.bot, "entry", intent.pair, intent.side, intent.signal_bar_close_ts, 0)
        req = OrderRequest(client_id=cid, pair=intent.pair, role="entry",
                           order_side=order_side_for(intent.side, "entry"), qty=intent.qty, trigger_price=None,
                           reduce_only=False, leverage=intent.leverage, signal_bar_close_ts=intent.signal_bar_close_ts,
                           created_ts=self.clock.now())
        if intent.leverage is not None:
            try:
                self.broker.prepare(intent.pair, intent.leverage)
            except StateError:
                raise
            except Exception as e:  # noqa: BLE001
                return self._prepare_failed(req, trade_id, e)
        return self._submit(req, 0, trade_id)

    def _prepare_failed(self, req: OrderRequest, trade_id: int, e: Exception) -> SubmitOutcome:
        now = self.clock.now()
        row = OrderRow(client_id=req.client_id, pair=req.pair, role=req.role, order_side=req.order_side,
                       qty=req.qty, trigger_price=None, reduce_only=False, status="failed",
                       signal_bar_close_ts=req.signal_bar_close_ts, seq=0, attempts=0, trade_id=trade_id,
                       broker_order_id=None, detail=f"prepare_failed:{type(e).__name__}", created_ts=now, updated_ts=now)
        with self.state.tx():
            self.state.insert_order(row)
        return self._after(SubmitOutcome(False, "failed", row, None, "prepare_failed"), trade_id)

    def submit_exit(self, pos: Position, reason: str, at: datetime) -> SubmitOutcome:
        if pos.qty is None or not pos.qty > 0:
            raise ValueError("pozisyon qty yok")
        cid = make_client_id(self.bot, "exit", pos.pair, pos.side, at, 0)
        req = OrderRequest(client_id=cid, pair=pos.pair, role="exit", order_side=order_side_for(pos.side, "exit"),
                           qty=pos.qty, trigger_price=None, reduce_only=True, leverage=None,
                           signal_bar_close_ts=at, created_ts=self.clock.now())
        self._pupd(pos.trade_id, exit_reason=reason)
        out = self._submit(req, 0, pos.trade_id)
        if out.status == "failed" and out.order.status == "failed":
            self._exit_failed_effects(pos)
        return out

    def _exit_failed_effects(self, pos: Position) -> None:
        n = int(self.state.kv_get(f"exit_retry:{pos.trade_id}", 0))
        if n >= _EXIT_RETRY_LIMIT:
            with self.state.tx():
                self.state.kv_set("entries_blocked_reason", "exit_unknown")
            log.critical("cikis emri cozulemedi: trade %s (stop pozisyonu korur)", pos.trade_id)

    # ------------------------------------------------------------------ stop
    def _stop_request(self, pos: Position, price: float, seq: int) -> OrderRequest:
        cid = make_client_id(self.bot, "stop", pos.pair, pos.side, pos.signal_bar_close_ts, seq)
        return OrderRequest(client_id=cid, pair=pos.pair, role="stop", order_side=order_side_for(pos.side, "stop"),
                            qty=pos.qty, trigger_price=price, reduce_only=True, leverage=None,
                            signal_bar_close_ts=pos.signal_bar_close_ts, created_ts=self.clock.now())

    def place_initial_stop(self, pos: Position) -> SubmitOutcome:
        if pos.qty is None or not pos.qty > 0:
            raise ValueError("pozisyon qty yok")
        tick = self.stop_tick(pos)
        price = round_tight(pos.initial_stop, pos.side, tick)
        out = self._stop_attempt(pos, price, 0)
        if out.ok:
            return out
        log.warning("ilk stop kurulamadi (%s), bir kez daha deneniyor", out.note)
        out = self._stop_attempt(pos, price, 1)
        if out.ok:
            return out
        log.critical("stop kurulamadi: trade %s kapatiliyor", pos.trade_id)
        cur = self.state.get_position(pos.trade_id) or pos
        self.submit_exit(cur, "other", self.clock.now())
        self._block("stop_failed")
        return SubmitOutcome(False, out.status, out.order, out.result, "stop_failed_closed")

    def _stop_attempt(self, pos: Position, price: float, seq: int) -> SubmitOutcome:
        req = self._stop_request(pos, price, seq)
        if seq != pos.stop_seq or self.state.get_order(req.client_id) is None:
            self._pupd(pos.trade_id, stop_seq=seq)
        out = self._submit(req, seq, pos.trade_id)
        if out.ok:
            self._pupd(pos.trade_id, stop_seq=seq, stop_client_id=req.client_id)
        return out

    def replace_stop(self, pos: Position, new_stop: float) -> SubmitOutcome:
        if pos.qty is None or not pos.qty > 0:
            raise ValueError("pozisyon qty yok")
        tick = self.stop_tick(pos)
        new = round_tight(new_stop, pos.side, tick)
        tighter = new > pos.current_stop if pos.side == "long" else new < pos.current_stop
        if not tighter:
            row = self.state.get_order(pos.stop_client_id) if pos.stop_client_id else None
            if row is None:
                now = self.clock.now()
                row = OrderRow(client_id=pos.stop_client_id or "", pair=pos.pair, role="stop",
                               order_side=order_side_for(pos.side, "stop"), qty=pos.qty,
                               trigger_price=pos.current_stop, reduce_only=True, status="accepted",
                               signal_bar_close_ts=pos.signal_bar_close_ts, seq=pos.stop_seq, attempts=0,
                               trade_id=pos.trade_id, broker_order_id=None, detail=None, created_ts=now, updated_ts=now)
            return SubmitOutcome(True, "accepted", row, None, "not_tighter")
        seq = pos.stop_seq + 1
        req = self._stop_request(pos, new, seq)
        self._pupd(pos.trade_id, stop_seq=seq)     # kimlik POST'tan once kalici
        out = self._submit(req, seq, pos.trade_id)
        if not out.ok:
            if out.note == "would_trigger":
                return out
            log.warning("stop guncellenemedi (%s): eski stop duruyor", out.note)
            return out
        self._pupd(pos.trade_id, current_stop=new, stop_client_id=req.client_id)
        old = pos.stop_client_id
        if old and old != req.client_id:
            try:
                self.broker.cancel(pos.pair, old)
            except StateError:
                raise
            except Exception as e:  # noqa: BLE001
                log.warning("eski stop iptal edilemedi %s: %r", old, e)
        return out

    def cancel_resting(self, pos: Position) -> None:
        cids: list[str] = []
        if pos.stop_client_id:
            cids.append(pos.stop_client_id)
        for r in self.state.orders_for_trade(pos.trade_id):
            if r.role in ("stop", "target") and r.status == "accepted" and r.client_id not in cids:
                cids.append(r.client_id)
        for cid in cids:
            try:
                self.broker.cancel(pos.pair, cid)
            except StateError:
                raise
            except Exception as e:  # noqa: BLE001
                log.warning("iptal basarisiz %s: %r", cid, e)

    # ------------------------------------------------------------------ cozum
    def resolve_unresolved(self) -> list[SubmitOutcome]:
        outs: list[SubmitOutcome] = []
        for row in self.state.unresolved_orders():
            out = self._resolve_row(row)
            if row.role == "stop" and out.ok and row.trade_id is not None:
                self._adopt_stop(row)
            outs.append(out)
        outs.extend(self._retry_failed_exits())
        return outs

    def _adopt_stop(self, row: OrderRow) -> None:
        p = self.state.get_position(row.trade_id) if row.trade_id is not None else None
        if p is None or p.status == "closed" or row.trigger_price is None:
            return
        with self.state.tx():
            if p.stop_client_id is None or row.seq >= p.stop_seq:
                tighter = (row.trigger_price > p.current_stop) if p.side == "long" else (row.trigger_price < p.current_stop)
                f: dict = {"stop_client_id": row.client_id, "stop_seq": max(p.stop_seq, row.seq)}
                if row.seq > 0 and tighter:
                    f["current_stop"] = row.trigger_price
                self.state.update_position(p.trade_id, **f)

    def _retry_failed_exits(self) -> list[SubmitOutcome]:
        outs: list[SubmitOutcome] = []
        for p in self.state.open_positions():
            if p.status != "closing" or not p.exit_client_id:
                continue
            row = self.state.get_order(p.exit_client_id)
            if row is None or row.status != "failed":
                continue
            n = int(self.state.kv_get(f"exit_retry:{p.trade_id}", 0))
            if n >= _EXIT_RETRY_LIMIT:
                self._exit_failed_effects(p)
                continue
            with self.state.tx():
                self.state.kv_set(f"exit_retry:{p.trade_id}", n + 1)
            row = self._upd(row.client_id, status="unknown", attempts=0)
            out = self._resolve_row(row)
            if out.status == "failed" and out.order.status == "failed":
                self._exit_failed_effects(self.state.get_position(p.trade_id) or p)
            outs.append(out)
        return outs
