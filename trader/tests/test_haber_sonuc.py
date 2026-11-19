"""Haber/duygu x sonuc raporu (ml.haber_sonuc.v1; docs/haber-sonuc-spec.md). Sentetik defter (tmp_path), ag yok, kilitli donem/var/history yok."""
import importlib.util
import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from panel_support import Env
from trader_core import haber_sonuc as HS
from trader_core import ledger as L
from trader_core import panel_data as P
from trader_panel.data import PanelData, load_config

UTC = timezone.utc
ROOT = Path(__file__).resolve().parent.parent
NOW = datetime(2026, 11, 16, 18, 0, tzinfo=UTC)
PARAMS = {"range_width_atr": 4.0, "vol_ratio_max": 1.5, "edge_zone_atr": 0.25, "pullback_ema": 50,
          "stop_buffer_atr": 0.3, "trail_atr": 3.0, "range_target_frac": 0.75, "rr_min": 1.5, "trigger_tf": "1h"}
CT_SUTUNLAR = ("etiket", "n", "kazanan", "isabet_yuzde", "toplam_pnl", "ortalama_pnl")      # CT rejim_sonuc_v1 satir alanlari (sira dahil)


def row(gun_once, pnl, sinif=None, ton=None, pair="BTC/USDT"):
    f = {}
    if sinif is not None:
        f["duygu"] = {"deger": 20, "sinif": sinif}
    if ton is not None:
        f["haber"] = {pair.split("/")[0]: {"adet_24s": 2, "ton": ton}}
    return {"exit_ts": NOW - timedelta(days=gun_once), "pnl": pnl, "pair": pair, "features": f}


ROWS = [row(1, 10.0, "Extreme Fear", "pozitif"), row(2, -4.0, "Extreme Fear", "pozitif"), row(3, 6.0, "Fear", "negatif"),
        row(5, -2.0, None, None), row(20, 8.0, "Greed", "notr"), row(30, -1.0)]


def test_sayim_isabet_toplam():
    t = HS.topla(ROWS, NOW)
    d = {r["etiket"]: r for r in t["tablolar"]["duygu"]}
    assert set(d) == {"Aşırı Korku", "Korku", "etiket yok"}                     # 7 gun: Greed ve eski etiketsiz disarida
    assert d["Aşırı Korku"] == {"etiket": "Aşırı Korku", "n": 2, "kazanan": 1, "isabet_yuzde": 50.0, "toplam_pnl": 6.0, "ortalama_pnl": 3.0}
    assert d["etiket yok"]["n"] == 1 and d["etiket yok"]["kazanan"] == 0 and d["etiket yok"]["toplam_pnl"] == -2.0
    assert [r["etiket"] for r in t["tablolar"]["duygu"]] == ["Aşırı Korku", "Korku", "etiket yok"]        # sabit sira, etiket yok sonda
    tn = {r["etiket"]: r["n"] for r in t["tablolar"]["haber_ton"]}
    assert tn == {"pozitif": 2, "negatif": 1, "haber yok": 1}
    allz = {r["etiket"]: r["n"] for r in t["tum_zamanlar"]["duygu"]}
    assert allz == {"Aşırı Korku": 2, "Korku": 1, "Açgözlülük": 1, "etiket yok": 2}
    assert {r["etiket"]: r["n"] for r in t["tum_zamanlar"]["haber_ton"]} == {"pozitif": 2, "negatif": 1, "notr": 1, "haber yok": 2}


def test_ton_coin_bazli_ve_bozuk_etiket():
    r = row(1, 1.0, "Neutral", "negatif", pair="ETH/USDT")
    r["features"]["haber"]["BTC"] = {"adet_24s": 3, "ton": "pozitif"}
    assert HS.ton_kovasi(r["features"], "ETH/USDT") == "negatif" and HS.ton_kovasi(r["features"], "SOL/USDT") == "haber yok"
    assert HS.duygu_kovasi({"duygu": {"sinif": "???"}}) == "etiket yok" and HS.duygu_kovasi({"duygu": "x"}) == "etiket yok"
    assert HS.duygu_kovasi(None) == "etiket yok" and HS.ton_kovasi({"haber": {"ETH": {"ton": None}}}, "ETH/USDT") == "haber yok"


def test_bos_durum_ve_ct_bicimi():
    v = HS.olustur([], NOW)
    assert v["sema"] == "ml.haber_sonuc.v1" and v["proje"] == "ML" and v["pencere_gun"] == 7 and v["uretim"] == "2026-11-16T18:00:00Z"
    assert v["tablolar"] == {"duygu": [], "haber_ton": []} and v["tum_zamanlar"] == {"duygu": [], "haber_ton": []}
    assert HS.telegram_satiri(v) == "Haber×sonuç: henüz veri yok"
    assert HS.telegram_satiri(None) == "Haber×sonuç: henüz veri yok"
    dolu = HS.olustur(ROWS, NOW)
    assert set(dolu) == {"sema", "proje", "uretim", "pencere_gun", "tablolar", "tum_zamanlar", "notlar"}
    for tb in (dolu["tablolar"], dolu["tum_zamanlar"]):
        for satirlar in tb.values():
            assert all(tuple(r) == CT_SUTUNLAR for r in satirlar)
    json.dumps(dolu, allow_nan=False)


def test_telegram_satiri():
    s = HS.telegram_satiri(HS.olustur(ROWS, NOW))
    assert s.startswith("Haber×sonuç (7g) — Duygu: en iyi Aşırı Korku +6,00 $ (n=2)") and "Haber tonu:" in s and "\n" not in s
    yalniz_etiketsiz = HS.olustur([row(1, 3.0)], NOW)
    assert "etiketli işlem yok" in HS.telegram_satiri(yalniz_etiketsiz)


