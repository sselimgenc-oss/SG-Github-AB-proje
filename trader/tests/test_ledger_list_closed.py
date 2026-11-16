"""Ledger.list_closed_trades(since, until, limit): salt okunur, cikis zamani yeniden eskiye, sinirli."""
import os
from datetime import datetime, timedelta, timezone

import pytest

from panel_support import NOW, day_specs, mkledger
from trader_core import ledger as L

UTC = timezone.utc


@pytest.fixture
def led(tmp_path):
    specs = (day_specs(datetime(2026, 11, 14, tzinfo=UTC), [(True, True), (False, True)])
             + day_specs(datetime(2026, 11, 16, tzinfo=UTC), [(True, True), (True, False)]))
    mkledger(tmp_path / "l.sqlite", "learner", specs)
    ro = L.open_ledger(tmp_path / "l.sqlite", "learner", create=False, read_only=True, migrate=False)
    yield ro
    ro.close()


def test_order_exit_desc_and_open_excluded(led):
    t = led.list_closed_trades()
    assert [x.trade_id for x in t] == [3, 2, 1]                   # 4 acik: yok; cikis zamani yeniden eskiye
    assert all(x.exit_ts is not None for x in t)
    assert [x.exit_ts for x in t] == sorted((x.exit_ts for x in t), reverse=True)


def test_since_until_half_open(led):
    a = datetime(2026, 11, 14, tzinfo=UTC)
    got = led.list_closed_trades(since=a, until=a + timedelta(days=1))
    assert [x.trade_id for x in got] == [2, 1]
    assert [x.trade_id for x in led.list_closed_trades(since=datetime(2026, 11, 16, 7, 0, tzinfo=UTC))] == [3]
    first_exit = min(x.exit_ts for x in led.list_closed_trades())
    assert led.list_closed_trades(until=first_exit) == []         # until dislayici (<)
    assert len(led.list_closed_trades(since=first_exit)) == 3      # since dahil (>=)


def test_limit_bounded(led):
    assert [x.trade_id for x in led.list_closed_trades(limit=2)] == [3, 2]
    assert led.list_closed_trades(limit=0) == []
    with pytest.raises(L.LedgerValidationError):
        led.list_closed_trades(limit=-1)
    with pytest.raises(L.LedgerValidationError):
        led.list_closed_trades(limit=L.Ledger.LIST_CLOSED_MAX + 1)
    with pytest.raises(L.LedgerValidationError):
        led.list_closed_trades(limit=1.5)


def test_default_limit_is_200(tmp_path):
    specs = [(True, True, datetime(2026, 10, 1, tzinfo=UTC) + timedelta(hours=i)) for i in range(205)]
    mkledger(tmp_path / "b.sqlite", "learner", specs)
    ro = L.open_ledger(tmp_path / "b.sqlite", "learner", create=False, read_only=True, migrate=False)
    try:
        assert len(ro.list_closed_trades()) == 200
        assert len(ro.list_closed_trades(limit=1000)) == 205
    finally:
        ro.close()


def test_read_only_and_existing_behavior_unchanged(tmp_path, led):
    p = tmp_path / "l.sqlite"
    before = os.stat(p).st_mtime_ns
    led.list_closed_trades()
    assert os.stat(p).st_mtime_ns == before
    assert len(led._trades("", closed=True)) == 3                  # eski yol ayni kume
    assert [x.trade_id for x in led._trades("", closed=True)] == [1, 2, 3]   # eski siralama (giris zamani artan)
    assert len(led.list_open_trades()) == 1


def test_bot_isolation(tmp_path):
    mkledger(tmp_path / "t.sqlite", "twin", day_specs(datetime(2026, 11, 16, tzinfo=UTC), [(True, True)]))
    ro = L.open_ledger(tmp_path / "t.sqlite", "twin", create=False, read_only=True, migrate=False)
    try:
        assert len(ro.list_closed_trades()) == 1
    finally:
        ro.close()
