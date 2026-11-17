#!/usr/bin/env python3
"""Saglik runner (docs/saglik-spec.md Bolum 8). Her 5 dk systemd timer ile calisir; daemon degildir.

Salt okuma: motorun `status.json` dosyasi (learner + twin), salt okunur sqlite. Islem acmaz, defter yazmaz, bot baslatmaz.
Cikis kodlari: 0 saglikli+nabiz gitti; 10 CRIT/UNKNOWN (nabiz yok); 11 saglikli ama nabiz gonderilemedi;
12 uyari iletilemedi; 1 beklenmeyen hata.
"""
from __future__ import annotations

import json
import logging
import os
import sqlite3
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

_HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(_HERE.parent / "src"))
sys.path.insert(0, str(_HERE))

from trader_core import health as H  # noqa: E402

log = logging.getLogger("trader.health.run")

EXIT_OK, EXIT_UNHEALTHY, EXIT_HB_FAILED, EXIT_ALERT_FAILED, EXIT_CRASH = 0, 10, 11, 12, 1
TOTAL_BUDGET_S = 60.0
STATUS_SCHEMA = "engine-status/1"
STATUS_MAX_BYTES = 2_000_000
PING_MAX_AGE_S = 120  # docs/motor/05 8.2: ping_ok = (simdi - loop_at) <= 120 sn
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
def status_path(var_dir: str, bot: str) -> str:
    return os.path.join(var_dir, bot, "status.json")


def ledger_path(var_dir: str, bot: str) -> str:
    return os.path.join(var_dir, bot, "ledger.sqlite")


def _ids(v):
    if not isinstance(v, list) or not all(isinstance(i, int) and not isinstance(i, bool) for i in v):
        return None
    return tuple(v)


def probe_status(path: str, bot: str, now: datetime) -> tuple[H.ApiProbe, int | None]:
    """Motor status.json -> (ApiProbe, timeframe_s). Fail-closed:
    dosya yok -> ping_ok=False (motor yazmiyor); okunamaz/bozuk/sema ya da bot uyusmaz -> hepsi None (UNKNOWN);
    loop_at 120 sn'den eskiyse ping_ok=False; gelecekteki (saat uyumsuz) loop_at -> ping_ok=None."""
    try:
        with open(path, "rb") as f:
            raw = f.read(STATUS_MAX_BYTES + 1)
    except FileNotFoundError:
        return H.ApiProbe(ping_ok=False), None
    except OSError:
        return H.ApiProbe(), None
    try:
        if len(raw) > STATUS_MAX_BYTES:
            raise ValueError("buyuk")
        d = json.loads(raw.decode("utf-8"))
    except (ValueError, UnicodeDecodeError):
        return H.ApiProbe(), None
    if not isinstance(d, dict) or d.get("schema") != STATUS_SCHEMA or d.get("bot") != bot:
        return H.ApiProbe(), None
    loop_at = _parse_dt(d.get("loop_at"))
    ping = None
    if loop_at is not None:
        age = (now - loop_at).total_seconds()
        if age >= -H.DEFAULT_CFG.clock_skew_tolerance_s:
            ping = age <= PING_MAX_AGE_S
    gate = d.get("gate")
    gc = gate.get("code") if isinstance(gate, dict) else None
    gate_code = gc if isinstance(gc, str) and gc else "status_malformed"
    kill = d.get("kill") if isinstance(d.get("kill"), bool) else None
    cnt = d.get("counters")
    le = cnt.get("ledger_errors") if isinstance(cnt, dict) else None
    le = le if isinstance(le, int) and not isinstance(le, bool) and le >= 0 else None
    pos = d.get("open_positions")
    unprot = None
    if isinstance(pos, list) and all(isinstance(p, dict) for p in pos):
        try:
            unprot = tuple(int(p["trade_id"]) for p in pos
                           if not (isinstance(p.get("stop"), (int, float)) and not isinstance(p.get("stop"), bool)
                                   and p["stop"] > 0))
        except (KeyError, TypeError, ValueError):
            unprot = None
    dry = d.get("dry_run") if isinstance(d.get("dry_run"), bool) else None
    probe = H.ApiProbe(ping, loop_at, _parse_dt(d.get("last_candle_open")), _ids(d.get("open_trade_ids")), dry,
                       gate_code, kill, le, unprot)
    return probe, timeframe_to_s(d.get("trigger_tf"))


