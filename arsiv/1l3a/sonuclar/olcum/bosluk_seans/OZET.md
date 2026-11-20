# Fiyat boşluğu dağılımı, %20/%25 stres ve seans kayması göstergesi

Yalnız ölçüm. Çarpan, limit, strateji, `seans_maliyet.json` değişmedi. Betik: `araclar/bosluk_olcum.py` (test: `testler/test_bosluk_olcum.py`); `araclar/kaldirac_stres.py`'ye yeni `--ek-bosluk 0.20,0.25` parametresi eklendi (geriye uyumlu). Ham sayılar: `bosluk_ham.json`, `emtia_ek_ham.json`, `ek_stres_ham.json`.

## Veri ve tanım
- Boşluk = |açılış / önceki kapanış − 1|. Yalnız geliştirme dönemi (en geç 2025-11-07; holdout okunmadı). Dönem: hisse 2017-01 → 2025-11 (17 hisse; 7'si 5m, 10'u 1h mum), emtia 2008/2012/2020 → 2025-11 (XAU, WTI 5m; XAG, COPPER, NATGAS 1h), kripto 13 sembol 5m'den 1 saatlik ve 1 günlük kapanış.
- Hisse: seans kapanışı → sonraki seans açılışı. Gece = ardışık iki işlem günü; hafta sonu = Cuma → Pazartesi; tatil = arada başka kapalı gün olan (tatil, köprü). Beklenen işlem günü veride yoksa olay atlandı (68 olay).
- Emtia: ardışık mumlar arası boşluk süresine göre. Gece = günlük mola (50 dk-2,5 sa); hafta sonu = Cuma kapanışı → Pazar açılışı; tatil = diğer ≥20 sa kapanışlar. 2,5-20 sa arası veri boşluğu sayıldı, atlandı (457 olay).
- Hisse bölünmesi (split): %40 üstü boşluk olsaydı dışlanacaktı; hiç çıkmadı, veri bölünme-düzeltmeli görünüyor (en büyükler gerçek haber/kazanç boşlukları).
- Kripto 1sa ve 1gün: mutlak kapanıştan kapanışa hareket (boşluk değil, 7/24 işlem karşılaştırması).

## 1) Boşluk dağılımı

| Grup | n | ort % | p50 % | p90 % | p99 % | maks % | sıklık % (>5/10/15/20/25) | adet (>5/10/15/20/25) |
|---|---|---|---|---|---|---|---|---|
| hisse gece | 28742 | 0.83 | 0.49 | 1.85 | 5.73 | 26.33 | 1.32 / 0.20 / 0.05 / 0.01 / 0.00 | 379 / 57 / 14 / 4 / 1 |
| hisse hafta sonu | 6629 | 0.93 | 0.53 | 2.05 | 6.84 | 37.58 | 1.76 / 0.45 / 0.05 / 0.02 / 0.02 | 117 / 30 / 3 / 1 / 1 |
| hisse tatil | 1337 | 0.86 | 0.53 | 1.94 | 4.83 | 14.86 | 0.90 / 0.07 / 0.00 / 0.00 / 0.00 | 12 / 1 / 0 / 0 / 0 |
| emtia gece | 10143 | 0.11 | 0.04 | 0.18 | 0.86 | 40.83 | 0.20 / 0.08 / 0.03 / 0.01 / 0.01 | 20 / 8 / 3 / 1 / 1 |
| emtia hafta sonu | 3443 | 0.48 | 0.12 | 1.09 | 5.80 | 35.25 | 1.45 / 0.23 / 0.12 / 0.09 / 0.03 | 50 / 8 / 4 / 3 / 1 |
| emtia tatil | 175 | 0.59 | 0.19 | 1.36 | 5.99 | 7.63 | 1.71 / 0.00 / 0.00 / 0.00 / 0.00 | 3 / 0 / 0 / 0 / 0 |
| emtia gece (NATGAS hariç) | 8312 | 0.07 | 0.04 | 0.14 | 0.57 | 3.19 | 0 / 0 / 0 / 0 / 0 | 0 / 0 / 0 / 0 / 0 |
| emtia hafta sonu (NATGAS hariç) | 2784 | 0.23 | 0.09 | 0.46 | 1.90 | 35.25 | 0.25 / 0.07 / 0.07 / 0.07 / 0.04 | 7 / 2 / 2 / 2 / 1 |
| emtia tatil (NATGAS hariç) | 136 | 0.30 | 0.14 | 0.72 | 1.87 | 3.56 | 0 / 0 / 0 / 0 / 0 | 0 / 0 / 0 / 0 / 0 |
| kripto 1 saatlik hareket | 750929 | 0.66 | 0.40 | 1.49 | 4.13 | 67.95 | 0.58 / 0.07 / 0.02 / 0.01 / 0.00 | 4388 / 540 / 147 / 50 / 23 |
| kripto 1 günlük hareket | 31304 | 3.42 | 2.21 | 7.69 | 18.48 | 389.81 | 20.99 / 5.45 / 1.87 / 0.76 / 0.41 | 6572 / 1705 / 584 / 238 / 129 |

