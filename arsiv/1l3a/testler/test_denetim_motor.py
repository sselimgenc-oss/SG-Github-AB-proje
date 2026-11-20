"""Genel denetim (2026-11-20) grup D/E bulgularının düzeltme testleri (raporlar/denetim_testleri/denetim_D_test.py, denetim_E_canli_yurutucu.py'den
taşındı, uyarlandı). Ağ YOK."""
import inspect
import json
from decimal import Decimal as D
from types import SimpleNamespace as NS

import numpy as np
import pandas as pd
import pytest

from motor.canli import cikis_karsi_olgu as cko
from motor.canli import paper as pp
from motor.canli import paper_veri as pv
from motor.canli.borsa.binance_futures import BorsaHata
from motor.canli.borsa.canli_yurutucu import Niyet, PozGorunum
from motor.canli.borsa.motor_kopru import gorunum
from testler.test_canli_borsa import ARALIK, T0, Ortam, ac_niyeti, gor
from testler.test_karantina import KOL_A, KOL_B, Bozuk, Gec, _kolu, _paper, _t, _veri
from testler.test_paper_motor import tanim


# ---------------------------------------------------------------------------- D1 (kullanıcı kararı: canlıda AÇIK) çıkış karşı-olgusu canlı modu
def test_D1_cikis_karsi_olgu_canli_yolda_acik_ve_canli_modda():
    kaynak = inspect.getsource(pp._canli_calistir_kilitli)
    satir = next(x for x in kaynak.splitlines() if "cikis_karsi_olgu.bagla(" in x)
    assert "canli=" in satir, satir.strip()
    assert "canli" in inspect.signature(cko.bagla).parameters
    assert cko.bagla(NS(adim=lambda *a, **k: 0), "/tmp/yok", canli=True, env={}) is not None      # canlıda bağlanır (kapatılmaz)


def test_D1_canli_modda_kismi_cikis_override_uygulanmaz_digeri_uygulanir(tmp_path):
    from testler.test_cikis_karsi_olgu import SK, _kol
    from testler.test_cikis_karsi_olgu import _paper as cko_paper
    c, p, _ = cko_paper(tmp_path, [])
    c.canli = True
    kol = _kol(p)
    once = kol.cikis_ayarlari
    (tmp_path / cko.OVERRIDE).write_text(json.dumps({SK: {"alternatif": "kismi_2R_yarim", "ayarlar": cko.ALTERNATIFLER["kismi_2R_yarim"],
                                                          "zaman": "2026-11-20T00:00:00Z", "onceki": None}}), encoding="utf-8")
    c.uygula()
    assert kol.cikis_ayarlari == once and not kol.cikis_ayarlari.kismi        # canlı kısmi çıkış yapamaz: fail-closed
    (tmp_path / cko.OVERRIDE).write_text(json.dumps({SK: {"alternatif": "basabas_1R", "ayarlar": cko.ALTERNATIFLER["basabas_1R"],
                                                          "zaman": "2026-11-20T00:00:00Z", "onceki": None}}), encoding="utf-8")
    c.uygula()
    assert kol.cikis_ayarlari.basabas_r_esigi == 1.0                          # canlının yansıtabildiği (stop yükseltme) uygulanır
    # otomatik seçim: canlıda kısmi içeren alternatif aday değil
    cikti = {"stratejiler": {SK: {"islem": 12, "alternatifler": {"brooks": {"n": 12, "fark_r": 9.0, "olcut_gecti": True, "uygulanabilir": True}}}}}
    assert c._otomatik_uygula(cikti, pd.Timestamp("2026-11-20T02:00Z"), {}, set()) == []


