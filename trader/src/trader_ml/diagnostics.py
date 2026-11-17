"""Rapor tani satirlari (ML-G1, plan bolum K). GECTI/KALDI ROLU YOK: yalniz okumayi kolaylastirir; run_gate'e girmez."""
from __future__ import annotations

import numpy as np
import pandas as pd

from .config import TARGET_R
from .gate import rankdata


def auc(y: np.ndarray, p: np.ndarray) -> float:
    y = np.asarray(y, float)
    pos = y == 1
    n1, n0 = int(pos.sum()), int((~pos).sum())
    if n1 == 0 or n0 == 0:
        return float("nan")
    r = rankdata(np.asarray(p, float))
    return float((r[pos].sum() - n1 * (n1 + 1) / 2) / (n1 * n0))


def auc_boot(day: np.ndarray, y: np.ndarray, p: np.ndarray, n_boot: int = 300, seed: int = 0) -> tuple[float, float]:
    """Gun-bloklu bootstrap %90 araligi (ayni gun adaylari bagimsiz sayilmaz)."""
    rng = np.random.default_rng(seed)
    codes, uniq = pd.factorize(day)
    idx = [np.flatnonzero(codes == k) for k in range(len(uniq))]
    vals = []
    for _ in range(n_boot):
        pick = rng.integers(0, len(idx), len(idx))
        rows = np.concatenate([idx[k] for k in pick])
        v = auc(y[rows], p[rows])
        if np.isfinite(v):
            vals.append(v)
    return (float(np.quantile(vals, 0.05)), float(np.quantile(vals, 0.95))) if vals else (float("nan"), float("nan"))


def compute(oof: pd.DataFrame, pcol: str, *, target_r: float = TARGET_R, n_boot: int = 300) -> dict:
    """Secili model icin tani olculeri. Filtre maskesi model_metrics ile ayni: p >= th_<model> (NaN esik -> alinmaz)."""
    L = oof[oof["label"].notna()]
    out = {"chance_rate": 1.0 / (1.0 + target_r), "target_r": target_r,
           "label_rate": float(L["label"].mean()) if len(L) else float("nan")}
    if len(L):
        y, p = L["label"].to_numpy(float), L[pcol].to_numpy(float)
        day = pd.to_datetime(L["ts"], utc=True).dt.floor("D").to_numpy()
        lo, hi = auc_boot(day, y, p, n_boot)
        out["auc"], out["auc_lo90"], out["auc_hi90"] = auc(y, p), lo, hi
    U = oof[oof["taken"].astype(bool)].sort_values(["ts", "pair"], kind="mergesort")
    r, p = U["net_r"].to_numpy(float), U[pcol].to_numpy(float)
    tcol = "th_" + pcol[2:]
    m = p >= U[tcol].to_numpy(float) if tcol in U.columns else np.zeros(len(U), bool)
    n = len(U)
    h = n // 2
    mean = lambda a: float(a.mean()) if len(a) else float("nan")
    out["halves"] = {"first_filtered": mean(r[:h][m[:h]]), "first_all": mean(r[:h]),
                     "second_filtered": mean(r[h:][m[h:]]), "second_all": mean(r[h:]), "n_first": h, "n_second": n - h}
    if n >= 20:
        k = max(1, int(np.ceil(0.05 * n)))
        order = np.argsort(-r, kind="mergesort")
        top = order[:k]
        tot = float(r.sum())
        out["tail"] = {"k": k, "top5_share_of_total_net_r": float(r[top].sum() / tot) if tot > 0 else float("nan"),
                       "top5_kept_by_filter": int(m[top].sum()), "total_net_r": tot}
        t10 = order[:min(10, n)]
        out["top10"] = {"dropped_by_filter": int((~m[t10]).sum()), "of": int(len(t10)), "sum_r": float(r[t10].sum())}
    return out


def lines(d: dict) -> list[str]:
    f = lambda v, nd=4: "-" if v is None or not np.isfinite(v) else f"{v:.{nd}f}"
    L = [f"- Şans kıyası (1/(1+hedef R), hedef={d['target_r']}R): {f(d['chance_rate'], 3)}; gerçekleşen etiket oranı {f(d['label_rate'], 3)}"]
    if "auc" in d:
        L.append(f"- AUC (tüm etiketli OOF satırları): {f(d['auc'], 3)} (gün-bloklu bootstrap %90 aralık {f(d['auc_lo90'], 3)} – {f(d['auc_hi90'], 3)}; 0,5 = şans)")
    h = d["halves"]
    L.append(f"- İki yarı (alınan işlemler, zamana göre): 1. yarı filtreli {f(h['first_filtered'])} / filtresiz {f(h['first_all'])} R; "
             f"2. yarı filtreli {f(h['second_filtered'])} / filtresiz {f(h['second_all'])} R")
    if "tail" in d:
        t = d["tail"]
        L.append(f"- Kuyruk payı: en iyi %5 işlem ({t['k']} adet) toplam net R'nin {f(t['top5_share_of_total_net_r'], 2)} oranı (1,0 = hepsi); filtre bunlardan {t['top5_kept_by_filter']}/{t['k']} tanesini tuttu")
        t10 = d["top10"]
        L.append(f"- Filtre en iyi {t10['of']} işlemden {t10['dropped_by_filter']} tanesini attı (bu 10 işlemin toplamı {f(t10['sum_r'], 2)} R)")
    return L
