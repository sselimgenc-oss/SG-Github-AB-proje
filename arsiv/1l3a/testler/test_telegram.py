"""Telegram mesajları: biçim (HTML geçerli/kaçışlı, TSİ, Türkçe sayı), standart ilk satır [1L3A] + önem, teknik olaylar gitmez, sel koruması, 3500 sınırı, dakikada 15, tekrar önleme."""
import re
from html.parser import HTMLParser

import pytest

from motor.canli import telegram as tg


class _Kontrol(HTMLParser):
    def __init__(self):
        super().__init__()
        self.yigin, self.hata = [], False

    def handle_starttag(self, t, a):
        self.yigin.append(t)

    def handle_endtag(self, t):
        if not self.yigin or self.yigin.pop() != t:
            self.hata = True


def html_gecerli(m: str) -> bool:
    k = _Kontrol()
    k.feed(m)
    k.close()
    return not k.hata and not k.yigin and len(m) <= 3500 and not re.search(r"<(?!/?(b|i)>)", m)


KAPANAN = {"zaman": "2026-11-07T16:55:00Z", "kimlik": "dis__dual-thrust|ETHUSDT|30m", "sembol": "ETHUSDT", "yon": "long",
           "giris_zamani": "2026-11-07T10:00:00Z", "giris_fiyati": "2450.5", "cikis_zamani": "2026-11-07T16:55:00Z",
           "cikis_fiyati": "2512.75", "miktar": "2", "r": 1.5, "net_pnl_yerel": "120.30", "set_katki_usd": "120.30", "cikis_nedeni": "hedef"}
ACIK = {"kimlik": "pf__kesit_ls|kripto|1d", "sembol": "SOLUSDT", "yon": "short", "miktar": "10", "giris_fiyati": "150.25", "mark_fiyat": "148",
        "giris_zamani": "2026-11-07T00:00:00Z", "stop": "160", "kz": "22.5", "kz_oran": 0.015, "nominal": "1480.00", "kasaya_orani": 0.15,
        "stop_riski": "100"}


def ozet(**ek):
    st = [{"kimlik": "dis__dual-thrust|ETHUSDT|30m", "ozsermaye_katkisi": "120.30", "islem_sayisi": 3, "acik_pozisyonlar": [], "durum": "calisiyor"},
          {"kimlik": "pf__kesit_ls|kripto|1d", "ozsermaye_katkisi": "-40.00", "islem_sayisi": 1, "acik_pozisyonlar": [ACIK], "durum": "calisiyor"}]
    st += [{"kimlik": k, "ozsermaye_katkisi": "0.00", "islem_sayisi": 0, "acik_pozisyonlar": [], "durum": "calisiyor"}
           for k in ("pf__rotasyon|hepsi|1d", "pf__kanarya|hisse_emtia|1d", "swing__cci-esik|SOLUSDT|1d")]
    oz = {"zaman": "2026-11-07T16:55:00Z", "ozsermaye": "10080.30", "gun_pnl": "80.30", "gun_getiri": 0.0081, "hafta_pnl": None,
          "toplam_pnl": "80.30", "toplam_getiri": 0.00803, "zirveden_dusus": 0.012,
          "risk": {"gunluk_kayip": {"deger": 0.0, "limit": 0.03}, "kill_switch": {"limit": 0.2}}}
    return {"ozet": oz, "stratejiler": {"stratejiler": st}, "saglik": {"uyarilar": ek.get("uyarilar", []), "durum": ek.get("durum", "ok")}}


def test_sayi_bicimi():
    assert tg.usd("1234.5") == "1.234,50 $" and tg.usd("-5", True) == "−5,00 $" and tg.usd("0", True) == "+0,00 $"
    assert tg.yuzde(0.0125) == "+%1,25" and tg.yuzde(-0.2, False, 0) == "%20" and tg.yuzde(None) == "—"
    assert tg.fiyat("2450.5") == "2.450,50" and tg.fiyat("0.0123") == "0,0123" and tg.fiyat("150.25") == "150,25"


