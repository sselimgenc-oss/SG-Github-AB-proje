"""Telegram komut servisi (motor/canli/telegram_komut.py) + durdurma bayrağı (paper.py). Ağ YOK: sahte istemci."""
import json
import re
from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pandas as pd
import pytest

from motor.backtest.motor import SembolKurallari
from motor.canli import paper as pp
from motor.canli import telegram_komut as tk
from motor.canli.paper_kaynak import TekrarKaynagi
from testler.test_paper_motor import duz, tanim

TOKEN = "123456789:AAH" + "x" * 30
CHAT = 4242
T0 = datetime(2026, 11, 19, 12, 0, tzinfo=timezone.utc)


class SahteIstemci:
    def __init__(self):
        self.giden, self.kuyruk = [], []

    def send_message(self, chat_id, text, *, disable_notification=False, reply_markup=None):
        self.giden.append((chat_id, text))
        return {"message_id": len(self.giden)}

    def get_updates(self, offset, timeout=30):
        return []


class SabitRng:
    def randbelow(self, n):
        return 1234


class Saat:
    def __init__(self):
        self.t = T0

    def __call__(self):
        return self.t


def kur(tmp_path):
    saat = Saat()
    c = SahteIstemci()
    s = tk.KomutServisi(c, CHAT, tmp_path / "durum", now_fn=saat, bayrak=tmp_path / "durum" / "DURDUR", ct_dizin=tmp_path / "ct",
                        canli_dizin=tmp_path / "canli", canli_ayar=tmp_path / "canli.json", rng=SabitRng(), sleep=lambda x: None)
    return s, c, saat


_uid = [0]


def mesaj(s, metin, chat=CHAT):
    _uid[0] += 1
    s.isle({"update_id": _uid[0], "message": {"chat": {"id": chat}, "from": {"id": chat}, "text": metin}})


def son(c):
    return c.giden[-1][1]


def test_yetkisiz_chat_yanit_almaz(tmp_path):
    s, c, _ = kur(tmp_path)
    for m in ("/durum", "/durdur", "/yardim", "1234"):
        mesaj(s, m, chat=999)
    assert c.giden == [] and s.yetkisiz == 4 and not s.bayrak.exists()


def test_durdur_kodsuz_uygulanmaz(tmp_path):
    s, c, _ = kur(tmp_path)
    mesaj(s, "/durdur")
    assert not s.bayrak.exists() and "Kod: 1234" in son(c)
    mesaj(s, "merhaba")                                  # kod yerine başka metin: yine uygulanmaz
    assert not s.bayrak.exists()


def test_yanlis_kod_uygulanmaz_ve_istegi_tuketir(tmp_path):
    s, c, _ = kur(tmp_path)
    mesaj(s, "/durdur")
    mesaj(s, "9999")
    assert not s.bayrak.exists() and "uygulanmadı" in son(c)
    mesaj(s, "1234")                                     # doğru kod ama istek tüketildi
    assert not s.bayrak.exists() and "Bekleyen onay yok" in son(c)


def test_120_sn_sonra_kod_gecersiz(tmp_path):
    s, c, saat = kur(tmp_path)
    mesaj(s, "/durdur")
    saat.t += timedelta(seconds=121)
    mesaj(s, "1234")
    assert not s.bayrak.exists() and "süresi doldu" in son(c)


def test_dogru_kodla_bayrak_yazilir_ve_devam_kaldirir(tmp_path):
    s, c, saat = kur(tmp_path)
    mesaj(s, "/durdur")
    saat.t += timedelta(seconds=30)
    mesaj(s, "1234")
    assert s.bayrak.exists() and json.loads(s.bayrak.read_text())["kaynak"] == "telegram" and "durduruldu" in son(c)
    mesaj(s, "/durdur")
    assert "zaten durdurulmuş" in son(c)
    mesaj(s, "/devam")
    assert s.bayrak.exists() and "Kod: 1234" in son(c)   # kodsuz kaldırılmaz
    mesaj(s, "/onay 1234")
    assert not s.bayrak.exists() and "kaldırıldı" in son(c)
    satirlar = [json.loads(x) for x in (tmp_path / "durum" / "telegram_komut" / "onay.denetim.jsonl").read_text().splitlines()]
    assert [x["sonuc"] for x in satirlar if x["olay"] == "dogrula"] == ["onaylandi", "onaylandi"]


