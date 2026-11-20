"""1L3A Telegram komut servisi (standart: docs/standart/telegram-standardi.md; çekirdek: motor/ortak_ogrenme/telegram_cekirdek.py).

Bu süreç Telegram'dan `getUpdates` (uzun yoklama) ile komut dinleyen TEK süreçtir. Bildirim gönderimi (sendMessage) paper servisinde (telegram.py) kalır;
iki süreç aynı token'la getUpdates yaparsa Telegram 409 verir, bu yüzden paper servisi getUpdates ÇAĞIRMAZ.

Komutlar: /durum, /rapor, /kurulumlar, /ders, /durdur, /devam, /hepsini_kapat, /cikis_geri_al (iki adımlı), /karantina_kaldir <strateji> (iki adımlı), /geri_al, /kademe, /kademe_devam, /onayla, /reddet, /yardim, /start.
/rapor, /kurulumlar, /ders yalnız durum dosyalarını OKUR (motor/canli/gunluk_ozet.py + kurulum_ozeti.py ortak okuyucuları); gizli hesaplar adıyla görünmez ("gizli_hesaplar (N)").
/hepsini_kapat: bayrak DURDUR + istek dosyası HEPSINI_KAPAT (aynı dizin); paper/ct/aday süreçleri sonraki turda açık pozisyonları piyasa fiyatından kapatır (paper.py `hepsini_kapat_uygula`).
- Yalnız TELEGRAM_CHAT_ID'den gelen mesajlara yanıt verilir (başkasına HİÇBİR yanıt yok; yalnız sayaç loglanır, içerik loglanmaz).
- Token hiçbir mesaja/loga yazılmaz (çekirdek `mask`).
- /durdur: yeni girişleri durduran bayrak dosyasını (`L3A_DURDUR_DOSYA`, varsayılan /var/lib/1l3a-paper/durum/DURDUR) yazar; paper motoru her turda
  okur (motor/canli/paper.py `giris_durdur_uygula`); açık pozisyonlar kendi stop/hedefiyle sürer. /devam bayrağı kaldırır.
- İki adımlı onay: komut -> 4 haneli kod (120 sn, tek kullanım) -> kod mesajı ("1234" ya da "/onay 1234"). Yanlış kod / süre dolması: hiçbir şey olmaz.
- /durum yalnız durum dosyalarını OKUR; motoru çağırmaz.
Ortam: TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID (systemd EnvironmentFile; repoya girmez); isteğe bağlı L3A_DURUM_DIZIN, L3A_CT_DURUM_DIZIN, L3A_CANLI_DURUM_DIZIN,
L3A_CANLI_AYAR, L3A_DURDUR_DOSYA.
"""
from __future__ import annotations

import json
import logging
import os
import re
import signal
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, Optional
from zoneinfo import ZoneInfo

from motor.canli import disk_bakim
from motor.canli import karantina as kq
from motor.canli import mutabakat_telegram as mt
from motor.canli import strateji_verisi as sv
from motor.canli import telegram as tg
from motor.ortak_ogrenme import telegram_cekirdek as tc

log = logging.getLogger("paper.telegram_komut")
UTC = timezone.utc
TSI = ZoneInfo("Europe/Istanbul")
PROJE = "1L3A"
VARSAYILAN_DURUM = "/var/lib/1l3a-paper/durum"
DISK_ARALIK_SN = 300                 # disk ölçümü/uyarısı: en çok 5 dakikada bir (disk_bakim.calistir)
VARSAYILAN_CT = "/var/lib/1l3a-ct-paper/durum/ct_konsensus"
VARSAYILAN_ADAY = "/var/lib/1l3a-paper/durum/adaylar"
VARSAYILAN_CANLI = "/var/lib/1l3a-canli/durum"
VARSAYILAN_CANLI_AYAR = "/etc/1l3a-canli.json"
KALP_BAYAT_SN = 600                       # kalp atışı bu süreden eskiyse "BAYAT" (motor 60 sn'de bir yazar)
RISKLI = ("/durdur", "/devam", "/geri_al", "/hepsini_kapat", "/cikis_geri_al")
KADEME_YANIT = "1L3A'da kademe yok; gerçek paraya geçiş kullanıcı kararı."
ONAY_YOK = "Onay bekleyen yok (1L3A'da ders onay beklemez; dersler gölgesiz otomatik işler)."
CANLI_UYARI = "UYARI: canlı modda yürütücü paper'ı izlediği için borsadaki pozisyonlar da kapatılır; Binance ekranından kontrol edin."
VARSAYILAN_GUNCELLE = "/var/lib/1l3a-guncelle"
VARSAYILAN_KOK = "/opt/1l3a"
_KOD_RE = re.compile(r"^(?:/onay\s+)?(\d{4})$")

