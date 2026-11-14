# Öğrenme Döngüsü Doğrulaması: Hangi Repo Gerçek L4 İçin En İyi Taban?

Yöntem: `git clone --depth 1`, yalnızca okuma/grep (hiçbir kod çalıştırılmadı). Tarih: 2026-11-14.
Klonlar: `/tmp/claude-0/-home-user-SG-Github-AB-proje/e7a4ca7f-2079-5069-8ada-ea4ed3c50c7b/scratchpad/clones/`

## Özet tablo

| Repo | Döngü kapalı mı? | Ne geri besleniyor | Kapı (gate) |
|---|---|---|---|
| astra-quant-agent | **EVET** (tam, kalıcı, LLM-üretimli ders) | Yapılandırılmış "心法" ders kütüphanesi -> canlı karar prompt'u | Anayasa linter + CAS + sağlık skoru ile arşiv; paper-gate YOK |
| NoFxAiOS/nofx | **KISMİ** (yalnız istatistik) | Sharpe/PF/WinRate/MaxDD + son emirler -> prompt | Yok; ders/refleksiyon yok |
| 195440/nof1.ai | **KISMİ** (ham geçmiş) | Son 10 işlem + 10 kapanış özeti + son 3-5 karar metni + Sharpe | Yok; refleksiyon yok |
| wquguru/nof0 | **HAYIR/zayıf** (Sharpe kablolu ama metrik üretimi eksik) | Prompt'ta `ROLLING_SHARPE`; Sharpe ile duraklatma | Sharpe pause (donanım gate, öğrenme değil) |
| TradingAgents | **EVET ama dar** (ders -> yalnız Portfolio Manager) | Sonuçla etiketlenmiş 2-4 cümlelik refleksiyon | Yok; canlı emir yok (analiz kütüphanesi) |

## 1. astra-quant-agent — döngü KAPALI (önceki bulgudaki yer değişti)

Not: önceki bulgudaki `self_improvement_engine.py:31-40` artık `scripts/self_improvement_engine.py:39-40` (dosya `scripts/` altında). `AI_TRADING_MEMORY.md` artık **yetkili kaynak değil, türetilmiş ayna** (salt-okunur uyumluluk; `scripts/evolution_shield.py:348-365`). Yetkili kaynak: `data/structured_trading_memory.json` (`evolution_shield.py:51`).

Uçtan uca akış:
1. **Sonuç kaydı**: kapanmış işlemler `load_closed_trades()` — `scripts/self_improvement_engine.py:431` (hesap sıfırlama zamanı ve `ASTRA_EVOLUTION_START_TIME` filtreli).
2. **Ders üretimi**: `compose_evolution_prompts()` (`:660`) mevcut hafızayı + kapalı işlemleri + çok boyutlu döküm (`_compute_multi_dimensional_breakdown :579`, `derive_deterministic_insights :941`) LLM'e verir; `call_llm_evolution_review()` (`:752`). Mevcut hafıza `memory_service.read_trading_context` ile okunur (`:1091`). Zamanlama: günde 4 kez 02/08/14/20 (`astra_backend/schedule_store.py:14`).
3. **Yazma + kapılar**: `publish_review()` (`evolution_shield.py:499`) -> `audit_proposed_lesson()` (`:154`; anayasa kırmızı çizgileri, emekli faktör referansı reddi) -> `_validate` (`:212`) -> `_commit` (`:415`), `expected_version` ile CAS (`:431`). Ardından `refresh_health_from_evidence()` (`:517`) dersin sağlık skorunu **kapanmış işlem kanıtından** yeniden hesaplar ve kötü dersleri arşivler (`enabled=False`; silmez, temel dersleri korur). Çağrı: `self_improvement_engine.py:1215`.
4. **Enjeksiyon**: `scripts/brain/prompt.py:276-278` `render_trading_memory()` -> `runtime_vars["trading_memory"]` (`:371`) -> `{{trading_memory}}` slotu (`prompt_library.py:114`, `brain/dispatch.py:90`). `scripts/ai_brain_trader.py:592-593` hafıza dosyalarını bu fonksiyona geçirir; canlı emir bu prompt'tan çıkar.
5. **Sürümleme/denetim**: `astra_backend/policy/capture.py:128`, `policy/fingerprints.py:150` hafıza sürümünü politika parmak izine alır.