def test_durum_ve_diger_cikti_token_icermez_ve_etiketli(tmp_path):
    s, c, _ = kur(tmp_path)
    durum = tmp_path / "durum"
    durum.mkdir(parents=True, exist_ok=True)
    (durum / "ozet.json").write_text(json.dumps({"ozsermaye": "10225.55", "gun_pnl": "-11.50", "sayaclar": {"acik_pozisyon": 3},
                                                 "risk": {"kill_switch": {"tetiklendi": False}}, "yazim_zamani": "2026-11-19T11:59:30Z"}))
    (durum / "kalp_atisi.json").write_text(json.dumps({"zaman": "2026-11-19T11:59:30Z", "durdu": False}))
    (tmp_path / "canli.json").write_text(json.dumps({"mod": "testnet", "anahtar_env": TOKEN}))     # token benzeri değer mesaja SIZMAMALI (okunan alan yalnız mod)
    (tmp_path / "canli").mkdir()
    (tmp_path / "canli" / "kalp_atisi.json").write_text(json.dumps({"zaman": "2026-11-19T11:58:00Z", "durdu": False}))
    for m in ("/durum", "/yardim", "/start", "/rapor", "/bilinmeyen", "/durdur"):
        mesaj(s, m)
    assert len(c.giden) == 6
    for _, metin in c.giden:
        assert metin.startswith("[1L3A] ") and TOKEN not in metin and "bot123456789" not in metin and len(metin) <= 3500
    d = c.giden[0][1]
    assert "10.225,55 $" in d and "açık pozisyon 3" in d and "−11,50 $" in d and "Yeni giriş: AÇIK" in d and "AKTİF" in d and "testnet" in d
    assert "Günlük rapor" in c.giden[3][1] and "henüz yok" not in c.giden[3][1]


def test_durum_bayrak_ve_bayat_kalp(tmp_path):
    s, c, _ = kur(tmp_path)
    durum = tmp_path / "durum"
    durum.mkdir(parents=True, exist_ok=True)
    (durum / "ozet.json").write_text(json.dumps({"ozsermaye": "1", "gun_pnl": "0", "sayaclar": {"acik_pozisyon": 0}}))
    (durum / "kalp_atisi.json").write_text(json.dumps({"zaman": "2026-11-19T10:00:00Z"}))
    s._bayrak_yaz()
    mesaj(s, "/durum")
    m = son(c)
    assert m.startswith("[1L3A] ⚠️") and "DURDURULDU" in m and "BAYAT" in m and "Canlı servis: durum dosyası yok" in m


def test_istemci_token_maskeler():
    assert TOKEN not in tk.tc.mask(f"https://api.telegram.org/bot{TOKEN}/getUpdates", TOKEN)


# ---------------------------------------------------------------------------- paper: bayrak varken yeni giriş yok, açık pozisyon stopla kapanır
def _paper(mum):
    t = tanim("a|AUSDT|1d", "AUSDT", grup="g1", pay="1.0", stop_yuzde=1.0)
    kur_ = {t.sembol: SembolKurallari(0.01, 0.001, 0.001, 5.0)}
    p = pp.Paper([t], TekrarKaynagi({("AUSDT", "1d"): mum}), kur_)
    return p, mum


def _dusus_verisi():
    m = duz(14, 100.0, dalga=0.0)
    m.iloc[7, m.columns.get_loc("dusuk")] = 90.0         # 7. mumda stop (99) delinir
    return m


