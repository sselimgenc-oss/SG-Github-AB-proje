"""C1 kaldirma gocu (trader_core/kol_kaldirma.py + scripts/c1_goc.py): sentetik defter (C1 + diger kollar) + sentetik state.
Tetikleyiciler goc sonrasi yerinde, kasa = baslangic + Σ net K/Z (C1 disi), mutabakat tutarli, idempotent, hata yolunda yedekten geri yukleme."""
from __future__ import annotations

import importlib.util
import json
import sqlite3
import sys
from datetime import datetime, timedelta, timezone

import pytest

from panel_support import ROOT
from test_strateji_veri import D0, mk  # noqa: E402
from trader_core import kol_kaldirma as K
from trader_core import ledger as L
from trader_core import mutabakat as M
from trader_engine.state import StateStore

UTC = timezone.utc
NOW = datetime(2026, 11, 21, 12, 0, tzinfo=UTC)
START = 1000.0


def _kur(tmp_path, *, c1_acik=False):
    var = tmp_path / "var"
    (var / "learner").mkdir(parents=True)
    led_p = var / "learner" / "ledger.sqlite"
    extra = [("C1@1h", "long", "range", "win", D0 + timedelta(days=5)), ("C1@1h", "short", "range", "loss", D0 + timedelta(days=6)),
             ("C1@4h", "long", "range", "win", D0 + timedelta(days=7)), ("T1@1h", "long", "trend_up", "win", D0 + timedelta(days=8))]
    if c1_acik:
        extra.append(("C1@1h", "long", "range", "open", D0 + timedelta(days=9)))
    mk(str(led_p), extra=extra)
    led = L.open_ledger(str(led_p), "learner", create=False, clock=lambda: NOW)
    tr = led.list_closed_trades()
    net_tum = sum(t.realized_pnl for t in tr)
    # gecmis kasa isaretleri: her kapanistan sonra
    for t in sorted(tr, key=lambda x: x.exit_ts):
        w = START + sum(x.realized_pnl for x in tr if x.exit_ts <= t.exit_ts)
        led.record_equity_mark(L.EquityMark(ts=t.exit_ts + timedelta(minutes=1), wallet=w, equity=w + 0.5, equity_low=w, n_open=0, src="mtm"
                                            if "mtm" in L._EQ_SRCS else sorted(L._EQ_SRCS)[0]))
    c1 = [t for t in tr if t.setup == "C1"]
    led.close()
    st = StateStore(str(var / "learner" / "state.sqlite"), bot="learner")
    with st.tx():
        st.kv_set("broker_snapshot", {"version": 1, "wallet": START + net_tum, "positions": {}, "orders": {}})
        st.kv_set("day_start:2026-11-21", START + net_tum)
        st.kv_set("day_start:2026-11-10", START + sum(t.realized_pnl for t in tr if t.exit_ts < datetime(2026, 11, 10, tzinfo=UTC)))
        for t in c1:
            st.kv_set(f"gecikme:{t.trade_id}", {"x": 1})
            st.kv_set(f"eq:{t.trade_id}", 1000.0)
        st.kv_set("gecikme:1", {"x": 1})
    st.close()
    sc = sqlite3.connect(var / "learner" / "state.sqlite")
    for t in tr:                                                      # kapali pozisyon satirlari (state.positions)
        sc.execute("INSERT INTO positions(trade_id,bot,pair,side,setup,status,decision_id,signal_bar_close_ms,leverage,initial_stop,current_stop,"
                   "trail_atr,param_version_id,trigger_tf,risk_amount,margin) VALUES (?,?,?,?,?,'closed',?,0,3,1,1,1,1,'1h',1,1)",
                   (t.trade_id, "learner", t.pair, t.side, t.setup, t.decision_id))
    sc.commit()
    sc.close()
    return var, tr, net_tum, c1


def _q(path, sql):
    c = sqlite3.connect(path)
    try:
        return c.execute(sql).fetchall()
    finally:
        c.close()


def _say(path, tablo, where="1=1"):
    c = sqlite3.connect(path)
    try:
        return c.execute(f"SELECT COUNT(*) FROM {tablo} WHERE {where}").fetchone()[0]
    finally:
        c.close()