def test_tsi_ve_ad():
    assert tg.tsi_saat("2026-11-07T16:55:00Z") == "07.11 19:55" and tg.tsi_gun("2026-11-07T16:55:00Z") == "7 Kasım"
    assert tg.ad("dis__dual-thrust|ETHUSDT|30m") == "Dual Thrust · ETH 30 dk" and tg.ad("bilinmeyen|X|1d") == "Bilinmeyen · X 1G" and tg.ad("ct_konsensus|BTCUSDT|15m") == "CT konsensüs · BTC 15 dk"
    from motor.canli import paper_sinyal  # noqa: F401
    import json
    from pathlib import Path
    kimlikler = [s["kimlik"] for s in json.loads((Path(__file__).parent.parent / "stratejiler" / "final_set.json").read_text(encoding="utf-8"))["stratejiler"]]
    assert len(kimlikler) == 7 and all(k in tg.AD for k in kimlikler)


def test_islem_kapandi_kar_ve_zarar():
    m = tg.islem_kapandi_metni(KAPANAN)
    assert m == "[1L3A] ✅ ETH long kapandı · Dual Thrust · ETH 30 dk\n+120,30 $ (+%2,5) · kâr al" and html_gecerli(m)
    z = tg.islem_kapandi_metni({**KAPANAN, "net_pnl_yerel": "-12.40", "cikis_nedeni": "stop", "sembol": "SOLUSDT", "giris_fiyati": "152.3", "miktar": "3.28"})
    assert z == "[1L3A] 🔻 SOL long kapandı · Dual Thrust · ETH 30 dk\n−12,40 $ (−%2,5) · stop" and tg.onem(z) == "INFO"
    assert "Dual" not in tg.islem_kapandi_metni(KAPANAN, gorunur=False) and "Diğer hesap" in tg.islem_kapandi_metni(KAPANAN, gorunur=False)


def test_islem_acildi():
    m = tg.islem_acildi_metni(ACIK)
    assert m == "[1L3A] 🟠 SOL short açıldı · Kesit L/S · Kripto\nGiriş 150,25 $ · Tutar 1.480 $ · Stop 160,00 $" and html_gecerli(m)
    assert tg.onem(m) == "INFO"                                                        # 🟠 short: sessiz (🔴 yalnız kritik)
    g = tg.islem_acildi_metni({**ACIK, "yon": "long"}, gorunur=False)
    assert g.startswith("[1L3A] 🟢 SOL long açıldı · Diğer hesap\n") and "Kesit" not in g and "USDT" not in g


def test_html_kacis():
    m = tg.islem_kapandi_metni({**KAPANAN, "sembol": "<b>x</b>&y"})
    assert "&lt;b&gt;x&lt;/b&gt;&amp;y" in m and "<b>x" not in m
    u = tg.uyari_metni("veri_bosluk", "<i>hata</i> & %12.50")
    assert "&lt;i&gt;" in u and "%12,50" in u and html_gecerli(u)


def test_gunluk_ozet():
    m = tg.ozet_metni(ozet(), diger=(3, "41.20"))
    assert html_gecerli(m) and "📊 <b>Günlük özet — 7 Kasım</b>" in m and "10.080,30 $" in m and "Bugün: +80,30 $ (+%0,81)" in m
    assert "Başlangıçtan beri +80,30 $ (+%0,80)" in m and "Günlük kayıp %0,0 / sınır %3" in m
    assert "👥 Diğer hesaplar (3): toplam +41,20 $" in m and "gizli" not in m.lower() and "_" not in m
    assert "Açık 1:" in m and "SOL" in m and "USDT" not in m and "En iyi Dual Thrust · ETH 30 dk +120,30 $" in m
    assert len(m.split("\n")) <= 12 and "🚨" not in m
    a = tg.ozet_metni(ozet(uyarilar=["BEKLENTİ ALARMI: swing__cci-esik|SOLUSDT|1d 4 hafta net getiri -%12.5"], durum="veri_bayat"))
    assert "🚨 BEKLENTİ ALARMI: CCI Eşik · SOL 1G" in a and "-%12,5" in a and "veri bayat" in a and html_gecerli(a)
    assert len(tg.ozet_metni(ozet(uyarilar=["u"] * 20, durum="veri_bayat")).split("\n")) <= 12


def test_ozet_3500():
    o = ozet(uyarilar=["x" * 300] * 40)
    assert len(tg.ozet_metni(o)) <= 3500
    assert len(tg.kirp("a\n" * 5000)) <= 3500


