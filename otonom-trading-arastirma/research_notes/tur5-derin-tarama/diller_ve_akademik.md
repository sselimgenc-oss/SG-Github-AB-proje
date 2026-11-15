# Tur 5 / Bölüm A: Yabancı dil toplulukları ve akademik makaleler

Tarih: 15 Kasım 2026. Yalnızca statik okuma (grep/okuma); hiçbir depo kurulmadı veya çalıştırılmadı. Yatırım tavsiyesi değildir.
Klonlar: `/tmp/claude-0/-home-user-SG-Github-AB-proje/e7a4ca7f-2079-5069-8ada-ea4ed3c50c7b/scratchpad/clones/`

## Kısa sonuç

Üç özelliği birden (kendi teknik analiziyle bulur, kendi açıp kapatır, KENDİ işlemlerinden öğrenir) taşıyan olgun bir repo yine çıkmadı. Ama Tur 3-4'te olmayan iki somut bulgu var:

1. **shoaibghulam/binance-ai-bot ("The Trader")**: Binance USDT-M vadeli, testnet varsayılan, teknik analiz tarayıcısı + kapanan işlemlerle yeniden eğitilen ML kapısı. Tarif edilen bota Binance tarafında bulduğumuz en yakın şey. Ama 1 commit, 0 yıldız, çok yeni; kanıt yok.
2. **suyunjing-su/r20-quantum-trader (astra-quant-agent'ın yeni sürüm yansısı, v8.4.0)**: Tur 3-4 "astra yalnız OKX" demişti. Bu yansıda **Binance USDT-M emir adaptörü (demo-fapi dahil) kodda var** (`astra_backend/exchanges/binance.py:555-599`). Astra'nın kendi deposunun README'si hâlâ "yalnız OKX" diyor; yani sürümler arası çelişki var. Lisans uyarısı aşağıda.

Akademik makalelerin (CryptoTrade, FinMem, FinCon, AQAA) hiçbirinde borsa emir yolu yok; hepsi geriye dönük test veya simülasyon.

## Puan tablosu (1-5)

| Aday | Otonomi | Öğrenme | Kanıt | Olgunluk | Güvenlik | Kullanım kolaylığı | Not |
|---|---|---|---|---|---|---|---|
| shoaibghulam/binance-ai-bot | 4 | 3 | 1 | 2 | 3 | 3 | Binance testnet; ML kapısı kendi işlemlerinden öğrenir |
| suyunjing-su/r20-quantum-trader (astra yansısı) | 4 | 4 | 1 | 3 | 2 | 2 | Binance demo-fapi var; lisans/varsayılan şifre sorunları; LLM maliyeti |
| parkseokjune/overfit-slayer | 3 | 2 | 2 | 2 | 4 | 3 | Dürüst, yalnız BTC, günlük bar (swing); öğrenme = aylık yeniden kalibrasyon |
| Gone2707/btc-trading-bot | 3 | 2 | 1 | 1 | 3 | 4 | Yalnız kâğıt; "zararına satmaz" tuzağı |
| danderson197874/apex-crypto-bot | 4 | 3 | 1 | 2 | 3 | 2 | Borsa Coinbase, Binance değil |
| CryptoTrade (EMNLP 2024) | 1 | 3 | 2 | 2 | 5 | 1 | Yalnız ETH simülasyonu, emir yok |
| FinMem / FinCon | 1 | 3 | 2 | 2 | 5 | 1 | Yalnız geriye dönük test |

Not: Otonomi/Öğrenme puanı "kodda doğrulanan" üzerinden; README iddiasına göre değil.

## Aday bölümleri

### 1) shoaibghulam/binance-ai-bot ("The Trader") — MIT, 1 commit, 0 yıldız, son push 2026-10-07

**README iddiası:** Binance USDT-M vadeli, testnet-first; 5 bot (gün içi, scalp, grid, DCA, rebalance); top-30 hacimli coini tarar; "her kapanan işlemden öğrenen" LightGBM modeli giriş kapısı.

**Kodda doğrulandı:**
- Varsayılan testnet: `app/config.py:33` (`trading_env` varsayılan "testnet"); mainnet için ek `MAINNET_CONFIRMED=yes` şartı: `app/main.py:342-357`.
- Emir gönderme: `app/broker/client.py:218` (`futures_create_order`).
- Karar veren: gösterge tarayıcı (`app/scanner/`, `app/signals/indicator_engine.py`) + ML kapısı `_gate` (`app/bots/manager.py:851-883`). Kapı yalnız doğrulama AUC >= 0,55 ise veto eder (`app/ml/trainer.py:32-35,148-159`); aksi halde göstergeler karar verir (dürüst bir tasarım).
- Çıkışlar: bot kendisi `_manage_exits` ile SL/TP/zaman-stopunu izleyip reduceOnly MARKET ile kapatır (`manager.py:771-816`). Reddedilirse işlemi açık bırakıp tekrar dener.
- Öğrenme döngüsü: `close_trade` net PnL ile (komisyon+kayma sonrası) win/loss etiketler, özellikleri DB'ye yazar ve `maybe_retrain` çağırır (`manager.py:1086-1115`); ilk 50 örnekten sonra her 25 kapanışta yeniden eğitim (`trainer.py:30`, docstring). Etiket = bot kendi işlem sonucu; canlıda kararı etkiliyor (kapı). Ayrıca tarihsel geri doldurma (`app/ml/backfill.py`) ile ön eğitim.
- Risk limitleri: kaldıraç 5x, işlem başı %1 risk, günlük zarar %4, hesap düşüşü %20, 5 eş zamanlı pozisyon, sembol başı %30 (`app/config.py:43-48`); kill switch `app/risk/engine.py:258+`.
- Testler: 6 test dosyası (`tests/`).

**Güvenlik / zayıflıklar:** Borsa tarafında koruyucu stop emri yok; SL/TP yazılım döngüsüyle izleniyor (bot çökerse veya mark fiyat alınamazsa pozisyon korumasız: `manager.py:776-784` kendisi uyarıyor). Panel API'sinde kimlik doğrulama görülmedi (`Depends`/token yok; yalnız 127.0.0.1'e bağlı çalıştırın). Eğitilen model per-bot, az örnekli; "öğrenme gerçek avantaj üretiyor" kanıtı yok. `docs/` içinde bir "ekosistem araştırması" var (yapay zeka üretimi görünümlü). Tek commit, tek geliştirici.