def test_D1_override_cikislari_canliya_yansir(tmp_path):
    """Paper'da override edilmiş yönetim (başabaş/iz süren -> p.stop yükselir; zaman/roi/geri çekilme -> cikis_emri) köprü + yürütücüyle canlıya geçer."""
    kol = NS(kimlik="K1", sembol="BTCUSDT", mod="sinyal", giris_emri=None, cikis_emri=None, birim="B1",
             cikis_ayarlari=NS(sabit_r_hedefi=None, kismi=None), grup_payi=1)
    birim = NS(kollar=[kol], son_t=T0, aralik=ARALIK, tf="1h", ad="B1")
    motor = NS(kill=False, gunluk_blok=False, risk_oran=0.01, karantina=set(), engelli_semboller=set(), _sk=lambda s: D("0.0005"),
               _tk=lambda s: D("0.0005"), acik={"K1": NS(sembol="BTCUSDT", yon=1, stop=D("49800"), hedef=None)})
    e = Ortam(tmp_path)
    e.y.adim(gor([ac_niyeti()]))
    g = gorunum(motor, [birim])                                              # paper başabaş: stop 49000 -> 49800
    assert g.pozlar["K1"].stop == D("49800")
    e.y.adim(g)
    assert [o["tetik"] for o in e.borsa.acik.values() if o["tur"] == "STOP_MARKET"] == [D("49800")]
    kol.cikis_emri = "geri_cekilme"                                          # paper override çıkışı (cikis_emri) -> canlı 'kapat' niyeti
    g = gorunum(motor, [birim])
    assert [n.tur for n in g.niyetler] == ["kapat"]
    e.y.adim(g)
    assert not e.borsa.poz


# ---------------------------------------------------------------------------- D2: strateji ZeroDivisionError / ValueError -> yalnız o strateji karantina
@pytest.mark.parametrize("hata", [ZeroDivisionError("float division by zero"), ArithmeticError("x"), ValueError("strateji içi")])
def test_D2_strateji_aritmetik_ve_valueerror_karantinaya_alinir_diger_strateji_surer(hata):
    mum = _veri()
    a = tanim(KOL_A, "AUSDT", grup="g1", pay="0.5", stop_yuzde=1.0)
    a.nesne = Bozuk(stop_yuzde=1.0)
    a.nesne.patla = 8
    a.nesne.hata = hata
    b = tanim(KOL_B, "BUSDT", grup="g2", pay="0.5", stop_yuzde=1.0)
    b.nesne = Gec(stop_yuzde=1.0)
    b.nesne.basla = 8
    p = _paper([a, b], mum)
    p.baslat(_t(mum, 3))
    p.adim(_t(mum, 12))
    assert p.karantina.get(KOL_A, {}).get("durum") == "aktif"
    ib, ab = _kolu(p, KOL_B)
    assert ab or ib


def test_D2_gecici_hata_siniflari_kod_hatasi_degil():
    for e in (pv.BinanceHata("503"), OSError("ag"), json.JSONDecodeError("x", "", 0), UnicodeDecodeError("utf-8", b"\xff", 0, 1, "x")):
        assert not pv.kod_hatasi_mi(e) and not pv.strateji_hatasi_mi(e)
    assert not pv.kod_hatasi_mi(ValueError("veri")) and pv.strateji_hatasi_mi(ValueError("veri"))   # veri yolunda ValueError geçici kalır
    assert pv.kod_hatasi_mi(ZeroDivisionError()) and pv.kod_hatasi_mi(ArithmeticError())


def test_D2_karantina_mesaji_sade_uyari_gizli_hesap_adsiz():
    from motor.canli import telegram as tg
    mum = _veri()
    p = _paper([tanim(KOL_A, "AUSDT", grup="g1", pay="0.5", stop_yuzde=1.0)], mum)
    giden = []
    p.bildirim = lambda tur, m: giden.append((tur, m))
    p._karantinaya_al(KOL_A, ValueError("x"))
    assert giden[-1] == ("karantina", f"{KOL_A} stratejisi hata verdi, yeni işlem açmıyor; açık pozisyonlar stop/hedefle sürüyor")
    p.gorunur = False
    p.karantina_bildirim.clear()
    p._karantinaya_al(KOL_A, ValueError("x"))
    assert giden[-1][1] == "Diğer hesap stratejisi hata verdi, yeni işlem açmıyor; açık pozisyonlar stop/hedefle sürüyor"
    out = []
    tg.Bildirimci(lambda m: out.append(m) or True, lambda: 1000.0).olay("karantina", giden[-1][1])
    assert out[0].startswith("[1L3A] ⚠️ Diğer hesap stratejisi hata verdi")


