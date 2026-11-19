"""docs/cikis-karsi-olgu-spec.md 9 test 2 (motor paritesi, motorun ice aktarilabildigi test): ATR ve hizalanmis rejim dizileri,
motorun strateji tablosuyla (`PriceActionV1.compute`) AYNI pencerede esit; kopya sabitler motorunkine esit."""
from __future__ import annotations

import math
from datetime import datetime, timezone

import numpy as np
import pandas as pd

from exit_cf_support import HR
from trader_core import exit_counterfactual as EC
from trader_core import signals as S
from trader_engine import funding as F
from trader_engine import holdout as H
from trader_engine.bars import STARTUP_BARS_4H
from trader_engine.marketdata import store as MS
from trader_engine.strategies.base import StrategyContext
from trader_engine.strategies.registry import get_strategy

START = EC.to_ms(datetime(2025, 1, 1, tzinfo=timezone.utc))


def _walk(n, step_ms, seed):
    rng = np.random.default_rng(seed)
    c = 100.0 + np.cumsum(rng.normal(0, 0.4, n))
    rows = []
    prev = 100.0
    for i in range(n):
        o = prev
        cl = float(c[i])
        hi, lo = max(o, cl) + abs(rng.normal(0, 0.2)), min(o, cl) - abs(rng.normal(0, 0.2))
        rows.append((START + i * step_ms, o, hi, lo, cl))
        prev = cl
    return rows


def test_atr_and_regime_equal_engine_table():
    h1_rows = _walk(1500, HR, 1)
    h4_rows = _walk(400, EC.H4_MS, 2)
    ser = EC.prepare_h1(h1_rows, h4_rows)
    st = get_strategy("price_action_v1")
    cols = ["open", "high", "low", "close"]

    def frame(rows):
        return pd.DataFrame([r[1:] for r in rows], index=pd.to_datetime([r[0] for r in rows], unit="ms", utc=True), columns=cols)
    params = {k: getattr(S.DEFAULT_SIGNAL_PARAMS, k) for k in ("range_width_atr", "vol_ratio_max", "edge_zone_atr", "pullback_ema",
                                                               "stop_buffer_atr", "trail_atr", "range_target_frac", "rr_min", "trigger_tf")}
    ctx = StrategyContext(pair="BTC/USDT", D=datetime(2025, 4, 1, tzinfo=timezone.utc), tf="1h", params=params,
                          bars={"1h": frame(h1_rows), "4h": frame(h4_rows)})
    tab = st.compute(ctx)
    a_eng, a_ours = tab["atr_tf"].to_numpy(), np.asarray(ser.atr)
    ok = np.isfinite(a_eng)
    assert ok.sum() > 1000 and np.array_equal(np.isfinite(a_ours), ok) and np.array_equal(a_eng[ok], a_ours[ok])
    assert list(tab["regime"]) == ser.regime
    assert len(set(ser.regime)) > 1                                        # sentetik yol birden cok rejim uretir (anlamli test)


def test_copied_constants_equal_engine():
    assert (EC.HOLDOUT_START, EC.HOLDOUT_END) == H.HOLDOUT                  # CLI ayrica HOLDOUT'u enjekte eder
    assert EC.MARKET_SCHEMA_VERSION == MS.SCHEMA_VERSION
    assert EC.WARMUP_DAYS * 6 == STARTUP_BARS_4H                             # 50 gun x 6 (4h mum) = motorun baslangic penceresi
    assert S.TRAIL_START_R == 1.0 and EC.EPS == S.EPS


def test_funding_copies_equal_engine_functions():
    from trader_engine.types import FundingPoint
    entry = EC.to_ms(datetime(2025, 1, 2, 3, 20, tzinfo=timezone.utc))
    exit_ = entry + 41 * HR
    eng = F.due_funding_times(EC.from_ms(entry), EC.from_ms(exit_))
    assert [EC.to_ms(t) for t in eng] == EC.funding_grid_times(entry, exit_)
    pts = [FundingPoint("BTC/USDT", t, 0.0002, 101.0) for t in eng]
    for side in ("long", "short"):
        tot, n = F.accrue(EC.from_ms(entry), pts, side, 1.5, 100.0)
        mine = EC._funding_fn([(EC.to_ms(p.ts), p.rate, p.mark) for p in pts], 0, side, 1.5, 100.0)(entry, exit_)[0]
        assert math.isclose(tot, mine) and n == len(eng)
        assert math.isclose(F.funding_payment(side, 1.5, 101.0, 0.0002), EC.funding_payment(side, 1.5, 101.0, 0.0002))
