# Canlıya geçiş öncesi kod denetimi — 2026-11-17

## Başlık bloğu

- **Tarih:** 2026-11-17
- **Kapsam:** `claude/dazzling-bell-oi6tmu` @ `7eddc5f` (`origin/main` ile aynı), 51 commit. Tüm dallar ve tüm geçmiş secret için tarandı.
- **Sistem:** Binance USDT-M vadeli, yaklaşık 1.000 $. İki yol var:
  1. **Özel motor** `trader/src/trader_engine` (+ `trader_core`, Telegram, panel, systemd birimleri). Asıl yol bu.
  2. **Eski freqtrade yolu** (`docker-compose.yml`, `config/base.json`, `user_data/strategies/TraderV1.py`). Tasarım belgelerine göre silinecek.
- **Yöntem:** Önce mimariyi ben çıkardım. Sonra 3 paralel denetçi çalıştı: Yürütme, Durum ve risk, Veri ve dayanıklılık + güvenlik. KRİTİK ve ORTA adayların hepsini kaynakta tek tek kendim doğruladım. Testleri çalıştırdım. Git geçmişini kendim taradım.
- **Testler:** `pytest` → **3081 geçti, 20 atlandı, 0 başarısız** (211 sn, Python 3.13). Atlananların çoğu `pyarrow` kurulu olmadığı için atlandı (`importorskip`).
- **Kapsam sınırları:**
  - **Canlı broker kodu yok.** Bu yüzden gerçek HTTP hata eşlemesi, imzalı istekler, listenKey/WS ve kaldıraç ayarı incelenemedi.
  - Hiçbir dış servise istek atılmadı. Binance, testnet ve Telegram çalıştırılmadı.
  - `veto.py` / `lesson.py` içindeki Anthropic çağrılarının zaman aşımı ve geri çekilme davranışı ayrıntılı okunmadı.
  - `health.py` feed tazeliğini izliyor mu, doğrulanamadı.
  - **Fable danışmanına ulaşılamadı** (kredi bitti, HTTP 429). Politika maddelerinde öneriler benimdir. Hepsi "kullanıcı onayı gerekir" diye işaretlidir.
  - Repoda AGENTS.md ve DURUM.md yok. Tek kural dosyası `otonom-trading-arastirma/CLAUDE.md`. Bu dosya bir araştırma klasörünü anlatıyor; denetime koyduğu ek bir kural yok.

## Yönetici özeti

**Mimari.** Özel motor tek süreçtir ve tek iş parçacığıyla çalışır. Akış şöyledir:
- Veri, REST yoklamasıyla `var/market.sqlite` dosyasına yazılır.
- Motor dakika ve bar adımlarında kapı zincirini (gates) ve risk kilidini (`trader_core.risk`) çalıştırır.
- Emirler `OrderManager` üzerinden `Broker` arayüzüne gider. Şu an tek gerçekleme `PaperBroker`'dır.
- Durum `state.sqlite` dosyasında tutulur (WAL, `synchronous=FULL`, flock kilidi).
- Defter (`ledger`) outbox ve spool ile beslenir. Dışarıya `status.json` yazılır.
- Telegram, panel, veto ve sağlık ayrı systemd servisleridir.
- `config.py:153`, `testnet` ve `live` kiplerini `ConfigError("faz_b")` ile **reddeder**.

**Genel kalite iyi.** Doğru çalışanlar:
- Deterministik istemci emir kimliği var. Emir satırı POST'tan önce commit edilir.
- Otomatik kör tekrar yok. Belirsizlikte önce sorgu yapılır.
- Stop değişiminde önce yeni stop konur, sonra eski iptal edilir.
- Yuvarlamalar riski artırmayan yöndedir.
- flock ile tek süreç kilidi var.
- Açılışta mutabakat, kaçan olayların yeniden oynatılmasından önce yapılır.
- Kill dosyası okunamazsa etkin sayılır (fail-closed).
- 429 ve 418'de Retry-After'a uyulur.
- Bozuk mumlar iki katmanda reddedilir.
- Telegram komutlarında `from.id` / `chat.id` beyaz listesi var.
- Panel yalnız 127.0.0.1'e bağlanır ve Worker'da Basic Auth vardır.
- Test kapsamı geniş: 3081 test.

**Asıl zayıflık:** Kod paper için tutarlı. Ancak canlıyı varsayan üç temel mekanizma **gerçek broker altında çalışmaz ya da tehlikeli kalır**:
- Dış transaction içinde emir gönderiliyor (K1).
- Belirsiz bir giriş "kapandı" diye işaretleniyor ve borsada stopsuz pozisyon kalabiliyor (K2).
- Kill komutu veri akışı ilerlemezse uygulanmıyor (K3).

Ayrıca feed'in çalıştırılabilir giriş noktası ve servis birimi yok. Bu yüzden 48 saatlik paper denemesi bile sunucuda başlayamaz (K4).

**Hazırlık seviyesi: HAZIR DEĞİL.** Canlı emir yolu henüz yazılmamış (Faz B). Önce şunlar gerekir: K1–K4, ORTA bulguların çoğu, testnet doğrulama listesi ve 48 saatlik paper denemesi.

**Güvenlik sonucu: TEMİZ.**
- Tüm geçmişte gerçek anahtar, token veya özel anahtar yok. Eşleşmelerin hepsi test sahtesi (`123456:SECRETTOKEN…`, `cfSENTINELtoken99`).
- `.env`, sqlite dosyası ve defter commit edilmemiş.
- Tek kişisel veri, 2 commit'teki yazar e-postası (`sselimgenc@…`).
- CI yok.