def test_standart_ilk_satir_ve_onem():
    assert tg.islem_kapandi_metni(KAPANAN).startswith("[1L3A] ") and tg.onem(tg.islem_kapandi_metni(KAPANAN)) == "INFO"
    assert tg.ozet_metni(ozet()).startswith("[1L3A] 📊") and tg.onem(tg.ozet_metni(ozet())) == "INFO"
    assert tg.uyari_metni("kill_switch", "x").split("\n")[0].startswith("[1L3A] 🔴 ")
    assert tg.uyari_metni("binance_hata", "x").split("\n")[0].startswith("[1L3A] ⚠️ ")
    assert tg.onem(tg.uyari_metni("kill_switch")) == "CRIT" and tg.onem(tg.uyari_metni("binance_hata")) == "WARN"
    assert tg.uyari_metni("giris_devam", "x").startswith("[1L3A] ▶️") and tg.onem(tg.uyari_metni("giris_devam")) == "INFO"
    for tur in tg.UYARI:                                                                  # başlıkta seviye kelimesi/kod adı yok
        assert not re.search(r"\b(INFO|WARN|CRIT)\b", tg.uyari_metni(tur).split("\n")[0])
    assert tg.onem("[1L3A] CRIT\nx") == "CRIT" and tg.onem("başlıksız CRIT") == "INFO"     # eski biçim okunmaya devam eder


def test_gunluk_ozet_gun_ici_itibariyla():
    m = tg.ozet_metni(ozet(), itibaren="21:00")
    assert "Günlük özet — 7 Kasım (21:00 itibarıyla)" in m and "Bugün: +80,30 $" in m and html_gecerli(m)


class _Oturum:
    def __init__(self):
        self.giden = []

    def post(self, url, data=None, timeout=None):
        self.giden.append(data)
        return type("R", (), {"status_code": 200, "text": ""})()


ENV = {"TELEGRAM_BOT_TOKEN": "123456:" + "A" * 30, "TELEGRAM_CHAT_ID": "42"}


def _sifirla():
    tg._pencere.clear()
    tg._son_metin.clear()
    tg._son_gonderim[0] = 0.0
    tg._ortak_onbellek.clear()


def test_gonder_sessiz_info_ve_tekrar_onleme():
    _sifirla()
    o = _Oturum()
    assert tg.gonder("[1L3A] INFO\na", ENV, o, uyku=lambda s: None, saat=lambda: 1000.0)
    assert o.giden[0]["disable_notification"] == "true"
    assert not tg.gonder("[1L3A] INFO\na", ENV, o, uyku=lambda s: None, saat=lambda: 1100.0)         # aynı metin 10 dk içinde atılır
    assert tg.gonder("[1L3A] INFO\na", ENV, o, uyku=lambda s: None, saat=lambda: 1700.0)             # 10 dk sonra gider
    assert tg.gonder("[1L3A] CRIT\nb", ENV, o, uyku=lambda s: None, saat=lambda: 1701.0) and o.giden[-1]["disable_notification"] == "false"


def test_gonder_dakikada_15_info_asarsa_atilir_crit_gider():
    _sifirla()
    o = _Oturum()
    t = [5000.0]
    kw = dict(oturum=o, uyku=lambda s: None, saat=lambda: t[0])
    sonuc = [tg.gonder(f"[1L3A] INFO\nm{i}", ENV, **kw) for i in range(20)]
    assert sum(sonuc) == 15 and len(o.giden) == 15
    assert tg.gonder("[1L3A] CRIT\nkritik", ENV, **kw)                       # CRIT sınıra takılmaz
    t[0] += 61
    assert tg.gonder("[1L3A] INFO\nyeni", ENV, **kw)                         # pencere boşalınca gider


def test_uyarilar():
    for tur in ("kill_switch", "gunluk_limit", "veri_bosluk", "binance_hata", "ayar_yenileme", "beklenti_alarmi"):
        m = tg.uyari_metni(tur, "ornek mesaj")
        assert html_gecerli(m) and ("🔴" in m or "⚠️" in m) and "🔧" in m and "👉" in m and len(m.split("\n")) <= 6
    assert "🔴" in tg.uyari_metni("kill_switch", "x") and tg.olay_metni("ws_koptu", "x") is None


def test_baslangic():
    m = tg.baslangic_metni(7, "10000.00")                                                # yalnız log metni: Telegram'a gitmez
    assert tg.onem(m) == "INFO" and tg.etiketli(m) == m
    g = []
    orijinal = tg.gonder
    tg.gonder = lambda metin, *a, **k: g.append(metin) or True
    try:
        assert tg.baslangic_kaydet(7, "10000", birlestir=False) is False
        assert tg.baslangic_kaydet(7, "10000", birlestir=True) is False
    finally:
        tg.gonder = orijinal
    assert g == []