Önemli ayrım: `ai_factor_trader.py` hafızayı **hiç okumuyor** (grep boş) — döngü `ai_brain_trader.py` hattında kapalı, factor trader hattında değil.
Eksik (L4 için): paper/shadow performans kapısı yok (yeni ders canlıya anında çıkar, kanıt = geçmiş sağlık skoru); A/B veya geri alma kuralı yok; yalnız metin dersi, parametre güncellemesi yok.

## 2. nofx — KISMİ

- Kayıt: `store.Position().GetFullStats()` — `trader/auto_trader_loop.go:683`; `kernel.TradingStats` doldurulur `:692-701`; son emirler `:670` (`ctx.RecentOrders`).
- Enjeksiyon: `kernel/engine_prompt.go:781-852` (son işlemler) ve `:797-852` "Historical Trading Statistics" (Sharpe, PF, WL oranı) + sabit kodlu ipucu ("GOOD / NEEDS IMPROVEMENT / HIGH RISK"). Aynı mantık `kernel/formatter.go:57-72,134-172`.
- Yani döngü kapalı ama **yalnız sayısal özet**; LLM'in ürettiği ders, gerekçe-sonuç etiketleme, hafıza yok. Politika (strateji config) kendiliğinden değişmez. `store/strategy.go` ve `store/decision.go` var -> sürümlü strateji eklemek için iyi kanca.

## 3. nof1.ai — KISMİ

- Kayıt: `scheduler/tradingLoop.ts:1574-1576` `getTradeHistory(20)`, `:1584` `getRecentDecisions(5)`; Sharpe `calculateSharpeRatio :554-598` (equity geçmişinden).
- Enjeksiyon: `agents/tradingAgent.ts:393-420` (son işlemler + kapanış özeti: win-rate, long oranı, net PnL), `:425-440` (son 3 karar metni), `:1161-1163` (Sharpe). Yardımcılar `agents/tradeHistoryUtils.ts:26-97`.
- Refleksiyon/ders yok; sadece kısa vadeli "kendi geçmişini göster". Tek bir prompt hattı, basit -> hafif ama dersler kalıcı değil.

## 4. nof0 — HAYIR / zayıf

- Prompt şablonu `etc/prompts/executor/default_prompt.tmpl:48,74` `ROLLING_SHARPE`; `pkg/executor/prompt_build.go:24,72` özetler (`sharpe, win_rate, trades, recent_rate`).
- Ancak `pkg/manager/trader.go:82` `RecentTradesRate: 0, // TODO`; `docs/engine.md:312` ve `docs/verification.md:107` metriklerin yer tutucu olduğunu belirtiyor; `UpdatePerformanceMetrics` kodda bulunamadı (yalnız dokümanda, `docs/engine-data-store.md:131`). `Performance.SharpeRatio` yalnız snapshot geri yüklemesinden doluyor (`manager.go:382`).
- Sharpe tabanlı duraklatma gerçek (`manager.go:469-477`) — bu bir risk freni, öğrenme değil. Ders/refleksiyon yok.

## 5. TradingAgents — KAPALI ama dar kapsamlı

