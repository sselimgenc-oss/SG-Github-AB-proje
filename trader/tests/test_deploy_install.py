"""Sunucu kurulum paketi icin statik denetimler (ag yok, systemd yok)."""
import re
import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
DEPLOY = ROOT / "deploy"
SCRIPTS = [DEPLOY / "install.sh", DEPLOY / "uninstall.sh"]
UNITS = sorted(p for p in DEPLOY.iterdir() if p.suffix in (".service", ".timer"))


@pytest.mark.parametrize("path", SCRIPTS, ids=lambda p: p.name)
def test_bash_syntax(path):
    assert subprocess.run(["bash", "-n", str(path)], capture_output=True).returncode == 0


@pytest.mark.skipif(shutil.which("shellcheck") is None, reason="shellcheck yok")
@pytest.mark.parametrize("path", SCRIPTS, ids=lambda p: p.name)
def test_shellcheck(path):
    r = subprocess.run(["shellcheck", "-S", "warning", str(path)], capture_output=True, text=True)
    assert r.returncode == 0, r.stdout


@pytest.mark.parametrize("path", SCRIPTS, ids=lambda p: p.name)
def test_no_secrets(path):
    t = path.read_text(encoding="utf-8")
    assert not re.search(r"sk-ant-[A-Za-z0-9_-]{8,}", t)
    assert not re.search(r"\b\d{8,10}:[A-Za-z0-9_-]{30,}", t)  # telegram token
    assert "PRIVATE KEY" not in t
    assert "ghp_" not in t and "github_pat_" not in t
    assert not re.search(r"^\s*(set -x|.*\bxtrace\b)", t, re.M)


def test_strict_mode_and_root_check():
    t = (DEPLOY / "install.sh").read_text(encoding="utf-8")
    assert "set -euo pipefail" in t
    assert "id -u" in t


def test_no_firewall_or_public_bind():
    t = "\n".join(p.read_text(encoding="utf-8") for p in SCRIPTS)
    assert not re.search(r"\bufw\b|iptables|nft |0\.0\.0\.0", t)


def test_engine_unit():
    t = (DEPLOY / "trader-engine@.service").read_text(encoding="utf-8")
    assert re.search(r"^MemoryMax=\d+M", t, re.M)
    assert re.search(r"^Nice=\d+", t, re.M)
    assert "Restart=on-failure" in t
    assert "-m trader_engine run --bot %i" in t
    assert (ROOT / "src/trader_engine/__main__.py").exists()
    for bot in ("learner", "twin"):
        assert (ROOT / f"config/engine.{bot}.json").exists()
    assert (ROOT / "config/engine.base.json").exists()


def test_units_reference_existing_paths():
    for u in UNITS:
        for m in re.finditer(r"/opt/trader/((?:scripts|config|src|docs)/[\w./-]+)", u.read_text(encoding="utf-8")):
            assert (ROOT / m.group(1)).exists(), f"{u.name}: {m.group(1)}"


def test_every_unit_handled_by_install():
    t = (DEPLOY / "install.sh").read_text(encoding="utf-8")
    # glob ile hepsi kurulur
    assert 'deploy/trader-*.service' in t and 'deploy/trader-*.timer' in t
    assert all(u.name.startswith("trader-") for u in UNITS)
    # etkinlestirme politikasi: her zamanlayici ve servis ya acikca etkinlestirilir ya da bilincli olarak etkinlestirilmez
    enabled = set(re.findall(r"enable_now (trader-[\w@.-]+)", t))
    deliberately_not = {"trader-health-fail@.service", "trader-health.service", "trader-backup.service", "trader-lesson.service",
                        "trader-veto.service", "trader-telegram-report.service", "trader-engine@.service",
                        "trader-panel-publish.service"}  # tetikleyici/sablon birimler
    for u in UNITS:
        if u.name == "trader-engine@.service":
            assert "trader-engine@learner.service" in enabled and "trader-engine@twin.service" in enabled
        elif u.name in deliberately_not:
            continue
        else:
            assert u.name in enabled, u.name


def test_env_examples_installed():
    t = (DEPLOY / "install.sh").read_text(encoding="utf-8")
    for p in DEPLOY.glob("*.env.example"):
        assert p.name in t, p.name
    assert "[ -e \"$dst\" ]" in t  # var olan ezilmez


