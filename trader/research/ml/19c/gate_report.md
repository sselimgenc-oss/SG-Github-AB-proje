# ML terfi kapısı raporu — RED

## Özet

- Seçilen model: **logistic** (LightGBM lojistigi net R'de gecemedi (- <= -0.9508))
- Eşik (dondurulmuş, eğitim dışı dilimlerde seçildi): bulunamadı
- Tarif: `ml1-r01-v1b-native33` | model türü: logistic | eğitim örneği: 1261
- Eğitim penceresi: 2024-12-21T09:00:00+00:00 → 2026-04-29T16:00:00+00:00
- Kilitli dönem (2026-05 → 2026-10) okunmadı (kod korumalı).
- Model oluşturma: 2026-11-17T09:17:24.541728+00:00 | son kullanma: 2026-12-08T09:17:24.541728+00:00 (21 gün)
- Veri özeti: `ad0ac841dc02213d…` | kod özeti: `b3485254cf992732…` | model özeti: `b4826bde82caaa28…`
- Özellik listesi özeti: `fc17d0ed80f424bf…` (33 özellik)
- Korpus sha256 (aday dosyası): `a0fd15a8440fd0cf03ab24dc8afdaab0627791b5992ba8a018a2fe251737bd6e`
- Tarif kimliği: `ml1-r01-v1b-native33` | deneme sayısı (n_trials): 4 | lightgbm sürümü: 4.6.0
- Tepe bellek: 213 MB (sunucu tavanı 450 MB)

## Kapı adımları (sırayla; biri kalırsa model reddedilir)

| Adım | Sonuç | Değer | Kural |
|---|---|---|---|
| 1. IC kapisi (yalniz alinan islemler) | KALDI | rho=0.0014, t=0.02 (n=197 gun, 624 alinan satir), pozitif dilim 3/4 | tam 4 dilim degerlendirilmis, rho>0, t>=2.0, en az 3 dilim pozitif (gunluk toplulastirma) |
| 2. Kalibrasyon (Brier) | KALDI | model=0.24273, sabit taban=0.23863 | model Brier < sabit taban orani Brier |
| 3a. Esik bulundu | KALDI | yok (rapor esigi=0.381) | [0,45-0,70] izgarasinda alinan oran >= 30% |
| 3b. Net R farki (filtreli-filtresiz) | KALDI | fark=-1.0742 R, boot %90 alt sinir=-1.1735 | fark >= +0.1 R ve alt sinir > 0 |
| 3c. Filtreli net beklenti | KALDI | -0.9508 R (filtresiz +0.1234) | > 0 R |
| 3d. Deflated Sharpe | KALDI | DSR=0.0000 (deneme sayisi 4, 240 gunluk gozlem) | >= 0.95 |
| 3e. PBO (CSCV) | KALDI | PBO=0.323 (3 yapilandirma, 240 gun) | <= 0.25 |
| 3f. En buyuk dusus | GEÇTİ | filtreli=0.95 R, filtresiz=26.28 R | filtreli <= filtresiz |
| 3g. Dejenerasyon korumasi | KALDI | alinan oran=0.2%; tek cift cikarilinca en kotu fark=-1.1233 R | alinan >= 30% ve her tek-cift-cikarmada fark > 0 |
| 3h. Holm (coklu karsilastirma) | KALDI | duzeltilmis p=1.0000 (2 model) | <= 0.1 |
| 4. Maliyet dayanikliligi (komisyon x2 + 5 bp/taraf) | KALDI | -1.3631 R | >= -0.05 R |
| 5. Esleme (motor okuyucusu = LightGBM) | GEÇTİ | en buyuk fark=0.000e+00 | <= 1e-09 |
| 6. Gorevdeki modele karsi | ATLANDI | atlandi (etkin model yok) | aday >= gorevdeki |

- IC (BAĞLAYICI, yalnız alınan işlemler): rho=0.0014, n=624 satır / 197 gün
- IC (TANI, tüm satırlar; geçti/kaldı rolü yok): rho=-0.0077, t=-0.11, n=641 satır / 198 gün, pozitif dilim 1/4

**Sonuç:** İlk kalan adım: 1. IC kapisi (yalniz alinan islemler).

- 1. IC kapisi (yalniz alinan islemler): dilim rho: 0:-0.102, 1:+0.079, 2:+0.050, 3:+0.007

## Test dilimleri (genişleyen pencere, 72 mum arındırma + 24 mum ambargo)

| Dilim | Eğitim satırı | Test satırı | Test başlangıcı | Test sonu |
|---|---|---|---|---|
| 0 | 571 | 154 | 2025-08-22 | 2025-10-21 |
| 1 | 731 | 173 | 2025-10-21 | 2025-12-20 |
| 2 | 903 | 163 | 2025-12-20 | 2026-02-18 |
| 3 | 1069 | 151 | 2026-02-18 | 2026-04-19 |

## Model karşılaştırması (aynı kapı ölçüleri, yalnız bilgi)

| Model | Eşik | Alınan oran | Filtreli net R | Filtresiz net R | Fark | Boot alt sınır |
|---|---|---|---|---|---|---|
| p_logistic | yok (rapor 0.381) | 0.2% | -0.9508 | 0.1234 | -1.0742 | -1.1735 |
| p_lgbm | yok (rapor 0.379) | 0.0% | - | 0.1234 | - | - |

## Notlar ve sınırlar

- Evren: stratejinin aldığı adaylar (`taken`); filtresiz temel = hepsi. Örtüşen pozisyonlar ve risk payı etkileşimi modellenmedi (§3.5 yaklaşıklığı).
- IC t-istatistiği ve DSR günlük (UTC) toplulaştırılmış gözlemlerle hesaplandı (aynı mum/gün adayları bağımsız sayılmaz); fark testinde ayrıca bootstrap blok uzunluğu kullanıldı.
- Platt kalibrasyonu ve eşik İLERİ YÖNLÜ uyduruldu (k. dilim için yalnız önceki dilimler; ilk dilimde özdeşlik + sabit 0,50 eşik). Paketteki Platt/eşik tüm OOF'a uydurulur ve kapıda skorlanmaz.
- Maliyet stresi: komisyon ×2 + 5 bp TARAF başına (tur başına 10 bp).
- Eşikler önceden yazılıdır ve gevşetilmez: {'ic_min_t': 2.0, 'required_folds': 4, 'ic_min_pos_folds': 3, 'delta_net_r_min': 0.1, 'bootstrap_alpha_two_sided': 0.2, 'filtered_expectancy_min': 0.0, 'dsr_min': 0.95, 'pbo_max': 0.25, 'min_taken_frac': 0.3, 'stress_expectancy_min': -0.05, 'stress_fee_mult': 2.0, 'stress_extra_bp_per_side': 5.0, 'parity_tol': 1e-09, 'holm_alpha': 0.1}.
- Kapıyı geçse bile geçmiş kapı yalnız gölgeye girişe yeter (§7 notları); paraya dokunma kararı ML-3'tedir.
