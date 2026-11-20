"""ortak_ogrenme (1.2.0) -> 1L3A paper adaptörü. GÖLGE MOD YOK: ML filtre ve ders (aday + aktif), paper girişini doğrudan ATLATABİLİR.
Ders freni + geri alma bağlıdır (gece adımı `fren_adimi`): etkin derslerin toplam etkisi <= -FREN_ESIK_R ise etkin dersler askıya alınır ve ölçülmeye
devam eder (askıdan sonra etki > 0 olunca kendiliğinden döner, Telegram "Düzeldi"); tek ders <= -GERI_ALMA_R ise emekli edilir (geri alınır).
Etki, engellenen sinyallerin simüle R'siyle (kontrafaktüel, "alınmış" sayılır) hesaplanır. Bildirim: Bildirimci (6 saat kuralı).

Sınır (kod düzeyinde): öğrenme parçası yalnız bir YENİ girişe "hayır" diyebilir. Boyut, stop, hedef, limit, kaldıraç, risk tavanı ve
SERT_LIMITLER'e dokunamaz, yeni işlem açtıramaz (kanca motorda emir verilmeden hemen önce reddeder; bkz. paper_motor._giris_izni).
Drift eylemi (CUSUM uyarısı): kurulumun ML filtresi hemen yeniden eğitilir, dersin girişi atlatması yarıya iner (çarpan 0,5), durum JSON'una `drift` yazılır.
Hata -> giriş SERBEST (fail-open). `L3A_OGRENME_KAPALI=1` ile tamamen kapanır (kanca bağlanmaz). Paket `motor/ortak_ogrenme/` değiştirilmez.

Durum dizininde: ogrenme_adaylar.jsonl (kapanan işlemler), ogrenme_ders.json (ders yaşam döngüsü), ogrenme_modeller/ (filtre paketleri),
ogrenme_durum.json (eğitim/drift/ders günü), ogrenme_esleme.json (strateji kimliği <-> kurulum adı), ogrenme_karne.json (pano okur).
Kurulum adı yalnız harf/rakam/_ (README: `@` yasak): "dis__ewo-ema-ofset" -> "dis_ewo_ema_ofset"; çakışırsa kısa hash eklenir ve eşleme kalıcıdır.
"""
from __future__ import annotations

import hashlib
import json
import logging
import math
import os
import re
import shutil
from pathlib import Path
from typing import Callable, Optional

import numpy as np
import pandas as pd

from motor.canli.durum import oku_json_varsayilan as _oku_json, yaz_json_sirali as _yaz_json  # noqa: E402
from motor.canli.kayit_etiketleri import _utc  # noqa: E402,F401

from motor.ortak_ogrenme import ders, drift, karne as karne_mod
from motor.ortak_ogrenme import kayit as ok
from motor.ortak_ogrenme.notlar import not_yaz

try:                                              # numpy yoksa filtre YOK (ders/drift/karne çalışır)
    from motor.ortak_ogrenme import filtre
except ImportError:                               # pragma: no cover
    filtre = None

from motor.canli.hesap_adlari import hesap_adi  # noqa: E402

log = logging.getLogger("ogrenme")

ENV_KAPALI = "L3A_OGRENME_KAPALI"
MIN_EGITIM = 10            # altında filtre kurulmaz (2026-11-19 kullanıcı: temkin adımları küçültüldü, 30 -> 10; paket iki sınıf yoksa zaten None döner)
YENIDEN_GUN = 20           # paketin ömrü 21 gün: bir gün erken yenilenir ki ömür dolup boşluk kalmasın
YENIDEN_ISLEM = 10
DERS_SAAT_TSI = (0, 30)
ADAY_DOSYASI, DERS_DOSYASI, DURUM_DOSYASI = "ogrenme_adaylar.jsonl", "ogrenme_ders.json", "ogrenme_durum.json"
ESLEME_DOSYASI, KARNE_DOSYASI, MODEL_DIZINI = "ogrenme_esleme.json", "ogrenme_karne.json", "ogrenme_modeller"
FREN_DOSYASI = "ogrenme_fren.json"      # {"askida": {kimlik: {"zaman", "neden"}}}
FREN_ESIK_R, GERI_ALMA_R, FREN_PENCERE_GUN = 10.0, 3.0, 30     # ders.fren_durumu varsayılanları; pencere = son 30 gün
EGITIM_HATA_BEKLEME_SAAT = 1   # eğitim hatasından sonra aynı kurulum için bekleme
DRIFT_DERS_CARPANI = 0.5   # drift (CUSUM uyarı) veren kurulumda dersin girişi atlatma oranı: eşleşen sinyallerin yarısında ders etkisiz (CT: çarpan 0,5)
REJIMLER = ("trend_up", "trend_down", "range", "volatile", "unclear")


def kapali(env=None) -> bool:
    return (env if env is not None else os.environ).get(ENV_KAPALI) == "1"


def _sayi(x) -> bool:
    return isinstance(x, (int, float)) and not isinstance(x, bool) and math.isfinite(x)


