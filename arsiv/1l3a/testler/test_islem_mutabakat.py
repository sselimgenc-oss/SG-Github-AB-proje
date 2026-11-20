"""İşlem mutabakatı (araclar/islem_mutabakat.py): fixture (paper + ct), yön bozma, gizli hesap, worker ve yayın bağlantısı."""
import json
from pathlib import Path

import pytest

from araclar import islem_mutabakat as im
from motor.canli import pano
from motor.canli import telegram as tg

KOK = Path(__file__).resolve().parent.parent
GIZLI = "dis__gizli-strateji"
GAUSS = "dis__gauss-stoch-eth"
CT = "ct_konsensus|BTCUSDT|15m"


def _t(dk):
    return f"2026-11-18T{dk // 60:02d}:{dk % 60:02d}:00Z"


def _isl(kimlik, sembol, yon, g, c, gf, cf, miktar, net, t0, t1):
    return {"zaman": _t(t1), "kimlik": kimlik, "sembol": sembol, "yon": yon, "giris_zamani": _t(t0), "giris_fiyati": str(gf), "cikis_zamani": _t(t1),
            "cikis_fiyati": str(cf), "miktar": str(miktar), "r": 1.0, "net_pnl_yerel": net, "set_katki_usd": net, "cikis_nedeni": "stop"}


def _poz(kimlik, sembol, yon, gf, mark, miktar, kz, t0):
    nom = f"{float(mark) * float(miktar):.2f}"
    return {"kimlik": kimlik, "sembol": sembol, "yon": yon, "miktar": str(miktar), "giris_fiyati": str(gf), "mark_fiyat": str(mark), "giris_zamani": _t(t0),
            "stop": str(gf), "kz": kz, "kz_oran": 0.01, "nominal": nom, "kasaya_orani": 0.1, "stop_riski": "0.00"}


def _yaz(dizin: Path, isl: list, poz: list, bas="10000.00", ozs=None):
    dizin.mkdir(parents=True, exist_ok=True)
    (dizin / "islemler.jsonl").write_text("\n".join(json.dumps(x) for x in isl) + "\n", encoding="utf-8")
    (dizin / "maruziyet.json").write_text(json.dumps({"pozisyonlar": poz}), encoding="utf-8")
    (dizin / "ozet.json").write_text(json.dumps({"baslangic_ozsermaye": bas, "ozsermaye": ozs, "sayaclar": {"acik_pozisyon": len(poz)}}), encoding="utf-8")
    ham_i = [{"sembol": x["sembol"], "yon": 1 if x["yon"] == "long" else -1, "giris_zamani": {"__T": x["giris_zamani"]}, "cikis_zamani": {"__T": x["cikis_zamani"]},
              "net_pnl": float(x["net_pnl_yerel"]), "miktar": float(x["miktar"]), "kol": "k"} for x in isl]
    ham_a = {str(i): {"sembol": p["sembol"], "yon": 1 if p["yon"] == "long" else -1, "giris": float(p["giris_fiyati"]), "miktar": float(p["miktar"]),
                      "zaman": {"__T": p["giris_zamani"]}, "kol": "k"} for i, p in enumerate(poz)}
    (dizin / "paper_state.json").write_text(json.dumps({"motor": {"islemler": ham_i, "acik": ham_a}}), encoding="utf-8")


