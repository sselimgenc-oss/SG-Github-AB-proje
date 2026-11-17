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
    assert ref[FEATURE_NAMES].iloc[:cut].notna().any().any()


def test_bars_since_exit_uses_only_real_exits_of_taken_trades(table):
    t = add_bars_since_exit(table.copy())
    assert (t["f_bars_since_exit"].dropna() >= 0).all()
    # alinmayan adaylarin bariyer bitisi (label_end_ts) ve exit_ts'i canlida GORUNMEZ: bozmak sonucu degistirmez
    t2 = table.copy()
    t2["label_end_ts"] = t2["label_end_ts"] + pd.Timedelta(days=30)
    t2.loc[~t2["taken"], "exit_ts"] = t2.loc[~t2["taken"], "ts"] + pd.Timedelta(hours=1)
    t2 = add_bars_since_exit(t2)
    pd.testing.assert_series_equal(t["f_bars_since_exit"], t2["f_bars_since_exit"])
    # gelecegi bozma: son satirlarin (alinan) exit_ts'ini ileri atmak onceki satirlari etkilemez
    k = len(table) // 2
    t3 = table.copy()
    t3.loc[t3.index[k:], "exit_ts"] = t3["exit_ts"].iloc[k:] + pd.Timedelta(days=30)
    t3 = add_bars_since_exit(t3)
    pd.testing.assert_series_equal(t["f_bars_since_exit"].iloc[:k], t3["f_bars_since_exit"].iloc[:k])
    # elle: tek cift, alinan islem 10:00'da cikti; 09:00'daki aday gormez, 12:00'daki 2 mum der; alinmayan sayilmaz
    base = pd.Timestamp("2025-03-01", tz="UTC")
    h = pd.Timedelta(hours=1)
    m = pd.DataFrame({"pair": "X", "ts": [base, base + 4 * h, base + 9 * h, base + 12 * h],
                      "taken": [True, False, True, True],
                      "exit_ts": [base + 10 * h, base + 5 * h, base + 11 * h, base + 20 * h],
                      "label_end_ts": [base + 3 * h] * 4})
    got = add_bars_since_exit(m)["f_bars_since_exit"].tolist()
    assert np.isnan(got[0]) and np.isnan(got[1]) and np.isnan(got[2]) and got[3] == 1.0
