"""Ortak ogrenme paketi parca 2 (spec bolum 4): ML ile esdegerlik + filtre paket gidis-donusu.

ML referanslari: counterfactual.arm_scorecard / arm_virtual_bankroll, setup_filter.train.fit_logistic,
drift_monitor.cusum_replay, TreeModel (logistic tahmin). Paket tarafi yalniz standart kutuphane + numpy.
"""
from __future__ import annotations

import copy
import json
from datetime import datetime, timedelta, timezone

import numpy as np
import pytest

from trader_core.counterfactual import arm_scorecard, arm_virtual_bankroll
from trader_core.drift_monitor import cusum_replay
from trader_core.ml_eval import TreeModel
from trader_ml.setup_filter.train import fit_logistic as ml_fit_logistic

from ortak_ogrenme import drift, filtre, karne
from ortak_ogrenme.kayit import Aday

T0 = datetime(2026, 5, 1, tzinfo=timezone.utc)
OLUS = datetime(2026, 11, 1, 9, 0, tzinfo=timezone.utc)
KURULUMLAR = ("T1", "R1", "X9")          # X9: adayi olmayan (sifir satir) kurulum
SINIFLAR = ("kripto", "hisse", "emtia")


def _adaylar(rng, n=240, kurulumlar=("T1", "R1")):
    out = []
    for i in range(n):
        r = None if rng.random() < 0.1 else float(rng.normal(0.1, 1.2))
        if i == 3:
            r = -150.0                     # kasayi sifira indiren kayip (max(0, ...) dalinin testi)
        out.append(Aday(
            id=str(i), proje="ML", kurulum=str(rng.choice(kurulumlar)), enstruman="BTC/USDT",
            varlik_sinifi=str(rng.choice(SINIFLAR)), yon="long",
            # saat olcegi: esitlikler (ayni ts) kasitli olarak olusur
            ts=T0 + timedelta(hours=int(rng.integers(0, 400))),
            alindi=bool(rng.random() < 0.5), r=r,
            ozellikler={"a": float(rng.normal()), "b": float(rng.normal(size=1)[0]) * 3}
            if rng.random() < 0.85 else {"a": "yok", "c": float(i)},
        ))
    return out


def _ml_cands(adaylar):
    return [{"arm_id": a.kurulum, "ts": a.ts, "r": a.r, "taken": a.alindi, "asset_class": a.varlik_sinifi}
            for a in adaylar]


def _ort_esle(ours, ref):
    if ref is None:
        assert ours is None
    else:
        assert ours == pytest.approx(ref, rel=1e-12, abs=1e-12)


def _blok_esle(ml, k):
    assert k["aday"] == ml["candidates"]
    assert k["alinan"] == ml["taken"]
    assert k["cozulen"] == ml["resolved"]
    _ort_esle(k["ort_r_alinan"], ml["mean_r_taken"])
    _ort_esle(k["ort_r_tum"], ml["mean_r_taken_cf"])


def _seri_esle(ml, k):
    assert k["n"] == ml["n"]
    assert k["kasa"] == ml["equity"]
    assert k["getiri_pct"] == ml["return_pct"]
    assert k["en_derin_pct"] == ml["max_dd_pct"]


# --------------------------------------------------------------------------- karne / sanal kasa
@pytest.mark.parametrize("seed", [0, 1, 2])
def test_karne_arm_scorecard_esdeger(seed):
    rng = np.random.default_rng(seed)
    adaylar = _adaylar(rng)
    ml = arm_scorecard(_ml_cands(adaylar), arms=KURULUMLAR)
    k = karne.karne(adaylar, kurulumlar=KURULUMLAR)
    assert list(k) == list(ml)                       # sira: once kurulumlar, sonra goruldugu sira
    for arm in ml:
        _blok_esle(ml[arm], k[arm])
        assert set(k[arm]["sinif"]) == set(ml[arm]["by_class"])
        for cls, mb in ml[arm]["by_class"].items():
            _blok_esle(mb, k[arm]["sinif"][cls])
        assert "kasa" in k[arm] and "sinif" in k[arm]
    assert k["X9"]["aday"] == 0 and k["X9"]["sinif"] == {}


@pytest.mark.parametrize("seed", [0, 1])
def test_sanal_kasa_arm_virtual_bankroll_esdeger(seed):
    rng = np.random.default_rng(seed)
    adaylar = _adaylar(rng)
    ml = arm_virtual_bankroll(_ml_cands(adaylar), start=1000.0, risk=0.01, arms=KURULUMLAR)
    kasa = karne.sanal_kasa(adaylar, baslangic=1000.0, risk=0.01, kurulumlar=KURULUMLAR)
    assert list(kasa) == list(ml)
    for arm in ml:
        _seri_esle(ml[arm]["taken"], kasa[arm]["alinan"])
        _seri_esle(ml[arm]["cf"], kasa[arm]["tum"])


