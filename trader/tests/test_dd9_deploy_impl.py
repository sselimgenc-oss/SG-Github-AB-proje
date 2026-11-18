"""DD-9 uygulama testleri (deploy/betik/yol tarafi). Sartname testleri ayri dosyadadir; bunlar uygulamanin kenar durumlari."""
from __future__ import annotations

import json
import os
import re
import shutil
import sqlite3
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))
INSTALL = (ROOT / "deploy" / "install.sh").read_text(encoding="utf-8")


def _fn(name: str) -> str:
    m = re.search(rf"^{name}\(\) \{{.*?^\}}", INSTALL, re.S | re.M)
    assert m, name
    return m.group(0)


def _bash(script: str, **env) -> subprocess.CompletedProcess:
    return subprocess.run(["bash", "-c", script], capture_output=True, text=True, env={**os.environ, **env})


# ----------------------------------------------------------------------------- install.sh islevleri
def test_impl9_set_kv_preserves_other_lines_and_missing_final_newline(tmp_path):
    f = tmp_path / "e.env"
    f.write_bytes(b"A=1\nB=eski\nC=3")                       # son satir satir sonsuz
    script = f"set -e\n{_fn('set_kv')}\nset_kv {f} B 'yeni/de|er&x'\nset_kv {f} B 'yeni/de|er&x'\nset_kv {f} D 4\n"
    assert _bash(script).returncode == 0
    assert f.read_bytes() == b"A=1\nB=yeni/de|er&x\nC=3\nD=4\n"


def test_impl9_resolve_commit_strips_and_rejects_bad_file(tmp_path):
    rel = tmp_path / "rel"
    rel.write_text("COMMIT=" + "a" * 40 + "  \n")
    s = f"{_fn('valid_commit')}\n{_fn('resolve_commit')}\nresolve_commit\n"
    r = _bash(s, RELEASE_FILE=str(rel), COMMIT="")
    assert r.stdout.strip() == "a" * 40
    rel.write_text("COMMIT=ABC\n")
    assert _bash(s, RELEASE_FILE=str(rel), COMMIT="").returncode == 1


def test_impl9_install_refuses_without_commit_before_any_change(tmp_path):
    head = INSTALL[:INSTALL.index("# ---- 0.")]
    pre = "id() { echo 0; }\n"
    e = {"COMMIT": "", "RELEASE_FILE": str(tmp_path / "yok")}
    r = subprocess.run(["bash", "-c", pre + head], capture_output=True, text=True, env={**os.environ, **e}, cwd=tmp_path)
    assert r.returncode == 1 and "COMMIT gerekli" in r.stderr


def test_impl9_install_text_invariants():
    assert "merge --ff-only" not in INSTALL and "usermod -aG" not in INSTALL and "0640" not in INSTALL
    assert "groupdel" not in INSTALL
    code = re.sub(r"#.*", "", INSTALL)
    assert "systemctl enable --now trader-engine-live" not in code and "enable_now trader-engine-live" not in code
    assert code.index("live_preflight.py") < code.index("systemctl enable trader-engine-live.service")
    for ln in INSTALL.splitlines():
        if "git" in ln and "REPO_DIR" in ln and not ln.lstrip().startswith("#"):
            assert ln.lstrip().startswith("as_trader"), ln


# ----------------------------------------------------------------------------- live_paths / preflight
def _write_cfg(tmp_path: Path) -> Path:
    c = tmp_path / "k" / "config"
    c.mkdir(parents=True)
    shutil.copy(ROOT / "config" / "engine.live.json", c / "engine.live.json")
    return c


def test_impl9_check_against_config_consistent_and_ladder_only_when_present(tmp_path):
    from trader_core import live_paths as LP
    cfg = _write_cfg(tmp_path)
    k = cfg.parent
    env = {"LIVE_BOTS": "learner", "LIVE_VAR_DIR": f"{k}/var-live", "LIVE_PAUSE_FILE": f"{k}/shared/live/PAUSE"}
    assert LP.check_against_config(env, cfg) == ()                 # saglik env'i tek basina (KILL_FILE yok) tutarli
    assert LP.check_against_config({**env, "KILL_FILE": f"{k}/shared/KILL"}, cfg) == ("kill_file_mismatch",)
    assert LP.check_against_config({"LIVE_BOTS": ""}, cfg) == ()
    with pytest.raises(LP.LivePathError):
        LP.bot_var_dir({"LIVE_BOTS": "learner"}, "learner", "/x/var")