# ---------------------------------------------------------------------------- kurulum adı eşlemesi
def temiz_ad(sk: str) -> str:
    return re.sub(r"_+", "_", re.sub(r"[^A-Za-z0-9_]", "_", str(sk))).strip("_") or "x"


class Esleme:
    """strateji kimliği <-> kurulum adı. Çakışmada sonradan gelen `_<hash>` alır; yazılan eşleme yeniden başlatmada korunur."""

    def __init__(self, yol: Optional[Path] = None):
        self.yol = yol
        self.ileri_t: dict = dict(_oku_json(yol, {})) if yol else {}
        self.ters_t = {v: k for k, v in self.ileri_t.items()}

    def ileri(self, sk: str) -> str:
        ad = self.ileri_t.get(sk)
        if ad is None:
            ad = temiz_ad(sk)
            if ad in self.ters_t:
                ad = f"{ad}_{hashlib.sha1(sk.encode('utf-8')).hexdigest()[:6]}"
            self.ileri_t[sk], self.ters_t[ad] = ad, sk
            if self.yol:
                try:
                    _yaz_json(self.yol, self.ileri_t)
                except Exception:  # noqa: BLE001
                    log.exception("kurulum eşlemesi yazılamadı")
        return ad

    def ters(self, ad: str) -> str:
        return self.ters_t.get(ad, ad)


# ---------------------------------------------------------------------------- özellikler (yalnız karar anına kadarki veri)
def etiket_ozellik(et: Optional[dict]) -> dict:
    """kayit_etiketleri çıktısı -> sayısal özellikler. Rejim one-hot (yalnız bilinen değerler)."""
    et, out = et or {}, {}
    for k in ("fonlama_orani", "korku_acgozluluk"):
        if _sayi(et.get(k)):
            out[k] = float(et[k])
    if "takvim_bayragi" in et:
        out["takvim_var"] = 0.0 if et["takvim_bayragi"] is None else 1.0
    for tf in ("4h", "1d"):
        if et.get(f"rejim_ml_{tf}") in REJIMLER:
            out[f"rejim_{tf}_{et[f'rejim_ml_{tf}']}"] = 1.0
    return out


def ozellik_sozlugu(yon: str, px, stop, hedef=None, atr14=None, atr_ratio=None, seans_kapali=None, etiketler=None) -> dict:
    px, stop = float(px), float(stop)
    oz = {"yon_long": 1.0 if yon == "long" else 0.0}
    if px > 0 and math.isfinite(stop):
        oz["stop_yuzde"] = abs(px - stop) / px
        if _sayi(atr14) and atr14 > 0:
            oz["stop_dist_atr"] = abs(px - stop) / atr14
        if hedef is not None and _sayi(float(hedef)) and px != stop:
            oz["rr"] = abs(float(hedef) - px) / abs(px - stop)
    if _sayi(atr_ratio):
        oz["atr_ratio"] = float(atr_ratio)
    if seans_kapali is not None:
        oz["seans_kapali"] = float(seans_kapali)
    oz.update(etiket_ozellik(etiketler))
    return oz


def atr_ozellikleri(df: Optional[pd.DataFrame]) -> tuple:
    """(atr14, atr_ratio = atr14 / son 50 TR ortalaması). df yalnız karar anına kadarki kapanmış mumlar. Yetersizse (None, None)."""
    try:
        if df is None or len(df) < 51:
            return None, None
        h, l, c = (df[k].to_numpy(dtype=float)[-51:] for k in ("yuksek", "dusuk", "kapanis"))
        tr = np.maximum(h[1:] - l[1:], np.maximum(np.abs(h[1:] - c[:-1]), np.abs(l[1:] - c[:-1])))
        atr14, atr50 = float(tr[-14:].mean()), float(tr.mean())
        return (atr14, atr14 / atr50) if atr50 > 0 and math.isfinite(atr14) else (None, None)
    except Exception:  # noqa: BLE001
        return None, None


def _seans_kapali(sembol: str, t) -> Optional[float]:
    from motor.canli.paper_takvim import seans_maskesi, tur
    if tur(sembol) == "kripto":
        return None
    return 0.0 if bool(seans_maskesi(sembol, pd.DatetimeIndex([_utc(t)]))[0]) else 1.0


# ---------------------------------------------------------------------------- Aday çevirisi
def _gorunum(oz: dict) -> dict:
    return {k: float(v) for k, v in (oz or {}).items() if _sayi(v)}


def _seans_etiketi(sinif: str, oz: dict) -> Optional[str]:
    if sinif == "kripto" or "seans_kapali" not in oz:
        return None
    return "closed" if oz["seans_kapali"] >= 1 else "open"


def _rejim(oz: dict, etiketler: Optional[dict]) -> Optional[str]:
    r = (etiketler or {}).get("rejim_ml_4h")
    return r if r in REJIMLER else None


