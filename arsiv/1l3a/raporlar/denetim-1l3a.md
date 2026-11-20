# 1L3A genel denetim (2026-11-20)

Taban: `458cda6..92e6ca4` (son 48 saat, 58 Python dosyası). Denetim boyunca kod DEĞİŞTİRİLMEDİ; düzeltmeler ayrı iş.
Yöntem: araç taraması → modül başına inceleme (5 grup, her bulgu kırmızı testle) → temiz bağlamlı ikinci inceleyici her bulguyu çürütmeye çalıştı → mutasyon testi (para yolu) → güven sınaması.
Kırmızı testler: `raporlar/denetim_testleri/` (dosya adları `test_` ile başlamaz, toplu koşuya girmez; tek tek: `python -m pytest raporlar/denetim_testleri/<dosya> -q -p no:cacheprovider`).

## Özet

- **30 bulgu**, hepsi kırmızı testli; çürütücü **0** çürüttü: **21 doğrulandı**, **9 kısmen** (önemi düşürüldü / tasarım kararı).
- Bugün kâğıtta **açık ve işleme etkili** olanlar yalnız 3: **E1**, **B1**, **B5**.
- Canlı servis kurulu/aktif değil (DURUM.md; `CANLI_ONAY` olmadan başlamaz) → canlı bulguları bugün etkisiz, **canlıya geçişten önce kapatılmalı**.
- Güven sınaması: **4/5** (eşik 4/5 tuttu); kaçan hata `paper.py` canlı/kâğıt ayrımındaydı → `paper.py` grubunu Opus inceledi.
- Değişen satır test kapsamı **%89**; testler rastgele sırada da yeşil (7826).

## Doğrulanmış bulgular (önem sırası)

"Kâğıtta" sütunu: AÇIK = bugün işlemleri etkiliyor; UYKUDA = koşul gelince etkiler; ETKİSİZ = yalnız rapor/görüntü; CANLI = canlıya geçince.

