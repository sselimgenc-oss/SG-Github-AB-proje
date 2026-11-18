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
                environ=environ, rest_factory=factory, clock=clock, input_fn=inputs or (lambda *_: ""), say=out.append,
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


# ====================================================================================== B7 mentor kararlari (R1-R7)
def _res(tmp_path, name=None):
    j = json.loads(next((tmp_path / "smoke").iterdir()).joinpath("result.json").read_text())["results"]
    return j[0] if name is None else next(r for r in j if r["name"] == name)


def test_new_b0_steps_registered_and_in_group():
    for n in ("b0-t04", "b0-t07", "b0-t08", "b0-t12"):
        assert n in M.STEPS and M.STEPS[n].group == "b0"
    names = [s.name for s in M.resolve_steps(["b0"])]
    assert names.index("b0-t04") < names.index("b0-t05") < names.index("b0-t07") < names.index("b0-t08") < names.index("b0-t12")
    assert M.STEPS["b0-t12"].trades is False
    for st in ("KISMI", "GOZLEM"):
        assert st in L.STATUSES


def test_t04_two_stops_accepted_and_fate_of_loose_stop_recorded(tmp_path):
    def nudge(ex):                      # siki stop (1.9994) tetiklenir, gevsek (1.9000) tetiklenmez
        ex.set_mark("XRPUSDT", "1.99")
    rc, ex, out, _ = run(tmp_path, ["--env", "testnet", "--step", "b0-t04", "--trigger-wait-s", "6"], on_wait=nudge)
    assert rc == 0, out
    r = _res(tmp_path)
    assert r["status"] == "GECTI" and r["data"]["iki_stop_kabul"] is True
    assert r["data"]["gevsek_akibet"] == "NEW"          # fake: digeri tetiklenmedi, duruyor -> akibet kaydedildi
    assert r["data"]["mark_son"] and "tetik" in r["data"]


def test_t04_second_stop_rejected_is_farkli(tmp_path, monkeypatch):
    orig = M.Ctx.stop
    calls = []

    def stop(self, pct, qty=None, role="stop"):
        calls.append(pct)
        if len(calls) == 2:                                     # ikinci stop kabul edilmez
            class R:
                status = "rejected"
            return "x", 0.0, R()
        return orig(self, pct, qty, role)
    monkeypatch.setattr(M.Ctx, "stop", stop)
    rc, ex, out, made = run(tmp_path, ["--env", "testnet", "--step", "b0-t04"])
    assert rc == 1 and _res(tmp_path)["status"] == "FARKLI"
    assert float(made["rest"].position_risk("XRPUSDT")[0]["positionAmt"]) == 0


def test_t07_records_child_order_id_usertrades_and_force_orders(tmp_path):
    rc, ex, out, made = run(tmp_path, ["--env", "testnet", "--step", "b0-t07", "--trigger-wait-s", "6"],
                            on_wait=lambda ex: ex.set_mark("XRPUSDT", "1.0"))
    assert rc == 0, out
    d = _res(tmp_path)["data"]
    assert _res(tmp_path)["status"] == "GECTI"
    assert d["userTrades_eslesen"] >= 1 and d["commissionAsset"] == ["USDT"] and d["realizedPnl"]
    assert d["cocuk_kimlik_modu"] == "auto" and d["cocuk_clientOrderId"].startswith("algo_auto_")   # fake temkinli varsayilan
    assert "likidasyon" in d["liquidation_queryable"] or "gozlenemedi" in d["liquidation_queryable"]
    assert ex.count("forceOrders") == 1
    assert float(made["rest"].position_risk("XRPUSDT")[0]["positionAmt"]) == 0


def test_t07_no_trigger_is_beklemede_and_flat(tmp_path):
    rc, ex, out, made = run(tmp_path, ["--env", "testnet", "--step", "b0-t07", "--trigger-wait-s", "3"])
    assert rc == 1 and _res(tmp_path)["status"] == "BEKLEMEDE"
    assert float(made["rest"].position_risk("XRPUSDT")[0]["positionAmt"]) == 0
    assert not made["rest"].open_conditionals("XRPUSDT")


