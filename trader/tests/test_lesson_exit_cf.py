"""Ders servisi x cikis karsi-olgusu kaniti (docs/cikis-karsi-olgu-spec.md 6-7, 9 test 4-5; docs/ders-spec.md Revizyon 6).

Kanit yalniz DESTEK (agirlik 0,5): hicbir esigi/`eligible`'i (mevcut girdilerde)/skoru degistirmez, otomatik uygulama nedeni degildir;
dosya yoksa davranis bit duzeyinde eskisiyle ayni. Fikstur: `test_lesson_spec` (rr_env) + elle yazilmis exit_counterfactual.sqlite."""
from __future__ import annotations

import json
import math
from datetime import date, datetime, timedelta, timezone

import pytest

COST = {"taker_fee": 0.0, "slip_exit_bps": 0.0, "slip_stop_bps": 0.0}
from test_lesson_spec import (RUN_DAY, acts, active, env, post_shadow, ref_cluster_mean, rr_env, run_to_end,  # noqa: F401
                              snapshot_for)
from trader_core import exit_counterfactual as EC
from trader_core import lesson as LS

UTC = timezone.utc
AS_OF = LS.as_of_for(RUN_DAY)
EPOCH = date(1970, 1, 1)
CUR_BLOCK = (AS_OF.date() - EPOCH).days // 7


def block_start(b: int) -> datetime:
    return datetime.combine(EPOCH + timedelta(days=7 * b), datetime.min.time(), tzinfo=UTC)


def mk(trade_id, entry, role, value, net, *, source="paper", run_id="", censored=0, parity=None, own=3.0, end_days=4):
    """Tek satir (EC._row ile ayni sema); parity: kendi degerinde oynatim icin actual_net_r = net - parity."""
    from exit_cf_support import trade
    tr = trade(trade_id=trade_id, entry_ts=entry, exit_ts=entry + timedelta(days=2), source=source, run_id=run_id,
               own_value=own, actual_net_r=None if parity is None else net - parity)
    rr = EC.ReplayResult("ok", "trail_stop", EC.to_ms(entry) + 3_600_000, 100.0, 1, 1.0, censored=censored)
    r = EC._row(tr, "learner", role, value, entry + timedelta(days=end_days), "last", COST, EC.to_ms(entry),
                EC.to_ms(entry + timedelta(days=end_days)), {"gross_r": net, "fee_r": 0.0, "funding_r": 0.0, "net_r": net},
                "trail_stop", rr, own if parity is not None else None)
    return r


def seed(path, *, blocks=range(CUR_BLOCK - 8, CUR_BLOCK), per_block=5, gain_up=0.3, gain_down=-0.3, noise=0.05,
         parity=0.02, parity_every=1, censored_every=0, source="paper", run_id="", id0=1, base_fn=None):
    """Her blokta `per_block` islem: taban net R + (up/down) kazanc. Doner: satirlar eklenmis depo yolu."""
    rows = []
    i = 0
    for b in blocks:
        for k in range(per_block):
            i += 1
            tid = id0 + i
            e = block_start(b) + timedelta(days=k, hours=12)
            base = (base_fn(i) if base_fn else 0.1 * ((i % 5) - 2))
            wob = noise * ((i % 7) - 3)
            cens = 1 if (censored_every and i % censored_every == 0) else 0
            par = parity if (i % parity_every == 0) else None
            rows.append(mk(tid, e, "base", 3.0, base, source=source, run_id=run_id, censored=cens, parity=par))
            rows.append(mk(tid, e, "up", 3.5, base + gain_up + wob, source=source, run_id=run_id, censored=cens))
            rows.append(mk(tid, e, "down", 2.5, base + gain_down - wob, source=source, run_id=run_id, censored=cens))
    with EC.ExitCfStore(path) as st:
        st.insert(rows)
    return path