def test_placeholder_gated_timers():
    t = (DEPLOY / "install.sh").read_text(encoding="utf-8")
    for key in ("ANTHROPIC_API_KEY_LESSON", "ANTHROPIC_API_KEY_VETO", "TRADER_VETO_HMAC_KEY", "TELEGRAM_BOT_TOKEN", "TELEGRAM_CHAT_ID"):
        assert re.search(rf"has_value \S+ {key}", t), key


def test_uninstall_only_trader_units():
    t = (DEPLOY / "uninstall.sh").read_text(encoding="utf-8")
    rms = re.findall(r"rm -[a-z]*f?\s+(.+)", t)
    assert "--purge" in t
    assert 'trader-*.service' in t and 'trader-*.timer' in t
    for line in t.splitlines():
        if re.search(r"systemctl (disable|stop)", line):
            assert '"$u"' in line  # yalniz trader-* ile suzulmus liste
    assert 'case "$u" in trader-*)' in t
    # silinen yollar yalniz bize ait
    for r in rms:
        for tok in r.split():
            tok = tok.strip('"')
            if tok.startswith("-"):
                continue
            assert any(k in tok for k in ("trader", "$f", "REPO_DIR")), tok
    assert "/swapfile" not in re.sub(r"echo .*", "", t)


def test_python_version_guard_and_runtime_deps():
    t = (DEPLOY / "install.sh").read_text(encoding="utf-8")
    assert "(3, 11)" in t
    assert "freqtrade" not in re.sub(r"#.*", "", t) and "pytest" not in re.sub(r"#.*", "", t)
    for dep in ("requests", "pandas", "numpy", "pyarrow", "anthropic"):
        assert dep in t


def test_install_does_not_install_frameworks():
    t = (Path(__file__).resolve().parents[1] / "deploy" / "install.sh").read_text()
    code = re.sub(r"#.*", "", t)
    for banned in ("ccxt", "freqtrade", "python-binance"):
        assert banned not in code


def test_panel_unit():
    t = (DEPLOY / "trader-panel.service").read_text(encoding="utf-8")
    assert re.search(r"^MemoryMax=64M$", t, re.M) and re.search(r"^Nice=10$", t, re.M)
    assert "EnvironmentFile" not in re.sub(r"#.*", "", t)          # anahtar/token gorulmez
    assert "-m trader_panel --config /opt/trader/config/panel.json" in t
    assert re.search(r"^ReadOnlyPaths=.*/opt/trader/var", t, re.M)
    assert re.search(r"^IPAddressAllow=localhost$", t, re.M) and re.search(r"^IPAddressDeny=any$", t, re.M)
    assert (ROOT / "src/trader_panel/__main__.py").exists() and (ROOT / "config/panel.json").exists()


def test_panel_installed_enabled_and_removed():
    i = (DEPLOY / "install.sh").read_text(encoding="utf-8")
    assert re.search(r"^enable_now trader-panel\.service", i, re.M)       # etkin + baslatilir
    u = (DEPLOY / "uninstall.sh").read_text(encoding="utf-8")
    assert "trader-*.service" in u and 'case "$u" in trader-*)' in u      # glob trader-panel.service'i de kaldirir


@pytest.mark.skipif(shutil.which("systemd-analyze") is None, reason="systemd-analyze yok")
def test_panel_unit_systemd_verify():
    r = subprocess.run(["systemd-analyze", "verify", "--man=no", str(DEPLOY / "trader-panel.service")],
                       capture_output=True, text=True)
    bad = [ln for ln in (r.stdout + r.stderr).splitlines()
           if "trader-panel" in ln and not re.search(r"Failed to (create|connect)|not found|Executable|User|Group", ln)]
    assert not bad, bad


# ---- panel yayini (Cloudflare Worker, spec §13) ----
def test_publish_script_static():
    p = DEPLOY / "panel_yayinla.sh"
    assert subprocess.run(["bash", "-n", str(p)], capture_output=True).returncode == 0
    t = p.read_text(encoding="utf-8")
    code = re.sub(r"^\s*#.*$", "", t, flags=re.M)
    assert "set -euo pipefail" in t
    assert "set -x" not in t and "xtrace" not in t
    for line in code.splitlines():
        if re.search(r"\b(echo|printf|cat)\b", line):
            assert "CLOUDFLARE_API_TOKEN" not in line and "CLOUDFLARE_ACCOUNT_ID" not in line, line
    assert "trader-pano" in t and "TRADER_PANEL_WORKER" in t
    assert "snapshot --out" in t and "wrangler" in t and " deploy " in t
    assert "exit 1" in t and "/etc/trader-panel-cf.env" in t
    assert "PANO_KILITSIZ" not in t


