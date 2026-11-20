"""Çıkış karşı-olgusu (motor/canli/cikis_karsi_olgu.py): yeniden oynatma motoru, ölçüt, otomatik uygulama, geri alma, "alınsaydı". Ağ YOK."""
import dataclasses
import json
from types import SimpleNamespace

import numpy as np
import pandas as pd
import pytest

from motor.backtest.motor import SembolKurallari
from motor.canli import cikis_karsi_olgu as ck
from motor.canli import gunluk_ozet as go
from motor.canli import paper as pp
from motor.canli import telegram as tg
from motor.canli import telegram_komut as tk
from motor.canli.paper_kaynak import TekrarKaynagi
from motor.ortak_ogrenme import kayit as ok
from testler.test_paper_motor import duz, tanim
from testler.test_telegram_komut import kur as komut_kur, mesaj, son

SAAT = pd.Timedelta(hours=1)
T0 = pd.Timestamp("2026-11-01 00:00", tz="UTC")


# ---------------------------------------------------------------------------- yeniden oynatma motoru (elle hesaplanan örnekler)
class SifirMal:
    """Maliyetsiz sahte maliyet kaynağı (örnekler elle hesaplanır)."""
    hedef_maker = False

    def __init__(self, tk_=0.0, ky=0.0, sk=0.0):
        self._tk, self._ky, self._sk = tk_, ky, sk

    def tk(self, s, t): return self._tk
    def mk(self, s, t): return self._tk
    def ky(self, s, t): return self._ky
    def sk(self, s, t): return self._sk
    def tick(self, s): return 0.01
    def step(self, s): return 0.001
    def min_qty(self, s): return 0.001


def mumlar(satirlar, atr=1.0, bas=T0):
    """satirlar: [(o, h, l, c)] 1 saatlik mumlar."""
    a = np.array(satirlar, dtype=float)
    return {"t": pd.date_range(bas, periods=len(a), freq="h", tz="UTC"), "o": a[:, 0], "h": a[:, 1], "l": a[:, 2], "c": a[:, 3],
            "atr": np.full(len(a), atr)}


def oyna(ad_veya_spec, m, hedef=None, dis=None, mal=None, giris_i=0, **kw):
    spec = ck.tam_spec(ck.ALTERNATIFLER[ad_veya_spec]) if isinstance(ad_veya_spec, str) else ad_veya_spec
    return ck.yeniden_oyna(spec, sembol="XUSDT", yon=1, giris=100.0, stop=95.0, hedef=hedef, qty=1.0, giris_zamani=m["t"][giris_i], mumlar=m,
                           mal=mal or SifirMal(), aralik=SAAT, dis=dis, **kw)


YOK = ck.tam_spec({})      # hiçbir yönetim yok: yalnız ilk stop


def test_stop_ve_hedef_ayni_mumda_stop_sayilir():
    m = mumlar([(100, 112, 94, 100)])
    o = oyna(YOK, m, hedef=110.0)
    assert o["neden"] == "stop" and o["r"] == pytest.approx(-1.0)


def test_basabas_atr_iz_zaman_elle_hesap():
    m = mumlar([(100, 102, 99, 101), (101, 106, 100, 105), (105, 106, 96, 97)] + [(97, 98, 96, 97)] * 9)
    # başabaş 1R: b1 kapanışında zirve 106 >= 105 -> stop 100; b2 düşüğü 96 <= 100 -> stop 100'den çıkar: 0 R
    o = oyna("basabas_1R", m)
    assert o["neden"] == "stop" and o["r"] == pytest.approx(0.0) and o["cikis_zamani"] == str(T0 + 3 * SAAT)
    # atr_iz_3 (ATR 1): b0 sonu stop 99, b1 sonu stop 103; b2 düşüğü 96 -> 103'ten çıkar: +0.6 R
    o = oyna("atr_iz_3", m)
    assert o["neden"] == "stop" and o["r"] == pytest.approx(0.6)
    # atr_iz_2: b0 sonu stop 100 (102-2); b1 düşüğü 100 <= 100 -> 100'den çıkar: 0 R
    o = oyna("atr_iz_2", m)
    assert o["r"] == pytest.approx(0.0) and o["cikis_zamani"] == str(T0 + 2 * SAAT)
    # zaman_stopu_10: 10. mum (b9) kapanışında karar, b10 AÇILIŞINDA (97) çıkış: -0.6 R
    o = oyna("zaman_stopu_10", m)
    assert o["neden"] == "zaman" and o["r"] == pytest.approx(-0.6)


def test_kismi_ve_brooks_elle_hesap():
    m = mumlar([(100, 111, 99, 110), (110, 112, 94, 95)])
    # kismi 2R yarım: seviye 110 b0'da vurulur, yarısı 110'dan (+5); kalan stop 95'ten (-2.5) -> 2.5/5 = +0.5 R
    o = oyna("kismi_2R_yarim", m)
    assert o["r"] == pytest.approx(0.5) and o["neden"] == "stop"
    # brooks: 110'da yarım (+5); b0 sonu başabaş+ATR3 izi: zirve 111 -> stop 108; b1'de 108'den kalan 0.5 (+4) -> 9/5 = 1.8 R
    o = oyna("brooks", m)
    assert o["r"] == pytest.approx(1.8)


