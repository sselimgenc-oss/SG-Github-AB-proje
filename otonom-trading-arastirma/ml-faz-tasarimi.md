# ML fazı tasarımı (taslak v1, 17 Kasım 2026)

Mentor taslağıdır; kullanıcı onayı bekler. Kod içermez. `tasarim-kararlari.md` ile çelişirse o belge geçerlidir.

## 0. Kısa sonuç

1. **ML önce filtre olarak girer, strateji olarak değil.** Price action stratejisi adayı üretir; model yalnızca "bu adayı alma" diyebilir (meta-etiket). Aday ekleyemez, fiyat/stop/boyut değiştiremez. Kendi adayını üreten ML stratejisi en erken ML-5'te, ayrı kapıyla.
2. **Model bir parametre sürümüdür.** Etkin model kimliği ve eşiği defterdeki parametre sürümüne yazılır. Böylece sıcak yükleme, denetim izi, geri alma ve "aynı sürüm + aynı veri = aynı karar" kuralı mevcut defter mekanizmasından gelir; yeni bir yol icat edilmez.
3. **Eğitim sunucuda haftalık, düşük öncelikli ve bellek sınırlı; araştırma sunucu dışında.** Motorun kendisine yeni kütüphane girmez: motor modeli kendi küçük ağaç okuyucumuzla çalıştırır.
4. **Dürüstlük notu:** v1 girişinde yön bilgisi yok, işlem başı maliyet 0,18–0,22 R. Filtre, kenarı olmayan bir sinyalden kenar yaratamaz; yalnızca "hangi koşulda alınmamalı" bilgisini bulabilir. ML-1 kapısını geçemezse faz durur ve bu sonuç kayda geçer. ML, strateji iyileştirmesinin yerine geçmez.

## 1. Amaç ve "daha güçlü"nün ölçüsü

Amaç: botun kendi kayıtlarından (alınan ve alınmayan her aday) düzenli olarak yeniden öğrenen, yeni modeli ancak sayısal kapıdan geçerse devreye alan, kötüleşince kendini geri alan bir filtre.

"Daha güçlü" şu altı ölçütün **hepsi** demektir. Hepsi maliyet sonrası (net), modelin eğitimde görmediği ileri dönemde ve aynı dönemin filtresiz temel stratejisine karşı ölçülür:

| Ölçüt | Eşik |
|---|---|
| İşlem başı ortalama net R farkı (filtreli − filtresiz) | ≥ +0,10 R; durağan bootstrap %90 alt sınırı > 0 |
| Filtreli stratejinin kendi net beklentisi | > 0 R (yalnızca "daha az kötü" yetmez) |
| Deflated Sharpe (deneme sayısı düzeltilmiş) | ≥ 0,95 |
| PBO (aşırı uyum olasılığı, CSCV) | ≤ 0,25 |
| En büyük düşüş | filtresizden kötü değil |
| Dejenerasyon koruması | adayların en az %30'u alınmaya devam eder; tek çift çıkarılınca sonuç çökmez |

"Kendi kendine öğrenme"nin ölçüsü: 8 hafta üst üste haftalık yeniden eğitim elle müdahalesiz çalışır ve terfi eden hiçbir model geri alınmaz.

## 2. Hangi özellik nereden

"Kod" = lisansı uygun, bizim koda monte edilir ve kendi testimizle doğrulanır. "Fikir" = kaynak koda bakmadan kendi kodumuz yazılır. freqtrade/FreqAI **GPL-3.0**'dır (kullanıcı raporundaki "MIT" yanlıştır): yalnız fikir. AGPL ve lisanssız repolar da yalnız fikir.

