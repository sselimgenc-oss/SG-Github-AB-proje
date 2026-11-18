"""DD-8 (O8): mod/hesap damgasi. `testnet`/`live` state'i ve defteri hangi moda+hesaba ait oldugunu soyler; yabanci ya da
eksik dosyayla acilis EngineExit(8) ile reddedilir (borsaya istek gitmeden). Karar tablosu: docs/dd8-canli-baslangic-spec.md §2.2.

`paper`: yalniz OKUR (var olan her damga yabancidir). `backtest`: hicbir sey yapilmaz (bu modul cagrilmaz).
Damga hicbir yolla uzerine yazilmaz; yazim sirasi: ONCE state, SONRA defter (ters sira 4. satira dusup kendini kilitler).
"""
from __future__ import annotations

import logging
import os
import sqlite3

from trader_core import ledger as L

from .config import EngineConfig
from .errors import EngineExit
from .state import StateStore

log = logging.getLogger(__name__)

STAMP_KEY = "account_stamp"


def want_stamp(cfg: EngineConfig) -> str:
    tag = cfg.live.account_tag if cfg.live is not None else ""
    return f"{cfg.mode}:{tag}"


def _read_state(state: StateStore):
    try:
        return state.kv_get(STAMP_KEY)
    except Exception as e:  # noqa: BLE001 - fail-closed: okunamayan damga = reddet
        log.critical("state damgasi okunamadi: %r", e)
        raise EngineExit(8, "state_stamp_mismatch") from e


def _read_ledger(ledger: L.Ledger):
    try:
        return ledger.get_meta(STAMP_KEY)
    except Exception as e:  # noqa: BLE001
        log.critical("defter damgasi okunamadi: %r", e)
        raise EngineExit(8, "ledger_stamp_mismatch") from e


def _virgin(state: StateStore) -> bool:
    try:
        return state.is_virgin()
    except Exception as e:  # noqa: BLE001
        log.critical("state bakirlik sorgusu basarisiz: %r", e)
        raise EngineExit(8, "state_stamp_mismatch") from e


def _paper_trace(state: StateStore) -> bool:
    try:
        return state.has_paper_trace()
    except Exception as e:  # noqa: BLE001
        log.critical("state kagit izi sorgusu basarisiz: %r", e)
        raise EngineExit(8, "state_stamp_mismatch") from e


def ledger_has_history(path: str) -> bool:
    """Defter islem/karar satiri iceriyor mu — KATI surum (mentor F1): okuma hatasi YUTULMAZ, istisna yukselir.
    `state._ledger_has_history` (paper 0-bayt denetimi) bilerek fail-open kalir; damga tablosu fail-closed olmali."""
    if os.path.getsize(path) == 0:
        return False
    con = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
    try:
        for t in ("trade_entries", "decision_events"):
            if con.execute(f"SELECT 1 FROM {t} LIMIT 1").fetchone() is not None:
                return True
        return False
    finally:
        con.close()


def _ledger_full(ledger: L.Ledger) -> bool:
    try:
        return ledger_has_history(ledger.path)
    except Exception as e:  # noqa: BLE001 - fail-closed: dolu/bos okunamazsa damga yazilmaz
        log.critical("defter gecmis sorgusu basarisiz: %r", e)
        raise EngineExit(8, "ledger_stamp_mismatch") from e


def _write_state(state: StateStore, want: str) -> None:
    try:
        with state.tx():
            state.kv_set(STAMP_KEY, want)
        ok = state.kv_get(STAMP_KEY) == want
    except Exception as e:  # noqa: BLE001
        log.critical("state damgasi yazilamadi: %r", e)
        raise EngineExit(8, "state_stamp_missing") from e
    if not ok:
        raise EngineExit(8, "state_stamp_missing")


def _write_ledger(ledger: L.Ledger, want: str) -> None:
    try:
        ledger.set_meta_once(STAMP_KEY, want)
    except Exception as e:  # noqa: BLE001
        log.critical("defter damgasi yazilamadi: %r", e)
        raise EngineExit(8, "ledger_stamp_missing") from e


def verify_or_init_stamp(cfg: EngineConfig, state: StateStore, ledger: L.Ledger) -> None:
    mode = cfg.mode
    if mode == "backtest":
        return
    s = _read_state(state)
    ll = _read_ledger(ledger)
    if mode == "paper":
        if s is not None:
            raise EngineExit(8, "state_stamp_mismatch")
        if ll is not None:
            raise EngineExit(8, "ledger_stamp_mismatch")
        return
    want = want_stamp(cfg)
    if s is not None and s != want:                                   # 1
        raise EngineExit(8, "state_stamp_mismatch")
    if ll is not None and ll != want:                                 # 2
        raise EngineExit(8, "ledger_stamp_mismatch")
    if s is None:
        if _paper_trace(state):                                       # 3
            raise EngineExit(8, "state_stamp_mismatch")
        if _virgin(state):
            if ll is not None or _ledger_full(ledger):                # 4
                raise EngineExit(8, "state_missing")
            _write_state(state, want)                                 # 5: once state, sonra defter
            _write_ledger(ledger, want)
            log.warning("ilk acilis: damga yazildi (%s)", want)
            return
        raise EngineExit(8, "state_stamp_missing")                    # 6
    if ll is None:                                                    # s == want
        if _ledger_full(ledger):                                      # 8
            raise EngineExit(8, "ledger_stamp_missing")
        _write_ledger(ledger, want)                                   # 7
        return
    return                                                            # 9
