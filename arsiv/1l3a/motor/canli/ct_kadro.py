"""CT projesinin trader kadrosu yön özeti (ct.kadro_yon.v1) -> 1L3A girdisi + "ct_konsensus" paper hesabının sinyal kuralı.

KULLANICI KARARI 2026-11-19: CT verisini girdi al; buna dayanarak işlem açan AYRI bir paper hesabı kur (yalnız paper; canlı yürütücüye bağlanmaz).
Giriş noktası: motor/canli/ct_paper.py. Mevcut 10'lu paper setine (imza fffbc6624416634e) DOKUNMAZ.

ÖN KAYIT (aşağıdaki sabitler değişmez; değişiklik = yeni ön kayıt + kullanıcı kararı):
  Her 15 dk'lık mum kapanışında (karar anı) TAZE veri varsa, eşlenen coinlerde:
    (long_trader + short_trader) >= MIN_TRADER  VE  çoğunluk oranı >= MIN_ORAN  VE  net_yon long/short (çoğunluk tarafı = net_yon)  -> o yönde sinyal.
  Sinyaller |net_nominal_usd| azalan sırayla; en çok MAX_POZ açık pozisyon; aynı sembolde açık pozisyon varsa yeni giriş yok.
  Giriş bir sonraki mumun açılışında (motor kuralı). Stop = STOP_ATR x ATR(ATR_PERIYOT, 15m), hedef = HEDEF_ATR x ATR.
  Ek çıkış: konsensüs ters döner (net_yon zıt) ya da coin listeden düşer -> sonraki mumda kapanır.
  Veri bayatsa (uretildi_utc karar anından BAYAT_DK dk'dan eski) ya da hiç yoksa: yeni giriş YOK ve konsensüs çıkışı YOK; açıklar kendi stop/hedefiyle yönetilir.
  Lookahead yok: yalnız uretildi_utc <= karar anı olan kayıt kullanılır. HIP-3 ("dex:COIN") coinleri atlanır.
  İşlem başı risk, kasa, kill, günlük limit: SERT_LIMITLER (motor/risk/limitler.py) aynen; burada kopyası yok.

Alıcı: ağ hatası yutulur + loglanır (motor bloklanmaz); çekim arka plan iş parçacığında, en seyrek CACHE_SN'de bir; ham kopya durum dizininde
`ct_kadro/kadro_yon.jsonl`'e eklenir (geçmiş birikir; JSONL_MAX_BAYT aşılınca döndürülür, en çok YEDEK_SAYISI yedek tutulur).
"""
from __future__ import annotations

import json
import logging
import math
import os
import threading
import time
from datetime import timezone
from decimal import Decimal
from pathlib import Path
from typing import Callable, Optional

import numpy as np
import pandas as pd

from motor.strateji import gostergeler as gst
from motor.strateji.temel import Strateji

log = logging.getLogger("paper.ct")
KOK = Path(__file__).resolve().parents[2]

# ------------------------------------------------------------------------------------------- ön kayıt sabitleri (DEĞİŞMEZ)
SEMA = "ct.kadro_yon.v1"
VARSAYILAN_URL = "https://raw.githubusercontent.com/sselimgenc-oss/CT-Proje/canli-durum/durum/paylasim/kadro_yon_v1.json"
URL_ENV = "L3A_CT_URL"
HESAP_AD = "ct_konsensus"
TF = "15m"
MIN_TRADER = 5            # long_trader + short_trader >= 5
MIN_ORAN = 0.70           # çoğunluk oranı >= %70 (tam tamsayı karşılaştırması: 10*coğunluk >= 7*toplam)
MAX_POZ = 3               # en çok 3 açık pozisyon
VERI_YASI_MAX_SN = 45 * 60  # coin başı `veri_yasi_sn` bu eşiği aşarsa o coinde YENİ giriş yok (eşik = dosya tazelik eşiği BAYAT_DK); açık pozisyon çıkışı etkilenmez
BAYAT_DK = 45             # uretildi_utc karar anından 45 dk'dan eskiyse veri YOK
ATR_PERIYOT = 14
STOP_ATR = 2.0
HEDEF_ATR = 3.0
BASLANGIC_KASA = 10000.0
AYAR_ETIKETI = "ct_kadro_yon_v1:min5_oran70_max3_atr14_s2_h3"
# alıcı
CACHE_SN = 300            # iki çekim arası en az 5 dk
ZAMAN_ASIMI_SN = 15
JSONL_MAX_BAYT = 5_000_000
YEDEK_SAYISI = 12
BELLEK_KAYIT = 200        # bellekte tutulan son kayıt sayısı (15 dk'da bir yayın: ~2 gün)
ESLEME_YOLU = KOK / "stratejiler" / "ct_sembol_esleme.json"

