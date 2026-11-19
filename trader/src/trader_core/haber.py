"""Haber / duygu etiketi: YALNIZ KAYIT, islem etkisi yok (belirtim: docs/haber-etiketi-spec.md).

Kaynak: kullanicinin kendi CT projesi `copytrade/canli/haber.py` (salt okunur kopya; calistirilmadi/kurulmadi) ve
`docs/VERI_SOZLESMESI.md` "Haber / duygu etiketi" bolumu; sozlesme AYNI (alan adlari, 24 saat penceresi, 26 saat duygu
bayatligi, kaba anahtar kelime tonu). Degisiklikler: ag cagrisi `requests` yerine stdlib `urllib` (yeni bagimlilik yok); kaynak
adresleri yapilandirmadan sabite alindi; onbellek dosyasi (`var/durum/haber_v1.json`) ve motor tarafi okuyucusu eklendi.
THIRD_PARTY_NOTICES.md'de belirtilmistir.

Kaynaklar (ucretsiz, anahtarsiz):
- Piyasa duygusu: alternative.me Crypto Fear & Greed Index (`/fng/?limit=1`) -> `{deger 0-100, sinif}`.
- Haber: herkese acik RSS (CoinDesk, Cointelegraph); stdlib `xml.etree`. Son 24 saatte coini anan baslik sayisi.

UYARI: ton etiketi KABA bir anahtar kelime sayimidir (Ingilizce baslik, baglam/olumsuzlama anlasilmaz). Yalniz bilgi amaclidir;
karar yoluna girmez. Her hata (ag, zaman asimi, bozuk XML/JSON) sessizce yutulur: son onbellek korunur; islevler istisna firlatmaz.
Zaman damgalari UTC milisaniyedir.
"""
from __future__ import annotations

import json
import os
import re
import time
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from pathlib import Path
from typing import Any, Callable

SEMA = "ml.haber.v1"
DUYGU_URL = "https://api.alternative.me/fng/?limit=1"
RSS_URLLERI = ("https://www.coindesk.com/arc/outboundfeeds/rss/", "https://cointelegraph.com/rss")

ZAMAN_ASIMI_SN = 5
TOPLAM_BUTCE_SN = 12                      # bir okumadaki tum ag cagrilari icin ust sinir; asilirsa kalan kaynaklar atlanir
MAX_BAYT = 1_000_000
PENCERE_MS = 24 * 3600 * 1000
SAKLA_MS = 25 * 3600 * 1000
EN_FAZLA_BASLIK = 150
DUYGU_BAYAT_MS = 26 * 3600 * 1000         # endeks gunlaktir; bundan eski okuma kayda yazilmaz
HABER_BAYAT_MS = 6 * 3600 * 1000          # saatlik toplayici; 6 saatten eski haber onbellegi null sayilir
GELECEK_TOLERANS_MS = 3600_000            # ileri tarihli baslik/onbellek (saat kaymasi ya da geri test): yazilmaz

POZITIF = ("surge", "rally", "soar", "gain", "jump", "record", "approv", "bullish", "adopt", "rise", "rebound", "breakout", "inflow")
NEGATIF = ("crash", "plunge", "hack", "exploit", "drop", "fall", "ban", "lawsuit", "bearish", "sell-off", "selloff", "liquidat", "fraud", "outflow", "slump", "sue")

# Yaygin isimler (sembol disinda); sembol buyuk harfle tam kelime eslesir.
ISIMLER = {"BTC": ("bitcoin",), "ETH": ("ethereum", "ether"), "SOL": ("solana",)}

Getir = Callable[[str], Any]


def varsayilan_yol() -> Path:
    """Onbellek dosyasi: `TRADER_HABER` ortam degiskeni ya da `<kok>/var/durum/haber_v1.json`."""
    return Path(os.environ.get("TRADER_HABER") or (Path(__file__).resolve().parents[2] / "var" / "durum" / "haber_v1.json"))


