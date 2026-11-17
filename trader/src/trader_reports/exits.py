"""Madde 4: cikis karnesi (cikis sonrasi yol, geri verme, cikis verimi, kazananlarin ters gezintisi, +1R oncesi gezinti,
bariyer yarisi merdiveni, islem basina tek satir neden). Yalniz degerlendirme; canli girdi degildir."""
from __future__ import annotations

import math

from trader_core.risk import LOCKED_CFG

from . import inputs as I
from .stats import (DASH, MIN_G, MIN_N, WILSON_NOTE, SubTable, cluster_mean, label_basic, mean, pctl, tr_isaretli, tr_sayi,
                    wilson)

HOUR = 3_600_000
HORIZONS = (24, 72)
STOP_NOTE = "stopu genişletme kanıtı sayılmaz"
SURVIVOR_NOTE = ("Stop olan işlemler tanım gereği kazanan değildir; bu dağılım 1R'de kesiktir (hayatta kalan yanlılığı).")
STOP_WIDTH_NOTE = ("Stop mesafesi değişirse pozisyon boyutu ve RR kapısı da değişir; bu tablo tek başına stop ayarı kanıtı değildir.")
LADDER_NOTE = "1 saatlik mumla; mum içi sıra bilinmez (stop önce varsayımı)."
PEAK_NOTE = "tepe önceden bilinemez; üst sınır"
REASON_TR = {"stop": "ilk stop", "trail_stop": "iz süren stop", "target": "hedef", "regime_flip": "piyasa koşulu değişimi",
             "time_stop": "süre sınırı", "manual": "elle kapatma", "force_exit": "zorunlu kapatma", "liquidation": "likidasyon",
             "other": "diğer"}
SIDE_TR = {"long": "alış", "short": "satış"}
LADDER_K = (0.5, 1.0, 1.5, 2.0, 3.0)


def plain(tid, title, columns, rows, notes=()):
    return {"kind": "table", "id": tid, "title": title, "columns": list(columns), "rows": rows, "notes": list(notes)}


def _dir(side: str) -> int:
    return 1 if side == "long" else -1


def reason_line(t: dict) -> str:
    """B-27: kural tabanli tek satir."""
    nd = REASON_TR.get(t["exit_reason"], REASON_TR["other"])
    side = SIDE_TR.get(t["side"], t["side"])
    net = tr_isaretli(t["net_r"], 1)
    if t.get("mfe_r") is not None and t.get("gross_r") is not None:
        gv = t["mfe_r"] - t["gross_r"]
        return f"{t['pair']} {side}: en çok +{tr_sayi(t['mfe_r'], 1)}R gördü, {nd} ile {net}R kapandı; tepeden {tr_sayi(gv, 1)}R geri verdi."
    return f"{t['pair']} {side}: {nd} ile {net}R kapandı."


# --------------------------------------------------------------------------- 6.1 cikis sonrasi yol
def post_path(t: dict, reader, now_ms: int, h: int) -> dict:
    r = t.get("r_px")
    start = I.ceil_hour(I.iso_ms(t["exit_ts"]))
    if now_ms < start + h * HOUR:
        return {"durum": "pending"}
    if not r or r <= 0:
        return {"durum": "data_gap"}
    st, rows = I.get_window(reader, t["pair"], "1h", start, h)
    if st != "ok":
        return {"durum": st}
    d = _dir(t["side"])
    ex = t["exit_price"]
    hi = max(x[1] for x in rows)
    lo = min(x[2] for x in rows)
    if d > 0:
        fav, adv = max(0.0, hi - ex) / r, max(0.0, ex - lo) / r
    else:
        fav, adv = max(0.0, ex - lo) / r, max(0.0, hi - ex) / r
    close = d * (rows[-1][3] - ex) / r
    fl, al = ex + d * r, ex - d * r
    i_f = i_a = None
    for k, (_, h_, l_, _c) in enumerate(rows):
        tf_ = (h_ >= fl) if d > 0 else (l_ <= fl)
        ta_ = (l_ <= al) if d > 0 else (h_ >= al)
        if tf_ and i_f is None:
            i_f = k
        if ta_ and i_a is None:
            i_a = k
        if i_f is not None and i_a is not None:
            break
    if i_f is not None and (i_a is None or i_f < i_a):
        touch = "lehte"
    elif i_a is not None:
        touch = "aleyhte"
    else:
        touch = "yok"
    return {"durum": "ok", "fav": fav, "adv": adv, "close": close, "touch": touch, "erken": 1 if touch == "lehte" else 0}


