"""Saatlik sembol durumu izleyicisi (1L3A motor/canli/sembol_izleme.py'dan uyarlandi).

Saatte bir herkese acik `exchangeInfo` (anahtarsiz; `marketdata.rest_public.PublicRestClient.exchange_info`) okunur ve her
izlenen cift icin `exchange.rules.extract_rules` ile TRADING durumu sinanir. Bir cift TRADING disina duserse (SETTLING, BREAK,
delist, exchangeInfo'da yok):
  - o ciftte YENI giris acilmaz (`EntryGate.symbol_blocked` -> `symbol_not_trading` atlamasi, defterde kayitli);
  - ACIK POZISYONA DOKUNULMAZ, zorla kapatma yok (borsa stopu / yazilim cikislari surer);
  - uyari: acik pozisyon yoksa WARN, varsa CRIT (status.json `dayaniklilik.sembol` -> Telegram).
Yeniden TRADING olursa engel kalkar, bir kez INFO. exchangeInfo hatasi sessizce bir sonraki saate birakilir (durum degismez).
Bozuk filtre gibi durumla ilgisiz kural hatalari durumu DEGISTIRMEZ (yalniz `not_trading`/`exchangeInfo'da yok` engeller).
"""
from __future__ import annotations

import logging
import threading
from collections.abc import Callable, Iterable
from datetime import datetime, timedelta

from .exchange.rules import RulesError, extract_rules
from .types import pair_symbol

log = logging.getLogger("engine.sembol_izleme")

ARALIK = timedelta(hours=1)
_BLOCKING = ("not_trading", "exchangeInfo'da yok")


class SembolIzleyici:
    def __init__(self, pairs: Iterable[str], fetch: Callable[[], dict], *, contract_types=("PERPETUAL",),
                 has_open_fn: Callable[[str], bool] | None = None, interval: timedelta = ARALIK,
                 background: bool = False) -> None:
        self.pairs = list(pairs)
        self.fetch = fetch
        self.contract_types = tuple(contract_types)
        self.has_open_fn = has_open_fn or (lambda p: False)
        self.interval = interval
        self.blocked: dict[str, dict] = {}       # cift -> {"since": iso, "open": bool, "alert": "WARN" | "CRIT"}
        self.events: list[tuple[str, str, str]] = []   # (seviye, cift, metin) -> engine loglar
        self._last: datetime | None = None
        self.background = background             # True: exchangeInfo istegi ayri iplikte (motor dongusunu bekletmez)
        self._thread: threading.Thread | None = None
        self._box: dict = {}

    def is_blocked(self, pair: str) -> bool:
        return pair in self.blocked

    def status(self) -> list[dict]:
        return [{"cift": p, **v} for p, v in sorted(self.blocked.items())]

    def check(self, now: datetime) -> bool:
        """Saatte bir calisir (her cagrida cagrilabilir). -> durum degisti mi. Hata: sessiz, sonraki saat."""
        if self.background and self._thread is not None:
            if self._thread.is_alive():
                return False
            self._thread = None
            info = self._box.pop("info", None)
            return self._apply(info, now) if info is not None else False
        if not self.pairs or (self._last is not None and now - self._last < self.interval):
            return False
        self._last = now
        if self.background:
            def run() -> None:
                self._box["info"] = self._get_info()
            self._thread = threading.Thread(target=run, name="sembol-izleme", daemon=True)
            self._thread.start()
            return False
        return self._apply(self._get_info(), now)

    def _get_info(self) -> dict | None:
        try:
            info = self.fetch()
            if not info or not info.get("symbols"):
                return None
            return info
        except Exception as e:  # noqa: BLE001  (ag/ban/ayristirma: durum degismez)
            log.info("sembol izleme: exchangeInfo alinamadi (%s: %s); sonraki saat", type(e).__name__, e)
            return None

    def _apply(self, info: dict | None, now: datetime) -> bool:
        if info is None:
            return False
        changed = False
        for pair in self.pairs:
            sym = pair_symbol(pair)
            try:
                extract_rules(info, sym, self.contract_types)
                trading = True
            except RulesError as e:
                msg = str(e)
                if not any(b in msg for b in _BLOCKING):
                    continue                              # bozuk filtre vb.: durumla ilgisiz, degistirme
                trading = False
            if not trading and pair not in self.blocked:
                has_open = bool(self.has_open_fn(pair))
                sev = "CRIT" if has_open else "WARN"
                self.blocked[pair] = {"since": now.isoformat(), "open": has_open, "alert": sev}
                self.events.append((sev, pair, "borsada islem disi; yeni giris yok" + (
                    ", acik pozisyon var (zorla kapatma yok)" if has_open else "")))
                log.log(logging.CRITICAL if has_open else logging.WARNING, "sembol TRADING disi: %s (acik pozisyon=%s)", pair, has_open)
                changed = True
            elif trading and pair in self.blocked:
                del self.blocked[pair]
                self.events.append(("INFO", pair, "yeniden islemde; yeni girisler acildi"))
                log.warning("sembol yeniden TRADING: %s", pair)
                changed = True
        return changed
