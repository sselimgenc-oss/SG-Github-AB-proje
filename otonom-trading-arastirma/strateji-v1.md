# Strateji v1 — kural seti (16 Kasım 2026)

Kaynak: `price-action-kural-katalogu.md` (58 kural) ve `tasarim-kararlari.md` (15–16 Kasım bölümü).
Bu belge v1 kural motorunun ne yapacağını tanımlar. Buradaki hiçbir sayı kârlılık kanıtı değildir; hepsi backtest ile sınanacak başlangıç değeridir.

## 1. Özet

- **1 rejim etiketi, 2 kurulum:** trendde EMA'ya geri çekilme (T1), range kenarında red mumu (R1).
- **Ayarlanan parametre sayısı: 8** (+1: 15dk tetik kolu açık/kapalı, bkz. Bölüm 2). Geri kalan her sayı sabittir ve taranmaz.
- **Swing/fraktal hesabı yok.** Trend etiketi hareketli ortalamalardan, range sınırı pencere en yüksek/en düşüğünden gelir. Böylece katalogdaki en dağınık parametre (swing N: 1–10) v1'e girmez.
- Lot, kaldıraç ve toplam risk risk kilidinden gelir. Kural motoru yalnızca giriş, stop ve çıkış üretir.

## 2. Zaman dilimleri

| TF | Görev |
|---|---|
| 4s | Rejim etiketi, trend yönü, range sınırları (RH/RL) |
| 1s | Kurulum, tetik mumu, stop ve iz süren stop hesabı |
| 15dk | Varsayılan: sinyal üretmez, backtest'te bar içi stop/hedef sırasını çözen ayrıntı verisidir (`timeframe_detail`). Ayrıca **aday tetik kolu** olarak test edilir (aşağıda) |
| 1g | Sonradan eklenir; yalnızca ek yön filtresi olur (PA-FLT-01), yeni parametre getirmez |

15dk'nın varsayılan olarak tetik olmamasının nedeni: stop mesafesi küçülür, maliyet ×2 varsayımında komisyon R'nin büyük kısmını yer; katalog da 15dk'yı gürültülü buluyor (PA-KIR-03, TE notu).

**15dk tetik kolu (onaylı tasarım kararında 15dk olduğu için):** backtest'te T1 ve R1 aynı kurallarla, tetik ve stop hesabı 15dk'ya alınarak ayrı bir kol olarak koşulur (`trigger_tf ∈ {1s, 15dk}`; rejim ve seviyeler yine 4s, başka hiçbir parametre değişmez). 15dk kolu ancak maliyet ×2 ile walk-forward'da kendi başına geçerse açılır; geçemezse v1 1s tetikle başlar ve 15dk sahte para döneminin verisiyle yeniden sınanır. Bu, ayarlanan parametre sayısını 9'a çıkarır.

Kullanılan göstergeler: EMA20/50/100 (4s), EMA20 veya EMA50 (1s), ATR(14) (4s ve 1s). Hepsi yalnızca kapanmış mumlardan hesaplanır; 4s verisi 1s'e bir mum kaydırılarak birleştirilir (ileriye bakma yok).

## 3. Rejim tespiti (4s, her 4s kapanışında)

**Kod kaynağı (mimari-taslak.md satır 4 ile uyum):** karışım. regime-trading-bot'tan (MIT, telif notu korunur) `indicators.py` gösterge hesapları (EMA, ATR) ve `regime.py`'nin etiket arayüzü, iskeleti ve test düzeni alınır: tek etiket, strateji + veto + ders servisi aynısını okur. **Sınıflandırma koşulları ve eşikleri ise aşağıdaki tablodan gelir**, o deponun kendi koşullarından değil. Neden: R1'in işlem yaptığı kenarlar (RH/RL) range tanımının kendisinden çıkıyor; etiket ile seviye iki ayrı tanımdan gelirse "range" denilen yerde kenar olmayabilir. Koşullar değiştiği için `regime.py` testleri yeniden yazılır; o deponun kapsam yüzdesi bizim koşullara devredilmez. Not: bu belge yazılırken `regime.py`'nin kendi koşulları yeniden okunmadı; uyarlama sırasında bizimkiyle eşdeğer çıkan kısım olduğu gibi kalır.

