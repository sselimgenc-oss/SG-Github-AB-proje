"""İşlem mutabakatı Telegram özeti: pano servisinin yazdığı mutabakat_v1.json okunur, kullanıcıya YALNIZ SORUN varsa (kasa tutmuyor / uyuşmazlık > 0) uyarı gider.

Yalnız komut servisi çağırır (Telegram anahtarı yalnız onda). Dosya yoksa/bozuksa sessizce geçilir.
Tekrar kuralı: sorun metni bir kez gider; metin değişirse bir kez daha. Sorun yoksa hiç mesaj yok ("Düzeldi" de yok).
"""
from __future__ import annotations

import hashlib
import json
import logging
import time
from pathlib import Path
from typing import Callable, Optional

from motor.canli import hesap_adlari as ha
from motor.canli import telegram as tg
from motor.canli.gunluk_ozet import _dec

log = logging.getLogger("paper.mutabakat_telegram")
DOSYA = "mutabakat_v1.json"
BAYRAK_DOSYA = "mutabakat_telegram.json"
ARALIK_SN = 600                       # kontrol sıklığı
TEKRAR_SN = 6 * 3600                  # aynı metin en çok 6 saatte bir
ORNEK_MAKS = 3
TUR_METNI = {"kasa": "kasa tutmuyor", "acik_sayisi": "açık pozisyon sayısı", "serit": "şerit kasası", "telegram_gonderim": "Telegram mesajı",
             "pano_okuma": "pano okuma"}


def _oku(yol: Path) -> Optional[dict]:
    try:
        c = json.loads(Path(yol).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    if not isinstance(c, dict) or not isinstance(c.get("ozet"), dict) or not isinstance(c.get("satirlar"), list):
        return None
    return c


def _n(x) -> int:
    return int(x) if isinstance(x, (int, float)) else 0


def _tamam(kasalar: list, ct: bool) -> bool:
    return all(bool(k.get("tamam")) for k in kasalar if isinstance(k, dict) and ((k.get("hesap") == ha.CT_HESABI) == ct))


def _ne(u: dict) -> str:
    tur = u.get("tur")
    if tur in TUR_METNI:
        return TUR_METNI[tur]
    return str(u.get("mesaj", "uyuşmuyor")).split(";")[0][:70]


def uyusmazlik_satiri(u: dict, s: dict) -> str:
    """Tek uyuşmazlık -> sade Türkçe satır (hesap adı yok). Yapısal alan (beklenen/kayit/fark) varsa tutarla, yoksa coin + yön + kısa neden."""
    b, k, f = _dec(u.get("beklenen")), _dec(u.get("kayit")), _dec(u.get("fark"))
    if u.get("tur") == "kasa" and None not in (b, k, f):
        return f"Kasa {tg.usd(b)} olmalı, kayıtta {tg.usd(k)} · fark {tg.usd(abs(f))}"
    if u.get("tur") == "acik_sayisi" and None not in (b, k):
        yer = "motor sayacında" if u.get("kaynak") == "motor sayacı" else "kayıtta"
        return f"Açık pozisyon: {yer} {tg.tr_sayi(k, 0)}, panoda {tg.tr_sayi(b, 0)}"
    parca = [s.get("coin"), s.get("yon"), _ne(u)]
    return " ".join(str(p) for p in parca if p)


def sorun_var(c: dict) -> bool:
    """Yalnız kasa tutmuyorsa ya da uyuşmazlık > 0 ise sorun vardır."""
    o = c["ozet"]
    return _n(o.get("uyusmazlik_sayisi")) > 0 or not _tamam(o.get("kasa_kontrolleri") or [], False) or not _tamam(o.get("kasa_kontrolleri") or [], True)


def metin_uret(c: dict) -> str:
    """Sorun mesajı: en çok 4 satır; ilk satır başlık + ilk sorun. Sorun yoksa boş metin (mesaj gitmez)."""
    if not sorun_var(c):
        return ""
    o = c["ozet"]
    satirlar = [s for s in c["satirlar"] if isinstance(s, dict)]
    uyus = [u for u in (o.get("uyusmazliklar") or []) if isinstance(u, dict)]
    by_no = {s.get("islem_no"): s for s in satirlar}
    detay = [uyusmazlik_satiri(u, by_no.get(u.get("islem_no")) or {}) for u in uyus[:ORNEK_MAKS]]
    if not detay:
        detay = ["Kasa tutmuyor, ayrıntı panoda"]
    L = [f"{tg.ust('WARN')} İşlem kontrolü: {detay[0]}"] + detay[1:]
    return "\n".join(L[:4]).replace("_", " ")


def tick(durum_dizin, gonder: Callable[..., bool] = None, simdi: Optional[float] = None) -> bool:
    """Gerekirse özeti gönderir -> gönderildi mi. Hiçbir hata dışarı çıkmaz."""
    try:
        gonder = gonder or tg.gonder
        simdi = time.time() if simdi is None else simdi
        durum = Path(durum_dizin)
        c = _oku(durum / DOSYA)
        if c is None:
            return False
        metin = metin_uret(c)
        bayrak_yol = durum / BAYRAK_DOSYA
        onceki = None
        try:
            onceki = json.loads(bayrak_yol.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            pass
        if not metin:                                         # sorun yok: mesaj yok, "Düzeldi" de yok; bayrak sıfırlanır (aynı sorun dönerse yeniden haber verilir)
            if isinstance(onceki, dict) and onceki.get("imza"):
                try:
                    bayrak_yol.write_text(json.dumps({"imza": None, "zaman": simdi}), encoding="utf-8")
                except OSError:
                    log.warning("mutabakat bayrağı yazılamadı")
            return False
        imza = hashlib.sha1(metin.encode("utf-8")).hexdigest()[:16]
        if isinstance(onceki, dict) and onceki.get("imza") == imza:
            return False                                      # aynı sorun metni tekrar gitmez
        if not gonder(metin, seviye="WARN"):
            return False
        try:
            bayrak_yol.write_text(json.dumps({"imza": imza, "zaman": simdi, "uretim": c.get("uretim")}), encoding="utf-8")
        except OSError:
            log.warning("mutabakat bayrağı yazılamadı")
        return True
    except Exception as e:  # noqa: BLE001  komut dinlemeyi asla etkilemesin
        log.warning("mutabakat özeti atlandı: %s", type(e).__name__)
        return False
