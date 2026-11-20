"""Paper v2 ODAK seti (2026-11-14 kullanıcı kararı, DURUM.md "ODAK LİSTESİ"): 20 -> 10 hesap; 7 panoda görünür + 3 gizli çalışan; 10 durdurulan.
Gerçek set dosyası (10 kayıt, imza, görünürlük) + sentetik veriyle: 20 -> 10 tek seferlik daralma (kalan 10 hesap AYNEN, durdurulanlar arşivde),
başka imza açık hata, pano gizli hesabı HİÇ göstermez, toplam yalnız görünür hesaplardan. Ağ/gerçek veri yok."""
import copy
import json
import re
from decimal import Decimal
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd
import pytest

from motor.canli import durum as dr
from motor.canli import guven as gv
from motor.canli import pano
from motor.canli import paper as pp
from motor.canli import paper_v2 as v2
from motor.canli import paper_veri as pv
from testler.test_paper_v2 import OrtalamaTrend, SEM, kos, set20, tanim, veri

KOK = Path(__file__).resolve().parents[1]
IMZA10 = "fffbc6624416634e"
IMZA20 = "be84a61831ca9bbc"
ESKI_IMZA, ESKI16_IMZA = "985f914d0bb6b643", "4c22e27149b65a14"
GORUNUR = ["dis__gauss-stoch-eth", "HAM:X005:664#v1", "dis__hma-atr-rider", "dis__ewo-ema-ofset", "dis__e0v1en", "HAM:X005:705"]
GIZLI = ["dis__lube", "HAM:B001:574#v1", "HAM:X005:730#v2", "HAM:B001:670#v1"]
DURDURULAN = ["dis__jt-awesome-osilator", "dis__uc-ortalama-boga-sma60", "dis__voltarget-trend", "dis__haftalik-macd-gunluk-ma", "pf__sabit_sepet",
              "HAM:X005:301#v1", "HAM:X005:138#v3", "HAM:X005:259#v1", "HAM:X005:793#v1", "HAM:B001:538#v1"]
SIMDI_PANO = datetime(2026, 11, 14, 12, 0, tzinfo=timezone.utc)


# ---------------------------------------------------------------------------- gerçek set
def test_gercek_set_10_hesap_7_gorunur_3_gizli_705_yedek():
    s = v2.set_yukle()
    ad = [v2.hesap_adi(k) for k in s["stratejiler"]]
    assert len(ad) == 10 and set(ad) == set(GORUNUR) | set(GIZLI)
    assert {v2.hesap_adi(k) for k in s["stratejiler"] if v2.gorunur_mu(k)} == set(GORUNUR) and len(GORUNUR) == 6
    assert {v2.hesap_adi(k) for k in s["stratejiler"] if not v2.gorunur_mu(k)} == set(GIZLI)
    assert [v2.hesap_adi(k) for k in s["stratejiler"] if k.get("yedek")] == ["HAM:X005:705"]
    assert not set(ad) & set(DURDURULAN)
    assert s["s"] == 0.5 and s["baslangic_sermaye"] == 10000
    assert "2026-11-14" in s["kaynak"] and "10 hesap" in s["kaynak"]
    # etiketler değişmedi (canlı onkontrol bunlara bakar)
    et = {v2.hesap_adi(k): k["etiket"] for k in s["stratejiler"]}
    assert et["HAM:X005:705"] == "kapanis_aday" and et["HAM:X005:730#v2"] == "kapanis_aday_ek" and et["dis__ewo-ema-ofset"] == "dogrulandi"


def test_yeni_imza_ve_20li_imza_sabiti_donmus_kopyadan_dogrulanir():
    s = v2.set_yukle()
    assert v2.set_imzasi(s) == IMZA10
    s20 = set20()
    assert len(s20["stratejiler"]) == 20 and v2.set_imzasi(s20) == IMZA20 == v2.IMZA20
    assert {v2.hesap_adi(k) for k in s20["stratejiler"]} == set(GORUNUR) | set(GIZLI) | set(DURDURULAN)
    assert set(v2.DURDURULAN_20261114) == set(DURDURULAN) and len(v2.DURDURULAN_20261114) == 10
    # görünürlük işareti imzaya girmez (yalnız gösterim): aynı set görünürlük değişse de aynı imza
    t = copy.deepcopy(s)
    t["stratejiler"][2]["gorunur"] = True
    assert v2.set_imzasi(t) == IMZA10
    # 10 hesabın tanımları 20'li setteki karşılıklarıyla AYNI (risk/limit/ayar mantığı değişmedi)
    t10 = {t.kimlik: t for t in v2.tanimlari_yukle(s)}
    t20 = {t.kimlik: t for t in v2.tanimlari_yukle(s20)}
    for k, a in t10.items():
        b = t20[k]
        assert (a.kimlik, a.kol, a.tf, tuple(a.evren), a.etiket, a.ayar, a.grup_payi, a.ajan) == (b.kimlik, b.kol, b.tf, tuple(b.evren), b.etiket, b.ayar, b.grup_payi, b.ajan)
        assert v2.hesap_ayarlari(a, s) == v2.hesap_ayarlari(b, s20)


