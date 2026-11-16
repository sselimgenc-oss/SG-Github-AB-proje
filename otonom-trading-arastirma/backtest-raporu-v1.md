# TraderV1 backtest değerlendirmesi (plan madde 14) — rapor v1

_Tarih: 16 Kasım 2026 · Strateji: `TraderV1` (kural mantığı, risk/rejim/defter modülleri ve parametre varsayılanları DEĞİŞTİRİLMEDİ) · HOLDOUT (20260501–20261101) ve Kasım 2026 BU RAPORDA ÇALIŞTIRILMADI._

## 0. Sade dilde özet

* **Geleceği görme (lookahead) / özyinelemeli (recursive) hata yok.** Göstergelerde hiçbir sızıntı bulunmadı (en büyük özyineleme sapması %0,003). Çiftler birlikte koşulunca freqtrade tek bir "biased entry" işaretledi; bunun nedeni portföy bağlaşımı (çiftler arası risk kilidi), gerçek sızıntı değil — çift başına koşularda 313 işlem sinyalinde (1h: 193, 15m: 120) sıfır sorun çıktı. Ayrıntı §2. Bu yüzden durdurma koşulu tetiklenmedi.
* **Ana karar kolunda (komisyon ×2 + 2 bp kayma, funding açık) strateji para kazandırmıyor.**
  * **1h tetik:** IS 627 işlem, beklenti **-0,091 R** (%95 GA -0,24 … 0,06), PF 0,79, maks. düşüş %66,2; WF 374 işlem, **-0,055 R** (GA -0,22 … 0,11), PF 0,93, maks. düşüş %39,3. Güven aralıkları sıfırı içeriyor: "kesin zararlı" da "kârlı" da denemez; ancak tahmin noktası iki dönemde de negatif.
  * **15m tetik:** IS 904 işlem, **-0,259 R** (GA -0,35 … -0,17), PF 0,58; WF 745 işlem, **-0,400 R**, PF 0,44. Hesabın ~%90'ı eriyor. 15m kolu **her maliyet varsayımında negatif** (en ucuz kolda bile IS −0,07 R, WF −0,19 R) → 15m tetik bu haliyle elenmeli.
