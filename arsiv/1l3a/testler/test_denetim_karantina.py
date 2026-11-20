"""Karantina sınır testleri (denetim: mutasyon skoru %47). Kaynak koda dokunmaz; ağ yok."""
import itertools
from pathlib import Path

import pytest

from motor.canli import karantina as kq
from testler.test_karantina import KOL_A, KOL_B, _paper, _tanimlar, _veri


# ---------------------------------------------------------------------------- hedef_eslesir: tüm kombinasyonlar
@pytest.mark.parametrize("hedef,kimlik,gorunur,beklenen", [
    ("hepsi", KOL_A, True, True), ("hepsi", KOL_A, False, True), ("HEPSI", KOL_A, False, True), ("  hepsi  ", KOL_A, True, True),
    ("gizli", KOL_A, False, True), ("Gizli", KOL_A, False, True),
    ("gizli", KOL_A, True, False),                                     # görünür hesap 'gizli' ile eşleşmez
    (KOL_A, KOL_A, True, True), (KOL_A.upper(), KOL_A, True, True), (f" {KOL_A} ", KOL_A, True, True),
    (KOL_A, KOL_A, False, False),                                      # gizli hesap kimlikle eşleşmez (adı sızmasın)
    (KOL_B, KOL_A, True, False), (KOL_B, KOL_A, False, False),
    ("", KOL_A, True, False), ("", KOL_A, False, False),
    ("gizlix", KOL_A, False, False), ("hepsi2", KOL_A, True, False),
    ("gizli", "gizli", True, True),                                    # görünür hesabın kimliği tesadüfen 'gizli' ise kimlik eşleşmesidir
])
def test_hedef_eslesir_kombinasyonlari(hedef, kimlik, gorunur, beklenen):
    assert kq.hedef_eslesir(hedef, kimlik, gorunur) is beklenen


def test_hedef_eslesir_tum_ikili_kombinasyonlar_tutarli():
    for hedef, gorunur in itertools.product(["hepsi", "gizli", KOL_A, KOL_B, ""], [True, False]):
        beklenen = hedef == "hepsi" or (hedef == "gizli" and not gorunur) or (gorunur and hedef == KOL_A)
        assert kq.hedef_eslesir(hedef, KOL_A, gorunur) is beklenen, (hedef, gorunur)


# ---------------------------------------------------------------------------- satir: sınırlar
def test_satir_bos_ve_none():
    assert kq.satir(None) is None
    assert kq.satir({}) is None
    assert kq.satir({"gorunur": [], "gizli": 0}) is None
    assert kq.satir({"gorunur": None, "gizli": None}) is None


def test_satir_yalniz_gorunur_yalniz_gizli_ve_ikisi():
    on = "Karantinada (yeni giriş yok, açık pozisyon stop/hedefle sürer): "
    assert kq.satir({"gorunur": [KOL_A], "gizli": 0}) == on + KOL_A
    assert kq.satir({"gorunur": [], "gizli": 1}) == on + f"{kq.GIZLI_AD} (1)"
    assert kq.satir({"gorunur": [KOL_A, KOL_B], "gizli": 3}) == on + f"{KOL_A}, {KOL_B}, {kq.GIZLI_AD} (3)"
    assert kq.satir({"gorunur": [KOL_A]}) == on + KOL_A               # 'gizli' alanı yok


def test_satir_girdiyi_degistirmez():
    ozet = {"gorunur": [KOL_A], "gizli": 2}
    kq.satir(ozet)
    assert ozet == {"gorunur": [KOL_A], "gizli": 2}


# ---------------------------------------------------------------------------- sabitler, istek dosyası, SHA
def test_sabitler():
    assert kq.BILDIRIM_ARALIK_SN == 6 * 3600
    assert kq.ISTEK_AD == "KARANTINA_KALDIR" and kq.ISTEK_ACK == "karantina_kaldir_islendi.json"
    assert kq.GIZLI_AD == "Diğer hesaplar"


def test_istek_dosyasi_env_ve_varsayilan(tmp_path):
    assert kq.istek_dosyasi(tmp_path, {}) == tmp_path / "KARANTINA_KALDIR"
    assert kq.istek_dosyasi(tmp_path, {"L3A_KARANTINA_KALDIR_DOSYA": ""}) == tmp_path / "KARANTINA_KALDIR"
    assert kq.istek_dosyasi(tmp_path, {"L3A_KARANTINA_KALDIR_DOSYA": str(tmp_path / "x")}) == Path(tmp_path / "x")
    assert isinstance(kq.istek_dosyasi(str(tmp_path), {}), Path)


def test_kod_sha_env_ezer_ve_onbellek(monkeypatch):
    monkeypatch.setenv("L3A_KOD_SHA", "abc123")
    assert kq.kod_sha() == "abc123"
    monkeypatch.delenv("L3A_KOD_SHA")
    monkeypatch.setattr(kq, "_SHA_ONBELLEK", {"sha": "onb"})
    assert kq.kod_sha() == "onb"                                       # önbellekten, git çağrılmadan
    monkeypatch.setattr(kq, "_SHA_ONBELLEK", {})

    def patla(*a, **k):
        raise OSError("git yok")
    monkeypatch.setattr(kq.subprocess, "run", patla)
    assert kq.kod_sha() is None                                        # okunamazsa None


@pytest.mark.parametrize("rc,out,beklenen", [(0, "deadbee\n", "deadbee"), (1, "deadbee\n", None), (0, "  \n", None)])
def test_kod_sha_git_cikti_ve_hata_kodu(monkeypatch, rc, out, beklenen):
    class R:
        returncode, stdout = rc, out
    monkeypatch.delenv("L3A_KOD_SHA", raising=False)
    monkeypatch.setattr(kq, "_SHA_ONBELLEK", {})
    monkeypatch.setattr(kq.subprocess, "run", lambda *a, **k: R())
    assert kq.kod_sha() == beklenen


