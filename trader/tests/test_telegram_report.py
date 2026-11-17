"""Günlük rapor bölümleri (Defter/Bütçe/Ders): salt okunur, her biri bağımsız hata verir."""
import json
import shutil
from datetime import datetime, timedelta, timezone
from pathlib import Path

from trader_core import ledger as L
from trader_core import lesson as LS
from trader_core import telegram as T

UTC = timezone.utc
ROOT = Path(__file__).resolve().parent.parent
NOW = datetime(2026, 11, 16, 18, 0, tzinfo=UTC)      # 21:00 TR
DAY = "2026-11-16"
PARAMS = {"range_width_atr": 4.0, "vol_ratio_max": 1.5, "edge_zone_atr": 0.25, "pullback_ema": 50,
          "stop_buffer_atr": 0.3, "trail_atr": 3.0, "range_target_frac": 0.75, "rr_min": 1.5, "trigger_tf": "1h"}


def mkcfg(tmp_path, **kw):
    d = dict(ledger_path=str(tmp_path / "l.sqlite"), twin_ledger_path=str(tmp_path / "t.sqlite"),
             budget_config=str(tmp_path / "config" / "budget.json"), lesson_store=str(tmp_path / "lesson.sqlite"))
    d.update(kw)
    return T.TelegramConfig("1:tok", 5, str(tmp_path / "tg"), "", str(tmp_path / "status.json"), **d)


def mkledger(path, bot, trades):
    clk = lambda: NOW  # noqa: E731
    led = L.open_ledger(path, bot, clock=clk)
    led.init_params(PARAMS, reason="x")
    for i, (win, closed) in enumerate(trades, start=1):
        bar = datetime(2026, 11, 16, 6 + i, 0, tzinfo=UTC)
        did = led.record_decision(L.DecisionEvent(
            bar_close_ts=bar, trigger_tf="1h", pair="ETH/USDT", side="long", setup="R1", regime="range",
            atr_ratio=1.1, rh=2100.0, rl=1980.0, rh_touches=2, rl_touches=3,
            features={"atr_1h": 20.0, "stop_dist_atr": 2.0, "atr_4h": 40.0, "wick_ratio": 0.5, "rr": 2.5,
                      "edge_dist_atr": 0.1},
            planned_entry=2000.0, planned_stop=1960.0, planned_target=2100.0, param_version_id=1,
            veto_status="allowed", veto_reason=None, risk_allowed=True, risk_reason="ok", size_qty=0.3,
            size_notional=600.0, size_margin=200.0, size_risk_amount=13.188, leverage=3,
            final_action="entered", skip_reason=None))
        led.record_trade_entry(L.TradeEntry(i, did, bar + timedelta(seconds=3), 2001.0, 0.3, 3, 0.30015))
        if closed:
            px = 2079.0 if win else 1960.0
            led.record_trade_exit(L.TradeExit(i, bar + timedelta(hours=1), px, "target" if win else "stop",
                                              2100.0, 0.3, 0.1))
    led.close()


def write_status(tmp_path):
    (tmp_path / "status.json").write_text(json.dumps({"equity": 1000.0, "day_start_equity": 1000.0}))


def test_ledger_normal_day(tmp_path):
    mkledger(tmp_path / "l.sqlite", "learner", [(True, True), (False, True), (True, False)])
    mkledger(tmp_path / "t.sqlite", "twin", [(True, True)])
    write_status(tmp_path)
    s = T.section_ledger(mkcfg(tmp_path), DAY)
    assert "kapanan=2" in s and "kazanan/kaybeden=1/1" in s and "açık=1" in s
    assert "equity=1000.00" in s and "bütçe %5=50.00$" in s and "ikiz: kapanan=1" in s


def test_ledger_no_trades(tmp_path):
    mkledger(tmp_path / "l.sqlite", "learner", [])
    mkledger(tmp_path / "t.sqlite", "twin", [])
    s = T.section_ledger(mkcfg(tmp_path), DAY)
    assert "kapanan=0" in s and "PnL=+0.00$" in s and "açık=0" in s