@pytest.fixture
def kurulum(tmp_path, monkeypatch):
    monkeypatch.setattr(pano, "_GIZLI", {GIZLI})
    monkeypatch.setenv("L3A_TELEGRAM_GONDERIM_DIZIN", str(tmp_path / "tglog"))
    durum, ct = tmp_path / "durum", tmp_path / "ct"
    isl = [_isl(GAUSS, "SOLUSDT", "long", 0, 0, 100, 110, 10, "98.00", 600, 660),
           _isl(GAUSS, "ETHUSDT", "short", 0, 0, 2000, 1900, 1, "98.00", 620, 680),       # kârlı short (fiyat düştü)
           _isl(GAUSS, "BTCUSDT", "short", 0, 0, 60000, 61000, "0.1", "-102.00", 640, 700),   # zararlı short (fiyat yükseldi)
           _isl(GIZLI, "XRPUSDT", "short", 0, 0, 2, 2.1, 100, "-11.00", 650, 710)]
    poz = [_poz(GAUSS, "SOLUSDT", "short", 150, 140, 1, "10.00", 720), _poz(GIZLI, "DOGEUSDT", "long", 1, 1.1, 10, "1.00", 721)]
    _yaz(durum, isl, poz, ozs="10104.00")      # görünür: 98+98-102 + açık 10 = 104
    ct_isl = [_isl(CT, "ETHUSDT", "short", 0, 0, 3000, 2900, 1, "95.00", 600, 650)]
    ct_poz = [_poz(CT, "BTCUSDT", "long", 60000, 60500, "0.01", "5.00", 700)]
    _yaz(ct, ct_isl, ct_poz, ozs="10100.00")
    return durum, ct


def test_uyumlu_senaryo_sifir_uyusmazlik(kurulum):
    durum, ct = kurulum
    c = im.hesapla(durum, ct)
    assert c["ozet"]["uyusmazlik_sayisi"] == 0, c["ozet"]["uyusmazliklar"]
    assert c["ozet"]["islem_sayisi"] == 8
    sh = c["ozet"]["short"]
    assert sh["sayi"] == 5 and sh["isaret_uyusmazligi"] == 0 and sh["panoda_long_gorunen"] == 0 and sh["telegramda_long_gorunen"] == 0
    assert any(s["coin"] == "ETH" and s["yon"] == "short" and float(s["net_kz"]) > 0 for s in c["satirlar"])      # kârlı short
    assert any(s["coin"] == "BTC" and s["yon"] == "short" and float(s["net_kz"]) < 0 for s in c["satirlar"])      # zararlı short
    assert im.TELEGRAM_NOTU in json.dumps(c, ensure_ascii=False)
    assert all(k["tamam"] for k in c["ozet"]["kasa_kontrolleri"])


def test_yon_bozulursa_yakalanir_ham_kayitla(kurulum):
    durum, ct = kurulum
    satirlar = [json.loads(x) for x in (durum / "islemler.jsonl").read_text(encoding="utf-8").splitlines()]
    for x in satirlar:
        if x["sembol"] == "ETHUSDT":
            x["yon"] = "long"                         # durum dosyası bozuk; ham motor kaydı short
    (durum / "islemler.jsonl").write_text("\n".join(json.dumps(x) for x in satirlar) + "\n", encoding="utf-8")
    c = im.hesapla(durum, ct)
    assert c["ozet"]["uyusmazlik_sayisi"] >= 1
    assert any("ham motor yönü short" in u["mesaj"] for u in c["ozet"]["uyusmazliklar"])
    assert c["ozet"]["short"]["motor_ham_long_gorunen"] == 0


def test_yon_bozulursa_ham_kayit_olmadan_isaret_kontroluyle_yakalanir(kurulum):
    durum, ct = kurulum
    (durum / "paper_state.json").unlink()
    satirlar = [json.loads(x) for x in (durum / "islemler.jsonl").read_text(encoding="utf-8").splitlines()]
    for x in satirlar:
        if x["sembol"] == "ETHUSDT":
            x["yon"] = "long"                         # fiyat 2000 -> 1900 düştü ama net +98: long olamaz
    (durum / "islemler.jsonl").write_text("\n".join(json.dumps(x) for x in satirlar) + "\n", encoding="utf-8")
    c = im.hesapla(durum, ct)
    assert any("işareti ters" in u["mesaj"] for u in c["ozet"]["uyusmazliklar"])


