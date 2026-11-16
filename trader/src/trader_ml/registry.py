"""Deneme defteri (DSR n_trials kurali): n_trials = KAYITLI tarif sayisi x model sayisi (2: lojistik, LightGBM).

Defter `research/ml_trial_registry.csv`: her satir bir denenmis tarif (RECIPE_ID). Yeni tarif denenmeden
once satir eklenir; satir silinmez. Boylece DSR'nin ceza terimi sessizce kucultulemez.
"""
from __future__ import annotations

import csv
from pathlib import Path

from .config import RECIPE_ID

MODELS_PER_RECIPE = 2
DEFAULT_REGISTRY = Path(__file__).resolve().parents[2] / "research" / "ml_trial_registry.csv"


class RegistryError(ValueError):
    pass


def n_trials_from_registry(path: str | Path = DEFAULT_REGISTRY, *, recipe_id: str = RECIPE_ID) -> int:
    p = Path(path)
    if not p.exists():
        raise RegistryError(f"deneme defteri yok: {p}")
    with p.open(encoding="utf-8", newline="") as fh:
        ids = [r["recipe_id"].strip() for r in csv.DictReader(fh) if (r.get("recipe_id") or "").strip()]
    if len(set(ids)) != len(ids):
        raise RegistryError("deneme defterinde tekrarli tarif")
    if recipe_id not in ids:
        raise RegistryError(f"tarif {recipe_id!r} defterde kayitli degil")
    return len(ids) * MODELS_PER_RECIPE
