"""Denetim E: canlı yürütücü bulguları (sahte borsa, ağ YOK). Kırmızı testler = bulgu."""
from decimal import Decimal as D

import pandas as pd

from motor.canli.borsa.binance_futures import BorsaHata
from motor.canli.borsa.canli_yurutucu import Niyet, PozGorunum
from testler.test_canli_borsa import ARALIK, T0, Ortam, ac_niyeti, gor


def _acik_kur(tmp_path):
    e = Ortam(tmp_path)
    e.y.adim(gor([ac_niyeti(hedef="52000")]))
    assert e.borsa.poz and any(o["tur"] == "STOP_MARKET" for o in e.borsa.acik.values())
    return e


def test_E1_belirsiz_kapatmada_dolmamis_emir_kapandi_sayilmaz(tmp_path):
    """_piyasa_kapat: belirsiz hata + sorgula(cid) bir emir döndürdü diye True; emir EXPIRED/dolan=0 ise pozisyon hâlâ açık ama
    _kapat_rec stopları iptal edip kaydı siler -> çıplak pozisyon."""
    e = _acik_kur(tmp_path)
    b = e.borsa
    orig = b.piyasa

    def piyasa(s, yon, q, cid, reduce_only=False):
        if reduce_only:
            b.cagrilar.append(("piyasa", s, yon, q, cid, reduce_only))
            b.dolu[cid] = {"client_id": cid, "durum": "EXPIRED", "dolan": D(0), "sembol": s, "tur": "MARKET", "reduce_only": True,
                           "miktar": q, "tetik": D(0), "yon": yon, "kosullu": False}
            raise BorsaHata("ağ", belirsiz=True)
        return orig(s, yon, q, cid, reduce_only)
    b.piyasa = piyasa
    kap = Niyet("kapat", "K1", "BTCUSDT", 1, neden="sinyal", aralik=ARALIK)
    e.y.adim(gor([kap], {"K1": PozGorunum("BTCUSDT", 1, D(49000))}))
    assert b.poz, "pozisyon hâlâ açık olmalı (kapatma gerçekleşmedi)"
    assert any(o["tur"] == "STOP_MARKET" for o in b.acik.values()), "pozisyon açıkken borsa stopu iptal edilmemeli"
    assert "K1" in e.y.durum["pozlar"], "pozisyon açıkken kayıt silinmemeli"


def test_E2_kisman_dolumda_stop_dolan_miktarda(tmp_path):
    """Kısmi dolum: stop ve kayıt dolan miktar üzerinden kurulmalı (kontrol testi; yeşil beklenir)."""
    e = Ortam(tmp_path)
    b = e.borsa
    orig = b.piyasa

    def piyasa(s, yon, q, cid, reduce_only=False):
        o = orig(s, yon, q / 2, cid, reduce_only)
        return o
    b.piyasa = piyasa
    e.y.adim(gor([ac_niyeti()]))
    stoplar = [o for o in b.acik.values() if o["tur"] == "STOP_MARKET"]
    assert len(stoplar) == 1 and stoplar[0]["miktar"] == b.poz["BTCUSDT"]


def test_E3_short_yon_ve_stop_tarafi(tmp_path):
    e = Ortam(tmp_path)
    n = Niyet("ac", "K1", "BTCUSDT", -1, stop=D("51000"), hedef=D("48000"), sinyal_zamani=T0, aralik=ARALIK)
    e.y.adim(gor([n]))
    c = [x for x in e.borsa.cagrilar if x[0] in ("piyasa", "kosullu")]
    assert c[0][2] == "SELL" and c[0][5] is False
    assert c[1][2:4] == ("STOP_MARKET", "BUY") and c[2][2:4] == ("TAKE_PROFIT_MARKET", "BUY")


def test_E5_kayma_sonrasi_kucultme_stop_ve_hedef_kalan_miktarda(tmp_path):
    """Gerçek dolum fiyatı kayınca pozisyon küçültülür; stop ve hedef KALAN miktarla kurulmalı (kontrol; yeşil beklenir)."""
    e = Ortam(tmp_path)
    e.borsa.fill_px = D("50400")
    e.y.adim(gor([ac_niyeti(hedef="52000")]))
    q = e.borsa.poz["BTCUSDT"]
    emirler = {o["tur"]: o["miktar"] for o in e.borsa.acik.values()}
    assert emirler == {"STOP_MARKET": q, "TAKE_PROFIT_MARKET": q}


def test_E6_gunluk_blokta_yeni_giris_yok_acik_pozisyon_kalir(tmp_path):
    e = _acik_kur(tmp_path)
    e.borsa.ozs = D("940")                                   # gün başı 1000 -> %6 kayıp
    n = len([c for c in e.borsa.cagrilar if c[0] == "piyasa"])
    e.y.adim(gor([ac_niyeti(t=T0 + ARALIK, kol="K2")], {"K1": PozGorunum("BTCUSDT", 1, D(49000))}))
    assert e.y.durum["gun_blok"] and len([c for c in e.borsa.cagrilar if c[0] == "piyasa"]) == n and e.borsa.poz


