#!/usr/bin/env python3
"""PBO raporu (docs/ml/pbo-holdout-muhur-spec.md bolum 2). Yalniz rapor: karar kapisi degildir, sunucuda calismaz.

  python research/pbo_rapor.py            # docs/ml/pbo-raporu.md + research/holdout/pbo_ozet.json yeniden yazilir (seed sabit)

Aday kumesi: (a) kagit kural ailesi kurulumlari (config/engine.paper.json `arms`) - var/backtests/*/trades.csv defterlerinden
kurulum (T1, R1) basina gunluk R serisi; (b) ML filtre tarifleri (research/ml/{19c,r02,r03}/oof_predictions.parquet):
yapilandirma = model x esik (trader_ml.gate.pbo_for deseni). Defteri/denemesi olmayan aileler raporda "eksik" yazilir; uydurulmaz.
Yalniz 2026-05-01 oncesi veri; her okumada check_holdout cagrilir ve kilitli donemle kesisen satirlar dusurulur.
"""
from __future__ import annotations

import json
import math
import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from trader_core.stats import deflated_sharpe, pbo_cscv, return_moments  # noqa: E402
from trader_engine.holdout import HOLDOUT, check_holdout  # noqa: E402

N_SPLITS = 16
MAX_COMB = 2000
SEED = 0
THRESHOLDS = (0.45, 0.50, 0.55, 0.60, 0.65, 0.70)      # trader_ml.gate.pbo_for ile ayni izgara
BT_DIR = ROOT / "var" / "backtests"
ML_DIR = ROOT / "research" / "ml"
ARMS_CONFIG = ROOT / "config" / "engine.paper.json"
OUT_MD = ROOT / "docs" / "ml" / "pbo-raporu.md"
OUT_JSON = ROOT / "research" / "holdout" / "pbo_ozet.json"
ML_RECIPES = {"19c": "ml1-r01-v1b-native33 (19c)", "r02": "ml1-r02-long-ctx-1r", "r03": "ml1-r03-long-regime8"}
RULE_WINDOW = (pd.Timestamp("2024-11-01", tz="UTC"), pd.Timestamp("2025-11-01", tz="UTC"))   # IS kosularinin donemi (holdout oncesi)
PBO_LOW = 0.5
ARMS_SEEN: set[str] = set()      # defteri olan kurulum@tf (meta.trigger_tf)


# ------------------------------------------------------------------------------------- saf hesap
def family_stats(M: pd.DataFrame, *, n_trials_total: int | None = None) -> dict:
    """M: gun x yapilandirma getiri tablosu. Sabit (std=0) sutunlar PBO'dan cikar ama deneme sayisinda kalir."""
    n_total = int(n_trials_total if n_trials_total is not None else M.shape[1])
    T = int(M.shape[0])
    out = {"n_yapilandirma": n_total, "T": T}
    keep = (M.std(axis=0, ddof=0) > 0).to_numpy()
    out["n_kullanilan"] = int(keep.sum())
    if keep.sum() < 2 or T < 2 * N_SPLITS:
        out.update(durum="hesaplanamadi", neden=f"kullanilabilir yapilandirma {int(keep.sum())} (en az 2), gun {T} (en az {2 * N_SPLITS})")
        return out
    U = M.loc[:, keep]
    res = pbo_cscv(U.to_numpy(), n_splits=N_SPLITS, max_combinations=MAX_COMB, seed=SEED)
    srs = np.array([float(c.mean() / c.std(ddof=1)) for c in U.to_numpy().T])        # gunluk (donem basina) Sharpe
    best = int(np.argmax(srs))
    sk, ku = return_moments(U.iloc[:, best].to_numpy())
    dsr = deflated_sharpe(float(srs[best]), T, sk, ku, trial_srs=srs, n_trials=n_total)
    out.update(durum="tamam", pbo=float(res.pbo), n_kombinasyon=int(res.n_combinations),
               medyan_oos_goreli_sira=float(np.median(res.oos_rank)), prob_oos_kayip=float(res.prob_oos_loss),
               en_iyi_yapilandirma=str(U.columns[best]), en_iyi_sr_yillik=float(srs[best] * math.sqrt(365)),
               dsr=float(dsr) if np.isfinite(dsr) else None,
               yorum="asiri uyum riski dusuk-orta" if res.pbo < PBO_LOW else "asiri uyum riski yuksek")
    return out


