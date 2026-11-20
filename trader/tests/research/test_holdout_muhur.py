"""research/holdout_muhur.py: yalniz sentetik feather dosyalari (tmp_path); gercek veri okunmaz."""
from __future__ import annotations

import importlib.util
import json
from datetime import timedelta
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from trader_engine.holdout import HOLDOUT

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location("holdout_muhur", ROOT / "research" / "holdout_muhur.py")
M = importlib.util.module_from_spec(spec)
spec.loader.exec_module(M)


def _write(d: Path, name: str, seed: int, funding: bool = False) -> Path:
    start = pd.Timestamp(HOLDOUT[0]) - timedelta(days=5)
    ts = pd.date_range(start, periods=24 * 12, freq="1h", tz="UTC")           # holdout oncesi + icinde
    rng = np.random.default_rng(seed)
    df = pd.DataFrame({"date": ts})
    if funding:
        df["funding_rate"] = rng.normal(0, 1e-4, len(ts))
    else:
        c = 100 + rng.normal(0, 1, len(ts)).cumsum()
        df["open"], df["high"], df["low"], df["close"], df["volume"] = c, c + 1, c - 1, c + 0.5, rng.uniform(1, 9, len(ts))
    p = d / name
    df.to_feather(p)
    return p


@pytest.fixture()
def hist(tmp_path):
    d = tmp_path / "hist"
    d.mkdir()
    _write(d, "AAA-1h-futures.feather", 1)
    _write(d, "BBB-1h-futures.feather", 2)
    _write(d, "AAA-1h-funding_rate.feather", 3, funding=True)
    return d


def test_seal_once_and_refuse_second(hist, tmp_path):
    out = tmp_path / "out" / "muhur.json"
    doc = M.muhurle(hist, out)
    assert doc["acildi"] is False and doc["dosya_sayisi"] == 3 and out.exists()
    assert doc["holdout"] == {"baslangic": HOLDOUT[0].strftime("%Y-%m-%d"), "bitis": HOLDOUT[1].strftime("%Y-%m-%d")}
    f = doc["dosyalar"][0]
    assert set(f) == {"dosya", "satir", "ilk_ts", "son_ts", "sha256"}
    assert f["satir"] > 0
    assert f["ilk_ts"].startswith(HOLDOUT[0].strftime("%Y-%m-%d"))
    before = out.read_text()
    with pytest.raises(M.MuhurError):
        M.muhurle(hist, out)
    assert out.read_text() == before


def test_slice_only_holdout_rows(hist, tmp_path):
    doc = M.muhurle(hist, tmp_path / "m.json")
    start = pd.Timestamp(HOLDOUT[0])
    expected = 24 * 12 - 24 * 5                  # bes gun holdout oncesi
    assert all(f["satir"] == expected for f in doc["dosyalar"])
    assert all(pd.Timestamp(f["ilk_ts"]) >= start for f in doc["dosyalar"])


def test_verify_equal_and_detects_change(hist, tmp_path):
    out = tmp_path / "m.json"
    M.muhurle(hist, out)
    ok, diff = M.dogrula(hist, out)
    assert ok and diff == []
    # holdout disi satir degisimi muhuru bozmaz
    p = hist / "AAA-1h-futures.feather"
    df = pd.read_feather(p)
    df.loc[0, "close"] += 1.0
    df.to_feather(p)
    assert M.dogrula(hist, out) == (True, [])
    # holdout satiri degisimi yakalanir
    df = pd.read_feather(p)
    df.loc[len(df) - 1, "close"] += 1e-6
    df.to_feather(p)
    ok, diff = M.dogrula(hist, out)
    assert not ok and diff == ["AAA-1h-futures.feather"]
    # silinen / eklenen dosya da farkli
    (hist / "BBB-1h-futures.feather").unlink()
    _write(hist, "CCC-1h-futures.feather", 9)
    ok, diff = M.dogrula(hist, out)
    assert not ok and {"BBB-1h-futures.feather", "CCC-1h-futures.feather"} <= set(diff)