def test_set_gorunur_ve_yedek_alani_bool_olmali(tmp_path):
    s = v2.set_yukle()
    yol = tmp_path / "set.json"
    s2 = copy.deepcopy(s)
    s2["stratejiler"][0]["gorunur"] = "hayir"
    yol.write_text(json.dumps(s2))
    with pytest.raises(v2.PaperV2Hatasi, match="true/false"):
        v2.set_yukle(yol)
    s3 = copy.deepcopy(s)
    for k in s3["stratejiler"]:
        k["gorunur"] = False
    yol.write_text(json.dumps(s3))
    with pytest.raises(v2.PaperV2Hatasi, match="görünür hesap yok"):
        v2.set_yukle(yol)


def test_butunluk_10_hesap_kayitla_eslesir_sert_limitler_ayni_arsiv_kayitlari_durur():
    mal = v2.cevrimdisi_maliyet_modeli()
    assert len(mal) == 10 and set(mal) == set(GORUNUR) | set(GIZLI)
    assert gv.KAYIT_YOLU_V2.name == "butunluk_kayit_v2_10.json" and gv.PROFILLER["v2"]["kayit_adi"] == "butunluk_kayit_v2_10.json"
    b = gv.butunluk("paper", "2026-11-14T00:00:00Z", None, profil="v2", maliyet=mal, onbellek_sn=0)
    assert b["genel_durum"] == "eslesti", [(x["id"], x["durum"]) for x in b["dosyalar"] + b["sanal"] if x["durum"] != "eslesti"]
    for ad in ("butunluk_kayit_v2_16.json", "butunluk_kayit_v2_20.json"):
        assert (KOK / "stratejiler" / ad).exists()
    sl = lambda p: json.loads(p.read_text())["sanal"]["sert_limitler"]["sha256"]          # noqa: E731
    assert sl(KOK / "stratejiler/butunluk_kayit_v2_10.json") == gv.sha256_sozluk(gv.sert_limitler())                       # güncel kayıt: yeni limit (günlük %5)
    assert sl(KOK / "stratejiler/butunluk_kayit_v2_20.json") == gv.sha256_sozluk({**gv.sert_limitler(), "gunluk_max_kayip_yuzde": 3.0})   # arşiv: eski (%3), mühürlü


def test_canli_onkontrol_kapanis_etiketleri_aynen_reddedilir():
    from types import SimpleNamespace as NS
    from motor.canli.borsa import calistir as cal
    from motor.canli.borsa.motor_kopru import CanliDesteklemiyorHatasi
    for k in ("HAM:X005:664#v1", "HAM:X005:705", "HAM:B001:670#v1", "HAM:B001:574#v1", "HAM:X005:730#v2"):
        with pytest.raises(CanliDesteklemiyorHatasi, match="kapanis_aday|12 hafta"):
            cal.onkontrol(NS(stratejiler=[NS(id=k)]))
    cal.onkontrol(NS(stratejiler=[NS(id="dis__e0v1en")]))


# ---------------------------------------------------------------------------- sentetik: 20 -> 10 daralma
def _kayit(kimlik, gorunur=True, yedek=False, grup=None):
    k = {"strateji": kimlik, "tf": "1d", "evren": "genel", "tur": "tek", "etiket": "iyi_gorundu"}
    if grup:
        k["grup"] = grup
    if not gorunur:
        k["gorunur"] = False
    if yedek:
        k["yedek"] = True
    return k


def _set(*kayitlar):
    return {"surum": 1, "ad": v2.SET_ADI, "s": 0.5, "baslangic_sermaye": 10000, "stratejiler": list(kayitlar)}


def _kur(monkeypatch):
    """a, b görünür (b yedek), g gizli; c, d durdurulan. IMZA20/DURDURULAN sabitleri 'c','d'li 5'li sete bağlanır."""
    mum = veri()
    ix = mum[("BTCUSDT", "1d")].index
    ta = {"a": tanim("a", SEM, OrtalamaTrend(n=10)), "b": tanim("b", SEM, OrtalamaTrend(n=15)), "g": tanim("g", SEM[:2], OrtalamaTrend(n=20)),
          "c": tanim("c", SEM, OrtalamaTrend(n=12)), "d": tanim("d", SEM[:2], OrtalamaTrend(n=8))}
    s_eski = _set(_kayit("a"), _kayit("b"), _kayit("g"), _kayit("c"), _kayit("d"))
    s_yeni = _set(_kayit("a"), _kayit("b", yedek=True), _kayit("g", gorunur=False))
    monkeypatch.setattr(v2, "IMZA20", v2.set_imzasi(s_eski))
    monkeypatch.setattr(v2, "DURDURULAN_20261114", ("c", "d"))
    return mum, ix, ta, s_eski, s_yeni


def _kasa(ta, adlar, mum, s):
    return v2.kasalar_kur([ta[k] for k in adlar], mum, {}, s, pencere={"1d": 300})


