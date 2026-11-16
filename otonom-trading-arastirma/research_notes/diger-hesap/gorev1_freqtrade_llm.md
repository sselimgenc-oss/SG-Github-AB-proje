# Görev 1 — freqtrade üstüne LLM karar katmanı / "kendi işlemlerinden öğrenme" katmanı

Tarih: 15 Kasım 2026 · Yöntem: GitHub arama (`gh api search/repositories`, ~20 sorgu) + aday repoların `git clone --depth 1` ile geçici klasöre indirilip **yalnızca grep/okuma** ile incelenmesi. Hiçbir şey kurulmadı, çalıştırılmadı.
Yıldız/commit/lisans verileri 15.11.2026'da GitHub API'den alındı. "Son commit" = klonlanan HEAD'in tarihi (API'nin `pushed_at` değeri bazı repolarda daha yeni olabilir).

## 0. Kısa özet

- freqtrade'in **resmî bir LLM entegrasyonu yok**. Issue [#10798](https://github.com/freqtrade/freqtrade/issues/10798) ("LLM's, Freqtrade with Large Language Models") 16.10.2024'te "not planned" kapatıldı; bakımcılar bunu kullanıcının kendi stratejisinde yapabileceğini söyledi, token maliyetinin kâr öncesi karşılanması gerektiğine ve LLM'lerin "trading kararı anlayan ML aracı" olmadığına, bunun için FreqAI benzeri yöntemlere bakılması gerektiğine dikkat çekti.
- Bulunan projelerin hepsi küçük (≤ 21 yıldız), tek kişilik ve çoğu 2026 içinde açılmış. **Olgun bir "standart" yok**; ama tasarım desenleri net ayrışıyor:
  1. **LLM → `signal.json` → strateji dosyayı okur** (cryptobot),
  2. **LLM `confirm_trade_entry` içinde veto verir** (regime-trading-bot),
  3. **LLM strateji kodunu yeniden yazar** (AutoEvolve, agent-to-earn, evotrade) — (b) için en yakın ama en riskli desen,
  4. **LLM veriyi yorumlar, parametre/kural verir, kod değil** (regime-trading-bot "council", cryptobot "strategy advisor").
- (b) maddesi ("önce dry-run'da test et, sonra uygula") için **hiçbir repo bunu tam olarak yapmıyor**. En yakınları: agent-to-earn (geri tutulmuş dönem backtest kapısı + terfi sonrası bekleme süresi) ve regime-trading-bot (backtest kapısı + 72 saat/20 işlem otomatik geri alma). Gerçek "dry-run forward test → canlıya terfi" döngüsü **hazır parça olarak yok; yazılması gerekiyor** (bkz. §5).

## 1. Ana tablo

Sütun "Canlı karara giriyor mu?": ✅ = kodda dosya:satır ile görüldü; ⚠️ = kısmen/koşullu; ❌ = yalnızca README iddiası ya da canlı yola bağlı değil.

