"""Çıkış karşı-olgusu: "aynı giriş, farklı çıkış yönetimi olsaydı ne olurdu" + onay beklemeden otomatik uygulama + "alınsaydı" gece özeti.

PAPER'DA ÇALIŞIR (kullanıcı kuralı 2026-11-19: onay/gözlem adımı yok; özellikler doğrudan devreye girer). Günde en çok bir kez (TSİ 01:00 sonrası),
paper tur döngüsünden çağrılır (`bagla`: p.adim sarılır; ogrenme_adaptor ile aynı kalıp).

1) Karşı-olgu: son 90 günde kapanan işlemler (her strateji) için GİRİŞ ve İLK STOP aynı tutulur; girişten SONRAKİ mumlarla (lookahead yok) ALTERNATIFLER
   (dosya başı sabit) yeniden oynatılır. Mum içinde stop ve hedef birlikte değerse STOP. Maliyet paper motorunun kendi maliyet yöntemleriyle
   (taker/maker/kayma/stop kayması, seans çarpanı dahil) hesaplanır; funding gerçek işlemin funding'i tutma süresiyle orantılanır (yaklaşık).
   Strateji sinyal çıkışı / gün sonu / kill / günlük limit gibi "dış" çıkışlar gerçek anında aynen uygulanır (alternatif yalnız stop/hedef/zaman/kısmi
   yönetimini değiştirir). Alternatif girişten sonra mum verisi bitene dek çıkmazsa o işlem o alternatif için "çözülmedi" sayılır ve (eşli
   karşılaştırma için) mevcut çıkışın toplamından da çıkarılır.
   Sonuç: `cikis_karsi_olgu.json` (strateji x alternatif: n, toplam R, ort R, kazanma, mevcut çıkışa fark). Her işlemin en iyi alternatifi
   ogrenme_adaylar'daki Aday.cikis["en_iyi_cikis"] alanına yazılır (ortak_ogrenme paketi DEĞİŞMEZ).
2) Otomatik uygulama (ön kayıt ölçütü, aşağıdaki sabitler): ≥ MIN_ISLEM işlem VE alternatif toplam R >= mevcut + max(MIN_FARK_R, |mevcut| x MIN_FARK_ORAN)
   VE alternatifin en kötü işlemi mevcut en kötüden kötü değil -> `cikis_override.json`; paper yalnız ÇIKIŞ alanlarını uygular (stop/boyut/risk/limit
   değişmez); açık pozisyonlar eski çıkışla kalır, yalnız yeni girişler yeni çıkışı alır. Telegram INFO. Geri alma: /cikis_geri_al (CIKIS_GERI_AL istek dosyası).
3) "Alınsaydı" (araclar/alinmayan_sonuc.py mantığı): neden bazında atlanan işlemler `alinmayan_sonuc.json`; ogrenme_karne.json'a ve günlük özet notuna
   tek satır; bir neden >= ALINMAYAN_MIN_ATLAMA atlamada toplam R > ALINMAYAN_UYARI_R ise tek Telegram WARN (otomatik kural değişikliği YOK).
Kapatma: L3A_CIKIS_KARSI_OLGU_KAPALI=1. Hata -> paper etkilenmez (log).
"""
from __future__ import annotations

import dataclasses
import logging
import math
import os
from pathlib import Path
from typing import Callable, Optional

import numpy as np
import pandas as pd

from motor.canli.durum import oku_json_varsayilan as _oku_json, yaz_json_sirali as _yaz_json  # noqa: E402
from motor.canli.kayit_etiketleri import _utc  # noqa: E402,F401

from motor.strateji import cikislar as cks

log = logging.getLogger("cikis_karsi_olgu")

ENV_KAPALI = "L3A_CIKIS_KARSI_OLGU_KAPALI"
# ------------------------------------------------------------------ ön kayıt sabitleri (değişmez)
PENCERE_GUN = 90
GUN_SAAT_TSI = (1, 0)
MIN_ISLEM = 10
MIN_FARK_R = 2.0
MIN_FARK_ORAN = 0.20
ALINMAYAN_MIN_ATLAMA = 20
ALINMAYAN_UYARI_R = 5.0
GERI_AL_ISTEK_OMRU_SN = 600
# Otomatik geri alma (ön kayıt; uygulama ölçütünün tersi): override SONRASI açılıp kapanan >= GERI_AL_MIN_ISLEM işlemde
# (özgün toplam R >= yeni toplam R + max(GERI_AL_MIN_FARK_R, |yeni| x GERI_AL_FARK_ORAN)) YA DA (yeni en kötü işlem özgün en kötüden en az GERI_AL_EN_KOTU_FARK_R daha kötü).
GERI_AL_MIN_ISLEM = 10
GERI_AL_MIN_FARK_R = 2.0
GERI_AL_FARK_ORAN = 0.20
GERI_AL_EN_KOTU_FARK_R = 1.0

# Alternatifler: yalnız ÇIKIŞ YÖNETİMİ alanları (CikisAyarlari alan adlarıyla). Belirtilmeyen yönetim alanı varsayılana (kapalı) döner.
ALTERNATIFLER = {
    "basabas_1R": {"basabas_r_esigi": 1.0},
    "atr_iz_2": {"atr_iz_suren_k": 2.0},
    "atr_iz_3": {"atr_iz_suren_k": 3.0},
    "zaman_stopu_10": {"zaman_cikisi_mum": 10},
    "kismi_2R_yarim": {"kismi": ((2.0, 0.5),)},
    "brooks": {"kismi": ((2.0, 0.5), (3.0, 0.25)), "basabas_r_esigi": 2.0, "atr_iz_suren_k": 3.0},
    "farley": {"atr_iz_suren_k": 3.0, "agresif_iz_esigi": 0.75, "agresif_iz_atr_k": 1.0},     # paper motoru uygular (agresif_iz_*; 2026-11-19)
    "zirveden_geri_cekilme": {"geri_cekilme_yuzde": 1.5, "geri_cekilme_min_kar_yuzde": 3.0},
}
YONETIM_ALANLARI = ("atr_iz_suren_k", "zaman_cikisi_mum", "basabas_r_esigi", "kismi", "azalan_roi", "geri_cekilme_yuzde",
                    "geri_cekilme_min_kar_yuzde", "agresif_iz_esigi", "agresif_iz_atr_k")
