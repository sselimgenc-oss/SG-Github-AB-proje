"""19 Kasim: kurali olmayan cift (TON not_trading) emir yokken PaperBroker.advance'i dusurmemeli."""
from trader_engine.brokers import paper as PB


def test_fills_pair_skips_rules_without_orders(monkeypatch):
    b = PB.PaperBroker.__new__(PB.PaperBroker)
    called = []
    b._funding_step = lambda pair, bar: None
    b._new_orders = lambda: []
    b._rules_fn = lambda pair: called.append(pair) or (_ for _ in ()).throw(RuntimeError("kural yok"))
    b._last_mark = {}
    b._ctr = {"mark_fallbacks": 0}

    class Bar:
        mark_c = 1.0
        last_c = 1.0
    b._fills_pair("TON/USDT", Bar())
    assert called == [] and b._last_mark["TON/USDT"] == 1.0
