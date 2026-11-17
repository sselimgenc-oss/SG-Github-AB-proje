# Başka botlardan alınacaklar: onay listesi

**Tarih:** 17 Kasım 2026 · **Hazırlayan:** mentor · **Durum:** kullanıcı onayı bekliyor

## Bu belge nedir?

İncelediğimiz 16 hazır botu dört ayrı ekip satır satır okudu ve bizim botla karşılaştırdı. Ortaya 83 öneri çıktı. Aynı şeyi söyleyenleri birleştirdim, zayıf olanları eledim, bizim kod hakkındaki iddiaları kendi kodumuzda tek tek doğruladım. Geriye **25 madde** kaldı.

Her maddenin altında bir onay satırı var. "Evet" ya da "Hayır" demeniz yeterli; sırayı ve teknik ayrıntıyı biz yürütürüz.

**Üç şeyi baştan söyleyeyim:**

1. **Hiçbir bot "para kazandıran sihirli yöntem" içermiyor.** Hızlı öğrendiğini söyleyen bütün yöntemler (yapay zekânın ayarları kendi başına değiştirmesi, modelin her gün kendini yenilemesi, kazanca göre pozisyon büyütme) ya kendi sahipleri tarafından kapatılmış ya da zarar ettirdiği ölçülmüş. Bunları almıyoruz.
2. **En değerli bulgular bizim kör noktalarımız.** Botumuzun kârı girişten değil çıkıştan (kazanan işlemi uzun taşımaktan) geliyor. Ama öğrenme tarafımız ağırlıklı olarak girişe bakıyor ve "almadığımız işlem ne olurdu" hesabını gerçek çıkış kuralımızla yapmıyor. Listenin başı bunu düzeltmeye ayrıldı.
3. **Kurallarımız aynen duruyor.** Hiçbir madde kapı eşiklerini gevşetmiyor, kilitli döneme (Mayıs–Kasım 2026) dokunmuyor, ML'e işlem ekleme ya da pozisyon büyütme yetkisi vermiyor, "vazgeçme" ölçütü getirmiyor. Her yeni ML tarifi yine koşudan önce deftere yazılır.

**Şu an koşan r02 denemesi hakkında karar:** r02 kayıtlı haliyle devam ediyor, durdurulmuyor. Gerekçesi 6. maddede.

**İş büyüklüğü:** küçük = 1 güne kadar · orta = 2–4 gün · büyük = 1 hafta ve üzeri.

---

## A. Hemen yapılmalı (kağıt işlem başlamadan ya da ilk haftalarında)

### 1. Kağıt dönemi için "nasıl değerlendireceğiz" planını önceden yazmak
- **Ne işe yarar:** Kağıt işlem başlamadan, neye bakacağımızı ve hangi işlem sayısında (örneğin 100 / 150 / 200) karar vereceğimizi yazıyoruz. Böylece sonuca bakıp sonradan ölçü değiştirme riski kalkar; her ayar değişikliği yeni bir değerlendirme penceresi açar.
- **Kaynak:** polymarket-btc-15-minutes, MATS
- **İş büyüklüğü:** küçük
- **Risk:** Yok. Kararlar biraz daha yavaş verilir (bilinçli olarak).
- **Onay:** [ ] Evet  [ ] Hayır

### 2. Gerçek işlem maliyetini ölçmek (kayma takibi)
- **Ne işe yarar:** Geçmiş testlerimizin hepsi "emir şu kadar kötü fiyattan dolar" varsayımına dayanıyor. Gerçek dolumları bu varsayımla haftalık karşılaştırır, varsayım iyimser çıkarsa uyarır. İşlem başı kârımız ince olduğu için 1–2 baz puanlık hata sonucu artıdan eksiye çevirebilir.
- **Kaynak:** forex-gold, Aurum (tradingbot), FTMO-TradingBot, qlib, MATS
- **İş büyüklüğü:** küçük–orta
- **Risk:** Yok (yalnız ölçüm ve uyarı).
- **Onay:** [ ] Evet  [ ] Hayır

