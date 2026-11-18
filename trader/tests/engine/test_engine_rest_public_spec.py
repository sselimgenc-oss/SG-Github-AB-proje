"""07 §4.1 test senaryoları (sahte oturum; gerçek saat/uyku/ağ yok)."""
import sys
import time

import pytest

from trader_engine.marketdata import rest_public as P

T = 3_600_000  # 1h ms


class Resp:
    def __init__(self, status=200, body=None, headers=None, text=""):
        self.status_code, self._b, self.headers, self.text = status, body, headers or {}, text

    def json(self):
        return self._b


class Sess:
    def __init__(self, seq):
        self.seq, self.calls = list(seq), []

    def get(self, url, params=None, timeout=None):
        self.calls.append((url, params))
        x = self.seq.pop(0)
        if isinstance(x, Exception):
            raise x
        return x


class Clk:
    def __init__(self):
        self.t, self.sleeps = 1000.0, []

    def now(self):
        return self.t

    def sleep(self, s):
        self.sleeps.append(s)
        self.t += s


def mk(seq, **kw):
    c = Clk()
    return P.PublicRestClient(session=Sess(seq), now_s=c.now, sleep=c.sleep, **kw), c


def row(open_ms, tf_ms=T, c=100.0):
    return [open_ms, "100", "101", "99", str(c), "5", open_ms + tf_ms - 1, "500", 10, "1", "1", "0"]


@pytest.fixture(autouse=True)
def no_real_time(monkeypatch):
    # Python 3.12'de logging kayit olustururken time.time() cagirir; bu yuzden yalniz rest_public
    # modulunden (dogrudan cagiranin dosya adi) gelen cagrilar yasaklanir, digerleri gercek islevi kullanir.
    mod_file = P.__file__

    def guard(real):
        def wrapped(*a, **k):
            if sys._getframe(1).f_code.co_filename == mod_file:  # dogrudan cagiran = rest_public
                raise AssertionError("gerçek saat/uyku çağrıldı")
            return real(*a, **k)
        return wrapped
    monkeypatch.setattr(time, "sleep", guard(time.sleep))
    monkeypatch.setattr(time, "time", guard(time.time))


def test_5xx_retried_then_ok():
    cl, c = mk([Resp(503), Resp(500), Resp(200, {"serverTime": 5})])
    assert cl.server_time_ms() == 5
    assert c.sleeps == [2, 4]


def test_network_error_retried_and_message_has_no_url():
    cl, _ = mk([ConnectionError("https://fapi.binance.com/secret?x=1")] * 3, max_attempts=3)
    with pytest.raises(P.ExchangeError) as e:
        cl.get("/fapi/v1/time", {"symbol": "BTCUSDT"})
    assert "http" not in str(e.value) and "BTCUSDT" not in str(e.value) and "/fapi/v1/time" in str(e.value)


def test_429_waits_retry_after_then_ok():
    cl, c = mk([Resp(429, headers={"Retry-After": "7"}), Resp(200, {"ok": 1})])
    assert cl.get("/x") == {"ok": 1} and c.sleeps == [7]


def test_429_garbage_retry_after_is_60():
    cl, c = mk([Resp(429, headers={"Retry-After": "soon"}), Resp(200, {})])
    cl.get("/x")
    assert c.sleeps == [60]


def test_429_total_wait_cap_is_ban():
    cl, c = mk([Resp(429, headers={"Retry-After": "200"})] * 3, max_total_wait_s=300)
    with pytest.raises(P.ExchangeBan) as e:
        cl.get("/x")
    assert e.value.http == 429 and c.sleeps == [200]


@pytest.mark.parametrize("code", [418, 451])
def test_418_451_not_retried(code):
    cl, c = mk([Resp(code, headers={"Retry-After": "120"}, text="blocked"), Resp(200, {})])
    with pytest.raises(P.ExchangeBan) as e:
        cl.get("/x", {"symbol": "S"})
    assert e.value.http == code and not c.sleeps and len(cl.session.calls) == 1
    assert "symbol" not in str(e.value)


