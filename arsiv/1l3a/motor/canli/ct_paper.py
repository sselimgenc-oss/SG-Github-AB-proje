"""ct_konsensus paper hesabı: giriş noktası (servis: deploy/1l3a-ct-paper.service). Gerçek emir YOK, canlı yürütücüye BAĞLI DEĞİL.

Kural/ön kayıt sabitleri: motor/canli/ct_kadro.py (dosyanın başı). Mevcut 10'lu paper setine (paper_v2, imza fffbc6624416634e) dokunulmaz:
burada yalnız `paper.canli_calistir` (mevcut paper motoru + durum yazıcısı + Telegram + kalp atışı + kill) AYRI bir durum dizininde ve
KENDİ süreci içinde, `eski` (tek hesap) kipiyle çalıştırılır. Süreç-içi yamalar (diske/başka sürece etkisi yok):
  - paper.psg.tanimlari_yukle -> ct_konsensus sembol tanımları
  - paper.PaperMotor          -> kendini KonsensusDeposu'na bağlayan alt sınıf (açık pozisyon sayısı/yönü için)
  - paper.paper_ayarlari      -> 10.000 USD, işlem başı risk SERT_LIMITLER.islem_basi_max_risk_yuzde (limitler motorda aynen uygulanır)
  - paper.PENCERE["15m"]      -> 300 bar (ATR için yeter; REST yükünü azaltır)
  - telegram.gonder           -> mesaj başına "[1L3A] ct_konsensus" başlığı
Durum dosyaları mevcut paper durum biçimindedir (ozet/stratejiler/islemler/saglik/...), böylece pano sonra okuyabilir.

CLI:  python -m motor.canli.ct_paper --durum DIZIN [--tek-sefer]        (ortam: L3A_CT_URL, L3A_CT_DURUM, TELEGRAM_BOT_TOKEN/CHAT_ID)
"""
from __future__ import annotations

import argparse
import logging
import os
from pathlib import Path
from typing import Optional

from motor.canli import ct_kadro as ck
from motor.canli import paper as pp
from motor.canli import paper_sinyal as psg
from motor.canli.paper_motor import PaperMotor
from motor.portfoy.motor import PortfoyAyarlari
from motor.risk.limitler import SERT_LIMITLER

log = logging.getLogger("paper.ct")
VARSAYILAN_DURUM = "/var/lib/1l3a-paper/durum/ct_konsensus"
BASLIK = "CT konsensüs hesabı"                         # kod adı (ct_konsensus) mesaja yazılmaz
ETIKET = "[1L3A]"


def ct_ayarlari(baslangic_sermaye: float = ck.BASLANGIC_KASA) -> PortfoyAyarlari:
    """10.000 USD sanal kasa; işlem başı risk SERT_LIMITLER'den (kopya yok); limit_modu 'uygula' (paper motoru başka kipi reddeder)."""
    return PortfoyAyarlari(baslangic_sermaye=baslangic_sermaye, risk_yuzde=SERT_LIMITLER.islem_basi_max_risk_yuzde, limit_modu="uygula")


def motor_sinifi(deposu: ck.KonsensusDeposu):
    class CtMotor(PaperMotor):
        def __init__(self, *a, **k):
            super().__init__(*a, **k)
            deposu.motor_bagla(self)
    return CtMotor


def etiket_ekle(metin: str, etiket: str) -> str:
    """"[1L3A] ✅ BTCUSDT long kapandı: +5 $" -> "... +5 $ · CT konsensüs hesabı" (etiket ilk satırın sonuna; seviye emojisi başta kalır).
    Standart ilk satır yoksa "[1L3A] <etiket>" satırı eklenir."""
    if metin.startswith(ETIKET):
        ilk, ayrac, kalan = metin.partition("\n")
        return metin if etiket in ilk else f"{ilk} · {etiket}{ayrac}{kalan}"          # hesap adı zaten yazılıysa (işlem mesajları) tekrar eklenmez
    return f"{ETIKET} {etiket}\n{metin}"


def baslikli(gonder):
    def g(metin, *a, **k):
        return gonder(etiket_ekle(metin, BASLIK), *a, **k)
    return g


def kur(durum_dizini: Path, alici: Optional[ck.KadroAlici] = None, esleme: Optional[dict] = None):
    """-> (alici, deposu, tanimlar). Ağ yok (çekim arka planda ayrıca başlatılır)."""
    esleme = esleme if esleme is not None else ck.esleme_yukle()
    alici = alici or ck.KadroAlici(Path(durum_dizini) / "ct_kadro")
    deposu = ck.KonsensusDeposu(alici, esleme)
    return alici, deposu, ck.tanimlar_olustur(esleme, deposu)


def surec_ici_yama(tg, tanimlar, gonder, servis_adi: str, motor=None) -> None:
    """CT ve aday hesabı süreçlerinin ORTAK süreç-içi yamaları (diske/başka sürece etkisi yok): tanımlar, (varsa) motor sınıfı, 10.000 USD ayarı,
    15m pencere 300 bar, Telegram başlıklı gönderici + servis adı. `aday_paper.hesap_calistir` de bunu kullanır."""
    pp.psg.tanimlari_yukle = lambda *a, **k: tanimlar
    if motor is not None:
        pp.PaperMotor = motor
    pp.paper_ayarlari = ct_ayarlari
    pp.PENCERE = {**pp.PENCERE, "15m": 300}
    tg.gonder = gonder
    tg.SERVIS_ADI = servis_adi


def calistir(durum_dizini: Path, tek_sefer: bool = False) -> int:
    from motor.canli import telegram as tg
    durum_dizini = Path(durum_dizini)
    durum_dizini.mkdir(parents=True, exist_ok=True)
    alici, deposu, tanimlar = kur(durum_dizini)
    alici.getir(zorla=True)                       # ilk çekim (hata yutulur); sonra arka plan (>= 5 dk aralık)
    alici.baslat_arka_plan()
    surec_ici_yama(tg, tanimlar, baslikli(tg.gonder), "ct_konsensus", motor=motor_sinifi(deposu))   # servis adı: birleşik başlangıç mesajı ve ortak bildirim anahtarları
    log.info("ct_konsensus başlıyor: %d sembol, durum %s, url %s", len(tanimlar), durum_dizini, alici.url)
    try:
        return pp.canli_calistir(durum_dizini, None, False, tek_sefer, set_modu="eski")
    finally:
        alici.durdur()


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="1L3A ct_konsensus paper hesabı (gerçek emir yok)")
    ap.add_argument("--durum", default=os.environ.get("L3A_CT_DURUM", VARSAYILAN_DURUM))
    ap.add_argument("--tek-sefer", action="store_true")
    ap.add_argument("--log", default="INFO")
    a = ap.parse_args(argv)
    logging.basicConfig(level=a.log, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    return calistir(Path(a.durum), a.tek_sefer)


if __name__ == "__main__":
    raise SystemExit(main())
