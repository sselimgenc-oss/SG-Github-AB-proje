"""Canlı servis girişi: `python -m motor.canli.borsa.calistir --durum DIZIN --tohum DIZIN [--ayar DOSYA]`.

Paper servisinin AYNI döngüsünü (`motor.canli.paper.canli_calistir`) çalıştırır; yalnız seçili stratejileri kurar ve her turdan sonra
paper motorunun niyetlerini yürütücüye verir. Durum dizini paper'dan AYRI olmalıdır (kendi paper durumu + `canli/` yürütücü durumu).
`canli` modu CANLI_ONAY=evet olmadan BAŞLAMAZ. Anahtarlar yalnız ortam değişkeninden okunur.
"""
from __future__ import annotations

import argparse
import hashlib
import logging
import sys
import time
from pathlib import Path
from typing import Optional

from motor.canli.borsa import canli_ayar as ca
from motor.canli.borsa import canli_kayit as ck
from motor.canli.borsa import canli_limitler as cl
from motor.canli.borsa.canli_yurutucu import Ayar, MotorGorunumu, SifirdanBaslamaHatasi, Yurutucu, sifirdan_kontrol
from motor.canli.borsa.motor_kopru import CanliDesteklemiyorHatasi, gorunum, uygunluk_kontrol

log = logging.getLogger("canli")
KALICI_KODLAR = frozenset({-2014, -2015, -1022})        # API anahtarı geçersiz / imza hatalı: tekrar denemek işe yaramaz (exit 3)
OKUMA_HATA_BLOK = 3                                      # hesap özsermayesi art arda bu kadar tur okunamazsa YENİ girişler bloklanır


YASAK_DOSYASI = "yasak.json"          # durum dizininde: 418/429 yasağı yeniden başlatmada da sürer (paper.py ile AYNI dosya)


def _durum_dosyasi(dizin: Path, sid: str) -> Path:
    return dizin / "canli" / f"yurutucu_{hashlib.sha1(sid.encode()).hexdigest()[:12]}.json"


def _hesap_dosyasi(dizin: Path) -> Path:
    return dizin / "canli" / "hesap_durumu.json"


def hesap_yukle(yol: Path, env=None) -> dict:
    import json
    if yol.exists():
        return json.loads(yol.read_text(encoding="utf-8"))
    sifirdan_kontrol(yol, "hesap", env)               # O9: hesap zirvesi/kill kaydı kaybolduysa sessizce sıfırdan başlama (L3A_SIFIRDAN_IZIN=hesap ile bilerek)
    return {"surum": 1, "kimlikler": None, "zirve": None, "toplam": None, "kill": False, "kill_neden": None}


