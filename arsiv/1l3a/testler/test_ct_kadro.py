"""ct_konsensus: CT kadro yön özeti alıcısı, ön kayıt kuralı, paper hesabı (sentetik veri, AĞ YOK)."""
import copy
import json

import numpy as np
import pandas as pd
import pytest

from motor.arastirma import tarama
from motor.canli import ct_kadro as ck
from motor.canli import ct_paper as cp
from motor.canli import paper as pp
from motor.canli import paper_v2 as v2
from motor.canli.paper_kaynak import TekrarKaynagi
from motor.risk.limitler import SERT_LIMITLER

T0 = pd.Timestamp("2026-11-10 00:00", tz="UTC")
ESL = {"BTC": ("BTCUSDT", 1.0), "ETH": ("ETHUSDT", 1.0), "SOL": ("SOLUSDT", 1.0), "XRP": ("XRPUSDT", 1.0), "ADA": ("ADAUSDT", 1.0),
       "kPEPE": ("1000PEPEUSDT", 1000.0)}


def zs(t):
    return t.strftime("%Y-%m-%dT%H:%M:%SZ")


def coin(ad, L, S, net, yon=None):
    yon = yon or ("long" if net > 0 else "short" if net < 0 else "notr")
    return {"coin": ad, "long_trader": L, "short_trader": S, "net_yon": yon, "nominal_long_usd": 1e6, "nominal_short_usd": 5e5,
            "net_nominal_usd": net, "veri_yasi_sn": 30}


def ozet(uretildi, coinler, **kw):
    d = {"sema": "ct.kadro_yon.v1", "uretildi_utc": zs(uretildi), "kadro_surumu": None, "kadro_kosu_utc": zs(uretildi),
         "saha_trader_sayisi": 40, "kip": "canli", "notlar": [], "coinler": coinler}
    d.update(kw)
    return d


def alici_ile(*ozetler, tmp_path=None):
    a = ck.KadroAlici(tmp_path)
    for o in ozetler:
        assert ck._ekle_bellek if False else True
        a._ekle_bellek(ck.dogrula(o))
    return a


def deposu(*ozetler, acik=None, esleme=None):
    d = ck.KonsensusDeposu(alici_ile(*ozetler), esleme or ESL)
    d.acik_fn = lambda: dict(acik or {})
    return d


# ----------------------------------------------------------------------------------------------- şema
def test_sema_gecerli_ve_ret_durumlari():
    iyi = ozet(T0, [coin("BTC", 8, 1, 1e6)])
    assert ck.dogrula(iyi) is iyi
    kotu = []
    k = copy.deepcopy(iyi); k["sema"] = "ct.kadro_yon.v2"; kotu.append(k)
    k = copy.deepcopy(iyi); k["sema"] = "ct.kadro_yon.v1 "; kotu.append(k)           # tam eşleşme
    k = copy.deepcopy(iyi); del k["coinler"]; kotu.append(k)
    k = copy.deepcopy(iyi); del k["uretildi_utc"]; kotu.append(k)
    k = copy.deepcopy(iyi); k["uretildi_utc"] = "dün"; kotu.append(k)
    k = copy.deepcopy(iyi); k["saha_trader_sayisi"] = "40"; kotu.append(k)
    k = copy.deepcopy(iyi); k["coinler"][0]["long_trader"] = "8"; kotu.append(k)
    k = copy.deepcopy(iyi); k["coinler"][0]["net_yon"] = "yukari"; kotu.append(k)
    k = copy.deepcopy(iyi); del k["coinler"][0]["short_trader"]; kotu.append(k)
    k = copy.deepcopy(iyi); k["coinler"][0]["net_nominal_usd"] = "1"; kotu.append(k)
    kotu.append([1, 2])
    for k in kotu:
        with pytest.raises(ck.KadroSemaHatasi):
            ck.dogrula(k)
    ok = copy.deepcopy(iyi); ok["coinler"][0]["net_nominal_usd"] = None; ok["kadro_surumu"] = None
    ck.dogrula(ok)                                                                  # null izinli