def test_E7_kill_pozisyonu_reduceonly_kapatir_ve_emirleri_siler(tmp_path):
    e = _acik_kur(tmp_path)
    e.borsa.ozs = D("690")                                   # zirveden -%31
    e.y.adim(gor())
    assert e.y.durum["kill"] and not e.borsa.poz and not e.borsa.acik
    son = [c for c in e.borsa.cagrilar if c[0] == "piyasa"][-1]
    assert son[2] == "SELL" and son[5] is True
    e.y = e.yeni()
    e.borsa.ozs = D("1000")
    e.y.adim(gor([ac_niyeti(t=T0 + ARALIK, kol="K2")]))
    assert not e.borsa.poz                                   # kill yeniden başlatmada da sürer


# ---------------------------------------------------------------------------------------------- paper kapıları canlıya aktarılıyor mu
from types import SimpleNamespace as NS

from motor.canli.borsa.motor_kopru import gorunum


def _sahte_motor(karantina=(), engelli=()):
    return NS(kill=False, gunluk_blok=False, acik={}, risk_oran=0.01, karantina=set(karantina), engelli_semboller=set(engelli),
              _sk=lambda s: D("0.0005"), _tk=lambda s: D("0.0005"))


def _sahte_birim():
    kol = NS(kimlik="B1|BTCUSDT", sembol="BTCUSDT", mod="sinyal", giris_emri=(1, 49000.0, 52000.0, float("nan")), cikis_emri=None,
             cikis_ayarlari=NS(sabit_r_hedefi=None, kismi=None), grup_payi=1, birim="B1")
    return NS(kollar=[kol], son_t=T0, aralik=ARALIK, tf="1h", ad="B1")


def test_E4b_paper_suzgeci_reddedecek_girisi_canli_niyet_yapar():
    """GERÇEK paper motoru: ML/etiket süzgeci (giris_suzgeci) paper girişini reddeder; ama köprü niyeti paper dolumundan ÖNCE `giris_emri`'nden
    türetir -> canlı girer, paper hiç girmez, bir bar sonra 'motor_kapali' kapatır."""
    from testler.test_ct_kadro import coin, kapanis, ozet, paper_kur
    p, _ = paper_kur(ozet(kapanis(110), [coin("BTC", 8, 1, 2e6)]))
    p.motor.giris_suzgeci = lambda *a, **k: (False, "ml_filtre")
    p.baslat(kapanis(105))
    p.adim(kapanis(110))
    g = gorunum(p.motor, p.birimler)
    p.adim(kapanis(112))
    assert not p.motor.acik                                  # paper girmedi (süzgeç)
    assert [n for n in g.niyetler if n.tur == "ac"] == [], "paper'ın reddedeceği giriş canlıya niyet olarak gitti"


def test_E8_islem_disi_sembolde_canli_niyet_yok_acik_pozisyon_kapat_niyeti_surer():
    """sembol_izleme: bekleyen giriş silinir (canlıya niyet gitmez); açık pozisyonun paper çıkışı yine 'kapat' niyeti olur (kontrol; yeşil)."""
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


def test_E9_ct_coin_veri_yasi_bayatsa_sinyal_yok():
    """ct_kadro: şemadaki coin başına `veri_yasi_sn` hiç okunmuyor; dosya taze ama o coinin verisi 1 gün eskiyse de sinyal üretilir."""
    from motor.canli import ct_kadro as ck
    c = {"coin": "BTC", "long_trader": 8, "short_trader": 1, "net_yon": "long", "nominal_long_usd": 1e6, "nominal_short_usd": 5e5,
         "net_nominal_usd": 5e5, "veri_yasi_sn": 86400}
    assert ck.sinyal_var(c) is None


def test_E10_aday_hesap_dizinleri_cakisamaz(tmp_path):
    """aday_paper.liste_yukle: farklı kimlikler hesap_dizin_adi ile AYNI durum dizinine eşlenebilir ('a:b' ve 'a_b'); ortak durum/.kilit."""
    import json
    from motor.canli import aday_paper as ap
    f = tmp_path / "liste.json"
    f.write_text(json.dumps([{"id": "swing__a:b__x", "kart_yolu": "k.json"}, {"id": "swing__a_b__x", "kart_yolu": "k.json"}]), encoding="utf-8")
    try:
        liste = ap.liste_yukle(f)
    except ap.AdayHatasi:
        return
    dizinler = {str(ap.hesap_dizini(tmp_path, k["id"])) for k in liste}
    assert len(dizinler) == len(liste)


def test_E4_karantinadaki_birimde_canli_giris_niyeti_uretilmez():
    """PaperMotor._giris_izni karantinadaki birimde girişi reddeder (paper pozisyon açmaz); köprü bunu bilmez -> canlı yine girer,
    bir bar sonra 'motor_kapali' ile kapatır."""
    g = gorunum(_sahte_motor(karantina={"B1"}), [_sahte_birim()])
    assert [n for n in g.niyetler if n.tur == "ac"] == []