_VARSAYILAN = cks.CikisAyarlari()
VARSAYILAN_YONETIM = {a: getattr(_VARSAYILAN, a) for a in YONETIM_ALANLARI}
# Stratejinin kendi stop/hedef/zaman/roi/kısmi yönetimine bağlı çıkışlar; bunlar alternatifte yeniden oynatılır. Diğerleri (sinyal, gün sonu, kill...) "dış"tır.
YONETILEN_NEDENLER = frozenset({"stop", "stop_gap", "hedef", "zaman", "roi", "geri_cekilme", "kismi_tam", "veri_sonu"})

CIKTI, OVERRIDE, YASAK, DURUM = "cikis_karsi_olgu.json", "cikis_override.json", "cikis_yasak.json", "cikis_karsi_olgu_durum.json"
ALINMAYAN_CIKTI, GERI_AL_ISTEK = "alinmayan_sonuc.json", "CIKIS_GERI_AL"
KARNE_DOSYASI = "ogrenme_karne.json"


def kapali(env=None) -> bool:
    return (env if env is not None else os.environ).get(ENV_KAPALI) == "1"


def tam_spec(alanlar: dict) -> dict:
    """Alternatif -> eksiksiz yönetim sözlüğü (belirtilmeyenler varsayılan)."""
    d = dict(VARSAYILAN_YONETIM)
    d.update(alanlar)
    return d


def yonetim_of(ca) -> dict:
    return {a: getattr(ca, a) for a in YONETIM_ALANLARI}


def canlida_uygulanir(ca) -> bool:
    """Canlı yürütücü bu çıkış yönetimini yansıtabilir mi: kısmi çıkış YOK (CikisAyarlari ya da alan sözlüğü)."""
    kismi = ca.get("kismi") if isinstance(ca, dict) else getattr(ca, "kismi", None)
    return not kismi


def uygulanabilir(alt: str) -> bool:
    """Paper motorunun uyguladığı çıkış alanlarıyla sınırlı mı (fail-closed: desteklenmeyen alan paper'a ASLA yazılmaz)."""
    from motor.canli.paper_motor import desteklenmeyen_cikis_alanlari
    try:
        return not desteklenmeyen_cikis_alanlari(dataclasses.replace(_VARSAYILAN, **tam_spec(ALTERNATIFLER[alt])))
    except (ValueError, TypeError):
        return False


# ---------------------------------------------------------------------------- dosya yardımcıları
def _liste(v):
    """JSON'dan gelen iç içe listeleri tuple'a çevirir (CikisAyarlari kısmi vb.)."""
    return tuple(_liste(e) for e in v) if isinstance(v, (list, tuple)) else v


def spec_json(spec: dict) -> dict:
    return {k: ([list(e) for e in v] if isinstance(v, tuple) else v) for k, v in spec.items()}


def spec_oku(d: dict) -> dict:
    return {k: _liste(v) for k, v in d.items()}


# ---------------------------------------------------------------------------- maliyet: paper motorunun kendi yöntemleri
class MotorMaliyet:
    """Paper motorunun taker/maker/kayma/stop kayması yöntemleri (seans çarpanı `motor._an` ile, o mumun zamanında)."""

    def __init__(self, motor):
        self.m = motor
        self.hedef_maker = bool(getattr(motor.ay, "hedef_limit_emri", False))

    def _w(self, fn, s, t):
        eski = getattr(self.m, "_an", None)
        self.m._an = t
        try:
            return float(fn(s))
        finally:
            self.m._an = eski

    def tk(self, s, t): return self._w(self.m._tk, s, t)
    def mk(self, s, t): return self._w(self.m._mk, s, t)
    def ky(self, s, t): return self._w(self.m._ky, s, t)
    def sk(self, s, t): return self._w(self.m._sk, s, t)
    def tick(self, s): return float(self.m.tick[s])
    def step(self, s): return float(self.m.step[s])
    def min_qty(self, s): return float(self.m.min_qty[s])


# ---------------------------------------------------------------------------- yeniden oynatma (saf; lookahead yok)
def _tickle(x: float, tick: float) -> float:
    return round(x / tick) * tick if tick > 0 else x


def _step_asagi(q: float, step: float) -> float:
    return math.floor(q / step + 1e-9) * step if step > 0 else q


