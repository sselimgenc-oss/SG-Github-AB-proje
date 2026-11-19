"""Cikis kipleri (basa-bas / kismi kar alma): MOTOR <-> KARSI-OLGU (exitcf-v2 `run_modes_once`) BIREBIR PARITE (docs/cikis-kipleri-spec.md 9).

Yontem: sentetik 1 dk yoldan (rejim degisen suruklenme; 15m/1h/4h bundan turetilir) GERCEK motor geri testi (native, 1 dk adim, tetik
`last`, kip ACIK) kosulur; cikan her islem icin karsi-olgu oynatimi (15 dk izgara, 1a ile ayni giris) AYNI islemin "kip acik"
sonucunu verir; neden, cikis fiyati ve R karsilastirilir. Kapi 1a ile ayni: medyan |dR| <= 0,001 R, neden uyumu %100.
Her kip icin kipin tetiklendigi ve tetiklenmedigi islemler ayri ayri olculur. Veri sentetik; var/history yok."""
from __future__ import annotations

import statistics as stt
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))
pytest.importorskip("pyarrow")

import exit_modes_parity_support as P  # noqa: E402

from trader_core import exit_counterfactual as EC  # noqa: E402
from trader_core import exit_modes as XM  # noqa: E402

GATE_MEDIAN_R = 0.001           # 1a parite kapisi (docs/cikis-karsi-olgu-spec.md sonu): medyan |dR|
GATE_MAX_R = 0.01               # tek islem ust siniri (sentetik veri; 1 dk <-> 15 dk dolum kaymasi)
PRICE_RTOL = 1e-4


@pytest.fixture(scope="module")
def world(tmp_path_factory):
    """Tek calisma dizini: sentetik tarih + motor kosulari (kapali / basa-bas / kismi / kismi-atlanan) + oynatimlar."""
    root = tmp_path_factory.mktemp("exit_modes_parity")
    tpl = root / "tpl"
    P.make_history(tpl)
    ws = root / "ws"
    ws.mkdir()
    mp = pytest.MonkeyPatch()
    P.setup_workspace(ws, mp, tpl)
    out: dict = {"ws": ws}
    try:
        for name, modes in (("off", None), ("be", {"default": {"breakeven": True}}), ("pt", {"default": {"partial": True}})):
            d = P.run_engine(ws, name, modes)
            tr = P.load_inputs(d, name)
            out[name] = dict(dir=d, trades=tr, rows=P.replay_rows(ws, d, tr, rules_for=P.lot_rules(ws)))
        # kismi adet yuvarlamasi olmadan (tam oran): duzeltme oncesi davranis; testin duyarliligini gosterir
        out["pt_norules"] = dict(rows=P.replay_rows(ws, out["pt"]["dir"], out["pt"]["trades"], tag="_norules"))
        # kismi atlanir: sentetik min adet, kapanacak parcadan buyuk (motor ve oynatim AYNI kurali okur)
        from trader_engine.marketdata.sources import HistoricalSource
        orig = HistoricalSource._synthetic_rules

        def big_min(self, p):
            import dataclasses
            return dataclasses.replace(orig(self, p), min_qty=50.0)
        mp.setattr(HistoricalSource, "_synthetic_rules", big_min)
        d = P.run_engine(ws, "pt_skip", {"default": {"partial": True}})
        tr = P.load_inputs(d, "pt_skip")
        out["pt_skip"] = dict(dir=d, trades=tr, rows=P.replay_rows(ws, d, tr, rules_for=P.lot_rules(ws)))
        yield out
    finally:
        mp.undo()


def _h1(ws: Path) -> pd.DataFrame:
    import pyarrow.feather as pf
    t = pf.read_table(str(ws / "hist" / "BTC_USDT_USDT-1h-futures.feather")).to_pandas()
    return t.set_index("date")


