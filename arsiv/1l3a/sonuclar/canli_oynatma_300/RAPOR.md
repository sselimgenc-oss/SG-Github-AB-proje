# Canlı oynatma, 300 USD hesap: rapor (düzeltilmiş sürüm, Fable denetimi sonrası)

Soru: Her odak strateji tek başına 300 USD ile CANLI limitlerle koşsaydı sinyallerinin kaçı alınırdı, getiri ve düşüş ne olurdu?
Yöntem: PLAN.md. Kod: araclar/canli_oynatma_300.py (gerçek `kurallar.boyutlandir` / `canli_limitler` çağrılır). Dönem 2020-01-01 - 2025-11-07, geliştirme verisi.
`Risk` = işlem başı stopta kayıp. Kodun bugün izin verdiği tek değer %1,5; %0,5 ve %1 yalnız bilgi içindir.

## Düzeltmeler (ilk sürüme göre)
- Atlama nedenleri artık canlı boyutlandırmanın `baglayan` alanına göre ayrıldı. Eskiden "min tutar" denen atlamaların çoğu aslında %6 toplam stop riski bütçesinin bıraktığı kırıntıydı.
- Günlük -%6 ve kill -%30 artık kasa = min(özsermaye, 300) üzerinden (canlı yürütücü gibi).
- Açık pozisyon riski: canlı `_risk_ozeti` açık riski MALİYETSİZ sayar ((mark - stop) x adet), yeni işlem ise maliyetli boyutlanır. Canlıda da aynı tutarsızlık var; replay canlıya sadık bırakıldı (replay'de mark yok, giriş fiyatı kullanıldı).

## Kısa sonuç (maliyet x1, risk %1,5)
- Swing stratejilerde sinyalin yalnız yaklaşık %38-44'ü alınıyor (664, 705, hma, gauss); gün içi ewo ve e0v1en çok daha fazlasını alıyor (bkz. tablo).
- Ana neden küçük hesap değil, **%6 toplam stop riski bütçesi**: %1,5 riskte bu bütçe yalnız yaklaşık 4 pozisyona yeter (6 / 1,5). Pozisyon açıkken gelen yeni sinyalin payına kalan bütçe ya pozisyonu KISALTIR ya da kırıntı bırakır; kırıntı adım/min tutarın altında yuvarlanınca atlanır. Swing stratejiler aynı anda çok pozisyon tuttuğu için en çok bunlar etkilenir.
- Düşük risk daha çok sinyal alır: %0,5'te aynı %6 bütçe yaklaşık 12 pozisyona yeter, %1,5'te yaklaşık 4. Bu yüzden risk düştükçe alınan pay yükselir (aşağıdaki tabloda görülür), ama getiri de küçülür.
- Stop > %25 elemesi yalnız yapısal: 670 hiç alınmaz (1443 sinyalin tamamı), 574 yalnız 1 işlem alır.
- GERÇEK min tutar atlamaları (hesap büyüklüğüyle ilgili) 300 USD'de en çok geniş stoplu 664 (145 sinyal) ve 705 (86) ile hma'da (32); gauss 10, ewo 23, e0v1en 22. 1500 USD'de bunlar 664 18, hma 5, 705 5, gauss 2, ewo 0, e0v1en 0'a iner (aşağıdaki duyarlılık tablosu).
- Kasa tavanı düzeltmesinden sonra (günlük/kill min(özsermaye, 300) üzerinden) hiçbir strateji x senaryoda strateji kill'i tetiklenmedi; en kötü düşüş e0v1en x2 %1,5'te -%27,1 (kill sınırı -%30'a yakın).

## Maliyet x1 (ana)
| Strateji | Risk | Sinyal | Tam | Kısaltılmış | Stop>%25 | Toplam risk %6 | Brüt/nominal | Gerçek min tutar | Günlük stop | Kill | Alınan % | CAGR % | Max DD % | Son USD | Kill |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| gauss | %0.5 | 990 | 684 | 18 | 192 | 33 | 0 | 63 | 0 | 0 | 70.9 | 6.6 | -4.4 | 436.7 | h |
| gauss | %1 | 990 | 411 | 113 | 192 | 252 | 0 | 22 | 0 | 0 | 52.9 | 5.3 | -11.9 | 406.0 | h |
| gauss | %1.5 | 990 | 295 | 102 | 192 | 391 | 0 | 10 | 0 | 0 | 40.1 | 6.4 | -11.9 | 431.2 | h |
| hma | %0.5 | 1431 | 1043 | 31 | 176 | 72 | 0 | 109 | 0 | 0 | 75.1 | 5.1 | -12.7 | 400.5 | h |
| hma | %1 | 1431 | 675 | 114 | 176 | 402 | 0 | 64 | 0 | 0 | 55.1 | 6.5 | -15.8 | 432.8 | h |
| hma | %1.5 | 1431 | 458 | 146 | 176 | 619 | 0 | 32 | 0 | 0 | 42.2 | 9.0 | -16.1 | 496.5 | h |
| 664 | %0.5 | 1810 | 1052 | 0 | 461 | 0 | 0 | 297 | 0 | 0 | 58.1 | 13.5 | -6.5 | 628.8 | h |
| 664 | %1 | 1810 | 832 | 37 | 461 | 259 | 0 | 221 | 0 | 0 | 48.0 | 17.8 | -8.4 | 783.2 | h |
| 664 | %1.5 | 1810 | 649 | 45 | 461 | 510 | 0 | 145 | 0 | 0 | 38.3 | 20.1 | -8.3 | 874.0 | h |
| 705 | %0.5 | 1069 | 700 | 0 | 182 | 0 | 0 | 187 | 0 | 0 | 65.5 | 13.6 | -8.0 | 634.0 | h |
| 705 | %1 | 1069 | 564 | 27 | 182 | 158 | 0 | 138 | 0 | 0 | 55.3 | 18.1 | -10.3 | 793.5 | h |
| 705 | %1.5 | 1069 | 441 | 33 | 182 | 327 | 0 | 86 | 0 | 0 | 44.3 | 20.2 | -8.9 | 882.4 | h |
| ewo | %0.5 | 1003 | 949 | 0 | 6 | 0 | 0 | 48 | 0 | 0 | 94.6 | 9.4 | -10.0 | 508.2 | h |
| ewo | %1 | 1003 | 839 | 49 | 6 | 70 | 3 | 25 | 11 | 0 | 88.5 | 14.3 | -16.0 | 655.5 | h |
| ewo | %1.5 | 1003 | 707 | 73 | 6 | 189 | 5 | 23 | 0 | 0 | 77.8 | 17.3 | -15.9 | 762.4 | h |
| e0v1en | %0.5 | 1899 | 1872 | 0 | 0 | 0 | 0 | 27 | 0 | 0 | 98.6 | 6.6 | -10.0 | 437.2 | h |
| e0v1en | %1 | 1899 | 1798 | 35 | 0 | 32 | 0 | 24 | 10 | 0 | 96.5 | 11.1 | -15.1 | 554.5 | h |
| e0v1en | %1.5 | 1899 | 1656 | 96 | 0 | 115 | 0 | 22 | 10 | 0 | 92.3 | 14.2 | -17.7 | 653.1 | h |
| 670 | %0.5 | 1443 | 0 | 0 | 1443 | 0 | 0 | 0 | 0 | 0 | 0.0 | 0.0 | 0.0 | 300.0 | h |
| 670 | %1 | 1443 | 0 | 0 | 1443 | 0 | 0 | 0 | 0 | 0 | 0.0 | 0.0 | 0.0 | 300.0 | h |
| 670 | %1.5 | 1443 | 0 | 0 | 1443 | 0 | 0 | 0 | 0 | 0 | 0.0 | 0.0 | 0.0 | 300.0 | h |
| 574 | %0.5 | 959 | 1 | 0 | 958 | 0 | 0 | 0 | 0 | 0 | 0.1 | 0.1 | 0.0 | 302.0 | h |
| 574 | %1 | 959 | 1 | 0 | 958 | 0 | 0 | 0 | 0 | 0 | 0.1 | 0.2 | 0.0 | 304.0 | h |
| 574 | %1.5 | 959 | 1 | 0 | 958 | 0 | 0 | 0 | 0 | 0 | 0.1 | 0.3 | 0.0 | 306.1 | h |
| BİRLEŞİK (5x300) | %0.5 | 7133 | 5600 | 49 | 835 | 105 | 0 | 544 | 0 | 0 | 79.2 | 8.5 | -3.1 | 2411.5 | strateji_kill=0 |
| BİRLEŞİK (5x300) | %1 | 7133 | 4555 | 348 | 835 | 1015 | 3 | 356 | 21 | 0 | 68.7 | 11.5 | -6.8 | 2832.0 | strateji_kill=0 |
| BİRLEŞİK (5x300) | %1.5 | 7133 | 3765 | 462 | 835 | 1824 | 5 | 232 | 10 | 0 | 59.3 | 13.9 | -7.4 | 3217.2 | strateji_kill=0 |

## Maliyet x2 (stres)
| Strateji | Risk | Sinyal | Tam | Kısaltılmış | Stop>%25 | Toplam risk %6 | Brüt/nominal | Gerçek min tutar | Günlük stop | Kill | Alınan % | CAGR % | Max DD % | Son USD | Kill |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| gauss | %0.5 | 990 | 679 | 21 | 192 | 36 | 0 | 62 | 0 | 0 | 70.7 | 6.0 | -5.8 | 421.1 | h |
| gauss | %1 | 990 | 408 | 115 | 192 | 253 | 0 | 22 | 0 | 0 | 52.8 | 4.2 | -14.4 | 380.7 | h |
| gauss | %1.5 | 990 | 300 | 95 | 192 | 393 | 0 | 10 | 0 | 0 | 39.9 | 5.3 | -14.5 | 406.6 | h |
| hma | %0.5 | 1431 | 1043 | 30 | 178 | 71 | 0 | 109 | 0 | 0 | 75.0 | 3.2 | -17.5 | 360.4 | h |
| hma | %1 | 1431 | 676 | 110 | 178 | 402 | 0 | 65 | 0 | 0 | 54.9 | 3.6 | -22.8 | 368.4 | h |
| hma | %1.5 | 1431 | 459 | 143 | 178 | 621 | 0 | 30 | 0 | 0 | 42.1 | 6.7 | -20.6 | 439.3 | h |
| 664 | %0.5 | 1810 | 1050 | 0 | 463 | 0 | 0 | 297 | 0 | 0 | 58.0 | 12.9 | -7.1 | 610.7 | h |
| 664 | %1 | 1810 | 831 | 36 | 463 | 259 | 0 | 221 | 0 | 0 | 47.9 | 16.7 | -9.3 | 741.4 | h |
| 664 | %1.5 | 1810 | 648 | 43 | 463 | 511 | 0 | 145 | 0 | 0 | 38.2 | 19.2 | -8.7 | 838.3 | h |
| 705 | %0.5 | 1069 | 699 | 0 | 183 | 0 | 0 | 187 | 0 | 0 | 65.4 | 13.3 | -8.6 | 622.4 | h |
| 705 | %1 | 1069 | 564 | 24 | 183 | 160 | 0 | 138 | 0 | 0 | 55.0 | 17.6 | -11.0 | 774.1 | h |
| 705 | %1.5 | 1069 | 440 | 35 | 183 | 324 | 0 | 87 | 0 | 0 | 44.4 | 19.7 | -9.9 | 857.5 | h |
| ewo | %0.5 | 1003 | 949 | 0 | 6 | 0 | 0 | 48 | 0 | 0 | 94.6 | 7.9 | -10.3 | 468.9 | h |
| ewo | %1 | 1003 | 839 | 49 | 6 | 70 | 3 | 25 | 11 | 0 | 88.5 | 12.0 | -16.9 | 583.4 | h |
| ewo | %1.5 | 1003 | 702 | 74 | 6 | 183 | 5 | 22 | 11 | 0 | 77.4 | 14.4 | -17.2 | 658.1 | h |
| e0v1en | %0.5 | 1899 | 1872 | 0 | 0 | 0 | 0 | 27 | 0 | 0 | 98.6 | 2.9 | -14.2 | 355.3 | h |
| e0v1en | %1 | 1899 | 1797 | 36 | 0 | 32 | 0 | 24 | 10 | 0 | 96.5 | 4.8 | -23.3 | 394.4 | h |
| e0v1en | %1.5 | 1899 | 1657 | 96 | 0 | 114 | 0 | 22 | 10 | 0 | 92.3 | 6.4 | -27.1 | 430.9 | h |
| 670 | %0.5 | 1443 | 0 | 0 | 1443 | 0 | 0 | 0 | 0 | 0 | 0.0 | 0.0 | 0.0 | 300.0 | h |
| 670 | %1 | 1443 | 0 | 0 | 1443 | 0 | 0 | 0 | 0 | 0 | 0.0 | 0.0 | 0.0 | 300.0 | h |
| 670 | %1.5 | 1443 | 0 | 0 | 1443 | 0 | 0 | 0 | 0 | 0 | 0.0 | 0.0 | 0.0 | 300.0 | h |
| 574 | %0.5 | 953 | 1 | 0 | 952 | 0 | 0 | 0 | 0 | 0 | 0.1 | 0.1 | 0.0 | 302.0 | h |
| 574 | %1 | 953 | 1 | 0 | 952 | 0 | 0 | 0 | 0 | 0 | 0.1 | 0.2 | 0.0 | 304.0 | h |
| 574 | %1.5 | 953 | 1 | 0 | 952 | 0 | 0 | 0 | 0 | 0 | 0.1 | 0.3 | 0.0 | 306.0 | h |
| BİRLEŞİK (5x300) | %0.5 | 7133 | 5593 | 51 | 839 | 107 | 0 | 543 | 0 | 0 | 79.1 | 6.9 | -3.3 | 2216.3 | strateji_kill=0 |
| BİRLEŞİK (5x300) | %1 | 7133 | 4551 | 346 | 839 | 1016 | 3 | 357 | 21 | 0 | 68.7 | 8.9 | -7.2 | 2468.2 | strateji_kill=0 |
| BİRLEŞİK (5x300) | %1.5 | 7133 | 3766 | 451 | 839 | 1822 | 5 | 229 | 21 | 0 | 59.1 | 11.1 | -8.1 | 2773.3 | strateji_kill=0 |

Not: Birleşik satırında "Alınan %" = (tam + kısaltılmış) / sinyal. "Kill" sütunu birleşikte kaç stratejinin kill'e girdiğini gösterir. Hesap kill (-%20 toplam) hiçbir senaryoda tetiklenmezdi; kural uygulanmadı, yalnız bakıldı.

## Hesap büyüklüğü duyarlılığı (x1, risk %1,5; her strateji tek başına, kasa tavanı = hesap)
| Strateji | Hesap USD | Alınan % | Kısaltılmış | Toplam risk | Gerçek min tutar | CAGR % | Max DD % |
|---|---|---|---|---|---|---|---|
| gauss | 300 | 40.1 | 102 | 391 | 10 | 6.4 | -11.9 |
| gauss | 600 | 41.4 | 134 | 381 | 7 | 6.5 | -11.3 |
| gauss | 1000 | 42.3 | 157 | 374 | 5 | 8.0 | -11.2 |
| gauss | 1500 | 44.3 | 183 | 357 | 2 | 7.7 | -11.1 |
| hma | 300 | 42.2 | 146 | 619 | 32 | 9.0 | -16.1 |
| hma | 600 | 43.3 | 175 | 608 | 28 | 9.2 | -16.1 |
| hma | 1000 | 45.1 | 207 | 594 | 16 | 8.4 | -17.1 |
| hma | 1500 | 46.7 | 233 | 582 | 5 | 7.6 | -16.2 |
| 664 | 300 | 38.3 | 45 | 510 | 145 | 20.1 | -8.3 |
| 664 | 600 | 40.8 | 93 | 499 | 111 | 20.0 | -8.4 |
| 664 | 1000 | 42.9 | 132 | 506 | 67 | 20.7 | -8.0 |
| 664 | 1500 | 45.3 | 167 | 511 | 18 | 21.1 | -8.6 |
| 705 | 300 | 44.3 | 33 | 327 | 86 | 20.2 | -8.9 |
| 705 | 600 | 45.9 | 56 | 325 | 71 | 22.3 | -7.8 |
| 705 | 1000 | 48.5 | 85 | 328 | 41 | 22.4 | -7.7 |
| 705 | 1500 | 51.8 | 113 | 328 | 5 | 21.8 | -8.0 |
| ewo | 300 | 77.8 | 73 | 189 | 23 | 17.3 | -15.9 |
| ewo | 600 | 79.2 | 85 | 195 | 3 | 17.1 | -15.9 |
| ewo | 1000 | 79.8 | 92 | 191 | 1 | 17.1 | -15.9 |
| ewo | 1500 | 80.1 | 95 | 189 | 0 | 17.1 | -16.3 |
| e0v1en | 300 | 92.3 | 96 | 115 | 22 | 14.2 | -17.7 |
| e0v1en | 600 | 92.8 | 98 | 126 | 0 | 14.8 | -17.5 |
| e0v1en | 1000 | 93.1 | 103 | 121 | 0 | 14.9 | -17.4 |
| e0v1en | 1500 | 93.2 | 105 | 120 | 0 | 14.9 | -17.4 |

Okuma: gerçek min tutar atlamaları hesap büyüdükçe düşer; toplam risk bütçesi atlamaları/kısaltmaları ise oransaldır ve hesap büyüklüğünden bağımsız kalır (bütçe de hesapla ölçeklenir). Yani hesabı büyütmek min tutar sorununu çözer, %6 bütçe sınırını çözmez.

## Bulgu (lider için, canlı kod değiştirilmedi)
Canlı yürütücü, toplam risk bütçesinin bıraktığı kırıntı adım/min tutarın altında kalınca bunu `min_tutar_alti` olayı olarak kaydeder (canli_limitler.py `miktar_hesapla` sonundaki min_tutar_alti dalı; yürütücü bunu `tur = "min_tutar_alti"` ile loglar). Oysa gerçek sebep toplam risk (veya brüt) bütçesidir; `baglayan` alanı bunu söyler. Olay günlüğü ve panoda bu atlamalar yanıltıcı görünür. Bu raporda `baglayan`'a göre doğru etiketlendi.

## Sınırlamalar
1. Borsa filtreleri depoda yok. Varsayım: min tutar BTC 100, ETH 20, diğerleri 5 USD (DK_* semboller de 5 USD, kesirli adım); adım BTC/ETH 0,001, diğerleri kaba. Gerçek exchangeInfo ile gerçek min tutar sayıları değişir. DK_* sembollerinin canlıda hangi borsada olacağı ayrı soru (gauss ve hma sinyallerinin bir kısmı DK_*).
2. Giriş fiyatı = stop_mesafe / sf; pnl = adet x stop_mesafe x r (r maliyet+fonlama sonrası net R). Boyutlandırma maliyeti yürütücü varsayılanı (stop_kayma %0,05 + taker %0,05).
3. Kasa 300'de tavanlı (canlı kural): kâr boyutu büyütmez, bu yüzden CAGR bileşik backtest'ten düşük; "Max DD %" büyüyen özsermaye zirvesine göre.
4. Özsermaye yalnız gerçekleşmiş pnl (MTM yok); günlük/kill bu seriye göre. Canlıda MTM daha erken tetikleyebilir. Açık risk girişteki stop mesafesiyle sayılır (canlıda mark ile; kâra geçmiş pozisyon canlıda daha az risk tüketir, replay biraz tutucu).
5. Kill sonrası açık işlemler kendi çıkışına kadar sürer; gerçekte kill hepsini kapatır.
6. Aynı sembolde açık pozisyon varsa giriş atlanır (canlı davranışı); bu sayı 0 çıktı.
7. Sinyal gecikmesi, dolum kayması ve emir hataları yok. Sonradan seçilmiş stratejiler, tarihsel sonuç; kanıt değil.
