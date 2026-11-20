"""Canlı yürütme yapılandırması. Anahtarlar DOSYADA YOKTUR: yalnız ortam değişkeni ADLARI yazılır; değerler sunucuda
/etc/1l3a-canli.env (chmod 600) içinden systemd ile ortama yüklenir.

Örnek: stratejiler/canli_ayar.ornek.json. Kurallar:
  - mod: kuru | testnet | canli (varsayılan testnet). `canli` için ayrıca ortamda CANLI_ONAY=evet şart; yoksa başlamaz.
  - Strateji başına `islem_risk` (işlem başı stopta kayıp / kasa): YALNIZ {0.005, 0.01, 0.015} (Decimal tam eşleşme),
    alan yoksa 0.015; başka her değer (0.0150001, NaN, >0.015, sayı olmayan) reddedilir.
    Kaynak: DURUM.md 2026-11-14 kararı (canlı bölüşüm ve risk; kullanıcı onaylı), önceki kilit: sonuclar/canli/CANLI_PLAN_V2.md §3. Boyut = min(islem_risk, CANLI_LIMITLER %3); o %3 güvenlik tavanıdır, değişmez.
  - Strateji başına `kaldirac` (isteğe bağlı): YALNIZ int {3, 4, 5}; alan yoksa 3; başka her değer (2, 6, "5", 5.0, True, None) reddedilir.
    Nominal ve brüt tavan = K x kasa (marj tavanı %50, toplam stop riski %6, işlem başı %3 AYNEN); borsada ayarlanan kaldıraç yakın stopta K, uzak stopta 2.
    Kullanıcı kararı 2026-11-19. UYARI: 5x test edilmiş sınırın dışında (backtestler brüt 3x); 5x seçmeden önce tavanlı backtest + boşluk stres testi önerilir.
  - `kapanis_canli_onay` (isteğe bağlı, varsayılan boş liste): [{"id": str, "tarih": "YYYY-MM-DD", "onay": "evet"}]. kapanis_aday / kapanis_aday_ek
    etiketli strateji GERÇEK PARA (mod=canli) ile ancak burada kimliğiyle listeliyse başlar; testnet/kuru modlarda gerekmez. Bozuk liste reddedilir.
  - Bir Binance hesabı (API anahtar çifti) = bir strateji. Aynı anahtar adı iki stratejide kullanılamaz (strateji arası netleştirme yok).
"""
from __future__ import annotations

import datetime
import hashlib
import json
import os
from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path
from typing import Optional

MODLAR = ("kuru", "testnet", "canli")
ONAY_ENV, ONAY_DEGER = "CANLI_ONAY", "evet"
VARSAYILAN_YOL = Path(__file__).resolve().parents[3] / "stratejiler" / "canli_ayar.json"


# Kaynak: DURUM.md 2026-11-14 "CANLI BÖLÜŞÜM VE RİSK" (kullanıcı onaylı): strateji başı işlem riski {%0,5; %1; %1,5}.
# CANLI_PLAN_V2 §3'teki "%1,5 sabit" kilidi bu kararla {0,005; 0,01; 0,015} kümesine genişledi; artış takvimi yine yok.
IZINLI_ISLEM_RISK_KUMESI = (Decimal("0.005"), Decimal("0.01"), Decimal("0.015"))
IZINLI_ISLEM_RISK = Decimal("0.015")   # alan yoksa varsayılan (kümenin en büyüğü)
IZINLI_KALDIRACLAR = (3, 4, 5)         # kullanıcı kararı 2026-11-19; 5x test edilmiş sınırın (brüt 3x) dışındadır
VARSAYILAN_KALDIRAC = 3


class CanliAyarHatasi(ValueError):
    pass


class CanliOnayHatasi(CanliAyarHatasi):
    """`canli` modu CANLI_ONAY=evet olmadan istendi: başlatma reddedilir."""


@dataclass(frozen=True)
class StratejiAyar:
    id: str
    api_key_env: str
    api_secret_env: str
    tahsis_usd: Decimal
    islem_risk: Decimal = IZINLI_ISLEM_RISK   # işlem başı stopta kayıp / kasa (maliyet dahil); yalnız IZINLI_ISLEM_RISK
    kaldirac: int = VARSAYILAN_KALDIRAC       # strateji kaldıracı; yalnız IZINLI_KALDIRACLAR


