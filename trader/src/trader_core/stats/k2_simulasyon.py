"""K2 rastgele-giris simulasyon testi (yalniz arastirma/raporlama araci; canli/paper etkisi yok).

1L3A ``motor/arastirma/v2/test.py`` (``p_degeri``, ``ceyrek_sinirlari``, ``k2_simule``, ``test_asamasi`` iki asamasi) ve
``evren_k2.py`` (``tek_islem_r``) mantigindan ML'ye uyarlandi. Fikir: her gercek islem icin yon, stop/ATR kati, azami tutma ve
maliyet korunur; giris mumu ayni TAKVIM CEYREGI (UTC) icinden tekduze rastgele cekilir. Istatistik T = toplam R. Bir stratejinin
gercek T'si rastgele-giris dagiliminin ust kuyrugundaysa strateji "zamanlama"dan deger katiyordur.

    p = (1 + #{sim >= gercek}) / (B + 1)

Iki asama (1L3A 5.3): B1 = 500; p <= 0.02 ise YENI tohumla B2; nihai p yalniz 2. asamadan. Birden cok strateji icin
``k2_duzelt`` p'leri mevcut ``stats.adjust_pvalues`` (BH/BHY) ile duzeltir.

Sadelestirme (1L3A'dan): cikis modeli = ATR tabanli stop (+ istege bagli R hedefi) + azami tutma (mum) + sabit komisyon/kayma;
stratejiye ozgu cikis kurallari (iz suren stop, sinyal cikisi vb.) yoktur. Bunlar gerekiyorsa ``cikis_fn`` ile enjekte edilir:
``cikis_fn(j, yon, mult, hold) -> R | None`` (None = gecersiz giris, yeniden cekilir).
"""
from __future__ import annotations

import math
import zlib
from dataclasses import dataclass
from typing import Callable, Mapping

import numpy as np
import pandas as pd

from ..indicators import atr as _atr
from .stats import adjust_pvalues

__all__ = ["K2Maliyet", "p_degeri", "ceyrek_sinirlari", "tek_islem_r", "k2_simule", "k2_testi", "k2_duzelt",
           "K2_B1", "K2_B2", "K2_GECIS_P"]

K2_B1 = 500
K2_B2 = 5000
K2_GECIS_P = 0.02
_YENIDEN_CEKIM = 8


@dataclass(frozen=True)
class K2Maliyet:
    """Giris/cikis kaymasi (oran) ve taker komisyonu (oran, taraf basi)."""
    kayma: float = 2e-4
    stop_kayma: float = 5e-4
    taker: float = 5e-4


def p_degeri(gercek: float, sim) -> float:
    """p = (1 + #{sim >= gercek}) / (B + 1). NaN gercek -> NaN; NaN simulasyon esitsizligi saglamaz."""
    s = np.asarray(sim, dtype=float)
    if not np.isfinite(gercek):
        return math.nan
    return float((1 + int((s >= gercek).sum())) / (s.size + 1))


def ceyrek_sinirlari(giris_zamanlari, alt_sinir=None) -> tuple[pd.DatetimeIndex, pd.DatetimeIndex]:
    """Her girisin takvim ceyregi [bas, bit) (UTC). ``alt_sinir`` ceyrek basini bunun altina indirmez."""
    gi = pd.DatetimeIndex(giris_zamanlari)
    gi = gi.tz_localize("UTC") if gi.tz is None else gi.tz_convert("UTC")
    donem = gi.tz_localize(None).to_period("Q")
    bas = donem.start_time.tz_localize("UTC")
    bit = (donem + 1).start_time.tz_localize("UTC")
    if alt_sinir is not None:
        lo = pd.Timestamp(alt_sinir)
        lo = lo.tz_localize("UTC") if lo.tzinfo is None else lo.tz_convert("UTC")
        bas = pd.DatetimeIndex(np.maximum(bas.asi8, lo.as_unit("ns").value)).tz_localize("UTC")
    return bas, bit


def tek_islem_r(o, h, l, c, atr, j: int, yon: int, hold: int, mult: float, m: K2Maliyet, hedef_r: float = math.nan):
    """j. mumun acilisinda giris (sinyal j-1 kapanisi), stop = c[j-1] -/+ mult*ATR[j-1]; stop/hedef/zaman cikisi -> R. Gecersizse None."""
    if not (np.isfinite(atr[j - 1]) and mult > 0) or j < 1:
        return None
    giris = o[j] * (1 + yon * m.kayma)
    stop = c[j - 1] - yon * mult * atr[j - 1]
    risk = (giris - stop) * yon
    if not risk > 0:
        return None
    n = len(o)
    son = min(j + max(int(hold), 1), n - 1)
    hedef = giris + yon * hedef_r * risk if (hedef_r == hedef_r and hedef_r > 0) else None
    cikis = None
    for b in range(j, son):
        ks = (o[b] <= stop or l[b] <= stop) if yon == 1 else (o[b] >= stop or h[b] >= stop)
        if ks:
            gap = o[b] <= stop if yon == 1 else o[b] >= stop
            cikis = (o[b] if gap else stop) * (1 - yon * m.stop_kayma)
            break
        if hedef is not None and ((h[b] >= hedef) if yon == 1 else (l[b] <= hedef)):
            gap = o[b] >= hedef if yon == 1 else o[b] <= hedef
            cikis = o[b] if gap else hedef
            break
    if cikis is None:
        cikis = o[son] * (1 - yon * m.kayma)
    return float((yon * (cikis - giris) - m.taker * (giris + cikis)) / risk)


