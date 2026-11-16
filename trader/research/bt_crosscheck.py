#!/usr/bin/env python3
"""Capraz dogrulama araci (06 §7): freqtrade referans calismasi (`user_data/backtest_results/<ID>/`) <-> motor calismasi
(`var/backtests/<ID>_compat/`). FREQTRADE CALISTIRILMAZ: yalniz uretilmis `ledger.sqlite` / csv dosyalari okunur.

Duzeyler: A kararlar, B girisler, C cikislar, D toplamlar; ilk sapma yontemi + siniflandirma (§7.3).
Cikti: research/crosscheck/<ID>.json + .md. Cikis kodu 0 = A-D kabul + aciklanamayan 0; 1 = degil; 2 = girdi hatasi.

Kullanim:
  python research/bt_crosscheck.py --id 1h_IS_f1_s0 [--ref-dir D] [--engine-dir D] [--out-dir D] [--history-dir D]
  python research/bt_crosscheck.py --model-diff --id 1h_IS_f1_s0 --compat D1 --native-last D2 --native-mark D3
"""
from __future__ import annotations

import argparse
import json
import math
import sqlite3
import sys
from datetime import timedelta
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent

TF_STEP = {"1h": pd.Timedelta(hours=1), "15m": pd.Timedelta(minutes=15)}
FEATURE_TOL = 1e-9
ENTRY_TOL = 1e-9
EXIT_PRICE_TOL = 1e-6
SIZE_TOL = 0.005
ACC_B, ACC_C = 0.99, 0.97
TOT_R, TOT_FEE, TOT_FUND, TOT_FUND_ABS = 0.02, 0.02, 0.05, 0.5
FUNDING_SIGN_TOL = 1e-6
COUPLED = {"missing_in_engine", "extra_in_engine", "equity_coupling", "decision_only"}
CLASSES = ("trail_timing", "same_bar_order", "time_stop_count", "entry_ref", "qty_rounding", "price_rounding",
           "gap_fill", "exit_before_entry", "day_start_def", "funding_data", "funding_sign", "funding_boundary", "fee_model", "liquidation",
           "open_at_end", "margin_accounting", "chained_after_first", "aggregate", "unexplained")


# ------------------------------------------------------------------------------------------------ okuma
def canon(p: str) -> str:
    return str(p).split(":")[0].upper()


def _isnan(x) -> bool:
    return x is None or (isinstance(x, float) and math.isnan(x)) or (x is pd.NA) or (x is pd.NaT)


def close(a, b, rel: float) -> bool:
    if _isnan(a) or _isnan(b):
        return _isnan(a) and _isnan(b)
    if isinstance(a, str) or isinstance(b, str):
        return a == b
    return abs(float(a) - float(b)) <= rel * max(1.0, abs(float(a)))


def read_ledger(d: Path) -> tuple[pd.DataFrame, pd.DataFrame]:
    p = Path(d) / "ledger.sqlite"
    if not p.exists():
        raise FileNotFoundError(f"ledger yok: {p}")
    c = sqlite3.connect(f"file:{p}?mode=ro", uri=True)
    try:
        dec = pd.read_sql("SELECT * FROM v_decisions", c)
        tr = pd.read_sql("SELECT * FROM v_trades", c)
    finally:
        c.close()
    for df in (dec, tr):
        df["pair"] = df["pair"].map(canon)
    return dec, tr


def read_equity(d: Path, trades: pd.DataFrame) -> dict:
    """{(pair, side, entry_ts): equity_at_entry}: motor `trades.csv:equity_at_entry` ya da referans
    `trades_enriched.csv:equity_entry_est` (yoksa bos)."""
    d = Path(d)
    out: dict = {}
    f = d / "trades.csv"
    if f.exists():
        t = pd.read_csv(f)
        if "equity_at_entry" in t:
            for _, r in t.iterrows():
                out[(canon(r["pair"]), r["side"], r["entry_ts"])] = r["equity_at_entry"]
        return out
    f = d / "trades_enriched.csv"
    if f.exists():
        t = pd.read_csv(f)
        if "equity_entry_est" in t:
            side = t["side"] if "side" in t else None
            for i, r in t.iterrows():
                ts = pd.Timestamp(r["open_date"]).tz_convert("UTC") if pd.Timestamp(r["open_date"]).tzinfo else \
                    pd.Timestamp(r["open_date"]).tz_localize("UTC")
                ets = ts.strftime("%Y-%m-%dT%H:%M:%S.") + f"{ts.microsecond // 1000:03d}Z"
                sd = r["side"] if side is not None else ("short" if r.get("is_short") else "long")
                out[(canon(r["pair"]), sd, ets)] = r["equity_entry_est"]
    return out


