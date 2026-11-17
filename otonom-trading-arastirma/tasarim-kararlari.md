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
- **16 Kasım 2026 — Backtest sonrası (kullanıcı onayı, mentor önerisi):** (1) Sahte para v1b ile başlar: 15 dk giriş kapalı, R1 (yatay kurulum) kapalı, aynı mumda yeniden giriş yok; gölge etiketler kaydedilir. (2) İyileştirme: en fazla 6 önceden kayda geçirilmiş deneme (strateji-iyilestirme-plani.md), kendi backtester'ımız hazır olunca; kilitli dönem (2026-05→2026-10) yalnız son aday için bir kez açılır. (3) Canlı: 1000 USD ve tarih aynı; işlem başı hedef risk %0,5 ile başlar (risk kilidi sınırları içinde, `target_trade_risk=0.005`); kademeli artış için yazılı kural (mentor yazacak) ve bakiye −%20'de durup değerlendirme eşiği.
- **16 Kasım 2026 — Öncelik (kullanıcı):** Önce projenin ana yapısı tamamlanır (kendi motor, ders servisi, Telegram/pano, uçtan uca test, sunucu). Strateji takılıp çıkarılabilir bir parça olacak (motorda strateji arayüzü); v1b ilk takılan stratejidir. İleride 1l3a'daki stratejiler ve başkaları aynı arayüzle denenebilir. 6 denemelik iyileştirme planı iptal edilmedi ama ana yapı bitene kadar ertelendi.
- **16 Kasım 2026 — Kullanıcının 25 repoluk ML listesi (mentor incelemesi):** Plan değişmez (kağıt 30 Kasım). Listeden alınacaklar, sonraki işler olarak:
  - Aurum v2 (zero-was-here/tradingbot, MIT): `aurum/research/stats.py` (deflated Sharpe, PBO/CSCV, Holm, durağan bootstrap) ve `splits.py` (purged walk-forward/CPCV) doğrudan monte edilebilir (yalnız numpy/pandas/scipy). Önce `lesson_calibrate.py` için çapraz kontrol; splits ve `labels/triple_barrier.py` ML fazına. ~1–2 gün, kendi testlerimizle; scipy yeni bağımlılık ya da kullanılan fonksiyonlar taşınır. Matematik makalelere karşı doğrulanacak.
  - PowerTrader_AI (Apache-2.0): yalnız fikir — ders başına güvenilirlik puanı, kanıtı tutmayan ders zamanla zayıflar. Ders servisi v2.
  - universal-portfolios: yalnız fikir — ders kanıtı komisyon+kayma sonrası (net) ölçülmeli; ders-spec'e tek satır.
  - Diğerleri zaten puanlanmıştı ya da katkısı yok.
- **17 Kasım 2026 — Kullanıcının iki ek repo raporu (mentor incelemesi):** Tasarım değişmez. Ortak desenin (zamanlanmış yeniden eğitim → nicel terfi kapısı → gölge → sıcak yükleme) terfi kapısı, gölge, sıcak yükleme, sınırlı parametre ve geri alma kısımları bizde zaten var; zamanlanmış walk-forward yeniden eğitim ML fazında (Aurum `splits.py`). Sonraki işler (yalnız fikir, kod alınmaz):
  - Alınmayan sinyallerin sonucu: gece işi atlanan kararları sonraki mumlarda yeniden oynatıp varsayımsal R saklar (gevşetme kuralları + ML eğitim derlemi). Kağıt başladıktan sonra, ~1–2 gün. Ön koşul doğrulandı: defter her kararda (atlananlar dahil) `planned_entry`/`planned_stop`/`planned_target` yazıyor.
  - Taban kayma alarmı: son N işlem, botun kendi önceki kağıt penceresiyle kıyaslanır; yalnız Telegram uyarısı. Ders servisi v2, ~yarım gün.
  - Kağıt sonu raporuna beta ve alfa t-istatistiği (yalnız toplam getiriye bakılmaz). Canlı kararından önce, ~yarım gün.
  - ML fazında yeni modeli reddeden IC tarzı kapı.
