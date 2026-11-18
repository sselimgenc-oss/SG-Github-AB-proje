"""Pano salt okunur dizinde ders magazasini acabilmeli (WAL, -wal/-shm yok): immutable=1 geri dusus."""
import sqlite3

import pytest

from trader_core import lesson as LS


class _Fail:
    def __init__(self, real):
        self._r = real

    def execute(self, *a, **k):
        raise sqlite3.OperationalError("unable to open database file")

    def close(self):
        self._r.close()

    def __setattr__(self, k, v):
        if k == "_r":
            object.__setattr__(self, k, v)
        else:
            setattr(self._r, k, v)


def _patch(monkeypatch, seen):
    real = sqlite3.connect

    def fake(db, *a, **k):
        seen.append(str(db))
        c = real(db, *a, **k)
        return c if "immutable=1" in str(db) or not str(db).startswith("file:") else _Fail(c)
    monkeypatch.setattr(LS.sqlite3, "connect", fake)


def test_ro_falls_back_to_immutable_when_no_wal(tmp_path, monkeypatch):
    p = tmp_path / "lesson.sqlite"
    LS.LessonStore(p).close()
    assert not (tmp_path / "lesson.sqlite-wal").exists()
    seen = []
    _patch(monkeypatch, seen)
    s = LS.LessonStore(p, read_only=True, create=False)
    try:
        assert s.open_requests() == []
    finally:
        s.close()
    assert any("immutable=1" in x for x in seen)


def test_ro_no_fallback_when_wal_present(tmp_path, monkeypatch):
    p = tmp_path / "lesson.sqlite"
    LS.LessonStore(p).close()
    (tmp_path / "lesson.sqlite-wal").write_bytes(b"")
    seen = []
    _patch(monkeypatch, seen)
    with pytest.raises(LS.LessonStoreError):
        LS.LessonStore(p, read_only=True, create=False)
    assert not any("immutable=1" in x for x in seen)


def test_ro_normal_path_unchanged(tmp_path):
    p = tmp_path / "lesson.sqlite"
    LS.LessonStore(p).close()
    s = LS.LessonStore(p, read_only=True, create=False)
    s.close()
    with pytest.raises(LS.LessonStoreError):
        LS.LessonStore(tmp_path / "yok.sqlite", read_only=True, create=False)
