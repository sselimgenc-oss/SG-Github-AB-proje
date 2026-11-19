"""Haftalik disk bakimi (scripts/bakim_run.py): silme izin listesi, saklama suresi, sqlite hata toleransi. Sentetik tmp_path; gercek var/ yok."""
import os
import sqlite3
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import bakim_run as B  # noqa: E402

NOW = time.time()
GUN = 86400


def _f(p: Path, gun: float, data="x"):
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(data)
    os.utime(p, (NOW - gun * GUN,) * 2)
    return p


def _db(p: Path, satir=2000, sil=True):
    p.parent.mkdir(parents=True, exist_ok=True)
    c = sqlite3.connect(p)
    c.execute("create table t(a,b)")
    c.executemany("insert into t values(?,?)", [(i, "x" * 100) for i in range(satir)])
    c.commit()
    if sil:
        c.execute("delete from t where a%2=0")
        c.commit()
    c.close()
    return p


def _eski_yap(p: Path, gun=400):
    for q in [p, *p.rglob("*")]:
        os.utime(q, (NOW - gun * GUN,) * 2)


def test_korunan_dosyalar_cok_eski_olsa_da_silinmez(tmp_path):
    v = tmp_path / "var"
    korunan = [_f(v / "learner" / "ledger.sqlite", 999), _f(v / "learner" / "counterfactual.sqlite", 999),
               _f(v / "market.sqlite", 999), _f(v / "history" / "BTC.feather", 999), _f(v / "history_x" / "a.json", 999),
               _f(v / "durum" / "haber_v1.json", 999), _f(v / "durum" / "tutarlilik_v1.json", 999),
               _f(v / "learner" / "state.sqlite", 999), _f(v / "learner" / "status.json", 999),
               _f(v / "vision_raw" / "z.zip", 999)]
    B.kos(v, now=NOW, bos_yer_fn=lambda p: 0)
    assert all(p.exists() for p in korunan)


def test_izin_listesi_eski_siler_yeniyi_ve_izin_disini_birakir(tmp_path):
    v = tmp_path / "var"
    eski = [_f(v / "rapor" / "tutarlilik" / "2020-01-01.md", 120), _f(v / "rapor" / "x" / "y" / "a.json", 120),
            _f(v / "learner" / "weekly_summaries" / "2020-W01.md", 120), _f(v / "snapshots" / "s1.json", 120)]
    yeni_ve_disi = [_f(v / "rapor" / "tutarlilik" / "2026-11-10.md", 10), _f(v / "learner" / "weekly_summaries" / "2026-W45.md", 3),
                    _f(v / "baska" / "eski.txt", 500), _f(v / "learner" / "notlar.md", 500), _f(v / "rapor" / "ham.bin", 500)]
    # her dizinde en yeni dosya korunur: eski.md tek basina kalan dosya olmamali -> yanlarina yeni dosya konuldu (yukarida)
    # snapshots ve rapor/x/y tek dosyali: en yeni oldugu icin KALIR
    ozet = B.kos(v, now=NOW, bos_yer_fn=lambda p: 0)
    assert not eski[0].exists() and not eski[2].exists()
    assert eski[1].exists() and eski[3].exists()                 # dizinin tek/en yeni dosyasi korunur
    assert all(p.exists() for p in yeni_ve_disi)
    assert ozet["silinen"]["dosya"] == 2


def test_saklama_suresi_sinirda(tmp_path):
    v = tmp_path / "var"
    a = _f(v / "rapor" / "a.md", B.SAKLAMA_GUN - 1)
    b = _f(v / "rapor" / "b.md", B.SAKLAMA_GUN + 1)
    c = _f(v / "rapor" / "c.md", 1)
    B.kos(v, now=NOW, bos_yer_fn=lambda p: 0)
    assert a.exists() and c.exists() and not b.exists()
    d = _f(v / "rapor" / "d.md", 40)
    B.kos(v, now=NOW, saklama_gun=30, bos_yer_fn=lambda p: 0)    # ozel sure
    assert not d.exists() and not a.exists() and c.exists()


def test_gecici_dizinler_ve_calisma_dizini(tmp_path):
    v = tmp_path / "var"
    work = v / "rapor" / "tutarlilik" / ".work" / "run1"
    _db(work / "ledger.sqlite", 10, False)                       # gocurulmus kopya: atilabilir
    _eski_yap(work)
    _eski_yap(work.parent)
    tmp = tmp_path / "tmp"
    eski_t = tmp / "exitcf_bt_abc"
    yeni_t = tmp / "exitcf_bt_new"
    diger = tmp / "baska_dizin"
    for d in (eski_t, yeni_t, diger):
        _f(d / "ledger.sqlite", 0)
    _eski_yap(eski_t)
    _eski_yap(diger)
    B.kos(v, now=NOW, gecici_kok=tmp, bos_yer_fn=lambda p: 0)
    assert not work.exists() and not eski_t.exists()
    assert yeni_t.exists() and diger.exists()


