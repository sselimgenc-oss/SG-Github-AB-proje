"""Ozellik uretici geri-export (§3.2): kod trader_core.ml_features'e tasindi (motor ayni kodu canlida kullanir; ML-0a).
Bu modul egitim yoluna kilitli donem korumasini ekler ve aday/`f_bars_since_exit` tablo islevlerini tasir."""
from __future__ import annotations

import numpy as np
import pandas as pd

from trader_core import ml_features as _core
from trader_core.ml_features import (  # noqa: F401
    BTC, ETH, FEATURE_NAMES, OHLC, _asof_close, _htf, _market_state)

from .config import BAR, MAX_FEATURES
from .guards import assert_pre_holdout

assert len(FEATURE_NAMES) <= MAX_FEATURES


def feature_frame(df: pd.DataFrame, btc: pd.DataFrame | None = None, eth: pd.DataFrame | None = None,
                  *, check_holdout: bool = True) -> pd.DataFrame:
    """Her 1s mum icin sinyal sutunlari + f_* ozellikleri; egitim yolu (kilitli donem korumali)."""
    if check_holdout:
        assert_pre_holdout(df.index, "mum verisi")
    return _core.feature_frame(df, btc, eth)


def candidate_rows(frame: pd.DataFrame, pair: str) -> pd.DataFrame:
    """Sinyal veren mumlari (planli giris/stop olan) aday satirlarina cevirir; ts = mum kapanisi."""
    m = frame["signal"].astype(bool) & frame["side"].notna() & frame["planned_entry"].notna()
    r = frame[m].copy()
    r.insert(0, "pair", pair)
    r.insert(1, "ts", r.index + BAR)
    return r.drop(columns=["signal"]).reset_index(drop=True)


def add_bars_since_exit(table: pd.DataFrame) -> pd.DataFrame:
    """Ayni cift icin, karar aninda ZATEN gerceklesmis (exit_ts <= ts) son ALINAN islemin cikisindan
    beri gecen mum sayisi. Canli bot alinmayan adaylarin bariyer bitisini goremez; yalniz alinan
    islemlerin gercek cikislari (exit_ts) kullanilir, gelecekte biten islem sayilmaz."""
    out = table.copy()
    vals = np.full(len(out), np.nan)
    for _, g in out.groupby("pair", sort=False):
        ts = g["ts"].to_numpy("datetime64[ns]")
        ex = g.loc[g["taken"].astype(bool), "exit_ts"].dropna().to_numpy("datetime64[ns]")
        if len(ex) == 0:
            continue
        e_sorted = np.sort(ex)
        pos = np.searchsorted(e_sorted, ts, side="right") - 1
        ok = pos >= 0
        res = np.full(len(g), np.nan)
        res[ok] = (ts[ok] - e_sorted[pos[ok]]) / np.timedelta64(1, "h")
        vals[out.index.get_indexer(g.index)] = res
    out["f_bars_since_exit"] = vals
    return out
