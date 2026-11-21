"""Rejim etiketi yayini gerceklestirme testleri (docs/standart/rejim-yayini-spec.md).

Sentetik market.sqlite (store.py semasi, user_version=1) ve sentetik 4h mumlar. Ag yok.
"""
from __future__ import annotations

import json
import math
import os
import re
import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from trader_core import rejim_yayini as ry

ROOT = Path(__file__).resolve().parents[2]
WORKER = ROOT / "deploy" / "panel_worker.js"
H4 = 14_400_000
GUN = 86_400_000
T0 = int(datetime(2026, 9, 1, tzinfo=timezone.utc).timestamp() * 1000)   # 4h ve gun sinirina hizali

SCHEMA = """
CREATE TABLE bars(
  kind TEXT NOT NULL, pair TEXT NOT NULL, tf TEXT NOT NULL, open_ms INTEGER NOT NULL,
  o REAL NOT NULL, h REAL NOT NULL, l REAL NOT NULL, c REAL NOT NULL, v REAL NOT NULL DEFAULT 0,
  written_ms INTEGER NOT NULL, PRIMARY KEY(kind, pair, tf, open_ms)) WITHOUT ROWID;
"""


def _mum_seti(n: int, *, baslangic: float = 100.0, egim: float = 0.5, t0: int = T0, dalga: float = 0.0):
    """Yumusak trend + kucuk salinim; gecerli OHLC."""
    out = []
    for i in range(n):
        base = baslangic + egim * i + dalga * math.sin(i / 3.0)
        o = base
        c = base + egim * 0.6
        h = max(o, c) + 0.4
        l = min(o, c) - 0.4
        out.append((t0 + i * H4, o, h, l, c, 1000.0 + i))
    return out


def _db(path: Path, pairs: dict[str, list[tuple]]) -> Path:
    con = sqlite3.connect(path)
    con.executescript(SCHEMA)
    con.execute("PRAGMA user_version=1")
    for pair, rows in pairs.items():
        con.executemany(
            "INSERT INTO bars(kind,pair,tf,open_ms,o,h,l,c,v,written_ms) VALUES('last',?,'4h',?,?,?,?,?,?,0)",
            [(pair, *r) for r in rows])
    con.commit()
    con.close()
    return path


def _now_after(rows: list[tuple]) -> datetime:
    son_kapali_bitis = rows[-1][0] + H4
    return datetime.fromtimestamp((son_kapali_bitis + 1000) / 1000, tz=timezone.utc)


@pytest.fixture
def store(tmp_path):
    rows = _mum_seti(300)
    db = _db(tmp_path / "market.sqlite", {"BTC/USDT": rows})
    s = ry.MarketReader(db)
    yield s, rows
    s.close()


# ------------------------------------------------------------------ JSON bicimi
def test_json_shape_and_labels(tmp_path):
    rows = _mum_seti(300)
    db = _db(tmp_path / "m.sqlite", {"BTC/USDT": rows, "1000SHIB/USDT": rows})
    s = ry.MarketReader(db)
    try:
        now = _now_after(rows)
        doc = ry.uret(s, ["BTC/USDT", "1000SHIB/USDT"], {"hisse": [], "metal": ["XAU/USDT"]}, now)
    finally:
        s.close()
    assert doc["surum"] == 1 and doc["kaynak"] == "ML" and doc["gecerlilik_dk"] == 90
    assert doc["rejimler"] == ["trend_up", "trend_down", "range", "volatile", "unclear"]
    assert re.fullmatch(r"\d{4}-\d\d-\d\dT\d\d:\d\d:\d\dZ", doc["uretim_ts"])
    btc = doc["varliklar"]["BTC/USDT"]
    assert btc["baz"] == "BTC" and btc["varlik_sinifi"] == "kripto"
    assert set(btc) == {"baz", "varlik_sinifi", "4h", "1d"}
    assert set(btc["4h"]) == {"rejim", "bar_ts"}
    assert btc["4h"]["rejim"] in doc["rejimler"]
    assert btc["4h"]["rejim"] == "trend_up"
    # son kapanmis 4h mum: son satirin acilisi
    assert btc["4h"]["bar_ts"] == ry._iso_z(rows[-1][0])
    assert doc["varliklar"]["1000SHIB/USDT"]["baz"] == "1000SHIB"
    # belge JSON'a donusturulebilir ve ayni yapiyi korur
    assert json.loads(json.dumps(doc)) == doc


