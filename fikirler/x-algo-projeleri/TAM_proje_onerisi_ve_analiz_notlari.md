# Proje Önerisi: Algoritmik Trading Araştırma ve Paper-Trading Platformu

Tarih: 21.11.2026
Dayanak: İki ekran videosu (MT5 + EA paneli, Quantum v5), TradesSenceAI ekran görüntüleri ve X'teki paylaşımlar.
Not: Bu belge bir yazılım proje önerisidir. Yatırım tavsiyesi değildir ve kâr vaadi içermez.


## 1. Amaç

İncelenen üç programın güçlü yanlarını tek bir sistemde birleştirmek, ama hepsinde eksik görünen şeyi en başa koymak: **istatistiksel olarak doğrulanmış bir avantaj olmadan gerçek parayla işlem yapmamak.**

Hedef bir "kâr makinesi" değil, şunları yapan bir **araştırma platformu**:

1. Stratejileri maliyet dahil, sızıntısız ve tekrarlanabilir şekilde test eder.
2. Doğrulanan stratejileri önce paper trading'de, sonra (isteğe bağlı) küçük sermayeyle canlıda çalıştırır.
3. Tüm sonuçları dürüstçe raporlar: ortalama R, güven aralığı, drawdown, işlem sayısı.

## 2. Referans analizden çıkan dersler

| Kaynak | Güçlü yanı | Zayıf yanı / ders |
| --- | --- | --- |
| MT5 + EA paneli | Birden çok sistemi tek panelde izleme (Net, ClosedDD, EquityDD, slippage), canlı test banner'ı | Ekran görüntüsü kanıt değil; birim ve maliyet dahil mi belirsiz; 3 aylık test sürüyor |
| Quantum v5 | Modüler ekranlar (ML, emirler, rapor, strateji kurucu, laboratuvar), kill switch, Parquet veri gölü, strateji kütüphanesi | Paper trading'de 8 işlemde %0 win rate (−$52,99); backtest formu var, sonuç yok; çok kısa çalışma |
| TradesSenceAI | Kendi geçmiş istatistiğini (ortalama R, n, %95 aralık) gösteriyor, "geçmişte anlamlı negatif" diyebiliyor | Sinyaller ortalama negatif (−0,10R ile −0,43R); referral/DM yönlendirmesi; analiz listesi ile öneri sistemi tutarsız görünüyor |
| Diğer ajanın notu | Strateji Kurucu, Walk-Forward, ML ayarları gibi ayrıntıları yakalamış | Küçük okuma hataları (System 2, 6 strateji) |

**Ana ders:** Arayüz kolay, istatistiksel doğrulama zor. Proje bütçesinin büyük kısmı doğrulama altyapısına gitmeli.

## 3. Tweetlerden çıkan fikirler (sıralı)

Kaynak A: @soligann "Hedge Fund Cockpit" paylaşımı. Kaynak B: "Quantbot" paylaşımı (yazarı belli değil). Kaynak C: B'ye gelen bir yanıt. Bunlar yazarların kendi beyanıdır, bağımsız doğrulanmadı.

| # | Fikir | Kaynak |
| -- | ------------------------------------ | ------- |
| 1 | Event-driven (olay güdümlü) Python altyapısı; `while True` döngüleri yerine olay akışı | A |
| 2 | ML motoru sinyal üretmek yerine riski yönetsin: teknik sinyal ML tarafından reddedilebilsin (örnek: ETH LONG sinyali "%78 düşüş ihtimali" ile veto) | A |
| 3 | Kendi kendini onaran veri gölü: Parquet + SQLite, PyArrow, Snappy; boşluk veya bozuk dosyada eksik mumları REST'ten tamamlama | A |
| 4 | Asenkron pub/sub; Binance WebSocket ile saniyelik veri; kopunca 5 saniyede otomatik yeniden bağlanma, veri kaybı sıfır | A |
| 5 | Bloomberg tarzı karanlık panel; üstte kayan canlı PnL, drawdown, ML güven skoru, API limit durumu | A |
| 6 | Her şeyi anında kapatıp sistemi durduran büyük Kill Switch | A |
| 7 | Risk yönetimi ve Walk-Forward Optimization yaklaşımlarını toplulukla tartışma | A |
| 8 | GPU destekli makine öğrenmesi | B |
| 9 | Meta-labeling ve triple-barrier labeling | B |
| 10 | Otomatik tarihsel veri toplama | B |
| 11 | Purged walk-forward cross-validation | B |
| 12 | Monte Carlo simülasyonu | B |
| 13 | Veri sızıntısı ve overfitting kontrolleri | B |
| 14 | İşlem maliyetlerini hesaba katan backtesting | B |
| 15 | Prop firmalara özel risk yönetimi (günlük kayıp, toplam drawdown limitleri) | B |
| 16 | Otomatik MT5 ve Binance entegrasyonu | B |
| 17 | Otomatik yazılım testleri (yazar 555 test sayıyor) | B |
| 18 | Dürüstlük ilkesi: altyapı hazır olsa bile avantaj kanıtlanmadan "çalışıyor" denmemeli (yazar kendi durumunu böyle anlatıyor) | B |
| 19 | Botu doğrudan prop firmaya bağlamak yerine TradingView alarmı veya Telegram sinyaliyle bildirim almak | C |
| 20 | Kriptoda hacimli majör paritelerle (BTC, ETH, SOL) çalışmak; daha az gürültülü hareket | C |
| 21 | Forex/emtia tarafında altın, gümüş, EURUSD, USDCAD, petrol, US100 gibi likit enstrümanlar | C |
| 22 | Range odaklı yaklaşım: haftalık/aylık range, arz-talep bölgesinden tepki sonrası karakter değişimi | C |