def hesap_izle(yurutuculer: dict, h: dict, yol: Optional[Path] = None) -> Optional[str]:
    """HESAP KILL: TÜM canlı stratejilerin GERÇEK özsermaye toplamı, ortak zirveden -%20 (taban min(toplam zirve, toplam tahsis)) -> her stratejiye
    kalıcı kill verilir (pozisyonlar kendi turlarında kapatılır). Zirve ve kill `h` içinde (diske yazılır) KALICIDIR: yeniden başlatma kaldırmaz.
    Para yatırma/çekme algılanmaz: para transferi yalnız canlı servis durdurulup yapılır, sonra zirve elle sıfırlanır.
    Bir stratejinin özsermayesi okunamazsa o tur toplam hesaplanmaz (eksik toplamla yanlış tetik/yanlış rahatlık olmasın); ART ARDA 3 turda okunamazsa
    tüm yürütücülerde `hesap_blok` açılır (YENİ giriş yok; mevcut pozisyon/stoplar etkilenmez), ilk başarılı okumada kalkar. Kill zaten verilmişse
    her turda tekrar uygulanır. -> yeni tetiklendiyse mesaj."""
    mesaj = None
    if not h.get("kill"):
        try:
            kasalar = {sid: y.ozsermaye_oku() for sid, y in yurutuculer.items()}
        except Exception as e:  # noqa: BLE001  (BorsaHata dahil her okuma hatası: sessiz değil, sayılır)
            log.warning("hesap kill: özsermaye okunamadı, bu tur toplam hesaplanmadı: %s", e)
            kasalar = None
            h["okuma_hata"] = int(h.get("okuma_hata") or 0) + 1
            if h["okuma_hata"] >= OKUMA_HATA_BLOK and yurutuculer and not any(y.hesap_blok for y in yurutuculer.values()):
                for y in yurutuculer.values():
                    y.hesap_blok = True
                next(iter(yurutuculer.values())).olay("canli_hesap_blok", f"hesap özsermayesi art arda {h['okuma_hata']} tur okunamadı: YENİ giriş bloklandı "
                                                      "(mevcut pozisyon/stoplar sürer; ilk başarılı okumada kalkar)")
        if kasalar is not None:
            h["okuma_hata"] = 0
            if any(y.hesap_blok for y in yurutuculer.values()):
                for y in yurutuculer.values():
                    y.hesap_blok = False
                next(iter(yurutuculer.values())).olay("canli_hesap_blok_kalkti", "hesap özsermayesi tekrar okunabiliyor: yeni giriş bloğu kalktı")
            mesaj = cl.hesap_kill_guncelle(h, kasalar, tahsisler={sid: y.ayar.tahsis for sid, y in yurutuculer.items()})
        if yol is not None:
            try:
                from motor.canli.durum import atomik_yaz_json
                yol.parent.mkdir(parents=True, exist_ok=True)
                atomik_yaz_json(yol, h)
            except Exception as e:  # noqa: BLE001  (disk hatası kill'i/kapatmayı engellemesin; bellekteki h doğru kalır, sonraki turda yeniden yazılır)
                log.error("hesap durumu diske yazılamadı: %s: %s", type(e).__name__, str(e)[:200])
                if yurutuculer:
                    next(iter(yurutuculer.values())).olay("canli_kayit_hatasi", f"[hesap] hesap_durumu.json yazılamadı ({type(e).__name__}); kill/koruma akışı sürüyor")
    if h.get("kill"):
        for y in yurutuculer.values():
            y.hesap_kill_ver(mesaj or "HESAP KILL kalıcı: tüm stratejiler durduruldu (hesap toplamı -%20 tetiklenmişti).")
    return mesaj


def baglan(ayar: ca.CanliAyar, s: ca.StratejiAyar, uyku=time.sleep, bildir=None, ilk_bekle: float = 10, en_cok_bekle: float = 300,
           uyari_aralik_sn: float = 1800, saat=time.monotonic):
    """Borsa bağlantısı + bakiye okuması (anahtar/izin doğrulaması). GEÇİCİ hata (ağ, 5xx, 429/418, zaman) -> sınırsız yeniden dene (10 sn, ikiye katlanır, en çok 300 sn;
    her deneme loglanır, `bildir` en fazla `uyari_aralik_sn` aralıkla çağrılır). YALNIZ gerçek yapılandırma/anahtar hataları yükselir:
    CanliAyarHatasi ve kodu -2014/-2015/-1022 olan BorsaHata (çağıran exit 3 döner). -> (borsa, bilgi, bakiye)."""
    from motor.canli.borsa.binance_futures import BorsaHata
    bekle, son_uyari, deneme = ilk_bekle, None, 0
    while True:
        deneme += 1
        try:
            borsa, bilgi = borsa_kur(ayar, s)
            return borsa, bilgi, borsa.bakiye()
        except ca.CanliAyarHatasi:
            raise
        except BorsaHata as e:
            if e.kod in KALICI_KODLAR:
                raise
            hata = e
        except Exception as e:  # noqa: BLE001  (ağ/ayrıştırma vb.: geçici say; mesajda gizli yok)
            hata = e
        log.error("%s: borsa bağlantısı kurulamadı (deneme %d, %s): %s; %g sn sonra yeniden", s.id, deneme, type(hata).__name__, hata, bekle)
        t = saat()
        if bildir is not None and (son_uyari is None or t - son_uyari >= uyari_aralik_sn):
            son_uyari = t
            try:
                bildir(f"🟠 <b>1L3A CANLI</b>: {s.id} borsa bağlantısı kurulamadı ({type(hata).__name__}); yeniden deneniyor (deneme {deneme}).")
            except Exception:  # noqa: BLE001
                pass
        uyku(bekle)
        bekle = min(bekle * 2, en_cok_bekle)


SPOT_TABAN = "https://api.binance.com"                  # apiRestrictions SPOT hostundadır (fapi'den FARKLI)


class ApiKisitHatasi(Exception):
    """O4: API anahtarı güvenli değil (çekim izni açık / IP kısıtı yok): canlı başlamaz (exit 2)."""


