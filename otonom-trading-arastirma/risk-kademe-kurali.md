# Risk kademe kuralı (v1, 17 Kasım 2026 — mentor)

Kaynak karar: `tasarim-kararlari.md`, 16 Kasım 2026 "Backtest sonrası" madde 3: canlı 1000 USD, işlem başı hedef risk %0,5 ile başlar; kademeli artış için yazılı kural ve bakiye −%20'de durup değerlendirme eşiği. Bu belge o kuraldır. Kod içermez; koda bağlanması ayrı bir iştir (Bölüm 9).

## Kısa özet

- Canlı, işlem başı **%0,5** riskle başlar (1000 USD'de işlem başına yaklaşık 5 USD kayıp hedefi).
- Risk yalnız basamak basamak artar: **%0,5 → %0,75 → %1,0 → %1,2 → %1,4**. %1,4 risk kilidinin tavanıdır; üstü yoktur.
- Bir üst basamağa çıkmak için ölçülebilir koşulların **hepsi** tutmalı ve **sen Telegram'dan onaylamalısın**. Bot, ders servisi ve makine öğrenmesi riski kendi başına artıramaz.
- Riski **düşürmek** otomatiktir ve onay gerektirmez: hesap tepe değerinden %10 düşerse bir basamak iner, %15 düşerse en alta iner.
- Hesap tepe değerinden **%20** düşerse yeni işlem açılmaz. Açık işlemler zarar durdurlarıyla yönetilmeye devam eder. Mentor 3 gün içinde değerlendirme yazar; devam edip etmemeye **yalnız sen** karar verirsin.
- En erken takvim: ilk artış mart başı; %1,4'e en erken ağustos civarı. Gerçekte daha geç olması, hiç olmaması da geçerli bir sonuçtur.
- Neden bu kadar yavaş: bugünkü geçmiş testte stratejinin kazandırdığına dair kanıt yok (beklenen sonuç sıfır civarı). Kanıt gelmeden riski büyütmek yalnızca dalgalanmayı büyütür.

## 1. Tanımlar

- **R:** bir işlemin, girişte planlanan kayıp tutarına oranla sonucu. −1 R = planlanan kadar kayıp. **Net R** komisyon, kayma ve fonlama düşüldükten sonraki değerdir. Bu belgede her ölçüm net R'dir.
- **Özsermaye:** cüzdan bakiyesi + açık işlemlerin anlık kâr/zararı.
- **Tepe değer:** canlı başlangıcından beri gün sonu özsermayesinin en yüksek değeri; en az yatırılan tutar (1000 USD). Para yatırma/çekme olursa tepe değer aynı tutarda düzeltilir.
- **Düşüş:** (tepe değer − şimdiki özsermaye) ÷ tepe değer.
- **Basamaktaki işlem:** o basamak yürürlükteyken açılıp kapanmış canlı işlem. Kağıt (sahte para) işlemleri sayılmaz.
- **Alt güven sınırı:** ortalama net R − 1,28 × standart hata (tek yönlü %90). Standart hata, ders servisindeki gibi gün kümelerine göre hesaplanır (aynı günün işlemleri bağımsız sayılmaz; `ders-spec.md` `z_cl` yöntemi).

## 2. Basamaklar

| Basamak | İşlem başı hedef risk | 1000 USD'de işlem başı | `target_trade_risk` |
|---|---|---|---|
| K−1 (koruma) | %0,35 | ≈ 3,5 USD | 0.0035 |
| **K0 (başlangıç)** | **%0,5** | ≈ 5 USD | 0.005 |
| K1 | %0,75 | ≈ 7,5 USD | 0.0075 |
| K2 | %1,0 | ≈ 10 USD | 0.010 |
| K3 | %1,2 | ≈ 12 USD | 0.012 |
| K4 (tavan) | %1,4 | ≈ 14 USD | 0.014 |

- Her seferinde en fazla **bir** basamak çıkılır. Basamak atlanmaz.
- K−1 yalnız iniş içindir (Bölüm 4). Kullanılmadan önce en küçük emir tutarına takılmadığı doğrulanmalı (%0,5 için doğrulandı: 858 adayda 0 engel; %0,35 ve küçülmüş bakiye için henüz bakılmadı). Takılıyorsa K−1 kullanılmaz, K0'da kalınır.
- Risk kilidinin diğer sınırları hiçbir basamakta değişmez: işlem başı gerçekleşen kayıp en fazla %2, günlük en fazla %5, toplam açık risk %6, aynı yönde %4, kaldıraç 3–5x.
- Bilinmesi gereken yan etki: basamak yükseldikçe aynı anda açık tutulabilecek işlem sayısı azalır, çünkü %6 ve %4 sınırları sabittir. %0,5'te bu sınırlar pratikte hiç devreye girmez; %1,0'da aynı yönde en fazla 4, %1,4'te aynı yönde en fazla 2 işlem sığar. Yani üst basamakta bot bazı sinyalleri "risk dolu" diye atlar. Bu yüzden her basamakta yeniden kanıt toplanır.

## 3. Basamak çıkma koşulları

Değerlendirme **4 haftada bir** yapılır (her gün bakılmaz; sık bakmak şansla geçme olasılığını artırır). Aşağıdakilerin **hepsi** tutarsa mentor kısa bir rapor yazar ve Telegram'dan onay istenir. Biri tutmazsa bir sonraki 4 haftalık değerlendirmeye kadar beklenir.

| # | Koşul | K0→K1 | Sonraki her basamak |
|---|---|---|---|
| 1 | Basamaktaki kapanmış canlı işlem | ≥ 100 | ≥ 60 |
| 2 | Basamakta geçen süre | ≥ 8 hafta | ≥ 6 hafta |
| 3 | Basamaktaki ortalama net R | ≥ 0 | ≥ 0 |
| 4 | Tüm canlı işlemlerde (aynı strateji ana sürümü) alt güven sınırı | > 0 | > 0 |
| 5 | Son 200 canlı işlemde görülen en büyük düşüş (R cinsinden) × yeni basamağın riski | ≤ %12 | ≤ %12 |
| 6 | Kağıt–canlı tutarlılığı (aşağıda) | tutuyor | tutuyor |
| 7 | Açık olay yok (aşağıda) | son 30 gün temiz | son 30 gün temiz |
| 8 | Son iniş ya da −%20 durmasından beri | ≥ 8 hafta | ≥ 8 hafta |
| 9 | Aynı anda gözlem altında başka büyük değişiklik yok | tutuyor | tutuyor |
| 10 | Kullanıcının Telegram onayı | zorunlu | zorunlu |

Açıklamalar:

- **Koşul 4 asıl kanıttır.** "Strateji kazandırıyor" iddiasının %90 güvenle sıfırın üstünde olması istenir. Kabaca: 100 işlemde ortalama yaklaşık +0,22 R, 300 işlemde yaklaşık +0,13 R gerekir (işlem başı dağılım ≈ 1,7 R varsayımıyla; gerçek sayı canlı veriden hesaplanır). Zayıf ama gerçek bir üstünlük varsa işlem sayısı arttıkça bu koşul kendiliğinden geçilir; üstünlük yoksa geçilmez ve risk %0,5'te kalır. Bu istenen davranıştır.
- **Koşul 5 örnek:** canlıda görülen en kötü düşüş 14 R ise K1'e (%0,75) çıkış için 14 × 0,75 = %10,5 ≤ %12, tutar. K2'ye (%1,0) çıkış için 14 × 1,0 = %14, tutmaz. Amaç: aynı kötü dönem yeni basamakta yaşansaydı %20 durma eşiğine yaklaşılmamasıdır.
- **Koşul 6, kağıt–canlı tutarlılığı.** İki ölçü, ikisi de basamaktaki işlemler üzerinden:
  - (a) Canlıda işlem başı gerçekleşen maliyet (komisyon + kayma + fonlama, R cinsinden), kağıt modelinin aynı işlemler için öngördüğünden en fazla 0,05 R kötü.
  - (b) Canlı bot ile ikizin aynı çift, aynı mum, aynı yönde girdiği eşleşen işlemlerde (en az 30 eşleşme) ortalama fark (canlı − ikiz) ≥ −0,10 R. Eşleşme 30'un altındaysa yalnız (a) bağlayıcıdır ve raporda yazılır.
- **Koşul 7, açık olay.** Son 30 günde şunların hiçbiri olmamış olmalı: bir işlemde gerçekleşen kaybın %2'yi aşması; günlük %5 sınırının aşılması; borsada zarar durdur emri olmayan açık pozisyon; sonucu bilinmeyen emir; borsa–defter uyuşmazlığı; kullanıcının kendi testi dışında acil durdurma (KILL); çözülmemiş kritik sağlık uyarısı.
- **Koşul 9.** Makine öğrenmesi filtresinin etkinleştirilmesi ya da yeni strateji sürümü ile risk artışı aynı döneme denk getirilmez; aralarında en az 4 hafta olur. Hangisi koşullarını önce tamamlarsa o yapılır, diğeri bekler. (ML etkinleştirme kuralındaki "o an gözlem altında başka değişiklik yok" şartıyla aynı ilke; risk artışı da 4 hafta "gözlem altında değişiklik" sayılır.) Ders servisinin beş parametredeki küçük ayarları bu koşulu bozmaz.
- **Sayaçların sıfırlanması.** Yeni strateji ana sürümü: tüm kanıt sıfırlanır ve risk K0'a döner (varsayılan; Bölüm 10 madde 7). ML filtresinin etkinleştirilmesi: basamak korunur, basamak sayaçları (koşul 1–3) sıfırlanır.
- Kâr eden bir dönem tek başına artış nedeni değildir; koşul 1–9'un yerine geçmez.

## 4. Otomatik basamak inme

İniş onay beklemez; aynı gün uygulanır ve Telegram'dan bildirilir. Yalnız **yeni** girişleri etkiler; açık işlemlerin büyüklüğüne dokunulmaz.

| # | Tetik | Sonuç |
|---|---|---|
| 1 | Düşüş ≥ %10 (tepe değerden) | Bir basamak iner (K0'daysa K−1) |
| 2 | Düşüş ≥ %15 | K0 ya da altındaysa K−1; üstündeyse doğrudan K0 |
| 3 | Düşüş ≥ %20 | Bölüm 5: yeni giriş durur |
| 4 | Art arda 12 zararlı işlem (yalnız K1 ve üstünde) | Bir basamak iner |
| 5 | Son 30 işlemin toplamı ≤ −12 R (yalnız K1 ve üstünde) | Bir basamak iner |
| 6 | Tutarlılık bozuldu: son 30 işlemde canlı maliyet modelden > 0,10 R kötü, ya da eşleşen işlemlerde (≥ 20) fark ≤ −0,20 R | Bir basamak iner; neden açıklanana kadar artış dondurulur |
| 7 | Bir işlemde gerçekleşen kayıp %2'yi aştı, ya da zarar durdursuz pozisyon olayı | Doğrudan K0; olay kaydı; artış saati sıfırlanır |
| 8 | Teknik nedenli KILL ya da kritik sağlık olayı (risk/emir yolu dışı) | Basamak korunur; koşul 7'nin 30 temiz günü yeniden başlar |

- Aynı gün birden çok tetik olursa en sert olan uygulanır. Madde 4–5 günde en fazla bir basamak indirir.
- İnişten sonra basamak sayaçları sıfırlanır. Yeniden çıkmak için Bölüm 3'ün tüm koşulları baştan aranır.
- Tepe değer inişte sıfırlanmaz; yalnız −%20 durmasından sonra devam kararıyla yenilenir (Bölüm 5).
- K0'da madde 4–5 uygulanmaz: %0,5'te uzun zarar serileri geçmiş testte de var (en uzunu 20 işlem ≈ −%10) ve bu, madde 1 ile zaten yakalanır.

## 5. −%20 durup değerlendirme

**Tetik:** özsermaye ≤ tepe değerin %80'i. Tepe değer en az 1000 USD olduğundan bu eşik "başlangıca göre −%20"den (800 USD) asla daha gevşek değildir; kâr edilmişse daha erken devreye girer. Her karar adımında ve gün sonunda denetlenir.

**Olduğu anda (otomatik):**
1. Canlı botta yeni giriş kapanır. Bu bir KILL değildir: açık işlemler kapatılmaz, borsadaki zarar durdurları ve normal çıkış kurallarıyla yönetilir. (O anda açık risk, risk kilidi gereği en fazla %6'dır; %0,5 basamağında pratikte %1–2.)
2. Telegram'a kritik mesaj gider: tepe değer, şimdiki özsermaye, açık işlemler, "hepsini kapatmak istersen `/hepsini_kapat`".
3. Ders servisi istatistik ve rapor üretmeye devam eder, ama canlı bota hiçbir değişiklik otomatik uygulanmaz.
4. İkiz (kağıt) çalışmaya devam eder; durma sırasında stratejinin nasıl gittiğini gösteren tek kaynaktır.
5. Giriş kapısı kendiliğinden açılmaz: süre dolunca, bot yeniden başlayınca ya da bakiye toparlanınca da kapalı kalır.

**Değerlendirme (mentor, en geç 3 gün):** kaybın kaynağı (strateji mi, maliyet mi, teknik olay mı), canlı–ikiz–geçmiş test karşılaştırması, işlem sayısı ve güven aralığı, ve seçenekler: (a) K0 ya da K−1'de devam, (b) belirli bir süre yalnız kağıtta devam, (c) strateji değişikliğiyle devam (K0'dan), (d) canlıyı bitirme.

**Devam kararı:** yalnız kullanıcı, Telegram'dan iki adımlı onayla (4 haneli kod). Mentor, ders servisi, ML ya da zamanlayıcı girişi açamaz. Devam edilirse:
- risk K0 ya da K−1 olur (daha yukarıdan devam edilmez);
- tepe değer o anki özsermayeye çekilir (yoksa durma hemen yeniden tetiklenir);
- karar ve gerekçe `tasarim-kararlari.md`ye yazılır.

**İkinci durma ve son taban:** devamdan sonra yeni tepe değerden yine −%20 olursa aynı süreç işler. Ayrıca özsermaye, yatırılan toplam paranın %60'ına (1000 USD için 600 USD) inerse canlı tamamen durur; yeniden başlamak Telegram onayıyla değil, `tasarim-kararlari.md`ye yazılan yeni bir kullanıcı kararıyla olur. (%60 tabanı mentor önerisidir; Bölüm 10 madde 3.)

## 6. Riski kim değiştirebilir

| Kim | Artırma | Azaltma |
|---|---|---|
| Kullanıcı | Evet — Bölüm 3 koşulları tutuyorsa, Telegram onayıyla | Evet, her zaman |
| Bu belgedeki otomatik kural | Hayır | Evet (Bölüm 4–5) |
| Mentor | Hayır; yalnız rapor ve öneri yazar | Evet (ardından kullanıcıya bildirir) |
| Ders servisi | **Hayır** | Hayır (risk ayarları ders servisine tamamen kapalıdır: `ders-spec.md` kural 2) |
| ML filtresi | **Hayır.** Model puanı yalnız "bu aday alınsın mı" sorusuna yarar; işlem büyüklüğünü değiştiremez | Hayır |
| Veto servisi | Hayır; yalnız girişi engelleyebilir | — |
| Panel | Hayır; salt okunur | — |

- Kullanıcı, koşullar tutmadan artış isteyebilir mi? Bu kuralı aşmak ancak `tasarim-kararlari.md`ye yazılan açık bir kullanıcı kararıyla olur (kuralın kendisini değiştirmek demektir); Telegram onayı tek başına yetmez.
- Risk kilidi (`HARD_LIMITS`, `LOCKED_CFG`) bu kuralla hiçbir şekilde değişmez. Bu kural kilidin **içinde** daha sıkı bir katmandır.
- "Puana göre büyüklük" (ML güveni yüksekse daha büyük işlem) bu kuralda yoktur; ileride istenirse ayrı karar gerekir.

## 7. İkiz ile ilişki

- İkiz kağıtta çalışan, ders almayan kontrol koludur; canlıya geçince de kağıtta kalır.
- **İkizin riski canlı botun basamağını aynı gün izler** (çıkışta da inişte de). Neden: basamak değişince "risk dolu" diye atlanan sinyal sayısı değişir (Bölüm 2). İki kol farklı riskte çalışırsa ders servisinin ikiz karşılaştırması, parametre farkını değil risk farkını ölçer. Bugün ikisi de tek değerden (`engine.base.json`) okur; bu böyle kalmalı, risk değeri yalnız öğrenen botun dosyasına yazılmamalı.
- İkizin sonucu basamak **çıkma** kanıtı sayılmaz (sahte para; gerçek dolum yok). İkiz yalnız koşul 6(b) için karşılaştırma tabanıdır.
- −%20 durmasında ikiz durmaz (Bölüm 5 madde 4). O dönemde ikizin riski K0'da tutulur.
- İkiz yine kullanıcı raporlarında görünmez; yalnız mentorun basamak ve değerlendirme raporlarında özet olarak yer alır.

## 8. Takvim beklentisi

- Kağıt: 30 Kasım–27 Aralık, %0,5 riskle (yapılandırmadaki değer). Kağıt işlemleri basamak sayaçlarına girmez; maliyet modelinin tabanını verir.
- Canlı başlangıç (aralık sonu–ocak başı): K0.
- İlk değerlendirme: canlının 8. haftası (şubat sonu–mart başı). Ayda yaklaşık 60 işlemle 100 işlem koşulu o tarihte dolar.
- Her şey ilk seferde tutarsa: K1 mart, K2 nisan sonu, K3 haziran, K4 ağustos. Gerçekçi beklenti daha yavaştır.
- ML etkinleştirmesi (en erken ocak ortası) ile çakışma beklenmez; çakışırsa koşul 9 geçerlidir.

## 9. Kodda nerede zorlanacak (sonraki iş; bu belgeyle yapılmadı)

**İş adı: RK-1 "risk kademe denetimi".** Bugünkü durum: kod yalnız `target_trade_risk ≤ 0.014` denetler (`trader_core/risk.py` `tightened()`, `trader_engine/config.py` `build_risk_config`). Yani biri yapılandırmada 0.005'i 0.014 yapsa kod kabul eder; basamak kuralı şu an yalnız yazılı kuraldır.

RK-1 kapsamı:
1. **Yapılandırma:** `config/risk_ladder.json` — basamaklar ve bu belgedeki eşikler. Eşiklerin kilitli sınırları olur (daha sıkı serbest, daha gevşek hata; risk kilidi ve ders yapılandırmasıyla aynı ilke).
2. **Durum:** geçerli basamak, tepe değer, basamak başlangıç zamanı, durma bayrağı — motorun durum deposunda, kalıcı.
3. **Artış kaydı:** basamak artışı defterde kullanıcı onaylı bir kayıt olmadan geçersizdir (ML `active` kipindeki "onaylı model sürümü defterde yoksa reddet" kalıbının aynısı). Motor başlarken `target_trade_risk`, onaylı basamağın değerinden büyükse başlamaz (`ConfigError`, hata durumunda kapalı).
4. **Giriş kapısı:** `trader_engine/gates.py` içinde düşüş denetimi; −%20'de giriş `entry_gate_closed`, neden `gate:drawdown_review`. Mevcut `entries_blocked_reason` mekanizması kullanılabilir, ama o bugün bazı nedenleri kendiliğinden temizliyor (`engine.py`); durma nedeni kendiliğinden temizlenmemeli.
5. **Otomatik iniş:** Bölüm 4 tetikleri; günlük iş ya da karar adımında; yalnız aşağı yönde yazar.
6. **Telegram:** `/kademe` (durum), basamak artışı onayı ve durma sonrası devam onayı (ikisi de iki adımlı kodla; `/devam` KILL'e özgüdür, bununla karıştırılmaz); günlük 21:00 raporunda bir satır: basamak, tepe değer, düşüş, bir sonraki eşiğe uzaklık.
7. **Testler:** basamak atlama reddi, onaysız artış reddi, iniş tetikleri, durmanın yeniden başlatmada korunması, ikizin aynı basamağı okuması.

**Zamanlama:** madde 2, 4, 5 ve Telegram'ın durma/devam kısmı **canlıdan önce zorunlu** (faz planı madde 26 geçiş kontrol listesine eklenmeli). Artış onayı (madde 3) şubat sonuna kadar yeter; o güne kadar artış zaten yasaktır. RK-1 bitmeden canlı başlarsa −%20 denetimi elle yapılamaz sayılmalı; bu durumda canlı başlangıcı beklemelidir.

## 10. Yalnız kullanıcının verebileceği kararlar

1. **−%20 neye göre ölçülsün?** Karar metni "bakiye −%20" diyor. Bu belge "tepe değerden −%20" olarak yazıldı (başlangıca göre −%20'den asla gevşek değil). Alternatif: yalnız başlangıç tutarına göre (800 USD). Onayın ya da değişikliğin gerekli.
2. **Durma anında açık işlemler:** bu belgede zarar durdurlarıyla açık kalır. Alternatif: hepsi hemen kapatılır.
3. **Son taban:** yatırılan paranın %60'ı (600 USD) önerildi. Başka bir tutar ya da "taban olmasın" senin kararın.
4. **Tavan:** kural %1,4'e kadar izin veriyor. İstersen canlının ilk yılı için tavanı %1,0'da tutabilirsin (mentor önerisi: ilk yıl %1,0).
5. **K−1 (%0,35) koruma basamağı kullanılsın mı?** Varsayılan: en küçük emir denetimi geçerse evet.
6. **Her basamak artışı** ve **her durma sonrası devam** — tek tek, Telegram'dan.
7. **Yeni strateji sürümünde K0'a dönüş:** varsayılan dönmek. O anki basamakta kalmak istersen bu ayrı kararın.
8. **Para ekleme:** 1000 USD'nin üstüne para yatırmak bu kuralın dışında, ayrı karardır.

## 11. Mevcut belgelerle çelişkiler ve açık noktalar

1. **Kağıt riski:** `strateji-iyilestirme-plani.md` Bölüm 3 kağıtta %1,4 öneriyordu; yapılandırma (`engine.base.json`) ve 17 Kasım ML kararı %0,5 kullanıyor. Bu belge %0,5'i geçerli sayar (canlıyla aynı olması tutarlılık ölçümü için de doğrusu). Strateji planındaki cümle eskidi.
2. **Eski örnek kural:** aynı planın B seçeneğindeki örnek ("100 işlemde E[R] ≥ 0 → %1,0; ikinci 100'de → %1,4") bu belgeyle geçersizdir; bu belge daha sıkıdır (basamak atlamaz, güven sınırı ister).
3. **"Girişi durdur, pozisyonu tut" mekanizması yok:** `telegram-spec.md` karar 1'e göre bugün yalnız KILL var ve KILL açık pozisyonları da kapatır; `/durdur` "desteklenmiyor". Bölüm 5 bu mekanizmayı gerektirir; spec zaten "canlıya geçmeden önce yeniden ele alınır" diyor. RK-1 ile birlikte çözülmeli.
4. **Canlı kip henüz yok:** motor `mode: "live"` değerini reddediyor (Faz B). Bu kuralın zorlanması Faz B işleriyle birlikte gelir.
5. **"Hedef ~%1,4" ifadesi:** risk kilidi belgeleri ve faz planı %1,4'ü "hedef" olarak anar. Kilit değişmedi; ama canlıda %1,4 artık hedef değil **tavandır**, geçerli hedef basamak değeridir.
6. **Geçmiş test rakamları:** eşiklerdeki dayanak sayılar (düşüş aralıkları, 20 işlemlik seri, dağılım ≈ 1,7 R) freqtrade dönemi koşularından; 17 Kasım kararına göre asıl motorla birebir kıyaslanmaz. Kağıdın 4. haftasında asıl motor verisiyle bu belgedeki R eşikleri (Bölüm 4 madde 4–5, koşul 5) bir kez gözden geçirilir; gevşetme gerekiyorsa kullanıcıya sorulur.
7. **Eşleşen işlem karşılaştırması (koşul 6b):** ders servisi öğrenen botun parametrelerini değiştirdikçe canlı ve ikiz ayrışır; eşleşme sayısı azalabilir. Bu yüzden (a) maliyet ölçüsü asıl, (b) yardımcıdır.

Bu belge başka hiçbir dosyayı değiştirmedi. Onaylanırsa `tasarim-kararlari.md`ye tek satırlık bir kayıt ve faz planı madde 26'ya RK-1 şartı eklenmelidir.
