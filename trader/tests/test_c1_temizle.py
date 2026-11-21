"""CT/C1 ayriligi veri temizligi (scripts/c1_temizle.py; docs/motor/ct-ayrilik-spec.md bolum 4-5): sentetik var dizini + sentetik defter.
Dosya duzeyi temizlik hedeflenenleri siler, digerlerine dokunmaz, idempotenttir; DEFTERE dokunmaz (yalnizca-ekleme tetikleyicileri) ve
C1'in net K/Z'sini salt okunur raporlar (kasa degismez)."""
from __future__ import annotations

import hashlib
import importlib.util
import json
import sqlite3
import sys
from datetime import timedelta

import pytest

from panel_support import ROOT
from test_strateji_veri import D0, mk  # noqa: E402

sys.path.insert(0, str(ROOT / "scripts"))
_spec = importlib.util.spec_from_file_location("c1_temizle", ROOT / "scripts" / "c1_temizle.py")
C = importlib.util.module_from_spec(_spec)
sys.modules["c1_temizle"] = C
_spec.loader.exec_module(C)


def _sha(p):
    return hashlib.sha256(p.read_bytes()).hexdigest()


def _kur(tmp_path):
    var = tmp_path / "var"
    (var / "ct").mkdir(parents=True)
    (var / "ct" / "kadro_yon.json").write_text("{}")
    (var / "ct" / "durum.json").write_text("{}")
    mdl = var / "learner" / "models" / "ortak_filtre"
    (mdl / "eski_kol").mkdir(parents=True)
    for ad in ("aile_C1.json", "aile_T1.json", "aile_TF1.json"):
        (mdl / ad).write_text('{"x": 1}')
    for ad in ("C1@1h.json", "C1@4h.json", "T1@1h.json"):
        (mdl / "eski_kol" / ad).write_text('{"x": 1}')
    (var / "learner" / "paper_models.csv").write_text("kol,n,neden\nT1,10,ok\nC1,3,model yok\nTF1,9,ok\nC1@4h,1,x\n")
    (var / "learner" / "arms_off.json").write_text(json.dumps({"arms": ["C1@1h", "T1@1h"], "sebep": {"C1@1h": "x", "T1@1h": "y"}}))
    (var / "durum").mkdir()
    (var / "durum" / "etiket_kurallari_v1.json").write_text(json.dumps({"sema": "ml.etiket_kurallari.v1", "uretim": None, "kurallar": {
        "etiket_rejim": {"acik": True, "gecmis": []}, "etiket_kalabalik": {"acik": False, "gecmis": [{"olay": "kapandi"}]}}}))
    saglik = tmp_path / "saglik.json"
    saglik.write_text(json.dumps({"ek_uyarilar": {"ct_kadro|bayat": {"ilk": "x", "son": "y"}, "disk|dolu": {"ilk": "x", "son": "y"}}}))
    mk(str(var / "learner" / "ledger.sqlite"), extra=[("C1@1h", "long", "range", "win", D0 + timedelta(days=5)),
                                                      ("C1@1h", "short", "range", "loss", D0 + timedelta(days=6)),
                                                      ("C1@1h", "long", "range", "open", D0 + timedelta(days=7))])
    return var, saglik


def _toplam(led, setup_neg=False):
    con = sqlite3.connect(f"file:{led}?mode=ro", uri=True)
    try:
        op = "<>" if setup_neg else "="
        return con.execute(f"SELECT COUNT(*), COALESCE(SUM(realized_pnl),0), COALESCE(SUM(fee_entry),0) FROM v_closed_trades WHERE setup {op} 'C1'").fetchone()
    finally:
        con.close()