def test_farley_agresif_iz_hedefle_dar_stop():
    m = mumlar([(100, 108, 99, 107), (108, 108, 100, 101)])
    o_f = oyna("farley", m, hedef=110.0)               # yol %80 >= 0.75: stop 108-1 = 107 -> +1.4 R
    o_3 = oyna("atr_iz_3", m, hedef=110.0)             # yalnız 108-3 = 105 -> +1.0 R
    assert o_f["r"] == pytest.approx(1.4) and o_3["r"] == pytest.approx(1.0)


def test_zirveden_geri_cekilme():
    m = mumlar([(100, 104, 99, 103.5), (103, 103.5, 101, 102), (102.5, 103, 102, 102.5)])
    o = oyna("zirveden_geri_cekilme", m)               # b1 sonu: zirve %4, kâr %2 -> fark 2 >= 1.5 -> b2 açılışında çık
    assert o["neden"] == "geri_cekilme" and o["r"] == pytest.approx(0.5)


def test_maliyet_giris_cikis_ucreti_ve_kayma():
    m = mumlar([(100, 101, 94, 96)])
    o = oyna(YOK, m, mal=SifirMal(tk_=0.001, ky=0.0, sk=0.0))
    # brüt -5; giriş ücreti 0.1; stop çıkış ücreti 95*0.001 = 0.095 -> -5.195 / 5
    assert o["r"] == pytest.approx(-5.195 / 5)
    o2 = oyna(YOK, m, mal=SifirMal(tk_=0.0, sk=0.01))   # stop kayması: 95*(1-0.01) = 94.05 -> -5.95
    assert o2["r"] == pytest.approx(-5.95 / 5)


def test_dis_cikis_gercek_anda_uygulanir():
    m = mumlar([(100, 102, 99, 101), (101, 103, 100, 102), (102, 103, 101, 102)])
    dis = {"neden": "sinyal", "zaman": T0 + 2 * SAAT}
    o = oyna(YOK, m, dis=dis)                           # b2 açılışı 102 -> +0.4 R
    assert o["neden"] == "sinyal" and o["r"] == pytest.approx(0.4)
    # alternatif dış çıkıştan ÖNCE stop yerse stop kazanır
    m2 = mumlar([(100, 106, 99, 105), (105, 106, 95, 96), (96, 97, 95, 96)])
    o2 = oyna("basabas_1R", m2, dis={"neden": "sinyal", "zaman": T0 + 2 * SAAT})
    assert o2["neden"] == "stop"


def test_veri_bitince_cozulmedi():
    m = mumlar([(100, 101, 99, 100)] * 3)
    assert oyna(YOK, m)["sonuc"] == "acik"


def test_lookahead_yok_girisden_onceki_ve_cikistan_sonraki_mumlar_sonucu_degistirmez():
    temel = [(100, 106, 99, 105), (105, 106, 94, 95)] + [(95, 96, 94, 95)] * 4
    m = mumlar([(500, 900, 1, 700)] * 3 + temel)                       # girişten ÖNCE saçma mumlar
    a = oyna("atr_iz_3", m, giris_i=3)
    m2 = mumlar([(1, 1, 1, 1)] * 3 + temel)                            # öncesi farklı
    assert oyna("atr_iz_3", m2, giris_i=3) == a
    kesik = {k: (v[:5] if k != "t" else v[:5]) for k, v in m.items()}   # çıkış (b4: i=4) sonrası mumlar yok
    assert oyna("atr_iz_3", kesik, giris_i=3) == a
    s = {k: v.copy() for k, v in m.items()}
    s["h"][6:], s["l"][6:] = 10_000, 1                                 # çıkıştan sonrası uçuk
    assert oyna("atr_iz_3", s, giris_i=3) == a


def test_ayni_giris_ve_ilk_stop_tum_alternatiflerde():
    m = mumlar([(100, 101, 94, 96)])                                   # ilk bar ilk stopu (95) vurur: hiçbir alternatif bunu değiştiremez
    for ad in ck.ALTERNATIFLER:
        o = oyna(ad, m, hedef=110.0)
        assert o["neden"] == "stop" and o["r"] == pytest.approx(-1.0), ad


def test_motor_maliyeti_paper_motorunun_yontemleriyle_ve_o_mumun_zamaninda():
    gorulen = []

    class M:
        _an = None
        ay = SimpleNamespace(hedef_limit_emri=True)
        tick = {"X": 0.01}
        step = {"X": 0.001}
        min_qty = {"X": 0.001}

        def _tk(self, s): gorulen.append(self._an); return 0.0005
        _mk = _ky = _sk = _tk

    mm = ck.MotorMaliyet(M())
    z = pd.Timestamp("2026-11-02 15:00", tz="UTC")
    assert mm.tk("X", z) == 0.0005 and gorulen == [z] and M._an is None and mm.hedef_maker is True
    assert mm.tick("X") == 0.01


