"""ETİKET KURALLARI (kullanıcı onaylı, 2026-11-19; ÖN KAYIT, aşağıdaki sabitler DEĞİŞMEZ): kayıt etiketleri paper GİRİŞİNİ yalnız ATLATABİLİR.

Boyut/limit/stop/hedef değişmez, yeni giriş açtırılmaz; hata -> giriş serbest (+log); etiket null -> o kural uygulanmaz (veri yok = engel yok).
Kanca: `paper_motor.etiket_suzgeci` (giris_suzgeci'nden sonra zincirlenir; herhangi biri reddederse atlanır). Atlanan giriş `alinmayan_sinyaller.jsonl`'e
neden "etiket:<kural>" ile yazılır. L3A_ETIKET_KURAL_KAPALI=1 ile kapanır. Canlı yürütücü niyetleri paper'dan aldığı için atlanan paper girişi canlıda da açılmaz.
Korku/açgözlülük (kullanıcı kararı 2026-11-19, "kapalı özellik kalmayacak"): 4. kural `korku_acgozluluk` — endeks >= 75 (aşırı açgözlülük) long'u, <= 25 (aşırı korku) short'u atlatır.
Haber (kullanıcı kararı 2026-11-19): 5. kural `haber_ters` — son 24 saatte >= 2 başlık VE haber tonu (-1..1) girişin tersiyse (long: ton < -0.2, short: ton > +0.2) atlatır.
"""
from __future__ import annotations

import logging
import os
from typing import Callable, Optional

log = logging.getLogger("etiket_kurallari")

# --- ön kayıt sabitleri (değişmez) ---
KALABALIK_FONLAMA = 0.0005        # long: fonlama_orani >= +bu; short: fonlama_orani <= -bu
KALABALIK_OI_DEGISIM_24S = 0.10   # VE oi_degisim_24s >= bu (oransal, %10)
ACGOZLULUK_ESIK, KORKU_ESIK = 75, 25   # korku_acgozluluk >= 75: long atla; <= 25: short atla
HABER_ESIK, HABER_MIN_SAYI = 0.2, 2     # haber_ters: haber_sayisi >= 2 VE long'da ton < -0.2 / short'ta ton > +0.2 -> atla (CT'de eşik bulunamadı; kullanıcı yönergesi 0.2)
REJIM_KARSITI = {"long": "trend_down", "short": "trend_up"}
KAPATMA_BAYRAGI = "L3A_ETIKET_KURAL_KAPALI"
KURALLAR = ("rejim_karsiti", "takvim_olayi", "kalabalik", "korku_acgozluluk", "haber_ters")   # `degerlendir` neden son eki ("etiket:<kural>")


def _sayi(x) -> bool:
    return isinstance(x, (int, float)) and not isinstance(x, bool)


def kapali(env=None) -> bool:
    return (os.environ if env is None else env).get(KAPATMA_BAYRAGI) == "1"


def degerlendir(yon: str, et: Optional[dict], devre_disi=frozenset()) -> Optional[str]:
    """Etiketlere göre atlatma nedeni ("etiket:<kural>") ya da None (serbest). yon: 'long'|'short'.
    `devre_disi`: kâğıtta gevşetilmiş kural adları (alinsaydi_gevsetme.py); varsayılan boş = davranış DEĞİŞMEZ."""
    if not et:
        return None
    rejim = et.get("rejim_ml_1d") or et.get("rejim_ml_4h")
    if rejim is not None and rejim == REJIM_KARSITI.get(yon) and "rejim_karsiti" not in devre_disi:
        return "etiket:rejim_karsiti"
    if et.get("takvim_bayragi") and "takvim_olayi" not in devre_disi:
        return "etiket:takvim_olayi"
    f, oi = et.get("fonlama_orani"), et.get("oi_degisim_24s")
    if f is not None and oi is not None and oi >= KALABALIK_OI_DEGISIM_24S and "kalabalik" not in devre_disi:
        if (yon == "long" and f >= KALABALIK_FONLAMA) or (yon == "short" and f <= -KALABALIK_FONLAMA):
            return "etiket:kalabalik"
    kg = et.get("korku_acgozluluk")
    if isinstance(kg, (int, float)) and not isinstance(kg, bool) and "korku_acgozluluk" not in devre_disi:
        if (yon == "long" and kg >= ACGOZLULUK_ESIK) or (yon == "short" and kg <= KORKU_ESIK):
            return "etiket:korku_acgozluluk"
    ht, hs = et.get("haber_tonu"), et.get("haber_sayisi")
    if _sayi(ht) and _sayi(hs) and hs >= HABER_MIN_SAYI and "haber_ters" not in devre_disi:
        if (yon == "long" and ht < -HABER_ESIK) or (yon == "short" and ht > HABER_ESIK):
            return "etiket:haber_ters"
    return None


def _suzgec(h) -> Callable:
    def suz(t, e) -> tuple:
        if getattr(h, "kayit", None) is None:
            return True, ""
        yon = "long" if e.yon == 1 else "short"
        neden = degerlendir(yon, h._etiket_uret(t, e.kol))
        return (True, "") if neden is None else (False, neden)
    return suz


def bagla(p, env=None) -> bool:
    """paper.canli_calistir tek satırı (kayit_ac'tan sonra). Paper ya da v2 (her hesabına; sonradan eklenenler her adımda). Kapalıysa/hatada False."""
    if kapali(env):
        return False
    try:
        def tak():
            for h in (list(p.hesaplar.values()) if hasattr(p, "hesaplar") else [p]):
                if getattr(h.motor, "etiket_suzgeci", None) is None:
                    h.motor.etiket_suzgeci = _suzgec(h)
        tak()
        adim = p.adim

        def adim_sarili(*a, **k):
            try:
                tak()
            except Exception:  # noqa: BLE001
                log.exception("etiket kuralları yeni hesaba bağlanamadı")
            return adim(*a, **k)
        p.adim = adim_sarili
        return True
    except Exception:  # noqa: BLE001
        log.exception("etiket kuralları bağlanamadı; paper kuralsız sürer")
        return False
