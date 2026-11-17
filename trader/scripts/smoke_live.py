#!/usr/bin/env python3
"""WP-B9: GERCEK hesap duman testi (11 §12; 28-29 Aralik, gercek ama kucuk para). Bir kez kosulur.

Yalniz Binance vadeli URETIM adresi (smoke_live.ALLOWED_BASES); testnet reddedilir. Anahtarlar yalniz ortamdan
(BINANCE_API_KEY / BINANCE_API_SECRET), her yerde maskelenir. `LIVE_CONFIRM` canli katmandaki `live.account_tag` ile
ayni olmali. `api_restrictions()` para cekme ACIK ya da IP kisiti YOK diyorsa (ya da okunamazsa) cikis kodu 8: bu betikte
beyan/atestasyon ile gecis YOKTUR. Risk kademe gunlugu (sermaye kaydi) yok/gecersizse ya da kademe tutusu/KILL varsa
baslamaz. Tek cift, asgari tutar, en fazla 1 pozisyon; yalniz betigin KENDI emirleri/pozisyonu (kimlik kumesi ile izlenir).
Ilk gercek emirden once yazili ifade istenir (yalniz testte `input_fn` enjekte edilerek atlanir). Her duraklamada `evet`
dışındaki yanit "simdi kapat"tir. finally: kendi emirleri iptal, yalniz kendi pozisyonu reduceOnly duzlenir.

Kapsam (tek cift kuralindan dolayi 11 §12'nin altkumesi): S-0, S-1, S-2, S-3, S-4, S-6, S-9, kapanis, S-12, S-13.
Kapsam disi (elle / motorla): S-5 (ikinci cift), S-7 (kill -9), S-8 (stop tetik bekleme), S-10/S-11 (motor duraklatma/KILL).

Ornek:  python scripts/smoke_live.py --env live --dry-run
Cikis: 0 tum adimlar GECTI; 1 KALDI/FARKLI; 2 guvenlik korkulugu / kullanim / operator iptali (hicbir emir gitmedi
ya da kapatildi); 8 anahtar izni (cekme acik / IP kisiti yok / dogrulanamadi) ya da motor acilis denetimi 8.
"""
from __future__ import annotations

import argparse
import os
import sys
import time
from dataclasses import dataclass
from datetime import timezone
from decimal import ROUND_FLOOR, Decimal
from pathlib import Path
from typing import Any, Callable

_HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(_HERE.parent / "src"))
sys.path.insert(0, str(_HERE))

import smoke_testnet_lib as S  # noqa: E402

UTC = timezone.utc
# Sabit izin listesi: yalniz Binance vadeli URETIM. Yapilandirmadan/komut satirindan eklenemez.
ALLOWED_BASES = frozenset({"https://fapi.binance.com"})
DEFAULT_PAIR = "XRP/USDT"
DEFAULT_OUT_ROOT = "var-live"
SMOKE_BOT = "smoke"                    # make_client_id botu: motorun learner/twin kimliklerinden ayrisir
MAX_NOTIONAL_USDT = 25.0               # mutlak tavan
MAX_NOTIONAL_FACTOR = 2.0              # min_notional'in en fazla 2 kati
EXIT_OK, EXIT_FAIL, EXIT_REFUSED, EXIT_PERM = 0, 1, 2, 8
_REQUIRED_PERMS = (("enableWithdrawals", False), ("ipRestrict", True), ("enableReading", True), ("enableFutures", True),
                   ("enableInternalTransfer", False), ("permitsUniversalTransfer", False))
S_COND_TYPES = ("STOP", "STOP_MARKET", "TAKE_PROFIT", "TAKE_PROFIT_MARKET", "TRAILING_STOP_MARKET")


class PermissionRefused(S.SafetyError):
    """Anahtar izni uygun degil / dogrulanamadi: cikis 8 (atestasyonla gecilemez)."""


class Aborted(Exception):
    """Operator 'simdi kapat' dedi ya da yazili onayi vermedi."""


# ---------------------------------------------------------------------------------------------- korkuluklar
def phrase_for(tag: str) -> str:
    return f"GERCEK EMIR {tag}"


def guard_env(env: str | None) -> None:
    if env == "testnet":
        raise S.SafetyError("--env testnet reddedildi: bu betik yalniz gercek hesap icindir (testnet icin smoke_testnet.py)")
    if env != "live":
        raise S.SafetyError("--env live zorunlu")


