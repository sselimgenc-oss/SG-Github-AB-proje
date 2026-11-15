# Tur 5 - Forklar ve yeni repolar (2026-06-01 sonrası)

Tarih: 14 Kasım 2026. Yalnız statik okuma; hiçbir kod kurulmadı/çalıştırılmadı. Yatırım tavsiyesi değildir.
Klonlar: `.../scratchpad/clones/<sahip>-<repo>` (depth 50).

## Kısa sonuç

- Fork avında anlamlı sapmış (öğrenme/yansıma ekleyen) fork **bulunamadı**. Forklar ya yıllar önce durmuş ya da upstream'in kopyası.
- Yeni repolarda iki gerçek aday çıktı: **bvedtrade** (kendi işlemlerinden öğrenen, Binance demo) ve **the-trader-bot** (kendi canlı sonucuna bakıp stratejiyi susturan, Binance spot testnet). İkisi de tek kişilik proje, kazanç kanıtı yok; ikisi de kendi kötü sonuçlarını dürüstçe yazıyor.
- Üç özelliği (TA + otomatik aç/kapat + kendinden öğrenme) birden olgun biçimde taşıyan repo yine yok.

## Rubrik tablosu (1-5; 5 en iyi)

| Repo | Otonomi | Öğrenme | Kanıt | Olgunluk | Güvenlik | Kullanım kolaylığı | Not |
|---|---|---|---|---|---|---|---|
| vedv0987-cloud/bvedtrade | 4 | 4 | 2 | 3 | 4 | 2 | Binance demo/futures; öğrenme kodda doğrulandı; kurulum ağır |
| FilipeThome/the-trader-bot | 4 | 3 | 2 | 4 | 5 | 3 | Binance Spot Testnet varsayılan; "canlı sonuç stratejiyi susturur" |
| RafaelPF07/evotrader (ABD ETF) | 3 | 4 | 3 | 4 | 5 | 3 | Yalnız sahte (simüle) hesap, aracı kurum bağlantısı yok |
| Nikhilperr/binance-futures-trading-bot | 4 | 3 | 1 | 1 | 1 | 3 | Öğrenme var ama 20x kaldıraç + bakiyenin %95'i |
| Max007-coder/quantbot | 3 | 1 | 1 | 2 | 3 | 3 | Öğrenme yok (aşağıda reddedilenler) |

## 1) vedv0987-cloud/bvedtrade (en ilginç gizli cevher)

Tek yazar, 50 commit, 2026-08'e kadar aktif, lisans dosyası yok, ~0 yıldız (arama sonucunda ilk sayfada çıkmadı; gizli).

**README iddiası:** "Kurumsal AI trading ekosistemi", 11 ajanlı NVIDIA NIM modelleri, tarayıcı, TA, SMC, journal, koç; 29 faz.

**Kodda doğrulandı:**
- Varsayılan güvenli: `backend/config.py:95` `binance_testnet: bool = True`; gerçek paraya geçmek için ikinci bir kilit (`live_trading_ack`, `config.py:99-110`) - yanlış yazılırsa uygulama hiç açılmıyor.
- Emir: spot motoru `backend/spot/engine.py:1359` (`order_market_sell`), futures `backend/hft/executor.py:306,328,469` (`futures_create_order`, borsa tarafı SL/TP ile). Spot motoru "vendor/binbot" adlı gömülü bir bottur (RSI/BB/MACD tabanlı).
- Karar veren: gerçek kodda TA/rejim sinyali; LLM yolu kapalı (`config.py:229` `ai_trading_enabled=False`; `LIVE_STATE.md` "AI path dead"). Yani LLM karar vermiyor, bu iyi (maliyet yok).
- Öğrenme (iki ayrı katman):
  1. `backend/ai/learning_engine.py` (340 satır): her kapanan işlem `trade_recorder.py:97-117` ile `record_outcome`'a gidiyor; rejime göre güven düzeltmesi, risk çarpanı, "engellenen strateji" üretiyor; zamanla azalan ağırlık (yarı ömür 14 gün). **Canlı kararı etkiliyor:** `backend/hft/risk_gate_v2.py:196-215` stratejiyi engelliyor veya skoru kaydırıyor. Ama bu yol HFT (futures scalper) için ve `hft_enabled=False` varsayılan.
  2. Gömülü spot botta (`vendor/binbot/ml.py:1765-1840`): işlem sonucundan Q-öğrenme (`reward()`), `should_block()` ile giriş engelleme, her 20 işlemde MLP yeniden eğitimi; `monitors.py:380` haftalık eşik (RSI/BB) otomatik ayarı; ML 6 saatte bir yeniden eğitim. Bunlar spot motorunun içinde, yani şu an "çalışan" kısım.
