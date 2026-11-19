"""DD-12 WP-07 uygulayici duman testleri (ikiz kaldirma)."""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DEPLOY = ROOT / "deploy"


def _t(rel):
    return (ROOT / rel).read_text(encoding="utf-8")


def test_install_has_no_twin_options_and_archives_var_twin():
    t = _t("deploy/install.sh")
    assert "--with-twin" not in t and "--no-twin" not in t and "WITH_TWIN" not in t
    assert "TRADER_ML_SHADOW" not in t and "ml-shadow" not in t
    assert 'HEALTH_BOTS_VAL="learner"' in t
    for u in ("trader-engine@twin.service", "trader-engine-retry@twin.timer", "trader-counterfactual@twin.timer",
              "trader-drift@twin.timer"):
        assert u in t
    assert "var/arsiv/twin-" in t and 'mv "$TRADER_DIR/var/twin"' in t and "rm -rf \"$TRADER_DIR/var/twin" not in t
    assert not (DEPLOY / "trader-engine@learner.service.d").exists()
    assert subprocess.run(["bash", "-n", str(DEPLOY / "install.sh")]).returncode == 0


def test_units_paper_env_and_ceilings():
    e = _t("deploy/trader-engine@.service")
    assert e.count("--env paper") == 2
    assert "MemoryHigh=600M" in e and "MemoryMax=750M" in e
    f = _t("deploy/trader-feed.service")
    assert "--env paper" in f and "MemoryHigh=200M" in f and "MemoryMax=260M" in f


def test_env_examples_learner_only():
    assert "HEALTH_BOTS=learner\n" in _t("deploy/trader-health.env.example")
    assert "PAUSE_BOTS=learner\n" in _t("deploy/trader-telegram.env.example")
    for rel in ("deploy/trader-telegram.env.example", "deploy/trader-lesson.env.example"):
        assert "TWIN_LEDGER_PATH" not in _t(rel)


def test_health_defaults_and_env_filter():
    sys.path.insert(0, str(ROOT / "scripts"))
    import health_run as H
    from trader_core.health import HealthConfig
    assert H.DEFAULT_BOTS == ("learner",) and HealthConfig().require_bots == ("learner",)
    assert H.bots_from_env({}) == ("learner",)
    assert H.bots_from_env({"HEALTH_BOTS": "learner"}) == ("learner",)


def test_panel_config_has_no_twin_and_panel_is_single_bot():
    raw = json.loads(_t("config/panel.json"))
    assert not [k for k in raw if "twin" in k] and raw["max_concurrent"] == 16
    from trader_panel import data as D
    assert D.BOTS == ("learner",) and not hasattr(D.PanelData, "compare")
    js, html = _t("src/trader_panel/static/panel.js"), _t("src/trader_panel/static/index.html")
    assert "twin" not in js and "ikiz" not in js and "twin" not in html and "ikiz" not in html


def test_telegram_config_and_scripts_have_no_twin():
    from trader_core import telegram as T
    assert not hasattr(T.TelegramConfig("t", 1, "/tmp/x"), "twin_ledger_path")
    assert "ikiz" not in T.BOT_TR.values().__repr__()
    for rel in ("scripts/telegram_run.py", "scripts/drift_run.py", "scripts/report_run.py",
                "scripts/counterfactual_run.py", "scripts/engine_retry.py"):
        assert "twin" not in _t(rel), rel
