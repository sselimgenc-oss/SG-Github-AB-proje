// 1L3A dış nabız (dead-man) Worker'ı: sunucu DIŞINDA koşar; nabız kesilirse Telegram'a uyarı gönderir.
// POST /nabiz (başlık X-Nabiz-Anahtar) -> son nabzı KV'ye yazar. Diğer her istek 404. cron (*/10) -> kontrol + uyarı.
// Secret'lar: NABIZ_ANAHTAR, TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID. KV binding: NABIZ. NABIZ_ANAHTAR yoksa POST 401 (fail-closed).
const ESIK_DK = 20;          // son nabız bu kadar eskiyse sunucu "sustu"
const TEKRAR_DK = 2 * 60;    // aynı uyarıyı en çok 2 saatte bir tekrarla

async function ozet(metin) {
  return new Uint8Array(await crypto.subtle.digest("SHA-256", new TextEncoder().encode(metin)));
}

// Sabit zamanlı karşılaştırma (pano_worker.js ile aynı yöntem)
async function esitMi(a, b) {
  const x = await ozet(a);
  const y = await ozet(b);
  let fark = 0;
  for (let i = 0; i < x.length; i++) fark |= x[i] ^ y[i];
  return fark === 0;
}

async function telegram(env, metin) {
  if (!env.TELEGRAM_BOT_TOKEN || !env.TELEGRAM_CHAT_ID) return false;
  try {
    const r = await fetch(`https://api.telegram.org/bot${env.TELEGRAM_BOT_TOKEN}/sendMessage`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ chat_id: env.TELEGRAM_CHAT_ID, text: metin }),
    });
    return r.ok;
  } catch (_) {
    return false;   // hata metni token içerebilir: loglanmaz
  }
}

async function nabizAl(istek, env) {
  const anahtar = env.NABIZ_ANAHTAR;
  const gelen = istek.headers.get("X-Nabiz-Anahtar") || "";
  const ok = await esitMi(gelen, typeof anahtar === "string" ? anahtar : "");   // her durumda karşılaştır
  if (typeof anahtar !== "string" || anahtar.length === 0 || !ok) return new Response("Yetkisiz", { status: 401 });
  let g;
  try { g = await istek.json(); } catch (_) { return new Response("Hatalı istek", { status: 400 }); }
  if (!g || typeof g !== "object") return new Response("Hatalı istek", { status: 400 });
  const durum = g.durum === "iyi" ? "iyi" : "paper_sorunlu";
  const kayit = { son: Date.now(), durum, neden: String(g.neden || "").slice(0, 200), canli: String(g.canli || "").slice(0, 20) };
  await env.NABIZ.put("nabiz", JSON.stringify(kayit));
  return new Response("tamam", { status: 200 });
}

async function oku(env, ad) {
  const m = await env.NABIZ.get(ad);
  if (!m) return null;
  try { return JSON.parse(m); } catch (_) { return null; }
}

// Zamanlanmış kontrol. Durum KV "uyari" kaydında: {tur: "sustu"|"sorunlu"|null, son: ms, baslangic: ms}
async function kontrol(env, simdi = Date.now()) {
  const nabiz = await oku(env, "nabiz");
  if (!nabiz) return;   // ilk kurulum: nabız hiç gelmediyse uyarı yok
  const dk = Math.floor((simdi - nabiz.son) / 60000);
  const uyari = (await oku(env, "uyari")) || { tur: null, son: 0, baslangic: 0 };
  const tur = dk > ESIK_DK ? "sustu" : nabiz.durum === "iyi" ? null : "sorunlu";

  if (tur === null) {
    if (uyari.tur) {
      const kesinti = Math.max(1, Math.round((nabiz.son - uyari.baslangic) / 60000));
      if (uyari.tur === "sustu") await telegram(env, `✅ 1L3A sunucusu yeniden ses veriyor (kesinti ~${kesinti} dk)`);
      else await telegram(env, `✅ 1L3A paper yeniden sağlıklı (sorun ~${kesinti} dk sürdü)`);
      await env.NABIZ.put("uyari", JSON.stringify({ tur: null, son: 0, baslangic: 0 }));
    }
    return;
  }
  const yeniTur = uyari.tur !== tur;
  if (!yeniTur && simdi - uyari.son < TEKRAR_DK * 60000) return;   // tekrar sınırı
  const metin = tur === "sustu"
    ? `🚨 1L3A sunucusu ${dk} dk'dır ses vermiyor`
    : `⚠️ 1L3A sunucusu ayakta ama paper sorunlu: ${nabiz.neden || "neden bilinmiyor"}`;
  if (await telegram(env, metin)) {
    await env.NABIZ.put("uyari", JSON.stringify({ tur, son: simdi, baslangic: yeniTur ? (tur === "sustu" ? nabiz.son : simdi) : uyari.baslangic }));
  }
}

export default {
  async fetch(istek, env) {
    const yol = new URL(istek.url).pathname;
    if (istek.method === "POST" && yol === "/nabiz") return nabizAl(istek, env);
    return new Response("Bulunamadı", { status: 404 });
  },
  async scheduled(_olay, env) {
    await kontrol(env);
  },
  kontrol,   // test için
};
