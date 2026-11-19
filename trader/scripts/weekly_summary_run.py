#!/usr/bin/env python3
"""Haftalik ozet (DD-12 WP-09, spec eki 18 Kas 2026): haftanin islem notlarini sade Turkce ozetler (sahibin okumasi icin).

Tek LLM kullanimi budur. Butce payi `haftalik_ozet` (aylik tavan 10 $; pay bitince DURUR, motor/not/ders etkilenmez):
`budget.authorize` -> cagri -> `budget.record` (hata/sapmada `release`). API anahtari (budget.api_key_env("haftalik_ozet"))
yoksa NO-OP (cikis 0). Mevcut yardimcilar: `lesson.AnthropicBatchClient` (hata esleme), `lesson.budget_usage`; yeni SDK yok.
Cikti: `<defter dizini>/weekly_summaries/YYYY-Www.md` (hafta basina bir kez). Test: `main(argv, llm=, budget=, now_fn=, env=)`;
`llm(params) -> (metin, usage)`.
"""
from __future__ import annotations

import argparse
import json
import logging
import os
import sys
from collections import Counter
from datetime import datetime, timedelta, timezone
from pathlib import Path

_HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(_HERE.parent / "src"))

from trader_core import budget as _budget  # noqa: E402
from trader_core import ledger as L  # noqa: E402
from trader_core import lesson as LS  # noqa: E402

log = logging.getLogger("trader.weekly.run")
SERVICE = "haftalik_ozet"
MODEL = "claude-haiku-5-5"
MAX_OUT = 700
MAX_NOTES = 60
SYSTEM = ("Sen bir kagit-islem botunun haftalik ozetini yazan yardimcisin. Yalnizca verilen sayilara ve notlara dayan; "
          "uydurma. Sade Turkce, kisa paragraflar, teknik terimleri acikla. Para tavsiyesi verme; gercek paraya "
          "gecis hakkinda yorum yapma. Sonda en fazla uc maddelik 'dikkat edilecekler' ver.")


def _resolve(p: str) -> str:
    q = Path(p)
    return str(q if q.is_absolute() else _HERE.parent / q)


def week_key(day: datetime) -> str:
    y, w, _ = day.isocalendar()
    return f"{y}-W{w:02d}"


def build_input(ledger, since: str, until: str) -> tuple[dict, str]:
    notes = [n for n in ledger.list_trade_notes() if since <= n["note_date"] <= until]
    tags = Counter(t for n in notes for t in n["tags"])
    rt = {t.trade_id: t.r_multiple for t in ledger.list_closed_trades(limit=ledger.LIST_CLOSED_MAX)}
    rs = [rt[n["trade_id"]] for n in notes if rt.get(n["trade_id"]) is not None]
    stats = {"hafta_baslangic": since, "hafta_bitis": until, "not_sayisi": len(notes),
             "toplam_R": round(sum(rs), 3), "ortalama_R": round(sum(rs) / len(rs), 3) if rs else None,
             "etiket_sayilari": dict(sorted(tags.items()))}
    lines = [f"- {n['text']}" for n in notes[-MAX_NOTES:]]
    return stats, "Sayilar:\n" + json.dumps(stats, ensure_ascii=False, sort_keys=True) + "\n\nNotlar:\n" + "\n".join(lines)


def _default_llm(env, b):
    key = env.get(b.api_key_env(SERVICE))
    if not key:
        return None
    import anthropic  # noqa: PLC0415  (mevcut SDK; yeni bagimlilik yok)
    helper = LS.AnthropicBatchClient(client=anthropic.Anthropic(api_key=key, max_retries=0, timeout=60.0))

    def call(params):
        try:
            msg = helper._client.messages.create(**params)
        except Exception as e:  # noqa: BLE001
            raise helper._map(e) from None
        text = "".join(LS._g(c, "text", "") for c in (msg.content or []) if LS._g(c, "type") == "text")
        return text, msg.usage
    return call


def main(argv=None, *, llm=None, budget=None, now_fn=None, env=None) -> int:
    ap = argparse.ArgumentParser(prog="weekly_summary_run.py")
    ap.add_argument("--once", action="store_true", required=True)
    ap.add_argument("--day", help="YYYY-MM-DD: bu gunun haftasi (varsayilan: bugun UTC); son 7 gun ozetlenir")
    ap.add_argument("--ledger")
    ap.add_argument("--out-dir")
    ap.add_argument("--force", action="store_true", help="bu hafta icin ozet varsa yeniden yaz")
    try:
        args = ap.parse_args(argv)
    except SystemExit as e:
        return 1 if e.code else 0
    env = os.environ if env is None else env
    b = budget or _budget
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    now = (now_fn or (lambda: datetime.now(timezone.utc)))()
    day = datetime.strptime(args.day, "%Y-%m-%d").replace(tzinfo=timezone.utc) if args.day else now
    if llm is None:
        try:
            llm = _default_llm(env, b)
        except Exception as e:  # noqa: BLE001
            log.warning("LLM istemcisi kurulamadi: %s", LS.scrub(e))
            llm = None
    if llm is None:
        print(json.dumps({"status": "noop", "reason": "no_api_key"}))
        return 0
    lp = _resolve(args.ledger or env.get("LEDGER_PATH") or "var/learner/ledger.sqlite")
    out_dir = Path(_resolve(args.out_dir) if args.out_dir else str(Path(lp).with_name("weekly_summaries")))
    out = out_dir / f"{week_key(day)}.md"
    if out.exists() and not args.force:
        print(json.dumps({"status": "exists", "week": week_key(day)}))
        return 0
    try:
        led = L.open_ledger(lp, "learner", create=False, read_only=True, migrate=False)
    except Exception as e:  # noqa: BLE001
        print(f"defter acilamadi: {LS.scrub(e)}", file=sys.stderr)
        return 3
    try:
        stats, user = build_input(led, (day - timedelta(days=6)).date().isoformat(), day.date().isoformat())
    finally:
        close = getattr(led, "close", None)
        if close:
            close()
    if stats["not_sayisi"] == 0:
        print(json.dumps({"status": "noop", "reason": "no_notes"}))
        return 0
    params = {"model": MODEL, "max_tokens": MAX_OUT, "system": SYSTEM,
              "messages": [{"role": "user", "content": user}]}
    est = b.estimate_cost(MODEL, max(1, (len(SYSTEM) + len(user)) // 3), MAX_OUT)
    grant = b.authorize(SERVICE, est)
    if not hasattr(grant, "grant_id"):                     # Denial: pay/tavan bitti => dur (sessiz, cikis 0)
        print(json.dumps({"status": "budget_denied", "reason": getattr(grant, "reason", "denied")}))
        return 0
    try:
        text, usage = llm(params)
    except Exception as e:  # noqa: BLE001
        b.release(grant)
        print(json.dumps({"status": "llm_error", "error": LS.scrub(type(e).__name__)}))
        return 2
    try:
        b.record(SERVICE, grant, LS.budget_usage(usage), MODEL, False)
    except Exception as e:  # noqa: BLE001
        log.error("butce kaydi yazilamadi: %s", LS.scrub(e))
    text = (text or "").strip()
    if not text:
        print(json.dumps({"status": "empty"}))
        return 2
    out_dir.mkdir(parents=True, exist_ok=True)
    out.write_text(f"# Haftalik ozet {week_key(day)}\n\n{text}\n", encoding="utf-8")
    print(json.dumps({"status": "ok", "week": week_key(day), "file": str(out), "notes": stats["not_sayisi"]}))
    return 0


if __name__ == "__main__":
    sys.exit(main())