def yeniden_oyna(spec: dict, *, sembol: str, yon: int, giris: float, stop: float, hedef: Optional[float], qty: float, giris_zamani,
                 mumlar: dict, mal, aralik: pd.Timedelta, dis: Optional[dict] = None, funding: float = 0.0, gercek_sure_sn: float = 0.0) -> dict:
    """Aynı giriş/ilk stop/miktar; çıkış yönetimi `spec`. mumlar: {"t": DatetimeIndex(UTC açılış), "o","h","l","c","atr": np.ndarray}.
    Yalnız giris_zamani'ndaki ve SONRAKİ mumlar kullanılır. dis: {"neden", "zaman", "yontem"} gerçek dış çıkış (sinyal/gün sonu/kill...): gerçek anında uygulanır.
    -> {"sonuc": "kapandi"|"acik"|"yok", "r", "net", "neden", "cikis_zamani"}."""
    t = mumlar["t"]
    i0 = int(t.get_indexer([_utc(giris_zamani)])[0])
    if i0 < 0:
        return {"sonuc": "yok"}
    tick, step, min_qty = mal.tick(sembol), mal.step(sembol), mal.min_qty(sembol)
    stop = _tickle(stop, tick)
    hedef = None if hedef is None else _tickle(hedef, tick)
    rb = abs(giris - stop)
    if rb <= 0 or qty <= 0:
        return {"sonuc": "yok"}
    giris_t = t[i0]
    giris_kom = qty * giris * mal.tk(sembol, giris_t)
    risk_tutar = qty * rb
    ilk_qty, miktar = qty, qty
    cur = stop
    ekstrem = giris
    tutulan = 0
    brut = cikis_kom = 0.0
    kis = [(_tickle(giris + yon * r_k * rb, tick), o) for r_k, o in sorted(spec["kismi"])]
    zl = spec["zaman_cikisi_mum"]
    bekleyen = None
    sonuc = None

    def piyasa(fiyat, k):
        return _tickle(fiyat * (1 - yon * k), tick)

    def azalt(fiyat, q, kom):
        nonlocal miktar, brut, cikis_kom
        q = min(q, miktar)
        brut += (fiyat - giris) * q * yon
        cikis_kom += fiyat * q * kom
        miktar -= q

    for i in range(i0, len(t)):
        ti = t[i]
        o, h, l, c = float(mumlar["o"][i]), float(mumlar["h"][i]), float(mumlar["l"][i]), float(mumlar["c"][i])
        dis_simdi = dis is not None and dis["neden"] != "gun_sonu" and ti >= dis["zaman"]
        if bekleyen is not None or dis_simdi:                              # 2) açılışta bekleyen çıkış
            neden = bekleyen or dis["neden"]
            k = mal.sk(sembol, ti) if neden in ("kill_switch", "gunluk_limit") else mal.ky(sembol, ti)
            azalt(piyasa(o, k), miktar, mal.tk(sembol, ti))
            sonuc = (neden, ti)
            break
        # 4) mum içi stop / hedef / kısmi
        if yon == 1:
            stop_gap, stop_vur = o <= cur, l <= cur
            hedef_gap = hedef is not None and o >= hedef
            hedef_vur = hedef is not None and h >= hedef
        else:
            stop_gap, stop_vur = o >= cur, h >= cur
            hedef_gap = hedef is not None and o <= hedef
            hedef_vur = hedef is not None and l <= hedef
        kom_h = mal.mk(sembol, ti) if mal.hedef_maker else mal.tk(sembol, ti)
        cikis = None
        if stop_gap:
            cikis = (piyasa(o, mal.sk(sembol, ti)), "stop_gap", ti, mal.tk(sembol, ti))
        elif hedef_gap:
            cikis = (_tickle(o, tick), "hedef", ti, kom_h)
        elif stop_vur:
            cikis = (piyasa(cur, mal.sk(sembol, ti)), "stop", ti + aralik, mal.tk(sembol, ti))
        elif hedef_vur:
            cikis = (hedef, "hedef", ti + aralik, kom_h)
        if kis and (cikis is None or (cikis[1] == "hedef" and not hedef_gap)):
            kalan = []
            for seviye, oran in kis:
                if hedef is not None and (seviye - hedef) * yon >= 0:
                    continue
                gorulen = (o >= seviye) if yon == 1 else (o <= seviye)
                vurdu = (h >= seviye) if yon == 1 else (l <= seviye)
                if not (gorulen or vurdu):
                    kalan.append((seviye, oran))
                    continue
                fiyat_k = _tickle(o, tick) if gorulen else seviye
                t_k = ti if gorulen else ti + aralik
                q = min(_step_asagi(ilk_qty * oran, step), miktar)
                if q <= 0:
                    continue
                if miktar - q < min_qty:
                    cikis = (fiyat_k, "kismi_tam", t_k, kom_h)
                    break
                azalt(fiyat_k, q, kom_h)
            kis = kalan
        if cikis is not None:
            azalt(cikis[0], miktar, cikis[3])
            sonuc = (cikis[1], cikis[2])
            break
        if dis is not None and dis["neden"] == "gun_sonu" and ti + aralik >= dis["zaman"]:     # 4b) gün sonu kapanışı (dış)
            azalt(piyasa(c, mal.ky(sembol, ti)), miktar, mal.tk(sembol, ti))
            sonuc = ("gun_sonu", ti + aralik)
            break
        # 7) kapanış kararı: iz süren stop / başabaş / zaman / roi / geri çekilme (etki sonraki mumda)
        tutulan += 1
        ekstrem = max(ekstrem, h) if yon == 1 else min(ekstrem, l)
        yeni = cur
        if spec["basabas_r_esigi"]:
            yeni = cks.basabasa_cek(yon, yeni, giris, ekstrem, rb, spec["basabas_r_esigi"])
        if spec["atr_iz_suren_k"]:
            yeni = cks.iz_suren_stop(yon, yeni, ekstrem, float(mumlar["atr"][i]), spec["atr_iz_suren_k"])
        if spec["agresif_iz_esigi"] and hedef is not None:
            yol = yon * (hedef - giris)
            if yol > 0 and yon * (ekstrem - giris) / yol >= spec["agresif_iz_esigi"]:
                yeni = cks.iz_suren_stop(yon, yeni, ekstrem, float(mumlar["atr"][i]), spec["agresif_iz_atr_k"])
        yeni = _tickle(yeni, tick)
        if (yeni - cur) * yon > 0:
            cur = yeni
        kar_c = cks.kar_yuzde(yon, giris, c)
        if cks.zaman_doldu(tutulan, zl):
            bekleyen = "zaman"
        elif spec["azalan_roi"] and cks.azalan_roi_doldu(tutulan, kar_c, spec["azalan_roi"]):
            bekleyen = "roi"
        elif cks.geri_cekilme_doldu(cks.kar_yuzde(yon, giris, ekstrem), kar_c, spec["geri_cekilme_yuzde"], spec["geri_cekilme_min_kar_yuzde"]):
            bekleyen = "geri_cekilme"
    if sonuc is None:
        return {"sonuc": "acik"}
    neden, tc = sonuc
    sure = (tc - giris_t).total_seconds()
    fund = funding * (sure / gercek_sure_sn) if gercek_sure_sn > 0 else 0.0
    net = brut - giris_kom - cikis_kom - fund
    return {"sonuc": "kapandi", "r": net / risk_tutar, "net": net, "neden": neden, "cikis_zamani": str(tc)}


# ---------------------------------------------------------------------------- ölçüt
def olcut_gecti(alt_r: list, mevcut_r: list) -> bool:
    """Ön kayıt ölçütü: >= MIN_ISLEM işlem VE alt toplam >= mevcut + max(MIN_FARK_R, |mevcut| x MIN_FARK_ORAN) VE alt en kötü >= mevcut en kötü."""
    if len(alt_r) < MIN_ISLEM or len(alt_r) != len(mevcut_r):
        return False
    a, m = sum(alt_r), sum(mevcut_r)
    return a >= m + max(MIN_FARK_R, abs(m) * MIN_FARK_ORAN) and min(alt_r) >= min(mevcut_r)


