# Tur 5 - Topluluk (freqtrade/FreqAI), büyük projeler ve meta-labeling taraması

Tarih: 14 Kasım 2026. Yalnızca statik okuma (grep/okuma); hiçbir şey kurulmadı veya çalıştırılmadı. Klonlar: `scratchpad/clones/`. Yatırım tavsiyesi değildir.
Tur 3/Tur 4'te işlenenler (TEMPEST, astra, Passivbot, nofx, AmpyFin vb.) atlandı.

## Ana sonuç

Üç özelliği (kendi bulur + açar/kapatır + kendi işlemlerinden öğrenir) birlikte taşıyan, kanıtlı yeni bir "cevher" çıkmadı. Topluluk FreqAI stratejilerinin neredeyse hepsi piyasadan öğrenir (modeli canlıda yeniden eğitir), kendi kapanan işlemlerinden değil. İki repo "kendi sonuçlarından" kısmi geri besleme yapıyor. İleri yönlü (dry-run/canlı) sonucu doğrulanabilir hiçbir aday yok.

## Rubrik (1-5)

Otonomi / Öğrenme / Kanıt / Olgunluk / Güvenlik / Kullanım kolaylığı (Türkiye'de programcı olmayan, Binance, dry-run)

| Aday | Otonomi | Öğrenme | Kanıt | Olgunluk | Güvenlik | Kolaylık | Not |
|---|---|---|---|---|---|---|---|
| jerome-benoit/freqai-strategies (QuickAdapter, ReforceXY) | 4 | 3 | 1 | 4 | 4 | 2 | Binance, dry-run varsayılan, çok iyi belgeli; piyasadan öğrenir |
| CyberWei922/ai-trader-paper | 4 | 2-3 | 1 | 2 | 4 | 4 | Binance spot, dry-run, Windows çift-tık kurulum; kendi zararına göre lot küçültür |
| AleksNovo/freqai-3ai-strategy | 4 | 4 (kendi sinyal "sanal dosyaları" ile) | 1 | 3 | 3 | 1 | Bybit, varsayılan işlem yapmaz (veri toplar), çok karmaşık |
| SoloHard32/MEXC-AI-BOT | 4 | 3-4 | 1 | 2 | 2-3 | 3 | Yalnız MEXC spot; çevrimiçi öğrenme dry-run'da kapalı |
| Mohamed-sm/Freqtrade-RLStrategy-IA | 3 | 2 | 1 | 1 | 3 | 3 | 21 günlük %91,78 iddiası; reddedilmeye yakın |
| Superalgos | 2 | 2 | 1 | 3 | 3 | 2 | Strateji kullanıcıdan; ML yalnız tahmin/kitle testi |
| nautilus_trader | 1 (çerçeve) | 1 | 1 | 5 | 4 | 1 | Hazır öğrenen bot yok |
| vnpy (alpha) | 1 | 2 | 1 | 4 | 3 | 1 | Hisse/geri test araştırma kiti, kripto canlı örneği yok |

## Aday bölümleri

### 1) jerome-benoit/freqai-strategies (64 yıldız, GPL benzeri lisans belirtilmemiş: `license` boş, tek commit, 14 Kas 2026)
- README iddiası: iki strateji (QuickAdapter: zigzag uç noktası regresyonu; ReforceXY: RL politikası MaskablePPO). "Kârlılık kanıtı değildir" diye açıkça yazıyor (`README.md` başı).
- Kodda doğrulandı: `dry_run: true`, borsa binance, spot, 5m (`quickadapter/user_data/config-template.json:12,47`). Karar verici: XGBoost modeli (`QuickAdapterV3.py`, `QuickAdapterRegressorV3.py`). Öğrenme: `live_retrain_hours` şablonda yorum satırı (`config-template.json:94`), `continual_learning` varsayılan false (`quickadapter/README.md:345`). Yani canlı yeniden eğitim varsayılan AÇIK DEĞİL, açılması gerekir. Kendi işlemlerinden öğrenme yok; yalnız freqtrade koruma kuralları (MaxDrawdown, StoplossGuard, `QuickAdapterV3.py:378,390`) kapanan zararlara tepki veriyor (öğrenme değil, devre kesici).
- Risk: custom_stoploss/custom_exit/protections var; API sunucusu şablonda kapalı. Güvenlik temiz görünüyor.
- Yorum: topluluğun en olgun ve dürüst FreqAI paketi; yine de "kendi işlemlerinden öğrenen" değil.

### 2) CyberWei922/ai-trader-paper (GPL-3, tek commit, Temmuz 2026)
- README iddiası: Binance spot, 100 USDT sahte para, `dry_run: true`, yapay zeka + trend/hacim/spread filtreleri, kâr garantisi yok (Çince).
- Kodda doğrulandı: `config.example.json:12,43` dry-run + binance; FreqAI `live_retrain_hours: 6`, `continual_learning: false` (satır 105-109); `can_short=False`, stoploss -%0,75 (`SmallCapitalFreqAI.py:35,50`). Kendi işlemlerinden geri besleme: son N saatte kapanan zararlı işlemler sayılıp lot 8 USDT'ye düşürülüyor (`SmallCapitalFreqAI.py:471-486`) ve günlük/toplam zarar tavanı var (`:528,536`). Bu öğrenme değil, kural tabanlı uyum, ama kendi sonuçlarını canlı kararda kullanıyor.
- Kurulum: Windows `.cmd`/`.ps1` betikleri `pip install freqtrade[freqai]==2026.6` yapıyor (`scripts/setup.ps1:27-28`); api_server 127.0.0.1, şifreler "ilk kurulumda üretilir". Anahtar yok.
- Yorum: kullanım kolaylığı en yüksek Binance-dry-run adayı; Çince README (çeviri gerekir); kanıt yok.

### 3) AleksNovo/freqai-3ai-strategy (GPL-3, 2 yıldız, Eylül 2026)
- README iddiası: 3 ML ajanı; Ai2 (giriş filtresi) ve Ai3 (çıkış yöneticisi) her sinyalin sanal 60/360 dk "dosyası"ndan öğrenir (hayatta kalma yanlılığı yok). Bu, "kendi sinyallerinin sonuçlarından öğrenme"nin en yaratıcı biçimi.
- Kodda doğrulandı: mimari ve bakım/yeniden eğitim döngüsü var (`maintenance.py`, `Arbiter.py`, `ExitModel.py`; `settings.py` `MODE_PROFILES`); `live_retrain_hours` 96 (README:581); varsayılan `strategy_mode: module1_only` yani işlem açmaz, yalnız veri toplar (`config.json:7`); borsa Bybit (`config.json:50`), yalnız LONG; "ticari sonuçlar yayımlanmıyor" diye açık yazıyor (README:628). Anahtarlar `${BYBIT_API_KEY}` ortam değişkeni. Binance'e uyarlama ister (coin_filter vb.).
- Yorum: fikir olarak değerli (tasarım örneği), kullanıma hazır değil.

### 4) SoloHard32/MEXC-AI-BOT (MIT, tek commit, Nisan 2026)
- README iddiası: otonom MEXC spot botu, GUI, risk guard, otomatik parametre uyumu, çevrimiçi öğrenme.
- Kodda doğrulandı: `DRY_RUN` varsayılan True (`mexc_bot.py:947`); kapanan işlem sonucu sembol kalite EMA'sına, kayıp serisine, karantinaya işleniyor (`:5125-5160`, `:7362`) = gerçek "kendi işleminden" geri besleme. Ancak model güncellemesi `not runtime_dry_run` şartına bağlı (`core/ai_signal.py:~690`): dry-run'da model öğrenmiyor, yalnız log tutuyor. Tek dosya 8700 satır. Borsa MEXC (Binance değil).
- Yorum: Binance dışı ve olgunluğu düşük; fikir kaynağı.

### 5) Büyük projeler
- Superalgos: kullanıcı strateji tasarlar (kendi bulmaz); ML = Bitcoin-Factory kitle tahmin testi + RL belgesi (`Bitcoin-Factory/ReadMeReinforcementLearning.md`), canlı otonom öğrenen bot değil. Son push Mayıs 2026.
- Nautilus Trader: `docs/concepts/overview.md:42` "RL ajanları eğitmek için simülasyon" diyor; hazır adaptif strateji örneği yok. Çok olgun çerçeve, programcı gerektirir.
- vnpy: `vnpy/alpha` yalnız çok faktörlü hisse alfa araştırma/geri test (lasso/lgb/mlp, tek demo strateji `equity_demo_strategy.py`); kripto otonom bot değil.

## Reddedilenler

- Dukesan-ai/crypto-ml-trading-framework: meta-labeling ve "gerçek parayla canlı" iddiası ama yalnız belge, sinyal kodu kasıtlı yok; doğrulanamaz.
- NeillBotushanski/alphaforge: kendi kendine öğrenen ABD hisse botu iddiası, ama kaynak kod özel (yalnız README/doküman).
- Mohamed-sm/Freqtrade-RLStrategy-IA: "%91,78 kazanma" 21 günlük, 50 USD'lik, 78 işlemlik dry-run beyanı; tek strateji dosyası, `live_retrain` yok, sabit stoploss. Güvenilir kanıt sayılmaz (düşük hacim, kazanma oranı sahte rahatlık: çıkış kuralı kârları erken alıp zararı tutuyor olabilir).
- Aenger-priv/ContextualBandits: FX, 1 yıldız, kripto değil.
- PetteKay/ai-forex-trading-bot: MT5 forex.
- markdregan/FreqAI-Marcos-Lopez-De-Prado: meta-labeling fikri ama proje "artık geliştirilmiyor"; yalnız referans.
- Bederf/leah-freqtrade-strategies: README'deki sonuçlar geri test; canlı yeniden eğitim 24 saat ama strateji ağırlıklı kural/momentum; kanıt geri testten ibaret.
- remiotore/ccxt-freqtrade, RoboticAutomations/freqtradestrategies vb. toplu strateji kopyaları: tekil bakım/kanıt yok (kod aramasında göründü, incelenmedi).
- Bandit/online-learning/"performans ağırlıklı topluluk" aramaları: ≥1 yıldızlı, bakımlı, kripto kullanılabilir repo çıkmadı (en iyi sonuçlar 0-2 yıldız).

## Yöntem ve sınırlar

- `gh search/repositories` (pushed>2025-06), 17 sorgu; `search/code` 1 sorgu (freqai + Trade.get_trades); 1 WebSearch (FreqAI sonuç/ranking): strat.ninja/FrequentHippo canlı sonuç içeren FreqAI sıralaması bulunamadı, sonuç sayfaları ağırlıkla blog/rehber. `freqai ReinforcementLearner` ve `continual_learning` repo aramaları boş döndü (topic bazlı arama zayıf).
- 8 repo (+3 büyük proje) klonlandı, hedefli grep. Bazı repolara API erişimi kısıtlıydı (markdregan, CyberWei922 meta verisi 403); yıldız sayısı bu ikisi için doğrulanamadı, commit tarihleri git log'dan.
- Statik okuma: çalışma zamanı davranışı doğrulanmadı. Hiçbir adayda ileri yönlü, maliyet sonrası gerçek sonuç yok.
- Öneri: Tur 4 sırası değişmez (freqtrade+FreqAI dry-run). Binance dry-run için jerome-benoit QuickAdapter ve CyberWei922 yapı olarak denenebilir; "kendi sinyallerinden öğrenme" fikri için AleksNovo mimarisi tasarım referansı.
