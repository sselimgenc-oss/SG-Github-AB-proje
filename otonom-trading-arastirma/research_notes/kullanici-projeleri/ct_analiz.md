# CT-Proje (Hyperliquid copy trade) — salt okunur analiz

Kaynak: `/home/user/sselimgenc-oss/ct-proje` (git HEAD `3aa4460`, `main`). Yalnız dosya okundu; hiçbir şey çalıştırılmadı, kurulmadı, içe aktarılmadı.
Tarih: 2026-11-16. Ayrıntılar ilgili dosyalarda; bu not onların özeti ve bizim projeye (freqtrade, Binance USDT-M) uyarlama notudur.

---

## 1. Ne bu proje

**Ne yapıyor:** Hyperliquid'de seçilen trader'ların (lider adayları) işlemlerini kopyalayan bir sistem. Üç parça:
- **Radar** (günlük, GitHub Actions): Hyperliquid lider tablosundan ön filtreli evren → 7 günlük R1 kopyalanabilirlik süzgeci → R2 form puanı → 30 kişilik kadro (İlk 11 saha + Yedek 19). `.github/workflows/radar.yml`, `copytrade/radar_tarama.py`, `radar_kadro.py`, `radar_form.py`, `radar_isabet.py`.
- **Motor** (`copytrade/canli/motor.py`, 3.276 satır, tek süreç): sahadaki 11 trader'ın dolumlarını WebSocket/REST ile izler, `boyut.py` ile boyutlar, `risk.py` ile süzer, `yurutucu.py` ile yürütür (sanal: l2Book yürüyüşü; gerçek: Hyperliquid SDK). İki kip, tek kod yolu: `sanal` (varsayılan) ve `gercek` (yalnız sunucu ortamında).
- **Pano / sağlık / bildirim**: `canli/pano.py` (tek dosya HTML + OZET.md), `saglik.py` (saatlik sağlık kontrolü), `canli/telegram.py`, Cloudflare Workers `sg-pano` (görünüm) ve `sg-nabiz` (dış ölü adam alarmı).

