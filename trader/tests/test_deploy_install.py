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


def test_feed_unit_and_engine_ordering():
    f = (DEPLOY / "trader-feed.service").read_text(encoding="utf-8")
    assert "-m trader_engine feed --config-dir config" in f
    assert "User=trader" in f and "Restart=always" in f
    assert re.search(r"^OnFailure=trader-health-fail@%n\.service", f, re.M)
    assert re.search(r"^MemoryMax=350M$", f, re.M) and re.search(r"^Nice=\d+", f, re.M)
    assert re.search(r"^ReadWritePaths=.*/opt/trader/var", f, re.M)
    e = (DEPLOY / "trader-engine@.service").read_text(encoding="utf-8")
    for key in ("ProtectSystem=strict", "NoNewPrivileges=true", "PrivateTmp=true", "ProtectHome=read-only"):
        assert key in f and key in e, key
    assert re.search(r"^After=.*trader-feed\.service", e, re.M) and re.search(r"^Wants=.*trader-feed\.service", e, re.M)


def test_install_enables_feed_before_engine_and_uninstall_covers_it():
    t = (DEPLOY / "install.sh").read_text(encoding="utf-8")
    assert t.index("enable_now trader-feed.service") < t.index("enable_now trader-engine@learner.service")
    u = (DEPLOY / "uninstall.sh").read_text(encoding="utf-8")
    assert "trader-feed.service" in u and "trader-*.service" in u


def _exec_lines():
    for u in UNITS:
        if u.suffix != ".service":
            continue
        for ln in u.read_text(encoding="utf-8").splitlines():
            m = re.match(r"(ExecStart|ExecStartPre)=-?(.*)", ln)
            if m:
                yield u.name, m.group(2)


def test_every_unit_exec_target_resolves():
    """`python3 -m X <altkomut>` modulu/alt komutu ve betik yollari gercekten var (feed alt komutu dahil)."""
    import importlib.util
    if True:
        from trader_engine import cli
        subcmds = set(cli.build_parser()._subparsers._group_actions[0].choices)
        seen_mod = 0
        for name, cmd in _exec_lines():
            toks = cmd.split()
            if "-m" in toks:
                i = toks.index("-m")
                mod = toks[i + 1]
                assert importlib.util.find_spec(mod) is not None, f"{name}: modul yok: {mod}"
                seen_mod += 1
                if mod == "trader_engine":
                    assert toks[i + 2] in subcmds, f"{name}: trader_engine alt komutu yok: {toks[i + 2]}"
                    if toks[i + 2] in ("feed", "rules-snapshot"):
                        from trader_engine.marketdata import feed as F
                        assert callable(getattr(F, "main" if toks[i + 2] == "feed" else "rules_snapshot_main"))
            for t in toks:
                m = re.match(r"/opt/trader/((?:scripts|config|src|docs)/[\w./-]+)", t)
                if m:
                    assert (ROOT / m.group(1)).exists(), f"{name}: {m.group(1)}"
        assert seen_mod >= 4


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
                        "trader-panel-publish.service", "trader-engine-retry@.service", "trader-counterfactual@.service",
                        "trader-oi.service", "trader-drift@.service",
                        "trader-engine-live.service", "trader-engine-env-retry@.service"}  # tetikleyici/sablon birimler (DD-9: canli birim yalniz --live ile, enable_now ile degil)
    for u in UNITS:
        if u.name == "trader-engine@.service":
            assert "trader-engine@learner.service" in enabled and "trader-engine@twin.service" in enabled
        elif u.name in deliberately_not:
            continue
        elif u.name == "trader-engine-retry@.timer":
            assert "trader-engine-retry@learner.timer" in enabled and "trader-engine-retry@twin.timer" in enabled
        elif u.name == "trader-engine-env-retry@.timer":      # DD-9: testnet ornegi etkin; live ornegi yalniz --live (systemctl enable --now)
            assert "enable_now trader-engine-env-retry@testnet.timer" in t and "enable --now trader-engine-env-retry@live.timer" in t
        elif u.name == "trader-drift@.timer":
            assert "trader-drift@learner.timer" in enabled and "trader-drift@twin.timer" in enabled
        elif u.name == "trader-counterfactual@.timer":
            assert "trader-counterfactual@learner.timer" in enabled and "trader-counterfactual@twin.timer" in enabled
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
    # veto: API anahtari VE HMAC (ayri dosya); ders: Anthropic anahtari VE Telegram anahtarlari
    assert re.search(r"has_value /etc/trader-veto\.env ANTHROPIC_API_KEY_VETO && has_value /etc/trader-veto-hmac\.env TRADER_VETO_HMAC_KEY", t)
    assert re.search(r'has_value /etc/trader-lesson\.env ANTHROPIC_API_KEY_LESSON && \[ "\$TG_OK" -eq 1 \]', t)