def test_goc_c1_siler_diger_kollara_dokunmaz_kasa_c1_siz_ve_tetikleyiciler_yerinde(tmp_path):
    var, tr, net_tum, c1 = _kur(tmp_path)
    led_p, st_p = var / "learner" / "ledger.sqlite", var / "learner" / "state.sqlite"
    diger = [t for t in tr if t.setup != "C1"]
    net_c1 = sum(t.realized_pnl for t in c1)
    assert len(c1) == 3 and len(diger) > 0
    mesajlar = []
    r = K.calistir(var, wallet_start=START, now=NOW, bildir=mesajlar.append)
    assert r["durum"] == "tamam" and r["tetikler_dogrulandi"] is True
    assert abs(r["eski_kasa"] - (START + net_tum)) < 1e-5 and abs(r["yeni_kasa"] - (START + net_tum - net_c1)) < 1e-5
    # defter: C1 yok, digerleri ayni
    for t in ("decision_events", "trade_entries", "shadow_decisions"):
        assert _say(led_p, t, "setup='C1'") == 0
    led = L.open_ledger(str(led_p), "learner", create=False, read_only=True, migrate=False)
    kalan = led.list_closed_trades()
    led.close()
    assert sorted((t.trade_id, t.realized_pnl) for t in kalan) == sorted((t.trade_id, t.realized_pnl) for t in diger)
    # kasa = baslangic + Σ net K/Z (C1 disi); mutabakat kontrolu tutarli
    snap = json.loads(_q(st_p, "SELECT v FROM kv WHERE k='broker_snapshot'")[0][0])
    net_diger = sum(t.realized_pnl for t in kalan)
    assert abs(snap["wallet"] - (START + net_diger)) < 1e-6
    k = M.kontrol_kasa(baslangic=START, net_sql=net_diger, net_motor=net_diger, status={"wallet": snap["wallet"], "open_positions": []})
    assert k["sonuc"] == "geçti"
    # state: C1 kapali pozisyon, per-trade kv temizlendi; digerleri durur
    assert _say(st_p, "positions", "setup='C1'") == 0 and _say(st_p, "positions") == len(diger)
    kv = dict(_q(st_p, "SELECT k, v FROM kv"))
    assert not any(f"gecikme:{t.trade_id}" in kv or f"eq:{t.trade_id}" in kv for t in c1) and "gecikme:1" in kv
    # gun basi ozsermaye ayni kaymayla duzeltildi
    assert abs(float(json.loads(kv["day_start:2026-11-21"])) - (START + net_diger)) < 1e-6
    # gecmis kasa isaretleri C1'siz
    marks = _q(led_p, "SELECT ts, wallet FROM equity_marks ORDER BY ts")
    assert marks and abs(marks[-1][1] - (START + net_diger)) < 1e-6
    # rapor, isaret, yedek yok, telegram satiri
    rap = json.loads((var / "durum" / K.RAPOR).read_text())
    assert rap["tetikler_dogrulandi"] is True and rap["eski_kasa"] != rap["yeni_kasa"] and rap["silinen_kayit"]["defter"]["trade_entries"] == 3
    assert (var / K.ISARET).is_file() and not (var / "yedek").exists()
    assert len(mesajlar) == 1 and "->" in mesajlar[0]
    # tetikleyiciler: UPDATE/DELETE reddedilir, eksik tetikleyici yok
    c = sqlite3.connect(led_p)
    trig = {x[0] for x in c.execute("SELECT name FROM sqlite_master WHERE type='trigger'")}
    assert L._EXPECTED_TRIGGERS <= trig
    with pytest.raises(sqlite3.DatabaseError, match="append-only"):
        c.execute("DELETE FROM trade_entries")
    c.close()


def test_idempotent_ikinci_calisma_no_op(tmp_path):
    var, *_ = _kur(tmp_path)
    K.calistir(var, wallet_start=START, now=NOW)
    h = (var / "learner" / "ledger.sqlite").read_bytes()
    assert K.calistir(var, wallet_start=START, now=NOW)["durum"] == "zaten_yapildi"
    assert (var / "learner" / "ledger.sqlite").read_bytes() == h
    (var / K.ISARET).unlink()                                         # isaret kaybolsa bile: silinecek C1 yok -> degisiklik yok
    r = K.calistir(var, wallet_start=START, now=NOW + timedelta(hours=1))
    assert r["durum"] == "tamam" and r["eski_kasa"] == r["yeni_kasa"] and (var / "learner" / "ledger.sqlite").read_bytes() == h


