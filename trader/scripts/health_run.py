#!/usr/bin/env python3
"""Saglik runner (docs/saglik-spec.md Bolum 8). Her 5 dk systemd timer ile calisir; daemon degildir.

Salt okuma: HTTP GET, salt okunur sqlite, `docker inspect`. Islem acmaz, defter yazmaz, bot baslatmaz.
Cikis kodlari: 0 saglikli+nabiz gitti; 10 CRIT/UNKNOWN (nabiz yok); 11 saglikli ama nabiz gonderilemedi;
12 uyari iletilemedi; 1 beklenmeyen hata.
"""
from __future__ import annotations

import base64
import json
import logging
import os
import sqlite3
import subprocess
import sys
import time
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

_HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(_HERE.parent / "src"))
sys.path.insert(0, str(_HERE))

from trader_core import health as H  # noqa: E402

log = logging.getLogger("trader.health.run")

EXIT_OK, EXIT_UNHEALTHY, EXIT_HB_FAILED, EXIT_ALERT_FAILED, EXIT_CRASH = 0, 10, 11, 12, 1
TOTAL_BUDGET_S = 60.0
HTTP_TIMEOUT_S = 5.0
DOCKER_TIMEOUT_S = 10.0
BOTS = ("learner", "twin")
_TF_UNITS = {"m": 60, "h": 3600, "d": 86400, "w": 7 * 86400}


def timeframe_to_s(tf) -> int | None:
    if not isinstance(tf, str) or len(tf) < 2 or tf[-1] not in _TF_UNITS or not tf[:-1].isdigit():
        return None
    n = int(tf[:-1])
    return n * _TF_UNITS[tf[-1]] if n > 0 else None


def _parse_dt(s):
    if not isinstance(s, str):
        return None
    try:
        dt = datetime.fromisoformat(s.strip().replace("Z", "+00:00"))
    except ValueError:
        return None
    return dt.astimezone(timezone.utc) if dt.tzinfo else None


# --------------------------------------------------------------------------- durum dosyasi
def load_state(path) -> tuple[dict, bool]:
    """(durum, sifirlandi_mi). Yok ya da bozuk -> bos durum; bozuksa sifirlandi=True (sessiz degil)."""
    try:
        with open(path, encoding="utf-8") as f:
            st = json.load(f)
        if isinstance(st, dict) and st.get("schema") == 1:
            return st, False
        return H.empty_state(), True
    except FileNotFoundError:
        return H.empty_state(), False
    except (OSError, ValueError):
        return H.empty_state(), True


def save_state(path, state) -> None:
    from health_backup import atomic_write_json
    atomic_write_json(path, state)


# --------------------------------------------------------------------------- olcumler
def _get_json(base: str, path: str, auth: str | None, timeout=HTTP_TIMEOUT_S):
    req = urllib.request.Request(base.rstrip("/") + path, method="GET")
    if auth:
        req.add_header("Authorization", auth)
    with urllib.request.urlopen(req, timeout=timeout) as r:  # noqa: S310 - yalnizca yerel adres
        if not 200 <= r.status < 300:
            raise OSError("http")
        return json.loads(r.read(2_000_000).decode("utf-8"))


def probe_api(base: str, auth: str | None, deadline: float, get=_get_json) -> tuple[H.ApiProbe, int | None]:
    """Her uc nokta ayri try/except; hata -> ilgili alan None. (ApiProbe, timeframe_s)"""
    def left():
        return time.monotonic() < deadline
    ping = last_proc = candle = ids = dry = None
    tf_s = None
    pair = None
    tf = None
    if left():
        try:
            ping = bool(get(base, "/api/v1/ping", None).get("status") == "pong")
        except Exception:  # noqa: BLE001
            ping = False
    if left():
        try:
            h = get(base, "/api/v1/health", auth)
            last_proc = _parse_dt(h.get("last_process")) if h.get("last_process") else None
            if last_proc is None and isinstance(h.get("last_process_ts"), (int, float)):
                last_proc = datetime.fromtimestamp(h["last_process_ts"], tz=timezone.utc)
        except Exception:  # noqa: BLE001
            pass
    if left():
        try:
            c = get(base, "/api/v1/show_config", auth)
            dry = c.get("dry_run") if isinstance(c.get("dry_run"), bool) else None
            tf = c.get("timeframe")
            tf_s = timeframe_to_s(tf)
            wl = c.get("pair_whitelist") or c.get("exchange", {}).get("pair_whitelist") or []
            pair = wl[0] if wl else None
        except Exception:  # noqa: BLE001
            pass
    if left():
        try:
            st = get(base, "/api/v1/status", auth)
            ids = tuple(int(t["trade_id"]) for t in st)
        except Exception:  # noqa: BLE001
            pass
    if left() and pair and tf:
        try:
            from urllib.parse import quote
            d = get(base, f"/api/v1/pair_candles?pair={quote(pair, safe='')}&timeframe={tf}&limit=2", auth)
            cols = d["columns"]
            row = d["data"][-1]
            v = row[cols.index("date")]
            candle = (datetime.fromtimestamp(v / 1000, tz=timezone.utc) if isinstance(v, (int, float))
                      else _parse_dt(v))
        except Exception:  # noqa: BLE001
            pass
    return H.ApiProbe(ping, last_proc, candle, ids, dry), tf_s


