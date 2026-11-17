"""Model havuzu (§2): yalniz lojistik regresyon (taban) + LightGBM. Kalibrasyon (Platt) kendi kodumuz.

lightgbm yalniz burada, fonksiyon icinde ice aktarilir (egitim/arastirma tarafi).
"""
from __future__ import annotations

import warnings

import numpy as np
import pandas as pd

from .config import AGE_HALF_LIFE_DAYS, BAR, EMBARGO_BARS, LGBM_PARAMS, LOGIT_PARAMS, SOURCE_WEIGHTS
from .treeeval import _sigmoid


def sample_weights(df: pd.DataFrame, ref_ts: pd.Timestamp) -> np.ndarray:
    """Kaynak agirligi x yasa gore ussel azalma (§3.3 adim 1; kanit tutmayan zamanla zayiflar)."""
    base = df["source"].map(SOURCE_WEIGHTS).to_numpy(float)
    age = np.clip((ref_ts - df["ts"]).dt.total_seconds().to_numpy() / 86400.0, 0.0, None)
    return base * 0.5 ** (age / AGE_HALF_LIFE_DAYS)


def training_weights(df: pd.DataFrame, scheme: str | None = None) -> np.ndarray:
    """Egitim agirliklari; `df` = bir dilimin (arindirma/ambargo sonrasi) EGITIM satirlari ya da nihai tablo.
    scheme "age_decay" (r01, varsayilan = config.WEIGHT_SCHEME) -> sample_weights; "uniq_decay" -> sample_weights_v2."""
    from . import config
    scheme = scheme or config.WEIGHT_SCHEME
    if scheme == "age_decay":
        return sample_weights(df, df["ts"].max())
    if scheme == "uniq_decay":
        from .weights import sample_weights_v2
        return sample_weights_v2(df)
    raise ValueError(f"bilinmeyen agirlik semasi: {scheme!r}")


# ------------------------------------------------------------------------------------- lojistik
def fit_logistic(X: np.ndarray, y: np.ndarray, w: np.ndarray, l2: float = LOGIT_PARAMS["l2"],
                 max_iter: int = LOGIT_PARAMS["max_iter"]) -> dict:
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", RuntimeWarning)
        fill = np.nanmedian(np.where(np.isfinite(X), X, np.nan), axis=0) if len(X) else np.zeros(X.shape[1])
    fill = np.where(np.isfinite(fill), fill, 0.0)
    Xf = np.where(np.isnan(X), fill, X)
    mean = np.average(Xf, axis=0, weights=w)
    std = np.sqrt(np.average((Xf - mean) ** 2, axis=0, weights=w))
    std = np.where(std > 1e-12, std, 1.0)
    Z = (Xf - mean) / std
    n, d = Z.shape
    A = np.hstack([Z, np.ones((n, 1))])
    beta = np.zeros(d + 1)
    reg = np.diag(np.r_[np.full(d, l2), 0.0])
    for _ in range(max_iter):
        p = _sigmoid(A @ beta)
        g = A.T @ (w * (p - y)) + reg @ beta
        H = (A * (w * p * (1 - p))[:, None]).T @ A + reg + 1e-9 * np.eye(d + 1)
        step = np.linalg.solve(H, g)
        beta -= step
        if np.max(np.abs(step)) < 1e-8:
            break
    return {"kind": "logistic", "n_features": int(d), "coef": beta[:d].tolist(), "intercept": float(beta[d]),
            "mean": mean.tolist(), "std": std.tolist(), "fill": fill.tolist()}


