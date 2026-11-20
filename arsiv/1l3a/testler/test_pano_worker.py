"""Pano Worker kilidi (Cloudflare Access JWT, node ile) ve pano_yayinla.sh."""
import base64
import json
import os
import shutil
import stat
import subprocess
from pathlib import Path

import pytest

KOK = Path(__file__).resolve().parent.parent
WORKER = KOK / "deploy" / "pano_worker.js"
ACIK_WORKER = KOK / "deploy" / "pano_acik_worker.js"
BETIK = KOK / "deploy" / "pano_yayinla.sh"

NODE_KOD = r"""
import { pathToFileURL } from "node:url";
const href = pathToFileURL(process.argv[1]).href;
const TAKIM = "slmgncortak";
const ISS = "https://" + TAKIM + ".cloudflareaccess.com";
const b64 = (x) => Buffer.from(x).toString("base64url");
const sim = () => Math.floor(Date.now() / 1000);
async function anahtarUret(kid) {
  const k = await crypto.subtle.generateKey({ name: "RSASSA-PKCS1-v1_5", modulusLength: 2048, publicExponent: new Uint8Array([1, 0, 1]), hash: "SHA-256" }, true, ["sign", "verify"]);
  const jwk = await crypto.subtle.exportKey("jwk", k.publicKey);
  return { kid, ozel: k.privateKey, jwk: { ...jwk, kid, alg: "RS256", use: "sig" } };
}
async function jwtYap(k, yuk, { kid = k.kid, bozImza = false } = {}) {
  const p = b64(JSON.stringify({ alg: "RS256", kid })) + "." + b64(JSON.stringify(yuk));
  let imza = Buffer.from(await crypto.subtle.sign("RSASSA-PKCS1-v1_5", k.ozel, new TextEncoder().encode(p)));
  if (bozImza) imza[0] ^= 0xff;
  return p + "." + imza.toString("base64url");
}
const gecerliYuk = (ek = {}) => ({ iss: ISS, aud: ["AUD123"], exp: sim() + 600, iat: sim(), ...ek });
// sahte sertifika ucu: ayarlar.keys / ayarlar.hata; çağrı sayısı tutulur
function sahteFetch(durum) {
  globalThis.fetch = async (u) => {
    durum.cagri.push(String(u));
    if (durum.hata) return new Response("hata", { status: 500 });
    return new Response(JSON.stringify({ keys: durum.keys }), { status: 200, headers: { "Content-Type": "application/json" } });
  };
}
let sayac = 0;
async function yeniWorker() { return (await import(href + "?n=" + sayac++)).default; }   // her senaryoya taze modül (önbellek sıfır)
const assets = { fetch: async () => new Response("<html>pano</html>", { status: 200, headers: { "X-Frame-Options": "DENY" } }) };
async function dene(w, env, { jwt = null, cerez = null, yol = "/" } = {}) {
  const h = {};
  if (jwt) h["Cf-Access-Jwt-Assertion"] = jwt;
  if (cerez) h["Cookie"] = "a=b; CF_Authorization=" + cerez + "; c=d";
  const r = await w.fetch(new Request("https://x.test" + yol, { headers: h }), env);
  return { durum: r.status, cache: r.headers.get("Cache-Control"), robots: r.headers.get("X-Robots-Tag"),
           xfo: r.headers.get("X-Frame-Options"), csp: r.headers.get("Content-Security-Policy"), www: r.headers.get("WWW-Authenticate"), govde: await r.text() };
}
const K = await anahtarUret("kid1");
const K2 = await anahtarUret("kid2");
const out = {};
{
  const d = { cagri: [], keys: [K.jwk] };
  sahteFetch(d);
  const w = await yeniWorker();
  const E = { ASSETS: assets };
  out.jwt_yok = await dene(w, E);
  out.dogru = await dene(w, E, { jwt: await jwtYap(K, gecerliYuk()) });
  out.dogru_cagri = d.cagri.length;
  out.dogru_url = d.cagri[0];
  await dene(w, E, { jwt: await jwtYap(K, gecerliYuk()) });
  out.onbellek_cagri = d.cagri.length;       // ikinci geçerli istek: önbellekten, yeni çekme yok
  out.bozuk_imza = await dene(w, E, { jwt: await jwtYap(K, gecerliYuk(), { bozImza: true }) });
  out.yanlis_iss = await dene(w, E, { jwt: await jwtYap(K, gecerliYuk({ iss: "https://baska.cloudflareaccess.com" })) });
  out.suresi_gecmis = await dene(w, E, { jwt: await jwtYap(K, gecerliYuk({ exp: sim() - 10 })) });
  out.nbf_gelecek = await dene(w, E, { jwt: await jwtYap(K, gecerliYuk({ nbf: sim() + 3600 })) });
  out.nbf_tolerans = await dene(w, E, { jwt: await jwtYap(K, gecerliYuk({ nbf: sim() + 30 })) });
  out.cerez = await dene(w, E, { cerez: await jwtYap(K, gecerliYuk()) });
  out.cerez_bozuk = await dene(w, E, { cerez: "abc.def.ghi" });
  out.coplu = await dene(w, E, { jwt: "not-a-jwt" });
  out.alg_none = await dene(w, E, { jwt: b64('{"alg":"none","kid":"kid1"}') + "." + b64(JSON.stringify(gecerliYuk())) + "." });
}
{
  const d = { cagri: [], keys: [K.jwk] };
  sahteFetch(d);
  const w = await yeniWorker();
  const E = { ASSETS: assets, ACCESS_AUD: "AUD123" };
  out.aud_ok = await dene(w, E, { jwt: await jwtYap(K, gecerliYuk()) });
  out.aud_tek_string = await dene(w, E, { jwt: await jwtYap(K, gecerliYuk({ aud: "AUD123" })) });
  out.aud_uyusmaz = await dene(w, { ...E, ACCESS_AUD: "BASKA" }, { jwt: await jwtYap(K, gecerliYuk()) });
  out.aud_yok_jwtde = await dene(w, E, { jwt: await jwtYap(K, gecerliYuk({ aud: undefined })) });
}
{
  const d = { cagri: [], keys: [K.jwk] };
  sahteFetch(d);
  const w = await yeniWorker();
  const E = { ASSETS: assets };
  await dene(w, E, { jwt: await jwtYap(K, gecerliYuk()) });          // önbellek: yalnız kid1
  d.keys = [K.jwk, K2.jwk];                                          // anahtar döndü
  const once = d.cagri.length;
  out.kid_taze = await dene(w, E, { jwt: await jwtYap(K2, gecerliYuk()) });
  out.kid_taze_cagri = d.cagri.length - once;
  const once2 = d.cagri.length;
  out.kid_hic_yok = await dene(w, E, { jwt: await jwtYap(await anahtarUret("kid9"), gecerliYuk()) });
  out.kid_hic_yok_cagri = d.cagri.length - once2;                    // tam bir taze çekme, döngü yok
}
{
  const d = { cagri: [], keys: [K.jwk], hata: true };
  sahteFetch(d);
  const w = await yeniWorker();
  out.sertifika_hata = await dene(w, { ASSETS: assets }, { jwt: await jwtYap(K, gecerliYuk()) });
}
{
  const d = { cagri: [], keys: [K.jwk] };
  sahteFetch(d);
  const w = await yeniWorker();
  const jwt = await jwtYap(K, gecerliYuk({ iss: "https://ozel.cloudflareaccess.com" }));
  out.takim_ozel = await dene(w, { ASSETS: assets, ACCESS_TAKIM: "ozel" }, { jwt });
  out.takim_ozel_url = d.cagri[0];
}
console.log(JSON.stringify(out));
const OZET = "/gunluk_ozet_v1.json";
const ozetAssets = { fetch: async () => new Response('{"sema":"ortak.gunluk_ozet.v1"}', { status: 200, headers: { "Content-Type": "text/plain" } }) };
async function yol(w, path, method = "GET") {
  const r = await w.fetch(new Request("https://x.test" + path, { method }), { ASSETS: ozetAssets });
  return { durum: r.status, tip: r.headers.get("Content-Type"), cache: r.headers.get("Cache-Control"), cors: r.headers.get("Access-Control-Allow-Origin"), govde: await r.text() };
}
{
  const d = { cagri: [], keys: [K.jwk] };
  sahteFetch(d);
  const w = await yeniWorker();
  const acik = {
    tam: await yol(w, OZET),
    sorgu: await yol(w, OZET + "?x=1"),
    bos_sorgu: await yol(w, OZET + "?"),
    alt_yol: await yol(w, OZET + "/"),
    nokta: await yol(w, OZET + "/../index.html"),
    buyuk: await yol(w, "/Gunluk_Ozet_v1.json"),
    buyuk2: await yol(w, "/GUNLUK_OZET_V1.JSON"),
    kodlu: await yol(w, "/gunluk_ozet_v1%2Ejson"),
    kodlu2: await yol(w, "/%67unluk_ozet_v1.json/x"),
    kok: await yol(w, "/"),
    index: await yol(w, "/index.html"),
    post: await yol(w, OZET, "POST"),
  };
  acik.cagri = d.cagri.length;     // JWT yok: sertifika çekilmeden 403
  console.log("ACIK" + JSON.stringify(acik));
}
{
  const hrefA = pathToFileURL(process.argv[2]).href;
  const wa = (await import(hrefA)).default;
  const aa = { fetch: async (r) => new Response('{"sema":"ortak.gunluk_ozet.v1"}', { status: 200, headers: { "Content-Type": "text/plain" } }) };
  const ac = {};
  for (const [k, p, m] of [["tam", OZET, "GET"], ["sorgu", OZET + "?x=1", "GET"], ["bos_sorgu", OZET + "?", "GET"], ["alt_yol", OZET + "/", "GET"],
      ["nokta", OZET + "/../index.html", "GET"], ["buyuk", "/Gunluk_Ozet_v1.json", "GET"], ["kok", "/", "GET"], ["index", "/index.html", "GET"],
      ["rejim", "/rejim.json", "GET"], ["post", OZET, "POST"], ["head", OZET, "HEAD"]]) {
    const r = await wa.fetch(new Request("https://x.test" + p, { method: m }), { ASSETS: aa });
    ac[k] = { durum: r.status, tip: r.headers.get("Content-Type"), cache: r.headers.get("Cache-Control"), cors: r.headers.get("Access-Control-Allow-Origin"),
              robots: r.headers.get("X-Robots-Tag"), govde: await r.text() };
  }
  console.log("ACIKW" + JSON.stringify(ac));
}
"""


