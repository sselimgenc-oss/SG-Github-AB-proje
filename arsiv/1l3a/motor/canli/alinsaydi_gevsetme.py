"""Alınsaydı öğrenme döngüsü: "alınsaydı" kârlı çıkan GİRİŞ FİLTRESİNİ KÂĞITTA otomatik gevşetir; kötü giderse otomatik geri alır (kullanıcı kararı 2026-11-19: "makine öğrendikçe karar versin").

YALNIZ KÂĞIT. Canlı yürütücü servisi (paper.canli_calistir'e `tur_kancasi`/`strateji_filtre` verilen) bu modülü HİÇ bağlamaz: `bagla(canli=True)` -> None; durum
dosyası canlı yolunda okunmaz. Canlıya geçiş ancak kalite kapısından geçen ayrı bir karar olur (bu dosya o yolu AÇMAZ).

KAPSAM (allowlist, fail-closed): yalnız sinyal kalite / giriş filtreleri: "etiket:<kural>" (etiket_kurallari: rejim_karsiti, takvim_olayi, kalabalik), "ders:<tip>"
(yaşayan ders) ve "ml_filtre". Risk kapıları (günlük kayıp, kaldıraç/risk tavanları, max_pozisyon, min_notional, kill, isınma, karantina, sembol işlem dışı,
açık_pozisyon...) KAPSAM DIŞIDIR: hiçbir koşulda gevşetilmez. Boyut/stop/hedef/limit bu modülde değişmez; yalnız bir girişi ATLATMAKTAN VAZGEÇİLİR (filtre devre dışı).

1) Gece (günde bir, TSİ 01:30 sonrası): her kapsam içi `neden` için son PENCERE_GUN günün alınmayan sinyalleri karar anından SONRAKİ mumlarla simüle edilir
   (araclar/alinmayan_sonuc.py; lookahead yok; brüt R). >= MIN_COZULEN çözülmüş VE ortalama R > 0 VE toplam R >= +MIN_TOPLAM_R -> o filtre gevşetilir (devre dışı;
   eşik adımı yok: en basit güvenli yol). Gecede en çok YENI_GEVSETME_GUNDE gevşetme (etki ayrışsın), en yüksek toplam R'li önce. Kara listedeki / zaten gevşek olan atlanır.
2) İzleme: gevşetme nedeniyle geçen (filtre aksi halde reddedecekti) girişler `gecisler`e yazılır; kapanan işlemleriyle eşlenir (gerçekleşen net R).
   Filtre başına >= GERI_AL_MIN_ISLEM işlemde toplam <= GERI_AL_TOPLAM_R -> OTOMATİK GERİ AL + kalıcı kara liste. Tüm aktif gevşetmelerin toplamı <= FREN_TOPLAM_R ->
   FREN: hepsi askıya alınır (kara listeye girmez), FREN_BEKLEME_GUN gün yeni gevşetme yok; ikinci fren kalıcı kilit (elle sıfırlanır).
3) Durum: `alinsaydi_gevsetme.json` (aktif, askida, kara_liste, fren, gecisler). Hesap/kol adı YAZILMAZ (yalnız kısaltılmış özet kimliği).
Kapatma: L3A_ALINSAYDI_GEVSETME_KAPALI=1. Hata -> paper etkilenmez (log; hatada filtre ESKİ haliyle çalışır).
"""
from __future__ import annotations

import hashlib
import logging
import os
from pathlib import Path
from typing import Callable, Optional

import pandas as pd

from motor.canli.durum import oku_json_varsayilan as _oku_json, yaz_json_sirali as _yaz_json  # noqa: E402
from motor.canli.kayit_etiketleri import _utc  # noqa: E402,F401

log = logging.getLogger("alinsaydi_gevsetme")

