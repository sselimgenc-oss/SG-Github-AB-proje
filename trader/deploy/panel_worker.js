// Trader panosu kilidi: tüm istekler önce buradan geçer; HTTP Basic Auth doğruysa statik anlık görüntü döner.
// Kaynak: 1L3A projesinin deploy/pano_worker.js dosyasından uyarlandı (kullanıcının kendi kodu; THIRD_PARTY_NOTICES.md'ye bakın).
// Kullanıcı adı sabit "trader"; parola Worker secret'ı PANEL_SIFRE. Secret yoksa/boşsa HER İSTEK 401 (fail-closed).
// Parolasız yayın seçeneği/bayrağı YOKTUR.
// Oturum çerezi: doğru Basic Auth sonrası 30 gün geçerli, PANEL_SIFRE ile HMAC imzalı çerez (telefonlar Basic Auth'u
// hatırlamadığı için). Parola değişince tüm çerezler geçersiz olur. Çerez HttpOnly + Secure + SameSite=Strict.
const KULLANICI = "trader";
const CEREZ = "pano_oturum";
const OTURUM_S = 30 * 24 * 3600;

async function imza(anahtar, mesaj) {
  const k = await crypto.subtle.importKey("raw", new TextEncoder().encode(anahtar), { name: "HMAC", hash: "SHA-256" },
    false, ["sign"]);
  const b = new Uint8Array(await crypto.subtle.sign("HMAC", k, new TextEncoder().encode(mesaj)));
  return Array.from(b, (x) => x.toString(16).padStart(2, "0")).join("");
}

async function cerezGecerli(istek, sifre) {
  const c = istek.headers.get("Cookie") || "";
  const m = c.match(new RegExp("(?:^|;\\s*)" + CEREZ + "=(\\d+)\\.([0-9a-f]{64})"));
  if (!m) return false;
  const bitis = Number(m[1]);
  const beklenen = await imza(sifre, "v1|" + m[1]);
  const ok = await esitMi(m[2], beklenen);           // sabit zamanli
  return ok && bitis > Math.floor(Date.now() / 1000);
}

async function cerezYap(sifre) {
  const bitis = String(Math.floor(Date.now() / 1000) + OTURUM_S);
  return `${CEREZ}=${bitis}.${await imza(sifre, "v1|" + bitis)}; Max-Age=${OTURUM_S}; Path=/; HttpOnly; Secure; SameSite=Strict`;
}

async function ozet(metin) {
  return new Uint8Array(await crypto.subtle.digest("SHA-256", new TextEncoder().encode(metin)));
}

// Sabit zamanlı karşılaştırma: iki değerin SHA-256'sı (eşit uzunluk) bayt bayt XOR'lanır, erken çıkış yok.
async function esitMi(a, b) {
  const x = await ozet(a);
  const y = await ozet(b);
  let fark = 0;
  for (let i = 0; i < x.length; i++) fark |= x[i] ^ y[i];
  return fark === 0;
}

function baslikEkle(yanit) {
  const h = new Headers(yanit.headers);
  h.set("Cache-Control", "no-store");
  h.set("X-Robots-Tag", "noindex");
  h.set("X-Content-Type-Options", "nosniff");
  h.set("Referrer-Policy", "no-referrer");
  h.set("X-Frame-Options", "DENY");
  h.set("Strict-Transport-Security", "max-age=31536000");
  h.set("Content-Security-Policy",
    "default-src 'none'; style-src 'unsafe-inline'; script-src 'unsafe-inline'; img-src data:; base-uri 'none'; form-action 'none'; frame-ancestors 'none'");
  return new Response(yanit.body, { status: yanit.status, statusText: yanit.statusText, headers: h });
}

function red() {
  return baslikEkle(new Response("Yetkisiz", {
    status: 401,
    headers: { "WWW-Authenticate": 'Basic realm="Trader panosu", charset="UTF-8"' },
  }));
}

function bilgiCoz(baslik) {
  if (!baslik || !/^basic /i.test(baslik)) return null;
  try {
    const bin = atob(baslik.slice(6).trim());
    const metin = new TextDecoder().decode(Uint8Array.from(bin, (c) => c.charCodeAt(0)));
    const i = metin.indexOf(":");
    if (i < 0) return null;
    return { kullanici: metin.slice(0, i), sifre: metin.slice(i + 1) };
  } catch (_) {
    return null;
  }
}

export default {
  async fetch(istek, env) {
    const sifre = env.PANEL_SIFRE;
    if (typeof sifre !== "string" || sifre.length === 0) return red();
    if (await cerezGecerli(istek, sifre)) return baslikEkle(await env.ASSETS.fetch(istek));
    const bilgi = bilgiCoz(istek.headers.get("Authorization"));
    if (!bilgi) return red();
    // iki karşılaştırma da her zaman yapılır (kullanıcı adı yanlışsa bile süre sızdırmasın)
    const kOk = await esitMi(bilgi.kullanici, KULLANICI);
    const sOk = await esitMi(bilgi.sifre, sifre);
    if (!(kOk && sOk)) return red();
    const yanit = baslikEkle(await env.ASSETS.fetch(istek));
    const h = new Headers(yanit.headers);
    h.append("Set-Cookie", await cerezYap(sifre));
    return new Response(yanit.body, { status: yanit.status, statusText: yanit.statusText, headers: h });
  },
};