# ------------------------------------------------------------------------------------- Platt
def fit_platt_info(z: np.ndarray, y: np.ndarray, iters: int = 50, *, nonneg_slope: bool = False) -> tuple[dict, bool]:
    """p = sigmoid(a*z + b); Newton. Dejenere durumda (a,b)=(1,0). nonneg_slope: a<0 ise a=0 ve
    b = logit(mean(y)) (yalniz kesen => sabit p = taban oran). Ikinci deger: egim KISILDI mi (clamped)."""
    if len(z) < 20 or y.min() == y.max() or np.std(z) < 1e-12:
        return {"a": 1.0, "b": 0.0}, False
    A = np.column_stack([z, np.ones_like(z)])
    beta = np.array([1.0, 0.0])
    for _ in range(iters):
        p = _sigmoid(A @ beta)
        g = A.T @ (p - y) + 1e-6 * beta
        H = (A * (p * (1 - p))[:, None]).T @ A + 1e-6 * np.eye(2)
        step = np.linalg.solve(H, g)
        beta -= step
        if np.max(np.abs(step)) < 1e-10:
            break
    if nonneg_slope and beta[0] < 0:
        m = float(np.clip(np.mean(y), 1e-6, 1 - 1e-6))
        return {"a": 0.0, "b": float(np.log(m / (1 - m)))}, True
    return {"a": float(beta[0]), "b": float(beta[1])}, False


def fit_platt(z: np.ndarray, y: np.ndarray, iters: int = 50, *, nonneg_slope: bool = False) -> dict:
    return fit_platt_info(z, y, iters, nonneg_slope=nonneg_slope)[0]


# ------------------------------------------------------------------------------------- LightGBM
def _lgb_params() -> dict:
    p = dict(LGBM_PARAMS)
    p.pop("n_estimators_max"), p.pop("early_stopping_rounds")
    return p


def fit_lgbm(X, y, w, *, val_frac: float = 0.2, num_rounds: int | None = None, ts=None, label_end=None):
    """Sabit tarif; erken durdurma icin kronolojik son %val_frac dogrulama. (booster, best_iter).
    num_rounds verilirse erken durdurma yok (nihai model). ts + label_end (datetime64, X ile ayni sira)
    verilirse egitim/dogrulama arasinda ARINDIRMA yapilir: etiketi dogrulama baslangicindan (- ambargo)
    sonra biten egitim satirlari atilir."""
    import lightgbm as lgb
    p = _lgb_params()
    if num_rounds is not None:
        ds = lgb.Dataset(X, label=y, weight=w, free_raw_data=False)
        return lgb.train(p, ds, num_boost_round=num_rounds), num_rounds
    k = int(len(X) * (1 - val_frac))
    tr_ix = np.arange(k)
    if ts is not None and label_end is not None:
        cut = np.asarray(ts, dtype="datetime64[ns]")[k] - np.timedelta64(EMBARGO_BARS * BAR.value, "ns")
        tr_ix = tr_ix[np.asarray(label_end, dtype="datetime64[ns]")[:k] < cut]
    dtr = lgb.Dataset(X[tr_ix], label=y[tr_ix], weight=w[tr_ix], free_raw_data=False)
    dva = lgb.Dataset(X[k:], label=y[k:], weight=w[k:], reference=dtr, free_raw_data=False)
    b = lgb.train(p, dtr, num_boost_round=LGBM_PARAMS["n_estimators_max"], valid_sets=[dva],
                  callbacks=[lgb.early_stopping(LGBM_PARAMS["early_stopping_rounds"], verbose=False)])
    return b, max(int(b.best_iteration), 10)


def lgbm_dump(booster) -> dict:
    d = booster.dump_model()
    return {"kind": "lgbm", "n_features": int(d["max_feature_idx"]) + 1, "tree_info": d["tree_info"],
            "objective": d["objective"]}


def logistic_predict_raw(model: dict, X: np.ndarray) -> np.ndarray:
    """Egitim tarafi dogrudan tahmin (esleme testi referansi; treeeval'dan bagimsiz yazildi)."""
    Xf = np.where(np.isnan(X), np.asarray(model["fill"]), X)
    return ((Xf - np.asarray(model["mean"])) / np.asarray(model["std"])) @ np.asarray(model["coef"]) + model["intercept"]


def lightgbm_version() -> str | None:
    """Kurulu lightgbm surumu; yuklenemezse None (gercek kosu bunu hata sayar)."""
    try:
        import lightgbm as lgb
        return str(lgb.__version__)
    except ImportError:
        return None