def guard_base_url(url: str) -> None:
    if str(url).rstrip("/") not in ALLOWED_BASES:
        raise S.SafetyError("taban adres izin listesinde degil (yalniz Binance vadeli uretim adresi)")


def guard_rest(rest: Any) -> None:
    if getattr(rest, "env", None) != "live":
        raise S.SafetyError("istemci kipi live degil")
    guard_base_url(getattr(rest, "_base", ""))


def guard_config(cfg: Any, environ: Any) -> None:
    """Canli kip + testnet olmayan yollar + LIVE_CONFIRM == live.account_tag (deger iletiye yazilmaz)."""
    if cfg.mode != "live" or cfg.live is None:
        raise S.SafetyError(f"yapilandirma kipi live degil: {cfg.mode}")
    for name in ("var_dir", "kill_file", "pause_file"):
        if "testnet" in str(getattr(cfg, name)):
            raise S.SafetyError(f"{name} testnet yolu: canli katman degil")
    got = environ.get("LIVE_CONFIRM")
    if not isinstance(got, str) or got != cfg.live.account_tag:
        raise S.SafetyError("LIVE_CONFIRM eksik ya da live.account_tag ile ayni degil")


def check_permissions(restrictions: Any) -> None:
    """Cekme acik / IP kisiti yok / izin okunamadi => PermissionRefused (cikis 8). Beyan ile gecis YOK."""
    if not isinstance(restrictions, dict):
        raise PermissionRefused("api_restrictions okunamadi: anahtar izinleri dogrulanamadi")
    for field, want in _REQUIRED_PERMS:
        v = restrictions.get(field)
        if not isinstance(v, bool):
            raise PermissionRefused(f"anahtar izni dogrulanamadi: {field}")
        if v is not want:
            raise PermissionRefused(f"anahtar izni uygunsuz: {field}={v} (beklenen {want})")


def check_ladder_and_holds(cfg: Any, clock: Any) -> dict:
    """Risk kademe gunlugu var + gecerli + durum ok; KILL yok; hicbir giris tutusu (kademe dahil) yok."""
    from trader_core import risk_ladder as RL
    from trader_engine.killswitch import Killswitch
    from trader_engine.pause import EntryPause

    path = cfg.path("risk_ladder.jsonl")
    try:
        st = RL.LadderLog(path).state()
    except RL.LadderLogError as e:
        raise S.SafetyError(f"risk kademe gunlugu gecersiz: {e}") from e
    if st is None:
        raise S.SafetyError("risk kademe gunlugu yok/bos: sermaye kaydi (capital init) yapilmamis")
    if st.status != "ok":
        raise S.SafetyError(f"kademe durumu {st.status}: giris tutusu (drawdown_review/capital_floor) etkin")
    if Killswitch(cfg.kill_file, clock).active():
        raise S.SafetyError("KILL etkin")
    holds = EntryPause(f"{cfg.pause_file}.{cfg.bot}", clock).holds()
    if holds:
        raise S.SafetyError("duraklatma tutusu etkin: " + ",".join(sorted({h.reason for h in holds})))
    return {"ladder_seq": st.seq, "ladder_step": st.step, "dep_net": st.dep_net}


# ---------------------------------------------------------------------------------------------- baglam
def _cid_of(row: dict) -> str:
    return str(row.get("clientAlgoId") or row.get("clientOrderId") or "")