def test_var_disina_ve_symlink_dokunulmaz(tmp_path):
    v = tmp_path / "var"
    dis = _f(tmp_path / "disarida" / "a.md", 999)
    (v / "rapor").mkdir(parents=True)
    (v / "rapor" / "link.md").symlink_to(dis)
    os.utime(v / "rapor" / "link.md", (NOW - 999 * GUN,) * 2, follow_symlinks=False)
    _f(v / "rapor" / "yeni.md", 1)
    B.kos(v, now=NOW, bos_yer_fn=lambda p: 0)
    assert dis.exists() and (v / "rapor" / "link.md").is_symlink()


def test_dry_run_hicbir_sey_degistirmez(tmp_path):
    v = tmp_path / "var"
    e = _f(v / "rapor" / "e.md", 200)
    _f(v / "rapor" / "y.md", 1)
    d = _db(v / "counterfactual.sqlite")
    boyut = d.stat().st_size
    B.kos(v, now=NOW, dry_run=True)
    assert e.exists() and d.stat().st_size == boyut


def test_canli_acik_defterde_vacuum_yok_yalniz_passive(tmp_path):
    v = tmp_path / "var"
    led = _db(v / "learner" / "ledger.sqlite")
    boyut = led.stat().st_size
    assert B.sqlite_bakim(led, bos_yer_fn=lambda p: 10**12) == "passive"
    assert led.stat().st_size == boyut                           # VACUUM olsaydi kuculurdu
    for ad in ("market.sqlite", "state.sqlite"):
        assert B.sqlite_bakim(_db(v / ad), bos_yer_fn=lambda p: 10**12) == "passive"


def test_canli_olmayan_defter_vacuumlanir_ve_bos_yer_yetmezse_yapilmaz(tmp_path):
    v = tmp_path / "var"
    d = _db(v / "counterfactual.sqlite")
    boyut = d.stat().st_size
    assert B.sqlite_bakim(d, bos_yer_fn=lambda p: 0) == "truncate"    # bos yer yok: VACUUM yok
    assert d.stat().st_size == boyut
    assert B.sqlite_bakim(d, bos_yer_fn=lambda p: 10**12) == "vacuum"
    assert d.stat().st_size < boyut
    n = sqlite3.connect(d).execute("select count(*) from t").fetchone()[0]
    assert n == 1000                                             # veri bozulmadi


def test_baska_yazar_kilit_tutarken_vacuum_atlanir(tmp_path):
    d = _db(tmp_path / "var" / "counterfactual.sqlite")
    boyut = d.stat().st_size
    w = sqlite3.connect(d, isolation_level=None)
    w.execute("BEGIN IMMEDIATE")                                 # yazar acik
    try:
        s = B.sqlite_bakim(d, bos_yer_fn=lambda p: 10**12)
    finally:
        w.execute("ROLLBACK")
        w.close()
    assert s != "vacuum" and d.stat().st_size == boyut


def test_sqlite_hata_toleransi_bozuk_dosya_digerlerini_durdurmaz(tmp_path):
    v = tmp_path / "var"
    (v / "a").mkdir(parents=True)
    (v / "a" / "bozuk.sqlite").write_bytes(b"bu bir sqlite dosyasi degil" * 50)
    (v / "b").mkdir()
    (v / "b" / "bos.sqlite").write_bytes(b"")
    iyi = _db(v / "z" / "counterfactual.sqlite")
    boyut = iyi.stat().st_size
    ozet = B.kos(v, now=NOW, bos_yer_fn=lambda p: 10**12)        # istisna firlatmaz
    assert ozet["sqlite"][str(v / "a" / "bozuk.sqlite")].startswith("atlandi")
    assert ozet["sqlite"][str(iyi)] == "vacuum" and iyi.stat().st_size < boyut


def test_var_yoksa_sorunsuz(tmp_path):
    assert B.kos(tmp_path / "yok", now=NOW)["sqlite"] == {}
    assert B.main(["--var-dir", str(tmp_path / "yok")]) == 0


def test_izin_listesi_defter_adlarini_icermez():
    for pat, _t in B.SILME_IZIN:
        assert ".sqlite" not in pat and "history" not in pat and "durum" not in pat
