# Görev 6 — Çalışma testi: freqtrade kurulumu ve üç parçanın testleri gerçekten çalıştırıldı

Tarih: 15 Kasım 2026 · Önceki raporlar: `gorev4_parca_katalogu.md`, `gorev5_degerlendirme_yontemi.md`, `gorev8_freqtrade_dogrulama.md` (hepsi `origin/claude/charming-hawking-ab5w5q` dalında; bu dala taşımadım). Bu rapor, onlardaki "yalnızca kod okuduk" sınırını kaldıran **ilk çalıştırma** denemesidir.

**Kurallar ve ortam.** Konteyner izole: içinde borsa/LLM anahtarı yok, ben de oluşturmadım veya istemedim; hesaba giriş ve gerçek emir yok; yalnızca herkese açık piyasa verisi. Python 3.13.18, 4 çekirdek, 15 GB RAM, disk 252 GB (30 GB boş). Kurulumlar ve klonlar oturumun geçici klasöründe; depoya yalnızca bu rapor eklendi. Her komut `python -I run.py` sarmalayıcısıyla (duvar saati, tepe RSS, CPU) ölçüldü; "RAM" = tepe RSS (MB). Süreler tek çalıştırmadır, tekrar edilmedi.

## 0. Kısa sonuç

- **Çalıştı:** freqtrade 2026.10 `pip install` ile 56 sn'de kuruldu; backtest, FreqAI+LightGBM backtest, lookahead-analysis ve recursive-analysis çalıştı; üç parçanın testleri **tamamı geçti** (guarded-trader araştırma 47/47, agent-to-earn 203/203, regime-trading-bot 96/96); `dsr.py` sayıları gorev5'teki "kendi hesabı" rakamlarıyla (yuvarlama farkı içinde) örtüştü.
- **Doğrudan çalışmayan:** Binance API'si (`api.binance.com`, `fapi.binance.com`) bu konteynerden **HTTP 451 (coğrafi kısıt)** döndürdü. `download-data` ancak Binance'in herkese açık piyasa-verisi ucu `data-api.binance.vision` ve ccxt ayarı hileleriyle çalıştı (§2.1). Vadeli işlem (futures) hiçbir şekilde denenemedi; FreqAI örnek stratejisi `can_short=True` geldiği için **spot'a uyarlayarak** çalıştırıldı.
- **Sürpriz:** (1) `lookahead-analysis` FreqAI stratejisinde "bias: Yes" verdi ve 328 sn sürdü (§2.6); (2) örnek strateji 6 ayda −%10 ve Sharpe −3,25 (kazanma oranı %76 iken: tek bir stop_loss çıkışı −%10 yiyor); (3) `recursive-analysis` örnek stratejide `startup_candle_count=30` iken ADX/RSI'da −%3,5…−%3,8 sapma gösterdi.
- **Pratik zorluk:** aşağıda (§7) — kurulum kolay, asıl iş parçaları birbirine bağlamak ve Binance erişimi.

## 1. Özet tablo (komut → süre → RAM → sonuç)

| # | Adım | Süre | Tepe RAM | Sonuç |
|---|---|---|---|---|
| 1 | `pip install freqtrade` (venv) | 56 sn | — | ✅ freqtrade 2026.10, ccxt 4.5.92, TA-Lib 0.8.3 (tekerlek, derleme yok) |
| 2 | `download-data` (varsayılan ccxt ayarı) | 3,5 sn | — | ❌ HTTP 451 |
| 3 | `download-data` (ayarlı; 3 parite × 1h+5m) | 17,5 sn | — | ✅ 4,2 MB feather |
| 4 | `backtesting` SampleStrategy, 1h mum, 6 ay | 6,4 sn | 552 MB | ✅ 67 işlem, −%10,28 |
| 5 | `backtesting` SampleStrategy, 5m mum, 6 ay | 15,5 sn | 745 MB | ✅ 180 işlem, −%11,61 |
| 6 | `pip install "freqtrade[freqai]"` | 11 sn (+venv 1,2 GB) | — | ✅ lightgbm 4.7.0, sklearn 1.9.1, xgboost 3.4.1 |
| 7 | `backtesting` FreqAI + LightGBMRegressor, 40 gün | 65 sn | 1.401 MB | ✅ 115 işlem, −%1,72; 18 eğitim |
| 8 | `lookahead-analysis` SampleStrategy | 10,4 sn | 581 MB | ✅ "no bias detected" |
| 9 | `lookahead-analysis` kasıtlı sızıntılı strateji | 9,7 sn | 568 MB | ✅ bias yakalandı |
| 10 | `recursive-analysis` SampleStrategy | 5,9 sn | 533 MB | ✅ çalıştı; kısa `startup` sapması gösterdi |
| 11 | `lookahead-analysis` FreqAI stratejisi, 21 gün | 328 sn | 1.612 MB | ⚠️ çalıştı, "has_bias: Yes" (yorum §2.6) |
| 12 | `trade` dry-run (anahtarsız), 2 koşu | 2 × 12 dk (SIGINT) | 465–521 MB | ⚠️ başladı, döngü çalıştı, temiz kapandı; **0 sinyal/işlem**, WS bağlanamadı (§2.7) |
| 13 | guarded-trader `pytest` | 6,0 sn | 156 MB | ✅ 47 geçti, 0 kaldı |
| 14 | agent-to-earn `pytest` | 4,4 sn | 373 MB | ✅ 203 geçti, 0 kaldı |
| 15 | regime-trading-bot `pytest` | 1,7 sn | 165 MB | ✅ 96 geçti, 0 kaldı |
| 16 | `dsr.py` örnek hesap | <1 sn | — | ✅ gorev5 ile örtüşüyor (§4) |

