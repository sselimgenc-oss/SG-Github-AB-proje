// 1L3A açık yayın Worker'ı: YALNIZ GET /gunluk_ozet_v1.json (ortak günlük özet) ve GET /mutabakat_v1.json (işlem mutabakatı; kâğıt işlem verisi, gizli hesap adı yok). Diğer her yol / yöntem 404.
// Ana pano Worker'ından (1l3a-pano, Cloudflare Access arkasında) ayrıdır; workers.dev'de Access yol bazında Bypass desteklemez.
const YOLLAR = ["/gunluk_ozet_v1.json", "/mutabakat_v1.json"];

export default {
  async fetch(istek, env) {
    const url = new URL(istek.url);
    if (istek.method !== "GET" || !YOLLAR.includes(url.pathname) || url.search !== "" || istek.url.includes("?")) {
      return new Response("Yok", { status: 404, headers: { "Cache-Control": "no-store", "X-Robots-Tag": "noindex" } });
    }
    const yanit = await env.ASSETS.fetch(new Request(url.origin + url.pathname, { method: "GET" }));
    if (!yanit.ok) return new Response("Yok", { status: 404, headers: { "Cache-Control": "no-store", "X-Robots-Tag": "noindex" } });
    const h = new Headers(yanit.headers);
    h.set("Content-Type", "application/json");
    h.set("Cache-Control", "no-store");
    h.set("Access-Control-Allow-Origin", "*");
    h.set("X-Robots-Tag", "noindex");
    return new Response(yanit.body, { status: 200, headers: h });
  },
};
