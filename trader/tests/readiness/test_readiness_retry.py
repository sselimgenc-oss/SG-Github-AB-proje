"""WP-C: motor acilis-kapisi (cikis 7) yeniden deneme betigi."""
from __future__ import annotations

import importlib.util
import json
import sqlite3
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))
spec = importlib.util.spec_from_file_location("engine_retry_t", ROOT / "scripts" / "engine_retry.py")
R = importlib.util.module_from_spec(spec)
spec.loader.exec_module(R)

NOW = datetime(2026, 1, 1, 12, 0, tzinfo=timezone.utc)
PAIRS = ["BTC/USDT:USDT", "ETH/USDT:USDT"]


def _ms(dt):
    return int(dt.timestamp() * 1000)


def make_env(tmp_path, *, feed_age=30, bar_age=30, rules=2, notifier="log"):
    var = tmp_path / "var"
    var.mkdir()
    (var / "feed-status.json").write_text(json.dumps({"ts": (NOW - timedelta(seconds=feed_age)).isoformat(), "pairs": PAIRS}))
    c = sqlite3.connect(var / "market.sqlite")
    c.execute("CREATE TABLE bars(kind TEXT, pair TEXT, tf TEXT, open_ms INTEGER)")
    c.execute("CREATE TABLE rules(pair TEXT)")
    c.execute("CREATE TABLE feed_meta(k TEXT, v TEXT)")
    for p in PAIRS:
        c.execute("INSERT INTO bars VALUES('last',?,'1m',?)", (p.split(":")[0].replace("/", "").replace("USDT", "/USDT"), _ms(NOW - timedelta(seconds=bar_age))))
    for i in range(rules):
        c.execute("INSERT INTO rules VALUES(?)", (f"P{i}",))
    c.commit()
    c.close()
    return {"ENGINE_VAR_DIR": str(var), "MARKET_DB": str(var / "market.sqlite"), "MARKET_PAIRS": ",".join(PAIRS),
            "STATE_DIR": str(tmp_path / "state"), "NOTIFIER": notifier}


class Ctl:
    def __init__(self, active="failed", exit_=7):
        self.active, self.exit_, self.calls = active, exit_, []

    def __call__(self, args):
        self.calls.append(list(args))
        if args[0] == "show":
            return 0, f"ActiveState={self.active}\nExecMainStatus={self.exit_}\nResult=exit-code\n"
        return 0, ""

    @property
    def restarts(self):
        return [c for c in self.calls if c[0] == "restart"]


def test_failed_exit7_feed_healthy_restarts(tmp_path):
    env, ctl = make_env(tmp_path), Ctl()
    assert R.run("learner", env, ctl=ctl, now=NOW) == "restarted"
    assert ctl.restarts == [["restart", "trader-engine@learner.service"]]
    assert len(json.loads((tmp_path / "state" / "engine-retry.json").read_text())["learner"]["attempts"]) == 1


def test_exit6_or_config_error_no_restart(tmp_path):
    env = make_env(tmp_path)
    for code in (6, 1, 2):
        ctl = Ctl(exit_=code)
        assert R.run("learner", env, ctl=ctl, now=NOW) == "not_gate"
        assert not ctl.restarts


@pytest.mark.parametrize("kw", [{"feed_age": 400}, {"bar_age": 400}, {"rules": 1}])
def test_feed_unhealthy_no_restart(tmp_path, kw):
    ctl = Ctl()
    assert R.run("learner", make_env(tmp_path, **kw), ctl=ctl, now=NOW) == "feed_unhealthy"
    assert not ctl.restarts


def test_missing_feed_files_no_restart(tmp_path):
    ctl = Ctl()
    env = {"ENGINE_VAR_DIR": str(tmp_path / "nope"), "MARKET_PAIRS": ",".join(PAIRS), "STATE_DIR": str(tmp_path / "s")}
    assert R.run("learner", env, ctl=ctl, now=NOW) == "feed_unhealthy"
    assert not ctl.restarts


def test_active_unit_is_noop(tmp_path):
    ctl = Ctl(active="active", exit_=0)
    assert R.run("learner", make_env(tmp_path), ctl=ctl, now=NOW) == "noop"
    assert not ctl.restarts


def test_seventh_attempt_in_hour_no_restart_and_one_crit(tmp_path, monkeypatch):
    env, ctl = make_env(tmp_path), Ctl()
    import health_run
    from trader_core import health as H
    n = H.NullNotifier()
    monkeypatch.setattr(health_run, "make_notifier", lambda name, environ=None: n)
    monkeypatch.setattr(R, "feed_healthy", lambda e, now: (True, "ok"))   # zaman ilerler; besleme tazeligi ayri test edilir
    for i in range(6):
        assert R.run("learner", env, ctl=ctl, now=NOW + timedelta(minutes=5 * i)) == "restarted"
    assert len(ctl.restarts) == 6
    assert R.run("learner", env, ctl=ctl, now=NOW + timedelta(minutes=30)) == "exhausted"
    assert R.run("learner", env, ctl=ctl, now=NOW + timedelta(minutes=35)) == "exhausted_quiet"
    assert len(ctl.restarts) == 6
    assert len(n.sent) == 1 and n.sent[0].level == H.Status.CRIT and n.sent[0].fingerprint.startswith("engine-retry-exhausted:")
    # pencere kayinca yeniden deneme yeniden acilir
    assert R.run("learner", env, ctl=ctl, now=NOW + timedelta(minutes=70)) == "restarted"


def test_per_bot_counters_are_independent(tmp_path):
    env, ctl = make_env(tmp_path), Ctl()
    R.run("learner", env, ctl=ctl, now=NOW)
    R.run("twin", env, ctl=ctl, now=NOW)
    st = json.loads((tmp_path / "state" / "engine-retry.json").read_text())
    assert set(st) == {"learner", "twin"}