Not: "NATGAS hariç" satırları ayrıca verildi; DK_NATGAS'ın (1h veri) gece boşluğu maks %40,8, diğer 4 emtiada gece boşluğunun maksimumu %3,2. NATGAS'ın büyük boşlukları vadeli kontrat devri (roll) kalıntısı olabilir; veriden ayırt edilemedi. WTI 2020-04-19 (−%35, Nisan 2020 negatif fiyat dönemi) gerçek piyasa olayı gibi görünüyor.

### En kötü 5 olay (sembol, tarih, boşluk)
- hisse gece: NVDA 2023-05-25 %26,3; META 2022-10-27 %24,5; META 2022-02-03 %24,2; AMD 2018-10-25 %21,3; META 2023-02-02 %19,8
- hisse hafta sonu: AMD 2025-10-06 %37,6; JPM 2020-03-16 %17,4; TSLA 2018-10-01 %15,5; V 2020-03-16 %14,8; NVDA 2019-01-28 %14,7
- hisse tatil: TSLA 2020-09-08 %14,9; TSLA 2019-01-02 %8,1; TSLA 2025-07-07 %7,8; WMT 2018-02-20 %7,5; TSLA 2021-04-05 %7,1
- emtia gece: NATGAS 2020-09-22 %40,8; NATGAS 2024-10-24 %18,2; NATGAS 2024-04-23 %15,8; NATGAS 2024-01-24 %14,6; NATGAS 2023-10-24 %11,7
- emtia hafta sonu: WTI 2020-04-19 %35,3; NATGAS 2025-10-26 %22,2; WTI 2020-03-08 %21,2; NATGAS 2025-01-26 %17,6; NATGAS 2025-05-25 %14,8
- emtia tatil: NATGAS 2020-12-27 %7,6; NATGAS 2017-01-03 %6,6; NATGAS 2021-12-26 %5,8; NATGAS 2024-01-01 %4,6; NATGAS 2022-12-26 %3,6
- kripto 1 saatlik: DOGE 2021-01-29 03:00 %67,9; XLM 2021-05-19 13:00 %57,3; LINK 2019-06-13 17:00 %54,3; XLM 2021-05-19 12:00 %48,8; DOGE 2021-01-28 04:00 %48,6
- kripto 1 günlük: DOGE 2021-01-28 %389,8; DOGE 2021-04-16 %101,2; TRX 2024-12-03 %95,8; DOGE 2021-01-02 %85,6; XLM 2021-01-06 %77,5

## 2) Mevcut stres testine %20 / %25 satırları
Aynı varsayımlar (kaldirac_stres): tüm pozisyonlar aynı anda g kadar ters; kayıp = brüt × g; en kötü hesapta ve 10 hesap birleşikte (üst sınır). Backtest yeniden koşulmadı; tepe brüt değerleri mevcut `ham_sayilar.json`'dan alındı (hesaplar ve brütler aynı). Likidasyon: izole marj, bakım marjı %0,5; tek pozisyon likide olur boşluk ≥ 1/K − %0,5.

| Profil | K | Boşluk %20 / %25: en kötü hesap kaybı (% kasa) | 10 hesap birleşik kayıp (%) | Tek pozisyon likidasyon eşiği | Tek pozisyon likide? (%20 / %25) |
|---|---|---|---|---|---|
| paper | 3x | 22,4 / 28,0 | 6,3 / 7,8 | %32,8 | hayır / hayır |
| paper | 4x | 22,4 / 28,0 | 6,3 / 7,8 | %24,5 | hayır / EVET |
| paper | 5x | 22,4 / 28,0 | 6,3 / 7,8 | %19,5 | EVET / EVET |
| canlı %1,5 | 3x | 38,6 / 48,3 | 11,4 / 14,3 | %32,8 | hayır / hayır |
| canlı %1,5 | 4x | 38,6 / 48,3 | 11,4 / 14,3 | %24,5 | hayır / EVET |
| canlı %1,5 | 5x | 38,6 / 48,3 | 11,4 / 14,3 | %19,5 | EVET / EVET |

- Hesap kaybı K'ya bağlı değil, brütten geliyor (paper brüt 1,12; canlı-benzeri 1,93; 10 hesap birleşik 0,31 / 0,57).
- Hesap (çapraz marj) bazında likidasyon eşiği: paper en kötü hesap %88,9, canlı %51,3; ikisi de %25'te aşılmıyor.
- Karşılaştırma: günlük limit %5, hesap kill %20, strateji kill %30. Canlı-benzeri en kötü hesapta %20 boşluk −38,6 (strateji kill %30'u aşar); 10 hesap birleşik −11,4 / −14,3 (hesap kill %20'ye ulaşmaz). Canlı %3 duyarlılık profili bu eklemede yeniden hesaplanmadı (ham dosyası ayrı klasörde).
- Marj kaybı: 5x'te %20 boşluk tek pozisyonun marjının tamamını (%100) siler, 4x'te %25'te %100.

