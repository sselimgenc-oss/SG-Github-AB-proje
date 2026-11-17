# Portions of this file (`efficiency_ratio`, `variance_ratio`, `_safe_div`) are adapted from Aurum v2
# (https://github.com/zero-was-here/aurum -- local clone `sselimgenc-oss/inceleme/tradingbot`), file
# `aurum/features/regime.py` lines 113-134 (+ `safe_div` from `aurum/features/volatility.py`), commit
# 49f073dfdb2f8831e2fcb39b321c1a02bc4bba5f, licensed under the MIT License, Copyright (c) 2025 zero-was-here.
# Read-only adaptation (the clone was never run or imported). Modifications: safe_div inlined, type hints trimmed.
# See THIRD_PARTY_NOTICES.md.
"""Ozellik uretici v2 (ML-G4, arastirma tarafi): r02 `ml1-r02-long-ctx-1r` ve r03 `ml1-r03-long-regime8`.

Motora/boru hattina BAGLI DEGIL (G5'te baglanacak); v1 (`ml_features.py`, canli motor) degismez.

Girdi: pairs {cift: 1s OHLCV (indeks = mum ACILIS zamani, UTC)} -- BTC ve ETH zorunlu; cands: ts (sinyal mumunun
KAPANIS zamani), pair, side ("long"/"short"). Cikti: aday basina bir satir (cands ile ayni indeks), yalniz tarifin
sutunlari (<= 40).

KATI NEDENSELLIK: ts'li aday icin yalniz KAPANIS zamani <= ts olan mumlar kullanilir. Sinyal mumu = acilis ts-1s.
Ust zaman dilimleri (4s/1g) yalniz tam kapanmis mumlardan (v1'in `_htf` + `_asof_close` yolu). Fonlama yalniz
zamani <= ts olan olaylardan.

Tanimlar (belirsiz olanlar):
- Genislik (`f_breadth`): ts'de tam kapanmis son 4s mumda close > EMA(20, 4s close) olan cift ORANI, payda = gecerli
  bayragi olan (EMA isinmis, verisi olan) cift sayisi; gecerli cift < MIN_VALID_PAIRS (5) ise NaN.
- Siralama (`f_rank_ret_24h/7d`): ts'deki son 24 / 168 mumluk getiri (close/close[-n]-1) pairs icindeki YUZDELIK sirasi
  (en dusuk 0, en yuksek 1; (sira-1)/(n-1), n = verisi olan cift sayisi, esitlikte ortalama sira; n < 5 ise NaN). Yone gore
  isaretli: short ise 1 - sira (yani "adayin yonunde en guclu" = 1).
- Korelasyon (`f_corr_btc_7d`): son 168 mumun 1s log getirilerinin cift-BTC Pearson korelasyonu (BTC icin 1).
- Fonlama (`f_funding_last`, `f_funding_sum3`): funding[pair] (indeks = olay zamani, sutun `funding_rate` ya da `rate`;
  ikisi de yoksa HATA) icinde zamani KESINLIKLE < ts olan son oran ve (ts-24s, ts) araligindaki oranlarin toplami
  (ad tarihsel; "son 3" degil), her ikisi side_sign ile carpilir (pozitif = adayin
  yonundeki taraf oduyor/kalabalik). funding verilmediyse ya da cift icin olay yoksa NaN.
- Verimlilik orani: BTC kapanis, 24 ve 96 mum (Kaufman). Varyans orani (`f_btc_vr`): BTC log fiyat, q=4, pencere 96.
- BTC 1g oynaklik yuzdeligi (`f_btc_vol_1d_pct90`): 1g oynaklik (log getiri std, 14 gun) serisinin tam kapanmis son 90
  gunluk penceredeki (en az 30 GECERLI deger) yuzdeligi = gecerli degerler icinde degerden kucuk-esit olanlarin orani
  (payda = NaN olmayan deger sayisi).
- 1g baglam (BTC/ETH/aday cifti 1g egim ve oynaklik, pct90): SABIT 200 gunluk geri bakis (LOOKBACK_1D_DAYS); yalniz
  acilisi >= ts-200g olan KAPANMIS 1g mumlar kullanilir, daha eski gecmis ne kadar olursa olsun sonuc ayni (canli motor
  G5'te >= 200 gun 1s gecmis saglamak ZORUNDA; bkz. ml-guclendirme-plani.md).
- f_stop_dist_atr = |planned_entry - planned_stop| / ATR14(1s, sinyal mumu); cands'ta planned_entry/planned_stop
  sutunlari ZORUNLU (r02).
- Hacim z-skoru: (hacim - ort_n) / std_n, n = 24 / 168, sinyal mumu dahil. Aralik/ATR, govde orani |c-o|/(h-l),
  kapanis konumu (c-l)/(h-l): sinyal mumu; ATR = Wilder 14 (1s). Tepe/dip mesafesi: (n-mum en yuksek high - close)/ATR
  ve (close - n-mum en dusuk low)/ATR, n = 20, 50, sinyal mumu dahil.
- Ayni mumdaki sinyal sayisi (`f_same_bar_signals`): cands icinde ayni ts'ye sahip aday sayisi (kendisi dahil).
- Cekirdek (v1'den yeniden kullanilir, ayni degerler): atr_ratio, 1s/4s egim, hizali 4s egim, 1s/4s oynaklik,
  atr_pct, saat/gun sin-cos; 1g egim/oynaklik sabit 200 gunluk pencereden (yukarida).
- Hacim z-skoru sifir std'de NaN (sonsuz degil). `f_side_sign` cands.side'tan.

ETH 1g oynakligi 40 ozellik sinirina uymak icin (BTC ile yuksek korelasyonlu) birakildi.
G5 ZORUNLULUKLARI (bu modulde YOK): (a) motor >= 200 gun 1g/1s gecmis saglar; (b) trader_ml sarmalayicisi HER cift
cercevesi ve funding uzerinde guards.assert_pre_holdout cagirir; (c) f_same_bar_signals icin iki gecisli degerlendirme.
TODO (G5, canli motor baglami gerektirir; bu modulde YOK): acik aday sayisi, son cikistan bu yana mum sayisi.
Sonuca dayali defter ozellikleri yasak.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from .indicators import atr, ema
from .ml_features import BAR, BTC, ETH, MAX_FEATURES, OHLC, _asof_close, _htf, feature_frame

RECIPES = ("r02", "r03")
LOOKBACK_1D_DAYS = 200       # 1g baglam ozellikleri icin SABIT geri bakis (mentor G4-1)
MIN_VALID_PAIRS = 5          # genislik / siralama icin asgari gecerli cift (mentor G4-5)
CORE_V1_NAMES = [
    "f_atr_ratio", "f_stop_dist_atr", "f_side_sign", "f_slope_1h", "f_slope_4h", "f_slope_1d", "f_slope_4h_aligned",
    "f_vol_1h", "f_vol_4h", "f_vol_1d", "f_atr_pct_1h", "f_hour_sin", "f_hour_cos", "f_dow_sin", "f_dow_cos",
]
R02_CONTEXT_NAMES = [
    "f_btc_slope_4h", "f_btc_slope_1d", "f_btc_vol_4h", "f_btc_vol_1d",
    "f_eth_slope_4h", "f_eth_slope_1d", "f_eth_vol_4h",
    "f_btc_er_24", "f_btc_er_96", "f_breadth",
    "f_rank_ret_24h", "f_rank_ret_7d", "f_corr_btc_7d",
    "f_funding_last", "f_funding_sum3", "f_same_bar_signals",
    "f_vol_z_24", "f_vol_z_168", "f_range_atr", "f_body_ratio", "f_close_pos",
    "f_dist_hi20_atr", "f_dist_lo20_atr", "f_dist_hi50_atr", "f_dist_lo50_atr",
]
R02_FEATURE_NAMES = CORE_V1_NAMES + R02_CONTEXT_NAMES
R03_FEATURE_NAMES = [
    "f_btc_slope_4h", "f_btc_slope_1d", "f_btc_er_96", "f_btc_vr", "f_btc_vol_1d_pct90", "f_breadth",
    "f_same_bar_signals", "f_side_x_btc_slope_1d",
]
assert len(R02_FEATURE_NAMES) <= MAX_FEATURES and len(R03_FEATURE_NAMES) <= MAX_FEATURES
assert len(set(R02_FEATURE_NAMES)) == len(R02_FEATURE_NAMES)

VR_Q, VR_WINDOW = 4, 96


def _safe_div(num, den, *, fill: float = np.nan) -> np.ndarray:
    n = np.asarray(num, dtype=float)
    d = np.asarray(den, dtype=float)
    out = np.full(np.broadcast(n, d).shape, fill, dtype=float)
    ok = np.isfinite(d) & (d != 0.0) & np.isfinite(n)
    np.divide(n, d, out=out, where=ok)
    out[~np.isfinite(out)] = fill
    return out


def efficiency_ratio(close: pd.Series, n: int) -> pd.Series:
    """Kaufman efficiency ratio over ``n`` bars (NaN warm-up; 0 for a flat window)."""
    c = close.astype(float)
    net = (c - c.shift(n)).abs()
    path = c.diff().abs().rolling(n, min_periods=n).sum()
    er = np.where(path.to_numpy() > 0, _safe_div(net, path, fill=0.0), 0.0)
    return pd.Series(np.where(path.isna().to_numpy() | net.isna().to_numpy(), np.nan, er), index=close.index)


def variance_ratio(logp: pd.Series, q: int, window: int) -> pd.Series:
    """Rolling Lo-MacKinlay variance ratio with overlapping q-bar returns (same trailing ``window`` for both)."""
    r1 = logp.diff()
    rq = logp - logp.shift(q)
    v1 = r1.rolling(window, min_periods=window).var(ddof=1)
    vq = rq.rolling(window, min_periods=window).var(ddof=1)
    return pd.Series(_safe_div(vq, q * v1), index=logp.index)


def _utc_index(df: pd.DataFrame) -> pd.DataFrame:
    if df.index.tz is None:
        df = df.tz_localize("UTC")
    return df.sort_index()


def _at(s: pd.Series, open_t: pd.DatetimeIndex) -> np.ndarray:
    """1s seri (indeks = acilis) -> aday sinyal mumlarindaki deger (yoksa NaN)."""
    return s.reindex(open_t).to_numpy(float)


def _trend_flag_4h(df: pd.DataFrame) -> pd.DataFrame:
    h = df[["open", "high", "low", "close"]].resample("4h", label="left", closed="left").agg(OHLC).dropna()
    e = ema(h["close"], 20)
    up = np.where(e.isna().to_numpy(), np.nan, (h["close"] > e).to_numpy().astype(float))
    return pd.DataFrame({"up": up}, index=h.index + pd.Timedelta("4h"))


def _pct_last(v: np.ndarray, window: int = 90, min_valid: int = 30) -> float:
    """Son `window` degerde, son degerin yuzdeligi: gecerli (NaN olmayan) degerler icinde <= olanlarin orani."""
    x = np.asarray(v, dtype=float)[-window:]
    ok = x[np.isfinite(x)]
    if len(ok) < min_valid or not np.isfinite(x[-1]):
        return np.nan
    return float(np.sum(ok <= x[-1]) / len(ok))


def _daily_ctx_fixed(df: pd.DataFrame, ts: pd.DatetimeIndex) -> pd.DataFrame:
    """Her ts icin 1g baglam (slope, vol, pct): ts'de KAPANMIS 1g mumlar, acilisi >= ts-200g olan 1s mumlardan.
    Pencere ts'ye gore SABIT: ondeki gecmis eklense/silinse sonuc degismez. 1g degerler gunde bir degistiginden
    gun basina (D = ts.floor('1D')) bir kez hesaplanir; pencere [D-199g, D) ve D-199g >= ts-200g."""
    day = ts.floor("1D")
    cols = ["slope", "vol", "pct"]
    res = {}
    for d in day.unique():
        w = df[(df.index >= d - pd.Timedelta(days=LOOKBACK_1D_DAYS - 1)) & (df.index < d)]
        if len(w) == 0:
            res[d] = (np.nan, np.nan, np.nan)
            continue
        h = _htf(w, "1D", 10, 3, 14)
        res[d] = (h["slope"].iloc[-1], h["vol"].iloc[-1], _pct_last(h["vol"].to_numpy())) if len(h) else (np.nan,) * 3
    return pd.DataFrame([res[d] for d in day], columns=cols, index=ts)


def _funding_at(fund: pd.DataFrame | None, ts: pd.DatetimeIndex) -> tuple[np.ndarray, np.ndarray]:
    nan = np.full(len(ts), np.nan)
    if fund is None or len(fund) == 0:
        return nan, nan.copy()
    f = _utc_index(fund)
    col = "funding_rate" if "funding_rate" in f.columns else ("rate" if "rate" in f.columns else None)
    if col is None:
        raise ValueError("funding frame needs a 'funding_rate' (or 'rate') column")
    r = f[col].astype(float).to_numpy()
    cs = np.concatenate([[0.0], np.cumsum(r)])
    hi = f.index.searchsorted(ts, side="left")                       # olay zamani KESINLIKLE < ts
    lo = f.index.searchsorted(ts - pd.Timedelta(hours=24), side="right")   # olay zamani > ts-24s
    last = np.where(hi >= 1, r[np.maximum(hi - 1, 0)], np.nan)
    s3 = np.where(hi > lo, cs[hi] - cs[np.minimum(lo, hi)], np.nan)
    return last, s3


def _pct_rank_signed(mat: pd.DataFrame, cols: list[str], pair_of_row: np.ndarray, side: np.ndarray) -> np.ndarray:
    r = mat.rank(axis=1, method="average")
    n = mat.notna().sum(axis=1).to_numpy(float)
    pct = (r.to_numpy() - 1.0) / np.where(n >= MIN_VALID_PAIRS, n - 1.0, np.nan)[:, None]
    ci = np.array([cols.index(p) for p in pair_of_row])
    own = pct[np.arange(len(ci)), ci]
    return np.where(side > 0, own, 1.0 - own)


def feature_frame_v2(pairs: dict[str, pd.DataFrame], cands: pd.DataFrame, *,
                     funding: dict[str, pd.DataFrame] | None = None, recipe: str) -> pd.DataFrame:
    """Aday basina r02/r03 ozellikleri (modul docstring'ine bakin). Satir sayisi/indeksi = cands."""
    if recipe not in RECIPES:
        raise ValueError(f"recipe must be one of {RECIPES}, got {recipe!r}")
    for need in (BTC, ETH):
        if need not in pairs:
            raise ValueError(f"pairs must include {need}")
    miss = set(cands["pair"]) - set(pairs)
    if miss:
        raise ValueError(f"candidate pairs without data: {sorted(miss)}")
    names = R02_FEATURE_NAMES if recipe == "r02" else R03_FEATURE_NAMES
    pairs = {p: _utc_index(d) for p, d in pairs.items()}
    cols = sorted(pairs)
    ts = pd.DatetimeIndex(pd.to_datetime(cands["ts"], utc=True))
    open_t = ts - BAR
    side = cands["side"].map({"long": 1.0, "short": -1.0}).to_numpy(float)
    if np.isnan(side).any():
        raise ValueError("cands.side must be 'long' or 'short'")
    pair_arr = cands["pair"].to_numpy()
    out = pd.DataFrame(index=cands.index)
    btc, eth = pairs[BTC], pairs[ETH]

    def htf(df, rule, ema_len, slope_n, vol_n):
        return _asof_close(_htf(df, rule, ema_len, slope_n, vol_n), open_t)

    b4, b1d = htf(btc, "4h", 20, 3, 12), _daily_ctx_fixed(btc, ts)
    out["f_btc_slope_4h"], out["f_btc_slope_1d"] = b4["slope"].to_numpy(), b1d["slope"].to_numpy()
    out["f_btc_er_96"] = _at(efficiency_ratio(btc["close"], 96), open_t)
    out["f_same_bar_signals"] = cands.groupby(ts)["pair"].transform("size").to_numpy(float)
    flags = np.column_stack([_asof_close(_trend_flag_4h(pairs[p]), open_t)["up"].to_numpy() for p in cols])
    n_valid = np.isfinite(flags).sum(axis=1).astype(float)
    out["f_breadth"] = np.where(n_valid >= MIN_VALID_PAIRS, (flags == 1.0).sum(axis=1) / np.maximum(n_valid, 1.0), np.nan)
    if recipe == "r03":
        out["f_btc_vr"] = _at(variance_ratio(np.log(btc["close"]), VR_Q, VR_WINDOW), open_t)
        out["f_btc_vol_1d_pct90"] = b1d["pct"].to_numpy()
        out["f_side_x_btc_slope_1d"] = side * out["f_btc_slope_1d"].to_numpy()
        return out[names]

    # ---- r02 ----
    for need_col in ("planned_entry", "planned_stop"):
        if need_col not in cands.columns:
            raise ValueError(f"r02 needs cands.{need_col} (f_stop_dist_atr)")
    e4, e1d = htf(eth, "4h", 20, 3, 12), _daily_ctx_fixed(eth, ts)
    out["f_btc_vol_4h"], out["f_btc_vol_1d"] = b4["vol"].to_numpy(), b1d["vol"].to_numpy()
    out["f_eth_slope_4h"], out["f_eth_slope_1d"] = e4["slope"].to_numpy(), e1d["slope"].to_numpy()
    out["f_eth_vol_4h"] = e4["vol"].to_numpy()
    out["f_btc_er_24"] = _at(efficiency_ratio(btc["close"], 24), open_t)

    for name, n in (("f_rank_ret_24h", 24), ("f_rank_ret_7d", 168)):
        mat = pd.DataFrame({p: _at(pairs[p]["close"] / pairs[p]["close"].shift(n) - 1.0, open_t) for p in cols})
        out[name] = _pct_rank_signed(mat, cols, pair_arr, side)

    lr_btc = np.log(btc["close"]).diff()
    res = {k: np.full(len(cands), np.nan) for k in (
        "f_corr_btc_7d", "f_funding_last", "f_funding_sum3", "f_vol_z_24", "f_vol_z_168", "f_range_atr",
        "f_body_ratio", "f_close_pos", "f_dist_hi20_atr", "f_dist_lo20_atr", "f_dist_hi50_atr", "f_dist_lo50_atr")}
    core = {k: np.full(len(cands), np.nan) for k in CORE_V1_NAMES}
    for p in sorted(set(pair_arr)):
        m = pair_arr == p
        df, ot = pairs[p], open_t[m]
        c, a = df["close"], atr(df, 14)
        res["f_corr_btc_7d"][m] = _at(np.log(c).diff().rolling(168, min_periods=168).corr(lr_btc.reindex(df.index)), ot)
        for n in (24, 168):
            v = df["volume"]
            res[f"f_vol_z_{n}"][m] = _at(pd.Series(_safe_div(v - v.rolling(n, min_periods=n).mean(), v.rolling(n, min_periods=n).std()), index=df.index), ot)
        rng = df["high"] - df["low"]
        res["f_range_atr"][m] = _at(rng / a, ot)
        res["f_body_ratio"][m] = _at(pd.Series(_safe_div((c - df["open"]).abs(), rng), index=df.index), ot)
        res["f_close_pos"][m] = _at(pd.Series(_safe_div(c - df["low"], rng), index=df.index), ot)
        for n in (20, 50):
            res[f"f_dist_hi{n}_atr"][m] = _at((df["high"].rolling(n, min_periods=n).max() - c) / a, ot)
            res[f"f_dist_lo{n}_atr"][m] = _at((c - df["low"].rolling(n, min_periods=n).min()) / a, ot)
        fl, s3 = _funding_at((funding or {}).get(p), ts[m])
        res["f_funding_last"][m], res["f_funding_sum3"][m] = fl, s3
        # ---- v1 cekirdegi: yalniz bu cift icin, sinyal modulu + HTF ozellikleri (v1 ile ayni kod) ----
        v1 = feature_frame(df[["open", "high", "low", "close", "volume"]])
        for k in CORE_V1_NAMES:
            if k not in ("f_side_sign", "f_stop_dist_atr", "f_slope_1d", "f_vol_1d"):
                core[k][m] = v1[k].reindex(ot).to_numpy(float)
        d1 = _daily_ctx_fixed(df, ts[m])                          # sabit 200 gunluk pencere (canli ile ayni)
        core["f_slope_1d"][m], core["f_vol_1d"][m] = d1["slope"].to_numpy(), d1["vol"].to_numpy()
        pe = cands["planned_entry"].to_numpy(float)[m]
        ps = cands["planned_stop"].to_numpy(float)[m]
        core["f_stop_dist_atr"][m] = _safe_div(np.abs(pe - ps), _at(a, ot))
    for k, v in res.items():
        out[k] = v
    for k, v in core.items():
        out[k] = v
    out["f_side_sign"] = side
    out["f_slope_4h_aligned"] = out["f_slope_4h"].to_numpy() * side
    for k in ("f_funding_last", "f_funding_sum3"):
        out[k] = out[k].to_numpy() * side
    return out[names]
