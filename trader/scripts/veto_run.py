#!/usr/bin/env python3
"""Claude veto runner (docs/veto-spec.md Bolum 7). systemd timer ile her 30 dk bir kez calisir; dongu yok.

Cikis kodlari: 0 yazildi; 10 bu tur karar yok; 11 butce/saglayici kaynakli `unavailable` belgesi
yazildi; 12 yapilandirma/anahtar hatasi (cagri yok, dosya yok); 1 beklenmeyen hata.
Test icin `main(..., client=, market=, budget=, now_fn=, sleep_fn=, env=)` enjekte edilebilir.
API anahtari yalnizca istemciye verilir; log/istisna metninde `sk-ant-` dizgisi maskelenir.
"""
from __future__ import annotations

import argparse
import fcntl
import json
import logging
import os
import re
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

_HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(_HERE.parent / "src"))  # trader_engine de buradan (yalniz marketdata okuma)

from trader_core import proc_guard  # noqa: E402
from trader_core import veto as V  # noqa: E402
from trader_core.budget import Usage as _BudgetUsage  # noqa: E402

log = logging.getLogger("trader.veto.run")

EXIT_OK, EXIT_NO_DECISION, EXIT_UNAVAILABLE, EXIT_CONFIG, EXIT_CRASH = 0, 10, 11, 12, 1
IN_UB = 4800     # dinamik girdi ust siniri (token); ilk calistirmada gercek usage ile dogrulanir
SYS_UB = 1500    # statik sistem istemi ust siniri (onbellek yazimi sayilir)

_KEY_RE = re.compile(r"sk-ant-[A-Za-z0-9_\-]*")


def scrub(text) -> str:
    return _KEY_RE.sub("sk-ant-***", str(text))


class _ScrubFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        try:
            record.msg = scrub(record.getMessage())
            record.args = None
        except Exception:
            pass
        return True


class _Stop(Exception):
    """Saglayici engeli: unavailable belgesi (budget_provider_blocked), cikis 11."""


class _Fail(Exception):
    """Bu tur karar yok (cikis 10)."""


class _Denied(Exception):
    def __init__(self, denial):
        self.denial = denial


def _get(obj, name, default=0):
    v = obj.get(name) if isinstance(obj, dict) else getattr(obj, name, None)
    return default if v is None else v


def _extract_usage(resp, budget_usage_cls):
    u = _get(resp, "usage", None)
    if u is None:
        return budget_usage_cls()
    cc = _get(u, "cache_creation", None)
    w5 = w1 = 0
    if cc is not None:
        w5 = int(_get(cc, "ephemeral_5m_input_tokens", 0))
        w1 = int(_get(cc, "ephemeral_1h_input_tokens", 0))
    else:
        w1 = int(_get(u, "cache_creation_input_tokens", 0))  # yalniz toplam -> hepsi 1sa
    return budget_usage_cls(input_tokens=int(_get(u, "input_tokens", 0)),
                            output_tokens=int(_get(u, "output_tokens", 0)),
                            cache_write_5m_tokens=w5, cache_write_1h_tokens=w1,
                            cache_read_tokens=int(_get(u, "cache_read_input_tokens", 0)))


def _response_text(resp) -> str:
    parts = []
    for blk in _get(resp, "content", []) or []:
        if _get(blk, "type", None) == "text":
            parts.append(str(_get(blk, "text", "")))
    return "".join(parts)


def _error_info(e: Exception):
    status = getattr(e, "status_code", None)
    if isinstance(status, bool) or not isinstance(status, int):
        status = None
    body = getattr(e, "body", None)
    etype = ecode = None
    if isinstance(body, dict):
        err = body.get("error") if isinstance(body.get("error"), dict) else body
        etype = err.get("type") if isinstance(err.get("type"), str) else None
        ecode = err.get("code") if isinstance(err.get("code"), str) else None
    retry_after = None
    try:
        h = getattr(getattr(e, "response", None), "headers", None)
        if h is not None and h.get("retry-after") is not None:
            retry_after = float(h.get("retry-after"))
    except Exception:
        retry_after = None
    return status, etype, ecode, scrub(e), retry_after