def _reached(h1: pd.DataFrame, tr: EC.TradeInput, trigger_r: float) -> bool:
    """Bagimsiz hesap: giris mumundan cikis dakikasindan ONCE kapanmis 1h mumlarinin en iyi ucu giris +/- trigger_r x R'ye ulasti mi."""
    r = abs(tr.entry_price - tr.initial_stop)
    a = pd.Timestamp(tr.entry_ts).floor("1h")
    b = pd.Timestamp(tr.exit_ts)
    bars = h1[(h1.index >= a) & (h1.index + pd.Timedelta(hours=1) < b)]
    if bars.empty:
        return False
    if tr.side == "long":
        return bool(bars["high"].max() >= tr.entry_price + trigger_r * r - XM.EPS)
    return bool(bars["low"].min() <= tr.entry_price - trigger_r * r + XM.EPS)


def _stats(run: dict, variant: str, subset=None):
    trades = [t for t in run["trades"] if subset is None or subset(t)]
    gaps = [abs(run["rows"][(t.trade_id, variant)]["net_r"] - t.actual_net_r) for t in trades]
    match = sum(run["rows"][(t.trade_id, variant)]["exit_reason_sim"] == t.exit_reason for t in trades)
    px = [abs(P.replay_exit_price(run["rows"][(t.trade_id, variant)], t) - t.exit_price) / t.exit_price for t in trades]
    return dict(n=len(trades), median=stt.median(gaps) if gaps else 0.0, mean=float(np.mean(gaps)) if gaps else 0.0,
                max=max(gaps) if gaps else 0.0, match=match / len(trades) if trades else 1.0, max_px=max(px) if px else 0.0)


def _gate(s: dict, label: str) -> None:
    assert s["n"] >= 1, label
    assert s["match"] == 1.0, (label, s)                    # neden eslesmesi %100
    assert s["median"] <= GATE_MEDIAN_R, (label, s)         # medyan |dR| <= 0,001 R
    assert s["max"] <= GATE_MAX_R, (label, s)
    assert s["max_px"] <= PRICE_RTOL, (label, s)            # cikis fiyati (karma fiyat dahil)


# ----------------------------------------------------------------------------------------------- taban (kip yok)
def test_off_baseline_parity(world):
    """Kip kapali: engine = oynatim `off` (1a kapisi ile ayni olcut; yeni kodun tabani bozmadigi)."""
    run = world["off"]
    assert len(run["trades"]) >= 30
    s = _stats(run, "off")
    _gate(s, "off")
    assert {t.exit_reason for t in run["trades"]} >= {"stop", "trail_stop"}          # sentetik yol iki nedeni de uretir


# ----------------------------------------------------------------------------------------------- basa-bas
def test_breakeven_parity_triggered_and_untriggered(world):
    run, h1 = world["be"], _h1(world["ws"])
    hit = lambda t: _reached(h1, t, XM.BE_TRIGGER_R)          # noqa: E731
    on, off = (lambda t: hit(t)), (lambda t: not hit(t))
    n_on, n_off = sum(map(hit, run["trades"])), sum(not hit(t) for t in run["trades"])
    assert n_on >= 10 and n_off >= 5, (n_on, n_off)
    _gate(_stats(run, "breakeven"), "be/all")
    _gate(_stats(run, "breakeven", on), "be/triggered")
    _gate(_stats(run, "breakeven", off), "be/untriggered")
    assert {t.exit_reason for t in run["trades"]} <= {"stop", "trail_stop", "regime_flip"}      # yeni neden yok


def test_breakeven_replay_rows_never_fire_partial(world):
    run = world["be"]
    assert all(run["rows"][(t.trade_id, "breakeven")]["partial_ts_sim"] is None for t in run["trades"])


# ----------------------------------------------------------------------------------------------- kismi
def test_partial_parity_triggered_and_untriggered(world):
    run, h1 = world["pt"], _h1(world["ws"])
    expected = {t.trade_id for t in run["trades"] if _reached(h1, t, XM.PT_TRIGGER_R)}           # bagimsiz veri hesabi
    fired_replay = {t.trade_id for t in run["trades"] if run["rows"][(t.trade_id, "partial")]["partial_ts_sim"] is not None}
    assert len(expected) >= 8 and len(run["trades"]) - len(expected) >= 5, (len(expected), len(run["trades"]))
    assert expected == fired_replay                                                              # ayni islemlerde tetiklenir
    _gate(_stats(run, "partial"), "pt/all")
    _gate(_stats(run, "partial", lambda t: t.trade_id in expected), "pt/triggered")
    _gate(_stats(run, "partial", lambda t: t.trade_id not in expected), "pt/untriggered")