def test_telegram_gonderim_yanlis_yon_ve_eksik(kurulum, tmp_path):
    durum, ct = kurulum
    gonderim = tmp_path / "tglog"
    gonderim.mkdir()
    satirlar = [{"zaman": "2026-11-18T01:00:00Z", "ilk_satir": "[1L3A] 🟢 ETH long kapandı · Gauss", "seviye": "INFO"}]
    (gonderim / tg.GONDERIM_DOSYA).write_text("\n".join(json.dumps(x) for x in satirlar) + "\n", encoding="utf-8")
    ilk = pano._ad_goster(GAUSS)
    satirlar = [{"zaman": "2026-11-18T01:00:00Z", "ilk_satir": f"[1L3A] ✅ ETH long kapandı · {ilk}", "seviye": "INFO"}]
    (gonderim / tg.GONDERIM_DOSYA).write_text("\n".join(json.dumps(x) for x in satirlar) + "\n", encoding="utf-8")
    c = im.hesapla(durum, ct)
    t = c["ozet"]["telegram"]
    assert t["yanlis_yonlu"] == 1 and t["eksik"] >= 1


def test_gizli_hesap_adi_ciktida_yok(kurulum):
    durum, ct = kurulum
    c = im.yaz(durum, ct, cikti=durum / "mutabakat_v1.json")
    hepsi = (durum / "mutabakat_v1.json").read_text(encoding="utf-8") + (durum / "mutabakat_v1.md").read_text(encoding="utf-8") + json.dumps(c, ensure_ascii=False)
    assert GIZLI not in hepsi and "gizli-strateji" not in hepsi and "gizli_strateji" not in hepsi
    assert "Diğer hesap" in hepsi


def test_kasa_uyusmazligi_yakalanir(kurulum):
    durum, ct = kurulum
    oz = json.loads((durum / "ozet.json").read_text(encoding="utf-8"))
    oz["ozsermaye"] = "10150.00"
    (durum / "ozet.json").write_text(json.dumps(oz), encoding="utf-8")
    c = im.hesapla(durum, ct)
    assert any(u["tur"] == "kasa" for u in c["ozet"]["uyusmazliklar"])


def test_telegram_gonder_kaydi_yazar(tmp_path, monkeypatch):
    class Yanit:
        status_code, text = 200, ""

    class Oturum:
        def post(self, *a, **k):
            return Yanit()
    monkeypatch.setenv("L3A_TELEGRAM_GONDERIM_DIZIN", str(tmp_path))
    env = {"TELEGRAM_BOT_TOKEN": "t", "TELEGRAM_CHAT_ID": "1", "L3A_TELEGRAM_GONDERIM_DIZIN": str(tmp_path)}
    assert tg.gonder("[1L3A] 🟠 SOL short açıldı · Gauss\nGiriş 1 $", env=env, oturum=Oturum(), uyku=lambda s: None) is True
    kayit = [json.loads(x) for x in (tmp_path / tg.GONDERIM_DOSYA).read_text(encoding="utf-8").splitlines()]
    assert kayit[0]["ilk_satir"] == "[1L3A] 🟠 SOL short açıldı · Gauss" and kayit[0]["seviye"] == "INFO" and kayit[0]["zaman"].endswith("Z")


def test_worker_mutabakat_yolu_ve_yayin_baglantisi():
    js = (KOK / "deploy" / "pano_acik_worker.js").read_text(encoding="utf-8")
    assert "/mutabakat_v1.json" in js and "/gunluk_ozet_v1.json" in js and 'istek.method !== "GET"' in js and 'url.search !== ""' in js
    sh = (KOK / "deploy" / "pano_yayinla.sh").read_text(encoding="utf-8")
    assert "site/mutabakat_v1.json" in sh and sh.index("acik_yayinla()") < sh.index("site/mutabakat_v1.json")
    svc = (KOK / "deploy" / "1l3a-pano.service").read_text(encoding="utf-8")
    assert "ExecStartPost=-" in svc and "araclar.islem_mutabakat" in svc