def _ts(s) -> pd.Timestamp:
    return pd.Timestamp(s)


def _features(s) -> dict:
    try:
        return json.loads(s) if isinstance(s, str) else {}
    except ValueError:
        return {}


# ------------------------------------------------------------------------------------------------ kanit
class Evidence:
    """Istege bagli: 15m/1h bar verisinden kanit satiri (rapor aciklamalari icin)."""

    def __init__(self, hist: Path | None) -> None:
        self.hist = Path(hist) if hist else None
        self._c: dict = {}

    def bars(self, pair: str, tf: str, ts: pd.Timestamp, n_before: int = 1, n_after: int = 1) -> list[dict]:
        if self.hist is None:
            return []
        stem = pair.replace("/", "_") + "_" + pair.split("/")[1]
        key = (stem, tf)
        if key not in self._c:
            f = self.hist / f"{stem}-{tf}-futures.feather"
            self._c[key] = pd.read_feather(f).set_index("date") if f.exists() else None
        df = self._c[key]
        if df is None:
            return []
        t = ts if ts.tzinfo else ts.tz_localize("UTC")
        step = TF_STEP[tf]
        sl = df.loc[t - n_before * step: t + n_after * step]
        return [dict(open=str(i), o=r.open, h=r.high, l=r.low, c=r.close) for i, r in sl.iterrows()]


    def funding_parts(self, pair: str, side: str, qty: float, entry_ts, exit_ts) -> dict | None:
        """Veriden yeniden hesap (pozitif = odenen): `entry_b` = giris anindaki 00/08/16 noktasi, `exit_b` = cikis
        anindaki nokta, `middle` = arasi; mark = 1h mark acilisi (uyum kipi, 03 §4.5 v)."""
        if self.hist is None or _isnan(exit_ts):
            return None
        stem = pair.replace("/", "_") + "_" + pair.split("/")[1]
        try:
            fr = self._c.get((stem, "fr"))
            if fr is None:
                fr = self._c[(stem, "fr")] = pd.read_feather(self.hist / f"{stem}-1h-funding_rate.feather").set_index("date")
            mk = self._c.get((stem, "mk"))
            if mk is None:
                mk = self._c[(stem, "mk")] = pd.read_feather(self.hist / f"{stem}-1h-mark.feather").set_index("date")
        except (OSError, ValueError):
            return None
        a, b = _ts(entry_ts), _ts(exit_ts)
        a = a if a.tzinfo else a.tz_localize("UTC")
        b = b if b.tzinfo else b.tz_localize("UTC")
        sign = 1.0 if side == "long" else -1.0
        parts = dict(entry_b=0.0, middle=0.0, exit_b=0.0)
        for t, r in fr[(fr.index >= a) & (fr.index <= b)].iterrows():
            if t not in mk.index:
                continue
            v = sign * qty * float(mk.loc[t, "open"]) * float(r["funding_rate"])
            if t == a:
                parts["entry_b"] += v
            if t == b:
                parts["exit_b"] += v
            if t != a and t != b:
                parts["middle"] += v
        return parts

    @staticmethod
    def fit(parts: dict, value: float) -> tuple[int, int] | None:
        """value = middle + ce*entry_b + cx*exit_b (ce in {0,1}, cx in {0,1,2}) -> (ce, cx) ya da None."""
        for ce in (0, 1):
            for cx in (1, 0, 2):
                if close(parts["middle"] + ce * parts["entry_b"] + cx * parts["exit_b"], value, 1e-6):
                    return ce, cx
        return None


