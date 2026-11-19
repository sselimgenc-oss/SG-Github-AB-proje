"""Ortak öğrenme paketi parça 2 belirtiminden türetilmiş testler.

Kapsam: karne + sanal kasa (karne.py), ortak filtre ve paket (filtre.py),
CUSUM drift (drift.py). Testler yalnız belirtime göre yazıldı.
"""

from __future__ import annotations

import copy
import hashlib
import json
from datetime import datetime, timedelta, timezone

import numpy as np
import pytest

from ortak_ogrenme import kayit, karne, filtre, drift

UTC = timezone.utc
BASLANGIC = datetime(2026, 1, 1, tzinfo=UTC)
OLUS = datetime(2026, 11, 19, 12, 0, tzinfo=UTC)


def aday(i, *, r=None, alindi=True, kurulum="T1@1h", sinif="kripto",
         ozellikler=None, ts=None):
    return kayit.Aday(
        id=f"a{i}",
        proje="ML",
        kurulum=kurulum,
        enstruman="BTC/USDT",
        varlik_sinifi=sinif,
        yon="long",
        ts=ts if ts is not None else BASLANGIC + timedelta(hours=i),
        alindi=alindi,
        r=r,
        ozellikler=dict(ozellikler) if ozellikler is not None else {},
    )


def _sha(metin: str) -> str:
    return hashlib.sha256(metin.encode("utf-8")).hexdigest()


def egitim_verisi(n=40, kurulum="T1@1h"):
    """Özellik x ile sonuç birbirine bağlı, iki sınıflı, alındı işlemler."""
    out = []
    for i in range(n):
        kazanc = i % 2 == 0
        x = (1.0 + 0.01 * i) if kazanc else (-1.0 - 0.01 * i)
        out.append(aday(i, r=1.0 if kazanc else -1.0, kurulum=kurulum,
                        ozellikler={"x": x}))
    return out


def _ilk_sayi_artir(obj) -> bool:
    """Bir JSON yapısındaki ilk sayısal yaprağı artırır (kurcalama simülasyonu)."""
    def sayi(v):
        return isinstance(v, (int, float)) and not isinstance(v, bool)

    if isinstance(obj, dict):
        for k in list(obj):
            if sayi(obj[k]):
                obj[k] = obj[k] + 1.0
                return True
            if _ilk_sayi_artir(obj[k]):
                return True
    elif isinstance(obj, list):
        for idx, v in enumerate(obj):
            if sayi(v):
                obj[idx] = v + 1.0
                return True
            if _ilk_sayi_artir(v):
                return True
    return False


# --------------------------------------------------------------------------
# karne.karne
# --------------------------------------------------------------------------

def test_karne_alanlari_ve_ortalamalar():
    adaylar = [
        aday(0, r=1.0, alindi=True, sinif="kripto"),
        aday(1, r=-0.5, alindi=True, sinif="kripto"),
        aday(2, r=2.0, alindi=False, sinif="hisse"),
        aday(3, r=None, alindi=True, sinif="hisse"),
    ]
    k = karne.karne(adaylar)["T1@1h"]

    assert set(k) == {"aday", "alinan", "cozulen", "ort_r_alinan",
                      "ort_r_tum", "sinif", "kasa"}
    assert k["aday"] == 4
    assert k["alinan"] == 3          # alindi olanlar, r None olsa da sayılır
    assert k["cozulen"] == 3         # r'si olan: 0, 1, 2
    assert k["ort_r_alinan"] == pytest.approx((1.0 - 0.5) / 2)
    assert k["ort_r_tum"] == pytest.approx((1.0 - 0.5 + 2.0) / 3)
    assert k["kasa"] == karne.sanal_kasa(adaylar)["T1@1h"]


