# 06 — Çapraz doğrulama sonucu (motor `legacy_compat` ↔ dondurulmuş freqtrade çıktıları)

Tarih: 16 Kasım 2026. Strateji: `price_action_v1_full` (TraderV1 eşdeğeri; v1b yapılandırması). Motor: `backtest --fill-model legacy_compat --granularity 15m --synthetic-rules --no-record-filtered` (uyum çalışması, yerel sonuç değildir). Referans: `user_data/backtest_results/<ID>/` ve `research/runs/<ID>.json` (freqtrade çalıştırılmadı). HOLDOUT (2026-05 → 2026-10) çalıştırılmadı. Ayrıntı: `research/crosscheck/<ID>.{md,json}`.

## Karar: KALDI (kapı geçilmedi) — açıklanamayan fark = 0

**Revizyon (tarihsel aylık tick):** İlk koşuda (aşağıda "önceki" sütunları) tüm `price_rounding` farkları SOL'daydı; neden yuvarlama yönü değil **tick büyüklüğüydü**: freqtrade backtest'i borsa hassasiyetini yok sayıp tarihsel tick türetir (`get_tick_size_over_time`: çift × UTC ayı × ana-tf mumlarının OHLC'sindeki en büyük ondalık hane sayısı); SOL'da ara sıra 3 haneli mumlar olduğundan referans 0,001, sentetik kural 0,01 kullanıyordu. `legacy_compat`'ta uygulandı (giriş ayı tick'i işlem ömrü boyunca; dolumlar en yakına, stoplar `round_tight` ile aynı tick'e; ayda veri yoksa sentetik tick'e dönüş; ayrıntı 03 §4.5 ii). Türetme, freqtrade'in kendi `get_tick_size_over_time` fonksiyonuyla 8 çift × 25 ay × {1h, 15m} üzerinde birebir karşılaştırıldı: 0 fark. Native kip değişmedi.

| Çalışma | A kararlar | B girişler (önceki → şimdi) | C çıkışlar (önceki → şimdi) | D ΣR (ref / motor; önceki motor) | D komisyon (ref / motor) | D funding | D işlem sayısı (ref / motor) | `price_rounding` (önceki → şimdi) |
|---|---|---|---|---|---|---|---|---|
| 1h_IS_f1_s0 | %100 geçti | %28 → %33,7 kaldı | %92,0 → %96,1 kaldı | 10,88 / -2,53 (6,57) kaldı | 422,6 / 401,7 kaldı | geçti | 630 / 622 kaldı | 28 → 3 |
| 1h_WF_f1_s0 | %100 geçti | %20 → %19,7 kaldı | %95,3 → %95,9 kaldı | 23,66 / 28,80 (28,80) kaldı | 393,2 / 362,0 kaldı | geçti | 376 / 349 kaldı | → 2 |
| 15m_IS_f1_s0 | %100 geçti | %5 → %6,4 kaldı | %80,4 → %85,6 kaldı | -160,6 / -158,4 (-145,0) geçti | 893,0 / 981,5 kaldı | geçti | 2195 / 2223 kaldı | → 79 |
| 1h_IS_f2_s5 | %100 geçti | %28 → %27,9 kaldı | %91,9 → %95,9 kaldı | -96,9 / -79,4 (-79,4) kaldı | 762,6 / 783,0 kaldı | kaldı | 614 / 614 geçti | 28 → 3 |

Eşikler (spec §7.2): A %100; B ≥ %99; C ≥ %97; ΣR ≤ %2; komisyon ≤ %2; funding ≤ %5; işlem sayısı ±max(1,%1). Geçme ölçütü `price_rounding = 0` **sağlanmadı** (SOL kaynaklı 28 satır gitti; kalanlar aşağıda).

Metrikler yan yana (referans `research/runs`, motor `summary.json`):