# ---------------------------------------------------------------------------- ölçüt sınırları
def test_olcut_sinirlari():
    mevcut = [2.0] * 5 + [0.0] * 5                                     # toplam 10: eşik 10 + max(2, 2.0) = 12
    assert ck.olcut_gecti([1.5] * 8 + [0.0] * 2, mevcut) is True       # tam 12 (eşit) geçer
    assert ck.olcut_gecti([1.5] * 7 + [1.0] + [0.0] * 2, mevcut) is False   # 11.5 altı
    assert ck.olcut_gecti([1.5] * 8 + [-0.5, 0.5], mevcut) is False    # toplam 12 ama en kötü işlem mevcuttan kötü
    assert ck.olcut_gecti([1.5] * 8 + [0.0], mevcut) is False          # n eşleşmiyor
    assert ck.olcut_gecti([3.0] * 9, [1.0] * 9) is False               # < 10 işlem
    zarar = [-2.0] * 10                                                # toplam -20: eşik -20 + max(2, 4.0) = -16
    assert ck.olcut_gecti([-1.6] * 10, zarar) is True
    assert ck.olcut_gecti([-1.61] * 10, zarar) is False
    kucuk = [0.1] * 10                                                 # toplam 1: eşik 1 + max(2, 0.2) = 3 (mutlak taban 2 R)
    assert ck.olcut_gecti([0.3] * 10, kucuk) is True and ck.olcut_gecti([0.29] * 10, kucuk) is False


def test_uygulanabilirlik_fail_closed():
    assert ck.uygulanabilir("brooks") and ck.uygulanabilir("atr_iz_3") and ck.uygulanabilir("zirveden_geri_cekilme")
    assert ck.uygulanabilir("farley") is True                          # agresif_iz_* paper motorunda uygulanır (2026-11-19)
    assert set(ck.ALTERNATIFLER) == {"basabas_1R", "atr_iz_2", "atr_iz_3", "zaman_stopu_10", "kismi_2R_yarim", "brooks", "farley", "zirveden_geri_cekilme"}


# ---------------------------------------------------------------------------- paper entegrasyonu (gerçek Paper, sentetik işlemler)
SK = "gizlistrat|XUSDT|1d"
SIMDI = pd.Timestamp("2026-11-19 22:30", tz="UTC")           # TSİ 20.11 01:30
N_ISLEM = 12


def _mum_serisi():
    """Günlük mumlar 2026-09-01'den; her işlem için (gün d): giriş açılışı 100, d'de zirve 106 (+1.2R), d+1'de dip 95 (gerçek stop 95 vurur)."""
    df = duz(80, 100.0, dalga=0.001)
    df.index = pd.date_range("2026-09-01", periods=80, freq="D", tz="UTC", name="zaman")
    gunler = [5 + 4 * k for k in range(N_ISLEM)]
    for d in gunler:
        df.iloc[d, df.columns.get_loc("yuksek")] = 106.0
        df.iloc[d + 1, df.columns.get_loc("dusuk")] = 95.0
        df.iloc[d + 1, df.columns.get_loc("kapanis")] = 97.0
    return df, gunler


def _paper(tmp_path, gonderilen, gorunur=True, kimlik=SK, ogrenme=None):
    t = tanim(kimlik, "XUSDT", stop_yuzde=3.0)
    df, gunler = _mum_serisi()
    kur = {"XUSDT": SembolKurallari(0.01, 0.001, 0.001, 5.0)}
    p = pp.Paper([t], TekrarKaynagi({("XUSDT", "1d"): df}, {}), kur)
    p.gorunur = gorunur
    for d in gunler:
        gz, cz = df.index[d], df.index[d + 1] + pd.Timedelta(days=1)
        p.motor.islemler.append({"sembol": "XUSDT", "kol": kimlik, "yon": 1, "giris_zamani": gz, "giris_fiyati": 100.0, "cikis_zamani": cz,
                                 "cikis_fiyati": 95.0, "miktar": 1.0, "net_pnl": -5.0, "r": -1.0, "funding": 0.0, "cikis_nedeni": "stop",
                                 "giris_gerekcesi": {"stop": 95.0, "hedef": None}})
    c = ck.CikisKarsiOlgu(tmp_path, gonder=lambda m: gonderilen.append(m) or True, ogrenme=ogrenme)
    c._p = p
    return c, p, df


def _kol(p):
    return next(k for k in p.motor.tum_kollar if k.mod == "sinyal")


def _en_iyi(cikti, sk=SK):
    alts = cikti["stratejiler"][sk]["alternatifler"]
    gecen = {a: v for a, v in alts.items() if a != "_mevcut_yeniden" and v["olcut_gecti"] and v["uygulanabilir"]}
    return gecen, max(gecen, key=lambda a: gecen[a]["fark_r"]) if gecen else None