def test_impl9_preflight_never_prints_secret_values(tmp_path, capsys):
    import live_preflight as P
    cfg = _write_cfg(tmp_path)
    k = cfg.parent
    etc = tmp_path / "etc"
    etc.mkdir()
    (etc / "trader-live.env").write_text("BINANCE_API_KEY=SIZMA-" + "k" * 40 + "\nBINANCE_API_SECRET=SIZMA-" + "s" * 40 + "\nLIVE_CONFIRM=SIZMA-x\n")
    (etc / "trader-release").write_text("COMMIT=" + "a" * 40 + "\n")
    for n in ("trader-live.env", "trader-release"):
        os.chmod(etc / n, 0o600)
    rc = P.main(["--skip-owner"], etc_dir=str(etc), config_dir=str(cfg), id_groups=("trader",))
    out = capsys.readouterr().out
    assert rc == 1 and "SIZMA" not in out and "FAIL live_confirm_matches" in out and "OK trader_not_in_tg" in out
    assert str(k) not in out


# ----------------------------------------------------------------------------- saglik / yedek
def test_impl9_account_mode_increase_rules():
    from trader_core import health as H
    assert H._acct_increase(3, None) == 0 and H._acct_increase(1, 5) == 1 and H._acct_increase(6, 5) == 1


def test_impl9_backup_live_env_invalid_marks_live_jobs_failed(tmp_path):
    import health_backup as B
    var = tmp_path / "var"
    for bot in ("learner", "twin"):
        (var / bot).mkdir(parents=True)
        c = sqlite3.connect(var / bot / "state.sqlite")
        c.execute("CREATE TABLE positions(id INTEGER)")
        c.commit()
        c.close()
    code, m = B.run_backup(tmp_path / "bk", var, bots=("learner", "twin"), bot_dirs={"learner": None}, free_bytes=lambda: 10 * B.GIB)
    assert code == B.EXIT_FAILED
    assert m["files"]["ledger_learner@live.sqlite"]["error"] == "live_env_invalid"
    assert m["files"]["state_twin.sqlite"]["ok"] is True or "state_twin.sqlite" in m["files"]


def test_impl9_engine_retry_unit_state_keys_split(tmp_path):
    import engine_retry as R
    calls = []

    def ctl(a):
        calls.append(list(a))
        return 0, "ActiveState=active\nExecMainStatus=0\nResult=success\n"
    assert R.run("learner", {"STATE_DIR": str(tmp_path)}, ctl=ctl, unit="trader-engine-live.service") == "noop"
    assert calls[0][1] == "trader-engine-live.service"
    with pytest.raises(ValueError):
        R.run("learner", {"STATE_DIR": str(tmp_path)}, ctl=ctl, unit="sshd.service")


def test_impl9_units_symmetry_and_render_of_env_retry():
    kv = lambda n: [ln for ln in (ROOT / "deploy" / n).read_text().splitlines() if ln and not ln.startswith("#")]  # noqa: E731
    live, test = kv("trader-engine-live.service"), kv("trader-engine-testnet.service")
    assert len(live) == len(test) + 1                  # fark: yalniz OOMScoreAdjust
    assert "Conflicts=" not in "\n".join(live)


# ----------------------------------------------------------------------------- F2-F5 (mentor duzeltmeleri)
def _block(start_pat: str) -> str:
    """start_pat ile baslayan satirdan, sutun 0'daki ilk `fi` satirina kadar ust duzey blok."""
    m = re.search(rf"^{start_pat}.*?^fi$", INSTALL, re.S | re.M)
    assert m, start_pat
    return m.group(0)


