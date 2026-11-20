"""YALNIZ KAYIT (2026-11-19): alınmayan sinyaller + işlem/sinyal etiketleri (fonlama, korku/açgözlülük, takvim, rejim).

İşleme / emre / boyuta / risk kararına SIFIR etki: motor yalnız kanca çağırır; buradaki her hata yutulur ve loglanır, ağ istekleri
kısa zaman aşımlıdır (hata sonrası bekleme süresi boyunca yeniden denenmez). Kanca kapalıyken (varsayılan) hiçbir şey çalışmaz.

`alinmayan_sinyaller.jsonl` (durum dizini; ekleme, 50 MB'ı geçince `.1`e taşınır): satır başına bir sinyal
  zaman (UTC, karar anı), hesap, strateji, kol, sembol, tf, yon (long|short), fiyat (sinyal/dolum fiyatı, metin), stop, hedef, zaman_cikisi_mum, neden
  + etiketler: fonlama_orani, oi_usd, oi_degisim_24s (açık pozisyon; yalnız kripto, OiIstemci bağlıysa dolu, yoksa/hatada null), korku_acgozluluk, takvim_bayragi, (rejim_ml_4h, rejim_ml_1d L3A_REJIM_KAPALI=1 değilse; URL varsayılanı YENI_REJIM_URL), haber_tonu + haber_sayisi (haber_etiketi.py; bağlıysa).
"""
from __future__ import annotations

import json
import logging
import os
import time
from pathlib import Path
from typing import Callable, Optional

import pandas as pd

log = logging.getLogger("kayit_etiketleri")

DOSYA_ADI = "alinmayan_sinyaller.jsonl"
MAX_BAYT = 50 * 1024 * 1024
TAKVIM_YOLU = Path(__file__).resolve().parents[2] / "stratejiler" / "ekonomik_takvim.json"
FNG_URL = "https://api.alternative.me/fng/?limit=30&format=json"
ZAMAN_ASIMI_SN = 3.0
HATA_BEKLEME_SN = 3600.0          # ağ hatasından sonra bu süre yeniden denenmez (motor döngüsü her kararda beklemesin)
FNG_TAZELIK = pd.Timedelta(hours=48)
TAKVIM_PENCERE = pd.Timedelta(hours=2)
_YOK = object()
ESKI_REJIM_URL = "https://trader-pano.sselimgenc-c18.workers.dev/rejim.json"        # Access arkasına alındı (2026-11-19); sunucu env'inde hâlâ olabilir
YENI_REJIM_URL = "https://trader-pano-acik.sselimgenc-c18.workers.dev/rejim.json"    # açık yayın (ayrı Worker)


def rejim_url_coz(url: Optional[str], kapali: bool = False) -> Optional[str]:
    """L3A_REJIM_URL çözümü: kapalı -> None; tanımsız/boş -> YENI; eski adres -> YENI (bir kez log); başka adres aynen."""
    if kapali:
        return None
    if not url:
        return YENI_REJIM_URL
    if url.strip() == ESKI_REJIM_URL:
        log.info("L3A_REJIM_URL eski adres (%s): yeni açık adres kullanılıyor (%s)", ESKI_REJIM_URL, YENI_REJIM_URL)
        return YENI_REJIM_URL
    return url


def _utc(x) -> pd.Timestamp:
    t = pd.Timestamp(x)
    return t.tz_localize("UTC") if t.tzinfo is None else t.tz_convert("UTC")


def _http_json(url: str):
    import requests
    r = requests.get(url, timeout=ZAMAN_ASIMI_SN)
    r.raise_for_status()
    return r.json()


def fng_getir() -> list:
    """alternative.me Fear & Greed: [(yayım zamanı UTC, değer)] eskiden yeniye. `timestamp` o günün yayım (00:00 UTC) damgasıdır."""
    veri = _http_json(FNG_URL)["data"]
    return sorted((pd.Timestamp(int(x["timestamp"]), unit="s", tz="UTC"), int(x["value"])) for x in veri)