# ---------------------------------------------------------------------------- bildirim eşiği (6 saat) ve düzeldi
def _p():
    p = _paper(_tanimlar(patla=10 ** 9, basla=10 ** 9), _veri())
    zaman = [1_000_000.0]
    p.saat = lambda: zaman[0]
    giden = []
    p.bildirim = lambda tur, m: giden.append((tur, m))
    return p, giden, zaman


def test_bildirim_tam_6_saat_sinirinda_gider_bir_saniye_oncesinde_gitmez():
    p, giden, z = _p()
    e = TypeError("x")
    p._karantinaya_al(KOL_A, e)
    p.karantina_kaldir(KOL_A, "elle")
    z[0] += kq.BILDIRIM_ARALIK_SN - 1
    p._karantinaya_al(KOL_A, e)
    assert len(giden) == 1                                             # 6 saatten 1 sn önce: bastırılır
    p.karantina_kaldir(KOL_A, "elle")
    z[0] += 1                                                          # ilk bildirimden tam 6 saat sonra: gider (>=)
    p._karantinaya_al(KOL_A, e)
    assert len(giden) == 2


def test_bildirim_sayaci_bastirilinca_ilerlemez():
    p, giden, z = _p()
    e = TypeError("x")
    p._karantinaya_al(KOL_A, e)
    ilk = p.karantina_bildirim[KOL_A]
    p.karantina_kaldir(KOL_A, "elle")
    z[0] += 3600
    p._karantinaya_al(KOL_A, e)
    assert p.karantina_bildirim[KOL_A] == ilk                          # bastırılan mesaj sayacı kaydırmaz
    assert len(giden) == 1


def test_karantina_kaydi_alanlari_ve_hata_kirpma():
    p, _, _ = _p()
    p.kod_sha_fn = lambda: "s1"
    p._karantinaya_al(KOL_A, KeyError("anahtar"))
    r = p.karantina[KOL_A]
    assert r["durum"] == "aktif" and r["sha"] == "s1" and r["hata"] == "KeyError: 'anahtar'" and r["zaman"]
    assert p.motor.karantina == {KOL_A}
    p._karantinaya_al(KOL_B, ValueError("y" * 500))
    assert len(p.karantina[KOL_B]["hata"]) == len("ValueError: ") + 200      # hata metni 200 karaktere kırpılır


def test_karantina_kaldir_yalniz_aktifte_calisir():
    p, _, _ = _p()
    assert p.karantina_kaldir(KOL_A, "elle") is False                  # kayıt yok
    p._karantinaya_al(KOL_A, TypeError("x"))
    assert p.karantina_kaldir(KOL_A, "elle") is True
    assert p.karantina[KOL_A]["durum"] == "deneme" and p.motor.karantina == set()
    assert p.karantina_kaldir(KOL_A, "elle") is False                  # zaten 'deneme'


def test_duzeldi_bildirimi_tek_ve_kayit_silinir():
    p, giden, _ = _p()
    p._karantinaya_al(KOL_A, TypeError("x"))
    giden.clear()
    p._karantina_duzeldi(KOL_A)
    assert KOL_A not in p.karantina and p.motor.karantina == set()
    assert giden == [("karantina_cikis", f"{KOL_A} düzeldi, karantinadan çıktı")]
    p._karantina_duzeldi(KOL_A)                                        # kayıt yokken de hata vermez
    assert KOL_A not in p.karantina


def test_gizli_hesapta_duzeldi_ve_karantina_mesajinda_ad_yok():
    p, giden, _ = _p()
    p.gorunur = False
    p._karantinaya_al(KOL_A, TypeError("x"))
    p._karantina_duzeldi(KOL_A)
    metin = " ".join(m for _, m in giden)
    assert "AUSDT" not in metin and kq.GIZLI_AD in metin
    assert p.karantina_ozeti() == {"gorunur": [], "gizli": 0}          # düzeldikten sonra boş


def test_sha_kontrol_sinirlari():
    p, _, _ = _p()
    p.kod_sha_fn = lambda: "s1"
    p._karantinaya_al(KOL_A, TypeError("x"))
    p.karantina_sha_kontrol()                                          # aynı SHA: kaldırılmaz
    assert p.karantina[KOL_A]["durum"] == "aktif"
    p.kod_sha_fn = lambda: None                                        # SHA okunamadı: kaldırılmaz
    p.karantina_sha_kontrol()
    assert p.karantina[KOL_A]["durum"] == "aktif"
    p.kod_sha_fn = lambda: "s2"
    p.karantina_sha_kontrol()                                          # farklı SHA: bir kez 'deneme'
    assert p.karantina[KOL_A]["durum"] == "deneme"
    p.kod_sha_fn = lambda: "s3"
    p.karantina_sha_kontrol()                                          # 'deneme'dekine dokunmaz
    assert p.karantina[KOL_A]["durum"] == "deneme"


def test_karantina_ozeti_sirali_ve_deneme_sayilmaz():
    p, _, _ = _p()
    p._karantinaya_al(KOL_B, TypeError("x"))
    p._karantinaya_al(KOL_A, TypeError("x"))
    assert p.karantina_ozeti() == {"gorunur": sorted([KOL_A, KOL_B]), "gizli": 0}
    p.karantina_kaldir(KOL_A, "elle")
    assert p.karantina_ozeti() == {"gorunur": [KOL_B], "gizli": 0}     # 'deneme' karantinada sayılmaz
    p.gorunur = False
    assert p.karantina_ozeti() == {"gorunur": [], "gizli": 1}
