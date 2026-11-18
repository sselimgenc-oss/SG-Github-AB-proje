#!/usr/bin/env python3
"""WP-B7: Binance vadeli TESTNET yoklama (B0), duman (T-13..T-16) ve tatbikat (D-1..D-8) adimlari (11 §11).

Yalniz testnet. `--env live` reddedilir; taban adres sabit izin listesinde olmali (smoke_testnet_lib.ALLOWED_BASES).
Anahtarlar yalniz BINANCE_API_KEY / BINANCE_API_SECRET ortam degiskenlerinden okunur, hicbir yere yazilmaz.
Tek cift, asgari miktar, en fazla 1 acik pozisyon; her kosu sonunda (finally) kendi acik emirleri iptal edilir ve
pozisyon duzlenir. Motor kodu degistirilmez/ice alinmaz: yalniz genel giris noktalari (LiveBroker, SignedRestClient, CLI).

Ornek:  python scripts/smoke_testnet.py --env testnet --step b0-preflight --dry-run
Cikis: 0 tum adimlar GECTI/ATLANDI; 1 KALDI/FARKLI var; 2 guvenlik korkuluguna takildi / kullanim hatasi.
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import ROUND_FLOOR, Decimal
from pathlib import Path
from typing import Any, Callable

_HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(_HERE.parent / "src"))
sys.path.insert(0, str(_HERE))

import smoke_testnet_lib as S  # noqa: E402

UTC = timezone.utc
DEFAULT_PAIR = "XRP/USDT"
OURS_PREFIX = "tr"          # order_manager.make_client_id oneki


# ---------------------------------------------------------------------------------------------- baglam
class Ctx:
    def __init__(self, *, rest, broker, clock, pair, cfg, args, input_fn=input, say=print, runner=subprocess.run,
                 on_wait: Callable[[], None] | None = None):
        self.rest, self.broker, self.clock, self.pair, self.cfg, self.args = rest, broker, clock, pair, cfg, args
        self.sym = pair.replace("/", "")
        self.input_fn, self.say, self.runner, self.on_wait = input_fn, say, runner, on_wait
        self.seq = 0
        self.t0 = clock.now().replace(microsecond=0)
        self.rules = broker.rules(pair)
        self.qty = float(S.min_order_qty(self.rules.min_qty, self.rules.step, self.rules.min_notional,
                                         float(rest.mark_price(self.sym))))
        self.notes: list[str] = []
        self.opened = False          # yalniz kendi actigimiz pozisyon duzlestirilir

    # kimlikler order_manager ile ayni biçimde -> LiveBroker onlari "kendi" tanir
    def cid(self, role: str) -> str:
        from trader_engine.order_manager import make_client_id
        self.seq += 1
        return make_client_id("learner", role, self.pair, "long", self.t0, self.seq)

    def now(self):
        return self.clock.now()

    def mark(self) -> Decimal:
        return self.rest.mark_price(self.sym)

    def round_tick(self, px: Decimal) -> float:
        t = Decimal(str(self.rules.tick))
        return float((px / t).to_integral_value(rounding=ROUND_FLOOR) * t)

    def positions_all(self) -> list:
        return [p for p in self.broker.positions()]

    def pos_qty(self) -> Decimal:
        rows = self.rest.position_risk(self.sym)
        return sum((Decimal(str(r["positionAmt"])) for r in rows), Decimal(0))

    def require_flat(self) -> None:
        """En fazla 1 acik pozisyon: baska pozisyon varken yenisi acilmaz."""
        rows = [r for r in self.rest.position_risk() if Decimal(str(r["positionAmt"])) != 0]
        if rows:
            raise S.SafetyError("hesapta zaten acik pozisyon var; yeni pozisyon acilmaz")

    def open_long(self, qty: float | None = None):
        from trader_engine.types import OrderRequest
        self.require_flat()
        self.broker.prepare(self.pair, int(self.cfg.leverage))
        r = self.broker.market_order(OrderRequest(client_id=self.cid("entry"), pair=self.pair, role="entry", order_side="buy",
                                                  qty=qty or self.qty, trigger_price=None, reduce_only=False,
                                                  leverage=int(self.cfg.leverage), created_ts=self.now()))
        self.opened = True
        self.broker.register_position(self.pair, self.now())
        return r

    def stop(self, pct: float, qty: float | None = None, role: str = "stop"):
        from trader_engine.types import OrderRequest
        trig = self.round_tick(self.mark() * (Decimal(1) - Decimal(str(pct))))
        cid = self.cid(role)
        r = self.broker.place_stop(OrderRequest(client_id=cid, pair=self.pair, role=role, order_side="sell",
                                                qty=qty or self.qty, trigger_price=trig, reduce_only=True, leverage=None,
                                                created_ts=self.now()))
        return cid, trig, r

    def conditionals(self) -> list[dict]:
        return self.rest.open_conditionals(self.sym)

    def open_positions(self) -> list[dict]:
        """Hesap geneli (tum semboller) sifirdan farkli pozisyon satirlari (T-15 / R1)."""
        return [r for r in self.rest.position_risk() if Decimal(str(r["positionAmt"])) != 0]

    def last_price(self) -> Decimal | None:
        """Son islem fiyati (best-effort; okunamazsa None). Tetik gozleminde mark ile birlikte kaydedilir (R4)."""
        try:
            r = self.rest.request("GET", "/fapi/v1/ticker/price", {"symbol": self.sym}, kind="read", signed=False)
            return Decimal(str(r["price"]))
        except Exception:  # noqa: BLE001
            return None

    def observe(self) -> dict:
        return {"mark": self.mark(), "last": self.last_price()}

    def watch_trigger(self, trig: float, timeout_s: float, every_s: float = 2.0) -> tuple[float | None, list[dict]]:
        """Pozisyon duzlenene kadar bekler; her turda (mark, son fiyat) orneklenir (R4). (gecen_sn | None, ornekler)."""
        samples: list[dict] = []

        def pred() -> bool:
            samples.append(self.observe())
            return self.pos_qty() == 0
        return self.wait_until(pred, timeout_s, every_s), samples

    def wait_until(self, pred: Callable[[], bool], timeout_s: float, every_s: float = 1.0) -> float | None:
        t = 0.0
        while t <= timeout_s:
            if pred():
                return t
            if self.on_wait:
                self.on_wait()
            self.clock.sleep(every_s)
            t += every_s
        return None

    def confirm(self, text: str) -> None:
        self.say(text)
        self.input_fn("Bitince Enter: ")


def _cid_of(row: dict) -> str:
    return str(row.get("clientAlgoId") or row.get("clientOrderId") or "")


def _stops(ctx: Ctx) -> list[dict]:
    return [r for r in ctx.conditionals() if _cid_of(r).startswith(OURS_PREFIX)]


def _stops_all(ctx: Ctx) -> list[dict]:
    """Hesap geneli kendi (tr-onekli) kosullu emirleri."""
    return [r for r in ctx.rest.open_conditionals() if _cid_of(r).startswith(OURS_PREFIX)]


def trigger_verdict(samples: list[dict], trig: float) -> tuple[bool | None, dict]:
    """R4: long'un SELL stop'u icin mark <= tetik gozlendi mi. (mark_gecti | None=gozlem yok, veri). Son fiyat yalniz kayit."""
    marks = [x["mark"] for x in samples if x.get("mark") is not None]
    if not marks:
        return None, {}
    t = Decimal(str(trig))
    crossed = any(m <= t for m in marks)
    last = samples[-1]
    first_cross = next((x for x in samples if x["mark"] <= t), last)
    lasts = [x["last"] for x in samples if x.get("last") is not None]
    data = {"tetik": str(trig), "mark_son": str(last["mark"]), "mark_min": str(min(marks)),
            "son_fiyat_son": None if last.get("last") is None else str(last["last"]),
            "son_fiyat_min": str(min(lasts)) if lasts else None,
            "mark_esik_gecis_ornegi": {"mark": str(first_cross["mark"]),
                                       "son_fiyat": None if first_cross.get("last") is None else str(first_cross["last"])}
            if crossed else None,
            "son_fiyat_once_gecti": bool(lasts) and any(x.get("last") is not None and x["last"] <= t and x["mark"] > t
                                                         for x in samples)}
    return crossed, data


def _R(status: str, *notes: str, **data) -> tuple[str, list[str], dict]:
    return status, list(notes), data


# ---------------------------------------------------------------------------------------------- B0 yoklama
def b0_preflight(ctx: Ctx):
    rest = ctx.rest
    off = rest.sync_time()
    acct = rest.account()
    rows = [r for r in rest.position_risk() if Decimal(str(r["positionAmt"])) != 0]
    oo = rest.open_orders(ctx.sym) + rest.open_conditionals(ctx.sym)
    cr = rest.commission_rate(ctx.sym)
    st = "GECTI" if not rows and not oo else "KALDI"
    return _R(st, f"saat_ofseti_ms={off}", f"acik_pozisyon={len(rows)}", f"acik_emir={len(oo)}",
              wallet=str(acct.get("totalWalletBalance")), taker=cr.get("takerCommissionRate"),
              min_qty=ctx.qty, one_way=not rest.position_mode(), multi_assets=rest.multi_assets())


def b0_t01(ctx: Ctx):
    ctx.open_long()
    cid, trig, r = ctx.stop(0.05)
    rows = ctx.conditionals()
    mine = [x for x in rows if _cid_of(x) == cid]
    st = "GECTI" if r.status == "accepted" and mine else "FARKLI"
    return _R(st, f"mod={ctx.rest.conditional_mode}", f"yanit_durum={r.status}", f"alanlar={sorted(mine[0]) if mine else None}",
              order_id=r.order_id)


def b0_t02(ctx: Ctx):
    from trader_engine.exchange.binance_rest import ExchangeReject
    rest, notes = ctx.rest, []
    rest.set_one_way(); rest.set_isolated(ctx.sym); rest.set_leverage(ctx.sym, int(ctx.cfg.leverage))
    rest.set_isolated(ctx.sym); rest.set_leverage(ctx.sym, int(ctx.cfg.leverage))      # 2. cagri: -4046/-4059 sessiz
    pr = rest.position_risk(ctx.sym)[0]
    ok = str(pr.get("marginType", "")).lower() == "isolated" and str(pr.get("leverage")) == str(int(ctx.cfg.leverage))
    ctx.open_long()
    codes = {}
    for label, path, p in (("marginType_cross", "/fapi/v1/marginType", {"symbol": ctx.sym, "marginType": "CROSSED"}),
                           ("leverage_dusur", "/fapi/v1/leverage", {"symbol": ctx.sym, "leverage": 2})):
        try:
            rest.request("POST", path, p, kind="setup")
            codes[label] = "kabul"
        except ExchangeReject as e:
            codes[label] = e.code
    notes.append(f"pozisyonlu_ret_kodlari={codes}")
    return _R("GECTI" if ok else "KALDI", *notes, marginType=pr.get("marginType"), leverage=pr.get("leverage"), codes=codes)


def b0_t03(ctx: Ctx):
    ctx.open_long()
    cid, trig, r = ctx.stop(0.01)
    row = next((x for x in ctx.conditionals() if _cid_of(x) == cid), {})
    wt = row.get("workingType")
    return _R("GECTI" if wt == "MARK_PRICE" else "FARKLI", f"workingType={wt}",
              "yalniz alan dogrulandi (tetik zamanlamasi gozlemi bu adimda yok)", trigger=trig)


def _fate(row: dict | None) -> str:
    if row is None:
        return "yok(-2013)"
    return str(row.get("algoStatus") or row.get("status") or "?")


def b0_t04(ctx: Ctx):
    """T-04 [V-3]: ayni pozisyona iki reduceOnly stop; biri tetiklenince digerinin akibeti kaydedilir."""
    ctx.open_long()
    far_cid, far_trig, fr = ctx.stop(0.05)
    tight_cid, tight_trig, tr = ctx.stop(float(ctx.args.t13_stop_pct))
    if fr.status != "accepted" or tr.status != "accepted":
        return _R("FARKLI", f"iki_stop_kabul: gevsek={fr.status} siki={tr.status} (11 §6.6 son satiri devreye girer; mentor karari)",
                  gevsek=fr.status, siki=tr.status)
    n = len(_stops(ctx))
    gone, samples = ctx.watch_trigger(tight_trig, float(ctx.args.trigger_wait_s), 2.0)
    crossed, mdata = trigger_verdict(samples, tight_trig)
    if gone is None:
        return _R("BEKLEMEDE", f"iki stop kabul edildi (sayi={n}); siki stop bekleme suresinde tetiklenmedi: akibet gozlenemedi "
                  "(--trigger-wait-s artirin)", iki_stop_kabul=True, **mdata)
    fate = _fate(ctx.rest.query_conditional(ctx.sym, far_cid))
    left = [_cid_of(x) for x in _stops(ctx)]
    st = "GECTI" if crossed is not False else "FARKLI"
    return _R(st, f"iki_stop_kabul=True stop_sayisi={n}", f"gevsek_stopun_akibeti={fate}", f"tetikten_sonra_acik_stop={len(left)}",
              *(["mark esigi gecmeden tetiklendi (FARKLI)"] if crossed is False else []), iki_stop_kabul=True,
              gevsek_akibet=fate, acik_stop_sonra=len(left), **mdata)


def b0_t05(ctx: Ctx):
    from trader_engine.exchange.binance_rest import ExchangeReject
    out = {}
    try:   # (a) pozisyonsuz reduceOnly stop
        ctx.rest.new_conditional(ctx.sym, "STOP_MARKET", "SELL", ctx.qty, ctx.round_tick(ctx.mark() * Decimal("0.95")),
                                 ctx.cid("stop"), "MARK_PRICE")
        out["a_pozisyonsuz_stop"] = "kabul"
    except ExchangeReject as e:
        out["a_pozisyonsuz_stop"] = e.code
    ctx.open_long()
    try:   # (b) pozisyondan buyuk reduceOnly piyasa
        r = ctx.rest.new_market(ctx.sym, "SELL", float(Decimal(str(ctx.qty)) * 2), ctx.cid("exit"), True)
        out["b_buyuk_reduceonly"] = {"status": r.get("status"), "executedQty": r.get("executedQty")}
    except ExchangeReject as e:
        out["b_buyuk_reduceonly"] = e.code
    return _R("GECTI", f"sonuclar={out}", **out)   # yoklama: gozlem kaydedilir, yorum 11-testnet-sonuc.md'de


def b0_t06(ctx: Ctx):
    from trader_engine.exchange.binance_rest import ExchangeReject
    ctx.open_long()
    trig = ctx.round_tick(ctx.mark() * Decimal("1.01"))     # long'un SELL stop'u mark ustunde: hemen tetiklenir
    try:
        r = ctx.rest.new_conditional(ctx.sym, "STOP_MARKET", "SELL", ctx.qty, trig, ctx.cid("stop"), "MARK_PRICE")
        res = f"kabul:{r.get('status') or r.get('algoStatus')}"
    except ExchangeReject as e:
        res = f"ret:{e.code}"
    return _R("GECTI", f"hemen_tetik_sonucu={res}", result=res)


def b0_t07(ctx: Ctx):
    """T-07 [V-7]: tetiklenen stop <-> gercek (cocuk) emir <-> userTrades; likidasyon sorgulanabilirligi yalniz okunur."""
    t_ms = int(ctx.now().timestamp() * 1000) - 5000
    ctx.open_long()
    cid, trig, _ = ctx.stop(float(ctx.args.t13_stop_pct))
    gone, samples = ctx.watch_trigger(trig, float(ctx.args.trigger_wait_s), 2.0)
    if gone is None:
        return _R("BEKLEMEDE", "stop bekleme suresinde tetiklenmedi (--trigger-wait-s artirin / --t13-stop-pct daraltin)")
    _, mdata = trigger_verdict(samples, trig)
    row = ctx.rest.query_conditional(ctx.sym, cid) or {}
    oid = row.get("actualOrderId") or row.get("orderId")
    child = ctx.rest.query_order_by_id(ctx.sym, oid) if oid not in (None, "", 0, "0") else None
    trades = [t for t in ctx.rest.user_trades(ctx.sym, t_ms) if oid is not None and str(t.get("orderId")) == str(oid)]
    ccid = (child or {}).get("clientOrderId")
    force = ctx.rest.force_orders(ctx.sym, t_ms)
    data = {"algo_alanlari": sorted(row), "gercek_emir_id": oid, "cocuk_clientOrderId": ccid,
            "cocuk_kimlik_modu": "same" if ccid == cid else "auto", "userTrades_eslesen": len(trades),
            "commission": [t.get("commission") for t in trades], "commissionAsset": sorted({str(t.get("commissionAsset")) for t in trades}),
            "realizedPnl": [t.get("realizedPnl") for t in trades], "forceOrders_satir": len(force),
            "forceOrders_alanlari": sorted(force[0]) if force else None,
            "liquidation_queryable": "gozlenemedi (testnette likidasyon uretilmez)"}
    ok = bool(oid) and child is not None and bool(trades)
    return _R("GECTI" if ok else "FARKLI", f"cocuk_clientOrderId={ccid} (stop kimligiyle {'AYNI' if ccid == cid else 'FARKLI/otomatik'})",
              f"userTrades_eslesen={len(trades)}", "likidasyon sorgulanabilirligi testnette gozlenemez (fake_exchange kaniti)", **data, **mdata)


def b0_t08(ctx: Ctx):
    """T-08 [V-5]: kimlik tekrari ve belirsizlik; yalniz gozlem (kabul/ret kodu kaydedilir)."""
    from trader_engine.exchange.binance_rest import ExchangeReject
    rest, out = ctx.rest, {}
    r = ctx.open_long()
    scid, trig, _ = ctx.stop(0.03)
    try:    # (a) acik emirle ayni kimlik
        rest.new_conditional(ctx.sym, "STOP_MARKET", "SELL", ctx.qty, trig, scid, "MARK_PRICE")
        out["a_acik_emirle_ayni_kimlik"] = "kabul"
    except ExchangeReject as e:
        out["a_acik_emirle_ayni_kimlik"] = e.code
    try:    # (b) dolmus piyasa emrinin kimligiyle ikinci emir (reduceOnly: ters pozisyon acilamaz)
        rr = rest.new_market(ctx.sym, "SELL", ctx.qty, r.client_id, True)
        out["b_dolmus_kimlikle_ikinci"] = f"kabul:{rr.get('status')}"
    except ExchangeReject as e:
        out["b_dolmus_kimlikle_ikinci"] = e.code
    old = rest.read_timeout_s       # (c) 1 ms okuma suresi: istemci zaman asimi; sonra kimlikle sorgu
    try:
        rest.read_timeout_s = 0.001
        try:
            rest.query_order(ctx.sym, r.client_id, attempts=1)
            out["c_zaman_asimi"] = "zaman asimi olusmadi"
        except Exception as e:  # noqa: BLE001
            out["c_zaman_asimi"] = type(e).__name__
    finally:
        rest.read_timeout_s = old
    found = rest.query_order(ctx.sym, r.client_id)
    t1 = time.monotonic()
    missing = rest.query_order(ctx.sym, OURS_PREFIX + "Lx-yok-" + str(int(t1)))
    out["c_kimlikle_sorgu_buldu"] = found is not None
    out["c_yok_yaniti_sn"] = round(time.monotonic() - t1, 3)
    out["c_yok_yaniti_bos"] = missing is None
    return _R("GECTI" if found is not None and missing is None else "FARKLI",
              f"sonuclar={out}", "kabulse max_attempts=1 kalicidir (11 §11 T-08)", **out)


def b0_t09(ctx: Ctx):
    from trader_engine.exchange.binance_rest import ExchangeReject
    out = {}
    for label, q in (("min_notional_alti", Decimal(str(ctx.rules.step))), ("adim_disi", Decimal(str(ctx.qty)) + Decimal(str(ctx.rules.step)) / 10)):
        try:
            r = ctx.rest.new_market(ctx.sym, "BUY", float(q), ctx.cid("entry"), False)
            out[label] = f"kabul:{r.get('status')}"
        except ExchangeReject as e:
            out[label] = e.code
    return _R("GECTI", f"ret_kodlari={out}", **out)


def b0_t10(ctx: Ctx):
    t_ms = int(ctx.now().timestamp() * 1000)
    r = ctx.open_long()
    since = t_ms - 5000
    trades = [t for t in ctx.rest.user_trades(ctx.sym, since) if str(t.get("orderId")) == str(r.order_id)]
    fee = sum((Decimal(str(t.get("commission", 0))) for t in trades), Decimal(0))
    rate = Decimal(str(ctx.rest.commission_rate(ctx.sym).get("takerCommissionRate", 0)))
    exp = Decimal(str(r.avg_price or 0)) * Decimal(str(r.filled_qty)) * rate
    ok = r.status == "filled" and (exp == 0 or abs(fee - exp) / exp < Decimal("0.01"))
    return _R("GECTI" if ok else "FARKLI", f"durum={r.status}", f"komisyon={fee} beklenen={exp}")


def b0_t11(ctx: Ctx):
    ctx.rest.account()
    cnt = dict(getattr(ctx.rest, "_hdr_cnt", {}))
    w = getattr(ctx.rest, "_used_weight", None)
    return _R("GECTI" if w else "FARKLI", f"used_weight_1m={w}", f"emir_sayaclari={sorted(cnt)}")


def b0_t12(ctx: Ctx):
    """T-12: yalniz OKUMA; funding gelir kaydi gozlenir (pozisyon acilmaz). Engelleyici DEGIL (durum GOZLEM)."""
    now_ms = int(ctx.now().timestamp() * 1000)
    rows = ctx.rest.income(ctx.sym, "FUNDING_FEE", now_ms - 3 * 86400 * 1000, now_ms)
    rows = list(rows) if isinstance(rows, list) else []
    last = rows[-1] if rows else None
    return _R("GOZLEM", f"son_3_gun_FUNDING_FEE_satir={len(rows)}",
              "funding anini gecen bir pozisyonla isaret (odenen negatif) ve gecikme elle dogrulanir (11 §11 T-12); engelleyici degil",
              satir=len(rows), son=None if last is None else {k: last.get(k) for k in ("income", "asset", "time")})


# ---------------------------------------------------------------------------------------------- T-13..T-16
def t13(ctx: Ctx):
    notes, data = [], {}
    t_fill = ctx.now()
    r = ctx.open_long()
    if r.status != "filled":
        return _R("KALDI", f"giris_durum={r.status}")
    cid, trig, sr = ctx.stop(0.02)
    gap = (ctx.now() - t_fill).total_seconds()
    data["stop_gecikme_s"] = gap
    notes.append(f"giris->stop={gap:.2f}s (sinir 10, hedef <2)")
    ok = sr.status == "accepted" and gap <= 10
    for i in range(2):          # iz suren stop: yeni once, sonra eski iptal
        new_cid, new_trig, nr = ctx.stop(0.02 - 0.005 * (i + 1))
        if nr.status != "accepted":
            return _R("KALDI", *notes, f"sikilastirma_{i + 1}_reddedildi")
        ctx.broker.cancel(ctx.pair, cid)
        cid = new_cid
    left = [_cid_of(x) for x in _stops(ctx)]
    notes.append(f"sikilastirma_sonrasi_stop_sayisi={len(left)}")
    ok = ok and left == [cid]
    # tetik: son stop mark'a cok yakin (--t13-stop-pct); belirli sure beklenir (--trigger-wait-s)
    tight_cid, tight_trig, _ = ctx.stop(float(ctx.args.t13_stop_pct))
    ctx.broker.cancel(ctx.pair, cid)
    gone, samples = ctx.watch_trigger(tight_trig, float(ctx.args.trigger_wait_s), 2.0)
    crossed, mdata = trigger_verdict(samples, tight_trig)
    data.update(mdata)
    if gone is None:
        notes.append("stop bekleme suresinde tetiklenmedi; kosu sonu temizligi duzlestirecek (T-13 tamamlanmadi; "
                     "--trigger-wait-s artirin / --t13-stop-pct daraltin)")
        return _R("BEKLEMEDE", *notes, **data)
    evs = ctx.broker.poll(ctx.now())
    kinds = [e.kind for e in evs]
    notes.append(f"olaylar={kinds}")
    notes.append(f"tetik_ani mark={mdata.get('mark_son')} son_fiyat={mdata.get('son_fiyat_son')} tetik={mdata.get('tetik')}")
    ev_ok = "fill" in kinds or bool(ctx.broker.closing_events(ctx.pair, t_fill, [tight_cid]))
    orphan = ctx.rest.open_orders(ctx.sym) + ctx.rest.open_conditionals(ctx.sym)
    notes.append("neden 'trail_stop' defter kaydi motor tarafindadir; burada yalniz kapanis olayi + yetim emir yok denetlenir")
    if crossed is False:
        notes.append("FARKLI: stop mark esigi gecilmeden tetiklendi (MARK_PRICE varsayimi dogrulanmadi)")
        return _R("FARKLI", *notes, orphans=len(orphan), **data)
    return _R("GECTI" if ok and ev_ok and not orphan else "KALDI", *notes, orphans=len(orphan), **data)


def t14(ctx: Ctx):
    n = int(ctx.args.partial_fill_multiple or 0)
    if n <= 1:
        return _R("ATLANDI", "asgari miktar kuraliyla kismi dolum uretilmez; yalniz fake_exchange kanitı (market_parts) kabul",
                  "denemek icin --partial-fill-multiple N (<=20, notional <= 200 USDT)")
    qty = ctx.qty * n
    if qty * float(ctx.mark()) > 200 or n > 20:
        raise S.SafetyError("--partial-fill-multiple notional siniri (200 USDT) asildi")
    r = ctx.open_long(qty)
    cid, trig, sr = ctx.stop(0.02, qty=r.filled_qty)
    row = next((x for x in ctx.conditionals() if _cid_of(x) == cid), {})
    got = Decimal(str(row.get("quantity") or row.get("origQty") or 0))
    partial = r.filled_qty < qty
    ok = got == Decimal(str(r.filled_qty))
    return _R("GECTI" if ok else "KALDI", f"kismi_dolum={'evet' if partial else 'hayir (tam doldu)'}",
              f"stop_miktari={got} executedQty={r.filled_qty}")


def _cli(args: list[str]) -> int:
    from trader_engine import cli
    return cli.main(args)


def _engine_status(ctx: Ctx) -> dict:
    try:
        return json.loads(Path(ctx.cfg.status_path).read_text())
    except (OSError, ValueError):
        return {}


def t15(ctx: Ctx):
    ctx.confirm("T-15 (KILL): motor `systemctl start trader-engine@learner` ile testnette calisiyor ve motorun actigi EN AZ 2 pozisyon "
                "(+stoplari) borsada olmali. Betik KILL'i CLI ile koyar.")
    pos0 = ctx.open_positions()                       # hesap geneli (R1): yalniz tek sembol sayilmaz
    stops0 = _stops_all(ctx)
    n_pos, n_stops = len(pos0), len(stops0)
    if n_pos == 0:
        return _R("ATLANDI", "motor pozisyonu yok; 2 acik pozisyon kosulu saglanmadi")
    rc = _cli(["kill", "--config-dir", str(ctx.args.config_dir), "--env", "testnet", "--by", "smoke", "--reason", "T-15"])
    flat = ctx.wait_until(lambda: not ctx.open_positions() and not _stops_all(ctx), 60.0, 2.0)
    ks = _engine_status(ctx).get("kill_state")
    rc2 = _cli(["kill", "--config-dir", str(ctx.args.config_dir), "--env", "testnet", "--clear"])
    ok = rc == 0 and flat is not None and ks in ("flat", None)
    st = ("GECTI" if n_pos >= 2 else "KISMI") if ok else "KALDI"
    notes = [f"kill_oncesi_pozisyon={n_pos}", f"kill_oncesi_stop={n_stops}", f"duzlenme_s={flat}", f"kill_state={ks}"]
    if ok and n_pos < 2:
        notes.append("KISMI: 11 §11 T-15 en az 2 acik pozisyon ister; sayi yetersiz, kosu yinelenmeli")
    notes.append("KILL kalkinca giris acilmasi + duraklatma gozlemi elle (11 §11 T-15)")
    return _R(st, *notes, pozisyon_oncesi=n_pos, stop_oncesi=n_stops, duzlenme_s=flat, kill_state=ks, clear_rc=rc2)


def t16(ctx: Ctx):
    ctx.confirm("T-16 (duraklatma): motor calisiyor ve acik pozisyonu olmali. Betik `pause` CLI ile tutus ekler/kaldirir.")
    q0 = ctx.pos_qty()
    rc = _cli(["pause", "--config-dir", str(ctx.args.config_dir), "--bot", "learner", "--env", "testnet", "--reason", "user_cmd", "--by", "smoke"])
    ctx.clock.sleep(float(ctx.args.wait_s))
    alive = ctx.pos_qty() == q0 and q0 != 0
    rc2 = _cli(["pause", "--config-dir", str(ctx.args.config_dir), "--bot", "learner", "--env", "testnet", "--clear", "--reason", "user_cmd", "--by", "smoke"])
    return _R("GECTI" if rc == 0 and alive and rc2 == 0 else "KALDI", f"pozisyon_yasiyor={alive}", f"pause_rc={rc},{rc2}",
              "gate:paused atlama ve yeniden baslatmada surme gozlemi elle")


# ---------------------------------------------------------------------------------------------- D tatbikatlari
def _need_engine(ctx: Ctx, text: str) -> None:
    ctx.confirm(text)


def d1(ctx: Ctx):
    ctx.open_long(); cid, *_ = ctx.stop(0.03)
    n0 = len(ctx.rest.open_orders(ctx.sym)) + len(ctx.conditionals())
    _need_engine(ctx, "D-1: motor calisirken `iptables` ile borsa cikisini 3 dk kesin (OUTPUT drop), sonra acin; 30 sn bekleyin.")
    n1 = len(ctx.rest.open_orders(ctx.sym)) + len(ctx.conditionals())
    stop_ok = any(_cid_of(x) == cid for x in ctx.conditionals())
    return _R("GECTI" if stop_ok and n1 == n0 else "KALDI", f"stop_yerinde={stop_ok}", f"emir_sayisi={n0}->{n1}",
              "kesinti boyunca 0 POST ve exchange_unreachable gozlemi journalctl'den elle")


def d2(ctx: Ctx):
    ctx.open_long()
    t0 = ctx.now()
    _need_engine(ctx, "D-2: pozisyon STOPSUZ acildi. Simdi motoru baslatin (protect_first stopu kurmali); gerekirse `kill -9` ile "
                      "kesip yeniden baslatin. Saat isliyor.")
    got = ctx.wait_until(lambda: bool(_stops(ctx)), 45.0, 1.0)
    naked = (ctx.now() - t0).total_seconds() if got is not None else None
    return _R("GECTI" if got is not None else "KALDI", f"ciplak_sure_s={naked} (sinir 45; onay bekleme suresi dahil)")


def d3(ctx: Ctx):
    ctx.open_long()
    old, _, _ = ctx.stop(0.03)
    new, _, _ = ctx.stop(0.01)           # yeni (siki) kuruldu, eski iptal EDILMEDI
    _need_engine(ctx, "D-3: iki stop var (gevsek+siki). Motoru baslatin; acilista gevsek olan iptal edilmeli (L7).")
    got = ctx.wait_until(lambda: len(_stops(ctx)) == 1, 30.0, 1.0)
    left = [_cid_of(x) for x in _stops(ctx)]
    return _R("GECTI" if got is not None and left == [new] else "KALDI", f"kalan={len(left)}", f"siki_kaldi={left == [new]}")


def d4(ctx: Ctx):
    ctx.open_long()
    t0 = ctx.now()
    cid, trig, _ = ctx.stop(0.0005)
    samples = [ctx.observe()]
    _need_engine(ctx, "D-4: motor KAPALI olmali (ya da D-1 kesintisi). Stop mark'a cok yakin; tetiklenmesini bekleyin, sonra motoru baslatin.")
    samples.append(ctx.observe())
    flat = ctx.pos_qty() == 0
    ev = ctx.broker.closing_events(ctx.pair, t0, [cid]) if flat else []
    orphan = ctx.rest.open_orders(ctx.sym) + ctx.conditionals()
    crossed, mdata = trigger_verdict(samples, trig)
    notes = [f"tetiklendi={flat}", f"kapanis_olayi={len(ev)}", f"yetim={len(orphan)}",
             f"mark_son={mdata.get('mark_son')} son_fiyat_son={mdata.get('son_fiyat_son')} tetik={mdata.get('tetik')}"]
    if flat and crossed is False:
        return _R("FARKLI", *notes, "stop mark esigi gecilmeden tetiklenmis gorunuyor (ornekler onceki/sonraki; elle dogrulayin)", **mdata)
    return _R("GECTI" if flat and ev and not orphan else "KALDI", *notes, **mdata)


def d5(ctx: Ctx):
    ctx.open_long(); cid, *_ = ctx.stop(0.03)
    _need_engine(ctx, "D-5: motor calisiyor. Testnet arayuzunden STOP emrini elle iptal edin.")
    got = ctx.wait_until(lambda: bool(_stops(ctx)), 15.0 + 5.0, 1.0)
    return _R("GECTI" if got is not None else "KALDI", f"yeniden_kurulma_s={got} (sinir 15+ag)")


def d6(ctx: Ctx):
    ctx.opened = True        # operatorun actigi pozisyon kosu sonunda duzlestirilir (tek cift, tek pozisyon)
    _need_engine(ctx, "D-6: motor calisiyor. Testnet arayuzunden elle bir pozisyon acin (motorun bilmedigi).")
    q0 = ctx.pos_qty()
    ctx.clock.sleep(float(ctx.args.wait_s))
    untouched = ctx.pos_qty() == q0 and q0 != 0 and not _stops(ctx)
    return _R("GECTI" if untouched else "KALDI", f"pozisyon_dokunulmadi_ve_stopsuz={untouched}",
              "unknown_position tutusu ve CRIT elle gozlenir; tutus yalniz CLI ile kalkar")


def d7(ctx: Ctx):
    ctx.open_long(); ctx.stop(0.03)
    _need_engine(ctx, "D-7: motor calisiyor. Arayuzden pozisyonun YARISINI kapatin ve bir LIMIT emir koyun.")
    q = ctx.pos_qty()
    got = ctx.wait_until(lambda: any(Decimal(str(x.get("quantity") or x.get("origQty") or 0)) == abs(ctx.pos_qty())
                                     for x in _stops(ctx)), 30.0, 1.0)
    foreign = [x for x in ctx.rest.open_orders(ctx.sym) if not str(x.get("clientOrderId", "")).startswith(OURS_PREFIX)]
    return _R("GECTI" if got is not None and foreign else "KALDI", f"stop_kuculdu={got is not None}", f"yabanci_emir_duruyor={bool(foreign)}", pos=str(q))


def d8(ctx: Ctx):
    env = dict(os.environ)
    env["BINANCE_API_KEY"], env["BINANCE_API_SECRET"] = "x" * 40, "y" * 40       # gecersiz sahte anahtar
    p = ctx.runner([sys.executable, "-m", "trader_engine", "run", "--bot", "learner", "--env", "testnet"], env=env,
                   capture_output=True, text=True, timeout=120, cwd=str(_HERE.parent))
    out = (p.stdout or "") + (p.stderr or "")
    leak = "x" * 40 in out or "y" * 40 in out
    return _R("GECTI" if p.returncode == 8 and not leak else "KALDI", f"cikis_kodu={p.returncode} (beklenen 8)", f"anahtar_sizdi={leak}")


@dataclass(frozen=True)
class Step:
    name: str
    ref: str
    title: str
    fn: Callable
    group: str
    interactive: bool = False
    trades: bool = True


STEPS: dict[str, Step] = {s.name: s for s in [
    Step("b0-preflight", "B0", "Salt okuma: saat, hesap, kurallar, komisyon, temiz hesap", b0_preflight, "b0", trades=False),
    Step("b0-t01", "T-01", "Kosullu emir ucu (algo/classic) yanit alanlari", b0_t01, "b0"),
    Step("b0-t02", "T-02", "Hesap hazirligi: ISOLATED, one-way, kaldirac; pozisyonlu ret kodlari", b0_t02, "b0"),
    Step("b0-t03", "T-03", "workingType=MARK_PRICE alani", b0_t03, "b0"),
    Step("b0-t04", "T-04", "Iki stop ayni pozisyonda (tetik bekler: --trigger-wait-s)", b0_t04, "b0"),
    Step("b0-t05", "T-05", "reduceOnly davranisi (a, b)", b0_t05, "b0"),
    Step("b0-t06", "T-06", "Hemen tetiklenecek stop", b0_t06, "b0"),
    Step("b0-t07", "T-07", "Tetiklenen stop <-> cocuk emir <-> userTrades (tetik bekler)", b0_t07, "b0"),
    Step("b0-t08", "T-08", "Kimlik tekrari ve zaman asimi sorgusu", b0_t08, "b0"),
    Step("b0-t09", "T-09", "Ret kodlari: min notional, adim disi", b0_t09, "b0"),
    Step("b0-t10", "T-10", "Piyasa emri yaniti ve komisyon", b0_t10, "b0"),
    Step("b0-t11", "T-11", "Hiz basliklari", b0_t11, "b0"),
    Step("b0-t12", "T-12", "Funding gelir kaydi (yalniz okuma, engelleyici degil)", b0_t12, "b0", trades=False),
    Step("t13", "T-13", "Tam yasam dongusu (motor sinifi LiveBroker)", t13, "t"),
    Step("t14", "T-14", "Kismi dolum", t14, "t"),
    Step("t15", "T-15", "KILL", t15, "t", interactive=True, trades=False),
    Step("t16", "T-16", "Duraklatma", t16, "t", interactive=True, trades=False),
    Step("d1", "D-1", "Yeniden baglanma (iptables)", d1, "d", interactive=True),
    Step("d2", "D-2", "Giriste kill -9 / protect_first", d2, "d", interactive=True),
    Step("d3", "D-3", "Iz suren stop ortasinda kill -9 (iki stop)", d3, "d", interactive=True),
    Step("d4", "D-4", "Kesintide stop tetiklenir", d4, "d", interactive=True),
    Step("d5", "D-5", "Mutabakat: stop silme", d5, "d", interactive=True),
    Step("d6", "D-6", "Mutabakat: bilinmeyen pozisyon", d6, "d", interactive=True, trades=False),
    Step("d7", "D-7", "Mutabakat: dis azaltma ve yabanci emir", d7, "d", interactive=True),
    Step("d8", "D-8", "Yanlis anahtar: cikis kodu 8", d8, "d", trades=False),
]}
GROUPS = {"b0": "b0", "t": "t", "drills": "d", "d": "d"}


def resolve_steps(spec: list[str]) -> list[Step]:
    out: list[Step] = []
    for item in [x for s in spec for x in s.split(",") if x]:
        if item in STEPS:
            out.append(STEPS[item])
        elif item in GROUPS:
            out += [s for s in STEPS.values() if s.group == GROUPS[item]]
        else:
            raise S.SafetyError(f"bilinmeyen adim: {item}")
    seen, uniq = set(), []
    for s in out:
        if s.name not in seen:
            seen.add(s.name); uniq.append(s)
    return uniq


def print_plan(steps: list[Step], pair: str, say=print) -> None:
    say(f"PLAN (dry-run; ag/anahtar yok) cift={pair} env=testnet taban={sorted(S.ALLOWED_BASES)[0]}")
    for s in steps:
        say(f"  - {s.name:13s} {s.ref:6s} {'[etkilesimli] ' if s.interactive else ''}{'emir gonderir  ' if s.trades else 'emir yok       '}{s.title}")
    say("  her kosu sonu: kendi acik emirleri iptal + pozisyon duzlestirme (finally); rapor var-testnet/smoke/<zaman>/")


# ---------------------------------------------------------------------------------------------- temizlik
def cleanup(ctx: Ctx, report: S.Report) -> None:
    """Kendi (tr-onekli) emirleri iptal et, pozisyonu reduceOnly piyasa ile duzle. Hata olsa da devam eder."""
    from trader_engine.exchange.binance_rest import fmt_num
    rest = ctx.rest
    try:
        for row in rest.open_conditionals(ctx.sym):
            c = _cid_of(row)
            if c.startswith(OURS_PREFIX):
                try:
                    rest.cancel_conditional(ctx.sym, c); report.cleanup.append(f"stop iptal {c[:8]}")
                except Exception as e:  # noqa: BLE001
                    report.cleanup.append(f"stop iptal HATA {type(e).__name__}")
        for row in rest.open_orders(ctx.sym):
            c = str(row.get("clientOrderId", ""))
            if c.startswith(OURS_PREFIX) and str(row.get("origType", row.get("type", ""))) not in S_COND_TYPES:
                try:
                    rest.cancel_order(ctx.sym, c); report.cleanup.append(f"emir iptal {c[:8]}")
                except Exception as e:  # noqa: BLE001
                    report.cleanup.append(f"emir iptal HATA {type(e).__name__}")
            elif not c.startswith(OURS_PREFIX):
                report.cleanup.append("UYARI: yabanci acik emir birakildi (dokunulmadi)")
    except Exception as e:  # noqa: BLE001
        report.cleanup.append(f"emir temizligi HATA {type(e).__name__}")
    try:
        q = ctx.pos_qty() if ctx.opened else Decimal(0)
        if q != 0:
            side = "SELL" if q > 0 else "BUY"
            rest.new_market(ctx.sym, side, float(abs(q)), ctx.cid("exit"), True)
            report.cleanup.append(f"pozisyon duzlestirildi {side} {fmt_num(abs(q))}")
        report.cleanup.append("son durum: pozisyon=%s" % ctx.pos_qty())
    except Exception as e:  # noqa: BLE001
        report.cleanup.append(f"DUZLESTIRME HATA {type(e).__name__}: elle kontrol edin")


S_COND_TYPES = ("STOP", "STOP_MARKET", "TAKE_PROFIT", "TAKE_PROFIT_MARKET", "TRAILING_STOP_MARKET")


# ---------------------------------------------------------------------------------------------- ana
def build_parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(prog="smoke_testnet", description=__doc__.split("\n")[0])
    ap.add_argument("--env", default=None, help="yalniz 'testnet'; 'live' reddedilir")
    ap.add_argument("--step", action="append", default=[], help="adim adi / grup (b0, t, drills); virgulle ya da tekrarla")
    ap.add_argument("--list", action="store_true", help="adimlari listele")
    ap.add_argument("--dry-run", action="store_true", help="plani yazdir; ag ve anahtar kullanilmaz")
    ap.add_argument("--config-dir", default="config")
    ap.add_argument("--pair", default=DEFAULT_PAIR)
    ap.add_argument("--ack-no-withdraw", action="store_true", help="testnet anahtarinda para cekme izni YOK (apiRestrictions testnette yok)")
    ap.add_argument("--trigger-wait-s", type=float, default=120.0)
    ap.add_argument("--t13-stop-pct", type=float, default=0.0003,
                    help="T-04/T-07/T-13 siki stop uzakligi (mark'tan oran; 0.00005..0.02); tetik icin daraltilabilir")
    ap.add_argument("--wait-s", type=float, default=20.0)
    ap.add_argument("--partial-fill-multiple", type=int, default=0)
    ap.add_argument("--out-root", default=None, help="varsayilan: yapilandirmadaki var_dir")
    return ap


def main(argv: list[str] | None = None, *, environ=None, rest_factory=None, clock=None, input_fn=input, say=print,
         runner=subprocess.run, on_wait=None) -> int:
    a = build_parser().parse_args(argv)
    environ = os.environ if environ is None else environ
    if a.list:
        for s in STEPS.values():
            say(f"{s.name:13s} {s.ref:6s} {s.title}")
        return 0
    try:
        S.guard_env(a.env)
        if not a.step:
            raise S.SafetyError("--step gerekli (bkz. --list)")
        steps = resolve_steps(a.step)
        if not 0.00005 <= a.t13_stop_pct <= 0.02:
            raise S.SafetyError("--t13-stop-pct 0.00005..0.02 araliginda olmali")
        if not 1 <= a.trigger_wait_s <= 3600:
            raise S.SafetyError("--trigger-wait-s 1..3600 sn araliginda olmali")
        if a.dry_run:
            print_plan(steps, a.pair, say)
            return 0
        return _run(a, steps, environ, rest_factory, clock, input_fn, say, runner, on_wait)
    except S.SafetyError as e:
        say(f"REDDEDILDI: {S.mask(e)}")
        return 2


def _run(a, steps, environ, rest_factory, clock, input_fn, say, runner, on_wait) -> int:
    import time

    from trader_engine.brokers.binance_futures import LiveBroker
    from trader_engine.clock import SystemClock
    from trader_engine.config import load_cli_config
    from trader_engine.exchange.binance_rest import SignedRestClient

    key, secret = S.read_keys(environ)
    d = Path(a.config_dir)
    cfg = load_cli_config(d, "learner", "testnet")           # DD-8 E2: kill/pause/var_dir mutlak (cwd'den bagimsiz)
    S.guard_config(cfg)
    clk = clock or SystemClock()
    now_ms = lambda: int(clk.now().timestamp() * 1000)  # noqa: E731
    from trader_core.ban_store import BanGuard, ban_dir_for, ban_path
    from trader_engine.exchange.binance_rest import BASES
    rest = (rest_factory or (lambda **kw: SignedRestClient(**kw)))(
        env="testnet", api_key=key, api_secret=secret, now_ms=now_ms, sleep=clk.sleep,
        recv_window_ms=cfg.live.recv_window_ms, conditional_mode=cfg.live.conditional_mode,
        ban_guard=BanGuard(ban_path(ban_dir_for(cfg.market_db), BASES["testnet"]), source="smoke_testnet", now_ms=now_ms))   # DD-7 §2
    S.guard_rest(rest)
    restr = None
    try:
        restr = rest.api_restrictions()       # testnette ExchangeError (SAPI yok) -> operator onayi gerekir
    except Exception:  # noqa: BLE001
        restr = None
    wd = S.check_withdrawals(restr, ack_no_withdraw=a.ack_no_withdraw)
    pair = a.pair
    if pair not in cfg.pairs:
        raise S.SafetyError("cift yapilandirmada yok")
    live = cfg.live
    broker = LiveBroker(live, "testnet", int(cfg.leverage), [pair], rest, clk, cfg.cost.taker_fee, environ=environ)
    stamp = clk.now().strftime("%Y%m%dT%H%M%SZ")
    report = S.Report(clk.now().isoformat(), (key, secret))
    report.meta = {"pair": pair, "env": "testnet", "withdraw_check": wd, "key": S.mask_key(key), "steps": [s.name for s in steps]}
    ctx = None
    try:
        broker.startup_check()
        ctx = Ctx(rest=rest, broker=broker, clock=clk, pair=pair, cfg=cfg, args=a, input_fn=input_fn, say=say,
                  runner=runner, on_wait=on_wait)
        ctx.require_flat()
        for s in steps:
            res = S.StepResult(s.name, s.ref)
            t0 = time.monotonic()
            try:
                res.status, res.notes, res.data = s.fn(ctx)
            except S.SafetyError as e:
                res.status, res.notes = "KALDI", [f"guvenlik: {S.mask(e, (key, secret))}"]
                report.results.append(res)
                raise
            except Exception as e:  # noqa: BLE001
                res.status, res.notes = "KALDI", [f"istisna {type(e).__name__}: {S.mask(e, (key, secret))[:200]}"]
            res.seconds = time.monotonic() - t0
            report.results.append(res)
            say(f"{s.ref:6s} {s.name:13s} {res.status}  {'; '.join(res.notes)[:160]}")
            if s.trades:
                cleanup(ctx, report)          # adimlar arasi: tek pozisyon kurali icin duz basla
    finally:
        if ctx is not None:
            cleanup(ctx, report)
        root = Path(a.out_root or cfg.var_dir)
        out = report.write(root, stamp)
        say(f"rapor: {out}")
    bad = [r for r in report.results if r.status in ("KALDI", "FARKLI", "BEKLEMEDE", "KISMI")]
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
