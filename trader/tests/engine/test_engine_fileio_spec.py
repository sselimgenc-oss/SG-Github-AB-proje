"""07 §4.4 test senaryoları (1l3a test_canli_durum karşılığı)."""
import json
import os
import threading
from datetime import datetime, timedelta, timezone

import pytest

from trader_engine import fileio as F

T0 = datetime(2026, 11, 16, 12, 0, 0, tzinfo=timezone.utc)


def test_no_tmp_left_and_content(tmp_path):
    p = F.atomic_write_json(tmp_path / "a" / "x.json", {"k": "ü"})
    assert json.loads(p.read_text(encoding="utf-8")) == {"k": "ü"} and p.read_text(encoding="utf-8").endswith("\n")
    assert [f.name for f in p.parent.iterdir()] == ["x.json"]
    F.atomic_write_jsonl(tmp_path / "r.jsonl", [{"a": 1}, {"b": 2}])
    assert (tmp_path / "r.jsonl").read_text().splitlines() == ['{"a": 1}', '{"b": 2}']


def test_failure_keeps_old_file_and_removes_tmp(tmp_path, monkeypatch):
    p = F.atomic_write_text(tmp_path / "x.txt", "old")

    def boom(*a, **k):
        raise OSError("disk")
    monkeypatch.setattr(os, "replace", boom)
    with pytest.raises(OSError):
        F.atomic_write_text(p, "new")
    monkeypatch.undo()
    assert p.read_text() == "old"
    assert [f.name for f in tmp_path.iterdir()] == ["x.txt"]


def test_nan_rejected_and_old_kept(tmp_path):
    p = F.atomic_write_json(tmp_path / "x.json", {"a": 1})
    with pytest.raises(ValueError):
        F.atomic_write_json(p, {"a": float("nan")})
    assert json.loads(p.read_text()) == {"a": 1}
    assert [f.name for f in tmp_path.iterdir()] == ["x.json"]


def test_reader_never_sees_partial(tmp_path):
    p = tmp_path / "x.json"
    F.atomic_write_json(p, {"n": 0, "pad": "x" * 5000})
    stop = threading.Event()
    errs = []

    def writer():
        i = 0
        while not stop.is_set():
            i += 1
            F.atomic_write_json(p, {"n": i, "pad": "x" * 5000})

    t = threading.Thread(target=writer)
    t.start()
    try:
        for _ in range(300):
            try:
                json.loads(p.read_text())
            except Exception as e:  # noqa: BLE001
                errs.append(e)
    finally:
        stop.set()
        t.join()
    assert not errs


def test_ts_roundtrip_and_naive_rejected():
    assert F.fmt_ts(T0) == "2026-11-16T12:00:00Z"
    assert F.parse_ts("2026-11-16T12:00:00Z") == T0
    assert F.fmt_ts(T0.astimezone(timezone(timedelta(hours=3)))) == "2026-11-16T12:00:00Z"
    with pytest.raises(ValueError):
        F.fmt_ts(datetime(2026, 11, 16, 12))


def test_heartbeat_roundtrip(tmp_path):
    assert F.heartbeat_read(tmp_path) is None
    F.heartbeat_write(tmp_path, T0, T0 - timedelta(minutes=5), prev="2026-11-16T11:00:00Z", stopped=True)
    v = F.heartbeat_read(tmp_path)
    assert v["schema"] == "engine/heartbeat/1" and v["interval_s"] == 60 and v["stopped"] is True
    assert v["ts"] == "2026-11-16T12:00:00Z" and v["prev"] == "2026-11-16T11:00:00Z"


def test_heartbeat_corrupt(tmp_path):
    (tmp_path / "kalp_atisi.json").write_text("{bad")
    with pytest.raises(F.FileIoError):
        F.heartbeat_read(tmp_path)
    (tmp_path / "kalp_atisi.json").write_text('{"x": 1}')
    with pytest.raises(F.FileIoError):
        F.heartbeat_read(tmp_path)
    (tmp_path / "kalp_atisi.json").write_text('{"ts": "garbage"}')
    with pytest.raises(F.FileIoError):
        F.heartbeat_read(tmp_path)


def test_interruption():
    a = F.interruption(None, T0)
    assert a["seconds"] is None and a["reason"] and a["prev"] is None
    b = F.interruption("2026-11-16T12:10:00Z", T0)  # saat geri gitti
    assert b["seconds"] is None and "geri" in b["reason"]
    c = F.interruption("2026-11-16T11:58:30Z", T0)
    assert c["seconds"] == 90.0 and c["reason"] is None
    assert F.interruption("2026-11-16T11:58:30Z", datetime(2026, 11, 16, 12)) ["seconds"] == 90.0  # naive -> UTC