class Sahte:
    def __init__(self):
        self.t, self.giden = 1000.0, []

    def saat(self):
        return self.t

    def gonder(self, m):
        self.giden.append(m)
        return True

    def bld(self):
        return tg.Bildirimci(self.gonder, self.saat)


def test_teknik_olaylar_gonderilmez():
    s = Sahte()
    b = s.bld()
    for tur in ("baslangic", "yeniden_baslatma", "ws_baglandi", "ws_koptu", "ws_yeniden_baglandi", "ws_24sa_yenileme", "veri_uyusmazlik"):
        b.olay(tur, "x")
    assert s.giden == []


def test_ws_10dk_sonra_tek_uyari():
    s = Sahte()
    b = s.bld()
    b.olay("ws_koptu", "x")
    s.t += 300
    b.olay("ws_koptu", "yeniden deneme")
    assert not b.kontrol() and s.giden == []
    s.t += 400
    assert b.kontrol() and len(s.giden) == 1 and "10 dakikadır" in s.giden[0]
    s.t += 60
    assert not b.kontrol() and len(s.giden) == 1


def test_ws_saatte_3_kopma():
    s = Sahte()
    b = s.bld()
    for _ in range(3):
        b.olay("ws_koptu", "x")
        s.t += 60
        b.olay("ws_yeniden_baglandi", "x")
        s.t += 60
    assert len(s.giden) == 1 and "3 kopma" in s.giden[0]


def test_sel_korumasi_6_saat():
    s = Sahte()
    b = s.bld()
    b.olay("binance_hata", "a")
    s.t += 1900
    b.olay("binance_hata", "b")                      # eski 30 dk penceresi geçti ama 6 saat dolmadı
    assert len(s.giden) == 1
    b.olay("veri_bosluk", "farklı tür")
    assert len(s.giden) == 2
    s.t += 6 * 3600
    b.olay("binance_hata", "c")
    assert len(s.giden) == 3
    for _ in range(3):
        b.olay("kill_switch", "k")                   # kill switch her zaman gider
    assert len(s.giden) == 6


def test_crit_turleri_asla_bastirilmaz():
    s = Sahte()
    b = s.bld()
    for tur in ("motor_hatasi", "motor_durdu", "askida_kapatma", "servis_hatasi"):
        for _ in range(3):
            b.olay(tur, "ayni")
    assert len(s.giden) == 12 and all(m.startswith("[1L3A] 🔴") for m in s.giden)


def test_kalici_tekrar_yeniden_baslatmada_surer(tmp_path):
    """İki ayrı Bildirimci (= yeniden başlayan süreç) aynı ortak dosyayı kullanır: 6 saat içinde aynı uyarı tekrar gitmez."""
    s = Sahte()
    o1 = tg.OrtakDurum(tmp_path / "ortak")
    tg.Bildirimci(s.gonder, s.saat, ortak=o1).olay("binance_hata", "x")
    assert len(s.giden) == 1
    o2 = tg.OrtakDurum(tmp_path / "ortak")
    b2 = tg.Bildirimci(s.gonder, s.saat, ortak=o2)
    s.t += 3600
    b2.olay("binance_hata", "x")
    assert len(s.giden) == 1
    s.t += 6 * 3600
    b2.olay("binance_hata", "x")
    assert len(s.giden) == 2


def test_veri_yok_farkli_mesaj_ayri_anahtar():
    s = Sahte()
    b = s.bld()
    b.olay("veri_yok", "A: veri eksik")
    b.olay("veri_yok", "B: veri eksik")
    b.olay("veri_yok", "A: veri eksik")
    assert len(s.giden) == 2


def test_islem_disi_sembol_bilgisi_telegram_a_gitmez(tmp_path):
    s = Sahte()
    ortak = tg.OrtakDurum(tmp_path / "o")
    b = tg.Bildirimci(s.gonder, s.saat, ortak=ortak)
    olay = "TONUSDT borsada işleme kapandı, listeden çıkarıldı"
    b.olay("evren_kapali", olay)
    b.olay("veri_yok", "dis__x: TONUSDT durumu SETTLING (TRADING değil)")
    b.olay("veri_yok", "BEKLENMEYEN evren düşmesi: TON: TONUSDT durumu SETTLING (TRADING değil) → 2 stratejinin evreninden çıkarıldı (a, b)")
    s.t = 10_000.0
    b.kontrol()
    s.t += 4000
    b.kontrol()
    assert s.giden == []                                                              # bilgi/saatlik not artık yok: yalnız log
    b.olay("veri_yok", "dis__x: ABCUSDT yerel veri yok; TONUSDT durumu SETTLING (TRADING değil)")   # karışık neden: normal uyarı
    assert len(s.giden) == 1 and s.giden[0].startswith("[1L3A] ⚠️")