def geri_al_gerekli(yeni_r: list, ozgun_r: list) -> bool:
    """Ön kayıt geri alma koşulu: >= GERI_AL_MIN_ISLEM eşli işlem VE (özgün toplam >= yeni toplam + max(2R, |yeni| x %20) YA DA yeni en kötü, özgün en kötüden
    GERI_AL_EN_KOTU_FARK_R veya daha fazla kötü). yeni_r: override altında gerçekleşen R; ozgun_r: aynı işlemlerin özgün çıkışla yeniden oynatılmış R'si."""
    if len(yeni_r) < GERI_AL_MIN_ISLEM or len(yeni_r) != len(ozgun_r):
        return False
    y, o = sum(yeni_r), sum(ozgun_r)
    toplam_kotu = o >= y + max(GERI_AL_MIN_FARK_R, abs(y) * GERI_AL_FARK_ORAN)
    en_kotu_kotu = min(yeni_r) <= min(ozgun_r) - GERI_AL_EN_KOTU_FARK_R
    return toplam_kotu or en_kotu_kotu


def _ozet(rs: list) -> dict:
    n = len(rs)
    return {"n": n, "toplam_r": round(sum(rs), 4), "ort_r": round(sum(rs) / n, 4) if n else None,
            "kazanma": round(sum(1 for r in rs if r > 0) / n, 4) if n else None, "en_kotu_r": round(min(rs), 4) if n else None}