# --------------------------------------------------------------------------- 6.5 +1R oncesi gezinti
def pre1r(rows, d: int, entry: float, r_px: float) -> tuple[float, bool]:
    """(+1R'den kesin onceki mumlarda en buyuk aleyhte gezinti / r_px, 1R'ye ulasti mi)."""
    lvl = entry + d * r_px
    k_star = None
    for k, (_, h, l, _c) in enumerate(rows):
        if (d > 0 and h >= lvl) or (d < 0 and l <= lvl):
            k_star = k
            break
    upto = rows if k_star is None else rows[:k_star]
    if not upto:
        return 0.0, k_star is not None
    if d > 0:
        adv = max(0.0, entry - min(x[2] for x in upto))
    else:
        adv = max(0.0, max(x[1] for x in upto) - entry)
    return adv / r_px, k_star is not None


def _pct_row(vals, qs=(50, 75, 85, 95)):
    return pctl(vals, qs) if vals else [None] * len(qs)


def build(trades: list[dict], decisions: list[dict], cf: dict | None, reader, now_ms: int, section: str = "exits") -> dict:
    counters = {"pending": 0, "data_gap": 0, "holdout_skipped_windows": 0}
    blocks: list = []
    csv_rows: list[dict] = []
    n_trades = len(trades)

    # ---- 6.1 + hesaplar
    for t in sorted(trades, key=lambda x: (x["pair"], x["trade_id"])):   # cift bazinda: mum dosyasi onbellegi sinirli
        t["post"] = {h: post_path(t, reader, now_ms, h) for h in HORIZONS}
        for h in HORIZONS:
            d = t["post"][h]["durum"]
            if d == "pending":
                counters["pending"] += 1
            elif d == "data_gap":
                counters["data_gap"] += 1
            elif d == "holdout_skipped":
                counters["holdout_skipped_windows"] += 1
        mfe, mae, g = t.get("mfe_r"), t.get("mae_r"), t.get("gross_r")
        t["gezinti"] = mfe is not None and mae is not None
        t["geri_verme_r"] = (mfe - g) if (t["gezinti"] and g is not None) else None
        t["verim"], t["verim_kirpildi"] = None, False
        if t["gezinti"] and g is not None:
            den = mfe + mae
            if den >= 0.05:
                v = (g + mae) / den
                if v < 0.0 or v > 1.0:
                    t["verim_kirpildi"] = True
                    v = min(1.0, max(0.0, v))
                t["verim"] = v
    gez = [t for t in trades if t["gezinti"]]
    n_gezinti_yok = n_trades - len(gez)

    reasons = sorted({t["exit_reason"] for t in trades})
    cells = []
    for rs in reasons:
        ts_ = [t for t in trades if t["exit_reason"] == rs]
        items = [(t["post"][72]["close"], t["gun"], t["entry_ts"]) for t in ts_ if t["post"][72]["durum"] == "ok"]
        ex = {"n_islem": len(ts_)}
        for h in HORIZONS:
            ok = [t for t in ts_ if t["post"][h]["durum"] == "ok"]
            w = wilson(sum(t["post"][h]["erken"] for t in ok), len(ok))
            ex[f"n_ok_{h}"] = len(ok)
            ex[f"erken_cikis_{h}"] = w["p"]
            ex[f"erken_cikis_{h}_aralik"] = [w["lo"], w["hi"]] if w["p"] is not None else None
            for s in ("pending", "data_gap", "holdout_skipped"):
                ex[f"{s}_{h}"] = sum(1 for t in ts_ if t["post"][h]["durum"] == s)
        oks = [t for t in ts_ if t["post"][72]["durum"] == "ok"]
        ex["ort_post_fav_r_72"] = mean([t["post"][72]["fav"] for t in oks]) if oks else None
        if rs == "stop":
            ex["not"] = STOP_NOTE
        cells.append((rs, items, ex))
    def xpost(r):
        r["n_ok"] = r["n"]          # olcum (72) icin ok satir sayisi
        r["n"] = r["n_islem"]       # n = dondeki tum islemler (spec 6.1)
    extra = ["n_islem", "n_ok", "n_ok_24", "erken_cikis_24", "n_ok_72", "erken_cikis_72", "erken_cikis_72_aralik",
             "ort_post_fav_r_72", "pending_24", "data_gap_24", "holdout_skipped_24", "pending_72", "data_gap_72",
             "holdout_skipped_72", "not"]
    blocks.append(SubTable("exit_sonrasi_yol", "1.1 Çıkış sonrası yol (çıkış nedenine göre)", "post_close_r_72", cells, extra,
                           [WILSON_NOTE, f"Ortalama post_fav_r_72: {PEAK_NOTE}.", f"`stop` satırı: {STOP_NOTE}.",
                            "Çıkış sonrası yol geleceği kullanır; yalnız değerlendirmedir."], section, xpost))

    # ---- 6.2 geri verme
    rows = []
    for th in (0.5, 1.0):
        reach = [t for t in gez if t["mfe_r"] >= th]
        geri = [t for t in reach if t["net_r"] < 0]
        w = wilson(len(geri), len(reach))
        cm = cluster_mean([1.0] * len(reach), [t["gun"] for t in reach])
        rows.append({"esik_r": th, "n_ulasan": len(reach), "n_geri": len(geri), "G": cm["G"], "oran": w["p"],
                     "aralik": [w["lo"], w["hi"]] if w["p"] is not None else None,
                     "toplam_r_geri": math.fsum(t["net_r"] for t in geri),
                     "etiket": label_basic(len(reach), cm["G"])})
    blocks.append(plain("geri_verme", "1.2 Geri verme: kâra geçip zararla kapanan",
                        ["esik_r", "n_ulasan", "n_geri", "G", "oran", "aralik", "toplam_r_geri", "etiket"], rows, [WILSON_NOTE]))
    brow = []
    for lo, hi, nm in ((0.5, 1.0, "[0,5;1)"), (1.0, 2.0, "[1;2)"), (2.0, math.inf, "[2;∞)")):
        ts_ = [t for t in gez if lo <= t["mfe_r"] < hi]
        w = wilson(sum(1 for t in ts_ if t["net_r"] < 0), len(ts_))
        gv = [t["geri_verme_r"] for t in ts_ if t["geri_verme_r"] is not None]
        cm = cluster_mean([1.0] * len(ts_), [t["gun"] for t in ts_])
        brow.append({"bant": nm, "n": len(ts_), "G": cm["G"], "zararla_kapanan_orani": w["p"],
                     "aralik": [w["lo"], w["hi"]] if w["p"] is not None else None,
                     "ort_geri_verme_r": mean(gv) if gv else None, "etiket": label_basic(len(ts_), cm["G"])})
    blocks.append(plain("geri_verme_bant", "1.2b Tepe bantlarına göre geri verme",
                        ["bant", "n", "G", "zararla_kapanan_orani", "aralik", "ort_geri_verme_r", "etiket"], brow, [WILSON_NOTE]))
    cells = []
    for rs in reasons:
        its = [(t["geri_verme_r"], t["gun"], t["entry_ts"]) for t in gez if t["exit_reason"] == rs and t["geri_verme_r"] is not None]
        cells.append((rs, its, {}))
    blocks.append(SubTable("geri_verme_neden", "1.2c Çıkış nedenine göre ortalama geri verme", "geri_verme_r", cells, [], [], section))

    # ---- 6.3 verim
    vt = [t for t in gez if t["verim"] is not None]
    n_tanimsiz = sum(1 for t in gez if t["verim"] is None)
    n_kirpilan = sum(1 for t in gez if t["verim_kirpildi"])
    for key, title, tid in (("setup", "1.3 Çıkış verimi (kurulum)", "verim_kurulum"), ("exit_reason", "1.3b Çıkış verimi (çıkış nedeni)", "verim_neden")):
        cells = [(v, [(t["verim"], t["gun"], t["entry_ts"]) for t in vt if t[key] == v], {})
                 for v in sorted({t[key] for t in vt})]
        blocks.append(SubTable(tid, title, "verim", cells, [], [f"Tanımsız (payda < 0,05): {n_tanimsiz}; kırpılan: {n_kirpilan}."], section))
    weeks: dict[str, list[float]] = {}
    for t in vt:
        weeks.setdefault(I.iso_week(t["exit_ts"]), []).append(t["verim"])
    wrows = [{"hafta": w, "n": len(v), "ort_verim": (mean(v) if len(v) >= 5 else None)} for w, v in sorted(weeks.items())]
    blocks.append(plain("verim_hafta", "1.3c Haftalık çıkış verimi", ["hafta", "n", "ort_verim"], wrows, ["n < 5 olan hafta: —"]))

    # ---- 6.4 kazananlarin ters gezintisi
    wins = [t for t in gez if t["net_r"] > 0]
    wrows, sentences = [], []
    keys = sorted({(t["setup"], t["side"]) for t in wins})
    for (su, sd) in keys:
        ts_ = [t for t in wins if t["setup"] == su and t["side"] == sd]
        mae = [t["mae_r"] for t in ts_]
        atr = [t["mae_r"] * t["r_px"] / t["atr"] for t in ts_ if t.get("atr") and t.get("r_px")]
        p = _pct_row(mae)
        pa = _pct_row(atr) if atr else [None] * 4
        share = sum(1 for m in mae if m >= 0.9) / len(mae)
        cm = cluster_mean(mae, [t["gun"] for t in ts_])
        okuma = ""
        if len(ts_) >= MIN_N:
            if p[2] <= 0.6:
                okuma = "stop gerekenden geniş olabilir (varsayım)"
            elif share >= 0.20:
                okuma = "stop dar olabilir (varsayım)"
        if okuma:
            sentences.append(f"{su} {SIDE_TR[sd]}: {okuma}")
        wrows.append({"hucre": f"{su} × {sd}", "n": len(ts_), "G": cm["G"], "p50": p[0], "p75": p[1], "p85": p[2], "p95": p[3],
                      "pay_mae_ge_0_9": share, "atr_p50": pa[0], "atr_p75": pa[1], "atr_p85": pa[2], "atr_p95": pa[3],
                      "okuma": okuma, "etiket": label_basic(len(ts_), cm["G"])})
    blocks.append(plain("kazanan_mae", "1.4 Kazananların ters gezintisi (mae_r, R biriminde; atr_* ATR biriminde)",
                        ["hucre", "n", "G", "p50", "p75", "p85", "p95", "pay_mae_ge_0_9", "atr_p50", "atr_p75", "atr_p85", "atr_p95",
                         "okuma", "etiket"], wrows, [SURVIVOR_NOTE]))

    # ---- 6.5 +1R oncesi gezinti
    grp: dict[tuple, list] = {}
    for t in sorted(gez, key=lambda x: (x["pair"], x["trade_id"])):
        if not t.get("r_px") or t["r_px"] <= 0:
            continue
        sd = abs(t["entry_price"] - t["planned_stop"])
        if sd <= 0:
            continue
        en, ex = I.iso_ms(t["entry_ts"]), I.iso_ms(t["exit_ts"])
        tf, step = "15m", 900_000
        start = I.floor_to(en, step)
        n = (I.floor_to(ex, step) - start) // step + 1
        if n > 3000:
            tf, step = "1h", HOUR
            start = I.floor_to(en, step)
            n = (I.floor_to(ex, step) - start) // step + 1
        st, rows_ = I.get_window(reader, t["pair"], tf, start, n)
        if st != "ok":
            counters["holdout_skipped_windows" if st == "holdout_skipped" else "data_gap"] += 1
            continue
        mae1, reached = pre1r(rows_, _dir(t["side"]), t["entry_price"], t["r_px"])
        use = mae1 * t["r_px"] / sd
        ua = (mae1 * t["r_px"] / t["atr"]) if t.get("atr") else None
        grp.setdefault(("alındı", "1R'ye ulaştı" if reached else "ulaşmadı"), []).append((use, ua, t["gun"]))
    atr_by_id = {x["id"]: x["atr"] for x in decisions}
    if cf:
        for did, d in sorted(cf.items(), key=lambda kv: (kv[1]["barrier"] or {}).get("pair", "")):
            b = d.get("barrier")
            if not b or b["exit_reason"] not in ("target", "stop", "time"):
                continue
            r_px = abs(b["planned_entry"] - b["planned_stop"])
            if r_px <= 0:
                continue
            st, rows_ = I.get_window(reader, b["pair"], "1h", I.iso_ms(b["window_start_ts"]), 72)
            if st != "ok":
                counters["holdout_skipped_windows" if st == "holdout_skipped" else "data_gap"] += 1
                continue
            mae1, reached = pre1r(rows_, _dir(b["side"]), b["planned_entry"], r_px)
            atr = atr_by_id.get(did)
            ua = (mae1 * r_px / atr) if atr else None
            grp.setdefault(("aday (alınmadı)", "1R'ye ulaştı" if reached else "ulaşmadı"), []).append((mae1, ua, b["decision_ts"][:10]))
    prow = []
    for key in sorted(grp):
        v = grp[key]
        use = [x[0] for x in v]
        ua = [x[1] for x in v if x[1] is not None]
        p, pa = _pct_row(use), (_pct_row(ua) if ua else [None] * 4)
        cm = cluster_mean(use, [x[2] for x in v])
        prow.append({"kaynak": key[0], "grup": key[1], "n": len(v), "G": cm["G"], "kullanim_p50": p[0], "kullanim_p75": p[1],
                     "kullanim_p85": p[2], "kullanim_p95": p[3], "atr_p50": pa[0], "atr_p75": pa[1], "atr_p85": pa[2],
                     "atr_p95": pa[3], "etiket": label_basic(len(v), cm["G"])})
    blocks.append(plain("on1r_gezinti", "1.5 +1R'den önceki ters gezinti (stop mesafesinin kullanılan payı)",
                        ["kaynak", "grup", "n", "G", "kullanim_p50", "kullanim_p75", "kullanim_p85", "kullanim_p95", "atr_p50",
                         "atr_p75", "atr_p85", "atr_p95", "etiket"], prow, [STOP_WIDTH_NOTE]))

    # ---- 6.6 bariyer yarisi merdiveni
    blocks.append(_ladder(trades, decisions, reader, now_ms, counters))

    # ---- csv
    for t in trades:
        row = {"trade_id": t["trade_id"], "pair": t["pair"], "side": t["side"], "setup": t["setup"], "regime": t["regime"],
               "exit_reason": t["exit_reason"], "net_r": t["net_r"], "gross_r": t["gross_r"], "mfe_r": t.get("mfe_r"),
               "mae_r": t.get("mae_r"), "geri_verme_r": t["geri_verme_r"], "verim": t["verim"]}
        for h in HORIZONS:
            p = t["post"][h]
            row[f"post_fav_r_{h}"] = p.get("fav")
            row[f"post_adv_r_{h}"] = p.get("adv")
            row[f"post_close_r_{h}"] = p.get("close")
            row[f"ilk_dokunus_{h}"] = p.get("touch")
            row[f"erken_cikis_{h}"] = p.get("erken")
        for h in HORIZONS:
            row[f"durum_{h}"] = t["post"][h]["durum"]
        row["ozet"] = reason_line(t)
        csv_rows.append(row)

    ok72 = [t for t in trades if t["post"][72]["durum"] == "ok"]
    reach05 = [t for t in gez if t["mfe_r"] >= 0.5]
    ozet = {"n_islem": n_trades, "ort_net_r": mean([t["net_r"] for t in trades]) if trades else None,
            "n_ulasan_05": len(reach05), "n_geri_05": sum(1 for t in reach05 if t["net_r"] < 0),
            "n_ok_72": len(ok72), "erken_72": sum(t["post"][72]["erken"] for t in ok72)}
    return {"blocks": blocks, "csv_rows": csv_rows, "counters": counters, "ozet": ozet,
            "data": {"n_islem": n_trades, "n_gezinti_yok": n_gezinti_yok, "n_tanimsiz": n_tanimsiz,
                     "n_kirpilan": n_kirpilan, "okuma_cumleleri": sentences}}


