"""S2 adim 0a: `metrics.compute_metrics` `fee_only` duzeltmesi -- bagimsiz kabul testleri M-1..M-5.

Kaynak: docs/ml/s2-on-kayit.md §3 (tablo M-1..M-5) ve docs/ml/s2-maliyet-denetimi.md (tek islem ornegi).
M-5'in "oncesi" degerleri HEAD'deki metrics.py'nin `git show` ciktisindan bagimsiz yuklenir; yeni koddan alinmaz.
"""
from __future__ import annotations

import math
import subprocess
import sys
import types
from pathlib import Path

import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

from trader_engine import metrics as NEW  # noqa: E402

_BASE_REF = "a305edc"   # duzeltme oncesi son commit (metrics.py = c51e2b1 icerigi); sabit


def _load_pre_fix():
    """HEAD'deki (duzeltme oncesi) metrics.py'yi ayri bir modul olarak yukler."""
    top = subprocess.run(["git", "rev-parse", "--show-toplevel"], cwd=ROOT, check=True,
                         capture_output=True, text=True).stdout.strip()
    rel = (ROOT / "src/trader_engine/metrics.py").relative_to(top).as_posix()
    src = subprocess.run(["git", "show", f"{_BASE_REF}:{rel}"], cwd=top, check=True,
                         capture_output=True, text=True).stdout
    mod = types.ModuleType("s2_0a_metrics_pre_fix")
    mod.__file__ = f"<{_BASE_REF}:{rel}>"
    mod.__package__ = "trader_engine"
    exec(compile(src, mod.__file__, "exec"), mod.__dict__)
    return mod


try:
    OLD = _load_pre_fix()
except (subprocess.CalledProcessError, OSError):   # sig klon (CI) taban commit'i icermeyebilir
    OLD = None


def _row(i: int, *, side="long", qty=10.0, pe=100.0, ep=100.02, pex=99.0, xp=98.9505, ps=98.5,
         fee_rate=0.0005, funding=0.0, setup="T1", pair="X/USDT", reason="stop", day=1):
    fee_e, fee_x = qty * ep * fee_rate, qty * xp * fee_rate
    gross = qty * (xp - ep) if side == "long" else qty * (ep - xp)
    return dict(
        trade_id=i, pair=pair, side=side, setup=setup, regime="trend_up",
        entry_ts=f"2021-01-{day:02d}T00:00:00Z", exit_ts=f"2021-01-{day:02d}T05:00:00Z",
        entry_price=ep, exit_price=xp, qty=qty, planned_entry=pe, planned_stop=ps, planned_exit=pex,
        exit_reason=reason, fee_entry=fee_e, fee_exit=fee_x, funding_paid=funding, gross_pnl=gross,
        realized_pnl=gross - fee_e - fee_x - funding,
        # defter isaret kurali (ledger.py ~1556/1691): yon ayarli, aleyhte kayma pozitif
        slippage_entry=((ep - pe) / pe) if side == "long" else ((pe - ep) / pe),
        slippage_exit=((pex - xp) / pex) if side == "long" else ((xp - pex) / pex))


def _single_trade_df():
    """Denetimdeki tek islem: long, planli giris 100 / dolum 100,02; planli stop 99 / dolum 98,9505; qty 10; 5 bp."""
    return NEW.enrich_trades(pd.DataFrame([_row(1)]))


def _multi_df(with_slip_cost=True):
    rows = [
        _row(1, qty=10, pe=100.0, ep=100.02, pex=99.0, xp=98.9505, day=1),
        _row(2, qty=3, pe=2000.0, ep=2000.8, pex=2060.0, xp=2058.97, ps=1960.0, setup="R1", reason="tp", day=2,
             funding=0.12),
        _row(3, side="short", qty=7, pe=50.0, ep=49.98, pex=51.0, xp=51.0255, ps=51.0, pair="Y/USDT", day=3),
        _row(4, qty=1.5, pe=30000.0, ep=30006.0, pex=30600.0, xp=30584.7, ps=29700.0, reason="tp", day=4,
             funding=-0.05),
    ]
    df = NEW.enrich_trades(pd.DataFrame(rows))
    if not with_slip_cost:
        df = df.drop(columns=["slip_cost"])
    return df


