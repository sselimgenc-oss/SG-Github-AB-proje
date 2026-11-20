"""Minimal imzalı Binance USDⓈ-M vadeli REST istemcisi (HMAC-SHA256).

GÜVENLİK: API anahtarı/gizli yalnız ortam değişkeninden okunur (bkz. canli_ayar). Bu modül gizliyi ASLA loga yazmaz; imzalı
sorgu dizgisi (signature=...) hiçbir log/hata metninde görünmez (`temizle`). Ağ hata metinleri (URL taşıyabilir) loglanmaz,
yalnız istisna türü adı loglanır.

YENİDEN DENEME POLİTİKASI: okuma/iptal/ayar istekleri yalnız ağ hatası, HTTP 5xx ve -1021 için (üstel geri çekilme) tekrar denenir.
EMİR VEREN POST'LAR (/fapi/v1/order, /fapi/v1/algoOrder) ağ hatası/zaman aşımı/5xx'te ASLA OTOMATİK TEKRAR EDİLMEZ: newClientOrderId yalnız
AÇIK emirler arasında benzersizdir, dolmuş bir piyasa emri aynı kimlikle yeniden gönderilirse ikinci kez dolar (çift pozisyon). Belirsiz sonuç
`belirsiz=True` BorsaHata olarak yükselir; çağıran (yürütücü) emri kimlikle SORGULAR ve yalnız borsa "böyle emir yok" derse yeniden gönderir.
Yalnız -1021 (reddedildi, işlenmedi) emir POST'unda da güvenle tekrar denenir. Emir reddi / diğer 4xx kodlarında tekrar yok.

KOŞULLU EMİRLER (STOP_MARKET / TAKE_PROFIT_MARKET): Binance 2025-12'den itibaren USDⓈ-M'de bunları "Algo Order" uçlarına taşıdı
(/fapi/v1/algoOrder). `kosullu_modu="algo"` (varsayılan) o uçları, "klasik" eski /fapi/v1/order ucunu kullanır. Uç/parametre adları
TESTNET'te doğrulanmalıdır (bu geliştirme ortamından Binance'e erişim yoktur; testler sahte HTTP ile yazıldı).
"""
from __future__ import annotations

import hashlib
import hmac
import json
import logging
import math
import os
import re
import time
from decimal import Decimal, InvalidOperation
from typing import Callable, Optional
from urllib.parse import urlencode

log = logging.getLogger("canli.borsa")

TESTNET = "https://testnet.binancefuture.com"
CANLI = "https://fapi.binance.com"
TABANLAR = {"testnet": TESTNET, "canli": CANLI}
AGIRLIK_ESIGI = 1800                 # dakikalık ağırlık 2400; %75'te bekle
ISTEK_ZAMAN_ASIMI = 20
IDEMPOTENT_KODLAR = {-4046, -4059}   # "değiştirmeye gerek yok" (marj tipi / pozisyon modu zaten istenen)
YOK_KODLARI = {-2013, -2011}         # emir yok / iptal edilecek emir yok
BELIRSIZ_KODLARI = {-1006, -1007, -1008}   # "durum bilinmiyor" (zaman aşımı / beklenmeyen yanıt / aşırı yük); HTTP 408 de öyle
SAYFA = 1000


# ---- 418/429 yasağı: BinanceFutures ve paper_veri.FapiIstemci arasında AYNI HOST için paylaşılır (aynı IP + aynı host). Host bazlı:
# fapi.binance.com / testnet.binancefuture.com / api.binance.com birbirini bloklamaz. Süreç içi; dosya isteğe bağlı.
VARSAYILAN_HOST = "fapi.binance.com"
_YASAK = {"bitis": {}, "dosya": None}      # bitis: {host: epoch sn}


def host_al(taban: Optional[str]) -> str:
    from urllib.parse import urlparse
    return (urlparse(taban or "").hostname or VARSAYILAN_HOST).lower()


