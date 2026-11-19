"""Pano Worker'i: Cloudflare Access JWT dogrulamasi (parola yok; 19 Kasim kullanici karari). Fail-closed davranis."""
import shutil
import subprocess
from pathlib import Path

import pytest

DEPLOY = Path(__file__).resolve().parents[1] / "deploy"


@pytest.mark.skipif(shutil.which("node") is None, reason="node yok")
def test_access_jwt_fail_closed(tmp_path):
    js = tmp_path / "t.mjs"
    js.write_text(f"""import w from {str(DEPLOY / 'panel_worker.js')!r};
const ok = (c, m) => {{ if (!c) throw new Error(m); }};
const enc = (o) => Buffer.from(typeof o === 'string' ? o : JSON.stringify(o)).toString('base64url');
const kp = await crypto.subtle.generateKey({{name: 'RSASSA-PKCS1-v1_5', modulusLength: 2048, publicExponent: new Uint8Array([1, 0, 1]),
  hash: 'SHA-256'}}, true, ['sign', 'verify']);
const pub = {{...(await crypto.subtle.exportKey('jwk', kp.publicKey)), kid: 'k1'}};
const yabanci = await crypto.subtle.generateKey({{name: 'RSASSA-PKCS1-v1_5', modulusLength: 2048,
  publicExponent: new Uint8Array([1, 0, 1]), hash: 'SHA-256'}}, true, ['sign', 'verify']);
let certCagri = 0;
globalThis.fetch = async (u) => {{ certCagri++;
  ok(u === 'https://slmgncortak.cloudflareaccess.com/cdn-cgi/access/certs', 'sertifika adresi ' + u);
  return new Response(JSON.stringify({{keys: [pub]}}), {{headers: {{'Content-Type': 'application/json'}}}}); }};
const simdi = Math.floor(Date.now() / 1000);
async function jwt(yuk, anahtar = kp.privateKey, bas = {{alg: 'RS256', kid: 'k1'}}) {{
  const g = enc(bas) + '.' + enc(yuk);
  const s = await crypto.subtle.sign('RSASSA-PKCS1-v1_5', anahtar, new TextEncoder().encode(g));
  return g + '.' + Buffer.from(s).toString('base64url');
}}
const iyi = {{iss: 'https://slmgncortak.cloudflareaccess.com', aud: ['AUD1'], exp: simdi + 600, nbf: simdi - 5}};
const env = {{ASSETS: {{fetch: async () => new Response('pano', {{headers: {{'Content-Type': 'text/html'}}}})}}}};
const rq = (p, t, m) => new Request('https://x' + p, {{method: m || 'GET', headers: t ? {{'Cf-Access-Jwt-Assertion': t}} : {{}}}});
// gecerli JWT -> icerik, guvenlik basliklari, X-Frame-Options yok
let r = await w.fetch(rq('/', await jwt(iyi)), env);
ok(r.status === 200 && (await r.text()) === 'pano', 'gecerli jwt ' + r.status);
ok(r.headers.get('Cache-Control') === 'no-store' && !r.headers.get('X-Frame-Options'), 'basliklar');
ok(r.headers.get('Content-Security-Policy').includes('frame-ancestors') && !r.headers.get('WWW-Authenticate'), 'csp/parola yok');
// fail-closed: baslik yok, bozuk, yanlis imza, yanlis iss, suresi dolmus, alg none, aud uyusmaz
const kotu = [
  ['yok', undefined], ['bozuk', 'a.b'], ['cop', 'x.y.z'],
  ['yanlis imza', await jwt(iyi, yabanci.privateKey)],
  ['yanlis iss', await jwt({{...iyi, iss: 'https://baska.cloudflareaccess.com'}})],
  ['sure', await jwt({{...iyi, exp: simdi - 1}})],
  ['nbf', await jwt({{...iyi, nbf: simdi + 3600}})],
  ['alg none', enc({{alg: 'none'}}) + '.' + enc(iyi) + '.'],
];
for (const [ad, t] of kotu) {{ r = await w.fetch(rq('/api/status', t), env); ok(r.status === 403, ad + ' ' + r.status); }}
r = await w.fetch(rq('/', await jwt(iyi)), {{...env, ACCESS_AUD: 'BASKA'}}); ok(r.status === 403, 'aud');
r = await w.fetch(rq('/', await jwt(iyi)), {{...env, ACCESS_AUD: 'AUD1'}}); ok(r.status === 200, 'aud esit');
ok(certCagri === 1, 'sertifika onbellegi ' + certCagri);
// acik yollar JWT'siz (yalniz GET/HEAD); benzer yollar ve POST kapali
for (const p of ['/rejim.json', '/gunluk_ozet_v1.json']) for (const m of ['GET', 'HEAD']) {{
  r = await w.fetch(rq(p, undefined, m), env);
  ok(r.status === 200 && r.headers.get('Access-Control-Allow-Origin') === '*', 'acik ' + p + m);
}}
for (const p of ['/rejim.jsonx', '/gunluk_ozet_v1.json/x']) {{ r = await w.fetch(rq(p), env); ok(r.status === 403, 'benzer ' + p); }}
r = await w.fetch(rq('/rejim.json', undefined, 'POST'), env); ok(r.status === 403, 'POST');
""", encoding="utf-8")
    (tmp_path / "package.json").write_text('{"type":"module"}')
    r = subprocess.run(["node", str(js)], capture_output=True, text=True)
    assert r.returncode == 0, r.stderr
