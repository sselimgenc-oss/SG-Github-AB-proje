#!/usr/bin/env python3
"""Esik kalibrasyonu (docs/ders-spec.md 7.3): backtest yeniden oynatma defterlerinde kural vekilini calistirir.

`python3 -I scripts/lesson_calibrate.py --backtest-ledger PATH --out config/lesson.json
[--seed N] [--config PATH] [--B 1000]`. LLM ve butce kullanilmaz; hicbir parametre degistirilmez; uretim defteri
kullanilmaz (yalniz verilen yeniden oynatma defterleri SALT OKUNUR acilir). Cikti: `--out` yapilandirmasina esikler ve
`calibration` nesnesi (BILGI; DD-12 WP-08: otomatik uygulamanin on sarti degildir, esikleri yapilandirmaya yazmaz).
M1 geri alma esigi (`monitor_margin_r`=0.3 R, `monitor_z`=1.0: diff <= -0.3R ve z <= -1) bu betikle kalibre edilir
(`yanlis_geri_alma` <= %15, `geri_alma_tespit` >= %70 olcutleri; spec 7.3.4/7.3.6): sonuc dosyasi yoksa ya da
`ok=false` ise otomatik uygulama baslamaz (gölge donem bitse bile; Revizyon 3).
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
    ap.add_argument("--apply-thresholds", action="store_true",
                    help="(eski) kalibre esikleri yapilandirmaya da yaz; varsayilan: yalniz bilgi (esiksiz kagit)")
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
    try:
        cal = LS.calibrate(led, None, cfg, seed=args.seed, B=args.B)       # ikiz yok (DD-12 WP-07/08)
    finally:
        led.close()
    cd = cal.to_dict()
    out_path = Path(args.out)
    base: dict = {}
    if out_path.exists():
        try:
            base = json.loads(out_path.read_text(encoding="utf-8"))
        except ValueError:
            base = {}
    if args.apply_thresholds:                       # DD-12 WP-08: kalibrasyon bilgi icindir, esikleri geri acmaz
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
    print(json.dumps({"ok": cal.ok, "code": cal.code, "min_z": cal.min_z, "FPR_aile": cal.FPR_aile,
                      "monitor_z": cal.monitor_z, "monitor_margin_r": cal.monitor_margin_r,
                      "yanlis_geri_alma": cal.yanlis_geri_alma, "geri_alma_tespit": cal.geri_alma_tespit,
                      "calibration_file": str(out_path)}))
    return 0 if cal.ok else 3


if __name__ == "__main__":
    sys.exit(main())