@dataclass(frozen=True)
class CanliAyar:
    mod: str
    stratejiler: tuple
    working_type: str = "MARK_PRICE"
    giris_gecikme_max_sn: int = 900
    kosullu_modu: str = "algo"
    hedef_emri: bool = True
    kapanis_canli_onay: tuple = ()    # ((id, "YYYY-MM-DD"), ...): kapanış adayı stratejiler için kullanıcı onayı (yalnız mod=canli'de aranır)


def _islem_risk(sid: str, ham) -> Decimal:
    """Fail-closed: sayı değilse veya izinli kümede (0.005, 0.01, 0.015) değilse yapılandırma reddedilir (DURUM.md 2026-11-14)."""
    if isinstance(ham, bool) or not isinstance(ham, (int, float, str, Decimal)):
        raise CanliAyarHatasi(f"{sid}: islem_risk sayı olmalı: {ham!r}")
    try:
        r = Decimal(str(ham))
    except Exception:  # noqa: BLE001
        raise CanliAyarHatasi(f"{sid}: islem_risk sayı olmalı: {ham!r}") from None
    if not r.is_finite() or r not in IZINLI_ISLEM_RISK_KUMESI:
        izinli = ", ".join(str(v) for v in IZINLI_ISLEM_RISK_KUMESI)
        raise CanliAyarHatasi(f"{sid}: islem_risk yalnız {{{izinli}}} olabilir; verilen: {ham!r}. "
                              "İşlem başı risk bu kümenin dışına çıkarılamaz (DURUM.md 2026-11-14; sonuclar/canli/CANLI_PLAN_V2.md §3).")
    return r


def _kaldirac(sid: str, ham) -> int:
    """Fail-closed: yalnız int ve {3, 4, 5} içinde (bool, float, str, None reddedilir)."""
    if isinstance(ham, bool) or not isinstance(ham, int) or ham not in IZINLI_KALDIRACLAR:
        raise CanliAyarHatasi(f"{sid}: kaldirac yalnız {IZINLI_KALDIRACLAR} (tam sayı) olabilir; verilen: {ham!r}. "
                              "5x test edilmiş sınırın dışında; tavanlı backtest + boşluk stres testi önerilir (DURUM.md 2026-11-19).")
    return ham


def _kapanis_onay(ham) -> tuple:
    """Fail-closed: liste değilse, girdi {id, tarih, onay} dışında/eksikse, onay != "evet", tarih YYYY-MM-DD değilse veya id tekrarlıysa reddedilir."""
    if not isinstance(ham, list):
        raise CanliAyarHatasi(f"kapanis_canli_onay liste olmalı: {ham!r}")
    cikti, gorulen = [], set()
    for x in ham:
        if not isinstance(x, dict) or set(x) != {"id", "tarih", "onay"}:
            raise CanliAyarHatasi(f"kapanis_canli_onay girdisi tam olarak {{id, tarih, onay}} alanlarını içermeli: {x!r}")
        sid, tarih, onay = x["id"], x["tarih"], x["onay"]
        if not isinstance(sid, str) or not sid.strip():
            raise CanliAyarHatasi(f"kapanis_canli_onay: id boş olmayan metin olmalı: {sid!r}")
        if onay != "evet":
            raise CanliAyarHatasi(f"{sid}: kapanis_canli_onay.onay yalnız \"evet\" olabilir: {onay!r}")
        if not isinstance(tarih, str) or len(tarih) != 10:
            raise CanliAyarHatasi(f"{sid}: kapanis_canli_onay.tarih YYYY-MM-DD olmalı: {tarih!r}")
        try:
            datetime.date.fromisoformat(tarih)
        except ValueError:
            raise CanliAyarHatasi(f"{sid}: kapanis_canli_onay.tarih geçerli YYYY-MM-DD olmalı: {tarih!r}") from None
        if sid in gorulen:
            raise CanliAyarHatasi(f"{sid}: kapanis_canli_onay içinde tekrarlı id")
        gorulen.add(sid)
        cikti.append((sid, tarih))
    return tuple(cikti)


