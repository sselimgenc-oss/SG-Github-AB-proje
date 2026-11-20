"""Ortak günlük özet (ortak.gunluk_ozet.v1) + haftalık Telegram özeti: şema, ct hariç kasa, gizli hesaplar, kancalar."""
import json
from pathlib import Path

import pandas as pd
import pytest

from motor.canli import gunluk_ozet as go
from motor.canli import paper_v2 as v2

KOK = Path(__file__).resolve().parent.parent
SET = json.loads(v2.SET_YOLU.read_text(encoding="utf-8"))
KAYITLAR = [(v2.hesap_adi(k), v2.hesap_dizin_adi(v2.hesap_adi(k)), v2.gorunur_mu(k)) for k in SET["stratejiler"]]
GIZLI_KIMLIK = [k for k, _, g in KAYITLAR if not g]
GORUNUR_KISA = {"Gauss stoch eth · Gauss kanal kırılımı", "Hma atr rider", "Ham 664 v1", "Ewo ema ofset", "E0v1en", "Ham 705"}
SIMDI = pd.Timestamp("2026-11-19 12:00", tz="UTC")           # TSİ 15:00, Perşembe
GUN = "2026-11-19"


def _yaz(yol: Path, veri):
    yol.parent.mkdir(parents=True, exist_ok=True)
    yol.write_text(json.dumps(veri) if not isinstance(veri, str) else veri, encoding="utf-8")


def _hesap(dizin: Path, ozsermaye, gun_pnl, toplam, kapanan=3, acik=1, islemler=(), zirve=None):
    _yaz(dizin / "ozet.json", {"ozsermaye": f"{ozsermaye:.2f}", "baslangic_ozsermaye": "10000.00", "gun_pnl": f"{gun_pnl:.2f}", "toplam_pnl": f"{toplam:.2f}",
                               "zirve_ozsermaye": f"{(zirve or max(ozsermaye, 10000)):.2f}", "sayaclar": {"acik_pozisyon": acik, "kapanan_islem": kapanan}})
    _yaz(dizin / "islemler.jsonl", "".join(json.dumps(x) + "\n" for x in islemler))
    _yaz(dizin / "stratejiler.json", {"stratejiler": []})


def _islem(giris, cikis, pnl):
    return {"zaman": cikis, "giris_zamani": giris, "cikis_zamani": cikis, "net_pnl_yerel": pnl}


@pytest.fixture
def durum(tmp_path):
    d = tmp_path / "durum"
    for i, (kimlik, klasor, _) in enumerate(KAYITLAR):
        _hesap(d / "hesaplar" / klasor, 10100 + i * 10, 5 + i, 100 + i * 10, kapanan=10 + i,
               islemler=[_islem("2026-11-19T05:00:00Z", "2026-11-19T08:00:00Z", "12.5"), _islem("2026-11-17T05:00:00Z", "2026-11-17T08:00:00Z", "-3")])
    ct = tmp_path / "ct"
    _hesap(ct, 9000, -50, -1000, kapanan=7)
    _yaz(d / "alinmayan_sinyaller.jsonl", "".join(json.dumps({"zaman": z}) + "\n" for z in
                                                  ["2026-11-19T01:00:00Z", "2026-11-19T10:00:00Z", "2026-11-18T10:00:00Z", "2026-11-18T22:30:00Z"]))
    return d, ct


def _topla(d, ct, **kw):
    return go.topla(d, SIMDI, ct_dizin=ct, env={"L3A_REJIM_KAPALI": "1", "L3A_DURDUR_DOSYA": str(d / "DURDUR"), **kw})