def test_karsi_olgu_sonucu_ve_olcut(tmp_path):
    g = []
    c, p, _ = _paper(tmp_path, g)
    cikti = c.karsi_olgu(SIMDI)
    s = cikti["stratejiler"][SK]
    assert s["islem"] == N_ISLEM
    b = s["alternatifler"]["basabas_1R"]
    assert b["n"] == N_ISLEM and b["mevcut_toplam_r"] == pytest.approx(-N_ISLEM) and b["fark_r"] > 0 and b["olcut_gecti"] is True
    assert b["toplam_r"] > -1.0                                        # ~0 R'ye (maliyetle az negatif) çıkar: -12 -> ~0
    assert set(b) >= {"n", "toplam_r", "ort_r", "kazanma", "mevcut_toplam_r", "fark_r", "en_kotu_r"}
    assert json.loads((tmp_path / ck.CIKTI).read_text(encoding="utf-8"))["stratejiler"][SK]["islem"] == N_ISLEM
    assert s["alternatifler"]["farley"]["uygulanabilir"] is True


def test_otomatik_uygulama_yalniz_cikis_alanlari_ve_telegram(tmp_path):
    g = []
    c, p, _ = _paper(tmp_path, g)
    kol = _kol(p)
    once = kol.cikis_ayarlari
    cikti = c.karsi_olgu(SIMDI)
    gecen, en = _en_iyi(cikti)
    assert en is not None
    ov = json.loads((tmp_path / ck.OVERRIDE).read_text(encoding="utf-8"))[SK]
    assert ov["alternatif"] == en and ov["onceki"] is None and ov["ayarlar"] and ov["zaman"]
    yeni = kol.cikis_ayarlari
    fark = {f.name for f in dataclasses.fields(yeni) if getattr(yeni, f.name) != getattr(once, f.name)}
    assert fark and fark <= set(ck.YONETIM_ALANLARI)                   # stop/boyut/risk/limit/sabit hedef/ATR periyodu değişmez
    assert yeni.sabit_r_hedefi == once.sabit_r_hedefi and yeni.atr_periyot == once.atr_periyot
    from motor.canli.paper_motor import desteklenmeyen_cikis_alanlari
    assert desteklenmeyen_cikis_alanlari(yeni) == []
    assert g == []                                                     # "Çıkış yöntemi değişti" Telegram'a gitmez (yalnız log)


def test_gizli_hesap_adi_telegramda_yok_gorunur_ad_var(tmp_path, caplog):
    import logging
    g = []
    c, p, _ = _paper(tmp_path, g, gorunur=False)
    with caplog.at_level(logging.INFO):
        c.karsi_olgu(SIMDI)
    assert g == []                                                     # Telegram'a hiçbir şey gitmez; log'da da gizli ad yok
    assert "Diğer hesaplar (1)" in caplog.text
    assert "gizlistrat" not in caplog.text and SK not in caplog.text


def test_acik_pozisyon_eski_cikisla_kalir_yalniz_yeni_giris_yeni_cikisi_alir(tmp_path):
    g = []
    c, p, _ = _paper(tmp_path, g)
    kol = _kol(p)
    once = kol.cikis_ayarlari
    p.motor.acik[kol.kimlik] = object()                                # açık pozisyon var
    c.karsi_olgu(SIMDI)
    assert (tmp_path / ck.OVERRIDE).exists() and kol.cikis_ayarlari == once and c._bekleyen is True
    c.uygula()
    assert kol.cikis_ayarlari == once                                  # hâlâ açık: eski çıkış
    p.motor.acik.pop(kol.kimlik)                                       # pozisyon kapandı
    c.uygula()
    assert kol.cikis_ayarlari != once and c._bekleyen is False         # yeni giriş artık yeni çıkışı alır


def test_gunde_bir_calisir_ve_tsi_0100_sonrasi(tmp_path):
    g = []
    c, p, _ = _paper(tmp_path, g)
    erken = pd.Timestamp("2026-11-19 21:30", tz="UTC")                 # TSİ 00:30: henüz değil
    assert c.gunluk(erken) is False and not (tmp_path / ck.CIKTI).exists()
    assert c.gunluk(SIMDI) is True and (tmp_path / ck.CIKTI).exists()
    assert c.gunluk(SIMDI + pd.Timedelta(hours=1)) is False            # aynı TSİ günü: ikinci çalışma yok
    c2 = ck.CikisKarsiOlgu(tmp_path, gonder=lambda m: True)            # yeniden başlatma: durum dosyasından
    c2._p = p
    assert c2.gunluk(SIMDI + pd.Timedelta(hours=2)) is False
    assert c.gunluk(SIMDI + pd.Timedelta(days=1)) is True              # ertesi TSİ günü


