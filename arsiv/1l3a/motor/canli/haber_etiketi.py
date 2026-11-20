"""HABER ETİKETİ (kullanıcı kararı 2026-11-19; ön kayıt): coin başına son 24 saatin haber tonu + başlık sayısı.

Kaynak: herkese açık RSS (CoinDesk, Cointelegraph; stdlib urllib + xml.etree, anahtarsız). Başlık, coinin sembolüyle (BTC, tam kelime) ya da
bilinen adıyla (Bitcoin...) eşleşirse sayılır. Ton ∈ [-1, 1] = eşleşen başlıkların ortalama işareti (pozitif sözlük +1, negatif sözlük -1, eşit 0).
Etiket alanları: `haber_tonu` (float | null), `haber_sayisi` (int | null). Kural (`etiket_kurallari`, haber_ters): haber_sayisi >= 2 ve ton girişin tersi ise atla.

Yalnız kripto sembolleri eşleşir (hisse/emtia -> null). Ağ yok / hata / bayat veri -> null (veri yok = engel yok). Önbellek >= 15 dk; hata sonrası
15 dk yeniden denenmez. Lookahead: yalnız yayım zamanı <= karar anı olan başlıklar; karar anı şimdiden > 2 saat geride ise (tekrar/geçmiş oynatma)
etiket null (canlı akış geçmişi doğru temsil etmez). KABA anahtar kelime sayımı: İngilizce, olumsuzlama anlaşılmaz.
Kapatma: L3A_HABER_KAPALI=1 (bağlanmaz).
"""
from __future__ import annotations

import logging
import os
import re
import time
import urllib.request
import xml.etree.ElementTree as ET
from email.utils import parsedate_to_datetime
from typing import Callable, Optional

import pandas as pd

from motor.canli.kayit_etiketleri import _utc  # noqa: E402,F401

log = logging.getLogger("haber_etiketi")

KAYNAKLAR = ("https://www.coindesk.com/arc/outboundfeeds/rss/", "https://cointelegraph.com/rss")
ZAMAN_ASIMI_SN = 4.0
ONBELLEK_SN = 15 * 60
HATA_BEKLEME_SN = 15 * 60
BAYAT_SN = 2 * 3600                           # son başarılı çekim bundan eskiyse (kaynaklar düşmüş) etiket null
PENCERE = pd.Timedelta(hours=24)
SAKLA = pd.Timedelta(hours=25)
KARAR_TAZELIK = pd.Timedelta(hours=2)        # karar anı bundan eskiyse (geçmiş oynatma) etiket null
MAX_BAYT = 3_000_000
KAPATMA_BAYRAGI = "L3A_HABER_KAPALI"

POZITIF = ("surge", "rally", "soar", "gain", "jump", "record", "approv", "bullish", "adopt", "rise", "rebound", "breakout", "inflow", "upgrade", "partnership")
NEGATIF = ("crash", "plunge", "hack", "exploit", "drop", "fall", "ban", "lawsuit", "bearish", "sell-off", "selloff", "liquidat", "fraud", "outflow", "slump", "sue", "dump", "delist")
ISIMLER = {"BTC": ("bitcoin",), "ETH": ("ethereum", "ether"), "SOL": ("solana",), "XRP": ("ripple",), "DOGE": ("dogecoin",), "BNB": ("binance coin",),
           "ADA": ("cardano",), "AVAX": ("avalanche",), "LINK": ("chainlink",), "DOT": ("polkadot",), "LTC": ("litecoin",), "TRX": ("tron",),
           "SUI": ("sui network",), "TON": ("toncoin",), "BCH": ("bitcoin cash",), "XLM": ("stellar",), "NEAR": ("near protocol",), "ARB": ("arbitrum",),
           "OP": ("optimism",), "ATOM": ("cosmos",), "UNI": ("uniswap",), "AAVE": ("aave",), "PEPE": ("pepe",), "SHIB": ("shiba inu",), "HYPE": ("hyperliquid",)}
SEMBOL_ESLEME_MIN_HARF = 3                    # <3 harfli semboller (OP...) yalnız adla eşleşir (gürültü)


def kapali(env=None) -> bool:
    return (os.environ if env is None else env).get(KAPATMA_BAYRAGI) == "1"


def temel_sembol(sembol: str) -> Optional[str]:
    """'BTCUSDT' -> 'BTC'; '1000PEPEUSDT' -> 'PEPE'. Hisse/emtia (paper_takvim.tur) ya da çözülemeyen -> None."""
    try:
        from motor.canli.paper_takvim import tur
        if tur(sembol) != "kripto":
            return None
    except Exception:  # noqa: BLE001
        return None
    s = str(sembol).upper()
    for sonek in ("USDT", "USDC", "BUSD", "USD"):
        if s.endswith(sonek) and len(s) > len(sonek):
            s = s[:-len(sonek)]
            break
    s = re.sub(r"^(1000000|1000|1M)", "", s)
    return s if len(s) >= 2 and s.isalnum() else None


_EKLER = r"(?:s|es|ed|d|ing|ning|ned|ped|ping|ies|ied)?"
_KOK_ONEKLI = ("approv", "liquidat")          # kök + her ek (approve/approved/approval, liquidated/liquidation)