| # | Repo | ★ | Son commit | Lisans | Ne yapıyor | Canlı karara giriyor mu? | Rol |
|---|---|---|---|---|---|---|---|
| 1 | [danny123-sudo/regime-trading-bot](https://github.com/danny123-sudo/regime-trading-bot) | 0 | 2026-10-21 | MIT | Rejim sınıflandırıcı + Grok (xAI) **veto** katmanı + sınırlı "council" ile parametre (lever) güncelleme | ✅ `user_data/strategies/RegimeComposite.py:268-292` `confirm_trade_entry` → `core/strategy_state.py:139-178` `confirm_entry` (LLM `buy`+güven ≥ eşik değilse `False`) | (a) + (b) |
| 2 | [Bachhsunkid/agent-to-earn](https://github.com/Bachhsunkid/agent-to-earn) | 0 | 2026-11-13 | MIT | Gece Claude Code döngüsü yeni strateji **adayı** yazar; deterministik `gate.py` geri tutulmuş dönemde (OOS backtest) kıyaslar, geçerse `live/`'a taşır ve `reload_config` çağırır | ✅ `agent/gate.py:295-318` (`promote`, `reload_bot`); risk (kaldıraç/stake/stop) `guarded_strategy.py`'de sabit | (b) |
| 3 | [7thDrag0n/AutoEvolve](https://github.com/7thDrag0n/AutoEvolve) | 11 | 2026-03-20 | GPL-3.0 | SQLite'tan metrik izler → LLM (Anthropic/OpenAI/OpenRouter/Ollama…) strateji dosyasını yeniden yazar → hot-reload → kötüleşirse geri alır | ✅ `autoevolve/orchestrator.py:554-600` (`_do_evolve`), `deployer.py:977-1003` (dosyayı yazar + `/reload_config`) | (b) (agresif) |
| 4 | [ruiwang20010702/cryptobot](https://github.com/ruiwang20010702/cryptobot) | 21 | 2026-02-25 | AGPL-3.0 | LangGraph çok-rollü LLM iş akışı (DeepSeek vb.), 16 veri kaynağı (funding/OI/haber/F&G…), sinyali `signal.json`'a yazar; freqtrade okur. "Strategy advisor" geçmiş performanstan kural üretip prompt'a enjekte eder | ✅ sinyal: `freqtrade_strategies/AgentSignalStrategy.py:126-150` (`populate_entry_trend`), `custom_exit:319`, `custom_stake_amount:424`. Öğrenme: `src/cryptobot/evolution/strategy_advisor.py:80-95` (kurallar trader/risk prompt'una ekleniyor) | (a) + (b) |
| 5 | [ymcbzrgn/HydraQuant](https://github.com/ymcbzrgn/HydraQuant) | 10 | 2026-05-31 | GPL-3.0 | freqtrade **fork'u** + `HydraSizer` stratejisi; yerel RAG/LLM servisi (`/signal/{pair}`), çoklu LLM sağlayıcı yönlendirici, kapanan işlemle "öğrenen" parametre sistemi | ⚠️ ✅ LLM servisi çağrısı `user_data/strategies/HydraSizer.py:1192-1215`, stake modülasyonu `:2746`, `custom_exit:4317`. Öğrenme iddiaları (BCM/STDP/"organism") çok geniş; hepsini doğrulamadım | (a) + (b), dev ve karmaşık |
| 6 | [6Kmfi6HP/ft-userdata-llm-share](https://github.com/6Kmfi6HP/ft-userdata-llm-share) | 3 | 2025-11-16 | MIT | OpenAI-uyumlu function-calling ile LLM giriş/çıkış kararı; JSONL işlem günlüğü + `SelfReflectionEngine` | ✅ LLM çağrısı `LLMFunctionStrategy.py:546` ve `:729` (`populate_entry_trend/exit_trend`). Yansıtma motoru bağlanmış (`:99`, `:138`); çıktısının tam olarak nereye aktığını satır satır izlemedim | (a) + (b), bayat (1 yıl) |
| 7 | [Giansn/SYGNIF](https://github.com/Giansn/SYGNIF) | 1 | 2026-05-13 | yok | Bybit demo'da çok servisli sistem; freqtrade "legacy yürütme". `SygnifStrategy` içinde Claude Haiku haber duyarlılığı → giriş etiketi `claude_s*` | ✅ `user_data/strategies/SygnifStrategy.py:1219-1231` (LLM skoru TA skoruna eklenip `enter_long=1`) | (a), dağınık/kişisel |
| 8 | [jgardet/evotrade](https://github.com/jgardet/evotrade) | 1 | 2026-03-23 | NOASSERTION | LLM ile freqtrade stratejisi üret → backtest → skorla → Postgres kayıt; Bayesçi hipotez motoru | ❌ canlı işlem yolu yok; yalnızca araştırma boru hattı | (b)-araştırma tarafı |
| 9 | [aplicy-com/guarded-trader](https://github.com/aplicy-com/guarded-trader) | 2 | 2026-11-14 | Apache-2.0 | "LLM araştırır, asla işlem yapmaz": freqtrade emir verir, ayrı "Conductor" servisi risk/kill-switch tutar; walk-forward, rastgele-giriş null testi, Deflated Sharpe, deneme sicili | ❌ (tasarım gereği) LLM emir yoluna girmez (README, ADR-0003). Mimari referans olarak değerli | (b) güvenlik tasarımı |
| 10 | [dasein108/freqtrade_dev_mcp](https://github.com/dasein108/freqtrade_dev_mcp) | 10 | 2026-09-23 | MIT | MCP sunucusu: veri indirme, backtest, hyperopt, sonuç analizi araçlarını Claude'a açar + LangGraph ajanı | ❌ canlı yol yok; strateji geliştirme yardımcısı | (b) araç katmanı |
| 11 | [pulseprotocolorg-cyber/pulse-freqtrade](https://github.com/pulseprotocolorg-cyber/pulse-freqtrade) | 2 | 2026-03-13 | yok | REST adaptörü (`forcebuy` vb.) + bellek içi `PulseSignalBus` | ⚠️ Kodda **hiçbir LLM çağrısı yok** (anthropic/openai grep'i boş). "Claude'u 5 satırda bağla" yazısı dev.to tanıtımı; LLM tarafını kullanıcı yazıyor | zayıf / tanıtım ağırlıklı |

Elediklerim / yalnızca not:
- [aria-tjr/llm-crypto-hyperopt](https://github.com/aria-tjr/llm-crypto-hyperopt) (0★, MIT): README'de freqtrade geçse de Bybit'e doğrudan bağlanan kendi botu; freqtrade tabanlı değil → kapsam dışı.
- [backtest-kit/backtest-ollama-crontab](https://github.com/backtest-kit/backtest-ollama-crontab): TypeScript/`backtest-kit`, freqtrade değil → elendi.
- `Sak-114514/freqtrade-agent`, `syh52/ft-analyzer`, `gaaiyun/freqtrade-strategy-generator`, `dieumerci8/freqtrade-strategy-builder`, `sc0Vu/freqlint`, `furkankoykiran/freqtrade-mcp`, `yalcin/freqtrade-mcp`: sohbet/analiz/strateji-yazma yardımcıları (0–18★). Kod yazımına yardım ediyor, canlı karar yolu yok; klonlayıp ayrıntı incelemedim (sadece açıklamalarına baktım, `Sak-114514/freqtrade-agent` ve `syh52/ft-analyzer`'ı indirdim ama derinlemesine okumadım).
- `PelleNybe/Crypto-MCP-Server---by-Corax-CoLAB`, `ymcbzrgn`'in dışındaki "AI hedge fund / swarm" tarzı pazarlama ağırlıklı repolar, `ai-deepseek-trading-bot.github.io` (kendi bildirdiği performans tablosu, freqtrade değil), Medium "Top 10 AI crypto repos" listeleri: spam/pazarlama niteliğinde veya freqtrade dışı → elendi.
- Freqtrade dışı ama **tasarım referansı**: [qrak/LLM_trader](https://github.com/qrak/LLM_trader) (N kapanan işlemde bir "yansıtma" ile LLM kural yazıyor; arama özetinden öğrendim, **klonlamadım, doğrulamadım**), [Superior-Trade trading-terminal](https://skillsllm.com/skill/trading-terminal) (Claude Code skill'i, freqtrade stratejisi üretir; **incelenmedi**). Akademik: [CryptoTrade (EMNLP 2024)](https://aclanthology.org/2024.emnlp-main.63/).
- Aşırı yeni (< 1 ay) ve 0–2★ olan `Bachhsunkid/agent-to-earn`, `aplicy-com/guarded-trader` kopya/spam değil, kodu ve ADR'leri gerçek; ama henüz **kanıtlanmış getiri yok** (her ikisinin README'si de bunu açıkça yazıyor).

Uyarı: Bu repoların hiçbirinde kanıtlanmış kârlı bir edge yok. regime-trading-bot README'si "stratejinin gösterilmiş bir edge'i yok, para koymayın" diyor; guarded-trader da kendi stratejilerinin zarar ettiğini yayımlıyor. Yıldız sayıları düşük; bunları "hazır ürün" değil "parça/örnek" olarak okumak gerekir.

## 2. Her repo için detay ve güvenlik notları

### 2.1 regime-trading-bot — (a) için en temiz örnek
- Akış: `candle → özellikler → giriş koşulu → Grok onayı → freqtrade protections → emir + borsa stopu` (README). Grok **sadece veto** edebilir, işlem başlatamaz (`core/grok_agent.py:33` system prompt: "veto weak ones, default hold").
- Kodda doğrulama: `RegimeComposite.py:268-292` önce günlük risk bütçesi, sonra `self.state.is_backtest` ise LLM atlanıyor (backtest'te LLM yok), değilse `state.confirm_entry(...)`. `strategy_state.py:139-178`: LLM yapılandırılmış ama ulaşılamıyorsa **giriş reddediliyor** (fail-closed); LLM bağlam olarak ADX/RSI/BB/hacim/X-duyarlılığı/günlük özet alıyor. Funding/açık pozisyon bağlamda **yok**.
- Öğrenme (b): "council" LLM'i `strategy_config.json`'a **veri** (lever) yazıyor, kod değil. `core/adaptive.py` doğrulama sırası: HMAC imza (`:171-180`) → sınırlara kırpma + yasak anahtar reddi (`core/levers.py:93-94`: `stoploss, max_open_trades, stake_amount, dry_run, api_key…`) → 30 günlük backtest kapısı (`:225-241`) → 72 saat/20 işlem otomatik geri alma izleyicisi, art arda geri almada donma (`:89`, `:168`). Dikkat: backtest evaluator bağlı değilse "yalnızca sınır doğrulamasıyla uygula" (`:241`) uyarısı var.
- Güvenlik: `XAI_API_KEY`, borsa anahtarı `.env`'den (`core/settings.py:79-105`), `.env.example` "yalnızca TRADE yetkili anahtar, çekim yok" diyor. **Dışarı giden veri**: parite, fiyat, gösterge değerleri, X duyarlılığı → `https://api.x.ai/v1/chat/completions` (`grok_agent.py:26`). Çağrı `confirm_trade_entry` içinde senkron → freqtrade dokümanının "bu callback'te ağ isteği yapma" uyarısıyla çelişiyor (§4). Config'de `dry_run: true` (400 USDT cüzdan).
- Test-sonrası-uygula: backtest + canlı geri alma var; **dry-run'da ileri test yok**.

### 2.2 agent-to-earn — (b) için en olgun güvenlik tasarımı
- Mimari (docs/adr/0001): LLM **asla emir vermez, risk kararı vermez**; yalnızca `strategies/candidates/<ad>.py` yazar. `agent/LOOP.md` izinli eylemleri tek tek sayıyor (tek dosya yaz, `bt.py`, `perf_snapshot.py`, `gate.py`, günlük). Risk (kaldıraç ≤ 10x, stake, stop, devre kesiciler) `user_data/strategies/guarded_strategy.py`'de; aday sınıf bu sınıftan türetiliyor ve `GUARDED_MEMBERS` (`custom_stake_amount`, `confirm_trade_entry`, `leverage`, `custom_stoploss` vb., `:59-67`) ezilemiyor.
- `agent/gate.py`: AST statik denetimi (izinli import listesi `:83`, yasak isimler `:189`, `__` öznitelikleri `:191`, modül seviyesi kod yasağı), bütünlük kilidi (`guardrails.lock`), lookahead testi (`:214`), son 120 günün **backtest'te dışarıda tutulması**, adayın canlı stratejiyi hem `profit_fixed_abs` hem "en iyi işlem hariç" metrikte yenmesi (`:232-262`), terfi sonrası bekleme süresi (ADR-0008), `shutil.move` ile `live/`'a taşıma + `POST /reload_config` (`:295-318`).
- **Dry-run ilişkisi**: bot varsayılan dry-run (`docker-compose.yml:22`, `DRY_RUN=${DRY_RUN:-true}`); ama gate'in test aşaması **backtest**, ileri dry-run değil. Yani "önce dry-run'da dene" burada "önce held-out backtest'te dene".
- Güvenlik: `CLAUDE_CODE_OAUTH_TOKEN`, borsa anahtarı, API şifreleri `.env`'de; `make env` rastgele API sırlarını üretiyor; arayüzler `127.0.0.1`'e bağlı, Cloudflare tüneli yalnızca "sanitized snapshot" yayımlıyor; CI/CD için kısıtlı `deploy` kullanıcısı (ADR-0003). Dışarı giden veri: Claude Code (Anthropic) araştırma bağlamı; sırlar agent'a **kapalı** (okuma engelli).
- Not: LOOP.md'de operatör incelemesi bulguları yazıyor (ör. kısa Donchian satışları her evrende zarar etmiş, backtest evreni yanlılığı) — projenin dürüstlüğü iyi, ama getiri iddiası yok.

### 2.3 AutoEvolve — (b) için en doğrudan, ama en riskli
- Döngü README'de tarif edildiği gibi kodda da var: `orchestrator._do_evolve` (`:554`) LLM'e mevcut kod + metrik + işlem geçmişi + evrim günlüğü veriyor; `improver._validate` (`:724`) yalnızca zorunlu metin parçaları (`class …`, `populate_*`, `INTERFACE_VERSION = 3`, `can_short = True`) ve `compile()` kontrolü yapıyor; `_sanitize` (`:636`) eksik import'ları **otomatik ekliyor**. AST izin listesi / yasak çağrı denetimi görmedim → LLM'in yazdığı kod bot sürecinde olduğu gibi çalışıyor (dosya/ağ/`subprocess` erişimi dahil). Bu, agent-to-earn'ün `gate.py` denetiminin karşıtı.
- `deployer.deploy` (`:977-1003`) dosyayı doğrudan stratejiler klasörüne yazıp `reload_config` çağırıyor; başarısızsa freqtrade'i yeniden başlatıyor. **Ön dry-run/backtest kapısı yok**: ilk sınama canlı (veya dry-run) süreçte, sonra `should_rollback` (`:1020`, varsayılan win-rate < 0.35 veya DD > 0.15) ile geri alma.
- Çok riskli ayrıntı: dağıtımdan sonra `reset_database` (`:740`, varsayılan `reset_db_after_evolve: true`) freqtrade işlem DB'sini **siliyor** → geçmiş işlem verisi kaybolur; kendi öğrenme verinizi bununla karıştırmayın.
- Varsayılan `extra_flags: "--dry-run"` (`config_template.yaml:65`), kullanıcı kaldırırsa canlı olur.
- Güvenlik: API anahtarı `config.yaml`'a düz metin yazılabiliyor ya da `api_key_env` ile ortam değişkeni (`improver.py:521-540`); kod + işlem geçmişi seçilen LLM sağlayıcısına gidiyor.

### 2.4 cryptobot — (a) için en zengin veri/rol tasarımı
- `README`: LangGraph 8 düğüm (veri topla → ele → analist x4 → boğa/ayı araştırmacı tartışması → trader → ML filtre → risk onayı → yaz). 16 veri kaynağı (CoinGlass funding/OI/likidasyon, Cryptonews, Finnhub takvim, F&G, DXY…). Her tur ~40 LLM çağrısı.
- Canlıya giriş: yürütme düğümü `signal.json`/`pending_signals.json` yazıyor (`workflow/nodes/execute.py:15-23`), `AgentSignalStrategy.populate_entry_trend` bunu okuyup `enter_long/enter_short = 1` yapıyor (`:126-150`), giriş fiyat aralığı denetimiyle. Stake/çıkış/kaldıraç LLM çıktısıyla (`custom_stake_amount:424`, `custom_exit:319`, `leverage:445`). `config_dry_run.json`: `dry_run: true`.
- Öğrenme: `evolution/strategy_advisor.py` performans kanıtından LLM ile kural üretiyor, `active_rules` içinde 14 gün geçerli; `get_rules_prompt_addon` kuralları trader/risk_manager prompt'una ekliyor (`:80-95`); süre bitince etkinlik değerlendirilip elenir/yenilenir. Ayrıca `prompt_optimizer`, `model_competition`, `overfit_detector` modülleri var (hepsini okumadım). Bu **freqtrade DB'sinden değil**, kendi `journal`/arşivinden besleniyor.
- Güvenlik: `.env.example`'da Binance, CoinGlass, CryptoNews, DeepSeek/OpenAI/Zhipu/MiniMax/Groq anahtarları; FastAPI+HTMX paneli ve freqtrade REST'i (`freqtrade_api.py:69`). Dışarı giden: piyasa verisi + pozisyon/PnL bağlamı LLM sağlayıcılarına. `jwt_secret_key` örnekte `dry_run_secret_change_me` → değiştirin. AGPL-3.0: ağ üzerinden hizmet verecekseniz kaynak açma yükümlülüğü doğabilir.

### 2.5 HydraQuant
- freqtrade'in tüm kaynağını içeren bir fork (≈1180 dosya) + `user_data/strategies/HydraSizer.py` (4700+ satır). Canlı yolda: `populate`/yardımcı kısım yerel RAG servisine (`127.0.0.1:8891`) HTTP isteği atıyor (`:1192-1215`), `custom_stake_amount` LLM güvenine göre stake'i ayarlıyor (`:2746`), `confirm_trade_entry:3383`, `custom_exit:4317`, `bot_loop_start:264`. Kodda "crisis brake" gibi yorumlar (LLM sağlayıcı kotası tükenmesi) var → gerçek kullanımda sorun yaşandığı anlaşılıyor.
- README "alpha" diyor; "BCM metaplasticity/STDP/pheromone" gibi iddiaların bir kısmı pazarlama dili — **doğrulamadım**. Bakımı/okunması zor; yeni başlayan için doğrudan tabanı olarak önermem, ama (i) LLM servisini ayrı süreç olarak çağırmak, (ii) "atlanan sinyaller defteri" (forgone-alpha) gibi fikirler için okunabilir.
- Güvenlik: yedi LLM sağlayıcısı (ücretsiz katmanlar); API anahtarları yönetimini incelemedim. Fork olduğu için freqtrade güncellemelerini almak zor.

### 2.6 ft-userdata-llm-share
- OpenAI-uyumlu `function calling` ile LLM giriş/çıkış kararı (`LLMFunctionStrategy.py:546`, `:729`); `confirm_trade_entry` yalnızca göstergeleri kaydediyor, LLM çağırmıyor (`:267-322`). İşlem günlüğü JSONL (`trade_experience.jsonl`), `SelfReflectionEngine`, `PatternAnalyzer`, `HistoricalQueryEngine` var. **Bayat** (son commit 2025-11-16) — güncel freqtrade API'sine uyumu garanti değil.
- Güvenlik: `config.example.json:185` `"api_key": "sk-your-llm-api-key"` → anahtar JSON dosyasında düz metin; gömme (embedding) servisi ayrı anahtar.

### 2.7 SYGNIF
- Freqtrade burada "legacy yürütme". `SygnifSentiment` sınıfı Anthropic API'ye doğrudan `requests` ile gidiyor (`SygnifStrategy.py:46-80`, model `claude-haiku-4-5-20251001`); haber GDELT vb.'den çekiliyor (`:179-194`). TA skoru 40-64 aralığındayken LLM duyarlılığı |≥2| ise skora ekleniyor ve `claude_s*` etiketiyle giriş açılıyor (`:1219-1231`) → sentiment `None` ise giriş yok (fail-closed). Aynı repoda kişisel altyapı (Tailscale, EC2, çok sayıda daemon) karışık; lisans yok → yeniden kullanım hakkı belirsiz.

### 2.8 Diğerleri
- evotrade: strateji-üretici araştırma hattı (Claude/OpenAI → freqtrade backtest → Postgres sicili). Canlı yola dokunmuyor. Lisans alanı NOASSERTION.
- guarded-trader: README'nin açık hedefi "LLM yalnızca araştırır, emir veremez, borsa anahtarını görmez". Araştırma servisinde ağsız/salt-okunur sandbox, rastgele-giriş null testi, Deflated Sharpe, deneme sicili. (b) için "kapı" tasarımı referansı.
- freqtrade_dev_mcp: 12 araçlı MCP (veri indir, backtest, hyperopt, sonuç analizi); dosya yazan araçlar `FREQTRADE_MCP_PATH` ile sınırlı. Canlı yola bağlı değil.
- pulse-freqtrade: `adapter.py` REST (`/api/v1/forcebuy` vb.), örneklerde sabit parola `SuperSecurePassword` (örnek kod). LLM yok, lisans yok, tanıtım odaklı → düşük öncelik.

## 3. Desenlerin karşılaştırması

| Desen | Örnek | Artı | Eksi |
|---|---|---|---|
| LLM `confirm_trade_entry` vetosu | regime-trading-bot | Basit; LLM sadece "hayır" diyebilir, fail-closed; backtest'e dokunmaz | Callback içinde senkron ağ çağrısı (docs uyarısı); backtest edilemez, LLM'in katkısı ölçülemez |
| LLM'in sinyali dosya/DB'ye yazması, stratejinin okuması | cryptobot | LLM gecikmesi emir yolundan çıkar; 5 sn'lik döngüyü bloklamaz; denetim/audit kolay | Sinyal bayatlayabilir (TTL/fiyat aralığı kontrolü gerekir); backtest'te LLM yok |
| LLM'in kodu yazması + otomatik dağıtım | AutoEvolve | Tam otonom | Yazılan kod bot sürecinde çalışır (RCE benzeri risk), dry-run ön kapısı yok, DB'yi siler |
| LLM'in aday kodu yazması + deterministik kapı | agent-to-earn | Risk kodu LLM'e kapalı; AST denetimi; OOS; bekleme süresi | OOS'un kendisi de aşırı uyuma açıktır; ileri dry-run yok |
| LLM'in sınırlı parametre (veri) yazması + geri alma | regime-trading-bot council | Kod değil veri; sınır, imza, geri alma | Backtest kapısı bağlı değilse atlanıyor |
| Kural/ders üretip prompt'a enjekte | cryptobot strategy_advisor | Kolay denetlenir, 14 gün süre sınırlı | Kuralları sınayan bir backtest zinciri yok; LLM'in LLM'i yönlendirmesi |

## 4. freqtrade'in kendi araçları — bu iş için nasıl kullanılır

Doğrudan okuduğum dokümanlar: [strategy-callbacks](https://www.freqtrade.io/en/stable/strategy-callbacks/), [producer-consumer](https://www.freqtrade.io/en/stable/producer-consumer/), [rest-api](https://www.freqtrade.io/en/stable/rest-api/), [strategy-advanced](https://www.freqtrade.io/en/stable/strategy-advanced/), [freqai](https://www.freqtrade.io/en/stable/freqai/). Aşağıdaki sayfaların linklerini standart yoldan verdim ama bu oturumda **açıp doğrulamadım**: [hyperopt](https://www.freqtrade.io/en/stable/hyperopt/), [webhook-config](https://www.freqtrade.io/en/stable/webhook-config/), [configuration](https://www.freqtrade.io/en/stable/configuration/), [freqai-running](https://www.freqtrade.io/en/stable/freqai-running/), [freqai-feature-engineering](https://www.freqtrade.io/en/stable/freqai-feature-engineering/), [plugins (protections)](https://www.freqtrade.io/en/stable/plugins/).

| Araç | Dokümandan öğrendiğim | LLM/öğrenme katmanı için kullanımı |
|---|---|---|
| `bot_start` | Strateji yüklendikten sonra bir kez çalışır | LLM istemcisini, ders/kural dosyasını yükle; başlangıç kontrolü |
| `bot_loop_start` | ~5 sn'de bir (canlı/dry-run), backtest'te mum başına bir; hafif tutulmalı | Dosyadan/kuyruktan **önceden hesaplanmış** LLM kararını belleğe al (ağ çağrısı değil). Ayrı bir iş parçacığı/süreç LLM'i asenkron çağırır |
| `custom_stake_amount` | Hata verirse önerilen stake'e düşer | LLM güvenine/rejime göre stake **çarpanı** (0..1, üst sınır sabit) |
| `confirm_trade_entry` | "Zamanlama kritik, ağ isteği yapma"; son kapı, emri iptal edebilir | Yalnızca **önbellekteki** karara bak: veto/onay. Canlı çağrı yerine `bot_loop_start`/arka plan servisinin yazdığı karar |
| `confirm_trade_exit` | Stoploss çıkışlarını da engelleyebilir, büyük zarar riski; likidasyonda çağrılmaz | LLM'e **bağlamayın** (en azından stop/likidasyon yolunda) |
| `custom_exit` | Her iterasyonda (~5 sn) çağrılır | Haber/rejim bozulması için "çık" sinyali; yine önbellekten |
| `custom_stoploss`, `adjust_trade_position`, `leverage` | Sık çağrılır; `adjust_trade_position` hızlı olmalı; `leverage` sadece futures | Risk parametreleri kodda sabit/sınırlı kalsın; LLM yalnızca sınır içinde öneri versin |
| `store_custom_data/get_custom_data` (trade) | JSON, küçük veri, trade'e bağlı, DB'de kalıcı | Giriş anındaki gerekçeyi (LLM kararı, güven, bağlam özeti) işleme yaz → kapanışta öğrenme verisi olur |
| REST API (`/trades`, `/performance`, `/status`, `/reload_config`, `/pause`, `/forceenter`, `/forceexit`) | Basic/JWT, JWT ~15 dk, varsayılan localhost, internete açma | Ayrı "öğrenme" sürecinin kapanan işlemleri okuması (`/trades`, max 500) ve kontrollü `reload_config`/`pause`; Python istemcisi `freqtrade-client` |
| WebSocket mesajları + Producer/Consumer | Üretici `analyzed_df` ve `whitelist` yayınlar, tüketici alır; `ws_token` gizli olmalı | Ağır analiz (FreqAI veya LLM) bir "producer" botta/süreçte, işlem yapan "consumer" botta hafif mantık. İşlem botu LLM sağlayıcısına hiç bağlanmaz |
| Webhook/Telegram | (bu oturumda doğrulanmadı) | Olay akışı (giriş/çıkış) → dış öğrenme süreci |
| FreqAI | Kendi ML modellerini canlıda periyodik/sürekli yeniden eğitir, dry/live'da arka planda | LLM'e rakip/tamamlayıcı **sayısal** katman: LLM'in ürettiği özellikleri (ör. haber duyarlılık skoru) bir feature olarak eklemek, etiketleri işlem sonucuyla eğitmek. Bakımcıların önerdiği yol |
| Hyperopt | (bu oturumda doğrulanmadı) | Kapanan işlemlerden çıkan "parametre aralığı" önerilerini **backtest + hyperopt** ile gerçek veride sınamak; AutoEvolve/agent-to-earn'ün dışarıdan yapıp backtesti yarım bırakmasına karşı doğru yer |
| `dry_run` | Ayrı DB/ cüzdan | Aday kural/parametrenin **ileri** (forward) testi: ikinci bir dry-run örneği (farklı `db_url`, port) |

## 5. "freqtrade'e bu katmanları eklemenin en temiz yolu" — öneri

Tasarım ilkesi (agent-to-earn, regime-trading-bot, guarded-trader'ın ortak çıkarımı + freqtrade dokümanının uyarıları): **LLM emir yoluna, risk koduna ve borsa anahtarına girmez; kararı bir "veri"dir (JSON), strateji onu önbellekten okur; her değişiklik sınırlı, imzalı ve geri alınabilirdir.**

```
┌─ Sürec A: "Analist" (ayrı süreç/konteyner, freqtrade'den bağımsız) ─────────┐
│ Girdi: freqtrade REST (/trades, /performance), Producer/Consumer WS         │
│        (analyzed_df), funding/OI (borsa API), haber                        │
│ LLM → karar JSON'u (pair, bias, güven, ttl, gerekçe)                       │
│ Çıktı: user_data/llm_decisions.json (atomik yaz, ttl'li, imzalı)            │
└───────────────────────────────┬─────────────────────────────────────────────┘
                                │ dosya/küçük SQLite (ağ yok)
┌─ Freqtrade (canlı bot) ───────▼─────────────────────────────────────────────┐
│ bot_start        : kural/parametre dosyasını yükle, imza doğrula           │
│ bot_loop_start   : llm_decisions.json'ı belleğe oku (≈5 sn, hafif)         │
│ populate_*       : deterministik giriş mantığı (LLM burada yok → backtest'e │
│                    olduğu gibi girer)                                       │
│ confirm_trade_entry : yalnızca bellekteki karar: bias çelişiyorsa/ttl      │
│                    bitmişse politika (fail-closed veya fail-open) uygula,  │
│                    karar+gerekçeyi trade.set_custom_data ile işleme yaz    │
│ custom_stake_amount : 0..1 çarpan, kodda sabit üst sınır                    │
│ custom_exit      : yalnızca "bias tersine döndü / haber riski" için; stop,  │
│                    kaldıraç, likidasyon yolu LLM'siz                        │
│ confirm_trade_exit: LLM yok                                                 │
└───────────────────────────────┬─────────────────────────────────────────────┘
                                │ kapanan işlemler (REST /trades)
┌─ Sürec B: "Öğrenme/Yansıtma" (gece veya N işlemde bir) ─────────────────────┐
│ 1. İşlem günlüğü: /trades + custom_data gerekçesi → kendi JSONL/SQLite       │
│    (freqtrade DB'sini silmeyin/yeniden yazmayın)                            │
│ 2. İstatistik: etiket/rejim/pair bazında win-rate, ortalama R, MAE/MFE       │
│ 3. LLM yansıtması: öneri = {parametre değişikliği ∈ izinli sınırlar}         │
│    veya {kural metni}, **kod değil**                                        │
│ 4. Kapı: (i) şema + sınır kırpma + yasak anahtarlar (stoploss, stake,       │
│    dry_run, api_key…), (ii) backtest/hyperopt held-out dönemde mevcut        │
│    ayarı yenmeli, (iii) ileri test                                          │
│ 5. Uygula: yalnızca (iii) geçerse canlı config'e/dosyaya yaz →               │
│    POST /reload_config; N işlem/72 saat sonra kötüleşirse otomatik geri al  │
└──────────────────────────────────────────────────────────────────────────────┘
        (iii) ileri test = AYNI strateji + aday parametre ile ikinci bir
        freqtrade dry-run örneği (ayrı db_url, ayrı port, aynı pair listesi);
        belirli süre/işlem sayısı boyunca canlı (dry-run) örnekle
        karşılaştırılır; ancak sonra canlıya terfi
```

Neden bu yol:
1. **Zamanlama uyarısına uyar**: dokümana göre `confirm_trade_entry`/`custom_exit` ağır iş ve ağ isteği için uygun değil; ağ çağrısı ayrı süreçte, strateji sadece dosyayı okur (cryptobot deseninin güvenli hali).
2. **LLM'in zararı sınırlı**: LLM kod yazmıyor (AutoEvolve'daki RCE benzeri risk yok), risk kodunu değiştiremiyor (agent-to-earn `GUARDED_MEMBERS`), değişiklik sınırlı veri (regime-trading-bot `levers.py`).
3. **Backtest bütünlüğü**: LLM backtest'e girmez; deterministik katman backtest edilir, LLM katkısı ayrı ölçülür (hem "LLM vetosu açık/kapalı" dry-run karşılaştırması hem `custom_data`'daki gerekçelerle).
4. **FreqAI ile tamamlayıcı**: haber duyarlılığı gibi LLM çıktısını bir feature olarak FreqAI'ye vermek, etiketleri gerçek sonuçla eğitmek bakımcıların önerdiği yöne uyar ve LLM'in "halüsinasyon" riskini istatistiksel modele bağlar.
5. **Producer/Consumer**: ağır analiz (LLM/FreqAI) ayrı bir bot/süreçte; işlem botu hafif kalır ve LLM sağlayıcısına/API anahtarına hiç dokunmaz.

Önerilen aşamalar (en az riskliden):
1. Yalnızca **log modu**: LLM kararları dosyaya yazılır, `confirm_trade_entry` bunu **uygulamaz**, sadece `custom_data`'ya "LLM olsaydı veto ederdi" bilgisini yazar (gölge mod). 2–4 hafta dry-run.
2. Gölge sonuçları analiz et (veto edilen işlemler gerçekte kaybettirdi mi? regime-trading-bot'un backtest'te LLM'i atlamasının sebebi bu ölçümün zorluğu).
3. Vetoyu aç (fail-closed, kısa ttl), `custom_stake_amount` çarpanını ekle.
4. Süreç B'yi **öneri modunda** çalıştır (otomatik uygulama kapalı), insan onayıyla uygula.
5. Ancak ondan sonra ileri-test kapısı geçen değişiklikleri otomatik uygula.

Hazır parça eşlemesi:
- (a) veto: `regime-trading-bot` `core/grok_agent.py` (JSON sözleşmesi) + `core/strategy_state.py` (fail-closed mantığı); sinyal dosyası: `cryptobot` `AgentSignalStrategy.py` + `workflow/nodes/execute.py`; veri toplama (funding/OI/haber): `cryptobot/src/cryptobot/data/`.
- (b) kapı: `agent-to-earn` `agent/gate.py` (AST denetimi, OOS, terfi sonrası bekleme), `regime-trading-bot` `core/adaptive.py` + `core/levers.py` (imza, sınır, geri alma), `guarded-trader` (ADR'ler, null test, deneme sicili); kural-enjeksiyonu: `cryptobot/evolution/strategy_advisor.py`.
- Doğrudan kopyalanmaması gerekenler: AutoEvolve'un kodu otomatik dağıtıp DB sıfırlaması, pulse-freqtrade'in tanıtım iddiaları.
- Lisanslar: regime-trading-bot/agent-to-earn/guarded-trader (MIT/Apache) kopyalamaya daha uygun; AutoEvolve, HydraQuant (GPL-3.0), cryptobot (AGPL-3.0) kopyalarsanız lisans yükümlülüğü gelir; SYGNIF/pulse-freqtrade lisanssız → izinsiz yeniden kullanmayın. freqtrade'in kendisi [GPL-3.0](https://github.com/freqtrade/freqtrade) (≈56.9k★, son push 2026-11-15) — stratejiniz ona bağlı çalıştığı için de GPL'e dikkat.

## 6. Güvenlik kontrol listesi (genel)

- Borsa anahtarı: yalnızca işlem yetkisi, **çekim kapalı**, IP kısıtlı. LLM sürecinin ortamında borsa anahtarı bulunmasın (agent-to-earn ve guarded-trader bunu yapıyor).
- LLM API anahtarı: `.env`/ortam değişkeni; düz metin `config.json`'a koymayın (ft-userdata-llm-share ve AutoEvolve'un `api_key:` alanı bu hataya açık). 
- Dışarı giden veri: pair, fiyat, gösterge, PnL/pozisyon bağlamı LLM sağlayıcısına gider (cryptobot, regime-trading-bot, SYGNIF, AutoEvolve işlem geçmişi + kodu gönderir). Hesap bakiyesi/adres göndermeyin; yerel model (Ollama) seçeneği AutoEvolve ve HydraQuant'ta mevcut.
- freqtrade REST/WS: localhost, güçlü parola, 32+ karakter `jwt_secret_key`, rastgele `ws_token`; internete açmayın (docs).
- LLM kodu çalıştırma: LLM'e kod yazdırıyorsanız AST izin listesi + ayrı sandbox/konteyner (agent-to-earn `gate.py` modeli); AutoEvolve'un tek `compile()` kontrolü yetersiz.
- Dosya-tabanlı sinyal: atomik yazma, TTL, imza/hash, boyut sınırı; strateji parse hatasında **işlem yapmama** yönüne düşsün.

## 7. Sınırlar ve doğrulanmayanlar

- Hiçbir repoyu çalıştırmadım/kurmadım; "canlıya girer" hükümleri kod okumasına dayanıyor, çalışma zamanı davranışı doğrulanmadı.
- HydraQuant ve cryptobot büyük; yalnızca canlı yola bağlanan noktaları taradım. HydraQuant'ın öğrenme iddialarını (BCM/STDP vb.) doğrulamadım. ft-userdata-llm-share yansıtma çıktısının prompt'a tam akışını satır satır izlemedim.
- Sak-114514/freqtrade-agent, syh52/ft-analyzer, qrak/LLM_trader, Superior-Trade trading-terminal derinlemesine incelenmedi.
- Arama GitHub arama API'siyle sınırlıydı (kod araması yalnızca varsayılan dal, hız limitli); küçük/yeni repolar kaçmış olabilir. Yıldız sayıları anlık görüntüdür.
- freqtrade dokümanlarının hyperopt, webhook, configuration, freqai-running, plugins sayfalarını bu oturumda açmadım; tablodaki ilgili satırlar genel bilgiye dayanır ve işaretlendi.
