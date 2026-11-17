# ML 19c kapı raporu — tek gerçek koşu (17 Kasım 2026)

**Karar: KIRMIZI (RED).** ML `off`'ta kalır; kâğıt etkilenmez. Tek koşu yapıldı, yeniden koşu/ayar yok; `trader_ml`, eşik, ızgara, özellik değişmedi.
Ham çıktılar: `research/ml/19c/gate_result.json`, `research/ml/19c/gate_report.md` (boru hattının kendi raporu), `oof_predictions.parquet`, `model_candidate.json`.

## 1. Kimlik

| Alan | Değer |
|---|---|
| Korpus sha256 (`candidates_v1b_native.parquet`) | `a0fd15a8440fd0cf03ab24dc8afdaab0627791b5992ba8a018a2fe251737bd6e` (manifestteki ile birebir, koşudan ÖNCE doğrulandı) |
| Manifest damgası | git_commit_start `224eca3e86d0`, ağaç temiz; rules_source `synthetic-preholdout` (istisna kayıtlı: min_notional BTC 100 / ETH 20 / diğerleri 5); target_trade_risk 0,005 (kâğıt riski); engine 05.1, strateji price_action_v1@1b.0 |
| Tarif kimliği | `ml1-r01-v1b-native33` (33 özellik) |
| n_trials | 4 (2 tarif x 2 model; defter: ml0c-baseline-v1 + ml1-r01-v1b-native33) |
| lightgbm | 4.6.0 (gerçek mod, `--research`) |
| Satır sayıları | aday 1261 (alınan 1234, atlanan 27); OOF 641 (alınan 624) |
| Tepe bellek | 213 MB |

## 2. Test dilimleri (genişleyen pencere; arındırma 72 mum, ambargo 24 mum)

| Dilim | Eğitim | Test | Test başı | Test sonu |
|---|---|---|---|---|
| 0 | 571 | 154 | 2025-08-22 | 2025-10-21 |
| 1 | 731 | 173 | 2025-10-21 | 2025-12-20 |
| 2 | 903 | 163 | 2025-12-20 | 2026-02-18 |
| 3 | 1069 | 151 | 2026-02-18 | 2026-04-19 |

## 3. §3.4 kontrolleri (sırayla; seçilen model: lojistik)

| Adım | Değer | Dondurulmuş eşik | Sonuç |
|---|---|---|---|
| 1. IC (yalnız alınanlar, bağlayıcı) | rho=0,0014, t=0,02, 197 gün, 624 satır, pozitif dilim 3/4 | 4 dilim, rho>0, t>=2,0, >=3 pozitif dilim | KALDI (**ilk kalan**) |
| 2. Kalibrasyon (Brier) | model 0,24273 / sabit taban 0,23863 | model < taban | KALDI |
| 3a. Eşik bulundu | yok (rapor eşiği 0,381) | ızgara [0,45-0,70], alınan oran >=%30 | KALDI |
| 3b. Net R farkı | -1,0742 R; bootstrap %90 alt sınır -1,1735 | >= +0,10 R ve alt sınır > 0 | KALDI |
| 3c. Filtreli net beklenti | -0,9508 R (filtresiz +0,1234) | > 0 | KALDI |
| 3d. Deflated Sharpe | 0,0000 (n_trials 4, 240 gün) | >= 0,95 | KALDI |
| 3e. PBO (CSCV) | 0,323 (3 yapılandırma, 240 gün) | <= 0,25 | KALDI |
| 3f. En büyük düşüş | filtreli 0,95 R / filtresiz 26,28 R | filtreli <= filtresiz | GEÇTİ |
| 3g. Dejenerasyon | alınan oran %0,2; tek-çift-çıkarma en kötü fark -1,1233 R | >=%30 ve her çıkarmada fark > 0 | KALDI |
| 3h. Holm | düzeltilmiş p=1,0000 (2 model) | <= 0,1 | KALDI |
| 4. Maliyet stresi (komisyon x2 + 5 bp/taraf) | -1,3631 R | >= -0,05 R | KALDI |
| 5. Eşleme (motor okuyucusu = LightGBM) | en büyük fark 0 | <= 1e-9 | GEÇTİ |
| 6. Görevdeki modele karşı | etkin model yok | - | ATLANDI |

İlk başarısız adım: **1. IC kapısı (yalnız alınan işlemler)**. Not: ilk eşik adımları (3a) da kalıyor; eşik bulunamadı çünkü hiçbir eşikte alınan oran %30'a ulaşmıyor.

## 4. IC

| Evren | rho | t | gün | satır | Dilim bazında rho (0/1/2/3) | Pozitif dilim |
|---|---|---|---|---|---|---|
| Yalnız alınanlar (BAĞLAYICI) | 0,0014 | 0,02 | 197 | 624 | -0,102 / +0,079 / +0,050 / +0,007 | 3/4 |
| Tüm satırlar (TANI, geçti/kaldı rolü yok) | -0,0077 | -0,11 | 198 | 641 | -0,100 / +0,062 / -0,014 / -0,012 | 1/4 |

