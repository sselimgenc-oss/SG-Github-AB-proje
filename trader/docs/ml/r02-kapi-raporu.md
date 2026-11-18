# ML r02 kapı raporu — KOŞULMADI: güç yetersiz (18 Kasım 2026 — mentor)

**Karar: `ml1-r02-long-ctx-1r` KOŞULMADI — güç yetersiz (ön kayıt §8, güç ön hesabı vetosu).** Bu bir kapı sonucu (KABUL/RED) değildir. Eğitim yapılmadı, OOF üretilmedi, `gate_result.json` yazılmadı. ML `off`'ta kalır. r03 koşulmadı.

**Asıl bulgu:** güçsüzlüğün nedeni veri azlığı değil, **alınan-işlem katmanının kusurlu olması**. Katmandaki 660 alınmış işlemin tamamı 2021'de (2021-02-20 → 2021-11-03); dört sınav diliminde (2022-01-06 → 2026-05-01) **tek alınmış işlem yok**. Bu yüzden §10 dondurma kaydı **doldurulmadı ve dondurulmadı** (kusurlu katman dondurulmaz).

## 1. Kimlik

| Alan | Değer |
|---|---|
| Tarif | `ml1-r02-long-ctx-1r` (40 özellik) |
| `corpus_v2.parquet` sha256 | `4d7c76b0adb1c40f9ac4b966ce82bd815e65249a168a393d289bb9c11d2f7bc6` (manifest ile aynı); `content_sha256` `8d116b9792da2ff6b9452768a540c0c8b37a619d824c9ccbe610a424210e1ad8` |
| Derlem kurulum commit'i | `0f4a6c663a2f` (ağaç temiz); geçmiş yeniden yazımından sonra `cf6f25d` |
| `corpus_v2_taken.parquet` sha256 | `a03f28474ce256f6dc3aae05c06d8e89a2b8c261aba0d9adbccdf901cfe6536f` (manifest ile aynı) |
| Katman backtest `config_hash` | `ca6e1433c6f38832b0950d4fb00206f6da274f6fffcf1002df216e3230d3d40b` |
| Katman commit'i | `7399343` (ağaç temiz); geçmiş yeniden yazımından sonra `3c084d4` (`otonom-trading-arastirma/gecmis/commit-map-2026-11-17.txt`) |
| Ön kontrol commit'i (kod) | `3597ced` |
| lightgbm | 4.6.0 (kullanılmadı) |
| n_trials | 10 (defter 5 satır × 2; değişmedi) |

## 2. Koşudan önce yapılan izinli kontroller (§2.1, §8)

| Kontrol | Sonuç |
|---|---|
| Manifest alanları (`corpus_version`, `recipe_ids`, `source`, dönem, 10 çift, `horizon_bars` 72, `target_rs`, r02 40 / r03 8 / 43 özellik, `same_bar`) | tuttu (boru hattının `verify_corpus_manifest` denetimi hatasız) |
| `corpus.sha256` = diskteki dosya | tuttu |
| `code_sha256` (13 dosya) = bugünkü dosyalar | 13/13 aynı |
| `git.tree_clean` | true; `holdout_read` false; `ts_max` 2026-04-30 17:00 |
| `candle_gaps` | 10 çiftte 0; `funding_stale_count` 0 |
| Satır | 7335; yıl: 2021 1374, 2022 1305, 2023 1474, 2024 1361, 2025 1346, 2026 475 |
| `label_1r` | çözülmüş 7329 (poz 3731, neg 3598, taban oranı 0,5091), çözülmemiş 6 |
| Elle kontrol | 50/50 "elle doğru", bağımsız yeniden hesap 150/150 |
| Katman bütünlüğü | alınan 660, alınmayan 6669 (koşu tablosunda), eşleşmeyen alınmış 0, dönem sonu açık 0, R'sız 0 |

## 3. `--precheck-only` (r02) çıktısı

```
Kosu tablosu: {"corpus_rows": 7335, "overlay_rows": 660, "overlay_unmatched_entered": 0, "dropped_unresolved_taken": 0, "dropped_unresolved": 6, "dropped_taken_open_at_end": 0, "rows": 7329, "taken": 660, "not_taken": 6669}
Ozellik sagligi: bos=[] sabit=[] kopya=[] -> TEMIZ
Guc on hesabi (n_trials=10): DSR icin 1576 gun -> gereken t=3.22 (gunluk SR>=0.0812); IC icin 0 gun -> t>=2.00 <=> rho>=yok
Gereken IC rho = inf (IC gun sayisi 0); DSR icin gereken t = 3.22
GUC YETERSIZ (veto): gereken rho inf > 0.08; tarif kosulmaz
```
Çıkış kodu 8 (güç vetosu). Özellik sağlığı temiz. IC gün sayısı (alınmış işlemi olan sınav günü) **0** → gereken rho sonsuz > 0,08 → **veto**.