## Bulgu tablosu

İşaretler: **[P]** = politika kararı, kullanıcı onayı gerekir. **[T]** = testnet doğrulaması gerekir. **[FB]** = canlı broker (Faz B) yazılınca etkili olur.

| Kod | Seviye | Başlık | Yer (dosya:satır) |
|---|---|---|---|
| K0 | KRİTİK | Canlı yürütme yolu yok; motor `live`/`testnet` kipini reddediyor (bilgi / kapı) | `trader_engine/config.py:153` |
| K1 | KRİTİK [FB] | Karar ve dakika adımı dış `tx()` içinde; gerçek broker ilk emirde `StateError` alır (giriş, çıkış, kill, stop gönderilemez) | `engine.py:423`, `:546`, `:754`; `state.py:293-298`; `order_manager.py:72` |
| K2 | KRİTİK [FB][T] | Belirsiz giriş "closed" yazılıyor; borsada dolmuşsa stopsuz yetim pozisyon kalıyor; mutabakat yalnız bayrak koyuyor | `order_manager.py:177-200`, `:216-223`; `engine.py:675-679`, `:470-476`; `reconcile.py:78-82` |
| K3 | KRİTİK | Kill yalnız veri ilerlerken uygulanıyor; feed bayatsa açık pozisyon kapanmıyor | `engine.py:442-452`, `:713-718`, `:741` |
| K4 | KRİTİK | Feed'in `main`'i ve systemd birimi yok; motor `market.sqlite` olmadan başlamıyor, ~100 sn sonra kalıcı `failed` | `cli.py:113-119`; `marketdata/feed.py` (`main` yok); `deploy/` (feed birimi yok); `trader-engine@.service:8-9` |
| O1 | ORTA [FB] | Her broker istisnası "belirsiz" sayılıyor; kesin ret de 2 deneme ve giriş kilidi doğuruyor | `order_manager.py:77-81` |
| O2 | ORTA [T] | Stop iptali başarısız olursa eski stop borsada kalıyor; mutabakat fazla stopu temizlemiyor | `order_manager.py:356-363`; `reconcile.py:96-97`, `:119` |
| O3 | ORTA [T] | `partially_filled` durumu yok; kısmi dolum "accepted" sayılıyor | `order_manager.py:20`, `:142`; `types.py:122` |
| O4 | ORTA | Gün başı değeri cüzdan (gerçekleşmemiş K/Z hariç), ölçüm özsermaye; günlük limit kayıyor | `engine.py:232`; `gates.py:183` |
| O5 | ORTA [P] | Zirveden düşüş kuralı yok; günlük limit yalnız girişi kapatıyor, otomatik kill yok | `trader_core/risk.py:283`; motorda `peak` yok |
| O6 | ORTA [P] | Giriş kilidi çözülmemiş emir varken kendiliğinden kalkıyor; `engine_errors` kilidi hiç kalkmıyor; `unblock` komutu yok | `reconcile.py:13`, `:158-167`; `engine.py:403` |
| O7 | ORTA | Outbox (defter) tıkanması sessiz; girişleri kapatmıyor | `engine.py:410-417` |
| O8 | ORTA [T] | Mutabakat pozisyonun miktarını ve yönünü kıyaslamıyor; `closing`+`failed` pozisyon stop denetiminden kaçıyor | `reconcile.py:94-97`; `engine.py:447` |
| O9 | ORTA | `_kill_step` içinde pozisyon başına hata yalıtımı yok; bir hata tüm kapanışları geri alıyor | `engine.py:447-449` |
| O10 | ORTA | Feed açılışında geçici ağ hatası süreci öldürüyor; bozuk JSON `ValueError` olarak kaçıyor | `feed.py:180`; `rest_public.py:105` |
| O11 | ORTA [P] | 6 ardışık banda `SystemExit(3)`; `Restart=` ile ban sürerken yeniden istek atılır | `feed.py:299-307`; birim yok |
| O12 | ORTA | Çalışma sırasında 5 dk'dan uzun kopmada boşluk yalnız yeniden başlatınca doluyor | `feed.py:52`, `:190`, `:376`, `:395` |
| O13 | ORTA | CI yok (`.github/` yok) | repo kökü |
| D1 | DÜŞÜK | `os.replace` sonrası dizin fsync yok (KILL dosyası güç kesintisinde kaybolabilir) | `fileio.py:41-55`; `telegram.py:29-40`; `snapshot.py:68-75` |
| D2 | DÜŞÜK | Spool'da yarım son satır sonraki kayda yapışıyor; `spool_pending` kalıcı kalıyor | `ledger.py:1946-1990` |
| D3 | DÜŞÜK | Geri çekilmede jitter yok | `rest_public.py:94`, `:123` |
| D4 | DÜŞÜK | `current_stop` yuvarlanmamış değerle tutuluyor; gereksiz stop yenileme | `order_manager.py:306-328`, `:335` |
| D5 | DÜŞÜK [T] | min_qty / min_notional gönderim fiyatıyla değil, dolumda denetleniyor; `min_qty` hiç denetlenmiyor | `paper.py:249-255`, `:425`; `gates.py:230` |
| D6 | DÜŞÜK | Kill çıkışı her dakika yeni (`now`) kimlikle gönderiliyor | `engine.py:449` |
| D7 | DÜŞÜK | `kill_file` göreli yol; başka dizinden `kill` yanlış dosyayı yazar | `config/engine.base.json`; `cli.py:99-110` |
| D8 | DÜŞÜK | `trader_engine reconcile` komutu replay ve karar da çalıştırıyor (salt okuma değil) | `cli.py:92-94` |
| D9 | DÜŞÜK | 0 baytlık `state.sqlite` sessizce yeni durum sayılıyor | `state.py:166`, `:218` |
| D10 | DÜŞÜK | freqtrade yolu: `dry_run` değişmezi çalışma anında denetlenmiyor (yalnız testte); API kimlik bilgisi boş | `config_loader.py`; `config/base.json` |
| D11 | DÜŞÜK | Env dosyası izinleri tutarsız (health.env yorum 0600, kurulum 0640 grup) | `install.sh:142`; `trader-health.env.example:1` |
| D12 | DÜŞÜK | `install.sh`: pip paketleri sabitlenmemiş, `StrictHostKeyChecking=accept-new` | `install.sh:86`, `:108-109` |
| D13 | DÜŞÜK [P] | Cloudflare token'ı hesap çapında; Worker'da deneme sınırı yok | `docs/sunucu-kurulum.md`; `panel_worker.js` |
| D14 | DÜŞÜK [P] | learner ve twin aynı çiftleri işliyor; aynı canlı hesapta pozisyonlar birleşir | `config/engine.base.json:4` |
| D15 | DÜŞÜK [P] | Tahsis tavanı yok; boyut doğrudan hesap özsermayesinden hesaplanıyor | `gates.py:183` |
| D16 | DÜŞÜK | Yazar e-postası iki commit'te açıkta | `git log` (`7eddc5f`, `2c36f9b`) |

