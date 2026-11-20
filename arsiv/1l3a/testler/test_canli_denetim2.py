"""Denetim-2 düzeltmeleri (O1 O2 O3 O4 O7 O9 B7 D1 D2 D6 D8 D12 D15). Sahte borsa; ağ yok."""
import pandas as pd
import pytest
from decimal import Decimal as D

from motor.canli import paper as pp
from motor.canli.borsa import calistir as cal
from motor.canli.borsa import canli_ayar as ca
from motor.canli.borsa import motor_kopru as mk
from motor.canli.borsa.binance_futures import BorsaHata
from motor.canli.borsa.canli_yurutucu import MotorGorunumu, PozGorunum, SifirdanBaslamaHatasi, Yurutucu, sifirdan_kontrol
from testler.test_canli_borsa import ARALIK, Ortam, Q, Sahte, T0, ac_niyeti, gor
from motor.canli.borsa.canli_yurutucu import Niyet


class BakiyeBozuk(Sahte):
    def bakiye(self): raise BorsaHata("sunucu 503")


def test_o1_kill_bakiye_okunamasa_da_kapatir(tmp_path):
    b = Sahte()
    e = Ortam(tmp_path, borsa=b)
    e.y.adim(gor([ac_niyeti()]))
    assert b.poz
    e.y.durum["kill"], e.y.durum["kill_neden"] = True, "hesap_kill"
    b.bakiye = lambda: (_ for _ in ()).throw(BorsaHata("503"))
    e.y.adim(gor())
    assert not b.poz                                   # bakiye okunamadı ama kill kapattı


def test_o1_bakiye_okunamazsa_koruma_turu_giris_yok_stop_kurulur(tmp_path):
    b = BakiyeBozuk()
    b.poz["BTCUSDT"] = Q                               # stopsuz pozisyon
    e = Ortam(tmp_path, borsa=b)
    e.y.durum["pozlar"]["K1"] = {"sembol": "BTCUSDT", "bsembol": "BTCUSDT", "yon": 1, "qty": str(Q), "stop": "49000", "hedef": None,
                                 "giris_bar": str(T0), "aralik_sn": 3600, "durum": "acik", "giris_id": "x", "stop_id": None, "hedef_id": None, "stop_deneme": 0}
    e.y.adim(gor([ac_niyeti(kol="K1")], {"K1": PozGorunum("BTCUSDT", 1, D("49000"))}))
    e.y.adim(gor([], {"K1": PozGorunum("BTCUSDT", 1, D("49000"))}))
    assert any(o["tur"] == "STOP_MARKET" for o in b.acik.values())
    assert e.turler().count("canli_koruma_turu") == 1


def test_o1_gercek_kill_risk_izleden_sonra_ayni_turda_kapatir(tmp_path):
    b = Sahte()
    e = Ortam(tmp_path, borsa=b)
    e.y.adim(gor([ac_niyeti()]))
    b.ozs = D("600")                                   # zirve 1000 -> -%40
    e.y.adim(gor())
    assert e.y.durum["kill"] and not b.poz


def test_o2_yalniz_koruma_giris_ve_motor_kapali_yok(tmp_path):
    b = Sahte()
    e = Ortam(tmp_path, borsa=b)
    e.y.adim(gor([ac_niyeti()]))
    assert b.poz
    # paper pozisyonu görmüyor (yarım güncel): normal turda motor_kapali kapatırdı; koruma turunda kapatmaz
    e.zaman[0] += pd.Timedelta(hours=3)
    e.y.adim(gor([ac_niyeti(t=T0 + ARALIK)], son=T0 + 3 * ARALIK), yalniz_koruma=True)
    assert b.poz == {"BTCUSDT": Q}
    assert sum(1 for c in b.cagrilar if c[0] == "piyasa") == 1