## 4. Neden: katman 2021-11-03'te duruyor (motor kilidi, strateji davranışı değil)

Yapısal sayım (özellik–etiket ilişkisine bakılmadı; yalnız `taken`/`ts` ve defterin atlama nedenleri):

| Dilim | Sınav | Eğitim satırı | Sınav satırı | Sınavda alınan |
|---|---|---|---|---|
| 0 | 2022-01-06 → 2023-02-04 | 1381 | 1406 | **0** |
| 1 | 2023-02-04 → 2024-03-04 | 2801 | 1598 | **0** |
| 2 | 2024-03-04 → 2025-04-02 | 4396 | 1441 | **0** |
| 3 | 2025-04-02 → 2026-05-01 | 5839 | 1477 | **0** |

Katman backtest'inin defteri (`var/backtests/corpus_v2_taken_v1b_native/ledger.sqlite`, `v_decisions`):

- 2021: alınan 660; `stop_width` 810; `entry_gate_closed` (`gate:stop_failed`) 219; `risk_denied` 7.
- 2022 → 2026: alınan **0**; her yıl tüm T1 adayları `entry_gate_closed` / `gate:stop_failed` (1305, 1474, 1361, 1346, 475) ya da `stop_width`.
- Son alınan işlem: BTC long, giriş 2021-11-03 18:00, çıkış 18:01, `exit_reason = other`, −1,23 R. Giriş anında koruyucu stop kurulamadı (stop zaten aşılmış), motor `stop_failed` giriş kilidini yazdı. Geri testte bu kilidi kaldıran yok; kalan 4,5 yıl boyunca tüm girişler kapalı kaldı.

Yani katman "stratejinin gerçekten aldığı işlemler"i 2021-11-03'ten sonra temsil etmiyor. Bütünlük sayaçları (eşleşmeyen 0, açık 0) bunu yakalamaz; çünkü hiç alınmamış işlem eşleşme hatası üretmez. Filtresiz v1b'nin bu koşudaki dönem sonucu (660 işlem, beklenti +0,077 R, PF 1,11, en büyük düşüş %17,0) da yalnız 2021'i ölçer.

## 5. Sonuç ve defter

- r02: **koşulmadı (güç yetersiz)**. Tek koşu hakkı kullanılmadı: hiçbir OOF ölçüsü üretilmedi, özellik–etiket / özellik–net R ilişkisine bakılmadı; `diag-…` satırı gerekmedi.
- Defter (`research/ml_trial_registry.csv`): değişmedi; 5 satır, n_trials = 10 (r02 ve r03 satırları sayılmaya devam eder).
- §10: doldurulmadı. Derlem v2 sağlam (sha256 yukarıda); dondurulmayan tek şey katmandır.
- r03 aynı katmanı kullanır; bu katmanla o da aynı vetoya takılır. Koşulmadı.
- Kapı eşikleri, özellik/etiket/ağırlık/pencere tanımları, dondurulmuş derlem kodu değişmedi. Kilitli dönem okunmadı.

## 6. Kullanıcı / mentor kararı gereken konu

Katmanın yeniden kurulması gerekir; bu, ön kayıttaki hiçbir tanımı değiştirmez (§2.2 tanımı aynen), ama motor geri test davranışına dokunur. Karar verilmesi gerekenler:

1. Geri testte `stop_failed` giriş kilidi nasıl ele alınacak (kâğıt/canlıda kilit doğru davranış; geri testte tek olay 4,5 yılı kapatıyor). Bu bir motor düzeltmesidir ve 19b/19c ile "aynı ayarlar" şartını etkileyebilir; karar `tasarim-kararlari.md`'ye yazılmalı.
2. Düzeltmeden sonra katman yeniden kurulur, manifestine **dilim başına alınan işlem sayısı** ve son alınan işlem tarihi eklenir, sonra `--precheck-only` (r02) yeniden çalıştırılır ve §10 doldurulup dondurulur.
3. Yeniden kurulan katmanla r02'nin koşulması ön kayıt açısından meşrudur: r02 hiç koşmadı, katman hiç dondurulmadı, sonuç görülmedi.