# ------------------------------------------------------------------------------------------------ cekirdek
def classify_exit(r, e, tf_step: pd.Timedelta) -> tuple[str, str]:
    rr, er = r["exit_reason"], e["exit_reason"]
    rt, et = _ts(r["exit_ts"]), _ts(e["exit_ts"])
    dt = (et - rt)
    if "liquidation" in (rr, er):
        return "liquidation", f"ref={rr} eng={er}"
    rel_px = abs(float(r["exit_price"]) - float(e["exit_price"])) / max(1.0, abs(float(r["exit_price"])))
    if dt != pd.Timedelta(0) and rr == er and 0 < rel_px < 1e-4:
        return "price_rounding", (f"stop seviyesi tick'e yuvarlandi (ref {r['exit_price']}, motor {e['exit_price']}, rel={rel_px:.1e}); "
                                  f"yuvarlama stopu sikilastirdigi icin tetik zamani {dt} farkli")
    if abs(dt) == tf_step and rr in ("trail_stop", "stop") and er in ("trail_stop", "stop"):
        return "trail_timing", f"iz stop {'bir bar once' if dt < pd.Timedelta(0) else 'bir bar sonra'}: ref {r['exit_ts']} eng {e['exit_ts']}"
    if abs(dt) == tf_step and rr == er == "time_stop":
        return "time_stop_count", f"48 bar sayimi {dt}"
    if dt == pd.Timedelta(0) and rr != er:
        return "same_bar_order", f"ayni adimda {rr} <-> {er}"
    if dt == pd.Timedelta(0) and rr == er:
        rel = abs(float(r["exit_price"]) - float(e["exit_price"])) / max(1.0, abs(float(r["exit_price"])))
        return ("price_rounding" if rel < 1e-4 else "gap_fill"), f"cikis fiyati ref={r['exit_price']} eng={e['exit_price']} rel={rel:.2e}"
    return "unexplained", f"exit_ts ref={r['exit_ts']} eng={e['exit_ts']} reason ref={rr} eng={er}"