def test_daralma_kalan_hesaplar_aynen_durdurulanlar_arsivde(tmp_path, monkeypatch):
    mum, ix, ta, s_eski, s_yeni = _kur(monkeypatch)
    yol = tmp_path / "paper_state.json"
    p1 = _kasa(ta, "abgcd", mum, s_eski)
    p1.baslat(ix[120])
    p1.adim(ix[160])
    p1.olay_ekle("deneme", "[c] durdurulacak hesabın olayı", ix[160], False)
    p1.olay_ekle("deneme", "[a] kalan hesabın olayı", ix[160], False)
    p1.kaydet(yol)
    v2.durum_yaz(p1, p1.kaynak, tmp_path, ix[160] + pd.Timedelta(days=1), kaynak_adi="paper", veri_dizini=tmp_path)     # hesaplar/<id>/ klasörleri oluşsun
    assert (tmp_path / "hesaplar" / "c" / "ozet.json").exists()
    ham1 = json.loads(yol.read_text())
    assert ham1["set_imza"] == v2.set_imzasi(s_eski) and set(ham1["hesaplar"]) == set("abgcd")
    # yeni set: yalnız a, b, g
    p2 = _kasa(ta, "abg", mum, s_yeni)
    assert p2.yukle(yol) is True and p2.yeni_hesaplar == [] and set(p2.arsivlenecek) == {"c", "d"}
    assert p2.durdurulanlari_arsivle(tmp_path) == ["c", "d"] and p2.arsivlenecek == {}
    p2.kaydet(yol)
    ham2 = json.loads(yol.read_text())
    assert ham2["set_imza"] == v2.set_imzasi(s_yeni) and set(ham2["hesaplar"]) == set("abg")
    for k in "abg":                                            # kalan hesaplar: kayıt AYNEN (konum, işlem, özsermaye)
        assert ham2["hesaplar"][k] == ham1["hesaplar"][k], k
        assert p2.hesaplar[k].motor.ozsermaye() == p1.hesaplar[k].motor.ozsermaye()
    ark = tmp_path / v2.ARSIV_DIZINI
    assert sorted(x.name for x in ark.iterdir() if x.is_dir()) == ["c", "d"]
    for k in "cd":                                             # durdurulanların ham kaydı silinmedi, arşivde AYNEN
        assert json.loads((ark / k / "hesap_durumu.json").read_text()) == ham1["hesaplar"][k]
    assert (ark / "c" / "cikti" / "ozet.json").exists() and not (tmp_path / "hesaplar" / "c").exists() and (tmp_path / "hesaplar" / "a").exists()
    notu = json.loads((ark / "arsiv_notu.json").read_text())
    assert notu["hesaplar"] == ["c", "d"] and [e["mesaj"] for e in notu["olaylar"]] == ["[c] durdurulacak hesabın olayı"]
    assert not any(e["mesaj"].startswith("[c]") for e in p2.olaylar) and any(e["mesaj"].startswith("[a]") for e in p2.olaylar)
    # ikinci yükleme normal yol (daralma bir kez)
    p3 = _kasa(ta, "abg", mum, s_yeni)
    assert p3.yukle(yol) is True and p3.arsivlenecek == {}


def test_daralma_baska_imza_ya_da_fazla_eksik_hesap_acik_hata_dosya_degismez(tmp_path, monkeypatch):
    mum, ix, ta, s_eski, s_yeni = _kur(monkeypatch)
    yol = tmp_path / "paper_state.json"
    p1 = _kasa(ta, "abgcd", mum, s_eski)
    p1.baslat(ix[120])
    p1.kaydet(yol)
    ham = yol.read_text()
    # (1) 10'lu / 16'lı ESKİ imzalar (sunucuda 20'ye geçilmemişse): açık hata, yönlendirme mesajı
    for eski in (ESKI_IMZA, ESKI16_IMZA):
        d = json.loads(ham)
        d["set_imza"] = eski
        yol.write_text(json.dumps(d))
        with pytest.raises(v2.PaperV2Hatasi, match="20'liye"):
            _kasa(ta, "abg", mum, s_yeni).yukle(yol)
    # (2) tanınmayan imza
    d = json.loads(ham)
    d["set_imza"] = "0123456789abcdef"
    yol.write_text(json.dumps(d))
    with pytest.raises(v2.PaperV2Hatasi, match="set imzası"):
        _kasa(ta, "abg", mum, s_yeni).yukle(yol)
    # (3) 20'li imza ama kayıtta durdurulan hesaplardan biri eksik / fazladan bilinmeyen hesap var
    for degis in ("eksik", "fazla"):
        d = json.loads(ham)
        if degis == "eksik":
            del d["hesaplar"]["d"]
        else:
            d["hesaplar"]["x"] = d["hesaplar"]["a"]
        yol.write_text(json.dumps(d))
        with pytest.raises(v2.PaperV2Hatasi, match="beklenen 10"):
            _kasa(ta, "abg", mum, s_yeni).yukle(yol)
    # (4) 20'li imza ama kalan hesaplardan biri kayıtta yok
    d = json.loads(ham)
    del d["hesaplar"]["g"]
    yol.write_text(json.dumps(d))
    with pytest.raises(v2.PaperV2Hatasi, match="beklenen 10"):
        _kasa(ta, "abg", mum, s_yeni).yukle(yol)
    assert yol.exists() and not (tmp_path / v2.ARSIV_DIZINI).exists()           # hiçbir hatada arşiv/silme yok


