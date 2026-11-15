# Görev 4 — Parça kataloğu: freqtrade tabanlı, kendi işlemlerinden öğrenen kripto botu için hazır parçalar

Tarih: 15 Kasım 2026 · Önceki rapor: `gorev1_freqtrade_llm.md` (aynı klasör). Bu rapor onun devamıdır; orada verilen genel bulgular tekrar edilmedi, burada **parça düzeyinde** (dosya:satır, test, hata davranışı, lisans) inceleme var.

**Yöntem:** Beş repo `git clone --depth 50` ile geçici klasöre indirildi; yalnızca okuma/grep yapıldı. Hiçbir şey kurulmadı, hiçbir test/betik çalıştırılmadı. Bütün hükümler **statik okumaya** dayanır; "test var" demek testlerin dosyada bulunduğunu ve neyi kapsadığını okuduğumu söyler, geçtiklerini doğruladığım anlamına gelmez. Satır numaraları klonlanan HEAD'e aittir.

| Repo | Klonlanan HEAD | ★ (API) | Lisans |
|---|---|---|---|
| [Bachhsunkid/agent-to-earn](https://github.com/Bachhsunkid/agent-to-earn) | 2026-11-13 | 0 | MIT |
| [danny123-sudo/regime-trading-bot](https://github.com/danny123-sudo/regime-trading-bot) | 2026-10-21 (tek commit) | 0 | MIT |
| [aplicy-com/guarded-trader](https://github.com/aplicy-com/guarded-trader) | 2026-11-14 | 2 | Apache-2.0 |
| [ruiwang20010702/cryptobot](https://github.com/ruiwang20010702/cryptobot) | 2026-02-25 | 21 | AGPL-3.0 |
| [0xethanq/astra-quant-agent](https://github.com/0xethanq/astra-quant-agent) | 2026-10-04 | 421 | **AGPL-3.0 + Commons Clause + ek "anti-scam" eki** (GitHub: NOASSERTION) |

## 0. Özet (karar listesi)

| Kod | Parça | Karar |
|---|---|---|
| A1 | `agent-to-earn/agent/gate.py` terfi kapısı (bütünlük kilidi, lookahead, OOS, sabit-stake karşılaştırma, bekleme süresi) | **Uyarlayarak al** |
| A2 | `gate.py::static_check` (AST izin listesi) | **Uyarlayarak al** — *açık delik var* (§2.2) |
| A3 | `user_data/strategies/guarded_strategy.py` (sabit risk çerçevesi) | **Uyarlayarak al** |
| R1 | `regime-trading-bot/core/adaptive.py` (lever zarfı: kırpma, bütçe, bekleme, geri alma, dondurma) | **Fikri al, yeniden yaz** (kodun çalışma zamanına bağlı olmayan kısımları var) |
| R2 | `core/levers.py` (sınır "anayasası") | **Doğrudan al** (şablon olarak; değerleri kendi stratejinize göre değiştirin) |
| R3 | `core/strategy_state.py::confirm_entry` + `core/grok_agent.py` (LLM vetosu) | **Uyarlayarak al** (sağlayıcıyı değiştir, ağ çağrısını callback dışına taşı) |
| G1 | `guarded-trader/.../dsr.py` (Deflated Sharpe, PSR, min track record) | **Doğrudan al** |
| G2 | `.../null.py` (rastgele-giriş null testi) | **Doğrudan al** (küçük uyarlama) |
| G3 | `.../registry.py` (ekleme-yalnız deneme sicili) | **Uyarlayarak al** |
| G4 | `.../walkforward.py` | **Uyarlayarak al** |
| G5 | `services/conductor` (ikinci katman risk/halt/kill-switch) | **Alma (tümü); `domain/risk.py` + `control_client.py` fikrini al, yeniden yaz** |
| C1 | `cryptobot/evolution/strategy_advisor.py` (ders → kural → prompt, TTL, değerlendirme) | **Fikri al, yeniden yaz** (AGPL) |
| C2 | `cryptobot/data/` toplayıcıları (funding/OI/taker, haber, CoinGlass) | **Uyarlayarak al** (yalnızca `onchain.py` + `crypto_news.py`; AGPL notu) |
| C3 | `cryptobot/freqtrade_strategies/AgentSignalStrategy.py` (sinyal dosyası deseni) | **Fikri al, yeniden yaz** (bayat sinyal hatası var) |
| S1 | `astra/scripts/evolution_shield.py` + `scripts/evolution/lesson_health.py` (ders denetimi, sürümlü bellek, kanıtla emekli) | **Fikri al, yeniden yaz — kodu kopyalama** (lisans) |
| S2 | `astra/scripts/self_improvement_engine.py` (ders üretimi) | **Alma; fikri al** (lisans + ağır bağımlılık) |

## 1. Genel lisans çerçevesi (hukuki görüş değildir)

freqtrade [GPL-3.0](https://github.com/freqtrade/freqtrade/blob/develop/LICENSE). Stratejiniz freqtrade'in `IStrategy` sınıfını içe aktarıp onunla aynı süreçte çalıştığı için **birleşik eser GPL-3.0 kapsamında dağıtılmalıdır** (dağıtırsanız; yalnızca kendi makinenizde çalıştırıp kimseye vermiyorsanız GPL kaynak açma yükümlülüğü doğmaz).

| Kaynak lisans | GPL-3.0 ile birleştirme | Notlar |
|---|---|---|
| MIT (agent-to-earn, regime-trading-bot) | Uyumlu; birleşik eser GPL-3.0 altında dağıtılır | Telif ve MIT metnini koruyun |
| Apache-2.0 (guarded-trader) | GPLv3 ile uyumlu (GPLv2 ile değil) | `NOTICE` dosyasındaki ilgi ve değişiklik bildirimi korunmalı; Apache patent hükmü gelir |
| AGPL-3.0 (cryptobot) | GPLv3 §13 ve AGPLv3 §13, ikisini birleştirmeye izin verir | Birleşik eserde AGPL'nin **ağ üzerinden kullanıcıya kaynak sunma** (§13) yükümlülüğü o kısım için geçerli kalır. Botu yalnızca kendiniz çalıştırıyorsanız pratikte yük yok; panel/API'yi başkalarına açarsanız kaynak sunmanız gerekir |
| AGPL-3.0 + **Commons Clause** + ek madde (astra) | **Uyumsuz sayın** | Commons Clause "Satma hakkı"nı (barındırma, abonelik, danışmanlık, ücretli sinyal dahil) hariç tutuyor (`LICENSE:9-22`); GPLv3 §10 "daha fazla kısıtlama" koymayı yasaklar. Ayrıca ek madde (`:24-47`) belirli kullanımları (ücretli sinyal kanalı, varlık yönetimi vb.) yasaklıyor. Bu OSI-açık-kaynak değildir. **Kodunu freqtrade stratejisine kopyalamayın**; yalnızca fikir düzeyinde yararlanın. Gerçek bir ürün/hizmet planı varsa hukuki danışmanlık alın |

Başka bir not: regime-trading-bot'un yalnızca bir commit'i var; sürüm geçmişi yok. guarded-trader'ın 148 commit'i, `CHANGELOG.md`, ADR'leri ve CI'si var (en olgun repo).

## 2. agent-to-earn

### A1 — `agent/gate.py` terfi kapısı

**(1) Ne yapıyor.** Aday strateji dosyasını sırayla: bütünlük kilidi (`check_integrity`, `:106`; `guardrails.lock` ile korunan dosyaların hash'i, liste `:36-65`), terfi bekleme süresi (`promotions_paused_until`, `:279`; 14 gün, `:72`), statik denetim, `pytest` (`run_tests`, `:209`), `freqtrade lookahead-analysis` (`:214`), iç-örnek + dış-örnek (son 120 gün) backtest (`run_gate:332`, ölçütler `CRITERIA:74-78`), mevcut canlı stratejiyi **sabit stake** ve **en iyi işlem hariç** metrikte yenme (`beats_incumbent:247`, ADR-0007) ve ek drawdown sınırı (`MAX_EXTRA_DRAWDOWN`, `:81`) ile geçirir. Geçerse `promote` (`:295`) dosyayı `live/`'a taşıyıp `strategy` config'ini yazar, `reload_bot` (`:310`) `POST /reload_config` çağırır; kalırsa `reject` (`:304`). Ajan yalnızca kriter başına geçti/kaldı görür, OOS rakamlarını görmez (`public_view`, `:378`). Dosya kilidi (`acquire_lock:321`, bayat kilit 3 saat).

**(2) Kod kalitesi.** `tests/test_gate.py` 652 satır, ~50 test: AST kuralları, bütünlük, `evaluate`, `beats_incumbent` (tek-aykırı-değer testi `:186`), `run_tests`, `lookahead` (CSV senaryoları), incumbent önbelleği, terfi/red, bekleme süresi dört test (`:316-346`), OOS rakamlarının sızmaması (`:354`), uçtan uca ana akış. Kod yöntem-yöntem küçük ve saf fonksiyonlara bölünmüş. CI var (`.github/workflows/ci.yml`).
Hata durumu:
- Bütünlük bozuksa dur (fail-closed) — iyi.
- `lookahead` çıktısı yoksa/komut hata verirse "kaldı" (fail-closed) — iyi (`:214-229`).
- Backtest hatası → "backtest" adımı kaldı, aday elenir (`run_gate`, `:360`) — iyi.
- **Fail-open:** `incumbent_oos` backtest'i patlarsa `None` döner (`:262-275`), `beats_incumbent(candidate, None)` boş liste döner (`:247-249`) → **adayın canlı stratejiyle karşılaştırması atlanır**, yalnızca mutlak ölçütler (`CRITERIA`) uygulanır. Test bu davranışı sabitliyor (`test_incumbent_oos_backtest_failure`, `:249`), yani kasıtlı, ama güvenlik açısından zayıf.
- `promote` önce dosyayı taşıyor, `reload_bot` başarısız olursa "bot reload edilmedi, yeniden başlat" uyarısı veriyor (`:310-318`); dosya/config zaten değişmiş. Yeniden başlatma olursa yeni strateji devreye girer; bu bir kapı değil bildirim.

**(3) Bağımlılıklar / bağımsızlık.** Python stdlib + kendi `common.py` (`run_tools`, docker'lı araç konteyneri, `backtest`, `windows`). `common.run_tools` docker konteyneri varsayıyor; `freqtrade` CLI'sine bağlı. **freqtrade'den bağımsız alınamaz** (zaten freqtrade kapısı), ama LLM'den bağımsız: kapı yalnızca bir `.py` aday dosyası bekliyor. Bizim senaryoda (LLM kod yazmıyor, parametre öneriyor) `static_check` yerine parametre şeması denetimi gelir; backtest/lookahead/OOS/incumbent/bekleme/kilit iskeleti aynen kullanılabilir.

**(4) Lisans.** MIT → GPL-3.0 projeye alınabilir (telif notunu koru).

**(5) Bilinen eksikler.**
- **Çoklu test sızıntısı:** OOS penceresi (son 120 gün) her gece **aynı** ve ajan geçti/kaldı bilgisini görüyor (`:378`, LOOP.md "kriter başına geçti/kaldı"). Yeterince aday denendikçe OOS'a uyum (overfit) olur; kodda deneme sayısı düzeltmesi (DSR vb.) **yok**. Çözüm: G1+G3 (deneme sicili + Deflated Sharpe) eklemek.
- Kriterler gevşek: OOS `min_trades: 15`, `min_profit_factor: 1.1` (`:75`); 15 işlem istatistiksel olarak zayıf.
- Backtest tabanlı kapı; **dry-run/ileri test yok** (bekleme süresi ADR-0008'de "canlı strateji karar verilebilecek kadar çalışsın" için, adayı dry-run'da denemek için değil).
- Hard-coded: `MAX_LEVERAGE = 10.0` (`:80`), kriter eşikleri, pencere süreleri `common.windows`.

**(6) Karar: uyarlayarak al.** Gerekçe: en olgun, test edilmiş terfi kapısı iskeleti; ama (i) OOS tek-kullanımlık/deneme sayılı hale getirilmeli (G1/G3), (ii) incumbent hatasında fail-closed yapılmalı (tek satır: `None` → `["incumbent_unavailable"]`), (iii) ileri dry-run adımı eklenmeli.

### A2 — `static_check` (AST izin listesi, `gate.py:145-206`)

**(1)** Tek sınıf, yalnızca `GuardedStrategy` türevi, modül düzeyinde yalnızca import ve sabit atama, izinli import listesi (`ALLOWED_IMPORTS:83-88`), yasak adlar (`FORBIDDEN_NAMES:89-93`: `exec, eval, open, os, sys, subprocess, socket, getattr…`), `__` öznitelik erişimi yasak, `self` dışına öznitelik atama yasak, korumalı üyelerin ezilmesi yasak.

**(2)** Test: `test_gate.py:55-120` (modül düzeyi ihlaller, metot gövdesi ihlalleri, ezme, sınıf şekli, sözdizimi hatası). Sözdizimi hatası → hata döner (fail-closed).

**(5) Güvenlik açığı (statik okumadan; denemedim):** İzin listesi **pandas ve numpy'yi** içeriyor (`:83-88`) ama bunların *öznitelik çağrılarını* engellemiyor. `pd.read_csv("http://…")`, `pd.read_pickle(...)`, `np.load(...)`, `df.to_pickle(...)`, `df.to_csv(...)` gibi çağrılar `FORBIDDEN_NAMES`'e (yalnızca çıplak ad) takılmaz. Ayrıca `self.config` ve `self.dp` erişimi yasak değil (`self.config["exchange"]` içindeki anahtarlar). Backtest/pytest araç konteynerinde sırlar yok ve ağ yok (ADR-0001 mimarisi), ama **canlıya terfi ettikten sonra** strateji, borsa anahtarının ortamda olduğu `freqtrade` konteynerinde çalışır ve ağa erişebilir. Yani "LLM'in yazdığı strateji kodu güvenli" iddiası bu kapıyla tek başına garanti edilmiyor. LLM'e kod yazdıracaksanız ek önlemler gerekir (öznitelik adı kara listesi: `read_*`, `to_*`, `load`, `fromfile`, `eval`; veya hiç kod yazdırmama).

**(6) Karar: uyarlayarak al** (yalnızca LLM'e kod yazdıracaksanız), **delikleri kapatarak**. Parametre-önerisi modelinde gerekmez.

### A3 — `guarded_strategy.py` (sabit risk çerçevesi)

**(1)** Her stratejinin türediği taban sınıf: risk kodu LLM/aday kodundan ayrılmış. `GUARDED_MEMBERS` (`:54-75`: `stoploss, custom_stoploss, leverage, custom_stake_amount, confirm_trade_entry, protections, adjust_trade_position…`) alt sınıfta ezilirse `__init_subclass__` `TypeError` fırlatır (`:130-136`); izinli zaman dilimleri 1h/2h/4h. Boyutlandırma: stop her zaman stake'in %20'sini kaybettirir (`STOPLOSS_RATIO`), kaldıraç stop mesafesine göre seçilir (`leverage:172`), stake risk bütçesine eşitlenir (`custom_stake_amount:178-190`, risk %1 × `risk_mult`, tavan %2), toplam notional ≤ 10× özkaynak (`MAX_ACCOUNT_LEVERAGE`); drawdown devre kesicileri günlük %5, haftalık %10, aylık %20 (`protections:139-150`); özkaynak tabanı (`EQUITY_FLOOR_RATIO:48`) ve **günlük pair evreni** dışında giriş reddi (`confirm_trade_entry:192-207`; evren dosyası yoksa/bozuksa giriş reddedilir → fail-closed).

**(2)** `tests/test_guarded_strategy.py` 227 satır, ~25 test: ezme yasağı, zaman dilimi, kaldıraç sınırları, stake=risk bütçesi, zarar ≤ maksimum risk, `risk_mult=0` → işlem yok, min stake altı, hesap kaldıraç sınırı, özkaynak tabanı, evren dışı/yok/bozuk dosya → red, devre kesicilerin varlığı. Kapsam iyi, parçanın kendisini gerçekten sınıyor. Hata: `_clamp` NaN/hatalı değerde varsayılana düşer, eksik `stop_dist`/`risk_mult` varsayılan.

**(3)** Yalnızca `freqtrade.persistence.Trade`, `IStrategy`; freqtrade'e bağlı ama başka bağımlılık yok. `user_data/universe.json` beklentisi (`scripts/build_universe.py`) strateji ile birlikte gelmeli; "evren yok → hiç giriş yok" davranışı bunu zorunlu kılıyor.

**(4)** MIT → GPL-3.0 uyumlu.

**(5) Eksikler:** `EQUITY_FLOOR_RATIO = 200 / 340` **sabit kodlanmış** (kendi bütçesine göre, `:48`) — parametreleştirin. Sabitler (`MAX_LEVERAGE=10`, risk %1) projeye özgü. `custom_stoploss` kapalı (`use_custom_stoploss=False`); bu bilinçli ama öğrenen bot için stop güncelleme gerekecekse değiştirilmeli. `StoplossGuard` bilerek yok (yorumda gerekçe: %30 kazanma oranlı trend stratejisini boğuyor). Backtest ile canlı davranışı eşit olsun diye risk mantığı callback'lerde; `confirm_trade_entry` yalnızca yerel dosya okur, ağ yok (freqtrade dokümanındaki zamanlama uyarısına uyuyor).

**(6) Karar: uyarlayarak al.** Gerekçe: "risk kodu LLM'e kapalı" ilkesini kod düzeyinde zorlayan, testli ve küçük (207 satır) bir iskelet; sabitleri bizim bütçemize göre ayarlayıp kullanmak yeterli.

### Bu repodan ADR'ler (fikir)
`docs/adr/0001` (LLM emir vermez, risk kodunu değiştiremez), `0007` (sabit stake + en iyi işlem hariç: bir "AKE" işleminin 100× kazancı yüzünden çıkan yanlış terfi), `0008` (terfi sonrası bekleme), `0006` (nokta-zamanlı evren, backtest'te hindsight'ı önler). Hepsi kısa ve uygulanabilir; **fikri al**.

## 3. regime-trading-bot

**Genel uyarı (önemli):** README "Dört şey bir öneriyle canlı ticaret arasında durur: imza, sınır kırpma, backtest kapısı, 72 saat geri alma" diyor. Kodda bunların **önemli bir kısmı çalışma zamanına bağlı değil** (R1).

### R1 — `core/adaptive.py` (lever zarfı)

**(1)** `AdaptiveConfig` (`:75`). `reload()` (`:117-138`) `strategy_config.json`'u sıcak okur, `_sanitise` (`:252-322`) ile **her okumada** sınıra kırpar, bilinmeyen anahtarı yok sayar. `process_proposal` (`:142`) / `_evaluate_proposal` (`:161`): HMAC imza (`:171-180`) → yasak anahtar (`_find_forbidden`, `:61-72`; tüm teklif reddi) → bütçe (en çok 3 lever, `ADAPTIVE_MAX_LEVERS_PER_CHANGE`; 72 saat bekleme) → kırpma → backtest kapısı (`:225-241`, `evaluator` varsa, `challenger > incumbent` Sharpe) → uygula (`_apply:324`, önceki sürümü `.prev`'e yazar, atomik `tmp.replace`). `check_watchdog` (`:352-405`): 20 işlem veya 72 saat sonra beklenti, baz çizginin altındaysa geri al, art arda 2 geri almada **dondur** (insan `unfreeze` ile açar, `:407`).

**(2) Test ve fail-closed.** `tests/test_adaptive.py` 269 satır, 21 test: bozuk config son iyi değeri korur, yasak anahtar (iç içe dahil), kötü imza, sınır kırpma, `min_confidence` düşürülemez, çok lever, pair evreni lever değil, başarısız backtest engeller, bekleme, teklifin tüketilmesi, geri alma, tutma, pencere, dondurma, çözme. Tasarım iyi düşünülmüş; testler gerçekten bu sınıfı kapsıyor. **Ama:**
- **Çalışma zamanına bağlı değil:** `process_proposal`, `arm_watchdog`, `check_watchdog` için depoda **testler dışında hiçbir çağrı yok** (grep; çağrılar yalnızca `tests/test_adaptive.py`'de). Strateji tarafı yalnızca `reload()` çağırır (`core/strategy_state.py:99`). `strategy_state.py:82` `AdaptiveConfig(settings, alerter=None, evaluator=None)` oluşturur → canlıda **backtest değerlendiricisi yok**, uyarı yalnızca log'da ("No backtest evaluator wired; applying on bounds validation alone", `adaptive.py:241`). `ADAPTIVE_BACKTEST_DAYS` (`levers.py:35`) hiçbir yerde kullanılmıyor. Yani README'deki "30 günlük backtest kapısı" ve "geri alma izleyicisi" **kodda yürütücü tarafından çağrılmıyor**; sadece kütüphane + test olarak var. (Repo "paper mode, under calibration" diyor; muhtemelen yürütücü/çalıştırıcı kısmı eksik veya ayrı. Bu bir çıkarım.)
- **İmza opsiyonel ve zayıf:** `if self._settings.council_secret:` (`:172`) — gizli anahtar boşsa imza kontrolü **atlanır** (README `council/README.md` bunu açıkça öneriyor). Anahtar paylaşılıyorsa (`sign_proposal.py`'yi LLM yanında çalıştırıyorsanız) imza yalnızca "kaynak" kanıtıdır, güvenlik değildir (dosyada da öyle yazıyor).
- `reload()` sınırları **her zaman** uyguladığı için dosyayı kim yazarsa yazsın değerler sınır içinde kalır; bu iyi bir son savunma hattı. Ancak `pair_blacklist` listesi `str` olarak kabul ediliyor (uzunluk/biçim sınırı yok).
- Backtest kapısı tek metrik (Sharpe), `challenger > incumbent` **marjsız**, tek pencere, çoklu-test düzeltmesi yok.
- Watchdog `baseline_expectancy` varsayılanı 0.0 (`AppliedChange`, `:39-46`) ve `arm_watchdog` çağrılmazsa 0'a karşı karşılaştırır; ayrıca "beklenti" tanımı ve nereden hesaplanacağı bağlı değil.
- `_state` ve `_apply` yazmaları `OSError`'da yutuluyor (log). Çok iş parçacıklı/süreçli ortamda kilit yok.

**(3) Bağımsızlık.** Yalnızca stdlib + `core.levers`, `core.settings`. freqtrade'den bağımsız, hatta LLM'den bağımsız; saf Python. Kopyalanabilir ama iskelet düzeyinde.

**(4)** MIT → uyumlu.

**(5)** Yukarıdakilere ek: yalnızca bir commit; sürüm geçmişi yok; README ile kod arasındaki fark güven kırıcı.

**(6) Karar: fikri al, yeniden yaz.** Gerekçe: fikir (veri-yaz-kod-yazma, sınırlı lever, bekleme, geri alma, dondurma) tam olarak aradığımız şey ve test seti iyi bir spesifikasyon; ama canlı bağlantıları eksik ve "imza boşsa atla"/"evaluator yoksa uygula" davranışları fail-open. Kendi sürümünüzde: imza zorunlu veya hiç yok (dosya izni ile korunan dizin), evaluator yoksa **uygulama**, `arm_watchdog` uygulama anında otomatik, ileri dry-run adımı ekle.

### R2 — `core/levers.py` (anayasa)

**(1)** Sabit "dokunulmaz" sabitler (`:26-28`, `MIN_CONFIDENCE_FLOOR=0.70`, `MAX_POSITION_PCT=0.08`, `KELLY_FRACTION=0.25`), bütçeler (`:30-39`), varsayılan lever tablosu (`DEFAULT_LEVERS:43`), sınırlar (`LEVER_BOUNDS:72`), **yasak anahtarlar** (`FORBIDDEN_LEVER_KEYS:88`: `stoploss, max_open_trades, stake_amount, dry_run, api_key, secret…`). Asimetri ilkesi: lever'lar riski azaltma yönünde serbest, artırma yönünde sınırlı (`min_confidence` alt sınırı mevcut değer 0.70).

**(2)** `test_adaptive.py` yasak/sınır/min_confidence testleriyle dolaylı kapsıyor. Saf veri/sabit modülü, hata durumu yok.

**(3)** Sıfır bağımlılık (`pathlib`, `typing`). **(4)** MIT.

**(5)** Lever'lar bu stratejiye özgü (`composite_threshold`, `regime_weights`, `atr_stop_mult`). Dosya yolları sabit (`context/`, `user_data/`).

**(6) Karar: doğrudan al** (şablon olarak). Yapıyı koru, lever adlarını ve sınırları kendi stratejinize göre değiştirin.

### R3 — `core/strategy_state.py::confirm_entry` + `core/grok_agent.py` (LLM vetosu)

**(1)** `RegimeComposite.confirm_trade_entry` (`user_data/strategies/RegimeComposite.py:268-292`) önce günlük risk bütçesi, sonra `is_backtest` ise LLM'i atlar (backtest'te LLM yok), aksi halde `state.confirm_entry` (`strategy_state.py:139-178`). Bağlam sözlüğü (`:150-163`): pair, rejim, bileşik skor, ADX, RSI, BB konumu, bulut konumu, hacim oranı, OBV sapması, X-duyarlılığı, günlük özet. `GrokAgent.decide` (`grok_agent.py:103-152`) `response_format=json_object`, `temperature=0.2`, 20 sn zaman aşımı (`levers.GROK_TIMEOUT_SEC`), yanıtı `_validate` (`:154-190`) ile sözleşmeye bağlar: bilinmeyen eylem → `hold`; güven < 0.70 → `hold`; `size_pct` > %8 → kırpılır; hata/zaman aşımı/bozuk JSON → `hold` (`_hold:74`, `_fail`).

**(2) Test ve hata davranışı.** `grok_agent.py` ve `strategy_state.py` için **test dosyası yok** (`tests/` altında `test_adaptive, council, executor_symbols, features, indicators, regime`; grep `grok_agent|strategy_state` testlerde boş). Fail-closed davranış kodda iyi: LLM yapılandırılmış ama hata verirse giriş reddedilir (`strategy_state.py:165-169`, açık yorum), anahtar tanımlı değilse "determinist katman tek başına" (bilinçli fail-open, log'da uyarı). `_run_sync` (`:189-210`) her çağrıda `asyncio.run` ile yeni olay döngüsü açar.
Sorunlar:
- **Callback içinde 20 sn'ye kadar senkron ağ çağrısı** — freqtrade dokümanı `confirm_trade_entry`'de ağ isteğinden kaçınmayı söylüyor; çağrı ana döngüyü bloklayabilir.
- `GrokAgent(settings, alerter=None)` (`strategy_state.py:84`) → ardışık hata uyarısı (`_fail`, `:192`) canlıda **hiç gönderilmez**.
- `sentiment_for` (`:122`) `update_sentiment` ile beslenmeli, ama `update_sentiment`'i (ve `core/sentiment.py::SentimentFeed.run`'ı) çağıran hiçbir kod depoda yok (grep) → canlıda `x_sentiment` her zaman 0.0 görünüyor. Sentiment kodu var, ama bağlanmamış.
- Dışarı giden veri: pair, fiyat, gösterge değerleri ve günlük özet `https://api.x.ai/v1/chat/completions`'a gidiyor (`grok_agent.py:26`); anahtar `.env`/`XAI_API_KEY`.

**(3) Bağımsızlık.** `aiohttp` + `core.levers`/`core.settings`. Sağlayıcı sabit (xAI). `decide(context) -> Decision` arayüzü temiz; başka sağlayıcıya (Anthropic/OpenAI) uyarlamak küçük iş.

**(4)** MIT → uyumlu.

**(5)** Yukarıdakiler + güvenlik: LLM çıktısı `rationale` 100 karakter kesiliyor ama log'a yazılıyor (log enjeksiyonu düşük risk). Prompt'ta kullanıcı kontrollü metin yok (haber/sentiment metni doğrudan geçmiyor) → prompt enjeksiyon yüzeyi dar; ancak sentiment bağlanırsa (X metni) yüzey genişler.

**(6) Karar: uyarlayarak al.** JSON sözleşmesi + `_validate` + fail-closed mantığı iyi. Değişiklikler: LLM çağrısını callback'ten çıkarıp arka plan sürecine/`bot_loop_start` önbelleğine taşıyın (gorev1 §5), testleri (özellikle `_validate` ve fail-closed dalları) siz yazın, `alerter`'ı bağlayın.

## 4. guarded-trader

### G1 — `services/research/src/research_harness/dsr.py` (Deflated Sharpe)

**(1)** Saf fonksiyonlar: `sharpe_std` (`:19`), `psr` (`:24`), `expected_max_sharpe` (`:29`, Bailey & López de Prado), `min_track_record` (`:38`), `deflated_sharpe` (`:64-90`): bir getiri serisinin DSR'sini, sicildeki deneme sayısı ve Sharpe dağılımına göre verir (`sigma_trials=None` → DSR tanımsız, tahmin etmez).

**(2)** `tests/test_dsr.py` 6 test (az ama saf fonksiyonlar için yeterli). Hata: `t<=1` için `sharpe_std` sıfıra bölme riski taşıyabilir (kontrol görmedim); sabit seri `sd=0` → `sr=0` işlenmiş.

**(3)** `numpy`, `scipy`. freqtrade/LLM'den tamamen bağımsız.

**(4)** Apache-2.0 → GPLv3 ile uyumlu; `NOTICE` korunmalı.

**(5)** Eksik: girdi doğrulaması az; günlük getiri serisinden hesaplıyor (işlem bazlı değil).

**(6) Karar: doğrudan al.** 90 satır, saf, gerekçesi dokümante.

### G2 — `.../null.py` (rastgele-giriş null testi)

**(1)** Adayın çıkışlarını/stop/maliyetini koruyup **yalnızca giriş sinyalini** adayın kendi pair-başı giriş oranıyla Bernoulli çekimleriyle değiştirir (`entry_rates:19`, `entry_mask:55`); çekimler `(seed, pair, mum zamanı)`'nın saf fonksiyonu (splitmix64, `uniforms:38`) → pencere değişse de aynı mum aynı çekimi alır. `verdict` (`:81`): aday Sharpe > null p95 **ve** MDD < null medyanı **ve** en iyi işlem payı ≤ null medyanı.

**(2)** `tests/test_walkforward_null_registry.py` (10 test, null+walkforward+registry birlikte); `test_round2_engine.py` 19 test. Not: dosya içindeki yorum, ms/s/ns zaman damgası hatasını "round 2'de bulundu" diye belgeliyor (iyi işaret: hata bulunup düzeltilmiş).

**(3)** `numpy`, `pandas`. Stratejiye bağlanması için backtest çalıştırıcı (`ft_runner.py`, freqtrade `Backtesting` sınıfını doğrudan çağırıyor, `:18-23`) uyarlanmalı. Saf kısım bağımsız.

**(4)** Apache-2.0 → uyumlu.

**(5)** Eksik: null'u freqtrade stratejisinde "entry maskesi" olarak çalıştırmak için strateji tarafında kancayı siz yazmalısınız; seed sayısı ve eşikler dokümanlarda (`docs/research/evidence-review-2026-10/`).

**(6) Karar: doğrudan al** (`null.py` saf modül), bağlantı kodu küçük işle yazılır.

### G3 — `.../registry.py` (ekleme-yalnız deneme sicili)

**(1)** SQLite, stdlib. Her aday **backtest'ten önce** kaydedilir (`hypothesis` zorunlu, `CHECK (length(trim(hypothesis)) > 0)`), `UPDATE/DELETE` tetikleyicilerle iptal edilir (`:52-59`), `strategy_hash` = kaynak+parametre+ücret+veri anlık görüntüsü+freqtrade sürümü (`:67`); aynı hash tekrar kaydedilemez (N şişirilemez); sonuçsuz kalan deneme aynı id ile devam eder. DSR'nin `n_trials` ve `sigma_trials` girdisi buradan gelir.

**(2)** Testler `test_walkforward_null_registry.py` içinde; tetikleyici davranışını kapsadığını dosya adı/test adlarından değil, kısmen okumadan çıkardım (tam doğrulamadım).

**(3)** stdlib. **(4)** Apache-2.0.

**(5)** Eksik: `canonical_timerange` sabit; sürekli ileri akan (rolling) öğrenme için "deneme" tanımını genişletmek gerekir.

**(6) Karar: uyarlayarak al.** Bizim bağlamda "deneme" = LLM'in önerdiği her parametre/kural değişikliği; kayıt şeması buna uyarlanmalı.

### G4 — `.../walkforward.py`

**(1)** Kayan/çapalı pencere geometrisi (`IS_MONTHS=12`, `OOS_MONTHS=3`, `MIN_OOS_WINDOWS=8`, `:20-23`), her OOS penceresi ayrı backtest, başlık OOS Sharpe birleşik (pooled) günlük getirilerden. Saf, G-test'te kapsanıyor.

**(5)** Eşikler kripto verisi tarih aralığına göre sabit; kendi veri uzunluğumuza göre ayarlanmalı. **(6) Karar: uyarlayarak al.** (Apache-2.0.)

### G5 — `services/conductor` (ikinci katman risk/kill-switch)

**(1)** Ayrı FastAPI servisi: SQLite/Alembic defter, `Decimal`, ekleme-yalnız tablolar, risk döngüsü her 60 sn (günlük zarar %3, tepe özkaynaktan düşüş %10, art arda 3 zarar, ≥ `MAX_CONCURRENT_POSITIONS`), ihlalde kalıcı **halt** + freqtrade `stopentry`. **Yazma yüzeyi tek bir izin listesi** (`adapters/freqtrade/control_client.py:1-47`): yalnızca `stopentry`, `start`, `stop`, `forceexit` (tümü, market), tek bir işlemin açık emrini iptal; `/forceenter` ve `/reload_config` bilerek **yok** (`:11-17`). `adapters/llm.py` yalnızca **stub** (`NotImplementedError`, "3B"); LLM araştırma döngüsü Conductor'da **uygulanmamış**.

**(2)** 42 test dosyası, ~537 test fonksiyonu (grep sayımı), `hypothesis` ve `mypy` dev bağımlılıkları; CI var. README açıkça "Not done: auto-flatten on drawdown (AC4.2) and writing available_capital to Freqtrade" diyor — dürüst eksik listesi.

**(3)** Ağır bağımlılık: FastAPI, SQLAlchemy 2.1, Alembic, APScheduler, boto3 (S3 yedek), python-telegram-bot, healthchecks.io, CAD vergi/kur modülleri (`domain/tax.py`, `fx_rates`). freqtrade'e yalnızca REST ile bağlı → freqtrade'den bağımsız servis olarak ayrı çalışabilir, ama bizim ihtiyacımıza göre **fazlası** var (Kanada vergi, bağış/sermaye çiti, S3 yedek).

**(4)** Apache-2.0 → uyumlu; ayrı süreç olarak çalıştırırsanız GPL birleşimi bile gerekmez (REST).

**(5)** Eksikler: LLM kısmı stub; "auto-flatten" yok (yalnızca giriş durdurur); tek kişilik operatör varsayımı; `reload_config` yazma izni yok → "terfi sonrası yeniden yükle" deseniyle **çakışır** (bkz. §5).

**(6) Karar: alma (tamamı).** Gerekçe: ihtiyaç duyulmayan alan çok. **`domain/risk.py` (saf, `Decimal`, `__post_init__` doğrulamalı) ve `control_client.py` izin listesi desenini fikir olarak alıp küçük bir "bağımsız risk bekçisi" yazın** (özkaynak = defter, freqtrade'in kendi görüşü değil; `stopentry` + `forceexit` ile sınırlı).

## 5. cryptobot (AGPL-3.0)

### C1 — `src/cryptobot/evolution/strategy_advisor.py` (ders → kural)

**(1)** Her gün: **son 14 günde** en az 50 kapanan işlem (`MIN_CLOSED_TRADES:26`, `:255`) varsa kanıt toplar (`_gather_evidence:243`), LLM'den en fazla 2 kural ister (`_call_advisor:302`, JSON şema zorlaması), en fazla 5 aktif kural (`MAX_ACTIVE_RULES:23`); kuralları `data/output/evolution/strategy_rules.json`'a yazar (`_create_rules:367`); süresi dolunca önce/sonra performansla (rejim farkındalıklı `regime_evaluator`) etkililiğini değerlendirip **yenile veya emekli et** (`_expire_old_rules:99`, `_evaluate_expired_rule:145`). Kurallar trader ve risk_manager LLM prompt'una eklenir (`get_strategy_addon:77`, çağrılar `workflow/nodes/trade.py:273`, `risk.py:773`). Yani çıktı **LLM'in bir sonraki kararına serbest metin ek bilgi** olarak gider; doğrudan işlem parametresi değiştirmez.

**(2)** `tests/test_strategy_advisor.py` 15 test. Hata durumu: LLM hatasında boş liste (`:349-365`), kural yoksa boş prompt eki. Fail-safe (kural eklenmezse davranış değişmez).
Sorunlar:
- **Doküman/kod tutarsızlığı:** modül başlığı ve prompt eki metni "14 gün" diyor (`:7`, `:91`), kod `RULE_TTL_DAYS = 30` (`:25`) kullanıyor.
- **Zayıf istatistik:** süresi dolan kuralın değerlendirmesi önce/sonra yalnızca **en az 2 işlemle** yapılıyor (`:171-177`); bu istatistiksel olarak anlamsız bir eşik.
- **Kural denetimi yok:** üretilen kural metni için astra'daki gibi bir "anayasa" kontrolü (yasak kalıplar, örneklem) yok; kural serbest metin olarak LLM prompt'una giriyor. Etki, LLM'in kuralı ne kadar dikkate aldığına bağlı; deterministik risk kodu ayrıca var (README "hard limits"), ama kuralın "kaldıracı yükselt" gibi bir şey demesi engellenmiyor.
- Nedensellik: önce/sonra karşılaştırması rejim düzeltmeli olsa da gürültülü.

**(3)** `cryptobot.config`, `cryptobot.journal.*`, `cryptobot.llm` (kendi çağrıcısı) bağımlılığı; kendi dosya yoluyla. Freqtrade'den bağımsız, ancak kendi `journal` biçimine bağlı (kendi kayıt şeması `actual_pnl_pct`, `status`).

**(4)** AGPL-3.0 → GPLv3 ile birleştirilebilir (§1); ağ hizmeti sunarsanız kaynak açma yükümlülüğü.

**(5)** Yukarıdakiler.

**(6) Karar: fikri al, yeniden yaz.** Gerekçe: yaşam döngüsü (üret → TTL → önce/sonra değerlendir → yenile/emekli) iyi fikir; ama eşikler/denetimler zayıf, kopyalamak AGPL yükümlülüğü getirir, kendi DB'mize (freqtrade `trades` tablosu) bağlamak için baştan yazmak zaten gerekecek. Rule denetimi için S1'in fikrini ekleyin.

### C2 — `src/cryptobot/data/` toplayıcılar (funding/OI/haber)

**(1)** Kapsam (kodda doğrulanan): `onchain.py` — Binance Futures **genel** uç noktalarından `get_funding_rate` (`:21`, `/fapi/v1/fundingRate`), `get_open_interest_hist` (`:66`), `get_taker_buy_sell_ratio` (`:115`), 10 sn zaman aşımı, dosya önbelleği (`cryptobot/cache.py`). `crypto_news.py` — CryptoNews API (anahtar gerekli: `CRYPTONEWS_API_KEY`), haber/duyarlılık/trend başlıkları, 15 sn zaman aşımı. `coinglass.py` — CoinGlass likidasyon (anahtar: `COINGLASS_API_KEY`). Başka toplayıcılar da var (ekonomik takvim/Finnhub, F&G, DXY, opsiyon, orderbook, whale, token unlocks, stablecoin, DeFi TVL…; hepsini okumadım).

**(2)** Testler: `test_data.py` (10), `test_coinglass.py` (16), `test_crypto_specific.py` (37) ve diğer toplayıcılar için ayrı test dosyaları (`test_dxy`, `test_defi_tvl`, `test_economic_calendar`…). Hata davranışı: **fail-neutral, "bilinmiyor" işaretli**: `get_funding_rate` hatada `{"current_rate": 0, "error": ..., "data_available": False}` döner (`onchain.py:36-38`); `crypto_news` anahtar yoksa `{"error": "...", "articles": [], "sentiment_score": 0}`; `coinglass` boş sonuçta sıfırlar + `"unknown"` (`:13-21`). Sıfır değer meşru değerle karışabilir; tüketici `data_available`/`error` alanını kontrol etmeli.

**(3)** `httpx` + `cryptobot.cache` + `cryptobot.config.load_settings`; birkaç dosya yeniden yazılarak freqtrade'den bağımsız küçük bir modül yapılabilir. Binance genel uç noktaları anahtar gerektirmez; haber/CoinGlass anahtar ister.

**(4)** AGPL-3.0 (bkz. §1).

**(5)** Haber/CoinGlass ücretli üçüncü taraf; veriler **dışarıya** gönderilmiyor ama istekler pair/zaman içerir. Önbellek yolu sabit; zaman damgası yorumu `_parse_timestamp` (`cache.py:86`) ayrıca var.

**(6) Karar: uyarlayarak al** (yalnızca `onchain.py` + `crypto_news.py`, ~380 satır). Alternatif: freqtrade zaten funding rate verisini backtest için indirir; OI ve taker oranı için `onchain.py` gibi küçük bir modül gerekli. AGPL yükü istemiyorsanız bu üç Binance çağrısını sıfırdan yazmak 1-2 saatlik iştir; o zaman **fikri al** yeterli.

### C3 — `freqtrade_strategies/AgentSignalStrategy.py` (sinyal dosyası deseni)

**(1)** `_read_signals` (`:66-84`) `signal.json`'u mtime önbelleğiyle okur; `populate_entry_trend` (`:126-150`) pair için sinyal varsa ve fiyat giriş aralığında (±%15 tolerans) ise son mumda `enter_long/enter_short=1` yapar; `custom_exit:319`, `custom_stake_amount:424`, `leverage:445` sinyal alanlarını kullanır.

**(2)** `tests/test_strategy.py` 33 test; `:412-423` mtime önbelleği testi mevcut. Hata durumu: dosya yok/bozuk → boş liste (giriş yok; fail-closed).
**Hata (statik okuma):** `_read_signals` önbelleği mtime aynıysa filtrelemeden döner (`:70-72`); `expires_at` süzmesi yalnızca dosya **yeniden okunduğunda** yapılır (`:74-80`). Dosya güncellenmezse **süresi dolmuş sinyal önbellekte kalır ve kullanılmaya devam eder**; testler önbellek davranışını sabitliyor (`test_strategy.py:412-423`) ama süre dolumunu önbellek varken denemiyor. Fiyat aralığı denetimi kısmen koruma sağlar, güvenilir bir TTL değildir.

**(3)** `freqtrade` + stdlib. **(4)** AGPL-3.0.

**(5)** Dosya yolu göreli (`data/output/signals/signal.json`, `:30`), sinyal imzası/yetkilendirme yok (dosyaya yazabilen herkes işlem açtırabilir), atomik yazma garantisi okuyucu tarafında yok (yazar tarafı `monitor.py` "önce yaz sonra sil" diyor).

**(6) Karar: fikri al, yeniden yaz.** Desen (LLM → dosya → strateji okur) gorev1 §5'te önerdiğim mimariyle aynı; ama TTL'yi **her okumada** kontrol eden, imza/hash doğrulayan, parse hatasında "işlem yok" diyen küçük bir sürüm kendiniz yazın (≈50 satır).

## 6. astra-quant-agent (AGPL-3.0 + Commons Clause)

> **Lisans uyarısı:** §1'e göre kodu kopyalamayın. Aşağıda yalnızca nasıl çalıştığı ve hangi fikirlerin alınabileceği var. Repo OKX tabanlı, freqtrade değil; `scripts/` altında yaklaşık 1200 dosyalık büyük bir proje (kullanıcı arayüzü, çok sağlayıcılı LLM geçidi vb.).

### S1 — `scripts/evolution_shield.py` (+ `scripts/evolution/lesson_health.py`)

**(1) Ders denetimi.** `audit_proposed_lesson` (`:154-198`): önerilen ders metni (a) çok kısaysa reddedilir, (b) "emekli" faktör kelimeleri içeriyorsa reddedilir (`RETIRED_FACTOR_TOKENS`, `_retired_factor_hits:139`), (c) **anayasa kırmızı çizgileri**: aşırı yön yanlılığı ("hiç long açma"), stop genişletme, martingale, risk kontrolünü bypass, kaldıraç/marj/pozisyon limiti yükseltme, eşik düşürme, tam marj (`POISON_PATTERNS:62-90`) — "yasak ifadeleri" (ör. "stopu genişletmek yasak") ayrıştırıp muaf tutar (`_strip_prohibition_clauses:98`), (d) mutlak sermaye tutarı yasak (USDT/USD rakamı), (e) örneklem < 2 ise "tek olay" diye reddedilir.
**Ders yaşam döngüsü.** `_review_candidates` (`:451-496`): aynı metin kimliğini korur, başlık tekrarını eler, denetimden geçmeyeni ekler (strict modda hata), REVISE/INVALIDATE'de LLM'in tekrar etmediği etkin dersleri **silmez, pasif arşive (tomb) çevirir** (`enabled=False`, `retired_at`, `retired_reason`). `publish_review` (`:499`): dosya kilidi (`fcntl.flock`, `:405-412`), sürüm kontrolü (`_check_version:431`, `expected_version`; `MemoryConflictError`), atomik commit (`_commit:415`).
**Kanıtla emekliye ayırma.** `lesson_health.py`: ders metninden **hedef kitleyi** çıkarır (`extract_cohort:79` — enstrüman, yön, çıkış mekanizması anahtar kelimeleri), kapanan işlemleri o kitleye süzer (`select_cohort:119`), sağlık puanı = `50 + (kazanma_oranı−50)×0.5 + normalleştirilmiş beklenti×30`, örneklem azsa 50'ye doğru çeker (`score_cohort:140-178`); `decide_archive` (`:241-259`): yeterli örnek (≥10) ve puan < 70 ise arşive; kanıt yoksa değişmez.

**(2) Test.** `tests/llm/test_evolution_shield_gates.py` (130 test), `test_self_evolution_safety.py` (25), `tests/llm/test_evolution_lesson_health.py`, `tests/ops/test_self_improvement_engine.py` ve birçok "extraction" testi. Test kapsamı gerçekten bu parçayı hedefliyor (örn. `NoPresetDoctrineTests`). Hata davranışı: bellek bozuksa `MemoryCorruptError`, sürüm çakışmasında reddet; LLM tamamen başarısızsa **bellek değişmez** (`NO_CHANGE`, `run_self_evolution`, `self_improvement_engine.py:1059-1273` içinde "Code is Law" yorumu).
Eksikler/uyarılar (statik okuma):
- **Dil bağımlılığı:** kırmızı çizgi kalıpları ve kitle çıkarımı **Çince** anahtar kelimelerle (`做多`, `止损`, `杠杆`…) yazılmış (`:62-90`, `lesson_health.py:52-62`). İngilizce/Türkçe dersleri bu regex'ler yakalamaz → kendi dilinize yeniden yazmak gerekir. Regex tabanlı, anlamsal değil; yeniden ifade edilen riskli kural kaçabilir (kodun kendi yorumları da bu tür kaçakları düzeltme geçmişi olarak anlatıyor: "audit P1-8").
- **Sağlık puanı nedensel değil:** ders uygulandı mı bakılmıyor; dersin tanımladığı **kitlenin** son işlem performansı ölçülüyor. Eşik 70, tarafsız 50 (kazanma oranı %50 + sıfır beklenti → 50) → varsayılan olarak 10 işlemden sonra çoğu ders eleniyor (agresif eşik).
- `fcntl` yalnızca Linux/macOS.

**(3) Bağımlılık/bağımsızlık.** `evolution_shield.py` yalnızca stdlib + `scripts.evolution.lesson_health` (kendi modülü; o da stdlib) — yani **gevşek bağlı**. `self_improvement_engine.py` ise `astra_backend`, `instrument_pool`, `prompt_library`, `astra_gateway` ve OKX defteri biçimine sıkı bağlı. Kapanan işlem şeması (`net_pnl`, `fee`, `snapshot_observability`…) astra'ya özgü.

**(4) Lisans.** AGPL + Commons Clause (bkz. §1): **kopyalama**.

**(5) Güvenlik.** LLM sağlayıcı anahtarı `astra_gateway`/`llm_credentials.py` ile yönetiliyor (incelemedim); işlem verisi LLM'e gidiyor (`call_llm_evolution_review`).

**(6) Karar: fikri al, yeniden yaz — kod kopyalanmaz.** Alınacak fikirler: (i) ders = yapılandırılmış kayıt (id, kategori, metin, örneklem, sağlık, TTL, `enabled`) ve **hiçbir zaman silinmeyip pasif arşive alınması**, (ii) ders yayımlamadan önce statik "anayasa" denetimi + minimum örneklem, (iii) **sürüm/CAS** ile eşzamanlı yazma koruması, (iv) LLM çökerse belleği değiştirme, (v) emekli etme kararını **kanıta** bağlama, ama nedensel (ders-uygulandı/uygulanmadı karşılaştırması) ve makul eşikle.

### S2 — `scripts/self_improvement_engine.py` (ders üretimi)

**(1)** Kapanan işlemleri yükler (`load_closed_trades:431`), sinyal günlüğüyle eşler (`_match_snapshot:396`), çok boyutlu döküm (`_compute_multi_dimensional_breakdown:579`), LLM ile "bilişsel post-mortem" (`call_llm_evolution_review:752`) → `change_status ∈ {NO_CHANGE, ADD, REVISE, INVALIDATE}` ve varlık çarpanları (`asset_multipliers.json`, `normalize_asset_multipliers`) ile `ai_long_term_memory` listesi. `run_self_evolution` (`:1059`): defter sürümünün (SHA-256) değişmediği durumda tekrar çalışmaz; LLM başarısızsa geri dönüş zinciri (biçim hatası → aynı modelle onarım isteği; sonra faturalama/yetki dışı adaylar atlanır, 400 sn bütçe); tüm zincir başarısızsa **değişmez** + deterministik içgörüler (`derive_deterministic_insights:941`).
**Karar noktası:** LLM dersleri yeni dersler `evolution_shield` (S1) denetiminden geçer (`apply_memory_review`, `scripts/evolution/memory_review.py`).

**(2)** `tests/ops/test_self_improvement_engine.py` + 25 güvenlik testi; ayrı ayrı çalıştırılamadı. Hata davranışı iyi düşünülmüş (çok katmanlı geri dönüş, NO_CHANGE fail-safe).

**(3)** Sıkı bağlı (OKX/astra defteri, Çin saat dilimi `parse_beijing`, `fcntl`, QQ bildirici).

**(4)** Aynı lisans sorunu. **(5)** Kodun kendisi 1273 satır; çok sayıda "2026-09/10 düzeltmesi" yorumu geçmişte çok iterasyon yaptığını gösteriyor — iyi (hatalar bulunmuş) ve kötü (karmaşık).

**(6) Karar: alma; fikri al.** Alınacak: "defter sürümü değişmediyse çalışma" (boşa LLM maliyeti yok), çok katmanlı LLM hata kurtarma sırası (format onarımı → alternatif model → deterministik özet), "LLM başarısızsa bellek değişmez" ilkesi.

## 7. Önerilen bileşim (görev → parça → nasıl alınır → uyarlama işi)

| Görev | Seçilen parça | Nasıl alınır | İş |
|---|---|---|---|
| Sabit risk çerçevesi, LLM'e kapalı | A3 `guarded_strategy.py` | MIT; kopyala, sabitleri (`EQUITY_FLOOR_RATIO`, risk %, kaldıraç) kendi bütçene göre parametreleştir, `GUARDED_MEMBERS` kuralını koru | Küçük |
| Kaldıraç/bütçe/sınır "anayasası" (öğrenme çıktısının zarfı) | R2 `levers.py` | MIT; yapıyı kopyala, lever adlarını ve sınırlarını değiştir | Küçük |
| LLM'in canlı girişi veto etmesi | R3 `confirm_entry` + `grok_agent._validate` + JSON sözleşmesi | MIT; sağlayıcı arayüzünü Claude/OpenAI/DeepSeek'e uyarla, LLM çağrısını `bot_loop_start`/arka plan sürecine taşı (callback'te yalnızca önbellek), `alerter` bağla, testleri yaz | Orta |
| LLM karar/sinyal dosyası → strateji | C3 deseni (kendi yazımınız) | Fikri al; TTL'yi her okumada kontrol et, atomik yazma, imza/hash, parse hatasında giriş yok | Küçük |
| Piyasa verisi (funding/OI/taker, haber) | C2 `onchain.py`, `crypto_news.py` | AGPL: ya uyarlayarak al (yükümlülüğü kabul et) ya da 3 Binance genel çağrısını sıfırdan yaz; `data_available` alanını tüketicide kontrol et | Küçük |
| Kapanan işlemlerden "ders" üretme (işlem günlüğü → istatistik → LLM yansıtması) | Kendi yazım; fikirler C1 + S1/S2 | Günlük: freqtrade `/trades` + `custom_data`; istatistik döküm (S2 `_compute_multi_dimensional_breakdown` fikri); LLM ≤ N öneri; çıktı **veri** (parametre) veya denetlenmiş kısa kural | Büyük |
| Ders/öneri denetimi (zarar verme) | S1 fikri + R1 `_find_forbidden/_sanitise` | Yeniden yaz: şema + yasak anahtar + sınır kırpma + minimum örneklem; kendi dilinizde yasak ifade kalıpları | Orta |
| Kanıtla emekli etme / TTL | S1 `lesson_health` + C1 TTL fikri | Yeniden yaz; **nedensel** karşılaştırma (uygulanan vs uygulanmayan işlemler veya önce/sonra + rejim), makul eşik ve en az örneklem (≥ 30) | Orta |
| Değişikliğin test edilmesi (backtest + OOS + sabit stake + sürüm) | A1 `gate.py` iskeleti | MIT; incumbent hatasında **fail-closed** yap, aday türü parametre seti olduğu için `static_check` yerine şema denetimi koy | Orta |
| İstatistiksel dayanıklılık (çoklu test düzeltmesi, null) | G1 `dsr.py`, G2 `null.py`, G3 `registry.py`, G4 `walkforward.py` | Apache-2.0; `dsr.py` ve `null.py` doğrudan; `registry.py` ve `walkforward.py` bizim "deneme" tanımımıza uyarla | Orta |
| Dry-run ileri test + terfi | Kendi yazım (parça yok) | İkinci freqtrade dry-run örneği (ayrı `db_url`, port), aday parametreyle N işlem/gün çalıştır, canlı dry-run'la karşılaştır; ardından terfi | Büyük |
| Terfi/yeniden yükleme + geri alma | A1 `promote/reload_bot` + R1 geri alma fikri | A1'in `shutil.move`+`/reload_config` desenini kullan; R1'in geri alma/dondurma durumunu (20 işlem/72 saat) yeniden yaz, `arm_watchdog` terfi anında otomatik | Orta |
| Bağımsız risk bekçisi / kill-switch | G5 `domain/risk.py` + `control_client.py` allowlist fikri | Küçük ayrı servis yaz (defter tabanlı özkaynak, `stopentry`/`forceexit` ile sınırlı); `/forceenter` ve konfig yazımı yok | Orta |
| LLM'e kod yazdırma (isteğe bağlı, öneri değil) | A2 + güçlendirme | Ancak gerekirse; `pd.read_*`, `to_*`, `np.load` vb. engelle, ayrı konteyner/ağsız çalıştır | Büyük (ve riskli; önermem) |

## 8. Parçalar arası çakışmalar ve uyumsuzluklar

1. **Terfi yöntemi çakışması (A1 ↔ G5 ↔ R1).** A1 terfiyi `POST /reload_config` ile yapıyor (`gate.py:310`); Conductor'un yazma izin listesi `/reload_config`'i bilerek **yasaklıyor** (`control_client.py:15-17`). İkisini aynı sistemde kullanırsanız bekçi servisi terfi aracını bloklar. Çözüm: bekçiyi "yalnızca durdur/acil çıkış" ile sınırlı tutup terfi kanalını ayrı (operatör/gate) yapın ya da bekçi dışındaki REST istemcisine `reload_config` izni verin; kararı ADR olarak yazın.
2. **LLM yetki sınırı çakışması (R3 ↔ A3/G5 ↔ C3).** R3 (ve C3) LLM'e `confirm_trade_entry`/`custom_stake_amount`/`custom_exit` etkisi verir; A3'te bu üyeler **alt sınıfta ezilemez** (`GUARDED_MEMBERS`), G5 LLM'e hiç yazma yolu açmaz. Birleştirirken LLM etkisini "risk_mult ∈ [0,1] ve veto" gibi **A3'ün izin verdiği veri sütunlarıyla** sınırlayın; `confirm_trade_entry` A3'te zaten ezilemediği için veto için yeni bir kanca (örn. `populate_entry_trend` içinde `llm_veto` sütunu ya da A3'te koruma altındaki fonksiyona kontrollü bir çağrı) tasarlayın.
3. **Kapı ölçütleri çakışması (A1 ↔ R1 ↔ G1/G2).** A1 "sabit stake + en iyi işlem hariç" kar karşılaştırması, R1 Sharpe karşılaştırması (marjsız), G1/G2 DSR + null kullanır. Tek bir kapıda hepsi birden uygulanmazsa en gevşeği baskın olur. Öneri: A1'in mevcut kontrolleri **ve** (G3 sicilindeki deneme sayısıyla) DSR eşiği **ve** G2 null geçişi; R1'in tek-Sharpe kapısını almayın.
4. **Çoklu test sızıntısı.** A1'in OOS'u her gece aynı; geçti/kaldı bilgisini ajan görüyor. G3 + G1 olmadan ölçüt kısa sürede aşılır. G3 sicilinde A1'in her gece denemesini ve R1'in her lever önerisini "deneme" olarak sayın.
5. **Bildirim/dil çakışması.** S1 anayasa denetimi Çince kalıplarla yazılmış; R1 yasak anahtarları İngilizce; C1 kuralları Çince prompt'la üretiyor. Tek bir dilde (örn. Türkçe/İngilizce) yeniden yazılacak, aksi halde denetim boşluğu doğar.
6. **Lisans karışımı.** MIT (A, R) + Apache-2.0 (G) kopyalanabilir; AGPL (C) kopyalanırsa birleşik eser ağ hizmeti yükümlülüğü taşır; astra (S) kopyalanmaz. Bu yüzden S1/S2/C1/C3'ü "yeniden yaz" olarak işaretledim; yalnızca C2 (üç Binance çağrısı) için kopya seçeneği var ve onu da sıfırdan yazmak kolay.
7. **Dosya-tabanlı durum çakışması.** A1 (`GATE_RESULTS` JSON), R1 (`strategy_config.json`, `adaptive_state.json`), C1 (`strategy_rules.json`), S1 (JSON bellek + md aynası) her biri kendi saklama biçimini kullanıyor; birleştirirken tek bir "değişiklik defteri" (G3 registry'nin SQLite'ı) ve tek bir "canlı parametre dosyası" (R1 deseni) seçin, diğerlerini bunun üstüne kurun. Dosya kilidi (A1 `.gate.lock`, S1 `fcntl`) farklı; çok süreçli çalışıyorsanız tek mekanizma kullanın.
8. **Zaman/rejim tanımı.** R1'in rejimleri (TRENDING/RANGING/BREAKOUT_WATCH), C1'in `regime_evaluator`'ı ve A3'ün `risk_mult`'ı farklı rejim fikirleri; rejim tanımını bir kez yapıp hepsi onu paylaşmalı.

## 9. Sınırlar ve doğrulanmayanlar

- Hiçbir kod çalıştırılmadı; testlerin geçip geçmediği **doğrulanmadı**. "N test" sayıları `def test_` grep sayımıdır (parametrik testler daha fazla senaryo üretir).
- `registry.py` tetikleyici testlerinin kapsamını ayrıntılı okumadım; `walkforward.py` testlerini satır satır doğrulamadım.
- `cryptobot`'ta yalnızca istenen alt klasörler (`evolution/strategy_advisor.py`, `data/`, `AgentSignalStrategy.py`) incelendi; `regime_evaluator`, `workflow`, `journal` ve diğer toplayıcılara (whale, options, orderbook…) bakılmadı.
- `astra` yalnızca `self_improvement_engine.py`, `evolution_shield.py`, `lesson_health.py` düzeyinde incelendi; `llm_credentials.py` ve API anahtarı yönetimi ayrıca incelenmedi.
- Lisans değerlendirmesi hukuki görüş değildir; özellikle AGPL ve Commons Clause maddeleri için kendi durumunuza göre hukuki danışmanlık alın.
- A2'deki "pandas/numpy öznitelik çağrıları engellenmiyor" bulgusu statik okumadan çıkarımdır; istismar denenmedi.
- `regime-trading-bot` için "yürütücü eksik" çıkarımı, depoda `process_proposal`/watchdog çağrısı bulunmamasına dayanır; çalıştırıcı başka bir yerde (ör. özel bir yürütücü) olabilir.
