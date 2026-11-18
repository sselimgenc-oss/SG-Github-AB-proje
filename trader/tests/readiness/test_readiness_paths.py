"""Hazirlik 3/6/7: yapilandirma anahtarlari, birimler arasi yol tutarliligi (KILL, status, ledger, telegram outbox, yedek),
ikiz ayrimi. Sunucudaki gercek yollar render edilmis env/birimlerden okunur."""
from __future__ import annotations

import json
import posixpath
import re
from pathlib import Path

import pytest

from readiness_support import DEPLOY, ROOT, SERVER_TRADER_DIR as T, install_text, render_env_files, render_units, unit_kv


@pytest.fixture(scope="module")
def envs(tmp_path_factory):
    return render_env_files(tmp_path_factory.mktemp("envs"))


@pytest.fixture(scope="module")
def units(tmp_path_factory):
    return render_units(tmp_path_factory.mktemp("units"))


def _abs(p: str) -> str:
    return p if p.startswith("/") else posixpath.join(T, p)


def _cfg(bot):
    from trader_engine.config import load_engine_config
    return load_engine_config(ROOT / "config/engine.base.json", ROOT / f"config/engine.{bot}.json")


def _rw(units, name):
    return [p for k, v in unit_kv(units[name]) if k == "ReadWritePaths" for p in v.split()]


def _ro(units, name):
    return [p for k, v in unit_kv(units[name]) if k == "ReadOnlyPaths" for p in v.split()]


def _covered(path, allowed):
    return any(path == a.lstrip("-") or path.startswith(a.lstrip("-").rstrip("/") + "/") for a in allowed)


# ------------------------------------------------------------------ yapilandirma anahtarlari
def test_engine_configs_load_for_both_bots_and_pairs_agree_everywhere():
    from trader_core import veto
    learner, twin = _cfg("learner"), _cfg("twin")
    assert learner.bot == "learner" and twin.bot == "twin"
    assert learner.mode == twin.mode == "paper" and learner.veto_mode == twin.veto_mode == "required"
    assert learner.ml_mode == twin.ml_mode == "off" and learner.ml_model_path is None      # ml_mode=off: ML bagimliligi yok
    assert len(learner.pairs) == 10 and learner.pairs == twin.pairs
    vcfg = veto.load_config(ROOT / "config/veto.json")
    vp = veto.load_pairs(vcfg, ROOT)
    assert sorted(veto.pair_key(p) for p in learner.pairs) == vp, "veto pair listesi (config/engine.base.json) motorun ciftleriyle ayni olmali"
    assert vcfg.hmac_key_env == "TRADER_VETO_HMAC_KEY"


def test_other_configs_load():
    from trader_core import budget, lesson
    from trader_panel.data import load_config
    pc = load_config(ROOT / "config/panel.json")
    assert pc.host == "127.0.0.1"
    bc = budget.load_config(ROOT / "config/budget.json")
    assert bc is not None
    lc = lesson.load_config(ROOT / "config/lesson.json", budget_config_path=ROOT / "config/budget.json")
    assert lc.twin_enabled is True


def test_twin_is_isolated_from_learner_but_shares_feed():
    l, t = _cfg("learner"), _cfg("twin")
    assert t.start_delay_s > 0 and l.start_delay_s == 0                      # ikiz birkac sn gec baslar
    assert t.market_db == l.market_db                                         # TEK feed (tek yazar), ikisi salt okur
    assert len({l.ledger_path, t.ledger_path}) == 2 and len({l.state_path, t.state_path}) == 2
    assert len({l.status_path, t.status_path}) == 2
    for a, b in ((l.ledger_path, t.ledger_path), (l.state_path, t.state_path), (l.status_path, t.status_path)):
        assert posixpath.dirname(a) != posixpath.dirname(b)                   # ayri var alt dizini
    assert l.kill_file == t.kill_file                                         # kill ortak: ikisi de durur
    eng = (DEPLOY / "trader-engine@.service").read_text(encoding="utf-8")
    assert "--bot %i" in eng and "trader-feed.service" in eng                 # sablon: tek feed'e bagli
    inst = install_text()
    assert "enable_now trader-engine@twin.service" in inst and "--with-twin" in inst
    assert inst.index("enable_now trader-feed.service") < inst.index("enable_now trader-engine@learner.service")


def test_sqlite_market_db_opened_read_only_by_engine():
    src = (ROOT / "src/trader_engine/marketdata/sources.py").read_text(encoding="utf-8")
    assert "MarketStore(self.db_path, read_only=True)" in src               # motor feed'in dosyasina yazmaz


