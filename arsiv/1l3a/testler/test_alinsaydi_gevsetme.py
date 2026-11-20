"""Alınsaydı gevşetme döngüsü (motor/canli/alinsaydi_gevsetme.py): gevşetme, geri alma, kara liste, fren, canlıda etkisizlik, işleme etki. Ağ YOK."""
import inspect
import json
from types import SimpleNamespace

import pandas as pd
import pytest

from motor.canli import alinsaydi_gevsetme as ag
from motor.canli import etiket_kurallari as ek
from motor.canli import ogrenme_adaptor as oa
from motor.canli import paper as pp
from testler.test_etiket_kurallari import BOS, et
from testler.test_kayit_etiketleri import _paper, satirlar

SIMDI = pd.Timestamp("2025-01-20 22:30", tz="UTC")           # TSİ 21.01 01:30
SK = "gizlistrat|XUSDT|1d"                                    # hesap/kol adı: hiçbir çıktıda geçmemeli
REJ, TAK = "etiket:rejim_karsiti", "etiket:takvim_olayi"


def kayit_satiri(neden, gun, i, hedef="110"):
    return {"zaman": str(gun), "hesap": f"gizlihesap{i}", "strateji": SK, "kol": f"{SK}#{i}", "sembol": "XUSDT", "tf": "1d", "yon": "long",
            "fiyat": "100", "stop": "95", "hedef": hedef, "zaman_cikisi_mum": None, "neden": neden}


def dosyaya(tmp_path, satirlar_):
    (tmp_path / "alinmayan_sinyaller.jsonl").write_text("\n".join(json.dumps(r) for r in satirlar_) + "\n", encoding="utf-8")


def kanit_hazir(tmp_path, p, mum, kazanc=None, kayip=None, risk=None):
    """kazanc: kazançlı (hedef +2R) nedenler, kayip: stop (-1R) nedenler, risk: kapsam dışı (risk kapısı) kazançlı nedenler; hepsi 12 satır."""
    df = mum[("XUSDT", "1d")]
    df.iloc[4, df.columns.get_loc("yuksek")] = 111.0          # kazanç günü: hedef 110
    df.iloc[5, df.columns.get_loc("dusuk")] = 94.0            # kayıp günü: stop 95
    rows = []
    for nd in (kazanc or []) + (risk or []):
        rows += [kayit_satiri(nd, df.index[4], i) for i in range(12)]
    for nd in (kayip or []):
        rows += [kayit_satiri(nd, df.index[5], i) for i in range(12)]
    dosyaya(tmp_path, rows)


def kur(tmp_path, etiket=None, ogrenme=None, durum=None, canli=False, bagla=True):
    tmp_path.mkdir(parents=True, exist_ok=True)
    p, mum, _ = _paper(tmp_path)
    if etiket is not None:
        p.kayit.etiketler = lambda *a, **k: dict(etiket)
    ek.bagla(p, env={})
    if durum is not None:
        (tmp_path / ag.DURUM).write_text(json.dumps(durum), encoding="utf-8")
    g = []
    c = ag.AlinsaydiGevsetme(tmp_path, gonder=lambda m: g.append(m) or True, ogrenme=ogrenme, canli=canli)
    if bagla:
        c.bagla(p)
    else:
        c._p = p
    return c, p, mum, g


def aktif_durum(*nedenler, zaman="2025-01-01T00:00:00+00:00"):
    return {"aktif": {n: {"zaman": zaman, "kanit": {}} for n in nedenler}}


