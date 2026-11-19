"""Rejim etiketi yayini (belirtim: docs/standart/rejim-yayini-spec.md, Faz 1).

ML Otonom her enstrumanin piyasa rejimini salt-okunur bir JSON olarak uretir. Bu modul yalniz etiket/kayit uretir;
hicbir islemi engellemez, motora ya da kapilara dokunmaz.

Katman: trader_core, trader_engine'i ICE AKTARMAZ. Market deposu (var/market.sqlite) bu modulde stdlib sqlite3 ile
salt okunur acilir ve `bars` tablosu store.py semasiyla birebir okunur. Asset sinifi kurali ve yapilandirma okuma
(pairs / optional_pairs / clusters / market_db) trader_engine'deki karsiliklarinin kopyasidir.

Donuk modul trader_core.regime yalniz iceri aktarilir (classify_series, DEFAULT_PARAMS); kurallarina dokunulmaz.

CLI: python -m trader_core.rejim_yayini --config-dir config --env paper --out <yol>
"""
from __future__ import annotations

import argparse
import json
import os
import sqlite3
import sys
import tempfile
from collections.abc import Iterable, Mapping, Sequence
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, NamedTuple

import pandas as pd

from trader_core.regime import DEFAULT_PARAMS, MIN_BARS, Regime, classify_series

SURUM = 1
KAYNAK = "ML"
GECERLILIK_DK = 90
REJIMLER = tuple(r.value for r in Regime)
UNCLEAR = Regime.UNCLEAR.value

# store.py ile ayni sema ve sabitler
STORE_SCHEMA_VERSION = 1
TF_MS = {"1m": 60_000, "15m": 900_000, "1h": 3_600_000, "4h": 14_400_000}
GUN_MS = 86_400_000
GUNLUK_4H_SAYISI = GUN_MS // TF_MS["4h"]          # 6
ISTENEN_4H_MUM = 800                               # >= 200 (belirtim) ve 1d icin >= MIN_BARS gun (133 gun)

# arm_guard.py ile ayni kume kurali
EQUITY_CLUSTER = "hisse"
COMMODITY_CLUSTERS = ("metal", "enerji_sanayi")
CLASS_CRYPTO, CLASS_EQUITY, CLASS_COMMODITY = "kripto", "hisse", "emtia"


class Mum(NamedTuple):
    open_ms: int
    o: float
    h: float
    l: float
    c: float
    v: float