def islem_adayi(satir: dict, ozellik: Optional[dict], esleme: Esleme, id_: Optional[str] = None) -> ok.Aday:
    """paper_durum._islem_satiri çıktısı (+ girişte saklanan özellikler) -> Aday (alindi=True, r = net R ya da None).
    ts = giriş zamanı (karar anı: giriş, karar mumunun kapanışında verilen emrin ilk açılışıdır)."""
    from motor.canli.paper_takvim import tur
    oz = _gorunum(ozellik)
    sinif = tur(satir["sembol"])
    cikis = {"exit_reason": satir.get("cikis_nedeni"), "cikis_zamani": satir.get("cikis_zamani"), "mfe_r": satir.get("mfe_r"), "mae_r": satir.get("mae_r")}
    try:
        cikis["entry_price"] = float(satir["giris_fiyati"])
    except (TypeError, ValueError):
        pass
    r = satir.get("r")
    return ok.Aday(id=id_ or f"{satir['kimlik']}|{satir['sembol']}|{satir['giris_zamani']}", proje="1L3A", kurulum=esleme.ileri(satir["kimlik"]),
                   enstruman=satir["sembol"], varlik_sinifi=sinif, yon=satir["yon"], ts=_utc(satir["giris_zamani"]).to_pydatetime(),
                   alindi=True, r=float(r) if _sayi(r) else None, seans=_seans_etiketi(sinif, oz), rejim=_rejim(oz, satir),
                   ozellikler=oz, cikis=cikis)


def alinmayan_adayi(satir: dict, esleme: Esleme) -> ok.Aday:
    """alinmayan_sinyaller.jsonl satırı -> Aday (alindi=False, r=None). Özellikler satırdaki fiyat/stop/hedef + kayıt etiketlerinden."""
    from motor.canli.paper_takvim import tur
    f = lambda k: float(satir[k]) if satir.get(k) not in (None, "") else None
    px, stop = f("fiyat"), f("stop")
    oz = ozellik_sozlugu(satir["yon"], px, stop, f("hedef"), etiketler=satir) if px and stop is not None else {}
    sinif = tur(satir["sembol"])
    return ok.Aday(id=f"alinmadi|{satir.get('hesap')}|{satir['kol']}|{satir['zaman']}|{satir['neden']}", proje="1L3A",
                   kurulum=esleme.ileri(satir["strateji"]), enstruman=satir["sembol"], varlik_sinifi=sinif, yon=satir["yon"],
                   ts=_utc(satir["zaman"]).to_pydatetime(), alindi=False, r=None, rejim=_rejim(oz, satir), ozellikler=oz,
                   etiketler=(f"neden:{satir['neden']}",))


