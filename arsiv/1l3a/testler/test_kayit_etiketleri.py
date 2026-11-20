"""Yalnız kayıt: alınmayan sinyaller + etiketler (fonlama, korku/açgözlülük, takvim, rejim). Kayıt açık/kapalı sonuç AYNI olmalı."""
import importlib.util
import json
from pathlib import Path

import pandas as pd
import pytest

from motor.backtest.motor import SembolKurallari
from motor.canli import kayit_etiketleri as ke
from motor.canli import paper as pp
from testler.test_paper_motor import TAN, duz, kural, sentetik, tanim

_sp = importlib.util.spec_from_file_location("alinmayan_sonuc", Path(__file__).resolve().parents[1] / "araclar" / "alinmayan_sonuc.py")
sonuc = importlib.util.module_from_spec(_sp)
_sp.loader.exec_module(sonuc)

T = pd.Timestamp("2025-03-10 12:00", tz="UTC")


def satirlar(dizin):
    yol = Path(dizin) / ke.DOSYA_ADI
    return [json.loads(x) for x in yol.read_text(encoding="utf-8").splitlines()] if yol.exists() else []


def kayit(tmp_path, **kw):
    kw.setdefault("fng_fn", lambda: [(z, 40) for z in pd.date_range("2024-01-01", "2025-12-31", freq="D", tz="UTC")])
    kw.setdefault("takvim_yolu", tmp_path / "yok.json")
    kw.setdefault("rejim_dosya", None)
    kw.setdefault("rejim_url", None)
    kw.setdefault("rejim_kapali", kw["rejim_url"] is None)        # URL verilmediyse kapalı: varsayılan YENI_REJIM_URL ağa çıkmasın
    return ke.Kayit(tmp_path, saat=lambda: T.timestamp(), **kw)


def _hazir(t, sembol="XUSDT", n=12, min_notional=5.0):
    mum = {(sembol, "1d"): duz(n, 100.0)}
    kur = {sembol: SembolKurallari(0.01, 0.001, 0.001, min_notional)}
    return mum, kur


def _paper(tmp_path, kay=True, min_notional=5.0):
    t = tanim("a|XUSDT|1d", "XUSDT", stop_yuzde=3.0)
    mum, kur = _hazir(t, min_notional=min_notional)
    from motor.canli.paper_kaynak import TekrarKaynagi
    p = pp.Paper([t], TekrarKaynagi(mum, {}), kur)
    if kay:
        p.kayit_ac(kayit(tmp_path))
    bas = mum[("XUSDT", "1d")].index[3]
    p.baslat(bas)
    return p, mum, bas


# ---------------------------------------------------------------------------- her atlama nedeni satır yazar
def test_min_notional_satiri(tmp_path):
    t = tanim("a|XUSDT|1d", "XUSDT", stop_yuzde=3.0)
    mum, kur = _hazir(t, min_notional=1e9)
    pp.tekrar_calistir([t], mum, {}, kur, mum[("XUSDT", "1d")].index[2], kapat=False, kayit=kayit(tmp_path))
    s = satirlar(tmp_path)
    assert s and s[0]["neden"] == "min_notional"
    for alan in ("zaman", "hesap", "strateji", "sembol", "yon", "fiyat", "stop", "neden", "fonlama_orani", "korku_acgozluluk", "takvim_bayragi"):
        assert alan in s[0]
    assert s[0]["sembol"] == "XUSDT" and s[0]["yon"] == "long" and float(s[0]["stop"]) < float(s[0]["fiyat"])
    assert s[0]["korku_acgozluluk"] == 40 and "rejim_ml_4h" not in s[0]


@pytest.mark.parametrize("ayar,neden", [("kill", "kill_switch"), ("gunluk", "gunluk_kayip_limiti"), ("isinma", "isinma")])
def test_limit_ve_isinma_satiri(tmp_path, ayar, neden):
    p, mum, bas = _paper(tmp_path)
    m = p.motor
    ilk = mum[("XUSDT", "1d")].index[3]
    if ayar == "kill":
        m.kill = True
    elif ayar == "gunluk":
        m.gun, m.gunluk_blok = ilk.date(), True
    else:
        m.islem_baslangic = ilk + pd.Timedelta(days=30)
    p.adim(ilk + pd.Timedelta(days=1))
    assert neden in [x["neden"] for x in satirlar(tmp_path)]
    assert not m.acik


def test_acik_pozisyon_ve_toplam_risk_satiri(tmp_path):
    p, mum, bas = _paper(tmp_path)
    p.adim(mum[("XUSDT", "1d")].index[8] + pd.Timedelta(days=1))
    assert len(p.motor.acik) == 1
    ap = [x for x in satirlar(tmp_path) if x["neden"] == "acik_pozisyon"]
    assert len(ap) == 1                                      # ardışık tekrarlar tek satır


