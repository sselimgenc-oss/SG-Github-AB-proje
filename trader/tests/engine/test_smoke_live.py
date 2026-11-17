"""WP-B9: scripts/smoke_live.py korkuluklari ve akisi; ag YOK (urlopen/requests yasak), sahte borsa (fake_exchange)."""
from __future__ import annotations

import json
import sys
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))

import smoke_live as M  # noqa: E402
import smoke_testnet_lib as L  # noqa: E402
from fake_exchange import KEY, SECRET, FakeExchange  # noqa: E402
from trader_core import risk_ladder as RL  # noqa: E402
from trader_engine.clock import SimClock  # noqa: E402
from trader_engine.exchange.binance_rest import SignedRestClient  # noqa: E402

T0 = datetime(2026, 12, 28, 9, 0, tzinfo=timezone.utc)
TAG = "live-sub"
PHRASE = f"GERCEK EMIR {TAG}"
ENV = {"BINANCE_API_KEY": KEY, "BINANCE_API_SECRET": SECRET, "LIVE_CONFIRM": TAG}


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


@pytest.fixture
def setup(tmp_path):
    """Canli katman + gecerli kademe gunlugu (capital init) tmp altinda."""
    var = tmp_path / "var-live"
    overlay = tmp_path / "engine.live.json"
    overlay.write_text(json.dumps({
        "mode": "live", "var_dir": str(var), "kill_file": str(tmp_path / "KILL"), "pause_file": str(tmp_path / "PAUSE"),
        "live": {"account_tag": TAG, "expected_wallet_max": 1000.0, "conditional_mode": "algo", "recv_window_ms": 5000,
                 "poll_open_s": 5.0, "poll_flat_s": 30.0, "stop_deadline_s": 10.0, "entry_resolve_window_s": 60.0,
                 "max_attempts": 1}}))
    lad = var / "learner" / "risk_ladder.jsonl"
    lad.parent.mkdir(parents=True)
    RL.LadderLog(str(lad)).append("initial", "cli:test", T0, amount=250.0)
    return {"overlay": overlay, "ladder": lad, "tmp": tmp_path}


def fn_input(phrase=PHRASE, say_no_at=None, log=None):
    n = {"i": 0}

    def f(prompt):
        n["i"] += 1
        if log is not None:
            log.append(prompt)
        if prompt.startswith("ONAY"):
            return phrase
        if say_no_at is not None and n["i"] == say_no_at:
            return "kapat"
        return "evet"
    return f


def run(setup, argv=(), ex=None, environ=ENV, input_fn=None, wallet="100"):
    clock = SimClock(T0)
    ex = ex or FakeExchange(lambda: int(clock.now().timestamp() * 1000), wallet=wallet)
    made = {}

    def factory(**k):
        r = SignedRestClient(session=ex.session, **k)
        made["rest"], made["kw"] = r, k
        return r
    out = []
    rc = M.main(["--env", "live", "--config-dir", str(ROOT / "config"), "--live-overlay", str(setup["overlay"]),
                 "--out-root", str(setup["tmp"] / "var-live"), *argv],
                environ=environ, rest_factory=factory, clock=clock, input_fn=input_fn or fn_input(), say=out.append)
    return rc, ex, out, made


def orders(ex):
    return [r for r in ex.requests if r[0] == "POST" and r[1] in ("/fapi/v1/order", "/fapi/v1/algoOrder")]


def reports(setup):
    d = next((setup["tmp"] / "var-live" / "smoke").iterdir())
    return json.loads((d / "result.json").read_text()), (d / "result.md").read_text()


# ------------------------------------------------------------------------------------------ ortam / izin listesi
def test_env_required_and_testnet_refused(setup):
    for argv in (["--env", "testnet"],):
        clock = SimClock(T0)
        ex = FakeExchange(lambda: 0)
        out = []
        rc = M.main(argv, environ=ENV, rest_factory=lambda **k: SignedRestClient(session=ex.session, **k), clock=clock,
                    input_fn=fn_input(), say=out.append)
        assert rc == 2 and not ex.requests and "testnet" in out[0]
    out = []
    assert M.main([], environ=ENV, say=out.append) == 2


def test_base_url_allowlist_production_only():
    M.guard_base_url("https://fapi.binance.com")
    for bad in ("https://testnet.binancefuture.com", "https://api.binance.com", "https://fapi.binance.com.evil.io", ""):
        with pytest.raises(L.SafetyError):
            M.guard_base_url(bad)


def test_guard_rest_rejects_testnet_client():
    c = SignedRestClient(env="testnet", api_key=KEY, api_secret=SECRET, session=object(), now_ms=lambda: 0, sleep=lambda s: None)
    with pytest.raises(L.SafetyError):
        M.guard_rest(c)
    ok = SignedRestClient(env="live", api_key=KEY, api_secret=SECRET, session=object(), now_ms=lambda: 0, sleep=lambda s: None)
    M.guard_rest(ok)