class _Runner:
    def __init__(self, cfg, budget, client, sleep_fn):
        self.cfg, self.b, self.client, self.sleep = cfg, budget, client, sleep_fn

    def authorize(self):
        est = self.b.estimate_cost(
            self.cfg.model, input_tokens=IN_UB, max_output_tokens=self.cfg.max_tokens,
            **({"cache_write_1h_tokens": SYS_UB} if self.cfg.cache_ttl == "1h"
               else {"cache_write_5m_tokens": SYS_UB}))
        g = self.b.authorize("veto", est)
        if not hasattr(g, "grant_id"):  # Denial
            raise _Denied(g)
        return g

    def call(self, g, parts):
        """Bir API cagrisi (retry/stop/fail butce karariyla). Yanit nesnesi doner."""
        cfg = self.cfg
        attempt = 1
        while True:
            try:
                return self.client.messages.create(
                    model=cfg.model, max_tokens=cfg.max_tokens,
                    # API surum 2026-10-21 / SDK 2.x: temperature/top_p/top_k artik 400 (kaldirildi); kisa siniflandirma icin dusuk efor
                    # Haiku 5.5'te dusunme varsayilan acik ve max_tokens'i tuketip JSON'u kesiyordu: kisa siniflandirma icin
                    # kapali (dusuk eforda izinli)
                    thinking={"type": "disabled"}, output_config={"effort": "low"},
                    system=[{"type": "text", "text": parts.system,
                             "cache_control": {"type": "ephemeral", "ttl": cfg.cache_ttl}}],
                    messages=[{"role": "user", "content": parts.user}])
            except Exception as e:  # noqa: BLE001 - SDK hata siniflari enjekte edilebilir istemciye bagli
                status, etype, ecode, msg, retry_after = _error_info(e)
                log.warning("API hatasi status=%s type=%s: %s", status, etype, msg)
                act = self.b.report_error("veto", g, attempt, status, etype, ecode, msg, retry_after)
                if act.kind == "retry":
                    self.sleep(act.sleep_s)
                    attempt += 1
                    continue
                if act.kind == "stop":
                    raise _Stop() from None
                if status is not None:  # yanit alindi (4xx/5xx govdesi) -> serbest birak
                    self.b.release(g)
                # yanit alinmadi (zaman asimi/baglanti): release YOK; tahmin sayili kalir, TTL'de expired
                raise _Fail() from None

    def settle(self, g, resp):
        usage = _extract_usage(resp, self._usage_cls)
        try:
            st = self.b.record("veto", g, usage, self.cfg.model)
            if getattr(st, "overrun_micro", 0) > 0:
                log.warning("butce asimi overrun_micro=%s", st.overrun_micro)
            if not getattr(st, "ok", True):
                log.warning("record ok=False code=%s (tahmin sayildi)", getattr(st, "code", "?"))
            cost = getattr(st, "cost_micro", None)
        except Exception as e:  # noqa: BLE001
            log.error("record basarisiz: %s", scrub(e))
            cost = None
        return usage, cost


def _write_unavailable(cfg, path, key, pairs, ctx_hash, reason, now):
    doc = V.build_document(cfg, [], now, ctx_hash, pairs, status="unavailable", reason=reason)
    V.write_veto_file(path, V.sign_document(doc, key))


def _setup_logging():
    root = logging.getLogger()
    if not root.handlers:
        h = logging.StreamHandler(sys.stderr)
        h.setFormatter(logging.Formatter("%(levelname)s %(name)s %(message)s"))
        root.addHandler(h)
    root.setLevel(logging.INFO)
    for h in root.handlers:
        if not any(isinstance(f, _ScrubFilter) for f in h.filters):
            h.addFilter(_ScrubFilter())


def main(argv=None, *, client=None, market=None, budget=None, now_fn=None, sleep_fn=None,
         env=None, root=None) -> int:
    if not proc_guard.set_nondumpable():                  # DD-9 §4.3: ortam (API anahtari) ayni kimlikli sureclerce okunamasin
        log.warning("proc_guard: surec dokulemez yapilamadi; devam")
    try:
        return _main(argv, client, market, budget, now_fn, sleep_fn, env, root)
    except Exception as e:  # noqa: BLE001
        log.error("beklenmeyen hata: %s: %s", type(e).__name__, scrub(e))
        return EXIT_CRASH


