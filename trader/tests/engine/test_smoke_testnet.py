"""WP-B7: scripts/smoke_testnet.py korkuluklari ve adimlari; ag YOK (urlopen/requests yasak), sahte borsa (fake_exchange)."""
from __future__ import annotations

import json
import sys
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))

import smoke_testnet as M  # noqa: E402
import smoke_testnet_lib as L  # noqa: E402
from fake_exchange import KEY, SECRET, FakeExchange  # noqa: E402
from trader_engine.clock import SimClock  # noqa: E402
from trader_engine.exchange.binance_rest import SignedRestClient  # noqa: E402

T0 = datetime(2026, 12, 28, 9, 0, tzinfo=timezone.utc)
ENV = {"BINANCE_API_KEY": KEY, "BINANCE_API_SECRET": SECRET}


@pytest.fixture(autouse=True)
def no_network(monkeypatch):
    def boom(*a, **k):
        raise AssertionError("ag erisimi yasak")
    monkeypatch.setattr(urllib.request, "urlopen", boom)
    try:
        import requests
        monkeypatch.setattr(requests.Session, "request", boom)
    except ImportError:
        pass


def run(tmp_path, argv, ex=None, environ=ENV, mode="algo", on_wait=None, inputs=None, **kw):
    clock = SimClock(T0)
    ex = ex or FakeExchange(lambda: int(clock.now().timestamp() * 1000), classic=(mode == "classic"))
    made = {}

    def factory(**k):
        r = SignedRestClient(session=ex.session, **k)
        made["rest"] = r
        return r
    out = []
    rc = M.main(["--config-dir", str(ROOT / "config"), "--out-root", str(tmp_path), "--ack-no-withdraw", *argv],
                environ=environ, rest_factory=factory, clock=clock, input_fn=lambda *_: "", say=out.append,
                on_wait=(lambda: on_wait(ex)) if on_wait else None, **kw)
    return rc, ex, out, made


def test_live_refused_before_anything(tmp_path):
    rc, ex, out, _ = run(tmp_path, ["--env", "live", "--step", "b0-preflight"])
    assert rc == 2 and not ex.requests and "live" in out[0]


def test_env_required(tmp_path):
    rc, ex, out, _ = run(tmp_path, ["--step", "b0-preflight"])
    assert rc == 2 and not ex.requests


def test_base_url_allowlist():
    L.guard_base_url("https://testnet.binancefuture.com")
    for bad in ("https://fapi.binance.com", "https://api.binance.com", "https://testnet.binancefuture.com.evil.io", ""):
        with pytest.raises(L.SafetyError):
            L.guard_base_url(bad)


def test_guard_rest_rejects_live_client():
    c = SignedRestClient(env="live", api_key=KEY, api_secret=SECRET, session=object(), now_ms=lambda: 0, sleep=lambda s: None)
    with pytest.raises(L.SafetyError):
        L.guard_rest(c)


def test_missing_keys_refused(tmp_path):
    rc, ex, out, _ = run(tmp_path, ["--env", "testnet", "--step", "b0-preflight"], environ={})
    assert rc == 2 and not ex.requests and "BINANCE_API_KEY" in out[0]


def test_withdrawals_enabled_refused(tmp_path):
    with pytest.raises(L.SafetyError):
        L.check_withdrawals({"enableWithdrawals": True}, ack_no_withdraw=True)
    assert L.check_withdrawals({"enableWithdrawals": False}, ack_no_withdraw=False) == "verified"
    with pytest.raises(L.SafetyError):
        L.check_withdrawals(None, ack_no_withdraw=False)
    assert L.check_withdrawals(None, ack_no_withdraw=True) == "operator_ack"


def test_withdraw_ack_required_end_to_end(tmp_path):
    clock = SimClock(T0)
    ex = FakeExchange(lambda: 0)
    out = []
    rc = M.main(["--env", "testnet", "--step", "b0-preflight", "--config-dir", str(ROOT / "config"), "--out-root", str(tmp_path)],
                environ=ENV, rest_factory=lambda **k: SignedRestClient(session=ex.session, **k), clock=clock, say=out.append)
    assert rc == 2 and "cekme" in out[0]


def test_mask_hides_secrets():
    assert SECRET not in L.mask(f"x {SECRET} signature=abcdef0123456789abcdef0123456789", (SECRET,))
    assert "***" in L.mask_key(KEY) and KEY not in L.mask_key(KEY)


def test_dry_run_prints_plan_without_network_or_keys(tmp_path):
    out = []
    rc = M.main(["--env", "testnet", "--step", "b0,t,drills", "--dry-run"], environ={}, say=out.append)
    assert rc == 0
    text = "\n".join(out)
    for ref in ("T-01", "T-13", "T-16", "D-1", "D-8", "B0"):
        assert ref in text
    assert not (tmp_path / "smoke").exists()


def test_all_steps_registered():
    for n in ("b0-preflight", "t13", "t14", "t15", "t16", *[f"d{i}" for i in range(1, 9)]):
        assert n in M.STEPS
    with pytest.raises(L.SafetyError):
        M.resolve_steps(["yok"])