def test_o2_yalniz_koruma_kill_kapatir(tmp_path):
    b = Sahte()
    e = Ortam(tmp_path, borsa=b)
    e.y.adim(gor([ac_niyeti()]))
    e.y.durum["kill"] = True
    e.y.adim(gor(), yalniz_koruma=True)
    assert not b.poz


def test_d1_telegram_stoptan_sonra(tmp_path):
    e = Ortam(tmp_path)
    sira = []
    e.bildirimler = []
    orijinal = e.borsa.kosullu
    e.borsa.kosullu = lambda *a, **k: (sira.append("stop"), orijinal(*a, **k))[1]
    e.y._bildir = lambda m: sira.append("tg:" + ("doldu" if "canli_emir_doldu" in m else "diger"))
    e.y.adim(gor([ac_niyeti()]))
    assert sira.index("stop") < sira.index("tg:doldu")


def test_d6_dolmadi_ama_pozisyon_var_yok_denmez(tmp_path):
    class Bozuk(Sahte):
        def piyasa(self, s, yon, q, cid, reduce_only=False):
            o = super().piyasa(s, yon, q, cid, reduce_only)
            return dict(o, dolan=D(0), durum="NEW")
        def sorgula(self, s, cid): return None if cid.startswith("1l3a-G") and not self.cagrilar else dict(self.dolu.get(cid, {}) or {}, dolan=D(0), durum="NEW") if cid in self.dolu else None
        def iptal(self, s, cid, kosullu=True): raise BorsaHata("-2011", belirsiz=True)
    b = Bozuk()
    e = Ortam(tmp_path, borsa=b)
    e.y.adim(gor([ac_niyeti()]))
    assert "K1" in e.y.durum["pozlar"]                 # kayıt silinmedi
    assert any(o["tur"] == "STOP_MARKET" for o in b.acik.values()) or e.y.durum["pozlar"]["K1"]["durum"] == "gonderildi"


def test_d8_eski_stop_iptal_hatasi_turu_kesmez(tmp_path):
    b = Sahte()
    e = Ortam(tmp_path, borsa=b)
    e.y.adim(gor([ac_niyeti()]))
    rec = e.y.durum["pozlar"]["K1"]
    # borsada iki stop: biri farklı miktarlı eski stop (kayıt ID'sinden farklı)
    b.acik["1l3a-eski"] = {"id": "e", "client_id": "1l3a-eski", "sembol": "BTCUSDT", "tur": "STOP_MARKET", "yon": "SELL", "miktar": Q * 2,
                           "tetik": D("48000"), "reduce_only": True, "durum": "NEW", "kosullu": True}
    rec["stop_id"] = None
    for k in [k for k, o in b.acik.items() if k != "1l3a-eski"]:
        b.acik.pop(k)
    b.iptal_hatasi = True
    e.y.adim(gor([], {"K1": PozGorunum("BTCUSDT", 1, D("49000"))}))     # istisna fırlamamalı
    assert "canli_yurutucu_hatasi" not in e.turler() and "canli_iptal_hatasi" in e.turler()


def test_d12_hedef_reddi_bir_kez(tmp_path):
    class H(Sahte):
        def kosullu(self, s, tur, *a, **k):
            if tur == "TAKE_PROFIT_MARKET":
                raise BorsaHata("red", belirsiz=True)
            return super().kosullu(s, tur, *a, **k)
    e = Ortam(tmp_path, borsa=H())
    e.y.adim(gor([ac_niyeti(hedef="52000")]))
    for _ in range(3):
        e.y.adim(gor([], {"K1": PozGorunum("BTCUSDT", 1, D("49000"), D("52000"))}))
    assert e.turler().count("canli_hedef_hatasi") == 1


def test_o3_paper_engeli_bir_kez_kendi_bildiricisiyle(tmp_path):
    e = Ortam(tmp_path)
    g = gor(); g.paper_engel = "kill"
    e.y.adim(g); e.y.adim(g)
    assert e.turler().count("canli_paper_engel") == 1 and any("canli_paper_engel" in b for b in e.bildirimler)
    g2 = gor(); g2.paper_engel = "gunluk_blok"
    e.y.adim(g2)
    assert e.turler().count("canli_paper_engel") == 2


