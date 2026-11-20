"""Strateji verisi belgesi: tüm alanlar, gizli hesap hariç tutma, 4096 sınırı (mesaj/belge), sürüm başına tek sefer, sessiz bayrak, veri yok durumları."""
import json
from datetime import datetime, timezone

from motor.canli import strateji_verisi as sv

GIZLI = "dis__gizlix"
SIMDI = datetime(2026, 11, 20, 12, 0, tzinfo=timezone.utc)


def _yaz(yol, c):
    yol.parent.mkdir(parents=True, exist_ok=True)
    yol.write_text(json.dumps(c) if not isinstance(c, str) else c, encoding="utf-8")


def _hesap(kok, klasor, pnl, islemler, acik=0, maliyet=True, alinmayan=None):
    _yaz(kok / "ozet.json", {"baslangic_ozsermaye": "10000.00", "ozsermaye": str(10000 + pnl), "toplam_pnl": str(pnl), "gun_pnl": "0", "zirve_ozsermaye": "10500.00",
                              "sayaclar": {"kapanan_islem": len(islemler), "acik_pozisyon": acik}})
    _yaz(kok / "islemler.jsonl", "\n".join(json.dumps({"zaman": "2026-11-10T10:00:00Z", "cikis_zamani": "2026-11-10T10:00:00Z", **x}) for x in islemler))
    if maliyet:
        _yaz(kok / "maliyet.json", {"toplam": {"tum": {"ucret": "5.00", "kayma": "2.00", "funding": "1.00", "toplam": "8.00"}}})
    if alinmayan:
        _yaz(kok / "alinmayan_sinyaller.jsonl", "\n".join(json.dumps({"zaman": "2026-11-10T10:00:00Z", "neden": n}) for n in alinmayan))


def _kur(tmp_path, rejim=True):
    durum = tmp_path / "durum"
    st = [{"strateji": "dis__gorunura", "tf": "1d", "evren": "genel", "tur": "tek"},
          {"strateji": "dis__gorunurb", "tf": "1d", "evren": "genel", "tur": "tek"},
          {"strateji": GIZLI, "tf": "1d", "evren": "genel", "tur": "tek", "gorunur": False}]
    _yaz(tmp_path / "set.json", {"stratejiler": st})
    r = {"rejim_ml_1d": "boga"} if rejim else {}
    _hesap(durum / "hesaplar" / "dis__gorunura", "a", 100, [{"net_pnl_yerel": "50", "yon": "long", **r}, {"net_pnl_yerel": "-20", "yon": "short", **r},
                                                           {"net_pnl_yerel": "30", "yon": "long", **r}, {"net_pnl_yerel": "40", "yon": "long", **r}], acik=1)
    _hesap(durum / "hesaplar" / "dis__gorunurb", "b", 0, [], alinmayan=["toplam_risk_tavani", "toplam_risk_tavani", "acik_pozisyon"])
    _hesap(durum / "hesaplar" / GIZLI, "g", 9999, [{"net_pnl_yerel": "9999", "yon": "long"}])
    return durum, tmp_path / "set.json"


def _topla(tmp_path, **kw):
    durum, sy = _kur(tmp_path, **kw)
    return sv.topla(durum, simdi=SIMDI, ct_dizin=tmp_path / "ct_yok", set_yolu=sy, gizli={GIZLI}), durum, sy


def test_tum_alanlar_ve_gizli_hesap_yok(tmp_path):
    v, _, _ = _topla(tmp_path)
    m = sv.metin_uret(v)
    assert m.startswith("[1L3A] Strateji verisi (beyin fırtınası için)")
    for parca in ("A) Toplam (görünür hesaplar)", "Net K/Z (kapanan + açık): +100,00 $ (+%0,50)", "İşlem: 4 kapanan / 1 açık", "Kazanma: %75,0", "Kâr faktörü: 6,00",
                  "Ortalama kazanç / ortalama kayıp: +40,00 $ / −20,00 $", "Zirveden düşüş:", "Maliyet: komisyon 10,00 $ + fonlama +2,00 $ + kayma 4,00 $ = 16,00 $ · brüt K/Z'nin %13,8",
                  "En iyi 3 işlem çıkarılınca kapanan net: −20,00 $", "boga: 4 işlem", "Long: 3 işlem · net +120,00 $ · kazanma %100,0", "Short: 1 işlem · net −20,00 $ · kazanma %0,0",
                  "B) STRATEJİ BAZINDA", "Toplam strateji: 2 · sinyal üreten: 2 · işlem açan: 1 · hiç işlem açmayan: 1", "açmama nedeni: toplam risk tavani (2 sinyal)",
                  "C) DERS VE ML DURUMU", "Dersler: veri yok", "Gorunura", "Gorunurb"):
        assert parca in m, parca
    assert "gizlix" not in m.lower() and "9.999" not in m and "9999" not in m and GIZLI not in m