def test_bayrak_yokken_yeniden_giris_olur_kontrol():
    p, m = _paper(_dusus_verisi())
    p.baslat(m.index[3])
    p.adim(m.index[-1] + pd.Timedelta(days=1))
    assert len(p.motor.islemler) >= 1 and len(p.motor.acik) == 1       # kapanıp yeniden girer (HepsiLong)


def test_bayrak_varken_yeni_giris_yok_acik_pozisyon_stopla_kapanir():
    p, m = _paper(_dusus_verisi())
    p.baslat(m.index[3])
    p.adim(m.index[5] + pd.Timedelta(days=1))
    assert len(p.motor.acik) == 1 and not p.motor.islemler            # bayrak yok: pozisyon açık
    pp.giris_durdur_uygula(p, True)                                    # /durdur
    p.adim(m.index[-1] + pd.Timedelta(days=1))
    pp.giris_durdur_uygula(p, True)
    assert len(p.motor.islemler) == 1 and p.motor.islemler[0]["cikis_nedeni"] == "stop"      # açık pozisyon kendi stop'uyla kapandı
    assert not p.motor.acik                                           # yeniden giriş YOK
    assert all(k.giris_emri is None for k in p.motor.tum_kollar)       # bekleyen giriş emri yok (canlı yürütücü bundan niyet türetir)
    pp.giris_durdur_uygula(p, False)                                   # /devam: motor engeli kalkar
    assert p.motor.islem_baslangic is None


def test_bayrak_bastan_varsa_hic_giris_olmaz_ve_devamda_girer():
    p, m = _paper(duz(14, 100.0, dalga=0.0))
    p.baslat(m.index[3])
    pp.giris_durdur_uygula(p, True)
    p.adim(m.index[8] + pd.Timedelta(days=1))
    pp.giris_durdur_uygula(p, True)
    assert not p.motor.acik and not p.motor.islemler
    pp.giris_durdur_uygula(p, False)
    p.adim(m.index[-1] + pd.Timedelta(days=1))
    assert len(p.motor.acik) == 1


def test_durdur_dosyasi_env(tmp_path):
    assert str(pp.durdur_dosyasi({})) == "/var/lib/1l3a-paper/durum/DURDUR"
    assert pp.durdur_dosyasi({"L3A_DURDUR_DOSYA": str(tmp_path / "x")}) == tmp_path / "x"


def test_cekirdek_zaman_asimi_demeti_urllibe_tek_sayi_gider(monkeypatch):
    """ortak_ogrenme 1.2.1: demet (bağlantı, okuma) urllib'e tek sayı olarak gitmeli (1.2.0'da TypeError -> 'transient 0')."""
    from motor.ortak_ogrenme import telegram_cekirdek as tc
    gelen = {}
    class Y:
        status = 200
        def read(self): return b'{"ok": true, "result": []}'
        def __enter__(self): return self
        def __exit__(self, *a): return False
    def ac(req, timeout=None):
        gelen["t"] = timeout
        return Y()
    monkeypatch.setattr(tc.urllib.request, "urlopen", ac)
    tc.TelegramClient("x").get_updates(None, timeout=30)
    assert isinstance(gelen["t"], (int, float))


# ---------------------------------------------------------------------------- /rapor, /kurulumlar, /ders, /hepsini_kapat, /kademe, /onayla
from motor.canli import paper_v2 as v2
from motor.canli.paper_motor import PaperMotor

SET = json.loads(v2.SET_YOLU.read_text(encoding="utf-8"))
KAYITLAR = [(v2.hesap_adi(k), v2.hesap_dizin_adi(v2.hesap_adi(k)), v2.gorunur_mu(k)) for k in SET["stratejiler"]]
GIZLI = [k for k, _, g in KAYITLAR if not g]
GIZLI_PARCA = ["lube", "670", "574", "730"]          # gizli 4 hesabın adları (hiçbir çıktıda görünmemeli)


def _yaz(yol, veri):
    yol.parent.mkdir(parents=True, exist_ok=True)
    yol.write_text(json.dumps(veri) if not isinstance(veri, str) else veri, encoding="utf-8")


