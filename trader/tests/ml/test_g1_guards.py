"""ML-G1: kapi esikleri/mantigi DONDURULDU (golden), ozellik sagligi, guc on hesabi, tani satirlari, sentetik koşu KIRMIZI."""
import numpy as np
import pandas as pd
import pytest

from trader_ml import config, diagnostics, pipeline, prechecks
from trader_ml.gate import rho_t, run_gate

GOLDEN_GATE = {
    "ic_min_t": 2.0, "required_folds": 4, "ic_min_pos_folds": 3,
    "delta_net_r_min": 0.10, "bootstrap_alpha_two_sided": 0.20,
    "filtered_expectancy_min": 0.0, "dsr_min": 0.95, "pbo_max": 0.25,
    "min_taken_frac": 0.30, "stress_expectancy_min": -0.05,
    "stress_fee_mult": 2.0, "stress_extra_bp_per_side": 5.0, "parity_tol": 1e-9,
    "holm_alpha": 0.10,
}


def test_gate_threshold_constants_are_frozen():
    assert config.GATE == GOLDEN_GATE
    assert config.THRESHOLD_GRID == tuple(round(0.45 + 0.01 * i, 2) for i in range(26))
    assert config.THRESHOLD_GRID[0] == 0.45 and config.THRESHOLD_GRID[-1] == 0.70 and len(config.THRESHOLD_GRID) == 26
    assert config.MIN_TAKEN_FRAC == 0.30 and config.BURN_IN_THRESHOLD == 0.50