def islem_ve_gecis(c, p, neden, r, i, kimlik=None):
    """Gevşetme geçişi + aynı kolun kapanmış işlemi (gerçekleşen net R = r)."""
    kimlik = kimlik or next(k.kimlik for k in p.motor.tum_kollar)
    z = pd.Timestamp("2025-01-02", tz="UTC") + pd.Timedelta(hours=i)
    c.durum["gecisler"].append({"neden": neden, "k": ag._kh(kimlik), "t": z.isoformat()})
    p.motor.islemler.append({"sembol": "XUSDT", "kol": kimlik, "yon": 1, "giris_zamani": z, "giris_fiyati": 100.0, "cikis_zamani": z + pd.Timedelta(hours=1),
                             "cikis_fiyati": 95.0, "miktar": 1.0, "net_pnl": r * 5.0, "r": r, "funding": 0.0, "cikis_nedeni": "stop"})


# ---------------------------------------------------------------------------- ölçütler
def test_gevsetme_olcutu_sinirlari():
    assert ag.gevsetme_olcutu([0.2] * 10) is True                       # n=10, ort>0, toplam tam +2 R
    assert ag.gevsetme_olcutu([0.2] * 9) is False                       # 9 çözülmüş
    assert ag.gevsetme_olcutu([0.19] * 10) is False                     # toplam 1.9 R
    assert ag.gevsetme_olcutu([-0.2] * 10) is False and ag.gevsetme_olcutu([]) is False


def test_geri_al_ve_fren_sinirlari():
    assert ag.geri_al_gerekli([-0.2] * 10) is True                      # toplam tam -2 R
    assert ag.geri_al_gerekli([-0.2] * 9) is False                      # 9 işlem
    assert ag.geri_al_gerekli([-0.19] * 10) is False
    assert ag.fren_gerekli(-5.0) is True and ag.fren_gerekli(-4.99) is False


def test_kapsam_allowlist_risk_kapilari_gevsetilemez():
    for n in ("etiket:rejim_karsiti", "etiket:takvim_olayi", "etiket:kalabalik", "ml_filtre", "ders:xyz"):
        assert ag.gevsetilebilir(n)
    for n in ag.RISK_NEDENLERI | {"etiket:bilinmeyen", "ders:", "", None, "bilinmeyen", "limit:gunluk"}:
        assert not ag.gevsetilebilir(n)
    assert ek.degerlendir("long", et(rejim_ml_1d="trend_down")) == REJ                          # varsayılan davranış değişmez
    assert ek.degerlendir("long", et(rejim_ml_1d="trend_down"), devre_disi={"rejim_karsiti"}) is None
    assert ek.degerlendir("long", et(rejim_ml_1d="trend_down", takvim_bayragi="X"), devre_disi={"rejim_karsiti"}) == TAK


# ---------------------------------------------------------------------------- 1) gevşetme
def test_gece_karli_filtreyi_gevsetir_risk_kapilarina_dokunmaz(tmp_path):
    c, p, mum, g = kur(tmp_path, bagla=False)
    kanit_hazir(tmp_path, p, mum, kazanc=[REJ], kayip=[TAK], risk=["max_pozisyon", "toplam_risk_tavani", "kaldirac_tavani", "gunluk_kayip_limiti", "etiket:bilinmeyen"])
    o = c.gece(SIMDI)
    assert o["yeni"] == [REJ] and set(c.aktif) == {REJ}                  # kârlı + kapsam içi: gevşer; zararlı ve risk kapıları gevşemez
    d = json.loads((tmp_path / ag.DURUM).read_text(encoding="utf-8"))
    assert set(d["aktif"]) == {REJ} and d["aktif"][REJ]["kanit"]["cozulen"] == 12 and d["aktif"][REJ]["kanit"]["toplam_r"] == pytest.approx(24.0)
    assert g == []                                                       # "filtresi gevşetildi" Telegram'a gitmez (yalnız log)
    assert c.gece(SIMDI)["yeni"] == []                                   # zaten gevşek: tekrar yok


