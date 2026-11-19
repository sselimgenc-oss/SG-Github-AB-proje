"""docs/cikis-karsi-olgu-spec.md 9 test 1: sentetik yollar (saf oynatim; elle hesapli degerler)."""
from __future__ import annotations

import inspect

import pandas as pd
import pytest

from exit_cf_support import HR, M15, NOW_MS, T0, T0_MS, build, run, trade
from trader_core import exit_counterfactual as EC
from trader_core import signals as S

NOFUND = lambda a, b: (0.0, None)          # noqa: E731


def price(res, **kw):
    tr = trade(**kw)
    return EC.price_result(res, tr, taker_fee=0.0, funding_of=NOFUND)


UP_PATH = [(100, 103, 100.5, 102.5), (102.5, 110, 102, 109), (109, 109, 100, 100), (100, 100, 100, 100)]


def test_a_looser_trail_beats_tighter_hand_values():
    tight = run("long", UP_PATH, trail=0.5)      # iz 103-0.5=102.5 = kapanis -> D_0'da gecildi -> sonraki acilista cikis
    loose = run("long", UP_PATH, trail=1.5)      # iz 101.5 -> 108.5; 3. saatte 108.5'ten vurulur
    assert (tight.reason, tight.exit_price, tight.exit_ms) == ("trail_stop", 102.5, T0_MS + HR)
    assert (loose.reason, loose.exit_price, loose.exit_ms) == ("trail_stop", 108.5, T0_MS + 2 * HR + 2 * M15)
    a, b = price(tight), price(loose)
    assert a["net_r"] == pytest.approx(1.25) and b["net_r"] == pytest.approx(4.25)   # (102.5-100)/2 ; (108.5-100)/2
    assert b["net_r"] - a["net_r"] == pytest.approx(3.0)


def test_b_same_15m_bar_stop_wins_over_new_high():
    hours = [(100, 103, 100.5, 102.5), (102.5, 120, 101, 119)]       # 2. saatte stop 101.5; ayni saatte yeni zirve 120
    # 2. saatin 15 dk mumlari: 2. mumda tepe 120 ama dip 101 de ayni saatin 3. mumunda; stop (101.5) once vurulur
    m = {T0_MS + HR + M15: (102.5, 120, 101.0, 119)}               # ayni mumda hem zirve hem dip
    r = run("long", hours, trail=1.5, m15_override=m)
    assert r.reason == "trail_stop" and r.exit_price == 101.5 and r.exit_ms == T0_MS + HR + M15


def test_c_gap_open_below_stop_fills_at_open_plus_stop_slip():
    hours = [(100, 103, 100.5, 102.5), (102.5, 102.6, 102.0, 102.4), (102.4, 102.4, 102.4, 102.4)]
    m = {T0_MS + HR + 2 * M15: (100.0, 100.0, 99.0, 99.5)}           # 3. mumun acilisi 100 < stop 101.5 (ilk mum degil)
    r = run("long", hours, trail=1.5, m15_override=m, slip_stop=10.0)
    assert r.reason == "trail_stop" and r.exit_price == pytest.approx(100.0 * (1 - 0.001))


def test_d_never_reaches_1r_means_no_trail_alt_equals_base():
    hours = [(100, 101.5, 99.5, 101.0), (101.0, 101.8, 99.0, 99.2), (99.2, 99.2, 97.0, 97.5)]
    r1, r2 = run("long", hours, trail=1.0), run("long", hours, trail=2.0)
    assert r1.reason == r2.reason == "stop" and r1.exit_price == r2.exit_price == 98.0
    assert price(r1)["net_r"] == price(r2)["net_r"] == pytest.approx(-1.0)


def test_e_short_mirror():
    hours = [(100, 99.5, 97, 97.5), (97.5, 98, 90, 91), (91, 100, 91, 99), (99, 99, 99, 99)]
    r = run("short", hours, trail=1.5, stop=102.0, regime="trend_down")
    # R=2, +1R=98; en dusuk 97 -> iz 97+1.5=98.5 (<102); 2. saatta dip 90 -> 91.5; 3. saatte 91.5 yukari vurulur
    assert r.reason == "trail_stop" and r.exit_price == 91.5
    assert price(r, side="short", initial_stop=102.0, planned_risk=2.0)["net_r"] == pytest.approx((100 - 91.5) / 2)


def test_f_market_exit_next_open_with_exit_slip():
    r = run("long", UP_PATH, trail=0.5, slip_exit=10.0)
    assert r.reason == "trail_stop" and r.exit_ms == T0_MS + HR
    assert r.exit_price == pytest.approx(102.5 * (1 - 0.001))                  # stop kaymasi degil, cikis kaymasi


def test_g_funding_three_times_sign_and_amount():
    entry = T0_MS                                                                 # 2025-01-02 00:00 UTC
    exit_ms = T0_MS + 17 * HR                                                     # 17:00
    times = EC.funding_grid_times(entry, exit_ms)
    assert times == [T0_MS + 8 * HR, T0_MS + 16 * HR]                             # 00:00 (giris an) hariç
    times3 = EC.funding_grid_times(entry, T0_MS + 25 * HR)
    assert len(times3) == 3
    pts = [(t, 0.0001, 100.0) for t in times3]
    fn_long = EC._funding_fn(pts, NOW_MS, "long", 2.0, 100.0)
    assert fn_long(entry, T0_MS + 25 * HR) == (pytest.approx(3 * 2.0 * 100.0 * 0.0001), None)
    fn_short = EC._funding_fn(pts, NOW_MS, "short", 2.0, 100.0)
    assert fn_short(entry, T0_MS + 25 * HR)[0] == pytest.approx(-3 * 2.0 * 100.0 * 0.0001)
    longer, shorter = fn_long(entry, T0_MS + 25 * HR)[0], fn_long(entry, T0_MS + 17 * HR)[0]
    assert longer > shorter                                                      # sure uzayinca funding artar
    assert fn_long(entry, T0_MS + 25 * HR + 8 * HR)[1] == T0_MS + 32 * HR       # eksik oran -> eksik zaman


