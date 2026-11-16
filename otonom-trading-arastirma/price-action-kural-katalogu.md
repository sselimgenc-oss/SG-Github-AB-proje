# Price Action Kural Kataloğu (birleştirilmiş)

## 1. Giriş

**Amaç.** Yedi price action kaynağından ayrı ayrı çıkarılan yaklaşık 194 kuralı tek bir tekilleştirilmiş katalogda toplamak. Katalog, sonraki aşamada kural motoruna ve backtest'e girdi olacak ham kural havuzudur. Bir kuralı katalogda görmek onun kârlı olduğu anlamına gelmez.

**Kaynaklar (kısaltma, dosya öneki, kitap).**

| Kısa | Önek | Kaynak |
|---|---|---|
| AN | 12 | Ansiklopedi (seviye, SFP, pin bar, piyasa yapısı, Fibonacci) |
| TE | 10 | Rayner Teo (piyasa yapısı, mum formasyonları, stop, ATR takip) |
| PA | 08 | Pansheriya (giriş düzeyi: trend, range, kırılım, formasyonlar) |
| DA | 05 | Damir Range (4 saatlik range ticareti) |
| MI | 02 | Minev (swing, MA, formasyonlar, volatilite, Ross/Brooks bölümleri) |
| BR | 23 | Brooks sözlüğü (iç/dış bar, H2/L2, salınım, ölçülen hareket) |
| WO | 31 | Galen Woods (kurulum katalogu: tıkanıklık, bölgeler, yavaşlama, zayıf geri çekme) |

**Yöntem.** Her kitap parçalara bölünüp ayrı ayrı çıkarıldı (17 dosya). Bu belge o çıkarımların birleşimidir. Aynı fikri anlatan kurallar tek ID altında toplandı. Kaynaklar arasındaki tanım farkları kuralın içinde "Fark" notu olarak, çözülemeyenler Bölüm 5'te listelendi.

**Kaynak gösterimi.** `12b-K3 s.1213–1262` şu demektir: 12 numaralı kitabın 2. parçasındaki 3. kural, ham metnin (`pdftxt/12.txt`) 1213–1262. satırları. Parça harfleri: a, b, c = ilgili dosyanın part1, part2, part3 çıkarımı. Satır numaraları ham metne aittir.

**Sayı kuralı.** `(varsayılan)` etiketli her sayı kitaptan gelmez. Çıkarımı yapan model eksik sayıyı (ATR katı, pencere, tolerans, oran) doldurmak için önermiştir. Bunlar başlangıç değeridir ve backtest ile taranıp belirlenecektir. Etiketsiz sayılar kitapta açıkça geçer. Aksi belirtilmedikçe `ATR` = ATR(14)'tür (TE ve MI'nin bazı bölümleri ATR(20) kullanır, ayrıca yazıldı). Kitapların çoğu forex/hisse/vadeli için yazılmıştır, kripto 7/24 olduğundan gap/seans kuralları dışarıda bırakıldı. Pip/tik değerleri ATR oranına çevrildi.

**Notasyon.** L = long, ayna = short için simetrik. `o,h,l,c` = açılış, yüksek, düşük, kapanış. R = giriş-stop mesafesi.

**Pozisyon ve risk uyarısı.** Bölüm "Pozisyon-risk"teki yüzdeler kitap bilgisidir. Bizim risk kilidimiz her kitabın boyutlandırma önerisini ezer. Kural motoru yalnızca giriş, stop ve hedef üretir. Lot/miktar risk kilidinden gelir.

**Netlik ölçeği.** yüksek = sayısal koşul kitapta açık. orta = yapı açık, eşikler varsayılan. düşük = öznel, görsele bağlı veya tanım eksik. Birleşik kuralda değerlerin çoğunluğu alındı.

**Sözlük notu.** İstenen `../sozluk.md` dosyası depoda bulunamadı. Terimler (kırılım, retest, SFP, tıkanıklık vb.) çıkarım dosyalarındaki kullanımla tutarlı tutuldu.

---

## 2. Katalog

### 2.1 Piyasa yapısı

### PA-YAP-01 — Swing tepe/dip (fraktal)
- **Rejim:** her ikisi · **Yön:** yok (etiketleme, diğer kuralların girdisi)
- **Tanım:** swing tepe: `h[i] = max(h[i-N..i+N])`, swing dip simetrik. Onay N bar gecikmeli (lookahead yok). N değerleri: MI 2 (kitap), BR 1 (kitap, komşu bar), DA 2, WO 2, PA 3, TE 5, AN 5 (LTF) ve 10 (HTF "derin salınım") (hepsi varsayılan, MI/BR hariç). Başlangıç: N=2 ve HTF için N=10 (varsayılan), taranacak.
- **Giriş / stop / hedef:** yok. **TF:** hepsi.
- **Fark:** WO swing tanımını başka cilde atıf yapıp vermiyor. MI swing aramayı yalnız yönlü hareket sonunda önerir (opsiyonel filtre).
- **Kaynaklar:** 12b-K3 s.1213–1262; 12c-K6 s.2254; 10a-K1 s.786–788,1068–1112; 08a-K1 s.92–110,373–413; 05a-K2 s.2831–2893; 02a-K1 s.87–90,236–242; 02c-K1 s.2625–2660; 23a-K6 s.757–768; 31b-K1 s.5222–5263 (N=2 varsayılan).
- **Netlik:** yüksek · **Kaynak sayısı:** 7 (AN, TE, PA, DA, MI, BR, WO)

### PA-YAP-02 — Trend / range etiketi (HH-HL, LH-LL) ve trend tespiti
- **Rejim:** trend / range etiketi · **Yön:** her ikisi
- **Tanım:** yükseliş: son 2 swing tepe ve 2 swing dip ardışık yükseliyor (HH+HL). Düşüş: LH+LL. İkisi de değilse konsolidasyon (2+2 minimum varsayılan). Trend bozulması: yükselişte `c` < son swing dip (PA). BR ek ölçüleri: son 3 kapanış artan, son 20 barın %50'den fazlası EMA20 üstünde (varsayılan %50), 20 ardışık bar EMA20'ye değmezse güçlü trend, mikro kanal: son 5 barda en fazla 1 geri çekme barı (varsayılan). DA "derece" kuralı: küçük dalga, ancak sonraki itiş kendi uzunluğunun ≥4 katıysa etikete girer (varsayılan, OCR sayısı güvenilmez).
- **Giriş / stop / hedef:** yok. **TF:** hepsi.
- **Kaynaklar:** 12b-K3; 10a-K1 s.786–788,1068–1076; 08a-K1 s.373–437; 05a-K3 s.2438–2552,2915–2918; 02a-K2 s.110–120; 23a-K5,K6,K11 s.523–531,883–891,908–910,948–951.
- **Netlik:** orta · **Kaynak sayısı:** 6 (AN, TE, PA, DA, MI, BR)

### PA-YAP-03 — Yapı kırılımı (BOS) ve karakter değişimi (CHoCH)
- **Rejim:** trend · **Yön:** her ikisi
- **Tanım:** boğa BOS: `c[i]` > en son derin SH (HTF, kapanış bazlı). Ayı BOS: `c` < derin SL. CHoCH: yükseliş trendinde son LTF HL'nin (altyapı, N=2 varsayılan) altında ilk kapanış. CHoCH tek başına uyarıdır, BOS onaydır.
- **Giriş:** BOS anında girilmez, geri çekilme beklenir (PA-TRD-01, PA-SDR-05, PA-KIR-02). CHoCH ile agresif giriş kitapta çelişkili (Bölüm 5). **Stop:** PA-STP-01. **Hedef:** yeni derin salınım. **TF:** HTF 4s/1g.
- **Kaynaklar:** 12b-K4,K5 s.1224–1249,1306–1467; 12a-K8 s.973–975.
- **Netlik:** orta (BOS yüksek, CHoCH orta) · **Kaynak sayısı:** 1 (AN)

### PA-YAP-04 — Dört faz sınıflaması (SMA200)
- **Rejim:** birikim/dağıtım = range, ilerleme/gerileme = trend · **Yön:** her ikisi
- **Tanım:** birikim: önceki düşüşten sonra M=150 bar (günlük, "≈5 ay", varsayılan) yatay bant, SMA200 eğimi ≈0 (10 bar karşılaştırma, varsayılan), kapanışlar SMA200 çevresinde. İlerleme: bant üstüne `c` + SMA200 yukarı + HH/HL. Dağıtım ve gerileme ayna. Sınıflandırıcıdır, tek başına sinyal değil.
- **Giriş / stop / hedef:** yok. **TF:** kitap günlük, ölçeklenmesi varsayılan.
- **Kaynaklar:** 10a-K2 s.736–884.
- **Netlik:** düşük · **Kaynak sayısı:** 1 (TE)

### PA-YAP-05 — Geri çekilme derinliği ve trend gücü sınıflaması
- **Rejim:** trend · **Yön:** her ikisi
- **Tanım (TE):** `retr = (bacak_ucu - geri_çekilme_dibi) / bacak_uzunluğu`. Güçlü ≤0,38 (MA20 çevresi), sağlıklı ≤0,50 (MA50), zayıf ≥0,62 (MA200). "Yakın" = 0,5×ATR (varsayılan). %50–62 arası sınıfsız kalıyor. Zayıflama: son geri çekilme range'i önceki ×1,2'yi aşıyor ve trend bacağı ortalama range'i düşüyor (varsayılan). Trend bacağı mumu: gövde ve range son N=20 ortalamasının üstünde (varsayılan).
- **Tanım (WO):** mum sayımı. Geri çekilme güçlüdür ancak pencerede 3 ardışık ters mum veya 2 ardışık ters trend çubuğu (gövde/aralık >0,5) varsa. Yoksa zayıf geri çekilmedir.
- **Giriş:** güçlü trendde kırılım, sağlıklı trendde MA50 geri çekilmesi, zayıf trendde MA200/direnç (TE). WO'da PA-TRD-03. **Stop / hedef:** PA-STP-01, PA-HDF-06.
- **Fark:** TE oran bazlı, WO mum sayısı bazlı. İkisi birlikte backtest edilebilir.
- **Kaynaklar:** 10c-K2,K3,K21 s.2463–2570; 31a-K26 s.5144–5220; 31b-K1 s.5222–5398.
- **Netlik:** orta · **Kaynak sayısı:** 2 (TE, WO)

### 2.2 Destek-direnç ve bölgeler

### PA-SDR-01 — Yatay destek/direnç bölgesi (bant)
- **Rejim:** her ikisi · **Yön:** simetrik
- **Tanım:** seviye çizgi değil bölgedir. Merkez: swing tepe/dip kümesi (≥2 dokunuş). Bölge toleransı/genişliği (hepsi varsayılan): AN 0,25, PA 0,3, DA 0,2, MI 0,2, TE 0,5 (yarı genişlik) ×ATR. Başlangıç 0,25×ATR (varsayılan), taranacak. Dokunuş: bar high/low bölgeye girer, ardışık barlar tek dokunuş (AN). Seviye giriş TF'sinden büyük/eşit TF'den alınır (AN, MI). Güçlü seviye: son 20 barda ≥2 dönüş (MI, L=20 varsayılan) veya birkaç kaynağın çakışması (MI, WO). Seviye sayısı sınırı: MI kanal ≤2, seviye ≤3 (kitap); AN ≤5 aktif seviye (varsayılan). DA: sınırlar bölge okunur, çizildikten sonra değiştirilmez.
- **Giriş:** bu kural girişi tanımlamaz, bkz. PA-KIR-02, PA-YTY-02, PA-TRD-05. **Stop / hedef:** PA-STP-01, PA-HDF-02.
- **Kaynaklar:** 12a-K1 s.105–283,404–420; 10a-K4 s.899–972,1098–1102; 08a-K2 s.137–168,427–431; 05a-K4 s.2954–3224,3515–3520; 02a-K4 s.249–253,633–641; 31b-K6 s.5830–5858,6009–6033.
- **Netlik:** orta · **Kaynak sayısı:** 6 (AN, TE, PA, DA, MI, WO)

