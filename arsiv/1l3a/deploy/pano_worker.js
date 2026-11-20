// 1L3A pano kilidi: tüm istekler önce buradan geçer; geçerli Cloudflare Access JWT'si varsa statik pano döner.
// JWT: `Cf-Access-Jwt-Assertion` başlığı (yoksa `CF_Authorization` çerezi). Yok / geçersiz / sertifika çekilemedi => 403 (fail-closed).
// Takım adı env.ACCESS_TAKIM (varsayılan slmgncortak); env.ACCESS_AUD tanımlıysa aud o değeri içermeli (gizli değil, `vars`).
const VARSAYILAN_TAKIM = "slmgncortak";
const TOLERANS_SN = 60;
const ONBELLEK_MS = 10 * 60 * 1000;

// JWT'siz açık yol YOK: tüm yollar JWT ister. (Açık günlük özet ayrı Worker'da: pano_acik_worker.js.)
// Kod genel kalsın diye mekanizma duruyor; yol eklenirse harfi harfine eşleşir, sorgu dizesi yok, yalnız GET.
const ACIK_YOLLAR = [];

let anahtarOnbellek = { takim: null, anahtarlar: null, zaman: 0 };

function baslikEkle(yanit) {
  const h = new Headers(yanit.headers);
  h.set("Cache-Control", "private, no-store");
  h.set("X-Robots-Tag", "noindex");
  h.set("Content-Security-Policy", "frame-ancestors 'self' https://orkestra-kapi.sselimgenc-c18.workers.dev");   // tek pano kapısı (orkestratör) iframe ile açabilsin
  h.delete("X-Frame-Options");
  return new Response(yanit.body, { status: yanit.status, statusText: yanit.statusText, headers: h });
}

function red() {
  return baslikEkle(new Response("Yasak", { status: 403 }));
}

function b64urlBayt(s) {
  const b = s.replace(/-/g, "+").replace(/_/g, "/");
  const bin = atob(b + "=".repeat((4 - (b.length % 4)) % 4));
  return Uint8Array.from(bin, (c) => c.charCodeAt(0));
}

function b64urlJson(s) {
  return JSON.parse(new TextDecoder().decode(b64urlBayt(s)));
}

function jwtAl(istek) {
  const b = istek.headers.get("Cf-Access-Jwt-Assertion");
  if (b) return b.trim();
  const cerez = istek.headers.get("Cookie") || "";
  for (const parca of cerez.split(";")) {
    const i = parca.indexOf("=");
    if (i > 0 && parca.slice(0, i).trim() === "CF_Authorization") return parca.slice(i + 1).trim();
  }
  return null;
}

async function anahtarlariCek(takim) {
  const r = await fetch(`https://${takim}.cloudflareaccess.com/cdn-cgi/access/certs`);
  if (!r.ok) throw new Error("sertifika ucu " + r.status);
  const j = await r.json();
  if (!j || !Array.isArray(j.keys)) throw new Error("sertifika biçimi");
  anahtarOnbellek = { takim, anahtarlar: j.keys, zaman: Date.now() };
  return j.keys;
}

async function anahtarBul(takim, kid) {
  const taze = anahtarOnbellek.takim === takim && anahtarOnbellek.anahtarlar && Date.now() - anahtarOnbellek.zaman < ONBELLEK_MS;
  if (taze) {
    const k = anahtarOnbellek.anahtarlar.find((x) => x.kid === kid);
    if (k) return k;
  }
  const keys = await anahtarlariCek(takim);   // önbellek yok/eski ya da kid bulunamadı: bir kez taze çek
  return keys.find((x) => x.kid === kid) || null;
}

async function jwtGecerliMi(jwt, env) {
  try {
    const takim = typeof env.ACCESS_TAKIM === "string" && env.ACCESS_TAKIM ? env.ACCESS_TAKIM : VARSAYILAN_TAKIM;
    const parcalar = jwt.split(".");
    if (parcalar.length !== 3) return false;
    const baslik = b64urlJson(parcalar[0]);
    const yuk = b64urlJson(parcalar[1]);
    if (baslik.alg !== "RS256" || typeof baslik.kid !== "string") return false;
    const jwk = await anahtarBul(takim, baslik.kid);
    if (!jwk) return false;
    const anahtar = await crypto.subtle.importKey(
      "jwk", jwk, { name: "RSASSA-PKCS1-v1_5", hash: "SHA-256" }, false, ["verify"]);
    const imzaOk = await crypto.subtle.verify(
      "RSASSA-PKCS1-v1_5", anahtar, b64urlBayt(parcalar[2]), new TextEncoder().encode(parcalar[0] + "." + parcalar[1]));
    if (!imzaOk) return false;
    if (yuk.iss !== `https://${takim}.cloudflareaccess.com`) return false;
    const simdi = Math.floor(Date.now() / 1000);
    if (typeof yuk.exp !== "number" || !(yuk.exp > simdi)) return false;
    if (yuk.nbf !== undefined && !(typeof yuk.nbf === "number" && yuk.nbf <= simdi + TOLERANS_SN)) return false;
    if (typeof env.ACCESS_AUD === "string" && env.ACCESS_AUD.length > 0) {
      const aud = Array.isArray(yuk.aud) ? yuk.aud : [yuk.aud];
      if (!aud.includes(env.ACCESS_AUD)) return false;
    } else {
      console.log("ACCESS_AUD tanımlı değil: aud denetlenmedi");
    }
    return true;
  } catch (_) {
    return false;   // fail-closed
  }
}

async function acikOzet(istek, env) {
  const yanit = await env.ASSETS.fetch(istek);
  const h = new Headers(yanit.headers);
  h.set("Content-Type", "application/json");
  h.set("Cache-Control", "no-store");
  h.set("Access-Control-Allow-Origin", "*");
  return new Response(yanit.body, { status: yanit.status, statusText: yanit.statusText, headers: h });
}

export default {
  async fetch(istek, env) {
    const url = new URL(istek.url);
    if (istek.method === "GET" && ACIK_YOLLAR.includes(url.pathname) && !istek.url.includes("?")) return acikOzet(istek, env);
    const jwt = jwtAl(istek);
    if (!jwt || !(await jwtGecerliMi(jwt, env))) return red();
    return baslikEkle(await env.ASSETS.fetch(istek));
  },
};