**Elenen yanlış alarmlar:**
- **Geçmişteki "secret" eşleşmeleri:** Hepsi test sahtesi ya da belge metni. Örnekler: `tests/test_telegram_*` içindeki `TOKEN = "123456:SECRETTOKEN…"` ve `cfSENTINELtoken99`.
- **"Mentor A5 `target_trade_risk` uygulanmamış":** Risk parametresi değişikliğidir, kapsam dışıdır. Değer zaten `HARD_LIMITS` ile kilitli.
- **"Gate yerel saat kullanıyor":** Feed, saat farkı 5 dk'yı aşarsa bar yazmıyor (`feed.py:144-153`). Kalan etki önemsiz.
- **"Telegram `audit.jsonl` yarım satır":** Okuyucu `ValueError`'ı yutuyor. Zararsız.
- **"TraderV1'de kill yok, bağlam bellekte":** freqtrade yolu fiilen kapalı. `docker-compose.yml`, `PlaceholderStrategy` çalıştırıyor. D10 altında not edildi.

---

## 1. Mimari bütünlük ve veri akışı

**Doğru çalışanlar**
- Akış: sinyal → kapı → `OrderManager` → `Broker` → olay → `PositionManager` → outbox → defter → `status.json`. Tutarlı.
- Açılış sırası: spool → outbox → parametre → snapshot → `resolve_unresolved` → mutabakat → replay (`engine.py:281-309`). **Mutabakat replay'den önce.**
- Durum: WAL, `synchronous=FULL`, açılışta `integrity_check` (`state.py:205-215`), hata olursa ROLLBACK.
- Adım hatasında state ve paper broker snapshot'tan geri yüklenir (`engine.py:389-399`).
- Gün başı değeri, giriş kilidi ve kill yeniden başlatmada sürer (kv ve dosya).

**K4 — Feed çalıştırılamıyor (KRİTİK)**
- **Yer:** `cli.py:113-119` `_cmd_feed`; `marketdata/feed.py` (`def main` yok); `deploy/` (feed birimi yok).
- **Senaryo:**
  1. `python -m trader_engine feed` çalıştırılır. `getattr(F, "main")` None döner; komut "bu sürümde 01 modülünden çalıştırılır" yazıp `EXIT_FAZ_B` ile çıkar.
  2. Feed birimi olmadığı için `market.sqlite` oluşmaz.
  3. Motor `StoreSource` açarken `DataError` alır ve exit 3 ile çıkar.
  4. `Restart=on-failure`, `RestartSec=20`, `StartLimitBurst=5/600s` ayarlarıyla birim yaklaşık 100 sn sonra kalıcı `failed` olur.
- **Finansal etki:** Doğrudan kayıp yok. Ancak canlı öncesi zorunlu 48 saatlik paper denemesi yapılamaz.
- **Düzeltme:**
```python
# marketdata/feed.py
def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="trader_engine feed")
    ap.add_argument("--config-dir", default="config")
    a = ap.parse_args(argv)
    f = Feed(FeedConfig.from_engine(load_engine_config(a.config_dir, "learner")), clock=WallClock())
    f.start()
    f.run_forever()
    return 0
```
```ini
# deploy/trader-feed.service
[Unit]
After=network-online.target
Wants=network-online.target
OnFailure=trader-health-fail@%n.service
StartLimitIntervalSec=0
[Service]
User=trader
WorkingDirectory=/opt/trader
Environment=PYTHONPATH=/opt/trader/src
ExecStart=/usr/bin/python3 -m trader_engine feed --config-dir config
Restart=always
RestartSec=20
RestartPreventExitStatus=3
```
- **Test:** `trader_engine feed --help` çıkış kodu 0 olmalı. `systemd-analyze verify deploy/trader-feed.service` hatasız geçmeli.