class _M:
    def __init__(self, kill=False, blok=False, giris=None):
        from types import SimpleNamespace as N
        self.kill, self.gunluk_blok, self.acik = kill, blok, {}
        self.risk_oran = 0.01
        self._sk = self._tk = lambda s: 0.0005
        self.k = N(kimlik="K1", sembol="BTCUSDT", giris_emri=giris, cikis_emri=None, grup_payi=1,
                   cikis_ayarlari=N(sabit_r_hedefi=None, kismi=None), mod="sinyal")
        self.b = N(kollar=[self.k], son_t=T0, aralik=ARALIK, tf="1h")


def test_kopru_paper_engel_ve_b7_bozuk_mum():
    m = _M(kill=True)
    assert mk.gorunum(m, [m.b]).paper_engel == "kill"
    assert mk.gorunum(_M(blok=True), [_M().b]).paper_engel == "gunluk_blok"
    m = _M(giris=(1, 49000.0, None, None))
    assert len(mk.gorunum(m, [m.b]).niyetler) == 1
    g = mk.gorunum(m, [m.b], None, lambda s, tf, t: True)
    assert g.niyetler == [] and g.bozuk_semboller == {"BTCUSDT"}


def test_b7_uyari_bir_kez(tmp_path):
    e = Ortam(tmp_path)
    g = gor(); g.bozuk_semboller = {"BTCUSDT"}
    e.y.adim(g); e.y.adim(g)
    assert e.turler().count("canli_bozuk_mum") == 1


def test_d2_transfer_uyarisi(tmp_path):
    class T(Sahte):
        satirlar = []
        def _get(self, yol, params=None):
            assert yol == "/fapi/v1/income" and params["incomeType"] == "TRANSFER"
            return list(self.satirlar)
    b = T()
    e = Ortam(tmp_path, borsa=b)
    e.y.adim(gor())                                    # ilk tur: referans zamanı
    e.zaman[0] += pd.Timedelta(minutes=10)
    b.satirlar = [{"income": "500"}]
    e.y.adim(gor())
    assert "canli_transfer_uyari" in e.turler()


# ---- O9
def test_o9_sifirdan_baslama(tmp_path):
    d = tmp_path / "canli"; d.mkdir()
    yol = d / "yurutucu_a.json"
    sifirdan_kontrol(yol, "S1", {})                    # boş dizin: serbest
    (d / "yurutucu_b.json").write_text("{}")
    with pytest.raises(SifirdanBaslamaHatasi):
        sifirdan_kontrol(yol, "S1", {})
    with pytest.raises(SifirdanBaslamaHatasi):
        sifirdan_kontrol(yol, "S1", {"L3A_SIFIRDAN_IZIN": "S2"})
    sifirdan_kontrol(yol, "S1", {"L3A_SIFIRDAN_IZIN": "S2, S1"})
    with pytest.raises(SifirdanBaslamaHatasi):
        cal.hesap_yukle(d / "hesap_durumu.json", {})
    assert cal.hesap_yukle(d / "hesap_durumu.json", {"L3A_SIFIRDAN_IZIN": "hesap"})["kill"] is False


def test_o9_yurutucu_yukle_reddeder(tmp_path):
    (tmp_path / "baska.jsonl").write_text("x")
    with pytest.raises(SifirdanBaslamaHatasi):
        Ortam(tmp_path)


# ---- O4
class _R:
    def __init__(self, kod, j): self.status_code, self._j, self.headers = kod, j, {}
    def json(self): return self._j


class _O:
    def __init__(self, yanitlar): self.y, self.istek = list(yanitlar), []
    def request(self, m, url, headers=None, timeout=None):
        self.istek.append(url)
        x = self.y.pop(0)
        if isinstance(x, Exception): raise x
        return x