# ------------------------------------------------------------------ yol tutarliligi
def test_engine_var_paths_match_health_panel_telegram(envs, units):
    from trader_panel.data import load_config
    l = _cfg("learner")
    var = _abs(l.var_dir)
    h = envs["trader-health.env"]
    assert h["ENGINE_VAR_DIR"] == var == f"{T}/var"
    assert h["MARKET_DB"] == _abs(l.market_db)
    assert h["ENGINE_CONFIG_DIR"] == f"{T}/config"
    pc = load_config(ROOT / "config/panel.json")
    for bot, st, lg in (("learner", pc.status_path, pc.ledger_path), ("twin", pc.twin_status_path, pc.twin_ledger_path)):
        c = _cfg(bot)
        assert st.replace(str(ROOT), T) == _abs(c.status_path), bot
        assert lg.replace(str(ROOT), T) == _abs(c.ledger_path), bot
    import importlib.util
    spec = importlib.util.spec_from_file_location("health_run_mod", ROOT / "scripts/health_run.py")
    hr = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(hr)
    for bot in ("learner", "twin"):
        c = _cfg(bot)
        assert hr.status_path(var, bot) == _abs(c.status_path) and hr.ledger_path(var, bot) == _abs(c.ledger_path)


def test_telegram_engine_status_path_points_to_learner_status(envs):
    """ENGINE_STATUS_PATH bos olursa /durum ve gunluk rapor 'durum okunamadi' der (sessiz bozulma)."""
    assert envs["trader-telegram.env"]["ENGINE_STATUS_PATH"] == _abs(_cfg("learner").status_path)


def test_kill_file_same_path_in_engine_telegram_panel(envs, units):
    from trader_panel.data import load_config
    eng = _abs(_cfg("learner").kill_file)
    assert eng == _abs(_cfg("twin").kill_file) == f"{T}/shared/KILL"
    assert envs["trader-telegram.env"]["KILL_FILE"] == eng
    assert load_config(ROOT / "config/panel.json").kill_file.replace(str(ROOT), T) == eng
    kdir = posixpath.dirname(eng)
    assert _covered(kdir, _rw(units, "trader-engine@.service"))               # motor yazabilir/okur
    assert _covered(kdir, _rw(units, "trader-telegram.service"))              # Telegram /hepsini_kapat yazabilir
    assert _covered(kdir, _ro(units, "trader-panel.service"))                 # panel yalniz okur
    assert not _covered(kdir, _rw(units, "trader-panel.service"))
    assert (DEPLOY / "trader-panel.service").read_text().count("EnvironmentFile") == 1     # yalniz yorumda


def test_telegram_outbox_dir_is_writable_for_every_writer(envs, units):
    out = envs["trader-telegram.env"]["TELEGRAM_VAR_DIR"]
    assert out == f"{T}/var/telegram"
    for u in ("trader-telegram.service", "trader-telegram-report.service", "trader-lesson.service", "trader-health-fail@.service"):
        assert _covered(out, _rw(units, u)), u
    assert re.search(r'install -d -m 2770 -o "\$TRADER_USER" -g "\$TG_GROUP" "\$TRADER_DIR/var/telegram/outbox"', install_text())
    for u in ("trader-telegram.service", "trader-telegram-report.service", "trader-lesson.service", "trader-health-fail@.service"):
        assert "SupplementaryGroups=trader-tg" in units[u], u


def test_backup_paths_and_timer(envs, units):
    h = envs["trader-health.env"]
    assert h["BACKUP_DIR"] == "/var/backups/trader"
    assert _covered(h["BACKUP_DIR"], _rw(units, "trader-backup.service"))
    assert f"{T}/var" in _rw(units, "trader-backup.service")        # OPEN-10: var yazilabilir (WAL -shm); yedek mode=ro URI kullanir
    assert "/var/backups/trader" in install_text() and "EnvironmentFile=/etc/trader-health.env" in units["trader-backup.service"]
    assert "OnCalendar=*-*-* 03:10:00 UTC" in units["trader-backup.timer"]
    assert "ExecStart=" in units["trader-backup.service"] and "health_backup.py" in units["trader-backup.service"]
    assert "enable_now trader-backup.timer" in install_text()


def test_every_timer_has_a_service_and_is_enabled_or_gated(units):
    inst = install_text()
    for name in units:
        if name.endswith(".timer"):
            stem = name[:-6]
            kv = dict(unit_kv(units[name]))
            target = kv.get("Unit", stem + ".service")
            assert target in units, f"{name} -> {target} yok"
            assert (f"enable_now {name}" in inst or (name in ("trader-engine-retry@.timer", "trader-counterfactual@.timer", "trader-drift@.timer") and f"enable_now {name.replace('@.', '@learner.')}" in inst)
                    or (name == "trader-engine-env-retry@.timer" and "enable_now trader-engine-env-retry@testnet.timer" in inst and "enable --now trader-engine-env-retry@live.timer" in inst)), f"{name} install.sh'te etkinlestirilmiyor"