ENV_KAPALI = "L3A_ALINSAYDI_GEVSETME_KAPALI"
# ------------------------------------------------------------------ ön kayıt sabitleri (değişmez)
PENCERE_GUN = 30
GUN_SAAT_TSI = (1, 30)
MIN_COZULEN = 10
MIN_TOPLAM_R = 2.0                  # ve ortalama R > 0
YENI_GEVSETME_GUNDE = 1
GERI_AL_MIN_ISLEM = 10
GERI_AL_TOPLAM_R = -2.0
FREN_TOPLAM_R = -5.0
FREN_MIN_ISLEM = 5                  # fren: aktif gevşetmelerin toplam işlem sayısı >= bu VE toplam <= FREN_TOPLAM_R (kullanıcı kararı 2026-11-20)
FREN_BEKLEME_GUN = 7
GECIS_OMRU_GUN = 90
GECIS_ESLEME_GUN = 2                # gevşetme geçişi -> aynı kolun işlemi: giriş zamanı pencere
DURUM = "alinsaydi_gevsetme.json"

# Kapsam dışı nedenler (belgeleme/test amaçlı; asıl koruma ALLOWLIST'tir: burada olmayan zaten gevşetilemez)
RISK_NEDENLERI = frozenset({"gunluk_kayip_limiti", "kill_switch", "isinma", "kaldirac_tavani", "toplam_risk_tavani", "max_pozisyon", "min_qty", "min_notional",
                            "kaldirac_orantili", "gecersiz_stop", "gecersiz_hedef", "karantina", "sembol_islem_disi", "acik_pozisyon"})
ADLAR = {"etiket:rejim_karsiti": "rejime ters giriş", "etiket:takvim_olayi": "takvim olayı yakını", "etiket:kalabalik": "kalabalık pozisyon (fonlama/açık faiz)",
         "etiket:korku_acgozluluk": "aşırı korku/açgözlülük", "etiket:haber_ters": "ters haber akışı",
         "ml_filtre": "öğrenilmiş puan filtresi"}


def gevsetilebilir(neden) -> bool:
    """ALLOWLIST: yalnız giriş kalite filtreleri. Risk kapıları ve bilinmeyen nedenler False (fail-closed)."""
    if not isinstance(neden, str):
        return False
    from motor.canli import etiket_kurallari as ek
    if neden.startswith("etiket:"):
        return neden[len("etiket:"):] in ek.KURALLAR
    if neden.startswith("ders:"):
        return len(neden) > len("ders:")
    return neden == "ml_filtre"


def gorunur_ad(neden: str) -> str:
    return ADLAR.get(neden) or ("öğrenilmiş ders filtresi" if neden.startswith("ders:") else "giriş filtresi")


def kapali(env=None) -> bool:
    return (env if env is not None else os.environ).get(ENV_KAPALI) == "1"


def _kh(kimlik) -> str:
    """Kol kimliği hesap adı taşıyabilir: dosyaya yalnız kısaltılmış özet yazılır."""
    return hashlib.sha1(str(kimlik).encode("utf-8")).hexdigest()[:12]


# ---------------------------------------------------------------------------- ölçütler (saf)
def gevsetme_olcutu(r: list) -> bool:
    """>= MIN_COZULEN çözülmüş alınsaydı sonucu VE ortalama R > 0 VE toplam R >= +MIN_TOPLAM_R."""
    return len(r) >= MIN_COZULEN and sum(r) / len(r) > 0 and sum(r) >= MIN_TOPLAM_R


def geri_al_gerekli(r: list) -> bool:
    """Gevşetme sonrası gerçekleşen net R: >= GERI_AL_MIN_ISLEM işlem VE toplam <= GERI_AL_TOPLAM_R."""
    return len(r) >= GERI_AL_MIN_ISLEM and sum(r) <= GERI_AL_TOPLAM_R


def fren_gerekli(toplam_r: float, sayi: int = FREN_MIN_ISLEM) -> bool:
    return sayi >= FREN_MIN_ISLEM and toplam_r <= FREN_TOPLAM_R


