# Kaldıraç 3x / 4x / 5x ölçümü ve fiyat boşluğu stresi

Yalnız ölçüm. Limit, ayar, strateji ve motor kodu değişmedi. Betik: `araclar/kaldirac_stres.py` (test: `testler/test_kaldirac_stres.py`). Ham sayılar: `ham_sayilar.json` (ana), `duyarlilik_risk3/ham_sayilar.json` (ek).

## Ne ölçüldü
- Set: `paper_v2_seti.json`, 10 hesap (imza fffbc6624416634e), her biri kendi 10.000 USD kasasında; v2 maliyet tablosu; aynı veri.
- Dönem: 2020-01-01 → 2025-11-07 (yalnız geliştirme dönemi; holdout okunmadı).
- Motor: `motor/portfoy` çekirdeği (`_Motor`). Brüt nominal tavanı K = 3, 4, 5. Motorun sert 3x tavanı yalnız bu betikte, çağrı süresince geçici kopyayla gevşetildi; `limitler.py` ve `motor/canli/**` aynen duruyor.
- İki boyut profili (tek fark K): **paper** = işlem başı %0,5 risk, toplam stop riski %5, günlük %5, kill %20. **canlı-benzeri** = işlem başı %1,5 risk, toplam stop riski %6, günlük %5, strateji kill %30. Ek duyarlılık: işlem başı %3 (canlı limitin izin verdiği en yüksek).

## Ana sonuç
**K = 3, 4 ve 5 için sonuçlar neredeyse birebir aynı.** Brüt tavan hiç bağlamıyor: 10 hesabın en yüksek brüt maruziyeti paper'da 1,12x, canlı-benzerinde 1,93x, %3 riskte 2,14x. Yani işlem başı risk ve toplam risk tavanı, kaldıraç tavanından çok önce devreye giriyor. 4x/5x ek getiri ya da ek düşüş getirmiyor (%3 riskte yalnız ewo hesabında 4x/5x'te 9 işlem daha az, getiri −%0,2 ile −%4 puan arası fark).

### Ana tablo (10 hesap; getiri ve DD hesap ortalaması/en kötüsü)

| Profil | K | Ort. getiri % | En kötü hesap max DD % | Gün sonu ≤ −%5 gün (10 hesap toplamı) | Kill tetik | En kötü gün % | En kötü işlem (% kasa) | Maks brüt | Maks tek poz (x kasa) |
|---|---|---|---|---|---|---|---|---|---|
| paper | 3x | 87,5 | −16,7 | 13 | 0/10 | −6,7 | −0,9 | 1,12 | 0,25 |
| paper | 4x | 87,5 | −16,7 | 13 | 0/10 | −6,7 | −0,9 | 1,12 | 0,25 |
| paper | 5x | 87,5 | −16,7 | 13 | 0/10 | −6,7 | −0,9 | 1,12 | 0,25 |
| canlı %1,5 | 3x | 156,1 | −30,1 | 52 | 2/10 | −10,3 | −2,6 | 1,93 | 0,52 |
| canlı %1,5 | 4x | 156,1 | −30,1 | 52 | 2/10 | −10,3 | −2,6 | 1,93 | 0,52 |
| canlı %1,5 | 5x | 156,1 | −30,1 | 52 | 2/10 | −10,3 | −2,6 | 1,93 | 0,52 |
| canlı %3 (duyarlılık) | 3x | 154,0 | −30,9 | 79 | 4/10 | −11,6 | −4,6 | 2,14 | 0,87 |
| canlı %3 (duyarlılık) | 4x | 153,8 | −30,9 | 79 | 4/10 | −11,6 | −4,6 | 2,14 | 0,87 |
| canlı %3 (duyarlılık) | 5x | 153,6 | −30,9 | 79 | 4/10 | −11,6 | −4,6 | 2,14 | 0,89 |

Notlar: "gün sonu ≤ −%5 gün" UTC gün sonu MTM'ine göre; motor günlük limiti gün içi de sayıyor, sayılar aynı çıktı (13 / 52 / 79). Kill'ler (canlı %1,5): e0v1en ve hma-atr-rider, her ikisi 3x/4x/5x'te aynı. Kapsam sınırı: 2 strateji 5m, 2 strateji 15m, 6 strateji 1d; veri aralığı kısaltılmadı.