def test_daralma_20li_imza_ayni_sette_normal_yukleme_gerekirse(tmp_path, monkeypatch):
    """20'li set kendi imzasıyla yüklenirken daralma tetiklenmez (imza şimdiki setle aynı)."""
    mum, ix, ta, s_eski, s_yeni = _kur(monkeypatch)
    yol = tmp_path / "paper_state.json"
    p1 = _kasa(ta, "abgcd", mum, s_eski)
    p1.baslat(ix[120])
    p1.kaydet(yol)
    p2 = _kasa(ta, "abgcd", mum, s_eski)
    assert p2.yukle(yol) is True and p2.arsivlenecek == {}


# ---------------------------------------------------------------------------- pano ve toplamlar: gizli hesap yok
def _durum_kur(tmp_path):
    mum = veri()
    ix = mum[("BTCUSDT", "1d")].index
    ta = [tanim("gorunen_a", SEM, OrtalamaTrend(n=10), etiket="dogrulandi"), tanim("yedek_b", SEM, OrtalamaTrend(n=15)),
          tanim("gizli_zz", SEM[:2], OrtalamaTrend(n=20))]
    s = _set(_kayit("gorunen_a"), _kayit("yedek_b", yedek=True), _kayit("gizli_zz", gorunur=False))
    p = kos(ta, mum, ayar_set=s, kapat=False)
    simdi = ix[-1] + pd.Timedelta(days=1)
    return p, simdi


def test_pano_gizli_hesabi_hic_gostermez_toplam_yalniz_gorunurlerden(tmp_path):
    p, simdi = _durum_kur(tmp_path)
    p.hesaplar["gizli_zz"].olay_ekle("deneme", "gizli hesap olayı", simdi, True)
    p.hesaplar["gorunen_a"].olay_ekle("deneme", "görünen hesap olayı", simdi, False)
    o = v2.durum_yaz(p, p.kaynak, tmp_path, simdi, kaynak_adi="paper", veri_dizini=tmp_path)
    veri_, sorun = pano.yukle(tmp_path)
    assert not sorun
    st = {x["kimlik"]: x for x in veri_["stratejiler"]["stratejiler"]}
    assert set(st) == {"gorunen_a", "yedek_b"} and st["yedek_b"].get("yedek") is True and "yedek" not in st["gorunen_a"]
    assert veri_["ozet"]["baslangic_ozsermaye"] == "20000.00"                                  # 2 görünür x 10.000 (gizli yok)
    toplam = sum(Decimal(json.loads((tmp_path / "hesaplar" / k / "ozet.json").read_text())["ozsermaye"]) for k in ("gorunen_a", "yedek_b"))
    assert Decimal(veri_["ozet"]["ozsermaye"]) == toplam
    assert abs(p.motor.ozsermaye() - toplam) < Decimal("0.01") and p.ayarlar.baslangic_sermaye == 20000.0
    # gizli hesabın işlemleri toplam işlem listesinde yok
    html = pano.html_olustur(veri_, sorun, SIMDI_PANO)
    assert "gizli_zz" not in html and "gizli hesap olayı" not in html
    assert "Gorunen a" in html and "Yedek b" in html                                     # hesap adları ortak fonksiyondan
    for dosya in tmp_path.glob("*.json*"):       # üst düzey dosyalarda gizli hesap geçmez; TEK istisna butunluk.json: maliyet_modeli ayrıntısı bütünlük özetinin (tüm 10 hesap) girdisidir, pano onu çizmez
        if dosya.name != "butunluk.json":
            assert "gizli_zz" not in dosya.read_text(encoding="utf-8"), dosya.name
    assert (tmp_path / "hesaplar" / "gizli_zz" / "ozet.json").exists()                   # gizli hesap paper'da çalışır ve kendi klasörüne yazar
    # Telegram özeti de yalnız görünürleri içerir
    from motor.canli import telegram as tg
    metin = tg.ozet_metni(o, dun={"gun": "2026-11-13", "pnl": Decimal(0), "getiri": 0.0, "not": None})
    assert "gizli_zz" not in metin
    assert "gizli_zz" not in pano.telegram_metni(veri_, [], SIMDI_PANO)


def test_gizli_hesabin_olayi_telegrama_gitmez_gunluge_yazilir(tmp_path):
    p, simdi = _durum_kur(tmp_path)
    gonderilen = []
    p.bildirim = lambda tur, mesaj: gonderilen.append((tur, mesaj))
    p.hesaplar["gizli_zz"].olay_ekle("giris", "BTC long", simdi, True)                   # işlem olayı: sessiz (kill/hata olayları: aşağıdaki testte [gizli] önekiyle gider)
    p.hesaplar["gorunen_a"].olay_ekle("kill_switch", "KILL SWITCH", simdi, True)
    assert [m for _, m in gonderilen] == ["[gorunen_a] KILL SWITCH"]
    assert any(e["mesaj"] == "[gizli_zz] BTC long" for e in p.olaylar)               # kayıtta (günlük/durum) kalır