**Kullanım:** `run.ps1` ile Windows'ta tek komut; Binance Futures testnet hesabı gerekir (README adım 59). Not: Binance'in eski testnet'inin durumu başka depoda "demo.binance.com" olarak değişmiş (aşağıda); anahtar uyumunu denemeden bilemeyiz.

### 2) suyunjing-su/r20-quantum-trader (astra yansısı, v8.4.0) — LICENSE: MIT (yansıda), upstream: AGPL+Commons Clause

**README iddiası (yansı):** OKX, Binance, Gate.io'ya "üç borsa eşitliği" ile emir; çok-LLM komite + CIO + fiziksel Python risk hattı + 15 dk beyin döngüsü. **Astra'nın kendi README'si:** yalnız OKX API, Binance sadece referans linki (`astra-quant-agent/README.md:62-67`).

**Kodda doğrulandı (yansıda):**
- Binance USDT-M adaptörü: `astra_backend/exchanges/binance.py:68-70` (canlı `fapi`, demo `demo-fapi.binance.com`), `place_order` `:555-599` (`new_order`), `cancel_order :628`.
- Binance yürütme bayrakları varsayılan kapalı: `env.example:198-201` (`ASTRA_BINANCE_EXECUTION=1` canlı, `ASTRA_BINANCE_DEMO_EXECUTION=1` demo). Yani ayrıca açılması gerekir.
- Öğrenme: Tur 3'teki doğrulama (`{{trading_memory}}` istemi, kapanan işlem incelemesi) geçerli; yansıda `trading_memory` yüklemesi `astra_backend/dashboard_cache.py:107-110`. Bu turda yeniden uçtan uca izlemedik.
- OKX varsayılanı demo: `env.example:22` (`ASTRA_OKX_ENV=demo`).