# --------------------------------------------------------------------------------------------- M-1
def test_M1_native_fee_only_equals_fees_total_and_slip_approx_is_sum_slip_cost():
    df = _multi_df()
    assert (df["slip_cost"] > 0).all(), "senaryo: slip_cost > 0 olan sentetik islemler"
    m = NEW.compute_metrics(df, wallet_start=1000.0)
    assert m["fee_only"] == m["fees_total"]  # tam esitlik
    assert m["slip_approx"] == pytest.approx(float(df["slip_cost"].sum()), rel=1e-12, abs=0)
    assert m["fees_total"] > 0


# --------------------------------------------------------------------------------------------- M-2
def test_M2_audit_single_trade_example():
    m = NEW.compute_metrics(_single_trade_df(), wallet_start=1000.0)
    assert m["fees_total"] == pytest.approx(0.9949, abs=5e-5)
    assert m["fee_only"] == pytest.approx(0.9949, abs=5e-5)
    assert m["fee_only"] != pytest.approx(0.2999, abs=1e-3)  # eski (yanlis) deger degil
    assert m["slip_approx"] == pytest.approx(0.695, abs=5e-4)
    assert m["costs_total"] == pytest.approx(0.9949, abs=5e-5)  # fonlama 0


# --------------------------------------------------------------------------------------------- M-3
def test_M3_compat_mode_keeps_old_behaviour():
    df = _multi_df()
    m = NEW.compute_metrics(df, wallet_start=1000.0, slip_bps=5)
    slip = float((df["qty"] * (df["entry_price"] + df["exit_price"]) * 5e-4).sum())
    assert m["fee_only"] == pytest.approx(m["fees_total"] - slip, rel=1e-12, abs=1e-12)
    assert m["slip_approx"] == pytest.approx(slip, rel=1e-12)
    assert m["fee_only"] != pytest.approx(m["fees_total"], rel=1e-6)  # uyum kipinde fark korunur


# --------------------------------------------------------------------------------------------- M-4
def test_M4_native_without_slip_cost_column():
    df = _multi_df(with_slip_cost=False)
    assert "slip_cost" not in df.columns
    m = NEW.compute_metrics(df, wallet_start=1000.0)
    assert m["slip_approx"] == 0
    assert m["fee_only"] == m["fees_total"]


# --------------------------------------------------------------------------------------------- M-5
def _same(a, b, path=""):
    if isinstance(a, dict):
        assert isinstance(b, dict) and set(a) == set(b), f"anahtar kumesi ayrisiyor: {path}"
        for k in a:
            _same(a[k], b[k], f"{path}.{k}")
    elif isinstance(a, list):
        assert isinstance(b, list) and len(a) == len(b), path
        for i, (x, y) in enumerate(zip(a, b)):
            _same(x, y, f"{path}[{i}]")
    elif isinstance(a, float) and isinstance(b, float) and math.isnan(a) and math.isnan(b):
        pass
    else:
        assert a == b, f"{path}: {a!r} != {b!r}"


@pytest.mark.parametrize("slip_bps", [None, 5])
@pytest.mark.parametrize("single", [True, False])
@pytest.mark.skipif(OLD is None, reason="taban commit klonda yok (sig klon)")
def test_M5_all_other_keys_equal_pre_fix(single, slip_bps):
    df = _single_trade_df() if single else _multi_df()
    new = NEW.compute_metrics(df.copy(), wallet_start=1000.0, slip_bps=slip_bps)
    old = OLD.compute_metrics(df.copy(), wallet_start=1000.0, slip_bps=slip_bps)
    assert set(new) == set(old)  # anahtar kumesi ayni (yeni anahtar yok)
    assert NEW.METRIC_KEYS == OLD.METRIC_KEYS
    n = {k: v for k, v in new.items() if k != "fee_only"}
    o = {k: v for k, v in old.items() if k != "fee_only"}
    _same(n, o)
    assert "fee_only" in new


@pytest.mark.skipif(OLD is None, reason="taban commit klonda yok (sig klon)")
def test_M5_empty_trades_behaviour_unchanged():
    empty = _multi_df().iloc[0:0]
    for kw in ({}, {"slip_bps": 5}):
        new = NEW.compute_metrics(empty, wallet_start=1000.0, **kw)
        old = OLD.compute_metrics(empty, wallet_start=1000.0, **kw)
        _same(new, old)
    # yalniz acik pozisyon (exit_ts bos) -> bos tablo gibi davranir
    open_only = _multi_df().copy()
    open_only["exit_ts"] = None
    _same(NEW.compute_metrics(open_only, wallet_start=1000.0), OLD.compute_metrics(open_only, wallet_start=1000.0))
