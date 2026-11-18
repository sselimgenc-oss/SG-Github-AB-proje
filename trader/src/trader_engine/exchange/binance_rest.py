# Kopyalandı: 1l3a-proje/motor/canli/borsa/binance_futures.py (kullanıcının kendi kodu; lisans engeli yok)
# Kopya tarihi: 2026-11-17   Kaynak commit: 2dd2dce
# Çalışma zamanında kaynak depo import edilmez/mount edilmez. Değişiklikler: kimlikler İngilizceye çevrildi; saat/uyku zorunlu enjekte (time.time/time.sleep varsayılanı yok); hata sınıfları ExchangeReject/ExchangeUncertain/ExchangeAuth/ExchangeBan; kind (read/cancel/setup/order) ve protective önceliği, ağırlık eşikleri, X-MBX-ORDER-COUNT sayaçları ve emir tavanı, 429/403 sessizlik penceresi, sabit taban adresleri, hata iletisi biçimi ve sırların temizlenmesi, userTrades sayfalama, income/commissionRate/apiRestrictions/multiAssets uçları eklendi (11 §4).
"""Binance USDⓈ-M vadeli imzalı REST istemcisi (HMAC-SHA256) — Faz B, 11 §4.

GÜVENLİK: API anahtarı/gizli yalnız kurucuya verilir (çağıran ortam dosyasından okur). Bu modülün ürettiği hiçbir günlük satırı ya da
istisna iletisi sorgu dizgesi, imza, anahtar ya da `X-MBX-APIKEY` başlığı taşımaz. İleti biçimi her yerde:
`<yöntem> <yol> http=<kod> code=<borsa kodu> msg=<en fazla 200 karakter>`. Ağ istisnalarının metni (URL taşıyabilir) kullanılmaz,
yalnız tür adı yazılır.

YENİDEN DENEME: okuma/iptal/ayar istekleri ağ hatası, HTTP 5xx, -1001, -1007 için 1, 2, 4 sn geri çekilmeyle tekrar edilir.
EMİR POST'LARI (kind="order") ağ hatası/zaman aşımı/5xx'te ASLA tekrar edilmez: sonuç belirsizdir (ExchangeUncertain); çağıran emri
kimlikle sorgular. Yalnız -1021 (işlenmedi) emirde de tek kez güvenle tekrar edilir.

ÖN-GÖNDERİM ExchangeBan'ları (sessizlik penceresi, weight_hard, weight_soft) isteğin borsaya HİÇ gönderilmediği anlamına gelir
(kesin "gönderilmedi"; çağıran güvenle yeniden deneyebilir/taramayı atlayabilir). weight_soft uyumaz: gönderilmeden
ExchangeBan(http=None, retry_after_s=dakika penceresi sonuna kalan sn) yükseltir. 429'da yalnız Retry-After <= 5 sn ise okuma
satır içi uyuyup tekrar edilir; daha uzunsa ExchangeBan hemen yükselir (pencere saatle kapanır). Emirde (kind="order") ExchangeReject
yalnız 4xx + tamsayı borsa kodu varsa; aksi halde (408, HTML 404, 302 ...) ExchangeUncertain.

`attempts=` (yalnız anahtar sözcük; request/query_order/query_conditional) o çağrı için `max_attempts`'i geçersiz kılar.

İSTEMCİ İŞ PARÇACIĞI GÜVENLİ DEĞİLDİR (tek iş parçacığı varsayımı). Üretimde `urllib3` günlükçüsü >= INFO tutulmalı (DEBUG URL/imza
yazar).

Saat (`now_ms`) ve uyku (`sleep`) zorunlu enjekte edilir; bu modül gerçek saati okumaz. Taşıma (`session`) enjekte edilebilir:
`session.request(method, url, headers=..., timeout=...)` -> yanıt (`status_code`, `headers`, `json()`, `text`); verilmezse `requests`
tembel içe aktarılır.
"""
from __future__ import annotations

import hashlib
import hmac
import logging
import re
from collections.abc import Callable, Mapping
from decimal import Decimal
from typing import Any, Literal
from urllib.parse import urlencode

