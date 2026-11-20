"""Strateji kod hatası karantinası (motor/canli/karantina.py, paper.py `_karar_guvenli`, paper_motor `_karantina_yonet`). Ağ YOK."""
import json
from datetime import datetime, timedelta, timezone
from decimal import Decimal

import numpy as np
import pandas as pd
import pytest

from motor.backtest.motor import SembolKurallari
from motor.canli import karantina as kq
from motor.canli import paper as pp
from motor.canli import pano
from motor.canli import telegram as tg
from motor.canli import telegram_komut as tk
from motor.canli.paper_kaynak import TekrarKaynagi
from testler.test_paper_motor import HepsiLong, duz, tanim
from testler.test_telegram_komut import kur as komut_kur, mesaj, son

KOL_A = "a|AUSDT|1d"
KOL_B = "b|BUSDT|1d"


class Bozuk(HepsiLong):
    """Her barda long ister; `hata` bayrağı açıksa (len(mumlar) >= patla) KASITLI TypeError fırlatır."""
    ad = "test__bozuk"
    hata = TypeError("kasitli programlama hatasi")
    cagri = 0

    def sinyaller(self, mumlar):
        type(self).cagri += 1
        if len(mumlar) >= getattr(self, "patla", 10 ** 9):
            raise self.hata
        return super().sinyaller(mumlar)


class Gec(HepsiLong):
    """`basla` barına kadar sinyal yok, sonra long ister (diğer stratejinin aynı turda giriş yapabildiğini göstermek için)."""
    ad = "test__gec"

    def sinyaller(self, mumlar):
        sig = super().sinyaller(mumlar)
        if len(mumlar) < self.basla:
            sig["yon"], sig["stop"] = 0, np.nan
        return sig


def _tanimlar(patla, basla, hata=None):
    a = tanim(KOL_A, "AUSDT", grup="g1", pay="0.5", stop_yuzde=1.0)
    a.nesne = Bozuk(stop_yuzde=1.0)
    a.nesne.patla = patla
    if hata is not None:
        a.nesne.hata = hata
    b = tanim(KOL_B, "BUSDT", grup="g2", pay="0.5", stop_yuzde=1.0)
    b.nesne = Gec(stop_yuzde=1.0)
    b.nesne.basla = basla
    return [a, b]


def _veri(cokus_bar=None):
    """A: düz 100; `cokus_bar`ta 100 -> 90 çöküş (stop 99'u deler). B: düz 100."""
    a, b = duz(30, 100.0), duz(30, 100.0)
    if cokus_bar is not None:
        a.iloc[cokus_bar:, a.columns.get_indexer(["acilis", "yuksek", "dusuk", "kapanis"])] = 90.0
    return {("AUSDT", "1d"): a, ("BUSDT", "1d"): b}


KUR = {"AUSDT": SembolKurallari(0.01, 0.001, 0.001, 5.0), "BUSDT": SembolKurallari(0.01, 0.001, 0.001, 5.0)}


def _paper(tans, mum, **kw):
    p = pp.Paper(tans, TekrarKaynagi(mum, {}), KUR, **kw)
    p.kod_sha_fn = lambda: "sha1"
    return p


def _t(mum, i):
    return mum[("AUSDT", "1d")].index[i] + pd.Timedelta(days=1)       # i. barın kapanışından sonra


def _kolu(p, kol):
    m = p.motor
    return [x for x in m.islemler if x["kol"] == kol], [q for q in m.acik.values() if q.kol.kimlik == kol]


