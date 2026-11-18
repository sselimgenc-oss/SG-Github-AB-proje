# Tur 6 / C — Pozisyon sınırları (7), hisse perp 7/24 vs NY seansı (8), emtia hafta sonu (9), çoklu varlık

Tarih: 18 Kasım 2026. Yalnız olgu toplama; hüküm yok. Kanıt biçimi: `repo/yol:satır`. Hiçbir üçüncü taraf kod çalıştırılmadı (yalnız cat/grep/sed). Repo içindeki metinler veri olarak okundu; istem enjeksiyonu denemesi görülmedi.
Derinlik notu: ~25 repo elle (dosya açılarak) okundu; kalanı için ripgrep deseni taraması yapıldı (ilgili tavan/seans kelimesi bulundu mu / bulunmadı). Taramada çıkmayan = "kodda kanıt yok", "yoktur" demek değildir.

## 0. Bizim plan (karşılaştırma tabanı)

| Konu | Bizim plan | Kaynak |
|---|---|---|
| Hesap geneli en çok pozisyon | Kâğıt katmanı: **10** (≤ %5 toplam açık risk). Eski taban/ayar: panelde `max_concurrent: 8`; `engine.base.json` dosyasında pozisyon sayısı anahtarı yok (10 çift, v1b; `risk.py` aynen: toplam açık risk %6, aynı yön %4, günlük zarar) | `trader/docs/motor/dd12-capraz-varlik-spec.md:61-71,152`; `trader/config/panel.json:17` |
| Küme tavanları | `kripto_buyuk` (BTC,ETH,XRP,BNB,SOL) 3; `kripto_diger` (15) 4; `hisse` (20) 3; `hisse_teknoloji` (12 isim) 2; `metal` (XAU,XAG) 1; `enerji_sanayi` (BZ,COPPER) 1. Bir çift çok kümede olabilir, hepsinde yer gerekir. Kurulum başına en çok 3 açık pozisyon (`M1` için 2) | spec §4 satır 61-71; §3 "Kurulum başına en çok 3" |
| Korelasyon ölçümü | Yok; yalnız elle tanımlı küme. Piyasa değeri sıralaması doğrulanmadı | spec satır 18, 257 |
| Hisse seansı (8) | Giriş yalnız New York 09:30–16:00, Pzt–Cum; ek koruma: son kapanmış tetik barı `volume==0` ya da `high==low` ise giriş yok (tatil). Açık pozisyonun stop/hedefi seans dışında da çalışır; hafta sonuna pozisyon taşınır, kapatılmaz | spec satır 61-71, test D-T7 satır 234 |
| Emtia hafta sonu (9) | `metal` ve `enerji_sanayi`: giriş Paz 23:00 → Cum 21:00 UTC; yani hafta sonu giriş yok. Test: Cuma 21:00 ve Pazar 22:59 UTC atlanır, 23:00 geçer | spec satır 61-71, 234 |
| TradFi kayma / funding / bilanço | Kayma tabanın 2 katı (giriş 4, çıkış 4, stop 10 bp; "tahmin"); hisse perp fonlaması ölçülmedi; kazanç açıklaması boşlukları ve yarım gün seansları için koruma YOK | spec satır 71, 257 |
| Veto | Hisse/emtia vetosuz başlar (BTC bağlamlı veto 44 enstrümanda maliyeti ~4x) | spec satır 73 |
| Doğrulanacak | 44 sembol `exchangeInfo` TRADING mi, `contractType` (beklenen `TRADIFI_PERPETUAL`), kapalı seansta 1 dk mum geliyor mu; Adım 0'da bir kez hafta sonu saatinde yoklama | spec satır 26, 207 |
| Sahibin görüşü | 7: "Artırın". 8 ve 9: "Binance futures 24 saat, neden açılmasın?" | 00-gorev.md |

## 1. Madde 7 — eşzamanlı pozisyon / korelasyon / küme / maruziyet sınırları

### 1a. Varsayılan sayısı ve küme/korelasyon kodu olan repolar (elle okundu)