def yasak_yukle(dosya) -> float:
    """Yasak bitişlerini (host -> epoch sn) dosyadan okur (yoksa/bozuksa boş); dosya yolunu hatırlar. Başlangıçta çağrılır.
    Dönüş: varsayılan host'un bitişi."""
    _YASAK["dosya"] = str(dosya) if dosya else None
    if dosya:
        try:
            with open(dosya, encoding="utf-8") as f:
                j = json.load(f)
            for h, v in dict(j["hostlar"]).items():
                _YASAK["bitis"][str(h)] = max(_YASAK["bitis"].get(str(h), 0.0), float(v))
        except (OSError, ValueError, KeyError, TypeError):
            pass
    return yasak_oku()


def yasak_ayarla(bitis: float, dosya=None, host: Optional[str] = None) -> None:
    """Host'un ortak yasak bitişini uzatır (kısaltmaz) ve varsa dosyaya yazar."""
    host = host or VARSAYILAN_HOST
    _YASAK["bitis"][host] = max(_YASAK["bitis"].get(host, 0.0), float(bitis))
    dosya = dosya or _YASAK["dosya"]
    if dosya:
        try:
            tmp = str(dosya) + ".tmp"
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump({"hostlar": _YASAK["bitis"]}, f)
            os.replace(tmp, dosya)
        except OSError as e:
            log.warning("yasak dosyası yazılamadı: %s", type(e).__name__)


def yasak_oku(host: Optional[str] = None) -> float:
    return _YASAK["bitis"].get(host or VARSAYILAN_HOST, 0.0)


def yasak_sifirla() -> None:       # testler için
    _YASAK["bitis"], _YASAK["dosya"] = {}, None


def _dec(v) -> Decimal:
    """Sonlu Decimal ya da BorsaHata (NaN/inf/bozuk metin sızmaz)."""
    try:
        d = Decimal(str(v))
    except (InvalidOperation, ValueError, TypeError):
        raise BorsaHata(f"geçersiz sayı alanı: {type(v).__name__}") from None
    if not d.is_finite():
        raise BorsaHata("sonlu olmayan sayı alanı")
    return d


def _retry_after(r, varsayilan: int) -> int:
    try:
        v = int(float(r.headers.get("Retry-After", varsayilan)))
    except (TypeError, ValueError, AttributeError):
        v = varsayilan
    return v if v > 0 else varsayilan

_IMZA = re.compile(r"signature=[0-9a-fA-F]+", re.I)


def temizle(metin) -> str:
    """Log/hata metninden imzayı (ve varsa anahtar başlığını) siler."""
    return _IMZA.sub("signature=***", str(metin))


def imzala(sorgu: str, gizli: str) -> str:
    """HMAC-SHA256(gizli, sorgu) onaltılık. Binance dokümantasyon örneğiyle test edilir."""
    return hmac.new(gizli.encode(), sorgu.encode(), hashlib.sha256).hexdigest()


def duz(x) -> str:
    """Sayıyı bilimsel gösterimsiz metne çevirir (Decimal / float / int)."""
    if isinstance(x, Decimal):
        return format(x.normalize(), "f") if x != 0 else "0"
    if isinstance(x, float):
        return format(Decimal(repr(x)).normalize(), "f")
    return str(x)


class BorsaHata(Exception):
    """Borsa isteği başarısız. `kod`: Binance hata kodu (varsa), `http`: HTTP durumu, `belirsiz`: emir borsada oluşmuş olabilir."""

    def __init__(self, mesaj: str, kod: Optional[int] = None, http: Optional[int] = None, belirsiz: bool = False):
        super().__init__(temizle(mesaj))
        self.kod, self.http, self.belirsiz = kod, http, belirsiz


class EmirReddi(BorsaHata):
    """Borsa isteği açıkça reddetti (tekrar YOK)."""


class BorsaYasagi(BorsaHata):
    """429/418: rate limit ya da IP yasağı. `suruyor`: istek hiç gönderilmedi, süren yasak (bitis: epoch sn)."""
    suruyor = False
    bitis = 0.0