Bu fikirlere ek olarak TradesSenceAI'dan alınan iki fikir:

| # | Fikir | Kaynak |
| -- | ------------------------------------ | ------- |
| 23 | Her sinyalin yanında geçmiş performansı göster: ortalama net R, n, %95 aralık, maliyet sonrası kârla kapanma oranı | TradesSenceAI |
| 24 | Performans bozulunca ilgili yöndeki yeni önerileri otomatik durdur ve nedenini yaz | TradesSenceAI |

## 4. Önerilen proje: "Çalışma Adı: Kokpit"

### 4.1 Modüller

1. **Veri katmanı:** Parquet veri gölü, otomatik gap tespiti ve onarım, WebSocket + REST, sürümlü veri setleri (fikir 3, 4, 10).
2. **Strateji katmanı:** Kütüphane + kural kurucu (VE/VEYA koşulları), her strateji için parametre dosyası ve sürüm (Quantum v5 Strateji Kurucu fikri).
3. **ML katmanı:** Triple-barrier etiketleme, meta-labeling, XGBoost/RF ensemble; ML'in rolü sinyali filtrelemek/veto etmek (fikir 2, 9).
4. **Backtest ve doğrulama motoru:** Maliyet dahil, purged walk-forward CV, Monte Carlo, sızıntı testleri (fikir 11–14).
5. **Çalıştırma katmanı:** Event-driven motor, paper trading, kill switch, risk limitleri (fikir 1, 4, 6).
6. **Raporlama ve panel:** Strateji bazında R-multiple, güven aralığı, drawdown, işlem listesi; canlı ticker (fikir 5, 23).
7. **Bildirim katmanı:** Telegram ve TradingView alarm entegrasyonu; ilk aşamada emir gönderimi yok (fikir 19).
8. **Test ve izleme:** Birim testleri, entegrasyon testleri, log ve alarm (fikir 17).

### 4.2 Mimari özet

```
Veri kaynakları (Binance WS/REST, MT5, CSV)
        |
   [Olay veri yolu (pub/sub)]
        |
  Veri gölü (Parquet + SQLite) <---> Gap onarımı
        |
  Strateji motoru --> ML veto/filtre --> Risk motoru --> Emir katmanı (paper / canlı)
        |                                   |
   Backtest & doğrulama                 Kill switch
        |
  Raporlama paneli + Telegram bildirimleri
```

### 4.3 Teknoloji önerisi

- Python 3.11+, `asyncio`, PyArrow/Parquet, SQLite, pandas veya Polars.
- ML: scikit-learn, XGBoost; GPU gerekiyorsa ikinci faza bırakılır.
- Panel: küçük bir web arayüzü (ör. FastAPI + basit frontend). İlk sürümde tek sayfa yeterli.
- Test: pytest. CI: her değişiklikte testler ve temel backtest çalışsın.

## 5. Özellik planı

### MVP (Faz 1)

- Veri indirme ve gap onarımı (1–2 borsa, 3–5 likit sembol).
- 2–3 basit strateji + kural kurucu.
- Maliyetli backtest (komisyon + slippage varsayımı).
- Sonuç raporu: ortalama R, n, %95 aralık, win rate, profit factor, max drawdown.
- Kill switch ve günlük/toplam kayıp limiti (paper).

### Faz 2

- Triple-barrier etiketleme ve meta-labeling modeli.
- Purged walk-forward CV ve Monte Carlo.
- Veri sızıntısı ve overfitting kontrol listesi (otomatik).
- Paper trading motoru, canlı panel, Telegram bildirimi.

### Faz 3

- Performans bozulunca otomatik "öneri durdurma" mantığı (fikir 24).
- Çoklu piyasa (kripto + forex/emtia) ve prop firma kuralı şablonları.
- İsteğe bağlı: MT5 köprüsü, küçük sermayeyle canlı pilot.

## 6. Doğrulama ve kabul kriterleri

Bir strateji canlıya (paper dışında) ancak şunları sağlarsa geçer:

1. En az **N işlem** (öneri: 300+) ve en az 2 farklı piyasa rejimini kapsayan test dönemi.
2. Maliyet sonrası ortalama R > 0 ve **%95 güven aralığının alt sınırı > 0**.
3. Purged walk-forward'da tutarlı sonuç; tek bir dönemde toplanan kâr yok.
4. Monte Carlo'da ruin olasılığı belirlenen eşiğin altında.
5. Sızıntı testlerinden geçmiş (etiketleme, özellik, zaman sırası).
6. En az 4–8 hafta paper trading; paper sonucu backtest beklentisiyle tutarlı.
7. Kill switch ve limitler test edilmiş.

Bu kriterleri sağlamayan strateji "araştırma" olarak kalır. İncelenen programlarda (Quantum v5 paper sonucu, TradesSenceAI geçmiş istatistiği) bu eşiklerin karşılanmadığı görülüyor.

## 7. Yol haritası (öneri)

| Faz | Süre (tahmini) | Çıktı | Çıkış kriteri |
| ------ | ----- | ---------- | ---------- |
| 0. Hazırlık | 1 hafta | Gereksinimler, veri kaynağı ve borsa seçimi | Kapsam onayı |
| 1. MVP | 4–6 hafta | Veri gölü, backtest, rapor, kill switch | Tekrarlanabilir rapor |
| 2. Doğrulama + ML | 6–8 hafta | Purged WF, Monte Carlo, meta-labeling, paper motoru | Bölüm 6'daki 1–5 |
| 3. Paper pilot | 4–8 hafta | Canlı panel, bildirimler, paper sonuçlar | Bölüm 6'daki 6–7 |
| 4. Karar | 1 hafta | Devam / strateji değiştir / durdur kararı | Dürüst değerlendirme |

Süreler tek geliştirici için kaba tahmindir.

## 8. Riskler ve notlar

- **Avantaj bulunamayabilir.** Quantbot yazarı da bunu açıkça söylüyor. Proje bu sonucu da başarılı bir çıktı sayar.
- **Overfitting ve sızıntı** en büyük teknik risk. Doğrulama modülü bu yüzden önceliklidir.
- **Kaldıraç:** Yüksek kaldıraç (5–20x gibi seçenekler) likidasyon riskini artırır. İlk aşamada kaldıraç 1x ile sınırlı tutulur.
- **API anahtarları:** Gerçek anahtarlar kod deposuna veya ekran kaydına girmemeli; yalnızca okuma/izin kısıtlı anahtarlar kullanılmalı.
- **Prop firma kuralları:** Bot kullanımına izin her firmada farklıdır; tek bir kişinin deneyimine güvenilmemeli, firmanın kendi şartları okunmalı (fikir 19 ve C yanıtı).
- **Yönlendirme (referral) düzenleri:** TradesSenceAI duyurusundaki gibi borsa üyeliği/para yatırma yönlendirmeleri projenin parçası olmamalı.
- **Yasal:** Başkalarına sinyal/analiz sunmak veya para yönetmek yerel düzenlemelere tabi olabilir; kişisel araştırma amacı dışına çıkılırsa uzmana danışılmalı.
- **Telif/ticari:** Kaynak programların arayüzleri veya kodları kopyalanmamalı; yalnızca genel fikirler referans alınmalı.

## 9. Açık sorular

1. Hedef piyasa: kripto, altın/forex veya her ikisi?
2. Amaç: kişisel araştırma mı, prop firma değerlendirmesi mi, başkalarına sunulacak bir ürün mü?
3. Platform: yalnızca Binance mı, MT5 de gerekli mi?
4. Bütçe ve süre: tek geliştirici mi, ekip mi?
5. ML için GPU gerçekten gerekli mi, yoksa ilk sürümde CPU yeterli mi?

## 10. Ekler