def api_kisitlari_oku(anahtar: str, gizli: str, zaman_farki_ms: int = 0, oturum=None, saat=time.time, taban: str = SPOT_TABAN) -> dict:
    """GET {spot}/sapi/v1/account/apiRestrictions (imzalı). Küçük, ayrı istek (binance_futures.py'ye dokunmaz; yalnız `imzala`/`temizle` kullanılır)."""
    from urllib.parse import urlencode
    from motor.canli.borsa.binance_futures import BorsaHata, imzala, temizle
    if oturum is None:
        import requests
        oturum = requests.Session()
    p = {"recvWindow": 5000, "timestamp": int(saat() * 1000) + int(zaman_farki_ms or 0)}
    sorgu = urlencode(p)
    sorgu += "&signature=" + imzala(sorgu, gizli)
    try:
        r = oturum.request("GET", f"{taban}/sapi/v1/account/apiRestrictions?{sorgu}", headers={"X-MBX-APIKEY": anahtar}, timeout=20)
    except Exception as e:  # noqa: BLE001  (yalnız tür adı: metin URL/imza taşıyabilir)
        raise BorsaHata(f"apiRestrictions ağ hatası: {type(e).__name__}", belirsiz=True) from None
    if r.status_code != 200:
        kod, mesaj = None, ""
        try:
            j = r.json()
            kod, mesaj = j.get("code"), temizle(str(j.get("msg", ""))[:200])
        except Exception:  # noqa: BLE001
            pass
        raise BorsaHata(f"apiRestrictions HTTP {r.status_code} kod={kod} {mesaj}", kod, r.status_code)
    try:
        return r.json()
    except Exception:  # noqa: BLE001
        raise BorsaHata("apiRestrictions yanıtı JSON değil") from None


def api_kisit_dogrula(ayar: ca.CanliAyar, s: ca.StratejiAyar, borsa, env=None, oturum=None, uyku=time.sleep, bildir=None) -> None:
    """O4 (yalnız canlı): enableWithdrawals=true ya da ipRestrict!=true -> ApiKisitHatasi. Ulaşılamazsa baglan ile AYNI geri çekilmeyle yeniden dener
    (10 sn -> 300 sn, sınırsız); yalnız kalıcı anahtar hatası (-2014/-2015/-1022) yükselir."""
    if ayar.mod != "canli":
        return
    from motor.canli import paper as pp
    from motor.canli.borsa.binance_futures import BorsaHata
    anahtar, gizli = ca.anahtarlar(s, env)

    def kalici(e):
        return isinstance(e, BorsaHata) and e.kod in KALICI_KODLAR
    r = pp.sonsuz_dene(lambda: api_kisitlari_oku(anahtar, gizli, getattr(borsa, "zaman_farki_ms", 0) or 0, oturum), f"{s.id} apiRestrictions",
                       uyku=uyku, kalici=kalici, bildir=bildir)
    if r.get("enableWithdrawals") is not False:
        raise ApiKisitHatasi(f"{s.id}: API anahtarında ÇEKİM izni açık (enableWithdrawals) ya da okunamadı: canlı başlamaz. Binance'te çekim iznini kapatın")
    if r.get("ipRestrict") is not True:
        raise ApiKisitHatasi(f"{s.id}: API anahtarında IP kısıtı yok (ipRestrict!=true): canlı başlamaz. Binance'te sunucu IP'sine kısıtlayın")


def onkontrol(ayar: ca.CanliAyar) -> None:
    """Başlamadan: strateji kimlikleri sette var mı, canlıda taklit edilebilir mi (portföy/kısmi çıkış yok)."""
    from motor.canli import paper_v2 as v2
    tanimlar = {t.kimlik: t for t in v2.tanimlari_yukle()}
    for s in ayar.stratejiler:
        t = tanimlar.get(s.id)
        if t is None:
            raise ca.CanliAyarHatasi(f"{s.id}: paper_v2 setinde yok")
        if t.etiket in ("kapanis_aday", "kapanis_aday_ek"):      # kapanış adayı: gerçek paraya YALNIZ kapanis_canli_onay'daki strateji bazlı kullanıcı onayıyla; testnet/kuru serbest (uyarı)
            if getattr(ayar, "mod", "canli") == "canli":         # mod okunamazsa gerçek para varsayılır (fail-closed)
                if s.id not in {o[0] for o in getattr(ayar, "kapanis_canli_onay", ())}:
                    raise CanliDesteklemiyorHatasi(f"{s.id}: kapanış turu paper adayı (etiket {t.etiket}) gerçek paraya alınamaz: kapanis_canli_onay içinde "
                                                   "bu strateji için kullanıcı onayı yok (12 hafta paper + kullanıcı kararı DURUM.md'ye yazıldıktan sonra eklenir)")
            else:
                log.warning("%s: kapanış adayı (%s) %s modunda çalıştırılıyor; gerçek paraya ancak kapanis_canli_onay ile girer", s.id, t.etiket, ayar.mod)
        if t.kol == "portfoy":
            raise CanliDesteklemiyorHatasi(f"{s.id}: portföy (ağırlık) stratejisi canlıda henüz desteklenmiyor")
        if t.nesne.cikis_ayarlari.kismi:
            raise CanliDesteklemiyorHatasi(f"{s.id}: kısmi çıkış canlıda desteklenmiyor")


