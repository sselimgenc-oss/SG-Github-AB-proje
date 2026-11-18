# Strateji iyileştirme planı (v1 backtest sonrası)

> **18 Kasım: kullanıcı kararıyla değişti.** Kâğıtta tek düz bot: v1b-kısıtları (15 dk kapalı, R1 kapalı/gölge) ve gölge etiket kararı kalktı; bütün kurulum aileleri × 15dk/1s/4s/1g, 44 enstrüman, ML ve ders ilk işlemden etkin, risk %1 / 16 pozisyon. Bölüm 4'teki canlı seçenekleri (1000 $, %0,5, kademe takvimi) ve takvim **[ASKIDA — kullanıcı yeniden belirleyecek]**. Deneme kayıt/kilitli dönem kuralları araştırma kaydı olarak durur.

_Tarih: 16 Kasım 2026 · Kaynak: `backtest-raporu-v1.md`, `trader/research/trial_registry.csv` (42 kayıt), `strateji-v1.md` · Bu belge için **yeni backtest koşulmadı**; ek kırılımlar mevcut `trades_enriched.csv` dosyalarından (1h ana kol, IS ve WF) hesaplandı. HOLDOUT'a dokunulmadı._

## 0. Kısa sonuç

1. v1'in giriş sinyali yön bilgisi taşımıyor: işlemlerin +1R'ye ulaşma oranı %48–52, +2R'ye %29–32. Bu, rastgele girişin vereceği orana (%50 / %33) eşit. Brüt kazanç (+0,09 R IS, +0,16 R WF) birkaç büyük trend işleminden geliyor; işlem başına 0,18–0,22 R maliyet bunu siliyor.
2. Maliyet sonrası güvenilir pozitif dilim **yok**. En iyi dilim (1h T1 short) IS +0,01 R, WF +0,06 R; standart hata 0,12–0,13 R. WF döneminde piyasa %31–60 düştü ve short yine sıfır civarında kaldı.
3. Öneri: 30 Kasım'da sahte para **v1b** ile başlasın (1h, yalnız T1, 15m ve R1 kapalı, aynı mumda yeniden giriş yasağı). İyileştirme denemeleri kendi backtester'ımız gelince (26–27 Kasım) koşulsun; en fazla 6 ön kayıtlı deneme, holdout yalnız sonda bir kez.
4. Canlı 1000 $ planı için risk bilgisi: bugünkü kanıtla beklenen sonuç sıfır ile ayda yaklaşık −%5…−%8 arası, görülen en büyük düşüş %39–66. Tutar kullanıcının kararı; risk kilidinin içinde kalan seçenek işlem başı riski %1,4 yerine %0,5 ile başlatmak (Bölüm 4).

## 1. Teşhis (1h, ana kol: komisyon ×2 + 2 bp)

### 1.1 Rapordaki kırılımlar

| Dilim | IS n / E[R] | WF n / E[R] | Okuma |
|---|---|---|---|
| T1 (trend geri çekilme) | 554 / −0,06 | 334 / −0,05 | İşlemlerin %88'i; sonucu T1 belirliyor |
| R1 (range) | 73 / −0,33 | 40 / −0,08 | Havuzda n=113, E ≈ −0,24 R. Örneklem yorum için yetersiz |
| Long / trend_up | 299 / −0,17 | 143 / −0,19 | İki dönemde de negatif |
| Short / trend_down | 328 / −0,02 | 231 / +0,03 | Sıfır civarı |
| Çiftler | ADA +0,31, SOL +0,25, XRP −0,28 | ADA −0,34, SOL −0,48, XRP +0,33 | Sıralama dönemler arası ters dönüyor; çift seçimine dayanak yok |
| stop_loss çıkışı | 342 / −1,03 | 205 / −1,03 | İşlemlerin %55'i |
| trailing çıkışı | 264 / +0,88 | 153 / +1,04 | Kazancın taşıyıcısı |
| 15m tetik | 904 / −0,26 | 745 / −0,40 | Brüt bile negatif; her maliyet kolunda negatif |

Çift notu: AVAX iki dönemde de pozitif (+0,23 / +0,17) ama n=52 ve 21; 10 çiftten birinin iki dönemde şans eseri pozitif çıkması beklenen bir durum.

