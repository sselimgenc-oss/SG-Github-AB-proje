# Motor şartnameleri — indeks (Faz A, 16 Kasım 2026)

Kaynak: `otonom-trading-arastirma/motor-tasarimi.md` (yetkili). Bu klasör tasarım §0'da vaat edilen `trader/docs/motor-spec.md`'nin yerini alır: **bir uygulanabilir birim = bir şartname**. Her şartname `risk-kilidi-spec.md` üslubundadır (Türkçe düzyazı, İngilizce tanımlayıcı, kesin imzalar, değişmezler, fail-closed kuralları, elle doğrulanabilir örnekler) ve **DOSYA SAHİPLİĞİ** listesi içerir; sahiplikler çakışmaz, birimler paralel gerçeklenebilir. Hiçbir belge kod, test ya da commit içermez; kod yok, mentor onayı olmadan kod başlamaz (§3.1 gün 16–17 kapısı).

## 1. Birimler

| # | Belge | Kapsam | Ana dosyalar (`src/trader_engine/…`) |
|---|---|---|---|
| 02 | `02-clock-bars.md` | Donmuş ortak sözleşme: tipler, hatalar, sayısal yardımcılar, `Clock`, bar aritmetiği, `EngineConfig` + JSON | `types, errors, numeric, clock, bars, config`, `config/engine*.json` |
| 01 | `01-feed.md` | `market.sqlite`, REST yoklama feed'i, `StoreSource`/`HistoricalSource` (`MarketView`) | `marketdata/{store,feed,sources}` |
| 03 | `03-paper-broker.md` | `Broker` arayüzü, `PaperBroker` (dolum, mark tetik, funding, likidasyon), `FaultPlan` | `brokers/{base,paper}`, `funding` |
| 04 | `04-order-position.md` | `state.sqlite`, idempotent `OrderManager` (belirsizlik yolu), `PositionManager` (stop/trail/hedef/zaman/rejim, MFE/MAE) | `state, order_manager, position_manager` |
| 05 | `05-engine-runner.md` | `StrategyRunner`, kapı zinciri, `Engine` döngüsü, yeniden oynatma, mutabakat (paper), kill, `status.json`, CLI; **takılabilir strateji arayüzü** (`Strategy` protokolü, kayıt defteri, `PriceActionV1` v1b adaptörü, 1l3a uyarlama taslağı; §13) | `strategy_runner, gates, engine, reconcile, killswitch, status, cli, __main__`, `strategies/{__init__,base,registry,price_action_v1}` |
| 06 | `06-backtester.md` | Aynı `Engine` ile backtest, metrikler, lookahead kilidi, freqtrade çapraz doğrulaması, paper ↔ backtest eşitliği, 1m veri çekme | `backtest, precomputed, metrics`, `research/bt_crosscheck.py`, `research/run_bt_engine.py`, `scripts/fetch_binance_vision.py` |
| 07 | `07-copied-1l3a.md` | 1l3a'dan **kopyalanan** dosyalar: kesinti/ek/yeniden adlandırma, başlık, Faz B ön kuralları | `marketdata/rest_public`, `exchange/rules`, `fileio` |
| 08 | `08-no-framework-guard.md` | Dış çerçeve yasağı + mimari koruma testleri, `pyproject.toml` bağımlılık kilidi | yalnız `tests/engine/test_*guard*`, `pyproject.toml`, `.gitignore` |

(Numaralar tasarım §3.1 paket adlarıyla uyumlu tutuldu; 02 en erken yapılır, bu yüzden listede başta.)

## 2. Bağımlılık sırası ve paralellik

```
02 (types, clock, bars, config)  ───────────────┐   (donmuş sözleşme: diğerleri belgedeki tanımlara karşı BAŞLAR)
07 (rest_public, rules, fileio)  ──> 01 (feed, store, sources)
08 (korumalar, pyproject)               03 (paper broker, funding)   ──┐
                                        04 (state, order/position mgr) ─┼──> 05 (strategy_runner, gates, engine, reconcile, kill, status, cli) ──> 06 (backtest e2e, çapraz doğrulama)
                                                                       ┘
```

**Paralel gruplar (her birim: gerçekleme ajanı + bağımsız test ajanı; sonra mentor incelemesi):**