| # | Önem | Yer | Bulgu | Kâğıtta |
|---|---|---|---|---|
| E2 | KRİTİK (canlıya geçişte) | motor_kopru.py:61-75, paper_motor.py:235-266 | Kâğıdın reddettiği giriş (ML/etiket/karantina/risk kırpma) canlı niyete aktarılmıyor: canlı önce girer, bir mum sonra kapatır. DURUM.md:12'deki "atlanan paper girişi canlıda da açılmaz" iddiası yanlış. | CANLI |
| D1 | KRİTİK (canlıya geçişte) | paper.py:818 | Çıkış karşı-olgusu (onaysız çıkış değişikliği) canlı yolda da bağlanıyor; "canlıda kendini değiştiren kod yok" kararıyla çelişir. Aynı soru ders/ML/etiket için: canlıda açık kalsın mı (karar). | CANLI |
| E1 | ORTA | ct_kadro.py:347-359 | CT konsensüs MAX_POZ=3 bekleyen dolumları saymıyor → 5 pozisyon açılabiliyor. | AÇIK |
| D2 | ORTA | paper_veri.py:53, paper.py:164/270 | `ZeroDivisionError`/`ArithmeticError` kod hatası sayılmıyor → strateji yerine tüm tur düşer, 5 tekrarda motor durur. | UYKUDA |
| A1 | ORTA | islem_mutabakat.py:106-122, 386-390 | Mutabakat kapanan işlemleri gizli hesaplar dahil sayıyor → ilk gizli kapanışta sahte uyuşmazlık ve açık yayına gizli hesabın coin/zaman izi. (Sunucuda 0 uyuşmazlık: gizli hesapların henüz kapanmış işlemi yok.) | UYKUDA |
| C1 | ORTA | ogrenme_adaptor.py:512,549,558 | Ders geri alma/fren/drift Telegram mesajında gizli hesap adı açık yazılıyor (kullanıcı şartı). Drift mesajı şimdiden tetiklenebilir. | UYKUDA |
| C2 | ORTA | ogrenme_adaptor.py:482-499 | Ders fren/geri alma penceresi dersin doğumundan önceki işlemleri de sayıyor → kötü ders maskelenebilir ya da iyi ders hemen geri alınabilir. | UYKUDA (ders yok) |
| E3 | ORTA-DÜŞÜK | canli_yurutucu.py:385-392, 626-637 | Belirsiz kapatmada dolmamış emir "kapandı" sayılıyor → stop iptal, bir tur korumasız pozisyon. | CANLI |
| B1 | DÜŞÜK-ORTA | alinsaydi_gevsetme.py:357-368 | Fren toplamı az önce geri alınan filtrenin R'sini de sayıyor → sağlam gevşetme gereksiz askıya (tutucu yön: kaçan fırsat). | AÇIK |
| B5 | DÜŞÜK-ORTA | haber_etiketi.py:72-76 | Haber tonu alt-dize eşleşmesi (bank⊃ban, issue⊃sue, enterprise⊃rise) → `haber_ters` girişi yanlış atlatabilir. | AÇIK |
| B4 | DÜŞÜK-ORTA | pano.py:1989-1996 | Alınsaydı durumu panoda ham dökülüyor; aktif gevşetmeler görünmüyor, "Henüz değişiklik yok" hiç çıkmıyor. | ETKİSİZ |
| C3 | DÜŞÜK-ORTA | ders.py:80-93 + adaptör | Girişi engelleyen aday ders hiç alive/retired olmuyor (n=0) → süresiz engelleyebilir. Spec boşluğu. | UYKUDA |
| D5 | DÜŞÜK-ORTA | bosluk_maruziyet.py:73,130 | Boşluk uyarısı zirveden mevcut düşüşü hesaba katmıyor (kill'e yakınken uyarı yok). Yalnız bildirim. | ETKİSİZ |
| A2 | DÜŞÜK | pano.py:202-210 | Gizli liste okunamazsa boş küme kalıcı önbelleğe giriyor → gizli adlar açık-başarısız. | UYKUDA |
| A3 | DÜŞÜK | gunluk_ozet.py:366-388 | Günün son saati günlük tarihçeye girmiyor (≤1 saat). | ETKİSİZ |
| A4 | DÜŞÜK | mutabakat_telegram.py:47 | Kasa kontrolü hiç yapılmadıysa "kasa tutuyor ✅" yazıyor. | ETKİSİZ |
| B6 | DÜŞÜK | haber_etiketi.py:121-138 | Kaynaklar düşünce eski önbellek kullanılıyor (24 saat penceresi sınırlıyor). | AÇIK, dar |
| C7 | DÜŞÜK | ogrenme_adaptor.py:368-388 | Eğitim hatası her turda yeniden deneniyor (log/CPU). | ETKİSİZ |
| D3 | DÜŞÜK | paper_motor.py:852,922 | Karantinada "gün sonu kapat" işareti kayboluyor (bugün kullanan strateji yok). | ETKİSİZ |
| D4 | DÜŞÜK | bosluk_maruziyet.py:73 | Uyarı `>`, kill `>=`: tam eşikte uyarı yok. | ETKİSİZ |
| E4 | DÜŞÜK | ct_kadro.py:281-293 | CT coin başı veri yaşı kullanılmıyor (ön kayıt boşluğu, karar). | AÇIK, dar |

## Kısmen doğrulananlar (önemi düşük / tasarım kararı)

- **B2** fren asgari örnek istemiyor (docstring'e uygun; karar). **B3** askıdaki filtre yeniden gevşeyebiliyor (kasıtlı; ikinci fren kilitliyor). **B7** = D1 ile aynı konu.
- **C4** tek küçük kazanç dersi emekli ediyor (alınmış `ders.py` spec'i, "değiştirmeyin"). **C5** gece adımı hatası günün drift/karnesini atlatır (olasılık düşük). **C6** öğrenme kayıt dosyasında tek bozuk satır geçmişi sildirebilir (yazım atomik; nadir).
- **D6** başlangıç yeniden deneme sayacı değişen hata mesajında sonsuz döngü. **D7** "genel kesinti" paydası atlanan serileri de sayıyor (hatalar loglanıyor). **E5** aday hesap dizin adı çakışması (bugün yok).

## Şüphe (testle doğrulanmadı)

- Canlı serviste `telegram_sessiz=True` → karantina CRIT/"düzeldi" bildirimi gitmiyor olabilir (gerçek para stratejisi fark edilmeden giriş bırakabilir).
- `exchangeInfo` canlıda yenilenmiyor; 418/429 yasak dosyası süreçlere özel; kill "bilinmeyen" pozisyonu da kapatıyor (teyit); emir POST'unda 429 belirsiz sayılıyor; marj tipi doğrulanmıyor.
- `kz_oran` kısmi çıkış sonrası paydası; `_kasa_dusus` seri yokken zirve toplamı; mutabakat çoklu dosya anlık görüntüsü; kaldıraç tavanı 5 vs 3 gösterimi; aynı sayıda farklı uyuşmazlık tekrar bildirilmez.
- Alınsaydı kanıtı brüt R, geri alma net R; çıkış karşı-olgusunda yeniden oynatma önyargısı; aynı işlem iki filtrede çift sayım; rejim `1d or 4h`.
- ML `MIN_EGITIM=10` aşırı uyum riski; drift birikimi çok hesapta; ders işlem kimliğinde hesap yok; askıdan dönüş histerezissiz.
- Test koşusu `raporlar/pano3/pano3_ozet_390_{acik,koyu}.png` dosyalarını her seferinde yeniden yazıyor (repo kirleniyor).

## Araç taraması (özet)

- ruff 80 (çoğu kullanılmayan import/değişken); mypy 393 (para yolunda 94; çoğu `Optional` tip uyarısı, `alinsaydi_gevsetme.py:160` hasattr korumalı); vulture 5 (`risk_senaryo_kos.py:93` ölü dal, araştırma aracı); bandit 19 (SHA1 özetleri güvenlik amaçlı değil; `paper_v2.py:985` pickle yalnız kendi önbellek dosyası).
- pytest-randomly (tohum 631186): 7826 geçti. diff-cover: değişen satır kapsamı %89. Düşük kapsamlı para yolu: `ct_paper.py` %45, `paper_durum.py` %71, `islem_mutabakat.py` %79, `paper.py` %82.

## Mutasyon testi (para yolu)

mutmut 2.5.1, 4 modül, yalnız ilgili test dosyalarıyla (hayatta kalan sayısı string/log mutantlarını da içerir):

| Modül | Toplam | Öldürülen | Hayatta | Öldürme oranı |
|---|---|---|---|---|
| alinsaydi_gevsetme | 466 | 333 | 133 | %71,5 |
| karantina | 62 | 29 | 33 | %46,8 |
| bosluk_maruziyet | 222 | 166 | 56 | %74,8 |
| etiket_kurallari | 125 | 83 | 42 | %66,4 |

Testle kilitlenmemiş anlamlı noktalar (düzeltme işinde test eklenecek):
- karantina.py ~60: gizli/görünür kaldırma koşulunun ters çevrilmesi yakalanmıyor (güven sınamasındaki hata da buradaydı; inceleyici buldu, test bulmazdı).
- alinsaydi_gevsetme.py ~373: ikinci frende kalıcı kilit eşiği (`>= 2`) testlenmemiş; ~32/340/401: 30 günlük pencere sınırları.
- bosluk_maruziyet.py ~69-70: ihlal eşiği `>`/`>=` ve `kasa > 0` sınırı (D4 ile aynı yer).
- etiket_kurallari.py ~52: `haber_ters` yön ve eşik sınırları testlenmemiş.
Sonuç: karantina testleri zayıf (%47); diğerleri orta. Düzeltmeler bu sınırlara sınır testleriyle gelmeli.

## Güven sınaması

Ayrı yerel kopyada para yoluna 5 bilinçli hata eklendi (hiç commitlenmedi/gönderilmedi; kopya ve dal silindi). Habersiz inceleyici 4'ünü kırmızı testle buldu (toplam/ortalama, fren eşik yönü, fonlama işareti, gizli kapsam); 5.'yi (`paper.py` canlı yol VE/VEYA) yalnız şüphe olarak gördü. Skor **4/5**. `paper.py` grubu bu yüzden Opus'la incelendi.

## Mükerrer kod (yalnız hangisi kalsın)

- `_oku_json/_yaz_json/_utc`: 4-5 dosyada kopya → `durum.py` atomik yazım yardımcısı + tek `_utc` (`kayit_etiketleri`) kalsın.
- `_json/_jsonl/_dec` (mutabakat, günlük özet, mutabakat Telegram) → `gunluk_ozet.py` sürümü kalsın.
- Gizli liste: `pano._gizli_adlar` kalsın (mutabakat ondan alsın).
- Açık net K/Z formülü: `paper_durum._acik_pnl` kalsın (`askida_net` ondan çağırsın).
- Alınsaydı mum getirme/simülasyon: `cikis_karsi_olgu.alinmayan` kalsın.
- Karantina kod hatası kontrolü: `paper._karar_guvenli` kalsın.
- CT/aday süreç-içi yama bloğu: `ct_paper.py`'de ortak kalsın.

## Kullanıcı kararı gerekenler

1. Canlıda ders/ML/etiket kuralları ve çıkış karşı-olgusu açık mı kalsın? (D1, B7)
2. Strateji içi `ValueError` tüm turu düşürsün mü, yoksa karantinaya mı alsın? (D2 şüphesi)
3. CT coin başı veri yaşı ön kayda eklensin mi? (E4)
4. Alınsaydı freni için asgari örnek sayısı olsun mu? (B2)