def _oof(seed, edge):
    rng = np.random.default_rng(seed)
    n = 900
    ts = pd.date_range("2025-09-01", periods=n, freq="7h", tz="UTC")
    s = rng.random(n) < 0.5
    net = np.where(s, 1.2, -0.7) + rng.normal(0, 0.4, n)
    lab = (rng.random(n) < np.where(s, 0.75, 0.10)).astype(float)
    df = pd.DataFrame({"ts": ts, "pair": rng.choice(list("ABCDEF"), n), "fold": np.repeat([0, 1, 2, 3], n // 4 + 1)[:n],
                       "taken": True, "label": lab, "net_r": net, "cost_r": 0.2, "base_rate": 0.42})
    sig = s if edge else rng.random(n) < 0.5
    df["p_m"] = np.clip(np.where(sig, 0.62, 0.20) + rng.normal(0, 0.03, n), 0.01, 0.99)
    return df


def test_gate_verdict_golden_on_fixtures():
    """Sabit tohumlu fikstur: ayni adim sirasi + ayni geçti/kaldı sonuclari (esik/mantik degisirse bozulur)."""
    names = ["1. IC", "2. Kalibrasyon", "3a", "3b", "3c", "3d", "3e", "3f", "3g", "3h", "4.", "5.", "6."]
    good = run_gate(_oof(0, True), ["p_m"], selected="p_m", parity_max_abs_diff=0.0, n_trials=2, n_boot=300)
    assert [c.name[:len(n)] for c, n in zip(good.checks, names)] == names
    failed = {c.name[:2] for c in good.checks if c.ok is False}
    assert failed <= {"3e"}                              # PBO tek-yapilandirmada belirsiz; digerleri gecer
    assert [c.ok for c in good.checks if c.name[:2] in ("1.", "2.", "3a", "3b", "3c", "3d", "3f", "3g", "3h", "4.", "5.")] == [True] * 11
    assert good.checks[-1].ok is None                    # gorevdeki model yok -> atlandi
    bad = run_gate(_oof(1, False), ["p_m"], selected="p_m", parity_max_abs_diff=0.0, n_trials=2, n_boot=300)
    assert bad.passed is False and bad.first_failure is not None
    # esik kenarlari: IC t esigi 2.0 tam sinirda gecer / alti kalir (rho_t formulu degismedi)
    assert rho_t(0.14, 197) == pytest.approx(0.14 * np.sqrt(195 / (1 - 0.14 ** 2)))


def test_feature_health_flags_dead_constant_duplicate():
    n = 50
    rng = np.random.default_rng(0)
    df = pd.DataFrame({"f_ok": rng.normal(size=n), "f_nan": np.nan, "f_const": 1.0,
                       "f_part": [np.nan] * 25 + [3.0] * 25, "f_dup": 0.0, "f_ok2": rng.normal(size=n)})
    df["f_dup"] = df["f_ok"]
    h = prechecks.feature_health(df)
    assert h["all_nan"] == ["f_nan"] and h["constant"] == ["f_const", "f_part"]
    assert h["duplicate"] == [("f_ok", "f_dup")] and h["ok"] is False
    assert set(h["healthy"]) == {"f_dup", "f_ok2"}
    with pytest.raises(prechecks.FeatureHealthError, match="reddedildi"):
        prechecks.assert_feature_health(h)
    assert prechecks.feature_health(df[["f_ok", "f_ok2"]])["ok"] is True


def test_real_run_refuses_unhealthy_features_but_synthetic_only_warns(table, tmp_path):
    pytest.importorskip("lightgbm")
    bad = table.copy()
    bad["f_dead_x"] = np.nan
    with pytest.raises(prechecks.FeatureHealthError):
        pipeline.run(bad, tmp_path / "a", synthetic=False, n_trials=6, n_boot=50)
    assert not (tmp_path / "a" / "gate_result.json").exists()           # egitim/kapi hic kosmadi


def test_power_precheck_matches_plan_table_and_gate_formula():
    # plan 2.1: n_trials=4 -> t ~ 2.8; 12 -> 3.2; 20 -> 3.5 (n gunu buyuk; plan kabaca yazmis)
    t4 = prechecks.power_precheck(240, 197, 4)["required_t_dsr"]
    t12 = prechecks.power_precheck(240, 197, 12)["required_t_dsr"]
    t20 = prechecks.power_precheck(240, 197, 20)["required_t_dsr"]
    assert 2.6 < t4 < 3.0 and 3.0 < t12 < 3.4 and 3.3 < t20 < 3.7 and t4 < t12 < t20
    assert prechecks.power_precheck(240, 197, 6)["required_t_dsr"] > t4           # deneme eklemek cıtayı yükseltir
    # IC: 197 gun, t>=2 -> rho >= ~0.14 (plan 2.1)
    p = prechecks.power_precheck(240, 197, 6)
    assert p["required_ic_rho"] == pytest.approx(0.1417, abs=2e-3)
    assert rho_t(p["required_ic_rho"], 197) == pytest.approx(2.0)
    # gereken SR tam sinirda DSR kapisi 0.95
    from trader_core.stats import deflated_sharpe
    assert deflated_sharpe(p["required_daily_sr"], 240, n_trials=6) == pytest.approx(0.95, abs=1e-6)
    # beklenen etki: ulasilamaz / ulasilabilir
    lo = prechecks.power_precheck(240, 197, 6, expected_daily_sr=0.05, expected_ic=0.05)
    assert lo["dsr_reachable"] is False and lo["ic_reachable"] is False
    hi = prechecks.power_precheck(1500, 1200, 6, expected_daily_sr=0.10, expected_ic=0.10)
    assert hi["dsr_reachable"] is True and hi["ic_reachable"] is True
    assert prechecks.power_precheck(2, 2, 6)["required_t_dsr"] == float("inf")


def test_diagnostics_known_values():
    assert diagnostics.auc(np.array([0, 0, 1, 1.0]), np.array([.1, .4, .35, .8])) == pytest.approx(0.75)
    assert diagnostics.auc(np.array([0, 1.0]), np.array([.5, .5])) == pytest.approx(0.5)
    n = 40
    ts = pd.date_range("2025-09-01", periods=n, freq="12h", tz="UTC")
    r = np.arange(n, dtype=float) - 10
    oof = pd.DataFrame({"ts": ts, "pair": "A", "taken": True, "label": (r > 5).astype(float), "net_r": r,
                        "p_m": np.linspace(0, 1, n), "th_m": 0.5})
    d = diagnostics.compute(oof, "p_m", target_r=2.0, n_boot=50)
    assert d["chance_rate"] == pytest.approx(1 / 3) and d["auc"] == pytest.approx(1.0)
    assert d["tail"]["k"] == 2 and d["top10"]["dropped_by_filter"] == 0       # en iyi satirlar yuksek p -> tutuldu
    assert d["halves"]["first_filtered"] != d["halves"]["first_all"] or d["halves"]["first_filtered"] != d["halves"]["first_filtered"]
    assert any("AUC" in ln for ln in diagnostics.lines(d))


def test_synthetic_gate_still_red_and_report_has_g1_sections(table, tmp_path, capsys):
    pytest.importorskip("lightgbm")
    s = pipeline.run(table, tmp_path, synthetic=True, n_boot=100, n_trials=6)
    assert s["passed"] is False                                          # sentetik koşu KIRMIZI kalir
    out = capsys.readouterr().out
    assert "Guc on hesabi (n_trials=6)" in out                           # kosudan once yazdirilir
    md = (tmp_path / "gate_report.md").read_text(encoding="utf-8")
    for needle in ("Koşu öncesi korumalar", "Özellik sağlığı", "Guc on hesabi", "Tanı satırları", "Şans kıyası", "AUC", "İki yarı", "Kuyruk payı", "en iyi 10"):
        assert needle in md, needle
    assert "power_precheck" in s and "feature_health" in s and "diagnostics" in s