def test_karne_kasa_arm_scorecard_kasa_ile_ayni():
    rng = np.random.default_rng(7)
    adaylar = _adaylar(rng)
    ml = arm_scorecard(_ml_cands(adaylar), arms=KURULUMLAR)
    k = karne.karne(adaylar, kurulumlar=KURULUMLAR)
    for arm in ml:
        _seri_esle(ml[arm]["kasa"]["taken"], k[arm]["kasa"]["alinan"])
        _seri_esle(ml[arm]["kasa"]["cf"], k[arm]["kasa"]["tum"])


def test_sanal_kasa_parametre_dogrulama():
    with pytest.raises(ValueError):
        karne.sanal_kasa([], baslangic=0.0)
    with pytest.raises(ValueError):
        karne.sanal_kasa([], risk=0.0)


# --------------------------------------------------------------------------- lojistik (ML fit_logistic)
@pytest.mark.parametrize("seed", [0, 3])
def test_fit_logistic_ml_ile_allclose(seed):
    rng = np.random.default_rng(seed)
    n, k = 400, 5
    X = rng.normal(size=(n, k))
    X[:, 2] = 1.7                                    # sabit kolon: std<1e-12 -> 1
    X[rng.random((n, k)) < 0.15] = np.nan            # NaN dahil
    X[:, 4][rng.random(n) < 0.99] = np.nan           # neredeyse tamamen NaN kolon
    y = (rng.random(n) < 0.4).astype(float)
    ml = ml_fit_logistic(X, y)
    ours = filtre.fit_logistic(X, y)
    assert ours["n_features"] == ml["n_features"]
    for alan in ("coef", "mean", "std", "fill"):
        assert np.allclose(ours[alan], ml[alan], rtol=1e-9, atol=1e-12), alan
    assert ours["intercept"] == pytest.approx(ml["intercept"], rel=1e-9, abs=1e-12)


def test_puan_ml_logistic_tahmini_ile_ayni():
    rng = np.random.default_rng(11)
    adaylar = [a for a in _adaylar(rng, n=300, kurulumlar=("T1",)) if a.alindi and a.r is not None]
    paket = filtre.egit("T1", adaylar, olusturma=OLUS)
    assert paket is not None
    adlar = paket["meta"]["ozellikler"]
    X = filtre.matris(adlar, adaylar)
    ml_p = TreeModel(paket["model"], {"a": 1.0, "b": 0.0}).predict_proba(X)
    ours = [filtre.puan(paket, a.ozellikler) for a in adaylar]
    assert np.allclose(ours, ml_p, rtol=1e-12, atol=1e-12)


# --------------------------------------------------------------------------- CUSUM (ML cusum_replay)
@pytest.mark.parametrize("seed", [0, 1, 2, 3])
def test_cusum_cusum_replay_esdeger(seed):
    rng = np.random.default_rng(seed)
    rs = list(rng.normal(-0.8, 1.1, 260)) + [-12.0, 9.0] + list(rng.normal(0.2, 1.0, 120))
    ml = cusum_replay(rs)
    ours = drift.cusum(rs)
    assert ml["alarms"], "test serisi alarm uretmeli"
    assert ours["alarms"] == ml["alarms"]
    assert ours["n"] == ml["n"]
    assert ours["cooldown"] == ml["cooldown"]
    assert ours["S"] == pytest.approx(ml["S"], rel=1e-12, abs=1e-12)


def test_cusum_sabitleri_ml_ile_ayni():
    from trader_core import drift_monitor as DM
    assert drift.CUSUM_MU0 == DM.CUSUM_MU0 and drift.CUSUM_SIGMA0 == DM.CUSUM_SIGMA0
    assert drift.CUSUM_K == DM.CUSUM_K and drift.CUSUM_CLIP == (DM.CUSUM_CLIP_LO, DM.CUSUM_CLIP_HI)
    assert drift.CUSUM_UYARI == DM.CUSUM_UYARI and drift.CUSUM_COOLDOWN == DM.CUSUM_COOLDOWN
    assert drift.MIN_N == DM.MIN_N


