"""P0 paper-baslangic: `feed.main` / `feed.rules_snapshot_main`, acilis kural cekimi (retry/451), saatlik yenileme.
Sahte REST oturumu; ag yok."""
from __future__ import annotations

import hashlib
import json
import logging
from datetime import datetime, timezone
from pathlib import Path

import pytest

from trader_engine import cli
from trader_engine.bars import to_ms
from trader_engine.clock import SimClock
from trader_engine.marketdata import feed as F
from trader_engine.marketdata.feed import Feed, FeedConfig, RulesFetchError
from trader_engine.marketdata.rest_public import PublicRestClient
from trader_engine.marketdata.store import MarketStore

FIXT = Path(__file__).parent / "fixtures" / "binance" / "exchange_info_sample.json"
T0 = datetime(2026, 12, 1, 9, 0, tzinfo=timezone.utc)
BTC, ETH = "BTC/USDT", "ETH/USDT"


class _Resp:
    def __init__(self, status=200, body=None, text=""):
        self.status_code, self._b, self.headers, self.text = status, body, {}, text

    def json(self):
        return self._b


class _Session:
    def __init__(self, server_ms):
        self.server_ms = server_ms
        self.info = json.loads(FIXT.read_text())
        self.info_status = 200
        self.paths = []

    def get(self, url, params=None, timeout=None):
        path = url.split("fapi.binance.com")[1]
        self.paths.append(path)
        if path == "/fapi/v1/time":
            return _Resp(200, {"serverTime": self.server_ms})
        if path == "/fapi/v1/exchangeInfo":
            if self.info_status != 200:
                return _Resp(self.info_status, None, "restricted location" if self.info_status == 451 else "boom")
            return _Resp(200, self.info)
        return _Resp(200, [])      # klines/mark/funding: bos


def _cfg_dir(tmp_path, pairs=(BTC, ETH)) -> Path:
    d = tmp_path / "config"
    d.mkdir()
    (d / "engine.base.json").write_text(json.dumps({
        "pairs": list(pairs), "var_dir": str(tmp_path / "var"), "market_db": str(tmp_path / "var" / "market.sqlite"),
        "history_dir": str(tmp_path / "hist")}))
    return d


def _rest(sess, clock):
    return PublicRestClient(session=sess, now_s=lambda: clock.now().timestamp(), sleep=clock.sleep, max_attempts=2)


def test_feedmain_builds_config_from_base_and_runs(tmp_path):
    d = _cfg_dir(tmp_path)
    clock = SimClock(T0)
    sess = _Session(to_ms(T0))
    rc = F.main(["--config-dir", str(d)], rest=_rest(sess, clock), clock=clock, max_ticks=2)
    assert rc == 0
    st = MarketStore(tmp_path / "var" / "market.sqlite", read_only=True)
    assert st.get_rules(BTC) is not None and st.get_rules(ETH) is not None
    assert st.meta_get("rules_fetched_at") and st.meta_get("rules_last_error") == ""
    assert (tmp_path / "var" / "feed-status.json").exists()
    # kilit birakildi: ikinci feed acilabilir
    Feed(FeedConfig((BTC,), str(tmp_path / "x.sqlite"), str(tmp_path / "var" / "feed.lock"), str(tmp_path / "s.json")),
         _rest(sess, clock), MarketStore(tmp_path / "x.sqlite"), clock).start()


def test_feedmain_startup_rules_failure_retries_then_exits_nonzero(tmp_path, caplog):
    d = _cfg_dir(tmp_path)
    clock = SimClock(T0)
    sess = _Session(to_ms(T0))
    sess.info_status = 500
    with caplog.at_level(logging.WARNING):
        rc = F.main(["--config-dir", str(d)], rest=_rest(sess, clock), clock=clock, max_ticks=1)
    assert rc == F.EXIT_RULES != 0
    assert sess.paths.count("/fapi/v1/exchangeInfo") >= 2 * 4        # 4 deneme x max_attempts=2
    assert (clock.now() - T0).total_seconds() >= 5 + 15 + 45          # sinirli geri cekilme gercekten beklendi
    assert any("denemede alinamadi" in r.getMessage() for r in caplog.records)


def test_feedmain_http451_distinct_message_and_code(tmp_path, caplog):
    d = _cfg_dir(tmp_path)
    clock = SimClock(T0)
    sess = _Session(to_ms(T0))
    sess.info_status = 451
    with caplog.at_level(logging.CRITICAL):
        rc = F.main(["--config-dir", str(d)], rest=_rest(sess, clock), clock=clock, max_ticks=1)
    assert rc == F.EXIT_GEOBLOCK != F.EXIT_RULES
    assert any("HTTP 451" in r.getMessage() and "konum" in r.getMessage() for r in caplog.records)
    assert sess.paths.count("/fapi/v1/exchangeInfo") == 1             # 451 tekrarlanmaz, bekleme yok
    assert (clock.now() - T0).total_seconds() < 5