def test_gecede_en_cok_bir_gevsetme_en_kazancli_once(tmp_path):
    c, p, mum, g = kur(tmp_path, bagla=False)
    df = mum[("XUSDT", "1d")]
    df.iloc[4, df.columns.get_loc("yuksek")] = 111.0
    rows = [kayit_satiri(REJ, df.index[4], i) for i in range(12)] + [kayit_satiri(TAK, df.index[4], i, hedef="106") for i in range(12)]    # TAK: +1.2 R x 12
    dosyaya(tmp_path, rows)
    assert c.gece(SIMDI)["yeni"] == [REJ]                                # 24 R > 14.4 R
    assert c.gece(SIMDI + pd.Timedelta(days=1))["yeni"] == [TAK]         # ertesi gece sıradaki (iz: tek filtre etkisi ayrışsın)


@pytest.mark.parametrize("n,gun_i", [(9, 4), (12, 5)])
def test_az_ornek_ya_da_zarar_gevsetmez(tmp_path, n, gun_i):
    c, p, mum, g = kur(tmp_path, bagla=False)
    df = mum[("XUSDT", "1d")]
    df.iloc[4, df.columns.get_loc("yuksek")] = 111.0
    df.iloc[5, df.columns.get_loc("dusuk")] = 94.0
    dosyaya(tmp_path, [kayit_satiri(REJ, df.index[gun_i], i) for i in range(n)])
    assert c.gece(SIMDI)["yeni"] == [] and not c.aktif and g == []


def test_lookahead_yok_karar_oncesi_mumlar_sonucu_etkilemez(tmp_path):
    c, p, mum, g = kur(tmp_path, bagla=False)
    df = mum[("XUSDT", "1d")]
    df.iloc[3, df.columns.get_loc("yuksek")] = 200.0                     # karardan ÖNCEKİ mum: hedefi vurur ama sayılmamalı
    dosyaya(tmp_path, [kayit_satiri(REJ, df.index[4], i) for i in range(12)])
    k = c.kanit(SIMDI)
    assert k[REJ]["cozulen"] == 0 and k[REJ]["sinyal"] == 12             # sonrasında stop/hedef yok: çözülmedi
    assert c.gece(SIMDI)["yeni"] == []


def test_pencere_30_gun_disindaki_kanit_sayilmaz(tmp_path):
    c, p, mum, g = kur(tmp_path, bagla=False)
    kanit_hazir(tmp_path, p, mum, kazanc=[REJ])
    assert c.kanit(SIMDI)[REJ]["cozulen"] == 12
    assert REJ not in c.kanit(SIMDI + pd.Timedelta(days=40))


def test_ayni_kurulum_tekrar_yazilmissa_tek_sayilir(tmp_path):
    c, p, mum, g = kur(tmp_path, bagla=False)
    df = mum[("XUSDT", "1d")]
    df.iloc[4, df.columns.get_loc("yuksek")] = 111.0
    r = kayit_satiri(REJ, df.index[4], 0)
    dosyaya(tmp_path, [r] * 30)
    assert c.kanit(SIMDI)[REJ]["sinyal"] == 1


def test_gunde_bir_ve_tsi_0130_sonrasi(tmp_path):
    c, p, mum, g = kur(tmp_path, bagla=False)
    kanit_hazir(tmp_path, p, mum, kazanc=[REJ])
    assert c.gunluk(pd.Timestamp("2025-01-20 22:00", tz="UTC")) is False        # TSİ 01:00 < 01:30
    assert c.gunluk(SIMDI) is True and set(c.aktif) == {REJ}
    assert c.gunluk(SIMDI + pd.Timedelta(hours=1)) is False                      # aynı gün
    assert c.gunluk(SIMDI + pd.Timedelta(days=1)) is True


