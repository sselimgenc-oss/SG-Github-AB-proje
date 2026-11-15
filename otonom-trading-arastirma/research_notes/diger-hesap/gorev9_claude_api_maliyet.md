# Haiku 5.5 ile analist katmanı ayda 3 dolara çalışır

Kasım 2026 fiyatlarıyla, 5-10 pariteli bir kripto botuna Claude "analist + öğrenme" katmanı eklemek 50 USD bütçenin çok altında kalıyor. **Önerilen kombinasyon: 15-30 dakikalık döngüde, tek istekte 8 pariteyi değerlendiren Claude Haiku 5.5 (1 saatlik önbellekle) ve günde 1-4 kez Batch API ile çalışan Sonnet 5.5 "ders" işi.** Hesabıma göre bu kurulum ayda yaklaşık **1,3-2,6 USD (döngü) + 0,4-1,6 USD (ders) = 2-4 USD** tutuyor. Sonnet 5.5'i döngüye koymak 15 dakikada ~51 USD ile bütçeyi aşıyor, 30 dakikada ~26 USD ile sığıyor; Opus 5.5 döngüde yalnızca 60 dakikada sığıyor (~26 USD). Bu rakamlar kendi token varsayımlarıma dayanıyor ve iki belirsizliğe çok duyarlı: Sonnet 5.5'in varsayılan "adaptive thinking"i (düşünme tokenleri çıktı fiyatından faturalanır) ve yeni tokenizer'ın ~%30 ek token üretmesi. Haiku 5.5'in 0,10/0,50 USD fiyatı, Haiku 4.5'in (1/5 USD) 10'da biri olduğu için şaşırtıcı görünüyor; **bütçe kararı vermeden önce resmî fiyat sayfasında doğrulayın.** Harcama güvenliği için ayrı bir workspace, Console'da aylık limit ve uygulama içi kill switch birlikte kullanılmalı; kendi koyduğunuz limit HTTP 400, katman tavanı ise HTTP 429 döndürür ve ikisi de "yeniden deneme" değil "dur" sinyalidir.

## Fiyatlar: Haiku 5.5 en ucuz, Sonnet 5.5 yirmide bir kat pahalı değil, yirmi kat pahalı

