"""Aday tablosu semasi (girdi sozlesmesi) ve yukleyici.

19b (backtester'in gecmis adaylari) bu semada bir parquet/csv uretir; `load_candidates` onu okur.
Her satir BIR ADAY KARAR (alinan + atlanan). Zaman damgasi `ts` = aday mumun KAPANIS zamani (UTC);
ozellikler yalniz bu ana kadar kapanmis mumlardan uretilmistir (canli ile ayni uretici, §3.2).

Zorunlu sutunlar:
  pair            str    'BTC/USDT:USDT' benzeri
  ts              UTC    karar ani (aday 1s mumun kapanisi)
  setup           str    'T1' | 'R1'
  side            str    'long' | 'short'
  planned_entry   float
  planned_stop    float  long: < entry, short: > entry
  planned_target  float  R1 icin hedef, T1 icin NaN (izleyen stop)
  source          str    'real' | 'paper' | 'counterfactual' | 'backtest'
  taken           bool   strateji bu adayi aldi mi
  label           float  uclu bariyer: 1 (+2R once) | 0 (stop/sure) | NaN (cozulmemis)
  label_end_ts    UTC    bariyer temas / ufuk sonu zamani (sizinti temizligi icin)
  net_r           float  GERCEK cikis kuraliyla maliyet sonrasi net R (degerlendirme olcusu, §3.1)
  cost_r          float  tur (giris+cikis) maliyetin R cinsinden payi: YALNIZ komisyon+kayma = 2*(fee+slip)*entry/|entry-stop|
                         (funding/spread yok; stres testi entry/R'yi bundan turetir)
  exit_ts         UTC    GERCEK cikis zamani (alinan islemlerde zorunlu; alinmayanlarda NaT/yok sayilir).
                         f_bars_since_exit yalniz alinan islemlerin gercek cikislarindan uretilir
  f_*             float  ozellikler (en fazla 40)
"""
from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

from .config import MAX_FEATURES, SOURCE_WEIGHTS
from .guards import assert_pre_holdout

REQUIRED = ["pair", "ts", "setup", "side", "planned_entry", "planned_stop", "planned_target",
            "source", "taken", "label", "label_end_ts", "exit_ts", "net_r", "cost_r"]
FEATURE_PREFIX = "f_"


class SchemaError(ValueError):
    pass


def feature_columns(df: pd.DataFrame) -> list[str]:
    return sorted(c for c in df.columns if c.startswith(FEATURE_PREFIX))


def validate_candidates(df: pd.DataFrame) -> pd.DataFrame:
    miss = [c for c in REQUIRED if c not in df.columns]
    if miss:
        raise SchemaError(f"zorunlu sutunlar eksik: {miss}")
    feats = feature_columns(df)
    if not feats:
        raise SchemaError("hic f_* ozellik sutunu yok")
    if len(feats) > MAX_FEATURES:
        raise SchemaError(f"ozellik sayisi {len(feats)} > {MAX_FEATURES}")
    out = df.copy()
    out["ts"] = pd.to_datetime(out["ts"], utc=True)
    out["label_end_ts"] = pd.to_datetime(out["label_end_ts"], utc=True)
    out["exit_ts"] = pd.to_datetime(out["exit_ts"], utc=True)
    assert_pre_holdout(out["ts"], "aday tablosu ts")
    # label_end_ts de kilitli doneme tasmamali (etiket ufku ileri bakar)
    assert_pre_holdout(out["label_end_ts"].dropna(), "aday tablosu label_end_ts")
    assert_pre_holdout(out["exit_ts"].dropna(), "aday tablosu exit_ts")
    out["taken"] = out["taken"].astype(bool)
    if out.loc[out["taken"], "exit_ts"].isna().any():
        raise SchemaError("alinan satirlarda exit_ts zorunlu")
    if (out["exit_ts"] < out["ts"]).any():
        raise SchemaError("exit_ts < ts")
    if not out["side"].isin(["long", "short"]).all():
        raise SchemaError("side yalniz long/short")
    if not out["setup"].isin(["T1", "R1"]).all():
        raise SchemaError("setup yalniz T1/R1")
    bad_src = set(out["source"]) - set(SOURCE_WEIGHTS)
    if bad_src:
        raise SchemaError(f"bilinmeyen source: {bad_src}")
    long = out["side"].eq("long")
    ok = np.where(long, out["planned_stop"] < out["planned_entry"], out["planned_stop"] > out["planned_entry"])
    if not ok.all():
        raise SchemaError("planned_stop yone gore entry'nin dogru tarafinda degil")
    if out.duplicated(["pair", "ts", "side"]).any():
        raise SchemaError("(pair, ts, side) tekrarli")
    if not out["label"].dropna().isin([0, 1]).all():
        raise SchemaError("label 0/1/NaN olmali")
    for c in ("net_r", "cost_r"):
        if out.loc[out["label"].notna(), c].isna().any():
            raise SchemaError(f"cozulmus satirlarda {c} NaN")
    out["taken"] = out["taken"].astype(bool)
    return out.sort_values(["ts", "pair", "side"], kind="mergesort").reset_index(drop=True)


def load_candidates(path: str | Path) -> pd.DataFrame:
    """19b ciktisini (parquet/csv) okur, dogrular, zamana gore siralar. Kilitli donem satiri
    varsa HoldoutViolation (sessizce atilmaz)."""
    p = Path(path)
    if p.suffix == ".parquet":
        df = pd.read_parquet(p)
    elif p.suffix == ".csv":
        df = pd.read_csv(p)
    else:
        raise SchemaError(f"desteklenmeyen uzanti: {p.suffix}")
    return validate_candidates(df)