### 1.2 Ek kırılımlar (yeni koşu yok; mevcut işlem listelerinden)

**Kurulum × yön**

| Dilim | IS n / net E[R] (SH) / brüt R | WF n / net E[R] (SH) / brüt R |
|---|---|---|
| T1 short | 290 / +0,011 (0,13) / +0,18 | 212 / +0,056 (0,12) / +0,26 |
| T1 long | 264 / −0,139 (0,10) / +0,06 | 120 / −0,243 (0,12) / 0,00 |
| R1 short | 38 / −0,29 (0,25) / −0,08 | 17 / −0,30 (0,39) / −0,05 |
| R1 long | 34 / −0,37 (0,25) / −0,17 | 22 / +0,08 (0,37) / +0,30 |

**Piyasa yönü (al-tut, aynı dönemler):** IS: BTC +%13, ETH +%15, SOL +%3, ADA −%33. WF: BTC −%31, ETH −%42, SOL −%55, ADA −%60. Yani short, güçlü düşüş döneminde bile yalnız +0,06 R yaptı; long, BTC'nin hafif yükseldiği IS'te de zarar etti. "Short çalışıyor" sonucu çıkmaz; görülen fark büyük ölçüde piyasa sürüşüdür.

**Giriş kalitesi (MFE, R cinsinden)**

| Ölçü | IS | WF |
|---|---|---|
| +1R'ye ulaşan işlem | %52 | %48 |
| +2R'ye ulaşan işlem | %29 | %32 |
| Kazanma oranı | %27 | %31 |
| +1R'ye ulaşıp zararla kapanan (ulaşanların payı) | %47 | %37 |
| Stop olanların medyan MFE'si | 0,37 R | 0,34 R |
| En iyi 10 işlemin toplamı / tüm toplam | +105 R / −57 R | +61 R / −21 R |
| En uzun zarar serisi | 20 işlem | 13 işlem |

İki sonuç: (a) giriş yazı-turadan ayırt edilemiyor; (b) +1R gören işlemlerin %37–47'si zarara dönüyor, çünkü iz süren stop 3 ATR geride ve medyan stop mesafesi yaklaşık 1 ATR; stop ancak yaklaşık +3R görüldükten sonra girişin üstüne çıkıyor.

**Maliyet ve stop mesafesi**

| Stop mesafesi çeyreği | IS net / brüt / maliyet (R) | WF net / brüt / maliyet (R) |
|---|---|---|
| En dar | −0,05 / +0,27 / 0,31 | −0,30 / +0,06 / 0,36 |
| 2. | +0,18 / +0,38 / 0,19 | −0,07 / +0,15 / 0,22 |
| 3. | −0,24 / −0,10 / 0,14 | +0,22 / +0,38 / 0,17 |
| En geniş | −0,27 / −0,17 / 0,10 | −0,06 / +0,06 / 0,12 |

Medyan stop mesafesi fiyatın %1,1–1,3'ü; gidiş-dönüş maliyet %0,24 → işlem başına ≈ 0,2 R. Maliyet stop genişledikçe beklenen biçimde düşüyor, ama brüt kazanç çeyrekler arasında kararsız. "Geniş stop daha iyi" bu veriden çıkmıyor; yalnız maliyetin düştüğü çıkıyor.

Toplam maliyet 723 $ (IS) ve 755 $ (WF); 1000 $ hesapta yılda hesabın yaklaşık 0,8–1,5 katı. Kayma payı yaklaşık altıda bir, funding ihmal edilebilir (7–8 $). Maliyet kolu sonucu belirliyor: ×1 + 2 bp kolunda E[R] −0,017 (IS) / +0,019 (WF); ×2 + 2 bp'de −0,091 / −0,055.

**Elde tutma süresi**

| Süre | IS n / E[R] | WF n / E[R] |
|---|---|---|
| 0–2 saat | 85 / −1,03 | 77 / −0,98 |
| 2–6 saat | 134 / −0,93 | 68 / −0,76 |
| 6–12 saat | 125 / −0,62 | 58 / −0,70 |
| 12–24 saat | 149 / +0,16 | 95 / +0,22 |
| 24–48 saat | 115 / +1,19 | 66 / +1,48 |
| 48 saat + | 18 / +3,97 | 7 / +4,12 |

