"""19 Kasim (sahip karari): kagit lab'da ML esik alti adayi ELEMEZ, yalniz `ml:below` etiketi yazar; eski strateji eler."""
from types import SimpleNamespace

import pandas as pd

from trader_engine.strategies.lab import make_lab_ml
from trader_engine.strategies.price_action_v1_ml import make_v1b_ml


def _ctx():
    model = SimpleNamespace(threshold=0.5, expired=lambda D: False)
    return SimpleNamespace(pair="BTC/USDT", model=model, D=pd.Timestamp("2026-01-01", tz="UTC"), tf="1h")


def _row():
    return pd.Series({"signal": True, "skip_reason": None, "reasons": "ml:p=0.100000|t1"})


def _run(ml, monkeypatch):
    ml.set_ml_mode("active")
    monkeypatch.setattr(ml._inner, "post_filter", lambda row, ctx: row)
    return ml.post_filter(_row(), _ctx())


def test_lab_ml_scores_but_never_blocks(monkeypatch):
    ml = make_lab_ml()._ml
    assert ml.ml_block is False
    out = _run(ml, monkeypatch)
    assert bool(out["signal"]) is True and out["skip_reason"] is None
    assert str(out["reasons"]).startswith("ml:below|")
    assert ml.counters["ml_below_noblock"] == 1


def test_legacy_v1_ml_still_filters(monkeypatch):
    ml = make_v1b_ml()
    assert ml.ml_block is True
    out = _run(ml, monkeypatch)
    assert bool(out["signal"]) is False and out["skip_reason"] == "ml_filter"
