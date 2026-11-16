"""Mutabakat, paper alt kumesi (05 §7). Brokerda gorunen gercek ile state/ledger karsilastirilir; belirsizlikte
girisler kapanir, cikislar ve koruyucu stop calismaya devam eder."""
from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime

from .clock import Clock
from .errors import StateError

log = logging.getLogger("engine.reconcile")
_AUTO_CLEAR = ("stop_failed", "order_unknown", "exit_unknown")


@dataclass(frozen=True)
class ReconcileReport:
    ok: bool
    fatal: bool
    actions: tuple[str, ...]
    findings: tuple[str, ...]


class Reconciler:
    def __init__(self, cfg, broker, state, ledger, orders, clock: Clock) -> None:
        self.cfg = cfg
        self.broker = broker
        self.state = state
        self.ledger = ledger
        self.orders = orders
        self.clock = clock

    # ------------------------------------------------------------------ yardimcilar
    def _block(self, reason: str) -> None:
        with self.state.tx():
            if self.state.kv_get("entries_blocked_reason") != reason:
                self.state.kv_set("entries_blocked_reason", reason)

    def _install_stop(self, pos, actions: list[str]) -> bool:
        """Yeni stop (yeni seq) kur; olmazsa piyasada kapat. True: stop duruyor."""
        om = self.orders
        from .numeric import round_tight
        tick = om.rules_fn(pos.pair).tick
        price = round_tight(pos.current_stop, pos.side, tick)
        seq = pos.stop_seq + 1
        with self.state.tx():
            self.state.update_position(pos.trade_id, stop_seq=seq)
        out = om._submit(om._stop_request(pos, price, seq), seq, pos.trade_id)   # noqa: SLF001
        if out.ok:
            with self.state.tx():
                self.state.update_position(pos.trade_id, stop_client_id=out.order.client_id)
            actions.append(f"stop_installed:{pos.trade_id}")
            return True
        log.critical("mutabakat: stop kurulamadi, trade %s kapatiliyor", pos.trade_id)
        cur = self.state.get_position(pos.trade_id) or pos
        if cur.status == "open":
            om.submit_exit(cur, "force_exit", self.clock.now())
        self._block("stop_failed")
        actions.append(f"stop_failed_closed:{pos.trade_id}")
        return False

    # ------------------------------------------------------------------ calistir
    def run(self, now: datetime) -> ReconcileReport:
        actions: list[str] = []
        findings: list[str] = []
        fatal = False
        reasons: list[str] = []

        # 1. bekleyen/belirsiz emirler
        if self.state.unresolved_orders():
            actions.append("resolve_unresolved")
            self.orders.resolve_unresolved()

        spos = {p.pair: p for p in self.state.open_positions()}
        bpos = {p.pair: p for p in self.broker.positions()}

        # 2. brokerda var, state'te yok
        for pair in sorted(set(bpos) - set(spos)):
            findings.append(f"unknown_position:{pair}")
            reasons.append("reconcile_unknown_position")
            fatal = True
            log.critical("mutabakat: brokerda state'te olmayan pozisyon %s (islem yapilmadi)", pair)
        # 3. state'te acik, brokerda yok
        for pair, p in sorted(spos.items()):
            if p.status in ("open", "closing") and pair not in bpos:
                findings.append(f"state_orphan:{p.trade_id}")
                reasons.append("reconcile_state_orphan")
                fatal = True
                log.critical("mutabakat: state'te acik ama brokerda olmayan pozisyon trade %s", p.trade_id)
        # 4. stop denetimi (brokerda ve state'te ortak pozisyonlar)
        orders_open = self.broker.open_orders()
        for pair in sorted(set(bpos) & set(spos)):
            p, bp = spos[pair], bpos[pair]
            if p.status != "open" or p.qty is None:
                continue
            stops = [o for o in orders_open if o.pair == pair and o.role == "stop" and o.reduce_only]
            ok_stops = [o for o in stops if abs(o.qty - bp.qty) <= 1e-12 * max(1.0, bp.qty)]
            if not stops:
                findings.append(f"no_stop:{p.trade_id}")
                if not self._install_stop(p, actions):
                    reasons.append("stop_failed")
            elif not ok_stops:
                findings.append(f"stop_qty_mismatch:{p.trade_id}")
                log.warning("mutabakat: stop miktari pozisyonla ayni degil (trade %s)", p.trade_id)
                old = [o.client_id for o in stops]
                if self._install_stop(p, actions):
                    for cid in old:
                        try:
                            self.broker.cancel(pair, cid)
                        except StateError:
                            raise
                        except Exception as e:  # noqa: BLE001
                            log.warning("eski stop iptal edilemedi %s: %r", cid, e)
                    actions.append(f"stop_qty_fixed:{p.trade_id}")
                else:
                    reasons.append("stop_failed")
        # 5. yetim reduceOnly emirler
        for o in orders_open:
            if o.reduce_only and o.pair not in bpos:
                findings.append(f"orphan_order:{o.client_id}")
                try:
                    self.broker.cancel(o.pair, o.client_id)
                    actions.append(f"orphan_canceled:{o.client_id}")
                except StateError:
                    raise
                except Exception as e:  # noqa: BLE001
                    log.warning("yetim emir iptal edilemedi %s: %r", o.client_id, e)
        # 6. ledger kuyrugu ve eslesme
        pending = self.state.outbox_pending()
        if pending:
            actions.append("drain_outbox")
            res = self.state.drain_outbox(self.ledger)
            if res.failed:
                findings.append("outbox_pending")
            pending = self.state.outbox_pending()
        pend_ids = {r.trade_id for r in pending}
        try:
            state_ids = {p.trade_id for p in self.state.open_positions() if p.status in ("open", "closing")}
            for t in self.ledger.list_open_trades():
                tid = t.trade_id if hasattr(t, "trade_id") else t.id
                if tid not in state_ids and tid not in pend_ids:
                    findings.append(f"ledger_orphan:{tid}")
                    reasons.append("reconcile_ledger_orphan")
                    log.warning("mutabakat: defterde acik, state'te olmayan islem %s", tid)
            filled = [p.trade_id for p in self.state.open_positions()
                      if p.status in ("open", "closing") and p.entry_price is not None]
            self.ledger.find_unledgered_trades(filled)
        except StateError:
            raise
        except Exception as e:  # noqa: BLE001
            log.error("mutabakat: defter denetimi basarisiz: %s", e)
            findings.append(f"ledger_check_failed:{type(e).__name__}")

        # blokaj yonetimi
        cur = self.state.kv_get("entries_blocked_reason")
        reasons = list(dict.fromkeys(reasons))
        # onceligi sabit: unknown_position > state_orphan > ledger_orphan > diger
        order = ("reconcile_unknown_position", "reconcile_state_orphan", "reconcile_ledger_orphan", "stop_failed")
        reasons.sort(key=lambda r: order.index(r) if r in order else len(order))
        if reasons:
            if cur != reasons[0] and (cur is None or cur in _AUTO_CLEAR or str(cur).startswith("reconcile_")):
                self._block(reasons[0])
        elif cur and (str(cur).startswith("reconcile_") or cur in _AUTO_CLEAR):
            with self.state.tx():
                self.state.kv_set("entries_blocked_reason", None)
            actions.append(f"cleared:{cur}")
            log.info("mutabakat: giris blokaji kaldirildi (%s)", cur)
        return ReconcileReport(ok=not findings, fatal=fatal, actions=tuple(actions), findings=tuple(findings))
