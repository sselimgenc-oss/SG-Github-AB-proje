# Parça planı denetimi (15 Kasım 2026)

**Hüküm: düzeltmeli.** Omurga doğru (freqtrade tabanı, risk çerçevesi, ölçüm araçları, lisans seçimleri). Ama ilk sürüm için fazla geniş, dört parça eksik, iki yerde parçalar birbirini engelliyor. Bu denetim yalnızca kod okumaya ve araştırma notlarına dayanır; hiçbir şey çalıştırılmadı.

## Düzeltilmiş plan

| Parça | Kaynak | Nasıl | İlk sürümde? |
|---|---|---|---|
| Emir altyapısı, sahte para | freqtrade | hazır | Evet |
| Fırsat bulma: kurallar + tek "piyasa durumu" etiketi (gün içi/swing ayarını bu seçer) | kendimiz | yaz | Evet |
| Makine öğrenmesi (FreqAI) | freqtrade | — | Sonra |
| Değişmez risk kuralları + "zarar durdurma likidasyondan önce" kontrolü | A3 | uyarla (%2, %5, 3-5x) | Evet |
| LLM veto | R3 doğrulama mantığı + C3 dosya deseni | uyarla: Claude ayrı süreçte çalışır, kararı dosyaya yazar; strateji yalnızca dosyayı okur | Evet |
| Claude harcama tavanı | Anthropic konsolu (gorev9) | ayar + "limit dolunca dur, haber ver" | Evet |
| Funding / açık pozisyon verisi | Binance açık verisi | kendimiz yaz | Evet |
| Haberler | ücretli servis | — | Sonra |
| Tek kayıt defteri + tek canlı ayar dosyası | G3 | uyarla | Evet |
| Dondurulmuş ikiz, al-tut, rastgele giriş kolları | ikinci freqtrade kopyası + G2 | kur / doğrudan al | Evet |
| Öğrenmenin dokunabileceği sınırlar | R2 şablonu + R1 fikri | şablonu al, uygulayan mekanizmayı yaz | Evet |
| Ders çıkarma | kendimiz (fikir: C1, S1, H1) | yaz | Evet, ama yalnızca "aday" olarak kaydeder |
| Test-et-terfi kapısı | A1 iskeleti + G1 | uyarla | Sonra (3. haftadan itibaren) |
| Geri alma | R1 fikri | yaz | Sonra (kapıyla birlikte) |
| Durdurma düğmesi | freqtrade Telegram komutları | hazır | Evet |
| Bağımsız risk bekçisi | G5 fikri | yaz | Sonra |
| Telegram, panel | freqtrade | hazır | Evet |
| Günlük öğrenme özeti + onay sorusu | yok | yaz (basit) | Evet |

## Değişiklikler ve gerekçeleri