Stop olanların medyan süresi 3–5 saat; işlemlerin %14–21'i ilk 2 saatte stop oluyor. Bu bir seçim ölçütü değildir (süre sonuçtan sonra bilinir); yalnız zararın hızlı, kazancın yavaş geldiğini gösterir.

**Giriş saati (UTC)**

| Saat | IS n / E[R] (SH) | WF n / E[R] (SH) |
|---|---|---|
| 00–08 | 231 / −0,05 (0,16) | 143 / −0,01 (0,15) |
| 08–16 | 206 / −0,28 (0,09) | 120 / −0,26 (0,13) |
| 16–24 | 189 / +0,06 (0,12) | 108 / +0,11 (0,16) |

08–16 dilimi iki dönemde de negatif (havuzda n=326, E ≈ −0,27 R, t ≈ −3,6; ağırlık long tarafta: −0,52 / −0,57). Yaklaşık 35 hücreye bakıldıktan sonra bulundu ve hem IS hem WF'ye bakılarak görüldü; bu yüzden kanıt değil, **hipotez**.

### 1.3 Maliyet sonrası güvenilir pozitif dilim var mı?

Hayır. Adaylar ve neden yetmedikleri:

- **T1 short:** havuzda n=502, E ≈ +0,03 R, SH ≈ 0,09. Sıfırdan ayırt edilemiyor; düşen piyasada ölçüldü.
- **16–24 UTC girişleri:** +0,06 / +0,11, SH 0,12–0,16. Sonradan bulundu.
- **×1 + 0 bp kolu:** WF +0,063 R, PF 1,10. Kayma sıfır varsayımı gerçekçi değil.

Güvenilir negatif dilimler ise var: 15m tetik (tümü), T1 long (havuzda −0,17 R, t ≈ −2,1), 08–16 UTC girişleri.

## 2. İyileştirme seçenekleri

Sıralama: beklenen değer yüksek, aşırı uyum riski ve emek düşük olan üstte. "Deneme" = kayıt defterine yazılan yeni bir kural/parametre koşusu.