| Özellik | Kaynak | Alınan | Bizdeki yeri | Aşama |
|---|---|---|---|---|
| Çok zaman dilimli özellikler (`include_timeframes`) | FreqAI | Fikir | Özellik üretici: 1s, 4s, 1g | ML-1 |
| Bağlı çift özellikleri (`include_corr_pairlist`) | FreqAI | Fikir | BTC ve ETH'nin trend/oynaklık durumu her çifte özellik | ML-1 |
| Kaydırılmış mumlar (`include_shifted_candles`) | FreqAI | Fikir | Seçili özelliklerin 1–3 mum gecikmeli kopyası | ML-1 |
| Kayan eğitim/test pencereleri (`train_period`, `backtest_period`) | FreqAI | Fikir | 18 ay eğitim, 3 ay test, ileri kaydırma | ML-1 |
| Canlıda zamanlanmış yeniden eğitim (`live_retrain_hours`) | FreqAI | Fikir | Haftalık iş (168 saat) | ML-4 |
| Model son kullanma süresi (`expiration_hours`) | FreqAI | Fikir | 21 gün; aşılırsa yeni giriş yok | ML-3 |
| Eğitim dağılımı dışını reddetme (DI eşiği, `do_predict`) | FreqAI | Fikir | Aday eğitim verisine benzemiyorsa alınmaz | ML-2 |
| Eşiğin eğitim dağılımından türetilmesi | FreqAI | Fikir | Eşik modelle birlikte dondurulur, sınırlı | ML-1 |
| Etiket tanımını modelden ayırma | FreqAI | Fikir | Etiket üretici ayrı parça | ML-0 |
| Model havuzu | FreqAI | Fikir, daraltılmış | Yalnız lojistik regresyon (taban) + LightGBM | ML-1 |
| Üçlü bariyer etiketi | Aurum v2 (MIT) | Kod | Etiket üretici | ML-0 |
| Purged walk-forward / CPCV bölmeleri | Aurum v2 (MIT) | Kod | Doğrulama | ML-0 |
| Deflated Sharpe, PBO, Holm, durağan bootstrap | Aurum v2 (MIT) | Kod | Terfi kapısı | ML-0 |
| Her sinyal bir sonuca bağlanır (alınmayanlar dahil) | MooreSi/forex-gold (AGPL) | Fikir | Gece işi: alınmayan sinyalin varsayımsal sonucu | ML-0 |
| Strateji başına ayrı kapı modeli | MooreSi/forex-gold | Fikir | Model strateji+kurulum (T1) başına | ML-1 |
| IC kapısı: geçmeyen model devreye girmez | RayanBatada (lisans belirsiz) | Fikir | Terfi kapısının ilk adımı | ML-1 |
| Otomatik terfi + modeli yeniden yükleme | Dahshan228 (MIT) | Fikir | Parametre sürümüyle sıcak yükleme | ML-3 |
| Kaymayı modelin kendi eski canlı penceresiyle ölçme | polymarket-btc botu (MIT) | Fikir | Kayma alarmı | ML-2 |
| Kaynağa göre örnek ağırlığı (gerçek > kağıt > varsayımsal) | MATS (Apache-2.0) | Fikir | Eğitim ağırlıkları | ML-1 |
| Kanıtı tutmayan zamanla zayıflar | PowerTrader_AI (Apache-2.0) | Fikir | Eski örneklere azalan ağırlık | ML-1 |

**Bilerek alınmayanlar:** PCA (ağaç modeli gerektirmez, açıklanabilirliği bozar); SVM ve DBSCAN aykırı değer ayıklama (DI yeterli, scikit-learn'e bağlar); XGBoost/CatBoost/PyTorch (tek ağaç kütüphanesi yeter, 2 GB'a sığmaz); RL (Bölüm 8); Optuna ile sürekli hiperparametre araması (deneme sayısını sınırsız büyütür); sürekli öğrenme/eski modelden devam (her hafta sıfırdan eğitim daha denetlenebilir).

## 3. Mimari

### 3.1 Veri ve etiketler