1. **FreqAI ertelendi.** Kendi yeniden eğitimi ikinci bir "öğrenme" olur, ölçümü bulandırır; dondurma tarifi de denenmemiş bir çıkarım. Karar 4 "kurallar veya ML" dediği için kararı bozmaz.
2. **Veto, A3'ün korumalı kodunun içine taşındı.** A3 giriş onayı fonksiyonunun değiştirilmesini yasaklıyor; R3 ise tam orada, 20 saniyeye kadar botu bekleterek çalışıyor.
3. **Veto dosyası öğrenen bot ile ikizde ortak.** Yoksa Claude'un cevap farkları "öğrenme" gibi görünür.
4. **Kayıt defteri, ikiz/kontrol kolları, harcama tavanı, rejim etiketi eklendi.** Taslakta yoktu; onaylı test yöntemi bunlarsız çalışmaz.
5. **R2 tek başına yetmez.** Yalnızca sınır listesi; sınırı uygulayan kısım (R1) yazılmalı.
6. **Terfi ve geri alma sonraya.** İlk iki hafta zaten "öneri kaydet, uygulama" dönemi. Kapı yazılırken: karşılaştırma başarısız olursa terfi reddedilmeli (A1'de tersine geçiyor); bekçi yalnızca durdurur, ayar yüklemeyi engellemez.
7. **Haber sonraya — onayınız gerekir (Karar 3'ten sapma).** Ücretli anahtar ister; haber metni LLM'i yanıltma kapısı açar.
8. **G3 ve G4 "doğrudan" değil "uyarla".** Katalog böyle diyor; G4 ilk sürümde gereksiz.
9. **Günlük öğrenme özeti ve onay sorusu hazır değil.** freqtrade kâr/zarar bildirir; ders özeti ve "onaylıyor musun" sorusu yazılmalı.

## Lisans

Sorun yok. A ve R (MIT), G (Apache; NOTICE dosyası korunmalı) kopyalanabilir. cryptobot, astra, HydraQuant'tan yalnızca fikir alınıyor; taslak bunu doğru yapmış. Botu başkasına dağıtmadıkça kaynak açma yükümlülüğü doğmaz. Hukuki görüş değildir.

## Erişim kısıtları

freqtrade, Binance'in deneme hesabını desteklemiyor: sahte paradan sonraki adım doğrudan küçük gerçek para. Türkiye'den vadeli işlem yalnızca binance.com üzerinden ve hukuken gri alanda. Kaldıraçlı aynı hesapta iki bot çalışamaz; kontrol kolları sahte parada kalır.

## En büyük risk

Botun gürültüden "ders" çıkarması. 20-30 işlem ve 4-8 hafta, öğrenmeyi şanstan ayırmaya yetmez; test en fazla "elendi / elenmedi" der. Önlem: dar sınırlar, haftada en fazla bir değişiklik, her öneri deftere, ikizle kıyas. İkinci risk: on parçanın hiçbiri henüz çalıştırılmadı, çoğu yıldızsız depolardan.

## Görev 6'nın doğrulaması gereken üç şey

1. **Vadeli sahte para uçtan uca:** botun çalışacağı makineden anahtarsız veri geliyor mu; kaldıraçlı alış ve açığa satış açılıyor mu; zarar durdurma likidasyondan önce tetikleniyor ve kayıp bakiyenin yaklaşık %2'si mi.
2. **İki özdeş kopya yan yana:** ayrı veritabanı ve portla aynı işlemleri açıyorlar mı (hedef en az %95 eşleşme). Tutmazsa öğrenme ölçülemez.
3. **Veto ve ayar yolu:** veto dosyası yokken, bayatken veya Claude limiti dolmuşken giriş reddediliyor mu; ayar dosyası değişince bot açık pozisyonları bozmadan yenisini yüklüyor mu.

## Ek aday: tradermonty/claude-trading-skills (15 Kasım 2026, hızlı bakış)

MIT, aktif (son commit 2026-11-14), Claude skill koleksiyonu. Otonom bot DEĞİL (README: "not designed for fully automated trading"). Yalnızca README + dosya yapısı + SKILL.md açıklamaları okundu; kod ve testler incelenmedi/çalıştırılmadı. Parça adayı olarak işaretlenenler:
- `skills/crypto-regime-analyzer`: anahtarsız açık veriyle (CoinGecko + Binance funding) 0-100 kripto rejim skoru, 6 bileşen. → MVP'deki "piyasa durumu etiketi" için aday (uyarla).
- `skills/signal-postmortem`: sinyal sonuçlarını sınıflandırıp (yanlış pozitif, kaçan fırsat, rejim uyumsuzluğu) ağırlıklara geri besleme; testli. → "ders çıkarma" için fikir/uyarlama adayı.
- `skills/drawdown-circuit-breaker`: kayıp serisi bekleme süresi, haftalık/aylık düşüş limitleri; testli. → risk çerçevesine ek adayı.
- Faz 2 (ABD hisseleri) için çok sayıda tarayıcı/analiz skill'i var.
- `futures-position-sizer` CME vadeli kontratları içindir, kripto perp için uygun değil.
