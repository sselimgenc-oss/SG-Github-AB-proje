"""05 §4.2/§8: `target_trade_risk` yapilandirmasi yalniz LOCKED_CFG'den SIKI olabilir (fail-closed), twin ve learner
ayni RiskConfig'i kullanir ve boyutlama bunu yansitir."""
from __future__ import annotations

import json
import math
from pathlib import Path

import pytest

from trader_core import risk as K
from trader_engine.config import apply_overrides, build_risk_config, load_engine_config
from trader_engine.errors import ConfigError

from test_engine_05_spec import BTC, Env, ROOT, T0, make_cfg


def test_default_is_locked_target(tmp_path):
    cfg = make_cfg(tmp_path)
    assert cfg.target_trade_risk == K.LOCKED_CFG.target_trade_risk == 0.014
    assert cfg.risk_config == K.LOCKED_CFG


def test_tighter_target_builds_only_target_differs(tmp_path):
    rc = make_cfg(tmp_path, target_trade_risk=0.005).risk_config
    assert rc.target_trade_risk == 0.005
    assert rc == K.tightened(K.LOCKED_CFG, target_trade_risk=0.005)
    for f in ("max_trade_risk", "daily_max_loss", "max_open_risk", "max_same_dir_risk", "min_leverage",
              "max_leverage", "liq_safety_factor", "max_notional_ratio", "fee_rate", "slippage_rate"):
        assert getattr(rc, f) == getattr(K.LOCKED_CFG, f)


@pytest.mark.parametrize("bad", [0.015, 0.02, 1.0, 0, 0.0, -0.005, float("nan"), float("inf"), True, "0.005", None])
def test_loose_or_invalid_target_is_config_error(tmp_path, bad):
    with pytest.raises(ConfigError):
        make_cfg(tmp_path, target_trade_risk=bad)
    with pytest.raises(ConfigError):
        build_risk_config(bad)


def test_apply_overrides_cannot_loosen(tmp_path):
    cfg = make_cfg(tmp_path, target_trade_risk=0.005)
    assert apply_overrides(cfg, target_trade_risk=0.01).risk_config.target_trade_risk == 0.01
    with pytest.raises(ConfigError):
        apply_overrides(cfg, target_trade_risk=0.0141)


def test_twin_and_learner_share_same_risk_config(tmp_path):
    raw = json.loads((ROOT / "config" / "engine.base.json").read_text())
    raw.update(target_trade_risk=0.005, var_dir=str(tmp_path / "var"))
    base = tmp_path / "base.json"
    base.write_text(json.dumps(raw))
    cfgs = {}
    for name in ("learner", "twin"):
        ov = tmp_path / f"{name}.json"
        ov.write_text((ROOT / "config" / f"engine.{name}.json").read_text())
        cfgs[name] = load_engine_config(base, ov)
    assert cfgs["learner"].risk_config == cfgs["twin"].risk_config
    assert cfgs["learner"].risk_config.target_trade_risk == 0.005


def test_shipped_configs_keep_locked_default():
    for name in ("engine.base.json", "engine.learner.json", "engine.twin.json"):
        assert "target_trade_risk" not in json.loads((ROOT / "config" / name).read_text())


def _entry_risk(tmp_path: Path, **over) -> float:
    e = Env(tmp_path, **over)
    e.start()
    e.signal(T0)
    e.decide(T0)
    d = e.decisions()[0]
    assert d.final_action == "entered" and d.risk_allowed is True
    risk_amount = d.size_risk_amount
    e.close()
    return risk_amount


def test_sizing_follows_configured_target(tmp_path):
    (tmp_path / "a").mkdir()
    (tmp_path / "b").mkdir()
    base = _entry_risk(tmp_path / "a")
    tight = _entry_risk(tmp_path / "b", target_trade_risk=0.005)
    assert base == pytest.approx(13.999, rel=1e-3)
    assert tight == pytest.approx(5.0, rel=2e-2) and tight < 0.005 * 1000.0 + 1e-9
    assert math.isclose(tight / base, 0.005 / 0.014, rel_tol=3e-2)
