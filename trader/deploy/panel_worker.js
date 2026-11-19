// Trader panosu kilidi: tüm istekler önce buradan geçer. Koruma Cloudflare Access ile (kullanıcı kararı 19 Kasım 2026:
// pano parolası kaldırıldı). Access, panoya giden her isteğe imzalı bir JWT ekler (Cf-Access-Jwt-Assertion); bu Worker o
// JWT'yi takımın açık anahtarlarıyla (RS256) doğrular. JWT yok/geçersizse HER İSTEK 403 (fail-closed): Access kapalıyken
// ya da yanlış kurulduysa pano açıkta kalmaz, yalnız kapanır.
// Kaynak: 1L3A projesinin deploy/pano_worker.js dosyasından uyarlandı (kullanıcının kendi kodu; THIRD_PARTY_NOTICES.md'ye bakın).
// Parolasız yayın seçeneği/bayrağı YOKTUR; yalnız /rejim.json ve /gunluk_ozet_v1.json (GET/HEAD) herkese açıktır.
const ACCESS_TAKIM = "slmgncortak";        // Cloudflare Zero Trust takım adı (<takim>.cloudflareaccess.com)
const SERTIFIKA_S = 3600;                  // açık anahtar önbelleği (sn)
let _anahtarlar = { zaman: 0, takim: "", liste: [] };

function b64url(s) {
  const t = s.replace(/-/g, "+").replace(/_/g, "/");
  const bin = atob(t + "=".repeat((4 - (t.length % 4)) % 4));
  return Uint8Array.from(bin, (c) => c.charCodeAt(0));
}

async function anahtarlar(takim, getir) {
  const simdi = Math.floor(Date.now() / 1000);
  if (_anahtarlar.takim === takim && simdi - _anahtarlar.zaman < SERTIFIKA_S && _anahtarlar.liste.length) return _anahtarlar.liste;
  const r = await getir(`https://${takim}.cloudflareaccess.com/cdn-cgi/access/certs`);
  if (!r.ok) throw new Error("sertifika alinamadi");
  const j = await r.json();
  const liste = [];
  for (const k of (j.keys || [])) {
    if (k.kty !== "RSA") continue;
    liste.push({ kid: k.kid, anahtar: await crypto.subtle.importKey("jwk", k, { name: "RSASSA-PKCS1-v1_5", hash: "SHA-256" },
      false, ["verify"]) });
  }
  _anahtarlar = { zaman: simdi, takim, liste };
  return liste;
}

// Access JWT dogrulamasi: RS256 imza (takim anahtarlari), iss = takim adresi, exp/nbf; env.ACCESS_AUD verilmisse aud eslesmesi.
async function accessGecerli(istek, env, getir) {
  const jwt = istek.headers.get("Cf-Access-Jwt-Assertion") || "";
  const p = jwt.split(".");
  if (p.length !== 3) return false;
  try {
    const bas = JSON.parse(new TextDecoder().decode(b64url(p[0])));
    const yuk = JSON.parse(new TextDecoder().decode(b64url(p[1])));
    if (bas.alg !== "RS256") return false;
    const takim = (typeof env.ACCESS_TAKIM === "string" && env.ACCESS_TAKIM) || ACCESS_TAKIM;
    const simdi = Math.floor(Date.now() / 1000);
    if (yuk.iss !== `https://${takim}.cloudflareaccess.com`) return false;
    if (typeof yuk.exp !== "number" || yuk.exp <= simdi) return false;
    if (typeof yuk.nbf === "number" && yuk.nbf > simdi + 60) return false;
    if (typeof env.ACCESS_AUD === "string" && env.ACCESS_AUD) {
      const aud = Array.isArray(yuk.aud) ? yuk.aud : [yuk.aud];
      if (!aud.includes(env.ACCESS_AUD)) return false;
    }
    const veri = new TextEncoder().encode(p[0] + "." + p[1]);
    const imza = b64url(p[2]);
    for (const k of await anahtarlar(takim, getir)) {
      if (bas.kid && k.kid !== bas.kid) continue;
      if (await crypto.subtle.verify("RSASSA-PKCS1-v1_5", k.anahtar, imza, veri)) return true;
    }
    return false;
  } catch (_) {
    return false;
  }
}

function baslikEkle(yanit) {
  const h = new Headers(yanit.headers);
  h.set("Cache-Control", "no-store");
  h.set("X-Robots-Tag", "noindex");
  h.set("X-Content-Type-Options", "nosniff");
  h.set("Referrer-Policy", "no-referrer");
  h.delete("X-Frame-Options");   // 19 Kasim: orkestra kapisi iframe'i (CSP frame-ancestors yeterli)
  h.set("Strict-Transport-Security", "max-age=31536000");
  h.set("Content-Security-Policy",
    `default-src 'none'; style-src 'unsafe-inline'; script-src 'unsafe-inline'; img-src data:; base-uri 'none'; form-action 'none'; frame-ancestors 'self' https://orkestra-kapi.sselimgenc-c18.workers.dev`);
  return new Response(yanit.body, { status: yanit.status, statusText: yanit.statusText, headers: h });
}

function red() {
  return baslikEkle(new Response("Yetkisiz: bu pano Cloudflare Access ile korunur.", { status: 403 }));
}

export default {
  async fetch(istek, env) {
    // Rejim etiketi (parolasiz; yalniz GET/HEAD; icerik rejim etiketidir, bakiye/pozisyon/anahtar yok). Auth'tan ONCE.
    if ((istek.method === "GET" || istek.method === "HEAD") && new URL(istek.url).pathname === "/rejim.json") {
      const r = await env.ASSETS.fetch(istek);
      const h = new Headers(r.headers);
      h.set("Content-Type", "application/json");
      h.set("Cache-Control", "no-store");
      h.set("Access-Control-Allow-Origin", "*");
      return baslikEkle(new Response(r.body, { status: r.status, statusText: r.statusText, headers: h }));
    }
    // ML gunluk ozeti (ortak.gunluk_ozet.v1; parolasiz, yalniz GET/HEAD, rejim.json ile ayni kurallar). Auth'tan ONCE.
    if ((istek.method === "GET" || istek.method === "HEAD") && new URL(istek.url).pathname === "/gunluk_ozet_v1.json") {
      const r = await env.ASSETS.fetch(istek);
      const h = new Headers(r.headers);
      h.set("Content-Type", "application/json");
      h.set("Cache-Control", "no-store");
      h.set("Access-Control-Allow-Origin", "*");
      return baslikEkle(new Response(r.body, { status: r.status, statusText: r.statusText, headers: h }));
    }
    // Panonun geri kalani: yalniz gecerli Cloudflare Access JWT'si ile (fail-closed).
    if (!(await accessGecerli(istek, env, (u) => fetch(u)))) return red();
    return baslikEkle(await env.ASSETS.fetch(istek));
  },
};