def test_ledger_missing_reported_in_report(tmp_path):
    cfg = mkcfg(tmp_path)
    out = T.build_report(cfg, NOW, DAY, T.default_sections(cfg, NOW, DAY))
    assert out.count("Bazı bilgiler okunamadı") == 1 and out.rstrip().endswith("Bazı bilgiler okunamadı")
    for ham in ("defter_yok", "depo_yok", "Defter:", "Ders", "SectionError", "yapilandirma"):
        assert ham not in out
    assert not (tmp_path / "l.sqlite").exists()          # okuma yazı oluşturmaz


def _budget(tmp_path, text=None):
    (tmp_path / "config").mkdir(exist_ok=True)
    (tmp_path / "config" / "budget.json").write_text(text if text is not None else
        (ROOT / "config" / "budget.json").read_text().replace("user_data/budget.sqlite", str(tmp_path / "b.sqlite")))


def test_budget_ok_and_corrupt(tmp_path):
    cfg = mkcfg(tmp_path)
    _budget(tmp_path)
    from trader_core import budget as B
    B.BudgetGuard(B.load_config(tmp_path / "config" / "budget.json")).authorize("veto", 0.01)   # deposu başlat
    assert (tmp_path / "b.sqlite").exists()
    s = T.section_budget(cfg)
    assert "/10.00$" in s and "/0.25$" in s and "ders 0.00$/0.10$" in s
    _budget(tmp_path, "{bozuk")
    out = T.build_report(cfg, NOW, DAY, {"Bütçe": lambda: T.rapor_butce(cfg)})
    assert "Bazı bilgiler okunamadı" in out and "yapilandirma" not in out
    _budget(tmp_path)
    (tmp_path / "b.sqlite").write_bytes(b"garbage" * 100)
    out = T.build_report(cfg, NOW, DAY, {"Bütçe": lambda: T.rapor_butce(cfg)})
    assert "Bazı bilgiler okunamadı" in out and "garbage" not in out


def test_lesson_pending_listed(tmp_path):
    cfg = mkcfg(tmp_path)
    cfg_l = LS.load_config(ROOT / "config" / "lesson.json")
    st = LS.LessonStore(cfg.lesson_store)
    run = st.create_run(cfg_l, "2026-11-16")
    st.add_event(run.id, "succeeded", "ok", {})
    st.set_shadow_once("2026-11-10", "2026-12-08")
    req = LS.ApprovalRequest("lr-2026-11-16-1", 3, 1, "rr_min", 1.5, 1.25, "global", "shadow_period", True, False,
                             "t", "b", {}, NOW, NOW + timedelta(days=3))
    st.add_request(run.id, req)
    st.close()
    s = T.section_lesson(cfg, NOW)
    assert "lr-2026-11-16-1: rr_min 1.5→1.25" in s and "/onayla lr-2026-11-16-1" in s
    assert "gün 7/28" in s and "2026-11-16 succeeded/ok" in s
    out = T.build_report(cfg, NOW, DAY, T.default_sections(cfg, NOW, DAY))
    assert len(out) <= 3500


# ------------------------------------------------------------------ sade Türkçe günlük rapor
def _status(tmp_path, now=NOW, **kw):
    d = {"mode": "paper", "kill": False, "kill_state": "flat", "entries_open": True, "equity": 1000.0,
         "day_start_equity": 1000.0, "loop_at": now.strftime("%Y-%m-%dT%H:%M:%SZ"), "param_version_id": 1,
         "open_positions": [], "gate": {"ok": True, "code": "ok"},
         "counters": {"mark_fallbacks": 11, "steps": 326, "decisions": 5, "skip:veto_missing": 1, "skip:stop_width": 1,
                      "skip:bilinmeyen_kod": 4, "ignore:no_signal": 300}}
    d.update(kw)
    (tmp_path / "status.json").write_text(json.dumps(d))