# ---------------------------------------------------------------------------- servis
class AlinsaydiGevsetme:
    def __init__(self, dizin, gonder: Optional[Callable] = None, saat: Optional[Callable] = None, kapali_: Optional[bool] = None, ogrenme=None, canli: bool = False):
        self.dizin = Path(dizin)
        self.canli = bool(canli)
        self.kapali = self.canli or (kapali() if kapali_ is None else kapali_)      # canlıda HİÇBİR ŞEY okunmaz/uygulanmaz
        self.saat = saat or (lambda: pd.Timestamp.now(tz="UTC"))
        self.gonder = gonder or self._tg
        self.og = ogrenme
        self._p = None
        self._maske: frozenset = frozenset()
        self._ctx: Optional[dict] = None                   # çalışan _giris_izni çağrısı: {"h", "t", "e", "gecis": [neden]}
        self._og_hazir = False
        self.durum = {"aktif": {}, "askida": {}, "kara_liste": [], "fren": {}, "gecisler": [], "son_gun": None}
        if not self.kapali:
            d = _oku_json(self.dizin / DURUM, {})
            if isinstance(d, dict):
                self.durum.update({k: d[k] for k in self.durum if k in d})
            self.durum["aktif"] = {n: v for n, v in (self.durum["aktif"] or {}).items() if gevsetilebilir(n)}     # bozuk/elle eklenen risk kapısı süzülür

    # ------------------------------------------------------------ yardımcılar
    @property
    def aktif(self) -> dict:
        return {} if self.kapali else self.durum["aktif"]

    def _kaydet(self) -> None:
        _yaz_json(self.dizin / DURUM, self.durum)

    def _mesaj(self, metin: str) -> None:
        try:
            self.gonder(metin)
        except Exception:  # noqa: BLE001
            log.exception("alınsaydı gevşetme mesajı gönderilemedi")

    @staticmethod
    def _tg(metin: str) -> bool:
        from motor.canli import telegram as tg
        return tg.gonder(metin)

    def _hesaplar(self) -> list:
        return list(self._p.hesaplar.values()) if hasattr(self._p, "hesaplar") else [self._p]

    # ------------------------------------------------------------ bağlama
    def bagla(self, p):
        if self.kapali:
            return None
        self._p = p
        self._tak()
        adim = p.adim

        def adim_sarili(simdi, *a, **k):
            n = adim(simdi, *a, **k)
            try:
                self._tak()                                # sonradan eklenen hesaplar + öğrenme adaptörünün kanca tazelemesi
                self.tur(simdi)
            except Exception:  # noqa: BLE001
                log.exception("alınsaydı gevşetme turu hatası (paper etkilenmez)")
            return n
        p.adim = adim_sarili
        return self

    def _tak(self) -> None:
        self._og_tak()
        for h in self._hesaplar():
            m = h.motor
            if not getattr(m, "_gevsetme_izni_sarili", False):
                m._giris_izni = self._izni_sar(h, m._giris_izni)
                m._gevsetme_izni_sarili = True
            es = getattr(m, "etiket_suzgeci", None)
            if es is not None and not getattr(es, "_gevsetme", False):
                m.etiket_suzgeci = self._etiket_sar(h, es)
            gs = getattr(m, "giris_suzgeci", None)
            if self._og_hazir and gs is not None and gs == self._og_orig_suz:
                m.giris_suzgeci = self.og.giris_suzgeci

    def _izni_sar(self, h, orig):
        def izni(t, e):
            self._ctx = {"h": h, "t": t, "e": e, "gecis": []}
            try:
                ok = orig(t, e)
                if ok and self._ctx["gecis"]:
                    self._gecis_kaydet(e.kol, t, self._ctx["gecis"])
                return ok
            finally:
                self._ctx = None
        return izni

    def _gecis_kaydet(self, kol, t, nedenler: list) -> None:
        try:
            for n in nedenler:
                self.durum["gecisler"].append({"neden": n, "k": _kh(kol.kimlik), "t": _utc(t).isoformat()})
            self._kaydet()
        except Exception:  # noqa: BLE001
            log.exception("gevşetme geçişi kaydedilemedi")

    def _gecis_isaretle(self, neden: str) -> None:
        if self._ctx is not None:
            self._ctx["gecis"].append(neden)

    def _etiket_sar(self, h, orig):
        from motor.canli import etiket_kurallari as ek

        def suz(t, e):
            izin, neden = orig(t, e)
            if izin or neden not in self.aktif:
                return izin, neden
            try:                                           # gevşetilmiş kural(lar) hariç yeniden değerlendir: diğer kurallar hâlâ engeller
                gev = frozenset(n[len("etiket:"):] for n in self.aktif if n.startswith("etiket:"))
                n2 = ek.degerlendir("long" if e.yon == 1 else "short", h._etiket_uret(t, e.kol), devre_disi=gev)
            except Exception:  # noqa: BLE001
                log.exception("gevşetilmiş etiket kuralı yeniden değerlendirilemedi: eski karar (fail-closed)")
                return izin, neden
            if n2 is None:
                self._gecis_isaretle(neden)
                return True, ""
            return False, n2
        suz._gevsetme = True
        return suz

    def _og_tak(self) -> None:
        """ML filtre + ders: öğrenme adaptörünün (DEĞİŞMEZ) giris_suzgeci'ni sarar. Gevşetilmiş ders/ml hariç tutularak YENİDEN sorulur (diğer filtreler hâlâ engeller).
        Adaptör beklenen yüzeyi sunmuyorsa ders/ml gevşetilmez (fail-closed)."""
        og = self.og
        if og is None or self._og_hazir:
            return
        if not all(callable(getattr(og, a, None)) for a in ("giris_suzgeci", "_etkin_dersler", "_model")):
            log.warning("öğrenme adaptörü yüzeyi beklenenden farklı: ders/ml filtreleri gevşetilmeyecek")
            return
        o_suz, o_ders, o_model = og.giris_suzgeci, og._etkin_dersler, og._model
        self._og_orig_suz = o_suz

        def dersler():
            d = o_ders()
            return [k for k in d if f"ders:{str(k).split(':', 1)[0]}" not in self._maske] if self._maske else d

        def model(ad):
            return None if "ml_filtre" in self._maske else o_model(ad)

        def suz(strateji, sembol, yon, oz):
            self._maske = frozenset()
            izin, neden = o_suz(strateji, sembol, yon, oz)
            if izin or neden not in self.aktif:
                return izin, neden
            gecen = []
            try:                                           # gevşek filtreleri sırayla hariç tutarak yeniden sor: sıradaki GEVŞEMEMİŞ filtre hâlâ engeller
                while not izin and neden in self.aktif and neden not in gecen:
                    gecen.append(neden)
                    self._maske = frozenset(gecen)
                    izin, neden = o_suz(strateji, sembol, yon, oz)
            except Exception:  # noqa: BLE001
                log.exception("gevşetilmiş ders/ml yeniden değerlendirilemedi: giriş reddedildi (fail-closed)")
                return False, gecen[0] if gecen else neden
            finally:
                self._maske = frozenset()
            if izin:
                for n in gecen:
                    self._gecis_isaretle(n)
                return True, ""
            return izin, neden
        og._etkin_dersler, og._model, og.giris_suzgeci = dersler, model, suz
        self._og_hazir = True

    # ------------------------------------------------------------ tur
    def tur(self, simdi) -> None:
        if self.kapali:
            return
        self.gunluk(_utc(simdi))

    def gunluk(self, simdi) -> bool:
        """TSİ 01:30'dan sonra günde en çok bir kez. True: bu çağrıda çalıştı."""
        if self.kapali:
            return False
        simdi = _utc(simdi)
        tsi = simdi + pd.Timedelta(hours=3)
        gun = str(tsi.date())
        if (tsi.hour, tsi.minute) < GUN_SAAT_TSI or self.durum.get("son_gun") == gun:
            return False
        self.durum["son_gun"] = gun
        self._kaydet()                                     # önce işaretle: hata olursa aynı gün tekrar tekrar denenmez
        try:
            self.gece(simdi)
        except Exception:  # noqa: BLE001
            log.exception("alınsaydı gevşetme gecesi başarısız")
        return True

    def gece(self, simdi) -> dict:
        ozet = {"geri_alinan": self.izle(simdi)}
        f = self.durum.get("fren") or {}
        if f.get("aktif") and not f.get("kalici") and f.get("bitis") and simdi >= _utc(f["bitis"]):
            f["aktif"] = False                             # bekleme bitti: yeni gevşetme tekrar değerlendirilir (askıdakiler kendiliğinden geri gelmez)
            self._kaydet()
        ozet["yeni"] = [] if (self.durum.get("fren") or {}).get("aktif") else self.gevset(simdi)
        return ozet

    # ------------------------------------------------------------ 2) izleme / geri alma / fren
    def _islemler(self) -> dict:
        """{kol özeti: [(giris zamanı, R), ...]} sıralı; yalnız KAPANMIŞ işlemler."""
        out: dict = {}
        for h in self._hesaplar():
            for x in h.motor.islemler:
                try:
                    r = float(x["r"])
                    if r != r:
                        continue
                    out.setdefault(_kh(x["kol"]), []).append((_utc(x["giris_zamani"]), r))
                except (KeyError, TypeError, ValueError):
                    continue
        for v in out.values():
            v.sort(key=lambda a: a[0])
        return out

    def izleme_sonucu(self) -> dict:
        """{neden: [R...]}: aktif gevşetmeler için, gevşetmeden SONRA geçişle açılıp kapanan işlemlerin gerçekleşen net R'si (geçiş -> aynı kolun ilk işlemi, bire bir)."""
        isl = self._islemler()
        alinan: set = set()
        out = {n: [] for n in self.aktif}
        pencere = pd.Timedelta(days=GECIS_ESLEME_GUN)
        for g in sorted(self.durum["gecisler"], key=lambda g: g["t"]):
            a = self.aktif.get(g["neden"])
            if a is None or _utc(g["t"]) < _utc(a["zaman"]):
                continue
            t = _utc(g["t"])
            for i, (gz, r) in enumerate(isl.get(g["k"], [])):
                if (g["k"], i) not in alinan and t <= gz <= t + pencere:
                    alinan.add((g["k"], i))
                    out[g["neden"]].append(r)
                    break
        return out

    def izle(self, simdi) -> list:
        """Aktif gevşetmeleri sonuca göre geri alır / fren uygular. -> geri alınan (kara listeye giren) nedenler."""
        d = self.durum
        d["gecisler"] = [g for g in d["gecisler"] if _utc(g["t"]) >= simdi - pd.Timedelta(days=GECIS_OMRU_GUN)]
        if not self.aktif:
            self._kaydet()
            return []
        sonuc = self.izleme_sonucu()
        geri = []
        for neden, r in sorted(sonuc.items()):
            if geri_al_gerekli(r):
                geri.append(neden)
                del self.durum["aktif"][neden]
                if neden not in d["kara_liste"]:
                    d["kara_liste"].append(neden)
                self._mesaj(f"[1L3A] ⚠️ Kâğıt: «{gorunur_ad(neden)}» filtresi geri alındı, tekrar gevşetilmeyecek "
                            f"(gevşetme sonrası {len(r)} işlem, {sum(r):+.1f} R)")
        kalan = {n: r for n, r in sonuc.items() if n in self.aktif}          # fren: geri alma döngüsünden SONRA kalan aktif gevşetmeler
        toplam = sum(sum(r) for r in kalan.values())
        sayi = sum(len(r) for r in kalan.values())
        if self.aktif and fren_gerekli(toplam, sayi):
            askiya = sorted(self.aktif)
            for n in askiya:
                d["askida"][n] = self.durum["aktif"].pop(n)
            sayac = int((d.get("fren") or {}).get("sayac", 0)) + 1
            d["fren"] = {"aktif": True, "zaman": simdi.isoformat(), "bitis": (simdi + pd.Timedelta(days=FREN_BEKLEME_GUN)).isoformat(),
                         "toplam_r": round(toplam, 4), "sayac": sayac, "kalici": sayac >= 2}
            self._mesaj(f"[1L3A] ⚠️ Kâğıt: giriş gevşetmeleri askıya alındı (toplam {toplam:+.1f} R, {sayi} işlem); "
                        + ("kalıcı kilit, elle açılmalı" if sayac >= 2 else f"{FREN_BEKLEME_GUN} gün yeni gevşetme yok"))
        self._kaydet()
        return geri

    # ------------------------------------------------------------ 1) kanıt + gevşetme
    def kanit(self, simdi) -> dict:
        """{neden: {"sinyal", "cozulen", "toplam_r", "ort_r", "r": [...]}}: son PENCERE_GUN gün, yalnız kapsam içi nedenler, karar anından sonraki mumlarla."""
        from araclar import alinmayan_sonuc as asn
        from motor.canli.cikis_karsi_olgu import alinmayan_mum_getirici
        if not ((self.dizin / asn.DOSYA).exists() or (self.dizin / (asn.DOSYA + ".1")).exists()):
            return {}
        sinir = simdi - pd.Timedelta(days=PENCERE_GUN)
        h0 = self._hesaplar()[0]
        mum_getir = alinmayan_mum_getirici(h0, simdi)
        goruldu: set = set()
        g: dict = {}
        for s in asn.satirlari_oku(self.dizin):
            try:
                neden = s["neden"]
                if not gevsetilebilir(neden) or not (sinir <= _utc(s["zaman"]) <= simdi):
                    continue
                anahtar = (neden, s.get("hesap"), s.get("kol"), s["sembol"], s["yon"], s.get("fiyat"), s.get("stop"), s.get("hedef"))
                if anahtar in goruldu:                     # aynı kurulum art arda barlarda yeniden yazılmış olabilir: tek sayılır
                    continue
                goruldu.add(anahtar)
                m = mum_getir(s["sembol"], s.get("tf"))
                r = asn.simule(s, m)["r"] if m is not None else None
            except Exception:  # noqa: BLE001
                continue
            e = g.setdefault(neden, {"sinyal": 0, "r": []})
            e["sinyal"] += 1
            if r is not None and r == r:
                e["r"].append(float(r))
        for e in g.values():
            e["cozulen"] = len(e["r"])
            e["toplam_r"] = round(sum(e["r"]), 4)
            e["ort_r"] = round(sum(e["r"]) / len(e["r"]), 4) if e["r"] else None
        return g

    def _destek(self, neden: str) -> bool:
        """Bu filtre bu süreçte gerçekten atlatılabiliyor mu? (etiket: kural kancası; ders/ml: sarılmış öğrenme adaptörü)"""
        if neden.startswith("etiket:"):
            return True
        return self._og_hazir

    def gevset(self, simdi) -> list:
        d = self.durum
        if (d.get("fren") or {}).get("aktif"):
            return []
        adaylar = []
        for neden, e in self.kanit(simdi).items():
            if neden in self.aktif or neden in d["kara_liste"] or not self._destek(neden):
                continue
            if gevsetme_olcutu(e["r"]):
                adaylar.append((e["toplam_r"], neden, e))
        yeni = []
        for toplam, neden, e in sorted(adaylar, reverse=True)[:YENI_GEVSETME_GUNDE]:
            d["aktif"][neden] = {"zaman": simdi.isoformat(), "kanit": {"cozulen": e["cozulen"], "toplam_r": e["toplam_r"], "ort_r": e["ort_r"], "pencere_gun": PENCERE_GUN}}
            d["askida"].pop(neden, None)
            yeni.append(neden)
            log.info("Kâğıt: «%s» filtresi gevşetildi (alınsaydı %s sinyal, %+.1f R); sonuçlar izleniyor", gorunur_ad(neden), e["cozulen"], toplam)   # Telegram'a gitmez
        if yeni:
            self._kaydet()
        return yeni


def bagla(p, dizin, gonder: Optional[Callable] = None, ogrenme=None, canli: bool = False, env=None) -> Optional[AlinsaydiGevsetme]:
    """paper.canli_calistir tek satırı. Kapalıyken ya da CANLIDA (canli=True) None: hiçbir kanca bağlanmaz, durum dosyası okunmaz. Kurulum hatası paper'ı durdurmaz."""
    if canli or kapali(env):
        return None
    try:
        return AlinsaydiGevsetme(dizin, gonder, ogrenme=ogrenme).bagla(p)
    except Exception:  # noqa: BLE001
        log.exception("alınsaydı gevşetme bağlanamadı; paper onsuz sürer")
        return None