def test_t08_identity_reuse_codes_and_timeout_query(tmp_path):
    rc, ex, out, made = run(tmp_path, ["--env", "testnet", "--step", "b0-t08"])
    assert rc == 0, out
    d = _res(tmp_path)["data"]
    assert d["a_acik_emirle_ayni_kimlik"] == -4116
    assert "b_dolmus_kimlikle_ikinci" in d
    assert d["c_kimlikle_sorgu_buldu"] is True and d["c_yok_yaniti_bos"] is True and "c_yok_yaniti_sn" in d
    assert float(made["rest"].position_risk("XRPUSDT")[0]["positionAmt"]) == 0
    assert not made["rest"].open_conditionals("XRPUSDT")


def test_t12_funding_is_read_only_and_non_blocking(tmp_path):
    clock = SimClock(T0)
    ex = FakeExchange(lambda: int(clock.now().timestamp() * 1000))
    ex.add_funding("XRPUSDT", "-0.0123", int(clock.now().timestamp() * 1000) - 3600_000)
    rc, ex, out, _ = run(tmp_path, ["--env", "testnet", "--step", "b0-t12"], ex=ex)
    assert rc == 0, out                                         # GOZLEM engelleyici degil
    r = _res(tmp_path)
    assert r["status"] == "GOZLEM" and r["data"]["satir"] == 1 and r["data"]["son"]["income"] == "-0.0123"
    assert not [x for x in ex.requests if x[0] == "POST" and "order" in x[1].lower()]       # emir yok (yalniz okuma)


def _two_positions(ex, n=2):
    from decimal import Decimal as D
    for sym, qty in (("XRPUSDT", "10"), ("DOGEUSDT", "40"))[:n]:
        ex.fill_market(sym, "BUY", qty)
        ex._new_cond(sym, "SELL", "STOP_MARKET", D(qty), D("1.0"), "MARK_PRICE", f"trTx-engine-{sym}")


def _kill_cli(ex, calls):
    def cli(args):
        calls.append(args)
        if args[0] == "kill" and "--clear" not in args:         # motorun KILL tepkisi: her seyi duzle, stoplari iptal et
            for sym in list(ex.pos):
                ex.external_close(sym)
            for a in ex.algos.values():
                a["algoStatus"] = "CANCELED"
        return 0
    return cli


def test_t15_counts_positions_account_wide_and_passes_with_two(tmp_path, monkeypatch):
    calls = []
    clock = SimClock(T0)
    ex = FakeExchange(lambda: int(clock.now().timestamp() * 1000))
    monkeypatch.setattr(M, "_cli", _kill_cli(ex, calls))
    rc, ex, out, _ = run(tmp_path, ["--env", "testnet", "--step", "t15"], ex=ex, inputs=lambda *_: _two_positions(ex) or "")
    assert rc == 0, out
    r = _res(tmp_path)
    assert r["status"] == "GECTI" and r["data"]["pozisyon_oncesi"] == 2 and r["data"]["stop_oncesi"] == 2
    assert any(c[0] == "kill" and "--clear" in c and "--env" in c and "--config-dir" in c for c in calls)    # DD-8 E2: --config-dir verilir


def test_t15_single_position_is_kismi_not_gecti(tmp_path, monkeypatch):
    calls = []
    clock = SimClock(T0)
    ex = FakeExchange(lambda: int(clock.now().timestamp() * 1000))
    monkeypatch.setattr(M, "_cli", _kill_cli(ex, calls))
    rc, ex, out, _ = run(tmp_path, ["--env", "testnet", "--step", "t15"], ex=ex, inputs=lambda *_: _two_positions(ex, 1) or "")
    r = _res(tmp_path)
    assert r["status"] == "KISMI" and rc == 1 and r["data"]["pozisyon_oncesi"] == 1
    assert any("KISMI" in n for n in r["notes"])


def test_t15_second_symbol_still_open_is_kaldi(tmp_path, monkeypatch):
    """Tek sembol (XRP) bakmak yetmez: KILL yalniz XRP'yi duzlerse DOGE hesap genelinde gorulur ve KALDI olur."""
    clock = SimClock(T0)
    ex = FakeExchange(lambda: int(clock.now().timestamp() * 1000))

    def cli(args):
        if args[0] == "kill" and "--clear" not in args:
            ex.external_close("XRPUSDT")
            for a in ex.algos.values():
                a["algoStatus"] = "CANCELED"
        return 0
    monkeypatch.setattr(M, "_cli", cli)
    rc, ex, out, _ = run(tmp_path, ["--env", "testnet", "--step", "t15"], ex=ex, inputs=lambda *_: _two_positions(ex) or "")
    assert rc == 1 and _res(tmp_path)["status"] == "KALDI"


