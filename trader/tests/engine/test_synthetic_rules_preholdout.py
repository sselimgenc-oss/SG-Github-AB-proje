"""Sentetik borsa kurallari yalniz kilitli donem oncesi barlardan (mentor, 17 Kasim 2026); sentetik fixture, gercek veri yok."""
from __future__ import annotations

from datetime import datetime as dt, timedelta, timezone

import numpy as np
import pandas as pd
import pytest

pytest.importorskip("pyarrow")

from trader_engine.marketdata.sources import DataError, HistoricalSource  # noqa: E402

CUT = dt(2026, 4, 30, tzinfo=timezone.utc) + timedelta(days=1)       # kilitli donem baslangici


def _write(hist_dir, stem, df):
    hist_dir.mkdir(parents=True, exist_ok=True)
    d = df.reset_index()
    d["date"] = pd.to_datetime(d["date"], utc=True)
    d.to_feather(str(hist_dir / f"{stem}-1h-futures.feather"), compression="uncompressed")


def test_synthetic_rules_ignore_post_boundary_bars(tmp_path):
    n_pre, n_post = 2100, 400
    idx = pd.DatetimeIndex([CUT - timedelta(hours=n_pre) + timedelta(hours=i) for i in range(n_pre + n_post)], name="date")
    assert idx[n_pre] == pd.Timestamp(CUT)
    post = np.arange(n_pre + n_post) >= n_pre
    px = np.where(post, 100.123456, 100.25)                 # sinir sonrasi: ince hassasiyet (etkili olsa tick/step kuculurdu)
    df = pd.DataFrame({"open": px, "high": px + 1, "low": px - 1, "close": px,
                       "volume": np.where(post, 1.123456, 12.345)}, index=idx)
    for pair, stem, mn in (("BTC/USDT", "BTC_USDT_USDT", 100.0), ("ETH/USDT", "ETH_USDT_USDT", 20.0),
                           ("SOL/USDT", "SOL_USDT_USDT", 5.0)):
        hist_dir = tmp_path / stem
        _write(hist_dir, stem, df)
        r = HistoricalSource(str(hist_dir), granularity="15m", synthetic_rules=True).rules(pair)
        assert r.tick == pytest.approx(0.01) and r.step == pytest.approx(0.001) and r.min_qty == pytest.approx(r.step)
        assert r.min_notional == mn and r.max_qty == 1e12
    only_post = tmp_path / "only_post"
    _write(only_post, "BTC_USDT_USDT", df.iloc[n_pre:])
    with pytest.raises(DataError):                          # yalniz sinir sonrasi bar: fail-closed
        HistoricalSource(str(only_post), granularity="15m", synthetic_rules=True).rules("BTC/USDT")


def test_synthetic_rules_window_is_last_2000_pre_boundary(tmp_path):
    # 2000 penceresi: sinirdan onceki son 2000 bar; daha eski ince hassasiyetli bar pencere disinda kalir
    n_pre = 2300
    idx = pd.DatetimeIndex([CUT - timedelta(hours=n_pre) + timedelta(hours=i) for i in range(n_pre)], name="date")
    px = np.where(np.arange(n_pre) < 200, 100.123456, 100.25)
    df = pd.DataFrame({"open": px, "high": px, "low": px, "close": px, "volume": 1.5}, index=idx)
    hist_dir = tmp_path / "w"
    _write(hist_dir, "SOL_USDT_USDT", df)
    r = HistoricalSource(str(hist_dir), granularity="15m", synthetic_rules=True).rules("SOL/USDT")
    assert r.tick == pytest.approx(0.01)