- **Ek A:** MetaTrader 5 + EA paneli analizi (video 1)
- **Ek B:** Quantum v5 analizi (video 2 ve X'ten gelen ekran görüntüleri)
- **Ek C:** TradesSenceAI analizi (ekran görüntüleri)
- **Ek D:** X paylaşımları (ayrıntılı)
- **Ek E:** Diğer ajanın PDF notu ve farklar
- **Ek F:** Gönderilen 29 fotoğrafın envanteri
- **Ek G:** Doğrulanamayan noktalar


---

# EKLER: Analiz Notları

Kaynak: 2 ekran videosu, 29 ekran görüntüsü, başka bir ajanın PDF notu. Yalnızca ekranda görülenler yazıldı; doğrulanamayanlar Ek G'de.

## Ek A. MetaTrader 5 + EA paneli (video 1, 25 sn)

- **Platform:** MT5, Pepperstone hesabı, XAUUSD M1 grafiği. Videonun sonunda H1 ve H4'e geçiliyor; geçmiş işlemler grafikte işaretçi olarak görünüyor.
- **Grafik üstündeki EA paneli:** İki sistem ayrı satırlarda izleniyor: **System 1** ve **System 3** (yakın kırpmada doğrulandı).
  - Sütunlar: Net, ClosedDD, EquityDD, Closes, Slip-/+, Measured, SlipNet.
  - System 1: Net 2421,95 · ClosedDD 704,70 · EquityDD 703,58 · Closes 136 · Measured 272/272.
  - System 3: Net 1078,62 · ClosedDD 834,21 · EquityDD 884,32 · Closes 96 · Measured 192/192.
  - Slippage 0/0, SlipNet 0,00. Net değerlerin para birimi ekranda yazmıyor.
- **History sekmesi:** 20 Ekim – 20 Kasım arası xauusd işlemleri. Alış ve satış karışık, lot 0,17–0,6 arası. Her işlemde S/L, T/P ve komisyon sütunu var. Aynı anda açılıp kapanan çift emirler iki sistemin işlemleri olabilir.
- **Sonuçlar:** Çoğu işlem küçük kârlı (yaklaşık +10 ile +130). Zaman zaman büyük zararlar var (yaklaşık −281 ve −395).
- **Alt banner:** "NOT FINANCIAL ADVICE • FOR EDUCATIONAL PURPOSES ONLY • Systems are under real market testings for 3 months to see results. 2nd phase begin at 21th October".
- **Diğer ayrıntılar:** Terminalde "Algo Trading" düğmesi, Market Watch, Navigator, bellek göstergesi (574/125 Mb) görünüyor.

## Ek B. Quantum v5 (video 2, 2 dk 16 sn, localhost:3000)

**Genel yapı.** Türkçe, koyu temalı panel. Üst çubuk: PnL/DD, ML Confidence (%50), API rate, sistem WebSocket gecikmesi (~45 ms) ve kırmızı KILL SWITCH. Altta AI Kernel Logs terminali ("Neural network initialized", "Data Lake connected via Parquet", "Waiting for market signals", pozisyon kapanış kayıtları). Sol menü: Terminal, ML Motoru, Emirler, Geçmiş, Raporlar, Strateji Kurucu, Kütüphane, Ayarlar, Laboratuvar.

### B.1 ML Motoru

- XGBoost modelini Triple Barrier Method ile eğitiyor.
- Girdiler: sembol, zaman dilimi, mum sayısı (5000), TP çarpanı (2,0), SL çarpanı (2,0), "Modeli Eğit" düğmesi.
- "Eğitilmiş Modeller (Ensemble)" tablosu: tarih, sembol, TF (1m/5m/15m), veri seti büyüklüğü, özellik sayısı, Precision/Recall/F1, XGB/RF/birleşik doğruluk. Precision yaklaşık %27–38, doğruluk yaklaşık %40–45.
- "Yenile" ve "Geçmişi Temizle" düğmeleri.
- Altta "Strateji Karar Merkezi" (yapay zekâ ve teknik stratejilerin karşılaştırılması) ve "Görsel Karar Simülasyonu" (GERÇEK AL/SAT, işlem kapanışı, ML sinyali, strateji sinyali göstergeleri; "Simülasyonu Başlat").
- Not: "Ensemble Learning: XGBoost + Random Forest modellerinin ortak kararı (Soft Voting)".

### B.2 Emirler

- 7 aktif strateji kartı: BNB (trend_master), BTC (adaptive_koncorde), DOGE (golden_combo), ETH (divergence_hunter), LINK (knn_quant_atr), SOL (custom_smartmoney), XRP (adaptive_koncorde). Her kartta timeframe (1m), PnL, işlem sayısı, Durdur ve Sil düğmeleri.
- Paper Trading – Canlı Performans: bakiye ≈ $9940, equity ≈ $9940,78, win rate %0,0, işlem 11/11, PnL ≈ −$60, komisyon $4,29.
- Açık pozisyon: trend_master SHORT BNB/USDT, miktar ≈ 1,5098, giriş ≈ $645,60, anlık +$0,70; SL/TP/likidasyon seviyeleri ve "Kapat" düğmesi.
- Sermaye kullanımı: kullanılan marjin ≈ $974,71, kullanılabilir bakiye ≈ $8965,29, toplam pozisyon değeri ≈ $973,99, ortalama kaldıraç 1,0x.

### B.3 Geçmiş (işlem geçmişi)

- Özet kartları: toplam işlem 8, win rate %0,0, toplam kâr/zarar −$52,99, ortalama işlem −$6,62, en iyi strateji golden_combo.
- Detaylı işlem listesi: tarih, parite, strateji, yön, giriş fiyatı, çıkış fiyatı, miktar/kaldıraç, PnL ($ ve %), neden.
- Görünen işlemlerin hepsi SHORT, çıkış nedeni STOP LOSS, kaldıraç 1x, tarih 25.03.2026 (yaklaşık 18:33–18:36).

### B.4 Raporlar ("Röntgen")

- Strateji bazında toplam PnL (golden_combo ≈ −$18,90, trend_master ≈ −$41,10), win rate, profit factor, brüt kâr/zarar, max drawdown, parite kırılımı.
- Otomatik "KRİTİK" uyarısı: düşük başarı oranı (%0) ve zayıf kâr faktörü (0,00); stop-loss seviyesi hatalı veya işlem yapılan pariteler bu botun tarzına uymuyor; acil parametre optimizasyonu gerekli.
- "Raporu Güncelle" düğmesi.

### B.5 Strateji Kurucu

- **Gösterge Kütüphanesi:** Trend (EMA 20, SMA 20, Supertrend), Momentum (RSI 14, MACD), Volatilite (ATR 14, Bollinger), arama kutusu.
- **Koşul Oluşturucu:** Strateji adı, açıklama, LONG ve SHORT koşulları, VE (AND) / VEYA (OR) seçimi, gösterge/operatör/değer satırları.
- **Backtest & Risk:** sembol (BTC/USDT), zaman dilimi (1h), gün sayısı (30), bakiye (10000), SL (ATR) 2,0, TP (ATR) 4,0, max risk %2,0; "Backtest Başlat", "Stratejiyi Kaydet", "Temizle".
- Videoda backtest çalıştırılıp sonuç gösterilmiyor.

### B.6 Kütüphane (7 strateji)

| Strateji | Mantık |
| --- | --- |
| TrendMaster Pro | SMA20, EMA200 ve RSI50 ile 1 dakikalık trend takibi |
| Scalper Ninja | Aşırı satım (RSI<30, Stoch<20) dip avcılığı |
| Adaptive Koncorde X | Kalman filtresi, Koncorde ve BTC volatilitesine göre uyum |
| Golden Combo | ADX, MACD, EMA ve OBV birleşimi |
| Divergence Hunter | Uyumsuzluk avcısı (ADX, PSAR, Ultimate Oscillator) |
| KNN Quant ATR Shield | KNN tahmini ve ATR koruması |
| Smart Money | RSI, MACD ve OBV konfluansı |

Her strateji için LONG/SHORT koşul kutuları, "Bu Stratejiyi Kullan" ve "Düzenle" düğmeleri var; koşullar "tanımlanmamış" görünüyor.

### B.7 Ayarlar ve Bot Yönetimi

- **Bot Başlatma Merkezi:** sembol (BNB, BTC, DOGE, ETH, LINK, SOL, XRP), strateji (7 seçenek), timeframe, market (Futures/Swap), marjin tipi (Isolated). Not: botu başlatmadan önce sembol ve strateji seçilmeli; tüm işlemler paper trading olarak yapılıyor.
- **Aktif Botlar:** her bot için durum, PnL, işlem sayısı, Durdur ve Sil.
- **Risk Ayarları:** maksimum risk (1,5; etiket 0,1–5,0), maksimum kaldıraç (50 okundu; etiket küçük, bkz. Ek G), maksimum pozisyon, ardışık kayıp limiti, Kill Switch aktif kutusu ve "Risk Yönetimi" notu.
- **Bot Yapılandırması:** borsa Binance, ortam Development, log seviyesi INFO.
- **Üst zaman dilimi filtresi:** EMA Stack (EMA 20 vs EMA 50); örnek not: 1m bot, 15m (minor) → 1h (major).
- **Kalman Filtresi (Denoising):** aktif kutusu, process noise 0,001, measurement noise 0,1; "Kalman Ayarlarını Kaydet" ve "Varsayılana Dön".
- **Re-optimizasyon:** 24–720 saat aralığı, değer 168 (1 hafta, önerilen).
- **ML Model Ayarları:** "ML Model Aktif (XGBoost + Random Forest Ensemble)" kutusu, Confidence Threshold (0,50–0,95; ekranda 0,4 yazılı, ≥%65 güven uyarısı notu).

### B.8 Laboratuvar (Veri Laboratuvarı ve Geçmiş Veri İndirme)

- 3 adım: Piyasa Seçimi (arama; spot, süresiz vadeli ve tarihli vadeli semboller), İndirme Kontrolü (seçili sembol, Parquet Data Lake mimarisi, başlangıç 01.01.2025, 1m otomatik, "İndirmeyi Başlat", "Tüm Verileri Sil"), Aktif ve Geçmiş Görevler (ilerleme çubukları, TAMAMLANDI durumları).
- **Veritabanı Envanteri ve İstatistikler:** toplam 4,52 milyon mum, 7 farklı sembol/zaman dilimi kombinasyonu; her biri yaklaşık 646K mum, 2025-01-01 – 2026-03-25.

### B.9 Yazarın anlatımı (X paylaşımı, @soligann)
Bunlar yazarın kendi beyanı, ayrıca doğrulanmadı. Ayrıntısı Ek D'de.

## Ek C. TradesSenceAI (Telegram mini uygulaması, 15 ekran görüntüsü)

Bot değil, analiz ve sinyal paneli. Pro üyelik süresi ekranda görünüyor.

- **Piyasalar:** Kripto, BIST, Forex, Hisse, Emtia. BIST fiyatları ~15 dk gecikmeli. Formasyon motoru 7/24 tarıyor.
- **Formasyonlar:** Fair Value Gap, Order Block, Fibonacci Deviation (likidite raid), Çift Dip/Tepe, Price Action Dönüş (pin bar, engulfing).
- **Analizler sekmesi:**
  - Her kartta sembol, formasyon, zaman dilimi, yön (LONG/SHORT), "Kriter x/12" skoru, giriş/stop/hedef ve konum çubuğu.
  - Durum etiketleri: "Fiyat seviyeden uzaklaştı", "Fiyat formasyon seviyesinde"; sıra değişimi ("1 sıra yükseldi").
  - Kart açılınca grafik, "Neden bu analiz?" listesi (ek formasyonlar, BTC trendiyle uyum, OI değişimi, onay kırılımı) ve geçmiş performans bölümü çıkıyor.
  - Ekranda 17 analizin 16'sı, bir başka anda 15 analizin 14'ü SHORT ("yoğun" uyarısı).
  - Örnekler: SEIUSDT, ORDIUSDT (4s Fair Value Gap, giriş 2,544, stop 2,6357, hedef 2,289), DOGEUSDT; BIST: GMTAS, AVGYO.
- **Geçmiş performans (uygulamanın kendi verisi):**
  - Fair Value Gap (4s) kurulumu: ortalama net sonuç −0,10R, n=7675, %95 aralık −0,15R…−0,05R, maliyet sonrası kârla kapanan %59, kazanınca +0,39R, kaybedince −0,80R. Dönem: Eylül 2024 – Ağustos 2026, 37 kripto. Uygulama bunu "geçmişte anlamlı şekilde negatif" diye yazıyor.
  - Kripto panosuna çıkan sinyaller (tüm zaman dilimleri): ortalama −0,43R (n=679). Formasyonların yalnızca %44'ü maliyet sonrası kârla kapanmış (6,2 bin sonuçlanan işlem).
  - BIST örneği GMTAS (Fibonacci Deviation, 1 gün): giriş 43,6243, stop 42,5618, hedef 55,5151, risk/ödül 10,19, geçmişte ortalama +0,45R (n=256), %53 kârla kapanan, girişi dolmayan sinyal %2. Son temettü 2025-05-07 (brüt %60,0).
- **Analiz sekmesi (sembol arama):**
  - BTC: fiyat ≈ 59.034,50, 15 dk trend düşüş, funding −0,0077%, long/short 78/22, 7 günlük −%13,54, 24s −%4,32; "30m Price Action Dönüş (Kriter 3/12)" bildirimi; ilgili haber (Bitcoin 59.000$'ın altına düştü).
  - THYAO: Çift Dip LONG (1s, onaylı), kırılım 325,75, SL 312,82, TP 337,00; gün ve 52 hafta aralığı; bilanço/temettü takvimi.
- **Balina İşlemleri:** "Makro Şok Tespit Edildi" kartları (SPXUSDT +%1,92 ve +%2,07, XAGUSDT +%1,58; eşik %1,80). Uygulama bunların otomatik ön tarama olduğunu ve doğrulanmadan sinyal olarak kullanılmaması gerektiğini yazıyor.
- **Hedefim:** Sanal hedef aracı.
  - Kripto veya Forex, başlangıç ve hedef bakiye (örnek 50$ → 200$), risk seviyesi (Temkinli, Dengeli, Agresif), kaldıraç aralığı (5–10x, 10–20x, 5–20x).
  - Her öneride likidasyon stopun en az 2 katı uzakta kalacak şekilde aralıktaki en düşük uygun kaldıraç (izole). Kriptoda en fazla ~38x "güvenli" olduğu yazıyor.
  - Bot gerçek işlem açmıyor, kullanıcı kendi borsasında uyguluyor; kaldıraçlı işlemde teminatın tamamı kaybedilebilir uyarısı var.
  - Öneriler yalnızca uygulama içinde görünüyor (/hedefimdurum komutu).
  - "Düşüş (SHORT) yönünde yeni öneri geçici olarak durdu; son dönemde bu yönde başarı belirgin düştü" uyarısı görünüyor.
- **Haberler:** Kripto ve BIST haber akışı (CoinDesk, Investing.com); otomatik çeviri (OPUS-MT, CC-BY 4.0).
- **Sohbet:** Moderasyonlu topluluk sohbeti. Kurallar: küfür/nefret yasak; link, @kullanıcı adı, telefon, e-posta, IBAN ve cüzdan adresi paylaşılamaz; özelden iletişim, garantili kazanç vaadi ve bahis reklamı yasak; pump çağrıları yönetici onayına düşer; yöneticiler özelden para/kod istemez. Takma ad, mesajlar ve moderasyon kayıtları saklanır; dil tercihi saklanır, konum toplanmaz.
- **Duyuru kutusu:** "5 yıldır geliştirdiğimiz uygulamayı BingX kullananlara ücretsiz veriyoruz; aylık 100$ yerine davet linkiyle üye olup hesaba para yatır" ve kişisel Telegram hesaplarına yönlendirme. Bu bir borsa yönlendirme (referral) düzeni gibi duruyor.
- **Sürekli uyarı:** "Yatırım tavsiyesi değildir; kazanç vaadi içermez, geçmiş sonuçlar gelecekteki sonuçları garanti etmez."

## Ek D. X paylaşımları (ayrıntılı)

### D.1 @soligann, "Hedge Fund Cockpit" paylaşımı
Quantum v5 videosunun kaynağı. Yazarın anlattıkları (kendi beyanı):

1. Sıradan "RSI kesişti al, MACD düştü sat" botlarından uzak, tamamen event-driven Python altyapısı.
2. **Sinyali değil riski yöneten ML motoru:** XGBoost/Random Forest, teknik strateji ETH için LONG verirken piyasa rejimini koklayıp "%78 ihtimalle düşüş var" diyerek işlemi reddetmiş.
3. **Kendi kendini onaran veri gölü:** PyArrow tabanlı, Snappy sıkıştırmalı Parquet + SQLite hibrit yapı; boşluk veya bozuk dosyada eksik mumları REST API'den çekip birleştiriyor.
4. **While True döngülerine veda:** asenkron pub/sub; Binance WebSocket'ten saniyelik veri, PnL hesabı, ML tetikleme, arayüze milisaniyelerde yansıma; bağlantı koptuğunda 5 saniyede yeniden bağlanma, veri kaybı sıfır.
5. **Bloomberg Terminal esintisi:** Dark/glassmorphism dashboard; canlı PnL, drawdown, ML güven skorları ve API limit durumu üstte kayan ticker olarak akıyor; işler ters giderse her şeyi anında boşaltıp sistemi durduracak büyük kırmızı Kill Switch.
6. Yazar diğer geliştiricilerden risk yönetimi ve Walk-Forward Optimization (WFO) yaklaşımları hakkında görüş istiyor.
Etiketler: #AlgorithmicTrading #Python #MachineLearning #QuantFinance #CryptoTrading #XGBoost #Bitcoin #BTC.

### D.2 "Quantbot" paylaşımı (yazarı ekran görüntüsünden belli değil)
Yapay zekâ ve makine öğrenmesi destekli kantitatif bir trading sistemi. Projede şu ana kadar:

- GPU destekli makine öğrenmesi
- Meta-labeling ve triple-barrier labeling
- Otomatik tarihsel veri toplama
- Purged walk-forward cross-validation
- Monte Carlo simülasyonu
- Veri sızıntısı ve overfitting kontrolleri
- İşlem maliyetlerini hesaba katan backtesting
- Prop firmalara özel risk yönetimi
- Otomatik MT5 ve Binance entegrasyonu
- 555 başarılı otomatik yazılım testi

Yazar, altyapının önemli bölümünü tamamladığını ama henüz istatistiksel olarak doğrulanmış, sürdürülebilir bir ekonomik avantaj elde edemediğini söylüyor. Amacı kendi sermayesini riske atmaktan çok prop firmalar üzerinden hem kriptoda hem geleneksel piyasalarda algoritmik işlem yapmak. Topluluğa soruları: Türkiye'den kullanılabilecek prop firmalar, botlara izin veren firmalar, kripto perpetual futures mı Forex/CFD mi daha mantıklı, hangi piyasa/strateji türlerinde ekonomik avantaj aranmalı, deneyimler neler.

### D.3 Yukarıdaki paylaşıma gelen bir yanıt

- Yanıtlayan, kullandığı iki prop firma adını veriyor; botlara izin verip vermediklerini bilmediğini, bunun için firmalarla iletişime geçilmesi gerektiğini yazıyor.
- Algoritmik tarafta kriptoda hacimli majörleri (BTC, ETH, SOL) öneriyor; çünkü "saçma hareketler" daha az.
- FX/emtia tarafında altın, gümüş, EURUSD, USDCAD, petrol (USOIL, Brent) ve US100'ü uygun buluyor.
- Kendi yöntemi: ağırlıklı range trade (haftalık/aylık range konsepti), range olmayan piyasada günlük/4h arz-talep bölgesinden tepki sonrası karakter değişimi; formasyon tarafında kama ve takoz gibi şekilleri harmanlıyor. Hiçbir konseptte win rate %100 değil.
- Fikir: botu prop firmaya bağlamak yerine TradingView alarmı veya Telegram'dan sinyal şeklinde işleme giriş bildirimi almak.
Bu tek bir kişinin deneyimi; firma kuralları her firmanın kendi şartlarından doğrulanmalı.

## Ek E. Diğer ajanın PDF notu ve farklar

Diğer ajanın PDF'i ("İki Video – Trading Programları Analiz Notları", 3 sayfa) şunları içeriyor:

- **Video 1:** MetaTrader tabanlı işlem ve performans takip ekranı; canlı grafik, birden fazla sistem (System 2 ve System 3 yazmış), net kazanç/kapanan işlem/drawdown, işlem geçmişi (yön, hacim, giriş-çıkış, zaman), SL/TP, kârlılık, Pepperstone bağlantısı. "Algoritma ve indikatörler videodan doğrulanamıyor."
- **Video 2 (A–H):**
  - A) XGBoost, Triple Barrier, Ensemble, Precision/Recall/F1, model skoruna göre dinamik kaldıraç.
  - B) Strateji yönetimi (trend_master, adaptive_koncorde, golden_combo, divergence_hunter, knn_quant_atr, custom_smartmoney).
  - C) Strateji oluşturucu (EMA 20, SMA 20, Supertrend, RSI 14, MACD, ATR 14, Bollinger; LONG/SHORT koşulları).
  - D) Backtest ve risk: max risk %0,1–5,0, max kaldıraç 1–500, max pozisyon 1–20, ardışık kayıp, Kill Switch, Walk-Forward Optimization, "Katı Mum Kapanış Kilidi" (sinyaller mum kapanışında, çıkış/trailing stop beklemeden).
  - E) Bot yönetimi: Binance, API Key/Secret alanları, Spot ve Futures (Swap), Isolated, zaman dilimleri 1m–1d.
  - F) Veri laboratuvarı (Parquet, ~4,52 milyon mum).
  - G) Paper trading ve canlı performans.
  - H) AI Kernel Logs.
