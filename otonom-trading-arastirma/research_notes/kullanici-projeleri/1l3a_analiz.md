# 1L3A (1 Lider, 3 Ajan Algotrading) — salt okunur analiz

Kaynak: `/home/user/sselimgenc-oss/1l3a-proje` (git deposu, tek commit görünüyor: `2dd2dce`).
Tarih: 2026-11-16. Durum kaynağı: `DURUM.md` (son güncelleme 2026-11-14 gece). Hiçbir kod çalıştırılmadı, içe aktarılmadı; yalnız okundu.
`veri/`, `sonuclar/`, `arsiv/` içeriği okunmadı; yalnız ne olduğu not edildi.

---

## 1. Ne bu proje

**Amaç:** Binance USDⓈ-M vadeli (futures) sözleşmelerinde, kitaplardan ve açık kaynak kaynaklardan kurala dökülmüş stratejileri
çalıştırmak. Üç "ajan" (scalp, day trade, swing) kendi bütçeleriyle çalışır. Bir "lider" katman sonuçları denetler ve
değişiklik **önerir**; onay insanda. Canlıda kendini değiştiren kod yoktur (DURUM.md karar 4).

**Dil ve çatı:** Python 3.13 (CI'da). Çatı yok: düz modüller, `argparse` CLI'ları, `systemd` servisleri.
Bağımlılıklar (`requirements.txt`): pandas, numpy, pyarrow, pymupdf, requests, websockets, pytest.
Strateji çekirdeği kendi yazılmış (`motor/strateji/temel.py` soyut sınıfı; `motor/strateji/cikislar.py` çıkış modülleri).

**Mimari (klasörler):**
- `motor/backtest/` — walk-forward öncesi backtest motoru (Decimal, komisyon/kayma/funding).
- `motor/arastirma/` — tarama, walk-forward, sağlamlık (bootstrap, rastgele giriş, komşu parametre), PBO, DSR, kilitli dönem testi, seçim.
- `motor/portfoy/` — çok sembollü portföy motoru (hedef ağırlık, toplam stop riski ≤ %5).
- `motor/canli/` — paper (sanal dolum) motoru, pano, Telegram, durum yazıcısı, günlük özet, dersler, koç.
- `motor/canli/borsa/` — borsa katmanı: gerçek Binance istemcisi, kuru (sahte borsa), canlı yürütücü.
- `motor/risk/` ve `motor/canli/borsa/canli_limitler.py` — risk kuralları (iki ayrı dosya, bkz. §5 ve §6).
- `motor/veri/` — veri indirme (data.binance.vision, Dukascopy, Yahoo, spot vekil), kilit (`kilit.py`), deposu.
- `stratejiler/` — kart şeması, aile listeleri (`aileler.json`), `dis_ayarlari/*.json` (strateji parametreleri), `canli_ayar.ornek.json`.
- `araclar/` — 35 yardımcı script (kart doğrulama, paper/canlı oynatma, haftalık rapor, risk senaryosu, yeni sembol sınavı).
- `deploy/` — systemd birimleri, env şablonları, Cloudflare yayın betiği, Worker, kurulum notları.
- `testler/` — 165 dosya, yaklaşık 2 200 test fonksiyonu. CI: `.github/workflows/testler.yml`.

**Veri kaynakları:**
- Geçmiş (backtest): `data.binance.vision` arşivi (`motor/veri/indir.py`), spot vekil (`motor/veri/spot_vekil.py`, perp öncesi dönem).
- TradFi (hisse, emtia): Dukascopy (`motor/veri/dukascopy.py`, `DK_` önekli semboller), Yahoo (BIST, `yahoo_bist.py`).
- Paper canlı veri: Binance USDⓈ-M REST (`https://fapi.binance.com`) ve WebSocket (`wss://fstream.binance.com`), `motor/canli/paper_veri.py`.
- Not: Binance API bu bulut makinesinden konum nedeniyle engelliydi (DURUM Aşama 1); arşivde 2026-10-28 tüm sembollerde eksik.

**Borsa bağlantısı ve modlar** (`motor/canli/borsa/`):
- **Piyasa türü:** yalnız USDⓈ-M futures (`/fapi/...`). Spot yalnız geçmiş veri vekili için kullanılıyor.
- **`paper`** (`motor/canli/paper_motor.py`, `paper_v2.py`): gerçek fiyat akışı, sanal dolum. Anahtar gerekmez. Dolum varsayılan kayma modeliyle simüle edilir.
  Servis: `deploy/1l3a-paper.service` çalıştırır `python -m motor.canli.paper --canli ...`. Buradaki `--canli` bayrağı "canlı veriyle paper" anlamına gelir, gerçek emir değildir. Adlandırma kafa karıştırıcı.
- **`kuru`** (`kuru.py`): aynı arayüzü (`BinanceFutures` gibi) bellekte taklit eder; emirler yalnız loglanır, borsaya gönderilmez.
- **`testnet`** (`https://testnet.binancefuture.com`): gerçek API imzası, sahte para. Anahtar gerekir.
- **`canli`** (`https://fapi.binance.com`): gerçek para. `CANLI_ONAY=evet` ortam değişkeni yoksa servis başlamaz (`canli_ayar.py`).
- İmza: HMAC-SHA256 (`binance_futures.py::imzala`). Gizli anahtar loga yazılmaz (`temizle`).
- Kaldıraç ve marj: izole marj, pozisyon modu tek yönlü, sembol başına kaldıraç ayarı (`hazirla()`).

**Mevcut durum (DURUM.md, 2026-11-14 gece itibarıyla):**
- Paper, 2026-11-14 17:57 UTC'de **sıfırdan** başlatıldı (eski durum `durum_eski_20261114_2100` olarak saklandı). Paper ölçümleri bu tarihten sayılır.
- Paper v2: 10 hesap. Panoda görünür 6 strateji ("odak") + 4 gizli ("gizli çalışan"); 10 durdurulmuş strateji arşivde.
- Canlı kasa tavanı ~2000 USD. Kademeli plan: testnet, sonra 2 × 60 USD duman testi, Aralık sonu karar, Ocak'ta tam paylar. Gerçek para henüz yok.
- Bekleyen işler: testnet API anahtarı, Binance alt hesapları, `git pull` + `PANO_SIFRE` sunucuda, algo emir uçlarının testnet'te doğrulanması, 2026-12-08 sadakat kontrolü.

---

## 2. Panel (pano)

**Teknoloji:** Panel bir **üretilen statik HTML dosyası**. Sunucu, framework ya da veritabanı yok.
- Üretici: `motor/canli/pano.py` (2065 satır). Tüm HTML parçaları Python string fonksiyonlarıyla üretilir (`_kutu`, `_tablo`, `_p`, `_sekme_*`).
- Grafikler: elle yazılmış SVG (`_egri`, `_dusus_grafigi`, `_kz_grafigi`, `_radar_svg`, `_mini_egri`). Harici JS kütüphanesi yok (`<script>` yalnız satır 2035'te inline).
- Sekmeler: özet, stratejiler, pozisyonlar, işlemler, risk, sağlık, dersler, rapor. Yardımcı modüller: `koni.py` (olasılık konisi), `kiyas.py` (paper-backtest kıyası), `korelasyon.py`, `yogunlasma.py`, `karne.py`, `koc.py`, `aylik_rapor.py`.
- Tek dosya, telefon uyumlu CSS, bayatlık bandı için küçük JS.

**Veri nasıl gelir:** API yok, veritabanı yok. Panel yalnız motorun yazdığı **JSON/JSONL dosyalarını** okur. Dizin: `/var/lib/1l3a-paper/durum/` (`durum.py::DOSYALAR` ve `EK_DOSYALAR`):
`ozet.json`, `stratejiler.json`, `islemler.jsonl`, `saglik.json`, `ozsermaye_gecmisi.json`, `maruziyet.json`, `maliyet.json`,
`reddedilen.json`, `olaylar.jsonl`, `icgoruler.json`, `dersler.json`, `aylik_rapor.json`, `veri_guveni.json`, `butunluk.json`,
`koni.json`, `kiyas.json`, `korelasyon.json`, `yogunlasma.json`, `karne.json`, `koc.json`.
Yazım: `durum.py::atomik_yaz_metin` (geçici dosya + fsync + `os.replace`), yani okuyucu ya eski ya yeni tam dosyayı görür.

**Dosya ve birimler:**
- `motor/canli/pano.py` — ana üretici (`uret()`, `main()` CLI: `python -m motor.canli.pano --durum DIR --cikti pano.html`).
- `motor/canli/durum.py` — şema ve atomik yazma (en önemli bağımlılık).
- `motor/canli/durum_ek.py`, `paper_durum.py` — ek durum alanları.
- `deploy/1l3a-pano.service` + `deploy/1l3a-pano.timer` — 5 dakikada bir üretim. Çıkış kodu 2 (kritik uyarı) başarı sayılır; 1 (dosya eksik) başarısız.

**Sunma ve güvenlik:**
- **Yerel:** `deploy/1l3a-pano-sunucu.service` — `python -m http.server 8080 --bind 127.0.0.1`. Dışarıya açık değil; SSH tüneli ile bakılır. Kimlik doğrulama yok, yalnız ağ erişim kontrolü.
- **Uzak (telefon):** `deploy/1l3a-pano-yayin.service` + `.timer` (15 dakikada bir) → `deploy/pano_yayinla.sh` → Cloudflare Workers (wrangler). Worker: `deploy/pano_worker.js`.
  - HTTP Basic Auth, kullanıcı `1l3a` sabit, şifre Worker secret'ı `PANO_SIFRE` (en az 16 karakter). Secret yoksa her istek 401 (fail-closed).
  - Sabit zamanlı karşılaştırma (SHA-256 üzerinden XOR), `Cache-Control: private, no-store`, `X-Robots-Tag: noindex`.
  - **Dikkat:** `PANO_KILITSIZ=1` seçeneği şifresiz yayın yapar (2026-11-14 kullanıcı kararı; `pano_yayinla.sh` başlığı). Bizim için bu yolu kullanmayın.

**Bizim freqtrade + SQLite ledger'a uyarlama:**
- Panelin "motor dosyalarını biçimler, hesap yapmaz" ilkesi bizimkiyle uyumlu.
- Zorluk: panel doğrudan `durum.py` JSON şemasına bağlı. Freqtrade REST (`/api/v1/status`, `/profit`, `/trades`, `/balance`, `/performance`) ve SQLite ledger'ı bu şemaya çevirecek bir **köprü** gerekir (bir "yükleyici" + JSON yazıcı). Ya da pano'nun HTML üreticisi kopyalanıp yalnız birkaç sekme tutulur.
- Öneri: Worker + yayın betiği + atomik yazma + SSH tüneli modeli doğrudan alınabilir. HTML üretici kısmı "görünüm kodu" olarak ayrı düşünülmeli; 2065 satırın tamamını taşımak gereksiz (L). Dört sekme (özet, pozisyon, işlem, sağlık) için yeniden yazım (M).
- Freqtrade'in kendi web arayüzü (FreqUI) da mevcut; karşılaştırma için değerlendirilebilir.

---

## 3. Telegram

**Kütüphane:** Yok. `motor/canli/telegram.py` doğrudan `requests` ile `https://api.telegram.org/bot<token>/sendMessage` çağırır, `parse_mode=HTML`, 4096 karakter sınırında satır kesimi, ~1 saniye aralık.
Token ve chat_id yalnız ortam değişkenlerinden (`TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_ID`; systemd `EnvironmentFile`). İkisi yoksa hiçbir şey gönderilmez, bu loglanır.

**Gönderilen mesajlar (giden, tek yönlü):**
- Başlangıç (`baslangic_metni`), işlem açıldı / kapandı (`islem_acildi_metni`, `islem_kapandi_metni`).
- Günlük özet: `ozet_metni` (dünle kıyaslı), gönderim `paper.py:597` — **her gün 00:10 TSİ**, yeniden başlatmada tekrar gitmez. Bizim 21:00 isteğimiz için zamanlama değişmeli.
- Uyarılar: `uyari_metni` (kill switch, veri bayat, uyarı). `Bildirimci` sınıfı aynı türü 30 dakikada bir tekrarlamaz; WebSocket olayları yalnız log.
- Servis hatası: `deploy/1l3a-bildirim@.service` (systemd `OnFailure=`), `python -m motor.canli.telegram --servis-hatasi <birim>`.
- Gizli hesaplar (`paper_v2.py`): kill/hata olayları "[gizli]" önekiyle gider, işlem bildirimi gitmez.

**Komut (gelen) desteği: YOK.** `getUpdates`, webhook ya da `/komut` işleyicisi yok. Bu nedenle **Telegram'dan acil durdurma bu kodda yok**.

**Bizim için:**
- Günlük rapor 21:00: `ozet_metni` mantığı ve biçimi doğrudan uyarlanır (S), yalnız zamanlayıcı ve veri kaynağı değişir.
- Anlık uyarılar: `Bildirimci` (throttle dahil) ve `uyari_metni` (S).
- Acil durdurma: yeni yazılacak (M-L). Gerekenler: chat_id doğrulaması, `getUpdates` uzun-yoklama ya da webhook, idempotent komut, "onay" adımı, durdurmanın borsa tarafında da çalışması (açık emirleri iptal, pozisyon kapatma seçeneği). 1L3A bunu hiç yapmadı; referans olarak kullanılmamalı.

---

## 4. Stratejiler (6 odak) ve örtüşme

Kaynak dosyalar `motor/strateji/dis/` altında. Parametreler `stratejiler/dis_ayarlari/*.json` ve `stratejiler/canli_ayar.ornek.json`.

| Strateji | Dosya | TF / yön | Kural özeti (göstergeler) | Trend-pullback / range-fade ile örtüşme |
|---|---|---|---|---|
| `dis__gauss-stoch-eth` | `d2_gauss.py` | 4h, long | Gauss kanalı üst bant kırılımı, StochRSI %K aşırı bölge süzgeci, ETH için SMA rejimi ve yeşil mum; çıkış üst bant altı | Düşük. Kırılım/trend tarafı. Kanal yeniden test (retest) mantığı pullback'e yakın ama ayrı |
| `dis__hma-atr-rider` | `d1_trend_ma.py:184` | 1d, long | HMA(8) > HMA(9) > HMA(20) rejimi yeni başlarsa giriş; ATR izleyen stop | Orta. Trend takibi, ancak giriş pullback değil rejim başlangıcı |
| `dis__ewo-ema-ofset` | `d11i_github.py:314` | 15m, long (scalp) | EWO% (EMA5−EMA35) negatif + kapanış < EMA8×ofset + RSI14/RSI4 + CTI(20) dip koşulu; ikinci kol Williams %R derin dip; ATR stop | Yüksek. Aşırı satım dip alımı (range-fade long tarafı) |
| `dis__e0v1en` | `d5_ek.py:574` (belge `:82`) | 15m, long (scalp) | RSI(4)<40, RSI(14)>42, kapanış < SMA15×0,973, CTI<0,69, 24s değişim bandı; çıkış stokastik %K>84 ya da CCI>80; stop %6 | Yüksek. Aşırı satım geri dönüşü (range-fade long) |
| `dis__lube` | `d1_osilator.py:130` | (ayar dosyasında) long/short | Aralık oranı "sürtünme" düşükken FIR eğimine göre yön; orta eşikte çıkış | Orta. Sıkışma → kırılım; range-fade değil |
| `dis__ifr2` (odak değil, en yakın) | `d5_ek.py:161` | swing/daytrade, long | RSI(2)<10 ve kapanış, uyarlanmış Ichimoku bulutunun (20/30/120/60) üstünde; çıkış son 2 mumun en yükseğinin üstü; ATR stop eklenmiş | **Çok yüksek.** Yükselen trendde aşırı düşüş = pullback. Bizim trend-pullback fikrine en yakın |

Ek örtüşme (kütüphanede, odak dışı): `swing__ma-geri-cekilme` (MA'ya geri çekilme, trend-pullback), `swing__bant-donus`, `swing__rsi-asiri-donus`, `daytrade__bant-donus`, `daytrade__vwap-donus` (range-fade), `dis__sparta-whb` (yalnız short, Bollinger orta çizgi dönüşü, fade).

**Notlar:** Odak stratejilerin ön kayıtlı holdout'u yalnız gauss ve ewo geçti (DURUM 2026-11-14). Odak listesi "sonuç görüldükten sonra TERCİHLE seçildi" yazıyor: kanıt düzeyi bilerek düşük sayılmalı.

---

## 5. Risk, sağlık, yedekleme, loglama, testler

**Risk (en değerli kısım):**
- `motor/canli/borsa/canli_limitler.py` — canlı yürütücünün tek risk kaynağı, saf Decimal fonksiyonlar. İşlem başı kayıp tavanı (maliyet dahil), marj ve nominal sınırı, toplam açık stop riski, UTC günlük kayıp kapısı (yeni giriş yok, açık pozisyon kapanmaz), strateji kill (zirveden −%30), hesap kill (ortak zirveden −%20), stop mesafesine göre kaldıraç (≤%15 → 3x, değilse 2x), stop mesafesi > %25 ise atlama.
- Miktar yuvarlama: `stepSize`'a **aşağı** yuvarlama, min tutar altındaysa işlemi atla, asla yukarı yuvarlama. Doğru tasarım.
- `motor/risk/limitler.py::maliyetli_risk_birim` — miktar formülü: `nakit·risk / (|giriş−stop| + max(giriş,stop)·(stop_kayma + 2·taker))`. Komisyon ve stop kaymasını boyuta dahil eder. Bizim için çok değerli.
- `motor/canli/borsa/risk_adim_kontrol.py` — salt okunur risk adımı denetimi.

**Dikkat — iki risk kaynağı tutarsız:**
- `motor/risk/limitler.py::SERT_LIMITLER`: işlem başı **%1**, günlük **%3**, kill **%20** (paper ve araştırma için).
- `canli_limitler.py::CanliLimitleri`: işlem başı **%3** tavanı, günlük **%6**, strateji kill **%30**, hesap kill **%20**. Strateji başı `islem_risk` 0,015 (%1,5) olarak ayarlı.
- DURUM kararı 14 "işlem başı %1" diyor; canlı tarafı %1,5 kullanıyor. Bizim risk kilidi yazarken hangisinin "sert" olduğu baştan netleştirilmeli.

**Borsa istemcisi (güvenlik ve dayanıklılık):** `motor/canli/borsa/binance_futures.py`
- Emir veren POST'lar ağ hatasında **asla otomatik tekrarlanmaz**; belirsiz sonuç `belirsiz=True` olur, yürütücü `newClientOrderId` ile sorgular. Çift pozisyon riskine karşı doğru yaklaşım.
- Yalnız -1021 ve 5xx okuma isteklerinde üstel geri çekilme.
- Ağırlık sınırı (`AGIRLIK_ESIGI=1800`), idempotent hata kodları (-4046, -4059), yetim emir temizliği (`hepsini_iptal`).
- Açık risk: koşullu emir uçları (`/fapi/v1/algoOrder`, Binance 2025-12 sonrası) testnet'te **henüz doğrulanmadı** (dosya başlığında açıkça yazılı).

**Sağlık / heartbeat:**
- `motor/canli/kalp_atisi.py` — her turda en çok 60 sn'de bir `kalp_atisi.json`; yeniden başlatma kesintisini ölçer. Basit ve yeniden kullanılabilir (S).
- `saglik.json` ve `bayat_esigi_dk(tf)` = 2 × mum süresi + 10 dk. Veri bayatlığı kontrolü (S).
- systemd: `Restart=on-failure`, `RestartSteps=5`, `RestartMaxDelaySec=600`, `StartLimitBurst=8` ve `OnFailure=` → Telegram. Servis durumunu gösterme ve sessiz hata yasağı için örnek (S).

**Yedekleme: repoda yok.** `deploy/KURULUM.md` içinde yedek/backup prosedürü bulunmadı. Yalnız uyarı: `paper_state.json` silinirse paper sıfırdan başlar; durum dizinleri elle yeniden adlandırılarak saklanıyor. Bizim yedekleme planı sıfırdan yazılmalı (idea only).

**Loglama ve gizlilik:**
- Python `logging`, isimli logger'lar (`paper.telegram`, `canli.borsa`, `canli.kuru`).
- Gizli maskeleme: `telegram.py::maskele` (token), `binance_futures.py::temizle` (imza parametresi). Ağ hata metinleri (URL taşıyabilir) loglanmaz, yalnız istisna tipi.
- Olay kayıtları: `olaylar.jsonl` (append), işlemler `islemler.jsonl`, `kilit_acilis.jsonl` (kilit açılış denetimi).

**Testler:**
- `testler/conftest.py`: gerçek deneme kaydını ve kilit günlüğünü test sırasında geçici dizine yönlendirir. Gerçek veri testleri CI'da atlanır, yerel ortamda `PAPER_GERCEK_VERI=1` ile hata verir.
- Kullanışlı test fikirleri: `test_lookahead_tum_stratejiler.py` (sızıntı testi), `test_kilit*.py` (veri kilidi), `test_canli_limitler`, `test_risk_senaryo.py`, `test_telegram.py`, `test_pano*.py`, `test_mutasyon_*` (mutasyon testleri).
- CI: `.github/workflows/testler.yml` — push ve PR'da `pytest testler -q -p no:cacheprovider`, Python 3.13, gizli anahtar yok.
- `testler/test_paper_denetim.py:267` bir token benzeri sabit içerir (`123456789:AAH-...`). Görünüşte sahte bir test değeri; yine de kontrol edilmeli (bkz. §8).

**Kilit (veri sızıntısı koruması):** `motor/veri/kilit.py` — 2025-11-01 sonrası veri "kasada"; yalnız bir kez açılır, açılış `kilit_acilis.jsonl`'e yazılır. Holdout disiplini için fikir olarak değerli.

---

## 6. Dersler ve bilinen sorunlar

Doğrudan dokümandan, yorumlardan ve TODO benzeri notlardan. (Kodda `TODO/FIXME` bulunmadı.)

1. **Seçim sonrası görülen sonuçla karar:** DURUM 2026-11-14 odak listesinin "sonuç görüldükten sonra TERCİHLE seçildiğini" açıkça yazıyor. Bizim için ders: ön kayıt (pre-registration) ve holdout'u en baştan kilitlemek.
2. **OOS ile seçilen önceki sonuçlar üst sınır sayıldı:** `arsiv/OZET.md` — "önceki sonuçlar OOS'a bakılarak seçilmiş ve kâr birkaç işlemde yoğun → üst sınır kabul edilir."
3. **Boğa dönemi şişirmesi:** 2020–25 kripto boğa dönemi uzun trend stratejilerini şişiriyor; 2022'de al-tut −%75.
4. **Çoklu test:** Bonferroni'yi hiçbir aday geçmedi, DSR ≈ 0. `dersler.py` ALFA=0,05 ve "çoklu test düzeltmesi YOK" diyor. Ciddi bir sınırlılık.
5. **Paper kayma ölçmez:** Paper dolumu varsayılan kaymayla simüle eder; kayma paper'da ölçülemez (DURUM düzeltme, Fable pano incelemesi). Kayma ancak testnet/küçük canlı dolumla ölçülür. Bizim paper planında da aynı tuzak var.
6. **Küçük kasada min tutar engeli:** `ATLANAN_TESHIS.md` — gauss (737), ewo (527), hma (1206) sinyalleri `min_tutar` yüzünden atlandı. 60–250 USD kasada çok sayıda sinyal kaybı. Kasa büyüklüğü baştan hesaplanmalı.
7. **Stop uzaklık filtresi sessizce engeller:** `stop_uzaklik_maks_oran=0.25` nedeniyle 670 ve 574 stratejileri hiç işlem açamadı (DURUM 2026-11-14). Filtrelerin panelde görünmesi gerekir.
8. **Veri kaynağı tuzakları:** Binance arşivinde 2026-10-28 tüm sembollerde eksik; Binance API bazı bulut IP'lerinden engelli; TradFi geçmişi kısa (≈1–10 ay Binance'te), Dukascopy'de funding yok.
9. **Açık teknik risk:** koşullu (algo) emir uçları testnet'te doğrulanmadı; testler sahte HTTP ile yazıldı (`binance_futures.py` başlığı).
10. **Risk tutarsızlığı:** §5'te anlatılan iki ayrı risk tanımı (%1/%3 vs %3/%6).
11. **Güvenlik kararı:** `PANO_KILITSIZ=1` ile şifresiz genel pano yayını seçeneği var.
12. **Yeniden kullanılacak kod lisansı:** DURUM "Yeniden kullanılacak eski kod" bölümü, kullanıcının `sg-arge` reposundan (GPLv3) kod alınacağını yazıyor. Bu koda bağlı kalan her parça GPL yükümlülüğü getirir; bizim repo lisansıyla uyumu kontrol edilmeli.

---

## 7. Yeniden kullanım tablosu

Efor: S (birkaç saat), M (birkaç gün), L (hafta+). "Idea" = yalnız fikir, kod kopyalanmaz.

| Parça | Dosya(lar) | Karar | Efor | Not |
|---|---|---|---|---|
| Panel üretici (HTML, sekmeler, grafikler) | `motor/canli/pano.py` | Adapt (kısmi) veya rewrite | M-L | Durum JSON şemasına bağlı; 4 sekmelik yeniden yazım önerilir |
| Panel yayın (Worker + Basic Auth + SSH tüneli) | `deploy/pano_worker.js`, `deploy/pano_yayinla.sh`, `deploy/1l3a-pano-sunucu.service` | Reuse as-is (şifreli mod) | S | `PANO_KILITSIZ` yolunu kullanma |
| Atomik JSON yazma | `motor/canli/durum.py` (`atomik_yaz_*`) | Reuse as-is | S | Panel dosyaları için |
| Telegram gönderici + throttle | `motor/canli/telegram.py` | Adapt | S | Komut desteği yok; `ozet_metni` ve `Bildirimci` alınır |
| Günlük 21:00 özet metni | `motor/canli/telegram.py::ozet_metni` | Adapt | S | Zamanlayıcı ve veri kaynağı değişir |
| Acil durdurma (Telegram komutu) | — | Idea only, yeni yazılacak | M-L | Chat doğrulaması, onay, borsa tarafı iptal |
| Maliyet dahil boyutlandırma | `motor/risk/limitler.py::maliyetli_risk_birim` | Reuse as-is | S | Formül doğrudan kullanılabilir |
| Canlı risk kapıları | `motor/canli/borsa/canli_limitler.py` | Adapt | M | Önce iki risk tanımı netleştirilmeli |
| Aşağı yuvarlama + min tutar atlama | `canli_limitler.py`, `canli_yurutucu.py` | Reuse (fikir + kod) | S | Yukarı yuvarlama yok |
| Güvenli emir gönderimi (belirsiz sonuç, sorgula) | `motor/canli/borsa/binance_futures.py` | Adapt | M | Freqtrade kendi emirlerini yönetir; yalnız fikir ya da ek katman |
| Kuru (sahte borsa) modu | `motor/canli/borsa/kuru.py` | Idea → Adapt | S | Freqtrade `dry_run` zaten var; yine de tutarlılık testi için |
| Kalp atışı | `motor/canli/kalp_atisi.py` | Reuse as-is | S | Kesinti ölçümü |
| Veri bayatlık eşiği | `motor/canli/durum.py::bayat_esigi_dk` | Reuse as-is | S | |
| Servis hatası → Telegram | `deploy/1l3a-bildirim@.service`, `OnFailure=` | Reuse as-is | S | |
| systemd servis şablonları | `deploy/1l3a-paper.service`, `1l3a-canli.service` | Adapt | S | Yeniden başlatma politikası iyi |
| Test yapısı ve CI | `testler/conftest.py`, `.github/workflows/testler.yml` | Adapt | S-M | Lookahead ve kilit testleri fikir olarak |
| Lookahead testi | `testler/test_lookahead_tum_stratejiler.py` | Idea (kendi testimiz) | S | |
| Veri kilidi (holdout) | `motor/veri/kilit.py` | Idea | S | Açılış günlüğü dahil |
| Strateji kart şeması | `stratejiler/KART_SEMASI.md` | Idea only | S | Bizim için gerekli değil |
| Yedekleme | — | Yok, sıfırdan | M | Repoda hiç yok |
| Haftalık rapor | `araclar/canli_haftalik_rapor.py`, `motor/canli/aylik_rapor.py` | Idea | M | Kapsam dışı olabilir |

---

## 8. Lisans ve gizli bilgi kontrolü

**Lisans:** **Yok.** Kök dizinde ve alt dizinlerde `LICENSE`, `COPYING` ya da lisans dosyası bulunmadı. `.gitignore` ve `AGENTS.md` repoyu "public repo" olarak anıyor. Lisanssız açık kaynak, kullanım hakları saklı demektir; kopyalama izni yoktur. Bunu fikir kaynağı olarak kullanmak serbesttir, kod kopyalamak için kullanıcıdan açık izin alınmalıdır.

**Gizli bilgi:** Tespit edilen **açıkça sızmış anahtar yok** (tarama: API anahtarı, Telegram token kalıbı, AWS anahtarı, özel anahtar başlığı, parola kalıpları).
- İzlenen dosyalarda `.env` ya da anahtar dosyası yok. `.gitignore` `.env` ve `*.env` dosyalarını dışlıyor.
- Şablonlar (`deploy/*.env.ornek`) yalnız yer tutucu içeriyor.
- Tek şüpheli satır: `testler/test_paper_denetim.py:267` — token biçiminde sahte bir değer. Muhtemelen test verisi, ama kontrol edilmeli.
- Git geçmişi bu klonda tek commit (`2dd2dce`). Eski geçmiş tam doğrulanamadı; `git log --all` ile bakılmalı.

Sonuç: sızmış gizli bilgi **hayır** (yalnız test satırı kontrol edilmeli). Ayrıntılı tarama bu kopyada gerçek değerleri yazdırmadan yapıldı.

---

## 9. Sonuç ve notlar

- Freqtrade'e geçişte en değerli parçalar: risk formülleri (`maliyetli_risk_birim`, `canli_limitler`), güvenli emir gönderimi fikri, Telegram gönderici ve günlük özet biçimi, systemd/health/`OnFailure` düzeni, atomik yazma.
- Panel yeniden kullanılabilir ama doğrudan taşınmaz; yayın katmanı (Worker) en kolay alınacak kısım.
- Telegram komut desteği ve yedekleme yok; bunlar sıfırdan yazılmalı.
- Strateji kanıtı zayıf ve seçim önyargılı; bizim test disiplinimiz için bir "ne yapmamalı" listesi olarak okunabilir.
- Anlamadığım kısımlar: `motor/canli/paper_v2.py` (çok hesaplı kapı mantığı) ve `motor/canli/pano.py` grafik ayrıntıları yalnız gezinerek okundu. Bunları kopyalamaya karar verirsek daha güçlü bir modelle ayrıntılı inceleme önerilir.