# ---------------------------------------------------------------------------- net açık K/Z, kasa formülü, açık sayısı, Telegram özeti
def _gercek_motor_durumu(dizin: Path):
    """Gerçek motor yolu: paper çalıştırılır, açık pozisyona fonlama + kısmi kapanış brütü işlenir (nakit de motorun yaptığı gibi), paper_durum yazar."""
    import pandas as pd
    from motor.canli import durum as d
    from motor.canli import paper as pp
    from motor.canli import paper_durum as pdr
    from testler.test_paper_motor import TAN, kural, sentetik
    tans = [TAN["swing__cci-esik|SOLUSDT|1d"], TAN["pf__kesit_ls|kripto|1d"]]
    mum = {("SOLUSDT", "1d"): sentetik(520, "1d", 3, vol=0.04)}
    for k, s in enumerate(["BTCUSDT", "ETHUSDT"]):
        mum[(s, "1d")] = sentetik(520, "1d", 20 + k, vol=0.04)
    kur = {s: kural(s) for s in ("SOLUSDT", "BTCUSDT", "ETHUSDT")}
    ix = mum[("SOLUSDT", "1d")].index
    p = pp.tekrar_calistir(tans, mum, {}, kur, ix[380], ix[-1] + pd.Timedelta(days=1), kapat=False)
    m = p.motor
    assert m.acik, "senaryo açık pozisyon gerektirir"
    pos = next(iter(m.acik.values()))
    pos.funding += 5                      # fonlama ödendi: nakitten düştü
    m.nakit -= 5
    pos.brut_toplam += 20                 # kısmi kapanış brütü nakde yazıldı
    m.nakit += 20
    pos.cikis_kom += 1                    # kısmi kapanış çıkış komisyonu nakitten düştü
    m.nakit -= 1
    simdi = ix[-1] + pd.Timedelta(days=1, minutes=5)
    o = pdr.olustur(p, simdi, kaynak_saglik=[])
    d.yaz_hepsi(dizin, ozet=o["ozet"], stratejiler=o["stratejiler"], islemler=o["islemler"], saglik=o["saglik"], gecmis=o["gecmis"], ekstra=o["ekstra"])
    return p


def test_net_acik_kz_gercek_motor_eski_formul_uyusmaz_yenisi_sifir(tmp_path):
    dizin = tmp_path / "durum"
    dizin.mkdir()
    _gercek_motor_durumu(dizin)
    mr = json.loads((dizin / "maruziyet.json").read_text(encoding="utf-8"))
    assert all("kz_brut" in q for q in mr["pozisyonlar"]) and any(q["kz"] != q["kz_brut"] for q in mr["pozisyonlar"])
    c = im.hesapla(dizin)
    assert not [u for u in c["ozet"]["uyusmazliklar"] if u["tur"] == "kasa"], c["ozet"]["uyusmazliklar"]
    assert all(k["tamam"] for k in c["ozet"]["kasa_kontrolleri"])
    # eski formül: açık pozisyonlarda brüt mark K/Z -> uyuşmazlık
    for q in mr["pozisyonlar"]:
        q["kz"] = q.pop("kz_brut")
    (dizin / "maruziyet.json").write_text(json.dumps(mr), encoding="utf-8")
    c2 = im.hesapla(dizin)
    kasa = [u for u in c2["ozet"]["uyusmazliklar"] if u["tur"] == "kasa"]
    assert kasa and kasa[0]["birim"] == "usd" and abs(float(kasa[0]["fark"])) > 1
    assert any("eski kayıt" in k.get("not", "") for k in c2["ozet"]["kasa_kontrolleri"])


def test_askida_kapanis_kasa_formulune_katilir(kurulum):
    durum, ct = kurulum
    oz = json.loads((durum / "ozet.json").read_text(encoding="utf-8"))
    oz["ozsermaye"] = "10111.00"          # 10104 + askıda kapanış 4 + askıdaki açık 3
    oz["askida"] = {"kapanis_net": "4", "acik_net": "3", "acik_adet": 0}
    (durum / "ozet.json").write_text(json.dumps(oz), encoding="utf-8")
    c = im.hesapla(durum, ct)
    assert not [u for u in c["ozet"]["uyusmazliklar"] if u["tur"] == "kasa"]