| Sıra | Seçenek | Beklenen etki | Aşırı uyum riski | Emek | Karar |
|---|---|---|---|---|---|
| 0 | **v1b temel:** 15m kapalı, R1 kapalı (sinyal yalnız kayda), aynı mumda stop sonrası yeniden giriş yasağı | Küçük ama kesin: R1 çıkınca −0,09 → yaklaşık −0,06 R; yeniden girişler koşu başına −4…−5 R | Yok. R1 için kural önceden yazılı (`strateji-v1.md` §6.3: örneklem yetmiyorsa kapalı başlar); diğer ikisi hata/teknik | Düşük | Yap. Deneme 1 (yeni temel çizgi) |
| 1 | **1g yön filtresi** (PA-FLT-01; v1'de zaten "sonradan eklenecek, yeni parametre yok" diye yazılı) | Orta. Long zararını hedefler; "long'u kapat" kuralının ilkeli hali | Düşük (önceden planlı, parametresiz) | Düşük-orta; 1g veri 2024-11 öncesine uzatılmalı (EMA ısınması) | Deneme 2 |
| 2 | **+1R'de stopu girişe çekme** (başa baş + maliyet) | Orta. +1R görüp zarara dönen %37–47'yi hedefler. Büyük kazananları erken kesme riski var; `trail_atr` 2,5 IS'te daha kötüydü | Orta (tek yapısal değişiklik, parametre yok; ama fikir aynı veriden çıktı) | Düşük | Deneme 3 |
| 3 | **4s tetik kolu** (rejim 4s kalır, tetik ve stop 4s) | Maliyet 0,2 R → yaklaşık 0,07–0,10 R. Brüt kazancın korunacağına dair kanıt yok | Düşük (mekanik gerekçe) ama n ≈ 150–200/dönem → SH ≈ 0,15 R; sonuç zayıf kanıt olur | Orta (defter şeması `trigger_tf` yalnız 1h/15m kabul ediyor) | Deneme 4 |
| 4 | **Limit (maker) giriş:** tetik kapanışına post-only limit, N mum içinde dolmazsa vazgeç | Giriş tarafında yaklaşık 0,03–0,06 R tasarruf. Ters seçim riski: kaybedenler hep dolar, kaçan kazananlar dolmaz | Orta; asıl risk backtest–canlı farkı | Orta-yüksek; tutucu dolum modeli gerekir, yalnız kendi backtester'ımızda | Deneme 5 |
| 5 | **Saat filtresi** (08–16 UTC giriş yok) | Kâğıt üstünde en büyük etki | Yüksek (sonradan bulundu, WF onu doğrulayamaz) | Düşük | Deneme değil. ~~Sahte parada **gölge etiket**; ileri veriyle sınanır~~ [KALDIRILDI 18 Kasım — kullanıcı: seans yasağı/gölge yok] |
| 6 | `stop_buffer_atr` 0,4 + `trail_atr` 3,5 | En çok +0,06 R; 1 SH içinde | Orta | Düşük | Şimdilik hayır; tek başına işareti çevirmez |
| 7 | Long tarafı kapatma, çift eleme | — | Yüksek (rejime bağlı; çiftler kararsız) | Düşük | Hayır. Yerine sıra 1 |
| 8 | Funding / açık pozisyon filtresi | Bilinmiyor | Orta-yüksek (yeni eşikler) | Orta; Binance OI geçmişi yalnız yaklaşık 30 gün veriyor, IS/WF için veri yok | Ertele. OI şimdiden biriktirilsin; funding her işlemde kayda yazılsın |
| 9 | Kırılım-retest kurulumu (PA-KIR-01/02, v1.1 adayı) | Bilinmiyor; taker maliyetinde kırılım girişleri pahalı | Yüksek (ikinci kurulum, swing N dahil yeni parametreler) | Yüksek | Ertele: 1–4 bittikten sonra, tek ön kayıtlı tanım, en az 3 deneme sayılır |
| 10 | Meta-etiketleme | Sıfır kenarlı sinyalin üstünde çoğunlukla gürültü öğrenir | Yüksek | Yüksek | Canlı sonrası; defter v2 özellikleriyle en az 300 ileri işlem birikince |

### 2.1 Deneme disiplini

- **Bütçe: holdout öncesi en fazla 6 yeni deneme.** Deneme 1–5 yukarıdaki sırayla, Deneme 6 = geçenlerin birleşimi olan tek "v1.1 adayı". Bugünkü 42 kayıtla birlikte hepsi kayıt defterine yazılır; başarısızlar silinmez.
- **Ön kayıt:** her denemenin kuralı, sabitleri ve geçme ölçütü koşudan **önce** yazılır. Koşudan sonra tanım değişirse yeni deneme sayılır.
- **Dönemler:** önce yalnız IS (2024-12-21 → 2025-10-31), ana maliyet kolu. IS kapısını geçen deneme WF'de (2025-11-01 → 2026-04-30) **bir kez** koşulur. Altı maliyet kolu yalnız v1.1 adayı için.
- **IS kapısı:** E[R] ≥ 0, n ≥ 200, sonuç en iyi 5 işlem çıkarılınca çökmüyor ve tek çifte bağlı değil (her seferinde bir çift çıkarılarak bakılır).
- **WF kapısı:** ana kolda E[R] > 0 ve PF > 1; ×2 + 5 bp kolunda E[R] ≥ −0,05.
- **Holdout (2026-05 → 2026-10):** yalnız dondurulmuş v1.1 adayı için, kullanıcı onayıyla, **bir kez**. Hiçbir deneme WF'yi geçmezse holdout açılmaz, sonraki sürüme saklanır.
- **Dürüstlük notu:** n ≈ 370 ile WF'nin standart hatası ≈ 0,09 R. Gerçek beklentisi −0,05 R olan bir kural WF'yi yaklaşık dörtte bir olasılıkla şans eseri geçer; beş denemede en az birinin şansla geçmesi olası. WF tek başına kanıt değildir; holdout ve sahte para dönemi bu yüzden gerekli. Ayrıca Deneme 2, 3 ve saat filtresi WF kırılımları görüldükten sonra yazıldı; bunlar için WF tam bağımsız değil.

## 3. Sahte para başlangıcında (30 Kasım) ne koşmalı?

Kendi backtester'ımız 26–27 Kasım'da geliyor; 30 Kasım'a kadar hiçbir denemenin WF + holdout'u geçmesi gerçekçi değil. Bu varsayımla:

**Öneri: v1b, tam büyüklükte, iki yön açık.**

- 1h tetik, yalnız T1, varsayılan parametreler, 15m kapalı, R1 kapalı, aynı mumda yeniden giriş yok.
- İşlem başı risk tasarımdaki gibi (%1,4 hedef). Sahte parada küçültmenin faydası yok; amaç risk kilidini, emir yolunu ve defteri gerçek büyüklükte sınamak.
- Long açık kalsın: para riski yok, her işlem ileri (out-of-sample) kanıt.
- ~~Her kararda **gölge etiketler** kayda yazılsın (işlemi etkilemez):~~ **[KALDIRILDI 18 Kasım — kullanıcı: kâğıtta gölge yok]** 1g yön filtresi ne derdi, giriş saati dilimi, stop mesafesi/ATR, limit emir dolabilir miydi, +1R'de başa baş stop olsaydı sonuç, R1 sinyali. Böylece dört haftada aday filtreler sıfır ek denemeyle ileri veride ölçülür.
- Ders servisi kararlaştırıldığı gibi 4 hafta yalnız öneri kipinde.

Seçenekler: (a) v1'i olduğu gibi koşmak — R1 ve yeniden giriş hatası bilinen zarar kaynağı, önerilmez; (b) yalnız short — tek rejime uyum, veri yarıya iner, önerilmez; (c) yukarıdaki v1b.

Beklenti: ayda yaklaşık 60 işlem → dört haftada SH ≈ 0,25 R. Sahte para dönemi kârlılığı kanıtlayamaz da çürütemez de; teknik doğrulama ve ileri örneklem toplar.

Bir aday aralık ortasına kadar WF + holdout'u geçerse sahte paraya alınması ayrı bir kullanıcı kararıdır (strateji değişikliği, teknik düzeltme değil; L ve T'ye birlikte uygulanır).