def mk_ledger(path, specs):
    """specs: [(gun_once, win, features_extra)]; gercek defter: karar -> giris -> kapanis."""
    led = L.open_ledger(path, "learner", clock=lambda: NOW)
    led.init_params(PARAMS, reason="x")
    for i, (gun, win, extra) in enumerate(specs, start=1):
        bar = NOW - timedelta(days=gun, hours=2)
        did = led.record_decision(L.DecisionEvent(
            bar_close_ts=bar, trigger_tf="1h", pair="ETH/USDT", side="long", setup="R1", regime="range", atr_ratio=1.1, rh=2100.0, rl=1980.0,
            rh_touches=2, rl_touches=3,
            features={"atr_1h": 20.0, "stop_dist_atr": 2.0, "atr_4h": 40.0, "wick_ratio": 0.5, "rr": 2.5, "edge_dist_atr": 0.1, **extra},
            planned_entry=2000.0, planned_stop=1960.0, planned_target=2100.0, param_version_id=1, veto_status="allowed", veto_reason=None,
            risk_allowed=True, risk_reason="ok", size_qty=0.3, size_notional=600.0, size_margin=200.0, size_risk_amount=13.188, leverage=3,
            final_action="entered", skip_reason=None))
        led.record_trade_entry(L.TradeEntry(i, did, bar + timedelta(seconds=3), 2001.0, 0.3, 3, 0.30015))
        led.record_trade_exit(L.TradeExit(i, bar + timedelta(hours=1), 2079.0 if win else 1960.0, "target" if win else "stop", 2100.0, 0.3, 0.1))
    led.close()


def test_defterden_karar_giris_kapanis_baglama(tmp_path):
    etiket = {"duygu": {"deger": 20, "sinif": "Extreme Fear"}, "haber": {"ETH": {"adet_24s": 2, "ton": "negatif"}}}
    mk_ledger(tmp_path / "l.sqlite", [(1, True, etiket), (2, False, etiket), (3, True, {}), (30, False, {"duygu": {"deger": 60, "sinif": "Greed"}})])
    out = tmp_path / "var" / "durum" / "haber_sonuc_v1.json"
    ro = L.open_ledger(tmp_path / "l.sqlite", "learner", create=False, read_only=True, migrate=False)
    try:
        v = HS.yaz(ro, NOW, out)
    finally:
        ro.close()
    assert json.loads(out.read_text(encoding="utf-8")) == v
    d = {r["etiket"]: r for r in v["tablolar"]["duygu"]}
    assert d["Aşırı Korku"]["n"] == 2 and d["Aşırı Korku"]["kazanan"] == 1 and d["etiket yok"]["n"] == 1 and "Açgözlülük" not in d
    assert d["Aşırı Korku"]["toplam_pnl"] == pytest.approx(d["Aşırı Korku"]["ortalama_pnl"] * 2, abs=0.01)
    assert {r["etiket"]: r["n"] for r in v["tum_zamanlar"]["duygu"]}["Açgözlülük"] == 1
    assert {r["etiket"]: r["n"] for r in v["tablolar"]["haber_ton"]} == {"negatif": 2, "haber yok": 1}
    assert not list(out.parent.glob(".hs-*"))                                   # atomik yazim: gecici dosya kalmaz


def _weekly():
    sys.path.insert(0, str(ROOT / "scripts"))
    spec = importlib.util.spec_from_file_location("weekly_summary_run_hs", ROOT / "scripts" / "weekly_summary_run.py")
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


def test_haftalik_uretim_ve_bos_durum(tmp_path):
    W = _weekly()
    env = {"TRADER_DATA_ROOT": str(tmp_path)}
    assert W.haber_sonuc_uret(env, str(tmp_path / "yok.sqlite"), NOW) == "Haber×sonuç: henüz veri yok"        # defter yok: istisna yok
    mk_ledger(tmp_path / "l.sqlite", [(1, True, {"duygu": {"deger": 20, "sinif": "Fear"}})])
    s = W.haber_sonuc_uret(env, str(tmp_path / "l.sqlite"), NOW)
    assert s.startswith("Haber×sonuç (7g) — Duygu: en iyi Korku") and (tmp_path / "var" / "durum" / "haber_sonuc_v1.json").exists()


@pytest.fixture()
def env(tmp_path):
    e = Env(tmp_path)
    yield e
    e.close()


def put_json(env, doc):
    p = env.root / "var/durum/haber_sonuc_v1.json"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(doc if isinstance(doc, str) else json.dumps(doc), encoding="utf-8")


def test_panel_karti(env):
    pd_ = PanelData(load_config(env.cfg_path), clock=lambda: NOW)
    assert pd_.habersonuc()["ok"] and pd_.habersonuc()["neden"] == "dosya_yok"
    put_json(env, HS.olustur(ROWS, NOW))
    r = pd_.habersonuc()
    assert r["ok"] and r["var"] and r["pencere_gun"] == 7 and tuple(r["tablolar"]["duygu"][0]) == CT_SUTUNLAR
    put_json(env, HS.olustur([], NOW))
    assert pd_.habersonuc()["neden"] == "kayit_yok"
    put_json(env, "{bozuk")
    assert pd_.habersonuc()["var"] is False
    put_json(env, {"sema": "x"})
    assert pd_.habersonuc()["neden"] == "sema_yanlis"
    assert P.haber_sonuc_view("")["var"] is False
