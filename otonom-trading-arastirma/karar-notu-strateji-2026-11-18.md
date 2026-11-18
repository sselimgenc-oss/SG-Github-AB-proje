# Karar notu: v1b uzun dönemde zararda — kâğıt, testnet, canlı ve araştırma (18 Kasım 2026, mentor)

**Kaynak:** `trader/docs/ml/r02-kapi-raporu.md` §6, `r03-kapi-raporu.md`, `tasarim-kararlari.md` (18 Kasım "açık karar"), `strateji-iyilestirme-plani.md`, `faz-plani.md`. Yeni geri test koşulmadı. Kilitli dönem (2026-05-01 → 2026-11-01) okunmadı.

## 0. Kullanıcı için özet

- Botun bugünkü stratejisi (v1b) 5,3 yıllık geçmişte **para kaybediyor**: 4695 işlem, işlem başı −0,026 R, her 1 birim zarara 0,92 birim kâr, toplam −%60, en büyük düşüş %84,6. Daha önce gördüğümüz artı sonuç yalnız 2021'e aitti.
- Sebep: strateji masraf öncesi biraz kazanıyor (+269), masraf (873) bunun üç katı. Makine öğrenmesi filtresi iki ayrı denemede zararı sildi ama kâra çeviremedi (en fazla +0,04 R).
- Motor, risk kilidi, sunucu, Telegram, ders servisi sağlam; sorun yalnız takılı stratejide. Motor zaten "strateji takılıp çıkarılır" diye yapıldı.
- **Mentor görüşü:** gerçek para, bir strateji görmediği veride artı sonuç gösterene kadar yatırılmasın. Kâğıt botlar ve testnet aynen devam etsin. Bu, "canlıyı yalnız teknik sorun geciktirir" kararınızı değiştirdiği için **tek soru size kalıyor** (§5).

## 1. Mentor kararları (kullanıcı onayı gerekmez)

| # | Karar |
|---|---|
| K1 | **v1b'nin statüsü:** canlı adayı değil, "bilinen eksi taban" (karşılaştırma stratejisi). Uzun dönem sonucu bundan sonraki resmi tabandır; 19b'nin kısa dönem +0,123 R'si taban olarak kullanılmaz. |
| K2 | **Kâğıt botlar (öğrenen + ikiz) v1b ile aynen sürer.** Görevleri: altyapı sınaması, ileri dönem verisi, gölge etiketler, ders servisi, alınmayan sinyal işi. Kâğıtta hafif zarar beklenen sonuçtur, arıza sayılmaz. v1b'yi "düzeltmek" için kâğıtta ayar oynanmaz. `kagit-degerlendirme-plani.md` sayıları değiştirilmez (ön kayıtlı); kontrol noktası raporlarına "referans iyimser, uzun dönem tabanı −0,026 R" notu düşülür. |
| K3 | **Testnet gölge koşusu 14 Aralık'ta başlar**, değişiklik yok. Para riski yok; canlı emir yolunu sınar ve stratejiden bağımsızdır. |
| K4 | **Gerçek para:** §5'teki soru cevaplanana kadar hesaba para yatırılmaz, canlı anahtar sunucuya konmaz. Duman testi (en küçük tutarla 1 long + 1 short) canlı başlangıcından önceki haftaya bağlıdır; canlı kayarsa o da kayar. |
| K5 | **31 Aralık** "canlıya geç" günü olmaktan çıkar, **durum değerlendirmesi** olur: mentor tek sayfa yazar (teknik liste, testnet sonucu, araştırma turunun durumu, canlı ölçütünün neresindeyiz). |
| K6 | **Canlı ölçütü CANLI-K1** bugün, yeni koşu yapılmadan donduruldu (§2). Sonuca bakılarak gevşetilmez. |
| K7 | **ML durmuyor, hedefi değişiyor:** v1b üstüne yeni filtre tarifi (r04+) yazılmaz; iki bağımsız özellik kümesi aynı +0,04 R tavanına takıldı. ML işi şimdi veri toplayıcılar, alınmayan sinyal işi ve yeni taban adayı için derlem hazırlığıdır. Yeni ML turu, bir taban aday CANLI-K1'in 1. adımını geçince açılır. ML yalnız çıkarır; kapı eşikleri aynen. |
| K8 | **Strateji araştırma turu S2** açılır: kilitli dönem öncesinde en fazla **6 ön kayıtlı deneme**, sıra ve kurallar §3'te. Eski "6 denemelik plan"ın yerine geçer (o plan 10 aylık veriye göreydi). |
| K9 | Mühendislik önceliği değişmez: DD-* güvenlik paketleri 14 Aralık'tan önce gelir; araştırma sunucu dışında, motor ekibini bekletmeden yürür. |

## 2. Canlı ölçütü CANLI-K1 (dondurulmuş)

Gerçek para ancak **tek bir dondurulmuş strateji sürümü** aşağıdakilerin hepsini geçince başlar:

1. **Uzun geçmiş (2021-01 → 2026-04, 10 çift, asıl motor, ana maliyet kolu), sınav dilimleri 2022-01 → 2026-04:** işlem başı net beklenti > 0 ve %90 alt sınırı > 0 (gün bloklu bootstrap); kâr faktörü > 1; 4 dilimin en az 3'ü artı; 2024-01 sonrası tek başına artı; en az 800 işlem; herhangi bir çift çıkarılınca hâlâ > 0.
2. **Maliyet stresi** (komisyon ×2 + 5 bp): beklenti ≥ −0,05 R.
3. **Çoklu deneme düzeltmesi:** DSR ≥ 0,95; deneme sayısı = max(10, 1 + S2'de kayıtlı deneme). (10 tabanı, kısa dönemde yapılmış eski keşfin payıdır.)
4. **Kilitli dönem:** yalnız 1–3'ü geçen dondurulmuş aday için, kullanıcı onayıyla, **bir kez** açılır. Geçme: beklenti > 0 ve kâr faktörü > 1. Kalırsa aday biter; kilitli dönem o andan sonra kanıt değeri taşımaz, yeni adaylar için ileri dönem kâğıt verisi kullanılır.
5. **İleri dönem:** aday en az 4 hafta kâğıtta + 14 gün testnette teknik olarak temiz; kâğıt sonucu geri testle çelişmiyor (4 hafta kâr kanıtı değildir, tutarlılık kontrolüdür).
6. Geçerse canlı mevcut kurallarla başlar: 300 USD, işlem başı %0,5, RK-1 (−%20 duruş, %60 taban), kasa tavanı 1500 USD; 1000 USD'ye tamamlama eski kural (3–4 hafta ya da 40–50 işlem, kayma ve komisyon kâğıtla uyumlu).

Dürüstlük notu: bu çıta yüksektir (5 yılda kabaca +0,08 R gerekir). Bugün elimizde bunu geçeceğine dair kanıtı olan aday yok; en erken gerçekçi tarih **ocak ortası–sonu**, geçen aday çıkmazsa tarih yoktur.

## 3. Araştırma seçenekleri (sıralı)

Ortak disiplin: her deneme koşudan **önce** tek dosyada yazılır ve `research/trial_registry.csv`'ye satır olur; koşudan sonra tanım değişirse yeni deneme sayılır; başarısızlar silinmez. Serbest dilimleme/teşhis yalnız **2021-01 → 2023-12**'de yapılır; her deneme tam dönemde bir kez koşar ve §2 madde 1–3 ile ölçülür. Kilitli dönem hiçbir denemede okunmaz.

| Sıra | İş | Neden bu sırada | Deneme hakkı | Emek |
|---|---|---|---|---|
| 0 | **Maliyet dökümü denetimi** (mevcut dondurulmuş koşu, salt okuma) | Kayma ≈ 593, komisyonun (187) üç katı; model 2–5 bp, komisyon 5 bp iken bu oran beklenmez. Ya stop/boşluk dolumları baskın ya da hesap hatası var. Çözülmeden hiçbir maliyet tahmini güvenilir değil. Ayrıca: brüt +269 < komisyon + fonlama 280; yani kayma sıfır olsa bile sonuç ≈ 0. **Yalnız maliyet düşürmek yetmez, brüt kazanç da artmalı.** | 0 (ölçüm) | 0,5–1 gün |
| 1 | **S2-1: 4 saatlik tetik** (kurallar aynı, tetik ve stop 4s) | Stop genişler, R başına maliyet kabaca yarıya iner; kazancın tamamı zaten 12 saatten uzun işlemlerden geliyor. Uzun geçmişte ~1100 işlem bekleniyor (yeterli). Aşırı uyum riski düşük, gerekçe mekanik. | 1 | 1–2 gün (defter `trigger_tf` alanı) |
| 2 | **S2-2: limit (maker) giriş**, tutucu dolum modeli (fiyat limitin ötesine geçmeden dolmuş sayılmaz; dolmayan atlanır) | Giriş komisyonu ve giriş kayması düşer. Risk: kaybedenler dolar, kazananlar kaçar; geri test–canlı farkı. Kâğıttaki "limit dolar mıydı" gölge etiketi ek deneme harcamadan ileri kanıt toplar. | 1 | 3–4 gün |
| 3 | **S2-3: 1 günlük yön filtresi** (önceden planlı, parametresiz) | Ucuz, ama beklenti düşük: r02/r03 bağlam ve rejim bilgisiyle en fazla +0,04 R buldu. Tek başına işareti çevirmesi beklenmez; ancak 1 ya da 2 ile birleşince anlamlı. | 1 | 1 gün |
| 4 | **S2-4: geçenlerin birleşimi** (tek aday) | Kilitli döneme gidecek aday budur. | 1 | 0,5 gün |
| 5 | **S2-5/6: ikinci strateji ailesi** (katalogdan kırılım + retest PA-KIR-01/02, ya da az parametreli 4s/1g kanal kırılımı; 1–3 sonuçları görüldükten sonra tek tanım yazılır) | 1–3 tutmazsa giriş sinyalinin kendisi değişmeli (v1 girişi yazı-turadan ayırt edilemiyor). Yeni parametreler getirir; her tanım en az 1 hak. | 2 (yedek) | 4–6 gün |
| — | **WP-5 çıkış karşı-olgusu** | Planlandığı gibi sürer (kendi ön kaydı `exitcf-v1`, 2 alternatif, yalnız kendi defterimiz, 21 Aralık sonrası girişler). Ders servisi için kanıt üretir; beklenen etki küçük (≤ 0,06 R), canlı yolunu tek başına açmaz. S2 bütçesinden yemez. | ayrı | planlı |
| — | **Rejim/saat filtresi tek başına** | Yapılmaz: r02/r03 bu soruyu cevapladı. Saat filtresi kâğıtta gölge etiket olarak kalır. | 0 | — |
| — | **Daha az çift** | Performansa göre çift seçimi yapılmaz (sıralama dönemler arası ters dönüyor). Likiditeye göre önceden seçim, gerçek dolum verisi gelince yeniden bakılır. | 0 | — |
| — | **Komisyon kademesi** | VIP kademeleri bizim hacimle ulaşılmaz. Komisyonu BNB ile ödeme indirimi (yaklaşık %10, gerçek hesapta doğrulanır) toplam masrafın birkaç yüzdesidir; bedava ama sonucu değiştirmez. Canlı hesabı açarken bakılır. | 0 | — |

Hiçbir deneme geçmezse: tur raporu yazılır, kilitli dönem açılmaz, yeni aileyle S3 ön kaydı yapılır (deneme sayısı birikerek artar). Proje durmaz (17 Kasım çerçeve kararı).

Takvim: sıra 0 → 20 Kasım; S2 ön kayıt belgesi → 21 Kasım; S2-1…3 sonuçları → aralığın ilk yarısı; aday çıkarsa kilitli dönem sorusu size aralık ortasında gelir.

## 4. Aynen kalanlar

- Motor güvenlik işleri (DD-4b … DD-10), RK-1, risk kilidi, kasa tavanı 1500 USD, testnet kampanyası ve 14 Aralık gölge koşusu.
- Kâğıt botlar, veri akışı, veto, sağlık, yedek, Telegram, pano.
- Ders servisi (ilk haftalar yalnız öneri kipi). Dersler beş ayarı küçük adımlarla oynatır; tabanı kâra çevirmesi beklenmez, öğrenme zincirinin sınanması için değerlidir.
- ML kapı eşikleri, ön kayıt kuralı, kilitli dönem, "ML yalnız çıkarır".
- Açık pozisyon / uzun-kısa veri toplayıcıları, alınmayan sinyal gece işi, WP-5/6/7.

## 5. Kullanıcıya soru (tek soru)

**Gerçek para ne zaman başlasın?**

- **A (mentor önerisi): Bekleyelim.** Bir strateji §2'deki sınavı geçene kadar para yatırılmaz. Kâğıt ve testnet sürer. En erken ocak ortası–sonu; aday çıkmazsa uzar. Para kaybı riski: sıfır.
- **B: Küçük başlayalım.** Planlanan tarihte yalnız 300 USD ile, bugünkü stratejiyle; 1000 USD'ye tamamlama sınav geçilene kadar yapılmaz. Kazancı: gerçek borsada kayma ve komisyon ölçülür. Bedeli: beklenen kayıp ayda yaklaşık 3–5 USD; kötü gidişte −%20'de (60 USD) bot durup size sorar; en fazla kayıp 120 USD (%60 taban).
- **C: Plan aynen.** 300 USD, sonra 1000 USD, bugünkü stratejiyle. Beklenen kayıp 1000 USD'de ayda yaklaşık 10–16 USD; duruş −200 USD'de, taban 400 USD kayıpta. Önermiyorum: zararda olduğu bilinen stratejiye para büyütmek öğrenmeye bir şey katmaz.

Cevap gelene kadar K4 geçerlidir (para yatırılmaz); geri dönüşü olmayan hiçbir adım atılmaz.

## 6. Bu notun sınırları

- Tek geri test koşusuna dayanır (sentetik borsa kuralları, işlem başı %0,5 risk). Kayma kaleminin (≈ 593) dökümü henüz doğrulanmadı; §3 sıra 0 bunu çözer.
- Evren bugünün ilk 10 coin'idir (hayatta kalma yanlılığı sonucu olduğundan iyi gösterir, kötü değil).
- B ve C'deki aylık kayıp tahmini geçmiş ortalamadır (ayda ~73 işlem × −0,026…−0,043 R × %0,5); tek ayın sonucu bundan çok sapabilir.