### 3. "Bot beklendiği gibi mi davranıyor?" günlük izleyicisi
- **Ne işe yarar:** Her gün işlem sıklığını, maliyeti ve fonlama giderini geçmiş testteki beklentiyle karşılaştırır; belirgin sapmada Telegram'dan haber verir. Kâr/zarar da gösterilir ama "henüz şans mı beceri mi ayırt edilemez" notuyla, çünkü kârımız az sayıda büyük işlemden geliyor.
- **Kaynak:** FTMO-TradingBot, Aurum, polymarket, alphastrike, AETS
- **İş büyüklüğü:** orta
- **Risk:** Yanlış alarm olabilir; yalnız uyarır, botu durdurmaz.
- **Onay:** [ ] Evet  [ ] Hayır

### 4. Çıkışların karnesi (hiçbir ayarı değiştirmeyen raporlar)
- **Ne işe yarar:** Her kapanan işlem için: çıktıktan sonra fiyat ne yaptı, masada ne kadar kâr bıraktık, kâra geçip zararla kapanan işlemler ne kadar tuttu, stop mesafemiz kazanan işlemlere göre geniş mi dar mı. Hangi çıkış kuralının para kaçırdığını gösterir; bir sonraki çıkış denemesini tahminle değil kanıtla seçeriz.
- **Kaynak:** MATS, forex-gold, freqai-strategies
- **İş büyüklüğü:** küçük
- **Risk:** Yok (yalnız rapor). Geçmişe bakarak "keşke" okuması riski var; rapor kural değiştirmez.
- **Onay:** [ ] Evet  [ ] Hayır

### 5. "Başka çıkış ayarıyla ne olurdu?" işini bitirmek ve sağlamlaştırmak
- **Ne işe yarar:** Tasarımı hazır ama kodu yazılmamış olan çıkış karşılaştırma işini tamamlar. Üç ek güvence eklenir: sonuç iki farklı zaman çözünürlüğünde aynı yönü göstermeli, dönemin iki yarısında da tutmalı, belirsiz durumda kötümser varsayım yapılmalı. Ayrıca yalnız ayarları değil, çıkış kurallarının kendisini de ("rejim döndü çık" kuralı olmasaydı ne olurdu) sınar.
- **Kaynak:** forex-gold, AETS, freqtrade, polymarket, FTMO-TradingBot
- **İş büyüklüğü:** orta
- **Risk:** Düşük. Sonuçlar yalnız kanıttır; değişiklik yine sizin onayınızla olur. Deneme defterine yeni satır gerekir.
- **Onay:** [ ] Evet  [ ] Hayır

### 6. Almadığımız işlemleri gerçek çıkış kuralımızla puanlamak
- **Ne işe yarar:** Bugün "bu sinyali alsaydık ne olurdu" hesabı sabit bir hedefe (2R) ya da süre dolunca çıkışa göre yapılıyor. Oysa bot gerçekte kazananı takip eden stopla uzun taşıyor ve kâr buradan geliyor. Hesabı gerçek çıkış kuralıyla yapınca hem ders servisi hem ML doğru şeyi öğrenir.
- **r02 kararı:** Şu an koşan r02 **durdurulmuyor**. Sebep: r02'nin geçip kalacağını belirleyen sınav zaten gerçekten alınan işlemlerin gerçek çıkışlı sonucuna bakıyor; yani sınav doğru şeyi ölçüyor. Zayıf olan yalnız modelin çalışırken kullandığı hedef ("1R'a ulaştı mı"). r02 ve r03 deneme defterine zaten yazıldı ve sayıldı; durdurmak hiçbir şey kazandırmaz, değiştirmek ise kuralı bozar. Gerçek çıkışa sadık hedef, henüz deftere yazılmamış olan sıradaki tarife (r05) konur; fazladan deneme hakkı harcanmaz.
- **Kaynak:** forex-gold
- **İş büyüklüğü:** orta (5. maddenin altyapısını kullanır)
- **Risk:** Düşük. Sonuçlar daha geç hazır olur (işlemin bitmesini beklemek gerekir). Yeni ML tarifi olarak ön kayıt gerekir.
- **Onay:** [ ] Evet  [ ] Hayır