# ---------------------------------------------------------------------------- 2) geri alma + kara liste
def test_geri_al_ve_kara_liste_tekrar_gevsemez(tmp_path):
    c, p, mum, g = kur(tmp_path, bagla=False, durum=aktif_durum(REJ))
    for i in range(10):
        islem_ve_gecis(c, p, REJ, -0.25, i)                                      # 10 işlem, toplam -2.5 R
    assert c.izle(SIMDI) == [REJ]
    assert not c.aktif and c.durum["kara_liste"] == [REJ]
    assert len(g) == 1 and g[0].startswith("[1L3A] ⚠️") and "\n" not in g[0] and "etiket:" not in g[0] and "-2.5 R" in g[0]
    d = json.loads((tmp_path / ag.DURUM).read_text(encoding="utf-8"))
    assert d["kara_liste"] == [REJ] and d["aktif"] == {}
    kanit_hazir(tmp_path, p, mum, kazanc=[REJ])                                  # kanıt yine kârlı görünse bile
    assert c.gece(SIMDI + pd.Timedelta(days=1))["yeni"] == [] and not c.aktif
    c2 = ag.AlinsaydiGevsetme(tmp_path, gonder=lambda m: True)                   # yeniden başlatma: kara liste kalıcı
    assert c2.durum["kara_liste"] == [REJ] and not c2.aktif


@pytest.mark.parametrize("n,r", [(9, -0.5), (10, -0.19)])
def test_geri_alma_olmaz_az_islem_ya_da_hafif_zarar(tmp_path, n, r):
    c, p, mum, g = kur(tmp_path, bagla=False, durum=aktif_durum(REJ))
    for i in range(n):
        islem_ve_gecis(c, p, REJ, r, i)
    assert c.izle(SIMDI) == [] and set(c.aktif) == {REJ} and g == []


def test_geri_alma_tam_sinir_toplam_eksi_2R(tmp_path):
    c, p, mum, g = kur(tmp_path, bagla=False, durum=aktif_durum(REJ))
    for i in range(10):
        islem_ve_gecis(c, p, REJ, -0.2, i)
    assert c.izle(SIMDI) == [REJ]


def test_gevsetme_oncesi_gecisler_ve_baska_filtre_sayilmaz(tmp_path):
    c, p, mum, g = kur(tmp_path, bagla=False, durum=aktif_durum(REJ, zaman="2025-01-03T00:00:00+00:00"))
    for i in range(10):
        islem_ve_gecis(c, p, REJ, -1.0, i)                                       # i<48 saat: gevşetme zamanından (01-03) ÖNCE -> sayılmaz
    s = c.izleme_sonucu()
    assert s[REJ] == [] and c.izle(SIMDI) == []


# ---------------------------------------------------------------------------- 2b) fren
def test_fren_tum_gevsetmeler_toplam_eksi_5R_hepsi_askiya(tmp_path):
    c, p, mum, g = kur(tmp_path, bagla=False, durum=aktif_durum(REJ, TAK))
    for i in range(5):
        islem_ve_gecis(c, p, REJ, -0.6, i)                                       # -3.0 (5 işlem: tek başına geri alma yok)
        islem_ve_gecis(c, p, TAK, -0.4, i + 10)                                  # -2.0 -> toplam tam -5.0
    assert c.izle(SIMDI) == [] and not c.aktif
    assert set(c.durum["askida"]) == {REJ, TAK} and c.durum["kara_liste"] == []   # askıya alma: kara listeye GİRMEZ
    assert c.durum["fren"]["aktif"] is True and c.durum["fren"]["toplam_r"] == pytest.approx(-5.0)
    assert len(g) == 1 and g[0].startswith("[1L3A] ⚠️") and "etiket:" not in g[0] and "-5.0 R" in g[0]
    kanit_hazir(tmp_path, p, mum, kazanc=[REJ])
    assert c.gece(SIMDI + pd.Timedelta(days=1))["yeni"] == [] and not c.aktif    # fren: yeni gevşetme yok
    gec = c.gece(SIMDI + pd.Timedelta(days=ag.FREN_BEKLEME_GUN + 1))             # bekleme bitti: normal değerlendirme
    assert gec["yeni"] == [REJ] and c.durum["fren"]["aktif"] is False and REJ not in c.durum["askida"]


