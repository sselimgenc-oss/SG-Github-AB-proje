#!/usr/bin/env python3
"""research/runs/*.json + research/extra_registry.json -> research/trial_registry.csv"""
import csv
import json
import subprocess
from pathlib import Path

R = Path(__file__).resolve().parent
ROOT = R.parent


def sh(*a):
    return subprocess.run(a, cwd=ROOT, capture_output=True, text=True).stdout.strip()


code = sh("git", "log", "-1", "--format=%h", "--", "user_data/strategies/TraderV1.py", "src/trader_core/signals.py",
          "src/trader_core/risk.py", "src/trader_core/regime.py", "src/trader_core/ledger.py", "config/base.json")
head = sh("git", "rev-parse", "--short", "HEAD")
rows = []
for f in sorted((R / "runs").glob("*.json")):
    d = json.loads(f.read_text())
    arm = f"fee x{d['fee_mult']:g} + {d['slip_bps']:g}bps (fee_eff={d['fee_eff']*100:.3f}%/taraf)"
    rows.append(dict(id=d["id"], timestamp=d["timestamp"], git_commit=f"{code} (HEAD {head})", strategy=d["strategy"],
                     params=json.dumps(d["params"], sort_keys=True), period=f"{d['period']} {d['timerange']}", cost_arm=arm,
                     trigger_tf=d["trigger_tf"], trades=d.get("n_trades"),
                     expectancy_R=None if d.get("expectancy_R") is None else round(d["expectancy_R"], 4),
                     PF=None if d.get("profit_factor") is None else round(d["profit_factor"], 4),
                     maxDD=None if d.get("max_dd_pct") is None else f"{d['max_dd_pct']:.2f}%", notes=d.get("notes", "")))
extra = R / "extra_registry.json"
if extra.exists():
    for e in json.loads(extra.read_text()):
        e.setdefault("git_commit", f"{code} (HEAD {head})")
        e.setdefault("strategy", "TraderV1Analysis (TraderV1 alt sinifi)")
        rows.append(e)
rows.sort(key=lambda r: r["timestamp"])
cols = ["id", "timestamp", "git_commit", "strategy", "params", "period", "cost_arm", "trigger_tf", "trades",
        "expectancy_R", "PF", "maxDD", "notes"]
with open(R / "trial_registry.csv", "w", newline="") as fh:
    w = csv.DictWriter(fh, fieldnames=cols)
    w.writeheader()
    for i, r in enumerate(rows, 1):
        r = {c: r.get(c, "") for c in cols}
        r["id"] = f"{i:03d}:{r['id']}"
        w.writerow(r)
print(len(rows), "satir")