def test_partial_qty_rounding_is_what_closes_the_gap(world):
    """Duzeltme: kismi adet motorla ayni yuvarlamayla (`exit_modes.partial_qty`). Yuvarlamasiz (tam oran) oynatim tetiklenen
    islemlerde kapidan acikca uzaktir; yuvarlamali oynatim kapida kalir."""
    run, bad = world["pt"], world["pt_norules"]
    fired = lambda t: run["rows"][(t.trade_id, "partial")]["partial_ts_sim"] is not None     # noqa: E731
    with_r = _stats(run, "partial", fired)
    without = _stats({"trades": run["trades"], "rows": bad["rows"]}, "partial", fired)
    assert with_r["median"] <= GATE_MEDIAN_R and with_r["max"] <= GATE_MAX_R
    assert without["max"] > 5 * with_r["max"] and without["max"] > GATE_MAX_R, (with_r, without)
    fr = {run["rows"][(t.trade_id, "partial")]["partial_frac"] for t in run["trades"] if fired(t)}
    t0 = next(t for t in run["trades"] if fired(t))
    assert len(fr) > 1 or fr != {XM.PT_FRAC}                                                  # oran adet yuvarlamasiyla degisti
    assert run["rows"][(t0.trade_id, "partial")]["partial_frac"] == pytest.approx(
        XM.partial_qty(t0.qty, XM.PT_FRAC, 0.001, 0.001, 100.0, 30000.0) / t0.qty, abs=1e-3)


def test_partial_skipped_below_min_qty_equals_engine(world):
    """Kapanan parca min adet altinda: motor kismiyi ATLAR (tek parca surer); oynatim da. Sonuc `off` ile ayni."""
    run = world["pt_skip"]
    assert len(run["trades"]) >= 20
    off = world["off"]                                                                          # kismi hic olmadi: motor sonucu kapali kosuyla AYNI
    assert [(t.entry_ts, t.exit_ts, t.exit_price, t.actual_net_r) for t in run["trades"]] == \
           [(t.entry_ts, t.exit_ts, t.exit_price, t.actual_net_r) for t in off["trades"]]
    assert all(run["rows"][(t.trade_id, "partial")]["partial_ts_sim"] is None for t in run["trades"])
    _gate(_stats(run, "partial"), "pt_skip")
    for t in run["trades"]:
        a, b = run["rows"][(t.trade_id, "partial")], run["rows"][(t.trade_id, "off")]
        assert a["net_r"] == b["net_r"] and a["exit_reason_sim"] == b["exit_reason_sim"]


# ----------------------------------------------------------------------------------------------- kipin etkisi (acik - kapali)
@pytest.mark.parametrize("name,variant", [("be", "breakeven"), ("pt", "partial")])
def test_mode_effect_delta_matches_engine(world, name, variant):
    """Ayni giris (zaman, yon, fiyat) iki motor kosusunda da varsa: motorun R farki (kip acik - kapali) = oynatimin Delta_r'si."""
    on, off = world[name], world["off"]
    key = lambda t: (t.entry_ts, t.side, t.entry_price)           # noqa: E731
    base = {key(t): t for t in off["trades"]}
    pairs = [(t, base[key(t)]) for t in on["trades"] if key(t) in base]
    assert len(pairs) >= 15
    diffs, nonzero = [], 0
    for t_on, t_off in pairs:
        eng = t_on.actual_net_r - t_off.actual_net_r
        rep = on["rows"][(t_on.trade_id, variant)]["net_r"] - on["rows"][(t_on.trade_id, "off")]["net_r"]
        diffs.append(abs(eng - rep))
        nonzero += abs(eng) > 0.01
    assert nonzero >= 3                                              # kip gercekten sonuc degistirdi (anlamli test)
    assert stt.median(diffs) <= GATE_MEDIAN_R and max(diffs) <= GATE_MAX_R, (stt.median(diffs), max(diffs))