def test_acik_c1_pozisyonu_varsa_reddeder_hicbir_sey_degismez(tmp_path):
    var, *_ = _kur(tmp_path, c1_acik=True)
    sc = sqlite3.connect(var / "learner" / "state.sqlite")
    sc.execute("UPDATE positions SET status='open' WHERE setup='C1' AND trade_id=(SELECT MAX(trade_id) FROM positions WHERE setup='C1')")
    sc.commit()
    sc.close()
    h = (var / "learner" / "ledger.sqlite").read_bytes()
    with pytest.raises(K.GocReddedildi):
        K.calistir(var, wallet_start=START, now=NOW)
    assert (var / "learner" / "ledger.sqlite").read_bytes() == h and not (var / K.ISARET).exists() and not (var / "yedek").exists()


def test_motor_calisiyorsa_reddeder(tmp_path):
    var, *_ = _kur(tmp_path)
    with pytest.raises(K.GocReddedildi):
        K.calistir(var, wallet_start=START, now=NOW, motor_aktif_fn=lambda: True)


def test_hata_yolu_yedekten_geri_yukler_isaret_yok_crit_ve_telegram(tmp_path, monkeypatch, caplog):
    var, tr, net_tum, c1 = _kur(tmp_path)
    led_p, st_p = var / "learner" / "ledger.sqlite", var / "learner" / "state.sqlite"
    snap0 = _q(st_p, "SELECT v FROM kv WHERE k='broker_snapshot'")[0][0]

    def patlat(*a, **k):
        raise K.GocHatasi("sentetik dogrulama hatasi")
    monkeypatch.setattr(K, "_tetikler_ve_butunluk", lambda lp, kl: (_ for _ in ()).throw(K.GocHatasi("sentetik dogrulama hatasi"))
                        if kl else True)
    mesajlar = []
    with caplog.at_level("CRITICAL", logger="trader.kol_kaldirma"), pytest.raises(K.GocHatasi, match="geri yuklendi"):
        K.calistir(var, wallet_start=START, now=NOW, bildir=mesajlar.append)
    assert any(r.levelname == "CRITICAL" for r in caplog.records)
    assert not (var / K.ISARET).exists() and not (var / "yedek").exists() and not (var / "durum" / K.RAPOR).exists()
    assert _q(st_p, "SELECT v FROM kv WHERE k='broker_snapshot'")[0][0] == snap0
    assert _say(led_p, "trade_entries", "setup='C1'") == 3                   # C1 geri geldi (kasa de eski)
    led = L.open_ledger(str(led_p), "learner", create=False, migrate=False)   # geri yuklenen defter acilir (tetikleyiciler yerinde)
    assert len(led.list_closed_trades()) == len(tr)
    led.close()
    assert len(mesajlar) == 1 and mesajlar[0].startswith("CRIT")
    # geri yuklenmis dosyalarin icerigi (sqlite sayfa duzeni degisebilir): mantiksal esitlik
    assert abs(json.loads(snap0)["wallet"] - (START + net_tum)) < 1e-6


def test_cli_c1_goc_cikis_kodlari(tmp_path):
    spec = importlib.util.spec_from_file_location("c1_goc", ROOT / "scripts" / "c1_goc.py")
    G = importlib.util.module_from_spec(spec)
    sys.modules["c1_goc"] = G
    spec.loader.exec_module(G)
    var, *_ = _kur(tmp_path)
    assert G.main(["--var-dir", str(var), "--wallet-start", str(START)]) == 0
    assert (var / K.ISARET).is_file() and (var / "durum" / K.RAPOR).is_file()
    assert G.main(["--var-dir", str(var), "--wallet-start", str(START)]) == 0                        # tekrar: no-op
    var2, *_ = _kur(tmp_path / "b")
    assert G.main(["--var-dir", str(var2), "--wallet-start", str(START), "--motor-birimi", "bu-birim-yok.service"]) == 0   # is-active: calismiyor
