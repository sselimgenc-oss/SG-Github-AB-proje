"""WP-B2 gerceklestirme duman testleri (11 §3): kipler, live blogu, LIVE_CONFIRM, keys_missing, cikis kodu 8."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from trader_core.risk import LOCKED_CFG
from trader_engine import cli
from trader_engine.config import apply_overrides, load_engine_config, load_keys
from trader_engine.engine import EngineExit
from trader_engine.errors import ConfigError

ROOT = Path(__file__).resolve().parents[2]
CFG = ROOT / "config"
LIVE = {"account_tag": "sub-acct-1", "expected_wallet_max": 1500.0}
GOOD = "A" * 32


def _base(**kw):
    return apply_overrides(load_engine_config(CFG / "engine.base.json", CFG / "engine.learner.json"), **kw)


def test_paper_unchanged():
    c = _base()
    assert c.mode == "paper" and c.live is None and c.leverage == LOCKED_CFG.min_leverage == 3


def test_testnet_overlay_loads():
    c = load_engine_config(CFG / "engine.base.json", CFG / "engine.learner.json", overlay_path=CFG / "engine.testnet.json")
    assert c.mode == "testnet" and c.live is not None and c.var_dir == "var-testnet"


def test_live_block_required_and_forbidden():
    for m in ("testnet", "live"):
        with pytest.raises(ConfigError):
            _base(mode=m)
        assert _base(mode=m, live=LIVE).live.account_tag == "sub-acct-1"
    with pytest.raises(ConfigError):
        _base(live=LIVE)
    with pytest.raises(ConfigError):
        _base(mode="testnet", live={**LIVE, "account_tag": "X"})
    with pytest.raises(ConfigError):
        _base(mode="testnet", live={**LIVE, "stop_deadline_s": 16})


def test_leverage_range():
    assert _base(leverage=5).leverage == 5
    for v in (2, 6, True, 3.5):
        with pytest.raises(ConfigError):
            _base(leverage=v)


def test_live_rules():
    with pytest.raises(ConfigError):
        _base(mode="live", bot="twin", live=LIVE)
    assert _base(mode="testnet", bot="twin", live=LIVE).mode == "testnet"
    with pytest.raises(ConfigError):
        _base(mode="live", live=LIVE, cost={"trigger_source": "last"})


def _write_live(tmp_path, tag="sub-acct-1"):
    p = tmp_path / "live.json"
    p.write_text(json.dumps({"mode": "live", "live": {**LIVE, "account_tag": tag}}))
    return p


def test_live_confirm(tmp_path):
    p = _write_live(tmp_path)
    args = (CFG / "engine.base.json", CFG / "engine.learner.json")
    assert load_engine_config(*args, overlay_path=p, env={"LIVE_CONFIRM": "sub-acct-1"}).mode == "live"
    for env in ({}, {"LIVE_CONFIRM": "sub-acct-2"}, {"LIVE_CONFIRM": ""}):
        with pytest.raises(ConfigError, match="live_confirm"):
            load_engine_config(*args, overlay_path=p, env=env)


def test_load_keys():
    assert load_keys({"BINANCE_API_KEY": GOOD, "BINANCE_API_SECRET": "B" * 40}) == (GOOD, "B" * 40)
    for env in ({}, {"BINANCE_API_KEY": GOOD}, {"BINANCE_API_KEY": GOOD, "BINANCE_API_SECRET": "short"},
                {"BINANCE_API_KEY": GOOD, "BINANCE_API_SECRET": "B" * 20 + " " + "B" * 20},
                {"BINANCE_API_KEY": "", "BINANCE_API_SECRET": GOOD}):
        with pytest.raises(ConfigError, match="keys_missing"):
            load_keys(env)


def _run(monkeypatch, env, checker=None):
    for k in ("BINANCE_API_KEY", "BINANCE_API_SECRET", "LIVE_CONFIRM"):
        monkeypatch.delenv(k, raising=False)
    for k, v in env.items():
        monkeypatch.setenv(k, v)
    a = cli.build_parser().parse_args(["run", "--bot", "learner", "--env", "testnet", "--config-dir", str(CFG)])
    return cli._cmd_run(a, checker=checker)


def test_cli_exit_codes(monkeypatch):
    assert cli.EXIT_PERMISSION == 8
    assert _run(monkeypatch, {}) == cli.EXIT_FAZ_B                      # keys_missing
    keys = {"BINANCE_API_KEY": GOOD, "BINANCE_API_SECRET": GOOD}
    assert _run(monkeypatch, keys) == cli.EXIT_FAZ_B                    # broker yok

    def refuse(cfg, k, s):
        raise EngineExit(8, "key_permission:enableWithdrawals")
    assert _run(monkeypatch, keys, checker=refuse) == 8
    seen = []
    assert _run(monkeypatch, keys, checker=lambda c, k, s: seen.append(c.mode)) == cli.EXIT_FAZ_B and seen == ["testnet"]
