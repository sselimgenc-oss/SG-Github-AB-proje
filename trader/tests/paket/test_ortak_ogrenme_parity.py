"""Ortak ogrenme paketi ile ML (trader_core.trade_notes) esdegerligi (spec bolum 4).

Adaptor: ML TradeRecord/DecisionRecord -> Aday. Bu dosyadaki `aday_from_ml` ayni dönusumun referans hali.
Bilinen fark: Aday'da exit_ts yoktur; ML lesson_effect ayrica exit_ts < as_of ister. Testler bu farkin
devreye girmedigi veriyle kurulur (cikis, karar as_of'tan once).
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from trader_core import trade_notes as TN
from trader_core.ledger import DecisionRecord, TradeRecord

from ortak_ogrenme import ders, notlar
from ortak_ogrenme.kayit import Aday

T0 = datetime(2026, 5, 2, 12, 0, tzinfo=timezone.utc)


def _dec(i, *, setup="T1", session="open", atr=1.0, feats=None, ts=T0, regime="trend_up"):
    f = {"stop_dist_atr": 2.0, "rr": 2.5}
    f.update(feats or {})
    return DecisionRecord(
        id=i, bot="ml", bar_close_ts=ts, trigger_tf="1h", pair="BTC/USDT", side="long", setup=setup,
        regime=regime, atr_ratio=atr, rh=None, rl=None, rh_touches=0, rl_touches=0, features=f,
        planned_entry=100.0, planned_stop=99.0, planned_target=None, param_version_id=1, veto_status="ok",
        veto_reason=None, risk_allowed=True, risk_reason=None, size_qty=1.0, size_notional=None,
        size_margin=None, size_risk_amount=None, leverage=1, final_action="entered", skip_reason=None,
        supersedes_id=None, recorded_at=ts, activation_id=None, session_tag=session)


def _trade(i, dec, r, *, setup=None, regime=None, entry=100.0, planned_entry=100.0, planned_stop=99.0,
           exit_ts=None, mfe=0.5, mae=-0.2, bars=3, reason="stop"):
    entry_ts = dec.bar_close_ts + timedelta(minutes=5)
    return TradeRecord(
        trade_id=i, decision_id=dec.id, pair="BTC/USDT", side="long", setup=setup or dec.setup,
        regime=regime or dec.regime, atr_ratio=dec.atr_ratio, param_version_id=1, activation_id=None,
        entry_ts=entry_ts, entry_price=entry, planned_entry=planned_entry, planned_stop=planned_stop,
        planned_target=None, qty=1.0, leverage=1, planned_risk=1.0, fee_entry=0.0, slippage_entry=0.0,
        exit_ts=exit_ts or (entry_ts + timedelta(hours=2)), exit_price=100.0 + r, exit_reason=reason,
        planned_exit=None, fee_exit=0.0, funding_paid=0.0, gross_pnl=r, realized_pnl=r, r_multiple=r,
        slippage_exit=0.0, mfe_r=mfe, mae_r=mae, bars_held=bars)


def aday_from_ml(t: TradeRecord, d: DecisionRecord | None) -> Aday:
    """Referans adaptor: ML kaydi -> Aday. ML'de yuksek_vol dec.atr_ratio alanini, rr/stop_dist_atr features'i okur."""
    oz = dict(d.features or {}) if d is not None else {}
    if d is not None and d.atr_ratio is not None:
        oz["atr_ratio"] = d.atr_ratio
    else:
        oz.pop("atr_ratio", None)
    return Aday(
        id=str(t.trade_id), proje="ML", kurulum=t.setup, enstruman=t.pair, varlik_sinifi="kripto",
        yon=t.side, ts=(d.bar_close_ts if d is not None else t.entry_ts), alindi=True, r=t.r_multiple,
        seans=(d.session_tag if d is not None else None), rejim=t.regime, ozellikler=oz,
        cikis={"entry_price": t.entry_price, "planned_entry": t.planned_entry, "planned_stop": t.planned_stop,
               "exit_reason": t.exit_reason, "bars_held": t.bars_held, "mfe_r": t.mfe_r, "mae_r": t.mae_r})


# (ad, trade kwargs, dec kwargs, dec_var_mi)
NOT_SENARYOLARI = [
    ("kazanc_temiz", dict(r=1.5), dict(), True),
    ("basabas", dict(r=0.0), dict(), True),
    ("kayip_ders_hepsi", dict(r=-1.2), dict(session="closed", atr=1.4, feats={"rr": 1.5, "stop_dist_atr": 0.5},
                                            regime="range"), True),
    ("kayip_uyumsuz_r1_trend", dict(r=-0.8, setup="R1", regime="trend_up"), dict(setup="R1", regime="trend_up"), True),
    ("kayip_kotu_dolum", dict(r=-1.0, entry=101.5), dict(), True),
    ("kayip_dec_yok", dict(r=-1.0, entry=101.5), None, False),
    ("kazanc_dec_yok", dict(r=2.0), None, False),
    ("stop_genis", dict(r=0.4), dict(feats={"stop_dist_atr": 3.5}), True),
    ("stop_yok", dict(r=0.4), dict(feats={"stop_dist_atr": None}), True),
    ("rejim_bilinmeyen", dict(r=-0.5, regime="chop"), dict(regime="chop"), True),
    ("kurulum_bilinmeyen", dict(r=-0.5, setup="X9"), dict(setup="X9", session="weekend"), True),
    ("weekend_seans", dict(r=-0.5), dict(session="weekend", atr=1.0), True),
    ("seans_yok", dict(r=-0.5), dict(session=None), True),
    ("nan_rr", dict(r=-0.5), dict(feats={"rr": float("nan")}, atr=1.3), True),
    ("sinir_atr_1_3_ve_rr_2_0", dict(r=-0.5), dict(atr=1.3, feats={"rr": 2.0}), True),
    ("stop_sinir_1_0", dict(r=0.1), dict(feats={"stop_dist_atr": 1.0}), True),
    ("kayma_sinir_0_10", dict(r=-0.5, entry=100.9), dict(), True),
    ("kayip_dusuk_rr_bar_yok", dict(r=-2.0, planned_stop=98.0), dict(feats={"rr": 1.0}), True),
]


@pytest.mark.parametrize("ad,tk,dk,dec_var", NOT_SENARYOLARI, ids=[s[0] for s in NOT_SENARYOLARI])
def test_not_etiketleri_ml_ile_ayni(ad, tk, dk, dec_var):
    dec = _dec(1, **dk) if dec_var else None
    trade = _trade(10, dec if dec is not None else _dec(1), **tk)
    ml_tags, _ = TN.build_note(trade, dec)
    tags, metin = notlar.not_yaz(aday_from_ml(trade, dec))
    assert tags == ml_tags
    assert "\n" not in metin


def test_not_yaz_alinmamis_veya_r_yok_reddeder():
    base = aday_from_ml(_trade(1, _dec(1), r=-1.0), _dec(1))
    from dataclasses import replace
    with pytest.raises(ValueError):
        notlar.not_yaz(replace(base, alindi=False))
    with pytest.raises(ValueError):
        notlar.not_yaz(replace(base, r=None))


class FakeLedger:
    """trade_notes.lesson_effect'in kullandigi minimum yuzey."""
    LIST_CLOSED_MAX = 10000

    def __init__(self, trades, decisions):
        self._trades = list(trades)
        self._decisions = list(decisions)

    def list_closed_trades(self, since=None, until=None, limit=200):
        return sorted(self._trades, key=lambda t: (t.exit_ts, t.trade_id), reverse=True)[:limit]

    def list_decisions(self, *, since_ts=None, until_ts=None, setup=None, final_action=None, limit=None):
        out = []
        for d in self._decisions:
            if since_ts is not None and d.bar_close_ts < since_ts:
                continue
            if until_ts is not None and d.bar_close_ts >= until_ts:
                continue
            if final_action is not None and d.final_action != final_action:
                continue
            out.append(d)
        return out

    def get_decision(self, decision_id):
        return next(d for d in self._decisions if d.id == decision_id)

    def list_trade_notes(self):
        return []


