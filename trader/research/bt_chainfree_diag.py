#!/usr/bin/env python3
"""Zincirsiz tani (06-crosscheck-sonuc.md, mentor karari adim 4 ve 17 Kasim kapisi a/b).
GIRIS (a): her referans girisi icin motorun boyutlandirmasi (`risk.check_entry`) REFERANSIN KENDI durumundan yeniden
hesaplanir: cuzdan = baslangic + giris aninda kapanmis referans islemlerin `profit_abs` toplami (komisyon + funding dahil,
TAM), ozsermaye = cuzdan + acik referans pozisyonlarin `calc_profit` (son kapanmis ana-tf mumu, komisyonlu), gun basi
ozsermayesi = cuzdan - bugun (UTC) kapanan K/Z, acik pozisyonlar referanstan (planned_risk, stake). Sonra freqtrade'in kendi
stake kisma kurali (docs 06 "Adim 5": min(karar marji, 0.99*cuzdan - acik stake'ler)) ve stake->miktar kesmesi uygulanir.
`--equity est` eski tahmini (`equity_entry_est`, kisma kurali yok) kullanir.
CIKIS (b): motor calismasi (`--engine-dir`, bayrak-kapali uyum motoru) ile anahtari eslesen islemlerde cikis nedeni +
zamani + fiyat (<= 1 tik) karsilastirilir.
Kullanim: python research/bt_chainfree_diag.py --id 1h_IS_f1_s0 --tf 1h [--engine-dir D] [--out-dir D]
Cikti: <out>/<id>_chainfree.json + ozet satirlari. Freqtrade calistirilmaz."""
from __future__ import annotations

import argparse
import itertools
import json
import sys
from decimal import ROUND_DOWN, Decimal
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from trader_core import risk as K  # noqa: E402
from trader_engine.marketdata.sources import HistoricalSource  # noqa: E402
import bt_crosscheck as X  # noqa: E402

SIZE_TOL = 0.005
START = 1000.0
ORDER = "pair"
# ayni mumda kapanan islemin giris anindaki durumu (ampirik, 4 kosuda en iyi uyum; 06 §"Adim 4"): 1h kosularda ayni mumdaki tum
# kapanislar cuzdanda, 15m kosuda yalniz giris yapan cifte gore ONCE gelen ciftlerin kapanislari
SAME_CLOSE = {"1h": "all", "15m": "lt"}
TRADABLE_RATIO = 0.99
PAIR_ORDER = ["BTC/USDT", "ETH/USDT", "BNB/USDT", "SOL/USDT", "XRP/USDT", "DOGE/USDT", "ADA/USDT", "TRX/USDT", "LINK/USDT",
              "AVAX/USDT"]
TF = {"1h": pd.Timedelta(hours=1), "15m": pd.Timedelta(minutes=15)}


def trunc_step(x: float, step: float) -> float:
    d, q = Decimal(repr(float(x))), Decimal(repr(float(step)))
    return float((d / q).to_integral_value(rounding=ROUND_DOWN) * q)


def _prices(hist: Path, tf: str) -> dict:
    px = {}
    for f in hist.glob(f"*-{tf}-futures.feather"):
        stem = f.name.split(f"-{tf}")[0]                       # BTC_USDT_USDT
        d = pd.read_feather(f)[["date", "close"]]
        px[stem.split("_")[0] + "/USDT"] = d.set_index("date")["close"]
    return px


def load_ref(ref_dir: Path, tf: str = "1h") -> pd.DataFrame:
    t = pd.read_csv(ref_dir / "trades_enriched.csv")
    t["pairc"] = t["pair"].map(X.canon)
    t["side"] = np.where(t["is_short"], "short", "long")
    t["open_ts"] = pd.to_datetime(t["open_date"], utc=True)
    t["close_ts"] = pd.to_datetime(t["close_date"], utc=True)
    t["porder"] = [PAIR_ORDER.index(p) if p in PAIR_ORDER else 99 for p in t["pairc"]]
    t = t.sort_values(["open_ts"] + (["porder"] if ORDER == "pair" else []), kind="stable").reset_index(drop=True)
    _, rtr = X.read_ledger(ref_dir)
    rtr = rtr.copy()
    rtr["key"] = list(zip(rtr["pair"], rtr["side"], pd.to_datetime(rtr["entry_ts"], utc=True)))
    t["key"] = list(zip(t["pairc"], t["side"], t["open_ts"]))
    t = t.merge(rtr[["key", "exit_reason", "exit_ts", "exit_price"]].rename(
        columns={"exit_reason": "lg_reason", "exit_ts": "lg_exit_ts", "exit_price": "lg_exit_price"}), on="key", how="left")
    return fill_reentry(t, tf)


