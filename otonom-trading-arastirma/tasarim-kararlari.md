# Bot tasarım kararları (15 Kasım 2026, kullanıcı onaylı)

| # | Konu | Karar |
|---|---|---|
| 1 | Piyasa | **Faz 1:** kripto vadeli. **Faz 2:** ABD hisseleri ve emtia |
| 2 | İşlem süresi | Gün içi + swing; bot piyasaya göre seçer. Scalp başlangıçta yok |
| 3 | Analiz kaynakları | Teknik analiz + vadeli verisi (funding, açık pozisyon) + haberler |
| 4 | Kararı kim verir | Kurallar / makine öğrenmesi karar verir; LLM yalnızca veto eder ("bu işleme girme") |
| 5 | Öğrenme | Her gün gözden geçirme; bir ders/değişiklik ancak en az 20-30 işlemlik kanıtla uygulamaya alınır |
| 6 | Uygulama yetkisi | Küçük değişiklikleri sahte parada test edip kendisi uygular; büyük değişiklikleri kullanıcıya sorar |
| 7 | Risk | İşlem başı bakiyenin %2'si, günlük en fazla %5 zarar, kaldıraç 3x-5x |
| 8 | Kullanıcı rolü | Günlük rapor, istediği an durdurabilme, önemli kararlarda onay |
| 9 | Raporlama | Telegram bildirimi + günlük özet + web paneli |
| 10 | Sermaye (gerçek paraya geçilirse) | 1.000-2.000 USD |

## Notlar

- Kaldıraç riski artırmaz (risk işlem başı %2 ile sabit), yalnızca bağlanan teminatı ve likidasyon mesafesini belirler. Kural: zarar durdurma her zaman likidasyon fiyatından önce gelmeli; kod bunu her işlemde kontrol etmeli.
- LLM maliyeti tahmini ~2-4 USD/ay (Haiku 5.5 döngü + Sonnet 5.5 günlük ders, Batch).
- Test: freqtrade dry-run (Binance herkese açık veri, anahtar gerekmez), öğrenen bot + dondurulmuş ikiz + al-tut + rastgele giriş kolları yan yana (bkz. research_notes/diger-hesap/gorev5 ve gorev8).