def test_t13_records_mark_and_last_price_at_trigger(tmp_path, monkeypatch):
    monkeypatch.setattr(M.Ctx, "last_price", lambda self: M.Decimal("1.0001"))
    rc, ex, out, _ = run(tmp_path, ["--env", "testnet", "--step", "t13", "--trigger-wait-s", "6"],
                         on_wait=lambda ex: ex.set_mark("XRPUSDT", "1.0"))
    d = _res(tmp_path)["data"]
    assert rc == 0 and _res(tmp_path)["status"] == "GECTI"
    assert d["mark_son"] == "1.0" and d["son_fiyat_son"] == "1.0001" and d["tetik"] == "1.9994"
    assert M.Decimal(d["mark_min"]) <= M.Decimal(d["tetik"]) and d["mark_esik_gecis_ornegi"]["mark"] == "1.0"


def test_t13_fires_without_mark_crossing_is_farkli(tmp_path, monkeypatch):
    monkeypatch.setattr(M.Ctx, "observe", lambda self: {"mark": M.Decimal("2.0"), "last": M.Decimal("1.0")})   # mark hic gecmedi
    rc, ex, out, _ = run(tmp_path, ["--env", "testnet", "--step", "t13", "--trigger-wait-s", "6"],
                         on_wait=lambda ex: ex.set_mark("XRPUSDT", "1.0"))
    r = _res(tmp_path)
    assert rc == 1 and r["status"] == "FARKLI" and any("mark esigi" in n for n in r["notes"])
    assert r["data"]["son_fiyat_once_gecti"] is True            # son fiyat esigi gecti, mark gecmedi: kayit altinda


def test_t13_tight_stop_and_wait_are_tunable_with_limits(tmp_path):
    rc, ex, out, _ = run(tmp_path, ["--env", "testnet", "--step", "t13", "--trigger-wait-s", "6", "--t13-stop-pct", "0.001"],
                         on_wait=lambda ex: ex.set_mark("XRPUSDT", "1.0"))
    assert rc == 0 and _res(tmp_path)["data"]["tetik"] == "1.998"
    for bad in (["--t13-stop-pct", "0.5"], ["--t13-stop-pct", "0"], ["--trigger-wait-s", "99999"]):
        rc, ex, out, _ = run(tmp_path, ["--env", "testnet", "--step", "t13", *bad])
        assert rc == 2 and not ex.requests
    rc, ex, out, _ = run(tmp_path, ["--env", "testnet", "--step", "t13", "--trigger-wait-s", "600"],
                         on_wait=lambda ex: ex.set_mark("XRPUSDT", "1.0"))
    assert rc == 0                                              # uzun bekleme izinli (tetikte hemen biter)


def test_d4_without_mark_crossing_is_farkli(tmp_path):
    def trigger_without_mark(*_):
        ex_.external_close("XRPUSDT")                           # pozisyon kapandi ama mark hic esigi gecmedi
        return ""
    clock = SimClock(T0)
    ex_ = FakeExchange(lambda: int(clock.now().timestamp() * 1000))
    rc, ex, out, _ = run(tmp_path, ["--env", "testnet", "--step", "d4"], ex=ex_, inputs=trigger_without_mark)
    r = _res(tmp_path)
    assert rc == 1 and r["status"] == "FARKLI" and r["data"]["mark_son"] == "2.0"
    assert any(n.startswith("mark_son=2.0") for n in r["notes"])


def test_d4_records_mark_when_stop_fires(tmp_path):
    clock = SimClock(T0)
    ex_ = FakeExchange(lambda: int(clock.now().timestamp() * 1000))
    rc, ex, out, _ = run(tmp_path, ["--env", "testnet", "--step", "d4"], ex=ex_, inputs=lambda *_: ex_.set_mark("XRPUSDT", "1.0") or "")
    r = _res(tmp_path)
    assert r["data"]["mark_son"] == "1.0" and r["status"] != "FARKLI"


