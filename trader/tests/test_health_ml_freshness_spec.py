"""Bagimsiz kabul testleri: docs/saglik-spec.md Bolum 16 (WP-1: ML paketi suresi/tazeligi, Telegram metinleri,
gunluk rapor "Model" satiri, sapma izleyicisi kancasi). Yalnizca spesifikasyondan yazildi (Bolum 16.7 madde 1-33).

Esleme (madde -> test sinifi): 1 TestOptIn | 2 TestOffAndUnreadable | 3 TestOffAndUnreadable | 4-7 TestExpiryLadder |
8-10 TestEngineStates | 11 TestExpiryLadder | 12 TestInvalidStatus | 13-14 TestRestartNeeded / TestWorstWins |
15 TestFileInvalid | 16 TestStaleDataRunner | 17 TestAbsoluteAge | 18 TestScoreErrorsRunner / TestScoreErrorsEval |
19 TestPackageMetaRunner | 20 TestImports | 21-23 TestAlertTexts / TestAlertSuppression / TestImmediate |
24-30 TestDailyReport | 31-33 TestDriftHook.

Sentetik veri. Spesifikasyonun adlandirmadigi arayuzler (runner durum anahtarlarinin ic bicimi, ml_seen zaman
bicimi, "stale" bayraginin evaluate'e nasil gectigi) varsayim olarak docstring'lerde belirtilmistir.
"""
from __future__ import annotations

import dataclasses
import importlib.util
import itertools
import json
import os
import subprocess
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
SCRIPTS = ROOT / "scripts"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

H = pytest.importorskip("trader_core.health")
Status = H.Status
UTC = timezone.utc
NOW = datetime(2026, 12, 10, 12, 0, 0, tzinfo=UTC)
DAY = timedelta(days=1)
T = 3600
GiB = 1 << 30
MiB = 1 << 20
MID_A = "r02@aaaaaaaaaaaa"
MID_B = "r02@bbbbbbbbbbbb"


def z(dt: datetime) -> str:
    return dt.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


# ==========================================================================
# Anlik goruntu kurucular
# ==========================================================================
def _api(now, **kw):
    base = dict(ping_ok=True, last_process_at=now - timedelta(seconds=30),
                last_candle_open=now.replace(minute=0, second=0, microsecond=0),
                open_trade_ids=(), dry_run=True)
    base.update(kw)
    return H.ApiProbe(**base)


def _ledger(now):
    return H.LedgerProbe(last_write_at=now.replace(minute=0, second=0, microsecond=0) + timedelta(seconds=2),
                         spool_lines=0, unledgered_ids=(), orphan_ids=(), schema_ok=True, has_active_params=True)


def mlp(**kw):
    """MlProbe; varsayilan: active/ok, 30 gun kalan, dosya not_configured, score_errors degismemis (0)."""
    base = dict(present=True, mode="active", state="ok", model_id=MID_A, expires_at=NOW + 30 * DAY, error=None,
                score_errors=0, file_state="not_configured", file_model_id=None, file_created_at=None,
                file_expires_at=None, file_data_hash=None, file_train_end=None, file_gate_passed=None,
                file_user_approved=None)
    base.update(kw)
    return H.MlProbe(**base)


def mk_snap(now=NOW, ml="__none__", drift="__none__", **over):
    base = dict(
        now=now, timeframe_s=T,
        api={b: _api(now) for b in ("learner", "twin")},
        ledger={b: _ledger(now) for b in ("learner", "twin")},
        disk_free_bytes=20 * GiB, disk_total_bytes=100 * GiB, mem_available_bytes=900 * MiB,
        swap_total_bytes=2048 * MiB, swap_used_bytes=int(0.10 * 2048 * MiB),
        containers={f"trader-{b}": H.ContainerProbe("running", 4, now - timedelta(days=2), False)
                    for b in ("learner", "twin")},
        prev_restart_counts={f"trader-{b}": 4 for b in ("learner", "twin")},
        last_backup_at=now - timedelta(hours=3),
    )
    if ml != "__none__":
        base["ml"] = ml
    if drift != "__none__":
        base["drift"] = drift
    base.update(over)
    return H.HealthSnapshot(**base)


def ml_snap(probe, now=NOW, **over):
    return mk_snap(now=now, ml={"learner": probe}, **over)


def ev(snap, cfg=None):
    return H.evaluate(snap) if cfg is None else H.evaluate(snap, cfg)


def ml_res(rep, bot="learner"):
    out = [r for r in rep.results if r.name == f"ml_package:{bot}"]
    assert len(out) == 1, [r.name for r in rep.results]
    return out[0]


def check(probe, *, now=NOW, cfg=None, **over):
    return ml_res(ev(ml_snap(probe, now=now, **over), cfg))


def expect(res, status, code):
    assert (res.status, res.code) == (status, code), res


def file_probe(**kw):
    """Gecerli, motorla ayni model_id'li dosya (hicbir satiri tetiklemez); alanlar ezilebilir."""
    base = dict(file_state="ok", file_model_id=MID_A, file_created_at=NOW - 1 * DAY,
                file_expires_at=NOW + 20 * DAY, file_data_hash="h1", file_train_end=NOW - 2 * DAY,
                file_gate_passed=True, file_user_approved=True)
    base.update(kw)
    return mlp(**base)


# ==========================================================================
# Yapilar
# ==========================================================================
class TestStructures:
    def test_mlprobe_fields_and_frozen(self):
        names = {f.name for f in dataclasses.fields(H.MlProbe)}
        assert names >= {"present", "mode", "state", "model_id", "expires_at", "error", "score_errors", "file_state",
                         "file_model_id", "file_created_at", "file_expires_at", "file_data_hash", "file_train_end",
                         "file_gate_passed", "file_user_approved"}
        p = mlp()
        with pytest.raises(dataclasses.FrozenInstanceError):
            p.mode = "off"  # type: ignore[misc]

    def test_driftprobe_fields_and_frozen(self):
        names = {f.name for f in dataclasses.fields(H.DriftProbe)}
        assert names >= {"file_state", "generated_at", "overall", "rules_at_uyari"}
        d = H.DriftProbe(file_state="ok", generated_at=NOW, overall="OK", rules_at_uyari=())
        with pytest.raises(dataclasses.FrozenInstanceError):
            d.overall = "UYARI"  # type: ignore[misc]

    def test_snapshot_defaults_none(self):
        s = H.HealthSnapshot(now=NOW)
        assert s.ml is None and s.drift is None

    def test_config_new_fields(self):
        c = H.DEFAULT_CFG
        assert tuple(c.ml_warn_days) == (7, 3, 1)
        assert c.ml_data_max_age_days is None
        assert c.drift_max_age_s == 129600
        assert c.drift_check_enabled is False

    @pytest.mark.parametrize("kw", [dict(drift_max_age_s=0), dict(drift_max_age_s=-1),
                                    dict(drift_max_age_s=float("nan")), dict(ml_data_max_age_days=-1),
                                    dict(ml_data_max_age_days=float("nan"))])
    def test_config_rejects_invalid(self, kw):
        with pytest.raises(ValueError):
            H.HealthConfig(**kw)


# ==========================================================================
# 1. opt-in
# ==========================================================================
class TestOptIn:
    def test_none_means_no_ml_check(self):
        rep = ev(mk_snap())
        assert not [r for r in rep.results if r.name.startswith("ml_package")]
        assert rep.overall is Status.OK

    def test_required_checks_unchanged(self):
        assert tuple(H.REQUIRED_CHECKS) == ("api_reachable", "bot_loop_age", "candle_age", "ledger_write_age",
                                            "ledger_gate", "disk_free", "memory", "container_restarts")

    def test_ml_given_does_not_change_required_and_no_missing_check_for_other_bot(self):
        rep = ev(ml_snap(mlp()))
        assert "ml_package" not in " ".join(H.REQUIRED_CHECKS)
        assert not [r for r in rep.results if r.code == "missing_check"]
        assert [r.name for r in rep.results if r.name.startswith("ml_package")] == ["ml_package:learner"]

    def test_per_bot_results(self):
        rep = ev(mk_snap(ml={"learner": mlp(), "twin": mlp(mode="shadow", state="expired")}))
        expect(ml_res(rep, "learner"), Status.OK, ml_res(rep, "learner").code)
        expect(ml_res(rep, "twin"), Status.WARN, "ml_shadow_down")


