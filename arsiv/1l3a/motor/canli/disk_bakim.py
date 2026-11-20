"""Disk doluluğu: ölçüm, Telegram uyarısı ve günlük kayıt döndürme (1L3A paper sunucusu).

Telegram komut servisinin (motor/canli/telegram_komut.py, 1l3a-telegram) ana döngüsünden 5 dakikada bir çağrılır: `calistir()`.
Aynı token (/etc/1l3a-paper.env) ile sendMessage yapılır; getUpdates bu modülde çağrılmaz.
  - Ölçüm her çağrıda: kök (/) ve durum kökü (/var/lib/1l3a-paper) için kullanım yüzdesi (df'deki Use% ile aynı formül).
  - Uyarı: %80 -> "[1L3A] ⚠️ Disk X% dolu"; %90 -> "[1L3A] 🔴 Disk X% dolu, kayıtlar duracak".
    Aynı uyarı en çok 6 saatte bir gider (OrtakDurum tekrar kaydı, durum dosyasında kalıcı). Eşiğin altına inince
    tek "[1L3A] Disk düzeldi (X%)" gider.
  - Döndürme: günde bir kez. Kök altındaki *.jsonl / *.log dosyalarından 50 MB'ı aşanlar `arsiv/` altına tarih damgalı
    .gz olarak kopyalanır, sonra asıl dosya boşaltılır (copytruncate). 90 günden eski arsiv/*.gz silinir.
    Silme YALNIZ arsiv/ içindeki .gz dosyaları için. Mühürlü/ön kayıt dosyalarına (ON_KAYIT*, *butunluk*, *kilit*,
    sonuclar/ altı) dokunulmaz; durum.json gibi jsonl olmayan durum dosyaları da hiç döndürülmez.

Copytruncate notu: kopyalama ile boşaltma arasında yazılan birkaç satır kaybolabilir (kopya, boşaltmadan hemen önce
dosyanın son boyutuna kadar yeniden alınır; yine de milisaniyelik bir pencere kalır). Paper kayıt dosyalarını "a" (ekleme)
kipinde açar, bu yüzden boşaltmadan sonraki yazmalar dosya başına düşer ve boşluk oluşmaz.

Hata yutulur: izin ya da disk hatası komut servisini ETKİLEMEZ (calistir hiçbir zaman istisna fırlatmaz).
"""
from __future__ import annotations

import gzip
import json
import logging
import os
import shutil
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, Optional

from motor.canli import telegram as tg

log = logging.getLogger("disk_bakim")

KOK_DIZIN = "/var/lib/1l3a-paper"
OLCULEN_YOLLAR = ("/", KOK_DIZIN)
WARN_ESIK, CRIT_ESIK = 80.0, 90.0
TEKRAR_SN = 6 * 3600
DONDURME_ARALIK_SN = 24 * 3600
DOSYA_SINIR_BAYT = 50 * 1024 * 1024
ARSIV_SAKLAMA_GUN = 90
ARSIV_DIZIN = "arsiv"
KAYIT_UZANTILARI = (".jsonl", ".log")
DURUM_DOSYASI = "disk_bakim.json"          # son döndürme zamanı + alarm durumu (jsonl değil: döndürme kapsamı dışında)
KORUNAN_DIZINLER = ("sonuclar", ARSIV_DIZIN)
KORUNAN_IZLER = ("ON_KAYIT", "butunluk", "kilit")   # dosya/dizin adında geçerse dokunulmaz (küçük harf karşılaştırma)


# ---------------------------------------------------------------------------- ölçüm
def kullanim_yuzdesi(yol: str, disk_usage: Callable = shutil.disk_usage) -> Optional[float]:
    """df'nin Use% değeri: kullanılan / (kullanılan + kullanılabilir). Ölçülemezse None."""
    try:
        u = disk_usage(yol)
    except OSError:
        return None
    toplam = u.used + u.free
    return 100.0 * u.used / toplam if toplam else None


def olc(yollar=OLCULEN_YOLLAR, disk_usage: Callable = shutil.disk_usage) -> dict:
    """{yol: yüzde} (ölçülebilenler). Boş dict: hiçbir yol ölçülemedi."""
    sonuc = {}
    for y in yollar:
        p = kullanim_yuzdesi(y, disk_usage)
        if p is not None and Path(y).exists():
            sonuc[y] = p
    return sonuc


