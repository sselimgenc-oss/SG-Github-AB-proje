# Gizli cevherler (20-1500 yıldız) - Tur 4 avı

Tarih: 2026-11-14. Yöntem: GitHub arama (yıldız 15-1500, 2026 push, ~60 sorgu; İngilizce + Çince), sonra 12 repo `git clone --depth 50` ile okundu (çalıştırılmadı, kurulmadı). Önceki turlarda bakılan repolar (nofx, tradememory, astra-quant-agent, darwinia, evotrader, LLM_trader vb.) ve büyük çatılar (freqtrade/FreqAI, OctoBot, jesse, hummingbot, Superalgos, intelligent-trading-bot) bilerek atlandı.

## Dürüst özet

Bu yıldız aralığında "kendi başına strateji bulan + işlem açıp kapatan + gerçekten öğrenen + olgun" bir repo bulunamadı. Doğrulanmış öğrenme döngüsü olan iki repo var, ikisinin de kendi sorunu var: AmpyFin (sadece ABD hissesi, MongoDB gerekir, son commit Ekim 2025) ve TorchTrade (RL çatısı, kod bilgisi şart). Kripto tarafındaki "AI ajan" botların çoğu öğrenmeyi yalnızca son 5-10 kararı LLM'e tekrar göstermek olarak yapıyor; bu parametre öğrenmesi değil, kısa hafıza.

