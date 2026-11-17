"""Telegram: bildirim, komut ve gunluk rapor (docs/telegram-spec.md). Yalniz stdlib + `requests`.

Giden: `TelegramNotifier` (spool + dogrudan, `dedup_key` zorunlu). Gelen: `TelegramDaemon` (long polling, tek chat,
yalniz ozel sohbet, iki adimli kod onayi, ders onayi alt surecle). Motor bu modulu ice aktarmaz; Telegram ticareti
asla bloke etmez. Token hicbir cikti/gunluk/spool/istisna metninde bulunmaz (`mask`).
HTTP enjekte edilir: `http_post(url, json=..., timeout=...) -> (status_code, body_dict)`; ag hatasi `(0, {})`.
"""
from __future__ import annotations

import contextlib
import hashlib
import hmac
import json
import logging
import os
import re
import secrets
import sys
import time
from collections.abc import Callable, Mapping
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any


from . import lesson as LS


# trader_core -> trader_engine bagimliligi yasak (08 §4.7): motorun fileio bicimiyle ayni kucuk yardimcilar.
def atomic_write_json(path, data: dict) -> Path:
    """Gecici dosya + fsync + os.replace (trader_engine.fileio.atomic_write_json ile ayni bicim)."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(f".{path.name}.tmp-{os.getpid()}")
    try:
        with open(tmp, "w", encoding="utf-8", newline="\n") as f:
            f.write(json.dumps(data, ensure_ascii=False, indent=1, allow_nan=False) + "\n")
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, path)
    except BaseException:
        tmp.unlink(missing_ok=True)
        raise
    return path


def parse_ts_z(s: str) -> datetime:
    return datetime.strptime(s, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=UTC)

log = logging.getLogger("trader.telegram")
UTC = timezone.utc
TR = timezone(timedelta(hours=3))          # Europe/Istanbul: sabit UTC+3 (DST yok)

API = "https://api.telegram.org"
MAX_TEXT = 3500
RETRY_DELAYS = (2, 5, 15)
SEND_BUDGET_S = 30.0
STALE_S = 120
CODE_TTL_S = 120
DEDUP_WINDOW_S = 600
SPOOL_MAX_FILES = 500
SPOOL_MAX_BYTES = 5 * 1024 * 1024
INFO_MAX_AGE_S = 24 * 3600
RATE_PER_MIN = 15
REQ_ID_RE = re.compile(r"^lr-\d{4}-\d{2}-\d{2}-\d+$")
CODE_RE = re.compile(r"^\d{4}$")
SEVERITIES = ("INFO", "WARN", "CRIT")
_TOKEN_RE = re.compile(r"bot\d+:[A-Za-z0-9_\-]+")
_CTRL_RE = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")


def mask(text: Any, token: str | None = None) -> str:
    t = str(text)
    if token:
        t = t.replace(token, "<gizli>")
    t = _TOKEN_RE.sub("bot<gizli>", t)
    return LS.scrub(t)


def tail3(x: Any) -> str:
    s = str(x)
    return s[-3:]


# ---------------------------------------------------------------------------
# Metin
# ---------------------------------------------------------------------------
def neutralize(text: str) -> str:
    """Komut gibi gorunen '/' satirlarinin basina bosluk ekler; kontrol karakterlerini atar."""
    t = _CTRL_RE.sub(" ", LS.scrub(text))
    return "\n".join((" " + ln) if ln.startswith("/") else ln for ln in t.split("\n"))


def fit_text(body: str, pinned: str = "", limit: int = MAX_TEXT) -> str:
    """Govde kisalir, `pinned` (komut/kod satirlari) sona sabitlenir ve asla kesilmez."""
    body = neutralize(body)
    tail = ("\n" + pinned) if pinned else ""
    if len(body) + len(tail) <= limit:
        return body + tail
    lines = body.split("\n")
    note_room = 40
    out: list[str] = []
    used = 0
    for ln in lines:
        if used + len(ln) + 1 + len(tail) + note_room > limit:
            break
        out.append(ln)
        used += len(ln) + 1
    dropped = len(lines) - len(out)
    if not out:
        out = [lines[0][: max(0, limit - len(tail) - note_room)]]
        dropped = len(lines) - 1
    return "\n".join(out) + f"\n(kısaltıldı, {dropped} satır)" + tail


# ---------------------------------------------------------------------------
# Istemci
# ---------------------------------------------------------------------------
class TelegramError(Exception):
    def __init__(self, kind: str, status: int = 0, retry_after: float | None = None, desc: str = ""):
        super().__init__(f"{kind} {status} {desc}"[:200])
        self.kind = kind                      # transient | permanent | conflict
        self.status = status
        self.retry_after = retry_after


def default_http_post(url: str, json: Any = None, timeout: Any = None, token: str | None = None):
    import requests
    try:
        r = requests.post(url, json=json, timeout=timeout)
    except Exception as e:  # noqa: BLE001  istisna metni token tasir: maskelenir, zincir basilmaz
        log.warning("http hatasi: %s", mask(type(e).__name__, token))
        return 0, {}
    try:
        body = r.json()
    except ValueError:
        body = {}
    return r.status_code, body if isinstance(body, dict) else {}


class TelegramClient:
    def __init__(self, token: str, http_post: Callable | None = None, sleep: Callable[[float], None] = time.sleep):
        if not token:
            raise ValueError("token yok")
        self._token = token
        self._post = http_post or (lambda url, json=None, timeout=None: default_http_post(url, json, timeout, token))
        self.sleep = sleep

    def call(self, method: str, payload: dict, timeout=(5, 10)) -> Any:
        try:
            status, body = self._post(f"{API}/bot{self._token}/{method}", json=payload, timeout=timeout)
        except Exception as e:  # noqa: BLE001
            raise TelegramError("transient", 0, desc=mask(type(e).__name__, self._token)) from None
        if status == 200 and body.get("ok") is True:
            return body.get("result")
        params = body.get("parameters") or {}
        desc = mask(body.get("description", ""), self._token)
        if status == 429:
            raise TelegramError("transient", 429, min(60.0, float(params.get("retry_after", 5) or 5)), desc)
        if status == 409:
            raise TelegramError("conflict", 409, desc=desc)
        if status in (400, 401, 403, 404):
            raise TelegramError("permanent", status, desc=desc)
        raise TelegramError("transient", status, desc=desc)

    def send_message(self, chat_id, text: str, *, disable_notification: bool = False, reply_markup=None) -> dict:
        p = {"chat_id": chat_id, "text": text, "disable_web_page_preview": True,
             "disable_notification": bool(disable_notification)}
        if reply_markup is not None:
            p["reply_markup"] = reply_markup
        res = self.call("sendMessage", p)
        if not isinstance(res, dict) or "message_id" not in res:
            raise TelegramError("transient", 200, desc="message_id yok")
        return res

    def get_updates(self, offset: int | None, timeout: int = 30) -> list:
        p: dict = {"timeout": timeout, "allowed_updates": ["message", "callback_query"]}
        if offset is not None:
            p["offset"] = offset
        res = self.call("getUpdates", p, timeout=(5, timeout + 10))
        return res if isinstance(res, list) else []

    def answer_callback_query(self, callback_query_id: str, text: str = "") -> Any:
        return self.call("answerCallbackQuery", {"callback_query_id": callback_query_id, "text": text[:190]})

    def edit_message_text(self, chat_id, message_id: int, text: str, reply_markup=None) -> Any:
        p = {"chat_id": chat_id, "message_id": message_id, "text": text, "disable_web_page_preview": True}
        p["reply_markup"] = reply_markup if reply_markup is not None else {"inline_keyboard": []}
        return self.call("editMessageText", p)


# ---------------------------------------------------------------------------
# Ortam / yapilandirma
# ---------------------------------------------------------------------------
class TelegramConfig:
    def __init__(self, token: str, chat_id: int, var_dir: str, kill_file: str = "", status_path: str = "",
                 lesson_run: str = "", health_state: str = "", ledger_path: str = "", twin_ledger_path: str = "",
                 budget_config: str = "", lesson_store: str = ""):
        self.ledger_path, self.twin_ledger_path = ledger_path, twin_ledger_path
        self.budget_config, self.lesson_store = budget_config, lesson_store
        self.token, self.chat_id, self.var_dir = token, chat_id, var_dir
        self.kill_file, self.status_path = kill_file, status_path
        self.lesson_run, self.health_state = lesson_run, health_state

    @classmethod
    def from_env(cls, env: Mapping[str, str]) -> "TelegramConfig | None":
        tok = (env.get("TELEGRAM_BOT_TOKEN") or "").strip()
        cid = (env.get("TELEGRAM_CHAT_ID") or "").strip()
        if not tok or not cid:
            return None
        try:
            chat = int(cid)
        except ValueError:
            return None
        here = Path(__file__).resolve().parent.parent.parent
        return cls(tok, chat, env.get("TELEGRAM_VAR_DIR") or str(here / "var" / "telegram"),
                   env.get("KILL_FILE", ""), env.get("ENGINE_STATUS_PATH", ""),
                   env.get("LESSON_RUN_PATH") or str(here / "scripts" / "lesson_run.py"),
                   env.get("HEALTH_STATE_PATH", ""),
                   _abs_path(here, env.get("LEDGER_PATH") or "user_data/ledger_learner.sqlite"),
                   _abs_path(here, env.get("TWIN_LEDGER_PATH") or "user_data/ledger_twin.sqlite"),
                   _abs_path(here, env.get("BUDGET_CONFIG_PATH") or "config/budget.json"),
                   _abs_path(here, env.get("LESSON_STORE_PATH") or "user_data/lesson.sqlite"))


def _abs_path(base: Path, p: str) -> str:
    q = Path(p)
    return str(q if q.is_absolute() else base / q)


def _key_hash(key: str) -> str:
    return hashlib.sha256(key.encode("utf-8")).hexdigest()[:16]


# ---------------------------------------------------------------------------
# Spool
# ---------------------------------------------------------------------------
class Outbox:
    def __init__(self, base: str | Path, now_fn: Callable[[], datetime]):
        self.dir = Path(base) / "outbox"
        self.sent_dir = self.dir / "sent"
        self.now = now_fn
        self.dropped = 0

    def _mk(self) -> None:
        self.sent_dir.mkdir(parents=True, exist_ok=True)

    def sent_recently(self, key: str) -> bool:
        try:
            until = float((self.sent_dir / _key_hash(key)).read_text().strip())
        except (OSError, ValueError):
            return False
        return until > self.now().timestamp()

    def mark_sent(self, key: str, until_epoch: float | None = None) -> None:
        try:
            self._mk()
            until = until_epoch if until_epoch else self.now().timestamp() + DEDUP_WINDOW_S
            (self.sent_dir / _key_hash(key)).write_text(f"{until:.0f}\n")
        except OSError as e:
            log.warning("sent isareti yazilamadi: %s", type(e).__name__)

    def pending_for(self, key: str) -> list[Path]:
        try:
            return sorted(self.dir.glob(f"*-{_key_hash(key)}.json"))
        except OSError:
            return []

    def list(self) -> list[Path]:
        try:
            return sorted(p for p in self.dir.glob("*.json") if p.is_file())
        except OSError:
            return []

    def enqueue(self, item: dict) -> bool:
        """Ayni dedup_key icin ikinci dosya olmaz. Yazilamazsa False (yalniz gunluk)."""
        key = item["dedup_key"]
        if self.pending_for(key):
            return True
        try:
            self._mk()
            ns = int(self.now().timestamp() * 1e9)
            p = self.dir / f"{ns:020d}-{_key_hash(key)}.json"
            atomic_write_json(p, item)
            try:
                os.chmod(p, 0o660)
            except OSError:
                pass
        except Exception as e:  # noqa: BLE001
            log.error("spool yazilamadi: %s", type(e).__name__)
            return False
        self._enforce_limits()
        return True

    def _read(self, p: Path) -> dict | None:
        try:
            d = json.loads(p.read_text(encoding="utf-8"))
            return d if isinstance(d, dict) and "text" in d and "dedup_key" in d else None
        except (OSError, ValueError):
            return None

    def _enforce_limits(self) -> None:
        files = self.list()
        total = sum(p.stat().st_size for p in files if p.exists())
        if len(files) <= SPOOL_MAX_FILES and total <= SPOOL_MAX_BYTES:
            return
        for sev in ("INFO", "WARN"):
            for p in list(files):
                if len(files) <= SPOOL_MAX_FILES and total <= SPOOL_MAX_BYTES:
                    return
                d = self._read(p)
                if d and d.get("severity") == sev:
                    total -= p.stat().st_size
                    p.unlink(missing_ok=True)
                    files.remove(p)
                    self.dropped += 1

    def drain(self, client: TelegramClient, chat_id: int, sleep: Callable[[float], None] = time.sleep) -> int:
        """Eski->yeni. Basarili dosya silinir. Hata: dur (siradaki tur dener). Gonderilen sayisini dondurur."""
        now = self.now().timestamp()
        items: list[tuple[Path, dict]] = []
        for p in self.list():
            d = self._read(p)
            if d is None:
                continue
            exp = d.get("expires_at")
            if exp is not None and exp <= now:
                p.unlink(missing_ok=True)       # suresi dolmus onay talebi gonderilmez
                continue
            if d.get("severity") == "INFO" and now - float(d.get("created_at", now)) > INFO_MAX_AGE_S:
                p.unlink(missing_ok=True)
                continue
            if self.sent_recently(d["dedup_key"]):
                p.unlink(missing_ok=True)
                continue
            items.append((p, d))
        # hiz siniri: tur basina <= RATE_PER_MIN; asan INFO tek ozet
        budget = RATE_PER_MIN
        if len(items) > budget:
            info = [x for x in items if x[1].get("severity") == "INFO"]
            others = [x for x in items if x[1].get("severity") != "INFO"]
            keep_n = max(0, budget - len(others) - 1)
            merge = info[keep_n:]
            if len(merge) > 1:
                items = sorted(others + info[:keep_n], key=lambda x: x[0].name)
                try:
                    client.send_message(chat_id, f"{len(merge)} mesaj birlestirildi", disable_notification=True)
                    for p, d in merge:
                        p.unlink(missing_ok=True)
                        self.mark_sent(d["dedup_key"])
                except TelegramError:
                    pass
        sent = 0
        for p, d in items[:budget]:
            try:
                client.send_message(chat_id, d["text"], disable_notification=d.get("severity") == "INFO",
                                    reply_markup=d.get("reply_markup"))
            except TelegramError as e:
                if e.kind == "permanent":
                    log.error("CRIT spool gonderimi kalici hata %s", e.status)
                if e.retry_after:
                    sleep(e.retry_after)
                break
            self.mark_sent(d["dedup_key"], d.get("expires_at"))
            p.unlink(missing_ok=True)
            sent += 1
            sleep(1.0)
        return sent


# ---------------------------------------------------------------------------
# Giden: notifier
# ---------------------------------------------------------------------------
class TelegramNotifier:
    def __init__(self, client: TelegramClient, chat_id: int, outbox: Outbox, now_fn: Callable[[], datetime] | None = None,
                 sleep: Callable[[float], None] = time.sleep):
        self.client, self.chat_id, self.outbox = client, chat_id, outbox
        self.now = now_fn or (lambda: datetime.now(UTC))
        self.sleep = sleep

    def _send_retry(self, text: str, severity: str, reply_markup=None) -> bool:
        waited = 0.0
        delays = list(RETRY_DELAYS)
        while True:
            try:
                self.client.send_message(self.chat_id, text, disable_notification=severity == "INFO",
                                         reply_markup=reply_markup)
                return True
            except TelegramError as e:
                if e.kind in ("permanent", "conflict"):
                    log.error("CRIT telegram kalici gonderim hatasi %s", e.status)
                    return False
                wait = e.retry_after if e.retry_after else (delays.pop(0) if delays else None)
                if wait is None or waited + wait > SEND_BUDGET_S:
                    return False
                self.sleep(wait)
                waited += wait
            except Exception:  # noqa: BLE001
                return False

    def send_text(self, text: str, severity: str, dedup_key: str, *, expires_at: float | None = None,
                  reply_markup=None, pinned: str = "") -> bool:
        if not dedup_key or not isinstance(dedup_key, str):
            raise ValueError("dedup_key zorunlu")
        if severity not in SEVERITIES:
            raise ValueError("gecersiz severity")
        try:
            return self._deliver(text, severity, dedup_key, expires_at, reply_markup, pinned)
        except Exception as e:  # noqa: BLE001  istisna disariya sizmaz
            log.error("telegram gonderim istisnasi: %s", mask(type(e).__name__))
            return False

    def _deliver(self, text, severity, key, expires_at, reply_markup, pinned) -> bool:
        if self.outbox.sent_recently(key):
            return True                                   # zaten teslim edildi
        body = fit_text(text, pinned)
        if expires_at is not None and expires_at <= self.now().timestamp():
            return False
        if self._send_retry(body, severity, reply_markup):
            self.outbox.mark_sent(key, expires_at)
            for p in self.outbox.pending_for(key):
                p.unlink(missing_ok=True)
            return True
        self.outbox.enqueue({"text": body, "severity": severity, "dedup_key": key, "expires_at": expires_at,
                             "reply_markup": reply_markup, "created_at": self.now().timestamp()})
        return False                                      # spool'a yazmak teslim degildir

    # health.Notifier
    def send(self, alert) -> bool:
        lvl = getattr(alert.level, "value", str(alert.level))
        sev = "CRIT" if str(lvl).upper() in ("CRIT", "CRITICAL", "UNKNOWN", "FAIL") else (
            "INFO" if str(lvl).upper() in ("OK", "INFO") else "WARN")
        return self.send_text(f"{alert.title}\n{alert.body}", sev, alert.fingerprint)

    # lesson.LessonNotifier
    def notify(self, notice) -> bool:
        sev = {"info": "INFO", "warn": "WARN", "warning": "WARN", "crit": "CRIT", "critical": "CRIT"}.get(
            str(notice.level).lower(), "INFO")
        return self.send_text(f"{notice.title}\n{notice.body}", sev, notice.fingerprint)

    def request_approval(self, req) -> bool:
        exp = req.expires_at.timestamp()
        rid = req.request_id
        ev = ", ".join(f"{k}={v}" for k, v in list(dict(req.evidence).items())[:6])
        text = (f"{req.title}\n{req.param}: {req.from_value} -> {req.to_value} [{req.reason_code}]\n"
                f"{req.body}\nKanit: {ev}\nSon gecerlilik: {LS.fmt_ts(req.expires_at)}")
        pinned = f"/onayla {rid}\n/reddet {rid}"
        kb = {"inline_keyboard": [[{"text": "Onayla", "callback_data": f"ok:{rid}:{int(exp)}"},
                                   {"text": "Reddet", "callback_data": f"no:{rid}:{int(exp)}"}]]}
        return self.send_text(text, "WARN", rid, expires_at=exp, reply_markup=kb, pinned=pinned)


def notifier_from_env(env: Mapping[str, str], http_post=None, now_fn=None, sleep=time.sleep) -> TelegramNotifier | None:
    cfg = TelegramConfig.from_env(env)
    if cfg is None:
        return None
    now_fn = now_fn or (lambda: datetime.now(UTC))
    return TelegramNotifier(TelegramClient(cfg.token, http_post, sleep), cfg.chat_id,
                            Outbox(cfg.var_dir, now_fn), now_fn, sleep)


LS.NOTIFIER_FACTORIES["telegram"] = lambda cfg, env: notifier_from_env(env)


# ---------------------------------------------------------------------------
# Gelen: daemon
# ---------------------------------------------------------------------------
class _Clk:
    def __init__(self, fn):
        self._fn = fn

    def now(self):
        return self._fn()

    def sleep(self, s):
        time.sleep(s)


def _norm_cmd_text(s: str) -> str:
    return re.sub(r"\s+", " ", s.strip().lower().replace("ı", "i").replace("İ", "i"))


HELP = ("/durum  /rapor  /hepsini_kapat  /devam  /onayla <id>  /reddet <id>  /yardim\n"
        "/durdur: desteklenmiyor (tam kapatma icin /hepsini_kapat)")


class TelegramDaemon:
    def __init__(self, cfg: TelegramConfig, client: TelegramClient, *, now_fn: Callable[[], datetime] | None = None,
                 runner: Callable | None = None, killswitch=None, report_fn: Callable[[], str] | None = None,
                 sleep: Callable[[float], None] = time.sleep, random_code: Callable[[], str] | None = None):
        self.cfg, self.client = cfg, client
        self.now = now_fn or (lambda: datetime.now(UTC))
        if runner is None:
            raise ValueError("runner zorunlu (alt surec cagrisi scripts/telegram_run.py'de)")
        self.runner = runner
        self.report_fn = report_fn
        self.sleep = sleep
        self.base = Path(cfg.var_dir)
        self.base.mkdir(parents=True, exist_ok=True)
        self.outbox = Outbox(self.base, self.now)
        self.killswitch = killswitch          # motorun Killswitch'i disaridan verilir (scripts/telegram_run.py)
        self.start_ts = self.now().timestamp()
        self._seen: set[int] = set()
        self._rand = random_code or (lambda: "%04d" % secrets.randbelow(10000))
        self._unauth: list[float] = []
        self._unauth_warned_at = 0.0
        self.kill_watch: float | None = None
        self._load_seen()

    # -- dosyalar -----------------------------------------------------------
    @property
    def _offset_p(self):
        return self.base / "offset.json"

    @property
    def _pending_p(self):
        return self.base / "pending.json"

    @property
    def _audit_p(self):
        return self.base / "audit.jsonl"

    def _audit(self, event: str, **kw) -> None:
        row = {"ts": LS.fmt_ts(self.now()), "event": event, **kw}
        try:
            with open(self._audit_p, "a", encoding="utf-8") as f:
                f.write(json.dumps(row, ensure_ascii=False) + "\n")
        except OSError as e:
            log.warning("audit yazilamadi: %s", type(e).__name__)

    def _load_seen(self) -> None:
        try:
            for ln in self._audit_p.read_text(encoding="utf-8").splitlines()[-1000:]:
                try:
                    r = json.loads(ln)
                except ValueError:
                    continue
                if r.get("event") == "exec" and isinstance(r.get("update_id"), int):
                    self._seen.add(r["update_id"])
        except OSError:
            pass

    def _get_offset(self) -> int | None:
        try:
            return int(json.loads(self._offset_p.read_text())["offset"])
        except (OSError, ValueError, KeyError, TypeError):
            return None

    def _set_offset(self, uid: int) -> None:
        try:
            atomic_write_json(self._offset_p, {"offset": uid + 1})
        except Exception as e:  # noqa: BLE001
            log.warning("offset yazilamadi: %s", type(e).__name__)

    def _read_pending(self) -> dict | None:
        try:
            d = json.loads(self._pending_p.read_text())
            return d if isinstance(d, dict) else None
        except (OSError, ValueError):
            return None

    def _clear_pending(self) -> None:
        self._pending_p.unlink(missing_ok=True)

    def _read_status(self) -> dict | None:
        try:
            d = json.loads(Path(self.cfg.status_path).read_text(encoding="utf-8"))
            return d if isinstance(d, dict) else None
        except (OSError, ValueError, TypeError):
            return None

    # -- yetki --------------------------------------------------------------
    def _authorized(self, chat: Mapping, frm: Mapping) -> bool:
        return (chat.get("type") == "private" and chat.get("id") == self.cfg.chat_id
                and frm.get("id") == chat.get("id") and not frm.get("is_bot"))

    def _reply(self, text: str, severity: str = "WARN") -> None:
        try:
            self.client.send_message(self.cfg.chat_id, fit_text(text), disable_notification=severity == "INFO")
        except Exception as e:  # noqa: BLE001
            log.warning("yanit gonderilemedi: %s", mask(type(e).__name__, self.cfg.token))

    # -- ana islem ----------------------------------------------------------
    def process_updates(self, updates: list) -> None:
        for u in updates:
            uid = u.get("update_id")
            if not isinstance(uid, int):
                continue
            if uid not in self._seen:
                try:
                    self._handle(u)
                except Exception as e:  # noqa: BLE001
                    log.error("komut hatasi: %s", mask(type(e).__name__, self.cfg.token))
                self._seen.add(uid)
            self._set_offset(uid)

    def _handle(self, u: dict) -> None:
        uid = u["update_id"]
        if "callback_query" in u:
            return self._handle_callback(uid, u["callback_query"])
        m = u.get("message")
        if not isinstance(m, dict):
            return                                        # edited_message vb.: yok say
        chat, frm = m.get("chat") or {}, m.get("from") or {}
        if not self._authorized(chat, frm):
            return self._unauthorized(uid, chat.get("id"), m.get("text"))
        text = m.get("text") or ""
        age = self.now().timestamp() - float(m.get("date", 0))
        if age > STALE_S or float(m.get("date", 0)) < self.start_ts:
            self._audit("exec", update_id=uid, cmd=text[:20], sonuc="stale")
            return self._reply(f"islenmedi, yeniden gonder (yas: {int(age)} sn)")
        result = self._dispatch_text(text, tail3(frm.get("id")))
        self._audit("exec", update_id=uid, cmd=text[:20] if not CODE_RE.match(text.strip()) else "<kod>",
                    sonuc=result)

    def _unauthorized(self, uid: int, chat_id: Any, text: Any) -> None:
        self._seen.add(uid)
        self._audit("unauthorized", update_id=uid, chat_tail=tail3(chat_id), cmd=str(text or "")[:20])
        now = self.now().timestamp()
        self._unauth = [t for t in self._unauth if now - t < 60] + [now]
        if len(self._unauth) > 10 and now - self._unauth_warned_at > 600:
            self._unauth_warned_at = now
            self._reply("yetkisiz komut denemesi")

    def _dispatch_text(self, text: str, who: str) -> str:
        t = text.strip()
        if CODE_RE.match(t):
            return self._on_code(t, who)
        n = _norm_cmd_text(t)
        if n == "hepsini kapat":
            return self._cmd_kill_start()
        parts = t.split()
        if not parts or not parts[0].startswith("/"):
            self._reply("anlasilmadi. " + HELP)
            return "unknown"
        cmd = parts[0].lower().split("@")[0]
        arg = parts[1] if len(parts) > 1 else ""
        if cmd == "/yardim" or cmd == "/start":
            self._reply(HELP, "INFO")
            return "ok"
        if cmd == "/durum":
            return self._cmd_status()
        if cmd == "/rapor":
            if self.report_fn is None:
                self._reply("rapor yapilandirilmadi")
                return "noreport"
            self._reply(self.report_fn() + "\n(manuel)", "INFO")
            return "ok"
        if cmd == "/hepsini_kapat":
            return self._cmd_kill_start()
        if cmd == "/devam":
            return self._cmd_devam_start()
        if cmd == "/durdur":
            self._reply("desteklenmiyor, tam kapatma icin /hepsini_kapat")
            return "unsupported"
        if cmd in ("/onayla", "/reddet"):
            return self._lesson(arg, cmd == "/onayla")
        self._reply("bilinmeyen komut. " + HELP)
        return "unknown"

    # -- durum --------------------------------------------------------------
    def _cmd_status(self) -> str:
        st = self._read_status()
        if not st:
            self._reply("durum okunamadı")
            return "unreadable"
        lines = [f"kip={st.get('mode')} kill={st.get('kill')} kill_state={st.get('kill_state')} "
                 f"entries_open={st.get('entries_open')} equity={st.get('equity')} "
                 f"loop_at={st.get('loop_at')}", f"acik pozisyon: {len(st.get('open_positions') or [])}"]
        self._reply("\n".join(lines), "INFO")
        return "ok"

    # -- iki adimli kod -----------------------------------------------------
    def _new_pending(self, action: str) -> str:
        code = self._rand()
        salt = secrets.token_hex(8)
        now = self.now().timestamp()
        atomic_write_json(self._pending_p, {
            "token_hash": hashlib.sha256((salt + code).encode()).hexdigest(), "salt": salt, "action": action,
            "chat_id": self.cfg.chat_id, "created_at": now, "expires_at": now + CODE_TTL_S})
        return code

    def _cmd_kill_start(self) -> str:
        if self.killswitch is None:
            self._reply("kill dosyasi yapilandirilmadi")
            return "noconfig"
        if self.killswitch.active():
            info = self.killswitch.info() or {}
            self._reply(f"KILL zaten etkin ({info.get('by')}, {info.get('at')})")
            return "already"
        code = self._new_pending("kill")
        self._reply("Tum pozisyonlar piyasadan kapatilacak ve yeni giris durdurulacak. Onay icin "
                    f"{CODE_TTL_S} sn icinde yalniz su 4 haneli kodu yanitla: {code}")
        return "code_sent"

    def _devam_refusal(self) -> str | None:
        if self.killswitch is None:
            return "kill dosyasi yapilandirilmadi"
        if not self.killswitch.active():
            return "KILL etkin degil"
        st = self._read_status()
        if st is None:
            return "durum okunamadı, reddedildi"
        ks = st.get("kill_state")
        if ks == "exiting":
            return "kapanis suruyor, bekleyin"
        if st.get("mode") not in ("paper", "backtest"):       # canli ya da bilinmeyen
            info = self.killswitch.info() or {}
            if not (str(info.get("by", "")).startswith("telegram:") and info.get("reason") == "user_cmd"):
                return "Bu KILL Telegram'dan kurulmadi; yalniz sunucuda kaldirilir"
            if ks != "flat":
                return "pozisyonlar kapanmadi (durum flat degil), reddedildi"
        return None

    def _cmd_devam_start(self) -> str:
        why = self._devam_refusal()
        if why:
            self._reply(why)
            return "refused"
        code = self._new_pending("devam")
        self._reply(f"KILL kaldirilacak ve girisler yeniden acilabilir. {CODE_TTL_S} sn icinde yalniz su 4 haneli "
                    f"kodu yanitla: {code}")
        return "code_sent"

    def _on_code(self, code: str, who: str) -> str:
        p = self._read_pending()
        if not p or p.get("chat_id") != self.cfg.chat_id:
            self._reply("bekleyen onay yok")
            return "no_pending"
        self._clear_pending()                                 # tek kullanimlik / tek deneme
        if self.now().timestamp() > float(p.get("expires_at", 0)):
            self._reply("sure doldu, yeniden baslat")
            return "expired"
        want = hashlib.sha256((p["salt"] + code).encode()).hexdigest()
        if not hmac.compare_digest(want, p["token_hash"]):
            self._reply("yanlis kod, iptal edildi")
            return "wrong_code"
        if p["action"] == "kill":
            self.killswitch.set(by=f"telegram:{who}", reason="user_cmd")
            self.kill_watch = self.now().timestamp()
            self._reply("KILL kuruldu; motor pozisyonlari kapatiyor")
            return "kill_set"
        if p["action"] == "devam":
            why = self._devam_refusal()
            if why:
                self._reply(why)
                return "refused"
            self.killswitch.clear()
            self._reply("KILL kaldirildi")
            return "kill_cleared"
        return "bad_action"

    def tick_kill_watch(self) -> None:
        if self.kill_watch is not None and self.now().timestamp() - self.kill_watch >= 300:
            self.kill_watch = None
            st = self._read_status()
            if st is None or st.get("kill_state") != "flat":
                self._reply("CRIT kapatma tamamlanmadi (kill_state flat degil)", "CRIT")

    # -- ders onayi (alt surec) ---------------------------------------------
    def _run_resolve(self, rid: str, approve: bool) -> dict:
        if not REQ_ID_RE.match(rid or ""):
            return {"status": "invalid", "message": "gecersiz id"}
        argv = [sys.executable, "-I", self.cfg.lesson_run, "--resolve", rid,
                "--approve" if approve else "--reject"]
        env = {k: v for k, v in os.environ.items() if k != "TELEGRAM_BOT_TOKEN"}
        rc, out = self.runner(argv, 60, env)
        try:
            d = json.loads((out or "").strip().splitlines()[-1])
            if not isinstance(d, dict):
                raise ValueError
        except (ValueError, IndexError):
            d = {"status": "error", "message": "çıktı okunamadı"}
        d["rc"] = rc
        return d

    def _lesson(self, rid: str, approve: bool) -> str:
        d = self._run_resolve(rid, approve)
        self._reply(f"ders onayi {rid[:40]}: {d.get('status')} {str(d.get('message', ''))[:200]}")
        return str(d.get("status"))

    def _handle_callback(self, uid: int, cq: dict) -> None:
        msg = cq.get("message") or {}
        chat, frm = msg.get("chat") or {}, cq.get("from") or {}
        cid = cq.get("id", "")
        if not self._authorized(chat, frm):
            return self._unauthorized(uid, chat.get("id"), cq.get("data"))
        data = str(cq.get("data") or "")
        parts = data.split(":")
        mid = msg.get("message_id")

        def ans(t: str = "") -> None:
            try:
                self.client.answer_callback_query(cid, t)
            except Exception as e:  # noqa: BLE001
                log.warning("answer_callback_query: %s", type(e).__name__)

        def edit(t: str, kb=None) -> None:
            try:
                self.client.edit_message_text(chat["id"], mid, fit_text(t), kb)
            except Exception as e:  # noqa: BLE001
                log.warning("edit_message_text: %s", type(e).__name__)

        if len(parts) != 3 or parts[0] not in ("ok", "no", "ev", "vz") or not REQ_ID_RE.match(parts[1]):
            ans("gecersiz")
            return self._audit("exec", update_id=uid, cmd="cb", sonuc="bad_data")
        act, rid = parts[0], parts[1]
        try:
            exp = float(parts[2])
        except ValueError:
            ans("gecersiz")
            return self._audit("exec", update_id=uid, cmd="cb", sonuc="bad_exp")
        orig = str(msg.get("text") or "")
        if exp <= self.now().timestamp():
            ans("suresi doldu")
            edit(orig.split("\n\nEmin misin?")[0] + "\n(suresi doldu)")
            return self._audit("exec", update_id=uid, cmd="cb:" + act, sonuc="expired")
        base = orig.split("\n\nEmin misin?")[0]
        if act == "ok":
            ans()
            kb = {"inline_keyboard": [[{"text": "Evet, onayla", "callback_data": f"ev:{rid}:{int(exp)}"},
                                       {"text": "Vazgec", "callback_data": f"vz:{rid}:{int(exp)}"}]]}
            edit(base + "\n\nEmin misin? Onaylarsan degisiklik uygulanir.", kb)
            res = "confirm_asked"
        elif act == "vz":
            ans("vazgecildi")
            kb = {"inline_keyboard": [[{"text": "Onayla", "callback_data": f"ok:{rid}:{int(exp)}"},
                                       {"text": "Reddet", "callback_data": f"no:{rid}:{int(exp)}"}]]}
            edit(base, kb)
            res = "cancelled"
        else:
            ans()
            d = self._run_resolve(rid, act == "ev")
            edit(f"{base}\n\nSonuc: {d.get('status')} {str(d.get('message', ''))[:200]}")
            res = str(d.get("status"))
        self._audit("exec", update_id=uid, cmd="cb:" + act, sonuc=res)

    # -- dongu --------------------------------------------------------------
    def write_alive(self) -> None:
        try:
            atomic_write_json(self.base / "alive.json", {"ts": LS.fmt_ts(self.now())})
        except Exception:  # noqa: BLE001
            pass

    def poll_once(self, timeout: int = 30) -> bool:
        """Bir tur: getUpdates + yurutme. Hata durumunda False (cagiran bekler)."""
        try:
            ups = self.client.get_updates(self._get_offset(), timeout)
        except TelegramError as e:
            if e.kind == "conflict":
                log.error("CRIT 409 conflict: baska poller")
            return False
        self.process_updates(ups)
        return True

    def run_forever(self, stop: Callable[[], bool] = lambda: False) -> None:
        backoff = 1.0
        last_drain = 0.0
        while not stop():
            self.write_alive()
            ok = self.poll_once()
            self.tick_kill_watch()
            nowt = self.now().timestamp()
            if nowt - last_drain >= 30:
                last_drain = nowt
                try:
                    self.outbox.drain(self.client, self.cfg.chat_id, self.sleep)
                except Exception as e:  # noqa: BLE001
                    log.warning("outbox bosaltma: %s", type(e).__name__)
            if ok:
                backoff = 1.0
            else:
                self.sleep(backoff)
                backoff = min(60.0, backoff * 2)


# ---------------------------------------------------------------------------
# Gunluk rapor
# ---------------------------------------------------------------------------
def report_decision(now_utc: datetime, last_day: str | None) -> tuple[str, str]:
    """-> (karar, gun): karar normal | gecikmis | atla. Kesimi betik uygular (karar 7)."""
    n = now_utc.astimezone(TR)
    sched = n.replace(hour=21, minute=0, second=0, microsecond=0)
    if n < sched:
        sched -= timedelta(days=1)
    day = sched.date().isoformat()
    if last_day == day:
        return "atla", day
    delay = (n - sched).total_seconds()
    if delay <= 600:
        return "normal", day
    if delay <= 150 * 60:                    # 23:30'a kadar
        return "gecikmis", day
    return "atla", day


def build_report(cfg: TelegramConfig, now: datetime, day: str, sections: Mapping[str, Callable[[], str]] | None = None
                 ) -> str:
    out = [f"Gunluk rapor {day}"]
    try:
        st = json.loads(Path(cfg.status_path).read_text(encoding="utf-8"))
        loop = parse_ts_z(st["loop_at"])
        if (now - loop).total_seconds() > 120:
            out.insert(0, "CRIT motor kalp atisi yok")
        pos = st.get("open_positions") or []
        out.append(f"Motor: kip={st.get('mode')} kill={st.get('kill')}/{st.get('kill_state')} "
                   f"entries_open={st.get('entries_open')} equity={st.get('equity')} "
                   f"gun_basi={st.get('day_start_equity')} param_v={st.get('param_version_id')}")
        for p in pos[:10]:
            out.append(f"  {p.get('pair')} {p.get('side')} giris={p.get('entry_price')} stop={p.get('stop')}")
        if len(pos) > 10:
            out.append(f"  +{len(pos) - 10}")
        nz = {k: v for k, v in (st.get("counters") or {}).items() if v}
        if nz:
            out.append(f"Sayaclar: {nz}")
    except Exception as e:  # noqa: BLE001
        out.append(f"Motor: okunamadı: {type(e).__name__}")
    if cfg.health_state:
        try:
            hs = json.loads(Path(cfg.health_state).read_text(encoding="utf-8"))
            out.append(f"Sağlık: son genel={hs.get('last_overall')}")
        except Exception as e:  # noqa: BLE001
            out.append(f"Sağlık: okunamadı: {type(e).__name__}")
    for name, fn in (sections or {}).items():
        try:
            out.append(f"{name}: {fn()}")
        except Exception as e:  # noqa: BLE001
            out.append(f"{name}: okunamadı: {getattr(e, 'code', type(e).__name__)}")
    try:
        out.append(f"Spool bekleyen: {len(Outbox(cfg.var_dir, lambda: now).list())}")
    except Exception:  # noqa: BLE001
        pass
    return fit_text("\n".join(out), "", 3500)


class SectionError(Exception):
    """Rapor bölümü okunamadı; `code` satıra yazılır."""

    def __init__(self, code: str):
        super().__init__(code)
        self.code = code


def _istanbul_day_bounds_utc(day: str) -> tuple[str, str]:
    d0 = datetime.fromisoformat(day).replace(tzinfo=TR)
    f = lambda d: d.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.000Z")  # noqa: E731
    return f(d0), f(d0 + timedelta(days=1))


def _fnum(x: Any, nd: int = 2) -> str:
    try:
        return f"{float(x):.{nd}f}"
    except (TypeError, ValueError):
        return "?"


def _ledger_day(path: str, bot: str, day: str) -> tuple[list, list]:
    from . import ledger as L  # noqa: PLC0415
    if not path or not Path(path).exists():
        raise SectionError("defter_yok")
    try:
        led = L.open_ledger(path, bot, create=False, read_only=True, migrate=False)
    except Exception as e:  # noqa: BLE001
        raise SectionError(getattr(e, "code", None) or type(e).__name__) from None
    try:
        a, b = _istanbul_day_bounds_utc(day)
        closed = led._trades("exit_ts>=? AND exit_ts<?", [a, b], closed=True)
        return closed, led.list_open_trades()
    except Exception as e:  # noqa: BLE001
        raise SectionError(type(e).__name__) from None
    finally:
        led.close()


def _sum(trades: list) -> tuple[float, float]:
    return (sum(t.realized_pnl or 0.0 for t in trades), sum(t.r_multiple or 0.0 for t in trades))


def section_ledger(cfg: TelegramConfig, day: str) -> str:
    closed, opened = _ledger_day(cfg.ledger_path, "learner", day)
    pnl, r = _sum(closed)
    win = sum(1 for t in closed if (t.realized_pnl or 0) > 0)
    loss = sum(1 for t in closed if (t.realized_pnl or 0) <= 0)
    eq = dse = None
    try:
        st = json.loads(Path(cfg.status_path).read_text(encoding="utf-8"))
        eq, dse = st.get("equity"), st.get("day_start_equity")
    except Exception:  # noqa: BLE001
        pass
    lines = [f"öğrenen: kapanan={len(closed)} PnL={pnl:+.2f}$ R={r:+.2f} kazanan/kaybeden={win}/{loss} "
             f"açık={len(opened)}"]
    if dse:
        lim = 0.05 * float(dse)
        lines.append(f"  equity={_fnum(eq)} gün_başı={_fnum(dse)} günlük zarar={max(0.0, -pnl):.2f}$ / "
                     f"bütçe %5={lim:.2f}$")
    else:
        lines.append(f"  equity={_fnum(eq)} gün_başı=? günlük zarar={max(0.0, -pnl):.2f}$ / bütçe %5=?")
    try:
        tc, _to = _ledger_day(cfg.twin_ledger_path, "twin", day)
        tp, tr = _sum(tc)
        lines.append(f"  ikiz: kapanan={len(tc)} PnL={tp:+.2f}$ R={tr:+.2f} (fark PnL {pnl - tp:+.2f}$)")
    except SectionError as e:
        lines.append(f"  ikiz: okunamadı: {e.code}")
    return "\n" + "\n".join(lines)


def section_budget(cfg: TelegramConfig) -> str:
    import dataclasses  # noqa: PLC0415
    from . import budget as B  # noqa: PLC0415
    try:
        bc = B.load_config(cfg.budget_config)
        db = Path(bc.db_path)
        if not db.is_absolute():
            db = Path(cfg.budget_config).resolve().parent.parent / db
        bc = dataclasses.replace(bc, db_path=str(db))
    except Exception:  # noqa: BLE001
        raise SectionError("yapilandirma_gecersiz") from None
    if not db.exists():
        raise SectionError("depo_yok")
    st = B.BudgetGuard(bc).status()
    if not st.config_ok:
        raise SectionError("yapilandirma_gecersiz")
    if not st.store_ok:
        raise SectionError("depo_okunamadi")
    sv = st.services
    names = {"veto": "veto", "lesson": "ders"}
    parts = [f"{names.get(k, k)} {v.used_usd:.2f}$/{v.cap_usd:.2f}$ ({v.state})" for k, v in sv.items()]
    out = f"ay {st.month_used_usd:.2f}$/{st.monthly_cap_usd:.2f}$ ({st.month_state}); bugün: " + ", ".join(parts)
    if not st.prices_verified:
        out += "; fiyatlar doğrulanmadı"
    return out


def section_lesson(cfg: TelegramConfig, now: datetime) -> str:
    if not cfg.lesson_store or not Path(cfg.lesson_store).exists():
        raise SectionError("depo_yok")
    try:
        store = LS.LessonStore(cfg.lesson_store, read_only=True, create=False)
    except Exception as e:  # noqa: BLE001
        raise SectionError(type(e).__name__) from None
    try:
        lines = []
        reqs = store.open_requests()
        if reqs:
            lines.append(f"  bekleyen öneri: {len(reqs)}")
            for r in reqs[:5]:
                try:
                    d = json.loads(r["request_json"])
                    summ = f"{d.get('param')} {d.get('from_value')}→{d.get('to_value')} ({d.get('scope')})"
                except Exception:  # noqa: BLE001
                    summ = f"öneri #{r.get('proposal_id')}"
                lines.append(f"  {r['request_id']}: {summ} -> /onayla {r['request_id']}")
            if len(reqs) > 5:
                lines.append(f"  +{len(reqs) - 5}")
        else:
            lines.append("  bekleyen öneri yok")
        sd, ed = store.get_state("shadow_start_day"), store.get_state("shadow_end_day")
        if sd:
            today = now.astimezone(TR).date()
            n = (today - datetime.fromisoformat(sd).date()).days + 1
            tot = (datetime.fromisoformat(ed).date() - datetime.fromisoformat(sd).date()).days if ed else "?"
            lines.append(f"  gölge dönem: gün {max(n, 0)}/{tot} (bitiş {ed})")
        else:
            lines.append("  gölge dönem: başlamadı")
        rows = store._q("SELECT id, run_day FROM lesson_runs ORDER BY id DESC LIMIT 1")
        if rows:
            ev = store.run_events(rows[0]["id"])
            last = ev[-1] if ev else None
            res = f"{last.status}{'/' + last.code if last and last.code else ''}" if last else "olay yok"
            lines.append(f"  son çalışma: {rows[0]['run_day']} {res}")
        else:
            lines.append("  son çalışma: yok")
        if rows:
            with contextlib.suppress(Exception):
                snap = store.get_snapshot(rows[0]["id"])
                if snap is not None and snap.counterfactual:
                    lines.append("  " + LS.counterfactual_line(snap.counterfactual))
        return "\n" + "\n".join(lines)
    except SectionError:
        raise
    except Exception as e:  # noqa: BLE001
        raise SectionError(type(e).__name__) from None
    finally:
        store.close()


def section_counterfactual(cfg: TelegramConfig, now: datetime) -> str:
    """Alınmayan sinyaller (plan 25a): öğrenen için son 7 günde hesaplanmış varsayımsal sonuçlar (salt okunur)."""
    if not cfg.ledger_path:
        raise SectionError("defter_yok")
    path = Path(cfg.ledger_path).parent / "counterfactual.sqlite"
    if not path.exists():
        return "henüz hesaplanmadı"
    from . import counterfactual as CF  # noqa: PLC0415
    try:
        sm = CF.summary(path, "learner", now=now, days=7)
    except CF.CounterfactualError as e:
        raise SectionError(e.code) from None
    if not sm["n"]:
        return "0"
    return f"{sm['n']}, ort. varsayımsal net R {sm['mean_r_net']:+.2f}"


def default_sections(cfg: TelegramConfig, now: datetime, day: str) -> dict[str, Callable[[], str]]:
    return {"Defter": lambda: section_ledger(cfg, day), "Bütçe": lambda: section_budget(cfg),
            "Ders": lambda: section_lesson(cfg, now),
            "Alınmayan sinyaller (son 7 gün)": lambda: section_counterfactual(cfg, now)}


def run_report(cfg: TelegramConfig, notifier: TelegramNotifier, now: datetime, sections=None) -> str:
    """-> 'sent' | 'spooled' | 'skipped' | 'already'. last_report.json gun anahtari yalniz teslimde yazilir."""
    lp = Path(cfg.var_dir) / "last_report.json"
    try:
        last = json.loads(lp.read_text()).get("day")
    except (OSError, ValueError, AttributeError):
        last = None
    decision, day = report_decision(now, last)
    if decision == "atla":
        return "already" if last == day else "skipped"
    text = build_report(cfg, now, day, default_sections(cfg, now, day) if sections is None else sections)
    if decision == "gecikmis":
        text = "[gecikmiş] " + text
    ok = notifier.send_text(text, "INFO", f"report-{day}")
    if ok:
        try:
            atomic_write_json(lp, {"day": day})
        except Exception:  # noqa: BLE001
            pass
        return "sent"
    return "spooled"