**O7 — Outbox tıkanması sessiz (ORTA)**
- **Yer:** `engine.py:410-417` `_post_commit`.
- **Senaryo:**
  1. Bir kayıtta kalıcı `LedgerError` oluşur; FIFO'nun başı tıkanır.
  2. Sonraki girişler ve çıkışlar deftere yazılmaz.
  3. Hata yalnız loglanır, girişler açık kalır.
- **Finansal etki:** Doğrudan kayıp yok. Defter tabanlı raporlar ve ders/veto girdileri kör kalır. Örnek: 10 işlem × 30 $ sonucu deftere hiç yazılmaz.
- **Düzeltme:**
```python
res = self.state.drain_outbox(self.ledger)
if getattr(res, "failed", 0):
    self._block("outbox_stuck")
elif self.state.kv_get("entries_blocked_reason") == "outbox_stuck":
    with self.state.tx():
        self.state.kv_set("entries_blocked_reason", None)
```
- **Test:** Defter `add` metodu `LedgerError` atarsa sonraki karar adımında `entries_blocked_reason == "outbox_stuck"` olmalı.

**D2, D9:** Tabloya bakın. Spool'da bozuk satırı `.bad` dosyasına taşıyın. Dosya var ama 0 baytsa açılışta hata verin.

## 2. Emir iletimi, çift işlem ve yarış koşulları

