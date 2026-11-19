"""M1 egitimi: ridge lojistik (WP-10 `setup_filter.train.fit_logistic`), kilit donemi YAPISAL reddi (D-T21).

Esik: egitim puanlarinin %98'i (en yuksek ~%2 aday). Model, veri, sinif tek ise None (aday uretilmez; motor durmaz).
Girdi satirlari {ts, ts_end, side, x, y}; ts ve ts_end tz-li olmali; herhangi bir satir kilit donemiyle kesisirse
LockWindowError (tek satir bile olsa egitim yapilmaz)."""
from __future__ import annotations

import hashlib
from collections.abc import Iterable, Mapping, Sequence
from datetime import datetime

import numpy as np

from trader_core.ml_eval import TreeModel
from trader_ml.setup_filter.train import LOCK_END, LOCK_START, LockWindowError, assert_no_lock, drop_lock, fit_logistic  # noqa: F401

from . import features as F
from .package import build_package

THRESHOLD_Q = 0.98
MAX_ROWS = 400_000


def train_tf(rows: Sequence[Mapping], *, arm_id: str, created_at: datetime | None = None, max_rows: int = MAX_ROWS) -> dict | None:
    """Tek zaman dilimi paketi (arm_id = 'M1@<tf>') ya da None. Kilit satiri -> LockWindowError."""
    assert_no_lock(rows)
    rows = sorted(rows, key=lambda r: (r["ts"], r["side"]))[-max_rows:]
    if len(rows) < 2:
        return None
    y = np.array([float(r["y"]) for r in rows])
    if y.min() == y.max():
        return None
    X = np.vstack([np.asarray(r["x"], dtype=np.float64) for r in rows])
    if not np.isfinite(X).all():
        raise ValueError("ozellik matrisinde sonlu olmayan deger")
    model = fit_logistic(X, y)
    scores = TreeModel(model, {"a": 1.0, "b": 0.0}).predict_proba(X)
    thr = float(np.quantile(scores, THRESHOLD_Q))
    return build_package(arm_id, model, thr, list(F.FEATURE_NAMES), train_start=rows[0]["ts"], train_end=rows[-1]["ts"],
                         n_train=len(rows), n_pos=int(y.sum()), data_hash=row_digest(rows), lock_dropped=0,
                         base_rate=float(y.mean()), created_at=created_at)


def split_lock(rows: Iterable[Mapping]) -> tuple[list[dict], int]:
    """Kilit satirlarini sayip dusurur (kâgit kaydi icin); tarihsel satirlar buradan gecmez, kilit ihlali TRAIN'de yakalanir."""
    return drop_lock(rows)


def row_digest(rows: Sequence[Mapping]) -> str:
    h = hashlib.sha256()
    for r in rows:
        h.update(f"{r['ts'].isoformat()}|{r['side']}|{r['y']}|{np.asarray(r['x']).tobytes().hex()}".encode())
    return h.hexdigest()