**Dil ve sürümler:** Python 3.12 (CI), `requirements.txt`: pandas 2.3.3, pytest 9.1.1, requests 2.34.2, PyYAML 6.0.3, websockets 15.0.1; canlı için `requirements-canli.lock` (hash'li kilit) ve `hyperliquid-python-sdk==0.24.0`. Sunucu dinleyicisi için pandas/numpy yok. Node 22 (yalnız Cloudflare worker ve pano aracı).

**Nasıl çalışıyor / deploy:**
- **Bugün sanal kip GitHub Actions'ta çalışıyor**: `canli_vardiya.yml` 4 saatte bir, her vardiya 4 sa 15 dk, yedek cron; durum `canli-durum` veri dalında (git branch = veri deposu, 90 gün tutulur). Radar `radar` dalına yazar.
- **Gerçek kip için sunucu kurulumu hazır ama açılmadı**: `deploy/sg-canli.service` (Ubuntu 24.04, `sgcanli` kullanıcısı, `StateDirectory=sg-canli`, `Restart=on-failure`, `RestartPreventExitStatus=3`, `OnFailure=` alarmı, `ProtectSystem=strict`), `deploy/kurulum.md`, `deploy/ACILIS_KONTROL.md`.
- **DigitalOcean hakkında**: Repoda DO'nun aktif bir kullanımı YOK. `docs/KARARLAR.md` K-20 (2026-11-04): "Kullanıcı iki hesabı da kapattı" — Cloudflare ve DigitalOcean; VPS "artık yok". Sunucu seçimi "canlı kararıyla birlikte kullanıcıya gelir" deniyor. K-40 yalnız Cloudflare Workers panoyu istisna olarak geri getiriyor. Yani "mevcut DO droplet'inde çalışan süreç" varsayımımız repoyla çelişiyor; sunucunun nerede olacağı açık karar. Bunu kullanıcıya sormak gerekir.
- **Bellek ayak izi hakkında veri yok**: Repoda RSS/bellek ölçümü yok. Ölçülebilir ipuçları: motor tek süreç, `SNAP_SAKLA = 50_000` ID sınırı (`motor.py:49`), dolum/önbellek sözlükleri sınırlı; ama 3.276 satırlık monolit ve WebSocket + REST + JSON durum dosyaları. 2 GB RAM'de sanal kipin kendisi zaten GitHub'da koşuyor; sunucuda gerçek kipin tek süreç olarak ne kadar tuttuğunu **ölçmeden** söyleyemeyiz. Tavsiye: freqtrade + panel + bizim motor birlikte koyulmadan önce tek başına RSS ölçümü.

**Veri kaynakları:** Hyperliquid public API'leri (stats-data lider tablosu, `userFillsByTime`, `clearinghouseState`, `l2Book`, `metaAndAssetCtxs`, WebSocket `trades`/`userFills`, `perpDexs`, `maxLeverage`). `izleme_motoru.py` ve `hl_ortak.py` içinde Binance referansı var (eski izleme hattı; kline/mum kaynağı olarak). Bizim için ilgili olan Hyperliquid değil Binance tarafı.

**Paper (sanal) mekanizması:** `canli/motor.py` + `canli/yurutucu.py` + `canli/hesap.py`:
- Sanal dolum fiyatı: l2Book'a yürüyüş, **1 dk gecikme**, taker %0,045 + kayma %0,05 (`kurallar.yaml` `maliyet_taker`, `maliyet_kayma`), saatlik funding.
- Sanal tasfiye: izole 3x marj, `tasfiye_fiyati` formülü (`hesap.py:24`): long `giris·(1−1/k)/(1−mmr)`, short `giris·(1+1/k)/(1+mmr)`, `mmr = 1/(2·maxLeverage)`.
- Gerçek kipte aynı kod yolu; yürütücü SDK ile gerçek emir. `kurallar.yaml canli_kip: sanal` (repodan `gercek` açılamaz; GitHub Actions'ta gerçek kip reddediliyor).

**Kaynak durumu (`DURUM.md`, 2026-11-16):**
- Hedef: Form Radarı (K-66, 14.11): sanal kasa 10.000 $, slot ≈ 909 $, 11 saha + 19 yedek. Gerçek para yok; sınır ≤ 1.000 $ (K-22/K-26/K-50).
- Değerlendirme 31.12.2026: aylık ≥ %4 **ve** BTC al-tut'tan iyi. Kasa zirveden −%20 → DUR.
- Yeni sanal dönem 16.11 11:30Z. Telegram açık. `main` korumalı (`test` + `canli_sdk` yeşil).
- Gerçek paraya geçiş için açık ön koşullar: `docs/DENETIM_DEVIR_2026-11-06.md` G-1…G-14 (K-48/K-51 ile kısmen kapandı), testnet stop denemesi (K-64, `copytrade/canli/stop_deneme.py`) "HEPSİ GEÇTİ" çıktısı beklemede, 7 temiz sanal gün (K-50).

---

## 2. Yeniden kullanılabilir altyapı

**Telegram** — `copytrade/canli/telegram.py` (529 satır): Bot API doğrudan (`requests`, yoksa stdlib yedeği). Güçlü yanlar: chat_id + özel sohbette `from.id` yetki kontrolü (K-37), komut adı = ilk sözcük, bilinmeyen komuta yanıt, eski (>15 dk) komutu yürütmeme (G-16), önemli mesajlarda 2/5/15 sn yeniden deneme ve 429 `retry_after` (G-18), offset kalıcı. Kritik: `getUpdates` tek tüketici olmalı (K-37/G-7 — Actions ile sunucu aynı botu dinlerse komut kaybolur; `TELEGRAM_KOMUT=kapali` mekanizması `deploy/kurulum.md` §2).

**Panel / dashboard** — `copytrade/canli/pano.py` (941 satır): tek dosya HTML (koyu "terminal" teması, `pano/index.html`), `OZET.md` (telefondan GitHub'da okunur), HTML kaçışı (`html.escape`) denetimde XSS yolu bulunmadığı yazılı. Yayın: `.github/scripts/pano_cf_yayimla.sh` + Cloudflare Workers `sg-pano` (`.github/pano/package.json`, wrangler 4.158.0 sabit). Veri kaynağı: durum JSON'ları; **yeni hesap yok** (kural 7) — bu ilke iyi, ayrıca korunmalı. Bizim "3 proje tek ekran" hedefi için bu tek-dosya üretici örnek, ama çoklu proje için veri sözleşmesi gerekir (`docs/VERI_SOZLESMESI.md`, 544 satır, birim disiplini).

**Sağlık / heartbeat** —
- `copytrade/saglik.py` (379 satır): SAF fonksiyon, girdi `ozet.json` + `kadro.json`, çıktı KRİTİK/UYARI/BİLGİ bulguları; eşikler sabit ve yaş tabanlı (vardiya yazma 30/60 dk, radar 30/54 sa, pano 45 dk). Saatlik `saglik.yml`. **Bizim için en yeniden kullanılabilir modül** (I/O'su ayrık, test edilebilir).
- `copytrade/canli/motor.py` `kilit.json` (`nabiz_ms`): motor her dakika nabız yazar, vardiya çakışmasını önler.
- `.github/nabiz/worker.js` (Cloudflare Cron 10 dk): GitHub Actions'a bağlı olmayan **dış ölü adam alarmı** — veri dalındaki `kilit.json` yaşına bakar, durum tutmadan (KV yok) yalnız Telegram. Bu, "sunucu çökerse sessizlik" riskine karşı doğrudan model.
- `deploy/alarm.sh` + `sg-canli-alarm.service` (OnFailure): kalıcı düşünce tek Telegram mesajı; token yoksa "atlandı" ile 0 çıkış.
- `deploy/gercek_yayimla.sh`: maskeli `ozet/kilit/nabiz.json` (adres `0xAAAA…ZZZZ`, anahtar alanları `[gizli]`).

**Loglama** — JSONL (`kayit/<tarih>.jsonl`), olay listesi son 200 ile sınırlı, taşanlar `olay_tasan.jsonl` → `.github/scripts/olay_arsivle.py` append-only arşiv (`id` tekil, mevcut kayıt silinmez). Sunucuda `journalctl -u sg-canli -o cat`. Kayıt ve niyet: `copytrade/canli/niyet.py` — emirden önce `durum/niyet.jsonl`'e **fsync ile** niyet, sonra sonuç; cloid deterministik (`sha256(dolum kimliği|eylem)`), yeniden başlatmada `orderStatus(cloid)` ile çift emir engeli. Bizim freqtrade ledger'ı için bu desen (niyet-sonuç çifti) doğrudan uyarlanabilir.

**Config ve sır yönetimi** —
- `copytrade/kurallar.yaml` (tüm eşikler tek yerde, "kodda sayı sabiti yok" ilkesi; ayrıca `radar_surum`, `canli_kip` gibi anahtarlar). İyi pratik; ama 200+ anahtarlı tek dosya ve `max_leverage: 15.0` (en üst satır) kodda okunmuyor (grep'te tüketici yok; ölü anahtar olabilir, teyit gerekir). Kaldıraç sınırı radar tarafında `radar_max_kaldirac: 20.0`.
- `copytrade/canli/ortam_dosyasi.py` (126 satır): systemd `EnvironmentFile` doğrulayıcı; değer **asla** basmaz, yalnız satır no + sorun. Satır sonu yorumun değere karıştığını yakalar (G-9). Doğrudan kopyalanabilir.
- Sırlar: yalnız GitHub Secrets / `/etc/sg-canli*.env` (izin 600, sahibi `sgcanli`), üç ayrı dosya (HL anahtarı yalnız motor birimine; Telegram ayrı; yayım ayrı — G-22). Bu ayrım bizim için iyi bir model.

**Yedek / kalıcılık** — açık bir "backup" betiği yok. Durum, git veri dalında (`canli-durum`, `radar`) tutuluyor; kayıt ve durum git geçmişinde; `.github/scripts/donem_geri.sh` dönem ayrımı (yeni dönemde eski durum yüklenmez, eski veri dal geçmişinde arşivli). Sunucuda `StateDirectory=sg-canli` + `durum/` dizini; **sunucu yedeği yok** — bizde ayrı bir yedek adımı yazmak gerekir.

**Deploy** — `deploy/sg-canli.service`, `sg-canli-kontrol.service` (açılış kontrolü; emir göndermez), `sg-canli-yayim.service` + `.timer` (15 dk nabız), `sg-canli-alarm.service`, `sg-dinleyici.service` (eski dinleyici, `/home/sg/...` yollu — DO döneminden kalma olabilir). systemd sertleştirme ayarları (`NoNewPrivileges`, `ProtectSystem=strict`, `ProtectHome`, `PrivateTmp`, `StateDirectory`, `StartLimitBurst`, çıkış kodu 3 = yeniden başlatma yok) bizim unit dosyalarına doğrudan taşınabilir. Docker yok.

**Testler / CI / lint** —
- `tests/`: 80 test dosyası, ~1.087 `def test_` (sayım kaba; parametrize olabilir). `pytest.ini` (`pythonpath = .`), `tests/conftest.py`, fixture'lar `tests/fixtures/*.json`. Kabul kuralı: "altın örnek" testleri (girdi + elle hesaplanmış beklenen sayı) — çok değerli pratik.
- `.github/workflows/ci.yml`: `pip install -r requirements.txt`, `ruff check` (sürüm sabit 0.17.0, `ruff.toml` yalnız F + E9), `pytest -q`; ayrıca `canli_sdk` işi (hash'li kilit ile SDK kablo testi). Actions sürümleri commit SHA ile sabitlenmiş; `persist-credentials: false`.
- Lint hafif (yalnız hata kuralları): `ruff.toml` bilerek biçim kuralı yok. Bizim için makul başlangıç.

---

## 3. Risk yönetimi, boyutlandırma, kaldıraç/tasfiye

**Boyutlandırma (`copytrade/boyut.py`, 140 satır; tek yer):** Slot = kasa / N, N = min(11, taban(kasa / 200 $)). Hedef nosyonel = slot × (trader pozisyon nosyoneli / trader hesap değeri); tavan 1,5 × slot; 11 $ altı emir atlanır, [5,5; 11) → 11 $'a yuvarlanır. Artırma/azaltma hedef tabanlı (K-36/K-38; eski "oran" kuralı kısmi dolumda bozulmuştu). Bunu "trader oranını kopyala" olarak düşünmek freqtrade için uyarlanabilir, ama bizim stratejimiz sinyal-tabanlı; **boyut formülü ve yuvarlama kuralları bize özgü değil, fikir olarak değerli.**

**Portföy/risk (`canli/risk.py`, 170 satır; saf durum makinesi, saat ve özsermaye dışarıdan verilir):**
- Coin yoğunlaşması: aynı coinde toplam brüt ≤ max(kasa × %30, 1,5 × slot).
- Patlama freni: 10 dk'da ≥ 8 yeni coin açan trader'dan 30 dk yeni açılış yok.
- Günlük kayıp ≥ %5 → o gün yeni açılış yok; ≥ %10 → tüm pozisyonlar kapanır (K-62 sert fren, DUR değil).
- Zirveden −%20 → DUR (reduce-only kapanış, `durum/DUR`, elle silinmeden açılmaz).
- Felaket stopu: pozisyon ortalama girişten −%20 → o pozisyon kapanır (yazılım, K-62). Borsa tarafı: `canli/borsa_stop.py` — coin NET pozisyonuna reduce-only tetikli stop, −%22; sıra "önce yeni, sonra eski iptal"; stop kaybolursa alarm + ters yön riskine karşı otomatik kapatma (K-65).
- Kasa üst sınırı 1.000 $ (gerçek) / sanal 10.000 $; marj: izole 3x (`canli_marj_kaldirac`), toplam marj ≤ özsermaye.
- Kopya hesabına tasfiye: `hesap.py` `tasfiye_kontrol` — mark tasfiye fiyatını geçerse izole pozisyon tasfiye fiyatında kapanır (sanal). Gerçek kipte borsadan gelen tasfiye/ADL farkı G-13 ile defterden düşülüyor.
- Trader filtreleri (R1): kaldıraç ≤ 20x (`radar_max_kaldirac`), coin likidite ≥ 1 M $ hacim ve ≥ %80 likit pay, işlem sayısı ≥ 10, devir ≤ 100× hesap değeri, "şans süzgeci" (bootstrap %20 alt yüzdelik > 0).

**Kaldıraç / likidasyon işleyişi için dikkat:**
- Hyperliquid'de coin başına tek net pozisyon ve çapraz/izole ayrımı var; kod izole 3x ile sanal tasfiye hesaplıyor ve gerçek kipte "borsa 0" mutabakatı yapıyor (G-13). Bizim freqtrade (Binance USDT-M) için: liquidation price'ı borsa API'sinden okumak gerekir, formül kopyası yerine.
- `kurallar.yaml` `golge_likidasyon_esigi: -1.0` ve `defter.py` çapraz teminat tasfiyesi; geçmiş (`kopya_v2`) testleri var.
- Sık görülen hatalar (aşağıda 5. bölüm): ters yönde reduce-only eksikliği (G-3), kaldıraç ayarı reddedilirse kapanışın hiç gitmemesi (G-4).

---

## 4. Araştırma notları (`arastirma/`) — bizim için ilgili olanlar

- **`arastirma/dis_inceleme/codex_tasarim/RAPOR.md`**: seçim ve ölçüm tasarımı. Özet: Sharpe benzeri seçim kısmen sınandı; asıl başarısızlık "bütün seçim kapılarının birlikte" sonucu. Yuvarlama ve boş başlangıç bazı trader türlerini farklı etkiler; ölçülmedi. Tarihler örtüşüyor, geçmişe bakılarak tasarlanan revizyon bağımsız sınav değil. **Bize**: değerlendirme/ölçüm disiplini için iyi örnek (önceden kayıt, bağımsız örneklem).
- **`arastirma/dis_inceleme/risk_secim/RAPOR.md`**: riske göre seçim. Dorfleitner 2018: en çok kazanana göre seçim kaybettiriyor; Sharpe'a göre seçim iyileştiriyor; maliyet sonrası kazandırdığı kanıtlanmamış. **Bize**: "en iyi getiri" yerine risk-normalize seçim gerekçesi.
- **`arastirma/dis_inceleme/dunya/RAPOR.md`**: kopya platformları literatürü. Popülerlik ile performans zayıf ilişkili; beceri nadir (Tayvan gün içi verisinde kalıcı kazananların %1'den az); Hyperliquid'de kaybeden taraf çoğunlukla elle işlem yapan bireyler. **Bize**: evren seçiminde popülerlik/leaderboard'a güvenme.
- **`arastirma/dis_inceleme/hl_ozel/RAPOR.md`**: Hyperliquid'e özgü kaynak taraması (15 aylık tüm işlemler; UI'den elle işlem yapanlar). Ayrıntı için dosyanın tamamı gerekir; bu notta yalnızca başlık düzeyinde okundu.
- **`arastirma/futbol_sinama/RAPOR.md`** (171 satır, "sinama" = geniş kadro denemesi): 11 kişilik kadro için slot 100/150/200 $ denendi; küçük slotta yuvarlama alarm eşiğini aşıyor; sıralamasız geniş kadro rastgeleden iyi olduğu gösterilemedi (yansız havuzda T başına ~1,5 temiz aday). **Bize**: küçük kasada çok slot = yuvarlama problemi; kendi evren boyutumuzu buna göre kur.
- Genel ders: araştırma notları "karar değildir" diye etiketli; geçmiş veriye bakılarak seçilen eşikler "kilitli" tutuluyor (`docs/RADAR_V1.md` §8). Bu disiplini almaya değer.

---

## 5. Dersler ve bilinen hatalar (bizim için ilgili)

Kaynak: `docs/DENETIM_DEVIR_2026-11-06.md` (G-1…G-14), `docs/DENETIM_PROJE_2026-11-08.md` (G-12…G-24), `docs/KARARLAR.md` K-62/K-64/K-65. Repo hâlâ "gerçek para için henüz hazır değil" diyor; aşağıdakiler düzeltilmiş ya da düzeltilmekte olan kalıplar:

1. **Emir sonucu belirsizliği (G-1):** SDK/ağ hatası emir gittikten sonra "red" sanılırsa yetim pozisyon oluşur. Çözüm: niyet kaydı + `orderStatus(cloid)` ile çözme. **Bizde zorunlu.**
2. **Kapatma yalnız defterdeki coinleri kapatıyordu (G-2):** borsada defterde olmayan pozisyon kalıyordu. Kapatma, borsa durumundan (teyitli) yapılmalı.
3. **Artırmada reduce-only eksikliği (G-3):** kaçan ters dönüşten sonra borsada ters net pozisyon. Her çıkış/azaltma emri reduce-only ve borsa durumuna göre hesaplanmalı.
4. **Kapanıştan önce kaldıraç ayarı (G-4):** `update_leverage` reddi kapanışı engelliyordu. Kapanış yolu kaldıraç ayarından bağımsız olmalı.
5. **Yeniden başlatmada zararın iki kez sayılması (G-5):** kasa + eski realize; yanlış DUR riski.
6. **Önbellekte kalıcı hata (G-6):** `perpDexs` hatası süreç boyu önbellekte; hata önbelleğe alınmamalı.
7. **İki Telegram tüketicisi (G-7):** `/kapat` kaybolabilir. Bizde de tek bot tek tüketici kuralı.
8. **Korumasız dal ve yazma izni (G-8):** `main`/veri dallarına yazma koruması (ruleset) — bizde de zorunlu.
9. **Env dosyası yorumu (G-9):** `CANLI_KASA_USD=300  # not` systemd'de değere karışıyor → motor açılmıyor. Doğrulayıcı yazın.
10. **Sessiz donma (G-12):** zaman aşımsız emir/istek; sistem sessizce durdu. Her ağ çağrısında timeout; "bayat veri" alarmı.
11. **Ters reduce-only ve tasfiye sonrası (G-13):** borsada tasfiye/ADL/elle kapanışla defter uyuşmazlığı; mutabakat zorunlu.
12. **Bayat trader pozisyonu ezmesi (G-14):** eski veri yeniyi ezmesin — veri zaman damgası kontrolü.
13. **Aynı gün yeniden koşu üzerine yazması (R-1):** isabet ölçümünü bozdu. Günün ilk çıktısı saklanmalı.
14. **Hata sayılmadan "tam" koşu (R-2):** `veri_hatasi` payı eşiği aşmadıkça koşu tam sayıldı. Eksik veri = eksik koşu kuralı.
15. **Payda hatası (K-65, 13–14.11):** Hyperliquid birleşik hesapta (`unifiedAccount`) USDC `hold` bekleyen emirlerin teminatını da içerdiği için yanlış paydalar; bir adres 213.155 $ yerine 0,09 $ okundu ve `payda_oran` 2,4 milyon çıktı. **Bizde**: API'den okunan bakiye alanlarının anlamı belgelenmeli, birim/sözleşme testi olmalı (`VERI_SOZLESMESI.md` kuralı bu yüzden var).
16. **Borsa stopu eksikse acil kapatma (K-65):** stop 2 saat korumasız kalırsa motor pozisyonu kapatır. İyi kalıp.
17. **Ölçüm disiplini:** "testler yeşil" birleşme için yetmez; gerçek veriyle üretilen çıktıya bakılır (AGENTS.md kalite kuralları 1–3). Bu süreç kuralını alalım.
18. **Gerçek paradan önce 7 temiz sanal gün ve küçük gerçek veri denemesi** (AGENTS.md kural 1).

---

## 6. Parça tablosu

Etiketler: **as-is** = olduğu gibi alınabilir; **uyarla** = fikir/kod yapısı alınır, bizim API'ye göre yazılır; **fikir** = yalnız tasarım fikri.

| Parça | Dosya(lar) | Karar | Efor | Not |
|---|---|---|---|---|
| Sağlık kontrolü (saf fonksiyon, yaş eşikleri) | `copytrade/saglik.py` | uyarla | S | I/O'su ayrık; freqtrade durum dosyalarına bağlamak yeterli |
| Dış ölü adam alarmı (Cloudflare Cron, heartbeat okur) | `.github/nabiz/worker.js`, `wrangler.toml`, `tests/test_nabiz.py` | uyarla | M | Sunucu çökerse dışarıdan alarm; bizim heartbeat dosyasına göre değişir. Node 22 gerektirir |
| Telegram modülü (yetki, retry, 429, komut offset) | `copytrade/canli/telegram.py` | uyarla | S–M | Komut işleyişi ve retry iyi; freqtrade'in kendi Telegram'ı ile çakışmamalı (tek tüketici) |
| Systemd unit'leri (sertleştirme, StateDirectory, çıkış kodu 3) | `deploy/sg-canli.service`, `sg-canli-alarm.service`, `sg-canli-kontrol.service` | as-is (yol/kullanıcı adı değişir) | S | Unit yapısı doğrudan kullanılır |
| Env dosyası doğrulayıcı (değer basmaz) | `copytrade/canli/ortam_dosyasi.py` | as-is | S | Testleri de al |
| Üç ayrı env dosyası (motor / telegram / yayım) | `deploy/kurulum.md` §2 | fikir | S | Sır ayrımı modeli |
| Niyet-sonuç günlüğü + cloid ile çift emir engeli | `copytrade/canli/niyet.py` | uyarla | M | freqtrade'in order_id'si ile aynı mantık; ledger'a bağla |
| Borsa tarafı stop (replace-before-cancel) | `copytrade/canli/borsa_stop.py` | fikir + uyarla | M | Binance'te stop-market reduce-only; yönlendirme aynı mantık |
| Risk durum makinesi (günlük kayıp, zirve düşüşü, patlama freni, coin tavanı) | `copytrade/canli/risk.py` | uyarla | M | Saf; freqtrade `custom_stoploss`/protections ile örtüşebilir, çakışmayı kontrol et |
| Tasfiye fiyatı formülü (sanal izole) | `copytrade/canli/hesap.py` | fikir | S | Binance USDT-M için formül farklı; borsadan okumak daha doğru |
| Boyutlandırma (slot, tavan, min emir yuvarlama) | `copytrade/boyut.py` | fikir | S | Bizim boyut kuralımıza göre yeniden yaz |
| Panel üretici (tek HTML + OZET.md, escape) | `copytrade/canli/pano.py` | fikir | M–L | 941 satır; freqtrade web panel yerine değil, özet için |
| Cloudflare pano yayın işi (worker + wrangler) | `.github/scripts/pano_cf_yayimla.sh`, `.github/pano/` | uyarla | S | Bağımlılık: Cloudflare hesabı (DO değil) |
| Olay arşivi (append-only, id tekil) | `.github/scripts/olay_arsivle.py` | as-is | S | Saf stdlib |
| Sağlık ışığı + `saglik.yml` (saatlik) | `.github/workflows/saglik.yml` | uyarla | S | Veri dalı okumak yerine doğrudan sunucudan okuyabilir |
| Yayın nabzı (maskeli JSON, adres/anahtar maskesi) | `deploy/gercek_yayimla.sh` | uyarla | S | Maskeleme mantığı iyi |
| Veri dalı ile durum saklama | `.github/workflows/canli_vardiya.yml`, `radar.yml` | fikir | M | Bizde sunucu + ayrı yedek daha uygun; git dalı yalnız kayıt için |
| CI (pinned actions, ruff F+E9, pytest, hash'li kilit) | `.github/workflows/ci.yml`, `ruff.toml`, `pytest.ini`, `requirements-canli.lock` | as-is | S | Doğrudan kopyalanabilir |
| Altın örnek testleri (elle hesaplanmış beklenen) | `tests/test_altin_ornekler.py`, `tests/test_olcut_olculer.py` | fikir | S | Kabul kuralı olarak al |
| Kurallar tek dosya (`kurallar.yaml`, kodda sabit yok) | `copytrade/kurallar.yaml` | fikir | S | 200+ anahtar; bizde daha küçük başla |
| Radar R0–R2 (trader evreni, form puanı, bootstrap) | `copytrade/radar_*.py`, `docs/RADAR_V1.md` | idea only | L | Hyperliquid'e özgü; bizim evren seçimi için yalnız fikir |
| Motor (sanal/gerçek tek kod yolu, WebSocket) | `copytrade/canli/motor.py`, `yurutucu.py`, `dinleyici.py` | idea only | L | 3.276 satır monolit; freqtrade ile işi ayırmak daha temiz |
| Kayıt / defter (JSON, 701 satır) | `copytrade/defter.py` | idea only | M | Biz SQLite ledger kullanacağız; yalnız hesap kuralları fikri |
| Dönem sıfırlama (`donem_geri.sh`, `DONEM`) | `.github/scripts/donem_geri.sh`, `copytrade/canli/DONEM` | fikir | S | Canlı geçişte "temiz dönem" kuralı |

---

## 7. Lisans ve gizli bilgi

- **Lisans:** `LICENSE` = **GNU GPL v3** (metin "GNU GENERAL PUBLIC LICENSE Version 3, 29 June 2007"). Bu copyleft: kod parçalarını kopyalayıp dağıtırsak bizim kodun da GPL-3 uyumlu olması gerekir. Fikir/kalıp düzeyinde alıp kendi kodumuzu yazmak ya da lisans kararını bilerek vermek gerekir. Kullanıcıya/hukuka danışılmalı; bu not hukuki görüş değildir.
- **Commit edilmiş gizli bilgi:** **Hayır** (git ağacı ve `main` üzerinde). Yapılan tarama: `0x` + 64 hex (özel anahtar biçimi), Telegram token biçimi, `sk-` anahtarları, PEM bloğu regex'leri — yalnız `tests/test_canli_motor.py` satır 303'te sahte bir placeholder token-benzeri dize var (`123456789:AAH-gizli-token-DEGERI_…`); gerçek değil, değeri bu notta kopyalanmadı. Git geçmişi (eski commit'ler, veri dalları) tam taranmadı; bunu bir `gitleaks`/`trufflehog` taramasıyla doğrulamak gerekir (yalnız sizin onayınızla çalıştırılabilir, bu analizde çalıştırılmadı).
- Repo herkese açık olduğu `README.md` ve `AGENTS.md`'de yazılı; sırlar GitHub Secrets ve sunucu dosyalarında (`/etc/sg-canli*.env`, izin 600).

---

## 8. Özet kararlar için

- **Hangi parçalar bize değer:** sağlık kontrolü, dış ölü adam alarmı, Telegram modülü (tek tüketici kuralıyla), systemd unit'leri ve env doğrulayıcı, niyet/cloid günlüğü, borsa tarafı stop kalıbı, CI/hash kilidi, altın örnek testleri.
- **Riskler:** GPL-3 lisansı; monolit motor; sunucu yönü belirsiz (DO kapatıldı; repo "sunucu kararı kullanıcıda" diyor); Hyperliquid'e özgü API varsayımları; bellek ölçümü yok.
- **Bize göre fark:** onlar copy-trade (lider seçimi + kopyalama), biz sinyal-tabanlı freqtrade stratejisi. Onların en değerli kısmı "risk ve operasyon katmanı"; seçim/evren kısmı bize doğrudan uymuyor.
- **Açık sorular kullanıcıya:** (a) DigitalOcean droplet bu projede hâlâ kullanılacak mı, yoksa repo'nun dediği gibi sunucu henüz seçilmedi mi? (b) GPL-3 kodunu kopyalamak kabul mü, yoksa yalnız fikir ve kendi kodumuz mu? (c) Telegram botu bizim proje için ayrı mı olacak (tek tüketici kuralı)?

---

## 9. Gerçek model gerekir mi?

- Bu analiz ve parça ayrımı: bu seviye yeterli.
- **Daha güçlü model gerektiren işler:** (1) motor/yürütücü/risk kodunun bizim freqtrade mimarisine taşınması (kaldıraç, tasfiye, borsa stopu, reduce-only mantığı — hata maliyeti yüksek); (2) K-65 tipi "birim/sözleşme" hatalarının denetimi (payda, hold, birleşik hesap); (3) gerçek para öncesi risk kurallarının bağımsız denetimi. Bu üçü için güçlü bir model ve gerçek veriyle test şart.