def _hesap(dizin, ozs, toplam, acik=1, son="2026-11-19T10:00:00Z"):
    _yaz(dizin / "ozet.json", {"ozsermaye": str(ozs), "baslangic_ozsermaye": "10000", "gun_pnl": "5", "toplam_pnl": str(toplam), "zirve_ozsermaye": str(ozs),
                               "sayaclar": {"acik_pozisyon": acik, "kapanan_islem": 3}})
    _yaz(dizin / "islemler.jsonl", json.dumps({"zaman": son, "cikis_zamani": son, "giris_zamani": son, "net_pnl_yerel": "1"}) + "\n")


@pytest.fixture
def dolu(tmp_path):
    s, c, saat = kur(tmp_path)
    d = tmp_path / "durum"
    for i, (_, klasor, _) in enumerate(KAYITLAR):
        _hesap(d / "hesaplar" / klasor, 10000 + i, 100 + i)
    _hesap(tmp_path / "ct", 9000, -50, acik=2)
    ad = tmp_path / "aday" / "swing__korelasyon-ivmesi__q"
    _hesap(ad, 10100, 100)
    s.aday = tmp_path / "aday"
    ders = {"b:dis_ewo_ema_ofset": {"status": "alive", "born": "2026-11-10", "effect": 0.12, "n": 8},
            "c:dis_gauss_stoch_eth": {"status": "candidate", "born": "2026-11-18", "effect": None, "n": 0},
            "r:dis_hma_atr_rider": {"status": "retired", "born": "2026-11-01", "retired_day": "2026-11-17"},
            "r:eski": {"status": "retired", "born": "2026-10-01", "retired_day": "2026-11-01"},
            "g:dis_lube": {"status": "alive", "born": "2026-11-10", "effect": 0.2, "n": 9}}
    _yaz(d / "ogrenme_ders.json", ders)
    _yaz(d / "ogrenme_durum.json", {"drift_uyari": ["dis_gauss_stoch_eth"], "egitim": {}})
    _yaz(d / "ogrenme_modeller" / "dis_ewo_ema_ofset.json", {"x": 1})
    return s, c, saat, tmp_path


def test_yeni_komutlar_yetkisiz_chat_yanit_almaz(tmp_path):
    s, c, _ = kur(tmp_path)
    for m in ("/rapor", "/kurulumlar", "/ders", "/hepsini_kapat", "/kademe", "/kademe_devam", "/onayla 1", "/reddet 1", "1234"):
        mesaj(s, m, chat=999)
    assert c.giden == [] and not s.bayrak.exists() and not s.hepsini_dosya.exists()


def test_rapor_kurulumlar_ders_gizli_hesap_adi_gecmez(dolu):
    s, c, _, tmp = dolu
    for m in ("/rapor", "/kurulumlar", "/ders", "/yardim"):
        mesaj(s, m)
    hepsi = "\n".join(t for _, t in c.giden)
    for g in GIZLI_PARCA:
        assert g not in hepsi.lower(), g
    for _, metin in c.giden:
        assert metin.startswith("[1L3A] ") and len(metin) <= 3500
    rapor, kur_, ders = c.giden[0][1], c.giden[1][1], c.giden[2][1]
    assert "Diğer hesaplar (4)" in rapor and "CT konsensüs hesabı" in rapor
    assert "Diğer hesaplar (4)" in kur_ and "CT konsensüs hesabı" in kur_ and "korelasyon ivmesi" in kur_.lower() and "gauss" in kur_.lower()
    assert "ML filtre aktif" in kur_ and "drift UYARI" in kur_ and "ML filtre pasif" in kur_       # ewo filtreli, gauss drift uyarılı
    assert "b:dis_ewo_ema_ofset [yaşayan]" in ders and "c:dis_gauss_stoch_eth [aday]" in ders and "r:dis_hma_atr_rider [emekli 2026-11-17]" in ders
    assert "r:eski" not in ders and "g:dis_lube" not in ders and "Diğer hesaplar: 1" in ders          # 7 günden eski emekli yok, gizli ders adsız sayıya