@pytest.fixture
def cfpath(rr_env):
    return rr_env.tmp / "exit_counterfactual.sqlite"


def cfg_of(env, **over):
    return post_shadow(env, **over)


# ---------------------------------------------------------------------------------------------- dosya yok => bit duzeyinde eski
def test_absent_file_means_no_evidence_and_unchanged(rr_env):
    cfg = cfg_of(rr_env)
    a, off = snapshot_for(rr_env, cfg), snapshot_for(rr_env, cfg_of(rr_env, exit_cf_enabled=False))
    assert a.cf_exit is None and a.stats_hash == off.stats_hash
    assert "cf_exit" not in a.core_dict() and not any(k.startswith("cfx.") for k in a.facts)
    assert a.entry("trail_atr:up") is None and all(not k.startswith("cf_exit") for m in a.menu for k in m.extra)
    assert "[cf_exit]" not in LS.render_prompt(a, cfg).user
    assert LS.exit_cf_line(None) == "Çıkış denemesi: henüz hesaplanmadı"


def test_unreadable_empty_disabled_and_explicit_path(rr_env, cfpath):
    cfpath.write_bytes(b"sqlite degil" * 30)
    assert snapshot_for(rr_env, cfg_of(rr_env)).cf_exit is None
    cfpath.unlink()
    EC.ExitCfStore(cfpath).close()                                           # bos depo: kanit yok
    assert snapshot_for(rr_env, cfg_of(rr_env)).cf_exit is None
    other = seed(rr_env.tmp / "baska.sqlite")
    assert snapshot_for(rr_env, cfg_of(rr_env)).cf_exit is None             # varsayilan yol: defterin yani
    assert snapshot_for(rr_env, cfg_of(rr_env, exit_cf_path=str(other))).cf_exit["by_alt"]["up"]["n"] == 40
    seed(cfpath)
    assert snapshot_for(rr_env, cfg_of(rr_env, exit_cf_enabled=False)).cf_exit is None


def test_config_locks(rr_env):
    for bad in (dict(exit_cf_min_n=29), dict(exit_cf_days=62), dict(exit_cf_enabled="evet"), dict(exit_cf_reject_cooldown_days=-1)):
        with pytest.raises(LS.LessonConfigError):
            cfg_of(rr_env, **bad)
    c = cfg_of(rr_env)
    assert (c.exit_cf_enabled, c.exit_cf_path, c.exit_cf_min_n, c.exit_cf_days, c.exit_cf_reject_cooldown_days) == (True, None, 30, 120, 28)


# ---------------------------------------------------------------------------------------------- istatistik (test 5)
def rows_of(values_by_block, per=5, base_block=CUR_BLOCK - 9):
    out = []
    for j, v in enumerate(values_by_block):
        for k in range(per):
            out.append({"delta_r": v, "entry_ts": EC.fmt_ms(EC.to_ms(block_start(base_block + j) + timedelta(days=k, hours=12))),
                        "censored": 0})
    return out


PAR_OK = {"status": "ok", "n": 30}


def stats(rows, parity=PAR_OK, **over):
    return LS._cf_exit_stats(cfg_of_min(**over), rows, parity)


def cfg_of_min(**over):
    return LS.LessonConfig(**over)


def test_block_is_seven_day_epoch_aligned():
    assert LS._cf_exit_block("1970-01-07T10:00:00.000Z") == 0 and LS._cf_exit_block("1970-01-08T00:00:00.000Z") == 1
    assert LS.CF_EXIT_BLOCK_DAYS == 7 and LS.CF_EXIT_MIN_BLOCKS == 8 and LS.CF_EXIT_Z_ADJ == 1.6449 and LS.CF_EXIT_WEIGHT == LS.CF_WEIGHT == 0.5