@pytest.fixture(scope="module")
def sonuc():
    if not shutil.which("node"):
        pytest.skip("node yok")
    r = subprocess.run(["node", "--input-type=module", "-e", NODE_KOD, str(WORKER), str(ACIK_WORKER)],
                       capture_output=True, text=True, timeout=120)
    assert r.returncode == 0, r.stderr
    satir = [x for x in r.stdout.splitlines() if x.strip()]
    sonuc = json.loads(next(x for x in satir if x.startswith("{")))
    sonuc["acik"] = json.loads(next(x for x in satir if x.startswith("ACIK{"))[4:])
    sonuc["acikw"] = json.loads(next(x for x in satir if x.startswith("ACIKW"))[5:])
    return sonuc


def test_dogru_jwt_200(sonuc):
    assert sonuc["dogru"]["durum"] == 200 and "pano" in sonuc["dogru"]["govde"]
    assert sonuc["dogru_cagri"] == 1
    assert sonuc["dogru_url"] == "https://slmgncortak.cloudflareaccess.com/cdn-cgi/access/certs"
    assert sonuc["onbellek_cagri"] == 1          # anahtarlar önbellekten


def test_cerezden_jwt_200(sonuc):
    assert sonuc["cerez"]["durum"] == 200 and "pano" in sonuc["cerez"]["govde"]