def test_kurulum_drift_durum_uyari():
    rng = np.random.default_rng(5)
    rs = list(rng.normal(-0.9, 1.0, 60))
    adaylar = [Aday(id=str(i), proje="ML", kurulum="T1", enstruman="BTC/USDT", varlik_sinifi="kripto",
                    yon="long", ts=T0 + timedelta(hours=i), alindi=True, r=float(r))
               for i, r in enumerate(rs)]
    sonuc = drift.kurulum_drift(adaylar)["T1"]
    assert sonuc["alarms"] and sonuc["alarms"] == cusum_replay(rs)["alarms"]
    kalan = sonuc["n"] - sonuc["alarms"][-1]
    assert sonuc["durum"] == ("uyari" if kalan < drift.CUSUM_COOLDOWN else "normal")


# --------------------------------------------------------------------------- filtre paket gidis-donusu
def _egitim_adaylari(seed=21, n=260):
    rng = np.random.default_rng(seed)
    out = []
    for i in range(n):
        ozel = {}
        if rng.random() < 0.8:
            ozel["a"] = float(rng.normal())
        if rng.random() < 0.7:
            ozel["b"] = float(rng.normal()) * 2
        if rng.random() < 0.1:
            ozel["c"] = "metin"                       # sayi olmayan: yok sayilir
        r = float(rng.normal(0.05 + 0.3 * (ozel.get("a", 0.0) > 0), 1.0))
        out.append(Aday(id=str(i), proje="ML", kurulum="T1", enstruman="BTC/USDT", varlik_sinifi="kripto",
                        yon="long", ts=T0 + timedelta(hours=i), alindi=bool(rng.random() < 0.8),
                        r=None if rng.random() < 0.05 else r, ozellikler=ozel))
    return out


def test_egit_paket_yapisi_ve_hash():
    adaylar = _egitim_adaylari()
    paket = filtre.egit("T1", adaylar, olusturma=OLUS)
    m = paket["meta"]
    assert m["paket_surumu"] == 1 and m["tur"] == "ortak_filtre" and m["kurulum"] == "T1"
    assert m["son_kullanma"] == (OLUS + timedelta(days=21)).isoformat()
    assert m["ozellikler"] == sorted(m["ozellikler"]) == ["a", "b"]    # "c" sayi degil
    assert 0.0 < paket["esik"] <= 1.0 and paket["esik"] == pytest.approx(0.9 * m["taban_oran"])
    elig = [a for a in adaylar if a.alindi and a.r is not None]
    assert m["n_egitim"] == len(elig) and m["kilit_dusen"] == 0
    assert m["n_pozitif"] == sum(1 for a in elig if a.r > 0)
    filtre.yukle(json.loads(json.dumps(paket)), simdi=OLUS)            # hash'ler tutar


def test_kaydet_yukle_gidis_donus(tmp_path):
    paket = filtre.egit("T1", _egitim_adaylari(), olusturma=OLUS)
    yol = filtre.kaydet(paket, tmp_path)
    assert yol == tmp_path / "T1.json" and not (tmp_path / "T1.prev.json").exists()
    geri = filtre.yukle(yol, simdi=OLUS + timedelta(days=1))
    assert geri == json.loads(json.dumps(paket))
    # ikinci kayit: eskisi .prev.json olur
    yeni = filtre.egit("T1", _egitim_adaylari(seed=22), olusturma=OLUS + timedelta(hours=1))
    filtre.kaydet(yeni, tmp_path)
    assert (tmp_path / "T1.prev.json").exists()
    assert filtre.yukle(tmp_path / "T1.json", simdi=OLUS)["meta"]["olusturma"] == yeni["meta"]["olusturma"]
    assert not list(tmp_path.glob(".filtre-*.tmp"))


def test_hash_tamper_paket_hatasi(tmp_path):
    paket = filtre.egit("T1", _egitim_adaylari(), olusturma=OLUS)
    bozuk = copy.deepcopy(paket)
    bozuk["model"]["coef"][0] += 1e-6                 # model degisti, model_hash tutmaz
    with pytest.raises(filtre.PaketHatasi):
        filtre.yukle(bozuk, simdi=OLUS)
    bozuk2 = copy.deepcopy(paket)
    bozuk2["esik"] = 0.99                              # esik de model_hash kapsaminda
    with pytest.raises(filtre.PaketHatasi):
        filtre.yukle(bozuk2, simdi=OLUS)
    bozuk3 = copy.deepcopy(paket)
    bozuk3["meta"]["ozellikler"] = ["a", "zz"]          # ozellik hash'i tutmaz
    with pytest.raises(filtre.PaketHatasi):
        filtre.yukle(bozuk3, simdi=OLUS)
    # dosyada bozulma
    yol = filtre.kaydet(paket, tmp_path)
    metin = yol.read_text(encoding="utf-8").replace('"intercept": ', '"intercept": 9', 1)
    yol.write_text(metin, encoding="utf-8")
    with pytest.raises(filtre.PaketHatasi):
        filtre.yukle(yol, simdi=OLUS)