def test_cikis_geri_al_ve_ayni_alternatif_tekrar_uygulanmaz(tmp_path):
    g = []
    c, p, _ = _paper(tmp_path, g)
    kol = _kol(p)
    once = kol.cikis_ayarlari
    c.gunluk(SIMDI)                                                    # günlük adım çalıştı (ayrıca ertesi güne kadar tekrar çalışmaz)
    uygulanan = json.loads((tmp_path / ck.OVERRIDE).read_text(encoding="utf-8"))[SK]["alternatif"]
    assert kol.cikis_ayarlari != once
    (tmp_path / ck.GERI_AL_ISTEK).write_text(json.dumps({"zaman": SIMDI.isoformat()}), encoding="utf-8")
    c.tur(SIMDI + pd.Timedelta(minutes=5))                             # paper turu: istek uygulanır
    assert not (tmp_path / ck.GERI_AL_ISTEK).exists()
    assert json.loads((tmp_path / ck.OVERRIDE).read_text(encoding="utf-8")) == {}
    assert kol.cikis_ayarlari == once                                  # özgün çıkışa döndü
    assert [SK, uygulanan] in json.loads((tmp_path / ck.YASAK).read_text(encoding="utf-8"))
    assert any(m.startswith("[1L3A] ⚠️ çıkış geri alındı") for m in g)
    c.karsi_olgu(SIMDI + pd.Timedelta(days=1))                         # ölçüt yine geçse de aynı alternatif bir daha uygulanmaz
    ov = json.loads((tmp_path / ck.OVERRIDE).read_text(encoding="utf-8"))
    assert ov.get(SK, {}).get("alternatif") != uygulanan


def test_cikis_geri_al_eski_istek_yoksayilir_ve_degisiklik_yoksa_bilgi(tmp_path):
    g = []
    c, p, _ = _paper(tmp_path, g)
    (tmp_path / ck.GERI_AL_ISTEK).write_text(json.dumps({"zaman": (SIMDI - pd.Timedelta(hours=2)).isoformat()}), encoding="utf-8")
    c.geri_al_isle(SIMDI)
    assert not (tmp_path / ck.GERI_AL_ISTEK).exists() and g == []      # bayat istek: hiçbir şey olmaz
    (tmp_path / ck.GERI_AL_ISTEK).write_text(json.dumps({"zaman": SIMDI.isoformat()}), encoding="utf-8")
    c.geri_al_isle(SIMDI)
    assert len(g) == 1 and "geri alınacak çıkış değişikliği yok" in g[0]


def test_override_sonrasi_yalniz_yeni_girisler_sayilir_ve_onceki_kaydi(tmp_path):
    g = []
    c, p, _ = _paper(tmp_path, g)
    c.karsi_olgu(SIMDI)
    ilk = json.loads((tmp_path / ck.OVERRIDE).read_text(encoding="utf-8"))[SK]
    cikti2 = c.karsi_olgu(SIMDI + pd.Timedelta(days=1))                # override'dan önce girilen işlemler yeni çıkışın "mevcut"u değil
    assert SK not in cikti2["stratejiler"]
    assert json.loads((tmp_path / ck.OVERRIDE).read_text(encoding="utf-8"))[SK] == ilk


def test_fail_closed_desteklenmeyen_alan_olcutu_gecse_de_uygulanmaz(tmp_path):
    g = []
    c, p, _ = _paper(tmp_path, g)
    cikti = {"stratejiler": {SK: {"islem": 12, "alternatifler": {"x": {"n": 12, "fark_r": 9.0, "olcut_gecti": True, "uygulanabilir": False}}}}}
    assert c._otomatik_uygula(cikti, SIMDI, {}, set()) == [] and not (tmp_path / ck.OVERRIDE).exists() and g == []


def test_adaylara_en_iyi_cikis_yazilir(tmp_path):
    g = []
    ad = "gizlistrat_XUSDT_1d"
    df, gunler = _mum_serisi()
    gz = df.index[gunler[0]]
    cz = df.index[gunler[0] + 1] + pd.Timedelta(days=1)
    aday_id = f"{SK}|{gz}|{cz}"
    a = ok.Aday(id=aday_id, proje="1L3A", kurulum=ad, enstruman="XUSDT", varlik_sinifi="kripto", yon="long", ts=gz.to_pydatetime(), alindi=True, r=-1.0,
                cikis={"exit_reason": "stop"})
    og = SimpleNamespace(kapananlar=[a], dizin=tmp_path)
    c, p, _ = _paper(tmp_path, g, ogrenme=og)
    cikti = c.karsi_olgu(SIMDI)
    assert cikti["islem_en_iyi"][aday_id] != "mevcut" and a.cikis["en_iyi_cikis"] == cikti["islem_en_iyi"][aday_id]
    yazilan = ok.oku_jsonl(tmp_path / "ogrenme_adaylar.jsonl")
    assert yazilan[0].cikis["en_iyi_cikis"] == a.cikis["en_iyi_cikis"] and yazilan[0].cikis["exit_reason"] == "stop"


def test_kapali_ve_bagla(tmp_path):
    assert ck.bagla(object(), tmp_path, env={ck.ENV_KAPALI: "1"}) is None
    g = []
    c, p, _ = _paper(tmp_path, g)
    c2 = ck.CikisKarsiOlgu(tmp_path, kapali_=True)
    assert c2.bagla(p) is None
    cagri = []

    class P:
        motor = p.motor

        def adim(self, simdi, *a, **k):
            cagri.append("adim")
            return 3
    fake = P()
    c3 = ck.CikisKarsiOlgu(tmp_path, gonder=lambda m: True)
    c3.tur = lambda simdi: cagri.append("tur")
    assert c3.bagla(fake) is c3 and fake.adim(SIMDI) == 3 and cagri == ["adim", "tur"]


