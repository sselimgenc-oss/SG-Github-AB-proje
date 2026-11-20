"""Sentetik testler: araclar/canli_oynatma_300.py"""
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from araclar import canli_oynatma_300 as m  # noqa: E402


def mk(rows):
    return pd.DataFrame([{"giris_zamani": pd.Timestamp(g, tz="UTC"), "cikis_zamani": pd.Timestamp(c, tz="UTC"), "yon": y, "r": r, "sf": sf,
                          "stop_mesafe": sf * px, "fonlama_r": 0.0, "sembol": s} for g, c, y, r, sf, px, s in rows])


def test_stop_cok_uzak_atlanir():
    o = m.oynat(mk([("2021-01-01", "2021-01-05", 1, 1.0, 0.30, 100.0, "ADAUSDT")]), 0.015)
    assert o["alinan"] == 0 and o["neden"]["stop_cok_uzak"] == 1


def test_tam_alinir_ve_pnl():
    # sf %5, risk %1,5 -> yaklaşık 4,5 USD risk / (stop+maliyet); r=+2 -> kazanç ~ 9 USD civarı
    o = m.oynat(mk([("2021-01-01", "2021-01-05", 1, 2.0, 0.05, 10.0, "ADAUSDT")]), 0.015)
    assert o["tam"] == 1 and 305 < o["son"] < 312


def test_zorunlu_kapanis_haric():
    o = m.oynat(mk([("2025-11-01", "2025-11-08", 1, 1.0, 0.05, 10.0, "ADAUSDT")]), 0.015)
    assert o["sinyal"] == 0


def test_toplam_risk_ve_kisaltma():
    # 5 eşzamanlı farklı sembol: ilk 3 tam (3x4,5=13,5 > 18? 6% = 18 USD -> 4 tam), sonrası kısaltılmış/atlanır
    rows = [("2021-01-01", "2021-02-01", 1, 0.5, 0.05, 10.0, s) for s in ["ADAUSDT", "XRPUSDT", "XLMUSDT", "TRXUSDT", "DOGEUSDT", "SOLUSDT"]]
    o = m.oynat(mk(rows), 0.015)
    assert o["tam"] == 4 and (o["kisaltilmis"] + o["neden"]["toplam_risk"]) >= 1 and o["alinan"] <= 6


def test_ayni_sembol():
    o = m.oynat(mk([("2021-01-01", "2021-01-10", 1, 1, 0.05, 10.0, "ADAUSDT"), ("2021-01-02", "2021-01-03", 1, 1, 0.05, 10.0, "ADAUSDT")]), 0.015)
    assert o["alinan"] == 1 and o["neden"]["diger"] == 1


def test_min_tutar_btc():
    # 300 USD, risk 4,5 USD, sf %5 -> nominal ~80 < BTC min 100 -> atla
    o = m.oynat(mk([("2021-01-01", "2021-01-05", 1, 1.0, 0.05, 50000.0, "BTCUSDT")]), 0.015)
    assert o["neden"]["min_tutar_gercek"] == 1


def test_gunluk_stop_ve_kill():
    # ardışık %-1,5 kayıplar (r=-1): günlük -%6 sonrası aynı gün giriş yok
    rows = []
    for i, s in enumerate(["ADAUSDT", "XRPUSDT", "XLMUSDT", "TRXUSDT", "DOGEUSDT"]):
        rows.append((f"2021-01-01 0{i}:00", f"2021-01-01 0{i}:30", 1, -1.2, 0.05, 10.0, s))
    rows.append(("2021-01-01 12:00", "2021-01-01 13:00", 1, 1.0, 0.05, 10.0, "SOLUSDT"))
    o = m.oynat(mk(rows), 0.03)
    assert o["neden"]["gunluk_stop"] >= 1


def test_kill():
    rows = [(f"2021-01-{i + 1:02d}", f"2021-01-{i + 1:02d} 12:00", 1, -1.2, 0.05, 10.0, "ADAUSDT") for i in range(25)]
    o = m.oynat(mk(rows), 0.015)
    assert o["kill"] and o["neden"]["kill"] > 0


def test_butce_kirintisi_min_tutar_degil():
    # 4 tam pozisyon %6 bütçeyi doldurur; 5.sinin kalan bütçesi < min tutar -> etiket toplam_risk (gerçek min tutar DEĞİL)
    syms = ["ADAUSDT", "XRPUSDT", "XLMUSDT", "TRXUSDT", "DOGEUSDT"]
    rows = [("2021-01-01", "2021-02-01", 1, 0.5, 0.05, 10.0, s) for s in syms]
    o = m.oynat(mk(rows), 0.015)
    assert o["neden"]["min_tutar_gercek"] == 0
    assert o["neden"]["toplam_risk"] + o["kisaltilmis"] >= 1