def test_nbf_tolerans(sonuc):
    assert sonuc["nbf_tolerans"]["durum"] == 200     # 30 sn ileri: 60 sn tolerans içinde
    assert sonuc["nbf_gelecek"]["durum"] == 403


@pytest.mark.parametrize("k", ["jwt_yok", "bozuk_imza", "yanlis_iss", "suresi_gecmis", "cerez_bozuk", "coplu",
                               "alg_none", "aud_uyusmaz", "aud_yok_jwtde", "sertifika_hata", "kid_hic_yok"])
def test_reddedilenler_403(sonuc, k):
    assert sonuc[k]["durum"] == 403
    assert "pano" not in sonuc[k]["govde"]
    assert sonuc[k]["www"] is None                   # Basic Auth yok


def test_aud_tanimli_ve_uyusan_200(sonuc):
    assert sonuc["aud_ok"]["durum"] == 200 and sonuc["aud_tek_string"]["durum"] == 200


def test_kid_bulunamazsa_taze_cekme(sonuc):
    assert sonuc["kid_taze"]["durum"] == 200 and sonuc["kid_taze_cagri"] == 1
    assert sonuc["kid_hic_yok_cagri"] == 1


def test_takim_adi_degisebilir(sonuc):
    assert sonuc["takim_ozel"]["durum"] == 200
    assert sonuc["takim_ozel_url"] == "https://ozel.cloudflareaccess.com/cdn-cgi/access/certs"


