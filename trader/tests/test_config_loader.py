import json
from pathlib import Path

import pytest

from trader_core.config_loader import ConfigError, deep_merge, load_config, validate

ROOT = Path(__file__).resolve().parent.parent
CFG = ROOT / "config"


def good():
    return {"trading_mode": "futures", "margin_mode": "isolated", "dry_run": True,
            "exchange": {"key": "", "secret": ""}}


def test_deep_merge_nested_and_no_mutation():
    base = {"a": {"x": 1, "y": 2}, "l": [1, 2]}
    out = deep_merge(base, {"a": {"y": 3}, "l": [9]})
    assert out == {"a": {"x": 1, "y": 3}, "l": [9]}
    assert base == {"a": {"x": 1, "y": 2}, "l": [1, 2]}


@pytest.mark.parametrize("name", ["learner", "twin"])
def test_real_configs_valid_and_bot_name(name):
    cfg = load_config(CFG / "base.json", CFG / f"{name}.json")
    assert cfg["bot_name"] == name
    assert cfg["dry_run"] is True


def test_bot_names_differ():
    a = load_config(CFG / "base.json", CFG / "learner.json")["bot_name"]
    b = load_config(CFG / "base.json", CFG / "twin.json")["bot_name"]
    assert a != b


def test_valid_passes():
    validate(good())


@pytest.mark.parametrize("field,value", [
    ("trading_mode", "spot"), ("margin_mode", "cross"), ("dry_run", False)])
def test_invariant_violations(field, value):
    cfg = good()
    cfg[field] = value
    with pytest.raises(ConfigError):
        validate(cfg)


def test_live_flag_allows_non_dry_run():
    cfg = good()
    cfg["dry_run"] = False
    validate(cfg, allow_live=True)


@pytest.mark.parametrize("field", ["key", "secret"])
def test_secret_in_file_rejected(field):
    cfg = good()
    cfg["exchange"][field] = "abc"
    with pytest.raises(ConfigError):
        validate(cfg)


def test_override_cannot_break_invariant(tmp_path):
    over = tmp_path / "o.json"
    over.write_text(json.dumps({"dry_run": False}))
    with pytest.raises(ConfigError):
        load_config(CFG / "base.json", over)
