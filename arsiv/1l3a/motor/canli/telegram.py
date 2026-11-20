"""Telegram bildirimleri (sg-arge `copytrade/canli/telegram.py` uyarlaması): metin üretimi + gönderim.

Token ve chat_id YALNIZ ortam değişkenlerinden okunur: TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID (systemd EnvironmentFile; repoya girmez).
Biri yoksa HİÇBİR ŞEY GÖNDERİLMEZ ve bu loglanır (hata değil, açık bilgi). Gönderim hatası loglanır ve False döner; motoru durdurmaz.
parse_mode=HTML: dinamik her metin html.escape'lidir. Mesaj 3500 karakteri aşmaz (satır sınırında kısaltılır).
Standart (docs/standart/telegram-standardi.md): ilk satır "[1L3A] INFO|WARN|CRIT ..." (önem düzeyi + proje etiketi); INFO sessiz gider;
dakikada en çok 15 mesaj (aşan INFO atılır, WARN/CRIT her zaman gider); aynı metin 10 dk içinde bir kez. Komutlar: telegram_komut.py.
Telegram YENİ HESAP YAPMAZ: sayılar durum alanlarından aynen gelir, burada yalnız biçimlenir (tek istisna: işlem mesajında
tutar = fiyat x miktar ve K/Z % = net / giriş tutarı, durumdaki `kz_oran` ile aynı tanım).
Teknik olaylar (WS bağlandı/koptu, yeniden başlatma...) kullanıcıya GİTMEZ (yalnız log/olaylar.jsonl); `Bildirimci` yalnız sorun
sürerse tek uyarı verir ve aynı türden mesajı 30 dk içinde tekrarlamaz.
"""
from __future__ import annotations

import fcntl
import hashlib
import html
import json
import logging
import os
import re
import time
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path
from decimal import Decimal, InvalidOperation
from typing import Callable, Optional
from zoneinfo import ZoneInfo

from motor.canli import hesap_adlari as hg

log = logging.getLogger("paper.telegram")
TOKEN_ENV, CHAT_ENV = "TELEGRAM_BOT_TOKEN", "TELEGRAM_CHAT_ID"
MAKS = 3500                         # standart: mesaj başına en çok 3500 karakter
PROJE_ETIKETI = "[1L3A]"
DAKIKA_SINIRI = 15
TEKRAR_PENCERE_SN = 600
EN_AZ_ARALIK_SN = 1.0                # iki mesaj arası alt sınır (Telegram: sohbet başına ~1 mesaj/sn)
_son_gonderim = [0.0]
_pencere: list = []                  # son 60 sn'de gönderilen mesaj zamanları (hız sınırı)
_son_metin: dict = {}                # {metin özeti: zaman} tekrar önleme
_SEV_KALIBI = re.compile(r"\b(INFO|WARN|CRIT)\b")
_yok_loglandi = [False]
TEKRAR_UYARI_SN = 6 * 3600           # aynı uyarı anahtarı en çok 6 saatte bir (kalıcı; yeniden başlatmaya dayanıklı). CRIT hiç bastırılmaz
BASLANGIC_PENCERE_SN = 60            # yeniden başlatma mesajlarını birleştirme penceresi (ilk kayıttan itibaren)
BILGI_ARALIK_SN = 3600               # işlemi etkilemeyen bilgi satırları en çok saatte bir TEK mesajda
ORTAK_ENV = "L3A_ORTAK_BILDIRIM"     # servisler arası ortak durum dizini (varsayılan: paper StateDirectory altı)
ORTAK_VARSAYILAN = "/var/lib/1l3a-paper/ortak_bildirim"
SERVIS_ADI = "paper"                 # ct_paper / aday_paper süreç başında değiştirir (birleşik başlangıç mesajında ad)


def yapilandirma(env=None) -> Optional[tuple]:
    env = os.environ if env is None else env
    token, chat = env.get(TOKEN_ENV, "").strip(), env.get(CHAT_ENV, "").strip()
    if not token or not chat:
        return None
    return token, chat


_TOKEN_KALIBI = re.compile(r"(bot)?\d{5,}:[A-Za-z0-9_-]{20,}")


def maskele(metin: str, token: Optional[str] = None) -> str:
    """Metindeki Telegram bot token'ını (verilen token ve 'bot<id>:<gizli>' kalıbı) '***' ile değiştirir. Log/olay metinleri için."""
    metin = str(metin)
    if token:
        metin = metin.replace(token, "***")
    y = yapilandirma()
    if y and y[0]:
        metin = metin.replace(y[0], "***")
    return _TOKEN_KALIBI.sub(lambda m: (m.group(1) or "") + "***", metin)


