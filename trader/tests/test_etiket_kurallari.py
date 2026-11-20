"""Etiket kurallari (docs/etiket-kurallari-spec.md): saf mantik, yapilandirma, otomatik kapat/izle/yeniden ac (histerezis), panel karti, ceviriler."""
from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace

import pytest

from trader_core import etiket_kurallari as EK
from trader_core import panel_pano as PP
from trader_core import telegram as TG
from trader_core import alinmayan_sonuc as AS
from trader_engine.config import ConfigError, load_cli_config

ROOT = Path(__file__).resolve().parents[1]
CFG = EK.build_config({"rejim": {}, "duygu": {}})
NOW = datetime(2026, 11, 20, 12, 0, tzinfo=timezone.utc)


# ---------------------------------------------------------------- kural mantigi
def test_rejim_karsiti_engeller_ve_izin_verir():
    assert EK.degerlendir("long", "trend_down", None, {"rejim": {"acik": True}})[0][0][0] == EK.REJIM
    assert EK.degerlendir("short", "trend_up", None, {"rejim": {"acik": True}})[0][0][0] == EK.REJIM
    for side, reg in (("long", "trend_up"), ("short", "trend_down"), ("long", "range"), ("short", "volatile"), ("long", "unclear")):
        assert EK.degerlendir(side, reg, None, {"rejim": {"acik": True}})[0] == []


def test_duygu_asiri_ters_yon():
    tet, yok = EK.degerlendir("long", "range", {"deger": 12, "sinif": "Extreme Fear"}, CFG)
    assert [k for k, _ in tet] == [EK.DUYGU] and EK.DUYGU not in yok
    assert [k for k, _ in EK.degerlendir("short", "range", {"deger": 85, "sinif": "Extreme Greed"}, CFG)[0]] == [EK.DUYGU]
    assert EK.degerlendir("short", "range", {"deger": 12}, CFG)[0] == []          # asiri korku + short = serbest
    assert EK.degerlendir("long", "range", {"deger": 85}, CFG)[0] == []          # asiri acgozluluk + long = serbest
    assert EK.degerlendir("long", "range", {"deger": 50}, CFG)[0] == []


def test_kalabalik_kurali_kaldirildi():
    """CT/ML ayriligi: kalabalik kurali yok (kural listesi, varsayilan config, dogrulama); eski anahtar reddedilir."""
    assert not hasattr(EK, "KALABALIK") and EK.KURALLAR == (EK.REJIM, EK.DUYGU)
    assert "kalabalik" not in EK.VARSAYILAN and "kalabalik" not in EK.build_config({"rejim": {}})
    with pytest.raises(EK.EtiketConfigHatasi):
        EK.build_config({"kalabalik": {"acik": True}})
    # CT verisi parametre olarak bile alinmaz: motor/ML hicbir CT girdisi gormez
    with pytest.raises(TypeError):
        EK.degerlendir("long", "range", None, {"long": 18, "short": 2, "net_yon": "long"}, CFG, 1)


def test_veri_yok_fail_open_ve_kaydedilir():
    tet, yok = EK.degerlendir("long", None, None, CFG)
    assert tet == [] and set(yok) == {EK.REJIM, EK.DUYGU}
    tet, yok = EK.degerlendir("long", "range", {"deger": "x"}, CFG)
    assert tet == [] and EK.DUYGU in yok


def test_kapali_config_hic_degerlendirmez():
    assert EK.degerlendir("long", "trend_down", {"deger": 1}, {}) == ([], [])
    c = EK.build_config({"rejim": {"acik": False}, "duygu": {"acik": False}})
    assert EK.degerlendir("long", "trend_down", {"deger": 1}, c) == ([], [])


# ---------------------------------------------------------------- yapilandirma
def test_build_config_dogrulama():
    assert EK.build_config(None) == {} and EK.build_config({}) == {}
    for bad in ({"x": {}}, {"duygu": {"asiri_korku_max": 90}}, {"otomatik": {"ac_esik_r": 1}},
                {"rejim": {"acik": "evet"}}, {"duygu": {"yok": 1}}, [1]):
        with pytest.raises(EK.EtiketConfigHatasi):
            EK.build_config(bad)