def crosscheck(ref_dir, eng_dir, run_id: str, *, trigger_tf: str = "1h", history_dir=None, until: str | None = None) -> dict:
    tf_step = TF_STEP[trigger_tf]
    rd, rt = read_ledger(ref_dir)
    ed, et = read_ledger(eng_dir)
    if until:                                           # yalniz gelistirme: erken donem karsilastirmasi
        rd, ed = rd[rd["bar_close_ts"] < until], ed[ed["bar_close_ts"] < until]
        rt, et = rt[rt["entry_ts"] < until], et[et["entry_ts"] < until]
    req = read_equity(ref_dir, rt)
    eeq = read_equity(eng_dir, et)
    ev = Evidence(history_dir)
    diffs: list[dict] = []

    def add(level, key, field, ref, eng, cls, evidence, taraf, ts):
        diffs.append(dict(level=level, key=str(key), field=field, ref=ref, eng=eng, cls=cls, evidence=evidence,
                          taraf=taraf, ts=str(ts), chained=False))

    # ------------------------------------------------------------------ A: kararlar
    dk = ["pair", "side", "setup", "trigger_tf", "bar_close_ts"]
    rdi = rd.set_index(dk)
    edi = ed.set_index(dk)
    common = rdi.index.intersection(edi.index)
    only_ref = rdi.index.difference(edi.index)
    only_eng = edi.index.difference(rdi.index)
    a_fields = ("regime", "atr_ratio", "rh", "rl", "rh_touches", "rl_touches", "planned_entry", "planned_stop",
                "planned_target")
    a_equal = 0
    for k in common:
        r, e = rdi.loc[k], edi.loc[k]
        bad = []
        for f in a_fields:
            if not close(r[f], e[f], FEATURE_TOL):
                bad.append((f, r[f], e[f]))
        fr, fe = _features(r["features"]), _features(e["features"])
        if set(fr) != set(fe):
            bad.append(("features.keys", sorted(fr), sorted(fe)))
        else:
            for f in fr:
                if not close(fr[f], fe[f], FEATURE_TOL):
                    bad.append((f"features.{f}", fr[f], fe[f]))
        if not bad:
            a_equal += 1
        for f, x, y in bad:
            add("A", k, f, x, y, "unexplained", "ortak karar anahtarinda alan farki", "?", k[4])
    for k in only_ref:
        add("A", k, "decision_only_in_reference", None, None, "decision_only",
            "yalniz referansta karar; genelde onceki islem sapmasi yuzunden pozisyon durumu farkli", "?", k[4])
    for k in only_eng:
        add("A", k, "decision_only_in_engine", None, None, "decision_only",
            "yalniz motorda karar; genelde onceki islem sapmasi yuzunden pozisyon durumu farkli", "?", k[4])

    # ------------------------------------------------------------------ B/C/D: islemler
    def dsize(dec: pd.DataFrame) -> dict:
        return {int(r["id"]): r["size_qty"] for _, r in dec.iterrows()} if "id" in dec else {}
    rsz, esz = dsize(rd), dsize(ed)
    tk = ["pair", "side", "entry_ts"]
    R = {tuple(r[tk]): r for _, r in rt.iterrows()}
    E = {tuple(r[tk]): r for _, r in et.iterrows()}
    matched = [k for k in R if k in E]
    b_ok = 0
    b_key = len(matched)
    b_price_ok = b_size_ok = 0
    c_ok = c_strict = c_pm1 = 0
    funding_bad = 0
    qty_diffs = 0

    def open_at_end(x) -> bool:
        return _isnan(x)

    for k in sorted(R, key=lambda x: x[2]):
        r = R[k]
        if k not in E:
            m = ed[(ed["pair"] == k[0]) & (ed["side"] == k[1]) & (ed["bar_close_ts"] == k[2])]
            if len(m) and str(m.iloc[0]["skip_reason"]) == "order_failed":
                add("B", k, "entry_missing_in_engine", r["entry_price"], None, "margin_accounting",
                    "motor karari var ama giris dolumunda `order_failed` (PaperBroker: margin+fee > cuzdan-kullanilan marjin = "
                    "`insufficient_margin`); freqtrade serbest bakiyeden acik islemlerin giris komisyonunu dusmez ve miktari "
                    "bakiyeye gore kisar. Motor karar boyutu referanstan buyuk (ozsermaye tanimi farki)"
                    f" [motor karar boyutu {m.iloc[0]['size_qty']}]", "?", k[2])
            elif len(m):
                add("B", k, "entry_missing_in_engine", r["entry_price"], None, "missing_in_engine",
                    f"motor karari: {m.iloc[0]['final_action']}/{m.iloc[0]['skip_reason']} ({m.iloc[0]['risk_reason']})", "?", k[2])
            else:
                add("B", k, "entry_missing_in_engine", r["entry_price"], None, "missing_in_engine",
                    "referans girisi motorda yok (motorda karar kaydi da yok: pozisyon durumu farki)", "?", k[2])
            continue
        e = E[k]
        ok = True
        if not close(r["entry_price"], e["entry_price"], ENTRY_TOL):
            ok = False
            add("B", k, "entry_price", r["entry_price"], e["entry_price"], "entry_ref",
                f"rel={abs(r['entry_price'] - e['entry_price']) / abs(r['entry_price']):.2e}", "?", k[2])
        else:
            b_price_ok += 1
        # boyut: karar ani risk tutari (`planned_risk`, gercek ozsermayeyle hesaplanir) goreli %0,5 icinde. Referans
        # `equity_entry_est` yalniz tahmindir (1h kapanis mark'i, 06 §13) ve kanit olarak gosterilir.
        rq, eq_ = req.get(k), eeq.get(k)
        ra, ea = float(r["planned_risk"]), float(e["planned_risk"])
        if abs(ra - ea) > SIZE_TOL * abs(ra):
            ok = False
            add("B", k, "size_ratio", ra, ea, "equity_coupling",
                f"planned_risk ref={ra:.6g} eng={ea:.6g} (rel {abs(ra - ea) / abs(ra):.2e}); ozsermaye tahmini ref={rq} "
                f"motor(karar ani)={eq_}", "?", k[2])
        else:
            b_size_ok += 1
        if ok:
            b_ok += 1
        # doldurulan miktar farki (bilgi; B kabulune girmez): kanit karar boyutundan
        if not close(r["qty"], e["qty"], 1e-12):
            qty_diffs += 1
            rs, es = rsz.get(int(r["decision_id"])), esz.get(int(e["decision_id"]))
            if rs is not None and es is not None and close(rs, es, 1e-9) and (not close(r["qty"], rs, 1e-12) or not close(e["qty"], es, 1e-12)):
                who = "referans" if not close(r["qty"], rs, 1e-12) else "motor"
                add("B", k, "qty", r["qty"], e["qty"], "qty_rounding",
                    f"ayni karar boyutu {rs}; {who} dolumu karar boyutundan farkli (ref dolum {r['qty']}, motor dolum {e['qty']}): "
                    f"amount kesme/yuvarlama (freqtrade stake->amount, sentetik adim)", "?", k[2])
            else:
                same_step = [x for x in R if x != k and str(R[x]["exit_ts"]) == str(k[2])]
                add("B", k, "qty", r["qty"], e["qty"], "exit_before_entry" if same_step else "equity_coupling",
                    f"karar boyutu ref={rs} motor={es}: ozsermaye/risk durumu farki"
                    + (f"; ayni adimda cikan referans islem(ler) {same_step[:3]}: referans cikisi gerceklestirir (realized), "
                       f"motor son mark'ta tutar (cikis-giristen-once modeli)" if same_step else ""), "?", k[2])
        # C
        rx = _ts(r["exit_ts"]) if not open_at_end(r["exit_ts"]) else None
        ex = _ts(e["exit_ts"]) if not open_at_end(e["exit_ts"]) else None
        if rx is None and ex is None:
            c_ok += 1
            c_strict += 1
            continue
        if (rx is None) != (ex is None):
            who = "referans" if ex is None else "motor"
            other = e if ex is None else r
            end_ok = (ex is None and str(r["exit_reason"]) == "other") or (rx is None and False)
            add("C", k, "exit_open_state", r["exit_ts"], e["exit_ts"], "open_at_end" if end_ok else "unexplained",
                f"{who} acik, diger kapali (diger: {other['exit_ts']} {other['exit_reason']}); "
                + ("referans kosu sonunda force-exit (freqtrade); motor acik pozisyonu kapatmaz (06 §9.6)" if end_ok else ""),
                "?", k[2])
            continue
        strict = (rx == ex and r["exit_reason"] == e["exit_reason"] and close(r["exit_price"], e["exit_price"], EXIT_PRICE_TOL))
        if strict:
            c_ok += 1
            c_strict += 1
        else:
            cls, evid = classify_exit(r, e, tf_step)
            fld = ("exit_ts" if rx != ex else "exit_reason" if r["exit_reason"] != e["exit_reason"] else "exit_price")
            if cls == "trail_timing" and abs(ex - rx) == tf_step and r["exit_reason"] in ("trail_stop",) and e["exit_reason"] == "trail_stop":
                c_ok += 1
                c_pm1 += 1                      # +-1 adim yalniz trail sinifi icin kabul (ayri sayilir)
            if cls == "unexplained":
                ev_b = ev.bars(k[0], trigger_tf, rx)
                evid += f" | bars={ev_b}" if ev_b else ""
            add("C", k, fld, f"{r['exit_ts']} {r['exit_reason']} {r['exit_price']}",
                f"{e['exit_ts']} {e['exit_reason']} {e['exit_price']}", cls, evid, "?", k[2])
        # funding (tek tek; qty'ye gore normalize)
        if rx is not None and ex is not None and rx == ex:
            rpq, epq = float(r["funding_paid"]) / float(r["qty"]), float(e["funding_paid"]) / float(e["qty"])
            if not close(rpq, epq, FUNDING_SIGN_TOL):
                funding_bad += 1
                if close(rpq, -epq, FUNDING_SIGN_TOL):
                    cls, evid = "funding_sign", f"birim miktar basina ref={rpq:.3e} motor={epq:.3e}"
                else:
                    pr = ev.funding_parts(k[0], k[1], float(r["qty"]), r["entry_ts"], r["exit_ts"])
                    pe = ev.funding_parts(k[0], k[1], float(e["qty"]), e["entry_ts"], e["exit_ts"])
                    fr_ = ev.fit(pr, float(r["funding_paid"])) if pr else None
                    fe_ = ev.fit(pe, float(e["funding_paid"])) if pe else None
                    if fr_ is not None and fe_ is not None:
                        cls = "funding_boundary"
                        evid = (f"sinir noktalari (giris/cikis anindaki 00/08/16): referans giris x{fr_[0]}, cikis x{fr_[1]}; "
                                f"motor giris x{fe_[0]}, cikis x{fe_[1]} (veriden yeniden hesapla birebir uyumlu; "
                                f"03 §5 `opened_ts >= p.ts` atlanir)")
                    else:
                        cls, evid = "unexplained", (f"ref={r['funding_paid']:.8f} motor={e['funding_paid']:.8f} (birim miktar "
                                                    f"ref={rpq:.3e} motor={epq:.3e}; uyum ref={fr_} motor={fe_})")
                add("D", k, "funding_paid", r["funding_paid"], e["funding_paid"], cls, evid, "?", k[2])
    for k in sorted(E, key=lambda x: x[2]):
        if k not in R:
            add("B", k, "entry_extra_in_engine", None, E[k]["entry_price"], "extra_in_engine", "motorda fazla giris", "?", k[2])

    # ------------------------------------------------------------------ ilk sapma + zincir
    diffs.sort(key=lambda d: (d["ts"], d["level"]))
    first = None
    for d in diffs:
        if d["level"] in ("A", "B", "C"):
            first = d
            break
    if first is not None:
        first["first_divergence"] = True
        for d in diffs:
            if d is not first and d["ts"] >= first["ts"] and d["cls"] in COUPLED:
                d["chained"] = True
                d["cls_original"] = d["cls"]
                d["cls"] = "chained_after_first"
    # ilk sapma motor <-> referans taraf notu
    for d in diffs:
        if d["cls"] == "unexplained":
            d["taraf"] = "belirsiz: kok neden incelenmeli (motor mu, TraderV1 baglastiricisi mi); aciklanamayan fark = hata"
        elif d["cls"] == "chained_after_first":
            d["taraf"] = "zincir"
        else:
            d["taraf"] = "model farki (aciklanmis sinif)"

    # ------------------------------------------------------------------ D: toplamlar
    def tot(t: pd.DataFrame) -> dict:
        c = t[t["exit_ts"].notna()]
        return dict(n=int(len(t)), sum_R=float(c["r_multiple"].sum()), fees=float((c["fee_entry"] + c["fee_exit"]).sum()),
                    funding=float(c["funding_paid"].sum()))
    tr_, te_ = tot(rt), tot(et)
    d_checks = {}
    d_checks["sum_R"] = dict(ref=tr_["sum_R"], eng=te_["sum_R"], diff=te_["sum_R"] - tr_["sum_R"],
                             tol=TOT_R * max(abs(tr_["sum_R"]), 1.0),
                             ok=abs(te_["sum_R"] - tr_["sum_R"]) <= TOT_R * max(abs(tr_["sum_R"]), 1.0))
    d_checks["fees"] = dict(ref=tr_["fees"], eng=te_["fees"], diff=te_["fees"] - tr_["fees"], tol=TOT_FEE * abs(tr_["fees"]),
                            ok=abs(te_["fees"] - tr_["fees"]) <= TOT_FEE * abs(tr_["fees"]) + 1e-12)
    fd = abs(te_["funding"] - tr_["funding"])
    d_checks["funding"] = dict(ref=tr_["funding"], eng=te_["funding"], diff=te_["funding"] - tr_["funding"],
                               tol=max(TOT_FUND * abs(tr_["funding"]), 0.0), abs_tol=TOT_FUND_ABS,
                               ok=(fd <= TOT_FUND * abs(tr_["funding"]) or fd <= TOT_FUND_ABS))
    d_checks["n_trades"] = dict(ref=tr_["n"], eng=te_["n"], diff=te_["n"] - tr_["n"], tol=max(1, 0.01 * tr_["n"]),
                                ok=abs(te_["n"] - tr_["n"]) <= max(1, 0.01 * tr_["n"]))
    # toplam farkinin ayrisimi (kanit): eslesen islemlerin farki + yalniz-ref + yalniz-motor
    def closed_r(x) -> float:
        return float(x["r_multiple"]) if not _isnan(x["exit_ts"]) else 0.0
    dec = dict(matched_pairs=sum(closed_r(E[k]) - closed_r(R[k]) for k in matched),
               ref_only=-sum(closed_r(R[k]) for k in R if k not in E),
               eng_only=sum(closed_r(E[k]) for k in E if k not in R))
    for name, v in d_checks.items():
        if not v["ok"]:
            add("D", name, name, v["ref"], v["eng"], "aggregate", f"toplam farki {v['diff']:.6g} > tolerans {v['tol']:.6g}; "
                f"sum_R ayrisimi: eslesen islemler {dec['matched_pairs']:+.3f}, yalniz-ref {dec['ref_only']:+.3f}, "
                f"yalniz-motor {dec['eng_only']:+.3f} (alttaki farklarin toplam etkisi)", "toplam", "9999")

    n_ref = len(R)
    a_total = len(common)
    cls_count: dict[str, int] = {}
    for d in diffs:
        cls_count[d["cls"]] = cls_count.get(d["cls"], 0) + 1
    n_unexpl = cls_count.get("unexplained", 0)
    b_rate = b_ok / n_ref if n_ref else 1.0
    c_rate = c_ok / b_key if b_key else 1.0
    acc = dict(
        A=dict(common=a_total, equal=a_equal, pct=(100.0 * a_equal / a_total if a_total else 100.0),
               only_ref=len(only_ref), only_eng=len(only_eng),
               ok=(a_equal == a_total and all(d["cls"] != "unexplained" for d in diffs if d["level"] == "A"))),
        B=dict(n_ref=n_ref, n_eng=len(E), key_matched=b_key, key_pct=(100.0 * b_key / n_ref if n_ref else 100.0),
               price_pct=(100.0 * b_price_ok / n_ref if n_ref else 100.0), entries_ok=b_ok, pct=100.0 * b_rate,
               price_ok=b_price_ok, size_ok=b_size_ok, ok=(b_rate >= ACC_B)),
        C=dict(matched=b_key, ok_n=c_ok, strict_ok=c_strict, trail_pm1=c_pm1, pct=100.0 * c_rate,
               pct_strict=(100.0 * c_strict / b_key if b_key else 100.0), ok=(c_rate >= ACC_C)),
        D=dict(checks=d_checks, sum_R_decomposition=dec, funding_per_trade_mismatch=funding_bad, qty_diffs=qty_diffs, ok=all(v["ok"] for v in d_checks.values())))
    passed = all(acc[x]["ok"] for x in "ABCD") and n_unexpl == 0
    return dict(id=run_id, trigger_tf=trigger_tf, passed=passed, accept=acc, unexplained=n_unexpl,
                class_counts=cls_count, first_divergence=first, n_diffs=len(diffs), diffs=diffs,
                totals=dict(ref=tr_, eng=te_))