_TS_TABLES = (("health_probes", "probed_at"), ("decision_events", "recorded_at"),
              ("trade_entries", "recorded_at"), ("trade_exits", "recorded_at"))


def probe_ledger(db_path: str, bot: str, open_ids) -> H.LedgerProbe:
    """Salt okunur. Kapi, yazmadan turetilir (spec 3.2)."""
    last = spool = unl = orphan = schema_ok = active = None
    try:
        spool = os.path.getsize(db_path + ".spool.jsonl") and _count_lines(db_path + ".spool.jsonl")
    except FileNotFoundError:
        spool = 0
    except OSError:
        spool = None
    try:
        from trader_core import ledger as L
        led = L.open_ledger(db_path, bot, create=False, read_only=True)
    except Exception as e:  # noqa: BLE001
        name = type(e).__name__
        if name == "LedgerSchemaError":
            schema_ok = False
        return H.LedgerProbe(None, spool, None, None, schema_ok, None)
    try:
        schema_ok = True
        try:
            if open_ids is not None:
                unl = tuple(led.find_unledgered_trades(open_ids))
        except Exception:  # noqa: BLE001
            unl = None
        try:
            orphan = tuple(led.find_orphan_decisions(older_than_s=3600))
        except Exception:  # noqa: BLE001
            orphan = None
    finally:
        try:
            led.close()
        except Exception:  # noqa: BLE001
            pass
    try:
        c = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True, timeout=5)
        try:
            stamps = []
            for t, col in _TS_TABLES:
                v = c.execute(f"SELECT max({col}) FROM {t} WHERE bot=?", (bot,)).fetchone()[0]
                if v:
                    stamps.append(v)
            if stamps:
                last = _parse_dt(max(stamps))
            else:
                m = c.execute("SELECT value FROM meta WHERE key='created_at'").fetchone()
                last = _parse_dt(m[0]) if m else None
            active = c.execute("SELECT 1 FROM param_activations WHERE bot=? LIMIT 1", (bot,)).fetchone() is not None
        finally:
            c.close()
    except Exception:  # noqa: BLE001
        pass
    return H.LedgerProbe(last, spool, unl, orphan, schema_ok, active)


def _count_lines(path) -> int:
    n = 0
    with open(path, "rb") as f:
        for line in f:
            if line.strip():
                n += 1
    return n


def probe_disk(paths) -> int | None:
    best = None
    for p in paths:
        try:
            st = os.statvfs(p)
        except OSError:
            return None
        free = st.f_bavail * st.f_frsize
        best = free if best is None else min(best, free)
    return best


def probe_mem(meminfo_path="/proc/meminfo"):
    try:
        d = {}
        with open(meminfo_path) as f:
            for line in f:
                k, _, rest = line.partition(":")
                d[k] = int(rest.split()[0]) * 1024
        return d["MemAvailable"], d["SwapTotal"], d["SwapTotal"] - d["SwapFree"]
    except (OSError, KeyError, ValueError, IndexError):
        return None, None, None


def probe_container(name: str, run=subprocess.run) -> H.ContainerProbe:
    try:
        p = run(["docker", "inspect", "--format", "{{json .}}", name], capture_output=True, text=True,
                timeout=DOCKER_TIMEOUT_S, check=True)
        d = json.loads(p.stdout)
        st = d["State"]
        return H.ContainerProbe(st.get("Status"), int(d.get("RestartCount")), _parse_dt(st.get("StartedAt")),
                                bool(st.get("OOMKilled")))
    except Exception:  # noqa: BLE001
        return H.ContainerProbe()


# --------------------------------------------------------------------------- ortam
def load_env(environ=None) -> dict:
    env = dict(os.environ if environ is None else environ)
    need = ("HEARTBEAT_URL", "LEDGER_DIR", "BACKUP_DIR", "LEARNER_API", "TWIN_API")
    missing = [k for k in need if not env.get(k)]
    if missing:
        raise ValueError("eksik ortam degiskenleri: " + ", ".join(missing))
    return env


def make_notifier(name: str):
    if name == "log":
        return H.LogNotifier()
    raise ValueError("bilinmeyen NOTIFIER")