def test_karne_sinif_kirilimi_kasasiz():
    adaylar = [
        aday(0, r=1.0, alindi=True, sinif="kripto"),
        aday(1, r=-0.5, alindi=True, sinif="kripto"),
        aday(2, r=2.0, alindi=False, sinif="hisse"),
        aday(3, r=None, alindi=True, sinif="hisse"),
    ]
    sinif = karne.karne(adaylar)["T1@1h"]["sinif"]

    assert set(sinif) == {"kripto", "hisse"}
    for girdi in sinif.values():
        assert set(girdi) == {"aday", "alinan", "cozulen", "ort_r_alinan", "ort_r_tum"}
        assert "kasa" not in girdi

    kripto = sinif["kripto"]
    assert kripto["aday"] == 2
    assert kripto["alinan"] == 2
    assert kripto["cozulen"] == 2
    assert kripto["ort_r_alinan"] == pytest.approx(0.25)
    assert kripto["ort_r_tum"] == pytest.approx(0.25)

    hisse = sinif["hisse"]
    assert hisse["aday"] == 2
    assert hisse["alinan"] == 1
    assert hisse["cozulen"] == 1
    assert hisse["ort_r_alinan"] is None   # alındı ama r yok
    assert hisse["ort_r_tum"] == pytest.approx(2.0)


def test_karne_r_yoksa_ortalamalar_none():
    adaylar = [aday(0, r=None, alindi=True), aday(1, r=None, alindi=False)]
    k = karne.karne(adaylar)["T1@1h"]
    assert k["aday"] == 2
    assert k["cozulen"] == 0
    assert k["ort_r_alinan"] is None
    assert k["ort_r_tum"] is None


def test_karne_alindi_olmayan_r_alinan_ortalamaya_girmez():
    adaylar = [aday(0, r=3.0, alindi=False), aday(1, r=1.0, alindi=True)]
    k = karne.karne(adaylar)["T1@1h"]
    assert k["ort_r_alinan"] == pytest.approx(1.0)
    assert k["ort_r_tum"] == pytest.approx(2.0)


def test_karne_adaysiz_kurulum_sifir_satir():
    sonuc = karne.karne([], kurulumlar=("Z",))
    assert list(sonuc) == ["Z"]
    k = sonuc["Z"]
    assert k["aday"] == 0
    assert k["alinan"] == 0
    assert k["cozulen"] == 0
    assert k["ort_r_alinan"] is None
    assert k["ort_r_tum"] is None
    assert k["sinif"] == {}
    assert k["kasa"]["alinan"]["n"] == 0
    assert k["kasa"]["alinan"]["kasa"] == pytest.approx(1000.0)


def test_karne_kurulum_sirasi_once_kurulumlar_sonra_gorulme():
    adaylar = [
        aday(0, r=1.0, kurulum="B"),
        aday(1, r=1.0, kurulum="A"),
    ]
    sonuc = karne.karne(adaylar, kurulumlar=("Z", "A"))
    assert list(sonuc) == ["Z", "A", "B"]
    assert sonuc["Z"]["aday"] == 0
    assert sonuc["A"]["aday"] == 1
    assert sonuc["B"]["aday"] == 1


# --------------------------------------------------------------------------
# karne.sanal_kasa
# --------------------------------------------------------------------------

def test_sanal_kasa_bilesik_getiri():
    res = karne.sanal_kasa([aday(0, r=2.0), aday(1, r=-1.0)])
    seri = res["T1@1h"]["alinan"]
    assert seri["n"] == 2
    assert seri["kasa"] == pytest.approx(1009.8)
    assert seri["getiri_pct"] == pytest.approx(0.98)


def test_sanal_kasa_alt_sinir_sifir():
    adaylar = [aday(0, r=-2.0), aday(1, r=1.0)]
    res = karne.sanal_kasa(adaylar, risk=1.0)
    assert res["T1@1h"]["alinan"]["kasa"] == 0.0


def test_sanal_kasa_dusus_baslangictan_olculur():
    res = karne.sanal_kasa([aday(0, r=-1.0), aday(1, r=2.0)])
    seri = res["T1@1h"]["alinan"]
    # 1000 -> 990 -> 1009.8: en derin nokta başlangıçtan %1 (işaret belirtimde
    # tanımlı değil; büyüklük kontrol edilir)
    assert abs(seri["en_derin_pct"]) == pytest.approx(1.0, abs=0.01)
    assert seri["kasa"] == pytest.approx(1009.8)