# ----------------------------------------------------------------- zaman yardimcilari
def _iso_z(ms: int) -> str:
    return datetime.fromtimestamp(ms / 1000, tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _floor(ms: int, step: int) -> int:
    return (ms // step) * step


# ----------------------------------------------------------------- salt okunur market deposu
class MarketReader:
    """store.MarketStore(read_only=True) ile ayni `query_bars` sozlesmesi; yalniz okuma."""

    def __init__(self, path: str | os.PathLike[str]) -> None:
        p = Path(path)
        if not p.exists():
            raise FileNotFoundError(f"market.sqlite yok: {p}")
        uri = p.resolve().as_uri() + "?mode=ro"
        self._db = sqlite3.connect(uri, uri=True, isolation_level=None, timeout=5.0)
        try:
            self._db.execute("PRAGMA busy_timeout=5000")
            ver = self._db.execute("PRAGMA user_version").fetchone()[0]
            if ver != STORE_SCHEMA_VERSION:
                raise ValueError(f"market.sqlite user_version={ver}, beklenen {STORE_SCHEMA_VERSION}")
        except Exception:
            self._db.close()
            raise

    def close(self) -> None:
        self._db.close()

    def query_bars(self, kind: str, pair: str, tf: str, until_ms: int, n: int | None) -> list[Mum]:
        """Kapanmis mumlar: open_ms + tf_ms <= until_ms; en yeni n tane, zamana gore artan sirada."""
        tf_ms = TF_MS.get(tf)
        if tf_ms is None:
            raise ValueError(f"bilinmeyen tf: {tf!r}")
        sql = ("SELECT open_ms,o,h,l,c,v FROM bars WHERE kind=? AND pair=? AND tf=? AND open_ms<=? "
               "ORDER BY open_ms DESC")
        args: tuple[Any, ...] = (kind, pair, tf, until_ms - tf_ms)
        if n is not None:
            if n <= 0:
                return []
            sql += " LIMIT ?"
            args += (int(n),)
        rows = self._db.execute(sql, args).fetchall()
        rows.reverse()
        return [Mum(*r) for r in rows]


# ----------------------------------------------------------------- saf hesaplama
def asset_class(pair: str, clusters: Mapping[str, Iterable[str]]) -> str:
    """arm_guard.asset_class kopyasi: kume adlarindan kripto | hisse | emtia; aksi kripto."""
    for name, members in clusters.items():
        if pair not in members:
            continue
        if name == EQUITY_CLUSTER:
            return CLASS_EQUITY
        if name in COMMODITY_CLUSTERS:
            return CLASS_COMMODITY
    return CLASS_CRYPTO


def gunluk_mumlar(mumlar: Sequence[Mum]) -> list[Mum]:
    """4h mumlardan UTC gun sinirinda 1d mumlar. Yalniz 6 x 4h tam olan gunler uretilir; eksik gun atlanir."""
    gunler: dict[int, list[Mum]] = {}
    for m in mumlar:
        gunler.setdefault(_floor(m.open_ms, GUN_MS), []).append(m)
    out: list[Mum] = []
    for gun in sorted(gunler):
        parcalar = sorted(gunler[gun], key=lambda m: m.open_ms)
        ofsetler = {(m.open_ms - gun) // TF_MS["4h"] for m in parcalar}
        if len(parcalar) != GUNLUK_4H_SAYISI or ofsetler != set(range(GUNLUK_4H_SAYISI)):
            continue
        out.append(Mum(
            gun,
            parcalar[0].o,
            max(m.h for m in parcalar),
            min(m.l for m in parcalar),
            parcalar[-1].c,
            sum(m.v for m in parcalar),
        ))
    return out


def _sinifla(mumlar: Sequence[Mum]) -> tuple[str, str | None]:
    """Son kapanmis mumun rejimi ve acilis zamani. Yetersiz veri / hata -> ('unclear', None)."""
    if len(mumlar) < MIN_BARS:
        return UNCLEAR, None
    df = pd.DataFrame(
        {
            "open": [m.o for m in mumlar],
            "high": [m.h for m in mumlar],
            "low": [m.l for m in mumlar],
            "close": [m.c for m in mumlar],
        },
        index=pd.Index([m.open_ms for m in mumlar], dtype="int64"),
    )
    try:
        res = classify_series(df, DEFAULT_PARAMS)
        etiket = str(res["regime"].iloc[-1])
    except (ValueError, ArithmeticError, KeyError, IndexError):
        return UNCLEAR, None
    if etiket not in REJIMLER:
        return UNCLEAR, None
    return etiket, _iso_z(mumlar[-1].open_ms)


def _zaman_dilimi(mumlar: Sequence[Mum]) -> dict[str, Any]:
    rejim, bar_ts = _sinifla(mumlar)
    return {"rejim": rejim, "bar_ts": bar_ts}


def uret(store: Any, pairs: Iterable[str], clusters: Mapping[str, Iterable[str]], now: datetime) -> dict[str, Any]:
    """Rejim belgesini dondurur (saf; ag yok, dosya yok). `store.query_bars(kind, pair, tf, until_ms, n)` kullanir.

    `now` UTC farkindalikli olmali. Her cift icin 4h ve 1d alanlari; veri yoksa ya da yetersizse rejim 'unclear',
    bar_ts null.
    """
    if now.tzinfo is None or now.utcoffset() is None:
        raise ValueError("now UTC farkindalikli olmali")
    now_utc = now.astimezone(timezone.utc)
    now_ms = int(now_utc.timestamp() * 1000)
    until_4h = _floor(now_ms, TF_MS["4h"])
    kume = {name: list(members) for name, members in clusters.items()}

    varliklar: dict[str, Any] = {}
    for pair in dict.fromkeys(pairs):          # sira korunur, tekrar yok
        if not isinstance(pair, str) or "/" not in pair:
            raise ValueError(f"cift bicimi gecersiz: {pair!r}")
        mumlar_4h = list(store.query_bars("last", pair, "4h", until_4h, ISTENEN_4H_MUM))
        varliklar[pair] = {
            "baz": pair.split("/", 1)[0],
            "varlik_sinifi": asset_class(pair, kume),
            "4h": _zaman_dilimi(mumlar_4h),
            "1d": _zaman_dilimi(gunluk_mumlar(mumlar_4h)),
        }

    return {
        "surum": SURUM,
        "kaynak": KAYNAK,
        "uretim_ts": _iso_z(now_ms),
        "gecerlilik_dk": GECERLILIK_DK,
        "rejimler": list(REJIMLER),
        "varliklar": varliklar,
    }


# ----------------------------------------------------------------- atomik yazma
def atomik_yaz(path: str | os.PathLike[str], doc: Mapping[str, Any]) -> None:
    """Belgeyi ayni dizinde gecici dosyaya yazar, fsync eder, os.replace ile yerine koyar. Hata olursa hedef degismez."""
    hedef = Path(path)
    hedef.parent.mkdir(parents=True, exist_ok=True)
    fd, gecici = tempfile.mkstemp(prefix=hedef.name + ".", suffix=".tmp", dir=str(hedef.parent))
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(doc, f, ensure_ascii=False, indent=2, sort_keys=False)
            f.write("\n")
            f.flush()
            os.fsync(f.fileno())
        os.replace(gecici, hedef)
    except BaseException:
        try:
            os.unlink(gecici)
        except FileNotFoundError:
            pass
        raise


# ----------------------------------------------------------------- yapilandirma (salt okuma)
def _yukle_json(p: Path) -> dict[str, Any]:
    with open(p, encoding="utf-8") as f:
        doc = json.load(f)
    if not isinstance(doc, dict):
        raise ValueError(f"{p}: JSON nesnesi bekleniyor")
    return doc


def yapilandirma_oku(config_dir: str | os.PathLike[str], env: str) -> tuple[list[str], dict[str, list[str]], Path]:
    """engine.base + engine.learner + engine.<env> (sig birlestirme) -> (pairs, clusters, market_db yolu).

    pairs = `pairs` + `optional_pairs` (tekrarsiz). clusters = {ad: pairs listesi}. market_db goreli ise config kokune
    gore cozulur (trader_engine.config.absolutize_paths ile ayni kural)."""
    d = Path(config_dir)
    cfg: dict[str, Any] = {}
    for ad in ("engine.base.json", "engine.learner.json", f"engine.{env}.json"):
        p = d / ad
        if p.exists():
            cfg.update(_yukle_json(p))
    pairs = list(cfg.get("pairs", [])) + list(cfg.get("optional_pairs", []))
    clusters_raw = cfg.get("clusters", {}) or {}
    clusters = {ad: list(spec.get("pairs", [])) for ad, spec in clusters_raw.items()}
    db = Path(cfg.get("market_db", "var/market.sqlite"))
    if not db.is_absolute():
        kok = d.parent if d.name == "config" else d
        db = kok / db
    return pairs, clusters, db


# ----------------------------------------------------------------- CLI
def main(argv: Sequence[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="python -m trader_core.rejim_yayini",
                                 description="ML rejim etiketlerini salt-okunur JSON olarak yayinlar.")
    ap.add_argument("--config-dir", default="config")
    ap.add_argument("--env", default="paper")
    ap.add_argument("--out", required=True, help="cikti JSON yolu (atomik yazilir)")
    ap.add_argument("--db", default=None, help="market.sqlite yolu (varsayilan: yapilandirmadaki market_db)")
    args = ap.parse_args(argv)
    try:
        pairs, clusters, db_varsayilan = yapilandirma_oku(args.config_dir, args.env)
        db = Path(args.db) if args.db else db_varsayilan
        store = MarketReader(db)
        try:
            doc = uret(store, pairs, clusters, datetime.now(timezone.utc))
        finally:
            store.close()
        atomik_yaz(args.out, doc)
    except Exception as e:  # noqa: BLE001 - CLI: her hata sifir olmayan cikis, dosya yazilmaz
        print(f"HATA: rejim yayini uretilemedi: {type(e).__name__}: {e}", file=sys.stderr)
        return 1
    print(f"rejim yayini yazildi: {args.out} ({len(doc['varliklar'])} varlik)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
