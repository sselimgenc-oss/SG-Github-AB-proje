"""19 Kasim: CT yon etiketi (features["ct_yon"]) yalniz kayit; hicbir adayi engellemez."""
import pytest

from trader_engine.gates import EntryGate


def _g(kadro):
    g = EntryGate.__new__(EntryGate)
    g.ct_kadro = (lambda: kadro) if kadro is not ... else None
    return g


def test_ct_yon_values():
    k = {"BTC/USDT": {"net_yon": "long"}, "ETH/USDT": {"net_yon": "notr"}}
    g = _g(k)
    assert g._ct_yon("BTC/USDT", "long") == 1
    assert g._ct_yon("BTC/USDT", "short") == -1
    assert g._ct_yon("ETH/USDT", "long") == 0
    assert g._ct_yon("SOL/USDT", "long") == 0


def test_ct_yon_none_when_no_data_or_error():
    assert _g(None)._ct_yon("BTC/USDT", "long") is None
    assert _g(...)._ct_yon("BTC/USDT", "long") is None
    g = EntryGate.__new__(EntryGate)
    g.ct_kadro = lambda: (_ for _ in ()).throw(OSError("x"))
    assert g._ct_yon("BTC/USDT", "long") is None
    assert _g({"BTC/USDT": {"net_yon": "long"}})._ct_yon("BTC/USDT", None) is None


def test_ml_feature_dict_picks_up_ct_yon():
    from trader_core.ml_live_v2 import setup_feature_dict
    d = setup_feature_dict(side="long", regime="range", atr_ratio=1.0, session_tag=None, asset_class="kripto",
                           planned_entry=100.0, planned_stop=99.0, features={"ct_yon": -1})
    assert d["f_ct_yon"] == -1.0


# ----------------------------------------------------------------------------- 20 Kasim: tek tip "CT bilgisi" blogu
def test_ct_blok_taze_veri_tum_anahtarlar():
    k = {"BTC/USDT": {"long": 12, "short": 3, "net_yon": "long", "net_nominal_usd": 5.0, "veri_yasi_sn": 600.0}}
    b = _g(k)._ct_blok("BTC/USDT", "long")
    assert b == {"ct_long": 12, "ct_short": 3, "ct_baskinlik": 0.8, "ct_net_yon": "long", "ct_yon": 1, "ct_yas_dk": 10.0}
    assert _g(k)._ct_blok("BTC/USDT", "short")["ct_yon"] == -1
    n = _g({"BTC/USDT": {"long": 2, "short": 2, "net_yon": "notr", "veri_yasi_sn": 60.0}})._ct_blok("BTC/USDT", "long")
    assert n["ct_yon"] == 0 and n["ct_net_yon"] == "notr" and n["ct_baskinlik"] == 0.5


def test_ct_blok_bayat_ya_da_hata_yalniz_ct_durum_yok():
    assert _g({})._ct_blok("BTC/USDT", "long") == {"ct_durum": "yok"}     # oku() bayatta None verir; bos harita da "yok"
    assert _g(None)._ct_blok("BTC/USDT", "long") == {"ct_durum": "yok"}
    assert _g(...)._ct_blok("BTC/USDT", "long") == {}                       # CT hic baglanmamis (kagit disi): hicbir sey yazilmaz
    g = EntryGate.__new__(EntryGate)
    g.ct_kadro = lambda: (_ for _ in ()).throw(OSError("x"))
    assert g._ct_blok("BTC/USDT", "long") == {}                             # hata: karar etkilenmez
    assert _g({"BTC/USDT": {"net_yon": "long"}})._ct_blok("BTC/USDT", None) == {}


def test_ct_blok_cift_dosyada_yoksa_sifir_sayim_notr():
    from datetime import datetime, timedelta, timezone
    from types import SimpleNamespace
    simdi = datetime(2026, 11, 20, 12, 0, tzinfo=timezone.utc)
    g = _g({"ETH/USDT": {"long": 5, "short": 0, "net_yon": "long", "veri_yasi_sn": 30.0}, "_uretildi": simdi - timedelta(minutes=7)})
    g.clock = SimpleNamespace(now=lambda: simdi)
    b = g._ct_blok("BTC/USDT", "long")
    assert b["ct_yon"] == 0 and b["ct_long"] == 0 and b["ct_short"] == 0 and b["ct_yas_dk"] == 7.0


def test_ml_trader_sayisi_log1p_ve_eksikse_yok():
    import math
    from trader_core.ml_live_v2 import setup_feature_dict
    kw = dict(side="long", regime="range", atr_ratio=1.0, session_tag=None, asset_class="kripto", planned_entry=100.0, planned_stop=99.0)
    d = setup_feature_dict(**kw, features={"ct_long": 12, "ct_short": 3, "ct_baskinlik": 0.8, "ct_yon": 1})
    assert d["f_ct_trader_sayisi"] == pytest.approx(math.log1p(15)) and d["f_ct_baskinlik"] == 0.8 and d["f_ct_yon"] == 1.0
    d = setup_feature_dict(**kw, features={})
    assert not any(k.startswith("f_ct_") for k in d)                         # CT yok: uc ozellik de yok (NaN/fill)
    d = setup_feature_dict(**kw, features={"ct_durum": "yok"})                # metin sayisal ozellik olamaz
    assert not any(k.startswith("f_ct_") for k in d)
