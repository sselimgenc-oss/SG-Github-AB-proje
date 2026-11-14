# Tur 4: Cevher avı özeti

Tarih: 14 Kasım 2026. Üç paralel tarama (popüler çerçeveler, 20-1500 yıldızlı gizli cevherler, doğrulanabilir performans kanıtı) + Tur 3 bulguları. Yalnız statik okuma ve web araması; hiçbir şey çalıştırılmadı. Ayrıntılar: `research_notes/tur4-cevher-avi/`. Yatırım tavsiyesi değildir.

## Aranan bot

Teknik analizle kendi işlem bulan (scalp/gün içi/swing), işlemi kendi açıp kapatan, kendi işlemlerinden öğrenip gelişen bot.

## Ana sonuç

Üç özelliği birden taşıyan, olgun ve kanıtlı bir repo yok. Her aday bu üçünden ikisinde güçlü:

| Aday | Kendi bulur + açar/kapatır | Kendinden öğrenir | Kanıt / olgunluk | Borsa | Not |
|---|---|---|---|---|---|
| **freqtrade + FreqAI** | Evet (ama giriş eşiklerini strateji dosyası belirler) | Kısmen: ML modelini canlıda sürekli yeniden eğitir (piyasadan öğrenir, kendi kâr/zararından değil) | Çok olgun (57k yıldız, test, topluluk); yayınlanmış sonuç yok | Binance dahil çok borsa, dry-run | Pratikte en sağlam başlangıç |
| **astra-quant-agent** | Evet (LLM karar verir) | **Evet**: kapanan işlemlerden ders çıkarıp canlı karara ekler (kodda doğrulandı) | Orta olgunluk, kanıt yok; güvenlik açıkları var | Yalnız OKX (demo) | Tarif edilen bota en yakın |
| **Passivbot** | Evet (grid/martingale benzeri; tahmin yapmaz, teknik analiz botu değil) | Hayır (iyileştirici çevrimdışı, kullanıcı çalıştırır) | **Tek gerçek-para kaydı**: Hyperliquid kasası ~1,2 yıl, ~%28 net (küçük TVL, doğrulama zayıf); aktif proje | Binance, Bybit, OKX, Hyperliquid… | `broker_codes.hjson` (borsa referans kodları) var |
| **TEMPEST** | Evet | Evet (ders terfi kapılı) | En iyi tasarım, 2 yıldız, lisans yok | Binance (kâğıt) | Lisans sorunu |
| **chase-mew/ai-hedge-fund** | Evet (varsayılan onaylı) | Evet (tahmin isabeti karara geri besleniyor) | En dürüst repo, ileri yönlü açık günlük; 97 yıldız | Hyperliquid | Gizli cevher |
| AmpyFin | Evet | Evet (strateji sıralaması → ağırlık) | 428 yıldız, bayat (Ekim 2025) | Alpaca (ABD hisse) | Hisse için tek adaylardan |
| TorchTrade | Evet (RL) | Modeli kullanıcı eğitir | 106 test, CI | Binance/Bybit/OKX | Programcı gerektirir |
| NostalgiaForInfinity | Evet | Hayır | Olgun, sadece backtest iddiası | freqtrade üstünden | Taban çizgisi olarak iyi |

## Kanıt durumu

Açık kaynak hiçbir bot için çok aylı, maliyet sonrası, bağımsız doğrulanmış kazanç kaydı bulunamadı. En iyisi Passivbot'un herkese açık Hyperliquid kasası (güvenilirlik 3/5). Bir Reddit testinde 42 freqtrade stratejisinin 33'ü kaybetti; Alpha Arena'da 6 modelin 4'ü büyük zarar etti.

## Denemek için öneri

1. **Binance hesabıyla:** freqtrade + FreqAI'yi dry-run (sahte para) modunda; karşılaştırma için yanında NostalgiaForInfinity (öğrenmeyen taban çizgisi).
2. **"Kendinden öğrenen" fikrini görmek için:** astra'yı OKX demo hesabıyla (ücretsiz OKX hesabı gerekir).
3. **Sadece izlemek için:** Passivbot'un herkese açık kasasını birkaç hafta takip etmek (kurulum yok).