def test_butunluk_maliyet_gizli_hesaplari_da_kapsar(tmp_path):
    p, _ = _durum_kur(tmp_path)
    assert set(p.butunluk_maliyet()) == {"gorunen_a", "yedek_b", "gizli_zz"}


# ---------------------------------------------------------------------------- servis: sahte Binance ile uçtan uca daralma
def test_canli_calistir_daralma_sahte_binance(tmp_path, monkeypatch):
    from testler.test_paper_canli import SahteFapi
    monkeypatch.setattr(pv, "FapiIstemci", SahteFapi)
    monkeypatch.setitem(pp.PENCERE, "1d", 120)
    def t_(k, sem, n, et="iyi_gorundu"):
        return tanim(k, sem, OrtalamaTrend(n=n), etiket=et)
    s_eski = _set(_kayit("a"), _kayit("b"), _kayit("c"))
    monkeypatch.setattr(v2, "set_yukle", lambda *x, **k: s_eski)
    monkeypatch.setattr(v2, "tanimlari_yukle", lambda *x, **k: [t_("a", ["BTCUSDT", "ETHUSDT"], 10), t_("b", ["SOLUSDT"], 15), t_("c", ["SOLUSDT"], 12)])
    assert pp.canli_calistir(tmp_path, None, False, tek_sefer=True) == 0
    ham1 = json.loads((tmp_path / "paper_state.json").read_text())
    assert set(ham1["hesaplar"]) == {"a", "b", "c"} and (tmp_path / "hesaplar" / "c").exists()
    s_yeni = _set(_kayit("a"), _kayit("b", gorunur=False))
    monkeypatch.setattr(v2, "IMZA20", v2.set_imzasi(s_eski))
    monkeypatch.setattr(v2, "DURDURULAN_20261114", ("c",))
    monkeypatch.setattr(v2, "set_yukle", lambda *x, **k: s_yeni)
    monkeypatch.setattr(v2, "tanimlari_yukle", lambda *x, **k: [t_("a", ["BTCUSDT", "ETHUSDT"], 10), t_("b", ["SOLUSDT"], 15)])
    assert pp.canli_calistir(tmp_path, None, False, tek_sefer=True) == 0
    ham2 = json.loads((tmp_path / "paper_state.json").read_text())
    assert set(ham2["hesaplar"]) == {"a", "b"} and ham2["set_imza"] == v2.set_imzasi(s_yeni)
    assert (tmp_path / v2.ARSIV_DIZINI / "c" / "hesap_durumu.json").exists() and (tmp_path / v2.ARSIV_DIZINI / "c" / "cikti").is_dir()
    assert json.loads((tmp_path / v2.ARSIV_DIZINI / "c" / "hesap_durumu.json").read_text()) == ham1["hesaplar"]["c"]
    veri_, sorun = dr.oku_hepsi(tmp_path)
    assert not sorun and {x["kimlik"] for x in veri_["stratejiler"]["stratejiler"]} == {"a"}      # b gizli: pano yalnız a
    assert veri_["ozet"]["baslangic_ozsermaye"] == "10000.00"
    # üçüncü başlatma: normal yükleme (arşiv tekrarlanmaz, kayıt değişmez)
    assert pp.canli_calistir(tmp_path, None, False, tek_sefer=True) == 0
    assert set(json.loads((tmp_path / "paper_state.json").read_text())["hesaplar"]) == {"a", "b"}


# ---------------------------------------------------------------------------- Fable denetimi: kaydet koruması + süzülmüş (strateji_filtre) gölge durum
def test_kaydet_arsivlenmemis_daralmada_reddeder_sessizce_hesap_dusurmez(tmp_path, monkeypatch):
    mum, ix, ta, s_eski, s_yeni = _kur(monkeypatch)
    yol = tmp_path / "paper_state.json"
    p1 = _kasa(ta, "abgcd", mum, s_eski)
    p1.baslat(ix[120])
    p1.kaydet(yol)
    ham = yol.read_text()
    p2 = _kasa(ta, "abg", mum, s_yeni)
    assert p2.yukle(yol) is True and set(p2.arsivlenecek) == {"c", "d"}
    with pytest.raises(v2.PaperV2Hatasi, match="arşivlenmedi"):
        p2.kaydet(yol)
    assert yol.read_text() == ham                                      # 20'li kayıt yerinde, durdurulanlar kaybolmadı
    p2.durdurulanlari_arsivle(tmp_path)
    p2.kaydet(yol)                                                     # arşivden sonra serbest
    assert set(json.loads(yol.read_text())["hesaplar"]) == set("abg")