def test_kurulumlar_ve_ders_veri_yokken_dusmez(tmp_path):
    s, c, _ = kur(tmp_path)
    for m in ("/rapor", "/kurulumlar", "/ders"):
        mesaj(s, m)
    assert len(c.giden) == 3 and "Henüz veri yok" in c.giden[1][1] and "Henüz veri yok" in c.giden[2][1]


def test_kademe_onayla_bilgi_yanitlari(tmp_path):
    s, c, _ = kur(tmp_path)
    for m in ("/kademe", "/kademe_devam", "/onayla 12", "/reddet 12"):
        mesaj(s, m)
    assert "kademe yok" in c.giden[0][1] and "kullanıcı kararı" in c.giden[0][1] and c.giden[1][1] == c.giden[0][1]    # /kademe_devam onay istemez
    assert "Onay bekleyen yok" in c.giden[2][1] and "Onay bekleyen yok" in c.giden[3][1] and "Kod:" not in "".join(t for _, t in c.giden)


def test_yardim_yeni_komutlari_listeler(tmp_path):
    s, c, _ = kur(tmp_path)
    mesaj(s, "/yardim")
    for k in ("/rapor", "/kurulumlar", "/ders", "/hepsini_kapat", "/kademe_devam", "/onayla", "/reddet"):
        assert k in son(c)
    assert "Henüz yok" not in son(c)


def test_hepsini_kapat_kodsuz_uygulanmaz(tmp_path):
    s, c, _ = kur(tmp_path)
    mesaj(s, "/hepsini_kapat")
    assert "Kod: 1234" in son(c) and not s.hepsini_dosya.exists() and not s.bayrak.exists()
    mesaj(s, "9999")                                                    # yanlış kod
    assert "uygulanmadı" in son(c) and not s.hepsini_dosya.exists() and not s.bayrak.exists()


def test_hepsini_kapat_dogru_kodla_istek_dosyasi_ve_durdur(tmp_path):
    s, c, saat = kur(tmp_path)
    mesaj(s, "/hepsini_kapat")
    saat.t += timedelta(seconds=20)
    mesaj(s, "1234")
    assert s.hepsini_dosya.exists() and s.hepsini_dosya.name == "HEPSINI_KAPAT" and s.hepsini_dosya.parent == s.bayrak.parent
    assert s.bayrak.exists() and "isteği yazıldı" in son(c) and "canlı gerçek para" not in son(c)      # mod canli değil: uyarı yok
    mesaj(s, "/hepsini_kapat")
    assert "zaten verilmiş" in son(c)


def test_hepsini_kapat_canli_modda_gercek_para_uyarisi(tmp_path):
    s, c, _ = kur(tmp_path)
    (tmp_path / "canli.json").write_text(json.dumps({"mod": "canli"}))
    mesaj(s, "/hepsini_kapat")
    assert "borsadaki pozisyonlar da kapatılır" in son(c)
    mesaj(s, "1234")
    assert "borsadaki pozisyonlar da kapatılır" in son(c)


def test_hepsini_kapat_120sn_sonra_gecersiz(tmp_path):
    s, c, saat = kur(tmp_path)
    mesaj(s, "/hepsini_kapat")
    saat.t += timedelta(seconds=121)
    mesaj(s, "1234")
    assert not s.hepsini_dosya.exists() and not s.bayrak.exists() and "süresi doldu" in son(c)


# ---------------------------------------------------------------------------- paper: HEPSINI_KAPAT isteği
def _istek(tmp_path, zaman="2026-11-19T12:00:00Z"):
    d = tmp_path / "durum"
    d.mkdir(exist_ok=True)
    env = {"L3A_DURDUR_DOSYA": str(d / "DURDUR")}
    (d / "HEPSINI_KAPAT").write_text(json.dumps({"zaman": zaman, "kaynak": "telegram"}))
    return d, env