def test_sema_alanlari_hepsi_var_bos_durumda_bile(tmp_path):
    o = go.topla(tmp_path / "yok", SIMDI, ct_dizin=tmp_path / "ct_yok", env={"L3A_REJIM_KAPALI": "1", "L3A_DURDUR_DOSYA": str(tmp_path / "D")})
    assert set(go.SEMA_ALANLARI) <= set(o) and o["sema"] == "ortak.gunluk_ozet.v1" and o["proje"] == "1L3A" and o["mod"] == "kagit" and o["gun"] == GUN
    assert set(o["kasa"]) == {"baslangic", "simdi", "gun_pnl", "toplam_pnl", "zirveden_dusus_yuzde"} and all(v is None for v in o["kasa"].values())
    assert set(o["islem"]) == {"gun_acilan", "gun_kapanan", "kazanan", "kaybeden", "acik_pozisyon", "alinmayan_sinyal"}
    assert set(o["ogrenme"]) == {"aktif_ders", "yeni_ders", "emekli_ders", "filtre_aktif"} and all(v is None for v in o["ogrenme"].values())
    assert o["rejim"] is None and o["drift_uyari"] is False
    assert set(o["limitler"]) == {"gunluk_kayip_yuzde", "kaldirac_tavan", "durdu_mu"} and set(o["saglik"]) == {"son_nabiz", "hata_sayisi_gun"}
    assert o["saglik"]["son_nabiz"] is None and o["saglik"]["hata_sayisi_gun"] is None and len(o["notlar"]) <= 5
    json.dumps(o, allow_nan=False)


def test_kasa_on_hesap_toplami_ct_haric(durum):
    d, ct = durum
    o = _topla(d, ct)
    assert o["kasa"]["baslangic"] == 100000.0
    assert o["kasa"]["simdi"] == sum(10100 + i * 10 for i in range(10))            # ct (9000) dahil değil
    assert o["kasa"]["gun_pnl"] == sum(5 + i for i in range(10)) and o["kasa"]["toplam_pnl"] == sum(100 + i * 10 for i in range(10))
    assert o["kasa"]["zirveden_dusus_yuzde"] == 0.0


def test_hesaplar_gorunur_adlariyla_gizliler_tek_satir_ct_ayri(durum):
    d, ct = durum
    o = _topla(d, ct)
    adlar = [h["ad"] for h in o["hesaplar"]]
    assert set(adlar[:6]) == GORUNUR_KISA and adlar[6] == "Diğer hesaplar (4)" and adlar[7] == "CT konsensüs hesabı" and len(adlar) == 8
    gizli = o["hesaplar"][6]
    assert gizli["islem"] == sum(10 + i for i, (_, _, g) in enumerate(KAYITLAR) if not g)
    ham = json.dumps(o)
    for k in GIZLI_KIMLIK:
        assert k not in ham and v2.hesap_dizin_adi(k) not in ham
    for parca in ("lube", "670", "574", "730"):
        assert parca not in ham
    assert o["hesaplar"][7]["toplam_pnl"] == -1000.0


def test_islem_sayilari_ve_alinmayan(durum):
    d, ct = durum
    o = _topla(d, ct)
    assert o["islem"]["gun_kapanan"] == 10 and o["islem"]["gun_acilan"] == 10 and o["islem"]["kazanan"] == 10 and o["islem"]["kaybeden"] == 0
    assert o["islem"]["acik_pozisyon"] == 10
    assert o["islem"]["alinmayan_sinyal"] == 3        # 19 Kasım TSİ günü: 01:00Z, 10:00Z ve 18 Kasım 22:30Z (= 01:30 TSİ)


def test_durdu_mu_bayraga_gore(durum):
    d, ct = durum
    assert _topla(d, ct)["limitler"]["durdu_mu"] is False
    (d / "DURDUR").write_text("")
    o = _topla(d, ct)
    assert o["limitler"]["durdu_mu"] is True and o["limitler"]["gunluk_kayip_yuzde"] == 5.0 and o["limitler"]["kaldirac_tavan"] == 5