# ---------------------------------------------------------------------------- servis
class CikisKarsiOlgu:
    def __init__(self, dizin, gonder: Optional[Callable] = None, saat: Optional[Callable] = None, kapali_: Optional[bool] = None, ogrenme=None,
                 canli: bool = False):
        self.dizin = Path(dizin)
        # CANLI yürütücü servisi (kullanıcı kararı 2026-11-20: canlıda da açık): yalnız canlının yürütebildiği çıkışlar uygulanır. Kısmi çıkış
        # (kismi) canlıda yok (motor_kopru.uygunluk_kontrol) -> o alternatif seçilmez/uygulanmaz (fail-closed). Diğer yönetim alanları paper'da
        # stop yükseltme (canlı _stop_yukselt) ya da cikis_emri (canlı 'kapat' niyeti) olarak canlıya yansır.
        self.canli = canli
        self.kapali = kapali() if kapali_ is None else kapali_
        self.saat = saat or (lambda: pd.Timestamp.now(tz="UTC"))
        self.gonder = gonder or self._tg
        self.ogrenme = ogrenme
        self.durum = _oku_json(self.dizin / DURUM, {})
        self.taban: dict = {}                         # {kol kimliği: stratejinin özgün CikisAyarlari'ı} (geri alma / karşılaştırma tabanı)
        self._p = None
        self._ov_imza = "ilk"                         # override dosyası değişmedikçe ve bekleyen kol yoksa uzlaştırma atlanır (her turda yüzlerce kol gezilmesin)
        self._bekleyen = False

    @staticmethod
    def _tg(metin: str) -> bool:
        from motor.canli import telegram as tg
        return tg.gonder(metin)

    def _mesaj(self, metin: str) -> None:
        try:
            self.gonder(metin)
        except Exception:  # noqa: BLE001
            log.exception("çıkış karşı-olgusu mesajı gönderilemedi")

    def _degisti_bildir(self, sk: str, ad: str, simdi) -> None:
        """Çıkış yöntemi değişti: Telegram'a GİTMEZ (kullanıcı kararı 2026-11-20), yalnız log. Geri alma/kötü gitti uyarıları ayrıdır."""
        log.info("Çıkış yöntemi değişti: %s → %s", self._ad_gorunur(sk), ad.replace("_", " "))

    # ------------------------------------------------------------ bağlama
    def bagla(self, p):
        if self.kapali:
            return None
        self._p = p
        adim = p.adim

        def adim_sarili(simdi, *a, **k):
            n = adim(simdi, *a, **k)
            try:
                self.tur(simdi)
            except Exception:  # noqa: BLE001
                log.exception("çıkış karşı-olgusu turu hatası (paper etkilenmez)")
            return n
        p.adim = adim_sarili
        return self

    def _hesaplar(self) -> list:
        return list(self._p.hesaplar.values()) if hasattr(self._p, "hesaplar") else [self._p]

    @staticmethod
    def _gorunur(h) -> bool:
        return bool(getattr(h, "gorunur", True))

    def _kollar(self, sk: Optional[str] = None):
        """(hesap, kol) çiftleri: yalnız sinyal kolları (çıkış ayarı olanlar)."""
        for h in self._hesaplar():
            for kol in h.motor.tum_kollar:
                if getattr(kol, "mod", "") == "sinyal" and (sk is None or kol.sk == sk):
                    yield h, kol

    # ------------------------------------------------------------ override dosyaları
    def override_oku(self) -> dict:
        d = _oku_json(self.dizin / OVERRIDE, {})
        return d if isinstance(d, dict) else {}

    def yasak_oku(self) -> list:
        d = _oku_json(self.dizin / YASAK, [])
        return d if isinstance(d, list) else []

    def _ca_override(self, ca, ov: dict):
        """Çıkış (yönetim) alanlarını değiştirir; stop/boyut/risk/limit/sabit hedef/ATR periyodu DEĞİŞMEZ."""
        return dataclasses.replace(ca, **spec_oku(ov["ayarlar"]))

    def uygula(self) -> int:
        """Override dosyasını kollara yansıtır (durumsuz uzlaştırma). Açık pozisyonu olan kol atlanır (eski çıkışla kalır); pozisyon kapanınca
        sonraki turda yeni ayar alır. Override yoksa / geri alındıysa kol özgün ayarına döner. -> değişen kol sayısı."""
        ovs = self.override_oku()
        n = 0
        self._bekleyen = False
        try:
            self._ov_imza = (self.dizin / OVERRIDE).stat().st_mtime_ns
        except OSError:
            self._ov_imza = None
        from motor.canli.paper_motor import desteklenmeyen_cikis_alanlari
        for h, kol in self._kollar():
            taban = self.taban.setdefault(kol.kimlik, kol.cikis_ayarlari)
            ov = ovs.get(kol.sk)
            try:
                hedef = self._ca_override(taban, ov) if isinstance(ov, dict) and ov.get("ayarlar") else taban
            except (TypeError, ValueError):
                log.exception("override geçersiz (%s): uygulanmadı", kol.sk)
                continue
            if hedef == kol.cikis_ayarlari:
                continue
            if desteklenmeyen_cikis_alanlari(hedef):                     # fail-closed
                log.error("override paper'ın uygulamadığı alan içeriyor (%s): uygulanmadı", kol.sk)
                continue
            if self.canli and not canlida_uygulanir(hedef):                 # fail-closed: canlı yürütücünün yapamadığı çıkış (kısmi)
                log.error("override canlıda yürütülemeyen alan içeriyor (%s): uygulanmadı", kol.sk)
                continue
            if kol.kimlik in h.motor.acik:                                # açık pozisyon eski çıkışla kalır
                self._bekleyen = True
                continue
            kol.cikis_ayarlari = hedef
            n += 1
        # ATR serisi karardan gelir (tek_karar st.cikis_ayarlari'na bakar): strateji nesnesi, ESKİ ya da YENİ ayardan biri ATR istiyorsa ATR hesaplatır.
        for h in self._hesaplar():
            for td in getattr(h, "tanimlar", []):
                ov = ovs.get(td.kimlik)
                nes = td.nesne
                if not hasattr(nes, "cikis_ayarlari") or getattr(td, "kol", "") == "portfoy":
                    continue
                tb = self.taban.setdefault(("nesne", td.kimlik, id(nes)), nes.cikis_ayarlari)
                try:
                    yeni = self._ca_override(tb, ov) if isinstance(ov, dict) and ov.get("ayarlar") else tb
                except (TypeError, ValueError):
                    continue
                k = yeni.atr_iz_suren_k or tb.atr_iz_suren_k
                yeni = dataclasses.replace(yeni, atr_iz_suren_k=k) if k and not yeni.atr_iz_suren_k else yeni
                if yeni != nes.cikis_ayarlari and not desteklenmeyen_cikis_alanlari(yeni) and (not self.canli or canlida_uygulanir(yeni)):
                    nes.cikis_ayarlari = yeni
        return n

    # ------------------------------------------------------------ geri alma (/cikis_geri_al)
    def geri_al_isle(self, simdi) -> bool:
        yol = self.dizin / GERI_AL_ISTEK
        if not yol.exists():
            return False
        try:
            ist = _oku_json(yol, {})
            yas = (_utc(simdi) - _utc(ist.get("zaman"))).total_seconds() if ist.get("zaman") else 0
        except Exception:  # noqa: BLE001
            yas = 0
        try:
            yol.unlink()
        except OSError:
            log.exception("geri alma isteği silinemedi")
        if yas > GERI_AL_ISTEK_OMRU_SN:
            return False
        ovs = self.override_oku()
        if not ovs:
            self._mesaj("[1L3A] çıkış geri alma: geri alınacak çıkış değişikliği yok")
            return True
        sk = max(ovs, key=lambda k: ovs[k].get("zaman", ""))
        ov = ovs[sk]
        yasak = self.yasak_oku()
        if [sk, ov.get("alternatif")] not in yasak:
            yasak.append([sk, ov.get("alternatif")])
        onceki = ov.get("onceki")
        if isinstance(onceki, dict) and onceki.get("ayarlar"):
            ovs[sk] = {"alternatif": onceki["alternatif"], "ayarlar": onceki["ayarlar"], "zaman": _utc(simdi).isoformat(), "onceki": None}
            yeni_ad = onceki["alternatif"]
        else:
            del ovs[sk]
            yeni_ad = "varsayılan"
        _yaz_json(self.dizin / YASAK, yasak)
        _yaz_json(self.dizin / OVERRIDE, ovs)
        self.uygula()
        self._mesaj(f"[1L3A] ⚠️ çıkış geri alındı: {self._ad_gorunur(sk)} {ov.get('alternatif')}→{yeni_ad} (bu strateji+alternatif bir daha otomatik uygulanmaz)")
        return True

    def _ad_gorunur(self, sk: str) -> str:
        """Telegram için strateji adı: görünür hesabın kısa adı; gizli hesap adı ASLA yazılmaz ("gizli_hesaplar (N)", N = gizli hesap sayısı)."""
        from motor.canli import gunluk_ozet as go
        gizli = sum(1 for h in self._hesaplar() if not self._gorunur(h))
        for h, _kol in self._kollar(sk):
            return go.kisa_ad(sk) if self._gorunur(h) else f"{go.GIZLI_AD} ({gizli})"
        return f"{go.GIZLI_AD} ({gizli})"

    # ------------------------------------------------------------ tur
    def tur(self, simdi) -> None:
        if self.kapali:
            return
        simdi = _utc(simdi)
        self.geri_al_isle(simdi)
        try:
            imza = (self.dizin / OVERRIDE).stat().st_mtime_ns
        except OSError:
            imza = None
        if self._bekleyen or imza != self._ov_imza:
            self.uygula()
        self.gunluk(simdi)

    def gunluk(self, simdi) -> bool:
        """TSİ 01:00'den sonra günde en çok bir kez. True: bu çağrıda çalıştı."""
        simdi = _utc(simdi)
        tsi = simdi + pd.Timedelta(hours=3)
        gun = str(tsi.date())
        if (tsi.hour, tsi.minute) < GUN_SAAT_TSI or self.durum.get("son_gun") == gun:
            return False
        self.durum["son_gun"] = gun
        _yaz_json(self.dizin / DURUM, self.durum)                     # önce işaretle: hata olursa aynı gün tekrar tekrar denenmez
        try:
            self.karsi_olgu(simdi)
        except Exception:  # noqa: BLE001
            log.exception("çıkış karşı-olgusu başarısız")
        try:
            self.alinmayan(simdi)
        except Exception:  # noqa: BLE001
            log.exception("alınmayan sinyal sonucu başarısız")
        return True

    # ------------------------------------------------------------ 1) karşı-olgu
    def _islemler(self, simdi) -> list:
        """Son PENCERE_GUN günde kapanan, ilk stopu bilinen sinyal işlemleri."""
        sinir = simdi - pd.Timedelta(days=PENCERE_GUN)
        out = []
        for h in self._hesaplar():
            kollar = {k.kimlik: k for k in h.motor.tum_kollar}
            for x in h.motor.islemler:
                kol = kollar.get(x["kol"])
                g = x.get("giris_gerekcesi") or {}
                if kol is None or getattr(kol, "mod", "") != "sinyal" or not isinstance(g, dict):
                    continue
                if _utc(x["cikis_zamani"]) < sinir:
                    continue
                try:
                    stop = float(g["stop"])
                except (KeyError, TypeError, ValueError):
                    continue
                if not math.isfinite(stop) or x.get("r") is None or x["r"] != x["r"]:
                    continue
                hedef = g.get("hedef")
                hedef = float(hedef) if isinstance(hedef, (int, float)) and math.isfinite(hedef) else None
                out.append({"h": h, "kol": kol, "x": x, "sk": kol.sk, "stop": stop, "hedef": hedef,
                            "id": f"{x['kol']}|{x['giris_zamani']}|{x['cikis_zamani']}"})
        return out

    def _mum(self, h, sembol: str, tf: str, simdi, onbellek: dict):
        k = (sembol, tf)
        if k not in onbellek:
            try:
                df = h.kaynak.gecmis(sembol, tf, simdi)
                atr = cks_atr(df)
                onbellek[k] = {"t": df.index, "o": df["acilis"].to_numpy(float), "h": df["yuksek"].to_numpy(float),
                               "l": df["dusuk"].to_numpy(float), "c": df["kapanis"].to_numpy(float), "atr": atr} if len(df) else None
            except Exception:  # noqa: BLE001
                onbellek[k] = None
        return onbellek[k]

    def karsi_olgu(self, simdi) -> dict:
        from motor.veri.depo import aralik_suresi
        islemler = self._islemler(simdi)
        ovs = self.override_oku()
        yasak = {tuple(v) for v in self.yasak_oku()}
        geri_zaman = self.durum.get("geri_alma_zamani", {})
        mum_onb: dict = {}
        sonuc: dict = {}
        en_iyi: dict = {}
        for tr in islemler:
            h, kol, x = tr["h"], tr["kol"], tr["x"]
            ov = ovs.get(tr["sk"])
            if ov and _utc(x["giris_zamani"]) < _utc(ov["zaman"]):        # yürürlükteki çıkıştan ÖNCE girilenler mevcut çıkışın örneği değil
                continue
            gz_son = geri_zaman.get(tr["sk"])
            if not ov and gz_son and _utc(x["giris_zamani"]) < _utc(gz_son):   # geri alınan çıkışla açılan işlemler özgün çıkışın örneği değil
                continue
            td = h.tanim_ad.get(kol.birim) if hasattr(h, "tanim_ad") else None
            mum = self._mum(h, kol.sembol, td.tf, simdi, mum_onb) if td is not None else None
            if mum is None:
                continue
            aralik = aralik_suresi(td.tf)
            mal = MotorMaliyet(h.motor)
            yon = int(x["yon"])
            giris = float(x["giris_fiyati"])
            hedef = tr["hedef"]
            if hedef is None and kol.cikis_ayarlari.sabit_r_hedefi:
                hedef = cks.r_hedef_fiyati(yon, giris, abs(giris - tr["stop"]), kol.cikis_ayarlari.sabit_r_hedefi)
            neden = x.get("cikis_nedeni")
            dis = None if neden in YONETILEN_NEDENLER else {"neden": neden, "zaman": _utc(x["cikis_zamani"])}
            sure = (_utc(x["cikis_zamani"]) - _utc(x["giris_zamani"])).total_seconds()
            ortak = dict(sembol=kol.sembol, yon=yon, giris=giris, stop=tr["stop"], hedef=hedef, qty=float(x["miktar"]), giris_zamani=x["giris_zamani"],
                         mumlar=mum, mal=mal, aralik=aralik, dis=dis, funding=float(x.get("funding") or 0.0), gercek_sure_sn=sure)
            gercek = float(x["r"])
            s = sonuc.setdefault(tr["sk"], {"islem": 0, "alt": {}})
            s["islem"] += 1
            en = ("mevcut", gercek)
            mevcut_y = yonetim_of(kol.cikis_ayarlari)
            for ad, alan in list(ALTERNATIFLER.items()) + [("_mevcut_yeniden", None)]:
                spec = mevcut_y if alan is None else tam_spec(alan)
                try:
                    o = yeniden_oyna(spec, **ortak)
                except Exception:  # noqa: BLE001
                    log.exception("yeniden oynatma hatası (%s)", ad)
                    continue
                if o["sonuc"] == "acik":
                    s["alt"].setdefault(ad, {"cift": [], "cozulmeyen": 0})["cozulmeyen"] += 1
                    continue
                if o["sonuc"] != "kapandi":
                    continue
                s["alt"].setdefault(ad, {"cift": [], "cozulmeyen": 0})["cift"].append((o["r"], gercek))
                if alan is not None and o["r"] > en[1]:
                    en = (ad, o["r"])
            en_iyi[tr["id"]] = en[0]
            if ov and ov.get("ayarlar"):                                  # uygulanmış override: aynı işlem özgün çıkışla (taban) yeniden oynatılır
                taban = self.taban.get(kol.kimlik)
                if taban is not None:
                    try:
                        og = yeniden_oyna(yonetim_of(taban), **ortak)
                    except Exception:  # noqa: BLE001
                        log.exception("özgün yeniden oynatma hatası")
                        og = {"sonuc": "yok"}
                    g = s.setdefault("ozgun", {"cift": [], "cozulmeyen": 0})
                    if og["sonuc"] == "kapandi":
                        g["cift"].append((og["r"], gercek))
                    elif og["sonuc"] == "acik":
                        g["cozulmeyen"] += 1
        cikti = self._sonuclandir(sonuc, simdi, ovs, yasak)
        cikti["islem_en_iyi"] = en_iyi
        geri = self._otomatik_geri_al(cikti, simdi, ovs, yasak)
        for sk in geri:                                                   # bu çalışmada geri alınan kolda yeni alternatif uygulanmaz
            cikti["stratejiler"].get(sk, {}).get("alternatifler", {}).clear()
        _yaz_json(self.dizin / CIKTI, cikti)
        self._adaylara_isle(en_iyi)
        self._otomatik_uygula(cikti, simdi, ovs, yasak)
        return cikti

    def _sonuclandir(self, sonuc: dict, simdi, ovs: dict, yasak: set) -> dict:
        strat = {}
        for sk, s in sorted(sonuc.items()):
            alt_ozet = {}
            for ad, v in sorted(s["alt"].items()):
                alt_r, mev_r = [a for a, _ in v["cift"]], [g for _, g in v["cift"]]
                o = _ozet(alt_r)
                m = _ozet(mev_r)
                o.update({"mevcut_toplam_r": m["toplam_r"], "mevcut_en_kotu_r": m["en_kotu_r"], "mevcut_ort_r": m["ort_r"], "mevcut_kazanma": m["kazanma"],
                          "fark_r": round(sum(alt_r) - sum(mev_r), 4), "cozulmeyen": v["cozulmeyen"]})
                if ad != "_mevcut_yeniden":
                    o["uygulanabilir"] = uygulanabilir(ad)
                    o["olcut_gecti"] = olcut_gecti(alt_r, mev_r)
                alt_ozet[ad] = o
            strat[sk] = {"islem": s["islem"], "alternatifler": alt_ozet}
            g = s.get("ozgun")
            if g and g["cift"]:
                oz_r, yeni_r = [a for a, _ in g["cift"]], [b for _, b in g["cift"]]
                strat[sk]["geri_alma"] = {"n": len(yeni_r), "yeni_toplam_r": round(sum(yeni_r), 4), "ozgun_toplam_r": round(sum(oz_r), 4),
                                          "yeni_en_kotu_r": round(min(yeni_r), 4), "ozgun_en_kotu_r": round(min(oz_r), 4), "cozulmeyen": g["cozulmeyen"],
                                          "gerekli": geri_al_gerekli(yeni_r, oz_r)}
        return {"zaman": simdi.isoformat(), "pencere_gun": PENCERE_GUN,
                "olcut": {"min_islem": MIN_ISLEM, "min_fark_r": MIN_FARK_R, "min_fark_oran": MIN_FARK_ORAN},
                "geri_alma_olcut": {"min_islem": GERI_AL_MIN_ISLEM, "min_fark_r": GERI_AL_MIN_FARK_R, "fark_oran": GERI_AL_FARK_ORAN, "en_kotu_fark_r": GERI_AL_EN_KOTU_FARK_R},
                "not": "mevcut = gerçekleşen R; _mevcut_yeniden = mevcut ayarın aynı motorla yeniden oynatılması (sadakat göstergesi, ölçütte kullanılmaz)",
                "stratejiler": strat}

    def _adaylara_isle(self, en_iyi: dict) -> None:
        """Her işlemin en iyi alternatifini ogrenme_adaylar'daki Aday.cikis["en_iyi_cikis"] alanına yazar (paket değişmez)."""
        og = self.ogrenme
        if og is None or not en_iyi:
            return
        from motor.ortak_ogrenme import kayit as ok
        from motor.canli import ogrenme_adaptor as oa
        degisti = False
        for a in og.kapananlar:
            e = en_iyi.get(a.id)
            if e is not None and a.cikis.get("en_iyi_cikis") != e:
                a.cikis["en_iyi_cikis"] = e                       # Aday frozen ama cikis sözlüğü değişebilir
                degisti = True
        if degisti:
            ok.yaz_jsonl(og.dizin / oa.ADAY_DOSYASI, og.kapananlar)

    # ------------------------------------------------------------ 1b) otomatik geri alma
    def _otomatik_geri_al(self, cikti: dict, simdi, ovs: dict, yasak: set) -> list:
        """Uygulanmış override'ı, override sonrası işlemlerde özgün çıkışa göre kötü gidiyorsa kaldırır; alternatif o kol için kalıcı kara listeye girer.
        Açık pozisyonlar mevcut çıkışıyla kalır (uygula() açık kolu atlar, kapanınca özgün ayara döner). -> geri alınan strateji kimlikleri."""
        geri = []
        for sk, s in cikti["stratejiler"].items():
            ov = ovs.get(sk)
            g = s.get("geri_alma")
            if not ov or not g or not g["gerekli"]:
                continue
            ad = ov.get("alternatif")
            kara = self.yasak_oku()
            if [sk, ad] not in kara:
                kara.append([sk, ad])
            yasak.add((sk, ad))
            del ovs[sk]
            _yaz_json(self.dizin / YASAK, kara)
            _yaz_json(self.dizin / OVERRIDE, ovs)
            self.durum.setdefault("geri_alma_zamani", {})[sk] = simdi.isoformat()
            _yaz_json(self.dizin / DURUM, self.durum)
            self.uygula()
            geri.append(sk)
            self._mesaj(f"[1L3A] ⚠️ {self._ad_gorunur(sk)}: yeni çıkış yöntemi kötü gitti, eski yönteme dönüldü "
                        f"(yeni {g['yeni_toplam_r']:+.1f} R, eski {g['ozgun_toplam_r']:+.1f} R, {g['n']} işlem)")
        return geri

    # ------------------------------------------------------------ 2) otomatik uygulama
    def _otomatik_uygula(self, cikti: dict, simdi, ovs: dict, yasak: set) -> list:
        uygulanan = []
        for sk, s in cikti["stratejiler"].items():
            mevcut_alt = (ovs.get(sk) or {}).get("alternatif")
            adaylar = [(v["fark_r"], ad) for ad, v in s["alternatifler"].items()
                       if ad != "_mevcut_yeniden" and v.get("olcut_gecti") and v.get("uygulanabilir")
                       and (not self.canli or canlida_uygulanir(tam_spec(ALTERNATIFLER[ad])))
                       and (sk, ad) not in yasak and ad != mevcut_alt]
            if not adaylar:
                continue
            fark, ad = max(adaylar)
            v = s["alternatifler"][ad]
            # özgün yönetim ile aynıysa (strateji zaten böyle çıkıyor) değişiklik yok
            kollar = list(self._kollar(sk))
            if kollar and yonetim_of(self.taban.get(kollar[0][1].kimlik, kollar[0][1].cikis_ayarlari)) == tam_spec(ALTERNATIFLER[ad]):
                continue
            onceki = None
            if mevcut_alt:
                eski = ovs[sk]
                onceki = {"alternatif": eski["alternatif"], "ayarlar": eski["ayarlar"], "zaman": eski["zaman"]}
            ovs[sk] = {"alternatif": ad, "ayarlar": spec_json(tam_spec(ALTERNATIFLER[ad])), "zaman": simdi.isoformat(), "onceki": onceki}
            _yaz_json(self.dizin / OVERRIDE, ovs)
            self.uygula()
            uygulanan.append(sk)
            log.info("çıkış değişti: %s", f"{self._ad_gorunur(sk)} {mevcut_alt or 'varsayılan'}→{ad} ({fark:+.1f} R, {v['n']} işlem)")
            self._degisti_bildir(sk, ad, simdi)
        return uygulanan

    # ------------------------------------------------------------ 3) "alınsaydı"
    def alinmayan(self, simdi) -> Optional[dict]:
        from araclar import alinmayan_sonuc as asn
        dosya = self.dizin / asn.DOSYA
        if not dosya.exists() and not (self.dizin / (asn.DOSYA + ".1")).exists():
            return None
        h0 = self._hesaplar()[0]
        sinir = simdi - pd.Timedelta(days=PENCERE_GUN)
        mum_getir = alinmayan_mum_getirici(h0, simdi)
        sonuclar = []
        for s in asn.satirlari_oku(self.dizin):
            try:
                if _utc(s["zaman"]) < sinir:
                    continue
                m = mum_getir(s["sembol"], s.get("tf"))
                sonuclar.append((s, asn.simule(s, m) if m is not None else {"sonuc": "acik", "r": None, "cikis_fiyati": None, "cikis_zamani": None}))
            except Exception:  # noqa: BLE001
                continue
        ozet = asn.ozet(sonuclar)
        toplam_cozulen = sum(o["cozulen"] for o in ozet)
        toplam_r = sum(o["toplam_r"] for o in ozet)
        cikti = {"zaman": simdi.isoformat(), "pencere_gun": PENCERE_GUN, "atlanan": sum(o["sinyal"] for o in ozet), "cozulen": toplam_cozulen,
                 "toplam_r": round(toplam_r, 4), "ort_r": round(toplam_r / toplam_cozulen, 4) if toplam_cozulen else None,
                 "nedenler": [{k: (round(v, 4) if isinstance(v, float) else v) for k, v in o.items()} for o in ozet],
                 "not": "brüt R (maliyet yok); yalnız analiz, motoru etkilemez"}
        satir = (f"alınsaydı ({PENCERE_GUN}g): atlanan {cikti['atlanan']}, çözülen {toplam_cozulen}, toplam {toplam_r:+.1f} R"
                 + (f", ort {cikti['ort_r']:+.2f} R" if cikti["ort_r"] is not None else ""))
        cikti["ozet_satiri"] = satir
        _yaz_json(self.dizin / ALINMAYAN_CIKTI, cikti)
        karne = _oku_json(self.dizin / KARNE_DOSYASI, None)
        if isinstance(karne, dict):
            karne["alinmayan_ozet"] = satir
            try:
                _yaz_json(self.dizin / KARNE_DOSYASI, karne)
            except Exception:  # noqa: BLE001
                log.exception("ogrenme_karne'ye alınmayan özeti yazılamadı")
        kotu = sorted(o["neden"] for o in ozet if o["sinyal"] >= ALINMAYAN_MIN_ATLAMA and o["toplam_r"] > ALINMAYAN_UYARI_R)
        onceki = set(self.durum.get("alinmayan_uyari", []))
        yeni = [k for k in kotu if k not in onceki]
        self.durum["alinmayan_uyari"] = kotu
        _yaz_json(self.dizin / DURUM, self.durum)
        if yeni:                                                       # tek mesaj; otomatik kural değişikliği YOK
            ayrinti = ", ".join(f"{o['neden']} ({o['sinyal']} atlama, {o['toplam_r']:+.1f} R)" for o in ozet if o["neden"] in yeni)
            log.info("Atlanan sinyaller kârlıydı (alınsaydı): %s", ayrinti)                # Telegram'a gitmez, yalnız log
        return cikti