def _cfg_dosya(tmp_path, mode, ek):
    base = json.loads((ROOT / "config" / f"engine.{mode}.json").read_text())
    base["etiket_kurallari"] = ek
    d = tmp_path / "config"
    d.mkdir(exist_ok=True)
    for f in (ROOT / "config").glob("*.json"):
        (d / f.name).write_text(f.read_text())
    (d / f"engine.{mode}.json").write_text(json.dumps(base))
    return d


def test_paper_config_etiket_kurallari_yuklenir():
    c = load_cli_config(ROOT / "config", "learner", "paper")
    assert c.etiket_kurallari["rejim"]["acik"] is True and c.etiket_kurallari["otomatik"]["pencere"] == 10


@pytest.mark.parametrize("mode", ["live", "testnet"])
def test_live_testnet_etiket_kurallari_yok_ve_yasak(tmp_path, mode):
    c = load_cli_config(ROOT / "config", "learner", mode)
    assert not c.etiket_kurallari                                    # base/live/testnet: bos
    d = _cfg_dosya(tmp_path, mode, {"rejim": {"acik": True}})
    with pytest.raises(ConfigError, match="etiket_kurallari"):
        load_cli_config(d, "learner", mode)


def test_paper_gecersiz_esik_reddedilir(tmp_path):
    d = _cfg_dosya(tmp_path, "paper", {"duygu": {"asiri_korku_max": 99}})
    with pytest.raises(ConfigError):
        load_cli_config(d, "learner", "paper")


# ---------------------------------------------------------------- otomatik kapat -> izle -> yeniden ac (histerezis)
def _cf(kod, rs, t0):
    return [{"skip_reason": kod, "ts": t0 + timedelta(hours=i), "r": r} for i, r in enumerate(rs)]


def _gercek(kod, rs, t0):
    return [{"kural": kod, "ts": t0 + timedelta(hours=i), "r": r} for i, r in enumerate(rs)]


def test_kapat_izle_yeniden_ac_ve_histerezis():
    t0 = NOW - timedelta(days=10)
    d = EK.bos_durum()
    # 9 sonuc: yetersiz; +1R esigi asilsa da kapanmaz
    d, ol = EK.guncelle(d, _cf(EK.REJIM, [0.5] * 9, t0), [], CFG, NOW)
    assert ol == [] and d["kurallar"][EK.REJIM]["acik"] is True
    # 10 sonuc, toplam tam +1R: esik asilmadi (> +1R gerekir)
    d, ol = EK.guncelle(d, _cf(EK.REJIM, [0.1] * 10, t0), [], CFG, NOW)
    assert ol == []
    # 10 sonuc, toplam +2R: kapanir
    d, ol = EK.guncelle(d, _cf(EK.REJIM, [0.2] * 10, t0), [], CFG, NOW)
    assert [e["olay"] for e in ol] == ["kapandi"] and d["kurallar"][EK.REJIM]["acik"] is False
    assert ol[0]["n"] == 10 and ol[0]["toplam_r"] == 2.0
    assert d["kurallar"][EK.DUYGU]["acik"] is True
    assert EK.olay_satiri(ol[0]) == "Etiket kuralı kapatıldı: rejim karşıtı (atladığı işlemler kâr ederdi)"
    assert EK.durum_etiketi(d["kurallar"][EK.REJIM]) == "Kanıta göre kapandı (20.11.2026)"
    # kapaliyken: eski kanit (olaydan once) yeniden acmaz; -0.5R gibi ara deger histerezis bandinda kalir
    t1 = NOW + timedelta(days=1)
    simdi2 = NOW + timedelta(days=5)
    d2, ol = EK.guncelle(d, [], _gercek(EK.REJIM, [-0.05] * 10, NOW - timedelta(days=3)), CFG, simdi2)
    assert ol == [] and d2["kurallar"][EK.REJIM]["acik"] is False
    d2, ol = EK.guncelle(d, [], _gercek(EK.REJIM, [-0.05] * 10, t1), CFG, simdi2)          # toplam -0.5R: bant icinde, acilmaz
    assert ol == []
    d2, ol = EK.guncelle(d, [], _gercek(EK.REJIM, [-0.2] * 10, t1), CFG, simdi2)           # toplam -2R < -1R: yeniden acilir
    assert [e["olay"] for e in ol] == ["acildi"] and d2["kurallar"][EK.REJIM]["acik"] is True
    assert EK.olay_satiri(ol[0]) == "Etiket kuralı yeniden açıldı: rejim karşıtı (atlamak kazandırırdı)"
    assert EK.durum_etiketi(d2["kurallar"][EK.REJIM]).startswith("Kanıta göre yeniden açıldı (")
    assert [g["olay"] for g in d2["kurallar"][EK.REJIM]["gecmis"]] == ["kapandi", "acildi"]
    # yeniden acildiktan sonra ayni eski kanit tekrar kapatmaz (yalniz olaydan sonraki sonuclar sayilir)
    d3, ol = EK.guncelle(d2, _cf(EK.REJIM, [0.2] * 10, t0), [], CFG, simdi2 + timedelta(days=1))
    assert ol == [] and d3["kurallar"][EK.REJIM]["acik"] is True


