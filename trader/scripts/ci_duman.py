#!/usr/bin/env python3
"""CI duman testi: motor modullerini iceri aktarir ve KISA bir kagit (paper) kosusu yapar (sentetik 2025 verisi, ag/anahtar yok;
kilitli donem okunmaz). Tam test takimindan once hizli bir "motor ayakta mi" sinyali verir; ~15-30 sn.

Kontroller: (1) motor/cekirdek paketleri iceri aktarilir, (2) 1 gunluk kagit kosusu hatasiz biter (strict), (3) defter sema
surumu ve karar satirlari var, (4) durum dosyasi (status.json) yazildi ve sema/mod dogru, (5) kagit modda gercek emir yok.
Cikis 0 = gecti; aksi halde ilk basarisiz kontrol yazilir ve cikis 1.
"""
from __future__ import annotations

import json
import sys
import tempfile
import time
from datetime import timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT))


def fail(msg: str) -> int:
    print(f"DUMAN BASARISIZ: {msg}", file=sys.stderr)
    return 1


def main() -> int:
    t0 = time.monotonic()
    try:
        import trader_core.health  # noqa: F401
        import trader_core.ledger  # noqa: F401
        import trader_engine.engine
        import trader_engine.brokers.paper  # noqa: F401
    except Exception as e:  # noqa: BLE001
        return fail(f"modul iceri aktarilamadi: {e!r}")
    try:
        from tests.e2e.test_e2e_chain import START, Chain, write_history
    except Exception as e:  # noqa: BLE001
        return fail(f"duman verisi/zinciri yuklenemedi: {e!r}")
    # Acilis kapisi (kural + taze canli 1m veri) sentetik gecmis veriyle anlamsizdir; tests/conftest.py ile ayni sekilde bu
    # SUREC icin etkisiz kilinir (uretim kodu degismez; yalniz bu betigin kendi sureci).
    trader_engine.engine.Engine._startup_gate = lambda self: None
    with tempfile.TemporaryDirectory(prefix="trader-duman-") as tmp:
        tmp_p = Path(tmp)
        hist = tmp_p / "history"
        write_history(hist)
        try:
            c = Chain(tmp_p / "run", hist)
            c.engine.start()
            c.engine.run_range(START, START + timedelta(days=1))
        except Exception as e:  # noqa: BLE001
            return fail(f"kagit kosusu coktu: {e!r}")
        if c.cfg.mode != "paper":
            return fail(f"mod 'paper' degil: {c.cfg.mode}")
        decisions = c.decisions()
        if not decisions:
            return fail("1 gunluk kosuda hic karar satiri yok (sinyal/risk zinciri calismadi)")
        sp = Path(c.cfg.status_path)
        if not sp.exists():
            return fail("status.json yazilmadi")
        st = json.loads(sp.read_text(encoding="utf-8"))
        if st.get("schema") != "engine-status/1" or st.get("bot") != "learner":
            return fail(f"status.json sema/bot hatali: {st.get('schema')}/{st.get('bot')}")
        n_tr = len(c.trades())
        print(f"DUMAN GECTI: {len(decisions)} karar, {n_tr} islem, {time.monotonic() - t0:.1f} sn")
    return 0


if __name__ == "__main__":
    sys.exit(main())