def test_fren_siniri_eksi_4_99_tetiklemez_ve_ikinci_fren_kalici(tmp_path):
    c, p, mum, g = kur(tmp_path, bagla=False, durum=aktif_durum(REJ, TAK))
    for i in range(5):
        islem_ve_gecis(c, p, REJ, -0.5, i)
        islem_ve_gecis(c, p, TAK, -0.499, i + 10)
    assert c.izle(SIMDI) == [] and set(c.aktif) == {REJ, TAK} and not c.durum.get("fren")
    islem_ve_gecis(c, p, REJ, -0.01, 20)
    c.izle(SIMDI)
    assert c.durum["fren"]["sayac"] == 1 and c.durum["fren"]["kalici"] is False
    for n in (REJ, TAK):                                                         # bekleme sonrası yeniden gevşetilmiş gibi (eski zarar yine sayılır): ikinci fren
        c.durum["aktif"][n] = c.durum["askida"].pop(n)
    c.durum["fren"]["aktif"] = False
    c.izle(SIMDI + pd.Timedelta(days=10))
    assert c.durum["fren"]["sayac"] == 2 and c.durum["fren"]["kalici"] is True
    assert c.gece(SIMDI + pd.Timedelta(days=60))["yeni"] == [] and c.durum["fren"]["aktif"] is True    # kalıcı kilit: süre dolsa da açılmaz


# ---------------------------------------------------------------------------- 3) canlıda etkisiz
def test_canlida_bagla_none_hicbir_kanca_yok_ve_durum_okunmaz(tmp_path):
    p, mum, _ = _paper(tmp_path)
    p.kayit.etiketler = lambda *a, **k: et(rejim_ml_1d="trend_down")
    ek.bagla(p, env={})
    (tmp_path / ag.DURUM).write_text(json.dumps(aktif_durum(REJ)), encoding="utf-8")        # canlı dizinde dosya olsa bile
    adim0, izni0, es0 = p.adim, p.motor._giris_izni, p.motor.etiket_suzgeci
    assert ag.bagla(p, tmp_path, canli=True) is None
    assert p.adim == adim0 and p.motor._giris_izni == izni0 and p.motor.etiket_suzgeci is es0
    c = ag.AlinsaydiGevsetme(tmp_path, canli=True)
    assert c.kapali and c.aktif == {} and c.gunluk(SIMDI) is False and c.bagla(p) is None and c.durum["aktif"] == {}
    p.adim(mum[("XUSDT", "1d")].index[8])
    assert not p.motor.acik                                                      # filtre canlı yolunda tam güçte: giriş hâlâ atlandı
    assert REJ in [s["neden"] for s in satirlar(tmp_path)]


def test_paper_canli_calistir_canliyi_tur_kancasi_ve_strateji_filtresiyle_ayirir():
    kaynak = inspect.getsource(pp._canli_calistir_kilitli)
    assert "alinsaydi_gevsetme.bagla(p, durum_dizini, gonder, ogrenme=og_, canli=(tur_kancasi is not None or strateji_filtre is not None))" in kaynak
    assert ag.bagla(SimpleNamespace(), "x", canli=True) is None and ag.bagla(SimpleNamespace(), "x", env={ag.ENV_KAPALI: "1"}) is None


def test_kapatma_bayragi(tmp_path):
    p, mum, _ = _paper(tmp_path)
    assert ag.bagla(p, tmp_path, env={ag.ENV_KAPALI: "1"}) is None
    assert not getattr(p.motor, "_gevsetme_izni_sarili", False)


