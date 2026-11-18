"""Borsa yasağı (ban) penceresinin kalıcı dosyası — DD-7 §1 (yalnız stdlib).

Aynı IP'yi paylaşan üç süreç (motor, feed, OI toplayıcı) yasak penceresini host başına bir dosyadan (`ban.<host>.json`) açılışta ve
çalışırken okur; yeni pencereyi aynı dosyaya yazar. Fail-closed: bozuk taze dosya = yasak var; yazılamayan pencere süreci
çıkarmaz (bellekteki pencere ile devam, çağıran sayaç + ERROR yazar). Pencere asla kısaltılmaz; süresi dolan dosya silinmez.
Zamanlama YALNIZ enjekte `now_ms` ile ölçülür.
"""
from __future__ import annotations

import fcntl
import json
import logging
import os
from collections.abc import Callable
from dataclasses import dataclass
from urllib.parse import urlparse

log = logging.getLogger("trader_core.ban_store")

PERSIST_MIN_S = 10          # kalan süresi bundan kısa pencere diske yazılmaz
MAX_HORIZON_S = 259_200     # 3 gün: kayıt en çok written_ms + bu kadar geçerli sayılır
CORRUPT_HOLD_S = 900        # bozuk dosya: mtime + 15 dk boyunca yasak varsayılır
REFRESH_MIN_S = 1.0         # BanGuard dosyayı en sık bu aralıkla yeniden okur
_FUTURE_SKEW_MS = 60_000
_PREFIX, _SUFFIX = "ban.", ".json"


@dataclass(frozen=True)
class BanRecord:
    host: str
    until_ms: int
    http: int | None
    source: str | None
    written_ms: int | None
    corrupt: bool = False


def ban_dir_for(market_db_path: str) -> str:
    return os.path.dirname(os.path.abspath(market_db_path))


def ban_path(ban_dir: str, base_url: str) -> str:
    host = (urlparse(base_url).hostname or "").lower()
    return f"{ban_dir}/{_PREFIX}{host}{_SUFFIX}"


def _host_of(path: str) -> str:
    name = os.path.basename(path)
    if name.startswith(_PREFIX) and name.endswith(_SUFFIX) and len(name) > len(_PREFIX) + len(_SUFFIX):
        return name[len(_PREFIX):-len(_SUFFIX)]
    return name


def _is_int(v: object) -> bool:
    return isinstance(v, int) and not isinstance(v, bool)


def _parse_valid(raw: bytes, host: str, now_ms: int) -> tuple[dict | None, int | None]:
    """(kayıt, eff) — geçerli değilse (None, None). eff = min(until, written + MAX_HORIZON)."""
    try:
        obj = json.loads(raw.decode("utf-8"))
    except Exception:  # noqa: BLE001  (bozuk JSON, kodlama, özyineleme ...)
        return None, None
    if not isinstance(obj, dict) or obj.get("v") != 1 or not _is_int(obj.get("v")):
        return None, None
    until, written, http = obj.get("until_ms"), obj.get("written_ms"), obj.get("http")
    if not (_is_int(until) and _is_int(written) and until > 0 and written > 0):
        return None, None
    if http is not None and not _is_int(http):
        return None, None
    if obj.get("host") != host:
        return None, None
    if written > now_ms + _FUTURE_SKEW_MS:
        return None, None
    return obj, min(until, written + MAX_HORIZON_S * 1000)


def read_ban(path: str, now_ms: int) -> BanRecord | None:
    """Etkin kaydı döner (§1 kuralları); hiçbir koşulda istisna sızdırmaz, dosyayı değiştirmez."""
    try:
        host = _host_of(path)
        try:
            st = os.stat(path)
        except FileNotFoundError:
            return None
        except OSError as e:
            log.error("ban dosyası stat edilemedi (%s): %s", path, type(e).__name__)
            return None
        try:
            with open(path, "rb") as fh:
                raw = fh.read(1_000_000)
        except FileNotFoundError:
            return None
        except OSError as e:
            log.error("ban dosyası okunamadı (%s): %s", path, type(e).__name__)
            return None
        obj, eff = _parse_valid(raw, host, now_ms)
        if obj is not None and eff is not None:
            if eff > now_ms:
                src = obj.get("source")
                return BanRecord(host=host, until_ms=eff, http=obj.get("http"),
                                 source=src if isinstance(src, str) else None, written_ms=obj["written_ms"], corrupt=False)
            return None
        mtime_ms = int(st.st_mtime * 1000)
        until = min(mtime_ms, now_ms) + CORRUPT_HOLD_S * 1000
        log.warning("ban dosyası bozuk (%s); %d sn yasak varsayılıyor", path, CORRUPT_HOLD_S)
        if until > now_ms:
            return BanRecord(host=host, until_ms=until, http=None, source=None, written_ms=None, corrupt=True)
        return None
    except Exception as e:  # noqa: BLE001  (read_ban istisna sızdırmaz)
        log.error("ban dosyası okuma hatası (%s): %s", path, type(e).__name__)
        return None


