"""07 §4.3 test senaryoları (1l3a test_kural_cikar_ve_yuvarlama karşılığı + bizim ekler)."""
import copy
import json
from decimal import Decimal as D
from pathlib import Path

import pytest

from trader_engine.exchange import rules as R

FIX = Path(__file__).parent / "fixtures" / "binance" / "exchange_info_sample.json"


@pytest.fixture
def info():
    return json.loads(FIX.read_text())


def _sym(info, name):
    return next(s for s in info["symbols"] if s["symbol"] == name)


def test_extract_and_rounding(info):
    k = R.extract_rules(info, "BTCUSDT")
    assert (k.tick, k.step, k.market_step, k.min_notional, k.market_max) == (D("0.10"), D("0.001"), D("0.01"), D("100"), D("100"))
    assert R.round_market_qty(D("0.0199"), k) == D("0.01")
    assert R.round_market_qty(D("500"), k) == D("100")
    assert R.round_stop_tight(D("49000.07"), 1, k) == D("49000.1")
    assert R.round_stop_tight(D("51000.07"), -1, k) == D("51000.0")
    assert R.round_target_easy(D("52000.07"), 1, k) == D("52000.0")
    assert R.round_target_easy(D("52000.07"), -1, k) == D("52000.1")


def test_unknown_symbol(info):
    with pytest.raises(R.RulesError):
        R.extract_rules(info, "XXXUSDT")


def test_market_lot_falls_back_to_lot_size(info):
    k = R.extract_rules(info, "ETHUSDT")
    assert k.market_step == k.step == D("0.001") and k.market_max == D("10000")
    assert k.min_notional == D("20")  # NOTIONAL.minNotional


def test_zero_step_is_error(info):
    f = next(x for x in _sym(info, "BTCUSDT")["filters"] if x["filterType"] == "LOT_SIZE")
    f["stepSize"] = "0"
    for x in _sym(info, "BTCUSDT")["filters"]:
        if x["filterType"] == "MARKET_LOT_SIZE":
            x["stepSize"] = "0"
    with pytest.raises(R.RulesError):
        R.extract_rules(info, "BTCUSDT")


def test_missing_min_notional_is_error_not_default_5(info):
    s = _sym(info, "BTCUSDT")
    s["filters"] = [x for x in s["filters"] if x["filterType"] != "MIN_NOTIONAL"]
    with pytest.raises(R.RulesError, match="min_notional_missing"):
        R.extract_rules(info, "BTCUSDT")


@pytest.mark.parametrize("field,val", [("status", "BREAK"), ("contractType", "CURRENT_QUARTER")])
def test_not_trading(info, field, val):
    _sym(info, "BTCUSDT")[field] = val
    with pytest.raises(R.RulesError, match="not_trading"):
        R.extract_rules(info, "BTCUSDT")


def test_missing_price_filter(info):
    s = _sym(info, "BTCUSDT")
    s["filters"] = [x for x in s["filters"] if x["filterType"] != "PRICE_FILTER"]
    with pytest.raises(R.RulesError):
        R.extract_rules(info, "BTCUSDT")


def test_extract_all_isolates_failures(info):
    bad = copy.deepcopy(info)
    _sym(bad, "ETHUSDT")["status"] = "BREAK"
    out = R.extract_all_rules(bad, ["BTCUSDT", "ETHUSDT", "NOPE"])
    assert isinstance(out["BTCUSDT"], R.SymbolRuleSpec)
    assert isinstance(out["ETHUSDT"], R.RulesError) and isinstance(out["NOPE"], R.RulesError)


def test_json_roundtrip(info):
    k = R.extract_rules(info, "BTCUSDT")
    assert R.spec_from_json(R.spec_to_json(k)) == k
    with pytest.raises(R.RulesError):
        R.spec_from_json("{}")


def test_to_symbol_rules_float_mapping(info):
    k = R.extract_rules(info, "BTCUSDT")
    r = R.to_symbol_rules("BTC/USDT", k)
    assert (r.pair, r.symbol, r.tick, r.step, r.min_qty, r.max_qty, r.min_notional) == \
           ("BTC/USDT", "BTCUSDT", 0.1, 0.01, 0.01, 100.0, 100.0)


def test_floor_ceil():
    assert R.floor_to_step(D("1.29"), D("0.1")) == D("1.2")
    assert R.ceil_to_step(D("1.21"), D("0.1")) == D("1.3")


def test_equals_numeric_round_tight(info):
    """Decimal (rules) ve float (numeric.round_tight) aynı tick'te aynı sonucu verir (risk 7)."""
    from trader_engine import numeric
    k = R.extract_rules(info, "BTCUSDT")
    for px in ("49000.07", "49000.10", "49000.01", "51000.07", "0.30000000000000004"):
        assert float(R.round_stop_tight(D(px), 1, k)) == numeric.round_tight(float(px), "long", 0.1)
        assert float(R.round_stop_tight(D(px), -1, k)) == numeric.round_tight(float(px), "short", 0.1)