def fill_reentry(t: pd.DataFrame, tf: str) -> pd.DataFrame:
    """freqtrade ayni sinyal mumunda stop sonrasi yeniden girer (giris :15/:30 gibi); ledger'da karar satiri yoktur
    (`planned_stop` bos). Planli stop/risk, ayni mumdaki onceki ayni cift+yon isleminden alinir (ayni sinyal satiri)."""
    t = t.copy()
    t["reentry"] = False
    t["bar"] = t["open_ts"].dt.floor(tf.replace("m", "min"))
    for k in range(len(t)):
        if np.isfinite(t.at[k, "planned_stop"]):
            continue
        r = t.iloc[k]
        prev = t.iloc[:k]
        prev = prev[(prev["pairc"] == r.pairc) & (prev["side"] == r.side) & (prev["bar"] == r.bar) & prev["planned_stop"].notna()]
        if len(prev):
            t.at[k, "planned_stop"] = float(prev.iloc[-1]["planned_stop"])
            t.at[k, "planned_risk"] = float(K.loss_at_stop(float(r.amount), float(r.open_rate), float(prev.iloc[-1]["planned_stop"]),
                                                           K.LOCKED_CFG))
            t.at[k, "reentry"] = True
    return t


def ref_state(t: pd.DataFrame, k: int, px: dict, tf: str) -> dict:
    """Referans durumu k. girisin anindaki: cuzdan, acik pozisyonlar, ozsermaye, gun basi ozsermayesi."""
    r = t.iloc[k]
    # freqtrade backtest dongusu cift sirasiyla: ayni mumda kapanan bir islem, giris yapan cifte gore SONRA gelen ciftteyse henuz
    # kapanmamistir (kar/zarari cuzdana yazilmaz, pozisyon acik sayilir)
    same_done = {"all": True, "none": False, "lt": t["porder"] < r.porder, "le": t["porder"] <= r.porder,
                 "gt": t["porder"] > r.porder}[SAME_CLOSE[tf] if isinstance(SAME_CLOSE, dict) else SAME_CLOSE]
    done = (t["close_ts"] < r.open_ts) | ((t["close_ts"] == r.open_ts) & same_done)
    closed = t[done]
    wallet = START + float(closed["profit_abs"].sum())
    ds = r.open_ts.floor("1D")
    realized_today = float(closed.loc[closed["close_ts"] >= ds, "profit_abs"].sum())
    prev = t.iloc[:k]
    opens = t[(~done) & (t["open_ts"] <= r.open_ts) & (t.index != k)
              & ((t["open_ts"] < r.open_ts) | (t.index < k))]
    unreal, pos, tied = 0.0, [], 0.0
    ts = r.open_ts - TF[tf]
    for o in opens.itertuples():
        s = px.get(o.pairc)
        p = float(o.open_rate)
        if s is not None:
            i = s.index.searchsorted(ts, side="right") - 1
            if i >= 0:
                p = float(s.iloc[i])
        sign = -1.0 if o.is_short else 1.0
        unreal += o.amount * (p - o.open_rate) * sign - o.amount * o.open_rate * o.fee_open - o.amount * p * o.fee_close
        pos.append(K.OpenPosition(o.pairc, o.side, float(o.planned_risk), float(o.stake_amount)))
        tied += float(o.stake_amount)
    return dict(wallet=wallet, equity=wallet + unreal, day_start=wallet - realized_today, pos=pos, tied=tied)