# ---------------------------------------------------------------------------- D3: karantinada gün sonu kapanışı korunur
class GunIci(Bozuk):
    ad = "test__gun_ici"

    def sinyaller(self, mumlar):
        sig = super().sinyaller(mumlar)
        sig["gun_sonu_kapanis"] = True
        return sig


def test_D3_karantinada_gun_ici_pozisyon_gece_tasinmaz():
    mum = _veri()
    a = tanim(KOL_A, "AUSDT", grup="g1", pay="0.5", stop_yuzde=1.0)
    a.nesne = GunIci(stop_yuzde=1.0)
    a.nesne.patla = 8
    b = tanim(KOL_B, "BUSDT", grup="g2", pay="0.5", stop_yuzde=1.0)
    b.nesne = Gec(stop_yuzde=1.0)
    b.nesne.basla = 10 ** 9
    p = _paper([a, b], mum)
    p.baslat(_t(mum, 3))
    p.adim(_t(mum, 7))
    assert all(x["cikis_nedeni"] == "gun_sonu" for x in _kolu(p, KOL_A)[0])
    p.adim(_t(mum, 12))
    assert p.motor.karantina == {KOL_A}
    assert not _kolu(p, KOL_A)[1]


# ---------------------------------------------------------------------------- D6: mesajı değişen aynı tür kod hatası da sınırda durur
class _Dur(BaseException):
    pass


def test_D6_sonsuz_dene_ardisik_kod_hatasi_mesaj_degisse_de_durur():
    n = [0]

    def fn():
        n[0] += 1
        if n[0] > 30:
            raise _Dur()
        raise KeyError(f"sembol_{n[0]}")
    with pytest.raises(KeyError):
        pp.sonsuz_dene(fn, "test", uyku=lambda s: None, saat=lambda: 0.0)
    assert n[0] == pp.KOD_HATASI_SINIRI


def test_D6_tur_koruyucu_kod_hatasi_mesaj_degisse_de_sayilir():
    p = NS(olay_ekle=lambda *a, **k: None)
    k = pp.TurKoruyucu(p, geri_yukle=lambda: None)
    n = [0]

    def tur():
        n[0] += 1
        raise KeyError(f"anahtar_{n[0]}")
    sonuc = [k.calistir(tur) for _ in range(pp.HATA_TEKRAR_SINIRI)]
    assert sonuc[-1] is False and k.cikis_kodu == 1
    k2 = pp.TurKoruyucu(p, geri_yukle=lambda: None)                         # kod dışı hata: mesaj farklıysa eski davranış (yeniden sayım)
    m = [0]

    def tur2():
        m[0] += 1
        raise RuntimeError(f"r{m[0]}")
    assert all(k2.calistir(tur2) for _ in range(pp.HATA_TEKRAR_SINIRI))


# ---------------------------------------------------------------------------- D7: genel kesinti paydası = bu turda denenen seriler
def _kaynak():
    from motor.canli import paper_canli as pc
    from testler.test_paper_motor import duz
    k = object.__new__(pc.CanliKaynak)
    h1 = duz(48, 100.0)
    h1.index = pd.date_range("2026-11-18", periods=48, freq="h", tz="UTC", name="zaman")
    d1 = duz(10, 100.0)
    d1.index = pd.date_range("2026-11-10", periods=10, freq="D", tz="UTC", name="zaman")
    k.seriler = [("XUSDT", "1h"), ("YUSDT", "1d")]
    k.mumlar = {("XUSDT", "1h"): h1, ("YUSDT", "1d"): d1}
    k.son_kontrol, k.funding_son, k.semboller = {}, {"t": pd.Timestamp("2026-11-20T02:20Z")}, ["XUSDT", "YUSDT"]
    k._veri_hata_olay, k.son_mum_bozuk, k.olay = {}, {}, lambda t, m: None
    return k


def test_D7_guncelle_denenen_tum_seriler_hataliysa_yukselir():
    k = _kaynak()

    def patla(*a, **kw):
        raise pv.BinanceHata("503 genel kesinti")
    k._mum_al = patla
    with pytest.raises(pv.BinanceHata):
        k.guncelle(pd.Timestamp("2026-11-20T02:30Z"))                       # yalnız 1h serinin sırası geldi ve hatalı


