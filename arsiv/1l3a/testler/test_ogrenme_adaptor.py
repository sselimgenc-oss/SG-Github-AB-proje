"""ortak_ogrenme adaptörü: kurulum adı, Aday çevirisi, filtre/ders ile giriş atlatma, kanca kapalı = birebir aynı, fail-open, limitlere dokunmaz."""
import json
from datetime import datetime, timezone

import pandas as pd
import pytest

from motor.canli import ogrenme_adaptor as oa
from motor.canli import paper as pp
from motor.canli.kayit_etiketleri import DOSYA_ADI
from motor.canli.paper_kaynak import TekrarKaynagi
from motor.ortak_ogrenme import kayit as ok
from testler.test_kayit_etiketleri import _hazir, kayit, satirlar
from testler.test_paper_motor import tanim

SK = "dis__ewo-ema-ofset"
A = "a|XUSDT|1d"          # test paper stratejisinin kimliği
NOW = pd.Timestamp("2026-11-19 12:00", tz="UTC")


def _og(tmp_path, **kw):
    kw.setdefault("saat", lambda: NOW)
    kw.setdefault("gonder", lambda m: True)
    return oa.Ogrenme(tmp_path, **kw)


def _paper(tmp_path, og=None, kay=True):
    t = tanim("a|XUSDT|1d", "XUSDT", stop_yuzde=3.0)
    mum, kur = _hazir(t)
    p = pp.Paper([t], TekrarKaynagi(mum, {}), kur)
    if kay:
        p.kayit_ac(kayit(tmp_path))
    if og is not None:
        og.bagla(p)
    p.baslat(mum[("XUSDT", "1d")].index[3])
    return p, mum


def _kos(p, mum):
    p.adim(mum[("XUSDT", "1d")].index[8])
    return p


def _durum(p):
    m = p.motor
    return ([(k, str(x.miktar), str(x.stop), str(x.giris)) for k, x in sorted(m.acik.items())], str(m.ozsermaye()), len(m.islemler))


def _aday(i, r, **oz):
    return ok.Aday(id=str(i), proje="1L3A", kurulum="a", enstruman="XUSDT", varlik_sinifi="kripto", yon="long",
                   ts=datetime(2026, 1, 1, tzinfo=timezone.utc) + pd.Timedelta(days=i), alindi=True, r=r, ozellikler=oz)


# ---------------------------------------------------------------------------- kurulum adı
def test_kurulum_adi_donusumu_ve_cakisma(tmp_path):
    assert oa.temiz_ad(SK) == "dis_ewo_ema_ofset"
    e = oa.Esleme(tmp_path / "e.json")
    a, b = e.ileri("x-y"), e.ileri("x_y")
    assert a == "x_y" and b != a and b.startswith("x_y_")
    assert e.ters(a) == "x-y" and e.ters(b) == "x_y"
    e2 = oa.Esleme(tmp_path / "e.json")                          # yeniden başlatmada aynı eşleme
    assert e2.ileri("x_y") == b and e2.ileri("x-y") == a
    assert all("@" not in v and v.replace("_", "").isalnum() for v in e.ileri_t.values())


# ---------------------------------------------------------------------------- Aday çevirisi
def test_islem_ve_alinmayan_adayi(tmp_path):
    e = oa.Esleme()
    satir = {"kimlik": SK, "sembol": "BTCUSDT", "yon": "short", "giris_zamani": "2026-11-01T00:00:00Z", "cikis_zamani": "2026-11-02T00:00:00Z",
             "giris_fiyati": "100.5", "r": 1.5, "cikis_nedeni": "hedef", "mfe_r": 2.0, "mae_r": -0.2, "rejim_ml_4h": "range"}
    a = oa.islem_adayi(satir, {"atr_ratio": 1.4, "metin": "x"}, e)
    assert (a.proje, a.kurulum, a.varlik_sinifi, a.yon, a.alindi, a.r, a.rejim) == ("1L3A", "dis_ewo_ema_ofset", "kripto", "short", True, 1.5, "range")
    assert a.ozellikler == {"atr_ratio": 1.4} and a.ts.tzinfo is not None
    assert oa.islem_adayi({**satir, "r": None, "sembol": "DK_NVDA"}, {"seans_kapali": 1.0}, e).seans == "closed"
    assert oa.islem_adayi({**satir, "r": None}, None, e).r is None
    n = oa.alinmayan_adayi({"zaman": "2026-11-03T00:00:00Z", "hesap": "h", "strateji": SK, "kol": "k", "sembol": "ETHUSDT", "yon": "long", "fiyat": "100",
                            "stop": "97", "hedef": "106", "neden": "ml_filtre", "fonlama_orani": 0.0001, "korku_acgozluluk": 40, "takvim_bayragi": None}, e)
    assert not n.alindi and n.r is None and n.kurulum == "dis_ewo_ema_ofset"
    assert n.ozellikler["rr"] == pytest.approx(2.0) and n.ozellikler["takvim_var"] == 0.0 and n.ozellikler["korku_acgozluluk"] == 40.0
    ok.aday_from_dict(ok.aday_to_dict(a))                          # paket doğrulamasından geçer


