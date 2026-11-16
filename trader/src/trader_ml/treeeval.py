"""Kendi agac degerlendiricimiz (§3, §5): LightGBM JSON dokumunu (Booster.dump_model) ve lojistik
paketini okur; YALNIZ numpy. lightgbm/sklearn/scipy/pandas import ETMEZ (motor tarafina tasinabilir).

Kurallar (LightGBM ile bire bir): karar `x <= esik` -> sol; NaN/0 isleme missing_type'a gore:
None -> NaN 0.0'a doner; Zero -> NaN ya da |x|<=1e-35 varsayilan yone; NaN -> NaN varsayilan yone.
Ikili hedef: p = sigmoid(sum(yaprak)). Kategorik bolme desteklenmez (kullanmiyoruz) -> hata.
"""
from __future__ import annotations

import math

import numpy as np

_ZERO = 1e-35


def _sigmoid(z):
    z = np.asarray(z, dtype=np.float64)
    out = np.empty_like(z)
    pos = z >= 0
    out[pos] = 1.0 / (1.0 + np.exp(-z[pos]))
    e = np.exp(z[~pos])
    out[~pos] = e / (1.0 + e)
    return out


class _Tree:
    """Duz dizilere acilmis tek agac. Dugum kodu: >= 0 ic dugum, < 0 yaprak (-(idx+1))."""

    def __init__(self, structure: dict):
        feat, thr, left, right, dleft, mtype, leaves = [], [], [], [], [], [], []
        mt = {"None": 0, "Zero": 1, "NaN": 2}

        def walk(node) -> int:
            if "leaf_index" in node or "split_index" not in node:
                leaves.append(float(node["leaf_value"]))
                return -len(leaves)
            if node.get("decision_type", "<=") != "<=":
                raise ValueError(f"desteklenmeyen decision_type: {node.get('decision_type')}")
            i = len(feat)
            feat.append(int(node["split_feature"])); thr.append(float(node["threshold"]))
            dleft.append(bool(node["default_left"])); mtype.append(mt[node["missing_type"]])
            left.append(0); right.append(0)
            left[i] = walk(node["left_child"])
            right[i] = walk(node["right_child"])
            return i

        self.root = walk(structure)
        self.feat = np.asarray(feat, dtype=np.int64)
        self.thr = np.asarray(thr, dtype=np.float64)
        self.left = np.asarray(left, dtype=np.int64)
        self.right = np.asarray(right, dtype=np.int64)
        self.dleft = np.asarray(dleft, dtype=bool)
        self.mtype = np.asarray(mtype, dtype=np.int64)
        self.leaves = np.asarray(leaves, dtype=np.float64)

    def predict(self, X: np.ndarray) -> np.ndarray:
        n = X.shape[0]
        if self.root < 0:
            return np.full(n, self.leaves[-self.root - 1])
        node = np.full(n, self.root, dtype=np.int64)
        for _ in range(len(self.feat) + 1):
            act = node >= 0
            if not act.any():
                break
            nd = node[act]
            x = X[act, self.feat[nd]]
            nan = np.isnan(x)
            mt = self.mtype[nd]
            x = np.where(nan & (mt != 2), 0.0, x)                     # missing_type != NaN: NaN -> 0
            missing = ((mt == 2) & nan) | ((mt == 1) & (np.abs(x) <= _ZERO))
            go_left = np.where(missing, self.dleft[nd], x <= self.thr[nd])
            node[act] = np.where(go_left, self.left[nd], self.right[nd])
        return self.leaves[-node - 1]


class TreeModel:
    """kind='lgbm' (agac dokumu) ya da 'logistic'. predict_raw -> marj, predict_proba -> kalibre."""

    def __init__(self, model: dict, calibration: dict | None = None):
        self.kind = model["kind"]
        self.n_features = int(model["n_features"])
        self.calibration = calibration or {"a": 1.0, "b": 0.0}
        if self.kind == "lgbm":
            self.trees = [_Tree(t["tree_structure"]) for t in model["tree_info"]]
        elif self.kind == "logistic":
            self.coef = np.asarray(model["coef"], dtype=np.float64)
            self.intercept = float(model["intercept"])
            self.mean = np.asarray(model["mean"], dtype=np.float64)
            self.std = np.asarray(model["std"], dtype=np.float64)
            self.fill = np.asarray(model["fill"], dtype=np.float64)
        else:
            raise ValueError(f"bilinmeyen model turu: {self.kind}")

    def _check(self, X) -> np.ndarray:
        X = np.atleast_2d(np.asarray(X, dtype=np.float64))
        if X.shape[1] != self.n_features:
            raise ValueError(f"ozellik sayisi {X.shape[1]} != {self.n_features}")
        return X

    def predict_raw(self, X) -> np.ndarray:
        X = self._check(X)
        if self.kind == "lgbm":
            z = np.zeros(X.shape[0])
            for t in self.trees:
                z += t.predict(X)
            return z
        Xf = np.where(np.isnan(X), self.fill, X)
        return ((Xf - self.mean) / self.std) @ self.coef + self.intercept

    def predict_uncalibrated(self, X) -> np.ndarray:
        return _sigmoid(self.predict_raw(X))

    def predict_proba(self, X) -> np.ndarray:
        z = self.predict_raw(X)
        return _sigmoid(self.calibration["a"] * z + self.calibration["b"])

    def predict_one(self, row) -> float:
        return float(self.predict_proba(np.asarray(row, dtype=np.float64)[None, :])[0])
