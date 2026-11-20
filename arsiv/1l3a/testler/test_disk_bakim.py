"""Disk bakımı: eşikler, 6 saat tekrar önleme, düzeldi mesajı, döndürme, 90 gün silme, durum.json'a dokunmama."""
import gzip
import json
import os
from datetime import datetime, timezone
from pathlib import Path

import pytest

from motor.canli import disk_bakim as db
from motor.canli import telegram as tg

T0 = datetime(2026, 11, 19, 12, 0, 0, tzinfo=timezone.utc)
S0 = T0.timestamp()
SAAT = 3600


class Toplayici:
    def __init__(self):
        self.mesajlar = []

    def __call__(self, metin):
        self.mesajlar.append(metin)
        return True


def _ortak(tmp_path):
    return tg.OrtakDurum(tmp_path / "ortak")


def _usage(dolu_yuzde):
    """Sahte shutil.disk_usage: used/(used+free) = dolu_yuzde."""
    def f(_yol):
        toplam = 1000
        used = int(toplam * dolu_yuzde / 100)
        return type("U", (), {"total": toplam, "used": used, "free": toplam - used})()
    return f


# ---------------------------------------------------------------- eşikler ve metin
def test_esik_altinda_mesaj_yok(tmp_path):
    t = Toplayici()
    alarm = db.degerlendir(79.9, False, _ortak(tmp_path), t, S0)
    assert alarm is False and t.mesajlar == []


def test_warn_esigi_ve_metni(tmp_path):
    t = Toplayici()
    alarm = db.degerlendir(80.4, False, _ortak(tmp_path), t, S0)
    assert alarm is True
    assert t.mesajlar == ["[1L3A] ⚠️ Disk 80% dolu"]


def test_crit_esigi_ve_metni(tmp_path):
    t = Toplayici()
    db.degerlendir(93.7, False, _ortak(tmp_path), t, S0)
    assert t.mesajlar == ["[1L3A] 🔴 Disk 93% dolu, kayıtlar duracak"]


def test_crit_warn_den_bagimsiz_gider(tmp_path):
    """WARN gönderildikten sonra CRIT'e çıkılırsa CRIT hemen gider (ayrı anahtar)."""
    t, o = Toplayici(), _ortak(tmp_path)
    db.degerlendir(85, False, o, t, S0)
    db.degerlendir(91, True, o, t, S0 + 60)
    assert t.mesajlar == ["[1L3A] ⚠️ Disk 85% dolu", "[1L3A] 🔴 Disk 91% dolu, kayıtlar duracak"]


# ---------------------------------------------------------------- 6 saat tekrar önleme
def test_ayni_uyari_6_saatte_bir(tmp_path):
    t, o = Toplayici(), _ortak(tmp_path)
    alarm = db.degerlendir(85, False, o, t, S0)
    alarm = db.degerlendir(85, alarm, o, t, S0 + 5 * SAAT)          # 5 saat: bastırılır
    assert len(t.mesajlar) == 1
    db.degerlendir(85, alarm, o, t, S0 + 6 * SAAT + 1)               # 6 saat geçti: yeniden gider
    assert len(t.mesajlar) == 2


def test_tekrar_kaydi_yeniden_baslatmada_da_korunur(tmp_path):
    t = Toplayici()
    db.degerlendir(85, False, _ortak(tmp_path), t, S0)
    db.degerlendir(85, False, _ortak(tmp_path), t, S0 + SAAT)      # yeni OrtakDurum nesnesi (aynı dosya)
    assert len(t.mesajlar) == 1


# ---------------------------------------------------------------- düzeldi
def test_duzeldi_mesaji_tek_sefer(tmp_path):
    t, o = Toplayici(), _ortak(tmp_path)
    alarm = db.degerlendir(85, False, o, t, S0)
    alarm = db.degerlendir(70, alarm, o, t, S0 + SAAT)              # eşik altına indi: düzeldi
    assert alarm is False
    assert t.mesajlar[-1] == "[1L3A] Disk düzeldi (70%)"
    alarm = db.degerlendir(70, alarm, o, t, S0 + 2 * SAAT)          # alarm kapalı: ikinci düzeldi yok
    assert len(t.mesajlar) == 2


