"""Binance USDⓈ-M açık pozisyon (open interest) etiketi için herkese açık, imzasız istemci (YALNIZ KAYIT/etiket verisi).

Uç: /futures/data/openInterestHist?symbol=..&period=1h&limit=30 (ağırlık 1). paper_veri.FapiIstemci ile AYNI host yasağını paylaşır
(binance_futures.yasak_oku/yasak_ayarla; 418/429 -> o süre HİÇ istek gitmez) ve aynı dakikalık ağırlık eşiğine (AGIRLIK_ESIGI) uyar.
Motoru bloklamaz: zaman aşımı 5 sn, yeniden deneme yok, her hata -> None (+ HATA_BEKLEME_SN boyunca yeni istek yok), sembol başına önbellek >= 15 dk.
Lookahead yok: yalnız zaman damgası + 1 saat <= karar anı olan (kapanmış) saatlik değer kullanılır.
"""
from __future__ import annotations

import logging
import time
from typing import Callable, Optional

import pandas as pd

from motor.canli.borsa import binance_futures as bf

log = logging.getLogger("oi_istemci")

FAPI = "https://fapi.binance.com"
YOL = "/futures/data/openInterestHist"
ZAMAN_ASIMI_SN = 5.0
ONBELLEK_SN = 900.0           # >= 15 dk
HATA_BEKLEME_SN = 900.0       # hatadan sonra bu süre yeni istek yok (motor her kararda 5 sn beklemesin)
SAAT = pd.Timedelta(hours=1)
BAYAT = pd.Timedelta(hours=3)  # kapanmış son değer karar anından bu kadar eskiyse null
AGIRLIK_ESIGI = 1800


class OiIstemci:
    def __init__(self, taban: str = FAPI, oturum=None, saat: Callable = time.time, yasak_dosyasi=None):
        import requests
        self.taban, self.oturum, self.saat = taban, oturum or requests.Session(), saat
        self.host = bf.host_al(taban)
        self._paylas = saat is time.time
        self.yasak_dosyasi = yasak_dosyasi
        self._onbellek: dict = {}
        self._hata_bitis = 0.0
        self._agirlik, self._agirlik_zamani = 0, 0.0

    def _cek(self, sembol: str) -> list:
        simdi = self.saat()
        if simdi < max(self._hata_bitis, bf.yasak_oku(self.host) if self._paylas else 0.0):
            raise RuntimeError("yasak/bekleme sürüyor")
        if simdi - self._agirlik_zamani < 60 and self._agirlik >= AGIRLIK_ESIGI:
            raise RuntimeError("dakikalık ağırlık eşiği")
        r = self.oturum.get(self.taban + YOL, params={"symbol": sembol, "period": "1h", "limit": 30}, timeout=ZAMAN_ASIMI_SN)
        w = r.headers.get("X-MBX-USED-WEIGHT-1M")
        if w is not None:
            self._agirlik, self._agirlik_zamani = int(w), simdi
        if r.status_code in (418, 429):
            bitis = simdi + bf._retry_after(r, 300 if r.status_code == 418 else 60)
            self._hata_bitis = max(self._hata_bitis, bitis)
            if self._paylas:
                bf.yasak_ayarla(bitis, self.yasak_dosyasi, self.host)
            raise RuntimeError(f"{r.status_code} yasak/rate limit")
        if r.status_code != 200:
            raise RuntimeError(f"HTTP {r.status_code}")
        return [(pd.Timestamp(int(x["timestamp"]), unit="ms", tz="UTC"), float(x["sumOpenInterestValue"])) for x in r.json()]

    def __call__(self, sembol: str, t) -> Optional[tuple]:
        """(oi_usd, oi_degisim_24s oransal) ya da None. t: karar anı (UTC)."""
        try:
            simdi = self.saat()
            o = self._onbellek.get(sembol)
            if o is None or simdi - o[0] >= ONBELLEK_SN:
                try:
                    o = (simdi, sorted(self._cek(sembol)))
                    self._onbellek[sembol] = o
                except Exception as e:  # noqa: BLE001
                    self._hata_bitis = max(self._hata_bitis, simdi + HATA_BEKLEME_SN)
                    log.warning("açık pozisyon alınamadı (%s): %s", sembol, e)
                    o = self._onbellek.get(sembol)       # eski önbellek (karar anından önceki damgalı değerler) hâlâ geçerli kullanılabilir
                    if o is None:
                        return None
            t = pd.Timestamp(t)
            t = t.tz_localize("UTC") if t.tzinfo is None else t.tz_convert("UTC")
            kapanmis = [(z, v) for z, v in o[1] if z + SAAT <= t]       # lookahead yok: damga + 1 saat karar anını geçmemeli
            if not kapanmis or t - (kapanmis[-1][0] + SAAT) > BAYAT:
                return None
            z, v = kapanmis[-1]
            onceki = dict(kapanmis).get(z - pd.Timedelta(hours=24))
            deg = (v / onceki - 1.0) if onceki else None
            return v, deg
        except Exception:  # noqa: BLE001
            log.exception("açık pozisyon etiketi hesaplanamadı")
            return None