ZORUNLU_UST = {"sema": str, "uretildi_utc": str, "saha_trader_sayisi": int, "kip": str, "notlar": (str, list, type(None)), "coinler": list}
ZORUNLU_COIN = {"coin": str, "long_trader": int, "short_trader": int, "net_yon": str, "nominal_long_usd": (int, float),
                "nominal_short_usd": (int, float), "veri_yasi_sn": (int, float)}
NET_YONLER = ("long", "short", "notr")


class KadroSemaHatasi(ValueError):
    """Gelen JSON ct.kadro_yon.v1 şemasına uymuyor (veri reddedilir)."""


def _tam_sayi(x) -> bool:
    return isinstance(x, int) and not isinstance(x, bool)


def zaman_coz(s: str) -> pd.Timestamp:
    t = pd.Timestamp(s)
    return t.tz_localize("UTC") if t.tzinfo is None else t.tz_convert("UTC")


def dogrula(d) -> dict:
    """Şemayı doğrular; uymazsa KadroSemaHatasi. Geçerliyse aynı sözlüğü döner (değiştirmez)."""
    if not isinstance(d, dict):
        raise KadroSemaHatasi("kök nesne değil")
    if d.get("sema") != SEMA:
        raise KadroSemaHatasi(f"sema {d.get('sema')!r} != {SEMA!r}")
    for k, tip in ZORUNLU_UST.items():
        if k not in d:
            raise KadroSemaHatasi(f"zorunlu alan yok: {k}")
        v = d[k]
        if k == "saha_trader_sayisi":
            if not _tam_sayi(v):
                raise KadroSemaHatasi("saha_trader_sayisi tam sayı değil")
        elif not isinstance(v, tip) or isinstance(v, bool):
            raise KadroSemaHatasi(f"{k}: tip uyumsuz ({type(v).__name__})")
    if d.get("kadro_surumu") is not None and not isinstance(d["kadro_surumu"], (str, int)):
        raise KadroSemaHatasi("kadro_surumu tip uyumsuz")
    try:
        zaman_coz(d["uretildi_utc"])
    except Exception as e:  # noqa: BLE001
        raise KadroSemaHatasi(f"uretildi_utc çözülemedi: {d['uretildi_utc']!r}") from e
    for i, c in enumerate(d["coinler"]):
        if not isinstance(c, dict):
            raise KadroSemaHatasi(f"coinler[{i}] nesne değil")
        for k, tip in ZORUNLU_COIN.items():
            if k not in c:
                raise KadroSemaHatasi(f"coinler[{i}] zorunlu alan yok: {k}")
            v = c[k]
            if tip is int:
                if not _tam_sayi(v):
                    raise KadroSemaHatasi(f"coinler[{i}].{k} tam sayı değil")
            elif not isinstance(v, tip) or isinstance(v, bool):
                raise KadroSemaHatasi(f"coinler[{i}].{k} tip uyumsuz")
        if c["long_trader"] < 0 or c["short_trader"] < 0:
            raise KadroSemaHatasi(f"coinler[{i}] negatif trader sayısı")
        if c["net_yon"] not in NET_YONLER:
            raise KadroSemaHatasi(f"coinler[{i}].net_yon geçersiz: {c['net_yon']!r}")
        n = c.get("net_nominal_usd")
        if n is not None and (isinstance(n, bool) or not isinstance(n, (int, float)) or not math.isfinite(n)):
            raise KadroSemaHatasi(f"coinler[{i}].net_nominal_usd sayı/null değil")
        for k in ("nominal_long_usd", "nominal_short_usd", "veri_yasi_sn"):
            if not math.isfinite(c[k]):
                raise KadroSemaHatasi(f"coinler[{i}].{k} sonlu değil")
    return d


