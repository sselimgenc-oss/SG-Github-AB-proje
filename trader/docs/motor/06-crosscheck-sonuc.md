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

## Yerel kip / model farkı (1h_IS, spec §7.4) — tarihsel tablo (tick öncesi); güncel tablo en altta

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

## Mentor kararı (17 Kasım 2026) — sınırlı ek uyum çalışması
Kapı kapalı kalır; freqtrade silme en sonda (e2e + mentor onayı). "Açıklanamayan = 0" yetmez: `chained_after_first` 665–5193 satır ve B %6–34; zincir kovası gerçek motor hatalarını saklayabilir; §7.2 A–D'nin geçmesini ister.
Sıra (motor A düzeltmeleri birleşip yeşil olduktan sonra; yalnız compat, native defter bayt bayt aynı kalır):
1. `exit_before_entry`: compat'ta aynı adımdaki çıkış K/Z'si giriş boyutlandırmadan önce özsermayeye yansır. 4 koşu yeniden. Kağıt/native'in bu durumda ne yaptığı ayrıca raporlanır; native mentora sorulmadan değişmez.
2. `qty_rounding`: freqtrade stake→miktar kesmesi uygulanır (önceki "uygulama" kararı geri alındı). Yeniden koşu.
3. İz süren stop ham değeri: kural değil, inceleme. 5 satır (önce BTC 96828.0 / 96823.6) iki tarafın ATR/uç girdileriyle adım adım. Motor yanlışsa gerçek hata (native'i de etkiler) — düzeltmeden önce rapor.
4. B hâlâ <%99 ise: zincirsiz tanı (boyut referans `equity_entry_est`'ten) ile kalan satırların saf zincir olduğu kanıtlanır.
4. adımdan sonra dur ve raporla; HOLDOUT yok. §7.4 model-fark tablosu yeniden üretilir (tick öncesinden kalma). f2_s5 funding hatası A düzeltmesindeki funding değişikliğinden sonra yeniden kontrol edilir.


## Mentor kararı adımlarının sonucu (17 Kasım 2026)

Kapsam: yalnız `legacy_compat` yolları (`backtest.py`: `_CompatBrokerView`, `_CoarsePaperBroker._fill_entry`); native/paper değişmedi (kanıt: `tests/engine/test_engine_compat_equity.py::test_native_ledger_hash_unchanged_by_compat_work`, 1m native backtest defterinin SHA-256'sı HEAD koduyla ve değişiklikten sonra aynı: `c12b069c…ce24e2`). HOLDOUT çalıştırılmadı. Koşular: motor A düzeltmeleri (funding imleci/8s ızgara, backtest `target_trade_risk` = 0,014) sonrası. Ham çıktılar: `research/crosscheck/<ID>.{md,json}` (adım 2 sonrası), `<ID>_chainfree.json` (adım 4).

### Yeni taban (düzeltme öncesi yeniden koşu, "r0")

| Çalışma | B (anahtar) | C | ΣR ref/motor | komisyon ref/motor | funding ref/motor | işlem ref/motor | `price_rounding` | `exit_before_entry` | `qty_rounding` |
|---|---|---|---|---|---|---|---|---|---|
| 1h_IS_f1_s0 | %8,7 (90,3) | %96,3 | 10,88 / 11,23 | 422,6 / 417,2 geçti | 13,20 / 14,85 kaldı | 630 / 596 | 2 | 9 | 9 |
| 1h_WF_f1_s0 | %6,4 (86,4) | %95,7 | 23,66 / 28,62 | 393,2 / 348,3 | 9,04 / 8,59 geçti | 376 / 340 | 2 | 3 | 2 |
| 15m_IS_f1_s0 | %1,3 (85,6) | %85,4 | -160,6 / -140,7 | 893,0 / 1050,4 | 8,53 / 9,57 | 2195 / 2143 | 80 | 85 | 4 |
| 1h_IS_f2_s5 | %14,3 (87,6) | %96,3 | -96,9 / -71,7 | 762,6 / 769,3 geçti | 6,81 / 8,39 kaldı | 614 / 575 | 2 | 10 | 5 |

A düzeltmeleri sonrası işlem sayısı motorda azaldı (ör. 1h_IS_f1_s0 622 → 596): hedef risk 0,014 ile boyutlar büyüdü, `insufficient_margin` ve zincir arttı.

**f2_s5 funding yeniden kontrolü:** hâlâ **kaldı** (ref 6,81 / motor 8,39–8,44; %23). Neden: (i) 77 satırda `funding_boundary`: freqtrade tam 00/08/16'da açılan işlemde giriş noktasını da öder, motor (`opened_ts >= p.ts` atlar, 03 §5) ödemez; eşleşen işlemlerde net etkisi yalnız +0,04 USDT; (ii) toplam farkın geri kalanı işlem kümesi farkından (614 / 575) gelir, funding kuralından değil. Funding imleci/8s ızgara düzeltmesi bu satırları değiştirmedi.

### Adım 1 — `exit_before_entry`

Compat'ta giriş kapısının özsermayesi, o adımda çıkacak (`closing` ya da stopu adım barında değecek) pozisyonların gerçekleşmiş K/Z'sini (çıkış komisyonu dahil, mark'taki gerçekleşmemiş K/Z yerine) içerir. İlk sapma (1h_IS XRP short 2024-12-22 12:00): motor boyutu 290,1 → **289,9**, ref 289,8; kalan 0,03 %, `TraderV1`'in özsermaye tanımı farkıdır (`wallet + calc_profit(1h kapanış)`, komisyonlu; motor: cüzdan + 15 dk açılış mark'ı; `equity_coupling`). Sınıflayıcı bu satırı hâlâ `exit_before_entry` etiketler (boyut tam eşit değil).

| Çalışma | B (anahtar) | C | ΣR ref/motor | komisyon | funding | işlem | `exit_before_entry` |
|---|---|---|---|---|---|---|---|
| 1h_IS_f1_s0 | %8,7 (90,3) | %96,3 | 10,88 / 11,23 | 422,6 / 417,3 | 13,20 / 14,85 | 630 / 596 | 9 |
| 1h_WF_f1_s0 | %12,8 (87,0) | %95,7 | 23,66 / 28,34 | 393,2 / 350,3 | 9,04 / 8,35 | 376 / 343 | 4 |
| 15m_IS_f1_s0 | %1,7 (85,7) | %85,5 | -160,6 / -151,6 | 893,0 / 1038,4 | 8,53 / 9,53 | 2195 / 2146 | 90 |
| 1h_IS_f2_s5 | %7,5 (87,3) | %96,3 | -96,9 / -72,6 | 762,6 / 775,3 | 6,81 / 8,42 | 614 / 573 | 10 |

Hiçbir ölçüt geçişi değişmedi. `exit_before_entry` sayısı azalmadı (sınıflayıcı eşiği), ama ilk sapma büyüklüğü 0,10 % → 0,03 %.

**Native/paper bu durumda ne yapar (değiştirilmedi):** karar adımı D'de `_exits` çıkış emrini verir (pozisyon `closing`), dolum bir sonraki dakikanın açılışında olur; aynı adımdaki `_entries` boyutu `broker.account().equity` = `cüzdan + son mark gerçekleşmemiş K/Z`'den hesaplar ve `closing` pozisyon hâlâ açık pozisyon/pozisyon sayısı/risk toplamına dahildir. Yani aynı adımdaki çıkış giriş boyutunu etkilemez; yalnız D'den önceki dakikalarda dolmuş stop/hedef çıkışları cüzdandadır. Fark küçüktür (çıkış fiyatı ≈ mark; fark çıkış kaymasıdır) ama pozisyon sayısı/risk üst sınırı ve cüzdan kullanılabilirliği için serbest bırakma yoktur: çıkış dolana kadar yer tutar. **Mentora soru:** native'de de "çıkış kararı verilen pozisyonun yerini aynı adımda serbest bırak" istenir mi? (Şimdilik hayır; compat'a özgü kural.)

### Adım 2 — `qty_rounding`

Kural: `margin = qty·ref/lev`; dolumda `qty = trunc((margin/fill)·lev, adım)`, kesme `Decimal(repr)` üzerinden. Örnek: BNB 2025-11-01 02:00 karar 0,92 (marj 332,81) → 998,4392/1085,26 = 0,9199999999999999 → ref dolum **0,91**. Doğrulama (1h_WF): referansın kendi karar marjininden hesaplanan miktar, cüzdan kesmesi olmayan **tüm** girişlerde (345 → 372'nin 27'si hariç) `amount` ile birebir.

| Çalışma | B (anahtar) | C | ΣR ref/motor | komisyon | funding | işlem | `qty_rounding` (önce → sonra) |
|---|---|---|---|---|---|---|---|
| 1h_IS_f1_s0 | %12,4 (90,3) | %96,1 | 10,88 / 0,83 | 422,6 / 411,0 | 13,20 / 14,26 | 630 / 598 | 9 → 1 |
| 1h_WF_f1_s0 | %7,2 (87,2) | %95,7 | 23,66 / 36,86 | 393,2 / 378,1 | 9,04 / 9,30 geçti | 376 / 343 | 2 → 0 |
| 15m_IS_f1_s0 | %0,6 (85,6) | %85,6 | -160,6 / -130,4 | 893,0 / 1133,8 | 8,53 / 10,27 | 2195 / 2143 | 4 → 0 |
| 1h_IS_f2_s5 | %7,8 (87,6) | %96,1 | -96,9 / -72,4 | 762,6 / 775,9 geçti | 6,81 / 8,44 | 614 / 575 | 5 → 2 |

`qty_rounding` sınıfı kapandı (kalan 1-2: 1 adımlık özsermaye tahmini sınırı). ΣR çok oynak (1h_IS: 11,23 → 0,83): küçük miktar değişimleri zincirle işlem sırasını/özsermayeyi kaydırır; ΣR'nin bu aşamada yorumlanması anlamsızdır.

### Adım 3 — iz süren stop ham değeri (yalnız inceleme; motor DOĞRU)

5 satır (`price_rounding`; 3'ü 1h_IS_f1_s0 = f2_s5, 2'si 1h_WF). Her satırda aynı girdilerle (1h/4h veri, `compute_signals`, `trail_stop_path`, `trail_atr=3`, referansın `open_rate`/`planned_stop`) yol yeniden hesaplandı; çıkış anına kadar kapanmış son mumlar:

| Satır | ref çıkış | motor çıkış | yol[son bar] → tick | yol[son-1] → tick | son bar (saat): ATR, uç |
|---|---|---|---|---|---|
| BTC short 02-16 08:00 → 02-17 14:00 | 96828,0 | 96823,6 | 96823,673 → 96823,6 | 96828,057 → **96828,0** | 13:00: ATR 361,358, en düşük 95739,6 (sabit) |
| ETH short 02-16 14:00 → 02-17 08:00 | 2695,41 | 2695,39 | 2695,3956 → 2695,39 | 2695,4192 → **2695,41** | 07:00: ATR 20,8619 (06:00: 20,8705) |
| LINK long 09-11 17:00 → 09-12 12:00 | 24,173 | 24,174 | 24,173919 → 24,174 | 24,172468 → **24,173** | 11:00: ATR 0,21536, en yüksek 24,494 |
| TRX long 2026-01-01 16:00 → 01-02 05:00 | 0,2853 | 0,28531 | 0,28530296 → 0,28531 | 0,2852955 → **0,2853** | 04:00: ATR 0,000662346 |
| TRX short 2026-03-01 15:00 → 03-02 01:00 | 0,28127 | 0,28126 | 0,28126831 → 0,28126 | 0,2812751 → **0,28127** | 00:00: ATR 0,000779437 |

Bulgu: **5/5 satırda referans = iz yolunun bir önceki barı** (çıkış anından önceki SON kapanmış bar yok sayılıyor), motor = son kapanmış barı içeren yol. Referans tarafın ATR/uç değerleri dosyalanmamıştır (freqtrade çalıştırılmadı); iki taraf da aynı `trail_stop_path` ve aynı veriyi kullanır, ve referansın çıkış fiyatı 5/5 satırda tam olarak son barı hariç tutan yolla (bir bar eski ATR/uç) yeniden üretilir; yani fark girdi değerinde değil, stopun hangi bara kadar güncellendiğindedir: freqtrade çıkış mumunda stopu bir bar eski veriyle uygular, motor (`trail_stop_path` sözleşmesi ve `exit_context`: D'de kapanmış son bar D-1 dahil) nedensel olarak bir bar önce uygular. Motor spesifikasyona ve nedenselliğe uygundur, **hata değil** (native'i etkileyen bir düzeltme gerekmiyor). Bu bir freqtrade zamanlama farkıdır; aynı fark `gap_fill` kovasındaki (rel 4e-4…8e-4) ve 15m'deki 79 `price_rounding` + 191 `gap_fill` satırının büyük bölümünü açıklıyor olmalı (diğer satırlar için yoldaşlık bu raporda **ölçülmedi**). Öneri (mentor onayı gerekir): yalnız compat'ta stop güncellemesini bir bar geciktiren bir "freqtrade iz gecikmesi" kuralı; native değişmez.

### Adım 4 — zincirsiz tanı (`research/bt_chainfree_diag.py`)

Her referans girişi için motorun boyutlandırması (`risk.check_entry`, açık pozisyonlar referanstan) referansın kendi `equity_entry_est` değeriyle + adım-2 kesmesiyle yeniden hesaplandı. B < %99 olduğu için çalıştırıldı.

| Çalışma | ref giriş | zincirsiz tahmin = ref `amount` (±%0,5) | + ref stake kesmesi | açıklanan | motor boyutu = ref (gerçek) |
|---|---|---|---|---|---|
| 1h_IS_f1_s0 | 630 | 609 (%96,7) | 13 | %98,7 | 79 (%12,5) |
| 1h_WF_f1_s0 | 379 | 341 (%90,0) | 27 | %97,1 | 28 (%7,4) |
| 15m_IS_f1_s0 | 2195 | 1860 (%84,7) | 136 | %90,9 | 22 (%1,0) |
| 1h_IS_f2_s5 | 615 | 532 (%86,5) | 8 | %87,8 | 49 (%8,0) |

Sonuç: **kanıt tam değil**. Zincirsiz tahmin yüksek (%85-97) ama kalan satırlar iki gruba ayrılır: (a) `equity_entry_est` tahmin hatası (1h_IS_f2_s5'te 71 satır tahmin ref'ten %0,5-2 uzak; tahmin komisyon/funding içermez); (b) **"referans stake kesmesi"**: referansın gerçekleşen `stake_amount`'u kendi ledger karar marjininden %0,5+ küçük (1h_WF: 27/379; 15m: 136/2195) — freqtrade'in stake'i kesme nedeni (cüzdan/serbest bakiye/`max_stake`) tanımlanmadı; engine bunu `insufficient_margin` ret olarak modelliyor (`margin_accounting` 7-155 satır, işlem sayısı farkının bir nedeni). (b) motor hatası değil ama taklit edilmedi.

### Kapı kararı

**Kapı KAPALI kalır.** Hiçbir çalışmada §7.2 geçmedi: A %100 (geçti); B %0,6-12,8 (anahtar eşleşmesi %85,6-90,3, ≥%99 değil); C %85,6 (15m) / %95,7-96,1 (1h, ≥%97 değil); ΣR farkı büyük; komisyon yalnız 1h_IS_f2_s5'te, funding yalnız 1h_WF'de geçti; işlem sayısı tolerans dışı; açıklanamayan = 0. Kalan açık fark kaynakları (mentor kararı için): (1) freqtrade iz gecikmesi (adım 3); (2) `TraderV1` özsermaye tanımı (`wallet + calc_profit(1h kapanış)`, komisyonlu) ↔ motor mark; (3) freqtrade stake kesmesi / `margin_accounting`; (4) giriş sınırında funding (`funding_boundary`); (5) 15m'de komisyon +%27 (motor 1133,8 / ref 893,0) — nedeni incelenmedi.

### Yerel kip / model farkı (§7.4), yeniden üretildi (1h_IS, tick + A düzeltmeleri + adım 1-2 sonrası)

| Çalışma | n_trades | expectancy_R | ΣR | PF |
|---|---|---|---|---|
| (1) compat (15m, last, kayma komisyonda) | 597 | 0,001 | 0,83 | 0,936 |
| (2) native_last (1m, last, 2/2/5 bps) | 582 | -0,036 | -20,78 | 0,871 |
| (3) native_mark (1m, mark) | 573 | -0,014 | -7,19 | 0,913 |

(2)→(3) mark↔last: last stop 325, mark stop 312; mark'ın kaldırdığı stop **6**, eklediği **0**; ΔΣR = **+13,59** (eşleşen 563 işlemde ort. ΔR +0,043). Önceki (tick öncesi/A öncesi) tablo: n 620/610/602, ΔΣR +35,8; hedef riskin 0,014'e kilitlenmesi ve zincir nedeniyle sayılar kaydı, mark'ın yönü aynı (last tetik fitil stoplarıyla ΣR'yi düşürür). Ham: `research/crosscheck/1h_IS_f1_s0_model_diff.json`.