def test_paper_hepsini_kapat_pozisyonlari_kapatir_dosyayi_siler_yeni_giris_yok(tmp_path):
    p, m = _paper(duz(14, 100.0, dalga=0.0))
    p.baslat(m.index[3])
    p.adim(m.index[5] + pd.Timedelta(days=1))
    assert len(p.motor.acik) == 1 and not p.motor.islemler
    d, env = _istek(tmp_path)
    olaylar = []
    p.bildirim = lambda tur, mesaj: olaylar.append((tur, mesaj))
    z0 = pd.Timestamp("2026-11-19T12:00:30Z")
    assert pp.hepsini_kapat_uygula(p, z0, d, env=env) == 1
    assert not p.motor.acik and len(p.motor.islemler) == 1 and p.motor.islemler[0]["cikis_nedeni"] == "hepsini_kapat"
    assert olaylar and olaylar[0][0] == "hepsini_kapat" and "1 açık pozisyon" in olaylar[0][1]
    assert (d / "HEPSINI_KAPAT").exists()                              # 120 sn dolmadan silinmez (aynı dizini izleyen diğer süreçler de görsün)
    assert pp.hepsini_kapat_uygula(p, z0 + pd.Timedelta(seconds=30), d, env=env) is None      # aynı istek ikinci kez işlenmez
    assert len(p.motor.islemler) == 1 and len(olaylar) == 1
    assert pp.hepsini_kapat_uygula(p, z0 + pd.Timedelta(seconds=130), d, env=env) is None
    assert not (d / "HEPSINI_KAPAT").exists()                          # süre dolunca dosya silinir
    pp.giris_durdur_uygula(p, True)                                    # DURDUR bayrağı: kapanıştan sonra yeni giriş yok
    p.adim(m.index[-1] + pd.Timedelta(days=1))
    assert not p.motor.acik and len(p.motor.islemler) == 1


def test_paper_hepsini_kapat_acik_pozisyon_yoksa_bile_dosya_islenir_ve_silinir(tmp_path):
    p, m = _paper(duz(14, 100.0, dalga=0.0))
    p.baslat(m.index[3])
    d, env = _istek(tmp_path)
    p.motor.acik.clear()
    assert pp.hepsini_kapat_uygula(p, pd.Timestamp("2026-11-19T12:05:00Z"), d, env=env) == 0
    assert not (d / "HEPSINI_KAPAT").exists()                          # istek 5 dk önce: işlendi, süre dolmuş -> silindi


def test_paper_hepsini_kapat_dosyasi_yoksa_hicbir_sey_olmaz(tmp_path):
    p, m = _paper(duz(14, 100.0, dalga=0.0))
    p.baslat(m.index[3])
    d = tmp_path / "durum"
    d.mkdir()
    assert pp.hepsini_kapat_uygula(p, pd.Timestamp("2026-11-19T12:00:00Z"), d, env={"L3A_DURDUR_DOSYA": str(d / "DURDUR")}) is None


def test_hepsini_kapat_dosyasi_durdur_ile_ayni_dizin(tmp_path):
    assert pp.hepsini_kapat_dosyasi({}) == __import__("pathlib").Path("/var/lib/1l3a-paper/durum/HEPSINI_KAPAT")
    assert pp.hepsini_kapat_dosyasi({"L3A_DURDUR_DOSYA": str(tmp_path / "x" / "DURDUR")}) == tmp_path / "x" / "HEPSINI_KAPAT"


def test_yanitlar_seviye_kelimesiz_kisa_ve_kod_adsiz(tmp_path):
    import re
    s, c, _ = kur(tmp_path)
    for komut, maks in (("/durum", 6), ("/yardim", 12), ("/rapor", 12), ("/kurulumlar", 12), ("/durdur", 6)):
        mesaj(s, komut)
        m = son(c)
        assert m.startswith("[1L3A] ") and len(m.split("\n")) <= maks, komut
        assert not re.search(r"\b(INFO|WARN|CRIT)\b", m.split("\n")[0]) and "ct_konsensus" not in m, komut
