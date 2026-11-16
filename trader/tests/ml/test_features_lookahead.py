"""Ozellikler kati nedensel: gelecek mumlar bozulunca karar anindaki ozellikler DEGISMEZ."""
import numpy as np
import pandas as pd

from trader_ml.config import BAR
from trader_ml.features import BTC, ETH, FEATURE_NAMES, add_bars_since_exit, feature_frame
from trader_ml.config import MAX_FEATURES


def _perturb(df, cut, rng):
    d = df.copy()
    n = len(d) - cut
    c = d["close"].to_numpy().copy()
    c[cut:] = c[cut - 1] * np.exp(np.cumsum(rng.normal(0.01, 0.05, n)))
    o = np.concatenate([[c[cut - 1]], c[cut:-1]])
    d.iloc[cut:, d.columns.get_loc("close")] = c[cut:]
    d.iloc[cut:, d.columns.get_loc("open")] = o
    d.iloc[cut:, d.columns.get_loc("high")] = np.maximum(o, c[cut:]) * 1.02
    d.iloc[cut:, d.columns.get_loc("low")] = np.minimum(o, c[cut:]) * 0.98
    return d


def test_feature_count_within_design_limit():
    assert len(FEATURE_NAMES) <= MAX_FEATURES and len(set(FEATURE_NAMES)) == len(FEATURE_NAMES)


def test_future_bars_do_not_change_features(candles):
    n = 6000
    base = {k: candles[k].iloc[:n] for k in (BTC, ETH, "SOL/USDT:USDT")}
    sol = base["SOL/USDT:USDT"]
    ref = feature_frame(sol, base[BTC], base[ETH])
    rng = np.random.default_rng(5)
    for cut in (3001, 4003, 5500):               # farkli saat/gun hizalamalari (4s/1g sinirlarinin ortasi dahil)
        pert = {k: _perturb(v, cut, rng) for k, v in base.items()}
        got = feature_frame(pert["SOL/USDT:USDT"], pert[BTC], pert[ETH])
        a, b = ref.iloc[:cut], got.iloc[:cut]            # satir cut-1 son degismemis mum
        pd.testing.assert_frame_equal(a, b, check_exact=True)
    # duyarlilik kontrolu: bozulan bolgede ozellikler GERCEKTEN degisiyor (test bos degil)
    assert not ref.iloc[cut:].equals(got.iloc[cut:])
    assert ref[FEATURE_NAMES[:-1]].iloc[:cut].notna().any().any()


def test_bars_since_exit_uses_only_resolved_candidates(table):
    t = table.copy()
    t = add_bars_since_exit(t)
    # her satir icin: referans cikis, ts'den once ya da esit bitmis olmali -> degerler >= 0
    assert (t["f_bars_since_exit"].dropna() >= 0).all()
    # gelecegi bozma: son satirlarin label_end_ts'ini degistirmek onceki satirlari etkilemez
    k = len(t) // 2
    t2 = t.copy()
    t2.loc[t2.index[k:], "label_end_ts"] = t2["label_end_ts"].iloc[k:] + pd.Timedelta(days=30)
    t2 = add_bars_since_exit(t2)
    pd.testing.assert_series_equal(t["f_bars_since_exit"].iloc[:k], t2["f_bars_since_exit"].iloc[:k])
