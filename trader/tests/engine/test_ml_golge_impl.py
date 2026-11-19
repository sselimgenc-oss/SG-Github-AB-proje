"""ML golge deneyi (G-1..G-5) uygulama duman testleri."""
from __future__ import annotations

import copy
import json
from datetime import datetime, timezone
from pathlib import Path

import pytest

from trader_core.ml_live_v2 import RECIPE_NAMES
from trader_core.ml_package import PackageError, load_model_view
from trader_engine.config import load_cli_config, load_engine_config
from trader_engine.errors import ConfigError
from trader_engine.strategies.price_action_v1_ml import load_engine_model

ROOT = Path(__file__).resolve().parents[2]
SRC = ROOT / "research/ml/r03/model_candidate.json"
NOW = datetime(2026, 11, 18, tzinfo=timezone.utc)
F = RECIPE_NAMES["r03"]


def test_learner_config_and_model_copy():
    c = load_cli_config(ROOT / "config", "learner", "paper")
    # 19 Kasim: r03 kagitta emekli (kullanici karari); paper ML kapali, eski anahtarlar yok
    assert (c.strategy, c.ml_mode, c.ml_features, c.ml_experimental) == ("price_action_lab_ml", "off", "v1", False)
    assert c.ml_model_path is None and c.ml_pairs == ()
    assert not (ROOT / "config/engine.paper-ml.json").exists()
    assert (ROOT / "models/ml1-r03.json").read_bytes() == SRC.read_bytes()
    for n in ("base", "testnet", "live"):
        assert "ml_experimental" not in json.loads((ROOT / f"config/engine.{n}.json").read_text())
    with pytest.raises(ConfigError):                               # ikiz kaldirildi
        load_cli_config(ROOT / "config", "twin")


@pytest.mark.parametrize("mode,ml,ok", [("paper", "shadow", True), ("paper", "off", False), ("paper", "active", False)])
def test_config_lock(tmp_path, mode, ml, ok):
    base = json.loads((ROOT / "config/engine.base.json").read_text())
    base.update({"bot": "learner", "ml_mode": ml, "ml_experimental": True, "mode": mode})
    p = tmp_path / "b.json"
    p.write_text(json.dumps(base))
    if ok:
        assert load_engine_config(p).ml_experimental is True
    else:
        with pytest.raises(ConfigError, match="paper\\+shadow"):
            load_engine_config(p)
    base.update({"bot": "learner", "ml_mode": "shadow", "ml_experimental": "yes", "mode": "paper"})
    p.write_text(json.dumps(base))
    with pytest.raises(ConfigError):
        load_engine_config(p)


def test_load_experimental_gate_hash_expiry(tmp_path):
    with pytest.raises(PackageError):
        load_model_view(SRC, expected_features=F, ml_mode="shadow", now=NOW)           # kapi reddi (varsayilan)
    v = load_model_view(SRC, expected_features=F, ml_mode="shadow", now=NOW, experimental=True)
    assert v.experimental is True and v.threshold == 0.5
    with pytest.raises(ValueError):
        load_model_view(SRC, expected_features=F, ml_mode="active", now=NOW, experimental=True)
    assert load_engine_model(str(SRC), "active", NOW, F, experimental=True)[0] is None
    late = datetime(2026, 12, 9, 16, tzinfo=timezone.utc)
    assert load_engine_model(str(SRC), "shadow", late, F, experimental=True)[0] is None
    bad = copy.deepcopy(json.loads(SRC.read_text()))
    bad["meta"]["model_hash"] = "0" * 64
    q = tmp_path / "bad.json"
    q.write_text(json.dumps(bad))
    assert load_engine_model(str(q), "shadow", NOW, F, experimental=True)[0] is None
    assert load_engine_model(str(SRC), "shadow", NOW, F, experimental=True)[1] is None