def test_results_template_lists_manual_ledger_checks_with_exact_commands():
    doc = (ROOT / "docs" / "motor" / "11-testnet-sonuc.md").read_text(encoding="utf-8")
    assert "sqlite3 var-testnet/learner/ledger.sqlite" in doc
    for ref in ("T-13", "T-15", "T-16", "D-4", "trail_stop", "force_exit"):
        assert ref in doc
    for ref in ("T-04", "T-07", "T-08", "T-12"):
        assert ref in doc
    spec = (ROOT / "docs" / "motor" / "11-canli-broker.md").read_text(encoding="utf-8")
    assert "probe_testnet" not in spec


# ---- R7: canli acilis izin denetimi: sert hata, onay ile asilamaz
@pytest.mark.parametrize("restr", [{"enableWithdrawals": True},                                   # kismi govde: yalniz ihlal
                                   {"enableReading": True, "enableFutures": True, "enableWithdrawals": False,
                                    "enableInternalTransfer": False, "permitsUniversalTransfer": False, "ipRestrict": False},
                                   {"enableReading": True, "enableFutures": True, "enableWithdrawals": True,
                                    "enableInternalTransfer": False, "permitsUniversalTransfer": False, "ipRestrict": True}])
def test_live_startup_hard_fails_on_withdrawals_or_no_ip_restriction_even_with_attestation(restr, monkeypatch):
    from test_live_broker_spec import FakeRest, make_broker, T0 as BT0
    from trader_engine.errors import EngineExit
    monkeypatch.setenv("LIVE_PERMISSION_ATTESTED", BT0.date().isoformat())       # beyan ihlali ASAMAZ
    rest = FakeRest(SimClock(BT0), "live")
    rest.restr.clear()
    rest.restr.update(restr)
    b, _, _ = make_broker("live", startup=False, rest=rest)
    with pytest.raises(EngineExit) as ei:
        b.startup_check()
    assert ei.value.code == 8 and "key_permission:" in str(ei.value)
    assert not [c for c in rest.calls if c[0] == "account"]                       # hesap/emir yoluna hic gecilmedi


@pytest.mark.parametrize("att", [False, True])
def test_live_startup_unverifiable_restrictions_exits_8_and_unreachable_exits_5(monkeypatch, att):
    """DD-8 O6: sonuc beyana bagli degil (att=True ayni sonucu verir). Bozuk/eksik govde -> 8; ag/zaman asimi -> 5 (yeniden denenir)."""
    from test_live_broker_spec import FakeRest, make_broker, T0 as BT0
    from trader_engine.errors import EngineExit
    from trader_engine.exchange.binance_rest import ExchangeUncertain
    if att:
        monkeypatch.setenv("LIVE_PERMISSION_ATTESTED", BT0.date().isoformat())
    else:
        monkeypatch.delenv("LIVE_PERMISSION_ATTESTED", raising=False)
    rest = FakeRest(SimClock(BT0), "live")
    rest.restr = {"foo": 1}
    b, _, _ = make_broker("live", startup=False, rest=rest)
    with pytest.raises(EngineExit) as ei:
        b.startup_check()
    assert ei.value.code == 8 and "key_permission_unverifiable" in str(ei.value)
    rest = FakeRest(SimClock(BT0), "live")
    rest.sticky["api_restrictions"] = ExchangeUncertain("down")
    b, _, _ = make_broker("live", startup=False, rest=rest)
    with pytest.raises(EngineExit) as ei:
        b.startup_check()
    assert ei.value.code == 5 and "exchange_unreachable" in str(ei.value)


def test_smoke_testnet_ack_flag_never_applies_to_live(tmp_path):
    """`--ack-no-withdraw` yalniz testnet betigindedir: live reddedilir (onay bayragi canli yolu acmaz); cli run'da yok."""
    rc, ex, out, _ = run(tmp_path, ["--env", "live", "--step", "b0-preflight"])
    assert rc == 2 and not ex.requests
    import trader_engine.cli as cli
    assert "ack" not in open(cli.__file__, encoding="utf-8").read().lower().replace("backtest", "")