### PA-SDR-02 — Seviye gücü ve dokunma sayısı
- **Rejim:** her ikisi · **Yön:** simetrik
- **Tanım:** her seviye için `touch_count`, reaksiyon şiddeti (ATR katı), yenilik ve yaş kaydedilir. Kitaplar dokunma sayısının yönünde ayrışır (Bölüm 5): çok dokunma zayıflatır (AN, PA ≤4 varsayılan üst sınır, DA 3. dokunuştan sonra dikkat, TE başlığı), kırılma olasılığını artırır (TE gövdesi), güçlü seviye ≥2 dönüştür (MI). TE ek: direnç yakınında son 3 swing dip yükseliyorsa (alçalan zirve için tersi) kırılım yanlısı güç/zayıflık işareti (3 varsayılan).
- **Karar:** `touch_count` özellik olarak üretilir, eşik ve yön backtest ile belirlenir (tarama aralığı 2–4, varsayılan). Güç skoru ağırlıkları kitapta yok.
- **Giriş / stop / hedef:** filtre/skor, yok.
- **Kaynaklar:** 12a-K11,K1 s.270–283,506–508; 10a-K4,K5,K6 s.942–961,1061–1112; 08a-K2 s.166–168; 05a-K5 s.3145–3165; 02a-K4 s.633–641.
- **Netlik:** düşük · **Kaynak sayısı:** 5 (AN, TE, PA, DA, MI)

### PA-SDR-03 — Önceki periyot seviyeleri ve pivot noktaları
- **Rejim:** her ikisi · **Yön:** simetrik
- **Tanım:** önceki gün/hafta/ay `o,c,h,l` seviye sayılır (AN). Pivot: `PP=(H+L+C)/3`, `R1=2PP-L`, `R2=PP+(H-L)`, `R3=H+2(PP-L)`, `S1=2PP-H`, `S2=PP-(H-L)`, `S3=L-2(H-PP)`. MI metnindeki `/3` eksikliği düzeltildi. Gün sınırı UTC 00:00 (varsayılan). `PP` üstü yükseliş, altı düşüş yanlılığı (MI). En fazla ilk 3 seviye kullanılır (MI).
- **Giriş:** seviye olarak PA-KIR-02 / PA-YTY-02'ye girer. **Hedef:** R1/S1 (varsayılan). **TF:** günlük pivot 15dk/1s grafikte.
- **Kaynaklar:** 12a-K2 s.521–711; 02a-K17 s.417–477.
- **Netlik:** yüksek (pivot formülü), orta (kullanım) · **Kaynak sayısı:** 2 (AN, MI)

### PA-SDR-04 — Yuvarlak sayı seviyeleri
- **Rejim:** her ikisi · **Yön:** simetrik
- **Tanım:** forex'te "00" ile biten fiyatlar. Kripto karşılığı fiyat büyüklüğüne göre 10^k basamak (varsayılan). Tepki toleransı 0,1×ATR (varsayılan). Giriş mantığı PA-YTY-02 (red) veya PA-KIR-02 (retest). Hedef: sonraki yuvarlak sayı (varsayılan).
- **Kaynaklar:** 02a-K18 s.553–620.
- **Netlik:** orta · **Kaynak sayısı:** 1 (MI)

### PA-SDR-05 — Fibonacci geri çekilme bölgesi ve girişi (altın cep, kesişme)
- **Rejim:** trend · **Yön:** her ikisi
- **Tanım:** bacak A→B (swing, fitilden fitile). `L_r = B - r*(B-A)`, `r` = 0,382 / 0,5 / 0,618 (AN, MI kitap). AN altın cep 0,618–0,66 (alternatif 0,65). WO bölge %50–%61,8, itiş koşulu en az 2 trend mumu ve 3 ardışık mum (kitapta "ideal"). Kesişme: iki fib setinin seviyesi ≤0,25×ATR (varsayılan). A/B derin salınımdan (HTF N=10 varsayılan). 0,618 altında kapanış ivme kaybı işaretidir (AN).
- **Giriş:** bölgede limit merdiven, 0,618/0,5/0,382'de eşit pay (AN, varsayılan pay) veya bölgede onay mumu (MI, WO). Kitaplar tek başına fib girişine tepki tanımı vermez. **Stop:** fib seviyesi stop olarak kullanılmaz (AN), yapı stopu: A'nın ötesi, MI 0,786 ötesi (varsayılan). **Hedef:** PA-HDF-04.
- **Fark:** WO "sadece yüzde"yi kullanıp fibe güvenmediğini söyler, MI'nin Ross/Brooks bölümü de fibin önemli rol oynamadığını belirtir (Bölüm 5).
- **Kaynaklar:** 12b-K6,K7,K8 s.1573–1964; 12c-K4 s.2118–2140; 02a-K16 s.498–549; 31b-K5 s.5830–5975.
- **Netlik:** orta · **Kaynak sayısı:** 3 (AN, MI, WO)

### PA-SDR-06 — Trend çizgisi ve kanal
- **Rejim:** trend (MI), range girişi filtresi (DA) · **Yön:** her ikisi
- **Tanım:** yükseliş: son 2 swing dipten doğru, karşı uçtan paralel = kanal. Test: `|c - çizgi| ≤ 0,2×ATR` (varsayılan). DA: sınıra giden hareketin son P=2 düzeltme swing'inden çizgi, giriş için kapanışla çizgi kırılımı zorunlu filtre, çizgi çizilemiyorsa filtre atlanır (varsayılan).
- **Giriş:** çizgi testinde trend yönünde (MI), kırılım+onay mumu (DA). **Stop:** çizginin 0,3×ATR ötesi (MI, varsayılan). **Hedef:** karşı kanal çizgisi (MI).
- **Not:** PA, TE, BR, WO'da trend çizgisi öznel çizim sayıldı, kodlanmadı.
- **Kaynaklar:** 02a-K3 s.133–141,309–340,629–631; 05a-K9 s.3636–4072.
- **Netlik:** orta · **Kaynak sayısı:** 2 (MI, DA)

### PA-SDR-07 — Sıkışıklık bölgesi ve kurulumu (Woods)
- **Rejim:** range · **Yön:** her ikisi
- **Tanım:** tıkanıklık barları (PA-YTY-05) `s..e-1` için `zh = max(c)`, `zl = min(c)` (kitap high/close konusunda tutarsız, kapanış varsayılan). Kesişen bölgeler birleştirilir, yakın olanlar aralık ≤0,25×ATR ise (varsayılan). Birleşik bölgede işlem yok (varsayılan). Uzun kurulum: boğa barı `l[k] > zh`, fiyat bölgeye dönüp `l[m] ≤ zh` ve `l > zl` kalır, tetik boğa barı `t`. Geçersiz: `c < zl`. Short ayna.
- **Giriş:** `h[t]` + tik stop-buy, yalnız `t+1` barında (tik = 0,05–0,1×ATR varsayılan). **Stop:** `l[t]` − tik (varsayılan, kitapta yok). **Hedef:** 2R (varsayılan).
- **Kaynaklar:** 31a-K6,K7,K8,K9 s.1077–1298.
- **Netlik:** orta · **Kaynak sayısı:** 1 (WO)

### PA-SDR-08 — Basınç bölgesi ve kurulumu (Woods)
- **Rejim:** her ikisi · **Yön:** her ikisi
- **Tanım:** üç ardışık barın alt gölge aralıkları `[l, min(o,c)]` kesişimi ≥ `T = 0,10×ATR` (1s ve üstü 0,20×ATR, varsayılan; kitapta 2 tik). Bölge `zl = min(l)`, `zh = min(min(o,c))`. Üst gölge için ayna. Kurulum: bölgeyi kesen boğa barı `j` ve `c[j] > zh`. Tıkanıklık içinde oluşan bölge atlanır (varsayılan). Geçersiz: `c < zl`.
- **Giriş:** `h[j]` + tik stop-buy (izleyen 1 bar). **Stop:** `l[j]` − tik (varsayılan). **Hedef:** 2R (varsayılan).
- **Kaynaklar:** 31a-K17–K20 s.3654–3854.
- **Netlik:** orta · **Kaynak sayısı:** 1 (WO)

### PA-SDR-09 — Kaygı bölgesi ve kurulumu (Woods)
- **Rejim:** trend sonu · **Yön:** her ikisi
- **Tanım:** karşı-trend kurulum barı `c` tetiklenince (`h[c+1] > h[c]`) bölge `[l[c], h[c]]`. Geçersiz: `l < zl` veya `h ≥ zh` (kitap "ulaşır/geçer" arasında tutarsız). Kurulum: bölgeyle kesişen boğa barı. Dış bar bölge oluşturmaz, "ikinci saldırı" gerekir. Düşük TF'de nadir.
- **Giriş:** `h[b]` + tik stop-buy. **Stop:** `l[b]` − tik (varsayılan). **Hedef:** 2R (varsayılan).
- **Kaynaklar:** 31a-K21–K25 s.4352–4619.
- **Netlik:** düşük (bölge yön eşleşmesi tutarsız) · **Kaynak sayısı:** 1 (WO)

### 2.3 Kırılım ve sahte kırılım

### PA-KIR-01 — Kırılımın tanımı ve onayı
- **Rejim:** trend / range sınırı · **Yön:** her ikisi
- **Tanım:** kırılım fitille değil kapanışla: `c[i] > R` ve `c[i-1] ≤ R` (L). Net kırılım: `c > R + 0,2×ATR` (PA varsayılan). N-bar kırılım (TE kitap): `c[i] > max(c[i-N..i-1])`, N ∈ {50,100,200}, trend filtresi `c > MA200`. Onay filtreleri (kitapta niteliksel, hepsi opsiyonel): hacim `> 1,5×SMA(vol,20)` (AN, PA varsayılan), gövde/range ≥0,6 (AN varsayılan). Tıkanıklık çıkışı: `c[e] > h[e-1]` (WO kitap).
- **Giriş:** tek başına giriş değil. TE: sonraki barın açılışında piyasa veya sinyal barı üstüne stop. Diğerleri PA-KIR-02. **Stop:** kırılan seviyenin 1×ATR ötesi (TE kitap); tampon farkı için PA-STP-01. **Hedef:** TE iz süren (PA-STP-02) veya PA-HDF-03.
- **Kaynaklar:** 12a-K3 s.112–125; 10a-K5 s.989–1020; 10c-K1 s.2222–2260,2770; 08a-K4 s.701–757; 02a-K14 s.1125–1255; 23a-K9 s.258–263; 31a-K3 s.467–476.
- **Netlik:** orta · **Kaynak sayısı:** 6 (AN, TE, PA, MI, BR, WO)

