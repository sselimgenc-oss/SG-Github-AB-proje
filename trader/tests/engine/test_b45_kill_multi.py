"""WP-B4/B5 re-review madde 8: iki acik canli pozisyon (iki parite), KILL -> ikisi de duz, stoplari iptal.

LiveEnv (test_engine_live_spec) tek pariteli; burada kendi alt sinifimizla iki pariteye genisletilir (paylasilan duzenek
dosyalarina dokunulmaz). Yalniz kamusal girisler (decision_step / live_tick) kullanilir. Sentetik veri, ag yok.
"""
from __future__ import annotations

from pathlib import Path

import pytest

import test_engine_live_spec as T
from test_engine_05_spec import make_frame

DOGE = "DOGE/USDT"
DSYM = "DOGEUSDT"


class LiveEnv2(T.LiveEnv):
    def __init__(self, tmp, **kw):
        super().__init__(tmp, pairs=(T.XRP, DOGE), **kw)

    def signal_pair(self, pair, D=T.DEC):
        self.src.frames[(pair, D)] = make_frame(pair, D, version=self.version_id, entry=2.0, stop=1.9, atr_tf=0.05,
                                                atr_4h=0.1, stop_dist_atr=2.0)

    def enter_both(self, D=T.DEC):
        self.signal_pair(T.XRP, D)
        self.signal_pair(DOGE, D)
        self.decide(D)

    def amt(self, sym):
        p = self.ex.pos.get(sym)
        return p["amt"] if p else 0

    def live_stops(self, sym):
        return [a for a in self.ex.algos.values() if a["symbol"] == sym and a["algoStatus"] == "NEW"]


@pytest.fixture
def env2(tmp_path):
    e = LiveEnv2(tmp_path).boot()
    yield e
    e.close()


def test_b45kill_two_open_positions_both_flat_and_stops_cancelled(env2):
    e = env2
    e.enter_both()
    px, pd = e.state.position_for_pair(T.XRP), e.state.position_for_pair(DOGE)
    assert px is not None and pd is not None and px.status == "open" and pd.status == "open", (px, pd)
    assert e.amt(T.SYM) > 0 and e.amt(DSYM) > 0
    assert len(e.live_stops(T.SYM)) == 1 and len(e.live_stops(DSYM)) == 1

    e.view.dead = True                                    # besleme yok: KILL live_tick'te yurur
    Path(e.cfg.kill_file).parent.mkdir(parents=True, exist_ok=True)
    Path(e.cfg.kill_file).write_text("{}")
    for _ in range(4):
        e.tick(6)

    assert e.amt(T.SYM) == 0 and e.amt(DSYM) == 0, "KILL sonrasi borsada acik pozisyon kaldi"
    assert e.live_stops(T.SYM) == [] and e.live_stops(DSYM) == [], "KILL sonrasi stop kaldi"
    for p in (px, pd):
        cur = e.state.get_position(p.trade_id)
        assert cur.status == "closed" and cur.exit_reason == "force_exit", (p.pair, cur.status, cur.exit_reason)
    xs = e.posted("x")
    assert len(xs) == 2 and {q["symbol"] for _, _, q in xs} == {T.SYM, DSYM}
    assert all(q.get("reduceOnly") in ("true", True) for _, _, q in xs)
    assert e.state.position_for_pair(T.XRP) is None and e.state.position_for_pair(DOGE) is None