# ==========================================================================
# 2-3. off / okunamadi
# ==========================================================================
class TestOffAndUnreadable:
    def test_present_false(self):
        expect(check(mlp(present=False, mode=None, state=None, model_id=None, expires_at=None)),
               Status.SKIPPED, "ml_off")

    def test_mode_off(self):
        expect(check(mlp(mode="off", state="off")), Status.SKIPPED, "ml_off")

    def test_off_evaluates_no_other_row(self):
        p = mlp(mode="off", state="expired", file_state="missing", score_errors=None)
        expect(check(p), Status.SKIPPED, "ml_off")

    def test_skipped_does_not_degrade_overall(self):
        rep = ev(ml_snap(mlp(mode="off", state="off")))
        assert rep.overall is Status.OK and rep.healthy

    def test_status_unreadable(self):
        p = mlp(present=None, mode=None, state=None, model_id=None, expires_at=None, score_errors=None)
        expect(check(p), Status.UNKNOWN, "ml_status_unreadable")

    def test_status_unreadable_overall_unknown(self):
        p = mlp(present=None, mode=None, state=None, model_id=None, expires_at=None)
        rep = ev(ml_snap(p))
        assert rep.overall is Status.UNKNOWN and not rep.healthy and not H.should_send_ok(rep)


# ==========================================================================
# 4-7, 11. sure esikleri
# ==========================================================================
class TestExpiryLadder:
    @pytest.mark.parametrize("mode,delta,status,code", [
        ("active", 7 * DAY + timedelta(seconds=1), Status.OK, None),
        ("active", 7 * DAY, Status.WARN, "ml_expiring_7d"),
        ("active", 3 * DAY + timedelta(seconds=1), Status.WARN, "ml_expiring_7d"),
        ("active", 3 * DAY, Status.WARN, "ml_expiring_3d"),
        ("active", 1 * DAY + timedelta(seconds=1), Status.WARN, "ml_expiring_3d"),
        ("active", 1 * DAY, Status.WARN, "ml_expiring_1d"),
        ("active", timedelta(seconds=1), Status.WARN, "ml_expiring_1d"),
        ("active", timedelta(0), Status.WARN, "ml_expiring_1d"),       # yaris: ok iken expires_at <= now
        ("shadow", 2 * DAY, Status.WARN, "ml_expiring_3d"),
        ("shadow", 7 * DAY + timedelta(seconds=1), Status.OK, None),
        ("shadow", 1 * DAY, Status.WARN, "ml_expiring_1d"),
    ])
    def test_boundaries(self, mode, delta, status, code):
        res = check(mlp(mode=mode, expires_at=NOW + delta))
        assert res.status is status
        if code:
            assert res.code == code
        else:
            assert res.code not in ("ml_expiring_7d", "ml_expiring_3d", "ml_expiring_1d")

    def test_warn_keeps_heartbeat(self):
        rep = ev(ml_snap(mlp(expires_at=NOW + 2 * DAY)))
        assert rep.overall is Status.WARN and H.should_send_ok(rep)

    def test_distinct_codes_per_threshold(self):
        codes = {check(mlp(expires_at=NOW + d)).code for d in (7 * DAY, 3 * DAY, 1 * DAY)}
        assert len(codes) == 3

    def test_no_warmup(self):
        s = ml_snap(mlp(state="expired"), installed_at=NOW - timedelta(seconds=60),
                    containers={f"trader-{b}": H.ContainerProbe("running", 4, NOW - timedelta(seconds=60), False)
                                for b in ("learner", "twin")})
        expect(ml_res(ev(s)), Status.CRIT, "ml_expired")


# ==========================================================================
# 8-10. motor durumlari
# ==========================================================================
class TestEngineStates:
    def test_active_expired_crit(self):
        rep = ev(ml_snap(mlp(state="expired")))
        expect(ml_res(rep), Status.CRIT, "ml_expired")
        assert rep.overall is Status.CRIT
        assert "ml_expired" in H.IMMEDIATE_CODES

    def test_crit_cuts_heartbeat(self):
        rep = ev(ml_snap(mlp(state="expired")))
        assert not H.should_send_ok(rep) and not rep.healthy

    def test_active_no_model_crit_with_error_detail(self):
        err = "PackageError: model suresi dolmus"
        res = check(mlp(state="no_model", error=err))
        expect(res, Status.CRIT, "ml_no_model")
        assert err in res.detail

    @pytest.mark.parametrize("state", ["expired", "no_model"])
    def test_shadow_down_is_warn(self, state):
        rep = ev(ml_snap(mlp(mode="shadow", state=state)))
        expect(ml_res(rep), Status.WARN, "ml_shadow_down")
        assert rep.overall is Status.WARN and H.should_send_ok(rep)


# ==========================================================================
# 12. gecersiz durum
# ==========================================================================
class TestInvalidStatus:
    def test_ok_without_expires_at(self):
        expect(check(mlp(expires_at=None)), Status.UNKNOWN, "ml_status_invalid")

    def test_unknown_mode(self):
        expect(check(mlp(mode="turbo")), Status.UNKNOWN, "ml_status_invalid")

    def test_unknown_state(self):
        expect(check(mlp(state="weird")), Status.UNKNOWN, "ml_status_invalid")


# ==========================================================================
# 13-14. yeniden baslatma gerekli / en agir kazanir
# ==========================================================================
def restart_probe(**kw):
    base = dict(expires_at=NOW + 10 * DAY, model_id=MID_A, file_state="ok", file_model_id=MID_B,
                file_expires_at=NOW + 20 * DAY, file_gate_passed=True, file_user_approved=True,
                file_created_at=NOW - 1 * DAY, file_data_hash="h", file_train_end=NOW - 2 * DAY)
    base.update(kw)
    return mlp(**base)


class TestRestartNeeded:
    def test_active_valid_file(self):
        expect(check(restart_probe()), Status.WARN, "ml_restart_needed")

    def test_active_not_approved_is_ok(self):
        res = check(restart_probe(file_user_approved=False))
        assert res.status is Status.OK

    def test_shadow_not_approved_still_warns(self):
        expect(check(restart_probe(mode="shadow", file_user_approved=False)), Status.WARN, "ml_restart_needed")

    def test_gate_not_passed_is_ok(self):
        assert check(restart_probe(file_gate_passed=False)).status is Status.OK

    def test_expired_file_is_ok(self):
        assert check(restart_probe(file_expires_at=NOW)).status is Status.OK

    def test_same_model_id_no_warn(self):
        assert check(restart_probe(file_model_id=MID_A)).status is Status.OK

    def test_not_configured_skips_file_rows(self):
        res = check(mlp(file_state="not_configured"))
        assert res.status is Status.OK
        assert "paket yolu bilinmiyor" in res.detail

    def test_warn_keeps_heartbeat(self):
        rep = ev(ml_snap(restart_probe()))
        assert H.should_send_ok(rep)


class TestWorstWins:
    def test_expired_beats_restart_needed(self):
        only = check(mlp(state="expired"))
        both = check(restart_probe(state="expired", expires_at=NOW - DAY))
        expect(both, Status.CRIT, "ml_expired")
        assert both.detail != only.detail and len(both.detail) > len(only.detail)

    def test_unknown_beats_warn(self):
        # ok + expires_at None (UNKNOWN) ile dosya gecersiz (WARN): UNKNOWN agirdir (CRIT > UNKNOWN > WARN)
        res = check(mlp(expires_at=None, file_state="missing"))
        assert res.status is Status.UNKNOWN and res.code == "ml_status_invalid"

    def test_crit_beats_unknown_rows_via_shadow_down_not(self):
        res = check(mlp(state="expired", file_state="missing"))
        expect(res, Status.CRIT, "ml_expired")


# ==========================================================================
# 15. dosya gecersiz
# ==========================================================================
class TestFileInvalid:
    def test_missing(self):
        expect(check(mlp(file_state="missing", expires_at=NOW + 10 * DAY)), Status.WARN, "ml_file_invalid")

    def test_unreadable(self):
        expect(check(mlp(file_state="unreadable")), Status.WARN, "ml_file_invalid")

    def test_created_in_future_6min(self):
        expect(check(file_probe(file_created_at=NOW + timedelta(minutes=6))), Status.WARN, "ml_file_invalid")

    def test_created_in_future_4min_not_triggered(self):
        assert check(file_probe(file_created_at=NOW + timedelta(minutes=4))).status is Status.OK

    def test_required_meta_missing(self):
        res = check(file_probe(file_created_at=None))
        expect(res, Status.WARN, "ml_file_invalid")