def test_atr_ozellikleri_lookahead_yok():
    import numpy as np
    idx = pd.date_range("2026-01-01", periods=80, freq="D", tz="UTC")
    c = np.linspace(100, 110, 80)
    df = pd.DataFrame({"acilis": c, "yuksek": c + 1, "dusuk": c - 1, "kapanis": c}, index=idx)
    a14, r = oa.atr_ozellikleri(df)
    assert a14 == pytest.approx(2.0, rel=0.2) and r == pytest.approx(1.0, rel=0.2)
    assert oa.atr_ozellikleri(df.iloc[:30]) == (None, None)


# ---------------------------------------------------------------------------- filtre
def test_veri_yokken_filtre_yok_ve_tek_sinif(tmp_path):
    og = _og(tmp_path)
    assert og.giris_suzgeci(SK, "XUSDT", "long", {"stop_yuzde": 0.9}) == (True, "")
    og.kapananlar = [_aday(i, 1.0, stop_yuzde=0.1) for i in range(40)]     # hepsi kazanç: tek sınıf
    for a in og.kapananlar:
        object.__setattr__(a, "kurulum", "a")
    og._egit_kontrol(NOW)
    assert not (tmp_path / oa.MODEL_DIZINI).exists() and og.giris_suzgeci(A, "XUSDT", "long", {"stop_yuzde": 0.9}) == (True, "")


def _egitilmis(tmp_path):
    og = _og(tmp_path)
    ad = og.esleme.ileri(A)
    og.kapananlar = [ok.Aday(id=str(i), proje="1L3A", kurulum=ad, enstruman="XUSDT", varlik_sinifi="kripto", yon="long",
                             ts=datetime(2026, 1, 1, tzinfo=timezone.utc) + pd.Timedelta(days=i), alindi=True, r=1.0 if i % 2 else -1.0,
                             ozellikler={"stop_yuzde": 0.001 if i % 2 else 0.03},
                             cikis={"cikis_zamani": (pd.Timestamp("2026-01-02", tz="UTC") + pd.Timedelta(days=i)).isoformat()}) for i in range(60)]
    og._egit_kontrol(NOW)
    return og, ad


def test_egitilmis_model_dusuk_puani_atlatir_ve_kayda_yazar(tmp_path):
    pytest.importorskip("numpy")
    og, ad = _egitilmis(tmp_path)
    assert (tmp_path / oa.MODEL_DIZINI / f"{ad}.json").exists()
    assert og.giris_suzgeci(A, "XUSDT", "long", {"stop_yuzde": 0.001}) == (True, "")
    assert og.giris_suzgeci(A, "XUSDT", "long", {"stop_yuzde": 0.03}) == (False, "ml_filtre")
    # yeniden başlatma: model diskten yüklenir
    og2 = _og(tmp_path)
    assert og2.giris_suzgeci(A, "XUSDT", "long", {"stop_yuzde": 0.03}) == (False, "ml_filtre")
    # paper girişi: stop %3 -> düşük puan -> giriş yok, alınmayan sinyal "ml_filtre"
    p, mum = _paper(tmp_path / "p", og2)
    og2.dizin = tmp_path
    _kos(p, mum)
    assert not p.motor.acik
    assert any(s["neden"] == "ml_filtre" for s in satirlar(tmp_path / "p"))