def _v2_ham(durum: Path, fazladan_gorunur: int = 0):
    s = json.loads((durum / "paper_state.json").read_text(encoding="utf-8"))["motor"]
    gizli_acik = {k: v for k, v in s["acik"].items() if k == "1"}
    gorunur_acik = {k: v for k, v in s["acik"].items() if k == "0"}
    for i in range(fazladan_gorunur):
        gorunur_acik[f"x{i}"] = dict(s["acik"]["0"])
    (durum / "paper_state.json").write_text(json.dumps({"hesaplar": {
        GAUSS: {"motor": {"islemler": [x for x in s["islemler"] if x["sembol"] != "XRPUSDT"], "acik": gorunur_acik}},
        GIZLI: {"motor": {"islemler": [x for x in s["islemler"] if x["sembol"] == "XRPUSDT"], "acik": gizli_acik}}}}), encoding="utf-8")
    mr = json.loads((durum / "maruziyet.json").read_text(encoding="utf-8"))
    (durum / "maruziyet.json").write_text(json.dumps({"pozisyonlar": [p for p in mr["pozisyonlar"] if p["kimlik"] == GAUSS]}), encoding="utf-8")
    oz = json.loads((durum / "ozet.json").read_text(encoding="utf-8"))
    oz["sayaclar"]["acik_pozisyon"] = 1
    (durum / "ozet.json").write_text(json.dumps(oz), encoding="utf-8")


def test_ham_kayitta_gizli_hesap_acik_sayisini_bozmaz(kurulum):
    durum, ct = kurulum
    _v2_ham(durum)
    c = im.hesapla(durum, ct)
    assert not [u for u in c["ozet"]["uyusmazliklar"] if u["tur"] == "acik_sayisi"], c["ozet"]["uyusmazliklar"]


def test_ham_kayitta_askidaki_acik_sayilmaz(kurulum):
    durum, ct = kurulum
    _v2_ham(durum, fazladan_gorunur=1)         # görünür blokta 1 fazla kayıt = askıdaki pozisyon
    oz = json.loads((durum / "ozet.json").read_text(encoding="utf-8"))
    oz["askida"] = {"kapanis_net": "0", "acik_net": "0", "acik_adet": 1}
    (durum / "ozet.json").write_text(json.dumps(oz), encoding="utf-8")
    assert not [u for u in im.hesapla(durum, ct)["ozet"]["uyusmazliklar"] if u["tur"] == "acik_sayisi"]


def test_telegram_ozeti_sade_turkce(kurulum):
    from motor.canli import mutabakat_telegram as mt
    durum, ct = kurulum
    oz = json.loads((durum / "ozet.json").read_text(encoding="utf-8"))
    oz["ozsermaye"] = "10034.00"           # beklenen 10104
    (durum / "ozet.json").write_text(json.dumps(oz), encoding="utf-8")
    c = im.hesapla(durum, ct)
    m = mt.metin_uret(c)
    print(m)
    assert "Kasa 10.104,00 $ olmalı, kayıtta 10.034,00 $ · fark 70,00 $" in m and m.startswith("[1L3A] ⚠️ İşlem kontrolü: ")
    assert "Ayrıntı" not in m and "_" not in m
    assert len(m.split("\n")) <= 4
    _v2_ham(durum, fazladan_gorunur=2)
    c = im.hesapla(durum, ct)
    m = mt.metin_uret(c)
    print(m)
    assert "Açık pozisyon: kayıtta 3, panoda 1" in m
    c["ozet"]["uyusmazliklar"] = [{"islem_no": None, "hesap": "Ana", "tur": "acik_sayisi", "beklenen": 15, "kayit": 16, "fark": 1, "birim": "adet", "mesaj": "x"}] * 6
    c["ozet"]["uyusmazlik_sayisi"] = 6
    m = mt.metin_uret(c)
    print(m)
    assert "Açık pozisyon: kayıtta 16, panoda 15" in m and len(m.split("\n")) == 3
