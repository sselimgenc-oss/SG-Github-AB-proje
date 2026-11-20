# Canlı oynatma, 300 USD hesap (plan; sonuç görülmeden yazıldı)

Soru: Her odak strateji 300 USD ile CANLI limitlerle koşsaydı sinyallerinin kaçı alınırdı, getiri ve düşüş ne olurdu?

## Veri
- `sonuclar/risk_senaryo/islemler/<id>__x1|x2.parquet` (ham işlem listesi). Pencere 2020-01-01 -> 2025-11-07; çıkışı tam 2025-11-08 00:00 olan (zorunlu kapanış) işlemler hariç (araclar/risk_senaryo.py ile aynı).
- Stratejiler: dis__gauss-stoch-eth, dis__hma-atr-rider, HAM:X005:664#v1, HAM:X005:705, dis__ewo-ema-ofset, dis__e0v1en; teyit için 670 ve 574 (beklenti: stop tavanı yüzünden hepsi atlanır).
- Kilitli veri açılmaz; sonuclar/ altında toplu arama yapılmaz.

## Boyutlandırma (gerçek kod, yeniden yazılmadı)
- `motor.canli.borsa.kurallar.boyutlandir` -> `canli_limitler.miktar_hesapla` + `limit_ihlalleri`. kasa = min(özsermaye, 300). Model maliyeti yürütücünün varsayılanı: stop_kayma 0,0005, taker 0,0005.
- Giriş fiyatı = stop_mesafe / sf; stop = giriş -/+ yon x stop_mesafe. Gerçekleşen pnl = qty x stop_mesafe x r (r maliyet+fonlama sonrası net R; x2 senaryosunda x2 dosyasının r'si).
- Borsa filtreleri: depoda exchangeInfo görüntüsü YOK. Varsayım: min tutar BTC 100, ETH 20, diğer 5 USD (DK_* sembolleri de 5 USD); adım BTC/ETH 0,001, diğerleri fiyata göre kaba (belgelenir). Min miktar = adım.
- Risk senaryoları (işlem başı): %0,5, %1,0, %1,5 (kod bugün yalnız %1,5 kabul eder; diğerleri bilgi amaçlı). Maliyet x1 ana, x2 stres.

## Olay sırası ve kurallar
- Zaman sıralı; aynı anda çıkış girişten önce. Eşzamanlı pozisyonlar çıkana kadar toplam stop riski ve brüt nominali tüketir (diger_stop_riski, diger_brut).
- Gerçekleşmiş pnl çıkışta işlenir. Başlangıç 300 USD.
- Aynı sembolde açık pozisyon varsa giriş atlanır (yürütücü davranışı; "diğer").
- Günlük -%6 (UTC gün) ve strateji kill -%30: `gunluk_kill_guncelle`. Kill sonrası yeni giriş yok; açık işlemler kendi çıkışına kadar sürer (gerçekte kill hepsini kapatır; fiyat yolu olmadığı için yaklaşık).
- Atlama nedenleri: stop_cok_uzak, toplam_risk (risk_butcesi_dolu), min_tutar, gunluk_stop, kill, diger.
- "Tam" = boyut, diğer pozisyonlar olmasaydı hesaplanacak boyuta eşit; "kısaltılmış" = toplam risk/brüt bütçesi yüzünden daha küçük.

## Metrikler
Sinyal, tam, kısaltılmış, atlama nedenleri, alınan %, CAGR (5,85 yıl), azami düşüş (gerçekleşmiş özsermaye üzerinden), son özsermaye, kill e/h. Birleşik görünüm: ewo+e0v1en+gauss+hma+664, her biri 300 (toplam 1500); hesap kill (-%20) uygulanmaz, yalnız tetiklenip tetiklenmeyeceği raporlanır.

## Dürüstlük
Seçim sonradan yapılmış stratejiler, tarihsel; kanıt değil. Parametre/sonuç görüldükten sonra değişmez.
