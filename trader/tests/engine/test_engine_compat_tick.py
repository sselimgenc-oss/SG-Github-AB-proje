"""03 §4.5(ii): legacy_compat tarihsel aylik tick (freqtrade get_tick_size_over_time) — turetme, giris-ayi kilidi, yedek, native."""
from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timedelta, timezone

import numpy as np
import pytest

from tests.engine import test_engine_03_impl_smoke as T3  # noqa: F401  (yardimcilar yeniden kullanilir)
from trader_engine.brokers.paper import PaperBroker, PaperConfig
from trader_engine.clock import SimClock
from trader_engine.config import CostModel
from trader_engine.marketdata.sources import decimals_of, monthly_ticks
from trader_engine.numeric import round_nearest

UTC = timezone.utc
P = T3.P


def ms(y, m, d=1, h=0):
    return int(datetime(y, m, d, h, tzinfo=UTC).timestamp() * 1000)


def test_decimals_float_repr_robust():
    assert decimals_of([100.0, 101.5, 99.25]) == 2
    assert decimals_of([0.1 + 0.2]) == 1                    # 0.30000000000000004 -> 10 ondalik yuvarlama -> 0.3
    assert decimals_of([186.74, 186.741]) == 3
    assert decimals_of([1e-05]) == 5
    assert decimals_of([100.0, 2.0]) == 0                   # sondaki sifirlar sayilmaz
    assert decimals_of([]) == 0


def test_monthly_ticks_per_month_max_over_ohlc():
    t = np.array([ms(2025, 1, 1, 0), ms(2025, 1, 1, 1), ms(2025, 2, 1, 0), ms(2025, 2, 1, 1)])
    o = np.array([100.01, 100.02, 100.02, 100.03])
    h = np.array([100.05, 100.123, 100.05, 100.05])         # Ocak'ta tek 3 haneli mum
    l = np.array([99.9, 99.9, 99.9, 99.9])
    c = np.array([100.0, 100.0, 100.0, 100.0])
    tk = monthly_ticks(t, o, h, l, c)
    assert tk[(2025, 1)] == pytest.approx(0.001)
    assert tk[(2025, 2)] == pytest.approx(0.01)
    assert (2025, 3) not in tk
    assert monthly_ticks(np.array([], dtype="int64"), *(np.array([]),) * 4) == {}


def test_tick_at_fallback_to_rules(tmp_path):
    from trader_engine.marketdata.sources import HistoricalSource
    h = HistoricalSource(tmp_path)
    t = np.array([ms(2025, 1, 1)])
    h._tick_tab["BTC/USDT"] = monthly_ticks(t, np.array([1.123]), np.array([1.123]), np.array([1.123]), np.array([1.123]))
    h._rules_json = {}
    h.rules = lambda p: T3.RULES                               # type: ignore[method-assign]
    assert h.tick_at("BTC/USDT", datetime(2025, 1, 20, tzinfo=UTC)) == pytest.approx(0.001)
    assert h.tick_at("BTC/USDT", datetime(2025, 3, 5, tzinfo=UTC)) == T3.RULES.tick   # ayda veri yok -> yedek


def _broker(legacy: bool, tick_fn):
    cost = (CostModel(fill_model="legacy_compat", trigger_source="last", granularity="15m", taker_fee=0.0005) if legacy
            else CostModel())
    clock = SimClock(T3.T0)
    return PaperBroker(PaperConfig(cost=cost, mmr=0.004), lambda p: T3.RULES, lambda p, a, z: [], clock, None,
                       tick_fn=tick_fn)


def test_round_nearest():
    assert round_nearest(186.7414, 0.001) == 186.741
    assert round_nearest(186.7416, 0.001) == 186.742
    assert round_nearest(100.005, 0.01) == 100.01            # yarim yukari


def test_entry_month_tick_locked_for_lifetime():
    seen = []

    def tick_fn(pair, ts):
        seen.append(ts)
        return 0.001 if ts.month == 12 else 0.1               # giris ayi (T0 = 2026-12) 0.001; baska ay 0.1

    b = _broker(True, tick_fn)
    b.prepare(P, 3)
    b.market_order(T3.req("e1", "entry", "buy", 6.369))
    ev = T3.step(b, {P: T3.bar(0, o=100.1234)})
    assert ev[0].fill.price == 100.123                        # giris dolumu: giris ayi tick'ine en yakin
    # pozisyon aylar sonra kapanir: cikis yine GIRIS ayi tick'i ile (ay degisse de)
    late = T3.T0 + timedelta(days=40)
    b.market_order(T3.req("x1", "exit", "sell", 6.369))
    bar2 = T3.bar(0, o=105.0567)
    bar2 = replace(bar2, open_ts=late)
    b.advance({P: bar2}, "fills")
    fills = [e for e in b.poll(late) if e.fill]
    assert fills[0].fill.price == 105.057
    assert all(s == T3.T0 for s in seen)                      # tick hep girisin ts'sinden sorgulandi


def test_stop_fill_rounds_on_entry_tick():
    b = _broker(True, lambda p, ts: 0.001)
    b.prepare(P, 3)
    b.market_order(T3.req("e1", "entry", "buy", 6.369))
    T3.step(b, {P: T3.bar(0)})
    b.place_stop(T3.req("s1", "stop", "sell", 6.369, 98.0))
    ev = T3.step(b, {P: T3.bar(1, o=97.9996, lo=97.5, h=99, c=98)})      # acilis stopun altinda: gap dolumu
    assert ev[0].fill.price == 98.0


def test_native_mode_unaffected_by_tick_fn():
    called = []
    b = _broker(False, lambda p, ts: called.append(ts) or 0.001)
    b.prepare(P, 3)
    b.market_order(T3.req("e1", "entry", "buy", 6.369))
    ev = T3.step(b, {P: T3.bar(0, o=100.1234)})
    assert called == []
    assert ev[0].fill.price == 100.15                         # native: 2 bps kayma + borsa tick'i (0.01) ceil; tick_fn yok sayilir


def test_legacy_without_tick_fn_keeps_unrounded():
    b = _broker(True, None)
    b.prepare(P, 3)
    b.market_order(T3.req("e1", "entry", "buy", 6.369))
    ev = T3.step(b, {P: T3.bar(0, o=100.1234)})
    assert ev[0].fill.price == 100.1234
