# Kopyalandı: 1l3a-proje/motor/canli/durum.py + motor/canli/kalp_atisi.py (kullanıcının kendi kodu; lisans engeli yok)
# Kopya tarihi: 2026-11-16   Kaynak commit: 2dd2dce
# Çalışma zamanında kaynak depo import edilmez/mount edilmez. Değişiklikler: yalnız atomik yazma, zaman biçimi ve kalp atışı alındı; pandas yerine datetime; kimlikler İngilizceye çevrildi; DurumHatasi -> FileIoError (07 §4.4).
"""Atomik dosya yazma (geçici dosya + fsync + os.replace), UTC zaman biçimi ve kalp atışı.

Zamanı çağıran verir; bu modül saat okumaz.
"""
from __future__ import annotations

import json
import os
from collections.abc import Iterable
from datetime import datetime, timezone
from pathlib import Path

HEARTBEAT_FILE = "kalp_atisi.json"
HEARTBEAT_SCHEMA = "engine/heartbeat/1"
HEARTBEAT_INTERVAL_S = 60
_TS_FMT = "%Y-%m-%dT%H:%M:%SZ"


class FileIoError(Exception):
    """Dosya yok / okunamıyor / şemaya uymuyor."""


def fmt_ts(t: datetime) -> str:
    """tz-aware datetime -> 'YYYY-MM-DDTHH:MM:SSZ' (UTC). tz-naive -> ValueError."""
    if getattr(t, "tzinfo", None) is None:
        raise ValueError("zaman saat dilimli (UTC) olmalı")
    return t.astimezone(timezone.utc).strftime(_TS_FMT)


def parse_ts(s: str) -> datetime:
    return datetime.strptime(s, _TS_FMT).replace(tzinfo=timezone.utc)


def _tmp(path: Path) -> Path:
    return path.with_name(f".{path.name}.tmp-{os.getpid()}")


def atomic_write_text(path, text: str) -> Path:
    """Geçici dosya (aynı dizin) + fsync + os.replace: okuyucu ya eski ya yeni TAM dosyayı görür. Hata olursa geçici silinir."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = _tmp(path)
    try:
        with open(tmp, "w", encoding="utf-8", newline="\n") as f:
            f.write(text)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, path)
    except BaseException:
        tmp.unlink(missing_ok=True)
        raise
    return path


def atomic_write_json(path, data: dict) -> Path:
    return atomic_write_text(path, json.dumps(data, ensure_ascii=False, indent=1, allow_nan=False) + "\n")


def atomic_write_jsonl(path, rows: Iterable[dict]) -> Path:
    return atomic_write_text(path, "".join(json.dumps(r, ensure_ascii=False, allow_nan=False) + "\n" for r in rows))


def _check_ts(s, name: str) -> None:
    try:
        parse_ts(s)
    except (TypeError, ValueError) as e:
        raise FileIoError(f"{name}: geçersiz zaman '{s}' (YYYY-MM-DDTHH:MM:SSZ bekleniyordu)") from e


def heartbeat_write(directory, now: datetime, started_at: datetime, prev: str | None = None, stopped: bool = False) -> Path:
    """Atomik yazar. `started_at`: bu sürecin başlangıcı; `prev`: başlarken bulunan önceki kalp atışı (yoksa None)."""
    data = {"schema": HEARTBEAT_SCHEMA, "ts": fmt_ts(now), "started_at": fmt_ts(started_at), "prev": prev,
            "stopped": bool(stopped), "interval_s": HEARTBEAT_INTERVAL_S}
    return atomic_write_json(Path(directory) / HEARTBEAT_FILE, data)


def heartbeat_read(directory) -> dict | None:
    """Yoksa None (ilk çalışma). Bozuksa FileIoError (çağıran olay olarak yazar; sessiz atlanmaz)."""
    p = Path(directory) / HEARTBEAT_FILE
    if not p.exists():
        return None
    try:
        v = json.loads(p.read_text(encoding="utf-8"))
    except json.JSONDecodeError as e:
        raise FileIoError(f"{HEARTBEAT_FILE}: bozuk JSON ({e})") from e
    if not isinstance(v, dict) or "ts" not in v:
        raise FileIoError(f"{HEARTBEAT_FILE}: 'ts' alanı yok")
    _check_ts(v["ts"], HEARTBEAT_FILE)
    return v


def _utc(t: datetime) -> datetime:
    return t.replace(tzinfo=timezone.utc) if t.tzinfo is None else t.astimezone(timezone.utc)


def interruption(prev: str | None, started_at: datetime) -> dict:
    """-> {prev, started_at, seconds (None: ölçülemedi), reason}. Önceki yoksa veya saat geri gittiyse seconds None + reason."""
    b = _utc(started_at)
    if not prev:
        return {"prev": None, "started_at": fmt_ts(b), "seconds": None,
                "reason": "önceki kalp atışı kayıtlı değil: kesinti süresi ölçülemedi"}
    o = parse_ts(prev)
    sec = (b - o).total_seconds()
    if sec < 0:
        return {"prev": fmt_ts(o), "started_at": fmt_ts(b), "seconds": None,
                "reason": f"saat geri gitti (önceki kalp atışı {fmt_ts(o)} > başlangıç {fmt_ts(b)})"}
    return {"prev": fmt_ts(o), "started_at": fmt_ts(b), "seconds": sec, "reason": None}