# ==========================================================================
# 17. mutlak yas (evaluate duzeyi; bkz. belirsizlik notu)
# ==========================================================================
class TestAbsoluteAge:
    """Varsayim: `ml_data_max_age_days` evaluate icinde file_created_at - file_train_end ile sinanir
    (MlProbe'da `stale` alani yok; spec 16.4 madde 5)."""

    def _p(self, gap_days):
        return file_probe(file_created_at=NOW - 1 * DAY, file_train_end=NOW - 1 * DAY - gap_days * DAY)

    def test_default_none_never_triggers(self):
        assert check(self._p(220)).status is Status.OK

    def test_limit_14_with_15_days(self):
        cfg = dataclasses.replace(H.DEFAULT_CFG, ml_data_max_age_days=14)
        expect(check(self._p(15), cfg=cfg), Status.WARN, "ml_stale_data")

    def test_limit_14_with_14_days(self):
        cfg = dataclasses.replace(H.DEFAULT_CFG, ml_data_max_age_days=14)
        assert check(self._p(14), cfg=cfg).status is Status.OK


# ==========================================================================
# 18. puanlama hatalari (evaluate duzeyi: yalniz None; onceki-tur karsilastirmasi runner testinde)
# ==========================================================================
class TestScoreErrorsEval:
    def test_none_does_not_trigger_and_detail_mentions(self):
        res = check(mlp(score_errors=None))
        assert res.status is Status.OK and res.code != "ml_score_errors"
        assert "sayaç okunamadı" in res.detail


# ==========================================================================
# 20. ithalat
# ==========================================================================
class TestImports:
    def test_health_import_is_light(self):
        code = ("import sys; sys.path.insert(0, %r); import trader_core.health; "
                "bad = [m for m in ('numpy', 'trader_core.ml_package', 'trader_engine') if m in sys.modules]; "
                "assert not bad, bad" % str(SRC))
        r = subprocess.run([sys.executable, "-I", "-c", code], capture_output=True, text=True)
        assert r.returncode == 0, r.stderr


# ==========================================================================
# 21-23. uyari metinleri, bastirma, hemen
# ==========================================================================
def at_min(n, base=NOW):
    return base + timedelta(minutes=n)


def run_turns(steps, cfg=None):
    """steps: [(now, rapor)] -> ([(now, alerts)], son durum)."""
    cfg = cfg or H.DEFAULT_CFG
    state: dict = {}
    out = []
    for now, rep in steps:
        alerts, state = H.plan_alerts(rep, state, now, cfg)
        out.append((now, list(alerts)))
    return out, state


def ml_report(probe, now=NOW, bot="learner"):
    return ev(mk_snap(now=now, ml={bot: probe}))


def manual_report(code, status=Status.WARN, name="ml_package:learner", now=NOW):
    r = H.CheckResult(name, status, code, "x")
    return H.HealthReport(now, (r,), status, status in (Status.OK, Status.WARN))


def ok_report(now=NOW):
    return ev(mk_snap(now=now))


ALERT_TABLE = [
    ("ml_expired", Status.CRIT, "Modelin süresi doldu — yeni işlemler durdu",
     "Model yenilendi, yeni işlemler yeniden açık",
     "Model 21 günden eski olduğu için bot yeni işlem açmıyor; açık pozisyonlar korunuyor. "
     "Model yenilenip motor yeniden başlatılmalı."),
    ("ml_no_model", Status.CRIT, "Model yüklenemedi — yeni işlemler durdu",
     "Model yüklendi, yeni işlemler yeniden açık",
     "Model dosyası yok, geçersiz ya da süresi dolmuş; bot yeni işlem açmıyor, açık pozisyonlar korunuyor."),
    ("ml_shadow_down", Status.WARN, "Gölgedeki model çalışmıyor", "Gölgedeki model yeniden çalışıyor",
     "İşlemler etkilenmiyor; yalnız modelin izleme kaydı duruyor."),
    ("ml_expiring_7d", Status.WARN, "Modelin süresi 7 gün içinde doluyor", "Model yenilendi",
     "Yenilenmezse süre dolduğunda yeni işlemler durur."),
    ("ml_expiring_3d", Status.WARN, "Modelin süresi 3 gün içinde doluyor", "Model yenilendi",
     "Yenilenmezse süre dolduğunda yeni işlemler durur."),
    ("ml_expiring_1d", Status.WARN, "Modelin süresi yarın doluyor!", "Model yenilendi",
     "Bugün yenilenmezse yeni işlemler durur."),
    ("ml_restart_needed", Status.WARN, "Yeni model hazır ama devrede değil", "Yeni model devrede",
     "Motor yeniden başlatılana kadar eski model kullanılır."),
    ("ml_stale_data", Status.WARN, "Yeni model eski veriyle üretilmiş", "Model güncel veriyle yenilendi",
     "Model dosyası yeni ama içindeki veri ilerlememiş; veri toplama ve eğitim hattı kontrol edilmeli."),
    ("ml_file_invalid", Status.WARN, "Model dosyası okunamıyor", "Model dosyası yeniden okunuyor",
     "Sıradaki yeniden başlatmada model yüklenemeyebilir."),
    ("ml_score_errors", Status.WARN, "Model bazı fırsatları puanlayamıyor", "Model yeniden puanlıyor",
     "Puanlanamayan fırsatlar alınmaz; işlem sayısı düşebilir."),
]
GENERIC = ("Yapay zekâ modeli sorunlu", "Yapay zekâ modeli yeniden normal", "Modelin durumu için günlük rapora bak.")


def alert_text(a):
    return f"{a.title}\n{a.body}"


def first_alert(code, status):
    """Iki tur (WARN icin onay) calistirir; ilk gonderilen uyariyi dondurur."""
    steps = [(at_min(i * 5), manual_report(code, status, now=at_min(i * 5))) for i in range(2)]
    out, _ = run_turns(steps)
    sent = [a for _, al in out for a in al]
    assert sent, f"{code}: uyari yok"
    return sent[0], steps


class TestAlertTexts:
    @pytest.mark.parametrize("code,status,sorun,duzeldi,anlam", ALERT_TABLE, ids=[r[0] for r in ALERT_TABLE])
    def test_problem_and_recovery_text(self, code, status, sorun, duzeldi, anlam):
        a, steps = first_alert(code, status)
        txt = alert_text(a)
        assert sorun in a.title and len(a.title) <= 80
        assert anlam in a.body
        assert code not in txt and "ml_package" not in txt
        # duzeldi: fingerprint kaybolur
        out, _ = run_turns(steps + [(at_min(10), ok_report(at_min(10)))])
        last = out[-1][1]
        rec = [x for x in last if x.level is Status.OK]
        assert rec and duzeldi in rec[0].title and len(rec[0].title) <= 80

    def test_twin_suffix(self):
        steps = [(at_min(i * 5), manual_report("ml_expired", Status.CRIT, "ml_package:twin", at_min(i * 5)))
                 for i in range(2)]
        out, _ = run_turns(steps)
        sent = [a for _, al in out for a in al]
        assert sent and "(ikiz bot)" in sent[0].title

    def test_generic_text_for_unlisted_code(self):
        a, _ = first_alert("ml_something_new", Status.WARN)
        assert GENERIC[0] in a.title and GENERIC[2] in a.body
        assert "ml_something_new" not in alert_text(a)

    def test_end_to_end_no_leak_of_model_id_or_path(self):
        err = "PackageError: /srv/models/learner_pkg.json bulunamadi"
        steps = [(NOW, ml_report(mlp(state="no_model", error=err, model_id=MID_A)))]
        out, _ = run_turns(steps)
        sent = [a for _, al in out for a in al]
        assert sent
        txt = alert_text(sent[0])
        for bad in ("ml_no_model", "ml_package", MID_A, "/srv/models", "learner_pkg.json", "PackageError"):
            assert bad not in txt
        assert "Model yüklenemedi — yeni işlemler durdu" in sent[0].title

    def test_end_to_end_expired_then_fixed(self):
        s1 = (NOW, ml_report(mlp(state="expired", model_id=MID_A)))
        s2 = (at_min(5), ml_report(mlp(), now=at_min(5)))
        out, _ = run_turns([s1, s2])
        first = out[0][1]
        assert first and "Modelin süresi doldu — yeni işlemler durdu" in first[0].title
        assert "ml_expired" not in alert_text(first[0]) and MID_A not in alert_text(first[0])
        rec = [a for a in out[1][1] if a.level is Status.OK]
        assert rec and "Model yenilendi, yeni işlemler yeniden açık" in rec[0].title


