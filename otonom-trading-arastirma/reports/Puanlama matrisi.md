# Puanlama matrisi: otonom trading botları (0-100)

Tarih: 15 Kasım 2026. Kaynak: bu klasördeki rapor ve araştırma notları (Tur 1-5). Yeni araştırma yapılmadı. Yatırım tavsiyesi değildir.

## Bu tablo nedir?

Notlarda ciddi biçimde incelenen 53 botu 8 kategoride 0-100 arası puanladım. Amaç şu soruya cevap vermek: kullanıcının önceliği olan "kendi işlemlerinden öğrenen, kendi fırsat bulan, kendi açıp kapatan bot"a kim ne kadar yakın? Çelişen yerde daha yeni turun ve kodla doğrulanmış notun bilgisi geçerli sayıldı.

## Kategoriler ve puan çıpaları

| Kategori | Neye bakıyor | Çıpalar |
|---|---|---|
| 1. Fırsat bulma | Strateji vermeden kendi analiz edip işlem fikri üretiyor mu? | 0: kullanıcı strateji yazmalı. 30: sabit kural/şablon. 60: ML/LLM piyasayı tarar, sabit kurulumla öneri üretir. 85+: çok kaynaklı araştırma (teknik analiz + türev/haber/duyarlılık), çok zaman dilimi, sembolü kendi seçer |
| 2. İşlem açma-kapama | Emri kendi açıp kapatıyor mu? | 0: emir kodu yok. 30: yalnız simülasyon defteri veya her işlemde insan onayı. 60: gerçek/testnet emri katılımsız gönderir. 85+: çıkışları da sağlam yönetir (borsa tarafı SL/TP, iz süren stop, zaman stopu) ve sürekli çalışır |
| 3. Öğrenme | KENDİ işlemlerinden ders çıkarıyor mu? | 0: yok. 25: yalnız son işlemleri/istatistiği modele gösterir veya yalnız piyasa verisiyle yeniden eğitir. 50: sonuç kodda mekanik geri besleme yapar (lot küçültme, karantina, kendi işlemleriyle yeniden eğitim). 75: açık dersler/yansıma canlı kararlara enjekte edilir (kodda doğrulanmış). 90+: dersler/parametreler canlıya çıkmadan önce kâğıtta veya örneklem dışında sınanır ve kanıta göre emekliye ayrılır |
| 4. Risk yönetimi | Sert limitler kodda mı, yalnız prompt'ta mı? | 0: yok/yalnız prompt. 40: bazı tavanlar (kaldıraç/pozisyon). 70: günlük zarar/düşüş durdurma + maruziyet tavanı kodda. 90+: kill switch, devre kesici, ajanın değiştiremeyeceği insan imzalı limitler. Tehlikeli varsayılanlar (20x, bakiyenin %95'i) ağır cezalı |
| 5. Kanıt / şeffaflık | Sonuçlar gösteriliyor mu, dürüst mü? | 0: iddialar kodla/veriyle çelişiyor. 20: sonuç yok. 40: yalnız backtest veya kısa kendi kâğıt kaydı. 60: kayıplar dahil dürüst ileri kayıt. 80+: bağımsız, herkese açık, çok aylı doğrulanabilir kayıt |
| 6. Olgunluk | Yıldız/topluluk, test/CI, bakım, commit geçmişi | 0: tek commit'lik döküm/terk edilmiş. 50: aktif küçük proje, testli. 90+: büyük, bakımlı proje |
| 7. Güvenlik | Varsayılanlar temiz mi? | 100: temiz. Düşenler: varsayılan yönetici şifresi, kimliksiz panel/anahtar uç noktası, telemetri, referral/builder ücreti, özel anahtar, curl\|bash, LLM'in yazdığı kodu çalıştırma, kapalı çalışma zamanı |
| 8. Kullanım kolaylığı | Türkiye'de programcı olmayan, Binance hesabı + Anthropic anahtarı olan kullanıcı için | Yüksek: Binance + testnet/dry-run + kolay kurulum + Claude desteği. Düşük: yalnız OKX/Hyperliquid/MEXC, ağır kurulum, yalnız Çince belge, programlama gerekir |

**Genel uygunluk** = ağırlıklı ortalama: Öğrenme 25, Fırsat 15, Yürütme 15, Risk 15, Kanıt 10, Olgunluk 10, Güvenlik 5, Kolaylık 5 (önceliğiniz kendi kendine öğrenen otonom trading olduğu için öğrenme en ağır). Tam sayıya yuvarlandı. **En güçlü alan** = o botun en yüksek puanlı kategorisi.

## Ana tablo (Genel uygunluğa göre sıralı)

Sütunlar: Fır = Fırsat bulma, Yür = Yürütme, Öğr = Öğrenme, Ris = Risk, Kan = Kanıt, Olg = Olgunluk, Güv = Güvenlik, Kol = Kolaylık.