# ---------------------------------------------------------------------------- adaptör
class Ogrenme:
    def __init__(self, dizin, gonder: Optional[Callable] = None, saat: Optional[Callable] = None, kapali_: Optional[bool] = None):
        self.dizin = Path(dizin)
        self.kapali = kapali() if kapali_ is None else kapali_
        self.saat = saat or (lambda: pd.Timestamp.now(tz="UTC"))
        self.gonder = gonder or self._tg
        self.esleme = Esleme(self.dizin / ESLEME_DOSYASI)
        self.durum = _oku_json(self.dizin / DURUM_DOSYASI, {})
        self.kapananlar = self._aday_oku(self.dizin / ADAY_DOSYASI)
        self._gorulen = {a.id for a in self.kapananlar}
        self._modeller: dict = {}
        self._ders_birikim: dict = {}                 # {kurulum: ders çarpanı birikimi} (drift sırasında deterministik "her ikinci eşleşmede ders etkisiz")

    @staticmethod
    def _aday_oku(yol: Path) -> list:
        """Aday dosyasını satır satır okur: bozuk satır atlanır (geçmiş düşmez); bozuk varsa dosya `.bozuk` olarak yedeklenir (varsa üstüne yazılmaz)."""
        if not yol.exists():
            return []
        out, bozuk = [], 0
        try:
            with yol.open(encoding="utf-8") as fh:
                for satir in fh:
                    satir = satir.strip()
                    if not satir:
                        continue
                    try:
                        out.append(ok.aday_from_dict(json.loads(satir)))
                    except Exception:  # noqa: BLE001
                        bozuk += 1
        except (OSError, UnicodeDecodeError):
            log.exception("öğrenme aday dosyası okunamadı")
            bozuk += 1
        if bozuk:
            hedef, i = yol.with_name(yol.name + ".bozuk"), 0
            while hedef.exists():
                i += 1
                hedef = yol.with_name(f"{yol.name}.bozuk.{i}")
            try:
                shutil.copy2(yol, hedef)
            except OSError:
                log.exception("bozuk aday dosyası yedeklenemedi")
            log.warning("öğrenme aday dosyasında %d bozuk satır atlandı; yedek: %s", bozuk, hedef.name)
        return out

    @staticmethod
    def _tg(metin: str) -> bool:
        from motor.canli import telegram as tg
        return tg.gonder(metin)

    def _durum_yaz(self) -> None:
        _yaz_json(self.dizin / DURUM_DOSYASI, self.durum)

    # ------------------------------------------------------------ bağlama
    def bagla(self, p):
        """Paper'a (ya da v2'de her hesabına) kancaları takar ve p.adim'i tur sonrası öğrenme turuyla sarar. Kapalıyken hiçbir şey yapmaz."""
        if self.kapali:
            return None
        self._p = p
        self._kanca_tak()
        adim = p.adim

        def adim_sarili(simdi, *a, **k):
            n = adim(simdi, *a, **k)
            try:
                self.tur(simdi)
            except Exception:  # noqa: BLE001
                log.exception("öğrenme turu hatası (paper etkilenmez)")
            return n
        p.adim = adim_sarili
        return self

    def _hesaplar(self) -> list:
        return list(self._p.hesaplar.values()) if hasattr(self._p, "hesaplar") else [self._p]

    def _gorunur_mi(self, kimlik: str) -> bool:
        """Hesap görünür mü (cikis_karsi_olgu._ad_gorunur mantığı). Paper bağlı değilse görünür; bağlıyken bilinmeyen hesap kapalı-başarısız (gizli)."""
        p = getattr(self, "_p", None)
        if p is None:
            return True
        hs = getattr(p, "hesaplar", None)
        if hs is None:
            return bool(getattr(p, "gorunur", True))
        h0 = str(kimlik).split("|")[0]
        h = hs.get(h0)
        if h is not None:
            return bool(getattr(h, "gorunur", True))
        ga = getattr(p, "gorunur_adlar", None)
        return ga is not None and h0 in ga

    def _ad_goster(self, kimlik: str) -> str:
        """Telegram/log için ad: gizli hesapsa "Diğer hesap" (gerçek ad asla yazılmaz)."""
        return hesap_adi(kimlik, gorunur=self._gorunur_mi(kimlik))

    def _kanca_tak(self) -> None:
        for h in self._hesaplar():                              # v2: sonradan eklenen hesaplar da (yeni_hesaplari_baslat)
            if h.motor.giris_suzgeci != self.giris_suzgeci:
                h.motor.giris_suzgeci = self.giris_suzgeci
                h.motor.ozellik_kancasi = lambda t, e, h=h: self.ozellik_uret(h, t, e)

    def ozellik_uret(self, h, t, e) -> dict:
        kol = e.kol
        td = h.tanim_ad.get(kol.birim)
        df = None
        if td is not None:                                      # t'den ÖNCE kapanmış mumlar (t'nin kendi mumu karar anında bilinmez)
            df = h.kaynak.gecmis(kol.sembol, td.tf, _utc(t))
            df = df[df.index < _utc(t)]
        atr14, atr_oran = atr_ozellikleri(df)
        et = h._etiket_uret(t, kol) if getattr(h, "kayit", None) is not None else None
        return ozellik_sozlugu("long" if e.yon == 1 else "short", e.px, e.stop, e.hedef, atr14, atr_oran, _seans_kapali(kol.sembol, t), et)

    # ------------------------------------------------------------ giriş süzgeci
    def _etkin_dersler(self) -> list:
        """candidate + alive dersler (askıdakiler hariç): aday ders de girişi atlatır (gölge yok); fren/geri alma devrede."""
        st = _oku_json(self.dizin / DERS_DOSYASI, {})
        askida = _oku_json(self.dizin / FREN_DOSYASI, {}).get("askida", {})
        return [k for k, v in st.items() if isinstance(v, dict) and v.get("status") in ("candidate", "alive") and k not in askida]

    def _model(self, ad: str):
        if ad not in self._modeller:
            yol = self.dizin / MODEL_DIZINI / f"{ad}.json"
            self._modeller[ad] = _oku_json(yol, None) if yol.exists() else None
        return self._modeller[ad]

    def giris_suzgeci(self, strateji: str, sembol: str, yon: str, oz: dict) -> tuple:
        """(izin, neden). Yalnız bir girişi atlatabilir. Aday (candidate) ve aktif (alive) ders engeller; askıdaki (fren) ve emekli ders engellemez."""
        if self.kapali:
            return True, ""
        simdi, ad = self.saat(), self.esleme.ileri(strateji)
        from motor.canli.paper_takvim import tur
        sinif = tur(sembol)
        taslak = ok.Aday(id="karar", proje="1L3A", kurulum=ad, enstruman=sembol, varlik_sinifi=sinif, yon=yon, ts=simdi.to_pydatetime(),
                         alindi=False, r=None, seans=_seans_etiketi(sinif, oz), ozellikler=_gorunum(oz))
        for kimlik in ders.uyan_dersler(self._etkin_dersler(), taslak):
            c = self.ders_carpani(ad)
            if c < 1.0:                                        # drift: ders etkisi çarpan oranında (0,5 -> eşleşmelerin yarısında ders atlatmaz; ML filtre aynen)
                b = self._ders_birikim.get(ad, 0.0) + c
                if b < 1.0 - 1e-9:
                    self._ders_birikim[ad] = b
                    break
                self._ders_birikim[ad] = b - 1.0
            return False, f"ders:{kimlik.split(':', 1)[0]}"
        paket = self._model(ad) if filtre is not None else None
        if paket is not None:
            try:
                paket = filtre.yukle(paket, simdi=simdi.to_pydatetime())     # hash + süre denetimi; hata -> filtre yok
            except ValueError as e:
                log.warning("ML filtre (%s) geçersiz/süresi dolmuş, filtre YOK: %s", ad, e)
                return True, ""
            if filtre.puan(paket, oz) < paket["esik"]:
                return False, "ml_filtre"
        return True, ""

    # ------------------------------------------------------------ tur: yeni kapanan işlemler, yeniden eğitim, günlük adım
    def tur(self, simdi) -> None:
        if self.kapali:
            return
        simdi = _utc(simdi)
        self._kanca_tak()
        self._yeni_islemler()
        self._egit_kontrol(simdi)
        self.gunluk(simdi)

    def _yeni_islemler(self) -> None:
        from motor.canli import paper_durum as pdr
        yeni = []
        for h in self._hesaplar():
            for x in h.motor.islemler:
                id_ = f"{x['kol']}|{x['giris_zamani']}|{x['cikis_zamani']}"
                if id_ in self._gorulen:
                    continue
                try:
                    yeni.append(islem_adayi(pdr._islem_satiri(h, x), x.get("ogrenme_ozellik"), self.esleme, id_))
                    self._gorulen.add(id_)
                except Exception:  # noqa: BLE001
                    log.exception("kapanan işlem Aday'a çevrilemedi")
        if yeni:
            self.kapananlar.extend(yeni)
            ok.yaz_jsonl(self.dizin / ADAY_DOSYASI, self.kapananlar)

    def egitim_adaylari(self, ad: str, karar_ts=None) -> list:
        """Eğitim verisi: yalnız bu kurulumun alınmış, R'si bilinen ve karar anından ÖNCE kapanmış işlemleri."""
        bitis = None if karar_ts is None else _utc(karar_ts)
        return [a for a in self.kapananlar if a.kurulum == ad and a.r is not None
                and (bitis is None or (a.cikis.get("cikis_zamani") and _utc(a.cikis["cikis_zamani"]) <= bitis))]

    def _egit_kontrol(self, simdi) -> None:
        if filtre is None:
            return
        ed = self.durum.setdefault("egitim", {})
        hata = self.durum.setdefault("egitim_hata", {})
        for ad in sorted({a.kurulum for a in self.kapananlar}):
            if ad in hata and simdi - _utc(hata[ad]) < pd.Timedelta(hours=EGITIM_HATA_BEKLEME_SAAT):
                continue                                           # eğitim yakın zamanda hata verdi: her turda tekrar denenmez
            n = len(self.egitim_adaylari(ad, simdi))
            son = ed.get(ad)
            if n < MIN_EGITIM or (son and n - son["n"] < YENIDEN_ISLEM and simdi - _utc(son["zaman"]) < pd.Timedelta(days=YENIDEN_GUN)):
                continue
            self._egit_bir(ad, simdi, n)

    def _egit_bir(self, ad: str, simdi, n: int) -> str:
        """Tek kurulumun filtresini şimdi eğitir. -> 'egitildi' | 'model_yok' (tek sınıf: filtre yok) | 'hata'."""
        ed = self.durum.setdefault("egitim", {})
        try:
            paket = filtre.egit(ad, self.egitim_adaylari(ad, simdi), olusturma=simdi.to_pydatetime())
            yol = self.dizin / MODEL_DIZINI / f"{ad}.json"
            if paket is not None:
                filtre.kaydet(paket, self.dizin / MODEL_DIZINI)
            elif yol.exists():
                yol.unlink()                                       # tek sınıf: eski model de geçersiz sayılır -> filtre YOK
            self._modeller[ad] = paket
            ed[ad] = {"zaman": simdi.isoformat(), "n": n, "model": paket is not None}
            self.durum.get("egitim_hata", {}).pop(ad, None)
            self._durum_yaz()
            return "egitildi" if paket is not None else "model_yok"
        except Exception:  # noqa: BLE001
            log.exception("filtre eğitimi başarısız (%s): eski model/filtre-yok durumu sürer", ad)
            self.durum.setdefault("egitim_hata", {})[ad] = simdi.isoformat()
            try:
                self._durum_yaz()
            except Exception:  # noqa: BLE001
                log.exception("eğitim hata kaydı yazılamadı")
            return "hata"

    def ders_carpani(self, ad: str) -> float:
        """Kurulumun ders çarpanı: drift uyarısı sürerken DRIFT_DERS_CARPANI (0,5), değilse 1,0. Uyarı bitince (CUSUM normal) kendiliğinden 1,0."""
        return DRIFT_DERS_CARPANI if ad in self.durum.get("drift_uyari", []) else 1.0

    def alinmayanlar(self) -> list:
        out = []
        for yol in (self.dizin / "alinmayan_sinyaller.jsonl",):
            if not yol.exists():
                continue
            for s in yol.read_text(encoding="utf-8").splitlines():
                try:
                    out.append(alinmayan_adayi(json.loads(s), self.esleme))
                except Exception:  # noqa: BLE001
                    continue
        return out

    def gunluk(self, simdi) -> bool:
        """TSİ 00:30'dan sonra, günde en çok bir kez: ders gece adımı + drift + karne. True: bu çağrıda çalıştı."""
        simdi = _utc(simdi)
        tsi = simdi + pd.Timedelta(hours=3)
        gun = str(tsi.date())
        if (tsi.hour, tsi.minute) < DERS_SAAT_TSI or self.durum.get("son_ders_gunu") == gun:
            return False
        self.durum["son_ders_gunu"] = gun
        self._durum_yaz()                                          # önce işaretle: hata olursa aynı gün tekrar tekrar denenmez
        adaylar = self.kapananlar + self.alinmayanlar()
        notlar = []
        for a in self.kapananlar:
            if a.r is None:
                continue
            try:
                notlar.append({"note_date": str(_utc(a.cikis.get("cikis_zamani") or a.ts).date()), "tags": not_yaz(a)[0]})
            except ValueError:
                continue
        gecis = {}
        try:
            gecis = ders.gece_adimi(adaylar, notlar, self.dizin / DERS_DOSYASI, str(simdi.date()))
        except Exception:  # noqa: BLE001
            log.exception("ders gece adımı hatası (karne yine yazılır)")
        engel: Optional[list] = None
        try:
            engel = self.engellenenler(simdi)                      # bir kez hesaplanır (aday ders gözlemi + fren ölçümü ortak)
            gecis["aday_karsi_olgu"] = self.aday_karsi_olgu(engel, simdi)
        except Exception:  # noqa: BLE001
            log.exception("aday ders karşı-olgu adımı hatası (paper etkilenmez; aday ders olduğu gibi sürer)")
        try:
            gecis["fren"] = self.fren_adimi(simdi) if engel is None else self.fren_adimi(simdi, engel)
        except Exception:  # noqa: BLE001
            log.exception("ders freni adımı hatası (paper etkilenmez; mevcut askı/emekli durumu sürer)")
        try:
            self._drift_bildir(adaylar, simdi)
        except Exception:  # noqa: BLE001
            log.exception("drift adımı hatası (karne yine yazılır)")
        self._karne_yaz(adaylar, gecis, simdi)
        return True

    # ------------------------------------------------------------ ders freni + geri alma (gece adımı)
    def _bildir(self, anahtar: str, metin: str) -> None:
        try:
            if getattr(self, "bildirimci", None) is None:
                from motor.canli import telegram as tg
                self.bildirimci = tg.Bildirimci(gonder_fn=self.gonder, ortak=tg.ortak_durum(), servis=tg.SERVIS_ADI)
            self.bildirimci.mesaj(anahtar, metin)               # Bildirimci: 6 saat kuralı (kalıcı); hata motoru etkilemez
        except Exception:  # noqa: BLE001
            log.exception("ders freni bildirimi gönderilemedi")

    def engellenenler(self, simdi) -> list:
        """Ders yüzünden atlanan sinyaller ('ders:' nedeni, son FREN_PENCERE_GUN gün), karar anından sonraki mumlarla simüle edilir; çözülenler
        'alınmış' Aday (r = brüt simüle R). Kontrafaktüel: yalnız fren/geri alma ölçümü içindir. Veri/hata -> o sinyal atlanır."""
        from araclar import alinmayan_sonuc as asn
        h0, sinir, onb, out = self._hesaplar()[0], _utc(simdi) - pd.Timedelta(days=FREN_PENCERE_GUN), {}, []
        for s in asn.satirlari_oku(self.dizin):
            try:
                if not str(s.get("neden", "")).startswith("ders:") or _utc(s["zaman"]) < sinir:
                    continue
                k = (s["sembol"], s.get("tf"))
                if k not in onb:
                    df = h0.kaynak.gecmis(s["sembol"], s.get("tf"), _utc(simdi))
                    onb[k] = df if len(df) else None
                if onb[k] is None:
                    continue
                r = asn.simule(s, onb[k]).get("r")
                if not _sayi(r):
                    continue
                a = alinmayan_adayi(s, self.esleme)
                out.append(ok.Aday(id="kf|" + a.id, proje=a.proje, kurulum=a.kurulum, enstruman=a.enstruman, varlik_sinifi=a.varlik_sinifi,
                                   yon=a.yon, ts=a.ts, alindi=True, r=float(r), seans=a.seans, rejim=a.rejim, ozellikler=a.ozellikler))
            except Exception:  # noqa: BLE001
                continue
        return out

    def aday_karsi_olgu(self, engel: list, simdi) -> dict:
        """C3: girişi ENGELLEYEN aday ders alınmış işlem üretmez, ders.gece_adimi'nde n=0 kalıp süresiz engelleyebilir. Yalnız hâlâ 'candidate' ve
        gözlemsiz (n=0) dersler için, engellediği girişlerin karşı-olgusu (alınsaydı sonucu: engellenenler(); alindi=True, brüt R) gözlem sayılır
        ve ders.py ölçütü aynen uygulanır: etki = -toplam R; etki > 0 -> alive (engellenenler kaybettirecekti), etki <= 0 -> emekli (kazandıracaktı).
        ders.py'ye dokunulmaz; alive/emekli dersler bu adımda ELE ALINMAZ (onların ölçümü gece adımı + fren adımında). Dönüş: {"alive", "retired"}."""
        simdi = _utc(simdi)
        ders_yolu = self.dizin / DERS_DOSYASI
        st = ders._yukle(ders_yolu)
        out: dict = {"alive": [], "retired": []}
        for lid, v in sorted(st.items()):
            if not isinstance(v, dict) or v.get("status") != "candidate" or v.get("n"):
                continue
            try:
                eff, n = ders.ders_etkisi(engel, lid, v["born"], simdi.to_pydatetime())
            except (KeyError, ValueError):
                continue
            if n == 0:
                continue
            v["effect"], v["n"] = round(eff, 6), n
            if eff > 0:
                v["status"] = "alive"
                out["alive"].append(lid)
            else:
                v["status"], v["retired_day"] = "retired", str(simdi.date())
                out["retired"].append(lid)
        if out["alive"] or out["retired"]:
            ders._kaydet(ders_yolu, st)
            log.info("aday ders karşı-olgu gözlemi: alive=%s retired=%s", out["alive"], out["retired"])
        return out

    def fren_adimi(self, simdi, engellenen: Optional[list] = None) -> dict:
        """Gece, ders gece adımından sonra: (1) askıdaki dersleri askıdan sonraki veriyle yeniden ölç (etki > 0 -> döner + 'Düzeldi';
        <= -GERI_ALMA_R -> emekli), (2) etkin derslerde tek tek <= -GERI_ALMA_R olanı geri al (emekli), (3) kalan etkin derslerin toplam etkisi
        <= -FREN_ESIK_R ise hepsini askıya al (askıdayken ölçülmeye devam)."""
        simdi = _utc(simdi)
        ders_yolu, fren_yolu = self.dizin / DERS_DOSYASI, self.dizin / FREN_DOSYASI
        st = ders._yukle(ders_yolu)
        askida = dict(_oku_json(fren_yolu, {}).get("askida", {}))
        etkin = [k for k, v in st.items() if isinstance(v, dict) and v.get("status") in ("candidate", "alive")]
        sonuc = {"askiya": [], "geri_alinan": [], "dondu": []}
        askida = {k: v for k, v in askida.items() if k in etkin}              # emekli olan askıdan düşer
        if not etkin:
            _yaz_json(fren_yolu, {"askida": askida})
            return sonuc
        adaylar = list(self.kapananlar) + (engellenen if engellenen is not None else self.engellenenler(simdi))
        pencere_basi = simdi - pd.Timedelta(days=FREN_PENCERE_GUN)

        def olc(kimlik, baslangic):
            dogum = (st.get(kimlik) or {}).get("born")           # ders.py ile tutarlı: etki doğum gününün ertesi 00:00 UTC'den başlar
            try:
                baslangic = max(baslangic, _utc(dogum) + pd.Timedelta(days=1))
            except (TypeError, ValueError):
                pass
            return ders.fren_durumu(adaylar, [kimlik], baslangic.to_pydatetime(), simdi.to_pydatetime(), FREN_ESIK_R, GERI_ALMA_R)
        geri = []
        for k in [k for k in etkin if k in askida]:
            r = olc(k, max(_utc(askida[k]["zaman"]), pencere_basi))
            if r["geri_al"]:
                geri.append(k)
            elif r["toplam_etki"] > 0:
                askida.pop(k)
                sonuc["dondu"].append(k)
        aktif = [k for k in etkin if k not in askida and k not in geri]
        toplam = 0.0
        for k in aktif:
            r = olc(k, pencere_basi)
            if r["geri_al"]:
                geri.append(k)
            else:
                toplam += r["toplam_etki"]
        for k in geri:                                                         # geri alma: emekli (paket: emekli geri dönmez)
            st[k]["status"], st[k]["retired_day"] = "retired", str(simdi.date())
            askida.pop(k, None)
        sonuc["geri_alinan"] = geri
        if toplam <= -FREN_ESIK_R:
            for k in aktif:
                if k not in geri:
                    askida[k] = {"zaman": simdi.isoformat(), "neden": "fren"}
                    sonuc["askiya"].append(k)
        if geri:
            ders._kaydet(ders_yolu, st)
        _yaz_json(fren_yolu, {"askida": askida, "toplam_etki": round(toplam, 4), "zaman": simdi.isoformat()})
        ad = lambda lst: ", ".join(self._ad_goster(self.esleme.ters(x.partition(":")[2])) + " (" + x.partition(":")[0].replace("_", " ") + ")" for x in lst)    # noqa: E731
        if geri:
            self._bildir("ders_geri_al", f"[1L3A] ⚠️ Kötü giden ders kaldırıldı: {ad(geri)}\nBu ders artık işlemleri etkilemiyor.\nSenden bir şey gerekmiyor.")
        if sonuc["askiya"]:
            self._bildir("ders_fren", f"[1L3A] ⚠️ Dersler durduruldu: toplam etkileri {toplam:+.1f} R (sınır -{FREN_ESIK_R:g} R)\n"
                         f"Durdurulanlar: {ad(sonuc['askiya'])}. Ölçülmeye devam ediliyor.\nSenden bir şey gerekmiyor.")
        if sonuc["dondu"]:
            self._bildir("ders_duzeldi", f"[1L3A] Düzeldi: ders yeniden devrede: {ad(sonuc['dondu'])}.")
        return sonuc

    def _drift_bildir(self, adaylar, simdi=None) -> None:
        """Drift (CUSUM) eylemi: yeni uyarı veren her kurulumda (a) ML filtre HEMEN yeniden eğitilir, (b) ders çarpanı 0,5 (uyarı sürerken),
        (c) durum JSON'una `drift` alanı (pano sonra okur); Telegram mesajı YOK, yalnız log. Eylem hatası paper'ı etkilemez."""
        simdi = _utc(simdi if simdi is not None else self.saat())
        d = drift.kurulum_drift(adaylar)
        uyari = sorted(k for k, v in d.items() if v["durum"] == "uyari")
        onceki = set(self.durum.get("drift_uyari", []))
        yeni = [k for k in uyari if k not in onceki]
        self.durum["drift_uyari"] = uyari
        eski_kayit = (self.durum.get("drift") or {}).get("kurulumlar", {})
        kayit = {}
        for k in uyari:
            e = dict(eski_kayit.get(k) or {})
            if k in yeni or not e:
                e["tespit_zamani"] = simdi.isoformat()
                try:
                    n = len(self.egitim_adaylari(k, simdi))
                    e["yeniden_egitim"] = "yetersiz_veri" if n < MIN_EGITIM else "filtre_yok" if filtre is None else self._egit_bir(k, simdi, n)
                except Exception:  # noqa: BLE001
                    log.exception("drift: yeniden eğitim hatası (%s)", k)
                    e["yeniden_egitim"] = "hata"
            e.update({"strateji": self.esleme.ters(k), "durum": "uyari", "ders_carpani": self.ders_carpani(k), "S": d[k]["S"], "n": d[k]["n"]})
            kayit[k] = e
        self.durum["drift"] = {"zaman": simdi.isoformat(), "carpan": DRIFT_DERS_CARPANI, "uyari_sayisi": len(uyari), "kurulumlar": kayit}
        if yeni:                                                   # yalnız log (yeni uyarı veren tüm kurulumlar); işlemi etkilemez
            adlar = ", ".join(self._ad_goster(self.esleme.ters(k)) for k in yeni)
            egitildi = sum(1 for k in yeni if kayit[k].get("yeniden_egitim") == "egitildi")
            log.info("Beklenenden kötü gidiyor: %s; makine öğrenmesi yeniden eğitildi (%d/%d), derslerin etkisi geçici olarak yarıya indirildi",
                     adlar, egitildi, len(yeni))                   # Telegram'a gitmez (kullanıcı kararı 2026-11-20), yalnız log
        self._durum_yaz()

    def _karne_yaz(self, adaylar, gecis, simdi) -> None:
        try:
            _yaz_json(self.dizin / KARNE_DOSYASI, {
                "zaman": simdi.isoformat(), "surum": "ortak_ogrenme 1.2.0", "esleme": self.esleme.ileri_t, "karne": karne_mod.karne(adaylar),
                "sanal_kasa": karne_mod.sanal_kasa(adaylar), "drift": {k: v for k, v in drift.kurulum_drift(adaylar).items()},
                "ders": _oku_json(self.dizin / DERS_DOSYASI, {}), "ders_gecis": gecis, "egitim": self.durum.get("egitim", {})})
        except Exception:  # noqa: BLE001
            log.exception("öğrenme karnesi yazılamadı")


def bagla(p, dizin, gonder: Optional[Callable] = None, env=None) -> Optional[Ogrenme]:
    """paper.canli_calistir tek satırı. L3A_OGRENME_KAPALI=1 -> None (hiçbir kanca bağlanmaz). Kurulum hatası paper'ı durdurmaz."""
    if kapali(env):
        return None
    try:
        return Ogrenme(dizin, gonder).bagla(p)
    except Exception:  # noqa: BLE001
        log.exception("öğrenme adaptörü bağlanamadı; paper öğrenmesiz sürer")
        return None
