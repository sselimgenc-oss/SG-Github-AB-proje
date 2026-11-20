# 1L3A — Durum ve Kararlar

_Son güncelleme: 2026-11-19 (takvim/şart kaldırma kararı)_

## ÜSTÜN KARAR — 2026-11-19 (kullanıcı kararı, orkestratör oturumu üzerinden; aşağıdaki eski kayıtlardan önce gelir)
1. Paper için bitiş/kabul tarihi YOK (2027-01-02 "8 hafta" ve 2027-02-06 "12 hafta" şartları kalktı). Canlı tarihi YOK ("Aralık sonu canlı kararı" kalktı). Paper, kullanıcı bildirene kadar sürer.
2. "Dönem bitti, devam mı dur mu" türü karar noktaları kaldırıldı. Proje zarar etse de devam eder; kullanıcı geliştirir.
3. İşlem sayısı / süre şartları kaldırıldı (paper kabulü ≥30 işlem, ≥8/12 hafta; haftalık taramada ≥12 hafta + ≥30 işlem; kapanış adaylarının 12 hafta ve "<20 işlem → 60 USD" kuralı).
4. Testnet ve gerçek paraya geçişin zamanı ve şekli yalnız kullanıcının kararı.
5. "2×60 USD duman testi" adımı TAMAMEN KALDIRILDI. Gerçek paraya geçişin adımları ve tutarı yalnız kullanıcı bildirdiğinde belirlenir. Kodda 60 USD'ye bağlı tavan/kısıt yok (`tahsis_usd` yalnız > 0 denetlenir; 60 değerleri yalnız örnek ayar dosyası ve belgelerde).
- ortak_ogrenme 1.2.0 adaptörü: ML filtre + ders paper girişlerini doğrudan atlatabilir (gölgesiz), limitleri aşamaz; veri birikene kadar filtre pasif; kapatma L3A_OGRENME_KAPALI=1 (`motor/canli/ogrenme_adaptor.py`, kanca `paper_motor.giris_suzgeci`).
- **Etiket kuralları (kullanıcı onaylı, 2026-11-19; ön kayıt, sabitler `motor/canli/etiket_kurallari.py` başında, değişmez):** kayıt etiketleri paper GİRİŞİNİ yalnız ATLATIR (boyut/limit/stop/hedef değişmez, yeni giriş açtırmaz; etiket null -> kural yok; hata -> giriş serbest). (1) `rejim_karsiti`: ML rejim (rejim_ml_1d, yoksa 4h) long'da trend_down / short'ta trend_up; (2) `takvim_olayi`: takvim_bayragi dolu (olaya ±2 sa); (3) `kalabalik`: long fonlama ≥ 0.0005 VE oi_degisim_24s ≥ 0.10, short fonlama ≤ −0.0005 VE oi_degisim_24s ≥ 0.10. Atlanan giriş `alinmayan_sinyaller.jsonl`'e neden `etiket:<kural>` ile yazılır; zincir: ML filtre + ders + etiket (biri reddederse atla), kanca `paper_motor.etiket_suzgeci`. Kapatma: `L3A_ETIKET_KURAL_KAPALI=1` (L3A_KAYIT_KAPALI=1 etiket üretmediği için kuralları da fiilen kapatır). Canlı yürütücü giriş niyetini yalnız paper'ın dolumda kabul edeceği girişlerden üretir (`motor_kopru.gorunum` → `PaperMotor.giris_on_izni`: işlem dışı sembol, karantina, max pozisyon, tükenmiş risk bütçesi, ML filtre + ders + etiket; süzgeç kararı niyet anında bir kez alınır ve paper dolumu aynı kararı kullanır, denetim E2 2026-11-20); bu yüzden atlanan paper girişi canlıda da açılmaz. Kalan fark: dolum fiyatına bağlı paper boyut redleri (min_qty/min_notional, kısmi bütçe/kaldıraç tavanı) niyet anında bilinmez; canlı kendi boyutlandırma/sert limitleriyle girer, paper girmezse sonraki turda kapatır. (4) `korku_acgozluluk` (ön kayıt, 2026-11-19 "kapalı özellik kalmayacak"): endeks >= 75 long, <= 25 short atlatır (`ACGOZLULUK_ESIK`, `KORKU_ESIK`); neden `etiket:korku_acgozluluk`. Ders freni + geri alma bağlı (`ogrenme_adaptor.fren_adimi`, gece): etkin (aday+aktif) derslerin toplamı <= -10 R ise askıya alınır ve ölçülür (etki > 0 -> döner, Telegram Düzeldi), tek ders <= -3 R ise emekli; etki engellenen sinyallerin simüle R ile (kontrafaktüel). Aday ders de girişi atlatır. Yeni kayıt alanları `oi_usd`, `oi_degisim_24s` (Binance openInterestHist 1sa, yalnız kripto, `motor/canli/oi_istemci.py`: ortak host yasağı/ağırlık eşiği, 5 sn zaman aşımı, önbellek ≥15 dk, hata -> null, damga+1 sa ≤ karar anı).
- **Haber etiketi + `haber_ters` kuralı (kullanıcı kararı 2026-11-19, paper'da hepsi açık; ön kayıt, sabitler `etiket_kurallari.py` başında, değişmez):** `motor/canli/haber_etiketi.py`: CoinDesk + Cointelegraph RSS (stdlib, anahtarsız, 15 dk önbellek, hata sonrası 15 dk bekleme), coin başına son 24 saat: `haber_tonu` ∈ [-1, 1] (eşleşen başlıkların ortalama işareti; sembol tam kelime ya da bilinen ad; İngilizce kaba sözlük) ve `haber_sayisi`; yalnız kripto, hisse/emtia, ağ hatası, bayat veri ya da geçmiş oynatma -> null (veri yok = engel yok). Kayıt etiketlerine (`kayit_etiketleri`) eklenir. 5. kural `haber_ters`: haber_sayisi >= 2 VE long'da ton < -0.2 / short'ta ton > +0.2 -> giriş atlanır (neden `etiket:haber_ters`; yalnız atlatır, boyut/limit/stop değişmez). Eşik 0.2 kullanıcı yönergesi: CT reposunda `copytrade/canli/haber.py` yalnız kayıt (haber_anlik; haber_ters kuralı ya da eşiği bulunamadı), mantık referans alındı, kod kopyalanmadı. Kapatma: L3A_HABER_KAPALI=1 (etiket) / L3A_ETIKET_KURAL_KAPALI=1 (kurallar).
- **Drift eylemi (kullanıcı kararı 2026-11-19, paper'da açık):** `ogrenme_adaptor._drift_bildir`: CUSUM uyarısı veren kurulumda (a) ML filtre HEMEN yeniden eğitilir (gece beklenmez; MIN_EGITIM altında yapılmaz, durum `yetersiz_veri`), (b) ders çarpanı 0,5 (1L3A'da dersler ikili: eşleşen sinyallerin yarısında ders girişi atlatmaz, deterministik her ikinci eşleşme; ML filtre aynen; uyarı bitince 1,0), (c) `ogrenme_durum.json` `drift` alanı (kurulum bazında durum, ders_carpani, yeniden_egitim, S, n; pano sonra okur, pano.py değişmedi) + tek Telegram INFO (Bildirimci, 6 saat kuralı).
- **Paper'da ayar yenilemesi onay beklemez (kullanıcı kararı 2026-11-19):** kayıtlı strateji ayarı `guncel_ayarlar.csv`'den farklıysa paper servisleri (paper, ct_paper, aday_paper) yeni ayarı otomatik kabul eder (`paper.Paper.ayar_oto_kabul`; olay `ayar_otomatik` + günlük + tek INFO "Strateji ayarı güncellendi: X (eski → yeni)"). Canlı yürütücüde (`tur_kancasi`/`strateji_filtre` verilen çağrı, borsa/calistir.py) onay şartı (`--ayar-guncelle`) AYNEN kalır; testle sabit. Evrenden çıkan sembolde açık pozisyon varsa eski koruma (açık hata) aynen sürer.
- **Seans bazlı kayma çarpanı (kullanıcı onaylı, 2026-11-19; ön kayıt `stratejiler/seans_maliyet.json`, ölçüm YOK = varsayım):** Binance TradFi perp'leri 7/24 işlem görür ama dayanak piyasa kapalıyken makas/kayma genişler. Paper motoru hisse/emtia dolumlarında kayma (kayma_bps ve stop_kayma_bps) bileşenini seans dilimine göre çarpar: hisse normal 1.0 / genişletilmiş (04:00-09:30 ve kapanış-+4 sa NY) 2.0 / kapalı (gece, hafta sonu, tatil) 3.0; emtia normal 1.0 / kapalı 2.0; kripto değişmez. Komisyon ve funding değişmez. Boyutlandırma (%1 risk) sembol sınıfının EN YÜKSEK çarpanıyla yapılır (stop hangi seansta çalışacağı bilinmez; sert limit aşılmasın). İşlem kaydına `seans_dilimi`, `kayma_carpani`, `cikis_seans_dilimi`, `cikis_kayma_carpani` (yalnız hisse/emtia). Backtest motoru (`motor/portfoy`, `motor/backtest`) DEĞİŞMEDİ (araştırma verisi seanslıdır; çarpan yok) ve backtest eşleşme aracı (`tetikleyen_hemen_kapat=False`) çarpanı 1.0 kullanır. Kod: `motor/canli/seans_maliyet.py`, `paper_takvim.seans_dilimi`, `paper_motor.PaperMotor._ky/_sk/_sk_taban`.
- Ortak günlük özet (2026-11-19): `motor/canli/gunluk_ozet.py` `ortak.gunluk_ozet.v1` JSON'u yazar (kasa = 10 sanal hesap, ct hariç; 6 görünür hesap adıyla, 4 gizli tek toplu satır; saatlik + 21:00 TSİ) ve Pazar 21:10 TSİ haftalık Telegram özetini aynı `topla()` verisiyle gönderir; JSON yalnız ayrı açık Worker'da (`pano_acik_worker.js`, `/gunluk_ozet_v1.json`) girişsiz yayınlanır; ana pano tamamen kilitli.
- KALICI KURAL (kullanıcı, 2026-11-19: "Sanki milyon eurolar yönetiyorum, her şeye risksiz temkinli."): kâğıt aşamada deneme süresi, gölge çalıştırma, yan yana bekleme, "birkaç gün gözleyelim", "önce şu kadar veri birikmeli" gibi ara adımlar ÖNERİLMEZ (lider ve Fable dahil); özellikler doğrudan devreye alınır, hata çıkarsa düzeltilir. Değişmeyenler: sert limitler (günlük %5, kaldıraç 3–5x, canlı tavan), gerçek paraya geçişin zamanı/şekli yalnız kullanıcıda, `kapanis_canli_onay` (gerçek para) listesi. Uygulanan küçültmeler: ML filtresi model kurma eşiği 30 → 10 işlem, yeniden eğitim 20 → 10 yeni işlem; "sürüm yan yana" iptal; haftalık taramada gölge izleme + çeyreklik karar kaldırıldı (yeni kart doğrudan paper'a girer, ayrı iş).
- Pano kilidi (2026-11-19, kullanıcı): Basic Auth/PANO_SIFRE kaldırıldı; pano Cloudflare Access (takım slmgncortak) JWT doğrulamasıyla açılır, orkestratör kapısında iframe içinde (frame-ancestors). JWT yoksa 403 (ana Worker'da açık yol yok); /gunluk_ozet_v1.json ayrı açık Worker'dadır: https://1l3a-pano-acik.sselimgenc-c18.workers.dev/gunluk_ozet_v1.json (workers.dev'de Access yol bazında Bypass yok). ML rejim adresi: https://trader-pano-acik.sselimgenc-c18.workers.dev/rejim.json (eski L3A_REJIM_URL kodda otomatik yeniye eşlenir). Ayrıntı: deploy/KURULUM.md pano bölümü.
- KALANLAR (değişmedi): ölçüm ve raporlar (sadakat kontrolü 2026-12-08, Dersler, karne, aylık rapor, beklenti aralığı alarmları) bilgi olarak sürer. Sert risk limitleri ve kill eşikleri (SERT_LIMITLER, CANLI_LIMITLER: strateji −%30, hesap −%20, günlük) dönem kararı değil, risk korumasıdır; aynen kalır (değişiklik ayrı kullanıcı onayı). `kapanis_canli_onay` listesi (gerçek para için strateji bazlı onay) aynen kalır.
- Kodda tarih/işlem sayısına bağlı otomatik durdurma YOK: `motor/canli/aylik_rapor.py` kabul listesi (EN_ERKEN_DEGERLENDIRME, 30 işlem) yalnız rapor üretir, hiçbir şeyi durdurmaz; bu kalemler pano/raporda bilgi olarak kalır, kod değişikliği istenirse ayrı iş.
- Aynı gün alınan diğer kullanıcı kararları (uygulama planı orkestratör onayını bekler): ML ve otomatik ders öğrenme gölge modda kurulacak; dış nabız, Telegram DURDUR/DURUM, alınmayan sinyal kaydı, drift uyarısı, rejim etiketi, haber/duygu kaydı; kaldıraç 3–5x ve günlük kayıp %5 (uygulandı: günlük %5 (canlı+paper), canlı kaldıraç 3–5x (varsayılan 3); Fable uyarısı: 5x test edilmiş sınırın dışında (backtestler brüt 3x); 5x seçmeden önce tavanlı backtest + boşluk stres testi önerilir); CT trader verisi 1L3A'ya girdi olarak alınacak (ayrı paper hesabı, plan hazır, CT yayın bilgisi bekleniyor).
- **Çıkış karşı-olgusu + otomatik çıkış uygulama + "alınsaydı" gece özeti (kullanıcı onaylı, 2026-11-19; `motor/canli/cikis_karsi_olgu.py`, paper turundan günde bir, TSİ 01:00 sonrası; kapatma L3A_CIKIS_KARSI_OLGU_KAPALI=1):** son 90 günde kapanan işlemler aynı giriş + aynı ilk stopla, girişten sonraki mumlarla 8 alternatif çıkışla (basabas_1R, atr_iz_2, atr_iz_3, zaman_stopu_10, kismi_2R_yarim, brooks, farley, zirveden_geri_cekilme) yeniden oynatılır (lookahead yok, mum içinde stop+hedef = stop, paper maliyet yöntemleri; sinyal/gün sonu/kill gibi dış çıkışlar gerçek anında); sonuç `cikis_karsi_olgu.json`, en iyi alternatif Aday.cikis["en_iyi_cikis"]. ÖN KAYIT ÖLÇÜTÜ (sabitler dosya başında, değişmez): ≥10 işlem VE alternatif toplam R ≥ mevcut + max(2.0, |mevcut|×0.20) VE alternatifin en kötü işlemi mevcut en kötüden kötü değil -> onay beklemeden `cikis_override.json` ile o stratejinin paper çıkışı olarak UYGULANIR (yalnız çıkış alanları; stop/boyut/risk/limit değişmez; paper'ın uygulamadığı alan (farley) yalnız ölçülür; açık pozisyonlar eski çıkışla kalır, yalnız yeni girişler yenisini alır; override sonrası yalnız yeni girişler değerlendirilir). Telegram INFO `çıkış değişti` (gizli hesap adı yazılmaz). Geri alma: Telegram /cikis_geri_al (iki adımlı, istek dosyası CIKIS_GERI_AL, paper uygular; o strateji+alternatif bir daha otomatik uygulanmaz). "Alınsaydı": `araclar/alinmayan_sonuc.py` mantığıyla günde bir `alinmayan_sonuc.json` (neden bazında), ogrenme_karne + günlük özet notuna tek satır; bir neden ≥20 atlamada toplam R > +5 ise tek Telegram WARN (kural değişikliği YOK).
- **Çıkış otomatik geri alma + Farley (2026-11-19; ön kayıt, sabitler `cikis_karsi_olgu.py` başında `GERI_AL_*`):** uygulanmış çıkış override'ı, uygulamadan SONRA açılıp kapanan ≥10 işlemde özgün çıkışa (yeniden oynatma) göre toplam R'de max(2R, %20) kadar ya da en kötü işlemde ≥1R kötüyse gece çalışmasında kendiliğinden kaldırılır (kol özgün ayara döner, açık pozisyon eski çıkışla kalır, Telegram WARN, alternatif o kol için kalıcı kara liste `cikis_yasak.json`; geri alınan çıkışla açılan işlemler sonraki değerlendirmeden dışlanır). Farley (`agresif_iz_*`) paper motorunda uygulanır (backtest ile birebir; yalnız stop sıkılaşır), diğer alternatiflerle aynı ölçüt ve geri alma kuralına tabidir.
- **Otomatik güncelleme (kullanıcı kararı 2026-11-19):** sunucu izlenen daldaki yeni commit'leri saatte bir kendisi kurar (`motor/canli/oto_guncelle.py`, `deploy/1l3a-guncelle.*`, KURULUM.md bölüm 16); yalnız ileri sarma, GitHub "testler" başarılıysa; duman testi/servis kontrolü başarısızsa kendiliğinden geri alır (CRIT). Tek seferlik kurulum: `cd /opt/1l3a && git pull && bash deploy/oto_guncelle_kur.sh`. Geri alma: Telegram `/geri_al` (iki adımlı, istek dosyası → root güncelleyici) ya da `--geri-al`; geri alınan sha bir daha kurulmaz. `/durum` "kod: <sha>, son güncelleme" satırı gösterir.
- **Telegram standardı + komutlar (kullanıcı onaylı plan, 2026-11-19; docs/standart/telegram-standardi.md):** bildirimler `[1L3A] INFO|WARN|CRIT` ilk satırıyla, ≤3500 karakter, dakikada ≤15 (aşan INFO atılır), tekrar önleme; günlük özet 21:00 TSİ (gün içi, "21:00 itibarıyla"). Komut servisi `motor/canli/telegram_komut.py` (`deploy/1l3a-telegram.service`, KURULUM.md bölüm 15): /durum, /durdur ve /devam (iki adımlı, 4 hane, 120 sn), /yardim; yalnız TELEGRAM_CHAT_ID'e yanıt. /durdur = bayrak dosyası `/var/lib/1l3a-paper/durum/DURDUR`: paper ve ct_konsensus YENİ giriş açmaz (bekleyen giriş emri silinir; canlı yürütücü niyetleri paper'dan aldığı için canlı giriş de durur), açık pozisyonlar kendi stop/hedefiyle sürer. Haftalık özet (Pazar 21:10 TSİ) ve /rapor, /kurulumlar, /ders, /hepsini_kapat, /kademe sonraki aşama.
- **Telegram yeni komutlar + pano kartları (kullanıcı onaylı, 2026-11-19):** `/rapor` (günlük özet, `gunluk_ozet.topla` verisi), `/kurulumlar` (hesap/ct/aday: açık pozisyon, toplam K/Z, son işlem, ML filtre, drift), `/ders` (aktif/aday + son 7 gün emekli), `/hepsini_kapat` (iki adımlı: DURDUR + istek dosyası `HEPSINI_KAPAT`; paper/ct/aday süreçleri sonraki turda açık pozisyonları motorun acil kapatma yoluyla piyasa fiyatından kapatır, WARN bildirir, dosya 120 sn sonra silinir; canlı yürütücü paper kapanışını mutabakatla borsaya taşır, canlı gerçek para pozisyonları bu komutla kapanmaz uyarısı mod canli iken yanıtta yazar), `/kademe`, `/kademe_devam`, `/onayla`, `/reddet` (1L3A'da kademe/ders onayı yok: bilgi yanıtı). Gizli 4 hesap hiçbir çıktıda adıyla görünmez ("gizli_hesaplar (N)"). Panoya 3 kart: CT konsensüs hesabı, Aday stratejiler, Öğrenme (ortak okuyucu `motor/canli/kurulum_ozeti.py`; veri yoksa "henüz veri yok"). `deploy/1l3a-pano.service` ve `1l3a-telegram.service`: L3A_CT_DURUM / L3A_ADAY_DURUM.
- **CT trader verisi → ct_konsensus paper hesabı (kullanıcı kararı 2026-11-19; yalnız paper, canlıya bağlı değil; mevcut 10'lu set imzası fffbc6624416634e değişmedi).** Girdi: CT projesi `kadro_yon_v1.json` (ct.kadro_yon.v1, 15 dk'da bir). Ön kayıt kuralı (`motor/canli/ct_kadro.py` sabitleri, değişmez): 15 dk mum kapanışında taze veri (uretildi_utc ≤ karar anı ve ≤45 dk eski) varsa, eşlenen coinde (long+short trader) ≥5 ve çoğunluk ≥%70 ve net_yon long/short (çoğunluk tarafı = net_yon) → o yönde sinyal; |net_nominal_usd| sırasıyla en çok 3 açık pozisyon; aynı sembolde açık pozisyon varsa yeni giriş yok; giriş sonraki mum açılışı; stop 2×ATR(14,15m), hedef 3×ATR; ek çıkış: net_yon zıt ya da coin listeden düşerse sonraki mumda kapat; veri bayatsa yeni giriş ve konsensüs çıkışı yok (açıklar kendi stop/hedefinde); HIP-3 (dex:COIN) atlanır. 10.000 USD sanal kasa, SERT_LIMITLER aynen (%1 işlem riski, kendi kill'i). Giriş: `motor/canli/ct_paper.py`, servis `deploy/1l3a-ct-paper.service` (KURULUM.md bölüm 14), eşleme `stratejiler/ct_sembol_esleme.json`. Panoya ekleme sonra (ayrı iş).

## Takım düzeni
- **Lider (Claude Opus):** planlama, görev/ajan dağıtımı, denetim, kalite.
- **Kod:** Sonnet ajanları. **Düşük eforlu işler** (özetleme, veri ayıklama): Haiku ajanları.
- Kararlar kullanıcıyla birlikte verilir.
- Dış ajanlar: YOK. İkinci Claude hesabı ("Sonnet") 2026-11-11 itibarıyla projeden çıkarıldı (kullanıcı kararı); araştırma da ana oturumun alt ajanlarında (`stratejiler/v3_adaylar/TALIMAT.md` aynen geçerli). ChatGPT Codex 2026-11-11 itibarıyla KULLANILMIYOR (kullanıcı kararı); kodlama ana oturumun Sonnet ajanlarında. `CODEX_KODLAMA.md` kuralları bu ajanlar için de geçerli.

## Alınan kararlar
1. Strateji seçimi = kitaplarda yaygın (**farklı yazar sayısı**) + kurala dökülebilir + **backtest'te avantaj**.
2. Price action'a zorlanmaz; kurala dökülemeyen elenir.
3. Min zaman dilimi 5 dk. Stratejiler deterministik kod; LLM ajanları her mumda değil, ≥15 dk aralıkla üst seviyede karar verir (rejim, sermaye dağılımı, işlem sonrası analiz).
4. Öğrenme: lider değişiklik önerir → walk-forward test → kullanıcı onayı. Canlıda kendini değiştiren kod yok.
5. Sert risk limitleri LLM kontrolü dışında. Martingale kesin ret.
6. Binance: kripto + TradFi (ABD hisse, emtia) perpetual'ları. ~~BIST yok.~~ (2026-11-07 kullanıcı: BIST eklendi, karar 27)
7. Önce paper trading (Binance testnet değil, canlı veri + kendi simülasyon motoru).
8. DigitalOcean'da çalışır; dashboard + Telegram.
9. ~~(2026-11-06) Az enstrüman, derin uzmanlık.~~ (2026-11-07 kullanıcı kararıyla değişti → karar 23)
10. (2026-11-06) Önceki projelerden aday stratejileri lider seçer (enstrüman sayısına bakmadan, işe yarayacağını düşündükleri); hepsi 1L3A'da yeniden test edilir. Delist/hayatta kalma yanlılığı ile uğraşılmaz.

## Aşama 0 — tamamlandı
- 50 PDF → `veri/kartlar_ham/` altında **438 kart** (scalp 94, day trade 126, swing 218).
- Birleştirme → `stratejiler/aileler.json`: **100 aile** (stil başına), **13 çıkış/risk modülü**, **70 elenen** (nedenleriyle).
- Aday listesi: [stratejiler/ADAY_RAPORU.md](stratejiler/ADAY_RAPORU.md) — her stil için 10 önerilen + 5 yedek.
- Görsel ağırlıklı, metni olmayan PDF'ler: Bressert, Morge (0 kart).

### Denetim notları
- Listeler **aday**dır; final 10 Aşama 2'de backtest sonucuyla seçilecek (15 aday/stil test edilir).
- **ORB** (day trade #1): Bulkowski'nin 555 hisse testinde mekanik çıkışlarla komisyon sonrası zararlı → testte doğrulanırsa elenir.
- Day trade havuzu zayıf (çoğu tek yazarlı); swing havuzu güçlü (MA kesişimi 12, MACD 7 yazar).
- Bant dönüşü / konsolidasyon kırılımı / stokastik üç stilde birden var → liderin portföy seviyesinde korelasyon/risk izlemesi şart.
- Elenenler: opsiyon, temel/olay verisi, tescilli göstergeler (LuxAlgo, VSA, ML), Level-2/TICK, martingale.
- Kitaplardaki kazanma oranı iddiaları çoğunlukla kanıtsız (raporda "şüpheli" işaretli).

## Aşama 1 — devam ediyor
Yapılanlar:
- **Veri:** Binance API bu bulut makinesinden konum nedeniyle engelli; geçmiş veri `data.binance.vision` arşivinden
  (`motor/veri/`: indirme + sha256 + parquet + 5m→üst TF). Arşivde 2026-10-28 günü tüm sembollerde eksik.
  Funding aralığı sembole göre değişir (BTC 8s, XAU 4s).
- **Sembol envanteri:** `veri/sembol_envanteri.csv` — 1080 sembol. TradFi geçmişi kısa: en eski XAU 2025-12,
  hisseler 2026-01..10 (≈1–10 ay). Sınıflandırma tahmini; kesin liste exchangeInfo ile (API erişimli sunucudan).
- **Backtest çekirdeği:** strateji arayüzü, göstergeler, Decimal motor (komisyon/kayma/funding, step aşağı yuvarlama),
  sert limitler (TASLAK), walk-forward, metrikler. İlk deneme (BTC 5m, EMA 9/21, 2 ay): −%17, komisyon sermayenin ~%9'u
  → 5m'de %1 risk kaldıraç tavanına dayanıyor, maliyet baskın.
- **Sürüyor:** swing ailelerinin kodu (9 aile), stop kayması ayrı + limit "ölç" modu, yazar sayısı denetimi,
  BTC/ETH 2020– 5m veri indirme.

### Aşama 0 denetim bulguları (lider)
- Kartların piyasası: hisse 185, genel 154, vadeli 64, forex 32, **kripto 2**, emtia 1 → kitap iddiaları bizim enstrümanlarda denenmemiş.
- 51 kart 1m kaynaklı (çoğu scalp) → 5m'ye taşınınca "esinlenen" stratejiye dönüşür.
- Day trade önerilenlerin 6/10'u ≤2 yazar; bb-sıkışma ve stokastik tek kart.
- Çok stilli 33 ailenin kanonik kuralı stiller arasında birebir kopya (ör. daytrade__stokastik-donus'un tek kartı Williams %R).
  → Koda dökerken kaynak kartlar esas alınır.
- Yazar sayısı yakın-ama-farklı kurallarla şişmiş olabilir (denetim sürüyor: `stratejiler/yazar_denetimi.csv`).
- 166 kartta stop, 192 kartta kâr al yok → çıkış modülü seçimi sonucu belirleyecek.
- Çoklu test riski (45 aday × ızgara × sembol) → Aşama 2'de eleme eşikleri gerekli.

### Önceki projeler (kapatıldı, arşivlendi)
`algo-sg`, `strateji-sg`, `swing-sg` kapatıldı; kod, stratejiler, sonuçlar, kağıt bot durumları `arsiv/` altında
(kitap/PDF alınmadı — kullanıcı kararı). Dersler ve aday/elenen listesi: [arsiv/OZET.md](arsiv/OZET.md).
Ana ders: önceki sonuçlar OOS'a bakılarak seçilmiş ve kâr birkaç işlemde yoğun → üst sınır kabul edilir.

### Kararlar (2026-11-06, kullanıcı onaylı)
11. **Scalp:** yalnız ≥15m, en güçlü 4–5 aday; hiçbiri geçmezse scalp ajanı kapanır.
12. **Day trade:** 10'a tamamlanmaz; en güçlü 5–6 aday (KGT dahil).
13. **Eleme ölçütü:** maliyet+funding sonrası kârlı, OOS PF ≥ 1.2, ≥ 50 işlem, en iyi %5 işlem çıkarılınca çökmez,
    OOS parametre seçiminde asla görülmez (seçim yalnız walk-forward eğitim pencerelerinde).
14. **Sert limitler kesin:** işlem başı %1 (2026-11-09'dan itibaren MALİYET DAHİL: fiyat riski + stop kayması + 2 komisyon; ON_KAYIT Güncelleme 8), günlük %3 (dolunca açık pozisyon da kapanır), 3x, %20 kill switch.
15. **Sunucu:** DigitalOcean Frankfurt.
16. ~~Veri/seçim: BTC+ETH 2020–; TradFi yalnız doğrulama.~~ (2026-11-06 kullanıcı kararıyla değişti → karar 22)
17. ~~Enstrüman: başlangıçta 3–5 (BTC, ETH, XAU + 1–2).~~ (2026-11-06 → karar 22). README'deki ~25 enstrüman planı iptal.
19. (2026-11-06) **Hepsi test edilir, erken eleme yok:** ~700 aday (438 kart + 160 TradingView + 68 freqtrade + ~30 dış kural).
    Huni: (1) hepsi kodlanır → (2) geniş tarama, yalnız apaçık umutsuzlar elenir → (3) walk-forward (karar 13) →
    (4) kilitli dönem → ajan başına ~3.
20. (2026-11-06) **Kilitli dönem:** 2025-11-01 00:00 UTC sonrası veri kasada. Tarama/walk-forward/seçimde kullanılmaz;
    final seçimde yalnız BİR kez açılır (açılış kayda geçer).
21. (2026-11-06) KGT iki aday: `onceki__kgt` (swing, orijinal, günlerce tutar) + `onceki__kgt-gun` (day trade, gün sonu kapanır).
22. (2026-11-06) **Test evreni (kullanıcı kararı):** yalnız kripto değil. Kripto: BTC, ETH, SOL (Binance verisi).
    TradFi: Magnificent 7 (AAPL, MSFT, GOOGL, AMZN, NVDA, META, TSLA) + altın (XAU) + petrol (WTI) + bakır.
    TradFi geçmişi Binance'ta kısa olduğundan veri **Dukascopy**'den çekilir (`DK_` önekli semboller); canlı işlem
    Binance TradFi perp'lerinde. Maliyet modeli Binance'ınki; Dukascopy verisinde funding yok. Kilit tarihi aynı.
    Canlıda yine az enstrüman (karar 9): enstrüman seçimi testlerin sonucuna göre yapılır.
23. (2026-11-07) **Canlıda enstrüman sayısı artacak (kullanıcı kararı); portföy katmanı zorunlu.** (a) Çok enstrümanlı
    portföy motoru: aynı anda birden çok grafik, portföy düzeyinde sert limitler (günlük %3, %20 kill switch, toplam 3x;
    işlem başı %1 risk her pozisyonda korunur). (b) Tek-grafik stratejilerinin birleşik çalıştırılması (risk üst üste
    binmesi, korelasyon). (c) "Tek enstrüman mimarisi" yüzünden elenen tüm stratejiler (rotasyon, kesitsel momentum,
    çift işlemi, KMN vb.) kodlanıp test edilir — strateji kaçırılmaz. ML ve opsiyon gibi başka nedenle elenenler hariç.
24. (2026-11-07) **Portföy stratejileri için eleme ölçütü (kullanıcı onayı):** işlem sayısı yerine OOS ≥ 3 yıl ve
    ≥ 20 yeniden dengeleme; başarı Sharpe ve düşüşle ölçülür (lider eşikleri: OOS net > 0, OOS Sharpe ≥ 0.5,
    OOS max düşüş ≤ %20). (2026-11-07 güncelleme, kullanıcı onayı: "en iyi %5 gün hariç net > 0" kaldırıldı — al-tut dahil
    hiçbir günlük seri geçemiyordu; yoğunlaşma sağlamlık aşamasında ölçülür.) Tek-grafik stratejilerinde karar 13 aynen geçerli.
25. (2026-11-07) **Portföy risk bütçesi (kullanıcı onayı):** tek-grafik stratejilerinde işlem başı %1 aynen kalır.
    Portföy (hedef ağırlık) stratejilerinde pozisyon başına %1 yerine **portföyün toplam stop riski ≤ %5**; günlük %3,
    %20 kill switch ve 3x tavanı her iki türde aynen geçerli. Değer koddadır (SERT_LIMITLER), ajan aşamaz.
26. (2026-11-07) **Yetki devri (kullanıcı):** canlı para dışındaki strateji/araştırma kararlarını lider sorumluluk alarak
    verir ve sonrasında kullanıcıya bildirir. Canlı para (gerçek emir, sermaye, API anahtarı, sert limitlerin gevşetilmesi)
    her zaman kullanıcı onayı ister. Lider kararları "Lider kararları günlüğü" bölümüne yazılır.
18. Önceki projelerden alınanlar: 4S kırılım (algo-sg A + swing-sg S2 birleşik), KGT, S1; yedek B. S3 alınmadı. KMN portföy katmanında test edilecek (karar 23).

## Aşama 2 — devam ediyor (2026-11-07)
- Katman 1 ✅: 192 strateji kodlu (105 kitap + 87 dış), 226 kart ayarı, 110 dış ayar. 1501+ test.
- Katman 2 ✅ (kripto): geniş tarama 3168 + ızgara ~27k koşu (`sonuclar/tarama/`). Swing %66 PF>1; daytrade %8, scalp %3.
  Uyarı: 2020–25 kripto boğa dönemi (BTC 15x) uzun-trend stratejilerini şişiriyor.
- Katman 3 (kripto) ✅: hızlı walk-forward (`motor/arastirma/wf_tarama.py`; swing 730/180 gün, day/scalp 365/90).
  1140 görevden karar 13'ü geçen 32 (swing 31, daytrade 1, scalp 0). Hiçbiri 3 kripto sembolün üçünde birden geçmedi.
- Katman 3b (kripto) ✅: sağlamlık (`motor/arastirma/saglamlik.py`; kapılar: maliyet×2 PF≥1.05, rastgele giriş p≤0.05,
  bootstrap PF alt sınırı >1, komşu parametrelerin ≥%60'ında PF>1). 32 adaydan 13'ü geçti (öneri). Uyarılar: Bonferroni'yi
  hiçbiri geçmiyor; aynı strateji komşu sembol/TF'de çoğunlukla zayıf; DSR ≈ 0.
- Portföy katmanı (karar 23) ✅ motor + 15 strateji sınıfı (71 adaydan 54 bağlandı) + portföy walk-forward.
  Kripto: 0/15 karar 13; 8'i Sharpe'ta al-tutu geçiyor; 2022'de al-tut −%75, çoğu strateji −%14..+%5.
- Veri ⏳: Dukascopy (karar 22). DK_AAPL 5m tamam (2017–); dakikalık indirme yavaş (9–30 saat). Hızlı yol: aylık
  saatlik dosyalar → swing/daytrade 1h+ testleri önce; 15m/30m dakikalık veri tamamlanınca.

## ODAK LİSTESİ VE ARALIK SONU CANLI — 2026-11-14 (KULLANICI KARARI; Fable görüşü alındı)
Sonuç görülmeden önce değil: 14 Kasım'a kadarki tüm sonuçlar (holdout, ileri sınav, risk senaryosu) görüldükten sonra
TERCİHLE seçildi; kanıt düzeyi stratejiye göre farklı (yalnız gauss ve ewo ön kayıtlı holdout'u geçti).
- ~~**Takvim:** paper Aralık sonuna kadar; canlı Aralık sonu / Ocak başı.~~ (KALKTI 2026-11-19: tarih yok, bkz. ÜSTÜN KARAR) Kapanış adaylarının "12 hafta paper" şartı
  kullanıcı kararıyla esnetildi (664/670/705 paper'a 14 Kasım'da girdi → ~6–7 hafta). Önceki v2 takvimi (ewo Ocak, Şubat sonu
  değerlendirme) bununla güncellenir.
- **Odak (panoda görünür, 7):** swing dis__gauss-stoch-eth, HAM:X005:664#v1, dis__hma-atr-rider; gün içi dis__ewo-ema-ofset,
  dis__e0v1en, HAM:B001:670#v1; swing yedeği HAM:X005:705.
- **Yedek kuralı (705):** yalnız 664 ya da hma TEK BAŞINA bozulursa devreye girer; iki swing aynı anda bozulursa 705 açılmaz
  (aynı aile) → lube ya da nakit.
- **Gizli çalışan (panoda yok, 3):** dis__lube, HAM:B001:574#v1, HAM:X005:730#v2. Yalnız bir odak stratejisi bozulursa açılır;
  "iyi gidiyor" diye terfi YOK.
- **Durdurulan (10; kayıtlar arşivde, silinmez):** jt-awesome-osilator, uc-ortalama-boga-sma60, voltarget-trend,
  haftalik-macd-gunluk-ma, pf__sabit_sepet, HAM:X005:301#v1, HAM:X005:138#v3, HAM:X005:259#v1, HAM:X005:793#v1, HAM:B001:538#v1.
- **Aralık sonu karar ölçütleri** (2026-11-19: karar noktası KALKTI; ölçütler yalnız bilgi/izleme olarak kalır) **(bozuk değil mi; "iyi" kanıtı değil):** paper işlemlerinin backtest ile uyumu (aynı gün/yön
  ≥ %90); düşüş, sınav yılı düşüşünün 2 katını aşmaz; kayma (ewo, e0v1en, 670) varsayımın 1,5 katını aşmaz (aşarsa e0v1en
  çıkar) — DÜZELTME (Fable pano incelemesi): paper dolumu varsayılan kaymayla simüle eder, kayma paper'da ÖLÇÜLEMEZ;
  bu ölçüt ancak testnet/canlı dolumla (küçük kasa ilk haftalar) uygulanır; 20'den az işlemde hüküm "bilinmiyor"; en çok kazandıran sembol çıkınca artıda mı; limitlere takılan sinyal oranı
  (2000 USD ölçeğinde > %50 ise elenir).
- **Canlı kasa:** en fazla ~2000 USD. Strateji başı risk kararı (şu an kodda %1,5 sabit; Fable önerisi %0,5–%3 arası,
  %3 tavanı aynen) canlıdan önce kullanıcıyla verilir; seçilenler gerçek kasa tutarı + limitlerle yeniden oynatılır.
- Dayanak: `sonuclar/risk_senaryo/RAPOR.md`, `sonuclar/kapanis/HAKEM_FABLE_PAPER_GENISLETME.md`.
- **GÜNCELLEME (2026-11-14 gece, Fable mantık denetimi; KULLANICI önerileri kabul etti):**
  - 670 odaktan çıktı, gizliye alındı: stopu %30–40, canlıda `stop_uzaklik_maks_oran` 0,25 nedeniyle hiç işlem açamaz
    (574 de aynı). Görünür odak 6: swing gauss, hma, 664; gün içi ewo, e0v1en; yedek 705. Gizli 4: lube, 574, 730, 670.
  - Düşüş ölçütü TEK tanım (önceki "sınav ×2" ve "×1,5" ifadelerinin yerine): sınır = min(max(1,5 × geliştirme dönemi en kötü
    düşüş (%0,5 risk, `sonuclar/risk_senaryo/ozet.csv` baz_0.5%), %5), %15). Ölçülen = paper başından beri en kötü düşüş.
  - Strateji başı canlı risk aralığı %0,5–1,5 (%3 fikri iptal: %6 toplam risk tavanında yalnız 2 pozisyon sığar).
  - ~~"Bilinmiyor" (< 20 işlem) olan strateji canlıya ancak en çok 60 USD deneme kasasıyla girer.~~ (2026-11-19: duman adımı KALKTI; gerçek paranın adımı ve tutarı yalnız kullanıcı bildirince belirlenir)
  - "En iyi sembol çıkınca artıda mı" testi paper'a değil geliştirme + sınav verisine uygulanır (paper'da gürültü).
  - Backtest uyumu yalnız 2026-11-14 17:57 UTC sonrası girişleri sayar; uyum ölçütü tesisat testidir, kanıt değil.
  - Kayma ve "limite takılan sinyal" ancak canlı kurallarla ölçülür: önce `sonuclar/canli_oynatma_300/` (300 USD kasa, gerçek
    CANLI_LIMITLER ile geçmiş oynatma), sonucuna göre paper yanına canlı limitli gölge hesaplar.
  - 11 Kasım v2 planından İPTAL olanlar: "6–9 strateji hedefi kaldırıldı" (yeniden 5–6 odak), "ewo 250 USD Ocak" ve
    "değerlendirme Şubat sonu" (yerine Aralık sonu karar), "hma/lube canlıya en erken 2027 Ç2" (hma odakta; lube gizli),
    "e0v1en ilk emeklilik adayı" (şartlı odak). GEÇERLİ kalanlar: CANLI_LIMITLER aynen, toplam −%10 büyüme freni (elle),
    ilk yıl hedefi "yatay" (±%10), sadakat kontrolü 8 Aralık, testnet + duman adımı (kayma ölçümü için gerekli).
  - Gizli hesapların kill ve hata olayları Telegram'a gider ("[gizli]"); işlem bildirimleri gitmez.
- **CANLI BÖLÜŞÜM VE RİSK (2026-11-14 gece; Fable önerisi, KULLANICI KABUL ETTİ; dayanak `sonuclar/canli_oynatma_300/RAPOR.md`):**
  - 2000 USD: 664 → 500 (%1,5), ewo → 400 (%1,0; kayma ölçülünce %1,5'e çıkabilir), hma → 300 (%0,5), gauss → 300 (%0,5),
    e0v1en → 200 (%0,5), yedek nakit 300 (705 devreye girerse buradan).
  - (2026-11-19: duman adımı KALKTI; gerçek paranın adımı ve tutarı yalnız kullanıcı bildirince belirlenir) ~~Kademeli giriş: önce testnet + 2 × 60 USD duman (kayma, min tutar/adım, emir hataları burada ölçülür); Aralık sonu
    karardan sonra tam paylar. "< 20 işlem → en çok 60 USD" ve "toplam −%10 büyüme freni" kuralları geçerli.~~
  - Beklenti (tarihsel, sonradan seçilmiş; kanıt değil): yılda ~%9–10, en kötü düşüş ~−%10. Hedef yine "ilk yıl yatay".
  - Kod: canlıda strateji başı `islem_risk` {0,005; 0,01; 0,015} izinli olacak (şu an yalnız 0,015); %3 güvenlik tavanı ve
    diğer CANLI_LIMITLER aynen.
- **Sunucu (2026-11-14):** 20→10 geçişi yapıldı (PR #64; imza fffbc6624416634e). Ardından kullanıcı kararıyla paper
  **17:57 UTC (20:57 TSİ) SIFIRDAN** başlatıldı; eski durum silinmedi: `/var/lib/1l3a-paper/durum_eski_20261114_2100`.
  Paper ölçümleri bu andan başlar. 8 Aralık sadakat hatırlatması yeniden kuruldu.

## 1L3A v2 PLANI — 2026-11-11 gece (KULLANICI ONAYLI; geçerli plan)
Kaynak: `sonuclar/canli/CANLI_PLAN_V2.md` (eski `CANLI_PLAN.md`'nin yerini aldı). Özet:
- **Tanım:** yürütme ve ölçüm projesi; kanıtlanmış avantaj yok, yapı tamamen long; ilk yıl hedefi "yatay" (±%10), düşüş ≤ %15.
- **Kadro:** ewo-ema-ofset çekirdek (60 → 250 USD); e0v1en 60 USD (kod sınayıcı, kırılgan, ilk emeklilik adayı);
  hma-atr-rider ve lube paper'da (canlıya geçiş V2 §6, en erken 2027 Ç2). "6–9 strateji" hedefi kaldırıldı.
- **Risk:** %1,5 sabit; %2/%3 takvimi kaldırıldı; CANLI_LIMITLER aynen; yeni: toplam −%10 büyüme freni (elle).
- **Takvim:** Faz 0 hazırlık (25 Kas) → testnet (25 Kas–5 Ara) → ~~2 × 60 USD duman (Aralık 1. hf)~~ (KALKTI 2026-11-19) → 08.12 sadakat +
  birleşik hesap oynatması (8–20 Ara) → ewo 250 USD (Ocak) → değerlendirme (Şubat sonu).
- **Dayanak (11 Kasım testleri):** meta-test + sağlamlık (PR #42, #44), teşhis (PR #43), yeni sembol sınavı (PR #45:
  4/4 genelleşmiyor; yeni coinlerin al-tut medyanı −%77), portföy boyutu (PR #44).
- **Faz 0 yazılım tarafı TAMAM (2026-11-11 gece):** haftalık rapor + yürütücü append-only kayıt (#48), birleşik hesap
  oynatması geçti (#47: S1 en kötü 12 ay −%11,5, hesap kill yok), risk kodda 0.015'e kilitli (#50), B18 pano şifre kilidi
  (#51), testnet/duman kontrol listesi `sonuclar/canli/TESTNET_KONTROL.md` (#49). Sunucu gideri 12 USD/ay.
- **Sırada (kullanıcı, 25 Kasım'a kadar):** sunucuda `git pull` + PANO_SIFRE (KURULUM §11 "Pano kilidi"); Binance alt
  hesaplar; testnet API anahtarı → TESTNET_KONTROL.md A bölümü. Yeni kayıt uçları (userTrades/income) ve algo stop uçları
  ilk kez testnet'te doğrulanacak. 2026-12-08 sadakat hatırlatması kurulu.

## DEVİR NOTU — 2026-11-11 akşamı (ESKİ; v2 planı bunun yerini aldı) (projeye dönüşte buradan başla)
Kullanıcı: "çok dağıldık, proje üzerinde yeniden çalışacağım". Açık iş bırakılmadı. Görsel özet: kullanıcıya gönderilen
"1L3A_Proje_Akis.pdf" (6 sayfa). Kaynak dosyalar:
- **Canlı plan (kilitli, kullanıcı onaylı):** `sonuclar/canli/CANLI_PLAN.md`. Aşama 1 = 4 × 250 USD: e0v1en, ewo-ema-ofset (15m; %1,5 → 6. hf %2 → 12. hf %3, şartlı, ELLE) + 2 swing (%1,5 sabit).
- **Kilitli swing seçimi:** `sonuclar/canli/SWING_SECIM.md` → hma-atr-rider, lube (yedek sırası: gauss-stoch-eth, haftalik-macd). 2026-12-08 sadakatini geçemeyen düşer, sıradaki alınır.
- **Ölçüm:** `sonuclar/canli/OLCUM_250_15.md`. Atlanan sinyal > %50: gauss, jt-awesome, voltarget ve **hma-atr-rider (%50,7)**. Plan maddesi "o strateji %2 ile başlar" → mekanik okuma: hma-atr-rider %2 ile başlar ve swing olduğu için %2'de sabit kalır. **Kullanıcı teyidi bekliyor** (plan, swing için "%1,5 sabit" de diyor).
- **Canlı kod:** `motor/canli/borsa/` (kuru/testnet/canli; CANLI_LIMITLER; strateji başına islem_risk 0,015–0,03; `python -m motor.canli.borsa.risk_adim_kontrol --durum DIR` salt okunur). Kurulum: `deploy/KURULUM.md` §13.
- **Eksik:** haftalık canlı–paper raporu yok (risk adım şartı 2 ve 3 bu yüzden "bilinmiyor" döner) — Aşama 1 başlamadan yazılmalı.
- **Sırada:** (1) Binance testnet: kullanıcı testnet API anahtarını oluşturup /etc/1l3a-canli.env'e koyar; tek strateji e0v1en; önce kuru, sonra testnet (algo emir uçları ilk kez burada doğrulanır). (2) B18 pano kilidi (Cloudflare Access). (3) 2026-12-08 sadakat kontrolü (14 bayat dolum hariç). (4) Aralık başı USDT yatırma, alt hesaplar. (5) Aralık ortası Aşama 1.
- **Bekleyen kullanıcı kararları:** hma-atr-rider başlangıç riski (%2 mekanik okuma mı, %1,5 mi); Aşama 2 kasası (+500 USD ya da 4'te kal; 6–8 hafta sonra).
- **Sonuçlar:** v3 eleme 0/9 (`sonuclar/v3/ELEME_RAPORU.md`), scalp araştırması: aday yok (RAPOR Tur 9), noise inceleme: motor hatası yok (`sonuclar/v3/INCELEME_NOISE.md`).
- **Ekip:** Codex ve ikinci Claude hesabı çıkarıldı; her şey ana oturum + alt ajanlar (Sonnet/Haiku) + Fable hakem.

## Lider kararları günlüğü (karar 26)
- 2026-11-11 gece (KULLANICI): "planı onaylıyorum, uygula" → 1L3A v2 planı (CANLI_PLAN_V2.md) geçerli; CANLI_PLAN.md yerini aldı.
  Kullanıcıya sunulan 4 dış belgeden yalnız paper testli ikisi (Öneri Formu, Yönetici Sentezi) dikkate alındı; doğrudan-canlı belgeleri kullanıcı eledi.
  stratejiler/canli_ayar.ornek.json v2 kadrosuna (ewo + e0v1en, 60'ar USD) güncellendi.
- 2026-11-10: BAĞIMSIZ DENETİM (Codex raporu B01-B18; Denetçi SG + Fable doğruladı: 17 gerçek, 1 şüphe) → düzeltmeler (testli):
  paper/portföy: B09 günlük/kill limiti açılışta girişlerden önce; B11 askıdaki pozisyon da limitte kapanır (+alarm); B05 geç gelen funding
  bir kez ödenir; B06 sembol bazlı maliyet; B07 geç gelen mumda kaçan stop/hedef kontrolü; B10 kaldıraç tavanında kayma payı.
  araştırma: B04 sıfır süreli işlem hayalet pozisyon bırakmaz (v2 ham: 1.6M işlemde 267, paper setindeki 10 stratejide 0 → v2 seçimi etkilenmedi);
  B15 holdout'ta atlanan sembol hata sayılır ve kapı KODDA kapanır; B16 ham/eleme yan dosyasına veri/strateji/motor hash + commit
  (eski v2 dosyaları yalnız --eski-yan-dosya ile); B17 sessiz skip → assert; B14 holdout başlangıç işareti atomik; B02 htf/yeniden_örnekle
  eşiği nedensel (ilk seans dönemi artık atılır). B01, B13 → v3 ön kaydında karar. B03, B08, B12 zaten belgeli. B18 (pano erişimi) canlıdan önce.
  Tüm suite: 4161 geçti. Paper sunucuda güncellenmeli (git pull + restart).
- 2026-11-10 (KULLANICI): ChatGPT (Codex) denetim + öneri + geliştirme için kullanılır. Kurallar AGENTS.md: kendi dalında PR açar,
  birleştirmez; lider her PR'ı doğrulayıp birleştirir. Sırayla: salt-okur denetim raporu → öneri listesi → seçilenler PR olarak.
- 2026-11-10: Y-5 UYGULANDI (evren zinciri bitti): tek-grafik kaldıraç tavanı komisyon payı dahil (portföy motoruyla aynı K·E/(1+K·taker)).
  Etki: tavanın bağladığı işlemlerde miktar −%0.15 (taker %0.05). Eski sonuçlar (v1/v2, kilit, final) tarihsel kayıt; yeniden üretilmez.
  test_cikis_modulleri_ek altın değerleri eski tavanla (monkeypatch) doğrulanmaya devam eder. Dolum denetimi öneri 2 testi eklendi;
  öneri 4/5 için motor'da İSTEĞE BAĞLI 'olumsuz_dolum' stresi (varsayılan 0 = birebir eski). Kapıya bağlanmadı: v3 ön kaydında karar verilecek.
  Yapılmadı: K1c reddedilen sayımı ve eşleşen-işlem PF (öneri 2b/3) → v3 ön kaydıyla birlikte.
- 2026-11-10 09:27 UTC: **PAPER v2 BAŞLADI** (sunucu, deploy/v2_gecis.sh): 10 hesap aktif, WS 46 akış, yeni 10 DK sembolü tohumu
  sunucuda indirildi (başarısız ay 0). DK_JNJ/DK_MA Binance'te yok → evrenden düştü (beklenen). Eski 7'li durum:
  /var/lib/1l3a-paper/durum_eski_7li_20261110_0906. Sunucu kilit günlüğü yedeği: /var/lib/1l3a-paper/kilit_acilis_sunucu_eski_20261110.jsonl.
  Uyum (fidelity) kontrolü 28 gün: en erken 2026-12-08; performans değerlendirmesi ≥12 hafta: en erken 2027-02-02.
- 2026-11-10 (KULLANICI): ikinci Claude hesabı yalnız v3 aday araştırması yapar (stratejiler/v3_adaylar/TALIMAT.md). Yalnız o klasöre yazar,
  PR açar, birleştirmez; ana oturum diff'i denetleyip birleştirir. Adaylar v3 kuyruğu; test yeni ön kayıt + holdout sonrası verisiyle.
- 2026-11-09 (KULLANICI kararı, SONUÇ SONRASI, ON_KAYIT_V2 0.3/0.4'ten SAPMA): resmi holdout bittikten sonra kıl payı kalan
  55 strateji (set dışı kalan 3 sağlam keşif, 2 izleme, 2 BH altı, eleme'de tek kapıdan kalan 48) holdout döneminde KEŞİF amaçlı
  koşulur. Etiket: 'sonuç sonrası keşif — kanıt değil'. Resmi v2 sonucu (set 2, GEÇTİ) değişmez; bu sonuçlarla hiçbir strateji
  resmi sete/paper'a doğrudan alınmaz — ancak yeni ön kayıt + ileri (paper) veriyle. Aynı s=0.5, maliyet ×1, K2 B=2000 (hk2 tohumu).
  Çıktı ayrı: sonuclar/evren/v2/holdout_kesif/. Resmi holdout dosyalarına dokunulmaz.
- 2026-11-10: KEŞİF SONUCU (kanıt değil). 55'in 35'i net > 0; net > 0 ve K2 p ≤ 0.05: 8 (şansla beklenen ≈ 2.75).
  8: jt-awesome-osilator 1d (+%23.1, p .005, eleme E5 kill), uc-ortalama-boga-sma60 1d (+%9.0, p .0005, E4), pf__sabit_sepet
  (+%7.8, p .0005, E5 kill), haftalik-macd-gunluk-ma 1d (+%2.4, p .019), e0v1en 15m kripto (+%2.0, p .0015), lube 1d
  (+%3.0, p .016, yalnız 20 işlem, E2), hma-atr-rider 1d (+%2.8, p .016, E5 kill), voltarget-trend 1d (+%2.5, p .023, E4).
  aroon-stochrsi-ema-dip 15m: p .036 ama net −%0.3. Paper önerisi kullanıcıya sunuldu (mühürlü 2 "doğrulandı" + keşif "iyi göründü").
- 2026-11-10 (KULLANICI onayı): paper seti = 10 strateji (doğrulandı: gauss-stoch-eth 1d, ewo-ema-ofset 15m; iyi göründü: yukarıdaki 8).
  Lider kararı: her strateji kendi sanal kasasında (10.000 USD, s=0.5, sert limitler kasa başına) — holdout ölçümüyle aynı, şanslılar tek tek elenir.
  Kabul şartı: tekrar modu holdout dönemindeki neti yeniden üretmeli. Eski 7'li deneme sürüşünün durumu silinmez, kenara alınır.
- 2026-11-10: paper v2 kodu hazır (motor/canli/paper_v2.py, 10 hesap, kasa başı s=0.5, sert limitler kasa başına; KURULUM §12).
  Kabul testi: 6 strateji holdout'a ≤0.45 puan yakın. 4'ünde fark büyük: gauss-stoch-eth +10.4→+6.1, jt-awesome +23.1→+8.9,
  hma-atr-rider +2.8→+9.6, voltarget +2.5→+1.3. Neden (ölçüldü): holdout oynatması (secim.yeniden_oyna) %5 toplam stop riskini
  giriş riskiyle sabit sayıyor; motorlar (backtest/paper/canlı) anlık riski sayıyor. Limitsiz karşılaştırmada işlem mekaniği uyuşuyor.
  LİDER KARARI: paper motor kuralıyla çalışır (canlıda geçerli olacak kural bu); holdout oynatmasının limit yaklaşıklığı bilinen
  sınırlama olarak kaydedildi, resmi holdout sonucu değiştirilmez. Sonuç: jt'nin +%23'ünün büyük kısmı limit yaklaşıklığından.
  Ayrıntı: sonuclar/paper_v2/uyum/uyum_raporu.md. Kilit günlüğüne bir ajan ön denemesi 4 satır 'bench' gerekçesiyle yazdı; dürüst kayıt olarak kalır.
- 2026-11-09 23:11 UTC: v2 HOLDOUT (kullanıcı onayıyla, tek sefer; 2025-11-08 → 2026-11-06): SET KAPISI GEÇTİ.
  Set net +%13.4 (tek kasa, maliyet ×1, TradFi funding dahil, işlem başı %0.5), p_set 0.0002; hatalar boş (beyan 1 sağlandı).
  gauss-stoch-eth 1d: 159 işlem, net +%10.4, PF(R) 1.53, K2 p 0.015. ewo-ema-ofset 15m: 46 işlem, net +%3.7, PF(R) 1.64,
  K2 p 0.0005. Budama yok; ikisi de paper'a gider (paper_girdisi.json). Beyan 5 gereği: gerekli, yeterli değil; asıl sınav paper.
- 2026-11-09: v2 HOLDOUT ÖNCESİ BEYAN (Fable denetimi GO: 0 engel, 5 belge şartı, 14 not; sonuclar/denetim/fable_holdout_oncesi_2026-11-09.md).
  Holdout koşusundan ÖNCE yazıldı, sonra değiştirilmez:
  (1) Hata kuralı: holdout raporunda herhangi bir set stratejisinin `hatalar` alanı boş değilse koşu 'hatalı' sayılır, kapı GEÇTİ kabul edilmez.
  (2) Açıklama: dis__gauss-stoch-eth havuzda kilit_gorulmus=hayir görünse de Katman 4'te (2026-11-07) 4h + ızgara ayarıyla
      ETH/SOL/META/NVDA'da 2025-11-01→2026-11-05 koşuldu (sonuclar/kilit/sonuc.csv, 4 satır; lider doğruladı). Seçim mekanikti.
  (3) Dondurma: koşu temiz çalışma kopyasında; veri yenilenmez; motor/arastirma/v2/ içine .py eklenmez; veri dosyası sha256
      listesi koşudan önce kaydedilir; holdout günlüğü hemen commit edilir.
  (4) Veri sonu: kripto 15m/1d 2026-11-06; hisse/emtia 2026-10-30; kripto funding 2026-10-31.
  (5) Yorum: p_set 15m bacakta yapısal olarak kolay (rastgele giriş maliyetten eksi) → belirleyici şart fiilen set net > 0.
      Evren 2026-11-07'de seçildi (ileriyi görme; ör. ZEC). GEÇTİ = 'gerekli, yeterli değil'; asıl sınav paper.
      Bilgi: ewo-ema-ofset geliştirmenin son yılında hafif ekside (net −%0.6) — holdout'ta budanması beklenen bir sonuçtur.
- 2026-11-09 (KULLANICI kararı): holdout'tan ÖNCE Fable bağımsız denetimi (v2 kodu + çıktıları); holdout denetimden sonra.
- 2026-11-09 (gece, v2 SONUÇ — geliştirme dönemi, kanıt değil): ham 13.628 görev; eleme 222 → 18; resmi test (K2, BH q=0.10,
  m=939) → 7 keşif (swing 4, gün içi kripto 3), SPA p=0.02; sağlamlık → 5 sağlam keşif; SET (mühürlü) = 2 strateji:
  dis__gauss-stoch-eth 1d (swing, genel evren) + dis__ewo-ema-ofset 15m (gün içi kripto), eşit risk s=0.5 (işlem başı %0.5;
  bootstrap %95 düşüş %14.4). Atlananlar: ama-egri-donus (aynı etiket), aroon-stochrsi (aynı etiket), gauss-stoch-btc
  (aynı küme). İzleme: haftalik-macd-gunluk-ma (S3), e0v1en (S2). HOLDOUT kullanıcı onayı bekliyor.
- 2026-11-09: v2 havuz SON MÜHÜR: 222 satır (+7 short açabilen aday: kesitsel L/S 2, yavaş TSMOM 2, funding/kripto 3),
  m=939, havuz_v2.csv sha256 e06c994e…. Eklemeler sonuç görülmeden yapıldı. Bundan sonra havuza ekleme yok.
  P1-1/P1-2/P0-4 kodlandı (motor/arastirma/v2), tam test 4043 geçti. Sıradaki: v2 ham + eleme koşusu; paralelde P1-3..P1-6.
- 2026-11-09: P0-5 dolum denetimi bitti (sonuclar/evren/v2/dolum_denetimi.md; lider motor.py:300-305, 338-360'ı doğruladı):
  motor hatası YOK (giriş sonraki mum açılışı, mum içinde stop önce, lookahead yok). Gecikmede PF artışı = `gecersiz_stop`
  ile çöküş devamı sinyallerinin atlanması (gerçek etki, fiyat iyileşmesi değil); yalnız 5m'de. Maliyet ×2 + mum aralığının
  %10'u kayma stresinde 5 scalp PF 1.05–1.58; kâr flash-crash günlerinde yoğun. ON_KAYIT_V2 2.5 ön şartı sağlandı.
- 2026-11-09: v2 havuz TASLAK mührü: 215 satır (swing 189 = 1d 182 + 4h 7; gunici_kripto 7; portfoy 19), 1 birleşme, m=939,
  havuz_v2.csv sha256 a9b5854c…; etiketler sonuç görülmeden kural metninden. Lider kararı: ON_KAYIT_V2 2.8 eklemeleri (Fable
  P2-1: kesitsel L/S, kısa açabilen yavaş TSMOM, funding) havuz SON mühründen ÖNCE kodlanır; Fable'ın ana eleştirisi short/koruma
  eksikliği olduğundan eklemeden mühürlemek tasarımın amacını boşa çıkarır. Rejim bindirmesi v2'de yok (2.8).
- 2026-11-09: v2 ÖN KAYIT donduruldu: sonuclar/evren/ON_KAYIT_V2.md sha256 13f17f53fe79c8c9c0063cc090f1cc57ee573355c500091ab91133802a567bf3 (Fable yazdı, lider denetledi:
  SERT_LIMITLER/martingale/holdout kuralları korunmuş). Bundan sonra eşik/kural değişikliği yok (0.3 tek tur).
- 2026-11-09 (KULLANICI kararı): Fable'ın v2 önerisi AYNEN uygulanacak (sonuclar/denetim/fable_havuz_secim_2026-11-09.md).
  Holdout v2 setine saklanır; D seçeneği uygulanmaz. Sıra: P0 (ön kayıt v2 → havuz dondurma → kill switch eleme → gün içi
  dolum denetimi) → P1. v2 ön kaydı dondurulmadan v2 koşusu yok; v1 sonucu (0 strateji) resmi kayıt olarak kalır.
- 2026-11-09 (KULLANICI kararı): K5 için Fable'ın D önerisi (resmi sonuç 0 kalır, DSR yalnız rapor, holdout öncesi
  stil başına ≤3 + korelasyon süzgeci, holdout tek sefer) CEPTE bekler, uygulanmadı. Önce strateji havuzu ve seçim mantığı
  baştan değerlendirilip teoride en iyiye yakın hale getirilecek (Fable incelemesi, yalnız öneri; kod değişikliği kararla).
- 2026-11-09 (gece, evren zinciri SONUÇ — ön kayıtlı yöntemle): sağlamlık 58 aday, 0 hata; seçim: iyi 0, iyiye yakın 0.
  Tek sebep K5 (DSR): 58'in 58'i kaldı. K5 hariç tüm WF + K1–K4 + PBO'yu geçen 24 (swing 20, scalp 4) — BİLGİ, liste değil.
  Teşhis: K5 eşiği SR0 her grupta o grubun EN İYİ denemesinden bile yüksek (scalp 15m SR0 yıllık 16.8 / 2483 denemenin en
  iyisi 1.58; swing 1d 3.71 / 3.68). Neden: V, maliyetle batan ayarların geniş Sharpe yayılımından şişiyor (scalp 15m medyan
  −5.9) ve DSR formülü denemeleri sıfır çevresinde gürültü varsayar; ayrıca V limitsiz toplam matrisinden, test edilen seri
  tek-kasa limitli. Yöntem DEĞİŞTİRİLMEDİ; değişiklik sonuç sonrası olur → KULLANICI kararı bekleniyor. Holdout yok.
- 2026-11-09 (KULLANICI kararı): repo PUBLIC kalır (private'ta CI çalışmıyor ve ücretsiz planda ruleset uygulanmıyor).
- 2026-11-09 (akşam, evren zinciri): ham 32.200 görev 0 hata; WF 920 kombinasyon → 38 geçen (swing 32, scalp 5, daytrade 1);
  portföy 19 → 1 geçen (pf__ibs_donus); PBO tüm stil×tf ≤ 0.5 (portföy 0.31, diğerleri ≤ 0.03) → düşürme yok.
  Sağlamlık ilk denemede açık hatayla durdu: `_gunluk_dizi` maliyet_payi sütununu düşürüyordu. Yalnız sütun korundu
  (yöntem/eşik değişmedi; DSR serisi WF net_getiri ile birebir), regresyon testi eklendi, sağlamlık yeniden başlatıldı.
- 2026-11-09: Y-5 (tek-grafik kaldıraç tavanında komisyon payı, ~%0.15) evren zinciri (ham→…→seçim/holdout) BİTENE KADAR
  uygulanmaz: WF ham işlemlerini kullanır, motor zincir ortasında değişirse ham ile sağlamlık koşuları tutarsız olur. Paper etkilenmez
  (portföy motoru zaten komisyon payını içerir).
- 2026-11-09 (KULLANICI kararları): proje main'e birleştirildi (PR #1, #2); repo PUBLIC yapıldı (CI için). Lider: üçüncü taraf
  TradingView betikleri, kaynak PDF metinleri ve dış proje stratejileri (arsiv/.../pine, kaynak, algo-sg/dis_kaynak) git geçmişinin
  tamamından silindi (kullanıcı onaylı force-push; dosyalar yalnız yerelde, .gitignore'da). Sunucu yeni geçmişe reset edildi.
  CI (GitHub Actions) çalışıyor, main ruleset ile korunuyor (PR + yeşil pytest, force-push yok). Pano erişim kontrolü: KULLANICI kararı şimdilik yok (yalnız paper verisi).
- 2026-11-09 (gece, dış denetim turları 2-3 sonrası; canlı para/risk limiti değişmedi):
  (1) Test taşınabilirliği: pandas 2/3 hash farkı giderildi, pf WF veri_dizini, gerçek veri testleri işaretli; requirements pandas<4.
  (2) Y-1: gün sonu kapanışı portföy + paper motorlarına taşındı (30m seanslı veride backtest=portföy=paper birebir). Yeni set paper'a
  bu düzeltme olmadan alınamazdı. (3) Y-2: paper desteklemediği çıkış alanında başlamaz (fail-closed). (4) Y-3: K1c gecikme stresi
  takvim bayrağını kaydırmaz. (5) Y-4: holdout mührü v3 (evren, git commit, 14 ortak modül). (6) Y-5 (tek-grafik kaldıraç tavanı
  komisyonsuz, ~%0.15 fazla) ham tarama BİTİNCE düzeltilecek — tarama ortasında motor davranışı değiştirilmez.
  Kullanıcıya sorulacak: main'e birleştirme + dal koruması, CI kurulumu, pano erişim kontrolü.
- 2026-11-09: Güncelleme 8 uygulandı. Lider kararları: sonuclar/kilit/set.csv ve final beklenti aralıkları ESKİ boyutla üretilmiş tarihsel
  kayıt olarak kalır (yeniden üretilmez; testi eski kurala göre doğrular). Portföy toplam %5 stop riski fiyat riski olarak kalır.
- 2026-11-09 (KULLANICI onayı, lider önerisi): (1) işlem başı %1 risk MALİYET DAHİL (stop kayması + 2 komisyon) — backtest, evren oynatma,
  portföy ve paper motorunda tutarlı; ham tarama etkilenmez (r tanımı aynı), WF bu kuralla koşar (ON_KAYIT Güncelleme 8).
  (2) Paper TradFi funding ödenir ama ayrı alanda tutulur; backtest beklentisine uyum karşılaştırmaları TradFi funding hariç yapılır.
- 2026-11-09 (KULLANICI): sunucudaki paper eski 7'li setle yalnız 'deneme sürüşü' (altyapı izleme) olarak çalışır; sonuçlarına bakılmaz.
  Evren testi + seçim bitince yeni setle sıfırdan başlatılır. Öncelik: Fable denetim düzeltmeleri ve strateji testleri.
- 2026-11-08 (KULLANICI kararı): BIST projeden TAMAMEN çıkarıldı (karar 27 evreni değişti: 48 -> 35 = 13 kripto + 17 ABD hissesi + 5 emtia;
  scalp da bu 35'te). Gerekçe: canlı işlem yolu yok, açığa satış/ödünç maliyeti ve TRY enflasyonu gerçekçi modellenemiyor. ON_KAYIT Güncelleme 7.
  İleride BIST istenirse ayrı test (yalnız long, USD bazlı, gerçek maliyet) kurulur. Tüm stillerin WF'si 35 evrenle yeniden hesaplanır.
- 2026-11-08: ON_KAYIT Güncelleme 6 uygulandı. Aşama sırası artık: ham → wf → (olcut: BIST'siz genişlik yeniden değerlendirme) → pbo → sağlamlık → seçim → holdout.
  Holdout mührü sürüm 2 (wf/sağlamlık/pbo + strateji kodu/kart hash'leri; holdout başlayınca önceki aşamalar yazamaz). K2 tutma süresi mum konumundan.
- 2026-11-08 (KULLANICI kararları, Fable denetimi sonrası; WF sonuçları GÖRÜLDÜKTEN sonra, sağlamlık koşulmadan önce):
  1) DSR/K5: seçenek (a) — N ve V aynı popülasyondan (stil×tf grubunun aday-ayar OOS Sharpe'ları); eski denemeler ayrı 'bilgi DSR'si'; eşik 0.90 aynı.
  2) Kill switch olayı: kapı değil, bilgi sütunu.  3) BIST: yalnız bilgi — geçme kapılarında (kârlı sınıf/enstrüman oranı) sayılmaz, evrende koşar.
  4) İşlem başı %1 riske maliyet katılması: evren testi bittikten sonra ele alınacak.
  Sonuç: kapılar değiştiği için swing/daytrade/scalp/portföy WF aşaması yeni kurallarla yeniden hesaplanır (ham tarama gerekmez, swing hamı korunur);
  daytrade/scalp hamı seans gün sonu düzeltmesinden sonra yeniden taranır. Ayrıntı ON_KAYIT Güncelleme 6.
- 2026-11-08 (KULLANICI kararı, scalp 4 enstrümanda 0/204 sonucunu GÖRDÜKTEN SONRA): scalp stratejileri genel 48 evrende test edilir
  (EVREN_STIL['scalp'] = EVREN_GENEL). Eski sonuç arşivde (sonuclar/evren/2017_gelistirme/arsiv_scalp4/); deneme_kaydi eski 204 denemeyi
  tutar, DSR deneme sayısı ikisini de içerir. Bu sonuç-sonrası bir değişikliktir; raporda böyle işaretlenir.
- 2026-11-08 (KULLANICI talimatı): Fable denetimi bitince bulgular Opus tarafından düzeltilir; işler sırayla, durmadan 2026-11-09 13:59 TSİ'ye
  kadar sürdürülür; kullanım limiti dolarsa yenilenince kendiliğinden devam edilir.
- 2026-11-08: Evren ön sonuçları (WF): swing 380'de 44, daytrade 336'da 5 (hepsi 30m), scalp 204'te 0 geçen. Portföy aşaması başlatıldı.
  sağlamlık/pbo/seçim/holdout, Fable denetiminin araştırma bulguları DOĞRULANANA kadar başlatılmaz (holdout tek seferlik; denetimde
  DSR kapısı ve holdout mühür kapsamı hakkında doğrulanmamış bulgular var).
- 2026-11-08: Fable 5.1 bağımsız denetimi YARIDA durduruldu (kullanıcı isteği; sonraki oturumda devam). 7 boyuttan 6'sı bitti
  (araştırma, backtest, risk, paper, ops, pano: 40 HAM bulgu, DOĞRULANMADI) -> sonuclar/denetim/fable_ham_bulgular_2026-11-08.json.
  Kalan: test-kalite boyutu, her bulguya bağımsız çürütme, sentez+öneriler. Betik: sonuclar/denetim/fable_denetim_betigi.js.
  Ham bulgular doğrulanmadan kullanıcıya sunulmaz / koda uygulanmaz.
- 2026-11-08 (KULLANICI kararı): mevduat kıyası yıllık %30 bileşik (stratejiler/kiyas_ayar.json); yoğunlaşma uyarısı: tek sembol açık stop
  riskinin %40'ından fazlası → panoda uyarı (yalnız uyarı, SERT_LIMITLER'e dokunmaz); sunucuya günlük DK_SPX güncellemesi (1l3a-spx.timer, 22:30 UTC).
  Lider: paper canlı yolu kıyas/güven okumasına artık tohum dizinini veriyor (önce /opt/1l3a/veri/mumlar'a bakıyordu, sunucuda yanlıştı).
- 2026-11-08: Pano öncelik 6 (karne/koç/çekmece) onaylandı: karne 'kalite' ekseninde PF ≥ 1.2 (ON_KAYIT) eşiği kalır;
  koç örnek sınırları (kova ≥ 5, tutma süresi grup başı ≥ 10) ve aile içi Bonferroni yeterli; tek genel puan yok.
  Pano backtest görünümü tarayıcıda (Chromium) tüm sekmelerle açıldı, JS hatası yok.
- 2026-11-08 (kullanıcı): Pano karne/rapor eşikleri eski panonunkiler (%10 DD, PSR>%95) değil, projenin kendi kurallarıyla
  (ON_KAYIT geçme ölçütleri, beklenti aralıkları). Günlük K/Z ve dönemsel getiri gün kesimi Türkiye saati (00:00 TSİ).
  Pano öncelik 1 (motor yazıcı paketi) onaylandı, başladı. ML panoya filtre olarak eklenmez; ayrı ön kayıtlı deney
  (meta-etiket, gölge mod) olarak evren testi sonrası konuşulacak.
- 2026-11-08: Evren testi kullanıcı onayıyla ("1 tamam") parça parça koşulur: swing ham+wf → ön sonuç → daytrade
  ham+wf → scalp ham+wf → portföy → sağlamlık/pbo/seçim/holdout HEPSİ BİRLİKTE en sonda. Sebep: DSR deneme sayısı
  tüm stillerin toplamıyla hesaplanmalı; swing'e erken sağlamlık koşmak sayıyı küçültüp kapıyı gevşetirdi.
  DK_WTI 5m 2017-2019 indirilemedi → scalp'te WTI 2020'den başlar.
- 2026-11-07: Portföy sağlamlık paketi eklenir (rastgele ağırlık/sepet kıyası, blok bootstrap Sharpe alt sınırı,
  maliyet ×2, parametre komşuluğu); karar 24'ten kaldırılan yoğunlaşma ölçütünün yerini alır.
- 2026-11-07: Veri kaynağı sabitlendi: DK_ sembollerinde tf ≥ 1h için her zaman 1h dosyası (dakikalık indirme sürerken
  kaynak kayıyordu; 5m'de eksik günler var). k3_dk ve DK içeren portföy koşuları yeni etiketle (v2) yeniden koşulur.
- 2026-11-07: Portföy sonuçları: kripto 5/15 karar 24, sağlamlıkta yalnız pf__kesit_ls (sınırda, p=0.03); hepsi evreni
  1/15 (ibs_donus), sağlamlıkta rastgele kıyastan kaldı. Karar: "hepsi" evreninde OOS 2009'dan başlıyor (yalnız altın
  varken) → portföy koşularında başlangıç, evrendeki sembollerin çoğunun (≥ %75) verisi olduğu tarihe çekilir; v3 ile tekrar.
  v3 sonucu (OOS 2019-01 → 2025-06; emtia 2014 →): sağlam = hepsi: pf__rotasyon (Sharpe 1.12), pf__btc_hedge (0.92);
  hisse_emtia: pf__kanarya (1.60, maliyet×2'de 1.55). Al-tut Sharpe ~1.1 (Mag7 boğası); yalnız kanarya belirgin üstün.

- 2026-11-07: TradFi tek-grafik (sabit veri, k3_dk_v2): WF 198/2877 geçti, sağlamlık 36. Kripto 15. Final tek-grafik
  aday havuzu 51 satır / 34 strateji (`sonuclar/final_aday_havuzu_tek_grafik.csv`); hepsi swing, tek daytrade
  (dis__dual-thrust ETH 1h/30m), scalp 0 (TradFi dakikalık veri bekleniyor). Çok sembolde sağlam: fraktal-alligator (5 hisse),
  rsi-gauss-velocity (3 hisse). Emtiada sağlam tek-grafik yok.
- 2026-11-07: Hisse kısa TF (15m/30m scalp + 30m/1h daytrade, k3_hisse_kisa): WF 27/1358 geçti, sağlamlık 0.
  Karar (karar 11 + 26): **scalp ajanı kapatıldı** (kripto 0, hisse 0 sağlam); emtia dakikalık veri tamamlanınca
  bir kez daha denenir, sağlam çıkarsa yeniden açılır. Daytrade'de tek aday dis__dual-thrust ETH 30m.
- 2026-11-07: **Katman 4 kilitli dönem testi** (ön kayıt `sonuclar/kilit/ON_KAYIT.md`, kilit bir kez açıldı, günlük
  `sonuclar/kilit_acilis.jsonl`; ayarlar kilit açılmadan seçildi). Set ölçütü GEÇTİ: tek-grafik kolu +%17.8 / Sharpe 1.21 /
  düşüş %8.0; portföy kolu −%2.8; 50/50 harman +%7.2 / Sharpe 0.85 / düşüş %4.2. A'da 7'nin 3'ü geçti (cci-esik SOL,
  dual-thrust ETH, kesit_ls). Ayırt edicilik tek-grafikte YOK (C medyan R −0.107 < D −0.054; WF PF ile kilitli PF
  Spearman −0.09). Kilitli dönem artık kullanılmış sayılır. Karar (ön kayıt gereği): set değiştirilmeden Aşama 3 (Pano)
  ve Aşama 4 (paper trading) başlar; seçim yönteminin öngörü gücü zayıf olduğu için paper trading asıl bağımsız sınavdır,
  canlıya geçiş paper sonucu + kullanıcı onayı olmadan konuşulmaz.
- 2026-11-07: Kullanıcı: kilitli yılda geçen 14'lük ayrı izleme listesi istenmedi, final 7 ile devam. Lider kararları:
  (1) paper'da ağırlıklar kilit testindeki set oynatmasıyla aynı (tek-grafik %1/işlem, portföy %5 bütçe, kollar 50/50),
  pf__rotasyon dahil — sert limitler (günlük %3, kill %20) paper'da da durdurucu; (2) paper ayarları WF kuralının
  ileriye devamı: son eğitim penceresi verinin sonuna kadar, yenileme swing/portföy 180 gün, daytrade 90 gün;
  (3) Aşama 2 kapanışı (final_set.json, beklenti aralıkları) ve Aşama 3 Pano v1 başlatıldı.
- 2026-11-07: **Aşama 2 kapandı, Aşama 3 Pano v1 hazır.** `stratejiler/final_set.json` (7), `sonuclar/final/`
  (guncel_ayarlar, beklenti_araliklari, OZET.md, pano_ornek.html), `motor/canli/` (durum sözleşmesi, backtest_durum, pano).
  Güncel ayar (veri sonuna kadar eğitim) 7'nin 4'ünde kilit testindekinden farklı (dual-thrust, fraktal-alligator,
  rotasyon, kesit_ls). Set 8 hafta beklenti: net %5/%50/%95 = −2.6/+2.0/+10.4, düşüş %95 = 3.9 → alarm eşiği.
  Kilit günlüğünde ajanın veri kontrolü sırasında yazdığı 6 "deneme" satırı var (silinmedi: günlük ekle-yalnız).
  **Aşama 4 için zorunlu notlar:** (a) portföy kolu kilit testinde limit_modu="olc" ile koştu — paper'da limitler
  uygulanır olmalı; (b) iki kolun ortak hesap limit kontrolü yazılmalı; (c) bayatlık eşiğine seans takvimi
  (hisse hafta sonu); (d) portföy kolu ortalamasında hafta sonu paydası tutarsızlığı (set.csv mean vs beklenti 0/3) tekleştirilmeli.

- 2026-11-07: Son 1 ay açık kaynak araştırması (Haiku oturumu, kullanıcı onaylı 4 aday) test edildi: hiçbiri final havuza
  girmedi. dis__son1ay-donchian-adx BTC 4h WF+karar 13+sağlamlık geçti (PF 1.93) ama kilitli dönemde (bilgi) PF 0.94;
  kanal 20/10 işlem sayısı yetersiz; TrendRider (OOS 15 gün kısa, al-tut altı) ve E014 makro (düşüş %29.9) karar 24'ten kaldı.
  Yeni veri: DK_SPX, DK_UST (1h). Donchian-ADX BTC 4h yedek gözlem listesinde, sette değil.

- 2026-11-07: **Aşama 4 paper motoru kodu hazır** (`motor/canli/paper*.py`, `deploy/KURULUM.md`). Tekrar modu ↔ backtest
  kilitli dönemde 7/7 stratejide işlem/fiyat/miktar/PnL birebir (NVDA'da 5 çıkışın yalnız zaman etiketi farklı: backtest
  seanslı 4h'ta medyan aralık kullanıyor). Limitler UYGULANIR (tek hesap, iki kol ortak). Açık: fapi.binance.com bu
  konteynerden 451 (konum kısıtı) → canlı WS/exchangeInfo ilk kez sunucuda doğrulanacak; TradFi perp 7/24 vs seanslı
  araştırma verisi (seans süzgeci varsayımı); TradFi funding backtestte yoktu.

- 2026-11-07: GTAA 10 aylık SMA (SPY/EFA/IEF/VNQ/DBC, Haiku araştırma önerisi) paper'a ALINMADI: varlıklar Binance TradFi'de
  yok, SPY'a üstünlük bootstrap'ta kanıtsız, boru hattımızdan geçmedi. Yeniden değerlendirme şartı: Binance vekilleriyle
  karar 24 + sağlamlık, sonra ≥6 ay paper (DD ≤ %15, beklenti aralığında).
- 2026-11-07: Paper sunucusu açıldı (DigitalOcean Frankfurt, Ubuntu 24.04, 2 GB); fapi.binance.com erişimi var ({}),
  repo salt-okur deploy key ile çekildi, veri indiriliyor.

- 2026-11-07 16:12 UTC: **Aşama 4 paper trading BAŞLADI** (DigitalOcean FRA1, servis 1l3a-paper, sanal 10.000 USD, 7 strateji,
  güncel ayarlar). Binance TradFi sözleşmeleri exchangeInfo'da "TRADIFI_PERPETUAL" türünde → kod düzeltildi (cab5d2e), durum sıfırlanıp
  yeniden başlatıldı. Sağlık: tüm semboller bayat değil. Süre ≥ 8 hafta (en erken değerlendirme 2027-01-02). Telegram henüz kapalı;
  pano yalnız sunucuda (telefona yayın yolu açık iş).

- 2026-11-07: Haiku Ar-Ge alt projesi (elenen 120 strateji × XU30/SPX/XAUUSD/UKOIL/BTCUSDT) kapandı: WF'de 3 geçen
  (altın 1d swing, XU30 1h daytrade ×2), hepsi sağlamlıktan kaldı; ön kayıtlı 12 geliştirme varyantı da kaldı → kazanan yok.
  Kayıt: dal claude/haiku-arge-5-enstruman, sonuclar/haiku_arge/KAPANIS.md. Deneme sayısı 787 — DSR hesabında toplam
  deneme sayısına eklenmeli.

- 2026-11-07 17:12 UTC: Paper kurulumu tamam. Düzeltmeler: Binance kline akışı `/market/stream` yolunda (eski `/stream` veri
  göndermiyor; 60a76b3); Telegram yeni bot + kullanıcı dostu HTML mesajlar (b2abb50); pano Cloudflare Workers'ta
  (adres repoda tutulmaz; 15 dk), masaüstü/mobil tasarım (2146654). Sunucu güncelleme: `git pull` (root,
  deploy key), motor durumu korunur. Açık soru: günlük Telegram özeti saati (şu an 00:10 UTC = 03:10 TSİ).

- 2026-11-07: **Karar 27 (kullanıcı):** tek sembol–strateji ikilileri (SOL'de CCI, NVDA'da Fraktal…) istenmiyor; final set
  paper'dan kaldırılır. Yeni hedef: **evren stratejileri** — tek parametre setiyle 13 enstrümanın hepsinde çalışan, sinyal
  nerede çıkarsa orada işleme giren stratejiler; ajan (stil) başına ≤ 3. Ön kayıt: `sonuclar/evren/ON_KAYIT.md`.
  Evren (kullanıcı, aynı gün): daytrade/swing = emtia 5 (altın, gümüş, petrol, bakır, doğalgaz) + S&P 500'de piyasa değeri
  > 500 milyar $ hisseler (bugün 18) + stabil hariç piyasa değeri > 5 milyar $ kriptolar (bugün 15, Binance perp'i olanlar);
  üyelik her gün kontrol. Scalp = yalnız SPX, XAUUSD, petrol, BTCUSDT.
  BIST eklendi (kullanıcı): daytrade/swing'e AKBNK, ASELS, ASTOR, BIMAS, EKGYO, EREGL, FROTO, KCHOL, SISE, TCELL, THYAO,
  TRALT, TUPRS; scalp'e XU030 (scalp evreni 5). BIST Binance'te yok → canlı için ayrı aracı kurum gerekir.
  Test dönemi (kullanıcı): 2020-01-01 → bugün, kilit ayrımı yok (WF örneklem-dışı sürer; bağımsız sınav paper). Tüm stratejiler
  kodlama bitince evrende test edilir; tüm veri 2020→bugün indirilir.

- 2026-11-07: Kullanıcı eski repoları geri yükledi ve **tüm PDF'lerden ve kodlardan strateji alınmasını** istedi (önceki
  "PDF alma" kısıtı kullanıcı kararıyla kalktı; PDF/metinler yine repoya girmez, yalnız kartlar/envanter). 11 repo klonlandı;
  130 tekil PDF (40'ı Aşama 0'da işlenmiş, 90 yeni: daytrade 25, swing 20, algo 17, scalp 9, diğer kitap 6, rapor/liste 13).
  8 ajan: 5 kart çıkarma, rapor PDF envanteri, eski repo kod envanteri, eski panoların incelenip panoya eklenmesi.
  Sonuç: 308 yeni kart (toplam 745), rapor envanteri 314 strateji (65 yeni, 54 yasak DCA/grid), kod envanteri 398 satır (44 yeni).
  Repolar silinmeden önce son kontrol: 130 PDF'in tamamı envanterde (eksik görünen 9'u başka repodaki aynı dosya, md5 eşit).
  Kodu arşivlenmemiş 6 repo `arsiv/`e alındı (day-trade-sg, scalp-sg, codex-algo, sg-arge-, sg-pano, strateji-test-pano;
  PDF/metinler/veri hariç). Taranmış `pano ekranlar.pdf` sayfaları `arsiv/sg-algo-proje/pano_ekranlar/` (kullanıcının kendi
  ekranları). Panoda olmayan bölümler (pano fazı işi): Karne (radar), Koç/dersler + "ne olurdu" simülatörü, Öğrenme
  kaydı, aylık Rapor sayfası, Dönemsel getiri tablosu, Risk (varlık yoğunlaşması, korelasyon, kaldıraç dışı düşüş).
- 2026-11-07 (gece) DEVAM NOKTASI: kodlandı d10a-e (89) + d11f/g/i (52) → kayıtta ~430 strateji; htf seanslı piyasa düzeltmesi
  (e048f90). GitHub 50 repo tarandı (github_g1..g7, 1198 satır) → kodlama_kuyrugu_github.csv. 5 kitap tam okundu (+65 kart, 810).
  Veri indirildi (ABBV yok; BIST 1h yalnız 2023-12'den, XU030 5m yok → scalp XU030 ve BIST daytrade kısa dönem; kullanıcıya soruldu).
  AÇIK İŞLER: d11h (daytrade 20 aile) ve d11j (mevcut sınıflara mod; ma_kesisim, supertrend_psar, bant_donus, macd_sinyal,
  rsi_asiri_donus değişiyor — varsayılan değişmezlik kontrolü şart) ajanları; tam okuma kartlarının eşleştirmesi
  (kodlama_kuyrugu_tam_okuma.csv); çıkış modülleri listesi (basamaklı stop, cooldown, RSI çıkış, azalan ROI, Elder güvenli bölge,
  Brooks/Farley yönetim kartları). Sonra: kalan yenileri kodla → wf_evren tam koşu (2020→bugün).
- 2026-11-07: **Kullanıcı kararı (BIST verisi):** elinde kaynak yok; "çekebiliyorsan çek yoksa olanla bakalım". Ücretsiz
  2020+ BIST gün içi kaynağı yok (Yahoo 1h ~2 yıl/5m 60 gün; İş Yatırım yalnız günlük; Stooq/Investing bu ağdan erişilemiyor ve
  geçmişleri de kısa). Karar: BIST swing 1d ile 2020→bugün; BIST daytrade 1h 2023-12→bugün (kısa dönem, raporda ayrı işaretlenir);
  XU030 scalp evrenden çıkar (scalp 4 enstrüman: DK_SPX, DK_XAU, DK_WTI, BTCUSDT). ABBV veri yok, ABD listesinden çıkar.
- 2026-11-07: Çıkış modülleri eklendi (CikisAyarlari: stop_basamaklari, azalan_roi, geri_cekilme_yuzde, kar_rsi_esikleri,
  elder_guvenli_bolge_k, agresif_iz_*, stop_sonrasi_bekleme_mum; hepsi varsayılan kapalı, 100 strateji öncesi/sonrası birebir).
  **AÇIK İŞ (yeni paper setinden önce şart):** motor/canli/paper_motor.py CikisAyarlari'nın gelişmiş alanlarını (atr_iz_suren_k,
  basabas_r_esigi dahil) uygulamıyor; paper'a alınacak stratejide bu alanlar varsa backtest ile paper farklı davranır.
- 2026-11-08: **STRATEJİLER HAZIR** (kullanıcı "hazır olunca bekle, konuşalım" dedi; evren testi kullanıcıyla konuşmadan başlamaz).
  460 tek grafik strateji (swing 190, daytrade 168, scalp 102) + 19 portföy sınıfı; ~120 ek ayar/mod kaydı; 7 çıkış modülü.
  Tüm test paketi geçiyor (3568). Sıradaki: kullanıcıyla konuşma → wf_evren tam koşu (2020→bugün, BIST/XU030 kararlarıyla).
- 2026-11-08: Kullanıcı ON_KAYIT Güncelleme 5'i seçti (holdout son 12 ay, DSR/PBO kapı, rastgele giriş kapı, enstrüman bazlı
  maliyet+stres, 2017'den veri). wf_evren uygulandı (b876c1d), 2017 verisi indi (kripto spot vekil 2017-08'den; DK 1h 2017;
  SPX/WTI 5m 2017-2019 indirmesi arka planda). Tam koşu KULLANICI "başla" DEYİNCE: --donem 2017_gelistirme ile
  ham → wf → portfoy → saglamlik → pbo → secim → holdout (tahmin: ham ~35 saat/4 çekirdek, toplam ~2 gün+).
- 2026-11-08: Pano öncelik 2 ve 3 (motor tarafı) yazıldı: `dersler.json` (canlı ↔ backtest beklentisi; binom + Welch t) ve `aylik_rapor.json` (TSİ ay özeti + paper kabul listesi),
  panoda DERSLER ve RAPOR sekmeleri. Kabul ölçütleri bu dosyadaki kurallardan: süre ≥ 8 hafta (en erken 2027-01-02), set 8 hf beklenti aralığı, sert limit ihlali yok. **Kullanıcı kararı (2026-11-08, tek kayıt):** (1) kabul için set toplamında ≥ 30 kapanan işlem (geçti/kaldı); (2) Dersler'de "altında" çıkan strateji kabulü bozmaz ama canlıya geçmez
  (`canliya_uygun` false + neden), "örnek az" da canlıya uygun sayılmaz (ayrı neden); (3) günlük %3 kayıp limitinin tetiklenmesi ihlal sayılmaz (sayı bilgi olarak raporda), kill switch / kaldıraç /
  stop riski aşımı ihlal; (4) toplam kesinti ≤ 24 saat, aşarsa kabul reddedilmez, en erken değerlendirme (başlangıç + 56 gün) aşan kesinti kadar kayar — kesinti `paper_state` olay kayıtlarından
  ölçülür (veri_bosluk aralığı, ws_koptu süresi), süresi kayıtta olmayan olay varsa null + neden; Dersler eşikleri (asgari 30 işlem, alfa 0.05) onaylandı, "geçici" etiketi kalktı. Açık soru: yalnız
  strateji bazlı alarmın kabulde aranıp aranmayacağı.
- 2026-11-08: Pano öncelik 4 (motor tarafı) yazıldı: `veri_guveni.json` (sembol başına son mum, bayatlık, son 30 günde eksik mum/boşluk, kaynak), `butunluk.json` (dayanılan dosyaların sha256 ↔ kayıtlı değer
  `sonuclar/final/butunluk_kayit.json`, kod sürümü git commit), `islemler.jsonl`'e `ayar_surumu` (parametre seti hash'i + set dosyası) ve `giris_gerekcesi` (sinyal anındaki genel şablon; stratejiler koşul metni üretmiyor),
  kalp atışı (`durum/kalp_atisi.json` + `paper_state.json`; yeniden başlatma kesintisi süresiyle olaya yazılır, `kesinti_olc` okur). Panoda SAĞLIK ve İŞLEMLER sekmelerinde kartlar. Kayıt dosyası ayar yenilemesinde
  (guncel_ayarlar.csv değişince) "uyuşmuyor" gösterir; yeni özeti kaydetmek kullanıcı onayıyladır (`python -m motor.canli.guven --kaydet`). Ayrıntı: `motor/canli/DURUM_SOZLESMESI.md`.
- 2026-11-08: Pano öncelik 5 (motor tarafı) yazıldı: `koni.json` (paper başlangıcında sabit Monte Carlo konisi: set OOS günlük getirisi `sonuclar/final/beklenti_koni_havuzu.csv`, beklenti_araliklari ile aynı blok bootstrap, 112 gün, tohum 42, havuz sha256'ya bağlı, lookahead yok), `kiyas.json` (paper ↔ BTC / DK_SPX al-tut / mevduat),
  `korelasyon.json` (≥30 ortak gün yoksa null + neden), `yogunlasma.json` (sınıf/sembol brüt ve açık risk payı). Panoda ÖZET (koni, kıyas) ve RİSK (korelasyon, yoğunlaşma) kartları. **Kullanıcıya sorulacak:** (1) mevduat yıllık oranı (`stratejiler/kiyas_ayar.json`, şimdi null → çizgi yok);
  (2) sembol/sınıf bazında yoğunlaşma eşiği isteniyor mu (şimdi tanımlı eşik yok, yalnız bilgi); (3) DK_SPX arşivi sunucuda güncellenmiyorsa S&P kıyası bayat kalır: güncel S&P kaynağı gerekir. Ayrıntı: `motor/canli/DURUM_SOZLESMESI.md`.
- 2026-11-08: Pano öncelik 6 (motor tarafı) yazıldı: `karne.json` (strateji ve set başına 6 eksen 0-100: getiri, risk/düşüş, kâr kalitesi [PF], isabet, beklentiye uyum, veri/çalışma sağlığı; eşikler projenin kendi kuralları: beklenti aralığı alarm eşikleri, ON_KAYIT PF ≥ 1.2, Dersler alfa 0.05 ve 30 işlem, paper kabul kararları [kesinti 24 sa, sert limit]; eski %10 DD / PSR eşikleri yok; tek genel puan bilerek yok; örnek az ise null + neden),
  `koc.json` (kurallı tespitler, LLM yok: stop sıklığı, çıkış nedeni payı, ardışık kayıp serisi, tutma süresi, saat/gün/sembol kayıp yoğunluğu, Dersler "altında"/set alarmı; dayanak sayılar + p + Bonferroni; seviye yalnız incele / izle / beklenti dışı; risk büyütme/ekleme/Kelly ASLA önermez, geriye dönük ayar seçimi önermez),
  işlem satırlarına MFE/MAE (paper motorunda işlem boyunca en iyi/en kötü fiyat; çıkış mumunun uçları sayılmaz, lookahead yok; gerçek değerin alt sınırı) ve panoda İŞLEMLER satırına tıklayınca açılan çekmece. Ayrıntı: `motor/canli/DURUM_SOZLESMESI.md`.
  **Kullanıcıya sorulacak:** (1) karnede PF ≥ 1.2 (ON_KAYIT evren-OOS ölçütü) paper "kalite" eşiği olarak uygun mu, yoksa bilgi mi kalsın; (2) koçun örnek sınırları: saat/gün/sembol kovasında ≥ 5 işlem, tutma süresinde her grupta ≥ 10 (30 işlem Dersler'den); (3) karnede tek "genel puan" istenmiyor (Goodhart): yine de istenirse formül ve ağırlık sizin kararınız;
  (4) koçun çoklu test düzeltmesi yalnız aynı kural ailesi/kapsam içinde (kapsamlar arası yok): daha sıkısı mı isteniyor.
- 2026-11-11: v3 araştırma kararları (lider):
  - Paper başlangıç bayat dolumu: 2026-11-10 12:27 başlatıldı; 14 günlük pozisyon 03:00 açılışından doldu (`islem_baslangic` canlıda verilmiyor). Kullanıcı: pano/pozisyonlar böyle kalsın. 2026-12-08 sadakat kontrolünde bu 14 giriş hariç tutulacak; `islem_baslangic` yeni kadro başlarken verilecek.
  - Test bütçesi: yalnız 10 aile temsilcisi (çoklu test); aynı ailenin diğer kodlu varyantlarına yalnız temsilci geçerse bakılır. Testte elenen v2 stratejileri canlandırılmaz (aşırı uyum).
  - Tur 6: veri_yok 514 adayın %79'u bizim açamadığımız piyasada işlem yapıyor; veri ekleyerek kurtarma beklentisi düşük. Yalnız FOMC takvimi eklendi (`veri/takvim/fomc.csv`, tur 7).
  - Kaynağa uyum düzeltmeleri (tur 4/5 → Codex parti 4, PR #32): noise-area makaleye göre; Donchian ansambl portföy stratejisi olarak yeniden (eski tek grafik sürüm "kaynağa aykırı"); funding-7g günlük ödeme TOPLAMI (`funding_gunluk_toplam`, eski sütun değişmedi), evren 13 coin; FIP min_sembol 5; vol-yönetimli-long portföy stratejisi (sabit %20 hedef, geleceğe bakan c yok, 1/n eşit sermaye: ana oturum düzeltmesi).
  - Kaynakta olmayan ATR stopları ön kayıtta "bizim eklememiz" diye yazılacak; stopsuz koşu da raporlanacak. saatlik-aşırı-tepki (De Nicola) birincil metin okunana dek bekletilir.
  - KULLANICI KARARI (canlı): 2027'den önce canlıya geçilecek (bu proje + ayrı copy trade projesi); kullanıcı riskleri ve kanıt eksikliğini kabul etti, 3-12 ay beklenmeyecek. İstatistiksel kanıt (84 gün / 365 gün sepet testi) canlı şartı DEĞİL, bilgi. Canlı şartları (güvenlik): sadakat kontrolü (v2: 2026-12-08), SERT_LIMITLER, B18, para çekme izni kapalı + IP kısıtlı API anahtarı, küçük bütçe. Denetçiler bu kararı bilir, süre şartı dayatmaz. Ayrıntı: sonuclar/v3/ON_KAYIT_V3.md 4.5.
  - KULLANICI KARARI (canlı boyut, Fable B "dengeli", 2026-11-11): YALNIZ canlı/testnet yürütücüde CANLI_LIMITLER (strateji kasası başına): işlem başı stopta kayıp ≤ %3, teminat ≤ %50, pozisyon ≤ 1,5×kasa, toplam açık stop riski ≤ %6, brüt ≤ 1,5x, günlük −%6 yeni giriş yok, strateji kill −%30 (zirveden), hesap toplamı kill −%20; izole, stop ≤ %15 → ≤3x, > %15 → ≤2x; asgari emir altı işlem atlanır. SERT_LIMITLER (paper/backtest/araştırma) DEĞİŞMEDİ. Kullanıcı hedefi: scalp/gün içi/swing, her türden 2-3, toplam 6-9 strateji; canlı kasa ~1.000 USD, alt hesaplar açık, Futures açık. Canlıdan önce işlem listesi yeni boyutla yeniden oynatılır (sonuclar/canli/BOYUT_RAPORU.md).
  - KULLANICI KARARI (kasa, 2026-11-11): ilk etapta toplam 1.000 USD'nin üstüne çıkılmaz; asgari emir tutarı yüzünden atlanan sinyaller (~%34, temkinli tabloyla) kabul; güven gelirse kasa artırılır. v3 eleme sonucu 0/9 (sonuclar/v3/ELEME_RAPORU.md); canlı aday havuzu v2 paper'ındaki stratejiler (jt-awesome ve voltarget yeniden oynatmada −%30 kill'e değdi: listeye alınmaması önerildi).
  - Sıradaki: Codex parti 5 (pre-FOMC), Sonnet tur 8 (kod-kaynak çapraz kontrolü), ana oturum ON_KAYIT v3 taslağı (`stratejiler/v3_adaylar/on_kayit_girdi.csv` temel) → kullanıcı onayı → test.

## Kullanıcıyı bekleyen kararlar
- ~~Final seçim ve kilitli dönemin bir kez açılması (karar 20)~~ — kullanıcı "aç" dedi (2026-11-07), yapıldı: `sonuclar/kilit/RAPOR.md`.
- Karar 13 eşikleri çoklu test düzeltmesi içermiyor; sağlamlık paketi öneri kapısı ekliyor (son karar kullanıcıda).

## Yol haritası (2026-11-06)
**Aşama 1 — Altyapı ve adaylar**
- 1A Motor: zorunlu çıkış kuralı; günlük limitte açık pozisyon kapatma; kısmi kâr alma; üst zaman dilimi hizalama
  (haftalık/günlük filtre, lookahead'siz); deneme sayısı kaydı; kâr yoğunlaşması ve günlük MTM düşüş metrikleri.
- 1B Veri: XAU + 1–2 aday enstrüman indirme; enstrüman listesinin kesinleşmesi (3–5).
- 1C Adaylar: swing 10 (✅ 9 + MA kesişim) + önceki projelerden 4S kırılım, KGT, S1 (+ yedek B);
  day trade 5–6; scalp (≥15m) 4–5.
- Bitiş: tüm adaylar kodlu, lookahead testli, 1A özellikleri testli.

**Aşama 2 — Test ve seçim**
- Karar 22 evreni (kripto + Mag7 + XAU/WTI/bakır): her aday için walk-forward (OOS seçimde görülmez), karar 13 ölçütleri.
- Geçenler: rejim analizi (boğa/ayı/yatay), parametre duyarlılığı, rastgele giriş karşılaştırması, maliyet ×2 stresi.
- Hedef: canlıda **ajan başına ortalama ~3 strateji** (10 aday bilerek fazla tutuldu, eleme beklenir). Aralarında korelasyon kontrolü.
- TradFi: Dukascopy uzun geçmişiyle tam test (karar 22); Binance TradFi verisi (2025-12+) kilitli dönemde fiyat tutarlılığı kontrolü.
- Bitiş: her stil için onaylı final listesi + beklenti aralıkları (paper'da karşılaştırmak için).

**Aşama 3 — Pano**
- sg-arge `copytrade/canli/pano.py` örnek alınır. İlke: **pano yeni hesap yapmaz**, yalnız motorun yazdığı durum/kayıt
  dosyalarını biçimler (motor ile pano asla farklı sayı göstermez).
- İçerik: ajan/strateji bazında özsermaye, açık pozisyonlar, kapanan işlemler, risk limitleri durumu, backtest
  beklenti aralığına göre konum, sağlık (veri bayatlığı, servis çalışıyor mu). Telefondan okunur; Telegram özetiyle uyumlu.
- Önce Aşama 2 backtest sonuçlarıyla çalışır, sonra paper verisine bağlanır.
- Bitiş: pano paper'ın ilk gününden hazır.

**Aşama 4 — Paper trading**
- DigitalOcean Frankfurt; Binance WS canlı veri; sanal dolum + hesap/risk/Telegram (sg-arge'den uyarlanır, Decimal), pano bağlı.
- Kağıt motoru = backtest motoru doğrulaması (aynı dönem aynı işlemler); dashboard.
- Süre ≥ 8 hafta; sonuç backtest beklenti aralığıyla karşılaştırılır.
- Bitiş: kesintisiz çalışma + sonuçların beklenti aralığında olması.

**Aşama 5 — Lider ajan ve öğrenme** (Aşama 4 sırasında başlar)
- ≥15 dk aralıkla: rejim tespiti, stiller arası sermaye dağılımı, işlem sonrası analiz, haftalık rapor.
- Değişiklik önerisi → walk-forward test → kullanıcı onayı. Canlıda kendini değiştiren kod yok.

**Aşama 6 — Küçük bütçeyle canlı**
- Gerçek emir yürütücü, borsa filtreleri (exchangeInfo), mutabakat; küçük bütçe; sert limitler aynı.

## Yeniden kullanılacak eski kod
Kullanıcının kendi `sselimgenc-oss/sg-arge` reposu (Hyperliquid copy trade, GPLv3):
`canli/hesap.py` (pozisyon/PnL/funding defteri), `canli/yurutucu.py` sanal dolum, `canli/risk.py`,
`canli/telegram.py`, `deploy/*.service` şablonları → Binance'e uyarlanacak.
Düzeltilecek: miktar yuvarlamada `round` yerine aşağı yuvarlama + `Decimal`; Binance rate-limit / WS 24 saat sınırı.

## KAPANIŞ ADAYI CANLI KAPISI — 2026-11-14 (kullanıcı kararı, Fable önerisi)
- Etiketi kapanis_aday / kapanis_aday_ek olan stratejiler (664, 705 vb.) testnet/kuru modda serbest (uyarı logu).
- Gerçek paraya yalnız `canli_ayar` içindeki `kapanis_canli_onay` listesinde strateji bazlı kullanıcı onayı varsa girer; liste boş başlar. CANLI_ONAY=evet şartı aynen.
- Kod tarihi yalnız biçim olarak denetler; "12 hafta paper" ve "<20 işlem → en çok 60 USD" kuralları listeyi dolduran kullanıcının kararına bağlıdır (kod zorlamaz).
- ~~12 hafta paper 2027-02-06'da dolar; Aralık sonu kararı bu şartı kısaltmak demek: karar Aralık sonunda açıkça verilecek.~~ (KALKTI 2026-11-19: süre/işlem şartı yok; onay listesi yalnız kullanıcı kararıyla dolar)
- Hesap kill zirvesi: strateji kümesi değişince sermaye farkı kadar kaydırılır. Düşüşteyken strateji çıkarmak hesap kill'i tetikleyebilir; para eklemek düşüş yüzdesini seyreltir.

## HAFTALIK YENİ STRATEJİ TARAMASI — 2026-11-16 (kullanıcı kararı, Fable önerisi)
- Her hafta yalnız SON 7 GÜNDE yayımlanan stratejiler taranır; haftada en çok 5 kart; yayım tarihi kaynakta doğrulanmalı; mevcut ailelerin benzeri reddedilir.
- Klasör: `stratejiler/v3_adaylar/haftalik/<tarih>/` (kartlar + REDDEDILENLER.txt). v3 TALIMAT kuralları aynen.
- **YENİ HÂLİ (kullanıcı kararı 2026-11-19):** kart yazılır → kodlanabiliyorsa kodlanır; `kart_dogrula` + lookahead testi geçerse `stratejiler/aday_paper_listesi.json`'a eklenir ({id, kart_yolu, eklenme_tarihi}; strateji tanımı karttaki/kayıttaki `uygulama` alanından) → paper'da DOĞRUDAN çalışır (ayrı hesap, 10.000 USD, SERT_LIMITLER, kendi kill'i, Telegram "[1L3A] aday:<kısa ad>"); çeyreklik karar YOK; kullanıcı istediğinde canlıya aday olur. Altyapı: `motor/canli/aday_paper.py` + `deploy/1l3a-aday-paper.service` (oto_guncelle ilk kez kendisi kurar: `OTOMATIK_KURULACAK`); durum `/var/lib/1l3a-paper/durum/adaylar/<kimlik>/`. 10'lu set imzası (fffbc6624416634e) değişmedi.
- ~~Kart yazıldığı gün ayarlar dondurulur (ön kayıt) ve gölge izleme başlar (gerçek para yok); kanıt yalnız kayıt sonrası veridir.~~ (gölge izleme KALKTI 2026-11-19)
- ~~Karar üç ayda bir toplu; karara girme şartı ≥12 hafta izleme ve ≥30 işlem; BH düzeltmesi; geçen → paper → canlı. İlk gerçek karar ~Mayıs 2027.~~ (çeyreklik karar KALKTI 2026-11-19)
- ~~Aralık sonu canlı setine yeni aday girmez.~~ (KALKTI 2026-11-19) ~~Gölge izleme altyapısı henüz yok.~~
- İlk tarama (2026-11-16): 1 kart (Quantpedia korelasyon ivmesi → SPY short hedge, yayım 2026-11-06). KODLANMADI, listeye EKLENMEDİ: verimizde sektör ETF'i (XLB…XLY) yok, SPYUSDT perp geçmişi kısa. Liste şimdilik boş (altyapı hazır).

## CANLI DENETİM (2026-11-17; Fable doğruladı, kullanıcı onayladı)
- Rapor: başka oturumda Fable'sız hazırlandı; Fable kodla doğruladı. B1 (çift giriş emri) KRİTİK; B2 orta-yüksek; B4/B5/B6 orta; B3, B7 düşük; B10 yalnız belge.
- Düzeltme sırası: B1 + EmirReddi→kayıt silme yolu → B4 (süreç içi yeniden deneme) + B5 → testnet → B2 (60 USD denemeden önce) → B3, B6 → B7.
- B2 kararı: risk GERÇEK özsermayeden izlenir; eşik tahsis tavanlı tabandan (ör. günlük: gün başı − şimdi ≥ %6 × min(gün başı, tahsis)); boyutlandırma min(özsermaye, tahsis) kalır. Transfer otomatik işlenene dek para transferi yalnız servis durdurulup yapılır.
- B9 kararı: hisse perp'leri Cuma kapatılmaz; hafta sonu stop tetikleri haftalık canlı-paper raporunda ayrı sayılır, fark büyürse yeniden karar.
- B10 kararı: kod değişmez. Paper (SERT_LIMITLER) ve canlı (CANLI_LIMITLER, 2026-11-11) bilinçli olarak ayrı; karar 14'teki günlük %3 + kapatma YALNIZ paper/backtest için geçerlidir, canlıda 2026-11-11 kuralları geçerlidir.
- Testnet kontrol listesine ek: algo uçlarının "emir yok" kodları (YOK_KODLARI), aynı clientOrderId ile ikinci emir davranışı, zaman aşımı, kill; "gönderildi" kaydı borsada dolu görülünce risk yeniden kontrol edilmiyor (not).
- 2026-11-17 uygulandı (Fable: hepsi ONAY): B1, B2, B3, B4, B5, B6, B7(kısmi).
  Kalanlar: B7 giriş atlama + olay bildirimi GERÇEK PARA (mod canli) öncesi ŞART (testnet için kabul);
  B4 sınırları: açılışta bir stratejinin geçici hatası diğerlerini bekletir, `except Exception` kod hatasını da geçici sayar;
  B2 geçiş günü: diskteki eski gun_basi kırpılmış birimde, ilk gün günlük -%6 eksik çalışabilir (ertesi UTC günü düzelir);
  araclar/canli_oynatma_300.py ve canli_birlesik_oynatma.py eski min(E, tahsis) modelinde (canlı öncesi yeniden koşuda güncellenmeli);
  paper.py tur(): kaynak.guncelle hatasında (B6 yasak penceresi dahil) yürütücü çağrılmaz, yetim pozisyon o süre stopsuz kalabilir.

## CANLI DENETİM-2 (2026-11-18; Fable doğruladı, kullanıcı onayladı: "hepsini yapalım")
- Kararlar (Fable önerisi, kullanıcı kabulü):
  - O3 → (b): paper kill / günlük blok canlıyı durdurmaya devam eder (tek karar kaynağı paper), ama kırmızı olay + Telegram üretilir.
    B10 DÜZELTME: canlı yürütücü CANLI_LIMITLER'e ek olarak gölge paper'ın SERT_LIMITLER çıkış/blokları ile de durur (sıkı yön, bilinçli).
  - O4: mod canli'de açılışta apiRestrictions denetimi; para çekme açık ya da IP kısıtsız anahtarla başlamaz.
  - O9: durum dosyası yok ama dizin doluysa başlamaz; bilerek sıfırlama yalnız strateji bazlı izinle (L3A_SIFIRDAN_IZIN).
  - D2: transfer elle kuralı sürer; yalnız "transfer görüldü" uyarısı eklenir, zirve otomatik kaydırılmaz.
- Sıra: koruma yolu (O1, O2, D1, D8, kanca koruması, O3 olayı) + yanıt sağlamlığı (O5, O8) + açılış (O7, O9) → testnet (O6 sonucuna göre ek düzeltme) → O4, B7, kalan düşükler → 2×60 USD → tam kasa.
- D14 (commit e-postaları): kullanıcı GitHub "e-postayı gizli tut" ayarını açtı (2026-11-18); yalnız yeni commitler gizli, geçmiş yeniden yazılmadı.
- 2026-11-18 uygulandı (Fable: hepsi ONAY, testnete engel yok): O1, O2, O3(b), O4, O5, O7, O8, O9, B7 (giriş atlama + bildirim, CanliKaynak bayrağı), D1–D13, D15–D17.
  Kalan: O6 testnette doğrulanacak; D14 ayrı karar; TradFi 5m dışı tf'de B7 bayrağı yeniden örneklemede düşebilir (doğrulanmadı).