def baz_varlik(cift: str) -> str:
    """`BTC/USDT` -> `BTC` (ayrac yoksa metnin kendisi)."""
    return str(cift).split("/", 1)[0].strip()


# ----------------------------------------------------------------- ag (yalniz https, okuma)
def _indir(url: str, kabul: str) -> bytes:
    import urllib.request

    if not url.startswith("https://"):
        raise ValueError("adres https degil")
    req = urllib.request.Request(url, headers={"User-Agent": "trader-haber/1", "Accept": kabul})
    with urllib.request.urlopen(req, timeout=ZAMAN_ASIMI_SN) as r:    # noqa: S310 (adres https; yukarida denetlendi)
        if r.status != 200:
            raise ValueError(f"http {r.status}")
        veri = r.read(MAX_BAYT + 1)
    if len(veri) > MAX_BAYT:
        raise ValueError("yanit 1 MB sinirini asti")
    return veri


def _getir_json(url: str) -> Any:
    return json.loads(_indir(url, "application/json").decode("utf-8"))


def _getir_metin(url: str) -> Any:
    return _indir(url, "application/rss+xml, application/xml, text/xml")


# ----------------------------------------------------------------- saf cozuculer
def duygu_coz(veri: Any) -> dict | None:
    """alternative.me yaniti -> `{"deger": int 0-100, "sinif": str}` ya da None."""
    try:
        k = veri["data"][0]
        d = int(float(k["value"]))
        s = str(k["value_classification"]).strip()
        return {"deger": d, "sinif": s} if 0 <= d <= 100 and s else None
    except Exception:  # noqa: BLE001
        return None


def ton(baslik: str) -> str:
    """KABA ton: pozitif/negatif anahtar kelime sayisi farkinin isareti (esitse 'notr')."""
    b = baslik.lower()
    skor = sum(1 for k in POZITIF if k in b) - sum(1 for k in NEGATIF if k in b)
    return "pozitif" if skor > 0 else "negatif" if skor < 0 else "notr"


def rss_coz(icerik: Any, simdi_ms: int) -> list[dict]:
    """RSS -> `[{"t": ms, "b": baslik(<=120), "ton": ...}]`; tarihsiz/25 saatten eski/ileri tarihli ogeler atilir. Bozuk XML -> `[]`.
    DTD/ENTITY iceren belge reddedilir (genisleme saldirisi)."""
    try:
        ham = icerik if isinstance(icerik, (bytes, bytearray)) else str(icerik).encode("utf-8")
        if b"<!DOCTYPE" in ham.upper() or b"<!ENTITY" in ham.upper():
            return []
        kok = ET.fromstring(ham)
        cikti = []
        for oge in kok.iter("item"):
            baslik = (oge.findtext("title") or "").strip()
            tarih = (oge.findtext("pubDate") or "").strip()
            if not baslik or not tarih:
                continue
            try:
                t = int(parsedate_to_datetime(tarih).timestamp() * 1000)
            except (TypeError, ValueError):
                continue
            if simdi_ms - t > SAKLA_MS or t > simdi_ms + GELECEK_TOLERANS_MS:
                continue
            cikti.append({"t": t, "b": baslik[:120], "ton": ton(baslik)})
        return cikti
    except Exception:  # noqa: BLE001
        return []


def _desen(coin: str) -> re.Pattern | None:
    sym = coin[1:] if len(coin) > 2 and coin[0] == "k" and coin[1].isupper() else coin      # HL "kPEPE" oneki
    if len(sym) < 2 or not sym.isalnum():
        return None
    return re.compile(r"(?<![A-Za-z0-9])" + re.escape(sym) + r"(?![A-Za-z0-9])")


def eslesir(baslik: str, coin: str) -> bool:
    """Coin sembolu buyuk harfle TAM KELIME (SOL; 'solid' degil) ya da bilinen isim (bitcoin, ethereum, solana)."""
    d = _desen(coin)
    if d is not None and d.search(baslik):
        return True
    bl = baslik.lower()
    return any(re.search(r"(?<![a-z0-9])" + n + r"(?![a-z0-9])", bl) for n in ISIMLER.get(coin, ()))