def test_son_kullanma_suresi(tmp_path):
    paket = filtre.egit("T1", _egitim_adaylari(), olusturma=OLUS)
    filtre.yukle(paket, simdi=OLUS + timedelta(days=20, hours=23))      # henuz gecerli
    with pytest.raises(filtre.PaketHatasi):
        filtre.yukle(paket, simdi=OLUS + timedelta(days=21))            # son kullanma aninda dolmus
    filtre.yukle(paket, simdi=OLUS + timedelta(days=30), sure_kontrol=False)
    yol = filtre.kaydet(paket, tmp_path)                                 # kayit suresi denetlemez
    with pytest.raises(filtre.PaketHatasi):
        filtre.yukle(yol, simdi=OLUS + timedelta(days=22))


def test_kilit_aralik_egitimden_dusurur():
    adaylar = _egitim_adaylari()
    kilit = [(T0 + timedelta(hours=50), T0 + timedelta(hours=99)),
             (T0 + timedelta(hours=200), T0 + timedelta(hours=200))]    # tek noktali aralik da dahil
    elig = [a for a in adaylar if a.alindi and a.r is not None]
    beklenen = sum(1 for a in elig if any(b <= a.ts <= e for b, e in kilit))
    assert beklenen > 0
    paket = filtre.egit("T1", adaylar, olusturma=OLUS, kilit=kilit)
    assert paket["meta"]["kilit_dusen"] == beklenen
    assert paket["meta"]["n_egitim"] == len(elig) - beklenen
    sinir = [a for a in elig if not any(b <= a.ts <= e for b, e in kilit)]
    assert paket["meta"]["n_egitim"] == len(sinir)


def test_egit_azami_son_satirlar():
    adaylar = _egitim_adaylari()
    paket = filtre.egit("T1", adaylar, olusturma=OLUS, azami=50)
    assert paket["meta"]["n_egitim"] == 50


def test_egit_tek_sinif_ve_bos_none():
    tum_pozitif = [Aday(id=str(i), proje="ML", kurulum="T1", enstruman="E", varlik_sinifi="kripto", yon="long",
                        ts=T0 + timedelta(hours=i), alindi=True, r=1.0 + i, ozellikler={"a": float(i)})
                   for i in range(30)]
    assert filtre.egit("T1", tum_pozitif, olusturma=OLUS) is None
    assert filtre.egit("T1", [], olusturma=OLUS) is None
    assert filtre.egit("T2", _egitim_adaylari(), olusturma=OLUS) is None   # kurulum adayi yok


def test_kilit_tek_sinifa_dusurur():
    adaylar = _egitim_adaylari()
    tum = (T0 - timedelta(days=1), T0 + timedelta(days=30))
    assert filtre.egit("T1", adaylar, olusturma=OLUS, kilit=[tum]) is None


def test_kaydet_ad_dogrulama(tmp_path):
    paket = filtre.egit("T1", _egitim_adaylari(), olusturma=OLUS)
    for kurulum in (".", ".gizli", ""):
        p = copy.deepcopy(paket)
        p["meta"]["kurulum"] = kurulum
        with pytest.raises(ValueError):
            filtre.kaydet(p, tmp_path)
    p = copy.deepcopy(paket)
    p["meta"]["kurulum"] = "T1@1h/x y"
    assert filtre.kaydet(p, tmp_path).name == "T1@1h_x_y.json"


def test_puan_0_1_aralik_ve_eksik_ozellik():
    paket = filtre.egit("T1", _egitim_adaylari(), olusturma=OLUS)
    rng = np.random.default_rng(4)
    for _ in range(200):
        ozel = {}
        if rng.random() < 0.7:
            ozel["a"] = float(rng.normal() * 1e6)     # asiri degerler: sigmoid kirpilir
        if rng.random() < 0.5:
            ozel["b"] = float("nan") if rng.random() < 0.3 else float(rng.normal())
        p = filtre.puan(paket, ozel)
        assert 0.0 <= p <= 1.0 and math_isfinite(p)
    # tamamen eksik ozellik: fill degerleriyle tek bir sabit puan
    assert filtre.puan(paket, {}) == filtre.puan(paket, {"a": float("nan"), "b": "x"})


def math_isfinite(x: float) -> bool:
    return x == x and x not in (float("inf"), float("-inf"))