def render_md(rep: dict, max_rows: int = 60) -> str:
    a = rep["accept"]
    L = [f"# Capraz dogrulama: {rep['id']}", "",
         f"Sonuc: **{'KABUL' if rep['passed'] else 'RED'}** (aciklanamayan: {rep['unexplained']})", "",
         "| Duzey | Olcut | Deger | Kabul |", "|---|---|---|---|",
         f"| A kararlar | ortak anahtarda esit | {a['A']['equal']}/{a['A']['common']} ({a['A']['pct']:.2f}%); "
         f"yalniz ref {a['A']['only_ref']}, yalniz motor {a['A']['only_eng']} | {'evet' if a['A']['ok'] else 'hayir'} |",
         f"| B girisler | eslesen/ref (anahtar+fiyat+boyut) | {a['B']['entries_ok']}/{a['B']['n_ref']} ({a['B']['pct']:.2f}%); yalniz anahtar {a['B']['key_pct']:.2f}%, anahtar+fiyat {a['B']['price_pct']:.2f}% | {'evet' if a['B']['ok'] else 'hayir'} |",
         f"| C cikislar | eslesen girislerde | {a['C']['ok_n']}/{a['C']['matched']} ({a['C']['pct']:.2f}%; kesin {a['C']['pct_strict']:.2f}%, "
         f"trail +-1: {a['C']['trail_pm1']}) | {'evet' if a['C']['ok'] else 'hayir'} |"]
    for n, v in a["D"]["checks"].items():
        L.append(f"| D {n} | ref {v['ref']:.6g} / motor {v['eng']:.6g} (fark {v['diff']:.4g}, tol {v['tol']:.4g}) | | {'evet' if v['ok'] else 'hayir'} |")
    L += ["", "Sinif sayilari: " + ", ".join(f"{k}={v}" for k, v in sorted(rep["class_counts"].items())) if rep["class_counts"] else "Fark yok.",
          f"unexplained: {rep['unexplained']}", ""]
    if rep["first_divergence"]:
        f = rep["first_divergence"]
        L += ["## Ilk sapma", f"{f['level']} {f['key']} {f['field']}: ref={f['ref']} motor={f['eng']} sinif={f['cls']} | {f['evidence']}", ""]
    if rep["diffs"]:
        L += ["## Farklar", "", "| duzey | anahtar | alan | ref | motor | sinif | kanit |", "|---|---|---|---|---|---|---|"]
        for d in rep["diffs"][:max_rows]:
            L.append(f"| {d['level']} | {d['key']} | {d['field']} | {d['ref']} | {d['eng']} | {d['cls']} | {str(d['evidence'])[:160]} |")
        if len(rep["diffs"]) > max_rows:
            L.append(f"... {len(rep['diffs']) - max_rows} fark daha (json'da)")
    return "\n".join(L) + "\n"


