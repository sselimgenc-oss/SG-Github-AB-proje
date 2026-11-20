# Risk senaryosu raporu: aynı işlemler, farklı pozisyon büyüklüğü

Dönem: 2020-01-01 -> 2025-11-07 (yalnız geliştirme dönemi; kilitli yıl açılmadı). 20 paper hesabı, her biri 10.000 ile başlar.
Plan (sonuçtan önce yazıldı): `sonuclar/risk_senaryo/PLAN.md`. Kod: `araclar/risk_senaryo_kos.py` (işlemleri üretir), `araclar/risk_senaryo.py` (yeniden oynatır), test: `testler/test_risk_senaryo.py`.
Ham sonuç tabloları: `ozet.csv`, `yillik.csv`, `portfoy.csv`, `portfoy_yillik.csv`; işlem listeleri: `islemler/`.

## 1. Ne yaptık (sade)
Her stratejinin geçmişteki işlemlerini bir kere çıkardık (giriş/çıkış zamanı, sembol, net R, stop mesafesi). Sonra AYNI işlemleri farklı büyüklükle yeniden oynattık. İşlem seçimi değişmedi, yalnız "her işlemde kasanın ne kadarını riske atıyoruz" değişti:

- **Baz 0,5%**: şu anki paper ayarı.
- **A 1,5%**: şu anki üst sınır (canlı limit).
- **B 3%**, **C 5%**: daha cesur.
- **D tam kasa**: her işlemde pozisyon büyüklüğü = hesabın tamamı, çıkış yalnız stratejinin kendi stop/çıkışında. Aynı anda 3 işlem açıksa 3 kat kaldıraç demek.

R = işlemin kazancının stop mesafesine oranı (komisyon, kayma, funding dahil). Sabit risk f ile kazanç = f x kasa x R. Tam kasada kazanç = kasa x R x (stop mesafesi / giriş fiyatı), yani saf fiyat hareketi yüzdesi.

**Kill kuralı** (planda sabit): hesap zirvesinden %30 düşünce yeni işlem açmaz, bir daha da açmaz (yeniden başlatma yok). Kill anında açık olan işlemler kendi çıkışına kadar sürer ("kill=açık"). Kill'siz hali de verildi, bir de "kill=donuk" duyarlılık: kill anında kasa dondurulur, açık işlemlerin sonradan getirdiği kâr/zarar sayılmaz.

## 2. Ana sonuç (maliyet x1, kill=açık)

| Senaryo | Medyan CAGR | Medyan maks. düşüş | Kill (hesap) | ≥%4/ay (hesap) | ≥%4/ay olanların medyan DD | Portföy CAGR | Portföy maks. DD | Portföy aylık ort. |
|---|---|---|---|---|---|---|---|---|
| baz_0.5% | 11.0% | -12.1% | 1/20 | 1 | -29.3% | 23.5% | -12.2% | 1.9% |
| A_1.5% | 15.5% | -28.6% | 11/20 | 2 | -32.8% | 31.0% | -14.4% | 2.4% |
| B_3% | 15.3% | -31.3% | 18/20 | 3 | -29.2% | 30.8% | -17.1% | 2.5% |
| C_5% | 16.5% | -31.7% | 18/20 | 8 | -31.9% | 58.8% | -18.7% | 4.8% |
| D_tamkasa | 11.7% | -42.2% | 19/19 | 7 | -40.6% | 28.5% | -34.9% | 2.8% |

Okuma notları:
- "≥%4/ay" = aylık getirinin aritmetik ortalaması en az %4 (71 ay). Aritmetik ortalama, nadir büyük aylardan şişer; medyan aya bakmak daha dürüst (tablolar aşağıda: çoğu hesapta medyan ay ~%0).
- Kill'li sütunlarda hesaplar çoğu zaman 2020-2021'de dururlar ve ömür boyu düz kalır. Bu yüzden CAGR ve "zararlı ay %" düşük riskli senaryolara göre bozulur/seyreltilir. Yani B, C, D'de sonuç neredeyse tamamen 2020-2021 boğa yolunun şansına bağlı.
- Kill'e rağmen maks. düşüş %30'u aşabiliyor: kill yalnız gerçekleşmiş kasadan bakıyor ve açık işlemler sürüyor; D'de bir işlem hesabı sıfırlayabiliyor.

## 3. Kill'siz (hiç durmayan hesap) ve duyarlılık

| Senaryo | Medyan CAGR | Medyan maks. düşüş | Kill (hesap) | ≥%4/ay (hesap) | ≥%4/ay olanların medyan DD | Portföy CAGR | Portföy maks. DD | Portföy aylık ort. |
|---|---|---|---|---|---|---|---|---|
| baz_0.5% | 11.0% | -12.1% | 0/20 | 1 | -29.3% | 24.7% | -11.0% | 2.0% |
| A_1.5% | 28.7% | -35.4% | 0/20 | 5 | -50.3% | 86.8% | -47.4% | 7.5% |
| B_3% | 47.8% | -61.7% | 0/20 | 12 | -66.3% | 136% | -77.0% | 12.8% |
| C_5% | 64.8% | -82.8% | 0/20 | 15 | -86.1% | 155% | -90.0% | 14.4% |
| D_tamkasa | -9.3% | -100% | 0/19 | 18 | -100% | 1034% | -41.2% | 41.1% |

Kill=donuk (x1) — plandan SONRA eklenen duyarlılık analizi (ön kayıtlı değil):

| Senaryo | Medyan CAGR | Medyan maks. düşüş | Kill (hesap) | ≥%4/ay (hesap) | ≥%4/ay olanların medyan DD | Portföy CAGR | Portföy maks. DD | Portföy aylık ort. |
|---|---|---|---|---|---|---|---|---|
| baz_0.5% | 11.0% | -12.1% | 1/20 | 1 | -29.3% | 23.5% | -12.3% | 1.9% |
| A_1.5% | 14.6% | -28.3% | 11/20 | 1 | -31.1% | 26.5% | -16.8% | 2.1% |
| B_3% | 12.8% | -30.2% | 18/20 | 2 | -26.9% | 29.0% | -17.6% | 2.4% |
| C_5% | 11.7% | -31.2% | 18/20 | 6 | -29.4% | 55.6% | -19.6% | 4.7% |
| D_tamkasa | 9.4% | -32.3% | 19/19 | 5 | -37.1% | 33.8% | -16.6% | 3.0% |