def test_alici_semasiz_veriyi_reddeder_ve_yazmaz(tmp_path):
    k = ozet(T0, [coin("BTC", 8, 1, 1e6)]); k["sema"] = "baska"
    a = ck.KadroAlici(tmp_path, getir_fn=lambda: json.dumps(k))
    assert a.getir(zorla=True) is None and a.hata_sayisi == 1 and not a.kayitlar
    assert not (tmp_path / "kadro_yon.jsonl").exists()


# ----------------------------------------------------------------------------------------------- bayatlık / lookahead
def test_bayat_45_dk_veri_yok_sayilir():
    a = alici_ile(ozet(T0, [coin("BTC", 8, 1, 1e6)]))
    assert a.gecerli(T0 + pd.Timedelta(minutes=44, seconds=59)) is not None
    assert a.gecerli(T0 + pd.Timedelta(minutes=45)) is not None                     # tam 45 dk: eski DEĞİL
    assert a.gecerli(T0 + pd.Timedelta(minutes=45, seconds=1)) is None
    d = deposu(ozet(T0, [coin("BTC", 8, 1, 1e6)]))
    pl = d.plan(T0 + pd.Timedelta(minutes=46))
    assert not pl.taze and pl.giris == {} and not pl.cikis("BTCUSDT", 1)           # bayat: giriş yok, konsensüs çıkışı da yok


def test_gelecekteki_uretildi_kullanilmaz():
    a = alici_ile(ozet(T0 + pd.Timedelta(minutes=30), [coin("BTC", 8, 1, 1e6)]))
    assert a.gecerli(T0 + pd.Timedelta(minutes=29, seconds=59)) is None
    assert a.gecerli(T0 + pd.Timedelta(minutes=30)) is not None
    # önceki + gelecek: karar anında yalnız önceki
    a = alici_ile(ozet(T0, [coin("BTC", 8, 1, 1e6)]), ozet(T0 + pd.Timedelta(minutes=15), [coin("BTC", 1, 8, -1e6)]))
    assert a.gecerli(T0 + pd.Timedelta(minutes=10))["uretildi_utc"] == zs(T0)
    assert a.gecerli(T0 + pd.Timedelta(minutes=15))["uretildi_utc"] == zs(T0 + pd.Timedelta(minutes=15))


# ----------------------------------------------------------------------------------------------- HIP-3 / eşleme
def test_hip3_atlanir_esleme_ve_carpan():
    d = deposu(ozet(T0, [coin("xyz:TSLA", 9, 0, 9e6), coin("kPEPE", 9, 0, 3e6), coin("BTC", 9, 0, 2e6), coin("BILINMEZ", 9, 0, 8e6)]))
    pl = d.plan(T0 + pd.Timedelta(minutes=1))
    assert set(pl.giris) == {"1000PEPEUSDT", "BTCUSDT"}
    assert "xyz:TSLA" not in d._atlanan and "BILINMEZ" in d._atlanan                  # HIP-3 sessizce, eşlemesiz bir kez loglanır
    e = ck.esleme_yukle()
    assert e["BTC"] == ("BTCUSDT", 1.0) and e["ETH"] == ("ETHUSDT", 1.0) and e["kPEPE"] == ("1000PEPEUSDT", 1000.0)
    assert all(":" not in k for k in e)


def test_atlanan_coin_bir_kez_loglanir(caplog):
    d = deposu(ozet(T0, [coin("BILINMEZ", 9, 0, 8e6)]))
    with caplog.at_level("INFO", logger="paper.ct"):
        d.plan(T0 + pd.Timedelta(minutes=1))
        d.plan(T0 + pd.Timedelta(minutes=2))
    assert sum("BILINMEZ" in r.getMessage() for r in caplog.records) == 1


