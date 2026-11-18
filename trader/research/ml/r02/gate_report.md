# ML terfi kapısı raporu — RED

## Özet

- Seçilen model: **logistic** (LightGBM lojistigi net R'de gecemedi (-0.0449 <= -0.0052))
- Eşik (dondurulmuş, eğitim dışı dilimlerde seçildi): 0.48
- Tarif: `ml1-r02-long-ctx-1r` | model türü: logistic | eğitim örneği: 7329
- Eğitim penceresi: 2021-01-19T21:00:00+00:00 → 2026-04-30T00:00:00+00:00
- Kilitli dönem (2026-05 → 2026-10) okunmadı (kod korumalı).
- Model oluşturma: 2026-11-18T15:25:36.588187+00:00 | son kullanma: 2026-12-09T15:25:36.588187+00:00 (21 gün)
- Veri özeti: `047e05dccaa53c48…` | kod özeti: `ca9007034a673367…` | model özeti: `7807f2110334763a…`
- Özellik listesi özeti: `2920d452c0b3fe8e…` (40 özellik)
- Korpus sha256 (aday dosyası): `4d7c76b0adb1c40f9ac4b966ce82bd815e65249a168a393d289bb9c11d2f7bc6`
- Katman (alınan işlem) sha256: `87fe782f347df616302311fc42c97bc79e1d8ac8793a4d7af78a1227ae8ae3ab`
- Tarif kimliği: `ml1-r02-long-ctx-1r` | deneme sayısı (n_trials): 10 | lightgbm sürümü: 4.6.0
- Tepe bellek: 480 MB (sunucu tavanı 1200 MB)

## Kapı adımları (sırayla; biri kalırsa model reddedilir)

| Adım | Sonuç | Değer | Kural |
|---|---|---|---|
| 1. IC kapisi (yalniz alinan islemler) | KALDI | rho=-0.0340, t=-1.22 (n=1284 gun, 3861 alinan satir), pozitif dilim 2/4 | tam 4 dilim degerlendirilmis, rho>0, t>=2.0, en az 3 dilim pozitif (gunluk toplulastirma) |
| 2. Kalibrasyon (Brier) | KALDI | model=0.25319, sabit taban=0.25049 | model Brier < sabit taban orani Brier |
| 3a. Esik bulundu | GEÇTİ | esik=0.46 | [0,45-0,70] izgarasinda alinan oran >= 30% |
| 3b. Net R farki (filtreli-filtresiz) | KALDI | fark=+0.0381 R, boot %90 alt sinir=+0.0063 | fark >= +0.1 R ve alt sinir > 0 |
| 3c. Filtreli net beklenti | KALDI | -0.0052 R (filtresiz -0.0434) | > 0 R |
| 3d. Deflated Sharpe | KALDI | DSR=0.0476 (deneme sayisi 10, 1574 gunluk gozlem) | >= 0.95 |
| 3e. PBO (CSCV) | KALDI | PBO=0.581 (9 yapilandirma, 1574 gun) | <= 0.25 |
| 3f. En buyuk dusus | GEÇTİ | filtreli=182.74 R, filtresiz=341.73 R | filtreli <= filtresiz |
| 3g. Dejenerasyon korumasi | GEÇTİ | alinan oran=63.9%; tek cift cikarilinca en kotu fark=+0.0298 R | alinan >= 30% ve her tek-cift-cikarmada fark > 0 |
| 3h. Holm (coklu karsilastirma) | KALDI | duzeltilmis p=0.1130 (2 model) | <= 0.1 |
| 4. Maliyet dayanikliligi (komisyon x2 + 5 bp/taraf) | KALDI | -0.1756 R | >= -0.05 R |
| 5. Esleme (motor okuyucusu = LightGBM) | GEÇTİ | en buyuk fark=0.000e+00 | <= 1e-09 |
| 6. Gorevdeki modele karsi | ATLANDI | atlandi (etkin model yok) | aday >= gorevdeki |

- IC (BAĞLAYICI, yalnız alınan işlemler): rho=-0.0340, n=3861 satır / 1284 gün
- IC (TANI, tüm satırlar; geçti/kaldı rolü yok): rho=-0.0072, t=-0.26, n=5922 satır / 1320 gün, pozitif dilim 2/4

**Sonuç:** İlk kalan adım: 1. IC kapisi (yalniz alinan islemler).

- 1. IC kapisi (yalniz alinan islemler): dilim rho: 0:+0.006, 1:-0.114, 2:+0.039, 3:-0.086

## Koşu öncesi korumalar (geçti/kaldı rolü yok; ham ihlal gerçek koşuyu reddeder)

- Özellik sağlığı: 40 özellik; boş=-; sabit=-; kopya=- -> TEMİZ
- Guc on hesabi (n_trials=10): DSR icin 1576 gun -> gereken t=3.22 (gunluk SR>=0.0812); IC icin 1284 gun -> t>=2.00 <=> rho>=0.056

## Koşu tablosu sayımları (tablodan atılanlar)

- Dönem sonunda AÇIK kalan alınmış işlem (çıkışı yok, atıldı): 0
- Etiketi çözülmemiş (son 72 mum) satır: 6; bunlardan ALINMIŞ olup atılan: 3
- Tablo: 7329 satır, alınan 4695, alınmayan 2634; katmanda derlemle eşleşmeyen alınmış işlem: 0

## Kalibrasyon (yalnız bilgi)

- Ağırlık şeması: `uniq_decay` | Platt eğimi a>=0 kısıtı: AÇIK
- Eğimi kısıtlanan (a<0 -> sabit p = taban oran) ileri yönlü dilim sayısı: logistic=0/4, lgbm=1/4

## Tanı satırları (yalnız bilgi; geçti/kaldı rolü yok)

- Şans kıyası (1/(1+hedef R), hedef=2.0R): 0.333; gerçekleşen etiket oranı 0.506
- AUC (tüm etiketli OOF satırları): 0.503 (gün-bloklu bootstrap %90 aralık 0.485 – 0.520; 0,5 = şans)
- İki yarı (alınan işlemler, zamana göre): 1. yarı filtreli -0.1549 / filtresiz -0.1206 R; 2. yarı filtreli 0.0406 / filtresiz 0.0338 R
- Kuyruk payı: en iyi %5 işlem (194 adet) toplam net R'nin - oranı (1,0 = hepsi); filtre bunlardan 127/194 tanesini tuttu
- Filtre en iyi 10 işlemden 1 tanesini attı (bu 10 işlemin toplamı 142.73 R)

## Test dilimleri (genişleyen pencere, 72 mum arındırma + 24 mum ambargo)

| Dilim | Eğitim satırı | Test satırı | Test başlangıcı | Test sonu |
|---|---|---|---|---|
| 0 | 1381 | 1406 | 2022-01-06 | 2023-02-04 |
| 1 | 2801 | 1598 | 2023-02-04 | 2024-03-04 |
| 2 | 4396 | 1441 | 2024-03-04 | 2025-04-02 |
| 3 | 5839 | 1477 | 2025-04-02 | 2026-05-01 |

## Model karşılaştırması (aynı kapı ölçüleri, yalnız bilgi)

| Model | Eşik | Alınan oran | Filtreli net R | Filtresiz net R | Fark | Boot alt sınır |
|---|---|---|---|---|---|---|
| p_logistic | 0.46 | 63.9% | -0.0052 | -0.0434 | 0.0381 | 0.0063 |
| p_lgbm | 0.49 | 99.1% | -0.0449 | -0.0434 | -0.0015 | -0.0058 |

## Notlar ve sınırlar

- Evren: stratejinin aldığı adaylar (`taken`); filtresiz temel = hepsi. Örtüşen pozisyonlar ve risk payı etkileşimi modellenmedi (§3.5 yaklaşıklığı).
- IC t-istatistiği ve DSR günlük (UTC) toplulaştırılmış gözlemlerle hesaplandı (aynı mum/gün adayları bağımsız sayılmaz); fark testinde ayrıca bootstrap blok uzunluğu kullanıldı.
- Platt kalibrasyonu ve eşik İLERİ YÖNLÜ uyduruldu (k. dilim için yalnız önceki dilimler; ilk dilimde özdeşlik + sabit 0,50 eşik). Paketteki Platt/eşik tüm OOF'a uydurulur ve kapıda skorlanmaz.
- Maliyet stresi: komisyon ×2 + 5 bp TARAF başına (tur başına 10 bp).
- Eşikler önceden yazılıdır ve gevşetilmez: {'ic_min_t': 2.0, 'required_folds': 4, 'ic_min_pos_folds': 3, 'delta_net_r_min': 0.1, 'bootstrap_alpha_two_sided': 0.2, 'filtered_expectancy_min': 0.0, 'dsr_min': 0.95, 'pbo_max': 0.25, 'min_taken_frac': 0.3, 'stress_expectancy_min': -0.05, 'stress_fee_mult': 2.0, 'stress_extra_bp_per_side': 5.0, 'parity_tol': 1e-09, 'holm_alpha': 0.1}.
- Kapıyı geçse bile geçmiş kapı yalnız gölgeye girişe yeter (§7 notları); paraya dokunma kararı ML-3'tedir.