def _paper_cfg(tmp_path):
    mkledger(tmp_path / "l.sqlite", "learner", [])
    mkledger(tmp_path / "t.sqlite", "twin", [])
    (tmp_path / "tg").mkdir(exist_ok=True)
    return mkcfg(tmp_path)


def test_report_paper_is_plain_turkish(tmp_path):
    cfg = _paper_cfg(tmp_path)
    _status(tmp_path)
    _budget(tmp_path)
    out = T.build_report(cfg, NOW, DAY, T.default_sections(cfg, NOW, DAY))
    assert out.splitlines()[0] == "🌙 Günlük rapor · 16 Kasım (deneme parası)"
    for want in ("📈 Bugün: +0,00 $ (+%0,00)", "💰 Kasa: 1.000,00 $ (gün başı 1.000,00 $)",
                 "🧾 Bugün kapanan işlem: 0 · kazanan 0 / kaybeden 0", "📌 Açık pozisyon yok",
                 "🔎 Bot açıldığından beri 326 kez piyasaya bakıldı, 5 fırsat değerlendirildi, 0 işlem açıldı",
                 "↳ Atlananlar: 1 veto hazır değildi, 1 stop çok genişti", "🛡️ Her şey normal, yeni işlemler açık"):
        assert want in out, want
    for ham in ("{", "Sayaclar", "PermissionError", "depo_yok", "Spool", "bilgiler okunamadı", "bilinmeyen_kod",
                "veto_missing", "fiyatlar doğrulanmadı", "kip="):
        assert ham not in out, ham
    assert "İkiz" not in out                                   # ikizde işlem yok -> satır yok


def test_report_open_positions_and_twin_line(tmp_path):
    mkledger(tmp_path / "l.sqlite", "learner", [(True, True), (False, True)])
    mkledger(tmp_path / "t.sqlite", "twin", [(True, True)])
    (tmp_path / "tg").mkdir(exist_ok=True)
    cfg = mkcfg(tmp_path)
    pos = [{"pair": f"P{i}/USDT", "side": "long" if i % 2 else "short", "entry_price": 2000.0 + i, "stop": 1960.0}
           for i in range(8)]
    _status(tmp_path, open_positions=pos)
    out = T.build_report(cfg, NOW, DAY, T.default_sections(cfg, NOW, DAY))
    assert "📌 Açık pozisyonlar (8):" in out and "… ve 2 pozisyon daha" in out
    assert "P1/USDT · uzun · giriş 2.001,00 · stop 1.960,00" in out and "P0/USDT · kısa" in out
    assert "🧾 Bugün kapanan işlem: 2 · kazanan 1 / kaybeden 1" in out and " R" in out
    assert "👥 İkiz bot: 1 işlem kapandı" in out


def test_report_risk_closed_lines(tmp_path):
    cfg = _paper_cfg(tmp_path)
    _status(tmp_path, entries_open=False, entries_blocked_reason="clock_skew")
    out = T.build_report(cfg, NOW, DAY, T.default_sections(cfg, NOW, DAY))
    assert "🛑 Yeni işlemler kapalı: sunucu saati kaymış" in out and "Her şey normal" not in out and "clock_skew" not in out
    _status(tmp_path, kill=True, entries_open=False)
    assert "🛑 Acil durdurma (KILL) açık" in T.build_report(cfg, NOW, DAY, {})
    _status(tmp_path, entries_open=False, equity=940.0)
    assert "🛑 Günlük zarar sınırına ulaşıldı" in T.build_report(cfg, NOW, DAY, {})
    _status(tmp_path, entries_open=False, gate={"ok": False, "code": "paused"})
    out = T.build_report(cfg, NOW, DAY, {"Duraklatma": lambda: "⏸️ ana bot: yeni işlemler duraklatıldı — elle durduruldu"})
    assert "⏸️ ana bot: yeni işlemler duraklatıldı" in out and "Her şey normal" not in out


