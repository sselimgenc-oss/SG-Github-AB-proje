"""Calisma sirasi dayaniklilik: sinirsiz yeniden deneme + tur-bellek koruyucusu (1L3A motor/canli/paper.py `sonsuz_dene` ve
`TurKoruyucu`'dan uyarlandi).

`Engine.run_forever` her donguyu `TurKoruyucu.calistir` ile sarar. Mevcut `_guard`/`_advance_failed` (DD-6) davranisi aynen
surer; bu katman yalniz bu guvenlik aglarindan SIZAN istisnalari yakalar (eskiden surecin cikisina yol aciyorlardi):
  - GECICI hata (errors.is_code_error degil: ag/veri/borsa/DataError...): surec cikmaz; ussel geri cekilme (2 sn .. 30 sn) ile
    SINIRSIZ yeniden denenir. testnet/canli'da ARDISIK `HATA_TEKRAR_SINIRI` (5) turdan sonra girisler kapanir (`engine_errors`,
    DD-6 O1 ile ayni; elle kalkar); kagitta kapanmaz (kesinti bitince kendiliginden surer).
  - KOD hatasi (kagit): bellekteki tur durumu tur oncesi kayda dondurulur (yari islenmis tur durumu bozmasin; kagit broker son
    kalici kayittan), olay loglanir; AYNI hata turu art arda `KOD_HATASI_SINIRI` (5) kez olursa kontrollu durus (EngineExit 4;
    systemd yeniden baslatir). testnet/canli'da kod hatasi ESKISI GIBI hemen yukselir (guvenlik gevsetilmez).
  - StateError, EngineExit ve `strict` (test) modu hic yakalanmaz.
"""
from __future__ import annotations

import copy
import logging
from collections import Counter
from collections.abc import Callable

from .errors import EngineExit, StateError, is_code_error

log = logging.getLogger("engine.tur_koruyucu")

KOD_HATASI_SINIRI = 5
HATA_TEKRAR_SINIRI = 5
EXIT_TURN_ERRORS = 4
BACKOFF_BASE_S = 2.0
BACKOFF_CAP_S = 30.0

# tur oncesi yakalanan salt-bellek alanlari (kalici durum sqlite tx'iyle zaten atomik); yalniz durum/gozlem alanlari
_MEM_ATTRS = ("_last_minute", "_last_decision", "_last_candle_open", "_adv_errors", "_adv_next_try", "_exit_retry",
              "_consec_errors", "_consec", "_last_marks", "_regime_mem", "_c")


def yakala(eng) -> dict:
    return {a: copy.copy(getattr(eng, a)) for a in _MEM_ATTRS if hasattr(eng, a)}


def geri_yukle(eng, snap: dict) -> None:
    for a, v in snap.items():
        cur = getattr(eng, a, None)
        if isinstance(cur, Counter) or isinstance(cur, dict):
            cur.clear()
            cur.update(v)                       # ayni nesne: baska referanslar (sayac vb.) gecerli kalir
        else:
            setattr(eng, a, v)
    if eng.is_paper:
        s = eng.state.kv_get("broker_snapshot")
        if s:
            eng._restore_broker(s)


class TurKoruyucu:
    def __init__(self, eng, *, sleep: Callable[[float], None] | None = None) -> None:
        self.eng = eng
        self.sleep = sleep or eng.clock.sleep
        self.transient = 0                       # ardisik gecici hata turu
        self.code_sig: str | None = None
        self.code_n = 0
        self.total = 0                           # toplam yakalanan tur hatasi (status)
        self.last_error: str | None = None

    def calistir(self, tur_fn: Callable[[], None]) -> None:
        eng = self.eng
        if eng.strict:
            tur_fn()
            return
        snap = yakala(eng)
        try:
            tur_fn()
        except (StateError, EngineExit):
            raise
        except Exception as e:  # noqa: BLE001
            self.total += 1
            self.last_error = f"{type(e).__name__}: {str(e)[:160]}"
            if is_code_error(e):
                self._kod(e, snap)
            else:
                self._gecici(e)
            return
        self.transient = 0
        self.code_sig, self.code_n = None, 0

    def _gecici(self, e: Exception) -> None:
        eng = self.eng
        self.transient += 1
        self.code_sig, self.code_n = None, 0
        delay = min(BACKOFF_CAP_S, BACKOFF_BASE_S * (2 ** (self.transient - 1)))
        log.error("tur gecici hata (%d. ardisik, %.0f sn sonra yeniden): %s: %s", self.transient, delay, type(e).__name__, e)
        eng._c["turn_transient_errors"] += 1
        if (not eng.is_paper and eng.cfg.mode in ("testnet", "live") and self.transient >= HATA_TEKRAR_SINIRI
                and not eng.state.block_has("engine_errors")):
            log.critical("%d ardisik gecici tur hatasi: girisler kapatildi (engine_errors)", self.transient)
            eng._block("engine_errors")
        self.sleep(delay)

    def _kod(self, e: Exception, snap: dict) -> None:
        eng = self.eng
        if not eng.is_paper:
            raise e                              # testnet/canli: eski davranis (guvenlik gevsetilmez)
        sig = type(e).__name__
        self.code_n = self.code_n + 1 if sig == self.code_sig else 1
        self.code_sig = sig
        self.transient = 0
        eng._c["turn_code_errors"] += 1
        log.critical("tur KOD hatasi (%d/%d, ayni tur): %s: %s", self.code_n, KOD_HATASI_SINIRI, sig, e, exc_info=True)
        try:
            geri_yukle(eng, snap)
        except Exception as e2:  # noqa: BLE001
            log.critical("tur durumu geri yuklenemedi: %r", e2)
            raise EngineExit(EXIT_TURN_ERRORS, "tur durumu geri yuklenemedi") from e
        if self.code_n >= KOD_HATASI_SINIRI:
            raise EngineExit(EXIT_TURN_ERRORS, f"ayni kod hatasi art arda {self.code_n} kez: {sig}") from e
        self.sleep(BACKOFF_BASE_S)