def test_suzulmus_golge_durum_20li_imzadan_10lu_sete_gecer_arsivlenecek_yok(tmp_path, monkeypatch):
    mum, ix, ta, s_eski, s_yeni = _kur(monkeypatch)
    yol = tmp_path / "paper_state.json"
    # strateji_filtre: yalnız a ve b ile kurulmuş gölge durum (20'li set imzasıyla)
    p1 = _kasa(ta, "ab", mum, s_eski)
    p1.baslat(ix[120])
    p1.adim(ix[150])
    p1.kaydet(yol)
    ham1 = json.loads(yol.read_text())
    assert ham1["set_imza"] == v2.set_imzasi(s_eski) and set(ham1["hesaplar"]) == {"a", "b"}
    p2 = _kasa(ta, "ab", mum, s_yeni)
    assert p2.yukle(yol) is True and p2.arsivlenecek == {}
    p2.kaydet(yol)
    ham2 = json.loads(yol.read_text())
    assert ham2["set_imza"] == v2.set_imzasi(s_yeni) and ham2["hesaplar"] == ham1["hesaplar"]
    assert not (tmp_path / v2.ARSIV_DIZINI).exists()


def test_suzulmus_golge_durum_diger_uyusmazliklar_acik_hata(tmp_path, monkeypatch):
    mum, ix, ta, s_eski, s_yeni = _kur(monkeypatch)
    yol = tmp_path / "paper_state.json"
    # (1) kayıttaki hesaplar süzülen altkümeyle aynı değil (kayıtta fazladan b var)
    p1 = _kasa(ta, "ab", mum, s_eski)
    p1.baslat(ix[120])
    p1.kaydet(yol)
    ham = yol.read_text()
    with pytest.raises(v2.PaperV2Hatasi, match="beklenen 10"):
        _kasa(ta, "a", mum, s_yeni).yukle(yol)
    # (2) kayıttaki hesap yeni sette yok (c durdurulan): süzülmüş altküme yeni sette değil -> hata
    p3 = _kasa(ta, "ac", mum, s_eski)
    p3.baslat(ix[120])
    p3.kaydet(yol)
    with pytest.raises(v2.PaperV2Hatasi, match="beklenen 10"):
        v2.kasalar_kur([ta["a"], ta["c"]], mum, {}, s_yeni, pencere={"1d": 300}).yukle(yol)
    # (3) yabancı imza süzülmüş durumda da açık hata
    d = json.loads(ham)
    d["set_imza"] = "0123456789abcdef"
    yol.write_text(json.dumps(d))
    with pytest.raises(v2.PaperV2Hatasi, match="set imzası"):
        _kasa(ta, "ab", mum, s_yeni).yukle(yol)


# ---------------------------------------------------------------------------- pano grupları (Gün içi / Swing / Yedek)
GRUP_BEKLENEN = {"dis__ewo-ema-ofset": "gunici", "dis__e0v1en": "gunici", "HAM:B001:670#v1": "gunici", "HAM:B001:574#v1": "gunici",
                 "dis__gauss-stoch-eth": "swing", "dis__hma-atr-rider": "swing", "HAM:X005:664#v1": "swing", "HAM:X005:705": "swing",
                 "dis__lube": "swing", "HAM:X005:730#v2": "swing"}


def test_gercek_set_grup_alani_ve_imza_degismez():
    s = v2.set_yukle()
    assert {v2.hesap_adi(k): k["grup"] for k in s["stratejiler"]} == GRUP_BEKLENEN
    assert v2.set_imzasi(s) == IMZA10 == "fffbc6624416634e"                      # grup yalnız gösterim alanı: imzaya girmez
    t = copy.deepcopy(s)
    for k in t["stratejiler"]:
        k["grup"] = "swing" if k["grup"] == "gunici" else "gunici"
    assert v2.set_imzasi(t) == IMZA10


def test_gecersiz_ya_da_eksik_grup_kapali_basarisiz(tmp_path):
    s = v2.set_yukle()
    yol = tmp_path / "set.json"
    for kotu in ("yedek", "Swing", None, 3):
        t = copy.deepcopy(s)
        if kotu is None:
            del t["stratejiler"][0]["grup"]
        else:
            t["stratejiler"][0]["grup"] = kotu
        yol.write_text(json.dumps(t))
        with pytest.raises(v2.PaperV2Hatasi, match="grup"):
            v2.set_yukle(yol)




