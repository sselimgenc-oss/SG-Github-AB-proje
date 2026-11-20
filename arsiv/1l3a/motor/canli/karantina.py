"""Strateji kod hatası karantinası (yardımcılar).

Bir stratejinin karar kodu PROGRAMLAMA hatası verirse (`paper_veri.STRATEJI_HATALARI`: TypeError, KeyError, ZeroDivisionError, ValueError ...) yalnız o strateji (birim) karantinaya
girer; tüm tur düşmez. Karantinada: strateji kodu ÇAĞRILMAZ, yeni giriş YOK (bekleyen giriş emirleri silinir, `_giris_izni` reddeder), açık pozisyon motorun
stop / hedef / zaman / kill / günlük limit yönetimiyle sürer (stop ve kill her turda çalışır). Diğer stratejiler aynı turda normal işler.
Geçici veri/ağ hataları (`paper_veri.GECICI_HATALAR`: BinanceHata, OSError, JSON/Unicode ayrıştırma) bu yola GİRMEZ; eski yolunda (TurKoruyucu / sonsuz_dene) kalır.

Kayıt (Paper.karantina[kimlik], paper_state.json'da kalıcı): {"zaman", "sha", "hata", "durum": "aktif" | "deneme"}.
  aktif : karantinada. deneme: kaldırıldı (kod SHA'sı değişti ya da elle), strateji yeniden çalışır; İLK başarılı karardan sonra kayıt silinir + INFO "düzeldi".
Kaldırma: (1) kod SHA'sı kayıttakinden farklıysa (oto_guncelle servisi yeniden başlatır) bir kez yeniden denenir; (2) Telegram /karantina_kaldir <strateji>
(iki adımlı kod; istek dosyası KARANTINA_KALDIR, paper her turda okur).
Bildirim: giriş WARN ⚠️ "<ad> stratejisi hata verdi, yeni işlem açmıyor; açık pozisyonlar stop/hedefle sürüyor" (aynı strateji için en çok 6 saatte bir), çıkış INFO. Gizli hesap adı hiçbir mesajda yok ("Diğer hesap").
"""
from __future__ import annotations

import os
import subprocess
from pathlib import Path
from typing import Callable, Optional

BILDIRIM_ARALIK_SN = 6 * 3600
ISTEK_AD = "KARANTINA_KALDIR"
ISTEK_ACK = "karantina_kaldir_islendi.json"
GIZLI_AD = "Diğer hesaplar"
_SHA_ONBELLEK: dict = {}


def kod_sha() -> Optional[str]:
    """Çalışan kodun kısa git SHA'sı (süreç başına bir kez; kod güncellenince servis yeniden başlar). L3A_KOD_SHA ile ezilir. Okunamazsa None."""
    env = os.environ.get("L3A_KOD_SHA")
    if env:
        return env
    if "sha" not in _SHA_ONBELLEK:
        kok = os.environ.get("L3A_GUNCELLE_KOK") or str(Path(__file__).resolve().parents[2])
        try:
            p = subprocess.run(["git", "-C", kok, "rev-parse", "--short", "HEAD"], capture_output=True, text=True, timeout=5)
            _SHA_ONBELLEK["sha"] = p.stdout.strip() if p.returncode == 0 and p.stdout.strip() else None
        except Exception:  # noqa: BLE001
            _SHA_ONBELLEK["sha"] = None
    return _SHA_ONBELLEK["sha"]


def istek_dosyasi(durdur_dizini: Path, env=None) -> Path:
    env = os.environ if env is None else env
    return Path(env.get("L3A_KARANTINA_KALDIR_DOSYA") or (Path(durdur_dizini) / ISTEK_AD))


def satir(ozet: Optional[dict]) -> Optional[str]:
    """saglik.json `karantina` bloğu {'gorunur': [kimlik...], 'gizli': N} -> tek satır (yoksa None). Gizli adlar yok."""
    if not ozet:
        return None
    parcalar = list(ozet.get("gorunur") or [])
    if ozet.get("gizli"):
        parcalar.append(f"{GIZLI_AD} ({ozet['gizli']})")
    if not parcalar:
        return None
    return "Karantinada (yeni giriş yok, açık pozisyon stop/hedefle sürer): " + ", ".join(parcalar)


def hedef_eslesir(hedef: str, kimlik: str, gorunur: bool) -> bool:
    """/karantina_kaldir argümanı: tam kimlik, 'gizli' (yalnız gizli hesaplar) ya da 'hepsi'."""
    h = hedef.strip().lower()
    return h == "hepsi" or (h == "gizli" and not gorunur) or (gorunur and h == kimlik.lower())