# ---------------------------------------------------------------------------- işleme etki
def test_gevsetilmis_filtre_artik_sinyali_engellemez_ve_gecis_islemle_eslenir(tmp_path):
    ters = et(rejim_ml_1d="trend_down")
    c0, p0, mum0, _ = kur(tmp_path / "0", etiket=ters, bagla=False)              # gevşetme yok: engel
    p0.adim(mum0[("XUSDT", "1d")].index[8])
    assert not p0.motor.acik and REJ in [s["neden"] for s in satirlar(tmp_path / "0")]
    d = tmp_path / "1"
    c, p, mum, g = kur(d, etiket=ters, durum=aktif_durum(REJ))                  # gevşetme aktif: aynı sinyal artık alınır
    idx = mum[("XUSDT", "1d")].index
    p.adim(idx[8])
    assert p.motor.acik and REJ not in [s["neden"] for s in satirlar(d)]
    assert len(c.durum["gecisler"]) == 1 and c.durum["gecisler"][0]["neden"] == REJ
    kol = next(iter(p.motor.acik))
    assert c.durum["gecisler"][0]["k"] == ag._kh(kol) and SK.split("|")[0] not in json.dumps(c.durum) and "a|XUSDT" not in json.dumps(c.durum)
    df = mum[("XUSDT", "1d")]
    df.iloc[10, df.columns.get_loc("dusuk")] = 80.0                             # stop vurur (motor kapanışı bir sonraki adımda işler)
    for i in (9, 10, 11):
        p.adim(idx[i])
    assert not p.motor.acik and len(p.motor.islemler) == 1
    s = c.izleme_sonucu()
    assert len(s[REJ]) == 1 and s[REJ][0] == pytest.approx(float(p.motor.islemler[0]["r"])) and s[REJ][0] < 0


def test_diger_kural_hala_engeller_gevsetme_yalniz_kendi_kuralini_acar(tmp_path):
    c, p, mum, g = kur(tmp_path, etiket=et(rejim_ml_1d="trend_down", takvim_bayragi="FOMC"), durum=aktif_durum(REJ))
    p.adim(mum[("XUSDT", "1d")].index[8])
    assert not p.motor.acik and TAK in [s["neden"] for s in satirlar(tmp_path)]
    assert c.durum["gecisler"] == []                                             # engel sürdüğü için geçiş sayılmaz


def test_gevsetilmeyen_filtre_ve_risk_kapisi_ayni_kalir(tmp_path):
    # aktif listede olmayan (ör. takvim) filtre engellemeye devam eder; durum dosyasına elle yazılmış risk kapısı yükte süzülür
    c, p, mum, g = kur(tmp_path, etiket=et(takvim_bayragi="FOMC"), durum=aktif_durum(REJ, "max_pozisyon", "kaldirac_tavani"))
    assert set(c.aktif) == {REJ}
    p.adim(mum[("XUSDT", "1d")].index[8])
    assert not p.motor.acik


def test_etiket_yeniden_degerlendirme_hatasinda_fail_closed(tmp_path, monkeypatch):
    c, p, mum, g = kur(tmp_path, etiket=et(rejim_ml_1d="trend_down"), durum=aktif_durum(REJ))
    orig = ek.degerlendir

    def bozuk(yon, etk, devre_disi=frozenset()):
        if devre_disi:                                                           # yalnız gevşetme yeniden değerlendirmesi patlar
            raise RuntimeError("x")
        return orig(yon, etk, devre_disi)
    monkeypatch.setattr(ek, "degerlendir", bozuk)
    p.adim(mum[("XUSDT", "1d")].index[8])
    assert not p.motor.acik                                                      # hata -> eski karar (engel)


# ---------------------------------------------------------------------------- ML filtre + ders zinciri (öğrenme adaptörü DEĞİŞMEDEN)
class SahteOg:
    """oa.Ogrenme'nin giris_suzgeci/_etkin_dersler/_model yüzeyi."""
    def __init__(self, dersler=("x:1",), model=True):
        self._d, self._m, self.cagri = list(dersler), model, 0

    def _etkin_dersler(self):
        return list(self._d)

    def _model(self, ad):
        return "M" if self._m else None

    def giris_suzgeci(self, strateji, sembol, yon, oz):
        self.cagri += 1
        for k in self._etkin_dersler():
            return False, f"ders:{k.split(':', 1)[0]}"
        if self._model("a") is not None:
            return False, "ml_filtre"
        return True, ""