# ---------------------------------------------------------------------------- "alınsaydı" gece özeti
def _alinmayan_hazir(tmp_path, g, kayip_neden_n=25, kazanc_n=25, az_n=19):
    c, p, df = _paper(tmp_path, g)
    (tmp_path / "ogrenme_karne.json").write_text(json.dumps({"surum": "x"}), encoding="utf-8")
    kazanc_gun, kayip_gun = df.index[7], df.index[8]
    satir = lambda neden, gun: {"zaman": str(gun), "hesap": "h", "strateji": SK, "kol": SK, "sembol": "XUSDT", "tf": "1d", "yon": "long",     # noqa: E731
                                "fiyat": "100", "stop": "95", "hedef": "110", "zaman_cikisi_mum": None, "neden": neden}
    # kazanç gününde zirve 111 (hedef), kayıp gününde dip 94 (stop)
    df.iloc[7, df.columns.get_loc("yuksek")] = 111.0
    df.iloc[8, df.columns.get_loc("dusuk")] = 94.0
    rows = ([satir("ml_filtre", kazanc_gun) for _ in range(kazanc_n)] + [satir("ders:x", kayip_gun) for _ in range(kayip_neden_n)]
            + [satir("etiket:y", kazanc_gun) for _ in range(az_n)])
    (tmp_path / "alinmayan_sinyaller.jsonl").write_text("\n".join(json.dumps(r) for r in rows) + "\n", encoding="utf-8")
    return c, p


def test_alinmayan_sonuc_ozeti_ve_warn_esigi(tmp_path):
    g = []
    c, p = _alinmayan_hazir(tmp_path, g)
    o = c.alinmayan(SIMDI)
    nd = {x["neden"]: x for x in o["nedenler"]}
    assert nd["ml_filtre"]["sinyal"] == 25 and nd["ml_filtre"]["toplam_r"] == pytest.approx(50.0) and nd["ml_filtre"]["ort_r"] == pytest.approx(2.0)
    assert nd["ders:x"]["toplam_r"] == pytest.approx(-25.0) and nd["etiket:y"]["sinyal"] == 19
    assert o["atlanan"] == 69 and o["toplam_r"] == pytest.approx(50.0 - 25.0 + 38.0)
    assert json.loads((tmp_path / ck.ALINMAYAN_CIKTI).read_text(encoding="utf-8"))["atlanan"] == 69
    assert json.loads((tmp_path / "ogrenme_karne.json").read_text(encoding="utf-8"))["alinmayan_ozet"].startswith("alınsaydı")
    # "Atlanan sinyaller kârlıydı" gece özeti Telegram'a gitmez (yalnız log + karne)
    assert g == []
    c.alinmayan(SIMDI + pd.Timedelta(days=1))
    assert g == []
    assert not (tmp_path / ck.OVERRIDE).exists()                       # otomatik kural değişikliği YOK


def test_alinmayan_esik_sinirlari(tmp_path):
    g = []
    c, p = _alinmayan_hazir(tmp_path, g, kazanc_n=19)                  # 19 atlama: uyarı yok
    c.alinmayan(SIMDI)
    assert g == []


def test_gunluk_ozet_notuna_tek_satir(tmp_path):
    g = []
    c, p = _alinmayan_hazir(tmp_path, g)
    c.alinmayan(SIMDI)
    o = go.topla(tmp_path, SIMDI, ct_dizin=tmp_path / "ct", env={"L3A_REJIM_KAPALI": "1", "L3A_DURDUR_DOSYA": str(tmp_path / "D")})
    assert any(n.startswith("alınsaydı (90g)") for n in o["notlar"])
    o2 = go.topla(tmp_path / "yok", SIMDI, ct_dizin=tmp_path / "ct", env={"L3A_REJIM_KAPALI": "1", "L3A_DURDUR_DOSYA": str(tmp_path / "D")})
    assert not any("alınsaydı" in n for n in o2["notlar"])