def alinmayan_mum_getirici(h, simdi):
    """"Alınsaydı" simülasyonu için önbellekli mum getirici: (sembol, tf) -> DataFrame ya da None (veri yok/hata). TEK kaynak
    (alinsaydi_gevsetme.kanit de bunu kullanır)."""
    onb: dict = {}

    def mum_getir(sembol, tf):
        k = (sembol, tf)
        if k not in onb:
            try:
                df = h.kaynak.gecmis(sembol, tf, simdi)
                onb[k] = df if len(df) else None
            except Exception:  # noqa: BLE001
                onb[k] = None
        return onb[k]
    return mum_getir


def cks_atr(df: pd.DataFrame) -> np.ndarray:
    from motor.strateji import gostergeler as gst
    return gst.atr(df["yuksek"], df["dusuk"], df["kapanis"], _VARSAYILAN.atr_periyot).to_numpy(dtype=float)


def bagla(p, dizin, gonder: Optional[Callable] = None, ogrenme=None, canli: bool = False, env=None) -> Optional[CikisKarsiOlgu]:
    """paper.canli_calistir tek satırı. Kapalıyken None. Kurulum hatası paper'ı durdurmaz. canli=True: canlı yürütücü servisi (AÇIK kalır; yalnız
    canlının yürütebildiği çıkışlar uygulanır, bkz. CikisKarsiOlgu.canli)."""
    if kapali(env):
        return None
    try:
        return CikisKarsiOlgu(dizin, gonder, ogrenme=ogrenme, canli=canli).bagla(p)
    except Exception:  # noqa: BLE001
        log.exception("çıkış karşı-olgusu bağlanamadı; paper onsuz sürer")
        return None