YARDIM = ("Komutlar:\n"
          "• /durum: bot, hesaplar ve sunucu durumu\n"
          "• /rapor: günlük özet · /kurulumlar: hesap listesi · /ders: dersler\n"
          "• /durdur: yeni girişleri durdurur, açık pozisyonlar kalır · /devam: yeniden açar\n"
          "• /hepsini_kapat: tüm açık pozisyonları kapatır, girişi durdurur (acil)\n"
          "• /geri_al: son otomatik güncellemeyi geri alır\n"
          "• /cikis_geri_al: son otomatik çıkış değişikliğini geri alır\n"
          "• /karantina_kaldir <strateji>: karantinadaki stratejiyi yeniden dener ('gizli', 'hepsi')\n"
          "• /kademe, /kademe_devam, /onayla, /reddet: 1L3A'da kullanılmaz (bilgi)\n"
          "• /yardim, /start: bu liste\n"
          "Riskli komutlardan sonra gelen 4 haneli kodu 120 sn içinde yazın.")


# ---------------------------------------------------------------------------- durum dosyası okuma (yalnız okur)
def _oku_json(yol: Path) -> Optional[dict]:
    try:
        d = json.loads(Path(yol).read_text(encoding="utf-8"))
        return d if isinstance(d, dict) else None
    except (OSError, ValueError):
        return None


def _yas_sn(zaman_str: Optional[str], simdi: datetime) -> Optional[float]:
    if not zaman_str:
        return None
    try:
        z = datetime.fromisoformat(str(zaman_str).replace("Z", "+00:00"))
    except ValueError:
        return None
    if z.tzinfo is None:
        z = z.replace(tzinfo=UTC)
    return max(0.0, (simdi - z).total_seconds())


def _yas_metni(sn: Optional[float]) -> str:
    if sn is None:
        return "bilinmiyor"
    if sn < 90:
        return f"{int(sn)} sn önce"
    if sn < 5400:
        return f"{int(sn // 60)} dk önce"
    return f"{sn / 3600:.1f} sa önce"


def _hesap_satiri(ad: str, dizin: Path, simdi: datetime) -> tuple[str, bool]:
    """-> (satır, sorunlu_mu). Dosya yoksa 'durum dosyası yok'."""
    oz = _oku_json(dizin / "ozet.json")
    if oz is None:
        return f"{ad}: durum dosyası yok/okunamadı", True
    kalp = _oku_json(dizin / "kalp_atisi.json")
    yas = _yas_sn((kalp or {}).get("zaman") or oz.get("yazim_zamani") or oz.get("zaman"), simdi)
    bayat = yas is None or yas > KALP_BAYAT_SN
    say = (oz.get("sayaclar") or {}).get("acik_pozisyon")
    risk = oz.get("risk") or {}
    uyari = []
    if (risk.get("kill_switch") or {}).get("tetiklendi"):
        uyari.append("KILL devrede")
    if (risk.get("gunluk_kayip") or {}).get("tetiklendi"):
        uyari.append("günlük limit doldu")
    satir = (f"{ad}: özsermaye {tg.usd(oz.get('ozsermaye'))} · açık pozisyon {say if say is not None else '—'} · "
             f"bugün {tg.usd(oz.get('gun_pnl'), True)} · kalp atışı {_yas_metni(yas)}{' (BAYAT)' if bayat else ''}")
    if uyari:
        satir += " · " + ", ".join(uyari)
    return satir, bayat or bool(uyari)


def _canli_satiri(dizin: Path, ayar_yolu: Path, simdi: datetime) -> str:
    kalp = _oku_json(dizin / "kalp_atisi.json")
    mod = (_oku_json(ayar_yolu) or {}).get("mod")
    mod_s = f", mod: {mod}" if mod else ", mod: bilinmiyor"
    if kalp is None:
        return f"Canlı servis: durum dosyası yok (kapalı olabilir){mod_s}"
    yas = _yas_sn(kalp.get("zaman"), simdi)
    aktif = yas is not None and yas <= KALP_BAYAT_SN and not kalp.get("durdu")
    return f"Canlı servis: {'AKTİF' if aktif else 'KAPALI/BAYAT'} (kalp atışı {_yas_metni(yas)}){mod_s}"



