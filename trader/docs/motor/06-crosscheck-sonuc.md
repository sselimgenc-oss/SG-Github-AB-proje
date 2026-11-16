# 06 — Çapraz doğrulama sonucu (motor `legacy_compat` ↔ dondurulmuş freqtrade çıktıları)

Tarih: 16 Kasım 2026. Strateji: `price_action_v1_full` (TraderV1 eşdeğeri; v1b yapılandırması). Motor: `backtest --fill-model legacy_compat --granularity 15m --synthetic-rules --no-record-filtered` (uyum çalışması, yerel sonuç değildir). Referans: `user_data/backtest_results/<ID>/` ve `research/runs/<ID>.json` (freqtrade çalıştırılmadı). HOLDOUT (2026-05 → 2026-10) çalıştırılmadı. Ayrıntı: `research/crosscheck/<ID>.{md,json}`.

## Karar: KALDI (kapı geçilmedi) — açıklanamayan fark = 0

| Çalışma | A kararlar | B girişler | C çıkışlar | D ΣR (ref / motor) | D komisyon | D funding | D işlem sayısı |
|---|---|---|---|---|---|---|---|
| 1h_IS_f1_s0 | %100 geçti | %28 (anahtar %96,8) kaldı | %92,0 kaldı | 10,88 / 6,57 kaldı | 422,6 / 405,2 kaldı | geçti | 630 / 622 kaldı |
| 1h_WF_f1_s0 | %100 geçti | %20 (anahtar %90,4) kaldı | %95,3 kaldı | 23,66 / 28,80 kaldı | 393,2 / 362,1 kaldı | geçti | 376 / 349 kaldı |
| 15m_IS_f1_s0 | %100 geçti | %5 (anahtar %88,3) kaldı | %80,4 kaldı | -160,6 / -145,0 kaldı | 893,0 / 999,9 kaldı | geçti | 2195 / 2211 geçti |
| 1h_IS_f2_s5 | %100 geçti | %28 (anahtar %94,9) kaldı | %91,9 kaldı | -96,9 / -79,4 kaldı | 762,6 / 783,1 kaldı | kaldı | 614 / 614 geçti |

Eşikler (spec §7.2): A %100; B ≥ %99; C ≥ %97; ΣR ≤ %2; komisyon ≤ %2; funding ≤ %5; işlem sayısı ±max(1,%1).

Metrikler yan yana (referans `research/runs`, motor `summary.json`; aynı sözlük):

| Çalışma | n_trades ref/motor | expectancy_R ref/motor | PF ref/motor | profit_abs ref/motor | max_dd % ref/motor |
|---|---|---|---|---|---|
| 1h_IS_f1_s0 | 630 / 620 | 0,018 / 0,011 | 0,960 / 0,952 | -143,5 / -164,3 | 37,2 / 39,4 |
| 1h_WF_f1_s0 | 379 / 347 | 0,063 / 0,083 | 1,098 / 1,136 | 264,1 / 339,8 | 28,7 / 32,1 |
| 15m_IS_f1_s0 | 2195 / 2211 | -0,073 / -0,066 | 0,818 / 0,840 | -852,0 / -813,6 | 86,2 / 82,7 |
| 1h_IS_f2_s5 | 615 / 612 | -0,159 / -0,130 | 0,718 / 0,746 | -726,6 / -666,8 | 74,7 / 71,8 |

Yön ve büyüklük aynı (işaretler, PF sıralaması, DD düzeyi tutarlı); fakat spec toleransları sağlanmadı.

## Farkların nedenleri (hepsi sınıflandırıldı)

1. **İlk sapma `price_rounding`** (1h_IS: SOL short, çıkış 186,741 ↔ 186,74, göreli 5e-6): freqtrade iz/durdurma seviyesini motorun `round_tight` (order_manager/position_manager, tick'e sıkı yuvarlama) yaptığı gibi yuvarlamıyor. Fiyat farkı küçük, ama stop seviyesi bir tick kaydığı için bazı tetikler farklı bara düşüyor ve özsermaye ayrışıyor. Deneme: stop yuvarlamasını tümden kapatmak (geçici, kalıcı değil) da eşleşmedi (ref 3357,58 ↔ motor 3357,5847): referans yuvarlıyor ama başka yönde/kuralla. Yani `legacy_compat` için doğru kural "yuvarlama yok" değil, referansın yuvarlama yönü; bu 03 §4.5 "tick yuvarlamama — doğrulanacak" maddesinin bulgusudur ve 03/05 revizyonu gerektirir (kural sessizce değiştirilmedi; `engine.py`/`order_manager.py` bu birimin dosyası değil).
2. **Zincirleme** (`chained_after_first`, 1h_IS'de 1049 satır): ilk sapmadan sonra özsermaye ayrışır, boyut/pozisyon durumu farklılaşır. B düzeyindeki düşük oran bunun sonucudur (boyut farkı çoğunlukla %0,1–0,3, tek tek anahtar eşleşmesi %88–97).
3. `qty_rounding` (sentetik lot adımı, ref doldurma 0,009 ↔ motor 0,01), `gap_fill` (açılış gap'inde dolum), `funding_boundary` (giriş/çıkışta 00/08/16 sınır noktası sayımı, funding kalem farkları veriden yeniden hesapla birebir uyumlu), `margin_accounting`, `exit_before_entry`, `open_at_end`: beklenen, ayrı etiketli.
4. Düzey A: ortak anahtarlı tüm kararlarda %100 eşitlik. Sinyal/strateji katmanı freqtrade ile birebir; ayrışma yalnız dolum/yuvarlama/muhasebe katmanında.

Motor mu bağdaştırıcı mı: yuvarlama farkı motorun `legacy_compat` kuralının eksikliği (referans TraderV1 değil); referans dosyalar değiştirilmedi.

## Yerel kip / model farkı (1h_IS, spec §7.4)

| Çalışma | n_trades | expectancy_R | ΣR | PF |
|---|---|---|---|---|
| (1) compat (15m, last, kayma komisyonda) | 620 | 0,011 | 6,57 | 0,952 |
| (2) native_last (1m, last, 2/2/5 bps) | 610 | -0,047 | -28,39 | 0,863 |
| (3) native_mark (1m, mark) | 602 | 0,011 | 7,39 | 0,956 |

(2)→(3) mark↔last: last stop 336, mark stop 325; mark'ın kaldırdığı stop 6, eklediği 0; ΔΣR = +35,8 (eşleşen 589 işlemde ort. ΔR +0,040). Bu fark yerel/1m çalışmada ayrıntı+maliyet etkisi (1→2: ΔΣR ≈ -35) ile mark etkisinin (2→3: ≈ +36) büyüklükçe aynı olduğunu gösterir: last tetikte fitil stopları ΣR'yi belirgin düşürüyor (risk tablosu 2 için ölçüm).

## Sonuç ve sonraki adım

- A düzeyi geçti, açıklanamayan 0; B/C/D toleransları geçmedi → §4.3 kapısı **açılmaz**.
- Kapatmak için: referansın tick/stop yuvarlama kuralını belirleyip (03 §4.5 revizyonu) `legacy_compat`'ta uygulamak, sonra dört çalışmayı yeniden koşmak. Zincirleme etkisi kalktığında B/C/D'nin geçmesi beklenir; ilk sapma tek bir sınıf (`price_rounding`).
- Model farkı raporu yalnız 1h_IS için üretildi (diğer dönemler gerekirse aynı komutlarla; ~45 dk/çalışma, 1 GB RAM).
