"""Motor tarafi agac okuyucusu == LightGBM (1e-9) ve paket butunlugu."""
import copy
import json
from datetime import datetime, timedelta, timezone

import numpy as np
import pytest

lgb = pytest.importorskip("lightgbm")

from trader_ml import models
from trader_ml.package import PackageError, build_package, is_expired, load_package, save_package
from trader_ml.schema import feature_columns
from trader_ml.treeeval import TreeModel


@pytest.fixture(scope="module")
def data(table):
    names = feature_columns(table)
    X, y = table[names].to_numpy(float), table["label"].to_numpy(float)
    k = int(len(X) * 0.7)
    return names, X, y, k


@pytest.fixture(scope="module")
def booster(data):
    names, X, y, k = data
    b, _ = models.fit_lgbm(X[:k], y[:k], np.ones(k))
    return b


def test_parity_heldout_raw_and_proba(data, booster):
    names, X, y, k = data
    held = X[k:]
    m = TreeModel(models.lgbm_dump(booster))
    assert np.max(np.abs(m.predict_raw(held) - booster.predict(held, raw_score=True))) <= 1e-9
    assert np.max(np.abs(m.predict_uncalibrated(held) - booster.predict(held))) <= 1e-9


def test_parity_after_json_roundtrip_and_deeper_trees(data):
    names, X, y, k = data
    p = {"objective": "binary", "max_depth": 6, "num_leaves": 31, "min_data_in_leaf": 5, "verbosity": -1,
         "learning_rate": 0.1, "num_threads": 1}
    b = lgb.train(p, lgb.Dataset(X[:k], label=y[:k]), num_boost_round=40)
    dump = json.loads(json.dumps(models.lgbm_dump(b)))
    m = TreeModel(dump)
    assert np.max(np.abs(m.predict_raw(X[k:]) - b.predict(X[k:], raw_score=True))) <= 1e-9
    assert m.predict_one(X[k]) == pytest.approx(float(1 / (1 + np.exp(-b.predict(X[k:k + 1], raw_score=True)[0]))), abs=1e-9)


def test_parity_with_missing_values(data, booster):
    names, X, y, k = data
    held = X[k:].copy()
    rng = np.random.default_rng(1)
    held[rng.random(held.shape) < 0.3] = np.nan
    m = TreeModel(models.lgbm_dump(booster))
    assert np.max(np.abs(m.predict_raw(held) - booster.predict(held, raw_score=True))) <= 1e-9


def test_parity_with_zero_as_missing_and_nan_training(data):
    names, X, y, k = data
    Xn = X.copy()
    Xn[::7, 3] = np.nan
    b = lgb.train({"objective": "binary", "max_depth": 4, "min_data_in_leaf": 20, "verbosity": -1,
                   "zero_as_missing": True, "num_threads": 1}, lgb.Dataset(Xn[:k], label=y[:k]), 20)
    m = TreeModel(models.lgbm_dump(b))
    held = Xn[k:].copy()
    held[::5, 4] = 0.0
    assert np.max(np.abs(m.predict_raw(held) - b.predict(held, raw_score=True))) <= 1e-9


def test_logistic_evaluator_matches_training_side(data):
    names, X, y, k = data
    lg = models.fit_logistic(X[:k], y[:k], np.ones(k))
    got = TreeModel(lg).predict_raw(X[k:])
    assert np.max(np.abs(got - models.logistic_predict_raw(lg, X[k:]))) <= 1e-9


def test_package_roundtrip_hash_and_expiry(data, booster, tmp_path):
    names, X, y, k = data
    t0 = datetime(2026, 11, 20, tzinfo=timezone.utc)
    pkg = build_package(models.lgbm_dump(booster), {"a": 1.0, "b": 0.0}, 0.5, names, X[:k], "2025-01-01",
                        "2026-04-30", "d" * 64, created_at=t0)
    assert pkg["meta"]["expiry_days"] == 21
    assert datetime.fromisoformat(pkg["meta"]["expires_at"]) - t0 == timedelta(days=21)
    assert pkg["meta"]["feature_list_hash"] and len(pkg["meta"]["features"]) == len(names)
    assert "pickle" not in json.dumps(pkg).lower()
    path = save_package(pkg, tmp_path / "m.json")
    loaded = load_package(path, now=t0 + timedelta(days=20))
    m = TreeModel(loaded["model"], loaded["calibration"])
    assert np.max(np.abs(m.predict_raw(X[k:]) - booster.predict(X[k:], raw_score=True))) <= 1e-9
    assert is_expired(loaded, t0 + timedelta(days=21))
    with pytest.raises(PackageError):
        load_package(path, now=t0 + timedelta(days=22))
    bad = copy.deepcopy(pkg)
    bad["threshold"] = 0.6
    with pytest.raises(PackageError, match="hash"):
        load_package(bad, now=t0)
    bad = copy.deepcopy(pkg)
    bad["meta"]["features"] = bad["meta"]["features"][::-1]
    with pytest.raises(PackageError, match="hash"):
        load_package(bad, now=t0)