# ---------------------------------------------------------------------------- pano sadeleştirme + aralık karnesi (2026-11-14 ek)
def test_aralik_karnesi_motor_hesabi_durumlar():
    ref = {"islem_esigi": 20, "dusus_limit_carpani": 1.5, "dusus_limit_taban": 0.05, "reddedilen_esik": 0.5, "reddedilen_min_sinyal": 20,
           "hesaplar": {"A": {"gecmis_max_dusus": 0.10}, "B": {"gecmis_max_dusus": 0.10}, "C": {"gecmis_max_dusus": None}, "D": {"gecmis_max_dusus": 0.004}}}
    def sj(k, n, mak, red=0.1, sinyal=30, anlik=0.0):
        return {"kimlik": k, "grup": "swing", "islem_sayisi": n, "hesap": {"zirveden_dusus": anlik, "maks_dusus": mak, "reddedilen_oran": red, "sinyal_sayisi": sinyal}}
    isl = [{"kimlik": "A", "sembol": "X", "set_katki_usd": "30"}, {"kimlik": "A", "sembol": "Y", "set_katki_usd": "5"},
           {"kimlik": "B", "sembol": "X", "set_katki_usd": "30"}, {"kimlik": "B", "sembol": "Y", "set_katki_usd": "-5"}]
    k = {r["kimlik"]: r for r in v2.aralik_karnesi([sj("A", 25, 0.14), sj("B", 3, 0.16, red=0.6), sj("C", 3, 0.5, sinyal=5), sj("D", 1, 0.049)], isl, ref)}
    assert k["A"]["islem"]["durum"] == "gecti" and k["B"]["islem"]["durum"] == "bilinmiyor"
    assert k["A"]["dusus"]["limit"] == pytest.approx(0.15) and k["A"]["dusus"]["durum"] == "gecti"          # 1,5 x %10
    ref2 = {**ref, "hesaplar": {"A": {"gecmis_max_dusus": 0.19}}}
    assert v2.aralik_karnesi([sj("A", 25, 0.14)], [], ref2)[0]["dusus"]["limit"] == pytest.approx(0.15)     # tavan %15 (1,5 x %19 = %28,5 değil)
    assert k["B"]["dusus"]["durum"] == "kaldi"                                                                # en kötü %16 > %15
    assert k["D"]["dusus"]["limit"] == pytest.approx(0.05) and k["D"]["dusus"]["durum"] == "gecti"          # taban %5 (1,5 x 0,4% = 0,6% değil)
    assert k["C"]["dusus"]["durum"] == "bilinmiyor" and k["C"]["dusus"]["neden"] == "referans yok"
    # karne ANLIK değil EN KÖTÜ düşüşü kullanır
    x = v2.aralik_karnesi([sj("A", 25, 0.30, anlik=0.0)], [], ref)[0]
    assert x["dusus"]["deger"] == 0.30 and x["dusus"]["durum"] == "kaldi"
    assert k["A"]["en_iyi_sembol"]["sembol"] == "X" and k["A"]["en_iyi_sembol"]["durum"] == "gecti"
    assert k["B"]["en_iyi_sembol"]["durum"] == "kaldi" and k["C"]["en_iyi_sembol"]["durum"] == "bilinmiyor"
    assert k["A"]["reddedilen"]["durum"] == "gecti" and k["B"]["reddedilen"]["durum"] == "kaldi"             # > %50 kaldı
    assert k["C"]["reddedilen"]["durum"] == "bilinmiyor"                                                      # 20'den az sinyal


def test_gercek_referans_dosyasi_gecmis_dusus_paper_olcegi():
    r = v2.referans_yukle()
    h = {k: v["gecmis_max_dusus"] for k, v in r["hesaplar"].items()}
    assert h["dis__gauss-stoch-eth"] == pytest.approx(0.0878, abs=1e-4) and h["HAM:X005:664#v1"] == pytest.approx(0.1582, abs=1e-4)
    assert h["HAM:B001:670#v1"] == pytest.approx(0.0048, abs=1e-4) and h["HAM:X005:730#v2"] == pytest.approx(0.1949, abs=1e-4)
    assert set(h) == set(GORUNUR) | set(GIZLI) and all("risk_senaryo/ozet.csv" in v["kaynak"] for v in r["hesaplar"].values())
    g = v2.paper_gunu(pd.Timestamp("2026-11-15T08:00:00Z"), r)
    assert g["gun"] == 2 and g["karar_kalan_gun"] == 46 and g["karar_tarihi"] == "2026-12-31"


def test_motor_maks_dusus_kalici_ve_eski_durum_baslatilir(tmp_path):
    p, simdi = _durum_kur(tmp_path)
    m = p.hesaplar["gorunen_a"].motor
    assert m.maks_dusus >= 0
    m.maks_dusus = Decimal("0.07")
    d = m.durum_al()
    assert d["maks_dusus"] == {"__D": "0.07"}                                                              # kodlanmış Decimal
    m.durum_yukle(dict(d))
    assert m.maks_dusus == Decimal("0.07")                                                                    # kayıtlı değer geri gelir
    d.pop("maks_dusus")
    m.durum_yukle(d)
    assert m.maks_dusus >= 0 and m.maks_dusus != Decimal("0.07")                                              # eski durum: şimdiki düşüşten başlar


