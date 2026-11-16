# Görev 7 — Kalan repolar: qrak/LLM_trader, ft-userdata-llm-share, HydraQuant, freqtrade-agent, Superior-Trade trading-terminal

Tarih: 15 Kasım 2026 · Önceki raporlar: `gorev1_freqtrade_llm.md`, `gorev4_parca_katalogu.md` (başka dalda: `origin/claude/charming-hawking-ab5w5q`; bu dalda yoktu, `git show` ile okudum, dosyaları bu dala taşımadım). Parça kodları (A1…S2) gorev4'tekilerdir; yenileri **H*, F*, T*** ile başlar.

**Yöntem:** `git clone --depth 50` ile oturum geçici klasörüne indirme; yalnızca `grep`/okuma. Hiçbir şey kurulmadı, hiçbir test/betik çalıştırılmadı. Hükümler statik okumaya dayanır; "test var" = test dosyasının varlığı ve kapsamı, geçtikleri **doğrulanmadı**. Satır numaraları klonlanan HEAD'e aittir.

## 0. Önemli sınır: iki repo incelenemedi

| Repo | Durum |
|---|---|
| `qrak/LLM_trader` | **İncelenmedi.** Oturumun `add_repo` çağrısı izin sınıflandırıcısı tarafından reddedildi; reddi aşmaya çalışmadım. |
| `6Kmfi6HP/ft-userdata-llm-share` | **İncelenmedi.** Aynı sebep. |

Dolayısıyla istenen "qrak yansıtma → kural → LLM kararı yolu" ve "SelfReflectionEngine → prompt akışı" için **dosya:satır izi yok**; gorev1'deki "izlemedim" notu aynen geçerli. Aşağıda bu ikisi için hiçbir bulgu uydurmadım. İzin verilirse (veya kullanıcı bu iki klonu elle açarsa) §6'daki sorgularla tamamlanır. Üç repo tam incelendi.

## 1. Özet karar tablosu

| Repo | Ne | Öğrenme döngüsü | Lisans | Test | Karar |
|---|---|---|---|---|---|
| ymcbzrgn/HydraQuant | freqtrade fork'u + 70k satırlık yapay zekâ katmanı | **Kapalı** (kapanan işlem → parametre → canlı karar), kodda doğrulandı | GPL-3.0 | Özgün 6 dosya / ~344 test + upstream testleri | Fikri al (H1, H2); kod alma |
| Sak-114514/freqtrade-agent | Freqtrade REST üstünde yerel sohbet/kontrol ajanı | **Yok** (açık; yalnız sohbet belleği) | **Lisans dosyası yok** | 76 test | H/F: yalnız F1 fikri; alma |
| Superior-Trade/trading-terminal | Next.js terminal; grafikten strateji üretir, hosted API'ye dağıtır | **Açık** (günlük yazılıyor, geri okunmuyor) | Apache-2.0 | 20 `*.test.ts` + e2e | T1 doğrudan/uyarlayarak al |
| qrak/LLM_trader | — | incelenmedi | — | — | karar verilemedi |
| 6Kmfi6HP/ft-userdata-llm-share | — | incelenmedi | — | — | karar verilemedi |

## 2. ymcbzrgn/HydraQuant

**Künye:** GPL-3.0 (`LICENSE`), klonlanan HEAD 2026-05-31 (derinlik-50 klonda 50 commit göründü, geçmiş daha uzun). `user_data/scripts/*.py` tek başına ≈70,5k satır; en büyükleri `scheduler.py` 5795, `neural_organism.py` 2999, `rag_graph.py` 2672, `llm_router.py` 1900; strateji `HydraSizer.py` (4700+ satır).

**Ne yapıyor:** freqtrade'in tüm kaynağını içeren fork + `HydraSizer` stratejisi. Sinyal: kural tabanlı "Evidence Engine" + LLM tartışması (MADAM) + RAG; boyutlandırma: Bayesçi Kelly, "Constitution" sınırları, otonomi merdiveni.