# ------------------------------------------------------------------ eski ACIK kusurlar (duzeltildi; regresyon testleri)
def test_OPEN_engine_unit_receives_veto_hmac_key():
    eng = (DEPLOY / "trader-engine@.service").read_text(encoding="utf-8")
    files = [v.lstrip("-") for k, v in unit_kv(eng) if k == "EnvironmentFile"]
    assert files, "motor birimi EnvironmentFile tanimlamiyor"
    have = {Path(f).name for f in files}
    assert any(
        "TRADER_VETO_HMAC_KEY" in (DEPLOY / (n + ".example")).read_text(encoding="utf-8")
        for n in have if (DEPLOY / (n + ".example")).exists())
    # API anahtari motora SIZMAZ; HMAC ayri dosyada, veto birimi de ayni dosyayi okur
    assert "trader-veto.env" not in have and "trader-veto-hmac.env" in have
    assert "ANTHROPIC" not in (DEPLOY / "trader-veto-hmac.env.example").read_text(encoding="utf-8")
    ve = (DEPLOY / "trader-veto.env.example").read_text(encoding="utf-8")
    assert "TRADER_VETO_HMAC_KEY" not in re.sub(r"#.*", "", ve)
    vs = [v for k, v in unit_kv((DEPLOY / "trader-veto.service").read_text(encoding="utf-8")) if k == "EnvironmentFile"]
    assert "/etc/trader-veto-hmac.env" in vs and "/etc/trader-veto.env" in vs


def test_OPEN_lesson_and_telegram_ledger_path_is_the_engine_ledger(envs):
    want = _abs(_cfg("learner").ledger_path)
    assert envs["trader-lesson.env"]["LEDGER_PATH"] == want
    assert envs["trader-telegram.env"]["LEDGER_PATH"] == want
    lc = json.loads((ROOT / "config/lesson.json").read_text())
    assert _abs(lc["ledger_path"]) == want and _abs(lc["twin_ledger_path"]) == _abs(_cfg("twin").ledger_path)


def test_OPEN_lesson_and_telegram_can_create_sqlite_sidecars(units):
    for u in ("trader-lesson.service", "trader-telegram.service"):
        assert any(p.rstrip("/") == f"{T}/user_data" for p in _rw(units, u)), u



def test_OPEN_lesson_config_has_a_notifier():
    assert json.loads((ROOT / "config/lesson.json").read_text())["notifier"] == "telegram"


def test_health_unit_can_notify_telegram_and_write_outbox(envs, units):
    h = units["trader-health.service"]
    kv = unit_kv(h)
    assert ("EnvironmentFile", "-/etc/trader-telegram.env") in kv
    assert "SupplementaryGroups=trader-tg" in h
    assert _covered(envs["trader-telegram.env"]["TELEGRAM_VAR_DIR"], _rw(units, "trader-health.service"))
    assert envs["trader-health.env"]["NOTIFIER"] == "auto"
    assert ("UMask", "0007") in kv                       # outbox dosyalari trader-tg grubuna okunur/yazilir (daemon siler)


def test_health_env_has_bots_and_veto_freshness(envs):
    h = envs["trader-health.env"]
    assert h["HEALTH_BOTS"] in ("learner,twin", "learner")
    assert h["VETO_FILE"] == f"{T}/shared/veto/veto.json"
    assert h["VETO_MAX_AGE_S"] == "5400"
    # veto.json'daki gercek cikis yolu ile ayni dosya
    assert json.loads((ROOT / "config/veto.json").read_text())["veto_path"] == "shared/veto/veto.json"


def test_lesson_and_telegram_sandbox_ledger_access(units):
    for u in ("trader-lesson.service", "trader-telegram.service"):
        assert f"-{T}/var/learner" in _rw(units, u), u
    assert f"-{T}/var/twin" in _ro(units, "trader-lesson.service")
    # telegram: /durdur ikiz icin de var/twin/pause_audit.jsonl yazar (WP-B6)
    assert f"-{T}/var/twin" in _rw(units, "trader-telegram.service")
    assert f"-{T}/var/twin" in _ro(units, "trader-telegram-report.service")
    assert _covered(f"{T}/var", _rw(units, "trader-backup.service"))                  # OPEN-10


def test_budget_db_precreated_and_hmac_generated_without_echo():
    t = install_text()
    assert re.search(r'install -m 0600 -o "\$TRADER_USER" -g "\$TRADER_USER" /dev/null "\$TRADER_DIR/user_data/budget.sqlite"', t)
    assert "openssl rand -hex 32" in t
    assert not re.search(r"echo[^\n]*HMAC_NEW|printf[^\n]*HMAC_NEW(?!.*>>)", t)


def test_telegram_pause_env_and_unit_match_engine(envs, units, tmp_path):
    e = envs["trader-telegram.env"]
    l = _cfg("learner")
    assert e["PAUSE_FILE"] == _abs(l.pause_file) == f"{T}/shared/PAUSE"
    assert e["ENGINE_VAR_DIR"] == _abs(l.var_dir) == f"{T}/var"
    assert e["PAUSE_BOTS"] == "learner,twin"
    assert any(k == "WorkingDirectory" for k, _ in unit_kv(units["trader-telegram.service"]))
    assert _covered(posixpath.dirname(e["PAUSE_FILE"]), _rw(units, "trader-telegram.service"))
    assert _covered(f"{T}/var/learner", _rw(units, "trader-telegram.service"))
    assert _covered(f"{T}/var/twin", _rw(units, "trader-telegram.service"))
    from readiness_support import render_env_files as rend
    (tmp_path / "nt").mkdir()
    assert rend(tmp_path / "nt", with_twin=0)["trader-telegram.env"]["PAUSE_BOTS"] == "learner"