def coin_haber(anlik: dict, coin: str, simdi_ms: int) -> dict | None:
    """`{coin: {"adet_24s": n, "ton": çoğunluk|None}}`; onbellek yok/bayatsa None."""
    try:
        basliklar = (anlik or {}).get("haberler")
        hms = (anlik or {}).get("haber_ms")
        if basliklar is None or not hms:
            return None
        if simdi_ms - int(hms) > HABER_BAYAT_MS or int(hms) - simdi_ms > GELECEK_TOLERANS_MS:
            return None
        es = [h for h in basliklar if -GELECEK_TOLERANS_MS <= simdi_ms - h["t"] <= PENCERE_MS and eslesir(h["b"], coin)]
        sayac = {"pozitif": 0, "negatif": 0, "notr": 0}
        for h in es:
            sayac[h["ton"]] += 1
        t = None
        if es:
            t = "pozitif" if sayac["pozitif"] > sayac["negatif"] else "negatif" if sayac["negatif"] > sayac["pozitif"] else "notr"
        return {coin: {"adet_24s": len(es), "ton": t}}
    except Exception:  # noqa: BLE001
        return None


def duygu_ozet(anlik: dict, simdi_ms: int) -> dict | None:
    """Onbellekteki duygu `{deger, sinif}`; yok, bayat ya da ileri tarihliyse None."""
    try:
        d = (anlik or {}).get("duygu")
        if not d:
            return None
        yas = simdi_ms - int(d["ms"])
        if yas > DUYGU_BAYAT_MS or yas < -GELECEK_TOLERANS_MS:
            return None
        deger = d["deger"]
        if isinstance(deger, bool) or not isinstance(deger, int) or not 0 <= deger <= 100:
            return None
        return {"deger": deger, "sinif": str(d["sinif"])}
    except Exception:  # noqa: BLE001
        return None


def emir_alanlari(anlik: dict, coin: str, simdi_ms: int) -> dict:
    """Kayda eklenecek alanlar (`duygu`, `haber`)."""
    return {"duygu": duygu_ozet(anlik, simdi_ms), "haber": coin_haber(anlik, coin, simdi_ms)}


# ----------------------------------------------------------------- toplayici
def guncelle(anlik: dict, simdi_ms: int, getir_json: Getir | None = None, getir_metin: Getir | None = None,
             duygu_url: str = DUYGU_URL, rss_urlleri: tuple[str, ...] | list[str] = RSS_URLLERI) -> dict:
    """Kaynaklari okur; yeni `anlik` doner. Hata olan kaynakta eski onbellek korunur. Istisna firlatmaz."""
    anlik = dict(anlik or {})
    try:
        gj, gm = getir_json or _getir_json, getir_metin or _getir_metin
        bas = time.monotonic()
        if duygu_url:
            try:
                d = duygu_coz(gj(duygu_url))
            except Exception:  # noqa: BLE001
                d = None
            if d:
                anlik["duygu"] = {**d, "ms": simdi_ms}
        gelen: list[dict] = []
        tamam = False
        for u in rss_urlleri:
            if time.monotonic() - bas > TOPLAM_BUTCE_SN:
                break
            try:
                ham = gm(u)
            except Exception:  # noqa: BLE001
                continue
            oge = rss_coz(ham, simdi_ms)
            if oge:
                gelen += oge
                tamam = True
        if tamam:
            birlesik = {h["b"]: h for h in (anlik.get("haberler") or []) if isinstance(h, dict) and simdi_ms - h["t"] <= SAKLA_MS}
            birlesik.update({h["b"]: h for h in gelen})
            anlik["haberler"] = sorted(birlesik.values(), key=lambda h: -h["t"])[:EN_FAZLA_BASLIK]
            anlik["haber_ms"] = simdi_ms
    except Exception:  # noqa: BLE001
        pass
    return anlik


