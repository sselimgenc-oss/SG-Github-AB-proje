# Faz planı (taslak v2, 15 Kasım 2026 — mentor incelemesi işlendi)

> **[19 Kasım 2026 — kullanıcı kesin kararı, bu belgedeki tüm takvimin ÜSTÜNDEDİR]** Kâğıt testin bitiş tarihi yok; canlı tarihi yok (30 Kasım, 14 Aralık testnet koşusu, 27 Aralık, aralık sonu/ocak başı gibi hedefler kalktı). "Dönem biter, devam mı dur mu" karar noktaları ve "en az N işlem / süre" şartları kaldırıldı; proje zarar etse de sürer, kullanıcı geliştirir. Gerçek paraya geçişin zamanı ve şekli yalnız kullanıcının kararıdır. Teknik ölçümler (ML kalite kapısı, ders emekliliği, risk limitleri) kalır.

> **18 Kasım 2026: kullanıcı kararıyla değişti — güncel karar: tek düz kâğıt bot (öğrenen); gölge kip, ikiz, ayrı deney botu yok; 44 enstrüman, 15dk/1s/4s/1g, tüm kurulum aileleri; ML ve ders ilk işlemden etkin (eşik/haftalık sınır yok); risk %1, 16 pozisyon; seans/hafta sonu yasağı yok. TÜM gerçek para kararları (tarih, tutar, kasa tavanı, duman testi, kademe artışı, adaylık ölçütü) askıda: kullanıcı yeniden belirleyecek. Aşağıdaki canlı/Faz 4 maddeleri tarihsel taslaktır.**

> 18 Kasım 2026: freqtrade kabulü kaldırıldı; parça ilkesi (16 Kasım) gereği kendi motorumuz kullanılıyor.

> **17 Kasım 2026 değişikliği (kullanıcı kararı):** eski madde 29 (makine öğrenmesi) "Sonraki fazlar"dan Faz 2'ye alındı; 19'dan sonra **19a–19d** olarak yazıldı, kağıt dönemindeki devamı **25a–25c**. Diğer numaralar değişmedi. Ayrıntı: `ml-faz-tasarimi.md` (v2).

Hedef: ~~aralık sonu–ocak başı canlı (1000 $, Binance global alt hesap). Teknik sorun çıkarsa takvim kayar; kâr/zarar sonucu geçişi engellemez.~~ **[ASKIDA — kullanıcı yeniden belirleyecek]** (18 Kasım)

## Faz 0 — Hazırlık ve en büyük belirsizlik (16–17 Kasım)
1. Kararları `tasarim-kararlari.md`ye yaz; `mimari-taslak.md`deki "ilk 2 hafta otomatik değişiklik yok" ifadesini "öğrenme ilk günden açık" olarak düzelt.
2. Proje iskeleti: klasör yapısı, kendi motorumuz (`trader/src/trader_engine`; bağımlılıklar `pyproject.toml`/`requirements.lock` ile sabit; Docker Compose yok, systemd birimleri `trader/deploy/`); tek komutla çalışan otomatik testler.
3. **DigitalOcean Frankfurt sunucusu + Binance erişim testi + vadeli dry-run uçtan uca** (451 engeli her şeyi durdurabilir, en başa alındı). Kullanıcıdan DigitalOcean erişimi bu adımda gerekir.

## Faz 1 — Altyapı ve risk (17–22 Kasım)
4. Kendi motorumuzun (`trader_engine`) iki örneği: tek öğrenen kâğıt bot (L); ~~ikiz (T)~~ ikiz bot yok (18 Kasım, kullanıcı: "ikiz bot yok, sil"); yapılandırma `engine.learner.json`, süreç `trader-engine@.service`. (İlk taslakta "freqtrade iki kopya" yazıyordu; 16 Kasım parça ilkesiyle terk edildi.)
5. Binance vadeli, sahte para, izole teminat, long + short.
6. Enstrüman listesi: 44 (20 kripto, 20 ABD hissesi incl. AMD/HD, XAU, XAG, Brent BZ, COPPER); aylık güncelleme şimdi başlar. *(18 Kasım: kullanıcı kararıyla değişti.)*
7. Zaman dilimleri: 15 dk, 1 saat, 4 saat, 1 gün (ilk günden); geçmiş veri. *(18 Kasım: kullanıcı kararıyla değişti.)*
8. Risk kilidi: işlem başı kâğıtta %1, en çok 16 eşzamanlı pozisyon (18 Kasım; eski: %2, hedef ~%1,4), günlük en fazla %5 zarar, toplam açık risk %6, aynı yönde %4, kaldıraç 3–5x, likidasyon zarar durdurmadan uzak.
9. Risk kilidi testleri: sınır aşımı, eşzamanlı işlemler, kayma senaryoları; gerçekleşen kaybın %2'yi geçmediği ölçülür.
10. Piyasa durumu etiketi: trend / yatay / oynak.
11. Kayıt defteri (her işlem gerekçesi ve sonucuyla) ve funding / açık pozisyon verisi.
12. PDF'lerden price action kural listesi. **PDF'ler için son gün 18 Kasım**; gelmezse basit kurallarla başlanır, sonra eklenir.

