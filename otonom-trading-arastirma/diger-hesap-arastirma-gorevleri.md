# Diğer Claude hesabı için araştırma görevleri

Her görevi ayrı bir sohbette (Research / derin araştırma açık) kullanın. Sonuçları markdown olarak kaydedip bu projeye getirin: `otonom-trading-arastirma/research_notes/diger-hesap/` klasörüne konacak.

Öncelik sırası: 1 → 2 → 3. Limit yetmezse yalnız 1 ve 2 yeterli.

---

## Görev 1: freqtrade'e LLM + öğrenme katmanı ekleyen projeler

```
Açık kaynak freqtrade (github.com/freqtrade/freqtrade) kripto trading botunun üstüne LLM (Claude, GPT, DeepSeek vb.) karar katmanı veya "kendi işlemlerinden öğrenme" katmanı ekleyen mevcut projeleri, eklentileri ve yöntemleri araştır. Tarih: Kasım 2026.

Amaç: freqtrade'i temel alıp şunları eklemek isteyen biri için hazır parça ve örnek bulmak:
(a) LLM'in piyasayı (teknik analiz + funding/açık pozisyon + haber) yorumlayıp işlem önermesi veya filtrelemesi,
(b) botun kapanan işlemlerinden ders çıkarıp (işlem günlüğü → istatistik/yansıtma → parametre veya kural güncellemesi) bunu canlı kararlara geri beslemesi, ama değişikliği önce kâğıt/dry-run üzerinde test edip sonra uygulaması,
(c) freqtrade'in kendi araçlarının (FreqAI, hyperopt, Producer/Consumer, REST API, webhook, strategy callbacks: custom_stake_amount, confirm_trade_entry, custom_exit, bot_loop_start) bu iş için nasıl kullanılabileceği.

Her bulgu için: GitHub linki, yıldız sayısı, son commit tarihi, lisans, ne yaptığı, LLM/öğrenme çıktısının canlı karara gerçekten girip girmediği (README iddiası mı, kodda mı görülüyor), güvenlik notları (API anahtarı yönetimi, dışarıya veri gönderme). Spam/kopya repoları ayıkla. freqtrade dokümantasyonundan ilgili sayfaların linklerini ver.

Çıktı: Türkçe, tablo + kısa açıklamalar + "freqtrade'e bu katmanları eklemenin en temiz yolu" önerisi (hangi callback/araç nereye).
```

---

## Görev 2: Türkiye'den Binance ve vadeli işlem erişimi (birincil kaynaklarla)

```
Türkiye'de yaşayan bir bireyin Kasım 2026 itibarıyla kripto trading botu çalıştırmasıyla ilgili güncel durumu araştır. Mümkün olduğunca birincil kaynak kullan (SPK, Resmî Gazete, mevzuat.gov.tr, GİB, MASAK, borsaların kendi resmi sayfaları) ve her iddianın kaynağını linkle ver; ikincil kaynaksa belirt.

Sorular:
1. Binance TR ile Binance global (binance.com) farkı: Türkiye'den binance.com hesabı açılabiliyor/kullanılabiliyor mu? Binance'in SPK lisans başvurusu/lisans durumu ne?
2. Türkiye'deki bir kullanıcı Binance USD-M vadeli işlemlere (futures) ve API ile otomatik işleme erişebiliyor mu? Türkiye'den kullanıcılara vadeli işlem kısıtı var mı?
3. Binance Futures Testnet (testnet.binancefuture.com) ve Binance Spot Testnet'e Türkiye'den erişim ve hesap açma: gerçek hesap/KYC gerekiyor mu?
4. OKX, Bybit, Hyperliquid için aynı sorular (kısa).
5. 7518 sayılı Kanun ve SPK kripto varlık hizmet sağlayıcı düzenlemelerine göre lisanslı Türk platformlarında kaldıraç/vadeli yasağı ve bireyin yabancı platform kullanmasının hukuki durumu.
6. Kripto kazançlarının vergilendirilmesinde Kasım 2026 itibarıyla yürürlükteki durum (Mart 2026'da geri çekilen teklifin yeniden gelip gelmediği dahil).

Çıktı: Türkçe, her soru için kısa cevap + kaynak linki + güven düzeyi (birincil/ikincil/belirsiz). Hukuki tavsiye olmadığını belirt.
```

---

## Görev 3: Passivbot'un herkese açık kasası ve doğrulanabilir bot sonuçları

```
Açık kaynak kripto botu Passivbot'un (github.com/enarjord/passivbot) gerçek parayla çalışan herkese açık Hyperliquid kasası ("Passivbot Canon" veya benzeri adlı vault) hakkında doğrulanabilir verileri bul: kasanın adresi/linki, başlangıç tarihi, toplam getiri, son 1 yıl getirisi, azami düşüş, TVL, kasa sahibinin Passivbot geliştiricisi olup olmadığı, hangi Passivbot sürümü/ayarıyla çalıştığı. Hyperliquid'in kendi kasa sayfasından veya zincir verisinden teyit etmeye çalış.

Ayrıca: FrequentHippo (freqtrade topluluk istatistik sitesi) ve strat.ninja / Strategy Ninja'da gerçek dry-run veya canlı sonucu yayınlanan freqtrade stratejileri; özellikle FreqAI (makine öğrenmesi) kullanan ve 3+ ay ileri yönlü sonucu olanlar. Her biri için süre, işlem sayısı, maliyet sonrası mı, bağımsız mı.

Çıktı: Türkçe, tablo (bot/strateji, kaynak linki, süre, getiri, düşüş, işlem sayısı, bağımsız mı, güvenilirlik 1-5) + kısa yorum. Yalnız backtest olan sonuçları ayrı işaretle.
```