def borsa_kur(ayar: ca.CanliAyar, s: ca.StratejiAyar, env=None):
    """(borsa, exchangeInfo). kuru: gerçek hiçbir istek imzalanmaz; herkese açık mark fiyat + exchangeInfo kullanılır."""
    from decimal import Decimal
    from motor.canli import paper_veri as pv
    if ayar.mod == "kuru":
        from motor.canli.borsa.kuru import KuruBorsa
        ist = pv.FapiIstemci()
        return KuruBorsa(lambda b: Decimal(str(ist.get("/fapi/v1/premiumIndex", {"symbol": b})["markPrice"])), s.tahsis_usd), ist.exchange_info()
    from motor.canli.borsa.binance_futures import BinanceFutures
    anahtar, gizli = ca.anahtarlar(s, env)
    b = BinanceFutures(ayar.mod, anahtar, gizli, kosullu_modu=ayar.kosullu_modu)
    b.zaman_esitle()
    return b, b.exchange_info()


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="1L3A canlı yürütücü")
    ap.add_argument("--ayar", default=None)
    ap.add_argument("--durum", default="durum_canli")
    ap.add_argument("--tohum", default=None)
    ap.add_argument("--tek-sefer", action="store_true")
    a = ap.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    try:
        ayar = ca.yukle(a.ayar)
        onkontrol(ayar)
    except (ca.CanliAyarHatasi, CanliDesteklemiyorHatasi) as e:
        log.error("canlı yürütücü BAŞLAMADI: %s", e)
        return 2
    from motor.canli import paper as pp, telegram as tg
    dizin = Path(a.durum)
    yurutuculer, tutucu, kontrol_edildi = {}, {}, set()
    hesap_yolu = _hesap_dosyasi(dizin)
    try:
        hesap = hesap_yukle(hesap_yolu)
    except SifirdanBaslamaHatasi as e:
        log.error("canlı yürütücü BAŞLAMADI: %s", e)
        return 2
    hesap_kayit = ck.HesapKaydi(dizin / "canli" / "ozsermaye_gunluk.jsonl")          # KAYIT: hesap toplamı + ortak zirve (servis başı ve her UTC günü)
    kayit_uyari = []

    def olay(tur, mesaj):
        p = tutucu.get("p")
        if p is not None:
            p.olay_ekle(tur, mesaj, bildir=False)

    from motor.canli.borsa import binance_futures as bf
    bf.yasak_yukle(dizin / YASAK_DOSYASI)                      # D3: 418/429 yasağı dosyada kalıcı; BinanceFutures/FapiIstemci (gerçek saat) ortak host bazlı yasağı yazar/okur
    for s in ayar.stratejiler:
        try:
            borsa, bilgi, b = baglan(ayar, s, bildir=tg.gonder)     # geçici hata: süreç içinde sınırsız backoff; yalnız kalıcı anahtar/ayar hatası -> 3
        except Exception as e:  # noqa: BLE001  (kalıcı hata: açık, mesajda gizli yok; BorsaHata metni zaten temizlenmiş)
            log.error("%s: borsa bağlantısı kurulamadı, KALICI hata (%s): %s", s.id, type(e).__name__, e)
            return 3
        try:
            api_kisit_dogrula(ayar, s, borsa, bildir=tg.gonder)    # O4: yalnız canlı; çekim izni açık / IP kısıtı yok -> başlamaz
        except ApiKisitHatasi as e:
            log.error("canlı yürütücü BAŞLAMADI: %s", e)
            return 2
        except Exception as e:  # noqa: BLE001  (kalıcı anahtar hatası)
            log.error("%s: API kısıt sorgusu KALICI hata (%s): %s", s.id, type(e).__name__, e)
            return 3
        log.info("%s: %s hesabı hazır, özsermaye %s, tahsis %s", s.id, ayar.mod, b["ozsermaye"], s.tahsis_usd)
        try:
            yurutuculer[s.id] = Yurutucu(s.id, borsa, bilgi, Ayar(ayar.mod, s.tahsis_usd, s.islem_risk, ayar.working_type, ayar.giris_gecikme_max_sn, ayar.hedef_emri, s.kaldirac),
                                         durum_yolu=_durum_dosyasi(dizin, s.id), olay=olay, bildir=tg.gonder)
        except SifirdanBaslamaHatasi as e:
            log.error("canlı yürütücü BAŞLAMADI: %s", e)
            return 2

    def kanca(p, simdi, yalniz_koruma: bool = False) -> None:
        """yalniz_koruma=True: paper turu yarıda kaldı (O2); yalnız hesap kill + kill kapatması + mutabakat/stop; giriş/motor_kapali/stop yükseltme YOK."""
        tutucu["p"] = p
        def son_mum(sembol, tf, t):
            df = p.kaynak.gecmis(sembol, tf, t)
            return df.index[-1] if len(df) else None
        def bozuk_mum(sembol, tf, t):                              # B7: paper_veri son kapalı mumu bozuk işaretlediyse giriş yok
            kaynak_bozuk = getattr(p.kaynak, "bozuk_mu", None)     # CanliKaynak bayrağı (attrs concat'te kaybolur)
            return bool(kaynak_bozuk(sembol, tf)) if kaynak_bozuk else False
        try:
            hesap_izle(yurutuculer, hesap, hesap_yolu)            # önce hesap düzeyi kill; sonra her strateji kendi turunu (kapatma dahil) yapar
        except Exception as e:  # noqa: BLE001  (hesap izleme hatası bireysel kill kapatmasını engellemesin)
            log.exception("hesap_izle başarısız")
            olay("canli_hesap_izle_hatasi", f"hesap izleme hatası ({type(e).__name__}: {str(e)[:150]}); yürütücü turları sürüyor")
        ilk_hata = None
        for sid, y in yurutuculer.items():
            try:
                h = p.hesaplar[sid]
                if sid not in kontrol_edildi and not yalniz_koruma:
                    uygunluk_kontrol(h.motor, h.birimler)         # fail-closed: desteklenmeyen kol varsa ilk turda açık hata, emir yok
                    kontrol_edildi.add(sid)
                g = gorunum(h.motor, h.birimler, son_mum, bozuk_mum)
            except Exception as e:  # noqa: BLE001  (görünüm/uygunluk hatası: giriş yok ama kill/mutabakat korumasını ENGELLEMEZ)
                log.exception("%s: görünüm/uygunluk hatası", sid)
                olay("canli_gorunum_hatasi", f"[{sid}] {type(e).__name__}: {str(e)[:200]}; bu turda yalnız koruma")
                ilk_hata = ilk_hata or e
                y.adim(MotorGorunumu(), yalniz_koruma=True)
                continue
            y.adim(g, yalniz_koruma=yalniz_koruma)
        if ilk_hata is not None:
            raise ilk_hata
        if yalniz_koruma:
            return
        try:
            hesap_kayit.yaz(hesap, simdi)
        except Exception as e:  # noqa: BLE001  (kayıt hatası işlemi durdurmaz; log + olay + (bir kez) Telegram: sessiz değil)
            log.error("hesap kaydı yazılamadı: %s: %s", type(e).__name__, str(e)[:200])
            olay("canli_kayit_hatasi", f"[hesap] ozsermaye_gunluk.jsonl hesap satırı yazılamadı ({type(e).__name__}); işlem akışı sürüyor")
            if not kayit_uyari:
                kayit_uyari.append(1)
                tg.gonder(f"🔴 <b>1L3A CANLI</b>: hesap kaydı (ozsermaye_gunluk.jsonl) yazılamadı: {type(e).__name__}. İşlem akışı sürüyor.")

    return pp.canli_calistir(dizin, Path(a.tohum) if a.tohum else None, tek_sefer=a.tek_sefer, tur_kancasi=kanca,
                             strateji_filtre=[s.id for s in ayar.stratejiler], telegram_sessiz=True)


if __name__ == "__main__":
    sys.exit(main())