Resmî fiyat sayfası (https://platform.claude.com/docs/en/about-claude/pricing) milyon token (MTok) başına şu değerleri listeliyor ([Pricing](https://platform.claude.com/docs/en/about-claude/pricing)):

| Model (API ID) | Girdi | 5 dk önbellek yazma | 1 saat önbellek yazma | Önbellek okuma | Çıktı | Batch (girdi/çıktı) |
|---|---|---|---|---|---|---|
| Haiku 5.5 (`claude-haiku-5-5`), ≤100k token istek | 0,10 | 0,125 | 0,20 | 0,01 | 0,50 | 0,05 / 0,25 |
| Sonnet 5.5 (`claude-sonnet-5-5`) | 2 | 2,50 | 4 | 0,10 | 10 | 1 / 5 |
| Opus 5.5 (`claude-opus-5-5`) | 4 | 5 | 8 | 0,20 | 20 | 2 / 10 |
| Fable 5.2 (`claude-fable-5-2`) | 8 | 10 | 16 | 0,20 | 40 | 4 / 20 |
| Haiku 4.5 (karşılaştırma) | 1 | 1,25 | 2 | 0,10 | 5 | 0,50 / 2,50 |

Haiku 5.5'te istek 100.000 token'ı aşarsa fiyat 0,50/2,50 USD'ye çıkıyor; bu eşik önbellek okuma/yazmayı da sayıyor ([Pricing](https://platform.claude.com/docs/en/about-claude/pricing)). Bu senaryoda istekler ~7k token olduğundan eşik önemsiz. Sonnet 5.5, Sonnet 5 ile aynı fiyatta; yalnızca önbellek okuması 0,10 USD ve önbellek asgari boyutu 512 token ([Sonnet 5.5 migration guide](https://platform.claude.com/docs/en/models/sonnet-5-5/migration-guide)). Notlara göre Sonnet 5'in 3/15 USD'ye çıkması planı iptal edilmiş, 2/10 USD kalıcı ([Pricing](https://platform.claude.com/docs/en/about-claude/pricing)).

İki doğrulama uyarısı: (1) Notlardan biri fiyat rakamlarının "özetlenmiş bir çekimden" geldiğini ve bütçelemeden önce sayfayla karşılaştırılması gerektiğini belirtiyor; (2) model ID'leri yalnızca Batch sayfasının metadata listesinden alındı, model genel bakış sayfası (https://platform.claude.com/docs/en/models/overview) çekilemedi, özellikle Fable 5.2 ID'sini kodlamadan önce doğrulayın. Ayrıca `claude-sonnet-5-5` gibi tarihsiz ID'ler bir takma ad olabilir; sabitleme (pinning) politikası doğrulanmadı.

## Önbellek ve Batch: 15 dakikalık döngüde 5 dakikalık önbellek işe yaramaz

Önbellek yazması 5 dakikalık TTL için 1,25x, 1 saatlik TTL için 2x; okuma çoğu modelde 0,1x, ancak Sonnet 5.5 ve Opus 5.5'te 0,05x. 5 dakikalık yazma bir okumada, 1 saatlik yazma iki okumada kendini amorti ediyor ([Pricing](https://platform.claude.com/docs/en/about-claude/pricing)). Varsayılan TTL 5 dakika ve her kullanımda ek ücretsiz yenileniyor; yani yalnızca çağrılar arası 5 dakikadan kısaysa canlı kalıyor ([Prompt caching](https://platform.claude.com/en/docs/build-with-claude/prompt-caching)). Dolayısıyla **15, 30 ve 60 dakikalık döngülerin hepsinde 5 dakikalık önbellek her çağrıda yeniden yazılır ve düz fiyattan daha pahalıdır; 1 saatlik TTL gerekir.** Resmî maliyet rehberi de çağrı aralığı 5 dakikayı aşınca 1 saatlik önbelleği öneriyor ([Optimizing for cost](https://platform.claude.com/docs/en/about-claude/models/optimizing-for-cost-and-intelligence)). Tek bir sınır durumu var: 60 dakikalık döngüde bir sonraki çağrı tam 60. dakikada gelirse süre hemen hemen dolmuş olur; TTL isteğin başlangıcından ölçüldüğü için bu durumda her çağrının yazma ödemesi gerekebilir (tabloda "1h en kötü" sütunu). Önbellek 512 token altında sessizce devre dışı kalır; sistem istemi + şema ~1.500 token olduğundan sorun yok. Kural olarak sabit kısmı (kurallar, şema, örnekler) başa, zaman damgası ve piyasa verisini sona koyun; araç tanımı, sistem istemi veya `output_config.format` değişirse önbellek geçersiz olur ([Prompt caching](https://platform.claude.com/en/docs/build-with-claude/prompt-caching), [Structured outputs](https://platform.claude.com/docs/en/build-with-claude/structured-outputs)).

Batch API tüm girdi ve çıktıda %50 indirim veriyor ve önbellekle birleşiyor; fakat sonuçlar "24 saat içinde" geliyor (çoğu 1 saat içinde), canlı gecikme garantisi yok ([Batch processing](https://platform.claude.com/docs/en/build-with-claude/batch-processing)). **Karar döngüsü (a) için uygunsuz, günlük ders işi (b) için ideal.** Batch'te önbellek isabeti "en iyi çabayla" (tipik %30-98) ve belgeler 1 saatlik TTL öneriyor; Batch ayrıca sıfır veri saklama kapsamında değil (29 gün). Ders işi tek istek ve altı-yedi bin token olduğu için önbelleğe ihtiyaç yok.

## Maliyet hesabı: varsayımlar ve tablolar

Hesabı Python ile yaptım (30 günlük ay; fiyatlar yukarıdaki tablodan). Senaryo (a) varsayımları: döngü başına **tek istek, 8 parite**; statik sistem istemi + şema **1.500 token (önbellekli)**; pariteye özel dinamik veri **600 token** (8 x 600 = 4.800); çıktı **100 token/parite = 800 token/istek**; döngü sayısı 15 dk = 2.880, 30 dk = 1.440, 60 dk = 720. İstek başına toplam girdi 6.300 token. "1 saat" satırında önbellek her kullanımda yenilendiği için ayda ~30 yazma (günde 1), geri kalan hepsi okuma kabul edildi. Bu token sayıları tahmindir; gerçek sayıları `usage` alanından ve `count_tokens` ucundan ölçün.

**(a) Aylık maliyet, USD: tek toplu istek (8 parite), düşünme tokeni yok varsayımıyla**

| Model | Önbellek | 15 dk | 30 dk | 60 dk |
|---|---|---|---|---|
| Haiku 5.5 | yok | 2,97 | 1,48 | 0,74 |
| Haiku 5.5 | 5 dk yazma (her çağrıda süresi dolar) | 3,07 | 1,54 | 0,77 |
| Haiku 5.5 | 1 saat | **2,59** | **1,30** | **0,65** |
| Sonnet 5.5 | yok | 59,33 | 29,66 | 14,83 |
| Sonnet 5.5 | 5 dk | 61,49 | 30,74 | 15,37 |
| Sonnet 5.5 | 1 saat | 51,30 | **25,74** | **12,96** |
| Opus 5.5 | yok | 118,66 | 59,33 | 29,66 |
| Opus 5.5 | 5 dk | 122,98 | 61,49 | 30,74 |
| Opus 5.5 | 1 saat | 102,59 | 51,47 | **25,91** |

"1 saat en kötü" durumu (her çağrıda 1 saatlik yazma): Haiku 3,40 / 1,70 / 0,85; Sonnet 67,97 / 33,98 / 16,99; Opus 135,94 / 67,97 / 33,98 (15/30/60 dk). Dikkat: kısa statik kısım (1.500 token) olduğu için önbellek toplamı yalnızca ~%13-14 düşürüyor; asıl maliyet 4.800 token'lık dinamik veri ve çıktıda. Önbellek, paritelere ayrılmış çağrılarda daha değerli:

**Karşılaştırma: pariteye ayrı çağrı (8 çağrı/döngü, her biri 1.500 statik + 600 dinamik girdi, 100 çıktı), USD/ay**

| Model | Önbellek | 15 dk | 30 dk | 60 dk |
|---|---|---|---|---|
| Haiku 5.5 | yok | 5,99 | 3,00 | 1,50 |
| Haiku 5.5 | 1 saat | 2,89 | 1,45 | 0,73 |
| Sonnet 5.5 | yok | 119,81 | 59,90 | 29,95 |
| Sonnet 5.5 | 5 dk (döngüde ilk çağrı yazar, 7'si okur) | 64,51 | 32,26 | 16,13 |
| Sonnet 5.5 | 1 saat | 54,32 | 27,25 | 13,71 |
| Opus 5.5 | 1 saat | 108,64 | 54,49 | 27,42 |

Ayrı çağrılar önbellek olmadan toplu isteğin yaklaşık iki katı; önbellekle fark ~%10'a iniyor. Toplu istek hâlâ biraz ucuz ve tek geri-çağrı noktası sunuyor, ancak pariteler arası "bulaşma" ve tek hatanın tüm döngüyü etkilemesi riski var; yapılandırılmış JSON'u parite başına doğrulayın. Paritelere ayrılmış çağrılar tek bir parite bozulduğunda yalnızca onu veto eder, hata yalıtımı için makul bir ödünleşim.

**Duyarlılık: 30 dk döngü, 1 saat önbellek, toplu istek, USD/ay**

| Senaryo | Haiku 5.5 | Sonnet 5.5 | Opus 5.5 |
|---|---|---|---|
| Taban | 1,30 | 25,74 | 51,47 |
| Tokenizer +%30 (girdi ve çıktı) | 1,69 | 33,46 | 66,91 |
| +500 düşünme tokeni/çağrı | 1,66 | 32,94 | 65,87 |
| +2.000 düşünme tokeni/çağrı | 2,74 | 54,54 | 109,07 |
| +2.000 düşünme ve +%30 tokenizer | 3,56 | 70,91 | 141,79 |

Düşünme duyarlılığı kritik: Sonnet 5.5'te `thinking` alanı verilmezse varsayılan olarak adaptive thinking çalışır, `disabled` HTTP 400 döndürür ve en alt ayar `thinking: {"type":"between_tools"}`; düşünme tokenleri çıktı olarak faturalanır, `max_tokens` düşünme + metni kapsar. Opus 5.5 ve Fable 5.x'te düşünme her zaman açık. **Haiku 5.5 ise `thinking: {"type":"disabled"}` kabul ediyor** (xhigh/max effort ile birlikte hariç) ([Sonnet 5.5 migration guide](https://platform.claude.com/docs/en/models/sonnet-5-5/migration-guide), [API errors](https://platform.claude.com/docs/en/api/errors)). Bu yüzden Haiku tabloları ancak düşünme kapalıyken geçerli; Sonnet/Opus tablolarını "+500" satırıyla okumak daha gerçekçi. Varsayılan effort `high`; gecikmeye duyarlı iş için `low`/`medium` öneriliyor, bu da maliyeti düşürür (hepsi kıyaslanmadı). Tokenizer notu: Claude 4.7+ ve 5.x yeni tokenizer ile aynı metinde yaklaşık %30 fazla token üretir ([Pricing](https://platform.claude.com/docs/en/about-claude/pricing)); fiyatlar zaten bu tokenizer üzerinden, ama benim token tahminlerim eski tokenizer ile yapılmışsa %30 ekleyin (ilgili satır). Ek not: 10 pariteyle 15 dk Haiku 3,22 USD, Sonnet 63,97 USD olur.

**(b) Ders çıkarma: çalıştırma başına 6.000 girdi + 1.500 çıktı token, USD/ay (30 gün)**

| Model | Mod | 1 çalıştırma/gün | 2/gün | 4/gün | 4/gün + 2.000 düşünme tokeni |
|---|---|---|---|---|---|
| Sonnet 5.5 | standart | 0,81 | 1,62 | 3,24 | 5,64 |
| Sonnet 5.5 | Batch | 0,41 | 0,81 | 1,62 | 2,82 |
| Opus 5.5 | standart | 1,62 | 3,24 | 6,48 | 11,28 |
| Opus 5.5 | Batch | 0,81 | 1,62 | 3,24 | 5,64 |
| Fable 5.2 | standart | 3,24 | 6,48 | 12,96 | 22,56 |
| Fable 5.2 | Batch | 1,62 | 3,24 | 6,48 | 11,28 |

+%30 tokenizer, en pahalı hücreyi (Fable standart, 4/gün) 16,85 USD'ye çıkarır. Ders işi gün içinde birkaç kez ve acil değil, dolayısıyla Batch'e uygun; Sonnet 5.5 Batch ile en yoğun kullanımda bile ~1,6-2,8 USD.

**Birleşik tablo: (a) 1 saat önbellekli toplu istek + (b) Batch ders işi, bütçe 50 USD**

| (a) modeli / döngü | (a) tek başına | + (b) Sonnet Batch 1/gün | + (b) Sonnet Batch 4/gün | + (b) Opus Batch 4/gün | Bütçe durumu |
|---|---|---|---|---|---|
| Haiku 5.5 / 15 dk | 2,59 | 2,99 | 4,21 | 5,83 | Çok geniş pay |
| Haiku 5.5 / 30 dk | 1,30 | 1,70 | 2,92 | 4,54 | Çok geniş pay |
| Haiku 5.5 / 60 dk | 0,65 | 1,06 | 2,27 | 3,89 | Çok geniş pay |
| Sonnet 5.5 / 15 dk | 51,30 | 51,70 | 52,92 | 54,54 | **Bütçeyi aşar** |
| Sonnet 5.5 / 30 dk | 25,74 | 26,14 | 27,36 | 28,98 | Sığar, düşünme/tokenizer riski ile ~35-70 USD'ye çıkabilir |
| Sonnet 5.5 / 60 dk | 12,96 | 13,36 | 14,58 | 16,20 | Sığar |

En kötü durumda, Sonnet 5.5 / 15 dk + 2.000 düşünme + %30 tokenizer ile Opus 5.5 4/gün standart (düşünme dahil) toplamı ~156 USD'ye çıkar; yani yanlış model/ayar kombinasyonu bütçeyi üç katına çıkarabilir. Olay güdümlü kapılama (aşağıda) ile döngülerin %30'unda çağrı yapılırsa Sonnet 5.5 / 1 saat önbellek 15/30/60 dk için 15,51 / 7,84 / 4,01 USD olur; gating Sonnet'i de bütçe içine sokar.

## Öneri: Haiku 5.5 döngü, Sonnet 5.5 Batch ders, olay güdümlü kapı

**Önerilen kombinasyon:** döngü için `claude-haiku-5-5`, **30 dakikada bir** (olay olursa daha sık), tek istekte 8 parite, `thinking: {"type":"disabled"}`, 1 saatlik önbellek, aylık ~1,3-2,6 USD. Ders işi için `claude-sonnet-5-5` Batch ile günde 1-4 kez, ~0,4-1,6 USD. Toplam ~2-4 USD; geriye ~46 USD kalıyor. Bu pay iki şekilde kullanılabilir: (i) döngüyü 15 dakikaya indirmek, veya (ii) veto kararını yalnızca belirsiz durumlarda Sonnet 5.5'e yükseltmek (Haiku "emin değil" derse veya güven düşükse). Resmî rehber de önce en ucuz modeli, yalnızca başarısızları yükseltmeyi öneriyor: düşük effort'ta çalışıp sadece başarısızları yeniden çalıştırmak tam-yüksek ayara göre ~%40 ucuz ([Optimizing for cost](https://platform.claude.com/docs/en/about-claude/models/optimizing-for-cost-and-intelligence)). Haiku 5.5'in "yüksek hacimli, kontrol edilebilir çıktılı işler" için tarif edildiği doğru ([Optimizing for cost](https://platform.claude.com/docs/en/about-claude/models/optimizing-for-cost-and-intelligence)), ancak bir veto kararının finansal kalitesi için yeterli olup olmadığı notlarda değerlendirilmedi: **kendi geçmiş verinizle bir değerlendirme (eval) yapmadan Haiku'yu tek karar mercii yapmayın.**

**Olay güdümlü kapılama** (resmî öneri değil, mühendislik çıkarımı): mum kapanışında veya bir gösterge eşiği/farkı aşıldığında (ör. son değerlendirilen özetin hash'inden fazla sapma, funding veya açık pozisyon değişimi) çağır; sakin piyasada son kararı parite başına TTL ile önbelleğe al. Bu, çağrıları sakin dönemlerde sıfıra yaklaştırır. Haber özeti değişmediyse göndermeyin.

**Güvenli-başarısızlık tasarımı:** aşağıdakilerden herhangi biri olursa karar **veto/işlem yok** olsun, `request-id` loglansın, uyarı gitsin, asla varsayılan "onay" olmasın: yeniden denemeler sonrası istisna, `stop_reason` değeri `end_turn` dışında (özellikle `refusal` ve `max_tokens`), JSON ayrıştırma hatası, enum dışı değer, güven değeri [0,1] dışı veya NaN, 400/401/402/403 ve spend-limit hataları. İsteğe bağlı: onay için güven eşiği.

**Yapılandırılmış JSON** (resmî): `output_config.format = {"type":"json_schema","schema":{...}}` artık GA, beta başlığı gerekmiyor ve tüm modellerde çalışıyor; JSON yanıtın metin bloğunda geliyor ([Structured outputs](https://platform.claude.com/docs/en/build-with-claude/structured-outputs)). Önemli farklar: eski `output_format` parametresi kullanımdan kalktı; **Sonnet 5.5, Opus 5.5 ve Fable/Mythos 5.1-5.2 modellerinde zorunlu `tool_choice` (`any`/`tool`) 400 döndürüyor**, bunun yerine `auto` + `strict: true` veya yapılandırılmış çıktı kullanın ([Define tools](https://platform.claude.com/docs/en/agents-and-tools/tool-use/define-tools)); prefill 4.6+ modellerinde 400 ([API errors](https://platform.claude.com/docs/en/api/errors)); Sonnet 5.5 `temperature/top_p/top_k` parametrelerini reddediyor ([Sonnet 5.5 migration guide](https://platform.claude.com/docs/en/models/sonnet-5-5/migration-guide), Haiku/Opus 5.5 için doğrulanmadı). Şema `minimum/maximum` ve string uzunluğu kısıtlarını desteklemiyor, bu yüzden güven değerinin aralığını istemci tarafında doğrulayın (veya `low/medium/high` enum kullanın). Şemadaki `additionalProperties: false` zorunlu. `refusal` HTTP 200 ve faturalı; adım adım muhakeme isteyen bir şema alanı `reasoning_extraction` reddine yol açabilir, bu yüzden `rationale` kısa tutulmalı. Enum büyük/küçük harf garantisi yok, büyük/küçük harfe duyarsız karşılaştırın. Şemayı sabit tutun: grammar önbelleği son kullanımdan 24 saat geçerli ve şema değişimi istem önbelleğini de geçersiz kılar ([Structured outputs](https://platform.claude.com/docs/en/build-with-claude/structured-outputs)). Yapılandırılmış çıktı için eklenen sistem istemi ek girdi token'ı demek, ama belgelerde sayısı yok; ölçün.

**Hız limitleri, hata ve zaman aşımı:** Katmanlar artık Evaluation/Start/Build/Scale/Custom ve otomatik atanıyor; resmî destek sayfası "bir depozito veya satın alma sizi yükseltmez" diyor ([Support: higher rate limits](https://support.claude.com/en/articles/10366389-how-can-i-get-higher-rate-limits-on-the-claude-api)). Start katmanında Haiku/Sonnet/Opus 5.5 için 4.000 RPM, 2M girdi ve 400k çıktı token/dk limiti var ([Rate limits](https://platform.claude.com/docs/en/api/rate-limits)); sizin yükünüz bunun %0,01'i civarında, hız limiti pratik risk değil, harcama tavanı risk. Evaluation katmanı limitleri yayımlanmamış ve yeni bir hesabın Sonnet 5.5'i hemen kullanıp kullanamayacağı doğrulanmadı. Eski depozito eşikleri (Tier 1-4) bulunamadı; üçüncü taraf blogları bir yeniden adlandırma iddia ediyor, doğrulanmadı. Hata yönetimi için: 408/409/429/5xx/bağlantı hatalarını (529 ve 504 dahil) üstel geri çekilmeyle yeniden deneyin, `retry-after` başlığına uyun; 400/401/402/403/404/413'ü ve `enforced_spend_limit_reached` 429'unu **denemeyin** ([API errors](https://platform.claude.com/docs/en/api/errors), [Rate limits](https://platform.claude.com/docs/en/api/rate-limits)). Resmî SDK'lar varsayılan olarak 2 yeniden deneme ve 10 dakikalık zaman aşımı kullanır ([Python SDK](https://platform.claude.com/docs/en/cli-sdks-libraries/sdks/python)); küçük bir JSON çağrısı için `timeout` ~30-60 sn ve `max_retries` 2-3 önerim (resmî sayı değil). Hız limiti 429'unda `ramp_limit_exceeded` kodu ani artışlarda görülebilir. `max_tokens`'ı düşünme + JSON'u kapsayacak şekilde ayarlayın (Sonnet 5.5 için 2.000-4.000 baş boşluk; `max_tokens` OTPM'e sayılmıyor), ama `max_tokens` modelin kısa yazmasını sağlamaz, bunun için kısa şema ve istem gerekir. Zaman aşımı veya istemci kopması durumunda başarıya gidecek bir istek yine de ücretlendirilebilir ([Support: paying for API usage](https://support.claude.com/en/articles/8977456-how-do-i-pay-for-my-claude-api-usage)).

## Harcama limiti: üç katman, iki farklı hata kodu

Üç katman birlikte çalışıyor: katman başına otomatik aylık tavan (Start 500, Build 1.000, Scale 200.000 USD), kendi koyduğunuz organizasyon aylık limiti ve isteğe bağlı workspace limiti ([Rate limits](https://platform.claude.com/docs/en/api/rate-limits)). Kendi limitiniz katman tavanının altında olmak zorunda. Adımlar:

| Adım | Nerede / ne yapılır |
|---|---|
| 1. Bot için ayrı workspace | Settings > Workspaces > Create workspace (yönetici gerekir), örn. `crypto-bot-prod`. Anahtarlar workspace'ler arası taşınamaz; önbellek de workspace başına yalıtılıdır, botu bölmeyin ([Workspaces](https://platform.claude.com/docs/en/manage-claude/workspaces)). |
| 2. API anahtarı | platform.claude.com/settings/keys, açılır listeden workspace'i seç, "Create key" ([Support](https://support.claude.com/en/articles/9796807-creating-and-managing-spend-limits-on-the-claude-developer-platform)). |
| 3. Organizasyon aylık limiti | Settings > Spend limits (platform.claude.com/settings/spend-limits) > "Monthly spend limit" yanında "Set limit"/"Adjust limit", katman tavanını aşmayan bir değer girin, örn. 50 USD ([Rate limits](https://platform.claude.com/docs/en/api/rate-limits)). |
| 4. Workspace aylık limiti | Workspaces > workspace > Spend limits > "Monthly limit: Change limit", org limitinden düşük (örn. 20-30 USD). Default workspace'e konamaz ([Support](https://support.claude.com/en/articles/9796807-creating-and-managing-spend-limits-on-the-claude-developer-platform)). |
| 5. E-posta uyarısı | Aynı sayfada "Email notification: + Add notification", örn. %50 ve %80 tutarları. |
| 6. Ön ödemeli kredi | platform.claude.com/settings/billing > Credit balance; auto-reload KAPALI bırakın (kredi bitince API durur). Krediler bir yıl sonra sona erer, iade edilmez ([Support](https://support.claude.com/en/articles/8977456-how-do-i-pay-for-my-claude-api-usage)). |

Doğrulanamayan noktalar: destek makalesi menü yolunu "Workspaces > workspace > Spend limits", resmî doküman ise "Settings > Spend limits > Workspace limits açılır menüsü" olarak anlatıyor; ikisi büyük olasılıkla aynı özelliğe götürüyor ama canlı Console'da görsel olarak doğrulanmadı. E-posta uyarılarının "Anthropic sizi doğrudan faturalandırıyorsa" geçerli olduğu yazıyor; ön ödemeli hesapta çalışıp çalışmadığı belirsiz, ayrıca düşük bakiye e-postası için resmî sayfa bulunamadı. Günlük tavan Console arayüzünde yok; programatik `POST /v1/organizations/spend_limits` ucu günlük/haftalık/aylık destekler ama Console organizasyonları için "early access preview" ([Set Spend Limit](https://platform.claude.com/docs/en/api/beta/organization/spend_limits/set)). Günlük kill switch'i uygulamada yapın.

**400 ve 429 davranışı:** kendi koyduğunuz limit dolduğunda **HTTP 400** `invalid_request_error` ve "You have reached your specified API usage limits..." mesajı gelir (workspace için "...workspace API usage limits"), erişimin ne zaman döneceğini söyler; limiti yükseltirseniz daha erken açılır. Katman tavanı dolduğunda **HTTP 429** `rate_limit_error` ve `error.details.error_code == "enforced_spend_limit_reached"` gelir, erişim ayın 1'inde 00:00 UTC'de döner ve **`retry-after` başlığı yoktur**, SDK'nın otomatik denemeleri boşa gider ([Rate limits](https://platform.claude.com/docs/en/api/rate-limits)). Botunuz ikisini de "dur ve uyar, tekrar deneme" olarak ele almalı; 400 genel olarak da yeniden denenmemesi gereken bir sınıf. Batch API workspace harcama limitini hafifçe aşabilir ([Batch processing](https://platform.claude.com/docs/en/build-with-claude/batch-processing)); bu yüzden ders işini küçük tutun. Uygulama içi koruma için her yanıttaki `usage` alanının beş token sınıfını (`input_tokens`, `cache_creation_input_tokens`, `cache_read_input_tokens`, `output_tokens` ve 5m/1h yazma kırılımı) kendi fiyatıyla çarparak yerel bir günlük/aylık defter tutun; çağrı öncesi `bugünkü_harcama + en_kötü_maliyet < GÜNLÜK_LİMİT` kontrolü yapın. Not: `input_tokens` yalnızca son önbellek kesme noktasından sonrasını sayar, toplam girdi üç alanın toplamıdır ([Prompt caching](https://platform.claude.com/docs/en/build-with-claude/prompt-caching)). Mutabakat için Usage and Cost API kullanın: eski uç `GET /v1/organizations/cost_report` yaklaşık 5 dakikada güncellenir, yeni analytics ucu (beta, `anthropic-beta: analytics-usage-cost-2026-08-24`) 4 saate, bazen 24 saate kadar gecikir; ikisi de Admin anahtarı ister ve bireysel Console hesaplarında kullanılamaz, o yüzden önce organizasyon kurun; Admin anahtarını bot ortamından uzak tutun ([Usage and Cost API](https://platform.claude.com/docs/en/manage-claude/usage-cost-api.md), [Analytics API](https://platform.claude.com/docs/en/manage-claude/usage-cost-analytics-api)).

## Sonuç

Bu analizin ana çıkarımı, maliyetin model seçimi ve düşünme ayarı tarafından belirlendiği, çağrı sıklığının ise ikincil olduğudur: aynı 15 dakikalık döngü Haiku 5.5'te ~2,6 USD, Sonnet 5.5'te ~51 USD, Opus 5.5'te ~103 USD tutuyor. Önbellek bu senaryoda mütevazı (%13-14), çünkü statik kısım küçük; asıl kazanç ucuz modelden ve gereksiz çağrıyı atlamaktan geliyor. Batch API yalnızca ders işi için anlamlı, ve bu iş zaten kuruşlar tutuyor.

Asıl risk fiyat değil, iki varsayımın doğruluğu: Haiku 5.5'in 0,10/0,50 USD fiyatı gerçek mi ve Haiku'nun veto kalitesi yeterli mi? İlkini resmî sayfada, ikincisini kendi geçmiş verinizle ölçün. Ayrıca Sonnet/Opus'a geçerseniz düşünme tokenlerini `usage.output_tokens` üzerinden birinci hafta izleyin; bu alan bütçeyi iki-üç kat saptırabilir. Limitleri (workspace 20-30 USD, org 50 USD, auto-reload kapalı, uygulama içi günlük tavan) botu canlıya almadan önce kurun.

## Kaynaklar

Resmî sayfalar (notlarda çekildiği tarih 2026-11-15):

- Fiyatlandırma: https://platform.claude.com/docs/en/about-claude/pricing (ayrıca https://claude.com/pricing)
- Önbellek: https://platform.claude.com/en/docs/build-with-claude/prompt-caching
- Batch: https://platform.claude.com/docs/en/build-with-claude/batch-processing
- Maliyet/zekâ optimizasyonu: https://platform.claude.com/docs/en/about-claude/models/optimizing-for-cost-and-intelligence
- Yapılandırılmış çıktı: https://platform.claude.com/docs/en/build-with-claude/structured-outputs
- Strict tool use: https://platform.claude.com/docs/en/agents-and-tools/tool-use/strict-tool-use
- Araç tanımı / forced tool use: https://platform.claude.com/docs/en/agents-and-tools/tool-use/define-tools
- Sonnet 5.5 geçiş rehberi: https://platform.claude.com/docs/en/models/sonnet-5-5/migration-guide
- Hız limitleri, katmanlar, harcama limiti hataları: https://platform.claude.com/docs/en/api/rate-limits
- API hataları: https://platform.claude.com/docs/en/api/errors
- Streaming: https://platform.claude.com/docs/en/build-with-claude/streaming
- Python SDK: https://platform.claude.com/docs/en/cli-sdks-libraries/sdks/python ; TypeScript SDK: https://platform.claude.com/docs/en/cli-sdks-libraries/sdks/typescript
- Token sayımı: https://platform.claude.com/docs/en/build-with-claude/token-counting
- Workspaces: https://platform.claude.com/docs/en/manage-claude/workspaces
- Set Spend Limit API: https://platform.claude.com/docs/en/api/beta/organization/spend_limits/set
- Rate Limits API: https://platform.claude.com/docs/en/manage-claude/rate-limits-api
- Usage and Cost API: https://platform.claude.com/docs/en/manage-claude/usage-cost-api.md ; Analytics: https://platform.claude.com/docs/en/manage-claude/usage-cost-analytics-api
- Destek: harcama limiti ve workspace https://support.claude.com/en/articles/9796807-creating-and-managing-spend-limits-on-the-claude-developer-platform ; ödeme/kredi https://support.claude.com/en/articles/8977456-how-do-i-pay-for-my-claude-api-usage ; daha yüksek limit https://support.claude.com/en/articles/10366389-how-can-i-get-higher-rate-limits-on-the-claude-api ; limit yaklaşımı https://support.claude.com/en/articles/8243635-our-approach-to-rate-limits-for-the-claude-api
- Console sayfaları: https://platform.claude.com/settings/spend-limits , https://platform.claude.com/usage/limits , https://platform.claude.com/settings/billing , https://platform.claude.com/settings/workspaces , https://platform.claude.com/settings/keys

Doğrulanmamış veya notlarda boşluk olarak işaretlenenler: model ID'lerinin genel bakış sayfasında teyidi; Haiku 5.5'in 0,10/0,50 USD fiyatı (özetlenmiş çekimden, sayfada teyit edin); düşünme faturalamasının ayrı sayfada teyidi (extended-thinking sayfası çekilemedi); Evaluation katmanı limitleri; önbellek TTL'inin yapılandırılmış-çıktı notunda yeniden doğrulanmaması (ancak önbellek ve fiyat sayfaları 5 dk/1 saat TTL'ini doğruluyor); Haiku/Opus 5.5'te örnekleme parametresi davranışı; ön ödemeli hesaplarda e-posta uyarıları. Hesaplama kodu: /home/claude/scripts/calc.py.
