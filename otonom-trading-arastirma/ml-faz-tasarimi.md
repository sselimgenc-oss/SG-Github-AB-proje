# ML fazı tasarımı (v2, 17 Kasım 2026 — kullanıcı onaylı)

**Durum (17 Kasım 2026): ML-0a (faz planı 19a, 19d test kancaları) kodlandı ve test edildi; commit/inceleme bekliyor.** Motor `StrategyContext.model` alanı (05 §13.2, §13.4a); defter şema 3 (`ml_filter` atlama nedeni + `ml_score` sütunu, göç 2→3; defter-spec Revizyon 3, §10.3); ağaç okuyucu + paket okuyucu + özellik üretici `trader_core`'a taşındı (`ml_eval`, `ml_package`, `ml_features`; motor `trader_ml` import etmez); `price_action_v1_ml` kayıtlı, `ml_mode` varsayılan `off` (`config/engine.base.json`). `off`/`shadow` kararları v1b ile birebir (test). Açık kalan: `precomputed.py`'ye `ctx.model` geçişi (backtest'te ML, 19b ile), BTC/ETH/fonlama özelliklerinin canlıda NaN olması ve `f_bars_since_exit`/1g-eğim pencere farkı (05 §13.4a "Bilinen sınırlar").

Kullanıcı 17 Kasım'da açık noktalardaki mentor önerilerini onayladı ve ML'yi Faz 2'ye aldı (Bölüm 9 ve 10; takvim Bölüm 7). Kod içermez. `tasarim-kararlari.md` ile çelişirse o belge geçerlidir.

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
| Kayan eğitim/test pencereleri (`train_period`, `backtest_period`) | FreqAI | Fikir | Genişleyen pencere: ≥ 8 ay eğitim, 2 ay test (Bölüm 3.3) | ML-1 |
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
2. Purged walk-forward, genişleyen pencere: en az 8 ay eğitim, 2 ay test, 2 ay kaydırma (2026-04 sonuna kadar 4 test dilimi). v1'deki "18 ay eğitim, 3 ay test" eldeki veriyle kurulamaz: veri 2024-11'de başlıyor, ısınma sonrası fiilen 2024-12-21, kilitli dönem 2026-05'te; kullanılabilir süre ~16 ay. Veri 2024-11 öncesine uzatılırsa pencere yeniden yazılır (yeni deneme sayılır).
3. Sabit tarifle eğitim: lojistik regresyon (taban) ve sığ LightGBM (derinlik ≤ 4, yaprak başı en az 50 örnek, erken durdurma). LightGBM tabanı net R'de geçemezse lojistik seçilir.
4. Olasılık kalibrasyonu ve eşik seçimi yalnız test dilimlerinde; eşik [0,45 – 0,70] aralığında, alınan aday oranı ≥ %30 şartıyla.
5. Çıktı paketi: ağaçların JSON dökümü, eşik, özellik listesi ve aralıkları, DI referansı, eğitim tarihi, veri ve kod özeti (hash). Pickle yok.

Tarif (özellik listesi, hiperparametre, etiket) değişirse bu yeni **denemedir**: önceden kayda yazılır, deneme defterine eklenir, DSR'deki deneme sayısını artırır. Haftalık yeniden eğitim aynı tarifle yapılır ve deneme sayılmaz.

### 3.4 Terfi kapısı (sırayla; biri kalırsa model reddedilir)

1. **IC kapısı:** test dilimlerinde model puanı ile net R arasındaki sıra korelasyonu > 0, t ≥ 2 ve 4 test diliminin en az 3'ünde pozitif.
2. **Kalibrasyon:** Brier skoru sabit taban oran tahmininden iyi.
3. **Bölüm 1 ölçütleri**, mount edilen Aurum istatistikleriyle (DSR, PBO, durağan bootstrap; çoklu karşılaştırmada Holm).
4. **Maliyet dayanıklılığı:** komisyon ×2 + 5 bp kolunda filtreli net beklenti ≥ −0,05 R.
5. **Eşlik testi:** motorun ağaç okuyucusu ile LightGBM'in tahmini 1e-9 içinde aynı.
6. **Görevdekine karşı:** aday, etkin modelden ileri pencerede kötü değil.

### 3.4a Ön kayıt: tarif `ml1-r01-v1b-native33` (17 Kasım 2026; gerçek koşudan önce)

Bu bölüm eşik gevşetmesi değil, tanım düzeltmesidir; eşikler (§3.4) aynen kalır.

- **IC evreni:** IC kapısının bağlayıcı evreni yalnız **alınan işlemlerdir** (`taken`: stratejinin gerçekten girdiği satırlar, gerçek net R). Tüm satırlar (alınan + atlanan) IC'si raporda **tanı satırı** olarak yer alır ve geçti/kaldı rolü yoktur; çünkü atlanan adayların net R'ı basitleştirilmiş referans çıkıştır.
- **Tarif kimliği:** `ml1-r01-v1b-native33` — sabit taban: lojistik + sığ LightGBM (`LGBM_PARAMS` olduğu gibi), 33 özellik (`ml_features.FEATURE_NAMES`; 39→33 değişimi yeni tarif sayılır), 2R / 72 mum üç-bariyer etiketi, ileri yönlü Platt, 4 test dilimi. Pipeline `RECIPE_ID` bu kimliktir; satır `research/ml_trial_registry.csv`'ye eklendi, eski satır (`ml0c-baseline-v1`) durur.
- **n_trials = 4:** deneme defteri 2 tarif × 2 model (lojistik, LightGBM); `registry.py` sayımı değişmedi, defter satırı silinemez/tekrarlanamaz.
- **lightgbm zorunlu:** gerçek koşuda (`--research` / sentetik olmayan) lightgbm yüklenemezse koşu **başarısız** sayılır (çıkış kodu 2); sessizce lojistiğe düşülmez. Yalnız sentetik/test kipi, açık parametreyle (`require_lightgbm=False`) düşebilir.
- **Rapor:** iki IC satırı (bağlayıcı: alınanlar; tanı: tüm satırlar), korpus sha256, tarif kimliği, n_trials, lightgbm sürümü.
- **19c:** yeniden kurulumdan sonra tek koşu; yeniden koşu/ayar yok; KIRMIZI geçerli sonuçtur ve kayda geçer.

### 3.5 Gölge ve ikiz

- **Gölge:** aday model her karara puan yazar, hiçbir kararı etkilemez. Filtre yalnız işlem çıkardığı için "filtre açık olsaydı" sonucu, alınan işlemlerin alt kümesi olarak defterden doğrudan hesaplanır; ayrı bir bot gerekmez. Tek yaklaşıklık: çıkarılan işlemin boşalttığı risk payına başka işlem girebilirdi; raporda ayrıca gösterilir.
- **İkiz:** değişmez; ilk sürüm parametreleriyle donmuş kontroldür ve ML'siz kalır. Model devredeyken "aynı mumda ikiz aldı, öğrenen ML yüzünden almadı" eşleşmesi doğal karşılaştırmayı verir.
- İlk terfi **büyük değişikliktir**: en az 6 hafta gölge + kullanıcının Telegram onayı. Aynı tarifin haftalık yenilemesi, kullanıcı onaylı ilk üç terfiden sonra kapıdan geçerse otomatik uygulanır.
- Ders servisiyle çakışma yok: aynı anda yalnız **bir** değişiklik gözlem altındadır; model terfisi de bu sıraya girer.

### 3.6 Sıcak yükleme, kayma alarmı, geri alma

- **Sıcak yükleme:** model paketi sunucuda hash'iyle statik model kaydına konur; devreye alma = defterde yeni parametre sürümü (`ml_model_id`, `ml_threshold`). Motor modeli kayıttan yükler ve stratejiye salt okunur verir; strateji dosya/ağ görmez. Açık pozisyonlar giriş anındaki sürümle yönetilir.
- **Güvenli taraf (yalnız `ml_mode=active` iken; `off` ve `shadow` modunda model eksikliği hiçbir işlemi engellemez, yalnız uyarı üretir):** model yok, hash tutmuyor, süresi dolmuş (21 gün) ya da aday DI eşiğinin dışındaysa ML'li strateji **yeni giriş açmaz**; çıkışlar çalışır, Telegram uyarır. Filtresiz stratejiye dönüş yalnız kullanıcı kararıyla.
- **Kayma alarmı:** (a) özellik kayması: canlı özellik dağılımı eğitimdekiyle kıyaslanır (PSI); (b) model kayması: son 30 puanlı adayın IC'si ve isabeti, aynı modelin önceki canlı penceresiyle kıyaslanır; (c) DI reddi oranı %30'u geçerse. Alarm yalnız Telegram uyarısıdır; kendi başına parametre değiştirmez.
- **Geri alma:** ders servisinin geri alma izleyicisi aynen kullanılır (ders-spec Bölüm 10): terfi sonrası gözlem penceresi kötüleşirse önceki model sürümüne dönülür, geri alınan model kara listeye girer. Kullanıcının geri alma düğmesi modeli de kapsar.

## 4. Motora nasıl takılır

- Yeni kayıtlı strateji: `price_action_v1_ml`. v1b'yi sarar; aynı adayları üretir, ardından yalnız "aday var → yok" nötrlemesi yapar (bugünkü `post_filter` sözleşmesi). Gerekçe alanına `ml:` öneki ve puan yazılır.
- **Değişmeyenler:** kapı zinciri ve sırası, LLM vetosu, `risk.check_entry` ve kilitli risk ayarları, boyut/kaldıraç, çıkışların kapısızlığı, kill. Model puanı boyutu **etkilemez**; "güvene göre boyut" yok. Risk kilidi her zaman son sözü söyler.
- **İki küçük sözleşme değişikliği (17 Kasım'da onaylandı, Bölüm 10; faz planı 19a):**
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

## 7. Aşamalı yol haritası (v2, faz-plani.md ile aynı)

İlke: ana yapı (faz planı 13–19) her zaman önce gelir. 30 Kasım'dan önceki ML işleri 27 Kasım akşamı kesilir; bitmeyen kağıt dönemine kayar. ML hiçbir aşamada kağıt başlangıcını (30 Kasım) ya da canlı tarihini (28 Aralık – 4 Ocak) bekletmez. v1'deki "ML-1 27 Aralık'tan önce başlamaz" eşiği kalktı; yerine aşağıdaki sıra geçerli. v1'deki "gölge için 8 hafta kayıt + 300 etiketli aday" eşiği de kalktı: hacmi geçmiş tarama verir, canlı kanıt şartı etkinleştirme kapısına (ML-2 çıkışı) taşındı.

| Aşama | Faz planı | İçerik | Ne zaman | Çıkış ölçütü |
|---|---|---|---|---|
| ML-0a Sözleşme ve kablolama | 19a, 19d | Motor bağlam alanı; `ml_filter` + puan alanı; `price_action_v1_ml`; `ml_mode` (varsayılan off) | 27 Kasım'a kadar — **zorunlu** | `off`/`shadow` modunda kararlar v1b ile birebir; uçtan uca test geçer |
| ML-0b Geçmiş derlem | 19b | Backtester v1b'yi 2024-11 → 2026-04'te oynatır; her aday (alınan + atlanan) etiket ve net R ile | Backtester çapraz doğrulaması geçince; hedef 27–28 Kasım, olmazsa kağıt 1. hafta | Derlem hash'iyle dondurulur; rastgele 50 adayın etiketi elle doğrulanır |
| ML-0c Eğitim hattı | 19c | Aurum montajı, özellik üretici, taban + LightGBM, JSON döküm, ağaç okuyucu, kapı betiği | Hedef 28 Kasım; olmazsa kağıt 1.–2. hafta | Bir uçtan uca koşu + kapı raporu; istatistikler makale örnekleriyle tutuyor; eşlik testi geçer |
| ML-0d Alınmayan sinyal gece işi | 25a | Atlanan kararların varsayımsal net R'si | Kağıt 1. hafta | 14 gün kesintisiz etiket üretimi |
| ML-1 Araştırma (sunucu dışı) | 25b | En fazla 8 ön kayıtlı tarif | ML-0b + ML-0c bitince; gerçekçi ilk sonuç aralık 1.–2. hafta | Bir tarif Bölüm 3.4'ü geçer; geçemezse **faz durur**, rapor yazılır |
| ML-2 Gölge | 25c | Model her karara puan yazar; kayma alarmı; DI | ML-1 geçince; en erken kağıt 2. hafta. Canlıda da sürer | ≥ 6 hafta ve ≥ 150 puanlı aday (≥ 50'si alınmış); ileri dönemde net R farkı > 0 ve IC > 0 |
| ML-3 Etkin filtre | 28a | `price_action_v1_ml` devrede; son kullanma süresi; geri alma izleyicisi | ML-2 geçti + kullanıcının Telegram onayı + canlının ilk 2 haftası geçmiş + gözlem altında başka değişiklik yok. En erken ocak ortası | 8 hafta geri almasız; ikize karşı net R farkı ≥ 0 |
| ML-4 Kendi kendine yenileme | Sonraki | Sunucuda haftalık eğitim + otomatik terfi | ML-3 geçti; ilk üç terfi kullanıcı onaylı | 8 hafta elle müdahalesiz, geri almasız |
| ML-5 ML stratejisi | Sonraki | Kendi adayını üreten model | ML-4'te en az 6 ay kayıt; ayrı ön kayıt | Bölüm 1 ölçütleri, tabanı filtreli strateji |

Notlar:
- **Geçmiş derlemin sınırı:** ~16 ay ve yalnız 4 test dilimi; geçmiş kanıt incedir. Bu yüzden geçmiş kapı yalnız gölgeye girişe yeter; paraya dokunma kararı (ML-3) gölgedeki ileri dönem kanıtına bağlıdır. Geçmiş tarama örnekleri eğitimde 0,3 ağırlıkla kalır.
- Sunucuya ML-4'e kadar eğitim yükü binmez; sunucudaki tek ML yükü gölgede puanlamadır (≤ 30 MB, ≤ 20 ms). Bölüm 6'daki haftalık sunucu eğitimi ML-4'te başlar; o zamana kadar yenileme sunucu dışında, elle.
- Bot canlıdayken gölge sonuçları kağıt kanıtı sayılır (filtre yalnız işlem çıkarır); etkinleştirme mevcut işlem başı riskle olur, risk artırılmaz.
- Model strateji sürümüne bağlıdır: 6 denemelik plandan v1.1 çıkar ve devreye girerse, model yeni stratejinin adaylarıyla yeniden eğitilir (yeni deneme sayılır), kapıdan yeniden geçer ve gölge sayacı sıfırlanır.

## 8. Yapılmayacaklar

- **Canlıda RL yok.** Ödül tanımı ve simülasyon kolayca aşırı uyar, 2 GB'a sığmaz, kararı denetlenemez. Yalnız ileride, sunucu dışı araştırma olarak.
- **LLM "öz-evrim" yok.** LLM model eğitmez, özellik seçmez, eşik koymaz, kod yazıp devreye almaz. LLM'in yeri veto ve menüden ders seçimidir.
- **Sınırsız parametre yok.** Model yalnız `ml_model_id` ve sınırlı `ml_threshold` üzerinden sisteme dokunur; hiperparametre araması canlı döngüde yapılmaz.
- Model boyut, kaldıraç, stop, hedef belirlemez; risk kilidini gevşetemez.
- Kapıyı geçemeyen model "biraz daha deneyelim" diye eşik gevşetilerek alınmaz; eşikler koşudan önce yazılır.
- Kilitli dönem ML için açılmaz. Başarısız denemeler silinmez.
- Dış çatı yok: freqtrade/FreqAI kodu, ccxt, hazır bot SDK'ları kullanılmaz; GPL/AGPL/lisanssız koddan satır alınmaz.
- Çevrim içi (her mumda) ağırlık güncellemesi yok; yalnız haftalık, kapılı, geri alınabilir yenileme.

## 9. Açık noktalar

Kalmadı; beşi de 17 Kasım'da çözüldü (Bölüm 10).

## 10. Kararlar (kullanıcı onayı 17 Kasım)

Kullanıcı: "Fable ne diyorsa onayım var" — mentor önerileri aynen geçerli. Ayrıca ML, faz planında Faz 2'ye alındı (19a–19d).

1. **Sözleşme değişiklikleri — onaylandı.** (a) Motor §13: yüklenmiş model stratejiye salt okunur bağlam alanı olarak verilir; model yokken alan boştur. (b) Defter: `ml_filter` atlama nedeni ve karar başına ML puanı alanı, yalnız ekleme türü şema göçüyle. İkisi de 30 Kasım'dan önce yapılır (19a) ki uçtan uca test son sözleşmeyi sınasın ve kağıt ortasında şema göçü gerekmesin. İlgili spec'ler (motor, defter, strateji) aynı işte güncellenir.
2. **lightgbm — kabul.** MIT; yalnız `ml` isteğe bağlı grubunda, tam sürüm + hash sabit; yalnız eğitim işi ve araştırma kullanır. Motor ve sunucudaki bot süreci lightgbm yüklemez; modeli kendi ağaç okuyucumuz çalıştırır, eşlik testi kapıdadır. scikit-learn ve scipy motora girmez.
3. **Sıra — paralel, ayrı şeritlerde.** Öncelik: ana yapı ve teknik düzeltmeler > (6 denemelik strateji planı ve ML-1, ikisi de sunucu dışında, paralel). ML-0 (sözleşme, geçmiş derlem, eğitim hattı) kağıttan önce; ML-1 kağıt sırasında. Deneme defterleri ayrıdır (ML tarifleri ML'nin DSR deneme sayısını artırır, strateji denemeleri kendi sayısını). Kilitli dönem ML'ye kapalı kalır; strateji planının tek seferlik sınavıdır. Strateji sürümü değişirse model yeniden eğitilir ve gölge sayacı sıfırlanır.
4. **Model süresi dolunca — güvenli tarafta kapanır.** Etkin modda model yok / hash tutmuyor / 21 günü geçmiş / aday DI dışındaysa yeni giriş açılmaz; çıkışlar çalışır; Telegram uyarır (14. ve 18. günde ön uyarı). Filtresiz stratejiye dönüş yalnız kullanıcı kararıyla. Bu kural `off` ve `shadow` modunda işlem engellemez.
5. **Kapı eşikleri — onaylandı ve donduruldu.** Bölüm 1 (net R farkı ≥ +0,10 R ve bootstrap %90 alt sınırı > 0; filtreli net beklenti > 0; DSR ≥ 0,95; PBO ≤ 0,25; düşüş filtresizden kötü değil; adayların ≥ %30'u alınır; tek çift çıkarılınca çökmez) ve Bölüm 3.4 aynen geçerli. İlk koşudan önce yazıldıkları için "ML-1'de bir kez kalibre et" adımı kaldırıldı: eşikler sonuç görüldükten sonra gevşetilmez, yalnız sıkılaştırılabilir. Tek teknik düzeltme: walk-forward penceresi eldeki veriye uyduruldu (Bölüm 3.3).

**Etkinleştirme kuralı (özet):** kağıt `ml_mode=off` ile başlar; `shadow` kapıdan geçmiş dondurulmuş modelle açılır; `active` yalnız ML-2 çıkış ölçütü + kullanıcının Telegram onayıyla. Canlı, filtre etkin olmadan başlar.

## 11. Mentor kararları — 19a sonrası (17 Kasım 2026)
1. **`meta.user_approved` kalır.** Eğitim hattı bunu asla yazmaz. Kullanıcı Telegram'da ders önerileri gibi `/onayla` akışıyla verir; onay deftere yazılır ve paket özetine (hash) bağlanır. Onay gerekir: ilk etkinleştirme; özellik listesi, etiket tanımı ya da eşik politikası değiştiğinde. Aynı tarifle haftalık yeniden eğitim kapıyı geçerse onayı devralır, yalnız bildirim gider (`/reddet` ya da geri alma mümkün).
2. **Canlı özellik açığı:** şimdi (a) — BTC/ETH çapraz çift, funding ve `f_bars_since_exit` özellikleri motor sağlayana kadar listeden çıkarılır; NaN ile eğitilmez. `f_slope_1d` eğitimde de 1500 barlık pencereyle hesaplanır. Sonra (b) motor bağlamı genişletilir. Kağıttan önce gerekmez; **gölgeden önce zorunlu**, eğitim/canlı eşlik testiyle.
3. **Backtest `model=`** (`precomputed.py:161`, `:212`): compat işi dosyayı bırakınca; gölgeyi de bekletir.
4. **19b şimdi native kipte başlar.** Aday seti motor commit'i ve kip ile damgalanır; compat çapraz doğrulaması native davranışı değiştirirse yeniden üretilir. Çapraz doğrulama bitmeden son model eğitilmez, kapı çalıştırılmaz.