- **Örnek = bir aday karar.** Kaynak 1: kendi backtester'ımızın geçmişte ürettiği adaylar (hacim buradan gelir). Kaynak 2: defterdeki `decision_events` (alınan ve atlanan her karar; hepsinde `planned_entry`, `planned_stop`, `planned_target` ve karar anındaki `features` var). Kaynak 3: gerçek işlemlerin net sonucu, MFE/MAE.
- **Alınmayan sinyalin sonucu:** gece işi atlanan kararları sonraki mumlarda yeniden oynatır, aynı maliyet modeliyle varsayımsal net R yazar. Bu parça şarttır: yoksa model yalnız kendi geçirdiği işlemlerden öğrenir ve kendi önyargısını büyütür.
- **Eğitim etiketi (üçlü bariyer):** alt bariyer = `planned_stop` (−1 R), üst bariyer = +2 R, zaman bariyeri = 72 adet 1 saatlik mum. Etiket 1: üst bariyer önce. Etiket 0: stop ya da süre. Bu tanım sabittir; ders servisi çıkış parametresini değiştirse de etiket kaymaz.
- **Değerlendirme ölçüsü:** etiket değil, gerçek çıkış kuralıyla net R (gerçekleşen ya da yeniden oynatılan). Model etikette iyi olup parada kötüyse kapıdan geçemez.
- **Sızıntı koruması:** özellikler yalnız karar anında kapanmış mumlardan; eğitim/test arasında etiket ufku (72 mum) kadar temizleme + 24 mum ambargo; aynı mumda birden çok çift tek küme sayılır.
- **Kilitli dönem (2026-05 → 2026-10) ML için açılmaz.** O dönem strateji planının tek seferlik sınavıdır. ML geçmişte 2026-04 sonuna kadar çalışır; asıl sınavı, model dondurulduktan sonra biriken kağıt/canlı kayıtlardır.

### 3.2 Özellikler

