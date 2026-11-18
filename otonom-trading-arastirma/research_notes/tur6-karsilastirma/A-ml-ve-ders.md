# Tur 6 — A: ML/LLM (madde 1) ve ders döngüsü (madde 2) — repo karşılaştırması

Tarih: 18 Kasım 2026. Kapsam: sahibin 9 maddesinden **1 (ML/LLM kendi işlem önerisi: "beyin")** ve **2 (her işlemden ders; makineyi besleme)**. Yöntem: yalnız `git clone --depth 1` + `grep/sed/cat`; hiçbir üçüncü taraf kodu çalıştırılmadı, kurulmadı. Repo metinleri veri sayıldı; **istem enjeksiyonu denemesi görülmedi** (README/istemlerde bana yönelik yönerge yoktu; yalnız bazı repoların kendi LLM istemleri var).

**Kanıt etiketleri (her satırın sonunda):** `[K]` = bu turda kodu grep/sed ile okudum, dosya:satır verilmiştir; `[K-dosya]` = dosya/sembol adı ve başlık yorumu okundu, iç mantık satır satır doğrulanmadı; `[Ö]` = önceki tur notundan (kod doğrulamalı) alındı; `[R]` = yalnız README / dosya adı / anahtar-sözcük sayımı (zayıf kanıt). Satır numaraları 18 Kasım klonlarına aittir.

> Dürüstlük notu: 247 klon + 8 yerel klon + sahibin 2 projesi için anahtar-sözcük taramasını (yansıma/ders/yeniden eğitim/model.fit/RL vb.) hepsinde çalıştırdım; **kodu satır satır okuduğum** repolar `[K]` etiketli olanlardır (≈60). Geri kalan satırlarda "yalnız README/dosya adı" yazıyorsa o satırdaki iddia zayıftır. Karar son incelemecinindir; ben olguları topluyorum.

## 1. Bizim şu anki plan (madde 1 ve 2) — özet

Kaynaklar: `ml-faz-tasarimi.md` (v2, 17 Kas), `ml-guclendirme-plani.md` (17 Kas), `trader/docs/ders-spec.md` (Rev 1-4), `trader/docs/motor/dd12-capraz-varlik-spec.md` (sürüm 3, 18 Kas), `trader/config/lesson.json`, `trader/src/trader_core/ledger.py:85-96` (`LESSON_PARAMS`). (Not: görevdeki `config/lesson.json` ve `src/trader_core/lesson.py` yolları `trader/` altındadır.)

### 1.1 Madde 1 — ML/LLM'in rolü

| Konu | Plan (kaynak) | Sayılar |
|---|---|---|
| ML'in yeri | "ML önce filtre olarak girer, strateji olarak değil": price action adayı üretir, model yalnız "alma" diyebilir (meta-etiket); aday ekleyemez, fiyat/stop/boyut değiştiremez (ml-faz §0.1, §4). Model bir **parametre sürümüdür** (§0.2), `ml_mode` varsayılan `off` (`config/engine.base.json:10`) | model puanı boyutu etkilemez; risk kilidi son söz |
| Etiket / eğitim | Üçlü bariyer: stop -1R, hedef +2R, 72 adet 1s mum; purged walk-forward, genişleyen pencere ≥8 ay eğitim / 2 ay test / 4 dilim; lojistik (taban) + sığ LightGBM (derinlik ≤4, yaprak ≥50); haftalık yeniden eğitim ML-4'te (ml-faz §3.1-3.3) | ağırlık: gerçek 1,0; kâğıt 0,7; varsayımsal 0,5; geçmiş tarama 0,3 |
| Terfi kapısı | Net R farkı ≥ +0,10 R ve durağan bootstrap %90 alt sınırı > 0; filtreli net beklenti > 0; DSR ≥ 0,95; PBO ≤ 0,25; düşüş filtresizden kötü değil; adayların ≥%30'u alınır; IC kapısı (t≥2, 4 dilimin ≥3'ü pozitif); Brier; maliyet x2+5bp'de ≥ -0,05 R; eşlik testi 1e-9; görevdekinden kötü değil (ml-faz §1, §3.4) | eşikler koşudan ÖNCE yazılı; sonuç görüldükten sonra yalnız sıkılaşır |
| Gölge / etkinleştirme | Gölge ≥6 hafta ve ≥150 puanlı aday (≥50'si alınmış); ilk terfi Telegram onayı; sonra haftalık yenileme otomatik; 21 gün süresi dolan model -> yeni giriş yok (ml-faz §3.5-3.6, §7) | ML-3 en erken Ocak ortası |
| Yasaklar | Canlıda RL yok; LLM öz-evrim yok (LLM model eğitmez/özellik seçmez/eşik koymaz); model boyut/kaldıraç/stop belirlemez (ml-faz §8) | - |
| Kendi adayını üreten ML | ml-faz'da **ML-5** (ML-4'te ≥6 ay kayıt, ayrı ön kayıt). **dd12 §5.2 (18 Kas, daha yeni) bunu öne çeker:** "M1@1s": son 64 barın ATR-ölçekli mum dizisi + yapı özellikleri, LightGBM 3 sınıf (uzun/kısa/yok), eşik eğitim-dışı dilimde barların en yüksek ≈%2'si, etiket stop 1,5 ATR / hedef 3 ATR / 48 bar, eğitim sunucu dışı 20 kripto 2021-01 -> 2026-04-30, 14 günde bir yeniden eğitim, bar kapanışında piyasa emri, küme/seans/risk kapılarından geçer; teslim ≤16 Aralık (Faz 3) | **İki belge çelişir**; dd12 geçerli sayılıyor. dd12 Faz 1'de "ML etkin, gölge yok; kâğıtta kapı şartı aranmaz; testnet/canlıya kapıdan geçmemiş model yüklenemez" |
| Süzgeç durumu | 19c kapısı **KALDI** (`ml-guclendirme-plani` §A, §2): sınav 240 gün/624 işlem; filtresiz günlük seri t=1,20 (ρ≥0,14 gerekirdi); 33 özelliğin 11'i ölü; girişte yön bilgisi şansa yakın (%35,3 vs şans %33,3); kâr kuyrukta (en iyi %5 işlem +412 R, kalan %95 -318 R). Beklenen geçme olasılığı canlıya kadar %15-25. dd12 Faz 1 r03'ü 10 çiftte "etkin" çalıştırır (kapıda AUC 0,50) | derlem 2021'e uzatılır (~1500 gün), ≤8 tarif (5 koşulur) |

### 1.2 Madde 2 — ders servisi

| Konu | Plan (kaynak) | Sayılar |
|---|---|---|
| Ne ayarlar | Yalnız 5 parametre (`ledger.py:85-96`): `vol_ratio_max` [1,3-1,7] adım 0,25; `stop_buffer_atr` [0,2-0,5] adım 0,1; `trail_atr` [2,5-3,5] adım 0,5; `range_target_frac` [0,6-0,9] adım 0,125; `rr_min` [1,2-2,0] adım 0,25. Risk ayarları ders servisine KAPALI (ders-spec §1.2) | ≤1 parametre, ≤1 adım, tek öneri; haftada ≤1 değişiklik (`ledger.py:2065` `weekly_limit`) |
| LLM'in rolü | LLM **menüden seçer**, serbest sayı/kod yürütmez; Python aday menüsünü + kanıtı hesaplar; model `claude-sonnet-5-5`, Batch API, günlük 02:40 UTC, çıktı ≤1500 token, istem ≤12.000 token tahmini (ders-spec §1.3-1.4, §3, §6; `lesson.json`) | `mode="llm"`; `allow_off_menu=false` |
| Kanıt kapısı | Kontrol noktaları [30, 45, 60] kapanmış işlem; `min_affected` 8; `min_gap_r` 0,5 R; `min_z` 2,0; `min_distinct_days` 8; `max_pair_share` 0,5; defter kanıtı ≥20 işlem (`ledger.py:1124` `min_evidence_trades=20`) (ders-spec §3, §4.4) | "30 işlem kanıtı" = ilk kontrol noktası |
| Gölge dönem | İlk 4 hafta her öneri kullanıcıya gider (`shadow_weeks`=4, 4-6 arası kilit) | `lesson.json: shadow_weeks=4` |
| Otomatik geri alma | İzleme K=20 işlem, marj 0,3 R, z 1,0; erken geri alma n≥10 ve ort ≤ -0,6 R ve z 1,645, ≥4 ayrı gün; en çok 28 gün; kara liste 14 gün; yeniden denetim 30 işlem / 42 gün (ders-spec §10) | `monitor_k=20`, `blacklist_days=14` |
| İkiz | Faz 0: salt-okunur ikiz kontrolü, ikizden en çok 2 adım (`twin_enabled=true`) -> **dd12 §6'da ikiz KALKAR** | `lesson.json` henüz `twin_enabled=true`, `shadow_weeks=4` (dd12'ye göre güncellenmemiş) |
| Karşı-olgusal kanıt (Rev 4) | Alınmayan sinyallerin "alınsaydı" sonucu: ağırlık 0,5, yalnız DESTEK, hiçbir eşiği/otomatik uygulamayı değiştirmez; menü girdisinde `cf_n` varsa öneri her zaman `needs_user`; n≥30, ≥8 ayrı 3 günlük blok, lb90>0 (ders-spec Rev 4, satır 50-52) | `counterfactual_min_n=30` |
| dd12 sürüm 3 | "Referans sürüm" = son kullanıcı onaylı ayar; **ders etkisi** = Σ R(bugünkü ayarın aldığı, referansın almayacağı; gerçek) − Σ R(referansın alacağı, bugünkü ayarın elediği; "alınsaydı"); tek değişiklik: ≥30 farklı-karar adayında etki ≤ −3 R -> geri al; toplam ≤ −10 R -> referans sürüme dön; otomatik uygulama ilk günden açık; Faz 3 "kurulum dersi": ≥40 aday ort ≤ −0,15 R -> kurulum kapat, son 40 aday ≥ +0,05 R -> yeniden aç; ML etkisi aynı yolla ölçülür (dd12 §6) | 10 R freni; 3 R tek değişiklik |
| Ders -> ML'yi besler mi? | Ders servisi ML'yi **doğrudan beslemez**; ayrı iki hat. Ortak olan: defter (`decision_events`, her aday özellikleriyle) ve gece işi "alınmayan sinyalin varsayımsal sonucu" ML'nin eğitim örneğidir (ml-faz §3.1). Model terfisi de ders servisiyle **aynı tek-gözlem sırasına** girer (ml-faz §3.5). LLM metin dersi (yansıma) yok; "ders" = parametre değişikliği, emeklilik = geri alma + 14 gün kara liste | - |
| Sahibin hayali | "Her işlemden kâr/zarar ders çıkarıp makineyi besleyen" servis ≠ plandaki: 5 ayar, ≤1 adım, haftada 1, ≥30 işlem kanıtı | madde 2 |

## 2. Madde 1 — ML/LLM işlem önerebiliyor mu? Olgusal özet (ayrıntı: Bölüm 3 tablosu)

**2.1 "Beyin" olarak ne yapılıyor (kanıt etiketli)**

| Rol | Örnek repolar (kanıt etiketiyle) | Not |
|---|---|---|
| LLM giriş kararını VERİR (aday + yön + boyut) | astra (`signals.py:327`) [K], nof1.ai (`tradingAgent.ts:447`) [K], nofx (`auto_trader_decision.go:283`) [K], hyper-alpha-arena (`ai_decision_service.py:483`) [K], nof0 (`executor/utils.go:36`) [K], peri (`analyst.py:215`, `engine.py:1394`) [K], erfaniaa (`prompts.py:22`) [K], rgg81 (Watcher->Analist->Tartışma->Yargıç->Trader, `SKILL.md:37-42`) [K], qrak (`data_models.py:11`) [K], quant-flow (`engine.py:441`) [K] | Hepsinde sert risk/yürütme kodda ya da yalnız istemde (nof1.ai klonları: istemde %15-25 bakiye, 20-25x `super-nof1.ai/lib/ai/prompt.ts:97`) |
| LLM SEMBOL SEÇER / aday listeler | rgg81 Watcher ~10 uzun/kısa aday (`README`, `SKILL.md`) [K]; contesttrade LightGBM+ajanlarla olay güdümlü hisse seçimi (`train_model.py:34`) [K]; shoaib top-30 hacim taraması [R]; friestrader `rank_candidates.py` [K-dosya]; superior trading-terminal "kurulum sıralar" [R] | Diğerlerinde evren sabit |
| LLM ÇIKIŞ yönetir | erfaniaa `adjust_sl/adjust_tp/reduce_position` (`prompts.py:22`) [K]; nof1.ai `closePosition` [K]; MATS çıkış öğrenici (`exit-price-learner.ts`, canlıda `index.ts:4176,10249,10897`) [K]; astra/rgg81 çıkışlar deterministik motorda (rgg81: borsada duran reduceOnly stop/TP, README) [R] | - |
| ML SİNYAL ÜRETİR (kendi girişini) | aleksnovo Ai1 LightGBM giriş üretici [K]; intelligent-trading-bot (ML skoru -> `threshold_rule` ±0,08, `config-sample-1h.jsonc:90-95`) [K]; ReforceXY MaskablePPO nötr/giriş/çıkış (`freqai-strategies/README:8`) [K]; bitbotby SAC (`dqn_signal.py:1-6`) [K]; orallexa PPO + RF/XGB (`rl_agent.py:4`, `ml_signal.py:5`) [K]; mohamed-sm FreqAI RL [K-dosya]; torchtrade PPO/DQN/GRPO + LLM ince ayar (`README:31,37`) [K]; MATS Q-RL tablosu (`q-rl-table.ts:1-5`) [K]; hydraquant LinUCB/RL [K-dosya]; Kronos (yalnız fiyat tahmini) [K] | **Hiçbirinde bağımsız canlı kanıt bulmadım**; aleksnovo varsayılanı `module1_only` (yalnız veri toplama, `config` satır 7); ReforceXY/itb dry-run |
| ML yalnız ELER/KAPI (bizim çizgi) | shoaib (`min_win_prob=0,55`, AUC≥0,55 kapısı, `trainer.py:30-47`) [K]; pettekay (`meta_label.py:212-243`) [K]; flukelaster (3 onaydan biri, `confirmation_gate.py:6-110`) [K]; aleksnovo Ai2 filtre [K]; FTMO, polymarket-btc, forex-gold, Aurum, dukesan (meta-etiket) [Ö/K-dosya] | forex-gold notu (plan §1.3): "hiçbir şey alma'ya yakınsayan kapı filtre değildir, üreticiye dair hükümdür" |