| Grup | Birimler | Koşul |
|---|---|---|
| **G0** (gün 18) | **02**, **07**, **08** | Birbirinden bağımsız. 02 `types.py` birleşir birleşmez diğerleri `import` edebilir; ondan önce belgedeki tanımlara karşı yazar |
| **G1** (gün 18–20) | **01**, **03**, **04** | 02'ye (donmuş tipler) ve 07'ye (01 için `PublicRestClient`/`rules` imzaları belgede donmuş; sahte REST ile test) bağlı; **birbirine bağlı değildir** (04, `Broker`/`SimBroker` protokolünü 03 §3'ten sahte broker ile kullanır). Birleştirme sırası: 02 → 07 → 01/03/04 (herhangi sırada) |
| **G2** (gün 20–23) | **05**; **06**'nın bağımsız parçaları | 05 `01+03+04` birleşince başlar. 06'dan `metrics.py`, `fetch_binance_vision.py` eki, `LedgerReplayVeto`, `GuardedView`, `bt_crosscheck.py` 05'i beklemez (yalnız dondurulmuş arayüzlere bağlıdır) |
| **G3** (gün 23–25) | **06** uçtan uca (`BacktestRunner`, `--paranoid`, `--truncate-check`), çapraz doğrulama koşuları; 05 `cli`/kill/status son rötuşu | 05 birleşmiş olmalı |

Takvim eşlemesi (§3.1): P1 = 01, P2 = 03, P3 = 04 (+02/07/08 G0), P4 = 05, P5 = 06 (backtester), P6 = 06 (çapraz doğrulama + lookahead), P7 = 05'in kill/status kısmı + **şartname dışı** işler (aşağıda).

## 3. Sahiplik matrisi (çakışma yok; ihlal = inceleme reddi)

Her `src/trader_engine` dosyasının **tek** sahibi vardır (08 `test_engine_module_inventory` modül listesini kilitler):

| Dosya | Sahip | Dosya | Sahip |
|---|---|---|---|
| `__init__.py, errors.py, types.py, numeric.py, clock.py, bars.py, config.py` | 02 | `state.py, order_manager.py, position_manager.py` | 04 |
| `marketdata/{__init__,store,feed,sources}.py` | 01 | `strategy_runner.py, gates.py, engine.py, reconcile.py, killswitch.py, status.py, cli.py, __main__.py`, `strategies/**` | 05 |
| `marketdata/rest_public.py` | 07 | `backtest.py, precomputed.py, metrics.py` | 06 |
| `exchange/{__init__,rules}.py, fileio.py` | 07 | `brokers/{__init__,base,paper}.py, funding.py` | 03 |
| `config/engine*.json` | 02 | `pyproject.toml`, `.gitignore` (satır ekleme) | 08 |
| `scripts/fetch_binance_vision.py`, `research/bt_crosscheck.py`, `research/run_bt_engine.py` | 06 | `tests/engine/test_engine_<birim>_*`, `test_no_framework_imports.py` | ilgili birim (adlar her belgede) |

Dokunulmaz (hiçbir birim): `src/trader_core/**`, `user_data/strategies/TraderV1.py`, `research/run_bt.py`, `docker-compose.yml` (§4.3 silme commit'i; kapıdan önce). `feed.py` **01** tarafından sıfırdan yazılır; 1l3a `paper_canli.py`'den yalnız fikir alınır (07 §4.2, mentor kararı).

## 4. Çapraz birim sözleşmeleri (değişiklik = mentor onayı + etkilenen belgelerin revizyonu)

1. `types.py` (02 §4): `Bar, MinuteBar, FundingPoint, SymbolRules, OrderRequest, OrderResult, BrokerOrder, Fill, BrokerEvent, BrokerPosition, BrokerAccount, Intent, Position`; kanonik çift `"BTC/USDT"`; `ExitReason` = `ledger._EXIT_REASONS`.
2. `MarketView` (01 §6): `bars(until zorunlu)`, `contiguous_tail`, `minute_steps`, `funding`, `rules`, `last_closed_minute`, `data_range`, `step_seconds`.
3. `Broker`/`SimBroker` (03 §3) ve iki aşamalı adım (`advance(…,"fills")` → `poll` → `advance(…,"triggers")` → `poll`).
4. `state.sqlite` şeması ve `StateStore` API'si (04 §3), `make_client_id` biçimi (04 §4).
5. `SignalSource`/`SignalFrame`/`SignalRow` (05 §3) ve `ExitContext`/`evaluate_exit` (04 §5). **Strateji arayüzü** (05 §13): `Strategy`/`StrategyInfo`/`StrategyContext`/`ExitPolicy`, `compute` çıktısı = `trader_core.signals.SIGNAL_COLUMNS` (sütun kümesi donmuş), `registry.get_strategy(name)`.
6. `PublicRestClient`, `rows_to_bars`, `extract_rules`/`to_symbol_rules`, `fileio` (07 §4).
7. `status.json` şeması (05 §8.2) — `health_run.py` uyarlamasının girdisi.
8. `trades.csv`/`summary.json` sütun/anahtar kümesi (06 §4) — `research/runs/*.json` ile uyumlu.

## 5. Tasarım ↔ mevcut `trader_core` API çakışmaları ve belirsizlikler (özet; ayrıntı ilgili belgede)

| # | Konu | Çözüm (şartname) | Karar gereken |
|---|---|---|---|
| 1 | **Hedef çıkışı:** tasarım §2.6 R1 hedefini borsada `TAKE_PROFIT_MARKET` ister; `strateji-spec` §5.4/`TraderV1.custom_exit` kapanmış bar high/low'una bakıp bir sonraki adımda piyasa çıkışı verir | Faz A `target_mode="bar_close"` (05 §1); `place_target` yalnız arayüzde | **Karar verildi:** `bar_close` onaylandı; strateji kuralının tek kaynağı `strateji-spec`. Borsada TP Faz A ve canlı v1'de yok. (R1'in v1b'de kapatılması ayrı kullanıcı kararıdır; kod yolu yine yazılır ve test edilir) |
| 2 | **Kapı sırası:** tasarım §2.2 `params_ok → ledger → stale → kill → tek karar → veto → risk`; TraderV1 `gate → stale → tek karar → veto → risk` | TraderV1 sırası korunur, kill/`entries_blocked_reason` ledger'ın arkasına eklenir (05 §1/§4.1) | Mentor (§5 inceleme 4) |
| 3 | **`ledger` `skip_reason` sözlüğü** `stale_data`, `kill` vb. içermez; `not_evaluated` yalnız belirli skip'lerle geçerli | `entry_gate_closed`/`other` + `veto_reason="gate:<kod>"` (05 §4.1) | — (bilgi) |
| 4 | **`Ledger.find_unledgered_trades(freqtrade_open_trade_ids)`** adı | Konumsal çağrı; yeniden adlandırma §4.3 madde 5 | — |
| 5 | **`health.ApiProbe`** freqtrade API alanları | `status.json` eşdeğer alanları taşır (05 §8.2); `health_run` uyarlaması ayrı iş | — |
| 6 | **`bars_held` 15 dk birimi** (ledger) ↔ zaman durdurma tetik tf barı (48) | İkisi ayrı; ledger 15 dk birimi ledger için, zaman durdurma tetik tf barı (04 §9) — mentor onayı | — |
| 7 | **`Ledger(clock=…)` "yalnızca test"** ↔ backtest `SimClock` **zorunlu** (`bar_close_ts ≤ now+5 sn`) | `clock.now` geçirilir (05 §1 madde 9) | — |
| 8 | **`veto.json.pairs_from → config/base.json`** (§4.3'te silinir); `veto.load_pairs` serbest `dosya:yol` | `config/engine.base.json:pairs`; silme adımında yeniden işaret | — |
| 9 | **`pyproject.toml`** yalnız pandas/numpy; `pyarrow`, `requests` yok; **bu ortamda pyarrow kurulu değil** | 08 §3; testler `importorskip`. Mentor: `pyarrow` §1.0'da izinli, `pip install` serbest; çapraz doğrulama ve backtest koşularında kurulu olması **zorunlu** (atlanan test kabul sayılmaz) | — |
| 10 | **`ConfigError` ad çakışması** (`trader_core.config_loader` freqtrade'e özgü `validate`) | `trader_engine.errors.ConfigError` ayrı sınıf; yalnız `deep_merge` yeniden kullanılır (02) | — |
| 11 | **§4.3 madde 7 (`grep -ri freqtrade …` boş) ↔ uyum kipi adı `legacy_compat`** | Kip adı `legacy_compat`; izin listesi yok, grep istisnasız boş (08 §6) | **Karar verildi** |
| 12 | **`paper_canli.py` "(a) kopyala"** `TekrarKaynagi`/`motor.veri`/`paper_takvim` bağımlıdır (kopya listesinde yok); `kurallar.py` varsayılan `min_notional=5` uydurur (kendi docstring'iyle çelişir) | `paper_canli.py` **(b) fikir**, `feed.py` sıfırdan; (a) kopya yalnız `paper_veri.py`, `kurallar.py`, `atomik_yaz_*`; min-notional eksik → `RulesError`, o çifte giriş yok (07 §4.2–4.3, §7) | **Karar verildi** |
| 13 | **Client id `seq` kuralı:** tasarım "yeniden gönderimde deneme sayacı seq'e girer"; şartname giriş/çıkışta aynı kimliği korur, yalnız stop'ta sayaç | Şartname yetkili: `e`/`x` aynı kimlik, sayaç yalnız stop; yeniden gönderim yalnız iki "emir yok" sorgusundan sonra; canlıda testnet doğrulamasına kadar `max_attempts=1` (04 §1) | **Karar verildi** |
| 14 | **freqtrade backtest sentetik piyasa kuralları** (`freqtrade_offline.py::synthetic_markets`) ile üretildi | Uyum çalışmasında aynı türetme `sources.py`'de yeniden yazılır; sonuçlar "sentetik kurallar" etiketli (01 §6.2) | — |
| 15 | **Geçmiş uzunluğu bağımlılığı:** özyinelemeli EMA/ATR → pencere (paper) ≠ tüm geçmiş (backtest); 4h EMA100 için 300 bar tohum etkisi ≈ %0,2 | `WINDOW_4H=1500` (≈1e-13); 06 paranoid kontrolü ayrık sütunları eşit, sürekli sütunları 1e-9 ister (05 §3.1) | — |
| 16 | **Ortamda Binance REST HTTP 451**; 1m Vision verisi henüz yok | Uyum kipi 15m adım; native 1m için veri çekme 06 §5; kurallar `synthetic` | — |
| 17 | **`day_start_equity` tanımı:** TraderV1 `cüzdan − bugün kapanan kâr/zarar`; motor gün başı cüzdan anlık görüntüsü | Eşdeğer (tek fark açık pozisyon funding'inin zamanı); çapraz doğrulama sınıfı `day_start_def` (05 §4.2) | — |

## 6. Mentor inceleme kapılarıyla eşleme (tasarım §5)

| Kapı | Şartname bölümleri |
|---|---|
| 1. `motor-spec`/dolum modeli | bu klasör; dolum modeli = `03` §4 (ayrı `motor-dolum-modeli.md` gerekmez; istenirse `03` §4–5 oradan türetilir) |
| 2. Broker arayüzü + dolum kuralları | `03` §3–4, §9 |
| 3. `order_manager` belirsizlik yolu, client id | `04` §4 |
| 4. `gates.py` zinciri, TraderV1 eşleme | `05` §4.1, §11 (eşleme testleri) |
| 5. Yeniden başlatma/oynatma, mutabakat | `05` §5.5, §7 |
| 6. Çapraz doğrulama + model farkı | `06` §7 |
| 7. 48 saat deneme | şartname dışı (P7 işletim) |
| 8. Freqtrade silme + çerçeve yasağı testi | `08` §4, §6; `06` §7 kabul |

## 7. Şartname dışı Faz A işleri (sahibi bu 8 birimden hiçbiri değil)

`deploy/trader-feed.service` (**17 Kas 2026: yazildi, ertelenmis degil**; `feed.main`/`rules_snapshot_main` giris noktalari, acilista kural cekimi yeniden deneme/451, motor `After=/Wants=` bagi ve paper acilis kapisi: `engine.start()` kural + taze 1m verisi 10/10 degilse `startup_wait_s` sonra cikis kodu 7), `trader-engine@.service`, `MemoryMax=400M`, swap, systemd kurulumu (§2.9, P7); `scripts/health_run.py` ve `health` toplayıcısının `status.json` okuyucusuna uyarlanması; `veto.json.pairs_from` yeniden işaretlenmesi; `ledger` `find_unledgered_trades` parametre adı ve `strateji-spec` §4–6 işaretlemesi (§4.3 madde 5); freqtrade silme commit'i (§4.3). Bunlar ayrı iş paketleridir ve ilgili şartname revizyonu + bağımsız test güncellemesiyle yapılır.

## 8. Testlerin yazımı

Her birimin testleri **şartnameden** bağımsız test ajanı tarafından yazılır (`test_engine_<birim>_spec.py`); gerçekleme ajanı yalnız `test_engine_<birim>_impl_smoke.py` yazar (risk 12). Tüm test dosyası adları `tests/` altında **tekildir** ve `test_engine_` önekiyle başlar (`test_no_framework_imports.py` istisna). `pyarrow` gerektiren testler `pytest.importorskip("pyarrow")` kullanır.