def test_dogrula_without_seal_refuses(hist, tmp_path):
    with pytest.raises(M.MuhurError):
        M.dogrula(hist, tmp_path / "yok.json")


def test_ac_only_once(hist, tmp_path):
    out = tmp_path / "m.json"
    sealed = M.muhurle(hist, out)
    with pytest.raises(M.MuhurError):
        M.ac("", "x", out)
    d = M.ac("aday-1", "yayina hazir", out)
    assert d["acildi"] is True
    assert d["acilis"]["aday_kumesi"] == "aday-1" and d["acilis"]["gerekce"] == "yayina hazir"
    assert d["acilis"]["birlesik_sha256"] == sealed["birlesik_sha256"]
    assert json.loads(out.read_text())["acildi"] is True
    with pytest.raises(M.MuhurError):
        M.ac("aday-2", "yine", out)
    assert json.loads(out.read_text())["acilis"]["aday_kumesi"] == "aday-1"


def test_ac_without_seal_refuses(tmp_path):
    with pytest.raises(M.MuhurError):
        M.ac("a", "b", tmp_path / "yok.json")


def test_cli_prints_no_content_values(hist, tmp_path, capsys):
    out = tmp_path / "m.json"
    assert M.main(["muhurle", "--history-dir", str(hist), "--muhur", str(out)]) == 0
    assert M.main(["dogrula", "--history-dir", str(hist), "--muhur", str(out)]) == 0
    assert M.main(["muhurle", "--history-dir", str(hist), "--muhur", str(out)]) == 2
    assert M.main(["ac", "--aday-kumesi", "a", "--gerekce", "b", "--muhur", str(out)]) == 0
    assert M.main(["ac", "--aday-kumesi", "a", "--gerekce", "b", "--muhur", str(out)]) == 2
    cap = capsys.readouterr()
    text = cap.out + cap.err
    df = pd.read_feather(hist / "AAA-1h-futures.feather")
    for v in df["close"].iloc[-5:]:
        assert f"{v:.2f}" not in text
    assert "close" not in text and "volume" not in text


def test_json_has_only_permitted_fields(hist, tmp_path):
    doc = M.muhurle(hist, tmp_path / "m.json")
    assert set(doc) == {"muhur_tarihi", "holdout", "dosya_sayisi", "dosyalar", "birlesik_sha256", "acildi"}


def test_kayit_alani_istege_bagli_ve_dogrula_etkilenmez(hist, tmp_path):
    f = tmp_path / "ayar.json"
    f.write_text("{}")
    k = M.kayit_olustur(["s1"], [f], [f])
    out = tmp_path / "o" / "muhur.json"
    doc = M.muhurle(hist, out, kayit=k)
    assert doc["kayit"]["stratejiler"] == ["s1"]
    assert M.dogrula(hist, out) == (True, [])
    out2 = tmp_path / "o2" / "muhur.json"
    assert "kayit" not in M.muhurle(hist, out2)


def test_on_kayit_zinciri_ve_kod_degisimi(tmp_path):
    f = tmp_path / "kod.py"
    f.write_text("x=1")
    g = tmp_path / "g.jsonl"
    M.on_kayit_yaz(M.kayit_olustur(["a"], [f], [f]), g)
    M.on_kayit_yaz(M.kayit_olustur(["a", "b"], [f], [f]), g)
    assert M.gunluk_dogrula(g) == []
    assert M.kayit_dogrula(M.gunluk_oku(g)[-1]["kayit"]) == []
    f.write_text("x=2")
    assert any("degismis" in x for x in M.kayit_dogrula(M.gunluk_oku(g)[-1]["kayit"]))
    satirlar = g.read_text().splitlines()
    g.write_text(satirlar[0].replace('"a"', '"z"') + "\n" + satirlar[1] + "\n")
    assert M.gunluk_dogrula(g)


def test_bos_strateji_reddedilir(tmp_path):
    f = tmp_path / "k.py"
    f.write_text("")
    with pytest.raises(M.MuhurError):
        M.kayit_olustur([], [f], [f])