def test_hand_computed_cluster_se_and_support():
    vb = [0.1, 0.3, 0.2, 0.4, 0.1, 0.3, 0.2, 0.4]            # 8 blok x 5 islem
    b = stats(rows_of(vb))
    m = 0.25
    u = [5 * (v - m) / 40 for v in vb]
    se = math.sqrt(8 / 7 * sum(x * x for x in u))
    assert b["n"] == 40 and b["blocks"] == 8 and b["mean_delta_r"] == pytest.approx(m)
    assert b["lb_adj"] == pytest.approx(m - 1.6449 * se, abs=1e-4) and b["ub_adj"] == pytest.approx(m + 1.6449 * se, abs=1e-4)
    assert b["lb90"] == pytest.approx(m - 1.2815515655446004 * se, abs=1e-4)
    assert b["loo_mean"] == pytest.approx((10.0 - 0.4) / 39, abs=1e-4) and b["verdict"] == "supports_change"
    xs = [(r["delta_r"], str(LS._cf_exit_block(r["entry_ts"]))) for r in rows_of(vb)]
    _m, ref_se, _ = ref_cluster_mean(xs)
    assert ref_se == pytest.approx(se)


def test_lb90_positive_but_bonferroni_bound_not_gives_inconclusive():
    vb = [0.47, -0.13] * 4                                    # m/SE ~ 1,5: lb90 > 0, lb_adj <= 0
    b = stats(rows_of(vb))
    assert b["lb90"] > 0 and b["lb_adj"] <= 0 and b["verdict"] == "inconclusive"


def test_against_change_when_upper_adjusted_bound_negative():
    b = stats(rows_of([-0.1, -0.3, -0.2, -0.4, -0.1, -0.3, -0.2, -0.4]))
    assert b["ub_adj"] < 0 and b["verdict"] == "against_change"


def test_minimum_n_blocks_and_ongoing_block_rules():
    vb = [0.1, 0.3, 0.2, 0.4, 0.1, 0.3, 0.2, 0.4]
    assert stats(rows_of(vb, per=5)[:29])["verdict"] == "insufficient_n"
    assert stats(rows_of(vb, per=5)[:30])["n"] == 30
    assert stats(rows_of(vb[:7], per=5))["verdict"] == "insufficient_days"            # 7 blok < 8
    assert stats(rows_of(vb), exit_cf_min_n=41)["verdict"] == "insufficient_n"        # esik yalniz yukari ayarlanabilir


def test_top5_share_trim_and_loo_by_hand():
    rows = rows_of([0.1] * 8)
    vals = [0.1] * 40
    for i, v in enumerate((2.0, -1.0)):
        rows[i]["delta_r"] = v
        vals[i] = v
    b = stats(rows)
    top = sorted(range(40), key=lambda i: (-abs(vals[i]), i))[:2]                      # ceil(0,05 x 40) = 2
    assert b["n_top"] == 2 and b["top5_share"] == pytest.approx(sum(vals[i] for i in top) / sum(vals), abs=1e-4)
    rest = [vals[i] for i in range(40) if i not in top]
    assert b["mean_trim"] == pytest.approx(sum(rest) / len(rest), abs=1e-4)
    assert b["loo_mean"] == pytest.approx((sum(vals) - 2.0) / 39, abs=1e-4)


def test_censored_share_above_ten_percent_is_inconclusive():
    vb = [0.1, 0.3, 0.2, 0.4, 0.1, 0.3, 0.2, 0.4]
    rows = rows_of(vb)
    for r in rows[:5]:
        r["censored"] = 1                                                              # 5/40 = %12,5 > %10
    b = stats(rows)
    assert b["censored_share"] == pytest.approx(0.125) and b["verdict"] == "inconclusive" and b["horizon_heavy"] == 1
    for r in rows[:4]:
        r["censored"] = 0
    assert stats(rows)["verdict"] == "supports_change" and stats(rows)["censored_share"] == pytest.approx(0.025)   # <= %10: engel yok


