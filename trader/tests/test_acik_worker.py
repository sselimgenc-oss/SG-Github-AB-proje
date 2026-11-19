"""Herkese acik ikiz Worker: yalniz rejim.json ve gunluk_ozet_v1.json (GET/HEAD); pano verisi bu Worker'a yuklenmez."""
import shutil
import subprocess
from pathlib import Path

import pytest

DEPLOY = Path(__file__).resolve().parents[1] / "deploy"


@pytest.mark.skipif(shutil.which("node") is None, reason="node yok")
def test_acik_worker_yalniz_iki_dosya(tmp_path):
    js = tmp_path / "t.mjs"
    js.write_text(f"""import w from {str(DEPLOY / 'acik_worker.js')!r};
const ok = (c, m) => {{ if (!c) throw new Error(m); }};
const env = {{ASSETS: {{fetch: async () => new Response('{{"a":1}}')}}}};
const rq = (p, m) => new Request('https://x' + p, {{method: m || 'GET'}});
for (const p of ['/rejim.json', '/gunluk_ozet_v1.json']) for (const m of ['GET', 'HEAD']) {{
  const r = await w.fetch(rq(p, m), env);
  ok(r.status === 200 && r.headers.get('Content-Type') === 'application/json' && r.headers.get('Access-Control-Allow-Origin') === '*'
     && r.headers.get('Cache-Control') === 'no-store', p + m);
}}
for (const p of ['/', '/index.html', '/api/status', '/rejim.jsonx', '/x/rejim.json']) {{
  const r = await w.fetch(rq(p), env); ok(r.status === 404, 'kapali olmali ' + p);
}}
ok((await w.fetch(rq('/rejim.json', 'POST'), env)).status === 404, 'POST');
""", encoding="utf-8")
    (tmp_path / "package.json").write_text('{"type":"module"}')
    r = subprocess.run(["node", str(js)], capture_output=True, text=True)
    assert r.returncode == 0, r.stderr


def test_yayin_betigi_acik_workeri_yalniz_iki_dosyayla_kurar():
    t = (DEPLOY / "panel_yayinla.sh").read_text(encoding="utf-8")
    assert subprocess.run(["bash", "-n", str(DEPLOY / "panel_yayinla.sh")], capture_output=True).returncode == 0
    blok = t[t.index('mkdir -p "$gecici/acik/site"'):]
    assert "for f in rejim.json gunluk_ozet_v1.json; do" in blok and "index.html" not in blok
    assert '"name": "$ad-acik"' in blok and '"main": "acik_worker.js"' in blok
    assert "UYARI: acik yayin" in blok and "exit 1" not in blok          # pano yayinini bozmaz
    assert t.index('echo "panel yayimlandi') < t.index('mkdir -p "$gecici/acik/site"')