def _og_kur(tmp_path, durum, **kw):
    og = SahteOg(**kw)
    tmp_path.mkdir(parents=True, exist_ok=True)
    p, mum, _ = _paper(tmp_path)
    p.motor.giris_suzgeci = og.giris_suzgeci
    (tmp_path / ag.DURUM).write_text(json.dumps(durum), encoding="utf-8")
    c = ag.AlinsaydiGevsetme(tmp_path, gonder=lambda m: True, ogrenme=og)
    c.bagla(p)
    return c, p, mum, og


def test_ders_gevsetilince_ml_filtre_hala_engeller_ikisi_gevsekse_gecer(tmp_path):
    c, p, mum, og = _og_kur(tmp_path / "a", aktif_durum("ders:x"))
    assert p.motor.giris_suzgeci == og.giris_suzgeci                            # kanca tazelemesiyle (ogrenme._kanca_tak) uyumlu: tek paylaşılan süzgeç
    p.adim(mum[("XUSDT", "1d")].index[8])
    assert not p.motor.acik and "ml_filtre" in [s["neden"] for s in satirlar(tmp_path / "a")]    # ders gevşek ama ML hâlâ engelliyor
    c, p, mum, og = _og_kur(tmp_path / "b", aktif_durum("ders:x", "ml_filtre"))
    p.adim(mum[("XUSDT", "1d")].index[8])
    assert p.motor.acik and len(c.durum["gecisler"]) == 2 and {g["neden"] for g in c.durum["gecisler"]} == {"ders:x", "ml_filtre"}
    c, p, mum, og = _og_kur(tmp_path / "c", {}, dersler=())                     # gevşetme yok: karar değişmez
    assert c._maske == frozenset()
    p.adim(mum[("XUSDT", "1d")].index[8])
    assert not p.motor.acik                                                     # yalnız ml_filtre engeller, gevşetilmemiş


def test_ml_filtre_tek_basina_gevsetilince_gecer_ve_maske_temizlenir(tmp_path):
    c, p, mum, og = _og_kur(tmp_path, aktif_durum("ml_filtre"), dersler=())
    p.adim(mum[("XUSDT", "1d")].index[8])
    assert p.motor.acik and c._maske == frozenset()
    assert og._model("a") == "M"                                                # maske dışında özgün davranış


def test_gercek_ogrenme_adaptoru_ile_baglanir_ve_dosyasi_degismez(tmp_path):
    p, mum, _ = _paper(tmp_path)
    og = oa.Ogrenme(tmp_path, saat=lambda: pd.Timestamp("2025-01-01", tz="UTC"), gonder=lambda m: True)
    og.bagla(p)
    c = ag.AlinsaydiGevsetme(tmp_path, gonder=lambda m: True, ogrenme=og)
    assert c.bagla(p) is c and c._og_hazir is True
    p.adim(mum[("XUSDT", "1d")].index[8])
    assert p.motor.acik                                                         # ders/ml yok: giriş serbest
    assert p.motor.giris_suzgeci == og.giris_suzgeci


def test_ogrenme_yoksa_ders_ml_gevsetilmez(tmp_path):
    c, p, mum, g = kur(tmp_path, bagla=False)
    df = mum[("XUSDT", "1d")]
    df.iloc[4, df.columns.get_loc("yuksek")] = 111.0
    dosyaya(tmp_path, [kayit_satiri("ml_filtre", df.index[4], i) for i in range(12)] + [kayit_satiri("ders:x", df.index[4], i) for i in range(12)])
    assert c.gece(SIMDI)["yeni"] == [] and not c.aktif                          # atlatma yüzeyi yok: gevşetme DEĞİL