def ml_matrix(oof: pd.DataFrame, pcols: list[str]) -> pd.DataFrame:
    """trader_ml.gate.pbo_for ile ayni kurulum: yapilandirma = model x esik; satir = gun (alinan islemlerin gunluk net R toplami)."""
    U = oof[oof["taken"].astype(bool)]
    if len(U) == 0:
        return pd.DataFrame()
    check_holdout(U["ts"].min().to_pydatetime(), (U["ts"].max() + pd.Timedelta(days=1)).to_pydatetime())
    days = pd.date_range(U["ts"].min().floor("D"), U["ts"].max().floor("D"), freq="D")
    cols = {}
    for pc in pcols:
        for th in THRESHOLDS:
            s = U["net_r"].where(U[pc] >= th, 0.0).groupby(U["ts"].dt.floor("D")).sum()
            cols[f"{pc}@{th:.2f}"] = s.reindex(days, fill_value=0.0).to_numpy()
    return pd.DataFrame(cols, index=days)


def rule_series(trades: pd.DataFrame, window: tuple[pd.Timestamp, pd.Timestamp]) -> dict[str, pd.Series]:
    """Defter -> {kurulum: gunluk R toplami (cikis gunune gore)}, pencere = [lo, hi); holdout ile kesisirse check_holdout reddeder; pencere tum gunleri kapsar."""
    lo, hi = window
    check_holdout(lo.to_pydatetime(), hi.to_pydatetime())
    t = trades[trades["exit_ts"].notna() & (trades["exit_ts"].astype(str).str.len() > 0)].copy()
    t["x"] = pd.to_datetime(t["exit_ts"], utc=True, format="ISO8601")
    t = t[(t["x"] >= lo) & (t["x"] < hi)]
    days = pd.date_range(lo.floor("D"), (hi - pd.Timedelta(days=1)).floor("D"), freq="D")
    out = {}
    for setup, g in t.groupby("setup"):
        s = g["r_multiple"].groupby(g["x"].dt.floor("D")).sum()
        out[str(setup)] = s.reindex(days, fill_value=0.0)
    return out


def union_matrix(parts: list[pd.DataFrame]) -> pd.DataFrame:
    parts = [p for p in parts if p.shape[1]]
    if not parts:
        return pd.DataFrame()
    idx = parts[0].index
    for p in parts[1:]:
        idx = idx.union(p.index)
    idx = pd.date_range(idx.min(), idx.max(), freq="D")
    return pd.concat([p.reindex(idx, fill_value=0.0) for p in parts], axis=1)


# ------------------------------------------------------------------------------------- veri toplama
def arms_from_config(path: Path = ARMS_CONFIG) -> list[str]:
    return list(json.loads(Path(path).read_text(encoding="utf-8")).get("arms", []))


def load_rule_ledgers(bt_dir: Path = BT_DIR) -> tuple[dict[str, pd.DataFrame], list[dict]]:
    """-> ({kurulum: gun x defter tablosu}, atlananlar). Yalniz RULE_WINDOW ile cakisan ve 'IS' penceresini kapsayan defterler."""
    series: dict[str, dict[str, pd.Series]] = {}
    skipped = []
    for d in sorted(Path(bt_dir).glob("*/")):
        tp, mp = d / "trades.csv", d / "meta.json"
        if not tp.exists() or not mp.exists():
            skipped.append({"kosu": d.name, "neden": "trades.csv/meta.json yok"})
            continue
        meta = json.loads(mp.read_text(encoding="utf-8"))
        per = meta.get("period") or []
        if len(per) != 2:
            skipped.append({"kosu": d.name, "neden": "donem bilgisi yok"})
            continue
        p0, p1 = pd.Timestamp(per[0]), pd.Timestamp(per[1])
        if not (p0 <= RULE_WINDOW[0] and p1 >= RULE_WINDOW[1]):
            skipped.append({"kosu": d.name, "neden": f"donem {p0:%Y-%m-%d}..{p1:%Y-%m-%d} ortak IS penceresini kapsamiyor"})
            continue
        for setup, s in rule_series(pd.read_csv(tp), RULE_WINDOW).items():
            series.setdefault(setup, {})[f"{setup}:{d.name}"] = s
            ARMS_SEEN.add(f"{setup}@{meta.get('trigger_tf', '?')}")
    return {k: pd.DataFrame(v) for k, v in series.items()}, skipped


