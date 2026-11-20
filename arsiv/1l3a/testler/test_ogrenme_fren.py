"""Ders freni + geri alma (ogrenme_adaptor.fren_adimi): askıya alma, yeniden ölçüm, Düzeldi, emekli, Bildirimci 6 saat kuralı."""
import json
from datetime import datetime

import pandas as pd

from motor.canli import ogrenme_adaptor as oa
from motor.canli import telegram as tg
from motor.ortak_ogrenme import kayit as ok

A = "a|XUSDT|1d"
NOW = pd.Timestamp("2026-11-19 12:00", tz="UTC")


def _ts_aday(id_, r, gun):
    return ok.Aday(id=id_, proje="1L3A", kurulum=oa.temiz_ad(A), enstruman="XUSDT", varlik_sinifi="kripto", yon="long",
                   ts=datetime.fromisoformat(gun + "T00:00:00+00:00"), alindi=True, r=r, ozellikler={"atr_ratio": 2.0})


def _fren_og(tmp_path, kf_r, gonderilen, durum="alive"):
    """kf_r: engellenen sinyallerin simüle R listesi (kontrafaktüel)."""
    kimlik = "yuksek_vol:" + oa.temiz_ad(A)
    tmp_path.mkdir(parents=True, exist_ok=True)
    (tmp_path / oa.DERS_DOSYASI).write_text(json.dumps({kimlik: {"status": durum, "born": "2026-11-01", "effect": 1.0, "n": 5}}))
    og = oa.Ogrenme(tmp_path, gonder=lambda m: True, saat=lambda: NOW)
    og.bildirimci = tg.Bildirimci(gonder_fn=lambda m: gonderilen.append(m) or True, ortak=tg.OrtakDurum(), servis="paper")
    og.engellenenler = lambda simdi: [_ts_aday(f"kf{i}", r, "2026-11-10") for i, r in enumerate(kf_r)]
    og.kapananlar = []
    return og, kimlik


def test_geri_alma_tek_ders_eksi_3r_emekli_ve_warn(tmp_path):
    g = []
    og, kimlik = _fren_og(tmp_path, [1.5, 1.5], g)               # ders etkisi -3 R -> geri al
    r = og.fren_adimi(NOW)
    assert r["geri_alinan"] == [kimlik]
    assert json.loads((tmp_path / oa.DERS_DOSYASI).read_text())[kimlik]["status"] == "retired"
    assert og.giris_suzgeci(A, "XUSDT", "long", {"atr_ratio": 2.0}) == (True, "")
    assert len(g) == 1 and "⚠️" in g[0] and "kaldırıldı" in g[0]


def test_fren_askiya_alma_olcme_ve_duzeldi(tmp_path, monkeypatch):
    g = []
    monkeypatch.setattr(oa, "FREN_ESIK_R", 1.5)                   # etki -2 R: geri alma (-3) değil, fren (<= -1.5)
    og, kimlik = _fren_og(tmp_path, [1.0, 1.0], g)
    r = og.fren_adimi(NOW)
    assert r["askiya"] == [kimlik] and r["geri_alinan"] == []
    assert og.giris_suzgeci(A, "XUSDT", "long", {"atr_ratio": 2.0}) == (True, "")        # askıda: engellemez
    assert any("Dersler durduruldu" in x and "⚠️" in x for x in g)
    og.engellenenler = lambda simdi: []                           # askıdan sonra eşleşen alınmış işlemler zarar eder -> ders yine değerli
    og.kapananlar = [_ts_aday(f"t{i}", -1.0, "2026-11-20") for i in range(2)]
    r2 = og.fren_adimi(NOW + pd.Timedelta(days=1))
    assert r2["dondu"] == [kimlik]
    assert og.giris_suzgeci(A, "XUSDT", "long", {"atr_ratio": 2.0}) == (False, "ders:yuksek_vol")
    assert any("Düzeldi" in x and "INFO" not in x for x in g)


def test_askidaki_ders_askidan_sonra_kotu_giderse_emekli(tmp_path, monkeypatch):
    g = []
    monkeypatch.setattr(oa, "FREN_ESIK_R", 1.5)
    og, kimlik = _fren_og(tmp_path, [1.0, 1.0], g)
    og.fren_adimi(NOW)
    og.engellenenler = lambda simdi: []
    og.kapananlar = [_ts_aday(f"t{i}", 2.0, "2026-11-20") for i in range(2)]      # askıdan sonra +4 R kaçtı -> etki -4
    r = og.fren_adimi(NOW + pd.Timedelta(days=1))
    assert r["geri_alinan"] == [kimlik]