**2.2 Olgular**
1. **Alınmayan/engellenen sinyalin sanal sonucu** dış repolarda da var ve bizim `ml-faz §3.1` / ders-spec Rev 4 ile aynı fikir: aleksnovo "paralel sanal günlük" (her Ai1 sinyali 60 dk, her onaylı giriş 360 dk izlenir; README) [K]; qrak bloke edilen işlemleri kaydeder (`vector_memory.py:312`, `brain_context.py:90`) [K]; rgg81 `declined_edge_setups` + `missed_opportunities` (`SKILL.md:68`) [K]; aithos HOLD/FLAT etiketi (`outcome_resolver.py:1-6`) [K].
2. **Kendi adayını üreten ML için kanıt:** bu evrende ileri-dönem, maliyet-sonrası, bağımsız ölçüm göstereni görmedim. En dürüst kayıtlar olumsuz: samsoncukor06 (8 hafta gerçek para, "stock edge yok") [R]; loveolu (~100 deneme, çıkan strateji yok) [R]; oficcejo (2 hafta, özsermaye ~değişmedi) [R]; bvedtrade (634 işlem, -0,55R) [Ö]; rafael evotrader (al-tut'u yenemedi) [Ö]; 19c bizim kendi sonucumuz. Pozitif iddialar (atlas-gic, alphaforge, baran0732, leadline88) için **kod yok**: atlas-gic repoda yalnız 6 .py (`src/mirofish/*`, `src/janus.py`) [K]; alphaforge/baran0732/leadline88 kaynak dosyası yok [K].
3. **LLM'e kod sınırı koyanlar:** quant-flow ("LLM yalnız JSON, emir/risk kodda", README) [K], erfaniaa deterministik risk katmanı [K], guarded-trader (aday kod kabul ADR'si) [R], eugmsub/robinhood (ayrı saf limit katmanı) [R], Vibe-Trading mandate (insan imzalı limitler) [K].
4. **Kendi adayını üreten ML'in varsayılan kipi:** aleksnovo `module1_only` (yalnız veri toplar, işlem açmaz; `-> sleep -> emulate -> live` aşamalı); ITB ve ReforceXY/QuickAdapter dry-run varsayılanlı; qlib yalnız skor üretir. dd12 Faz 3 M1 tasarımı (LightGBM 3 sınıf, 2021-2026-04 eğitim) en çok aleksnovo Ai1 (LightGBM, **GPL-3.0: yalnız fikir**) ve ITB (MIT) ile örtüşüyor.


## 3. Madde 1 — tablo (ML/LLM kendi işlem önerisi, sembol seçimi, çıkış yönetimi, filtre, RL)