def test_ders_ve_ml_ifadeleri(tmp_path):
    durum, sy = _kur(tmp_path)
    ders = {"d1:gorunura": {"status": "alive"}, "d2:gorunura": {"status": "candidate"}, "d3:gorunura": {"status": "alive"}, "d4:gorunura": {"status": "retired"},
            f"d5:{GIZLI}": {"status": "alive"}}
    _yaz(durum / "ogrenme_ders.json", ders)
    _yaz(durum / "ogrenme_fren.json", {"askida": {"d3:gorunura": {}}})
    _yaz(durum / "ogrenme_durum.json", {"egitim": {}})
    _yaz(durum / "ogrenme_esleme.json", {"dis__gorunura": "gorunura", "dis__gorunurb": "gorunurb", GIZLI: GIZLI})
    _yaz(durum / "ogrenme_adaylar.jsonl", "\n".join(json.dumps({"kurulum": "gorunura", "alindi": True, "r": 1.0}) for _ in range(7)))
    v = sv.topla(durum, simdi=SIMDI, ct_dizin=tmp_path / "ct_yok", set_yolu=sy, gizli={GIZLI})
    m = sv.metin_uret(v)
    assert "Dersler: aday 1 · etkin 1 · askıda 1 · emekli 1" in m
    assert "Açık, veri birikiyor (7/10 işlem)" in m
    assert "Açık, veri birikiyor (0/10 işlem)" in m
    assert GIZLI not in m
    _yaz(durum / "ogrenme_durum.json", {"egitim": {"gorunura": {"model": True, "n": 12, "zaman": "2026-11-19T00:00:00Z"}}})
    assert "Açık, işlemleri etkiliyor" in sv.metin_uret(sv.topla(durum, simdi=SIMDI, ct_dizin=tmp_path / "ct_yok", set_yolu=sy, gizli={GIZLI}))


def test_ml_kapali_ve_model_bekleniyor(tmp_path):
    og = {"ders": None, "durum": None, "karne": None, "filtre": [], "esleme": {}}
    assert sv._ml_ifadesi(og, {}, "x", SIMDI) == "Kapalı"
    og = {"ders": {}, "durum": {"egitim": {}}, "karne": None, "filtre": [], "veri_var": True}
    ek = {"adaylar": [{"kurulum": "x", "alindi": True, "r": 1.0}] * 10}
    assert sv._ml_ifadesi(og, ek, "x", SIMDI) == "Açık, model bekleniyor"


def test_rejim_yok_ve_veri_yok_satirlari(tmp_path):
    v, _, _ = _topla(tmp_path, rejim=False)
    v["hesaplar"][0]["maliyet"] = None
    m = sv.metin_uret(v)
    assert "Rejime göre: rejim verisi yok" in m
    assert "Maliyet / brüt K/Z: veri yok" in m
    bos = {"uretim": SIMDI, "hesaplar": [], "ct": None, "dusus": {"toplam": None, "ct": None}, "ders": None, "ml": []}
    m = sv.metin_uret(bos)
    assert m.count("veri yok") >= 4 and "ML: veri yok" in m


def test_ct_hesabi_dahil(tmp_path):
    durum, sy = _kur(tmp_path)
    _hesap(tmp_path / "ct", "c", 20, [{"net_pnl_yerel": "20", "yon": "short"}])
    v = sv.topla(durum, simdi=SIMDI, ct_dizin=tmp_path / "ct", set_yolu=sy, gizli={GIZLI})
    m = sv.metin_uret(v)
    assert "A) CT konsensüs hesabı" in m and "Toplam strateji: 3" in m and "- CT konsensüs hesabı: 1 kapanan" in m


def test_gizli_liste_okunamazsa_bos(tmp_path, monkeypatch):
    from motor.canli import pano
    durum, sy = _kur(tmp_path)
    monkeypatch.setattr(pano, "_gizli_adlar", lambda: pano._HepsiGizli())
    v = sv.topla(durum, simdi=SIMDI, ct_dizin=tmp_path / "ct_yok", set_yolu=sy)
    assert v["hesaplar"] == [] and v["ct"] is None


class Yanit:
    status_code, text = 200, ""


class Oturum:
    def __init__(self):
        self.cagrilar = []

    def post(self, url, data=None, files=None, timeout=None):
        self.cagrilar.append((url, data, files))
        return Yanit()


ENV = {"TELEGRAM_BOT_TOKEN": "123456:ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789", "TELEGRAM_CHAT_ID": "42"}