def test_publish_units_and_env_example():
    s = (DEPLOY / "trader-panel-publish.service").read_text(encoding="utf-8")
    assert "Type=oneshot" in s and re.search(r"^MemoryMax=\d+M", s, re.M) and re.search(r"^Nice=\d+", s, re.M)
    assert "EnvironmentFile=/etc/trader-panel-cf.env" in s
    tm = (DEPLOY / "trader-panel-publish.timer").read_text(encoding="utf-8")
    assert "OnUnitActiveSec=5min" in tm and "Persistent=true" in tm
    ex = (DEPLOY / "trader-panel-cf.env.example").read_text(encoding="utf-8")
    for line in ex.splitlines():
        if line and not line.startswith("#"):
            k, _, v = line.partition("=")
            assert v == "", line   # yalniz yer tutucu


def test_publish_timer_gated_and_wrangler_pinned():
    t = (DEPLOY / "install.sh").read_text(encoding="utf-8")
    assert re.search(r"has_value /etc/trader-panel-cf\.env CLOUDFLARE_API_TOKEN", t)
    assert re.search(r"has_value /etc/trader-panel-cf\.env CLOUDFLARE_ACCOUNT_ID", t)
    assert "enable_now trader-panel-publish.timer" in t
    assert "wrangler secret put PANEL_SIFRE" in t
    assert re.search(r'^WRANGLER_VERSION="\d+\.\d+\.\d+"', t, re.M)
    code = re.sub(r"#.*", "", t)
    assert "npm install -g" not in code and "npm i -g" not in code
    assert not re.search(r"curl[^\n|]*\|\s*(ba)?sh", code)
    assert "command -v node" in t
    assert "trader-panel-cf.env.example" in t


def test_worker_js_static():
    t = (DEPLOY / "panel_worker.js").read_text(encoding="utf-8")
    assert "PANEL_SIFRE" in t and "typeof sifre !== \"string\" || sifre.length === 0) return red()" in t   # fail-closed
    assert "crypto.subtle.digest" in t and "fark |=" in t                                                  # sabit zamanli
    assert re.search(r'"Cache-Control", "no-store"', t)
    for h in ("X-Content-Type-Options", "Referrer-Policy", "Content-Security-Policy", "X-Frame-Options"):
        assert h in t
    assert not re.search(r"KILITSIZ|UNLOCK|unlock|kilitsiz", t, re.I)
    assert "pano_worker.js" in t       # kaynak notu
    n = (ROOT / "THIRD_PARTY_NOTICES.md").read_text(encoding="utf-8")
    assert "pano_worker.js" in n


@pytest.mark.skipif(shutil.which("node") is None, reason="node yok")
def test_worker_js_fail_closed_behaviour(tmp_path):
    js = tmp_path / "t.mjs"
    js.write_text(f"""import w from {str(DEPLOY / 'panel_worker.js')!r};
const env0 = {{ASSETS: {{fetch: async () => new Response('ok')}}}};
const rq = (a) => new Request('https://x/', a ? {{headers: {{Authorization: a}}}} : {{}});
const ok = 'Basic ' + btoa('trader:pw');
let r = await w.fetch(rq(ok), env0); if (r.status !== 401) throw new Error('fail-open');
r = await w.fetch(rq(ok), {{...env0, PANEL_SIFRE: 'pw'}}); if (r.status !== 200 || r.headers.get('Cache-Control') !== 'no-store') throw new Error('ok yolu');
r = await w.fetch(rq('Basic ' + btoa('trader:x')), {{...env0, PANEL_SIFRE: 'pw'}}); if (r.status !== 401) throw new Error('yanlis parola');
r = await w.fetch(rq(), {{...env0, PANEL_SIFRE: 'pw'}}); if (r.status !== 401) throw new Error('baslik yok');
""", encoding="utf-8")
    (tmp_path / "package.json").write_text('{"type":"module"}')
    r = subprocess.run(["node", str(js)], capture_output=True, text=True)
    assert r.returncode == 0, r.stderr
