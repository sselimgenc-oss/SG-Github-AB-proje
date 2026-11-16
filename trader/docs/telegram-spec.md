# Telegram: bildirim, komut ve günlük rapor — arayüz ve kurallar (spesifikasyon v1, 16 Kasım 2026)

Plan maddesi 18. Bu belge kod, test ve commit içermez; testler bu belgeden yazılır. Biçim `saglik-spec.md` ile aynıdır; çelişkide `ders-spec.md`, `saglik-spec.md`, `motor/05-engine-runner.md` §8 geçerlidir. Her belirsizlikte **fail-closed** (yetki, onay, kod doğrulaması) ama **ticareti asla bloke etmez**: Telegram modülü ne motor ne defter ne risk yoluna girer.

## 0. Kaynaklar (CT `copytrade/canli/telegram.py`; yalnızca okundu, içe aktarılmadı, çalıştırılmadı)

| CT parçası | Karar | Bizde |
|---|---|---|
| Bot API'ye doğrudan HTTPS, enjekte edilebilir `post(url, json)` | **Fikir alınır** (kod bağımlılığı yok; python-telegram-bot yok) | `requests` + enjekte edilebilir `http_post` (testte sahte sunucu) |
| Token/chat yalnız ortamdan; yoksa kanal kapalı, motor çökmez | Alınır | Bölüm 7 |
| `yetkili_mi`: `chat.id == chat_id` zorunlu; özel sohbette ek `from.id == chat_id`; grupta `is_bot` reddi | **Doğrudan alınır** (K-37) | Bölüm 3 (çoklu kimlik listesi) |
| Eski komut yürütülmez (motor başlamadan önce ya da > 15 dk), "İŞLENMEDİ" yanıtı | Alınır; **bizde sıkılaşır**: pencere 120 sn, onay kodu 60 sn | Bölüm 4.2 |
| Kalıcı `offset`, yürütme bitince onay | Alınır | Bölüm 4.1 |
| Önemli mesajda 2/5/15 sn yeniden deneme + 429 `retry_after` | Alınır | Bölüm 2.2 |
| `/dur /devam /kapat /durum` | Adlar bizim kararlarla değişir (Bölüm 5) | Bölüm 5 |
| `msg_*` TR biçimleyicileri (`tr_sayi`, `tr_yuzde`, tek ikon başlığı) | Fikir alınır, kod kopyalanmaz | Bölüm 6 |

## 1. Süreç ve modül düzeni

Tek modül `src/trader_core/telegram.py` (yalnız standart kütüphane + `requests`; `trader_engine` yalnız `Killswitch`/`fileio` için içe aktarılır). Süreçler ve yazma sahipliği:

| Parça | Süreç | Yazdığı |
|---|---|---|
| `TelegramClient` (ham Bot API: `send_message`, `get_updates`) | kütüphane | — |
| `TelegramNotifier` (outbound; `NOTIFIER_FACTORIES["telegram"]` ve health `Notifier` olarak kaydolur) | çağıran süreçte (ders/health/veto/bütçe tek seferlik süreçleri) | `var/telegram/outbox/` (spool) |
| `scripts/telegram_run.py daemon` (komut dinleyici + outbox boşaltıcı) | **tek** uzun ömürlü süreç, `trader-telegram.service` | `var/telegram/{offset.json,pending.json,audit.jsonl}`, `shared/KILL` (yalnız Bölüm 5) |
| `scripts/telegram_run.py report` (günlük rapor) | tek seferlik, `trader-telegram-report.timer` 21:00 `Europe/Istanbul` | outbox |

Neden ayrı daemon: `getUpdates` tek tüketici ister (iki süreç aynı bot için aynı anda poll ederse 409 döner). Tek seferlik süreçler (ders, health) yalnız **gönderir**; poll yalnız daemon'dadır. Bütçe ve veto olayları `budget.pending_events()` (at-least-once) ile daemon'un outbox döngüsünden çekilir; başarılı gönderimden sonra `ack_events` (butce-spec §10).

## 2. Giden mesaj API'si

### 2.1 Arayüz

