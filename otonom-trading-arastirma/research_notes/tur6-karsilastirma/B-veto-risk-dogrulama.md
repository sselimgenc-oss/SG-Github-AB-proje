# Tur 6 / B: LLM rolü, yeniden giriş, işlem başı risk, doğrulama (gerçek toplama)

Tarih: 18 Kasım 2026. Kapsam: sahibin 3, 4, 5, 6. maddeleri. Yalnız olgu toplama; hüküm yok (kıdemli gözden geçiren verecek).
Yöntem: yalnız `git clone --depth 1` + `grep/sed/cat`. Hiçbir üçüncü taraf kod çalıştırılmadı. Klonlar: `/tmp/claude-0/-home-user-SG-Github-AB-proje/e7a4ca7f-2079-5069-8ada-ea4ed3c50c7b/scratchpad/repos/` (247 dizin). Kanıt biçimi `repo-dizini/yol:satır` (dizin ön eki: `a_` = Tur-A havuzu, `c_` = Tur-C, `x_` = ek, `t_` = qrak kopyası). İstem enjeksiyonu denemesi: taranan satırlarda görülmedi.
Sınırlar: (1) 247 repoda önce 4 konu için otomatik regex taraması (sayımlar kapsam bölümünde), sonra ~45 repo elle okundu. Elle okunmayanlar için tablolara yalnız tarama satırı girdi ve "tarama düzeyi" diye işaretlendi. (2) Sayı = repo varsayılanı, canlı ayar değil. (3) "yalnız README" işareti kodla doğrulanmayanlara konuldu.

## 0. Bizim şu anki değerlerimiz (karşılaştırma tabanı)

| Alan | Bizim değer | Kaynak |
|---|---|---|
| LLM rolü | Yalnız veto (`veto_mode: required`; veto belgesi yoksa/bayatsa giriş açılmaz). LLM karar vermez, aday üretmez, risk artıramaz. Tek model `claude-haiku-5-5`, `temperature 0`, `max_tokens 2000`, belge ömrü `ttl_s 2700` (45 dk), `request_timeout_s 30`, `parse_retries 1`, önbellek 1 saat. Veto bağlamı: 4s mum 200, 1s mum 72, getiri 1/4/24 saat. Çift başına tek belge (10 çiftin hepsi tek döngüde; notta "tek istekte 8 parite, 30 dk" tasarımı) | `trader/config/veto.json:1-16`, `trader/config/engine.base.json:15` (`veto_mode`), `research_notes/diger-hesap/gorev9_claude_api_maliyet.md:100` |
| LLM maliyet tavanı | Günlük veto 0,25 $, günlük ders 0,10 $, aylık 10 $, aylık uyarı 5 $, günlük %70'te uyarı, ön ödemeli kredi 10 $, kredi 3 $ altında uyarı, toplu istek çarpanı 0,5. Fiyat: haiku-5-5 girdi 0,10 / çıktı 0,50 $/Mtok; sonnet-5-5 2,00/10,00. Ayrı iki anahtar (veto, ders). Veto sınırı dolarsa yeni işlem açılmaz | `trader/config/budget.json:1-23`, `tasarim-kararlari.md:42` |
| Yeniden giriş | v1b: aynı mumda yeniden giriş yasağı. Son çıkış nedeni `stop` veya `trail_stop` ise ve çıkış zamanı `[bar_open, D)` içindeyse aday sinyali kapatılır (`v1b:same_bar_reentry`). Yalnız bu iki neden; hedef/zaman/rejim çıkışlarında yasak yok. Başka soğuma süresi yok. `shadow_blocks` listesinde gölge olarak da kaydedilir | `trader/src/trader_engine/strategies/price_action_v1.py:19,79-91,99,104`, `trader/config/engine.base.json:24` |
| İşlem başı risk | Hedef `target_trade_risk = 0,005` (%0,5; 1000 $ cüzdanda ≈ 5 $). Kilit tavanı: gerçekleşen işlem başı kayıp ≤ %2 (`max_trade_risk 0.02`), kilit varsayılan hedefi %1,4 | `trader/config/engine.base.json:6`, `trader/src/trader_core/risk.py:69-81` |
| Kademe kuralı | %0,35 (yalnız iniş) → %0,5 → %0,75 → %1,0 → %1,2 → %1,4 (tavan). Her artış: ≥100 canlı işlem (sonrakiler ≥60), ≥8 hafta (≥6), ortalama net R ≥ 0, alt güven sınırı (%90 tek yön) > 0, son 200 işlemde en kötü düşüş × yeni risk ≤ %12, kâğıt-canlı tutarlılığı, 30 gün temiz, kullanıcının Telegram onayı. İniş otomatik: tepeden −%10 bir basamak, −%15 en alta; −%20 (yatırılan tabana göre) yeni giriş durur. Değerlendirme 4 haftada bir. En erken ilk artış mart başı | `otonom-trading-arastirma/risk-kademe-kurali.md:3-6,40-70` |
| Kaldıraç | 3–5x, izole, tek yönlü (varsayılan 3: paper-broker örneklerinde `kaldıraç 3`); likidasyon güvenlik çarpanı 1,5; bakım marjı 0,004 | `risk.py:77-80`, `trader/docs/motor/03-paper-broker.md:167`, `tasarim-kararlari.md:38` |
| Günlük/toplam sınır | Günlük en çok %5 zarar (`daily_max_loss 0.05`), toplam açık risk %6, aynı yönde %4. Eşzamanlı işlem sayısına ayrı sınır yok (`max_open_trades=-1`; sahibin 7. maddesi ayrı ajanda) | `risk.py:74-76`, `trader/docs/motor/06-crosscheck-sonuc.md:220`, `tasarim-kararlari.md:38` |
| Doğrulama (CANLI-K1, dondurulmuş) | (1) 2021-01→2026-04, 10 çift, sınav 2022-01→: ortalama net R > 0 ve %90 alt sınır > 0 (gün bloklu bootstrap), kâr faktörü > 1, 4 dilimin ≥3'ü artı, 2024-01 sonrası artı, ≥800 işlem, her çift çıkarılınca > 0; (2) maliyet stresi (komisyon ×2 + 5 bp/taraf): ≥ −0,05 R; (3) DSR ≥ 0,95, deneme sayısı = max(10, 1 + S2 denemesi); (4) kilitli dönem (2026-05→2026-10) yalnız geçen tek aday için, kullanıcı onayıyla, bir kez: beklenti > 0, kâr faktörü > 1; (5) ≥4 hafta kâğıt + 14 gün testnet temiz; canlı: 300 $, %0,5, −%20 duruş | `otonom-trading-arastirma/karar-notu-strateji-2026-11-18.md:26-35`, `trader/docs/ml/s2-on-kayit.md:42-60` |
| S2 ön kayıt | En çok 6 deneme; keşif bölgesi 2021-01-01→2024-01-01 serbest; deneme tanımı + `research/trial_registry.csv` satırı tam koşudan önce commit; sonuç değişirse yeni deneme sayılır; başarısızlar silinmez; dondurulmuş dosya listesi; DSR için güç ön hesabı (n=1576 gün, N=10 → günlük SR ≥ 0,082, yıllık ≈ 1,57). Bu belge commit'lendiği anda §1,2,5,6,7 donar | `trader/docs/ml/s2-on-kayit.md:3,7-22,53-56` |
| Ek (LLM harici) | 1l3a'da "Koç" LLM'siz; ct'de LLM yok (aşağıda 6) | |

## 1. Madde 3: LLM'in rolü (karar verici / veto / danışman / risk), sembol başına çağrı, maliyet

Rol etiketleri: KARAR = LLM işlemi önerir/açtırır; VETO = LLM yalnız "hayır" diyebilir; DANIŞMAN = bilgi/analiz; ÖĞRENME = çevrimdışı/gece döngüsü; DOĞRULAMA = yalnız araç.

