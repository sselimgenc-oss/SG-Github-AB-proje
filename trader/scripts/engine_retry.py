#!/usr/bin/env python3
"""Motor acilis-kapisi yeniden deneme (WP-C). 5 dk'lik systemd zamanlayicisi ile `trader-engine-retry@<bot>.service`.

Yalniz su durumda `trader-engine@<bot>` yeniden baslatilir: birim `failed` VE son cikis kodu 7 (acilis kapisi: kural 10/10
degil ya da veri bayat) VE besleme saglikli (feed-status.json taze, rules satir sayisi >= cift sayisi, her cift icin son 1m
bar taze). Cikis 6 (451) ve yapilandirma hatalari (diger kodlar) yeniden denenmez: tek sert alarm kalir.
Saatte en fazla MAX_ATTEMPTS deneme (kayan 1 saat); tukenince tek CRIT (dedup_key) gonderilir.
Cikis: 0 her zaman (karar gunluge yazilir); 1 yalniz beklenmeyen hata.
"""
from __future__ import annotations

import argparse
import json
import logging
import os
import re
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

_HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(_HERE.parent / "src"))
sys.path.insert(0, str(_HERE))

log = logging.getLogger("trader.engine.retry")

GATE_EXIT = 7
MAX_ATTEMPTS = 6
WINDOW_S = 3600
FRESH_S = 180


def systemctl(args):
    """-> (returncode, stdout). Testlerde enjekte edilir."""
    p = subprocess.run(["systemctl", *args], capture_output=True, text=True, timeout=30, check=False)
    return p.returncode, p.stdout


# DD-9 §2.3: yalniz bilinen motor birimleri yeniden baslatilabilir (baska ad -> hicbir systemctl cagrisi yok)
UNIT_RE = re.compile(r"^trader-engine(@learner|-testnet|-live)\.service$")


def unit_state(bot: str, ctl=systemctl, unit: str | None = None) -> dict:
    rc, out = ctl(["show", unit or f"trader-engine@{bot}.service", "-p", "ActiveState", "-p", "ExecMainStatus", "-p", "Result"])
    d = dict(ln.split("=", 1) for ln in (out or "").splitlines() if "=" in ln)
    try:
        st = int(d.get("ExecMainStatus", ""))
    except ValueError:
        st = None
    return {"active": d.get("ActiveState", ""), "exit": st, "result": d.get("Result", "")}


def feed_healthy(env: dict, now: datetime) -> tuple[bool, str]:
    from trader_core.market_probe import probe_market
    from health_run import market_pairs
    var_dir = env.get("ENGINE_VAR_DIR", "")
    db = env.get("MARKET_DB") or os.path.join(var_dir, "market.sqlite")
    fs = env.get("MARKET_FEED_STATUS") or os.path.join(var_dir, "feed-status.json")
    pairs = market_pairs(env)
    m = probe_market(db_path=db, feed_status_path=fs, pairs=pairs)
    if m.feed_status_state != "ok" or m.feed_status_at is None:
        return False, "feed-status.json okunamadi"
    age = (now - m.feed_status_at).total_seconds()
    if age > FRESH_S:
        return False, f"feed-status bayat ({age:.0f} sn)"
    if m.db_state != "ok":
        return False, f"market.sqlite {m.db_state}"
    plist = m.pairs
    if not plist:
        return False, "cift listesi yok"
    if m.rules_count is None or m.rules_count < len(plist):
        return False, f"rules {m.rules_count} < {len(plist)}"
    for p in plist:
        t = (m.newest_bar_at or {}).get(p)
        if t is None or (now - t).total_seconds() > FRESH_S:
            return False, f"{p} son 1m bar bayat/yok"
    return True, "ok"


def _load(path: Path) -> dict:
    try:
        d = json.loads(path.read_text(encoding="utf-8"))
        return d if isinstance(d, dict) else {}
    except (OSError, ValueError):
        return {}


def _save(path: Path, d: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(d), encoding="utf-8")
    os.replace(tmp, path)