def test_parity_unknown_or_bad_gives_degraded_but_numbers_shown():
    rows = rows_of([0.1, 0.3, 0.2, 0.4, 0.1, 0.3, 0.2, 0.4])
    b = stats(rows, parity={"status": "parity_unknown", "n": 3})
    assert b["verdict"] == "degraded" and b["mean_delta_r"] == pytest.approx(0.25) and b["lb_adj"] is not None
    assert LS.exit_cf_extra({"by_alt": {"up": b}}, "trail_atr:up")["cf_exit_support"] == 0
    assert stats(rows, parity={"status": "degraded", "n": 30})["verdict"] == "degraded"


# ---------------------------------------------------------------------------------------------- okuma / pencere
def test_builds_from_store_completed_blocks_only_and_backtest_is_info(rr_env, cfpath):
    seed(cfpath)
    cfg = cfg_of(rr_env)
    cf = LS.build_exit_counterfactual(cfg, AS_OF)
    up = cf["by_alt"]["up"]
    assert cf["available"] and cf["weight"] == 0.5 and cf["days"] == 120 and cf["parity"]["status"] == "ok"
    assert up["n"] == 40 and up["verdict"] == "supports_change" and cf["by_alt"]["down"]["verdict"] == "against_change"
    # suren blok (as_of'u iceren) dislanir; hukum haftada en cok bir kez degisir
    seed(cfpath, blocks=[CUR_BLOCK], per_block=5, gain_up=-5.0, id0=500)
    assert LS.build_exit_counterfactual(cfg, AS_OF)["by_alt"]["up"] == up
    # bir sonraki blok tamamlaninca (as_of +7 gun) girer
    later = LS.build_exit_counterfactual(cfg, AS_OF + timedelta(days=7))["by_alt"]["up"]
    assert later["n"] == 45 and later["mean_delta_r"] < up["mean_delta_r"]
    # backtest satirlari hukmu/n'yi DEGISTIRMEZ; yalniz bilgi blogu
    seed(cfpath, source="backtest", run_id="1h_IS_f1_s0_native_last", gain_up=-3.0, blocks=range(CUR_BLOCK - 20, CUR_BLOCK - 8), id0=900)
    cf2 = LS.build_exit_counterfactual(cfg, AS_OF)
    assert cf2["by_alt"] == cf["by_alt"]
    bt = cf2["backtest"]["up"]
    assert bt["n"] == 60 and bt["info_only"] == 1 and bt["in_sample"] == 1 and bt["source"] == "backtest" and bt["source_conflict"] == 1


def test_only_outcomes_known_by_as_of_and_window_days(rr_env, cfpath):
    seed(cfpath, blocks=range(CUR_BLOCK - 12, CUR_BLOCK))
    cfg = cfg_of(rr_env)
    assert LS.build_exit_counterfactual(cfg, AS_OF - timedelta(days=21))["by_alt"]["up"]["n"] < 60     # sonuc as_of'ta henuz bilinmiyor
    assert LS.build_exit_counterfactual(cfg, AS_OF)["by_alt"]["up"]["n"] == 60
    short = cfg_of(rr_env, exit_cf_days=63)
    assert LS.build_exit_counterfactual(short, AS_OF)["by_alt"]["up"]["n"] < 60                         # pencere disi giris


# ---------------------------------------------------------------------------------------------- menu (test 4)
def strip(m):
    return {**m.to_dict(), "extra": {k: v for k, v in m.extra.items() if not k.startswith("cf_exit")}}