# ------------------------------------------------------------------------------------------- sembol eşleme
def esleme_yukle(yol: Path = ESLEME_YOLU) -> dict:
    """{HL adı: (binance_sembol, çarpan)}. Dosya bozuksa açık hata (fail-closed)."""
    j = json.loads(Path(yol).read_text(encoding="utf-8"))
    if j.get("sema") != "1l3a.ct_sembol_esleme.v1":
        raise ValueError(f"{yol}: tanınmayan sema")
    out = {}
    for hl, v in j["semboller"].items():
        if not v["binance"].endswith("USDT") or not float(v["carpan"]) > 0:
            raise ValueError(f"{yol}: {hl}: geçersiz kayıt {v}")
        out[hl] = (v["binance"], float(v["carpan"]))
    return out


def hip3_mu(coin: str) -> bool:
    return ":" in coin


# ------------------------------------------------------------------------------------------- alıcı
class KadroAlici:
    """Kadro yön özetini çeker, doğrular, jsonl'e ekler; `gecerli(karar_zamani)` ile bellekten (ağsız) okunur.
    `getir_fn() -> metin(JSON)`: ağ katmanı (testte sahte). Hatalar yutulur (None döner, loglanır); motoru bloklamaz."""

    def __init__(self, dizin: Optional[Path] = None, url: Optional[str] = None, getir_fn: Optional[Callable[[], str]] = None,
                 saat: Callable[[], float] = time.time, cache_sn: float = CACHE_SN):
        self.dizin = Path(dizin) if dizin is not None else None
        self.url = url or os.environ.get(URL_ENV) or VARSAYILAN_URL
        self.getir_fn = getir_fn or self._http
        self.saat = saat
        self.cache_sn = cache_sn
        self.kayitlar: list = []                   # [(uretildi Timestamp, ham dict)] uretildi'ye göre sıralı
        self.son_deneme: Optional[float] = None
        self.son_hata: Optional[str] = None
        self.hata_sayisi = 0
        self._kilit = threading.Lock()
        self._dur = threading.Event()
        self._is_parcasi: Optional[threading.Thread] = None
        if self.dizin is not None:
            self._gecmisi_yukle()

    # --- ağ
    def _http(self) -> str:
        import requests
        r = requests.get(self.url, timeout=ZAMAN_ASIMI_SN, headers={"User-Agent": "1l3a-ct-paper"})
        r.raise_for_status()
        return r.text

    # --- kalıcılık
    @property
    def _jsonl(self) -> Optional[Path]:
        return None if self.dizin is None else self.dizin / "kadro_yon.jsonl"

    def _gecmisi_yukle(self) -> None:
        yol = self._jsonl
        if yol is None or not yol.exists():
            return
        try:
            son = yol.read_text(encoding="utf-8").splitlines()[-BELLEK_KAYIT:]
        except OSError as e:
            log.warning("ct_kadro geçmişi okunamadı: %s", e)
            return
        for s in son:
            try:
                ham = dogrula(json.loads(s)["veri"])
                self._ekle_bellek(ham)
            except Exception:  # noqa: BLE001
                continue                         # bozuk satır atlanır (kullanılmaz)

    def _ekle_bellek(self, ham: dict) -> bool:
        u = zaman_coz(ham["uretildi_utc"])
        with self._kilit:
            if any(k[0] == u for k in self.kayitlar):
                return False
            self.kayitlar.append((u, ham))
            self.kayitlar.sort(key=lambda k: k[0])
            del self.kayitlar[:-BELLEK_KAYIT]
        return True

    def _yaz(self, ham: dict) -> None:
        yol = self._jsonl
        if yol is None:
            return
        yol.parent.mkdir(parents=True, exist_ok=True)
        if yol.exists() and yol.stat().st_size >= JSONL_MAX_BAYT:
            damga = pd.Timestamp.now(tz="UTC").strftime("%Y%m%dT%H%M%S")
            yol.rename(yol.with_name(f"kadro_yon.{damga}.jsonl"))
            eski = sorted(yol.parent.glob("kadro_yon.*.jsonl"))
            for f in eski[:-YEDEK_SAYISI]:
                f.unlink(missing_ok=True)
        satir = {"alindi_utc": pd.Timestamp.now(tz="UTC").strftime("%Y-%m-%dT%H:%M:%SZ"), "veri": ham}
        with open(yol, "a", encoding="utf-8") as f:
            f.write(json.dumps(satir, ensure_ascii=False, separators=(",", ":")) + "\n")
            f.flush()
            os.fsync(f.fileno())

    # --- çekim
    def getir(self, zorla: bool = False) -> Optional[dict]:
        """Önbellek süresi dolduysa çeker. -> yeni kayıt (dict) | None (önbellek içinde, hata ya da yinelenen yayın). ASLA istisna fırlatmaz."""
        simdi = self.saat()
        if not zorla and self.son_deneme is not None and simdi - self.son_deneme < self.cache_sn:
            return None
        self.son_deneme = simdi
        try:
            ham = dogrula(json.loads(self.getir_fn()))
        except Exception as e:  # noqa: BLE001  (ağ/JSON/şema: yut + logla)
            self.hata_sayisi += 1
            self.son_hata = f"{type(e).__name__}: {e}"[:300]
            log.warning("ct_kadro çekilemedi/reddedildi (%d): %s", self.hata_sayisi, self.son_hata)
            return None
        self.son_hata = None
        if not self._ekle_bellek(ham):
            return None
        try:
            self._yaz(ham)
        except OSError as e:
            log.warning("ct_kadro jsonl yazılamadı: %s", e)
        return ham

    def baslat_arka_plan(self) -> None:
        if self._is_parcasi is not None:
            return

        def dongu():
            while not self._dur.is_set():
                self.getir()
                self._dur.wait(self.cache_sn)
        self._is_parcasi = threading.Thread(target=dongu, name="ct-kadro-alici", daemon=True)
        self._is_parcasi.start()

    def durdur(self) -> None:
        self._dur.set()

    # --- okuma
    def gecerli(self, karar_zamani) -> Optional[dict]:
        """Karar anında geçerli kayıt: uretildi_utc <= karar_zamani (lookahead yok) ve yaş <= BAYAT_DK; yoksa None (veri YOK)."""
        kz = pd.Timestamp(karar_zamani)
        kz = kz.tz_localize("UTC") if kz.tzinfo is None else kz.tz_convert("UTC")
        with self._kilit:
            adaylar = [k for k in self.kayitlar if k[0] <= kz]
        if not adaylar:
            return None
        u, ham = adaylar[-1]
        if kz - u > pd.Timedelta(minutes=BAYAT_DK):
            return None
        return ham