def test_config_kapali_kural_degismez_ve_cfg_yok():
    t0 = NOW - timedelta(days=10)
    c = EK.build_config({"rejim": {"acik": False}})
    d, ol = EK.guncelle(EK.bos_durum(), _cf(EK.REJIM, [0.5] * 10, t0), [], c, NOW)
    assert ol == [] and d["kurallar"][EK.REJIM]["acik"] is True
    d, ol = EK.guncelle(EK.bos_durum(), _cf(EK.REJIM, [0.5] * 10, t0), [], None, NOW)
    assert ol == []


def test_durum_dosyasi_yaz_oku_ve_bozuk(tmp_path):
    p = tmp_path / "d" / EK.DOSYA
    assert EK.acik_haritasi(EK.durum_oku(p)) == {k: True for k in EK.KURALLAR}           # yok -> hepsi acik
    d, _ = EK.guncelle(EK.bos_durum(), _cf(EK.DUYGU, [0.5] * 10, NOW - timedelta(days=5)), [], CFG, NOW)
    EK.yaz_atomik(p, d)
    assert EK.acik_haritasi(EK.durum_oku(p)) == {EK.REJIM: True, EK.DUYGU: False}
    p.write_text("{bozuk")
    assert EK.acik_haritasi(EK.durum_oku(p)) == {k: True for k in EK.KURALLAR}


def test_gercek_satirlari_kapali_kuralin_atlayacagi_islemler():
    dec = [SimpleNamespace(id=1, final_action="entered", features={EK.FEATURE_ANAHTAR: "etiket_rejim,etiket_duygu"}),
           SimpleNamespace(id=2, final_action="entered", features={}),
           SimpleNamespace(id=3, final_action="skipped", features={EK.FEATURE_ANAHTAR: "etiket_rejim"})]
    tr = [SimpleNamespace(decision_id=1, exit_ts=NOW, r_multiple=-1.0), SimpleNamespace(decision_id=2, exit_ts=NOW, r_multiple=2.0),
          SimpleNamespace(decision_id=3, exit_ts=NOW, r_multiple=1.0)]
    out = EK.gercek_satirlari(dec, tr)
    assert sorted(o["kural"] for o in out) == [EK.DUYGU, EK.REJIM] and all(o["r"] == -1.0 for o in out)


# ---------------------------------------------------------------- panel karti
def _al(rows, coz):
    return {"sema": AS.SEMA, "tablolar": {"neden": rows}, "cozulmedi": {"tablolar": coz}}


def test_kart_verisi_ve_gizleme():
    assert EK.kart_verisi(EK.bos_durum(), False, None) is None                       # veri yok: kart gizli
    al = _al([{"etiket": "etiket_rejim", "n": 4, "toplam_pnl": -1.5}, {"etiket": "ml_filter", "n": 9, "toplam_pnl": 3.0}], {"etiket_rejim": 2})
    d, _ = EK.guncelle(EK.bos_durum(), _cf(EK.DUYGU, [0.5] * 10, NOW - timedelta(days=5)), [], CFG, NOW)
    k = EK.kart_verisi(d, True, al)
    r = {x["kural"]: x for x in k["kurallar"]}
    assert r[EK.REJIM]["atlanan_7g"] == 6 and r[EK.REJIM]["alinsaydi_r"] == -1.5 and r[EK.REJIM]["acik"] is True
    assert r[EK.DUYGU]["acik"] is False and r[EK.DUYGU]["durum"].startswith("Kanıta göre kapandı")
    assert EK.REJIM in r and "etiket_kalabalik" not in r


