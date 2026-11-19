"""Pano Worker'i: orkestra kapisi iframe'inde parola formu (Basic Auth penceresi capraz-site iframe'de acilmaz)."""
import shutil
import subprocess
from pathlib import Path

import pytest

DEPLOY = Path(__file__).resolve().parents[1] / "deploy"


@pytest.mark.skipif(shutil.which("node") is None, reason="node yok")
def test_iframe_giris_formu_ve_cerez(tmp_path):
    js = tmp_path / "t.mjs"
    js.write_text(f"""import w from {str(DEPLOY / 'panel_worker.js')!r};
const env = {{PANEL_SIFRE: 'pw', ASSETS: {{fetch: async () => new Response('pano', {{headers: {{'Content-Type': 'text/html'}}}})}}}};
const ok = (c, m) => {{ if (!c) throw new Error(m); }};
const ifr = {{'Sec-Fetch-Dest': 'iframe'}};
// iframe, cerezsiz: form (401, Basic penceresi yok, form-action 'self')
let r = await w.fetch(new Request('https://x/', {{headers: ifr}}), env);
ok(r.status === 401 && !r.headers.get('WWW-Authenticate'), 'iframe form ' + r.status);
ok((await r.text()).includes('action="/giris"'), 'form yok');
ok(r.headers.get('Content-Security-Policy').includes("form-action 'self'"), 'csp form');
ok(r.headers.get('Content-Security-Policy').includes('frame-ancestors') && !r.headers.get('X-Frame-Options'), 'frame');
// ust duzey: Basic Auth aynen
r = await w.fetch(new Request('https://x/'), env);
ok(r.status === 401 && r.headers.get('WWW-Authenticate').startsWith('Basic'), 'ust duzey basic');
ok(r.headers.get('Content-Security-Policy').includes("form-action 'none'"), 'normal csp');
// yanlis parola: form tekrar, cerez yok
const post = (s) => new Request('https://x/giris', {{method: 'POST', headers: ifr, body: new URLSearchParams({{sifre: s}})}});
r = await w.fetch(post('yanlis'), env);
ok(r.status === 401 && !r.headers.get('Set-Cookie') && (await r.text()).includes('yanlış'), 'yanlis parola');
// dogru parola: 303 + bolumlenmis cerez; cerezle iframe icerik gorur
r = await w.fetch(post('pw'), env);
ok(r.status === 303 && r.headers.get('Location') === '/', 'yonlendirme ' + r.status);
const c = r.headers.get('Set-Cookie');
ok(c.includes('Partitioned') && c.includes('SameSite=None') && c.includes('HttpOnly'), 'cerez ' + c);
r = await w.fetch(new Request('https://x/', {{headers: {{...ifr, Cookie: c.split(';')[0]}}}}), env);
ok(r.status === 200 && (await r.text()) === 'pano', 'cerezle icerik');
// acik yollar degismedi; sifre yoksa her sey kapali
for (const p of ['/rejim.json', '/gunluk_ozet_v1.json']) {{
  r = await w.fetch(new Request('https://x' + p, {{headers: ifr}}), env); ok(r.status === 200, 'acik yol ' + p);
}}
r = await w.fetch(post('pw'), {{ASSETS: env.ASSETS}}); ok(r.status === 401, 'secret yokken giris');
""", encoding="utf-8")
    (tmp_path / "package.json").write_text('{"type":"module"}')
    r = subprocess.run(["node", str(js)], capture_output=True, text=True)
    assert r.returncode == 0, r.stderr