def build(bt_dir: Path = BT_DIR, ml_dir: Path = ML_DIR, arms: list[str] | None = None) -> dict:
    arms = arms if arms is not None else arms_from_config()
    ARMS_SEEN.clear()
    rules, skipped = load_rule_ledgers(bt_dir)
    fams: list[dict] = []
    parts_all: list[pd.DataFrame] = []
    for setup in sorted(rules):
        M = rules[setup]
        r = {"aile": f"Kural {setup}", "tur": "kural", "kaynak": f"var/backtests/*/trades.csv ({M.shape[1]} defter, IS 2024-11-01..2025-10-31)"}
        r.update(family_stats(M))
        fams.append(r)
        parts_all.append(M)
    for key, name in ML_RECIPES.items():
        p = Path(ml_dir) / key / "oof_predictions.parquet"
        if not p.exists():
            fams.append({"aile": f"ML {key}", "tur": "ml", "kaynak": str(p.relative_to(ROOT)) if p.is_relative_to(ROOT) else str(p),
                         "durum": "eksik", "neden": "oof_predictions.parquet yok"})
            continue
        oof = pd.read_parquet(p)
        M = ml_matrix(oof, ["p_logistic", "p_lgbm"])
        r = {"aile": f"ML {key}", "tur": "ml", "kaynak": f"research/ml/{key}/oof_predictions.parquet ({name}; model x esik)"}
        r.update(family_stats(M) if M.shape[1] else {"durum": "eksik", "neden": "alinan satir yok", "n_yapilandirma": 0, "T": 0})
        fams.append(r)
        if M.shape[1]:
            parts_all.append(M.rename(columns=lambda c, k=key: f"{k}:{c}"))
    U = union_matrix(parts_all)
    allr = {"aile": "TUM KUME", "tur": "tum", "kaynak": "yukaridaki tum yapilandirmalar, ortak gun izgarasinda (etkin olmayan gun = 0 R)"}
    allr.update(family_stats(U) if U.shape[1] else {"durum": "eksik", "neden": "veri yok", "n_yapilandirma": 0, "T": 0})
    fams.append(allr)
    arm_rows = [{"kurulum": a, "kayit": "var" if a in ARMS_SEEN else "yok"} for a in arms]
    return {"parametreler": {"n_splits": N_SPLITS, "max_combinations": MAX_COMB, "seed": SEED, "esikler": list(THRESHOLDS),
                             "holdout_oncesi_sinir": HOLDOUT[0].strftime("%Y-%m-%d")},
            "aileler": fams, "kurulumlar": arm_rows, "atlanan_defterler": skipped}


# ------------------------------------------------------------------------------------- cikti
def _f(x, nd=3) -> str:
    return "-" if x is None or (isinstance(x, float) and not np.isfinite(x)) else f"{x:.{nd}f}".replace(".", ",")