def test_sanal_kasa_ayni_ts_stabil_siralama():
    ts = BASLANGIC
    kayip_once = [aday(0, r=-1.0, ts=ts), aday(1, r=1.0, ts=ts)]
    kazanc_once = [aday(1, r=1.0, ts=ts), aday(0, r=-1.0, ts=ts)]

    seri_a = karne.sanal_kasa(kayip_once)["T1@1h"]["alinan"]
    seri_b = karne.sanal_kasa(kazanc_once)["T1@1h"]["alinan"]

    # Girdi sırası korunur: önce -1 (990), sonra +1 -> en derin %1 (büyüklük)
    assert abs(seri_a["en_derin_pct"]) == pytest.approx(1.0, abs=0.01)
    assert seri_a["kasa"] == pytest.approx(999.9)
    # (lider duzeltmesi) Dusus TEPEDEN olculur (ML ile ayni): 1000 -> 1010 -> 999.9 => (1010-999.9)/1010 = %1.0
    assert abs(seri_b["en_derin_pct"]) == pytest.approx(1.0, abs=0.01)
    assert seri_b["kasa"] == pytest.approx(999.9)
    # Sira korunur: once kayip => 990 dibi baslangictan; once kazanc => tepe 1010 (kasa yolu farkli, sonuc ayni)
    assert seri_a["kasa"] == seri_b["kasa"]


def test_sanal_kasa_ts_sirasina_gore_isler():
    gec = aday(5, r=-1.0)
    erken = aday(0, r=2.0)
    res = karne.sanal_kasa([gec, erken])
    assert res["T1@1h"]["alinan"]["kasa"] == pytest.approx(1009.8)


def test_sanal_kasa_alinan_ve_tum_ayrimi():
    adaylar = [
        aday(0, r=1.0, alindi=False),
        aday(1, r=1.0, alindi=True),
        aday(2, r=None, alindi=True),
    ]
    res = karne.sanal_kasa(adaylar)["T1@1h"]
    assert res["alinan"]["n"] == 1
    assert res["tum"]["n"] == 2


@pytest.mark.parametrize("kwargs", [
    {"baslangic": 0.0},
    {"baslangic": -5.0},
    {"risk": 0.0},
    {"risk": -0.01},
])
def test_sanal_kasa_gecersiz_parametre(kwargs):
    with pytest.raises(ValueError):
        karne.sanal_kasa([aday(0, r=1.0)], **kwargs)


# --------------------------------------------------------------------------
# filtre: özellik adları, matris
# --------------------------------------------------------------------------

def test_ozellik_adlari_sirali_birlesim_sayi_olmayanlar_yok():
    adaylar = [
        aday(0, ozellikler={"rr": 2.0, "atr_ratio": 1.1, "etiket": "metin"}),
        aday(1, ozellikler={"stop_dist_atr": 2, "rr": 3.0, "bos": None}),
    ]
    assert filtre.ozellik_adlari(adaylar) == ["atr_ratio", "rr", "stop_dist_atr"]


def test_matris_eksik_ve_sayi_olmayan_nan():
    adaylar = [
        aday(0, ozellikler={"a": 1.0}),
        aday(1, ozellikler={"b": "x", "a": None}),
    ]
    m = filtre.matris(["a", "b"], adaylar)
    assert isinstance(m, np.ndarray)
    assert m.shape == (2, 2)
    assert m[0, 0] == pytest.approx(1.0)
    assert np.isnan(m[0, 1])
    assert np.isnan(m[1, 0])
    assert np.isnan(m[1, 1])


# --------------------------------------------------------------------------
# filtre.egit
# --------------------------------------------------------------------------

def test_egit_yalniz_alindi_ve_r_olanlar():
    adaylar = egitim_verisi(40)
    adaylar += [aday(100 + i, r=1.0, alindi=False, ozellikler={"x": 5.0})
                for i in range(10)]           # alınmamış: dışarıda
    adaylar += [aday(200 + i, r=None, alindi=True, ozellikler={"x": -5.0})
                for i in range(5)]            # r yok: dışarıda
    paket = filtre.egit("T1@1h", adaylar, olusturma=OLUS)

    assert paket is not None
    assert paket["meta"]["n_egitim"] == 40
    assert paket["meta"]["n_pozitif"] == 20


