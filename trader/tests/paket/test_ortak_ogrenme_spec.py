"""Ortak ogrenme paketi icin belirtime dayali testler.

Kaynak: docs/standart/ortak-ogrenme-paketi-spec.md. Uygulama kodu okunmadan
yazildi; belirsiz kalan noktalar skip nedeni veya yorumla isaretlendi.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

import pytest

from ortak_ogrenme import ders, kayit, notlar

UTC = timezone.utc
T1 = "T1@1h"
K_SEANS = "seans_kapali:T1@1h"
K_VOL = "yuksek_vol:T1@1h"
K_RR = "dusuk_rr:T1@1h"
LOSS_FEATURES = dict(
    seans="closed",
    kurulum=T1,
    ozellikler={"atr_ratio": 1.5, "rr": 1.0, "stop_dist_atr": 2.0},
)


def _ts(y, m, d, h=12, mi=0, s=0):
    return datetime(y, m, d, h, mi, s, tzinfo=UTC)


def _aday(**kw) -> kayit.Aday:
    base = dict(
        id="a1",
        proje="ML",
        kurulum=T1,
        enstruman="BTC/USDT",
        varlik_sinifi="kripto",
        yon="long",
        ts=_ts(2026, 3, 11),
        alindi=True,
        r=1.0,
        seans="open",
        rejim="trend_up",
        ozellikler={"atr_ratio": 1.0, "rr": 2.5, "stop_dist_atr": 2.0},
        etiketler=(),
        cikis={},
    )
    base.update(kw)
    return kayit.Aday(**base)


def _tags(**kw):
    tags, _metin = notlar.not_yaz(_aday(**kw))
    return tags


def _kayip(**kw):
    return _aday(**{"r": -1.0, **kw})


# ---------------------------------------------------------------------------
# kayit.py: round-trip, dogrulama, JSONL
# ---------------------------------------------------------------------------

def _gecerli_dict():
    return {
        "id": "x1",
        "proje": "ML",
        "kurulum": T1,
        "enstruman": "BTC/USDT",
        "varlik_sinifi": "kripto",
        "yon": "long",
        "ts": "2026-03-10T12:00:00Z",
        "alindi": True,
        "r": 1.0,
    }


def test_gecerli_dict_parse_edilir():
    a = kayit.aday_from_dict(_gecerli_dict())
    assert a.id == "x1"
    assert a.ts == _ts(2026, 3, 10)
    assert a.ts.utcoffset().total_seconds() == 0


@pytest.mark.parametrize(
    "alan", ["id", "proje", "kurulum", "enstruman", "varlik_sinifi", "yon", "ts", "alindi"]
)
def test_zorunlu_alan_eksikse_valueerror(alan):
    d = _gecerli_dict()
    del d[alan]
    with pytest.raises(ValueError):
        kayit.aday_from_dict(d)


@pytest.mark.parametrize("yon", ["up", "buy", ""])
def test_gecersiz_yon_valueerror(yon):
    d = _gecerli_dict()
    d["yon"] = yon
    with pytest.raises(ValueError):
        kayit.aday_from_dict(d)


@pytest.mark.parametrize("varlik", ["forex", "", "crypto"])
def test_gecersiz_varlik_sinifi_valueerror(varlik):
    d = _gecerli_dict()
    d["varlik_sinifi"] = varlik
    with pytest.raises(ValueError):
        kayit.aday_from_dict(d)


@pytest.mark.parametrize("varlik", ["kripto", "hisse", "emtia"])
def test_gecerli_varlik_sinifi_kabul_edilir(varlik):
    d = _gecerli_dict()
    d["varlik_sinifi"] = varlik
    assert kayit.aday_from_dict(d).varlik_sinifi == varlik


def test_tzsiz_ts_valueerror():
    d = _gecerli_dict()
    d["ts"] = "2026-03-10T12:00:00"
    with pytest.raises(ValueError):
        kayit.aday_from_dict(d)


def test_dict_round_trip_kayipsiz():
    a = kayit.Aday(
        id="x1",
        proje="1L3A",
        kurulum="strat-A",
        enstruman="AAPL",
        varlik_sinifi="hisse",
        yon="short",
        ts=_ts(2026, 3, 10, 14, 30),
        alindi=False,
        r=-0.42,
        seans="closed",
        rejim="range",
        ozellikler={"atr_ratio": 1.1, "rr": 2.2},
        etiketler=("ct:ayni_yon", "giris:iyi"),
        cikis={
            "entry_price": 10.0,
            "planned_entry": 10.0,
            "planned_stop": 10.5,
            "exit_reason": "stop",
            "bars_held": 3,
            "mfe_r": 0.5,
            "mae_r": -1.0,
        },
    )
    d = kayit.aday_to_dict(a)
    assert d["ts"] == "2026-03-10T14:30:00Z"
    assert kayit.aday_from_dict(d) == a
    assert kayit.aday_from_dict(json.loads(json.dumps(d))) == a


def test_round_trip_opsiyonel_alanlar_none_ve_bos():
    a = kayit.Aday(
        id="x2",
        proje="CT",
        kurulum="kopya-1",
        enstruman="ETH/USDT",
        varlik_sinifi="kripto",
        yon="long",
        ts=_ts(2026, 1, 2),
        alindi=False,
        r=None,
    )
    assert kayit.aday_from_dict(json.loads(json.dumps(kayit.aday_to_dict(a)))) == a


def test_yaz_oku_jsonl_round_trip_ve_satir_formati(tmp_path):
    p = tmp_path / "adaylar.jsonl"
    adaylar = [
        _aday(id="a1"),
        _aday(
            id="a2",
            r=None,
            alindi=False,
            etiketler=("ct:ayni_yon",),
            cikis={"exit_reason": "stop şartı"},
        ),
    ]
    kayit.yaz_jsonl(p, adaylar)
    assert kayit.oku_jsonl(p) == adaylar

    satirlar = p.read_text(encoding="utf-8").splitlines()
    assert len(satirlar) == 2
    for satir in satirlar:
        assert isinstance(json.loads(satir), dict)


def test_yaz_jsonl_uzerine_yazar_eklemez(tmp_path):
    p = tmp_path / "adaylar.jsonl"
    kayit.yaz_jsonl(p, [_aday(id="a1"), _aday(id="a2")])
    kayit.yaz_jsonl(p, [_aday(id="a3")])
    assert kayit.oku_jsonl(p) == [_aday(id="a3")]


def test_yaz_jsonl_bos_liste(tmp_path):
    p = tmp_path / "bos.jsonl"
    kayit.yaz_jsonl(p, [])
    assert kayit.oku_jsonl(p) == []


def test_yaz_jsonl_atomik_hata_orijinali_bozmaz(tmp_path):
    p = tmp_path / "adaylar.jsonl"
    kayit.yaz_jsonl(p, [_aday(id="ilk")])
    onceki = p.read_bytes()

    # JSON'a dusturulemeyen bir deger: yazma yarida kalmali.
    bozuk = _aday(id="bozuk", cikis={"x": object()})
    with pytest.raises((TypeError, ValueError)):
        kayit.yaz_jsonl(p, [_aday(id="yeni"), bozuk])

    assert p.read_bytes() == onceki
    assert sorted(x.name for x in tmp_path.iterdir()) == ["adaylar.jsonl"]


def test_yaz_jsonl_basarili_yazimdan_sonra_gecici_dosya_kalmaz(tmp_path):
    p = tmp_path / "adaylar.jsonl"
    kayit.yaz_jsonl(p, [_aday(id="a1")])
    assert sorted(x.name for x in tmp_path.iterdir()) == ["adaylar.jsonl"]


# ---------------------------------------------------------------------------
# notlar.py: ders kimligi, ders_uyar_mi
# ---------------------------------------------------------------------------

def test_ders_kimligi_bicimi():
    assert notlar.ders_kimligi("seans_kapali", "T1@1h") == "seans_kapali:T1@1h"


def test_ders_uyar_mi_seans_kapali():
    assert notlar.ders_uyar_mi("seans_kapali", T1, _aday(seans="closed")) is True
    assert notlar.ders_uyar_mi("seans_kapali", T1, _aday(seans="weekend")) is True
    assert notlar.ders_uyar_mi("seans_kapali", T1, _aday(seans="open")) is False
    assert notlar.ders_uyar_mi("seans_kapali", T1, _aday(seans=None)) is False


def test_ders_uyar_mi_kurulum_eslesmezse_false():
    assert notlar.ders_uyar_mi("seans_kapali", T1, _aday(seans="closed", kurulum="R1@1h")) is False


@pytest.mark.parametrize(
    "atr, beklenen",
    [(1.3, True), (1.2999, False), (2.0, True), (1.0, False)],
)
def test_ders_uyar_mi_yuksek_vol_esik(atr, beklenen):
    aday = _aday(ozellikler={"atr_ratio": atr, "rr": 2.5})
    assert notlar.ders_uyar_mi("yuksek_vol", T1, aday) is beklenen


@pytest.mark.parametrize("ozellik", [None, "abc"])
def test_ders_uyar_mi_yuksek_vol_eksik_veya_sayi_degil(ozellik):
    aday = _aday(ozellikler={"atr_ratio": ozellik} if ozellik is not None else {})
    assert notlar.ders_uyar_mi("yuksek_vol", T1, aday) is False


def test_ders_uyar_mi_yuksek_vol_ozellik_hic_yok():
    assert notlar.ders_uyar_mi("yuksek_vol", T1, _aday(ozellikler={})) is False


@pytest.mark.parametrize(
    "rr, beklenen",
    [(1.99, True), (2.0, False), (2.5, False)],
)
def test_ders_uyar_mi_dusuk_rr_esik(rr, beklenen):
    aday = _aday(ozellikler={"atr_ratio": 1.0, "rr": rr})
    assert notlar.ders_uyar_mi("dusuk_rr", T1, aday) is beklenen


@pytest.mark.parametrize("ozellik", [None, "abc"])
def test_ders_uyar_mi_dusuk_rr_eksik_veya_sayi_degil(ozellik):
    aday = _aday(ozellikler={"rr": ozellik} if ozellik is not None else {})
    assert notlar.ders_uyar_mi("dusuk_rr", T1, aday) is False


def test_ders_uyar_mi_dusuk_rr_kurulum_eslesmezse_false():
    aday = _aday(kurulum="R1@1h", ozellikler={"rr": 1.0})
    assert notlar.ders_uyar_mi("dusuk_rr", T1, aday) is False


# ---------------------------------------------------------------------------
# notlar.py: not_yaz
# ---------------------------------------------------------------------------

def test_not_yaz_alinmayan_aday_valueerror():
    with pytest.raises(ValueError):
        notlar.not_yaz(_aday(alindi=False, r=1.0))


def test_not_yaz_r_none_valueerror():
    with pytest.raises(ValueError):
        notlar.not_yaz(_aday(alindi=True, r=None))


def test_not_yaz_donus_tipi_ve_tek_satir_metin_iki_ondalik():
    tags, metin = notlar.not_yaz(_aday(r=1.2567, ozellikler={}))
    assert isinstance(tags, list)
    assert all(isinstance(t, str) for t in tags)
    assert isinstance(metin, str)
    assert "\n" not in metin
    assert "1.26" in metin
    assert "1.2567" not in metin


def test_not_yaz_bilinmeyen_deger_yok_olarak_yazilir():
    _tags_, metin = notlar.not_yaz(_aday(r=1.0, ozellikler={}, cikis={}))
    assert "yok" in metin


def test_giris_iyi_bilgi_yoksa():
    assert "giris:iyi" in _tags(cikis={})


def _giris(entry, planned_entry, planned_stop):
    return {"entry_price": entry, "planned_entry": planned_entry, "planned_stop": planned_stop}


def test_giris_kayma_siniri_tam_010_iyi_kabul():
    # |101-100| / |100-90| = 0.10 -> '> 0.10' kosulu saglanmaz
    t = _tags(cikis=_giris(101.0, 100.0, 90.0))
    assert "giris:iyi" in t
    assert "giris:kotu_dolum" not in t


def test_giris_kayma_010_ustu_kotu_dolum():
    t = _tags(cikis=_giris(101.1, 100.0, 90.0))
    assert "giris:kotu_dolum" in t
    assert "giris:iyi" not in t


def test_giris_kayma_kisa_pozisyonda_mutlak_deger():
    # short: stop 110, planned 100 -> pay 10
    assert "giris:iyi" in _tags(yon="short", cikis=_giris(99.0, 100.0, 110.0))
    assert "giris:kotu_dolum" in _tags(yon="short", cikis=_giris(98.0, 100.0, 110.0))


def test_stop_dar_normal_genis_sinirlari():
    def stop(v):
        return _tags(ozellikler={"stop_dist_atr": v})

    assert stop(0.99) != stop(1.0)  # dar -> normal sinirinda degisir
    assert stop(1.0) == stop(2.0)  # ikisi de normal
    assert stop(3.0) == stop(2.0)  # 3.0 normal (geniş degil)
    assert stop(3.01) != stop(3.0)  # geniş sinirinda degisir
    assert stop(0.5) != stop(4.0)  # dar ve geniş farklı etiket
    assert stop(0.5) != stop(2.0)


def test_seans_etiketi_kapali_ve_acik_farkli():
    assert _tags(seans="closed") != _tags(seans="open")


def test_rejim_none_unclear_ile_ayni():
    assert _tags(rejim=None) == _tags(rejim="unclear")
    assert _tags(rejim="trend_up") != _tags(rejim="unclear")


def test_olay_bilinmiyor_etiketi_var():
    # Aday olay bilgisi tasimaz (belirtimde olay alani yok)
    assert "olay:bilinmiyor" in _tags()


def test_uyum_kurulum_on_eki_at_isaretinden_once():
    assert _tags(kurulum="T1@1h", rejim="trend_up") == _tags(kurulum="T1@4h", rejim="trend_up")
    assert _tags(kurulum="T1", rejim="trend_up") == _tags(kurulum="T1@1h", rejim="trend_up")


def test_uyum_tablosu_uyumsuz_ve_uyumlu():
    # Ayni rejim, yalniz kurulum farkli: uyum etiketi degisir
    assert _tags(kurulum="T1@1h", rejim="range") != _tags(kurulum="R1@1h", rejim="range")
    assert _tags(kurulum="R1@1h", rejim="range") == _tags(kurulum="R1@4h", rejim="range")


def test_uyum_bilinmeyen_kurulum_uyumlu_sayilir():
    assert _tags(kurulum="Z9@1h", rejim="range") == _tags(kurulum="R1@1h", rejim="range")


def test_sonuc_kazanc_kayip_basabas_ayri_etiket():
    kazanc = _tags(r=1.0)
    kayip = _tags(r=-1.0)
    basabas = _tags(r=0.0)
    assert len({tuple(kazanc), tuple(kayip), tuple(basabas)}) == 3


@pytest.mark.skip(reason="Belirtim 'kacinilabilir' etiketinin kuralini tanimlamiyor")
def test_kacinilabilir_etiketi_kurali():
    raise NotImplementedError


@pytest.mark.skip(reason="Belirtim sozluk ve validate_tags'in bu pakette nasil acildigini tanimlamiyor")
def test_etiket_sozluk_disi_valueerror():
    raise NotImplementedError


def test_ders_etiketleri_yalnizca_kayipta():
    tags, _ = notlar.not_yaz(_kayip(**LOSS_FEATURES))
    ders_tags = sorted(t for t in tags if t.startswith("ders:"))
    assert ders_tags == sorted(["ders:" + K_SEANS, "ders:" + K_VOL, "ders:" + K_RR])


@pytest.mark.parametrize("r", [1.0, 0.0])
def test_ders_etiketi_kazanc_ve_basabasta_yok(r):
    tags, _ = notlar.not_yaz(_aday(r=r, **LOSS_FEATURES))
    assert not [t for t in tags if t.startswith("ders:")]


def test_ders_etiketi_kurulum_eslesmezse_yok():
    # (lider duzeltmesi) ders kimligi her zaman adayin KENDI kurulumuyla uretilir; baska kurulumun dersi yazilmaz
    tags, _ = notlar.not_yaz(_kayip(**{**LOSS_FEATURES, "kurulum": "R1@1h"}))
    ders_t = [t for t in tags if t.startswith("ders:")]
    assert ders_t and all(t.endswith(":R1@1h") for t in ders_t)
    assert not [t for t in ders_t if t.endswith(":" + T1)]


def test_ders_etiketi_yalniz_uyan_kodlar():
    tags, _ = notlar.not_yaz(
        _kayip(seans="open", kurulum=T1, ozellikler={"atr_ratio": 1.0, "rr": 1.0})
    )
    assert [t for t in tags if t.startswith("ders:")] == ["ders:" + K_RR]


def test_etiket_sirasi_giris_basta_ders_sonda():
    # Belirtim sirasini listeler: giris ... sonuc, ders en sonda
    tags, _ = notlar.not_yaz(_kayip(**LOSS_FEATURES))
    assert tags[0].startswith("giris:")
    ders_idx = [i for i, t in enumerate(tags) if t.startswith("ders:")]
    assert ders_idx
    assert ders_idx == list(range(len(tags) - len(ders_idx), len(tags)))


# ---------------------------------------------------------------------------
# ders.py: ders_etkisi
# ---------------------------------------------------------------------------

def _pencere_adaylari():
    return [
        _aday(id="pre", ts=_ts(2026, 3, 10, 23, 59, 59), seans="closed", r=-5.0),
        _aday(id="in1", ts=_ts(2026, 3, 11, 0, 0, 0), seans="closed", r=-1.0),
        _aday(id="in2", ts=_ts(2026, 3, 11, 12), seans="closed", r=-2.0),
        _aday(id="asof", ts=_ts(2026, 3, 12, 0, 0, 0), seans="closed", r=-100.0),
        _aday(id="alinmadi", ts=_ts(2026, 3, 11, 6), seans="closed", alindi=False, r=-50.0),
        _aday(id="r_yok", ts=_ts(2026, 3, 11, 7), seans="closed", r=None),
        _aday(id="acik", ts=_ts(2026, 3, 11, 8), seans="open", r=-30.0),
        _aday(id="baska_kurulum", ts=_ts(2026, 3, 11, 9), seans="closed", kurulum="R1@1h", r=-30.0),
    ]


def test_ders_etkisi_pencere_ve_filtreler():
    etki, n = ders.ders_etkisi(
        _pencere_adaylari(), K_SEANS, "2026-03-10", _ts(2026, 3, 12, 0, 0, 0)
    )
    # Dahil: in1 (-1), in2 (-2). Toplam r = -3 -> etki = +3.0
    assert n == 2
    assert etki == pytest.approx(3.0)


def test_ders_etkisi_kazanc_negatif_etki():
    adaylar = [_aday(ts=_ts(2026, 3, 11, 12), seans="closed", r=2.0)]
    etki, n = ders.ders_etkisi(adaylar, K_SEANS, "2026-03-10", _ts(2026, 3, 12))
    assert (etki, n) == (pytest.approx(-2.0), 1)


@pytest.mark.parametrize("shrink_n, beklenen", [(2, 1.5), (8, 0.6)])
def test_ders_etkisi_shrink_formulu(shrink_n, beklenen):
    # n = 2, etki = 3 * n/(n+shrink)
    etki, n = ders.ders_etkisi(
        _pencere_adaylari(), K_SEANS, "2026-03-10", _ts(2026, 3, 12, 0, 0, 0), shrink_n=shrink_n   # (lider duzeltmesi: _ts varsayilan saati 12)
    )
    assert n == 2
    assert etki == pytest.approx(beklenen)


def test_ders_etkisi_n_sifir():
    assert ders.ders_etkisi([], K_SEANS, "2026-03-10", _ts(2026, 3, 12)) == (0.0, 0)
    sadece_acik = [_aday(ts=_ts(2026, 3, 11, 12), seans="open", r=-1.0)]
    assert ders.ders_etkisi(sadece_acik, K_SEANS, "2026-03-10", _ts(2026, 3, 12)) == (0.0, 0)


# ---------------------------------------------------------------------------
# ders.py: gece_adimi, etkin_dersler, uyan_dersler, fren_durumu
# ---------------------------------------------------------------------------

NOT_DOGUM = [{"note_date": "2026-03-10", "tags": ["giris:iyi", "ders:" + K_SEANS]}]
ZARAR_11 = _aday(id="z11", ts=_ts(2026, 3, 11, 12), seans="closed", kurulum=T1, r=-1.0)
KAZANC_11 = _aday(id="k11", ts=_ts(2026, 3, 11, 12), seans="closed", kurulum=T1, r=1.0)
KAZANC_12 = _aday(id="k12", ts=_ts(2026, 3, 12, 6), seans="closed", kurulum=T1, r=2.0)


def _durum_yolu(tmp_path) -> str:
    return str(tmp_path / "ders_durumu.json")


def _oku_durum(p: str) -> dict:
    with open(p, encoding="utf-8") as f:
        return json.load(f)


def _yaz_durum(p: str, veri: dict):
    with open(p, "w", encoding="utf-8") as f:
        json.dump(veri, f)


def test_gece_not_dan_candidate_dogar_ve_bekler(tmp_path):
    p = _durum_yolu(tmp_path)
    out = ders.gece_adimi([], NOT_DOGUM, p, "2026-03-10")
    assert out["born"] == [K_SEANS]
    assert out["alive"] == []
    assert out["retired"] == []
    durum = _oku_durum(p)
    assert durum[K_SEANS]["status"] == "candidate"
    assert durum[K_SEANS]["born"] == "2026-03-10"
    assert ders.etkin_dersler(p) == [K_SEANS]


def test_gece_ders_olmayan_etiketler_dogurmaz(tmp_path):
    p = _durum_yolu(tmp_path)
    out = ders.gece_adimi([], [{"note_date": "2026-03-10", "tags": ["giris:iyi"]}], p, "2026-03-10")
    assert out["born"] == []


def test_candidate_pozitif_etkiyle_alive(tmp_path):
    p = _durum_yolu(tmp_path)
    ders.gece_adimi([], NOT_DOGUM, p, "2026-03-10")
    out = ders.gece_adimi([ZARAR_11], [], p, "2026-03-12")
    assert out["alive"] == [K_SEANS]
    assert out["retired"] == []
    assert _oku_durum(p)[K_SEANS]["status"] == "alive"


@pytest.mark.parametrize("r", [1.0, 0.0])
def test_candidate_sifir_veya_negatif_etkiyle_retired(tmp_path, r):
    p = _durum_yolu(tmp_path)
    ders.gece_adimi([], NOT_DOGUM, p, "2026-03-10")
    kazanc = _aday(id="k", ts=_ts(2026, 3, 11, 12), seans="closed", kurulum=T1, r=r)
    out = ders.gece_adimi([kazanc], [], p, "2026-03-12")
    assert out["retired"] == [K_SEANS]
    durum = _oku_durum(p)
    assert durum[K_SEANS]["status"] == "retired"
    assert durum[K_SEANS]["retired_day"] == "2026-03-12"


def test_n_sifirken_candidate_birden_fazla_gece_bekler(tmp_path):
    p = _durum_yolu(tmp_path)
    ders.gece_adimi([], NOT_DOGUM, p, "2026-03-10")
    for gun in ("2026-03-11", "2026-03-12"):
        out = ders.gece_adimi([], [], p, gun)
        assert out["alive"] == [] and out["retired"] == []
    assert _oku_durum(p)[K_SEANS]["status"] == "candidate"


def test_alive_sonra_negatif_etkiyle_retired(tmp_path):
    p = _durum_yolu(tmp_path)
    ders.gece_adimi([], NOT_DOGUM, p, "2026-03-10")
    ders.gece_adimi([ZARAR_11], [], p, "2026-03-12")  # alive
    # Kumulatif r: -1 + 2 = +1 -> etki -1 -> retired
    out = ders.gece_adimi([KAZANC_12], [], p, "2026-03-13")
    assert out["retired"] == [K_SEANS]
    assert _oku_durum(p)[K_SEANS]["status"] == "retired"


def test_emekli_geri_donmez(tmp_path):
    p = _durum_yolu(tmp_path)
    ders.gece_adimi([], NOT_DOGUM, p, "2026-03-10")
    ders.gece_adimi([KAZANC_11], [], p, "2026-03-12")  # retired
    assert _oku_durum(p)[K_SEANS]["status"] == "retired"

    # Sonraki gecelerde pozitif etki ve ayni ders notu: yine emekli
    out = ders.gece_adimi([ZARAR_11], NOT_DOGUM, p, "2026-03-13")
    assert out["alive"] == []
    assert out["born"] == []
    assert _oku_durum(p)[K_SEANS]["status"] == "retired"
    assert ders.etkin_dersler(p) == []


def test_gece_adimi_durum_dosyasi_atomik_yazilir(tmp_path):
    p = _durum_yolu(tmp_path)
    ders.gece_adimi([], NOT_DOGUM, p, "2026-03-10")
    assert sorted(x.name for x in tmp_path.iterdir()) == ["ders_durumu.json"]


def test_bozuk_durum_dosyasi_bos_sayilir(tmp_path):
    p = _durum_yolu(tmp_path)
    Path(p).write_text("{bozuk json", encoding="utf-8")
    assert ders.etkin_dersler(p) == []
    out = ders.gece_adimi([], NOT_DOGUM, p, "2026-03-10")
    assert out["born"] == [K_SEANS]
    assert _oku_durum(p)[K_SEANS]["status"] == "candidate"


def test_eksik_durum_dosyasi_bos_sayilir(tmp_path):
    assert ders.etkin_dersler(_durum_yolu(tmp_path)) == []


def test_etkin_dersler_siralama(tmp_path):
    p = _durum_yolu(tmp_path)
    _yaz_durum(p, {
        "dusuk_rr:T1@1h": {"status": "alive", "born": "2026-03-01", "effect": 1.0, "n": 5},
        "seans_kapali:T1@1h": {"status": "alive", "born": "2026-03-01", "effect": 3.0, "n": 5},
        "yuksek_vol:T1@1h": {"status": "candidate", "born": "2026-03-05", "effect": 5.0, "n": 4},
        "yuksek_vol:R1@1h": {"status": "candidate", "born": "2026-03-05", "effect": 0.5, "n": 2},
        "eski:T1@1h": {"status": "retired", "born": "2026-02-01", "effect": -2.0, "n": 4,
                       "retired_day": "2026-03-09"},
    })
    assert ders.etkin_dersler(p) == [
        "seans_kapali:T1@1h",  # alive, etki 3.0
        "dusuk_rr:T1@1h",      # alive, etki 1.0
        "yuksek_vol:T1@1h",    # candidate, etki 5.0
        "yuksek_vol:R1@1h",    # candidate, etki 0.5
    ]


def test_etkin_dersler_esitlikte_kimlik_sirasi(tmp_path):
    p = _durum_yolu(tmp_path)
    _yaz_durum(p, {
        "seans_kapali:T1@1h": {"status": "alive", "born": "2026-03-01", "effect": 2.0, "n": 3},
        "dusuk_rr:T1@1h": {"status": "alive", "born": "2026-03-01", "effect": 2.0, "n": 3},
    })
    assert ders.etkin_dersler(p) == ["dusuk_rr:T1@1h", "seans_kapali:T1@1h"]


def test_etkin_dersler_limit(tmp_path):
    p = _durum_yolu(tmp_path)
    veri = {
        f"k{i:02d}:T1@1h": {"status": "alive", "born": "2026-03-01", "effect": float(i), "n": 3}
        for i in range(10)
    }
    _yaz_durum(p, veri)
    beklenen = [f"k{i:02d}:T1@1h" for i in range(9, 1, -1)]  # varsayilan limit 8
    assert ders.etkin_dersler(p) == beklenen
    assert ders.etkin_dersler(p, limit=3) == beklenen[:3]


def test_uyan_dersler_aday_kosullarina_gore():
    etkin = [K_SEANS, K_VOL, K_RR]
    hepsi = _aday(seans="closed", kurulum=T1, ozellikler={"atr_ratio": 1.5, "rr": 1.0})
    assert sorted(ders.uyan_dersler(etkin, hepsi)) == sorted(etkin)

    hicbiri = _aday(seans="open", kurulum=T1, ozellikler={"atr_ratio": 1.0, "rr": 2.5})
    assert ders.uyan_dersler(etkin, hicbiri) == []

    karisik = _aday(seans="closed", kurulum=T1, ozellikler={"atr_ratio": 1.0, "rr": 1.0})
    assert sorted(ders.uyan_dersler(etkin, karisik)) == sorted([K_SEANS, K_RR])


def test_uyan_dersler_kurulum_eslesmezse_bos():
    aday = _aday(seans="closed", kurulum="R1@1h", ozellikler={"atr_ratio": 1.5, "rr": 1.0})
    assert ders.uyan_dersler([K_SEANS, K_VOL, K_RR], aday) == []


FREN_BAS = datetime(2026, 3, 1, tzinfo=UTC)
FREN_SON = datetime(2026, 3, 31, tzinfo=UTC)


def _s_islem(i, r, alindi=True):
    # seans_kapali'ya uyar, diger dersler uymaz
    return _aday(id=f"s{i}", ts=_ts(2026, 3, 4 + i), seans="closed", kurulum=T1,
                 ozellikler={"atr_ratio": 1.0, "rr": 2.5}, r=r, alindi=alindi)


def _v_islem(i, r):
    # yuksek_vol'a uyar, diger dersler uymaz
    return _aday(id=f"v{i}", ts=_ts(2026, 3, 4 + i), seans="open", kurulum=T1,
                 ozellikler={"atr_ratio": 1.5, "rr": 2.5}, r=r)


def _r_islem(i, r):
    # dusuk_rr'a uyar, diger dersler uymaz
    return _aday(id=f"r{i}", ts=_ts(2026, 3, 4 + i), seans="open", kurulum=T1,
                 ozellikler={"atr_ratio": 1.0, "rr": 1.0}, r=r)


def test_fren_toplam_esik_siniri_tam_minus_10():
    adaylar = [_s_islem(1, 2.0), _s_islem(2, 2.0), _s_islem(3, 2.0),
               _v_islem(1, 2.0), _v_islem(2, 2.0)]
    s = ders.fren_durumu(adaylar, [K_SEANS, K_VOL], FREN_BAS, FREN_SON)
    assert s["toplam_etki"] == pytest.approx(-10.0)
    assert s["fren"] is True
    assert sorted(s["geri_al"]) == sorted([K_SEANS, K_VOL])


def test_fren_toplam_esik_ustunde_fren_yok():
    adaylar = [_s_islem(1, 2.0), _s_islem(2, 2.0), _s_islem(3, 2.0),
               _v_islem(1, 2.0), _v_islem(2, 2.0), _r_islem(1, -0.5)]
    s = ders.fren_durumu(adaylar, [K_SEANS, K_VOL, K_RR], FREN_BAS, FREN_SON)
    assert s["toplam_etki"] == pytest.approx(-9.5)
    assert s["fren"] is False
    assert sorted(s["geri_al"]) == sorted([K_SEANS, K_VOL])


def test_fren_esik_parametresi():
    adaylar = [_s_islem(1, 2.0), _s_islem(2, 2.0), _s_islem(3, 2.0),
               _v_islem(1, 2.0), _v_islem(2, 2.0), _r_islem(1, -0.5)]
    s = ders.fren_durumu(adaylar, [K_SEANS, K_VOL, K_RR], FREN_BAS, FREN_SON, esik_r=9.0)
    assert s["fren"] is True


def test_geri_al_bireysel_esik_siniri_tam_minus_3():
    s3 = ders.fren_durumu([_s_islem(1, 3.0)], [K_SEANS], FREN_BAS, FREN_SON)
    assert s3["geri_al"] == [K_SEANS]
    s29 = ders.fren_durumu([_s_islem(1, 2.9)], [K_SEANS], FREN_BAS, FREN_SON)
    assert s29["geri_al"] == []
    assert s29["fren"] is False


def test_geri_alma_parametresi():
    adaylar = [_s_islem(1, 2.0), _s_islem(2, 2.0), _s_islem(3, 2.0)]
    s = ders.fren_durumu(adaylar, [K_SEANS], FREN_BAS, FREN_SON, geri_alma_r=7.0)
    assert s["geri_al"] == []


def test_fren_sayilmayan_islemler():
    adaylar = [
        _s_islem(1, 50.0, alindi=False),          # alinmadi
        _aday(id="rnone", ts=_ts(2026, 3, 5), seans="closed", kurulum=T1,
              ozellikler={"atr_ratio": 1.0, "rr": 2.5}, r=None),  # r yok
        _aday(id="once", ts=_ts(2026, 2, 28), seans="closed", kurulum=T1,
              ozellikler={"atr_ratio": 1.0, "rr": 2.5}, r=50.0),  # pencere disi
        _aday(id="sonra", ts=_ts(2026, 4, 1), seans="closed", kurulum=T1,
              ozellikler={"atr_ratio": 1.0, "rr": 2.5}, r=50.0),  # pencere disi
    ]
    s = ders.fren_durumu(adaylar, [K_SEANS], FREN_BAS, FREN_SON)
    assert s["toplam_etki"] == pytest.approx(0.0)
    assert s["fren"] is False
    assert s["geri_al"] == []


def test_fren_bos_etkin_liste():
    s = ders.fren_durumu([_s_islem(1, 5.0)], [], FREN_BAS, FREN_SON)
    assert s["toplam_etki"] == pytest.approx(0.0)
    assert s["fren"] is False
    assert s["geri_al"] == []
