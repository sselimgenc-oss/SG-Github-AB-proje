"""Tek ozellik uretici (§3.2): gecmis tarama ve canli AYNI kodu kullanir. Kati nedensel.

ML-0a: motorun trader_ml'e bagimli olmamasi icin trader_core'a tasindi; trader_ml.features geri-export eder ve
kilitli donem korumasini (assert_pre_holdout) kendi sarmalayicisinda uygular.

Satir t (1 saatlik mum, indeks = ACILIS zamani) yalniz 0..t mumlarina baglidir; karar ani = mumun
kapanisi (t + 1s). 4s/1g ozellikler yalniz karar aninda TAMAMLANMIS 4s/1g mumlardan alinir.
Ozellikler olcek bagimsizdir (ATR'ye ya da yuzdeye bolunmus); en fazla 40 tane.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from .indicators import atr, ema
from .regime import align_to_base, classify_series
from .signals import compute_signals

BAR = pd.Timedelta(hours=1)
MAX_FEATURES = 40

BTC, ETH = "BTC/USDT:USDT", "ETH/USDT:USDT"
OHLC = {"open": "first", "high": "max", "low": "min", "close": "last"}

FEATURE_NAMES = [
    "f_atr_ratio", "f_reg_trend_up", "f_reg_trend_down", "f_reg_range", "f_reg_volatile",
    "f_stop_dist_atr", "f_rr", "f_is_t1", "f_side_sign", "f_edge_dist_atr", "f_rh_touches", "f_rl_touches",
    "f_range_width_atr", "f_entry_to_rh_atr", "f_entry_to_rl_atr",
    "f_slope_1h", "f_slope_4h", "f_slope_1d", "f_slope_4h_aligned",
    "f_vol_1h", "f_vol_4h", "f_vol_1d", "f_atr_pct_1h",
    "f_btc_slope_4h", "f_btc_vol_4h", "f_eth_slope_4h", "f_eth_vol_4h", "f_funding",
    "f_hour_sin", "f_hour_cos", "f_dow_sin", "f_dow_cos",
    "f_ret_lag1", "f_ret_lag2", "f_ret_lag3", "f_atr_ratio_lag1", "f_atr_ratio_lag2", "f_atr_ratio_lag3",
    "f_bars_since_exit",
]
assert len(FEATURE_NAMES) <= MAX_FEATURES


def _htf(df: pd.DataFrame, rule: str, ema_len: int, slope_n: int, vol_n: int) -> pd.DataFrame:
    """Ust zaman dilimi: slope/vol; indeks = TAMAMLANMA (kapanis) zamani."""
    h = df[["open", "high", "low", "close"]].resample(rule, label="left", closed="left").agg(OHLC).dropna()
    a = atr(h, 14)
    e = ema(h["close"], ema_len)
    slope = (e - e.shift(slope_n)) / a
    vol = np.log(h["close"]).diff().rolling(vol_n, min_periods=vol_n).std()
    # .to_numpy(): Series indeksiyle hizalama YAPMA (yoksa deger tamamlanmamis mumun etiketine kayar)
    out = pd.DataFrame({"slope": slope.to_numpy(), "vol": vol.to_numpy()}, index=h.index + pd.Timedelta(rule))
    return out


def _asof_close(src: pd.DataFrame, base_index: pd.DatetimeIndex) -> pd.DataFrame:
    """src (indeks = tamamlanma zamani) -> 1s mumlarin KAPANIS aninda gecerli son tamamlanmis deger."""
    pos = src.index.searchsorted(base_index + BAR, side="right") - 1
    ok = pos >= 0
    vals = src.to_numpy(float)[np.where(ok, pos, 0)]
    vals[~ok] = np.nan
    return pd.DataFrame(vals, index=base_index, columns=src.columns)


def _market_state(df: pd.DataFrame, base_index: pd.DatetimeIndex) -> pd.DataFrame:
    return _asof_close(_htf(df, "4h", 20, 3, 12), base_index)


def feature_frame(df: pd.DataFrame, btc: pd.DataFrame | None = None, eth: pd.DataFrame | None = None) -> pd.DataFrame:
    """Her 1s mum icin sinyal sutunlari + f_* ozellikleri (f_bars_since_exit tablo duzeyinde eklenir).
    Kilitli donem korumasi YOK (motor canli veriyle cagirir); egitim yolu trader_ml.features.feature_frame'i kullanir."""
    idx = df.index
    h4 = df[["open", "high", "low", "close"]].resample("4h", label="left", closed="left").agg(OHLC).dropna()
    reg = align_to_base(classify_series(h4), idx, 4)
    sig = compute_signals(df[["open", "high", "low", "close"]], reg)
    a1 = atr(df, 14)
    c = df["close"]
    f = pd.DataFrame(index=idx)
    ratio = sig["atr_ratio"]
    f["f_atr_ratio"] = ratio
    for name in ("trend_up", "trend_down", "range", "volatile"):
        f[f"f_reg_{name}"] = (sig["regime"] == name).astype(float)
    side_sign = sig["side"].map({"long": 1.0, "short": -1.0}).astype(float)
    f["f_stop_dist_atr"] = sig["stop_dist_atr"]
    f["f_rr"] = sig["rr"]
    f["f_is_t1"] = (sig["setup"] == "T1").astype(float)
    f["f_side_sign"] = side_sign
    f["f_edge_dist_atr"] = sig["edge_dist_atr"]
    f["f_rh_touches"] = sig["rh_touches"].astype(float)
    f["f_rl_touches"] = sig["rl_touches"].astype(float)
    f["f_range_width_atr"] = (sig["rh"] - sig["rl"]) / sig["atr_4h"]
    f["f_entry_to_rh_atr"] = (sig["rh"] - sig["planned_entry"]) / sig["atr_tf"]
    f["f_entry_to_rl_atr"] = (sig["planned_entry"] - sig["rl"]) / sig["atr_tf"]
    e1 = ema(c, 20)
    f["f_slope_1h"] = (e1 - e1.shift(5)) / a1
    h4f = _asof_close(_htf(df, "4h", 20, 3, 12), idx)
    d1f = _asof_close(_htf(df, "1D", 10, 3, 14), idx)
    f["f_slope_4h"], f["f_vol_4h"] = h4f["slope"], h4f["vol"]
    f["f_slope_1d"], f["f_vol_1d"] = d1f["slope"], d1f["vol"]
    f["f_slope_4h_aligned"] = h4f["slope"] * side_sign
    f["f_vol_1h"] = np.log(c).diff().rolling(24, min_periods=24).std()
    f["f_atr_pct_1h"] = a1 / c
    for nm, ref in (("btc", btc), ("eth", eth)):
        ms = _market_state(ref, idx) if ref is not None else None
        f[f"f_{nm}_slope_4h"] = ms["slope"] if ms is not None else np.nan
        f[f"f_{nm}_vol_4h"] = ms["vol"] if ms is not None else np.nan
    f["f_funding"] = df["funding"] if "funding" in df.columns else np.nan
    close_t = idx + BAR
    f["f_hour_sin"] = np.sin(2 * np.pi * close_t.hour / 24)
    f["f_hour_cos"] = np.cos(2 * np.pi * close_t.hour / 24)
    f["f_dow_sin"] = np.sin(2 * np.pi * close_t.day_of_week / 7)
    f["f_dow_cos"] = np.cos(2 * np.pi * close_t.day_of_week / 7)
    r1 = (c - c.shift(1)) / a1
    for k in (1, 2, 3):
        f[f"f_ret_lag{k}"] = r1.shift(k)
        f[f"f_atr_ratio_lag{k}"] = ratio.shift(k)
    f["f_bars_since_exit"] = np.nan
    f = f[FEATURE_NAMES]
    keep = ["setup", "side", "signal", "planned_entry", "planned_stop", "planned_target"]
    return pd.concat([sig[keep], f], axis=1)