def test_basliklar_frame(sonuc):
    for k in ("dogru", "jwt_yok", "bozuk_imza", "sertifika_hata"):
        assert sonuc[k]["cache"] == "private, no-store"
        assert sonuc[k]["robots"] == "noindex"
        assert sonuc[k]["xfo"] is None
        assert "frame-ancestors 'self' https://orkestra-kapi.sselimgenc-c18.workers.dev" in sonuc[k]["csp"]


@pytest.mark.parametrize("k", ["tam", "sorgu", "bos_sorgu", "alt_yol", "nokta", "buyuk", "buyuk2", "kodlu", "kodlu2", "kok", "index", "post"])
def test_ana_worker_ozet_dahil_her_yol_jwtsiz_403(sonuc, k):
    a = sonuc["acik"][k]
    assert a["durum"] == 403 and "gunluk_ozet" not in a["govde"] and a["cors"] is None
    assert sonuc["acik"]["cagri"] == 0


def test_acik_worker_yalniz_tam_yol_200(sonuc):
    a = sonuc["acikw"]["tam"]
    assert a["durum"] == 200 and "gunluk_ozet.v1" in a["govde"]
    assert a["tip"] == "application/json" and a["cache"] == "no-store" and a["cors"] == "*" and a["robots"] == "noindex"


@pytest.mark.parametrize("k", ["sorgu", "bos_sorgu", "alt_yol", "nokta", "buyuk", "kok", "index", "rejim", "post", "head"])
def test_acik_worker_diger_her_sey_404(sonuc, k):
    a = sonuc["acikw"][k]
    assert a["durum"] in (404, 405) and "gunluk_ozet" not in a["govde"] and a["cors"] is None


def _sahte_wrangler(tmp_path):
    bin_ = tmp_path / "bin"
    bin_.mkdir(exist_ok=True)
    log = tmp_path / "cagrilar.log"
    w = bin_ / "wrangler"
    w.write_text(f'#!/usr/bin/env bash\necho "$@" >> {log}\nif [ "$1" = deploy ] && [ -d site ]; then K=site_kopya; W=wr.jsonc; case $PWD in */acik) K=acik_kopya; W=acik_wr.jsonc;; esac; rm -rf {tmp_path}/$K && cp -r site {tmp_path}/$K && cp wrangler.jsonc {tmp_path}/$W && cp *.js {tmp_path}/$K/ 2>/dev/null; fi\nif [ "$1 $2" = "secret put" ]; then cat > {tmp_path}/stdin.txt; fi\n[ "$1 $2" = "secret delete" ] && exit 1\nexit 0\n')
    w.chmod(w.stat().st_mode | stat.S_IXUSR)
    return bin_, log


def _calistir(tmp_path, **ek):
    bin_, log = _sahte_wrangler(tmp_path)
    pano = tmp_path / "pano.html"
    pano.write_text("<html></html>")
    env = {"PATH": f"{bin_}:{os.environ['PATH']}", "CLOUDFLARE_API_TOKEN": "t", "CLOUDFLARE_ACCOUNT_ID": "a",
           "PANO_DOSYA": str(pano), "PANO_SIFRE_HASH_DOSYA": str(tmp_path / "h" / "sifre.sha256")}
    env.update(ek)
    r = subprocess.run(["bash", str(BETIK)], env=env, capture_output=True, text=True, timeout=60)
    return r, log


def test_betik_sifresiz_yayinlar_secret_put_yok(tmp_path):
    """Basic Auth kalktı: PANO_SIFRE gerekmez; varsa yok sayılır (secret put yok)."""
    r, log = _calistir(tmp_path)
    assert r.returncode == 0, r.stderr
    cagri = log.read_text()
    assert "deploy" in cagri and "secret put" not in cagri and "secret delete" not in cagri
    r, log = _calistir(tmp_path)
    assert r.returncode == 0 and "secret put" not in log.read_text()
    assert not (tmp_path / "stdin.txt").exists()