def test_toplam_risk_tavani_satiri(tmp_path):
    tans = [tanim(f"k{i}|S{i}USDT|1d", f"S{i}USDT", grup="tek", pay="0.5", stop_yuzde=0.05) for i in range(4)]
    mum = {(t.sembol, "1d"): duz(10, 100.0, dalga=0.0) for t in tans}
    kur = {t.sembol: SembolKurallari(0.01, 0.001, 0.001, 5.0) for t in tans}
    k = kayit(tmp_path)
    pp.tekrar_calistir(tans, mum, {}, kur, mum[("S0USDT", "1d")].index[3], kapat=False, kayit=k)
    nedenler = {x["neden"] for x in satirlar(tmp_path)}
    assert nedenler <= {"toplam_risk_tavani", "kaldirac_tavani", "min_qty", "min_notional", "acik_pozisyon"} and nedenler


# ---------------------------------------------------------------------------- sonuçlar kayıt açık/kapalı BİREBİR aynı
def _kos(tmp_path, kay, fng_fn=None):
    tid = "swing__cci-esik|SOLUSDT|1d"
    t = TAN[tid]
    m = sentetik(700, "1d", 1, vol=0.03)
    f = pd.DataFrame({"oran": 0.0001}, index=pd.date_range(m.index[0], periods=2100, freq="8h", tz="UTC"))
    k = kayit(tmp_path, **({"fng_fn": fng_fn} if fng_fn else {})) if kay else None
    p = pp.tekrar_calistir([t], {(t.sembol, "1d"): m}, {t.sembol: f}, {t.sembol: kural(t.sembol)}, m.index[500], kapat=True, kayit=k)
    return p


def _norm(p):
    m = p.motor
    isl = [{k: v for k, v in x.items() if k != "etiketler"} for x in m.islemler]
    return isl, m.reddedilenler, m.kirpmalar, m.nakit, m.ozsermaye()


def test_sonuclar_kayit_acik_kapali_ayni(tmp_path):
    kapali = _kos(tmp_path / "a", False)
    acik = _kos(tmp_path / "b", True)
    assert len(kapali.motor.islemler) >= 1
    assert _norm(kapali) == _norm(acik)
    assert all("etiketler" not in x for x in kapali.motor.islemler)
    e = acik.motor.islemler[0]["etiketler"]
    assert e["fonlama_orani"] == pytest.approx(0.0001) and e["korku_acgozluluk"] == 40 and e["takvim_bayragi"] is None


def test_ag_hatasinda_null_ve_motor_devam(tmp_path):
    def bozuk():
        raise ConnectionError("ag yok")
    kapali = _kos(tmp_path / "a", False)
    acik = _kos(tmp_path / "b", True, fng_fn=bozuk)
    assert _norm(kapali) == _norm(acik)
    assert acik.motor.islemler[0]["etiketler"]["korku_acgozluluk"] is None


def test_kanca_hatasi_motoru_dusurmez(tmp_path):
    k = kayit(tmp_path)
    k.etiketler = lambda *a, **b: (_ for _ in ()).throw(RuntimeError("kanca"))
    k.alinmadi = lambda *a, **b: (_ for _ in ()).throw(RuntimeError("kanca"))
    t = tanim("a|XUSDT|1d", "XUSDT", stop_yuzde=3.0)
    mum, kur = _hazir(t, min_notional=1e9)
    p = pp.tekrar_calistir([t], mum, {}, kur, mum[("XUSDT", "1d")].index[2], kapat=False, kayit=k)
    assert any(r["neden"] == "min_notional" for r in p.motor.reddedilenler)


# ---------------------------------------------------------------------------- etiketler
def test_fear_greed_gelecek_deger_kullanilmaz(tmp_path):
    z = pd.Timestamp
    liste = [(z("2025-03-09", tz="UTC"), 30), (z("2025-03-11", tz="UTC"), 90)]
    k = kayit(tmp_path, fng_fn=lambda: liste)
    assert k.korku(z("2025-03-10 12:00", tz="UTC")) == 30          # 03-11 değeri karar anında henüz yayımlanmamış
    assert k.korku(z("2025-03-08 12:00", tz="UTC")) is None        # yalnız gelecek/olmayan -> null
    assert k.korku(z("2025-03-14 12:00", tz="UTC")) is None        # 48 saatten eski -> null