## 3) Seans kayması için dolaylı gösterge
Gerçek makas (spread) ve dolum kayması verisi YOK: elde yalnız OHLC mumları var. Mum aralığı (yüksek−düşük)/kapanış makasın kendisi değil, oynaklık + makasın karışımıdır; sonuçlar 2x/3x çarpanlarını ne doğrular ne çürütür.

Seans dilimine göre ortalama 5m mum aralığı (7 hisse + XAU + WTI 5m verisi; 10 hisse ve 3 emtia yalnız 1h verili olduğu için dışarıda):

| Sınıf | normal | genişletilmiş | kapalı |
|---|---|---|---|
| hisse | %0,271 (n=1,2 M) | %0,026 (n=1066) | %0,219 (n=2737) |
| emtia | %0,106 (n=1,68 M) | tanımsız | %0,043 (n=18786) |
| kripto (karşılaştırma) | %0,381 | yok | yok |

- Hisse verisi yalnız normal seansı içeriyor (09:30-16:00 NY); genişletilmiş/kapalı dilimde çok az bar var ve bunlar seans kenarındaki durağan mumlar (aralık ~0). Bu dilimler için kanıt yok.
- Emtia kapalı dilimde mum aralığı normalden DÜŞÜK (%0,043 vs %0,106): kaynak kapalıyken ince/bayat teklif üretiyor. Mum aralığı kapalı seansta genişleme göstermiyor; bu, kaynağın makası hakkında bilgi vermez.
- NY saatine göre ortalama mum aralığı: emtia Asya gecesi %0,076, Avrupa %0,109, ABD günü %0,143, ABD açılış ilk 15 dk %0,209; hisse ilk 15 dk %0,676, gün ortası %0,228, son 30 dk %0,254; kripto 7/24 %0,36-0,42. İnce saatlerde oynaklık düşük; makas bu veriyle ölçülemiyor.
- Sonuç: 2x/3x çarpanlar için ölçüme dayalı destek de itiraz da yok. Ölçüm için canlı dolum kayıtları veya teklif/emir defteri (bid-ask) verisi gerekir.

## 4) Mevcut varsayımlara kıyasla gördüğümüz (ölçüm, öneri değil)
- Hisse: gece/hafta sonu boşluğunun >%5 sıklığı %1,3-1,8, >%10 %0,2-0,45, >%15 %0,05; >%20 toplam 5 olay (4 gece + 1 hafta sonu; 36 708 olay içinde), >%25 2 olay (NVDA 2023-05-25 %26,3 ve AMD 2025-10-06 %37,6). Aynı anda birçok hissede olan en kötü gün 2020-03-16 (JPM %17,4, V %14,8).
- Emtia: NATGAS hariç gece boşluğu hiç %5'i geçmedi (maks %3,2); hafta sonu p99 %1,9, ama WTI'da 2 olay >%20 (Mart-Nisan 2020). NATGAS ayrı ve çok daha kaba (kontrat devri olasılığı).
- Kripto: tek günlük hareket >%20 olan olay 238/31 304 (%0,76), >%25 129 (%0,41); en kötü 1 saatlik %68 (DOGE 2021).
- Mevcut %5/10/15 stresiyle kıyas: %15'i aşan boşluk tüm tarihte hissede 17 olay (14 gece + 3 hafta sonu), emtiada 7 olay (3 gece + 4 hafta sonu; çoğu NATGAS); %20'yi aşan 5 hisse + 4 emtia olayı. Stres "tüm pozisyonlar aynı anda ters" varsayar; burada olaylar tek sembol bazında sayıldı, aynı gün birden çok sembolün birlikte boşluk yapması (korelasyon) ayrıca ölçülmedi.
- %20/%25 sonucu: canlı-benzeri profilde en kötü hesap −38,6 / −48,3 (strateji kill −%30 aşılır), 10 hesap birleşik −11,4 / −14,3. 5x'te %20, 4x'te %25 boşluk tek pozisyonu likide eder; 3x'te ikisinde de likidasyon yok.
- Seans kayması çarpanları (2x/3x): ölçülen bir makas verisi olmadığı için sınanamadı.

## Varsayımlar ve sınırlar
- Veri Dukascopy kaynaklı CFD/spot kopyaları; Binance TradFi perp'in kendi boşlukları ve makası bundan farklı olabilir.
- Emtia sınıflandırması mum zaman aralıklarından türetildi (takvimden değil). 1h verili semboller için açılış/kapanış 1 saatlik mumun açılış/kapanış fiyatı.
- Hisse tatil = arada beklenen işlem günü olmayan her durum (köprü hafta sonu dahil). Veri boşluğu olayları atlandı (68 hisse, 457 emtia).
- Kripto hareketleri UTC saat/gün kapanışlarından.
- %20/%25 stres, mevcut mühürlü tepe brütlerden aynı formülle hesaplandı.
- Tüm semboller sınıf içinde birleştirildi; sembol başı emtia özeti `emtia_ek_ham.json`'da.