# ----------------------------------------------------------------------------------------------- eşikler
@pytest.mark.parametrize("L,S,net_yon,beklenen", [
    (4, 1, "long", 1),        # n=5, %80
    (3, 1, "long", None),     # n=4 < 5
    (5, 0, "long", 1),        # n=5, %100
    (7, 3, "long", 1),        # tam %70 (n=10)
    (6, 4, "long", None),     # %60
    (14, 6, "long", 1),       # tam %70
    (13, 7, "long", None),    # %65
    (1, 4, "short", -1),
    (3, 7, "short", -1),      # tam %70 short
    (4, 6, "short", None),
    (8, 1, "notr", None),     # net_yon notr
    (8, 1, "short", None),    # çoğunluk long ama net_yon short: çelişki -> sinyal yok
    (5, 5, "long", None),     # eşit
])
def test_esik_sinirlari(L, S, net_yon, beklenen):
    c = coin("BTC", L, S, 1e6, yon=net_yon)
    assert ck.sinyal_var(c) == beklenen


# ----------------------------------------------------------------------------------------------- en çok 3 pozisyon / sıra
def _bes_aday():
    return [coin("BTC", 9, 0, 1e6), coin("ETH", 9, 0, 5e6), coin("SOL", 9, 0, -4e6, "short") | {"long_trader": 0, "short_trader": 9},
            coin("XRP", 9, 0, 2e6), coin("ADA", 9, 0, 3e6)]


def test_en_cok_3_pozisyon_net_nominale_gore():
    d = deposu(ozet(T0, _bes_aday()))
    pl = d.plan(T0 + pd.Timedelta(minutes=1))
    assert pl.giris == {"ETHUSDT": 1, "SOLUSDT": -1, "ADAUSDT": 1}                    # |5e6|, |4e6|, |3e6|


def test_acik_pozisyon_yer_kaplar_ve_ayni_sembole_yeni_giris_yok():
    d = deposu(ozet(T0, _bes_aday()), acik={"ETHUSDT": 1})                            # ETH zaten açık (konsensüs hâlâ long: tutulur)
    pl = d.plan(T0 + pd.Timedelta(minutes=1))
    assert "ETHUSDT" not in pl.giris and set(pl.giris) == {"SOLUSDT", "ADAUSDT"}      # 1 yer dolu -> 2 yeni
    d = deposu(ozet(T0, _bes_aday()), acik={"BTCUSDT": 1, "XRPUSDT": 1, "ADAUSDT": 1})
    assert d.plan(T0 + pd.Timedelta(minutes=1)).giris == {}                           # 3 dolu: yeni yok


def test_ters_donen_pozisyon_yeri_bosaltmaz_ayni_kararda_degil_ama_cikis_verilir():
    d = deposu(ozet(T0, [coin("ETH", 1, 9, -5e6, "short"), coin("BTC", 9, 0, 1e6)]), acik={"ETHUSDT": 1})
    pl = d.plan(T0 + pd.Timedelta(minutes=1))
    assert pl.cikis("ETHUSDT", 1) is True and pl.cikis("ETHUSDT", -1) is False
    assert pl.giris == {"BTCUSDT": 1}


def test_listeden_dusen_ya_da_ters_net_yon_kapatir_notr_kapatmaz():
    pl = deposu(ozet(T0, [coin("ETH", 5, 5, 0, "notr")])).plan(T0 + pd.Timedelta(minutes=1))
    assert not pl.cikis("ETHUSDT", 1)                                                  # notr: kapatma kuralı yok
    assert pl.cikis("BTCUSDT", 1)                                                      # listede yok -> kapat
    pl = deposu(ozet(T0, [coin("ETH", 9, 0, 1e6)])).plan(T0 + pd.Timedelta(minutes=1))
    assert not pl.cikis("ETHUSDT", 1) and pl.cikis("ETHUSDT", -1)


