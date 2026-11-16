"""Arastirma kablolama sinifi: TraderV1'in KURAL MANTIGINA DOKUNMAZ.

freqtrade `lookahead-analysis` / `recursive-analysis` RunMode.UTIL_NO_EXCHANGE ile calisir;
TraderV1 bunu "canli" sayar (ledger_unconfigured kapisi -> giris yok, 0 islem). Bu alt sinif yalniz
calisma modunu backtest gibi ele alir; sinyal, risk, cikis kodu TraderV1 ile ayni.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "user_data" / "strategies"))

import TraderV1 as _tv1  # noqa: E402
from freqtrade.enums import RunMode  # noqa: E402

_tv1._BACKTEST_MODES = (RunMode.BACKTEST, RunMode.HYPEROPT, RunMode.UTIL_NO_EXCHANGE)


class TraderV1Analysis(_tv1.TraderV1):
    pass