def render_md(res: dict) -> str:
    P = res["parametreler"]
    L = ["# PBO raporu (holdout oncesi, yalniz rapor)", "",
         "Bu rapor **bilgi amaclidir**: karar kapisi degildir, hicbir islemi ya da kurulumu engellemez. Yalniz "
         f"`{P['holdout_oncesi_sinir']}` oncesi veri kullanildi; holdout satirlarina dokunulmadi. Uretim: `python research/pbo_rapor.py` "
         f"(seed {P['seed']}, sabit).", "", "## 1. Tablo", "",
         "| Aile | Yapilandirma (kullanilan) | T (gun) | PBO | Medyan OOS goreli sira | En iyi IS yapilandirma | Yillik SR | DSR | Yorum |",
         "|---|---|---|---|---|---|---|---|---|"]
    for f in res["aileler"]:
        if f.get("durum") == "tamam":
            L.append(f"| {f['aile']} | {f['n_yapilandirma']} ({f['n_kullanilan']}) | {f['T']} | {_f(f['pbo'])} | {_f(f['medyan_oos_goreli_sira'])} | "
                     f"`{f['en_iyi_yapilandirma']}` | {_f(f['en_iyi_sr_yillik'], 2)} | {_f(f['dsr'])} | {f['yorum']} |")
        else:
            L.append(f"| {f['aile']} | {f.get('n_yapilandirma', 0)} | {f.get('T', 0)} | - | - | - | - | - | {f.get('durum')}: {f.get('neden', '')} |")
    L += ["", "PBO < 0,5 ise \"asiri uyum riski dusuk-orta\", aksi \"yuksek\" yazilir; esik bilgi amaclidir. DSR, en iyi (tam orneklem Sharpe) "
          "yapilandirma icin, o ailedeki tum yapilandirma sayisiyla (elenenler ve sabit sutunlar dahil) hesaplanir. Yillik SR = gunluk SR x sqrt(365).",
          "", "## 2. Yontem", "",
          f"- `trader_core.stats.pbo_cscv`, `n_splits={P['n_splits']}`, `max_combinations={P['max_combinations']}`, `seed={P['seed']}`, olcut Sharpe; "
          "`trader_ml.gate.pbo_for` deseni (ML ailelerinde yapilandirma = model x esik, satir = gun, deger = alinan islemlerin gunluk net R toplami).",
          "- Kural ailelerinde yapilandirma = bir deneme kosusundaki kurulumun (T1, R1) gunluk R toplami (cikis gunune gore); kosular maliyet kolu, "
          "dolum modeli ve tetik zaman dilimi bakimindan farklidir. Ortak pencere IS 2024-11-01..2025-10-31 (365 gun, islemsiz gun = 0).",
          "- Sabit (std = 0) sutunlar CSCV'den cikarilir ama deneme sayisinda kalir.",
          "- Medyan OOS goreli sira: IS'te en iyi yapilandirmanin OOS goreli sirasinin (rank/(N+1)) kombinasyonlar uzerindeki medyani; 0,5 = medyan.",
          "- TUM KUME: ortak gun izgarasi (en erken..en gec gun); bir ailenin etkin olmadigi gunler 0 R'dir. Bu, pencereleri farkli aileleri tek matriste "
          "karistirir; sonuc yalniz kaba bir ust-kume gostergesidir.", "", "## 3. Deneme kaynaklari", "",
          "| Aile | Kaynak |", "|---|---|"]
    L += [f"| {f['aile']} | {f.get('kaynak', '')} |" for f in res["aileler"]]
    L += ["", "Kayit dosyalari (`research/trial_registry.csv`, `research/ml_trial_registry.csv`, `research/runs/*.json`) yalniz toplu istatistik tasir "
          "(gunluk getiri serisi yok); gunluk seriler `var/backtests/*/trades.csv` defterlerinden ve ML `oof_predictions.parquet` dosyalarindan "
          "uretildi. Yeni backtest kosulmadi.", "", "## 4. Eksik kalan aileler", ""]
    miss = [a["kurulum"] for a in res["kurulumlar"] if a["kayit"] == "yok"]
    ok = [a["kurulum"] for a in res["kurulumlar"] if a["kayit"] == "var"]
    L += [f"- `config/engine.paper.json` `arms` icinde defteri olan kurulumlar (kurulum duzeyinde): {', '.join(ok) or '-'}.",
          f"- Deneme kaydi / defteri **olmayan** {len(miss)} kurulum: {', '.join(miss) or '-'}. Bunlar icin PBO hesaplanmadi; deneme uydurulmadi. "
          "Yeniden uretim, uzun donemli motor kosulari gerektirir (ucuz degil).",
          "- M1 (LightGBM/ridge onerici) adaylari: `research/paper_models.csv` ve `research/pa_proposer_build.py` yalniz egitim kaydi tutar "
          "(model sha256, satir sayisi); walk-forward getiri serisi ya da deneme kaydi yok -> PBO hesaplanmadi.",
          "- Defter ailelerinde yalniz `T1` ve `R1` var; `T1` defterlerinin bir kismi (`ml_cand_v1b_native`, `s2_base_v1b`) farkli strateji surumu "
          "(`price_action_v1`) ve 10 ciftlik evrenle kosulmustur."]
    if res["atlanan_defterler"]:
        L += ["", "Atlanan defterler:"] + [f"- `{s['kosu']}`: {s['neden']}" for s in res["atlanan_defterler"]]
    return "\n".join(L) + "\n"


def main(argv=None) -> int:
    res = build()
    OUT_JSON.parent.mkdir(parents=True, exist_ok=True)
    OUT_JSON.write_text(json.dumps(res, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    OUT_MD.write_text(render_md(res), encoding="utf-8")
    for f in res["aileler"]:
        print(f"{f['aile']:<12} {f.get('durum'):<12} cfg={f.get('n_yapilandirma')} T={f.get('T')} PBO={_f(f.get('pbo'))} DSR={_f(f.get('dsr'))}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