def _hazirla(mumlar: pd.DataFrame, atr_periyot: int):
    for k in ("date", "open", "high", "low", "close"):
        if k not in mumlar.columns:
            raise ValueError(f"mumlarda '{k}' sutunu yok")
    t = pd.DatetimeIndex(mumlar["date"])
    t = t.tz_localize("UTC") if t.tz is None else t.tz_convert("UTC")
    if not t.is_monotonic_increasing:
        raise ValueError("mumlar zamana gore sirali olmali")
    a = _atr(mumlar, atr_periyot).to_numpy(float)
    return t, [mumlar[k].to_numpy(float) for k in ("open", "high", "low", "close")], a


def k2_simule(islemler: pd.DataFrame, mumlar: pd.DataFrame, n_sim: int, tohum: int, *, maliyet: K2Maliyet = K2Maliyet(),
              atr_periyot: int = 14, hedef_r: float = math.nan, alt_sinir=None,
              cikis_fn: Callable | None = None) -> dict:
    """Tek enstruman. ``islemler`` sutunlari: giris_zamani, yon (+1/-1), stop_carpan (stop mesafesi / ATR14[giris-1]),
    tutma (mum sayisi). -> ``{'toplam_r': (n_sim,), 'n_gecersiz', 'n_islem'}``. Islem basina RNG = default_rng([tohum, i, crc32(...)])
    (ayni tohum -> ayni sonuc). Bir cekim gecersizse en cok 8 kez yeniden cekilir; olmazsa o islem o simulasyonda atlanir."""
    for k in ("giris_zamani", "yon", "stop_carpan", "tutma"):
        if k not in islemler.columns:
            raise ValueError(f"islemlerde '{k}' sutunu yok")
    t, (o, h, l, c), a = _hazirla(mumlar, atr_periyot)
    n = len(t)
    gi = pd.DatetimeIndex(islemler["giris_zamani"])
    gi = gi.tz_localize("UTC") if gi.tz is None else gi.tz_convert("UTC")
    qbas, qbit = ceyrek_sinirlari(gi, alt_sinir)
    toplam = np.zeros(n_sim)
    gecersiz = 0
    for i in range(len(islemler)):
        yon, mult, hold = int(islemler["yon"].iat[i]), float(islemler["stop_carpan"].iat[i]), int(islemler["tutma"].iat[i])
        lo = max(1, int(t.searchsorted(qbas[i], "left")))
        hi = min(int(t.searchsorted(qbit[i], "left")), n - max(hold, 1))
        if hi <= lo:
            hi = lo + 1
        rng = np.random.default_rng([tohum, i, zlib.crc32(str(gi[i]).encode())])
        u = rng.random((n_sim, _YENIDEN_CEKIM))
        j = np.clip((lo + u * (hi - lo)).astype(np.int64), 1, n - 2)
        onb: dict = {}

        def deger(jj: int) -> float:
            if jj not in onb:
                r = (cikis_fn(jj, yon, mult, hold) if cikis_fn is not None
                     else tek_islem_r(o, h, l, c, a, jj, yon, hold, mult, maliyet, hedef_r))
                onb[jj] = math.nan if r is None else float(r)
            return onb[jj]
        sonuc = np.full(n_sim, np.nan)
        bekleyen = np.arange(n_sim)
        for e in range(_YENIDEN_CEKIM):
            if not bekleyen.size:
                break
            uj, ters = np.unique(j[bekleyen, e], return_inverse=True)
            vals = np.array([deger(int(x)) for x in uj])[ters]
            ok = np.isfinite(vals)
            sonuc[bekleyen[ok]] = vals[ok]
            bekleyen = bekleyen[~ok]
        gecersiz += int(bekleyen.size)
        toplam += np.where(np.isfinite(sonuc), sonuc, 0.0)
    return {"toplam_r": toplam, "n_gecersiz": gecersiz, "n_islem": int(len(islemler)) * n_sim}


def k2_testi(gercek_r: float, simule: Callable[[int, int], np.ndarray], tohum: int, *, b1: int = K2_B1, b2: int = K2_B2,
             gecis_p: float = K2_GECIS_P) -> dict:
    """Iki asamali test (1L3A `test_asamasi`). ``simule(n_sim, tohum) -> toplam_r dizisi``. B1; p1 <= gecis_p ise YENI tohumla
    (tohum ^ 0x9E3779B1) B2; nihai p yalniz son asamadan. -> ``{'p', 'p1', 'p2', 'asama', 'B'}``."""
    s1 = np.asarray(simule(b1, tohum), dtype=float)
    p1 = p_degeri(gercek_r, s1)
    if not (p1 <= gecis_p):
        return {"p": p1, "p1": p1, "p2": math.nan, "asama": 1, "B": b1}
    s2 = np.asarray(simule(b2, tohum ^ 0x9E3779B1), dtype=float)
    p2 = p_degeri(gercek_r, s2)
    return {"p": p2, "p1": p1, "p2": p2, "asama": 2, "B": b2}


def k2_duzelt(p: Mapping[str, float], method: str = "bh", q: float = 0.10) -> dict:
    """Strateji p'lerini mevcut ``adjust_pvalues`` (bh/bhy/holm...) ile duzeltir. NaN p reddedilmez (p=1 sayilir).
    -> ``{'p_duz': {ad: p}, 'kesif': [ad,...]}`` (kesif: duzeltilmis p <= q)."""
    ad = sorted(p)
    ham = np.array([1.0 if not np.isfinite(p[k]) else float(p[k]) for k in ad])
    duz = adjust_pvalues(ham, method)
    return {"p_duz": dict(zip(ad, map(float, duz))), "kesif": [k for k, d in zip(ad, duz) if d <= q]}