- **Karşılaştırma tablosu ve genel değerlendirme:** İkinci sistem bir bot değil, algoritmik motor + ML + strateji laboratuvarı + backtest + risk + veri merkezi + canlı panel bir platform.
- **Güvenlik notları:** Videolar gerçek başarıyı kanıtlamaz; AI başarı oranı doğrulanamaz; backtest'te komisyon/slippage kontrolü, WFO'da veri sızıntısı kontrolü, gerçek zamanlı emir performansı ve API güvenliği test edilmeli; gerçek API anahtarı paylaşılmışsa gizlenmeli ve yenilenmeli.

**Bu notla farklar:**

| Konu | Diğer ajan | Bu not |
| --- | --- | --- |
| Video 1 sistem adları | System 2 ve System 3 | System 1 ve System 3 (yakın kırpmada doğrulandı) |
| Kütüphane stratejileri | 6 isim (botlarda çalışanlar) | 7 strateji, 7.si Scalper Ninja |
| Strateji Kurucu, Walk-Forward, ML ayarları | Var | Doğrulandı |
| Katı Mum Kapanış Kilidi, dinamik kaldıraç, API Key alanları, tam zaman dilimi listesi | Var | Karelerde görülmedi, doğrulanamadı |
| Max kaldıraç | 1–500 | 1–50 okundu, etiket küçük; çözülemedi |
| Spot desteği | Spot ve Futures | Bot ekranında yalnızca Futures (Swap); veri laboratuvarında spot semboller listeli |
| Paper trading sonuçları | Belirtilmemiş | %0 win rate, −$52,99 (geçmiş), ≈ −$60 (Emirler) |