class TestImmediate:
    def test_in_immediate_codes(self):
        assert {"ml_expired", "ml_no_model"} <= set(H.IMMEDIATE_CODES)

    @pytest.mark.parametrize("probe", [mlp(state="expired"), mlp(state="no_model", error="x")])
    def test_first_turn_alerts(self, probe):
        out, _ = run_turns([(NOW, ml_report(probe))])
        assert out[0][1], "ilk turda uyari beklenir"

    def test_warn_not_immediate(self):
        out, _ = run_turns([(NOW, ml_report(mlp(expires_at=NOW + 2 * DAY)))])
        assert not out[0][1]


class TestAlertSuppression:
    def test_ladder_new_alert_per_threshold(self):
        exp7 = NOW + 7 * DAY
        steps = []
        # 7 gun bandi: 0..60 dk her 5 dk
        for i in range(0, 13):
            n = at_min(i * 5)
            steps.append((n, ml_report(mlp(expires_at=exp7), now=n)))
        # 3 gun bandi: +4 gun
        n3 = NOW + 4 * DAY
        for i in range(0, 4):
            n = n3 + timedelta(minutes=i * 5)
            steps.append((n, ml_report(mlp(expires_at=exp7), now=n)))
        # 1 gun bandi: +6 gun
        n1 = NOW + 6 * DAY
        for i in range(0, 4):
            n = n1 + timedelta(minutes=i * 5)
            steps.append((n, ml_report(mlp(expires_at=exp7), now=n)))
        out, _ = run_turns(steps)
        warn_alerts = [(n, a) for n, al in out for a in al if a.level is Status.WARN]
        by_code = {}
        for n, a in warn_alerts:
            by_code.setdefault(a.code, []).append(n)
        assert set(by_code) == {"ml_expiring_7d", "ml_expiring_3d", "ml_expiring_1d"}, by_code
        assert len(by_code["ml_expiring_7d"]) == 1           # 12 saatlik tekrar penceresinde bastirilir
        assert len(by_code["ml_expiring_3d"]) == 1
        assert len(by_code["ml_expiring_1d"]) == 1
        assert by_code["ml_expiring_7d"][0] < by_code["ml_expiring_3d"][0] < by_code["ml_expiring_1d"][0]


# ==========================================================================
# Runner duzeyi (scripts/health_run.py): 16, 18, 19
# ==========================================================================
def _load_runner():
    sys.path.insert(0, str(SCRIPTS))
    try:
        spec = importlib.util.spec_from_file_location("health_run_mlfresh", SCRIPTS / "health_run.py")
        m = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(m)
        return m
    finally:
        sys.path.remove(str(SCRIPTS))


R = _load_runner()


class _Sender:
    def ok(self, rep):
        return True

    def fail(self, rep):
        return True


def pkg_doc(version="r02", *, created, train_end, data_hash="dh0", model_hash="0123456789abcdef", expires_at=None,
            gate=True, approved=True, snapshot=None, naive=False, drop=()):
    def fmt(dt):
        s = dt.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%S")
        return s if naive else s + "Z"
    meta = {"pkg_version": 1, "version": version, "kind": "gbdt", "created_at": fmt(created),
            "expires_at": fmt(expires_at if expires_at else created + timedelta(days=21)), "expiry_days": 21,
            "features": ["f1"], "feature_list_hash": "x" * 64, "feature_ranges": {},
            "train_window": {"start": fmt(train_end - timedelta(days=100)), "end": fmt(train_end)},
            "n_train": 1000, "data_hash": data_hash, "code_hash": "c" * 64, "model_hash": model_hash,
            "gate_passed": gate, "user_approved": approved}
    if snapshot is not None:
        meta["data_snapshot_at"] = fmt(snapshot)
    for k in drop:
        meta.pop(k, None)
    return {"meta": meta, "threshold": 0.5}


def model_id_of(pkg):
    return f"{pkg['meta']['version']}@{pkg['meta']['model_hash'][:12]}"


class Env:
    def __init__(self, tmp: Path):
        self.tmp = tmp
        (tmp / "bk").mkdir(exist_ok=True)
        (tmp / "var" / "learner").mkdir(parents=True, exist_ok=True)
        self.pkg_path = tmp / "model_pkg.json"
        self.state_path = tmp / "state.json"
        self.env = {"ENGINE_VAR_DIR": str(tmp / "var"), "BACKUP_DIR": str(tmp / "bk"), "HEARTBEAT_URL": "https://h/x",
                    "HEALTH_BOTS": "learner", "ML_MODEL_PATH_LEARNER": str(self.pkg_path),
                    "STATE_DIR": str(tmp)}

    def write_status(self, now, *, ml="default", counters=None, mode="active", state="ok", model_id=MID_A,
                     expires_at=None, v2_errors=0):
        if ml == "default":
            ml = {"mode": mode, "state": state, "model_id": model_id, "threshold": 0.5,
                  "expires_at": z(expires_at or now + 30 * DAY), "error": None, "features": 1, "v2_error": None,
                  "v2_errors": v2_errors, "entries_blocked": False}
        doc = {"schema": "engine-status/1", "bot": "learner", "mode": "paper", "pid": 1,
               "started_at": z(now - timedelta(hours=5)), "loop_at": z(now - timedelta(seconds=10)),
               "last_candle_open": z(now.replace(minute=0, second=0)), "trigger_tf": "1h", "param_version_id": 1,
               "entries_open": True, "gate": {"ok": True, "code": "ok"}, "kill": False, "dry_run": True,
               "open_positions": [], "open_trade_ids": [],
               "counters": dict({"ledger_errors": 0, "ml_score_errors": 0}, **(counters or {})), "ml": ml}
        (self.tmp / "var" / "learner" / "status.json").write_text(json.dumps(doc), encoding="utf-8")

    def write_pkg(self, doc):
        self.pkg_path.write_text(json.dumps(doc), encoding="utf-8")

    def run(self, now, capsys, **status_kw):
        self.write_status(now, **status_kw)
        capsys.readouterr()
        R.run_once(dict(self.env), now=now, state_path=self.state_path, notifier=H.NullNotifier(),
                   sender=_Sender())
        out = capsys.readouterr().out
        line = [ln for ln in out.splitlines() if ln.startswith("{")][-1]
        rep = json.loads(line)
        state = json.loads(self.state_path.read_text())
        return {f["name"]: f for f in rep["failing"]}, state

    def ml_fail(self, failing):
        f = failing.get("ml_package:learner")
        return (f["status"], f["code"]) if f else None


def parse_t(x):
    if isinstance(x, (int, float)):
        return datetime.fromtimestamp(x, UTC)
    d = datetime.fromisoformat(str(x).replace("Z", "+00:00"))
    return d.replace(tzinfo=UTC) if d.tzinfo is None else d.astimezone(UTC)


# --------------------------------------------------------------------------- 16
def _stale_sequence():
    c0 = NOW - 8 * DAY
    e0 = NOW - 9 * DAY
    p0 = pkg_doc(created=c0, train_end=e0, data_hash="H0", model_hash="a" * 16)
    p1 = pkg_doc(created=c0 + 7 * DAY, train_end=e0, data_hash="H0", model_hash="b" * 16)         # (b) bayat
    p2 = pkg_doc(created=c0 + 14 * DAY, train_end=e0 + 14 * DAY, data_hash="H2", model_hash="c" * 16)   # (c) ileri
    p3 = pkg_doc(created=c0 + 15 * DAY, train_end=e0 + 14 * DAY, data_hash="H3", model_hash="d" * 16)   # (d)
    p4 = pkg_doc(created=c0 + 1 * DAY, train_end=e0 + 20 * DAY, data_hash="H4", model_hash="e" * 16)   # (e) daha eski
    # (kural 4: created <= onceki created => stale)
    return [(p0, False), (p1, True), (p1, True), (p2, False), (p3, False), (p4, True)]