* **Maliyet belirleyici.** 1h kolunda brüt (maliyet öncesi) PnL pozitif ama komisyon+kayma+funding onu eritiyor: ana kolda maliyet/brüt IS 5,7×, WF 1,3×. En ucuz kolda (×1 komisyon, 0 bp) 1h beklentisi IS +0,018 R, WF +0,063 R (PF 0,96 / 1,10) — başabaş civarı, gerçek kenar kanıtı değil. Kayma varsayımı (0/2/5 bp) sonucu işaret değiştirecek kadar etkili.
* **Risk kilidi ihlali yok:** hiçbir işlemin gerçekleşen zararı giriş anındaki özsermayenin %2'sini aşmadı (tüm koşularda en yüksek ≈ %1,5; hedef %1,4). Ancak zararların çoğu planlanan riskin biraz üstünde (medyan R ≈ −1,01…−1,03; maliyet + boşluk) — bu ihlal değil, bilgi (§7.2).
* **Defter ↔ freqtrade tutarlı** (eşleşen işlemlerde brüt PnL ve komisyon birebir; fark yalnız funding anlık görüntüsünden, ≤ 0,15 USDT/işlem). Tek tutarsızlık: 1h koşusunda aynı mum içinde stop sonrası yeniden girişlerin (IS'te 1, WF'de 3 işlem) deftere yazılamaması (§7.1).
* **Parametre taraması (yalnız IS, 1h, ana kol): varsayılanlar korundu.** `stop_buffer_atr` {0,2; 0,3; 0,4} ve `trail_atr` {2,5; 3,0; 3,5} denendi; komşu değerler kararsız/gürültü içinde (en iyi fark ≈ +0,07 R ≈ 1 standart hata; stop_buffer'da eğri monoton değil) ve hiçbiri pozitif beklenti üretmedi (§6).
* **Teknik bulgular (önemli):** (1) 15m tetik **canlıda başlayamaz**: startup 4800 mum, freqtrade Binance 15m için ≤2494 mumu kabul ediyor (ConfigurationError). (2) `lookahead-analysis`/`recursive-analysis` `RunMode.UTIL_NO_EXCHANGE` ile çalışır ve TraderV1 bunu "canlı" sayıp girişleri kapatır (0 işlem) — analiz için yalnız çalışma modunu eşleyen bir alt sınıf kullanıldı. (3) IS fiilen **2024-12-21**'de başlıyor (1200/4800 mum ısınma). (4) Kayma freqtrade'de yok; komisyona eklenerek yaklaşıklandı.

## 1. Kapsam, yöntem ve koşu kurulumu

| Konu | Uygulama |
|---|---|
| Strateji / parametre | `TraderV1`, `trader_v1.params` varsayılanları (range_width_atr 4.0, vol_ratio_max 1.5, edge_zone_atr 0.25, pullback_ema 50, stop_buffer_atr 0.3, trail_atr 3.0, range_target_frac 0.75, rr_min 1.5); yalnız `trigger_tf` (1h/15m) ve sweep'teki parametre config üst-katmanıyla (`research/…/overlay.json`) değiştirildi |
| Evren | `config/base.json` beyaz listesi: BTC, ETH, BNB, SOL, XRP, DOGE, ADA, TRX, LINK, AVAX (USDT-M perpetual), kaldıraç 3×, izole, cüzdan 1000 USDT |
| Dönemler | **IS** 20241101–20251101, **WF** 20251101–20260501. **HOLDOUT 20260501–20261101 çalıştırılmadı**; Kasım 2026 hariç. (Koşucu, 20260501 sonrası zaman aralığını reddeder.) |
| Maliyet kolları | Komisyon ×1 (%0,05/taraf) ve ×2 (%0,10/taraf) × kayma 0/2/5 bp/taraf. **freqtrade backtest'te kayma seçeneği yoktur** → kayma, `--fee`'ye eklenerek yaklaşıklandı: `fee_eff = 0,0005×çarpan + kayma_bp/1e4` (giriş ve çıkışta ayrı uygulanır). Funding açık (Binance 8 saatlik funding + mark verisi; IS/WF aralığında boşluk yok). **Ana karar kolu: ×2 + 2 bp (`fee_eff` %0,12/taraf).** (×1+5bp ile ×2+0bp aynı `fee_eff`=%0,10 → koşular birebir aynı çıktı; bu bir determinizm doğrulamasıdır.) |
| Tetik kolları | 1h (`--timeframe-detail 15m` ile) ve 15m (**5m detay verisi yok** → mum-içi sıra belirsizliği 15m kolunda daha kaba; bkz. §8) |
| Çıktı | Ham sonuçlar `user_data/backtest_results/<id>/` (gitignore'da; git'e girmez); özet JSON `research/runs/<id>.json`; deneme kaydı `research/trial_registry.csv` |
| R tanımı | R = `profit_abs / risk_tutarı`; risk tutarı = **fiilen açılan miktar** için `loss_at_stop(miktar, giriş, planlanan_stop)` (risk modülünün maliyet varsayımıyla: %0,05 komisyon + %0,05 kayma/taraf). Defter `planned_risk` değeri işlemlerin ≈%2'sinde (çoğunlukla BTC/DOGE/XRP; %2–20) fiilî miktarın riskinden yüksek çıktı (miktar yuvarlama/kısma olası neden; §8, madde 1) → birincil R olarak fiilî miktar kullanıldı; defter R'si de karşılaştırıldı (ortalama mutlak fark < 0,01 R) |
| Maliyetler | `komisyon+kayma` = `miktar×(giriş×fee_open + çıkış×fee_close)`; `funding` = freqtrade `funding_fees` (işaret: + alınan, − ödenen); `brüt PnL` = `profit_abs + komisyon+kayma − funding` |
| Eniyileme yasağı | Toplam getiri, kazanma oranı ve Sharpe üzerinde seçim yapılmadı; karar ölçütleri: beklenti (R), PF, maks. düşüş, işlem sayısı ve kararlılık |

**Araç/yöntem notları:** `research/run_bt.py` (koşucu + metrik), `research/queue.sh` (4 paralel), `research/ft_offline_15m.py` (yalnız 15m: startup-mum korumasını atlayan yama), `research/strategies/TraderV1Analysis.py` (yalnız lookahead/recursive için çalışma-modu eşlemesi), `research/build_registry.py`, `research/make_report.py`. Tüm koşularda defter (`ledger_path`) **her koşu için yeni geçici dosya** olarak açıldı; aynı ayda defterli/deftersiz koşunun birebir aynı 81 işlemi verdiği doğrulandı (defter alım-satım davranışını değiştirmiyor). Bu sayede rejim, planlanan stop ve defter R'si her işleme bağlanabildi.

## 2. Adım 1 — Lookahead ve recursive analiz

| Test | Komut özeti | Sonuç |
|---|---|---|
| lookahead, TraderV1 doğrudan | `lookahead-analysis --timerange 20250501-20250801` | **Teknik bulgu:** 0/10 işlem; "too few trades". Neden: komut `RunMode.UTIL_NO_EXCHANGE` ile çalışır; `TraderV1._is_bt` yalnız BACKTEST/HYPEROPT'ta doğrudur → "canlı yol" → `_gate()` → `ledger_unconfigured` → giriş yok |
| lookahead, `TraderV1Analysis` (yalnız `_BACKTEST_MODES`'a UTIL_NO_EXCHANGE eklenir; sinyal/risk/çıkış kodu aynı) — 10 çift birlikte | 208 işlem, ilk 20 analiz | `has_bias: Yes` — **1 biased entry** (ADA/USDT 2025-05-03 13:00→17:00), 0 biased exit, **0 biased indicator** |
| aynı, her çift ayrı (1h) | 10 koşu, 193 işlem analiz | **0 biased** (entry/exit/indicator) |
| aynı, 15m tetik, her çift ayrı | 10 koşu, 120 işlem analiz | **0 biased** |
| recursive, 1h, 10 çift ayrı | `--startup-candle 200 400 800` (strateji 1200) | "No variance … found due to recursive formula"; en büyük sapma `atr_ratio` %0,003 (200 mum), 400/800/1200'de %0,000; "No lookahead bias on indicators" |
| recursive, 15m (BTC, SOL) | aynı | en büyük sapma %0,003; lookahead yok |

**Tek işaretin açıklaması (yanlış pozitif — portföy bağlaşımı):** freqtrade'in testi tam koşudaki işlemi, veriyi o işlemin mumuna kadar kesip **yalnız o çiftle** yeniden koşarak arar. TraderV1'in risk kilidi çiftler arası bağlıdır (aynı yön risk sınırı %4, toplam açık risk %6, özsermaye). Tam koşuda ADA'nın 05:00 sinyali "aynı yön (long) risk sınırı aşılır" ile reddedildi (DOGE/ETH/XRP long açıktı), ADA ancak 13:00'te girdi; kesilmiş tek-çift koşuda 05:00 girişi serbest kaldı ve pozisyon 13:00'te zaten açıktı → 13:00 girişi "kayboldu". Doğrulama: ADA tek-çift tam koşuda 05:00 girişi var; çoklu koşuda `risk reddi ADA … aynı yön (long)` günlüğü var; **gösterge sütunlarının hiçbiri** (`biased_indicators` boş) kesik/tam veride farklı değil; çift başına koşularda (bağlaşım yok) tüm sinyaller tutarlı. Sonuç: gerçek lookahead bulgusu yok. (Not: bu durum aracın varsayımını — çiftlerin bağımsızlığı — bozduğu için çoklu-çift lookahead sonucu bu strateji için hep gürültü içerebilir; çift başına koşu doğru ölçüttür.)

## 3. Ana karar kolu (komisyon ×2 + 2 bp, funding açık)

| Metrik | 1h IS | 1h WF | 15m IS | 15m WF |
|---|---:|---:|---:|---:|
| Fiilî test başı (ısınma sonrası) | 2024-12-21 | 2025-11-01 | 2024-12-21 | 2025-11-01 |
| İşlem sayısı | 627 | 374 | 904 | 745 |
| Beklenti (R/işlem) | -0,091 | -0,055 | -0,259 | -0,400 |
| Beklenti %95 GA (R) | -0,24 … 0,06 | -0,22 … 0,11 | -0,35 … -0,17 | -0,49 … -0,31 |
| Medyan R | -1,012 | -1,015 | -1,021 | -1,028 |
| Profit factor (net) | 0,79 | 0,93 | 0,58 | 0,44 |
| Maks. düşüş (hesap, %) | 66,2 | 39,3 | 90,6 | 90,5 |
| Toplam getiri (bilgi; ölçüt değil) | -59,7% | -17,5% | -89,9% | -89,9% |
| Ort. süre | 14:30:00 | 13:32:00 | 3:38:00 | 3:37:00 |
| Brüt PnL (USDT) | 126 | 580 | -107 | -258 |
| Komisyon+kayma toplamı (USDT) | 715 | 748 | 791 | 640 |
|   – bunun kayma payı (yaklaşık) | 119 | 125 | 132 | 107 |
| Funding (ödenen +, alınan −; USDT) | 7,8 | 7,2 | 1,0 | 0,4 |
| Toplam maliyet (USDT) | 723 | 755 | 792 | 641 |
| Maliyet / brüt PnL | 5,75 | 1,30 | brüt ≤ 0 | brüt ≤ 0 |
| Maliyet / brüt KAZANAN işlemler | 0,29 | 0,30 | 0,54 | 0,73 |
| Maliyet / işlem (R) | 0,184 | 0,216 | 0,280 | 0,339 |
| Kazanma oranı (bilgi) | 0,27 | 0,30 | 0,27 | 0,23 |

Yorum: Stop-loss çıkışları işlemlerin %54–57'si ve ortalama ≈ −1,03 R; kârlı çıkışlar (iz süren stop, hedef) büyük R getiriyor (aşağıda §5). Komisyon, pozisyon büyüklüğü risk-temelli (stop mesafesi dar → notional büyük) olduğundan işlem başına tablodaki "Maliyet / işlem (R)" satırı kadar (R cinsinden) tutuyor; bu, brüt kenarın büyük bölümünü yiyor. 15m'de brüt PnL bile negatif. Hesap düşüşü ve toplam getiri, bileşik büyüklük ve 5% günlük zarar kilidi nedeniyle (işlem sayısı maliyetle azalıyor: günlük zarar bütçesi reddi) R-metriklerinden daha az güvenilir.

## 4. Tüm maliyet kolları (24 koşu)

Beklenti R cinsinden, işlem başına; T1/R1 sütunları `n / beklenti(R)`. R1 (menzil dönüşü) örneklemi küçük → **yalnız rapor, yorum yok**.

| Tetik | Dönem | Komisyon × | Kayma bp | n | E[R] | PF | Maks. DD % | Ort. süre | Komisyon+kayma | Funding | Brüt PnL | Maliyet/brüt | T1 n / E[R] | R1 n / E[R] | Koşu |
|---|---|---:|---:|---:|---:|---:|---:|---|---:|---:|---:|---:|---|---|---|
| 1h | IS | 1 | 0 | 630 | 0,018 | 0,96 | 37,2 | 14:40:00 | 423 | 13,2 | 292 | 1,49 | 558 / 0,047 | 72 / -0,208 | `1h_IS_f1_s0` |
| 1h | IS | 1 | 2 | 624 | -0,017 | 0,90 | 48,5 | 14:35:00 | 508 | 10,8 | 188 | 2,76 | 552 / 0,012 | 72 / -0,244 | `1h_IS_f1_s2` |
| 1h | IS | 1 | 5 | 629 | -0,070 | 0,81 | 63,6 | 14:26:00 | 620 | 9,0 | 88 | 7,19 | 553 / -0,036 | 76 / -0,325 | `1h_IS_f1_s5` |
| 1h | IS | 2 | 0 | 629 | -0,070 | 0,81 | 63,6 | 14:26:00 | 620 | 9,0 | 88 | 7,19 | 553 / -0,036 | 76 / -0,325 | `1h_IS_f2_s0` |
| 1h | IS | 2 | 2 | 627 | **-0,091** | 0,79 | 66,2 | 14:30:00 | 715 | 7,8 | 126 | 5,75 | 554 / -0,060 | 73 / -0,330 | `1h_IS_f2_s2` |
| 1h | IS | 2 | 5 | 615 | -0,159 | 0,72 | 74,7 | 14:23:00 | 764 | 6,7 | 44 | 17,65 | 540 / -0,125 | 75 / -0,403 | `1h_IS_f2_s5` |
| 1h | WF | 1 | 0 | 379 | 0,063 | 1,10 | 28,7 | 13:33:00 | 396 | 9,6 | 670 | 0,61 | 334 / 0,068 | 45 / 0,024 | `1h_WF_f1_s0` |
| 1h | WF | 1 | 2 | 378 | 0,019 | 1,03 | 34,1 | 13:36:00 | 501 | 8,2 | 578 | 0,88 | 335 / 0,029 | 43 / -0,055 | `1h_WF_f1_s2` |
| 1h | WF | 1 | 5 | 374 | -0,029 | 0,96 | 37,0 | 13:28:00 | 661 | 7,1 | 573 | 1,17 | 332 / -0,021 | 42 / -0,091 | `1h_WF_f1_s5` |
| 1h | WF | 2 | 0 | 374 | -0,029 | 0,96 | 37,0 | 13:28:00 | 661 | 7,1 | 573 | 1,17 | 332 / -0,021 | 42 / -0,091 | `1h_WF_f2_s0` |
| 1h | WF | 2 | 2 | 374 | **-0,055** | 0,93 | 39,3 | 13:32:00 | 748 | 7,2 | 580 | 1,30 | 334 / -0,052 | 40 / -0,085 | `1h_WF_f2_s2` |
| 1h | WF | 2 | 5 | 371 | -0,116 | 0,85 | 44,9 | 13:33:00 | 832 | 6,7 | 506 | 1,66 | 329 / -0,107 | 42 / -0,190 | `1h_WF_f2_s5` |
| 15m | IS | 1 | 0 | 2195 | -0,073 | 0,82 | 86,2 | 3:45:00 | 893 | 8,1 | 49 | 18,38 | 2052 / -0,082 | 143 / 0,054 | `15m_IS_f1_s0` |
| 15m | IS | 1 | 2 | 1808 | -0,133 | 0,74 | 90,6 | 3:44:00 | 850 | 4,3 | -44 | brüt≤0 | 1677 / -0,140 | 131 / -0,054 | `15m_IS_f1_s2` |
| 15m | IS | 1 | 5 | 951 | -0,225 | 0,60 | 90,6 | 3:37:00 | 733 | 1,3 | -165 | brüt≤0 | 882 / -0,250 | 69 / 0,096 | `15m_IS_f1_s5` |
| 15m | IS | 2 | 0 | 951 | -0,225 | 0,60 | 90,6 | 3:37:00 | 733 | 1,3 | -165 | brüt≤0 | 882 / -0,250 | 69 / 0,096 | `15m_IS_f2_s0` |
| 15m | IS | 2 | 2 | 904 | **-0,259** | 0,58 | 90,6 | 3:38:00 | 791 | 1,0 | -107 | brüt≤0 | 846 / -0,275 | 58 / -0,036 | `15m_IS_f2_s2` |
| 15m | IS | 2 | 5 | 705 | -0,337 | 0,51 | 90,6 | 3:38:00 | 788 | 0,8 | -110 | brüt≤0 | 664 / -0,338 | 41 / -0,316 | `15m_IS_f2_s5` |
| 15m | WF | 1 | 0 | 1222 | -0,191 | 0,62 | 87,9 | 3:36:00 | 481 | 2,7 | -379 | brüt≤0 | 1143 / -0,186 | 79 / -0,261 | `15m_WF_f1_s0` |
| 15m | WF | 1 | 2 | 1138 | -0,239 | 0,57 | 90,0 | 3:40:00 | 566 | 1,7 | -321 | brüt≤0 | 1062 / -0,235 | 76 / -0,299 | `15m_WF_f1_s2` |
| 15m | WF | 1 | 5 | 876 | -0,329 | 0,49 | 90,8 | 3:37:00 | 638 | 1,0 | -260 | brüt≤0 | 830 / -0,323 | 46 / -0,449 | `15m_WF_f1_s5` |
| 15m | WF | 2 | 0 | 876 | -0,329 | 0,49 | 90,8 | 3:37:00 | 638 | 1,0 | -260 | brüt≤0 | 830 / -0,323 | 46 / -0,449 | `15m_WF_f2_s0` |
| 15m | WF | 2 | 2 | 745 | **-0,400** | 0,44 | 90,5 | 3:37:00 | 640 | 0,4 | -258 | brüt≤0 | 710 / -0,394 | 35 / -0,526 | `15m_WF_f2_s2` |
| 15m | WF | 2 | 5 | 656 | -0,458 | 0,39 | 90,3 | 3:40:00 | 684 | 0,9 | -215 | brüt≤0 | 624 / -0,451 | 32 / -0,608 | `15m_WF_f2_s5` |

Gözlemler: (a) 1h'de maliyet arttıkça beklenti monoton düşer; başabaş yaklaşık %0,05–0,08/taraf toplam maliyet (komisyon+kayma) civarındadır — yani gerçekçi (taker + kayma) maliyette kenar yok. (b) 15m'de işlem sayısı maliyetle azalır çünkü hesap küçüldükçe/günlük zarar bütçesi dolunca yeni işlemler reddedilir; 15m'de hesap düşüşü %86–91'e doyar. (c) 15m'de iz süren stop çıkışları kârlı ama stop-out'lar baskın; brüt toplam negatif.

## 5. Kırılımlar (ana kol: ×2 + 2 bp)

Hücre: `n / E[R] / PF`. n < 30 olan hücreler yalnız bilgi içindir (özellikle R1 ve tek çift/yön hücreleri); bu kırılımlardan parametre veya çift seçimi yapılmadı.

### Setup (T1 = trend pullback, R1 = menzil dönüşü)

| Grup | 1h IS | 1h WF | 15m IS | 15m WF |
|---|---|---|---|---|
| R1 | 73 / -0,33 / 0,54 | 40 / -0,08 / 1,02 | 58 / -0,04 / 0,90 | 35 / -0,53 / 0,39 |
| T1 | 554 / -0,06 / 0,83 | 334 / -0,05 / 0,91 | 846 / -0,27 / 0,55 | 710 / -0,39 / 0,44 |

### Giriş anındaki rejim

| Grup | 1h IS | 1h WF | 15m IS | 15m WF |
|---|---|---|---|---|
| trend_up | 264 / -0,14 / 0,72 | 120 / -0,24 / 0,63 | 307 / -0,31 / 0,41 | 199 / -0,52 / 0,23 |
| trend_down | 290 / 0,01 / 0,94 | 212 / 0,06 / 1,08 | 539 / -0,26 / 0,61 | 511 / -0,34 / 0,49 |
| range | 72 / -0,33 / 0,54 | 39 / -0,08 / 1,04 | 58 / -0,04 / 0,90 | 35 / -0,53 / 0,39 |
| defterde karşılığı yok (aynı mumda yeniden giriş; §7.1) | 1 / – / 0,00 | 3 / – / 0,00 | – | – |

### Yön

| Grup | 1h IS | 1h WF | 15m IS | 15m WF |
|---|---|---|---|---|
| long | 299 / -0,17 / 0,68 | 143 / -0,19 / 0,74 | 335 / -0,30 / 0,45 | 217 / -0,52 / 0,21 |
| short | 328 / -0,02 / 0,90 | 231 / 0,03 / 1,04 | 569 / -0,24 / 0,63 | 528 / -0,35 / 0,50 |

### Çift

| Grup | 1h IS | 1h WF | 15m IS | 15m WF |
|---|---|---|---|---|
| ADA/USDT:USDT | 72 / 0,31 / 1,25 | 35 / -0,34 / 0,54 | 66 / -0,15 / 0,43 | 60 / -0,43 / 0,32 |
| AVAX/USDT:USDT | 52 / 0,23 / 1,27 | 21 / 0,17 / 1,33 | 85 / -0,39 / 0,51 | 49 / -0,28 / 0,74 |
| BNB/USDT:USDT | 75 / 0,04 / 0,98 | 53 / 0,07 / 0,99 | 98 / -0,23 / 0,79 | 80 / -0,45 / 0,60 |
| BTC/USDT:USDT | 76 / -0,33 / 0,43 | 43 / 0,06 / 1,07 | 118 / -0,43 / 0,20 | 99 / -0,30 / 0,71 |
| DOGE/USDT:USDT | 56 / -0,25 / 0,68 | 31 / 0,10 / 1,09 | 80 / -0,31 / 0,56 | 79 / -0,06 / 0,75 |
| ETH/USDT:USDT | 59 / -0,13 / 0,78 | 35 / 0,05 / 1,15 | 85 / -0,09 / 0,68 | 84 / -0,57 / 0,23 |
| LINK/USDT:USDT | 51 / -0,60 / 0,18 | 33 / -0,00 / 1,00 | 80 / -0,35 / 0,53 | 69 / -0,22 / 0,41 |
| SOL/USDT:USDT | 45 / 0,25 / 1,51 | 28 / -0,48 / 0,25 | 105 / -0,12 / 0,87 | 70 / -0,57 / 0,23 |
| TRX/USDT:USDT | 77 / -0,14 / 0,64 | 52 / -0,45 / 0,39 | 69 / -0,34 / 0,49 | 76 / -0,54 / 0,31 |
| XRP/USDT:USDT | 64 / -0,28 / 0,52 | 43 / 0,33 / 1,73 | 118 / -0,18 / 0,61 | 79 / -0,55 / 0,27 |

### Çıkış nedeni (freqtrade etiketi)

| Grup | 1h IS | 1h WF | 15m IS | 15m WF |
|---|---|---|---|---|
| force_exit | 2 / -0,02 / 0,60 | 2 / -0,08 / 0,15 | – | – |
| stop_loss | 342 / -1,03 / 0,00 | 205 / -1,03 / 0,00 | 492 / -1,04 / 0,00 | 427 / -1,05 / 0,00 |
| target | 12 / 2,83 / ∞ | 8 / 2,96 / ∞ | 5 / 3,11 / ∞ | 1 / 4,93 / ∞ |
| time_stop | 3 / 0,34 / 3,99 | 4 / 0,26 / 2,16 | 10 / 2,79 / ∞ | 7 / 0,73 / 342,21 |
| trail_stop | 4 / 6,32 / ∞ | 1 / 5,35 / ∞ | 4 / -0,14 / 0,06 | 6 / 2,54 / ∞ |
| trailing_stop_loss | 264 / 0,88 / 6,15 | 153 / 1,04 / 8,44 | 393 / 0,60 / 3,94 | 304 / 0,42 / 2,85 |
| regime_flip | – | 1 / -0,50 / 0,00 | – | – |

Notlar: (1) **Long taraf 1h'de iki dönemde de negatif** (IS −0,17 R n=299; WF −0,19 R n=143), **short ≈ 0** (−0,02 / +0,03). Rejim kırılımı aynı resmi verir: `trend_up` her iki dönemde negatif (−0,14 / −0,24), `trend_down` ≈ 0/+0,06. Bu, örneklem dönemindeki piyasa sürüşünden (düşüş eğilimi) kaynaklanıyor olabilir; bu raporda bir karar/parametre değişikliğine **dönüştürülmedi**, yalnız gözlem olarak kayda geçti. (2) **Çift sıralaması dönemler arasında kararsız** (ör. ADA IS +0,31 → WF −0,34; SOL +0,25 → −0,48; XRP −0,28 → +0,33): çift seçimi için dayanak yok. (3) "range / R1" IS'te −0,33 R (n=73), WF'de −0,09 R (n=40) — küçük örneklem, yalnız rapor.

## 6. Parametre taraması (yalnız IS, 1h, ana kol ×2 + 2 bp)

**Seçim gerekçesi:** ders-ayarlanabilir 5 parametreden (vol_ratio_max, stop_buffer_atr, trail_atr, range_target_frac, rr_min) ikisi seçildi: **`stop_buffer_atr`** — her iki kurulumda stop mesafesini belirler; stop mesafesi hem pozisyon büyüklüğünü (dar stop → büyük notional → komisyon/R yüksek) hem stop-out sıklığını (işlemlerin ≈%55'i −1R stop) belirler; **`trail_atr`** — işlemlerin ≈%88'ini oluşturan T1'in kârlı çıkışını (iz süren stop) kontrol eder ve brüt kenarın taşıyıcısıdır. `range_target_frac` ve `rr_min` yalnız R1'i etkiler (n≈73, anlamlı sonuç çıkmaz); `vol_ratio_max` bir filtre (işlem sayısını değiştirir, kenar değil). Değerler ders adımı (step) ve sınırları içinde, bir seferde bir parametre (ızgara değil): stop_buffer {0,2; **0,3**; 0,4}, trail {2,5; **3,0**; 3,5}. Toplam 4 ek koşu (varsayılan koşu yeniden kullanıldı).

| Parametre | Değer | n | E[R] | %95 GA | PF | Maks. DD % | Brüt PnL | Komisyon+kayma | T1 E[R] | R1 E[R] (n) |
|---|---|---:|---:|---|---:|---:|---:|---:|---:|---|
| stop_buffer_atr | 0,2 | 657 | -0,065 | -0,21 … 0,08 | 0,84 | 58,1 | 336 | 844 | -0,038 | -0,268 (76) |
| stop_buffer_atr | 0,3 (varsayılan) | 627 | -0,091 | -0,24 … 0,06 | 0,79 | 66,2 | 126 | 715 | -0,060 | -0,330 (73) |
| stop_buffer_atr | 0,4 | 575 | -0,020 | -0,18 … 0,14 | 0,91 | 51,8 | 546 | 828 | 0,013 | -0,242 (73) |
| trail_atr | 2,5 | 655 | -0,107 | -0,24 … 0,03 | 0,77 | 70,9 | 98 | 708 | -0,093 | -0,217 (75) |
| trail_atr | 3,0 (varsayılan) | 627 | -0,091 | -0,24 … 0,06 | 0,79 | 66,2 | 126 | 715 | -0,060 | -0,330 (73) |
| trail_atr | 3,5 | 581 | -0,027 | -0,21 … 0,16 | 0,89 | 57,5 | 414 | 773 | 0,017 | -0,319 (76) |

**Sonuç: varsayılanlar korunuyor.** (i) Tek işlem R'sinin standart sapması ≈ 1,90, n≈600 → beklentinin standart hatası ≈ 0,075 R; tüm komşu farkları (≤ 0,07 R) ≈ 1 SE içinde, yani gürültü. (ii) `stop_buffer_atr` eğrisi monoton değil (0,2: −0,065; 0,3: −0,091; 0,4: −0,020) → komşular kararsız. (iii) `trail_atr` eğrisi monoton (2,5 < 3,0 < 3,5) ama iyileşme (+0,064 R) anlamsız ve işlem sayısı düşerken (655 → 581) oluyor; 3,5 bile pozitif beklenti vermiyor (−0,027). (iv) Hiçbir kombinasyonda beklenti pozitif değil; yönlendirme olarak "daha geniş stop / daha geniş iz" hipotezi (stop_buffer 0,4, trail 3,5) ileride **bağımsız veriyle** sınanabilir; bu rapor onu WF'de denemedi (WF'yi seçimle kirletmemek için). Bu hipotezler tek gözlemden gelir; seçilmiş değil, not edilmiştir.

## 7. Tutarlılık kontrolleri

### 7.1 Defter ↔ freqtrade işlem listesi

Her koşuda yeni geçici defter dosyası (`ledger.sqlite`) açıldı; `v_trades` ile freqtrade işlem listesi `(çift, giriş zamanı)` anahtarıyla eşlendi.

| Koşu | freqtrade işlem | defter işlem | defterde karşılığı olmayan ft işlemi | Eşleşenlerde brüt PnL maks. fark | komisyon maks. fark | PnL maks. mutlak fark | PnL toplam fark (defter−ft) | Defter E[R] | Fiilî-risk E[R] |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| `1h_IS_f2_s2` | 627 | 626 | 1 | ≤5e-9 | 0 | 0,078 USDT | 1,003 USDT | -0,092 | -0,091 |
| `1h_WF_f2_s2` | 374 | 371 | 3 | ≤5e-9 | 0 | 0,146 USDT | 13,889 USDT | -0,056 | -0,055 |
| `15m_IS_f2_s2` | 904 | 904 | 0 | ≤5e-9 | 0 | 0,106 USDT | -0,112 USDT | -0,258 | -0,259 |
| `15m_WF_f2_s2` | 745 | 745 | 0 | ≤5e-9 | 0 | 0,114 USDT | 0,237 USDT | -0,397 | -0,400 |

Tüm 30 koşu için: eşleşen işlemlerde brüt PnL ve komisyon birebir (≤ 5e-9); PnL farkı yalnız **funding** satırından: defter `funding_paid`'i çıkış emri dolduğu anda `trade.funding_fees`'ten okur, freqtrade'in kapanışta nihai hesapladığı funding ile farklı olabilir (en büyük işlem farkı 0.20 USDT; ≥ 0,10 USDT olan işlem sayısı koşu başına 0–3). **Toplam PnL farkı** (tablo) 1h koşularında esas olarak defterde hiç olmayan işlemlerden gelir (WF: üç işlemin toplamı ≈ −13,4 USDT). **Sayı farkı:** 15m koşularında defter = freqtrade (tam eşleşme). 1h koşularında defterde olmayan işlemler (IS 1, WF 3, diğer 1h kollarında benzer) **aynı sinyal mumu içinde stop sonrası yeniden girişlerdir** (`--timeframe-detail 15m` ile işlem mumun 15 dakikalık alt-mumlarında yeniden tetiklenebiliyor); defter bir karara tek `trade_id` bağlar → günlükte `giris kaydi yazilamadi: karar baska bir trade_id'ye bagli` (CRITICAL) ve çıkış kaydı da yazılamıyor. Bu yeniden girişler 1h koşusunda 7 adettir ve toplam ≈ −4…−5 R yapar (backtest'e yansıyor, deftere yansımıyor). Canlıda aynı mum içinde yeniden giriş mantığı (freqtrade sinyali aynı mumda yeniden görür) ve defterin bunu işleyememesi **ayrı bir tasarım sorunu**; bu rapor strateji kodunu değiştirmez, yalnız bildirir.

### 7.2 Risk kilidi (işlem başına en çok %2 özsermaye) kontrolü

Yöntem: giriş anında özsermaye tahmini = başlangıç bakiyesi + o ana kadar kapanan işlemlerin PnL'si + açık işlemlerin son 1h kapanışla gerçekleşmemiş PnL'si (strateji de `wallet + unrealized` kullanır; bu bir **tahmin**dir, komisyon/funding açık pozisyonlar için dahil değil). İhlal = `gerçekleşen zarar (komisyon+funding dahil) > %2 × özsermaye`.

| Koşu grubu | koşu | işlem | İhlal (>%2) | En yüksek zarar/özsermaye | R < −1 olan işlem | R < −1,1 olan işlem | En kötü R |
|---|---:|---:|---:|---:|---:|---:|---:|
| 15m IS | 6 | 7514 | 0 | 1.52% | 979 | 206 | -1,318 |
| 15m WF | 6 | 5513 | 0 | 1.55% | 897 | 283 | -1,346 |
| 1h IS | 6 | 3754 | 0 | 1.51% | 877 | 72 | -1,257 |
| tekrar koşuları | 2 | 1001 | 0 | 1.47% | 543 | 3 | -1,121 |
| 1h IS sweep | 4 | 2468 | 0 | 1.46% | 1341 | 3 | -1,121 |
| 1h WF | 6 | 2250 | 0 | 1.53% | 472 | 67 | -1,252 |

**İhlal listesi: boş** (hiçbir koşuda, hiçbir işlemde gerçekleşen zarar giriş özsermayesinin %2'sini aşmadı; en yüksek ≈ %1,5 — hedef %1,4, kilit %2). Bilgi amaçlı: zarar planlanan riski (R = −1) birkaç yüzde (uç durumda %35'e kadar, 15m) aşabiliyor çünkü (i) ana kolda gerçek maliyet (%0,12/taraf) risk modülünün varsayımından (%0,10/taraf) yüksek, (ii) stop dolumu mum açılışındaki boşluklarda stop fiyatının ötesinde olabilir, (iii) funding. R < −1,1 olan işlemler az (ana kolda 1h: IS 2/627, WF 1/374; 15m: IS 12/904, WF 30/745); en kötü tek işlem R = −1,35 (15m; boşluk/stop-market dolumu). Bu, kilidin işlevini bozmaz çünkü sınır %2 iken hedef %1,4'tür (≈ %43 pay); ancak **15m ×2 + 5 bp kolunda en kötü zarar ≈ %1,55'e** çıkıyor — daha yüksek maliyet/boşlukta payın azaldığını gösterir.

### 7.3 Determinizm / yeniden üretilebilirlik

| Koşu | işlem | E[R] | PF | Maks. DD % | Orijinal ile işlem listesi |
|---|---:|---:|---:|---:|---|
| `1h_IS_f2_s2_rerun` | 627 | -0,091 | 0,79 | 66,2 | birebir aynı |
| `1h_WF_f2_s2_rerun` | 374 | -0,055 | 0,93 | 39,3 | birebir aynı |

Ek: ×1+5 bp ve ×2+0 bp koşuları (aynı `fee_eff`) birebir aynı sonucu verdi. Çalışma sırasında depodaki `ledger.py` başka bir oturumca değiştirildi (şema v2, commit 78d4b04; ana koşular v1 ile, sweep/tekrar koşuları sonrasıyla yapıldı) → tekrar koşuları işlem listesinin değişmediğini gösterir.

## 8. Teknik bulgular ve uyarılar (caveat)

1. **Piyasa meta verisi yaklaşıktır.** `scripts/freqtrade_offline.py` market listesini yerelden sentetik üretir: min. notional **5 USDT**, miktar/fiyat adımı son mumlardan türetilmiş, kaldıraç kademeleri paket içi tablodan. Gerçek borsa filtreleri (min. notional ≈ 5–100 USDT, lot adımı, fiyat adımı) farklıdır; sonuçlar bire bir değildir. Özellikle büyük adımlı çiftlerde (BTC) küçük pozisyonların reddi/yuvarlaması gerçekte farklı olur. Defterin `planned_risk`'i işlemlerin ≈%2'sinde (çoğunlukla BTC/DOGE/XRP) fiilî miktarın riskinden %2–20 yüksek çıktı; olası neden türetilmiş adıma göre miktar yuvarlama (nedeni ayrıca araştırılmadı).
2. **15m kolunda 5m detay verisi yok.** Veri seti 15m/1h/4h/1d içeriyor; 15m koşularında `--timeframe-detail` kullanılamadı → mum içinde stop ile hedef/iz stop aynı mumda ise sıra varsayımı (freqtrade'in standart kötümser kuralı) belirleyici. 1h kolu 15m detay ile koştu (daha doğru).
3. **Kayma modellenmedi, komisyona eklendi.** Gerçek kayma işlem büyüklüğü, volatilite ve stop dolumuna bağlıdır (stop-market çıkışlarda boşluk kaymaları 2–5 bp'den büyük olabilir). Komisyon ×2 taker için ihtiyatlı bir üst varsayımdır; gerçekte maker/BNB indirimi farklıdır. Bu yüzden maliyet kolları bir **duyarlılık aralığı** olarak okunmalı.
4. **Funding boşlukları.** Funding verisi 2026-10-31 16:00'a kadar (ay sonu yayımı; Kasım 2026 eksik). IS ve WF aralıklarında 8 saatlik funding kesintisiz (2190 satır/çift, boşluk yok); dolayısıyla bu raporun sonuçları bundan etkilenmez, ancak HOLDOUT'un son ayı (Ekim 2026'nın sonu) ve Kasım için funding eksik olacaktır. Funding etkisi küçük: 1h'de toplam ≈ 7–13 USDT (komisyon ≈ 400–800 USDT).
5. **IS fiilen 2024-12-21'de başlıyor** (veri 2024-11-01'de başlıyor; strateji 1200 mum (1h) / 4800 mum (15m) ısınma ve 4h rejim verisi ister) → IS ≈ 10,3 ay; kullanıcıya "12 ay" olarak sunulmamalı.
6. **15m tetik canlıda başlayamaz:** `startup_candle_count = 300·4/0,25 = 4800`; freqtrade `validate_required_startup_candles` Binance 15m için en fazla 5 çağrı × 499 = 2494 mumu kabul eder (`ConfigurationError: This strategy requires 4800 candles to start, which is more than 5x (2494 candles)`). Backtest'te yalnız `research/ft_offline_15m.py` ile (kontrolü atlayarak) koşabildi. 1h için 1200 mum (3 çağrı) uyarı verir ama geçer.
7. **`lookahead/recursive` araçları ve çalışma modu:** bu araçlar `UTIL_NO_EXCHANGE` ile koşar; TraderV1 bunu canlı sayıp girişleri kapatır. Araç uyumluluğu için `_BACKTEST_MODES` eşlemesi gerekir (alt sınıf yöntemi kullanıldı; strateji dosyası değişmedi). Çoklu çift lookahead testi portföy bağlaşımı nedeniyle yanlış pozitif verir (§2).
8. **Aynı mumda yeniden giriş (1h + detay):** stop sonrası aynı sinyal mumunda 15 dakikalık alt-mumlarda yeniden giriş mümkün (IS'te 7, WF'de 7 mum-ortası giriş; çoğu −1 R civarı zarar; defter 1–3'ünü yazamıyor). Canlıda freqtrade sinyali aynı mumda yeniden gördüğü için benzer davranış beklenir. Soğuma süresi/koruma yok.
9. **Hesap metrikleri bileşik ve doygun.** %5 günlük zarar kilidi, %6 açık risk ve min. notional nedeniyle kötü kollarda işlem sayısı maliyetle azalır ve hesap düşüşü %90 civarında doyar (15m); toplam getiri/DD bu yüzden ölçüt olarak kullanılmadı, R-bazlı beklenti ve PF kullanıldı. Maks. DD freqtrade'in kapanmış-işlem bakiyesi üzerinden hesabıdır.
10. **Çift evreni** bugünün büyük USDT-M perpetual'leri (hayatta kalanlar); evren seçimi geçmişe bakarak yapıldığı için ileriye dönük bir hayatta kalma yanlılığı olabilir (10 çiftin tamamı veri döneminde mevcuttu).
11. **Pipeline testi sırasında** WF'nin son ayı (20260401–20260501) iki kez yalnız altyapıyı doğrulamak için koşuldu (karar/parametre seçiminde kullanılmadı; kayıt defterinde `tani_*` olarak işaretli). HOLDOUT'a hiç dokunulmadı.
12. **Çalışma süresi:** 1h IS (detaylı) ≈ 9 dk, 15m IS ≈ 7 dk; strateji geri çağrıları her mumda tüm kapanmış işlemleri tarar (O(n²)), bu yüzden yıl boyu koşular dakikalar sürer.
13. **Depo eşzamanlı değişti:** çalışma boyunca başka oturumlar (veto, bütçe, ders servisi, defter şema v2) commit attı; strateji/risk/rejim/sinyal dosyaları değişmedi (yalnız `ledger.py` v2). Kayıt defterindeki `git_commit` sütunu = strateji koduna dokunan son commit (+ HEAD).

## 9. Sonuç ve öneri

* **Teknik doğrulama:** lookahead/recursive temiz; risk kilidi ihlali yok; defter ↔ freqtrade tutarlı (aynı-mum yeniden giriş istisnası hariç).
* **Strateji değerlendirmesi:** Gerçekçi maliyette (×2 + 2 bp) 1h tetikte beklenti hem IS hem WF'de hafif negatif (GA sıfırı içeriyor), PF 0,79/0,93; 15m tetikte net negatif ve elenmeli. Brüt kenar küçük ve maliyet duyarlı; en ucuz maliyet kolunda bile kanıtlanmış bir kenar yok.
* **HOLDOUT:** açılmadı. Mevcut kanıt, holdout'un "tek seferlik" hakkını bu yapılandırmayla harcamayı desteklemiyor (ana kolda pozitif beklenti yok); karar kullanıcıda. Açılacaksa önce açık onay ve donmuş parametre/maliyet kolu gerekir.
* **Olası sonraki adımlar (kod değişikliği gerektirir, bu işin kapsamı dışında):** aynı mum içinde yeniden girişe soğuma süresi; komisyon/işlem-başına-R'yi düşürecek (daha geniş stop / daha az işlem) hipotezlerinin bağımsız veriyle testi; 15m için startup gereksiniminin düşürülmesi (aksi halde canlı başlamaz); gerçek `exchangeInfo` ile market meta verisinin doğrulanması; ledger'a aynı mumda ikinci giriş için karar-başına-çoklu işlem desteği; `lookahead-analysis` için portföy-bağımsız doğrulama modu.

## 10. Dosyalar ve yeniden üretim

* Deneme kaydı: `trader/research/trial_registry.csv` (her koşu + lookahead/recursive + tanı koşuları).
* Koşu özetleri (kırılımlar dahil): `trader/research/runs/*.json`; ham sonuçlar `trader/user_data/backtest_results/<id>/` (git'te yok).
* Günlükler: `trader/research/logs/` (lookahead/recursive çıktıları, kuyruk günlüğü).
* Yeniden üretim: `PYTHONPATH=src .venv-ft/bin/python research/run_bt.py --id 1h_IS_f2_s2 --period IS --fee-mult 2 --slip-bps 2 --tf 1h` ; kuyruk: `research/queue.sh research/jobs_arms.txt`; kayıt: `research/build_registry.py`; rapor: `research/make_report.py`.
* Lookahead: `lookahead-analysis --config config/base.json --config config/backtest.json --userdir user_data --datadir user_data/data/binance --strategy TraderV1Analysis --strategy-path research/strategies --timerange 20250501-20250801 -p <çift>`.
