# Ön kayıt: `ml1-r02-long-ctx-1r` ve `ml1-r03-long-regime8` (17 Kasım 2026 — mentor)

**Durum: derlem v2 henüz YOK.** Bu belge, derlem sunucuda kurulmadan ve kimse tek satırını görmeden yazıldı (geçmiş 2021-01 → 2026-04 şu an indiriliyor). Hiçbir veri dosyası okunmadı; kilitli dönem (2026-05-01 ve sonrası) okunmadı. Aşağıdaki her tanım koşudan önce sabittir; sonuç görüldükten sonra hiçbiri değişmez. Kapı eşikleri (`trader_ml/config.py`: `GATE`, `THRESHOLD_GRID`, `MIN_TAKEN_FRAC`, `BURN_IN_THRESHOLD`) **aynen** kalır; bu belge eşik gevşetmez.

Dayanak: `otonom-trading-arastirma/ml-guclendirme-plani.md` §3.0, §3.1, §3.2, §3.2.1; `ml-faz-tasarimi.md` §3.4 ve §3.4a (r01 ön kaydı; "bağlayıcı evren yalnız alınan işlemler" kuralı burada da geçerlidir). Çelişki olursa `tasarim-kararlari.md` geçerlidir.

Defter: `research/ml_trial_registry.csv`'ye iki satır bu belgeyle birlikte eklendi (bkz. §9).

---

## 1. Varsayımlar

| Tarif | Varsayım | Kaldıysa ne öğreniriz |
|---|---|---|
| **r02** `ml1-r02-long-ctx-1r` | 19c'nin kalma nedenleri (kısa veri, piyasa bağlamı yok, etiket–ızgara uyumsuzluğu) giderilirse, işlem başı filtre v1b'nin alınan işlemlerinde net R'ı ölçülebilir biçimde artırır. Beklenen etki: günlük IC 0,06–0,08; adayların %50–60'ı tutulduğunda +0,08–0,12 R. Ön olasılık %15–25. | 40 özellikli bağlam bilgisi, 5 yıllık veride işlem düzeyinde ayırt edici değil. |
| **r03** `ml1-r03-long-regime8` | Kâr/zarar piyasa rejimiyle sallanıyor (plan 2.4 c–d); filtre işlem değil rejim düzeyinde çalışmalı. 8 piyasa düzeyi özellik 4 dilimde kararlı kalır ve aşırı uyum (PBO) riski düşüktür. | Rejim bilgisi bu 8 ölçüyle yakalanmıyor. |

İkisi de yalnız filtredir (işlem çıkarır; boyut, stop, hedef, kaldıraç belirlemez).

## 2. Derlem tanımı

### 2.1 Aday derlemi (derlem v2)

