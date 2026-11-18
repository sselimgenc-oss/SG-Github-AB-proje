# ML r02 kapı raporu — RED (18 Kasım 2026 — mentor)

**Karar: `ml1-r02-long-ctx-1r` RED.** Tek koşu yapıldı, sonuç kesindir (ön kayıt §8). İlk kalan adım: 1. IC kapısı (rho = −0,034, t = −1,22; pozitif dilim 2/4). 13 kontrolün 8'i kaldı. ML `off`'ta kalır; paket (`model_candidate.json`) kullanılmaz. Ön kayıt gereği sıradaki adım r03'tür (r02 KABUL değil).

**İkinci bulgu (strateji bilgisi, ML'den bağımsız ve daha önemli):** filtresiz v1b bu geri testte 5,3 yılda **para kaybediyor**: 4695 işlem, beklenti **−0,026 R**, kâr faktörü 0,92, en büyük düşüş %84,6 (§6). Kusurlu eski katmandaki "+0,077 R" yalnız 2021'in ilk 10 ayını ölçüyordu.

## 1. Kimlik

| Alan | Değer |
|---|---|
| Tarif | `ml1-r02-long-ctx-1r` (40 özellik; lojistik + LightGBM, `LGBM_PARAMS` aynen) |
| `corpus_v2.parquet` sha256 | `4d7c76b0adb1c40f9ac4b966ce82bd815e65249a168a393d289bb9c11d2f7bc6` |
| `corpus_v2_taken.parquet` sha256 | `87fe782f347df616302311fc42c97bc79e1d8ac8793a4d7af78a1227ae8ae3ab` |
| Katman kurulum commit'i | C = `8632b24` (ağaç temiz); manifest commit'i `ec757f7`; `config_hash` `7c0a9198471243869d2e345c804bd09119a7ab7b1d1b1f2f8ee8c5aab470c397` |
| Dondurma commit'i (§10) = koşu commit'i | `8db6344` (`gate_result.json` → `git.commit` `8db63446a601`, `tree_clean` true) |
| lightgbm | 4.6.0 |
| n_trials | 10 (defter 5 satır × 2; değişmedi) |
| Tepe bellek | 480 MB (tarif tavanı 1200 MB) |
| Ham çıktılar | `research/ml/r02/` (`gate_result.json`, `gate_report.md`, `oof_predictions.parquet`, `model_candidate.json`) |

## 2. Koşudan önce

| Adım | Sonuç |
|---|---|
| `verify_overlay_manifest` | hatasız (4 dilimde alınan 932 / 1040 / 918 / 974; `gate_closed_skips` boş; `corpus_sha256` diskle aynı) |
| `verify_corpus_manifest`, `code_sha256` 13/13, `verify_sample_check` (150/150) | hatasız |
| `--precheck-only` (r02), `ec757f7`, temiz ağaç | çıkış 0. Özellik sağlığı TEMİZ. Gereken IC rho **0,0558** ≤ 0,08 (1284 gün) → veto yok. DSR için gereken t 3,22 (günlük SR ≥ 0,0812; 1576 gün) |
| §10 dondurma | `8db6344`, koşudan önce commit'lendi ve itildi |
| Hızlandırılmış kod kanıtı | altın 3 çift, `8e63e5f` ↔ `8632b24`: `trades.csv` `5c24abf2…9b6df1`, `summary.json` `6d61844c…f7dad2`, `open_at_end.json` `66ebd29e…9393f3` bayt bayt aynı; yarıda kesilen `8e63e5f` katman koşusunun `exit_ts` < 2022-03-01 olan 950 işlemi birebir aynı |

Koşu tablosu: 7329 satır (alınan 4695, alınmayan 2634); etiketi çözülmemiş 6 satır atıldı (3'ü alınmış); eşleşmeyen alınmış 0; dönem sonu açık atılan 0.

## 3. Kapı sonucu (tek koşu; temiz çalışma ağacı, `8db6344`)

Seçilen model: lojistik (LightGBM lojistiği geçemedi: −0,0449 ≤ −0,0052 R). Sınav evreni: 3861 alınan işlem, 1284 gün.

| Adım | Sonuç | Değer | Kural |
|---|---|---|---|
| 1. IC (yalnız alınan) | **KALDI** | rho −0,0340, t −1,22; dilim rho +0,006 / −0,114 / +0,039 / −0,086 (pozitif 2/4) | rho > 0, t ≥ 2, ≥ 3 dilim pozitif |
| 2. Kalibrasyon (Brier) | **KALDI** | model 0,25319, taban 0,25049 | model < taban |
| 3a. Eşik bulundu | geçti | 0,46 (alınan oran %63,9) | alınan ≥ %30 |
| 3b. Net R farkı | **KALDI** | +0,0381 R; %90 alt sınır +0,0063 | ≥ +0,10 R ve alt sınır > 0 |
| 3c. Filtreli beklenti | **KALDI** | −0,0052 R (filtresiz −0,0434) | > 0 |
| 3d. DSR | **KALDI** | 0,0476 | ≥ 0,95 |
| 3e. PBO | **KALDI** | 0,581 | ≤ 0,25 |
| 3f. En büyük düşüş | geçti | filtreli 182,7 R, filtresiz 341,7 R | filtreli ≤ filtresiz |
| 3g. Dejenerasyon | geçti | tek çift çıkarınca en kötü fark +0,0298 R | fark > 0 |
| 3h. Holm | **KALDI** | p 0,113 | ≤ 0,10 |
| 4. Maliyet stresi | **KALDI** | −0,1756 R | ≥ −0,05 R |
| 5. Eşleme | geçti | 0 | ≤ 1e-9 |
| 6. Görevdeki | atlandı | etkin model yok | — |

Tanı (geçti/kaldı rolü yok): AUC 0,503 (%90 aralık 0,485–0,520; 0,5 = şans). Tüm satırlar IC'si rho −0,007. Platt eğimi kısıtlanan dilim: lojistik 0/4, LightGBM 1/4. İki yarı (alınan, zamana göre): 1. yarı filtreli −0,155 / filtresiz −0,121 R; 2. yarı +0,041 / +0,034 R. Filtre en iyi 10 işlemden 1'ini attı.

## 4. Yorum

- Model işlem düzeyinde ayırt etmiyor: sıralama gücü şans düzeyinde (AUC 0,503), bağlayıcı IC negatif, dört dilimin ikisinde ters işaretli. Bu, ön kayıttaki "kaldıysa ne öğreniriz" satırıdır: **40 özellikli bağlam bilgisi 5 yıllık veride işlem düzeyinde ayırt edici değil.**
- Görülen +0,038 R fark küçük bir pozitif artıktır ama eşiğin (+0,10 R) üçte biri; DSR ve PBO bunun seçim şansından ayırt edilemediğini söylüyor. Filtreli beklenti de sıfırın altında: filtre zararı azaltıyor, kâra çevirmiyor.
- Güç yeterliydi (gereken rho 0,056; 1284 gün). Bu "veri azdı" sonucu değil, gerçek bir RED'dir.
- 19c'nin kalma nedenleri olarak sayılan üç şey (kısa veri, bağlam yok, etiket–ızgara uyumsuzluğu) giderildi; sonuç değişmedi.

## 5. Sonuç ve defter

- r02: **RED**, kesin. Yeniden koşu, ayar, özellik/etiket değişikliği yok.
- Defter (`research/ml_trial_registry.csv`): değişmedi; 5 satır, n_trials = 10.
- Kapı eşikleri, tanımlar, dondurulmuş derlem ve katman değişmedi. Kilitli dönem (2026-05-01 → 2026-11-01) okunmadı.
- r03 (`ml1-r03-long-regime8`): ön kayıt §8 sıra 3 gereği, bu rapor commit'lendikten sonra, aynı dondurulmuş girdilerle, değiştirilmeden koşulur.

## 6. Filtresiz v1b'nin dönem sonucu (katman geri testi; ön kayıt §8'de bakılması izinli strateji bilgisi)

Kaynak: `var/backtests/corpus_v2_taken_v1b_native/summary.json` (C = `8632b24`; 2021-01-01 → 2026-05-01, 10 çift, 1s, yerel dolum, sentetik kurallar, işlem başı risk %0,5).

| Ölçü | Değer |
|---|---|
| İşlem | 4695 (kazanma oranı %31,4) |
| Beklenti | **−0,0256 R** (medyan −0,93 R) |
| Kâr faktörü | 0,92 |
| Net sonuç | −%60,4 (1000 birim başlangıçta −603,8) |
| En büyük düşüş | %84,6 |
| Brüt kâr / maliyet | brüt +269,2; maliyet 872,9 (komisyon 186,8 + kayma ≈ 593,3 + fonlama 92,8) |
| Rejim | `trend_down` 2540 işlem −0,018 R; `trend_up` 2155 işlem −0,034 R |
| Sınav dilimlerinde (2022-01 → 2026-04, 3861 işlem) | −0,043 R; ilk yarı −0,121 R, ikinci yarı +0,034 R |

Okuma: strateji maliyet öncesi hafif artıda, maliyet sonrası ekside. Bu, 19b'nin kısa dönem sonucuyla (819 işlem) çelişir ve ML'den ayrı bir karar konusudur: ML yalnız çıkarır, zarar eden bir temeli kâra çevirmesi beklenmez (r02 de çevirmedi). **Kullanıcı / mentor kararı gerekir** (v1b'nin kâğıt/canlı takvimi bu sonuca göre yeniden değerlendirilmeli); bu rapor o kararı vermez.

## 7. Önceki girişim (aynı gün, sonuç değil)

İlk `--precheck-only` güç vetosu vermişti (IC gün sayısı 0): o zamanki katmanda (sha256 `a03f2847…e6536f`, commit `7399343`) 660 alınan işlemin tamamı 2021'deydi; geri testte 2021-11-03'te `stop_failed` giriş kilidi kalıcı kalmıştı. O katman dondurulmadı, hiçbir OOF üretilmedi, tek koşu hakkı kullanılmadı. Düzeltme: BT-1 (`would_trigger` giriş kilidi yazmaz; `tasarim-kararlari.md` 18 Kasım) + katman korumaları (`taken_per_fold`, `gate_closed_skips`), sonra katman C = `8632b24` ile yeniden kuruldu. Ayrıntı bu dosyanın `8db6344` öncesi sürümünde.