# ------------------------------------------------------------------------------------------------ model farki
def model_diff(run_id: str, compat: Path, native_last: Path, native_mark: Path) -> dict:
    """§7.4: compat -> native_last (ayrinti+maliyet) -> native_mark (mark<->last)."""
    def load(d):
        s = json.loads((Path(d) / "summary.json").read_text())
        t = pd.read_csv(Path(d) / "trades.csv")
        return s, t
    runs = {n: load(d) for n, d in (("compat", compat), ("native_last", native_last), ("native_mark", native_mark))}
    rows = {}
    for n, (s, t) in runs.items():
        c = t[t["exit_ts"].notna()]
        rows[n] = dict(n_trades=int(s.get("n_trades", len(c))), expectancy_R=s.get("expectancy_R"),
                       sum_R=float(c["r_multiple"].sum()), profit_factor=s.get("profit_factor"))
    (_, tl), (_, tm) = runs["native_last"], runs["native_mark"]
    k = ["pair", "side", "entry_ts"]
    L_ = {tuple(r[k]): r for _, r in tl.iterrows() if isinstance(r["exit_ts"], str)}
    M_ = {tuple(r[k]): r for _, r in tm.iterrows() if isinstance(r["exit_ts"], str)}
    n_last = sum(1 for r in L_.values() if r["exit_reason"] == "stop")
    n_mark = sum(1 for r in M_.values() if r["exit_reason"] == "stop")
    removed, added, samples, dr = 0, 0, [], []
    for key, r in L_.items():
        m = M_.get(key)
        if m is None:
            continue
        if r["exit_reason"] == "stop" and m["exit_reason"] != "stop":
            removed += 1
            samples.append(dict(key=str(key), kind="removed_by_mark", last=f"{r['exit_ts']} {r['exit_reason']} {r['exit_price']}",
                                mark=f"{m['exit_ts']} {m['exit_reason']} {m['exit_price']}"))
        if r["exit_reason"] != "stop" and m["exit_reason"] == "stop":
            added += 1
            samples.append(dict(key=str(key), kind="added_by_mark", last=f"{r['exit_ts']} {r['exit_reason']} {r['exit_price']}",
                                mark=f"{m['exit_ts']} {m['exit_reason']} {m['exit_price']}"))
        dr.append(float(m["r_multiple"]) - float(r["r_multiple"]))
    return dict(id=run_id, runs=rows, n_stop_native_last=n_last, n_stop_native_mark=n_mark, n_stops_removed_by_mark=removed,
                n_stops_added_by_mark=added, delta_sum_R=rows["native_mark"]["sum_R"] - rows["native_last"]["sum_R"],
                mean_delta_R=(sum(dr) / len(dr) if dr else None), n_paired=len(dr), samples=samples[:50],
                note="HOLDOUT kullanilmaz; (1)->(2) ayrinti+maliyet, (2)->(3) mark<->last")


