"""Derlem v2 + alinan-islem katmani -> koşu tablosu (on kayit docs/ml/r02-r03-on-kayit.md 2.1-2.3).

`load_run_table`: derlem (fiyat bariyeri etiketleri) + katman (motor defterinden alinan islemler, gercek net R) ->
r02/r03 kosu tablosu (trader_ml.schema sozlesmesi). `verify_corpus_manifest`: koşudan once manifestte 2.1 alanlari
BIREBIR dogrulanir (biri tutmazsa kosu baslamaz). Bu modul veri/etiket UretMEZ; yalniz okur, esler, dogrular.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

import numpy as np
import pandas as pd

from .config import HOLDOUT_START
from .features_v2 import R02_FEATURE_NAMES, R03_FEATURE_NAMES
from .guards import assert_pre_holdout
from .schema import FEATURE_PREFIX, validate_candidates

ROOT = Path(__file__).resolve().parents[2]            # trader/ (manifestteki code_sha256 yollari buna goreli)
KEY = ["pair", "ts", "side"]
BASE_COLUMNS = ["pair", "ts", "setup", "side", "planned_entry", "planned_stop", "planned_target", "source", "cost_r"]
CORPUS_REQUIRED = BASE_COLUMNS + ["label_1r", "label_end_ts_1r", "barrier_net_r_1r"]
OVERLAY_REQUIRED = KEY + ["exit_ts", "r_multiple"]
CORPUS_PAIRS = ["BTC", "ETH", "BNB", "SOL", "XRP", "DOGE", "ADA", "TRX", "LINK", "AVAX"]
CORPUS_PAIRS = [f"{c}/USDT:USDT" for c in CORPUS_PAIRS]
R03_EXTRA = [c for c in R03_FEATURE_NAMES if c not in R02_FEATURE_NAMES]
CORPUS_RECIPE_IDS = ["ml1-r02-long-ctx-1r", "ml1-r03-long-regime8"]


class CorpusError(ValueError):
    """Derlem/katman girdisi sozlesmeye uymuyor (kosu baslamaz)."""


def sha256_path(path: str | Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for b in iter(lambda: f.read(1 << 20), b""):
            h.update(b)
    return h.hexdigest()


def _read(x) -> pd.DataFrame:
    if isinstance(x, pd.DataFrame):
        return x.copy()
    p = Path(x)
    if p.suffix == ".parquet":
        return pd.read_parquet(p)
    raise CorpusError(f"desteklenmeyen uzanti: {p.suffix}")


def load_run_table(corpus, overlay, recipe) -> tuple[pd.DataFrame, dict]:
    """(kosu tablosu, bilgi). corpus/overlay: yol ya da DataFrame. Bilgi: satir sayilari, dusen alinmis-acik islem sayisi vb.

    1. label=label_1r, label_end_ts=label_end_ts_1r; label bos (cozulmemis) satirlar atilir.
    2. source -> recipe.source_map (native_v1b -> backtest).
    3. katman (pair, ts, side) ile sol birlestirilir: taken = katmanda var; net_r = r_multiple (alinan) / barrier_net_r_1r;
       exit_ts = gercek cikis (alinan) / bos. Cikisi olmayan (donem sonunda acik) alinmis satirlar atilir ve sayilir.
    4. yalniz tarifin f_* sutunlari (tarifteki sirayla) modele gider; digerleri tabloya HIC girmez.
    """
    df, ov = _read(corpus), _read(overlay)
    lab, lend = recipe.label_col, recipe.label_end_col
    barrier = lab.replace("label", "barrier_net_r", 1)
    need = BASE_COLUMNS + [lab, lend, barrier] + list(recipe.features)
    miss = [c for c in need if c not in df.columns]
    if miss:
        raise CorpusError(f"derlemde eksik sutun: {miss}")
    miss = [c for c in OVERLAY_REQUIRED if c not in ov.columns]
    if miss:
        raise CorpusError(f"katmanda eksik sutun: {miss}")
    df["ts"] = pd.to_datetime(df["ts"], utc=True)
    assert_pre_holdout(df["ts"], "derlem ts")
    ov["ts"] = pd.to_datetime(ov["ts"], utc=True)
    ov["exit_ts"] = pd.to_datetime(ov["exit_ts"], utc=True)
    assert_pre_holdout(ov["ts"], "katman ts")
    assert_pre_holdout(ov["exit_ts"].dropna(), "katman exit_ts")
    if ov.duplicated(KEY).any():
        raise CorpusError("katmanda (pair, ts, side) tekrarli")
    if df.duplicated(KEY).any():
        raise CorpusError("derlemde (pair, ts, side) tekrarli")
    info = {"corpus_rows": int(len(df)), "overlay_rows": int(len(ov)),
            "overlay_unmatched_entered": int((~pd.MultiIndex.from_frame(ov[KEY]).isin(pd.MultiIndex.from_frame(df[KEY]))).sum())}
    n_corpus = len(df)
    df = df[df[lab].notna()].copy()                              # cozulmemis (son 72 mum) atilir
    info["dropped_unresolved"] = n_corpus - int(len(df))

    m = df.merge(ov[KEY + ["exit_ts", "r_multiple"]].assign(_taken=True), how="left", on=KEY)
    taken = m["_taken"].fillna(False).to_numpy(bool)
    out = pd.DataFrame({
        "pair": m["pair"], "ts": m["ts"], "setup": m["setup"], "side": m["side"],
        "planned_entry": m["planned_entry"].astype(float), "planned_stop": m["planned_stop"].astype(float),
        "planned_target": m["planned_target"].astype(float),
        "source": m["source"].map(lambda s: recipe.source_map.get(s, s)),
        "taken": taken,
        "label": m[lab].astype(float), "label_end_ts": pd.to_datetime(m[lend], utc=True),
        "net_r": np.where(taken, m["r_multiple"], m[barrier]).astype(float),
        "cost_r": m["cost_r"].astype(float),
        "exit_ts": m["exit_ts"].where(taken),
    })
    for c in recipe.features:                                    # yalniz tarifin sutunlari, tarifin sirasiyla
        out[c] = m[c].astype(float)
    open_taken = out["taken"] & out["exit_ts"].isna()
    info["dropped_taken_open_at_end"] = int(open_taken.sum())
    out = out[~open_taken]
    nr_bad = out["taken"] & out["net_r"].isna()
    if nr_bad.any():
        raise CorpusError(f"{int(nr_bad.sum())} alinmis satirda r_multiple bos (cikisi var)")
    out = validate_candidates(out)
    info.update(rows=int(len(out)), taken=int(out["taken"].sum()), not_taken=int((~out["taken"]).sum()))
    extra = [c for c in out.columns if c.startswith(FEATURE_PREFIX) and c not in recipe.features]
    assert not extra, extra
    return out.reset_index(drop=True), info


# ------------------------------------------------------------------ manifest dogrulamasi (2.1)
def _eq(errs, name, got, want):
    if got != want:
        errs.append(f"{name}: manifest={got!r} beklenen={want!r}")


def verify_corpus_manifest(man: dict, corpus_path: str | Path, *, root: Path = ROOT) -> tuple[list[str], list[str]]:
    """(hatalar, notlar). Hata listesi bos degilse kosu BASLAMAZ. root: code_sha256 yollarinin goreli oldugu dizin."""
    errs, notes = [], []
    _eq(errs, "corpus_version", man.get("corpus_version"), "corpus_v2")
    _eq(errs, "recipe_ids", man.get("recipe_ids"), CORPUS_RECIPE_IDS)
    _eq(errs, "source", man.get("source"), "native_v1b")
    cd = str(man.get("candidate_definition", ""))
    for tok in ("pre-post_filter", "feature_frame+candidate_rows", "T1", "iki yon", "10 cift"):
        if tok not in cd:
            errs.append(f"candidate_definition '{tok}' icermiyor: {cd!r}")
    per = man.get("period") or {}
    _eq(errs, "period.start", per.get("start"), "2021-01-01 00:00:00+00:00")
    _eq(errs, "period.end_exclusive", per.get("end_exclusive"), "2026-05-01 00:00:00+00:00")
    _eq(errs, "period.holdout_read", per.get("holdout_read"), False)
    try:
        if not pd.Timestamp(per.get("ts_max")) < HOLDOUT_START:
            errs.append(f"period.ts_max {per.get('ts_max')} >= kilitli donem")
    except Exception:
        errs.append(f"period.ts_max okunamadi: {per.get('ts_max')!r}")
    _eq(errs, "pairs", man.get("pairs"), CORPUS_PAIRS)
    _eq(errs, "horizon_bars", man.get("horizon_bars"), 72)
    _eq(errs, "target_rs", [float(x) for x in man.get("target_rs", [])], [1.0, 1.5, 2.0])
    g = man.get("git") or {}
    _eq(errs, "git.tree_clean", g.get("tree_clean"), True)
    if g.get("dirty"):
        errs.append(f"git.dirty bos degil: {g.get('dirty')}")
    if not g.get("commit"):
        errs.append("git.commit yok")
    _eq(errs, "r02_features", man.get("r02_features"), list(R02_FEATURE_NAMES))
    _eq(errs, "r03_features", man.get("r03_features"), list(R03_FEATURE_NAMES))
    _eq(errs, "n_features", man.get("n_features"), 43)
    _eq(errs, "feature_columns", man.get("feature_columns"), list(R02_FEATURE_NAMES) + R03_EXTRA)
    sb = man.get("same_bar") or {}
    _eq(errs, "same_bar.rows_unique_pair_ts", sb.get("rows_unique_pair_ts"), True)
    _eq(errs, "same_bar.feature_matches_distinct_pairs", sb.get("feature_matches_distinct_pairs"), True)
    actual = sha256_path(corpus_path)
    _eq(errs, "corpus.sha256 (diskteki dosya)", (man.get("corpus") or {}).get("sha256"), actual)
    code = man.get("code_sha256") or {}
    if not code:
        errs.append("code_sha256 bos")
    for rel, want in sorted(code.items()):
        p = Path(root) / rel
        if not p.exists():
            errs.append(f"code_sha256: {rel} yok")
        elif sha256_path(p) != want:
            errs.append(f"code_sha256: {rel} manifestten sonra degismis")
    if not man.get("inputs_sha256") or not man.get("input_slices"):
        errs.append("inputs_sha256 / input_slices kayitli degil")
    gaps = {p: v.get("candle_gaps") for p, v in (man.get("input_slices") or {}).items() if v.get("candle_gaps")}
    if gaps:
        notes.append(f"candle_gaps > 0 (arsiv bosluk raporuyla aciklanmali): {gaps}")
    return errs, notes


def verify_overlay_manifest(man: dict, overlay_path: str | Path) -> list[str]:
    """Katman manifesti: dosya sha256'si tutmali, eslesmeyen alinmis islem 0 olmali, donem kilitli doneme girmemeli."""
    errs = []
    _eq(errs, "overlay.sha256 (diskteki dosya)", man.get("sha256"), sha256_path(overlay_path))
    _eq(errs, "overlay.unmatched_entered", man.get("unmatched_entered"), 0)
    _eq(errs, "overlay.period", man.get("period"), "20210101-20260501")
    if not man.get("config_hash"):
        errs.append("overlay.config_hash yok")
    return errs


def load_manifest(path: str | Path) -> dict:
    return json.loads(Path(path).read_text(encoding="utf-8"))