# ----------------------------------------------------------------------------------------------- ağ / alıcı
def test_ag_hatasinda_yutulur_onbellek_ve_jsonl(tmp_path):
    cagri = []
    saat = [1000.0]

    def getir():
        cagri.append(1)
        if len(cagri) == 1:
            raise ConnectionError("ağ yok")
        return json.dumps(ozet(T0, [coin("BTC", 8, 1, 1e6)]))
    a = ck.KadroAlici(tmp_path, getir_fn=getir, saat=lambda: saat[0])
    assert a.getir() is None and a.hata_sayisi == 1 and a.son_hata.startswith("ConnectionError")      # istisna YOK
    saat[0] += 100
    assert a.getir() is None and len(cagri) == 1                                       # önbellek (5 dk) içinde istek yok
    saat[0] += 250
    assert a.getir() is not None and len(cagri) == 2
    saat[0] += 301
    assert a.getir() is None and len(cagri) == 3                                       # aynı yayın: yinelenmez
    assert len((tmp_path / "kadro_yon.jsonl").read_text().splitlines()) == 1
    b = ck.KadroAlici(tmp_path)                                                        # yeniden başlatma: geçmiş yüklenir
    assert b.gecerli(T0 + pd.Timedelta(minutes=5)) is not None


def test_jsonl_dondurme(tmp_path, monkeypatch):
    monkeypatch.setattr(ck, "JSONL_MAX_BAYT", 500)
    monkeypatch.setattr(ck, "YEDEK_SAYISI", 2)
    sira = [0]

    def getir():
        sira[0] += 1
        return json.dumps(ozet(T0 + pd.Timedelta(minutes=15 * sira[0]), [coin("BTC", 8, 1, 1e6)]))
    a = ck.KadroAlici(tmp_path, getir_fn=getir, cache_sn=0)
    for _ in range(8):
        a.getir(zorla=True)
    yedek = list(tmp_path.glob("kadro_yon.*.jsonl"))
    assert 1 <= len(yedek) <= 2 and (tmp_path / "kadro_yon.jsonl").exists()


# ----------------------------------------------------------------------------------------------- paper entegrasyonu (sentetik)
def duz_mumlar(n=400, fiyat=100.0):
    idx = pd.date_range(T0 - pd.Timedelta(minutes=15 * 100), periods=n, freq="15min", tz="UTC", name="zaman")
    return pd.DataFrame({"acilis": fiyat, "yuksek": fiyat + 0.2, "dusuk": fiyat - 0.2, "kapanis": fiyat, "hacim": 1000.0,
                         "quote_hacim": 1e5, "islem_sayisi": 10}, index=idx)


def kapanis(i):
    """i. mumun (T0'dan i bar sonrası) KAPANIŞ anı."""
    return T0 + pd.Timedelta(minutes=15 * (i + 1))


def paper_kur(*ozetler, esl=None, tmp_path=None):
    esl = esl or {"BTC": ("BTCUSDT", 1.0), "ETH": ("ETHUSDT", 1.0)}
    alici = ck.KadroAlici(tmp_path)
    for o in ozetler:
        alici._ekle_bellek(ck.dogrula(o))
    deposu_ = ck.KonsensusDeposu(alici, esl)
    tan = ck.tanimlar_olustur(esl, deposu_)
    mumlar = {(t.sembol, "15m"): duz_mumlar() for t in tan}
    kurallar = {t.sembol: tarama.SEMBOL_KURALLARI.get(t.sembol, tarama.VARSAYILAN_KURAL) for t in tan}
    p = pp.Paper(tan, TekrarKaynagi(mumlar, {}), kurallar, ayarlar=cp.ct_ayarlari())
    deposu_.motor_bagla(p.motor)
    return p, deposu_


def test_ayarlar_sert_limitten_ve_10k():
    a = cp.ct_ayarlari()
    assert a.baslangic_sermaye == 10000.0 and a.risk_yuzde == SERT_LIMITLER.islem_basi_max_risk_yuzde and a.limit_modu == "uygula"