- Sert riskler: `MAX_DAILY_LOSS_PCT=0.05` (`vendor/binbot/config.py:489`), `max_drawdown_from_peak=0.12`, `kill_switch_consecutive_losses=8` (`config.py:210`), kill switch spot'a 2026-08-28'de bağlanmış (`LIVE_STATE.md`).
- Kanıt (yazarın kendi dürüst yazısı): `STRATEGY.md:19-21` HFT sinyali 634 gerçek işlemde %27,1 isabet, beklenti -0,55R (rastgeleden kötü); `AUDIT.md:115`. Gerçek para 2026-08-03 başladı, 08-27'de sonlandı, demo'ya dönüldü. Spot motorunun ayrı kâr/zarar kaydı bulunamadı.
- Güvenlik: referans kodu/telemetri/obfuscation bulunmadı (grep). Kırmızı bayrak: `DASHBOARD_AUTH_DISABLED=true` (yazar isteğiyle; dışarı açılırsa tehlikeli, yazma API'si ayrı başlıkla korunuyor), repoda alakasız dosyalar (YouTube html, PDF), lisans yok.
- Kullanım: Linux VM + Redis/Postgres/Caddy/Celery, 3 .env, 6 NVIDIA anahtarı gerekir; programcı olmayan için zor (2).

## 2) FilipeThome/the-trader-bot

Tek yazar, 51 commit, son 2026-11-03, lisans yok, 0 yıldız. Vibe-Trading'in (HKUDS) emir kapısı modülünü uyarlamış (`ORIGIN.md`).

**README iddiası:** USDT çiftlerini analiz eder; emir yalnız "order gate" üzerinden; panel borsayla konuşmaz.

**Kodda doğrulandı:**
- Varsayılan testnet: `bot/config.py:209` `mode: Mode = "testnet"`; üretim için 30 günlük testnet geçmişi, >=30 işlem, pozitif ortalama R, Monte Carlo drawdown kapısı ve "PRODUCAO" yazısı (`bot/promotion.py:1-40`, README satır 55).
- Karar veren: deterministik stratejiler (`bot/strategies/`: momentum, trend, mean_reversion, intraday, day, funding...). DeepSeek yalnız tavsiye verir, karar motoru kodda (README "DeepSeek advisor").
- Öğrenme (dar ama gerçek): `bot/decay.py:77-128` `review_strategy` - canlı 30 günlük Sharpe backtest'in yarısının altındaysa veya son 20 işlemin ortalama R'si negatifse stratejiyi "sadece sinyal" moduna indirir; `bot/runtime.py:836-846` günde bir çalışır; çift bazlı da (kayma, beklenti) engeller (`decay.py:131`). Bu bir **frenleme** döngüsü: kendini iyileştirmez, kötü giden stratejiyi kapatır. Parametre ayarlama/yeniden eğitim yok.
- Sert limitler: günlük %2 kayıp, günde 8 işlem, zarardan sonra 60 dk bekleme, toplam açık risk %6 (README 100-110), halt bayrağı, yürütme günlüğü, hash zincirli kayıt.
- Kanıt: README satır 176-182: 90 günlük backtest'te BTC/ETH/SOL hepsi zarar; 9 volatil çiftte 18 testten 1'i geçti = şans seviyesi. Bot geçmeyen şeyi gerçekten işlemiyor.
- Güvenlik: anahtar sızdırma/yönlendirme kodu görülmedi (dış HTTP yalnız Binance/DeepSeek). Panel arayüzü Portekizce; Node 22 + Python 3.12 gerekir.

## 3) RafaelPF07/evotrader (ABD hisse/ETF, ikinci öncelik)

25 commit, 115 test + CI, lisans yok. Yalnız günlük **simüle** hesap (`src/evotrader/paper/trader.py`); aracı kurum/borsa anahtarı yok, gerçek emir yok.
- Öğrenme kodda doğrulandı: günlük SQLite günlüğü, kayıp işlem analizi (`paper/learner.py:111`), üç ayda bir yeniden evrim, yeni strateji ancak ayrılmış veride `promote_margin=0.10` farkla kazanırsa terfi (`learner.py:162-176`, `trader.py:165-182`). Yani canlı karara geri besleniyor.
- Kanıt: README kendisi "al-tut'u yenemiyor", ML sinyali yazı-tura (AUC ~0,51), deflated Sharpe: hiçbir kazanç anlamlı değil; ileri test 22 Eylül 2026'da başladı, 24 ay sonra yargılanacak. Dürüstlük 5, kazanç 0.
- Gün içi/scalp değil (günlük bar). Binance'e uygulanmaz; hisse için "öğrenen çerçeve" örneği.

## 4) Nikhilperr/binance-futures-trading-bot (öğrenme var, güvenlik yok)

2 commit, 3 yıldız, 2026-06-23.
- README: "self-learning"; kodda doğrulandı: `modules/learning_engine.py:280-322` her sinyal x saat için son 30 günün isabetinden ağırlık hesaplıyor; `main.py:629-634` her 20 işlemde çağrılıyor; ağırlıklar `signals.py:302-311` ile giriş skoruna giriyor. Yani gerçekten geri besleme var.
- Varsayılan mod "test" (`modules/state.py:34`) ama `USE_TESTNET` varsayılanı false (`config.py:15`).
- Kırmızı bayraklar: `LEVERAGE=20`, `RISK_PER_TRADE=0.95` (bakiyenin %95'i) (`config.py:28-29`), amaç "10 USDT'yi 10 katına", dashboard `host="0.0.0.0"` (`dashboard.py:84`) ve kimlik doğrulama yok. Kumar profili; yalnızca öğrenme mantığını okumak için değerli.

## Reddedilenler

| Repo | Neden |
|---|---|
| Max007-coder/quantbot | 5 commit, öğrenme yok (yalnız journal/istatistik), Binance spot + MT5 + Solana; Tur 4 eşiğinin altında |
| roclee2692/autonomous-spot-trading-agent | Disiplinli (IP beyaz liste, hash zincirli günlük) ama yalnız BTCUSDT grid, öğrenme yok, 4 commit |
| IslamBaraka90/Super-Agent-Trading-Bot | 2 commit, LLM ajan, yalnız paper, öğrenme/yansıma bulunamadı |
| boredom198/thesis-ai-trading-agent | Hackathon projesi, 2 commit, öğrenme yok |
| sopersone/cabbage-trading-machine | 2 commit; Investing Algorithm Framework'ün 1419 dosyalık kopyası, öğrenme yok |
| Maazullah8/AI_Self_Improving_Bot | Öğrenme döngüsü tasarımı iyi (journal-hipotez-terfi) ama MT5/forex, sentetik demo, Binance yok |
| Aswin-Ram-K/algo-trading-bot | 3 commit, HANDOFF "paused", HMM planı yarım |
| danderson197874/apex-crypto-bot | Coinbase; `log_shipper.py:5` logları üçüncü taraf siteye POST ediyor (telemetri/sızıntı riski) - kırmızı bayrak |
| CaptainNahin/Trading-bot ("%90+ doğruluk") | Abartılı iddia, spam işareti |
| Ricardokarma/claude-trading-bot | Web tarayıcı/ısı haritası, otomatik emir döngüsü yok |
| janitoff0/ninjatrader-bot (1104 yıldız), Polytutor-AI-Labs/*, Nour-Br/*, TradePilot | Yıldız patlaması + anahtar kelime doldurma; spam/reklam/airdrop görünümü |
| 0xethanq/astra-quant-agent forkları (10 adet) | Ekim 2026'da toplu kopya; sapma yok (Tur 4'te zaten kapsandı) |
| nofx forkları (nofxai, fsinbad, gale-crypto, OrienSpec...) | Commit geçmişi upstream'in aynısı; fsinbad'ın son commit'i "enjekte edilmiş kötü amaçlı workflow (GhostAction) silindi" - nofx forklarında CI güvenliği riski |
| passivbot forkları (djienne, msei99, tedyptedto) | djienne: HYPE/Hyperliquid dağıtım ayarları; msei99: Şubat 2026'dan beri upstream; ikisi de öğrenmesiz grid |
| freqai-strategies forkları, emergentmethods/freqai | Boş/eski kopyalar (en son 2025-07) |
| nof1 forkları (MaoTouHU/Nof1OpenAI 19 yıldız vb.) | 2025'te durmuş kopyalar |
| Apex-prim/strategy-audit | Bot değil; ama yararlı kanıt: 895 herkese açık freqtrade stratejisi örneklem dışı denetlendi, "iki tanesi her testten geçiyor" (okunmadı, yalnız açıklama) |
| Superior-Trade/trading-terminal (1093 yıldız) | Hyperliquid terminali; Binance değil; derin okunmadı |

## Yöntem / kısıtlar

- **`gh api repos/<sahip>/<repo>/...` (forks, compare) tüm depolarda HTTP 403 verdi** ("GitHub access to this repository is not enabled for this session"). Bu yüzden ahead-by karşılaştırması ve fork listesi API'den alınamadı. Yerine: `search/repositories` (çalıştı; `X in:name fork:only` biçimi) ve klonlanan forkların commit geçmişi/yazarları. Sonuç: fork sapması yalnız commit mesajlarından tahmin edildi, sayısal ahead-by yok.
- `search/repositories` çalıştı; `gh auth status` "Failed" yazdı ama arama yine döndü. Bazı sorgular (OR'lu veya `stars:>` birleşimleri) boş döndü; daha basit sorgularla yeniden denendi. Arama hız sınırına takılınmadı (~9 sn aralık).
- Kod araması (`search/code`) kullanılmadı; web araması yapılmadı. Tarama kapsamı: 2026-06-01 sonrası ~12 sorgu, her biri ilk 10-15 sonuç. Düşük yıldızlı iyi repolar kaçmış olabilir.
- 18 repo klonlandı, hiçbiri çalıştırılmadı. Okunan: README, ana karar/öğrenme/risk dosyaları, `grep` ile güvenlik taraması (referans kodu, eval/exec, curl|sh, base64, dış POST). Büyük depolarda (bvedtrade 340 py dosyası) tüm kod okunmadı; doğrulananlar yukarıda dosya:satır ile verilen kısımlardır.
- Hiçbir adayda bağımsız doğrulanmış kâr kaydı yok; "Kanıt" puanları dürüstlük/test titizliğini yansıtır, kazancı değil.