def test_testnet_config_layer_refused(setup):
    tn = setup["tmp"] / "engine.tn.json"
    tn.write_text((ROOT / "config" / "engine.testnet.json").read_text())
    setup["overlay"] = tn
    rc, ex, out, _ = run(setup)
    assert rc == 2 and not ex.requests and "live degil" in out[0]


def test_missing_live_overlay_refused(setup):
    setup["overlay"] = setup["tmp"] / "yok.json"
    rc, ex, out, _ = run(setup)
    assert rc == 2 and not ex.requests


def test_live_confirm_required_and_must_match_tag(setup):
    for env in ({**ENV, "LIVE_CONFIRM": "baska-etiket"}, {k: v for k, v in ENV.items() if k != "LIVE_CONFIRM"}):
        rc, ex, out, _ = run(setup, environ=env)
        assert rc == 2 and not ex.requests and "LIVE_CONFIRM" in out[0]


def test_missing_keys_refused(setup):
    rc, ex, out, _ = run(setup, environ={"LIVE_CONFIRM": TAG})
    assert rc == 2 and not ex.requests and "BINANCE_API_KEY" in out[0]


# ------------------------------------------------------------------------------------------ izinler (cikis 8)
@pytest.mark.parametrize("patch", [{"enableWithdrawals": True}, {"ipRestrict": False}, {"enableWithdrawals": "true"},
                                   {"enableInternalTransfer": True}])
def test_unsafe_key_permissions_exit_8_no_orders(setup, patch):
    clock = SimClock(T0)
    ex = FakeExchange(lambda: int(clock.now().timestamp() * 1000))
    ex.restrictions.update(patch)
    rc, ex, out, _ = run(setup, ex=ex)
    assert rc == 8 and not orders(ex)


def test_permissions_unreadable_exit_8_and_no_attestation_bypass(setup):
    clock = SimClock(T0)
    ex = FakeExchange(lambda: int(clock.now().timestamp() * 1000))
    ex.restrictions_status = 500
    env = {**ENV, "LIVE_PERMISSION_ATTESTED": "2026-12-27"}
    rc, ex, out, _ = run(setup, ex=ex, environ=env)
    assert rc == 8 and not orders(ex)
    p = M.build_parser()
    for flag in ("--ack-no-withdraw", "--yes", "--attest", "--force"):
        with pytest.raises(SystemExit):
            p.parse_args(["--env", "live", flag])


def test_check_permissions_unit():
    good = {"enableReading": True, "enableFutures": True, "enableWithdrawals": False, "enableInternalTransfer": False,
            "permitsUniversalTransfer": False, "ipRestrict": True}
    M.check_permissions(good)
    for bad in (None, {}, {**good, "enableWithdrawals": True}, {**good, "ipRestrict": False}, {k: v for k, v in good.items() if k != "ipRestrict"}):
        with pytest.raises(M.PermissionRefused):
            M.check_permissions(bad)


# ------------------------------------------------------------------------------------------ kademe / KILL / tutus
def test_missing_ladder_log_refused_before_network(setup):
    setup["ladder"].unlink()
    rc, ex, out, _ = run(setup)
    assert rc == 2 and not ex.requests and "sermaye" in out[0]


def test_invalid_ladder_log_refused(setup):
    setup["ladder"].write_text(setup["ladder"].read_text().replace("250.0", "999.0"))
    rc, ex, out, _ = run(setup)
    assert rc == 2 and not ex.requests and "gecersiz" in out[0]


def test_ladder_review_or_floor_state_refused(setup):
    log = RL.LadderLog(str(setup["ladder"]))
    log.append("review_stop", "engine:rk1", T0, equity=199.0, base=250.0)
    rc, ex, out, _ = run(setup)
    assert rc == 2 and not ex.requests and "review" in out[0]


def test_kill_active_refused(setup):
    (setup["tmp"] / "KILL").write_text("{}")
    rc, ex, out, _ = run(setup)
    assert rc == 2 and not ex.requests and "KILL" in out[0]


def test_ladder_hold_refused(setup):
    from trader_engine.pause import EntryPause
    EntryPause(f"{setup['tmp'] / 'PAUSE'}.learner", SimClock(T0)).add("drawdown_review", "engine:rk1", "x")
    rc, ex, out, _ = run(setup)
    assert rc == 2 and not ex.requests and "drawdown_review" in out[0]


def test_kill_set_after_start_blocks_first_order(setup):
    """Ilk emirden hemen once yeniden denetlenir: onay sirasinda KILL konursa emir gitmez."""
    def inp(prompt):
        if prompt.startswith("ONAY"):
            (setup["tmp"] / "KILL").write_text("{}")
            return PHRASE
        return "evet"
    rc, ex, out, _ = run(setup, input_fn=inp)
    assert rc == 2 and not orders(ex)