def test_fear_greed_gunde_bir_cekilir_ve_hata_beklemesi(tmp_path):
    sayac = []
    k = kayit(tmp_path, fng_fn=lambda: sayac.append(1) or [(pd.Timestamp("2025-03-10", tz="UTC"), 40)])
    for _ in range(5):
        k.korku(T)
    assert len(sayac) == 1
    hata = []
    k2 = kayit(tmp_path, fng_fn=lambda: hata.append(1) or (_ for _ in ()).throw(OSError("x")))
    for _ in range(5):
        assert k2.korku(T) is None
    assert len(hata) == 1                                            # hata sonrası bekleme: her kararda yeniden denenmez


def test_takvim_bayragi(tmp_path):
    yol = tmp_path / "takvim.json"
    yol.write_text(json.dumps({"olaylar": [{"ad": "FOMC", "zaman": "2025-03-10T13:30:00Z"}]}), encoding="utf-8")
    k = kayit(tmp_path, takvim_yolu=yol)
    assert k.takvim(T) == "FOMC"
    assert k.takvim(T - pd.Timedelta(hours=1)) is None
    assert kayit(tmp_path, takvim_yolu=tmp_path / "yok.json").takvim(T) is None
    gercek = json.loads((Path(__file__).resolve().parents[1] / "stratejiler" / "ekonomik_takvim.json").read_text(encoding="utf-8"))
    assert gercek["olaylar"] == []                                    # tarih uydurulmadı


def _yayin(**kw):
    d = {"surum": 1, "kaynak": "ml", "uretim_ts": "2025-03-10T11:00:00Z", "gecerlilik_dk": 90,
         "rejimler": ["trend_up", "trend_down", "range", "volatile", "unclear"],
         "varliklar": {"BTCUSDT": {"baz": "BTC", "varlik_sinifi": "kripto", "4h": {"rejim": "trend_up", "bar_ts": "2025-03-10T08:00:00Z"},
                                   "1d": {"rejim": "range", "bar_ts": "2025-03-10T00:00:00Z"}}}}
    d.update(kw)
    return d


def _rj(tmp_path, ham, sembol="BTCUSDT"):
    f = tmp_path / "rejim.json"
    f.write_text(ham if isinstance(ham, str) else json.dumps(ham), encoding="utf-8")
    return kayit(tmp_path, rejim_dosya=str(f)).etiketler(sembol, T)


def test_rejim_yuvasi(tmp_path):
    e = _rj(tmp_path, _yayin())
    assert (e["rejim_ml_4h"], e["rejim_ml_1d"]) == ("trend_up", "range")
    assert "rejim_ml_4h" not in kayit(tmp_path).etiketler("BTCUSDT", T)      # tanımlı değil: alan yok
    nul = {"rejim_ml_4h": None, "rejim_ml_1d": None}
    assert {k: _rj(tmp_path, _yayin(uretim_ts="2025-03-10T09:00:00Z"))[k] for k in nul} == nul     # 180 dk > 90: bayat yayın
    assert {k: _rj(tmp_path, _yayin(uretim_ts="2025-03-10T12:30:00Z"))[k] for k in nul} == nul     # karardan sonra üretilmiş
    assert {k: _rj(tmp_path, _yayin(), sembol="DK_NVDA")[k] for k in nul} == nul                   # eşleşmeyen sembol
    assert {k: _rj(tmp_path, "bozuk")[k] for k in nul} == nul
    g = _yayin()
    g["varliklar"]["BTCUSDT"]["4h"]["bar_ts"] = "2025-03-10T16:00:00Z"                              # gelecekteki bar
    e = _rj(tmp_path, g)
    assert e["rejim_ml_4h"] is None and e["rejim_ml_1d"] == "range"


def test_rejim_url_onbellek_ve_hata(tmp_path):
    n = []
    k = kayit(tmp_path, rejim_url="http://x", rejim_http=lambda u: n.append(1) or (_ for _ in ()).throw(OSError()))
    assert k.etiketler("BTCUSDT", T)["rejim_ml_4h"] is None and k.etiketler("BTCUSDT", T)["rejim_ml_4h"] is None and len(n) == 1
    m = []
    k = kayit(tmp_path, rejim_url="http://x", rejim_http=lambda u: m.append(1) or _yayin())
    assert k.rejim("BTCUSDT", T)["rejim_ml_1d"] == "range" and k.rejim("BTCUSDT", T)["rejim_ml_1d"] == "range" and len(m) == 1


def test_fonlama_yalniz_kripto_ve_gecmis(tmp_path):
    f = pd.DataFrame({"oran": [0.1, 0.2]}, index=pd.DatetimeIndex(["2025-03-10 08:00", "2025-03-10 16:00"], tz="UTC"))
    k = kayit(tmp_path)
    assert k.fonlama("BTCUSDT", T, f) == 0.1                          # 16:00 değeri karar anından sonra
    assert k.fonlama("DK_NVDA", T, f) is None and k.fonlama("BTCUSDT", T, None) is None