**Doğru çalışanlar**
- `make_client_id` deterministik: `sha1(bot|pair|side|bar_close|rol|seq)` (`order_manager.py:28-39`). Saat veya rastgelelik yok.
- Emir satırı POST'tan önce commit edilir. Satır zaten varsa POST yapılmaz (`order_manager.py:149-158`).
- Otomatik kör tekrar yok. Sorgu → bekleme → sorgu yapılır, ancak ondan sonra en fazla 1 yeniden gönderim olur (`max_attempts=2`). Başarısız sorgu "emir yok" sayılmaz (`:86-94`).
- Aynı karar ikinci kez verilmez (`decided` tablosu).
- Stop değişiminde önce yeni stop konur (kimlik POST'tan önce kalıcı yazılır), sonra eski iptal edilir. Gevşetme reddedilir (`order_manager.py:335-364`).
- İlk stop 2 denemede konamazsa pozisyon piyasa emriyle kapatılır ve girişler kilitlenir (`:303-319`).
- `flock(LOCK_EX|LOCK_NB)` ile tek süreç (`state.py:181-192`). Feed'in de kendi kilidi var (`feed.py:~170`). `threading` kullanılmıyor.

**K1 — Dış transaction içinde emir (KRİTİK, [FB])**
- **Yer:** `engine.py:546` `_decision_step` (`with self.state.tx():`), `engine.py:423` `_process_step`, `engine.py:754` `_periodic_reconcile`. `state.py:293-298` `barrier`. `order_manager.py:72` `_send`.
- **Senaryo:**
  1. Gerçek broker için `is_simulated=False` olur.
  2. Karar adımı dış `tx()` açar. İçinde `submit_entry` → `_send` → `barrier(allow_outer=False)` çağrılır.
  3. `StateError("POST oncesi commit citi…")` fırlar ve adım geri alınır.
  4. Aynı şey kill `force_exit` ve mutabakat `_install_stop` için de olur.
- **Finansal etki:** Fail-closed olduğu için yeni pozisyon açılmaz. Ancak canlıya geçildiğinde borsada var olan pozisyon için **ne kill ne stop onarımı** çalışır. Örnek: 3 pozisyon × 300 $ nosyonel, kaldıraç 3. %10'luk ters harekette, stop eksikse yaklaşık 90 $ zarar.
- **Düzeltme:** Karar adımını ikiye bölün. (a) tx içinde: niyet ve emir satırları commit edilir. (b) tx dışında: gönderim yapılır, sonuç küçük bir tx ile yazılır.
```python
def _decision_step(self, D):
    with self.state.tx():
        self.ensure_day_start(D)
        intents = self._plan_step(D)        # yalniz state yazar, emir satirlarini 'pending' commit eder
    for it in intents:                      # tx disi
        self.orders.dispatch(it)            # _send + kendi kucuk tx'i
```
- **Test:** `is_simulated=False` olan sahte bir broker ile `decision_step`, `StateError` atmadan `market_order` çağırmalı. POST anında emir satırı ayrı bir bağlantıdan okunabilmeli.

**K2 — Belirsiz giriş "kapandı" sayılıyor (KRİTİK, [FB][T])**
- **Yer:** `order_manager.py:177-200` `_unknown_path`; `:216-223` `_entry_failed`; `engine.py:675-679`; `engine.py:470-476` `_on_entry_fill`; `reconcile.py:78-82`.
- **Senaryo:**
  1. Giriş POST'u zaman aşımına uğrar. Emir borsada aslında kabul edilmiş ve dolmuştur.
  2. Borsa geç tutarlı olduğu için iki sorgu da "yok" döner. Sonra `_fail` → `_entry_failed` çalışır ve pozisyon `closed` yazılır.
  3. (Ya da sorgu başarısızdır: `engine.py:675` durum `filled/accepted` değil → `_close_unopened` → yine `closed`.)
  4. Dolum olayı gelir. `_on_entry_fill` "beklenmeyen giriş dolumu" logu yazar ve **stop koymaz**.
  5. Mutabakat `unknown_position` görür. Yalnız bayrak koyar ("işlem yapılmadı").
- **Finansal etki:** Stopsuz pozisyon. Örnek: 1.000 $ × `max_notional_ratio=1.0` = 1.000 $ nosyonel, ters %25 iğne → yaklaşık 250 $ kayıp, ya da izole marjın tamamı.
- **Düzeltme:**
```python
# engine._enter
if res.status == "rejected":
    self._close_unopened(cur, now)          # yalniz kesin ret
# else: 'opening' kalsin; resolve_unresolved surdursun
# order_manager._entry_failed: 'unknown_unresolved' ise pozisyonu kapatma, satiri 'unknown' birak
# reconcile: unknown_position icin koruma
if self.cfg.protect_unknown:
    self._close_unknown(bp)                  # reduce-only piyasa kapanisi + block
```
- **Test:** Sahte broker ilk POST'ta `BrokerUncertain` atsın, iki sorgu `None` dönsün, sonra `fill` olayı gelsin. Beklenen: pozisyon `closed` olmamalı. Dolum sonrası stop emri ya da reduce-only kapanış gönderilmeli.

**O1 — Kesin ret de belirsiz sayılıyor (ORTA, [FB])**
- **Yer:** `order_manager.py:77-81`.
- **Senaryo:** Borsa kesin bir ret döner (yetersiz marj, -2019). `except Exception` bunu `None` yapar. Ardından 2 sorgu, 2 sn bekleme, yeniden gönderim ve `order_unknown` kilidi gelir.
- **Finansal etki:** Kayıp yok. Gürültü oluşur ve O6 ile birleşince kilit kendiliğinden kalkar.
- **Düzeltme:** `class BrokerRejected(BrokerError)` tanımlayın. `_send` içinde `except BrokerRejected as e: return OrderResult(status="rejected", detail=str(e))` yazın. Canlı broker sözleşmesine şunu ekleyin: "kesin 4xx = BrokerRejected".

**O2, O3:** Tabloya bakın. Mutabakatta, bir çiftte `stop_client_id` dışında kalan stopları iptal edin. `partially_filled` ekleyin: kısmi dolan girişte kalanı iptal edin ve `pos.qty`'yi dolan miktara çekin.

**D6:** Kill çıkış kimliğinde `now` yerine `kill_seen_at` kullanın.

## 3. Piyasa kuralları, yuvarlama, hassasiyet

**Doğru çalışanlar**
- Stop fiyatı riski artırmayan yöne yuvarlanır (`numeric.py:641 round_tight`; long yukarı, short aşağı). `Decimal(repr(x))` kullanılır.
- Miktar adıma göre aşağı yuvarlanır (`risk.py:222`, `rules.py:566`).
- Dolum sonrası risk tekrar doğrulanır (`position_manager.py:122`).
- Çıkış ve stop emirleri `reduce_only=True`. Paper da bu kuralı uygular (`paper.py:290-298`).
- min_notional yoksa `RulesError` atılır ve o çifte giriş yapılmaz (uydurma 5 $ yok).

**D5 — Denetim gönderim fiyatıyla değil (DÜŞÜK, [T]):** Boyutlama `ref` fiyatıyla yapılıyor. min_notional dolumda denetleniyor, `min_qty` hiç denetlenmiyor. Canlı gönderimde fiyat ve miktar `Decimal.quantize` ile string olarak yazılmalı. Gönderimden hemen önce şu kontrol eklenmeli: `qty >= min_qty and qty*px >= min_notional`.

**Hisse senedi / TradFi:** **Kapsam dışı.** Sistem yalnız 7/24 kripto vadeli (USDT-M) işliyor. Seans saati ve devre kesici yok.

## 4. Paper ile gerçek piyasa farkları

**Paper'da simüle edilenler:**
- Taker komisyonu (0,0005)
- Giriş, çıkış ve stop kayması (2 / 2 / 5 bps)
- Funding
- Basit izole likidasyon (sabit MMR 0,004, `risk.py:28`)
- Dolumda min_notional reddi
- reduce-only reddi
- Mark tetiği
- `FaultPlan` ile yapay hatalar

**Simüle edilmeyenler:**
- Kısmi dolum
- Gecikme ve emir defteri derinliği
- Rate limit
- Kaldıraç reddi
- ADL
- Kademeli MMR
- Geç tutarlı sorgular

**Canlıda sapacak yerler:**
- K1: dış tx yalnız paper'da serbest.
- K2: paper, belirsiz girişin borsada dolma yolunu canlıdaki gibi üretmez.
- O3: kısmi dolum.
- Küçük altcoinlerde (ADA, DOGE, AVAX) MMR 0,004'ten yüksek olabilir; likidasyon fiyatı ve `liq_safety_factor=1.5` hesabı sapar [T].

**Risk limitleri:** Paper ve canlı için aynı `trader_core.risk` (`LOCKED_CFG`, `HARD_LIMITS`) kullanılıyor. Canlı kip olmadığı için "aynı mı" sorusu şimdilik tasarım düzeyinde evet.

## 5. Veri bütünlüğü ve API hata yönetimi

**Doğru çalışanlar**
- **429:** `Retry-After` kadar beklenir; toplam bekleme tavanı 300 sn (`rest_public.py:106-115`).
- **418/451:** Tekrar yok, `ExchangeBan` atılır. Feed, ban süresince istek atmaz (`feed.py:299-307`).
- **Zaman aşımı ve 5xx:** Her istekte 20 sn zaman aşımı. 5xx için 5 denemeli üstel geri çekilme.
- **Ağırlık izleme:** `X-MBX-USED-WEIGHT-1M` ≥ 1800 ise dakika sonuna kadar beklenir.
- **Bozuk mum:** NaN, inf, 0 ve negatif değerler; `high<low`; closeTime tutarsızlığı; kapanmamış mum. Hepsi reddedilir (`rest_public.py:231-242`, `store.py:65-68`). Çakışan bar eski değeri korur.
- **Bayat veri:** `stale_data` kapısı girişleri kapatır (`gates.py:162`).
- **Atomik yazım:** tmp + fsync + `os.replace` (`fileio.py:41-55`).
- **WS:** Kullanılmıyor, yalnız REST yoklama var. Ping bekçisi yerine `last_ok` meta kaydı ve bayatlık kapısı var.

**O10 — Açılışta geçici hata servisi durduruyor (ORTA)**
- **Yer:** `feed.py:180` `start()` → `_measure_offset()` korumasız. `rest_public.py:105` `r.json()` bozuk gövdede `ValueError` atar.
- **Senaryo:** Sunucu açılırken ağ ~100 sn gelmez. 5 yeniden başlatma da başarısız olur, birim kalıcı `failed` kalır. Toparlanma elle yapılır.
- **Düzeltme:**
```python
i = 0
while True:
    try:
        self._measure_offset()
        break
    except ExchangeBan:
        raise
    except (ExchangeError, ValueError):
        self.clock.sleep(min(2 ** min(i, 6), 60) * (0.5 + random.random()))
        i += 1
```
`rest_public.py:105` için `ValueError` yakalanmalı ve `ExchangeError("bozuk JSON")` ile döngüye girilmeli. Birimde `StartLimitIntervalSec=0` olmalı.

**O11 — Ban sonrası yeniden başlatma (ORTA, [P]):** `RestartPreventExitStatus=3` + alarm + elle başlatma mı, yoksa süreç içinde `retry_after` kadar uyumak mı? Politika kararıdır. Önerim: süreç içinde uyusun, üst sınır 1 saat olsun. Aşılırsa çıkış 3 ve `RestartPreventExitStatus=3`.

**O12 — Boşluk doldurma (ORTA):** `_minute` içinde son bar ile şimdiki an arasındaki fark `minute_fetch_limit`'i aşarsa `_backfill_series` çağrılmalı.

**D1, D3:** Tabloya bakın.

## 6. Risk yönetimi ve acil durdurma

**Doğru çalışanlar**
- Günlük kayıp limiti her kararda yeniden hesaplanır. Yeniden başlatma onu sıfırlayamaz (`gates.py:183`, `risk.py:283`).
- Kill dosyası kalıcıdır ve okunamazsa etkin sayılır (`killswitch.py:260-272`).
- `status.write` ve heartbeat hataları yutulur. `_kill_step` status yazımından önce commit edilir. Kozmetik bir adım kill'i kesmez.
- Bakiye okunamazsa giriş yapılmaz (istisna yakalanıp giriş atlanır). `equity<=0` olursa ret.
- Kaldıraç 3, izole marj. Likidasyon mesafesi ≥ 1,5 × stop mesafesi denetlenir (`risk.py:308`). `HARD_LIMITS` gevşetilemez.

**K3 — Kill veri akışına bağlı (KRİTİK)**
- **Yer:** `engine.py:442-452` `_kill_step`. Yalnız `_process_step` ve `_decision_step` içinden çağrılıyor. `advance_to` veri bayatsa erken dönüyor (`:713-718`). `run_forever` yalnız `ClockError` yakalıyor (`:741`).
- **Senaryo:**
  1. Feed 30 dk durur (ban veya ağ).
  2. Kullanıcı Telegram'dan DUR der; `shared/KILL` yazılır.
  3. `advance_to` dakika ilerletmez, `_kill_step` hiç çalışmaz. Açık pozisyonlar kapanmaz.
- **Finansal etki:** Kill'in asıl gerektiği an (veri veya borsa sorunu) tam da çalışmadığı andır. Örnek: 3 pozisyon × 300 $, %25 iğne → yaklaşık 225 $. Stop da yoksa (K2) daha fazlası.
- **Düzeltme:**
```python
# run_forever dongusu, advance_to'dan ONCE ve veriden bagimsiz
try:
    self._kill_watchdog(now)                # canlida tx disi gonderim (K1)
except StateError:
    raise
except Exception as e:  # noqa: BLE001
    log.critical("kill bekcisi: %r", e)
```
- **Test:** Kill etkin, `view` hiç yeni dakika döndürmüyor, 1 açık pozisyon var. Beklenen: tek döngü sonunda `force_exit` emri gönderilmiş olmalı.

**O4 — Gün başı cüzdan, ölçüm özsermaye (ORTA)**
- **Yer:** `engine.py:232` (`account().wallet`) ve `gates.py:183` (`account().equity`).
- **Senaryo:** Gece yarısı cüzdan 1.000 $, açık pozisyonda +50 $ gerçekleşmemiş kâr var. Gün içinde özsermaye 951 $'a iner.
  - Ölçülen kayıp: −%4,9 (limit −%5 olduğu için girişler açık kalır).
  - Gerçek düşüş: 1.050 → 951, yani −%9,4.
- **Düzeltme:** `kv_set("day_start:"+day, self.broker.account().equity)`. `docs/motor/05-engine-runner.md` belgesi de güncellenmeli.
- **Altın test:** wallet=1000, unrealized=+50 → `day_start=1050`. equity=995 → kayıp %5,2 → giriş reddi.

**O5 — Zirveden düşüş yok (ORTA, [P]):** `day_peak` kv'de tutulmalı. `equity < peak × (1−X)` ise `_block("dd_lock")` ya da kill. X değeri politika kararıdır.
- Altın test (X=%7): day_start 1.000, peak 1.100, equity 1.020 (zirveden −%7,3) → giriş reddi. Günlük limit −%5 ise bu durumda henüz tetiklenmez (−%5 eşiği 950 $).

**O6 — Kilit yönetimi (ORTA, [P]):**
- **Yer:** `reconcile.py:158-167`. Mutabakat kendi bulgusu yoksa `order_unknown` ve `exit_unknown` kilitlerini kaldırıyor; `unresolved_orders()` dolu olsa bile.
- **Düzeltme:** Kilit kaldırılmadan önce şu koşullar sağlanmalı: `not self.state.unresolved_orders()` ve `closing`+`failed` durumunda çıkış yok. Ayrıca `trader_engine unblock --reason …` komutu eklenmeli. `engine_errors` için temizleme yolu yazılmalı.
- Canlıda belirsiz emirden sonra kilidin elle mi kalkacağı politika kararıdır. **Önerim: elle, Telegram onayıyla.**
- **Test:** Çözülmemiş emir varken `reconcile.run`, `order_unknown` kilidini silmemeli.

**O8, O9:** Tabloya bakın.
- **O8:** Mutabakatta `abs(p.qty-bp.qty) > tol or p.side != bp.side` ise fatal `reconcile_qty_mismatch`. `closing` durumundaki pozisyon da stop denetimine alınmalı.
- **O9:** Kill döngüsünde her pozisyon için ayrı `try/except` olmalı; `StateError` dışındaki hatalar loglanıp `continue` edilmeli. Test: iki pozisyon var, ilkinde istisna atılıyor; ikincisi yine kapanmalı.

**Mevduat ve çekim [P][T]:** Gün içi mevduat, `equity − day_start` farkında kâr gibi görünür. Örnek: 500 $ yatırılırsa 500 $'a kadar gerçek zarar ölçülmez. Binance `TRANSFER` gelir kayıtlarıyla `day_start` düzeltilmeli.

**Tahsis tavanı (D15) [P]:** Boyut doğrudan hesap özsermayesinden hesaplanıyor. Futures cüzdanında 1.000 $'dan fazla para olursa risk de onunla büyür. Önerim: `equity=min(equity, CAP)`; başlangıçta CAP = 1.000 $.

## 7. Public repo güvenlik denetimi

**Doğru çalışanlar**
- `git log -p --all` ile tüm geçmiş tarandı. Bakılanlar: özel anahtar, AWS/GitHub/`sk-` desenleri, Telegram bot token deseni, Slack/Discord webhook. **Gerçek secret yok.** Eşleşmelerin hepsi test sahtesi ya da belge metni.
- `.env`, `*.sqlite`, defter ve özsermaye kayıtları commit edilmemiş. `research/runs/*.json` yalnız backtest çıktısıdır.
- Anahtarlar `/etc/trader-*.env` dosyalarından `EnvironmentFile` ile okunuyor. Veto ve Cloudflare env dosyaları `0600 root:root` (`install.sh:142-146`).
- `config_loader` dosyada `exchange.key` / `secret` dolu olmasını reddediyor.
- Panel sürecinde `EnvironmentFile` yok.
- Telegram token'ı `mask()` ile loglardan temizleniyor. Alt sürecin ortamından da çıkarılıyor (`telegram.py:67-75`, `:765`).
- Telegram yetki kontrolü: `chat.type=private`, `chat.id == cfg.chat_id`, `from.id == chat.id`, `not is_bot` (`telegram.py:572-574`). Hem mesaj hem callback yolunda uygulanıyor. Onay kodu `hmac.compare_digest` ile karşılaştırılıyor.
- Panel Worker: secret yoksa her istek 401 alır (fail-closed). Karşılaştırma sabit zamanlı. CSP başlığı var.
- **Para çekme yetkisi:** Binance anahtarı henüz hiç kullanılmıyor. Canlı broker yazılırken açılışta `GET /sapi/v1/account/apiRestrictions` çağrılmalı; `enableWithdrawals=true` ise motor başlamamalı. Bu yeni bir kuraldır **[P]**.
- **CI:** Yok. Bu yüzden secret'ların iş seviyesinde açık kalma riski de yok.

**Bulgular:** D11, D12, D13 ve D16 tabloda. Yazar e-postasının açık kalmasını istemiyorsanız ileride GitHub noreply adresi kullanın. Geçmişi yeniden yazmak ayrı bir karardır.

---

## Testnet doğrulama listesi

1. **Yinelenen `newClientOrderId`:** Aynı kimlikle iki MARKET emri gönderin. Beklenen: ikincisi hata kodu alır ve `duplicate_client_id` eşlemesi çalışır.
2. **Zaman aşımından sonra sorgu:** Emri gönderdikten hemen sonra (0, 200 ms, 1 sn, 2 sn) `GET /fapi/v1/order?origClientOrderId=` sorgulayın. Geç tutarlılık penceresini ölçün (K2'nin tetik koşulu).
3. **STOP_MARKET + reduceOnly:** (a) Pozisyon yokken gönderin. (b) Tetik fiyatı geçmişken gönderin (-2021). (c) `workingType=MARK_PRICE` ile tetiği gözleyin. (d) LOT_SIZE ile MARKET_LOT_SIZE adım farkını kontrol edin.
4. **Kısmi dolum:** İnce bir çiftte büyük bir MARKET emriyle `PARTIALLY_FILLED` durumu ve olay sırası.
5. **Eski stop iptali ve yeni pozisyon:** Stop A'yı bırakın, stop B'yi koyun, pozisyonu kapatın, aynı yönde yeni pozisyon açın. Stop A yeni pozisyonu etkiliyor mu? (O2)
6. **reduce-only çıkışta min_notional muafiyeti:** Min değerin altındaki bir kalıntıyı kapatmayı deneyin.
7. **Kaldıraç ve marj:** `leverage=3`, `marginType=ISOLATED` ayarlayın. Açık pozisyon varken marj tipi değiştirilmeye çalışılınca ne oluyor?
8. **MMR kademesi:** ADA, DOGE ve AVAX için `leverageBracket`. 0,004 varsayımını ve likidasyon fiyatı hesabını karşılaştırın.
9. **429 ve 418:** `Retry-After` her zaman var mı, değeri saniye mi?
10. **`X-MBX-USED-WEIGHT-1M`:** klines, markPriceKlines ve premiumIndex yanıtlarında bu başlık geliyor mu?
11. **Dolum bildirim gecikmesi:** Giriş dolumundan stop kabulüne kadar geçen süre. Stopsuz pencereyi ölçün.
12. **`TRANSFER` geliri:** Mevduatın özsermaye ve `income` kayıtlarında görünme anı (O4 ve mevduat).
13. **API anahtarı izinleri:** `apiRestrictions` yanıtında `enableWithdrawals` ve `ipRestrict` alanları.

## Canlıya geçiş öncesi sıralı yapılacaklar

Her madde ayrı bir PR'dır. Hesap değiştiren düzeltmeler (★) altın örnek testi olmadan birleştirilmemeli.

1. **PR-1 Feed giriş noktası ve birimi (K4, O10, O11):** `feed.main`, `trader-feed.service`, açılışta tekrar denemeli başlatma, `rest_public` JSON hatası. Ardından 48 saatlik paper denemesi başlayabilir.
2. **PR-2 Kill bekçisi (K3, O9):** Veriden bağımsız kill; pozisyon başına hata yalıtımı. Test: bayat feed + kill → kapanış.
3. **PR-3 ★ Gün başı = özsermaye (O4):** Altın test: 1000 + 50 gerçekleşmemiş → `day_start=1050`.
4. **PR-4 Kilit yönetimi (O6, O7) [P]:** Çözülmemiş emir varken kilit kaldırılmasın; `outbox_stuck` kilidi; `unblock` komutu.
5. **PR-5 Mutabakat sıkılaştırma (O8, O2):** Miktar ve yön kıyası; `closing` pozisyonda stop denetimi; çiftte fazla stop iptali.
6. **PR-6 Feed boşluk doldurma ve jitter (O12, D3).**
7. **PR-7 Dayanıklılık küçükleri (D1, D2, D7, D8, D9):** Dizin fsync, spool karantinası, mutlak kill yolu, salt-okur `reconcile`, 0 bayt kontrolü.
8. **PR-8 CI (O13):** pytest (`pyarrow` kurulu), `compileall`, `shellcheck deploy/*.sh scripts/*.sh`, `systemd-analyze verify deploy/*.service`. Secret'lar gerekmez.
9. **Politika kararları (kullanıcı onayı):**
   - O5: zirveden düşüş eşiği.
   - D15: tahsis tavanı (öneri: 1.000 $).
   - O6: belirsiz emirde kilit elle mi kalksın? (öneri: elle)
   - D14: learner/twin canlıda ayrı alt hesapta mı, yoksa yalnız learner mı canlı? (öneri: ilk aşamada yalnız learner)
   - Stopsuz pencere toleransı (öneri: 10 sn; aşılırsa reduce-only kapanış ve kilit).
   - Para çekme yetkili anahtarı reddetme kuralı.
   - D13: Cloudflare için ayrı hesap.
10. **PR-9 (Faz B) Canlı broker iskeleti ★ (K1, K2, O1, O3, D5, D6):**
    - Emir gönderimi tx dışında.
    - Belirsiz girişte pozisyon `opening` kalsın.
    - `unknown_position` için koruma.
    - `BrokerRejected` sınıfı.
    - `partially_filled` durumu.
    - Gönderim fiyatıyla `Decimal` denetimi.
    - Kill çıkışı için sabit kimlik.
    - Altın testler: K2 senaryosu, kısmi dolum, kesin ret.
11. **Testnet turu:** Yukarıdaki 13 madde. Sonuçlar `docs/` altına yazılmalı.
12. **Sınırlı canlı:** Yalnız learner, düşük tahsis tavanı. Kademeli artırma politikası kullanıcı tarafından belirlenmeli.