## Faz 2 — Strateji, Claude ve izleme (23–29 Kasım)
13. Strateji: trendde trend takibi, yatayda ortalamaya dönüş; price action kuralları koda.
14. Geçmiş veriyle test: komisyon iki katıyla da; geleceği görme (lookahead) hatası analizi.
15. API bütçesi (veto ve dersten önce): ayrı workspace, aylık **10 $** (19 Kasım kullanıcı kararı; 18 Kasım'daki 30 $ geri alındı), %70 uyarısı; LLM aday önerisi açık, günlük adet sınırı yok (yalnız 10 $/ay); veto yok.
16. ~~Veto servisi (Haiku, 30 dk): dosya yok / eski / "girme" → işlem yok. Veto testleri.~~ **[KALDIRILDI 18 Kasım — kullanıcı: LLM veto kâğıtta tamamen kaldırıldı]**
17. Ders servisi (Sonnet, günlük, toplu mod), en sade hali: ilk işlemden etkin, her işleme gece ders notu (ertesi gün aday ders; işe yaramazsa emekli; dersler ML'e girdi); işlem/kanıt eşiği ve haftalık sınır yok (18 Kasım); küçük değişikliği uygular, büyüğü Telegram'dan sorar; sınırlı ayarlar; **değişiklik günlüğü ve geri alma düğmesi**.
18. Telegram: günlük rapor 21:00, anlık uyarılar; **acil durdurma komutu ("hepsini kapat")**.
19. Sağlık denetçisi: iç kontroller + dışarıdan 5 dakikalık nabız; **günlük veritabanı yedeği; sunucu yeniden başlayınca kendiliğinden toparlanma testi**.
**Makine öğrenmesi filtresi (eski madde 29; FreqAI'nin kodu değil fikirleri, kendi kodumuz).** Kural: 13–19 (ana yapı) her zaman önce gelir. ML işleri **27 Kasım akşamı kesilir**; o ana kadar bitmeyen ML işi 25a–25c'ye kayar, 20. maddeyi ve 30 Kasım'ı bekletmez. Kağıt başlangıcının motor yüzünden tanınan esnekliği (en geç 4 Aralık) ML için kullanılmaz.

19a. **(30 Kasım'dan önce — zorunlu, küçük)** Sözleşme ve kablolama: motor §13 bağlamına salt okunur model alanı; defterde `ml_filter` atlama nedeni ve ML puanı alanı (yalnız ekleme türü şema göçü); `price_action_v1_ml` sarmalayıcısı; `ml_mode = off | shadow | active`. Kâğıtta ML ilk işlemden etkin (18 Kasım, kullanıcı; kapı/onay/gölge şartı yok); `shadow`/kapı koşulu yalnız canlı için geçerliydi ve askıdadır.
19b. **(30 Kasım'dan önce — hedef)** Geçmiş eğitim derlemi: kendi backtester'ımız v1b'yi 2024-11 → 2026-04 üzerinde yeniden oynatır; alınan ve atlanan **her** adayı planlanan giriş/stop/hedef ve karar anı özellikleriyle yazar; üçlü bariyer etiketi ve gerçek çıkış kuralıyla net R eklenir. Kilitli dönem (2026-05 → 2026-10) taranmaz. Ön koşul: backtester çapraz doğrulaması geçmiş olmalı (motor planında ~27 Kasım); geçmediyse 19b kağıdın 1. haftasına kayar.
19c. **(30 Kasım'dan önce — hedef)** Eğitim hattı, sunucu dışında: Aurum istatistik/bölme/etiket montajı, özellik üretici, lojistik taban + LightGBM, ağaçların JSON dökümü, motor tarafı ağaç okuyucu + eşlik testi, terfi kapısı betiği. Çıktı: 19b derlemi üzerinde uçtan uca bir koşu ve kapı raporu (geçti ya da kaldı; ikisi de kayda geçer).
19d. **(30 Kasım'dan önce — zorunlu)** 20. maddenin kapsamı: `ml_mode=off` ile tam zincir + küçük bir test modeliyle `shadow` yolunun kararları değiştirmediğinin sınaması. ~~Kağıt `off` ile başlar~~ Kâğıt ML etkin başlar (18 Kasım, kullanıcı).

20. Uçtan uca test: sinyal → ~~veto~~ → risk → emir → kayıt → ders (ML: 19d kapsamıyla).

## Faz 3 — Sahte para dönemi (30 Kasım – 27 Aralık)
21. L sunucuda kâğıtta, ders ve ML açık (T yok; 18 Kasım).
22. Haftalık kontrol: hatalar, risk ihlali, API harcaması (ilk hafta sonunda bütçe ayarı).
23. ~~1. hafta: 1 günlük zaman dilimi ve aylık coin güncellemesi eklenir.~~ 1g zaman dilimi ve aylık enstrüman güncellemesi şimdi başlar (18 Kasım).
24. 1. hafta (kullanıcı): mali müşavirle vergi görüşmesi.
25. 2. hafta (kullanıcı): Binance alt hesap, vadeli izni, API anahtarı (para çekme kapalı, sadece sunucu IP'si). Para son gün yatırılır.

**Makine öğrenmesi, kağıt döneminde** (18 Kasım: kâğıtta ML etkindir ve kendi adaylarını önerir; eğitim/araştırma sunucu dışında):

25a. 1. hafta: alınmayan sinyalin sonucu gece işi (atlanan kararların varsayımsal net R'si); 19b/19c'den kalan iş varsa tamamlanır.
25b. 1.–3. hafta: ML-1 araştırması, en fazla 8 ön kayıtlı tarif, 6 denemelik strateji planıyla paralel ve ayrı deneme defteriyle. Hiçbir tarif kapıyı geçemezse tur raporu yazılır, sonraki tur açılır; kağıt ve canlı takvimi etkilenmez. Ayrıntı: ml-guclendirme-plani.md (17 Kasım, kullanıcı onaylı)
25c. ~~Kapıyı geçen model olunca: `ml_mode=shadow`~~ **[KALDIRILDI 18 Kasım — kullanıcı: kâğıtta gölge yok, ML etkin]**

## Faz 4 — Canlıya geçiş (28 Aralık – 4 Ocak) — **[ASKIDA — kullanıcı yeniden belirleyecek; 26–28a tarihsel]**
26. Geçiş kontrol listesi: açık teknik hata yok; risk kilidi testleri geçiyor; **RK-1 (risk kademe denetimi: `trader/docs/motor/12-risk-kademe.md` RK1–RK4 + testnet tatbikatları D-1…D-3) bitmiş** — RK-1 bitmeden canlı başlamaz (−%20 durma ve %60 taban elle denetlenemez); canlıya geçiş operatör adımları (`capital init`, `LADDER_BOTS`, ikizde `ladder_follow`, `/kademe` kontrolü, 1000 USD'ye tamamlamada `capital deposit`) için `11-canli-broker.md` §12.
27. **Teknik duman testi (28–29 Aralık):** gerçek hesapta en küçük tutarla 1 long + 1 short; borsadaki zarar durdur emri, kaldıraç, izole teminat, en küçük emir tutarı doğrulanır. Kâr-zarar testi değildir.
28. Geçerse 1000 $ ile canlı; ilk hafta yakın izleme. **Canlı, ML filtresi etkin olmadan başlar** (`off` ya da `shadow`).
28a. ML filtresinin etkinleştirilmesi (`active`) tarihe değil kapıya bağlıdır: en az 6 hafta gölge + en az 150 puanlı aday (en az 50'si alınmış) + ileri dönemde net R farkı > 0 ve IC > 0 + kullanıcının Telegram onayı + canlının ilk 2 haftası geçmiş + o an gözlem altında başka değişiklik yok. En erken ocak ortası; gerçekçi beklenti ocağın ikinci yarısı.

## Sonraki fazlar (tarih yok)
29. ~~FreqAI (makine öğrenmesi modeli)~~ → 17 Kasım'da Faz 2'ye alındı (19a–19d, 25a–25c, 28a). Burada kalanlar: haftalık kendi kendine yenileme (ML-4) ve kendi adayını üreten ML stratejisi (ML-5).
30. Haber verisi.
31. ABD hisse + emtia. **18 Kasım 2026 notu (mentor):** kullanıcı listesi Magnificent 7 (AAPL, MSFT, NVDA, GOOGL, AMZN, META, TSLA) + altın, gümüş, petrol, bakır. Hepsi Binance USDⓈ-M'de USDT perp olarak listeli (arşivde ilk gün Aralık 2025 – Nisan 2026; XAU/XAG/TSLA/AMZN/COPPER/NVDA/GOOGL/META/CL/AAPL/MSFT, Brent BZ de var), ayrı aracı kurum gerekmez. ~~Geçmiş sınav için yetersiz (çoğu kilitli döneme düşüyor); S2'ye ve learner/ikiz botlara eklenmez. Kripto kapısı (CANLI-K1) sonuçlanınca ayrı ön kayıtla (kendi sınav penceresi, Mag7 küme risk sınırı, hafta sonu/bilanço kuralı, maliyet ölçümü).~~ **[KALDIRILDI 18 Kasım — kullanıcı: 20 ABD hissesi (AMD, HD dahil) + XAU, XAG, BZ, COPPER kâğıt botta şimdi, ilk günden; seans/hafta sonu yasağı yok.]** Petrol: kullanıcı kararı "dünyada geçerli olan" → **Brent (BZUSDT)**, WTI (CLUSDT) alınmaz. Şimdi yalnız sunucudan `exchangeInfo` ile komisyon/fonlama/en küçük emir/kaldıraç/testnet durumu not edilir.
32. Üç projeyi tek ekrandan yönetme (copytrade, 1l3a, bu bot) — zorsa yapılmaz; standart durum çıktısı o zaman eklenir.