# ------------------------------------------------------------------------------------------- konsensüs planı
def _yon_sayisi(y: str) -> int:
    return 1 if y == "long" else -1


def sinyal_var(c: dict) -> Optional[int]:
    """Giriş kuralı (ön kayıt): +1 long, -1 short, None. Çoğunluk tarafı net_yon ile aynı olmalı."""
    if c["net_yon"] not in ("long", "short"):
        return None
    yas = c.get("veri_yasi_sn")
    if isinstance(yas, (int, float)) and yas > VERI_YASI_MAX_SN:      # bayat coin verisi: yeni işlem açılmaz
        return None
    n = c["long_trader"] + c["short_trader"]
    if n < MIN_TRADER:
        return None
    ceks, taraf = (c["long_trader"], "long") if c["long_trader"] >= c["short_trader"] else (c["short_trader"], "short")
    if c["long_trader"] == c["short_trader"] or taraf != c["net_yon"]:
        return None
    if ceks * 10 < round(MIN_ORAN * 10) * n:          # ceks/n >= 0.70, tamsayı karşılaştırma
        return None
    return _yon_sayisi(c["net_yon"])


class Plan:
    """Bir karar anının sonucu. giris: {binance sembol: yön}; liste: {binance sembol: (net_yon, coin kaydı)}; taze: bool."""
    __slots__ = ("taze", "giris", "liste", "uretildi")

    def __init__(self, taze=False, giris=None, liste=None, uretildi=None):
        self.taze, self.giris, self.liste, self.uretildi = taze, giris or {}, liste or {}, uretildi

    def cikis(self, sembol: str, yon: int) -> bool:
        """Açık pozisyon (yön) için konsensüs çıkışı: taze veri + (listeden düştü ya da net_yon zıt)."""
        if not self.taze:
            return False
        e = self.liste.get(sembol)
        if e is None:
            return True
        return e[0] == ("short" if yon == 1 else "long")