class Ctx:
    def __init__(self, *, rest, broker, clock, pair, cfg, phrase, input_fn, say, recheck: Callable[[], Any]):
        self.rest, self.broker, self.clock, self.pair, self.cfg = rest, broker, clock, pair, cfg
        self.phrase, self.input_fn, self.say, self.recheck = phrase, input_fn, say, recheck
        self.sym = pair.replace("/", "")
        self.seq = 0
        self.t0 = clock.now().replace(microsecond=0)
        self.rules = broker.rules(pair)
        mark = rest.mark_price(self.sym)
        self.qty = float(S.min_order_qty(self.rules.min_qty, self.rules.step, self.rules.min_notional, float(mark)))
        notional = self.qty * float(mark)
        cap = min(MAX_NOTIONAL_USDT, MAX_NOTIONAL_FACTOR * float(self.rules.min_notional))
        if notional > cap:
            raise S.SafetyError(f"asgari tutar siniri asildi: {notional:.2f} > {cap:.2f} USDT")
        self.own: set[str] = set()             # yalniz bu betigin urettigi istemci kimlikleri
        self.order_ids: set[str] = set()
        self.opened = False                    # giris gonderildi mi (kendi pozisyonumuz var olabilir)
        self.entry_qty = 0.0
        self.confirmed = False
        self.wallet0: Decimal | None = None
        self.start_ms = self._now_ms()

    def _now_ms(self) -> int:
        return int(self.clock.now().timestamp() * 1000)

    def cid(self, role: str) -> str:
        from trader_engine.order_manager import make_client_id
        self.seq += 1
        c = make_client_id(SMOKE_BOT, role, self.pair, "long", self.t0, self.seq)   # type: ignore[arg-type]
        self.own.add(c)
        return c

    def mark(self) -> Decimal:
        return self.rest.mark_price(self.sym)

    def round_tick(self, px: Decimal) -> float:
        t = Decimal(str(self.rules.tick))
        return float((px / t).to_integral_value(rounding=ROUND_FLOOR) * t)

    def pos_qty(self) -> Decimal:
        return sum((Decimal(str(r["positionAmt"])) for r in self.rest.position_risk(self.sym)), Decimal(0))

    def pos_row(self) -> dict:
        rows = [r for r in self.rest.position_risk(self.sym) if r.get("symbol") == self.sym]
        return rows[0] if rows else {}

    def account_open_positions(self) -> list[dict]:
        return [r for r in self.rest.position_risk() if Decimal(str(r["positionAmt"])) != 0]

    def account_open_orders(self) -> list[dict]:
        return self.rest.open_orders() + self.rest.open_conditionals()

    def require_clean(self) -> None:
        if self.account_open_positions():
            raise S.SafetyError("hesapta zaten acik pozisyon var: en fazla 1 pozisyon kurali, baslanmaz")
        if self.account_open_orders():
            raise S.SafetyError("hesapta zaten acik emir var (betige ait degil): baslanmaz")

    def my_stops(self) -> list[dict]:
        return [r for r in self.rest.open_conditionals(self.sym) if _cid_of(r) in self.own]

    # -- etkilesim ---------------------------------------------------------------------
    def proceed(self, label: str, what: str) -> None:
        self.say(f"{label}: {what}")
        ans = self.input_fn("Devam icin `evet` yazin (baska her yanit = simdi her seyi kapat): ")
        if str(ans).strip().lower() != "evet":
            raise Aborted(f"operator durdurdu ({label})")

    def confirm_first_order(self) -> None:
        self.say("DIKKAT: bundan sonra GERCEK hesapta GERCEK emir gonderilecek (asgari tutar, en fazla 1 pozisyon).")
        ans = self.input_fn(f"ONAY - devam icin tam olarak su ifadeyi yazin: {self.phrase}\n> ")
        if str(ans).strip() != self.phrase:
            raise Aborted("yazili onay verilmedi: hicbir emir gonderilmedi")
        self.confirmed = True

    # -- emirler -----------------------------------------------------------------------
    def open_long(self):
        from trader_engine.types import OrderRequest
        if not self.confirmed:
            raise S.SafetyError("yazili onay olmadan gercek emir gonderilmez")
        self.recheck()                                    # KILL / kademe / tutus: emirden hemen once yeniden
        self.require_clean()
        self.broker.prepare(self.pair, int(self.cfg.leverage))
        self.opened = True
        r = self.broker.market_order(OrderRequest(client_id=self.cid("entry"), pair=self.pair, role="entry", order_side="buy",
                                                  qty=self.qty, trigger_price=None, reduce_only=False,
                                                  leverage=int(self.cfg.leverage), created_ts=self.clock.now()))
        if r.order_id:
            self.order_ids.add(str(r.order_id))
        self.entry_qty = float(r.filled_qty or 0.0)
        self.broker.register_position(self.pair, self.clock.now())
        return r

    def conditional(self, role: str, pct: float, up: bool = False, qty: float | None = None):
        from trader_engine.types import OrderRequest
        f = Decimal(1) + Decimal(str(pct)) if up else Decimal(1) - Decimal(str(pct))
        trig = self.round_tick(self.mark() * f)
        cid = self.cid(role)
        req = OrderRequest(client_id=cid, pair=self.pair, role=role, order_side="sell", qty=qty or self.entry_qty or self.qty,
                           trigger_price=trig, reduce_only=True, leverage=None, created_ts=self.clock.now())
        r = self.broker.place_target(req) if role == "target" else self.broker.place_stop(req)
        return cid, trig, r

    def close_own(self):
        """Yalniz kendi giris miktari kadar reduceOnly piyasa (baska pozisyona dokunmaz)."""
        from trader_engine.types import OrderRequest
        q = self.pos_qty()
        amt = min(abs(q), Decimal(str(self.entry_qty))) if q > 0 else Decimal(0)
        if amt <= 0:
            return None
        r = self.broker.market_order(OrderRequest(client_id=self.cid("exit"), pair=self.pair, role="exit", order_side="sell",
                                                  qty=float(amt), trigger_price=None, reduce_only=True, leverage=None,
                                                  created_ts=self.clock.now()))
        if r.order_id:
            self.order_ids.add(str(r.order_id))
        return r


