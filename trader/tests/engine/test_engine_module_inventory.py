"""08 §4.6: Faz A kapsam kilidi (modül envanteri)."""
from __future__ import annotations

import os
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
PHASE = "A"
ENGINE = "src/trader_engine"
ALLOWED_MODULES_A = {
    "__init__.py", "__main__.py", "errors.py", "types.py", "numeric.py", "clock.py", "bars.py", "config.py", "fileio.py",
    "state.py", "order_manager.py", "position_manager.py", "funding.py", "strategy_runner.py", "gates.py", "engine.py",
    "reconcile.py", "killswitch.py", "status.py", "backtest.py", "precomputed.py", "metrics.py", "cli.py",
    "marketdata/__init__.py", "marketdata/rest_public.py", "marketdata/store.py", "marketdata/feed.py", "marketdata/sources.py",
    "strategies/__init__.py", "strategies/base.py", "strategies/registry.py", "strategies/price_action_v1.py", "strategies/price_action_v1_ml.py",
    "brokers/__init__.py", "brokers/base.py", "brokers/paper.py", "exchange/__init__.py", "exchange/rules.py"}
PHASE_B_FILES = ["brokers/binance_futures.py", "exchange/binance_rest.py", "marketdata/ws.py", "reconcile_live.py"]
FORBIDDEN_TEXT = ["listen" + "Key", "userData" + "Stream", "algo" + "Order", "web" + "sockets"]


def scan_inventory(root: Path, phase: str = PHASE) -> list[str]:
    v = []
    base = Path(root) / ENGINE
    if not base.exists():
        return v
    for d, dirs, files in os.walk(base):
        dirs[:] = [x for x in dirs if x != "__pycache__"]
        for f in files:
            if f.endswith(".py"):
                rel = str((Path(d) / f).relative_to(base))
                if rel not in ALLOWED_MODULES_A:
                    v.append(f"unlisted module {rel}")
                if phase == "A":
                    t = (Path(d) / f).read_text(encoding="utf-8")
                    v += [f"{rel}: phase B text {w}" for w in FORBIDDEN_TEXT if w in t]
    if phase == "A":
        v += [f"phase B file {p}" for p in PHASE_B_FILES if (base / p).exists()]
    return v


def test_real_tree_inventory():
    assert scan_inventory(REPO) == []


def test_phase_constant():
    assert PHASE == "A"


def test_scanner_boundaries(tmp_path):
    b = tmp_path / ENGINE
    (b / "brokers").mkdir(parents=True)
    (b / "types.py").write_text("x = 1\n")
    assert scan_inventory(tmp_path) == []
    (b / "extra.py").write_text("")
    assert scan_inventory(tmp_path) == ["unlisted module extra.py"]
    (b / "extra.py").unlink()
    (b / "brokers" / "binance_futures.py").write_text("")
    r = scan_inventory(tmp_path)
    assert any("binance_futures" in x for x in r)
    (b / "brokers" / "binance_futures.py").unlink()
    (b / "types.py").write_text("x = 'listen" + "Key'\n")
    assert scan_inventory(tmp_path)
    assert scan_inventory(tmp_path, phase="B") == []
