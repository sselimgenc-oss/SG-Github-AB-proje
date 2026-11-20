"""Aday paper hesapları: haftalık taramadan çıkan kartlar DOĞRUDAN paper'a girer (kullanıcı kararı 2026-11-19). Gerçek emir YOK.

Servis: deploy/1l3a-aday-paper.service. Mevcut 10'lu paper setine (paper_v2, imza fffbc6624416634e) ve ct_paper'a DOKUNMAZ.
Yapı: gözetmen süreç `stratejiler/aday_paper_listesi.json` ([{id, kart_yolu, eklenme_tarihi}]) listesini okur ve HER aday için ayrı bir alt süreç
başlatır (`--hesap ID`): kendi durum dizini (`<taban>/<hesap_dizin_adi(id)>`), kendi 10.000 USD sanal hesabı, SERT_LIMITLER aynen (paper motoru),
kendi kill'i ve "[1L3A] aday:<kısa ad>" Telegram başlığı. Alt süreç ayrı olduğu için süreç-içi yamalar (ct_paper kalıbı) hesaplar arasında karışmaz.
Liste boşsa gözetmen boşta bekler (hata yok); liste büyüyünce yeni hesap eklenir (çalışırken ya da yeniden başlatmada), mevcut hesapların durumu
kendi alt dizininde kalır (set imzası sorunu yok). Listeden çıkarılan hesap durdurulmaz/silinmez (durum dizini korunur).
Strateji tanımı: kart JSON'unda (liste ya da tek nesne) ya da liste kaydında "uygulama": {"sinif", "modul", "parametreler", "tf", "evren"}
(kapanış koşu listesi ile aynı çözümleyici: araclar/kapanis_kosu_listesi). Tanım yoksa/çözülmezse hesap başlamaz (fail-closed, gözetmen yalnız uyarır).

CLI:  python -m motor.canli.aday_paper --durum TABAN_DIZIN [--liste YOL] [--tek-sefer]      (ortam: L3A_ADAY_DURUM, L3A_ADAY_LISTE)
"""
from __future__ import annotations

import argparse
import json
import logging
import os
import signal
import subprocess
import sys
import time
from decimal import Decimal
from pathlib import Path
from typing import Callable, Optional

from motor.canli import ct_paper as cp
from motor.canli import paper as pp
from motor.canli.paper_v2 import hesap_dizin_adi
from motor.canli.paper_sinyal import StratejiTanim

log = logging.getLogger("paper.aday")
KOK = Path(__file__).resolve().parents[2]
VARSAYILAN_DURUM = "/var/lib/1l3a-paper/durum/adaylar"
VARSAYILAN_LISTE = KOK / "stratejiler" / "aday_paper_listesi.json"
ETIKET = cp.ETIKET
BEKLEME_SN = 30
GERI_CEKILME_SN = 60                                  # çöken alt süreç: deneme sayısı x bu kadar sn sonra yeniden (en çok 10 dk)


class AdayHatasi(RuntimeError):
    """Aday kaydı/kartı geçersiz (fail-closed: o hesap başlamaz)."""


def liste_yukle(yol: Path = VARSAYILAN_LISTE) -> list:
    """Dosya yok/boş -> []. Bozuk dosya -> AdayHatasi. Kayıtlar {id, kart_yolu, eklenme_tarihi}; id tekil olmalı."""
    yol = Path(yol)
    if not yol.exists() or not yol.read_text(encoding="utf-8").strip():
        return []
    try:
        liste = json.loads(yol.read_text(encoding="utf-8"))
    except ValueError as e:
        raise AdayHatasi(f"{yol}: JSON okunamadı: {e}") from e
    if not isinstance(liste, list):
        raise AdayHatasi(f"{yol}: liste bekleniyordu")
    gorulen = set()
    for k in liste:
        if not isinstance(k, dict) or not k.get("id") or not k.get("kart_yolu"):
            raise AdayHatasi(f"{yol}: kayıtta 'id' ve 'kart_yolu' zorunlu: {k}")
        if k["id"] in gorulen:
            raise AdayHatasi(f"{yol}: yinelenen id {k['id']}")
        gorulen.add(k["id"])
    dizinler: dict = {}
    for k in liste:                                  # farklı kimlikler aynı durum dizinine düşerse ortak durum/.kilit olur: açık hata
        ad = hesap_dizin_adi(k["id"])
        if ad in dizinler:
            raise AdayHatasi(f"{yol}: '{dizinler[ad]}' ve '{k['id']}' aynı hesap dizin adına düşüyor ({ad})")
        dizinler[ad] = k["id"]
    return liste


