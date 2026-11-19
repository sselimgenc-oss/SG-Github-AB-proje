"""docs/cikis-karsi-olgu-spec.md 9 test 6 (CLI cikis kodlari, kayit, dry-run) ve test 7 (yazma yolu): scripts/exit_counterfactual_run.py."""
from __future__ import annotations

import importlib.util
import json
import sqlite3
import sys
from datetime import datetime, timedelta, timezone

import pytest

from pathlib import Path

from exit_cf_support import T0, T0_MS, _sqlite_market, mk_t1_ledger
from trader_core import exit_counterfactual as EC

NOW = datetime(2025, 3, 1, tzinfo=timezone.utc)
ROOT = Path(__file__).resolve().parents[1]
_spec = importlib.util.spec_from_file_location("exit_counterfactual_run", ROOT / "scripts" / "exit_counterfactual_run.py")
CLI = importlib.util.module_from_spec(_spec)
sys.modules["exit_counterfactual_run"] = CLI
_spec.loader.exec_module(CLI)


@pytest.fixture
def env(tmp_path):
    led = tmp_path / "ledger.sqlite"
    mk_t1_ledger(led, [(T0, T0 + timedelta(days=3), 105.0, "trail_stop", "1h"),
                       (T0 + timedelta(hours=5), T0 + timedelta(days=4), 99.0, "stop", "15m"),
                       (T0 + timedelta(hours=9), T0 + timedelta(days=4), 99.0, "manual", "1h")])
    mkt = tmp_path / "market.sqlite"
    _sqlite_market(mkt, T0)
    csv = tmp_path / "reg.csv"
    csv.write_text("id,strategy\nexitcf-v1,TraderV1b\n", encoding="utf-8")
    base = tmp_path / "base.json"
    base.write_text(json.dumps({"cost": {"trigger_source": "last"}}), encoding="utf-8")
    return tmp_path, ["--bot", "learner", "--once", "--ledger", str(led), "--market", str(mkt), "--out", str(tmp_path / "out.sqlite"),
                      "--registry-csv", str(csv), "--base-config", str(base), "--paper-config", str(tmp_path / "yok2.json")]


def call(args, capsys, now=NOW):
    rc = CLI.main(args, now_fn=lambda: now)
    out = capsys.readouterr().out.strip().splitlines()
    return rc, json.loads(out[-1]) if out else None


def test_end_to_end_counters_and_rows(env, capsys):
    tmp, args = env
    rc, o = call(args, capsys)
    assert rc == 0 and o["status"] == "ok" and o["registry_id"] == "exitcf-v1"
    assert (o["scanned"], o["computed"], o["skipped_15m"], o["excluded_exit_reason"]) == (3, 1, 1, 1)
    assert o["rows_written"] == 3 and o["horizon_mtm"] == 3 and o["censored"] == 3          # sabit seri: yol 720. mumda piyasaya gore
    assert o["parity_n"] == 1 and o["parity_status"] == "parity_unknown"                     # < 20 parite satiri
    for k in ("base_parity_median_abs_r", "parity_mean_r", "reason_match_rate", "pending", "no_data", "data_gap", "holdout_skipped"):
        assert k in o
    c = sqlite3.connect(tmp / "out.sqlite")
    assert c.execute("SELECT COUNT(*), MIN(version), MIN(registry_id), MIN(source) FROM ecf_outcomes").fetchone() == (3, 1, "exitcf-v1", "paper")
    c.close()
    rc2, o2 = call(args, capsys)                                                             # idempotans
    assert rc2 == 0 and o2["already"] == 1 and o2["rows_written"] == 0 and o2["computed"] == 0


def test_dry_run_writes_no_file(env, capsys):
    tmp, args = env
    rc, o = call(args + ["--dry-run"], capsys)
    assert rc == 0 and o["computed"] == 1 and o["rows_written"] == 0 and not (tmp / "out.sqlite").exists()


def test_unregistered_registry_id_exits_1(env, capsys):
    tmp, args = env
    rc, o = call(args + ["--registry-id", "exitcf-v2"], capsys)
    assert rc == 1 and o["status"] == "unregistered" and not (tmp / "out.sqlite").exists()


def test_registry_csv_row_required_when_csv_exists(env, capsys):
    tmp, args = env
    (tmp / "reg.csv").write_text("id,strategy\nbaska,X\n", encoding="utf-8")
    rc, o = call(args, capsys)
    assert rc == 1 and o["status"] == "unregistered"


def test_missing_ledger_is_success(env, capsys):
    tmp, args = env
    args = [a if a != str(tmp / "ledger.sqlite") else str(tmp / "yok.sqlite") for a in args]
    rc, o = call(args, capsys)
    assert rc == 0 and o["status"] == "no_ledger"


def test_corrupt_store_and_missing_market_are_degraded(env, capsys):
    tmp, args = env
    (tmp / "out.sqlite").write_bytes(b"bu bir sqlite dosyasi degil" * 40)
    rc, o = call(args, capsys)
    assert rc == 3 and o["status"] == "degraded"
    (tmp / "out.sqlite").unlink()
    args2 = [a if a != str(tmp / "market.sqlite") else str(tmp / "yok.sqlite") for a in args]
    rc, o = call(args2, capsys)
    assert rc == 3 and o["code"] == "market_missing"


def test_once_required_and_backtest_list_fixed(env, capsys):
    tmp, args = env
    assert CLI.main([a for a in args if a != "--once"]) == 1
    capsys.readouterr()
    with pytest.raises(SystemExit):
        CLI.main(args + ["--runs", "15m_IS_f1_s0_compat"], now_fn=lambda: NOW)


def test_cli_cannot_write_ledger_or_market(env):
    tmp, args = env
    led = CLI.L.open_ledger(tmp / "ledger.sqlite", "learner", create=False, read_only=True, migrate=False)
    try:
        with pytest.raises(Exception):
            led.init_params({}, reason="yazma denemesi")
    finally:
        led.close()
    ms = EC.MarketSource(tmp / "market.sqlite")
    with pytest.raises(sqlite3.OperationalError):
        ms._db.execute("DELETE FROM bars")
    ms.close()


def test_script_writes_only_its_own_file(env, capsys):
    import hashlib
    tmp, args = env
    digest = lambda n: hashlib.sha256((tmp / n).read_bytes()).hexdigest()          # noqa: E731
    before = (digest("ledger.sqlite"), digest("market.sqlite"))
    call(args, capsys)
    assert (digest("ledger.sqlite"), digest("market.sqlite")) == before and (tmp / "out.sqlite").exists()