Bağlayıcı IC pozitif dilim sayısını (3/4) sağlıyor ama t=0,02 ile anlamlılıktan çok uzak; sinyal yok.

## 5. Modeller ve seçim nedeni

| Model | Eşik | Alınan oran | Filtreli net R | Filtresiz net R | Fark | Boot alt sınır |
|---|---|---|---|---|---|---|
| lojistik | yok (rapor 0,381) | %0,2 | -0,9508 | 0,1234 | -1,0742 | -1,1735 |
| LightGBM | yok (rapor 0,379) | %0,0 | - (hiç işlem alınmadı) | 0,1234 | - | - |

Seçim nedeni (boru hattı): lojistik seçildi; "LightGBM lojistiği net R'de geçemedi (filtreli beklenti <= -0,9508)". Seçim, rapor edilen ölçülerle zaten başarısız iki modelden daha az kötü olanı seçmektir; geçer anlamına gelmez.

## 6. İleri yönlü eşikler ve alınan oran (OOF'tan, betimleyici)

İleri yönlü eşik: k. dilim için yalnız önceki dilimlerde seçilir; ilk dilimde sabit 0,50. Önceki dilimlerde alınan oran >=%30 sağlayan eşik bulunamadığı için dilim 1-3'te eşik yok (NaN) ve filtre hiçbir adayı geçirmiyor.

| Dilim | Eşik (lojistik) | Alınan oran, tüm satır (lojistik) | Alınan oran, alınan işlemler | Eşik (LightGBM) | Alınan oran (LightGBM) |
|---|---|---|---|---|---|
| 0 | 0,50 (sabit) | %0,65 (1/154) | %0,65 | 0,50 (sabit) | %0 |
| 1 | yok | %0 | %0 | yok | %0 |
| 2 | yok | %0 | %0 | yok | %0 |
| 3 | yok | %0 | %0 | yok | %0 |

Toplam: lojistik 1 alınan işlem tutuyor (%0,16), LightGBM 0. Filtre fiilen "hiçbir şey alma"ya dejenere oldu; bu nedenle 3b/3c'deki -1,07 R fark tek işlemin sonucudur ve bilgilendirici değildir. Asıl bulgu: model olasılıkları hiçbir ileri eşikte %30 alınan oranını kurtaran bir ayrım üretmiyor.

## 7. Net R, DSR, PBO, düşüş, tek-çift-çıkarma, stres, eşleme

- Net R farkı (filtreli - filtresiz): -1,0742 R; bootstrap %90 alt sınır -1,1735 (eşik >= +0,10 ve > 0).
- Filtreli beklenti -0,9508 R; filtresiz +0,1234 R (alınan 624 işlem ortalaması).
- DSR 0,0000 (>=0,95); PBO 0,323 (<=0,25).
- En büyük düşüş: filtreli 0,95 R, filtresiz 26,28 R (geçti, ancak neredeyse hiç işlem alınmadığı için anlamsız).
- Tek-çift-çıkarma: en kötü fark -1,1233 R (her çıkarmada fark > 0 gerekir); alınan oran %0,2 < %30.
- Stres kolu: -1,3631 R (>= -0,05).
- Eşleme: motor okuyucusu ile LightGBM arasında en büyük fark 0 (geçti).
- Holm: p=1,0000.

## 8. Çift bazında döküm (alınan işlemler, OOF; ortalama gerçek net R ve lojistik filtresinden geçen)

| Çift | Alınan (OOF) | Ortalama net R | Filtreden geçen |
|---|---|---|---|
| ADA | 70 | +0,102 | 0 |
| AVAX | 58 | +0,417 | 0 |
| BNB | 70 | +0,554 | 0 |
| BTC | 56 | +0,063 | 0 |
| DOGE | 52 | -0,007 | 0 |
| ETH | 56 | +0,199 | 1 |
| LINK | 73 | -0,003 | 0 |
| SOL | 51 | -0,245 | 0 |
| TRX | 71 | -0,260 | 0 |
| XRP | 67 | +0,354 | 0 |

Toplam 624 alınan işlem, ortalama net R +0,1234; etiket pozitif oranı %38,0. Korpusun tamamında (1234 alınan) ortalama net R +0,0762.

## 9. Kilitli dönem

**Kilitli dönem (2026-05-01 → 2026-11-01) okunmadı.** Korpus en geç 2026-04-29 16:00 UTC adaylarını içerir; manifest `holdout_read=false`; boru hattı kodu korumalıdır.

## 10. Karar

**KIRMIZI — ML terfi kapısını geçemedi; ilk kalan adım: 1. IC kapısı (yalnız alınan işlemler; rho=0,0014, t=0,02). ML `off`'ta kalır.**