def test_D7_bir_seri_hatali_digeri_basarili_yukselmez():
    k = _kaynak()
    from testler.test_paper_motor import duz

    def al(s, tf, bas, simdi):
        if s == "XUSDT":
            raise pv.BinanceHata("503")
        d = duz(1, 100.0)
        d.index = pd.DatetimeIndex([bas], name="zaman")
        return d
    k._mum_al = al
    k.funding_son["t"] = pd.Timestamp("2026-11-21T00:20Z")
    assert k.guncelle(pd.Timestamp("2026-11-21T00:30Z")) == 1             # ikisi de denendi; biri başarılı -> izole, yükselmez


# ---------------------------------------------------------------------------- E3: belirsiz kapatmada dolmamış emir "kapandı" sayılmaz
def _acik_kur(tmp_path):
    e = Ortam(tmp_path)
    e.y.adim(gor([ac_niyeti(hedef="52000")]))
    assert e.borsa.poz and any(o["tur"] == "STOP_MARKET" for o in e.borsa.acik.values())
    return e


def _belirsiz_kapat(e, durum, dolan_kat):
    b = e.borsa
    orig = b.piyasa

    def piyasa(s, yon, q, cid, reduce_only=False):
        if reduce_only:
            b.cagrilar.append(("piyasa", s, yon, q, cid, reduce_only))
            b.dolu[cid] = {"client_id": cid, "durum": durum, "dolan": q * dolan_kat, "sembol": s, "tur": "MARKET", "reduce_only": True,
                           "miktar": q, "tetik": D(0), "yon": yon, "kosullu": False}
            if dolan_kat:
                b.poz.pop(s, None) if dolan_kat == 1 else None
            raise BorsaHata("ağ", belirsiz=True)
        return orig(s, yon, q, cid, reduce_only)
    b.piyasa = piyasa


@pytest.mark.parametrize("durum,kat", [("EXPIRED", D(0)), ("PARTIALLY_FILLED", D("0.5"))])
def test_E3_belirsiz_kapatmada_dolmamis_emir_kapandi_sayilmaz(tmp_path, durum, kat):
    e = _acik_kur(tmp_path)
    _belirsiz_kapat(e, durum, kat)
    kap = Niyet("kapat", "K1", "BTCUSDT", 1, neden="sinyal", aralik=ARALIK)
    e.y.adim(gor([kap], {"K1": PozGorunum("BTCUSDT", 1, D(49000))}))
    assert e.borsa.poz
    assert any(o["tur"] == "STOP_MARKET" for o in e.borsa.acik.values())
    assert "K1" in e.y.durum["pozlar"]


def test_E3_belirsiz_kapatmada_dolmus_emir_kapandi_sayilir(tmp_path):
    e = _acik_kur(tmp_path)
    _belirsiz_kapat(e, "FILLED", D(1))
    kap = Niyet("kapat", "K1", "BTCUSDT", 1, neden="sinyal", aralik=ARALIK)
    e.y.adim(gor([kap], {"K1": PozGorunum("BTCUSDT", 1, D(49000))}))
    assert "K1" not in e.y.durum["pozlar"] and not any(o["tur"] == "STOP_MARKET" for o in e.borsa.acik.values())


# ---------------------------------------------------------------------------- E2: paper'ın reddedeceği giriş canlı niyete dönüşmez
def _sahte_motor(karantina=(), engelli=()):
    return NS(kill=False, gunluk_blok=False, acik={}, risk_oran=0.01, karantina=set(karantina), engelli_semboller=set(engelli),
              _sk=lambda s: D("0.0005"), _tk=lambda s: D("0.0005"))


def _sahte_birim():
    kol = NS(kimlik="B1|BTCUSDT", sembol="BTCUSDT", mod="sinyal", giris_emri=(1, 49000.0, 52000.0, float("nan")), cikis_emri=None,
             cikis_ayarlari=NS(sabit_r_hedefi=None, kismi=None), grup_payi=1, birim="B1")
    return NS(kollar=[kol], son_t=T0, aralik=ARALIK, tf="1h", ad="B1")


