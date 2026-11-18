"""DD-9 uygulama testleri (motor tarafi): peek_meta, proc_guard, ensure-ledger, ban_store dizin fsync, status blogu."""
from __future__ import annotations

import os
import sqlite3
import stat
from pathlib import Path

import pytest

from trader_core import ledger as L
from trader_core import proc_guard
from trader_core.ban_store import write_ban


def test_impl9_peek_meta_is_read_only_and_total(tmp_path):
    p = tmp_path / "led.sqlite"
    assert L.peek_meta(p, "account_stamp") is None                   # dosya yok
    p.write_bytes(b"")
    assert L.peek_meta(p, "account_stamp") is None                   # 0 bayt
    assert p.stat().st_size == 0
    c = sqlite3.connect(p)
    c.execute("CREATE TABLE x(a)")
    c.commit()
    c.close()
    before = p.read_bytes()
    assert L.peek_meta(p, "account_stamp") is None                   # meta tablosu yok
    assert p.read_bytes() == before
    p.write_bytes(b"bu bir sqlite dosyasi degil" * 10)
    with pytest.raises(L.LedgerError):
        L.peek_meta(p, "account_stamp")


def test_impl9_proc_guard_roundtrip_in_subprocess():
    import subprocess
    import sys
    code = ("import sys; sys.path.insert(0, %r)\nfrom trader_core import proc_guard as P\n"
            "print(P.set_nondumpable(), P.is_dumpable())" % str(Path(__file__).resolve().parents[2] / "src"))
    out = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True).stdout.split()
    if sys.platform.startswith("linux"):
        assert out == ["True", "False"]


def test_impl9_write_ban_fsyncs_directory(tmp_path, monkeypatch):
    seen = []
    real = os.fsync

    def spy(fd):
        seen.append(stat.S_ISDIR(os.fstat(fd).st_mode))
        return real(fd)
    monkeypatch.setattr(os, "fsync", spy)
    assert write_ban(str(tmp_path / "ban.fapi.binance.com.json"), until_ms=10_000_000, http=429, source="t", now_ms=0)
    assert True in seen and False in seen


def test_impl9_status_exchange_account_mode_values_are_ints_or_none():
    from trader_engine.status import _exchange_block

    class E:
        broker = None
    blk = _exchange_block(E(), {"exchange": {"account_mode_drift": 2, "account_mode_unverified": True}}, "live")
    assert blk["account_mode"] == {"drift": 2, "unverified": None, "unverified_ban": None}


# ----------------------------------------------------------------------------- F1: run --ensure-ledger, eski semali defter
import types  # noqa: E402

import test_dd8_spec as D8  # noqa: E402
from fake_exchange import KEY, SECRET, FakeExchange  # noqa: E402
from test_dd9_spec import _make_v3, _sha, _uv, patch_proc_guard  # noqa: E402


@pytest.fixture
def run_env9(monkeypatch):
    from trader_engine import cli
    from trader_engine import engine as E
    ex = FakeExchange(lambda: 1_800_000_000_000)
    D8.patch_rest(monkeypatch, ex)
    monkeypatch.setenv("BINANCE_API_KEY", KEY)
    monkeypatch.setenv("BINANCE_API_SECRET", SECRET)
    monkeypatch.delenv("LIVE_CONFIRM", raising=False)
    monkeypatch.setattr(cli.signal, "signal", lambda *a, **k: None)
    calls: list = []

    class Eng:
        def run_forever(self):
            return None

        def stop(self):
            return None
    monkeypatch.setattr(E, "build_engine", lambda cfg, **kw: (calls.append(cfg), Eng())[1])
    patch_proc_guard(monkeypatch, True)
    return types.SimpleNamespace(ex=ex, calls=calls)


def _run_ensure(cdir):
    from trader_engine import cli
    return cli.main(["run", "--bot", "learner", "--env", "testnet", "--config-dir", str(cdir), "--ensure-ledger"])


def test_impl9_f1_ensure_ledger_old_schema_matching_stamp_skips_init_and_builds(tmp_path, monkeypatch, run_env9):
    cdir, _ = D8.make_tree(tmp_path, "testnet")
    monkeypatch.chdir(tmp_path)
    cfg = D8.cli_cfg(cdir, "testnet")
    Path(cfg.ledger_path).parent.mkdir(parents=True, exist_ok=True)
    _make_v3(cfg.ledger_path, stamp="testnet:testnet-sub")
    sha = _sha(cfg.ledger_path)
    assert _run_ensure(cdir) == 0
    assert len(run_env9.calls) == 1                      # build_engine (goc orada) bir kez
    assert _sha(cfg.ledger_path) == sha and _uv(cfg.ledger_path) == 3   # init isi dosyaya dokunmadi


def test_impl9_f1_ensure_ledger_old_schema_foreign_stamp_exit_8_untouched(tmp_path, monkeypatch, run_env9):
    cdir, _ = D8.make_tree(tmp_path, "testnet")
    monkeypatch.chdir(tmp_path)
    cfg = D8.cli_cfg(cdir, "testnet")
    Path(cfg.ledger_path).parent.mkdir(parents=True, exist_ok=True)
    _make_v3(cfg.ledger_path, stamp="live:baska")
    sha = _sha(cfg.ledger_path)
    assert _run_ensure(cdir) == 8
    assert run_env9.calls == [] and run_env9.ex.requests == []
    assert _sha(cfg.ledger_path) == sha and _uv(cfg.ledger_path) == 3
    assert not [p for p in Path(cfg.ledger_path).parent.iterdir() if "premigrate" in p.name]


def test_impl9_f1_ensure_ledger_old_schema_no_stamp_exit_8_untouched(tmp_path, monkeypatch, run_env9):
    cdir, _ = D8.make_tree(tmp_path, "testnet")
    monkeypatch.chdir(tmp_path)
    cfg = D8.cli_cfg(cdir, "testnet")
    Path(cfg.ledger_path).parent.mkdir(parents=True, exist_ok=True)
    _make_v3(cfg.ledger_path, stamp=None)
    sha = _sha(cfg.ledger_path)
    assert _run_ensure(cdir) == 8
    assert run_env9.calls == []
    assert _sha(cfg.ledger_path) == sha and _uv(cfg.ledger_path) == 3
    assert not [p for p in Path(cfg.ledger_path).parent.iterdir() if "premigrate" in p.name]