def test_menu_up_entry_supported_and_existing_entries_unchanged(rr_env, cfpath):
    cfg = cfg_of(rr_env)
    before = snapshot_for(rr_env, cfg)
    seed(cfpath)
    after = snapshot_for(rr_env, cfg)
    up = after.entry("trail_atr:up")
    assert (up.evidence_class, up.semantics, up.eligible, up.auto_capable, up.always_user) == ("exit_cf_only", "loosen", True, False, True)
    assert up.from_value == 3.0 and up.to_value == 3.5 and up.checkpoint_c is None and up.stream == "trail_atr|exit_cf"
    assert up.extra["cf_exit_n"] == 40 and up.extra["cf_exit_support"] == 1 and up.extra["cf_exit_n_eff"] == 20.0
    for k in ("cf_exit_mean_delta_r", "cf_exit_lb90", "cf_exit_lb_adj", "cf_exit_ub_adj", "cf_exit_top5_share", "cf_exit_censored_share"):
        assert k in up.extra
    # mevcut kural girdileri: yalniz bilgi alanlari eklenir; esik/eligible/auto/skor/kontrol noktasi ayni
    old = [m for m in before.menu]
    new = [m for m in after.menu if m.menu_id != "trail_atr:up"]
    assert [strip(m) for m in old] == [strip(m) for m in new]
    assert [(m.eligible, m.auto_capable, m.score, m.checkpoint_c) for m in old] == [(m.eligible, m.auto_capable, m.score, m.checkpoint_c) for m in new]
    dn = after.entry("trail_atr:down")
    if dn is not None:
        assert dn.extra["cf_exit_n"] == 40 and dn.extra["cf_exit_support"] == 0
    assert before.checkpoints == after.checkpoints and before.stats_hash != after.stats_hash
    assert after.facts["cfx.trail_atr.up.n"] == 40 and after.facts["menu.trail_atr:up.cf_exit_n"] == 40
    back = LS.Snapshot.from_dict(json.loads(json.dumps(after.to_dict())))
    assert back.cf_exit == after.cf_exit and back.core_dict() == after.core_dict()


def test_up_entry_not_eligible_unless_supports_change(rr_env, cfpath):
    seed(cfpath, gain_up=0.0, noise=0.4)
    up = snapshot_for(rr_env, cfg_of(rr_env)).entry("trail_atr:up")
    assert up is not None and up.eligible is False and up.auto_capable is False and up.extra["cf_exit_support"] == 0
    assert any(f.startswith("exit_cf_") for f in up.fail_reasons)


def test_up_entry_not_eligible_when_degraded(rr_env, cfpath):
    seed(cfpath, parity=0.5)
    up = snapshot_for(rr_env, cfg_of(rr_env)).entry("trail_atr:up")
    assert up.eligible is False and "exit_cf_degraded" in up.fail_reasons and up.extra["cf_exit_support"] == 0
    assert up.extra["cf_exit_mean_delta_r"] > 0                                    # sayilar gosterilir


def test_up_entry_absent_at_bound(rr_env, cfpath):
    seed(cfpath)
    cfg = cfg_of(rr_env)
    led = rr_env.ro()
    try:
        snap = LS.build_snapshot(led, cfg, RUN_DAY)
    finally:
        led.close()
    hi = snap.bounds["trail_atr"][1]
    assert snap.entry("trail_atr:up").to_value <= hi


def test_up_never_auto_capable_calibration_and_proxy(rr_env, cfpath):
    seed(cfpath)
    cfg = cfg_of(rr_env, proxy_include_ask_user=True)
    snap = snapshot_for(rr_env, cfg)
    assert "trail_atr:up" not in {r.menu_id for r in LS._CAL_RULES}
    assert LS.RULES_BY_ID["trail_atr:up"].evidence_class == "exit_cf_only"
    assert not any(m.auto_capable for m in snap.menu if m.menu_id == "trail_atr:up")
    assert all(m.menu_id != "trail_atr:up" for m in snap.menu if m.auto_capable)
    for m in snap.menu:
        if m.menu_id != "trail_atr:up":
            assert m.evidence_class != "exit_cf_only"
    # baska hicbir parametre/yon icin kanit-yalniz girdi yok
    # Revizyon 7 (docs/cikis-kipleri-spec.md 7): kanit-yalniz kalip yalniz iki cikis kipi girdisiyle genisletildi
    assert [r.menu_id for r in LS.RULES_V1 if r.evidence_class == "exit_cf_only"] == [
        "trail_atr:up", "exit:breakeven", "exit:partial"]