def _defter():
    """Dogum 2026-05-01; karar/islem 2026-05-02..09 arasi; as_of 2026-05-10 00:00 UTC."""
    trades, decs = [], []
    base = datetime(2026, 5, 2, 9, 0, tzinfo=timezone.utc)
    spec = [
        # (karar_ek_saat, setup, session, atr, feats, r, regime)
        (0, "T1", "closed", 1.5, {"rr": 1.8}, -1.0, "trend_up"),
        (24, "T1", "closed", 1.0, {"rr": 3.0}, 0.5, "trend_up"),
        (48, "T1", "open", 1.4, {"rr": 1.5}, -0.7, "trend_down"),
        (72, "T1", "weekend", 1.1, {"rr": 2.5}, -0.2, "trend_up"),
        (96, "T1", "open", 1.0, {"rr": 2.2}, 1.2, "trend_up"),
        (120, "R1", "closed", 1.6, {"rr": 1.0}, -0.9, "range"),
        (144, "T1", "closed", 0.9, {"rr": 1.9}, -0.4, "trend_down"),
        (168, "T1", "open", 1.35, {"rr": 2.1}, 0.3, "trend_up"),
    ]
    for i, (dk, setup, sess, atr, feats, r, reg) in enumerate(spec, start=1):
        d = _dec(i, setup=setup, session=sess, atr=atr, feats=feats, ts=base + timedelta(hours=dk), regime=reg)
        decs.append(d)
        trades.append(_trade(100 + i, d, r, exit_ts=d.bar_close_ts + timedelta(hours=3)))
    # Alinmamis karar (sayilmamali)
    decs.append(DecisionRecord(**{**decs[0].__dict__, "id": 99, "final_action": "skipped",
                                  "bar_close_ts": base + timedelta(hours=30)}))
    # Dogum gununde (ertesi gunden once) ve as_of'tan sonra karar (sayilmamali)
    decs.append(_dec(50, setup="T1", session="closed", atr=1.5, feats={"rr": 1.0},
                     ts=datetime(2026, 5, 1, 20, 0, tzinfo=timezone.utc)))
    trades.append(_trade(150, decs[-1], -3.0, exit_ts=datetime(2026, 5, 1, 23, 0, tzinfo=timezone.utc)))
    decs.append(_dec(51, setup="T1", session="closed", atr=1.5, feats={"rr": 1.0},
                     ts=datetime(2026, 5, 10, 1, 0, tzinfo=timezone.utc)))
    trades.append(_trade(151, decs[-1], -3.0, exit_ts=datetime(2026, 5, 10, 4, 0, tzinfo=timezone.utc)))
    return trades, decs


@pytest.mark.parametrize("shrink_n", [0, 10])
@pytest.mark.parametrize("lid", ["seans_kapali:T1", "yuksek_vol:T1", "dusuk_rr:T1", "seans_kapali:R1",
                                 "dusuk_rr:X9"])
def test_ders_etkisi_ml_ile_ayni(lid, shrink_n):
    trades, decs = _defter()
    led = FakeLedger(trades, decs)
    as_of = datetime(2026, 5, 10, tzinfo=timezone.utc)
    dogum = "2026-05-01"
    adaylar = [aday_from_ml(t, next(d for d in decs if d.id == t.decision_id)) for t in trades
               if next(d for d in decs if d.id == t.decision_id).final_action == "entered"]
    ml_eff, ml_n = TN.lesson_effect(led, lid, dogum, as_of, shrink_n)
    eff, n = ders.ders_etkisi(adaylar, lid, dogum, as_of, shrink_n)
    assert n == ml_n
    assert eff == pytest.approx(ml_eff, abs=1e-9)