def satir() -> str:
    """/durum için tek satır: 'disk: X%' (ölçülenlerin en dolusu)."""
    v = olc()
    return f"disk: {int(max(v.values()))}%" if v else "disk: ölçülemedi"


# ---------------------------------------------------------------------------- uyarı
def _metin(pct: float, seviye: str) -> str:
    x = int(pct)                                  # ekranda aşağı yuvarlanır: 79.9 -> 79, eşik kararı ham değerle verilir
    if seviye == "CRIT":
        return f"[1L3A] 🔴 Disk {x}% dolu, kayıtlar duracak"
    if seviye == "WARN":
        return f"[1L3A] ⚠️ Disk {x}% dolu"
    return f"[1L3A] Disk düzeldi ({x}%)"


def degerlendir(pct: float, alarm_acik: bool, ortak: tg.OrtakDurum, gonder: Callable[[str], bool], simdi: float) -> bool:
    """Eşik kararı ve bildirim. Döner: yeni alarm durumu (açık/kapalı)."""
    if pct >= WARN_ESIK:
        seviye = "CRIT" if pct >= CRIT_ESIK else "WARN"
        anahtar = "disk:" + seviye.lower()
        if not ortak.tekrar_var(anahtar, TEKRAR_SN, simdi):
            ortak.tekrar_isaretle(anahtar, simdi)
            gonder(_metin(pct, seviye))
        return True
    if alarm_acik:                                 # eşiğin altına indi: tek düzelme mesajı
        gonder(_metin(pct, "INFO"))
    return False


# ---------------------------------------------------------------------------- döndürme
def _korunan(rel: tuple) -> bool:
    """rel: kök altındaki göreli yol parçaları (dosya adı dahil)."""
    for parca in rel:
        kucuk = parca.lower()
        if parca in KORUNAN_DIZINLER or any(i.lower() in kucuk for i in KORUNAN_IZLER):
            return True
    return False


def _aday_kayitlar(kok: Path) -> list:
    if not kok.is_dir():
        return []
    aday = []
    for dis, dizinler, dosyalar in os.walk(kok):
        dizinler[:] = [d for d in dizinler if d not in KORUNAN_DIZINLER and not os.path.islink(os.path.join(dis, d))]
        for ad in dosyalar:
            yol = Path(dis) / ad
            if yol.suffix not in KAYIT_UZANTILARI or yol.is_symlink() or not yol.is_file():
                continue
            if _korunan(yol.relative_to(kok).parts):
                continue
            aday.append(yol)
    return aday


def _acilan_uzunluk(gz: Path) -> int:
    toplam = 0
    with gzip.open(gz, "rb") as f:
        while True:
            parca = f.read(1 << 20)
            if not parca:
                return toplam
            toplam += len(parca)


def arsivle(yol: Path, arsiv: Path, simdi: datetime) -> Path:
    """yol'un o anki içeriğini arsiv/<ad>.<YYYYmmdd-HHMMSS>.gz'ye yazar, doğrular, sonra yol'u boşaltır (copytruncate).
    Doğrulama başarısızsa yol'a dokunulmaz."""
    arsiv.mkdir(parents=True, exist_ok=True)
    damga = simdi.strftime("%Y%m%d-%H%M%S")
    hedef = arsiv / f"{yol.name}.{damga}.gz"
    n = 1
    while hedef.exists():
        hedef = arsiv / f"{yol.name}.{damga}-{n}.gz"
        n += 1
    gecici = hedef.with_name(hedef.name + ".part")
    kopyalanan = 0
    try:
        with open(yol, "rb") as k, gzip.open(gecici, "wb", compresslevel=6) as z:
            # Kopyalama sırasında büyüyen ek de alınır: boyut her turda yeniden okunur, değişmeyene kadar sürer.
            while True:
                boyut = os.fstat(k.fileno()).st_size
                if kopyalanan >= boyut:
                    break
                while kopyalanan < boyut:
                    parca = k.read(min(1 << 20, boyut - kopyalanan))
                    if not parca:
                        break
                    z.write(parca)
                    kopyalanan += len(parca)
        if _acilan_uzunluk(gecici) != kopyalanan:
            raise OSError("arşiv doğrulanamadı (uzunluk tutmadı)")
        os.replace(gecici, hedef)
    except Exception:
        gecici.unlink(missing_ok=True)
        raise
    # copytruncate: yalnız arşiv doğrulandıktan sonra. Paper dosyayı "a" kipinde açar; yazmalar sıfırdan devam eder.
    os.truncate(yol, 0)
    return hedef