## 2. freqtrade adım adım

### 2.1 Kurulum ve veri indirme

- **Kurulum:** `python3 -m venv ft-venv && ft-venv/bin/pip install freqtrade` → 56 sn, çıktı `freqtrade 2026.10`, `CCXT 4.5.92`. TA-Lib tekerleği hazır geldi; C kütüphanesi derlemek gerekmedi. `freqtrade new-config` **etkileşimli** (stdin yoksa `EOFError`); yapılandırmayı elle yazdım (`dry_run: true`, `key/secret: ""`, spot, `StaticPairList`: BTC/ETH/SOL-USDT).
- **Hata 1 — HTTP 451:** `freqtrade download-data` → `binance GET https://api.binance.com/api/v3/exchangeInfo` → `ExchangeNotAvailable`; `curl` ile `api.binance.com` ve `fapi.binance.com` 451 (`Service unavailable from a restricted location according to 'b. Eligibility'`). `data.binance.vision` (toplu arşiv) 200 döndü. Bu bir **konteynerin çıkış IP'si** kısıtıdır; sizin makinenizde farklı olabilir (bkz. gorev2, Türkiye erişimi).
- **Çözüm (anahtarsız, yalnızca herkese açık veri):** Binance'in herkese açık piyasa-verisi ucu `data-api.binance.vision` (200) kullanıldı; `cfg.json`'a şunlar eklendi:
  - `exchange.ccxt_config` ve `ccxt_async_config`: `{"urls": {"api": {"public": "https://data-api.binance.vision/api/v3"}}}` (bu tek başına yetmedi);
  - `"cafile": "/root/.ccr/ca-bundle.crt"` ve `aiohttp_trust_env: true` (ccxt kendi `certifi` paketini kullanır; oturum proxy'sinin CA'sı orada yok → TLS el sıkışma hatası. TLS doğrulaması **kapatılmadı**, CA paketi gösterildi);
  - `options.fetchMarkets.types: ["spot"]` (ccxt varsayılan olarak vadeli piyasaları da yükler → `fapi` 451).
- **Sonuç:** `--timerange 20260515-` (≈6 ay), 1h ve 5m: her parite için 4.428 adet 1h ve 53.137 adet 5m mum; toplam **4,2 MB** feather; 17,5 sn. Ek olarak FreqAI için 15m (11,9 sn).
- **Not:** Bu çözüm Binance **spot** verisi içindir. Vadeli işlem verisi bu konteynerden indirilemedi (denenmedi: fapi 451). `can_short=True` stratejiler için bu ortam yetersiz.

### 2.2 Örnek strateji backtesti (SampleStrategy, spot, 3 parite, cüzdan 1000 USDT)

| Çalıştırma | Mum | İşlem | Ort. kâr | Toplam | Kazanma | Max DD | Sharpe (günlük) | Süre / RAM |
|---|---|---|---|---|---|---|---|---|
| `-i 1h` (şablonun 5m varsayılanını ezdim) | 1h | 67 | −%1,54 | −102,8 USDT (−%10,28) | %76,1 | %10,54 | −3,25 | 6,4 sn / 552 MB |
| şablon varsayılanı | 5m | 180 | −%0,64 | −116,1 USDT (−%11,61) | %83,9 | %11,61 | — | 15,5 sn / 745 MB |

