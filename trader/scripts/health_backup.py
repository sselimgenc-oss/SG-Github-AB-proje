#!/usr/bin/env python3
"""Gunluk yedek (docs/saglik-spec.md Bolum 6). Yalnizca standart kutuphane.

Kaynak veritabani kilitlenmez: salt okunur URI + sqlite3 Connection.backup(pages=-1). `cp` kullanilmaz.
Cikis kodu: 0 hepsi basarili/atlandi; 20 en az bir dosya basarisiz; 1 beklenmeyen istisna.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import socket
import sqlite3
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

GIB = 1024 ** 3
MIN_FREE_BYTES = 1 * GIB
KEEP_MIN, KEEP_MAX, KEEP_DEFAULT = 3, 60, 14
MIN_OK_AFTER_ROTATION = 3
BOTS = ("learner", "twin")   # varsayilan; HEALTH_BOTS ile degistirilir


def bots_from_env(env) -> tuple:
    raw = (env.get("HEALTH_BOTS") or "").strip()
    bots = tuple(dict.fromkeys(b for b in (x.strip() for x in raw.split(",")) if b))
    return bots or BOTS
EXIT_OK, EXIT_FAILED, EXIT_CRASH = 0, 20, 1

_DAY_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
_LEFTOVER_RE = re.compile(r"^(\d{4}-\d{2}-\d{2})\.(failed-\d{4}(-\d{2})?|partial)$")


def parse_keep_days(value=None) -> int:
    if value is None or (isinstance(value, str) and value.strip() == ""):
        return KEEP_DEFAULT
    if isinstance(value, bool):
        raise ValueError("BACKUP_KEEP_DAYS tamsayi olmali")
    try:
        n = int(str(value).strip())
    except ValueError as e:
        raise ValueError("BACKUP_KEEP_DAYS tamsayi olmali") from e
    if not KEEP_MIN <= n <= KEEP_MAX:
        raise ValueError(f"BACKUP_KEEP_DAYS {KEEP_MIN}..{KEEP_MAX} araliginda olmali")
    return n


def atomic_write_json(path, obj) -> None:
    path = str(path)
    d = os.path.dirname(os.path.abspath(path))
    tmp = os.path.join(d, f".{os.path.basename(path)}.tmp-{os.getpid()}")
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False, sort_keys=True, indent=1)
        f.flush()
        os.fsync(f.fileno())
    os.replace(tmp, path)
    try:
        fd = os.open(d, os.O_RDONLY)
        try:
            os.fsync(fd)
        finally:
            os.close(fd)
    except OSError:
        pass


def _sha256(path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def _tables(conn) -> list[str]:
    return [r[0] for r in conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%' ORDER BY name")]


def _trigger_counts(conn) -> dict[str, int]:
    out: dict[str, int] = {}
    for tbl, n in conn.execute(
            "SELECT tbl_name, count(*) FROM sqlite_master WHERE type='trigger' GROUP BY tbl_name"):
        out[tbl] = n
    return out


def _max_ids(conn) -> dict[str, int]:
    out: dict[str, int] = {}
    for t in _tables(conn):
        try:
            v = conn.execute(f'SELECT max(id) FROM "{t}"').fetchone()[0]
        except sqlite3.Error:
            continue
        out[t] = 0 if v is None else int(v)
    return out


def _fail(name: str, error: str, bytes_: int = 0) -> dict:
    return {"ok": False, "bytes": bytes_, "sha256": None, "integrity": None, "user_version": None,
            "max_ids": {}, "positions": None, "error": error}


def backup_one(kind: str, bot: str, src, dest, *, sleep=time.sleep, lock_retry_s: float = 30.0) -> dict:
    """Tek veritabanini yedekler ve dogrular. `kind`: 'ledger' | 'state' (motor state.sqlite). Girdi dosyasi degismez."""
    src, dest = str(src), str(dest)
    partial = dest + ".partial"
    if not os.path.isfile(src):
        return _fail(dest, "source_missing")
    for p in (partial,):
        if os.path.exists(p):
            os.unlink(p)
    attempts = 2
    last_err = "backup_error"
    for attempt in range(attempts):
        s = d = None
        try:
            s = sqlite3.connect(f"file:{src}?mode=ro", uri=True, timeout=5)
            d = sqlite3.connect(partial)
            src_uv = s.execute("PRAGMA user_version").fetchone()[0]
            src_trg = _trigger_counts(s)
            s.backup(d, pages=-1)
            d.commit()
            d.execute("PRAGMA journal_mode=DELETE").fetchone()  # yan dosya (-wal/-shm) birakma
            d.close()
            d = None
            s.close()
            s = None
            last_err = None
            break
        except sqlite3.OperationalError as e:
            last_err = "locked" if "locked" in str(e).lower() else "backup_error"
            if last_err == "locked" and attempt == 0:
                sleep(lock_retry_s)
        except sqlite3.Error:
            last_err = "backup_error"
        finally:
            for c in (s, d):
                if c is not None:
                    try:
                        c.close()
                    except sqlite3.Error:
                        pass
        if os.path.exists(partial):
            os.unlink(partial)
        if last_err != "locked":
            break
    if last_err is not None:
        if os.path.exists(partial):
            os.unlink(partial)
        return _fail(dest, last_err)

    corrupt = dest + ".corrupt"

    def bad(code: str) -> dict:
        os.replace(partial, corrupt)
        return _fail(dest, code, os.path.getsize(corrupt))

    size = os.path.getsize(partial)
    if size <= 0:
        return bad("empty")
    v = None
    try:
        v = sqlite3.connect(f"file:{partial}?mode=ro", uri=True, timeout=5)
        rows = [r[0] for r in v.execute("PRAGMA integrity_check")]
        if rows != ["ok"]:
            v.close()
            return bad("integrity")
        uv = v.execute("PRAGMA user_version").fetchone()[0]
        entry = {"ok": True, "bytes": size, "integrity": "ok", "user_version": uv, "max_ids": {},
                 "positions": None, "error": None}
        if kind == "ledger":
            if uv != src_uv:
                v.close()
                return bad("user_version")
            row = v.execute("SELECT value FROM meta WHERE key='bot'").fetchone()
            if row is None or row[0] != bot:
                v.close()
                return bad("meta_bot")
            if _trigger_counts(v) != src_trg:
                v.close()
                return bad("triggers")
            entry["max_ids"] = _max_ids(v)
        else:
            if "positions" not in _tables(v):
                v.close()
                return bad("no_positions_table")
            entry["positions"] = int(v.execute("SELECT count(*) FROM positions").fetchone()[0])
        v.close()
        v = None
    except sqlite3.Error:
        if v is not None:
            try:
                v.close()
            except sqlite3.Error:
                pass
        return bad("verify_error")
    entry["sha256"] = _sha256(partial)
    os.replace(partial, dest)
    return entry


def _copy_spool(src_db, dest_dir, name) -> None:
    sp = str(src_db) + ".spool.jsonl"
    try:
        if os.path.getsize(sp) <= 0:
            return
    except OSError:
        return
    out = os.path.join(dest_dir, name + ".spool.jsonl")
    shutil.copyfile(sp, out)
    fd = os.open(out, os.O_RDONLY)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


def _copy_corrupt(src_db, dest_dir, name) -> int:
    """DD-8 (E4): `<defter>.spool.corrupt.jsonl` (okunamayan spool satirlari; sessizce kaybolmus kayit) bos degilse gun dizinine
    kopyalanir (fsync). Dosya yok / 0 bayt -> 0 (kopya yok). Kopyalanan bayt sayisini dondurur; hata yukselir (cagiran girdiyi
    ok=false yapar)."""
    sp = str(src_db) + ".spool.corrupt.jsonl"
    try:
        n = os.path.getsize(sp)
    except OSError:
        return 0
    if n <= 0:
        return 0
    out = os.path.join(dest_dir, name + ".spool.corrupt.jsonl")
    shutil.copyfile(sp, out)
    fd = os.open(out, os.O_RDONLY)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)
    return os.path.getsize(out)


def read_manifest(day_dir) -> dict | None:
    try:
        with open(os.path.join(str(day_dir), "MANIFEST.json"), encoding="utf-8") as f:
            m = json.load(f)
        return m if isinstance(m, dict) else None
    except (OSError, ValueError):
        return None


def latest_ok_backup(backup_dir) -> datetime | None:
    """En yeni ok=true manifestin created_at'i (runner backup_age icin)."""
    best = None
    try:
        names = os.listdir(str(backup_dir))
    except OSError:
        return None
    for n in names:
        if not _DAY_RE.match(n):
            continue
        m = read_manifest(os.path.join(str(backup_dir), n))
        if m and m.get("ok") is True:
            try:
                t = datetime.strptime(m["created_at"], "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
            except (KeyError, TypeError, ValueError):
                continue
            if best is None or t > best:
                best = t
    return best


def rotate_backups(backup_dir, keep_days: int, today: str) -> list[str]:
    """Donus (6.6). Silinen dizin adlarini dondurur. Guvenlik kurallari (a)(b)(c) uygulanir."""
    keep_days = parse_keep_days(keep_days)
    root = Path(backup_dir)
    m = read_manifest(root / today)
    if not (m and m.get("ok") is True):
        return []  # (a) bugunku yedek basarisizsa hicbir sey silinmez
    days, leftovers = [], []
    for e in root.iterdir():
        if e.is_symlink() or not e.is_dir():
            continue
        if _DAY_RE.match(e.name):
            days.append(e.name)
        else:
            mm = _LEFTOVER_RE.match(e.name)
            if mm:
                leftovers.append((e.name, mm.group(1)))
    days.sort()
    kept = days[-keep_days:]
    old = days[:-keep_days] if len(days) > keep_days else []
    oldest_kept = kept[0] if kept else today
    old_left = [n for n, d in leftovers if d < oldest_kept]
    ok_left = 0
    for n in kept:
        mf = read_manifest(root / n)
        if mf and mf.get("ok") is True:
            ok_left += 1
    if (old or old_left) and ok_left < MIN_OK_AFTER_ROTATION:
        return []  # (b)
    removed = []
    rr = os.path.realpath(root)
    for n in old + old_left:
        p = root / n
        if p.is_symlink() or os.path.dirname(os.path.realpath(p)) != rr:
            continue  # (c)
        shutil.rmtree(p)
        removed.append(n)
    return removed


def run_backup(backup_dir, var_dir, keep_days=KEEP_DEFAULT, *, now: datetime | None = None,
               free_bytes=None, sleep=time.sleep, bots=BOTS) -> tuple[int, dict]:
    now = now or datetime.now(timezone.utc)
    if now.tzinfo is None:
        raise ValueError("now tz-aware olmali")
    now = now.astimezone(timezone.utc)
    keep_days = parse_keep_days(keep_days)
    root = Path(backup_dir)
    os.makedirs(root, mode=0o700, exist_ok=True)
    day = now.strftime("%Y-%m-%d")
    day_dir = root / day
    if day_dir.exists():
        m = read_manifest(day_dir)
        if m and m.get("ok") is True:
            return EXIT_OK, m  # idempotent: atla
        target = root / f"{day}.failed-{now.strftime('%H%M')}"
        if target.exists():
            target = root / f"{day}.failed-{now.strftime('%H%M')}-{now.strftime('%S')}"
        os.rename(day_dir, target)
    os.makedirs(day_dir, mode=0o700)

    jobs = []
    for b in bots:
        jobs.append(("ledger", b, Path(var_dir) / b / "ledger.sqlite", f"ledger_{b}.sqlite"))
    for b in bots:
        jobs.append(("state", b, Path(var_dir) / b / "state.sqlite", f"state_{b}.sqlite"))

    if free_bytes is None:
        def free_bytes():
            st = os.statvfs(root)
            return st.f_bavail * st.f_frsize
    try:
        low = free_bytes() < MIN_FREE_BYTES
    except OSError:
        low = True
    files: dict[str, dict] = {}
    for kind, bot, src, name in jobs:
        if low:
            files[name] = _fail(name, "disk_low")
            continue
        try:
            files[name] = backup_one(kind, bot, src, day_dir / name, sleep=sleep)
            if files[name]["ok"] and kind == "ledger":
                _copy_spool(src, day_dir, name)
                cb = _copy_corrupt(src, day_dir, name)
                if cb > 0:
                    files[name]["spool_corrupt_bytes"] = cb
        except Exception:  # noqa: BLE001 - tek dosya digerlerini durdurmaz
            files[name] = _fail(name, "unexpected")
    ok = all(v["ok"] for v in files.values())
    manifest = {"schema": 1, "created_at": now.strftime("%Y-%m-%dT%H:%M:%SZ"), "host": socket.gethostname(),
                "ok": ok, "files": files}
    atomic_write_json(day_dir / "MANIFEST.json", manifest)
    if ok:
        rotate_backups(root, keep_days, day)
    return (EXIT_OK if ok else EXIT_FAILED), manifest


def main(argv=None) -> int:
    try:
        env = os.environ
        backup_dir = env.get("BACKUP_DIR")
        var_dir = env.get("ENGINE_VAR_DIR")
        if not (backup_dir and var_dir):
            print("health_backup: BACKUP_DIR, ENGINE_VAR_DIR gerekli", file=sys.stderr)
            return EXIT_CRASH
        keep = parse_keep_days(env.get("BACKUP_KEEP_DAYS"))
        code, m = run_backup(backup_dir, var_dir, keep, bots=bots_from_env(env))
        bad = [k for k, v in m["files"].items() if not v["ok"]]
        print(json.dumps({"backup_ok": m["ok"], "failed": bad, "created_at": m["created_at"]}))
        if bad:
            print(f"health_backup: basarisiz: {', '.join(bad)}", file=sys.stderr)
        return code
    except Exception as e:  # noqa: BLE001
        print(f"health_backup: beklenmeyen hata: {type(e).__name__}", file=sys.stderr)
        return EXIT_CRASH


if __name__ == "__main__":
    sys.exit(main())
