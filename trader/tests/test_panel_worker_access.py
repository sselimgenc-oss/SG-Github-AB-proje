"""Pano Worker'i: 20 Kasim 2026 kullanici karari ile kilitsiz (parola/Access yok), yalniz okuma; guvenlik basliklari aynen."""
import shutil
import subprocess
from pathlib import Path

import pytest

DEPLOY = Path(__file__).resolve().parents[1] / "deploy"


@pytest.mark.skipif(shutil.which("node") is None, reason="node yok")
def test_pano_kilitsiz_yalniz_okuma(tmp_path):
    js = tmp_path / "t.mjs"
    js.write_text(f"""import w from {str(DEPLOY / 'panel_worker.js')!r};
const ok = (c, m) => {{ if (!c) throw new Error(m); }};
globalThis.fetch = async () => {{ throw new Error('dis istek yapilmamali'); }};
const env = {{ASSETS: {{fetch: async () => new Response('pano', {{headers: {{'Content-Type': 'text/html'}}}})}}}};
const rq = (p, m, h) => new Request('https://x' + p, {{method: m || 'GET', headers: h || {{}}}});
// JWT/oturum olmadan pano acilir; guvenlik basliklari, X-Frame-Options yok, CSP cerceve izni
let r = await w.fetch(rq('/'), env);
ok(r.status === 200 && (await r.text()) === 'pano', 'pano ' + r.status);
ok(r.headers.get('Cache-Control') === 'no-store' && !r.headers.get('X-Frame-Options'), 'basliklar');
ok(r.headers.get('Content-Security-Policy').includes("frame-ancestors 'self' https://orkestra-kapi.sselimgenc-c18.workers.dev"), 'csp');
ok(!r.headers.get('WWW-Authenticate') && !r.headers.get('Access-Control-Allow-Origin'), 'parola/CORS yok');
for (const p of ['/api/status', '/index.html']) {{ r = await w.fetch(rq(p, 'HEAD'), env); ok(r.status === 200, 'HEAD ' + p); }}
// eski Access basligi etkisiz (ne gerekli ne zararli)
r = await w.fetch(rq('/', 'GET', {{'Cf-Access-Jwt-Assertion': 'a.b.c'}}), env); ok(r.status === 200, 'eski baslik');
// yazma yontemleri kapali
for (const m of ['POST', 'PUT', 'PATCH', 'DELETE']) {{
  r = await w.fetch(rq('/', m), env); ok(r.status === 405 && r.headers.get('Allow') === 'GET, HEAD', m);
}}
r = await w.fetch(rq('/rejim.json', 'POST'), env); ok(r.status === 405, 'POST rejim');
// acik JSON yollari CORS ile (degismedi)
for (const p of ['/rejim.json', '/gunluk_ozet_v1.json']) for (const m of ['GET', 'HEAD']) {{
  r = await w.fetch(rq(p, m), env);
  ok(r.status === 200 && r.headers.get('Access-Control-Allow-Origin') === '*' && r.headers.get('Content-Type') === 'application/json', p + m);
}}
""", encoding="utf-8")
    (tmp_path / "package.json").write_text('{"type":"module"}')
    r = subprocess.run(["node", str(js)], capture_output=True, text=True)
    assert r.returncode == 0, r.stderr