def test_suresi_dolmus_ya_da_bozuk_model_filtre_yok(tmp_path, caplog):
    pytest.importorskip("numpy")
    og, ad = _egitilmis(tmp_path)
    gec = _og(tmp_path, saat=lambda: NOW + pd.Timedelta(days=30))
    assert gec.giris_suzgeci(A, "XUSDT", "long", {"stop_yuzde": 0.03}) == (True, "")
    assert "filtre YOK" in caplog.text
    yol = tmp_path / oa.MODEL_DIZINI / f"{ad}.json"
    yol.write_text(yol.read_text().replace('"coef"', '"coefX"'))
    assert _og(tmp_path).giris_suzgeci(A, "XUSDT", "long", {"stop_yuzde": 0.03}) == (True, "")


def test_egitim_yalniz_karar_oncesi_kapanan_islemler(tmp_path):
    og, ad = _egitilmis(tmp_path)
    assert len(og.egitim_adaylari(ad, pd.Timestamp("2026-01-12", tz="UTC"))) == 11
    assert len(og.egitim_adaylari(ad)) == 60


# ---------------------------------------------------------------------------- ders
def _ders(tmp_path, durum):
    (tmp_path).mkdir(parents=True, exist_ok=True)
    (tmp_path / oa.DERS_DOSYASI).write_text(json.dumps({"yuksek_vol:" + oa.temiz_ad(A): {"status": durum, "born": "2026-01-01", "effect": 1.0, "n": 5}}))


def test_aktif_ders_girisi_atlatir_aday_ders_atlatmaz(tmp_path):
    _ders(tmp_path, "alive")
    og = _og(tmp_path)
    assert og.giris_suzgeci(A, "XUSDT", "long", {"atr_ratio": 2.0}) == (False, "ders:yuksek_vol")
    assert og.giris_suzgeci(A, "XUSDT", "long", {"atr_ratio": 1.0}) == (True, "")
    assert og.giris_suzgeci("b|XUSDT|1d", "XUSDT", "long", {"atr_ratio": 2.0}) == (True, "")
    _ders(tmp_path, "candidate")
    assert og.giris_suzgeci(A, "XUSDT", "long", {"atr_ratio": 2.0}) == (False, "ders:yuksek_vol")      # aday da engeller (gölge yok)
    _ders(tmp_path, "retired")
    assert og.giris_suzgeci(A, "XUSDT", "long", {"atr_ratio": 2.0}) == (True, "")


def test_ders_paper_girisini_atlatir_kayda_neden_yazar(tmp_path):
    _ders(tmp_path, "alive")
    og = _og(tmp_path)
    p, mum = _paper(tmp_path, og)
    p.motor.ozellik_kancasi = lambda t, e: {"atr_ratio": 2.0}
    _kos(p, mum)
    assert not p.motor.acik
    assert "ders:yuksek_vol" in [s["neden"] for s in satirlar(tmp_path)]


def test_gunluk_ders_adimi_en_cok_gunde_bir(tmp_path):
    og = _og(tmp_path)
    assert not og.gunluk(pd.Timestamp("2026-11-19 21:10", tz="UTC"))       # TSİ 00:10: erken
    assert og.gunluk(pd.Timestamp("2026-11-19 21:40", tz="UTC"))           # TSİ 00:40
    assert not og.gunluk(pd.Timestamp("2026-11-19 23:00", tz="UTC"))       # aynı TSİ günü
    assert og.gunluk(pd.Timestamp("2026-11-20 21:40", tz="UTC"))
    assert (tmp_path / oa.KARNE_DOSYASI).exists() and (tmp_path / oa.DERS_DOSYASI).exists()


# ---------------------------------------------------------------------------- kanca: kapalı = aynı, hata = serbest, limitlere dokunmaz
def test_kanca_kapali_ve_acik_izinli_birebir_ayni(tmp_path):
    p0, m0 = _paper(tmp_path / "0", None)
    p1, m1 = _paper(tmp_path / "1", _og(tmp_path / "1"))
    p2, m2 = _paper(tmp_path / "2", None)
    p2.motor.giris_suzgeci = lambda *a: (True, "ok")
    d0, d1, d2 = (_durum(_kos(p, m)) for p, m in ((p0, m0), (p1, m1), (p2, m2)))
    assert d0[0] and d0 == d1 == d2                                 # aynı miktar/stop/özsermaye: kanca boyutu/limiti değiştirmez