# ---------------------------------------------------------------------------- Telegram /cikis_geri_al (iki adımlı)
def test_telegram_cikis_geri_al_iki_adimli(tmp_path):
    s, c, _ = komut_kur(tmp_path)
    mesaj(s, "/cikis_geri_al")                                         # override yok: kod istenmez
    assert "Geri alınacak" in son(c) and not s.cikis_geri_al_dosya.exists()
    s.durum.mkdir(parents=True, exist_ok=True)
    (s.cikis_geri_al_dosya.parent / "cikis_override.json").write_text(json.dumps({SK: {"alternatif": "atr_iz_3", "ayarlar": {}, "zaman": "x", "onceki": None}}),
                                                                       encoding="utf-8")
    mesaj(s, "/cikis_geri_al")
    assert "Kod: 1234" in son(c) and not s.cikis_geri_al_dosya.exists()    # 1. adım: yalnız kod
    mesaj(s, "9999")                                                   # yanlış kod: hiçbir şey olmaz
    assert not s.cikis_geri_al_dosya.exists() and "uygulanmadı" in son(c)
    mesaj(s, "/cikis_geri_al")
    mesaj(s, "1234")                                                   # 2. adım: istek dosyası (paper uygular)
    assert s.cikis_geri_al_dosya.exists() and s.cikis_geri_al_dosya.name == ck.GERI_AL_ISTEK and s.cikis_geri_al_dosya.parent == s.bayrak.parent
    assert SK not in son(c) and "gizlistrat" not in son(c)
    mesaj(s, "/cikis_geri_al")
    assert "zaten verilmiş" in son(c)
    assert "/cikis_geri_al" in tk.YARDIM and "/cikis_geri_al" in tk.RISKLI


# ---------------------------------------------------------------------------- otomatik geri alma
def test_geri_al_olcutu_sinirlari():
    ozgun = [1.0] * 10                                                 # toplam 10
    yeni = [0.0] * 10                                                  # toplam 0: 10 >= 0 + max(2, 0) -> geri al
    assert ck.geri_al_gerekli(yeni, ozgun) is True
    assert ck.geri_al_gerekli([0.9] * 10, ozgun) is False              # fark 1 R < 2 R; en kötü de aynı değil
    assert ck.geri_al_gerekli([0.8] * 10, ozgun) is True               # fark 2 R (eşit) geri alınır
    assert ck.geri_al_gerekli([-5.0] * 10, [-3.0] * 10) is True        # |yeni|x%20 = 10 R eşiği: fark 20 R
    assert ck.geri_al_gerekli([-5.0] * 10, [-4.0] * 10) is True        # fark 10 R = eşik (eşit geri alınır)
    assert ck.geri_al_gerekli([-5.0] * 10, [-4.1] * 10) is False       # fark 9 R < 10 R; en kötü fark 0.9 R < 1 R
    assert ck.geri_al_gerekli([1.0] * 9, [1.0] * 8 + [9.0]) is False   # eşli değil / < 10 işlem
    assert ck.geri_al_gerekli([1.0] * 5, [9.0] * 5) is False           # < 10 işlem
    iyi = [1.0] * 9 + [-2.0]                                           # toplam eşit; yalnız en kötü işlem belirgin kötü (-2 <= -0.5 - 1)
    assert ck.geri_al_gerekli(iyi, [1.0] * 9 + [-0.5]) is True
    assert ck.geri_al_gerekli([1.0] * 9 + [-1.4], [1.0] * 9 + [-0.5]) is False


def _ov_hazirla(c, p, alt="basabas_1R", zaman="2026-09-01T00:00:00+00:00", r_gercek=-3.0):
    """Override'ı elle yazar (geçmişten itibaren yürürlükte) ve gerçek işlemlerin R'sini r_gercek yapar."""
    kol = _kol(p)
    ck._yaz_json(c.dizin / ck.OVERRIDE, {SK: {"alternatif": alt, "ayarlar": ck.spec_json(ck.tam_spec(ck.ALTERNATIFLER[alt])), "zaman": zaman, "onceki": None}})
    c.uygula()
    for x in p.motor.islemler:
        x["r"] = r_gercek
    return kol


def test_otomatik_geri_alma_override_kotu_giderse(tmp_path):
    g = []
    c, p, _ = _paper(tmp_path, g)
    kol = _kol(p)
    once = kol.cikis_ayarlari
    _ov_hazirla(c, p)
    assert kol.cikis_ayarlari != once
    cikti = c.karsi_olgu(SIMDI)
    ga = cikti["stratejiler"][SK]["geri_alma"]
    assert ga["n"] == N_ISLEM and ga["gerekli"] is True and ga["yeni_toplam_r"] == pytest.approx(-3.0 * N_ISLEM)
    assert json.loads((tmp_path / ck.OVERRIDE).read_text(encoding="utf-8")) == {}
    assert kol.cikis_ayarlari == once                                  # kol özgün ayarına döndü
    assert ["gizlistrat|XUSDT|1d", "basabas_1R"] in json.loads((tmp_path / ck.YASAK).read_text(encoding="utf-8"))
    uyar = [m for m in g if m.startswith("[1L3A] ⚠️ ")]
    assert len(uyar) == 1 and "yeni çıkış yöntemi kötü gitti, eski yönteme dönüldü" in uyar[0] and f"{N_ISLEM} işlem" in uyar[0]
    assert "Gizlistrat" in uyar[0]                                     # görünür hesap adı
    c.karsi_olgu(SIMDI + pd.Timedelta(days=1))                         # geri alınan alternatif kara listede: tekrar uygulanmaz
    assert json.loads((tmp_path / ck.OVERRIDE).read_text(encoding="utf-8")).get(SK, {}).get("alternatif") != "basabas_1R"