def _ton_deseni(k: str):
    """Kelime sınırlı desen: "ban" "bank"/"banner" ya da "sue" "issue"u eşleştirmez; yalnız kelime başı + açık ek listesi."""
    if k in _KOK_ONEKLI:
        return re.compile(r"\b" + re.escape(k) + r"\w*")
    ek = re.escape(k) + _EKLER
    if k.endswith("e"):
        ek = r"(?:" + re.escape(k) + _EKLER + "|" + re.escape(k[:-1]) + r"ing)"
    return re.compile(r"\b" + ek + r"\b")


_POZ_DESEN = tuple(_ton_deseni(k) for k in POZITIF)
_NEG_DESEN = tuple(_ton_deseni(k) for k in NEGATIF)


def ton(baslik: str) -> int:
    """Kaba başlık tonu: +1 / 0 / -1 (pozitif ve negatif sözlük sayısı farkının işareti; kelime sınırıyla eşleşir)."""
    b = baslik.lower()
    skor = sum(1 for d in _POZ_DESEN if d.search(b)) - sum(1 for d in _NEG_DESEN if d.search(b))
    return 1 if skor > 0 else -1 if skor < 0 else 0


def eslesir(baslik: str, temel: str) -> bool:
    if len(temel) >= SEMBOL_ESLEME_MIN_HARF and re.search(r"(?<![A-Za-z0-9])" + re.escape(temel) + r"(?![A-Za-z0-9])", baslik):
        return True
    bl = baslik.lower()
    return any(re.search(r"(?<![a-z0-9])" + re.escape(a) + r"(?![a-z0-9])", bl) for a in ISIMLER.get(temel, ()))


def rss_coz(icerik, simdi: pd.Timestamp) -> list:
    """RSS -> [(yayım zamanı UTC, başlık)]; tarihsiz, 25 saatten eski ya da ileri tarihli öğeler atılır. DTD/ENTITY içeren ya da bozuk belge -> []."""
    try:
        ham = icerik if isinstance(icerik, (bytes, bytearray)) else str(icerik).encode("utf-8")
        if b"<!DOCTYPE" in ham.upper() or b"<!ENTITY" in ham.upper():
            return []
        out = []
        for oge in ET.fromstring(ham).iter("item"):
            baslik, tarih = (oge.findtext("title") or "").strip(), (oge.findtext("pubDate") or "").strip()
            if not baslik or not tarih:
                continue
            try:
                z = _utc(parsedate_to_datetime(tarih))
            except (TypeError, ValueError):
                continue
            if simdi - z > SAKLA or z > simdi + pd.Timedelta(hours=1):
                continue
            out.append((z, baslik[:200]))
        return out
    except Exception:  # noqa: BLE001
        return []


def _http_al(url: str) -> bytes:
    istek = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 (compatible; paper-haber)", "Accept": "application/rss+xml, application/xml, text/xml"})
    with urllib.request.urlopen(istek, timeout=ZAMAN_ASIMI_SN) as r:      # noqa: S310 (sabit https adresleri)
        return r.read(MAX_BAYT)


class HaberEtiketi:
    def __init__(self, http: Callable = _http_al, saat: Callable = time.time, kaynaklar=KAYNAKLAR):
        self.http, self.saat, self.kaynaklar = http, saat, tuple(kaynaklar)
        self._onbellek = None          # (çekim saati, [(z, başlık)])
        self._yasak = 0.0

    def _basliklar(self) -> Optional[list]:
        simdi = self.saat()
        if self._onbellek is not None and simdi - self._onbellek[0] < ONBELLEK_SN:
            return self._onbellek[1]
        if simdi >= self._yasak:
            toplam, ok = [], 0
            for url in self.kaynaklar:
                try:
                    toplam += rss_coz(self.http(url), pd.Timestamp(simdi, unit="s", tz="UTC"))
                    ok += 1
                except Exception as e:  # noqa: BLE001
                    log.warning("haber akışı alınamadı (%s): %s", url, e)
            if ok:
                self._onbellek = (simdi, toplam)
            else:
                self._yasak = simdi + HATA_BEKLEME_SN
        # tüm kaynaklar düştüyse eski önbellek kısa süre korunur (pencere zaten süzer); BAYAT_SN'yi aşarsa None (bayat veri -> null)
        if self._onbellek is None or simdi - self._onbellek[0] > BAYAT_SN:
            return None
        return self._onbellek[1]

    def etiket(self, sembol: str, t) -> Optional[tuple]:
        """(haber_tonu, haber_sayisi) ya da None (eşleme/veri yok -> null etiketler). Asla istisna fırlatmaz."""
        try:
            temel = temel_sembol(sembol)
            t = _utc(t)
            if temel is None or pd.Timestamp(self.saat(), unit="s", tz="UTC") - t > KARAR_TAZELIK:
                return None
            bas = self._basliklar()
            if bas is None:
                return None
            es = [ton(b) for z, b in bas if t - PENCERE <= z <= t and eslesir(b, temel)]
            if not es:
                return (None, 0)
            return (round(sum(es) / len(es), 4), len(es))
        except Exception:  # noqa: BLE001
            log.exception("haber etiketi alınamadı")
            return None