### 2.1 README iddiaları → kodda var mı?

| İddia | Kodda | Canlı karara bağlı mı |
|---|---|---|
| "Her kapanan işlem parametre-nöron altyapısını değiştirir" (BCM + STDP) | ✅ `ParamNeuron` Beta sonrası + BCM `theta_m` `neural_organism.py:836-880`; STDP zaman ağırlığı `CreditAssigner._stdp_temporal_weight` `:1379-1388` (6 saat pencere, üstel sönüm) | ✅ evet (aşağıda tam yol) |
| Forgone-alpha defteri: atlanan sinyaller kaydı, eşik otomatik gevşer | ✅ kayıt `HydraSizer.py:2033-2056` (`log_forgone_signal`), çözüm `:3739-3741`, haftalık eşik uyarlaması `scheduler.py:700` → `_forgone_threshold_adapt` `:5134`, yazım `pair_thresholds` `:5211-5220` (zarf sınırlı: `env_floor/env_ceiling`) | ✅ okuma `HydraSizer.py:2367` (`_pair_confidence_threshold`), kapı `:2787-2793` (altındaysa `min_stake`), stake çarpanı `:2345-2357` (×1.10 / ×0.90) |
| Güven kalibratörü | ✅ `confidence_calibrator.py` | ✅ `HydraSizer.py:2752-2754` `adjust_confidence` |
| Graduated autonomy L0→L5 (Sharpe/DD/gün kapısı) | ✅ terfi ölçütleri `autonomy_manager.py:52-58` (örn. L3→L4: 200 işlem, Sharpe>0,8, DD<%10, 60 gün) | ✅ stake tavanı `HydraSizer.py:3138-3140` (`get_max_stake`) |
| Constitution (sert kurallar) | ✅ | ✅ `HydraSizer.py:3051`; değerlendirilemezse savunmacı kapanış `:3069` |
| Feromon alanı / hormonlar (kortizol, serotonin) | ✅ okunuyor `:1115-1116`, `:2157`, `:2513-2514` (stop genişliği kortizole bağlı), `:1675`, `:2898` | ✅ ama etkinin yönü/işe yarayıp yaramadığı **doğrulanmadı** |
| "Dersler" (`ai_lessons`) RAG'e geri beslenir | ⚠️ yazım `lesson_emitter.py:17-35`; gömme `bidirectional_rag.py:91-100` | ⚠️ LLM prompt'una erişimi satır satır izlemedim |
| "Yedi LLM, Thompson + LinUCB router" | ✅ dosya var (`llm_router.py`) | Okunmadı; öğrenmeyle ilgisi dolaylı |

### 2.2 Kapalı döngü — dosya:satır izi

1. İşlem kapanırken freqtrade `confirm_trade_exit` `HydraSizer.py:3724`. Çift sayım koruması `:3730-3737` (`_processed_exits` anahtarı `trade.id_exit_reason_rate`).
2. Forgone çözümü `:3739-3741`; Bayesçi Kelly (çift/rejim) güncellemesi aynı fonksiyonda.
3. `organism.update_cycle(...)` çağrısı `HydraSizer.py:4073`; tanım `neural_organism.py:2145`. İçeride 16 adımlı döngü (README); nöron güncellemesi + kalıcılık: `_persist_streak` `:2183`, `_maybe_persist` `:2364`, `_persist_hormone_history` `:2369` (SQLite).
4. **Geri okuma:** strateji `_p(param_id, fallback)` yardımcısıyla (`neural_organism.py:2925-2938`, içeride `get_organism().get_param`) parametreleri okur: `HydraSizer.py:2476-2489` (breakeven, Chandelier ATR çarpanları), `:1362-1370` (gösterge periyotları), `:1928` (MTF uyumu), `:2431` (stop-hunt). Hata olursa `fallback` döner (graceful degrade).
5. Ban önerisi doğrudan emir yoluna girer: `HydraSizer.py:4086-4094` (`lock_pair`).

