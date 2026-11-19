"""Veto uygulamasi duman testleri (spec testleri test_veto_spec.py'de)."""
import importlib.util
import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace

import pytest

from trader_core import budget as B
from trader_core import veto as V

ROOT = Path(__file__).resolve().parents[1]
KEY = "k" * 40
T0 = datetime(2026, 12, 1, 9, 50, 3, 120000, tzinfo=timezone.utc)
PAIRS = ["BTC/USDT", "ETH/USDT"]
CFG = V.load_config(ROOT / "config/veto.live.json")

spec = importlib.util.spec_from_file_location("veto_run", ROOT / "scripts/veto_run.py")
RUN = importlib.util.module_from_spec(spec)
spec.loader.exec_module(RUN)


def pc(p, **kw):
    d = dict(pair=p, regime="range", atr_ratio=1.1, ret_pct={1: -0.42, 4: -1.1, 24: 2.3},
             funding_rate=0.0001, candidate={"long": True, "short": False})
    d.update(kw)
    return V.PairContext(**d)


def snap():
    return V.MarketSnapshot("2026-12-01T09:00:00.000Z", pc("BTC/USDT"), (pc("ETH/USDT"), pc("BTC/USDT")))


def out_text(block_eth_short=True):
    rows = []
    for p in PAIRS:
        for s in ("long", "short"):
            if block_eth_short and (p, s) == ("ETH/USDT", "short"):
                rows.append({"pair": p, "side": s, "action": "block", "reason": "funding", "expires_in_min": 15})
            else:
                rows.append({"pair": p, "side": s, "action": "allow"})
    return json.dumps({"v": 1, "decisions": rows})


def doc_and_sig(now=T0, decisions=None):
    ds = V.parse_model_output(decisions or out_text(), PAIRS)
    ctx = V.build_context(snap())
    return V.sign_document(V.build_document(CFG, ds, now, V.context_sha256(ctx), PAIRS), KEY)


# ---- veto.py
def test_stdlib_only():
    src = (ROOT / "src/trader_core/veto.py").read_text()
    for bad in ("anthropic", "ccxt", "pandas", "freqtrade", "budget"):
        assert f"import {bad}" not in src and f"from {bad}" not in src


def test_config_limits():
    with pytest.raises(V.VetoConfigError):
        V.VetoConfig(ttl_s=3000)
    with pytest.raises(V.VetoConfigError):
        V.VetoConfig(parse_retries=2)
    with pytest.raises(V.VetoConfigError):
        V.VetoConfig(cache_ttl="2h")


def test_context_deterministic_and_closed_set():
    a, b = V.build_context(snap()), V.build_context(snap())
    assert a == b and V.context_sha256(a) == V.context_sha256(b)
    assert [e["pair"] for e in a["pairs"]] == ["BTC/USDT", "ETH/USDT"]
    with pytest.raises(V.VetoError):
        V.build_context(V.MarketSnapshot("x", pc("BTC/USDT", regime="bullish!"), ()))
    n = V.build_context(V.MarketSnapshot("x", pc("BTC/USDT", atr_ratio=float("nan")), ()))
    assert n["btc"]["atr_ratio"] is None


def test_prompt_static_prefix():
    c2 = V.build_context(V.MarketSnapshot("y", pc("BTC/USDT", atr_ratio=3.0), ()))
    p1 = V.build_prompt(CFG, V.build_context(snap()), PAIRS)
    p2 = V.build_prompt(CFG, c2, PAIRS)
    assert p1.system == p2.system and p1.user != p2.user
    assert not any(ch.isdigit() for ch in p1.system)


@pytest.mark.parametrize("mut", [
    lambda t: "Tamam: " + t, lambda t: "```json\n" + t + "\n```",
    lambda t: t.replace("ETH/USDT", "PEPE/USDT"),
    lambda t: t.replace('"action": "allow"', '"action": "allow", "size": 0.5', 1),
    lambda t: json.dumps({"v": 1, "decisions": json.loads(t)["decisions"][:3]}),
    lambda t: t.replace('"reason": "funding", ', ""),
    lambda t: t.replace("funding", "x" * 121),
    lambda t: t.replace('"expires_in_min": 15', '"expires_in_min": 90'),
    lambda t: t.replace('"v": 1', '"v": true'),
    lambda t: t.replace('"expires_in_min": 15', '"expires_in_min": true'),
])
def test_parse_rejects(mut):
    with pytest.raises(V.VetoParseError):
        V.parse_model_output(mut(out_text()), PAIRS)


def test_parse_ok():
    ds = V.parse_model_output(out_text(), PAIRS)
    assert len(ds) == 4 and sum(d.action == "block" for d in ds) == 1


def test_roundtrip_and_lookup(tmp_path):
    p = tmp_path / "v" / "veto.json"
    V.write_veto_file(p, doc_and_sig())
    assert oct(p.stat().st_mode & 0o777) == "0o644"
    st = V.read_veto_file(p, KEY, T0 + timedelta(minutes=1), CFG)
    assert st.ok
    now = T0 + timedelta(minutes=1)
    r = V.lookup(st, "BTC/USDT:USDT", "long", now)
    assert (r.status, r.blocks, r.reason) == ("allowed", False, "ok:2026-12-01T09:50:03.120Z")
    r = V.lookup(st, "ETH/USDT", "short", now)
    assert (r.status, r.reason, r.blocks) == ("blocked", "funding", True)
    r = V.lookup(st, "ETH/USDT", "short", T0 + timedelta(minutes=20))
    assert (r.status, r.reason, r.blocks) == ("stale", "decision_expired", True)
    assert V.lookup(st, "XRP/USDT", "long", now).reason == "pair_side_absent"
    exp = T0 + timedelta(seconds=2700)
    assert V.lookup(st, "BTC/USDT", "long", exp - timedelta(milliseconds=1)).blocks is False
    assert V.lookup(st, "BTC/USDT", "long", exp).status == "stale"
    assert V.read_veto_file(p, KEY, exp, CFG).code == "file_expired"