## Ek F. Gönderilen 29 fotoğrafın envanteri

| Grup | Adet | İçerik |
| --- | --- | --- |
| TradesSenceAI | 15 | Analizler (ana liste, 3 görünüm), ORDIUSDT detayı (grafik, geçmiş performans, neden bu analiz), BIST listesi, GMTAS detayı (2), Analiz arama (BTC, THYAO), Sohbet, Haberler, Balina İşlemleri, Hedefim (2) |
| Quantum v5 ekran kareleri (X videosundan) | 8 | ML Motoru, Emirler, İşlem Geçmişi, Raporlar, Strateji Kurucu, Strateji Kütüphanesi, Ayarlar (bot başlatma), Laboratuvar |
| X paylaşımı metinleri | 5 | @soligann paylaşımı (2), "Quantbot" paylaşımı (2, arama sonucu dahil), bir yanıt (1) |
| MT5 ekran görüntüsü | 1 | System 1 ve System 3 paneli, History sekmesi |

## Ek G. Doğrulanamayan noktalar

- **Max kaldıraç:** 1–50 mi 1–500 mü; etiket küçük, çözülemedi.
- **Spot desteği:** Bot başlatma ekranında yalnızca Futures (Swap) ve Isolated görünüyor.
- **Katı Mum Kapanış Kilidi, dinamik kaldıraç, API Key/Secret alanları:** Yalnızca diğer ajanın notunda var.
- **İkinci videonun ses kaydı:** Çözümlenmedi; notlar yalnızca görüntüden çıkarıldı.
- **MT5 net değerleri:** Birim ve komisyon/slippage dahil olup olmadığı ekranda yazmıyor.
- **TradesSenceAI:** Analiz listesi SHORT ağırlıklıyken "Hedefim" SHORT önerilerini durdurmuş; iki bölümün bağımsız olup olmadığı belli değil.
- **X'teki tüm teknik iddialar** yazarların kendi beyanıdır; bağımsız doğrulanmadı.
- **Quantum v5 paper verisi** yalnızca birkaç dakikalık bir çalışmaya (25.03.2026) ait.