- **17 Kasım 2026 — Makine öğrenmesi Faz 2'ye alındı (kullanıcı kararı; açık noktalarda mentor önerileri onaylandı: "Fable ne diyorsa onayım var"):** Eski madde 29, faz planında 19'dan sonraya taşındı (19a–19d; kağıt döneminde 25a–25c; etkinleştirme 28a). "İlk sürüm sapmaları" madde 3 ("FreqAI ilk sürümde yok") şu hale geldi: ML **altyapısı** ilk sürümde var, ML **filtresi** ilk sürümde kararları etkilemez. FreqAI kodu kullanılmaz (GPL; parça ilkesi), yalnız fikirleri. Ayrıntı: `ml-faz-tasarimi.md` v2.
  - **Takvim korunur:** kağıt 30 Kasım, canlı aralık sonu–ocak başı. Ana yapı önce gelir; 30 Kasım'dan önceki ML işleri 27 Kasım akşamı kesilir, bitmeyen kağıt dönemine kayar. ML kağıdı ya da canlıyı bekletmez; 4 Aralık esnekliği ML için kullanılmaz.
  - **30 Kasım'dan önce:** zorunlu — iki sözleşme değişikliği, `price_action_v1_ml` sarmalayıcısı, `ml_mode` (off/shadow/active, varsayılan off), uçtan uca testte `off` + `shadow` yolu. Hedef — backtester ile geçmiş eğitim derlemi (v1b, 2024-11 → 2026-04, alınan ve atlanan her aday; backtester çapraz doğrulamasına bağlı) ve sunucu dışı eğitim hattı.
  - **Kağıt sırasında:** alınmayan sinyal gece işi (1. hafta); ML-1 araştırması (en fazla 8 ön kayıtlı tarif, sunucu dışı); kapıyı geçen modelle gölge (en erken 2. hafta). Kağıt `off` ile, canlı filtre etkin olmadan başlar.
  - **Etkinleştirme:** ≥ 6 hafta gölge + ≥ 150 puanlı aday (≥ 50 alınmış) + ileri dönemde net R farkı > 0 ve IC > 0 + kullanıcının Telegram onayı + canlının ilk 2 haftası geçmiş. En erken ocak ortası.
  - **Çözülen açık noktalar:** (1) motor §13 bağlamına salt okunur model alanı ve defterde `ml_filter` atlama nedeni + puan alanı onaylı; (2) lightgbm sabit sürüm + hash, yalnız eğitim tarafında, motor yüklemez; (3) ML-1, 6 denemelik strateji planıyla paralel ve ayrı deneme defteriyle; kilitli dönem ML'ye kapalı; strateji sürümü değişirse model yeniden eğitilir; (4) etkin modda model süresi (21 gün) dolunca yeni giriş yok, filtresize dönüş yalnız kullanıcı kararıyla; (5) kapı eşikleri (+0,10 R, DSR ≥ 0,95, PBO ≤ 0,25 ve diğerleri) aynen donduruldu, gevşetilmez.
  - **Bilinen sınır:** geçmiş derlem ~16 ay (kilitli dönem hariç), 4 test dilimi; geçmiş kanıt incedir, asıl sınav gölgedeki ileri dönemdir. Walk-forward penceresi buna göre "≥ 8 ay eğitim, 2 ay test" olarak düzeltildi. Hiçbir tarif kapıyı geçemezse ML durur ve bu sonuç kayda geçer; takvim etkilenmez.
- **17 Kasım 2026 — Çapraz doğrulama kapısı (mentor kararı, uyum adımları 1–4 sonrası):** Kapı bugün kapalı kalır; sınırsız uyum kovalamacası durur. Sinyal katmanı %100 eşleşiyor; kalan fark bakiye zincirinden. 20 Kasım'a kadar tek bir sınırlı kanıt turu, sonra §7.2 B/C/D'nin harfi yerine **"açıklanmış eşdeğerlik"** ile onay. Koşullar: (a) zincirsiz girişler tam referans cüzdanla 1h'de ≥ %99, 15m'de ≥ %97, kalan her satırın nedeni listelenir; (b) anahtarı eşleşen işlemlerde çıkış nedeni/zamanı 1h'de ≥ %97, fiyat 1 tik içinde; (c) freqtrade'in kendi işlem büyüklüğünü kısma kuralı ≥ 20 satırda tek kural olarak tanımlanır (uygulanmaz); (d) ücret oranı (ücret ÷ nominal) eşleşir, f2_s5 fonlaması eşleşen işlemlerde ±%5 içinde. Tutarsa freqtrade silme yolu uçtan uca test + mentor onayı sonrası açılır (hedef 26–27 Kasım); tutmazsa §4.3 yedeği: kağıt yine bizim motorla başlar, silme bekler.
  - Uyum modunda stop güncellemesini bir mum geciktirme bayrağı onaylandı (yalnız `legacy_compat`; yarım gün; bundan sonra yeni uyum kuralı yok).
  - Asıl (native) modda aynı adımda çıkış-giriş yuvası serbest bırakılmaz: çıkış dolana kadar yuva ve risk tutulur (canlıyla tutarlı, güvenli taraf). Kağıdın 4. haftasında veriyle yeniden bakılır.
  - Giriş anında başlayan fonlamayı ödememe kuralı kalır (gerçekçi; net etkisi +0,04); bilinen fark olarak belgelenir.
  - Kullanıcı kararı gerekmez: silme geri alınabilir (git + dondurulmuş referans sonuçları), kağıt başlangıcı silmeye bağlı değil.
- **17 Kasım 2026 — Kilitli döneme mekanik test teması (olay kaydı; mentor kararı):** Üç motor testi gerçek veride kilitli dönemin içinde çalışmış: `test_engine_ml_filter.py` (2026-10-01→10-11, BTC/ETH/SOL, 19a'dan beri birkaç kez), `test_engine_05_impl_smoke.py` (2026-10 tam ay BTC/ETH ve 2026-10-01'den 3 saatlik kağıt tekrarı), `test_engine_01_impl_smoke.py` (2026-10-31 fonlama dosyası okuma). Testler yalnız mekanik doğruluyor; kâr/zarar, R ya da yön bakılmadı ve yazdırılmadı. Sızan bilgi ihmal edilebilir ("Ekim'de BTC/ETH'de ≥ 5 işlem", "1–11 Ekim'de ≥ 4 aday"). **Karar:** kilitli dönem bozulmuş sayılmaz, 2026-05-01→2026-11-01 aynen kalır. Testlerin eski geçici dizinleri açılmadan silindi; kilitli dönem raporuna bu temas tek satırla yazılacak. Bu çalışmalardan işlem başı/kâr çıktısına bakıldığı ortaya çıkarsa Ekim yanmış sayılır. Düzeltme: testler kilitli dönem öncesine taşınır; motorun `run_range` backtest yoluna anahtarsız kilitli dönem kilidi eklenir (şimdiye kadar yalnız CLI yolundaydı); testlerde gerçek veriyle kilitli tarih kullanımını yakalayan statik koruma testi eklenir. Kullanıcı kararı gerekmez.