def test_ogrenme_rejim_nabiz_hata(durum, tmp_path):
    d, ct = durum
    _yaz(d / "ogrenme_ders.json", {"a": {"status": "alive", "born": "2026-11-10"}, "b": {"status": "candidate", "born": GUN},
                                   "c": {"status": "retired", "born": "2026-11-01", "retired_day": GUN}})
    _yaz(d / "ogrenme_durum.json", {"drift_uyari": ["kurulum_x"]})
    (d / "ogrenme_modeller").mkdir()
    _yaz(d / "ogrenme_modeller" / "m.json", {"x": 1})
    rejim = tmp_path / "rejim.json"
    _yaz(rejim, {"uretim_ts": "2026-11-19T11:00:00Z", "gecerlilik_dk": 180, "rejimler": ["trend", "yatay"], "varliklar": {"BTCUSDT": {"1d": {"rejim": "trend", "bar_ts": "2026-11-19T00:00:00Z"}}}})
    _yaz(d / "kalp_atisi.json", {"zaman": "2026-11-19T11:59:30Z"})
    _yaz(d / "olaylar.jsonl", "".join(json.dumps(e) + "\n" for e in [{"zaman": "2026-11-19T09:00:00Z", "tur": "binance_hata", "mesaj": "x"},
                                                                       {"zaman": "2026-11-19T09:00:00Z", "tur": "ws_koptu", "mesaj": "x"},
                                                                       {"zaman": "2026-11-18T09:00:00Z", "tur": "kill_switch", "mesaj": "x"}]))
    o = _topla(d, ct, L3A_REJIM_DOSYA=str(rejim))
    assert o["ogrenme"] == {"aktif_ders": 2, "yeni_ders": 1, "emekli_ders": 1, "filtre_aktif": True}
    assert o["drift_uyari"] is True and o["rejim"] == "trend"
    assert o["saglik"]["son_nabiz"] == "2026-11-19T11:59:30Z" and o["saglik"]["hata_sayisi_gun"] == 1


def test_gizli_bilgi_yok(durum, monkeypatch):
    d, ct = durum
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "123456789:ABCdefGhIJKlmnOPQrstUVwxyz0123456789")
    monkeypatch.setenv("TELEGRAM_CHAT_ID", "987654321")
    monkeypatch.setenv("CLOUDFLARE_API_TOKEN", "cf-gizli-anahtar")
    o = go.yaz(d, SIMDI, ct_dizin=ct, env={"L3A_REJIM_KAPALI": "1", "L3A_DURDUR_DOSYA": str(d / "DURDUR")})
    metin = (d / go.DOSYA).read_text(encoding="utf-8") + go.haftalik_metin(go.haftalik_ozet([o], GUN))
    import re
    assert not re.search(r"\d{5,}:[A-Za-z0-9_-]{20,}|987654321|cf-gizli|@[\w-]+\.\w+|api[_-]?key|secret|token", metin, re.I)


class _P:
    son_haftalik = None


def _kanca(p, d, ct, simdi, ozet_an=False, gidenler=None):
    g = [] if gidenler is None else gidenler
    return go.paper_kancasi(p, d, simdi, ozet_an, lambda m: g.append(m) or True, ct_dizin=ct, env={"L3A_REJIM_KAPALI": "1", "L3A_DURDUR_DOSYA": str(d / "DURDUR")}), g


def test_21de_bir_kez_yazilir_ve_saatlik_guncelleme(durum):
    d, ct = durum
    p = _P()
    t0 = pd.Timestamp("2026-11-19 17:59", tz="UTC")                # 20:59 TSİ
    _kanca(p, d, ct, t0)
    ilk = json.loads((d / go.DOSYA).read_text())["uretim"]
    assert ilk == "2026-11-19T17:59:00Z"
    _kanca(p, d, ct, t0 + pd.Timedelta(minutes=30))                # saat dolmadı, 21:00 değil: yazılmaz
    assert json.loads((d / go.DOSYA).read_text())["uretim"] == ilk
    _kanca(p, d, ct, t0 + pd.Timedelta(minutes=1), ozet_an=True)   # 21:00 TSİ günlük özet anı: yazılır
    assert json.loads((d / go.DOSYA).read_text())["uretim"] == "2026-11-19T18:00:00Z"
    _kanca(p, d, ct, t0 + pd.Timedelta(minutes=2), ozet_an=False)  # özet işaretlendi (ozet_an artık False): tekrar yazılmaz
    assert json.loads((d / go.DOSYA).read_text())["uretim"] == "2026-11-19T18:00:00Z"
    _kanca(p, d, ct, t0 + pd.Timedelta(minutes=62))                # saatlik güncelleme
    assert json.loads((d / go.DOSYA).read_text())["uretim"] == "2026-11-19T19:01:00Z"


