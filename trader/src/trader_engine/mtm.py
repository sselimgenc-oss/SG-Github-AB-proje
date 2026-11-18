"""WP-3 (defter-ek-alanlar 6): anlik degerli (mark-to-market) oz varlik isareti. YALNIZ KAYIT: motor bu degerleri
yazar, okumaz. Saf birikim + enjekte edilen yazici; ag, saat, dosya, durum yok. `engine.counters()`'a anahtar eklemez."""
from __future__ import annotations

import logging
import math
from collections.abc import Callable, Iterable, Mapping

log = logging.getLogger("engine.mtm")

Writer = Callable[..., object]


class MtmRecorder:
    """Dakika adimi `on_minute`: acik pozisyonlarin ters uc (temkinli) gerceklesmemis K/Z'si -> `eq_worst`.
    Karar adimi `on_decision`: bir isaret (wallet, equity, equity_low, n_open) uretir ve yaziciya verir.

    `writer(ts, wallet, equity, equity_low, n_open, src)`; None ise yalniz `keep` listesine yazilir. Yazici hatasi
    yalniz `errors` sayacini artirir (islem yolu etkilenmez)."""

    def __init__(self, writer: Writer | None = None, *, src: str = "sim", keep: bool = False,
                 enabled: bool = True) -> None:
        self.writer = writer
        self.src = src
        self.keep = bool(keep)
        self.enabled = bool(enabled)
        self.rows_written = 0
        self.errors = 0
        self.rows: list[tuple] = []              # yalniz keep=True (geri test): (ts, wallet, equity, low, n_open)
        self._low = math.inf
        self._wallet: float | None = None
        self._last_u: dict[int, float] = {}

    # ------------------------------------------------------------------ dakika
    def on_minute(self, ts, bars: Mapping[str, object], positions: Iterable, wallet: float | None = None) -> None:
        if not self.enabled:
            return
        try:
            w = self._wallet if wallet is None else float(wallet)
            if wallet is not None:
                self._wallet = w
            if w is None or not math.isfinite(w):
                return
            u = 0.0
            seen: dict[int, float] = {}
            for p in positions:
                if p.status not in ("open", "closing") or p.entry_price is None or not p.qty:
                    continue
                bar = bars.get(p.pair)
                tid = int(p.trade_id)
                if bar is None:
                    uw = self._last_u.get(tid, 0.0)
                else:
                    if p.side == "long":
                        worst = bar.mark_l if bar.mark_l is not None else bar.last_l
                        sgn = 1.0
                    else:
                        worst = bar.mark_h if bar.mark_h is not None else bar.last_h
                        sgn = -1.0
                    uw = sgn * (float(worst) - float(p.entry_price)) * float(p.qty)
                seen[tid] = uw
                u += uw
            self._last_u = seen
            eqw = w + u
            if math.isfinite(eqw) and eqw < self._low:
                self._low = eqw
        except Exception as e:  # noqa: BLE001 - olcum islemi hicbir zaman durdurmaz
            self.errors += 1
            log.warning("mtm dakika isareti hatasi: %r", e)

    # ------------------------------------------------------------------ karar adimi
    def on_decision(self, D, account, n_open: int) -> None:
        if not self.enabled:
            return
        try:
            wallet, equity = float(account.wallet), float(account.equity)
            self._wallet = wallet
            low = min(equity, self._low)
            self._low = math.inf
            if not (math.isfinite(wallet) and math.isfinite(equity) and math.isfinite(low)):
                self.errors += 1
                return
            n = int(n_open)
            if self.writer is not None:
                self.writer(D, wallet, equity, low, n, self.src)
            if self.keep:
                self.rows.append((D, wallet, equity, low, n))
            self.rows_written += 1
        except Exception as e:  # noqa: BLE001
            self.errors += 1
            log.warning("mtm isareti yazilamadi: %r", e)