**Hüküm:** döngü **kapalı ve canlı yola bağlı** (kanıt: 3→4). **Ama** (a) güncelleme `confirm_trade_exit` içinde, yani emir **dolmadan** çalışır; koruma anahtarı `rate`'i içerdiği için yeniden denemede `rate` değişirse aynı işlem iki kez öğretebilir (benim çıkarımım, doğrulanmadı); (b) öğrenmenin getiri **iyileştirdiğine** dair kanıt kodda görmedim — `ablation_league.py`, `dry_divergence_report.py` var ama okunmadı; (c) dry-run/forward-test kapısı yok: öğrenilen parametre doğrudan uygulanıyor (otonomi merdiveni yalnız stake'i sınırlar). Bizim hedefimizdeki "önce dry-run'da test et, sonra uygula" bunda **yok**.

### 2.3 Test, güvenlik

- **Test:** `tests/` içindeki ~105 dosya çoğunlukla upstream freqtrade testleri. HydraQuant'a özgü olanlar: `test_ai_scripts.py` (241 `def test_`), `test_sprint_april25.py` (34), `test_audit_fixes_april25.py` (21), `test_dead_intel_revival.py` (21), `test_risk_envelope.py` (20), `test_learning_loops.py` (7) ≈ 344. `test_learning_loops.py` forgone → gölge Kelly → feromon → Thompson kapısı zincirini test ediyor (`:29-267`). Ayrıca `audits/*.yaml` SQL tabanlı bütünlük denetimleri (örn. `A28`: tekrarlı ders yok). CI: `.github/workflows/` upstream'den (ci.yml, audit.yml…).
- **Güvenlik:** `docs/DEPLOYMENT.md:82-100` yedi sağlayıcı + Bybit/Binance anahtarları `.env`'de; çoklu anahtar yuvaları. İzlenen dosyalarda gömülü `sk-/AIza/ghp_` biçimli anahtar bulamadım (grep). FastAPI salt-okunur yüzey :8890 (`api_ai.py`) — kimlik doğrulamasına bakmadım. Verinin LLM sağlayıcılarına (ücretsiz katmanlar) gittiği açık. Fork olduğu için freqtrade güncellemesi zor. GPL-3.0.

### 2.4 Katalog kararı

| Kod | Parça | Karar |
|---|---|---|
| **H1** | "Atlanan sinyal defteri" (forgone-alpha) + haftalık, zarf sınırlı eşik uyarlaması (`forgone_pnl_engine.py`, `scheduler.py:5134-5225`, `HydraSizer.py:2345-2357,2787-2793`) | **Fikri al, yeniden yaz.** Bizim "kapanan işlemden öğren" hedefinin en doğrudan karşılığı: kaçan fırsatı da ölç, eşik değişimini taban/tavanla sınırla, `n/30` güven rampası. GPL → kopyalama. |
| **H2** | `update_cycle` kapanışta tek giriş noktası + `_p(id, fallback)` okuma deseni (`neural_organism.py:2145,2925`) | **Fikri al.** Parametreleri tek kayıt defterinde tut, strateji `fallback`'li okusun. BCM/STDP/hormon kısmını **alma** (kanıtsız karmaşıklık). |
| H3 | `autonomy_manager.py` terfi ölçütleri (işlem sayısı/Sharpe/DD/gün) | **Fikri al** (gorev4 A1 ile birleştir); sayılar kanıtsız, kendi değerlerinizi koyun. |
| H4 | `confirm_trade_exit` çift-sayım koruması | **Alma** (anahtarda `rate` hatası); order_id ile yeniden yazın. |
| — | Tüm fork / 70k satır / LLM router / RAG | **Alma.** |

## 3. Sak-114514/freqtrade-agent

**Künye:** klonlanan HEAD 2026-06-15, **4 commit** (derinlik-50 klonda toplam 4). **Lisans dosyası yok**; README ve `pyproject.toml`'da lisans geçmiyor → varsayılan "tüm hakları saklıdır", yeniden kullanım izni belirsiz. Python ≈11,4k satır (`tools/agent_platform/`, en büyükleri `freqtrade_plugin.py` 945, `chart_plugin.py` 777).