## Fiyat boşluğu stresi
Varsayım: tüm açık pozisyonlar aynı anda g kadar ters sıçrar (long düşer, short yükselir), stoplar kapanışta değil boşlukla dolar. Tek günlük kasa kaybı = brüt maruziyet × g. Uygulandığı an: her hesabın backtest geçmişindeki en yüksek brütlü anı; birleşik sütunu 10 hesabın gün-içi tepe nominal toplamı (aynı anda olmayabilir, üst sınır).

| Profil | Boşluk | Hesap başına en kötü kayıp (% kasa) | 10 hesap birleşik (üst sınır) |
|---|---|---|---|
| paper | %5 / %10 / %15 | 5,6 / 11,2 / 16,8 | 1,6 / 3,1 / 4,7 |
| canlı %1,5 | %5 / %10 / %15 | 9,7 / 19,3 / 29,0 | 2,9 / 5,7 / 8,6 |
| canlı %3 | %5 / %10 / %15 | 10,7 / 21,4 / 32,0 | 3,0 / 6,1 / 9,1 |

K'ya göre fark yok (brüt aynı olduğu için kayıp aynı).

Limitlerle karşılaştırma:
- Günlük %5: tek hesapta %5 boşluk bile (−5,6 / −9,7) eşiği aşıyor; günlük limit anlık boşluğu engelleyemez, yalnız ertesi giriş durur. Birleşik 10 hesapta %10 boşluk (−3,1 / −5,7) canlı-benzerinde eşiğe değiyor.
- Strateji kill −%30: canlı %1,5'te %15 boşluk en kötü hesapta −29,0, %3 riskte −32,0 (kill'i aşar). Hesap kill −%20: birleşik −8,6 / −9,1, aşılmıyor.
- Marjin ≤ %50: tek pozisyon marjı = nominal / K. En büyük tek pozisyon canlı %1,5'te 0,52x kasa, yani marj 5x'te %10, 4x'te %13, 3x'te %17 (kural per-işlem; aşılmıyor). Toplam marj kullanımı (brüt/K) en kötü hesapta 3x'te %64, 4x'te %48, 5x'te %39.
- Likidasyon (varsayım: izole marj, marj = nominal/K, bakım marjı %0,5): pozisyon tek başına likide olur boşluk ≥ 1/K − %0,5 = 3x %32,8, 4x %24,5, 5x %19,5 (stop > %15 ise 2x: %49,5). Ölçülen boşluklar (%5–%15) bu eşiklerin altında: likidasyon yok. Ama 5x'te %15 boşluk pozisyon marjının %75'ini siler (4x %60, 3x %45). Çapraz marj gibi hesap bazında bakarsak en kötü hesapta likidasyon boşluğu %51 (brüt 1,93x), erişilmedi.

## "5x güvenli mi" (ölçüme dayalı yanıt, öneri değil)
- Mevcut risk kurallarıyla (işlem başı %0,5–%3, toplam stop riski %5–%6) 5x tavanı hiç bağlamadı: getiri, düşüş, kill ve en kötü gün 3x ile aynı. 5x'in ölçülebilir tek farkı izole likidasyon tamponunun %32,8'den %19,5'e inmesi.
- Boşluk stresinde hesap kaybı K'dan değil brütten geliyor; %15 boşlukta en kötü hesap −%29 / −%32 (strateji kill −%30 civarı), 10 hesap birleşik −%8,6 / −%9,1.
- %20 ve üzeri boşluk ölçülmedi; 5x'te bu pozisyonları likide eder (eşik %19,5).

## Varsayımlar ve sınırlar
- Boşluk modeli: tek yönlü eşzamanlı sıçrama, stopun ötesinde dolum; mark fiyatından g kadar kayıp, ek kayma/komisyon eklenmedi. Gerçek boşluk korelasyonu ve likidite çöküşü modellenmedi.
- Likidasyon: izole marj, bakım marjı %0,5 sabit (Binance kademesi pozisyon büyüklüğüne göre değişir, burada tek değer).
- Canlı-benzeri profil yaklaşıktır: motorda canlıdaki marj ≤ %50 kuralı, stop > %15 için 2x kuralı, %25 stop uzaklık atlaması, min tutar ve adım yuvarlaması yok; paper'ın seans kayma çarpanı ve Telegram/ML/etiket filtreleri yok.
- Gün-sonu eşik günleri 5m/15m/1d barlarının MTM'ine bağlı; TradFi funding varsayım değeri (v2) kullanıldı.
- Strateji kümesi sonradan seçilmiş, tarihsel; kanıt değil. Sonuçlar paper/canlı performans öngörüsü değil, yalnız bu kuralların bu veride davranışı.