## 4. Canlı 1000 $ planı için risk bilgisi

Tutar ve takvim kullanıcının kararı; faz planına göre kâr/zarar geçişi engellemiyor. Aşağısı karar için bilgi ve seçeneklerdir.

**Bugünkü kanıt ne söylüyor (1h, ayda ≈ 62 işlem, işlem başı %1,4 risk):**

- Ana kol (×2 + 2 bp): E[R] −0,055…−0,09 → ayda yaklaşık −%5…−%8 beklenen kayma.
- Gerçekçi kol (×1 + 2 bp, taker %0,05): E[R] ≈ −0,02…+0,02 → sıfır civarı; düşüş yine %34–49.
- Görülen en büyük düşüş %39 (6 ay) ve %66 (10 ay). En uzun zarar serisi 20 işlem; %1,4 riskle bu tek başına yaklaşık −%25.
- Risk kilidi işini yapıyor (en kötü tek işlem −%1,55), ama kilit tek işlemi sınırlar, birikimli düşüşü değil.

**İşlem başı riske göre yaklaşık düşüş** (aynı işlem dizisi, bileşik ölçekleme; yaklaşık değerdir):

| İşlem başı risk | Düşüş aralığı (WF – IS) | 20 işlemlik zarar serisi |
|---|---|---|
| %1,4 (bugünkü hedef) | %39 – %66 | ≈ −%25 |
| %0,7 | %22 – %42 | ≈ −%13 |
| %0,5 | %16 – %32 | ≈ −%10 |
| %0,35 | %12 – %24 | ≈ −%7 |

**Seçenekler** (hepsi risk kilidinin içinde; %2 üst sınır ve diğer sınırlar değişmez):

- **A.** 1000 $, %1,4 risk, v1b. Yukarıdaki düşüş aralığı aynen geçerli.
- **B.** **[ASKIDA — kullanıcı yeniden belirleyecek]** 1000 $ yatırılır, işlem başı risk %0,5 ile başlanır; kademeli artış kuralı önceden yazılır (örnek: en az 100 canlı işlemde gerçekleşen maliyetle E[R] ≥ 0 → %1,0; ikinci 100'de aynı → %1,4).
- **C.** B'ye ek olarak hesap düzeyinde gözden geçirme eşiği (örnek: tepe değerden −%20'de yeni giriş durur, Telegram'dan sorulur).
- **D.** Sahte para ya da holdout'ta geçen bir aday varsa canlıya onunla, yoksa v1b ile girmek (A–C'den bağımsız).