**Ne yapıyor:** Freqtrade'in REST API'siyle konuşan **ayrı FastAPI servisi** (127.0.0.1:8090): OpenAI-uyumlu araç çağırma döngüsü (`agents/trading_copilot.py`), araç kayıt defteri + izin katmanı (`registry/`), doğrulayıcı (`agents/verifier.py`), SQLite bellek, Telegram paneli, PNG grafik araçları. Bir "Trading Copilot": durum sorgula, log oku, düşük riskli kontrolleri (pause/start/reload) onayla.

**Öğrenme döngüsü: açık / yok.** Bellek = sohbet ve gözlem notları:
- Her koşuda `memory_save_observation` `trading_copilot.py:110-123`, davranış kaydı `record_behavior_from_run` `:137`.
- Prompt'a giren: `recent_memory` `storage/db.py:1152-1180` (son 3 gözlem, 2 konuşma, özetler; kısa kesilmiş) ve kısa süreli Telegram bağlamı `trading_copilot.py:1094-1110`.
- Kapanan işlem, PnL veya strateji sonucundan **kural/parametre üretimi yok**; strateji düzenleme araçları bilerek kapalı (README).

**Güvenlik tasarımı (iyi yanı):** `dry_run=false` ise araç yürütme reddi: `registry/tool_registry.py:195-206`, `freqtrade_plugin.py:194-201`; yüksek riskli metin listesi (forceenter/forceexit/dry_run kapatma) `registry/permissions.py:22-65`; çıktı denetleyicisi `agents/verifier.py` (gizli anahtar kalıpları `:8`, "kâr garantisi" ve "yapıldı" iddia kalıpları). Onay gerektiren araçlar `freqtrade_plugin.py:532`. Eksik/risk: API'de kimlik doğrulama yok (`main.py`'de Depends/Bearer grep'i boş; localhost'a güveniyor); `Dockerfile`/compose `FREQTRADE_AGENT_HOST=0.0.0.0` ama port `127.0.0.1:8090`'a bağlı; şifre/anahtarlar `user_data/config.json` ve `agent_llm.env` düz dosyada (gitignore'lu). Varsayılan LLM yerel (`127.0.0.1:1234`) — veri dışarı gitmez, bulut LLM'e çevrilirse gider. `web_search/web_fetch` (Tavily) opsiyonel.

**Test:** `tests/agent/` içinde 76 `def test_` (db 21, registry 16, api 9, verifier 8…). CI yok (`.github` klasörü yok).

**Katalog kararı:**

| Kod | Parça | Karar |
|---|---|---|
| **F1** | Araç kaydı + izin katmanı + dry-run bekçisi deseni (`registry/`) | **Fikri al** (bizim "LLM yalnız önerir, emir yetkisi yok" ilkemizle uyumlu; lisans belirsiz olduğundan kopyalama yok). |
| F2 | `verifier.py` (çıktıda sızıntı/"yaptım" yalanı denetimi) | **Fikri al**; kodu alma. |
| — | Geri kalan (grafik, Telegram, bellek) | **Alma.** |

## 4. Superior-Trade/trading-terminal