def _ladder(trades, decisions, reader, now_ms, counters) -> dict:
    entry_of = {t["decision_id"]: t["entry_price"] for t in trades if t.get("decision_id") is not None}
    cost_rate = 2 * (LOCKED_CFG.fee_rate + LOCKED_CFG.slippage_rate)
    agg: dict[tuple, list] = {}
    for dcs in sorted(decisions, key=lambda x: (x["pair"], x["id"])):
        e = entry_of.get(dcs["id"]) if dcs["final_action"] == "entered" else None
        if e is None:
            e = dcs["planned_entry"]
        s = dcs["planned_stop"]
        if not e or not s or e == s:
            continue
        start = I.ceil_hour(I.iso_ms(dcs["bar_close_ts"]))
        if now_ms < start + 72 * HOUR:
            counters["pending"] += 1
            continue
        st, rows = I.get_window(reader, dcs["pair"], "1h", start, 72)
        if st != "ok":
            counters["holdout_skipped_windows" if st == "holdout_skipped" else "data_gap"] += 1
            continue
        d = _dir(dcs["side"])
        R = abs(e - s)
        i_stop = None
        for k, (_, h, l, _c) in enumerate(rows):
            if (d > 0 and l <= s) or (d < 0 and h >= s):
                i_stop = k
                break
        res = {}
        for kk in LADDER_K:
            lvl = e + d * kk * R
            i_t = None
            for k, (_, h, l, _c) in enumerate(rows):
                if (d > 0 and h >= lvl) or (d < 0 and l <= lvl):
                    i_t = k
                    break
            reached = i_t is not None and (i_stop is None or i_t < i_stop)
            res[kk] = (1.0 if reached else 0.0, i_t is None and i_stop is None)
        agg.setdefault((dcs["setup"], dcs["side"]), []).append((res, dcs["gun"], cost_rate * e / R))
    rows_out = []
    for key in sorted(agg):
        v = agg[key]
        c = mean([x[2] for x in v])
        for kk in LADDER_K:
            xs = [x[0][kk][0] for x in v]
            cm = cluster_mean(xs, [x[1] for x in v])
            rows_out.append({"hucre": f"{key[0]} × {key[1]}", "k": kk, "n": cm["n"], "G": cm["G"], "P_k": cm["m"],
                             "aralik": [cm["lo"], cm["hi"]] if cm["lo"] is not None else None,
                             "basabas": 1 / (1 + kk), "maliyetli_basabas": (1 + c) / (1 + kk),
                             "zaman_asimi": sum(1 for x in v if x[0][kk][1]), "etiket": label_basic(cm["n"], cm["G"])})
    return plain("bariyer_merdiveni", "1.6 Bariyer yarışı merdiveni (tüm kararlar)",
                 ["hucre", "k", "n", "G", "P_k", "aralik", "basabas", "maliyetli_basabas", "zaman_asimi", "etiket"], rows_out,
                 [LADDER_NOTE])