def test_askida_acik_pozisyon_yoksa_not_varsa_uyari():
    s = Sahte()
    b = s.bld()
    b.olay("askida", "X ASKIDA: veri yok; açık pozisyon yok")
    assert s.giden == []
    b.olay("askida", "Y ASKIDA: veri yok; açık pozisyon son bilinen fiyatla donduruldu")
    assert len(s.giden) == 1 and s.giden[0].startswith("[1L3A] ⚠️")


def test_saatlik_not_kalkti_bilgi_yalniz_log(tmp_path):
    s = Sahte()
    s.t = 100_000.0
    b = tg.Bildirimci(s.gonder, s.saat, ortak=tg.OrtakDurum(tmp_path / "o"))
    assert not b.bilgi("a") and not b.bilgi("b")
    b.kontrol()
    s.t += 7200
    b.kontrol()
    assert s.giden == []


def test_baslangic_mesajlari_telegram_a_gitmez(tmp_path):
    """paper + ct + aday başlangıcı: hiçbir mesaj gitmez (yalnız log)."""
    s = Sahte()
    s.t = 100_000.0
    ortak = tg.OrtakDurum(tmp_path / "o")
    for ad, n in (("paper", 10), ("ct_konsensus", 1), ("aday:xyz", 1)):
        eski = tg.SERVIS_ADI
        tg.SERVIS_ADI = ad
        try:
            tg.baslangic_kaydet(n, "10000", ortak=ortak, saat=s.saat)
        finally:
            tg.SERVIS_ADI = eski
    s.t += 120
    tg.Bildirimci(s.gonder, s.saat, ortak=ortak).kontrol()
    assert s.giden == []


def test_baslangic_tek_servis_gitmez(tmp_path):
    s = Sahte()
    ortak = tg.OrtakDurum(tmp_path / "o")
    s.t = 1000.0
    tg.baslangic_kaydet(7, "10000", ortak=ortak, saat=s.saat)
    s.t += 61
    tg.Bildirimci(s.gonder, s.saat, ortak=ortak).kontrol()
    assert s.giden == []


def test_gonder_warn_6_saat_kalici_crit_her_zaman(tmp_path, monkeypatch):
    _sifirla()
    monkeypatch.setenv("L3A_ORTAK_BILDIRIM", str(tmp_path / "o"))
    o = _Oturum()
    kw = dict(oturum=o, uyku=lambda s: None, saat=lambda: 1000.0)
    assert tg.gonder("[1L3A] WARN\nw", ENV, **kw)
    assert not tg.gonder("[1L3A] WARN\nw", ENV, **kw)
    tg._ortak_onbellek.clear()                                                         # süreç yeniden başladı: dosya durur
    assert not tg.gonder("[1L3A] WARN\nw", ENV, **kw)
    assert tg.gonder("[1L3A] CRIT\nc", ENV, **kw) and tg.gonder("[1L3A] CRIT\nc", ENV, **kw)


def test_etiketsiz_mesaja_standart_ilk_satir_eklenir():
    assert tg.etiketli("🔴 <b>1L3A CANLI</b>: x") == "[1L3A] 🔴\n🔴 <b>1L3A CANLI</b>: x"
    assert tg.etiketli("düz metin").startswith("[1L3A] ⚠️\n") and tg.etiketli("[1L3A] x") == "[1L3A] x"