def test_betik_eski_secret_bir_kez_silinmeye_calisilir_hata_yutulur(tmp_path):
    h = tmp_path / "h"
    h.mkdir()
    (h / "sifre.sha256").write_text("eski\n")
    r, log = _calistir(tmp_path)
    assert r.returncode == 0, r.stderr
    assert "secret delete PANO_SIFRE" in log.read_text()
    assert not (h / "sifre.sha256").exists()
    log.unlink()
    r, log = _calistir(tmp_path)
    assert "secret delete" not in log.read_text()


def test_betik_worker_yuklenir_ve_vars(tmp_path):
    r, _ = _calistir(tmp_path, ACCESS_AUD="abc123def", ACCESS_TAKIM="slmgncortak")
    assert r.returncode == 0, r.stderr
    kfg = json.loads((tmp_path / "wr.jsonc").read_text())
    assert kfg["main"] == "pano_worker.js" and kfg["assets"]["run_worker_first"] is True
    assert kfg["vars"] == {"ACCESS_AUD": "abc123def", "ACCESS_TAKIM": "slmgncortak"}
    r, _ = _calistir(tmp_path)
    assert "vars" not in json.loads((tmp_path / "wr.jsonc").read_text())


def test_betik_gecersiz_aud_reddedilir(tmp_path):
    r, log = _calistir(tmp_path, ACCESS_AUD='x"y')
    assert r.returncode != 0 and not log.exists()


def test_betik_kilitsiz_yayin(tmp_path):
    """PANO_KILITSIZ=1: Worker kilidi yüklenmez, secret put yok."""
    r, log = _calistir(tmp_path, PANO_KILITSIZ="1")
    assert r.returncode == 0, r.stderr
    cagri = log.read_text()
    assert "deploy" in cagri and "secret put" not in cagri
    assert "ŞİFRESİZ" in r.stdout


def test_betik_iki_yayin_ana_sitede_ozet_yok_dosya_yoksa_acik_atlanir(tmp_path):
    r, log = _calistir(tmp_path)
    assert r.returncode == 0 and (tmp_path / "site_kopya" / "index.html").exists()
    assert not (tmp_path / "site_kopya" / "gunluk_ozet_v1.json").exists()
    assert not (tmp_path / "acik_kopya").exists() and log.read_text().count("deploy") == 1       # dosya yok: açık yayın atlanır, hata yok
    assert "atlandı" in r.stdout
    (tmp_path / "gunluk_ozet_v1.json").write_text('{"sema": "ortak.gunluk_ozet.v1"}')           # pano.html ile aynı dizin
    log.unlink()
    r, log = _calistir(tmp_path)
    assert r.returncode == 0 and log.read_text().count("deploy") == 2
    assert not (tmp_path / "site_kopya" / "gunluk_ozet_v1.json").exists()                      # ana Worker'a kopyalanmaz
    assert (tmp_path / "acik_kopya" / "gunluk_ozet_v1.json").read_text() == '{"sema": "ortak.gunluk_ozet.v1"}'
    assert not (tmp_path / "acik_kopya" / "index.html").exists() and (tmp_path / "acik_kopya" / "pano_acik_worker.js").exists()
    kfg = json.loads((tmp_path / "acik_wr.jsonc").read_text())
    assert kfg["name"] == "1l3a-pano-acik" and kfg["main"] == "pano_acik_worker.js" and "vars" not in kfg
    r, _ = _calistir(tmp_path, PANO_ACIK_AD="ozel-acik")
    assert json.loads((tmp_path / "acik_wr.jsonc").read_text())["name"] == "ozel-acik"
    assert json.loads((tmp_path / "wr.jsonc").read_text())["name"] == "1l3a-pano"


def test_kilitsiz_kipte_ozet_ayri_worker(tmp_path):
    (tmp_path / "gunluk_ozet_v1.json").write_text("{}")
    r, log = _calistir(tmp_path, PANO_KILITSIZ="1")
    assert r.returncode == 0 and log.read_text().count("deploy") == 2
    assert "gunluk_ozet" not in (tmp_path / "site_kopya" / "_headers").read_text()
    assert (tmp_path / "acik_kopya" / "gunluk_ozet_v1.json").exists()