def test_dosya_temizligi_hedefleri_siler_digerlerine_dokunmaz_ve_idempotent(tmp_path):
    var, saglik = _kur(tmp_path)
    ozet = C.calistir(var, saglik_durum=saglik)
    assert not (var / "ct").exists()
    mdl = var / "learner" / "models" / "ortak_filtre"
    assert sorted(p.name for p in mdl.iterdir() if p.is_file()) == ["aile_T1.json", "aile_TF1.json"]
    assert sorted(p.name for p in (mdl / "eski_kol").iterdir()) == ["T1@1h.json"]
    assert (var / "learner" / "paper_models.csv").read_text() == "kol,n,neden\nT1,10,ok\nTF1,9,ok\n"
    off = json.loads((var / "learner" / "arms_off.json").read_text())
    assert off == {"arms": ["T1@1h"], "sebep": {"T1@1h": "y"}}
    et = json.loads((var / "durum" / "etiket_kurallari_v1.json").read_text())
    assert list(et["kurallar"]) == ["etiket_rejim"]
    assert list(json.loads(saglik.read_text())["ek_uyarilar"]) == ["disk|dolu"]
    assert (var / C.ISARET).is_file() and ozet["defter_dokunuldu"] is False
    # ikinci calisma: hicbir degisiklik, ayni dosya durumu
    once = {str(p): _sha(p) for p in var.rglob("*") if p.is_file() and p.name != C.ISARET and p.suffix != ".sqlite"}
    ozet2 = C.calistir(var, saglik_durum=saglik)
    assert {str(p): _sha(p) for p in var.rglob("*") if p.is_file() and p.name != C.ISARET and p.suffix != ".sqlite"} == once
    assert {k: v for k, v in ozet2.items() if k not in ("defter_rapor", "defter_dokunuldu")} == {}


def test_defter_degismez_kasa_ayni_ve_c1_net_kz_raporlanir(tmp_path):
    var, saglik = _kur(tmp_path)
    led = var / "learner" / "ledger.sqlite"
    h0 = _sha(led)
    diger0, c1 = _toplam(led, True), _toplam(led)
    assert c1[0] == 2 and diger0[0] > 0
    ozet = C.calistir(var, saglik_durum=saglik)
    assert _sha(led) == h0                                                     # defter dosyasi bayt bayt ayni
    assert _toplam(led, True) == diger0 and _toplam(led) == c1                 # diger kollar da C1 de (kasa) degismedi
    r = ozet["defter_rapor"]
    assert r["c1_kapanan"] == 2 and abs(r["c1_net_kz"] - c1[1]) < 1e-9 and r["c1_islem"] == 3 and r["c1_karar"] == 3
    assert C.calistir(var)["defter_rapor"] == r                               # idempotent


def test_defter_yalnizca_ekleme_tetikleyicisi_silmeyi_reddeder(tmp_path):
    """Celiski belgesi: C1 satirlarini silmek yalnizca-ekleme korumasini kapatmayi gerektirir; betik bunu yapmaz."""
    var, _ = _kur(tmp_path)
    con = sqlite3.connect(var / "learner" / "ledger.sqlite")
    try:
        with pytest.raises(sqlite3.DatabaseError, match="append-only"):
            con.execute("DELETE FROM trade_entries WHERE setup='C1'")
    finally:
        con.close()


def test_main_cikis_kodu_ve_isaret(tmp_path):
    var, saglik = _kur(tmp_path)
    assert C.main(["--var-dir", str(var), "--saglik-durum", str(saglik)]) == 0
    assert (var / C.ISARET).is_file()
    assert C.main(["--var-dir", str(tmp_path / "yok")]) == 1


def test_v2_isaret_ve_setup_filter_ile_tum_models_c1_paketleri(tmp_path):
    assert C.ISARET == "c1_temizle_v2.done"
    var = tmp_path / "var"
    sf = var / "learner" / "models" / "setup_filter"
    sf.mkdir(parents=True)
    for ad in ("C1@1h.json", "C1@1h.prev.json", "C1@4h.json", "T1@1h.json"):
        (sf / ad).write_text("{}")
    of = var / "twin" / "models" / "ortak_filtre"
    of.mkdir(parents=True)
    for ad in ("aile_C1.json", "aile_C1.prev.json", "aile_T1.json"):
        (of / ad).write_text("{}")
    (var / "learner" / "paper_models.csv").write_text(
        "ad,sinif,tarif\nortak_filtre_aile_C1_2026-11-20,nightly,ridge;aile=C1\nsetup_filter_nightly_2026-11-20,nightly,arms=3\n"
        "ortak_filtre_aile_T1_2026-11-20,nightly,ridge;aile=T1\n")
    ozet = C.calistir(var)
    assert sorted(p.name for p in sf.iterdir()) == ["T1@1h.json"]
    assert sorted(p.name for p in of.iterdir()) == ["aile_T1.json"]
    txt = (var / "learner" / "paper_models.csv").read_text()
    assert "C1" not in txt and "aile_T1" in txt and "setup_filter_nightly" in txt
    assert ozet["paket"] == 5 and (var / C.ISARET).is_file()
    assert C.calistir(var, isaret_yaz=False).get("paket") is None                 # idempotent
