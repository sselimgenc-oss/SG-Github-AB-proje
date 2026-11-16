"""Model paketi (§3.3 adim 5, §3.6): JSON (pickle YOK) + meta (ozellik listesi/hash, egitim penceresi,
surum, son kullanma 21 gun, veri ve kod ozeti)."""
from __future__ import annotations

import hashlib
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

import numpy as np
import pandas as pd

from .config import MODEL_EXPIRY_DAYS, RECIPE_ID

PKG_VERSION = 1


def canon(obj) -> str:
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), allow_nan=False)


def sha256_text(s: str) -> str:
    return hashlib.sha256(s.encode("utf-8")).hexdigest()


def feature_list_hash(names: list[str]) -> str:
    return sha256_text("\n".join(names))


def data_hash(df: pd.DataFrame) -> str:
    """Aday tablosunun icerik ozeti (sutun adlari + degerler, satir sirasi dahil)."""
    h = hashlib.sha256()
    h.update("|".join(df.columns).encode())
    h.update(pd.util.hash_pandas_object(df, index=False).to_numpy().tobytes())
    return h.hexdigest()


def code_hash() -> str:
    h = hashlib.sha256()
    for f in sorted(Path(__file__).parent.glob("*.py")):
        h.update(f.name.encode())
        h.update(f.read_bytes())
    return h.hexdigest()


def feature_ranges(X: np.ndarray, names: list[str]) -> dict:
    """DI referansi (ML-2'de kullanilir): ozellik basina min/max/ortalama/std (NaN'lar atilir)."""
    out = {}
    for j, nm in enumerate(names):
        c = X[:, j]
        c = c[np.isfinite(c)]
        out[nm] = ({"min": float(c.min()), "max": float(c.max()), "mean": float(c.mean()), "std": float(c.std())}
                   if len(c) else None)
    return out


def build_package(model: dict, calibration: dict, threshold: float | None, names: list[str], X_train: np.ndarray,
                  train_start, train_end, dhash: str, *, version: str = RECIPE_ID, created_at: datetime | None = None,
                  extra: dict | None = None) -> dict:
    created = created_at or datetime.now(timezone.utc)
    body = {"model": model, "calibration": calibration, "threshold": None if threshold is None else float(threshold)}
    meta = {
        "pkg_version": PKG_VERSION, "version": version, "kind": model["kind"],
        "created_at": created.isoformat(), "expires_at": (created + timedelta(days=MODEL_EXPIRY_DAYS)).isoformat(),
        "expiry_days": MODEL_EXPIRY_DAYS,
        "features": list(names), "feature_list_hash": feature_list_hash(names),
        "feature_ranges": feature_ranges(X_train, names),
        "train_window": {"start": pd.Timestamp(train_start).isoformat(), "end": pd.Timestamp(train_end).isoformat()},
        "n_train": int(len(X_train)), "data_hash": dhash, "code_hash": code_hash(),
        "model_hash": sha256_text(canon(body)),
    }
    if extra:
        meta.update(extra)
    return {"meta": meta, **body}


def save_package(pkg: dict, path: str | Path) -> Path:
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(pkg, sort_keys=True, allow_nan=False), encoding="utf-8")
    return p


class PackageError(ValueError):
    pass


def load_package(path: str | Path | dict, *, now: datetime | None = None, check_expiry: bool = True) -> dict:
    """Okur, hash'leri dogrular (tutmuyorsa PackageError), suresi dolmussa PackageError."""
    pkg = path if isinstance(path, dict) else json.loads(Path(path).read_text(encoding="utf-8"))
    meta = pkg["meta"]
    body = {"model": pkg["model"], "calibration": pkg["calibration"], "threshold": pkg["threshold"]}
    if sha256_text(canon(body)) != meta["model_hash"]:
        raise PackageError("model hash tutmuyor")
    if feature_list_hash(meta["features"]) != meta["feature_list_hash"]:
        raise PackageError("ozellik listesi hash tutmuyor")
    if check_expiry and is_expired(pkg, now):
        raise PackageError("model suresi dolmus")
    return pkg


def is_expired(pkg: dict, now: datetime | None = None) -> bool:
    now = now or datetime.now(timezone.utc)
    return now >= datetime.fromisoformat(pkg["meta"]["expires_at"])
