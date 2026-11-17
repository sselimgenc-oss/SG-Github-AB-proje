"""Madde 16: piyasa kosuluna gore tablolar + standart dokumler + yil satirlari (madde 17)."""
from __future__ import annotations

import math

from . import inputs as I
from .exits import plain
from .stats import SubTable, cluster_mean, mean, wilson, year_rows

VOL_NOTE = "İncelenen botlarda hiçbir koşul hücresi kalıcı çıkmadı; hücre 'tutuyor' demeden koşula bağlı kural yazılmaz."
WEEK_NOTE = "Etiket geleceği ve iki farklı getiri tanımını kullanır; yalnız değerlendirme (varsayım)."
EXIT_REGIME_MISSING = "`exit_regime` alanı defterde yok (WP-3 ekleyecek); tablo üretilmedi."
WEEKDAYS = ("Pzt", "Sal", "Çar", "Per", "Cum", "Cmt", "Paz")


def vol_state(ar) -> str:
    if ar is None:
        return "bilinmiyor"
    return "düşük" if ar < 0.80 else ("orta" if ar < 1.00 else "yüksek")


def _item(t):
    return (t["net_r"], t["gun"], t["entry_ts"])


def _split(trades, keyf):
    d: dict = {}
    for t in trades:
        d.setdefault(keyf(t), []).append(t)
    return d


def _cells(groups, extra=None, dims=None):
    out = []
    for k, v in sorted(groups.items(), key=lambda kv: str(kv[0])):
        ex = dict(extra(v)) if extra else {}
        if dims:
            kk = k if isinstance(k, tuple) else (k,)
            for nm, val in zip(dims, kk):
                ex[nm] = val
        lbl = " × ".join(k) if isinstance(k, tuple) else k
        out.append((lbl, [_item(t) for t in v], ex))
    return out


def _wr(v):
    w = wilson(sum(1 for t in v if t["net_r"] > 0), len(v))
    return {"kazanc_orani": w["p"], "toplam_r": math.fsum(t["net_r"] for t in v)}


def hour_bucket(ts: str) -> str:
    h = int(ts[11:13])
    return "00–08" if h < 8 else ("08–16" if h < 16 else "16–24")