### PA-KIR-02 — Kırılım sonrası retest (rol değişimi) girişi
- **Rejim:** her ikisi (trend yönünde) · **Yön:** her ikisi
- **Tanım (L):** kırılım barı `i0` (PA-KIR-01). Sonraki pencerede `j`: `l[j] ≤ R + w` ve `c[j] ≥ R`. Pencere: 10 bar (AN, TE, PA, MI varsayılan), BR kitap 1–5 bar. Bant `w` (varsayılan): AN 0,25, PA 0,2, TE 0,5, BR 0,1 ×ATR. Seviye altında kapanış kurulumu geçersiz kılar. Short ayna.
- **Giriş (üç varyant, kitaplar seçmiyor, ayrı test edilecek):** (a) retest barı kapanışında piyasa (AN, TE), (b) retest barı `h` + tampon stop emri (PA, BR, MI, WO), (c) seviyede limit, `R + w` (AN, TE "kaçırma" yöntemi).
- **Stop:** retest barı dibi − tampon (PA 0,2, TE 0,25, AN 0,5 ×ATR seviye altı, WO 1 tik; tampon karşılaştırması PA-STP-01). **Hedef:** PA-HDF-01/02/03.
- **Varyantlar:** boyun çizgisi retesti (PA-KIR-05/06), bayrak retesti (PA-KIR-07), sıkışıklık bölgesine dönüş (PA-SDR-07).
- **Fark:** MI "ilk çıkış çoğunlukla yanlış, yalnız testte gir" der, ama dar kama kırılımında test olmayabileceğini de yazar. TE ise birikim üstüne retest beklemeden buy-stop önerir (PA-TRD-04).
- **Kaynaklar:** 12a-K4 s.443–479,779–782,1009–1019; 12b-K14 s.1077–1084; 12c-K5 s.2118–2122; 10a-K5 s.989–1020; 08a-K4 s.715–757; 02a-K13,K14 s.1099–1255; 23a-K9 s.258–263; 31a-K8,K9 s.1203–1298.
- **Netlik:** orta · **Kaynak sayısı:** 6 (AN, TE, PA, MI, BR, WO)

