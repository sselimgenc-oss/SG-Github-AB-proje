"""C1: CT kadro uzlasisi (belirtim docs/motor/c1-ct-kadro-spec.md bolum 3).

Kaynak: `var/ct/kadro_yon.json` (`scripts/ct_kadro_cek.py` yazar). Dosya yok / bayat (45 dk) / bozuk -> aday yok (motor calisir).
Sinyal (son kapanmis bar, karar ani D): cift icin kayit var; net_yon long|short; toplam = long+short >= 3; baskin taraf
max/toplam >= 0,70 ve net_yon ile ayni; net_nominal_usd (null degilse) yonle uyumlu isaretli.
Giris = mum kapanisi; stop = giris -/+ 1,5 ATR(14); hedef = giris +/- 2R (R = 1,5 ATR). Ayni (aralik, cift, yon) icin ayni
`uretildi_utc` ile tek aday. Yol: `TRADER_CT_KADRO` ortam degiskeni ya da <depo>/var/ct/kadro_yon.json (M1 ile ayni kalip).
"""
from __future__ import annotations

import os
from pathlib import Path

import numpy as np
import pandas as pd

from trader_core import ct_kadro as CK
from trader_core.signals import SIGNAL_COLUMNS

from . import ArmInput
from . import _pa as P

SETUP = "C1"
TIMEFRAMES = ("1h", "4h")
CORE = False
ML_SCORED = False
EXIT_MODE = "target"
PRIORITY = 80
# defter anahtari -> tasiyici sutun (6 tasiyicinin tamami): ct_long tamsayi oldugu icin pullback_ema'ya gider
FEATURES = {"ct_long": "pullback_ema", "ct_short": "ema_value", "ct_baskinlik": "body_ratio",
            "ct_net_nominal_usd": "wick_ratio", "ct_veri_yasi_sn": "edge_dist_atr", "rr": "rr"}
_REPO_ROOT = Path(__file__).resolve().parents[4]
MIN_TOPLAM = 3
BASKIN_MIN = 0.70
STOP_ATR = 1.5
TARGET_R = 2.0

_CACHE: dict = {"path": None, "mtime": None, "doc": None}     # ham (dogrulanmis) belge; yalniz dosya mtime degisince okunur
_EMITTED: dict[tuple[str, str, str], object] = {}              # (tf, cift, yon) -> son aday verilen uretildi_utc


def kadro_yolu() -> Path:
    return Path(os.environ.get("TRADER_CT_KADRO") or (_REPO_ROOT / "var" / "ct" / "kadro_yon.json"))


def _belge() -> dict | None:
    p = kadro_yolu()
    try:
        mt = p.stat().st_mtime_ns
    except OSError:
        _CACHE.update(path=None, mtime=None, doc=None)
        return None
    if _CACHE["path"] != str(p) or _CACHE["mtime"] != mt:
        _CACHE.update(path=str(p), mtime=mt, doc=CK.yukle(p))
    return _CACHE["doc"]


def _aday(inp: ArmInput):
    """(yon, kayit, uretildi, baskinlik) ya da None. Ortak tablo gerektirmez (aday yoksa hesap yok)."""
    doc = _belge()
    if doc is None:
        return None
    harita = CK.kadro_belgeden(doc, inp.D)
    kayit = None if harita is None else harita.get(inp.pair)
    if kayit is None:
        return None
    net = kayit["net_yon"]
    if net not in ("long", "short"):
        return None
    long_n, short_n = kayit["long"], kayit["short"]
    toplam = long_n + short_n
    if toplam < MIN_TOPLAM or long_n == short_n:
        return None
    dominant = "long" if long_n > short_n else "short"
    baskinlik = max(long_n, short_n) / toplam
    if baskinlik < BASKIN_MIN or dominant != net:
        return None
    nom = kayit["net_nominal_usd"]
    if nom is not None and ((net == "long" and not nom > 0) or (net == "short" and not nom < 0)):
        return None
    return net, kayit, harita["_uretildi"], baskinlik


def _bos(index) -> pd.DataFrame:
    """SIGNAL_COLUMNS sutunlu, aday yok tablosu (signal=False; aday alanlari NaN)."""
    n = len(index)
    obj = np.full(n, None, dtype=object)
    data = {c: np.full(n, np.nan) for c in SIGNAL_COLUMNS}
    data.update({"setup": obj, "side": obj.copy(), "skip_reason": obj.copy(), "regime": obj.copy(),
                 "reasons": np.full(n, "", dtype=object), "signal": np.zeros(n, dtype=bool),
                 "rh_touches": np.zeros(n, dtype="int64"), "rl_touches": np.zeros(n, dtype="int64"),
                 "pullback_ema": np.zeros(n, dtype="int64")})
    return pd.DataFrame({c: data[c] for c in SIGNAL_COLUMNS}, index=index)[SIGNAL_COLUMNS]


def compute(inp: ArmInput):
    aday = _aday(inp)
    if aday is None:
        return _bos(inp.trig.index)
    side, kayit, uretildi, baskinlik = aday
    key = (inp.tf, inp.pair, side)
    if _EMITTED.get(key) == uretildi:                 # ayni CT dosyasi icin tek aday
        return _bos(inp.trig.index)
    p = P.prepare(inp)
    i = len(p.c) - 1
    if i < 0 or not bool(p.ok[i]):
        return _bos(inp.trig.index)
    tab = P.Table(p.core)
    s = P.SIGN[side]
    atr = float(p.atr[i])
    entry = float(p.c[i])
    stop = entry - s * STOP_ATR * atr
    target = entry + s * TARGET_R * STOP_ATR * atr
    nom = kayit["net_nominal_usd"]
    tab.put(i, setup=SETUP, side=side, skip=None, labels=["ct", f"ct_{side}"], entry=entry, stop=stop, target=target,
            rr=TARGET_R, sda=STOP_ATR, ema=float(kayit["short"]), body=baskinlik,
            wick=float("nan") if nom is None else float(nom), edge=float(kayit["veri_yasi_sn"]), pb=int(kayit["long"]))
    _EMITTED[key] = uretildi
    return tab.frame()
