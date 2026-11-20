"""CT/C1 ayriligi: kaldirilan kolun (C1) acik pozisyonlari baslangicta piyasadan kapatilir (tek seferlik, idempotent).
Diger kollara dokunulmaz; kapanis normal `_submit_exit` yolundan (reduce-only piyasa cikisi) gider; gonderilemezse CRIT."""
from __future__ import annotations

import logging
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from test_engine_04_spec import mkpos, put_pos  # noqa: E402

from trader_engine import engine as E  # noqa: E402
from trader_engine.state import StateStore  # noqa: E402


def _engine(state, submit):
    eng = object.__new__(E.Engine)
    eng.state = state
    eng._c = Counter()
    eng._submit_exit = submit
    return eng


def _mk_state():
    st = StateStore(":memory:", bot="learner")
    put_pos(st, mkpos(trade_id=1, pair="BTC/USDT", setup="C1"))
    put_pos(st, mkpos(trade_id=2, pair="ETH/USDT", setup="T1"))
    put_pos(st, mkpos(trade_id=3, pair="SOL/USDT", setup="C1", side="short"))
    return st


def test_yalniz_kaldirilan_kol_kapanir_ve_ikinci_calisma_no_op():
    st = _mk_state()
    gonderilen = []

    def submit(pos, reason, at, quote=False):
        gonderilen.append((pos.trade_id, reason))
        with st.tx():
            st.update_position(pos.trade_id, status="closing", exit_reason=reason)       # normal yol: pozisyon `closing`e gecer
        return type("Out", (), {"status": "submitted"})()

    eng = _engine(st, submit)
    assert E.KALDIRILAN_KOLLAR == ("C1",)
    assert eng._kaldirilan_kollari_kapat(None) == 2
    assert gonderilen == [(1, "force_exit"), (3, "force_exit")]               # T1 dokunulmaz; neden defterin kabul ettigi 'force_exit'
    assert E.EngineExit is not None and "force_exit" in E._REASONS
    assert eng._kaldirilan_kollari_kapat(None) == 0                           # idempotent: cikis zaten yolda
    assert gonderilen == [(1, "force_exit"), (3, "force_exit")]
    assert st.get_position(2).status == "open" and eng._c["kaldirilan_kol_kapatildi"] == 2


def test_cikis_gonderilemezse_crit_ve_sessiz_birakilmaz(caplog):
    st = _mk_state()
    eng = _engine(st, lambda pos, reason, at, quote=False: None)              # ban penceresi vb.: cikis gonderilemedi
    with caplog.at_level(logging.CRITICAL, logger="engine"):
        assert eng._kaldirilan_kollari_kapat(None) == 0
    assert eng._c["kaldirilan_kol_hata"] == 2
    assert sum("kol_kaldirildi" in r.getMessage() and r.levelno == logging.CRITICAL for r in caplog.records) >= 2

    def patlat(pos, reason, at, quote=False):
        raise RuntimeError("borsa reddetti")
    eng2 = _engine(st, patlat)
    assert eng2._kaldirilan_kollari_kapat(None) == 0 and eng2._c["kaldirilan_kol_hata"] == 2


def test_acilmakta_olan_pozisyon_crit_ile_bildirilir(caplog):
    st = StateStore(":memory:", bot="learner")
    put_pos(st, mkpos(trade_id=9, setup="C1", status="opening", qty=None, entry_price=None))
    eng = _engine(st, lambda *a, **k: (_ for _ in ()).throw(AssertionError("opening icin cikis gonderilmemeli")))
    with caplog.at_level(logging.CRITICAL, logger="engine"):
        assert eng._kaldirilan_kollari_kapat(None) == 0
    assert eng._c["kaldirilan_kol_bekliyor"] == 1


def test_start_cagrisi_kaynakta_baglidir():
    src = (Path(E.__file__)).read_text(encoding="utf-8")
    assert src.index("self._started = True\n        self._kaldirilan_kollari_kapat(now)") > 0


# ------------------------------------------------------------------ uctan uca (sentetik kagit motor; gercek kagit broker + defter)
def test_uctan_uca_c1_piyasadan_kapanir_gerceklesen_kz_normal_yazilir(tmp_path):
    from test_engine_05_spec import BTC, M1, T0, Env  # noqa: E402

    env = Env(tmp_path)
    env.start()
    p = env.open_pos(BTC, T0, setup="C1", entry=100.0, stop=98.0)
    assert p.setup == "C1" and p.status == "open"
    for k in range(1, 4):
        env.step(T0 + k * M1, pairs=(BTC,), price=101.0, hi=101.0, lo=101.0)       # stop/hedefe degmeden, fiyat girisin ustunde
    now = env.clock.now()
    assert env.engine._kaldirilan_kollari_kapat(now) == 1
    for k in range(4, 8):
        env.step(T0 + k * M1, pairs=(BTC,), price=101.0, hi=101.0, lo=101.0)
    t = env.real_ledger.get_trade(p.trade_id)
    assert t.exit_reason == "force_exit" and t.exit_price is not None and t.fee_exit > 0     # piyasa cikisi: komisyon/kayma normal
    assert abs(t.realized_pnl - (t.gross_pnl - t.fee_entry - t.fee_exit - t.funding_paid)) < 1e-9     # K/Z normal formulle yazilir
    assert env.state.position_for_pair(BTC) is None                                         # pozisyon kapandi
    assert abs(env.broker.account().wallet - (env.cfg.wallet_start + t.realized_pnl)) < 1e-6   # kasa = baslangic + gerceklesen K/Z
    assert env.engine._kaldirilan_kollari_kapat(env.clock.now()) == 0                       # ikinci calisma no-op
    env.close()