### PA-KIR-03 — Sahte kırılım / SFP (seviyeyi delip geri kapanış, ters yön girişi)
- **Rejim:** range ağırlıklı, trend geri çekilmesi dahil · **Yön:** her ikisi
- **Tanım (L, seviye `L`):** `l[i] < L - buffer` ve `c[i] > L`. Buffer: PA 0,1×ATR, TE 0,5×ATR, AN 0 (hepsi varsayılan). AN alt fitil oranı ≥0,5 (varsayılan). Geri dönüş penceresi: PA 2 bar, MI 3 bar (MA'da), WO "anında" 1–2 bar, BR "birkaç çubuk", 3 bar (varsayılan). Varyantlar: WO tıkanıklık giderme arızası (tıkanıklık ≥3 bar, `c[e] < l[e-1]` ayı çıkışı, hemen sonraki boğa barı kurulum barı), MI MA'da sahte kırılım (≤3 bar MA altı, derinlik >1,5×ATR ise atla), MI stop avı (kırılım barı ≥1,5×ATR, 2 bar içinde geri kapanış), BR başarısız kırılım + başarısız başarısızlık. Short ayna.
- **Giriş:** (a) sinyal/dönüş barı kapanışında piyasa (AN, PA), (b) sinyal barı `h` + tik üstüne stop-buy, yalnız izleyen 1 barda (TE, WO, BR, MI). Kapanmadan girmek (AN, BR) OHLCV'de kodlanamaz.
- **Stop:** sinyal barının ekstremi − tampon (AN 0,1, PA 0,2, MI 0,1, TE 1 ATR, WO 1 tik). **Hedef:** karşı kenar / önceki swing / bir önceki S/R (PA, TE, BR, AN). **TF:** AN seviye HTF, stop-giriş LTF. TE 1s/4s/1g, 15dk gürültülü.
- **Kaynaklar:** 12a-K5 s.362–499; 12b-K2 s.1130–1296; 10b-K13 s.1592–1616; 10c-K17 s.2859–2868; 08a-K5 s.759–811; 02a-K9 s.807–832; 02b-K8 s.2504–2552; 02c-K9 s.2941–2992; 23a-K8 s.363–377; 31a-K4,K5 s.512–601; 31b-K9 s.6022–6217.
- **Netlik:** orta (çekirdek tanım yüksek, eşikler varsayılan) · **Kaynak sayısı:** 6 (AN, TE, PA, MI, BR, WO)

### PA-KIR-04 — 1-2-3, Ross Hook, Trader's Trick Entry, başarısızlık (MI)
- **Rejim:** trend dönüşü / geri çekilme · **Yön:** her ikisi
- **Tanım:** 1-2-3 (L): nokta 1 swing dip, nokta 2 sonraki swing tepe, nokta 3 nokta 1'den düşük yeni dip. Sinyal `c[t] > h[b]` (b = nokta 2). Üst 1-2-3 ayna. Ross Hook: yükselişte `l[i] < l[i-1]` ilk mum, giriş `c > h[i]`. TTE: nokta 2 sonrası en fazla 3 mum, her barın `h` üstüne stop-buy, stop giriş barı dibi, kitap "giriş ile P2 stop oranı ≥2:1" daha iyi diyor. Başarısızlık: girişten sonra ≤3 barda `c < l[giriş barı]`, ters giriş; başarısız başarısızlık aynı pencerede orijinal yöne dönüş.
- **Giriş:** nokta 2 üstüne stop + 0,1×ATR (varsayılan). **Stop:** nokta 1 veya 3 ötesi + 0,1–0,2×ATR (varsayılan). **Hedef:** 2R (varsayılan, kitapta yok).
- **Fark:** TTE (erken) ve Brooks H2 (ikinci deneme, PA-TRD-02) farklı kurulum üretir.
- **Kaynaklar:** 02a-K12 s.1042–1066; 02c-K1,K2,K3,K9 s.2625–2992.
- **Netlik:** orta (Ross Hook düşük) · **Kaynak sayısı:** 1 (MI)

### PA-KIR-05 — Çift tepe / çift dip
- **Rejim:** trend sonu (PA, MI, BR), range sınırı (DA) · **Yön:** her ikisi
- **Tanım:** iki swing tepe `|T1 - T2| ≤ tol`, arada swing dip = boyun `B`. Tol (varsayılan): DA 0,2, PA 0,3, MI 0,5, BR 0,1 ×ATR (BR kitap pencere 1–20 bar). Sinyal: `c < B` ilk kapanış. DA'da formasyon yalnız range sınırında onay kaynağı olarak kullanılır.
- **Giriş:** boyun altı ilk kapanış (PA), boyun retesti sonrası stop/limit (MI, "çoğunlukla en iyisi"), DA onay mumu kapanışı. BR giriş tanımlamaz. **Stop:** T2 üstü + 0,2×ATR (PA, MI, varsayılan). **Hedef:** `B - (T - B)` ölçülen hareket.
- **Kaynaklar:** 08a-K8 s.552–605; 02a-K13 s.983–1036; 05a-K7 s.3524–3634; 23a-K7 s.327–345,533–543; 02c-K10 s.3047–3069.
- **Netlik:** orta · **Kaynak sayısı:** 4 (PA, MI, DA, BR)

### PA-KIR-06 — Baş-omuz / ters baş-omuz
- **Rejim:** trend sonu · **Yön:** her ikisi
- **Tanım:** üç swing tepe `S1, H, S2`, `H` en yüksek, `|S1 - S2| ≤ 0,5×ATR` (PA varsayılan; DA 0,2×ATR). Boyun çizgisi iki dibi birleştirir. Sinyal: boyun altı ilk kapanış.
- **Giriş:** ilk kapanışta piyasa (PA) veya boyun retesti sonrası (MI). **Stop:** sağ omuz üstü + 0,2×ATR (varsayılan). **Hedef:** `boyun - (H - boyun)`.
- **Kaynaklar:** 08a-K9 s.607–662; 02a-K13 s.1099–1124; 05a-K7 s.3524–3634.
- **Netlik:** orta · **Kaynak sayısı:** 3 (PA, MI, DA)

### PA-KIR-07 — Bayrak / üçgen / flama / kama (devam formasyonları)
- **Rejim:** trend devamı · **Yön:** her ikisi
- **Tanım:** güçlü trend bacağı sonrası iki çizgi (swing'lerden) arasında konsolidasyon, her çizgiye ≥2 dokunuş (kitap). Bayrak paralel, üçgen/flama paralel değil. Kırılım: trend yönünde `c` çizgi dışında. Dar kama/NR (NR7 veya aralık ≤0,5×ATR, varsayılan) kırılımında test beklenmez, ilk swing geri çekilmesi beklenir.
- **Giriş:** yalnız kırılan çizgi retesti + tutunma sonrası stop (+0,1×ATR varsayılan). Erken giriş ayrı varyant. **Stop:** konsolidasyonun karşı ucu − 0,2×ATR (varsayılan). **Hedef:** çizgiler arası mesafe veya direk (PA-HDF-03).
- **Not:** BR'nin kama/bayrak tanımları öznel bulunup kodlanmadı.
- **Kaynaklar:** 02a-K14,K15 s.1125–1284.
- **Netlik:** orta · **Kaynak sayısı:** 1 (MI)

### 2.4 Mum formasyonları

### PA-MUM-01 — Pin bar / çekiç / kayan yıldız
- **Rejim:** trend sonu veya seviyede (seviye yakınlığı şart) · **Yön:** her ikisi
- **Tanım (boğa):** öncesinde düşüş `c[i-1] < c[i-N]` (N=5 varsayılan, AN, TE). Alt gölge ≥2×gövde (TE kitap "2–3 kat", diğerleri varsayılan). Üst gölge ≤0,10×range (AN, TE varsayılan). Kapanış konumu üst çeyrek ≥0,75 (TE kitap) veya gövde üst üçte birde ≥0,66 (PA, BR varsayılan). Gövde ≤0,3×range (DA, MI varsayılan). Belirginlik: range ≥1,0×ATR (AN varsayılan). Seviye yakınlığı: fitil ucu S/R bölgesinin 0,25×ATR içinde (MI varsayılan). Ayna: kayan yıldız / ayı pin. Tek başına yetersiz, seviye/EMA/HTF bağlamı şart (AN, TE, PA, DA, MI).
- **Giriş:** sinyal barı `h` + tampon stop-buy (TE, PA, MI, BR; tampon 0,05–0,1×ATR varsayılan), sonraki bar açılışı (TE-c), AN kademeli limit (pin öncesi mum dibi retesti, pin üstü seviye, pin `h`; 3 eşit pay varsayılan, LTF onayıyla), DA: mini range kırılımlı onay mumu. **Stop:** pin dibi − tampon (TE 1×ATR kitap, PA/AN/MI/BR 0,1). **Hedef:** yakın swing/HTF seviye (TE, AN), PA-HDF-01.
- **Kaynaklar:** 12a-K6,K7 s.858–1019; 10b-K1,K2 s.1193–1217,1344–1368; 10c-K10 s.2882–2896; 08a-K7 s.257–290,877–881,1126; 05a-K8 s.3480–3497; 02b-K3 s.2148–2180; 23a-K10 s.643–654.
- **Netlik:** orta · **Kaynak sayısı:** 6 (AN, TE, PA, DA, MI, BR)

### PA-MUM-02 — Yutan mum (boğa / ayı)
- **Rejim:** trend sonu · **Yön:** her ikisi
- **Tanım (boğa):** `c[i-1] < o[i-1]`, `c[i] > o[i]`, `min(o,c)[i] ≤ min(o,c)[i-1]`, `max(o,c)[i] ≥ max(o,c)[i-1]` (gövde yutma, gölge yok sayılır). PA: `o[i] ≤ c[i-1]` ve `c[i] ≥ o[i-1]`. TE ek koşul (kitap): kapanış önceki mumun `h` üstünde (çelişkili, Bölüm 5). Güç filtresi: `range[i] ≥ 2×ort(range[i-5..i-1])` (TE kitap "iki kat"). Her yutan sinyal değildir, HTF trend sonu şartı (AN).
- **Giriş:** sinyal barı `h` + tik stop (TE varsayılan), TE-c sonraki bar açılışı. AN hemen girmez, LTF seviye retesti bekler (PA-KIR-02). **Stop:** sinyal dibi (PA 0,1, AN 0,2×ATR varsayılan; TE 1×ATR kitap). **Hedef:** yakın swing / HTF direnç, kısmi (PA-HDF-05).
- **Kaynaklar:** 12b-K1 s.1032–1117; 10b-K3,K4 s.1219–1242,1372–1395; 10c-K9 s.2832–2846; 08a-K7 s.265–290.
- **Netlik:** orta · **Kaynak sayısı:** 3 (AN, TE, PA)

### PA-MUM-03 — Delici, kara bulut örtüsü, cımbız tepe/dip
- **Rejim:** trend sonu · **Yön:** her ikisi
- **Tanım (TE):** delici (L): `c[i-1] < o[i-1]`, `c[i] > o[i]`, `c[i] >` önceki gövde ortası, `c[i] < o[i-1]`. Kara bulut ayna. Cımbız dibi: `|l[i] - l[i-1]| ≤ 0,10×ATR` (varsayılan), `c[i] > c[i-1]`, `c[i] > o[i]`. Delici yutan kadar güçlü değil, ek teyit önerilir (PA-MUM-06).
- **Giriş:** sinyal barı `h` + tik stop (varsayılan). **Stop:** 1×ATR (kitap) altı. **Hedef:** swing / PA-STP-02.
- **Kaynaklar:** 10b-K5–K8 s.1243–1444.
- **Netlik:** orta · **Kaynak sayısı:** 1 (TE)

### PA-MUM-04 — Sabah/akşam yıldızı ve çok mumlu dönüş
- **Rejim:** trend sonu · **Yön:** her ikisi
- **Tanım:** sabah yıldızı: `c[i-2] < o[i-2]`, ortadaki mum range ≤0,5×ATR (varsayılan), `c[i] > o[i]` ve `c[i] >` ilk mumun gövde ortası (kitap %50). Akşam ayna. MI genel: ilk mum eski trend rengi, son mum yeni trend rengi, arada `n-2` ara mum (n=3–4 varsayılan). Formasyon adları (Grafik 53) kodlanamadı.
- **Giriş:** üçüncü mum `h` + tik stop veya kapanışta piyasa (varsayılan). **Stop:** üç mumun dibi − 1×ATR (TE) / uç ötesi + 0,2×ATR (MI varsayılan). **Hedef:** swing.
- **Kaynaklar:** 10b-K9,K10 s.1296–1474; 02b-K4 s.2187–2200.
- **Netlik:** orta (MI kısmı düşük) · **Kaynak sayısı:** 2 (TE, MI)

### PA-MUM-05 — İç bar, ii/iii, dış bar, NR4/NR7
- **Rejim:** sıkışma / trend başlangıcı · **Yön:** her ikisi (trend filtresiyle tek yön)
- **Tanım:** iç bar `h[i] < h[i-1]` ve `l[i] > l[i-1]` (BR eşitliği de iç sayar). ii/iii ardışık (≥2 iç bar sıkışma teyidi, varsayılan). Dış bar: `h` > önceki `h` ve `l` < önceki `l`. NR4/NR7: iç bar ve `range[i] = min(range[i-N+1..i])`, N=4/7 (MI kitap, NR7 muhafazakar). BR varyantları ioi, oio, ah (giriş tanımı yok, ioi ilk bar varsayım). Dış bar kurulum barı olarak kullanılmaz, kırılım emri dış barın ucuna konmaz, dış bar bölge oluşturmaz (WO filtre).
- **Giriş:** iç barın üstüne buy-stop, altına sell-stop (MI, BR). Trend filtresi açıksa yalnız trend yönü (MI: EMA20 > EMA50, üst TF). Tampon 0,05–0,1×ATR (varsayılan). **Stop:** iç barın karşı ucu + 0,1×ATR (varsayılan). **Hedef:** ölçülen hareket / 2R (varsayılan).
- **Kaynaklar:** 02b-K1,K2 s.1494–1576; 23a-K2,K3 s.451–590; 31b-K7 s.6137–6223; 31a-K25 s.4602–4607.
- **Netlik:** orta · **Kaynak sayısı:** 3 (MI, BR, WO)

### PA-MUM-06 — Mum sınıflandırma ölçüleri (trend çubuğu, kapanış konumu, boyut)
- **Rejim:** her ikisi · **Yön:** her ikisi (filtre)
- **Tanım:** trend çubuğu: `|c - o| / (h - l) > 0,50` (WO kitap), boğa için açılış alt yarıda, kapanış üst yarıda. Güçlü eğilim çubuğu gövde ≥0,6×range (BR, AN momentum varsayılan). Kapanış konumu `(c - l)/(h - l)` ≥0,75 boğa, ≤0,25 ayı (TE kitap "çeyrek"). Güçlü red: range ≥1,5×ATR (TE kitap). Büyük mum: range ≥2×son 5 ortalaması (TE kitap, N=5 varsayılan). Doji `|c - o| ≤ 0,1×range` (BR varsayılan).
- **Giriş / stop / hedef:** yok, diğer kuralların filtresi.
- **Kaynaklar:** 10b-K11,K12 s.1482–1523,2045–2057; 31a-K10 s.1824–1835; 23a-K1,K10 s.250,863–864; 12a-K3 s.122–125.
- **Netlik:** orta (WO yüksek) · **Kaynak sayısı:** 4 (TE, WO, BR, AN)

### PA-MUM-07 — Yavaşlama ve doruk karşıtı (4 bar)
- **Rejim:** trend sonu aşırı uç · **Yön:** her ikisi
- **Tanım:** ardışık `p0..p3`. Ayı yavaşlaması (short): `d_k = h[p_k] - h[p_{k-1}] > 0` ve `d1 > d2 > d3`, sınır `L = h[p3]`. Boğa yavaşlaması: düşen `l` farkları `e1 > e2 > e3 > 0`. Doruk karşıtı: aynı yapı, mesafeler artan (`d1 < d2 < d3` / `e1 < e2 < e3`). Geçersiz: bar `l > L` (kitap). Kitap isimleri yön olarak tersini çağrıştırır, tanım sayısaldır.
- **Giriş:** `p3` kurulum yönünde bar ise ters ucu ± tik stop, değilse ilk uygun barın ucu, yalnız izleyen 1 barda. **Stop:** kurulum barı ucu ± tik (varsayılan). **Hedef:** 2R (varsayılan).
- **Kaynaklar:** 31a-K13–K16 s.2344–3054.
- **Netlik:** orta · **Kaynak sayısı:** 1 (WO)

### PA-MUM-08 — Trend çubuğu arızası
- **Rejim:** trend (karşı-trend dönüş) · **Yön:** her ikisi
- **Tanım (uzun):** `A` ayı trend çubuğu (PA-MUM-06). `B = A+1`: `l[B] < l[A]` ve B ayı trend çubuğu değil. `C = A+2` tetik kontrolü. Short ayna.
- **Giriş:** `h[B]` + tik stop-buy, yalnız `C` barında, aksi iptal. **Stop:** `l[B]` − tik (genel kural), kitap şekli `l[A]` altını gösteriyor (Bölüm 5). **Hedef:** 2R (varsayılan).
- **Kaynaklar:** 31a-K11,K12 s.1850–1931.
- **Netlik:** yüksek (giriş/iptal), orta (stop) → yüksek · **Kaynak sayısı:** 1 (WO)

### 2.5 Trend takibi girişleri (geri çekilme)

### PA-TRD-01 — Trendde hareketli ortalamaya geri çekilme
- **Rejim:** trend · **Yön:** her ikisi
- **Tanım (L):** yükseliş rejimi (PA-FLT-02). Geri çekilme: `l[i] ≤ MA[i] ≤ h[i]` ve `c[i] ≥ MA[i]` (MI, MA ∈ {EMA20, EMA50, EMA100}). PA: `l ≤ EMA21`, son swing dibi HL. TE: `l ≤ SMA50 + 0,5×ATR` ve `c > SMA50`. Güçlü kurulum: MA ile önceki swing tepesi çakışması ≤0,2×ATR ve ikinci dip birincinin yakınında (MI, varsayılan). Opsiyonel osilatör: Stoch(5,3,3) <20 ve RSI(10) <35 (MI; RSI eşiği varsayılan).
- **Giriş:** sinyal barı: `c > o` ve `c > EMA9` (PA), `h` + 0,1×ATR stop (MI varsayılan). **Stop:** `min(son HL, EMA21) - 0,2×ATR` (PA), `l_ref - 0,2×ATR` (MI), son swing dibi altı (TE) (varsayılan). **Çıkış:** `c < EMA21` iki kapanış (PA varsayılan), PA-STP-02. **Hedef:** sabit hedef yok, 2R veya sonraki swing (varsayılan).
- **Not:** MA'da sahte kırılım PA-KIR-03, MA'da çift/üçlü dip (MI-K10, kitap deneyimsize önermiyor, düşük) bu kuralın ek varyantıdır.
- **Kaynaklar:** 08a-K6 s.402–507,994–998; 02a-K5,K7,K8,K10 s.704–881; 10a-K7 s.1045–1052; 23a-K4 s.443–448 (EMA20 filtresi).
- **Netlik:** orta · **Kaynak sayısı:** 4 (PA, MI, TE, BR)

### PA-TRD-02 — Yüksek/Düşük 1–4 (H2/L2) geri çekilme sayımı
- **Rejim:** trend · **Yön:** her ikisi
- **Tanım (L):** trend: `c > EMA20` ve EMA20 yukarı (varsayılan). H1: `h[k] > h[k-1]`. Geri çekilme: en az bir `h[j] < h[j-1]`. H2: geri çekilmeden sonraki ilk yeni `h[i] > h[i-1]`. Pencere ≤20 bar, ikinci giriş ilk girişten sonra ≤5 bar (BR varsayılan). H2/L2 tercih edilir (MI), yalnız trend yönünde.
- **Giriş:** sinyal barı `h` + 0,05×ATR (BR varsayılan) buy-stop. **Stop:** geri çekilmedeki en düşük `l` − 0,1×ATR (BR), MI sinyal barı dibi. **Hedef:** 2R (varsayılan) veya PA-HDF-03.
- **Fark:** BR kama bayrağında ilk sinyal, kama ters çevirmede ikinci sinyal der. MI ek koşullar (trend çizgisi kırılımı, ekstremum testi) tanımsız.
- **Kaynaklar:** 02c-K7,K8 s.2870–2927; 23a-K4 s.443–448,687–703,948–951.
- **Netlik:** orta · **Kaynak sayısı:** 2 (MI, BR)

### PA-TRD-03 — Zayıf geri çekme girişi ve yeniden giriş (Woods)
- **Rejim:** trend · **Yön:** her ikisi
- **Tanım (short):** ayı trendinde yukarı geri çekilme zayıftır (PA-YAP-05 WO tanımı, en az 2 karşı-trend salınım, N=2 varsayılan). İkinci yükseliş bacağından sonra ilk düşüş mumu = kurulum barı. Aynı yönde ters 3 ardışık mum gelirse arama durur (kitap). Yeniden giriş (tek hak): orijinal kurulum başarılı/başarısız olmadıysa (`h[j] ≤ h[setup]`, `l[j] ≥ l[setup]`), yeniden giriş barı `r` yön mumu, stop emri `r` ucu ± tik. Stop'a değip hızla toparlanma iyi işaret (ölçüm: 2 mum içinde `c > stop`, varsayılan).
- **Giriş:** `l[setup]` − tik sell-stop (tik = 0,1×ATR varsayılan), yalnız izleyen 1 barda, tetiklenmezse iptal. **Stop:** `h[setup]` + 0,1×ATR (varsayılan, kitapta yok). **Hedef:** 1R–2R (varsayılan, kitapta yok). Seviye yakınlığı skor olarak (PA-SDR-01).
- **Kaynaklar:** 31b-K1–K4,K2b,K8 s.5222–5432,7018–7314; 31a-K26 s.5144–5220.
- **Netlik:** orta · **Kaynak sayısı:** 1 (WO)

### PA-TRD-04 — Birikim/sıkışma sonrası trend yönlü kırılım (MBEE, ön-kırılma)
- **Rejim:** trend (birikim sonrası) · **Yön:** her ikisi
- **Tanım (TE):** birikim: son M bar (5–10, varsayılan) toplam aralık ≤3×ATR veya her bar range ≤0,5×ATR (varsayılan; kitapta tanım yok). Ön-kırılma: üst TF'de birikim, alt TF'de (4:1–6:1 oranı varsayılan) birikim dibinde ret mumu (`l ≤ alt sınır`, `c > o`). MA20 ile birikim dibi |fark| ≤0,5×ATR filtresi. MI: NR7/iç bar kırılımı (PA-MUM-05) ve dar kama ilk geri çekilme (PA-KIR-07) aynı aile.
- **Giriş:** birikim tepesi `H` üstüne buy-stop (kitap) veya ret mumundan sonraki bar açılışı. **Stop:** birikim dibi − 1×ATR (kitap). **Çıkış:** 3×ATR iz süren (PA-STP-02).
- **Kaynaklar:** 10b-K20,K22 s.2074–2182; 10c-K5,K6 s.2424–2449,2770–2828,2976–2987; 02a-K15 s.1265–1284.
- **Netlik:** orta (ön-kırılma düşük) · **Kaynak sayısı:** 2 (TE, MI)

### PA-TRD-05 — Seviye + tetikleyici mum birleşimi (konfluens, MAEE)
- **Rejim:** trend geri çekilmesi veya range kenarı · **Yön:** her ikisi
- **Tanım:** üç bileşen: (1) yapı filtresi (PA-YAP-02), (2) değer alanı = S/R bölgesi (PA-SDR-01), MA veya fib, (3) tetikleyici mum (PA-MUM-01..04). AN: HTF seviye + LTF onay (4s seviye, 15dk giriş). WO: S/R kaynaklarının çakışması kaliteyi artırır. Kitaplar "birleşim" için sayısal koşul vermez, konfluens skoru (bileşen sayısı) olarak tasarlanmalı (varsayılan).
- **Giriş:** tetikleyici mum ucu dışına stop. **Stop:** değer alanı dışı − 1×ATR (TE kitap). **Hedef:** yakın swing + kısmi çıkış (PA-HDF-05).
- **Kaynaklar:** 10b-K21 s.1918–2005; 12a-K1,K7,K8 s.255–258,806–1019; 02a-K4,K11 s.249–305; 31b-K6 s.6009–6033.
- **Netlik:** orta · **Kaynak sayısı:** 4 (TE, AN, MI, WO)

### 2.6 Yatay piyasa ve ortalamaya dönüş

### PA-YTY-01 — Range tespiti
- **Rejim:** range · **Yön:** her ikisi
- **Tanım:** son N bar (N=20 varsayılan; TE faz için 150) `RH = max(h)`, `RL = min(l)`. `(RH - RL)/ATR ≤ X`: AN 3, PA 3, TE 4 (varsayılan). Sınırlara ≥2'şer swing dokunuşu (PA, TE varsayılan). MA yatay ve fiyat MA'yı 20 barda ≥3 kez kesiyor (MI, `|eğim| ≤ 0,1×ATR/bar`, varsayılan) veya SMA200 yatay (TE). DA: tek taraf iki pivot yeterli (erken çizim, TOL=0,2×ATR varsayılan), PA-SDR-02 ile doğrulama. Orta bölge `RL + 0,4(RH-RL) ≤ c ≤ RL + 0,6(RH-RL)` işlem yok (TE varsayılan). Range bozulma: `c` sınırın 0,5×ATR (AN varsayılan) ötesinde.
- **Giriş / stop / hedef:** PA-YTY-02. **TF:** kitaplar 4s/günlük, kalibrasyon gerekir.
- **Kaynaklar:** 12a-K10 s.601–652; 10a-K3 s.736–862; 10c-K16 s.2859–2914; 08a-K3 s.833–924; 05a-K4 s.2954–3224; 02a-K19 s.727–728,1302–1340.
- **Netlik:** orta · **Kaynak sayısı:** 5 (AN, TE, PA, DA, MI)

### PA-YTY-02 — Range kenarında ters yön (ortalamaya dönüş) girişi
- **Rejim:** range · **Yön:** her ikisi (alt kenar long, üst kenar short)
- **Tanım:** fiyat kenar bölgesinde (`h ≥ RH - w` / `l ≤ RL + w`, w = bölge genişliği PA-SDR-01) ve onay: pin bar (PA-MUM-01), yutan (PA-MUM-02), çift tepe/dip (PA-KIR-05), SFP (PA-KIR-03). DA: son W=3 bar küçük gövde (≤0,3×range) uzun fitil (≥2×gövde), onay barı mini range dışında kapanır, alt fitil ≤0,1×range, ayrıca trend çizgisi kırılımı zorunlu (PA-SDR-06). MI seviye reddi: `h ≥ R - tol` ve `c < R`, A: `R - 0,1×ATR` limit, B: ters mum veya 2–3 eşit dip altı.
- **Giriş:** sinyal/onay barı kapanışında piyasa (PA, DA) veya sinyal ucu stop. **Stop:** kenar dışı + tampon: PA 0,2, DA 0,2, AN 0,5, MI 0,5–1,0, TE 1×ATR (varsayılan; TE kitap). **Hedef:** karşı kenar (AN, TE, PA, DA, MI), AN alternatif orta nokta.
- **Fark:** 3./4. dokunuşta DA işlemi atlar veya kısaltır (PA-SDR-02). BR ve WO bu rejimde giriş tanımlamaz.
- **Kaynaklar:** 12a-K10 s.601–652; 10a-K3 s.847–862; 10c-K16 s.2859–2914; 08a-K3 s.857–924; 05a-K6,K7,K8,K11 s.3349–4017; 02a-K11 s.278–305; 02b-K3,K5 s.1479–1487,2148–2180.
- **Netlik:** orta · **Kaynak sayısı:** 5 (AN, TE, PA, DA, MI)

### PA-YTY-03 — Range oluşum filtresi (impulsif hareket sonrası)
- **Rejim:** trend → range geçişi · **Yön:** her ikisi
- **Tanım (DA):** impulsif bacak ≥2× en büyük düzeltme ve ≤5 bar (varsayılan, OCR sayıları güvenilmez). Sonra trendin son ekstremini aşmadan bir SH ve bir SL oluşursa "yan piyasa" etiketi. Trendin son LH/LL seviyesi kapanışla aşılana kadar range sürer. Bu sürede trend-takip girişleri kapalı. Kitap range'in çoğunlukla bu tür hareketten sonra oluştuğunu söyler (kesin yüzde güvenilmez).
- **Giriş / stop / hedef:** yok (ön koşul). **TF:** 4s.
- **Kaynaklar:** 05a-K1,K2,K3 s.2438–2945.
- **Netlik:** orta · **Kaynak sayısı:** 1 (DA)

### PA-YTY-04 — Range'de Fibonacci 0,702 / 0,786 alım bölgesi
- **Rejim:** range · **Yön:** her ikisi
- **Tanım (AN):** `RH, RL` son M=50 bar (varsayılan). Long bölgesi `L = RH - r(RH - RL)`, `r` = 0,702 ve 0,786. Tetik: `l ≤ L_0,786` ve `c > L_0,702`. Range geçersiz: `c < RL - 0,5×ATR` (varsayılan).
- **Giriş:** bölgede limit merdiven. **Stop:** `RL - 0,5×ATR` (varsayılan). **Hedef:** karşı kenar / ara destek. **TF:** kitap 15dk örneği.
- **Kaynaklar:** 12b-K12 s.2002–2061.
- **Netlik:** orta · **Kaynak sayısı:** 1 (AN)

### PA-YTY-05 — Dar sıkışma: tıkanıklık, dikenli tel, çıkıntı, süre
- **Rejim:** range (sıkışma) · **Yön:** her ikisi
- **Tanım:** WO tıkanıklık: `l[k-1] ≤ c[k] ≤ h[k-1]` ardışık ≥3 bar (kitap), üst sınır yok, ara fitil kırılımları bozmaz. Çıkış barı: `c[e] > h[e-1]` / `c[e] < l[e-1]`. BR dikenli tel: ≥3 bar (BR başka yerde ≥2 diyor), ardışık çiftlerde örtüşme ≥0,5×min(range) (varsayılan), en az bir doji, toplam aralık ≤2×ATR (varsayılan). MI çıkıntı: pencere 4–10 bar, ≥2 eşleşen high ve low çifti (≤0,25×ATR varsayılan), trend içinde. MI süre: son kırılımdan beri T ≥10 bar işlem aralığı, T >20 ise kırılma beklenir.
- **Giriş:** tek başına giriş yok. Giriş: PA-KIR-03 (giderme arızası), PA-SDR-07, çıkıntı kırılımı `c > max(h[pencere])` (MI varsayılan). **Stop / hedef:** pencere karşı ucu, pencere yüksekliği (MI varsayılan).
- **Kaynaklar:** 31a-K2,K3 s.340–476; 23a-K1 s.228–230,481–483,809–812; 02c-K4,K5 s.2667–2688.
- **Netlik:** orta · **Kaynak sayısı:** 3 (WO, BR, MI)

### 2.7 Volatilite ve filtreler

### PA-FLT-01 — Üst zaman dilimi (HTF) yön filtresi
- **Rejim:** trend · **Yön:** her ikisi
- **Tanım:** `htf_bias = +1/-1/0`. Kaynaklar: HTF son BOS yönü veya HTF pin (AN), HTF EMA yapısı (MI, PA-FLT-02). LTF sinyali yalnızca `htf_bias` yönünde. Önyargı geçerliliği 5 HTF mumu (AN varsayılan). TF eşlemesi (varsayılan): 15dk→1s, 1s→4s, 4s→1g (MI); AN: HTF 1g/4s, LTF 4s/1s/15dk; TE ön-kırılma alt/üst oranı 4:1–6:1.
- **Giriş / stop / hedef:** yok (filtre).
- **Kaynaklar:** 12a-K8 s.806–977; 12b-K13 s.1351–1416; 02a-K6 s.249–253,735–742; 02b-K1 s.1508–1510; 10c-K5 s.2446–2449; 08a-K6 s.994–998.
- **Netlik:** orta · **Kaynak sayısı:** 4 (AN, MI, TE, PA)

### PA-FLT-02 — Hareketli ortalama trend filtresi
- **Rejim:** trend · **Yön:** her ikisi
- **Tanım (yükseliş):** MI: `c > EMA100` ve `EMA20 > EMA50` ve ikisi de yükseliyor (eğim `> 0,05×ATR/bar` varsayılan), aksi "karışık". PA: `EMA9 > EMA21` ve `c > EMA21` (uzun vade 50/200 SMA opsiyonel). TE: `c > SMA200` ve SMA200 yukarı. BR: `c > EMA20` ve eğim yukarı. WO: `c > EMA50` (varsayılan). Başlangıç: EMA20/50 + EMA100, taranacak.
- **Giriş / stop / hedef:** yok (filtre).
- **Kaynaklar:** 02a-K5 s.704–731,783–785; 08a-K6 s.465–482; 10a-K2 s.757–843; 10c-K1 s.2259; 23a-K4,K11 s.359–360,948–951; 31a-K1 s.233–265 (varsayılan).
- **Netlik:** orta · **Kaynak sayısı:** 5 (MI, PA, TE, BR, WO)

### PA-FLT-03 — Volatilite rejimi (ATR oranı, daralma)
- **Rejim:** her ikisi · **Yön:** her ikisi
- **Tanım:** TE: `atr_ratio = ATR20 / ort(ATR20, 100)`; `< 0,75` düşük vol (giriş izni, dar stop), `> 1,25` yüksek vol (yeni giriş yok) (varsayılan). MI: ATR(20) son 20 barın en düşüğünde ve σ(20) de düşükse daralma (varsayılan), alternatif ATR yüzdesi son 100 barın alt çeyreğinde (varsayılan).
- **Fark:** MI düşük vol sonrası yönlü hareketi "daha olası" bulur, başka bir yerde düşük vol'de kırılım olasılığının az olduğunu söyler. Yön backtestle belirlenir.
- **Giriş / stop / hedef:** yok (filtre).
- **Kaynaklar:** 10c-K15 s.2674–2698; 02b-K5 s.1393–1561,1959–1961; 02a-K19 s.1302–1316.
- **Netlik:** düşük · **Kaynak sayısı:** 2 (TE, MI)

### PA-FLT-04 — Aşırı uzama ve günlük hareket tükenmesi
- **Rejim:** trend · **Yön:** her ikisi
- **Tanım (TE):** `dist = |c - MA50| / ATR20 > 2,0` trend yönünde yeni giriş yok (varsayılan). `|c - günlük açılış| ≥ 1,0×ATR20` trend yönünde giriş yok, ters sinyal değerlendirilir (varsayılan). Kripto için "gün" UTC günü (varsayılan).
- **Giriş / stop / hedef:** yok (filtre).
- **Kaynaklar:** 10c-K4,K20 s.2504–2592,2956–2964.
- **Netlik:** düşük · **Kaynak sayısı:** 1 (TE)

### PA-FLT-05 — Hacim teyidi (opsiyonel)
- **Rejim:** her ikisi · **Yön:** her ikisi
- **Tanım:** kırılım barında `vol > 1,5×SMA(vol,20)` (AN, PA varsayılan). MI: omuzlarda hacim azalması (opsiyonel); forex'te hacim güvenilmez, kriptoda borsaya göre değişir. Kitaplar sayısal eşik vermez, zorunlu kural değildir.
- **Giriş / stop / hedef:** yok (filtre).
- **Kaynaklar:** 12a-K3 s.122–125; 08a-K4 s.711–713,853–855; 02a-K13 s.1082–1089.
- **Netlik:** düşük · **Kaynak sayısı:** 3 (AN, PA, MI)

### PA-FLT-06 — Belirsiz yapı / tıkanıklıkta işlem yok
- **Rejim:** her ikisi · **Yön:** her ikisi
- **Tanım:** TE: son 4 swing'de HH/HL veya LH/LL sırası bozuksa veya kapanışların ≥%70'i SMA200 ± w bandındaysa işlem yok (varsayılan). MI-c (Brooks): T ≥10 bar tıkanıklıkta trend-takip girişleri kapalı (kitap tutarsız, Bölüm 5). WO: tıkanıklık içi basınç/sıkışıklık bölgesinden kurulum alınmaz (PA-SDR-07/08), birleşik bölgede işlem yok.
- **Giriş / stop / hedef:** yok (filtre).
- **Kaynaklar:** 10a-K8 s.859–868; 02c-K6 s.2892–2894; 31a-K20 s.3829–3854; 31a-K7 s.1196–1201.
- **Netlik:** orta · **Kaynak sayısı:** 3 (TE, MI, WO)

### PA-FLT-07 — Rejim testi: önceki gün kırılım sistemi
- **Rejim:** her ikisi · **Yön:** her ikisi
- **Tanım (TE, günlük):** `h[i] > h[i-1]` long, long iken `l[i] < l[i-1]` kapat ve short, tersi. Toplam PnL eğrisi eğimi pozitif ise piyasa trend, negatif ise ortalamaya dönüş. Eşik kitapta yok (backtestle). Haftalık da denenebilir.
- **Giriş / stop / hedef:** testin kendi mekaniği, ticari kural değil.
- **Kaynaklar:** 10c-K14 s.2600–2645.
- **Netlik:** orta · **Kaynak sayısı:** 1 (TE)

### PA-FLT-08 — Çoklu varlık korelasyon filtresi
- **Rejim:** her ikisi · **Yön:** her ikisi
- **Tanım (MI):** `r = corr(c_A, c_B)` pencere L=50 ve 200 (kitap), `|r| ≥ 0,90` güçlü (kitap). Korelasyon bozulunca pozisyon kısma. Çoklu varlık verisi gerekir, tek parite için kullanılmaz.
- **Giriş / stop / hedef:** yok (filtre).
- **Kaynaklar:** 02b-K7 s.1614–1738.
- **Netlik:** orta · **Kaynak sayısı:** 1 (MI)

### 2.8 Stop yerleşimi

### PA-STP-01 — Yapısal stop (yapı seviyesinin ötesi + tampon)
- **Rejim:** her ikisi · **Yön:** her ikisi
- **Tanım:** long stop = ilgili yapısal ekstremum − tampon. Ekstremum kurulum tipine göre: sinyal mumu dibi, retest dibi, son swing dibi (HL), değer alanı alt sınırı, kırılan seviye, birikim dibi, nokta 1/3. Short ayna. Kapanış bazlı stop (AN, HTF yapı) ve intrabar stop ayrı test edilir. Tampon kitaplar arasında çok farklı (Bölüm 5): TE 1×ATR (kitap), PA 0,2, DA 0,2, MI 0,2 (giriş 0,1), AN 0,1–0,2 (range 0,5), BR 0,1, WO 1 tik ≈ 0,05–0,1×ATR (hepsi varsayılan, TE hariç). Tampon 0,1–1,0×ATR aralığında tarama parametresidir. Fib seviyeleri stop olarak kullanılmaz (AN). Kurulumu geçersiz kılan seviye seçilir (TE).
- **Giriş / hedef:** yok (stop kuralı). Stop mesafesi çok genişse işlem atlanır (PA-RSK-02).
- **Kaynaklar:** 12a-K5,K7 s.473–499,1001; 12b-K11 s.1091–1095,1943; 10b-K14 s.1639–1657; 10c-K8 s.2770–2937; 08a-K10 s.432–437,921–924; 05a-K10 s.3983–4091; 02a-K20 s.795–881; 02c-K12 s.2657–3023; 23a-K2,K4 (varsayılan); 31a-K1 s.233–265.
- **Netlik:** orta · **Kaynak sayısı:** 7 (AN, TE, PA, DA, MI, BR, WO)

### PA-STP-02 — İz süren stop ve MA/swing bazlı çıkış
- **Rejim:** trend · **Yön:** her ikisi
- **Seçenekler (ayrı test edilecek):** (a) ATR: `stop = max(stop, h - 3×ATR20)`, ilerleme eşiği ≥1R (TE kitap 3 ATR, eşik varsayılan). (b) swing: yeni swing dibinde stop yukarı, `c < önceki swing dibi - 1×ATR` çıkış (TE, swing penceresi 2 varsayılan), BR son düşük salınım − tampon, DA son swing, MI son 2 mum dibi (varsayılan). (c) MA: `c < MA200` (uzun vade), MA100 (orta), MA300 (çok uzun) (TE kitap, SMA varsayılan), PA `c < EMA21` iki kapanış (varsayılan). (d) karşı-trend işlemde `stop = max(stop, l[i-1])` (TE). AN: -0,618 uzantı ihlali sonrası 2 kapanışla başa baş (düşük, varsayılan). Stop asla geri çekilmez.
- **Kaynaklar:** 10c-K7,K11 s.2770–2894; 10b-K17,K18 s.1778–1808; 23a-K13 s.836–840; 05a-K11 s.4008–4017; 08a-K6,K11 s.493–496,1055; 02c-K11 s.2783–2962; 12c-K2 s.2107–2112.
- **Netlik:** orta · **Kaynak sayısı:** 6 (TE, BR, DA, PA, MI, AN)

### PA-STP-03 — Emir süresi ve zaman durdurma
- **Rejim:** her ikisi · **Yön:** her ikisi
- **Tanım:** WO: kurulum emri yalnız izleyen 1 barda geçerli, tetiklenmezse iptal (kitap). MI: pozisyon N=10 bar sonunda kapatılır (varsayılan), başarısızlık penceresi 3 bar (kitap).
- **Kaynaklar:** 31a-K4 s.552–556; 31b-K3 s.5366–5368; 02b-K6 s.1580–1594; 02c-K9 s.2941–2992.
- **Netlik:** orta · **Kaynak sayısı:** 2 (WO, MI)

### 2.9 Hedef ve çıkış

### PA-HDF-01 — Sabit R hedefi ve minimum risk/ödül filtresi
- **Rejim:** her ikisi · **Yön:** her ikisi
- **Tanım:** `hedef = giriş ± k×R`. Varsayılan k=2 (PA kitap "en az 1:2", AN kitap "2:1 yeterli"). Minimum ödül/risk filtresi `reward/risk ≥ eşik`: BR 1,0 (kitap alt sınır), DA 1,0 (RR_MIN varsayılan, hedef 2), TE 0,8 (kitap tek örnek, yüksek kazanma oranına bağlı), PA 2, AN örnekte ≥3. Başlangıç eşiği 1,0 (varsayılan), 0,8–2 aralığı taranacak. TE: yüksek vol genişlemesinde 1:5 hedef (kitap).
- **Kaynaklar:** 08a-K11 s.1130–1136; 12a-K9 s.396–397,838; 12b-K10 s.1855; 10c-K18,K15 s.2674–2698,2909–2921; 05a-K11 s.3988–4017; 23b-K1 s.1126–1128.
- **Netlik:** orta · **Kaynak sayısı:** 6 (PA, AN, TE, DA, BR, MI)

### PA-HDF-02 — Karşı seviye / karşı kenar / yakın swing hedefi
- **Rejim:** her ikisi · **Yön:** her ikisi
- **Tanım:** hedef giriş yönündeki ilk sorunlu bölge (FTA, AN), önceki swing tepe/dip (TE, BR, AN, PA), range karşı kenarı (AN, TE, PA, DA, MI), kanal karşı çizgisi (MI), R1/S1 (MI varsayılan), salınım rejiminde önceki gün high/low (TE). Hedefi seviyenin biraz içinde tut (TE hedef 1 için 0,2×ATR içeride, varsayılan). Hedef yoksa PA-HDF-01'e düş (AN).
- **Kaynaklar:** 12a-K9 s.430–457; 10b-K1,K21 s.1193–2005; 10c-K9,K13,K16 s.2641–2914; 08a-K3,K11 s.894–896; 05a-K11 s.3988–4017; 02a-K3,K17 s.309–477; 23a-K8 s.363–377.
- **Netlik:** orta · **Kaynak sayısı:** 6 (AN, TE, PA, DA, MI, BR)

### PA-HDF-03 — Ölçülen hareket
- **Rejim:** her ikisi · **Yön:** her ikisi
- **Tanım:** hedef = kırılım noktası + formasyon/range yüksekliği: çift tepe/dip ve baş-omuz (PA), bayrak direği veya çizgiler arası mesafe (MI), range yüksekliği veya ilk bacak (BR). BR mikro ölçüm boşluğu: `mid = (l[t+1] + h[t-1])/2`, hedef `mid + range[t]` (varsayılan, düşük).
- **Kaynaklar:** 08a-K4,K8,K9 s.574–576,634–635,751–752; 02a-K13,K14 s.1166–1168; 02c-K4,K10 s.2667–2677,3047–3069; 23a-K12 s.544–548,1079–1082.
- **Netlik:** orta · **Kaynak sayısı:** 3 (PA, MI, BR)

### PA-HDF-04 — Fibonacci uzantı hedefleri
- **Rejim:** trend · **Yön:** her ikisi
- **Tanım:** AN uzantı `T_k = A + k(B - A)`, `k` = 1,618 / 2,618 (ATH sonrası). Negatif seviyeler `T = B + (B-A)k`, `k` = 0,236 / 0,618 / 1,0 (kitap; "%1" yazımı -1,0 okundu). Trend tabanlı 3 nokta: `H(k) = P3 + (P2 - P1)k`, `k` = 0,618 / 0,786 / 0,88 (formül kitapta yazılı değil, yorum, varsayılan; P3 derinliği 0,5–0,618 çelişkili). MI uzatma 1,618 / 2,618 / 4,236 (kitap). Kısmi çıkış eşit üçe bölme (varsayılan). TP1 seçimi belirsiz.
- **Kaynaklar:** 12b-K9 s.1884–1920; 12c-K1,K3 s.2083–2268; 02a-K16 s.520.
- **Netlik:** orta · **Kaynak sayısı:** 2 (AN, MI)

### PA-HDF-05 — Kısmi çıkış ve başa baş stop
- **Rejim:** her ikisi · **Yön:** her ikisi
- **Tanım:** AN: hedefte pozisyonun 0,5'i (varsayılan), kalan karşı seviyeye. TE: ilk hedefte en fazla %50 (kitap, aynı bölümde %90 örneği çelişki), kalan en az %50 hedef 2'ye. MI: 2–3 parça (kitap), 1. parça 1R (varsayılan), 2. parça başa baş, 3. parça iz süren. Ross 3 parça, Brooks 2 parça (kitap). Başa baş taşıma kitaplar arasında net değil (TE "doğru cevap yok"). Başlangıç önerisi: 2 parça, 1R'de %50, başa baş taşıma ayrı varyant.
- **Kaynaklar:** 12a-K9 s.453–455,836–846; 12b-K10 s.1097–1103; 12c-K1 s.2107–2140; 10b-K16 s.1818–1835; 10c-K12 s.2848–2878; 02b-K6 s.1580–1594; 02c-K11 s.2783–2962.
- **Netlik:** orta · **Kaynak sayısı:** 3 (AN, TE, MI)

### PA-HDF-06 — Rejime göre çıkış modu
- **Rejim:** her ikisi · **Yön:** her ikisi
- **Tanım (TE):** trend rejiminde iz süren stop (PA-STP-02), salınım/range rejiminde sabit hedef (önceki gün high/low veya karşı kenar). Üst TF dağıtımdaysa en yakın swing tepesinde çık, birikimdeyse yarısını dirençte sat. Rejim ayrımı PA-FLT-07 veya PA-YAP-04 ile yapılır, kitap sayı vermez.
- **Kaynaklar:** 10c-K13 s.2236–2238,2641–2666.
- **Netlik:** orta · **Kaynak sayısı:** 1 (TE)

### 2.10 Pozisyon-risk

> Bu bölümdeki yüzdeler kitap bilgisidir. Bizim risk kilidimiz her kitabın boyutlandırma önerisini ezer.

### PA-RSK-01 — İşlem başına risk ve pozisyon boyutu
- **Rejim:** her ikisi · **Yön:** her ikisi
- **Tanım:** `risk_tutar = equity × r`, `qty = risk_tutar / |giriş - stop|`. TE: r ≤ %1 (kitap, tavan), PA: %1–2 (kitap). Kaldıraç/teminat kuralı kitaplarda yok. Ajan boyutu risk kilidinden gelir, bu kural yalnızca stop mesafesinden miktarı hesaplayan formül olarak referanstır.
- **Kaynaklar:** 10b-K15 s.1666–1725; 10c-K19 s.2242–2266; 08a-K11 s.1141–1143.
- **Netlik:** yüksek · **Kaynak sayısı:** 2 (TE, PA)

### PA-RSK-02 — Stop genişliğine göre işlem atlama
- **Rejim:** her ikisi · **Yön:** her ikisi
- **Tanım:** stop mesafesi `> 1,5×ATR` ise işlem atlanır (MI varsayılan, kitap "mola çok büyükse atla"). Stop mesafesi ödülden büyükse atla (DA). TE: düşük vol'de dar stop ve büyük pozisyon, yüksek vol'de geniş stop ve düşük R/R (yön kitapta, sayı yok).
- **Kaynaklar:** 02a-K20,K9 s.824–830; 05a-K10,K11 s.4088–4094; 10c-K15 s.2687–2698.
- **Netlik:** düşük · **Kaynak sayısı:** 3 (MI, DA, TE)

---

## 3. Özet tablo

| ID | Kural | Kategori | Rejim | Kaynak sayısı | Netlik |
|---|---|---|---|---|---|
| PA-YAP-01 | Swing tepe/dip (fraktal) | Piyasa yapısı | her ikisi | 7 | yüksek |
| PA-YAP-02 | Trend / range etiketi (HH-HL, LH-LL) ve trend tespiti | Piyasa yapısı | trend / range etiketi | 6 | orta |
| PA-YAP-03 | Yapı kırılımı (BOS) ve karakter değişimi (CHoCH) | Piyasa yapısı | trend | 1 | orta |
| PA-YAP-04 | Dört faz sınıflaması (SMA200) | Piyasa yapısı | birikim/dağıtım = range, ilerleme/gerileme = trend | 1 | düşük |
| PA-YAP-05 | Geri çekilme derinliği ve trend gücü sınıflaması | Piyasa yapısı | trend | 2 | orta |
| PA-SDR-01 | Yatay destek/direnç bölgesi (bant) | Destek-direnç ve bölgeler | her ikisi | 6 | orta |
| PA-SDR-02 | Seviye gücü ve dokunma sayısı | Destek-direnç ve bölgeler | her ikisi | 5 | düşük |
| PA-SDR-03 | Önceki periyot seviyeleri ve pivot noktaları | Destek-direnç ve bölgeler | her ikisi | 2 | yüksek |
| PA-SDR-04 | Yuvarlak sayı seviyeleri | Destek-direnç ve bölgeler | her ikisi | 1 | orta |
| PA-SDR-05 | Fibonacci geri çekilme bölgesi ve girişi (altın cep, kesişme) | Destek-direnç ve bölgeler | trend | 3 | orta |
| PA-SDR-06 | Trend çizgisi ve kanal | Destek-direnç ve bölgeler | trend (MI), range girişi filtresi (DA) | 2 | orta |
| PA-SDR-07 | Sıkışıklık bölgesi ve kurulumu (Woods) | Destek-direnç ve bölgeler | range | 1 | orta |
| PA-SDR-08 | Basınç bölgesi ve kurulumu (Woods) | Destek-direnç ve bölgeler | her ikisi | 1 | orta |
| PA-SDR-09 | Kaygı bölgesi ve kurulumu (Woods) | Destek-direnç ve bölgeler | trend sonu | 1 | düşük |
| PA-KIR-01 | Kırılımın tanımı ve onayı | Kırılım ve sahte kırılım | trend / range sınırı | 6 | orta |
| PA-KIR-02 | Kırılım sonrası retest (rol değişimi) girişi | Kırılım ve sahte kırılım | her ikisi (trend yönünde) | 6 | orta |
| PA-KIR-03 | Sahte kırılım / SFP (seviyeyi delip geri kapanış, ters yön girişi) | Kırılım ve sahte kırılım | range ağırlıklı, trend geri çekilmesi dahil | 6 | orta |
| PA-KIR-04 | 1-2-3, Ross Hook, Trader's Trick Entry, başarısızlık (MI) | Kırılım ve sahte kırılım | trend dönüşü / geri çekilme | 1 | orta |
| PA-KIR-05 | Çift tepe / çift dip | Kırılım ve sahte kırılım | trend sonu (PA, MI, BR), range sınırı (DA) | 4 | orta |
| PA-KIR-06 | Baş-omuz / ters baş-omuz | Kırılım ve sahte kırılım | trend sonu | 3 | orta |
| PA-KIR-07 | Bayrak / üçgen / flama / kama (devam formasyonları) | Kırılım ve sahte kırılım | trend devamı | 1 | orta |
| PA-MUM-01 | Pin bar / çekiç / kayan yıldız | Mum formasyonları | trend sonu veya seviyede (seviye yakınlığı şart) | 6 | orta |
| PA-MUM-02 | Yutan mum (boğa / ayı) | Mum formasyonları | trend sonu | 3 | orta |
| PA-MUM-03 | Delici, kara bulut örtüsü, cımbız tepe/dip | Mum formasyonları | trend sonu | 1 | orta |
| PA-MUM-04 | Sabah/akşam yıldızı ve çok mumlu dönüş | Mum formasyonları | trend sonu | 2 | orta |
| PA-MUM-05 | İç bar, ii/iii, dış bar, NR4/NR7 | Mum formasyonları | sıkışma / trend başlangıcı | 3 | orta |
| PA-MUM-06 | Mum sınıflandırma ölçüleri (trend çubuğu, kapanış konumu, boyut) | Mum formasyonları | her ikisi | 4 | orta |
| PA-MUM-07 | Yavaşlama ve doruk karşıtı (4 bar) | Mum formasyonları | trend sonu aşırı uç | 1 | orta |
| PA-MUM-08 | Trend çubuğu arızası | Mum formasyonları | trend (karşı-trend dönüş) | 1 | yüksek |
| PA-TRD-01 | Trendde hareketli ortalamaya geri çekilme | Trend takibi girişleri (geri çekilme) | trend | 4 | orta |
| PA-TRD-02 | Yüksek/Düşük 1–4 (H2/L2) geri çekilme sayımı | Trend takibi girişleri (geri çekilme) | trend | 2 | orta |
| PA-TRD-03 | Zayıf geri çekme girişi ve yeniden giriş (Woods) | Trend takibi girişleri (geri çekilme) | trend | 1 | orta |
| PA-TRD-04 | Birikim/sıkışma sonrası trend yönlü kırılım (MBEE, ön-kırılma) | Trend takibi girişleri (geri çekilme) | trend (birikim sonrası) | 2 | orta |
| PA-TRD-05 | Seviye + tetikleyici mum birleşimi (konfluens, MAEE) | Trend takibi girişleri (geri çekilme) | trend geri çekilmesi veya range kenarı | 4 | orta |
| PA-YTY-01 | Range tespiti | Yatay piyasa ve ortalamaya dönüş | range | 5 | orta |
| PA-YTY-02 | Range kenarında ters yön (ortalamaya dönüş) girişi | Yatay piyasa ve ortalamaya dönüş | range | 5 | orta |
| PA-YTY-03 | Range oluşum filtresi (impulsif hareket sonrası) | Yatay piyasa ve ortalamaya dönüş | trend → range geçişi | 1 | orta |
| PA-YTY-04 | Range'de Fibonacci 0,702 / 0,786 alım bölgesi | Yatay piyasa ve ortalamaya dönüş | range | 1 | orta |
| PA-YTY-05 | Dar sıkışma: tıkanıklık, dikenli tel, çıkıntı, süre | Yatay piyasa ve ortalamaya dönüş | range (sıkışma) | 3 | orta |
| PA-FLT-01 | Üst zaman dilimi (HTF) yön filtresi | Volatilite ve filtreler | trend | 4 | orta |
| PA-FLT-02 | Hareketli ortalama trend filtresi | Volatilite ve filtreler | trend | 5 | orta |
| PA-FLT-03 | Volatilite rejimi (ATR oranı, daralma) | Volatilite ve filtreler | her ikisi | 2 | düşük |
| PA-FLT-04 | Aşırı uzama ve günlük hareket tükenmesi | Volatilite ve filtreler | trend | 1 | düşük |
| PA-FLT-05 | Hacim teyidi (opsiyonel) | Volatilite ve filtreler | her ikisi | 3 | düşük |
| PA-FLT-06 | Belirsiz yapı / tıkanıklıkta işlem yok | Volatilite ve filtreler | her ikisi | 3 | orta |
| PA-FLT-07 | Rejim testi: önceki gün kırılım sistemi | Volatilite ve filtreler | her ikisi | 1 | orta |
| PA-FLT-08 | Çoklu varlık korelasyon filtresi | Volatilite ve filtreler | her ikisi | 1 | orta |
| PA-STP-01 | Yapısal stop (yapı seviyesinin ötesi + tampon) | Stop yerleşimi | her ikisi | 7 | orta |
| PA-STP-02 | İz süren stop ve MA/swing bazlı çıkış | Stop yerleşimi | trend | 6 | orta |
| PA-STP-03 | Emir süresi ve zaman durdurma | Stop yerleşimi | her ikisi | 2 | orta |
| PA-HDF-01 | Sabit R hedefi ve minimum risk/ödül filtresi | Hedef ve çıkış | her ikisi | 6 | orta |
| PA-HDF-02 | Karşı seviye / karşı kenar / yakın swing hedefi | Hedef ve çıkış | her ikisi | 6 | orta |
| PA-HDF-03 | Ölçülen hareket | Hedef ve çıkış | her ikisi | 3 | orta |
| PA-HDF-04 | Fibonacci uzantı hedefleri | Hedef ve çıkış | trend | 2 | orta |
| PA-HDF-05 | Kısmi çıkış ve başa baş stop | Hedef ve çıkış | her ikisi | 3 | orta |
| PA-HDF-06 | Rejime göre çıkış modu | Hedef ve çıkış | her ikisi | 1 | orta |
| PA-RSK-01 | İşlem başına risk ve pozisyon boyutu | Pozisyon-risk | her ikisi | 2 | yüksek |
| PA-RSK-02 | Stop genişliğine göre işlem atlama | Pozisyon-risk | her ikisi | 3 | düşük |

---

## 4. Koda çevrilemeyenler (birleşik)

- **Psikoloji, disiplin, kişisel hikâye, para kazanma vaadi, reklam/bonus bağlantıları:** tüm kitaplarda, kural değil.
- **Emir akışı ve niyet çıkarımı:** tape/tik okuma, ısı haritası, pasif likidite, kurumsal/akıllı para niyeti, stop avının motivasyonu. OHLCV'de yok (AN, TE, MI, BR, PA).
- **Haber, temel analiz, opsiyon akışları, mevsimsellik, spread:** OHLCV dışı veri (AN, TE, PA, MI, BR).
- **Gap / seans / oturum kuralları:** kripto 7/24 olduğundan kapsam dışı (TE, MI, BR, DA, WO).
- **Öznel çizim ve görsel yargı:** "en belirgin seviye", "derin salınım" seçimi, "derece" (DA), kanal/kama/bayrak adlandırma, spike/merdiven, şekil ve grafik atıfları (hepsi). Kodlanabilen karşılıklar varsayılan eşiklerle verildi.
- **OHLCV dışı gösterge ve veri:** RSI/MACD sapması, Bollinger squeeze, hacim profili, nPOC. Stokastik ve RSI yalnızca MI'de opsiyonel filtre.
- **Bar içi (intrabar) giriş:** "mum kapanmadan gir", erken uzun/şort, tik/beş tık hatası, scalper tik hedefleri (AN, BR, MI).
- **Tik/pip/puan bazlı sabit değerler ve para stopu:** ATR oranına çevrildi, birebir taşınmadı.
- **Tanımı eksik kavramlar:** TTE istisna cümlesi, kaçış modu, kopma testi, yuvalama, "birleşim" ağırlıkları, kurulum kalite puanı, piyasa önyargısı analizi, değer alanının tanımı, Ross Hook seviyesi.
- **Önceki gün yüksek iz süren (TE 10b-K19):** cümle mantıksal olarak belirsiz, kodlanmadan önce teyit gerekir.
- **Performans iddiaları ve süreç önerileri:** kazanma oranı iddiaları, beklenti formülü, DERR, işlem günlüğü, backtest örneklemi ≥100 işlem (süreç notu olarak not edilir).
- **Okunamayan kısımlar:** DA kitabının son bölümü (OCR bozuk), MI ve WO'daki bazı kopuk satırlar, DA/MI/WO sayısal değerlerinin bozuk OCR'ı.

---

## 5. Çelişkiler (birleşik)

1. **Dokunma sayısı yönü.** AN, PA, DA ve TE başlığı: çok test edilen seviye zayıflar. TE gövdesi: çok test kırılma olasılığını artırır. MI: ≥2 dönüş "güçlü". Karar: `touch_count` parametre, yön backtestle (PA-SDR-02). [12a-K11 s.506–508; 10a s.942–961,1061–1104; 08a-K2 s.166–168; 05a-K5; 02a-K4]
2. **Seviye yaşı ve yenilik.** AN: eski seviye güçlü (s.270–274), yakın tarihli tepki daha önemli (s.278–280), seviye zamanla zayıflar (s.217–219). [12a-K11]
3. **Stop tamponu büyüklüğü.** TE sabit 1×ATR (kitap); PA, DA, MI 0,2; AN 0,1–0,2 (range 0,5); BR 0,1; WO 1 tik. Fark 10 kata kadar çıkıyor. Tarama parametresi (PA-STP-01). [10b-K14; 10c-K8; 08a-K10; 05a-K10; 02a-K20; 12a-K5; 23a; 31a-K1]
4. **Stop bağlamı.** Yapı stopu (HL) vs MA stopu (PA, s.434–437 ve 506–507), kapanış bazlı mı intrabar mı (AN s.1091–1095), kurulum barı dibi mi önceki bar dibi mi (WO 4-2 şekli `l[A]` vs genel kural). [08a; 12b-K11; 31a-K11]
5. **Giriş emri tipi.** Aynı kurulum için limit, stop emri ve kapanışta piyasa farklı kitaplarda öneriliyor (retest, pin, SFP). Üçü ayrı varyant olarak test edilir (PA-KIR-02, PA-MUM-01). [12a-K1/K4/K5; 10a-K5; 08a-K4; 31a]
6. **CHoCH giriş mi, uyarı mı.** AN yeni başlayanlara giriş olarak kullanmayı yasaklıyor, aynı bölümde CHoCH'a göre agresif giriş anlatıyor. [12b-K5 s.1328,1344–1348,1474–1476]
7. **Retest zorunluluğu.** AN ve MI "yalnız testte gir, ilk çıkış çoğunlukla yanlış" derken MI dar kama kırılımında test olmadığını, TE ise birikim üstüne direkt buy-stop önerir. [12a-K4; 02a-K14 s.1176–1179,1270–1271; 10b-K20]
8. **Konsolidasyonda işlem.** BR "konsolidasyonda ticaret yapılmaz", Ross konsolidasyon kırılmasını giriş sayıyor (kitap içinde); TE ve DA range'de ticaret yapıyor, WO tıkanıklık içi bölgeyi atlıyor. [02c-K6 s.2892–2894 ve s.2701–2723; 10a-K3; 05a; 31a-K20]
9. **TTE (erken) vs H2 (ikinci deneme).** İki farklı kurulum ve stop tanımı. [02c-K3 s.2741–2776 ve s.2910–2916]
10. **Trend çizgisi zorunlu mu.** DA K9 "zorunlu koşul" diyor, bazı örneklerde çizgi yok, filtre atlanıyor (varsayılan). [05a-K9 s.3638,3806–3807,4070–4072]
11. **Kısmi çıkış oranı.** TE %50 tavan ve %90 örnek aynı bölümde; başa baş taşıma kitaplarda net değil; AN aynı bölümde "ATH'de nakitteydim". [10b-K16; 10c-K12 s.2872–2878; 12b-K10]
12. **Geri çekilme sınıfı boşluğu.** TE güçlü ≤%38, sağlıklı ≤%50, zayıf ≥%62: %50–62 sınıfsız. WO güçlü geri çekilme için iki koşul ("veya"/"ve") belirsiz. [10c-K3 s.2465–2492; 31b-K1]
13. **Volatilite yönü.** MI düşük vol sonrası kırılım "daha olası" ve "daha az olası" diyor, yön belirsiz. [02b-K5 s.1556–1561,1959–1961]
14. **Yutan mum ek koşulu.** TE gövde yutma tanımı ve "kapanış önceki high üstünde" ek koşulu çakışıyor; delici ile ayrım; cımbızda "daha yüksek kapanış" anlamı belirsiz. [10b-K3,K4,K7]
15. **Swing N.** 1/2/3/5/10 arasında değişiyor. Tarama parametresi (PA-YAP-01).
16. **Fibonacci güveni.** AN ve MI fibi kullanıyor, WO yalnız %50–61,8 bölgesini alıyor ve diğer seviyelere güvenmiyor, MI'nin Ross/Brooks bölümü fibin önemli rol oynamadığını söylüyor. Trend tabanlı fibte P3 derinliği 0,5 mi 0,618 mi (AN). [31b; 02c s.2887–2888; 12c-K3 s.2203–2253]
17. **Dış bar.** WO "dış bardan kaçın" ve "diğer faktörler uygunsa kabul edilir" diyor. BR iç bar tanımı eşitliği içerir, diğerleri dışlar. [31b-K7 s.6224–6226; 23a-K2]
18. **Sıkı aralık / tıkanıklık bar sayısı.** BR 3 ve 2, WO ≥3 (örnek 5). [23a s.228,810–811; 31a-K2]
19. **Bölge ve zone tanımı.** WO sıkışıklık bölgesinde en yüksek bar mı kapanış mı; kaygı bölgesi geçersizliği "ulaşır" mı "geçer" mi; yeniden girişte stop'a değmek mi kurulum düşüğünü temizlemek mi belirleyici. [31a-K6,K22; 31b-K8]
20. **İsimlendirme ve yön.** WO yavaşlama/doruk karşıtı isimleri yönün tersini çağrıştırıyor, tanımlar sayısal olduğundan isimler yok sayıldı. [31a-K13–K16,K21]
21. **Range tanımı.** DA tam oluşum (iki taraf iki nokta) ile erken çizim (tek taraf iki nokta) arasında. Kodda erken çizim kullanılır, doğrulama PA-SDR-02 ile. [05a-K4 s.2971–2988,3295–3301]
22. **Hacim.** AN "düşük hacimli kırılım" için hem "direncin tutma şansı artar" hem "sahte olabilir" diyor (aynı yön). MI forex hacmini güvenilmez görüyor. [12a-K3; 02a-K13]
23. **Veri hatası.** MI pivot formülünde `/3` eksik (düzeltildi); PA'da bir cümlede "satın" yerine "sat" okunmalı (s.900–901); AN'da "%1 / -1" yazımı. [02a-K17; 08a; 12c-K1]
24. **R/R alt sınırı.** BR 1,0, DA 1,0 (hedef 2), PA 2, TE 0,8. Tarama parametresi (PA-HDF-01).