# ----------------------------------------------------------------- onbellek dosyasi (`var/durum/haber_v1.json`)
def _iso(ms: int) -> str:
    return datetime.fromtimestamp(ms / 1000, tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def belge_yap(anlik: dict, simdi_ms: int) -> dict:
    """Onbellek belgesi: `{"sema","uretim","duygu":{deger,sinif,ms}|null,"basliklar":[...],"haber_ms"}`."""
    return {"sema": SEMA, "uretim": _iso(simdi_ms), "duygu": anlik.get("duygu") or None,
            "basliklar": list(anlik.get("haberler") or []), "haber_ms": anlik.get("haber_ms")}


def belge_coz(doc: Any) -> dict | None:
    """Belge -> `anlik` (`duygu`, `haberler`, `haber_ms`); sema/sekil gecersizse None. Istisna firlatmaz."""
    try:
        if not isinstance(doc, dict) or doc.get("sema") != SEMA:
            return None
        duygu = doc.get("duygu")
        if duygu is not None and not (isinstance(duygu, dict) and isinstance(duygu["ms"], int) and "deger" in duygu and "sinif" in duygu):
            return None
        bas = doc.get("basliklar")
        if not isinstance(bas, list):
            return None
        temiz = []
        for h in bas:
            if not (isinstance(h, dict) and isinstance(h["t"], int) and isinstance(h["b"], str) and h["ton"] in ("pozitif", "negatif", "notr")):
                return None
            temiz.append({"t": h["t"], "b": h["b"], "ton": h["ton"]})
        hms = doc.get("haber_ms")
        if hms is not None and not isinstance(hms, int):
            return None
        return {"duygu": duygu, "haberler": temiz, "haber_ms": hms}
    except Exception:  # noqa: BLE001
        return None


def dosya_oku(yol: str | os.PathLike) -> dict | None:
    """Dosya -> `anlik`; yok/bozuksa None."""
    try:
        return belge_coz(json.loads(Path(yol).read_text(encoding="utf-8")))
    except Exception:  # noqa: BLE001
        return None


_ONBELLEK: dict = {"yol": None, "mtime": None, "anlik": None}      # dosya yalniz mtime degisince yeniden okunur


def oku(yol: str | os.PathLike | None = None) -> dict | None:
    """Motorun okuyucusu: salt okunur, mtime onbellekli; yok/bozuksa None. Istisna firlatmaz."""
    try:
        p = Path(yol) if yol is not None else varsayilan_yol()
        mt = p.stat().st_mtime_ns
        if _ONBELLEK["yol"] != str(p) or _ONBELLEK["mtime"] != mt:
            _ONBELLEK.update(yol=str(p), mtime=mt, anlik=dosya_oku(p))
        return _ONBELLEK["anlik"]
    except Exception:  # noqa: BLE001
        _ONBELLEK.update(yol=None, mtime=None, anlik=None)
        return None


def etiket(cift: str, simdi_ms: int, yol: str | os.PathLike | None = None) -> dict | None:
    """Karar kaydina eklenecek `{"duygu": {...}|None, "haber": {coin: {...}}|None}`; onbellek yok/bozuk/bayatsa None
    (kayda hic alan eklenmez; okuyucu yok alani null sayar). Istisna firlatmaz."""
    try:
        anlik = oku(yol)
        if anlik is None:
            return None
        e = emir_alanlari(anlik, baz_varlik(cift), simdi_ms)
        return e if (e["duygu"] is not None or e["haber"] is not None) else None
    except Exception:  # noqa: BLE001
        return None


def duygu_siniflari_tr(sinif: str) -> str:
    """Kisa Turkce ad (gunluk ozet notu); bilinmeyen sinif aynen doner."""
    return {"extreme fear": "Aşırı korku", "fear": "Korku", "neutral": "Nötr", "greed": "Açgözlülük",
            "extreme greed": "Aşırı açgözlülük"}.get(sinif.strip().lower(), sinif.strip())
