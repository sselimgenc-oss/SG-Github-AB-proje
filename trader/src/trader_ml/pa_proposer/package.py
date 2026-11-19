"""M1 paketi: JSON + sha256 (trader_core.ml_package ile ayni dogrulama), tek surum yedek, atomik yazim (WP-10 deseni)."""
from __future__ import annotations

import json
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path

from trader_core.ml_package import (MODEL_EXPIRY_DAYS, canon, feature_list_hash, load_package, safe_arm_name,  # noqa: F401
                                    sha256_text)

from . import features as F

PKG_VERSION = 1
KIND = "pa_proposer"


def build_package(arm_id: str, model: dict, threshold: float, names: list[str], *, train_start, train_end, n_train: int,
                  n_pos: int, data_hash: str, lock_dropped: int, base_rate: float, created_at: datetime | None = None) -> dict:
    created = created_at or datetime.now(timezone.utc)
    body = {"model": model, "calibration": {"a": 1.0, "b": 0.0}, "threshold": float(threshold)}
    meta = {
        "pkg_version": PKG_VERSION, "version": f"{KIND}-{PKG_VERSION}", "kind": KIND, "arm_id": arm_id,
        "created_at": created.isoformat(), "expires_at": (created + timedelta(days=MODEL_EXPIRY_DAYS)).isoformat(),
        "expiry_days": MODEL_EXPIRY_DAYS, "features": list(names), "feature_list_hash": feature_list_hash(names),
        "window": F.WINDOW, "label": {"stop_atr": F.STOP_ATR, "target_atr": F.TARGET_ATR, "horizon": F.HORIZON},
        "threshold_quantile": 0.98,
        "train_window": {"start": None if train_start is None else train_start.isoformat(),
                         "end": None if train_end is None else train_end.isoformat()},
        "n_train": int(n_train), "n_pos": int(n_pos), "base_rate": float(base_rate), "data_hash": data_hash,
        "lock_dropped": int(lock_dropped), "model_hash": sha256_text(canon(body)),
        # Kapi kosulu kagitta aranmaz (spec 5); paket yalniz kagit motorunda yuklenir.
        "gate_passed": True, "paper_only": True, "user_approved": True,
    }
    return {"meta": meta, **body}


def save_package(pkg: dict, models_dir: str | Path) -> Path:
    """models_dir/<arm_id>.json; onceki dosya <arm>.prev.json olur. Atomik (tmp + os.replace); yazmadan once yeniden dogrulanir."""
    d = Path(models_dir)
    d.mkdir(parents=True, exist_ok=True)
    name = safe_arm_name(pkg["meta"]["arm_id"])
    cur, prev, tmp = d / f"{name}.json", d / f"{name}.prev.json", d / f".{name}.json.tmp"
    tmp.write_text(json.dumps(pkg, sort_keys=True, allow_nan=False), encoding="utf-8")
    load_package(tmp)
    if cur.exists():
        os.replace(cur, prev)
    os.replace(tmp, cur)
    return cur