| Repo | Ne yapıyor (kod kanıtı) | Sayılar / varsayılan |
|---|---|---|
| danny123-sudo/regime-trading-bot (`c_danny123-sudo_regime-trading-bot`) | **VETO.** Sistem istemi "işlem bulmak senin işin DEĞİL, zayıfı veto et; varsayılan hold" (`core/grok_agent.py:33`); hata/zaman aşımı hep HOLD (fail-closed) (`core/grok_agent.py:111,133-138`); `confirm_trade_entry` içinde: önce günlük risk bütçesi, sonra Grok (`user_data/strategies/RegimeComposite.py:273-286`). **Yalnız canlıda; backtestte atlanıyor** ("deterministik katman ölçülsün") (`RegimeComposite.py:282-285`) | Sağlayıcı xAI Grok, `temperature 0.2` (`core/grok_agent.py:119`); `GROK_TIMEOUT_SEC` levers'ta |
| FilipeThome/the-trader-bot (`c_filipethome_the-trader-bot`) | **VETO + küçültme (DANIŞMAN)**, DeepSeek. Modlar `off`/`shadow` (sorar, kaydeder)/`filter` (veto edilen satırı otomatik işlemden çıkarır ya da boyutunu küçültür); danışman "yalnız çıkarır ya da küçültür", mandate'ın parçası değil (`bot/config.py:169-190`). Ayrı iş parçacığında çalışır, `reduce` kararı boyutu kısar (`bot/runtime.py:34`); test satırlarını hiç sormaz (`bot/runtime.py:727-729`) | Varsayılan `mode: off`; `daily_budget_usd 1.0` (üst 50); `min_veto_confidence 0.6`; `require_verdict False` (başarısız/geç çağrı girişi durdurmaz); `wait_seconds 45`; model `deepseek-flash` (`bot/config.py:183-190`) |
| 0xethanq/astra-quant-agent (+ r20-quantum-trader aynası) | **KARAR.** "Havuzdaki tüm kripto sürekli vadeliler tek makro-bağlam LLM çağrısına girer" (`backend/scripts/ai_brain_trader.py:2-4`); LLM önerir, boyut/limit tek kaynaktan kodda (`backend/scripts/risk_constants.py`); istem ile kod aynı fonksiyonu kullanır (aynı dosya satır 165-190 yorumu) | Çağrı başına tüm semboller (sembol başı çağrı yok). Önbellek ısıtıcı `max_tokens=1` (`backend/astra_gateway/cache_warmer.py:212`). Maliyet tavanı kodda bulunamadı (tarama) |
| rgg81/crypto-trade-claude-code (`c_rgg81_crypto-trade-claude-code`) | **KARAR + deterministik risk kapısı.** Claude alt-ajanları: araştırma müdürü (5 kademeli derece + çürütülebilir tahmin), trader (ATR stop ≥2R hedef), risk yöneticisi deterministik: "LLM onun önünden geçemez" (`README.md:59-61`); yansıtıcı dersleri yalnız ADAY yapar, terfi istatistik kapısında (`agents/reflector.md:17`) | Kaldıraç çıktıdır, girdi değil (`README.md:66`). Sembol başı tam ekip (tartışma+karar). Maliyet kodu bulunamadı |
| chase-mew/ai-hedge-fund (`c_chase-mew_ai-hedge-fund`) | **KARAR** (Hyperliquid), `autonomy = "approve"` (paper/approve/auto) (`fund.toml:7`). Şampiyon `opus-5.5/single`, 3 gölge model paralel (opus ekip, sonnet, haiku) = canlı A/B (`fund.toml:10-11`) | Döngü `cycle_hours 4`; **`daily_llm_budget_usd 6.0`**; `max_tokens 16000`; Opus 4/20 $/Mtok, haiku 0,10/0,50; haber araması en çok 6 arama × 0,01 $ (`fund.toml:5-6,13-48`) |
| bijectivelabs/bitra (`a_bijectivelabs_bitra`) | **KARAR + kör doğrulayıcı + gözden geçirenler.** Aynı enstrüman için tek karar penceresi: `cooldown_s 900`; `blind_confirmer` ve `reviewer` rolleri ayrı model/sağlayıcıda; `min_support`, `on_missing_reviewer="refuse"` (cevap vermeyen gözden geçiren işlemi reddettirir) (`src/trading_research_agents/templates/strategy.toml:122-153,261`; `README.md:317`) | Örnek (yorum satırı) `daily_cost_budget 5.0`, `max_calls_per_hour 60` (`strategy.toml:90-91`); `DEFAULT_MODEL claude-opus-5-5`, `DEFAULT_MAX_TOKENS 8192` (`src/trading_research_agents/llm/providers/anthropic.py:16-19`) |
| 195440/nof1.ai (`c_195440_nof1.ai`) | **KARAR** (Gate/OKX), kodda kurallar. Döngü her 5 dk, tek karar çağrısı (`README_ZH.md:181`; `src/scheduler/tradingLoop.ts:1620` `temperature 0.4`) | `MAX_LEVERAGE 25`, `MAX_POSITIONS 5`, `MAX_HOLDING_HOURS 36` (`README_ZH.md:182-184`); maliyet kodu: yalnız arayüz sayacı (tarama düzeyi) |
| wquguru/nof0 (`c_wquguru_nof0`) | **KARAR.** `decision_interval: 3m`, `default_model gpt-5` (`go/etc/executor.yaml:6`, `go/etc/llm.yaml:7`); "hold" çıktısında miktar 0, kaldıraç 1 (`gitbook/prompt/system-prompt.md:135`) | Sembol başı çağrı notu yok (tek istem). Maliyet tavanı bulunamadı |
| NoFxAiOS/nofx (`c_nofxaios_nofx`) | **KARAR.** `GetFullDecisionWithStrategy` (`trader/auto_trader_loop.go:124`). Alanlar ayrıştırılmış: `max_margin_usage` "CODE ENFORCED", `min_confidence` "AI guided" (`web/src/types/strategy.ts:208-211`) | `min_confidence 78` (`web/src/pages/StrategyStudioPage.tsx:247`); tarama aralığı 15 dk, otopilotta 5 dk (`web/src/components/trader/TraderConfigModal.tsx:103`, `AutopilotLaunchPanel.tsx:262`) |
| el-bach/claude-trader (`a_el-bach_claude-trader`) | **KARAR** (yönetici ajan `claude-opus-4-5`, izleyici ajan ayrı). Döngü 15 dk (`main.py:58`); izleyici `max_tokens 300` (`agents/monitor.py:82`); toplam açık risk tavanı %2 (`agents/manager.py:33`) | Günlük zarar limiti "TEAM HALTED" (`main.py:84`) |
| codeptor/peri (`a_codeptor_peri`) | **KARAR** (Hyperliquid), "analist" çağrı; kod rayları 2026-08-28 zarar sonrası eklendi (`config.toml:60-95`) | `cycle_secs 900`, sakin 900 / hareketli 300 (`config.toml:37,53-54`); `temperature 0.2` (`config.toml:43`); görsel çağrı `max_tokens 300` (`src/peri/vision.py:61`) |
| ygwyg/MAHORAGA (`c_ygwyg_mahoraga`) | **KARAR/ANALİST** + sert `PolicyEngine` (kill switch `src/policy/engine.ts:79`); LLM min tutma süresi `llm_min_hold_minutes` (0–1440; test 30) (`src/schemas/agent-config.ts:31`); sınıflandırıcı `temperature 0.3`, `max_tokens 500` (`src/providers/llm/classifier.ts:45-46`) | `min_analyst_confidence` (0–1), `stop_loss_pct` 1–50, `position_size_pct_of_cash` 1–100 (`agent-config.ts:14-18`) |
| qrak/LLM_trader (`x_qrak_LLM_trader`, `t_llmtrader` aynı içerik) | **KARAR** (iç simülasyon defteri), `timeframe 4h` (`config/config.ini.example:19`); karar kapısı `min_confidence_pct 20` (`src/config/loader.py:560`); devre kesici `cooldown_seconds 120` (`loader.py:166`) | `temperature 1.0`, `max_tokens 32768` (`config.ini.example:110-114`); `max_position_size 0.10` (`loader.py:711`) |
| erfaniaa/LLM-Auto-Trader (`c_erfaniaa_llm-auto-trader`) | **KARAR** + maliyet izleyici; LLM art arda 3 kez başarısız olursa devre kesici (`src/risk/circuit_breakers.py:61`) | `daily_budget 5.00 $` (`src/llm/cost_tracker.py:33`) |
| ryanfrigo/kalshi-ai-trading-bot (`c_ryanfrigo_kalshi-ai-trading-bot`) | **KARAR** (tahmin piyasası; yalnız maliyet örneği) | Piyasa başı günde ≤4 analiz (`src/config/settings.py:138`); `daily_ai_cost_limit 10.0 $`, limit dolunca gün sonuna uyku (`settings.py:142-146`) |
| ymcbzrgn/HydraQuant (`c_ymcbzrgn_hydraquant`) | **KARAR + öğrenme**; maliyet izleyicisi `check_budget(daily_limit_usd=5.0)` (`user_data/scripts/llm_cost_tracker.py:190`) | Kelly merdiveni için bkz. 5 |
| a_millw14_merrymen | **KARAR**; `llmModel claude-opus-4-8`, `llmIntervalMin 30` (`packages/core/src/settings.ts:1189-1191`) | 30 dk |
| yi-111-a/alphaloop-crypto | **KARAR**; `DECISION_INTERVAL_MS = 4 saat` (`webui/app.py:55`) | 4 saat |
| virattt/ai-hedge-fund (`c_virattt_ai-hedge-fund`) | **KARAR (kişilik sinyalleri)** + deterministik risk (aşağıda 5); `DEFAULT_MODEL claude-opus-5-5` (`hedge_fund/llm/client.py:36`) | Ticker başı kişilik çağrısı; maliyet kodu bulunamadı |
| TauricResearch/TradingAgents (`x_TauricResearch_TradingAgents`) | **DANIŞMAN** (emir kodu yok). Boğa/ayı tartışması `max_debate_rounds=1`, risk tartışması `max_risk_discuss_rounds=1` (`tradingagents/graph/conditional_logic.py:7`) | Sembol başı çok ajanlı zincir (tartışma turları ×ajan); `TEMPERATURE 0.0`, `MAX_TOKENS 8192` yorumda (`.env.example:73-79`) |
| aithos-rr/ai-agent-for-trading (`a_aithos-rr_ai-agent-for-trading`) | **KARAR; kod kelepçesi.** LLM kaldıraç 30 önerir, DB'ye ≤10 yazılır ve `leverage_clamped=True` (`progress/log.md:1228-1231`); HOLD/FLAT'ta `size_pct=0, leverage=0` zorunlu (`src/aiat/domain/schemas.py:75`) | `AIAT_TEMPERATURE=0`, `MAX_TOKENS=4096` (`.env.example:57-59`) |
| HKUDS/Vibe-Trading (`c_hkuds_vibe-trading`) | **KARAR sınırlı "mandate"**: ajan değiştiremez; alanlar `max_order_notional_usd`, `max_total_exposure_usd`, `max_leverage` (1.0 = nakit), `allowed_instruments` (boş = hepsi yasak), `max_trades_per_day` (`agent/src/live/mandate/model.py:55-77`) | Sayı varsayılanı yok (kullanıcı imzalar) |
| aplicy-com/guarded-trader (`c_aplicy-com_guarded-trader`) | **LLM emir veremez** (önceki tur notu; bu turda yalnız kapı kodu doğrulandı); Freqtrade + araştırma donanımı (`services/research/src/research_harness/cli.py`) | |
| Bachhsunkid/agent-to-earn (`c_bachhsunkid_agent-to-earn`) | **ÖĞRENME** (gece LLM döngüsü strateji önerir; işlem başına LLM yok). Terfi kapısı kodda (`agent/gate.py:75-88`) | Kapı sayıları bkz. 6 |
| okx-2pa-agent-web (`c_oficcejo_okx-2pa-agent-web`) | **KARAR** (DeepSeek); yapı dönüşünden sonra 3 mum bekleme (`pa_agent/ai/decision_continuity.py:15`) | |
| gajesh2007/ai-trading-agent (`a_gajesh2007_ai-trading-agent`) | **KARAR**, soğuma kuralı **yalnız istemde** ("açma/ekleme/azaltma/ters çevirmeden sonra ≥3 mum kendi soğuması") (`src/agent/decision_maker.py:55`); `temperature 0` (`:189`) | Kodda doğrulama yok (tarama düzeyi) |
| Drakkar-Software/OctoBot (`c_drakkar-software_octobot`) | **KARAR takımı** (AI trading mode), `recommended_position_size_modifier 0.5` (`packages/tentacles/Trading/Mode/ai_trading_mode/deep_agent_team.py:170`); örnek `temperature 0.3` | |
| 6Kmfi6HP/ft-userdata-llm-share (`c_6kmfi6hp_ft-userdata-llm-share`) | **KARAR** (Freqtrade girişi/çıkışı LLM); örnek model `qwen3-30b`, `temperature 0.6`; `max_leverage 100`, `default_leverage 10` **README örneği** (`README.md:189-219`; yalnız README) | |
| shoaibghulam/binance-ai-bot | **VETO (ML, LLM değil)**: LightGBM kapısı; yeniden eğitim için ≥50 işlem (`frontend/app.js:17`); kapı yalnız doğrulama AUC ≥ 0,55 ise veto eder (önceki tur notu: `research_notes/tur5-derin-tarama/diller_ve_akademik.md:38`, `app/bots/manager.py:851-883`) | |
| Gelişim/yansıma sınıfı (kısa) | rafaelpf07/evotrader (GP, LLM yok), adamCYH/evotrader (Gemini flash `src/evotrader/agents/factory.py:108`), 7thDrag0n/AutoEvolve (LLM strateji kodunu yeniden yazar; `min_trades_before_trigger 30` `config_template.yaml:120`), maxwellcm92/darwinfi (Claude haiku `src/instinct/reflexes/ai-predictor.ts:35`), mnemox/tradememory (Claude, evrim keşfi `src/tradememory/evolution/llm.py:138`) | tarama düzeyi |
| Freqtrade ailesi | freqtrade/freqtrade: **LLM yok**; FreqAI makine öğrenmesi modeli (giriş sinyali ML'den) (`freqtrade/` içinde 23 LLM-kelime eşleşmesi, hepsi alakasız); jerome-benoit/freqai-strategies: ML (`quickadapter/README.md:95`) | |
| Konu dışı / LLM yok (liste) | 1l3a-proje (LLM yok; "Koç" kural tabanlı `motor/canli/koc.py:1`), ct-proje (LLM yok), passivbot, jesse, hummingbot, nautilus_trader, vnpy, go-trader (LLM yalnız örnek betik: `shared_scripts/llm_review.py:22`), go_binance_futures, torchtrade (RL; LLM örnek `README.md:401`) | |

Sahibin sorusu için özet olgular (hüküm değil): (a) LLM'i **yalnız veto** olarak kullanan repolar: regime-trading-bot, the-trader-bot (+ küçültme), shoaibghulam (ML); (b) LLM'i **karar verici** yapıp sert kodu kapı koyanlar: astra, rgg81, nof1.ai/nof0/nofx, chase-mew, aithos-rr, Vibe-Trading, mahoraga, peri; (c) maliyet tavanı kodda olanlar: the-trader-bot günlük 1 $, erfaniaa 5 $, hydraquant 5 $, bitra (örnek) 5 $, chase-mew 6 $, ryanfrigo 10 $; (d) kimse veto için "sembol başına ayrı çağrı"yı zorunlu görmüyor: astra tek çağrı/tüm semboller, nof1 klonları tek çağrı/döngü; the-trader-bot aday satırı başına (kuyruk) sorar; rgg81, bitra, TradingAgents sembol başına tam ekip çalıştırır.

## 2. Madde 4: yeniden giriş / soğuma (cooldown)

Önce not: "aynı mumda yeniden giriş yasağı" adını ya da özdeşini taşıyan repo **bulunmadı** (regex `same.?bar|same.?candle` taraması: yalnız göstergelerde aynı-mum girişi öncelik sırası; `a_deuteriumzzz_bitbotby/src/strategies/ported_ind.py:311,382,1021`; `c_ymcbzrgn_hydraquant/user_data/strategies/HydraSizer.py:2097`). En yakın kurallar mum sayısıyla soğuma: 1l3a, olaxbt, Dahshan, cryptobot, quantbot.

| Repo | Ne yapıyor (kod kanıtı) | Sayılar / varsayılan |
|---|---|---|
| freqtrade/freqtrade | Protections eklentileri: `CooldownPeriod` (kapanıştan sonra çifti kilitler), `StoplossGuard` (belirli süre içinde N stop olursa durdurur), `MaxDrawdown`, `LowProfitPairs` (`freqtrade/plugins/protections/`) | `StoplossGuard trade_limit` varsayılan 10 (`stoploss_guard.py:21`); süreler yapılandırma, kod varsayılanı yok |
| 1l3a-proje (sahibin) | Stop sonrası N mum bekleme: `stop_sonrasi_bekleme_mum`, son stop mumundan `i - son_stop_i <= N` ise giriş `red="bekleme"` (`motor/backtest/motor.py:220,323-325`). Aynı mumda stop ve hedef birlikte değerse stop sayılır (`motor/backtest/motor.py:5,9`) | N yapılandırma ayarı (`cks_ayar`) |
| NoFxAiOS/nofx | Otopilot: son kapanıştan `autopilotReentryCooldown = 4 saat` içinde aynı sembole yeniden giriş yok (`trader/auto_trader_throttle.go:21,110-112`) | 4 saat |
| vedv0987-cloud/bvedtrade | Sembol başı HFT freni: `hft_cooldown_seconds 300` (yorum "was 30 – 10x, per-symbol re-entry brake"), kayıptan sonra `hft_loss_cooldown_seconds 1800`, `hft_loss_cooldown_max_mult 8`; tarayıcıda `_MIN_HOLD_SECONDS 20`; art arda 8 kayıpta kill switch (`backend/config.py:210,859-868`; `backend/hft/scalper.py:79`) | 300 s / 1800 s / ×8 |
| codeptor/peri | Piyasa başı: herhangi kapanıştan sonra `cooldown_secs 3600`, stop-out sonrası asimetrik `stop_cooldown_secs 14400` (`config.toml:80-81`); günde en çok 3 giriş (`daily_entry_cap 3`, `:70-79`) | 1 saat / 4 saat |
| FilipeThome/the-trader-bot | Gün-işlem ön ayarı: `pair_cooldown_minutes 60`, `loss_guard_trades 3` (art arda 3 kayıp = kilit), `max_trades_per_day 8` (`bot/api/presets.py:19-23`) | 60 dk, 3 kayıp, 8/gün |
| erfaniaa/LLM-Auto-Trader | Stop sonrası sembol kilidi `base_minutes × (1 + art arda SL)`; 4 saatte 3 SL = "testere" (chop) → 4 saat kilit ve yeniden giriş için daha yüksek LLM güveni + ADX (`src/risk/cooldown.py:2-8,35-41`) | 30 dk tabanı, chop 3 SL/4 s |
| 0xethanq/astra-quant-agent (+r20 aynası) | `ASTRA_STOP_COOLDOWN_MINUTES 30` (`backend/scripts/risk_constants.py:153` ve `scripts/risk_constants.py:147`), zaman stopu 4 saat / ATR bandı 0,15 (`risk_constants.py:151-152`) | 30 dk |
| chase-mew/ai-hedge-fund | Pozisyon yönü çevirme soğuması `flip_cooldown_hours 12` (`fund.toml:58`) | 12 saat |
| 195440/nof1.ai | Aynı sembol için en az 3 döngü: `MIN_SAME_SYMBOL_COOLDOWN_CYCLES = 3` (`src/tools/trading/tradeExecution.ts:111`; `docs/TRADING_STRATEGIES_ZH.md:1303`) | 3 döngü (×5 dk) |
| wquguru/nof0 | `CooldownAfterClose: 15 dk` (`go/pkg/executor/validator_test.go:175`; test değeri) | 15 dk |
| wyc-dev/MATS | Son açma/kapama 12 saat içindeyse sembole girilmez (`src/index.ts:1351`); ayrıca "6 döngü" kısa soğuma (`:1226`) | 12 saat |
| julian-dev28/pathiel | `cooldown_min` 60 / 120 / 90 ön ayarlarda (`scripts/config_preset.py:92,116,167`); builder reddine `REJECT_COOLDOWN_S 600` (`pathiel/client/builder.py:45`) | 60–120 dk |
| mocasus/trade-agent, kaoi-cyber/ai-trader, islambaraka90/super-agent | `cooldown_minutes 30` (`trade_agent/config.py:43`); `SYMBOL_COOLDOWN_MINUTES=60` (`.env.example:26`, `risk.py:43`); `STOPOUT_COOLDOWN_MIN=60` (`.env.example:117`) | 30 / 60 / 60 dk |
| Gotji253/AI_trading_ADA | `LOSS_COOLDOWN_MINUTES=20` (`docs/risk-rules.md:28`), `MIN_HOLD_DAYS=7` (`.env.example:36`) | 20 dk |
| hypurrquant/perp-cli | `pause_after_loss_sec 300` (`src/bot/config.ts:104`) | 5 dk |
| chrisleekr/binance-trading-bot | `lossCooldownMinutes: 60` "kayıptan sonra bir saat yeniden alım yok" (`docs/concepts/strategies/trailing-trade.md:169`) | 60 dk |
| olaxbt/ai-market-maker | `trade_cooldown_bars` 2 (scalp) / 24 (swing); kill switch soğuması 80 / 160 mum (`config/policy.scalp.json:8,18`, `policy.swing.json:8,18`) | mum cinsinden |
| ruiwang20010702/cryptobot | Taban strateji `_COOLDOWN_BARS = 24` (`src/cryptobot/backtest/baselines.py:21,155-158`) | 24 mum |
| Dahshan228/FTMO-TradingBot | Mum ve dakika soğuması: `cooldown_bars=8`, `max_entries_per_day 1`, aynı gün yeniden giriş için en az `reentry_signal_delta` kadar sinyal değişimi (`src/broker/live_loop.py:281-283`, `src/broker/main.py:480-490`, `src/model/run_training.py:134-135`) | 8 mum, 1/gün |
| max007-coder/quantbot | `cooldown_bars 3` ×300 sn (`quantbot.py:141,814`) | 15 dk |
| Senpi-ai/senpi-skills | `cooldown_seconds 5400`, `per_asset_cooldown_seconds 21600` (`senpi-trading-runtime/references/runtime-yaml.md:98-100`) | 90 dk / 6 saat |
| hummingbot | PMM `buy_cooldown_time`/`sell_cooldown_time` = 60 sn (`controllers/generic/pmm_mister.py:45-46`) | 60 sn |
| alex-jb/orallexa | Sistem kilidi: toplam kayıp 500 $ → 7 gün bekleme; 14 gün Sharpe < 0 → 3 gün; düşüş %15 → 7 gün (`engine/kill_conditions.py:73-90`) | 7/3/7 gün |
| flukelaster/ai-trading-agent | Devre kesici varsayılan 60 dk (`backend/app/risk/circuit_breaker.py:19`); strateji değiştirme 1 saat + günde 3 (`mcp_server/strategy_switch_guard.py:16`) | 60 dk |
| pettekay/ai-forex-trading-bot | 3 art arda kayıpta lot çarpanı 0,5 (`config.py:329-330`) | 3 kayıp → ×0,5 |
| Aynı sınıfta, tarama düzeyi | gajesh2007 (istem içinde ≥3 mum), okx-2pa (3 mum), valory-xyz/trader (`declined_market_cooldown 3600`, `skill.yaml:349`), Dahshan, huntr/hunter (zarar serisi), loveolu (`cooldown_bars=4/24` araştırma `exp_cx_001_dispersion_reversal.py:43`) | |
| ct-proje (sahibin) | Soğuma kuralı yok; yalnız bildirim/radar bekleme (konu dışı) | |

## 3. Madde 5: işlem başı risk, boyutlandırma, kaldıraç, günlük zarar durdurma (sahip %1–2 istiyor)

Boyutlandırma türleri: SABİT% (özsermayenin sabit yüzdesi stopa kadar), KELLY, VOLATİLİTE/REJİM (ATR/rejime göre), PORTFÖY-YÜZDE (pozisyon başı yüzde, işlem başı risk değil).

| Repo | Ne yapıyor (kod kanıtı) | Sayılar / varsayılan |
|---|---|---|
| 0xethanq/astra-quant-agent (+r20 aynası) | SABİT% + mutlak tavan: `min(sabit USDT, bakiye × oran)`; ATR stop (`backend/scripts/risk_constants.py:66,115-190`) | **Risk 2%/işlem** (`ASTRA_RISK_PER_TRADE_RATIO 0.02`), kaldıraç 2–5x, günlük zarar `min(150 USDT, bakiye %5)`, aynı yön en çok 4 pozisyon, güven ≥68, R:R 2.0–3.5, kısmi çıkış %35 @2×ATR (`risk_constants.py:134-160`) |
| rgg81/crypto-trade-claude-code | REJİM × SAĞLIK matrisi: 5 rejimde (kaldıraç, işlem riski, toplam ısı) (`futures_fund/policy.py:8-15`); "caution" katmanı hepsini ×0,5, "stressed" = 0 (`policy.py:25-44`); kaldıraç çıktıdır (`README.md:66`) | `low_vol_trend` 5x/%1,5/ısı %10; `high_vol_trend` 4x/%1,0/%8; `low_vol_range` 3x/%1,0/%8; `high_vol_range` ve `transition` 2x/%0,5/%4. Devre kesici: günlük ≤ −%3 yeni giriş yok, haftalık ≤ −%7, aylık ≤ −%12 zorunlu kapama; tepeden %5 → risk ×0,75, %10 → ×0,5 (`policy.py:56-85`) |
| FilipeThome/the-trader-bot | SABİT%, gün-işlem ön ayarı (`bot/api/presets.py:19-24`); stop `PRESET_STOP_PCT 0.01` (`:15`) | **%0,5/işlem**, günlük kayıp %2, günde 8 işlem, `cost_multiple 3.0`, `min_reward_risk 1.2` |
| vedv0987-cloud/bvedtrade | SABİT% + HFT USD tavanı (`backend/config.py:189-190,346,1188,1204,899`; `CARRY_DESIGN.md:62` "Kaldıraç 3x, 4x ya da 5x değil") | **%1/işlem** (`max_risk_per_trade 0.01`), günlük kayıp %5, art arda 8 kayıp kill switch, HFT işlem başı en çok 5 $ kayıp, toplam HFT riski %8, HFT kaldıraç 2, carry kaldıraç 3 |
| julian-dev28/pathiel | SABİT% (`config/public/agent-config.json:8-13`) | **%1**, günlük kayıp %3, kaldıraç ≤3x, 1 açık pozisyon, min-emir yükseltmesinde en çok %2 |
| codeptor/peri | SABİT%, "Bhanu'nun kararıyla" yükseltildi (`config.toml:67`): "5 %; liq. gürültüye girmeden daha büyük boyut" | **%5/işlem**, kaldıraç ≤20x, ≤3 açık pozisyon (3×5% = %15 = kill switch eşiği), günlük giriş sınırı 3, gün %6 düşünce yeni giriş yok, kill %15 (`config.toml:66-85`), min stop %2, ATR çarpanı 4, min R:R 2 |
| bijectivelabs/bitra | Baz puan: `max_risk_per_trade_bps 50`, `max_position 0.05`, `daily_loss_limit_bps 300`, `max_drawdown_bps 1000` (`templates/strategy.toml:37-43`) | **%0,5/işlem**, poz. ≤%5, günlük %3, tepeden %10 sonra yeni giriş yok |
| a_deuteriumzzz_bitbotby | Üç ön ayar (`src/settings/runtime_config.py:116-135`): muhafazakâr/orta/saldırgan | %1 / %2 / **%4** işlem riski; 2 / 3 / 5 pozisyon; düşüşe göre ölçekleme açık/açık/kapalı; kaldıraç sabit / volatilite / tam |
| el-bach/claude-trader | SABİT% (`README.md:339` `MAX_RISK_PER_TRADE_PCT=0.005`) + portföy açık risk tavanı (`agents/manager.py:33`) | **%0,5/işlem**, toplam açık risk %2 |
| islambaraka90/super-agent | `RISK_PER_TRADE_PCT=0.5`, `MAX_POSITION_PCT=20` (`.env.example:113-114`) | **%0,5** |
| leadline88, aswin-ram-k, boredom198 | `RISK_PER_TRADE=0.01`, `LEVERAGE=1` (`README.md:44-45`); `risk_per_trade 0.01`, `max_drawdown_limit 0.15` ve "30 gün pozitif canlı P&L'ye kadar PAPER" (`config_optimized.yaml:11-14`); `MAX_RISK_PER_TRADE=0.02` (`.env.example:33`) | %1 / %1 / %2 |
| erfaniaa/LLM-Auto-Trader | SABİT% + pozisyon yüzdesi (`src/risk/risk_manager.py:38-47`); devre kesici (`src/risk/circuit_breakers.py:51-61`) | **%2/işlem**, kaldıraç ≤5, tek poz. ≤%25, toplam maruziyet ≤%60, ≤3 eşzamanlı, R:R ≥1,5; tepeden düşüş %5, günlük kayıp %3 |
| mnemox/tradememory | Uyarlanabilir risk `risk_per_trade_pct=2.0` (`src/tradememory/adaptive_risk.py:25`), Kelly ile sapma izleme (`owm/dqs.py:145`) | %2; (önceki tur notu: depo `.zip` dağıtan kopya ailesi, bu x_ kopyası tarama düzeyi) |
| Dahshan228/FTMO-TradingBot | Kayan pencereli Kelly yeniden kalibrasyonu (`src/broker/live_loop.py:285-290`); FTMO: günlük kayıp %5, toplam %10 (`deep_backtest_metals.py:92`) | `max_entries_per_day 1` |
| alex-jb/orallexa | KELLY: varsayılan yarım Kelly 0,5, tavan 0,25 (`engine/kelly_sizing.py:55,62`); sert kayıp 500 $ (`engine/kill_conditions.py:76`) | Kelly 0,5×, tavan %25 |
| mocasus/trade-agent | KELLY: `kelly_fraction 0.5`, `leverage 3` (README örneği `README.md:190,200`), `max_open_positions 5` (`trade_agent/config.py:42`), muhafazakâr profil stop %1,5, ≤3 poz. (`plugins/risk_profile/conservative.py:12-16`) | yarım Kelly |
| ymcbzrgn/HydraQuant | Otonomi merdiveni L0→L5: L0 = %3 Kelly (nano-canlı) ... L5 = %75 Kelly; terfi işlem sayısı, Sharpe, düşüş sınırına bağlı (yalnız README: `README.md:150,267`); kodda `risk_budget.py:151 daily_budget` (`user_data/scripts/risk_budget.py`) | |
| henryzhangpku/autonomous-quant-researcher | KELLY_FRACTION 0,25 (`research/hmm/sizing.py:19`); günlük kayıp limiti ve tepe düşüş kill (`research/hmm/risk.py:62-67`); kapı: Sharpe 1,5, maxDD 0,15, isabet 0,55, t 2,0 (`research/hmm/backtest.py:60`) | çeyrek Kelly |
| flukelaster/ai-trading-agent | KELLY çeyrek (`backend/app/risk/manager.py:151`), devre kesici tepe düşüş (`circuit_breaker.py:159`) | 0,25× |
| ryanfrigo/kalshi bot (tahmin piyasası) | `kelly_fraction 0.25`, `max_position_size_pct 3.0` (`cli.py:86-87`) | çeyrek Kelly |
| nikhilperr/binance-futures-trading-bot | `risk_pct = 0.05` ve sabit kaldıraç 3 (`modules/position_sizer.py:71`, `modules/trade_manager.py:76`) | %5 |
| deneyimsiz küçük botlar | harzem: `MAX_POSITION_PCT=5`, `DEFAULT_STOP_LOSS_PCT=3` (Gotji253 `config/example.env:16-17`); `MAX_POSITION_PCT=15`, `MAX_DAILY_LOSS_PCT=3` (kaoi `.env.example:21-23`); `max_position_pct 0.1`, günlük %3 (x_00hsynclk `main.py:47-51`) | |
| nof1 ailesi (195440, qingshungli, maotouhu, dax-523, etrobot) | Kaldıraç tavanları yüksek: 25x (195440 `README_ZH.md:182`), 30x (`a_qingshungli_super-nof1.ai/README.md:327-328`), 10x (`a_maotouhu_nof1openai/ai_trader.py:70`), 10x/5x (`a_dax-523_ai-trading-agent/app/markets.py:7,14`); hesap düşüş eşikleri %20 uyarı, %30 yeni açma yok, %50 zorunlu kapama (195440 `README_ZH.md:217-219`) | |
| nofx | `max_margin_usage` (kodda zorlanan) varsayılan 0,9–1,0; BTC/ETH ve altcoin için ayrı azami kaldıraç ve pozisyon değeri oranı (`trader/auto_trader_risk.go:243-248`; test örneği 10x ve 5× pozisyon değeri oranı `trader/auto_trader_full_size_test.go:13-16,53`) | |
| passivbot | **Risk işlem başına değil, cüzdan maruziyeti**: `total_wallet_exposure_limit 1.5`, `n_positions 7`; hesap kaldıraç 10 (`src/config/schema.py:49-56,414`); pozisyon başına limit = toplam/pozisyon sayısı | PORTFÖY-YÜZDE |
| virattt/ai-hedge-fund | PORTFÖY-YÜZDE: tek isim ≤%25, brüt maruziyet 1,0, tepeden %10'da yarım boyut, %20'de nakde in (`hedge_fund/fund/example.yaml:27-36`); örnek maliyet: yarım spread 5 bp, işlem başı komisyon 0,005 $/hisse | |
| chase-mew/ai-hedge-fund | PORTFÖY-YÜZDE: piyasa başı ağırlık ≤%0,20, brüt ≤1,5, net ≤1,0, döngü başı yeni risk ≤%0,6, günlük kayıp %4, tepe düşüş %20, borsa kaldıracı 5, canlı özsermaye üst sınırı 1000 $, hafta sonu öncesi ağırlık ≤%0,10, stop %1–12 varsayılan %5 (`fund.toml:50-80`) | |
| 1l3a-proje (sahibin) | SABİT%, **maliyet dahil** risk: `islem_basi_max_risk_yuzde 1.0`, günlük %3 (dolunca açık pozisyon da kapanır), `max_kaldirac 3.0`, kill switch %20, portföy stratejilerinde toplam stop riski ≤%5 (`motor/risk/limitler.py:26-34`; tanım: `maliyetli_risk_birim` aynı dosya `:42-46`). Canlı strateji başı aralık %0,5–1,5, "%3 fikri iptal (%6 toplam risk tavanında yalnız 2 pozisyon sığar)" (`DURUM.md:70,95,133-143`); canlıda 2000 USD tavanı | **%1 (kodda), canlı için %0,5–1,5** |
| ct-proje (sahibin) | Kopya ticaret; USD sabit limitler: günlük zarar 10 $, emir 100 $, toplam brüt 300 $, trader başı 200 $, referans kasa 100 $ (`copytrade/live_koruma.py:25-33`); `max_leverage 15.0` liderler için ölçüt (`copytrade/kurallar.yaml:1`) | |
| freqtrade/freqtrade | Boyut kural değil: `stake_amount`/`tradable_balance_ratio` yapılandırma, `leverage()` geri çağrısı strateji yazarında; Protections (bkz. 4) | Çerçeve; varsayılan risk % yok |
| freqtrade stratejileri | NostalgiaForInfinity `futures_mode_leverage 3.0` (`NostalgiaForInfinityX6.py:176`); Sygnif 3.0 (`SygnifStrategy.py:427`); AutoEvolve hedef düşüş %10 (`config_template.yaml:183`); SmallCapitalFreqAI günlük kayıp 1,5 USDT (`user_data/strategies/SmallCapitalFreqAI.py:81`) | |
| trade-foundry | `RISK_FRACTION = 0.01` yürüyen pencere sınamasında; `MAX_DRAWDOWN_PCT = 30` sağlamlık (`research/trade-long/walkforward.ts:100`, `robustness.ts:24`) | %1 |
| a_valory-xyz_trader | Kelly kriteri stratejisi ayrı paket (`packages/valory/agents/trader/aea-config.yaml:85`) | |
| hypurrquant/perp-cli | `max_position_usd 1000`, `max_daily_loss 100`, kaldıraç 5 (`src/bot/config.ts:101-102`, `apex-strategy.ts:46`) | |
| a_hunter (mikegianfelice) | AI sürüş: günlük kayıp %5, azalış çarpanı 0,5 (`src/ai/ai_drawdown_protection_system.py:63-75`) | |
| web3spreads/quant-flow | Tepe düşüş %10 / günlük %5, 4 saat duraklatma (`src/config.py:29-30`) | |
| orta düzey 20x-100x örnekler | ct/peri 20x, 6Kmfi6 `max_leverage 100` (README), nof1 25–30x; Vibe-Trading nakit için 1.0 | |
| MCP / SDK / çatı sınıfı | konu dışı (aşağıda kapsam) | |

Kısa olgu: bu taramada **işlem başı %1–2 aralığını varsayılan alan** repolar: astra (2%), erfaniaa (2%), bvedtrade (1%), pathiel (1%), bitbotby (1–2–4% ön ayar), 1l3a (1%), aswin/leadline (1%), rgg81 (rejime göre 0,5–1,5%). **%0,5 alanlar**: the-trader-bot, bitra, el-bach, islambaraka90, rgg81 yüksek-vol rejimi. **%5 ve üstü**: peri (5%, kullanıcı kararıyla yükseltilmiş), nikhilperr (5%), bitbotby saldırgan (4%). Kaldıraç varsayılan/tavan ailesi: 2–5x (astra, rgg81, erfaniaa, kb-90 `README.md:243` max 5), 3x (bvedtrade carry, 1l3a, pathiel, NFI), 10–30x (nof1 ailesi, peri 20x).

## 4. Madde 6: doğrulama (walk-forward, holdout, ön kayıt, DSR/PBO, kâğıt/testnet kapısı)

| Repo | Ne yapıyor (kod kanıtı) | Sayılar / eşikler |
|---|---|---|
| FilipeThome/the-trader-bot | Strateji başına otomatik canlıya terfi kapısı: 4 pencerede yürüyen ileri sınama, ≥3 pencere kârlı, "yürüyen verimlilik" (WFE) ≥0,5, son %20 kilit tutma, DSR ≥0,95 (önceki denemelerle indirgenmiş) (`bot/backtest/runner.py:28-34,72-85,695-702`); arayüz aynı eşiği gösterir (`ui/src/pages/Performance.tsx:10-11`) | `MIN_SHARPE 1.0`, `MAX_DRAWDOWN 0.20`, `MIN_TRADES 30`, `WF_WINDOWS 4`, `WF_MIN_PROFITABLE 3`, `MIN_WFE 0.5`, `HOLDOUT_SHARE 0.2`, `HOLDOUT_MIN_TRADES 5`, `MIN_DSR 0.95` |
| aplicy-com/guarded-trader | Kapı 1 (kâğıttan önce): ön kayıt (append-only deneme sicili, ilk backtest'ten önce), IS Sharpe ≥1,0 (günlük özsermaye eğrisi), iki şemada ≥8 OOS pencere ve havuz OOS Sharpe ≥ %50 IS, ≥100 işlem, ücret oranı <%40, tek işlem ≤%30 kâr, ≤6 parametre, rastgele-giriş sıfır modeli (200 koşu), DSR **raporlanır, kapı değil** (eşik TBD, öneri ≥0,80) (`services/research/src/research_harness/cli.py:39-43,289-296`; `docs/08-paper-exit-criteria.md:26-49`). Kapı 2 (kâğıt): ≥3 kesintisiz hafta **ve** ≥20 işlem ya da 8 hafta, hangisi önce; düşük işlem sayısı hata değil olgu (`docs/08-paper-exit-criteria.md:75-99`). Kapı 3 (%25→%100): TBD (`:122-130`) | `OOS_OVER_IS_FLOOR 0.5`, `MIN_TRADES_CANONICAL 100`, `FEE_RATIO_CEILING 0.40`, `SINGLE_TRADE_CEILING 0.30`, `MAX_PARAMS 6` |
| 0Smallcat0/trialgate | 9 kapı: (1) deneme sicili, (2) veri tabanı, (3) **PBO ≤0,05**, (4) **DSR ≥0,95**, (5) **tek kullanımlık holdout**, (6) canlı sapma bantları (canlıdan önce kilitli), (7) stop çizgisi dayanıklılığı, (8) bildirilen maliyetler, (9) maliyet stresi (maliyet iki kat, DSR yeniden) (`src/trialgate/gates.py:1-30`) | PBO ≤0,05, DSR ≥0,95 |
| rgg81/crypto-trade-claude-code | Kâğıttan canlıya mezuniyet: ≥20 denetlenmiş döngü, OOS Sharpe >0, DSR p ≥ eşik, alma-tutu net maliyetle yenmeli; 120 döngüde kazanç yoksa "failed" (`futures_fund/graduation.py:25-50`); canlı kapı varsayılan-ret, mezun olmadıkça `live_allowed False` (`futures_fund/live_gate.py:6-14`) | `min_cycles 20`, `horizon_cycles 120`, `DSR_THRESHOLD ≥0,95` (README:`:71`) |
| Bachhsunkid/agent-to-earn | LLM'in önerdiği strateji için kapı: örnek içi ≥40 işlem, PF ≥1,0, maxDD ≤0,30; örnek dışı ≥15 işlem, PF ≥1,1, kâr ≥0, maxDD ≤0,20; adayın OOS düşüşü canlıdan ≤+0,05 fazla; kaldıraç ≤10; terfi sonrası 14 gün soğuma (`agent/gate.py:70-90`; ADR-0008) | tablodaki sayılar |
| a_henryzhangpku_autonomous-quant-researcher | Hash zincirli ön kayıt defteri (`research/prereg/ledger.py:1-3`), aşamalar discovery / validation / holdout (`research/prereg/gpu_campaign.py:36,185`), kampanya 2 kampanya 1 geçmeden mühürlü (`:278`); backtest kapısı Sharpe 1,5 / DD 0,15 / isabet 0,55 / t 2,0 (`research/hmm/backtest.py:60`) | |
| rp7o/trade-foundry | Mühürlü holdout: değerlendirme başlayınca arama kalıcı kapanır; yürüyen pencere (`research/validation/README.md:178`; `research/trade-long/README.md:14`; `research/trade-long/AGENTS.md:46` "holdout verisine bakma") | |
| a_yellowpancake_quant-autoresearch | Kronolojik eğitim/doğrulama/son test ayrımı; son test ayrı dizinde, strateji dondurulduktan sonra bir kez (`README.md:50,65-68,87`) | |
| a_aithos-rr_ai-agent-for-trading | Ön kayıtlı çıkış ölçütleri C1–C9, 48 saatlik ön kayıtlı pencere (`README.md:101-106`); 4 haftayı 2+2'ye bölüp kararlılık (`docs/RESEARCH_DESIGN.md:378`) | |
| a_yllvar_quant-autoresearch | Hedef: ortalama yürüyen-ileri OOS Sharpe; "OOS Sharpe > 2,0" hedef (`src/prompts/program.md:6`; `src/core/engine.py:214`) | |
| ruiwang20010702/cryptobot | Yürüyen pencere: eğitim 60 gün, test 30 gün, adım 30 gün (`src/cryptobot/backtest/walk_forward.py:62-64`) | 60/30/30 |
| erfaniaa/LLM-Auto-Trader | CPCV (arındırma+ambargo, `src/backtest/cpcv.py:8-45`), PBO (`:107`), yürüyen-ileri (`src/backtest/walk_forward.py:1-3`) | |
| alex-jb/orallexa | CPCV (`engine/cpcv.py`, README_CN `:68`), yürüyen-ileri **FAIL** kaydı: ortalama OOS Sharpe −3,08 (2026-06-09) (`skills/prediction.py:175`) | |
| chrisleekr/binance-trading-bot | Zaman aralığının bir kısmı holdout (`packages/strategy/backtest/src/regime.ts:176-195`) | |
| NoFxAiOS/nofx | Optimizasyon betiği: holdout penceresi ayrılır (`scripts/optimize/search.py:4,72`) | |
| jerome-benoit/freqai-strategies | 21 gün eğitim, 2 gün test, **0,333 holdout**, yedek holdout 0,1 `train_test_split` (`quickadapter/README.md:95-98`) | |
| a_bhtbwh_ai-trader | Canlıda tepe düşüş sert tavanı %15 (`src/ai_trader/broker/live_guards.py:16`) | |
| danny123-sudo/regime-trading-bot | Kâğıt kapısı (README): ≥200 işlem, isabet >%60, maxDD <%20, Sharpe >1,0; şort ayrı iz (`README.md:166-170`); LLM vetosu backtestte yok (bkz. 3) | |
| mocasus/trade-agent | `paper_mode_required_first_run: true` (`config.example.yaml:203`) | |
| aswin-ram-k/algo-trading-bot | "30 gün pozitif canlı P&L'ye kadar PAPER olmalı" (`config_optimized.yaml:11`) | 30 gün |
| vedv0987-cloud/bvedtrade | Kâğıt-canlı geçiş kontrol listesi: "Önce kâğıtta kenarı kanıtla", bleed-fix sonrası koddan N gün (`LIVE_TRADING_CHECKLIST.md:39-75`); testnet/canlı çift kilit | |
| parkseokjune/overfit-slayer | Kendi DSR'ını bildirir: Sharpe 0,92, DSR 0,41–0,75 "seçim şansından ayırt edilemez"; 9 yıllık yürüyen-ileri (`README.md:11,52`; `STATE.md:66`) | |
| wyc-dev/MATS | Doğrulama modülü: Sharpe/Sortino/Calmar/PF/yürüyen-ileri/bootstrap/DSR (`src/edge/index.ts:15`; `src/edge/backtest-validation.ts:9,195-211,275`) | |
| HKUDS/Vibe-Trading | Yürüyen-ileri, Monte Carlo, bootstrap ve DSR doğrulama kipi (`agent/backtest/validation.py:6,243-246,373,416`) | |
| OpenByteInc/QuantDinger | Yürüyen-ileri + son kör test aralığı, bileşik puan, PBO, Deflated Sharpe, blok bootstrap Monte Carlo, maliyet stresi (**yalnız README**: `README_CN.md:154-155`) | |
| neillbotushanski/alphaforge | DSR + PBO + arındırılmış CV meta-model (**yalnız README**, kaynak yok: `README.md:25-27`) | |
| henryzhang vb. | `a_daviddtech_ai-trading-agent`: "overfitting detector" ajan şablonu (yalnız README/istem: `loop/10-overfitting-detector.md`) | |
| coding-kitties/investing-algorithm-framework (+cabbage kopyası) | Yürüyen-ileri pencere ayrıştırması (`investing_algorithm_framework/services/backtest_store/decompose.py:31`) | |
| freqtrade/freqtrade | `lookahead-analysis` ve `recursive-analysis` komutları + API uçları (`freqtrade/rpc/api_server/api_analysis.py:93-139`; `build_helpers/create_command_partials.py:62-63`); hyperopt; **canlı kapı yok** (dry-run kullanıcı kararı) | |
| nateemma/strategies | Yürüyen-ileri kıvrımları ile deney yargısı (`AGENT_GUIDE.md:20-34`) | |
| a_loveolu_crypto-strategy-research | Denetim notu: yürüyen-ileri Sharpe'ı `sqrt(365)` sabitiyle yanlış ölçekliyor (`research/AUDIT_2026-07-30_opus.md:52-73`); terfi ölçütü 3 aynı hata (`PROJECT_OPERATOR_MANUAL.md:748`) | |
| kb-90/okx-algotrade-agent-x | Yürüyen-ileri optimizasyon (README `:76`, yalnız README) | |
| a_imsatoshi_genetrader | GA + yürüyen-ileri doğrulayıcı sınıfı (`optimization/genetic_optimizer.py:7,26`) | |
| a_jgardet_evotrade (`c_jgardet_evotrade`) | Kronolojik holdout bayrağı `is_holdout` (`src/backtest/runner.py:45-56`) | |
| 0xsanei/darwinia | `validate -w 3 -g 20` yürüyen-ileri aşırı uyum kontrolü (`README.md:230,286`) | |
| rafaelpf07/evotrader | Arındırılmış yürüyen-ileri GB sinyali: AUC ≈0,51 "yazı-tura"; "al-tut'u yenmiyor" (`README.md:5-15`) | |
| maxwellcm92/darwinfi | Kâğıttan canlıya kapılı terfi (kod: `src/agent/evolution-engine.ts:37,136`) | |
| mahoraga, nightwatcher, mats gibi | Doğrulama/holdout kodu yok (sayım val=0) | |
| 1l3a-proje (sahibin) | Resmi **holdout kapısı**: `HOLDOUT_BAS = 2025-11-08`, bu tarih ve sonrası okunmaz; sızıntı `HoldoutSizintisi` sert hata (`motor/arastirma/v2/sabit.py:2,16`; testler `testler/test_v2_ham_eleme.py:224-259`); walk-forward `pencereler_uret`, seçim yalnız eğitimle, tek aday, kilit, deneme kaydı (`testler/test_wf_tarama.py:1`); panoda "doğrulandı" (holdout kapısı) ile "iyi göründü" (sonuç sonrası keşif, kanıt değil) ayrımı (`deploy/KURULUM.md:200`); canlıdan önce paper + testnet duman adımı (`DURUM.md:152`); "bilinmiyor" (<20 işlem) olan strateji canlıya en çok 60 $ deneme kasasıyla (`DURUM.md:144`); düşüş ölçütü min(max(1,5×geliştirme en kötü düşüşü, %5), %15) (`DURUM.md:140-142`) | |
| ct-proje (sahibin) | Walk-forward seçim doğrulaması yapıldı ve **kapatıldı**: "geçmişe bakarak seçim rastgeleden iyi değil" (`arastirma/dis_inceleme/dunya/RAPOR.md:29`; `DURUM.md:10`) | |
| qlib, finrl, fincon, tensortrade | tensortrade: `train_walkforward.py` örneği (`examples/training/train_walkforward.py:3`); finrl-meta optuna "out-of-sample" (`meta/env_market_impact/optuna_optimize.py:5`); qlib/finrl/fincon: doğrulama kapısı yok (araştırma çerçevesi) | |
| Tarama düzeyinde (kapı yok / belirsiz) | nof1 ailesi, nofx (backtest yok), ai-hedge-fund-crypto, hyper-alpha-arena, OpenAlice, LLM-trader, TradingAgents (val=0 ya da alakasız), polymarket/MCP/SDK repoları | |

Not (olgu): CANLI-K1'e benzer çok kapılı yapıyı (ön kayıt + DSR + PBO + tek-kullanımlık holdout + kâğıt kapısı) tek repoda bir arada koda koyan: trialgate (kapılar) ve guarded-trader (Kapı 1–2, DSR raporlanır ama kapı değil). Ön kayıt deneme sicili kodda olan: guarded-trader, henryzhangpku, trade-foundry, trialgate; 1l3a (sahibin) ON_KAYIT güncellemeleri ve deneme kaydı. Kimse "6 deneme" sınırı gibi sabit deneme bütçesi koymuyor; sınır sicilde sayma (DSR için N).

## 5. Bizim plan (özet olgular, çapraz karşılaştırma için)

- LLM rolü: yalnız veto, fail-closed; günlük 0,25 $ + aylık 10 $ tavan; tek model (haiku-5-5); çift başına belge. En yakın dış örnekler: regime-trading-bot (veto, fail-closed, backtestte yok) ve the-trader-bot (shadow/filter, günlük 1 $, `min_veto_confidence 0.6`, `require_verdict False`).
- Soğuma: yalnız `stop`/`trail_stop` çıkışlarından sonra aynı mumda giriş yasak; zaman tabanlı soğuma yok. Dış repolarda yaygın biçim: sembol başına 15–240 dakika, bir kısmı stop sonrası asimetrik (peri 1 s / 4 s, bvedtrade 5 dk / 30 dk, erfaniaa 30 dk × ardışık SL, nofx 4 s).
- Risk: %0,5 başlangıç, tavan %1,4 (kilit %2); kademe artışı onaylı ve kanıt kapılı; günlük %5, açık risk %6; kaldıraç 3–5x.
- Doğrulama: ön kayıtlı en çok 6 S2 denemesi, kilitli dönem, DSR ≥0,95 (N ≥ 10), kâğıt ≥4 hafta + testnet 14 gün.

## 6. Kapsam

Evren: `reports/Puanlama matrisi.md` (53 + 8 ikinci tur + puanlanmayanlar), tüm `reports/` ve `research_notes/` adları, sahibin `1l3a-proje` ve `ct-proje`. Yerel klon dizini: 247 repo (+ sahibin 2 projesi). Bu turda yeniden klonlananlar: TauricResearch/TradingAgents, qrak/LLM_trader, imsatoshi/GeneTrader, 51bitquant/binance_grid_trader (aynı içerik `x_` ön ekiyle zaten vardı; kopyalar silindi), Superalgos, vnpy (yeni).

Okuma düzeyi: **E** = elle okundu (kod satırı ve sayı doğrulandı), **T** = otomatik regex taraması ve satır örnekleri okundu, **K** = konu dışı / ilgili kural bulunmadı, **R** = klonlanamadı/zararlı-kopya (önceki tur notu).


| Repo | Düzey | Sayımlar (llm/veto/maliyet/soğuma/risk/doğrulama regex eşleşmesi) |
|---|---|---|
| a_aenger-priv_contextualbandits | T/K | 0/0/0/0/0/23 |
| a_affaan-m_dprc-autotrader-v2 | T | 407/0/33/10/2/0 |
| a_ai-brokers_aibrokers | T/K | 16/0/0/0/2/0 |
| a_ai4finance-foundation_elegantrl | T/K | 59/0/0/8/14/4 |
| a_ai4finance-foundation_finrl-meta | T | 16/6/0/58/21/68 |
| a_aifore_coinx | T | 1/1/0/9/0/8 |
| a_aithos-rr_ai-agent-for-trading | E | 627/56/52/6/48/22 |
| a_aksaayyy_ai-bot-earn-or-die | T/K | 0/0/0/0/0/0 |
| a_alaika-cyber_pumpfun | T/K | 10/3/0/2/7/0 |
| a_alexandrelamure_auto-trade | T | 54/0/5/0/29/0 |
| a_aminhp_gym-anytrading | T/K | 1/0/0/0/0/0 |
| a_aristidesai_ibkr-aihedge | T | 15/0/0/0/5/0 |
| a_azmax7434_trading-view | T/K | 1/0/0/0/0/0 |
| a_benpomme_agentictrading | T | 130/104/119/51/4195/7678 |
| a_bhtbwh_ai-trader | T | 111/4/15/0/47/1 |
| a_bijectivelabs_bitra | E | 216/14/74/49/259/103 |
| a_captainnahin_trading-bot | T | 127/28/33/6/3/8 |
| a_codeptor_peri | E | 70/497/64/514/330/44 |
| a_daviddtech_ai-trading-agent | T | 27/1/0/19/69/99 |
| a_dax-523_ai-trading-agent | T/K | 6/0/0/0/0/0 |
| a_deuteriumzzz_bitbotby | E | 486/3/32/179/270/165 |
| a_dexoryn-china_polymarket-arbitrage-bot | T/K | 77/1/44/52/127/13 |
| a_dexorynlabs_polymarket-ai-agent-trading-bot | T/K | 71/1/44/52/124/13 |
| a_dieumerci8_freqtrade-strategy-builder | T | 5/0/0/0/4/37 |
| a_dogstailfarmer_martin-binance | T/K | 0/0/0/0/2/0 |
| a_dontbesideline_open-nof1-alphaarena | T/K | 22/0/0/0/22/0 |
| a_drakkar-software_octobot-ai | T | 12/14/0/0/1/11 |
| a_dvampire_finagent | T | 118/5/7/0/1/1 |
| a_el-bach_claude-trader | E | 362/1/19/16/102/0 |
| a_etrobot_open-alpha-arena | T/K | 11/0/3/0/15/6 |
| a_eugmsub_robinhoodagentictrader | T | 44/2/4/0/11/4 |
| a_flukelaster_ai-trading-agent | T | 136/0/5/85/146/269 |
| a_furkankoykiran_freqtrade-mcp | T/K | 7/0/0/0/13/0 |
| a_gaaiyun_freqtrade-strategy-generator | T/K | 59/0/1/0/0/0 |
| a_gacord1213-arch_alpaca-ai-trading-agent | T | 60/2/1/0/3/1 |
| a_gajesh2007_ai-trading-agent | T | 3/1/1/3/1/1 |
| a_gotji253_ai_trading_ada | T/K | 11/0/2/62/65/17 |
| a_guixu-project_guixu | T/K | 196/2/4/0/0/12 |
| a_henryzhangpku_autonomous-quant-researcher | E | 50/4/17/28/33/572 |
| a_hsliuping_tradingagents-cn | T/K | 1913/100/343/27/100/41 |
| a_hypurrquant_perp-cli | T | 66/28/1/701/104/42 |
| a_inapp-mobile_clodds | T | 749/144/69/397/522/80 |
| a_janitoff0_ninjatrader-bot | T/K | 0/0/0/0/1/0 |
| a_julian-dev28_pathiel | E | 434/129/59/114/833/230 |
| a_kaoi-cyber_ai-trader | T | 46/0/6/9/10/0 |
| a_kevinmyding_tradinggpt | T | 22/9/3/0/9/67 |
| a_kojott_llm-trader-test | T | 45/0/21/2/17/2 |
| a_kukapay_awesome-alpha-arena | T/K | 24/0/0/0/0/0 |
| a_kylinmountain_tradingagents-ashare | T | 189/7/6/0/23/0 |
| a_llmquant_awesome-trading-agents | T/K | 40/4/0/0/2/1 |
| a_loveolu_crypto-strategy-research | T | 35/276/0/65/908/2279 |
| a_ma-pony_cryptotrader-ai | T | 603/142/78/100/87/131 |
| a_mad1kow-cloud_crypto-intelligence-agent | T | 42/1/2/0/1/0 |
| a_maotouhu_nof1openai | T/K | 13/0/1/0/0/0 |
| a_marigold_universal-portfolios | T | 0/1/0/2/52/13 |
| a_masaichig0_tradinggpt | T/K | 59/0/0/0/0/0 |
| a_mikegianfelice_hunter | T | 0/1/25/261/80/39 |
| a_milady-ai_plugin-bsc-memes | T/K | 0/1/0/0/0/0 |
| a_millw14_merrymen | E | 1335/662/110/1208/294/476 |
| a_mocasus_trade-agent | E | 16/0/8/13/35/0 |
| a_mogons_noraz-agent | T | 73/21/5/16/3/33 |
| a_muzafferkadir_claude-crypto-trader-public | T | 29/0/0/0/0/2 |
| a_neryaai_nerya | T | 1016/399/234/168/278/781 |
| a_nirholas_binance-mcp | T/K | 46/7/0/0/2/6 |
| a_oficcejo_alpha-arena-okx | T | 36/0/0/0/0/0 |
| a_okay-bet_plugin-polymarket | T/K | 7/2/0/0/0/1 |
| a_okay456okay_nof1.ai.monitor | T/K | 12/0/0/0/0/0 |
| a_okx_agent-trade-kit | T/K | 185/8/0/0/0/9 |
| a_olaxbt_ai-market-maker | T | 138/217/89/30/138/72 |
| a_oyi77_1ai-skills | T/K | 1089/182/41/110/90/174 |
| a_p20090504-dotcom_qs-bot | T/K | 6/0/0/0/0/0 |
| a_pellenybe_crypto-mcp-server---by-corax-colab | T/K | 90/10/10/7/4/12 |
| a_pettekay_ai-forex-trading-bot | T | 83/79/16/26/81/41 |
| a_phichleng_tradinggpt | T/K | 10/1/3/0/17/3 |
| a_pi-2r_quant-science | T/K | 0/0/0/0/0/0 |
| a_polymarket_agents | T/K | 23/0/0/0/0/0 |
| a_pranavjadhav1363_plugin-ccxt | T/K | 0/0/0/0/0/0 |
| a_qingshungli_super-nof1.ai | E | 61/0/0/0/16/2 |
| a_raphael2025_perp-recap | T/K | 0/0/0/0/0/0 |
| a_remiotore_ccxt-freqtrade | T/K | 0/0/0/1904/3888/78 |
| a_roboticautomations_freqtradestrategies | T/K | 189/1/22/1938/3221/1904 |
| a_rp7o_trade-foundry | E | 0/7/0/3/13/232 |
| a_sak-114514_freqtrade-agent | E | 30/0/26/0/9/0 |
| a_samsoncukor06_agentic-trader | T | 7/1/0/28/1/0 |
| a_satyamdas03_alpaca-trading-agent | T | 505/19/20/10/138/167 |
| a_sc0vu_freqlint | T/K | 10/1/0/0/19/0 |
| a_scodive_alpha-arena-prompt | T/K | 6/0/0/0/0/0 |
| a_shiyu-coder_kronos | T/K | 1/0/0/0/5/0 |
| a_snowingfox_open-nof1.ai | E | 50/0/0/0/0/0 |
| a_superior-trade_superior-skills | T/K | 16/4/0/0/53/31 |
| a_syh52_ft-analyzer | T | 43/0/1/83/537/164 |
| a_teraus111_web3-agent-kit-solana-trading | T/K | 79/1/9/69/16/11 |
| a_terryso_nof1-tracker | T/K | 107/0/0/0/4/1 |
| a_thefourgreaterrors_alpha-rptr | T/K | 0/0/0/0/23/8 |
| a_tiramisuice_ai-trader | T | 118/0/25/0/35/0 |
| a_ulab-uiuc_live-trade-bench | T/K | 63/1/2/0/0/3 |
| a_valory-xyz_trader | T | 20/16/1/50/58/10 |
| a_vnavanee_cryptotrader-llm | T/K | 0/0/0/0/0/0 |
| a_web3spreads_quant-flow | T | 18/0/6/27/48/0 |
| a_yalcin_freqtrade-mcp | T/K | 22/0/0/0/4/0 |
| a_yellowpancake_quant-autoresearch | T | 0/0/0/3/312/45 |
| a_yi-111-a_alphaloop-crypto | T | 113/10/41/20/120/125 |
| a_yllvar_quant-autoresearch | T | 6/0/10/0/21/23 |
| a_zeframlou_bagholder | T/K | 0/0/0/0/0/0 |
| a_zetryn-ai_ai-agent | T/K | 1804/623/0/235/6/5 |
| a_zhangjinhahaha_agentlens | T/K | 172/7/6/2/0/0 |
| a_zhulinsen_daily_stock_analysis | T/K | 1998/103/113/399/55/50 |
| c_0smallcat0_trialgate | E | 1/0/0/0/13/290 |
| c_0xethanq_astra-quant-agent | E | 268/45/9/168/247/33 |
| c_195440_nof1.ai | E | 170/3/88/14/123/5 |
| c_6kmfi6hp_ft-userdata-llm-share | T | 39/0/17/0/66/0 |
| c_7thdrag0n_autoevolve | T | 62/1/20/45/22/17 |
| c_adamcyh_evotrader | T | 429/24/0/81/91/54 |
| c_ai4finance-foundation_finrl-trading | T | 37/1/1/90/21/67 |
| c_ai4finance-foundation_finrl | T/K | 8/0/0/7/1/2 |
| c_ai4finance-foundation_finrobot | T | 334/58/9/66/22/171 |
| c_aleksnovo_freqai-3ai-strategy | T | 0/0/0/83/32/57 |
| c_alex-jb_orallexa-ai-trading-agent | E | 595/10/130/41/303/580 |
| c_alpacahq_alpaca-mcp-server | T/K | 15/0/0/0/0/1 |
| c_alsk1992_cloddsbot | E | 771/145/70/397/523/80 |
| c_ampyfin_ampyfin | T/K | 0/0/1/0/4/11 |
| c_aplicy-com_guarded-trader | E | 105/41/0/58/185/508 |
| c_aria-tjr_llm-crypto-hyperopt | T | 26/3/11/2/217/7 |
| c_asavinov_intelligent-trading-bot | T/K | 0/0/0/0/0/5 |
| c_bachhsunkid_agent-to-earn | E | 17/1/0/17/42/96 |
| c_backtest-kit_backtest-ollama-crontab | T/K | 51/52/0/0/0/0 |
| c_caiovicentino_polymarket-mcp-server | T/K | 320/4/14/0/7/0 |
| c_chase-mew_ai-hedge-fund | E | 96/0/21/7/22/3 |
| c_chrisleekr_binance-trading-bot | T | 246/946/21/325/20/241 |
| c_chrisworsey55_atlas-gic | T/K | 22/0/2/0/3/0 |
| c_coding-kitties_investing-algorithm-framework | T | 3/237/0/625/287/442 |
| c_cyberwei922_ai-trader-paper | T | 2/1/0/8/8/1 |
| c_danderson197874_apex-crypto-bot | T | 0/0/0/2/2/2 |
| c_danny123-sudo_regime-trading-bot | E | 4/21/0/16/29/9 |
| c_dasein108_freqtrade_dev_mcp | T | 80/0/11/0/84/17 |
| c_drakkar-software_octobot | T | 284/6/126/26/21/185 |
| c_enarjord_passivbot | E | 109/24/222/1520/75/236 |
| c_erfaniaa_llm-auto-trader | E | 199/94/33/53/471/954 |
| c_filipethome_the-trader-bot | E | 95/326/19/56/201/175 |
| c_finstep-ai_contesttrade | T/K | 126/3/47/0/0/0 |
| c_freqtrade_freqtrade | E | 23/0/0/69/544/199 |
| c_galleonlabs_hypergrok-trading-desk | T | 161/8/0/0/32/146 |
| c_giansn_sygnif | T | 576/67/21/159/156/114 |
| c_hammergpt_hyper-alpha-arena | T | 479/13/64/44/312/19 |
| c_hkuds_ai-trader | T | 9/1/0/55/129/9 |
| c_hkuds_vibe-trading | E | 1307/180/74/123/237/972 |
| c_hummingbot_hummingbot | E | 154/38/7/91/52/27 |
| c_iterativv_nostalgiaforinfinity | T | 14/1/0/200/2125/28 |
| c_jackson-video-resources_claude-tradingview-mcp-trading | T/K | 48/0/0/0/0/2 |
| c_je-suis-tm_quant-trading | T/K | 0/0/0/0/0/39 |
| c_jerome-benoit_freqai-strategies | T | 0/1/0/100/32/282 |
| c_jesse-ai_jesse | T/K | 21/95/0/17/138/890 |
| c_jgardet_evotrade | T | 46/0/17/8/31/147 |
| c_kb-90_okx-algotrade-agent-x | E | 0/0/0/3/54/13 |
| c_kyky2347_alta | T/K | 3452/107/529/160/11/364 |
| c_lnstt369_nightwatcher-v2 | T | 131/5/36/31/119/0 |
| c_lumiwealth_lumibot | T | 1041/28/27/105/102/335 |
| c_maxwellcm92_darwinfi | T | 276/4/5/30/3/104 |
| c_microsoft_qlib | T/K | 0/0/0/4/27/8 |
| c_microsoft_rd-agent | T/K | 165/8/51/2/12/95 |
| c_mingyuj666_stockagent | T/K | 42/1/0/0/0/0 |
| c_nateemma_strategies | T | 52/363/0/41/10208/2588 |
| c_nautechsystems_nautilus_trader | T/K | 57/68/380/585/183/1183 |
| c_nikhilperr_binance-futures-trading-bot | T | 0/0/0/6/33/0 |
| c_nofxaios_nofx | E | 695/65/53/23/177/17 |
| c_oficcejo_okx-2pa-agent-web | T | 117/6/17/49/41/0 |
| c_oft3r_agentic-trading-desk | T/K | 26/3/0/8/0/0 |
| c_open-finance-lab_agentictrading | T | 2368/172/150/179/461/423 |
| c_openbyteinc_quantdinger | T | 217/50/58/96/275/306 |
| c_parkseokjune_overfit-slayer | E | 26/0/1/0/5/131 |
| c_pipiku915_finmem-llm-stocktrading | T | 41/1/6/0/7/0 |
| c_pulseprotocolorg-cyber_pulse-freqtrade | T/K | 12/0/0/0/8/0 |
| c_quant-science_sunday-quant-scientist | T/K | 0/0/0/0/10/2 |
| c_rafaelpf07_evotrader | T | 1/1/0/0/95/217 |
| c_rgg81_crypto-trade-claude-code | E | 40/266/0/1/118/272 |
| c_richkuo_go-trader | T | 359/199/16/394/84987/16974 |
| c_ruiwang20010702_cryptobot | E | 99/21/6/41/206/145 |
| c_ryanfrigo_kalshi-ai-trading-bot | E | 137/15/47/18/251/49 |
| c_senpi-ai_senpi-skills | T | 18/184/77/1345/1477/32 |
| c_shoaibghulam_binance-ai-bot | T | 27/36/0/13/43/53 |
| c_solohard32_mexc-ai-bot | T | 1/226/8/170/31/31 |
| c_sorry510_go_binance_futures | T | 177/103/26/313/159/73 |
| c_superalgos_superalgos | T/K | 0/177/0/6/23/197 |
| c_superior-trade_trading-terminal | T/K | 28/64/1/0/55/49 |
| c_suyunjing-su_r20-quantum-trader | E | 204/59/60/128/255/19 |
| c_tensortrade-org_tensortrade | T/K | 7/0/0/12/0/118 |
| c_the-finai_fincon | T/K | 0/1/0/0/0/0 |
| c_the-swarm-corporation_autohedge | T/K | 20/0/0/0/0/0 |
| c_torchtrade_torchtrade | T | 48/0/17/0/125/31 |
| c_traderalice_openalice | T/K | 2476/58/7/110/14/519 |
| c_tradermonty_claude-trading-skills | T/K | 1488/262/0/127/633/233 |
| c_vedv0987-cloud_bvedtrade | E | 95/59/10/141/302/252 |
| c_virattt_ai-hedge-fund | E | 82/3/4/0/127/20 |
| c_vnpy_vnpy | T/K | 1/0/0/3/19/1 |
| c_wquguru_nof0 | E | 1920/3/33/128/78/7 |
| c_wyc-dev_mats | T | 272/250/9/351/126/263 |
| c_ygwyg_mahoraga | E | 377/21/18/48/65/0 |
| c_yizhisong_friestrader | T | 11/0/0/20/9/0 |
| c_ymcbzrgn_hydraquant | E | 718/122/89/200/1391/519 |
| t_llmtrader | E | 322/21/112/56/52/20 |
| x_00hsynclk_crypto-trading-bot | T/K | 0/2/2/16/132/15 |
| x_0xemmkty_quantmuse | T/K | 162/1/13/0/53/9 |
| x_0xmerl99_agent-world-protocol | T/K | 1/3/0/2/0/0 |
| x_0xsanei_darwinia | T/K | 11/0/0/0/45/102 |
| x_51bitquant_ai-hedge-fund-crypto | T/K | 61/1/0/3/21/0 |
| x_51bitquant_binance_grid_trader | T/K | 0/0/0/0/0/0 |
| x_Dahshan228_FTMO-TradingBot | E | 4/2/20/116/580/581 |
| x_TauricResearch_TradingAgents | E | 438/4/20/0/21/1 |
| x_aswin-ram-k_algo-trading-bot | T/K | 0/0/0/0/49/9 |
| x_ayrtondavoli97_neural_trader_v7 | T/K | 0/0/0/0/0/2 |
| x_baran0732_ai-crypto-trader-pro | T/K | 0/0/0/0/0/0 |
| x_bederf_leah-freqtrade-strategies | T/K | 0/0/0/2/4/13 |
| x_boredom198_thesis-ai-trading-agent | T/K | 50/2/0/0/22/1 |
| x_conjason_binance-alpha-miner | T/K | 58/1/4/8/49/71 |
| x_dietmarwo_autoresearch-trading | T/K | 126/0/3/29/14/178 |
| x_dukesan-ai_crypto-ml-trading-framework | T/K | 0/1/0/2/1/195 |
| x_dukesky_allpath-trading-agent | T/K | 245/89/76/34/31/30 |
| x_garagesteve1155_PowerTrader_AI | T/K | 0/5/0/5/0/0 |
| x_gone2707_btc-trading-bot | T/K | 0/11/0/0/0/0 |
| x_imsatoshi_genetrader | T/K | 0/0/0/0/30/137 |
| x_ishieldi_alphaswarm | T/K | 46/2/4/0/0/14 |
| x_islambaraka90_super-agent-trading-bot | T/K | 112/6/10/8/15/3 |
| x_kairospan_gravit-agent | T/K | 1218/53/10/84/17/82 |
| x_krakenfx_kraken-cli | T/K | 76/20/0/2/41/139 |
| x_leadline88_binance-ai-trader | T/K | 0/0/0/0/25/11 |
| x_maazullah8_ai_self_improving_bot | T/K | 41/0/1/19/46/176 |
| x_markdregan_freqai-marcos-lopez-de-prado | T/K | 9/0/0/109/538/49 |
| x_markfans_cryptoquant-ai | T/K | 1/7/0/20/12/71 |
| x_max007-coder_quantbot | T/K | 0/12/0/18/12/2 |
| x_michi883_trade-cast | T/K | 64/0/0/0/0/4 |
| x_mnemox-ai_tradememory-protocol | T | 330/63/19/102/1571/902 |
| x_mohamed-sm_freqtrade-rlstrategy-ia | T/K | 0/0/0/0/0/0 |
| x_moss-site_moss-trade-bot-skills | T/K | 6/13/42/90/497/41 |
| x_neillbotushanski_alphaforge | T/K | 0/0/0/0/0/13 |
| x_nofiix_openclaw-workspace | T/K | 294/8/29/55/183/275 |
| x_qrak_LLM_trader | E | 322/21/112/56/52/20 |
| x_quantiaai_helm-agents | T/K | 205/4/2/0/3/23 |
| x_ricardokarma_claude-trading-bot | T/K | 65/0/2/0/3/0 |
| x_roclee2692_autonomous-spot-trading-agent | T/K | 0/20/0/0/28/1 |
| x_ryan-yuuu_crypto-trading-arena | T/K | 77/0/0/0/0/51 |
| x_sendaifun_solana-agent-kit | T/K | 1416/7/0/0/17/0 |
| x_snowcheetos_automoonbot | T/K | 0/0/0/0/0/0 |
| x_sonirico_go-hyperliquid | T/K | 3/10/0/0/0/2 |
| x_sopersone_cabbage-trading-machine | T/K | 3/164/0/587/272/442 |
| x_vishalsaraswat047_apha-tb | T/K | 30/0/1/33/18/8 |
| x_xtra-computing_cryptotrade | T/K | 146/649/2/19/91/448 |
| x_zhivko_ai-trading-bot-3 | T/K | 0/0/0/0/6/0 |

Sahibin projeleri: 1l3a-proje (E; risk/holdout/koç kodu okundu), ct-proje (E; risk limitleri ve walk-forward raporu okundu, LLM yok).

Klonlanamadı / yerelde yok (R, önceki tur notu: kopya, zararlı CI, spam ya da silinmiş): Eltano1985/tradememory-protocol, fsinbad/nofx, gale-crypto/nofx, caelum0x/hyperliqbot, Infinite Bagholder (rickyispresent), rmbell09-lang/tradesight, zhou343/stock-trader-ai, thom899g/autonomous-cross-asset, Shelpid/SETS, wolfinch, squidKid-deluxe/QTradeX, zero-was-here/tradingbot, ccxt/ccxt (kütüphane), djienne ve msei99 passivbot çatalları, chase-manning/ai-hedge-fund, hmt1501/finmem, netanelshoshan/freqai-lstm, sleeyax/ml-crypto-trading-bot, khovala/moex-ml-trading, misolove/gsuda-engine, mooresi/forex-gold, apex-prim/strategy-audit, rayanbatada/autonomous-equity-trading-system, masterputra169/polymarket-btc-15-minutes, thanh-van-2001 quant AI agent. Bu repolar için bulgu üretilmedi; önceki tur notları geçerlidir.

Atlanan: yok. Sınır: T düzeyindeki repolarda (çoğunluk) yalnız regex satırları okundu; E dışındaki tablolardaki satırlar tarama kanıtıdır, tam okuma değildir. 'T/K' = taramada anlamlı kural çıkmadı ya da repo konu dışı (MCP/SDK, çerçeve, spam, akademik).