def kirp(metin: str) -> str:
    """4096 sınırı: aşarsa son tam satırda keser (etiketler satır içinde kapalı olduğundan HTML bozulmaz)."""
    if len(metin) <= MAKS:
        return metin
    kes = metin[:MAKS - 1]
    n = kes.rfind("\n")
    return (kes[:n] if n > MAKS // 2 else kes) + "…"


def onem(metin: str) -> str:
    """İlk satırdaki önem düzeyi (INFO/WARN/CRIT); yoksa INFO."""
    ilk = str(metin).split("\n", 1)[0]
    if not ilk.startswith(PROJE_ETIKETI):
        return "INFO"
    govde = ilk[len(PROJE_ETIKETI):].lstrip()
    if govde.startswith(SEV_EMOJI["CRIT"]):                 # seviye kelimesi yok: 🔴 kritik, ⚠️ uyarı, emojisiz INFO (sessiz)
        return "CRIT"
    if govde.startswith(SEV_EMOJI["WARN"][0]):
        return "WARN"
    m = _SEV_KALIBI.search(ilk)                              # eski biçim ("[1L3A] WARN ...") okunmaya devam eder
    return m.group(1) if m else "INFO"


def etiketli(metin: str) -> str:
    """Standart ilk satır yoksa (örn. canlı yürütücünün "🔴 1L3A CANLI" mesajları) üstüne "[1L3A] WARN|CRIT" satırı eklenir (🔴/🚨 = CRIT)."""
    metin = str(metin)
    if metin.startswith(PROJE_ETIKETI):
        return metin
    return ust("CRIT" if ("🔴" in metin or "🚨" in metin) else "WARN") + "\n" + metin


MAKS_SATIR, MAKS_SATIR_OZET = 6, 12


def satir_sinirla(metin: str, maks: int = MAKS_SATIR) -> str:
    """En çok `maks` satır (fazlası atılır). Özet ("özet" ilk satırda) 12 satıra kadar."""
    satirlar = str(metin).split("\n")
    if "özet" in satirlar[0].lower():
        maks = max(maks, MAKS_SATIR_OZET)
    return "\n".join(satirlar[:maks])


def gonder(metin: str, env=None, oturum=None, uyku=time.sleep, saat=time.monotonic, seviye: Optional[str] = None) -> bool:
    """`seviye` (INFO|WARN|CRIT) verilirse metindeki işaretin yerine geçer: INFO sessiz (disable_notification), WARN/CRIT sesli.
    True: Telegram'a iletildi. False: yapılandırma yok (loglanır), hız sınırı/tekrar nedeniyle atıldı ya da gönderim hatası (loglanır)."""
    y = yapilandirma(env)
    if y is None:
        if not _yok_loglandi[0]:
            log.warning("Telegram devre dışı: %s / %s ortam değişkenleri tanımlı değil; mesaj gönderilmiyor", TOKEN_ENV, CHAT_ENV)
            _yok_loglandi[0] = True
        log.info("telegram (gönderilmedi): %s", metin[:120].replace("\n", " | "))
        return False
    import requests
    token, chat = y
    metin = satir_sinirla(etiketli(metin))
    sev = seviye if seviye in ("INFO", "WARN", "CRIT") else onem(metin)
    simdi = saat()
    anahtar = hash(str(metin))
    ortak = tekrar_anahtari = None
    if sev == "INFO" and anahtar in _son_metin and simdi - _son_metin[anahtar] < TEKRAR_PENCERE_SN:   # INFO: aynı metin 10 dk içinde bir kez
        log.info("telegram (tekrar, atlandı): %s", metin[:80].replace("\n", " | "))
        return False
    if sev == "WARN":                                                                   # WARN: aynı metin 6 saatte bir (kalıcı); CRIT asla bastırılmaz
        ortak, tekrar_anahtari = ortak_durum(), "gonder:" + hashlib.sha1(metin.encode("utf-8")).hexdigest()[:16]
        if ortak.tekrar_var(tekrar_anahtari, TEKRAR_UYARI_SN, time.time()):
            log.info("telegram (tekrar, atlandı): %s", metin[:80].replace("\n", " | "))
            return False
    _pencere[:] = [t for t in _pencere if simdi - t < 60]
    if len(_pencere) >= DAKIKA_SINIRI and sev == "INFO":                                 # hız sınırı: dakikada <= 15; aşan INFO atılır
        log.warning("telegram hız sınırı: INFO mesaj atıldı: %s", metin[:80].replace("\n", " | "))
        return False
    gec = simdi - _son_gonderim[0]
    if gec < EN_AZ_ARALIK_SN:
        uyku(EN_AZ_ARALIK_SN - gec)
    try:
        r = (oturum or requests).post(f"https://api.telegram.org/bot{token}/sendMessage",
                                      data={"chat_id": chat, "text": kirp(metin), "parse_mode": "HTML",
                                            "disable_web_page_preview": "true",
                                            "disable_notification": "true" if sev == "INFO" else "false"}, timeout=15)
    except Exception as e:  # noqa: BLE001  (ağ hatası loglanır; motor durmaz)
        # repr/str istek URL'sini (içinde bot token'ı) taşır: yalnız tür adı + MASKELİ metin loglanır (journal'a token düşmesin)
        log.error("Telegram gönderim ağ hatası: %s: %s", type(e).__name__, maskele(str(e), token))
        return False
    _son_gonderim[0] = saat()
    if r.status_code != 200:
        log.error("Telegram gönderim başarısız: HTTP %s %s", r.status_code, maskele(r.text[:200], token))
        return False
    _pencere.append(simdi)
    _son_metin[anahtar] = simdi
    gonderim_kaydet(metin, sev, env)
    if ortak is not None:
        ortak.tekrar_isaretle(tekrar_anahtari, time.time())
    if len(_son_metin) > 500:
        for k in [k for k, t in _son_metin.items() if simdi - t >= TEKRAR_PENCERE_SN]:
            _son_metin.pop(k, None)
    return True


GONDERIM_DOSYA = "telegram_gonderim.jsonl"
GONDERIM_MAKS_BAYT = 1_000_000       # aşınca .1'e döndürülür (en çok ~2 MB)
GONDERIM_ENV = "L3A_TELEGRAM_GONDERIM_DIZIN"


def gonderim_dizini(env=None) -> Optional[Path]:
    """Başarılı gönderim kaydının dizini: L3A_TELEGRAM_GONDERIM_DIZIN, yoksa ortak bildirim dizini (servisler arası paylaşılır). Yoksa None."""
    env = os.environ if env is None else env
    d = env.get(GONDERIM_ENV, "").strip()
    if d:
        return Path(d)
    o = ortak_durum(env)
    return o.dizin if o.dosya_ok else None



def api_istek(token: str, yontem: str, oturum=None, **kw):
    """Bot API'ye POST (URL yalnız bu modülde; token koda girmez). Diğer modüllerin özel gönderimleri (ör. strateji_verisi belge) bunu kullanır."""
    if oturum is None:
        import requests as oturum
    return oturum.post(f"https://api.telegram.org/bot{token}/{yontem}", **kw)


def gonderim_kaydet(metin: str, sev: str, env=None) -> None:
    """Başarılı gönderimi {zaman, ilk_satir, seviye} olarak ekler (mutabakat için; hesap adı mesajda zaten gizlidir). Hata motoru etkilemez."""
    try:
        d = gonderim_dizini(env)
        if d is None:
            return
        d.mkdir(parents=True, exist_ok=True)
        yol = d / GONDERIM_DOSYA
        if yol.exists() and yol.stat().st_size > GONDERIM_MAKS_BAYT:
            os.replace(yol, yol.with_name(GONDERIM_DOSYA + ".1"))
        satir = {"zaman": datetime.now(ZoneInfo("UTC")).strftime("%Y-%m-%dT%H:%M:%SZ"), "ilk_satir": str(metin).split("\n", 1)[0][:300], "seviye": sev}
        with open(yol, "a", encoding="utf-8") as f:
            f.write(json.dumps(satir, ensure_ascii=False) + "\n")
    except Exception:  # noqa: BLE001
        log.debug("telegram gönderim kaydı yazılamadı", exc_info=True)


ham_gonder = gonder                 # ct_paper/aday_paper `telegram.gonder`i başlıklı sürümle değiştirir; birleşik/saatlik mesajlar bunu kullanır


# ---------------------------------------------------------------------------- ortak durum (servisler arası: tekrar önleme, birleşik başlangıç, saatlik bilgi)
class OrtakDurum:
    """Tek JSON + flock: ayrı systemd servisleri (paper / ct_konsensus / aday) aynı dosyayı güvenle paylaşır. dizin None: yalnız bellek (tek süreç).
    Yazılamazsa sessizce belleğe düşer (bildirim motoru asla durdurmaz). Anahtarlar: tekrar {anahtar: epoch}, bir_kez [anahtar],
    baslangic {bas, kayitlar{servis: {...}}}, bilgi {satirlar, son}."""

    def __init__(self, dizin=None):
        self.dizin, self.bellek, self.dosya_ok = (Path(dizin) if dizin else None), {}, False
        if self.dizin is not None:
            try:
                self.dizin.mkdir(parents=True, exist_ok=True)
                self._izin(self.dizin, 0o700)
                self._kilit, self._dosya = self.dizin / "kilit", self.dizin / "durum.json"
                self._kilit.touch()
                self._izin(self._kilit, 0o600)
                self.dosya_ok = True
            except OSError as ex:
                log.warning("ortak bildirim durumu açılamadı (%s); yalnız bellek: %s", type(ex).__name__, self.dizin)

    def _izin(self, yol, mod) -> None:
        """Yalnız sahibi yazar/okur (0700/0600): başka kullanıcı sahte Telegram mesajı sokamaz. Süreç root ise sahiplik üst dizinin sahibine (l3a) verilir,
        böylece servisler sonradan da yazabilir. Hata motoru etkilemez."""
        try:
            os.chmod(yol, mod)
            if os.geteuid() == 0:
                st = os.stat(self.dizin.parent)
                os.chown(yol, st.st_uid, st.st_gid)
        except OSError:
            pass

    @contextmanager
    def _acik(self):
        if not self.dosya_ok:
            yield self.bellek
            return
        with open(self._kilit, "a+") as k:
            fcntl.flock(k, fcntl.LOCK_EX)
            try:
                d = json.loads(self._dosya.read_text(encoding="utf-8"))
                d = d if isinstance(d, dict) else {}
            except (OSError, ValueError):
                d = {}
            yield d
            tmp = self._dosya.with_name(f".durum.json.tmp-{os.getpid()}")
            tmp.write_text(json.dumps(d, ensure_ascii=False), encoding="utf-8")
            self._izin(tmp, 0o600)
            os.replace(tmp, self._dosya)

    def _islem(self, fn, varsayilan=None):
        try:
            with self._acik() as d:
                return fn(d)
        except Exception as ex:  # noqa: BLE001  (durum dosyası bildirimi/motoru asla düşürmez)
            log.warning("ortak bildirim durumu hatası: %s", type(ex).__name__)
            return varsayilan

    def tekrar_var(self, anahtar: str, aralik: float, simdi: float) -> bool:
        """True: bu anahtar `aralik` sn içinde zaten gönderildi (bastır)."""
        return bool(self._islem(lambda d: simdi - float((d.get("tekrar") or {}).get(anahtar, -1e18)) < aralik, False))

    def tekrar_isaretle(self, anahtar: str, simdi: float) -> None:
        def f(d):
            t = d.setdefault("tekrar", {})
            t[anahtar] = simdi
            for k in [k for k, v in t.items() if simdi - float(v) > 7 * 86400]:
                t.pop(k, None)
        self._islem(f)

    def bir_kez(self, anahtar: str) -> bool:
        """True: ilk kez görüldü (kalıcı işaretlenir); sonraki çağrılar False (yeniden başlatmada da tekrar yok)."""
        def f(d):
            l = d.setdefault("bir_kez", [])
            if anahtar in l:
                return False
            l.append(anahtar)
            return True
        return bool(self._islem(f, True))

    def bayrak_koy(self, anahtar: str) -> None:
        """Kalıcı bayrak (yeniden başlatmaya dayanıklı): örn. "bot hata/durdu verdi, düzelince tek 'Düzeldi' gider"."""
        self._islem(lambda d: d.setdefault("bayrak", {}).__setitem__(anahtar, True))

    def bayrak_al(self, anahtar: str) -> bool:
        """True: bayrak vardı ve KALDIRILDI (tek sefer)."""
        return bool(self._islem(lambda d: bool(d.setdefault("bayrak", {}).pop(anahtar, False)), False))

    def baslangic_kaydet(self, servis: str, kayit: dict, simdi: float) -> None:
        def f(d):
            b = d.setdefault("baslangic", {"bas": None, "kayitlar": {}})
            if b.get("bas") is None:
                b["bas"] = simdi
            b["kayitlar"][servis] = kayit
        self._islem(f)

    def baslangic_al(self, simdi: float, pencere: float = BASLANGIC_PENCERE_SN, zorla: bool = False) -> Optional[list]:
        """Pencere dolduysa (ilk kayıttan `pencere` sn sonra) birikmiş kayıtları verir ve sıfırlar (tek süreç alır: kilit altında)."""
        def f(d):
            b = d.get("baslangic")
            if not b or b.get("bas") is None or not b.get("kayitlar") or (not zorla and simdi - float(b["bas"]) < pencere):
                return None
            k = [dict(v, servis=s) for s, v in sorted(b["kayitlar"].items())]
            d["baslangic"] = {"bas": None, "kayitlar": {}}
            return k
        return self._islem(f)

    def bilgi_ekle(self, satir: str, simdi: float, tekrar_sn: float = TEKRAR_UYARI_SN, tekrarli: bool = True) -> bool:
        def f(d):
            if tekrarli:
                t = d.setdefault("tekrar", {})
                k = "bilgi:" + hashlib.sha1(satir.encode("utf-8")).hexdigest()[:16]
                if simdi - float(t.get(k, -1e18)) < tekrar_sn:
                    return False
                t[k] = simdi
            b = d.setdefault("bilgi", {"satirlar": [], "son": -1e18})   # hiç gönderilmediyse: ilk satır hemen gider
            b["satirlar"] = (b["satirlar"] + [satir])[-30:]
            return True
        return bool(self._islem(f, False))

    def bilgi_al(self, simdi: float, aralik: float = BILGI_ARALIK_SN) -> Optional[list]:
        def f(d):
            b = d.get("bilgi")
            if not b or not b.get("satirlar") or simdi - float(b.get("son", -1e18)) < aralik:
                return None
            k = list(b["satirlar"])
            d["bilgi"] = {"satirlar": [], "son": simdi}
            return k
        return self._islem(f)


_ortak_onbellek: dict = {}


def ortak_durum(env=None) -> OrtakDurum:
    """Ortak durum: L3A_ORTAK_BILDIRIM ya da (varsa) /var/lib/1l3a-paper/ortak_bildirim; yoksa süreç içi bellek (geliştirme/test)."""
    env = os.environ if env is None else env
    d = env.get(ORTAK_ENV, "").strip() or (ORTAK_VARSAYILAN if Path(ORTAK_VARSAYILAN).parent.is_dir() else "")
    if d not in _ortak_onbellek:
        _ortak_onbellek[d] = OrtakDurum(d or None)
    return _ortak_onbellek[d]


# ---------------------------------------------------------------------------- biçim yardımcıları
TSI = ZoneInfo("Europe/Istanbul")
AYLAR = ["Ocak", "Şubat", "Mart", "Nisan", "Mayıs", "Haziran", "Temmuz", "Ağustos", "Eylül", "Ekim", "Kasım", "Aralık"]
ETIKET = "1L3A"


SEV_EMOJI = {"CRIT": "🔴", "WARN": "⚠️"}                     # INFO: emoji yok, sessiz bildirim


def ust(sev: str = "INFO") -> str:
    """Standart ilk satır başı: proje etiketi (INFO'da seviye kelimesi yok) + WARN/CRIT işareti."""
    return PROJE_ETIKETI if sev == "INFO" else f"{PROJE_ETIKETI} {SEV_EMOJI[sev]}"


ETIKET_SATIRI = ust("INFO")
# final_set.json'daki 7 strateji; bilinmeyen kimlikte kimliğin kendisi gösterilir.
AD = hg.AD                                      # kimlik -> okunur ad haritası (tek kaynak: hesap_adlari.py)
NEDEN_TR = {"stop": "stop çalıştı", "hedef": "hedefe ulaştı", "kismi": "kısmi çıkış", "kismi_tam": "kısmi çıkışlar tamamlandı",
            "veri_sonu": "veri sonu", "sinyal": "sinyal kapandı", "hedef_sifir": "sinyal kapandı", "yon_degisim": "sinyal yön değiştirdi",
            "kucultme": "pozisyon küçültüldü", "kill_switch": "kill switch", "gunluk_limit": "günlük kayıp limiti",
            "gunluk_kayip_limiti": "günlük kayıp limiti", "isinma": "ısınma dönemi"}
TEKNIK = {"ws_baglandi", "ws_yeniden_baglandi", "ws_koptu", "ws_24sa_yenileme", "yeniden_baslatma", "veri_uyusmazlik", "gec_bar"}


def ad(kimlik: str) -> str:
    """Kimlik -> okunur ad (hesap_adlari.okunur_ad: AD haritası, yoksa gövdeden üretilir; hiçbir zaman "_" içermez).
    Gizli hesap adı buraya gelmez (çağıranlar gizliyi "Diğer hesaplar (N)" yazar)."""
    return hg.okunur_ad(kimlik)


def e(x) -> str:
    return html.escape(str(x), quote=False)


def _ondalik(x) -> Optional[Decimal]:
    try:
        return None if x is None else Decimal(str(x))
    except (InvalidOperation, ValueError):
        return None


def tr_sayi(x, ondalik: int = 2) -> str:
    """1234.5 -> '1.234,50'."""
    return f"{x:,.{ondalik}f}".replace(",", "X").replace(".", ",").replace("X", ".")


def usd(x, isaretli: bool = False, ondalik: int = 2) -> str:
    """'1234.5' -> '1.234,50 $' (isaretli: '+1.234,50 $'); yok -> '—'."""
    v = _ondalik(x)
    if v is None:
        return "—"
    s = tr_sayi(abs(v), ondalik)
    isaret = ("−" if v < 0 else "+") if isaretli else ("−" if v < 0 else "")
    if isaretli and v == 0:
        isaret = "+"
    return f"{isaret}{s} $"


def yuzde(oran, isaretli: bool = True, ondalik: int = 2) -> str:
    """0.0125 -> '+%1,25'; isaretsiz '%1,25'."""
    v = _ondalik(oran)
    if v is None:
        return "—"
    s = "%" + tr_sayi(abs(v) * 100, ondalik)
    return (("−" if v < 0 else "+") + s) if isaretli else s


def fiyat(x) -> str:
    """Fiyat: büyüklüğe göre ondalık, gereksiz sıfırlar atılır (en az 2 ondalık)."""
    v = _ondalik(x)
    if v is None:
        return "—"
    n = 2 if abs(v) >= 1000 else 4 if abs(v) >= 1 else 6
    s = tr_sayi(v, n)
    ana, _, ond = s.partition(",")
    return ana + "," + (ond.rstrip("0").ljust(2, "0"))


def _tsi(zaman) -> datetime:
    z = datetime.fromisoformat(str(zaman).replace("Z", "+00:00"))
    return z.astimezone(TSI)


def tsi_saat(zaman) -> str:
    return _tsi(zaman).strftime("%d.%m %H:%M")


def tsi_gun(zaman) -> str:
    t = _tsi(zaman)
    return f"{t.day} {AYLAR[t.month - 1]}"


def _tr_ondalik(metin: str) -> str:
    """Motorun serbest metinlerindeki '%12.34' -> '%12,34'."""
    return re.sub(r"(%\d+)\.(\d+)", r"\1,\2", metin)


def _serbest(metin: str) -> str:
    """Motor/uyarı metni: kimlikler okunur ada çevrilir, sayı Türkçeleşir, HTML kaçışlanır."""
    for k in sorted(AD, key=len, reverse=True):
        metin = metin.replace(k, AD[k])
    metin = re.sub(r"[\w.-]+\|[\w.]+\|\d+[mhdw]\b", lambda m: ad(m.group(0)), metin)      # "ct_konsensus|BTCUSDT|15m" -> "CT konsensüs · BTC · 15 dk"
    return e(_tr_ondalik(metin))


def _em(yon: str) -> str:
    return "🟢" if yon == "long" else "🟠"             # 🔴 yalnız kritik uyarı içindir


def _yon(yon: str) -> str:
    return f"{_em(yon)} {'long' if yon == 'long' else 'short'}"


# ---------------------------------------------------------------------------- mesajlar (hepsi durum dosyasındaki sayılardan)
def baslangic_metni(strateji_sayisi: int, kasa) -> str:
    return f"{ust('INFO')}\n▶️ <b>Paper motoru çalışıyor</b> · {strateji_sayisi} strateji · kasa {usd(kasa, ondalik=0)}"


def _servis_adi(servis: str) -> str:
    return "Paper motoru" if servis == "paper" else servis


def baslangic_birlesik_metni(kayitlar: list) -> str:
    """Birlikte (pencere içinde) yeniden başlayan servisler TEK mesaj. Hesap adı yok; yalnız servis adı, strateji sayısı, kasa."""
    if len(kayitlar) == 1:
        k = kayitlar[0]
        return f"{ust('INFO')}\n▶️ <b>{e(_servis_adi(k['servis']))} çalışıyor</b> · {k['n']} strateji · kasa {k['kasa']}"
    g = [ust("INFO"), f"▶️ <b>{len(kayitlar)} servis çalışıyor</b>"]
    g += [f"• {e(_servis_adi(k['servis']))}: {k['n']} strateji · kasa {k['kasa']}" for k in kayitlar[:20]]
    return kirp("\n".join(g))


def baslangic_kaydet(strateji_sayisi: int, kasa, birlestir: bool = True, ortak: Optional[OrtakDurum] = None, saat=time.time) -> bool:
    """Servis başlangıcı: birleştirilebilirse ortak duruma yazar (Bildirimci.kontrol pencere dolunca TEK mesaj yollar); değilse hemen gönderir."""
    """Telegram'a GİTMEZ (rutin 'servis başladı'): yalnız log. Ortak duruma da yazılmaz; birleşik başlangıç mesajı artık yok."""
    log.info("servis başladı (Telegram'a gitmez): %s", baslangic_metni(strateji_sayisi, kasa).replace("\n", " | "))
    return False


def bilgi_metni(satirlar: list) -> str:
    """Saatlik not: işlemi etkilemeyen bilgi satırları tek INFO mesajında."""
    return kirp("\n".join([ust("INFO"), f"ℹ️ <b>Saatlik not</b> ({len(satirlar)})"] + [f"• {_serbest(x)}" for x in satirlar]))


def bilgi_ekle(satir: str, ortak: Optional[OrtakDurum] = None, saat=time.time) -> bool:
    """İşlemi etkilemeyen bilgi: Telegram'a GİTMEZ (saatlik not kalktı), yalnız log."""
    log.info("bilgi (Telegram'a gitmez): %s", str(satir)[:200])
    return False


NEDEN_KISA = {"stop": "stop", "hedef": "kâr al", "kismi": "kısmi kâr al", "kismi_tam": "kısmi kâr al", "veri_sonu": "süre doldu",
              "sinyal": "sinyal kapandı", "hedef_sifir": "sinyal kapandı", "yon_degisim": "yön değişti", "kucultme": "küçültüldü",
              "kill_switch": "güvenlik freni", "gunluk_limit": "günlük kayıp limiti", "gunluk_kayip_limiti": "günlük kayıp limiti",
              "isinma": "ısınma dönemi"}


def _para0(x) -> str:
    v = _ondalik(x)
    return "—" if v is None else usd(v, ondalik=0 if v == v.to_integral_value() else 2)


def islem_acildi_metni(poz: dict, gorunur: bool = True) -> str:
    """2 satır. "[1L3A] 🟢 SOL long açıldı · <hesap>" / "Giriş 152,30 $ · Tutar 500 $ · Stop 148,10 $". INFO: sessiz gider.
    Hesap adı hesap_adlari.hesap_adi (pano ile aynı); gizli hesap "Diğer hesap"."""
    yon = "long" if poz["yon"] == "long" else "short"
    return (f"{ETIKET_SATIRI} {_em(poz['yon'])} {e(hg.coin_adi(poz['sembol']))} {yon} açıldı · {e(hg.hesap_adi(poz['kimlik'], gorunur))}\n"
            f"Giriş {fiyat(poz['giris_fiyati'])} $ · Tutar {_para0(poz.get('nominal'))} · Stop {fiyat(poz.get('stop'))} $")


def islem_kapandi_metni(satir: dict, gorunur: bool = True) -> str:
    """2 satır. "[1L3A] ✅|🔻 SOL long kapandı · <hesap>" / "−12,40 $ (−%2,5) · stop". `paper_durum._islem_satiri` çıktısından. INFO: sessiz gider."""
    net = _ondalik(satir["net_pnl_yerel"])
    kar = net is not None and net > 0
    giris, miktar = _ondalik(satir.get("giris_fiyati")), _ondalik(satir.get("miktar"))
    tutar = giris * miktar if giris is not None and miktar is not None else None      # biçimlendirme türevi
    oran = net / tutar if net is not None and tutar else None
    yon = "long" if satir["yon"] == "long" else "short"
    neden = NEDEN_KISA.get(satir["cikis_nedeni"], str(satir["cikis_nedeni"]).replace("_", " "))
    return (f"{ETIKET_SATIRI} {'✅' if kar else '🔻'} {e(hg.coin_adi(satir['sembol']))} {yon} kapandı · {e(hg.hesap_adi(satir['kimlik'], gorunur))}\n"
            f"{usd(net, True)} ({yuzde(oran, True, 1)}) · {e(neden)}")


islem_metni = islem_kapandi_metni


def ozet_metni(o: dict, dun: Optional[dict] = None, itibaren: Optional[str] = None, diger: Optional[tuple] = None) -> str:
    """paper_durum.olustur çıktısından günlük özet (pano ile aynı dosyalar/sayılar), EN ÇOK 12 satır. INFO: sessiz gider.
    dun: {gun: 'YYYY-MM-DD' (TSİ), pnl, getiri, not} verilirse özet BİTEN TSİ gününü anlatır (başlık o gün; 'Dün').
    itibaren: 'HH:MM' verilirse başlığa "(HH:MM itibarıyla)" eklenir: gün içi kısmi özet (standart: günlük rapor 21:00 TSİ)."""
    oz, st, sg = o["ozet"], o["stratejiler"]["stratejiler"], o["saglik"]
    r = oz["risk"]
    if dun is not None:
        g = datetime.strptime(dun["gun"], "%Y-%m-%d")
        baslik = f"{g.day} {AYLAR[g.month - 1]} {g.year}"
        gun_satiri = f"📅 Dün: {usd(dun['pnl'], True)} ({yuzde(dun.get('getiri'))})" + (f" · {e(dun['not'])}" if dun.get("not") else "")
    else:
        baslik = tsi_gun(oz['zaman'])
        gun_satiri = f"📅 Bugün: {usd(oz['gun_pnl'], True)} ({yuzde(oz.get('gun_getiri'))})"
    if itibaren:
        baslik += f" ({itibaren} itibarıyla)"
    s = [f"{ETIKET_SATIRI} 📊 <b>Günlük özet — {e(baslik)}</b>",
         f"💰 Kasa <b>{usd(oz['ozsermaye'])}</b> · {gun_satiri}",
         f"📈 Başlangıçtan beri {usd(oz['toplam_pnl'], True)} ({yuzde(oz['toplam_getiri'])}) · zirveden düşüş {yuzde(oz['zirveden_dusus'], False)}",
         f"🛡 Günlük kayıp {yuzde(r['gunluk_kayip']['deger'], False, 1)} / sınır {yuzde(r['gunluk_kayip']['limit'], False, 0)}"]
    if diger and diger[1] is not None:                      # gizli hesaplar adsız tek satır (hesap_adlari.DIGER_HESAPLAR)
        s.append(f"👥 {hg.DIGER_HESAPLAR} ({diger[0]}): toplam {usd(diger[1], True)}")
    acik = [(x, p) for x in st for p in x["acik_pozisyonlar"]]
    if acik:
        s.append(f"📂 Açık {len(acik)}: " + " · ".join(f"{_em(p['yon'])} {e(hg.coin_adi(p['sembol']))} {usd(p['kz'], True)}" for _, p in acik[:3])
                 + (f" (+{len(acik) - 3})" if len(acik) > 3 else ""))
    else:
        s.append("📂 Açık pozisyon yok")
    aktif = [x for x in st if x["durum"] == "calisiyor" and (x["islem_sayisi"] or _ondalik(x["ozsermaye_katkisi"]) != 0)]
    if aktif:
        iyi = max(aktif, key=lambda x: _ondalik(x["ozsermaye_katkisi"]))
        kotu = min(aktif, key=lambda x: _ondalik(x["ozsermaye_katkisi"]))
        s.append(f"🧩 En iyi {e(ad(iyi['kimlik']))} {usd(iyi['ozsermaye_katkisi'], True)} · en kötü {e(ad(kotu['kimlik']))} {usd(kotu['ozsermaye_katkisi'], True)}")
    uy = []
    for u in sg["uyarilar"][:4]:
        uy.append(f"{'🚨' if 'BEKLENTİ ALARMI' in u else '⚠️'} {_serbest(u)[:140]}")
    if sg["durum"] != "ok":
        uy.append(f"⚠️ Durum: <b>{e(DURUM_TR.get(sg['durum'], sg['durum']))}</b>")
    s += uy[:max(0, MAKS_SATIR_OZET - len(s))]
    return kirp("\n".join(s))
DURUM_TR = {"kill_switch": "kill switch devrede", "veri_bayat": "veri bayat", "uyari": "uyarı var"}

# tür -> (emoji, başlık, ne yapılıyor, senden bir şey gerekiyor mu). Sıra: Ne oldu -> Ne yapılıyor -> Senden bir şey gerekiyor mu. Kod/servis/dosya adı yok.
UYARI = {"kill_switch": ("🚨", "Güvenlik freni devrede: tüm işlemler durdu", "Açık pozisyonlar kapatıldı, yeni işlem açılmıyor.", "Evet: panoya bakıp karar vermeden yeniden başlatma."),
         "gunluk_limit": ("⚠️", "Günlük kayıp limiti doldu", "Açık pozisyonlar kapatıldı, bugün yeni işlem açılmıyor; yarın otomatik devam eder.", "Hayır."),
         "veri_bosluk": ("⚠️", "Veri sorunu", "İlgili sembolde işlem durabilir.", "Sürerse panoda veri durumuna bak."),
         "veri_yok": ("⚠️", "Veri yok", "Bu strateji çalışmıyor.", "Panoda veri durumuna bak."),
         "binance_hata": ("⚠️", "Borsa bağlantı hatası", "Bot kendisi yeniden deniyor.", "30 dakika sürerse sunucuyu kontrol et."),
         "ayar_yenileme": ("⚠️", "Ayar yenileme zamanı", "Önerilen ayar hazır, onayın olmadan uygulanmaz.", "Evet: öneriyi incele."),
         "beklenti_alarmi": ("🚨", "Strateji beklentinin altında", "Strateji izleniyor.", "Panoda ilgili stratejiye bak."),
         "ws_sorunu": ("⚠️", "Canlı veri bağlantısı sorunlu", "Bot yeniden bağlanmayı deniyor.", "Sürerse sunucuyu kontrol et."),
         "motor_hatasi": ("🚨", "Bot hata verdi", "Kayıtlı son noktadan devam etmeyi deniyor; aynı hata 5 kez olursa durur.", "Sürerse sunucuyu kontrol et (ayrıntı kayıtta)."),
         "motor_durdu": ("🚨", "Bot durdu", "Sistem kendiliğinden yeniden başlatır.", "Düzelmezse sunucuyu kontrol et."),
         "askida": ("⚠️", "Strateji askıda", "Sembol verisi yok; durumu korunuyor, emir verilmiyor.", "Panoda veri durumuna bak."),
         "askida_kapatma": ("🚨", "Askıdaki pozisyon limitte kapatıldı", "Son bilinen fiyattan kapatıldı.", "Evet: bakiyeyi ve sembol verisini kontrol et."),
         "giris_durduruldu": ("⚠️", "Yeni girişler durduruldu", "Açık pozisyonlar kendi stop/hedefiyle sürer.", "Açmak için /devam yaz."),
         "hepsini_kapat": ("🛑", "Hepsini kapat uygulandı", "Açık pozisyonlar kapatıldı, yeni girişler durdu (canlı modda borsadakiler de).", "Evet: borsa ekranından kontrol et."),
         "giris_devam": ("▶️", "Yeni girişler yeniden açıldı", "Bot normal çalışıyor.", "Hayır."),
         "servis_hatasi": ("🚨", "Bir servis durdu", "Otomatik yeniden başlatmalar tükendi.", "/durum yaz; yanıt gelmezse orkestratöre haber ver.")}


UYARI_ONEM = {"kill_switch": "CRIT", "beklenti_alarmi": "WARN", "motor_hatasi": "CRIT", "motor_durdu": "CRIT", "servis_hatasi": "CRIT",
              "askida_kapatma": "CRIT", "giris_devam": "INFO"}                        # listede olmayan uyarılar WARN


MESAJSIZ = frozenset({"motor_hatasi", "motor_durdu", "servis_hatasi", "binance_hata"})


DURDU_SON_SATIR = "Senden: /durum yaz; yanıt gelmezse orkestratöre haber ver"


def uyari_metni(tur: str, mesaj: str = "", durum: str = "") -> str:
    """En çok 4 satır: başlık / (kısa ayrıntı) / ne yapılıyor / senden bir şey gerekiyor mu.
    motor_hatasi: tek satır "Bot hata verdi (2/5) · kendini toparlamayı deniyor · Senden: şimdilik bir şey gerekmiyor".
    motor_durdu: başlık / `durum` (açık pozisyon sayısı + stoplar; bilinmiyorsa "stoplar: bilinmiyor") / son satır."""
    if tur == "motor_hatasi":
        m = re.search(r"art arda (\d+)/(\d+)", mesaj)
        return (f"{ust('CRIT')} <b>Bot hata verdi{f' ({m.group(1)}/{m.group(2)})' if m else ''}</b> · kendini toparlamayı deniyor"
                " · Senden: şimdilik bir şey gerekmiyor")
    if tur == "motor_durdu":
        return "\n".join([f"{ust('CRIT')} <b>Bot durdu</b> · sistem yeniden başlatmayı deniyor",
                          e(durum or "Açık pozisyon: bilinmiyor · stoplar: bilinmiyor"), DURDU_SON_SATIR])
    emoji, baslik, yap, sen = UYARI.get(tur, ("⚠️", tur.replace("_", " ").capitalize(), "İzleniyor.", "Panoya bak."))
    sev = UYARI_ONEM.get(tur, "WARN")
    g = [f"{ust(sev)} " + (f"{emoji} " if sev == "INFO" else "") + f"<b>{e(baslik)}</b>"]    # WARN/CRIT: seviye emojisi ust()'ta (⚠️/🔴)
    if mesaj and tur not in MESAJSIZ:                            # teknik ayrıntı (istisna/dosya adı) mesaja girmez; kayıtta kalır
        g.append(_serbest(mesaj.split("\n")[0][:160]))
    g.append(f"🔧 {e(yap)}")
    g.append(f"👉 {e(sen)}")
    return "\n".join(g)


def limit_yaklasma_metni(deger, limit) -> str:
    """Günlük kayıp limitin %80'ine ulaştı (yalnız bildirim; risk koduna dokunmaz). Sayılar durum dosyasından aynen."""
    return (f"{ust('WARN')} Günlük kayıp limitine yaklaşıldı: {yuzde(deger, False, 1)} / {yuzde(limit, False, 0)}. "
            "Yeni işlemler sürüyor; limit dolarsa bugün yeni işlem açılmaz. Senden bir şey gerekmiyor.")


LIMIT_YAKLASMA_ORAN = 0.8


def limit_yaklasma_kontrol(o: dict, bld, gun: str) -> bool:
    """Gün içi kayıp, limitin %80'i ile limit arasındaysa gün başına BİR kez (ve 6 saat kuralıyla) uyarır. -> gönderildi mi."""
    try:
        k = o["ozet"]["risk"]["gunluk_kayip"]
        deger, limit = _ondalik(k.get("deger")), _ondalik(k.get("limit"))
        if deger is None or not limit or limit <= 0 or not (limit * Decimal(str(LIMIT_YAKLASMA_ORAN)) <= deger < limit):
            return False
        return bool(bld.mesaj("limit_yaklasma:" + gun, limit_yaklasma_metni(deger, limit), 24 * 3600))
    except Exception:  # noqa: BLE001  (bildirim motoru asla düşürmez)
        log.exception("limit yaklaşma kontrolü başarısız")
        return False


def olay_metni(tur: str, mesaj: str) -> Optional[str]:
    """Teknik olay -> None (gönderilmez); diğerleri uyarı metni."""
    return None if tur in TEKNIK or tur in ("baslangic",) else uyari_metni(tur, mesaj)


# ---------------------------------------------------------------------------- olay yönlendirme (sel koruması + teknik olaylar)
ARALIK_SN = TEKRAR_UYARI_SN      # aynı uyarı anahtarı en erken 6 saat sonra tekrar (kalıcı: yeniden başlatmada da); CRIT bastırılmaz
WS_KOPUK_SN = 10 * 60            # bu süre yeniden bağlanamazsa tek uyarı
WS_KOPMA_SAYI, WS_KOPMA_PENCERE_SN = 3, 3600
CRIT_TURLER = frozenset(k for k, v in UYARI_ONEM.items() if v == "CRIT")
MESAJLI_ANAHTAR = frozenset({"veri_yok", "askida", "tradfi_sinif"})       # anahtar = tür + mesaj (rakamsız): farklı sembol/strateji ayrı uyarı
_KAPALI_KALIBI = re.compile(r"([A-Z0-9_.]+)\s+durumu\s+\w+\s+\(TRADING değil\)")
_DIGER_NEDEN = re.compile(r"exchangeInfo'da yok|yerel veri|eşleme|sürekli sözleşme|evren boş|eksik sembol")
_KAPALI_OLAY = re.compile(r"^(\S+) borsada işleme kapandı")


def kapali_semboller(mesaj: str) -> list:
    """'... XXXUSDT durumu SETTLING (TRADING değil) ...' biçimindeki veri-yok/evren mesajından işleme kapanan semboller; mesajda başka
    bir neden de varsa (karışık) boş döner (normal uyarı yolu sürer)."""
    bulunan = _KAPALI_KALIBI.findall(mesaj)
    return bulunan if bulunan and not _DIGER_NEDEN.search(mesaj) else []


class Bildirimci:
    """Motorun `bildirim(tur, mesaj)` geri çağrısı. Teknik olaylar yalnız loglanır; sorun sürerse tek uyarı; aynı anahtar 6 saatte bir (kalıcı,
    `ortak` dosyası üzerinden). CRIT asla bastırılmaz/geciktirilmez. İşlemi etkilemeyen bilgi: saatlik nota satır. Başlangıç mesajları birleşir."""

    def __init__(self, gonder_fn: Callable[[str], bool] = None, saat: Callable[[], float] = time.time,
                 ortak: Optional[OrtakDurum] = None, servis: str = "paper", ham_fn: Callable[[str], bool] = None):
        self.gonder = gonder_fn or gonder
        self.ham = ham_fn or self.gonder                     # birleşik başlangıç / saatlik not (servis başlığı taşımaz)
        self.saat = saat
        self.ortak = ortak if ortak is not None else OrtakDurum()
        self.servis = servis
        self.kopuk_since: Optional[float] = None
        self.kopuk_uyarildi = False
        self.kopmalar: list = []
        self.karantina_fn: Optional[Callable[[str], bool]] = None   # canlı (telegram_sessiz) serviste karantina uyarısı/"düzeldi" bu yoldan gider (gonder_fn sessiz)
        self.durdu_bilgi: Optional[Callable[[], str]] = None   # paper takar: "Açık pozisyon: N · stoplar: yerinde" (bilinmiyorsa "stoplar: bilinmiyor")
        self._duzeldi_bak = True                               # açılışta ve hatadan sonra: önceki hata/durma bayrağı varsa tek "Düzeldi"

    def _yolla(self, anahtar: str, metin: str, aralik: float = ARALIK_SN) -> bool:
        t = self.saat()
        anahtar = f"{self.servis}:{anahtar}"
        if self.ortak.tekrar_var(anahtar, aralik, t):
            log.info("telegram (tekrar, atlandı) %s", anahtar)
            return False
        self.ortak.tekrar_isaretle(anahtar, t)
        return self.gonder(metin)

    def bilgi(self, satir: str) -> bool:
        """İşlemi etkilemeyen bilgi: Telegram'a GİTMEZ (saatlik not kalktı); yalnız log."""
        return bilgi_ekle(satir if self.servis == "paper" else f"{self.servis}: {satir}", ortak=self.ortak)

    def _kapali(self, sembol: str) -> bool:
        if not self.ortak.bir_kez("kapali:" + sembol):                       # kalıcı: yeniden başlatmada da tekrar yok
            return False
        return self.bilgi(f"{sembol} borsada işleme kapandı, listeden çıkarıldı")

    def olay(self, tur: str, mesaj: str) -> bool:
        t = self.saat()
        if tur == "ws_koptu":
            if self.kopuk_since is None:                       # yeni kopma dönemi (yeniden deneme hataları sayılmaz)
                self.kopuk_since = t
                self.kopmalar = [x for x in self.kopmalar if t - x < WS_KOPMA_PENCERE_SN] + [t]
                if len(self.kopmalar) >= WS_KOPMA_SAYI:
                    return self._yolla("ws_sorunu", uyari_metni("ws_sorunu", f"Son 1 saatte {len(self.kopmalar)} kopma."))
            return False
        if tur in ("ws_baglandi", "ws_yeniden_baglandi"):
            self.kopuk_since, self.kopuk_uyarildi = None, False
            return False
        if tur in TEKNIK or tur == "baslangic":
            return False
        if tur in ("motor_hatasi", "motor_durdu"):                # hata/durma: ASLA bastırılmaz; toparlanınca tek "Düzeldi"
            self.ortak.bayrak_koy("hata:" + self.servis)
            self._duzeldi_bak = True
            durum = ""
            if tur == "motor_durdu":
                try:
                    durum = self.durdu_bilgi() if self.durdu_bilgi else ""
                except Exception:  # noqa: BLE001
                    log.exception("durdu bilgisi alınamadı")
            return self.gonder(uyari_metni(tur, mesaj, durum))
        if tur in ("karantina", "karantina_cikis"):              # strateji kod hatası karantinası: 6 saat kuralı paper tarafında (Paper._karantinaya_al); burada bastırma yok
            return (self.karantina_fn or self.gonder)(f"{ust('WARN' if tur == 'karantina' else 'INFO')} {_serbest(mesaj[:200])}")
        if tur == "evren_kapali":                                # borsada işleme kapanan sembol: evrenden düşer, BİR KEZ bilgi (saatlik notta)
            m = _KAPALI_OLAY.match(mesaj)
            return self._kapali(m.group(1)) if m else False
        if tur == "veri_yok":
            kapali = kapali_semboller(mesaj)
            if kapali:                                           # TRADING dışı sembol uyarı değil: tek seferlik bilgi
                return any([self._kapali(x) for x in kapali])
        if tur == "askida" and "açık pozisyon yok" in mesaj:     # açık pozisyonu olmayan askı: işlemi etkilemez -> saatlik not
            return self.bilgi(mesaj[:200])
        metin = uyari_metni(tur, mesaj)
        if tur in CRIT_TURLER or tur in ("giris_durduruldu", "giris_devam", "hepsini_kapat"):    # CRIT ve kullanıcı komutu: bastırma/gecikme yok
            return self.gonder(metin)
        anahtar = tur
        if tur in MESAJLI_ANAHTAR:
            anahtar += ":" + hashlib.sha1(re.sub(r"\d+", "#", mesaj).encode("utf-8")).hexdigest()[:10]
        return self._yolla(anahtar, metin)

    def kontrol(self) -> bool:
        """Her turda çağrılır: birleşik başlangıç / saatlik not zamanı geldiyse gönderir; bağlantı 10 dk'dır yoksa tek uyarı."""
        self.ortak_yolla()
        if self._duzeldi_bak:
            self._duzeldi_bak = False
            if self.ortak.bayrak_al("hata:" + self.servis):       # tur başarıyla bitti (çağrı yalnız başarılı turdan sonra): hata sonrası toparlanma
                self.gonder(f"{ust('INFO')} ✅ Düzeldi: bot tekrar çalışıyor")
        if self.kopuk_since is not None and not self.kopuk_uyarildi and self.saat() - self.kopuk_since >= WS_KOPUK_SN:
            self.kopuk_uyarildi = True
            return self._yolla("ws_sorunu", uyari_metni("ws_sorunu", "10 dakikadır yeniden bağlanılamadı."))
        return False

    def ortak_yolla(self, zorla: bool = False) -> None:
        t = self.saat()
        try:
            k = self.ortak.baslangic_al(t, zorla=zorla)
            if k:                                            # eski kuyruk kalıntısı: Telegram'a gitmez, yalnız log
                log.info("servis başladı (Telegram'a gitmez): %s", baslangic_birlesik_metni(k).replace("\n", " | "))
            n = self.ortak.bilgi_al(t)
            if n:
                log.info("saatlik not (Telegram'a gitmez): %s", " | ".join(str(x)[:100] for x in n))
        except Exception:  # noqa: BLE001  (bildirim motoru asla düşürmez)
            log.exception("birleşik/saatlik bildirim gönderilemedi")

    def mesaj(self, anahtar: str, metin: str, aralik: float = ARALIK_SN) -> bool:
        """Genel (özet/işlem dışı) gönderim için sel korumalı yol."""
        return self._yolla(anahtar, metin, aralik)


# ---------------------------------------------------------------------------- systemd OnFailure bildirimi (deploy/1l3a-bildirim@.service)
def servis_hatasi_metni(birim: str, env=None) -> str:
    """OnFailure birimi için uyarı. systemd (>= 251) izlenen birimin sonucunu MONITOR_* ortam değişkenleriyle verir (yoksa yazılmaz)."""
    env = os.environ if env is None else env
    ek = ", ".join(f"{k.lower()}={env[k]}" for k in ("MONITOR_SERVICE_RESULT", "MONITOR_EXIT_CODE", "MONITOR_EXIT_STATUS") if env.get(k))
    log.error("servis hatası: %s 'failed' durumuna geçti %s", birim, ek)       # birim adı/çıkış kodu yalnız kayıtta; mesaja girmez
    return uyari_metni("servis_hatasi")


def main(argv=None) -> int:
    import argparse
    ap = argparse.ArgumentParser(description="1L3A Telegram bildirimi (token yalnız ortamdan: /etc/1l3a-paper.env)")
    ap.add_argument("--servis-hatasi", metavar="BIRIM", required=True, help="systemd birimi 'failed' oldu (OnFailure)")
    a = ap.parse_args(argv)
    logging.basicConfig(level="INFO", format="%(levelname)s %(name)s: %(message)s")
    return 0 if gonder(servis_hatasi_metni(a.servis_hatasi)) else 1


if __name__ == "__main__":
    raise SystemExit(main())
