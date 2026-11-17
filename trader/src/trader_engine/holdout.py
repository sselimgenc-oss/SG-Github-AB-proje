"""Kilitli donem (HOLDOUT) yapisal kilidi: backtest.py ve Engine.run_range ayni kontrolu kullanir. Gecersiz kilma anahtari yoktur."""
from __future__ import annotations

from datetime import datetime, timezone

from .errors import EngineError

HOLDOUT = (datetime(2026, 5, 1, tzinfo=timezone.utc), datetime(2026, 11, 1, tzinfo=timezone.utc))


class BacktestArgError(EngineError):
    def __init__(self, code: str, msg: str = "") -> None:
        super().__init__(msg or code)
        self.code = code


def check_holdout(start: datetime, end: datetime) -> None:
    if start < HOLDOUT[1] and end > HOLDOUT[0]:
        raise BacktestArgError("holdout_locked", f"HOLDOUT [{HOLDOUT[0]:%Y%m%d}, {HOLDOUT[1]:%Y%m%d}) ile kesisen donem")
