# Tur 5: Derin tarama özeti

Tarih: 15 Kasım 2026. Üç paralel tarama: (1) popüler projelerin fork'ları + Haziran 2026 sonrası açılan repolar, (2) freqtrade topluluk stratejileri + Superalgos/nautilus/vnpy + bandit/çevrimiçi öğrenme, (3) Rusça/Korece/Japonca/Vietnamca/Türkçe/İspanyolca-Portekizce aramalar + akademik açık kodlar. Yalnız statik okuma; hiçbir şey çalıştırılmadı. Ayrıntılar: `research_notes/tur5-derin-tarama/`. Yatırım tavsiyesi değildir.

## Ana sonuç

Üç özelliği (teknik analizle kendi bulur, kendi açar/kapatır, kendi işlemlerinden öğrenir) birlikte taşıyan, olgun ve kanıtlı bir bot yine bulunamadı. Ama kendi işlemlerinden öğrenen birkaç küçük, yeni aday çıktı. Kendi verisini dürüstçe paylaşan her proje ya zarar ediyor ya da al-tut'u yenemiyor.

## Yeni adaylar (puan: Otonomi/Öğrenme/Kanıt/Olgunluk/Güvenlik/Kolaylık, 1-5)

| Aday | Puan | Borsa | Kendi işleminden öğrenme | Not |
|---|---|---|---|---|
| vedv0987-cloud/bvedtrade | 4/4/2/3/4/2 | Binance (testnet varsayılan, canlıya ikinci kilit) | Evet: sonuçlar giriş kapısını etkiliyor; Q-öğrenme, 20 işlemde bir model eğitimi | Yazarın kendi verisi: 634 işlem, %27 isabet, -0,55R (zararda). Lisans yok, kurulum ağır |
| shoaibghulam/binance-ai-bot | 4/3/1/2/3/3 | Binance vadeli (testnet varsayılan) | Evet: LightGBM kapısı kapanan işlemlerle yeniden eğitiliyor (yalnız veto) | 0 yıldız, tek commit; borsa tarafı stop yok; panel kimliksiz |
| CyberWei922/ai-trader-paper | 4/2-3/1/2/4/4 | Binance spot (dry-run) | Kısmen: zarardan sonra lot küçültme, 6 saatte bir yeniden eğitim | En kolay kurulum (Windows çift tık); Çince |
| AleksNovo/freqai-3ai-strategy | 4/4/1/3/3/1 | Bybit | Evet: her sinyalin sanal sonucundan öğreniyor | Varsayılan işlem açmıyor; tasarım referansı |
| FilipeThome/the-trader-bot | 4/3/2/4/5/3 | Binance spot testnet | Fren: kötü giden stratejiyi sinyal moduna indiriyor | Güvenli ve dürüst; kendi backtest'inde kaybediyor |
| SoloHard32/MEXC-AI-BOT | 4/3-4/1/2/2-3/3 | Yalnız MEXC | Evet: zarar eden sembolü karantinaya alıyor | |
| RafaelPF07/evotrader | 3/4/3/4/5/3 | Simülasyon (ABD ETF) | Evet, ayrılmış veride kapılı terfi | Al-tut'u yenemediğini yazıyor |
| parkseokjune/overfit-slayer | 3/2/2/2/4/3 | Binance demo | Aylık parametre yeniden uydurma | Kendi istatistiğiyle "şanstan ayırt edilemez" diyor |

**astra ile ilgili yeni bilgi:** suyunjing-su/r20-quantum-trader, astra'nın daha eski bir sürümünün (v8.4.0) aynası ve içinde Binance USDT-M emir bağdaştırıcısı var (`astra_backend/exchanges/binance.py`, `binance_orders.py`); asıl astra (v8.6.1) deposunda bu dosyalar yok. Yani astra'nın Binance desteği geçmişte vardı veya aynada eklendi; doğrulanmadı. Aynanın lisansı (MIT) asıl projeninkiyle (AGPL + Commons Clause) çelişiyor; kaynak olarak asıl depo esas alınmalı.

## Uzak durulacaklar

- Nikhilperr/binance-futures-trading-bot: öğrenme gerçek ama 20x kaldıraç ve bakiyenin %95'i.
- apex-crypto-bot: günlükleri üçüncü taraf siteye gönderiyor.
- fsinbad/nofx: son commit "kötü amaçlı workflow silindi" diyor; fork'lara körü körüne güvenmeyin.
- "21 günde %91 kazanma" gibi kanıtsız iddialı repolar.

## Kapsam sınırları

GitHub fork ve karşılaştırma API'leri 403 verdi; fork sapması commit geçmişinden tahmin edildi. Rusça/Korece/Japonca/Vietnamca aramalarda gerçek aday çıkmadı; Habr/Velog/Qiita/Zenn sayfaları doğrudan açılmadı. Akademik repoların (CryptoTrade, FinMem, FinCon) hiçbirinde borsa emir yolu yok.

## Tur 3-5 sonrası genel tablo

- **Kendi işleminden öğrenip karar veren en olgun aday:** astra-quant-agent (LLM, OKX demo; Binance aynada var).
- **En sağlam altyapı:** freqtrade + FreqAI (piyasadan öğrenir, kendi işleminden değil).
- **Kâğıt üzerinde tarife en uygun küçük aday:** bvedtrade (Binance testnet, kendi işlemlerinden öğreniyor; ama kendi verisi zararda).
- **Gerçek parayla kaydı olan tek bot:** Passivbot (teknik analiz/öğrenen bot değil).