def kisa_ad(kimlik: str) -> str:
    """'swing__korelasyon-ivmesi-spy-hedge__quantpedia' -> 'korelasyon-ivmesi-spy-hedge' (en çok 30 karakter)."""
    parca = kimlik.split("__")
    return (parca[1] if len(parca) >= 3 else kimlik)[:30]


def hesap_dizini(taban: Path, kimlik: str) -> Path:
    return Path(taban) / hesap_dizin_adi(kimlik)


def baslik(kimlik: str) -> str:
    return "Aday hesabı"                            # kod adı (kısa_ad) mesaja yazılmaz


def baslikli(gonder, kimlik: str):
    """ct_paper.baslikli ile aynı kalıp; başlık '[1L3A] aday:<kısa ad>' (önem düzeyi korunur)."""
    b = baslik(kimlik)

    def g(metin, *a, **k):
        return gonder(cp.etiket_ekle(metin, b), *a, **k)
    return g


def tanim_kur(kayit: dict, kok: Path = KOK) -> StratejiTanim:
    """Kayıt + kart -> StratejiTanim (tek_evren, pay 1; kapanış kaydı ile aynı çözümleyici)."""
    from araclar import kapanis_kosu_listesi as kl
    yol = Path(kayit["kart_yolu"])
    yol = yol if yol.is_absolute() else Path(kok) / yol
    try:
        kart = json.loads(yol.read_text(encoding="utf-8"))
    except (OSError, ValueError) as e:
        raise AdayHatasi(f"{kayit['id']}: kart okunamadı ({yol}): {e}") from e
    if isinstance(kart, list):
        kart = next((x for x in kart if isinstance(x, dict) and x.get("kart_id") == kayit["id"]), kart[0] if len(kart) == 1 else {})
    u = kayit.get("uygulama") or (kart or {}).get("uygulama")
    if not isinstance(u, dict) or not all(u.get(a) for a in ("sinif", "tf", "evren")):
        raise AdayHatasi(f"{kayit['id']}: 'uygulama' ({{sinif, modul, parametreler, tf, evren}}) yok; kart henüz kodlanmamış")
    try:
        nesne, pf = kl.strateji_kur(u["sinif"], u.get("modul", ""), dict(u.get("parametreler") or {}))
        evren = kl.evren_coz(u["evren"])
    except Exception as e:  # noqa: BLE001
        raise AdayHatasi(f"{kayit['id']}: strateji kurulamadı: {type(e).__name__}: {e}") from e
    if pf or nesne is None:
        raise AdayHatasi(f"{kayit['id']}: portföy sınıfı aday paper hesabı olamaz")
    return StratejiTanim(kayit["id"], getattr(nesne, "stil", "") or "swing", "tek_evren", nesne.ad, "", u["tf"], "varsayilan", nesne,
                         kayit["id"], Decimal(1), tuple(evren), etiket="aday",
                         ayar_dosyasi=f"{kayit['kart_yolu']} (haftalık tarama kartı)")


def hesap_calistir(kayit: dict, durum_dizini: Path, tek_sefer: bool = False) -> int:
    """Alt süreç: TEK aday hesabı (ct_paper.calistir kalıbı; yamalar bu sürece özel)."""
    from motor.canli import telegram as tg
    tanim = tanim_kur(kayit)
    durum_dizini = Path(durum_dizini)
    durum_dizini.mkdir(parents=True, exist_ok=True)
    cp.surec_ici_yama(tg, [tanim], baslikli(tg.gonder, kayit["id"]), f"aday:{kisa_ad(kayit['id'])}")
    log.info("aday hesabı başlıyor: %s, durum %s", kayit["id"], durum_dizini)
    return pp.canli_calistir(durum_dizini, None, False, tek_sefer, set_modu="eski")