from trader_engine.marketdata.rest_public import ExchangeBan, ExchangeError

log = logging.getLogger("engine.binance_rest")

BASES = {"live": "https://fapi.binance.com", "testnet": "https://testnet.binancefuture.com"}   # sabit; yapılandırılamaz [V-2]
SAPI_BASE = "https://api.binance.com"          # yalnız apiRestrictions [V-6]
EXCHANGE_ORDER_LIMIT_10S = 300                 # borsa emir sınırları (varsayım; koruyucu tavan = %80)
EXCHANGE_ORDER_LIMIT_1M = 1200
PROTECTIVE_FRACTION = 0.8
AUTH_CODES = {-2014, -2015, -1022}
TRANSIENT_CODES = {-1001, -1007}
CANCEL_OK_CODES = {-2011, -2013}
SETUP_OK_CODES = {-4046, -4059}
CONDITIONAL_TYPES = {"STOP_MARKET", "TAKE_PROFIT_MARKET"}
_CLASSIC_COND_TYPES = {"STOP", "STOP_MARKET", "TAKE_PROFIT", "TAKE_PROFIT_MARKET", "TRAILING_STOP_MARKET"}
SEVEN_DAYS_MS = 7 * 24 * 3600 * 1000 - 1
_SIG = re.compile(r"signature=[0-9a-fA-F]+", re.I)


class ExchangeReject(ExchangeError):
    """Borsa isteği işledi ve reddetti (kesin) ya da istemci yerel tavanı gönderimi engelledi (http=0)."""

    def __init__(self, message: str, *, code: int | None = None, http: int = 0, msg: str = ""):
        super().__init__(message)
        self.code, self.http, self.msg = code, http, msg


class ExchangeUncertain(ExchangeError):
    """İsteğin işlenip işlenmediği bilinmiyor (ağ hatası, zaman aşımı, 5xx, -1001, -1007)."""

    def __init__(self, message: str, http: int | None = None):
        super().__init__(message)
        self.http = http


class ExchangeAuth(ExchangeError):
    """401, -2014, -2015, -1022 (tekrar yok)."""

    def __init__(self, message: str, *, code: int | None = None, http: int | None = None):
        super().__init__(message)
        self.code, self.http = code, http


def sign(query: str, secret: str) -> str:
    """HMAC-SHA256(secret, query) onaltılık (11 §16.1)."""
    return hmac.new(secret.encode(), query.encode(), hashlib.sha256).hexdigest()


def fmt_num(x: Any) -> str:
    """Sayıyı üstel gösterimsiz, sondaki sıfırsız dizgeye çevirir (Decimal / float / int / bool)."""
    if isinstance(x, bool):
        return "true" if x else "false"
    if isinstance(x, float):
        x = Decimal(repr(x))
    if isinstance(x, int):
        return str(x)
    if isinstance(x, Decimal):
        if not x.is_finite():
            raise ValueError("sonlu olmayan sayı")
        if x == 0:
            return "0"
        return format(x.normalize(), "f")
    return str(x)


def encode_params(params: Mapping[str, Any] | None) -> str:
    """Eklenme sırasıyla urlencode; None değerler atlanır; sayılar fmt_num ile."""
    items = [(k, fmt_num(v)) for k, v in (params or {}).items() if v is not None]
    return urlencode(items)


def _hdr(headers: Any, name: str) -> str | None:
    if not headers:
        return None
    try:
        v = headers.get(name)
        if v is not None:
            return v
        low = name.lower()
        for k, val in headers.items():
            if str(k).lower() == low:
                return val
    except Exception:  # noqa: BLE001
        return None
    return None


def _int_or(v: Any, default: int | None = None) -> int | None:
    try:
        return int(float(v))
    except (TypeError, ValueError):
        return default


def _retry_after(headers: Any) -> int:
    """Retry-After saniye; ayrıştırılamazsa 60; [1, 3600] aralığına kısılır."""
    v = _int_or(_hdr(headers, "Retry-After"), 60)
    return max(1, min(3600, 60 if v is None else v))