def _R(status: str, *notes: str, **data) -> tuple[str, list[str], dict]:
    return status, list(notes), data


def _truthy(v: Any) -> bool:
    return str(v).lower() == "true"


# ---------------------------------------------------------------------------------------------- adimlar
def s0(ctx: Ctx):
    acct = ctx.rest.account()
    ctx.wallet0 = Decimal(str(acct.get("totalWalletBalance")))
    pos, oo = ctx.account_open_positions(), ctx.account_open_orders()
    ok = not pos and not oo and not ctx.rest.position_mode() and not ctx.rest.multi_assets()
    return _R("GECTI" if ok else "KALDI", f"cuzdan={ctx.wallet0}", f"cuzdan_tavani={ctx.cfg.live.expected_wallet_max}",
              f"acik_pozisyon={len(pos)}", f"acik_emir={len(oo)}", "izinler=dogrulandi (para cekme kapali, IP kisitli)")


def s1(ctx: Ctx):
    mark = ctx.mark()
    notional = ctx.qty * float(mark)
    return _R("GECTI", f"cift={ctx.pair}", f"miktar={ctx.qty}", f"mark={mark}", f"nominal={notional:.4f} USDT",
              f"min_notional={ctx.rules.min_notional}", qty=ctx.qty, notional=notional)


def s2(ctx: Ctx):
    ctx.broker.prepare(ctx.pair, int(ctx.cfg.leverage))
    row = ctx.pos_row()
    ok = str(row.get("marginType", "")).lower() == "isolated" and int(float(row.get("leverage", 0))) == int(ctx.cfg.leverage)
    return _R("GECTI" if ok else "KALDI", f"marjin={row.get('marginType')}", f"kaldirac={row.get('leverage')}")


def s3(ctx: Ctx):
    mark = ctx.mark()
    r = ctx.open_long()
    if r.status != "filled":
        return _R("KALDI", f"giris_durum={r.status}", f"neden={r.reason}")
    row = ctx.pos_row()
    amt = Decimal(str(row.get("positionAmt", 0)))
    notes = [f"executedQty={r.filled_qty}", f"pozisyon={amt}", f"marjin={row.get('marginType')}"]
    ok = amt == Decimal(str(ctx.qty)) and abs(float(r.filled_qty) - ctx.qty) < 1e-12 \
        and str(row.get("marginType", "")).lower() == "isolated"
    st = "GECTI" if ok else "KALDI"
    exp_margin = ctx.qty * float(mark) / int(ctx.cfg.leverage)
    im = float(row.get("isolatedMargin") or 0)
    if im > 0:
        notes.append(f"teminat={im:.4f} beklenen~{exp_margin:.4f}")
        if abs(im - exp_margin) > 0.02 * exp_margin and st == "GECTI":
            st = "FARKLI"
    return _R(st, *notes, avg_price=r.avg_price, fee=r.fee)


