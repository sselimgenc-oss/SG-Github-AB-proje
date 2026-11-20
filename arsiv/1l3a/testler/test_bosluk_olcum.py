"""araclar/bosluk_olcum.py: istatistik, emtia aralık sınıflaması, hisse gece/hafta sonu sınıflaması, ek stres formülü."""
import json

import pandas as pd

from araclar import bosluk_olcum as bo


def _mum(zamanlar, acilis, kapanis):
    return pd.DataFrame({"acilis": acilis, "kapanis": kapanis, "yuksek": acilis, "dusuk": acilis},
                        index=pd.DatetimeIndex(zamanlar, tz="UTC"))


def test_istatistik_esikler_ve_en_kotu():
    o = [(0.01, "A", "d1"), (0.06, "B", "d2"), (0.30, "C", "d3")]
    s = bo.istatistik(o)
    assert s["n"] == 3 and abs(s["maks"] - 0.30) < 1e-12
    assert s["en_kotu5"][0]["sembol"] == "C" and s["adet"]["5"] == 2 and s["adet"]["25"] == 1
    assert bo.istatistik([]) == {"n": 0}


def test_hisse_gece_hafta_sonu_ve_split_dislanir():
    # Per 2024-01-04 -> Cum 2024-01-05 (gece), Cum -> Pzt 2024-01-08 (hafta sonu); 14:30 UTC = 09:30 NY (kış)
    z = ["2024-01-04 14:30", "2024-01-04 21:00", "2024-01-05 14:30", "2024-01-05 21:00", "2024-01-08 14:30", "2024-01-08 21:00"]
    m = _mum(z, [100.0, 100.0, 101.0, 101.0, 103.02, 103.02], [100.0, 100.0, 101.0, 101.0, 103.02, 103.02])
    o, atlanan, split = bo.hisse_olaylari("DK_AAPL", m)
    assert len(o["gece"]) == 1 and abs(o["gece"][0][0] - 0.01) < 1e-9
    assert len(o["hafta_sonu"]) == 1 and abs(o["hafta_sonu"][0][0] - 0.02) < 1e-9
    assert atlanan == 0 and not split
    m2 = m.copy()
    m2.iloc[4:, m2.columns.get_loc("acilis")] = 20.0
    m2.iloc[4:, m2.columns.get_loc("kapanis")] = 20.0
    assert len(bo.hisse_olaylari("DK_AAPL", m2)[2]) == 1


def test_emtia_aralik_siniflari():
    # Sal 16:55 NY -> 18:00 NY (günlük mola = gece); Cuma 16:55 NY -> Pazar 18:00 NY (hafta sonu); Ocak: UTC-5
    z = ["2024-01-02 21:55", "2024-01-02 23:00", "2024-01-05 21:55", "2024-01-07 23:00"]
    m = _mum(z, [100.0, 100.5, 100.5, 102.0], [100.0, 100.5, 100.5, 102.0])
    o, atlanan = bo.emtia_olaylari("DK_XAU", m)
    assert len(o["gece"]) == 1 and len(o["hafta_sonu"]) == 1 and atlanan == 0
    assert abs(o["hafta_sonu"][0][0] - (102.0 / 100.5 - 1)) < 1e-9


def test_ek_stres_formul(tmp_path):
    ham = {"bosluk_stresi": {"canli|5": {"hesaplar": {"a": {"tepe_brut": 1.0}, "b": {"tepe_brut": 2.0}}, "birlesik_brut": 0.5}}}
    p = tmp_path / "h.json"
    p.write_text(json.dumps(ham))
    r = bo.ek_stres(p)["canli|5"]
    assert r["20"]["en_kotu_hesap"] == "b" and abs(r["20"]["en_kotu_hesap_kayip_yuzde"] - 40.0) < 1e-9
    assert r["20"]["tek_poz_likide"] is True            # 20 > 19,5
    assert r["25"]["birlesik_kayip_yuzde"] == 12.5
