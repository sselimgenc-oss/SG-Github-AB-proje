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

## İlk sürüm (MVP) için onaylanan sapmalar (15 Kasım 2026)

Danışman denetimi (parca-plani-denetim.md) sonrası kullanıcı onayıyla:

1. **Haberler ilk sürümde yok** (Karar 3 ertelendi): istem enjeksiyonu riski; sonraki sürüme.
2. **İlk 2 hafta otomatik değişiklik yok** (Karar 6 kademeli): bot yalnızca ders önerilerini deftere kaydeder; otomatik uygulama 3. haftadan sonra, test-terfi kapısıyla.
3. **FreqAI ilk sürümde yok** (Karar 4): fırsatları kurallar bulur, Claude veto eder; ML sonraki sürüme.

Ek notlar: Claude kredisi/harcama limiti dolarsa bot yeni işlem açmaz (açık pozisyonlar SL/TP ile yönetilmeye devam eder). Sahte para ile gerçek para arasında isteğe bağlı ara adım: Bybit demo (freqtrade destekliyor).

## 15–16 Kasım kararları (güncel; eski maddelerle çelişirse bunlar geçerli)

- **Strateji:** price action; trend piyasada trend takibi, yatay piyasada ortalamaya dönüş. Kurallar kullanıcının price action PDF'lerinden ölçülebilir tanımlara çevrilecek (PDF son tarihi 18 Kasım; gelmezse basit kurallarla başlanır).
- **Zaman dilimleri:** 15 dk, 1 saat, 4 saat, 1 gün (1 gün sahte para döneminin 1. haftasında eklenir).
- **Coinler:** stabil coinler hariç piyasa değerine göre ilk 10; başta sabit liste, ayda bir güncelleme sonradan.
- **Yön:** long ve short.
- **Risk:** işlem başı gerçekleşen kayıp en fazla %2 (hedef ~%1,4 + komisyon/kayma payı); günlük en fazla %5 zarar; toplam açık risk en fazla %6; aynı yönde en fazla %4; kaldıraç 3–5x; izole teminat; likidasyon zarar durdurmadan uzak olmalı. Eşzamanlı işlem sayısına ayrıca sınır yok.
- **Borsa:** Binance global (binance.com), canlıda ayrı alt hesap. Sunucu DigitalOcean Frankfurt.
- **İkiz bot:** arka planda çalışır, kullanıcı raporlarında görünmez. Al-tut karşılaştırması yok.
- **Öğrenme:** ilk günden açık (eski "ilk 2 hafta otomatik değişiklik yok" kararının yerine geçer). Değişiklik için en az 20–30 işlem kanıtı; küçük değişikliği kendisi uygular, büyüğü Telegram'dan sorar; değişiklik günlüğü ve geri alma düğmesi.
- **Claude API bütçesi:** ayrı workspace; aylık sınır 10 $; günlük sınır veto 0,25 $, ders 0,10 $ (ayrı ayrı); veto ve ders için iki ayrı anahtar; günlük sınırın %70'inde uyarı, %100'ünde durdu mesajı; aylık 5 $ geçince tek uyarı; 10 $ kredi, otomatik yükleme kapalı, bakiye 3 $ altında uyarı. Veto sınırı dolarsa yeni işlem açılmaz; ders sınırı dolarsa o günkü ders atlanır.
- **Raporlama:** Telegram günlük rapor 21:00 (TR saati) + anlık uyarılar + acil durdurma komutu.
- **Sağlık:** iç sağlık denetçisi + dışarıdan 5 dakikalık nabız kontrolü; günlük veritabanı yedeği; yeniden başlamada kendiliğinden toparlanma.
- **Takvim:** 4 hafta sahte para (30 Kasım – 27 Aralık), aralık sonu–ocak başı canlı. Yalnızca teknik hata geçişi geciktirir; ancak sistem doğru çalışmıyorsa acele edilmez. Canlıdan önce gerçek hesapta en küçük tutarla 1 long + 1 short teknik duman testi.
- **Canlı sermaye:** 1000 $. Hedef: aylık %4 (uzun vadeli hedef, kanıt ölçütü değil).
- **Ayrıntılı faz planı:** faz-plani.md.
- **Sonraki fazlar:** FreqAI, haber verisi, ABD hisse + emtia, üç projeyi (copytrade/Hyperliquid, 1l3a/Binance, bu bot) tek ekrandan yönetme — zorsa yapılmaz.
- **16 Kasım 2026 — Öğrenme gölge dönemi (kullanıcı kararı):** Öğrenme sahte para döneminin 1. gününden açıktır (istatistik, geri alma izleyicisi ve öneriler her gün çalışır), ancak ilk 4–6 hafta (yapılandırma `shadow_weeks`, varsayılan 4, izinli 4–6) **hiçbir değişiklik otomatik uygulanmaz**: her öneri `needs_user` durumuna alınır ve onay için kullanıcıya gönderilir (Telegram bildirim arayüzü; kullanıcı `apply_proposal(actor="user")` ile onaylar). Gölge dönem bitince otomatik uygulama kuralları geçerlidir (eşikler `ders-spec.md` Bölüm 7.3 kalibrasyonunu geçmişse). Ayrıntı: `trader/docs/ders-spec.md` Revizyon 2.

- **16 Kasım 2026 — Parça ilkesi (kullanıcı):** Başka repolardan seçilen parçalar ya doğrudan bizim koda monte edilip bizim kodumuz olarak çalıştırılır ya da yalnızca fikri alınıp kendi kodumuz yazılır. Bir dış çatıya (freqtrade gibi) bağımlı olunmaz. Kendi motorumuz yazılacak; freqtrade çalışma ortamından ve backtest'ten tamamen çıkarılacak. Genel amaçlı kütüphaneler (pandas, numpy, requests, websockets, sqlite3) kabul; büyük trading çatıları/SDK'ları (ccxt, python-binance vb.) kullanılmaz.
- **16 Kasım 2026 — Takvim (kullanıcı):** Hedef canlı aralık sonu–ocak başı. Sahte para başlangıcı kendi motorumuz yüzünden kayarsa (en geç 4 Aralık) 4 haftalık sahte para süresi korunur; canlı birkaç gün kayar (en geç 2–5 Ocak). Canlıyı yalnız teknik sorun geciktirir.
