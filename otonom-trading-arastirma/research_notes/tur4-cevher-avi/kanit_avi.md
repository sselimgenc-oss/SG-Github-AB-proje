# Kanıt Avı: Açık kaynak botların doğrulanabilir performans kanıtı (14 Kasım 2026)

Kısa sonuç: Açık kaynak bir botun, bağımsız biri tarafından doğrulanmış, birkaç aylık, komisyon sonrası kârını gösteren sağlam bir kayıt BULAMADIK. En iyi kanıtlar bile zayıf veya kısmi. Not: Bu tur sadece web aramasıyla yapıldı; bazı siteler (tradingstrategy.ai, bazı GitHub repoları) bu oturumdan açılamadı, rakamlar arama özetlerinden geliyor ve doğrudan teyit edilmedi.

## Tablo

| Bot / strateji | Repo | Kanıt kaynağı | Süre | İşlem sayısı | Maliyet sonrası mı | Bağımsız mı | Sonuç | Güvenilirlik (1-5) |
|---|---|---|---|---|---|---|---|---|
| Passivbot Canon vault | enarjord/passivbot | Hyperliquid zincir üstü vault, tradingstrategy.ai listesi | ~1,2 yıl | bilinmiyor | Büyük olasılıkla evet (gerçek hesap, zincir üstü) ama teyit edilmedi | Kısmen (vault verisi zincirde, ama vault'u işleten taraf bot yazarına yakın/üçüncü taraf, belirsiz) | 1 yıllık net getiri %28, maks. düşüş %-13,8; sadece ~33 bin $ TVL | 3 (en iyi aday, ama küçük ve tek vault) |
| Passivbot referans vault (resmi) | enarjord/passivbot | Hyperliquid, varsayılan ayarla canlı | belirsiz | bilinmiyor | zincir üstü | Hayır (proje kendisi) | Rakam doğrulanamadı; "canlı örnek" olarak sunuluyor | 2 |
| Passivbot kullanıcı anekdotu | enarjord/passivbot | Gainium incelemesi | 100 gün | bilinmiyor | belirsiz | Hayır (anonim kullanıcı) | Yıllık %6,3; aynı dönem BTC al-tut ~%16 yaptı, yani bot geride | 2 (ama dürüst, kötü sonucu gösteriyor) |
| Alpha Arena Sezon 1 (LLM botları) | Bot kodu kapalı (Nof1); sadece klonlar açık | Nof1 canlı yarışma, Hyperliquid, 6 model x 10.000 $ gerçek para | ~17 gün | Qwen3 için 43 işlem | Belirsiz (ücretler anılmıyor) | Evet (herkese açık, zincir üstü) | Qwen3 +%22,3, DeepSeek +%4,9; GPT-5 yaklaşık -%62, Gemini -%57; çoğu kaybetti | 3 (gerçek para, bağımsız, ama kısa ve kod açık değil) |
| Alpha Arena Sezon 1.5 / 2 | Kapalı | İkincil haber siteleri | belirsiz | - | - | Evet ama haber sitesi tutarsız | Grok 4.2 kazandı denmiş (tek kaynak); ABD hisse turunda dört model zarar etti; Sezon 2 sonucu bulunamadı | 1 |
| LiveTradeBench | ulab-uiuc/live-trade-bench | Akademik makale arXiv 2511.03628 | 50 gün canlı | bilinmiyor | belirsiz | Akademik, bağımsız | 21 LLM; ABD hisse + Polymarket (kripto yok). Ana bulgu: model "zekâ" sıralaması ile kâr arasında zayıf/negatif ilişki | 3 (kod açık, ama araştırma ölçütü, kâr vaadi değil) |
| Agent Market Arena (AMA) | Kod linki doğrulanamadı | arXiv 2510.11695 | ~2 ay | bilinmiyor | belirsiz | Yazarlar kendi sistemini ölçüyor | TSLA, BMRN, BTC, ETH; "al-tut'u sık geçti" deniyor, rakamlar teyit edilmedi | 2 |
| NostalgiaForInfinity (NFI) | iterativv/NostalgiaForInfinity | Backtest sonuçları, Patreon, freqst.com | backtest | küçük örnek | Hayır / belirsiz | Hayır | Bir backtestte %79 kâr ama çok yüksek düşüş; canlı kayıt yok | 1 |
| FreqAI / Freqtrade stratejileri | freqtrade/freqtrade | Resmi dokümanlar, topluluk | - | - | - | - | Hiçbir yerde doğrulanmış canlı kayıt yok. Bir Reddit testinde 42 halka açık stratejinin 33'ü 8 yıllık BTC verisinde kaybetti | 1 |
| Hummingbot yarışmaları | hummingbot/hummingbot | Hummingbot blogu | 1 ay | - | Hacim ağırlıklı skor | Organizatör kendisi | Hacim ve ödül odaklı; örn. birinci ~135 USDT kâr (35 bin USDT hacimde). Sürdürülebilir kâr kanıtı değil | 2 |
| OctoBot | Drakkar-Software/OctoBot | Bulunamadı | - | - | - | - | Herhangi bir performans kaydı çıkmadı | 1 |

## Notlar

- En güçlü kanıt türü: zincir üstü (Hyperliquid) vault geçmişi. Çünkü sahte gösterilemez. Passivbot Canon bunun tek somut örneği; %28 yıllık ve %-13,8 düşüş makul görünüyor ama 33 bin dolarlık küçük bir havuz, tek bir vault ve tek bir dönem. Bir yıl boyunca nasıl bir piyasa olduğuna (boğa/ayı) bağlı olabilir. Kontrol edilmesi gereken: vault'un kodu gerçekten bu repo mu, hangi ayar, geçmiş günlük getiri, kaldıraç.
- Alpha Arena en şeffaf gerçek-para deneyi, ama botların kodu açık değil ve süre 2,5 hafta. Asıl dersi: LLM ile "kendi başına" işlem yapan botların çoğu para kaybetti (aşırı işlem, ücret). Açık kaynak klonlar (Open-Nof1-AlphaArena, awesome-alpha-arena listesi) sadece benzer çerçeve; kendi canlı sonuçları yok.
- Akademik canlı benchmarklar (LiveTradeBench, AMA) kısa süreli ve "model karşılaştırma" amaçlı; kâr kanıtı olarak zayıf.
- Freqtrade ekosistemi: strat.ninja ve benzeri sıralamalar çoğunlukla backtest. FrequentHippo adlı topluluk projesi dry/canlı istatistik yayınladığını söylüyor (resmi sayfada listeli), ama doğrudan açıp inceleyemedik. Bu bir sonraki adım olabilir.
- Zorluk: gerçekten iyi çalışan bir strateji sahibi bunu çoğunlukla herkese açmaz. Açık olanlar için "hayatta kalma yanlılığı" (sadece kazananlar gösterilir) büyük risk.

## Kanıt yok ama çok iddia var

- NostalgiaForInfinity: popüler, ama sadece backtest ve Patreon pazarlaması; bağımsız canlı kayıt yok.
- Freqtrade genel ve FreqAI: "kendi kendine öğrenir" anlatısı çok, kayıtlı canlı kâr yok; bir geliştirici 40+ negatif backtest sonrası ML tasarımını bıraktığını yazmış.
- passivbots.com: gösterilen güçlü rakamlar kendi sayfasında "geçmiş sonuç" (backtest) olarak etiketli.
- alexbobes.com rehberi: "6 aylık getiri/kazanma oranı" iddiası, kaynak/hesap yok.
- web3.career profili: "6 ayda %100" iddiası, doğrulanamaz.
- Hyperliquid bot listeleri (chainstack, arx, coinlaunch): pazarlama; denetimler (CertiK, Salus) ticari platformlar için, açık kaynak için değil, ve kodun güvenliğini ölçer, kârı değil.
- Rastgele GitHub "autonomous AI trading bot" repoları (ör. sparkssolutions, caelum0x/hyperliqbot): README iddiaları, kanıt yok.
