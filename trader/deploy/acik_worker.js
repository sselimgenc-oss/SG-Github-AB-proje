// Herkese acik ML yayini (19 Kasim 2026): pano Cloudflare Access arkasina alindi; workers.dev icin yol bazli Access
// muafiyeti verilemedigi icin diger projelerin okudugu iki dosya bu AYRI Worker'dan parolasiz yayinlanir.
// Yalniz GET/HEAD /rejim.json, /gunluk_ozet_v1.json ve /mutabakat_v1.json; baska her yol 404. Icerik: rejim etiketi ve gunluk ozet
// (islem mutabakati: islem satirlari ve uyusmazlik sayisi; anahtar, kisisel bilgi yok). Pano verisi bu Worker'a hic yuklenmez.
const ACIK = new Set(["/rejim.json", "/gunluk_ozet_v1.json", "/mutabakat_v1.json"]);

export default {
  async fetch(istek, env) {
    const yol = new URL(istek.url).pathname;
    if (!((istek.method === "GET" || istek.method === "HEAD") && ACIK.has(yol))) {
      return new Response("Bulunamadi", { status: 404, headers: { "Cache-Control": "no-store", "X-Content-Type-Options": "nosniff" } });
    }
    const r = await env.ASSETS.fetch(istek);
    const h = new Headers(r.headers);
    h.set("Content-Type", "application/json");
    h.set("Cache-Control", "no-store");
    h.set("Access-Control-Allow-Origin", "*");
    h.set("X-Content-Type-Options", "nosniff");
    h.set("Referrer-Policy", "no-referrer");
    h.set("Content-Security-Policy", "default-src 'none'; frame-ancestors 'none'");
    return new Response(r.body, { status: r.status, statusText: r.statusText, headers: h });
  },
};