def test_egit_kilit_araligi_dusurur_ve_sayar():
    adaylar = egitim_verisi(40)
    kilit = [(BASLANGIC + timedelta(hours=10, minutes=30),
              BASLANGIC + timedelta(hours=19, minutes=30))]
    paket = filtre.egit("T1@1h", adaylar, olusturma=OLUS, kilit=kilit)

    # saat 11..19 arasındaki 9 satır düşer, sınırlar belirsiz değil
    assert paket["meta"]["kilit_dusen"] == 9
    assert paket["meta"]["n_egitim"] == 31


def test_egit_azami_son_satirlari_tutar():
    etiketler = [1.0] * 7 + [-1.0, 1.0, -1.0]   # son 3: -1, +1, -1
    adaylar = [aday(i, r=r, ozellikler={"x": float(i)})
               for i, r in enumerate(etiketler)]
    paket = filtre.egit("T1@1h", list(reversed(adaylar)), olusturma=OLUS, azami=3)

    assert paket["meta"]["n_egitim"] == 3
    assert paket["meta"]["n_pozitif"] == 1


def test_egit_veri_yok_ya_da_tek_sinif_none():
    assert filtre.egit("T1@1h", [], olusturma=OLUS) is None
    tek_negatif = [aday(i, r=-1.0, ozellikler={"x": float(i)}) for i in range(30)]
    assert filtre.egit("T1@1h", tek_negatif, olusturma=OLUS) is None
    tek_pozitif = [aday(i, r=1.0, ozellikler={"x": float(i)}) for i in range(30)]
    assert filtre.egit("T1@1h", tek_pozitif, olusturma=OLUS) is None
    hic_alinmamis = [aday(i, r=1.0, alindi=False, ozellikler={"x": float(i)})
                     for i in range(30)]
    assert filtre.egit("T1@1h", hic_alinmamis, olusturma=OLUS) is None


def test_egit_r_sifir_etiket_negatif():
    adaylar = egitim_verisi(40)
    adaylar += [aday(300 + i, r=0.0, ozellikler={"x": 0.5}) for i in range(10)]
    paket = filtre.egit("T1@1h", adaylar, olusturma=OLUS)
    assert paket["meta"]["n_pozitif"] == 20      # r=0 pozitif sayılmaz


def test_egit_esik_taban_orani_ile_iliskili():
    adaylar = egitim_verisi(40)
    # daha az pozitif: 10 ekstra negatif
    adaylar += [aday(400 + i, r=-1.0, ozellikler={"x": -2.0}) for i in range(10)]
    paket = filtre.egit("T1@1h", adaylar, olusturma=OLUS)
    meta = paket["meta"]
    assert meta["taban_oran"] == pytest.approx(meta["n_pozitif"] / meta["n_egitim"])
    assert paket["esik"] == pytest.approx(0.9 * meta["taban_oran"])


def test_egit_paket_ve_meta_alanlari():
    adaylar = egitim_verisi(40)
    paket = filtre.egit("T1@1h", adaylar, olusturma=OLUS)

    assert set(paket) >= {"meta", "model", "esik"}
    meta = paket["meta"]
    assert set(meta) >= {"paket_surumu", "tur", "kurulum", "olusturma",
                         "son_kullanma", "ozellikler", "ozellik_hash",
                         "n_egitim", "n_pozitif", "taban_oran",
                         "kilit_dusen", "model_hash"}
    assert meta["paket_surumu"] == 1
    assert meta["tur"] == "ortak_filtre"
    assert meta["kurulum"] == "T1@1h"
    assert datetime.fromisoformat(meta["olusturma"]) == OLUS
    assert datetime.fromisoformat(meta["son_kullanma"]) == OLUS + timedelta(days=21)
    assert list(meta["ozellikler"]) == ["x"]
    assert meta["ozellik_hash"] == _sha("\n".join(meta["ozellikler"]))
    assert meta["kilit_dusen"] == 0