1h koşusunda çıkış dökümü: 51 `roi` (+%1,03 ort., +52,6 USDT), **15 `stop_loss` (−%10,18 ort., −152,6 USDT)**, 1 `force_exit`. Yani yüksek kazanma oranı, az sayıdaki büyük kaybı örtmüyor (profit factor 0,34, SQN −2,67). Piyasa aynı dönemde −%17,47 düştü. Bu bir "strateji edge'i yok" göstergesidir; **örnek strateji bilerek zayıf bir şablondur**, sonuç bir bulgu değil, çalışma doğrulamasıdır. Sonuçlar `ud/backtest_results/*.zip` (geçici klasör).

### 2.3 FreqAI + LightGBM

- `freqtrade[freqai]` ekstrası 11 sn'de geldi; **venv toplam 1,2 GB** (lightgbm, sklearn, xgboost, tensorboard…). `freqai-rl` (torch) kurulmadı.
- `FreqaiExampleStrategy` pip paketinin içinde `freqtrade/templates/` altında; **config örneği pakette yok** (`config_examples/` sadece git deposunda) — docs'taki parametrelerle elle yazdım: `train_period_days 15`, `backtest_period_days 7`, 5m/15m/1h özellikler, `include_corr_pairlist` BTC+ETH, `label_period_candles 24`, `use_SVM_to_remove_outliers`, `n_estimators 200` (varsayılan örnek 800; **hızlı olsun diye 200'e düşürdüm** — sonuç bu yüzden docs'taki örnekle birebir değildir), `data_split_parameters.random_state 1`.
- **Uyarlama:** örnek strateji `can_short = True` ve vadeli işlem bekler; spot'ta çalışsın diye dosyayı kopyalayıp **`can_short = False`** yaptım (sınıf adı `FreqaiExampleSpot`). `enter_short` sinyalleri yoksayılır.
- **Komut:** `freqtrade backtesting --config cfg_freqai.json --strategy FreqaiExampleSpot --freqaimodel LightGBMRegressor --timerange 20261001-20261110 --cache none`.
- **Sonuç:** 65 sn duvar saati, **CPU 219 sn** (çok çekirdekli eğitim), **tepe RSS 1.401 MB**, 18 "Done training" (3 parite × 6 pencere), `ud/models` 1,3 MB. 115 işlem, −%1,72 (−17,2 USDT), kazanma %47,0, Sharpe (günlük cüzdan) −3,39, Max DD %2,33. **Anlamlı bir performans iddiası yok** (40 gün, tek rejim, n_estimators 200); amaç çalıştığını görmekti.

### 2.4 lookahead-analysis (temiz örnek)

`lookahead-analysis --strategy SampleStrategy --timerange 20260901-20261110 -i 1h`: 10,4 sn, 581 MB. Çıktı: `SampleStrategy: no bias detected`, `total_signals 19`, `biased_entry_signals 0`, `biased_exit_signals 0`. Log'da 3 "force-exit… skipping to avoid a false-positive" satırı var (pencere sonunda zorla kapanan işlemler sayılmıyor).

### 2.5 lookahead-analysis, kasıtlı sızıntı (komutun gerçekten yakaladığını görmek için)

Kendi yazdığım `BiasedTest` (`dataframe["close"].shift(-1)` ile `future_close`, `future_close > close` girişi): 9,7 sn. Çıktı: `bias detected!`, `has_bias: Yes`, `biased_indicators: future_close, enter_long`; log: `found look ahead bias in column future_close. 2470.02 != nan`. Yani araç **çalışıyor ve basit `shift(-1)` sızıntısını yakalıyor**; ilginç ayrıntı: `biased_entry_signals` sütunu 0 kaldı, tespit `biased_indicators` sütunundan geldi — rapor okuyanın bu iki sütuna birlikte bakması gerekir.

### 2.6 recursive-analysis ve FreqAI üzerinde lookahead