Öncelik sırası yukarıdan aşağı; ilk tutan etiket geçerlidir.

| Sıra | Etiket | Koşul | Kural |
|---|---|---|---|
| 1 | **Volatil** | `ATR14 / ort(ATR14, 100) > vol_ratio_max` | PA-FLT-03 |
| 2 | **Range** | Son 20 kapanmış 4s mumda `(RH − RL) / ATR14 ≤ range_width_atr` **ve** her iki kenar bölgesine en az 2 ayrı dokunuş | PA-YTY-01, PA-SDR-01 |
| 3 | **Trend yukarı** | `c > EMA100` ve `EMA20 > EMA50` | PA-FLT-02 |
| 3 | **Trend aşağı** | `c < EMA100` ve `EMA20 < EMA50` | PA-FLT-02 |
| 4 | **Belirsiz** | Hiçbiri | PA-FLT-06 |

- `RH = max(h)`, `RL = min(l)` (son 20 kapanmış 4s mum).
- Kenar bölgesi: `RH − edge_zone_atr × ATR14(4s)` ile `RH` arası (alt kenar ayna). Dokunuş: mumun high/low değeri bölgeye girer; ardışık mumlar tek dokunuş sayılır.
- **Volatil ve belirsiz etikette yeni işlem açılmaz.** Açık pozisyonlar kendi stop/çıkış kurallarıyla sürer.

## 4. Trend kurulumu T1 — EMA'ya geri çekilme

Kurallar: PA-TRD-01 (giriş), PA-FLT-01 (4s yön filtresi), PA-MUM-06 (mum ölçüsü), PA-STP-01 (stop), PA-STP-02a (iz süren), PA-RSK-02 (stop genişliği), PA-HDF-06 (trendde iz süren çıkış).

Long (short tam ayna):