def test_read_failures(tmp_path):
    p = tmp_path / "veto.json"
    assert V.read_veto_file(p, KEY, T0, CFG).code == "file_missing"
    V.write_veto_file(p, doc_and_sig())
    assert V.read_veto_file(p, None, T0, CFG).code == "key_missing"
    assert V.read_veto_file(p, "short", T0, CFG).code == "key_missing"
    assert V.read_veto_file(p, "z" * 40, T0, CFG).code == "bad_signature"
    raw = p.read_text().replace("funding", "funding2")
    p.write_text(raw)
    assert V.read_veto_file(p, KEY, T0, CFG).code == "bad_signature"
    p.write_text("{not json")
    assert V.read_veto_file(p, KEY, T0, CFG).code == "bad_json"
    p.write_text('{"a":1,"a":2}')
    assert V.read_veto_file(p, KEY, T0, CFG).code == "bad_json"
    p.write_text("x" * 70000)
    assert V.read_veto_file(p, KEY, T0, CFG).code == "file_unreadable"
    V.write_veto_file(p, doc_and_sig())
    assert V.read_veto_file(p, KEY, T0 - timedelta(minutes=3), CFG).code == "clock_skew"
    assert V.lookup(V.VetoState(False, "file_missing"), "BTC/USDT", "long", T0).status == "missing"


def test_unavailable_doc(tmp_path):
    p = tmp_path / "veto.json"
    d = V.build_document(CFG, [], T0, "0" * 64, PAIRS, status="unavailable", reason="budget_daily_cap")
    V.write_veto_file(p, V.sign_document(d, KEY))
    st = V.read_veto_file(p, KEY, T0, CFG)
    assert not st.ok and st.code == "unavailable:budget_daily_cap"
    assert V.lookup(st, "BTC/USDT", "long", T0).status == "missing"


def test_write_failure_keeps_old(tmp_path, monkeypatch):
    p = tmp_path / "veto.json"
    V.write_veto_file(p, doc_and_sig())
    before = p.read_bytes()
    monkeypatch.setattr(V.os, "replace", lambda *a: (_ for _ in ()).throw(OSError("boom")))
    with pytest.raises(V.VetoError):
        V.write_veto_file(p, doc_and_sig(T0 + timedelta(minutes=5)))
    assert p.read_bytes() == before and [x.name for x in tmp_path.iterdir()] == ["veto.json"]


# ---- runner
class FakeMarket:
    def __init__(self, fail=False):
        self.fail = fail

    def fetch(self, cfg, pairs, now):
        if self.fail:
            raise RuntimeError("no data")
        return snap()


class Resp:
    def __init__(self, text, stop="end_turn", **u):
        usage = dict(input_tokens=4800, output_tokens=800, cache_read_input_tokens=1500)
        usage.update(u)
        self.content = [SimpleNamespace(type="text", text=text)]
        self.stop_reason = stop
        self.usage = SimpleNamespace(**usage)


class APIErr(Exception):
    def __init__(self, status=None, msg="err"):
        super().__init__(msg)
        self.status_code = status


class FakeClient:
    def __init__(self, *items):
        self.items, self.calls = list(items), []
        self.messages = SimpleNamespace(create=self._create)

    def _create(self, **kw):
        self.calls.append(kw)
        it = self.items.pop(0)
        if isinstance(it, Exception):
            raise it
        return it


@pytest.fixture
def env(tmp_path):
    (tmp_path / "config").mkdir()
    (tmp_path / "config/veto.live.json").write_text((ROOT / "config/veto.live.json").read_text())
    (tmp_path / "config/engine.base.json").write_text(
        json.dumps({"pairs": ["BTC/USDT:USDT", "ETH/USDT:USDT"]}))
    bcfg = B.BudgetConfig(db_path=str(tmp_path / "b.sqlite"))
    guard = B.BudgetGuard(bcfg, clock=lambda: T0)
    return SimpleNamespace(root=tmp_path, guard=guard, bcfg=bcfg, path=tmp_path / "shared/veto/veto.json",
                           envv={"ANTHROPIC_API_KEY_VETO": "sk-ant-secret123", "TRADER_VETO_HMAC_KEY": KEY})


def run(e, client, market=None, envv=None):
    return RUN.main(["--root", str(e.root)], client=client, market=market or FakeMarket(),
                    budget=e.guard, now_fn=lambda: T0, sleep_fn=lambda s: None,
                    env=e.envv if envv is None else envv)


def test_run_disabled_exits_zero(env, caplog):
    """DD-12 WP-06a: runner devre disi; eski test_run_* (butce/yazma/yeniden deneme) emekliye ayrildi."""
    with caplog.at_level("INFO"):
        assert RUN.main(["--root", str(env.root)], client=None, market=None, budget=env.guard,
                        now_fn=lambda: T0, sleep_fn=lambda s: None, env=env.envv) == 0
    assert "veto devre disi" in caplog.text
    assert not env.path.exists()


def test_cost_arithmetic():
    assert B.BudgetGuard(B.BudgetConfig(db_path=":memory:")).estimate_cost(
        "claude-haiku-5-5", input_tokens=4800, max_output_tokens=1200, cache_write_1h_tokens=1500) == 0.00138