class KonsensusDeposu:
    """Sembol bağımsız ortak karar nesnesi: aynı karar anında tüm sembol stratejileri AYNI planı görür (en çok MAX_POZ, sıralama)."""

    def __init__(self, alici: KadroAlici, esleme: dict, acik_fn: Callable[[], dict] = lambda: {}):
        self.alici, self.esleme = alici, esleme
        self.acik_fn = acik_fn                      # () -> {binance sembol: yön (+1/-1)} açık pozisyonlar
        self.bekleyen_fn: Callable[[], dict] = lambda: {}      # () -> {binance sembol: 1} bekleyen (dolmamış) girişler; MAX_POZ'a sayılır
        self._onbellek: dict = {}
        self._atlanan: set = set()                  # eşlemede olmayan coinler (bir kez loglanır)

    def motor_bagla(self, motor) -> None:
        self.acik_fn = lambda: {p.sembol: int(p.yon) for p in motor.acik.values()}
        # bekleyen (önceki barda kurulmuş, henüz dolmamış) girişler: birimler aynı barda sırayla işlenir, sonraki birimin dolumu `acik`'ta yoktur
        self.bekleyen_fn = lambda: {k.sembol: 1 for k in motor.tum_kollar
                                    if getattr(k, "giris_emri", None) is not None and k.kimlik not in motor.acik
                                    and k.sembol not in {p.sembol for p in motor.acik.values()}}

    def _logla_atlanan(self, coin: str) -> None:
        if coin not in self._atlanan:
            self._atlanan.add(coin)
            log.info("ct_kadro: %s eşlemede yok, atlandı", coin)

    def plan(self, karar_zamani) -> Plan:
        kz = pd.Timestamp(karar_zamani)
        if kz in self._onbellek:
            return self._onbellek[kz]
        ham = self.alici.gecerli(kz)
        if ham is None:
            p = Plan(False)
        else:
            liste = {}
            for c in ham["coinler"]:
                if hip3_mu(c["coin"]):
                    continue
                e = self.esleme.get(c["coin"])
                if e is None:
                    self._logla_atlanan(c["coin"])
                    continue
                liste[e[0]] = (c["net_yon"], c)
            acik = self.acik_fn()
            tutulan = [s for s, y in acik.items() if s in liste and not Plan(True, None, liste).cikis(s, y)]
            bekleyen = {s for s in self.bekleyen_fn() if s not in acik}
            bos = max(0, MAX_POZ - len(tutulan) - len(bekleyen))
            aday = []
            for s, (ny, c) in liste.items():
                if s in acik or s in bekleyen:
                    continue
                y = sinyal_var(c)
                if y is not None:
                    nn = c.get("net_nominal_usd")
                    aday.append((-(abs(float(nn)) if nn is not None else 0.0), s, y))
            aday.sort()
            p = Plan(True, {s: y for _, s, y in aday[:bos]}, liste, ham["uretildi_utc"])
        if len(self._onbellek) > 64:
            self._onbellek.clear()
        self._onbellek[kz] = p
        return p