class _S:
    id = "S1"


def _ayar(mod): 
    class A: pass
    a = A(); a.mod = mod; return a


def test_o4_kisit_kontrol(monkeypatch):
    monkeypatch.setattr(ca, "anahtarlar", lambda s, env=None: ("AK", "SK"))
    uyk = []
    ok = _O([ConnectionError("x"), _R(200, {"enableWithdrawals": False, "ipRestrict": True})])
    cal.api_kisit_dogrula(_ayar("canli"), _S(), None, oturum=ok, uyku=uyk.append)
    assert uyk == [10] and ok.istek[0].startswith("https://api.binance.com/sapi/v1/account/apiRestrictions?") and "signature=" in ok.istek[0]
    with pytest.raises(cal.ApiKisitHatasi):
        cal.api_kisit_dogrula(_ayar("canli"), _S(), None, oturum=_O([_R(200, {"enableWithdrawals": True, "ipRestrict": True})]), uyku=uyk.append)
    with pytest.raises(cal.ApiKisitHatasi):
        cal.api_kisit_dogrula(_ayar("canli"), _S(), None, oturum=_O([_R(200, {"enableWithdrawals": False, "ipRestrict": False})]), uyku=uyk.append)
    bos = _O([])
    cal.api_kisit_dogrula(_ayar("testnet"), _S(), None, oturum=bos)      # testnet: sorgu yok
    assert bos.istek == []


# ---- O7 / D15
def test_o7_sonsuz_dene_geri_cekilme():
    n, uyk = [0], []
    def f():
        n[0] += 1
        if n[0] < 8: raise OSError("ag")
        return 7
    assert pp.sonsuz_dene(f, "x", uyku=uyk.append) == 7
    assert uyk == [10, 20, 40, 80, 160, 300, 300]
    with pytest.raises(KeyError):
        pp.sonsuz_dene(lambda: (_ for _ in ()).throw(KeyError("k")), "x", uyku=uyk.append, kalici=lambda e: isinstance(e, KeyError))


def test_d15_kilit_yeniden_dene(tmp_path):
    import fcntl
    yol = tmp_path / ".kilit"
    tutan = open(yol, "w"); fcntl.flock(tutan, fcntl.LOCK_EX)
    uyk = []
    assert pp._kilit_al(yol, uyku=uyk.append, deneme=3, bekle=1) is None and uyk == [1, 1]
    def birak(_): tutan.close()
    k = pp._kilit_al(yol, uyku=birak, deneme=3, bekle=1)
    assert k is not None
    k.close()


# ---- hesap_izle disk hatası kill'i engellemez
def test_hesap_izle_disk_hatasi_kill_engellemez(tmp_path, monkeypatch):
    e = Ortam(tmp_path, ozs="700")
    h = {"surum": 1, "kimlikler": ["S1"], "zirve": "1000", "toplam": "1000", "kill": False, "kill_neden": None}
    import motor.canli.durum as dr
    monkeypatch.setattr(dr, "atomik_yaz_json", lambda *a, **k: (_ for _ in ()).throw(OSError("disk dolu")))
    cal.hesap_izle({"S1": e.y}, h, tmp_path / "c" / "hesap.json")      # 1000 / 5000: hesap kill tetiklenir; yazım hatası yutulur
    assert h["kill"] and e.y.durum["kill"] is True


# ---- Fable denetimi düzeltmeleri (B7 kaynak bayrağı, görünümsüz mutabakat, D3 host yasağı, D2 kısıt, D10 TRADING dışı)
def _rec(stop_id=None):
    return {"sembol": "BTCUSDT", "bsembol": "BTCUSDT", "yon": 1, "qty": str(Q), "stop": "49000", "hedef": None, "giris_bar": str(T0),
            "aralik_sn": 3600, "durum": "acik", "giris_id": "x", "stop_id": stop_id, "hedef_id": None, "stop_deneme": 0}