def test_fren_bildirimi_6_saat_kuraliyla_tekrarlanmaz(tmp_path):
    g = []
    og, kimlik = _fren_og(tmp_path, [2.0, 2.0], g)
    og.fren_adimi(NOW)
    (tmp_path / oa.DERS_DOSYASI).write_text(json.dumps({kimlik: {"status": "candidate", "born": "2026-11-01", "effect": None, "n": 0}}))
    og.fren_adimi(NOW + pd.Timedelta(hours=1))
    assert len(g) == 1                                            # aynı anahtar 6 saatte bir


def test_fren_hatasi_gece_adimini_bozmaz(tmp_path):
    og = oa.Ogrenme(tmp_path, gonder=lambda m: True, saat=lambda: NOW)
    og.fren_adimi = lambda s: 1 / 0
    assert og.gunluk(pd.Timestamp("2026-11-19 21:40", tz="UTC"))


# ---------------------------------------------------------------------------- C3: gözlemsiz aday ders karşı-olgu gözlemi
def _aday_og(tmp_path, durum="candidate", n=0):
    kimlik = "yuksek_vol:" + oa.temiz_ad(A)
    tmp_path.mkdir(parents=True, exist_ok=True)
    (tmp_path / oa.DERS_DOSYASI).write_text(json.dumps({kimlik: {"status": durum, "born": "2026-11-01", "effect": None, "n": n}}))
    og = oa.Ogrenme(tmp_path, gonder=lambda m: True, saat=lambda: NOW)
    return og, kimlik


def _durum_oku(tmp_path, kimlik):
    return json.loads((tmp_path / oa.DERS_DOSYASI).read_text())[kimlik]


def test_aday_ders_engelledigi_giris_kaybettirecekti_alive_olur(tmp_path):
    og, kimlik = _aday_og(tmp_path)
    r = og.aday_karsi_olgu([_ts_aday("kf0", -1.0, "2026-11-10"), _ts_aday("kf1", -0.5, "2026-11-11")], NOW)
    assert r == {"alive": [kimlik], "retired": []}
    d = _durum_oku(tmp_path, kimlik)
    assert d["status"] == "alive" and d["n"] == 2 and d["effect"] == 1.5


def test_aday_ders_engelledigi_giris_kazandiracakti_emekli_olur(tmp_path):
    og, kimlik = _aday_og(tmp_path)
    r = og.aday_karsi_olgu([_ts_aday("kf0", 0.5, "2026-11-10")], NOW)
    assert r == {"alive": [], "retired": [kimlik]}
    d = _durum_oku(tmp_path, kimlik)
    assert d["status"] == "retired" and d["retired_day"] == "2026-11-19"
    assert kimlik not in og._etkin_dersler()                       # emekli ders artık engellemez


def test_aday_ders_gozlem_yoksa_aday_kalir_ve_yalniz_adayi_ele_alir(tmp_path):
    og, kimlik = _aday_og(tmp_path)
    assert og.aday_karsi_olgu([], NOW) == {"alive": [], "retired": []}
    assert _durum_oku(tmp_path, kimlik)["status"] == "candidate"
    assert og.aday_karsi_olgu([_ts_aday("kf0", -9.0, "2026-10-30")], NOW)["alive"] == []   # doğumdan ÖNCE: sayılmaz
    og2, k2 = _aday_og(tmp_path / "b", durum="alive", n=3)                                # alive ders bu adımda ele alınmaz
    assert og2.aday_karsi_olgu([_ts_aday("kf0", 5.0, "2026-11-10")], NOW) == {"alive": [], "retired": []}
    assert _durum_oku(tmp_path / "b", k2)["status"] == "alive"


def test_gunluk_aday_ders_karsi_olgu_ile_cozulur(tmp_path):
    og, kimlik = _aday_og(tmp_path)
    og.kapananlar = []
    og.alinmayanlar = lambda: []
    og.engellenenler = lambda simdi: [_ts_aday("kf0", -1.0, "2026-11-10")]
    assert og.gunluk(pd.Timestamp("2026-11-19 21:40", tz="UTC"))
    assert _durum_oku(tmp_path, kimlik)["status"] == "alive"


def test_karsi_olgu_hatasi_gece_adimini_bozmaz(tmp_path):
    og, kimlik = _aday_og(tmp_path)
    og.alinmayanlar = lambda: []
    og.engellenenler = lambda simdi: 1 / 0
    assert og.gunluk(pd.Timestamp("2026-11-19 21:40", tz="UTC"))
    assert _durum_oku(tmp_path, kimlik)["status"] == "candidate"