def test_kisa_metin_sessiz_mesaj(tmp_path):
    o = Oturum()
    assert sv.telegram_gonder(sv.BASLIK + "\nkısa", env=ENV, oturum=o) is True
    url, data, files = o.cagrilar[0]
    assert url.endswith("/sendMessage") and files is None and data["disable_notification"] == "true" and data["text"].startswith(sv.BASLIK)


def test_uzun_metin_sessiz_belge(tmp_path):
    o = Oturum()
    metin = sv.BASLIK + "\n" + "x" * 5000
    assert sv.telegram_gonder(metin, env=ENV, oturum=o) is True
    url, data, files = o.cagrilar[0]
    assert url.endswith("/sendDocument") and data["disable_notification"] == "true" and data["caption"] == sv.BASLIK
    assert files["document"][0] == "strateji_verisi.txt" and files["document"][1].decode("utf-8") == metin
    o2 = Oturum()
    sv.telegram_gonder(sv.BASLIK + "\n" + "y" * (sv.MESAJ_MAKS - len(sv.BASLIK) - 1), env=ENV, oturum=o2)
    assert o2.cagrilar[0][0].endswith("/sendMessage")                      # tam 4096: mesaj


def test_gonderim_yapilandirma_yoksa_ve_hata(tmp_path):
    assert sv.telegram_gonder("x", env={}, oturum=Oturum()) is False

    class Hata:
        def post(self, *a, **k):
            raise RuntimeError(ENV["TELEGRAM_BOT_TOKEN"])
    assert sv.telegram_gonder("x", env=ENV, oturum=Hata()) is False


def test_gonderim_kaydi_yazilir(tmp_path):
    env = {**ENV, "L3A_TELEGRAM_GONDERIM_DIZIN": str(tmp_path / "kayit")}
    assert sv.telegram_gonder(sv.BASLIK + "\nx", env=env, oturum=Oturum()) is True
    satir = json.loads((tmp_path / "kayit" / "telegram_gonderim.jsonl").read_text(encoding="utf-8").splitlines()[0])
    assert satir["ilk_satir"] == sv.BASLIK and satir["seviye"] == "INFO"


def test_tick_surum_basina_tek_sefer(tmp_path):
    durum, sy = _kur(tmp_path)
    gonderilen = []
    kw = dict(ct_dizin=tmp_path / "ct_yok", set_yolu=sy, gizli={GIZLI})

    def gonder(m):
        gonderilen.append(m)
        return True
    assert sv.tick(durum, "abc1234", gonder, 1_800_000_000.0, **kw) is True
    assert sv.tick(durum, "abc1234", gonder, 1_800_000_900.0, **kw) is False       # aynı sürüm: yeniden yok
    assert sv.tick(durum, "def5678", gonder, 1_800_001_000.0, **kw) is True        # yeni sürüm: bir kez daha
    assert len(gonderilen) == 2 and all(GIZLI not in m for m in gonderilen)
    assert json.loads((durum / sv.BAYRAK_DOSYA).read_text(encoding="utf-8"))["surumler"] == ["abc1234", "def5678"]


def test_tick_basarisiz_gonderimde_isaret_yok_ve_veri_yokken_bekler(tmp_path):
    durum, sy = _kur(tmp_path)
    kw = dict(ct_dizin=tmp_path / "ct_yok", set_yolu=sy, gizli={GIZLI})
    assert sv.tick(durum, "s1", lambda m: False, 1_800_000_000.0, **kw) is False
    assert not (durum / sv.BAYRAK_DOSYA).exists()
    assert sv.tick(durum, "s1", lambda m: True, 1_800_000_100.0, **kw) is True     # sonraki turda yeniden denenir
    bos = tmp_path / "bos"
    bos.mkdir()
    assert sv.tick(bos, "s1", lambda m: True, 1_800_000_000.0, **kw) is False       # henüz hesap verisi yok: işaret yok
    assert not (bos / sv.BAYRAK_DOSYA).exists()


def test_komut_servisi_tick_baglantisi(tmp_path):
    from motor.canli import telegram_komut as tk
    durum, sy = _kur(tmp_path)
    gonderilen = []
    svc = tk.KomutServisi.__new__(tk.KomutServisi)
    svc.durum, svc.ct, svc.set_yolu = durum, tmp_path / "ct_yok", sy
    svc.now = lambda: SIMDI
    svc.sha_fn = lambda: "abc"
    svc.sv_gonder = lambda m: gonderilen.append(m) or True
    svc._sv_son = None
    import motor.canli.pano as pano
    pano_gizli = pano._GIZLI
    pano._GIZLI = {GIZLI}
    try:
        svc._strateji_verisi_tick()
        svc._strateji_verisi_tick()                                                 # 10 dk içinde ikinci kontrol yok
    finally:
        pano._GIZLI = pano_gizli
    assert len(gonderilen) == 1 and GIZLI not in gonderilen[0]