def _not_before_created(pkg, now):
    # lider duzeltmesi: saat paketin created_at'inden geride kalamaz (spec 16.3 satir 12: created > now+5 dk = gecersiz)
    return max(now, parse_t(pkg["meta"]["created_at"]))


class TestStaleDataRunner:
    """Varsayim: durum dosyasinda ml_seen[bot] = {model_id, created_at, data_hash, train_end, stale} (spec 16.2/16.4);
    sonuc runner'in stdout satirindaki failing listesinden okunur (status/code)."""

    @pytest.mark.parametrize("k", range(1, 7))
    def test_sequence(self, tmp_path, capsys, k):
        e = Env(tmp_path)
        seq = _stale_sequence()
        for i in range(k):
            pkg, stale = seq[i]
            e.write_pkg(pkg)
            n = _not_before_created(pkg, NOW) + timedelta(minutes=5 * i)
            failing, state = e.run(n, capsys, model_id=model_id_of(pkg))
            got = e.ml_fail(failing)
            if stale:
                assert got == ("WARN", "ml_stale_data"), (i, got)
            else:
                assert got is None, (i, got)
            seen = state["ml_seen"]["learner"]
            assert bool(seen["stale"]) is stale, (i, seen)
            assert seen["model_id"] == model_id_of(pkg)

    def test_baseline_written_on_first_turn(self, tmp_path, capsys):
        e = Env(tmp_path)
        pkg = _stale_sequence()[0][0]
        e.write_pkg(pkg)
        failing, state = e.run(NOW, capsys, model_id=model_id_of(pkg))
        seen = state["ml_seen"]["learner"]
        assert seen["data_hash"] == "H0" and seen["stale"] in (False, 0)
        assert parse_t(seen["train_end"]) == parse_t(pkg["meta"]["train_window"]["end"])
        assert parse_t(seen["created_at"]) == parse_t(pkg["meta"]["created_at"])

    def test_mtime_is_not_used(self, tmp_path, capsys):
        e = Env(tmp_path)
        p0, p1 = _stale_sequence()[0][0], _stale_sequence()[1][0]
        e.write_pkg(p0)
        e.run(NOW, capsys, model_id=model_id_of(p0))
        e.write_pkg(p1)
        os.utime(e.pkg_path, (0, 0))                      # mtime anlamsiz; yalniz meta sayilir
        failing, _ = e.run(at_min(5), capsys, model_id=model_id_of(p1))
        assert e.ml_fail(failing) == ("WARN", "ml_stale_data")

    def test_stale_closes_when_data_advances(self, tmp_path, capsys):
        e = Env(tmp_path)
        seq = _stale_sequence()
        for i, idx in enumerate((0, 1, 3)):
            e.write_pkg(seq[idx][0])
            failing, _ = e.run(_not_before_created(seq[idx][0], NOW) + timedelta(minutes=5 * i), capsys,
                               model_id=model_id_of(seq[idx][0]))
        assert e.ml_fail(failing) is None


# --------------------------------------------------------------------------- 18
class _ScoreEnv(Env):
    """Lider duzeltmesi: gecerli paket dosyasi yazilir ve durumdaki model_id ona esitlenir; aksi halde dosya yok
    (spec 16.3 satir 12) ya da yeniden baslatma gerekli bulgusu skor hatasi kontrolunu golgeler."""

    def __init__(self, tmp):
        super().__init__(tmp)
        self._pkg = pkg_doc(created=NOW - DAY, train_end=NOW - 2 * DAY)
        self.write_pkg(self._pkg)

    def run(self, now, capsys, **kw):
        kw.setdefault("model_id", model_id_of(self._pkg))
        return super().run(now, capsys, **kw)


class TestScoreErrorsRunner:
    """Varsayim: score_errors = counters.ml_score_errors + ml.v2_errors (tamsayi); onceki tur
    state.json `ml_score_errors[bot]` icinde tutulur (spec 16.2)."""

    def test_increase_warns_first_baseline_silent_drop_resets(self, tmp_path, capsys):
        e = _ScoreEnv(tmp_path)
        f1, s1 = e.run(NOW, capsys, counters={"ml_score_errors": 3})
        assert e.ml_fail(f1) is None                                  # ilk tur: taban, alarm yok
        assert s1["ml_score_errors"]["learner"] == 3
        f2, s2 = e.run(at_min(5), capsys, counters={"ml_score_errors": 3}, v2_errors=2)     # 3 -> 5 (toplam)
        assert e.ml_fail(f2) == ("WARN", "ml_score_errors")
        f3, s3 = e.run(at_min(10), capsys, counters={"ml_score_errors": 0}, v2_errors=0)    # 5 -> 0
        assert e.ml_fail(f3) is None
        assert s3["ml_score_errors"]["learner"] == 0
        f4, _ = e.run(at_min(15), capsys, counters={"ml_score_errors": 0})
        assert e.ml_fail(f4) is None

    def test_unchanged_does_not_warn(self, tmp_path, capsys):
        e = _ScoreEnv(tmp_path)
        e.run(NOW, capsys, counters={"ml_score_errors": 4})
        f, _ = e.run(at_min(5), capsys, counters={"ml_score_errors": 4})
        assert e.ml_fail(f) is None

    def test_shadow_mode_also_warns(self, tmp_path, capsys):
        e = _ScoreEnv(tmp_path)
        e.run(NOW, capsys, mode="shadow", counters={"ml_score_errors": 1})
        f, _ = e.run(at_min(5), capsys, mode="shadow", counters={"ml_score_errors": 2})
        assert e.ml_fail(f) == ("WARN", "ml_score_errors")

    def test_first_turn_with_five_no_alarm(self, tmp_path, capsys):
        e = _ScoreEnv(tmp_path)
        f, _ = e.run(NOW, capsys, counters={"ml_score_errors": 5})
        assert e.ml_fail(f) is None