def collect(env: dict, state: dict, now: datetime, *, deadline: float, get=_get_json, run=subprocess.run) -> H.HealthSnapshot:
    user = env.get("FREQTRADE_API_USER", "")
    pw = env.get("FREQTRADE_API_PASS", "")
    auth = ("Basic " + base64.b64encode(f"{user}:{pw}".encode()).decode()) if user and pw else None
    apis = {"learner": env["LEARNER_API"], "twin": env["TWIN_API"]}
    api, ledger = {}, {}
    tf_s = None
    for bot in BOTS:
        try:
            probe, t = probe_api(apis[bot], auth, deadline, get)
        except Exception:  # noqa: BLE001
            probe, t = H.ApiProbe(), None
        api[bot] = probe
        tf_s = tf_s or t
        try:
            ledger[bot] = probe_ledger(os.path.join(env["LEDGER_DIR"], f"ledger_{bot}.sqlite"), bot,
                                       probe.open_trade_ids)
        except Exception:  # noqa: BLE001
            ledger[bot] = H.LedgerProbe()
    free = probe_disk([env["LEDGER_DIR"], env["BACKUP_DIR"]])
    mem, swap_t, swap_u = probe_mem()
    containers = {f"trader-{b}": probe_container(f"trader-{b}", run) for b in BOTS}
    last_backup = None
    try:
        from health_backup import latest_ok_backup
        last_backup = latest_ok_backup(env["BACKUP_DIR"])
    except Exception:  # noqa: BLE001
        pass
    return H.HealthSnapshot(
        now=now, timeframe_s=tf_s, api=api, ledger=ledger, disk_free_bytes=free, mem_available_bytes=mem,
        swap_total_bytes=swap_t, swap_used_bytes=swap_u, containers=containers,
        prev_restart_counts=dict(state.get("restart_counts", {})),
        consecutive_restart_runs=dict(state.get("consecutive_restart_runs", {})),
        installed_at=H._from_iso(state.get("installed_at")), last_backup_at=last_backup)


def run_once(env: dict, *, now: datetime | None = None, state_path=None, notifier=None, sender=None,
             snapshot_fn=None) -> int:
    now = now or datetime.now(timezone.utc)
    state_path = state_path or os.path.join(env.get("STATE_DIR", "/var/lib/trader-health"), "state.json")
    state, reset = load_state(state_path)
    if state.get("installed_at") is None:
        state["installed_at"] = H._iso(now)
    notifier = notifier or make_notifier(env.get("NOTIFIER", "log"))
    sender = sender or H.HttpsHeartbeat(env["HEARTBEAT_URL"], env.get("HEARTBEAT_FAIL_URL") or None)
    deadline = time.monotonic() + TOTAL_BUDGET_S
    snap = snapshot_fn(env, state, now) if snapshot_fn else collect(env, state, now, deadline=deadline)
    report = H.evaluate(snap)

    maint = None
    mf = env.get("HEALTH_MAINTENANCE_FILE")
    if mf:
        try:
            maint = H.parse_maintenance(Path(mf).read_text(encoding="utf-8"), now)
        except OSError:
            maint = None
    alerts, new_state = H.plan_alerts(report, state, now, maintenance_until=maint)
    if reset:
        alerts.append(H.Alert(H.Status.WARN, "state_reset", "Saglik durum dosyasi sifirlandi",
                              "state.json yok ya da bozuktu; sayaclar sifirdan basladi.", "state|state_reset", now))
    # restart sayaclari / ust uste restart turlari
    counts = dict(state.get("restart_counts", {}))
    runs = dict(state.get("consecutive_restart_runs", {}))
    for k, c in snap.containers.items():
        if c.restart_count is not None:
            prev = counts.get(k)
            runs[k] = runs.get(k, 0) + 1 if prev is not None and c.restart_count > prev else 0
            counts[k] = c.restart_count
    new_state["restart_counts"], new_state["consecutive_restart_runs"] = counts, runs
    new_state["installed_at"] = state["installed_at"]

    failed = []
    for a in alerts:
        try:
            ok = notifier.send(a)
        except Exception:  # noqa: BLE001
            ok = False
        if not ok:
            failed.append(a)
    if failed:
        new_state = H.revert_failed_alerts(new_state, state, failed)

    code = EXIT_OK
    hb_ok = None
    if H.should_send_ok(report):
        hb_ok = sender.ok(report)
        if not hb_ok:
            log.critical("nabiz gonderilemedi")
            code = EXIT_HB_FAILED
            try:
                notifier.send(H.Alert(H.Status.WARN, "heartbeat_send_failed", "Nabiz gonderilemedi",
                                      "Dis nabiz gonderimi basarisiz; dis servis sessizlikten uyarir.",
                                      "heartbeat|heartbeat_send_failed", now))
            except Exception:  # noqa: BLE001
                pass
    else:
        try:
            sender.fail(report)
        except Exception:  # noqa: BLE001
            pass
        code = EXIT_UNHEALTHY
    if failed and code == EXIT_OK:
        code = EXIT_ALERT_FAILED
    try:
        save_state(state_path, new_state)
    except Exception:  # noqa: BLE001
        log.critical("durum dosyasi yazilamadi")
    print(json.dumps({"at": H._iso(now), "overall": report.overall.value, "heartbeat": hb_ok,
                      "failing": [{"name": r.name, "status": r.status.value, "code": r.code}
                                  for r in report.failing()]}, ensure_ascii=False))
    return code


def main() -> int:
    logging.basicConfig(stream=sys.stderr, level=logging.INFO, format="%(levelname)s %(message)s")
    try:
        env = load_env()
        return run_once(env)
    except Exception as e:  # noqa: BLE001
        print(f"health_run: beklenmeyen hata: {type(e).__name__}", file=sys.stderr)
        return EXIT_CRASH


if __name__ == "__main__":
    sys.exit(main())
