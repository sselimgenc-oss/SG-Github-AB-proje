"""Kurulum suzgeci paketi: JSON + sha256 (trader_core.ml_package ile ayni dogrulama), bir surum yedek, atomik yazim."""
from __future__ import annotations

import hashlib
import json
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path

from trader_core.ml_package import (MODEL_EXPIRY_DAYS, canon, feature_list_hash, load_package, safe_arm_name,  # noqa: F401
                                    sha256_text)

PKG_VERSION = 1
KIND = "setup_filter"


def build_package(arm_id: str, model: dict, threshold: float, names: list[str], *, train_start, train_end, n_train: int,
                  n_pos: int, data_hash: str, lock_dropped: int, base_rate: float, lesson_ids: list[str],
                  created_at: datetime | None = None) -> dict:
    created = created_at or datetime.now(timezone.utc)
    calibration = {"a": 1.0, "b": 0.0}
    body = {"model": model, "calibration": calibration, "threshold": float(threshold)}
    meta = {
        "pkg_version": PKG_VERSION, "version": f"{KIND}-{PKG_VERSION}", "kind": KIND, "arm_id": arm_id,
        "created_at": created.isoformat(), "expires_at": (created + timedelta(days=MODEL_EXPIRY_DAYS)).isoformat(),
        "expiry_days": MODEL_EXPIRY_DAYS, "features": list(names), "feature_list_hash": feature_list_hash(names),
        "train_window": {"start": None if train_start is None else train_start.isoformat(),
                         "end": None if train_end is None else train_end.isoformat()},
        "n_train": int(n_train), "n_pos": int(n_pos), "base_rate": float(base_rate), "data_hash": data_hash,
        "lock_dropped": int(lock_dropped), "lesson_ids": sorted(lesson_ids),
        "model_hash": sha256_text(canon(body)),
        # Kapi kosulu kagitta aranmaz (spec 5); paket yalniz kagit motorunda yuklenir (testnet/canli: paper_only reddi).
        "gate_passed": True, "paper_only": True, "user_approved": True,
    }
    return {"meta": meta, **body}


def data_hash_of(rows) -> str:
    h = hashlib.sha256()
    for r in rows:
        h.update(f"{r['ts'].isoformat()}|{r['r']:.8f}|".encode())
    return h.hexdigest()


def save_package(pkg: dict, models_dir: str | Path) -> Path:
    """models_dir/<arm>.json; eski dosya `<arm>.prev.json` olur (tek surum yedek). Atomik (tmp + os.replace)."""
    d = Path(models_dir)
    d.mkdir(parents=True, exist_ok=True)
    name = safe_arm_name(pkg["meta"]["arm_id"])
    cur, prev, tmp = d / f"{name}.json", d / f"{name}.prev.json", d / f".{name}.json.tmp"
    tmp.write_text(json.dumps(pkg, sort_keys=True, allow_nan=False), encoding="utf-8")
    load_package(tmp)                                  # gidis-donus: hash + ozellik hash + sure
    if cur.exists():
        os.replace(cur, prev)
    os.replace(tmp, cur)
    return cur