def _crit(env: dict, bot: str, now: datetime, unit: str | None = None) -> bool:
    from trader_core import health as H
    from health_run import make_notifier
    name = bot if unit is None else unit            # kagit birimlerinin mevcut anahtari (bot adi) degismez
    a = H.Alert(level=H.Status.CRIT, code="engine_retry_exhausted",
                title=f"Motor yeniden deneme tukendi: {name}",
                body=f"{unit or f'trader-engine@{bot}.service'} acilis kapisinda {MAX_ATTEMPTS} yeniden denemeye ragmen kalkmadi; elle mudahale gerekli.",
                fingerprint=f"engine-retry-exhausted:{name}", created_at=now)
    try:
        return bool(make_notifier(env.get("NOTIFIER", "auto"), env).send(a))
    except Exception:  # noqa: BLE001
        log.exception("CRIT gonderilemedi")
        return False


def run(bot: str, env: dict, *, ctl=systemctl, now: datetime | None = None, state_dir: str | None = None,
        unit: str | None = None) -> str:
    """-> karar: noop | not_gate | feed_unhealthy | restarted | exhausted | exhausted_quiet.
    `unit` (DD-9): testnet/canli birimi; deneme sayaci ve CRIT dedup anahtari birim adina gore ayrilir."""
    if unit is not None and not UNIT_RE.match(unit):
        raise ValueError("bilinmeyen birim")
    if unit == f"trader-engine@{bot}.service":
        unit = None
    key = bot if unit is None else unit
    now = now or datetime.now(timezone.utc)
    sp = Path(state_dir or env.get("STATE_DIR", "/var/lib/trader-health")) / "engine-retry.json"
    state = _load(sp)
    b = state.get(key) if isinstance(state.get(key), dict) else {}
    st = unit_state(bot, ctl, unit)
    if st["active"] != "failed":
        if b.get("alerted"):
            b["alerted"] = False
            state[key] = b
            _save(sp, state)
        return "noop"
    if st["exit"] != GATE_EXIT:
        log.info("%s: failed ama cikis=%s (acilis kapisi degil); yeniden deneme yok", bot, st["exit"])
        return "not_gate"
    ok, why = feed_healthy(env, now)
    if not ok:
        log.info("%s: acilis kapisi hatasi ama besleme saglikli degil (%s); bekleniyor", bot, why)
        return "feed_unhealthy"
    ts = [t for t in b.get("attempts", []) if isinstance(t, (int, float)) and now.timestamp() - t < WINDOW_S]
    if len(ts) >= MAX_ATTEMPTS:
        decision = "exhausted_quiet"
        if not b.get("alerted"):
            if _crit(env, bot, now, unit):
                b["alerted"] = True
            decision = "exhausted"
        b["attempts"] = ts
        state[key] = b
        _save(sp, state)
        log.warning("%s: saatte %d deneme siniri doldu; yeniden baslatilmadi", bot, MAX_ATTEMPTS)
        return decision
    ts.append(now.timestamp())
    b["attempts"] = ts
    state[key] = b
    _save(sp, state)
    log.info("%s: acilis kapisi hatasi, besleme saglikli; yeniden baslatiliyor (deneme %d/%d)", bot, len(ts), MAX_ATTEMPTS)
    target = unit or f"trader-engine@{bot}.service"
    ctl(["reset-failed", target])
    ctl(["restart", target])
    return "restarted"


def main(argv=None, *, ctl=systemctl) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--bot", required=True)
    ap.add_argument("--unit", default=None, help="yeniden baslatilacak motor birimi (varsayilan trader-engine@<bot>.service)")
    a = ap.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    if a.unit is not None and not UNIT_RE.match(a.unit):
        log.error("bilinmeyen birim adi; hicbir sey yapilmadi")
        return 1
    try:
        run(a.bot, dict(os.environ), ctl=ctl, unit=a.unit)
    except Exception:  # noqa: BLE001
        log.exception("beklenmeyen hata")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