def s4(ctx: Ctx):
    t_fill = ctx.clock.now()
    cid, trig, r = ctx.conditional("stop", 0.01)
    gap = (ctx.clock.now() - t_fill).total_seconds()
    row = next((x for x in ctx.my_stops() if _cid_of(x) == cid), None)
    if r.status != "accepted" or row is None:
        return _R("KALDI", f"stop_durum={r.status}", f"borsada_gorunur={row is not None}", trigger=trig)
    qty = Decimal(str(row.get("quantity") or row.get("origQty") or 0))
    ok = (gap <= 10 and row.get("workingType") == "MARK_PRICE" and _truthy(row.get("reduceOnly"))
          and qty == Decimal(str(ctx.entry_qty)))
    return _R("GECTI" if ok else "KALDI", f"dolum->stop={gap:.2f}s (sinir 10)", f"workingType={row.get('workingType')}",
              f"reduceOnly={row.get('reduceOnly')}", f"miktar={qty}", trigger=trig, stop_cid=cid, gap_s=gap)


def s6(ctx: Ctx):
    snaps = [[_cid_of(x) for x in ctx.my_stops()]]
    old = snaps[0][0] if snaps[0] else None
    cid, trig, r = ctx.conditional("stop", 0.005)
    if r.status != "accepted":
        return _R("KALDI", f"yeni_stop_reddedildi={r.status}", snapshots=snaps)
    snaps.append([_cid_of(x) for x in ctx.my_stops()])         # yeni kabul edildi, eski hala orada
    if old:
        ctx.broker.cancel(ctx.pair, old)                        # eski ANCAK yeni kabulden sonra iptal
    snaps.append([_cid_of(x) for x in ctx.my_stops()])
    ok = all(len(s) >= 1 for s in snaps) and snaps[-1] == [cid] and old is not None and old in snaps[1]
    return _R("GECTI" if ok else "KALDI", f"goruntuler={[len(s) for s in snaps]} (her an >= 1 stop)", trigger=trig,
              snapshots=snaps)


def s9(ctx: Ctx):
    cid, trig, r = ctx.conditional("target", 0.05, up=True)
    row = next((x for x in ctx.rest.open_conditionals(ctx.sym) if _cid_of(x) == cid), None)
    seen = row is not None
    if r.status == "accepted":
        ctx.broker.cancel(ctx.pair, cid)
    gone = all(_cid_of(x) != cid for x in ctx.rest.open_conditionals(ctx.sym))
    ok = r.status == "accepted" and seen and gone
    return _R("GECTI" if ok else "KALDI", f"hedef_durum={r.status}", f"gorundu={seen}", f"iptal_edildi={gone}", trigger=trig)


def s_close(ctx: Ctx):
    r = ctx.close_own()
    if r is None or r.status not in ("filled", "accepted"):
        return _R("KALDI", f"kapanis_durum={None if r is None else r.status}")
    for _ in range(10):                                           # borsa dolumu gorunene kadar kisa bekleme
        if ctx.pos_qty() == 0:
            break
        ctx.clock.sleep(1.0)
    flat = ctx.pos_qty() == 0
    if flat:
        for row in ctx.my_stops():                                # pozisyon duz: kendi stoplarini iptal et
            ctx.broker.cancel(ctx.pair, _cid_of(row))
    left = [_cid_of(x) for x in ctx.account_open_orders()]
    return _R("GECTI" if flat and not left else "KALDI", f"duz={flat}", f"acik_emir={len(left)}", fee=r.fee)


def _own_trades(ctx: Ctx) -> list[dict]:
    rows = ctx.rest.user_trades(ctx.sym, ctx.start_ms - 1000)
    return [t for t in rows if str(t.get("orderId")) in ctx.order_ids]


def s12(ctx: Ctx):
    tr = _own_trades(ctx)
    comm = sum((Decimal(str(t.get("commission", 0))) for t in tr), Decimal(0))
    flat = ctx.pos_qty() == 0 and not ctx.account_open_orders()
    ok = len(tr) >= 2 and flat and comm > 0
    return _R("GECTI" if ok else "KALDI", f"islem_sayisi={len(tr)}", f"komisyon_toplami={comm}", f"pozisyon_ve_emir_sifir={flat}",
              commission=str(comm))