def predict(r, st: dict, rules, lev: float, mode: str) -> dict:
    if mode == "est":
        eq = float(r.equity_entry_est)
        state = K.AccountState(equity=eq, day_start_equity=eq, open_positions=st["pos"])
    else:
        state = K.AccountState(equity=st["equity"], day_start_equity=st["day_start"], open_positions=st["pos"])
    cand = K.Candidate(r.pairc, r.side, float(r.open_rate), float(r.planned_stop), float(lev), rules.step, rules.min_notional)
    dec = K.check_entry(state, cand, K.LOCKED_CFG)
    out = dict(allowed=bool(dec.allowed), reason=None if dec.allowed else dec.reason, margin=None, avail=None, cut=False,
               amount=None, amount_nocut=None)
    if not dec.allowed:
        return out
    m = float(dec.size.margin)
    out["margin"] = m
    out["amount_nocut"] = trunc_step((m / float(r.open_rate)) * lev, rules.step)
    mm = m
    if mode != "est":
        avail = TRADABLE_RATIO * st["wallet"] - st["tied"]
        out["avail"] = avail
        if avail < m:
            mm, out["cut"] = avail, True
    out["amount"] = trunc_step((mm / float(r.open_rate)) * lev, rules.step) if mm > 0 else 0.0
    return out


def entries(t, px, src, tf, mode, lev):
    rows = []
    for k in range(len(t)):
        r = t.iloc[k]
        rules = src.rules(r.pairc)
        st = ref_state(t, k, px, tf)
        p = predict(r, st, rules, lev, mode)
        a = p["amount"]
        ok = a is not None and abs(a - r.amount) <= SIZE_TOL * max(r.amount, 1e-12) + 1e-12
        exact = a is not None and abs(a - r.amount) <= 1e-9 * max(r.amount, 1.0)
        rows.append(dict(i=k, pair=r.pairc, side=r.side, entry_ts=str(r.open_ts), ref_amount=float(r.amount), pred_amount=a,
                         pred_nocut=p["amount_nocut"], pred_cut=p["cut"], allowed=p["allowed"], deny=p["reason"], ok=bool(ok),
                         exact=bool(exact), step=rules.step, wallet=st["wallet"], equity=st["equity"], tied=st["tied"],
                         n_open=len(st["pos"]), ref_stake=float(r.stake_amount), ref_margin_dec=None))
    return rows


def cause(row: dict, t: pd.DataFrame) -> str:
    """Kalan satirin nedeni (kural tabanli; tahmin yok)."""
    r = t.iloc[row["i"]]
    if bool(r.get("reentry", False)):
        return "ayni_mum_yeniden_giris: freqtrade ayni sinyal mumunda stop sonrasi yeniden girdi (ledger karari yok; motor mum basina tek karar)"
    if not row["allowed"]:
        return f"riskte_red: {row['deny']} (zincirsiz motor reddeder; referans girmis)"
    same = t[(t["open_ts"] == r.open_ts)]
    rel = (row["pred_amount"] - row["ref_amount"]) / max(row["ref_amount"], 1e-12)
    step_rel = row["step"] / max(row["ref_amount"], 1e-12)
    if bool(r.get("reentry", False)):
        return "ayni_mum_yeniden_giris: freqtrade ayni sinyal mumunda stop sonrasi yeniden girdi (ledger karari yok; motor mum basina tek karar)"
    if abs(row["pred_amount"] - row["ref_amount"]) <= 1.5 * row["step"] + 1e-12:
        return "tek_adim_kesme: <=1 adim (karar marji/stake kesme kayan nokta siniri)"
    if len(same) > 1:
        return f"ayni_mum_giris_sirasi: {len(same)} giris ayni mumda; freqtrade isleme sirasi bilinmiyor (kisma/risk toplami)"
    if row["pred_cut"]:
        return f"kisma_kurali_kalan: tahmin {rel:+.2%}; kuralda aciklanmayan cuzdan farki"
    return f"ozsermaye_tanimi: tahmin {rel:+.2%} (acik poz. funding/calc_profit ya da risk_amount farki)"