### 7. Kapıların ve yapay zekâ vetosunun karnesi
- **Ne işe yarar:** Her filtre ve Claude vetosu için haftalık tek satır: kaç sinyali engelledi, engelledikleri kazanır mıydı, maliyeti ne. "Bu filtre kazananları engelliyor" ya da "bu filtre hiç devreye girmiyor" durumunu görünür kılar. Hiç aday üretmediğimiz durumlar (örneğin kapalı tuttuğumuz piyasa koşulları) için de gölge kayıt tutar ki o yasaklar da sınanabilsin.
- **Kaynak:** MATS, AETS, Aurum, polymarket, forex-gold
- **İş büyüklüğü:** küçük–orta
- **Risk:** Yok. Otomatik gevşetme **yapılmaz**; karne yalnız bilgi verir, değişiklik sizin onayınıza gelir.
- **Onay:** [ ] Evet  [ ] Hayır

### 8. ML modelinin süresi dolunca sessizce işlem durmasını önleyen alarm
- **Ne işe yarar:** Doğruladığım bir açık: ML açıkken model paketinin 21 günlük süresi dolarsa bot yeni işlem almayı keser, ama sağlık kontrolü bunu bildirmiyor. Süre dolmadan önce uyarı, dolunca kırmızı alarm ve günlük raporda ML durumu eklenir. Ayrıca dosyaların "yeni ama eski veriden üretilmiş" olması da yakalanır.
- **Kaynak:** PowerTrader_AI, forex-gold, FTMO-TradingBot, AETS
- **İş büyüklüğü:** küçük
- **Risk:** Yok.
- **Onay:** [ ] Evet  [ ] Hayır

### 9. Canlı kararlar ile geçmiş testin birebir karşılaştırması
- **Ne işe yarar:** Her gece dünkü mumları test motorundan geçirip kağıt/canlı botun verdiği kararlarla tek tek karşılaştırır; fark varsa hangi adımda ayrıştığını yazar. Bütün öğrenme verimiz test motorundan geldiği için, ikisi ayrışırsa öğrendiğimiz her şey şüpheli olur. Göstergelerin "ne kadar geçmiş yüklendiğine" göre değişmediği de test edilir.
- **Kaynak:** AETS, freqtrade, MATS
- **İş büyüklüğü:** orta
- **Risk:** Yok (yalnız kontrol).
- **Onay:** [ ] Evet  [ ] Hayır

---

## B. Yakında (kağıt döneminin ilk ayı içinde)

### 10. "Girişimiz yazı-turadan iyi mi?" kontrol deneyi
- **Ne işe yarar:** Aynı çıkış kuralını, aynı piyasa koşulunda rastgele seçilmiş girişlere uygular ve bizim gerçek girişlerle karşılaştırır. Girişlerimiz rastgeleden iyi değilse emeği giriş puanlamaya değil, "hangi piyasa koşulunda işlem yapmalı" sorusuna ve çıkışlara kaydırırız. Tek deney, nereye çalışacağımızı belirler.
- **Kaynak:** forex-gold
- **İş büyüklüğü:** orta
- **Risk:** Paraya risk yok (yalnız araştırma). Deneme defterinde 1 hak harcar.
- **Onay:** [ ] Evet  [ ] Hayır

### 11. Takip eden stopun şeklini denemek
- **Ne işe yarar:** Bizim kendi teşhisimiz: 1R kâra ulaşan işlemlerin %37–47'si zararla kapanıyor, çünkü takip mesafesi ilk riskin yaklaşık 3 katı. Takip mesafesini anlık oynaklığa değil ilk riske ya da giriş anındaki oynaklığa bağlayan üç seçenek geçmiş veride sınanır.
- **Kaynak:** forex-gold
- **İş büyüklüğü:** orta (5. madde bittikten sonra)
- **Risk:** Orta. Kaynak botun kanıtı altın ve çok kısa vadeli; bize taşınacağı kesin değil. Büyük kazananları kesme riski var; bu yüzden yalnız geçmiş veride, ön kayıtlı deneme olarak yapılır (3 deneme hakkı), değişiklik sizin onayınıza gelir.
- **Onay:** [ ] Evet  [ ] Hayır