class BinanceFutures:
    def __init__(self, ortam: str = "testnet", anahtar: str = "", gizli: str = "", oturum=None, uyku: Callable = time.sleep,
                 saat: Callable = time.time, recv_window: int = 5000, max_deneme: int = 4, kosullu_modu: str = "algo",
                 taban: Optional[str] = None, yasak_dosyasi=None):
        if ortam not in TABANLAR and taban is None:
            raise ValueError(f"ortam testnet|canli olmalı: {ortam!r}")
        if kosullu_modu not in ("algo", "klasik"):
            raise ValueError("kosullu_modu algo|klasik")
        self.ortam = ortam
        self.taban = taban or TABANLAR[ortam]
        self._anahtar, self._gizli = anahtar, gizli
        if oturum is None:
            import requests
            oturum = requests.Session()
        self.oturum, self.uyku, self.saat = oturum, uyku, saat
        self.recv_window, self.max_deneme, self.kosullu_modu = recv_window, max_deneme, kosullu_modu
        self.zaman_farki_ms: Optional[int] = None
        self.kullanilan_agirlik, self.agirlik_zamani = 0, 0.0
        self.yasak_bitis = 0.0
        self.host = host_al(self.taban)
        self._paylas = saat is time.time           # sahte saatli (test) örnekler paylaşılan yasağa girmez
        self.yasak_dosyasi = yasak_dosyasi
        if self._paylas and yasak_dosyasi:
            yasak_yukle(yasak_dosyasi)

    def _yasak_koy(self, bitis: float) -> None:
        self.yasak_bitis = max(self.yasak_bitis, bitis)
        if self._paylas:
            yasak_ayarla(bitis, self.yasak_dosyasi, self.host)

    def __repr__(self) -> str:                      # anahtar/gizli asla gösterilmez
        return f"BinanceFutures(ortam={self.ortam!r}, taban={self.taban!r})"

    # ------------------------------------------------------------------ çekirdek
    def zaman_esitle(self) -> int:
        r = self._ham("GET", "/fapi/v1/time", {}, imzali=False)
        self.zaman_farki_ms = int(r["serverTime"]) - int(self.saat() * 1000)
        return self.zaman_farki_ms

    def _agirlik_bekle(self) -> None:
        simdi = self.saat()
        bitis = max(self.yasak_bitis, yasak_oku(self.host) if self._paylas else 0.0)
        if simdi < bitis:
            e = BorsaYasagi(f"IP yasağı/rate limit sürüyor ({bitis - simdi:.0f} sn)", http=418)
            e.bitis, e.suruyor = bitis, True
            raise e
        if simdi - self.agirlik_zamani >= 60:
            self.kullanilan_agirlik = 0
        if self.kullanilan_agirlik >= AGIRLIK_ESIGI:
            bekle = max(1.0, 60 - (simdi - self.agirlik_zamani))
            log.warning("rate limit: ağırlık %d >= %d; %.0f sn bekleniyor", self.kullanilan_agirlik, AGIRLIK_ESIGI, bekle)
            self.uyku(bekle)
            self.kullanilan_agirlik = 0

    def _ham(self, yontem: str, yol: str, params: dict, imzali: bool = True, tekrar_guvenli: bool = True):
        """tekrar_guvenli=False (emir veren POST): ağ hatası/5xx tek denemede `belirsiz` hata olarak yükselir."""
        son = None
        for deneme in range(1, self.max_deneme + 1):
            self._agirlik_bekle()
            p = dict(params)
            basliklar = {}
            if imzali:
                if not self._anahtar or not self._gizli:
                    raise BorsaHata("API anahtarı/gizli tanımlı değil (ortam değişkeni)")
                if self.zaman_farki_ms is None:
                    self.zaman_esitle()
                p["recvWindow"] = self.recv_window
                p["timestamp"] = int(self.saat() * 1000) + (self.zaman_farki_ms or 0)
                sorgu = urlencode(p)
                sorgu += "&signature=" + imzala(sorgu, self._gizli)
                basliklar["X-MBX-APIKEY"] = self._anahtar
            else:
                sorgu = urlencode(p)
            url = self.taban + yol + ("?" + sorgu if sorgu else "")
            try:
                r = self.oturum.request(yontem, url, headers=basliklar, timeout=ISTEK_ZAMAN_ASIMI)
            except Exception as e:  # noqa: BLE001  (ağ hatası: yalnız tür adı loglanır — metin URL/imza taşıyabilir; tekrar denenir)
                son = BorsaHata(f"{yontem} {yol} ağ hatası: {type(e).__name__}", belirsiz=True)
                if not tekrar_guvenli:
                    raise son from None
                bekle = min(2 ** deneme, 30)
                log.warning("%s %s ağ hatası %s (%d/%d); %d sn sonra tekrar", yontem, yol, type(e).__name__, deneme, self.max_deneme, bekle)
                self.uyku(bekle)
                continue
            w = r.headers.get("X-MBX-USED-WEIGHT-1M") if getattr(r, "headers", None) else None
            if w is not None:
                self.kullanilan_agirlik, self.agirlik_zamani = int(w), self.saat()
            if r.status_code == 200:
                try:
                    return r.json()
                except Exception:  # noqa: BLE001  (200 ama gövde JSON değil: emir oluşmuş olabilir)
                    raise BorsaHata(f"{yontem} {yol}: 200 yanıtı JSON değil", http=200, belirsiz=True) from None
            kod, mesaj = None, ""
            try:
                j = r.json()
                kod, mesaj = j.get("code"), str(j.get("msg", ""))[:200]
            except Exception:  # noqa: BLE001  (gövde JSON değil: durum kodu yeter)
                mesaj = ""
            if r.status_code in (429, 418):
                bekle = _retry_after(r, 60 if r.status_code == 429 else 300)
                self._yasak_koy(self.saat() + bekle)         # içeride UYUMAZ; çağıran sonraki turda tekrar dener
                raise BorsaYasagi(f"{r.status_code} {yol} rate limit/yasak; Retry-After={bekle} sn", kod, r.status_code,
                                  belirsiz=(kod in BELIRSIZ_KODLARI) or not tekrar_guvenli)
            if kod == -1021 and deneme < self.max_deneme:            # zaman damgası penceresi dışında: saati eşitle, tekrar dene
                log.warning("%s %s: -1021 zaman damgası; sunucu saatiyle eşitleniyor", yontem, yol)
                self.zaman_esitle()
                continue
            if 500 <= r.status_code < 600 or r.status_code == 408 or kod in BELIRSIZ_KODLARI:
                son = BorsaHata(f"{yontem} {yol} durum bilinmiyor HTTP {r.status_code} kod={kod}", kod, r.status_code, belirsiz=True)
                if not tekrar_guvenli:
                    raise son
                bekle = min(2 ** deneme, 30)
                log.warning("%s %s HTTP %d (%d/%d); %d sn sonra tekrar", yontem, yol, r.status_code, deneme, self.max_deneme, bekle)
                self.uyku(bekle)
                continue
            raise EmirReddi(f"{yontem} {yol} reddedildi: HTTP {r.status_code} kod={kod} {mesaj}", kod, r.status_code)
        raise BorsaHata(f"{yontem} {yol}: {self.max_deneme} denemede başarısız: {son}", belirsiz=True)

    def _get(self, yol, params=None, imzali=True):
        return self._ham("GET", yol, params or {}, imzali)

    # ------------------------------------------------------------------ herkese açık
    def sunucu_zamani(self) -> int:
        return int(self._get("/fapi/v1/time", imzali=False)["serverTime"])

    def exchange_info(self) -> dict:
        return self._get("/fapi/v1/exchangeInfo", imzali=False)

    def mark_fiyat(self, sembol: str) -> Decimal:
        r = self._get("/fapi/v1/premiumIndex", {"symbol": sembol}, imzali=False)
        try:
            d = _dec(r["markPrice"])
        except (KeyError, TypeError):
            raise BorsaHata("markPrice alanı yok/bozuk") from None
        if d <= 0:
            raise BorsaHata("markPrice <= 0")
        return d

    # ------------------------------------------------------------------ hesap
    def bakiye(self) -> dict:
        """-> {'ozsermaye': marj bakiyesi (cüzdan + gerçekleşmemiş K/Z), 'kullanilabilir', 'cuzdan'} (USDT, Decimal)."""
        a = self._get("/fapi/v2/account")
        try:
            return {"ozsermaye": _dec(a["totalMarginBalance"]), "kullanilabilir": _dec(a["availableBalance"]),
                    "cuzdan": _dec(a["totalWalletBalance"])}
        except (KeyError, TypeError):
            raise BorsaHata("hesap yanıtında alan eksik/bozuk") from None

    def pozisyonlar(self) -> list:
        """Açık pozisyonlar: [{'sembol', 'miktar' (işaretli), 'giris', 'mark', 'marj_tipi'}]."""
        out = []
        try:
            for x in self._get("/fapi/v2/positionRisk"):
                q = _dec(x["positionAmt"])
                if q != 0:
                    out.append({"sembol": x["symbol"], "miktar": q, "giris": _dec(x["entryPrice"]),
                                "mark": _dec(x["markPrice"]), "marj_tipi": str(x.get("marginType", "")).upper()})
        except (KeyError, TypeError, AttributeError):
            raise BorsaHata("positionRisk yanıtında alan eksik/bozuk") from None
        return out

    @staticmethod
    def _norm(x: dict, kosullu: bool) -> dict:
        """Eksik/bozuk alan -> BorsaHata(belirsiz=True) (emir borsada oluşmuş olabilir); ham KeyError/ValueError sızmaz."""
        try:
            return BinanceFutures._norm_ic(x, kosullu)
        except BorsaHata as e:
            raise BorsaHata(str(e), belirsiz=True) from None
        except (KeyError, ValueError, TypeError, AttributeError, ArithmeticError):
            raise BorsaHata("emir yanıtı alanı eksik/bozuk", belirsiz=True) from None

    @staticmethod
    def _norm_ic(x: dict, kosullu: bool) -> dict:
        if kosullu and "algoId" in x:
            return {"id": str(x["algoId"]), "client_id": x.get("clientAlgoId", ""), "sembol": x["symbol"], "tur": x.get("orderType", x.get("type", "")),
                    "yon": x["side"], "miktar": _dec(x.get("quantity", "0")), "tetik": _dec(x.get("triggerPrice", "0")),
                    "reduce_only": bool(x.get("reduceOnly", False)) or bool(x.get("closePosition", False)),
                    "durum": x.get("algoStatus", x.get("status", "")), "kosullu": True}
        return {"id": str(x["orderId"]), "client_id": x.get("clientOrderId", ""), "sembol": x["symbol"], "tur": x.get("origType", x.get("type", "")),
                "yon": x["side"], "miktar": _dec(x.get("origQty", "0")), "tetik": _dec(x.get("stopPrice", "0")),
                "reduce_only": bool(x.get("reduceOnly", False)) or bool(x.get("closePosition", False)),
                "durum": x.get("status", ""), "kosullu": kosullu, "dolan": _dec(x.get("executedQty", "0")),
                "ort_fiyat": _dec(x.get("avgPrice", "0"))}

    def emirler(self, sembol: Optional[str] = None) -> list:
        """Açık emirler (normal + koşullu), normalize."""
        p = {"symbol": sembol} if sembol else {}
        out = [self._norm(x, False) for x in self._get("/fapi/v1/openOrders", p)]
        if self.kosullu_modu == "algo":
            out += [self._norm(x, True) for x in self._get("/fapi/v1/openAlgoOrders", p)]
        return out

    # ------------------------------------------------------------------ hazırlık
    def hazirla(self, sembol: str, kaldirac: int) -> None:
        """Tek yönlü (one-way) mod, ISOLATED marj, kaldıraç. 'zaten öyle' hataları (-4046/-4059) sorun değildir."""
        for yol, p in (("/fapi/v1/positionSide/dual", {"dualSidePosition": "false"}),
                       ("/fapi/v1/marginType", {"symbol": sembol, "marginType": "ISOLATED"})):
            try:
                self._ham("POST", yol, p)
            except EmirReddi as e:
                if e.kod not in IDEMPOTENT_KODLAR:
                    raise
        self._ham("POST", "/fapi/v1/leverage", {"symbol": sembol, "leverage": int(kaldirac)})

    # ------------------------------------------------------------------ emirler
    def piyasa(self, sembol: str, yon: str, miktar: Decimal, client_id: str, reduce_only: bool = False) -> dict:
        p = {"symbol": sembol, "side": yon, "type": "MARKET", "quantity": duz(miktar), "newClientOrderId": client_id,
             "newOrderRespType": "RESULT"}
        if reduce_only:
            p["reduceOnly"] = "true"
        return self._norm(self._ham("POST", "/fapi/v1/order", p, tekrar_guvenli=False), False)

    def kosullu(self, sembol: str, tur: str, yon: str, miktar: Decimal, tetik: Decimal, client_id: str,
                working_type: str = "MARK_PRICE") -> dict:
        """STOP_MARKET / TAKE_PROFIT_MARKET, her zaman reduceOnly. `yon`: kapatan taraf (long pozisyon için SELL)."""
        if tur not in ("STOP_MARKET", "TAKE_PROFIT_MARKET"):
            raise ValueError(tur)
        if working_type not in ("MARK_PRICE", "CONTRACT_PRICE"):
            raise ValueError(working_type)
        if self.kosullu_modu == "algo":
            p = {"algoType": "CONDITIONAL", "symbol": sembol, "side": yon, "type": tur, "quantity": duz(miktar),
                 "triggerPrice": duz(tetik), "workingType": working_type, "reduceOnly": "true", "clientAlgoId": client_id}
            return self._norm(self._ham("POST", "/fapi/v1/algoOrder", p, tekrar_guvenli=False), True)
        p = {"symbol": sembol, "side": yon, "type": tur, "quantity": duz(miktar), "stopPrice": duz(tetik),
             "workingType": working_type, "reduceOnly": "true", "newClientOrderId": client_id}
        return self._norm(self._ham("POST", "/fapi/v1/order", p, tekrar_guvenli=False), False)

    def sorgula(self, sembol: str, client_id: str) -> Optional[dict]:
        """clientOrderId ile emir; yoksa None. Normal ve koşullu uçlara bakar."""
        try:
            return self._norm(self._get("/fapi/v1/order", {"symbol": sembol, "origClientOrderId": client_id}), False)
        except EmirReddi as e:
            if e.kod not in YOK_KODLARI:
                raise
        if self.kosullu_modu == "algo":
            try:
                return self._norm(self._get("/fapi/v1/algoOrder", {"clientAlgoId": client_id}), True)
            except EmirReddi as e:
                if e.kod not in YOK_KODLARI:
                    raise
        return None

    def iptal(self, sembol: str, client_id: str, kosullu: bool = True) -> None:
        try:
            if kosullu and self.kosullu_modu == "algo":
                self._ham("DELETE", "/fapi/v1/algoOrder", {"clientAlgoId": client_id})
            else:
                self._ham("DELETE", "/fapi/v1/order", {"symbol": sembol, "origClientOrderId": client_id})
        except EmirReddi as e:
            if e.kod not in YOK_KODLARI:
                raise

    def hepsini_iptal(self, sembol: str) -> None:
        self._ham("DELETE", "/fapi/v1/allOpenOrders", {"symbol": sembol})
        if self.kosullu_modu == "algo":
            self._ham("DELETE", "/fapi/v1/algoOpenOrders", {"symbol": sembol})

    # ------------------------------------------------------------------ SALT OKUMA: kayıt (islemler.jsonl) için dolum ve funding geçmişi
    def kullanici_islemleri(self, sembol: str, bas_ms: int, bit_ms: Optional[int] = None) -> list:
        """Hesabın DOLUM kayıtları (userTrades), zamana göre sıralı, normalize: [{id, emir_id, yon, fiyat, miktar, komisyon, komisyon_varlik,
        gercek_pnl, zaman_ms}]. Binance en çok 7 günlük pencere verir: pencereler halinde gezilir, id ile tekrarlar elenir. Emir vermez."""
        bit_ms = bit_ms or int(self.saat() * 1000) + (self.zaman_farki_ms or 0)
        gorulen, out, bas = set(), [], int(bas_ms)
        yedi_gun = 7 * 24 * 3600 * 1000 - 1
        try:
            while bas <= bit_ms:
                son = min(bas + yedi_gun, bit_ms)
                for x in self._sayfala("/fapi/v1/userTrades", {"symbol": sembol}, bas, son, lambda r: r["id"], lambda r: int(r["time"])):
                    if x["id"] not in gorulen:
                        gorulen.add(x["id"])
                        out.append({"id": int(x["id"]), "emir_id": str(x.get("orderId", "")), "yon": x["side"], "fiyat": _dec(x["price"]),
                                    "miktar": _dec(x["qty"]), "komisyon": _dec(x.get("commission", "0")),
                                    "komisyon_varlik": str(x.get("commissionAsset", "")), "gercek_pnl": _dec(x.get("realizedPnl", "0")),
                                    "zaman_ms": int(x["time"])})
                bas = son + 1
        except (KeyError, ValueError, TypeError, AttributeError):
            raise BorsaHata("userTrades yanıtında alan eksik/bozuk") from None
        return sorted(out, key=lambda f: (f["zaman_ms"], f["id"]))

    def funding_gecmisi(self, sembol: str, bas_ms: int, bit_ms: Optional[int] = None) -> Decimal:
        """Aralıktaki FUNDING_FEE toplamı (işaretli: negatif = ödenen). Emir vermez."""
        bit_ms = bit_ms or int(self.saat() * 1000) + (self.zaman_farki_ms or 0)
        try:
            r = self._sayfala("/fapi/v1/income", {"symbol": sembol, "incomeType": "FUNDING_FEE"}, int(bas_ms), int(bit_ms),
                              lambda x: x.get("tranId", (x["time"], x["income"])), lambda x: int(x["time"]))
            return sum((_dec(x["income"]) for x in r), Decimal(0))
        except (KeyError, ValueError, TypeError, AttributeError):
            raise BorsaHata("income yanıtında alan eksik/bozuk") from None

    def _sayfala(self, yol: str, p: dict, bas: int, bit: int, anahtar, zaman) -> list:
        """limit=1000'e dolan sonuçlarda zaman imlecini ilerleterek TÜM satırları çeker (anahtar ile tekrarlar elenir).
        İlerleme yoksa (aynı ms'de >1000 satır) sessiz kesmek yerine BorsaHata."""
        gorulen, out = set(), []
        while True:
            r = self._get(yol, {**p, "startTime": bas, "endTime": bit, "limit": SAYFA})
            for x in r:
                k = anahtar(x)
                if k not in gorulen:
                    gorulen.add(k)
                    out.append(x)
            if len(r) < SAYFA:
                return out
            son_t = max(zaman(x) for x in r)
            if son_t <= bas:
                raise BorsaHata(f"{yol}: aynı ms'de >={SAYFA} satır; sayfalanamadı")
            bas = son_t