def test_paper_21_00_ozet_zamaniyla_ayni_anda(durum):
    """paper.ozet_zamani doğru olduğu turda kanca yazar; kancayı tetikleyen koşul gün başına bir kez doğrudur (p.son_ozet)."""
    from motor.canli import paper as pp
    d, ct = durum

    class Q:
        son_ozet = None
    q, yaz_sayisi = Q(), 0
    for dk in (0, 5, 10):
        simdi = pd.Timestamp("2026-11-19 18:00", tz="UTC") + pd.Timedelta(minutes=dk)
        an = pp.ozet_zamani(q, simdi)
        if an:
            yaz_sayisi += 1
            q.son_ozet = pp.bugun_tsi(simdi)
        _kanca(_P(), d, ct, simdi, ozet_an=an)
    assert yaz_sayisi == 1


def test_pazar_2110_haftalik_bir_kez(durum):
    d, ct = durum
    p, g = _P(), []
    # Cumartesi 21:30 TSİ: haftalık yok
    assert _kanca(p, d, ct, pd.Timestamp("2026-11-21 18:30", tz="UTC"), gidenler=g)[0] is False
    # Pazar 21:05 TSİ: henüz yok; 21:10: gider; sonrasında tekrar gitmez
    assert _kanca(p, d, ct, pd.Timestamp("2026-11-22 18:05", tz="UTC"), gidenler=g)[0] is False
    assert _kanca(p, d, ct, pd.Timestamp("2026-11-22 18:10", tz="UTC"), gidenler=g)[0] is True
    assert p.son_haftalik == "2026-11-22" and len(g) == 1
    assert _kanca(p, d, ct, pd.Timestamp("2026-11-22 19:30", tz="UTC"), gidenler=g)[0] is False and len(g) == 1
    m = g[0]
    assert m.startswith("[1L3A] 📆") and len(m) <= 3500 and len(m.split("\n")) <= 12
    assert "Haftalık K/Z" in m and "Alınmayan sinyal" in m and "drift" in m
    assert "gizli" not in m.lower() and "lube" not in m and "ct_konsensus" not in m
    assert "En iyi hesap" in m and "En kötü hesap" in m


def test_gecmis_gunde_bir_satir_ve_haftalik_toplam(durum):
    d, ct = durum
    env = {"L3A_REJIM_KAPALI": "1", "L3A_DURDUR_DOSYA": str(d / "DURDUR")}
    go.yaz(d, pd.Timestamp("2026-11-19 10:00", tz="UTC"), ct_dizin=ct, env=env)
    go.yaz(d, pd.Timestamp("2026-11-19 11:00", tz="UTC"), ct_dizin=ct, env=env)          # aynı gün: satır güncellenir
    assert [x["gun"] for x in go.gecmis_oku(d)] == [GUN]
    for gun in ("2026-11-20", "2026-11-21", "2026-11-22"):
        go.yaz(d, pd.Timestamp(gun + " 10:00", tz="UTC"), ct_dizin=ct, env=env)
    satirlar = go.gecmis_oku(d)
    assert [x["gun"] for x in satirlar] == [GUN, "2026-11-20", "2026-11-21", "2026-11-22"]
    h = go.haftalik_ozet(satirlar, "2026-11-22")
    assert h["gun_sayisi"] == 4 and h["kz"] == 4 * 95.0 and h["en_iyi"][0] in GORUNUR_KISA and h["en_kotu"][0] in GORUNUR_KISA
    assert h["en_iyi"][1] >= h["en_kotu"][1]