| Çalışma | n_trades ref/motor | expectancy_R ref/motor | PF ref/motor | profit_abs ref/motor | max_dd % ref/motor |
|---|---|---|---|---|---|
| 1h_IS_f1_s0 | 630 / 620 | 0,018 / -0,004 | 0,960 / 0,923 | -143,5 / -262,9 | 37,2 / 38,9 |
| 1h_WF_f1_s0 | 379 / 347 | 0,063 / 0,083 | 1,098 / 1,136 | 264,1 / 339,6 | 28,7 / 32,1 |
| 15m_IS_f1_s0 | 2195 / 2223 | -0,073 / -0,071 | 0,818 / 0,834 | -852,0 / -831,3 | 86,2 / 84,3 |
| 1h_IS_f2_s5 | 615 / 612 | -0,159 / -0,130 | 0,718 / 0,746 | -726,6 / -666,8 | 74,7 / 71,8 |

## Kalan fark sınıfları (hepsi sınıflandırıldı, açıklanamayan 0)

1. **`price_rounding` kalanı (1h: 2-3, 15m: 79):** tick türetmesi doğru (freqtrade fonksiyonuyla birebir); bunlar tick'in katı olan iki farklı iz-stop değeridir (örn. BTC 96828,0 ↔ 96823,6; ETH 2695,41 ↔ 2695,39; LINK 24,173 ↔ 24,174; 15m'de çoğu 1 tick). Sınıflayıcı "aynı çıkış anı + göreli < 1e-4" kuralıyla etiketler; neden yuvarlama değil, iz-stop **ham** değerindeki küçük sapmadır (ATR/en uç fiyat zamanlaması). Tick kuralıyla kapanmaz; ayrı inceleme gerekir.
2. **İlk sapma artık `exit_before_entry`** (1h_IS/f2_s5: XRP short 2024-12-22 12:00, boyut 289,8 ↔ 290,1): referans aynı adımda çıkan SOL işleminin gerçekleşmiş kârını boyutlandırmadan önce özsermayeye yazar, motor yazmaz. Zincirleme (`chained_after_first` 665-5193 satır) buradan sürer; B'nin düşük oranı bunun sonucudur (anahtar eşleşmesi %88-97).
3. `qty_rounding` (freqtrade stake→amount kesmesi: 1h 3-14 satır, 15m 8; **uygulanmadı**), `gap_fill`, `funding_boundary`, `margin_accounting`, `open_at_end`: beklenen, ayrı etiketli.
4. Düzey A: ortak anahtarlı tüm kararlarda %100 eşitlik; sinyal/strateji katmanı birebir.

## Yerel kip / model farkı (1h_IS, spec §7.4)

| Çalışma | n_trades | expectancy_R | ΣR | PF |
|---|---|---|---|---|
| (1) compat (15m, last, kayma komisyonda) | 620 | 0,011 | 6,57 | 0,952 |
| (2) native_last (1m, last, 2/2/5 bps) | 610 | -0,047 | -28,39 | 0,863 |
| (3) native_mark (1m, mark) | 602 | 0,011 | 7,39 | 0,956 |

(2)→(3) mark↔last: last stop 336, mark stop 325; mark'ın kaldırdığı stop 6, eklediği 0; ΔΣR = +35,8 (eşleşen 589 işlemde ort. ΔR +0,040). Bu fark yerel/1m çalışmada ayrıntı+maliyet etkisi (1→2: ΔΣR ≈ -35) ile mark etkisinin (2→3: ≈ +36) büyüklükçe aynı olduğunu gösterir: last tetikte fitil stopları ΣR'yi belirgin düşürüyor (risk tablosu 2 için ölçüm).

## Sonuç ve sonraki adım

- A düzeyi geçti, açıklanamayan 0; B/C/D toleransları hâlâ geçmedi → §4.3 kapısı **açılmaz**. Tick düzeltmesi C'yi %80-95 → %86-96'ya taşıdı, `price_rounding`'in SOL/tick kaynaklı kısmını kapattı.
- Sıradaki kök neden: **aynı adımda çıkış → özsermaye gerçekleşmesi → giriş boyutlandırma sırası** (`exit_before_entry`); sonra `qty_rounding` (stake→amount kesmesi) ve iz-stop ham değer sapması.
- Model farkı raporu yalnız 1h_IS için üretildi (yukarıdaki tablo tick düzeltmesinden önceki koşulara aittir; yenilenmedi).