# --------------------------------------------------------------------------- 19
class TestPackageMetaRunner:
    def _restart_case(self, e, capsys, pkg, now=NOW):
        """Motor MID_A kullaniyor, diskte baska paket: gecerliyse ml_restart_needed beklenir."""
        e.write_pkg(pkg)
        return e.run(now, capsys, model_id=MID_A, expires_at=now + 10 * DAY)

    def test_valid_file_restart_needed(self, tmp_path, capsys):
        e = Env(tmp_path)
        pkg = pkg_doc(created=NOW - 1 * DAY, train_end=NOW - 3 * DAY, model_hash="b" * 16)
        failing, _ = self._restart_case(e, capsys, pkg)
        assert e.ml_fail(failing) == ("WARN", "ml_restart_needed")

    def test_naive_timestamps_are_utc(self, tmp_path, capsys):
        e = Env(tmp_path)
        pkg = pkg_doc(created=NOW - 1 * DAY, train_end=NOW - 3 * DAY, model_hash="b" * 16, naive=True)
        failing, state = self._restart_case(e, capsys, pkg)
        assert e.ml_fail(failing) == ("WARN", "ml_restart_needed")
        seen = state["ml_seen"]["learner"]
        assert parse_t(seen["created_at"]) == NOW - 1 * DAY

    def test_naive_created_six_minutes_ahead_is_invalid_as_utc(self, tmp_path, capsys):
        e = Env(tmp_path)
        pkg = pkg_doc(created=NOW + timedelta(minutes=6), train_end=NOW - 3 * DAY, model_hash="b" * 16, naive=True)
        failing, _ = self._restart_case(e, capsys, pkg)
        assert e.ml_fail(failing) == ("WARN", "ml_file_invalid")

    def test_expires_capped_at_created_plus_21_days(self, tmp_path, capsys):
        e = Env(tmp_path)
        created = NOW - 30 * DAY
        pkg = pkg_doc(created=created, train_end=created - 2 * DAY, model_hash="b" * 16,
                      expires_at=created + 40 * DAY)                  # meta sinir: now+10g; ama created+21g gecmis
        failing, _ = self._restart_case(e, capsys, pkg)
        assert e.ml_fail(failing) != ("WARN", "ml_restart_needed")    # dosya suresi dolmus sayilir

    def test_data_snapshot_at_preferred_over_train_window_end(self, tmp_path, capsys):
        e = Env(tmp_path)
        te, snap = NOW - 30 * DAY, NOW - 4 * DAY
        pkg = pkg_doc(created=NOW - 1 * DAY, train_end=te, snapshot=snap, model_hash="a" * 16)
        e.write_pkg(pkg)
        _, state = e.run(NOW, capsys, model_id=model_id_of(pkg))
        assert parse_t(state["ml_seen"]["learner"]["train_end"]) == snap

    def test_train_window_end_used_without_snapshot(self, tmp_path, capsys):
        e = Env(tmp_path)
        te = NOW - 30 * DAY
        pkg = pkg_doc(created=NOW - 1 * DAY, train_end=te, model_hash="a" * 16)
        e.write_pkg(pkg)
        _, state = e.run(NOW, capsys, model_id=model_id_of(pkg))
        assert parse_t(state["ml_seen"]["learner"]["train_end"]) == te

    def test_over_32mb_is_unreadable(self, tmp_path, capsys):
        e = Env(tmp_path)
        pkg = pkg_doc(created=NOW - 1 * DAY, train_end=NOW - 3 * DAY, model_hash="b" * 16)
        e.pkg_path.write_text(json.dumps(pkg) + " " * (32 * 1024 * 1024 + 10), encoding="utf-8")
        failing, _ = e.run(NOW, capsys, model_id=MID_A, expires_at=NOW + 10 * DAY)
        assert e.ml_fail(failing) == ("WARN", "ml_file_invalid")

    def test_file_not_modified(self, tmp_path, capsys):
        import hashlib
        e = Env(tmp_path)
        pkg = pkg_doc(created=NOW - 1 * DAY, train_end=NOW - 3 * DAY, model_hash="b" * 16)
        e.write_pkg(pkg)
        before = (hashlib.sha256(e.pkg_path.read_bytes()).hexdigest(), e.pkg_path.stat().st_mtime_ns)
        e.run(NOW, capsys, model_id=MID_A, expires_at=NOW + 10 * DAY)
        after = (hashlib.sha256(e.pkg_path.read_bytes()).hexdigest(), e.pkg_path.stat().st_mtime_ns)
        assert before == after

    def test_missing_file_invalid(self, tmp_path, capsys):
        e = Env(tmp_path)
        failing, _ = e.run(NOW, capsys, model_id=MID_A)
        assert e.ml_fail(failing) == ("WARN", "ml_file_invalid")

    def test_corrupt_json_invalid(self, tmp_path, capsys):
        e = Env(tmp_path)
        e.pkg_path.write_text("{bozuk", encoding="utf-8")
        failing, _ = e.run(NOW, capsys, model_id=MID_A)
        assert e.ml_fail(failing) == ("WARN", "ml_file_invalid")

    @pytest.mark.parametrize("field", ["created_at", "expires_at", "model_hash", "gate_passed"])
    def test_required_meta_missing_invalid(self, tmp_path, capsys, field):
        e = Env(tmp_path)
        pkg = pkg_doc(created=NOW - 1 * DAY, train_end=NOW - 3 * DAY, model_hash="b" * 16, drop=(field,))
        failing, _ = self._restart_case(e, capsys, pkg)
        assert e.ml_fail(failing) == ("WARN", "ml_file_invalid")

    def test_not_configured_no_result(self, tmp_path, capsys):
        e = Env(tmp_path)
        e.env.pop("ML_MODEL_PATH_LEARNER")
        failing, _ = e.run(NOW, capsys)
        assert e.ml_fail(failing) is None

    def test_engine_config_dir_merge(self, tmp_path, capsys):
        e = Env(tmp_path)
        e.env.pop("ML_MODEL_PATH_LEARNER")
        cfgd = tmp_path / "cfg"
        cfgd.mkdir()
        good = pkg_doc(created=NOW - 1 * DAY, train_end=NOW - 3 * DAY, model_hash="b" * 16)
        e.write_pkg(good)
        (cfgd / "engine.base.json").write_text(json.dumps({"ml_model_path": str(tmp_path / "yok.json")}))
        (cfgd / "engine.learner.json").write_text(json.dumps({"ml_model_path": str(e.pkg_path)}))
        e.env["ENGINE_CONFIG_DIR"] = str(cfgd)
        failing, _ = e.run(NOW, capsys, model_id=MID_A, expires_at=NOW + 10 * DAY)
        assert e.ml_fail(failing) == ("WARN", "ml_restart_needed")    # bot dosyasi tabani ezer

    def test_engine_config_base_only(self, tmp_path, capsys):
        e = Env(tmp_path)
        e.env.pop("ML_MODEL_PATH_LEARNER")
        cfgd = tmp_path / "cfg"
        cfgd.mkdir()
        (cfgd / "engine.base.json").write_text(json.dumps({"ml_model_path": str(tmp_path / "yok.json")}))
        e.env["ENGINE_CONFIG_DIR"] = str(cfgd)
        failing, _ = e.run(NOW, capsys, model_id=MID_A)
        assert e.ml_fail(failing) == ("WARN", "ml_file_invalid")      # yol belli ama dosya yok

    def test_env_key_beats_engine_config(self, tmp_path, capsys):
        e = Env(tmp_path)
        cfgd = tmp_path / "cfg"
        cfgd.mkdir()
        good = pkg_doc(created=NOW - 1 * DAY, train_end=NOW - 3 * DAY, model_hash="b" * 16)
        e.write_pkg(good)
        (cfgd / "engine.base.json").write_text(json.dumps({"ml_model_path": str(tmp_path / "yok.json")}))
        e.env["ENGINE_CONFIG_DIR"] = str(cfgd)                        # ML_MODEL_PATH_LEARNER gecerli dosyaya isaret eder
        failing, _ = e.run(NOW, capsys, model_id=MID_A, expires_at=NOW + 10 * DAY)
        assert e.ml_fail(failing) == ("WARN", "ml_restart_needed")

    def test_status_without_ml_block_is_off(self, tmp_path, capsys):
        e = Env(tmp_path)
        failing, _ = e.run(NOW, capsys, ml=None)
        assert e.ml_fail(failing) is None

    def test_runner_status_unreadable_gives_unknown(self, tmp_path, capsys):
        e = Env(tmp_path)
        e.write_status(NOW)
        (tmp_path / "var" / "learner" / "status.json").write_text("{bozuk")
        capsys.readouterr()
        R.run_once(dict(e.env), now=NOW, state_path=e.state_path, notifier=H.NullNotifier(), sender=_Sender())
        line = [ln for ln in capsys.readouterr().out.splitlines() if ln.startswith("{")][-1]
        f = {x["name"]: x for x in json.loads(line)["failing"]}
        assert ("ml_package:learner" in f) and f["ml_package:learner"]["code"] == "ml_status_unreadable"


# ==========================================================================
# 24-30. gunluk rapor
# ==========================================================================
tg = pytest.importorskip("trader_core.telegram")
TNOW = NOW
TDAY = "2026-12-10"


def mk_tg_cfg(tmp, health_state=""):
    return tg.TelegramConfig("1:tok", 5, str(tmp / "tg"), "", str(tmp / "status.json"),
                             health_state=health_state)


def ml_block(mode="active", state="ok", remaining=12 * DAY + timedelta(hours=5), model_id=MID_A, **kw):
    b = {"mode": mode, "state": state, "model_id": model_id, "threshold": 0.5,
         "expires_at": z(TNOW + remaining) if remaining is not None else None, "error": None, "features": 33,
         "v2_error": None, "v2_errors": 0, "entries_blocked": mode == "active" and state in ("expired", "no_model")}
    b.update(kw)
    return b


def write_tg_status(tmp, ml, *, entries_open=True, gate_code="ok", omit_ml=False):
    d = {"loop_at": z(TNOW - timedelta(seconds=10)), "mode": "paper", "entries_open": entries_open,
         "gate": {"ok": entries_open, "code": gate_code}, "equity": 1000.0, "day_start_equity": 1000.0,
         "open_positions": []}
    if not omit_ml:
        d["ml"] = ml
    (tmp / "status.json").write_text(json.dumps(d), encoding="utf-8")


