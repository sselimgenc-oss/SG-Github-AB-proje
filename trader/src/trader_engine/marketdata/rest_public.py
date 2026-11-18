# Kopyalandı: 1l3a-proje/motor/canli/paper_veri.py (kullanıcının kendi kodu; lisans engeli yok)
# Kopya tarihi: 2026-11-16   Kaynak commit: 2dd2dce
# Çalışma zamanında kaynak depo import edilmez/mount edilmez. Değişiklikler: kimlikler İngilizceye çevrildi; pandas/numpy kullanımı ve sembol eşleme tablosu kesildi; saat/uyku zorunlu enjekte; markPriceKlines, premiumIndex, toplam 429 bekleme tavanı, rows_to_bars eklendi (07 §4.1).
"""Binance USDⓈ-M vadeli herkese açık REST istemcisi (API anahtarı YOK, imzalı uç YOK, yalnız GET).

Uçlar (Faz A'da yalnız kayıtlı sahte fixture ile sınanır; uç/parametre adları doğrulanacak):
/fapi/v1/klines, /fapi/v1/markPriceKlines, /fapi/v1/premiumIndex, /fapi/v1/fundingRate, /fapi/v1/exchangeInfo, /fapi/v1/time.

Rate limit: yanıt başlığındaki `X-MBX-USED-WEIGHT-1M` izlenir; eşik (1800) aşılırsa dakika sonuna kadar beklenir. 429 -> `Retry-After`
kadar bekle ve tekrar dene (toplam bekleme tavanı aşılırsa ExchangeBan); 418 ve 451 tekrarlanmaz (ExchangeBan). Ağ/5xx hataları
üstel geri çekilmeyle `max_attempts` kez denenir, sonunda hata YÜKSELİR (sessiz yutma yok).
Saat ve uyku zorunlu enjekte edilir (`now_s`, `sleep`); bu modül gerçek saati okumaz.
"""
from __future__ import annotations

import logging
import math
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from trader_engine.bars import tf_delta
from trader_engine.types import Bar, Kind

log = logging.getLogger("engine.rest_public")

FAPI_BASE = "https://fapi.binance.com"
WEIGHT_THRESHOLD = 1800


class ExchangeError(Exception):
    pass


class ExchangeBan(ExchangeError):
    """418 (IP yasağı), 429 toplam bekleme tavanı aşıldı, 451 (konum kısıtı)."""

    def __init__(self, message: str, http: int | None = None, retry_after_s: int | None = None):
        super().__init__(message)
        self.http = http
        self.retry_after_s = retry_after_s


def _retry_after(headers, default: int = 60) -> int:
    """`Retry-After` güvenli ayrıştırma: sayı değilse ya da negatifse `default` (varsayılan 60)."""
    try:
        v = int(str(headers.get("Retry-After")).strip())
    except (TypeError, ValueError):
        return default
    return v if v >= 0 else default