def _eski_arsivleri_sil(arsiv: Path, simdi: datetime, gun: int = ARSIV_SAKLAMA_GUN) -> int:
    """YALNIZ arsiv/ içindeki .gz dosyaları; mtime'ı `gun` günden eski olanlar silinir."""
    if not arsiv.is_dir():
        return 0
    sinir = simdi.timestamp() - gun * 86400
    silinen = 0
    for f in arsiv.glob("*.gz"):
        if f.is_file() and not f.is_symlink() and f.stat().st_mtime < sinir:
            f.unlink()
            silinen += 1
    return silinen


def dondur(kok: Path, simdi: datetime, sinir: int = DOSYA_SINIR_BAYT) -> dict:
    """Bir döndürme turu. Dosya bazlı hatalar loglanır, tur devam eder."""
    arsivlenen, hata = [], 0
    arsiv = kok / ARSIV_DIZIN
    for yol in _aday_kayitlar(kok):
        try:
            if yol.stat().st_size > sinir:
                arsivle(yol, arsiv, simdi)
                arsivlenen.append(yol.name)
        except Exception as e:  # noqa: BLE001
            hata += 1
            log.warning("döndürme atlandı (%s): %s", yol.name, type(e).__name__)
    try:
        silinen = _eski_arsivleri_sil(arsiv, simdi)
    except OSError as e:
        silinen, hata = 0, hata + 1
        log.warning("eski arşiv silinemedi: %s", type(e).__name__)
    return {"arsivlenen": arsivlenen, "silinen": silinen, "hata": hata}


# ---------------------------------------------------------------------------- durum dosyası (yalnız disk_bakim.json)
def _durum_oku(yol: Path) -> dict:
    try:
        d = json.loads(yol.read_text(encoding="utf-8"))
        return d if isinstance(d, dict) else {}
    except (OSError, ValueError):
        return {}


def _durum_yaz(yol: Path, d: dict) -> None:
    gecici = yol.with_name(yol.name + ".tmp")
    gecici.write_text(json.dumps(d, ensure_ascii=False), encoding="utf-8")
    os.replace(gecici, yol)


# ---------------------------------------------------------------------------- giriş noktası
def calistir(kok: str = KOK_DIZIN, simdi: Optional[float] = None, ortak: Optional[tg.OrtakDurum] = None,
             gonder: Optional[Callable[[str], bool]] = None, olcer: Optional[Callable[[], dict]] = None) -> Optional[dict]:
    """Komut döngüsünde çağrılır (5 dk). Ölçüm + uyarı her çağrıda; döndürme günde bir. Hiçbir hata dışarı çıkmaz."""
    try:
        t = time.time() if simdi is None else simdi
        kok_p = Path(kok)
        ortak = ortak if ortak is not None else tg.ortak_durum()
        gonder = gonder or tg.gonder
        olcum = (olcer or olc)()
        durum_yolu = kok_p / DURUM_DOSYASI
        durum = _durum_oku(durum_yolu) if kok_p.is_dir() else {}
        sonuc = {"olcum": olcum, "dondurme": None}
        if olcum:
            pct = max(olcum.values())
            alarm = degerlendir(pct, bool(durum.get("alarm")), ortak, gonder, t)
            durum["alarm"] = alarm
        son = durum.get("son_dondurme")
        if kok_p.is_dir() and (son is None or t - float(son) >= DONDURME_ARALIK_SN):
            simdi_dt = datetime.fromtimestamp(t, tz=timezone.utc)
            sonuc["dondurme"] = dondur(kok_p, simdi_dt)
            durum["son_dondurme"] = t
        if kok_p.is_dir():
            _durum_yaz(durum_yolu, durum)
        return sonuc
    except Exception as e:  # noqa: BLE001  (disk bakımı nabız servisini asla düşürmez)
        log.warning("disk bakımı atlandı: %s", type(e).__name__)
        return None