def test_other_4xx_raises_without_params():
    cl, _ = mk([Resp(400, text="bad")])
    with pytest.raises(P.ExchangeError) as e:
        cl.get("/x", {"symbol": "SECRET"})
    assert "SECRET" not in str(e.value) and not isinstance(e.value, P.ExchangeBan)


def test_max_attempts_exhausted():
    cl, _ = mk([Resp(500)] * 2, max_attempts=2)
    with pytest.raises(P.ExchangeError):
        cl.get("/x")


def test_weight_threshold_waits():
    cl, c = mk([Resp(200, {}, {"X-MBX-USED-WEIGHT-1M": "1800"}), Resp(200, {})])
    cl.get("/x")
    assert cl.used_weight() == 1800 and not c.sleeps
    cl.get("/x")
    assert len(c.sleeps) == 1 and 1 <= c.sleeps[0] <= 60 and cl.used_weight() == 0


def test_klines_all_paginates_without_duplicates():
    p1 = [row(i * T) for i in range(3)]
    p2 = [row(i * T) for i in range(3, 5)]
    cl, _ = mk([Resp(200, p1), Resp(200, p2)])
    rows = cl.klines_all("BTCUSDT", "1h", 0, page=3)
    assert [r[0] for r in rows] == [i * T for i in range(5)]
    assert cl.session.calls[1][1]["startTime"] == 2 * T + 1
    assert cl.session.calls[0][0].endswith("/fapi/v1/klines")


def test_klines_all_exact_page_then_empty_and_max_pages():
    cl, _ = mk([Resp(200, [row(0)]), Resp(200, [])])
    assert len(cl.klines_all("S", "1h", 0, page=1)) == 1
    cl, _ = mk([Resp(200, [row(i * T)]) for i in range(5)])
    with pytest.raises(P.ExchangeError):
        cl.klines_all("S", "1h", 0, page=1, max_pages=3)


def test_mark_klines_and_premium_paths():
    cl, _ = mk([Resp(200, []), Resp(200, {"markPrice": "1"}), Resp(200, [])])
    cl.mark_price_klines("S", "1h")
    assert cl.premium_index("S") == {"markPrice": "1"}
    cl.premium_index()
    urls = [u for u, _ in cl.session.calls]
    assert urls[0].endswith("/fapi/v1/markPriceKlines") and urls[1].endswith("/fapi/v1/premiumIndex")
    assert cl.session.calls[2][1] is None


def test_funding_all_paginates_and_dedupes():
    # limit sabit 1000 olduğundan sayfa dolu sayılması için ilk yanıtı 1000'e tamamla
    f = [{"fundingTime": i, "fundingRate": "0.0001"} for i in range(1000)]
    cl, _ = mk([Resp(200, f), Resp(200, [{"fundingTime": 999, "fundingRate": "1"}, {"fundingTime": 1000, "fundingRate": "2"}])])
    out = cl.funding_rates_all("S", 0)
    assert [x["fundingTime"] for x in out] == list(range(1001))
    assert cl.session.calls[1][1]["startTime"] == 1000


def test_rows_to_bars_closed_filter_boundary():
    rows = [row(0), row(T)]
    b, bad = P.rows_to_bars("BTC/USDT", "last", "1h", rows, now_server_ms=2 * T)       # closeTime+1 == now: kapanmış
    assert len(b) == 2 and not bad and b[0].o == 100.0 and b[0].v == 5.0 and b[0].open_ts.timestamp() == 0
    b, _ = P.rows_to_bars("BTC/USDT", "last", "1h", rows, now_server_ms=2 * T - 1)      # 1 ms önce: açık
    assert len(b) == 1


def test_rows_to_bars_abnormal_and_mark_volume():
    bad_close = row(0)
    bad_close[6] += 1
    nan_row = row(T)
    nan_row[4] = "nan"
    zero_row = row(2 * T)
    zero_row[3] = "0"
    good = row(3 * T)
    b, bad = P.rows_to_bars("BTC/USDT", "mark", "1h", [bad_close, nan_row, zero_row, good], 10 * T)
    assert [(a.open_ms, a.reason) for a in bad] == [(0, "bad_close_time"), (T, "bad_values"), (2 * T, "bad_values")]
    assert len(b) == 1 and b[0].kind == "mark" and b[0].v == 0.0