**Önerim:** takvim aynı kalsın; canlı B + C ile başlasın. Gerekçe: bugün pozitif beklenti kanıtı yok, öğrenme amacı küçük riskle de aynı veriyi toplar, 1000 $'ın ömrü uzar. %0,5'te medyan pozisyon yaklaşık 380–450 $ notional; en küçük emir tutarına (BTC'de yaklaşık 100 $) takılmaz, ama gerçek `exchangeInfo` ile doğrulanmalı.

## 5. Önümüzdeki 7 gün (17–23 Kasım)

**Beklemeli mi?** Teşhis için hayır: dondurulmuş (eski freqtrade dönemi) çıktılar yeterli. Yeni denemeler için **evet**, kendi backtester'ımız (`trader_engine.backtest`) kullanılmalı, eski freqtrade stratejisine kod yazılmaz: Deneme 1–5'in hepsi strateji kodu değişikliği istiyor (kurulum kapatma, 4s tetik, başa baş, limit giriş config seçeneği değil) ve `TraderV1.py` silinecek dosyalar listesinde. Oraya yazılan kod atılır, iki motor arasında fark riski doğar. Backtester'ın ilk işi zaten `1h_IS_f2_s2` ve `1h_WF_f2_s2`'yi yeniden üretmek.

| Gün | İş | Motor inşasıyla çakışma |
|---|---|---|
| 17 Kas | Kararları `tasarim-kararlari.md`'ye yaz: ~~15m kapalı, R1 kapalı (gölge), v1b sahte para başlangıcı~~ (18 Kasım: kaldırıldı, tüm aileler açık); aynı mumda yeniden giriş yasağını `position_manager` şartnamesine ekle | Yok (belge) |
| 17–18 Kas | Ön kayıt: Deneme 1–5'in tam kural tanımı ve Bölüm 2.1 kapıları tek dosyada; kayıt defterine "planlandı" satırları | Yok |
| 18–19 Kas | Teşhis betiği (`research/diag_slices.py`): Bölüm 1.2 tablolarını `trades_enriched.csv`'den yeniden üretir. Bundan sonraki her ek dilimleme yalnız IS'te | Yok (salt okuma) |
| 18–20 Kas | Veri: 1g ve 4s geçmişi en az 2024-01'e uzat; IS/WF için 1m veri; gerçek `exchangeInfo` anlık görüntüsü; hesabın gerçek komisyon kademesi; açık pozisyon (OI) verisini biriktirmeye başla | Yok (indirme; veri indirmek deneme değildir) |
| 19–21 Kas | Gölge etiket şartnamesi (Bölüm 3): hangi alanlar, nasıl hesaplanır. Motor ekibine yalnız şartname olarak; alanlar boş geçilebilir | Düşük; `strategy_runner` (20–23 Kas) yetişmezse Faz B'ye kalır |
| 21–22 Kas | `jobs_v1b.txt` ve deneme iş dosyaları hazır; backtester geldiği gün sıra: çapraz doğrulama → Deneme 1 (IS, WF) → 2 → 3 | Yok |
| 23 Kas | Kullanıcıya Bölüm 4 tablosu; canlı işlem başı risk seçimi (acil değil, aralık ortasına kadar yeter) | Yok |

27 Kasım sonrası: çapraz doğrulama geçince Deneme 1–3 (her biri yaklaşık 10–20 dakika), ardından 4–5. Gerçekçi takvim: denemeler sahte paranın ilk haftasında biter; v1.1 adayı ve holdout kararı en erken aralığın ikinci haftası.

## 6. Bu belgenin sınırları

- Ek kırılımlar tek koşu çiftinden (ana kol) geliyor; dilim sayısı arttıkça şans eseri bulgu olasılığı artar. Tablolar hipotez üretmek içindir.
- Düşüş ölçeklemesi yaklaşık; en küçük emir tutarı, günlük zarar kilidi ve bileşik etki gerçek sonucu değiştirir.
- Kayma komisyona eklenerek yaklaşıklandı; stop-market dolumlarındaki gerçek kayma ancak kendi backtester'ımızın 1m modeli ve sahte para verisiyle ölçülecek.
- Evren bugünün ilk 10 coin'i (hayatta kalma yanlılığı); IS fiilen 10,3 ay.