def test_h_horizon_mtm_censored_at_last_close():
    hours = [(100, 100.5, 99.5, 100.2)] * 6
    r = run("long", hours, trail=3.0, max_bars=5, slip_exit=10.0)
    assert (r.reason, r.censored, r.bars_held) == ("horizon", 1, 5)
    assert r.exit_price == pytest.approx(100.2 * (1 - 0.001)) and r.exit_ms == T0_MS + 5 * HR


def test_i_regime_flip_has_priority_over_trail():
    h1, m15 = build(UP_PATH)
    h1.regime[0] = "trend_down"                                                  # long icin donus
    r = run("long", UP_PATH, trail=0.5, h1_m15=(h1, m15))
    assert r.reason == "regime_flip" and r.exit_ms == T0_MS + HR and r.exit_price == 102.5


def test_j_entry_bar_including_pre_entry_part_feeds_trail():
    # giris saatin 20. dakikasi; giris mumunun (floor_1h) high'i iz hesabina girer
    hours = [(100, 103, 100.5, 102.8), (102.8, 103, 102.0, 102.7), (102.7, 102.7, 102.7, 102.7)]
    r = run("long", hours, trail=0.5, entry_off_ms=20 * 60_000, max_bars=3)
    # path[0] = 103-0.5 = 102.5; kapanis 102.8 -> gecilmedi; sikilasir; sonra 15 dk vurusu
    assert r.reason in ("trail_stop",) and r.exit_price == 102.5


def test_k_tightened_stop_already_crossed_at_next_open_is_market_trail_exit():
    hours = [(100, 103, 100.5, 102.9), (102.2, 102.4, 102.0, 102.1)]
    m = {T0_MS + HR: (102.2, 102.4, 102.0, 102.1)}                                  # acilis 102.2 < yeni stop 102.5
    r = run("long", hours, trail=0.5, m15_override=m, slip_exit=10.0, slip_stop=50.0)
    assert r.reason == "trail_stop" and r.exit_ms == T0_MS + HR
    assert r.exit_price == pytest.approx(102.2 * (1 - 0.001))                       # piyasa cikisi (stop kaymasi degil)


def test_l_not_armed_close_beyond_initial_stop_gives_no_trail_exit_at_close():
    # 15 dk mumlari stopa degmiyor ama 1h kapanisi ilk stopun otesinde: armed degil -> kapanista trail_stop uretilmez
    hours = [(100, 100.5, 99.5, 97.0), (97.0, 97.5, 96.5, 97.0)]
    m = {T0_MS + i * M15: (99.0, 99.2, 98.5, 99.0) for i in range(4)}
    m.update({T0_MS + HR + i * M15: (99.0, 99.2, 98.5, 99.0) for i in range(4)})
    r = run("long", hours, trail=3.0, m15_override=m, max_bars=2)
    assert r.reason == "horizon" and r.exit_ms == T0_MS + 2 * HR                      # piyasa cikisi kapanista olmadi


def test_m_single_full_path_equals_prefix_calls():
    n = 40
    hs = pd.Series([100 + (i % 7) * 0.8 + i * 0.1 for i in range(n)], dtype="float64")
    ls = hs - 1.0
    at = pd.Series([1.0 + 0.01 * i for i in range(n)], dtype="float64")
    full = S.trail_stop_path("long", 100.0, 98.0, hs, ls, at, 1.5)
    for k in range(n):
        pre = S.trail_stop_path("long", 100.0, 98.0, hs[:k + 1], ls[:k + 1], at[:k + 1], 1.5)
        assert pre.iloc[-1] == full.iloc[k]


def test_trail_formula_is_called_not_copied():
    src = inspect.getsource(EC)
    assert "S.trail_stop_path(" in src and "TRAIL_START_R" not in src
    assert "hh - tr" not in src and "cand = " not in src                        # satir ici kopya yok
    assert EC.EPS == S.EPS


def test_pending_when_bars_end_and_gap_when_hole():
    short = UP_PATH[:2]
    r = run("long", short, trail=3.0, now_ms=T0_MS + 2 * HR)
    assert r.status == "pending"
    hours = [(100, 100.5, 99.5, 100.2)] * 4
    m = {}
    h1, m15 = build(hours)
    del m15[T0_MS + 2 * HR + M15]                                                  # delik
    r = EC.replay_trail(side="long", entry_price=100.0, initial_stop=98.0, entry_ms=T0_MS, trail_atr=3.0, h1=h1, m15=m15,
                        now_ms=NOW_MS, slip_exit_bps=0, slip_stop_bps=0)
    assert r.status == "gap" and r.gap_ms == T0_MS + 2 * HR + M15 and r.gap_kind == "bars15"
