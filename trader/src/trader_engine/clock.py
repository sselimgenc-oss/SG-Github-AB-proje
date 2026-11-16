"""Saat (02 §6). Duvar saati kullanimi yalnizca bu modulde."""
from __future__ import annotations

import time
from datetime import datetime, timedelta, timezone
from typing import Protocol

from .errors import ClockError
from .types import require_utc


class Clock(Protocol):
    def now(self) -> datetime: ...

    def sleep(self, seconds: float) -> None: ...


class SystemClock:
    def now(self) -> datetime:
        return datetime.now(timezone.utc)

    def sleep(self, seconds: float) -> None:
        time.sleep(seconds)


class SimClock:
    def __init__(self, start: datetime) -> None:
        self._now = require_utc(start, "start")

    def now(self) -> datetime:
        return self._now

    def set_time(self, t: datetime) -> None:
        require_utc(t, "t")
        if t < self._now:
            raise ClockError(f"saat geri gitmez: {t} < {self._now}")
        self._now = t

    def advance(self, seconds: float) -> None:
        if seconds < 0:
            raise ClockError(f"negatif ilerleme: {seconds}")
        self._now = self._now + timedelta(seconds=seconds)

    def sleep(self, seconds: float) -> None:
        self.advance(seconds)