**Künye:** Apache-2.0 (`LICENSE` + `NOTICE`; TradingView Advanced Charts yeniden dağıtılmıyor, gitignore'lu). API metaverisi: 1093★, `pushed_at` 2026-11-03 (arama sonucu); klonlanan HEAD tarihi 2026-09-19, 21 commit (fark: `pushed_at` başka dalı da yansıtıyor olabilir). Aynı organizasyonda `Superior-Trade/superior-skills` (232★, MIT) ayrı repo — **incelenmedi**.

**"Claude Code skill'i" iddiası:** gorev1'in skillsllm bağlantısı bunu böyle tarif ediyordu. Repo içinde `SKILL*` dosyası **yok**; README skill'i uzak bir URL olarak anıyor (`Read https://superior.trade/SKILL.md and register`). Reponun kendisi **Next.js 16 uygulaması**: grafiğe çizim → LLM kurulum planı → freqtrade stratejisi üretimi → doğrulayıcı → **barındırılan Superior Trade API**'ye dağıtım (Hyperliquid). Strateji burada çalışmaz (`AGENTS.md`). Yani "freqtrade botu için parça" olarak değil, "LLM kodunu güvenli üretme hattı" olarak değerli; yürütmeyi üçüncü taraf barındırıyor.

**Öğrenme döngüsü: açık.**
- `strategy_log` tablosu (`lib/strategy-log.ts:1-81`): detect → compile_ok/reject → backtest_submit/verify → live_verify aşamalarını `codeHash`/`deploymentId` ile bağlayan denetim günlüğü — **ama okunduğu tek yer** `alreadyLogged` tekilleştirmesi (`:46-48`); prompt'a veya kurala geri dönen bir okuma yok (grep: `schema.strategyLog` yalnız insert + dedupe).
- Bellek yalnız **sohbet sıkıştırma** (`lib/agent-memory.ts`): 24 mesajda bir "narrative + facts" (riskProfile, strategiesBuilt…) özeti; `renderMemory` prompt'a giriyor (`app/api/chat/route.ts:235`, `app/api/detect/route.ts:211`), sıkıştırma `chat/route.ts:488`. Bu kullanıcı tercihi belleğidir, işlem sonuçlarından kural çıkarmaz.

**Test:** 20 `*.test.ts` (vitest; örn. `freqtrade-guard.test.ts` 10 durum, `safety-reject.test.ts`, `sizing-ceiling.test.ts`), `evals/` (e2e: 19 kontrol "hiçbir şey mock'lanmadan", davranış/araç/bellek evalleri), CI `.github/workflows/ci.yml`. Hiçbirini çalıştırmadım.

**Güvenlik notları:** Kimlik doğrulama **bilerek yok** — `lib/account.ts` tek sabit hesap döndürür; `SECURITY.md:44-47`: "Anyone who can reach the port can trade with your key", anahtar para çekebilir → internete açmayın. LLM OpenRouter üzerinden (`agent-memory.ts:29`); grafik ekran görüntüsü, çizimler ve plan dış LLM'e gider. `dry_run` upstream-kontrollü, model değeri silinir (`superior-api.ts:31`). Sentry telemetrisi var (`sentry-*.config.ts`). Kill-switch yalnız para hareketi rotaları için ve env tabanlı, dağıtım gerektirir (`lib/kill-switch.ts:1-12`) — bir bot kill-switch'i değil.

**Katalog kararı:**

| Kod | Parça | Karar |
|---|---|---|
| **T1** | `lib/freqtrade-guard.ts` (348 satır; `validateStrategySafety` `:122`) + `docs/strategy-pipeline.md`: kaldıraçlı stoploss tuzağı, `shift(-N)`/`iloc`/`resample` lookahead yasağı, `startup_candle_count`, hacim kapısı, sabit fiyat penceresi, trailing kuralları, **import izin listesi** (`:15-…`) | **Uyarlayarak al** (Apache-2.0 → kopyalanabilir; TypeScript → Python'a taşıyın). gorev4 A2'nin (AST izin listesi, "açık delik var") **tamamlayıcısı**: kural listesi daha zengin, ama regex/metin tabanlı olduğu için pandas özniteliği gibi yollar için AST ile birleştirin (benim önerim; bu gerekçeyi gerçek istismarla denemedim). |
| **T2** | Doğrulama-onarım döngüsü (`app/api/compile/route.ts`): hata listesi + önceki deneme geri verilir, sınırlı yeniden deneme | **Fikri al** (LLM'in yazdığı strateji/parametre için). |
| **T3** | `lib/metrics-honesty.ts` (8 satır): hesaplanmış backtest yoksa kazanma oranı/beklenen getiri söyletmeme + örneklem/dönem zorunluluğu | **Doğrudan al** (prompt metni; Türkçeleştirin). |
| T4 | `strategy-log.ts` doğrulama merdiveni fikri (compile → backtest → ilk gerçek dolum vs plan) | **Fikri al.** Önemli: bizde bu günlük **geri okunmalı** (burada okunmuyor — döngüyü kapatmak sizin işiniz). |
| — | Uygulama, kill-switch, hosted API entegrasyonu, bellek sıkıştırma | **Alma.** |

## 5. qrak/LLM_trader ve ft-userdata-llm-share (boşluk)

Bu iki repo için: ne yaptığı, öğrenme döngüsü, test, lisans, güvenlik ve katalog kararı **bu oturumda üretilemedi** (erişim reddedildi, §0). gorev1'deki mevcut bilgiler (MIT, 3★, son commit 2025-11-16; `LLMFunctionStrategy.py:546,729` LLM çağrısı; `SelfReflectionEngine` `:99,:138`'de bağlı; `config.example.json:185` düz metin `api_key`; qrak için "N kapanan işlemde yansıtma" yalnızca arama özetinden) **doğrulanmış değil**.

## 6. Boşluğu kapatmak için (izin gelirse) yapılacak aramalar

- ft-userdata-llm-share: `grep -n "SelfReflectionEngine\|reflect\|insight\|lesson" -r .` → `LLMFunctionStrategy.py:99,138`'den motorun dönüş değerini; sonra bu değerin `messages`/`system_prompt` oluşturan yere ulaşıp ulaşmadığını; `trade_experience.jsonl`'ın hem yazıldığı hem **okunduğu** yeri.
- qrak/LLM_trader: `grep -n -i "reflect\|lesson\|rule\|insight" -r .` → kuralı üreten fonksiyon, saklandığı dosya/tablo, ve prompt şablonuna eklendiği satır; "N işlem" tetikleyicisinin sabiti; test dosyaları.

## 7. Gorev4 kataloğuna eklenecekler (özet)

`H1` (fikri al), `H2` (fikri al), `H3` (fikri al), `F1` (fikri al), `T1` (uyarlayarak al), `T2` (fikri al), `T3` (doğrudan al), `T4` (fikri al). Alınmayanlar: HydraQuant kodu (GPL fork, kanıtsız karmaşıklık), freqtrade-agent kodu (lisanssız), trading-terminal uygulaması (hosted API'ye bağlı, kimlik doğrulamasız).

**Ortak ders:** üç repodan ikisinde "öğrenme" ya hiç yok ya da günlük yazılıp okunmuyor; kodda gerçekten kapanan tek döngü HydraQuant'ta ve orada da **ileri-test/dry-run kapısı yok, getiri etkisi kanıtlı değil**. Bizim hedefimiz için (öğren → dry-run'da dene → terfi et) hâlâ gorev4 A1/G1-G4 kapıları gerekir; H1'in zarf-sınırlı eşik uyarlaması bunun "ne öğrenilsin" tarafını besleyebilir.

## 8. Sınırlar

- Statik okuma; çalışma zamanı davranışı, testlerin geçmesi, HydraQuant'ın getiri/etki iddiaları doğrulanmadı.
- HydraQuant'ta yalnızca canlı yola bağlanan öğrenme noktalarını izledim; `ablation_league.py`, `dry_divergence_report.py`, LLM router, RAG, `ai_lessons`→prompt yolu okunmadı. Test sayıları `def test_` sayımıdır.
- Superior-Trade: `superior-skills` ve uzak `SKILL.md` incelenmedi; `app/api/*` rotalarının tamamı okunmadı.
- freqtrade-agent: API kimlik doğrulaması yokluğu `main.py` grep'ine dayanır.
- Lisans değerlendirmesi hukuki görüş değildir.
- Derinlik-50 klonlar nedeniyle commit sayıları alt sınırdır (freqtrade-agent hariç, orada tüm geçmiş 4 commit).
