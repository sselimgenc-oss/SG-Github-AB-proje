"""Madde 19: kucuk hesapta boyut bozulmasi. risk.size_position ile ayni aritmetik; hesap yalniz degerlendirmedir."""
from __future__ import annotations

import math
from decimal import Decimal

from trader_core.risk import LOCKED_CFG

from .exits import plain
from .stats import merge, MIN_G, MIN_N, label_basic, mean, pctl, wilson

ASSUMPTION = ("Varsayım: özsermaye W'de sabit, başka açık pozisyon yok, giriş fiyatı planlanan fiyat. Portföy sınırları "
              "(aynı yön, günlük bütçe) hesaba katılmaz.")
STEP_NOTE = "red_min_adet: motorun boyut adımı bunu denetlemez; emir yolunda reddedilir (ayrı sayılır)."


def floor_to_step(qty: float, step: float) -> float:
    d, s = Decimal(repr(qty)), Decimal(repr(step))
    out = float((d // s) * s)
    while out > qty:
        out = math.nextafter(out, 0.0)
    return out


def size_one(e: float, s: float, W: float, tau: float, lev: float, rules, cfg=LOCKED_CFG) -> dict:
    c = cfg.fee_rate + cfg.slippage_rate
    birim = abs(e - s) + e * c + s * c
    qty_risk = tau * W / birim
    qty_tavan = cfg.max_notional_ratio * W / e
    qty_ham = min(qty_risk, qty_tavan)
    qty = floor_to_step(qty_ham, rules.step)
    if qty <= 0 or qty * e < rules.min_notional:
        sonuc = "red_min_emir"
    elif qty * e / lev > W:
        sonuc = "red_teminat"
    elif qty < rules.min_qty:
        sonuc = "red_min_adet"
    else:
        sonuc = "kabul"
    risk = qty * birim
    return {"sonuc": sonuc, "qty": qty, "risk": risk, "risk_orani": risk / (tau * W), "adim_kaybi": 1 - qty / qty_ham,
            "tavan_bagli": qty_tavan < qty_risk, "birim": birim, "qty_risk": qty_risk}


def _valid(d) -> bool:
    e, s = d["planned_entry"], d["planned_stop"]
    if not e or not s or e <= 0 or s <= 0:
        return False
    return s < e if d["side"] == "long" else s > e


def _agg(res: list[dict], gunler: list[str]) -> dict:
    n = len(res)
    out = {"n_aday": n, "n": n, "G": len(set(gunler))}
    for k in ("red_min_emir", "red_min_adet", "red_teminat"):
        c = sum(1 for r in res if r["sonuc"] == k)
        w = wilson(c, n)
        out[k] = c
        out[k + "_oran"] = w["p"]
        out[k + "_aralik"] = [w["lo"], w["hi"]] if w["p"] is not None else None
    red = sum(out[k] for k in ("red_min_emir", "red_min_adet", "red_teminat"))
    out["red_oran"] = red / n if n else None
    out["tavan_bagli_oran"] = (sum(1 for r in res if r["tavan_bagli"]) / n) if n else None
    ro = [r["risk_orani"] for r in res if r["sonuc"] == "kabul"]
    if ro:
        p = pctl(ro, (5, 25, 50))
        merge(out, {"risk_orani_min": min(ro), "risk_orani_p5": p[0], "risk_orani_p25": p[1], "risk_orani_medyan": p[2],
                    "risk_orani_ort": mean(ro)})
    else:
        merge(out, {"risk_orani_min": None, "risk_orani_p5": None, "risk_orani_p25": None, "risk_orani_medyan": None,
                    "risk_orani_ort": None})
    ak = [r["adim_kaybi"] for r in res if r["sonuc"] == "kabul"]
    out["adim_kaybi_medyan"] = pctl(ak, (50,))[0] if ak else None
    out["bayrak"] = ("bozulma" if (n and (out["red_oran"] >= 0.05 or (out["risk_orani_medyan"] is not None
                                                                       and out["risk_orani_medyan"] < 0.90))) else "")
    out["etiket"] = label_basic(n, out["G"])
    return out


COLS = ["pair", "W", "tau", "n_aday", "G", "red_min_emir", "red_min_emir_oran", "red_min_emir_aralik", "red_min_adet",
        "red_min_adet_oran", "red_min_adet_aralik", "red_teminat", "red_teminat_oran", "red_teminat_aralik", "red_oran",
        "tavan_bagli_oran", "risk_orani_min", "risk_orani_p5", "risk_orani_p25", "risk_orani_medyan", "risk_orani_ort",
        "adim_kaybi_medyan", "bayrak", "etiket"]


def build(decisions, trades, rules: dict, wallets, taus, mode_backtest: bool) -> dict:
    blocks: list = []
    notes = [ASSUMPTION, STEP_NOTE]
    srcs = sorted({r.source for r in rules.values() if r is not None})
    notes.append("Kural kaynağı: " + (", ".join(srcs) if srcs else "yok"))
    no_rule = sorted(p for p, r in rules.items() if r is None)
    if no_rule:
        notes.append("kural yok (hesaba girmedi): " + ", ".join(no_rule))
    valid = [d for d in decisions if _valid(d)]
    universes = {"ana": [d for d in valid if d["final_action"] == "entered" or d["skip_reason"] == "risk_denied"],
                 "genis": valid}
    data: dict = {"kural_kaynagi": srcs, "kural_yok": no_rule, "cuzdanlar": list(wallets), "riskler": list(taus), "evren": {}}
    summary_red = None
    for uname, dec in universes.items():
        rows, pooled = [], {}
        pairs = sorted({d["pair"] for d in dec})
        for W in wallets:
            for tau in taus:
                allres, alld = [], []
                for p in pairs:
                    r = rules.get(p)
                    if r is None:
                        continue
                    res, gun = [], []
                    for d in dec:
                        if d["pair"] != p:
                            continue
                        lev = d.get("leverage") or LOCKED_CFG.min_leverage
                        res.append(size_one(d["planned_entry"], d["planned_stop"], W, tau, lev, r))
                        gun.append(d["gun"])
                    if res:
                        a = _agg(res, gun)
                        rows.append({"pair": p, "W": W, "tau": tau, **a})
                        allres += res
                        alld += gun
                if allres:
                    a = _agg(allres, alld)
                    rows.append({"pair": "tümü", "W": W, "tau": tau, **a})
                    pooled[(W, tau)] = a
        blocks.append(plain(f"boyut_{uname}", f"5.{1 if uname == 'ana' else 2} Küçük hesap ({'ana evren: alınan + risk reddi' if uname == 'ana' else 'geniş evren: tüm kararlar'})",
                            COLS, rows, notes))
        comp = []
        if 1000 in wallets or 1000.0 in wallets:
            for tau in taus:
                base = pooled.get((1000, tau))
                for W in wallets:
                    a = pooled.get((W, tau))
                    if base is None or a is None or W == 1000:
                        continue
                    comp.append({"W": W, "tau": tau, "red_oran_fark": (a["red_oran"] - base["red_oran"]),
                                 "medyan_risk_orani_fark": (None if a["risk_orani_medyan"] is None or base["risk_orani_medyan"] is None
                                                            else a["risk_orani_medyan"] - base["risk_orani_medyan"])})
        blocks.append(plain(f"boyut_karsilastirma_{uname}", f"5.{3 if uname == 'ana' else 4} 1000'e göre fark ({uname})",
                            ["W", "tau", "red_oran_fark", "medyan_risk_orani_fark"], comp, []))
        data["evren"][uname] = {"n_karar": len(dec)}
        if uname == "ana" and wallets:
            w0 = min(wallets)
            vals = [pooled[(w0, t)]["red_oran"] for t in taus if (w0, t) in pooled]
            summary_red = vals[0] if vals else None
    if mode_backtest:
        rows = []
        for tau in taus:
            for p in sorted({t["pair"] for t in trades}):
                v = [t["planned_risk"] / (tau * t["equity_at_entry"]) for t in trades
                     if t["pair"] == p and t.get("equity_at_entry")]
                if v:
                    q = pctl(v, (5, 25, 50))
                    rows.append({"pair": p, "tau": tau, "n": len(v), "min": min(v), "p5": q[0], "p25": q[1], "medyan": q[2],
                                 "ort": mean(v), "max": max(v)})
        blocks.append(plain("gercek_risk_orani", "5.5 Gerçekleşen risk oranı (planned_risk / (τ·özsermaye))",
                            ["pair", "tau", "n", "min", "p5", "p25", "medyan", "ort", "max"], rows, []))
    return {"blocks": blocks, "data": data, "ozet_red": summary_red}