def test_feedstart_partial_rules_is_failure(tmp_path):
    clock = SimClock(T0)
    sess = _Session(to_ms(T0))
    cfg = FeedConfig((BTC, "SOL/USDT"), str(tmp_path / "m.sqlite"), str(tmp_path / "l"), str(tmp_path / "s.json"),
                     rules_start_backoff_s=(1.0,))
    f = Feed(cfg, _rest(sess, clock), MarketStore(tmp_path / "m.sqlite"), clock)
    with pytest.raises(RulesFetchError) as ei:
        f.start()
    assert "SOL/USDT" in str(ei.value) and not ei.value.geoblock
    f.close()


def test_feed_hourly_rules_refresh_failure_is_warning_and_stamps_meta(tmp_path, caplog):
    clock = SimClock(T0)
    sess = _Session(to_ms(T0))
    cfg = FeedConfig((BTC, ETH), str(tmp_path / "m.sqlite"), str(tmp_path / "l"), str(tmp_path / "s.json"),
                     backfill_bars={"1m": 0, "15m": 0, "1h": 0, "4h": 0})
    store = MarketStore(tmp_path / "m.sqlite")
    f = Feed(cfg, _rest(sess, clock), store, clock)
    f.start()
    ok_at = store.meta_get("rules_fetched_at")
    assert ok_at and store.meta_get("rules_last_error") == ""
    sess.info_status = 500
    clock.advance(3700)
    sess.server_ms = to_ms(clock.now())
    with caplog.at_level(logging.WARNING):
        f.run_once()                                                   # firlatmaz
    assert store.meta_get("rules_fetched_at") == ok_at                 # son BASARILI cekim damgasi degismez
    assert int(store.meta_get("rules_attempt_at")) > int(ok_at)        # deneme damgalandi
    assert store.meta_get("rules_last_error")
    assert any(r.levelno == logging.WARNING and r.name == "engine.feed" for r in caplog.records)
    assert store.get_rules(BTC) is not None                            # eski kural duruyor
    f.close()


def test_rules_snapshot_main_writes_json_and_sidecar(tmp_path):
    d = _cfg_dir(tmp_path)
    clock = SimClock(T0)
    sess = _Session(to_ms(T0))
    out = tmp_path / "out" / "rules.json"
    rc = F.rules_snapshot_main(["--config-dir", str(d), "--out", str(out)], rest=_rest(sess, clock), clock=clock)
    assert rc == 0
    data = json.loads(out.read_text())
    assert set(data) == {BTC, ETH}
    meta = json.loads((tmp_path / "out" / "rules.json.meta.json").read_text())
    assert meta["sha256"] == hashlib.sha256(out.read_bytes()).hexdigest()
    assert meta["fetched_at"] == "2026-12-01T09:00:00Z"
    assert meta["source_url"].endswith("/fapi/v1/exchangeInfo") and meta["source_url"].startswith("https://")


def test_rules_snapshot_main_default_out_and_451_and_missing_pair(tmp_path, capsys):
    clock = SimClock(T0)
    d = _cfg_dir(tmp_path)
    sess = _Session(to_ms(T0))
    assert F.rules_snapshot_main(["--config-dir", str(d)], rest=_rest(sess, clock), clock=clock) == 0
    assert (tmp_path / "hist" / "rules.json").exists()
    sess.info_status = 451
    assert F.rules_snapshot_main(["--config-dir", str(d)], rest=_rest(sess, clock), clock=clock) == F.EXIT_GEOBLOCK
    assert "HTTP 451" in capsys.readouterr().err
    d2 = tmp_path / "c2"
    d2.mkdir()
    (d2 / "engine.base.json").write_text(json.dumps({"pairs": [BTC, "SOL/USDT"], "var_dir": str(tmp_path / "v2"),
                                                     "market_db": str(tmp_path / "v2" / "m.sqlite"), "history_dir": str(tmp_path / "h2")}))
    sess.info_status = 200
    assert F.rules_snapshot_main(["--config-dir", str(d2)], rest=_rest(sess, clock), clock=clock) == 1
    assert "SOL/USDT" in capsys.readouterr().err


def test_cli_subcommands_dispatch_to_feed_entrypoints(tmp_path, monkeypatch):
    """cli.py'deki `feed` ve `rules-snapshot` artik 'bu surumde yok' degil, gercek giris noktalarina gider."""
    d = _cfg_dir(tmp_path)
    now = datetime.now(timezone.utc)
    sess = _Session(to_ms(now))
    monkeypatch.setattr(F, "_make_rest", lambda clock: PublicRestClient(
        session=sess, now_s=lambda: clock.now().timestamp(), sleep=clock.sleep, max_attempts=2))
    assert cli.main(["rules-snapshot", "--config-dir", str(d)]) == 0
    assert (tmp_path / "hist" / "rules.json").exists()
    orig = Feed.run_forever
    monkeypatch.setattr(Feed, "run_forever", lambda self, max_ticks=None: orig(self, max_ticks=1))
    assert cli.main(["feed", "--config-dir", str(d)]) == 0
    assert MarketStore(tmp_path / "var" / "market.sqlite", read_only=True).get_rules(BTC) is not None