- `recursive-analysis --timerange 20260901-20261110 -i 1h`: 5,9 sn, 533 MB; "No lookahead bias on indicators found". Ama tablo, strateji `startup_candle_count=30` iken (kolon "30 (from strategy)") ADX −%3,803, RSI −%3,545 sapma gösteriyor; 199 mumda −%0,000. Yani **başlangıç mumu sayısı yetersizse göstergeler canlıda/backtest'te farklı hesaplanır** — şablondaki varsayılan bu açıdan gevşek. (macd/htsine "nan%" ilk kolonda: yeterli veri yok.)
- `lookahead-analysis` FreqAI stratejisinde: **328 sn**, **1.612 MB**, CPU 1.132 sn. Sonuç `has_bias: Yes`; işaretlenenler: `&-s_close, &-s_close_mean, &-s_close_std, do_predict, DI_values, enter_tag, enter_long, exit_short, exit_long`. Aracın kendi notu: "`set_freqai_targets()` içinde kullanılan göstergeler yok sayılabilir" — `&-s_close*` etiketleri meşru (geleceği kullanmak etiketin tanımı). Ama `do_predict`, `DI_values`, `enter_long` da işaretlendi; `biased_entry_signals` yine 0. **Yorumum (doğrulanmadı):** her zaman penceresinde modeller yeniden eğitildiği için çıktılar bitwise aynı olmuyor; bu bir sızıntı değil, determinizm farkı olabilir. Ayırt etmek için tohumlu, tek modelli bir koşu gerekir (gorev8 §FreqAI tohum notlarına bakın). Dolayısıyla **FreqAI stratejilerinde bu aracın pozitif/negatif sonucu tek başına kanıt sayılmamalı**.

### 2.7 Dry-run (anahtarsız, 12 dakika)

**Komut:** `freqtrade trade --config cfg.json --strategy SampleStrategy --db-url sqlite:///…/dry.sqlite` (SampleStrategy, spot, `dry_run: true`, anahtarlar boş, 12 dk `timeout -s INT`).
İki koşu yapıldı (ilk koşudan sonra "tekrar deneyin" isteği geldi; ikincisi `-v` ile):

| Koşu | Komut farkı | Süre | Tepe RAM / CPU | Sonuç |
|---|---|---|---|---|
| 1 | INFO log | 721,5 sn (SIGINT ile durduruldu, rc=124 = `timeout` kodu) | 521 MB / 7,4 sn | Açılış tamam; log sessiz (139 satır); 12 "Bot heartbeat"; DB: 0 işlem, 0 emir |
| 2 | `-v` (DEBUG) | 721,2 sn (SIGINT) | 465 MB / 7,9 sn | 3.023 log satırı; 12 heartbeat; **0 işlem, 0 emir**; DB `dry2.sqlite` |

**Çalıştığının kanıtı (koşu 2):** `Runmode set to dry_run`, `Instance is running with dry_run enabled`, 3 paritelik beyaz liste, her ~5 sn'de bir `Found no enter signals for whitelisted currencies. Trying again...` ve `Skipping TA Analysis for already analyzed candle`; durdururken `SIGINT received, aborting` ve RPC/WS temizliği. Yani bot anahtarsız başlıyor, herkese açık veriyle mumları çekip stratejiyi çalıştırıyor, temiz kapanıyor.

**Çalışmayan kısım:** 12 dakikada **hiç giriş sinyali çıkmadı**, dolayısıyla emir yaşam döngüsü (sanal dolum, çıkış) **bu koşuda görülmedi**; "dry-run emir verip kapatıyor" iddiası doğrulanmadı. Sebep olarak SampleStrategy'nin giriş koşulunun nadir olması muhtemel (backtest'te 6 ayda 67–180 işlem ≈ günde 0,4–1), ama gerçek neden ölçülmedi. İkinci hata: üç parite için `continuously_async_watch_ohlcv … NetworkError: Cannot connect to host stream.binance.com:9443` (ccxt-pro WebSocket); WS görevleri durup freqtrade REST yoklamasına düştü ve döngü kesilmedi. Kaynak: 465–521 MB RAM, CPU ihmal edilebilir (≈8 sn / 12 dk). Veri yolu `data-api.binance.vision` üzerinden herkese açık uçlardı; `trade` komutu anahtar sormadı.

## 3. Üç parçanın testleri

**Güvenlik:** önce kurulum/test yapılandırmasını okudum. Üç repoda da testler ağ/alt süreç çağrılarını `monkeypatch` ile taklit ediyor (`urlopen`, `subprocess.run`); `conftest.py` gerçek `.env`'e güvenmiyor, ortam değişkenlerini temizliyor veya sahte değer koyuyor. Repo kodu kurulmadı (`pip install -e` yok); yalnızca bağımlılıklar ayrı venv'lere kuruldu; `pytest -p no:cacheprovider` ile çalıştırıldı, repo klasörüne yazılmadı.