def build(trades, decisions, cf, has_exit_regime: bool, section: str = "regimes") -> dict:
    blocks: list = []
    cells = _cells(_split(trades, lambda t: (t["regime"], t["side"], t["setup"])), _wr, ["kosul", "yon", "kurulum"])
    blocks.append(SubTable("kosul_yon_kurulum", "3.1 Giriş koşulu × yön × kurulum", "net_r", cells, ["kosul", "yon", "kurulum", "kazanc_orani", "toplam_r"],
                           [], section))

    def vpost(r):
        r["tutuyor"] = "evet" if (r["etiket"] == "çıtayı geçti" and r["aralik"] and not (r["aralik"][0] <= 0 <= r["aralik"][1])) else "hayır"
    cells = _cells(_split(trades, lambda t: (t["regime"], vol_state(t.get("atr_ratio")))), _wr, ["kosul", "oynaklik"])
    blocks.append(SubTable("kosul_oynaklik", "3.2 Giriş koşulu × oynaklık (düşük < 0,80 ≤ orta < 1,00 ≤ yüksek)", "net_r", cells,
                           ["kosul", "oynaklik", "kazanc_orani", "toplam_r", "tutuyor"], [VOL_NOTE], section, vpost))

    groups = _split(trades, lambda t: (t["regime"], t["exit_reason"]))
    tot = {k: math.fsum(t["net_r"] for t in v) for k, v in groups.items()}
    den = math.fsum(abs(x) for x in tot.values())
    cells = _cells(groups, lambda v: {"toplam_r": math.fsum(t["net_r"] for t in v),
                                      "pay": (abs(math.fsum(t["net_r"] for t in v)) / den) if den else None}, ["kosul", "cikis_nedeni"])
    blocks.append(SubTable("kosul_cikis_nedeni", "3.3 Giriş koşulu × çıkış nedeni", "net_r", cells, ["kosul", "cikis_nedeni", "toplam_r", "pay"], [], section))

    # ---- 8.4 haftalik etiket
    pool: dict[str, list] = {}
    for t in trades:
        pool.setdefault(I.iso_week(t["bar_close_ts"]), []).append((t["pair"], t["net_r"], t["bar_close_ts"][:10]))
    kaynak = "alinan"
    if cf:
        dec = {d["id"]: d for d in decisions}
        for did, c in cf.items():
            b = c.get("barrier")
            d = dec.get(did)
            if b and d and d["final_action"] == "skipped" and b["hyp_r_net"] is not None:
                pool.setdefault(I.iso_week(d["bar_close_ts"]), []).append((d["pair"], b["hyp_r_net"], d["bar_close_ts"][:10]))
                kaynak = "aday"

    def lab(vals):
        if len(vals) < 5:
            return "yetersiz"
        return "trend_odedi" if mean(vals) > 0 else "trend_odemedi"
    wrows = []
    for w, v in sorted(pool.items()):
        cm = cluster_mean([x[1] for x in v], [x[2] for x in v])
        wrows.append({"hafta": w, "n": len(v), "G": cm["G"], "ort": cm["m"], "aralik": [cm["lo"], cm["hi"]] if cm["lo"] is not None else None,
                      "etiket": lab([x[1] for x in v])})
    blocks.append(plain("hafta_etiket", "3.4 Haftalık 'trend ödedi' etiketi", ["hafta", "n", "G", "ort", "aralik", "etiket"], wrows,
                        [f"etiket_kaynagi: {kaynak}", WEEK_NOTE]))

    def tlab(t):
        v = [x[1] for x in pool.get(I.iso_week(t["bar_close_ts"]), []) if x[0] != t["pair"]]
        return lab(v)
    cells = _cells(_split(trades, tlab), _wr)
    blocks.append(SubTable("hafta_etiket_sonuc", "3.4b Hafta etiketine göre sonuç (işlemin kendi çifti hariç)", "net_r", cells,
                           ["kazanc_orani", "toplam_r"], [WEEK_NOTE], section))

    # ---- 8.5 cikis kosulu
    if not has_exit_regime:
        blocks.append({"kind": "text", "text": EXIT_REGIME_MISSING})
    else:
        cells = _cells(_split(trades, lambda t: (t["regime"], t.get("exit_regime") or "bilinmiyor")), None, ["giris_kosulu", "cikis_kosulu"])
        blocks.append(SubTable("kosul_gecis", "3.5 Giriş koşulu → çıkış koşulu", "net_r", cells, ["giris_kosulu", "cikis_kosulu"], [], section))

    # ---- standart dokumler
    for tid, title, kf in (("dokum_cift", "4.1 Çift", lambda t: t["pair"]), ("dokum_yon", "4.2 Yön", lambda t: t["side"]),
                           ("dokum_kurulum", "4.3 Kurulum", lambda t: t["setup"]),
                           ("dokum_saat", "4.4 UTC saat dilimi", lambda t: hour_bucket(t["entry_ts"])),
                           ("dokum_gun", "4.5 Haftanın günü", lambda t: WEEKDAYS[I.utc_dt(t["entry_ts"]).weekday()])):
        blocks.append(SubTable(tid, title, "net_r", _cells(_split(trades, kf), None, ["deger"]), ["deger"], [], section))

    yr = {"tumu": year_rows([_item(t) for t in trades])}
    for (su, sd), v in sorted(_split(trades, lambda t: (t["setup"], t["side"])).items()):
        yr[f"{su} × {sd}"] = year_rows([_item(t) for t in v])
    return {"blocks": blocks, "years": yr, "data": {"etiket_kaynagi": kaynak}}