def test_b7_canli_kaynak_bozuk_bayragi_gercek_yoldan(tmp_path):
    from motor.canli import paper_canli as pc, paper_veri as pv
    from testler.test_paper_motor import TAN
    t = TAN["swing__cci-esik|SOLUSDT|1d"]
    G = 86_400_000
    base = 1_699_920_000_000
    def satir(i, bozuk=False):
        h = 8 if bozuk else 11                                  # yüksek < açılış: bozuk
        return [base + i * G, "10", str(h), "9", "10", "1", base + (i + 1) * G - 1, "1", 1, "0", "0", "0"]
    class Ist:
        rows = [satir(i) for i in range(5)]
        def klines(self, sembol, aralik, bas=None, bit=None, simdi=None):
            return pv.klines_df(self.rows, simdi)
        def funding(self, sembol, bas=None):
            return pd.DataFrame({"oran": []}, index=pd.DatetimeIndex([], tz="UTC"))
    ist = Ist()
    k = pc.CanliKaynak(ist, [t], {"1d": 50}, None)
    gun = lambda i: pd.Timestamp(base + i * G + 30_000, unit="ms", tz="UTC")
    k.baslat(gun(5))                                            # 0..4 kapalı
    assert not k.bozuk_mu("SOLUSDT", "1d")
    ist.rows = [satir(i) for i in range(5)] + [satir(5, bozuk=True)]
    n0 = len(k.mumlar[("SOLUSDT", "1d")])
    k.guncelle(gun(6))                                          # bar 5 bozuk -> atılır, yeni boş; bayrak yine de kaynakta
    assert len(k.mumlar[("SOLUSDT", "1d")]) == n0 and k.bozuk_mu("SOLUSDT", "1d")
    m = _M(giris=(1, 49000.0, None, None))
    g = mk.gorunum(m, [m.b], None, lambda s, tf, t_: k.bozuk_mu("SOLUSDT", "1d"))      # BTCUSDT kolu SOLUSDT serisine eşlenmiş sayılır
    assert g.niyetler == [] and g.bozuk_semboller == {"BTCUSDT"}   # giriş atlandı
    ist.rows = [satir(i) for i in range(6)]
    k.son_kontrol[("SOLUSDT", "1d")] = gun(0)
    k.guncelle(gun(7))                                          # sağlam çekim: bayrak temizlenir
    assert not k.bozuk_mu("SOLUSDT", "1d") and len(k.mumlar[("SOLUSDT", "1d")]) == n0 + 1


def test_gorunumsuz_koruma_kayitli_pozisyon_bilinmeyen_degil_stop_kurulur(tmp_path):
    b = Sahte()
    b.poz["BTCUSDT"] = Q
    e = Ortam(tmp_path, borsa=b)
    e.y.durum["pozlar"]["K1"] = _rec()
    e.y.adim(MotorGorunumu(), yalniz_koruma=True)               # calistir.py görünüm hatası yolu
    assert any(o["tur"] == "STOP_MARKET" for o in b.acik.values())
    assert not any("BİLİNMEYEN" in m for _, m in e.olaylar)
    b2 = Sahte(); b2.poz["BTCUSDT"] = Q                         # kayıtsız pozisyon HÂLÂ bilinmeyen
    e2 = Ortam(tmp_path / "b", borsa=b2) if (tmp_path / "b").mkdir() is None else None
    e2.y.adim(MotorGorunumu(), yalniz_koruma=True)
    assert any("BİLİNMEYEN" in m for _, m in e2.olaylar)