def yukle(yol: Optional[Path] = None, env: Optional[dict] = None) -> CanliAyar:
    env = os.environ if env is None else env
    yol = Path(yol or env.get("CANLI_AYAR") or VARSAYILAN_YOL)
    try:
        h = json.loads(yol.read_text(encoding="utf-8"))
    except FileNotFoundError:
        raise CanliAyarHatasi(f"yapılandırma yok: {yol}") from None
    return coz(h, env)


def coz(h: dict, env: dict) -> CanliAyar:
    mod = h.get("mod", "testnet")
    if mod not in MODLAR:
        raise CanliAyarHatasi(f"mod {MODLAR} içinden olmalı: {mod!r}")
    if mod == "canli" and env.get(ONAY_ENV, "").strip().lower() != ONAY_DEGER:
        raise CanliOnayHatasi(f"mod=canli için ortamda {ONAY_ENV}={ONAY_DEGER} gerekir; yok: GERÇEK PARA ile başlatma reddedildi")
    wt = h.get("working_type", "MARK_PRICE")
    if wt not in ("MARK_PRICE", "CONTRACT_PRICE"):
        raise CanliAyarHatasi("working_type MARK_PRICE | CONTRACT_PRICE")
    km = h.get("kosullu_modu", "algo")
    if km not in ("algo", "klasik"):
        raise CanliAyarHatasi("kosullu_modu algo | klasik")
    kapanis_onay = _kapanis_onay(h.get("kapanis_canli_onay", []))
    ss, gorulen_id, gorulen_anahtar, gorulen_ozet = [], set(), set(), {}
    for x in h.get("stratejiler", []):
        for a in ("id", "api_key_env", "api_secret_env", "tahsis_usd"):
            if a not in x:
                raise CanliAyarHatasi(f"strateji girdisinde '{a}' yok: {x}")
        tahsis = Decimal(str(x["tahsis_usd"]))
        if tahsis <= 0:
            raise CanliAyarHatasi(f"{x['id']}: tahsis_usd > 0 olmalı")
        if x["id"] in gorulen_id or x["api_key_env"] in gorulen_anahtar:
            raise CanliAyarHatasi(f"{x['id']}: bir hesap = bir strateji (strateji ya da anahtar adı tekrarlı)")
        deger = env.get(x["api_key_env"], "").strip()       # değer ASLA loglanmaz/yazılmaz; yalnız sha256 özeti karşılaştırılır
        if deger:
            oz = hashlib.sha256(deger.encode()).hexdigest()
            if oz in gorulen_ozet:
                raise CanliAyarHatasi(f"{x['id']}: {x['api_key_env']} ile {gorulen_ozet[oz]} aynı API anahtarı değerini kullanıyor (bir hesap = bir strateji)")
            gorulen_ozet[oz] = x["api_key_env"]
        islem_risk = _islem_risk(x["id"], x.get("islem_risk", IZINLI_ISLEM_RISK))
        kaldirac = _kaldirac(x["id"], x.get("kaldirac", VARSAYILAN_KALDIRAC))
        gorulen_id.add(x["id"])
        gorulen_anahtar.add(x["api_key_env"])
        ss.append(StratejiAyar(x["id"], x["api_key_env"], x["api_secret_env"], tahsis, islem_risk, kaldirac))
    if not ss:
        raise CanliAyarHatasi("en az bir strateji gerekir")
    return CanliAyar(mod, tuple(ss), wt, int(h.get("giris_gecikme_max_sn", 900)), km, bool(h.get("hedef_emri", True)), kapanis_onay)


def anahtarlar(s: StratejiAyar, env: Optional[dict] = None) -> tuple:
    """(anahtar, gizli) yalnız ortamdan. Eksikse hata MESAJI yalnız değişken adını içerir (değer asla)."""
    env = os.environ if env is None else env
    a, g = env.get(s.api_key_env, "").strip(), env.get(s.api_secret_env, "").strip()
    if not a or not g:
        raise CanliAyarHatasi(f"{s.id}: ortam değişkeni {s.api_key_env} / {s.api_secret_env} tanımlı değil")
    return a, g