def test_gizli_hesap_sorunu_gercek_olay_turleriyle(tmp_path):
    p, simdi = _durum_kur(tmp_path)
    assert v2.gizli_ozeti(p) == {"adet": 1, "sorun": []}
    p.hesaplar["gizli_zz"].olay_ekle("kill_switch", "KILL SWITCH: deneme", simdi, False)           # paper.py'nin gerçekten ürettiği tür
    assert v2.gizli_ozeti(p)["sorun"] == ["1 hata/uyarı olayı"]                                     # kill_switch olayı sorun sayılır
    p.hesaplar["gizli_zz"].motor.kill = True
    assert "1 hesapta kill switch" in v2.gizli_ozeti(p)["sorun"]
    p.hesaplar["gizli_zz"].olay_ekle("motor_hatasi", "hata", simdi, False)
    assert "2 hata/uyarı olayı" in v2.gizli_ozeti(p)["sorun"]
    p.hesaplar["gorunen_a"].olay_ekle("motor_hatasi", "görünen hesabın olayı", simdi, False)
    assert "2 hata/uyarı olayı" in v2.gizli_ozeti(p)["sorun"]                                       # görünen hesabın olayı sayılmaz
    assert set(v2.SORUN_OLAY_TURLERI) == {"kill_switch", "gunluk_limit", "motor_hatasi", "binance_hata", "motor_durdu", "veri_yok"}


def test_pano_sadelestirme_ve_yeni_bolumler(tmp_path):
    p, simdi = _durum_kur(tmp_path)
    v2.durum_yaz(p, p.kaynak, tmp_path, simdi, kaynak_adi="paper", veri_dizini=tmp_path)
    veri_, sorun = pano.yukle(tmp_path)
    assert not sorun
    veri_["saglik"]["bilgiler"] = ["DK_JNJ, DK_MA (beklenen, kalıcı)"]
    assert not any("DK_JNJ" in m for _, m in pano.uyarilar(veri_, sorun, SIMDI_PANO))                  # üst bantta yok
    html = pano.html_olustur(veri_, sorun, SIMDI_PANO)
    for yok in ("Beklenti konisi", "DERSLER", "Paper kabul kontrol listesi", "Canlıya uygun", "En erken değerlendirme"):
        assert yok not in html, yok
    assert "gizli_zz" not in html and "Zirveden düşüş" in html


def test_gizli_hesabin_kill_ve_hata_olayi_telegrama_gizli_onekiyle_gider_islem_sessiz(tmp_path):
    p, simdi = _durum_kur(tmp_path)
    gidenler = []
    p.bildirim = lambda tur, mesaj: gidenler.append((tur, mesaj))
    gz, gor = p.hesaplar["gizli_zz"], p.hesaplar["gorunen_a"]
    gz.olay_ekle("kill_switch", "KILL SWITCH: deneme", simdi, True)
    gz.olay_ekle("motor_hatasi", "hata", simdi, True)
    gz.olay_ekle("giris", "BTC long açıldı", simdi, True)                         # işlem bildirimi: sessiz
    gor.olay_ekle("giris", "BTC long açıldı", simdi, True)
    assert [t for t, _ in gidenler] == ["kill_switch", "motor_hatasi", "giris"]
    assert all(m.startswith("[gizli] ") and "gizli_zz" not in m for t, m in gidenler[:2])
    assert gidenler[2][1].startswith("[gorunen_a]")
    assert any(e["mesaj"].startswith("[gizli_zz] KILL") for e in p.olaylar)       # günlükte hesap adıyla (pano süzer)


def test_gizli_hesap_veri_yok_sorun_sayilir_ve_telegrama_gizli_onekiyle_gider():
    from testler.test_paper_v2 import TekrarKaynagi, SembolKurallari
    mum = veri(["BTCUSDT"])
    a = tanim("gorunen_a", ["BTCUSDT"])
    b = tanim("gizli_b", ["DK_JNJ", "DK_MA"])
    pp._tanimlara_veri_yok_isle([b], {"DK_JNJ": (None, "yok"), "DK_MA": (None, "yok")})
    assert b.veri_yok
    s = _set(_kayit("gorunen_a", grup="swing"), _kayit("gizli_b", gorunur=False, grup="swing"))
    p = v2.PaperKasalar([a, b], TekrarKaynagi(mum, {}, {"1d": 300}), {"BTCUSDT": SembolKurallari(0.1, 0.001, 0.001, 5.0)}, s)
    assert p.veri_yok == [] and [t.kimlik for t in p.tum_veri_yok] == ["gizli_b"]
    assert v2.gizli_ozeti(p)["sorun"] == ["veri yok"]                                            # önceden "sorun yok" görünürdü
    gidenler = []
    p.bildirim = lambda tur, mesaj: gidenler.append((tur, mesaj))
    pp.veri_yok_bildir(p, pd.Timestamp("2026-11-15T00:00:00Z"))
    assert len(gidenler) == 1 and gidenler[0][0] == "veri_yok" and gidenler[0][1].startswith("Diğer hesaplar (1)") and "gizli_b" not in gidenler[0][1]
    assert any(e["mesaj"].startswith("[gizli_b] ") for e in p.olaylar)                           # günlükte hesap adıyla (pano süzer)


def test_canli_calistir_ayni_durum_dizininde_ikinci_surec_2_doner(tmp_path):
    import fcntl
    from motor.canli import paper as pp
    f = open(tmp_path / ".kilit", "w")
    fcntl.flock(f, fcntl.LOCK_EX | fcntl.LOCK_NB)
    try:
        assert pp.canli_calistir(tmp_path, None, False, tek_sefer=True) == 2
    finally:
        f.close()
