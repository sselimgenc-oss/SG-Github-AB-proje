// Trader panosu Worker'i: tüm istekler önce buradan geçer. 20 Kasım 2026 kullanıcı kararı: panoda şifre/kilit YOK (1L3A ve CT
// panoları gibi açık; kâğıt dönemi bitince hepsi birlikte kapatılacak). Önceki Cloudflare Access JWT doğrulaması kaldırıldı.
// Yalnız okuma: GET/HEAD; diğer yöntemler 405. Güvenlik başlıkları (CSP, nosniff, no-store) ve orkestra kapısı çerçeve izni aynen.
// Kaynak: 1L3A projesinin deploy/pano_worker.js dosyasından uyarlandı (kullanıcının kendi kodu; THIRD_PARTY_NOTICES.md'ye bakın).
// Pano anahtar/parola içermez: anlık görüntü yalnız kâğıt işlem, kasa ve durum özetidir.

function saltOkuma(istek) {
  return istek.method === "GET" || istek.method === "HEAD";
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
  return baslikEkle(new Response("Yalniz okuma (GET/HEAD).", { status: 405, headers: { Allow: "GET, HEAD" } }));
}

export default {
  async fetch(istek, env) {
    // Rejim etiketi (parolasiz; yalniz GET/HEAD; icerik rejim etiketidir, bakiye/pozisyon/anahtar yok). Pano dalindan ONCE.
    if ((istek.method === "GET" || istek.method === "HEAD") && new URL(istek.url).pathname === "/rejim.json") {
      const r = await env.ASSETS.fetch(istek);
      const h = new Headers(r.headers);
      h.set("Content-Type", "application/json");
      h.set("Cache-Control", "no-store");
      h.set("Access-Control-Allow-Origin", "*");
      return baslikEkle(new Response(r.body, { status: r.status, statusText: r.statusText, headers: h }));
    }
    // ML gunluk ozeti (ortak.gunluk_ozet.v1; parolasiz, yalniz GET/HEAD, rejim.json ile ayni kurallar). Pano dalindan ONCE.
    if ((istek.method === "GET" || istek.method === "HEAD") && new URL(istek.url).pathname === "/gunluk_ozet_v1.json") {
      const r = await env.ASSETS.fetch(istek);
      const h = new Headers(r.headers);
      h.set("Content-Type", "application/json");
      h.set("Cache-Control", "no-store");
      h.set("Access-Control-Allow-Origin", "*");
      return baslikEkle(new Response(r.body, { status: r.status, statusText: r.statusText, headers: h }));
    }
    // Panonun geri kalani: kilitsiz (20 Kasim kullanici karari), yalniz okuma.
    if (!saltOkuma(istek)) return red();
    return baslikEkle(await env.ASSETS.fetch(istek));
  },
};