| Repo (HEAD) | Venv | Komut | Sonuç | Süre | Tepe RAM |
|---|---|---|---|---|---|
| guarded-trader (2026-11-14 `2b4e839`), `services/research/tests` | numpy 2.5.4, pandas 3.1.1, scipy 1.18.1, pytest 9.2.0 (322 MB) | `pytest services/research/tests` | **47 geçti, 0 başarısız, 0 atlanan**, 14 uyarı | 6,0 sn | 156 MB |
| agent-to-earn (2026-11-13 `ca2f47b`) | freqtrade 2026.10 + pytest 9.2 + pytest-asyncio 1.5 + pyyaml (757 MB) | `pytest tests` | **203 geçti, 0 kalan** | 4,4 sn | 373 MB |
| regime-trading-bot (2026-10-21 `508d7d9`) | aynı venv | `pytest tests` | **96 geçti, 0 kalan** | 1,7 sn | 165 MB |

"Kaç test kaldı" → **hiçbiri**: başarısız, atlanan veya hata veren yok. Çalıştırılmayanlar: guarded-trader `services/conductor/tests` (kendi `pyproject.toml`'u var; istenen kapsam dışıydı); Docker/compose, `make` hedefleri ve Kraken arşivi indirme (10 GB) hiç çalıştırılmadı.

### 3.1 Testler gerçekten bu parçaları kapsıyor mu?

**guarded-trader** (`services/research/tests`, `src/research_harness/`):
- `dsr.py` (90 sat.) → `test_dsr.py` 6 test; `test_min_track_record_matches_review_worked_number` 992 gün, `test_expected_max_sharpe_matches_review_worked_numbers` 1,66/1,86 beklenen-maksimum sayılarına sabitlenmiş; PSR monotonluğu, kalın kuyruk, DSR azalışı, dağılım yokken tanımsızlık test ediliyor. **Kapsam iyi**, ama beklenen değerler incelemeyle aynı kişinin ürettiği sayılar (bağımsız doğrulama değil); `deflated_sharpe` için çarpıklık/basıklık dallarının çoğu test edilmiyor.
- `null.py`, `registry.py`, `walkforward.py` → `test_walkforward_null_registry.py` 12 test: 15 çeyreklik pencere, havuzlanmış OOS Sharpe (oran ortalaması değil), null tohumunun pencereden/datetime çözünürlüğünden bağımsızlığı, null kararı için üç koşul, kayıt defterinin yalnızca-ekleme/yeniden-puanlamayı-reddetme/hipotez zorunluluğu/salt-okunur modu. **Kapsam iyi (davranış sözleşmesi düzeyinde)**; gerçek freqtrade/backtest verisiyle entegrasyon (`ft_runner.py`) testlenmedi (Docker gerektirir).
- Ek: `test_metrics.py` 7, `test_round2_engine.py` 19, `test_round2_prereg.py` 2, `test_round2_run.py` 1.

**agent-to-earn** (203 test; `agent/gate.py`, `user_data/strategies/guarded_strategy.py`):
- `gate.py` (≈420 satır): `static_check` için parametrik AST ret testleri (`import os`, `eval`, `open`, `__class__`, `global`, korunan üyeyi ezme…), bütünlük kilidi (`test_repo_lock_matches_protected_files`), `evaluate`, `beats_incumbent` ("tek aykırı değer kıyası kazanamaz"), terfi bekleme süresi, OOS reddinde sayı sızdırmama, kilit alma/bayatlama… **Kapsam çok geniş.** Ama alt süreçler/HTTP **taklit** (`common.subprocess.run`, `lookahead`, `incumbent_oos`): yani **gerçek backtest/lookahead/pytest kapısı çalışmadı**, yalnızca onları çağıran ve çıktıyı ayrıştıran mantık test edildi.
- gorev4 A2'deki "açık delik" (pandas/numpy öznitelik çağrıları, örn. `pd.read_*`, `np.load`) için `test_gate.py`'de **bir test bulamadım** (`grep read_csv|read_pickle|np\.|pd\.` yalnızca `pd.options = None` atama testini buldu). Delik varsa testler onu yakalamıyor; delik varlığını bu çalıştırmada **doğrulamadım** (yalnızca testleri çalıştırma kuralı).
- `guarded_strategy.py` → `test_guarded_strategy.py` 28 test: kaldıraç tavanı/stop mesafesi, stake bütçesi, `risk_mult`, sıfır rejim = işlem yok, hesap kaldıraç tavanı, özsermaye tabanı, evren dosyası bozuksa giriş reddi, günlük/haftalık/aylık düşüş kesicileri. **Kapsam iyi**; sahte `DataProvider` ile, gerçek freqtrade yaşam döngüsü yok.

**regime-trading-bot** (96 test; `tests/`: adaptive 21, council 21, executor_symbols 11, features 12, indicators 16, regime 15):
- Kapsananlar: `core/adaptive.py` (R1), `core/levers.py` (R2; `from core import levers as config`), `core/regime.py`, `core/features.py`, `core/indicators.py`, `core/settings.py`, `council` imza/HMAC (`hmac`, `hashlib`).
- **Kapsanmayan (grep ile):** `core/strategy_state.py::confirm_entry` ve `core/grok_agent.py` — yani gorev4'teki **R3 (LLM vetosu) parçasının testi yok**; `user_data/strategies/RegimeComposite.py` da hiçbir testte geçmiyor. Parçayı alacaksanız kendi testinizi yazmalısınız.

## 4. `dsr.py` örnek hesabı ve gorev5 ile karşılaştırma

**Düzenek:** `deflated_sharpe` / `psr` / `min_track_record` / `expected_max_sharpe` doğrudan `import` edildi (`research_harness.dsr`); sayılar gerçek fonksiyonlardan. 56 günlük seri: günlük `N(μ, 1%)`, `μ` öyle ki yıllık Sharpe 2 (`√365`). `sigma_trials` yıllık 0,5 (günlüğe `0,5/√365`) — gorev5'in varsayımı. Çalıştırma: `dsr_demo.py` (geçici; repoya eklenmedi).

**(B) Örneklem Sharpe'ı tam yıllık 2 olacak şekilde yeniden ölçeklenmiş 56 günlük seri** (T=56, çarpıklık −0,124, basıklık 3,085):

| Ölçüt | `dsr.py` | gorev5 "kendi hesabı" |
|---|---|---|
| PSR(c=0) | **0,779** | "56 günde ölçülen yıllık SR 2 için t≈0,78, PSR≈0,77" ✔ (normalde 0,781) |
| MinTRL(c=0, %95) | **252,5 gün** | 248 gün (normal), 266 (skew −0,5/kurt 10) ✔ (çarpıklık/basıklık kaymasıyla) |
| SR0 (N=10 / 50 / 200), yıllık | **0,787 / 1,138 / 1,383** | beklenen maks. N=10: ~1,58 × σ(0,5)=0,79 ✔ |
| **DSR, N=10** | **0,680** | — (gorev5'te 56 gün için yok) |
| **DSR, N=50** | **0,630** | — |
| **DSR, N=200** | **0,594** | — |
| MinTRL vs SR0 (N=10/50/200) | 685 / 1.355 / 2.642 gün | — |

**(A) Ham rastgele seri (tohum 42):** yıllık SR gerçekte **3,75** çıktı (PSR 0,923, DSR N=10/50/200 = 0,870/0,839/0,816) — kısa örneklemde Sharpe tahmininin ne kadar savrulduğunun örneği. **(C) 2.000 ham çekim** (gerçek SR 2, T=56): ölçülen yıllık SR ort. 2,02 **std 2,53** (p5 −2,19, p95 +6,28); PSR medyanı 0,781, p5–p95 = 0,197–0,992; PSR>0,95 oranı yalnızca **%17,7**. gorev5'in "yıllık SR standart hatası ≈2,55" ve "[−3, 7] güven aralığı" iddiasıyla örtüşüyor (2,53 ve [−2,2; 6,3]).

**(D) gorev5'in DSR örneğini aynı fonksiyonlarla yeniden hesaplamak** (T=365, yıllık SR 2, çarpıklık −0,5, basıklık 10, σ yıllık 0,5):

| | `dsr.py` | gorev5 |
|---|---|---|
| tekil PSR | 0,9729 | ~0,97 ✔ |
| DSR N=10 | 0,8784 | 0,88 ✔ |
| DSR N=50 | 0,7965 | 0,80 ✔ |
| DSR N=200 | 0,7237 | 0,72 ✔ |

**(E) MinTRL (c=0, %95, günlük):** yıllık SR 1 / 1,5 / 2 / 3 için normal: 989,9 / 441,3 / 249,2 / 112,1 gün (gorev5: 989 / 440 / 248 / 111); çarpıklık −0,5/basıklık 10: 1.020,5 / 463,2 / 266,9 / 125,4 (gorev5: 1019 / 462 / 266 / 124); çarpıklık −1/basıklık 20: 1.053,1 / 487,2 / 286,6 / 140,8 (gorev5: 1052 / 486 / 286 / 140). **(F)** beklenen maksimum (σ=1): N=10/50/100/1000 → 1,575 / 2,276 / 2,531 / 3,255 (gorev5: 1,58 / 2,28 / 2,53 / 3,26).

**Fark ve neden:** `dsr.py`'de standart hata `√(… / (T−1))` ve MinTRL `1 + …` kullanıyor; gorev5'in notları `T` kullanıyordu. Sonuç: MinTRL ≈ 1 gün büyük; 56 günde t-istatistiği 0,783 yerine 0,774 (normal getiride PSR 0,7806); **fark karşılaştırılan tüm ölçütlerde ≤ %1,2** (en büyük: MinTRL 125,4 vs 124). gorev5'in "doğrulanması gerekenler" maddesindeki DSR varyans terimi sorusu (SR mı SR0 mı) şöyle cevaplandı: `dsr.py` DSR'da PSR'ı **gözlenen SR** ile hesaplıyor (`psr(sr, sr_star, …)`), SR0 ile değil; gorev5'in (D) örneği bu biçimle de aynı sayıları verdi, yani gorev5'in "Wikipedia aynası SR0 kullanıyor" endişesi bu örneklerde sonuca yansımadı — bu, iki sürümü eşitlemez, yalnızca bu rakamlarda gözlenen farkın ihmal edilebilir olduğunu söyler.

**Yorum:** 56 günde yıllık Sharpe 2 olan bir botun PSR'ı %78, DSR'ı N=10'da %68, N=200'de %59 — hiçbiri %95 eşiğini geçmez; MinTRL tek deneme için bile ~250 gündür. Bu, gorev5'in "4–8 haftalık dry-run edge'i doğrulayamaz" sonucunu **çalışan kodla doğruluyor**.

## 5. Neyin çalışmadığı / kurulum zorlukları

| Sorun | Ayrıntı | Çözüm / durum |
|---|---|---|
| Binance 451 | `api.binance.com`, `fapi.binance.com` coğrafi kısıt | `data-api.binance.vision` + CA + spot; **futures hiç denenemedi** |
| ccxt ve proxy CA | `certifi` kendi CA'sını kullanır; ortamın `SSL_CERT_FILE`'ı işe yaramadı | `ccxt_config.cafile` + `aiohttp_trust_env` |
| `new-config` etkileşimli | boş stdin → `EOFError` | config'i elle yazdım |
| FreqAI örnek config'i pakette yok | yalnızca git deposunda `config_examples/` | docs'tan elle yazıldı |
| FreqAI örnek stratejisi futures-only | `can_short=True` spot'ta reddedilir | kopya + `can_short=False` |
| `trade -i` | `trade` komutunda `-i/--timeframe` yok (yalnızca strateji/yapılandırmadan); denemede `unrecognized arguments: -i 5m` | bayrağı kaldırdım |
| WebSocket | `stream.binance.com:9443` bu konteynerden bağlanamıyor (`NetworkError: Cannot connect to host stream.binance.com:9443`); ws görevleri "Task finished - done" ile bitiyor | freqtrade REST'e düşüyor; bot çalışmaya devam etti |
| `/usr/bin/time` yok | RAM ölçümü için | Python `resource` ile tepe RSS ölçen küçük sarmalayıcı |

## 6. Gerçek kaynak ve süre ihtiyacı

| Kalem | Değer |
|---|---|
| freqtrade kurulumu | 56 sn; venv ≈ 0,7–0,8 GB (çekirdek), **1,2 GB** (+FreqAI) |
| 6 ay × 3 parite × (1h+5m+15m) veri | ≈ 4–5 MB (feather); indirme ≈ 12–18 sn |
| Basit backtest (6 ay, 3 parite) | 6–16 sn; **550–750 MB** RAM |
| FreqAI backtest (40 gün, 3 parite, 18 eğitim, n_est 200) | 65 sn duvar, 219 sn CPU, **1,4 GB** RAM |
| lookahead-analysis basit / FreqAI | 10 sn / **328 sn** (1,6 GB, 1.132 sn CPU) |
| recursive-analysis | 6 sn |
| guarded-trader testleri | 6 sn, 156 MB; venv 322 MB |
| agent-to-earn + regime-trading-bot testleri | 4,4 + 1,7 sn; ortak venv 757 MB |
| Toplam disk (üç venv + klonlar + veri) | ≈ 2,3 GB (klonlar 9 MB, veri 4 MB) |

Bunlar **küçük** rakamlardır: 15 GB RAM ve 4 çekirdeğin çok altında kaldı. Ölçekleme yapılmadı: 6 ay × tüm 5m × 50+ parite, hyperopt (binlerce deneme) ve FreqAI'de `n_estimators 800` / daha uzun dönem çok daha pahalı olur; bunlar ölçülmedi.

## 7. "Bu parçalarla bot kurmak pratikte ne kadar zor?"

**Kolay olanlar (ölçülen):** freqtrade kurulumu ve backtest/lookahead/recursive araçları dakikalar içinde çalışıyor; üç repo testleri tek komutla ve saniyeler içinde geçiyor; parçaların kendi iç mantığı (DSR, bütünlük kilidi, risk çerçevesi, rejim sınıflayıcı) test edilmiş durumda.

**Zor olanlar (bu çalıştırmadan çıkan):**
1. **Veri/borsa erişimi** kurulumdan daha büyük risk: 451, CA/proxy, ws, futures. Sizin ağınızda farklı olabilir; yine de bunu "ilk gün testi" yapın.
2. **Parçalar birbirine bağlanmıyor.** guarded-trader araştırma modülü Docker/Kraken arşivi/10 GB ve kendi freqtrade imajını (`freqtradeorg/freqtrade:2026.8`) varsayıyor; agent-to-earn `docker compose` + Claude Code (`CLAUDE_CODE_OAUTH_TOKEN`) + Telegram varsayıyor; regime-trading-bot LLM anahtarı (`XAI_API_KEY`) ister. **Testlerin geçmesi bunların çalıştığını göstermez**: kapı mantığı (A1/G1–G4) saf Python olarak test edildi, ama uçtan uca "aday strateji → gerçek backtest → terfi → `reload_config`" hattı hiç çalıştırılmadı (alt süreçler taklitli).
3. **Test kapsamı boşlukları:** R3 (LLM vetosu) ve `RegimeComposite.py` hiç test edilmemiş; A2'deki öznitelik-çağrısı deliği testlerde yok; `ft_runner.py` (gerçek backtest yürütücüsü) testsiz.
4. **Doğrulama araçlarının sınırı:** lookahead-analysis FreqAI'de "bias" bayrağı veriyor ve yorumlaması gerekiyor; recursive-analysis, `startup_candle_count` düşükse %3–4 sapma gösteriyor — yani "araç geçti" ≠ "strateji temiz".
5. **İstatistik gerçeği:** 56 günlük bir dry-run (yıllık Sharpe 2 bile olsa) PSR ≈ 0,78; deney boyunca N arttıkça DSR ≈ 0,6'ya iniyor. Bot çalışıyor olsa bile edge **kanıtlanamaz** (§4).

**Genel değerlendirme (öznel):** parçaları *tek tek* çalıştırmak kolay; bunlardan, kendini güncelleyen ve istatistiksel olarak savunulabilir bir bot kurmak **orta-zor**: kod miktarı değil, (a) veri/borsa erişim koşulları, (b) üç farklı repoyu tek mimaride birleştirme (Docker imajları, ortam değişkenleri, lisanslar — gorev4 §1), (c) kendi testlerini yazma (R3, A2 deliği, uçtan uca kapı) ve (d) ayları-yılları bulan doğrulama süresi asıl yük. Hesaplama kaynağı bir engel değil (laptop yeter).

## 8. Sınırlar

- Tek çalıştırma, tek makine (4 çekirdek/15 GB); süre ve RAM değerleri tekrarlanmadı. İşlem sonuçları (kâr/zarar) **yalnızca aracın çalıştığını** gösterir; strateji kalitesi hakkında kanıt değildir (özellikle FreqAI: 40 gün, `n_estimators 200`, spot'a uyarlanmış, tek rejim).
- Binance vadeli işlemleri, funding verisi, canlı emir akışı denenmedi (451 ve "gerçek emir yok" kuralı). Dry-run yalnızca herkese açık ucu kullandı (§2.7).
- Üç repoda yalnızca belirtilen test klasörleri çalıştırıldı; Docker, `make`, `services/conductor`, `scripts/`, dashboard, LLM çağrıları ve kurulum betikleri çalıştırılmadı.
- Test sayıları `pytest` çıktısındandır; "kapsıyor mu" yargıları test adlarını/içe aktarmaları okumaya dayanır, kod kapsama (coverage) ölçülmedi.
- `dsr.py` karşılaştırması gorev5'in "kendi hesabı" tablolarıyla yapıldı; ikisi de aynı formüllere dayandığından bağımsız doğrulama değil, **tutarlılık** kontrolüdür.