def s13(ctx: Ctx):
    tr = _own_trades(ctx)
    realized = sum((Decimal(str(t.get("realizedPnl", 0))) for t in tr), Decimal(0))
    comm = sum((Decimal(str(t.get("commission", 0))) for t in tr), Decimal(0))
    funding, note = Decimal(0), "funding=okunamadi"
    try:
        rows = ctx.rest.income(ctx.sym, "FUNDING_FEE", ctx.start_ms - 1000, ctx._now_ms() + 1000)
        funding, note = sum((Decimal(str(i.get("income", 0))) for i in rows), Decimal(0)), f"funding={len(rows)} satir"
    except Exception as e:  # noqa: BLE001
        note = f"funding okunamadi ({type(e).__name__})"
    after = Decimal(str(ctx.rest.account().get("totalWalletBalance")))
    delta = after - (ctx.wallet0 or after)
    expected = realized - comm + funding
    ok = ctx.wallet0 is not None and abs(delta - expected) <= Decimal("0.01")
    return _R("GECTI" if ok else "KALDI", f"cuzdan_degisimi={delta}", f"beklenen={expected} (gerceklesen {realized} - komisyon {comm} + funding {funding})",
              note, wallet_before=str(ctx.wallet0), wallet_after=str(after))


@dataclass(frozen=True)
class Step:
    name: str
    ref: str
    title: str
    fn: Callable[[Ctx], tuple]
    trades: bool
    gate: str


STEPS: list[Step] = [
    Step("s0", "S-0", "Acilis denetimi: izinler, cuzdan tavani, temiz hesap, one-way", s0, False, "salt okuma"),
    Step("s1", "S-1", "Kurallar ve asgari miktar (tek cift)", s1, False, "salt okuma"),
    Step("s2", "S-2", "Hazirlik: izole marjin + kaldirac", s2, False, "marjin/kaldirac ayari gonderir (emir degil)"),
    Step("s3", "S-3", "LONG piyasa girisi (GERCEK EMIR)", s3, True, "GERCEK piyasa emri"),
    Step("s4", "S-4", "Stop (mark'in %1 alti, MARK_PRICE, reduceOnly)", s4, True, "koruyucu stop emri"),
    Step("s6", "S-6", "Stopu sikilastir (%0,5): yeni kabul -> eski iptal", s6, True, "stop emri + iptal"),
    Step("s9", "S-9", "Hedef emri kur, gor, iptal et", s9, True, "hedef emri + iptal"),
    Step("close", "S-C", "Kendi pozisyonunu reduceOnly piyasa ile kapat, kendi stoplarini iptal et", s_close, True,
         "GERCEK reduceOnly piyasa emri"),
    Step("s12", "S-12", "Kayit denetimi: userTrades komisyon, pozisyon/emir sifir", s12, False, "salt okuma"),
    Step("s13", "S-13", "Hesap denetimi: cuzdan degisimi = gerceklesen - komisyon + funding", s13, False, "salt okuma"),
]


def print_plan(pair: str, say=print) -> None:
    say(f"PLAN (dry-run; ag/anahtar yok) cift={pair} env=live taban={sorted(ALLOWED_BASES)[0]}")
    for s in STEPS:
        say(f"  - {s.ref:5s} {'emir gonderir ' if s.trades else 'emir yok      '}{s.title}")
    say("  her adimdan once `evet` beklenir; ilk gercek emirden once yazili ifade istenir; yanit `evet` degilse simdi kapat")
    say(f"  her kosu sonu: kendi emirleri iptal + yalniz kendi pozisyonu duzlenir (finally); rapor {DEFAULT_OUT_ROOT}/smoke/<zaman>/")
    say("  kapsam disi: S-5 (2. cift), S-7 (kill -9), S-8 (stop tetik bekleme), S-10/S-11 (motor duraklatma/KILL)")


# ---------------------------------------------------------------------------------------------- rapor / temizlik
class LiveReport(S.Report):
    def to_markdown(self) -> str:
        d = self.to_dict()
        import json
        L = [f"# Canli duman testi raporu {d['started']}", "",
             f"Meta: `{json.dumps(d['meta'], ensure_ascii=False)}`", "",
             "| Adim | Ref | Durum | sn | Not |", "|---|---|---|---|---|"]
        for r in d["results"]:
            L.append(f"| {r['name']} | {r['ref']} | {r['status']} | {r['seconds']:.1f} | {'; '.join(r['notes'])[:300]} |")
        L += ["", "## Temizlik", *(f"- {c}" for c in d["cleanup"]), ""]
        return "\n".join(L)