def test_otomatik_geri_alma_gizli_hesap_adi_yok_ve_acik_pozisyon_eski_cikisla_kalir(tmp_path):
    g = []
    c, p, _ = _paper(tmp_path, g, gorunur=False)
    kol = _kol(p)
    once = kol.cikis_ayarlari
    _ov_hazirla(c, p)
    yeni = kol.cikis_ayarlari
    p.motor.acik[kol.kimlik] = object()                                # açık pozisyon var
    c.karsi_olgu(SIMDI)
    assert json.loads((tmp_path / ck.OVERRIDE).read_text(encoding="utf-8")) == {}
    assert kol.cikis_ayarlari == yeni and c._bekleyen is True          # açık pozisyon mevcut çıkışıyla kalır
    uyar = [m for m in g if m.startswith("[1L3A] ⚠️ ")]
    assert len(uyar) == 1 and "Diğer hesaplar (1)" in uyar[0] and "gizlistrat" not in uyar[0] and SK not in uyar[0]
    p.motor.acik.pop(kol.kimlik)
    c.uygula()
    assert kol.cikis_ayarlari == once                                  # pozisyon kapanınca özgün ayar


def test_geri_alma_olmaz_override_iyi_gidiyorsa_veya_az_islem(tmp_path):
    g = []
    c, p, _ = _paper(tmp_path, g)
    _ov_hazirla(c, p, r_gercek=-1.0)                                   # gerçek = özgün: kötüleşme yok
    c.karsi_olgu(SIMDI)
    assert SK in json.loads((tmp_path / ck.OVERRIDE).read_text(encoding="utf-8")) and not any(m.startswith("[1L3A] ⚠️") for m in g)
    g2 = []
    c2, p2, _ = _paper(tmp_path / "b", g2)
    _ov_hazirla(c2, p2)
    p2.motor.islemler[:] = p2.motor.islemler[:9]                       # 9 işlem < 10
    c2.karsi_olgu(SIMDI)
    assert SK in json.loads((tmp_path / "b" / ck.OVERRIDE).read_text(encoding="utf-8")) and g2 == []


def test_farley_uygulanabilir_ve_olcutten_gecerse_uygulanir(tmp_path):
    g = []
    c, p, _ = _paper(tmp_path, g)
    kol = _kol(p)
    cikti = {"stratejiler": {SK: {"islem": 12, "alternatifler": {"farley": {"n": 12, "fark_r": 9.0, "olcut_gecti": True, "uygulanabilir": True}}}}}
    assert c._otomatik_uygula(cikti, SIMDI, {}, set()) == [SK]
    assert kol.cikis_ayarlari.agresif_iz_esigi == 0.75 and kol.cikis_ayarlari.agresif_iz_atr_k == 1.0


# ---------------------------------------------------------------------------- Farley: paper = backtest (yeniden oynatma ile canlı paper aynı mantık)
@pytest.mark.parametrize("kimlik,tf,n,bas_i,seed", [("swing__cci-esik|SOLUSDT|1d", "1d", 500, 300, 1), ("dis__dual-thrust|ETHUSDT|30m", "30m", 1200, 600, 4)])
def test_farley_agresif_iz_paper_ve_backtest_ayni(kimlik, tf, n, bas_i, seed):
    from testler.test_paper_motor import TAN, kural, sentetik
    from motor.canli import paper_esleme as es
    t = TAN[kimlik]
    nes = t.nesne
    eski = nes.cikis_ayarlari
    hedefli = dataclasses.replace(eski, atr_iz_suren_k=3.0, agresif_iz_esigi=0.75, agresif_iz_atr_k=1.0, sabit_r_hedefi=eski.sabit_r_hedefi or 2.0)
    nes.cikis_ayarlari = hedefli
    try:
        m = sentetik(n, tf, seed=seed, p0=100.0, vol=0.02 if tf != "30m" else 0.006)
        r = es.tek_esle(t, m, None, {t.sembol: kural(t.sembol)}, m.index[bas_i])
    finally:
        nes.cikis_ayarlari = eski
    assert r["n_backtest"] == r["n_paper"] and r["n_backtest"] >= 1
    assert r["tam_esit_zaman_haric"], r["farklar"][:3]
    assert r["max_mutlak_fark"] <= 1e-9


def test_cikis_degisti_mesaji_telegrama_gitmez(tmp_path):
    g = []
    c = ck.CikisKarsiOlgu(tmp_path, gonder=lambda m: g.append(m) or True, kapali_=False)
    c._ad_gorunur = lambda sk: "CCI Eşik · SOL 1G"
    t0 = pd.Timestamp("2026-11-19 10:00", tz="UTC")
    c._degisti_bildir("sk", "zirveden_geri_cekilme", t0)
    c._degisti_bildir("sk", "zirveden_geri_cekilme", t0 + pd.Timedelta(hours=2))        # rutin tekrar bastırılır
    c._degisti_bildir("sk", "zirveden_geri_cekilme", t0 + pd.Timedelta(hours=7))
    assert g == []                                                                       # hiçbir zaman Telegram'a gitmez
