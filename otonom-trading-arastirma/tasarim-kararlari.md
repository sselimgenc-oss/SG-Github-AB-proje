# Bot tasarım kararları (kullanıcı cevapları, 15 Kasım 2026)

| # | Konu | Kullanıcı cevabı | Not / açık nokta |
|---|---|---|---|
| 1 | Piyasa | Kripto + ABD hisseleri, vadeli | Öneri: önce kripto vadeli; ABD hisseleri sonraki aşama (Türkiye'den broker erişimi ayrı iş) |
| 2 | İşlem süresi | Bot piyasaya göre seçsin | Öneri: gün içi + swing; scalp LLM ile uygun değil (gecikme, maliyet, komisyon) |
| 3 | Analiz kaynakları | Teknik analiz + vadeli verisi (funding, OI) + haberler | |
| 4 | Kararı kim verir | "a" (kurallar/ML karar verir, LLM veto eder), emin değil | Öneri: a |
| 5 | Öğrenme sıklığı | Günlük ile her N işlem arası | Öneri: ikisi birlikte (günlük gözden geçirme; terfi için en az N işlem) |
| 6 | Uygulama yetkisi | Küçük değişiklikleri kendisi (sahte parada test ederek), büyükleri kullanıcıya sorar | |
| 7 | Risk | İşlem başı %2, günlük en fazla %5 zarar, kaldıraç "en az 3" | Kaldıraç "en fazla 3" mü kastedildi? Netleştirilecek |
| 8 | Kullanıcı rolü | Günlük rapor + durdurabilme + önemli kararlarda onay | |
| 9 | Raporlama | Telegram + günlük özet + web paneli | |
| 10 | Sermaye (gerçek paraya geçilirse) | 1.000-2.000 USD | LLM maliyeti (~2-4 $/ay) bu ölçekte uygun |