Üretici: `scripts/build_corpus_v2.py` (ML-G6, commit `9dfb475` ve sonrası düzeltmeler; kurulum commit'i manifestte). Çıktı: `research/ml/corpus_v2.parquet` + `research/ml/corpus_v2.manifest.json` + `research/ml/corpus_v2.sample_check.md`.

Koşudan önce manifestte **birebir** doğrulanacak alanlar (biri tutmazsa koşu başlamaz):

| Manifest alanı | Zorunlu değer |
|---|---|
| `corpus_version` | `corpus_v2` |
| `recipe_ids` | `["ml1-r02-long-ctx-1r", "ml1-r03-long-regime8"]` |
| `source` | `native_v1b` |
| `candidate_definition` | post_filter öncesi yerel v1b adayı: `feature_frame` + `candidate_rows` (19b kodu), sinyal True, kurulum T1, iki yön, 10 çift |
| `period.start` / `period.end_exclusive` | `2021-01-01 00:00:00+00:00` / `2026-05-01 00:00:00+00:00` |
| `period.holdout_read` | `false`; `period.ts_max` < 2026-05-01 |
| `pairs` | BTC, ETH, BNB, SOL, XRP, DOGE, ADA, TRX, LINK, AVAX (`/USDT:USDT`), bu sırayla, tam 10 |
| `horizon_bars` / `target_rs` | `72` / `[1.0, 1.5, 2.0]` |
| `git.tree_clean` | `true` (`git.dirty` boş); `git.commit` kayda geçer |
| `r02_features` / `r03_features` | §3'teki listelerle ad ad ve sırayla aynı (40 / 8) |
| `n_features` / `feature_columns` | 43; r02 (40) + `f_btc_vr`, `f_btc_vol_1d_pct90`, `f_side_x_btc_slope_1d` |
| `same_bar.rows_unique_pair_ts` | `true` |
| `same_bar.feature_matches_distinct_pairs` | `true` |
| `corpus.sha256` | diskteki `corpus_v2.parquet` dosyasının `sha256sum` çıktısıyla aynı |
| `code_sha256` | koşu commit'inde aynı dosyaların sha256'sı ile aynı (özellik/etiket kodu kurulumla koşu arasında değişmemiş) |
| `inputs_sha256`, `input_slices` | kayda geçer; `candle_gaps` > 0 olan çift varsa nedeni arşiv boşluk raporuyla açıklanmış olmalı |

Ek ön koşul: `corpus_v2.sample_check.md` içinde 50 etiketin elle kontrolü tamamlanmış, "Bağımsız yeniden hesap uyumu: 150/150". Tek hatalı etiket varsa derlem kullanılmaz.

**Derlem sha256'sı bugün bilinmiyor.** Kurulumda manifestten okunur, §10'daki dondurma kaydına yazılır ve commit'lenir. Koşu yalnız bu sha256 ile başlar; dondurmadan sonra derlem yeniden kurulmaz.

### 2.2 Alınan işlem / gerçek net R katmanı (zorunlu; derlem v2'de yok)

Derlem v2 yalnız fiyat bariyeri etiketleri taşır: `taken`, gerçek `net_r` ve `exit_ts` sütunları yoktur. Kapının bağlayıcı evreni ise r01 ön kaydındaki gibi **stratejinin gerçekten aldığı işlemler ve onların gerçek çıkış kuralıyla net R'ıdır**. Bu tanım değişmez; bariyer getirisi (`barrier_net_r_1r`) kapıda gerçek net R'ın yerine **kullanılmaz** (kâr kuyruktan geliyor; bariyer getirisi stratejinin sonucunu ölçmez).

Bu yüzden ikinci, ayrı bir girdi kurulur (`research/ml/corpus_v2_taken.parquet` + manifest):

- Motor backtest'i, 19b ile aynı ayarlar: `--period 20210101-20260501 --tf 1h --fill-model native --strategy price_action_v1 --synthetic-rules --target-trade-risk 0.005`; `rules_source = synthetic-preholdout` (19b'deki kayıtlı istisna aynen); `config/engine.base.json` o commit'teki haliyle. Kilitli dönem koşulmaz.
- Defterden okunanlar: `v_decisions` (karar: çift, `bar_close_ts`, yön, `final_action`) ve `v_trades` (`exit_ts`, `r_multiple`, `exit_reason`).
- Eşleme anahtarı: (`pair`, `ts` = `bar_close_ts`, `side`).
- `taken` = defterde `final_action == "entered"` olan ve derlem satırıyla eşleşen adaylar. Eşleşmeyen derlem satırları (post_filter'ın elediği, risk/emir nedeniyle atlanan) `taken = False`.
- Alınan satırlarda `net_r` = `r_multiple` (komisyon + kayma + fonlama sonrası, gerçek çıkış), `exit_ts` = gerçek çıkış zamanı.
- Alınmayan satırlarda `net_r` = `barrier_net_r_1r`, `exit_ts` = boş. Bu değer **yalnız tanı satırlarında** (tüm satırlar IC'si) görünür; eşik seçimi, net R farkı, DSR, PBO ve stres yalnız alınan satırlardan hesaplanır (kod bugün de böyle).
- Dönem sonunda açık kalan alınmış işlemler (çıkışı yok) tablodan atılır; sayısı rapora yazılır.
- **Bütünlük şartı:** defterde alınmış olup derlemde karşılığı bulunmayan işlem sayısı **0** olmalıdır. Değilse koşu başlamaz, mentor inceler (derlem ile motorun aday kümesi ayrışmış demektir).
- Bu dosyanın sha256'sı, backtest ayar özeti (`config_hash`) ve commit'i de §10'a yazılır ve dondurulur.

### 2.3 Koşu tablosu (iki tarifte aynı satırlar)

Koşu tablosu derlem + katmandan bellekte, deterministik olarak kurulur:

1. `label` = `label_1r`; `label_end_ts` = `label_end_ts_1r`.
2. `label` boş (çözülmemiş: son 72 mum) satırlar atılır.
3. `source`: `native_v1b` → kaynak ağırlığı tablosunda `backtest` (0,3). Tüm satırlar aynı kaynaktandır.
4. `cost_r`, `planned_*`, `setup` derlemden aynen.
5. Özellik sütunları: yalnız tarifin listesi, §3'teki sırayla. Diğer `f_*` sütunları modele verilmez.

Eğitim evreni: tüm satırlar (alınan + alınmayan). Sınav (bağlayıcı) evreni: yalnız alınanlar.

## 3. Özellik listeleri (ad ad; fazlası/eksiği yok)

Kod kaynağı: `trader_core/ml_features_v2.py` (`R02_FEATURE_NAMES`, `R03_FEATURE_NAMES`). Tanımlar plan §3.2.1 madde 1–7'dedir ve aynen geçerlidir (evren 10 çift, en az 5 geçerli çift; genişlik; sıra; `f_same_bar_signals`; fonlama `ts`'den kesin önce; sabit 200 günlük 1g geri bakış; BTC varyans oranı q=4, pencere 96).

**Bayat fonlama (3.2.1 madde 6):** `ts`'den önceki en yeni fonlama olayı 9 saatten eskiyse `f_funding_last` ve `f_funding_sum3` NaN olur ve sayılır (`funding_stale_count` manifestte); hiç olay yoksa da NaN. Eğitim ve canlı aynı kuralı uygular.

**r02 — 40 özellik, bu sırayla:**

Çekirdek (15): `f_atr_ratio`, `f_stop_dist_atr`, `f_side_sign`, `f_slope_1h`, `f_slope_4h`, `f_slope_1d`, `f_slope_4h_aligned`, `f_vol_1h`, `f_vol_4h`, `f_vol_1d`, `f_atr_pct_1h`, `f_hour_sin`, `f_hour_cos`, `f_dow_sin`, `f_dow_cos`

Bağlam (25): `f_btc_slope_4h`, `f_btc_slope_1d`, `f_btc_vol_4h`, `f_btc_vol_1d`, `f_eth_slope_4h`, `f_eth_slope_1d`, `f_eth_vol_4h`, `f_btc_er_24`, `f_btc_er_96`, `f_breadth`, `f_rank_ret_24h`, `f_rank_ret_7d`, `f_corr_btc_7d`, `f_funding_last`, `f_funding_sum3`, `f_same_bar_signals`, `f_vol_z_24`, `f_vol_z_168`, `f_range_atr`, `f_body_ratio`, `f_close_pos`, `f_dist_hi20_atr`, `f_dist_lo20_atr`, `f_dist_hi50_atr`, `f_dist_lo50_atr`

**r03 — 8 özellik, bu sırayla:** `f_btc_slope_4h`, `f_btc_slope_1d`, `f_btc_er_96`, `f_btc_vr`, `f_btc_vol_1d_pct90`, `f_breadth`, `f_same_bar_signals`, `f_side_x_btc_slope_1d`

Özellik sağlık kontrolü (ML-G1) gerçek koşuda zorunludur: tamamı boş, sabit ya da birebir kopya özellik varsa koşu **reddedilir**; özellik sessizce atılmaz (liste değişirse tarif değişmiş olur ve yeni defter satırı gerekir).

Bilinen ve kabul edilen sınır: geçmiş 2021-01'de başladığı için 1g bağlam özellikleri (200 günlük geri bakış) 2021'in ilk ~200 gününde NaN'dır. Bu satırlar yalnız eğitimdedir (ilk sınav dilimi 2022-01-06'da başlar); LightGBM NaN'ı kendi işler, lojistik eğitim medyanıyla doldurur. Satır atılmaz.