# ---------------------------------------------------------------------------- 5. ana senaryo: karantinada stop çalışır, diğer strateji girer
def test_karantinadaki_stratejinin_stopu_calisir_diger_strateji_ayni_turda_girer():
    mum = _veri(cokus_bar=12)
    p = _paper(_tanimlar(patla=8, basla=8), mum)
    olaylar = []
    p.bildirim = lambda tur, m: olaylar.append((tur, m))
    p.baslat(_t(mum, 3))
    p.adim(_t(mum, 6))                                     # A girdi, hata henüz yok
    ia, aa = _kolu(p, KOL_A)
    assert aa and not ia and not p.karantina
    Bozuk.cagri = 0
    p.adim(_t(mum, 20))                                    # TEK adim: bar 8'de A patlar, B girer, bar 12'de A'nın fiyatı stopu deler
    assert p.karantina[KOL_A]["durum"] == "aktif" and p.karantina[KOL_A]["sha"] == "sha1"
    assert "TypeError" in p.karantina[KOL_A]["hata"]
    # A: tek işlem, nedeni stop (açılış gap ise stop_gap); yeni giriş YOK (stop sonrası sinyal hâlâ long ama karantina engeller)
    ia, aa = _kolu(p, KOL_A)
    assert len(ia) == 1 and ia[0]["cikis_nedeni"] in ("stop", "stop_gap") and not aa
    # strateji kodu karantinadan sonra çağrılmadı (patlayan çağrı + öncekiler; 8. bardan sonra ek çağrı yok)
    assert Bozuk.cagri <= 3
    # B aynı turda giriş yaptı
    ib, ab = _kolu(p, KOL_B)
    assert ab or ib
    # bildirim: tam bir CRIT olayı
    assert [t for t, _ in olaylar] == ["karantina"]
    assert olaylar[0][1] == KOL_A + " stratejisi hata verdi, yeni işlem açmıyor; açık pozisyonlar stop/hedefle sürüyor"
    # alınmayan sinyal / red: yok sayılamaz ama giriş izni reddi kayda yazılabilir; motorun kümesi eşit
    assert p.motor.karantina == {KOL_A}


def test_karantinada_kill_switch_pozisyonu_kapatir():
    mum = _veri()
    p = _paper(_tanimlar(patla=8, basla=10 ** 9), mum)
    p.baslat(_t(mum, 3))
    p.adim(_t(mum, 6))
    assert _kolu(p, KOL_A)[1]
    p.adim(_t(mum, 9))                                      # bar 8'de patladı
    assert p.motor.karantina == {KOL_A} and _kolu(p, KOL_A)[1]
    p.motor.nakit -= Decimal("2500")                        # zirveden > %20 düşüş: kill
    p.adim(_t(mum, 11))
    assert p.motor.kill and not _kolu(p, KOL_A)[1]
    assert any(x["cikis_nedeni"] == "kill_switch" for x in _kolu(p, KOL_A)[0])


def test_gecici_hata_karantinaya_girmez_eski_yolda_yukselir():
    # ValueError artık strateji hatası (karantina; kullanıcı kararı 2026-11-20, testler/test_denetim_motor.py D2); ValueError alt sınıfı
    # JSON ayrıştırma hatası ağ/veri kaynaklı geçici sayılır.
    for hata in (json.JSONDecodeError("veri", "", 0), OSError("ag"), RuntimeError("x"), pp.pv.BinanceHata("503") if hasattr(pp, "pv") else OSError("ag")):
        mum = _veri()
        p = _paper(_tanimlar(patla=8, basla=10 ** 9, hata=hata), mum)
        p.baslat(_t(mum, 3))
        with pytest.raises(type(hata)):
            p.adim(_t(mum, 12))
        assert not p.karantina and not p.motor.karantina


def test_baslangicta_kod_hatasi_da_karantinaya_alir():
    mum = _veri()
    p = _paper(_tanimlar(patla=1, basla=10 ** 9), mum)       # ilk karar (baslat) zaten patlar
    p.baslat(_t(mum, 3))
    assert p.karantina[KOL_A]["durum"] == "aktif"
    p.adim(_t(mum, 12))                                      # B sorunsuz, A giriş yapmaz
    assert not _kolu(p, KOL_A)[0] and not _kolu(p, KOL_A)[1]