def test_twin_default_on_with_no_twin_opt_out():
    t = (DEPLOY / "install.sh").read_text(encoding="utf-8")
    assert re.search(r"^WITH_TWIN=1$", t, re.M)
    assert "--no-twin) WITH_TWIN=0" in t and "--with-twin) WITH_TWIN=1" in t      # eski secenek kabul edilir
    assert "HEALTH_BOTS" in t and "learner,twin" in t
    assert "HEALTH_BOTS=" in (DEPLOY / "trader-health.env.example").read_text(encoding="utf-8")


def test_install_sets_pause_bots_for_telegram():
    t = (DEPLOY / "install.sh").read_text(encoding="utf-8")
    assert "PAUSE_BOTS=${HEALTH_BOTS_VAL}" in t
    env = (DEPLOY / "trader-telegram.env.example").read_text(encoding="utf-8")
    for k in ("PAUSE_FILE=", "ENGINE_VAR_DIR=", "PAUSE_BOTS="):
        assert re.search(rf"^{k}", env, re.M)
    assert "WorkingDirectory=/opt/trader" in (DEPLOY / "trader-telegram.service").read_text(encoding="utf-8")


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


def test_engine_retry_units_and_install():
    s = (DEPLOY / "trader-engine-retry@.service").read_text(encoding="utf-8")
    tm = (DEPLOY / "trader-engine-retry@.timer").read_text(encoding="utf-8")
    e = (DEPLOY / "trader-engine@.service").read_text(encoding="utf-8")
    assert "RestartPreventExitStatus=7" in e                      # kapi hatasi hala 'failed' olur
    assert "Type=oneshot" in s and "User=root" in s and "engine_retry.py --bot %i" in s
    assert "OnUnitActiveSec=5min" in tm and "WantedBy=timers.target" in tm
    t = (DEPLOY / "install.sh").read_text(encoding="utf-8")
    assert "enable_now trader-engine-retry@learner.timer" in t
    assert re.search(r'if \[ "\$WITH_TWIN" -eq 1 \]; then enable_now trader-engine-retry@twin\.timer', t)
    u = (DEPLOY / "uninstall.sh").read_text(encoding="utf-8")
    assert "trader-*.timer" in u                                   # sablon zamanlayici da kaldirilir


def test_trader_slice_installed_and_removed():
    i = (DEPLOY / "install.sh").read_text(encoding="utf-8")
    u = (DEPLOY / "uninstall.sh").read_text(encoding="utf-8")
    assert (DEPLOY / "trader.slice").exists()
    assert 'render "$REL_DIR/deploy/trader.slice" "${UNIT_DIR}/trader.slice"' in i      # DD-9: sablonlar root sahipli surum dizininden
    assert i.index("trader.slice\"") < i.index("systemctl daemon-reload")
    assert 'rm -f "$UNIT_DIR/trader.slice"' in u
    assert "Slice=trader.slice" in i          # trader-fetch (systemd-run) de ayni slice'ta


def test_counterfactual_units_and_install():
    """Alinmayan sinyal gece isi (25a): sablon birim, 23:10 UTC (02:10 TSI), defter/market salt okunur, yalniz var/<bot> yazilabilir."""
    s = (DEPLOY / "trader-counterfactual@.service").read_text(encoding="utf-8")
    tm = (DEPLOY / "trader-counterfactual@.timer").read_text(encoding="utf-8")
    assert "Type=oneshot" in s and "Slice=trader.slice" in s and "User=trader" in s
    assert "counterfactual_run.py --bot %i --once" in s and "OnFailure=trader-health-fail@%n.service" in s
    assert re.search(r"^MemoryMax=128M$", s, re.M) and re.search(r"^Nice=\d+", s, re.M) and "NoNewPrivileges=true" in s
    assert "ProtectSystem=strict" in s and "ProtectHome=read-only" in s and "PrivateTmp=true" in s
    assert "EnvironmentFile" not in re.sub(r"#.*", "", s)                      # anahtar/token yok: ag ve API kullanmaz
    rw = re.search(r"^ReadWritePaths=(.*)$", s, re.M).group(1).split()
    assert rw == ["-/opt/trader/var/%i"]                                        # yalniz kendi bot dizini
    ro = re.search(r"^ReadOnlyPaths=(.*)$", s, re.M).group(1).split()
    assert "-/opt/trader/var/%i/ledger.sqlite" in ro and "-/opt/trader/var/market.sqlite" in ro
    assert "OnCalendar=*-*-* 23:10:00 UTC" in tm and "Persistent=true" in tm
    t = (DEPLOY / "install.sh").read_text(encoding="utf-8")
    assert "enable_now trader-counterfactual@learner.timer" in t
    assert re.search(r'if \[ "\$WITH_TWIN" -eq 1 \]; then enable_now trader-counterfactual@twin\.timer', t)
    assert (ROOT / "scripts/counterfactual_run.py").exists() and (ROOT / "docs/alinmayan-sinyal-spec.md").exists()