class SignedRestClient:
    def __init__(self, *, env: Literal["testnet", "live"], api_key: str, api_secret: str, session=None,
                 now_ms: Callable[[], int], sleep: Callable[[float], None], recv_window_ms: int = 5000,
                 read_timeout_s: float = 10.0, order_timeout_s: tuple[float, float] = (2.0, 3.0),
                 max_attempts: int = 4, weight_soft: int = 1200, weight_hard: int = 1800,
                 order_cap_10s: int = 20, order_cap_1m: int = 100, conditional_mode: str = "algo"):
        if env not in BASES:
            raise ValueError("env testnet|live olmalı")
        if conditional_mode not in ("algo", "classic"):
            raise ValueError("conditional_mode algo|classic olmalı")
        if not api_key or not api_secret:
            raise ValueError("api_key/api_secret boş olamaz")
        if session is None:
            import requests  # tembel: içe aktarma anında yüklenmez
            session = requests.Session()
            session.max_redirects = 0            # yönlendirme izlenmez (imzalı istek başka adrese gitmez)
        self.env = env
        self._base = BASES[env]
        self._api_key, self._api_secret = api_key, api_secret
        self.session = session
        self.now_ms, self.sleep = now_ms, sleep
        self.recv_window_ms = recv_window_ms
        self.read_timeout_s, self.order_timeout_s = read_timeout_s, order_timeout_s
        self.max_attempts = max(1, int(max_attempts))
        self.weight_soft, self.weight_hard = weight_soft, weight_hard
        self.order_cap_10s, self.order_cap_1m = order_cap_10s, order_cap_1m
        self.conditional_mode = conditional_mode
        self.clock_offset_ms = 0
        self.last_sync_ms: int | None = None
        self.counters: dict[str, int] = {}
        self._used_weight, self._weight_ts_ms = 0, 0
        self._order_sent_ms: list[int] = []
        self._hdr_cnt: dict[str, tuple[int, int]] = {}       # "10s"/"1m" -> (değer, alınma zamanı)
        self._ban_until_ms, self._ban_http = 0, None
        self._ban_403_s = 0
        self._testnet_warn_ms: int | None = None      # testnet ağırlık uyarısı hız sınırı
        self._last_ok_ms: int | None = None

    def __repr__(self) -> str:                      # anahtar/gizli asla gösterilmez
        return f"SignedRestClient(env={self.env!r})"

    # ------------------------------------------------------------------ yardımcılar
    def _bump(self, name: str) -> None:
        self.counters[name] = self.counters.get(name, 0) + 1

    def _scrub(self, text: Any) -> str:
        s = str(text)
        for secret in (self._api_secret, self._api_key):
            if secret:
                s = s.replace(secret, "***")
        s = _SIG.sub("signature=***", s)
        return " ".join(s.split())[:200]

    def _fmt(self, method: str, path: str, http: Any, code: Any, msg: Any) -> str:
        return f"{method} {path} http={http} code={code} msg={self._scrub(msg)}"

    def _order_counts(self, now: int) -> tuple[int, int]:
        self._order_sent_ms = [t for t in self._order_sent_ms if now - t < 60_000]
        c10 = sum(1 for t in self._order_sent_ms if now - t < 10_000)
        c1m = len(self._order_sent_ms)
        for key, window in (("10s", 10_000), ("1m", 60_000)):
            v = self._hdr_cnt.get(key)
            if v and now - v[1] < window:
                if key == "10s":
                    c10 = max(c10, v[0])
                else:
                    c1m = max(c1m, v[0])
        return c10, c1m

    def _cur_weight(self, now: int) -> int:
        if now - self._weight_ts_ms >= 60_000:
            return 0
        return self._used_weight

    def health(self) -> dict:
        now = self.now_ms()
        c10, c1m = self._order_counts(now)
        return {"used_weight": self._cur_weight(now), "order_count_10s": c10, "order_count_1m": c1m,
                "clock_offset_ms": self.clock_offset_ms, "ban_until_ms": self._ban_until_ms, "last_ok_ms": self._last_ok_ms}

    # ------------------------------------------------------------------ saat
    def sync_time(self) -> int:
        return self._sync(attempts=None, timeout=None)

    def sync_time_once(self) -> int:
        """DD-2 (D5): periyodik esitleme icin TEK deneme (geri cekilme yok) ve KISA zaman asimi (order_timeout_s): ag
        sorununda dongu en fazla birkac saniye bloke olur."""
        return self._sync(attempts=1, timeout=self.order_timeout_s)

    def _sync(self, *, attempts: int | None, timeout: Any) -> int:
        t0 = self.now_ms()
        r = self._send("GET", "/fapi/v1/time", None, kind="read", signed=False, protective=True, base=self._base,
                       attempts=attempts, timeout=timeout)
        t1 = self.now_ms()
        st = r.get("serverTime") if isinstance(r, dict) else None
        if isinstance(st, bool) or not isinstance(st, (int, float, str)) or _int_or(st) is None:
            raise ExchangeUncertain(self._fmt("GET", "/fapi/v1/time", 200, None, "bad_server_time"), http=200)
        self.clock_offset_ms = int(_int_or(st)) - (t0 + t1) // 2
        self.last_sync_ms = t1
        off = abs(self.clock_offset_ms)
        if off > 5000:
            self._bump("clock_offset")
            log.log(logging.CRITICAL, "saat farkı %d ms > 5000 (sunucu NTP'si bozuk olabilir)", self.clock_offset_ms)
        elif off > 1000:
            self._bump("clock_offset")
            log.log(logging.WARNING, "saat farkı %d ms > 1000", self.clock_offset_ms)
        return self.clock_offset_ms

    # ------------------------------------------------------------------ çekirdek
    def request(self, method: str, path: str, params: dict | None, *, kind: Literal["read", "cancel", "setup", "order"],
                signed: bool = True, protective: bool = False, attempts: int | None = None) -> Any:
        return self._send(method, path, params, kind=kind, signed=signed, protective=protective, base=self._base, attempts=attempts)

    def _send(self, method: str, path: str, params: dict | None, *, kind: str, signed: bool, protective: bool, base: str,
              attempts: int | None = None, timeout: Any = None) -> Any:
        if kind not in ("read", "cancel", "setup", "order"):
            raise ValueError(f"kind: {kind!r}")
        is_order = kind == "order"
        now = self.now_ms()
        max_attempts = self.max_attempts if attempts is None else max(1, int(attempts))
        # 1) sessizlik penceresi (429/418/403): koruyucular dahil hiçbir istek gitmez
        if now < self._ban_until_ms:
            left = -(-(self._ban_until_ms - now) // 1000)
            raise ExchangeBan(self._fmt(method, path, self._ban_http, None, f"ban_window {left}s"), http=self._ban_http, retry_after_s=left)
        # 2) ağırlık eşikleri
        w = self._cur_weight(now)
        if self.env == "testnet":
            # mentor: testnet ağırlık başlığı paylaşımlı/gürültülü → iki ağırlık eşiği de atlanır (429/418/403 ve sessizlik penceresi geçerli)
            if w >= self.weight_soft and (self._testnet_warn_ms is None or now - self._testnet_warn_ms >= 60_000):
                self._testnet_warn_ms = now
                log.log(logging.WARNING, "testnet ağırlık başlığı %d >= %d yok sayılıyor (paylaşımlı/gürültülü)", w, self.weight_soft)
        elif w >= self.weight_hard and not protective:
            raise ExchangeBan(self._fmt(method, path, None, None, f"weight_hard {w}"), http=None)
        if self.env != "testnet" and w >= self.weight_soft and not protective and kind == "read":
            left = max(1, -(-(self._weight_ts_ms + 60_000 - now) // 1000))
            log.log(logging.WARNING, "ağırlık %d >= %d; okuma gönderilmedi (%d sn)", w, self.weight_soft, left)
            raise ExchangeBan(self._fmt(method, path, None, None, f"weight_soft {w}"), http=None, retry_after_s=left)
        # 3) emir tavanı
        if is_order:
            c10, c1m = self._order_counts(now)
            if protective:
                over = c10 >= PROTECTIVE_FRACTION * EXCHANGE_ORDER_LIMIT_10S or c1m >= PROTECTIVE_FRACTION * EXCHANGE_ORDER_LIMIT_1M
            else:
                over = c10 >= self.order_cap_10s or c1m >= self.order_cap_1m
            if over:
                self._bump("order_rate_cap")
                raise ExchangeReject(self._fmt(method, path, 0, None, "order_rate_cap"), code=None, http=0, msg="order_rate_cap")

        resynced = False
        attempt = 0
        last_err: ExchangeError | None = None
        while attempt < max_attempts:
            attempt += 1
            query = encode_params(params)
            headers: dict[str, str] = {}
            if signed:
                ts = self.now_ms() + self.clock_offset_ms
                extra = urlencode([("recvWindow", str(self.recv_window_ms)), ("timestamp", str(ts))])
                query = (query + "&" if query else "") + extra
                query += "&signature=" + sign(query, self._api_secret)
                headers["X-MBX-APIKEY"] = self._api_key
            url = base + path + ("?" + query if query else "")
            timeout_v = timeout if timeout is not None else (self.order_timeout_s if is_order else self.read_timeout_s)
            if is_order:
                self._order_sent_ms.append(self.now_ms())
            exc_name = None
            r = None
            try:
                r = self.session.request(method, url, headers=headers, timeout=timeout_v)
            except Exception as e:  # noqa: BLE001  (yalnız tür adı; metin URL/imza taşıyabilir)
                exc_name = type(e).__name__
            if r is None:
                last_err = ExchangeUncertain(self._fmt(method, path, None, None, f"network_error {exc_name}"), http=None)
                if is_order:
                    raise last_err
                if attempt < max_attempts:
                    wait = 2 ** (attempt - 1)
                    log.log(logging.WARNING, "%s (%d/%d); %d sn sonra tekrar", last_err, attempt, max_attempts, wait)
                    self.sleep(wait)
                continue

            status = int(r.status_code)
            h = getattr(r, "headers", None)
            self._read_counters(h)
            body: Any = None
            code, msg = None, ""
            eff = status                               # sınıflandırma durumu (200 + gövdede hata kodu -> 4xx gibi)
            if status == 200:
                bad_json = False
                try:
                    body = r.json()
                except Exception:  # noqa: BLE001
                    bad_json = True
                if bad_json:
                    last_err = ExchangeUncertain(self._fmt(method, path, 200, None, "bad_json"), http=200)
                    if is_order:
                        raise last_err from None
                    if attempt < max_attempts:
                        self.sleep(2 ** (attempt - 1))
                    continue
                bc = body.get("code") if isinstance(body, dict) else None
                if is_order and isinstance(bc, int) and not isinstance(bc, bool) and bc < 0:
                    code, msg, eff = bc, str(body.get("msg", "")), 400
                else:
                    self._last_ok_ms = self.now_ms()
                    self._ban_403_s = 0
                    return body
            else:
                bad_json = False
                try:
                    j = r.json()
                except Exception:  # noqa: BLE001
                    bad_json = True
                if bad_json:
                    msg = str(getattr(r, "text", "") or "")
                elif isinstance(j, dict):
                    code, msg = _int_or(j.get("code")), str(j.get("msg", ""))
            text = self._fmt(method, path, status, code, msg)

            if status == 429:
                ra = _retry_after(h)
                self._ban_until_ms, self._ban_http = self.now_ms() + ra * 1000, 429
                self._bump("http_429")
                log.log(logging.WARNING, "%s", text)
                if is_order:
                    raise ExchangeReject(self._fmt(method, path, 429, code, "rate_limited"), code=None, http=429, msg="rate_limited")
                last_err = ExchangeBan(text, http=429, retry_after_s=ra)
                if ra <= 5 and attempt < max_attempts:
                    self.sleep(ra)                    # yalnız kısa Retry-After satır içi beklenir; pencere saatle kapanır
                    continue
                raise last_err
            if status == 418:
                ra = _retry_after(h)
                self._ban_until_ms, self._ban_http = self.now_ms() + ra * 1000, 418
                self._bump("http_418")
                raise ExchangeBan(text, http=418, retry_after_s=ra)
            if status == 451:
                self._bump("http_451")
                raise ExchangeBan(text, http=451)
            if status == 403:
                self._ban_403_s = 300 if self._ban_403_s == 0 else min(self._ban_403_s * 2, 1800)
                self._ban_until_ms, self._ban_http = self.now_ms() + self._ban_403_s * 1000, 403
                self._bump("http_403")
                raise ExchangeBan(text, http=403, retry_after_s=self._ban_403_s)
            if code == -1021 and not resynced and status < 500:
                resynced = True
                attempt -= 1                      # yeniden eşitleme deneme hakkı tüketmez
                log.log(logging.WARNING, "%s; saat eşitleniyor", text)
                try:                              # tek deneme, geri çekilme yok; emirde emir zaman aşımı
                    self._sync(attempts=1, timeout=self.order_timeout_s if is_order else None)
                except Exception:  # noqa: BLE001
                    raise ExchangeReject(text, code=-1021, http=400, msg=self._scrub(msg)) from None
                continue
            if status == 401 or code in AUTH_CODES:
                raise ExchangeAuth(text, code=code, http=status)
            if status >= 500 or code in TRANSIENT_CODES:
                last_err = ExchangeUncertain(text, http=status)
                if is_order:
                    raise last_err
                if attempt < max_attempts:
                    wait = 2 ** (attempt - 1)
                    log.log(logging.WARNING, "%s (%d/%d); %d sn sonra tekrar", text, attempt, max_attempts, wait)
                    self.sleep(wait)
                continue
            if kind == "cancel" and code in CANCEL_OK_CODES:
                return None
            if kind == "setup" and code in SETUP_OK_CODES:
                return None
            if is_order and not (400 <= eff < 500 and code is not None):
                raise ExchangeUncertain(text, http=status)     # 408, HTML 404, 302 ...: işlendi mi bilinmez
            raise ExchangeReject(text, code=code, http=status, msg=self._scrub(msg))
        raise last_err if last_err is not None else ExchangeUncertain(self._fmt(method, path, None, None, "exhausted"))

    def _read_counters(self, headers: Any) -> None:
        now = self.now_ms()
        w = _int_or(_hdr(headers, "X-MBX-USED-WEIGHT-1M"))
        if w is not None:
            self._used_weight, self._weight_ts_ms = w, now
        for key, name in (("10s", "X-MBX-ORDER-COUNT-10S"), ("1m", "X-MBX-ORDER-COUNT-1M")):
            v = _int_or(_hdr(headers, name))
            if v is not None:
                self._hdr_cnt[key] = (v, now)

    # ------------------------------------------------------------------ herkese açık
    def exchange_info(self) -> dict:
        return self.request("GET", "/fapi/v1/exchangeInfo", None, kind="read", signed=False)

    def book_ticker(self, symbol: str, *, timeout: tuple[float, float] = (0.25, 0.25)) -> dict:
        """WP-3 (defter-ek-alanlar 3.5): en iyi alis/satis (`bookTicker`). TEK deneme, baglanti+okuma toplami <= 0,5 sn;
        yeniden deneme/uyku/saat esitleme yok. Imzasiz kamusal okuma; yalniz kayit icindir."""
        return self._send("GET", "/fapi/v1/ticker/bookTicker", {"symbol": symbol}, kind="read", signed=False,
                          protective=False, base=self._base, attempts=1, timeout=timeout)

    def mark_price(self, symbol: str) -> Decimal:
        r = self.request("GET", "/fapi/v1/premiumIndex", {"symbol": symbol}, kind="read", signed=False)
        return Decimal(str(r["markPrice"]))

    # ------------------------------------------------------------------ hesap / okuma
    def account(self, *, protective: bool = False) -> dict:
        return self.request("GET", "/fapi/v2/account", None, kind="read", protective=protective)

    def position_risk(self, symbol: str | None = None, *, protective: bool = False) -> list[dict]:
        return self.request("GET", "/fapi/v2/positionRisk", {"symbol": symbol} if symbol else None, kind="read", protective=protective)

    def open_orders(self, symbol: str | None = None, *, protective: bool = False) -> list[dict]:
        return self.request("GET", "/fapi/v1/openOrders", {"symbol": symbol} if symbol else None, kind="read", protective=protective)

    def open_conditionals(self, symbol: str | None = None, *, protective: bool = False) -> list[dict]:
        p = {"symbol": symbol} if symbol else None
        if self.conditional_mode == "algo":
            return self.request("GET", "/fapi/v1/openAlgoOrders", p, kind="read", protective=protective)
        rows = self.request("GET", "/fapi/v1/openOrders", p, kind="read", protective=protective)
        return [x for x in rows if str(x.get("origType", x.get("type", ""))) in _CLASSIC_COND_TYPES]

    # ------------------------------------------------------------------ emirler
    def new_market(self, symbol, side, qty, client_id: str, reduce_only: bool, *, protective: bool | None = None) -> dict:
        p: dict[str, Any] = {"symbol": symbol, "side": side, "type": "MARKET", "quantity": qty,
                             "newClientOrderId": client_id, "newOrderRespType": "RESULT"}
        if reduce_only:
            p["reduceOnly"] = "true"
        return self.request("POST", "/fapi/v1/order", p, kind="order", protective=reduce_only if protective is None else protective)

    def new_conditional(self, symbol, order_type, side, qty, trigger, client_id: str, working_type: str, *,
                        protective: bool | None = None) -> dict:
        if order_type not in CONDITIONAL_TYPES:
            raise ValueError(f"order_type: {order_type!r}")
        prot = (order_type == "STOP_MARKET") if protective is None else protective
        if self.conditional_mode == "algo":
            p = {"algoType": "CONDITIONAL", "symbol": symbol, "side": side, "type": order_type, "quantity": qty,
                 "triggerPrice": trigger, "workingType": working_type, "reduceOnly": "true", "priceProtect": "false",
                 "clientAlgoId": client_id}
            return self.request("POST", "/fapi/v1/algoOrder", p, kind="order", protective=prot)
        p = {"symbol": symbol, "side": side, "type": order_type, "quantity": qty, "stopPrice": trigger,
             "workingType": working_type, "reduceOnly": "true", "newClientOrderId": client_id}
        return self.request("POST", "/fapi/v1/order", p, kind="order", protective=prot)

    def _query(self, path: str, params: dict, protective: bool, attempts: int | None = None) -> dict | None:
        try:
            return self.request("GET", path, params, kind="read", protective=protective, attempts=attempts)
        except ExchangeReject as e:
            if e.code == -2013:
                return None
            raise

    def query_order(self, symbol, client_id: str, *, protective: bool = True, attempts: int | None = None) -> dict | None:
        return self._query("/fapi/v1/order", {"symbol": symbol, "origClientOrderId": client_id}, protective, attempts)

    def query_order_by_id(self, symbol, order_id, *, protective: bool = True, attempts: int | None = None) -> dict | None:
        """GET /fapi/v1/order?orderId=: yalnız -2013 ("emir yok") None döner; diğer her ret/hata çağırana yükselir."""
        oid = int(order_id) if str(order_id).isdigit() else order_id
        return self._query("/fapi/v1/order", {"symbol": symbol, "orderId": oid}, protective, attempts)

    def force_orders(self, symbol, start_ms: int, auto_close_type: str = "LIQUIDATION", *, protective: bool = True,
                     attempts: int | None = None) -> list[dict]:
        """GET /fapi/v1/forceOrders (likidasyon / ADL emirleri); boş yanıt -> []."""
        if auto_close_type not in ("LIQUIDATION", "ADL"):
            raise ValueError(f"auto_close_type: {auto_close_type!r}")
        r = self.request("GET", "/fapi/v1/forceOrders", {"symbol": symbol, "autoCloseType": auto_close_type,
                                                         "startTime": int(start_ms), "limit": 50},
                         kind="read", protective=protective, attempts=attempts)
        return list(r) if isinstance(r, list) else []

    def query_conditional(self, symbol, client_id: str, *, protective: bool = True, attempts: int | None = None) -> dict | None:
        if self.conditional_mode == "algo":
            return self._query("/fapi/v1/algoOrder", {"clientAlgoId": client_id}, protective, attempts)
        return self.query_order(symbol, client_id, protective=protective, attempts=attempts)

    def cancel_order(self, symbol, client_id: str, *, protective: bool = False) -> None:
        self.request("DELETE", "/fapi/v1/order", {"symbol": symbol, "origClientOrderId": client_id}, kind="cancel", protective=protective)

    def cancel_conditional(self, symbol, client_id: str, *, protective: bool = False) -> None:
        if self.conditional_mode == "algo":
            self.request("DELETE", "/fapi/v1/algoOrder", {"clientAlgoId": client_id}, kind="cancel", protective=protective)
        else:
            self.cancel_order(symbol, client_id, protective=protective)

    # ------------------------------------------------------------------ geçmiş
    def user_trades(self, symbol, start_ms: int, end_ms: int | None = None) -> list[dict]:
        end_ms = int(end_ms) if end_ms is not None else self.now_ms() + self.clock_offset_ms
        seen: set = set()
        out: list[dict] = []
        start = int(start_ms)
        while start <= end_ms:
            stop = min(start + SEVEN_DAYS_MS, end_ms)
            cur = start
            while True:
                page = self.request("GET", "/fapi/v1/userTrades", {"symbol": symbol, "startTime": cur, "endTime": stop, "limit": 1000},
                                    kind="read") or []
                new = 0
                for x in page:
                    if x["id"] not in seen:
                        seen.add(x["id"])
                        out.append(x)
                        new += 1
                if len(page) < 1000:
                    break
                last_t = max(int(x["time"]) for x in page)
                # Not: aynı ms'de >1000 dolum varsa last_t + 1 bazılarını atlar; bu yüzden yeni kayıt geldikçe cur=last_t (kayıt tekrarı
                # id ile elenir). Tek ms'de 1000'den fazla dolum pratikte yok; gerekirse fromId ile sayfalanmalı.
                cur = last_t if new and last_t > cur else last_t + 1
                if cur > stop:
                    break
            start = stop + 1
        return sorted(out, key=lambda f: (int(f["time"]), int(f["id"])))

    def income(self, symbol, income_type: str, start_ms: int, end_ms: int) -> list[dict]:
        return self.request("GET", "/fapi/v1/income", {"symbol": symbol, "incomeType": income_type, "startTime": int(start_ms),
                                                       "endTime": int(end_ms), "limit": 1000}, kind="read")

    def commission_rate(self, symbol) -> dict:
        return self.request("GET", "/fapi/v1/commissionRate", {"symbol": symbol}, kind="read")

    def api_restrictions(self) -> dict:
        if self.env != "live":
            raise ExchangeError("api_restrictions yalnız live kipte")
        return self._send("GET", "/sapi/v1/account/apiRestrictions", None, kind="read", signed=True, protective=False, base=SAPI_BASE)

    # ------------------------------------------------------------------ hesap kipi
    def position_mode(self) -> bool:
        r = self.request("GET", "/fapi/v1/positionSide/dual", None, kind="read")
        return str(r["dualSidePosition"]).lower() == "true"

    def set_one_way(self) -> None:
        self.request("POST", "/fapi/v1/positionSide/dual", {"dualSidePosition": "false"}, kind="setup")

    def multi_assets(self) -> bool:
        r = self.request("GET", "/fapi/v1/multiAssetsMargin", None, kind="read")
        return str(r["multiAssetsMargin"]).lower() == "true"

    def set_single_asset(self) -> None:
        self.request("POST", "/fapi/v1/multiAssetsMargin", {"multiAssetsMargin": "false"}, kind="setup")

    def set_isolated(self, symbol) -> None:
        self.request("POST", "/fapi/v1/marginType", {"symbol": symbol, "marginType": "ISOLATED"}, kind="setup")

    def set_leverage(self, symbol, leverage: int) -> None:
        self.request("POST", "/fapi/v1/leverage", {"symbol": symbol, "leverage": int(leverage)}, kind="setup")