class KomutServisi:
    def __init__(self, istemci: tc.TelegramClient, chat_id: int, durum_dizin, *, now_fn: Callable[[], datetime] = lambda: datetime.now(UTC),
                 bayrak=None, ct_dizin=None, canli_dizin=None, canli_ayar=None, rng=None, sleep: Callable[[float], None] = time.sleep,
                 guncelle_dizin=None, sha_fn: Optional[Callable[[], Optional[str]]] = None, geri_al_dosya=None, aday_dizin=None, set_yolu=None,
                 hepsini_kapat_dosya=None, cikis_geri_al_dosya=None, disk_kok=None, disk_fn=None, mut_gonder=None, sv_gonder=None):
        self.istemci, self.chat_id, self.now, self.sleep = istemci, int(chat_id), now_fn, sleep
        self.disk_kok = Path(disk_kok or os.environ.get("L3A_DISK_KOK") or disk_bakim.KOK_DIZIN)
        self.disk_fn = disk_fn or disk_bakim.calistir
        self._disk_son: Optional[float] = None
        self.mut_gonder = mut_gonder or tg.gonder
        self._mut_son: Optional[float] = None
        self.sv_gonder = sv_gonder
        self._sv_son: Optional[float] = None
        self.durum = Path(durum_dizin)
        self.bayrak = Path(bayrak) if bayrak else Path(os.environ.get("L3A_DURDUR_DOSYA") or self.durum / "DURDUR")
        self.ct = Path(ct_dizin) if ct_dizin else Path(os.environ.get("L3A_CT_DURUM_DIZIN") or VARSAYILAN_CT)
        self.canli = Path(canli_dizin) if canli_dizin else Path(os.environ.get("L3A_CANLI_DURUM_DIZIN") or VARSAYILAN_CANLI)
        self.canli_ayar = Path(canli_ayar) if canli_ayar else Path(os.environ.get("L3A_CANLI_AYAR") or VARSAYILAN_CANLI_AYAR)
        self.guncelle = Path(guncelle_dizin) if guncelle_dizin else Path(os.environ.get("L3A_GUNCELLE_DIZIN") or VARSAYILAN_GUNCELLE)
        self.sha_fn = sha_fn or self._git_sha
        self.geri_al_dosya = Path(geri_al_dosya) if geri_al_dosya else Path(os.environ.get("L3A_GERI_AL_DOSYA") or self.durum / "GERI_AL")
        self.aday = Path(aday_dizin) if aday_dizin else Path(os.environ.get("L3A_ADAY_DURUM") or VARSAYILAN_ADAY)
        self.set_yolu = set_yolu
        self.hepsini_dosya = Path(hepsini_kapat_dosya) if hepsini_kapat_dosya else Path(os.environ.get("L3A_HEPSINI_KAPAT_DOSYA") or self.bayrak.parent / "HEPSINI_KAPAT")
        self.karantina_dosya = kq.istek_dosyasi(self.bayrak.parent)
        self.cikis_geri_al_dosya = Path(cikis_geri_al_dosya) if cikis_geri_al_dosya else Path(os.environ.get("L3A_CIKIS_GERI_AL_DOSYA") or self.bayrak.parent / "CIKIS_GERI_AL")
        kok = self.durum / "telegram_komut"
        self.kok = kok
        outbox = tc.Outbox(kok, now_fn)
        self.bildirim = tc.TelegramNotifier(istemci, self.chat_id, outbox, now_fn, PROJE, sleep=sleep)
        kw = {"rng": rng} if rng is not None else {}
        self.kapi = tc.OnayKapisi(kok / "onay.json", now_fn, denetim=kok / "onay.denetim.jsonl", **kw)
        self.bekleyen: Optional[str] = None         # kod beklenen komut (bellekte; yeniden başlatmada onay düşer = güvenli taraf)
        self.offset: Optional[int] = None
        self.yetkisiz = 0
        self._dur = False

    # ------------------------------------------------------------------ giden
    def _yanit(self, update_id, onem: str, govde: str, pinned: str = "", maks: int = 12) -> None:
        """Seviye kelimesi yazılmaz: INFO sessiz ve işaretsiz, WARN "⚠️", CRIT "🔴" (bildirim sesi `onem` ile). Mesaj en çok `maks` satır (liste/rapor: 12)."""
        isaret = {"WARN": "⚠️ ", "CRIT": "🔴 "}.get(onem, "")
        metin = "\n".join(str(govde).split("\n")[:maks])
        self.bildirim.send_text(f"{isaret}{metin}", onem, f"yanit-{update_id}-{time.monotonic_ns()}", pinned=pinned)

    def _denetim(self, mesaj: dict, komut: str, sonuc: str) -> None:
        satir = {"zaman": tc._fmt_ts(self.now()), "kullanici": (mesaj.get("from") or {}).get("id"), "komut": komut, "sonuc": sonuc}
        try:
            self.kok.mkdir(parents=True, exist_ok=True)
            with open(self.kok / "komut_denetim.jsonl", "a", encoding="utf-8") as f:
                f.write(json.dumps(satir, ensure_ascii=False) + "\n")
        except OSError as e:
            log.warning("komut denetimi yazılamadı: %s", type(e).__name__)

    # ------------------------------------------------------------------ komutlar
    @staticmethod
    def _git_sha() -> Optional[str]:
        import subprocess
        try:
            p = subprocess.run(["git", "-C", os.environ.get("L3A_GUNCELLE_KOK", VARSAYILAN_KOK), "rev-parse", "--short", "HEAD"],
                               capture_output=True, text=True, timeout=5)
            return p.stdout.strip() if p.returncode == 0 and p.stdout.strip() else None
        except Exception:  # noqa: BLE001
            return None

    def kod_satiri(self) -> str:
        """'kod: <kısa sha>, son güncelleme <zaman>' (gecmis.jsonl yalnız okunur; yoksa 'yok')."""
        sha, zaman = self.sha_fn() or "?", "yok"
        try:
            for satir in (self.guncelle / "gecmis.jsonl").read_text(encoding="utf-8").splitlines():
                try:
                    g = json.loads(satir)
                except ValueError:
                    continue
                if g.get("sonuc") in ("kuruldu", "geri_alindi") and g.get("zaman"):
                    zaman = datetime.fromisoformat(str(g["zaman"]).replace("Z", "+00:00")).astimezone(TSI).strftime("%d.%m %H:%M") + " TSİ"
        except (OSError, ValueError):
            pass
        return f"kod: {sha}, son güncelleme {zaman}"

    def _karantina(self) -> dict:
        """saglik.json `karantina` bloğu ({'gorunur': [...], 'gizli': N}); yoksa/okunamazsa boş. Gizli hesap adı dosyada yok."""
        k = (_oku_json(self.durum / "saglik.json") or {}).get("karantina")
        if not isinstance(k, dict):
            return {"gorunur": [], "gizli": 0}
        return {"gorunur": [str(x) for x in (k.get("gorunur") or [])], "gizli": int(k.get("gizli") or 0)}

    def _karantina_komut(self, uid, m: dict, metin: str) -> None:
        """/karantina_kaldir <strateji|gizli|hepsi>: iki adımlı. İstek dosyasını paper her turda okur (paper.py `karantina_kaldir_uygula`)."""
        parca = metin.split(None, 1)
        arg = parca[1].strip() if len(parca) > 1 else ""
        k = self._karantina()
        if not (k["gorunur"] or k["gizli"]):
            self._denetim(m, "/karantina_kaldir", "karantina_yok")
            return self._yanit(uid, "INFO", "Karantinada strateji yok.")
        adlar = {x.lower(): x for x in k["gorunur"]}
        kisa = arg.lower()
        if kisa in adlar:
            hedef, ad = adlar[kisa], adlar[kisa]
        elif kisa == "gizli" and k["gizli"]:
            hedef, ad = "gizli", f"{kq.GIZLI_AD} ({k['gizli']})"
        elif kisa == "hepsi":
            hedef, ad = "hepsi", "karantinadaki tüm stratejiler"
        else:
            self._denetim(m, "/karantina_kaldir", "gecersiz_arguman")
            return self._yanit(uid, "INFO", (kq.satir(k) or "") + "\nKullanım: /karantina_kaldir <strateji> (ya da 'gizli' / 'hepsi')")
        komut = f"/karantina_kaldir {hedef}"
        ozet = f"{ad} karantinadan çıkarılır, strateji bir sonraki turda yeniden denenir (yine hata verirse yeniden karantinaya girer; bildirim 6 saatte bir)."
        kod = self.kapi.baslat(komut, ozet)
        self.bekleyen = komut
        self._denetim(m, "/karantina_kaldir", "kod_istendi")
        self._yanit(uid, "WARN", f"/karantina_kaldir: {ozet}\nOnaylamak için {tc.CODE_TTL_S} sn içinde bu 4 haneli kodu yazın.", pinned=f"Kod: {kod}")

    def durum_metni(self) -> tuple[str, str]:
        """-> (önem, gövde). Yalnız durum dosyalarını okur."""
        simdi = self.now()
        satirlar, sorun = [f"Durum · {simdi.astimezone(TSI).strftime('%d.%m %H:%M')} TSİ"], False
        s, b = _hesap_satiri("Paper (görünür hesaplar)", self.durum, simdi)
        satirlar.append(s)
        sorun |= b
        if (self.ct / "ozet.json").exists():
            s, b = _hesap_satiri("CT konsensüs hesabı", self.ct, simdi)
            satirlar.append(s)
            sorun |= b
        if self.bayrak.exists():
            ic = _oku_json(self.bayrak) or {}
            satirlar.append("Yeni giriş: DURDURULDU" + (f" ({ic['zaman']})" if ic.get("zaman") else "") + " · açık pozisyonlar kendi stop/hedefiyle sürer · /devam ile açılır")
            sorun = True
        else:
            satirlar.append("Yeni giriş: AÇIK (durdurma bayrağı yok)")
        kar = kq.satir(self._karantina())
        if kar:
            satirlar.append(kar)
            sorun = True
        satirlar.append(_canli_satiri(self.canli, self.canli_ayar, simdi))
        satirlar.append(f"{disk_bakim.satir()} · {self.kod_satiri()}")
        return ("WARN" if sorun else "INFO"), "\n".join(satirlar)

    # ------------------------------------------------------------------ okuma komutları (yalnız durum dosyaları)
    def rapor_metni(self) -> tuple[str, str]:
        from motor.canli import gunluk_ozet as go
        try:
            env = {**os.environ, "L3A_DURDUR_DOSYA": str(self.bayrak), "L3A_CT_DURUM": str(self.ct)}
            o = go.topla(self.durum, self.now(), ct_dizin=self.ct, set_yolu=self.set_yolu, env=env)
            return "INFO", go.gunluk_metin(o)
        except Exception as e:  # noqa: BLE001  okuma hatası servisi düşürmesin
            log.warning("rapor üretilemedi: %s", type(e).__name__)
            return "WARN", "Rapor üretilemedi: durum dosyaları okunamadı (henüz veri yok olabilir)."

    @staticmethod
    def _satir(h: dict, simdi: datetime) -> str:
        z = lambda v: {True: "aktif", False: "pasif", None: "—"}[v]          # noqa: E731
        son = _yas_metni(_yas_sn(h.get("son_islem"), simdi)) if h.get("son_islem") else "işlem yok"
        drift = {"uyari": "UYARI", "normal": "yok", None: "—"}[h.get("drift")]
        pnl = tg.usd(h.get("toplam_pnl"), True)
        acik = h.get("acik")
        return (f"• {h['ad']}: açık {acik if acik is not None else '—'} · toplam K/Z {pnl} · son işlem {son}"
                + ("" if h.get("kurulum") is None else f" · ML filtre {z(h.get('filtre'))} · drift {drift}"))

    def kurulumlar_metni(self) -> tuple[str, str]:
        from motor.canli import kurulum_ozeti as ko
        simdi = self.now()
        try:
            v = ko.hesaplar(self.durum, ct=self.ct, aday=self.aday, set_yolu=self.set_yolu)
        except Exception as e:  # noqa: BLE001
            log.warning("kurulumlar okunamadı: %s", type(e).__name__)
            return "WARN", "Kurulum bilgisi okunamadı (henüz veri yok olabilir)."
        s = [f"Kurulumlar · {simdi.astimezone(TSI).strftime('%d.%m %H:%M')} TSİ"]
        if not (v["gorunur"] or v["gizli"] or v["ct"] or v["adaylar"]):
            return "INFO", s[0] + "\nHenüz veri yok."
        s += [self._satir(h, simdi) for h in v["gorunur"]]
        if v["gizli"]:
            s.append(self._satir(v["gizli"], simdi))
        s.append("CT konsensüs:" if v["ct"] else "CT konsensüs: veri yok")
        if v["ct"]:
            s.append(self._satir(v["ct"], simdi))
        s.append("Aday stratejiler:" if v["adaylar"] else "Aday stratejiler: aday yok")
        s += [self._satir(h, simdi) for h in v["adaylar"]]
        return "INFO", "\n".join(s)

    def ders_metni(self) -> tuple[str, str]:
        from motor.canli import kurulum_ozeti as ko
        simdi = self.now()
        try:
            v = ko.hesaplar(self.durum, ct=self.ct, aday=self.aday, set_yolu=self.set_yolu)
            kaynaklar = [("paper", v["ana_ogrenme"])] + ([("ct_konsensus", v["ct"]["og"])] if v["ct"] else []) + [(f"aday {a['ad']}", a["og"]) for a in v["adaylar"]]
            gizli = v["gizli_kurulum"]
        except Exception as e:  # noqa: BLE001
            log.warning("dersler okunamadı: %s", type(e).__name__)
            return "WARN", "Ders bilgisi okunamadı (henüz veri yok olabilir)."
        s, veri = [f"Dersler · {simdi.astimezone(TSI).strftime('%d.%m %H:%M')} TSİ"], False
        for ad, og in kaynaklar:
            d = ko.dersler(og, gizli, simdi)
            if not d["veri"]:
                continue
            veri = True
            s.append(f"{ad}: aktif/aday {len(d['aktif'])}, son {ko.EMEKLI_GUN} günde emekli {len(d['emekli'])}" + (f", Diğer hesaplar: {d['gizli_adet']}" if d["gizli_adet"] else ""))
            for kimlik, durum, etki, n in d["aktif"]:
                s.append(f"  • {kimlik} [{'yaşayan' if durum == 'alive' else 'aday'}] etki {'—' if etki is None else f'{etki:+.3f}'} · n {n if n is not None else '—'}")
            for kimlik, gun in d["emekli"]:
                s.append(f"  • {kimlik} [emekli {gun}]")
        return "INFO", "\n".join(s) if veri else s[0] + "\nHenüz veri yok (ders dosyası oluşmadı)."

    def _canli_mod(self) -> Optional[str]:
        return (_oku_json(self.canli_ayar) or {}).get("mod")

    def _bayrak_yaz(self) -> None:
        tc.atomic_write_json(self.bayrak, {"zaman": tc._fmt_ts(self.now()), "kaynak": "telegram"})

    def _bayrak_kaldir(self) -> None:
        self.bayrak.unlink(missing_ok=True)

    def isle(self, guncelleme: dict) -> None:
        """Tek update. Yetkisiz sohbet: yanıt YOK."""
        uid = guncelleme.get("update_id")
        if isinstance(uid, int):
            self.offset = uid + 1
        m = guncelleme.get("message")
        if not isinstance(m, dict):
            return                                              # callback vb.: bu aşamada yok
        if (m.get("chat") or {}).get("id") != self.chat_id:
            self.yetkisiz += 1
            log.warning("yetkisiz sohbetten mesaj yok sayıldı (toplam %d)", self.yetkisiz)
            return
        metin = str(m.get("text") or "").strip()
        if not metin:
            return
        kod = _KOD_RE.match(metin)
        if kod:
            return self._kod(uid, m, kod.group(1))
        ilk = metin.split()[0].lower().split("@")[0]
        if ilk in ("/yardim", "/start", "/help"):
            self._denetim(m, ilk, "yanit")
            return self._yanit(uid, "INFO", YARDIM, maks=12)
        if ilk == "/durum":
            self._denetim(m, ilk, "yanit")
            onem, govde = self.durum_metni()
            return self._yanit(uid, onem, govde)
        if ilk in ("/rapor", "/kurulumlar", "/ders"):
            self._denetim(m, ilk, "yanit")
            onem, govde = {"/rapor": self.rapor_metni, "/kurulumlar": self.kurulumlar_metni, "/ders": self.ders_metni}[ilk]()
            return self._yanit(uid, onem, govde, maks=12)
        if ilk in ("/kademe", "/kademe_devam"):
            self._denetim(m, ilk, "yanit")
            return self._yanit(uid, "INFO", KADEME_YANIT)
        if ilk in ("/onayla", "/reddet"):
            self._denetim(m, ilk, "yanit")
            return self._yanit(uid, "INFO", ONAY_YOK)
        if ilk == "/karantina_kaldir":
            return self._karantina_komut(uid, m, metin)
        if ilk in RISKLI:
            return self._riskli(uid, m, ilk)
        self._denetim(m, "bilinmeyen", "yanit")
        self._yanit(uid, "INFO", "Bilinmeyen komut.\n" + YARDIM)

    def _riskli(self, uid, m: dict, komut: str) -> None:
        var = self.bayrak.exists()
        if komut == "/geri_al" and self.geri_al_dosya.exists():
            self._denetim(m, komut, "zaten_istendi")
            return self._yanit(uid, "INFO", "Geri alma isteği zaten verilmiş; güncelleyici uygulayınca bildirir.")
        if komut == "/durdur" and var:
            self._denetim(m, komut, "zaten_durdurulmus")
            return self._yanit(uid, "INFO", "Yeni girişler zaten durdurulmuş. Açmak için /devam")
        if komut == "/devam" and not var:
            self._denetim(m, komut, "zaten_acik")
            return self._yanit(uid, "INFO", "Yeni girişler zaten açık; yapılacak bir şey yok.")
        if komut == "/hepsini_kapat" and self.hepsini_dosya.exists():
            self._denetim(m, komut, "zaten_istendi")
            return self._yanit(uid, "INFO", "Hepsini kapat isteği zaten verilmiş; motorlar bir sonraki turda uygular ve bildirir.")
        if komut == "/cikis_geri_al":
            if self.cikis_geri_al_dosya.exists():
                self._denetim(m, komut, "zaten_istendi")
                return self._yanit(uid, "INFO", "Çıkış geri alma isteği zaten verilmiş; paper bir sonraki turda uygular ve bildirir.")
            if not (_oku_json(self.cikis_geri_al_dosya.parent / "cikis_override.json") or {}):
                self._denetim(m, komut, "geri_alinacak_yok")
                return self._yanit(uid, "INFO", "Geri alınacak otomatik çıkış değişikliği yok.")
        ozet = {"/durdur": "Yeni girişleri durdurur; açık pozisyonlar kendi stop/hedefiyle sürer.",
                "/hepsini_kapat": "TÜM paper hesaplarında (10'lu set, ct_konsensus, adaylar) açık pozisyonları bir sonraki turda piyasa fiyatından kapatır ve yeni girişleri durdurur."
                                  + (" " + CANLI_UYARI if self._canli_mod() == "canli" else ""),
                "/devam": "Durdurmayı kaldırır; yeni girişler yeniden açılır.",
                "/cikis_geri_al": "Son otomatik çıkış değişikliğini geri alır (yalnız yeni girişler etkilenir); o strateji+alternatif bir daha otomatik uygulanmaz.",
                "/geri_al": "Son otomatik güncellemeyi geri alır ve servisleri yeniden başlatır; o sürüm bir daha kurulmaz."}[komut]
        kod = self.kapi.baslat(komut, ozet)
        self.bekleyen = komut
        self._denetim(m, komut, "kod_istendi")
        self._yanit(uid, "WARN", f"{komut}: {ozet}\nOnaylamak için {tc.CODE_TTL_S} sn içinde bu 4 haneli kodu yazın.",
                    pinned=f"Kod: {kod}")

    def _kod(self, uid, m: dict, kod: str) -> None:
        komut, self.bekleyen = self.bekleyen, None
        if komut is None:
            self._denetim(m, "kod", "bekleyen_yok")
            return self._yanit(uid, "INFO", "Bekleyen onay yok; hiçbir şey yapılmadı. Önce /durdur, /devam, /hepsini_kapat ya da /karantina_kaldir yazın.")
        if not self.kapi.dogrula(komut, kod):
            self._denetim(m, komut, "reddedildi")
            return self._yanit(uid, "WARN", f"Kod yanlış ya da süresi doldu: {komut} uygulanmadı. Gerekirse komutu yeniden yazın.")
        try:
            if komut.startswith("/karantina_kaldir "):
                tc.atomic_write_json(self.karantina_dosya, {"zaman": tc._fmt_ts(self.now()), "kaynak": "telegram", "strateji": komut.split(None, 1)[1]})
                govde = ("Karantina kaldırma isteği yazıldı. Paper bir sonraki turda stratejiyi yeniden dener; düzelirse INFO bildirir, yine hata verirse "
                         "yeniden karantinaya alır (bildirim aynı strateji için 6 saatte bir).")
                onem = "WARN"
            elif komut == "/durdur":
                self._bayrak_yaz()
                govde = "Yeni girişler durduruldu (bayrak yazıldı). Motor bir sonraki turda uygular; açık pozisyonlar kendi stop/hedefiyle sürer. Açmak için /devam"
                onem = "WARN"
            elif komut == "/hepsini_kapat":
                self._bayrak_yaz()                                 # önce DURDUR: kapanış sırasında yeni giriş olmasın
                tc.atomic_write_json(self.hepsini_dosya, {"zaman": tc._fmt_ts(self.now()), "kaynak": "telegram"})
                govde = ("Hepsini kapat isteği yazıldı, yeni girişler durduruldu. Paper/ct/aday motorları bir sonraki turda açık pozisyonları piyasa fiyatından kapatır "
                         "ve WARN ile bildirir. Girişleri açmak için /devam." + (" " + CANLI_UYARI if self._canli_mod() == "canli" else ""))
                onem = "WARN"
            elif komut == "/cikis_geri_al":
                tc.atomic_write_json(self.cikis_geri_al_dosya, {"zaman": tc._fmt_ts(self.now()), "kaynak": "telegram"})
                govde = "Çıkış geri alma isteği yazıldı. Paper bir sonraki turda son otomatik çıkış değişikliğini geri alır ve bildirir; açık pozisyonlar etkilenmez."
                onem = "WARN"
            elif komut == "/geri_al":
                tc.atomic_write_json(self.geri_al_dosya, {"zaman": tc._fmt_ts(self.now()), "kaynak": "telegram"})
                govde = "Geri alma isteği yazıldı. Sunucudaki güncelleyici (root) birkaç saniye içinde uygular ve Telegram'a bildirir."
                onem = "WARN"
            else:
                self._bayrak_kaldir()
                govde = "Durdurma kaldırıldı; yeni girişler yeniden açılıyor (motor bir sonraki turda uygular)."
                onem = "INFO"
        except OSError as e:
            self._denetim(m, komut, "yazilamadi")
            return self._yanit(uid, "CRIT", f"{komut} uygulanamadı: bayrak dosyası yazılamadı/silinemedi ({type(e).__name__}). Sunucuyu kontrol edin.")
        self._denetim(m, komut, "uygulandi")
        self._yanit(uid, onem, govde)

    # ------------------------------------------------------------------ döngü
    def baslat(self) -> None:
        """Eski (birikmiş) güncellemeleri atlar: yeniden başlatmada eski komutlar tekrar işlenmesin."""
        try:
            for u in self.istemci.get_updates(-1, timeout=0):
                if isinstance(u.get("update_id"), int):
                    self.offset = u["update_id"] + 1
        except tc.TelegramError as e:
            log.warning("başlangıç güncelleme temizliği başarısız: %s", e.kind)

    def tur(self, bekleme: int = 30) -> int:
        """Bir uzun yoklama turu -> işlenen update sayısı. Hata: loglanır, bekleme yapılır, 0 döner."""
        try:
            ups = self.istemci.get_updates(self.offset, timeout=bekleme)
        except tc.TelegramError as e:
            log.error("getUpdates hatası: %s %s%s", e.kind, e.status, " (başka bir süreç aynı token'la getUpdates yapıyor olabilir)" if e.kind == "conflict" else "")
            self.sleep(30 if e.kind in ("conflict", "permanent") else (e.retry_after or 5))
            return 0
        for u in ups:
            try:
                self.isle(u)
            except Exception as e:  # noqa: BLE001  tek komut hatası servisi düşürmesin; metin loglanmaz (token riski yok ama gizlilik)
                log.error("komut işlenemedi: %s", tc.mask(type(e).__name__))
                if isinstance(u.get("update_id"), int):
                    self.offset = u["update_id"] + 1
        return len(ups)

    def _disk_tick(self) -> None:
        """Disk ölçümü/uyarısı/günlük döndürme: en çok 5 dakikada bir, yoklama turundan SONRA (getUpdates'e dokunmaz). Hata yutulur."""
        try:
            t = self.now().timestamp()
            if self._disk_son is not None and t - self._disk_son < DISK_ARALIK_SN:
                return
            self._disk_son = t
            self.disk_fn(str(self.disk_kok), simdi=t)
        except Exception as e:  # noqa: BLE001  disk bakımı komut dinlemeyi asla etkilemesin
            log.warning("disk bakımı atlandı: %s", type(e).__name__)

    def _mutabakat_tick(self) -> None:
        """İşlem mutabakatı özeti: en çok 10 dakikada bir dosya kontrolü; tek seferlik sessiz Telegram (mutabakat_telegram.tick). Hata yutulur."""
        try:
            t = self.now().timestamp()
            if self._mut_son is not None and t - self._mut_son < mt.ARALIK_SN:
                return
            self._mut_son = t
            mt.tick(self.durum, gonder=self.mut_gonder, simdi=t)
        except Exception as e:  # noqa: BLE001
            log.warning("mutabakat özeti atlandı: %s", type(e).__name__)

    def _strateji_verisi_tick(self) -> None:
        """Strateji verisi belgesi: kod sürümü başına TEK sessiz gönderim (strateji_verisi.tick); en çok 10 dakikada bir kontrol. Hata yutulur."""
        try:
            t = self.now().timestamp()
            if self._sv_son is not None and t - self._sv_son < sv.ARALIK_SN:
                return
            self._sv_son = t
            sv.tick(self.durum, self.sha_fn(), gonder=self.sv_gonder, simdi=t, ct_dizin=self.ct, set_yolu=self.set_yolu)
        except Exception as e:  # noqa: BLE001
            log.warning("strateji verisi atlandı: %s", type(e).__name__)

    def calistir(self, max_tur: Optional[int] = None) -> int:
        self.baslat()
        n = 0
        while not self._dur and (max_tur is None or n < max_tur):
            self.tur()
            self._disk_tick()
            self._mutabakat_tick()
            self._strateji_verisi_tick()
            n += 1
        return 0

    def durdur(self, *_a) -> None:
        self._dur = True


def main(argv=None) -> int:
    import argparse
    ap = argparse.ArgumentParser(description="1L3A Telegram komut servisi (token yalnız ortamdan: /etc/1l3a-paper.env)")
    ap.add_argument("--durum", default=os.environ.get("L3A_DURUM_DIZIN", VARSAYILAN_DURUM))
    ap.add_argument("--log", default="INFO")
    a = ap.parse_args(argv)
    logging.basicConfig(level=a.log, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    y = tg.yapilandirma()
    if y is None:
        log.error("TELEGRAM_BOT_TOKEN / TELEGRAM_CHAT_ID tanımlı değil; komut servisi çalışmaz")
        return 2
    token, chat = y
    try:
        chat_id = int(chat)
    except ValueError:
        log.error("TELEGRAM_CHAT_ID sayı olmalı")
        return 2
    svc = KomutServisi(tc.TelegramClient(token), chat_id, Path(a.durum))
    signal.signal(signal.SIGTERM, svc.durdur)
    signal.signal(signal.SIGINT, svc.durdur)
    log.info("komut servisi başladı (durum dizini %s, bayrak %s)", svc.durum, svc.bayrak)
    return svc.calistir()


if __name__ == "__main__":
    raise SystemExit(main())