def exits(ref_dir: Path, eng_dir: Path, src: HistoricalSource, tf: str) -> dict:
    _, rtr = X.read_ledger(ref_dir)
    _, etr = X.read_ledger(eng_dir)
    for d in (rtr, etr):
        d["key"] = list(zip(d["pair"], d["side"], pd.to_datetime(d["entry_ts"], utc=True)))
        d["exit_t"] = pd.to_datetime(d["exit_ts"], utc=True)
    em = {k: row for k, row in zip(etr["key"], etr.to_dict("records"))}
    n = nm = n_reason = n_time = n_both = n_price = n_all = 0
    rows = []
    for r in rtr.itertuples():
        e = em.get(r.key)
        if e is None:
            continue
        n += 1
        tick = src.tick_at(r.pair, pd.Timestamp(r.key[2]).to_pydatetime())
        reason = r.exit_reason == e["exit_reason"]
        time = r.exit_t == e["exit_t"]
        px = abs(float(r.exit_price) - float(e["exit_price"])) <= tick * (1 + 1e-9)
        n_reason += reason
        n_time += time
        n_both += reason and time
        n_price += px
        n_all += reason and time and px
        if not (reason and time and px):
            rows.append(dict(pair=r.key[0], side=r.key[1], entry_ts=str(r.key[2]), ref_reason=r.exit_reason, eng_reason=e["exit_reason"],
                             ref_exit=str(r.exit_t), eng_exit=str(e["exit_t"]), ref_px=float(r.exit_price),
                             eng_px=float(e["exit_price"]), tick=tick, reason_ok=bool(reason), time_ok=bool(time), px_ok=bool(px)))
    pct = lambda x: 100.0 * x / max(n, 1)  # noqa: E731
    return dict(n_key_matched=n, reason_pct=pct(n_reason), time_pct=pct(n_time), reason_and_time_pct=pct(n_both),
                price_1tick_pct=pct(n_price), all_pct=pct(n_all), mismatches=rows)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(allow_abbrev=False)
    ap.add_argument("--id", required=True)
    ap.add_argument("--tf", default="1h", choices=["1h", "15m"])
    ap.add_argument("--equity", default="wallet", choices=["wallet", "est"])
    ap.add_argument("--engine-dir", default=None)
    ap.add_argument("--out-dir", default=str(ROOT / "research" / "crosscheck"))
    ap.add_argument("--history-dir", default=str(ROOT / "user_data" / "data" / "binance" / "futures"))
    ap.add_argument("--suffix", default="")
    a = ap.parse_args(argv)
    ref = ROOT / "user_data" / "backtest_results" / a.id
    hist = Path(a.history_dir)
    t = load_ref(ref, a.tf)
    px = _prices(hist, a.tf)
    src = HistoricalSource(a.history_dir, granularity="15m", synthetic_rules=True)
    src.main_tf = a.tf
    lev = K.LOCKED_CFG.min_leverage
    rows = entries(t, px, src, a.tf, a.equity, lev)
    n = len(rows)
    n_ok = sum(r["ok"] for r in rows)
    n_exact = sum(r["exact"] for r in rows)
    rem = [dict(r, cause=cause(r, t)) for r in rows if not r["ok"]]
    out = dict(id=a.id, tf=a.tf, equity_mode=a.equity, n_ref=n, entries_match=n_ok, entries_match_pct=100.0 * n_ok / n,
               entries_exact=n_exact, entries_exact_pct=100.0 * n_exact / n, n_pred_cut=sum(r["pred_cut"] for r in rows),
               remaining=rem, remaining_causes={})
    for x in rem:
        k = x["cause"].split(":")[0]
        out["remaining_causes"][k] = out["remaining_causes"].get(k, 0) + 1
    msg = (f"[{a.id}] giris (zincirsiz, {a.equity}): {n_ok}/{n} ({out['entries_match_pct']:.2f}%), kesin {n_exact} "
           f"({out['entries_exact_pct']:.2f}%), kalan {len(rem)}: {out['remaining_causes']}")
    if a.engine_dir:
        ex = exits(ref, Path(a.engine_dir), src, a.tf)
        out["exits"] = ex
        msg += (f"\n[{a.id}] cikis ({a.engine_dir}): anahtar-eslesen {ex['n_key_matched']}, neden {ex['reason_pct']:.2f}% "
                f"zaman {ex['time_pct']:.2f}% neden+zaman {ex['reason_and_time_pct']:.2f}% fiyat<=1tik {ex['price_1tick_pct']:.2f}% "
                f"hepsi {ex['all_pct']:.2f}%")
    Path(a.out_dir).mkdir(parents=True, exist_ok=True)
    (Path(a.out_dir) / f"{a.id}_chainfree{a.suffix}.json").write_text(json.dumps(out, indent=1, default=str))
    print(msg)
    return 0


if __name__ == "__main__":
    sys.exit(main())