def write_health_state(tmp, codes=(), stale=False, last_overall="WARN"):
    fps = {f"ml_package:learner|{c}": {"first_seen": z(TNOW), "consecutive": 3, "last_alert_at": z(TNOW),
                                       "alerted": True, "level": "WARN"} for c in codes}
    st = {"schema": 1, "restart_counts": {}, "fingerprints": fps, "last_overall": last_overall,
          "last_run_at": z(TNOW)}
    if stale:
        st["ml_seen"] = {"learner": {"model_id": MID_A, "created_at": z(TNOW), "data_hash": "h",
                                     "train_end": z(TNOW), "stale": True}}
    p = tmp / "health_state.json"
    p.write_text(json.dumps(st), encoding="utf-8")
    return str(p)


def report_for(tmp, ml, *, health_state="", extra_sections=None, **status_kw):
    write_tg_status(tmp, ml, **status_kw)
    cfg = mk_tg_cfg(tmp, health_state)
    secs = tg.default_sections(cfg, TNOW, TDAY)
    assert "Model" in secs, f"default_sections'ta 'Model' yok: {list(secs)}"
    sections = {"Model": secs["Model"]}
    if extra_sections:
        sections.update(extra_sections)
    return tg.build_report(cfg, TNOW, TDAY, sections)


def lines_of(txt):
    return txt.splitlines()


class TestDailyReport:
    def test_24_null_block(self, tmp_path):
        out = report_for(tmp_path, None)
        assert "🤖 Model filtresi kapalı (bot filtresiz çalışıyor)" in lines_of(out)

    def test_24_missing_key(self, tmp_path):
        out = report_for(tmp_path, None, omit_ml=True)
        assert "🤖 Model filtresi kapalı (bot filtresiz çalışıyor)" in lines_of(out)

    def test_24_mode_off(self, tmp_path):
        out = report_for(tmp_path, ml_block(mode="off", state="off", remaining=None))
        assert "🤖 Model filtresi kapalı (bot filtresiz çalışıyor)" in lines_of(out)

    def test_25_shadow_ok_12_days(self, tmp_path):
        out = report_for(tmp_path, ml_block("shadow", "ok", 12 * DAY + timedelta(hours=5)))
        assert "🤖 Model gölgede izliyor, kararları etkilemiyor · süresi 12 gün sonra doluyor" in lines_of(out)

    def test_active_ok_12_days(self, tmp_path):
        out = report_for(tmp_path, ml_block("active", "ok", 12 * DAY + timedelta(hours=5)))
        assert "🤖 Model filtresi açık · süresi 12 gün sonra doluyor" in lines_of(out)

    def test_boundary_just_over_7_days_is_normal_line(self, tmp_path):
        out = report_for(tmp_path, ml_block("active", "ok", 7 * DAY + timedelta(seconds=1)))
        assert "🤖 Model filtresi açık · süresi 7 gün sonra doluyor" in lines_of(out)

    def test_boundary_exactly_7_days_is_warning_line(self, tmp_path):
        out = report_for(tmp_path, ml_block("active", "ok", 7 * DAY))
        assert ("⚠️ Model filtresi açık ama süresi 7 gün sonra doluyor; yenilenmezse yeni işlemler durur"
                in lines_of(out))

    @pytest.mark.parametrize("remaining,txt", [
        (5 * DAY + timedelta(hours=23), "5 gün"),
        (timedelta(hours=20), "20 saat"),
        (timedelta(minutes=20), "1 saat"),
        (1 * DAY, "1 gün"),
        (1 * DAY - timedelta(seconds=1), "23 saat"),
    ])
    def test_26_active_expiring(self, tmp_path, remaining, txt):
        out = report_for(tmp_path, ml_block("active", "ok", remaining))
        exp = f"⚠️ Model filtresi açık ama süresi {txt} sonra doluyor; yenilenmezse yeni işlemler durur"
        assert exp in lines_of(out)

    def test_shadow_expiring_line(self, tmp_path):
        out = report_for(tmp_path, ml_block("shadow", "ok", 5 * DAY + timedelta(hours=3)))
        assert "⚠️ Gölgedeki modelin süresi 5 gün sonra doluyor (işlemler etkilenmez)" in lines_of(out)

    def test_27_active_expired(self, tmp_path):
        out = report_for(tmp_path, ml_block("active", "expired", None), entries_open=False, gate_code="ml_expired")
        assert "🚨 Modelin süresi doldu: yeni işlem açılmıyor, açık pozisyonlar korunuyor" in lines_of(out)
        assert "modelin süresi doldu" in out
        assert "yapay zekâ filtresi hazır değil" not in out

    def test_active_no_model(self, tmp_path):
        out = report_for(tmp_path, ml_block("active", "no_model", None, error="PackageError: x"),
                         entries_open=False, gate_code="ml_no_model")
        assert "🚨 Model yüklenemedi: yeni işlem açılmıyor, açık pozisyonlar korunuyor" in lines_of(out)
        assert "model yüklenemedi" in out and "PackageError" not in out

    @pytest.mark.parametrize("state", ["no_model", "expired"])
    def test_28_shadow_down(self, tmp_path, state):
        out = report_for(tmp_path, ml_block("shadow", state, None))
        assert "⚠️ Gölgedeki model çalışmıyor (işlemler etkilenmiyor)" in lines_of(out)
        assert "🛑 Yeni işlemler kapalı" not in out

    def test_29_restart_needed_suffix(self, tmp_path):
        hs = write_health_state(tmp_path, ["ml_restart_needed"])
        out = report_for(tmp_path, ml_block("active", "ok", 12 * DAY + timedelta(hours=5)), health_state=hs)
        base = "🤖 Model filtresi açık · süresi 12 gün sonra doluyor"
        assert base + " · yeni model hazır, motorun yeniden başlatılması gerekiyor" in lines_of(out)

    def test_stale_suffix_from_ml_seen(self, tmp_path):
        hs = write_health_state(tmp_path, [], stale=True)
        out = report_for(tmp_path, ml_block("active", "ok", 12 * DAY + timedelta(hours=5)), health_state=hs)
        base = "🤖 Model filtresi açık · süresi 12 gün sonra doluyor"
        assert base + " · yeni model eski veriyle üretilmiş görünüyor" in lines_of(out)

    def test_score_errors_suffix(self, tmp_path):
        hs = write_health_state(tmp_path, ["ml_score_errors"])
        out = report_for(tmp_path, ml_block("shadow", "ok", 12 * DAY + timedelta(hours=5)), health_state=hs)
        base = "🤖 Model gölgede izliyor, kararları etkilemiyor · süresi 12 gün sonra doluyor"
        assert base + " · bazı fırsatlar puanlanamadı" in lines_of(out)

    def test_no_suffix_without_health_state(self, tmp_path):
        out = report_for(tmp_path, ml_block("active", "ok", 12 * DAY + timedelta(hours=5)))
        assert "yeni model hazır" not in out and "eski veriyle" not in out

    @pytest.mark.parametrize("ml,kw", [
        (ml_block("shadow", "ok"), {}),
        (ml_block("active", "ok"), {}),
        (ml_block("active", "ok", 3 * DAY), {}),
        (ml_block("active", "expired", None), dict(entries_open=False, gate_code="ml_expired")),
        (ml_block("active", "no_model", None, error="PackageError: x"),
         dict(entries_open=False, gate_code="ml_no_model")),
        (ml_block("shadow", "no_model", None), {}),
        (None, {}),
    ])
    def test_30_no_raw_terms(self, tmp_path, ml, kw):
        hs = write_health_state(tmp_path, ["ml_restart_needed", "ml_score_errors"], stale=True)
        out = report_for(tmp_path, ml, health_state=hs, **kw)
        for bad in ("expired", "no_model", "shadow", "active", "model_id", MID_A, "ml_", "entries_blocked",
                    "PackageError", "v2_errors"):
            assert bad not in out, (bad, out)

    @pytest.mark.parametrize("bad", [[1, 2, 3], "metin", 42, {"mode": ["x"], "state": 5}])
    def test_30_corrupt_block_does_not_crash(self, tmp_path, bad):
        out = report_for(tmp_path, bad)
        assert "⚠️ Bazı bilgiler okunamadı" in lines_of(out)
        for raw in ("Traceback", "Error", "list", "TypeError"):
            assert raw not in out

    def test_section_order_before_risk_kademesi(self, tmp_path):
        extra = {"Risk kademesi": lambda: "📶 kademe satiri", "Bütçe": lambda: "💰 butce satiri"}
        out = report_for(tmp_path, ml_block("active", "ok", 12 * DAY), extra_sections=extra)
        ls = lines_of(out)
        i_model = next(i for i, ln in enumerate(ls) if ln.startswith("🤖 Model filtresi açık"))
        i_risk = ls.index("📶 kademe satiri")
        i_budget = ls.index("💰 butce satiri")
        i_normal = next(i for i, ln in enumerate(ls) if ln.startswith("🛡️ Her şey normal"))
        assert i_normal < i_model < i_risk < i_budget
        assert i_risk - i_model == 1                                 # "hemen önce"