# ---------------------------------------------------------------------------- gizlilik + bütünlük
def test_gizli_hesap_ve_kol_adi_hicbir_yerde_yok(tmp_path):
    c, p, mum, g = kur(tmp_path, bagla=False)
    kanit_hazir(tmp_path, p, mum, kazanc=[REJ])
    c.gece(SIMDI)
    islem_ve_gecis(c, p, REJ, -3.0, 1)
    c.izle(SIMDI)
    tum = json.dumps(g) + (tmp_path / ag.DURUM).read_text(encoding="utf-8")
    for yasak in ("gizlistrat", "gizlihesap", "a|XUSDT"):
        assert yasak not in tum


def test_hata_paper_etkilemez_ve_bozuk_durum_dosyasi_acilir(tmp_path):
    (tmp_path / ag.DURUM).write_text("{bozuk", encoding="utf-8")
    c, p, mum, g = kur(tmp_path, etiket=et(rejim_ml_1d="trend_down"), bagla=False)
    assert c.aktif == {} and c.durum["kara_liste"] == []
    c.bagla(p)
    c.gece = lambda simdi: 1 / 0                                                # gece hatası paper'ı düşürmez
    p.adim(mum[("XUSDT", "1d")].index[8])
    assert not p.motor.acik                                                     # durum bozuk: filtre eski haliyle çalışır
    assert c.gunluk(SIMDI) is True                                              # istisna yutulur


# ---------------------------------------------------------------------------- v2 (çok hesaplı) bağlama
def _v2(tmp_path, durum=None):
    from motor.backtest.motor import SembolKurallari
    from motor.canli import paper_v2 as v2
    from motor.canli.paper_kaynak import TekrarKaynagi
    from testler.test_kayit_etiketleri import kayit
    from testler.test_paper_v2 import set_, tanim as tanim2, veri
    tmp_path.mkdir(parents=True, exist_ok=True)
    mum = veri(["BTCUSDT"])
    a, b = tanim2("a", ["BTCUSDT"]), tanim2("b", ["BTCUSDT"])
    p = v2.PaperKasalar([a, b], TekrarKaynagi(mum, {}, {"1d": 300}), {"BTCUSDT": SembolKurallari(0.1, 0.001, 0.001, 5.0)}, set_("a", "b"))
    p.kayit_ac(kayit(tmp_path))
    for h in p.hesaplar.values():
        h.kayit.etiketler = lambda *a_, **k: et(rejim_ml_1d="trend_down", rejim_ml_4h="trend_down")
    ek.bagla(p, env={})
    if durum is not None:
        (tmp_path / ag.DURUM).write_text(json.dumps(durum), encoding="utf-8")
    c = ag.bagla(p, tmp_path, lambda m: True)
    return p, c, mum


def test_v2_her_hesaba_baglanir_gevsetme_yalniz_aktifken_islem_acar(tmp_path):
    p0, c0, mum = _v2(tmp_path / "0")
    ix = mum[("BTCUSDT", "1d")].index
    p0.baslat(ix[120])
    p0.adim(ix[200])
    assert all(h.motor._gevsetme_izni_sarili and h.motor.etiket_suzgeci._gevsetme for h in p0.hesaplar.values())
    n0 = sum(len(h.motor.islemler) + len(h.motor.acik) for h in p0.hesaplar.values())
    p1, c1, _ = _v2(tmp_path / "1", aktif_durum(REJ))
    p1.baslat(ix[120])
    p1.adim(ix[200])
    n1 = sum(len(h.motor.islemler) + len(h.motor.acik) for h in p1.hesaplar.values())
    assert n0 == 0 and n1 > 0 and c1.durum["gecisler"]                         # gevşetme yok: tüm girişler engelli; gevşek: işlem açılır
    assert all(set(g) == {"neden", "k", "t"} for g in c1.durum["gecisler"])    # hesap adı yok: yalnız özet kimliği