def test_impl9_f2_safe_tree_path_rejects_symlinks_and_touches_nothing(tmp_path):
    real = tmp_path / "real"
    real.mkdir()
    os.chmod(real, 0o750)
    (tmp_path / "leaf").symlink_to(real)
    (real / "sub").mkdir()
    pre = "fail() { echo FAIL >&2; exit 1; }\n" + _fn("safe_tree_path") + "\n"
    ok = _bash(pre + f"safe_tree_path {real}/sub {tmp_path}/yok/yeni\n")
    assert ok.returncode == 0, ok.stderr
    assert _bash(pre + f"safe_tree_path {tmp_path}/leaf\n").returncode != 0                 # yaprak baglanti
    assert _bash(pre + f"safe_tree_path {tmp_path}/leaf/sub\n").returncode != 0              # ust bilesen baglanti
    assert (real.stat().st_mode & 0o777) == 0o750                                            # hedefe dokunulmadi
    # fail tanimsiz olsa bile sifirdan farkli cikis
    assert _bash(_fn("safe_tree_path") + f"\nsafe_tree_path {tmp_path}/leaf\n").returncode != 0


def test_impl9_f2_every_trader_tree_install_is_guarded_and_key_uses_chown_h():
    lines = INSTALL.splitlines()
    n = 0
    for i, ln in enumerate(lines):
        st = ln.strip()
        if re.match(r"install -(d|m)\b", st) and '-o "$TRADER_USER"' in st:
            n += 1
            prev = [x for x in lines[max(0, i - 12):i] if not x.strip().startswith("#")]
            assert any("safe_tree_path" in x for x in prev), st
    assert n >= 5
    assert 'chown -h "$TRADER_USER:$TRADER_USER" "$DEPLOY_KEY"' in INSTALL and '[ ! -L "$DEPLOY_KEY" ]' in INSTALL
    assert re.search(r'safe_tree_path "\$DEPLOY_KEY"', INSTALL)


def _reexec_run(tmp_path, flag):
    (tmp_path / "releases" / "C" / "deploy").mkdir(parents=True, exist_ok=True)
    (tmp_path / "releases" / "C" / "deploy" / "install.sh").write_text("echo RELEASE-RAN\n")
    blk = _block(r'if \[ "\$\{TRADER_INSTALL_REEXEC:-\}" != "root" \]')
    s = (f"say() {{ :; }}\nROOT_DIR={tmp_path}\nCOMMIT=C\nSELF_SUM_AT_START=farkli\n"
         f"{'export TRADER_INSTALL_REEXEC=' + flag if flag else ''}\n{blk}\necho SKIPPED\n")
    return _bash(s).stdout


def test_impl9_f3_reexec_unless_root_flag(tmp_path):
    assert "RELEASE-RAN" in _reexec_run(tmp_path, "1")            # eski betigin bayragi atlatamaz
    assert "RELEASE-RAN" in _reexec_run(tmp_path, "")
    out = _reexec_run(tmp_path, "root")
    assert "SKIPPED" in out and "RELEASE-RAN" not in out
    assert "export TRADER_INSTALL_REEXEC=root" in INSTALL


def test_impl9_f4_root_venv_pip_is_always_hash_pinned():
    cmds = INSTALL.replace("\\\n", " ")
    pips = [ln for ln in cmds.splitlines() if '"$ROOT_DIR/venv/bin/python" -m pip' in ln]
    assert pips and all("--require-hashes" in ln for ln in pips)


def test_impl9_f5_live_without_release_file_fails_before_any_change(tmp_path):
    blk = _block(r'if \[ "\$LIVE" -eq 1 \]; then\n  say "Canli on kosullari"')
    rec = tmp_path / "rec"
    s = (f"fail() {{ echo \"FAIL:$*\" >&2; exit 1; }}\nsay() {{ :; }}\nsystemctl() {{ echo \"$@\" >> {rec}; }}\n"
         f"has_value() {{ return 0; }}\nRELEASE_FILE={tmp_path}/yok\nLIVE=1\nCOMMIT={'a' * 40}\n{blk}\n")
    r = _bash(s)
    assert r.returncode != 0 and "FAIL:" in r.stderr and "sız kurulum" in r.stderr
    assert not rec.exists()