| Repo | Ne yapıyor (kod kanıtı) | Sayı | Bizim plan | Fark / not |
|---|---|---|---|---|
| c_galleonlabs_hypergrok-trading-desk | Masa risk kuralı: işlem başı %0,5, toplam açık risk %2, günlük zarar -%2; "korelasyonlu küme": BTC/ETH/SOL tek küme, küme başına en çok 2 pozisyon; `positions_after <= max_positions ; cluster count` kontrolü (`skills/desk-risk-limits/SKILL.md:42-50,97`) | küme başı 2; toplam risk %2 (tavan %6, işlem %2: satır 21-24) | 10 poz; büyük kripto kümesi 3 | Bizden SIKI; küme tanımı elle (3 majör) |
| c_chase-mew_ai-hedge-fund | `fund.toml [risk]`: `max_weight_per_market 0.20`, `max_gross 1.5`, `max_net 1.0`, `max_new_risk_per_cycle 0.6`, `class_caps`: equity_index 0.6, stock 0.6, commodity 0.4, fx 0.3, crypto 0.4 (`fund.toml:46-68`); `risk/gate.py:181-184` `_class_caps` ölçekler; mark/oracle sapması >%1 kapısı (`gate.py:147-149`) | sınıf başı ağırlık tavanı (poz sayısı değil) | küme başı POZİSYON SAYISI tavanı | Varlık sınıfı kümeleri bizimkine en yakın; ağırlık tabanlı |
| c_ruiwang20010702_cryptobot | `risk/correlation.py:160-196`: yeni sinyal, mevcut aynı yönlü pozisyonlardan korelasyonu >0,7 olanlar `max_correlated_same_direction=3` ise reddedilir; etkin pozisyon sayısı hesabı | eşik 0,7; 3 | Korelasyon ölçülmez, elle küme | Ölçüm tabanlı korelasyon kapısı örneği |
| c_giansn_sygnif | `CLAUDE.md:93-94`: `max_concurrent_open 7` (10'dan 2026-04-28'de düşürüldü), `max_concurrent_per_side 3` (TREND'de x1,7); `SygnifStrategy.py:462` premium olmayan tavan 10 | 7; yön başı 3 | 10 | Düşürülmüş (gevşek ayarla zarar → sıkı) |
| c_nofxaios_nofx | `trader/auto_trader_risk.go:343-360` `enforceMaxPositions` kodda zorunlu; yoksa varsayılan 3 | 3 (autopilot varsayılanı `store.AutopilotDefaultMaxPositions`, sayı okunmadı) | 10 | Kodda zorunlu |
| c_ygwyg_mahoraga | `src/policy/engine.ts:215-228` `max_open_positions` ihlali; şema 1–50 (`schemas/agent-config.ts:12`); kripto için seans kontrolü atlanır (`engine.ts:121-129`) | env `DEFAULT_MAX_OPEN_POSITIONS` (sayı okunmadı) | — | Hisse+kripto aynı motor |
| c_wquguru_nof0 | `go/etc/executor.yaml:5` `max_positions: 4`; `manager.yaml` trader başına 3 ve 2; ana kripto kaldıracı 20x, alt 10x | 4 / 3 / 2 | 10 | Sıkı |
| c_kyky2347_alta | `portfolio_construction.py:39-41` `max_open_positions` 1–8 (sert aralık); `implementation.py:34-59` `per_trade_loss_budget 25 bp`, `max_position_nav 100 bp`, `max_gross_nav 800 bp`, `max_underlying_nav 150 bp` (aynı dayanak başına tavan), `equity_stress_floor 2500 bp` | 8 | 10 | Dayanak başına tavan (bizde yok) |
| c_erfaniaa_llm-auto-trader | `src/risk/risk_manager.py:41-58`: `max_total_exposure_pct 0.60`, `max_concurrent_positions 3` | 3; %60 | 10 | Sıkı |
| c_aplicy-com_guarded-trader | `conductor/infrastructure/config.py:49`: "her beyaz liste çifti bir maruziyet grubu; Freqtrade `max_open_trades`'e eşit tut"; `C01Tsmom1d.py:11` max_open_trades 2 | 2 | — | Çift = grup |
| a_el-bach_claude-trader | `agents/manager.py:31,33`: `MAX_OPEN_POSITIONS` env varsayılan 3; `MAX_PORTFOLIO_RISK_PCT 0.02` (toplam açık risk tavanı %2); MT5 gold ajanı tek-pozisyon | 3; %2 | 10 | |
| a_gotji253_ai_trading_ada | `src/paper/gold_trader.py:31` `max_positions = 1` (altın); `agents/risk_agent.py:27` `MAX_OPEN_RISK_PCT 3.0` | 1; %3 | metal 1 | Altın için 1 — bizimle aynı |
| a_pettekay_ai-forex-trading-bot | `config.py:134` `MAX_OPEN_POSITIONS = 3` ("korelasyonsuz pariteler"); `risk_governor.py:117` | 3 | | Yorumda "uncorrelated pairs", kod sayaç |
| a_mocasus_trade-agent | `config.py:42` max_open_positions 5; `risk.py:21` max_positions 3 | 5 / 3 | | iki farklı varsayılan |
| a_codeptor_peri | `config.py:57,255` `max_concurrent` (risk.toml'dan); istem: "en çok N otonom pozisyon" (`analyst.py:199`) | istekle | | |
| a_julian-dev28_pathiel | `config/public/agent-config.json:11` `max_open_positions 1`, risk/işlem %1, günlük zarar %3, max kaldıraç 3 (sözleşme 1.1.0 daha yükseğe izin verir: `SKILL.md:115`) | 1 (masa başına tek yuva) | | Tek yuva kuralı |
| a_web3spreads_quant-flow | `src/config.py:75` `max_positions 3`; `strategy/perp.py:232` | 3 | | |
| a_inapp-mobile_clodds / c_alsk1992_cloddsbot | `src/opportunity/executor.ts:134-136` `maxConcurrentPositions 3` (aynı kod iki repoda) | 3 | | |
| c_cyberwei922_ai-trader-paper | `user_data/config.example.json:7` 6; `tools/preflight.py:50,56` 6 değilse reddeder; stake*max ≤ 72 | 6 | | Ön uçuş kapısı |
| c_lnstt369_nightwatcher-v2 | `src/policy/config.ts:103` `DEFAULT_MAX_OPEN_POSITIONS` 10 | 10 | 10 | Aynı |
| c_vedv0987-cloud_bvedtrade | `LIVE_TRADING_CHECKLIST.md:81` `HFT_MAX_POSITIONS 5` ("özsermayenin %90'ı") | 5 | | |
| c_195440_nof1.ai | `README_ZH.md:183,329,382` MAX_POSITIONS 5 (örnek 3) | 5 | | |
| c_shoaibghulam_binance-ai-bot | `app/main.py:173` `max_concurrent_positions` 1–10; `bots/manager.py:57` bot başına 1 | 1–10 | | |
| c_yizhisong_friestrader | `scripts/position_sizing.py:89-92` `max_concurrent_positions` aşılınca aday reddi; README:118 | argüman | | |
| c_filipethome_the-trader-bot | `ui/src/types.ts:176,202` `max_positions`, `pair_cooldown_minutes`, `max_exposure_pct` %60; `README.md:103` | %60 toplam | | |
| c_maxwellcm92_darwinfi | `src/agent/evolution-engine.ts:253,451-452` `maxPositions` 1–6 evrimle ayarlanan, sert kırpma | 1–6 | | Ajan değiştirebilir ama kırpılı |
| c_aria-tjr_llm-crypto-hyperopt | `src/live_trading.py:244,597-599` `MAX_TOTAL_EXPOSURE = 3.0` (x hesap) | 3x | | Poz sayısı değil, maruziyet |
| c_nikhilperr_binance-futures-trading-bot | `modules/regime_detector.py:5-8` rejime göre `max_trades`: BOĞA/AYI 4, YATAY 3, YÜKSEK VOL 1 | 4/3/1 | sabit | Rejime bağlı tavan |
| c_ryanfrigo_kalshi-ai-trading-bot | `cli.py:89` `max_sector_exposure 0.30`; `src/jobs/decide.py:418` poz sayısı tavanı | %30 | | Kalshi (tahmin pazarı) |
| a_dexoryn-china_polymarket-arbitrage-bot (ve dexorynlabs kopyası) | `src/config.py:84,156` `max_open_positions 25`, `max_correlated_positions 4`; `policy/portfolio_risk.py:64` kategori başına maruziyet | 25; 4 | | Polymarket; korelasyon kümesi sayacı |
| c_open-finance-lab_agentictrading | `orchestrator_config.yaml:200` `max_sector_exposure 0.30`; `integration_example.py:218` korelasyon eşiği 0,7 | %30 | | Çoğu örnek/yapılandırma |
| c_ai4finance-foundation_finrl-trading | `src/config/settings.py:104` `max_sector_weight 0.3` | %30 | | |
| c_virattt_ai-hedge-fund | `hedge_fund/fund/example.yaml:36` `max_sector_pct 0.3` (yorumlu), spec doğrulayıcı `test_spec.py:404` (max_beta 0,5, max_volatility 0,15) | %30 | | |
| a_zhulinsen_daily_stock_analysis | `src/services/portfolio_risk_service.py:338-375` sektör maruziyeti hesabı (uyarı) | — | | Raporlama |
| c_coding-kitties_investing-algorithm-framework | `services/strategy_phases/apply_risk_budget.py:15,89`; `risk_rules/exposure_rule.py:23` `max_portfolio_percentage` | örnek 80 | | Kütüphane kuralı |
| c_hkuds_vibe-trading | `skills/earnings-forecast/SKILL.md:93,153` max_positions 10 / 20 (ŞABLON) | 10 / 20 | 10 | Yalnız beceri metni |
| c_tradermonty_claude-trading-skills | `skills/edge-strategy-designer/scripts/design_strategy_drafts.py:74-86` risk profiline göre 3 / 5 / 7 | 3-5-7 | | |
| a_hypurrquant_perp-cli | `src/strategies/funding-arb.ts:37,99` `maxPositions` 3; `agent-operations.md:235` `maxPositionUsd/maxTotalExposureUsd/maxPositions` kodda uygulanır (`enforce-order-risk.test.ts:16`) | 3 | | |
| c_senpi-ai_senpi-skills | `strategies/condor/main/runtime.yaml:58`, `scanners/scan.py:405-435` `maxPositions 1` ("günde bir harika işlem") | 1 | | |
| c_0xethanq_astra-quant-agent, c_suyunjing-su_r20-quantum-trader | `scripts/ai_factor_trader.py:193-214` `MAX_CONCURRENT_POSITIONS_CAP`, `effective_max_positions`; panelde "toplam/aynı yön" (`risk.ts:10`) | sayı okunmadı | | toplam + yön ayrımı |
| c_traderalice_openalice | `src/workspaces/service.ts:217` `MAX_CONCURRENT_HEADLESS 8` (ajan görevleri, pozisyon değil) | 8 | | KONU DIŞI (sayı pozisyon değil) |
| freqtrade ailesi: c_freqtrade_freqtrade, a_syh52_ft-analyzer, a_dieumerci8_freqtrade-strategy-builder, a_sc0vu_freqlint, a_superior-trade_superior-skills, c_6kmfi6hp_ft-userdata-llm-share, c_bachhsunkid_agent-to-earn, c_jgardet_evotrade, c_aleksnovo_freqai-3ai-strategy, c_danny123-sudo_regime-trading-bot, c_jerome-benoit_freqai-strategies, a_remiotore_ccxt-freqtrade, a_roboticautomations_freqtradestrategies, a_loveolu_crypto-strategy-research, c_nateemma_strategies, c_iterativv_nostalgiaforinfinity, a_pellenybe..., a_sak-114514..., c_superior-trade_trading-terminal | `max_open_trades` yapılandırması: örnekler 1/2/3/4/5/6 (freqtrade örnek `config_full.example.json:3` = 3, `config_freqai.example.json:5` = 5; superior-skills 1–3; aleksnovo README:580 = 160!; loveolu perp 9, spot 2; NFI `X.py:27888` boş yuva sayar; QuickAdapter `-1` = sınırsız `README:56`) | 1–10 tipik, bir iki aşırı | 10 | `max_open_trades` küme/korelasyon bilmez, düz sayıdır |
| c_enarjord_passivbot | `src/config/schema.py:49,99` `n_positions` (long 7,0 / short 1,0 varsayılan), `total_wallet_exposure_limit 1,5`; pozisyon başı maruziyet = toplam/n | 7 | 10 | Maruziyet-bölüşümlü yuva |
| c_hummingbot_hummingbot, c_richkuo_go-trader (`backtest_theta.py:15` 2), c_lumiwealth_lumibot (`strangle.py:49` 4, örnek) | örnek/denetleyici sayıları; çerçeve kütüphanesi, politika yok | — | | KONU DIŞI-yakın |
| a_rp7o_trade-foundry | `research/engine/validation-portfolio.ts:24,112` `maxPositions` backtest parametresi | param | | |
| a_millw14_merrymen | `packages/core/src/settings.ts:605,1162` `classMaxPositions` (sınıf başı tavan, varsayılan 0=kapalı) | 0 | küme tavanı | Sınıf başı tavan kavramı var, kapalı varsayılan |
| a_ma-pony_cryptotrader-ai | `runtime_config/models.py:144` `max_total_exposure_pct 1.00`; `runtime.py:742` | %100 | | |
| a_olaxbt_ai-market-maker | `tier1/presets.py:77,164,247` önayara göre işlem başı portföy riski %1/%2/%4; `policy_manager.py:150` ayı rejiminde maruziyet tavanı | %1-4 | | |

### 1b. Karşılaştırma notu (olgu)
- Küme/sınıf tavanı kodda olanlar: hypergrok (küme başı 2), chase-mew (sınıf başı ağırlık), ruiwang cryptobot (ölçülen korelasyon), alta (dayanak başı), merrymen (`classMaxPositions`, kapalı), polymarket-bot (`max_correlated_positions 4`), sektör oranı tavanları (%30: finrl-trading, agentictrading, ai-hedge-fund, kalshi). Düz sayı sınırı çoğunluk (3–8). 10 ve üstü olanlar: nightwatcher 10, polymarket 25, aleksnovo 160 (freqtrade).
- Bizim 10 poz + 6 kümeli yapı, taranan kod tabanında sınıf-kümeli ve çok-üyelikli (bir çift birden çok kümede) en ayrıntılı örnek; ölçülen korelasyon kullanan yalnız ruiwang cryptobot.

## 2. Madde 8 — hisse perp 7/24 mi, NY seansı mı

| Repo | Ne yapıyor (kod kanıtı) | Sayı / pencere | Bizim plan | Fark / not |
|---|---|---|---|---|
| c_chase-mew_ai-hedge-fund (xyz: hisse+emtia+endeks+FX perp) | `src/fund/clock.py:25-32` `tradfi_open`: **kapalı = Cuma 20:00 → Pazar 20:05 New York** (tatiller yok sayılır: satır 2); kapalıyken risk kapısı `no_increase` (artış yok, azaltma serbest) `risk/gate.py:154-158`; `pre_weekend` Cuma 12:00-20:00 NY'de hedef ağırlık tavanı 0,10 (`fund.toml:59`, `gate.py:159-161`); istem: kapalı piyasa "yine işlem görür, fiyat yeniden açılışta boşluk bırakabilir" (`brain/prompts.py:25`). Hafta içi gece seansı (NY 16:00-20:00 arası) AÇIK sayılır; yalnız hafta sonu pencere kapalı | Cuma 20:00–Paz 20:05 NY kapalı; Cuma 12:00 sonrası ağırlık ≤0,10 | NY 09:30–16:00 Pzt–Cum dışında giriş yok | EN YAKIN KARŞILAŞTIRMA: seans = "hafta sonu penceresi", hafta içi gece açık; bizim kural çok daha dar |
| a_julian-dev28_pathiel | `pathiel/client/universe.py:41-43`: "HIP-3 hisse perp'leri yalnız ABD saatinde işlem görür, dışında hacim ~0; … özel saat kapısı UYGULANMAMIŞ" (not, ama aynı projede `desk_tick_sim.py:173-175`: "xyz HIP-3 perp'leri hafta sonunu **kesintisiz** işler"). `universe.py:18-19` kaldıraç: xyz:NVDA 20x, SP500 50x, GOLD 25x; HIP-3 evreni varsayılan KAPALI `enable_hip3` | — | | Aynı repoda iki çelişkili ifade (docstring ↔ sim); önceki "yalnız ABD saati" notu eskimiş görünüyor |
| c_enarjord_passivbot | `docs/stock_perps.md:23-28`: xyz hisse perp "işlem saatleri 24/7", azami kaldıraç 10x, ücret = standardın 2 katı, izole marj; `src/tradfi_data.py:11-14`: TradFi verisi "oracle fiyatı/hafta sonu/after-hours" içermez; `hlcv_preparation.py:1054-1057` TradFi destekli veride hafta sonu/tatil boşluğu toleransı ≥4 gün | 24/7; 10x | | Seans süzgeci yok; boşluk veri tarafında tolere ediliyor |
| c_galleonlabs_hypergrok-trading-desk | `skills/hyperliquid-market-data/SKILL.md:180-186` "HIP-3 hisse, altta yatan piyasa kapalıyken": `oraclePx` deployer referansı, resmi kapanış değil; mark/oracle sapması bps ve `dayNtlVlm` raporlanır; sıfır/ince hacim → `l2Book` kontrol; hafta sonu fonlama için saatlik `fundingHistory` oku, tek değerle yıllıklaştırma | — | | Okuma/gözlem kuralı, giriş kapısı değil |
| a_flukelaster_ai-trading-agent | `backend/app/market/sessions.py:1-40`: varlık sınıfı kuralları; stock: "Pzt–Cum, ABD nakit seansı dışında kapalı", reset 21:00 UTC; kripto 24/7; metal/forex/enerji hafta sonu kapalı, günlük kapanış 22–23 UTC (MT5) | seans tablosu | NY 09:30-16:00 | MT5 (aracı) mantığı, perp değil |
| c_adamcyh_evotrader | `src/evotrader/tools/market_hours.py:1-60`: ET; PRE 04:00, REGULAR 09:30-16:00, AFTER 16:00-20:00, OVERNIGHT 20:00-04:00 (Paz–Per); NYSE tatilleri kuralla üretilir, erken kapanış 13:00; `agents/tools.py:1146-1157,1260` `is_market_open`, `get_market_status` brokerdan | seans sınıfı 5 | 09:30-16:00 | Tatil + erken kapanış takvimi var (bizde yok: spec satır 257) |
| c_ai4finance-foundation_finrl-trading | `src/strategies/adaptive_rotation/utils/calendar_utils.py`, `trading/alpaca_manager.py` takvim/saat (Alpaca) | — | | Alpaca spot hisse |
| a_gacord1213-arch_alpaca-ai-trading-agent / c_alpacahq_alpaca-mcp-server | `overrides.py:81-176` `extended_hours` bayrağı (pre/after-market emir) | bayrak | | Alpaca spot |
| c_ygwyg_mahoraga | `src/policy/engine.ts:121-129`: kripto saat kontrolünden muaf; hisse için `clock.is_open` yoksa ihlal "Trading outside market hours is not allowed" | seans zorunlu (hisse) | | Politika motoru kuralı |
| c_hkuds_vibe-trading | `agent/src/tools/paper_trade/calendar.py:1-60` takvim kapı (hk/us hafta içi aday günleri, tatil sıfır-takvim kapalı varsayım `market_closed_inferred`) | — | | Kâğıt işlem takvimi |
| a_zhulinsen_daily_stock_analysis | `src/core/trading_calendar.py` (Çin/ABD takvimi) | — | | Analiz, işlem yok |
| a_pettekay_ai-forex-trading-bot | `config.py`/`bot.py` seans/haber pencereleri (forex) | — | | Forex |
| a_alexandrelamure_auto-trade | `util/session.py`, `agent/orchestrator.py` seans sınıflama | okunmadı | | Yalnız tarama |
| c_lumiwealth_lumibot | Çerçeve: broker takvimi/`is_market_open` (taramada 170 dosya) | — | | Kütüphane |
| c_nautechsystems_nautilus_trader | Çerçeve: `Commodity` enstrümanı (`crates/model/src/instruments/commodity.rs`), Hyperliquid adaptörü; seans politikası yok | — | | Kütüphane |
| c_enarjord_passivbot, c_hummingbot_hummingbot (`hyperliquid_perpetual_derivative.py:57,66` `enable_hip3_markets=True`), c_nofxaios_nofx (`provider/hyperliquid/kline.go:412-475` xyz hisse/FX/emtia, `coins.go:44`), c_hammergpt_hyper-alpha-arena, c_freqtrade_freqtrade (`exchange/hyperliquid.py`), c_ymcbzrgn_hydraquant | HIP-3 / xyz sembol desteği; seans kapısı kodu bulunmadı | — | | Veri/bağlayıcı seviyesi |
| c_superior-trade_trading-terminal | `lib/market-categories.ts:7-43` xyz ticker "Stocks" sınıfı, `asset-directory.ts` | — | | Arayüz sınıflaması |
| a_henryzhangpku_autonomous-quant-researcher | `research/backtest/overnight.py`, `validators/overnight_spx.py`: SPX **gece** (kapanış→açılış) getiri araştırması | — | | Araştırma, perp değil |

Olgu özeti 8: Taranan kodda hisse perp için "yalnız RTH (09:30-16:00) giriş" kuralı uygulayan repo bulunmadı. chase-mew yalnız hafta sonu penceresinde artışı engelliyor (hafta içi gece açık); pathiel hafta sonunda hisse/emtia perp'in kesintisiz işlediğini yazıyor; passivbot 24/7 diyor; seansı kapı yapanlar (mahoraga, flukelaster, evotrader) spot/aracı (Alpaca/MT5) bağlamında.

## 3. Madde 9 — emtia perp / hafta sonu girişi

| Repo | Ne yapıyor (kod kanıtı) | Sayı | Bizim plan | Fark / not |
|---|---|---|---|---|
| a_julian-dev28_pathiel (petrol/altın/gümüş masaları, xyz:BRENTOIL/CL/GOLD/SILVER) | `services/strategies/weekend.py` + `desks/oil.py`: "weekend flat" yalnız petrol, 2026-11-05'ten beri CANLI: pencere Cuma 16:00–Pazar 18:00 NY (= Cum 21:00–Paz 23:00 UTC kış); yeni giriş yok, açık pozisyon piyasa emriyle KAPATILIR; `place_bracket` reddeder (`agents/desk-tick.md:202-217`). Altın/gümüş HAFTA SONU DONDURULMAZ ("backtest gümüşte kaybetti"). Operatör "hafta sonu elde tut" istisnası var (`desk-tick.md:218-225`). Backtest sonucu (`docs/strategy/BRENT_STOP_BUFFER_TEST_2026-11-02.md:31-82,194-225`): 30 tez ile 24/7=Tut=Flat=$121,78 (hiçbir tez hafta sonuna düşmedi); "hep long" Brent 24/7 $1.057,89 → Tut $1.451,67 → Flat $1.636,42; "hep short" $3,63 → $2,02 / $1,78; gümüş (30 tez) 24/7 $253,36 DD %32 → Tut $319,14 → Flat $200,65; "gümüşte 5/7 kayıp"; karar: "benimsenmedi", sonra operatör petrolde flat'ı açtı. Hafta sonu hacmi: xyz:BRENTOIL 24s $24,9M (pazar 22:00 UTC) vs $218,7M hafta içi; xyz:CL $30,7M vs $230,3M; NATGAS $1,3M vs $15,8M (`desks/oil.py:15-21`). Etkinlik karartması (EIA): girişten 2 saat önce yok (`event_blackout.py:1`); petrol-gümüş saatlik korelasyon -0,36 (`PULLBACK_AND_CORRELATION_TEST_2026-11-02.md:27`) | Cum 16:00–Paz 18:00 NY | Metal 1 + enerji 1; Paz 23:00→Cum 21:00 UTC giriş | EN ÖNEMLİ KARŞILAŞTIRMA: aynı pencere (CME hafta sonu); petrolde flat, metalde serbest; kanıt örneklem küçük |
| c_chase-mew_ai-hedge-fund | emtia sınıfı tavan 0,4 (`fund.toml:64`); hafta sonu penceresinde artış yok + Cuma 12:00'dan sonra |ağırlık| ≤ 0,10 (`gate.py:154-161`); xyz:GOLD, xyz:CL (`fund.toml:122-130`) | 0,10 / 0,4 | | Giriş yasağı yerine ağırlık kısma |
| c_chrisleekr_binance-trading-bot | KRİPTO "weekend gap" giriş tetikleyicisi: `packages/strategy/momentum/src/tick.ts:352-375`, `weekend-gap.ts`, 27 satırlık test; Cuma kapanışına göre Pazartesi boşluğunda alım | — | | Hafta sonu fiyat boşluğunu sinyal olarak kullanıyor |
| a_el-bach_claude-trader | MT5 XAUUSD ajanları (`agents/gold.py`, `gold_watch.py`, CLAUDE.md:38-51) | tek poz | | Aracı CFD, hafta sonu piyasa kapalı |
| a_oyi77_1ai-skills | `trading/xauusd-asia-7c-breakout/SKILL.md` Asya seansı XAUUSD kırılım becerisi | — | | Beceri metni |
| a_flukelaster_ai-trading-agent | metal/enerji hafta sonu kapalı, 22–23 UTC günlük kapanış (`sessions.py:37-41`) | | | MT5 |
| c_openbyteinc_quantdinger | `backend_api_python/app/data_providers/commodities.py` emtia veri sağlayıcı (34 hit) | — | | Veri |
| c_nautechsystems_nautilus_trader | `Commodity` enstrüman tipi | — | | Kütüphane |
| c_traderalice_openalice | FMP emtia spot fiyat modeli (`commodity-spot-price.ts`) | — | | Veri |
| c_hkuds_vibe-trading | `swarm/presets/commodity_research_team.yaml` emtia araştırma ekibi | — | | Araştırma ön ayarı |
| c_enarjord_passivbot | emtia: GOLD, SILVER, COPPER, NATGAS, URANIUM xyz perp listesi (`docs/stock_perps.md:37`) | — | | Liste |
| c_ct (sahip: ct-proje) | `copytrade/coin_sinif.py:5-16` HIP-3 coinleri emtia/endeks/hisse sınıflar (CL, BRENTOIL, GOLD, SILVER, XAU, XAG, NATGAS, COPPER, HG, PLATINUM); `kurallar.yaml:39` takma ad GOLD→XAU | — | | Sınıflama; seans kuralı yok |

## 4. Çoklu varlık yönetimi (sembol evreni, seans, boşluk, bilanço, TradFi funding)

| Repo | Ne yapıyor (kod kanıtı) | Not |
|---|---|---|
| **1l3a (sahip) `/sselimgenc-oss/1l3a-proje`** | `motor/canli/paper_takvim.py:1-50`: hisse = NYSE 09:30-16:00 NY, tatiller + 13:00 erken kapanış; emtia (DK_XAU/WTI/COPPER/XAG/NATGAS) CME Globex benzeri: Pazar 18:00 NY → Cuma 17:00 NY, günlük mola 17:00-18:00, 1 Oca/25 Ara/Büyük Cuma kapalı; "Binance TradFi perp 7/24, Dukascopy araştırma verisi yalnız seanslı → canlı TradFi mumları seans süzgecinden geçirilir (`seans_maskesi`)"; takvim yaklaşık, yanlış-açık = gereksiz bayatlık uyarısı. `motor/risk/limitler.py:25-35` SertLimitler: işlem başı %1, günlük -%3 (UTC), kaldıraç 3x, kill -%20, portföy kolunda toplam açık stop riski ≤ %5. Pozisyon-sayısı/küme tavanı YOK; yoğunlaşma yalnız UYARI (`yogunlasma.py:8`, risk %40'tan fazlası). `DURUM.md:395-397`: "TradFi perp 7/24 vs seanslı araştırma verisi (seans süzgeci varsayımı); TradFi funding backtestte yoktu"; DK_JNJ/DK_MA Binance'te yok → evrenden düştü (satır 216); evren: DK_AAPL, MSFT, GOOGL, AMZN, NVDA, META, TSLA, XAU, WTI, COPPER (`deploy/KURULUM.md:37`); `DURUM.md:386`: "bayatlık eşiğine seans takvimi (hisse hafta sonu)" | Sahibin projesi seans süzgecini girdiyi araştırma verisiyle uyumlu tutmak için kullanıyor (giriş yasağı değil, mum süzgeci) |
| c_ct (`ct-proje`) | Hyperliquid HIP-3 kopya izleme; sınıflama dosyası (bkz. §3); `kurallar.yaml:1` max_leverage 15, radar 20x; pozisyon tavanı anahtarı bulunmadı | Kopya işlem, strateji değil |
| c_chase-mew_ai-hedge-fund | Sembol evreni `fund.toml` (xyz:SP500, XYZ100, NVDA, AAPL, MSFT, TSLA, GOLD, CL, JPY…), sınıf etiketleri stock/commodity/equity_index/fx/crypto, taker ücreti xyz 0,00009 vs çekirdek 0,00045 (`fund.toml:80-83`), kaldıraç 5x, `max_price_gap 0,05`, kâğıt kayma 5 bp | Bizim 44'lü evrene en yakın tasarım |
| a_julian-dev28_pathiel | HIP-3 evreni `universe.py:136-165`; likidite eşiği ">1M $ 24s hacim" masa kayıt kuralı (`desks/oil.py:10-13`); xyz:HO ince ($77k/24s) olduğu için dışarıda; testnette Brent delisted (`oil.py:25-29`) | Hacimle evren eleme (sayısal) |
| c_kyky2347_alta | Hisse/opsiyon: ADV katılım `adv_participation_bps 500`, `max_exit_days 2`, `equity_stress_floor 2500 bp` (`implementation.py:34-59`) | Likidite tabanlı boyut; gap için stres tabanı |
| Bilanço/kazanç: c_alex-jb_orallexa-ai-trading-agent (`engine/earnings.py`), a_satyamdas03_alpaca-trading-agent (`actor-finance-mcp/src/tools/earnings_calendar.py`, `routines/pre_market.md`), c_tradermonty_claude-trading-skills (`pead-screener/scripts/screen_pead.py`, 250 hit), c_hkuds_vibe-trading (earnings-forecast), c_ai4finance-foundation_finrobot (equity-research) | Bilanço takvimi/PEAD araçları var; hisse PERP için "bilanço öncesi giriş yok" kuralı olan repo bulunmadı (EIA karartması yalnız pathiel petrolde: `event_blackout.py:1`) | Bizde de yok (spec:257) |
| Funding (TradFi perp): hypergrok `SKILL.md:185` saatlik fundingHistory; passivbot ücret x2 (`stock_perps.md:27`); chase-mew taker ücret ayrımı; 1l3a "backtestte yoktu" | Kod tarafında TradFi funding'i modelleyen backtest bulunmadı | |
| Pozisyon boyutu/maruziyet: c_aria-tjr (3x hesap maruziyeti), a_el-bach (%2 toplam risk), c_erfaniaa (%60) | | bkz. §1 |

## 5. Binance USDⓈ-M TradFi perp'leri — doğrulanmış / çıkarım

Yöntem: WebSearch özeti (tek sorgu; çoğu haber sitesi bu oturumda erişime kapalı: stablecoininsider.org, onekey.so, theblock.co `ENOTFOUND`; `data.binance.vision` sayfası JS ile yüklendiği için WebFetch boş tablo döndü). Resmî Binance duyuru/spesifikasyon sayfası bu oturumda okunamadı → aşağıdakilerin hiçbiri "birincil kaynaktan doğrulandı" değil.

| Olgu | Durum | Kaynak |
|---|---|---|
| XAUUSDT 7/24 işlem görür; altın spot piyasası hafta sonu kapalı olsa da Binance sürekliliği "özel model" ile fiyatlayarak sağlar | İkincil kaynak özeti (haberler); birincil doğrulanmadı | WebSearch özeti (gncrypto.news, aap.com.au Cision 2026-01-08, theblock 2026-01-08) |
| Fiyat endeksi: altta yatan piyasa saatlerinde çok sağlayıcıdan, saniyede güncellenir; piyasa kapalıyken endeks SON KAYITLI DEĞERDE tutulur | İkincil | aynı |
| Mark fiyat: kapalı saatlerde EWMA ile yumuşatılmış vadeli fiyat | İkincil | aynı |
| Fiyat bandı: mark fiyat endeksten ±%3'ten fazla sapamaz (emtia örneği XAUUSDT) | İkincil; hisse perp bandı bilinmiyor | aynı |
| Funding aralığı/tavan: XAUUSDT için spesifik bilgi bulunamadı; XAG için "4 saatte %2 tavan" iddiası kalitesiz kaynak (doğrulanmadı); hisse-bağlantılı (TEM, MRK, IONQ, MARA, PDD) kontratlar için 8 saatlik uzlaşma ifadesi (onekey, 2026-08-28) okunamadı | Belirsiz | WebSearch özeti |
| Düzenleme/ihraççı: Nest Exchange Limited (ADGM/FSRA tanınmış yatırım borsası); USDT teminatlı | İkincil | aynı |
| 2026-08'e kadar hisse bağlantılı perp listelemeleri sürüyor (TEM, MRK, IONQ, MARA, PDD) | İkincil | onekey başlığı |
| Arşivde sembol var: NVDA (2026-03), XAU (2025-12), XAG (2026-01), BZ (2026-04), COPPER (2026-03) vb. | Bizim spec'te dizin listesi 18 Kasım'da okundu (yalnız adlar) | dd12 spec satır 18-22 |
| `contractType` = TRADIFI_PERPETUAL, kapalı seansta 1 dk mum geliyor mu, halt/devre kesici, hafta sonu davranışı | DOĞRULANMADI (bu ortamdan Binance API 451; spec Adım 0 sunucuda yoklayacak) | spec:26 |
| Hafta sonu / tatil: mark/index "son değerde" ise bar `high==low`/`volume==0` üretmesi beklenir → bizim `flat_bar_guard` mantığıyla uyumlu | ÇIKARIM | — |
| Hyperliquid xyz (rakip, kodla kanıtlı): hafta sonu kesintisiz işler (pathiel `desk_tick_sim.py:173-175`), hafta sonu hacim ~%10 (pathiel `oil.py:15-21`), oracle ≠ resmi kapanış (hypergrok `SKILL.md:182`) | Kod/yorum kanıtı; Binance'e genellenmez | |

## 6. Kapsam

- Evren: `reports/Puanlama matrisi.md` + notlarda geçen + sahibin 1l3a ve ct. Klon dizininde şu an 247 klasör var (198 tur-6 başlangıç klonu + diğer ajanların eklediği `x_*` ve ek `c_*` klonları).
- ELLE OKUNAN (dosya açıldı, satır alıntılandı): chase-mew ai-hedge-fund, pathiel, passivbot, hypergrok, evotrader (adamcyh), mahoraga, nofx, ruiwang cryptobot, alta, nof0 (wquguru), sygnif, flukelaster, el-bach claude-trader, guarded-trader, erfaniaa, 1l3a, ct.
- PATTERN TARAMASI (tavan/seans kelimesi araması; satır alıntılı, tam okunmadı): §1a/§2/§3 tablosundaki diğer tüm repolar; 153 klasörde en az bir eşleşme çıktı (liste `hits`), eşleşmesi saptanan fakat ilgisiz olanlar (ör. nautilus/lumibot/jesse "çerçeve", hsliuping/tradingagents/finrobot "analiz", polymarket botları "tahmin pazarı") KONU DIŞI ya da kütüphane olarak not edildi.
- Eşleşme YOK (bu üç konuda kodda kanıt bulunmadı → "konu dışı / kanıt yok"; yalnız tarama): a_aenger-priv_contextualbandits, a_affaan-m_dprc-autotrader-v2, a_ai-brokers_aibrokers, a_aifore_coinx, a_aksaayyy_ai-bot-earn-or-die, a_alaika-cyber_pumpfun, a_aminhp_gym-anytrading, a_aristidesai_ibkr-aihedge, a_azmax7434_trading-view, a_dax-523_ai-trading-agent, a_dogstailfarmer_martin-binance, a_drakkar-software_octobot-ai, a_dvampire_finagent, a_etrobot_open-alpha-arena, a_furkankoykiran_freqtrade-mcp, a_gaaiyun_freqtrade-strategy-generator, a_janitoff0_ninjatrader-bot, a_kojott_llm-trader-test, a_kukapay_awesome-alpha-arena, a_llmquant_awesome-trading-agents, a_mad1kow-cloud_crypto-intelligence-agent, a_maotouhu_nof1openai, a_masaichig0_tradinggpt, a_milady-ai_plugin-bsc-memes, a_muzafferkadir_claude-crypto-trader-public, a_oficcejo_alpha-arena-okx, a_okay456okay_nof1.ai.monitor, a_p20090504-dotcom_qs-bot, a_pi-2r_quant-science, a_polymarket_agents, a_pranavjadhav1363_plugin-ccxt, a_raphael2025_perp-recap, a_scodive_alpha-arena-prompt, a_snowingfox_open-nof1.ai, a_terryso_nof1-tracker, a_vnavanee_cryptotrader-llm, a_yllvar_quant-autoresearch, a_zeframlou_bagholder, a_zetryn-ai_ai-agent, a_zhangjinhahaha_agentlens, c_backtest-kit_backtest-ollama-crontab, c_danderson197874_apex-crypto-bot, c_microsoft_rd-agent, c_mingyuj666_stockagent, c_parkseokjune_overfit-slayer, c_pipiku915_finmem-llm-stocktrading, c_pulseprotocolorg-cyber_pulse-freqtrade, c_superalgos_superalgos, c_the-finai_fincon, c_the-swarm-corporation_autohedge, c_vnpy_vnpy. (Alpha-arena/nof1 klonları: 6 kripto coin, sınırlı poz; doğrulanmadı, taramada eşleşme yok.)
- Sonradan eklenen `x_*` klonları (örn. x_krakenfx_kraken-cli, x_Dahshan228_FTMO-TradingBot, x_sonirico_go-hyperliquid, x_51bitquant_*, x_qrak_LLM_trader, x_TauricResearch_TradingAgents …) bu görevin kapsamındaki taramaya GİRMEDİ (ayrı ajanlar); `c_51bitquant_*`, `c_qrak`, `c_tauricresearch`, `c_imsatoshi` tarama g8'de yer aldı fakat ilgili eşleşme önemsiz.
- Erişilemeyen: yok (tüm klonlar yerelde). Web: Binance resmî sayfaları ve haber siteleri bu oturumda ağ izni olmadığından okunamadı (§5).
- Sınırlar: (1) §1a'daki bazı varsayılan sayılar `.env`/config dışı env anahtarından okunduğu için "sayı okunmadı" işaretli; (2) tarama deseni `max_*positions|max_open*|correlation|exposure|sector` ile sınırlı, farklı adlandırmalı tavanlar kaçmış olabilir; (3) 1l3a/ct salt okunur incelendi.