def engine_container(path: str, bot: str, now: datetime, state: dict, key: str) -> H.ContainerProbe:
    """Motor surec dogrulugu (docker yok): state = status taze mi; started_at = status.started_at;
    restart_count = kalici sayac (started_at degisince +1; durum dosyasinda saklanir); oom_killed bilinmez (None)."""
    try:
        with open(path, "rb") as f:
            d = json.loads(f.read(STATUS_MAX_BYTES).decode("utf-8"))
        if not isinstance(d, dict) or d.get("schema") != STATUS_SCHEMA or d.get("bot") != bot:
            return H.ContainerProbe()
        started = _parse_dt(d.get("started_at"))
        loop_at = _parse_dt(d.get("loop_at"))
    except (OSError, ValueError, UnicodeDecodeError):
        return H.ContainerProbe()
    if started is None or loop_at is None:
        return H.ContainerProbe()
    base = int(state.get("restart_counts", {}).get(key, 0) or 0)
    prev = state.get("engine_started_at", {}).get(key)
    count = base + (1 if prev and prev != H._iso(started) else 0)
    fresh = (now - loop_at).total_seconds() <= H.DEFAULT_CFG.loop_crit_s
    return H.ContainerProbe("running" if fresh else "not_running", count, started, None)


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


def market_pairs(env: dict) -> tuple[str, ...]:
    """MARKET_PAIRS (virgullu) ya da ENGINE_CONFIG_DIR/engine.base.json `pairs`; ikisi de yoksa bos
    (probe_market feed-status.json listesine duser)."""
    raw = env.get("MARKET_PAIRS")
    if raw:
        return tuple(p for p in (x.strip() for x in raw.split(",")) if p)
    cd = env.get("ENGINE_CONFIG_DIR")
    if cd:
        try:
            with open(os.path.join(cd, "engine.base.json"), encoding="utf-8") as f:
                pairs = json.load(f).get("pairs")
            if isinstance(pairs, list) and all(isinstance(p, str) for p in pairs):
                return tuple(pairs)
        except (OSError, ValueError, AttributeError):
            pass
    return ()


def collect_market(env: dict, var_dir: str):
    """Opt-in: MARKET_DB yoksa None (piyasa denetimleri kapali). Salt okunur."""
    db = env.get("MARKET_DB")
    if not db:
        return None
    from trader_core.market_probe import probe_market
    fs = env.get("MARKET_FEED_STATUS") or os.path.join(var_dir, "feed-status.json")
    try:
        return probe_market(db_path=db, feed_status_path=fs, pairs=market_pairs(env),
                            engine_status_paths={b: status_path(var_dir, b) for b in BOTS})
    except Exception:  # noqa: BLE001
        return H.MarketProbe(feed_status_state="unreadable", db_state="unreadable")


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


# --------------------------------------------------------------------------- ortam
def load_env(environ=None) -> dict:
    env = dict(os.environ if environ is None else environ)
    need = ("HEARTBEAT_URL", "ENGINE_VAR_DIR", "BACKUP_DIR")
    missing = [k for k in need if not env.get(k)]
    if missing:
        raise ValueError("eksik ortam degiskenleri: " + ", ".join(missing))
    return env


def make_notifier(name: str):
    if name == "log":
        return H.LogNotifier()
    if name == "telegram":
        from trader_core import telegram as T
        n = T.notifier_from_env(os.environ)
        if n is None:
            raise ValueError("telegram yapilandirilmamis")
        return n
    raise ValueError("bilinmeyen NOTIFIER")


def collect(env: dict, state: dict, now: datetime, *, deadline: float = 0.0) -> H.HealthSnapshot:
    var_dir = env["ENGINE_VAR_DIR"]
    api, ledger, containers = {}, {}, {}
    tf_s = None
    for bot in BOTS:
        sp = status_path(var_dir, bot)
        try:
            probe, t = probe_status(sp, bot, now)
        except Exception:  # noqa: BLE001
            probe, t = H.ApiProbe(), None
        api[bot] = probe
        tf_s = tf_s or t
        try:
            ledger[bot] = probe_ledger(ledger_path(var_dir, bot), bot, probe.open_trade_ids)
        except Exception:  # noqa: BLE001
            ledger[bot] = H.LedgerProbe()
        try:
            containers[f"trader-{bot}"] = engine_container(sp, bot, now, state, f"trader-{bot}")
        except Exception:  # noqa: BLE001
            containers[f"trader-{bot}"] = H.ContainerProbe()
    free = probe_disk([var_dir, env["BACKUP_DIR"]])
    mem, swap_t, swap_u = probe_mem()
    last_backup = None
    try:
        from health_backup import latest_ok_backup
        last_backup = latest_ok_backup(env["BACKUP_DIR"])
    except Exception:  # noqa: BLE001
        pass
    market = collect_market(env, var_dir)
    return H.HealthSnapshot(
        market=market, prev_rules_missing=dict(state.get("rules_missing", {})),
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
    starts = dict(state.get("engine_started_at", {}))
    for k, c in snap.containers.items():
        if c.started_at is not None:
            starts[k] = H._iso(c.started_at)
    new_state["engine_started_at"] = starts
    new_state["installed_at"] = state["installed_at"]
    if snap.market is not None:   # rules_missing artis tespiti icin son gorulen sayaclar
        rm = dict(state.get("rules_missing", {}))
        rm.update({b: v for b, v in snap.market.rules_missing.items() if v is not None})
        new_state["rules_missing"] = rm

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