def test_kanca_hata_giris_serbest(tmp_path, caplog):
    p0, m0 = _paper(tmp_path / "0", None)
    og = _og(tmp_path / "1")
    p1, m1 = _paper(tmp_path / "1", og)
    og.giris_suzgeci = lambda *a: 1 / 0
    p1.motor.giris_suzgeci = og.giris_suzgeci
    assert _durum(_kos(p1, m1)) == _durum(_kos(p0, m0))
    assert "giriş süzgeci hatası" in caplog.text
    p1.motor.giris_suzgeci = lambda *a: ("tuple", "değil", 3)       # bozuk dönüş de güvenli
    p3, m3 = _paper(tmp_path / "3", None)
    p3.motor.giris_suzgeci = lambda *a: (True,)
    assert _durum(_kos(p3, m3)) == _durum(_kos(p0, m0))


def test_ozellik_kancasi_hatasi_giris_serbest(tmp_path):
    p0, m0 = _paper(tmp_path / "0", None)
    p1, m1 = _paper(tmp_path / "1", None)
    p1.motor.giris_suzgeci = lambda *a: (True, "")
    p1.motor.ozellik_kancasi = lambda *a: 1 / 0
    assert _durum(_kos(p1, m1)) == _durum(_kos(p0, m0))


def test_bagla_kapali_env(tmp_path):
    p, m = _paper(tmp_path, None)
    assert oa.bagla(p, tmp_path, env={"L3A_OGRENME_KAPALI": "1"}) is None
    assert p.motor.giris_suzgeci is None and "adim" not in vars(p)
    assert oa.bagla(p, tmp_path, env={}) is not None and p.motor.giris_suzgeci is not None
    assert oa.Ogrenme(tmp_path, kapali_=True).giris_suzgeci(A, "X", "long", {"atr_ratio": 9}) == (True, "")


def test_kapanan_islem_adaya_cevrilir_ve_ozellik_saklanir(tmp_path):
    og = _og(tmp_path)
    p, mum = _paper(tmp_path, og)
    _kos(p, mum)
    assert p.motor.acik
    p.adim(mum[("XUSDT", "1d")].index[11])
    # zaman çıkışı 1000 mum: pozisyonu elle kapat
    m = p.motor
    for pos in list(m.acik.values()):
        m._azalt(pos, pos.giris, pos.miktar, mum[("XUSDT", "1d")].index[11], m._tk(pos.sembol), "hedef", False)
    og.tur(NOW)
    assert len(og.kapananlar) == 1 and "stop_yuzde" in og.kapananlar[0].ozellikler
    assert ok.oku_jsonl(tmp_path / oa.ADAY_DOSYASI)[0].id == og.kapananlar[0].id


# ---------------------------------------------------------------------------- drift
def test_drift_uyarisi_telegrama_gitmez(tmp_path):
    gonderilen = []
    og = _og(tmp_path, gonder=lambda m: gonderilen.append(m) or True)
    from motor.canli import telegram as tg
    og.bildirimci = tg.Bildirimci(gonder_fn=og.gonder, ortak=tg.OrtakDurum(), servis="paper")        # Bildirimci: 6 saat kuralı
    og.kapananlar = [ok.Aday(id=f"{k}{i}", proje="1L3A", kurulum=k, enstruman="X", varlik_sinifi="kripto", yon="long",
                             ts=datetime(2026, 1, 1, tzinfo=timezone.utc) + pd.Timedelta(days=i), alindi=True, r=-1.0)
                     for k in ("s_bir", "s_iki") for i in range(25)]
    og.esleme.ileri("s-bir"), og.esleme.ileri("s-iki")
    og._drift_bildir(og.kapananlar)
    assert gonderilen == []                                           # drift eylemi Telegram'a gitmez (yalnız log)
    og._drift_bildir(og.kapananlar)
    assert gonderilen == [] and og.durum["drift_uyari"] == ["s_bir", "s_iki"]