def _main(argv, client, market, budget, now_fn, sleep_fn, env, root) -> int:
    _setup_logging()
    ap = argparse.ArgumentParser(description="Claude veto runner")
    ap.add_argument("--root", default=None)
    ap.add_argument("--config", default=None)
    args = ap.parse_args(argv)
    root = Path(args.root or root or _HERE.parent)
    env = os.environ if env is None else env
    now_fn = now_fn or (lambda: datetime.now(timezone.utc))
    sleep_fn = sleep_fn or time.sleep
    if budget is None:
        from trader_core import budget as budget  # noqa: PLC0415

    # 0. yapilandirma, anahtarlar
    try:
        cfg = V.load_config(args.config or (root / V.DEFAULT_PATH))
        pairs = V.load_pairs(cfg, root)
        api_env = budget.api_key_env("veto")
    except Exception as e:  # noqa: BLE001
        log.error("yapilandirma hatasi: %s", scrub(e))
        return EXIT_CONFIG
    api_key = env.get(api_env)
    hmac_key = env.get(cfg.hmac_key_env)
    if not api_key or not str(api_key).strip():
        log.error("ortam degiskeni yok: %s", api_env)
        return EXIT_CONFIG
    if not hmac_key or len(hmac_key) < V.MIN_KEY_CHARS:
        log.error("ortam degiskeni yok ya da kisa: %s", cfg.hmac_key_env)
        return EXIT_CONFIG
    veto_path = Path(cfg.veto_path)
    if not veto_path.is_absolute():
        veto_path = root / veto_path

    # kilit
    try:
        veto_path.parent.mkdir(parents=True, exist_ok=True)
        lock_f = open(veto_path.parent / ".lock", "a+")
        fcntl.flock(lock_f, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError as e:
        log.error("kilit alinamadi: %s", scrub(e))
        return EXIT_NO_DECISION
    try:
        return _locked(cfg, pairs, veto_path, hmac_key, api_key, root, client, market, budget,
                       now_fn, sleep_fn)
    finally:
        lock_f.close()


def _locked(cfg, pairs, veto_path, hmac_key, api_key, root, client, market, budget, now_fn,
            sleep_fn) -> int:
    # 1. piyasa verisi
    try:
        market = market or StoreMarketSource(root=root)
        snap = market.fetch(cfg, pairs, now_fn())
        ctx = V.build_context(snap)
        parts = V.build_prompt(cfg, ctx, pairs)
        ctx_hash = V.context_sha256(ctx)
    except Exception as e:  # noqa: BLE001
        log.error("piyasa verisi/baglam yok: %s: %s", type(e).__name__, scrub(e))
        return EXIT_NO_DECISION

    if client is None:
        try:
            import anthropic  # noqa: PLC0415
            client = anthropic.Anthropic(api_key=api_key, max_retries=0, timeout=cfg.request_timeout_s)
        except Exception as e:  # noqa: BLE001
            log.error("anthropic istemcisi kurulamadi: %s", scrub(e))
            return EXIT_CONFIG

    r = _Runner(cfg, budget, client, sleep_fn)
    r._usage_cls = _BudgetUsage

    def unavailable(reason: str) -> int:
        try:
            _write_unavailable(cfg, veto_path, hmac_key, pairs, ctx_hash, reason, now_fn())
        except V.VetoError as e:
            log.error("unavailable belgesi yazilamadi: %s", scrub(e))
            return EXIT_NO_DECISION
        log.warning("veto unavailable: %s", reason)
        return EXIT_UNAVAILABLE

    # 3-4. tahmin + yetkilendirme; 5-8. cagri, kayit, ayristirma
    decisions = usage = cost = None
    try:
        for attempt in range(cfg.parse_retries + 1):
            g = r.authorize()
            resp = r.call(g, parts)
            usage, cost = r.settle(g, resp)  # ayristirmadan ONCE
            stop_reason = _get(resp, "stop_reason", None)
            if stop_reason == "max_tokens":
                log.warning("yanit max_tokens ile kesildi")
                continue
            try:
                decisions = V.parse_model_output(_response_text(resp), pairs)
                break
            except V.VetoParseError as e:
                log.warning("cikti ayristirilamadi: %s", scrub(e))
    except _Denied as d:
        return unavailable("budget_" + str(d.denial.reason))
    except _Stop:
        return unavailable("budget_provider_blocked")
    except _Fail:
        return EXIT_NO_DECISION
    except (ValueError, TypeError) as e:  # BudgetConfigError (estimate_cost) vb.
        log.error("butce hatasi: %s", scrub(e))
        return EXIT_CONFIG
    if decisions is None:
        return EXIT_NO_DECISION

    # 9. belge
    now = now_fn()
    try:
        doc = V.build_document(cfg, decisions, now, ctx_hash, pairs)
        V.write_veto_file(veto_path, V.sign_document(doc, hmac_key))
    except V.VetoError as e:
        log.error("belge yazilamadi: %s", scrub(e))
        return EXIT_NO_DECISION
    cache_read = getattr(usage, "cache_read_tokens", 0)
    if cache_read == 0:
        log.warning("cache_miss: cache_read_tokens=0")
    print(json.dumps({"generated_at": doc["generated_at"],
                      "blocked": sum(1 for d in decisions if d.action == "block"),
                      "cost_micro": cost,
                      "usage": {"input_tokens": usage.input_tokens, "output_tokens": usage.output_tokens,
                                "cache_write_5m_tokens": usage.cache_write_5m_tokens,
                                "cache_write_1h_tokens": usage.cache_write_1h_tokens,
                                "cache_read_tokens": cache_read},
                      "cache_miss": cache_read == 0, "context_sha256": ctx_hash},
                     sort_keys=True), flush=True)
    return EXIT_OK


# --------------------------------------------------------------------------- piyasa kaynagi (salt okunur)
MAX_STALE_1H_S = 2 * 3600 + 600  # son kapanmis 1s mum bundan eskiyse (feed durmus) -> hata
FUNDING_LOOKBACK_S = 3 * 86400


class StoreMarketSource:
    """Motorun paylasimli market.sqlite deposundan (StoreSource, salt okunur) KAPANMIS mumlar. Ag yok.
    Depo yok/bayat/kisa ise istisna firlatir; veto_run bu turu cikis 10 ile bitirir (fail-closed)."""

    def __init__(self, db_path=None, root=None):
        self.db_path, self.root = db_path, root

    def _path(self, cfg):
        p = Path(self.db_path or cfg.market_db)
        return p if p.is_absolute() else Path(self.root or _HERE.parent) / p

    def fetch(self, cfg, pairs, now):
        import pandas as pd  # noqa: PLC0415
        from trader_core import regime as R  # noqa: PLC0415
        from trader_core import signals as S  # noqa: PLC0415
        from trader_engine.marketdata.sources import StoreSource  # noqa: PLC0415

        path = self._path(cfg)
        if not path.exists():
            raise RuntimeError(f"market.sqlite yok: {path}")
        src = StoreSource(path)
        try:
            return self._build(cfg, pairs, now, src, pd, R, S)
        finally:
            src.close()

    @staticmethod
    def _build(cfg, pairs, now, src, pd, R, S):
        def candles(pair, tf, n):
            df = src.bars(pair, tf, now, n)  # yalniz close_ts <= now (kapanmis)
            if df.empty or len(df) < n // 2:
                raise RuntimeError(f"{pair} {tf} mum eksik ({len(df)}/{n})")
            return df

        def ctx_for(key):
            d4 = candles(key, "4h", cfg.context["candles_4h"])
            d1 = candles(key, "1h", max(cfg.context["candles_1h"], 72))
            last_close = d1.index[-1] + pd.Timedelta(hours=1)
            if (now - last_close.to_pydatetime()).total_seconds() > MAX_STALE_1H_S:
                raise RuntimeError(f"{key} depo bayat: son kapanmis 1s mum {last_close}")
            res = R.classify_last(d4)
            reg_df = R.classify_series(d4)
            sig = S.compute_signals(d1, R.align_to_base(reg_df, d1.index)).iloc[-1]
            cand = {"long": False, "short": False}
            if bool(sig["signal"]) and sig["side"] in cand:
                cand[sig["side"]] = True
            closes = d1["close"]
            rets = {}
            for h in cfg.context["return_hours"]:
                rets[h] = float((closes.iloc[-1] / closes.iloc[-1 - h] - 1) * 100) \
                    if len(closes) > h else None
            fr = src.funding(key, now - timedelta(seconds=FUNDING_LOOKBACK_S), now)
            f = fr[-1].rate if fr else None
            return V.PairContext(key, res.regime.value, res.atr_ratio, rets,
                                 None if f is None else float(f), cand), last_close

        out, as_of = [], None
        for p in pairs:
            pc, t = ctx_for(p)
            out.append(pc)
            as_of = t
        btc = next((p for p in out if p.pair == "BTC/USDT"), None) or ctx_for("BTC/USDT")[0]
        return V.MarketSnapshot(V.format_ts(as_of.to_pydatetime()), btc, tuple(out))


if __name__ == "__main__":
    sys.exit(main())
