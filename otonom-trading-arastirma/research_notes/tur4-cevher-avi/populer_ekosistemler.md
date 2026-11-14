# Tur 4 - Popüler ekosistemler (freqtrade, OctoBot, Jesse, Hummingbot, ITB, NFI, Lumibot)

Yöntem: yalnızca statik okuma (grep/okuma); hiçbir şey kurulmadı/çalıştırılmadı. Klonlar: `scratchpad/clones/`. Yıldız sayıları bu oturumda GitHub API erişimi kapalı olduğu için doğrulanmadı (genel bilgiye göre freqtrade ~40k+, OctoBot/Jesse/Hummingbot binler seviyesinde - "README iddiası/tahmin"). Yatırım tavsiyesi değildir.

Etiketler: **[KOD]** = kodda doğrulandı, **[README]** = yalnız belge/README iddiası, **[YAPILMADI]** = bu turda incelenmedi.

## Puan tablosu (1-5)

| Aday | Otonomi | Öğrenme | Kanıt | Olgunluk | Güvenlik | Kolaylık | Toplam /30 |
|---|---|---|---|---|---|---|---|
| freqtrade + FreqAI | 3 | 4 | 2 | 5 | 4 | 3 | 21 |
| NostalgiaForInfinity (freqtrade stratejisi) | 5 | 1 | 3 | 5 | 4 | 4 | 22 (öğrenme yok) |
| intelligent-trading-bot (ITB) | 4 | 2 | 2 | 2 | 3 | 2 | 15 |
| OctoBot | 3 | 1 | 2 | 4 | 4 | 5 | 19 |
| Jesse | 1 | 2 | 2 | 4 | 3 | 2 | 14 |
| Hummingbot (V2 controller) | 3 | 1 | 2 | 4 | 3 | 2 | 15 |
| Lumibot | 1 | 1 | 1 | 4 | 3 | 2 | 12 |
| Superalgos, nautilus_trader, vnpy | - | - | - | - | - | - | [YAPILMADI] |

Ana sonuç: bu popüler çerçevelerin hiçbiri "stratejiyi kendin bulur + işlem sonuçlarından öğrenir" isteğini kutudan çıkar çıkmaz karşılamıyor. En yakını **freqtrade + FreqAI**: model canlıda düzenli yeniden eğitiliyor, ama "alım/satım kuralı" (modelin tahminini eşiğe bağlayan kısım) yine bir strateji dosyasında yazılı.

## freqtrade + FreqAI (en yakın "klasik ML" seçeneği)

- Ne yapar: Freqtrade kendi başına emir açıp kapatan, çok olgun bir bot. FreqAI eklentisi fiyat/gösterge verisinden bir ML modeli eğitip "önümüzdeki N mumda fiyat ne olur" tahmini üretiyor.
- Nasıl öğrenir: 
  - Kayan pencereyle canlı yeniden eğitim: `freqtrade/freqai/data_kitchen.py:559` (`elapsed_time > live_retrain_hours` ise yeniden eğit), pencere `train_period_days` (satır ~561). **[KOD]**
  - Sürekli öğrenme (önceki modelden devam): `freqai_interface.py:99` (`continual_learning`) ve `:784` (önceki model başlangıç noktası). **[KOD]**
  - Model eskirse kullanmayı bırakma: `data_kitchen.py:524-535` (`expiration_hours`). **[KOD]**
  - Hazır modeller: LightGBM, XGBoost, RandomForest, PyTorch MLP/Transformer ve pekiştirmeli öğrenme (PPO/A2C/DQN) - `freqtrade/freqai/prediction_models/`, `RL/BaseReinforcementLearningModel.py:36`. **[KOD]**
- Önemli ayrım: Öğrenilen şey "piyasa verisinden fiyat tahmini". Botun kendi kapanmış işlemlerinin kâr/zarar kaydı modele geri beslenmiyor (RL ortamı simülasyon üzerinde eğitiliyor). Yani "kendi işlem günlüğünden ders çıkarma" yok. **[KOD, okuma temelli]**
- Giriş/çıkış kuralı kullanıcıdan: örnek strateji `freqtrade/templates/FreqaiExampleStrategy.py:238-261` (`do_predict == 1` ve `&-s_close > 0.01` ise al; `< 0` ise çık). Eşikler elle yazılmış. **[KOD]**
- Güvenlik: örnek yapılandırmada `dry_run: true` (`config_examples/config_freqai.example.json:10`). Strateji şablonunda `stoploss = -0.05`. **[KOD]** Sabit risk limitleri (max_open_trades, stoploss) var ama kullanıcı koyuyor.
- Kanıt: Belge kendi "Disclaimer"ını koyuyor (`docs/freqai.md:13`); RL örnek ödülü için "canlı üretim için değil" uyarısı var (`prediction_models/ReinforcementLearner.py:112-117`). Yayınlanmış canlı sonuç yok; topluluk raporları karışık. **[KOD/README]**
- Zayıflıklar: Kurulum ve ayar bilgisi gerekir (Python/Docker, JSON, strateji dosyası). Aşırı uyum riski yüksek; tahmin doğruluğu kâra çevrilmeyebilir. Binance/OKX/Bybit destekli (ccxt) - tam liste doğrulanmadı **[README]**.
- Topluluk eklentileri (popüler FreqAI stratejileri): **[YAPILMADI]** bu turda tek tek incelenmedi.

## NostalgiaForInfinity (NFI)