def test_classify_route_forces_needs_user_with_exit_cf_evidence(rr_env, cfpath):
    seed(cfpath)
    cfg = cfg_of(rr_env)
    snap = snapshot_for(rr_env, cfg)
    up = snap.entry("trail_atr:up")
    d = LS.ProposalDraft("change", "trail_atr:up", "trail_atr", up.to_value, "r", (), "low", "llm")
    r = LS.classify_route(snap, d, cfg)
    assert (r.klass, r.reason_code) == ("ask_user", "counterfactual_exit_support")
    assert "counterfactual_exit_support" in LS.REASON_PRIORITY
    assert LS.REASON_PRIORITY.index("counterfactual_support") < LS.REASON_PRIORITY.index("counterfactual_exit_support") < LS.REASON_PRIORITY.index("off_menu")
    # kanit yokken eski davranis
    plain = snapshot_for(rr_env, cfg_of(rr_env, exit_cf_enabled=False))
    dn = plain.entry("trail_atr:down")
    if dn is not None:
        d2 = LS.ProposalDraft("change", "trail_atr:down", "trail_atr", dn.to_value, "r", (), "low", "llm")
        assert LS.classify_route(plain, d2, cfg).reason_code == "weak_evidence"


def test_service_never_auto_applies_with_exit_cf_evidence(rr_env, monkeypatch):
    # kanitsiz: rr_min:up golge sonrasi otomatik uygulanir; kanitli (zorla cf_exit_n): needs_user, aktivasyon yok
    monkeypatch.setattr(LS, "exit_cf_extra", lambda cf, mid: {"cf_exit_n": 40, "cf_exit_support": 0} if mid == "rr_min:up" else {})
    monkeypatch.setattr(LS, "build_exit_counterfactual", lambda cfg, as_of, path=None: {"available": True, "days": 120, "min_n": 30, "weight": 0.5,
                                                                                         "step": 0.5, "parity": {}, "by_alt": {}, "backtest": {}})
    st = run_to_end(rr_env, cfg_of(rr_env))[1]
    assert st[0] == "needs_user" and st[1] == "counterfactual_exit_support"
    assert active(rr_env) == 1 and not [a for a in acts(rr_env) if a[0] == "apply"]
    body = rr_env.notifier.approvals[-1]
    assert body.reason_code == "counterfactual_exit_support" and "varsayimsal oynatim" in body.body and "kuyruk payi" in body.body


def test_route_structural_guard_even_if_classifier_says_auto(rr_env, monkeypatch):
    monkeypatch.setattr(LS, "exit_cf_extra", lambda cf, mid: {"cf_exit_n": 40} if mid == "rr_min:up" else {})
    monkeypatch.setattr(LS, "build_exit_counterfactual", lambda cfg, as_of, path=None: {"available": True, "days": 120, "min_n": 30, "weight": 0.5,
                                                                                         "step": 0.5, "parity": {}, "by_alt": {}, "backtest": {}})
    monkeypatch.setattr(LS, "classify_route", lambda snap, draft, cfg: LS.Route("auto", None, (), False, False))
    st = run_to_end(rr_env, cfg_of(rr_env))[1]
    assert st[0] == "needs_user" and st[1] == "counterfactual_exit_support"
    assert not [a for a in acts(rr_env) if a[0] == "apply"]


def test_blacklisted_up_entry_is_not_eligible(rr_env, cfpath):
    seed(cfpath)
    snap = LS.build_snapshot(rr_env.ro(), cfg_of(rr_env), RUN_DAY, blacklist={("trail_atr", "up"): LS.fmt_ts(AS_OF + timedelta(days=5))})
    up = snap.entry("trail_atr:up")
    assert up.eligible is False and "blacklisted" in up.fail_reasons and up.checks["not_blacklisted"] is False