def test_ortak_durum_izinleri_dar_ve_root_sahiplik_ust_dizinden(tmp_path, monkeypatch):
    import os
    import stat
    o = tg.OrtakDurum(tmp_path / "ortak")
    o.tekrar_isaretle("k", 1.0)
    assert stat.S_IMODE(os.stat(o.dizin).st_mode) == 0o700
    for ad in ("kilit", "durum.json"):
        assert stat.S_IMODE(os.stat(o.dizin / ad).st_mode) == 0o600
    cagri = []
    monkeypatch.setattr(os, "geteuid", lambda: 0)
    monkeypatch.setattr(os, "chown", lambda y, u, g: cagri.append((str(y), u, g)))
    tg.OrtakDurum(tmp_path / "ortak2").tekrar_isaretle("k", 1.0)
    st = os.stat(tmp_path)
    assert cagri and all(c[1:] == (st.st_uid, st.st_gid) for c in cagri)
    cagri.clear()
    monkeypatch.setattr(os, "geteuid", lambda: 1000)
    tg.OrtakDurum(tmp_path / "ortak3").tekrar_isaretle("k", 1.0)
    assert cagri == []
    monkeypatch.setattr(os, "geteuid", lambda: 0)
    monkeypatch.setattr(os, "chown", lambda *a: (_ for _ in ()).throw(PermissionError()))
    assert tg.OrtakDurum(tmp_path / "ortak4").tekrar_var("k", 10, 2.0) is False       # chown hatası motoru etkilemez


def test_saatlik_not_hic_gitmez(tmp_path):
    s = Sahte()
    s.t = 1_800_000_000.0
    b = tg.Bildirimci(s.gonder, s.saat, ortak=tg.OrtakDurum(tmp_path / "o"))
    b.bilgi("TONUSDT borsada işleme kapandı, listeden çıkarıldı")
    b.kontrol()
    s.t += 5 * 3600
    b.bilgi("XYZUSDT kapandı")
    b.kontrol()
    assert s.giden == []


def test_ust_seviye_emojisi_ve_sessizlik():
    assert tg.ust("INFO") == "[1L3A]" and tg.ust("WARN") == "[1L3A] ⚠️" and tg.ust("CRIT") == "[1L3A] 🔴"


# ---------------------------------------------------------------------------- kullanıcı dostu sadeleştirme (2026-11-19)
def _kod_adi_var(m: str) -> bool:
    return bool(re.search(r"ct_konsensus|aday_paper|\.service|\.py|journalctl|systemctl|[a-z]+__[a-z-]+|\|[A-Z]+USDT\|", m))


def test_ad_okunur_ve_gizli_kimlik_ham_yazilmaz():
    assert tg.ad("ct_konsensus|BTCUSDT|15m") == "CT konsensüs · BTC 15 dk"
    assert tg.ad("x|ETHUSDT|4h") == "X · ETH 4S"


def test_tum_uyari_turleri_en_cok_6_satir_ve_kod_adi_yok():
    for tur in tg.UYARI:
        m = tg.uyari_metni(tur, "ayrıntı\nikinci satır\nüçüncü")
        assert len(m.split("\n")) <= 6 and m.startswith("[1L3A] ") and not _kod_adi_var(m), tur
    m = tg.servis_hatasi_metni("1l3a-paper.service", {"MONITOR_EXIT_CODE": "1"})
    assert "1l3a-paper" not in m and len(m.split("\n")) <= 6


def test_gonder_satir_siniri_6_ozet_12():
    _sifirla()
    o = _Oturum()
    assert tg.gonder("[1L3A] ⚠️ x\n" + "\n".join("s%d" % i for i in range(20)), ENV, o, uyku=lambda s: None, saat=lambda: 1.0)
    assert len(o.giden[-1]["text"].split("\n")) == 6
    assert tg.gonder("[1L3A] 📊 Günlük özet\n" + "\n".join("s%d" % i for i in range(30)), ENV, o, uyku=lambda s: None, saat=lambda: 99.0)
    assert len(o.giden[-1]["text"].split("\n")) == 12


def test_gonder_seviye_parametresi_ve_sessiz_info():
    _sifirla()
    o = _Oturum()
    kw = dict(oturum=o, uyku=lambda s: None)
    assert tg.gonder("[1L3A] 🟢 BTCUSDT long açıldı", ENV, saat=lambda: 1.0, **kw) and o.giden[-1]["disable_notification"] == "true"
    assert tg.gonder("[1L3A] ⚠️ x", ENV, saat=lambda: 2.0, **kw) and o.giden[-1]["disable_notification"] == "false"
    assert tg.gonder("[1L3A] 🔴 y", ENV, saat=lambda: 3.0, **kw) and o.giden[-1]["disable_notification"] == "false"
    assert tg.gonder("[1L3A] z", ENV, saat=lambda: 4.0, seviye="CRIT", **kw) and o.giden[-1]["disable_notification"] == "false"
    assert tg.gonder("[1L3A] ⚠️ w", ENV, saat=lambda: 5.0, seviye="INFO", **kw) and o.giden[-1]["disable_notification"] == "true"


