"""19 Kasim: CT yon etiketi (features["ct_yon"]) yalniz kayit; hicbir adayi engellemez."""
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
