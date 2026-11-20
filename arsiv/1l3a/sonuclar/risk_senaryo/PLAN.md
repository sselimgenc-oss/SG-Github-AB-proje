# Risk senaryosu planı (sonuç görülmeden önce sabitlendi)

Soru: Aynı 20 paper stratejisinin AYNI işlemleri, yalnız pozisyon büyüklüğü değişirse ne olur?

## Dönem ve veri
- Yalnız geliştirme dönemi (veri 2025-11-07 dahil'e kadar; `veri_oku` holdout'ta HoldoutSizintisi fırlatır). Kilitli yıl açılmaz, kilit_ac kullanılmaz.
- Ana pencere: **2020-01-01 -> 2025-11-07** (tüm hesaplar için ortak; öncesindeki işlemler analiz dışı). Her hesap 2020-01-01'de 10.000 ile başlar.

## Stratejiler
- `stratejiler/paper_v2_seti.json` içindeki 20 kayıt. 10 v2 stratejisi (varsayılan ayar, evren havuz_v2.csv: genel=35 / kripto=13), 10 kapanış (`kapanis_kosu_listesi.strateji_kur`, dondurulmuş liste, kripto13).
- Her strateji kendi hesabında, evrenindeki tüm sembollerin işlemleri tek hesapta (paper ile aynı).
- `pf__sabit_sepet` portföy stratejisidir (işlem listesi yok, günlük getiri serisi): A/B/C ve baz için getiri x s (s = f / %1; paper mantığı), D (tam kasa) YOK (stop mesafesi tanımsız; tahmin edilmez).
- Her strateji mevcut ayarıyla bir kez koşulur; maliyet x1 ana, x2 stres. İşlem R'si maliyet+funding sonrası net R'dir (kaynak: v2 `islem_hazirla`).

## Senaryolar (aynı işlemler, yalnız boyut)
- Baz: f = %0,5 (mevcut paper). A: %1,5. B: %3. C: %5. pnl = f x giriş anındaki özsermaye x R.
- D "tam kasa": notional = giriş anındaki özsermaye (eşzamanlı işlemler her biri tam kasa kullanır = kaldıraç); pnl = notional x R x sf (sf = stop mesafesi / giriş fiyatı, `sf` sütunu). sf'siz strateji için atlanır.
- Özsermaye yalnız gerçekleşmiş (çıkış anında işlenir; MTM yok). Boyut giriş anındaki gerçekleşmiş özsermayeden.
- Özsermaye 0'ın altına inemez (D'de tek işlem %100'den fazla kaybedebilir -> hesap 0, iflas).

## Kill kuralı
- Gerçekleşmiş özsermaye zirvesinden %-30'a düşünce hesap yeni işlem açmaz (kill tarihi raporlanır; kill anında açık işlemler kendi çıkışına kadar sürer). Kill'siz varyant da raporlanır.
- SERT_LIMITLER (günlük %3, 3x kaldıraç, %20 kill) simüle EDİLMEZ; bu saf yeniden-boyutlandırma. Azami eşzamanlı kaldıraç (toplam notional / özsermaye) her senaryoda raporlanır.

## Metrikler
Strateji x senaryo: toplam getiri, CAGR, aylık ortalama getiri, aylık medyan, en kötü ay, zararlı ay %, azami düşüş (max DD), kill (e/h, tarih), yıllık getiri tablosu, azami kaldıraç. 20 hesaplı birleşik portföy (hesapların toplamı, her biri 10k) ve ≥ %4/ay ortalamaya ulaşan strateji sayısı (ve onların düşüşü) her senaryo için.

## Durdurma / dürüstlük
- Optimizasyon, parametre değişikliği, yeni strateji mantığı yok. Sonuç görüldükten sonra senaryo/metrik değişmez.
- Yeniden üretilemeyen strateji nedeniyle raporda belirtilir. Sonuçlar tarihsel ve sonradan seçilmiş stratejiler üzerindedir; kanıt değildir.
