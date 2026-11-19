"""Panel sunucu degismezleri: bind, yontemler, Host, yol, basliklar, ag yasagi, semafor, zaman asimi."""
import re
import threading
import time
from pathlib import Path

import pytest

from panel_support import Env, Running
from trader_panel import server as S
from trader_panel.data import ConfigError, load_config

STATIC = Path(S.STATIC_DIR)


@pytest.fixture(scope="module")
def env(tmp_path_factory):
    e = Env(tmp_path_factory.mktemp("panel"))
    yield e
    e.close()


@pytest.fixture(scope="module")
def run(env):
    r = Running(env)
    yield r
    r.stop()


def test_binds_loopback_only(run):
    assert run.srv.server_address[0] == "127.0.0.1"


def test_config_rejects_other_host_and_unknown_keys(env, tmp_path):
    import json
    raw = json.loads(env.cfg_path.read_text())
    for bad in ({"host": "0.0.0.0"}, {"host": "::"}, {"port": 0}, {"port": 70000}, {"max_concurrent": 17}, {"x": 1}):
        p = tmp_path / "bad.json"
        p.write_text(json.dumps({**raw, **bad}))
        with pytest.raises(ConfigError):
            load_config(p)
    assert load_config(env.cfg_path).port == raw["port"]
    assert load_config(Path(__file__).resolve().parent.parent / "config/panel.json").port == 8787


@pytest.mark.parametrize("method", ["POST", "PUT", "DELETE", "PATCH", "OPTIONS"])
def test_non_get_is_405(run, method):
    st, hdr, _ = run.req("/api/status", method)
    assert st == 405 and "GET" in hdr["Allow"]


def test_head_ok_without_body(run):
    st, hdr, body = run.req("/api/status", "HEAD", raw=True)
    assert st == 200 and body == b""


@pytest.mark.parametrize("host", ["evil.example", "127.0.0.1:1", "127.0.0.1", "localhost", "[::1]:8787", ""])
def test_bad_host_is_400(run, host):
    st, _, j = run.req("/api/status", host=host)
    assert st == 400 and j["code"] == "host_gecersiz"


def test_localhost_host_ok(run):
    st, _, _ = run.req("/healthz", host=f"localhost:{run.port}")
    assert st == 200


@pytest.mark.parametrize("path", ["/yok", "/static/../data.py", "/static/%2e%2e/data.py", "/static/panel.css/../../x",
                                  "/..%2f..%2fetc/passwd", "/static/", "/api", "//etc/passwd"])
def test_unknown_or_traversal_is_404(run, path):
    st, _, _ = run.req(path)
    assert st == 404


def test_security_headers_on_all_responses(run):
    for path in ("/", "/static/panel.js", "/api/status", "/yok"):
        _, hdr, _ = run.req(path, raw=True)
        assert hdr["Content-Security-Policy"] == "default-src 'self'; connect-src 'self'; img-src 'self' data:; frame-ancestors 'none'"
        assert hdr["X-Content-Type-Options"] == "nosniff" and hdr["Referrer-Policy"] == "no-referrer"
        assert hdr["Cache-Control"] == "no-store"
    st, hdr, _ = run.req("/api/status", method="POST", raw=True)
    assert hdr["Content-Security-Policy"].startswith("default-src 'self'")


def test_static_served_from_fixed_map(run):
    st, hdr, body = run.req("/", raw=True)
    assert st == 200 and b"/static/panel.js" in body and "text/html" in hdr["Content-Type"]
    assert run.req("/static/panel.css", raw=True)[0] == 200


def test_no_external_url_in_static_assets():
    pat = re.compile(r"https?://|//cdn|@import\s+url\(|<link[^>]+href=[\"']?https?|url\(\s*[\"']?(?!data:)", re.I)
    files = [p for p in STATIC.iterdir() if p.is_file()]
    assert {p.name for p in files} >= {"index.html", "panel.css", "panel.js"}
    for p in files:
        t = p.read_text(encoding="utf-8")
        assert not pat.search(t), p.name
        assert "<script src=\"http" not in t and "src=\"//" not in t
    idx = (STATIC / "index.html").read_text(encoding="utf-8")
    assert "<script>" not in idx and "onclick=" not in idx           # satir ici betik yok (CSP uyumu)
    assert "innerHTML" not in (STATIC / "panel.js").read_text(encoding="utf-8").replace("innerHTML yok", "")
    assert "default-src 'self'" in S.CSP


def test_static_sources_and_copyright_notes():
    assert "pano.py" in (STATIC / "panel.css").read_text(encoding="utf-8").splitlines()[0]
    assert "pano.py" in (STATIC / "panel.js").read_text(encoding="utf-8")[:400]


def test_semaphore_limits_to_eight(env):
    r = Running(env, cache_s=0)
    gate, lock = threading.Event(), threading.Lock()
    state = {"cur": 0, "max": 0}

    def slow():
        with lock:
            state["cur"] += 1
            state["max"] = max(state["max"], state["cur"])
        gate.wait(5)
        with lock:
            state["cur"] -= 1
        return {"ok": True}
    r.data.system = slow
    res = []
    ts = [threading.Thread(target=lambda: res.append(r.req("/api/system")[0])) for _ in range(12)]
    for t in ts:
        t.start()
    time.sleep(2.5)                         # 8 ici, 4 bekleyen semafor bekleme suresini (1 sn) asip 503
    gate.set()
    for t in ts:
        t.join(10)
    r.stop()
    assert state["max"] == 8
    assert sorted(res) == [200] * 8 + [503] * 4


def test_request_timeout(env):
    r = Running(env, cache_s=0, request_timeout_s=0.5)
    r.data.system = lambda: (time.sleep(1.5), {"ok": True})[1]
    t0 = time.monotonic()
    st, _, j = r.req("/api/system")
    assert st == 503 and j["code"] == "zaman_asimi" and time.monotonic() - t0 < 1.4
    time.sleep(1.5)
    assert r.req("/healthz")[0] == 200       # surec ayakta
    r.stop()


def test_response_size_cap(env):
    r = Running(env, cache_s=0, max_response_bytes=1024)
    r.data.system = lambda: {"ok": True, "x": "a" * 5000}
    st, _, j = r.req("/api/system")
    assert st == 500 and j["code"] == "yanit_buyuk"
    r.stop()


def test_js_syntax_if_node_available():
    import shutil
    import subprocess
    if shutil.which("node") is None:
        pytest.skip("node yok")
    r = subprocess.run(["node", "--check", str(STATIC / "panel.js")], capture_output=True, text=True)
    assert r.returncode == 0, r.stderr
