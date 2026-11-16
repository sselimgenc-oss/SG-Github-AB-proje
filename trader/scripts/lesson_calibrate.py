#!/usr/bin/env python3
"""Esik kalibrasyonu (docs/ders-spec.md 7.3): backtest yeniden oynatma defterlerinde kural vekilini calistirir.

`python3 -I scripts/lesson_calibrate.py --backtest-ledger PATH --twin-backtest-ledger PATH --out config/lesson.json
[--seed N] [--config PATH] [--B 1000]`. LLM ve butce kullanilmaz; hicbir parametre degistirilmez; uretim defteri
kullanilmaz (yalniz verilen yeniden oynatma defterleri SALT OKUNUR acilir). Cikti: `--out` yapilandirmasina esikler ve
`calibration` nesnesi; `ok=false` ise esikler en siki hucreye ayarlanir ama otomatik uygulama kapali kalir.
Cikis: 0 ok=true, 3 ok=false (yazildi), 1 kullanim/yapilandirma hatasi.
"""
from __future__ import annotations

import argparse
import dataclasses
import json
import os
import sys
import tempfile
from pathlib import Path

_HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(_HERE.parent / "src"))

from trader_core import ledger as L  # noqa: E402
from trader_core import lesson as LS  # noqa: E402


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="lesson_calibrate.py")
    ap.add_argument("--backtest-ledger", required=True)
    ap.add_argument("--twin-backtest-ledger")
    ap.add_argument("--out", required=True)
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--config")
    ap.add_argument("--B", type=int, default=1000)
    try:
        args = ap.parse_args(argv)
    except SystemExit as e:
        return 1 if e.code else 0
    try:
        cfg = LS.load_config(args.config)
    except LS.LessonConfigError as e:
        print(f"yapilandirma hatasi: {LS.scrub(e)}", file=sys.stderr)
        return 1
    try:
        led = L.open_ledger(args.backtest_ledger, "learner", create=False, read_only=True, migrate=False)
    except L.LedgerError as e:
        print(f"yeniden oynatma defteri acilamadi: {e}", file=sys.stderr)
        return 1
    twin = None
    if args.twin_backtest_ledger:
        try:
            twin = L.open_ledger(args.twin_backtest_ledger, "twin", create=False, read_only=True, migrate=False)
        except L.LedgerError as e:
            print(f"ikiz yeniden oynatma defteri acilamadi: {e}", file=sys.stderr)
            return 1
    try:
        cal = LS.calibrate(led, twin, cfg, seed=args.seed, B=args.B)
    finally:
        led.close()
        if twin is not None:
            twin.close()
    cd = cal.to_dict()
    out_path = Path(args.out)
    base: dict = {}
    if out_path.exists():
        try:
            base = json.loads(out_path.read_text(encoding="utf-8"))
        except ValueError:
            base = {}
    for k in LS._CAL_NUM:
        base[k] = cd[k]
    base["calibration"] = cd
    fd, tmp = tempfile.mkstemp(dir=str(out_path.parent or "."), prefix=".lesson-cal-")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(base, f, indent=2, sort_keys=True)
            f.write("\n")
        os.replace(tmp, out_path)
    finally:
        if os.path.exists(tmp):
            os.unlink(tmp)
    # lesson_calibrations satiri (magaza zaten varsa)
    sp = Path(cfg.store_path)
    sp = sp if sp.is_absolute() else _HERE.parent / sp
    if sp.exists():
        try:
            with LS.LessonStore(sp) as st:
                st.add_calibration(cd)
        except Exception:  # noqa: BLE001
            pass
    print(json.dumps({"ok": cal.ok, "code": cal.code, "min_z": cal.min_z, "FPR_aile": cal.FPR_aile}))
    return 0 if cal.ok else 3


if __name__ == "__main__":
    sys.exit(main())