## 4. Etiket

`label_1r`: planlanan girişe göre **+1R'a stoptan önce, 72 adet 1s mum içinde** (aynı mumda ikisi birden değerse stop önce; 72 mum dolarsa 0). Arındırma, ambargo, teklik aralığı ve ileri kalibrasyonda `label_end_ts_1r` kullanılır. Çözülmemiş satırlar atılır. İki tarifte aynı.

## 5. Ağırlık

`WEIGHT_SCHEME = "uniq_decay"` (`trader_ml.weights.sample_weights_v2`): kaynak (0,3; sabit) × teklik (tüm çiftler havuzlanmış, ortalama 1) × doğrusal zaman azalması (**en eski 0,3**, en yeni 1,0; aynı `ts`'li satırlar eşit). **Her dilimin arındırma/ambargo sonrası eğitim satırlarında** hesaplanır; tüm tabloda hesaplanıp dilime kesilmez. Nihai (paket) modelde tüm koşu tablosunda hesaplanır. Sınıf ağırlığı yok. İki tarifte aynı.

## 6. Model çifti, ayarlar, kalibrasyon

| | r02 | r03 |
|---|---|---|
| Lojistik | `LOGIT_PARAMS` aynen (`l2 = 1.0`, `max_iter = 100`) | aynı |
| LightGBM | `LGBM_PARAMS` aynen: `max_depth 4`, `num_leaves 15`, `min_data_in_leaf 50`, `learning_rate 0.05`, en fazla 300 ağaç, erken durdurma 30, `feature_fraction 1.0`, `bagging_fraction 1.0`, `lambda_l2 1.0`, `seed 7`, deterministik, tek iş parçacığı | `LGBM_PARAMS` üzerinde yalnız üç değişiklik: **`max_depth 2`, `num_leaves 4`, `min_data_in_leaf 100`** (plandaki "derinlik 2, yaprak 100": yaprak başına en az 100 satır; derinlik 2'nin en fazla yaprak sayısı 4). Gerisi aynen |
| Erken durdurma | eğitim satırlarının kronolojik son %20'si doğrulama, arındırmalı (mevcut `fit_lgbm`) | aynı |
| Model seçimi | LightGBM, ileri yönlü filtreli net R'da lojistiği geçerse LightGBM; aksi hâlde lojistik (mevcut kural) | aynı |
| Platt | ileri yönlü; **eğim a ≥ 0** (`PLATT_NONNEG_SLOPE = True`). Kısıtlanan dilimde p = önceki satırların taban oranı; kısıtlanan dilim sayısı raporda. İlk dilim: özdeşlik + sabit eşik 0,50 (dondurulmuş) | aynı |
| Paket | paket düzeyi kalibrasyon kısıtlanırsa paket üretilmez (`CalibrationClamped`) | aynı |
| lightgbm | gerçek koşuda zorunlu; sürüm rapora yazılır | aynı |

## 7. Yürüyen pencere (derlem v2 için yeniden tanımlandı; iki tarifte aynı)

Saat ızgarası: başlangıç **2021-01-01 00:00 UTC**, bitiş (dışlayıcı) **2026-05-01 00:00 UTC** = 46.704 mum. Genişleyen pencere (`anchored`), arındırma 72 mum, ambargo 24 mum (değişmedi).

`train_bars = 8784` (366 gün), `test_bars = step_bars = min_test_bars = 9456` (394 gün). `trader_core.stats.walk_forward_splits(46704, 8784, 9456, 9456, anchored=True, purge=72, embargo=24, min_test=9456)` **tam 4 dilim** verir:

| Dilim | Eğitim (mum açılışı) | Sınav başı | Sınav sonu (dışlayıcı) |
|---|---|---|---|
| 0 | 2021-01-01 → 2022-01-02 | 2022-01-06 | 2023-02-04 |
| 1 | 2021-01-01 → 2023-01-31 | 2023-02-04 | 2024-03-04 |
| 2 | 2021-01-01 → 2024-02-29 | 2024-03-04 | 2025-04-02 |
| 3 | 2021-01-01 → 2025-03-29 | 2025-04-02 | 2026-05-01 |

Sınav dönemi toplam 1.576 gün. Ek olarak etiketi sınav başından 24 mum öncesine taşan eğitim satırları atılır (mevcut `make_folds` kuralı). Dilim sayısı 4 değilse ya da bir dilim atlanırsa (eğitim satırı < 100 ya da boş sınav) kapı 1. adımda kalır (mevcut kural: "tam 4 dilim").

Plandaki "her dilim ~13 ay" ifadesi 394 gün olarak sabitlendi (arındırma + ambargo payı 4 gün ızgaradan düşer; ilk eğitim 366 gün ≥ 12 ay).

## 8. Kapı, geçti/kaldı, koşu kuralları

**Kapı:** `trader_ml.gate.run_gate` ve `config.GATE` aynen. Bağlayıcı evren yalnız alınan işlemler, gerçek net R. Kontroller: 1 (IC: tam 4 dilim, rho > 0, t ≥ 2, ≥ 3 dilim pozitif, günlük toplulaştırma), 2 (Brier < taban), 3a (ızgara [0,45–0,70], alınan oran ≥ %30), 3b (fark ≥ +0,10 R ve %90 alt sınır > 0), 3c (filtreli beklenti > 0), 3d (DSR ≥ 0,95, n_trials defterden), 3e (PBO ≤ 0,25), 3f (düşüş), 3g (dejenerasyon; tek çift çıkarma), 3h (Holm ≤ 0,10), 4 (maliyet stresi ≥ −0,05 R), 5 (eşleme ≤ 1e-9), 6 (görevdeki yok → atlanır). `n_boot = 2000`.

**GEÇTİ (KABUL):** `gate_result.json` içinde `passed = true` (bütün kontroller + uygun paket eşiği). Sonuç: paket gölge (`shadow`) adayıdır; `active` için ayrıca ≥ 6 hafta gölge + kullanıcının Telegram onayı gerekir. Sonraki tarifler durur (plan §3.0).

**KALDI (RED):** herhangi bir kontrol başarısız; ya da paket kalibrasyonu kısıtlandı (çıkış kodu 4: sinyalsiz model). RED geçerli bir sonuçtur, kayda geçer; ML `off`'ta kalır.

**Koşulmadı sayılan durumlar (sonuç değil; defter satırı yine sayılır):**
- Özellik sağlık kontrolü reddi (çıkış kodu 3) → tarif bu listeyle koşulamaz; liste değişikliği yeni tariftir.
- Güç ön hesabı vetosu: `--precheck-only` çıktısında IC için gereken günlük sıra korelasyonu **> 0,08** ise (beklenen etkinin üst ucu) tarif koşulmaz, rapora "güç yetersiz" yazılır. DSR için gereken t yalnız raporlanır, veto değildir.
- Teknik kesinti (lightgbm yok, bellek/süre sınırı, çökme) **ve** hiçbir OOF ölçüsü yazılmamış/yazdırılmamışsa: aynı commit, aynı sha256'larla bir kez daha başlatılabilir; kesinti rapora yazılır. `gate_result.json` yazıldıktan sonra sonuç kesindir.

**Tek koşu:** her tarif için bir gerçek koşu. Yeniden koşu, ayar, özellik/etiket/ağırlık/pencere değişikliği yok. Değişiklik = yeni tarif kimliği + yeni defter satırı.

**Koşudan önce bakılabilecekler (sonucu etkilemez):** manifest (satır sayıları, etiket çözülme ve taban oranları, NaN oranları, boşluklar), 50 etiket elle kontrol, katmanın bütünlük sayıları, filtresiz v1b'nin dönem sonucu (strateji bilgisi), `--precheck-only` (özellik sağlığı + güç). **Yasak:** derlem v2 üzerinde özellik–etiket ya da özellik–net R ilişkisine bakan her şey (korelasyon, grafik, deneme eğitimi, OOF) — tek gerçek koşu dışında. Böyle bir bakış olursa `diag-…` satırıyla deftere yazılır (n_trials +2).

**Sıra:**
1. Kod işi (iş emri) birleşir → derlem v2 kurulur → manifest + elle kontrol → katman kurulur → `--precheck-only` (r02) → §10 dondurma kaydı commit'lenir.
2. **r02 tek koşu** → `docs/ml/r02-kapi-raporu.md` + `tasarim-kararlari.md` satırı, commit.
3. **r03 yalnız r02 raporu commit'lendikten sonra** ve yalnız r02 KABUL değilse: `--precheck-only` (r03) → tek koşu → `docs/ml/r03-kapi-raporu.md`. r02 KABUL ise r03 koşulmaz (satırı defterde sayılmaya devam eder). r03, r02'nin sonucuna göre **değiştirilmez**; bu belgedeki haliyle koşar.
4. r03 aynı dondurulmuş derlem ve katmanı kullanır (aynı sha256'lar).

Ham çıktılar: `research/ml/r02/` ve `research/ml/r03/` (`gate_result.json`, `gate_report.md`, `oof_predictions.parquet`, `model_candidate.json`).

## 9. Deneme sayısı (n_trials)

Kural değişmedi: n_trials = defterdeki satır sayısı × 2 model (`trader_ml.registry.n_trials_from_registry`). Satır silinmez, sayı sıfırlanmaz.

| | Satır | n_trials |
|---|---|---|
| Bu kayıttan önce | `ml0c-baseline-v1`, `ml1-r01-v1b-native33`, `diag-19c-univariate` | 3 × 2 = **6** |
| Bu kayıtla | + `ml1-r02-long-ctx-1r`, + `ml1-r03-long-regime8` | 5 × 2 = **10** |

İki satır aynı anda eklendiği için **r02 de n_trials = 10 ile** değerlendirilir (r03 henüz koşmamış olsa bile). Bu bir sıkılaştırmadır. Koşu anında defterde daha fazla satır varsa o sayı kullanılır; `--n-trials` yalnız büyütebilir.

Ön güç hesabı (veri görülmeden, yalnız takvimden; kesin sayılar `--precheck-only` ile koşudan önce yazdırılır ve §10'a girer): 1.576 sınav günü ve n_trials = 10 ile DSR ≥ 0,95 için filtreli günlük serinin t değeri ≈ **3,2** (günlük Sharpe ≈ 0,081). IC kapısı için gereken günlük sıra korelasyonu = 2 / √(N + 2), N = alınan işlemi olan sınav günü sayısı (ör. N = 1.400 → 0,053).

## 10. Dondurma kaydı (derlem kurulunca doldurulur; koşudan ÖNCE commit'lenir)

Bu tabloyu doldurmak tanım değişikliği değildir. Tablo commit'lenmeden koşu başlamaz.

**Durum notu (18 Kasım 2026 — mentor):** tablo **doldurulmadı, dondurma yapılmadı.** `--precheck-only` (r02) güç vetosu verdi (IC gün sayısı 0 → gereken rho sonsuz > 0,08): alınan-işlem katmanındaki 660 işlemin tamamı 2021'de, sınav dilimlerinde alınan işlem yok (geri testte 2021-11-03'te `stop_failed` giriş kilidi kalıcı kaldı). r02 koşulmadı; ayrıntı `docs/ml/r02-kapi-raporu.md`. Derlem v2 sha256 `4d7c76b0…2f7bc6` doğrulandı; kusurlu katman (sha256 `a03f2847…e6536f`, `config_hash` `ca6e1433…d3d40b`, commit `7399343` = yeniden yazım sonrası `3c084d4`) dondurulmaz, yeniden kurulmalıdır.

**Dondurma notu (18 Kasım 2026 — mentor): tablo dolduruldu, DONDURULDU.** Katman, `tasarim-kararlari.md` 18 Kasım kararına (BT-1: `would_trigger` giriş kilidi yazmaz) göre temiz çalışma ağacında C = `8632b24` ile yeniden kuruldu; derlem v2 yeniden kurulmadı. §2.2 tanımı ve bu belgedeki diğer tanımlar değişmedi. `verify_overlay_manifest` ve `verify_corpus_manifest` hatasız; `--precheck-only` (r02) güç şartını geçti.

Katmanın hızlandırılmış kodla (`8632b24`) kurulmasının sonucu değiştirmediğinin kanıtı — altın 3 çift eşdeğerliği, `8e63e5f` (hızlandırma öncesi) ile `8632b24`, aynı `--id eqv`, üç dosya bayt bayt aynı:

- `trades.csv` `5c24abf29d59cb278619410d24b6b22bc3a3f489756e9d7d19e607117c9b6df1`
- `summary.json` `6d61844c11fac65b646c3bf7e1b7608cb983c8d4567be546f90202429df7dad2`
- `open_at_end.json` `66ebd29ed9ec29e6f3786a76e25a0b0a3ff32be1aa0b37808e6af0c5e39393f3`

Çapraz denetim: yarıda kesilen `8e63e5f` katman koşusunun defterindeki `exit_ts` < 2022-03-01 olan 950 işlem, yeni katmandakilerle birebir aynı.

| Alan | Değer |
|---|---|
| `corpus_v2.parquet` sha256 (`corpus.sha256`) | `4d7c76b0adb1c40f9ac4b966ce82bd815e65249a168a393d289bb9c11d2f7bc6` |
| `corpus.content_sha256` | `8d116b9792da2ff6b9452768a540c0c8b37a619d824c9ccbe610a424210e1ad8` |
| Derlem kurulum commit'i (`git.commit`, ağaç temiz) | `0f4a6c663a2f` (ağaç temiz); geçmiş yeniden yazımından sonra `cf6f25d`. Derlem yeniden kurulmadı |
| Satır sayısı; yıl bazında; `label_1r` çözülmüş / çözülmemiş | 7335; 2021 1374, 2022 1305, 2023 1474, 2024 1361, 2025 1346, 2026 475; çözülmüş 7329 / çözülmemiş 6 |
| `funding_stale_count` | 0 (`candle_gaps` 10 çiftte 0) |
| Elle kontrol (150/150) | 50/50 elle doğru; bağımsız yeniden hesap 150/150 (`verify_sample_check` hatasız) |
| `corpus_v2_taken.parquet` sha256; backtest `config_hash`; commit | `87fe782f347df616302311fc42c97bc79e1d8ac8793a4d7af78a1227ae8ae3ab`; `7c0a9198471243869d2e345c804bd09119a7ab7b1d1b1f2f8ee8c5aab470c397`; katman kurulum commit'i **C = `8632b24`** (ağaç temiz; BT-1 düzeltmesi + geri test hızlandırması), manifest commit'i `ec757f7` |
| Alınan / alınmayan satır; eşleşmeyen alınmış işlem (0 olmalı); dönem sonu açık atılan | katman: alınan 4698, atlanan 2637, eşleşmeyen alınmış **0**, R'sız 0, dönem sonu açık 3. Koşu tablosu: 7329 satır, alınan 4695, alınmayan 2634 (etiketi çözülmemiş 6 satır atıldı; 3'ü alınmış). Dilim başına alınan 932 / 1040 / 918 / 974; yıl: 2021 809, 2022 873, 2023 952, 2024 896, 2025 868, 2026 300; ilk giriş 2021-02-20 17:00, son giriş 2026-04-30 05:00; `gate_closed_skips` boş |
| Koşu commit'i (kod) | bu dondurma commit'i (yalnız bu belge değişir; kod `ec757f7` ile aynı, `code_sha256` 13/13 tutuyor). Kesin karma `gate_result.json` ve r02 raporuna yazılır |
| lightgbm sürümü | 4.6.0 |
| `--precheck-only` r02: özellik sağlığı; gereken t (DSR), gereken rho (IC), IC gün sayısı | TEMİZ (boş/sabit/kopya yok); t = 3,22 (günlük SR ≥ 0,0812; 1576 gün); rho = **0,0558** ≤ 0,08 → veto yok; IC gün sayısı 1284. Çıkış kodu 0 (`ec757f7`, temiz çalışma ağacı) |
| `--precheck-only` r03 (r02 raporundan sonra doldurulur) | r02 RED (rapor commit'i `a17c708`). r03 ön hesabı `a17c708`'de, temiz çalışma ağacında, `--prior-result research/ml/r02/gate_result.json` ile: TEMİZ (8 özellik; boş/sabit/kopya yok); t = 3,22; rho = **0,0558** ≤ 0,08 → veto yok; IC gün sayısı 1284; çıkış 0. Aynı sha256'lar. r03 koşu commit'i: bu satırı ekleyen commit |
| Koşu anındaki n_trials | 10 (defter 5 satır × 2; değişmedi) |

## 11. Değişmeyenler

Kilitli dönem 2026-05-01 → 2026-11-01 okunmaz. Kapı eşikleri değişmez. ML yalnız çıkarır. Deneme sayısı sıfırlanmaz. r01 kaydı ve `config.RECIPE_ID` / `WEIGHT_SCHEME` / `PLATT_NONNEG_SLOPE` varsayılanları (r01 davranışı) yerinde kalır; r02/r03 ayarları tarif seçimiyle açılır.
