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
    assert sorted(veto.pair_key(p) for p in learner.pairs) == vp, "veto pair listesi (config/base.json) motorun ciftleriyle ayni olmali"
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
    assert f"{T}/var" in _ro(units, "trader-backup.service")
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
            assert f"enable_now {name}" in inst, f"{name} install.sh'te etkinlestirilmiyor"


# ------------------------------------------------------------------ ACIK kusurlar (xfail strict: duzelince test kirilir, isareti kaldirin)
@pytest.mark.xfail(strict=True, reason="ACIK OPEN-1 (P0): motor birimi TRADER_VETO_HMAC_KEY'i hic gormuyor (EnvironmentFile yok) -> veto 'key_missing', giris hic acilmaz")
def test_OPEN_engine_unit_receives_veto_hmac_key():
    eng = (DEPLOY / "trader-engine@.service").read_text(encoding="utf-8")
    files = [v.lstrip("-") for k, v in unit_kv(eng) if k == "EnvironmentFile"]
    assert files, "motor birimi EnvironmentFile tanimlamiyor"
    have = {Path(f).name for f in files}
    assert any(
        "TRADER_VETO_HMAC_KEY" in (DEPLOY / (n + ".example")).read_text(encoding="utf-8")
        for n in have if (DEPLOY / (n + ".example")).exists())


@pytest.mark.xfail(strict=True, reason="ACIK OPEN-6 (P1): ders/telegram LEDGER_PATH=user_data/ledger_learner.sqlite; motor defteri var/learner/ledger.sqlite")
def test_OPEN_lesson_and_telegram_ledger_path_is_the_engine_ledger(envs):
    want = _abs(_cfg("learner").ledger_path)
    assert envs["trader-lesson.env"]["LEDGER_PATH"] == want
    assert envs["trader-telegram.env"]["LEDGER_PATH"] == want
    lc = json.loads((ROOT / "config/lesson.json").read_text())
    assert _abs(lc["ledger_path"]) == want and _abs(lc["twin_ledger_path"]) == _abs(_cfg("twin").ledger_path)


@pytest.mark.xfail(strict=True, reason="ACIK OPEN-2 (P1): dizin salt okunur (ProtectSystem=strict) iken dosya-duzeyi ReadWritePaths -journal/-wal/-shm olusturtmaz (bkz. docs/hazirlik-denetimi.md)")
def test_OPEN_lesson_and_telegram_can_create_sqlite_sidecars(units):
    for u in ("trader-lesson.service", "trader-telegram.service"):
        assert any(p.rstrip("/") == f"{T}/user_data" for p in _rw(units, u)), u



@pytest.mark.xfail(strict=True, reason="ACIK OPEN-6 (P1): config/lesson.json notifier=null -> `lesson_run.py --once` her saat cikis 1 (bildirimci yapilandirilmamis) -> OnFailure")
def test_OPEN_lesson_config_has_a_notifier():
    assert json.loads((ROOT / "config/lesson.json").read_text())["notifier"] == "telegram"