class TestNedenTr:
    def test_ml_expired(self):
        assert tg.neden_tr("ml_expired") == "modelin süresi doldu"

    def test_ml_no_model(self):
        assert tg.neden_tr("ml_no_model") == "model yüklenemedi"

    @pytest.mark.parametrize("k", ["ml_other", "ml_veto", "ml_"])
    def test_other_ml_codes_keep_generic(self, k):
        assert tg.neden_tr(k) == "yapay zekâ filtresi hazır değil"


# ==========================================================================
# 31-33. sapma izleyicisi kancasi
# ==========================================================================
DRIFT_CFG = dataclasses.replace(H.DEFAULT_CFG, drift_check_enabled=True)


def dprobe(file_state="ok", generated_at=NOW - timedelta(hours=1), overall="OK", rules=()):
    return H.DriftProbe(file_state=file_state, generated_at=generated_at, overall=overall,
                        rules_at_uyari=tuple(rules))


def drift_res(probe, cfg=DRIFT_CFG, now=NOW, **kw):
    rep = ev(mk_snap(now=now, drift={"learner": probe} if probe is not None else None, **kw), cfg)
    out = [r for r in rep.results if r.name == "drift_monitor:learner"]
    assert len(out) == 1, [r.name for r in rep.results]
    return out[0], rep


class TestDriftHook:
    def test_31_disabled_is_placeholder(self):
        res, rep = drift_res(dprobe(overall="UYARI"), cfg=H.DEFAULT_CFG)
        expect(res, Status.SKIPPED, "placeholder")
        assert rep.overall is Status.OK

    def test_31_snapshot_none_is_placeholder(self):
        rep = ev(mk_snap(), DRIFT_CFG)
        r = [x for x in rep.results if x.name == "drift_monitor:learner"]
        if r:                                                          # kontrol uretilirse SKIPPED placeholder olmali
            expect(r[0], Status.SKIPPED, "placeholder")
        assert rep.overall is Status.OK

    def test_32_missing(self):
        expect(drift_res(dprobe("missing", None, None))[0], Status.WARN, "drift_missing")

    def test_32_unreadable(self):
        expect(drift_res(dprobe("unreadable", None, None))[0], Status.WARN, "drift_unreadable")

    def test_32_age_exact_36h_ok(self):
        res, _ = drift_res(dprobe(generated_at=NOW - timedelta(hours=36)))
        assert res.status is Status.OK

    def test_32_age_over_36h_stale(self):
        expect(drift_res(dprobe(generated_at=NOW - timedelta(hours=36, seconds=1)))[0], Status.WARN, "drift_stale")

    def test_32_alert_with_rule_ids(self):
        res, _ = drift_res(dprobe(overall="UYARI", rules=("R2_hit_rate", "R5_slip")))
        expect(res, Status.WARN, "drift_alert")
        assert "R2_hit_rate" in res.detail and "R5_slip" in res.detail

    @pytest.mark.parametrize("o", ["IZLE", "YETERSIZ", "OK"])
    def test_32_ok_values(self, o):
        assert drift_res(dprobe(overall=o))[0].status is Status.OK

    def test_32_unknown_overall(self):
        expect(drift_res(dprobe(overall="CRIT"))[0], Status.WARN, "drift_unreadable")

    def test_32_custom_max_age(self):
        cfg = dataclasses.replace(DRIFT_CFG, drift_max_age_s=60)
        expect(drift_res(dprobe(generated_at=NOW - timedelta(seconds=61)), cfg=cfg)[0], Status.WARN, "drift_stale")

    def test_33_never_crit_or_unknown_and_heartbeat_unchanged(self):
        base = ev(mk_snap(), DRIFT_CFG)
        for fs, ga, ov in itertools.product(
                ("ok", "missing", "unreadable"),
                (None, NOW - timedelta(hours=1), NOW - timedelta(hours=40), NOW + timedelta(hours=5)),
                (None, "OK", "IZLE", "YETERSIZ", "UYARI", "CRIT", "bilinmeyen", "")):
            res, rep = drift_res(dprobe(fs, ga, ov, rules=("R1",) if ov == "UYARI" else ()))
            assert res.status not in (Status.CRIT, Status.UNKNOWN), (fs, ga, ov, res)
            assert H.should_send_ok(rep) == H.should_send_ok(base), (fs, ga, ov)
            assert rep.healthy == base.healthy

    def test_33_does_not_mask_other_crit(self):
        bad = dict(api={b: _api(NOW, last_candle_open=NOW - timedelta(seconds=11000)) for b in ("learner", "twin")})
        _, rep = drift_res(dprobe(overall="UYARI", rules=("R1",)), **bad)
        assert rep.overall is Status.CRIT and not H.should_send_ok(rep)

    @pytest.mark.parametrize("code,sorun,duzeldi,anlam", [
        ("drift_alert", "Bot beklenenden farklı davranıyor", "Bot yeniden beklendiği gibi davranıyor",
         "Bot durdurulmadı; ayrıntı günlük raporda. İnceleme gerekir."),
        ("drift_missing", "Davranış izleyicisi çalışmıyor", "Davranış izleyicisi yeniden çalışıyor",
         "Günlük karşılaştırma yapılamıyor; işlemler etkilenmez."),
        ("drift_stale", "Davranış izleyicisi çalışmıyor", "Davranış izleyicisi yeniden çalışıyor",
         "Günlük karşılaştırma yapılamıyor; işlemler etkilenmez."),
        ("drift_unreadable", "Davranış izleyicisi çalışmıyor", "Davranış izleyicisi yeniden çalışıyor",
         "Günlük karşılaştırma yapılamıyor; işlemler etkilenmez."),
    ])
    def test_texts(self, code, sorun, duzeldi, anlam):
        a, steps = first_alert_named(code, "drift_monitor:learner")
        assert sorun in a.title and anlam in a.body
        assert code not in alert_text(a) and "drift_monitor" not in alert_text(a)
        out, _ = run_turns(steps + [(at_min(10), ok_report(at_min(10)))])
        rec = [x for x in out[-1][1] if x.level is Status.OK]
        assert rec and duzeldi in rec[0].title

    def test_alert_text_excludes_rule_ids(self):
        steps = []
        for i in range(2):
            n = at_min(i * 5)
            steps.append((n, ev(mk_snap(now=n, drift={"learner": dprobe(overall="UYARI", rules=("R2_hit_rate",))}),
                                DRIFT_CFG)))
        out, _ = run_turns(steps)
        sent = [a for _, al in out for a in al]
        assert sent and "R2_hit_rate" not in alert_text(sent[0])

    def test_single_sender_dedup(self):
        steps = []
        for i in range(6):
            n = at_min(i * 5)
            steps.append((n, ev(mk_snap(now=n, drift={"learner": dprobe(overall="UYARI", rules=("R1",),
                                                                       generated_at=n - timedelta(hours=1))}),
                                DRIFT_CFG)))
        out, _ = run_turns(steps)
        sent = [a for _, al in out for a in al if a.code == "drift_alert"]
        assert len(sent) == 1


def first_alert_named(code, name, status=Status.WARN):
    steps = [(at_min(i * 5), manual_report(code, status, name, at_min(i * 5))) for i in range(2)]
    out, _ = run_turns(steps)
    sent = [a for _, al in out for a in al]
    assert sent, code
    return sent[0], steps