def test_egit_model_hash_kanonik_json():
    adaylar = egitim_verisi(40)
    paket = filtre.egit("T1@1h", adaylar, olusturma=OLUS)
    kanonik = json.dumps({"model": paket["model"], "esik": paket["esik"]},
                         sort_keys=True, separators=(",", ":"))
    assert paket["meta"]["model_hash"] == _sha(kanonik)


# --------------------------------------------------------------------------
# filtre.kaydet / yukle
# --------------------------------------------------------------------------

def test_kaydet_yukle_gidis_donus(tmp_path):
    paket = filtre.egit("T1@1h", egitim_verisi(40), olusturma=OLUS)
    yol = filtre.kaydet(paket, tmp_path)

    assert yol.name == "T1@1h.json"
    yuklenen = filtre.yukle(str(yol), simdi=OLUS + timedelta(days=1))
    assert yuklenen["esik"] == paket["esik"]
    assert yuklenen["meta"]["model_hash"] == paket["meta"]["model_hash"]
    for x in (1.0, -1.0, 0.0):
        assert filtre.puan(yuklenen, {"x": x}) == pytest.approx(
            filtre.puan(paket, {"x": x}))


def test_yukle_sozluk_kabul_eder():
    paket = filtre.egit("T1@1h", egitim_verisi(40), olusturma=OLUS)
    yuklenen = filtre.yukle(copy.deepcopy(paket), simdi=OLUS + timedelta(days=1))
    assert yuklenen["meta"]["model_hash"] == paket["meta"]["model_hash"]


def test_kaydet_ikinci_kayitta_prev_dosyasi(tmp_path):
    ilk = filtre.egit("T1@1h", egitim_verisi(40), olusturma=OLUS)
    filtre.kaydet(ilk, tmp_path)

    farkli = [aday(i, r=(1.0 if i % 3 else -1.0), ozellikler={"x": float(i % 5)})
              for i in range(40)]
    ikinci = filtre.egit("T1@1h", farkli, olusturma=OLUS + timedelta(hours=1))
    assert ikinci["meta"]["model_hash"] != ilk["meta"]["model_hash"]
    yol = filtre.kaydet(ikinci, tmp_path)

    prev = tmp_path / "T1@1h.prev.json"
    assert prev.exists()
    onceki = filtre.yukle(str(prev), sure_kontrol=False)
    assert onceki["meta"]["model_hash"] == ilk["meta"]["model_hash"]
    guncel = filtre.yukle(str(yol), simdi=OLUS + timedelta(days=1))
    assert guncel["meta"]["model_hash"] == ikinci["meta"]["model_hash"]


def test_yukle_kurcalanmis_model_paket_hatasi(tmp_path):
    paket = filtre.egit("T1@1h", egitim_verisi(40), olusturma=OLUS)
    yol = filtre.kaydet(paket, tmp_path)

    veri = json.loads(yol.read_text(encoding="utf-8"))
    assert _ilk_sayi_artir(veri["model"])
    yol.write_text(json.dumps(veri), encoding="utf-8")

    with pytest.raises(filtre.PaketHatasi):
        filtre.yukle(str(yol), simdi=OLUS + timedelta(days=1))


def test_yukle_suresi_dolmus_paket_hatasi_ama_kontrolsuz_yuklenir(tmp_path):
    paket = filtre.egit("T1@1h", egitim_verisi(40), olusturma=OLUS)
    yol = filtre.kaydet(paket, tmp_path)

    gecmis = OLUS + timedelta(days=21, seconds=1)
    with pytest.raises(filtre.PaketHatasi):
        filtre.yukle(str(yol), simdi=gecmis)

    yuklenen = filtre.yukle(str(yol), simdi=gecmis, sure_kontrol=False)
    assert yuklenen["meta"]["model_hash"] == paket["meta"]["model_hash"]


@pytest.mark.parametrize("kurulum, beklenen", [
    ("BTC/USDT 1h", "BTC_USDT_1h.json"),
    ("T1@1h", "T1@1h.json"),
])
def test_kaydet_guvenli_ad(tmp_path, kurulum, beklenen):
    paket = filtre.egit("T1@1h", egitim_verisi(40), olusturma=OLUS)
    paket = copy.deepcopy(paket)
    paket["meta"]["kurulum"] = kurulum
    yol = filtre.kaydet(paket, tmp_path)
    assert yol.name == beklenen