def test_d3_yasak_host_bazli_ve_dosyada_kalici(tmp_path):
    import time
    from motor.canli.borsa import binance_futures as bf
    bf.yasak_sifirla()
    try:
        d = tmp_path / "yasak.json"
        bf.yasak_ayarla(time.time() + 100, d, "testnet.binancefuture.com")
        class O:
            def request(self, *a, **k): raise AssertionError("istek gitmemeli")
        bf.BinanceFutures("canli", "k" * 10, "g" * 10, oturum=O(), yasak_dosyasi=d)._agirlik_bekle()     # fapi etkilenmez
        from motor.canli import paper_veri as pv
        assert pv.FapiIstemci(oturum=O()).host == "fapi.binance.com" and bf.yasak_oku("fapi.binance.com") == 0.0
        bf.yasak_sifirla()                                       # "yeniden başlatma": dosyadan yüklenir
        c = bf.BinanceFutures("testnet", "k" * 10, "g" * 10, oturum=O(), yasak_dosyasi=d)
        with pytest.raises(bf.BorsaYasagi) as ei:
            c._agirlik_bekle()
        assert ei.value.suruyor and ei.value.bitis > time.time()
    finally:
        bf.yasak_sifirla()


def test_d3_suren_yasak_telegrami_pencere_basina_bir_kez(tmp_path):
    from motor.canli.borsa import canli_yurutucu as cy
    from motor.canli.borsa.binance_futures import BorsaYasagi
    cy._YASAK_BILDIRILEN.clear()
    class Y(Sahte):
        def pozisyonlar(self):
            e = BorsaYasagi("IP yasağı/rate limit sürüyor (100 sn)", http=418); e.bitis, e.suruyor = 1234567.0, True
            raise e
    e = Ortam(tmp_path, borsa=Y())
    for _ in range(3):
        e.y.adim(gor())
    assert e.turler().count("canli_yurutucu_hatasi") == 3 and sum("canli_yurutucu_hatasi" in x for x in e.bildirimler) == 1
    cy._YASAK_BILDIRILEN.clear()


def test_d2_transfer_sorgusu_basarisizsa_da_5dk_kisiti(tmp_path):
    class T(Sahte):
        n = 0
        def _get(self, yol, params=None):
            T.n += 1
            raise BorsaHata("503")
    e = Ortam(tmp_path, borsa=T())
    e.y.adim(gor())                                    # referans
    e.zaman[0] += pd.Timedelta(minutes=10); e.y.adim(gor())
    assert T.n == 1
    e.zaman[0] += pd.Timedelta(minutes=1); e.y.adim(gor())
    assert T.n == 1                                    # kısıt sürüyor
    e.zaman[0] += pd.Timedelta(minutes=5); e.y.adim(gor())
    assert T.n == 2


def test_d10_trading_disi_sembolde_acik_pozisyon_her_tur_hata_vermez(tmp_path):
    from testler.test_canli_borsa import bilgi
    b = Sahte()
    e = Ortam(tmp_path, borsa=b)
    e.y.adim(gor([ac_niyeti()]))                       # pozisyon + stop (kural önbelleğe girdi)
    assert "K1" in e.y.durum["pozlar"]
    halt = bilgi(); halt["symbols"][0]["status"] = "BREAK"
    e.y.bilgi = halt
    e.y.kurallar.clear()                               # yeniden başlatma: önbellek yok -> gevşek çıkarım
    for _ in range(3):
        e.y.adim(gor(pozlar={"K1": PozGorunum("BTCUSDT", 1, D("49000"))}))
    assert "canli_yurutucu_hatasi" not in e.turler()
    assert sum("TRADING değil" in m for _, m in e.olaylar) == 1
    e.y.bilgi = {"symbols": []}; e.y.kurallar.clear(); e.y._uyari_sil("kural_poz:")   # kural hiç yok: bir kez uyarı, hata yok
    for _ in range(2):
        e.y.adim(gor(pozlar={"K1": PozGorunum("BTCUSDT", 1, D("49000"))}))
    assert "canli_yurutucu_hatasi" not in e.turler()
    assert sum("kuralı alınamadı" in m for _, m in e.olaylar) == 1