# ------------------------------------------------------------------------------------------ hesap durumu / tutar
def test_wallet_above_cap_exit_8(setup):
    rc, ex, out, _ = run(setup, wallet="5000")
    assert rc == 8 and not orders(ex)


def test_existing_foreign_position_refused_untouched(setup):
    clock = SimClock(T0)
    ex = FakeExchange(lambda: int(clock.now().timestamp() * 1000))
    ex.fill_market("DOGEUSDT", "BUY", "10")
    rc, ex, out, _ = run(setup, ex=ex)
    assert rc == 2 and not orders(ex)
    assert ex.pos["DOGEUSDT"]["amt"] != 0


def test_existing_foreign_open_order_refused(setup):
    clock = SimClock(T0)
    ex = FakeExchange(lambda: int(clock.now().timestamp() * 1000))
    ex.orders["web_x"] = {"clientOrderId": "web_x", "symbol": "XRPUSDT", "side": "BUY", "type": "LIMIT", "status": "NEW",
                          "origQty": "1", "orderId": 7}
    rc, ex, out, _ = run(setup, ex=ex)
    assert rc == 2 and not orders(ex)


def test_notional_cap_refuses_large_step(setup):
    clock = SimClock(T0)
    ex = FakeExchange(lambda: int(clock.now().timestamp() * 1000),
                      symbols={"XRPUSDT": {"tick": "0.0001", "step": "10", "notional": "5"},
                               "DOGEUSDT": {"tick": "0.00001", "step": "1", "notional": "5"}})
    rc, ex, out, _ = run(setup, ex=ex)
    assert rc == 2 and not orders(ex) and "siniri" in "".join(out)


def test_pair_must_be_in_config(setup):
    rc, ex, out, _ = run(setup, argv=["--pair", "FOO/USDT"])
    assert rc == 2 and not ex.requests


# ------------------------------------------------------------------------------------------ onay ifadesi
def test_wrong_phrase_sends_no_order(setup):
    rc, ex, out, _ = run(setup, input_fn=fn_input(phrase="evet"))
    assert rc == 2 and not orders(ex)


def test_order_impossible_without_confirmation(setup):
    clock = SimClock(T0)
    ex = FakeExchange(lambda: int(clock.now().timestamp() * 1000))
    rc, ex, out, made = run(setup, ex=ex, input_fn=fn_input(phrase=""))
    assert rc == 2 and not orders(ex)


def test_stop_now_at_gate_after_entry_flattens(setup):
    # 1:s0 2:s1 3:s2 (ONAY) 4:s3 5:s4 -> 'kapat' stop'tan once
    rc, ex, out, _ = run(setup, input_fn=fn_input(say_no_at=6))
    assert rc == 2
    assert ex.pos["XRPUSDT"]["amt"] == 0
    assert not [a for a in ex.algos.values() if a["algoStatus"] == "NEW"]


# ------------------------------------------------------------------------------------------ tam akis
def test_full_flow_passes_and_writes_reports(setup):
    log = []
    rc, ex, out, _ = run(setup, input_fn=fn_input(log=log))
    assert rc == 0, out
    assert any(p.startswith("ONAY") for p in log)
    j, md = reports(setup)
    assert [r["status"] for r in j["results"]] == ["GECTI"] * len(M.STEPS)
    assert ex.pos["XRPUSDT"]["amt"] == 0
    assert not [o for o in ex.orders.values() if o.get("status") == "NEW"]
    assert not [a for a in ex.algos.values() if a["algoStatus"] == "NEW"]
    assert "Canli duman testi" in md and j["meta"]["env"] == "live"
    # yalniz tek cift
    assert {r[2].get("symbol") for r in orders(ex)} == {"XRPUSDT"}


def test_first_order_after_confirmation_only(setup):
    seen = {"order_before": None}

    def inp(prompt):
        if prompt.startswith("ONAY"):
            seen["order_before"] = bool(orders(holder["ex"]))
            return PHRASE
        return "evet"
    clock = SimClock(T0)
    holder = {"ex": FakeExchange(lambda: int(clock.now().timestamp() * 1000))}
    rc, ex, out, _ = run(setup, ex=holder["ex"], input_fn=inp)
    assert rc == 0 and seen["order_before"] is False


def test_report_dir_is_var_live_smoke_timestamp(setup):
    rc, *_ = run(setup)
    d = next((setup["tmp"] / "var-live" / "smoke").iterdir())
    assert d.name.startswith("20261228T") and (d / "result.json").exists() and (d / "result.md").exists()
    assert M.DEFAULT_OUT_ROOT == "var-live"