**Uyarılar:**
- Lisans karışıklığı: upstream `LICENSE` = AGPL-3.0 + Commons Clause + "anti-scam" koşulları; yansı `LICENSE` = "MIT, AstraQuant Team". Yansının başka birinin hesabından MIT'e çevrilmesi güvenilir değil; **resmi kaynak olarak 0xethanq/astra-quant-agent'ı baz alın**, Binance desteğini onun sürümünde de kontrol edin (README çelişkisi).
- Varsayılan şifre: upstream `env.example:160` `ASTRA_ADMIN_TOKEN=R20admin888888`, `DASHBOARD_HOST=0.0.0.0` (Tur 3'te de not edilmişti). Yansıda bu satır `ASTRA_SETUP_TOKEN=replace_with...` olarak değiştirilmiş (daha iyi), ama hâlâ `DASHBOARD_HOST=0.0.0.0`.
- Referans (rebate) kodu gömülü: `BINANCE_INVITE_URL` (`env.example:319`) — ticari yönlendirme.
- Boyut: 900+ dosya, 10k test iddiası; LLM maliyeti yüksek (Tur 3: 50 $/ay hedefini aşabilir).

### 3) parkseokjune/overfit-slayer — lisans YOK, 1 commit, 0 yıldız (Korece/İngilizce)

**README iddiası:** 9 yıllık walk-forward ile "hayatta kalan" 3 strateji (SMA 10/200, Supertrend, Bollinger kırılması), BTC vadeli, aylık "kendi kendine öğrenme", dürüst DSR öz-denetimi (DSR 0,41-0,75 = istatistiksel olarak ayırt edilemez), Binance **Demo Trading** (sahte para).

**Kodda doğrulandı:**
- Gerçek demo emir yolu: `src/paper_trader.py:52` `ex.enable_demo_trading(True)`; "gerçek borsaya asla emir yok" kuralı dosya başında (`:3`); `create_order` `:232,241,244`.
- Öğrenme: `src/self_learn.py:1-12` — parametre ızgarasını geçmiş veride yeniden aratır (yalnız doğrulanmış aile içinde), +0,15 Sharpe iyileşmesi ve plato şartı yoksa değiştirmez. **Bu botun kendi işlemlerinden değil geçmiş fiyattan öğrenmedir.** Canlıya tek bağ: `drift_status.json` CRITICAL ise eşik 0,05'e iner (`self_learn.py:29-37`); canlı gün < 90 ise "gözlem modu" (`:133-134`).
- Günlük (1d) çubuk, 15 dk sinyal döngüsü, maker-first; risk: %4 stop, %8 trailing, -%40 kill switch (README).

**Değerlendirme:** Dürüst, anlaşılır ve güvenli tasarım; ama "scalp/gün içi" değil swing, yalnız BTC, lisans yok. Orijinal beklenti (kendi işlemlerinden öğrenen) karşılanmıyor. İlham/yardımcı fikir (DSR, öğrenme korkulukları) için değerli.

### 4) Gone2707/btc-trading-bot — lisans yok, 1 commit, 0 yıldız (İspanyolca)

**İddia:** Binance BTC/USDT spot, "otomatik öğrenme", $50 sanal para, Vercel'de çalışan MT5 tarzı panel.
**Kodda:** Yalnız kâğıt: Binance herkese açık fiyat verisi (`src/app/api/cron/route.ts:8`), sanal cüzdan `localStorage` (`engine/paperTradingEngine.ts:35,64`). `LIVE_BINANCE` arayüz seçeneği var (`types/trading.ts:99`) ama emir kodu bulunmadı (grep: `newOrder`/`api/v3/order` yok). "Öğrenme" = 3 işlemde bir TP/ızgara aralığını kural bazlı ayarlamak (`engine/selfTuner.ts:50-85`); gerçek ML yok. "Asla zararına satmaz" kuralı: düşüşte pozisyon süresiz tutulur (bag-holding riski). Tarayıcı kapanınca durumu `localStorage`'a bağlı. **Düşük değer; kavram gösterimi.**

### 5) danderson197874/apex-crypto-bot — lisans yok, 1 commit

Python, **Coinbase** (Binance değil). Varsayılan `DRY_RUN=true` (`bot.py:122`). 5 katmanlı sinyal + `MetaLearner`: kapanan işlemde, BUY oyu veren katmanların ağırlığı kazanç/kayıpta %5 artırılıp azaltılır (`bot.py:341-388`), ayrıca ML modeli 6 saatte bir yeniden eğitilir (`ML_RETRAIN_HOURS`, `:139`), 3 üst üste kayıpta sembol duraklatılır (`:895-910`). Bu gerçek "kendi işleminden öğrenen" geri besleme. Ama: Coinbase, harici "dashboard" (`DASHBOARD_URL`/`INGEST_TOKEN`) ile log gönderimi (`log_shipper.py`) ve ağırlıkları uzaktan çekiyor (`bot.py:342-360`) — verinin üçüncü tarafa gitmesi ve uzaktan ağırlık enjeksiyonu riski. Binance istendiği için elendi ama öğrenme deseni (katman ağırlık güncellemesi) not edilmeye değer.

### 6) Akademik: kod var, emir yolu yok

| Makale / repo | Emir yolu | Öğrenme canlı karara geri besleniyor mu | Kanıt (kodda) |
|---|---|---|---|
| CryptoTrade (EMNLP 2024), Xtra-Computing/CryptoTrade, 166 yıldız, lisans NOASSERTION | YOK (borsa/ccxt/binance grep boş; `eth_env.py` simülasyon) | Evet, yansıtma metni sonraki isteme ekleniyor (`env_history.py:47-67`) ama yalnız ETH geçmiş simülasyonu | emir kodu yok |
| FinMem (pipiku915 + hmt1501 türevi) | YOK (Alpaca yalnız haber verisi indirme: `data-pipeline/01_Alpaca_News_API_download.py`) | Katmanlı bellek, geriye dönük | emir kodu yok |
| FinCon (The-FinAI/FinCon, MIT) | YOK (grep boş) | Sözel pekiştirme, geriye dönük | emir kodu yok |
| AQAA (Thanh-Van-2001/..., Apache-2.0, 2026) | YOK: `aqaa/lema/executor.py:8` "simulation-first, broker bağlantısı yok", `core/config.py:71` `broker: "simulated"`; Binance yalnız veri indirme | UCB1 bandit/IC bozunumu simülasyonda; README'deki Sharpe 2,41/2,17/2,73 sonuçları 5 yıllık geriye dönük test | emir kodu yok |
| TradingAgents, AI-Trader (HKUDS), FinAgent | Önceki turlarda incelenmişti; bu turda tekrar bakılmadı | | |

Sonuç: Bu akademik repolar "araştırma çıktısı"; canlı bota dönüştürmek bizim işimiz olur. AQAA'nın backtest Sharpe sayıları doğrulanmadı ve canlı kanıt yok (ek şüphe: kod 47 dosya, tek yazar, doğrudan arXiv'de değil Zenodo/preprint).