# ---------------------------------------------------------------- ölçüm
def test_olc_df_formulu(tmp_path):
    v = db.olc([str(tmp_path)], disk_usage=_usage(42))
    assert v == {str(tmp_path): pytest.approx(42.0)}


def test_satir_bicimi(monkeypatch):
    monkeypatch.setattr(db, "olc", lambda *a, **k: {"/": 61.2, "/var/lib/1l3a-paper": 33.0})
    assert db.satir() == "disk: 61%"
    monkeypatch.setattr(db, "olc", lambda *a, **k: {})
    assert db.satir() == "disk: ölçülemedi"


# ---------------------------------------------------------------- döndürme
def _kayit(p: Path, boyut: int, ad_ornek: bytes = b"satir\n") -> Path:
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_bytes((ad_ornek * (boyut // len(ad_ornek) + 1))[:boyut])
    return p


def test_buyuk_jsonl_arsivlenir_ve_bosaltilir(tmp_path):
    kok = tmp_path / "1l3a"
    kaynak = _kayit(kok / "durum" / "islemler.jsonl", 3000)
    icerik = kaynak.read_bytes()
    sonuc = db.dondur(kok, T0, sinir=1000)
    assert sonuc["arsivlenen"] == ["islemler.jsonl"]
    assert kaynak.stat().st_size == 0                               # asıl dosya boşaltıldı (copytruncate)
    arsiv = list((kok / "arsiv").glob("islemler.jsonl.20261119-120000*.gz"))
    assert len(arsiv) == 1
    with gzip.open(arsiv[0], "rb") as f:
        assert f.read() == icerik                                   # arşiv tam içeriği taşır


def test_kucuk_dosya_dokunulmaz(tmp_path):
    kok = tmp_path / "1l3a"
    k = _kayit(kok / "kucuk.log", 500)
    sonuc = db.dondur(kok, T0, sinir=1000)
    assert sonuc["arsivlenen"] == [] and k.stat().st_size == 500


def test_durum_dosyasi_ve_jsonl_olmayanlar_asla_dondurulmaz(tmp_path):
    kok = tmp_path / "1l3a"
    durum_json = _kayit(kok / "durum" / "durum.json", 5000, b"{}")
    ozet = _kayit(kok / "durum" / "ozet.json", 5000, b"{}")
    veri = _kayit(kok / "veri" / "mumlar" / "x.parquet", 5000)
    db.dondur(kok, T0, sinir=1000)
    assert durum_json.stat().st_size == 5000
    assert ozet.stat().st_size == 5000
    assert veri.stat().st_size == 5000


def test_muhurlu_ve_on_kayit_dosyalarina_dokunulmaz(tmp_path):
    kok = tmp_path / "1l3a"
    dosyalar = [
        _kayit(kok / "ON_KAYIT_2026.jsonl", 3000),
        _kayit(kok / "kilit_acilis.jsonl", 3000),
        _kayit(kok / "butunluk_kayit.jsonl", 3000),
        _kayit(kok / "sonuclar" / "final" / "olay.jsonl", 3000),
    ]
    boyutlar = [d.stat().st_size for d in dosyalar]
    sonuc = db.dondur(kok, T0, sinir=1000)
    assert sonuc["arsivlenen"] == []
    assert [d.stat().st_size for d in dosyalar] == boyutlar


def test_90_gunden_eski_gz_silinir_yalniz_arsivde(tmp_path):
    kok = tmp_path / "1l3a"
    arsiv = kok / "arsiv"
    arsiv.mkdir(parents=True)
    eski = arsiv / "a.jsonl.20260101-000000.gz"
    yeni = arsiv / "b.jsonl.20261110-000000.gz"
    disi = kok / "dis.jsonl.gz"                                      # arşiv dizini dışında: silinmez
    for f in (eski, yeni, disi):
        f.write_bytes(b"x")
    eski_zaman = T0.timestamp() - 91 * 86400
    yeni_zaman = T0.timestamp() - 9 * 86400
    os.utime(eski, (eski_zaman, eski_zaman))
    os.utime(yeni, (yeni_zaman, yeni_zaman))
    os.utime(disi, (eski_zaman, eski_zaman))
    sonuc = db.dondur(kok, T0, sinir=10**9)
    assert sonuc["silinen"] == 1
    assert not eski.exists() and yeni.exists() and disi.exists()


def test_gunde_bir_kez_doondurme(tmp_path):
    kok = tmp_path / "1l3a"
    kok.mkdir()
    _kayit(kok / "x.jsonl", 60 * 1024 * 1024)
    o, t = _ortak(tmp_path), Toplayici()
    ilk = db.calistir(str(kok), simdi=S0, ortak=o, gonder=t, olcer=lambda: {})
    assert ilk["dondurme"] is not None
    _kayit(kok / "y.jsonl", 60 * 1024 * 1024)
    ikinci = db.calistir(str(kok), simdi=S0 + 3600, ortak=o, gonder=t, olcer=lambda: {})
    assert ikinci["dondurme"] is None                                 # 1 saat sonra tekrar döndürme yok
    assert (kok / "y.jsonl").stat().st_size == 60 * 1024 * 1024
    ucuncu = db.calistir(str(kok), simdi=S0 + 25 * SAAT, ortak=o, gonder=t, olcer=lambda: {})
    assert ucuncu["dondurme"] is not None                             # 25 saat sonra yeniden


# ---------------------------------------------------------------- giriş noktası
def test_calistir_olcum_uyari_ve_durum_dosyasi(tmp_path):
    kok = tmp_path / "1l3a"
    kok.mkdir()
    durum_json = _kayit(kok / "durum.json", 200, b"{}")
    onceki = durum_json.read_bytes()
    t = Toplayici()
    db.calistir(str(kok), simdi=S0, ortak=_ortak(tmp_path), gonder=t, olcer=lambda: {"/": 92.0})
    assert t.mesajlar == ["[1L3A] 🔴 Disk 92% dolu, kayıtlar duracak"]
    assert durum_json.read_bytes() == onceki                          # durum.json'a dokunulmaz
    durum = json.loads((kok / db.DURUM_DOSYASI).read_text(encoding="utf-8"))
    assert durum["alarm"] is True and durum["son_dondurme"] == S0


def test_calistir_hata_yutar(tmp_path):
    def patlar():
        raise PermissionError("izin yok")
    assert db.calistir(str(tmp_path), simdi=S0, ortak=_ortak(tmp_path), gonder=Toplayici(), olcer=patlar) is None


def test_komut_servisi_disk_5_dakikada_bir(tmp_path):
    from motor.canli import telegram_komut as tk
    cagri = []
    simdi = [S0]
    s = tk.KomutServisi(None, 1, tmp_path / "durum", now_fn=lambda: datetime.fromtimestamp(simdi[0], tz=timezone.utc),
                        disk_kok=tmp_path / "1l3a", disk_fn=lambda kok, simdi: cagri.append(simdi))
    s._disk_tick()
    s._disk_tick()                                  # aynı an: tekrar yok
    simdi[0] = S0 + 299
    s._disk_tick()
    simdi[0] = S0 + 300
    s._disk_tick()
    assert cagri == [S0, S0 + 300]


def test_komut_servisi_disk_hatasi_yutulur(tmp_path):
    from motor.canli import telegram_komut as tk

    def patlar(kok, simdi):
        raise OSError("disk yok")
    s = tk.KomutServisi(None, 1, tmp_path / "durum", now_fn=lambda: T0, disk_kok=tmp_path, disk_fn=patlar)
    s._disk_tick()                                  # istisna dışarı çıkmaz


def test_calistir_kok_yoksa_olcer_yine_calisir(tmp_path):
    t = Toplayici()
    sonuc = db.calistir(str(tmp_path / "yok"), simdi=S0, ortak=_ortak(tmp_path), gonder=t, olcer=lambda: {"/": 85.0})
    assert sonuc["olcum"] == {"/": 85.0} and sonuc["dondurme"] is None
    assert t.mesajlar == ["[1L3A] ⚠️ Disk 85% dolu"]