def test_no_secrets_in_outputs_and_reports(setup):
    log = []
    rc, ex, out, _ = run(setup, input_fn=fn_input(log=log))
    j, md = reports(setup)
    for blob in (json.dumps(j), md, "\n".join(out), "\n".join(log)):
        assert KEY not in blob and SECRET not in blob


def test_no_secrets_in_failure_paths(setup):
    clock = SimClock(T0)
    ex = FakeExchange(lambda: int(clock.now().timestamp() * 1000))
    ex.inject("/fapi/v1/algoOrder", RuntimeError(f"boom {SECRET} {KEY}"))
    rc, ex, out, _ = run(setup, ex=ex)
    j, md = reports(setup)
    for blob in (json.dumps(j), md, "\n".join(out)):
        assert KEY not in blob and SECRET not in blob


# ------------------------------------------------------------------------------------------ finally / temizlik
def test_failure_after_entry_flattens_own_position_and_cancels_own_orders(setup):
    clock = SimClock(T0)
    ex = FakeExchange(lambda: int(clock.now().timestamp() * 1000))
    ex.inject("/fapi/v1/algoOrder", RuntimeError("stop kurulamadi"))
    rc, ex, out, _ = run(setup, ex=ex)
    assert rc == 1
    assert ex.pos["XRPUSDT"]["amt"] == 0
    j, _ = reports(setup)
    assert j["results"][-1]["status"] == "KALDI"
    assert any("duzlestirildi" in c for c in j["cleanup"])


def test_cleanup_touches_only_own(setup):
    """Hesapta baslangicta bos; kosu sirasinda 'yabanci' emir eklenirse dokunulmaz."""
    clock = SimClock(T0)
    ex = FakeExchange(lambda: int(clock.now().timestamp() * 1000))

    # yabanci emir 5. 'evet'ten sonra (giris yapildi) eklenir
    calls = {"n": 0}

    def inp2(prompt):
        if prompt.startswith("ONAY"):
            return PHRASE
        calls["n"] += 1
        if calls["n"] == 5:
            ex.algos["foreign-1"] = {"algoId": 5, "cid": "foreign-1", "symbol": "XRPUSDT", "side": "SELL", "type": "STOP_MARKET",
                                     "qty": L.Decimal("1"), "triggerPrice": L.Decimal("1.0"), "workingType": "MARK_PRICE",
                                     "algoStatus": "NEW", "time": 0, "reduce": True}
        return "evet"
    rc, ex, out, _ = run(setup, ex=ex, input_fn=inp2)
    assert ex.algos["foreign-1"]["algoStatus"] == "NEW"          # yabanci emre dokunulmadi
    assert ex.pos["XRPUSDT"]["amt"] == 0


def test_does_not_flatten_foreign_extra_size(setup):
    """Yalniz kendi giris miktari duzlenir; sonradan eklenen yabanci miktar kalir."""
    clock = SimClock(T0)
    ex = FakeExchange(lambda: int(clock.now().timestamp() * 1000))
    calls = {"n": 0}

    def inp(prompt):
        if prompt.startswith("ONAY"):
            return PHRASE
        calls["n"] += 1
        if calls["n"] == 5:                                       # S-4 oncesi: giris yapildi
            ex.fill_market("XRPUSDT", "BUY", "10")
        if calls["n"] == 6:
            return "kapat"
        return "evet"
    rc, ex, out, _ = run(setup, ex=ex, input_fn=inp)
    assert ex.pos["XRPUSDT"]["amt"] == L.Decimal("10")


def test_min_notional_only_and_leverage_from_config(setup):
    rc, ex, out, _ = run(setup)
    j, _ = reports(setup)
    notional = j["results"][1]["data"]["notional"]
    assert 5.0 <= notional <= 2 * 5.0
    lev = [r[2] for r in ex.requests if r[1] == "/fapi/v1/leverage"]
    from trader_engine.config import load_engine_config
    want = load_engine_config(ROOT / "config/engine.base.json", ROOT / "config/engine.learner.json",
                              overlay_path=setup["overlay"]).leverage
    assert lev and all(int(q["leverage"]) == want for q in lev)


def test_dry_run_and_list_no_network_no_keys(setup):
    out = []
    assert M.main(["--env", "live", "--dry-run"], environ={}, say=out.append) == 0
    assert "S-3" in "\n".join(out) and "evet" in "\n".join(out)
    out = []
    assert M.main(["--list"], environ={}, say=out.append) == 0 and out


def test_mask_helpers():
    assert SECRET not in L.mask(f"x {SECRET}", (SECRET,)) and KEY not in L.mask_key(KEY)


def test_no_leverage_in_config_json():
    for p in (ROOT / "config").glob("*.json"):
        assert "leverage" not in p.read_text(), p.name