# ---------------------------------------------------------------------------- 2. kalıcılık + SHA ile yeniden deneme + düzeldi
def test_karantina_kalici_sha_ayni_kalir_sha_degisince_bir_kez_denenir(tmp_path):
    mum = _veri()
    yol = tmp_path / "s.json"
    p = _paper(_tanimlar(patla=8, basla=10 ** 9), mum, durum_yolu=yol)
    p.baslat(_t(mum, 3))
    p.adim(_t(mum, 11))
    p.kaydet()
    assert json.loads(yol.read_text(encoding="utf-8"))["karantina"][KOL_A]["sha"] == "sha1"
    # yeniden başlatma, aynı SHA: karantina sürer, strateji kodu çağrılmaz
    q = _paper(_tanimlar(patla=8, basla=10 ** 9), mum, durum_yolu=yol)
    assert q.yukle() and q.motor.karantina == {KOL_A}
    Bozuk.cagri = 0
    q.adim(_t(mum, 14))
    assert Bozuk.cagri == 0 and q.karantina[KOL_A]["durum"] == "aktif"
    # yeni SHA, kod DÜZELDİ: bir kez denenir, ilk başarılı karardan sonra karantina biter + INFO "düzeldi"
    olaylar = []
    r = _paper(_tanimlar(patla=10 ** 9, basla=10 ** 9), mum, durum_yolu=yol)
    r.kod_sha_fn = lambda: "sha2"
    r.bildirim = lambda tur, m: olaylar.append((tur, m))
    assert r.yukle()
    assert r.karantina[KOL_A]["durum"] == "deneme" and r.motor.karantina == set()
    r.adim(_t(mum, 17))
    assert KOL_A not in r.karantina and r.motor.karantina == set()
    assert olaylar == [("karantina_cikis", f"{KOL_A} düzeldi, karantinadan çıktı")]


def test_sha_degisti_ama_kod_hala_bozuksa_yeniden_karantina_ve_bildirim_bastirilir(tmp_path):
    mum = _veri()
    yol = tmp_path / "s.json"
    p = _paper(_tanimlar(patla=8, basla=10 ** 9), mum, durum_yolu=yol)
    p.baslat(_t(mum, 3))
    p.adim(_t(mum, 11))
    p.kaydet()
    olaylar = []
    r = _paper(_tanimlar(patla=8, basla=10 ** 9), mum, durum_yolu=yol)
    r.kod_sha_fn = lambda: "sha2"
    r.bildirim = lambda tur, m: olaylar.append(tur)
    assert r.yukle() and r.karantina[KOL_A]["durum"] == "deneme"
    r.adim(_t(mum, 14))
    assert r.karantina[KOL_A]["durum"] == "aktif" and r.karantina[KOL_A]["sha"] == "sha2"
    assert olaylar == []                                    # 6 saat içinde aynı strateji: CRIT tekrar basılmaz


def test_geri_yukle_karantinayi_korur(tmp_path):
    mum = _veri()
    yol = tmp_path / "s.json"
    p = _paper(_tanimlar(patla=8, basla=10 ** 9), mum, durum_yolu=yol)
    p.baslat(_t(mum, 3))
    p.kaydet()                                              # kayıtta karantina yok
    p.adim(_t(mum, 11))
    assert p.karantina
    a = p.karantina_anlik()
    p.yukle(ayar_guncelle=True, olay_yaz=False)             # TurKoruyucu geri yüklemesi (paper.canli_calistir.geri_yukle)
    assert not p.karantina
    p.karantina_geri(a)
    assert KOL_A in p.karantina and p.motor.karantina == {KOL_A}


# ---------------------------------------------------------------------------- 3. bildirim kuralları
def test_bildirim_6_saatte_bir_ve_ilk_mesaj_aninda():
    mum = _veri()
    p = _paper(_tanimlar(patla=10 ** 9, basla=10 ** 9), mum)
    saat = [1_000_000.0]
    p.saat = lambda: saat[0]
    gonder = []
    p.bildirim = lambda tur, m: gonder.append((tur, m))
    e = TypeError("x")
    p._karantinaya_al(KOL_A, e)
    assert len(gonder) == 1                                  # ilk mesaj anında
    p.karantina_kaldir(KOL_A, "elle")
    saat[0] += 3600
    p._karantinaya_al(KOL_A, e)                              # 1 saat sonra tekrar patladı: bastırılır (CRIT bile olsa)
    assert len(gonder) == 1
    saat[0] += 6 * 3600
    p.karantina_kaldir(KOL_A, "elle")
    p._karantinaya_al(KOL_A, e)
    assert len(gonder) == 2
    p._karantinaya_al("b|BUSDT|1d", e)                       # başka strateji: kendi sayacı
    assert len(gonder) == 3