def test_E2_karantinadaki_birimde_canli_giris_niyeti_uretilmez():
    assert [n for n in gorunum(_sahte_motor(karantina={"B1"}), [_sahte_birim()]).niyetler if n.tur == "ac"] == []
    assert [n for n in gorunum(_sahte_motor(engelli={"BTCUSDT"}), [_sahte_birim()]).niyetler if n.tur == "ac"] == []
    assert [n.tur for n in gorunum(_sahte_motor(), [_sahte_birim()]).niyetler] == ["ac"]


def _ct_paper():
    from testler.test_ct_kadro import coin, kapanis, ozet, paper_kur
    p, _ = paper_kur(ozet(kapanis(110), [coin("BTC", 8, 1, 2e6)]))
    return p, kapanis


def test_E2_paper_suzgeci_reddedecek_girisi_canli_niyet_yapmaz():
    p, kapanis = _ct_paper()
    p.motor.giris_suzgeci = lambda *a, **k: (False, "ml_filtre")
    p.baslat(kapanis(105))
    p.adim(kapanis(110))
    g = gorunum(p.motor, p.birimler)
    p.adim(kapanis(112))
    assert not p.motor.acik
    assert [n for n in g.niyetler if n.tur == "ac"] == []


def test_E2_suzgec_karari_niyet_ve_dolumda_paylasilir_tek_cagri():
    """Süzgeç niyet anında BİR kez sorulur; paper dolumu aynı kararı kullanır (durumlu ders çarpanı iki kez ilerlemez, canlı = paper)."""
    p, kapanis = _ct_paper()
    cagri = []
    p.motor.giris_suzgeci = lambda *a, **k: cagri.append(a) or (True, "")
    p.baslat(kapanis(105))
    p.adim(kapanis(110))
    n0 = len(cagri)
    g = gorunum(p.motor, p.birimler)
    gorunum(p.motor, p.birimler)                                             # aynı turda tekrar: önbellekten
    assert [n.tur for n in g.niyetler] == ["ac"] and len(cagri) == n0 + 1
    p.adim(kapanis(112))
    assert p.motor.acik and len(cagri) == n0 + 1                            # dolum aynı kararı kullandı (yeni çağrı yok)


def test_E2_niyette_red_dolumda_da_red_ayni_karar():
    """Niyet anında reddedilen sinyal (durumlu süzgeç sonra 'izin' verse bile) paper dolumunda da reddedilir: canlı ve paper ayrışmaz."""
    p, kapanis = _ct_paper()
    cevap = [(False, "ders:x"), (True, "")]
    p.motor.giris_suzgeci = lambda *a, **k: cevap.pop(0) if cevap else (True, "")
    p.baslat(kapanis(105))
    p.adim(kapanis(110))
    g = gorunum(p.motor, p.birimler)
    assert [n for n in g.niyetler if n.tur == "ac"] == []
    p.adim(kapanis(111))
    assert not p.motor.acik


def test_E2_islem_disi_sembolde_canli_niyet_yok_acik_pozisyon_kapat_niyeti_surer():
    from motor.canli import sembol_izleme as si
    from testler.test_ct_kadro import coin, kapanis, ozet, paper_kur
    p, _ = paper_kur(ozet(kapanis(110), [coin("BTC", 8, 1, 2e6)]), ozet(kapanis(130), [coin("BTC", 1, 8, -2e6, "short")]))
    p.baslat(kapanis(105))
    p.adim(kapanis(110))
    iz = si.kur(p, None, ["BTCUSDT"], sessiz=True)
    iz.uygula_durum({"BTCUSDT": False}, kapanis(110))
    assert [n for n in gorunum(p.motor, p.birimler).niyetler if n.tur == "ac"] == []
    iz.uygula_durum({"BTCUSDT": True}, kapanis(111))
    p.adim(kapanis(130))
    assert any(n.tur == "kapat" for n in gorunum(p.motor, p.birimler).niyetler) or not p.motor.acik


def test_E2_kismi_cikisli_kolda_canli_giris_niyeti_yok():
    b = _sahte_birim()
    b.kollar[0].cikis_ayarlari = NS(sabit_r_hedefi=None, kismi=((2.0, 0.5),))
    assert [n for n in gorunum(_sahte_motor(), [b]).niyetler if n.tur == "ac"] == []
