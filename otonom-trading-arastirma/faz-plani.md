# Faz planı (taslak v2, 15 Kasım 2026 — mentor incelemesi işlendi)

Hedef: aralık sonu–ocak başı canlı (1000 $, Binance global alt hesap). Teknik sorun çıkarsa takvim kayar; kâr/zarar sonucu geçişi engellemez.

## Faz 0 — Hazırlık ve en büyük belirsizlik (16–17 Kasım)
1. Kararları `tasarim-kararlari.md`ye yaz; `mimari-taslak.md`deki "ilk 2 hafta otomatik değişiklik yok" ifadesini "öğrenme ilk günden açık" olarak düzelt.
2. Proje iskeleti: klasör yapısı, Docker Compose, freqtrade 2026.10 sabit; tek komutla çalışan otomatik testler.
3. **DigitalOcean Frankfurt sunucusu + Binance erişim testi + vadeli dry-run uçtan uca** (451 engeli her şeyi durdurabilir, en başa alındı). Kullanıcıdan DigitalOcean erişimi bu adımda gerekir.

## Faz 1 — Altyapı ve risk (17–22 Kasım)
4. freqtrade iki kopya: öğrenen bot (L) ve ikiz (T, ders almaz, raporda görünmez).
5. Binance vadeli, sahte para, izole teminat, long + short.
6. Coin listesi: stabil coinler hariç ilk 10 (sabit liste; aylık otomatik güncelleme sonra).
7. Zaman dilimleri: 15 dk, 1 saat, 4 saat (1 gün 30 Kasım sonrası eklenir); geçmiş veri.
8. Risk kilidi: işlem başı %2 (hedef ~%1,4 + komisyon/kayma payı; gerçekleşen en fazla %2), günlük en fazla %5 zarar, toplam açık risk %6, aynı yönde %4, kaldıraç 3–5x, likidasyon zarar durdurmadan uzak.
9. Risk kilidi testleri: sınır aşımı, eşzamanlı işlemler, kayma senaryoları; gerçekleşen kaybın %2'yi geçmediği ölçülür.
10. Piyasa durumu etiketi: trend / yatay / oynak.
11. Kayıt defteri (her işlem gerekçesi ve sonucuyla) ve funding / açık pozisyon verisi.
12. PDF'lerden price action kural listesi. **PDF'ler için son gün 18 Kasım**; gelmezse basit kurallarla başlanır, sonra eklenir.

## Faz 2 — Strateji, Claude ve izleme (23–29 Kasım)
13. Strateji: trendde trend takibi, yatayda ortalamaya dönüş; price action kuralları koda.
14. Geçmiş veriyle test: komisyon iki katıyla da; geleceği görme (lookahead) hatası analizi.
15. API bütçesi (veto ve dersten önce): ayrı workspace, aylık 10 $, veto 0,25 $/gün, ders 0,10 $/gün, iki ayrı anahtar, %70 uyarısı, aylık 5 $ uyarısı, kredi 10 $ (otomatik yükleme kapalı).
16. Veto servisi (Haiku, 30 dk): dosya yok / eski / "girme" → işlem yok. Veto testleri.
17. Ders servisi (Sonnet, günlük, toplu mod), en sade hali: ilk günden açık; ≥20–30 işlem kanıtı; küçük değişikliği uygular, büyüğü Telegram'dan sorar; sınırlı ayarlar; **değişiklik günlüğü ve geri alma düğmesi**.
18. Telegram: günlük rapor 21:00, anlık uyarılar; **acil durdurma komutu ("hepsini kapat")**.
19. Sağlık denetçisi: iç kontroller + dışarıdan 5 dakikalık nabız; **günlük veritabanı yedeği; sunucu yeniden başlayınca kendiliğinden toparlanma testi**.
20. Uçtan uca test: sinyal → veto → risk → emir → kayıt → ders.

## Faz 3 — Sahte para dönemi (30 Kasım – 27 Aralık)
21. L ve T sunucuda 4 hafta, öğrenme açık. Teknik düzeltmeler L ve T'ye birlikte uygulanır.
22. Haftalık kontrol: hatalar, risk ihlali, API harcaması (ilk hafta sonunda bütçe ayarı).
23. 1. hafta: 1 günlük zaman dilimi ve aylık coin güncellemesi eklenir.
24. 1. hafta (kullanıcı): mali müşavirle vergi görüşmesi.
25. 2. hafta (kullanıcı): Binance alt hesap, vadeli izni, API anahtarı (para çekme kapalı, sadece sunucu IP'si). Para son gün yatırılır.

## Faz 4 — Canlıya geçiş (28 Aralık – 4 Ocak)
26. Geçiş kontrol listesi: açık teknik hata yok; risk kilidi testleri geçiyor.
27. **Teknik duman testi (28–29 Aralık):** gerçek hesapta en küçük tutarla 1 long + 1 short; borsadaki zarar durdur emri, kaldıraç, izole teminat, en küçük emir tutarı doğrulanır. Kâr-zarar testi değildir.
28. Geçerse 1000 $ ile canlı; ilk hafta yakın izleme.

## Sonraki fazlar (tarih yok)
29. FreqAI (makine öğrenmesi modeli).
30. Haber verisi.
31. ABD hisse + emtia.
32. Üç projeyi tek ekrandan yönetme (copytrade, 1l3a, bu bot) — zorsa yapılmaz; standart durum çıktısı o zaman eklenir.