- Ne yapar: Freqtrade için dev bir kural tabanlı strateji (5 dakikalık mum, 6-12 açık işlem önerisi, 40-80 çiftlik havuz) - `README.md` "General Recommendations". **[KOD/README]**
- Öğrenir mi? Hayır. FreqAI'ye hiç atıf yok (README ve `NostalgiaForInfinityX7.py` içinde "freqai" araması boş). Parametreler geliştiriciler tarafından elle güncelleniyor; kullanıcı için `tools/checkupdates.sh` yeni sürümü indirir - bu "öğrenme" değil, el ile ayar yayını. **[KOD]**
- Otonomi çok yüksek: sinyal, alım, satım, DCA/yeniden alım hepsi içinde. Örnek yapılandırmalar `dry_run: true` (`configs/exampleconfig.json:5`). Eski sürümde `stoploss = -0.99` (`NostalgiaForInfinityX.py:131`) - yani fiilen stop yok, risk "tut ve ortalama" mantığına dayanıyor. **[KOD]**
- Zayıflık: Backtest sonuçları commit yorumlarında; canlı doğrulama yok. Bunu "adaptif değil ama en olgun, sıfır-strateji-yazma" taban çizgisi olarak düşünün.

## intelligent-trading-bot (asavinov)

- Ne yapar: ML ile al/sat sinyali üretir (etiketler: `topbot2` tepe/dip, `src/itb/scripts/labels.py`), Binance (`src/itb/outputs/trader_binance.py:26`) ve MT5 için emir verici var, simülasyon çıktısı `trader_simulation` (`configs/config-sample-1h.jsonc:127`). **[KOD]**
- Öğrenme: Eğitim ayrı komutlarla yapılıyor (`train.py`, `predict_rolling.py`); canlı sunucu eğitmiyor: `src/itb/service/server.py:132` ("Server does not train - it only predicts"). Yani periyodik yeniden eğitim otomatik değil, elle/zamanlayıcıyla yapmanız gerekir. "rolling_predict" geriye dönük değerlendirme içindir (`config-sample-1h.jsonc:150`). **[KOD]**
- Zayıflık: Az sayıda borsa, dokümantasyon ve test zayıf, tek geliştirici; Binance işlem kodunda test emri yolu var (`trader_binance.py:389` "Submitting test order") ama varsayılan güvenlik/limit doğrulanmadı. Pazar/kanal tanıtımı README'de (sinyal Telegram kanalı) - kanıt değil.

## OctoBot (Drakkar-Software)

- Ne yapar: Kullanımı en kolay arayüzlü bot (web UI, paper trading varsayılan önerisi - `README.md:70,94,230`). Modlar: grid, DCA, TradingView sinyali, `ai_trading_mode` (LLM ajan ekibi: `packages/tentacles/Trading/Mode/ai_trading_mode/`). **[KOD]**
- Öğrenme: Ana modlarda yok. AI modu LLM'e dayanıyor (Tur 1-3'te kapsandı); sonuçlardan öğrenme döngüsü bu turda doğrulanmadı. Dahili "strategy optimizer" backtest ile parametre arama, canlı öğrenme değil; README'ye göre backtest yalnız "manual OctoBot"larda **[README]**.
- Zayıflık: Bulut ürünü (octobot.cloud) yönlendirmeleri çok; ücretsiz çekirdek kısıtlı hissettirebilir.

## Jesse

- Kendi stratejinizi yazarsınız (`README.md:21` "YOUR OWN trading strategies"); `optimization_controller.py` genetik parametre arama yapar - çevrimdışı. Canlı/paper var **[README]** (canlı işlem eklentisi ücretli olabilir - doğrulanmadı). Otonomi ve öğrenme düşük; kullanıcının isteğine uymuyor.

## Hummingbot (V2 controller'lar)

- `controllers/directional_trading/` altında kural tabanlı örnekler: `bollinger_v1/v2`, `macd_bb_v1`, `supertrend_v1`, `dman_v3`. Hepsi sabit göstergeli; ML/uyarlama yok (controllers içinde ML araması yalnız market making'de parametre adı eşleşmesi). **[KOD]** Asıl güçlü olduğu alan piyasa yapıcılık; kurulum zor. Sistem yeniden öğrenmez.

## Lumibot

- Sadece örnek `lumibot/example_indicators/ml_direction.py`; hisse/opsiyon ağırlıklı çerçeve, otonom öğrenen bot değil. **[KOD, yüzeysel]**

## Öneri (bu avcılık sahasından)

1. Gerçekten "model canlıda yeniden eğitilsin" istiyorsanız: freqtrade + FreqAI, `dry_run: true` ile başlayıp birkaç hafta izleyin; `live_retrain_hours`, `expiration_hours` ve sabit stoploss'u siz kilitleyin.
2. Strateji yazmadan, kutudan çıkar çıkmaz çalışan bir taban çizgisi için NFI (öğrenmez ama olgun); bunu başka bir öğrenme katmanıyla (ör. Tur 3'teki TEMPEST/Astra fikirleri) karşılaştırma referansı yapın.
3. ITB ilginç ama canlıda otomatik yeniden eğitim eksik; fikir kaynağı olarak kalsın.
4. İşlem günlüğünden gerçekten öğrenen (L4) çözüm hâlâ yalnız Tur 3'te bulunan LLM tabanlı botlar; klasik ML çerçevelerinde bu özellik yok.
