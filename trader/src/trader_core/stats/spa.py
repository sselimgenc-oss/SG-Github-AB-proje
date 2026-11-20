"""Hansen (2005) Superior Predictive Ability (SPA) testi - yalniz arastirma/raporlama araci.

1L3A ``motor/arastirma/v2/spa.py``'dan uyarlandi; ML'nin mevcut durağan bootstrap'ini
(``stats.stationary_bootstrap_indices``) kullanir. Karar yoluna bagli degildir (canli/paper etkisi yok).

H0: hicbir model kiyasdan (varsayilan: 0 getiri) iyi degil, ``max_k E[d_k] <= 0``.
Istatistik: ``T = max(0, max_k sqrt(n) dbar_k / omega_k)`` (studentize; omega_k bootstrap'tan).
p-degeri uc null ortalamayla (bootstrap ortalamasi ``dbar``'dan ``mu``'ya kaydirilir):
  alt     mu = min(dbar, 0)                       (en liberal)
  tutarli mu = dbar * 1{t_k <= -sqrt(2 log log n)} (raporlanan p)
  ust     mu = 0                                  (en muhafazakar)
Sapma (1L3A'dan): p = mean(Tb >= T) (1L3A'da ``>``). T = 0 iken (hicbir model pozitif degil) ``>`` p = 0 uretir, bu mantiksiz;
``>=`` p = 1 verir. Surekli dagilimda ikisi ayni sonucu verir.
"""
from __future__ import annotations

import math
from typing import Mapping

import numpy as np

from .stats import stationary_bootstrap_indices

__all__ = ["hansen_spa"]

_EPS = 1e-12


def hansen_spa(
    returns: Mapping[str, np.ndarray] | np.ndarray,
    *,
    benchmark: np.ndarray | None = None,
    n_boot: int = 2000,
    mean_block: float = 20.0,
    seed: int = 0,
) -> dict:
    """Hansen SPA. ``returns``: ``{ad: 1-boyutlu seri}`` (ayni uzunluk/hiza) ya da ``(n, K)`` dizi.

    ``benchmark`` verilirse ``d = x - benchmark`` (varsayilan kiyas 0). Varyansi 0 olan model istatistikten cikarilir ve ``n_sabit``
    ile sayilir. Doner: ``p`` (tutarli), ``p_alt``, ``p_ust``, ``T``, ``n``, ``n_model``, ``n_sabit``, ``en_iyi``.
    """
    if isinstance(returns, Mapping):
        names = sorted(returns)
        X = np.column_stack([np.asarray(returns[k], dtype=float) for k in names])
    else:
        X = np.asarray(returns, dtype=float)
        X = X[:, None] if X.ndim == 1 else X
        names = [str(i) for i in range(X.shape[1])]
    if benchmark is not None:
        X = X - np.asarray(benchmark, dtype=float)[:, None]
    if not np.all(np.isfinite(X)):
        raise ValueError("returns must be finite")
    n, K = X.shape
    if n < 3 or K < 1:
        raise ValueError("need n >= 3 observations and at least one model")
    if n_boot < 2:
        raise ValueError("n_boot must be >= 2")
    dbar = X.mean(axis=0)
    rng = np.random.default_rng(seed)
    chunk = max(1, min(n_boot, 4_000_000 // max(n * K, 1)))
    parts, done = [], 0
    while done < n_boot:
        b = min(chunk, n_boot - done)
        idx = stationary_bootstrap_indices(n, b, min(max(mean_block, 1.0), n), rng)
        parts.append(X[idx].mean(axis=1))          # (b, K)
        done += b
    Db = np.concatenate(parts)
    omega = np.sqrt(n * Db.var(axis=0, ddof=1))
    ok = omega > _EPS
    if not ok.any():
        return {"p": 1.0, "p_alt": 1.0, "p_ust": 1.0, "T": 0.0, "n": n, "n_model": K, "n_sabit": K, "en_iyi": ""}
    d, w, D = dbar[ok], omega[ok], Db[:, ok]
    t = math.sqrt(n) * d / w
    T = max(0.0, float(t.max()))
    esik = -math.sqrt(2.0 * math.log(math.log(n))) if n > 2 else -math.inf
    mu = {"alt": np.minimum(d, 0.0), "tutarli": np.where(t <= esik, d, 0.0), "ust": np.zeros(d.size)}
    p = {}
    for ad, m in mu.items():
        Z = math.sqrt(n) * (D - d[None, :] + m[None, :]) / w[None, :]
        Tb = np.maximum(0.0, Z.max(axis=1))
        p[ad] = float((Tb >= T).mean())
    en = names[int(np.flatnonzero(ok)[int(np.argmax(t))])]
    return {"p": p["tutarli"], "p_alt": p["alt"], "p_ust": p["ust"], "T": T, "n": int(n), "n_model": int(K),
            "n_sabit": int(K - int(ok.sum())), "en_iyi": en}