@pytest.mark.parametrize("kurulum", [".gizli", "..", ""])
def test_kaydet_nokta_veya_bos_ad_value_error(tmp_path, kurulum):
    paket = copy.deepcopy(filtre.egit("T1@1h", egitim_verisi(40), olusturma=OLUS))
    paket["meta"]["kurulum"] = kurulum
    with pytest.raises(ValueError):
        filtre.kaydet(paket, tmp_path)


# --------------------------------------------------------------------------
# filtre.puan
# --------------------------------------------------------------------------

def test_puan_aralik_ve_eksik_ozellik():
    paket = filtre.egit("T1@1h", egitim_verisi(40), olusturma=OLUS)
    for ozellikler in ({"x": 1.0}, {"x": -1.0}, {"x": 1e6}, {}):
        p = filtre.puan(paket, ozellikler)
        assert isinstance(p, float)
        assert 0.0 <= p <= 1.0


def test_puan_kazanca_iliskili_ozellik_daha_yuksek():
    paket = filtre.egit("T1@1h", egitim_verisi(40), olusturma=OLUS)
    assert filtre.puan(paket, {"x": 1.0}) > filtre.puan(paket, {"x": -1.0})


# --------------------------------------------------------------------------
# drift
# --------------------------------------------------------------------------

def test_drift_sabitleri():
    assert drift.CUSUM_MU0 == -0.111
    assert drift.CUSUM_SIGMA0 == 1.224
    assert drift.CUSUM_K == 0.5
    assert tuple(drift.CUSUM_CLIP) == (-1.5, 3.0)
    assert drift.CUSUM_UYARI == 4.0
    assert drift.CUSUM_COOLDOWN == 30
    assert drift.MIN_N == 20


def test_cusum_kucuk_pozitif_sabit_alarm_yok():
    sonuc = drift.cusum([0.1] * 200)
    assert sonuc["alarms"] == []
    assert sonuc["S"] == pytest.approx(0.0)
    assert sonuc["n"] == 200


def test_cusum_uzun_kayip_serisi_alarm_ve_cooldown():
    sonuc = drift.cusum([-1.5] * 100)
    alarmlar = sonuc["alarms"]
    assert len(alarmlar) >= 2
    assert alarmlar[0] >= 20
    # cooldown 30: ardışık alarmlar arası en az 30 işlem
    for a, b in zip(alarmlar, alarmlar[1:]):
        assert b - a >= 30


def test_cusum_clip_kayip_sinirlanir():
    assert drift.cusum([-10.0] * 60) == drift.cusum([-1.5] * 60)


def test_kurulum_drift_uyari_ve_normal():
    adaylar = [aday(i, r=-1.5, kurulum="A") for i in range(25)]
    adaylar += [aday(100 + i, r=0.2, kurulum="B") for i in range(25)]
    sonuc = drift.kurulum_drift(adaylar)

    assert sonuc["A"]["durum"] == "uyari"
    assert sonuc["B"]["durum"] == "normal"


def test_kurulum_drift_alinmamis_satirlar_dislanir():
    adaylar = [aday(i, r=-1.5, alindi=False, kurulum="C") for i in range(25)]
    sonuc = drift.kurulum_drift(adaylar)
    # Satırı olmayan kurulum anahtarla hiç yer almayabilir; yer alıyorsa normal olmalı
    assert sonuc.get("C", {"durum": "normal"})["durum"] == "normal"


def test_kurulum_drift_ts_sirasi_girdi_sirasindan_bagimsiz():
    adaylar = [aday(i, r=-1.5, kurulum="A") for i in range(25)]
    assert drift.kurulum_drift(list(reversed(adaylar))) == drift.kurulum_drift(adaylar)


def test_kurulum_drift_eski_alarm_normal_doner():
    adaylar = [aday(i, r=-1.5, kurulum="D") for i in range(25)]
    adaylar += [aday(100 + i, r=0.0, kurulum="D") for i in range(40)]
    sonuc = drift.kurulum_drift(adaylar)
    assert sonuc["D"]["durum"] == "normal"