class PublicRestClient:
    def __init__(self, *, base_url: str = FAPI_BASE, session=None, now_s: Callable[[], float],
                 sleep: Callable[[float], None], max_attempts: int = 5, weight_threshold: int = WEIGHT_THRESHOLD,
                 timeout_s: float = 20.0, max_total_wait_s: float = 300.0,
                 jitter: Callable[[], float] | None = None):
        if session is None:
            import requests  # tembel: içe aktarma anında yüklenmez
            session = requests.Session()
        self.base_url = base_url
        self.session = session
        self.now_s, self.sleep = now_s, sleep
        self.max_attempts = max_attempts
        self.weight_threshold = weight_threshold
        self.timeout_s = timeout_s
        self.max_total_wait_s = max_total_wait_s
        self.jitter = jitter      # None: jitter yok (deterministik); aksi halde [0,1) donen kaynak (D3)
        self._used_weight = 0
        self._weight_ts = 0.0

    def _backoff(self, attempt: int) -> float:
        """Ag/5xx geri cekilmesi: min(2**deneme, 60) sn; jitter varsa en fazla %25 EKLENIR (asla kisalmaz)."""
        base = float(min(2 ** attempt, 60))
        if self.jitter is None:
            return int(base)
        return base * (1.0 + 0.25 * min(max(float(self.jitter()), 0.0), 1.0))

    def used_weight(self) -> int:
        """Son dakikadaki kullanilan agirlik; 60 sn'den eski olcum 0 sayilir (bayat deger doldurmayi kilitlemesin)."""
        if self.now_s() - self._weight_ts >= 60:
            return 0
        return self._used_weight

    def _wait_for_weight(self) -> None:
        now = self.now_s()
        if now - self._weight_ts >= 60:
            self._used_weight = 0
        if self._used_weight >= self.weight_threshold:
            wait = max(1.0, 60 - (now - self._weight_ts))
            log.warning("rate limit: dakikalık ağırlık %d >= %d; %.0f sn bekleniyor", self._used_weight, self.weight_threshold, wait)
            self.sleep(wait)
            self._used_weight = 0

    def get(self, path: str, params: dict | None = None) -> Any:
        """Yalnız GET. Hata iletileri URL/parametre sızdırmaz (yalnız yol + HTTP kodu + kısaltılmış gövde)."""
        last_err: Exception | None = None
        waited_429 = 0.0
        for attempt in range(1, self.max_attempts + 1):
            self._wait_for_weight()
            try:
                r = self.session.get(self.base_url + path, params=params, timeout=self.timeout_s)
            except Exception as e:  # noqa: BLE001  (ağ hatası: loglanır, tekrar denenir, sonunda yükseltilir)
                last_err = ExchangeError(f"{path}: ağ hatası ({type(e).__name__})")
                wait = self._backoff(attempt)
                log.warning("GET %s ağ hatası (%d/%d): %s; %.0f sn sonra tekrar", path, attempt, self.max_attempts, type(e).__name__, wait)
                self.sleep(wait)
                continue
            w = r.headers.get("X-MBX-USED-WEIGHT-1M")
            if w is not None:
                try:
                    self._used_weight, self._weight_ts = int(w), self.now_s()
                except ValueError:
                    pass
            if r.status_code == 200:
                try:
                    return r.json()
                except ValueError:     # bozuk/yarım gövde (JSONDecodeError dahil): çökme yok, tekrar denenir (O10/O11)
                    last_err = ExchangeError(f"{path}: bozuk JSON yanıtı")
                    wait = self._backoff(attempt)
                    log.warning("GET %s bozuk JSON (%d/%d); %.0f sn sonra tekrar", path, attempt, self.max_attempts, wait)
                    self.sleep(wait)
                    continue
            if r.status_code == 429:
                wait = _retry_after(r.headers)
                if waited_429 + wait > self.max_total_wait_s:
                    raise ExchangeBan(f"429 {path}: toplam bekleme tavanı ({self.max_total_wait_s:.0f} sn) aşıldı",
                                      http=429, retry_after_s=wait)
                log.warning("GET %s 429 (rate limit); Retry-After=%s sn", path, wait)
                waited_429 += wait
                self.sleep(wait)
                last_err = ExchangeError(f"429 {path}")
                continue
            if r.status_code == 418:
                ra = _retry_after(r.headers, default=120)     # 418: okunamazsa en az 120 sn
                raise ExchangeBan(f"418 IP yasağı ({path}); Retry-After={ra} sn. Otomatik tekrar yok.", http=418, retry_after_s=ra)
            if r.status_code == 451:
                raise ExchangeBan(f"451 konum kısıtı ({path}): bu makineden Binance vadeli erişimi engelli. {r.text[:200]}", http=451)
            if 500 <= r.status_code < 600:
                last_err = ExchangeError(f"{r.status_code} {path}")
                wait = self._backoff(attempt)
                log.warning("GET %s sunucu hatası %d (%d/%d); %.0f sn sonra tekrar", path, r.status_code, attempt, self.max_attempts, wait)
                self.sleep(wait)
                continue
            raise ExchangeError(f"{r.status_code} {path}: {r.text[:300]}")
        raise ExchangeError(f"{path}: {self.max_attempts} denemede başarısız: {last_err}")

    # ------------------------------------------------------------------ uçlar
    def server_time_ms(self) -> int:
        return int(self.get("/fapi/v1/time")["serverTime"])

    def exchange_info(self) -> dict:
        return self.get("/fapi/v1/exchangeInfo")

    def _klines_at(self, path: str, symbol, interval, start_ms, end_ms, limit) -> list[list]:
        p: dict = {"symbol": symbol, "interval": interval, "limit": limit}
        if start_ms is not None:
            p["startTime"] = start_ms
        if end_ms is not None:
            p["endTime"] = end_ms
        return self.get(path, p)

    def _klines_all_at(self, path: str, symbol, interval, start_ms, end_ms, page, max_pages) -> list[list]:
        rows: list[list] = []
        cur = start_ms
        for _ in range(max_pages):
            part = self._klines_at(path, symbol, interval, cur, end_ms, page)
            if not part:
                break
            rows += part
            if len(part) < page:
                break
            cur = int(part[-1][0]) + 1
        else:
            raise ExchangeError(f"{path}: max_pages={max_pages} aşıldı")
        return rows

    def klines(self, symbol, interval, start_ms=None, end_ms=None, limit=1500) -> list[list]:
        return self._klines_at("/fapi/v1/klines", symbol, interval, start_ms, end_ms, limit)

    def klines_all(self, symbol, interval, start_ms, end_ms=None, *, page=1500, max_pages=200) -> list[list]:
        return self._klines_all_at("/fapi/v1/klines", symbol, interval, start_ms, end_ms, page, max_pages)

    def mark_price_klines(self, symbol, interval, start_ms=None, end_ms=None, limit=1500) -> list[list]:
        return self._klines_at("/fapi/v1/markPriceKlines", symbol, interval, start_ms, end_ms, limit)

    def mark_price_klines_all(self, symbol, interval, start_ms, end_ms=None, *, page=1500, max_pages=200) -> list[list]:
        return self._klines_all_at("/fapi/v1/markPriceKlines", symbol, interval, start_ms, end_ms, page, max_pages)

    def funding_rates(self, symbol, start_ms=None, end_ms=None, limit=1000) -> list[dict]:
        p: dict = {"symbol": symbol, "limit": limit}
        if start_ms is not None:
            p["startTime"] = start_ms
        if end_ms is not None:
            p["endTime"] = end_ms
        return self.get("/fapi/v1/fundingRate", p)

    def funding_rates_all(self, symbol, start_ms, end_ms=None, *, max_pages=100) -> list[dict]:
        rows: list[dict] = []
        seen: set[int] = set()
        cur = start_ms
        for _ in range(max_pages):
            part = self.funding_rates(symbol, cur, end_ms, 1000)
            if not part:
                break
            for x in part:
                t = int(x["fundingTime"])
                if t not in seen:  # çift kayıt süzme
                    seen.add(t)
                    rows.append(x)
            if len(part) < 1000:
                break
            cur = int(part[-1]["fundingTime"]) + 1
        else:
            raise ExchangeError(f"/fapi/v1/fundingRate: max_pages={max_pages} aşıldı")
        return rows

    def premium_index(self, symbol: str | None = None) -> dict | list:
        return self.get("/fapi/v1/premiumIndex", {"symbol": symbol} if symbol else None)


