"""ML golge deneyi: `init-ledger --reason strategy_update` yalniz strateji etiketini tasir (params ayni)."""
import json
import shutil
from pathlib import Path

from trader_core import ledger as L
from trader_engine import cli
from trader_engine.strategies.registry import parse_label

ROOT = Path(__file__).resolve().parents[2]


def _cfgdir(tmp_path):
    d = tmp_path / "config"
    shutil.copytree(ROOT / "config", d)
    base = json.loads((d / "engine.base.json").read_text())
    base["var_dir"] = str(tmp_path / "var")
    (d / "engine.base.json").write_text(json.dumps(base))
    return d


def _run(d, *extra):
    return cli.main(["init-ledger", "--bot", "learner", "--config-dir", str(d), *extra])


def _active(tmp_path):
    led = L.open_ledger(str(tmp_path / "var" / "learner" / "ledger.sqlite"), "learner", create=False, read_only=True)
    try:
        a = led.get_active_params()
        return a, led.get_version(a.version_id).reason
    finally:
        led.close()


def test_strategy_update_moves_label_keeps_params_hash(tmp_path, capsys):
    d = _cfgdir(tmp_path)
    assert _run(d) == 0
    a0, r0 = _active(tmp_path)
    assert parse_label(r0)[0] == "price_action_v1"
    assert _run(d, "--env", "paper") == 0                 # strategy_update degil: dokunulmaz
    a1, r1 = _active(tmp_path)
    assert a1.version_id == a0.version_id
    assert _run(d, "--env", "paper", "--reason", "strategy_update") == 0
    a2, r2 = _active(tmp_path)
    assert parse_label(r2)[0] == "price_action_lab_ml"   # DD-12 WP-11: engine.paper.json strategy
    assert a2.version_id != a0.version_id and a2.params_hash == a0.params_hash
    assert _run(d, "--env", "paper", "--reason", "strategy_update") == 0   # tekrar: degisiklik yok
    a3, _ = _active(tmp_path)
    assert a3.version_id == a2.version_id
    assert "zaten" in capsys.readouterr().out
    assert _run(d, "--reason", "strategy_update") == 0       # geri donus de mumkun
    a4, r4 = _active(tmp_path)
    assert parse_label(r4)[0] == "price_action_v1" and a4.params_hash == a0.params_hash


def test_create_user_version_same_params_still_rejected_by_default(tmp_path):
    led = L.open_ledger(str(tmp_path / "l.sqlite"), "learner", create=True)
    try:
        from trader_core.signals import DEFAULT_SIGNAL_PARAMS
        p = {k: getattr(DEFAULT_SIGNAL_PARAMS, k) for k in L.PARAM_KEYS}
        led.init_params(p, reason="strategy:price_action_v1@1b.0 ilk")
        try:
            led.create_user_version(p, reason="x")
            raise AssertionError("no_change bekleniyordu")
        except L.LedgerValidationError as e:
            assert "no_change" in str(e)
    finally:
        led.close()