def test_kaldirilan_turler_gonderilmez():
    g = []
    orijinal = tg.gonder
    tg.gonder = lambda metin, *a, **k: g.append(metin) or True
    try:
        tg.baslangic_kaydet(7, 10000, birlestir=False)
        tg.bilgi_ekle("bir bilgi")
        s = Sahte()
        b = tg.Bildirimci(s.gonder, s.saat, ortak=tg.OrtakDurum(None))
        b.bilgi("x")
        b.kontrol()
        assert s.giden == []
    finally:
        tg.gonder = orijinal
    assert g == []



def _risk(deger, limit=0.05):
    return {"ozet": {"risk": {"gunluk_kayip": {"deger": deger, "limit": limit}}}}


def test_limit_yaklasma_metni_ve_esik(tmp_path):
    assert tg.limit_yaklasma_metni(0.04, 0.05) == ("[1L3A] ⚠️ Günlük kayıp limitine yaklaşıldı: %4,0 / %5. Yeni işlemler sürüyor; "
                                                   "limit dolarsa bugün yeni işlem açılmaz. Senden bir şey gerekmiyor.")
    s = Sahte()
    b = tg.Bildirimci(s.gonder, s.saat, ortak=tg.OrtakDurum(tmp_path / "o"))
    assert not tg.limit_yaklasma_kontrol(_risk(0.039), b, "2026-11-19") and not tg.limit_yaklasma_kontrol(_risk(0.05), b, "2026-11-19")
    assert s.giden == []                                                                 # %80 altı ve limit dolu (ayrı uyarı yolu): yok
    assert tg.limit_yaklasma_kontrol(_risk(0.04), b, "2026-11-19") and len(s.giden) == 1
    assert not tg.limit_yaklasma_kontrol(_risk(0.045), b, "2026-11-19") and len(s.giden) == 1     # gün başına bir kez
    s.t += 7 * 3600
    assert not tg.limit_yaklasma_kontrol(_risk(0.045), b, "2026-11-19")                  # aynı gün anahtarı: tekrar yok
    assert tg.limit_yaklasma_kontrol(_risk(0.045), b, "2026-11-20") and len(s.giden) == 2         # ertesi gün yeniden
    assert tg.onem(s.giden[0]) == "WARN" and len(s.giden[0].split("\n")) <= 6



def test_hesap_adlari_modulu_ve_pano_ile_ayni_ad():
    from motor.canli import gunluk_ozet as go
    from motor.canli import hesap_adlari as ha
    assert go.kisa_ad("dis__gauss-stoch-eth") == ha.hesap_adi("dis__gauss-stoch-eth") == "Gauss stoch eth · Gauss kanal kırılımı"     # özet hesap tablosu aynı fonksiyonu kullanır (kısa kod adı yok)
    assert ha.kisa_ad("dis__gauss-stoch-eth") == "gauss"                                                        # yalnız iç kullanım
    assert ha.hesap_adi("dis__gauss-stoch-eth") == "Gauss stoch eth · Gauss kanal kırılımı" and ha.hesap_adi("pf__kesit_ls|kripto|1d") == "Kesit L/S · Kripto"
    assert ha.hesap_adi("swing__yeni-strateji_x|SOLUSDT|4h") == "Yeni strateji x · SOL 4S"
    assert ha.hesap_adi("dis__deneme|BTCUSDT|15m") == "Deneme · BTC 15 dk" and ha.hesap_adi("dis__deneme|ETHUSDT|1h") == "Deneme · ETH 1S"
    assert ha.hesap_adi("dis__gauss-stoch-eth", gorunur=False) == "Diğer hesap"
    assert ha.hesap_adi("ct_konsensus|BTCUSDT|15m") == "CT konsensüs hesabı"
    assert ha.coin_adi("BTCUSDT") == "BTC" and ha.coin_adi("DK_NVDA") == "NVDA" and ha.coin_adi("SOL") == "SOL"