- Kayıt: `graph/trading_graph.py:368` `memory_log.store_decision(...)` (bekleyen karar, `memory/log.py:32`).
- Sonuç etiketleme: `memory/settlement.py:136` `settle_pending` -> `fetch_returns` (`:60-125`, ham getiri + benchmark'a göre alpha, çözüm tarihi) -> `Reflector.reflect_on_final_decision` (`memory/reflection.py:37-63`, 2-4 cümle, sonuç+alpha ile) -> `memory_log.update_with_outcome` (`settlement.py:179`).
- Okuma: `trading_graph.py:330` `get_past_context(ticker, n_same=5, n_cross=3, as_of)` (`memory/log.py:93`) -> state `past_context` (`agents/state.py:71`) -> **yalnız** `agents/managers/portfolio_manager.py:35-38` prompt'una girer (diğer analistler görmez).
- Güçlü yan: `as_of` filtresi (`log.py:96-103`) look-ahead sızıntısını engeller; `backtest.py:170-214` ile geriye dönük koşturulabilir. Zayıf: canlı emir/broker yok, ders sentezi/konsolidasyon yok (ham log büyür), kapı yok.

## L4 döngüsü ekleme zorluğu ve kanca noktaları

Hedef döngü: sonuç-etiketli işlem günlüğü -> periyodik refleksiyon -> sürümlü prompt/parametre güncellemesi -> paper performans kapısı -> canlıya terfi.

| Repo | Zorluk | Nereye kanca |
|---|---|---|
| astra | **Düşük-orta** (iskelet hazır) | Eksik parça yalnız paper kapısı: `evolution_shield.publish_review()` (`:499`) içinde yeni dersi `enabled=False/shadow` yaz, `policy/capture.py` parmak iziyle shadow ve canlı sonuçlarını karşılaştır, N işlem sonra `refresh_health_from_evidence` ile terfi/arşiv. `{{trading_memory}}` slotu `brain/prompt.py:276` zaten tek enjeksiyon noktası. Parametre güncellemesi için `risk_constants.py`/`order_risk.py` eklenmeli. |
| nofx | Orta | `GetFullStats` çıktısını + `store/decision.go` kayıtlarını reflektöre ver; çıktıyı `store/strategy.go` yeni sürüm olarak yaz; `kernel/engine_prompt.go:797` yanına "lessons" bölümü. Go ve çok kullanıcılı yapı iş yükünü artırır. |
| nof1.ai | Orta | `tradingLoop.ts:1574-1584` yanına reflektör cron'u; ders tablosu SQLite'a; `tradingAgent.ts:393` yanına enjeksiyon. Küçük ama sürümleme/gate sıfırdan. |
| nof0 | Yüksek | Önce metrik üretimini gerçekten bitirmek gerekir (`trader.go:82`, `UpdatePerformanceMetrics`). |
| TradingAgents | Orta | Zaten `settle -> reflect -> inject`; eksik: broker, ders konsolidasyonu, diğer ajanlara enjeksiyon, paper kapısı (`backtest.py` buna uygun). Canlı yürütme katmanı sıfırdan. |

## Sıralama (L4 tabanı olarak)

1. **astra-quant-agent** — tek gerçek, canlı emir yoluna bağlı, kalıcı, kapılı ve sürüm/CAS destekli döngü. Eksik tek büyük parça paper/shadow kapısı. Dikkat: `ai_factor_trader.py` yolu döngüsüz; `ai_brain_trader.py` kullanılmalı. Kod büyük ve Çince yorumlu (bakım maliyeti).
2. **TradingAgents** — en temiz "sonuç etiketli refleksiyon" tasarımı (alpha, as_of anti-sızıntı, backtest); bu desen astra'ya taşınabilir/ödünç alınabilir ama canlı emir katmanı yok.
3. **nofx** — iyi canlı altyapı + istatistik geri beslemesi; ders katmanı sıfırdan.
4. **nof1.ai** — basit ham geçmiş geri beslemesi.
5. **nof0** — geri besleme çoğunlukla iskelet/TODO.

Öneri: astra'nın `ai_brain_trader` hattını taban al, TradingAgents'tan `as_of`-filtreli, alpha-etiketli sonuç çözümleme (settlement) desenini al, ve astra'ya shadow/paper terfi kapısı ekle.

Sınırlar: statik okuma; hiçbir şey çalıştırılmadı, bu yüzden dersin runtime'da gerçekten dolu olup olmadığı (örn. boş hafıza durumu) doğrulanmadı.
