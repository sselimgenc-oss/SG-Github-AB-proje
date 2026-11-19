"""Cikis karsi-olgusu testleri icin ortak sentetik veri (docs/cikis-karsi-olgu-spec.md 9). Tarihler kilitli donemin disinda."""
from __future__ import annotations

import sqlite3
from datetime import datetime, timezone

from trader_core import exit_counterfactual as EC

T0 = datetime(2025, 1, 2, 0, 0, tzinfo=timezone.utc)
T0_MS = EC.to_ms(T0)
HR, M15 = EC.HR_MS, EC.M15_MS
NOW_MS = EC.to_ms(datetime(2025, 6, 1, tzinfo=timezone.utc))


def hour_to_15m(o, h, l, c, *, o_next=None):
    """Bir saatlik (o,h,l,c) -> 4 adet 15 dk mumu (tepe 2., dip 3. mumda); saat toplamlari korunur."""
    b0 = (o, o, o, o)
    b1 = (o, h, min(o, h), h)
    b2 = (h, h, l, l)
    b3 = (l, max(l, c), min(l, c), c)
    return [b0, b1, b2, b3]


def build(hours, *, atr=1.0, regime="trend_up", m15_override=None, start_ms=T0_MS):
    """hours: [(o,h,l,c)] -> (H1Series, m15 dict). Bosluksuz; m15_override {acilis_ms: (o,h,l,c)} ile ezilir."""
    ms = [start_ms + i * HR for i in range(len(hours))]
    h1 = EC.H1Series(ms, [x[0] for x in hours], [x[1] for x in hours], [x[2] for x in hours], [x[3] for x in hours],
                     [atr] * len(hours), [regime] * len(hours))
    m15 = {}
    for i, hh in enumerate(hours):
        for j, bar in enumerate(hour_to_15m(*hh)):
            m15[start_ms + i * HR + j * M15] = bar
    if m15_override:
        m15.update(m15_override)
    return h1, m15


def run(side, hours, *, trail, entry=100.0, stop=98.0, entry_off_ms=0, slip_exit=0.0, slip_stop=0.0, atr=1.0,
        regime="trend_up", m15_override=None, now_ms=NOW_MS, max_bars=EC.MAX_BARS, h1_m15=None):
    h1, m15 = h1_m15 if h1_m15 else build(hours, atr=atr, regime=regime, m15_override=m15_override)
    return EC.replay_trail(side=side, entry_price=entry, initial_stop=stop, entry_ms=T0_MS + entry_off_ms, trail_atr=trail, h1=h1,
                           m15=m15, now_ms=now_ms, slip_exit_bps=slip_exit, slip_stop_bps=slip_stop, max_bars=max_bars)


def trade(**kw) -> EC.TradeInput:
    base = dict(trade_id=1, pair="BTC/USDT", side="long", setup="T1", trigger_tf="1h", entry_ts=T0,
                exit_ts=datetime(2025, 1, 5, tzinfo=timezone.utc), entry_price=100.0, qty=1.0, planned_risk=2.0,
                initial_stop=98.0, fee_entry=0.0, exit_reason="trail_stop", exit_price=None, actual_net_r=None,
                param_version_id=1, own_value=3.0, source="paper", run_id="")
    base.update(kw)
    return EC.TradeInput(**base)


class FakeMarket:
    """bars()/funding() sunar; cagrilari ve sorgu araliklarini kaydeder."""

    def __init__(self, h1=None, m15=None, h4=None, funding=None):
        self.h1, self.m15, self.h4, self.fund = h1 or [], m15 or [], h4 or [], funding or []
        self.calls = []

    def bars(self, pair, tf, start_ms, end_ms, kind="last"):
        self.calls.append((tf, start_ms, end_ms))
        src = {"15m": self.m15, "1h": self.h1, "4h": self.h4}[tf]
        return [r for r in src if start_ms <= r[0] < end_ms]

    def funding(self, pair, start_ms, end_ms):
        self.calls.append(("funding", start_ms, end_ms))
        return [r for r in self.fund if start_ms <= r[0] < end_ms]


PARAMS = {"range_width_atr": 4.0, "vol_ratio_max": 1.5, "edge_zone_atr": 0.25, "pullback_ema": 50, "stop_buffer_atr": 0.3,
          "trail_atr": 3.0, "range_target_frac": 0.75, "rr_min": 1.5, "trigger_tf": "1h"}


def mk_t1_ledger(path, specs, *, bot="learner"):
    """specs: [(entry_ts, exit_ts, exit_price, reason, trigger_tf)] -> T1 long islemleri (giris 100, ilk stop 98, qty 1)."""
    from datetime import timedelta

    from trader_core import ledger as L
    led = L.open_ledger(path, bot, clock=lambda: datetime(2025, 6, 1, tzinfo=timezone.utc))
    led.init_params(PARAMS, reason="x")
    for i, (en, ex, px, why, tf) in enumerate(specs, start=1):
        did = led.record_decision(L.DecisionEvent(
            bar_close_ts=en - timedelta(hours=1) if tf == "1h" else en, trigger_tf=tf, pair="BTC/USDT", side="long", setup="T1",
            regime="trend_up", atr_ratio=1.1, rh=None, rl=None, rh_touches=0, rl_touches=0,
            features={"atr_1h": 1.0, "stop_dist_atr": 2.0, "atr_4h": 2.0, "body_ratio": 0.6, "ema_value": 99.0, "pullback_ema": 50},
            planned_entry=100.0, planned_stop=98.0, planned_target=None, param_version_id=1, veto_status="allowed",
            veto_reason=None, risk_allowed=True, risk_reason="ok", size_qty=1.0, size_notional=100.0, size_margin=30.0,
            size_risk_amount=2.0, leverage=3, final_action="entered", skip_reason=None))
        led.record_trade_entry(L.TradeEntry(i, did, en, 100.0, 1.0, 3, 0.0))
        led.record_trade_exit(L.TradeExit(i, ex, px, why, None, 0.0, 0.0))
    led.close()


def _sqlite_market(path, entry: datetime):
    c = sqlite3.connect(path)
    c.executescript("""PRAGMA user_version=1;
    CREATE TABLE bars(kind TEXT, pair TEXT, tf TEXT, open_ms INTEGER, o REAL,h REAL,l REAL,c REAL,v REAL DEFAULT 0, written_ms INTEGER,
      PRIMARY KEY(kind,pair,tf,open_ms)) WITHOUT ROWID;
    CREATE TABLE funding(pair TEXT, ts_ms INTEGER, rate REAL, mark REAL, PRIMARY KEY(pair,ts_ms)) WITHOUT ROWID;""")
    e = EC.to_ms(entry)
    for tf, ms in (("1h", HR), ("15m", M15), ("4h", EC.H4_MS)):
        t = e - 60 * EC.DAY_MS
        while t < e + 40 * EC.DAY_MS:
            c.execute("INSERT INTO bars VALUES('last','BTC/USDT',?,?,100,101,99,100,0,?)", (tf, t - t % ms, t - t % ms + ms))
            t += ms
    t = (e - 60 * EC.DAY_MS) // EC.H8_MS * EC.H8_MS
    while t < e + 40 * EC.DAY_MS:
        c.execute("INSERT INTO funding VALUES('BTC/USDT',?,0.0001,100.0)", (t + 5,))          # ham fundingTime birkac ms gec
        t += EC.H8_MS
    c.commit()
    c.close()