# ------------------------------------------------------------------------------------------- strateji (motor arayüzü)
class CtKonsensus(Strateji):
    """Tek sembole bağlı strateji nesnesi (paper motoru tek_grafik kolu). Sinyal = KonsensusDeposu.plan(karar anı); stop/hedef ATR tabanlı."""
    ad = HESAP_AD
    stil = "daytrade"
    varsayilan_parametreler = {}

    def __init__(self, sembol: str, deposu: KonsensusDeposu):
        super().__init__()
        self.sembol, self.deposu = sembol, deposu

    def cikis_var_mi(self) -> bool:
        return True                              # her girişte stop + hedef üretilir

    def yeni(self, **p):
        return CtKonsensus(self.sembol, self.deposu)

    def sinyaller(self, mumlar: pd.DataFrame) -> pd.DataFrame:
        n = len(mumlar)
        sig = pd.DataFrame({"yon": np.zeros(n, dtype=int), "stop": np.full(n, np.nan), "hedef": np.full(n, np.nan),
                            "cikis": np.zeros(n, dtype=bool), "cikis_long": np.zeros(n, dtype=bool), "cikis_short": np.zeros(n, dtype=bool)},
                           index=mumlar.index)
        if n == 0:
            return sig
        karar_zamani = mumlar.index[-1] + pd.Timedelta(minutes=15)          # mumun kapanışı (karar anı)
        pl = self.deposu.plan(karar_zamani)
        if not pl.taze:
            return sig
        sig.iloc[-1, sig.columns.get_loc("cikis_long")] = pl.cikis(self.sembol, 1)
        sig.iloc[-1, sig.columns.get_loc("cikis_short")] = pl.cikis(self.sembol, -1)
        y = pl.giris.get(self.sembol)
        if y:
            atr = float(gst.atr(mumlar["yuksek"], mumlar["dusuk"], mumlar["kapanis"], ATR_PERIYOT).iloc[-1])
            c = float(mumlar["kapanis"].iloc[-1])
            if math.isfinite(atr) and atr > 0 and math.isfinite(c):
                sig.iloc[-1, sig.columns.get_loc("yon")] = y
                sig.iloc[-1, sig.columns.get_loc("stop")] = c - y * STOP_ATR * atr
                sig.iloc[-1, sig.columns.get_loc("hedef")] = c + y * HEDEF_ATR * atr
                e = pl.liste[self.sembol][1]
                sig["ct_long_trader"] = np.nan
                sig["ct_short_trader"] = np.nan
                sig["ct_net_nominal_usd"] = np.nan
                sig.iloc[-1, sig.columns.get_loc("ct_long_trader")] = e["long_trader"]          # giriş gerekçesi göstergeleri (denetim)
                sig.iloc[-1, sig.columns.get_loc("ct_short_trader")] = e["short_trader"]
                if e.get("net_nominal_usd") is not None:
                    sig.iloc[-1, sig.columns.get_loc("ct_net_nominal_usd")] = float(e["net_nominal_usd"])
        return sig


def tanimlar_olustur(esleme: dict, deposu: KonsensusDeposu) -> list:
    """Eşlemedeki her Binance sembolü için bir tek_grafik StratejiTanim (15m, kasa payı 1 = işlem başı risk SERT_LIMITLER'den)."""
    from motor.canli.paper_sinyal import StratejiTanim
    out = []
    for b in sorted({v[0] for v in esleme.values()}):
        st = CtKonsensus(b, deposu)
        out.append(StratejiTanim(f"{HESAP_AD}|{b}|{TF}", "ct", "tek_grafik", HESAP_AD, b, TF, AYAR_ETIKETI, st, "tek_grafik", Decimal(1),
                                 ayar_dosyasi="stratejiler/ct_sembol_esleme.json + ct_kadro.py ön kayıt sabitleri", etiket=HESAP_AD))
    return out