# ------------------------------------------------------------------------------------------------ CLI
def main(argv=None) -> int:
    ap = argparse.ArgumentParser(allow_abbrev=False)
    ap.add_argument("--id", required=True)
    ap.add_argument("--ref-dir", "--reference", "--ref", "--reference-dir", dest="ref", default=None)
    ap.add_argument("--engine-dir", "--engine", dest="eng", default=None)
    ap.add_argument("--out-dir", "--out", "--outdir", "--output-dir", dest="out", default=None)
    ap.add_argument("--history-dir", default=None)
    ap.add_argument("--tf", default=None, choices=["1h", "15m"])
    ap.add_argument("--until", default=None, help="gelistirme: yalniz bu ISO anindan onceki karar/girisler")
    ap.add_argument("--model-diff", action="store_true")
    ap.add_argument("--compat", default=None)
    ap.add_argument("--native-last", default=None)
    ap.add_argument("--native-mark", default=None)
    try:
        a = ap.parse_args(argv)
    except SystemExit as e:
        return 2 if e.code else 0
    out = Path(a.out) if a.out else ROOT / "research" / "crosscheck"
    out.mkdir(parents=True, exist_ok=True)
    if a.model_diff:
        try:
            rep = model_diff(a.id, Path(a.compat), Path(a.native_last), Path(a.native_mark))
        except (OSError, TypeError, KeyError) as e:
            print(f"girdi hatasi: {e}", file=sys.stderr)
            return 2
        (out / f"{a.id}_model_diff.json").write_text(json.dumps(rep, indent=1, default=str))
        print(json.dumps({k: v for k, v in rep.items() if k != "samples"}, indent=1, default=str))
        return 0
    ref = Path(a.ref) if a.ref else ROOT / "user_data" / "backtest_results" / a.id
    eng = Path(a.eng) if a.eng else ROOT / "var" / "backtests" / f"{a.id}_compat"
    tf = a.tf or ("15m" if a.id.startswith("15m") else "1h")
    hist = a.history_dir or (str(ROOT / "user_data/data/binance/futures")
                             if (ROOT / "user_data/data/binance/futures").exists() else None)
    try:
        rep = crosscheck(ref, eng, a.id, trigger_tf=tf, history_dir=hist, until=a.until)
    except (OSError, sqlite3.Error, KeyError) as e:
        print(f"girdi hatasi: {e}", file=sys.stderr)
        return 2
    (out / f"{a.id}.json").write_text(json.dumps(rep, indent=1, default=str))
    (out / f"{a.id}.md").write_text(render_md(rep))
    acc = rep["accept"]
    print(f"[{a.id}] {'KABUL' if rep['passed'] else 'RED'} A={acc['A']['pct']:.2f}% B={acc['B']['pct']:.2f}% "
          f"(anahtar {acc['B']['key_pct']:.2f}%, anahtar+fiyat {acc['B']['price_pct']:.2f}%) "
          f"C={acc['C']['pct']:.2f}% (kesin {acc['C']['pct_strict']:.2f}%) D_ok={acc['D']['ok']} "
          f"aciklanamayan={rep['unexplained']} siniflar={rep['class_counts']}")
    return 0 if rep["passed"] else 1


if __name__ == "__main__":
    sys.exit(main())