## Elenenler

| Depo | Neden |
|---|---|
| ayrtondavoli97/Neural_trader_V7 (İtalyanca, MIT) | KuCoin; yalnız tahmin değerlendirme + sanal cüzdan CSV (`scripts/paper_trader.py`); borsaya emir kodu yok; tahmin isabeti ile yeniden eğitim var ama işlem yok |
| conjason/binance-alpha-miner (AGPL) | RL faktör madenciliği, yalnız geri test; **upstream'de kimlik bilgisi okuma kodu (infostealer benzeri) olduğu için** bu kopya temizlenmiş (`SECURITY_CHANGES.md`); yine de güvenilmez soy, emir yolu yok |
| zhivko/ai-trading-bot-3 | SAC RL, yalnız eğitim/backtest; emir yolu yok; Windows/RTX 5090 odaklı |
| Leadline88/binance-ai-trader | README "mükemmel, hatalar giderildi" tarzı abartı; 1 commit, bu turda derin okunmadı; testnet varsayılan görünüyor |
| BaRaN0732/ai-crypto-trader-pro | Depoda yalnız README+LICENSE, kod yok (boş vitrin) |
| Vishalsaraswat047/apha-tb | AI Studio şablonu; "1 saniyelik genetik motor" iddiası, kanıt yok, scalp-yüksek-frekans riskli |
| HammerGPT/Hyper-Alpha-Arena | Zaten Tur 3'te L3 olarak incelendi |
| bhtbwh/ai-trader, zhou343/stock-trader-ai, CTAAgents/FDT | Çin A-hisse, Binance/ABD değil |
| 7836246/hengzhi, raphael2025/perp-recap, Aifore/coinx | Yalnız işlem GÖZLEM/ders kaydı (Binance), karar vermez |
| Upbit/Koreli depolar (Baekshook, pks10415 vb.) | Yalnız GPT-çağrılı basit bot, öğrenme yok, Upbit |
| Rusça/Vietnamca/Japonca repolar | Aramada anlamlı bir aday çıkmadı (aşağı bak) |

## Yöntem ve sınırlar

- GitHub repo araması: çok kelimeli ve CJK/Kiril sorgular çoğunlukla boş döndü (API tam eşleme yapıyor); kısa sorgular + `sort=updated` daha iyi çalıştı. Hız sınırı sorun olmadı.
- Web araması (Rusça Habr/smart-lab, Korece Inflearn/Kmong, Japonca Zenn/Speaker Deck, Çince): sonuçlar ya genel kitaplık (ccxt/binance-trade-bot, chrisleekr, FinRL) ya eğitim/ders sayfaları; **tutarlı bir "kendinden öğrenen + canlı Binance" Rusça/Korece/Japonca repo bulunamadı**. Bunun nedeni gerçekten yoklukla mı, arama aracının (ABD odaklı) sınırıyla mı ilgili, bilemiyoruz; Velog/Tistory/Qiita/Zenn sayfalarına doğrudan girilmedi (WebFetch yapılmadı).
- Türkçe, Portekizce, İspanyolca, Vietnamca aramalarda yalnız 0-1 yıldızlı öğrenci projeleri çıktı; derin okunmadı (RafaelGallo robo_trader: Q-learning ödevi; 00hsynclk/Crypto-Trading-Bot vb.: yapay zeka etiketli arayüz).
- Hiçbir kod çalıştırılmadı; "öğrenme" iddiaları yalnız kodun okunmasıyla doğrulandı. Performans kanıtı toplanmadı (hiçbir aday kanıtlı sonuç sunmuyor).
- Yeni depoların hepsi 1 commit/0-3 yıldız: topluluk doğrulaması yok, sahte yıldız/yapay zeka ile üretilmiş kod olasılığı yüksek (özellikle `shoaibghulam`'ın `docs/research` ve README üslubu).
- Tahmin: shoaibghulam botunun gerçek testnette hata vermeden çalışıp çalışmadığı bilinmiyor.