def test_report_heartbeat_missing_first_line(tmp_path):
    cfg = _paper_cfg(tmp_path)
    _status(tmp_path, now=NOW - timedelta(minutes=7))
    out = T.build_report(cfg, NOW, DAY, {})
    assert out.splitlines()[0] == "🚨 Motor yanıt vermiyor! (son sinyal 7 dk önce)"
    assert "Her şey normal" not in out


def test_report_budget_line_threshold(tmp_path):
    cfg = _paper_cfg(tmp_path)
    _status(tmp_path)
    _budget(tmp_path)
    from trader_core import budget as B
    guard = B.BudgetGuard(B.load_config(tmp_path / "config" / "budget.json"))
    guard.authorize("veto", 0.01)                                   # depo başlar, harcama %50'nin çok altında
    assert T.rapor_butce(cfg) == ""
    assert "Yapay zekâ" not in T.build_report(cfg, NOW, DAY, T.default_sections(cfg, NOW, DAY))
    import dataclasses
    from trader_core import budget as B2
    st = B2.BudgetGuard(B2.load_config(tmp_path / "config" / "budget.json")).status()
    fake = dataclasses.replace(st, month_used_usd=6.1, monthly_cap_usd=10.0)
    orig = T.section_budget_status
    T.section_budget_status = lambda c: fake
    try:
        line = T.rapor_butce(cfg)
        assert line == "🤖 Yapay zekâ bütçesi: ayda 6,10 $ / 10 $"
        assert "🤖 Yapay zekâ bütçesi: ayda 6,10 $ / 10 $" in T.build_report(cfg, NOW, DAY, T.default_sections(cfg, NOW, DAY))
        T.section_budget_status = lambda c: dataclasses.replace(st, month_used_usd=4.99, monthly_cap_usd=10.0)
        assert T.rapor_butce(cfg) == ""
        T.section_budget_status = lambda c: dataclasses.replace(st, month_used_usd=5.0, monthly_cap_usd=10.0)
        assert "ayda 5,00 $ / 10 $" in T.rapor_butce(cfg)
    finally:
        T.section_budget_status = orig


def test_report_health_spool_and_lesson_rules(tmp_path):
    cfg = _paper_cfg(tmp_path)
    _status(tmp_path)
    hs = tmp_path / "health.json"
    cfg = mkcfg(tmp_path, health_state=str(hs))
    hs.write_text(json.dumps({"last_overall": "OK"}))
    assert "Sağlık" not in T.build_report(cfg, NOW, DAY, {})
    hs.write_text(json.dumps({"last_overall": "CRIT"}))
    assert "⚠️ Sağlık kontrolü: sorun var, panoya bak" in T.build_report(cfg, NOW, DAY, {})
    hs.write_text("{bozuk")
    out = T.build_report(cfg, NOW, DAY, {})
    assert "Sağlık" not in out and "JSONDecodeError" not in out and "bilgiler okunamadı" not in out
    assert T.rapor_ders(cfg, NOW) == ""                                # depo yok -> bölüm hiç yok
    assert "Spool" not in out and "📮" not in out
    from trader_core.telegram import Outbox
    ob = Outbox(cfg.var_dir, lambda: NOW)
    for i in range(3):
        ob.enqueue({"dedup_key": f"k{i}", "text": "x", "severity": "INFO", "created": 0})
    assert "📮 Gönderilemeyen 3 mesaj bekliyor" in T.build_report(cfg, NOW, DAY, {})


def test_report_section_failures_collapse_to_one_line(tmp_path):
    cfg = _paper_cfg(tmp_path)
    _status(tmp_path)

    def boom():
        raise PermissionError("secret path")
    out = T.build_report(cfg, NOW, DAY, {"A": boom, "B": boom, "C": boom})
    assert out.count("Bazı bilgiler okunamadı") == 1 and "PermissionError" not in out and "secret" not in out
    assert out.rstrip().endswith("Bazı bilgiler okunamadı")
