#!/usr/bin/env python3
"""S2 deneme baslaticisi (docs/ml/s2-on-kayit.md §4): sabit bayraklarla motor kosusu + s2_eval + registry satiri.

  python research/s2_run.py --trial {BASE,S2-1,S2-2}
  python research/s2_run.py --explore YYYYMMDD-YYYYMMDD [--trial ...] [--paranoid [N]]

Serbest parametre yok. Onkosullar (sirayla): arguman/aralik, temiz agac, on kayit satiri (tam kosuda S2-*),
cikti dizini yok. Ret = cikis 2, hicbir motor kosusu baslamadan.
"""
from __future__ import annotations

import argparse
import csv
import json
import re
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
REGISTRY_PATH = REPO_ROOT / "research" / "trial_registry.csv"
OUT_ROOT = REPO_ROOT / "var" / "backtests"

TRIALS = ("BASE", "S2-1", "S2-2")
RUN_IDS = {"BASE": "s2_base_v1b", "S2-1": "s2_1_4h", "S2-2": "s2_2_limit"}
STRATEGY = {"BASE": "price_action_v1", "S2-1": "price_action_v1_4h", "S2-2": "price_action_v1"}
FULL_PERIOD = "20210101-20260501"
EXPLORE_LO, EXPLORE_HI = "20210101", "20240101"
_ID_RE = re.compile(r"^(?:\d+:)?(?P<name>.*)$")


def _git_clean() -> bool:
    r = subprocess.run(["git", "status", "--porcelain", "--untracked-files=no"], cwd=REPO_ROOT,
                       capture_output=True, text=True)
    return r.returncode == 0 and r.stdout.strip() == ""


def _run_backtest(argv) -> int:
    sys.path.insert(0, str(REPO_ROOT / "src"))
    from trader_engine import backtest as B
    return B.main(list(argv))


def _registry_names(path: Path) -> list[str]:
    path = Path(path)
    if not path.exists():
        return []
    with open(path, newline="", encoding="utf-8") as fh:
        return [_ID_RE.match(r.get("id", "") or "").group("name") for r in csv.DictReader(fh)]


def _fail(msg: str) -> int:
    print(f"s2_run ret: {msg}", file=sys.stderr)
    return 2


def _parse_range(s: str):
    m = re.fullmatch(r"(\d{8})-(\d{8})", s or "")
    if not m:
        return None
    lo, hi = m.group(1), m.group(2)
    try:
        datetime.strptime(lo, "%Y%m%d")
        datetime.strptime(hi, "%Y%m%d")
    except ValueError:
        return None
    if not (EXPLORE_LO <= lo < hi <= EXPLORE_HI):
        return None
    return lo, hi


def _register_strategy(trial: str) -> str | None:
    """Return an error message if the strategy cannot be made available, else None."""
    if trial == "BASE":
        return None
    sys.path.insert(0, str(REPO_ROOT / "src"))
    if trial == "S2-1":
        try:
            from trader_engine.strategies import price_action_v1_4h as mod
            from trader_engine.strategies import registry as reg
        except ImportError:
            return "S2-1 strategy (price_action_v1_4h) not implemented yet (step 1a)"
        reg._FACTORIES["price_action_v1_4h"] = mod.make_v1b_4h
        return None
    return f"{trial} run path not implemented yet (step 2a)"


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(allow_abbrev=False)
    ap.add_argument("--trial", choices=TRIALS, default=None)
    ap.add_argument("--explore", default=None, metavar="YYYYMMDD-YYYYMMDD")
    ap.add_argument("--paranoid", nargs="?", const=200, type=int, default=None)
    try:
        a = ap.parse_args(argv)
    except SystemExit as e:
        return 2 if e.code not in (0, None) else 0

    # (1) argument / range checks
    explore = a.explore is not None
    if not explore and a.trial is None:
        return _fail("--trial or --explore required")
    if a.paranoid is not None and not explore:
        return _fail("--paranoid is only allowed with --explore")
    trial = a.trial or "BASE"
    if explore:
        rng = _parse_range(a.explore)
        if rng is None:
            return _fail(f"--explore range must be within [{EXPLORE_LO}, {EXPLORE_HI}] and lo < hi: {a.explore}")
        period = f"{rng[0]}-{rng[1]}"
        run_id = f"{RUN_IDS[trial]}_x{rng[0]}_{rng[1]}"
        out_root = Path(OUT_ROOT) / "s2_explore"
    else:
        period = FULL_PERIOD
        run_id = RUN_IDS[trial]
        out_root = Path(OUT_ROOT)

    # (2) clean tree
    if not _git_clean():
        return _fail("working tree not clean (tracked changes)")

    # (3) pre-registration row (full run of S2-* only), and single-run rule
    names = _registry_names(REGISTRY_PATH)
    if not explore and trial.startswith("S2-"):
        if f"{trial}_onkayit" not in names:
            return _fail(f"no pre-registration row '{trial}_onkayit' in registry")
        if f"{trial}_sonuc" in names:
            return _fail(f"{trial} already has a result row (single full run only)")

    # (4) output dir must not exist
    run_dir = out_root / run_id
    if run_dir.exists():
        return _fail(f"output dir exists: {run_dir}")

    err = _register_strategy(trial)
    if err:
        return _fail(err)

    bt = ["--id", run_id, "--out-root", str(out_root), "--period", period, "--tf", "1h", "--fill-model", "native",
          "--strategy", STRATEGY[trial], "--synthetic-rules", "--target-trade-risk", "0.005"]
    if a.paranoid is not None:
        bt += ["--paranoid", str(a.paranoid)]
    rc = _run_backtest(bt)
    if rc != 0:
        print(f"s2_run: backtest exit {rc}", file=sys.stderr)
        return rc

    sys.path.insert(0, str(Path(__file__).resolve().parent))
    import s2_eval
    n_reg = sum(1 for n in names if re.fullmatch(r"S2-\d+_onkayit", n))
    try:
        res = s2_eval.evaluate(run_dir, n_reg)
    except (ValueError, OSError, KeyError) as e:
        return _fail(f"s2_eval failed: {e}")
    print(s2_eval.format_table(res))

    if not explore and trial.startswith("S2-"):
        import run_bt_engine
        meta = json.loads((run_dir / "meta.json").read_text())
        summ = json.loads((run_dir / "summary.json").read_text())
        verdict = "GECTI" if res["passed"] else f"KALDI (ilk kalan {res['first_failure']})"
        dd = summ.get("max_dd_pct")
        e, pf = summ.get("expectancy_R"), summ.get("profit_factor")
        run_bt_engine.append_registry(Path(REGISTRY_PATH), dict(
            id=f"{trial}_sonuc", timestamp=datetime.now(timezone.utc).isoformat(timespec="seconds"),
            git_commit=meta.get("git_commit", ""), strategy=f"engine:{meta.get('strategy')}@{meta.get('strategy_version')}",
            params="{}", period=FULL_PERIOD, cost_arm="native: taker 5bp/taraf, kayma 2/5bp, fonlama",
            trigger_tf=meta.get("trigger_tf", ""), trades=summ.get("n_trades"),
            expectancy_R="" if e is None else round(e, 4), PF="" if pf is None else round(pf, 4),
            maxDD="" if dd is None else f"{dd:.2f}%",
            notes=f"SONUC {verdict}; run {run_id}; K1 sinav penceresi n={res['exam_window']['n_trades']}"))
    return 0


if __name__ == "__main__":
    sys.exit(main())