# ---------------------------------------------------------------------------------------------- istem, olgular, ozet
def test_prompt_facts_and_cites(rr_env, cfpath):
    seed(cfpath)
    seed(cfpath, source="backtest", run_id="1h_IS_f1_s0_native_last", gain_up=-3.0, blocks=range(CUR_BLOCK - 20, CUR_BLOCK - 8), id0=900)
    cfg = cfg_of(rr_env)
    snap = snapshot_for(rr_env, cfg)
    user = LS.render_prompt(snap, cfg).user
    assert "[cf_exit]" in user and user.index("[counterfactual]") < user.index("[cf_exit]") < user.index("[recent_trades]") \
        if "[counterfactual]" in user else user.index("[cf_exit]") < user.index("[recent_trades]")
    assert "weight=0.5" in user and "never a sole basis" in user and "tails are heavy" in user
    assert "cfx param=trail_atr dir=up n=40" in user and "verdict=supports_change" in user and "lb_adj=" in user
    assert "cfx_bt param=trail_atr dir=up n=60" in user and "in_sample=1 info_only" in user
    assert LS.SYSTEM_PROMPT.count("cfx") == 0
    up = snap.entry("trail_atr:up")
    cites = LS._required_cites(up)
    assert all(k in snap.facts for k in cites)
    prop = LS.propose_rule_proxy(snap, cfg_of(rr_env, proxy_include_ask_user=True))
    assert prop.menu_id != "trail_atr:up" or prop.decision == "change"


def test_daily_summary_and_line(rr_env, cfpath):
    seed(cfpath)
    cfg = cfg_of(rr_env)
    svc, _ = run_to_end(rr_env, cfg)
    s = svc.daily_summary(RUN_DAY)["exit_counterfactual"]
    assert s["available"] is True and s["n"] == 40 and "\n" not in s["line"] and s["line"].startswith("Çıkış denemesi (son 120 gün")
    assert "iz stopu 0,50 gevşek (n=40)" in s["line"] and "varsayımsal; gerçek dolum yok" in s["line"]
    assert s["line"].endswith("değişiklik için sana sorulur")
    cf = LS.build_exit_counterfactual(cfg, AS_OF)
    assert LS.exit_cf_line(cf) == s["line"]


def test_line_phrases():
    base = {"days": 120, "step": 0.5, "by_alt": {"up": {"n": 42, "mean_delta_r": 0.06, "verdict": "inconclusive"},
                                                  "down": {"n": 10, "mean_delta_r": -0.2, "verdict": "insufficient_n"}}}
    assert LS.exit_cf_line(base) == ("Çıkış denemesi (son 120 gün, varsayımsal; gerçek dolum yok): iz stopu 0,50 gevşek (n=42): "
                                     "ortalama +0,06 R fark, güvenilir değil — sonuç yalnız bilgi, değişiklik için sana sorulur")
    base["by_alt"]["up"]["verdict"] = "degraded"
    assert "oynatım gerçek çıkıştan sapıyor / henüz doğrulanmadı" in LS.exit_cf_line(base)


def test_no_new_live_exit_modes_no_blocking():
    """1a kapsami (v1 yolu): yalniz kanit; v1 oynatimi/gece isi cikis kipi acmaz. Kipler (1b, Revizyon 7) ayri `run_modes_once` /
    `ecf_modes` yolunda ve `replay_trail(modes=None)` varsayilaniyla kapalidir."""
    import inspect
    for fn in (EC.run_once, EC._compute_trade, EC.deltas, EC.parity_stats):
        src = inspect.getsource(fn).lower()
        for word in ("breakeven", "partial", "take_profit"):
            assert word not in src, (fn.__name__, word)
    assert inspect.signature(EC.replay_trail).parameters["modes"].default is None
