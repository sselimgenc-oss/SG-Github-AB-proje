# Tur 3: Öğrenen (L4) ajan araştırması — sonuç ve yol haritası

Tarih: 14 Kasım 2026. Yöntem: yalnızca statik kod okuma (grep/okuma), hiçbir depo çalıştırılmadı. Ayrıntılar: `research_notes/tur3-L4-ogrenen-ajanlar/`. Yatırım, hukuki veya vergi tavsiyesi değildir.

## Ne değişti?

Önceki iki tur doğrulanmış L4 (sonuçtan öğrenip canlı kararını değiştiren) bot bulamamıştı. Bu tur, öğrenme döngüsünü kodda uçtan uca izleyerek iki gerçek aday buldu:

| Depo | Seviye | Öğrenme döngüsü (kodda) | Risk/yürütme | Lisans | Durum |
|---|---|---|---|---|---|
| rgg81/crypto-trade-claude-code ("TEMPEST") | L4 | Reflector dersleri → DSR kapılı terfi → Bull/Bear/Trader istemine enjekte; playbook skor kartı (güven aralıklı) | LLM yalnız akıl yürütür; matematik, risk kapısı, devre kesici, yürütme deterministik Python (256 test). Binance USD-M, kâğıt varsayılan, canlı için "graduated" şartı | **Yok (tüm hakları saklı)** | 2 yıldız, tek commit, 330+ kâğıt çevrimi izi (kendi beyanı) |
| 0xethanq/astra-quant-agent | L4 (kapısız) | Kapanan işlemler → günde 4 LLM incelemesi → ders denetimi + kanıtla arşivleme → canlı isteme `{{trading_memory}}` (`scripts/brain/prompt.py:278,371`; zamanlayıcı `ai_factor_trader.py:239` üzerinden çağırıyor) | OKX demo varsayılan; 2-5x kaldıraç, %2 işlem riski, günlük zarar tavanı, kara kuğu sentineli | AGPL-3.0 + Commons Clause (satış yasak, kişisel kullanım/değişiklik serbest) | ~422 yıldız, aktif |

Diğer bulgular: AutoEvolve (LLM kendi strateji kodunu yazıp çalıştırıyor — güvenlik nedeniyle reddedildi), MATS (L4/L5 iddialı ama özel anahtar riski), Vibe-Trading (L3, en iyi "insan imzalı yetki" deseni), nofx/nof1.ai (yalnız istatistik geri beslemesi, kısmi). README iddiası ile kod arasında ciddi uçurumlar: atlas-gic (+%22 iddia, depodaki sonuç -%5,91), AutoHedge (emir aracı hiç bağlanmamış). Spam uyarısı: Eltano1985/tradememory-protocol (depo içi .zip dağıtıyor — indirmeyin).

## Danışman (Fable) görüşü ve takım lideri kararı

- **Temel: TEMPEST mimarisi** (LLM önerir, kod karar sınırlarını uygular, dersler kapıdan geçerek terfi eder). Claude'a özgü, kâğıt varsayılan, testli. Astra'dan kara kuğu sentineli ve kanıtla ders arşivleme; Vibe-Trading'den "ajanın değiştiremeyeceği insan imzalı limit dosyası" alınacak.
- **Engel: TEMPEST'in lisansı yok.** Kodu kopyalayıp yayımlamak hukuken mümkün değil. Seçenekler: (a) yazardan lisans istemek, (b) astra'yı (lisanslı) temel alıp TEMPEST'in fikirlerini kendi kodumuzla eklemek, (c) TEMPEST mimarisini sıfırdan kendi kodumuzla yazmak.
- Hisse tarafı: Alpaca'nın Türkiye erişimi doğrulanana kadar ertelendi.

## Maliyet (50 $/ay hedefi)

Tahmin (ölçüm değil): TEMPEST 4 saatte bir tam çevrim, hepsi Sonnet ile ~190 $/ay → bütçe dışı. **Karma model:** gözcü/analist/tartışma Haiku, hakem ve reflector Sonnet → ~20-35 $/ay. Kurulum yoksa tartışmayı atla; gerekirse 6-8 saatlik çevrim. İlk hafta gerçek token ölçülecek, Anthropic Console'da aylık sert tavan konacak.

## Sprint 1 (kâğıt/testnet, gerçek para yok)

1. **İzole kurulum:** konteyner, para çekme yetkisiz testnet anahtarları, testleri ve kâğıt döngüyü çalıştırma; ajan başı model yönlendirme ve token/maliyet günlüğü.
2. **LLM'in dokunamayacağı risk zarfı:** insan imzalı limit dosyası, kill switch, hata enjeksiyon testleriyle doğrulanmış devre kesici, her karar ve ders sürümü için yalnız-ekleme defter.
3. **Değerlendirme düzeni (ayar yapmadan önce):** gerçekçi ücret/kayma/funding; önceden yazılmış başarı ölçütleri.

## En büyük metodoloji tuzağı: rejim şansını öğrenme sanmak

4-8 haftada tek piyasa rejiminde ~30-100 işlem, test sırasında kendini değiştiren bir sistem: yükselen bakiye "öğrendi" ile "şanslıydı"yı ayırt edemez. Önlemler: test süresince kodu dondur; aynı veride paralel kollar (dersleri dondurulmuş ikiz, al-tut, aynı risk kapısından rastgele giriş); kârı ders sürümüne göre atfet; geç/kal kararını yalnız kâra değil süreç ölçütlerine bağla (sıfır risk ihlali, ders terfi isabeti, maliyet, çalışma süresi). Geçerse en fazla çok küçük tutarlı canlı deneme.