def cleanup(ctx: Ctx, report: S.Report) -> None:
    """Once kendi pozisyonunu duzle (stop korumada kalir), sonra kendi emirlerini iptal et. Yabanci emre/pozisyona dokunmaz."""
    rest = ctx.rest
    flat = True
    try:
        if ctx.opened:
            r = ctx.close_own()
            if r is not None:
                report.cleanup.append(f"pozisyon duzlestirildi status={r.status}")
            q = ctx.pos_qty()
            flat = q == 0
            report.cleanup.append(f"son pozisyon={q}")
            if q != 0:
                report.cleanup.append("UYARI: pozisyon duz degil: stoplar BIRAKILDI; Binance uygulamasindan elle kapatin")
    except Exception as e:  # noqa: BLE001
        flat = False
        report.cleanup.append(f"DUZLESTIRME HATA {type(e).__name__}: elle kontrol edin (stoplar birakildi)")
    try:
        for row in rest.open_conditionals(ctx.sym):
            c = _cid_of(row)
            if c not in ctx.own:
                report.cleanup.append("UYARI: yabanci acik kosullu emir birakildi (dokunulmadi)")
                continue
            if c.startswith("tr") and len(c) > 3 and c[3] == "s" and not flat:
                continue                                            # pozisyon duz degilse koruyucu stop kalir
            try:
                rest.cancel_conditional(ctx.sym, c)
                report.cleanup.append(f"kosullu emir iptal {c[:8]}")
            except Exception as e:  # noqa: BLE001
                report.cleanup.append(f"kosullu iptal HATA {type(e).__name__}")
        for row in rest.open_orders(ctx.sym):
            c = str(row.get("clientOrderId", ""))
            if c in ctx.own and str(row.get("origType", row.get("type", ""))) not in S_COND_TYPES:
                try:
                    rest.cancel_order(ctx.sym, c)
                    report.cleanup.append(f"emir iptal {c[:8]}")
                except Exception as e:  # noqa: BLE001
                    report.cleanup.append(f"emir iptal HATA {type(e).__name__}")
            elif c not in ctx.own:
                report.cleanup.append("UYARI: yabanci acik emir birakildi (dokunulmadi)")
    except Exception as e:  # noqa: BLE001
        report.cleanup.append(f"emir temizligi HATA {type(e).__name__}")


# ---------------------------------------------------------------------------------------------- ana
def build_parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(prog="smoke_live", description=__doc__.split("\n")[0])
    ap.add_argument("--env", default=None, help="yalniz 'live'; 'testnet' reddedilir")
    ap.add_argument("--list", action="store_true", help="adimlari listele")
    ap.add_argument("--dry-run", action="store_true", help="plani yazdir; ag ve anahtar kullanilmaz")
    ap.add_argument("--config-dir", default="config")
    ap.add_argument("--live-overlay", default=None, help="varsayilan: <config-dir>/engine.live.json (canli katman; zorunlu)")
    ap.add_argument("--pair", default=DEFAULT_PAIR)
    ap.add_argument("--out-root", default=DEFAULT_OUT_ROOT, help="rapor koku (varsayilan var-live)")
    return ap


def main(argv: list[str] | None = None, *, environ=None, rest_factory=None, clock=None, input_fn=input, say=print) -> int:
    a = build_parser().parse_args(argv)
    environ = os.environ if environ is None else environ
    if a.list:
        for s in STEPS:
            say(f"{s.ref:5s} {s.title}")
        return EXIT_OK
    secrets: tuple[str, ...] = tuple(environ.get(n, "") for n in S.KEY_VARS)
    msay = lambda t: say(S.mask(t, secrets))  # noqa: E731
    try:
        guard_env(a.env)
        if a.dry_run:
            print_plan(a.pair, msay)
            return EXIT_OK
        return _run(a, environ, rest_factory, clock, input_fn, msay)
    except PermissionRefused as e:
        msay(f"REDDEDILDI (anahtar izni): {e}")
        return EXIT_PERM
    except S.SafetyError as e:
        msay(f"REDDEDILDI: {e}")
        return EXIT_REFUSED