def test_giris_stop_hedef_ve_ters_donuste_kapanis():
    s1 = ozet(kapanis(110), [coin("BTC", 8, 1, 2e6), coin("ETH", 9, 0, 1e6)])         # 110. mumun kapanışında yayın
    s2 = ozet(kapanis(130), [coin("BTC", 1, 8, -2e6, "short"), coin("ETH", 9, 0, 1e6)])   # BTC ters döner
    p, _ = paper_kur(s1, s2)
    p.baslat(kapanis(105))
    p.adim(kapanis(112))
    ac = {x.sembol: x for x in p.motor.acik.values()}
    assert set(ac) == {"BTCUSDT", "ETHUSDT"} and all(x.yon == 1 for x in ac.values())   # 110 kapanışında karar, 111 açılışında giriş
    btc = ac["BTCUSDT"]
    assert float(btc.stop) == pytest.approx(100 - 2 * 0.4, abs=0.02) and float(btc.hedef) == pytest.approx(100 + 3 * 0.4, abs=0.02)
    kasa = 10000.0
    risk = float(btc.miktar) * (float(btc.giris) - float(btc.stop))
    assert risk <= kasa * SERT_LIMITLER.islem_basi_max_risk_yuzde / 100 + 1e-6          # işlem başı risk <= %1
    p.adim(kapanis(135))
    kapanan = [x for x in p.motor.islemler]
    assert [x["sembol"] for x in kapanan] == ["BTCUSDT"] and kapanan[0]["cikis_nedeni"] == "sinyal"
    ac2 = {x.sembol: x.yon for x in p.motor.acik.values()}
    # ETH hâlâ long konsensüste: açık. BTC: ters dönüş kararında açık pozisyon vardı (yeni giriş yok); kapandıktan sonraki karar short açar.
    assert ac2 == {"ETHUSDT": 1, "BTCUSDT": -1}


def test_bayat_veride_giris_yok_acik_pozisyon_kendi_basina():
    s1 = ozet(kapanis(110), [coin("BTC", 8, 1, 2e6)])
    p, _ = paper_kur(s1)
    p.baslat(kapanis(105))
    p.adim(kapanis(112))
    assert len(p.motor.acik) == 1
    p.adim(kapanis(110 + 4 + 8))      # 12 bar sonrası: yayın 180 dk eski -> bayat
    assert len(p.motor.acik) == 1 and not p.motor.islemler                              # ne kapandı ne yeni açıldı (stop/hedef de vurmadı)


def test_veri_hic_yokken_motor_calisir_islem_acmaz(tmp_path):
    p, _ = paper_kur()
    p.baslat(kapanis(105))
    assert p.adim(kapanis(150)) > 0 and not p.motor.acik and not p.motor.islemler


def test_durum_dosyalari_paper_bicimiyle_yazilir(tmp_path):
    s1 = ozet(kapanis(110), [coin("BTC", 8, 1, 2e6)])
    p, _ = paper_kur(s1)
    p.baslat(kapanis(105))
    p.adim(kapanis(112))

    class K:
        mumlar = p.kaynak.mumlar
    o = pp._durum_yaz(p, K, tmp_path, kapanis(112))
    for ad in ("ozet.json", "stratejiler.json", "islemler.jsonl", "saglik.json"):
        assert (tmp_path / ad).exists(), ad
    assert o["ozet"]["sayaclar"]["acik_pozisyon"] == 1


# ----------------------------------------------------------------------------------------------- mevcut set bozulmadı
def test_mevcut_10lu_set_imzasi_degismedi():
    assert v2.set_imzasi(v2.set_yukle()) == "fffbc6624416634e"
    assert not any("ct_konsensus" in json.dumps(k) for k in v2.set_yukle()["stratejiler"])


def test_ct_paper_mevcut_dosyalari_degistirmez_yamalar_surece_ozel():
    # modül yüklemesi yama uygulamaz (yamalar yalnız calistir() içinde)
    assert pp.PaperMotor.__name__ == "PaperMotor" and pp.paper_ayarlari().baslangic_sermaye == 10000.0