def alt_surec_baslat(kayit: dict, durum_dizini: Path, liste_yolu: Path):
    return subprocess.Popen([sys.executable, "-m", "motor.canli.aday_paper", "--hesap", kayit["id"], "--durum", str(durum_dizini),
                             "--liste", str(liste_yolu)], cwd=str(KOK))


def gozetle(taban: Path, liste_yolu: Path = VARSAYILAN_LISTE, baslat: Callable = alt_surec_baslat, uyku: Callable = time.sleep,
            simdi: Callable = time.monotonic, tek_sefer: bool = False, dur: Optional[Callable[[], bool]] = None) -> int:
    """Liste okur, her aday için alt süreç tutar (çökeni geri çekilmeyle yeniden başlatır). Liste boş/bozuk -> boşta (hata yok)."""
    taban = Path(taban)
    taban.mkdir(parents=True, exist_ok=True)
    cocuk: dict = {}                                   # id -> {"p": süreç, "deneme": n, "sonra": t}
    durdur = {"v": False}
    try:
        signal.signal(signal.SIGTERM, lambda *_: durdur.__setitem__("v", True))
    except ValueError:                                 # ana iş parçacığı değil (testler)
        pass
    uyari: set = set()
    try:
        while not durdur["v"] and not (dur and dur()):
            try:
                liste = liste_yukle(liste_yolu)
            except AdayHatasi as e:
                if str(e) not in uyari:
                    uyari.add(str(e))
                    log.error("aday listesi okunamadı (mevcut hesaplar sürer): %s", e)
                liste = []
            for k in liste:
                c = cocuk.get(k["id"])
                if c and c["p"] is not None and c["p"].poll() is None:
                    continue
                if c and simdi() < c["sonra"]:
                    continue
                if c and c["p"] is not None:
                    log.warning("aday %s alt süreci düştü (çıkış %s); yeniden başlatılıyor", k["id"], c["p"].poll())
                deneme = (c["deneme"] + 1) if c else 0
                try:
                    p = baslat(k, hesap_dizini(taban, k["id"]), liste_yolu)
                except Exception as e:  # noqa: BLE001
                    log.error("aday %s başlatılamadı: %s: %s", k["id"], type(e).__name__, e)
                    p = None
                cocuk[k["id"]] = {"p": p, "deneme": deneme, "sonra": simdi() + min(GERI_CEKILME_SN * (deneme + 1), 600)}
            if tek_sefer:
                break
            uyku(BEKLEME_SN)
    finally:
        for c in cocuk.values():
            if c["p"] is not None and c["p"].poll() is None:
                c["p"].terminate()
    return 0


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="1L3A aday paper hesapları (gerçek emir yok)")
    ap.add_argument("--durum", default=os.environ.get("L3A_ADAY_DURUM", VARSAYILAN_DURUM))
    ap.add_argument("--liste", default=os.environ.get("L3A_ADAY_LISTE", str(VARSAYILAN_LISTE)))
    ap.add_argument("--hesap", default=None, help="(alt süreç) yalnız bu aday kimliğini çalıştır; --durum o hesabın dizinidir")
    ap.add_argument("--tek-sefer", action="store_true")
    ap.add_argument("--log", default="INFO")
    a = ap.parse_args(argv)
    logging.basicConfig(level=a.log, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    if a.hesap:
        kayit = next((k for k in liste_yukle(Path(a.liste)) if k["id"] == a.hesap), None)
        if kayit is None:
            log.error("aday %s listede yok", a.hesap)
            return 2
        return hesap_calistir(kayit, Path(a.durum), a.tek_sefer)
    return gozetle(Path(a.durum), Path(a.liste), tek_sefer=a.tek_sefer)


if __name__ == "__main__":
    raise SystemExit(main())
