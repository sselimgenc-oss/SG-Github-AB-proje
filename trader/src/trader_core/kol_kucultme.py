"""Kademeli boyut kucultme (20 Kasim 2026, yalniz kagit): kolun son kapanan islemlerinin net R toplamina gore islem basi
risk carpani. Spec: docs/motor/kademeli-kucultme-spec.md. Saf Python (stdlib); girdi: kolun kapanan islemlerinin net R
degerleri, EN YENIDEN ESKIYE.

Kural (kesin, deterministik):
  n >= 10 ve son 10'un toplami < 0  -> 0.3   (asgari boyut; kol ASLA kapatilmaz)
  degilse n >= 5 ve son 5'in toplami < 0 -> 0.5
  degilse 1.0
Carpan yalniz kucultur (<= 1.0); stop/kaldirac/gunluk limit/kademe (RK-1) anlamina dokunmaz. Geri yukselis otomatiktir:
pencere toplami >= 0 olunca carpan bir ust basamaga cikar (0.3 -> 0.5 -> 1.0)."""
from __future__ import annotations

import math
from typing import NamedTuple, Sequence

PENCERE_KISA = 5
PENCERE_UZUN = 10
CARPAN_YARI = 0.5
CARPAN_MIN = 0.3
KAYIT_SAYISI = PENCERE_UZUN


class KolKarar(NamedTuple):
    carpan: float
    n: int                      # degerlendirilen kapanmis islem sayisi (en cok 10)
    net_5: float | None         # son 5'in net R toplami (n < 5 ise None)
    net_10: float | None        # son 10'un net R toplami (n < 10 ise None)


def karar(net_r_yeniden_eskiye: Sequence[float]) -> KolKarar:
    vals = [float(v) for v in list(net_r_yeniden_eskiye)[:KAYIT_SAYISI] if v is not None and math.isfinite(float(v))]
    n = len(vals)
    n5 = math.fsum(vals[:PENCERE_KISA]) if n >= PENCERE_KISA else None
    n10 = math.fsum(vals[:PENCERE_UZUN]) if n >= PENCERE_UZUN else None
    if n10 is not None and n10 < 0:
        c = CARPAN_MIN
    elif n5 is not None and n5 < 0:
        c = CARPAN_YARI
    else:
        c = 1.0
    return KolKarar(c, n, n5, n10)


def ozellikler(k: KolKarar) -> dict:
    """Karar satiri `features` anahtarlari (yalniz kayit)."""
    out: dict = {"kol_boyut_carpani": float(k.carpan), "kol_n": int(k.n)}
    if k.net_5 is not None:
        out["kol_net_r_5"] = round(k.net_5, 6)
    if k.net_10 is not None:
        out["kol_net_r_10"] = round(k.net_10, 6)
    return out


def azaltilanlar(kol_sonuclari: "dict[str, Sequence[float]]") -> dict[str, KolKarar]:
    """{arm_id: net R (yeniden eskiye)} -> yalniz carpani < 1.0 olan kollar ({arm_id: KolKarar}); rapor/panel icin."""
    out: dict[str, KolKarar] = {}
    for arm, vals in kol_sonuclari.items():
        k = karar(vals)
        if k.carpan < 1.0:
            out[arm] = k
    return out


def satir(azaltilan: "dict[str, KolKarar]", en_cok: int = 4) -> str:
    """Telegram gunluk ozet satiri; azaltilan kol yoksa bos metin."""
    if not azaltilan:
        return ""
    parca = [f"{a} %{round(k.carpan * 100)}" for a, k in sorted(azaltilan.items())]
    ek = f" (+{len(parca) - en_cok})" if len(parca) > en_cok else ""
    return "Boyutu küçültülen kollar (son işlemler zararda): " + ", ".join(parca[:en_cok]) + ek