def probe_ban_file(path: str, now_ms: int) -> BanRecord | None:
    """Saglik yoklamasi (DD-7 §6): gecerli dosya -> kayit (SURESI DOLMUS olsa da; until_ms = eff); gecersiz ya da okunamayan dosya ->
    `corrupt=True, until_ms=0` kaydi; dosya yok -> None. Istisna sizdirmaz, dosyayi degistirmez."""
    host = _host_of(path)
    try:
        with open(path, "rb") as fh:
            raw = fh.read(1_000_000)
    except FileNotFoundError:
        return None
    except Exception:  # noqa: BLE001
        return BanRecord(host=host, until_ms=0, http=None, source=None, written_ms=None, corrupt=True)
    try:
        obj, eff = _parse_valid(raw, host, now_ms)
    except Exception:  # noqa: BLE001
        obj, eff = None, None
    if obj is None or eff is None:
        return BanRecord(host=host, until_ms=0, http=None, source=None, written_ms=None, corrupt=True)
    src = obj.get("source")
    return BanRecord(host=host, until_ms=eff, http=obj.get("http"), source=src if isinstance(src, str) else None,
                     written_ms=obj["written_ms"], corrupt=False)


def write_ban(path: str, *, until_ms: int, http: int | None, source: str, now_ms: int) -> bool:
    """Pencereyi atomik yazar; kısa pencere yazılmaz (True); mevcut daha uzun/eşit geçerli kayıt korunur (True).
    Her OSError -> False. Dizin oluşturulmaz."""
    try:
        if until_ms - now_ms < PERSIST_MIN_S * 1000:
            return True
        host = _host_of(path)
        lock_fd = os.open(path + ".lock", os.O_CREAT | os.O_RDWR, 0o644)
    except OSError as e:
        log.error("ban kilidi açılamadı (%s): %s", path, type(e).__name__)
        return False
    except Exception as e:  # noqa: BLE001
        log.error("ban yazma hatası (%s): %s", path, type(e).__name__)
        return False
    tmp = f"{path}.tmp.{os.getpid()}"
    try:
        try:
            fcntl.flock(lock_fd, fcntl.LOCK_EX)
            try:
                with open(path, "rb") as fh:
                    raw = fh.read(1_000_000)
            except FileNotFoundError:
                raw = None
            except OSError:
                raw = None
            if raw is not None:
                obj, eff = _parse_valid(raw, host, now_ms)
                if obj is not None and eff is not None and eff >= until_ms:
                    return True
            payload = json.dumps({"v": 1, "host": host, "until_ms": int(until_ms), "http": http, "source": source,
                                  "written_ms": int(now_ms)}, sort_keys=False).encode("utf-8")
            fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o644)
            try:
                os.fchmod(fd, 0o644)
                os.write(fd, payload)
                os.fsync(fd)
            finally:
                os.close(fd)
            os.replace(tmp, path)
            try:                                   # DD-9 §9.1: dizin kaydi da kalici olsun; hata yutulur (dosya yerinde)
                dfd = os.open(os.path.dirname(os.path.abspath(path)), os.O_RDONLY)
                try:
                    os.fsync(dfd)
                finally:
                    os.close(dfd)
            except OSError as e:
                log.warning("ban dizini fsync edilemedi (%s): %s", path, type(e).__name__)
            return True
        finally:
            try:
                os.unlink(tmp)
            except OSError:
                pass
            os.close(lock_fd)
    except OSError as e:
        log.error("ban dosyası yazılamadı (%s): %s", path, type(e).__name__)
        return False
    except Exception as e:  # noqa: BLE001
        log.error("ban dosyası yazma hatası (%s): %s", path, type(e).__name__)
        return False


class BanGuard:
    def __init__(self, path: str, source: str, now_ms: Callable[[], int]):
        self.path = path
        self.source = source
        self.now_ms = now_ms
        self._last_read_ms: int | None = None
        self._cached: BanRecord | None = None

    def active(self) -> BanRecord | None:
        now = int(self.now_ms())
        last = self._last_read_ms
        if last is not None and 0 <= now - last < REFRESH_MIN_S * 1000:
            rec = self._cached
            return rec if rec is not None and rec.until_ms > now else None
        rec = read_ban(self.path, now)
        self._last_read_ms, self._cached = now, rec
        return rec

    def note(self, until_ms: int, http: int | None) -> bool:
        now = int(self.now_ms())
        ok = write_ban(self.path, until_ms=until_ms, http=http, source=self.source, now_ms=now)
        if ok:
            self._last_read_ms, self._cached = now, read_ban(self.path, now)
        return ok