| Repo | Ne yapıyor (kod kanıtı) | Sayılar/varsayılan | Lisans |
|---|---|---|---|
| `00hsynclk/crypto-trading-bot` | Binance spot+vadeli otomatik/manuel işlem (Türkçe); collect_training_data.py veri toplayıcı; ML karar bağı doğrulanmadı [R] | - | yok |
| `0xemmkty/quantmuse` | 'AI/ML' kantitatif sistem iddiası; data_service/factors/stock_selector.py faktör tabanlı seçici [R] | - | MIT |
| `0xethanq/astra-quant-agent` | LLM 'beyin' sinyalleri/aksiyonları üretir: scripts/trader/signals.py:327 `BUY_LONG`, order_submit.py:320; OKX'e koşullu emir [K] | - | AGPL-3.0+CommonsClause |
| `0xsanei/darwinia` | 'Darwinia kur, BTC stratejisi evrimleştir' ajan becerisi (README:1; darwinia/discovery/asset_scanner.py) [R] | - | MIT |
| `195440/nof1.ai` | LLM ajan kararı: src/agents/tradingAgent.ts:447,784 `openPosition(symbol, side, leverage, amountUsdt)` araç çağrısı [K] | - | AGPL-3.0 |
| `o_1l3a-proje (sahibin)` | ML/LLM ile işlem önerisi YOK: 3 ajan kitaplardan kurala dökülmüş kart stratejileri çalıştırır; ML 'elenenler' arasında (DURUM.md:34) ve 'ML panoya filtre olarak eklenmez, ayrı ön kayıtlı deney' (DURUM.md:344); lider ajan yalnız değişiklik ÖNERİR, onay insanda (README:1-3) [K] | - | sahibin projesi |
| `51bitquant/ai-hedge-fund-crypto` | LangGraph iş akışı + topluluk teknik analiz + LLM kripto karar (README:1) [R] | - | MIT |
| `6kmfi6hp/ft-userdata-llm-share` | Freqtrade + OpenAI fonksiyon çağrısı: LLM 30 dk ana zaman diliminde global piyasa analizi yapar (README:1) [R] | 30 dk | MIT |
| `7thdrag0n/autoevolve` | LLM işlem DEĞİL strateji KODUNU yeniden yazar (autoevolve/improver.py, deployer.py; README:1) [K] | - | GPL-3.0 |
| `adamcyh/evotrader` | AI ekibi seçtiğiniz ABD hisse/ETF'sinde işlem yapar (README:1) [R] | - | Apache-2.0 |
| `aenger-priv/contextualbandits` | Bağlamsal bandit (seçenek seçme) algoritmalarını sentetik zaman çizelgesinde karşılaştırır; canlı işlem yok (bandit_algorithms.py, contextual_bandits/policies.py) [R] | - | MIT |
| `affaan-m/dprc-autotrader-v2` | Solana için LLM ajanı (Rust `rig`, src/agents/mod.rs:4 OpenAI istemcisi; 'stoic' kişilik istemi personality/mod.rs:38); öneri/giriş üretir [R] | - | MIT |
| `ai-brokers/aibrokers` | Çok-LLM-ajan 'hedge fund' (src/agents/portfolio_manager.py:3 ChatOpenAI); LLM portföy kararı verir [R] | - | MIT |
| `ai4finance-foundation/finrl` | RL (A2C/DDPG/PPO; finrl/agents/stablebaselines3/models.py:11-13) hisse al/sat/tut aksiyonu; eğitim finrl/train.py [K] | - | MIT |
| `ai4finance-foundation/finrl-meta` | RL ortamları (DRL): agents/stablebaselines3_models.py:6-9 A2C/DDPG/PPO/SAC; ajan al/sat aksiyonu seçer, geçmiş fiyatla eğitilir [K] | eğitim/test bölmesi; canlı yok | MIT |
| `ai4finance-foundation/finrl-trading` | FinRL-X: src/strategies/rl_model.py + universe_manager.py (RL + evren seçimi) [R] | - | Apache-2.0 |
| `aithos-rr/ai-agent-for-trading` | 4 LLM ajanı (her biri 1.000 $) Hyperliquid testnet'te perp işlem açar/kapatır (README:1; src/aiat/config/settings.py:54 sağlayıcı seçimi) [R] | 4 ajan x 1.000 $ | yok |
| `aksaayyy/ai-bot-earn-or-die` | 10 ajan, genom (stop/TP vb. parametre) ile kural tabanlı işlem; LLM yok (triage LLM=0) [R] | 10 ajan x 1.000 USDC (README) | MIT |
| `aleksnovo/freqai-3ai-strategy` | ÜÇ ML modeli: Ai1 giriş ÜRETİCİ (LightGBM, FreqAI, çift başına), Ai2 giriş FİLTRESİ (tek XGBoost, 64 özellik), Ai3 çıkış YÖNETİCİSİ (3 kademeli çıkış, XGBoost+rejim) [K] | GOOD_ENTRY: maks kâr ≥ +%0,75 (Arbiter.py:106) | GPL-3.0 |
| `alex-jb/orallexa-ai-trading-agent` | ML + RL sinyali: engine/rl_agent.py:4 PPO (stable-baselines3, çok tohum seçimi :221), engine/ml_signal.py:5 RF/XGBoost (5 gün ileri etiket :40); LLM strateji KODU üretip kum havuzunda çalıştırır (strategy_evolver.py:159-268) [K] | forward_days=5; PPO 20.000 adım | MIT |
| `alexandrelamure/auto-trade` | Yerel LLM (Ollama) 'yatırım komitesi' Alpaca paper hesabında alım-satım yapar, 30 günlük PnL hedefi (README:1) [R] | - | yok |
| `i_alphastrike (clawinfra)` | Fonlama/OI/long-short oranından karşıt sinyal özellikleri (src/features/alternative_signals.py:390-500) [Ö §1.8] | - | lisans yok |
| `alsk1992/cloddsbot` | inapp-mobile/clodds ile aynı kod tabanı (aynı dosya yolları) [K] | - | MIT |
| `ampyfin/ampyfin` | NASDAQ-100: birçok klasik strateji sınanır; ML modeli (TradeSim/training.py:50 train) [R] | - | yok |
| `aplicy-com/guarded-trader` | LLM aday strateji/kod önerebilir, tüm emirleri Freqtrade sert limitlerle verir (README:1; docs/05-adr/0007-candidate-code-admission.md) [R] | - | Apache-2.0 |
| `aria-tjr/llm-crypto-hyperopt` | LLM duygu + hiperparametre optimizasyonlu portföy stratejileri, Bybit perp, 100 varlık (README:1) [R] | haftalık/saatlik hyperopt | MIT |
| `aristidesai/ibkr-aihedge` | IBKR + LLM analizi ile karar (config.py:34 model_provider) [R] | - | MIT |
| `asavinov/intelligent-trading-bot` | ML SİNYAL ÜRETİCİ: etiketler 'highlow2' (üst/alt eşiğe önce dokunma; configs/config-sample-1h.jsonc:46-48), ML skoru -> `threshold_rule` buy=+0,08 / sell=-0,08 (:90-95), grid 0,01..0,10 (:148-149); label_horizon=24 (:21) [K] | eşik ±0,08; ufuk 24 | MIT |
| `i_autonomous-equity-trading-system (RayanBatada)` | Tohum topluluğu (aynı tarif farklı tohum; src/sma/model/ensemble.py:66-120) [Ö] | - | tüm hakları saklı |
| `ayrtondavoli97/neural_trader_v7` | Otomatik tahmin üreten sinir ağı botu (Telegram bildirimi; README:1) [R] | - | MIT |
| `bachhsunkid/agent-to-earn` | Her gece Claude Code araştırma döngüsü yeni strateji ÖNERİR; deterministik kapı karar verir (README:1) [R] | - | MIT |
| `backtest-kit/backtest-ollama-crontab` | Ollama + cron ile LLM backtest/sinyal örneği (README) [R] | - | yok |
| `baran0732/ai-crypto-trader-pro` | README: trend takibi, 'self-learning' iddiası, 678+ coin; kod dosyası yok (0 kaynak) [K-yokluk] | - | MIT |
| `benpomme/agentictrading` | Otonom araştırma+kâğıt işlem 'fabrikası': LLM ajanları strateji adayı üretir (README:1); işlem değil strateji önerir [R] | ailelerin ≤5, challenger ≤3, canlı kalıcı kapalı (artifacts/paper_promotion_policy_v2.md:11-20) | AGPL-3.0 |
| `bhtbwh/ai-trader` | LangGraph çok-ajan tartışması, A-hisse simülasyon hesabı; kural motoru çift yol (sert + yumuşak) [R] | - | yok |
| `bijectivelabs/bitra` | Araştırma/tahmin ajanları (öneri sayılmaz): forecast/calibration.py:52 Platt kalibrasyonu; strategy/harness.py:123 walk-forward `core.fit` [K] | - | MIT |
| `captainnahin/trading-bot` | Deterministik tarama + LLM yalnız ÖNERİ üretir ('recommendations', gerçek veriden; README:1) [R] | - | yok |
| `chase-mew/ai-hedge-fund` | LLM (Claude) 4 saatte bir ÖNERİR, kod yürütür/reddeder ('Claude proposes, code disposes'); karar defterlenir/puanlanır (README:1) [R] | 4 saat | MIT |
| `chrisleekr/binance-trading-bot` | Kural tabanlı Binance botu + backtest kapısı (apps/web/.../gate-candidate.ts); ML/LLM karar çekirdeği değil [R] | - | Apache-2.0 |
| `chrisworsey55/atlas-gic` | 25+ LLM ajan 4 katmanda her gün tartışır (README:17) [R] | 25+ ajan | MIT |
| `codeptor/peri` | Hyperliquid'de LLM tek 'beyin': analyst.py:215 {"kind":"open",market,side,conviction}, engine.py:1394 açma; tam bağlam istemi [K] | conviction alanı | yok |
| `conjason/binance-alpha-miner` | RL ile yorumlanabilir FAKTÖR FORMÜLÜ arar (token dizisi=özellik+operatör, StackVM; README:1; train_binance.py:6 reward-mode standard); işlem önerisi değil faktör keşfi [K] | - | AGPL-3.0 |
| `o_ct-proje (sahibin)` | ML/LLM yok (grep sklearn/anthropic boş): Hyperliquid Form Radarı v1.1 kural tabanlı kopya seçimi, eşikler kilitli (README:1-9) [K] | kadro 30 = ilk 11 + yedek 19 | sahibin projesi |
| `cyberwei922/ai-trader-paper` | Binance spot dry-run, FreqAI modeli (tests/test_project.py:38 live_retrain_hours ≥ 6) [K] | 100 USDT, 6 saat | GPL-3.0 |
| `Dahshan228/FTMO-TradingBot` | FTMO MT5: 3 bağımsız strateji botu, ML KAPI/filtre modeli (src/model/train.py) [K-dosya] | MIT | MIT |
| `danderson197874/apex-crypto-bot` | 5 katmanlı sinyal (Momentum, Arbitraj, ML, Duygu...) ağırlıklı füzyon (bot.py:344 momentum 0,28, arbitraj 0,15, ml 0,24) [K] | - | yok |
| `danny123-sudo/regime-trading-bot` | Rejim bilinçli KuCoin/Freqtrade botu; Grok döngü içi TEYİT katmanı (veto benzeri) + 'strateji konseyi' (README:1; council/sign_proposal.py) [R] | - | MIT |
| `dax-523/ai-trading-agent` | LLM ajanı (app/agent.py:4 OpenAI) Lighter'da SANDBOX/TESTNET/LIVE işlem; öğrenme yok [R] | başlangıç 1.000 $ sahte | yok |
| `i_deepalpha (stefanoviana)` | Saf numpy HMM rejim (regime_detector.py:28-272); TFT/GNN modelleri 2 GB sunucuya uygun değil [Ö] | - | MIT |
| `deuteriumzzz/bitbotby` | 16 LLM sağlayıcı zinciri + SAC RL sinyali (ai/dqn_signal.py:1-6: OBS_DIM=21, {action, confidence, source='sac'}) + Amazon Chronos tahmini (ai/chronos_analyzer.py:32) [K] | OBS_DIM=21 | MIT |
| `dexoryn-china/polymarket-arbitrage-bot` | Polymarket: çok-model LLM topluluğu olasılık tahmin eder, işlem açar (README:1) [R] | - | yok |
| `dexorynlabs/polymarket-ai-agent-trading-bot` | Üsttekiyle aynı kod tabanı (aynı dosya adları/satırlar) [K] | - | yok |
| `dietmarwo/autoresearch-trading` | LLM ile otonom strateji keşfi (Karpathy autoresearch esinli; README:1) [R] | - | MIT |
| `dukesan-ai/crypto-ml-trading-framework` | AFML metodolojisi: meta-etiketleme (labeling/meta_labeling.py) = filtre/boyut modeli, mikroyapı alfa, rejim modeli, kayma farkında araştırma (README:1) [K-dosya] | - | MIT |
| `dukesky/allpath-trading-agent` | LLM ajan, araç kaydı (agent/memory_tools.py, reflection_tools.py) [R] | - | MIT |
| `dvampire/finagent` | Çok-modlu LLM ajanı (hisse/kripto, A* FinAgent): getiri 'low/high-level reflection' ile karar (configs/exp/trading_mi_w_low_w_high_w_decision/MSFT.py:32-39,114-115) [K] | top_k=5, previous_action_look_back_days=14 (MSFT.py:27-28) | MIT |
| `el-bach/claude-trader` | Claude API + MT5, 14 uzman ajan (günlük strateji, makro...) kendi başına işlem [R] | 14 ajan | MIT |
| `erfaniaa/llm-auto-trader` | LLM aksiyon kümesi: src/llm/prompts.py:22 `open_long\|open_short\|close\|adjust_sl\|adjust_tp\|add_to_position\|reduce_position\|hold` (çıkış yönetimi dahil); deterministik risk katmanı LLM'i sınırlar [K] | - | MIT |
| `etrobot/open-alpha-arena` | nof1 esinli LLM kripto botu (frontend SettingsDialog.tsx:373); karar LLM'de [R] | - | yok |
| `eugmsub/robinhoodagentictrader` | Claude MCP bağlayıcısıyla LLM doğal dilde işlem ÖNERİR; ayrı saf (LLM'siz) katman limitleri uygular (README:1) [R] | - | MIT |
| `filipethome/the-trader-bot` | Binance USDT çiftleri analiz eder; emir YALNIZ 'order gate'ten geçer (Vibe-Trading'den taşınmış); LLM danışman (bot/advisor/calibration.py) [K-dosya] | - | yok |
| `finstep-ai/contesttrade` | Olay güdümlü hisse SEÇİMİ: araştırmacı ajanlar + LightGBM tahminci (contest/researcher/lightgbm_predictor/train_model.py:34) [K] | - | Apache-2.0 |
| `flukelaster/ai-trading-agent` | MT5 (GOLD/OIL/BTC/USDJPY): LightGBM sinyal modeli sembol başına eğitilir (frontend/app/ml/page.tsx:193) + quant + LLM üçlü onay: ai/confirmation_gate.py:6-110 (ML güveni>0,6, required=3 onay) [K] | ML güven>0,6; onay=3 | yok |
| `i_forex-gold (MooreSi)` | Strateji başına meta-etiket kapısı (reversal_engine/meta_label.py:1-30: 'hiçbir şey alma'ya yakınsayan kapı üreticiye dair hükümdür'; etiket='işlem kendi maliyetini aştı mı' :62-76) [Ö §1.3] | - | AGPL-3.0 |
| `freqtrade/freqtrade` | FreqAI: strateji `&-` hedefi (ör. getiri) tahmin ettirir, giriş/çıkış kuralını strateji dosyası yazar (docs/freqai-feature-engineering.md:137; strategy/interface.py:254 populate_entry_trend, :446 custom_stoploss) + RL tabanı (freqai/RL/BaseReinforcementLearningModel.py, prediction_models/ReinforcementLearner.py) [K] | DI_threshold; do_predict | GPL-3.0 |
| `gaaiyun/freqtrade-strategy-generator` | Tek cümleden Freqtrade IStrategy KODU üreten LLM (scripts/llm_generator.py:11); işlem değil strateji kodu önerir [K] | - | yok |
| `gacord1213-arch/alpaca-ai-trading-agent` | Claude 'beyin', Alpaca emirleri (mcp_bridge.py:7); öğrenme yok [R] | - | MIT |
| `gajesh2007/ai-trading-agent` | LLM (TAAPI verisi) -> Hyperliquid işlem kararı (src/agent/decision_maker.py:23) [R] | - | yok |
| `galleonlabs/hypergrok-trading-desk` | 7 rol (fikir->kanıt->risk onayı->SİZİN onayınız->tek gönderim->inceleme); LLM öneri, insan onay (README:1) [R] | - | MIT |
| `garagesteve1155/PowerTrader_AI` | Özel fiyat tahmin yapay zekâsı + kademeli DCA; tam otomatik (README:1) [K-dosya] | Apache-2.0 | Apache-2.0 |
| `giansn/sygnif` | Otonom BTC sistemi (3 süreç, Bybit demo); ec2-snapshot/services/sygnif_training_scanner.py eğitim tarayıcısı [R] | - | yok |
| `gotji253/ai_trading_ada` | Hermes ajanı + Manager/Alpha/Risk/Execution çok-ajan, ADA işlemleri [R] | - | yok |
| `guixu-project/guixu` | Rust ajan çatısı (ZJU), LLM iz içe aktarıcı (crates/node/src/main.rs:330); ticaret/öğrenme döngüsü doğrulanmadı [R] | - | Apache-2.0 |
| `hammergpt/hyper-alpha-arena` | LLM karar şeması `operation: buy\|sell\|hold\|close` (backend/services/ai_decision_service.py:483), 'Program' yolu (program_execution_service.py:709) [K] | - | Apache-2.0 |
| `henryzhangpku/autonomous-quant-researcher` | LLM yalnız HİPOTEZ önerir (sabit sözlük içinde), deterministik değerlendirici kabul eder: keşif->doğrulama->tek kullanımlık holdout duvarı (README:1-12); işlem önermez [K] | arXiv:2611.06607 makalesi | MIT |
| `hkuds/vibe-trading` | Ajan strateji/backtest üretir; canlı için ajan 2-4 'mandate' profili ÖNERİR (hesabın izin verdiğine kısılmış), insan imzalı limitler (wiki content.en.js:813) [K] | - | MIT |
| `hsliuping/tradingagents-cn` | TradingAgents Çince fork: A-hisse araştırma yardımcısı, emir yok [R] | - | Apache-2.0 |
| `imsatoshi/genetrader` | Genetik algoritma ile STRATEJİ PARAMETRESİ optimizasyonu (README:1); geçmiş veri [R] | - | MIT |
| `inapp-mobile/clodds` | Claude sohbet terminali, 118+ strateji; ML sinyal modülü trading/ml-signals.ts:97 türü simple\|ensemble\|xgboost_python [K] | - | MIT |
| `ishieldi/alphaswarm` | README yok; improve/outcome_analyzer.py sonuç çözümleyici; sistem amacı belirsiz [R] | - | yok |
| `islambaraka90/super-agent-trading-bot` | TypeScript, olay güdümlü LLM ajanı: 1 dk-1 hafta mumlarda fırsat görünce işlem (README:1) [R] | - | MIT |
| `jackson-video-resources/claude-tradingview-mcp-trading` | Claude, TradingView grafiğini okur ve Bitget'te işlem yapar; her koşul 'güvenlik kontrolü'nden geçer (README:1) [R] | - | yok |
| `jerome-benoit/freqai-strategies` | İki karar modeli: QuickAdapter (XGBoost, zigzag uç noktası rejresyonu, kalibre uç noktalarda giriş) ve ReforceXY (MaskablePPO, nötr/giriş/çıkış aksiyonlarını RL politikası seçer) (README:7-8) [K] | 5 dk spot dry-run; HPO açık | yok |
| `jgardet/evotrade` | LLM Freqtrade stratejisi ÜRETİR + backtest + yinelemeli geliştirir (README:1) [R] | - | özel/belirsiz |
| `julian-dev28/pathiel` | Hyperliquid MCP + Claude Code eklentisi, 30 araç; emir bracket.py üzerinden (bracket.py:5) — Claude karar verir [K] | - | MIT |
| `kairospan/gravit-agent` | Yatırım deneyimiyle büyüyen kişisel ajan (araştırma + kâğıt işlem; README:1) [R] | - | Apache-2.0 |
| `kaoi-cyber/ai-trader` | Claude portföy yöneticisi: piyasayı araştırır, ABD hisse/ETF/kripto al-sat (brain.py:6, README:1) [R] | - | MIT |
| `kojott/llm-trader-test` | DeepSeek ile çok-varlık karar botu + backtest (backtest.py:3) [R] | - | yok |
| `kyky2347/alta` | LLM ajanlarıyla yönetilen sanal ticaret platformu: tarayıcı/fırsat ajanları (README:1) [R] | - | Apache-2.0 |
| `kylinmountain/tradingagents-ashare` | TradingAgents A-hisse forku, 14 ajan çok-boğa/ayı; emir yok [R] | - | Apache-2.0 |
| `leadline88/binance-ai-trader` | README: 'sürekli öğrenir'; kaynak dosya yok [K-yokluk] | - | yok |
| `llmtrader` | x_qrak_LLM_trader ile AYNI kod (aynı dosya yolları) [K] | - | MIT |
| `lnstt369/nightwatcher-v2` | Cloudflare Workers üzerinde çok-ajan Alpaca sistemi, LLM karar (README:1) [R] | - | MIT |
| `lumiwealth/lumibot` | LLM ajanı karar verir (components/agents/chatgpt_llm.py:34 remember); kodla zorlanan limit yok (yalnız istem) [O] | - | GPL-3.0 |
| `ma-pony/cryptotrader-ai` | Kronos + 4 LLM ajan komitesi + özel bileşenler ayrı sinyal kaynağı, web'den ayarlanabilen güven ağırlıklarıyla füzyon (README:1); kronos.py:294 predict_proba kapı sınıflandırıcı [K] | - | MIT |
| `maazullah8/ai_self_improving_bot` | 'Kendini geliştiren' 7/24 bot için araştırma çatısı: veri->tekrar oynatma->strateji->risk (README:1); ai/generator.py LLM strateji üretici [K-dosya] | - | yok |
| `mad1kow-cloud/crypto-intelligence-agent` | Tek dosya (agent.py) Claude ile otonom işlem ('this one trades', README:1) [R] | - | yok |
| `maotouhu/nof1openai` | AITradeGame: LLM işlem simülatörü (ai_trader.py:3) [R] | - | MIT |
| `marigold/universal-portfolios` | Çevrimiçi portföy seçimi (OLPS) algoritmaları (universal/algos/mpt.py:146-147 kovaryans/getiri `fit`); portföy ağırlığı önerir [K] | FMIT lisansı | MIT |
| `markdregan/freqai-marcos-lopez-de-prado` | Freqtrade çatalı: AFML stratejileri FreqAI'ye taşıma hedefi (README:1), RL taban sınıfları (freqai/RL) [R] | GPL-3.0 | GPL-3.0 |
| `markfans/cryptoquant-ai` | Yerel kantitatif panel + isteğe bağlı OKX yürütme (README:1) [R] | - | MIT |
| `maxwellcm92/darwinfi` | Zincir üstü (Base L2) strateji popülasyonu rekabet eder, en güçlüsü işlem yapar (README:1) [R] | - | MIT |
| `michi883/trade-cast` | Gemini + Google ADK ile otonom izleme listesi taraması + karar + medya (README:1) [R] | - | MIT |
| `microsoft/qlib` | ML ALFA MODELLERİ: skor üretir (portföy), işlem açmaz; çok model (LightGBM, ağlar) [K-dosya] | - | MIT |
| `microsoft/rd-agent` | LLM ajan faktör/model Ar-Ge ÖNERİR (rdagent/components/proposal; CoSTEER evolving_strategy.py) — işlem değil model/faktör kodu [K-dosya] | MIT | MIT |
| `mikegianfelice/hunter` | Solana token tarayıcı + LLM dinamik strateji seçici (src/ai/ai_dynamic_strategy_selector.py) [R] | - | Apache-2.0 |
| `millw14/merrymen` | Barındırılan/yerel ajan platformu (2.737 dosya): kullanıcı ajan yaratır, piyasa/limit seçer, kararları izler (README:1); LLM karar [R] | - | yok |
| `mnemox-ai/tradememory-protocol` | Ajanlara kalıcı işlem belleği MCP sunucusu; evrim motoru mcp_server.py:1037 evolution_evolve_strategy [K-dosya] | - | MIT |
| `mocasus/trade-agent` | Eklenti mimarili LLM ajan: LLM piyasa+haber+gösterge -> karar -> emir (README:1) [R] | - | MIT |
| `mogons/noraz-agent` | Robinhood Chain memecoin LLM ajanı [R] | - | MIT |
| `mohamed-sm/freqtrade-rlstrategy-ia` | FreqAI + RL: RL ajanı giriş/çıkış kararı verir (RLStrategy.py:272-287; README:1) [K-dosya] | - | yok |
| `moss-site/moss-trade-bot-skills` | Ticaret botu fabrikası: 'evrim mekanizması' ile parametre önerisi (scripts/run_evolve_backtest.py, scripts/ambush/propose.py) [K-dosya] | - | MIT |
| `muzafferkadir/claude-crypto-trader-public` | 3 AI karakter her saat al/sat kararı verir, 10.000 $ sahte (README:1) [R] | 3 x 10.000 $ | yok |
| `neillbotushanski/alphaforge` | ABD hisse: sinyal arar, çoklu-test düzeltmesinden sağ çıkanları tutar (README:1); kaynak dosya yok [K-yokluk] | - | yok |
| `neryaai/nerya` | Yerel ajan strateji çalışma alanı: araştırmacı/strateji yazarı/inceleyici ajanlar strateji yazar+backtest (README:1) [R] | - | özel/belirsiz |
| `nikhilperr/binance-futures-trading-bot` | Ücret bilinçli, kilometre taşı bazlı bileşik büyütme sistemi ('$10 -> $100', README:1); kural tabanlı [R] | - | MIT |
| `nofiix/openclaw-workspace` | Polymarket fabrikası: stratejiler (POLY_FACTORY/strategies/poly_no_scanner.py) + Telegram [K-dosya] | - | yok |
| `nofxaios/nofx` | LLM aksiyonları open_long/open_short/close_long/close_short (trader/auto_trader_decision.go:283); 10+ borsa [K] | AGPL-3.0 | AGPL-3.0 |
| `oficcejo/alpha-arena-okx` | DeepSeek ile OKX 15 dk işlem; 2 haftalık deneme: toplam özsermaye 'neredeyse değişmedi' (README:1) [R] | - | yok |
| `oficcejo/okx-2pa-agent-web` | OKX kripto + TradFi (altın, petrol, hisse) piyasa verisiyle OpenAI-uyumlu LLM karar verir (README:1) [R] | - | AGPL-3.0 |
| `oft3r/agentic-trading-desk` | Hisse/ETF kısa vade teknik analiz için AI ajanı + portföy yönetimi masası (README:1); insan etkileşimli [R] | - | MIT |
| `olaxbt/ai-market-maker` | 'Küçük profesyonel firma' tarzı LLM ajan çok-ajan sistemi (AGPL) [R] | - | AGPL-3.0 |
| `open-finance-lab/agentictrading` | FinAgents: ajan prototipleme/backtest/karar günlüğü deney platformu; orchestration/FinAgents/orchestrator/core/rl_policy_engine.py RL politika motoru [K-dosya] | - | özel/belirsiz |
| `openbyteinc/quantdinger` | AI hızlı analiz skoru (backend_api_python/app/services/fast_analysis_scoring.py:122) + çok-LLM; strateji evrimi servisi [K-dosya] | - | Apache-2.0 |
| `parkseokjune/overfit-slayer` | Kural tabanlı swing botu (SMA çaprazı/supertrend); LLM/ML karar yok | - | yok |
| `pettekay/ai-forex-trading-bot` | MT5: LLM bull/bear tartışma masası + ML meta-label kapısı: ml/meta_label.py:212-243 kalibre LightGBM (RF yedek), kendi bellek kayıtlarından eğitilir [K] | MIN_SAMPLES=30, MIN_SAMPLES_PER_REGIME=15, geriye 180 gün (meta_label.py:42-43,292) | MIT |
| `phichleng/tradinggpt` | Deterministik ICT/SMC motorları + strateji seçimi + aşılamaz risk kapısı; LLM RAG günlük arama (README:1; backend/app/selection/selector.py) [R] | - | yok |
| `pipiku915/finmem-llm-stocktrading` | LLM ajanı katmanlı bellekle hisse al/sat/tut (FinMem, README:1) [R] | - | MIT |
| `i_polymarket-btc-15-minutes (masterputra169)` | Meta-etiket (al/alma) modeli, birkaç yüz çözülmüş bahisle; elle yazılmış çıkarım (backtest/ml_training/mltrain/meta_eval.py:76-135) [Ö §1.2] | - | MIT |
| `polymarket/agents` | Polymarket resmi ajan çatısı: LangChain LLM işlem önerir/yürütür (agents/application/executor.py:11) [R] | - | MIT |
| `qingshungli/super-nof1.ai` | nof1 klonu: LLM karar; istem 'bakiyenin %15-25'i, güvenle 20-25x' önerir (lib/ai/prompt.ts:97) [K] | %15-25 bakiye, 20-25x | MIT |
| `qrak/LLM_trader` | Çok-modlu LLM 1920x1080 grafik + sayısal göstergeler + KENDİ kapanmış işlem belleği ile kararı verir, sonra deterministik kurallar denetler; kâğıt (README:1; BTC/USDC 4 s) [K] | MIT; 2.804 test | MIT |
| `quantiaai/helm-agents` | LLM ajanları tartışır, riski stres test eder, tek karara yakınsar (README:1) [R] | - | Apache-2.0 |
| `rafaelpf07/evotrader` | Genetik programlama ile KENDİ strateji kuralını evrimleştirir; ML sinyali yapı taşı olarak kullanabilir; ABD ETF kâğıt (README:1) [K] | - | yok |
| `rgg81/crypto-trade-claude-code` | Watcher ~10 uzun/kısa aday önerir (sembol seçimi) -> 4 analist -> boğa/ayı tartışması -> yargıç -> trader emri (README:1-60; SKILL.md:37-42); LLM 'akıl yürütür', matematik/risk/yürütme Python [K] | 4 saatte bir; lisans YOK | yok |
| `ricardokarma/claude-trading-bot` | Piyasa tarama, favoriler, kurulum sıralama, ısı haritası; 'self-improving analysis' (README:1) [R] | - | MIT |
| `roclee2692/autonomous-spot-trading-agent` | Binance BTC/USDT düşük frekanslı, açıklanabilir 'anayasa-öncelikli' harness [R] | - | yok |
| `rp7o/trade-foundry` | LLM araştırma döngüsü strateji HİPOTEZİ önerir (research/validation/proposer.ts); işlem açmaz [R] | - | MIT |
| `ruiwang20010702/cryptobot` | 8 LLM rolü piyasa analiz + sinyal üretir, Freqtrade yürütür; 16 veri kaynağı (README:1) [R] | - | AGPL-3.0 |
| `ryan-yuuu/crypto-trading-arena` | Ajanlar Coinbase/Binance canlı fiyat akışıyla yarışır (README:1) [R] | - | Apache-2.0 |
| `ryanfrigo/kalshi-ai-trading-bot` | 'İşlem seçen LLM' değil, edge ölçüm araç takımı (Kalshi) (README:1) [R] | - | MIT |
| `samsoncukor06/agentic-trader` | LLM ajan 8 hafta (Haz-Ağu 2026) küçük GERÇEK para hesabında günde 4 kez hisse araştırıp işlem yaptı; sonuçta 'hisse edge'i yoktu' (README:1) [R] | 8 hafta, 4/gün | yok |
| `senpi-ai/senpi-skills` | Hyperliquid ajan çatısının açık katmanı: strateji şablonları + tarayıcı skorlama (strategies/*/main/scanners/scoring.py) kural tabanlı; LLM ajanı şablonu çalıştırır [K-dosya] | - | MIT |
| `shiyu-coder/kronos` | K-çizgisi temel modeli (hiyerarşik jeton + otoregresif Transformer, README:1); FİYAT TAHMİNİ üretir, işlem önermez; sinyal kaynağı olarak başka botlara takılır (ör. cryptotrader-ai kronos.py:294) [K] | MIT | MIT |
| `shoaibghulam/binance-ai-bot` | 5 strateji botu (gün, scalp, grid, DCA, rebalans) top-30 hacimli coini TARAR; ML YALNIZ veto kapısı (min_win_prob 0,55, app/ml/trainer.py:47) [K] | min_win_prob=0,55 | MIT |
| `snowcheetos/automoonbot` | Algoritmik işlem uygulamaları; moonpy/model/memory.py + reward/ RL benzeri bileşenler [R] | - | MIT |
| `solohard32/mexc-ai-bot` | MEXC spot botu, risk-guard, parametre otoadaptasyonu [R] | - | MIT |
| `sorry510/go_binance_futures` | Yerel seçici v2 (controllers/local_selector.go) + ajan bellek (agent_memory.go); LLM ajan modülü (doc/agent/v2..v4) [K-dosya] | - | MIT |
| `superalgos/superalgos` | Görsel kripto platformu; Projects/TensorFlow/.../Learning-Bot (TensorFlowModelsManager.js, MLDataManager.js) ML öğrenme botu modülü [K-dosya] | - | Apache-2.0 |
| `superior-trade/trading-terminal` | Grafiğe çizdiğiniz görüşü AI'ın giriş/stop/hedefli kuruluma çevirir ve daha fazla kurulum SIRALAR (README:1) [R] | - | Apache-2.0 |
| `suyunjing-su/r20-quantum-trader` | Astra'nın eski sürüm aynası (scripts/self_improvement_engine.py, scripts/evolution/memory_review.py aynı dosyalar) [K-dosya] | - | MIT |
| `TauricResearch/TradingAgents` | Çok-ajan LLM araştırma/karar çatısı; EMİR YOK (analiz kütüphanesi) [O] | Apache-2.0 | Apache-2.0 |
| `tensortrade-org/tensortrade` | RL ajanı eğitme çatısı (examples/training/train_walkforward.py, train_profit.py); canlı değil [K-dosya] | Apache-2.0 | Apache-2.0 |
| `the-finai/fincon` | FinCon (NeurIPS 2024) kavramsal sözlü pekiştirme çok-ajan; KOD YAYIMLANMAMIŞ: README 'açık kaynağa 3-4 ay içinde' diyor [K-README] | - | MIT |
| `the-swarm-corporation/autohedge` | LLM sürü ajanları uçtan uca analiz/risk/yürütme (README:1) [R] | - | MIT |
| `tiramisuice/ai-trader` | 10 ajan aynı veri/araçla, persona/model farkıyla ABD ve Tayvan hissesi işlem yapar (README:1) [R] | 5x10.000 $ + 5xNT$300.000 | MIT |
| `torchtrade/torchtrade` | RL çatısı: PPO, DQN, IQL, GRPO, DSAC (README:31) + yerel LLM aktörünü KENDİ verinizde GRPO/SAO ile ince ayar (README:37); bandit/OneStepEnv [K] | - | MIT |
| `traderalice/openalice` | Yerel çalışma alanı: AI ajan + araçlar + işlem hesapları; 'tez gözetimi' [R] | - | AGPL-3.0 |
| `i_tradingbot (zero-was-here, Aurum v2)` | ML stratejisi: aurum/strategies/ml.py (Platt eğimi a≥0 kısıtı :399-423; beceri kapısı :810-837); üçlü bariyer etiket + teklik ağırlığı (labels/triple_barrier.py:538-687) [Ö: ml-guclendirme-plani §1.1] | - | MIT |
| `vedv0987-cloud/bvedtrade` | NVIDIA NIM çok-model AI: tarayıcı, TA, SMC; 29 aşamalı plan (README:1) [R] | - | yok |
| `virattt/ai-hedge-fund` | LLM 'kişilikleri' (Buffett vb.) sinyal verir; portföy yöneticisi birleştirir; emir yok [O] | - | MIT |
| `vishalsaraswat047/apha-tb` | AI Studio uygulaması; src/lib/observatory/learning_engine.ts öğrenme motoru dosyası [R] | - | yok |
| `web3spreads/quant-flow` | LLM yalnız yapılandırılmış JSON karar üretir; emir, TP/SL, risk deterministik kod (README:1; engine.py:441 `action`, trading/grid_manager.py:207) [K] | - | yok |
| `wquguru/nof0` | Prompt-merkezli çoklu LLM arenası: LLM open_long/open_short (go/pkg/executor/utils.go:36, validator.go:18) [K] | - | yok |
| `wyc-dev/mats` | 'Kendi kendini evrimleştiren beyin': LLM grafik okur, istatistik denetler (README:1); Q-RL tablosu LLM'in denemeyeceği eylemleri keşfeder: evolution/q-rl-table.ts:1-5 ε-açgözlü Q tablosu, 'Aligned Shadow' ödülleriyle; index.ts:23,1942 [K] | Q-tablo 2000 yineleme (q-rl-table.ts:781) | Apache-2.0 |
| `xtra-computing/cryptotrade` | LLM ajan zincir üstü + zincir dışı veriyi birleştirir (akademik, README:1) [R] | - | özel/belirsiz |
| `yellowpancake/quant-autoresearch` | Ajan strateji değişikliği önerir->düzenler->değerlendirir->tutar/atar (README:1; config/reward.py) [R] | - | MIT |
| `ygwyg/mahoraga` | LLM yalnız haber/olay SINIFLANDIRIR (providers/llm/classifier.ts:9); giriş/çıkış kural + sert PolicyEngine [K] | - | MIT |
| `yi-111-a/alphaloop-crypto` | 7/24 kâğıt işlem 'evrim sistemi': strateji ajanı kendi git dalında evrimleşir (LOCKED/git_merge_executor.py, evolution_orchestrator.py) [K-dosya] | - | yok |
| `yizhisong/friestrader` | Ucuz/otonom Robinhood LLM ajanı; scripts/rank_candidates.py aday SIRALAMA (sembol seçimi) [K-dosya] | - | MIT |
| `yllvar/quant-autoresearch` | LLM+ArXiv ile hipotez/kod yazar, güvenli kum havuzunda doğrular (README:1) [R] | - | yok |
| `ymcbzrgn/hydraquant` | 'Bilişsel organizma': LinUCB bandit + ajan tartışması + çok model; konfidans kalibratörü (user_data/scripts/confidence_cali*.py), RL ortamı (rl_environment.py) [K-dosya] | - | GPL-3.0 |
| `zetryn-ai/ai-agent` | Solana memecoin verisini denetlenebilir karara çeviren çatı (README:1); LLM/ML yerine kural [R] | - | MIT |
| `zhulinsen/daily_stock_analysis` | A-hisse LLM analiz/uyarı; emir yok [R] | - | MIT |

## 4. Madde 2 — öğrenme döngüsü: olgusal özet (ayrıntı: Bölüm 5 tablosu)

**4.1 Terfi / emeklilik kapısı olan döngüler (sayılar kodda)**

| Repo | Ders/model ne zaman devreye girer | Eşik / kapı | Emeklilik / geri alma |
|---|---|---|---|
| rgg81 | Aday -> VALIDATED | ≥5 teyit **ve** DSR p ≥ 0,95 (`lessons.py:224-236`); retrieve k=5, kısıtlayıcı ≤3, recency 0,995^saat (`:93,114-117`) | `demote` teyitleri 0'lar (`:198-212`); retired kalıcı |
| qrak | Kayıp deseni dersi: ≥5 kayıp, kayıp oranı ≥0,6, taban ≥10 işlem (`brain_reflection.py:14-18`); kazanan yansıması ≥5 kazanç (`:74`) | kapı yok (sayı eşiği) | Kural emekli: karşıt ≥ max(3, destek/2) ve > doğrulama (`:33-58`); bellek çürümesi yarı ömür=tf/17 gün, ≤30 gün (`vector_memory.py:35-37`) |
| astra | Ders hemen canlı; yazma kapısı anayasa linter (`evolution_shield.py:154`) | **paper/gölge kapısı yok** [Ö]; isteme ≤8 ders (`:301`) | Kanıttan sağlık skoru, kötü ders arşivlenir (`:517`) |
| pettekay | LLM ders yazar, faydalılık puanı 0-1 eşik altı kaydedilmez (`reflection.py:7-24`); ML meta-label ≥30 örnek (`meta_label.py:42`) | ders puanı; ML: rejim başına ≥15 | memory decay/expire [K-dosya] |
| rafael evotrader | 63 işlem gününde bir yeniden öğrenme; zarar dersleri aday kural | 252 gün holdout'ta marj ≥0,10 (`learner.py:42-48`) | tutmayan ders atılır |
| parkseokjune | Aylık/uyarı ile yeniden kalibrasyon | komşu hücre medyan OOS>0; OOS Sharpe ≥ +0,15; öğrenme başına ≤1 parametre seti (`self_learn.py:1-12`) | her karar CSV'de |
| autoevolve | 5 ardışık kayıp, ≥30 işlem, soğuma 240 dk (`config_template.yaml:116-124`) | LLM kodu yeniden yazar | kazanma <0,35 veya düşüş >0,15 -> geri al (`:156-159`) |
| shoaib | 50 kapanan işlemle başla, her 25'te yeniden eğit (`trainer.py:30`) | AUC ≥0,55 (`:35`), min_win_prob 0,55 | AUC altı model devrede değil |
| FTMO | Haftalık/zamanlanmış eğitim -> kapı -> atomik terfi | yeni model görevdekinden >%10 kötüyse reddedilir (`retrain_scheduler.py:3-32`) [plan notu] | nöbetçi dosya, geri yükleme |
| aleksnovo | Ai2 ≥5000 örnek (`Arbiter.py:112`), Ai3 ≥1000 kapanmış işlem, pencere 5000 (`ExitModel.py:146-147`) | ilk model için ≥500 held-out (`Arbiter.py:131`) | 3 sürüm + .bak + otomatik geri alma (`ExitModel.py:30`) |
| hydraquant | gerçek sermaye kapısı | PnL>0, Sharpe>1, DD<%10, 0 tasfiye, ≥30 işlem, kazanma ≥%55, LinUCB var<0,1, otonomi≥1 (`promotion_gate.py:1-12`) | geçse de manuel onay |
| the-trader-bot | testnet -> canlı | 30 gün PnL>0, ≥MIN_LIVE_TRADES, ort R>0, Monte Carlo p95 DD (`promotion.py:1-18`) | - |
| bhtbwh, adamcyh evotrader | LLM yansıması öneri üretir | **insan onayı** (`approver.py:23`; `proposals.py`) | - |
| TradingAgents | ders yalnız Portföy Yöneticisine (`portfolio_manager.py:35-37`) | kapı yok; `as_of` sızıntı engeli (`log.py:93`) | - |

**4.2 Kapısız / zayıf kapılı döngüler:** peri (LLM kendi dersini yazar), mad1kow (her kapanışta 150 kelimelik ders), qingshungli (`prompt.ts:198` son 7 gün), hyper-alpha-arena (LLM kendi belleğini yazar), bitbotby (her 50 işlemde yeniden eğitim, atomik değiştirme, kapı yok), bvedtrade (`min_samples=2000`), gotji253 (kapı kodda ama `max_dd_ok = True  # Placeholder`, `validator.py:47`), apex (ağırlıklar **uzak paneldan** çekiliyor, `bot.py:348-357`), neural_trader_v7 (kendi tahminlerini eğitim setine ekler, `retrainer_v7.py`).

**4.3 Olgular**
1. **Kâr VE zarar:** qrak hem kazanan hem kaybeden yansıması (`brain_reflection.py:69-77`, `trigger_loss_reflection :145`, AI-hata :246) [K]; rgg81 winners vs losers + kaçırılan fırsat [K]; MATS her kapanışı öğrenir ama sistem kapanışlarını 0,3-0,5 ağırlıkla (`learning-weight.ts:1-25`) [K]; captainnahin kazanç yalnız kaydedilir, kayıp teşhis edilip nedene bağlı DO/DONT türetilir (asimetrik, `memory.py:1-20`) [K]; pettekay ders "kazanan benzer kurulum ders başına +5 puan" (`portfolio_manager.py:227`) [K].
2. **Dersin modele/istem'e enjeksiyonu:** istem enjeksiyonu: astra (`{{trading_memory}}`), rgg81 (sayısal bantlar kelimesi kelimesine), qrak (vektör bellek getirme), pettekay, qingshungli, mad1kow, peri, dukesky (ders bütçesi 1000, `review.py:187`), finmem/finagent (katmanlı bellek, top_k=5); TradingAgents yalnız PM. **Modele (ML) enjeksiyon / yeniden eğitim kendi işlemleriyle:** shoaib, bvedtrade, bitbotby, pettekay (aynı hafıza kayıtları meta-label'ı eğitir, `meta_label.py:292`), aleksnovo (sanal dosyalar), neural_trader_v7, FTMO. Metin dersini ML'yi beslemek için kullanan görülmedi; **pettekay** hem LLM dersini hem ML'yi aynı hafızadan besleyen tek örnek.
3. **Ders emekliliği:** rgg81 (demote/retire), qrak (karşıt kanıtla), astra (arşiv), flukelaster (gece süre dolumu/azalma, `consolidator.py:2`), finmem (üstel azalma 0,988, `decay.py:9`), MATS (ağırlık 0,1-3,0 EMA, `meta-learner.ts:165-170`).
4. **Kapı eşiklerinin büyüklüğü (olgu):** kapılı döngülerde en küçük örnek ölçütü 30 (hydraquant, autoevolve, MIN_SAMPLES pettekay), 50 (shoaib, cryptobot, mnemox), 500-5000 (aleksnovo, bvedtrade); sayısal istatistik kapısı kullananlar: DSR (rgg81), Monte Carlo p95 (the-trader-bot), holdout marjı (rafael), OOS Sharpe artışı (parkseokjune). Bizim ders-spec'in ilk kontrol noktası 30 işlem + z≥2 + ≥8 ayrı gün + ≥20 defter kanıtı; diğerlerinin çoğu bunun altında (tek işlem/ders) ya da aynı büyüklükte.
5. **Çevrimiçi/anlık güncelleme:** MATS meta-öğrenici (EMA 0,8/0,9, `meta-learner.ts:169-170`), apex ağırlıkları, bvedtrade LearningEngine (14 gün yarı ömür, `learning_engine.py:79`): ağırlık/çarpan anlık güncellenir; bizim planda "çevrim içi (her mumda) ağırlık güncellemesi yok" (ml-faz §8).
6. **Sahibin projeleri:** 1l3a `dersler.py`/`koc.py` kurallı (LLM'siz) ders = bizim ders-spec ile aynı felsefe (30 işlem, alfa 0,05); ct yalnız seçim isabeti ölçer.

## 5. Madde 2 — tablo (öğrenme döngüsü: yansıma/bellek/ders enjeksiyonu/yeniden eğitim/emeklilik/kapı/ML'yi besleme)

| Repo | Ne yapıyor (kod kanıtı) | Sayılar/varsayılan | Lisans |
|---|---|---|---|
| `0xethanq/astra-quant-agent` | Kalıcı yapılandırılmış ders kütüphanesi: scripts/evolution_shield.py:154 audit_proposed_lesson (anayasa linter), :499 publish_review, :517 refresh_health_from_evidence (kapanan işlem kanıtıyla sağlık skoru, kötü ders ARŞİVLENİR); isteme `{{trading_memory}}` MAX_INJECTED_LESSONS=8 (:301); günde 4 kez 02/08/14/20 (astra_backend/schedule_store.py:14). Kâğıt/gölge performans kapısı YOK, yeni ders hemen canlıya [K] | 8 ders/istem; 4 çalışma/gün | AGPL-3.0+CommonsClause |
| `0xsanei/darwinia` | Strateji evrimi (yalnız README/dosya adı) [R] | - | MIT |
| `195440/nof1.ai` | Yalnız son işlemler + Sharpe isteme (scheduler/tradingLoop.ts getTradeHistory/getRecentDecisions; tradingAgent.ts:393-440); ders/yansıma/kapı yok [K] | son 10-20 işlem, son 3-5 karar | AGPL-3.0 |
| `o_1l3a-proje (sahibin)` | Kapanan işlemlerden KURALLI ders: motor/canli/dersler.py:1-30 paper/canlı sonucunu backtest beklentisiyle kıyaslar (binom/Welch, MIN_ISLEM_DERS=30, ALFA=0,05, çoklu test düzeltmesi yok), 'altında' kabulü bozmaz ama canlıya geçirmez; motor/canli/koc.py:1-25 'Koç' LLM'siz şablon bulgular, Bonferroni, asgari 30 işlem, ASLA risk artırma/Kelly/kayıp sonrası ekleme önermez, değişiklik yalnız walk-forward + onayla [K] | ≥30 işlem; alfa 0,05 | sahibin projesi |
| `6kmfi6hp/ft-userdata-llm-share` | user_data/strategies/llm_modules/learning/self_reflection.py:11-317 SelfReflectionEngine (giriş/çıkış kalitesi, ders çıkarımı :270), trade_evaluator.py, rag_manager.py, pattern_analyzer.py; strateji dosyasında bağlı (…:42,99,138) [K] | - | MIT |
| `7thdrag0n/autoevolve` | İzle->tetikle->LLM analiz->kod yaz->deploy->izle->tut/geri al: config_template.yaml:116-124 ardışık kayıp=5, min işlem=30, soğuma 240 dk; :156-159 geri alma kazanma<0,35 veya düşüş>0,15; deploy aşaması subprocess başlatır (deployer.py:452-539); matris notu [Ö]: LLM'in yazdığı kod doğrudan çalıştırılıyor ve deploy sonrası işlem DB'si siliniyor | 5 kayıp; min 30; 240 dk | GPL-3.0 |
| `adamcyh/evotrader` | evolution/ içinde instruction_evolver.py, code_evolver.py, proposals.py (ProposalManager, md ön-madde); öğrenme önerileri İNSAN onaylı [K-dosya] | - | Apache-2.0 |
| `aenger-priv/contextualbandits` | Çevrimiçi öğrenme algoritmaları yalnız simülasyonda; kendi işlem verisi yok [R] | - | MIT |
| `ai4finance-foundation/finrl-meta` | Yeniden eğitim yalnız piyasa verisiyle (stablebaselines3_models.py:621 'Best Model Retraining'); kendi işlem sonucu yok [K] | - | MIT |
| `aithos-rr/ai-agent-for-trading` | Sonuç etiketleme: execution/outcome_resolver.py:1-6 (HOLD/FLAT kararı, tur-ücreti aşılmadıysa 'kârlı'); sonuçlar istemlere GERİ BESLENMİYOR (grep: yalnız db/ ve execution/ okuyor) -> ölçüm var, öğrenme yok [K] | - | yok |
| `aksaayyy/ai-bot-earn-or-die` | Darwin seçilimi: app/core/evolution.py:64 evolve_population(winners, survivors, losers) — kaybedenler yerine kazananların çaprazlanmış çocukları (:75-80); kapı/holdout yok [K] | - | MIT |
| `aleksnovo/freqai-3ai-strategy` | 'Paralel sanal günlük': Ai1'in HER sinyali 60 dk, onaylanan her giriş 360 dk izlenip diske yazılır (Ai2 reddetse de) -> hayatta kalma yanlılığı yok (README:1); yeniden eğitim Ai2 ≥5000 örnek (Arbiter.py:112), Ai3 ≥1000 kapanmış işlem, pencere 5000 (ExitModel.py:146-147), ilk model için ≥500 held-out (Arbiter.py:131), 3 sürüm + .bak + otomatik geri alma (ExitModel.py:30; Arbiter.py:23); varsayılan strategy_mode=module1_only (yalnız veri toplar), modlar module1_only→sleep→emulate→live [K] | 5000/1000/500 örnek | GPL-3.0 |
| `alex-jb/orallexa-ai-trading-agent` | Kaynak doğruluğuna göre füzyon ağırlığı: engine/dynamic_weights.py:4-20 (yetersiz geçmişte taban ağırlık, toplam yeniden normalize); platt_calibration.py; proposal_runner.py:43-62 öneri gerçekten daha iyiyse kabul; katmanlı bellek layered_memory.py:142 [K] | - | MIT |
| `alexandrelamure/auto-trade` | store/journal.py:1 kararları + sonradan mark-to-market sonucu saklar; istem tarafında okunduğu grep'te bulunamadı -> yalnız kayıt [K] | - | yok |
| `i_alphastrike (clawinfra)` | Model başına canlı isabet izleyici, rejime göre ağırlık (src/ml/quality_tracker.py:302-470) [Ö] | - | lisans yok |
| `alsk1992/cloddsbot` | Aynı: trading/ml-signals.ts retrain() [K] | - | MIT |
| `ampyfin/ampyfin` | Simüle sonuç -> sıralama -> canlı strateji ağırlığı zinciri (utilities/ranking_trading_utils) [O]; lisans yok | - | yok |
| `aplicy-com/guarded-trader` | Aday kod kabulü ADR (kabul kapısı); sonuç öğrenmesi yok [R] | - | Apache-2.0 |
| `aria-tjr/llm-crypto-hyperopt` | Hyperopt döngüleri (geçmiş piyasa verisi); kendi işlem öğrenmesi yok [R] | - | MIT |
| `asavinov/intelligent-trading-bot` | Yeniden eğitim yalnız piyasa verisiyle (train_length: 0 = tüm veri :23); kendi işlem sonucuna bağ yok [K] | MIT | MIT |
| `i_autonomous-equity-trading-system (RayanBatada)` | IC kapısı: geçmeyen model devreye girmez [Ö] | - | tüm hakları saklı |
| `ayrtondavoli97/neural_trader_v7` | scripts/retrainer_v7.py:1-15 kendi tahminlerinin değerlendirme dosyalarını (data/evaluations) eğitim setine (training_memory_extended.csv) ekleyip yeniden eğitir; terfi kapısı doğrulanmadı [K-dosya] | - | MIT |
| `bachhsunkid/agent-to-earn` | Kapılı terfi + soğuma süresi (docs/adr/0008-promotion-cooldown.md), nokta-zamanlı evren (0006) [R-ADR] | - | MIT |
| `baran0732/ai-crypto-trader-pro` | Yalnız README iddiası | - | MIT |
| `benpomme/agentictrading` | Aday -> kâğıt terfi politikası + soy emekliliği (factory/promotion.py; types/snapshot.ts retired_lineage_count); AGPL [K-dosya adı/politika belgesi] | env bayrağı FACTORY_ALLOW_AUTONOMOUS_PAPER_PROMOTION | AGPL-3.0 |
| `bhtbwh/ai-trader` | evolution/reflector.py:1-4 LLM yansıması -> EvolutionProposal; evolution/approver.py:23 HumanApprovalGate (insan onayı olmadan uygulanmaz); graph düğümü günlük aralıkla çalışır (agents/nodes.py:121-138) [K] | yansıma günde 1 (nodes.py:127-136) | yok |
| `bijectivelabs/bitra` | Sonuç değerlendirici ajan (agents/outcome_assessor), oturum kuralı continue/demote/halt (agents/session_rules.py:22), forecast/calibration kapı eşiği PLATT_ROWS [K-dosya] | - | MIT |
| `captainnahin/trading-bot` | services/memory.py:1-20: kazanç kaydedilir, kayıp önce teşhis edilir (services/postmortem.py), DO/DONT kuralları ölçülen neden kodundan TÜRETİLİR (yazılmaz); LLM kayıp teşhisi providers/llm/seekai.py:481 [K] | - | yok |
| `chase-mew/ai-hedge-fund` | fund/journal/store.py:200-208 TrackRecord: son kararlar + çözülmüş tahminlerin Brier skoru modele GÖSTERİLİR (yalnız geçmiş isabet); yansıma/ders yok [K] | - | MIT |
| `chrisworsey55/atlas-gic` | README:15-17,55-61: en kötü ajanın istemi yeniden yazılır, 5 işlem günü sonra Sharpe iyileşirse git commit kalır yoksa geri alınır ('istemler ağırlıktır'). Bu döngünün KODU repoda YOK: yalnız 6 .py (src/mirofish/*, src/janus.py); yalnız README iddiası [K-yokluk] | 5 işlem günü | MIT |
| `codeptor/peri` | LLM kendi dersini yazar: analyst.py:166-175 `{"kind":"remember","lesson":...}` ('yalnız kaydınızın desteklediği ders'); kalıcı bellek docs/memory/2026-09-07-learned-memory.md; yazım kapısı/emeklilik yok (grep) [K] | - | yok |
| `o_ct-proje (sahibin)` | Seçim isabeti ölçümü: copytrade/radar_isabet.py:1-17 7 gün önceki havuz/kadro ile sonraki 7 günün kopya getirisi, ≤30 kişilik sabit tohumlu rastgele karşılaştırma, kötü senaryo (kayma x2, gecikme 3 dk), süre bütçesi 30 dk; ders döngüsü/yeniden eğitim yok [K] | - | sahibin projesi |
| `cyberwei922/ai-trader-paper` | Zarardan sonra lot küçültme [O]; yeniden eğitim yalnız piyasa verisi | - | GPL-3.0 |
| `Dahshan228/FTMO-TradingBot` | scripts/retrain_scheduler.py:3-32,59,149-250: zamanlanmış yeniden eğitim -> hazırlık dizini -> kapı -> bozulma tavanı (yeni model görevdekinden >%10 kötüyse kapıyı geçse de reddedilir) -> nöbetçi dosyalı atomik terfi -> canlıya yeniden yükleme sinyali [K, plan notu §1.4] | bozulma tavanı %10 | MIT |
| `danderson197874/apex-crypto-bot` | Katman ağırlıkları kendi işlem sonuçlarıyla güncellenir, ama bot.py:348-357 ağırlıkları UZAK panelden (`/api/weights`) çeker (güvenlik riski); clamp_weights :146 [K] | - | yok |
| `deuteriumzzz/bitbotby` | ai/online_learner.py:188-208 'Mod B': her ONLINE_LEARNING_TRIGGER kapanan işlemde tam yeniden eğitim (:17 örnek 50), arka plan iş parçacığı, atomik os.replace ile sıcak değiştirme; terfi kapısı YOK [K] | tetik=50 işlem | MIT |
| `dexoryn-china/polymarket-arbitrage-bot` | analytics/calibration_feedback.py:131 `calibrator.fit(history)` + engine/loop.py:307 retrain_calibrator (kendi çözülen bahisleriyle); günlükte lessons_learned alanı storage/database.py:394 [K] | - | yok |
| `dexorynlabs/polymarket-ai-agent-trading-bot` | Aynı: kalibratör yeniden eğitimi engine/loop.py:307 [K] | - | yok |
| `dietmarwo/autoresearch-trading` | Deney döngüsü (README); kapı/holdout doğrulanmadı [R] | - | MIT |
| `dukesan-ai/crypto-ml-trading-framework` | docs/04-production-lessons.md üretim dersleri belgesi; model yeniden eğitim/terfi hattı doğrulanmadı [K-dosya] | - | MIT |
| `dukesky/allpath-trading-agent` | allpath_trade/reflect.py + agent/reflection_tools.py:32; agent/review.py:187 `_matching_lessons(ticker, budget=1000)` ders enjeksiyonu BÜTÇELİ; research/redteam/cases/memory.py hafıza zehirleme kırmızı takım testi; kapanan işlem günlüğü store/journal.py [K] | ders bütçesi 1000 | MIT |
| `dvampire/finagent` | Yansıma + FAISS bellek: prompt/trading/low_level_reflection.py, high_level_reflection.py; eğitim ve doğrulama döneminde ayrı yansıma şablonları (MSFT.py:32-39); bellek faiss.py:141 similarity_search; kapı/emeklilik yok [K] | bellek top_k=5 | MIT |
| `erfaniaa/llm-auto-trader` | src/llm/memory.py:86 son kararlar isteme gösterilir, kalıcı değil [K] | son 5 karar [O] | MIT |
| `filipethome/the-trader-bot` | bot/promotion.py:1-18 canlıya terfi: testnet son 30 gün net PnL>0 + MIN_LIVE_TRADES kapanmış R'li işlem + ort R>0 + Monte Carlo p95 düşüş < limit; pilot istisnası sermaye tavanı ile [K] | 30 gün testnet | yok |
| `finstep-ai/contesttrade` | LightGBM modeli kaydeder (train_model.py:62); kendi işlem sonucundan döngü doğrulanmadı [R] | - | Apache-2.0 |
| `flukelaster/ai-trading-agent` | Bellek: memory/consolidator.py:2 gece işi terfi/süre dolumu/azalma; mcp_server/agents/reflector.py; ml/trainer.py + ml/calibration.py; terfi kapısı yok (grep) [K] | - | yok |
| `i_forex-gold (MooreSi)` | Her sinyal sonuca bağlanır (alınmayanlar dahil); R-regresyon kapısı her yeniden eğitimde daha çok engelleyip %11'e inmiş; küme-dayanıklı t kanıt çıtası (edge_model.py:105-146) [Ö] | - | AGPL-3.0 |
| `freqtrade/freqtrade` | Canlı yeniden eğitim varsayılan live_retrain_hours=0 ('olabildiğince sık'), expiration_hours=0 (süresiz), purge_old_models=2 (docs/freqai-parameter-table.md:16-18) — yalnız PİYASA verisiyle, kendi işlem sonucu etiket değil [K] | GPL-3.0 | GPL-3.0 |
| `galleonlabs/hypergrok-trading-desk` | 'inceleme' rolü; otomatik ders enjeksiyonu doğrulanmadı [R] | - | MIT |
| `garagesteve1155/PowerTrader_AI` | pt_trainer.py:114-176 desen belleği + ağırlıkların sonuca göre güncellenmesi, kanıtı tutmayan zayıflar [K, plan notu §1.8] | - | Apache-2.0 |
| `giansn/sygnif` | Eğitim servisleri var; kendi işlemlerinden döngü doğrulanmadı [R] | - | yok |
| `gotji253/ai_trading_ada` | Ders döngüsü: memory/trade_memory.py + memory/learning_prompt.py:8-21 (dersleri isteme koyar); 4 aşamalı self_improve.py:1-40 (hafıza->atıf->optimizer->walk-forward); validator.py:47-48 `max_dd_ok = True  # Placeholder` ve Sharpe>=1.5 kapısı -> kapı kısmen sahte; çıktı 'Review and apply manually' [K] | Sharpe>=1.5 | yok |
| `guixu-project/guixu` | crates/storage/src/feedback_store.rs, memory_store.rs var (dosya adı); işlem sonucuyla bağ doğrulanmadı [R] | - | Apache-2.0 |
| `hammergpt/hyper-alpha-arena` | LLM kendi hafızasını yazar/okur: services/hyper_ai_tools.py:2593 execute_save_memory, hyper_ai_memory_service.py:94 add_memory, hyper_ai_service.py:569 _build_memory_context; PnL'e bağlı otomatik ders/kapı yok [K] | - | Apache-2.0 |
| `henryzhangpku/autonomous-quant-researcher` | Hash zincirli defter (README) + araştırma belleği research/lab/memory.py; bizim araştırma kuralları (madde 6) ile aynı felsefe [K-dosya] | - | MIT |
| `hkuds/vibe-trading` | agent/src/agent/memory.py:14-37 WorkspaceMemory oturum belleği; skills/trade-journal + tools/trade_journal_tool.py günlük okuma; sonuçtan ders enjeksiyonu yok [K] | MIT | MIT |
| `hsliuping/tradingagents-cn` | tradingagents/graph/reflection.py; app/services/skill_generation_service.py:382-398 yinelemeli yansımadan 'kök neden + düzeltme planı' dersleri; mem0 göçü (app/scripts/migrate_legacy_agent_memory_to_mem0.py); kapı yok [K] | - | Apache-2.0 |
| `inapp-mobile/clodds` | ml-signals.ts:9,133,450 `retrain()` birikmiş verilerle, lastRetrain; otomatik tetik/terfi kapısı doğrulanmadı [K] | - | MIT |
| `ishieldi/alphaswarm` | alphaswarm/improve/outcome_analyzer.py (dosya adı) [R] | - | yok |
| `jerome-benoit/freqai-strategies` | Canlı yeniden eğitim varsayılan kapalı, kendi işlemlerinden öğrenme yok [O]; lisans yok | - | yok |
| `jgardet/evotrade` | Otomatik araştırma döngüsü (üret-test-yinele); kâğıt kapısı doğrulanmadı [R] | - | özel/belirsiz |
| `julian-dev28/pathiel` | docs/strategy/learning/REVIEW_2026-11-03..11-10.md periyodik inceleme raporları, services/review/proposals.py, agents/atomic_io.py:12 'her terfi/emekliye ayırma kararının delili'; kapı sayıları incelenmedi [K-dosya] | - | MIT |
| `kairospan/gravit-agent` | face/src/memory-*.ts bellek modülleri (dosya adları); işlem sonucundan ders döngüsü doğrulanmadı [R] | - | Apache-2.0 |
| `kyky2347/alta` | alta-runtime/python/src/alta_asterism/alpha_feedback.py:49 alt-güven-sınırı hesabı (`_alpha_lower_confidence_bound`), forecast_calibration.py, scout_feedback.py, opportunity_memory.py: olgun sonuçlardan alfa katkı geri beslemesi [K-dosya] | - | Apache-2.0 |
| `kylinmountain/tradingagents-ashare` | tradingagents/graph/trading_graph.py:142,470 Reflector.reflect_and_remember(returns_losses) [K] | Apache-2.0 | Apache-2.0 |
| `leadline88/binance-ai-trader` | Yalnız README iddiası | - | yok |
| `llmtrader` | Aynı [K] | - | MIT |
| `lnstt369/nightwatcher-v2` | src/storage/d1/queries/memory.ts + trade_journal; sonuçtan ders enjeksiyonu doğrulanmadı [R] | - | MIT |
| `lumiwealth/lumibot` | components/memory/store.py + agents/manager.py:479,716 ajan hafıza notları; ders PnL'e bağlı değil [K-dosya/O] | GPL-3.0 | GPL-3.0 |
| `ma-pony/cryptotrader-ai` | learning/evolution/skill_provider.py + idf.py: 'beceri' dosyaları rejime/anahtar kelimeye göre isteme alınır (IDF puanı idf.py:77); journal/ ; beceri üretimi/terfisi doğrulanmadı [K-dosya] | - | MIT |
| `maazullah8/ai_self_improving_bot` | ai/review.py, ai/optimizer.py, ai/pattern.py, journal/ ; önerinin kapısı doğrulanmadı [K-dosya] | - | yok |
| `mad1kow-cloud/crypto-intelligence-agent` | agent.py:187-237 kapanan her işlem için Claude 150 kelimelik ders yazar -> episodic_memory.json (:60); kapı/emeklilik yok [K] | ders ≤150 kelime | yok |
| `marigold/universal-portfolios` | Çevrimiçi ağırlık güncellemesi yalnız fiyat verisiyle; kendi işlem sonucu yok [R] | - | MIT |
| `markfans/cryptoquant-ai` | public/legacy/auto-trading-feedback.js eski geri bildirim betiği [R] | - | MIT |
| `maxwellcm92/darwinfi` | src/evolution/memory.ts, proposal.ts, agent/signal-calibration.ts; kâğıttan canlıya KAPILI terfi (kâğıt kapısı) [O] | - | MIT |
| `michi883/trade-cast` | agents/reflector.py:275 run_reflector, server.py:128 zamanlanmış yansıma, reflection/cycle_history.py, memory/cycle_store.py [K-dosya] | - | MIT |
| `microsoft/qlib` | workflow/online/manager.py:101 OnlineManager, strategy.py:93 RollingStrategy: kayan pencerede yeniden eğitim + terfi; yalnız piyasa verisi [K] | MIT | MIT |
| `microsoft/rd-agent` | Evrimleşen kod: coder/CoSTEER/evolving_strategy.py; sonuca göre tekrar önerir [K-dosya] | - | MIT |
| `mikegianfelice/hunter` | core/performance_tracker.py:353 kapanan işlem istatistiği; scripts/prepare_ml_training_data.py; geri besleme bağı doğrulanmadı [R] | - | Apache-2.0 |
| `millw14/merrymen` | RetiredAgent listesi (android PublicPerformance.kt:26) yalnız performans gösterimi; öğrenme döngüsü doğrulanmadı [R] | - | yok |
| `mnemox-ai/tradememory-protocol` | owm/dqs.py:436 calibrate(min_trades=50) işlem sonuçlarından kalibrasyon; adaptive_risk.py:45 MIN_TRADES=5; tradememory-plugin/skills/evolution-engine [K] | calibrate ≥50; risk ≥5 | MIT |
| `mogons/noraz-agent` | orchestrator/swarm-learning.ts:1-14 SignalOutcome (TAKE_PROFIT_2X/1_5X/STOP_LOSS) sonuç etiketleme; ağırlık/ders enjeksiyonu doğrulanmadı [R] | - | MIT |
| `moss-site/moss-trade-bot-skills` | Backtest ile evrim (geçmiş veri); kendi işlem sonucuna bağ doğrulanmadı [R] | - | MIT |
| `neillbotushanski/alphaforge` | Yalnız README iddiası | - | yok |
| `neryaai/nerya` | /evolution/reflect uç noktası öneri (proposal.id) üretir (scripts/run_hackathon_demo_validation.py:612-515); skills/builtin/evolve [K-dosya] | - | özel/belirsiz |
| `nikhilperr/binance-futures-trading-bot` | modules/learning_engine.py:219-248 SQLite strategy_performance (strateji x rejim win/loss sayacı), :508 sorgu; seçime bağ doğrulanmadı; lisans yok [K-dosya] | - | MIT |
| `nofiix/openclaw-workspace` | POLY_FACTORY/risk/poly_strategy_promotion_gate.py terfi kapısı; agents/learner/SOUL.md, AGENTS.md, POLY_FACTORY/tasks/lessons.md ders dosyası [K-dosya] | - | yok |
| `nofxaios/nofx` | Yalnız istatistik: trader/auto_trader_loop.go:684 GetFullStats (Sharpe/PF/WinRate) isteme; yeni planning/harness/memory.go:67 OpenMemory (docs/architecture/AGENT_MEMORY_AND_PLANNING.md) ajan belleği var, ders/kapı doğrulanmadı [K-dosya/O] | - | AGPL-3.0 |
| `oficcejo/okx-2pa-agent-web` | pa_agent/ai/retry_feedback.py emir/doğrulama reddi geri bildirimi; PnL öğrenmesi değil [K-dosya] | - | AGPL-3.0 |
| `olaxbt/ai-market-maker` | memory/policy_memory.py (json .runs/), governance/policy_orchestrator.py; dersin sonuçla bağı doğrulanmadı [R] | - | AGPL-3.0 |
| `open-finance-lab/agentictrading` | Bellek ajan havuzu (agent_pools/alpha_agent_pool/corepkg/ports/memory.py); gerçek işlem sonuçlarıyla döngü doğrulanmadı [R] | - | özel/belirsiz |
| `openbyteinc/quantdinger` | services/ai_calibration.py:56,162 AICalibrationService.calibrate_market: geçmiş AI öneri isabetine göre kalibrasyon; services/strategy_evolution/constraints.py; analysis_memory.py [K-dosya] | - | Apache-2.0 |
| `parkseokjune/overfit-slayer` | src/self_learn.py:1-12 aylık özdeğerlendirme/yeniden kalibrasyon, 6 koruma: yalnız doğrulanmış aile içinde arama; komşu hücre medyan OOS>0 (plato); mevcuda göre OOS Sharpe ≥ +0,15 iyileşme şartı; öğrenme başına en çok 1 parametre seti; kaldıraç/stop/vol-hedef öğrenilmez; her karar CSV'ye (değişmedi dahil) [K] | +0,15 Sharpe; 1 değişiklik | yok |
| `pettekay/ai-forex-trading-bot` | agents/reflection.py:7-24 kapanan işlemden ders çıkarır, 0-1 faydalılık puanı, eşik altı kaydedilmez ('mediocre lessons pollute'); agents/portfolio_manager.py:151-156,227 dersler isteme 'usefulness_score' ile girer, benzer kazanan kurulum ders başına +5 puan; memory/semantic.py [K] | ders puanı 0-1; +5/ders | MIT |
| `phichleng/tradinggpt` | backend/app/schemas/journal.py + api/v1/journals.py: günlük/playbook RAG araması; sonuçtan otomatik ders yok [R] | - | yok |
| `pipiku915/finmem-llm-stocktrading` | puppy/memory_functions/decay.py:9 importance_factor=0,988 üstel azalma + recency/importance/access skorları; puppy/reflection.py; eğitim/test ayrı yansıma fabrikası (:56,96) [K] | 0,988 | MIT |
| `i_polymarket-btc-15-minutes (masterputra169)` | Kayma = modelin kendi eski canlı penceresiyle kıyas (plan: ML-2 kayma alarmı) [Ö] | - | MIT |
| `qingshungli/super-nof1.ai` | lib/ai/learning-feedback.ts:19-65 kapanan işlemden `lesson_learned` çıkarır; prompt.ts:198 `getLearningStats(7)` son 7 günü isteme koyar; kapı yok [K] | pencere 7 gün | MIT |
| `qrak/LLM_trader` | src/trading/vector_memory.py:35-37 çürüme yarı ömrü = timeframe/17 gün (en çok 30 gün), azami yaş x4; brain_reflection.py:14-18 kayıp deseni için ≥5 kayıp, anti-örüntü kayıp oranı ≥0,6, taban ≥10 işlem, AI-hata ≥5 örnek; :33-58 kural EMEKLİ: karşıt kanıt ≥ max(3, destek/2) VE > doğrulama sayısı (RETIRE_MIN_CONTRADICTIONS=3); BLOKE işlemler de kaydedilir (vector_memory.py:312, brain_context.py:90 get_blocked_trade_feedback) -> alınmayan sinyal geri bildirimi; post_mortem.py PostMortemService.analyze_closed_trade (:90) [K] | ≥5 kayıp; oran ≥0,6; karşıt ≥3 | MIT |
| `quantiaai/helm-agents` | apps/api/src/lib/reflection.ts, packages/persistence/src/memory-repo.ts yansıma+bellek (dosya adları) [R] | - | Apache-2.0 |
| `rafaelpf07/evotrader` | paper/learner.py:1-18,42-48: her 63 işlem gününde (relearn_every) şampiyonun zarar işlemlerini inceler -> 'zarar şu koşulda toplandı' dersleri aday kural olur; GA'yı şampiyon+ders adayları+şan salonuyla tohumlar; yalnız son 252 gün HOLDOUT'ta marj ≥ 0,10 ile üstünse terfi; tutmayan ders atılır [K] | 63 gün; 252 gün holdout; marj 0,10 | yok |
| `rgg81/crypto-trade-claude-code` | futures_fund/lessons.py: aday ders -> VALIDATED yalnız ≥5 teyit VE DSR p ≥ 0,95 (:224-236, :178-196); demote teyitleri sıfırlar (:198-212); retrieve k=5, max kısıtlayıcı 3 (:114-117), skor recency 0,995^saat (:93); sayısal bantlar kelimesi kelimesine enjekte (SKILL.md:37-38); ayrıca 'declined_edge_setups' ve 'missed_opportunities' (alınmayan fırsat) yansıtıcıya girer (SKILL.md:68) [K] | teyit ≥5; DSR ≥0,95; k=5 | yok |
| `ricardokarma/claude-trading-bot` | services/learning/daily-loop.ts günlük öğrenme döngüsü (dosya adı) [R] | - | MIT |
| `roclee2692/autonomous-spot-trading-agent` | src/spot_agent/journal.py günlük; öğrenme döngüsü doğrulanmadı [R] | - | yok |
| `rp7o/trade-foundry` | research/trade-long/hooks/workflow.ts:861-862 en düşük skorlu soy emekliye ayrılır, en iyi ebeveynlerden yenisi üretilir (retireAndBreed); skor tabanlı, kâğıt kapısı yok [K] | - | MIT |
| `ruiwang20010702/cryptobot` | journal/analyst_weights.py:18 calc_analyst_weights(days=30) isabete göre analist ağırlığı; journal/confidence_tuner.py:17-18,86 min güven dinamik: _MIN_CLOSED=50, kova başına ≥15, taban 60; evolution/strategy_advisor.py:263 [K] | ≥50 kapanmış; kova ≥15 | AGPL-3.0 |
| `ryanfrigo/kalshi-ai-trading-bot` | agent/learnings.py:122 reconcile_outcomes (sonuçlarla uzlaşma), :183 calibration_table, :272 edge_breakdown, :313 flag_rules; docs/plans/2026-06-24-learnings-system-design.md [K] | - | MIT |
| `shiyu-coder/kronos` | finetune/train_predictor.py ince ayar (piyasa verisi); kendi işlem sonucu yok [K-dosya] | - | MIT |
| `shoaibghulam/binance-ai-bot` | app/ml/trainer.py:1-35: kapanan işlemlerin features_json+sonucundan bot başına WinProbModel yeniden eğitilir; MIN_SAMPLES_TO_START=50, her 25 yeni kapanan işlemde, MIN_GATE_AUC=0,55 (AUC altı model devrede değil); lisans MIT [K] | 50 başla; her 25; AUC≥0,55 | MIT |
| `solohard32/mexc-ai-bot` | core/model_evolver.py:15-25 ModelEvolver: çalışma metriğine göre model anlık görüntüleri + en iyi sürüm kaydı, min_trade_gap=8; DRY_RUN'da model öğrenmez [K] | gap=8 | MIT |
| `sorry510/go_binance_futures` | doc/agent/v3/07-phase-v3-7-outcome-review.md sonuç incelemesi; ders çıkarma otomatik bağlı değil [O]; MIT | - | MIT |
| `superalgos/superalgos` | Learning-Bot modülü fiyat verisiyle model eğitir; kendi işlem sonucuna bağ doğrulanmadı [R] | - | Apache-2.0 |
| `superior-trade/trading-terminal` | lib/agent-memory.ts ajan belleği; sonuç döngüsü doğrulanmadı [R] | - | Apache-2.0 |
| `suyunjing-su/r20-quantum-trader` | Astra ile aynı döngü (aynı dosya adları) [K-dosya] | - | MIT |
| `TauricResearch/TradingAgents` | Çözümle-yansıt-enjekte: memory/settlement.py:136 settle_pending (ham getiri + benchmark alpha) -> memory/reflection.py:36 reflect_on_final_decision (2-4 cümle) -> memory/log.py:93 get_past_context(n_same=5, n_cross=3, as_of); YALNIZ Portföy Yöneticisi istemine girer (agents/managers/portfolio_manager.py:35-37); as_of ile ileriye bakış sızıntısı engeli; kapı/emeklilik yok [K] | n_same=5, n_cross=3 | Apache-2.0 |
| `the-finai/fincon` | Kod yok -> yalnız makale iddiası [K-README] | - | MIT |
| `torchtrade/torchtrade` | Çevrimiçi/çevrimdışı/model-tabanlı RL eğitimi; canlı işlemlerden yeniden eğitim hattı doğrulanmadı [R] | MIT | MIT |
| `i_tradingbot (zero-was-here, Aurum v2)` | Planın ana ML kaynağı: DSR/PBO/CPCV istatistikleri (research/stats.py, splits.py) bizim terfi kapısında kullanılıyor [Ö] | - | MIT |
| `vedv0987-cloud/bvedtrade` | ai/learning_engine.py:79 LearningEngine(decay_half_life_days=14) rejim ayarı (record_outcome :87, get_adjustments :109); ml/adaptive_retrain.py:100-167 zamana veya düşen kazanma oranına göre yeniden eğitim, min_samples=2000; yazarın kendi verisi 634 işlem -0,55R [K/O] | yarı ömür 14 gün; min 2000 | yok |
| `vishalsaraswat047/apha-tb` | learning_engine.ts (dosya adı); içerik incelenmedi [R] | - | yok |
| `wquguru/nof0` | Prompt'ta ROLLING_SHARPE; metrik üretimi eksik (`RecentTradesRate: 0, // TODO`, pkg/manager/trader.go:82) [O]; yalnız Sharpe tabanlı duraklatma | - | yok |
| `wyc-dev/mats` | Çıkış öğrenici (analysis/exit-price-learner.ts, τ=7 gün :223; index.ts:4176,10249,10897 canlı kullanım), rejim kazanma oranı (analysis/regime-win-rate-learner.ts:17-22: ≤300 işlem halka, ≥10 örnek, τ=24 s, sembol 0,8/çapraz 0,2), meta-öğrenici özellik ağırlığı 0,1-3,0 (evolution/meta-learner.ts:165-168), öğrenme ağırlığı: sistem kapanışları 0,3-0,5'e indirilir, 'kirli' sinyal (evolution/learning-weight.ts:1-25); kapı yok [K] | ağırlık 0,1-3,0; ≥10 örnek | Apache-2.0 |
| `xtra-computing/cryptotrade` | generate_reflections.py yansıma üretimi (dosya adı) [R] | - | özel/belirsiz |
| `yellowpancake/quant-autoresearch` | Tut/at araştırma döngüsü (deney sonucu ile); kâğıt/holdout kapısı doğrulanmadı [R] | - | MIT |
| `ygwyg/mahoraga` | storage/d1/queries/memory.ts var ama harness'e bağlı değil [O] | - | MIT |
| `yi-111-a/alphaloop-crypto` | LOCKED/reflector.py:1-30 yansıtıcının girdisi YAPISAL OLARAK kapalı: yalnız decisions.jsonl + fiyat sonucu, haber/serbest arama imzada yok, AST testiyle korunur; falsifier hükmü kodla (LLM öz-değerlendirme değil); ajan LOCKED dizinine yazamaz [K] | - | yok |
| `yllvar/quant-autoresearch` | src/memory/playbook.py:1-15 SQLite çift-bellek (başarılı strateji kalıpları); işlem sonucu değil araştırma sonucu [K] | - | yok |
| `ymcbzrgn/hydraquant` | user_data/scripts/promotion_gate.py:1-12 gerçek sermaye için 8 şartlı sert kapı: PnL>0, Sharpe>1, DD<%10, 0 tasfiye, ≥30 işlem, kazanma ≥%55, LinUCB varyans<0,1, otonomi≥1; geçse de manuel onay (:13); ayrıca ai_lessons göçü ve 'memory poisoning' kırmızı takım betiği (scripts/redteam_memory_poisoning.py) [K] | 30 işlem; %55; DD<%10 | GPL-3.0 |
| `zetryn-ai/ai-agent` | memory/reflective.py, memory/blacklist.py, memory/decision_log.py, analytics/calibration.py (dosya adları); sonuç->kara liste->karar bağı doğrulanmadı [R] | - | MIT |
| `zhulinsen/daily_stock_analysis` | services/decision_signal_outcome_service.py + skill_opinion_outcome_service.py: verilen sinyalin sonucunu ölçer; istemlere geri besleme doğrulanmadı [R] | - | MIT |

## 6. Konu dışı (madde 1 ve 2'de ilgisiz; yine de listeli)

| Repo | Neden konu dışı | Lisans |
|---|---|---|
| `0smallcat0/trialgate` | Backtest deneme sayısını hash-zincirli defterde tutan aşırı-uyum kapısı (README:1) -> madde 6'ya ait; ML/LLM karar yok | MIT |
| `0xmerl99/agent-world-protocol` | Çok oyunculu piksel dünya oyunu; ticaretle ilgisiz | yok |
| `51bitquant/binance_grid_trader` | Grid botu; ML/LLM yok | MIT |
| `ai4finance-foundation/elegantrl` | Genel RL kütüphanesi (rlsolver/…, torch); ticaret ortamı/kendi işlem verisi yok | Apache-2.0 |
| `ai4finance-foundation/finrobot` | LLM finansal analiz/rapor çatısı ('models reason, software computes'); emir/öğrenme yok | Apache-2.0 |
| `aifore/coinx` | Kişisel araştırma raporu + veri betikleri + salt-okunur Binance pozisyon aracı; ML/LLM karar yok | MIT |
| `alaika-cyber/pumpfun` | pump.fun araç/arayüz; model yok | MIT |
| `alpacahq/alpaca-mcp-server` | Alpaca MCP sunucusu (araç) | MIT |
| `aminhp/gym-anytrading` | Gym RL ortamı (gym_anytrading/envs/trading_env.py:23); eğitim/canlı yok, araç | MIT |
| `aswin-ram-k/algo-trading-bot` | README yok; belirgin ML/LLM işareti yok | MIT |
| `azmax7434/trading-view` | Kaynak kodu yok (0 dosya); yalnız README | yok |
| `bederf/leah-freqtrade-strategies` | Freqtrade strateji araştırma/backtest (rejim zayıflaması üzerine); ML/LLM çekirdek yok | MIT |
| `boredom198/thesis-ai-trading-agent` | Tez belgesi/diyagram; kod yok | yok |
| `caiovicentino/polymarket-mcp-server` | Polymarket MCP sunucusu (45 araç); karar Claude'da, kod araç | MIT |
| `coding-kitties/investing-algorithm-framework` | Kural tabanlı backtest/canlı çatısı; ML/LLM karar yok | Apache-2.0 |
| `dasein108/freqtrade_dev_mcp` | Freqtrade strateji geliştirme MCP sunucusu | MIT |
| `daviddtech/ai-trading-agent` | Yalnız beceri/README dizini (0 kaynak dosya) | MIT |
| `dieumerci8/freqtrade-strategy-builder` | Claude/Codex 'beceri' (Freqtrade strateji yazma/backtest rehberi); kendi karar vermez | MIT |
| `dogstailfarmer/martin-binance` | Martingale/grid botu; ML/LLM yok (triage 0) | MIT |
| `dontbesideline/open-nof1-alphaarena` | nof1 Alpha Arena arayüz klonu; model/öğrenme yok | MIT |
| `drakkar-software/octobot` | Görsel arayüzlü klasik bot (OctoBot); ML bu incelemede doğrulanmadı, kural tabanlı çekirdek | GPL-3.0 |
| `drakkar-software/octobot-ai` | 3 kaynak dosya, README iskeleti; kod yok | AGPL-3.0 |
| `enarjord/passivbot` | Grid/martingale; tahmin etmez, öğrenmez (src/tools/capture_optimize_memory.py yalnız optimizer bellek ölçümü) | Unlicense |
| `i_freqAI-LSTM / moex-ml-trading / ml-crypto-trading-bot` | Tek LSTM / onlarca 'optimize' backtest betiği / Python kodu yok: aşırı-uyum örneği, alınacak şey yok [Ö §1.8] | ? |
| `furkankoykiran/freqtrade-mcp` | Freqtrade REST için MCP sunucusu; karar vermez | MIT |
| `gone2707/btc-trading-bot` | Muhafazakâr BTC HODL botu; ML/LLM yok | yok |
| `hkuds/ai-trader` | Ajanların katıldığı sosyal işlem platformu (service/server/rewards.py puan ödülü, ticari öğrenme değil) | yok |
| `hummingbot/hummingbot` | Piyasa yapıcı/arbitraj çatısı (arb_proposal.py bir arbitraj teklifi sınıfı); ML/LLM çekirdek değil | Apache-2.0 |
| `hypurrquant/perp-cli` | Çok-DEX perp CLI'ı (komut satırı aracı); karar mantığı yok | MIT |
| `iterativv/nostalgiaforinfinity` | Kural tabanlı Freqtrade stratejisi (NFI); ML/LLM yok | GPL-3.0 |
| `janitoff0/ninjatrader-bot` | Tek dosya NinjaTrader kutusu; ML/LLM yok | yok |
| `je-suis-tm/quant-trading` | Klasik kantitatif strateji örnekleri; ML/LLM karar yok | Apache-2.0 |
| `jesse-ai/jesse` | Algoritmik strateji çatısı (backtest/canlı); ML/LLM yok | MIT |
| `kb-90/okx-algotrade-agent-x` | Küçük README + betik; ML/LLM işareti yok (triage) | AGPL-3.0 |
| `kevinmyding/tradinggpt` | FinGPT duygu LLM'i ince ayarı (fingpt/FinGPT-v1/training/finetune.py:15-133); ticaret kararı yok | MIT |
| `krakenfx/kraken-cli` | Kraken CLI (ajan araç kiti); feedback.rs ürün geri bildirimi | MIT |
| `kukapay/awesome-alpha-arena` | Bağlantı listesi (0 kod) | MIT |
| `llmquant/awesome-trading-agents` | Liste | özel/belirsiz |
| `loveolu/crypto-strategy-research` | Negatif sonuç arşivi (README:1: ~100 deneme, 44 döngü, çıkan strateji yok); ML/LLM karar yok. Not: 'ders #15/#20' kuralları testlere zorunlu aserssiyon olarak yazılmış (user_data/research/phase_t039_census.py:673) -> insan dersi kodla zorlama | yok |
| `masaichig0/tradinggpt` | Şirket bilgisinden LLM analiz not defteri; işlem/öğrenme yok | yok |
| `max007-coder/quantbot` | Çok-borsa kâğıt/canlı bot paneli; ML/LLM karar işareti yok | yok |
| `milady-ai/plugin-bsc-memes` | elizaOS BSC meme eklentisi; model yok | yok |
| `mingyuj666/stockagent` | Akademik LLM ajan piyasa simülasyonu (dış etken etkisi); canlı işlem/öğrenme döngüsü yok | yok |
| `nateemma/strategies` | Freqtrade ML/klasik strateji koleksiyonu + araştırma notları (research/clfstudy/calibrate.py); tek sistem değil | GPL-3.0 |
| `nautechsystems/nautilus_trader` | Rust motoru (LGPL); ML/LLM karar yok | LGPL |
| `nirholas/binance-mcp` | Binance MCP sunucusu (araç) | özel/belirsiz |
| `okay-bet/plugin-polymarket` | elizaOS Polymarket eklentisi | yok |
| `okay456okay/nof1.ai.monitor` | Alpha Arena pozisyon izleyici (Flask) | MIT |
| `okx/agent-trade-kit` | OKX MCP/CLI araç kiti; karar vermez | MIT |
| `oyi77/1ai-skills` | Claude Code beceri deposu (tasarım/güvenlik); hooks/auto-evolve/skill-evolver.js kendi becerilerini evrimleştirir ama ticaret değil | MIT |
| `p20090504-dotcom/qs-bot` | 0 kaynak dosya; README: BTC perp sinyal sistemi (yalnız iddia) | özel/belirsiz |
| `pellenybe/crypto-mcp-server---by-corax-colab` | MCP orkestratör altyapısı; model/öğrenme yok (triage 0) | MIT |
| `pi-2r/quant-science` | Veri bilimi ortamı (notebook); işlem yok | yok |
| `pranavjadhav1363/plugin-ccxt` | elizaOS CCXT eklentisi | yok |
| `pulseprotocolorg-cyber/pulse-freqtrade` | Freqtrade'e harici AI sinyali enjekte eden mesaj arayüzü; karar kaynağı dışarıda | yok |
| `quant-science/sunday-quant-scientist` | Eğitim içerik/bülten deposu | yok |
| `raphael2025/perp-recap` | Binance işlem inceleme aracı (Streamlit); otomatik karar/öğrenme yok | MIT |
| `remiotore/ccxt-freqtrade` | Strat.Ninja strateji koleksiyonu (3.980 dosya) + analiz notebook'u; bazı FreqAI/RL örnekleri (strategies/AlexNexusForgeV8AIV2.py:491 retrain_interval_hours=48) koleksiyon düzeyinde | yok |
| `richkuo/go-trader` | Go + Python 50+ kural tabanlı strateji orkestratörü; Hurst kapısı kalibrasyonu araştırması (backtest/research/hurst_gate_calibration.py); ML/LLM yok | MIT |
| `roboticautomations/freqtradestrategies` | Topluluk Freqtrade strateji/FreqAI model koleksiyonu (TSPredict, GGYT_SAC, LorentzianClassification vb.); tek bir tutarlı sistem değil | yok |
| `sak-114514/freqtrade-agent` | Freqtrade REST kopilot katmanı (FastAPI); memory_plugin.py sohbet belleği, işlem öğrenmesi yok | yok |
| `satyamdas03/alpaca-trading-agent` | Çok proje deposu (Apify aktörleri, araştırma); tek bir öğrenme döngüsü yok (projects/RESEARCH_HERMES/aqra/src/aqra/live/monitor.py:5 should_retire taslağı) | yok |
| `sc0vu/freqlint` | Freqtrade strateji doğrulama 'beceri'si | MIT |
| `scodive/alpha-arena-prompt` | AI Studio uygulaması/istem | yok |
| `sendaifun/solana-agent-kit` | Solana araç SDK'sı (60+ eylem); karar yok | Apache-2.0 |
| `snowingfox/open-nof1.ai` | Alpha Arena benzeri arayüz/benchmark; öğrenme yok | yok |
| `sonirico/go-hyperliquid` | Hyperliquid Go istemci kütüphanesi | MIT |
| `sopersone/cabbage-trading-machine` | Investing Algorithm Framework 9.0 üzerine kurulu bot (çatı); ML/LLM karar doğrulanmadı | Apache-2.0 |
| `superior-trade/superior-skills` | Hyperliquid strateji yazma/backtest 'beceri'leri; karar çekirdeği yok | MIT |
| `syh52/ft-analyzer` | Freqtrade çatalı (içinde FreqAI RL ReinforcementLearner.py, freqtrade ile aynı); ayrıca incelenmedi | GPL-3.0 |
| `teraus111/web3-agent-kit-solana-trading` | SDK/tanıtım metni (docs/promotion/…); model yok | MIT |
| `terryso/nof1-tracker` | nof1 ajan sinyallerini kopyalayan CLI (kendi model yok) | MIT |
| `thefourgreaterrors/alpha-rptr` | Kural tabanlı Binance/Bybit botu; ML/LLM yok | MIT |
| `tradermonty/claude-trading-skills` | Claude beceri seti (tarama/analiz iş akışları, ör. dividend-growth screener); otomatik emir/öğrenme yok | MIT |
| `ulab-uiuc/live-trade-bench` | LLM ajan değerlendirme platformu (FastAPI); kendi karar mantığı yok | özel/belirsiz |
| `valory-xyz/trader` | Olas tahmin-piyasası ajanı (decision_maker_abci); kripto vadeli/ML öğrenme konusu dışı | Apache-2.0 |
| `vnavanee/cryptotrader-llm` | Vite/React şablonu; kod yok | yok |
| `vnpy/vnpy` | Genel kantitatif işlem çatısı; ML/LLM karar çekirdeği yok | MIT |
| `yalcin/freqtrade-mcp` | Salt-okunur Freqtrade kod tabanı MCP'si | GPL-3.0 |
| `zeframlou/bagholder` | NFT sadakat protokolü (akıllı sözleşme); ticaret modeli yok | AGPL-3.0 |
| `zhangjinhahaha/agentlens` | Ajan kiralama platformu (altyapı) | AGPL-3.0 |
| `zhivko/ai-trading-bot-3` | README yalnız RTX 5090 / CUDA 13 PyTorch derleme rehberi; işlem mantığı dokümante değil | yok |

## 7. Kapsam

**Sayılar.** Tarama evreni: `reports/Puanlama matrisi.md` (53 repo) + `reports/` ve `research_notes/` içinde adı geçen diğer repolar (GitHub URL'leri + metin içi `sahip/repo` adları elle süzüldü) + sahibin 2 projesi + planın yerel klonları.
- **Klonlanmış ve taranmış: 247 dizin** (`scratchpad/repos/`): `a_` 107, `c_` 92 (matris 53 + diğerleri), `x_` 47 (bu turda eklenen), `t_` 1 (`t_llmtrader` = `x_qrak_LLM_trader`, aynı kod; yani **246 farklı repo**). Hepsinde anahtar-sözcük taraması (yansıma/ders/yeniden eğitim/`fit`/RL/LLM çağrısı) + README ilk satırları + dosya adı taraması yapıldı; kodu satır satır okuduğum ≈60 repo `[K]` etiketli.
- **Yerel (sahibin makinesi) plan klonları:** `/home/user/sselimgenc-oss/inceleme/` 16 repo; 7'si zaten scratch'te (FTMO, MATS, PowerTrader_AI, freqai-strategies, freqtrade, intelligent-trading-bot, qlib), kalan 9'u tablolarda `İ` satırlarıyla (`tradingbot`/Aurum, `polymarket-btc-15-minutes`, `forex-gold`, `alphastrike`, `autonomous-equity-trading-system`, `deepalpha` ve 3'ü tek satırda `freqAI-LSTM / moex-ml-trading / ml-crypto-trading-bot`); bu 9'unun kanıtı `ml-guclendirme-plani.md` §1'den **önceki tur notu `[Ö]`**'dür, yeniden okunmadı.
- **Sahibin projeleri (salt okunur):** `1l3a-proje`, `ct-proje` — iki tabloda `o_` satırı.
- **Erişilemedi (4):** `zhou343/stock-trader-ai`, `thom899g/autonomous-cross-asset`, `squidkid-deluxe/qtradex`, `rickyispresent/infinite-bagholder` — `git clone` "could not read Username" (silinmiş/özel). Notlardaki önceki bulgu bu dosyada kullanılmadı (tahmin yok). 2 repo (`zhivko/ai-trading-bot-3`, `quantiaai/helm-agents`) ilk denemede paket hatası verdi, ikinci denemede klonlandı.
- **Bilerek klonlanmayan (kapsam dışı):** `ccxt/ccxt` (borsa kütüphanesi), `elizaos/eliza` (genel ajan çatısı), `stefan-jansen/machine-learning-for-trading` (kitap kodu, çok büyük; plan notu `ml-guclendirme-plani` §1'de de klonlanmadı), `PGPortfolio` (plan: RL kapsam dışı; `ElegantRL`, `FinRL`, `TensorTrade` ise klonlu ve listeli).
- **Tablo satırları:** Madde 1 tablosu 174; Madde 2 tablosu 130; konu dışı (iki maddede de ilgisiz) 82. Madde 1 + konu dışı = 256 benzersiz satır = 247 dizin (kopya `t_llmtrader` satırı dahil) + 7 `İ` + 2 `o_`. Her dizin en az bir tabloda yer alır; hiçbiri atlanmadı.
- Madde 1'de listeli ama **madde 2'de öğrenme döngüsü bulunmayan** repolar (44): 00hsynclk/crypto-trading-bot, 0xemmkty/quantmuse, 51bitquant/ai-hedge-fund-crypto, affaan-m/dprc-autotrader-v2, ai-brokers/aibrokers, ai4finance-foundation/finrl, ai4finance-foundation/finrl-trading, aristidesai/ibkr-aihedge, backtest-kit/backtest-ollama-crontab, chrisleekr/binance-trading-bot, conjason/binance-alpha-miner, danny123-sudo/regime-trading-bot, dax-523/ai-trading-agent, i_deepalpha (stefanoviana), el-bach/claude-trader, etrobot/open-alpha-arena, eugmsub/robinhoodagentictrader, gaaiyun/freqtrade-strategy-generator, gacord1213-arch/alpaca-ai-trading-agent, gajesh2007/ai-trading-agent, imsatoshi/genetrader, islambaraka90/super-agent-trading-bot, jackson-video-resources/claude-tradingview-mcp-trading, kaoi-cyber/ai-trader, kojott/llm-trader-test, maotouhu/nof1openai, markdregan/freqai-marcos-lopez-de-prado, mocasus/trade-agent, mohamed-sm/freqtrade-rlstrategy-ia, muzafferkadir/claude-crypto-trader-public, oficcejo/alpha-arena-okx, oft3r/agentic-trading-desk, polymarket/agents, ryan-yuuu/crypto-trading-arena, samsoncukor06/agentic-trader, senpi-ai/senpi-skills, snowcheetos/automoonbot, tensortrade-org/tensortrade, the-swarm-corporation/autohedge, tiramisuice/ai-trader, traderalice/openalice, virattt/ai-hedge-fund, web3spreads/quant-flow, yizhisong/friestrader.
- Lisans dağılımı (247 dizin): MIT 115, Apache-2.0 29, GPL-3.0 12, AGPL-3.0 12 (+1 AGPL+Commons Clause = astra), LGPL 1, Unlicense 1, özel/belirsiz 8, **lisans dosyası yok 68**. Planın kuralı: GPL/AGPL/lisanssız = yalnız fikir (ml-faz §2).

**Planın iç tutarsızlıkları (olgu, karar değil)**
1. `ml-faz-tasarimi.md` ML-5 ("kendi adayını üreten ML") = ML-4'te ≥6 ay kayıttan sonra; `dd12 §5.2` aynı şeyi **Faz 3 ≤16 Aralık**'a çekiyor (kâğıtta, gölgesiz). dd12 daha yeni ve "gölge kip kâğıtta hiçbir yerde yok" diyor.
2. `trader/config/lesson.json` hâlâ `shadow_weeks=4`, `twin_enabled=true`; dd12 §6 ikizi kaldırıp otomatik uygulamayı ilk günden açıyor (Faz 1 teslim ≤21 Kasım). Yapılandırma henüz güncellenmemiş.
3. `ml-faz` §8 "canlıda RL yok, LLM öz-evrim yok" ve ders-spec "LLM menüden seçer" — dış repolarda en çok kullanılan iki yaklaşımı (LLM serbest ders yazar; RL/Q-öğrenme çarpanı) bilerek dışarıda bırakıyor; bunlar Bölüm 3/5'te `peri`, `mad1kow`, `MATS`, `bitbotby`, `ReforceXY` vb. olarak listeli.
4. Önceki tur notlarındaki bazı satır numaraları klon sürümüne göre kaymış (ör. nof1.ai `tradingLoop.ts:1574-1584` bu klonda `getTradeHistory`/`getRecentDecisions` tanımları `:884`/`:925`); bu dosyada yalnız bu turda doğruladığım numaralar kullanıldı.