def _run(a, environ, rest_factory, clock, input_fn, say) -> int:
    from trader_engine.brokers.binance_futures import LiveBroker
    from trader_engine.clock import SystemClock
    from trader_engine.config import load_engine_config
    from trader_engine.errors import ConfigError, EngineExit
    from trader_engine.exchange.binance_rest import SignedRestClient

    d = Path(a.config_dir)
    overlay = Path(a.live_overlay) if a.live_overlay else d / "engine.live.json"
    if not overlay.is_file():
        raise S.SafetyError(f"canli yapilandirma katmani yok: {overlay.name} (--live-overlay)")
    try:
        cfg = load_engine_config(d / "engine.base.json", d / "engine.learner.json", overlay_path=overlay)
    except ConfigError as e:
        raise S.SafetyError(f"yapilandirma hatasi: {e}") from e
    guard_config(cfg, environ)
    key, secret = S.read_keys(environ)
    secrets = (key, secret)
    clk = clock or SystemClock()
    pair = a.pair
    if pair not in cfg.pairs:
        raise S.SafetyError("cift yapilandirmada yok")
    ladder_info = check_ladder_and_holds(cfg, clk)                 # yerel denetimler: ag yok

    now_ms = lambda: int(clk.now().timestamp() * 1000)  # noqa: E731
    rest = (rest_factory or (lambda **kw: SignedRestClient(**kw)))(
        env="live", api_key=key, api_secret=secret, now_ms=now_ms, sleep=clk.sleep,
        recv_window_ms=cfg.live.recv_window_ms, conditional_mode=cfg.live.conditional_mode)
    guard_rest(rest)
    stamp = clk.now().strftime("%Y%m%dT%H%M%SZ")
    report = LiveReport(clk.now().isoformat(), secrets)
    report.meta = {"pair": pair, "env": "live", "account_tag": cfg.live.account_tag, "key": S.mask_key(key),
                   "withdraw_check": "verified_by_api_restrictions", "steps": [s.ref for s in STEPS], **ladder_info}
    ctx: Ctx | None = None
    rc = EXIT_OK
    try:
        try:
            restr = rest.api_restrictions()
        except Exception as e:  # noqa: BLE001  (auth/ban/ag hatasi dahil: dogrulanamadi)
            raise PermissionRefused(f"api_restrictions alinamadi ({type(e).__name__})") from None
        check_permissions(restr)
        env_no_attest = {k: v for k, v in environ.items() if k != "LIVE_PERMISSION_ATTESTED"}   # beyanla gecis yok
        broker = LiveBroker(cfg.live, "live", int(cfg.leverage), [pair], rest, clk, cfg.cost.taker_fee, environ=env_no_attest)
        try:
            broker.startup_check()
        except EngineExit as e:
            report.meta["startup_exit"] = e.code
            say(f"acilis denetimi reddetti: kod {e.code} {S.mask(e, secrets)}")
            return e.code
        ctx = Ctx(rest=rest, broker=broker, clock=clk, pair=pair, cfg=cfg, phrase=phrase_for(cfg.live.account_tag),
                  input_fn=lambda p: input_fn(S.mask(p, secrets)), say=say, recheck=lambda: check_ladder_and_holds(cfg, clk))
        ctx.require_clean()
        for s in STEPS:
            if s.ref == "S-3":
                ctx.confirm_first_order()
            ctx.proceed(f"{s.ref} {s.title}", f"[{s.gate}]")
            res = S.StepResult(s.name, s.ref)
            t0 = time.monotonic()
            try:
                res.status, res.notes, res.data = s.fn(ctx)
            except (Aborted, S.SafetyError):
                res.status, res.notes = "KALDI", ["guvenlik/iptal"]
                report.results.append(res)
                raise
            except Exception as e:  # noqa: BLE001
                res.status, res.notes = "KALDI", [f"istisna {type(e).__name__}: {S.mask(e, secrets)[:200]}"]
            res.seconds = time.monotonic() - t0
            report.results.append(res)
            say(f"{s.ref:5s} {res.status}  {S.mask('; '.join(res.notes), secrets)[:160]}")
            if res.status != "GECTI":
                rc = EXIT_FAIL
                say("adim GECMEDI: kalan adimlar atlanir, temizlik yapilacak")
                break
    except Aborted as e:
        say(f"DURDURULDU: {e}")
        rc = EXIT_REFUSED
    finally:
        if ctx is not None:
            cleanup(ctx, report)
        out = report.write(Path(a.out_root), stamp)
        say(f"rapor: {out}")
    return rc


if __name__ == "__main__":
    sys.exit(main())