Maliyet x2 (stres), kill=açık:

| Senaryo | Medyan CAGR | Medyan maks. düşüş | Kill (hesap) | ≥%4/ay (hesap) | ≥%4/ay olanların medyan DD | Portföy CAGR | Portföy maks. DD | Portföy aylık ort. |
|---|---|---|---|---|---|---|---|---|
| baz_0.5% | 9.3% | -13.5% | 2/20 | 0 | - | 13.6% | -8.7% | 1.1% |
| A_1.5% | 13.5% | -29.5% | 11/20 | 2 | -34.4% | 27.8% | -16.0% | 2.2% |
| B_3% | 14.3% | -32.0% | 18/20 | 3 | -28.2% | 28.2% | -15.8% | 2.3% |
| C_5% | 15.4% | -31.5% | 19/20 | 6 | -31.6% | 54.0% | -19.1% | 4.5% |
| D_tamkasa | 11.5% | -43.1% | 19/19 | 7 | -43.1% | 23.4% | -35.6% | 2.4% |

## 4. Ne anlama geliyor
1. **Risk büyüyünce ortalama getiri büyür ama düşüş daha hızlı büyür.** Kill'siz: medyan CAGR %11 (0,5%) -> %29 (1,5%) -> %48 (3%) -> %65 (5%); medyan maks. düşüş %12 -> %35 -> %62 -> %83. %5'te tipik hesap kasanın beşte dördünü bir noktada kaybediyor.
2. **%4/ay hedefi**: kill'siz %1,5 ile 20 stratejiden 5'i, %3 ile 12'si, %5 ile 15'i aylık ortalamada %4'ü geçiyor, ama o hesapların medyan maks. düşüşü sırasıyla %50, %66, %86. Kill'li yolda (gerçekçi kural) %1,5'te 2, %3'te 3, %5'te 8 hesap geçiyor ve onların da çoğu kill'e yakalanmış (yani hedefe 2020-21'de ulaşıp durmuşlar). Kill'siz sütun "kuralsız bahis" yorumu: düşüşler kabul edilemez.
3. **Tam kasa (D)** hesapların çoğunu yok ediyor: kill'siz 19 hesabın 14'ü %99+ düşüş (fiilen sıfır), medyan CAGR negatif. İstisnalar (ör. kap_HAM_B001_670: stop %35 uzaklıkta, işlemler küçük) çok şanslı yollar; tek tek strateji tablosuna bakın. D'nin aylık ortalamaları (kill'siz %26 gibi) bileşik büyümenin tuhaf sonuçlarıdır, anlamlı değil. Azami eşzamanlı kaldıraç D'de 3x ile 18x arası (kill'siz bazılarında daha da yüksek).
4. **Mevcut %1,5 bile sert limitin (3x) üstünde kaldıraç ister**: bu yeniden oynatma 3x tavanını simüle etmez. A senaryosunda gauss-stoch-eth 8,8x, jt-awesome 5,2x, voltarget 5,1x, kap_X005_301 3,3x azami eşzamanlı kaldıraç gösteriyor (1d, çok sembol aynı anda sinyal veriyor). Canlıda 3x limit bu işlemleri kısar/engeller; yani A sütunu gerçek canlı sistemin alabileceğinden farklıdır (bkz. 4c; limitli sistem işlemlerin yaklaşık yarısını reddeder).
5. **Portföy (20 hesap toplamı)**: kill'siz %0,5 -> %1,5 geçişinde portföy maks. düşüşü %11'den %47'ye, CAGR %25'ten %87'ye çıkıyor. Portföy sonuçları 2020-21 boğası ve 2024 yükselişi ile belirlenir. Yüksek risk kötü yıllarda daha çok kaybettirir: 2022'de kill'siz portföy %0,5'te -%5,8, %1,5'te -%22, %3'te -%47, %5'te -%69. 2025'te (veri 11-07'ye kadar, açık pozisyonlar hariç, bkz. 4b) gerçekleşmiş sonuç kill'siz %0,5'te -%0,9, %1,5'te -%18, %3'te -%40, %5'te -%43; ama 2025 rakamı açıkta kalan kârları saymadığı için aşağı yönlü yanlıdır (zorunlu kapanışlar dahil edilince tablo çok değişir).
6. **Sonuç kanıt değildir.** Stratejiler sonradan seçilmiş, dönem boğa ağırlıklı, her kasada tek yol var. Yalnız boyutlandırma etkisinin yönünü gösterir.

## 4b. Veri sonunda zorunlu kapanan işlemler (düzeltme)
Veri 2025-11-07'de bitiyor; o anda açık olan işlemler motor tarafından 2025-11-08 00:00'da zorla kapatılmış görünüyor. Bunlar gerçek çıkış değil, gerçekleşmemiş kâr/zarar. İlk sürümde bu işlemler seçiliyor ve kaldıraç/sayımda görünüyor, ama kârı günlük seriye girmiyordu (tutarsızdı). Düzeltme: **bu işlemler her yerden hariç tutuldu** (kâr, kaldıraç, sayım). Ana tablolardaki kâr/CAGR/düşüş rakamları bu yüzden değişmedi (kâr zaten girmiyordu); yalnız kaldıraç değerleri biraz değişti.
- Hariç tutulan: 86 işlem, 17 stratejide, toplam 608 R (x1 net R; ayrıntı `zorunlu_kapanis.csv`). Büyük kısmı iki yerden gelir: `kap_HAM_X005_301_v1` (13 sembolün hepsi, +247 R) ve tek bir ZEC uzun işlemi `haftalik-macd` stratejisinde (+70 R); ayrıca `jt-awesome` +99 R, `voltarget` +68 R, `lube` +58 R, `gauss-stoch-eth` +48 R. Sık geçen sembol ZECUSDT (13 stratejide açık) ve DK_ hisse/emtia sembolleri.
- Dahil edilseydi (bit = 2025-11-08; gerçekleşmemiş kâr, ağırlıkla tek coin ZEC'te toplanmış, yani kırılgan):

| Senaryo | Kill'siz portföy CAGR (hariç → dahil) | Kill'siz maks. düşüş (hariç → dahil) | Kill'li portföy CAGR (hariç → dahil) |
|---|---|---|---|
| baz_0.5% | 24.7% → 34.6% | -11.0% → -11.0% | 23.5% → 33.1% |
| A_1.5% | 86.8% → 133% | -47.4% → -47.4% | 31.0% → 32.8% |
| B_3% | 136% → 217% | -77.0% → -77.0% | 30.8% → 30.8% |
| C_5% | 155% → 229% | -90.0% → -90.0% | 58.8% → 58.8% |
| D_tamkasa | 1034% → 1027% | -41.2% → -41.2% | 28.5% → 28.5% |

Yorum: bu fark gerçekleşmemiş ve tek-coin yoğunluklu kâr; ana tablolar gerçekleşmiş sonuçları gösterir. Kill'siz yüksek riskte (B/C) dahil/hariç farkı çok büyük, çünkü açık pozisyonlar yüksek kaldıraçla büyütülmüş.

## 4c. "Aynı işlemler" ne demek: ham sinyal listesi, limitli sistem DEĞİL
Bu rapordaki "aynı işlemler" = stratejilerin **ham sinyal listesi** (motorun %1 risk ölç-modunda ürettiği, hiç reddetmeden aldığı her işlem). Mevcut kapanış backtest'i (`motor/arastirma/kapanis/tek_grafik.py`, `motor/arastirma/secim.py`) ise %1,5 risk, **toplam açık risk ≤ %5**, 3x kaldıraç ve günlük %3 limiti uygular ve ham işlemlerin yaklaşık yarısını reddeder (örnek: X005_705'te 1127 ham işlemin 594'ü, X005_301'de 3139'un 1146'sı kabul). Bu yeniden oynatma o filtreyi uygulamıyor, çünkü soru "boyut değişirse ne olur" idi. Sonuçları:
- **A (%1,5)**: limitli sistemde aynı anda en çok 3 pozisyon (3 x %1,5 = %4,5 ≤ %5) açık olabilir; burada ise çok sembolde sinyal birlikte gelince çok daha fazlası açık (bkz. kaldıraç tablosu). A'daki kill sayıları limitli sistemin davranışı DEĞİL, kuralsız oynatmanın davranışıdır.
- **B (%3) ve C (%5)**: %5 toplam açık risk tavanıyla %3'te en fazla 1 pozisyon, %5'te de 1 pozisyon açık olabilir. Yani B ve C mevcut kod limitleriyle uygulanamaz; burada gösterilenler "limitler olmasaydı" senaryosudur.
- **D (tam kasa)** de aynı şekilde mevcut limitlerle (3x, %5 risk tavanı, %20 kill) bağdaşmaz.
Limitli ve filtreli bir yeniden oynatma ayrı bir iş olur (yapılmadı).

## 5. Strateji bazında (maliyet x1)
Kill=açık, "CAGR / maks. düşüş", K = kill ayı:
| Strateji | baz_0.5% | A_1.5% | B_3% | C_5% | D_tamkasa |
|---|---|---|---|---|---|
| dis__e0v1en | 8.1% / -13.7% | 9.3% / -30.6% K21-04 | -5.8% / -32.1% K20-03 | -10.8% / -52.2% K20-03 | -14.4% / -62.7% K20-03 |
| dis__ewo-ema-ofset | 13.0% / -11.6% | -4.0% / -32.8% K20-03 | -3.8% / -41.6% K20-03 | -8.7% / -64.6% K20-03 | -24.1% / -89.5% K20-03 |
| dis__gauss-stoch-eth | 13.1% / -8.8% | 36.6% / -24.3% | 0.4% / -30.3% K20-06 | -5.3% / -36.2% K20-05 | -1.4% / -34.9% K20-02 |
| dis__haftalik-macd-gunluk-ma | 4.5% / -7.8% | 12.4% / -22.1% | 9.4% / -30.5% K23-05 | 20.4% / -44.1% K21-09 | 26.1% / -43.8% K20-05 |
| dis__hma-atr-rider | 10.7% / -15.5% | 11.9% / -30.7% K22-09 | 28.7% / -35.6% K22-01 | 51.7% / -32.2% K21-10 | 2.2% / -45.9% K20-03 |
| dis__jt-awesome-osilator | 19.5% / -30.2% K22-11 | 54.8% / -34.9% K22-02 | 47.1% / -34.5% K20-11 | 57.4% / -38.6% K20-10 | 15.2% / -31.9% K20-03 |
| dis__lube | 5.6% / -7.1% | 15.7% / -19.9% | 6.0% / -34.3% K23-07 | -1.8% / -30.9% K20-09 | -20.7% / -100% K20-03 |
| dis__uc-ortalama-boga-sma60 | 3.1% / -7.0% | 8.4% / -19.5% | 3.9% / -29.3% K23-03 | 8.3% / -29.6% K22-11 | -4.9% / -30.2% K20-05 |
| dis__voltarget-trend | 13.8% / -15.4% | 10.7% / -31.4% K23-02 | -2.9% / -32.8% K20-03 | -5.8% / -50.7% K20-03 | -4.2% / -68.7% K20-03 |
| kap_HAM_B001_538_v1 | 16.5% / -6.2% | 51.6% / -17.7% | 57.0% / -29.2% K22-06 | 89.2% / -27.1% K21-06 | 39.4% / -31.1% K20-02 |
| kap_HAM_B001_574_v1 | 4.6% / -1.1% | 13.9% / -3.2% | 7.2% / -32.1% K21-05 | -4.3% / -25.4% K20-03 | -2.1% / -28.1% K20-03 |
| kap_HAM_B001_670_v1 | 4.9% / -0.5% | 15.2% / -1.5% | 32.5% / -2.9% | 59.3% / -4.9% | 86.4% / -40.6% K21-01 |
| kap_HAM_X005_138_v3 | 4.1% / -3.2% | 12.3% / -9.4% | 24.3% / -18.4% | 39.4% / -29.8% | 21.1% / -44.7% K20-12 |
| kap_HAM_X005_259_v1 | 9.0% / -12.6% | 18.7% / -31.1% K22-11 | 44.7% / -31.7% K22-01 | 81.0% / -31.6% K21-09 | 27.3% / -39.9% K20-03 |
| kap_HAM_X005_301_v1 | 78.8% / -29.3% | 21.9% / -31.0% K20-04 | 25.2% / -34.5% K20-04 | 22.3% / -36.4% K20-01 | 23.6% / -42.2% K20-01 |
| kap_HAM_X005_664_v1 | 27.4% / -15.8% | 39.2% / -30.1% K22-03 | 21.2% / -30.7% K20-10 | 12.5% / -31.8% K20-03 | -100% / -100% K20-03 |
| kap_HAM_X005_705 | 25.0% / -14.6% | 34.1% / -27.1% K22-09 | 74.3% / -26.8% K21-12 | 133% / -29.6% K21-09 | 34.0% / -82.3% K20-05 |
| kap_HAM_X005_730_v2 | 23.1% / -19.5% | 70.2% / -30.6% K24-11 | 9.5% / -30.6% K20-10 | 2.4% / -30.8% K20-01 | 11.7% / -35.7% K20-01 |
| kap_HAM_X005_793_v1 | 11.3% / -7.2% | 32.6% / -21.0% | 35.6% / -32.5% K22-11 | 64.1% / -32.4% K22-04 | 42.0% / -16.5% K20-03 |
| pf__sabit_sepet | 6.8% / -13.8% | 9.6% / -30.3% K22-05 | 4.0% / -30.9% K20-06 | 10.9% / -30.5% K20-02 | yok |

Kill yok:
| Strateji | baz_0.5% | A_1.5% | B_3% | C_5% | D_tamkasa |
|---|---|---|---|---|---|
| dis__e0v1en | 8.1% / -13.7% | 22.7% / -38.1% | 37.4% / -66.3% | 34.7% / -88.6% | 19.6% / -94.5% |
| dis__ewo-ema-ofset | 13.0% / -11.6% | 39.0% / -35.6% | 71.2% / -67.5% | 79.1% / -92.5% | -100% / -100% |
| dis__gauss-stoch-eth | 13.1% / -8.8% | 36.6% / -24.3% | 65.9% / -43.2% | 95.7% / -61.5% | 192% / -94.8% |
| dis__haftalik-macd-gunluk-ma | 4.5% / -7.8% | 12.4% / -22.1% | 21.6% / -40.4% | 30.0% / -59.4% | 29.3% / -100% |
| dis__hma-atr-rider | 10.7% / -15.5% | 30.4% / -43.3% | 53.8% / -72.8% | 70.4% / -91.8% | -60.5% / -100% |
| dis__jt-awesome-osilator | 39.3% / -30.7% | 88.7% / -67.0% | 118% / -89.3% | 112% / -97.8% | 17.0% / -100% |
| dis__lube | 5.6% / -7.1% | 15.7% / -19.9% | 28.3% / -36.0% | 41.6% / -52.8% | 9.2% / -100% |
| dis__uc-ortalama-boga-sma60 | 3.1% / -7.0% | 8.4% / -19.5% | 14.7% / -35.2% | 20.3% / -51.7% | 35.4% / -92.6% |
| dis__voltarget-trend | 13.8% / -15.4% | 27.0% / -39.5% | 30.9% / -65.1% | 23.6% / -81.8% | -9.3% / -100% |
| kap_HAM_B001_538_v1 | 16.5% / -6.2% | 51.6% / -17.7% | 107% / -32.8% | 181% / -50.6% | -100% / -100% |
| kap_HAM_B001_574_v1 | 4.6% / -1.1% | 13.9% / -3.2% | 28.2% / -7.5% | 46.2% / -15.4% | -100% / -100% |
| kap_HAM_B001_670_v1 | 4.9% / -0.5% | 15.2% / -1.5% | 32.5% / -2.9% | 59.3% / -4.9% | 1775% / -36.2% |
| kap_HAM_X005_138_v3 | 4.1% / -3.2% | 12.3% / -9.4% | 24.3% / -18.4% | 39.4% / -29.8% | 82.1% / -70.3% |
| kap_HAM_X005_259_v1 | 9.0% / -12.6% | 24.9% / -35.2% | 41.8% / -61.7% | 46.9% / -86.1% | -100% / -100% |
| kap_HAM_X005_301_v1 | 78.8% / -29.3% | 198% / -67.9% | 272% / -90.7% | 252% / -98.1% | 83.0% / -100% |
| kap_HAM_X005_664_v1 | 27.4% / -15.8% | 86.2% / -41.9% | 173% / -68.8% | 255% / -87.9% | -100% / -100% |
| kap_HAM_X005_705 | 25.0% / -14.6% | 74.6% / -38.6% | 144% / -64.3% | 214% / -83.9% | -51.6% / -100% |
| kap_HAM_X005_730_v2 | 23.1% / -19.5% | 58.9% / -50.3% | 89.4% / -78.3% | 93.7% / -94.2% | -88.5% / -100% |
| kap_HAM_X005_793_v1 | 11.3% / -7.2% | 32.6% / -21.0% | 60.7% / -39.6% | 88.7% / -60.0% | -100% / -100% |
| pf__sabit_sepet | 6.8% / -13.8% | 18.7% / -36.8% | 30.9% / -61.7% | 32.8% / -83.7% | yok |

Aylık metrikler (kill=açık; ortalama / medyan / en kötü ay / zararlı ay oranı):
| Strateji | baz_0.5% | A_1.5% | B_3% | C_5% | D_tamkasa |
|---|---|---|---|---|---|
| dis__e0v1en | 0.7% / 0.3% / -6.3% / 21% | 0.9% / 0.0% / -21.5% / 6% | -0.4% / 0.0% / -30.8% / 3% | -0.7% / 0.0% / -50.4% / 3% | -0.8% / 0.0% / -61.0% / 3% |
| dis__ewo-ema-ofset | 1.0% / 0.3% / -5.0% / 20% | -0.2% / 0.0% / -31.5% / 1% | -0.1% / 0.0% / -39.2% / 1% | -0.2% / 0.0% / -62.2% / 1% | -0.3% / 0.0% / -88.8% / 1% |
| dis__gauss-stoch-eth | 1.1% / -0.3% / -2.0% / 63% | 3.1% / -0.8% / -6.0% / 63% | 0.1% / 0.0% / -8.6% / 7% | -0.4% / 0.0% / -14.3% / 7% | -0.1% / 0.0% / -11.1% / 1% |
| dis__haftalik-macd-gunluk-ma | 0.4% / -0.2% / -2.0% / 61% | 1.1% / -0.6% / -6.0% / 61% | 1.0% / 0.0% / -9.4% / 35% | 2.1% / 0.0% / -15.1% / 15% | 3.5% / 0.0% / -22.8% / 4% |
| dis__hma-atr-rider | 0.9% / 0.6% / -4.3% / 41% | 1.1% / 0.0% / -11.2% / 20% | 2.4% / 0.0% / -15.3% / 11% | 4.3% / 0.0% / -19.1% / 8% | 0.5% / 0.0% / -41.1% / 1% |
| dis__jt-awesome-osilator | 1.7% / 0.0% / -7.0% / 25% | 4.7% / 0.0% / -20.9% / 15% | 4.1% / 0.0% / -17.1% / 7% | 5.6% / 0.0% / -31.7% / 7% | 2.6% / 0.0% / -23.2% / 3% |
| dis__lube | 0.5% / 0.0% / -2.0% / 38% | 1.3% / 0.0% / -5.8% / 38% | 0.6% / 0.0% / -7.6% / 30% | -0.0% / 0.0% / -12.3% / 7% | -2.3% / 0.0% / -100% / 4% |
| dis__uc-ortalama-boga-sma60 | 0.3% / -0.1% / -1.3% / 56% | 0.8% / -0.2% / -3.8% / 56% | 0.5% / 0.0% / -7.5% / 32% | 1.0% / 0.0% / -12.5% / 27% | -0.4% / 0.0% / -19.0% / 4% |
| dis__voltarget-trend | 1.2% / -0.1% / -5.6% / 54% | 1.1% / 0.0% / -16.3% / 31% | -0.1% / 0.0% / -30.5% / 1% | -0.2% / 0.0% / -48.0% / 1% | 0.8% / 0.0% / -64.9% / 1% |
| kap_HAM_B001_538_v1 | 1.3% / 0.4% / -3.4% / 39% | 4.0% / 1.2% / -9.9% / 39% | 5.0% / 0.0% / -13.7% / 15% | 8.2% / 0.0% / -22.1% / 7% | 5.3% / 0.0% / 0.0% / 0% |
| kap_HAM_B001_574_v1 | 0.4% / 0.1% / -0.9% / 11% | 1.1% / 0.2% / -3.0% / 11% | 0.8% / 0.0% / -28.8% / 3% | -0.3% / 0.0% / -25.4% / 1% | -0.1% / 0.0% / -28.1% / 1% |
| kap_HAM_B001_670_v1 | 0.4% / 0.2% / -0.1% / 7% | 1.2% / 0.5% / -0.4% / 7% | 2.5% / 1.0% / -0.8% / 7% | 4.3% / 1.7% / -1.4% / 7% | 6.7% / 0.0% / -28.0% / 1% |
| kap_HAM_X005_138_v3 | 0.3% / 0.0% / -2.4% / 37% | 1.0% / 0.0% / -7.1% / 37% | 2.1% / 0.0% / -14.1% / 37% | 3.5% / 0.0% / -23.5% / 37% | 3.1% / 0.0% / -26.4% / 7% |
| kap_HAM_X005_259_v1 | 0.8% / -0.1% / -4.8% / 51% | 1.7% / 0.0% / -14.3% / 24% | 3.8% / 0.0% / -14.9% / 15% | 6.9% / 0.0% / -20.7% / 14% | 4.8% / 0.0% / -16.2% / 1% |
| kap_HAM_X005_301_v1 | 6.1% / 1.1% / -11.4% / 44% | 2.4% / 0.0% / -13.7% / 4% | 3.8% / 0.0% / -25.9% / 3% | 4.9% / 0.0% / -32.8% / 1% | 5.9% / 0.0% / -38.2% / 1% |
| kap_HAM_X005_664_v1 | 2.2% / 0.4% / -5.6% / 45% | 3.4% / 0.0% / -16.2% / 18% | 2.1% / 0.0% / -21.4% / 6% | 1.6% / 0.0% / -31.6% / 1% | 4.5% / 0.0% / -100% / 1% |
| kap_HAM_X005_705 | 2.0% / -0.0% / -3.3% / 51% | 2.9% / 0.0% / -9.4% / 23% | 6.0% / 0.0% / -16.2% / 14% | 10.1% / 0.0% / -14.4% / 11% | 5.5% / 0.0% / -56.1% / 3% |
| kap_HAM_X005_730_v2 | 2.0% / -0.0% / -5.4% / 51% | 6.2% / 0.0% / -13.8% / 42% | 1.1% / 0.0% / -20.6% / 6% | 0.3% / 0.0% / -15.8% / 1% | 1.4% / 0.0% / -8.5% / 1% |
| kap_HAM_X005_793_v1 | 0.9% / 0.0% / -3.3% / 48% | 2.8% / 0.0% / -9.7% / 48% | 3.1% / 0.0% / -16.7% / 21% | 5.3% / 0.0% / -17.0% / 14% | 5.2% / 0.0% / 0.0% / 0% |
| pf__sabit_sepet | 0.6% / -0.6% / -4.3% / 55% | 0.9% / 0.0% / -12.7% / 18% | 0.4% / 0.0% / -11.6% / 4% | 1.0% / 0.0% / 0.0% / 0% | yok |

Azami eşzamanlı kaldıraç (kill=açık; toplam notional / gerçekleşmiş kasa):
| Strateji | baz_0.5% | A_1.5% | B_3% | C_5% | D_tamkasa |
|---|---|---|---|---|---|
| dis__e0v1en | 0.9x | 2.8x | 5.6x | 9.3x | 11.0x |
| dis__ewo-ema-ofset | 1.2x | 2.7x | 5.4x | 9.2x | 11.0x |
| dis__gauss-stoch-eth | 2.9x | 8.8x | 3.2x | 5.4x | 15.3x |
| dis__haftalik-macd-gunluk-ma | 0.9x | 2.8x | 4.4x | 5.7x | 18.2x |
| dis__hma-atr-rider | 1.1x | 3.1x | 6.3x | 10.5x | 10.2x |
| dis__jt-awesome-osilator | 1.8x | 5.2x | 9.2x | 15.5x | 15.3x |
| dis__lube | 0.6x | 1.7x | 3.0x | 3.5x | 4.1x |
| dis__uc-ortalama-boga-sma60 | 0.3x | 1.0x | 2.1x | 3.5x | 3.0x |
| dis__voltarget-trend | 1.6x | 5.1x | 2.9x | 4.7x | 9.0x |
| kap_HAM_B001_538_v1 | 0.3x | 0.8x | 1.4x | 2.4x | 11.3x |
| kap_HAM_B001_574_v1 | 0.2x | 0.6x | 1.2x | 2.0x | 2.0x |
| kap_HAM_B001_670_v1 | 0.2x | 0.5x | 1.0x | 1.7x | 11.0x |
| kap_HAM_X005_138_v3 | 0.3x | 0.9x | 1.8x | 3.0x | 8.0x |
| kap_HAM_X005_259_v1 | 0.5x | 1.1x | 2.0x | 3.2x | 8.7x |
| kap_HAM_X005_301_v1 | 1.9x | 3.3x | 7.1x | 11.0x | 12.6x |
| kap_HAM_X005_664_v1 | 0.6x | 1.2x | 2.5x | 3.3x | 11.0x |
| kap_HAM_X005_705 | 0.6x | 1.2x | 2.5x | 4.1x | 12.2x |
| kap_HAM_X005_730_v2 | 0.6x | 1.8x | 2.6x | 3.1x | 7.3x |
| kap_HAM_X005_793_v1 | 0.5x | 1.4x | 2.1x | 3.5x | 11.0x |
| pf__sabit_sepet | - | - | - | - | yok |

## 6. Yıllık getiri
### Birleşik portföy yıllık getiri x1 kill=True
| Senaryo | 2020 | 2021 | 2022 | 2023 | 2024 | 2025 |
|---|---|---|---|---|---|---|
| baz_0.5% | 20.2% | 50.9% | -5.7% | 13.4% | 79.4% | -1.1% |
| A_1.5% | 58.3% | 121% | -11.9% | 8.8% | 40.9% | 2.8% |
| B_3% | 105% | 143% | -6.6% | 0.8% | 1.6% | 0.6% |
| C_5% | 174% | 433% | -1.0% | 1.2% | 1.8% | 0.8% |
| D_tamkasa | 413% | -15.3% | 0.0% | 0.0% | 0.0% | 0.0% |

### Birleşik portföy yıllık getiri x1 kill=False
| Senaryo | 2020 | 2021 | 2022 | 2023 | 2024 | 2025 |
|---|---|---|---|---|---|---|
| baz_0.5% | 20.2% | 50.9% | -5.8% | 15.0% | 87.5% | -0.9% |
| A_1.5% | 65.0% | 237% | -22.2% | 55.4% | 607% | -18.5% |
| B_3% | 141% | 626% | -46.9% | 97.9% | 1281% | -39.9% |
| C_5% | 257% | 1134% | -69.0% | 140% | 1187% | -43.0% |
| D_tamkasa | 935% | 147671% | 69.8% | 343% | 472% | 126% |

Strateji bazında yıllık getiri (kill=açık) A 1,5%:
| Strateji | 2020 | 2021 | 2022 | 2023 | 2024 | 2025 |
|---|---|---|---|---|---|---|
| dis__e0v1en | 46.5% | 14.9% | 0.0% | 0.0% | 0.0% | 0.0% |
| dis__ewo-ema-ofset | -21.4% | 0.0% | 0.0% | 0.0% | 0.0% | 0.0% |
| dis__gauss-stoch-eth | 22.8% | 106% | -7.9% | -5.0% | 156% | 9.5% |
| dis__haftalik-macd-gunluk-ma | 52.0% | -0.7% | -11.1% | -8.2% | 59.8% | 0.5% |
| dis__hma-atr-rider | 52.9% | 56.6% | -19.2% | 0.0% | 0.0% | 0.0% |
| dis__jt-awesome-osilator | 106% | 682% | -20.1% | 0.0% | 0.0% | 0.0% |
| dis__lube | -7.2% | 34.6% | 5.5% | -9.9% | 38.9% | 42.5% |
| dis__uc-ortalama-boga-sma60 | 1.2% | 27.4% | -4.8% | 5.2% | 26.6% | -1.9% |
| dis__voltarget-trend | 6.4% | 72.0% | -23.5% | 2.7% | 26.2% | 0.0% |
| kap_HAM_B001_538_v1 | 78.1% | 174% | -6.4% | 21.3% | 85.4% | 11.1% |
| kap_HAM_B001_574_v1 | 7.5% | 61.0% | 1.8% | 2.7% | 5.2% | 12.8% |
| kap_HAM_B001_670_v1 | 20.0% | 54.1% | 2.8% | 7.1% | 8.4% | 3.8% |
| kap_HAM_X005_138_v3 | 21.3% | 6.7% | 13.4% | 12.1% | 15.0% | 4.2% |
| kap_HAM_X005_259_v1 | 98.9% | 79.5% | -23.4% | 0.0% | 0.0% | 0.0% |
| kap_HAM_X005_301_v1 | 218% | 0.0% | 0.0% | 0.0% | 0.0% | 0.0% |
| kap_HAM_X005_664_v1 | 151% | 200% | -7.8% | 0.0% | 0.0% | 0.0% |
| kap_HAM_X005_705 | 147% | 169% | -16.0% | 0.0% | 0.0% | 0.0% |
| kap_HAM_X005_730_v2 | 34.8% | 246% | -11.9% | 103% | 170% | 0.0% |
| kap_HAM_X005_793_v1 | 75.5% | 77.0% | -13.4% | 3.9% | 91.9% | -3.0% |
| pf__sabit_sepet | 53.7% | 33.9% | -16.9% | 0.0% | 0.0% | 0.0% |

C 5%:
| Strateji | 2020 | 2021 | 2022 | 2023 | 2024 | 2025 |
|---|---|---|---|---|---|---|
| dis__e0v1en | -48.9% | 0.0% | 0.0% | 0.0% | 0.0% | 0.0% |
| dis__ewo-ema-ofset | -41.3% | 0.0% | 0.0% | 0.0% | 0.0% | 0.0% |
| dis__gauss-stoch-eth | -27.2% | 0.0% | 0.0% | 0.0% | 0.0% | 0.0% |
| dis__haftalik-macd-gunluk-ma | 218% | -6.5% | 0.0% | 0.0% | 0.0% | 0.0% |
| dis__hma-atr-rider | 217% | 262% | 0.0% | 0.0% | 0.0% | 0.0% |
| dis__jt-awesome-osilator | 332% | 230% | 0.0% | 0.0% | 0.0% | 0.0% |
| dis__lube | -10.3% | 0.0% | 0.0% | 0.0% | 0.0% | 0.0% |
| dis__uc-ortalama-boga-sma60 | -0.5% | 83.4% | -12.3% | 0.0% | 0.0% | 0.0% |
| dis__voltarget-trend | -29.7% | 0.0% | 0.0% | 0.0% | 0.0% | 0.0% |
| kap_HAM_B001_538_v1 | 414% | 713% | 0.0% | 0.0% | 0.0% | 0.0% |
| kap_HAM_B001_574_v1 | -22.8% | 0.0% | 0.0% | 0.0% | 0.0% | 0.0% |
| kap_HAM_B001_670_v1 | 83.0% | 310% | 9.5% | 25.4% | 30.7% | 13.2% |
| kap_HAM_X005_138_v3 | 74.6% | 23.1% | 43.7% | 40.2% | 48.7% | 8.4% |
| kap_HAM_X005_259_v1 | 567% | 384% | 0.0% | 0.0% | 0.0% | 0.0% |
| kap_HAM_X005_301_v1 | 225% | 0.0% | 0.0% | 0.0% | 0.0% | 0.0% |
| kap_HAM_X005_664_v1 | 99.4% | 0.0% | 0.0% | 0.0% | 0.0% | 0.0% |
| kap_HAM_X005_705 | 951% | 1257% | 0.0% | 0.0% | 0.0% | 0.0% |
| kap_HAM_X005_730_v2 | 14.9% | 0.0% | 0.0% | 0.0% | 0.0% | 0.0% |
| kap_HAM_X005_793_v1 | 380% | 368% | -19.3% | 0.0% | 0.0% | 0.0% |
| pf__sabit_sepet | 83.2% | 0.0% | 0.0% | 0.0% | 0.0% | 0.0% |

(Kill'den sonraki yıllar 0,0% = hesap durmuş. Tüm senaryoların yıllık tabloları `yillik.csv`'de.)

## 7. ≥%4/ay ortalamaya ulaşan hesaplar (x1)
kill=True A_1.5%: jt-awesome-osilator(4.7%, DD -34.9%), kap_X005_730_v2(6.2%, DD -30.6%)

kill=True B_3%: jt-awesome-osilator(4.1%, DD -34.5%), kap_X005_705(6.0%, DD -26.8%), kap_B001_538_v1(5.0%, DD -29.2%)

kill=True C_5%: jt-awesome-osilator(5.6%, DD -38.6%), hma-atr-rider(4.3%, DD -32.2%), kap_X005_705(10.1%, DD -29.6%), kap_X005_301_v1(4.9%, DD -36.4%), kap_B001_670_v1(4.3%, DD -4.9%), kap_X005_259_v1(6.9%, DD -31.6%), kap_X005_793_v1(5.3%, DD -32.4%), kap_B001_538_v1(8.2%, DD -27.1%)

kill=True D_tamkasa: kap_X005_664_v1(4.5%, DD -100%), kap_X005_705(5.5%, DD -82.3%), kap_X005_301_v1(5.9%, DD -42.2%), kap_B001_670_v1(6.7%, DD -40.6%), kap_X005_259_v1(4.8%, DD -39.9%), kap_X005_793_v1(5.2%, DD -16.5%), kap_B001_538_v1(5.3%, DD -31.1%)

kill=donuk A_1.5%: jt-awesome-osilator(4.5%, DD -31.1%)

kill=donuk B_3%: kap_X005_705(6.0%, DD -24.6%), kap_B001_538_v1(5.0%, DD -29.2%)

kill=donuk C_5%: hma-atr-rider(4.2%, DD -32.2%), kap_X005_705(10.0%, DD -25.4%), kap_B001_670_v1(4.3%, DD -4.9%), kap_X005_259_v1(6.9%, DD -31.6%), kap_X005_793_v1(5.1%, DD -32.4%), kap_B001_538_v1(8.2%, DD -27.1%)

kill=donuk D_tamkasa: kap_X005_664_v1(5.4%, DD -40.7%), kap_X005_705(7.1%, DD -37.1%), kap_B001_670_v1(7.0%, DD -24.2%), kap_X005_259_v1(4.8%, DD -39.9%), kap_B001_538_v1(5.3%, DD -31.1%)

kill=False A_1.5%: jt-awesome-osilator(7.7%, DD -67.0%), kap_X005_664_v1(6.4%, DD -41.9%), kap_X005_705(5.8%, DD -38.6%), kap_X005_301_v1(16.1%, DD -67.9%), kap_X005_730_v2(5.6%, DD -50.3%)

kill=False B_3%: gauss-stoch-eth(5.9%, DD -43.2%), ewo-ema-ofset(5.9%, DD -67.5%), jt-awesome-osilator(13.2%, DD -89.3%), hma-atr-rider(4.9%, DD -72.8%), voltarget-trend(4.6%, DD -65.1%), kap_X005_664_v1(12.4%, DD -68.8%), kap_X005_705(10.8%, DD -64.3%), kap_X005_301_v1(29.5%, DD -90.7%), kap_X005_730_v2(11.0%, DD -78.3%), kap_X005_259_v1(4.5%, DD -61.7%), kap_X005_793_v1(5.5%, DD -39.6%), kap_B001_538_v1(8.0%, DD -32.8%)

kill=False C_5%: gauss-stoch-eth(9.5%, DD -61.5%), ewo-ema-ofset(9.5%, DD -92.5%), jt-awesome-osilator(21.9%, DD -97.8%), pf__sabit_sepet(7.1%, DD -83.7%), hma-atr-rider(7.8%, DD -91.8%), voltarget-trend(7.5%, DD -81.8%), e0v1en(4.6%, DD -88.6%), kap_X005_664_v1(20.1%, DD -87.9%), kap_X005_705(16.8%, DD -83.9%), kap_X005_301_v1(46.9%, DD -98.1%), kap_B001_670_v1(4.3%, DD -4.9%), kap_X005_730_v2(20.0%, DD -94.2%), kap_X005_259_v1(7.6%, DD -86.1%), kap_X005_793_v1(8.9%, DD -60.0%), kap_B001_538_v1(13.3%, DD -50.6%)

kill=False D_tamkasa: gauss-stoch-eth(43.1%, DD -94.8%), jt-awesome-osilator(57.0%, DD -100%), uc-ortalama-boga-sma60(10.2%, DD -92.6%), lube(6.7%, DD -100%), hma-atr-rider(49.2%, DD -100%), voltarget-trend(85.3%, DD -100%), haftalik-macd-gunluk-ma(13.8%, DD -100%), e0v1en(4.9%, DD -94.5%), kap_X005_664_v1(4.5%, DD -100%), kap_X005_705(37.1%, DD -100%), kap_X005_301_v1(59.6%, DD -100%), kap_X005_138_v3(10.7%, DD -70.3%), kap_B001_670_v1(58.7%, DD -36.2%), kap_B001_574_v1(26.4%, DD -100%), kap_X005_730_v2(362%, DD -100%), kap_X005_259_v1(24.3%, DD -100%), kap_X005_793_v1(23.7%, DD -100%), kap_B001_538_v1(84.1%, DD -100%)

## 8. Varsayımlar ve sınırlar
- **Yalnız yeniden boyutlandırma**: giriş/çıkış sinyalleri aynı. Gerçekte büyük pozisyon farklı dolum/kayma, 3x kaldıraç tavanı, günlük %3 limiti ve likidasyon riski getirirdi; hiçbiri simüle edilmedi. Maliyet R içinde; D'de R x stop mesafesi kullanıldığı için maliyet orantılı kalır (büyük pozisyonda kayma/derinlik etkisi yok).
- **Mark-to-market yok**: özsermaye yalnız işlem kapanınca güncellenir; açık işlemlerin geçici zararı düşüşte görünmez, yani düşüşler hafif iyimser. Boyut giriş anındaki gerçekleşmiş kasadan.
- **Kill sonrası açık işlemler** ön kayıttaki kurala göre kendi çıkışına kadar sürer; bu özellikle uzun tutulan 1d stratejilerde kill'den sonra büyük kâr/zarar getirebilir (bkz. kill=donuk). Kill kalıcı: hesap bir daha açılmaz.
- **2020 öncesi** işlemler analiz dışı (swing stratejilerinin TradFi geçmişi 2008'e uzanıyor). Dönem kripto boğa ağırlıklı.
- **pf__sabit_sepet** portföy stratejisidir: işlem listesi yok, günlük getiri x s (s = f/%1) ile ölçeklendi (paper ile aynı mantık); D yok (stop mesafesi tanımsız), D'nin portföyü 19 hesaptır. Kaldıraç ölçümü ona yok.
- `sf` (stop mesafesi / fiyat) motorun `islem_hazirla` çıktısıdır (alt sınır 1e-4; R==0 satırlarında komşu satırın stop oranı kullanılır, upstream kuralı). Nasos tipi 5m stratejilerde (B001:574, 670) sabit %30-35 stop var; bu yüzden %1,5 risk ile pozisyon neredeyse kasanın %4-5'i (kaldıraç <1x) ve getiri sönük, D'de ise fiyat hareketi birebir kasaya yansır.
- Üretim doğrulaması: 19 tek-grafik stratejisinin hepsi hatasız koşuldu (veri eksiği yok). Mevcut mühürlü v2 ham sonuçlarıyla 5 strateji kontrol edildi: işlem sayıları aynı, R toplamı 1e-3 içinde aynı (jt-awesome'ta DK_COPPER/NATGAS'ta ±0,3 R'lik küçük fark).
- Ardışık oynatma tek yoldur (tek geçmiş); örneklem şansı yüksek. Özellikle kill kararı yolu şansa bağlı: B ve C'de bir hesabın kill tarihi tek bir kötü haftanın (Mart 2020) sonucudur.
