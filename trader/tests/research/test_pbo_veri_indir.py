"""research/pbo_veri_indir.py: sentetik zip/CSV (ag yok, tmp_path); gercek veri okunmaz/yazilmaz."""
from __future__ import annotations

import hashlib
import importlib.util
import io
import zipfile
from pathlib import Path

import pandas as pd
import pytest

from trader_engine.holdout import HOLDOUT

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location("pbo_veri_indir", ROOT / "research" / "pbo_veri_indir.py")
D = importlib.util.module_from_spec(spec)
spec.loader.exec_module(D)
spec2 = importlib.util.spec_from_file_location("arm_harness_v", ROOT / "research" / "arm_harness.py")
H = importlib.util.module_from_spec(spec2)
spec2.loader.exec_module(H)


def _zip(rows: list[tuple], header: bool) -> bytes:
    lines = ["open_time,open,high,low,close,volume,close_time,qv,n,tb,tq,ignore"] if header else []
    for ms, px in rows:
        lines.append(f"{ms},{px},{px + 1},{px - 1},{px + 0.5},10,{ms + 1},1,1,1,1,0")
    b = io.BytesIO()
    with zipfile.ZipFile(b, "w") as z:
        z.writestr("x.csv", "\n".join(lines) + "\n")
    return b.getvalue()


class _Resp:
    def __init__(self, code, content=b""):
        self.status_code, self.content = code, content


class _Sess:
    def __init__(self, files):
        self.files = files

    def get(self, url, timeout=0):
        return self.files.get(url, _Resp(404))


def test_months_stop_before_holdout_and_symbol_mapping():
    ms = D.months()
    assert ms[-1] == "2026-04" and (HOLDOUT[0].year, HOLDOUT[0].month) > tuple(map(int, ms[-1].split("-")))
    assert D.symbol("1000SHIB/USDT") == "1000SHIBUSDT" and D.stem("NVDA/USDT") == "NVDA_USDT_USDT"


@pytest.mark.parametrize("header", [True, False])
def test_fetch_month_parses_and_checks_sha(header):
    z = _zip([(1609459200000, 10.0), (1609462800000, 11.0)], header)
    url = f"{D.BASE}/AAAUSDT/1h/AAAUSDT-1h-2021-01.zip"
    ok = _Sess({url: _Resp(200, z), url + ".CHECKSUM": _Resp(200, f"{hashlib.sha256(z).hexdigest()}  f.zip".encode())})
    df = D.fetch_month(ok, "AAAUSDT", "1h", "2021-01")
    assert list(df.columns) == D.COLS and len(df) == 2 and df["open"].iloc[1] == 11.0
    bad = _Sess({url: _Resp(200, z), url + ".CHECKSUM": _Resp(200, b"0" * 64 + b"  f.zip")})
    with pytest.raises(RuntimeError):
        D.fetch_month(bad, "AAAUSDT", "1h", "2021-01")
    assert D.fetch_month(_Sess({}), "AAAUSDT", "1h", "2021-01") is None


def test_build_one_never_writes_holdout_rows(tmp_path, monkeypatch):
    cut_ms = int(pd.Timestamp(HOLDOUT[0]).timestamp() * 1000)
    day = 86_400_000
    df = pd.DataFrame({"open_time": [cut_ms - 2 * day, cut_ms - day, cut_ms, cut_ms + day], "open": 1.0, "high": 2.0, "low": 0.5, "close": 1.5, "volume": 3.0})
    monkeypatch.setattr(D, "OUT", tmp_path)
    monkeypatch.setattr(D, "months", lambda: ["2026-04"])
    monkeypatch.setattr(D, "fetch_month", lambda s, sym, tf, ym: df)
    r = D.build_one(("ZZZ/USDT", "1d"))
    out = pd.read_feather(tmp_path / "ZZZ_USDT_USDT-1d-futures.feather")
    assert r["n"] == 2 and len(out) == 2 and out["date"].max() < pd.Timestamp(HOLDOUT[0])
    assert str(out["date"].dtype) == "datetime64[ms, UTC]" and out["open"].dtype == "float64"
    monkeypatch.setattr(D, "fetch_month", lambda s, sym, tf, ym: None)
    assert D.build_one(("NONE/USDT", "1d"))["n"] == 0
    assert not (tmp_path / "NONE_USDT_USDT-1d-futures.feather").exists()


def test_harness_falls_back_to_pre_dir(tmp_path, monkeypatch):
    hist, pre = tmp_path / "hist", tmp_path / "pre"
    hist.mkdir(), pre.mkdir()
    idx = pd.date_range("2022-01-01", periods=10, freq="4h", tz="UTC").as_unit("ms")
    pd.DataFrame({"date": idx, "open": 1.0, "high": 2.0, "low": 0.5, "close": 1.5, "volume": 1.0}).to_feather(pre / "QQQ_USDT_USDT-4h-futures.feather")
    monkeypatch.setattr(H, "HISTORY", hist)
    monkeypatch.setattr(H, "HISTORY_PRE", pre)
    have, missing = H.available_pairs(hist, ["QQQ/USDT", "NOPE/USDT"])
    assert have == ["QQQ/USDT"] and missing == ["NOPE/USDT"]
    assert len(H.load_pre_holdout(hist, "QQQ/USDT", "4h")) == 10
    assert H.load_pre_holdout(hist, "NOPE/USDT", "4h") is None