class Kayit:
    def __init__(self, dizin, fng_fn: Optional[Callable] = None, saat: Callable = time.time, takvim_yolu: Path = TAKVIM_YOLU,
                 rejim_dosya: Optional[str] = None, rejim_url: Optional[str] = None, rejim_http: Callable = _http_json,
                 oi_fn: Optional[Callable] = None, rejim_kapali: Optional[bool] = None, haber_fn: Optional[Callable] = None):
        self.yol = Path(dizin) / DOSYA_ADI
        self.fng_fn = fng_fn or fng_getir
        self.saat = saat
        self.takvim_yolu = Path(takvim_yolu)
        self.rejim_dosya = rejim_dosya if rejim_dosya is not None else os.environ.get("L3A_REJIM_DOSYA")
        if rejim_kapali is None:
            rejim_kapali = os.environ.get("L3A_REJIM_KAPALI") == "1"
        self.rejim_url = rejim_url_coz(rejim_url if rejim_url is not None else os.environ.get("L3A_REJIM_URL"), rejim_kapali)   # L3A_REJIM_KAPALI=1 ile kapanır
        self.rejim_http = rejim_http
        self.oi_fn = oi_fn                # oi_fn(sembol, t) -> (oi_usd, oi_degisim_24s) | None; bağlı değilse (testler/varsayılan) alanlar null
        self.haber_fn = haber_fn          # haber_fn(sembol, t) -> (haber_tonu, haber_sayisi) | None (haber_etiketi.HaberEtiketi.etiket); bağlı değilse alanlar hiç yazılmaz
        self._fng = None                  # (çekim günü, liste)
        self._fng_yasak = 0.0
        self._rejim_url_onbellek = None   # (çekim saati, veri)
        self._rejim_url_yasak = 0.0
        self._takvim = None               # (mtime, olaylar)

    # ------------------------------------------------------------------ etiketler
    def fonlama(self, sembol: str, t, funding_df) -> Optional[float]:
        """Kripto sembolde karar anından ÖNCE (<= t) en son funding oranı (paper'ın zaten taşıdığı veriden); yoksa null."""
        try:
            from motor.canli.paper_takvim import tur
            if tur(sembol) != "kripto" or funding_df is None or not len(funding_df):
                return None
            j = funding_df.index.searchsorted(_utc(t), side="right")
            return float(funding_df["oran"].iloc[j - 1]) if j > 0 else None
        except Exception:  # noqa: BLE001
            log.exception("fonlama etiketi alınamadı")
            return None

    def oi(self, sembol: str, t) -> tuple:
        """Kripto sembolde karar anından ÖNCE kapanmış son saatlik açık pozisyon (USD) ve 24 saatlik oransal değişim (0.10 = %10); yoksa (None, None)."""
        try:
            from motor.canli.paper_takvim import tur
            if self.oi_fn is None or tur(sembol) != "kripto":
                return None, None
            r = self.oi_fn(sembol, _utc(t))
            return (None, None) if r is None else (r[0], r[1])
        except Exception:  # noqa: BLE001
            log.exception("açık pozisyon etiketi alınamadı")
            return None, None

    def korku(self, t) -> Optional[int]:
        """Karar anından önce yayımlanmış (yayım damgası <= t, en çok 48 saat eski) son Fear & Greed değeri; günde bir kez çekilir."""
        try:
            t = _utc(t)
            bugun = pd.Timestamp(self.saat(), unit="s", tz="UTC").date()
            if (self._fng is None or self._fng[0] != bugun) and self.saat() >= self._fng_yasak:
                try:
                    self._fng = (bugun, self.fng_fn())
                except Exception as e:  # noqa: BLE001
                    self._fng_yasak = self.saat() + HATA_BEKLEME_SN
                    log.warning("fear&greed alınamadı: %s", e)
            if self._fng is None:
                return None
            uygun = [(z, v) for z, v in self._fng[1] if z <= t]
            if not uygun or t - uygun[-1][0] > FNG_TAZELIK:
                return None
            return int(uygun[-1][1])
        except Exception:  # noqa: BLE001
            log.exception("korku/açgözlülük etiketi alınamadı")
            return None

    def _takvim_olaylari(self) -> list:
        try:
            mt = self.takvim_yolu.stat().st_mtime
            if self._takvim is None or self._takvim[0] != mt:
                self._takvim = (mt, json.loads(self.takvim_yolu.read_text(encoding="utf-8")).get("olaylar", []))
            return self._takvim[1]
        except FileNotFoundError:
            return []
        except Exception as e:  # noqa: BLE001
            log.warning("ekonomik takvim okunamadı: %s", e)
            return []

    def takvim(self, t) -> Optional[str]:
        """Karar anı bir takvim olayının ±2 saati içindeyse olay adı, değilse null."""
        try:
            t = _utc(t)
            en = None
            for o in self._takvim_olaylari():
                fark = abs(t - _utc(o["zaman"]))
                if fark <= TAKVIM_PENCERE and (en is None or fark < en[0]):
                    en = (fark, str(o["ad"]))
            return en[1] if en else None
        except Exception:  # noqa: BLE001
            log.exception("takvim etiketi alınamadı")
            return None

    def _rejim_ham(self):
        if self.rejim_dosya:
            return json.loads(Path(self.rejim_dosya).read_text(encoding="utf-8"))
        simdi = self.saat()
        o = self._rejim_url_onbellek
        if (o is None or simdi - o[0] > 300) and simdi >= self._rejim_url_yasak:      # >=5 dk önbellek; hatada 1 saat yeniden denenmez
            try:
                self._rejim_url_onbellek = o = (simdi, self.rejim_http(self.rejim_url))
            except Exception as e:  # noqa: BLE001
                self._rejim_url_yasak = simdi + HATA_BEKLEME_SN
                log.warning("rejim yayını alınamadı: %s", e)
        return o[1] if o else None

    def rejim(self, sembol: str, t):
        """ML rejim yayını (`/rejim.json`: surum, uretim_ts, gecerlilik_dk, rejimler, varliklar{cift:{"4h":{rejim,bar_ts},"1d":{...}}}).
        L3A_REJIM_KAPALI=1 ve dosya yoksa _YOK (alanlar hiç yazılmaz). Tanımlıysa {rejim_ml_4h, rejim_ml_1d}: yayın karar anından önce
        üretilmiş ve uretim_ts+gecerlilik_dk geçmemiş olmalı; etiket yalnız bar_ts <= karar anı ise; sembol varliklar anahtarıyla eşleşmezse null."""
        if not (self.rejim_dosya or self.rejim_url):
            return _YOK
        out = {"rejim_ml_4h": None, "rejim_ml_1d": None}
        try:
            t, ham = _utc(t), self._rejim_ham()
            if not ham:
                return out
            uretim = _utc(ham["uretim_ts"])
            if uretim > t or t > uretim + pd.Timedelta(minutes=float(ham.get("gecerlilik_dk", 90))):
                return out
            v = (ham.get("varliklar") or {}).get(sembol)
            for tf in ("4h", "1d"):
                e = (v or {}).get(tf)
                if e and _utc(e["bar_ts"]) <= t and (not ham.get("rejimler") or e["rejim"] in ham["rejimler"]):
                    out[f"rejim_ml_{tf}"] = str(e["rejim"])
        except Exception as e:  # noqa: BLE001
            log.warning("rejim etiketi okunamadı: %s", e)
            return {"rejim_ml_4h": None, "rejim_ml_1d": None}
        return out

    def etiketler(self, sembol: str, t, funding_df=None) -> dict:
        oi_usd, oi_deg = self.oi(sembol, t)
        out = {"fonlama_orani": self.fonlama(sembol, t, funding_df), "oi_usd": oi_usd, "oi_degisim_24s": oi_deg, "korku_acgozluluk": self.korku(t), "takvim_bayragi": self.takvim(t)}
        r = self.rejim(sembol, t)
        if r is not _YOK:
            out.update(r)
        if self.haber_fn is not None:
            out.update(self.haber(sembol, t))
        return out

    def haber(self, sembol: str, t) -> dict:
        """Son 24 saatin haber tonu (-1..1) ve başlık sayısı (yalnız kripto, RSS); eşleme/ağ/hata -> ikisi de null (veri yok = engel yok)."""
        try:
            r = self.haber_fn(sembol, _utc(t))
            return {"haber_tonu": r[0], "haber_sayisi": r[1]} if r else {"haber_tonu": None, "haber_sayisi": None}
        except Exception:  # noqa: BLE001
            log.exception("haber etiketi alınamadı")
            return {"haber_tonu": None, "haber_sayisi": None}

    # ------------------------------------------------------------------ alınmayan sinyal satırı
    def alinmadi(self, satir: dict) -> None:
        try:
            self.yol.parent.mkdir(parents=True, exist_ok=True)
            if self.yol.exists() and self.yol.stat().st_size > MAX_BAYT:
                os.replace(self.yol, self.yol.with_name(self.yol.name + ".1"))
            with open(self.yol, "a", encoding="utf-8", newline="\n") as f:
                f.write(json.dumps(satir, ensure_ascii=False, allow_nan=False) + "\n")
        except Exception:  # noqa: BLE001
            log.exception("alınmayan sinyal satırı yazılamadı")