def test_dosya_donmesi(tmp_path, monkeypatch):
    monkeypatch.setattr(ke, "MAX_BAYT", 200)
    k = kayit(tmp_path)
    for i in range(10):
        k.alinmadi({"i": i, "dolgu": "x" * 50})
    assert (tmp_path / (ke.DOSYA_ADI + ".1")).exists() and (tmp_path / ke.DOSYA_ADI).exists()


# ---------------------------------------------------------------------------- alinmayan_sonuc: lookahead yok
def _mum(satirlar_):
    idx = pd.DatetimeIndex([x[0] for x in satirlar_], tz="UTC")
    return pd.DataFrame([x[1:] for x in satirlar_], index=idx, columns=["acilis", "yuksek", "dusuk", "kapanis"])


S = {"zaman": "2025-03-10T00:00:00Z", "yon": "long", "fiyat": "100", "stop": "95", "hedef": "110", "zaman_cikisi_mum": None, "neden": "x"}


def test_sonuc_lookahead_yok():
    m = _mum([("2025-03-09", 100, 130, 50, 100),               # karardan ÖNCE: stop ve hedefi de vurur, yok sayılmalı
              ("2025-03-10", 100, 104, 99, 102),
              ("2025-03-11", 102, 112, 101, 111)])
    r = sonuc.simule(S, m)
    assert r["sonuc"] == "hedef" and r["r"] == pytest.approx(2.0) and r["cikis_zamani"].startswith("2025-03-11")
    sadece_once = m.iloc[:1]
    assert sonuc.simule(S, sadece_once)["sonuc"] == "acik"       # sonrası yoksa çözülmez (öncesi kullanılmaz)


def test_sonuc_stop_zaman_ve_ozet():
    m = _mum([("2025-03-10", 100, 101, 94, 96), ("2025-03-11", 96, 99, 95, 98)])
    assert sonuc.simule(S, m) == {"sonuc": "stop", "r": -1.0, "cikis_fiyati": 95.0, "cikis_zamani": str(m.index[0])}
    z = dict(S, zaman_cikisi_mum=2, hedef=None)
    m2 = _mum([("2025-03-10", 100, 101, 99, 100), ("2025-03-11", 100, 102, 99, 101), ("2025-03-12", 103, 104, 102, 103)])
    r = sonuc.simule(z, m2)
    assert r["sonuc"] == "zaman" and r["cikis_fiyati"] == 103.0
    ozet = sonuc.ozet([(S, sonuc.simule(S, m)), (z, r)])
    assert ozet[0]["sinyal"] == 2 and ozet[0]["cozulen"] == 2
    assert "toplam_R" in sonuc.tablo(ozet)


def test_sonuc_dosyadan_calistir(tmp_path):
    (tmp_path / ke.DOSYA_ADI).write_text(json.dumps(dict(S, sembol="XUSDT", tf="1d")) + "\n", encoding="utf-8")
    m = _mum([("2025-03-10", 100, 104, 99, 102), ("2025-03-11", 102, 112, 101, 111)])
    out = sonuc.calistir(tmp_path, lambda s, tf: m)
    assert out[0][1]["sonuc"] == "hedef"


def test_rejim_url_eski_yeni_esleme_ve_bayrak(tmp_path, monkeypatch):
    for d in ("L3A_REJIM_URL", "L3A_REJIM_KAPALI", "L3A_REJIM_DOSYA"):
        monkeypatch.delenv(d, raising=False)
    mk = lambda **kw: ke.Kayit(tmp_path, takvim_yolu=tmp_path / "yok.json", **kw)
    monkeypatch.setenv("L3A_REJIM_URL", ke.ESKI_REJIM_URL)
    assert mk().rejim_url == ke.YENI_REJIM_URL                      # eski -> yeni
    monkeypatch.delenv("L3A_REJIM_URL")
    assert mk().rejim_url == ke.YENI_REJIM_URL                      # tanımsız -> yeni
    monkeypatch.setenv("L3A_REJIM_URL", "http://baska/rejim.json")
    assert mk().rejim_url == "http://baska/rejim.json"              # başka adres aynen
    monkeypatch.setenv("L3A_REJIM_KAPALI", "1")
    k = mk()
    assert k.rejim_url is None and k.rejim("BTCUSDT", T) is ke._YOK  # kapalı
    assert ke.rejim_url_coz(ke.ESKI_REJIM_URL, True) is None