def test_bildirimci_bicimi_crit_ve_info():
    giden = []
    b = tg.Bildirimci(lambda m: giden.append(m) or True, lambda: 1000.0)
    b.olay("karantina", f"{KOL_A} stratejisi hata verdi, yeni işlem açmıyor; açık pozisyonlar stop/hedefle sürüyor")
    b.olay("karantina_cikis", f"{KOL_A} düzeldi, karantinadan çıktı")
    assert giden[0].startswith("[1L3A] ⚠️ ") and "stratejisi hata verdi, yeni işlem açmıyor; açık pozisyonlar stop/hedefle sürüyor" in giden[0]
    assert giden[1].startswith("[1L3A] ") and "düzeldi, karantinadan çıktı" in giden[1]


def test_gizli_hesap_adi_hicbir_yerde_gecmez():
    mum = _veri()
    p = _paper(_tanimlar(patla=10 ** 9, basla=10 ** 9), mum)
    p.gorunur = False
    gonder = []
    p.bildirim = lambda tur, m: gonder.append(m)
    p._karantinaya_al(KOL_A, TypeError("x"))
    assert gonder and all("AUSDT" not in m and "a|" not in m for m in gonder) and gonder[0].startswith("Diğer hesap stratejisi hata verdi")
    assert p.karantina_ozeti() == {"gorunur": [], "gizli": 1}
    p._karantina_duzeldi(KOL_A)
    assert "AUSDT" not in gonder[1] and "Diğer hesaplar (1)" in gonder[1]


# ---------------------------------------------------------------------------- elle kaldırma (istek dosyası)
def test_karantina_kaldir_istek_dosyasi_bir_kez_uygulanir(tmp_path):
    mum = _veri()
    p = _paper(_tanimlar(patla=10 ** 9, basla=10 ** 9), mum)
    p._karantinaya_al(KOL_A, TypeError("x"))
    p._karantinaya_al(KOL_B, TypeError("y"))
    env = {"L3A_DURDUR_DOSYA": str(tmp_path / "DURDUR")}
    assert pp.karantina_kaldir_uygula(p, T0, tmp_path, env) is None           # istek yok
    (tmp_path / "KARANTINA_KALDIR").write_text(json.dumps({"zaman": "2026-11-19T12:00:00Z", "strateji": KOL_A.upper()}), encoding="utf-8")
    assert pp.karantina_kaldir_uygula(p, T0, tmp_path, env) == 1
    assert p.karantina[KOL_A]["durum"] == "deneme" and p.karantina[KOL_B]["durum"] == "aktif"
    p._karantinaya_al(KOL_A, TypeError("x"))
    assert pp.karantina_kaldir_uygula(p, T0, tmp_path, env) is None           # aynı istek ikinci kez işlenmez
    assert p.karantina[KOL_A]["durum"] == "aktif"


T0 = pd.Timestamp("2026-11-19T12:00:00Z")


# ---------------------------------------------------------------------------- 3. /durum, pano, saglik
def test_karantina_ozeti_gorunur_ve_satir():
    mum = _veri()
    p = _paper(_tanimlar(patla=10 ** 9, basla=10 ** 9), mum)
    p._karantinaya_al(KOL_A, TypeError("x"))
    oz = p.karantina_ozeti()
    assert oz == {"gorunur": [KOL_A], "gizli": 0}
    assert kq.satir({"gorunur": [KOL_A], "gizli": 4}).endswith(f"{KOL_A}, Diğer hesaplar (4)")
    assert kq.satir({"gorunur": [], "gizli": 0}) is None


def _durum_dosyasi(tmp_path, karantina):
    d = tmp_path / "durum"
    d.mkdir(parents=True, exist_ok=True)
    (d / "saglik.json").write_text(json.dumps({"karantina": karantina}), encoding="utf-8")