| # | Repo | Borsa | Lisans | Fır | Yür | Öğr | Ris | Kan | Olg | Güv | Kol | **Genel** | En güçlü alan | Not |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 1 | [0xethanq/astra-quant-agent](https://github.com/0xethanq/astra-quant-agent) | OKX (demo varsayılan) | AGPL-3.0 + Commons Clause | 80 | 82 | 78 | 72 | 25 | 62 | 30 | 35 | **67** | Yürütme | Kapanan işlemlerden ders çıkarıp canlı isteme koyan ve kanıta göre eski dersi arşivleyen tek olgun bot; ama yalnız OKX, varsayılan yönetici şifresi var, kanıt yok (ders yeni çıkınca kâğıt kapısı yok). |
| 2 | [rgg81/crypto-trade-claude-code](https://github.com/rgg81/crypto-trade-claude-code) | Binance USD-M (kâğıt varsayılan) | Yok (tüm hakları saklı) | 72 | 50 | 88 | 82 | 35 | 18 | 85 | 55 | **65** | Öğrenme | Dersler istemlere enjekte ediliyor ve istatistiksel kapıdan (DSR) geçmeden terfi etmiyor; en iyi tasarım, ama 2 yıldız, tek commit ve lisans yok (kodu yayımlamak hukuken sorunlu). |
| 3 | [vedv0987-cloud/bvedtrade](https://github.com/vedv0987-cloud/bvedtrade) | Binance (testnet varsayılan, canlı için ikinci kilit) | Yok | 50 | 72 | 58 | 76 | 58 | 30 | 55 | 25 | **57** | Risk | Sonuçlar giriş kapısını etkiliyor (Q-öğrenme, 20 işlemde bir yeniden eğitim, kill switch); yazarın kendi verisi zararda (634 işlem, -0,55R), ağır kurulum, lisans yok. |
| 4 | [suyunjing-su/r20-quantum-trader (astra aynası)](https://github.com/suyunjing-su/r20-quantum-trader) | Binance USDT-M demo + OKX + Gate (yürütme bayrakları kapalı) | MIT (yansıda; asıl astra AGPL+Commons Clause ile çelişiyor) | 80 | 70 | 70 | 70 | 10 | 25 | 28 | 40 | **57** | Fırsat bulma | Astra'nın eski sürümünün aynası, Binance emir adaptörü kodda var (asıl depoda yok); lisans çelişkisi nedeniyle güvenilmez, kaynak olarak asıl astra esas alınmalı. |
| 5 | [HKUDS/Vibe-Trading](https://github.com/HKUDS/Vibe-Trading) | 16 broker SDK + Robinhood MCP (varsayılan IBKR paper) | MIT | 70 | 70 | 25 | 92 | 20 | 85 | 80 | 35 | **57** | Risk | En iyi 'insan imzalı yetki' (mandate): ajan limitleri değiştiremez, HALT/flatten var; ama sonuçtan öğrenme bağı yok ve canlı broker özelliği gerçek hesapta doğrulanmadığını kendisi yazıyor. |
| 6 | [qrak/LLM_trader](https://github.com/qrak/LLM_trader) | Yok (iç simülasyon defteri) | MIT | 70 | 28 | 75 | 40 | 45 | 70 | 85 | 45 | **57** | Güvenlik | Kapanan işlem belleği ve semantik kurallar kodla canlı isteme giriyor, 2777 test ve şeffaf yayın; ama borsa emir yolu yok (broker eklemek gerekir). |
| 7 | [FilipeThome/the-trader-bot](https://github.com/FilipeThome/the-trader-bot) | Binance spot testnet | Yok | 40 | 60 | 52 | 82 | 55 | 33 | 90 | 40 | **56** | Güvenlik | Güvenli ve dürüst; kötü giden stratejiyi sinyal moduna indiriyor ve canlıya terfi için 30 günlük testnet şartı var; ama kendi backtest'inde kaybediyor, öğrenme yalnız frenleme, arayüz Portekizce. |
| 8 | [NoFxAiOS/nofx](https://github.com/NoFxAiOS/nofx) | Binance, Hyperliquid, Bybit, OKX ve 6 borsa daha (testnet yalnız Hyperliquid) | AGPL-3.0 | 75 | 85 | 28 | 50 | 20 | 82 | 40 | 50 | **53** | Yürütme | Güçlü canlı yürütme ve borsa tarafı SL/TP, ama öğrenmesi yalnız istatistik gösterimi, günlük zarar durdurma bağlı değil, canlı varsayılan, telemetri ve builder ücreti var. |
| 9 | [freqtrade/freqtrade + FreqAI](https://github.com/freqtrade/freqtrade) | Binance dahil çok borsa (ccxt), dry-run | GPL-3.0 | 42 | 88 | 25 | 60 | 20 | 98 | 85 | 45 | **53** | Olgunluk | En sağlam altyapı: modeli canlıda yeniden eğitir (piyasadan öğrenir, kendi kâr/zararından değil); giriş eşiklerini strateji dosyası belirler, yayınlanmış sonuç yok. |
| 10 | [RafaelPF07/evotrader](https://github.com/RafaelPF07/evotrader) | Yok (simüle ABD ETF hesabı) | Yok | 40 | 30 | 82 | 40 | 60 | 42 | 85 | 20 | **52** | Güvenlik | Kayıp analizi, üç ayda bir yeniden evrim ve ayrılmış veride kapılı terfi (en iyi kapılı öğrenme deseni); al-tut'u yenemediğini kendisi yazıyor, gerçek emir yok. |
| 11 | [chase-mew/ai-hedge-fund](https://github.com/chase-mew/ai-hedge-fund) | Hyperliquid (paper/testnet/live) | Notlarda belirtilmemiş | 65 | 45 | 28 | 72 | 60 | 48 | 85 | 30 | **51** | Güvenlik | En dürüst repo (açık ileri günlük, 'anekdot' diyor), varsayılan insan onaylı, deterministik risk kapısı; öğrenme yalnız geçmiş isabeti (Brier) modele göstermek, Hyperliquid ve ağır kurulum. |
| 12 | [195440/nof1.ai](https://github.com/195440/nof1.ai) | Gate.io, OKX (Gate testnet) | AGPL-3.0 | 72 | 80 | 25 | 75 | 20 | 45 | 40 | 30 | **50** | Yürütme | Kodla en kapsamlı hesap zarar-durdur/düşüş engeli ve 10 sn'lik stop izleyici var; öğrenme yalnız son işlemleri göstermek, panel kimliksiz, örnek ayar 25x, Binance yok. |
| 13 | [shoaibghulam/binance-ai-bot](https://github.com/shoaibghulam/binance-ai-bot) | Binance USDT-M vadeli (testnet varsayılan) | MIT | 58 | 58 | 52 | 70 | 10 | 15 | 45 | 60 | **49** | Risk | Kapanan işlemlerle yeniden eğitilen LightGBM kapısı (yalnız veto) ve iyi risk limitleri; ama borsa tarafı stop yok, panel kimliksiz, 0 yıldız ve tek commit. |
| 14 | [enarjord/passivbot](https://github.com/enarjord/passivbot) | Binance, Bybit, OKX, Hyperliquid vb. | Unlicense (kamu malı) | 25 | 85 | 15 | 55 | 62 | 75 | 70 | 42 | **48** | Yürütme | Gerçek parayla tek kayıt (Hyperliquid kasası ~1,2 yıl, ~%28 net, küçük TVL, doğrulama zayıf); grid/martingale, tahmin etmez ve öğrenmez, referans kodları var. |
| 15 | [wyc-dev/MATS](https://github.com/wyc-dev/MATS) | Hyperliquid (gerçek) + kâğıt motoru | Apache-2.0 | 68 | 60 | 58 | 60 | 10 | 15 | 20 | 20 | **47** | Fırsat bulma | Q-öğrenme çarpanı canlı kararda ve kendi kodunu düzenleyen 'system engineer' var; ama tek commit, pazarlama dili, düz metin özel anahtar ve anahtar yazan ayar API'si kırmızı bayrak. |
| 16 | [AmpyFin/ampyfin](https://github.com/AmpyFin/ampyfin) | Alpaca (ABD hissesi, paper varsayılan) | Yok (lisans dosyası yok) | 50 | 65 | 55 | 40 | 15 | 45 | 60 | 20 | **47** | Yürütme | Simüle sonuç -> sıralama -> canlı strateji ağırlığı zinciri kodda gerçek; Ekim 2025'ten beri durağan, MongoDB zorunlu, kripto/Binance yok. |
| 17 | [7thDrag0n/AutoEvolve](https://github.com/7thDrag0n/AutoEvolve) | FreqTrade üzerinden (dry-run varsayılan) | GPL-3.0 | 45 | 55 | 75 | 40 | 10 | 20 | 10 | 30 | **45** | Öğrenme | LLM kendi işlem sonuçlarına bakıp strateji kodunu yeniden yazıyor ve kötüleşirse geri alıyor (L5'e en yakın), ama LLM'in yazdığı kod doğrudan çalıştırılıyor ve deploy sonrası işlem DB'sini siliyor. |
| 18 | [Lumiwealth/lumibot (ajanlar)](https://github.com/Lumiwealth/lumibot) | Alpaca/Tradier vb. 12 broker (PAPER varsayılan) | GPL-3.0 | 50 | 65 | 40 | 25 | 10 | 88 | 65 | 20 | **45** | Olgunluk | LLM ajanı kendi yazdığı dersleri sonraki turlara geri alıyor (PnL'e bağlı değil); ajan yolunda kodla zorlanan limit yok (yalnız prompt). |
| 19 | [CyberWei922/ai-trader-paper](https://github.com/CyberWei922/ai-trader-paper) | Binance spot (dry-run) | GPL-3.0 | 45 | 55 | 40 | 58 | 10 | 15 | 80 | 78 | **44** | Güvenlik | En kolay kurulum (Windows çift tık, sahte para); zarardan sonra lot küçültüyor ve 6 saatte bir yeniden eğitiyor, ama kanıt yok, tek commit, Çince README. |
| 20 | [Erfaniaa/LLM-Auto-Trader](https://github.com/Erfaniaa/LLM-Auto-Trader) | Binance/Bybit/OKX (CCXT, paper varsayılan) | MIT | 58 | 60 | 22 | 62 | 10 | 38 | 80 | 52 | **44** | Güvenlik | Bağımsız devre kesicili (maks. %5 düşüş), testli ve temiz bir LLM botu; öğrenme yalnız son 5 kararı bellekte göstermek (kalıcı değil), sonuç yayımlanmamış. |
| 21 | [jerome-benoit/freqai-strategies](https://github.com/jerome-benoit/freqai-strategies) | Binance spot (dry-run varsayılan) | Yok (lisans dosyası yok) | 50 | 75 | 20 | 58 | 18 | 40 | 85 | 38 | **44** | Güvenlik | Topluluğun en dürüst/belgeli FreqAI paketi ('kârlılık kanıtı değildir'); canlı yeniden eğitim varsayılan kapalı ve kendi işlemlerinden öğrenmiyor, kurulum bilgi ister. |
| 22 | [TauricResearch/TradingAgents](https://github.com/TauricResearch/TradingAgents) | Yok (emir kodu yok) | Apache-2.0 | 78 | 3 | 55 | 5 | 25 | 95 | 70 | 35 | **44** | Olgunluk | Çok kaynaklı araştırma ve boğa/ayı tartışması, sonuçla etiketli ders günlüğü portföy yöneticisine geri besleniyor; ama emir vermez, bağımsız yeniden üretimde al-tut'u çoğunlukla yenemedi. |
| 23 | [adamCYH/evotrader](https://github.com/adamCYH/evotrader) | Robinhood oturumu / simülasyon broker | Apache-2.0 | 55 | 30 | 45 | 82 | 15 | 12 | 80 | 15 | **44** | Risk | Evrim ajanı öneri üretir, insan onaylar (öğrenme insan kapılı); sert hesap limitleri ajanın değiştiremeyeceği yerde, ama 1 yıldız ve Binance yok. |
| 24 | [SoloHard32/MEXC-AI-BOT](https://github.com/SoloHard32/MEXC-AI-BOT) | Yalnız MEXC spot (DRY_RUN varsayılan) | MIT | 50 | 58 | 50 | 55 | 8 | 12 | 45 | 28 | **43** | Yürütme | Zarar eden sembolü karantinaya alıyor (kendi işleminden geri besleme), ama model dry-run'da öğrenmiyor, tek 8700 satırlık dosya ve Binance yok. |
| 25 | [parkseokjune/overfit-slayer](https://github.com/parkseokjune/overfit-slayer) | Binance Demo Trading | Yok | 28 | 62 | 30 | 62 | 45 | 8 | 85 | 55 | **43** | Güvenlik | Kendi istatistiğiyle 'şanstan ayırt edilemez' diyen dürüst swing botu; öğrenme geçmiş fiyattan aylık yeniden kalibrasyon, kendi işlemlerinden değil; lisans yok. |
| 26 | [virattt/ai-hedge-fund](https://github.com/virattt/ai-hedge-fund) | Yok (dahili kâğıt defter) | MIT | 65 | 35 | 3 | 72 | 15 | 95 | 72 | 40 | **43** | Olgunluk | LLM kişilikleri sinyal verir, limitleri deterministik kod uygular (en olgun risk mimarisi, kullanıcı açarsa); gerçek broker yok, öğrenme yok. |
| 27 | [ygwyg/MAHORAGA](https://github.com/ygwyg/MAHORAGA) | Alpaca (paper varsayılan) | MIT | 62 | 70 | 5 | 80 | 10 | 38 | 75 | 15 | **42** | Risk | 30 sn'lik döngü, kural çıkışları ve sert PolicyEngine (kill switch, günlük zarar) var; hafıza harness'e bağlı değil, opsiyon yolu limiti atlıyor, Şubat 2026'dan beri durağan. |
| 28 | [maxwellcm92/darwinfi](https://github.com/maxwellcm92/darwinfi) | Base L2 / Uniswap V3 (zincir üstü) | MIT | 40 | 48 | 68 | 50 | 10 | 10 | 25 | 10 | **41** | Öğrenme | Kâğıttan canlıya kapılı terfi kodda var (kâğıt kapısı fikri iyi), ama hackathon kalitesi, zincir üstü özel anahtar, 1 yıldız ve Binance yok. |
| 29 | [AleksNovo/freqai-3ai-strategy](https://github.com/AleksNovo/freqai-3ai-strategy) | Bybit (varsayılan işlem açmıyor) | GPL-3.0 | 50 | 40 | 55 | 40 | 10 | 25 | 65 | 10 | **41** | Güvenlik | Her sinyalin sanal sonucundan öğrenme fikri yaratıcı (tasarım referansı); ama varsayılan olarak işlem açmıyor, Bybit ve çok karmaşık, sonuç yayımlamıyor. |
| 30 | [danderson197874/apex-crypto-bot](https://github.com/danderson197874/apex-crypto-bot) | Coinbase (DRY_RUN varsayılan) | Yok | 55 | 55 | 55 | 45 | 5 | 8 | 10 | 20 | **40** | Fırsat bulma | Katman ağırlıkları kendi işlem sonuçlarıyla güncelleniyor, ama günlükleri üçüncü taraf siteye gönderiyor ve ağırlıkları uzaktan çekiyor; Binance yok. |
| 31 | [sorry510/go_binance_futures](https://github.com/sorry510/go_binance_futures) | Binance spot/vadeli (spot testnet döngüsü doğrulanmış) | MIT | 48 | 58 | 15 | 50 | 30 | 52 | 55 | 28 | **40** | Yürütme | Çok dürüst README ('mainnet doğrulanmadı'), 235 test; ders çıkarma otomatik bağlı değil, arayüz Çince, MySQL önerilir. |
| 32 | [iterativv/NostalgiaForInfinity](https://github.com/iterativv/NostalgiaForInfinity) | Freqtrade üzerinden Binance dahil (dry-run) | GPL-3.0 | 35 | 78 | 0 | 28 | 30 | 88 | 85 | 60 | **40** | Olgunluk | Strateji yazmadan çalışan olgun kural botu (öğrenmeyen taban çizgisi); eski sürümde stoploss -0,99 yani fiilen stop yok, kanıt yalnız backtest. |
| 33 | [TorchTrade/torchtrade](https://github.com/TorchTrade/torchtrade) | Binance/Bybit/OKX/Alpaca (demo=True varsayılan) | MIT | 40 | 55 | 25 | 40 | 18 | 68 | 85 | 8 | **40** | Güvenlik | 106 test ve CI ile olgun bir RL çatısı, ama hazır ajan yok: modeli kullanıcı eğitmeli, programcı gerektirir. |
| 34 | [HammerGPT/Hyper-Alpha-Arena](https://github.com/HammerGPT/Hyper-Alpha-Arena) | Hyperliquid (testnet/mainnet), Binance Futures | Apache-2.0 | 45 | 70 | 20 | 40 | 15 | 50 | 35 | 55 | **39** | Yürütme | Kullanımı en kolay arayüzlü LLM botlarından; stratejiyi kullanıcının promptu belirliyor, atıf analizi yalnız insana gösteriliyor, sabit 0,03% builder ücreti ve kimliksiz rotalar var. |
| 35 | [kb-90/okx-algotrade-agent-x](https://github.com/kb-90/okx-algotrade-agent-x) | OKX (demo varsayılan) | AGPL-3.0 | 45 | 60 | 25 | 62 | 10 | 20 | 75 | 28 | **39** | Güvenlik | LSTM yeniden eğitimi ve evrimsel parametre araması canlı dosyaya yazıyor ama piyasa verisinden öğreniyor, kendi işlemlerinden değil; LLM yok, Ekim 2025'ten beri durağan. |
| 36 | [richkuo/go-trader](https://github.com/richkuo/go-trader) | Binance US/OKX/Hyperliquid (paper/live) | MIT | 25 | 72 | 3 | 55 | 20 | 78 | 80 | 35 | **39** | Güvenlik | 50+ hazır strateji, çok testli ve olgun; ama öğrenmiyor, stratejiyi kullanıcı seçiyor, Binance US (Türkiye için uygun değil). |
| 37 | [Drakkar-Software/OctoBot](https://github.com/Drakkar-Software/OctoBot) | Binance dahil çok borsa (paper önerilir) | GPL-3.0 | 25 | 75 | 3 | 40 | 10 | 85 | 70 | 82 | **39** | Olgunluk | Kullanımı en kolay arayüzlü bot (paper trading); grid/DCA, öğrenme yok, AI modu bu turda öğrenme açısından doğrulanmadı, bulut ürünü yönlendirmeleri çok. |
| 38 | [OpenByteInc/QuantDinger](https://github.com/OpenByteInc/QuantDinger) | Binance, OKX, Bybit, Alpaca, IBKR vb. (varsayılan sinyal modu) | Apache-2.0 (ön yüz kapalı) | 25 | 65 | 18 | 50 | 10 | 80 | 35 | 55 | **39** | Olgunluk | Kullanıcının/ajanın yazdığı kural botu; LLM filtresi hata verirse emri geçiriyor (fail-open), varsayılan admin şifresi 123456 ve gömülü broker referans kodları var. |
| 39 | [AI4Finance-Foundation/FinRL](https://github.com/AI4Finance-Foundation/FinRL) | Alpaca (paper/canlı yalnız URL ile ayrılır) | MIT | 35 | 60 | 15 | 25 | 25 | 88 | 65 | 10 | **37** | Olgunluk | Öğrenilmiş PPO politikasıyla Alpaca'ya emir verir ama eğitim çevrimdışı ve kullanıcıya ait; risk limiti zayıf, README gerçek para önermiyor. |
| 40 | [wquguru/nof0](https://github.com/wquguru/nof0) | Hyperliquid (testnet varsayılan) | Yok | 62 | 55 | 8 | 48 | 15 | 40 | 40 | 30 | **36** | Fırsat bulma | Emir veriyor ama SL/TP hataları yok sayılıyor (çıplak pozisyon riski), öğrenme metrikleri yarım (TODO), lisans yok, Aralık 2025'ten beri güncellenmedi. |
| 41 | [hummingbot/hummingbot](https://github.com/hummingbot/hummingbot) | Çok borsa (V2 controller) | Apache-2.0 | 20 | 70 | 0 | 40 | 15 | 90 | 70 | 25 | **35** | Olgunluk | Olgun ama örnek yönlü stratejiler sabit göstergeli; öğrenme yok, asıl alanı piyasa yapıcılık, kurulum zor. |
| 42 | [alex-jb/orallexa-ai-trading-agent](https://github.com/alex-jb/orallexa-ai-trading-agent) | Alpaca (yalnız paper) | MIT | 45 | 40 | 15 | 40 | 35 | 40 | 85 | 20 | **35** | Güvenlik | Rolling isabete göre ağırlık uyarlaması kodda var ama varsayılan KAPALI; README rozet ağırlıklı, 2 aylık, kanıt iddiası doğrulanmadı. |
| 43 | [Nikhilperr/binance-futures-trading-bot](https://github.com/Nikhilperr/binance-futures-trading-bot) | Binance vadeli (test modu varsayılan) | MIT | 50 | 60 | 52 | 5 | 5 | 5 | 15 | 35 | **34** | Yürütme | Öğrenme gerçek (sinyal ağırlıkları kendi isabetinden) ama 20x kaldıraç ve bakiyenin %95'i risk, kimliksiz 0.0.0.0 panel: uzak durun, yalnız mantığı okumaya değer. |
| 44 | [asavinov/intelligent-trading-bot](https://github.com/asavinov/intelligent-trading-bot) | Binance, MT5 | MIT | 48 | 52 | 15 | 25 | 10 | 28 | 65 | 20 | **31** | Güvenlik | ML ile al/sat sinyali üretir ama sunucu eğitmiyor (elle yeniden eğitim), zayıf belge/test ve tek geliştirici. |
| 45 | [AI4Finance-Foundation/FinRL-Trading (FinRL-X)](https://github.com/AI4Finance-Foundation/FinRL-Trading) | Alpaca (paper varsayılan) | Apache-2.0 | 35 | 50 | 0 | 45 | 12 | 62 | 55 | 15 | **30** | Olgunluk | Kural tabanlı rotasyon motoru; 'trade' rotası kırık görünüyor ve web düğmesi paper kontrolü yapmıyor, README sonuç görseli doğrulanmadı. |
| 46 | [alsk1992/CloddsBot](https://github.com/alsk1992/CloddsBot) | Binance, Hyperliquid, Polymarket, Kalshi vb. (anahtar varsa canlı) | MIT | 30 | 45 | 5 | 30 | 10 | 65 | 40 | 45 | **29** | Olgunluk | Sohbet asistanı; emir araçları gerçek ama kaldıraç tavanı yok (1-125), kapatma emirleri limiti atlıyor, canlı varsayılan ve çok geniş saldırı yüzeyi. |
| 47 | [LNSTT369/NightWatcher-V2](https://github.com/LNSTT369/NightWatcher-V2) | Alpaca (paper varsayılan) | MIT | 35 | 62 | 0 | 75 | 5 | 8 | 15 | 20 | **29** | Risk | Katılımsız döngü ve sert politika motoru var, ama karar LLM değil StockTwits eşiği; kimliksiz anahtar yazma uç noktası ve tahmin edilebilir kill-switch sırrı ciddi güvenlik açığı. |
| 48 | [jesse-ai/jesse](https://github.com/jesse-ai/jesse) | Çok borsa (canlı kısım ücretli olabilir) | MIT | 0 | 55 | 8 | 30 | 10 | 80 | 65 | 15 | **28** | Olgunluk | Stratejiyi kullanıcı yazar (0 fırsat bulma); genetik optimizasyon çevrimdışı. |
| 49 | [galleonlabs/hypergrok-trading-desk](https://github.com/galleonlabs/hypergrok-trading-desk) | Hyperliquid (harici ajan SDK) | MIT | 40 | 25 | 0 | 25 | 10 | 45 | 70 | 20 | **24** | Güvenlik | Her yazma insan onaylı; limitler yalnız LLM talimatı ve regex kancası, depoda emir kodu yok. |
| 50 | [oficcejo/okx-2pa-agent-web](https://github.com/oficcejo/okx-2pa-agent-web) | OKX (demo/gerçek) | AGPL-3.0 | 38 | 52 | 0 | 35 | 5 | 12 | 25 | 30 | **23** | Yürütme | Sabit fiyat-hareketi promptuyla LLM karar veriyor, öğrenme yok; repoda web.rar ve yönlendirme (referral) bağlantısı kırmızı bayrak. |
| 51 | [Senpi-ai/senpi-skills](https://github.com/Senpi-ai/senpi-skills) | Hyperliquid (kapalı @senpi-ai/runtime) | MIT | 30 | 30 | 0 | 20 | 10 | 40 | 25 | 20 | **19** | Olgunluk | Açık kod yalnız YAML kural stratejileri; emir ve gerçek limitler kapalı çalışma zamanında, denetlenemiyor. |
| 52 | [The-Swarm-Corporation/AutoHedge](https://github.com/The-Swarm-Corporation/AutoHedge) | Solana/Jupiter (araç ajana bağlı değil) | MIT | 30 | 10 | 0 | 5 | 5 | 18 | 25 | 10 | **11** | Fırsat bulma | 'Otonom hedge fon' iddiası kodla desteklenmiyor: emir aracı hiçbir ajana bağlanmamış, tek tur REPL; özel anahtar .env'de düz. |
| 53 | [chrisworsey55/atlas-gic](https://github.com/chrisworsey55/atlas-gic) | Yok (emir kodu bulunamadı) | MIT | 20 | 0 | 0 | 0 | 0 | 15 | 55 | 10 | **8** | Güvenlik | README'deki +%22 ve 'gerçek sermaye' iddiası kendi sonuç dosyasıyla (-%5,91) çelişiyor, otomatik öğrenme modülleri depoda yok: güvenilmez. |

## Her kategorinin en iyi 3'ü

- **Fırsat bulma:** 0xethanq/astra-quant-agent (80); suyunjing-su/r20-quantum-trader (astra aynası) (80); TauricResearch/TradingAgents (78)
- **Yürütme:** freqtrade/freqtrade + FreqAI (88); NoFxAiOS/nofx (85); enarjord/passivbot (85)
- **Öğrenme:** rgg81/crypto-trade-claude-code (88); RafaelPF07/evotrader (82); 0xethanq/astra-quant-agent (78)
- **Risk:** HKUDS/Vibe-Trading (92); rgg81/crypto-trade-claude-code (82); FilipeThome/the-trader-bot (82)
- **Kanıt:** enarjord/passivbot (62); RafaelPF07/evotrader (60); chase-mew/ai-hedge-fund (60)
- **Olgunluk:** freqtrade/freqtrade + FreqAI (98); TauricResearch/TradingAgents (95); virattt/ai-hedge-fund (95)
- **Güvenlik:** FilipeThome/the-trader-bot (90); rgg81/crypto-trade-claude-code (85); qrak/LLM_trader (85)
- **Kolaylık:** Drakkar-Software/OctoBot (82); CyberWei922/ai-trader-paper (78); shoaibghulam/binance-ai-bot (60)

Bir bot yalnız bir kategoride parlıyorsa genel sıralamada yukarı çıkamaz; örneğin Vibe-Trading riskte, freqtrade yürütme ve olgunlukta, TradingAgents fırsat bulmada öndedir ama hiçbiri üç özelliği birlikte taşımaz. Genel tabloda öğrenme + yürütme + risk üçlüsünü en iyi birleştiren iki aday TEMPEST (kâğıt, lisanssız) ve astra'dır (yalnız OKX).

## Dışarıda bırakılanlar

### Spam, klon, tek kelimeyle reddedilenler

| Depo | Neden |
|---|---|
| Eltano1985/tradememory-protocol | Sahte/klon: depo içi .zip indirtiyor, indirmeyin |
| hermes-trading adlı 4 depo (wallstreetwolf59-sketch, khalednoor75, satyamdas03, Gotji253/AI_trading_ADA) | Aynı şablon spam, 0-1 yıldız |
| oyi77/1ai-skills, aksaayyy/Ai-bot-earn-or-die, thom899g/autonomous-cross-asset-... | Şişirilmiş/spam |
| FinMem kopyaları (cqu3la, ivanleekk, TanTaf, ranjeetyadavnitt vb.) | Akademik kopyalar |
| ~18 adet 'polymarket-ai-agent' deposu, Polymarket arbitraj botları, 0 yıldızlı 'Claude trading agent' depoları | Anahtar kelime doldurma, anahtar hırsızlığı şüphesi |
| janitoff0/ninjatrader-bot, Polytutor-AI-Labs/*, Nour-Br/*, TradePilot | Yıldız patlaması + reklam/airdrop görünümü |
| jackson-video-resources/claude-tradingview-mcp-trading (+6 klon) | Lisanssız, gizli affiliate, klon çiftliği |
| Mohamed-sm/Freqtrade-RLStrategy-IA, CaptainNahin/Trading-bot | '%91 / %90+ kazanma' gibi kanıtsız abartı |
| stefanoviana/deepalpha, Markfans/cryptoquant-ai | Şişirilmiş iddia / şüpheli |
| bigmacman1129/*, aitradingbotspro/* | Klon/spam |
| Shelpid/SETS, ryan-yuuu/crypto-trading-arena, etrobot/open-alpha-arena | Yalnız simülasyon, gerçek emir yok |
| imsatoshi/GeneTrader, squidKid-deluxe/QTradeX, DogsTailFarmer/martin-binance, TheFourGreatErrors/alpha-rptr, 51bitquant/binance_grid_trader | Strateji kullanıcıdan (optimizer/grid/çatı) |
| rmbell09-lang/tradesight, SnowCheetos/AutoMoonBot, wolfinch/wolfinch | Dağınık/ticari, terk edilmiş veya eski |
| QuantiaAI/helm-agents, Max007-coder/quantbot, roclee2692/autonomous-spot-trading-agent, IslamBaraka90/Super-Agent-Trading-Bot, boredom198/thesis-ai-trading-agent, sopersone/cabbage-trading-machine, Aswin-Ram-K/algo-trading-bot, Ricardokarma/claude-trading-bot | Öğrenme yok, çok az commit, tek amaçlı veya hackathon |
| Dukesan-ai/crypto-ml-trading-framework, NeillBotushanski/alphaforge, BaRaN0732/ai-crypto-trader-pro | Kaynak kod yok / yalnız belge (doğrulanamaz) |
| danderson197874 dışındaki Upbit/Çin A-hisse/Rus/Vietnam/İspanyol-Portekiz öğrenci projeleri, Gone2707/btc-trading-bot, ayrtondavoli97/Neural_trader_V7, zhivko/ai-trading-bot-3, conjason/binance-alpha-miner (kimlik bilgisi okuyan koddan türemiş), Leadline88/binance-ai-trader, Vishalsaraswat047/apha-tb | Emir yolu yok / düşük değer / güvenilmez soy |
| Maazullah8/AI_Self_Improving_Bot, Aenger-priv/ContextualBandits, PetteKay/ai-forex-trading-bot, MT5/XAUUSD EA'ları, zero-was-here/tradingbot | Forex/MT5, Binance'e uygulanmaz |
| Polymarket/Kalshi/tahmin piyasası botları (howdymary/autopredict, openthomas, caiovicentino/polymarket-mcp-server vb.) | Kapsam dışı |
| Eski nof1/nofx forkları (fsinbad/nofx: kötü amaçlı workflow silinmiş, nofxai, gale-crypto, MaoTouHU/Nof1OpenAI), astra forkları, passivbot forkları, freqai-strategies forkları | Upstream kopyası, sapma yok; fsinbad forkunda zararlı CI geçmişi |

### Puanlanmayanlar (emir yolu yok, çerçeve veya yeterli kanıt yok)

| Depo | Neden |
|---|---|
| FinRobot, TradingAgents-CN, HKUDS/AI-Trader, SnowingFox/open-nof1.ai, AgenticTrading, tensortrade, microsoft/RD-Agent, qlib | Emir kodu yok veya boş/demo (rastgele sinyal); puanlanırsa Yürütme ~0 olurdu. Kısa notlar kod incelemesi raporunda. |
| CryptoTrade, FinMem, FinCon, AQAA (akademik) | Borsa emir yolu yok, yalnız simülasyon/backtest |
| Superalgos, nautilus_trader, vnpy | Çerçeve (strateji kullanıcıdan), derin incelenmedi |
| Infinite Bagholder | Depo erişilemedi, derecelendirilemedi |
| TraderAlice/OpenAlice, kyky2347/ALTA, FriesTrader, Oft3r/agentic-trading-desk, mnemox-ai/tradememory-protocol, moss-trade-bot-skills, gravit-agent, darwinia, gsuda-engine, trade-cast, AlphaSwarm, openclaw-workspace | Yalnız README/kısa tarama veya insan onaylı/broker'sız; yeterli kanıt yok ya da kapsam dışı |

## Uyarılar

- **Yalnız statik okuma:** Notlardaki tüm kod bulguları dosya okuma ve grep'e dayanır; hiçbir repo kurulmadı veya çalıştırılmadı. "Emir gönderir" demek "emir koduna ulaşılabilir" demektir; borsa tarafı davranışı doğrulanmadı.
- **Puanlar yargıdır:** Notlardaki kanıta dayanan, benim verdiğim yaklaşık değerlerdir; ölçüm değildir. Birkaç puanlık fark anlamsızdır. Kanıtı ince olan repolarda (tek commit, yeni, README ağırlıklı) puanları bilinçli olarak düşük tuttum.
- **Eksik veri:** Yıldız/son push değerleri arama dizininden, canlı depodan saatler/günler geride olabilir. Bazı repoların (chase-mew, jerome-benoit, AmpyFin vb.) lisansı notlarda yoktu; klonlardaki LICENSE dosyasına bakılarak dolduruldu, klonu olmayan chase-mew için "belirtilmemiş" yazıldı. Yıldız sayısı bilinmeyen repolarda Olgunluk puanı commit/test/bakım izlenimine dayanır.
- **Kanıt puanı kâr değil dürüstlüktür:** Hiçbir açık kaynak bot için bağımsız, çok aylı, maliyet sonrası kâr kaydı bulunamadı. Kendi verisini paylaşan projelerin çoğu zarar ediyor veya al-tut'u yenemiyor (Alpha Arena'da 6 modelin 4'ü büyük zarar etti).
- **Öğrenme gerçek avantaj demek değildir:** Kısa sürede tek piyasa rejiminde yükselen bakiye "öğrendi" ile "şanslıydı"yı ayırt etmez (bkz. Tur 3 raporu).
- **Kolaylık puanı** Türkiye'den Binance + Anthropic anahtarı varsayar; Türkiye'den Alpaca/Robinhood erişimi doğrulanmadı, bu yüzden hisse botlarında düşük tutuldu. Binance'in testnet uç noktası değişmiş olabilir (bazı notlarda demo.binance.com).
- Hukuki/vergi bilgisi için ana rapora bakın; bu dosya onu kapsamaz.


## Ek puanlama (2. tur)

Bu bölüm 2. turda eklendi. Yukarıdaki içerik değiştirilmedi. Aynı 8 kategori, aynı çıpalar ve aynı ağırlıklı ortalama kullanıldı; puanlar yalnızca `research_notes/diger-hesap/` ve `mimari-taslak.md` / `parca-plani-denetim.md` içindeki kanıta dayanır (yeni araştırma, kurulum veya çalıştırma yok). `puanlama.json` içinde bu kayıtlar `"tur": 2` alanıyla işaretlidir.

Kanıt gücü: agent-to-earn, regime-trading-bot ve guarded-trader için testler gerçekten çalıştırıldı (gorev6/6b: sırasıyla 203, 96 ve 47 test geçti; kapsam ölçüldü), bilinen delikler de çalıştırılarak doğrulandı. cryptobot, HydraQuant ve trading-terminal yalnızca statik okumaya dayanır. claude-trading-skills (beceri koleksiyonu) ve trialgate için yalnızca README/açıklama düzeyinde bilgi var; puanları bilinçli düşük tutuldu.

Bilinen delikler puana yansıdı: agent-to-earn `static_check` pandas/numpy ile dosya/ağ erişimini kaçırıyor (Güvenlik, Risk düşük) ve `beats_incumbent(None)` fail-open (Risk); regime-trading-bot LLM vetosu (grok_agent, strategy_state) testsiz ve geri alma/backtest kapısı çalışma zamanına bağlı değil (Öğrenme, Risk, Olgunluk düşük); HydraQuant öğrenilen parametreyi dry-run kapısı olmadan uyguluyor (Öğrenme tavanı 62).

Sütunlar: Fır = Fırsat bulma, Yür = Yürütme, Öğr = Öğrenme, Ris = Risk, Kan = Kanıt, Olg = Olgunluk, Güv = Güvenlik, Kol = Kolaylık.

| # | Repo | Borsa | Lisans | Fır | Yür | Öğr | Ris | Kan | Olg | Güv | Kol | **Genel** | En güçlü alan | Gerekçe ve kaynak not |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 1 | [Bachhsunkid/agent-to-earn](https://github.com/Bachhsunkid/agent-to-earn) | Binance USDⓈ-M vadeli (freqtrade, dry-run varsayılan) | MIT | 45 | 65 | 68 | 82 | 35 | 45 | 55 | 35 | **58** | Risk | Gece LLM döngüsü aday strateji yazıyor; kapı (gate.py) bütünlük kilidi, lookahead, ayrılmış dönem backtest, sabit-stake kıyas ve bekleme süresiyle terfi ettiriyor; risk kodu (guarded_strategy) ezilemez, 203 test geçti (gate %99). Delikler çalıştırılarak doğrulandı: static_check pandas/numpy ile dosya/ağ erişimini kaçırıyor, beats_incumbent(None) fail-open; ileri dry-run kapısı yok, getiri iddiası yok, 0 yıldız. (Kaynak: gorev1, gorev4, gorev6, gorev6b) |
| 2 | [ruiwang20010702/cryptobot](https://github.com/ruiwang20010702/cryptobot) | Binance vadeli (freqtrade, dry-run yapılandırması) | AGPL-3.0 | 80 | 58 | 65 | 45 | 15 | 50 | 55 | 25 | **54** | Fırsat bulma | En zengin veri/rol tasarımı (16 kaynak: funding, açık pozisyon, haber; boğa/ayı tartışması); strategy_advisor kapanan işlemlerden kural üretip LLM istemine koyuyor, TTL ve önce/sonra değerlendirmeyle yeniliyor/emekli ediyor; ama değerlendirme 2 işlemle yapılıyor, kural denetimi yok, sinyal dosyasında bayat sinyal hatası, sonuç yayımlanmamış, Şubat 2026'dan beri durağan. (Kaynak: gorev1, gorev4) |
| 3 | [ymcbzrgn/HydraQuant](https://github.com/ymcbzrgn/HydraQuant) | Binance/Bybit (freqtrade çatalı, dry-run) | GPL-3.0 | 60 | 65 | 62 | 65 | 15 | 40 | 50 | 12 | **53** | Yürütme | Kapanan işlem -> parametre -> canlı karar döngüsü kodda doğrulandı (forgone-alpha defteri, haftalık zarf sınırlı eşik uyarlaması, güven kalibratörü, otonomi merdiveni, Constitution); ~344 özgün test; ama öğrenilen parametre dry-run kapısı olmadan uygulanıyor, getiri etkisi kanıtsız, 70 bin satır ve freqtrade çatalı, kurulum ağır. (Kaynak: gorev1, gorev7) |
| 4 | [aplicy-com/guarded-trader](https://github.com/aplicy-com/guarded-trader) | Spot (freqtrade; veri arşivi Kraken, borsa notlarda doğrulanmadı); LLM emir veremez | Apache-2.0 | 25 | 50 | 10 | 82 | 50 | 60 | 85 | 20 | **42** | Güvenlik | Ölçüm ve güvenlik iskeleti: dsr/null/registry/walkforward %95-100 kapsamlı (47 test geçti, DSR bağımsız hesapla örtüştü), conductor risk/halt katmanı (~537 test iddiası), kendi stratejilerinin zararını açıkça yayımlıyor. Ama öğrenme/fırsat bulma yok (LLM kısmı stub), auto-flatten yok, ft_runner %0 test, spot ve Docker/uv kurulumu. (Kaynak: gorev1, gorev4, gorev6, gorev6b) |
| 5 | [danny123-sudo/regime-trading-bot](https://github.com/danny123-sudo/regime-trading-bot) | KuCoin (freqtrade, dry-run varsayılan) | MIT | 45 | 55 | 25 | 62 | 25 | 28 | 60 | 22 | **40** | Risk | Rejim sınıflandırıcı + LLM vetosu (fail-closed) + imzalı, sınırlı parametre güncelleme tasarımı iyi (96 test geçti, levers anayasası). Ama LLM vetosu (grok_agent, strategy_state) testsiz (%0 kapsam), geri alma/backtest kapısı çalışma zamanına bağlı değil, imza boşsa atlanıyor, tek commit, "henüz kârlı değil". (Kaynak: gorev1, gorev4, gorev6, gorev6b) |
| 6 | [Superior-Trade/trading-terminal](https://github.com/Superior-Trade/trading-terminal) | Hyperliquid (barındırılan Superior Trade API) | Apache-2.0 | 40 | 40 | 8 | 45 | 25 | 65 | 25 | 20 | **32** | Olgunluk | Grafikten LLM ile freqtrade stratejisi üretip doğrulayan hat (freqtrade-guard, metrics-honesty, 20 test + e2e eval, CI); öğrenme yok (strategy_log yazılıyor ama geri okunmuyor), kimlik doğrulaması bilerek yok, Sentry telemetrisi, yürütme üçüncü tarafta. Parça (güvenlik kuralları) olarak değerli, bot olarak değil. (Kaynak: gorev7) |
| 7 | [tradermonty/claude-trading-skills](https://github.com/tradermonty/claude-trading-skills) | Yok (ajan beceri koleksiyonu; emir yok) | MIT | 45 | 0 | 15 | 20 | 15 | 55 | 65 | 40 | **26** | Güvenlik | Otonom bot değil ("tam otomatik için tasarlanmadı"); crypto-regime-analyzer (anahtarsız rejim skoru), signal-postmortem (sonuçtan ağırlık geri beslemesi, testli), drawdown-circuit-breaker (testli) parça adayları. Yalnızca README ve SKILL.md açıklamaları okundu, kod ve testler incelenmedi; puanlar bilinçli temkinli. (Kaynak: parca-plani-denetim) |
| 8 | [0Smallcat0/trialgate](https://github.com/0Smallcat0/trialgate) | Yok (ölçüm aracı; freqtrade hyperopt çıktısını okur) | MIT | 0 | 0 | 0 | 0 | 25 | 12 | 65 | 25 | **8** | Güvenlik | Deflated Sharpe ve PBO/CSCV ile "bu sonuç şans mı" sorusunu yanıtlayan ölçüm aracı (guarded-trader dsr.py için yedek aday). Bot değildir, o yüzden bot kategorileri 0; yalnızca README okundu, kod/test incelenmedi, 0 yıldız, yeni. (Kaynak: gorev10, mimari-taslak) |

### Puanlanmayan adaylar (2. tur, kısa gerekçe)

| Depo | Neden |
|---|---|
| Sak-114514/freqtrade-agent | Lisans dosyası yok, öğrenme yok (yalnız sohbet belleği), API kimlik doğrulaması yok; yalnız araç/izin katmanı fikri alındı (gorev7) |
| 6Kmfi6HP/ft-userdata-llm-share | gorev1'de kısmen okundu (LLM giriş/çıkış çağrısı dosya:satır ile görüldü; yansıtma çıktısının isteme akışı izlenmedi), gorev7'de klonlanamadı; bir yıllık bayat (gorev1, gorev7) |
| shiyu-coder/Kronos | Bot değil, fiyat tahmin modeli; incelenmedi (parca-plani-denetim) |
| 0xemmkty/QuantMuse | Temmuz 2025'ten beri bayat, rozet doğrulanmamış (parca-plani-denetim) |
| jgardet/evotrade, Giansn/SYGNIF, pulse-freqtrade, freqtrade_dev_mcp | Canlı yol yok, lisanssız/dağınık veya tanıtım ağırlıklı; yalnız geçerken anıldı (gorev1) |
| coding-kitties/investing-algorithm-framework, loveolu/crypto-strategy-research, sunday-quant-scientist, nautilus_trader, je-suis-tm/quant-trading | Yalnız başlıkla anıldı, kod incelenmedi (gorev10) |

### Birleşik genel sıralama: ilk 15 (eski 53 + yeni 8)

Eşit puanda eski kayıt önce gelir. **Kalın** = 2. turda eklenen.

| # | Repo | Genel | En güçlü alan |
|---|---|---|---|
| 1 | 0xethanq/astra-quant-agent | 67 | Yürütme |
| 2 | rgg81/crypto-trade-claude-code | 65 | Öğrenme |
| 3 | **Bachhsunkid/agent-to-earn** | 58 | Risk |
| 4 | vedv0987-cloud/bvedtrade | 57 | Risk |
| 5 | suyunjing-su/r20-quantum-trader (astra aynası) | 57 | Fırsat bulma |
| 6 | HKUDS/Vibe-Trading | 57 | Risk |
| 7 | qrak/LLM_trader | 57 | Güvenlik |
| 8 | FilipeThome/the-trader-bot | 56 | Güvenlik |
| 9 | **ruiwang20010702/cryptobot** | 54 | Fırsat bulma |
| 10 | NoFxAiOS/nofx | 53 | Yürütme |
| 11 | freqtrade/freqtrade + FreqAI | 53 | Olgunluk |
| 12 | **ymcbzrgn/HydraQuant** | 53 | Yürütme |
| 13 | RafaelPF07/evotrader | 52 | Güvenlik |
| 14 | chase-mew/ai-hedge-fund | 51 | Güvenlik |
| 15 | 195440/nof1.ai | 50 | Yürütme |

Not: 2. turdaki repolar kısmen parça adayıdır; bu sıralama "tam otonom bot"a yakınlığı ölçer, parça olarak değerini değil (örneğin guarded-trader ve trialgate ölçüm/güvenlik parçası olarak mimaride kullanılır, ama bot olarak düşük puan alır).

## Mentor doğrulaması (16 Kasım 2026)

Kapsam: 2. turdaki 8 puan, eski ilk 15'in formül tutarlılığı, atlananlar listesi ve `mimari-taslak.md` içindeki parça seçimleri; dayanak `research_notes/diger-hesap/gorev1, 4, 6, 6b, 7, 10` ile Tur 3 notları. Yeni araştırma veya çalıştırma yapılmadı. 2. tur repolarının klonları bu oturumda yoktu; aşağıdaki hükümler notlardaki dosya:satır izlerine ve gorev6/6b çalıştırma sonuçlarına dayanır.

### Puan düzeltmeleri

Formül 61 kaydın hepsinde yeniden hesaplandı. Tek tutarsızlık yuvarlamadaydı: tam ,5 çıkan dört kayıttan üçü yukarı yuvarlanmış (39,5→40; 23,5→24; 48,5→49), biri aşağı (40,5→40). Kural "yarım yukarı" olarak sabitlendi. "En güçlü alan" sütununda hata yok.

| Repo | Değişen | Eski → yeni | Genel | Neden |
|---|---|---|---|---|
| AleksNovo/freqai-3ai-strategy | yalnız yuvarlama | — | 40 → 41 | Ağırlıklı ortalama 40,5; diğer ,5 kayıtlarıyla aynı kural |
| aplicy-com/guarded-trader | Öğrenme | 30 → 10 | 49 → 42 | Öğrenme döngüsü yok: LLM kısmı `NotImplementedError` (gorev4 G5). Çıpaya göre 25 bile "istatistiği modele göstermek" ister |
| | Kanıt | 62 → 50 | | Yayımlanan şey ileri kayıt değil, kendi backtest/walk-forward zararı. Çıpa 40 + ön kayıt ve null testi dürüstlüğü; 62 gerçek para kaydı olan passivbot ile eşitti |
| | Borsa alanı | "Binance spot" → "Spot, borsa doğrulanmadı" | | Notlarda Binance geçmiyor; veri arşivi Kraken (gorev6) |
| danny123-sudo/regime-trading-bot | Öğrenme | 35 → 25 | 42 → 40 | `process_proposal` ve geri alma izleyicisini testler dışında çağıran kod yok (gorev4 R1); çalışan botta yalnız ayar dosyası okunuyor. Emsal: varsayılan kapalı uyarlaması olan orallexa 15 |
| ruiwang20010702/cryptobot | Risk | 55 → 45 | 56 → 54 | Sert limit yalnız README iddiası, kodda okunmadı; kaldıraç ve lot LLM çıktısından geliyor, kural metni denetlenmiyor (gorev4 C1, C3) |
| tradermonty/claude-trading-skills | Öğrenme | 30 → 15 | 31 → 26 | Yalnız README okundu; geri besleme elle çalıştırılan beceri, canlı karara bağlı değil |
| | Risk | 30 → 20 | | Beceriler ajana tavsiye üretir, emri engelleyen kod yok (çıpa: "yalnız prompt" = 0) |

Dokunulmayanlar: agent-to-earn (58), HydraQuant (53), trading-terminal (32) kanıtla uyumlu. trialgate (8) formül olarak doğru, ama bot olmadığı için bu sayı kalite ölçüsü değildir; sıralamada atlas-gic ile aynı yerde durması yanıltıcıdır. agent-to-earn için iki çekince: Risk 82 testlerde sahte freqtrade nesneleriyle ölçüldü ve sabitler bizim kurallarımızdan gevşek (10x); Öğrenme 68 uçtan uca hiç çalıştırılmamış bir hatta dayanıyor (alt süreçler taklitli).

### Atlananlar

Atlama kararları doğru. İki not: ft-userdata-llm-share için "incelenemedi" gerekçesi yanlıştı, düzeltildi (gorev1'de kısmen okundu). freqtrade-agent tam okunmuştu ve puanlanabilirdi, ama lisanssız ve öğrenmesiz olduğu için sonucu değiştirmez.

### Parça seçimleri

| # | Parça | Hüküm | Gerekçe ve koşul |
|---|---|---|---|
| 1 | freqtrade | **Onaylandı** | Tabloda Yürütme 88, Olgunluk 98 ile rakipsiz. Açık nokta: Binance vadeli hiç denenemedi (HTTP 451); vadeli uçtan uca yalnız OKX'te görüldü |
| 3 | Kilitli risk: agent-to-earn `guarded_strategy.py` | **Onaylandı (uyarla)** | freqtrade içinde çalışan, testli (%98 kapsam, çalıştırıldı) ve kopyalanabilir tek aday. Riski daha yüksek puanlı Vibe-Trading freqtrade'e uymuyor; TEMPEST ve the-trader-bot lisanssız. Yapılacaklar: 10x → 3-5x, %1 → %2, sabit kodlu özsermaye tabanı, yalnız 1h/2h/4h izni (gün içi için dar), "SL likidasyondan önce" kontrolü dosyada açık bir kural değil, yazılacak. gorev6b: bot tarafı stopla %2 hedefi %2,5-3,2 çıktı (20x); borsa tarafı stop ve kayma payı gerekli |
| 4 | Piyasa durumu etiketi | **Değişmeli → regime-trading-bot `core/regime.py` + `indicators.py` uyarla** | "Kendimiz yaz" yerine MIT, testli (%87 ve %93 kapsam, çalıştırıldı) kod var. claude-trading-skills'teki rejim skoru okunmadı, kaynak olmamalı |
| 5 | Veto: regime-trading-bot R3 | **Onaylandı, ama kaynak etiketi düzeltilmeli** | Çalıştığına dair kanıtı olmayan tek parça: `grok_agent.py` ve `strategy_state.py` kapsamı %0, tek commit, anahtar yoksa veto atlanıyor. Çalıştığı görülen şey bizim gorev6b'deki dosya tabanlı sondamız (yok/bozuk/bayat → ret). Doğru tarif: "kendimiz yaz; R3'ten yalnız JSON sözleşmesi ve doğrulama mantığı". Sonda depoda yok, yeniden yazılacak. Daha iyi hazır aday yok |
| 6 | Funding / açık pozisyon | **Onaylandı** | Kendimiz; Binance vadeli açık uçları bu ortamdan sınanamadı |
| 7 | Kayıt defteri: guarded-trader `registry.py` | **Onaylandı (uyarla)** | %97 kapsam, çalıştırıldı. Şema "backtest öncesi deneme sicili"dir; ders ve değişiklik kaydına uyar. İşlemler freqtrade veritabanında kalmalı, buraya kopyalanmamalı |
| 8 | Ders servisi fikirleri: astra, cryptobot, HydraQuant | **Onaylandı, iki ek kaynakla** | Üçü de yalnız fikir (lisans). Eksik: tablonun Öğrenme birincisi TEMPEST (88; ders → DSR kapısı → terfi, Tur 3'te temel mimari seçilmişti) listede yok, fikir olarak eklenmeli (lisanssız, kod alınamaz). Kodu kopyalanabilen tek öğrenme kaynağı qrak/LLM_trader (MIT, Öğrenme 75). cryptobot'un 2 işlemle değerlendirmesi örnek alınmamalı |
| 9 | Sınır anayasası: regime-trading-bot `levers.py` | **Onaylandı (şablon)** | %94 kapsam, saf sabitler. Uygulayan kısım için `adaptive.py` içindeki kırpma ve yasak anahtar işlevleri testli ve çalışma zamanına bağlı; onlar da uyarlanabilir. Yasak listesine kendi risk anahtarlarımız eklenmeli |
| 10 | Ölçüm: guarded-trader `dsr.py`, `null.py` | **Onaylandı** | En sağlam kanıtlı parça (%100 ve %98 kapsam, sayılar bağımsız hesapla örtüştü). `null.py` backtest içindir; freqtrade'e bağlayan `ft_runner.py` %0 testli, bağlantı bizde. 4-8 haftada DSR 0,95'e ulaşamaz, yalnız "elendi / elenmedi" der |
| 10 | Yedek: trialgate | **Yedek sayılmamalı** | Yalnız README okundu, 0 yıldız, kod ve test görülmedi. `dsr.py` doğrulandığı için yedeğe gerek yok; tek katkısı PBO/CSCV, o da hyperopt eklenirse |
| — | Terfi kapısı (sonra): agent-to-earn `gate.py` | **Onaylandı (uyarla)** | `beats_incumbent(None)` terfiyi geçiriyor (çalıştırılarak doğrulandı), kapatılmalı. Parametre terfisinde `static_check` gereksiz |
| — | Risk eki: claude-trading-skills devre kesici | **Gerek yok** | A3'te günlük/haftalık/aylık kesici var; bu beceri okunmadı |

### Lisans

- **freqtrade GPL-3.0:** strateji ve onunla aynı süreçte çalışan her şey, dağıtılırsa GPL-3.0 olur. Yalnız kendi sunucumuzda çalıştırmak yükümlülük doğurmaz.
- **MIT (agent-to-earn, regime-trading-bot):** kopyalanan dosyada telif satırı ve MIT metni kalmalı. regime-trading-bot tek commit ve aynı adlı en az üç repo var (gorev10); asıl sahibi doğrulanmadı, kopyalamadan önce bakılmalı.
- **Apache-2.0 (guarded-trader):** lisans metni, varsa NOTICE ve değiştirilen dosyalarda değişiklik notu korunmalı. NOTICE dosyasının varlığı notlarda doğrulanmadı.
- **Yalnız fikir:** astra (AGPL + Commons Clause), cryptobot (AGPL), HydraQuant (GPL), TEMPEST ve freqtrade-agent (lisans yok). Kod, istem metni veya satır satır çeviri alınmamalı.
- trialgate ve claude-trading-skills için MIT bilgisi README düzeyinde; LICENSE dosyası görülmedi.

### Hâlâ doğrulanmayanlar

Binance vadeli dry-run (Frankfurt'tan erişim dahil); `guarded_strategy.py`'nin gerçek freqtrade altında içe aktarılıp çalışması; veto yolunun tamamı; guarded-trader conductor testleri (537 sayısı grep sayımı); cryptobot ve HydraQuant'ın tümü (yalnız statik okuma); trialgate ve claude-trading-skills kodu; ikiz eşleşmesi yalnız 8 işlemle görüldü. Hukuki görüş değildir.