1. **Filtre:** 4s etiketi "trend yukarı".
2. **Tetik (1s mumu kapanışında):**
   - `l ≤ EMA(pullback_ema) ≤ c` (mum EMA'ya değdi ve üstünde kapandı),
   - `c > o`,
   - gövde/range ≥ 0,5.
3. **Giriş:** tetik mumu kapanınca piyasa emri (sonraki mum açılışı).
4. **Stop:** `min(son 5 adet 1s mumun dibi) − stop_buffer_atr × ATR14(1s)`. Borsada duran, bar içi çalışan stop.
5. **Atlama:** stop mesafesi `0,5 × ATR14(1s)`'den dar veya `2,0 × ATR14(1s)`'den genişse işlem yok.
6. **Çıkış:**
   - Fiyat +1R'ye ulaşınca iz süren stop devreye girer: `stop = max(stop, girişten beri en yüksek h − trail_atr × ATR14(1s))`. Stop asla geri çekilmez.
   - 4s etiketi "trend aşağı"ya dönerse 1s kapanışında çık.
   - Sabit kâr hedefi yok, kısmi çıkış yok.

## 5. Range kurulumu R1 — kenarda red mumu

Kurallar: PA-YTY-02 (kenarda ters yön girişi), PA-KIR-03 + PA-MUM-01 (tek tanımda birleştirilmiş red mumu: sahte kırılım ve pin bar), PA-STP-01 (stop), PA-HDF-02 (karşı kenar hedefi), PA-HDF-01 (asgari ödül/risk), PA-STP-03 (zaman durdurma), PA-RSK-02.

Long alt kenarda (short üst kenarda, tam ayna):

1. **Filtre:** 4s etiketi "range".
2. **Tetik (1s mumu kapanışında):**
   - `l ≤ RL + edge_zone_atr × ATR14(4s)` (mum kenar bölgesine girdi; RL'yi delmesi şart değil),
   - `c > RL` (range içinde kapandı),
   - alt fitil / range ≥ 0,5.
3. **Giriş:** tetik mumu kapanınca piyasa emri.
4. **Stop:** `tetik mumunun dibi − stop_buffer_atr × ATR14(1s)`. Borsada, bar içi.
5. **Hedef:** `RL + range_target_frac × (RH − RL)`. Tek hedef, pozisyonun tamamı.
6. **Atlama:** `(hedef − giriş) / (giriş − stop) < rr_min` ise işlem yok. Stop mesafesi sınırı T1 ile aynı (0,5–2,0 × ATR14(1s)).
7. **Zaman durdurma:** 48 adet 1s mum içinde stop veya hedef gelmezse kapanışta çık.
8. RH/RL giriş anında dondurulur; etiket sonradan değişse de pozisyon kendi stop/hedefiyle yönetilir.

## 6. Parametreler

### 6.1 Ayarlanan parametreler (8)

| # | Parametre | Nerede | Varsayılan | Backtest tarama aralığı | Ders servisi | Ders servisi sınırı |
|---|---|---|---|---|---|---|
| 1 | `range_width_atr` | Rejim | 4,0 | 3,0 – 6,0 (adım 0,5) | Hayır | — |
| 2 | `vol_ratio_max` | Rejim | 1,5 | 1,25 – 2,0 (adım 0,25) | Evet | 1,3 – 1,7 |
| 3 | `edge_zone_atr` | Rejim + R1 | 0,25 | 0,15 – 0,50 (adım 0,05) | Hayır | — |
| 4 | `pullback_ema` | T1 | 50 | {20, 50} | Hayır | — |
| 5 | `stop_buffer_atr` | T1 + R1 (ortak) | 0,3 | 0,1 – 1,0 (adım 0,1) | Evet | 0,2 – 0,5 |
| 6 | `trail_atr` | T1 | 3,0 | 2,0 – 4,0 (adım 0,5) | Evet | 2,5 – 3,5 |
| 7 | `range_target_frac` | R1 | 0,75 | 0,50 – 1,00 (adım 0,125) | Evet | 0,6 – 0,9 |
| 8 | `rr_min` | R1 | 1,5 | 1,0 – 2,0 (adım 0,25) | Evet | 1,2 – 2,0 |

Ders servisi kuralları:

- Yalnızca yukarıdaki **5 parametreye** dokunabilir; bir seferde bir parametre, bir adım.
- Backtest sonrası sınırlar seçilen değerin çevresine yeniden ortalanır (seçilen değer ± yaklaşık bir-iki adım, tarama aralığının dışına çıkmadan).
- `vol_ratio_max` için sıkılaştırma (düşürme) küçük değişikliktir; gevşetme büyük değişiklik sayılır ve kullanıcıya sorulur.
- 1, 3 ve 4 numaralı parametreler ders servisine kapalıdır: bunlar hangi işlemlerin açıldığını değiştirir, 20–30 işlemlik kanıt önceki işlemlerle karşılaştırılamaz hale gelir. Yalnızca yeni backtest ile değişir.

### 6.2 Sabitler (taranmaz)

| Sabit | Değer | Kaynak |
|---|---|---|
| ATR periyodu | 14 | Katalog genel kuralı |
| Rejim EMA'ları (4s) | 20 / 50 / 100 | PA-FLT-02 (MI, kitap) |
| Range penceresi | 20 adet 4s mum | PA-YTY-01 (varsayılan) |
| Kenar başına asgari dokunuş | 2 | PA-YTY-01 (PA, TE) |
| Volatilite ortalama penceresi | 100 adet 4s mum | PA-FLT-03 (TE) |
| T1 gövde/range eşiği | 0,5 | PA-MUM-06 (WO, kitap) |
| T1 stop geri bakışı | 5 adet 1s mum | Bu belgenin seçimi |
| R1 fitil/range eşiği | 0,5 | PA-KIR-03 (AN, varsayılan) |
| Stop mesafesi alt/üst sınırı | 0,5 / 2,0 × ATR14(1s) | PA-RSK-02 (MI 1,5); alt sınır maliyet için bu belgenin seçimi |
| İz süren stop başlangıcı | +1R | PA-STP-02a (TE, varsayılan) |
| R1 zaman durdurma | 48 adet 1s mum | PA-STP-03 (MI 10 bar); bu belgenin seçimi |

Sabitler de birer seçimdir. Backtest'te her biri için tek bir duyarlılık kontrolü yapılır (değeri bir kademe oynat, sonuç çökmüyor mu); sonuç iyileşiyor diye değiştirilmez.

### 6.3 Backtest notu

- Walk-forward, maliyet ×2, T1 ve R1 ayrı ayrı raporlanır.
- 8 parametre tek seferde optimize edilmez. Önce rejim (1–3) kaba ızgarayla, sonra kurulum parametreleri.
- Tepe değer değil plato seçilir: komşu değerlerde de sonuç benzer olmalı.
- Bir kurulumun test dönemindeki işlem sayısı yorum yapmaya yetmiyorsa o kurulum v1'de kapalı başlar.

## 7. Katalog Bölüm 5 çelişkileri ve v1 çözümü

| # | Çelişki | v1 çözümü |
|---|---|---|
| 1 | Dokunma sayısı güçlendirir mi zayıflatır mı | Alt sınır sabit 2, üst sınır yok. Dokunuş sayısı her işlemde kayda yazılır; yön ileride veriden okunur |
| 3 | Stop tamponu 0,1 – 1,0 × ATR (10 kat fark) | Tek ortak parametre `stop_buffer_atr`, varsayılan 0,3, tüm aralık taranır |
| 4 | Kapanış bazlı mı bar içi mi stop; yapı mı MA stopu mu | Bar içi, borsada duran yapısal stop. Risk kilidi gerçekleşen kaybı sınırlamak zorunda; kapanış bazlı stop bunu garanti etmez |
| 5 | Giriş emri: limit, stop emri, kapanışta piyasa | Yalnızca kapanışta piyasa. En basit ve backtest ile canlı arasında en az fark veren seçenek. Diğer ikisi v1'de yok |
| 7 | Retest zorunlu mu | v1'de kırılım kurulumu olmadığı için konu dışı |
| 8 | Konsolidasyonda işlem yapılır mı | Yalnızca tanımlı range'in kenarında işlem (R1). Range ortasında ve belirsiz etikette işlem yok |
| 11 | Kısmi çıkış oranı ve başa baş | Kısmi çıkış ve başa baş taşıma yok. 1000 $ sermayede parçalar borsanın asgari emir tutarına takılabilir |
| 13 | Düşük volatilite sonrası kırılım yönü | Kullanılmıyor. Volatilite yalnızca üst sınır olarak (yüksekse dur) |
| 15 | Swing N (1–10) | v1'de swing hesabı yok |
| 21 | Range tanımı: tam oluşum mu erken çizim mi | Tam oluşum: iki kenarda da en az 2 dokunuş. Daha az işlem, daha temiz range |
| 24 | Asgari ödül/risk 0,8 – 2 | Parametre `rr_min`, varsayılan 1,5 (maliyet ×2 nedeniyle 1,0'ın üstünde), 1,0–2,0 taranır |

Diğer çelişkiler (2, 6, 9, 10, 12, 14, 16–20, 22, 23) v1'e girmeyen kurallara aittir.

## 8. v1'e alınmayanlar

| Kural | Neden |
|---|---|
| PA-YAP-01/02/03/05 (swing, HH-HL, BOS/CHoCH, geri çekilme derinliği) | Swing N'ye bağlı; etiket titrer, ek parametre getirir. Trend etiketi EMA ile veriliyor |
| PA-YAP-04, PA-FLT-07 (dört faz, önceki gün kırılım testi) | Tek kaynak; ikinci bir rejim tanımı gereksiz |
| PA-KIR-01/02, PA-TRD-04 (kırılım ve retest girişi) | İkinci trend kurulumu parametre sayısını ikiye katlar. v1.1'in ilk adayı |
| PA-KIR-04/05/06/07 (1-2-3, çift tepe, baş-omuz, bayrak) | Formasyon tespiti öznel, çok eşikli |
| PA-MUM-02/03/04/05/07/08 (yutan ve diğer mum formasyonları) | Her biri ayrı eşik seti ister; tek red mumu tanımı yeterli |
| PA-TRD-02/03/05 (H2/L2 sayımı, zayıf geri çekme, konfluens) | Sayım kuralları kırılgan, 1–2 kaynak; konfluens ağırlıkları kitapta yok |
| PA-SDR-02 (seviye gücü skoru) | Netlik düşük, yönü çelişkili. Yalnızca kayda yazılır |
| PA-SDR-03/04 (pivot, yuvarlak sayı seviyeleri) | Ek seviye kaynağı; v1'de tek seviye kaynağı range kenarı |
| PA-SDR-05, PA-YTY-04, PA-HDF-04 (Fibonacci) | Kaynaklar fibe güvende ayrışıyor (çelişki 16) |
| PA-SDR-06 (trend çizgisi, kanal) | Öznel çizim; kaynak kendi içinde tutarsız (çelişki 10) |
| PA-SDR-07/08/09, PA-YTY-05 (Woods bölgeleri, dar sıkışma) | Tek kaynak, tanımlar belirsiz (çelişki 18, 19) |
| PA-YTY-03 (impuls sonrası range filtresi) | Tek kaynak, sayılar bozuk OCR'dan |
| PA-FLT-04 (aşırı uzama) | Tek kaynak, düşük netlik; EMA'ya geri çekilme zaten uzamış fiyattan girmiyor |
| PA-FLT-05 (hacim teyidi) | Düşük netlik, kaynaklar çelişkili (çelişki 22) |
| PA-FLT-08 (korelasyon filtresi) | Risk kilidinin aynı yön %4 sınırı bu işi görüyor |
| PA-STP-02b/c/d (swing ve MA bazlı iz süren) | Tek iz süren yöntem yeterli; ATR olanı swing gerektirmiyor |
| PA-HDF-03 (ölçülen hareket) | Kırılım kurulumu olmadığı için gereksiz |
| PA-HDF-05 (kısmi çıkış, başa baş) | Çelişki 11; küçük sermayede asgari emir sorunu |
| PA-RSK-01 (kitap boyutlandırması) | Risk kilidi eziyor |
| Funding ve açık pozisyon verisi | Price action kuralı değil; kural motoruna girmez |

## 9. Bilinen zayıf noktalar

1. **Rejim etiketi tek hata noktası.** İki kurulum da 4s etiketine bağlı ve etiket gecikmeli. Geçiş anlarında (range'den trende, trendden range'e) ikisi birden yanlış tarafta kalır.
2. **Varsayılan sayıların çoğu kitaptan değil.** Katalogda "(varsayılan)" etiketli değerler çıkarımı yapan modelin önerisidir; range eşikleri ayrıca 4s/günlük forex-hisse için yazılmıştır. Kripto için kalibrasyon tamamen backtest'e kalıyor.
3. **R1 seyrek olabilir.** Dar range + iki kenarda ikişer dokunuş + red mumu şartı az işlem üretebilir. Az işlemle walk-forward güvenilir sonuç vermez ve ders servisi 20–30 işlem kanıtına geç ulaşır.
4. **İlk 10 coin birlikte hareket eder.** T1 sinyalleri aynı saatte aynı yönde kümelenir. Aynı yön %4 sınırı kaybı kapatır, ama fiilen aynı bahsin 2–3 kopyası açılmış olur.