```
Severity: INFO | WARN | CRIT
class TelegramNotifier:
    def send(self, alert: health.Alert) -> bool                 # saglik-spec §5 (Notifier)
    def notify(self, notice: lesson.LessonNotice) -> bool       # LessonNotifier
    def request_approval(self, req: lesson.ApprovalRequest) -> bool   # LessonNotifier
    def send_text(self, text: str, severity: Severity, dedup_key: str | None = None) -> bool   # veto/bütçe/rapor
```
Dönüş kuralı (ders-spec Revizyon 3 ile aynı): **`True` yalnız Telegram `ok:true` ve `message_id` döndürdüyse.** Disk spool'una yazmak `False`'tur (çağıran yeniden dener / `undelivered` kalır). İstisna asla fırlatılmaz. `build_notifier(cfg, env)` fabrikası: token/chat eksikse `None` döner (çağıran bunu başarısızlık sayar; ders servisi çıkış 1). `ApprovalRequest` mesajı: başlık, `param from→to`, `reason_code`, kanıt özeti, `expires_at`, ve satır içi komutlar `/onayla <request_id>` / `/reddet <request_id>`; ayrıca inline düğmeler (Bölüm 5.4).

### 2.2 Gönderim kuralları

- Uç nokta: `https://api.telegram.org/bot<TOKEN>/sendMessage`, `disable_web_page_preview=true`, **`parse_mode` yok** (düz metin; Markdown kaçış hatası mesajı düşürmesin). Zaman aşımı bağlantı 5 sn / okuma 10 sn.
- Yeniden deneme: ağ hatası/5xx → 2, 5, 15 sn; `429` → `parameters.retry_after` (tavan 60 sn). `400/401/403` (kalıcı) → yeniden deneme yok, `False`, `CRIT` günlük satırı (token iptal/yanlış chat). Tek `send` çağrısı toplam ≤ 30 sn; ders/health süreçlerini asılı bırakmaz.
- Hız sınırı: kanal başına ≤ 1 mesaj/sn, ≤ 15 mesaj/dk (Telegram sınırının altı); aşan `INFO` mesajlar tek "N mesaj birleştirildi" özetine toplanır; `CRIT` birleştirilmez, sıraya girer. Aynı `dedup_key` 10 dk içinde bir kez (spool'da da).
- Boyut: Telegram sınırı 4096 karakter; bizim sınırımız **3500**. Aşan mesaj son satırda "(kısaltıldı, N satır)" ile kesilir; kesme satır sınırında yapılır, onay kodu/komut satırı asla kesilmez (gövde kısalır, komut satırı sona sabitlenir).
- Sır/biçim: gövde `scrub()` (ders-spec) ve `sanitize_text` ile geçer; token, HMAC anahtarı, API anahtarı, tam yol metinde olmaz. Kullanıcı kaynaklı metin (LLM gerekçesi dahil) komut gibi görünen `/` ile başlayan satırlarda başına boşluk eklenerek etkisizleştirilir.
- Sessizlik: `INFO` `disable_notification=true`; `WARN`/`CRIT` sesli. Gece saat dilimi: bildirim kuralı yoktur (CRIT her zaman sesli).

### 2.3 Telegram kapalıyken (spool)

Gönderim `False` ise (ağ, 5xx, 429 süresi aşıldı) mesaj `var/telegram/outbox/<utc_ns>-<sha8>.json` olarak **atomik** yazılır (`fileio.atomic_write_json`; `ReadWritePaths`). Daemon her 30 sn outbox'ı eski→yeni sırayla boşaltır; başarılı gönderilen dosya silinir. Sınırlar: ≤ 500 dosya / ≤ 5 MiB; aşılırsa en eski `INFO` düşer, sonra `WARN`; `CRIT` düşmez (sayaç `dropped` raporda). 24 saatten eski `INFO` spool'dan atılır; `CRIT`/onay talepleri yaşar (onay talebi kendi `expires_at`'ında süresi dolmuş olarak işaretlenir ve gönderilmez). Spool yazılamıyorsa (disk dolu) yalnız günlük (journal) satırı; **hiçbir durumda istisna ya da bekleme motor/ders/health yoluna sızmaz** — motor Telegram'ı hiç içe aktarmaz.

## 3. Yetkilendirme

- `TELEGRAM_CHAT_IDS` (virgülle ayrılmış tam sayılar; ilk Faz için tek kimlik beklenir). Boş/eksik → komut kanalı **kapalı** (yalnız giden mesaj mümkünse), daemon "komut kapalı" açılış satırı yazar.
- Kabul: `message.chat.id ∈ izinli` **ve** (özel sohbette) `message.from.id == chat.id`; grupta `from.is_bot` değilse ve `from.id ∈ TELEGRAM_USER_IDS` (grup kullanılırsa zorunlu ikinci liste). `callback_query` için aynı kontrol `callback_query.from.id` + `message.chat.id` üzerinden.
- Diğer her güncelleme: **yanıtsız yok sayılır** (kaçak bilgi yok, bot varlığı doğrulanmaz) ve `audit.jsonl`'a `{event:"unauthorized", chat_id_prefix, update_id, cmd:ilk 20 karakter}` yazılır; tam kimlik/metin yazılmaz. Dakikada > 10 yetkisiz güncelleme → tek `WARN` (kullanıcıya) "yetkisiz komut denemesi" (hız sınırlı).
- `allowed_updates=["message","callback_query"]`; `edited_message`, kanal, inline sorgu ve diğerleri hiç alınmaz.
- Kimlik değerleri günlükte yalnız son 3 hane ile görünür.

## 4. Gelen komut döngüsü

### 4.1 Long polling (webhook yok, açık port yok)

`getUpdates(offset, timeout=30, allowed_updates=…)`, istemci okuma zaman aşımı 40 sn. Dış bağlantı yalnız `api.telegram.org:443` (giden). Döngü hatasında üstel bekleme 1→60 sn (tavan), `409 Conflict` (başka poller) → `CRIT` günlük + 60 sn bekle. `offset` = son işlenen `update_id + 1`, `var/telegram/offset.json`'a **komut yürütüldükten ve audit yazıldıktan sonra** atomik yazılır (yürütme çökmesi → aynı update yeniden gelir; komutlar idempotenttir, Bölüm 5). Aynı `update_id` (yeniden başlatma/yeniden teslim) bellekte ve `audit.jsonl` son 1000 satırında bakılarak ikinci kez **yürütülmez**. Telegram yalnız son 24 saatin güncellemelerini saklar; daemon uzun süre kapalı kaldıysa ilk turda gelenler "bayat" sayılır (4.2).

### 4.2 Bayatlık

`message.date` ile şimdi arasındaki fark > **120 sn** ya da mesaj daemon başlangıcından önceyse: **hiçbir komut yürütülmez**; tek yanıt "işlenmedi, yeniden gönder (yaş: N sn)". Bu kural `/hepsini_kapat` onay kodu girişi için de geçerlidir (4.3 sürelerinden bağımsız ek sınır).

### 4.3 Onay durumu

`var/telegram/pending.json` (atomik): `{token_hash, action, chat_id, created_at, expires_at}` kayıtları; kod düz metin saklanmaz (SHA-256 + tuz). Süresi dolmuş kayıtlar her turda temizlenir. Yeniden başlatma sonrası **yaşar** (TTL'i dolmadıysa), böylece kod gönderilmiş ama süreç yeniden başlamışsa yine geçerli kalır; ancak bayat güncelleme kuralı (4.2) geçerliliğini korur.

## 5. Komutlar

Komut adı = ilk sözcük (küçük harf, `@botadı` eki atılır); bilinmeyen komut → geçerli komut listesi yanıtı. Tüm yürütmeler `audit.jsonl`'a (`update_id`, `cmd`, `sonuç`, `ts`) yazılır; **Telegram'dan gelen hiçbir metin emir, pozisyon, risk ya da parametre değeri olarak yorumlanmaz** (`/onayla` yalnız ders servisinin kendi `request_id`'sini çözer).

| Komut | Etki | Onay |
|---|---|---|
| `/yardim` | komut listesi | yok |
| `/durum` | Bölüm 6.2 kısa durum (status.json, salt okunur) + `kill` durumu | yok |
| `/rapor` | günlük raporu şimdi üretir (Bölüm 6) | yok |
| `/hepsini_kapat` | killswitch'i **kurar** (Bölüm 5.1) | 2 adım |
| `/devam` | `shared/KILL`'i **kaldırır** (girişler bir sonraki karar adımında açılır) | 2 adım (`/devam` → kod) |
| `/onayla <id>` · `/reddet <id>` | `LessonService.resolve_request(id, approve, actor_ref="telegram:<chat_id son 3>")` | id doğrulaması (5.4) |
| `/durdur` | **Şimdilik yok** (aşağı) | — |

**`/durdur` (yalnız yeni girişleri durdur):** mevcut `Killswitch` yalnız `set/clear` sunar ve etkin iken motor açık pozisyonları da `force_exit` eder (05 §8.1); "girişleri durdur ama pozisyonları tut" bir **yeni mekanizmadır** (ör. ayrı `PAUSE` dosyası = kapı 7'ye yeni satır) ve `trader_engine` değişikliği gerektirir; kullanıcı onayı olmadan eklenmez (açık soru 1). Bu sürümde `/durdur` "desteklenmiyor, tam kapatma için /hepsini_kapat" yanıtı verir. `/devam` yalnız `KILL`'i kaldırır; `PAUSE` olmadığı için başka bir şey açmaz.

### 5.1 `/hepsini_kapat` iki adımlı onay

1. Yetkili kullanıcı `/hepsini_kapat` yazar (ya da "hepsini kapat" metni; boşluk/büyük-küçük harf ve `ı` farkı normalize edilir; **yalnız tam eşleşme**, cümle içinde geçerse yürütülmez).
2. Daemon rastgele 6 karakterli kod üretir (`secrets`, belirsiz harfsiz alfabe: `ABCDEFGHJKMNPQRSTUVWXYZ23456789`), mesaj: "Tüm pozisyonlar piyasadan kapatılacak ve yeni giriş durdurulacak. Onay için 60 sn içinde yanıtla: /onay KOD". Kod `pending.json`'a yazılır (TTL **60 sn**, tek kullanımlık, yalnız aynı `chat_id`'den).
3. `/onay KOD` doğruysa ve TTL içindeyse: `Killswitch(path=cfg.kill_file).set(by="telegram:<son3>", reason="user_cmd")` çağrılır (**tek yol**: motorun zaten izlediği dosya; yeni bir iptal/kapatma kodu yok). Yanıt: "KILL kuruldu; motor pozisyonları kapatıyor". Yanlış kod → kayıt silinir (tek deneme), "iptal" yanıtı; süre dolarsa "süre doldu, yeniden başlat".
4. Sonuç doğrulama: 10 sn sonra `status.json`'dan `kill` ve `kill_state` okunur; 5 dk içinde `kill_state != "flat"` ise `CRIT` "kapatma tamamlanmadı". Daemon pozisyon kapatmaz; yalnız dosyayı kurar ve izler.
5. Yeniden `/hepsini_kapat` zaten etkinken: idempotent "KILL zaten etkin (<kim>, <ne zaman>)" yanıtı.

**Telegram çökmüşken** durdurma yolu: operatör sunucuda `python -m trader_engine kill --by me --reason manual` çalıştırır ya da `shared/KILL` dosyasını elle yazar (05 §9). Telegram ile aynı dosya, aynı davranış; Telegram'a bağımlılık yoktur. `/devam` aynı biçimde `kill --clear` karşılığıdır.

### 5.4 Ders önerileri

`ApprovalRequest.request_id` (`lr-<gün>-<proposal_id>`) mesajda görünür. `/onayla <id>`/`/reddet <id>`: id biçimi `^lr-\d{4}-\d{2}-\d{2}-\d+$` değilse reddedilir; daemon `LessonService.resolve_request` çağırır (ders-spec: süresi dolmuş/bayat/bilinmeyen → `ResolveResult.status` ayrı yanıtla bildirilir; çift onay idempotent). Inline düğme `callback_data="ok:<id>"` / `"no:<id>"` aynı yolu kullanır; düğmeye basılınca mesaj düzenlenip sonuç yazılır. `/onayla` onay kodu gerektirmez (parametre sınırları ve tek adım limiti ders servisinde zorunludur) ama `expires_at` geçmişse çalışmaz. Bekleyen öneri sayısı `/durum`'da görünür.

## 6. Günlük rapor (21:00 Europe/Istanbul)

### 6.1 Zamanlama
`trader-telegram-report.timer`: `OnCalendar=*-*-* 21:00:00 Europe/Istanbul`, `Persistent=true` (kaçırılırsa açılışta bir kez; 23:30'dan sonra ise "gecikmiş" etiketiyle). Rapor günü = İstanbul takvim günü; veri sınırları UTC'ye çevrilerek sorgulanır (butce-spec: 21:00 TR = 18:00 UTC aynı UTC günü). Aynı gün ikinci kez üretilmez (`var/telegram/last_report.json` gün anahtarı; `/rapor` bunu etkilemez, "(manuel)" etiketlenir).

### 6.2 İçerik (salt okunur; yeni sayı hesaplanmaz, defter/status'ın verdiği gösterilir)
1. Başlık: kip (`paper`/`live`), gün, strateji adı@sürüm, `param_version_id`.
2. **Motor (`status.json`, `engine-status/1`)**: `loop_at` yaşı, `entries_open`, `gate.code`, `kill`/`kill_state`, `entries_blocked_reason`, `equity`, `day_start_equity`, günlük getiri %, açık pozisyonlar (pair, yön, giriş, stop; ≤ 10 satır, fazlası "+N"), `counters` içinde sıfır olmayanlar.
3. **Defter (`ledger_learner`, `ledger_twin` salt okunur)**: günün kapanan işlemleri (adet, kazanan/kaybeden, toplam R, ücret+funding), açılan işlemler, günün karar olayları dökümü (`entered`/`skipped`/`blocked` ve `skip_reason` sayıları), ikiz ile fark (varsa).
4. **Veto/bütçe**: `budget.status()` (gün/ay harcama / sınır, `prices_verified=False` ise "fiyatlar doğrulanmadı"), engellenen sinyal sayısı, `lesson_skipped_budget` varsa tek satır.
5. **Sağlık**: `health` durum dosyasının son `overall`, başarısız kontroller (≤ 5), yedek durumu, spool bekleyen sayısı (Telegram outbox dahil).
6. **Ders**: bekleyen/yeni öneriler (`request_id`, süre), son uygulanan sürüm, geri alma izleyici durumu.

Salt okunur kaynak okunamazsa o bölüm "okunamadı: <kod>" satırı olur (rapor yine gönderilir; boş rapor göndermek yerine eksik rapor tercih edilir). `status.json` yaşı > 120 sn ise raporun ilk satırı `CRIT` "motor kalp atışı yok". Rapor yine 3500 karakter sınırına tabidir; aşarsa 2. mesaja bölünür (ders ve sağlık bölümleri ayrı mesaj).

### 6.3 Anlık uyarı kaynakları
Sağlık `plan_alerts` çıktısı (debounce/düzeldi dahil), bütçe `pending_events()` (%70/%100), veto `veto_blocked`/`stale` seli özeti, ders bildirimleri ve onay talepleri, `KILL` kurulması/kalkması, motor `counters` artışı (`ledger_errors`, `unknown_orders`) ve `kill_state` geçişleri. Her birinin seviyesi kendi spec'indedir; Telegram yalnız taşır.

## 7. Sırlar

- `TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_IDS` (+ `TELEGRAM_USER_IDS`) yalnız `/etc/trader-telegram.env` (mod 0600, systemd `EnvironmentFile`; satır kuralları `saglik-spec` §8.3: yorum yok değerde, tırnak yok). Depoda yalnız değersiz `deploy/trader-telegram.env.example`. Ders/health/veto süreçlerinin kendi env dosyalarına **aynı token kopyalanmaz**: onlar ortak `/etc/trader-telegram.env`'i ikinci `EnvironmentFile=` olarak okur (tek kaynak, tek rotasyon).
- Token hiçbir günlükte, hata iletisinde, spool dosyasında, `audit.jsonl`'da ya da istisna metninde bulunmaz; URL'ler günlüğe `…/bot<gizli>/…` olarak yazılır (`requests` istisna metni token içeren URL taşır: **yakalanıp** `scrub` ile maskelenir, `__cause__` zinciri basılmaz). Komut satırına token konmaz.
- Token sızarsa: BotFather `/revoke`, env güncelle, daemon yeniden başlat. Yetkisiz kimlik toplu hatası token ihlali belirtisi sayılır (Bölüm 3'teki `WARN`).

## 8. systemd

`deploy/trader-telegram.service` (`Type=simple`, `Restart=always`, `RestartSec=5`, `User=trader`, `EnvironmentFile=/etc/trader-telegram.env`, `ExecStart=/usr/bin/python3 -I /opt/trader/scripts/telegram_run.py daemon`, `After=network-online.target`, `OnFailure=trader-health-fail@%n.service`, `MemoryMax=96M`, `CPUQuota=10%`, `Nice=10`, `NoNewPrivileges`, `PrivateTmp`, `ProtectSystem=strict`, `ProtectHome=read-only`, `ReadWritePaths=/opt/trader/var/telegram /opt/trader/shared`, `ReadOnlyPaths` ders/ledger/status dosyaları; ders onayı için `lesson.sqlite*` yazma izni ayrıca (açık soru 3)). `deploy/trader-telegram-report.{service,timer}` tek seferlik rapor (yukarıdaki zamanlama). `trader-health-fail@.service` Telegram'a bağlanırken **Telegram daemon'una bağımlı olmaz**: doğrudan `telegram_run.py send --severity CRIT "<metin>"` (tek seferlik, spool'lu) ya da mevcut `HEARTBEAT_FAIL_URL` yedeği. Daemon sağlığı: `var/telegram/alive.json` (30 sn'de bir zaman damgası) `health_run`'a yeni kontrol olarak eklenir (ayrı iş; `telegram_daemon_stale`, WARN).

## 9. Kurallar özeti

1. Yetkisiz ⇒ sessiz yok sayma + audit. 2. Her yıkıcı komut iki adım + TTL + tek kullanım. 3. Telegram arıza ⇒ spool; ticaret etkilenmez. 4. Kapatma = `Killswitch.set` (tek yol). 5. Metinden değer çıkarılmaz. 6. Token yalnız env.

## 10. Test planı (`tests/test_telegram_*.py`; ağ yok)

Sahte Telegram sunucusu: `http_post` enjeksiyonu ya da yerel `http.server` (`127.0.0.1`, rastgele port) ile `sendMessage`/`getUpdates` yanıtları ve hata kipleri (429+`retry_after`, 5xx, kopan bağlantı, `ok:false`). Saat enjekte edilir; `time.sleep` enjekte edilir.

- Giden: `True` yalnız `ok:true`+`message_id`; spool'a düşüş `False`; yeniden deneme çizelgesi (2/5/15, `retry_after` tavanı); kalıcı 400/401/403'te yeniden deneme yok; 3500 sınırı ve komut satırı korunumu; hız sınırı ve `INFO` birleştirme, `CRIT` birleştirilmez; `dedup_key`; token hiçbir çıktıda yok (istisna zinciri dahil, `grep` benzeri tarama); `build_notifier` token yokken `None`; `NullNotifier` ile ders/health sözleşme testleri.
- Spool: atomik yazım, sıra, 500/5 MiB sınırında düşme önceliği (`CRIT` düşmez), süresi dolan onay talebinin gönderilmemesi, Telegram dönünce boşaltma, süreç öldürülünce dosya bütünlüğü.
- Yetki: yabancı `chat.id` ⇒ yanıt yok + audit, yürütme yok; doğru chat yanlış `from.id`; `is_bot`; `edited_message`/kanal gönderisi yok sayılır; yetkisiz seli ⇒ tek `WARN`; audit'te tam kimlik yok.
- Polling: aynı `update_id` iki kez ⇒ tek yürütme (yeniden başlatma dahil); `offset` yalnız yürütme+audit sonrası ilerler (yürütmede çökme ⇒ yeniden teslim, idempotent sonuç); 409 davranışı; bayat (> 120 sn) ve başlangıçtan eski komut yürütülmez, "işlenmedi" yanıtı alır (her update bir kez).
- `/hepsini_kapat`: tek adımda kill yok; doğru kod ⇒ `Killswitch.set` (dosya içeriği `by/reason`), yanlış kod ⇒ iptal ve yeniden başlamak gerekir, **TTL 60 sn sonunda kod geçersiz** (sınır: 59/60/61 sn), kod tek kullanımlık, başka chat'ten kod, "hepsini kapat" metni normalizasyonu ve cümle içinde yürütülmemesi, kill zaten etkin ⇒ idempotent, `pending.json` yeniden başlatmadan sonra TTL içinde geçerli / sonra geçersiz, kod düz metin saklanmaz, Telegram tamamen kapalıyken `Killswitch.set` yerel yolu (daemon yokken) engelsiz, `kill_state` flat olmazsa `CRIT`.
- `/devam`: onay + `clear`; kill yokken no-op yanıtı. `/durdur` ⇒ "desteklenmiyor".
- `/onayla`/`/reddet`: sahte `LessonService` ile her `ResolveResult.status`, bozuk id biçimi, süresi dolmuş, çift onay idempotent, callback düğmesi aynı yol; `/onayla` metinden başka hiçbir değer taşımaz (enjeksiyon: `/onayla lr-…; DROP` reddi).
- Rapor: golden metin (sabit `status.json` + sahte defter), kaynak okunamazsa "okunamadı" satırı, `status.json` bayat ⇒ ilk satır `CRIT`, 21:00 İstanbul ⇒ 18:00 UTC (yaz/kış saati yok, TR UTC+3 sabit), günde bir kez, `Persistent` gecikmiş etiketi, 3500 sınırında bölme, salt okunur bağlantıda yazma denemesi yok (defter `read_only=True`).
- Ortam: kapalı kanal (token yok) ⇒ motor/ders çökmez; env dosyası biçim tuzakları (`# not`, tırnak) uyarısı.

## 11. Açık sorular (mentor)

1. **`/durdur` (yalnız giriş durdur, pozisyon kalsın):** `Killswitch` set ederse motor pozisyonları da kapatır. Ayrı bir `PAUSE` dosyası (motor kapı 7'ye yeni satır, `trader_engine` değişikliği) eklensin mi, yoksa yalnız KILL ile mi devam edelim? Önerimiz: Faz A'da yalnız KILL.
2. **`/devam` iki adımlı mı?** Önerimiz evet (yanlışlıkla girişleri açmasın); kullanıcı tek adım isterse risk: eski bir komut tekrar gelirse kill kalkar (4.2 bayatlık kuralı bunu sınırlar).
3. **Ders onayı yazma yolu:** `resolve_request` ders defterine (`lesson.sqlite` + öğrenen defteri RW) yazar; uzun ömürlü Telegram daemon'u ikinci RW süreç olur (kilit `lesson.lock` ile çakışma). Daemon doğrudan `LessonService` mi çağırsın, yoksa `lesson_run.py --resolve <id> --approve|--reject` (kısa ömürlü, kilitli; şu an CLI'de yok, eklenmeli) alt süreci mi? Önerimiz ikincisi.
4. **Grup mu özel sohbet mi?** Tek özel sohbet (önerilen) mi; grup ise `TELEGRAM_USER_IDS` zorunlu mu?
5. **Çoklu yetkili kimlik / ikinci operatör:** Faz A'da tek mi? Kapatma yetkisi ile onay yetkisi ayrılsın mı?
6. **`/hepsini_kapat` TTL 60 sn** ve bayatlık penceresi 120 sn uygun mu; gece uykusunda telefon gecikmesi için gevşetmek ister misiniz?
7. **Rapor saati yeniden başlatma politikası:** sunucu 21:00'de kapalıysa gecikmiş rapor 23:30'a kadar mı, yoksa ertesi sabaha atlansın mı?
8. **Sağlık dış nabzı** (saglik-spec §4) Telegram'dan bağımsız kalsın (önerimiz: evet); `trader-health-fail@` için Telegram ikincil kanal olarak yeterli mi?
9. **Canlı kipte (Faz B) ek yetki:** `/hepsini_kapat` canlıda borsada emir iptali/pozisyon kapatmayı da tetikleyecek; Telegram'dan canlıda `/devam` yasak (yalnız sunucudan) olsun mu?
10. Telegram bot'u bu proje için **yeni** bot mu (CT'nin token'ı paylaşılmasın; önerimiz: yeni bot, yeni token)?
