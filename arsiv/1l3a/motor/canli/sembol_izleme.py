"""Çalışırken sembol durumu izleme: saatte bir Binance exchangeInfo (herkese açık uç nokta, anahtarsız) okunur.

Bir strateji sembolü TRADING dışına düşerse (SETTLING, BREAK, delist...):
  - O sembolde YENİ giriş açılmaz (`PaperMotor.engelli_semboller` + bekleyen giriş emirleri silinir). Açık pozisyona dokunulmaz, zorla kapatma YOK
    (kapatma, yeniden başlatmadaki mevcut "askıda" mantığıyla/stop-hedefle olur).
  - Açık pozisyon yoksa WARN, varsa CRIT (Telegram; gizli hesap adı hiçbir mesajda yazmaz, yalnız sembol).
Sembol yeniden TRADING olursa girişler açılır, bir kez INFO gider. exchangeInfo hatası sessizce bir sonraki saate bırakılır.
Başlangıçtaki "evrenden düşürme" (paper._tanimlara_veri_yok_isle) aynen sürer; burada yalnız o turda TRADING olan semboller izlenir.
ct_paper ve aday_paper `paper.canli_calistir` kullandığı için aynı korumayı otomatik alır.
"""
from __future__ import annotations

import logging

import pandas as pd

from motor.canli import paper_veri as pv

log = logging.getLogger("paper.sembol_izleme")
ARALIK = pd.Timedelta(hours=1)


def _motorlar(p) -> list:
    h = getattr(p, "hesaplar", None)
    return [x.motor for x in h.values()] if h else [p.motor]


def acik_pozisyon_var(p, sembol: str) -> bool:
    """Herhangi bir hesapta bu strateji sembolünde açık (ya da askıdaki) pozisyon var mı."""
    for m in _motorlar(p):
        if any(q.sembol == sembol for q in m.acik.values()):
            return True
        if any(q.get("sembol") == sembol for q in (getattr(m, "askida", None) or {}).get("acik", {}).values()):
            return True
    return False


class SembolIzleyici:
    """`semboller`: izlenecek strateji sembolleri (başlangıçta TRADING olanlar). `bld`: telegram.Bildirimci (dedup + gönderim). `gonder`: yedek
    gönderici (bld yoksa). Mesaj biçimi `telegram.ust` ile standart ilk satır."""

    def __init__(self, p, ist, semboller, bld=None, gonder=None, sessiz: bool = False):
        self.p, self.ist = p, ist
        self.semboller = sorted(set(semboller))
        self.bld = bld
        self._gonder_fn = gonder
        self.sessiz = sessiz
        self.engelli: set = set()
        self.son: pd.Timestamp | None = None

    # ------------------------------------------------------------------ Telegram
    def _gonder(self, metin: str) -> bool:
        if self.sessiz:
            return False
        try:
            return bool((self.bld.gonder if self.bld is not None else self._gonder_fn)(metin))
        except Exception:  # noqa: BLE001
            log.exception("sembol izleme: telegram gönderilemedi")
            return False

    def _uyari_dedup(self, anahtar: str, metin: str) -> None:
        """WARN: Bildirimci'nin 6 saatlik kalıcı tekrar önlemesi."""
        if self.sessiz:
            return
        if self.bld is None:
            self._gonder(metin)
            return
        t = self.bld.saat()
        anahtar = f"{self.bld.servis}:{anahtar}"
        if self.bld.ortak.tekrar_var(anahtar, 6 * 3600, t):
            return
        self.bld.ortak.tekrar_isaretle(anahtar, t)
        self._gonder(metin)

    # ------------------------------------------------------------------ ana akış
    def kontrol(self, simdi) -> bool:
        """Saatte bir çağrılır (her turda çağrılabilir; zamanlayıcı içeride). Hata -> sessiz, sonraki saat. -> durum değişti mi."""
        simdi = pd.Timestamp(simdi)
        if not self.semboller or (self.son is not None and simdi - self.son < ARALIK):
            return False
        self.son = simdi                                    # başarısız olsa da bir sonraki saate bırakılır
        try:
            bilgi = self.ist.exchange_info()
            if not bilgi or not bilgi.get("symbols"):
                return False
            esl = pv.esleme_dogrula(bilgi, self.semboller)
        except Exception as e:  # noqa: BLE001
            log.info("sembol izleme: exchangeInfo alınamadı (%s: %s); sonraki saat", type(e).__name__, e)
            return False
        return self.uygula_durum({s: v[0] is not None for s, v in esl.items()}, simdi)

    def uygula_durum(self, tradingde: dict, simdi) -> bool:
        """{sembol: TRADING mi}. Geçişlere göre engel kümesini ve bildirimleri günceller."""
        degisti = False
        for s, ok in sorted(tradingde.items()):
            if not ok and s not in self.engelli:
                self.engelli.add(s)
                degisti = True
                self._kapandi(s, simdi)
            elif ok and s in self.engelli:
                self.engelli.discard(s)
                degisti = True
                self.p.olay_ekle("sembol_yeniden_acildi", f"{s} yeniden TRADING; yeni girişler açıldı", simdi, bildir=False)
                log.info("sembol yeniden işlemde (Telegram.a gitmez): %s", s)
        if degisti:
            self.uygula()
        return degisti

    def _ust(self, sev: str) -> str:
        from motor.canli import telegram as tg
        return tg.ust(sev)

    def _kapandi(self, s: str, simdi) -> None:
        if acik_pozisyon_var(self.p, s):
            msg = f"{s} borsada işleme kapandı, açık pozisyon var; yeni giriş yok, zorla kapatma yok (stop/hedef ya da askıda mantığı yönetir)"
            self.p.olay_ekle("sembol_islem_disi", msg, simdi, bildir=False)
            self._gonder(f"{self._ust('CRIT')} {msg}")                 # CRIT asla bastırılmaz
        else:
            self.p.olay_ekle("sembol_islem_disi", f"{s} borsada işleme kapandı, yeni giriş yok", simdi, bildir=False)
            self._uyari_dedup(f"sembol_kapandi:{s}", f"{self._ust('WARN')} {s} borsada işleme kapandı, yeni giriş yok")

    def uygula(self) -> None:
        """Her turda (adımdan önce ve sonra): engel kümesini motorlara yazar, engelli sembollerdeki bekleyen giriş emirlerini siler."""
        for m in _motorlar(self.p):
            m.engelli_semboller = self.engelli
            if not self.engelli:
                continue
            for kol in getattr(m, "tum_kollar", []):
                if kol.sembol in self.engelli:
                    kol.giris_emri = None


def kur(p, ist, semboller, bld=None, sessiz: bool = False) -> SembolIzleyici:
    return SembolIzleyici(p, ist, semboller, bld=bld, sessiz=sessiz)
