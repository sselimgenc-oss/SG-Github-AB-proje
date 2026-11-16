"""StoreMarketSource (veto piyasa kaynagi): temp MarketStore + sentetik barlar; ccxt yasagi korumasi."""
from __future__ import annotations

import importlib.util
import math
import re
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from trader_core import veto as V
from trader_engine.bars import to_ms
from trader_engine.marketdata.store import MarketStore
from trader_engine.types import Bar

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("veto_run", ROOT / "scripts/veto_run.py")
RUN = importlib.util.module_from_spec(spec)
spec.loader.exec_module(RUN)
CFG = V.load_config(ROOT / "config/veto.json")
NOW = datetime(2026, 11, 16, 12, 0, tzinfo=timezone.utc)
PAIRS = ["BTC/USDT", "ETH/USDT"]
H = {"1h": 3600, "4h": 14400}


def _bars(pair, tf, n, end, last_open_extra=0):
    """n kapanmis bar: son bar close_ts == end; ek olarak last_open_extra adet kapanmamis."""
    step = timedelta(seconds=H[tf])
    out = []
    for i in range(n + last_open_extra):
        t = end - step * (n - i)
        px = 100 + 5 * math.sin(i / 7) + i * 0.05
        out.append(Bar(pair, "last", tf, t, px, px + 1, px - 1, px + 0.3, 10.0))
    return out


def make_store(tmp_path, *, n4=200, n1=80, end=NOW, extra=0, pairs=PAIRS):
    p = tmp_path / "var" / "market.sqlite"
    st = MarketStore(p)
    for pair in pairs:
        st.put_bars(_bars(pair, "4h", n4, end - timedelta(hours=end.hour % 4), extra), now_ms=to_ms(NOW))
        st.put_bars(_bars(pair, "1h", n1, end, extra), now_ms=to_ms(NOW))
    st.close()
    return p


def fetch(path, now=NOW):
    return RUN.StoreMarketSource(db_path=path).fetch(CFG, PAIRS, now)


def test_normal(tmp_path):
    snap = fetch(make_store(tmp_path))
    assert [p.pair for p in snap.pairs] == PAIRS and snap.btc.pair == "BTC/USDT"
    assert snap.as_of == V.format_ts(NOW)
    assert set(snap.pairs[0].ret_pct) == {1, 4, 24} and snap.pairs[0].funding_rate is None
    V.build_context(snap)  # baglam kurulabilir


def test_stale_store(tmp_path):
    p = make_store(tmp_path)
    with pytest.raises(RuntimeError, match="bayat"):
        fetch(p, NOW + timedelta(hours=5))


def test_missing_store(tmp_path):
    with pytest.raises(RuntimeError, match="yok"):
        fetch(tmp_path / "nope.sqlite")


def test_too_few_candles(tmp_path):
    with pytest.raises(RuntimeError, match="eksik"):
        fetch(make_store(tmp_path, n4=20))
    with pytest.raises(RuntimeError, match="eksik"):
        fetch(make_store(tmp_path / "b", n1=10))


def test_open_candle_excluded(tmp_path):
    p = make_store(tmp_path, extra=1)  # NOW'da acilan (kapanmamis) 1s mum da depoda
    snap = fetch(p)
    assert snap.as_of == V.format_ts(NOW)  # kapanmamis mum as_of'u ileri tasimaz
    base = fetch(make_store(tmp_path / "c"))
    assert V.build_context(snap) == V.build_context(base) or \
        V.context_sha256(V.build_context(snap)) == V.context_sha256(V.build_context(base))


def test_missing_store_fails_closed_exit10(tmp_path):
    # main(): depo yok -> cikis 10 (kaynak enjekte edilmedi)
    (tmp_path / "config").mkdir()
    (tmp_path / "config/veto.json").write_text((ROOT / "config/veto.json").read_text())
    (tmp_path / "config/base.json").write_text('{"exchange":{"pair_whitelist":["BTC/USDT:USDT"]}}')
    from trader_core import budget as B
    guard = B.BudgetGuard(B.BudgetConfig(db_path=str(tmp_path / "b.sqlite")), clock=lambda: NOW)
    rc = RUN.main(["--root", str(tmp_path)], budget=guard, now_fn=lambda: NOW, sleep_fn=lambda s: None,
                  env={"ANTHROPIC_API_KEY_VETO": "sk-ant-x", "TRADER_VETO_HMAC_KEY": "k" * 40})
    assert rc == 10


def test_no_ccxt_imports():
    pat = re.compile(r"^\s*(import|from)\s+ccxt\b", re.M)
    bad = []
    for base in ("src", "scripts"):
        for f in (ROOT / base).rglob("*.py"):
            if f.name == "freqtrade_offline.py":
                continue
            if pat.search(f.read_text(encoding="utf-8")):
                bad.append(str(f.relative_to(ROOT)))
    assert not bad, bad
