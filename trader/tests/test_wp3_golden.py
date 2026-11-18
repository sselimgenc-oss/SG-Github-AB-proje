"""WP-3 K1/K2 altin karsilastirmasi (spec defter-ek-alanlar §10). lead: ayri dosya - taban kosusu gercek gecmis veriyi
okur; spec dosyasi kilitli-donem tarihlerini belge metninde andigi icin statik kilit gercek-veri dosyasinda buna izin vermez.
Kosu donemi 20250101-20250401 (kilitli donemin disinda). WP3_GOLDEN=1 ile calisir (~8 dk)."""
from __future__ import annotations

import hashlib
import json
import os
import sqlite3
import subprocess
import sys
from pathlib import Path

import pandas as pd  # noqa: F401
import pytest

from test_wp3_spec import BASE_REF, TRADER, _golden_cmd, _sha, metrics_mod, table_cols  # noqa: E402


@pytest.mark.slow
@pytest.mark.skipif(os.environ.get("WP3_GOLDEN") != "1", reason="set WP3_GOLDEN=1 (needs local history; ~15 min)")
@pytest.mark.parametrize("extra", [[], ["--record-shadow"]], ids=["K1", "K2"])
def test_K1_K2_golden_backtest_equal_to_base(tmp_path, extra):
    base_src = tmp_path / "base_src"
    base_src.mkdir()
    tar = subprocess.run(["git", "-C", str(TRADER), "archive", BASE_REF, "--format=tar", "src", "config"],
                         capture_output=True, timeout=120)
    if tar.returncode != 0:
        pytest.skip("git archive of the base commit failed")
    subprocess.run(["tar", "-x", "-C", str(base_src)], input=tar.stdout, check=True)
    (base_src / "var").mkdir()                      # lead: taban kendi config/'i ile, cwd=base_src kosar (config cwd'ye goredir)
    (base_src / "var" / "history").symlink_to(TRADER / "var" / "history")
    outs = {}
    for tag, src in (("base", base_src / "src"), ("new", TRADER / "src")):
        out = tmp_path / f"out_{tag}"
        env = dict(os.environ, PYTHONPATH=str(src))
        cmd = _golden_cmd(extra if tag == "new" else [], out, src)
        r = subprocess.run(cmd, cwd=str(base_src if tag == "base" else TRADER), env=env, capture_output=True, text=True, timeout=7200)
        assert r.returncode == 0, r.stderr[-2000:]
        outs[tag] = out / "wp3_k1"
    b, n = outs["base"], outs["new"]
    for f in ("trades.csv", "open_at_end.json"):
        assert _sha(b / f) == _sha(n / f), f
    # S2 0a: summary.json yalniz fee_only'de ayrisir (native: fee_only == fees_total; taban: fees_total - slip_approx)
    sb, sn = json.loads((b / "summary.json").read_text()), json.loads((n / "summary.json").read_text())
    fo_b, fo_n = sb.pop("fee_only"), sn.pop("fee_only")
    assert sb == sn
    assert fo_n == sn["fees_total"]
    assert fo_b == pytest.approx(sb["fees_total"] - sb["slip_approx"])
    mb, mn = json.loads((b / "meta.json").read_text()), json.loads((n / "meta.json").read_text())
    for k in ("git_commit", "duration_s"):
        mb.pop(k, None)
        mn.pop(k, None)
    for m in (mb, mn):                               # lead: komut satiri (--out-root yolu, --record-shadow) her zaman farkli
        (m.get("flags") or {}).pop("argv", None)
    assert mb == mn
    q = lambda p, s: [tuple(r) for r in sqlite3.connect(f"file:{p}?mode=ro", uri=True).execute(s)]  # noqa: E731
    lb, ln = b / "ledger.sqlite", n / "ledger.sqlite"
    assert q(lb, "SELECT * FROM v_decisions ORDER BY id") == q(ln, "SELECT * FROM v_decisions ORDER BY id")
    cols = ",".join(table_cols(lb, "v_trades"))
    assert q(lb, f"SELECT {cols} FROM v_trades ORDER BY trade_id") == q(ln, f"SELECT {cols} FROM v_trades ORDER BY trade_id")
    for t in ("param_versions", "param_activations"):
        assert q(lb, f"SELECT * FROM {t} ORDER BY id") == q(ln, f"SELECT * FROM {t} ORDER BY id")
    ntr = q(ln, "SELECT COUNT(*) FROM v_trades")[0][0]
    assert ntr >= 20, "window too small (spec K1 item 5): widen the period"
    shadow = q(ln, "SELECT pair, side, setup, trigger_tf, bar_close_ts, block FROM shadow_decisions")
    if extra:
        assert not [r for r in shadow if r[3] == "15m" or r[5] == "tf_15m"]
        dec = {(r[0], r[1], r[2], r[3], r[4]) for r in q(ln, "SELECT pair, side, setup, trigger_tf, bar_close_ts "
                                                           "FROM v_decisions")}
        assert not {r[:5] for r in shadow} & dec
    else:
        assert shadow == []
    # M8
    hdr = (n / "equity_mtm.csv").read_text().splitlines()[0]
    assert hdr == "ts,wallet,equity,equity_low,n_open"
    mt = json.loads((n / "mtm.json").read_text())
    summ = json.loads((n / "summary.json").read_text())
    assert mt["schema"] == "mtm/1" and mt["max_dd_realized_pct"] == summ["max_dd_pct"]
    assert mt["max_dd_mtm_low_pct"] >= mt["max_dd_mtm_pct"]
    df = pd.read_csv(n / "equity_mtm.csv")
    st = metrics_mod().drawdown_stats(df["equity"].tolist(), df["equity_low"].tolist(), mt["wallet_start"])
    for k, v in st.items():
        if k in mt:
            assert mt[k] == pytest.approx(v)