def test_panel_etiket_view_dosyalardan(tmp_path):
    dy, ay = tmp_path / "d.json", tmp_path / "a.json"
    assert PP.etiket_view(str(dy), str(ay)) is None
    ay.write_text(json.dumps(_al([{"etiket": "etiket_duygu", "n": 3, "toplam_pnl": 0.8}], {})))
    v = PP.etiket_view(str(dy), str(ay))
    r = {x["kural"]: x for x in v["kurallar"]}
    assert r[EK.DUYGU]["sonuc"] == {"r": 0.8, "n": 3} and r[EK.DUYGU]["renk"] == "yesil"
    assert r[EK.REJIM]["sonuc"] == {"olculemedi": "Henüz ölçülemedi"}


# ---------------------------------------------------------------- ceviriler / satirlar
def test_turkce_cevirileri():
    for kod in EK.KURALLAR:
        assert kod in TG.ATLAMA_TR and TG.ATLAMA_TR[kod]
        assert kod in AS.NEDEN_SIRA
    st = {"counters": {"steps": 5, "decisions": 3, "enter": 1, "skip:etiket_rejim": 2}, "loop_at": "2026-11-20T12:00:00Z",
          "etiket_kurallari": {"kurallar": {EK.DUYGU: {"son_olay": {"ts": "2026-11-20T03:00:00Z", "olay": "kapandi"}},
                                             EK.REJIM: {"son_olay": None}}}}
    satirlar = TG._aktivite_satirlari(st)
    assert any("rejim etiketi ters yöndeydi" in s for s in satirlar)
    assert satirlar[-1].endswith("Etiket kuralı kapatıldı: uç duygu karşıtı (atladığı işlemler kâr ederdi)")
    st["loop_at"] = "2026-11-25T12:00:00Z"                                              # eski olay tekrarlanmaz
    assert not any("Etiket kuralı" in s for s in TG._aktivite_satirlari(st))


def test_yaz_gece_durum_dosyasi_ve_olay(tmp_path, monkeypatch):
    from trader_core import ledger as L
    led = tmp_path / "var" / "learner" / "ledger.sqlite"
    led.parent.mkdir(parents=True)
    L.open_ledger(str(led), "learner", create=True).close()
    monkeypatch.setattr(AS, "_cf_satirlari", lambda yol, bot: _cf(EK.DUYGU, [0.3] * 10, NOW - timedelta(days=4)))
    dy = tmp_path / "var" / "durum" / EK.DOSYA
    ol = EK.yaz_gece(led, tmp_path / "cf.sqlite", "learner", NOW, dy, {"duygu": {"acik": True}})
    assert [(e["kural"], e["olay"]) for e in ol] == [(EK.DUYGU, "kapandi")]
    assert EK.acik_haritasi(EK.durum_oku(dy))[EK.DUYGU] is False
    assert EK.yaz_gece(led, tmp_path / "cf.sqlite", "learner", NOW, dy, {}) is None            # yapilandirma yok: dokunmaz
    assert EK.yaz_gece(tmp_path / "yok.sqlite", tmp_path / "cf.sqlite", "learner", NOW, dy, {"rejim": {}}) is None   # hata yutulur


# ---------------------------------------------------------------- CT/ML ayriligi: ML ozellikleri
def test_ml_ozellik_sozlugu_ct_alanlarini_yok_sayar_ve_eski_paket_puanlanir():
    import numpy as np

    from trader_core import ml_live_v2 as M
    feats = {"rr": 2.0, "ct_long": 12, "ct_short": 3, "ct_baskinlik": 0.8, "ct_yon": 1, "ct_yas_dk": 2.0, "atr_1h": 5.0}
    d = M.setup_feature_dict(side="long", regime="trend_up", atr_ratio=1.0, session_tag=None, asset_class="kripto", pair="BTC/USDT",
                             planned_entry=100.0, planned_stop=98.0, features=feats)
    assert d["f_rr"] == 2.0 and d["f_atr_1h"] == 5.0
    assert not any(k.startswith("f_ct_") for k in d)                      # CT alanlari ne egitime ne puanlamaya girer
    # eski paket (f_ct_* bekliyor): eksik ozellik NaN -> modelin fill degeri; vektor hata vermez, giris engellenmez
    v = M.setup_feature_vector(["f_rr", "f_ct_yon", "f_ct_trader_sayisi"], d)
    assert v[0] == 2.0 and np.isnan(v[1]) and np.isnan(v[2])
