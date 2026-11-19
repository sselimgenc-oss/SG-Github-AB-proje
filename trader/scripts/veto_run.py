#!/usr/bin/env python3
"""Claude veto runner: DEVRE DISI (DD-12 WP-06a, kullanici karari 18 Kasim 2026).

Kagit botta LLM veto kaldirildi: bu betik hicbir sey uretmez, API cagrisi yapmaz, dosya yazmaz; temiz (0) cikar.
Eski systemd birimi tetiklense bile zararsizdir. Veto kodu (`trader_core.veto`) yalniz testnet/canli yolu icindir.
"""
from __future__ import annotations

import logging
import sys

log = logging.getLogger("trader.veto.run")


def main(argv=None, **_ignored) -> int:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(levelname)s %(message)s")
    log.info("veto devre disi (DD-12 WP-06a): kagit botta LLM veto yok; yapilacak is yok")
    return 0


if __name__ == "__main__":
    sys.exit(main())
