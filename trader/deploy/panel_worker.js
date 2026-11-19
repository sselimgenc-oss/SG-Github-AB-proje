// Trader panosu kilidi: tüm istekler önce buradan geçer; HTTP Basic Auth doğruysa statik anlık görüntü döner.
// Kaynak: 1L3A projesinin deploy/pano_worker.js dosyasından uyarlandı (kullanıcının kendi kodu; THIRD_PARTY_NOTICES.md'ye bakın).
// Kullanıcı adı sabit "trader"; parola Worker secret'ı PANEL_SIFRE. Secret yoksa/boşsa HER İSTEK 401 (fail-closed).
// Parolasız yayın seçeneği/bayrağı YOKTUR.
// Oturum çerezi: doğru Basic Auth sonrası 30 gün geçerli, PANEL_SIFRE ile HMAC imzalı çerez (telefonlar Basic Auth'u
// hatırlamadığı için). Parola değişince tüm çerezler geçersiz olur. Çerez HttpOnly + Secure + SameSite=None; Partitioned (kapı iframe'i için; pano salt okunur).
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
  return `${CEREZ}=${bitis}.${await imza(sifre, "v1|" + bitis)}; Max-Age=${OTURUM_S}; Path=/; HttpOnly; Secure; SameSite=None; Partitioned`;   // 19 Kasim: kapi iframe'inde de calissin (pano salt okunur; durum degistiren istek yok)
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

function baslikEkle(yanit, formIzni = false) {
  const h = new Headers(yanit.headers);
  h.set("Cache-Control", "no-store");
  h.set("X-Robots-Tag", "noindex");
  h.set("X-Content-Type-Options", "nosniff");
  h.set("Referrer-Policy", "no-referrer");
  h.delete("X-Frame-Options");   // 19 Kasim: orkestra kapisi iframe'i (CSP frame-ancestors yeterli)
  h.set("Strict-Transport-Security", "max-age=31536000");
  h.set("Content-Security-Policy",
    `default-src 'none'; style-src 'unsafe-inline'; script-src 'unsafe-inline'; img-src data:; base-uri 'none'; form-action ${formIzni ? "'self'" : "'none'"}; frame-ancestors 'self' https://orkestra-kapi.sselimgenc-c18.workers.dev`);
  return new Response(yanit.body, { status: yanit.status, statusText: yanit.statusText, headers: h });
}

function red() {
  return baslikEkle(new Response("Yetkisiz", {
    status: 401,
    headers: { "WWW-Authenticate": 'Basic realm="Trader panosu", charset="UTF-8"' },
  }));
}

// Kapi iframe'i: tarayicilar capraz-site iframe'de Basic Auth penceresi acmaz ve ust duzey giristeki (bolumlenmis)
// cerez iframe'e gecmez. Bu yuzden iframe isteginde (Sec-Fetch-Dest: iframe) parola formu doner; POST /giris dogruysa
// cerez kapi bolumunde kurulur. Ust duzey (telefon/tarayici) Basic Auth aynen kalir.
function girisFormu(hatali) {
  const govde = '<!doctype html><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">' +
    '<title>Trader panosu</title><body style="font-family:system-ui;max-width:22rem;margin:3rem auto;padding:0 1rem">' +
    '<h1 style="font-size:1.2rem">Trader panosu</h1>' + (hatali ? '<p style="color:#b00">Parola yanlış.</p>' : '') +
    '<form method="post" action="/giris"><label>Parola<br><input type="password" name="sifre" autocomplete="current-password" ' +
    'required style="width:100%;font-size:1rem;padding:.4rem"></label><p><button type="submit">Giriş</button></p></form></body>';
  return baslikEkle(new Response(govde, { status: 401, headers: { "Content-Type": "text/html; charset=utf-8" } }), true);
}

function iframeMi(istek) {
  return istek.headers.get("Sec-Fetch-Dest") === "iframe";
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
    const sifre = env.PANEL_SIFRE;
    if (typeof sifre !== "string" || sifre.length === 0) return red();
    if (await cerezGecerli(istek, sifre)) return baslikEkle(await env.ASSETS.fetch(istek));
    if (istek.method === "POST" && new URL(istek.url).pathname === "/giris") {
      let gelen = "";
      try {
        const v = (await istek.formData()).get("sifre");
        gelen = typeof v === "string" ? v : "";
      } catch (_) {
        gelen = "";
      }
      if (!(await esitMi(gelen, sifre))) return girisFormu(true);
      return baslikEkle(new Response(null, { status: 303, headers: { "Location": "/", "Set-Cookie": await cerezYap(sifre) } }));
    }
    if (iframeMi(istek) && !istek.headers.get("Authorization")) return girisFormu(false);
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