İlk sürümde en fazla 40 özellik, hepsi ölçek bağımsız (ATR'ye ya da yüzdeye bölünmüş): rejim ve `atr_ratio`; 1s/4s/1g trend eğimi ve oynaklık; aralık kenarlarına uzaklık ve dokunma sayıları; stop genişliği ve planlanan R/R; BTC ve ETH durumu; fonlama oranı; saat/gün; son 1–3 mumun gecikmeli değerleri; son çıkıştan bu yana geçen mum sayısı. Tek özellik üretici hem geçmiş taramada hem canlıda kullanılır; canlıda üretilen değer karara yazılır, eğitim o yazılanı okur (eğitim/canlı farkı olmaz).

### 3.3 Eğitim döngüsü

1. Veri derlenir, etiketlenir, ağırlıklanır (gerçek 1,0; kağıt 0,7; varsayımsal 0,5; geçmiş tarama 0,3; yaşa göre azalır).
2. Purged walk-forward: 18 ay eğitim, 3 ay test, 3 ay kaydırma.
3. Sabit tarifle eğitim: lojistik regresyon (taban) ve sığ LightGBM (derinlik ≤ 4, yaprak başı en az 50 örnek, erken durdurma). LightGBM tabanı net R'de geçemezse lojistik seçilir.
4. Olasılık kalibrasyonu ve eşik seçimi yalnız test dilimlerinde; eşik [0,45 – 0,70] aralığında, alınan aday oranı ≥ %30 şartıyla.
5. Çıktı paketi: ağaçların JSON dökümü, eşik, özellik listesi ve aralıkları, DI referansı, eğitim tarihi, veri ve kod özeti (hash). Pickle yok.

Tarif (özellik listesi, hiperparametre, etiket) değişirse bu yeni **denemedir**: önceden kayda yazılır, deneme defterine eklenir, DSR'deki deneme sayısını artırır. Haftalık yeniden eğitim aynı tarifle yapılır ve deneme sayılmaz.

### 3.4 Terfi kapısı (sırayla; biri kalırsa model reddedilir)

1. **IC kapısı:** test dilimlerinde model puanı ile net R arasındaki sıra korelasyonu > 0, t ≥ 2 ve dilimlerin en az üçte ikisinde pozitif.
2. **Kalibrasyon:** Brier skoru sabit taban oran tahmininden iyi.
3. **Bölüm 1 ölçütleri**, mount edilen Aurum istatistikleriyle (DSR, PBO, durağan bootstrap; çoklu karşılaştırmada Holm).
4. **Maliyet dayanıklılığı:** komisyon ×2 + 5 bp kolunda filtreli net beklenti ≥ −0,05 R.
5. **Eşlik testi:** motorun ağaç okuyucusu ile LightGBM'in tahmini 1e-9 içinde aynı.
6. **Görevdekine karşı:** aday, etkin modelden ileri pencerede kötü değil.

### 3.5 Gölge ve ikiz

- **Gölge:** aday model her karara puan yazar, hiçbir kararı etkilemez. Filtre yalnız işlem çıkardığı için "filtre açık olsaydı" sonucu, alınan işlemlerin alt kümesi olarak defterden doğrudan hesaplanır; ayrı bir bot gerekmez. Tek yaklaşıklık: çıkarılan işlemin boşalttığı risk payına başka işlem girebilirdi; raporda ayrıca gösterilir.
- **İkiz:** değişmez; ilk sürüm parametreleriyle donmuş kontroldür ve ML'siz kalır. Model devredeyken "aynı mumda ikiz aldı, öğrenen ML yüzünden almadı" eşleşmesi doğal karşılaştırmayı verir.
- İlk terfi **büyük değişikliktir**: en az 6 hafta gölge + kullanıcının Telegram onayı. Aynı tarifin haftalık yenilemesi, kullanıcı onaylı ilk üç terfiden sonra kapıdan geçerse otomatik uygulanır.
- Ders servisiyle çakışma yok: aynı anda yalnız **bir** değişiklik gözlem altındadır; model terfisi de bu sıraya girer.

### 3.6 Sıcak yükleme, kayma alarmı, geri alma

- **Sıcak yükleme:** model paketi sunucuda hash'iyle statik model kaydına konur; devreye alma = defterde yeni parametre sürümü (`ml_model_id`, `ml_threshold`). Motor modeli kayıttan yükler ve stratejiye salt okunur verir; strateji dosya/ağ görmez. Açık pozisyonlar giriş anındaki sürümle yönetilir.
- **Güvenli taraf:** model yok, hash tutmuyor, süresi dolmuş (21 gün) ya da aday DI eşiğinin dışındaysa ML'li strateji **yeni giriş açmaz**; çıkışlar çalışır, Telegram uyarır. Filtresiz stratejiye dönüş yalnız kullanıcı kararıyla.
- **Kayma alarmı:** (a) özellik kayması: canlı özellik dağılımı eğitimdekiyle kıyaslanır (PSI); (b) model kayması: son 30 puanlı adayın IC'si ve isabeti, aynı modelin önceki canlı penceresiyle kıyaslanır; (c) DI reddi oranı %30'u geçerse. Alarm yalnız Telegram uyarısıdır; kendi başına parametre değiştirmez.
- **Geri alma:** ders servisinin geri alma izleyicisi aynen kullanılır (ders-spec Bölüm 10): terfi sonrası gözlem penceresi kötüleşirse önceki model sürümüne dönülür, geri alınan model kara listeye girer. Kullanıcının geri alma düğmesi modeli de kapsar.

## 4. Motora nasıl takılır

- Yeni kayıtlı strateji: `price_action_v1_ml`. v1b'yi sarar; aynı adayları üretir, ardından yalnız "aday var → yok" nötrlemesi yapar (bugünkü `post_filter` sözleşmesi). Gerekçe alanına `ml:` öneki ve puan yazılır.
- **Değişmeyenler:** kapı zinciri ve sırası, LLM vetosu, `risk.check_entry` ve kilitli risk ayarları, boyut/kaldıraç, çıkışların kapısızlığı, kill. Model puanı boyutu **etkilemez**; "güvene göre boyut" yok. Risk kilidi her zaman son sözü söyler.
- **Gereken iki küçük sözleşme değişikliği (mentor/kullanıcı onayı ister):**
  1. Motor §13: motor, yüklenmiş modeli stratejiye salt okunur bağlam alanı olarak verir (strateji saflığı korunur).
  2. Defter: ML'nin elediği aday da karar olarak yazılır (yeni atlama nedeni `ml_filter`, ekleme türü şema göçü) ki gece işi onun da sonucunu etiketlesin.
- **Sonrası (ML-5):** kendi adayını üreten ML stratejisi aynı strateji arayüzüyle, önce `paper_allowed=False` (yalnız backtest), sonra kağıt; kapısı Bölüm 1 ile aynı, karşılaştırma tabanı o günkü en iyi filtreli strateji.

## 5. Bağımlılık kararı

- **lightgbm (MIT):** yalnız `ml` isteğe bağlı grubunda, tam sürüm + hash sabitlenmiş; yalnız eğitim işi ve araştırma kullanır. Motorun bağımlılıkları değişmez.
- **Motor tarafı:** ağaç JSON'unu okuyan kendi küçük değerlendiricimiz (numpy). Eşlik testi terfi kapısındadır.
- **scikit-learn alınmaz;** kalibrasyon, lojistik regresyon, DI ve PSI kendi kodumuzdur (hepsi kısa ve elle doğrulanabilir).
- **scipy:** Aurum istatistiklerinin kullandığı birkaç fonksiyon (normal dağılım) taşınır; scipy motora girmez. Araştırma ortamında çapraz kontrol için kullanılabilir.
- Aurum parçaları `THIRD_PARTY_NOTICES.md`'ye yazılır; matematik makalelere karşı kendi testimizle doğrulanır.

## 6. Kaynak planı (2 GB paylaşımlı sunucu)

| İş | Nerede | Ne zaman | Sınır |
|---|---|---|---|
| Canlı puanlama | Sunucu, motor içinde | Her kararda | ek bellek ≤ 30 MB, karar başı ≤ 20 ms |
| Alınmayan sinyal etiketleme | Sunucu, gece işi | Günlük, ders işinden sonra | ≤ 200 MB, ≤ 5 dk |
| Haftalık yeniden eğitim + kapı | Sunucu, ayrı düşük öncelikli iş | Pazar 03:00 UTC | bellek tavanı 450 MB (aşarsa iş ölür, bot etkilenmez), tek çekirdek, ≤ 20 dk |
| Araştırma: CPCV, PBO, yeni tarif denemeleri, geçmiş tarama | Sunucu dışı (geliştirme makinesi) | Elle, ön kayıtlı | — |

Eğitim işi botla aynı süreçte çalışmaz, deftere salt okunur bağlanır, başarısız olursa hiçbir şey değişmez. Ölçülen tepe bellek 450 MB'ı aşarsa haftalık eğitim de sunucu dışına alınır ve yalnız model paketi sunucuya taşınır. API maliyeti yok (LLM kullanılmaz).

## 7. Aşamalı yol haritası

Başlama eşiği: **ML araştırması (ML-1) 4 haftalık kağıt dönemi bitmeden (27 Aralık) başlamaz; gölge model (ML-2) en az 8 haftalık kayıt ve en az 300 etiketli aday (alınan + alınmayan), bunların en az 60'ı kapanmış gerçek/kağıt işlem olmadan başlamaz.** Hangisi geç gelirse o beklenir.

| Aşama | İçerik | Giriş ölçütü | Çıkış ölçütü |
|---|---|---|---|
| ML-0 Temel | Alınmayan sinyal gece işi; Aurum istatistik/bölme/etiket montajı; özellik kaydının denetimi | Kağıt başlamış, ana yapı çalışıyor | 14 gün kesintisiz etiket üretimi; istatistikler makale örnekleriyle tutuyor |
| ML-1 Araştırma (sunucu dışı) | Özellik üretici, etiket, taban model, kapı; en fazla 8 ön kayıtlı tarif | Kağıt 4 haftası bitti; kendi backtester'ımız çapraz doğrulandı; 6 denemelik strateji planı sonuçlandı ya da kullanıcı sırayı değiştirdi | Bir tarif Bölüm 3.4'ü 2026-04 öncesi veride geçer; geçemezse **faz durur**, rapor yazılır |
| ML-2 Gölge | Model her karara puan yazar; kayma alarmı; DI | ML-1 geçti; yukarıdaki veri eşiği; iki sözleşme değişikliği onaylı | ≥ 6 hafta ve ≥ 150 puanlı aday (≥ 50'si alınmış); ileri dönemde net R farkı > 0 ve IC > 0 |
| ML-3 Etkin filtre | `price_action_v1_ml` devrede; son kullanma süresi; geri alma izleyicisi | ML-2 geçti; kullanıcı onayı; o an botta gözlem altında başka değişiklik yok | 8 hafta geri almasız; ikize karşı net R farkı ≥ 0 |
| ML-4 Kendi kendine yenileme | Haftalık eğitim + otomatik terfi | ML-3 geçti; ilk üç terfi kullanıcı onaylı | 8 hafta elle müdahalesiz, geri almasız |
| ML-5 ML stratejisi | Kendi adayını üreten model, strateji arayüzüyle | ML-4'te en az 6 ay kayıt; ayrı ön kayıt | Bölüm 1 ölçütleri, tabanı filtreli strateji |

Her aşama önce kağıtta/gölgede kanıtlanır. Bot o sırada canlıdaysa gölge sonuçları kağıt kanıtı sayılır (filtre yalnız işlem çıkarır); etkinleştirme yine kullanıcı onayıyla ve mevcut işlem başı riskle olur, risk artırılmaz.

## 8. Yapılmayacaklar

- **Canlıda RL yok.** Ödül tanımı ve simülasyon kolayca aşırı uyar, 2 GB'a sığmaz, kararı denetlenemez. Yalnız ileride, sunucu dışı araştırma olarak.
- **LLM "öz-evrim" yok.** LLM model eğitmez, özellik seçmez, eşik koymaz, kod yazıp devreye almaz. LLM'in yeri veto ve menüden ders seçimidir.
- **Sınırsız parametre yok.** Model yalnız `ml_model_id` ve sınırlı `ml_threshold` üzerinden sisteme dokunur; hiperparametre araması canlı döngüde yapılmaz.
- Model boyut, kaldıraç, stop, hedef belirlemez; risk kilidini gevşetemez.
- Kapıyı geçemeyen model "biraz daha deneyelim" diye eşik gevşetilerek alınmaz; eşikler koşudan önce yazılır.
- Kilitli dönem ML için açılmaz. Başarısız denemeler silinmez.
- Dış çatı yok: freqtrade/FreqAI kodu, ccxt, hazır bot SDK'ları kullanılmaz; GPL/AGPL/lisanssız koddan satır alınmaz.
- Çevrim içi (her mumda) ağırlık güncellemesi yok; yalnız haftalık, kapılı, geri alınabilir yenileme.

## 9. Açık noktalar (kullanıcı kararı)

1. Bölüm 4'teki iki sözleşme değişikliğinin onayı (motor bağlamına model alanı; defterde `ml_filter` atlama nedeni).
2. lightgbm'in sabitlenmiş, yalnız eğitim tarafında kullanılan bağımlılık olarak kabulü.
3. Sıra: ML-1, 6 denemelik strateji planından sonra mı (öneri), yoksa paralel mi?
4. Model süresi dolunca "yeni giriş yok" (öneri) mi, yoksa filtresiz stratejiye otomatik dönüş mü?
5. Bölüm 1'deki eşikler (+0,10 R, DSR 0,95, PBO 0,25) mentor önerisidir; kalibrasyon ML-1'de backtest verisiyle yapılıp bir kez dondurulacak.
