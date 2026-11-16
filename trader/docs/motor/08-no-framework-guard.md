# 08 — Dış çerçeve yasağı ve mimari koruma testleri (spesifikasyon v1, 16 Kasım 2026)

Kaynak kararlar: `motor-tasarimi.md` §1.0 (bağlayıcı kullanıcı ilkesi: izinli bağımlılıklar yalnız `pandas`, `numpy`, `pyarrow`, `requests`, Faz B `websockets`, standart kütüphane; yasak: işlem çerçeveleri ve borsa SDK'ları; `tests/engine/test_no_framework_imports.py` kaynak ağacını tarar ve `pyproject.toml` bağımlılık listesini denetler), §2.2 (`clock.py`: kodda `datetime.now()` yasak, test ile kilitlenir), §5 risk 6 (`trader_engine` içinde risk sabiti tanımlamak testle yasak), §4.3 madde 7 (silme kabulü), §3.1 (Faz A kapsam kilidi). Bu birim **kod üretmez**: korumalar yalnız testtir ve `pyproject.toml`/`.gitignore` bağımlılık-ilke düzenlemesidir. Bu belge kod, test ve commit içermez.

## 1. Kararlar (özet)

| Konu | Karar |
|---|---|
| Yöntem | Kaynak ağacı `ast` ile **statik** taranır; hiçbir test taranan modülü içe aktarmaz (kopya/ağır modül yükleme yok). Ağırlık testi tek istisna: alt süreçte içe aktarma, `sys.modules` denetimi |
| Kapsam | `src/trader_engine/**` ve `src/trader_core/**` (yasak çerçeveler iki pakette de yasak) |
| Hata ölçütü | Tek ihlal = test kırmızı; ihlal satırı `dosya:satır` ile raporlanır |
| İzin listeleri | Test dosyalarının başında **adlandırılmış sabit** olarak durur; değişiklik mentor onayı gerektirir (inceleme maddesi 8) |
| Faz kilidi | `PHASE = "A"` sabiti; Faz B dosyaları (`brokers/binance_futures.py`, `exchange/binance_rest.py`) Faz A'da var olamaz |
| Serbest kapsam | Testler, `scripts/`, `research/` bu korumaların **dışındadır** (freqtrade artıkları §4.3'e kadar orada durur); ancak §4.3 kapısı açıldığında `FREQTRADE_REMOVED = True` ile genişler (§6) |

## 2. DOSYA SAHİPLİĞİ

Bu birim yalnızca şunlara dokunur:

- `tests/engine/test_no_framework_imports.py` (tasarım §1.0'ın adlandırdığı dosya)
- `tests/engine/test_engine_clock_discipline.py`, `test_engine_no_risk_constants.py`, `test_engine_import_weight.py`, `test_engine_copy_headers.py`, `test_engine_module_inventory.py`, `test_engine_dependency_direction.py`, `test_engine_test_names_unique.py`
- `pyproject.toml` (yalnız: `dependencies`, `[project.optional-dependencies]`, `description`, `name` **değiştirilmez**)
- `.gitignore` (yalnız eklenen satırlar: `var/`, `shared/KILL`, `research/crosscheck/`)

Bu testlerin **yazarı bağımsız test ajanıdır** (şartnameden); `pyproject.toml`/`.gitignore` düzenlemesini ayrı bir küçük gerçekleme ajanı yapar. Dokunulmaz: `src/**` (hiçbir kaynak dosya), diğer birimlerin dosyaları, `docker-compose.yml`, `tests/test_compose.py` (§4.3).

## 3. `pyproject.toml` düzenlemesi (08 sahibi)

Mevcut: `dependencies = ["pandas>=2.2", "numpy>=1.26"]`, `description = "Freqtrade tabanli vadeli islem botu iskeleti - cekirdek paket"`, `dev = ["pytest", "pyyaml"]`. Hedef:

```toml
description = "Kendi islem motorumuz (trader_engine) ve saf cekirdek (trader_core)"
dependencies = ["pandas>=2.2", "numpy>=1.26", "pyarrow>=15", "requests>=2.31"]

[project.optional-dependencies]
dev  = ["pytest", "pyyaml"]          # pyyaml: tests/test_compose.py (§4.3'te silinir)
live = ["websockets>=12"]            # Faz B; Faz A'da kurulmaz
```
- `pyarrow`: feather okuma (01 `HistoricalSource`); `requests`: `PublicRestClient` (07; tembel import).
- `[tool.setuptools.packages.find] where = ["src"]` zaten `trader_engine`'i bulur (paketin `__init__.py`'si 02'dedir); `[tool.pytest.ini_options]` **değişmez** (`pythonpath = ["src"]`, `testpaths = ["tests"]`).
- Bu çalışma ortamında `pyarrow` kurulu değildir; `HistoricalSource` ve ilgili testler `pytest.importorskip("pyarrow")` kullanır (01).

## 4. Testler

### 4.1 `test_no_framework_imports.py`

Sabitler:
```
FORBIDDEN_TOP = {"freqtrade","freqtrade_client","ccxt","binance","binance_connector","python_binance","pybit","bybit",
                 "okx","kucoin","krakenex","alpaca","alpaca_trade_api","ib_insync","backtrader","vectorbt","vectorbtpro",
                 "zipline","backtesting","lean","motor","1l3a"}
ALLOWED_DEPS = {"pandas","numpy","pyarrow","requests"}
ALLOWED_OPTIONAL = {"dev": {"pytest","pyyaml"}, "live": {"websockets"}}
SCAN_ROOTS = ("src/trader_engine", "src/trader_core")
```
Denetimler:
1. **İçe aktarma taraması:** her `.py` dosyası `ast.parse`; `Import`, `ImportFrom` (göreli içe aktarma hariç) üst düzey adı (`a.b.c → a`) `FORBIDDEN_TOP` içindeyse ihlal. `importlib.import_module("x")`, `__import__("x")` ve `importlib.util.find_spec("x")` çağrılarında **sabit metin** argümanı yasak adlarla eşleşirse ihlal; sabit olmayan argüman (`import_module(name)`) bu ağaçta **tamamen yasak** (dinamik içe aktarma yok).
2. **Süreç çağrısı taraması:** `subprocess.*`, `os.system`, `os.popen`, `shutil.which` çağrılarında ilk argüman (liste ya da metin) sabit öğe olarak `freqtrade` ya da `docker` içeriyorsa ihlal (`subprocess` motorda yalnız `git rev-parse` için `backtest.py`'de **izinli**: izin listesi `{("backtest.py", "git")}`).
3. **Yol manipülasyonu:** `sys.path.insert/append`, `os.environ["PYTHONPATH"]` atama, `site.addsitedir` çağrıları `src/trader_engine`'de **yasak** (`cli.py`/`__main__.py` dahil; paket normal kurulumla içe aktarılır).
4. **`pyproject.toml`:** `tomllib` ile okunur; `project.dependencies` adları (`name[extra]>=ver; marker` biçiminden normalleştirilmiş: küçük harf, `_`→`-`) **küme olarak `ALLOWED_DEPS`'e eşit**; `optional-dependencies` anahtarları ve içerikleri `ALLOWED_OPTIONAL` ile eşit; hiçbir bağımlılık URL/yol (`@`, `git+`, `file:`, `http`) içermez; yasak adlar (`FORBIDDEN_TOP` + `python-binance`, `binance-connector`, `freqtrade`) hiçbir yerde (de `build-system.requires` dahil) bulunmaz.
5. **Alt modül/mount yokluğu:** depoda `.gitmodules` yok ya da `1l3a` içermez; `trader/` altında 1l3a'ya işaret eden sembolik bağ yok; `docker-compose.yml` (varsa, §4.3 öncesi) `1l3a` içermez.
6. **Kendi sınır testi:** sentetik bir geçici ağaçta kasıtlı ihlaller (her denetim için bir tane) kırmızı üretir; temiz ağaç yeşil (testin kendisinin çalıştığının kanıtı; tarayıcı işlevi `scan_tree(root)` testte yaşar).

### 4.2 `test_engine_clock_discipline.py`

`src/trader_engine/**` AST taraması; takma ad çözümlemesi yapılır (`import time as t`, `from datetime import datetime as dt`, `from time import sleep`).
- Yasak çağrılar: `datetime.now`, `datetime.utcnow`, `datetime.today`, `date.today`, `time.time`, `time.time_ns`, `time.sleep`, `time.monotonic`, `time.perf_counter`, `pd.Timestamp.now/utcnow/today`, `pandas.Timestamp.now`, `os.times`, `asyncio.sleep`.
- **İzin listesi** (`ALLOWED_WALL_CLOCK`): `clock.py` → `{datetime.now, time.sleep}` (yalnız `SystemClock` sınıfı içinde: AST'de çağrının üst sınıfı `SystemClock` olmalı); `backtest.py` → `{time.perf_counter}` (yalnız çalışma süresi ölçümü, kural yolunda kullanılmaz); başka hiçbir dosya.
- `from time import ...` ve `from datetime import datetime` + `datetime.now` kombinasyonları takma adla yakalanır.
- **SQL içi saat:** metin sabitlerinde `CURRENT_TIMESTAMP`, `datetime('now'`, `strftime(` + `'now'`, `julianday('now'` (yalnız `CREATE|INSERT|UPDATE|SELECT` içeren sabitlerde) yasak: zaman Python tarafından `Clock` ile verilir.
- **Rastgelelik:** `random.*`, `numpy.random.*`, `uuid.uuid4`, `secrets.*` çağrıları `src/trader_engine/**`'da yasak; **istisna** `backtest.py` içinde `random.Random(seed)` (yalnız `--paranoid` örneklemi; sabit tohum zorunlu: çağrı argümansızsa ihlal).
- `trader_core` bu testin dışındadır (ledger/risk saati enjekte alır; ayrı kapsam).

### 4.3 `test_engine_no_risk_constants.py` (risk 6: tek risk seti)

`src/trader_engine/**` AST taraması:
- **Ad deseni:** `Assign/AnnAssign/AugAssign` hedefi, anahtar sözcük argümanı adı, dataclass alan adı ya da sözlük sabit anahtarı bu desenlerden birine uyuyorsa **ve** değer sayı sabitiyse ihlal: `max_trade_risk|target_trade_risk|daily_max_loss|max_open_risk|max_same_dir_risk|max_leverage|min_leverage|liq_safety|maint_margin|max_notional|fee_rate|slippage_rate|risk_per_trade|leverage` (alt dize eşleşmesi, küçük harf). İzin listesi `RISK_NAME_ALLOW = {("types.py","leverage"), ("types.py","qty")}` yalnız **tür açıklaması** olan alanlar için (sayısal varsayılan yok: `leverage: int | None` ✓; `= 3` ihlal).
- **Yapıcı yasağı:** `RiskConfig(` çağrısı, `dataclasses.replace(<LOCKED_CFG ya da RiskConfig örneği>, …)`, `HARD_LIMITS` içe aktarma ya da kullanımı **yasak**.
- **Tek kaynak kullanımı:** `trader_core.risk` çağrıları (`check_entry`, `size_position`, `loss_at_stop`, `liquidation_price`) cfg argümanını **ya hiç vermez ya da** `LOCKED_CFG` (Ad/Öznitelik zinciri sonu `LOCKED_CFG`) verir; başka ifade ihlal. `liquidation_price`'ın `mmr` argümanı `LOCKED_CFG.maint_margin_rate` ya da `PaperConfig.mmr` (motor bunu `LOCKED_CFG`'den doldurur; `PaperConfig.mmr` için **sayısal varsayılan yok**).
- **Maliyet modeli serbest:** `CostModel` alanları (`taker_fee`, `slip_*_bps`) risk sabiti değildir; bu desenlere **uymayan adlarla** tanımlandığı için taranmaz. (Ad çakışması çıkarsa 02 adı değiştirilir, desen gevşetilmez.)
- JSON yapılandırmaları: `config/engine*.json` anahtar kümesinde `RISK_NAME` desenlerine uyan anahtar yok (02 `ConfigError` ile zaten ayrıca korur; burada ikinci kilit).

### 4.4 `test_engine_import_weight.py` (feed hafifliği, risk 9/§2.9)

Alt süreç: `[sys.executable, "-I", "-c", KOD]` (`-I` `PYTHONPATH`'i yok saydığından `KOD` kendi içinde `sys.path.insert(0, "<repo>/trader/src")` yapar; `-I` ayrıca kullanıcı site-paketlerini dışlar). `KOD`: modülü içe aktarır, sonra `sorted(m for m in sys.modules if m.split(".")[0] in {"pandas","numpy","requests","pyarrow"})` çıktısını JSON verir.
- **Hafif küme (hiçbirini yüklemez):** `trader_engine.types`, `errors`, `numeric`, `clock`, `bars`, `config`, `fileio`, `exchange.rules`, `marketdata.rest_public`, `marketdata.store`, `marketdata.feed`, `trader_engine.cli` (alt komutlar tembel).
- **Serbest küme:** `marketdata.sources`, `strategy_runner`, `engine`, `gates`, `backtest`, `metrics`, `precomputed` (pandas/numpy yükleyebilir).
- `requests` yalnız `PublicRestClient` kurucusunda yüklenir (içe aktarma anında **yüklenmez**).
- Süre/bellek: tek alt süreç başına zaman aşımı 30 sn; bellek ölçümü bu testin işi değildir (sunucu denemesi, §3.1 gün 28–29).

### 4.5 `test_engine_copy_headers.py`

`COPIED = {"exchange/rules.py": "motor/canli/borsa/kurallar.py", "marketdata/rest_public.py": "motor/canli/paper_veri.py", "fileio.py": "motor/canli/durum.py"}` (`marketdata/feed.py` listede **yoktur**: mentor kararıyla `paper_canli.py` "(b) fikir" sınıfındadır; kopya başlığı taşımaz, başlık dışı `1l3a` metni yasağı ona da uygulanır). Her dosyanın ilk 3 satırı: `# Kopyalandı: 1l3a-proje/<yol>`, `# Kopya tarihi: <YYYY-MM-DD>   Kaynak commit: <…>`, `# Çalışma zamanında kaynak depo …` desenleriyle eşleşir (düzenli ifade; tarih geçerli ve bugünden ileri değil — `Clock` yerine testte sabit "şimdi" yoktur: yalnız `YYYY-MM-DD` biçimi ve `≥ 2026-11-16` denetlenir). Ek:
- `src/trader_engine/**` içinde **başlık dışında** `1l3a` geçen **sabit metin** (docstring dahil) yoktur; başlık yalnızca yorum satırlarıdır.
- Hiçbir dosyada `motor.canli`, `motor.backtest`, `motor.veri`, `motor.portfoy` metni (içe aktarma ya da sabit) yok.
- `07 §4` "Kesilen" listesindeki adlar kopyalarda geçmez: `ESLEME`, `tradfi`, `boyutlandir`, `Boyut`, `canli_limitler`, `paper_takvim`, `TekrarKaynagi`, `BinanceHata`, `FapiIstemci`.
- Kaynak depo yolu `/home/user/sselimgenc-oss` ya da `sselimgenc` metni `src/`, `tests/engine/`, `config/` altında geçmez.

### 4.6 `test_engine_module_inventory.py` (Faz A kapsam kilidi)

`ALLOWED_MODULES_A` (göreli yol kümesi): `__init__.py, __main__.py, errors.py, types.py, numeric.py, clock.py, bars.py, config.py, fileio.py, state.py, order_manager.py, position_manager.py, funding.py, strategy_runner.py, gates.py, engine.py, reconcile.py, killswitch.py, status.py, backtest.py, precomputed.py, metrics.py, cli.py, marketdata/{__init__,rest_public,store,feed,sources}.py, brokers/{__init__,base,paper}.py, exchange/{__init__,rules}.py`. `src/trader_engine` altındaki her `.py` bu kümede olmalı (yeni dosya = test kırmızı = mentor onayı). `PHASE == "A"` iken `brokers/binance_futures.py`, `exchange/binance_rest.py`, `marketdata/ws.py`, `reconcile_live.py` **yok** olmalıdır (kapsam kilidi: §3.1 "yok" listesi — imzalı istemci, `BinanceFuturesBroker`, algo emirleri, emir hız sınırı, WS, listenKey, 1d, exchangeInfo'nun emir yolunda kullanımı). Ayrıca: kaynakta `listenKey`, `userDataStream`, `algoOrder`, `websockets` metni **yok** (Faz A'da).

### 4.7 `test_engine_dependency_direction.py`

`src/trader_core/**` içinde `trader_engine` içe aktarması **yok** (tersi yok, §1.0 değişmez ilke 1); `trader_engine` içinde `trader_core`'dan yalnız şu modüller içe aktarılır: `risk`, `signals`, `regime`, `indicators`, `ledger`, `veto`, `config_loader.deep_merge` (`health` ve `budget` **içe aktarılmaz**: sağlık toplayıcısı ve bütçe/veto servisleri ayrı işlerdir). Özel (`_` önekli) `trader_core` adları kaynakta içe aktarılmaz (`from trader_core.ledger import _EXIT_REASONS` yasak; 02 uyum testi bunu **testte** kullanır, kaynakta değil). Motor modülleri arası döngü yok: `types/errors/numeric/clock/bars/fileio/config` yaprak (içe aktarma yalnız birbirleri ve stdlib); `marketdata/*` ve `brokers/*` `engine`, `gates`, `strategy_runner`, `state`, `order_manager`, `position_manager`'ı **içe aktarmaz**; `position_manager`, `order_manager`, `state` `engine`/`gates`/`strategy_runner`'ı içe aktarmaz (04 §2). Testte bu kurallar bir "izinli kenarlar" tablosuyla (`ALLOWED_EDGES`) ifade edilir.

### 4.8 `test_engine_test_names_unique.py`

`tests/` ve `tests/engine/` altındaki tüm `test_*.py` dosya adları tekildir (pytest `rootdir`/`prepend` modunda çakışma olmaması; `tests/engine/__init__.py` yoktur); `tests/engine/fixtures` dışında `conftest.py` yoktur ya da yalnız `pythonpath` bağımsız yardımcıdır.

## 5. Değişmezler

1. Bu testlerin hiçbiri ağ, gerçek saat, çalışma zamanı içe aktarma (ağırlık testi hariç) ya da dosya yazma (geçici dizin hariç) kullanmaz; tümü < 5 sn (ağırlık testi < 30 sn).
2. İzin listeleri (`ALLOWED_*`, `FORBIDDEN_TOP`, `ALLOWED_MODULES_A`, `ALLOWED_WALL_CLOCK`, `RISK_NAME_ALLOW`) yalnız mentor onayıyla büyür; küçültmek serbesttir.
3. Taramalar **tüm** `src/trader_engine` ağacını dolaşır (`os.walk`, `__pycache__` hariç); yeni dosya otomatik kapsanır.
4. Yanlış-pozitif sıfır: ihlal bildirimi `dosya:satır:ifade` içerir; sabit metin taramaları yalnız `ast.Constant` (yorum satırları taranmaz, ama kopya başlığı testi yorumları ayrıca doğrular).

## 6. §4.3 silme kapısı ile ilişkisi

`test_no_framework_imports.py` içinde `FREQTRADE_REMOVED = False` sabiti vardır. **Silme commit'i** bu sabiti `True` yapar ve ek denetimler açılır:
- `scripts/`, `config/`, `deploy/`, `src/` altında `freqtrade` (büyük/küçük harf duyarsız) metni **bulunmaz**; **istisna ve izin listesi yoktur** (`FREQTRADE_TEXT_ALLOWLIST` tanımlanmaz). **Mentor kararı (16 Kasım 2026):** uyum kipi adı `fill_model="legacy_compat"` olarak değiştirildi; kod, config, betik ve test adlarında/yorumlarında "freqtrade" yerine "legacy"/"referans" yazılır. Böylece §4.3 madde 7 (`grep -ri freqtrade trader/src trader/scripts trader/config trader/deploy` **boş**) istisnasız geçerlidir. Sözcük yalnız `trader/docs/**`, `trader/research/**` (çapraz doğrulama aracı, dondurulmuş referans yolu `research/reference/freqtrade-2026.10/`) ve bu koruma testinin kendi yasak-sözcük sabitinde (parçalı yazılır: `"freq" + "trade"`) geçebilir. Uyum kipi, çapraz doğrulama raporu kabul edilip paper ↔ backtest eşitliği iki hafta kararlı kaldıktan sonra ayrı commit ile silinir.
- `src/trader_core/health.py` ve `ledger.py` içindeki freqtrade metni/parametre adı §4.3 madde 5 ile temizlenmiş olmalıdır (aksi bu test kırmızı: kapıyı bilerek açan commit'in kabulüdür).
- `docker-compose.yml` yok ya da `freqtradeorg` içermez; `deploy/*.service` `ExecStart` satırlarında `freqtrade`/`docker` yok.
- Temiz ortam testi: `pip freeze` benzeri bağımlılık çözümlemesi bu belgenin dışıdır (CI görevi); burada yalnız `tomllib` listesi denetlenir.

## 7. Elle doğrulanabilir örnekler

1. `src/trader_engine/foo.py` içinde `import ccxt` ⇒ ihlal `foo.py:1:import ccxt` (üst ad `ccxt`). `from binance.client import Client` ⇒ üst ad `binance` ⇒ ihlal. `import trader_core.risk` ⇒ temiz. `import importlib; importlib.import_module(name)` ⇒ ihlal (dinamik içe aktarma yasak).
2. `datetime.now(timezone.utc)` `engine.py` içinde ⇒ `engine.py:LINE: datetime.now` ihlali; `clock.py::SystemClock.now` içinde ⇒ izinli; aynı çağrı `clock.py::helper()` (sınıf dışı) ⇒ ihlal. `from time import sleep as nap; nap(1)` ⇒ ihlal.
3. `max_leverage = 5` `gates.py` içinde ⇒ ihlal; `lev = LOCKED_CFG.min_leverage` ⇒ temiz; `K.check_entry(state, cand, K.RiskConfig(max_trade_risk=0.03))` ⇒ iki ihlal (yapıcı + alan adı); `K.check_entry(state, cand)` ve `K.check_entry(state, cand, K.LOCKED_CFG)` ⇒ temiz.
4. `pyproject.toml` `dependencies = ["pandas>=2.2","numpy>=1.26","pyarrow>=15","requests>=2.31"]` ⇒ yeşil; `"ccxt>=4"` eklenirse ya da `"requests @ git+https://…"` ⇒ kırmızı.
5. Alt süreçte `import trader_engine.marketdata.feed` sonrası yüklü `pandas`/`numpy`/`requests` listesi `[]` ⇒ yeşil; `feed.py` `import pandas` ⇒ liste `["pandas","numpy"]` ⇒ kırmızı.
6. `src/trader_engine/brokers/binance_futures.py` dosyası eklenirse (`PHASE="A"`) ⇒ `test_engine_module_inventory` kırmızı.

## 8. Kabul senaryoları

§4'ün her denetimi için (a) mevcut ağaçta yeşil, (b) kasıtlı ihlalli sentetik ağaçta kırmızı (tarayıcı işlevi `scan_tree(root, rules)` ile geçici dizinde); alias çözümlemesi (`import time as t`, `from datetime import datetime as dt`); `ast.Constant` ile docstring'te yasak ad geçmesi ihlal **sayılmaz** (içe aktarma testi), ama `1l3a`/`motor.` sabit metin testi ve SQL içi saat testi docstring'leri de kapsar (açık ayrım testi); `trader_core` ağacına `trader_engine` içe aktarması eklenince `test_engine_dependency_direction` kırmızı; izin listesi dışı `random` ve argümansız `random.Random()` kırmızı; kopya başlığı bozukken (kaynak yol yanlış, tarih biçimi yanlış) kırmızı; `FREQTRADE_REMOVED=True` kipi yalnız sentetik ağaçta sınanır (gerçek ağaçta kapalıdır).

## 9. Belirsizlikler ve çözümleri

- **Çakışma 1 (silme kabulü ↔ uyum kipi adı):** çözüldü (mentor) — kip `legacy_compat`, izin listesi yok (§6).
- **Test dosyası adı:** tasarım yalnızca `test_no_framework_imports.py`'yi adlandırır; diğer korumalar aynı dosyaya da sığabilirdi, ancak ayrı dosyalar hata mesajlarını ve sahipliği netleştirir (tek dosya istenirse bu belge `4.2–4.8`'i `test_no_framework_imports.py` altına bölüm olarak taşır; denetimler aynıdır).
- **`scripts/`/`research/` kapsamı:** Faz A korumaları bu dizinleri taramaz (`freqtrade_offline.py` ve `run_bt.py` §4.3'e kadar yürürlükte). Bu bilinçli bir boşluktur; `FREQTRADE_REMOVED` kapısı bunu kapatır.
- **`bt`, `ta`, `talib`** gibi kısa/çok anlamlı paket adları yasak kümeye **alınmadı** (yanlış-pozitif riski; `talib` bir işlem çerçevesi değil göstergedir). Gerekirse mentor genişletir; bağımlılık listesi zaten **kapalı küme** (`ALLOWED_DEPS`) olduğundan kurulmayan paket içe aktarılamaz.