def test_motor_hatasi_ve_durdu_metni():
    h = tg.uyari_metni("motor_hatasi", "ValueError: x @ paper.py:1 (f); art arda 2/5; bellek geri döndü")
    assert h == "[1L3A] 🔴 <b>Bot hata verdi (2/5)</b> · kendini toparlamayı deniyor · Senden: şimdilik bir şey gerekmiyor"
    assert "sunucu" not in h and "paper.py" not in h and tg.onem(h) == "CRIT"
    d = tg.uyari_metni("motor_durdu", "x", "Açık pozisyon: 2 · stoplar: yerinde")
    assert d.split("\n") == ["[1L3A] 🔴 <b>Bot durdu</b> · sistem yeniden başlatmayı deniyor", "Açık pozisyon: 2 · stoplar: yerinde",
                             "Senden: /durum yaz; yanıt gelmezse orkestratöre haber ver"]
    assert "stoplar: bilinmiyor" in tg.uyari_metni("motor_durdu", "x")


def test_motor_durdu_bastirilmaz_duzeldi_tek_sefer(tmp_path):
    s = Sahte()
    ortak = tg.OrtakDurum(tmp_path / "o")
    b = tg.Bildirimci(s.gonder, s.saat, ortak=ortak)
    b.durdu_bilgi = lambda: "Açık pozisyon: 1 · stoplar: yerinde"
    for _ in range(3):                                                                   # hatadan durmaya geçiş: 6 saat kuralı yok
        b.olay("motor_hatasi", "x; art arda 1/5; y")
        b.olay("motor_durdu", "x")
    assert len(s.giden) == 6 and all(m.startswith("[1L3A] 🔴") for m in s.giden) and "yerinde" in s.giden[1]
    s.giden.clear()
    b2 = tg.Bildirimci(s.gonder, s.saat, ortak=tg.OrtakDurum(tmp_path / "o"))            # yeniden başlatma: ilk başarılı turda tek Düzeldi
    b2.kontrol()
    b2.kontrol()
    assert s.giden == ["[1L3A] ✅ Düzeldi: bot tekrar çalışıyor"] and tg.onem(s.giden[0]) == "INFO"
    b3 = tg.Bildirimci(s.gonder, s.saat, ortak=tg.OrtakDurum(tmp_path / "o"))            # normal açılış: "başladı"/Düzeldi yok
    b3.kontrol()
    assert len(s.giden) == 1
    b3.olay("motor_hatasi", "x; art arda 1/5; y")                                         # aynı süreçte toparlanma da bildirilir
    b3.kontrol()
    assert s.giden[-1].startswith("[1L3A] ✅ Düzeldi")


def test_limit_doldu_ve_kill_acik_pozisyonlari_soyler():
    assert "Açık pozisyonlar kapatıldı" in tg.uyari_metni("gunluk_limit") and "Açık pozisyonlar kapatıldı" in tg.uyari_metni("kill_switch")


def test_durum_komutu_var():
    from motor.canli import telegram_komut as tk
    assert "/durum" in tk.YARDIM and hasattr(tk.KomutServisi if hasattr(tk, "KomutServisi") else tk, "durum_metni") or "durum_metni" in open(tk.__file__, encoding="utf-8").read()



def test_hesap_adi_hicbir_zaman_alt_cizgi_icermez():
    from motor.canli import hesap_adlari as ha
    for k in tg.AD:
        assert "_" not in ha.hesap_adi(k) and "_" not in tg.ad(k) and ha.hesap_adi(k) == tg.AD[k], k
    for k in ("dis__yeni_strateji-x|DK_NVDA|1h", "pf__kesit_ls_v2|kripto|1d", "HAM:X005:664#v1", "swing__a_b|BTCUSDT|15m", "ct_konsensus|BTCUSDT|15m"):
        assert "_" not in ha.hesap_adi(k) and ha.hesap_adi(k)[:1].isupper() or ha.hesap_adi(k)[:1].isdigit(), k
    assert tg.AD is ha.AD


def test_kapandi_mesajinda_hesap_adi_dolu_ya_da_bilinmiyor():
    from motor.canli import hesap_adlari as hg
    assert tg.islem_kapandi_metni({**KAPANAN, "kimlik": "pf__kesit_ls|kripto|1d"}).split("\n")[0].endswith("· Kesit L/S · Kripto")
    for bos in ("", None, "   "):
        assert hg.hesap_adi(bos) == "Hesap bilinmiyor"
        assert tg.islem_kapandi_metni({**KAPANAN, "kimlik": bos}).split("\n")[0].endswith("· Hesap bilinmiyor")