Yıldız sayıları (Tur 4'te görülen): AmpyFin 428, TorchTrade 428, go-trader 367, go_binance_futures 257, Hyper-Alpha-Arena 1200, Orallexa 72, LLM-Auto-Trader 48, ai-hedge-fund 97 (chase-mew), okx-2pa-agent-web 28.

## Rubrik tablosu (1-5, 5 en iyi)

| Repo | Piyasa | Otonomi | Öğrenme (doğrulanmış) | Kanıt | Olgunluk | Güvenlik | Kullanım kolaylığı | Toplam /30 |
|---|---|---|---|---|---|---|---|---|
| chase-mew/ai-hedge-fund | Hyperliquid (BTC/ETH + TradFi perp) | 4 | 2 | 4 | 3 | 5 | 2 | 20 |
| AmpyFin/ampyfin | ABD hissesi (Alpaca) | 4 | 4 | 2 | 4 | 3 | 2 | 19 |
| TorchTrade/torchtrade | Binance/Bybit/OKX/Alpaca | 4 | 4 | 2 | 4 | 4 | 1 | 19 |
| richkuo/go-trader | Binance US/OKX/HL (50+ hazır strateji) | 3 | 1 | 3 | 5 | 4 | 3 | 19 (öğrenmiyor) |
| Erfaniaa/LLM-Auto-Trader | Binance/Bybit/OKX (CCXT) | 4 | 2 | 2 | 3 | 4 | 3 | 18 |
| alex-jb/orallexa-ai-trading-agent | ABD hissesi (Alpaca paper) | 3 | 3 | 3 | 3 | 4 | 2 | 18 |
| sorry510/go_binance_futures | Binance spot/futures | 4 | 2 | 3 | 4 | 3 | 2 | 18 |
| HammerGPT/Hyper-Alpha-Arena | Binance Futures + HL testnet | 3 | 2 | 2 | 2 | 3 | 4 | 16 |
| oficcejo/okx-2pa-agent-web | OKX (demo/gerçek) | 4 | 1 | 1 | 2 | 3 | 3 | 14 |

Not: Güvenlik ve kullanım puanları kodda gördüklerime dayanır; hiçbirini çalıştırmadım.

## Repo bazında kısa notlar

### 1) chase-mew/ai-hedge-fund (97 yıldız) - en dürüst repo
- README iddiası: Her 4 saatte Claude hedef ağırlık/stop/tez üretir, deterministik risk kapısı filtreler, her şey günlüğe yazılır ve yayınlanır. "Backtest yok, yüzlerce döngüye kadar sonuç anekdottur" diyor.
- Kodda doğrulandı: `fund.toml:7` autonomy = "approve" (varsayılan, insan onayı bekler); `venues/hyperliquid.py:41` mainnet için `FUND_ALLOW_MAINNET=yes` şart; `cli.py:57` mod paper/testnet/live; `brain/decide.py:50` karar fonksiyonuna `TrackRecord` (son kararlar + Brier skoru, `contracts.py:159`) veriliyor, yani geçmiş isabet LLM'e geri besleniyor. CI var, 19 test dosyası, 51 commit (Ocak 2025 - Ekim 2026), tek yazar.
- Eksik: öğrenme sadece "geçmişi prompt'a koy" düzeyinde; Binance/OKX/Bybit yok (Hyperliquid); kurulum uv + Python 3.13. Sahte LLM ile anahtarsız deneme modu var (`--fake-llm`).

### 2) AmpyFin/ampyfin (428 yıldız) - ABD hissesi, gerçek geri besleme döngüsü
- README iddiası: "Sıralı topluluk öğrenmesi, her stratejinin performansına göre etkisini dinamik ayarlar"; NASDAQ-100.
- Kodda doğrulandı: `TradeSim/ranking.py:98-198` simüle işlemlerden puan (`points_tally`, `time_delta`) üretiyor; `TradeSim/trading.py:274-300` `initialize_strategy_coefficients` MongoDB'deki rank -> katsayıyı okuyup canlı kararlara uyguluyor. Yani sim sonuçları -> sıralama -> canlı ağırlık zinciri gerçek. `docs/configuration.md:127` varsayılan Alpaca paper URL. 4 yazar, CI, `tests/` var (sadece 1 test dosyası).
- Eksik: son commit 2025-10-27 (GitHub'da 2026 push görünse de kod durağan); MongoDB zorunlu; yfinance; yayınlanmış canlı sonuç doğrulanamadı; kripto yok.

### 3) TorchTrade/torchtrade (428 yıldız) - RL çatısı
- README iddiası: PPO/DQN/GRPO, Binance/Bybit/OKX/Alpaca canlı ortamları, "araştırmadan üretime aynı kod". "Work in progress" uyarısı dürüst.
- Kodda doğrulandı: `torchtrade/envs/live/binance/order_executor.py:73` `demo: bool = True` (güvenli varsayılan); 106 test dosyası, 4 CI iş akışı, mkdocs. Polymarket için "paper-only" notu README'de çok dürüst.
- Eksik: hazır ajan yok; modeli kullanıcı eğitmeli (kod bilgisi şart). Eğitim çevrimdışı; canlıda kendini yeniden eğiten döngü hazır değil. Türkiye'de teknik olmayan kullanıcı için uygun değil.

### 4) richkuo/go-trader (367 yıldız) - olgun ama öğrenmiyor
- README iddiası: 50+ strateji, paper ve live, Discord/Telegram uyarıları, Docker.
- Kodda doğrulandı: 477 test dosyası, 4 CI, 50+ commit/2 haftada; `config.example.json` örnekleri `--mode=paper`. Öğrenme/optimizer/otomatik ayar dosyası yok (`scheduler/`, `shared_tools/` tarandı; yalnızca `regime.go` rejim kapısı var). Stratejiyi kullanıcı menüden seçiyor, Binance US destekli (Türkiye uygun değil).
- Karar: altyapı ödünç alınabilir ama "öğrenen" değil.

### 5) Erfaniaa/LLM-Auto-Trader (48 yıldız)
- README iddiası: LLM karar verir, kurallar uygular; paper varsayılan; "önceki karar nasıl sonuçlandı" bağlamda.
- Kodda doğrulandı: `src/bot.py:274` `paper_mode=not self.settings.is_live`; `src/llm/memory.py` son 5 karar + 10 işlem, `outcome/pnl` sonradan doldurulur (bellekte `deque`, kalıcı değil); `src/risk/circuit_breakers.py` bağımsız devre kesici (max drawdown %5). 55 test dosyası, CI, 35 commit (Mart-Temmuz 2026), tek yazar.
- Eksik: gerçek parametre öğrenmesi yok; yayınlanmış sonuç yok.

### 6) alex-jb/orallexa-ai-trading-agent (72 yıldız) - dikkat
- README iddiası: "Kendini ayarlayan", kaynak doğruluğuna göre ağırlık uyarlama, yayınlanmış Brier kaydı, 333 test.
- Kodda doğrulandı: `engine/dynamic_weights.py` rolling accuracy -> ağırlık çarpanı gerçekten var; ama `engine/signal_fusion.py:484` `use_dynamic_weights: bool = False` -> varsayılanda KAPALI. `bot/alpaca_executor.py:32` yalnızca Alpaca paper URL'si. 99 test dosyası, CI, ama README rozet ağırlıklı ve repo 2 aylık (Mayıs-Temmuz 2026), tek yazar.
- Eksik: ABD hissesi, sadece paper, öğrenme varsayılan kapalı.

### 7) sorry510/go_binance_futures (257 yıldız) - Çince, Binance
- README iddiası: AI ajan + vadeli quant + simülasyon + backtest; AI ile strateji üretimi.
- Kodda doğrulandı: README:134 "gerçek Spot Testnet BUY->SELL->CLOSED döngüsü doğrulandı, Mainnet emirleri ve üretim şeması DOĞRULANMADI" (çok dürüst). `agent/memory` içinde `TypeLesson` var ama sonuca bağlı otomatik ders çıkarma görmedim; strateji şablonları kullanıcı/AI tarafından tanımlanıyor. 235 test dosyası, 2 yazar, çok hızlı geliştirme (2 ayda 90+ commit).
- Eksik: arayüz Çince, MySQL önerilir; öğrenme doğrulanmadı.

### 8) HammerGPT/Hyper-Alpha-Arena (1200 yıldız)
- README iddiası: LLM'ler Hyperliquid ve Binance Futures'ta otonom işlem; 86 faktör; işlem atıf analizi; yapay zekayla faktör madenciliği; "hosted login kapatıldı".
- Kodda doğrulandı: `backend/services/ai_decision_service.py` kullanıcının yazdığı prompt'a göre karar; `hyper_ai_memory_service.py` kullanıcı sohbet belleği (max 50 kayıt, "lesson" kategorisi); `ai_attribution_service.py` atıf analizini insana gösterir (otomatik geri besleme yok). GitHub'da tek squash commit (geçmiş görülemiyor), 1 test dosyası.
- Eksik: strateji prompt'unu kullanıcı veriyor (Otonomi 3); olgunluk kanıtı zayıf. Kullanımı en kolay (Docker, arayüz, Hyperliquid testnet) olan bu.

### 9) oficcejo/okx-2pa-agent-web (28 yıldız)
- Kodda doğrulandı: README:180-186 `OKX_DEMO_TRADING=true` varsayılanı ve `ENABLE DEMO` kilidi; LLM sabit bir fiyat-aksiyonu prompt'u ile karar verir. Öğrenme yok. Kırmızı bayrak: repoda `web.rar`, README'de yönlendirme (referral) bağlantısı, tek yazar, CI yok.

## Reddedilenler (tek kelime sebep)

| Repo | Sebep |
|---|---|
| Shelpid/SETS | Simülasyon (tarayıcıda, borsa bağlantısı yok; 1 commit) |
| imsatoshi/GeneTrader | Optimizer (işlem açmıyor, README kendisi söylüyor) |
| squidKid-deluxe/QTradeX | Çatı (strateji kullanıcıdan) |
| rmbell09-lang/tradesight | Dağınık/ticari (Gumroad satışı, yapay zekâ yazımlı denetim notları, sadece paper) |
| DogsTailFarmer/martin-binance | Strateji-kullanıcıdan (martingale/grid, "adaptif" yalnızca parametre) |
| TheFourGreatErrors/alpha-rptr | Strateji-kullanıcıdan |
| 51bitquant/binance_grid_trader | Strateji-kullanıcıdan (grid) |
| Markfans/cryptoquant-ai | Şüpheli (2 commit) |
| stefanoviana/deepalpha | Şişirilmiş iddia ("%84.9 doğruluk") |
| bigmacman1129/*, aitradingbotspro/* | Klon/spam (aynı açıklamalar, çoklu hesap) |
| SnowCheetos/AutoMoonBot | Terk edilmiş (son commit 2024) |
| wolfinch/wolfinch | Eski (genetik optimizer var ama bakımı seyrek, 3 test) |
| ryan-yuuu/crypto-trading-arena | Sanal arena (gerçek emir yok) |
| QuantiaAI/helm-agents | Öğrenme yok (4 commit, LLM tartışma masası) |
| zero-was-here/tradingbot | Kapsam dışı (altın/forex, MT5; bakılmadı) |
| howdymary/autopredict, openthomas, Polymarket/Kalshi botları | Kapsam dışı (tahmin pazarı) |
| MT5/XAUUSD scalper EA'ları | Kapsam dışı (forex/altın, MQL5) |
| mikegianfelice/Hunter, Paldo-ALM | Doğrulanmadı (zincir üstü/şişirilmiş açıklama; klonlanmadı) |
| nof1-türevleri (Oakshen, web3spreads/quant-flow vb.) | Zaten kapsanmış (Tur 3 sınıfı) |

## Arama notları
- GitHub arama indeksi bu aralıkta ince: çok kelimeli sorgular çoğunlukla boş döndü; tek kelime + `topic:` sorguları verimli oldu.
- `gh api repos/.../contributors` 403 verdi (oturum erişimi yok); yazar sayıları `git shortlog` ile (--depth 50 içinde) sayıldı, bu yüzden büyük repolar için eksik olabilir.
