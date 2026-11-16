"""Kill dosyasi (05 §8.1). Dosya varligi = etkin; okunamazsa etkin sayilir (fail-closed)."""
from __future__ import annotations

import json
import os
from pathlib import Path

from .clock import Clock
from .fileio import atomic_write_json, fmt_ts


class Killswitch:
    def __init__(self, path: str, clock: Clock) -> None:
        self.path = str(path)
        self.clock = clock

    def active(self) -> bool:
        try:
            os.stat(self.path)
        except FileNotFoundError:
            return False
        except OSError:
            return True
        try:
            with open(self.path, "rb") as f:
                f.read(1)
        except OSError:
            return True
        return True

    def info(self) -> dict | None:
        try:
            raw = Path(self.path).read_text(encoding="utf-8")
        except FileNotFoundError:
            return None
        except (OSError, UnicodeDecodeError) as e:
            return {"raw": f"unreadable: {e}"}
        try:
            v = json.loads(raw)
        except ValueError:
            return {"raw": raw[:500]}
        return v if isinstance(v, dict) else {"raw": raw[:500]}

    def set(self, by: str, reason: str) -> None:
        atomic_write_json(self.path, {"at": fmt_ts(self.clock.now()), "by": by, "reason": reason})

    def clear(self) -> None:
        try:
            os.unlink(self.path)
        except FileNotFoundError:
            pass