def test_min_order_qty():
    q = L.min_order_qty(0.1, 0.1, 5.0, 2.0)
    assert q == L.Decimal("3.0")           # 5*1.2/2 = 3.0
    assert L.min_order_qty(10, 1, 5.0, 2.0) == 10


def test_preflight_writes_reports_and_no_secrets(tmp_path):
    rc, ex, out, _ = run(tmp_path, ["--env", "testnet", "--step", "b0-preflight"])
    assert rc == 0, out
    d = next((tmp_path / "smoke").iterdir())
    j = (d / "result.json").read_text()
    md = (d / "result.md").read_text()
    assert json.loads(j)["results"][0]["status"] == "GECTI"
    for blob in (j, md, "\n".join(out)):
        assert KEY not in blob and SECRET not in blob
    assert not [r for r in ex.requests if r[0] == "POST" and "order" in r[1].lower()]


def test_refuses_when_position_already_open(tmp_path):
    clock = SimClock(T0)
    ex = FakeExchange(lambda: int(clock.now().timestamp() * 1000))
    ex.fill_market("XRPUSDT", "BUY", "10")
    rc, ex, out, _ = run(tmp_path, ["--env", "testnet", "--step", "b0-t01"], ex=ex)
    assert rc == 2
    assert not [r for r in ex.requests if r[0] == "POST" and r[1].endswith("/order")]   # yabanci pozisyona dokunulmadi


def test_probe_steps_cleanup_leaves_flat_and_no_orders(tmp_path):
    rc, ex, out, made = run(tmp_path, ["--env", "testnet", "--step", "b0-t01,b0-t02,b0-t03,b0-t05,b0-t06,b0-t09,b0-t10"])
    assert rc == 0, out
    assert float(made["rest"].position_risk("XRPUSDT")[0]["positionAmt"]) == 0
    assert not made["rest"].open_conditionals("XRPUSDT") and not made["rest"].open_orders("XRPUSDT")


def test_t13_lifecycle_with_trigger(tmp_path):
    def nudge(ex):                      # fiyat dusur -> son stop tetiklenir
        ex.set_mark("XRPUSDT", "1.0")
    rc, ex, out, _ = run(tmp_path, ["--env", "testnet", "--step", "t13", "--trigger-wait-s", "6"], on_wait=nudge)
    assert rc == 0, out
    res = json.loads(next((tmp_path / "smoke").iterdir()).joinpath("result.json").read_text())["results"][0]
    assert res["status"] == "GECTI" and res["data"]["stop_gecikme_s"] <= 10


def test_t13_no_trigger_flattens_in_finally(tmp_path):
    rc, ex, out, made = run(tmp_path, ["--env", "testnet", "--step", "t13", "--trigger-wait-s", "3"])
    assert rc == 1                                          # BEKLEMEDE
    assert float(made["rest"].position_risk("XRPUSDT")[0]["positionAmt"]) == 0
    assert not made["rest"].open_conditionals("XRPUSDT")


def test_step_exception_still_cleans_up(tmp_path, monkeypatch):
    def bad(ctx):
        ctx.open_long(); ctx.stop(0.02)
        raise RuntimeError(f"patladi {SECRET}")
    monkeypatch.setitem(M.STEPS, "t14", M.Step("t14", "T-14", "x", bad, "t"))
    rc, ex, out, made = run(tmp_path, ["--env", "testnet", "--step", "t14"])
    assert rc == 1
    assert float(made["rest"].position_risk("XRPUSDT")[0]["positionAmt"]) == 0
    assert not made["rest"].open_conditionals("XRPUSDT")
    d = next((tmp_path / "smoke").iterdir())
    assert SECRET not in (d / "result.json").read_text()


def test_t14_skipped_by_default_and_large_qty_capped(tmp_path):
    rc, ex, out, _ = run(tmp_path, ["--env", "testnet", "--step", "t14"])
    assert rc == 0 and "ATLANDI" in "\n".join(out)
    rc, ex, out, _ = run(tmp_path, ["--env", "testnet", "--step", "t14", "--partial-fill-multiple", "5000"])
    assert rc == 2


def test_d8_wrong_key_runs_cli_and_checks_exit_code(tmp_path):
    class P:
        returncode, stdout, stderr = 8, "acilis denetimi reddetti\n", ""
    calls = []
    rc, ex, out, _ = run(tmp_path, ["--env", "testnet", "--step", "d8"], runner=lambda *a, **k: calls.append((a, k)) or P)
    assert rc == 0 and calls and calls[0][0][0][-4:] == ["--bot", "learner", "--env", "testnet"] and "x" * 40 != KEY


def test_drill_d5_guided_with_reinstall(tmp_path):
    rc, ex, out, _ = run(tmp_path, ["--env", "testnet", "--step", "d5"])
    assert rc == 0, out      # stop elle silinmedigi icin yerinde: bekleme hemen biter


def test_uses_testnet_paths_only():
    from trader_engine.config import load_engine_config
    d = ROOT / "config"
    cfg = load_engine_config(d / "engine.base.json", d / "engine.learner.json", overlay_path=d / "engine.testnet.json")
    L.guard_config(cfg)
    assert cfg.var_dir == "var-testnet" and cfg.kill_file == "shared/testnet/KILL"
