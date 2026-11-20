"""20 Kasim: her kagit kararinin features'inda tek tip "CT bilgisi" blogu (taze / bayat); karar ve boyut degismez; eski model uyumu."""
from __future__ import annotations

import dataclasses
import json
from datetime import datetime, timedelta, timezone

import pytest

from test_etiket_kurallari_gate import _go, mk  # noqa: F401,E402  (fixture + yardimci)

UTC = timezone.utc


def _taze(e, **rec):
    base = {"long": 12, "short": 3, "net_yon": "long", "net_nominal_usd": 1.0, "veri_yasi_sn": 300.0}
    e.g.ct_kadro = lambda: {"BTC/USDT": {**base, **rec}, "_uretildi": datetime(2026, 12, 1, tzinfo=UTC)}


def test_karar_features_ct_blogu_taze(mk):  # noqa: F811
    e = mk(cfg=None)
    _taze(e)
    o = _go(e, side="long")
    f = o.event.features
    assert o.action == "enter"
    assert f["ct_long"] == 12 and f["ct_short"] == 3 and f["ct_baskinlik"] == pytest.approx(0.8)
    assert f["ct_net_yon"] == "long" and f["ct_yon"] == 1 and f["ct_yas_dk"] == 5.0 and "ct_durum" not in f


def test_karar_features_ct_blogu_bayat_yalniz_durum_yok(mk):  # noqa: F811
    e = mk(cfg=None)
    e.g.ct_kadro = lambda: None                                            # oku(): bayat/yok -> None
    o = _go(e, side="long")
    f = o.event.features
    assert o.action == "enter" and f["ct_durum"] == "yok"
    assert not [k for k in f if k.startswith("ct_") and k != "ct_durum"]


def test_ct_blogu_karari_ve_boyutu_degistirmez(mk):  # noqa: F811
    a, b = mk(cfg=None), mk(cfg=None)
    _taze(b)
    oa, ob = _go(a), _go(b)
    assert (oa.action, oa.size, oa.leverage) == (ob.action, ob.size, ob.leverage)
    da, db = dataclasses.asdict(oa.event), dataclasses.asdict(ob.event)
    da.pop("features", None), db.pop("features", None)
    assert da == db


def test_atlanan_karar_da_blok_tasir(mk):  # noqa: F811
    e = mk()                                                              # etiket kurallari acik: kalabalik yonundeki giris atlanir
    _taze(e, long=1, short=19, net_yon="short")
    o = _go(e, side="short", planned_stop=102.0, regime="trend_down")
    assert o.code == "etiket_kalabalik"
    assert o.event.features["ct_yon"] == 1 and o.event.features["ct_baskinlik"] == pytest.approx(0.95)


# ----------------------------------------------------------------------------- eski model uyumu (adla eslesme)
def _aday(i, r, **oz):
    from ortak_ogrenme.kayit import Aday
    return Aday(id=str(i), proje="ML", kurulum="C1@1h", enstruman="BTC/USDT", varlik_sinifi="kripto", yon="long",
                ts=datetime(2026, 12, 1, tzinfo=UTC) + timedelta(hours=i), alindi=True, r=r, rejim="range", ozellikler=oz)


def test_eski_model_kendi_ozellik_listesiyle_puanlanir_yeni_ozellikler_yoksayilir():
    from ortak_ogrenme import filtre
    eski = [_aday(i, 1.0 if i % 2 else -1.0, atr_ratio=1.0 + i * 0.1, stop_dist_pct=0.01) for i in range(20)]
    p = filtre.egit("C1@1h", eski, olusturma=datetime(2026, 12, 2, tzinfo=UTC))
    assert p["meta"]["ozellikler"] == ["atr_ratio", "stop_dist_pct"]
    taban = {"atr_ratio": 1.3, "stop_dist_pct": 0.01}
    yeni = {**taban, "f_ct_yon": 1.0, "f_ct_baskinlik": 0.9, "f_ct_trader_sayisi": 2.7}   # canli ozellik sozlugu CT iceriyor
    assert filtre.puan(p, yeni) == pytest.approx(filtre.puan(p, taban))                   # eski model CT'yi gormez, kaymaz
    assert 0.0 <= filtre.puan(p, yeni) <= 1.0


def test_yeni_model_ct_ozelligi_eksikse_fill_ile_puanlanir():
    from ortak_ogrenme import filtre
    yeni = [_aday(i, 1.0 if i % 2 else -1.0, atr_ratio=1.0 + i * 0.1, f_ct_yon=float(i % 3 - 1), f_ct_baskinlik=0.8,
                  f_ct_trader_sayisi=2.5) for i in range(20)]
    p = filtre.egit("C1@1h", yeni, olusturma=datetime(2026, 12, 2, tzinfo=UTC))
    assert {"f_ct_yon", "f_ct_baskinlik", "f_ct_trader_sayisi"} <= set(p["meta"]["ozellikler"])
    s = filtre.puan(p, {"atr_ratio": 1.3})                                                # CT bayat/yok: eksik -> fill
    assert 0.0 <= s <= 1.0


def test_ogrenme_filtre_deposu_eski_paketi_yeni_ozelliklerle_puanlar(tmp_path):
    from ortak_ogrenme import filtre
    from trader_engine.ogrenme_filtre import FiltreDeposu, ozellikler
    eski = [_aday(i, 1.0 if i % 2 else -1.0, atr_ratio=1.0 + i * 0.1, stop_dist_pct=0.01) for i in range(20)]
    filtre.kaydet(filtre.egit("C1@1h", eski, olusturma=datetime(2026, 12, 2, tzinfo=UTC)), tmp_path)
    oz = ozellikler(side="long", regime="range", atr_ratio=1.3, session_tag=None, pair="BTC/USDT", planned_entry=100.0,
                    planned_stop=99.0, features={"ct_long": 12, "ct_short": 3, "ct_baskinlik": 0.8, "ct_yon": 1})
    assert "f_ct_trader_sayisi" in oz
    k = FiltreDeposu(tmp_path).karar("C1@1h", oz, datetime(2026, 12, 3, tzinfo=UTC))
    assert k.neden in ("ok", "esik_alti") and k.puan is not None


def test_setup_filter_eski_model_adlariyla_vektor():
    import numpy as np
    from trader_core.ml_live_v2 import setup_feature_dict, setup_feature_vector
    eski_adlar = ["atr_ratio", "rr_plan", "side_long", "f_ct_yon"]                         # CT'siz egitilmis olabilir de, f_ct_yon'lu da
    d = setup_feature_dict(side="long", regime="range", atr_ratio=1.0, session_tag=None, asset_class="kripto",
                           planned_entry=100.0, planned_stop=99.0, planned_target=102.0, features={"ct_long": 5, "ct_short": 0})
    v = setup_feature_vector(eski_adlar, d)
    assert v.shape == (4,) and np.isnan(v[3])                                              # f_ct_yon yok -> NaN (modelin fill'i)
    assert v[0] == 1.0 and v[2] == 1.0