### 12. Fiyat dışı veri: alıcı/satıcı baskısı ve açık pozisyon geçmişi
- **Ne işe yarar:** Modele yalnız fiyat değil, "agresif alıcılar mı satıcılar mı baskın" bilgisini de verir. Bu veri 2021'e kadar geriye indirilebiliyor, yani hemen sınanabilir. Açık pozisyon ve long/short verisi için canlı toplayıcı zaten yazıldı; sunucuda çalıştığı doğrulanır ve herkese açık arşivden geçmişi tamamlanır.
- **Kaynak:** deepalpha, freqtrade, alphastrike, polymarket
- **İş büyüklüğü:** orta
- **Risk:** Düşük. Veri gürültü çıkabilir; modelde kullanmak ayrı bir ön kayıtlı tarif gerektirir (deneme hakkı harcar). Kilitli dönem indirilmez.
- **Onay:** [ ] Evet  [ ] Hayır

### 13. ML gölge dönemi için izleme kuralları
- **Ne işe yarar:** Model gölgede çalışırken ne zaman "bozuldu" diyeceğimizi önceden sabitler: eksik puan sıfır sayılmaz, yeterli gerçek gözlem birikmeden alarm ya da onay sayımı yapılmaz, "alışılmadık piyasa" ölçüsü eğitim verisine göre sabitlenir, model kendine aşırı güvenmeye başlarsa filtre otomatik kapanır (bot ML'siz temel haline döner; yeniden açmak sizin onayınızla). Almadığımız sinyaller de izlemeye katılır, böylece izleyici aylar değil haftalar içinde işe yarar.
- **Kaynak:** freqai-strategies, freqtrade, AETS, MATS, Aurum, FTMO-TradingBot, polymarket
- **İş büyüklüğü:** orta
- **Risk:** Yok. Kurallar yalnız sıkılaştırır; ML yine yalnız işlem çıkarabilir.
- **Onay:** [ ] Evet  [ ] Hayır

### 14. ML raporlarına "kendimizi kandırmıyor muyuz" satırları
- **Ne işe yarar:** Her ML raporuna ucuz kontrol satırları: aynı model rastgele karıştırılmış veriyle ne kadar iyi görünüyor, yeni eklenen veri gerçekten katkı veriyor mu, kazanç tek bir dönemden ya da tek bir coinden mi geliyor, sonuç şüphe uyandıracak kadar iyi mi (sızıntı işareti). Ayrıca kapıyı geçen bir tarif farklı rastgele başlangıçlarla yeniden koşulur; ortanca sonuç da geçmek zorundadır.
- **Kaynak:** forex-gold, AETS, alphastrike, freqai-strategies, qlib, polymarket, FTMO-TradingBot, deepalpha
- **İş büyüklüğü:** küçük
- **Risk:** Yok. Geçmek zorlaşır (bilinçli). Şu an koşan r02'ye sonradan eklenmez; sıradaki tariflerin ön kaydına yazılır.
- **Onay:** [ ] Evet  [ ] Hayır

### 15. Haftalık model yenilemede "yenisi gerçekten daha mı iyi" kuralı
- **Ne işe yarar:** Yeniden eğitilen model eskisinin yerine ancak aynı veride belirgin biçimde daha iyiyse geçer; değilse eskisi kalır. İki model aynı adaylarda ne kadar farklı karar veriyor, o da raporlanır (çok farklıysa filtre gürültüdür).
- **Kaynak:** AETS, qlib
- **İş büyüklüğü:** küçük
- **Risk:** Yok (yalnız sıkılaştırır).
- **Onay:** [ ] Evet  [ ] Hayır

### 16. Piyasa koşuluna göre sonuç tabloları (önce ölç, sonra karar ver)
- **Ne işe yarar:** Sonuçları piyasa koşuluna (trend yukarı/aşağı, yatay, oynak) ve "o dönemde trend takibi para kazandırdı mı" ayrımına göre düzenli raporlar; işleme girerken ve çıkarken piyasa koşulu ne idi, onu da kaydeder. Hiçbir botta kanıtlanmış "koşula göre davranış değiştirme" kuralı bulamadık; bu yüzden önce ölçüyoruz, kural yazmıyoruz.
- **Kaynak:** forex-gold, FTMO-TradingBot, AETS, MATS
- **İş büyüklüğü:** küçük
- **Risk:** Küçük gruplarda gürültüyü gerçek sanma riski; tablolar örnek sayısını ve belirsizlik aralığını gösterir.
- **Onay:** [ ] Evet  [ ] Hayır

### 17. Alt grup bulgularına otomatik "henüz varsayım" etiketi
- **Ne işe yarar:** "Şu saatlerde daha iyi", "şu coinde daha iyi" gibi alt grup bulguları çok sayıda gruba bakıldığında tesadüfen de çıkar. Raporlar her dökümde gereken çıtayı kendisi hesaplar ve altında kalanı "varsayım" diye işaretler; yıl yıl sonuç satırı da eklenir.
- **Kaynak:** forex-gold
- **İş büyüklüğü:** küçük
- **Risk:** Yok.
- **Onay:** [ ] Evet  [ ] Hayır

### 18. Daha dürüst düşüş (drawdown) ölçümü ve kötü senaryo tablosu
- **Ne işe yarar:** Bugün en büyük düşüşü yalnız kapanmış işlemlerden hesaplıyoruz; açık pozisyonlardaki anlık zarar görünmüyor (kodda doğruladım). Açık pozisyonları da sayan ikinci bir ölçü eklenir ve "−%10 / −%15 / −%20 basamaklarına düşme olasılığı ne, en uzun kayıp serisi kaç işlem" tablosu çıkarılır. Sizin için beklenti ayarıdır.
- **Kaynak:** freqai-strategies, freqtrade, Aurum
- **İş büyüklüğü:** küçük–orta
- **Risk:** Yok. Mevcut eşiklerin hiçbiri yeni ölçüye bağlanmaz.
- **Onay:** [ ] Evet  [ ] Hayır

### 19. Küçük hesapta pozisyon boyutu bozulması kontrolü
- **Ne işe yarar:** Canlıya 250–300 USD ile başlayacağız, geçmiş testler ise 1000 USD ile koştu. Küçük hesapta borsanın en küçük emir tutarı ve adım kuralları yüzünden bazı işlemler reddedilir ya da planlanandan farklı riskle açılır. Bunun ne kadar tuttuğunu coin coin raporlar.
- **Kaynak:** forex-gold
- **İş büyüklüğü:** küçük
- **Risk:** Yok (yalnız rapor).
- **Onay:** [ ] Evet  [ ] Hayır

### 20. Art arda stop olunca mola: önce gölgede ölç
- **Ne işe yarar:** "Kısa sürede çok sayıda stop olduysa bir süre yeni işlem alma" kuralını önce yalnız kayıt olarak işletir; gerçekte uygulanmaz, ne kazandırıp ne kaybettireceği ölçülür. Stop sonrası aynı coinde hemen tekrar girişlerin sonucu da ayrıca raporlanır. Bugün "tek stop" ile "günlük −%5 sınırı" arasında bir koruma yok.
- **Kaynak:** freqtrade, MATS
- **İş büyüklüğü:** küçük (gölge)
- **Risk:** Gölgede yok. Gerçek kurala dönüşürse işlem sayısı azalır; o adım ayrı onay ve ön kayıt ister.
- **Onay:** [ ] Evet  [ ] Hayır

---

## C. Sonra (ilk ay sonrası; daha büyük ya da deneme hakkı harcayan işler)

### 21. Ders servisini geçmiş 5 yılda "sanki canlıymış gibi" yürütmek
- **Ne işe yarar:** Botun kendi kendine ayar düzeltme döngüsünü 2021'den 2026 Nisan'a kadar gün gün oynatır ve "hiç dokunmasaydık" durumuyla karşılaştırır. Canlıda aylar sürecek "bu öğrenme döngüsü işe yarıyor mu" sorusuna birkaç günde yanıt verir.
- **Kaynak:** qlib, freqai-strategies
- **İş büyüklüğü:** büyük
- **Risk:** Orta. Sonuca bakıp ders kurallarını ayarlamak aşırı uyum olur; bu yüzden tek seferlik, ön kayıtlı koşu. Olumsuz sonuç "vazgeçme" gerekçesi sayılmaz.
- **Onay:** [ ] Evet  [ ] Hayır

### 22. Birkaç fikri aynı anda gölgede sınamak
- **Ne işe yarar:** Bugün canlı veride tek bir "ikiz" ile tek bir fikri sınayabiliyoruz. Önceden kaydedilmiş birkaç değişikliği (emir vermeden) aynı anda kayıt altında yürütür; öğrenme hızlanır.
- **Kaynak:** forex-gold, AETS
- **İş büyüklüğü:** orta–büyük
- **Risk:** Orta. Her gölge fikir bir deneme hakkı sayılır ve kapı çıtasını yükseltir; sunucu belleği sınırlı (2 GB). Kaç fikir yürütüleceğine mentor karar verir.
- **Onay:** [ ] Evet  [ ] Hayır

### 23. Denemelerin otomatik sayılması
- **Ne işe yarar:** Bugün deneme defterine satırı elle ekliyoruz; bir kez kayıtsız bir bakış oldu ve sonradan beyan edildi. Her koşu kendini otomatik kaydeder, böylece sayım insan dikkatine bağlı kalmaz.
- **Kaynak:** Aurum (tradingbot)
- **İş büyüklüğü:** orta
- **Risk:** Yok. Sayı artabilir, çıta yükselir (sıkılaştırma).
- **Onay:** [ ] Evet  [ ] Hayır

### 24. Ayar "bıçak sırtında mı" ve sinyal "kırılgan mı" kontrolleri
- **Ne işe yarar:** Bir ayar ancak komşu değerlerde de benzer sonuç veriyorsa güvenilirdir; ders servisinin önerdiği her değişiklik için bu bakılır. Ayrıca girdiler çok az oynatıldığında kaybolan sinyaller "kırılgan" diye işaretlenir ve daha az mı kazandırdıkları geçmiş veride sınanır.
- **Kaynak:** Aurum, MATS
- **İş büyüklüğü:** orta
- **Risk:** Komşu değerleri denemek deneme sayısını artırır; ön kayıt gerekir.
- **Onay:** [ ] Evet  [ ] Hayır

### 25. "Coinler birlikte mi hareket ediyor" ölçüsü ve gerçek risk yoğunluğu göstergesi
- **Ne işe yarar:** On coin çoğu zaman birlikte hareket eder; aynı yönde 8 pozisyon aslında tek büyük bahse yakındır. Raporlara "gerçekte kaç bağımsız bahis taşıyoruz" satırı eklenir. Coinlerin ne kadar ayrıştığı da ileride bir ML tarifinde özellik adayı olur.
- **Kaynak:** qlib, AETS
- **İş büyüklüğü:** orta
- **Risk:** Gösterge olarak yok. Modelde kullanmak ön kayıtlı yeni tarif ister.
- **Onay:** [ ] Evet  [ ] Hayır

---

## D. Önerilmiyor

Bunlar için onay istemiyorum; bilginiz olsun diye yazıyorum. Aksi yönde görüşünüz varsa söyleyin.

| Fikir | Kaynak | Neden almıyoruz |
|---|---|---|
| Yapay zekânın ayar değerlerini doğrudan yazması | forex-gold, polymarket, alphastrike | Kanıt şartı yok; kaynak botlarda zarar eden ayarlara kaydı ve kapatıldı. Bizim "menüden seç + geri al" düzenimiz daha sıkı. |
| Modelin her gün/her işlemde kendini yenilemesi | forex-gold, MATS, freqtrade, polymarket | Sınavsız değişiklik; kapımızı ve ön kayıt kuralını atlar. |
| Kazanca ya da model güvenine göre pozisyon büyütme (Kelly vb.) | FTMO, MATS, alphastrike, forex-gold | ML pozisyon boyutu belirleyemez (kuralımız); kaynaklarda da zarar ettirdi. |
| Zarardan sonra pozisyonu ikiye katlama, stopsuz maliyet düşürme | MATS, PowerTrader_AI | Risk kurallarımıza aykırı. |
| Kârda pozisyona ekleme | FTMO-TradingBot | Kendi denetimleri kazancın 4 kat abartıldığını buldu. |
| Kademeli kâr alma (parça parça çıkış) | alphastrike, freqai-strategies | Kârımızı taşıyan büyük kazananları keser; küçük hesapta parçalar borsa alt sınırının altında kalır. |
| Stopu başa baş noktasına çekme | forex-gold | Kaynakta 8 denemenin 8'inde para kaybettirdi. İsterseniz bir deneme hakkı harcanarak sınanabilir. |
| İşlem yaşlandıkça takip stopunu daraltma | freqai-strategies | Uzun süren kazananları kesme olasılığı yüksek; deneme hakkına değmez. |
| Kazanan işlem öncesi kapıyı otomatik kapatma/açma | MATS | Otomatik gevşetme; bizde yalnız karne (7. madde) ve sizin onayınız. |
| Kayma alarmı çalınca otomatik yeniden eğitim | polymarket, alphastrike | Kayıtsız deneme olur; alarm yalnız uyarır. |
| Birçok sinyal aynı anda gelince boyutu küçültme | FTMO-TradingBot | Tek ve tekrarlanamayan bir teste dayanıyor; mevcut toplam risk sınırlarımız var. |
| Yeni özellikleri önceden eleme taraması | MATS, alphastrike | Aynı veriye fazladan bakış demek; sızıntı riski kazancından büyük. |
| Büyük sinir ağı modelleri (LSTM, Transformer vb.) | deepalpha, qlib, freqAI-LSTM | Verimiz ve sunucumuz için fazla büyük; biri hatalı hedefle eğitilmiş. |
| Sınırsız otomatik ayar taraması (Optuna vb.) | freqtrade, polymarket, FTMO | Deneme sayısı patlar; aşırı uyumun bilinen yolu. |
| Zayıf coinleri son sonuçlara göre kilitleme | freqtrade | Birkaç işleme bakıp sonuç kovalamak; gürültü. |
| Korku-açgözlülük endeksi, tahmini tasfiye kümeleri, altına özgü veriler | deepalpha, forex-gold | Kanıtsız ya da bize uymuyor. |
| Etiket arındırmasında gerçek çıkış zamanı kontrolü | freqai-strategies | Kendi kodumuzda baktım: zaten doğru yapılıyor; iş gerekmiyor. |

---

## E. Uygulayıcılar için: madde ↔ denetim kimlikleri

Kimlikler denetim dosyalarındaki (A.md, B.md, C.md, D.md) numaralardır. D dosyasındaki D1–D18, burada D-01…D-18 olarak yazıldı.

| Madde | İç kimlikler | Not |
|---|---|---|
| 1 | D-07, B-09 | 30 Kasım'dan önce yazılmalı. B-09 = gözlemsel sorular defteri (açık madde sayısı sınırlı). |
| 2 | D-02, A-05, A-06, B-23, C-11 | Kayıt alanları (emir anı fiyatı, gecikme) testnet/canlıdan önce eklenmeli. |
| 3 | D-01, D-04, B-14, D-12 (bant), B-26 | Eşikler kağıt başlamadan sabitlenir. K/Z kuralı düşük güçlü; sıklık + maliyet + fonlama asıl kurallar. CUSUM yalnız aşağı kol, kırpılmış R. |
| 4 | B-01, B-02 (1. adım), C-01, A-10, B-03, A-09, B-27 | Yalnız rapor. Stop çıkışları stopu genişletme kanıtı sayılmaz. |
| 5 | 25c (`cikis-karsi-olgu-spec.md`) + D-13, B-05, C-03, A-04 | B-05/C-03/A-04 `exitcf-v1` ilk gerçek koşusundan ÖNCE spec'e girer. D-13 (kural ablasyonu) = `exitcf-v2` satırı. |
| 6 | A-01 | 25a'ya `real_exit` yöntemi (yeni `version`). ML tarafı: r05 ön kaydında hedef/etiket alınmayan satırlarda da gerçek çıkış replay'i; r02/r03 değişmez. Doğrulama notu: A-01'in "derlem iki getiri tanımını karıştırıyor" iddiası r02 için kısmen yanlış: etiket tüm satırlarda `label_1r`; karışık `net_r` yalnız tanı satırında; bağlayıcı evren alınan işlemler + gerçek net R (`corpus_v2.py:101-112`, ön kayıt §2.2). |
| 7 | B-07, D-17, A-16, A-11 | A-11: aday bastıran bloklar için gölge karar satırı. Otomatik devre dışı bırakma yok. |
| 8 | A-18, D-06, B-25 | Doğrulandı: `strategy_runner.py:259-277` girişleri keser; `health.py` ve Telegram'da ML durumu yok. |
| 9 | B-24, C-12, B-08, C-14 | C-12 = `active` öncesi ön koşul (sıkılaştırma). |
| 10 | A-02 | Strateji deneme defteri, 1 satır; N, pencere, tohum önceden sabit. A-09 plasebo satırı buna bağlı. |
| 11 | A-03 | `exitcf-v2`, 3 seçenek. B-04'ün rejime bağlı trail denemesi ve B-02 2. adım buraya ALINMADI (ayrı onay). |
| 12 | B-20, C-18, B-21, D-15, D-16 | Doğrulandı: mum deposu yalnız OHLCV (`marketdata/sources.py:26`). Düzeltme: OI/LS arşivi var (plan §3.3 C notu: BTC 2020-09, SOL/AVAX 2021-12); "geri doldurulamaz" iddiası yalnız API uçları için doğru. D-15 toplayıcı yazıldı; sunucuda çalıştığı teyit edilecek. |
| 13 | C-06, C-07, C-08, B-12, B-13, D-03, D-08 | ML-2 spec'ine gölge başlamadan önce yazılır. |
| 14 | A-07, A-08, B-17, D-09, C-16, A-15, A-17, C-13, D-18, B-28 | C-13 usul sıkılaştırması (ön kayıt). r02 koşusuna eklenmez; r04+ şablonuna. B-16 cümlesi r06 ön kaydına. |
| 15 | B-15, C-09, B-16 | Haftalık yeniden eğitim spec'i (plan maddesi I). |
| 16 | A-14, D-05, B-18, B-04 (yalnız tablo + `exit_regime` alanı) | Doğrulandı: `exit_regime` alanı yok. B-18 yalnız değerlendirme (geleceği kullanır, canlı girdi olamaz). |
| 17 | A-13 | Bağlayıcı kontrol yapılırsa ön kayıt (yalnız sıkılaştırma). |
| 18 | C-15, D-12 | Doğrulandı: `metrics.py:41-51` gerçekleşmiş bakiye. |
| 19 | A-19 | Canlı 250–300 USD (karar 17 Kas), backtest `wallet_start` 1000. |
| 20 | C-04, B-06 | Gölge bayrak; zorunlu kural ayrı ön kayıt. |
| 21 | C-10 | Tek ön kayıtlı koşu; LLM'siz kural vekili. |
| 22 | A-12, B-10 | Deneme bütçesi mentor kararı. |
| 23 | D-10 | |
| 24 | D-11, B-22 | |
| 25 | C-05, B-19 | |
| Önerilmiyor | C-02, D-14, B-11, C-17 (doğrulandı: eğitim arındırması `label_end_ts`, ileri kalibrasyon `max(label_end_ts, exit_ts)` kullanıyor: `walkforward.py:29-34`, `pipeline.py:115-124`), B-02 2. adım (başa baş), dört denetimin ret tabloları | |