def test_bar_ts_is_last_closed_bar_not_partial(tmp_path):
    rows = _mum_seti(300)
    db = _db(tmp_path / "m.sqlite", {"BTC/USDT": rows})
    s = ry.MarketReader(db)
    try:
        # simdi son mumun ortasi: son mum henuz kapanmadi, bar_ts bir onceki mum olmali
        now = datetime.fromtimestamp((rows[-1][0] + H4 // 2) / 1000, tz=timezone.utc)
        doc = ry.uret(s, ["BTC/USDT"], {}, now)
    finally:
        s.close()
    assert doc["varliklar"]["BTC/USDT"]["4h"]["bar_ts"] == ry._iso_z(rows[-2][0])


def test_asset_class_rule():
    clusters = {"kripto_buyuk": ["BTC/USDT"], "hisse": ["NVDA/USDT"], "metal": ["XAU/USDT"],
                "enerji_sanayi": ["BZ/USDT"]}
    assert ry.asset_class("BTC/USDT", clusters) == "kripto"
    assert ry.asset_class("NVDA/USDT", clusters) == "hisse"
    assert ry.asset_class("XAU/USDT", clusters) == "emtia"
    assert ry.asset_class("BZ/USDT", clusters) == "emtia"
    assert ry.asset_class("UNKNOWN/USDT", clusters) == "kripto"


# ------------------------------------------------------------------ 1d birlestirme
def test_daily_aggregation_six_bars_per_utc_day():
    # 2 tam gun (6+6 bar) + bir eksik gun (3 bar): eksik gun atlanmali
    tam1 = [(T0 + i * H4, 10 + i, 20 + i, 5 + i, 11 + i, 100.0) for i in range(6)]
    eksik = [(T0 + GUN + i * H4, 1.0, 2.0, 0.5, 1.5, 10.0) for i in range(3)]
    tam2 = [(T0 + 2 * GUN + i * H4, 30 + i, 40 + i, 25 + i, 31 + i, 50.0) for i in range(6)]
    mumlar = [ry.Mum(*r) for r in tam1 + eksik + tam2]
    gunler = ry.gunluk_mumlar(mumlar)
    assert [g.open_ms for g in gunler] == [T0, T0 + 2 * GUN]
    g = gunler[0]
    assert g.o == 10          # ilk 4h'in acilisi
    assert g.h == 20 + 5     # en yuksek high
    assert g.l == 5          # en dusuk low
    assert g.c == 11 + 5     # son 4h'in kapanisi
    assert g.v == pytest.approx(600.0)
    assert gunler[1].o == 30 and gunler[1].c == 36


def test_daily_skips_incomplete_day_with_gap_inside():
    tam = [(T0 + i * H4, 10.0, 12.0, 9.0, 11.0, 1.0) for i in range(6)]
    delikli = tam[:2] + tam[3:]           # 5 bar: bir 4h eksik
    assert ry.gunluk_mumlar([ry.Mum(*r) for r in delikli]) == []


def test_uret_daily_uses_aggregated_bars(tmp_path):
    rows = _mum_seti(6 * 150)              # 150 gun, tam gunler
    db = _db(tmp_path / "m.sqlite", {"ETH/USDT": rows})
    s = ry.MarketReader(db)
    try:
        doc = ry.uret(s, ["ETH/USDT"], {}, _now_after(rows))
    finally:
        s.close()
    d1 = doc["varliklar"]["ETH/USDT"]["1d"]
    assert d1["rejim"] in doc["rejimler"]
    # 1d bar_ts gun sinirina hizali ve son TAM gunun acilisi olmali (son 4h kapanisi gun sonuna denk degil)
    assert d1["bar_ts"] is not None and d1["bar_ts"].endswith("T00:00:00Z")
    son_tam_gun_ms = ((rows[-1][0] + H4) // GUN) * GUN - GUN
    assert d1["bar_ts"] == ry._iso_z(son_tam_gun_ms)


# ------------------------------------------------------------------ eksik veri
def test_missing_pair_is_unclear_with_null_ts(store):
    s, _ = store
    doc = ry.uret(s, ["XRP/USDT"], {}, datetime(2026, 11, 19, 12, tzinfo=timezone.utc))
    x = doc["varliklar"]["XRP/USDT"]
    assert x["4h"] == {"rejim": "unclear", "bar_ts": None}
    assert x["1d"] == {"rejim": "unclear", "bar_ts": None}
    assert x["baz"] == "XRP"


def test_insufficient_bars_is_unclear(tmp_path):
    n = ry.MIN_BARS - 1
    rows = _mum_seti(n)
    db = _db(tmp_path / "m.sqlite", {"SOL/USDT": rows})
    s = ry.MarketReader(db)
    try:
        doc = ry.uret(s, ["SOL/USDT"], {}, _now_after(rows))
    finally:
        s.close()
    assert doc["varliklar"]["SOL/USDT"]["4h"] == {"rejim": "unclear", "bar_ts": None}


def test_missing_db_raises(tmp_path):
    with pytest.raises(FileNotFoundError):
        ry.MarketReader(tmp_path / "yok.sqlite")


def test_wrong_schema_version_rejected(tmp_path):
    db = _db(tmp_path / "m.sqlite", {})
    con = sqlite3.connect(db)
    con.execute("PRAGMA user_version=7")
    con.commit()
    con.close()
    with pytest.raises(ValueError):
        ry.MarketReader(db)


def test_read_only_store_cannot_write(tmp_path):
    db = _db(tmp_path / "m.sqlite", {"BTC/USDT": _mum_seti(3)})
    s = ry.MarketReader(db)
    try:
        with pytest.raises(sqlite3.OperationalError):
            s._db.execute("DELETE FROM bars")
    finally:
        s.close()


# ------------------------------------------------------------------ atomik yazma
def test_atomic_write_replaces_whole_file(tmp_path):
    out = tmp_path / "site" / "rejim.json"
    ry.atomik_yaz(out, {"surum": 1, "a": 1})
    assert json.loads(out.read_text(encoding="utf-8")) == {"surum": 1, "a": 1}
    ry.atomik_yaz(out, {"surum": 1, "a": 2})
    assert json.loads(out.read_text(encoding="utf-8"))["a"] == 2
    assert sorted(p.name for p in out.parent.iterdir()) == ["rejim.json"]


def test_atomic_write_failure_keeps_old_file(tmp_path, monkeypatch):
    out = tmp_path / "rejim.json"
    ry.atomik_yaz(out, {"surum": 1, "eski": True})
    before = out.read_bytes()

    def boom(*_a, **_k):
        raise OSError("disk dolu (test)")

    monkeypatch.setattr(ry.os, "replace", boom)
    with pytest.raises(OSError):
        ry.atomik_yaz(out, {"surum": 1, "yeni": True})
    assert out.read_bytes() == before
    assert sorted(p.name for p in tmp_path.iterdir()) == ["rejim.json"]   # gecici dosya temizlendi


def test_atomic_write_failure_creates_no_file(tmp_path):
    out = tmp_path / "rejim.json"

    class Bozuk:
        pass

    with pytest.raises(TypeError):
        ry.atomik_yaz(out, {"x": Bozuk()})     # json.dump hatasi
    assert not out.exists()
    assert list(tmp_path.iterdir()) == []


# ------------------------------------------------------------------ CLI
def _cli_setup(tmp_path: Path, rows: list[tuple]) -> tuple[Path, Path]:
    kok = tmp_path / "trader"
    cfg = kok / "config"
    cfg.mkdir(parents=True)
    (cfg / "engine.base.json").write_text(json.dumps({
        "pairs": ["BTC/USDT"], "market_db": "var/market.sqlite"}), encoding="utf-8")
    (cfg / "engine.learner.json").write_text(json.dumps({"bot": "learner"}), encoding="utf-8")
    (cfg / "engine.paper.json").write_text(json.dumps({
        "pairs": ["BTC/USDT", "NVDA/USDT"], "optional_pairs": ["NVDA/USDT"],
        "clusters": {"hisse": {"pairs": ["NVDA/USDT"], "max_positions": 2}}}), encoding="utf-8")
    (kok / "var").mkdir()
    db = _db(kok / "var" / "market.sqlite", {"BTC/USDT": rows})
    return cfg, db


def test_cli_end_to_end(tmp_path):
    rows = _mum_seti(300)
    cfg, _db_path = _cli_setup(tmp_path, rows)
    out = tmp_path / "out" / "rejim.json"
    rc = ry.main(["--config-dir", str(cfg), "--env", "paper", "--out", str(out)])
    assert rc == 0
    doc = json.loads(out.read_text(encoding="utf-8"))
    assert set(doc["varliklar"]) == {"BTC/USDT", "NVDA/USDT"}          # paper overlay pairs + optional
    assert doc["varliklar"]["NVDA/USDT"]["varlik_sinifi"] == "hisse"
    assert doc["varliklar"]["NVDA/USDT"]["4h"]["rejim"] == "unclear"  # mum yok
    assert doc["varliklar"]["BTC/USDT"]["varlik_sinifi"] == "kripto"


def test_cli_failure_exits_nonzero_and_writes_nothing(tmp_path):
    cfg = tmp_path / "config"
    cfg.mkdir()
    (cfg / "engine.base.json").write_text(json.dumps({"pairs": ["BTC/USDT"]}), encoding="utf-8")
    out = tmp_path / "rejim.json"
    rc = ry.main(["--config-dir", str(cfg), "--env", "paper", "--out", str(out)])   # market.sqlite yok
    assert rc == 1
    assert not out.exists()


def test_cli_db_override_relative_path_resolved_from_config_root(tmp_path):
    rows = _mum_seti(10)
    cfg, db = _cli_setup(tmp_path, rows)
    pairs, clusters, db_yolu = ry.yapilandirma_oku(cfg, "paper")
    assert db_yolu == db
    assert pairs[0] == "BTC/USDT" and "NVDA/USDT" in pairs
    assert clusters == {"hisse": ["NVDA/USDT"]}
    assert os.path.isabs(db_yolu)


# ------------------------------------------------------------------ worker (node'suz statik test)
def test_worker_rejim_branch_before_auth_and_get_head_only():
    t = WORKER.read_text(encoding="utf-8")
    assert '"/rejim.json"' in t
    assert '"GET"' in t and '"HEAD"' in t
    branch = t.index('pathname === "/rejim.json"')
    auth = t.index("if (!saltOkuma(istek))")
    assert branch < auth, "rejim dali kimlik kontrolunden once olmali"
    # dal, yalniz GET/HEAD kosulu icinde; istek ASSETS'ten okunur
    kosul = t[t.rfind("if (", 0, branch):branch]
    assert '"GET"' in kosul and '"HEAD"' in kosul
    govde = t[branch:auth]
    assert "env.ASSETS.fetch(istek)" in govde
    assert '"Content-Type", "application/json"' in govde
    assert '"Cache-Control", "no-store"' in govde
    assert '"Access-Control-Allow-Origin", "*"' in govde
    assert "return baslikEkle(new Response(" in govde