def test_durum_komutu_karantina_satiri_gizli_adsiz(tmp_path):
    s, c, _ = komut_kur(tmp_path)
    _durum_dosyasi(tmp_path, {"gorunur": [KOL_A], "gizli": 2})
    mesaj(s, "/durum")
    metin = son(c)
    assert "Karantinada" in metin and KOL_A in metin and "Diğer hesaplar (2)" in metin
    s2, c2, _ = komut_kur(tmp_path / "bos")
    mesaj(s2, "/durum")
    assert "Karantinada" not in son(c2)


def test_komut_karantina_kaldir_iki_adimli(tmp_path):
    s, c, saat = komut_kur(tmp_path)
    mesaj(s, "/karantina_kaldir " + KOL_A)
    assert "Karantinada strateji yok" in son(c)
    _durum_dosyasi(tmp_path, {"gorunur": [KOL_A], "gizli": 1})
    mesaj(s, "/karantina_kaldir bilinmeyen")
    assert "Kullanım" in son(c) and not s.karantina_dosya.exists()
    mesaj(s, "/karantina_kaldir " + KOL_A)
    assert "Kod: 1234" in son(c) and not s.karantina_dosya.exists()          # kodsuz uygulanmaz
    mesaj(s, "9999")
    assert "uygulanmadı" in son(c) and not s.karantina_dosya.exists()
    mesaj(s, "/karantina_kaldir " + KOL_A)
    saat.t += timedelta(seconds=10)
    mesaj(s, "1234")
    ist = json.loads(s.karantina_dosya.read_text(encoding="utf-8"))
    assert ist["strateji"] == KOL_A and s.karantina_dosya.name == "KARANTINA_KALDIR" and "isteği yazıldı" in son(c)
    s.karantina_dosya.unlink()
    mesaj(s, "/karantina_kaldir gizli")                                       # gizli hesaplar adsız hedeflenir
    mesaj(s, "1234")
    assert json.loads(s.karantina_dosya.read_text(encoding="utf-8"))["strateji"] == "gizli"
    assert "AUSDT" not in son(c)


def test_pano_uyarisi_karantina_tek_satir_gizli_adsiz():
    sg = {"veri": [], "durum": "ok", "uyarilar": [], "karantina": {"gorunur": [KOL_A], "gizli": 3}}
    u = pano.uyarilar({"ozet": None, "saglik": sg, "stratejiler": None}, [], datetime(2026, 11, 19, tzinfo=timezone.utc))
    k = [m for s, m in u if "Karantinada" in m]
    assert len(k) == 1 and "AUSDT" not in k[0] and "Diğer hesaplar (3)" in k[0]
    sg["karantina"] = {"gorunur": [], "gizli": 0}
    assert not [m for s, m in pano.uyarilar({"ozet": None, "saglik": sg, "stratejiler": None}, [], datetime(2026, 11, 19, tzinfo=timezone.utc)) if "Karantinada" in m]


def test_v2_gizli_hesap_karantinasi_adsiz_bildirilir_ve_saglikta_sayilir(tmp_path):
    from motor.canli import paper_v2 as v2
    from testler.test_paper_v2_odak import _durum_kur
    p, simdi = _durum_kur(tmp_path)
    giden = []
    p.bildirim = lambda tur, m: giden.append((tur, m))
    p.hesaplar["gizli_zz"]._karantinaya_al("gizli_zz", TypeError("x"))
    p.hesaplar["gorunen_a"]._karantinaya_al("gorunen_a", TypeError("y"))
    assert [t for t, _ in giden] == ["karantina", "karantina"]
    assert "gizli_zz" not in giden[0][1] and giden[0][1].startswith("Diğer hesap stratejisi hata verdi")
    assert giden[1][1].startswith("gorunen_a stratejisi hata verdi")
    assert p.karantina_ozeti() == {"gorunur": ["gorunen_a"], "gizli": 1}
    assert "1 hesapta kod hatası karantinası" in v2.gizli_ozeti(p)["sorun"]
    assert any(e["mesaj"].startswith("[gizli_zz] ") for e in p.olaylar)            # günlükte kimlikle (pano süzer)