@dataclass(frozen=True)
class AbnormalRow:
    open_ms: int
    reason: str  # "bad_close_time" | "bad_values"


def _pos_finite(x: float) -> bool:
    return math.isfinite(x) and x > 0


def rows_to_bars(pair: str, kind: Kind, tf: str, rows: Sequence[Sequence], now_server_ms: int) -> tuple[list[Bar], list[AbnormalRow]]:
    """Binance kline satırları -> kapanmış Bar listesi + anormal satırlar.

    Kapanış süzgeci: closeTime + 1 <= now_server_ms (kapanmamış satır sessizce atılır). closeTime == open + tf_ms - 1 olmalıdır
    (değilse bad_close_time); o,h,l,c sonlu ve > 0 olmalıdır (değilse bad_values); mark'ta hacim 0 alınır.
    """
    tf_ms = int(tf_delta(tf).total_seconds() * 1000)
    bars: list[Bar] = []
    bad: list[AbnormalRow] = []
    seen: set[int] = set()
    for x in rows:
        open_ms = int(x[0])
        try:
            close_ms = int(x[6])
        except (TypeError, ValueError, IndexError):
            bad.append(AbnormalRow(open_ms, "bad_close_time"))
            continue
        if close_ms != open_ms + tf_ms - 1:
            bad.append(AbnormalRow(open_ms, "bad_close_time"))
            continue
        if close_ms + 1 > now_server_ms:
            continue  # henüz kapanmamış
        try:
            o, h, l, c = (float(x[i]) for i in range(1, 5))
            v = 0.0 if kind == "mark" else float(x[5])
        except (TypeError, ValueError, IndexError):
            bad.append(AbnormalRow(open_ms, "bad_values"))
            continue
        if not all(_pos_finite(z) for z in (o, h, l, c)) or not math.isfinite(v) or v < 0:
            bad.append(AbnormalRow(open_ms, "bad_values"))
            continue
        if open_ms in seen:
            continue
        seen.add(open_ms)
        bars.append(Bar(pair, kind, tf, datetime.fromtimestamp(open_ms / 1000, tz=timezone.utc), o, h, l, c, v))
    bars.sort(key=lambda b: b.open_ts)
    return bars, bad
