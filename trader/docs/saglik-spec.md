# Sağlık izleme, dış nabız, günlük yedek ve yeniden başlatma kurtarma — arayüz ve kurallar (spesifikasyon v1, 16 Kasım 2026)

Bu belge kod ve test içermez; testler bu belgeden yazılır. Biçim `risk-kilidi-spec.md` ile aynıdır. Defter arayüzleri `defter-spec.md`'den (Bölüm 4, 7.2, 8) alınmıştır; çelişkide o belge geçerlidir.

Modül: `src/trader_core/health.py` (yalnızca standart kütüphane; `pandas`, `numpy`, `freqtrade`, `docker` SDK import edilmez; saf: dosya, ağ, saat, süreç okumaz). Ölçümleri toplayan kod modülde değil, `scripts/health_run.py` içindedir. Her belirsizlikte **fail-closed**: sağlık belirlenemiyorsa sağlıklı sayılmaz, nabız gönderilmez, uyarı gider; sağlık modülü hiçbir koşulda işlem açmaz, bot başlatmaz, defter satırı yazmaz.

## 0. Kaynaklar ve neyin yeniden kullanıldığı (yalnızca okundu; hiçbiri çalıştırılmadı, içe aktarılmadı)

| Kaynak (kullanıcının projesi) | Alınan fikir | Bizde |
|---|---|---|
| CT `copytrade/saglik.py` | Saf kontrol: girdi anlık görüntü, çıktı `Bulgu(seviye, kod, mesaj)` listesi; eşikler bilinçli sabit; **okunamayan girdi sahte alarm üretmez** (CT) | Aynı saf biçim. Ters yön: bizde okunamayan girdi `UNKNOWN` olur ve nabzı keser (fail-closed); sahte alarm gürültüsü tekrar bastırma ile (Bölüm 5) azaltılır |
| CT `.github/nabiz/worker.js` | Dış ölü adam alarmı: nabız yaşı eşiği, ilk tikte alarm, sonra N dakikada bir tekrar, "veri okunamadı" ayrı durum, saf `karar()` | Cloudflare **kullanılmaz** (hesap kapalı, CT K-20). Aynı karar mantığı dış servise bırakılır (Bölüm 4) |
| CT `deploy/*.service`, `alarm.sh` | `Type=oneshot` + timer, `ProtectSystem=strict`, `OnFailure=` alarm birimi, çıkış kodu semantiği (kalıcı neden = yeniden başlatma yok), alarm betiği token'ı komut satırına koymaz, yoksa "atlandı" ile 0 çıkar | Bölüm 8 |
| CT `ortam_dosyasi.py` | systemd `EnvironmentFile` tuzakları (satır sonu `# not` değere karışır; tırnak yok); sır değeri asla basılmaz | Bölüm 8.3 ortam dosyası kuralları |
| CT `niyet.py` | Emirden önce niyet, fsync'li ekleme | Bizde defterin `decision_events` + spool'u aynı işi görür; sağlık yalnız okur |
| 1L3A `motor/canli/durum.py` | Atomik yazma: aynı dizinde geçici dosya + `fsync` + `os.replace` | Sağlık durum dosyası ve yedek bildirimi (Bölüm 5.3, 6) |
| 1L3A `kalp_atisi.py` | Bot canlıyken düzenli zaman damgası; yeniden başlatmada "son kalp atışı → başlangıç" kesintisi ölçülür; bozuk dosya sessiz geçilmez | Bizde bot kalp atışı = defterin `health_probes.probed_at` (yeni sütun/dosya gerekmez); kesinti süresi raporda |
| 1L3A `deploy/1l3a-bildirim@.service` | `OnFailure=...@%n.service` şablon birimi: başarısız birim adı alarm metnine girer | `trader-health-fail@.service` (Bölüm 8) |

## 1. Kapsam ve dosya sahipliği

Bu belgenin iş paketi yalnızca şunlara dokunur: `src/trader_core/health.py`, `scripts/health_*.{py,sh}`, `deploy/` (yeni dizin), `tests/test_health_*.py`. `TraderV1`, `ledger.py`, `docker-compose.yml`, `config/*.json` **değiştirilmez**; gerekli değişiklikler Bölüm 11'de bir sonraki adım için listelenir. Telegram gönderimi madde 18'dedir; burada yalnız `Notifier` arayüzü tanımlanır.

Çalışma ortamı: paylaşımlı DigitalOcean droplet, 1 vCPU / 2 GB RAM, başka proje de çalışıyor. Sağlık işlemleri kısa ömürlü süreçlerdir (daemon yok): tepe bellek hedefi ≤ 40 MiB, tek çalışma ≤ 5 sn CPU (yedek hariç).

## 2. Veri yapıları (`health.py`)

```
class Status(str, Enum): OK, WARN, CRIT, UNKNOWN, SKIPPED
@dataclass(frozen=True) class CheckResult:
    name: str            # Bölüm 3'teki ad
    status: Status
    code: str            # kısa, makine okur: "ok", "stale_candle", "api_unreachable", ...
    detail: str          # sade Türkçe tek cümle; sır ve yol dışında değer içermez
    value: float | None  # ölçülen (sn, bayt, oran, adet), yoksa None
    threshold: float | None
@dataclass(frozen=True) class HealthReport:
    generated_at: datetime        # UTC, tz-aware
    results: tuple[CheckResult, ...]
    overall: Status               # OK | WARN | CRIT | UNKNOWN (SKIPPED asla overall olmaz)
    healthy: bool                 # overall in (OK, WARN)
    def failing(self) -> tuple[CheckResult, ...]   # status in (WARN, CRIT, UNKNOWN)
```

**Birleştirme kuralı (`overall`):** `SKIPPED` yok sayılır. Kalan sonuçlarda sırayla: herhangi biri `CRIT` → `CRIT`; yoksa herhangi biri `UNKNOWN` → `UNKNOWN`; yoksa herhangi biri `WARN` → `WARN`; yoksa `OK`. Kalan sonuç **yoksa** (hepsi `SKIPPED` ya da boş) → `UNKNOWN`. **Zorunlu kontroller** (Bölüm 3'te "Z" işaretli) `results` içinde bulunmuyorsa her biri için `UNKNOWN` (`code="missing_check"`) eklenir. `healthy = overall in (OK, WARN)`; yani nabız yalnız `OK`/`WARN` iken gider, `CRIT` ve `UNKNOWN` iken gitmez.

### 2.1 Anlık görüntü (`HealthSnapshot`, frozen dataclass; ölçülemeyen alan `None`)

Runner ölçüp doldurur; `health.py` yalnız değerlendirir. `None` = "ölçülemedi" (istisna, zaman aşımı, ayrıştırma hatası) ve ilgili kontrol `UNKNOWN` olur. Alanlar:

| Alan | Tür | Anlam |
|---|---|---|
| `now` | `datetime` (UTC) | Runner'ın saati; tz-aware değilse `ValueError` |
| `timeframe_s` | `int \| None` | `show_config.timeframe` saniyeye çevrilmiş (bugün `1h` → 3600) |
| `api` | `dict[str, ApiProbe]` | Anahtar: bot (`learner`, `twin`). `ApiProbe(ping_ok: bool\|None, last_process_at: datetime\|None, last_candle_open: datetime\|None, open_trade_ids: tuple[int,...]\|None, dry_run: bool\|None)` |
| `ledger` | `dict[str, LedgerProbe]` | `LedgerProbe(last_write_at: datetime\|None, spool_lines: int\|None, unledgered_ids: tuple[int,...]\|None, orphan_ids: tuple[int,...]\|None, schema_ok: bool\|None, has_active_params: bool\|None)` |
| `disk_free_bytes`, `disk_total_bytes` | `int \| None` | Ledger/yedek dizinlerini barındıran dosya sistemi (`os.statvfs`; en küçük boş alanlı olan) |
| `mem_available_bytes`, `swap_total_bytes`, `swap_used_bytes` | `int \| None` | `/proc/meminfo` (`MemAvailable`, `SwapTotal`, `SwapTotal-SwapFree`) |
| `containers` | `dict[str, ContainerProbe]` | `ContainerProbe(state: str\|None, restart_count: int\|None, started_at: datetime\|None, oom_killed: bool\|None)`; `docker inspect` |
| `prev_restart_counts` | `dict[str, int]` | Önceki çalışmanın sayaçları (durum dosyası, Bölüm 5.3); ilk çalışmada boş |
| `veto_file_mtime` | `datetime \| None` | **Yer tutucu**; yapılandırmada kapalıysa kullanılmaz |
| `budget_state` | `str \| None` | **Yer tutucu**: `"ok" \| "warn" \| "exhausted"` |
| `last_backup_at` | `datetime \| None` | En son **doğrulanmış** yedek zamanı (Bölüm 6.6 manifest) |

### 2.2 `HealthConfig` (frozen dataclass; geçersiz değer → `ValueError`)

Eşikler bilinçli sabit varsayılandır (CT ilkesi); `warn < crit` değilse (süre/oran yönüne göre) veya sayı sonlu/pozitif değilse `ValueError`. Hepsi Bölüm 3 tablosundadır. Ek: `warmup_s=600` (Bölüm 3.3), `require_bots=("learner","twin")`, `veto_max_age_s: int|None=None` (None = yer tutucu kapalı), `budget_check_enabled=False`.

## 3. Kontroller (`health.evaluate(snap, cfg=DEFAULT_CFG) -> HealthReport`)

`evaluate` saf ve belirleyicidir; istisna sızdırmaz: bir kontrolün hesabı beklenmedik istisna verirse o kontrol `UNKNOWN`, `code="internal_error"`. Bot bazlı kontroller her bot için ayrı sonuç üretir (`name` = `"api_reachable:learner"` vb.).

| # | `name` | Z | Girdi | OK | WARN | CRIT | `None` |
|---|---|---|---|---|---|---|---|
| 1 | `api_reachable` | Z | `api[bot].ping_ok` | `True` | — | `False` (`api_unreachable`) | UNKNOWN |
| 2 | `bot_loop_age` | Z | `now - api[bot].last_process_at` (freqtrade `/api/v1/health` `last_process`) | ≤ 120 sn | > 120 sn | > 300 sn | UNKNOWN |
| 3 | `candle_age` | Z | `now - last_candle_open`, `timeframe_s=T` | ≤ 2T+120 | > 2T+120 | > 3T+120 (`stale_candle`) | UNKNOWN |
| 4 | `ledger_write_age` | Z | `now - ledger[bot].last_write_at` (en yeni `recorded_at`/`probed_at`; Bölüm 3.1) | ≤ T+300 | > T+300 | > 2T+300 | UNKNOWN |
| 5 | `ledger_gate` | Z | `LedgerProbe` alanları (Bölüm 3.2) | kapı açık olurdu | `orphan_ids` boş değil | kapı kapalı olurdu | UNKNOWN |
| 6 | `disk_free` | Z | `disk_free_bytes` | ≥ 3 GiB | < 3 GiB | < 1 GiB (`disk_low`) | UNKNOWN |
| 7 | `memory` | Z | `mem_available_bytes` | ≥ 250 MiB | < 250 MiB | < 120 MiB | UNKNOWN |
| 8 | `swap` | — | `swap_used/swap_total` | ≤ 0,50 | > 0,50 | > 0,80; `swap_total=0` ise `SKIPPED` | UNKNOWN |
| 9 | `container_restarts` | Z | `restart_count - prev_restart_counts[c]`, `state`, `oom_killed` | delta 0 ve `running` | delta ≥ 1 | delta ≥ 3, `state != running` ya da `oom_killed` | UNKNOWN |
| 10 | `backup_age` | — | `now - last_backup_at` | ≤ 26 sa | > 26 sa | > 50 sa | UNKNOWN (ilk kurulum günü: Bölüm 6.7) |
| 11 | `veto_file_age` | — | `veto_file_mtime` | — | — | — | `veto_max_age_s is None` → `SKIPPED` (`placeholder`); verilirse yaş ≤ süre OK, > süre WARN, > 3×süre CRIT; dosya yoksa/okunamıyorsa UNKNOWN |
| 12 | `budget_status` | — | `budget_state` | `"ok"` | `"warn"` | `"exhausted"` | `budget_check_enabled=False` → `SKIPPED`; açıkken `None` UNKNOWN; bilinmeyen metin UNKNOWN |

Yaşlar negatifse (saat geri gitti): 0 sayılmaz; ölçüm güvenilmez → `UNKNOWN`, `code="clock_skew"`. Gelecek tarihli `now`'dan 5 sn'den fazla ileri damga aynı kuralla `UNKNOWN`.

Her sınırda eşitlik **iyi tarafa** düşer ("≤ eşik" OK; "> eşik" WARN), tabloda böyle yazılmıştır. Bellek/disk için "≥ eşik" OK, "< eşik" bozuk.

### 3.1 `ledger_write_age` ne ölçer

Runner, defteri `open_ledger(path, bot, create=False, read_only=True)` ile açar ve şu dört tablodaki en yeni zamanı alır: `health_probes.probed_at`, `decision_events.recorded_at`, `trade_entries.recorded_at`, `trade_exits.recorded_at` (`last_write_at = max`). Bot her mum kapanışında `entries_allowed()` çağırdığından `health_probes` doğal bir "bot defteri yazabiliyor" nabzıdır (kalp atışı fikri, 1L3A). Hiç satır yoksa (taze defter, yalnız `meta`) `last_write_at = meta` oluşturma zamanı sayılır; o da yoksa `None`. Bot bilerek durdurulmuşsa (`initial_state` ≠ running) bu kontrol UNKNOWN verir ve nabız kesilir; bu **istenen** davranıştır (durdurulmuş bot "sağlıklı" değildir; bakım için `HEALTH_MAINTENANCE` dosyası, Bölüm 9, yalnız uyarıyı bastırır, nabzı değil).

### 3.2 `ledger_gate`: `entries_allowed` durumunun salt okunur türetimi

`Ledger.entries_allowed()` yazma yapar (`check_writable`, `drain_spool`) ve salt okunur bağlantıda `LedgerStateError` verir; sağlık süreci **ikinci yazar olmamalıdır** (defter-spec Bölüm 9). Bu yüzden runner kapıyı kendisi, yazmadan türetir; her koşul `LedgerProbe` alanından gelir:

1. `spool_lines > 0` → kapalı, `code="spool_pending"`.
2. `unledgered_ids` boş değil (`find_unledgered_trades(api.open_trade_ids)`, salt okunur çağrı) → kapalı, `unledgered_trades`.
3. `has_active_params is False` → kapalı, `no_active_params`.
4. `schema_ok is False` → kapalı, `schema`.
5. Yukarıdakilerden herhangi biri `None` (ölçülemedi) → `UNKNOWN` (kapının gerçekte ne yaptığı bilinmiyor).
6. Hepsi temiz → OK. `orphan_ids` (1 saatten eski, trade'e bağlanmamış `entered` kararları) boş değilse WARN, `code="orphan_decisions"`, `detail` ilk 5 kimliği listeler.

Türetilen durum, botun içindeki `degraded` bayrağını (bellekte/dosyadan) **göremez**; bu bir bilinen eksikliktir (Bölüm 12, Soru 2). Önerilen çözüm (sonraki adım, `ledger.py`'de): `Ledger.gate_status_readonly() -> Health`.

### 3.3 Isınma (warm-up)

Bir konteynerin `started_at`'i `warmup_s=600` sn içindeyse o botun `bot_loop_age`, `candle_age`, `ledger_write_age` sonuçlarında `CRIT` yalnız `WARN`e indirilir (`code` sonuna `_warmup` eklenir); `UNKNOWN` olduğu gibi kalır. `api_reachable` ve `container_restarts` ısınmada gevşemez. Amaç: restart sonrası tek seferlik bayat mum gürültüsü; nabız zaten `WARN`da gider, dış servisin tolerans süresi (Bölüm 4) boşluğu örter.

## 4. Dış nabız (dead man's switch), sağlayıcıdan bağımsız

Amaç: droplet düşse, ağ kopsa, systemd timer durup runner hiç çalışmasa bile **sessizliğin** alarm vermesi. İçeriden uyarı (Telegram) bu durumu bildiremez; bu yüzden nabız dışarıdan beklenir. Cloudflare varsayılmaz.

```
class HeartbeatSender(Protocol):
    def ok(self, report: HealthReport) -> bool       # sağlıklı: nabız ping'i
    def fail(self, report: HealthReport) -> bool     # isteğe bağlı: açık "bozuk" ping'i
```

Tek somut gerçekleme v1: `HttpsHeartbeat` (standart kütüphane `urllib.request`):
- `HEARTBEAT_URL` (zorunlu; sır sayılır): `ok()` bu adrese HTTPS `GET`. `https://` dışı şema reddedilir (`ValueError` açılışta). Zaman aşımı 10 sn; 3 deneme (bekleme 2 sn, 5 sn); 2xx başarı. Yönlendirme izlenmez (ssrf/sızıntı azaltma).
- `HEARTBEAT_FAIL_URL` (isteğe bağlı): doluysa `fail()` buraya `GET`; boşsa `fail()` hiçbir şey göndermez (sessizlik = alarm). Sağlayıcının "başarısızlık" uç noktası yoksa boş bırakılır.
- Adres ve sır günlüğe **asla** basılmaz (yalnız ana makine adı ve HTTP durum kodu). Hata metinleri adresi içermez.
- Çağrı gövdesi yok ya da en çok 200 bayt düz metin (`overall`, başarısız kontrol kodları); sır/bakiye/pozisyon içermez.

Sağlayıcı seçimi **sonraya** bırakılır: healthchecks.io tarzı herhangi bir "ping gelmezse alarm" servisi (healthchecks.io ücretsiz katmanı veya kendi barındırılan örneği, Better Stack/Cronitor/UptimeRobot heartbeat izleyicileri, ayrı bir makinedeki Uptime Kuma push monitörü) yalnızca bir URL verir; kodda sağlayıcıya özel hiçbir şey yoktur. Seçim ölçütleri: ücretsiz katman, e-posta + (varsa) Telegram/webhook entegrasyonu, ping sıklığına uygun tolerans, **bizim droplet'ten bağımsız** altyapı (aynı droplet'te barındırılan izleyici anlamsızdır).

Zamanlama: runner her **5 dakikada** çalışır; dış servis "beklenen aralık 5 dk, tolerans (grace) 15 dk" ile kurulur. Böylece art arda en çok 2 kayıp nabız (sağlıksız dahil) tolere edilir, 3. kayıp (≥ 15 dk) alarm verir; tek bir bayat mum/restart alarm vermez. Dış alarm kanalı kullanıcının seçeceği e-posta/Telegram'dır; bu kanal içeriden Telegram yolundan **bağımsızdır** (ikisi birden kırılamaz).

**Nabız kuralı (karar tablosu):**

| `overall` | `ok()` gönderilir mi | `fail()` | içeriden uyarı |
|---|---|---|---|
| OK | evet | hayır | yok (önceki bozuksa "düzeldi" bildirimi) |
| WARN | evet | hayır | var (Bölüm 5) |
| CRIT | **hayır** | evet (varsa) | var |
| UNKNOWN | **hayır** | evet (varsa) | var |
| Runner çöktü / `evaluate` istisna | **hayır** | hayır | `OnFailure` birimi (Bölüm 8) |

Nabız, kontrol hesabı tamamlandıktan sonra, **en son adım** olarak gönderilir; hesabın herhangi bir noktasında istisna olursa nabız gitmez. Nabız gönderimi başarısızsa runner yerelde `CRITICAL` günlük yazar, içeriden `heartbeat_send_failed` uyarısı üretir (dış servis zaten sessizlikten uyarır); `ok()` tekrar denenmez (bir sonraki tur 5 dk sonra).

## 5. Uyarı yolu: `Notifier` arayüzü ve tekrar bastırma

Telegram gerçeklemesi madde 18'dedir. Burada yalnız arayüz ve yerel gerçeklemeler:

```
@dataclass(frozen=True) class Alert:
    level: Status                # WARN | CRIT | UNKNOWN | OK (düzeldi bildirimi)
    code: str                    # CheckResult.code
    title: str                   # ≤ 80 karakter
    body: str                    # ≤ 500 karakter, sır içermez
    fingerprint: str             # "<name>|<code>"; tekrar bastırma anahtarı
    created_at: datetime
class Notifier(Protocol):
    def send(self, alert: Alert) -> bool    # True = iletildi; istisna fırlatmaz, False döner
```

Yerel gerçeklemeler (bu iş paketinde): `LogNotifier` (stderr/journal; her zaman çalışır, `False` dönmez) ve `NullNotifier` (testler, `send` çağrılarını listeler). `TelegramNotifier` bu belgenin kapsamı dışıdır (madde 18). Runner `NOTIFIER=log` (varsayılan) ile açılır; bilinmeyen ad → çıkış 1.

**Tekrar bastırma ve onay (debounce)** (`health.py`'deki saf `plan_alerts(report, state, now, cfg) -> (list[Alert], new_state)`):
1. Aynı `fingerprint` için seviye `CRIT`/`UNKNOWN`: ilk uyarı, bozukluğun **ardışık 2. çalışmasında** (≈ 10 dk) gider; `IMMEDIATE_CODES = {disk_low, unledgered_trades, spool_pending, schema, oom_killed}` 1. çalışmada gider. Sonra her **180 dk**'da bir hatırlatma.
2. `WARN`: ilk görüldüğünde (ardışık 2. çalışmada) bir uyarı, sonra her **720 dk**.
3. Bir `fingerprint` bir çalışmada kaybolursa `state`'te kapanır; daha önce uyarı gönderilmişse **bir** "düzeldi" (`level=OK`) uyarısı.
4. `Notifier.send` `False` dönerse `last_alert_at` güncellenmez (sonraki turda yeniden denenir); alınamayan uyarı nabzı etkilemez (nabız yalnız sağlığa bağlı).
5. Yeniden başlatma sonrası `UNKNOWN` seli: aynı turda ≥ 4 farklı `fingerprint` bozuksa tek özet uyarı (`code="multiple"`) gider, ayrıntı `body`'de (kontrol adları, ilk 5).

### 5.3 Durum dosyası

`/var/lib/trader-health/state.json` (`StateDirectory=trader-health`): `{"schema":1, "restart_counts":{...}, "fingerprints":{fp:{"first_seen","consecutive","last_alert_at","alerted":bool}}, "last_overall":"OK", "last_run_at":...}`. Atomik yazma: aynı dizinde `.state.json.tmp-<pid>` + `fsync` + `os.replace` (1L3A `atomik_yaz_json`). Dosya yoksa ya da bozuksa **boş durum** sayılır (restart sayacı sıfırdan, tüm uyarılar yeni), `WARN` `state_reset` kaydı yazılır; bozuk dosya sessizce yutulmaz ama sağlığı bozmaz. Konteyner sayaçları bu dosyada olduğundan 24 saatlik `delta` yerine "önceki çalışmadan beri" delta kullanılır (5 dk pencere): bir çalışmada ≥ 1 yeni restart `WARN`, ≥ 3 (ya da `state != running`, `oom_killed`) `CRIT`. Sürekli restart döngüsü (her turda +1) her turda WARN verir ve tekrar bastırma ile 720 dk'da bir hatırlatılır; 3 tur üst üste restart `CRIT`'e yükseltilir (`consecutive_restart_runs ≥ 3` durumda tutulur).

## 6. Günlük yedek (`scripts/health_backup.py`)

Amaç: iki defter (`ledger_learner.sqlite`, `ledger_twin.sqlite`) ve iki freqtrade veritabanı (`tradesv3.sqlite`, her botun `user_data` dizininde) günde bir yerel döner dizine yedeklenir; her yedek doğrulanır; **kaynak veritabanı kilitlenmez, yazar engellenmez**.

### 6.1 Zamanlama ve kaynak kullanımı
Günde bir, 03:10 UTC (`OnCalendar=*-*-* 03:10:00 UTC`, `Persistent=true`: makine kapalıyken kaçan çalışma açılışta yapılır). `Nice=19`, `IOSchedulingClass=idle`, `MemoryMax=96M`. Dört dosya **sırayla** (paralel değil) yedeklenir.

### 6.2 Kopyalama yöntemi
- **Dosya kopyası (`cp`) yasaktır** (WAL/`-shm` tutarsızlığı).
- Kaynak, salt okunur URI ile açılır: `sqlite3.connect("file:<yol>?mode=ro", uri=True, timeout=5)`; hedef `<dest>.partial` dosyasına `Connection.backup(hedef, pages=-1)` (tek adım, tek okuma işlemi). Defterler WAL modundadır: okuyucu yazarı bloklamaz; boyutlar küçük (MiB düzeyi) olduğundan tek adım milisaniyeler sürer. `pages=-1` seçildi çünkü sayfa sayfa kopyada araya giren yazma kopyayı baştan başlatır.
- Defter dosyaları için eşdeğer olan `Ledger.backup(dest)` (defter-spec Bölüm 4) kullanılabilir (aynı sqlite yedek API'si); ancak o yöntem şema denetimi ve açılış maliyeti getirdiği için betik ham `sqlite3` ile yapar ve sonuçta aynı doğrulamayı uygular.
- **freqtrade veritabanı**: freqtrade varsayılanı WAL **değildir** (geri alma günlüğü); okuma anında kısa süre yazara `database is locked` bekletebilir. Veritabanı küçük (trade tablosu) olduğundan kabul edilir; `timeout=5`. `OperationalError: database is locked` olursa 30 sn sonra **bir** yeniden deneme; yine başarısızsa o dosya `failed`, uyarı gider, döngü sürmez.
- Spool: `<db>.spool.jsonl` varsa aynı dizine olduğu gibi kopyalanır (`shutil.copyfile`, `fsync`); boş/yok ise atlanır. Spool yedeğe girmesi, defter ile spool arasında kurtarma yapılabilmesi içindir.

### 6.3 Dizin düzeni ve adlandırma
```
/var/backups/trader/                    # BACKUP_DIR (ortam değişkeni); sahibi root, izin 0700
  2026-11-16/
    ledger_learner.sqlite
    ledger_twin.sqlite
    freqtrade_learner.sqlite
    freqtrade_twin.sqlite
    ledger_learner.sqlite.spool.jsonl   # yalnız doluysa
    MANIFEST.json
  2026-11-15/ ...
```
Gün dizini UTC tarihi. Aynı gün ikinci çalışma: gün dizini varsa ve `MANIFEST.json` `ok=true` ise **atlanır** (idempotent); `ok=false` ya da `.partial` varsa dizin `<tarih>.failed-<HHMM>` olarak yeniden adlandırılıp yeniden denenir.

### 6.4 Doğrulama (her dosya için, kopya bittikten sonra, kopya üzerinde)
1. `PRAGMA integrity_check` (tam, kopyada) sonucu tam `ok` olmalı.
2. Defter: `PRAGMA user_version` kaynağın okunduğu `user_version`'a eşit; `meta.bot` beklenen bot; `BEFORE UPDATE/DELETE` tetikleyici sayısı kaynaktaki sayıya eşit (tablo başına; `ledger.py` `_trigger_ddl` ile aynı beklenti); tablo başına `max(id)` değerleri manifestte kayıtlı.
3. freqtrade: `trades` tablosu mevcut; `count(*)` manifestte kayıtlı.
4. Kopya boyutu > 0 ve kaynaktaki `page_count × page_size` ile uyumlu (± WAL farkı kabul; yalnız > 0 ve `integrity_check` zorunlu).
5. SHA-256 hesaplanır ve manifestte saklanır (sonradan bozulma tespiti için).
Doğrulama başarısızsa kopya `<ad>.corrupt` olarak yeniden adlandırılır (silinmez), dosya `failed`.

### 6.5 `MANIFEST.json`
`{"schema":1,"created_at","host","ok":bool,"files":{ad:{"ok","bytes","sha256","integrity":"ok","user_version","max_ids":{tablo:id},"trades":int,"error":null|"kod"}}}`. Yazma atomik (Bölüm 5.3 yöntemi). `ok` = dört dosyanın hepsi `ok`. Sır içermez.

### 6.6 Dönüş (rotation)
`BACKUP_KEEP_DAYS` (varsayılan **14**, alt sınır 3, üst sınır 60; dışı `ValueError`). Kural: yeni günün manifesti `ok=true` olduktan **sonra** en yeni N gün dizini kalır, daha eskiler silinir. Güvenlik: (a) bugünkü yedek başarısızsa **hiçbir şey silinmez**; (b) silme sonrasında `ok=true` manifestli en az 3 gün dizini kalmalıdır, kalmayacaksa silme yapılmaz; (c) silinen yalnızca `BACKUP_DIR` altında, adı `YYYY-MM-DD` (ya da `.failed-*`/`.partial` kalıntısı) desenine uyan dizinlerdir (başka hiçbir yol silinmez; sembolik bağ izlenmez). Boyut tahmini: dört dosya ≈ 20 MiB/gün olarak varsayılırsa 14 gün ≈ 280 MiB (gerçek boyut Bölüm 12, Soru 4).

### 6.7 Yedek sağlığı ve çıkış kodu
Yedek betiği çıkış kodu: 0 hepsi başarılı; 20 en az bir dosya başarısız (uyarı gönderildi); 1 beklenmedik istisna (`OnFailure`). `health.backup_age` en yeni **`ok=true`** manifestten beslenir (runner `BACKUP_DIR`'in manifestlerini okur). İlk kurulum günü hiç manifest yoksa: ilk 26 saat `SKIPPED` (`code="no_backup_yet"`), sonra `UNKNOWN` (runner kurulum zamanını durum dosyasında `installed_at` olarak tutar). Yedek yoluna yazılamaması (disk dolu) `disk_free` kontrolünü zaten kırmızıya çevirir; yedek, boş alan < 1 GiB ise **hiç başlamaz** (yedek diski doldurup canlı defteri öldürmesin) ve `failed(disk_low)` olur.

### 6.8 Kapsam dışı
Droplet kaybına karşı **uzak kopya** bu sürümde yoktur (yedekler aynı makinede). Öneri: DigitalOcean anlık görüntüsü ya da `rclone`/`rsync` ile ayrı bir hedefe bir sonraki adımda (Bölüm 12, Soru 3). Şifreleme yok (dizin 0700); yedek sır içermez ama ticari veri içerir.

### 6.9 Geri yükleme (belge, otomatik değil)
Botlar `docker compose stop learner twin` ile durdurulur → bozuk dosya ve varsa `-wal`/`-shm` yan dosyaları `*.bad-<tarih>` diye **yan yana saklanır** (silinmez) → seçilen gün dizinindeki kopya + spool yerine konur → `sha256sum` manifestle karşılaştırılır → `scripts/health_recover.py --check` (Bölüm 7) çalıştırılır → botlar başlatılır. Defter geri yüklenince geri yükleme zamanından sonraki kayıtlar kaybolur; freqtrade'in açık işlemleri ile defter farkı `find_unledgered_trades` ile açığa çıkar ve kapı kapalı kalır (Bölüm 7, adım R5). Geri yükleme otomatik **yapılmaz**.

## 7. Yeniden başlatma kurtarma kontrol listesi (`scripts/health_recover.py --check`)

Salt okunur bir rapordur; hiçbir şey başlatmaz, düzeltmez, yazmaz (spool boşaltma dahil). Çıktı: adım başına `PASS | WARN | FAIL | UNKNOWN` ve yapılacak elle işlem. Aynı mantık `health.evaluate` ile paylaşılır (aynı `HealthSnapshot`); ek olarak aşağıdaki adımlar. Ne zaman çalışır: elle (restart/çökme sonrası), ayrıca runner `container_restarts` ≥ 1 gördüğünde durum raporuna "kurtarma önerilir" satırı ekler.

| Adım | Kontrol | Başarısızlıkta |
|---|---|---|
| R1 | Konteynerler `running`; `ExitCode`, `OOMKilled`, `RestartCount`, `StartedAt` | `oom_killed` ise bellek sınırını (Bölüm 11) ve `memory` kontrolünü incele; restart döngüsünde `docker logs --tail 200` |
| R2 | Canlı veritabanlarında `PRAGMA quick_check` (salt okunur, bot çalışıyorsa bile güvenli) | FAIL → botu durdur, Bölüm 6.9 ile son iyi yedeği geri yükle |
| R3 | Her defter salt okunur açılır: `user_version == SCHEMA_VERSION`, `meta.bot` doğru, tetikleyiciler tam (`LedgerSchemaError` → FAIL) | Kod/şema uyumsuzluğu: konteyner imajı ve `src` sürümünü kontrol et; göç yalnız bot durmuşken, elle |
| R4 | **Spool**: `<db>.spool.jsonl` satır sayısı. > 0 → FAIL (`spool_pending`, kapı kapalı) | Bot başlangıçta `drain_spool()` çağırır (defter-spec 8.2); bot çalışıyor ve spool hâlâ doluysa neden `ledger_gate`/`degraded` ile bakılır; elle boşaltma yalnız botlar durmuşken, tek yazar olarak `Ledger.drain_spool()` ile |
| R5 | **Açık işlemler**: freqtrade `/api/v1/status` açık işlem kimlikleri → `find_unledgered_trades(ids)`. Boş değil → FAIL (`unledgered_trades`) | Bu işlemler borsada/dry-run'da açık ama defterde girişi yok. Kapı zaten kapalıdır; otomatik düzeltme yok. Elle karar: (a) defter girişi `record_trade_entry` ile **geriye dönük** ve açıkça işaretli notla eklenir, ya da (b) pozisyon kapatılır. İkisi de insan işi |
| R6 | `find_orphan_decisions(older_than_s=3600)` | WARN; `record_decision` ile `supersedes_id`, `skipped/order_failed` düzeltmesi (defter-spec 7.2) |
| R7 | Her açık işlem için borsada koruyucu stop emri var mı (freqtrade `stoploss_on_exchange` / API alanı; **alan adı 2026.10 imajında doğrulanacak**) | Yoksa FAIL: yeniden başlatma sonrası korumasız pozisyon; stop elle ya da freqtrade'in kendi mutabakatı ile yeniden kurulana dek uyarı |
| R8 | `dry_run` değeri (API `show_config`) ve whitelist'in beklenenle aynı olduğu | Beklenmeyen `dry_run=false`: FAIL ve acil uyarı (bu belge canlı para açmaz; yalnız tespit eder) |
| R9 | `check_writable` eşdeğeri **dolaylı**: son `health_probes.probed_at` bot başlangıcından sonra mı | Değilse bot kapıyı henüz yoklamamış olabilir (ısınma); 2 mum sonra yeniden bak |
| R10 | Saat: `timedatectl show -p NTPSynchronized` = yes | `no` → WARN (mum yaşı ve nabız hesapları saate bağlı) |
| R11 | Önceki sağlık durumu (`state.json`): hangi kontroller bozuktu, ne zamandan beri | Bilgi |

**Kapı yeniden açma kuralı:** yeni işlem kapısını sağlık/kurtarma betiği **hiçbir zaman** açmaz ya da zorlamaz. Kapı yalnızca botun içinde `ledger.entries_allowed()` ≡ `ok=True` olduğunda açılır (defter-spec 8.1). Kurtarma betiğinin tek işi hangi koşulun kapıyı kapalı tuttuğunu ve ne yapılacağını söylemektir. Nabız, bu koşullar giderilene dek zaten `ledger_gate=CRIT` ile kesilidir.

## 8. Çalıştırma: runner ve systemd birimleri (`scripts/health_run.py`, `deploy/`)

### 8.1 Runner akışı (her 5 dk)
1. Ortamı oku (Bölüm 8.3). Yoksa/geçersizse: günlük + çıkış 1 (nabız gitmez, `OnFailure`).
2. Durum dosyasını oku (5.3).
3. Ölçümleri topla; **her ölçüm ayrı `try/except` ve kendi zaman aşımı** (HTTP 5 sn, `docker inspect` 10 sn). Hata → ilgili alan `None`. Toplam süre üst sınırı 60 sn (aşılırsa kalanlar `None`).
4. `health.evaluate` → `HealthReport`; `plan_alerts` → uyarılar.
5. Uyarıları gönder (`Notifier`); sonra **nabız** (Bölüm 4 tablosu); sonra durum dosyasını yaz.
6. Raporu tek satır JSON olarak stdout'a (journal) yaz (sır yok).
Salt okuma: HTTP `GET` (`/api/v1/ping`, `/api/v1/health`, `/api/v1/show_config`, `/api/v1/status`, `/api/v1/pair_candles?pair=<referans>&timeframe=<tf>&limit=2`); POST/PUT/DELETE yasak. API kimlik bilgileri ortam dosyasından, günlüğe basılmaz. Referans çift: whitelist'in ilki. freqtrade API uç noktalarının 2026.10 sürümündeki tam adları kod yazılmadan önce imajdan doğrulanacak.

### 8.2 Bellek ve süreç disiplini
Süreç ömrü < 10 sn, daemon yok (timer her seferinde başlatır; arada 0 bayt). `MemoryMax=64M`, `CPUQuota=20%`, `Nice=10`. Docker için SDK yok; `docker inspect` alt süreci. Docker soketi root'a eşdeğerdir; birim bu yüzden `User=root` ama sıkı sandbox ile çalışır (`ProtectSystem=strict`, `ReadOnlyPaths=/home/<kullanıcı>/trader/user_data`, `ReadWritePaths=/var/lib/trader-health`, `NoNewPrivileges=true`, `PrivateTmp=true`, `ProtectHome=read-only`). Alternatif (`docker` grubundaki ayrı kullanıcı) aynı yetkiyi verir; seçim Bölüm 12 Soru 5.

### 8.3 Ortam dosyası (`/etc/trader-health.env`, izin 0600, sahibi root)
Anahtarlar: `HEARTBEAT_URL`, `HEARTBEAT_FAIL_URL` (ops.), `FREQTRADE_API_USER`, `FREQTRADE_API_PASS`, `LEARNER_API=http://127.0.0.1:8080`, `TWIN_API=http://127.0.0.1:8081`, `LEDGER_DIR`, `FREQTRADE_USER_DATA_DIR`, `BACKUP_DIR`, `BACKUP_KEEP_DAYS`, `NOTIFIER`, `HEALTH_MAINTENANCE_FILE` (ops.). Kurallar (CT `ortam_dosyasi.py` dersi): satır ya boş, ya `#` ile başlayan tam satır yorum, ya `AD=değer`; eşittir çevresinde boşluk yok, değerde `#` yok, tırnak yok. Sır değerleri asla basılmaz. Depoda yalnız `deploy/trader-health.env.example` (değersiz) bulunur.

### 8.4 Birimler (`deploy/`, yeni)
| Dosya | İçerik özeti |
|---|---|
| `trader-health.service` | `Type=oneshot`, `ExecStart=/usr/bin/python3 -I /opt/trader/scripts/health_run.py`, `EnvironmentFile=/etc/trader-health.env`, `StateDirectory=trader-health`, `TimeoutStartSec=90`, `SuccessExitStatus=10 11 12` (sağlıksız/gönderim hatası = beklenen çıkış, `OnFailure` yalnız beklenmedik çöküşte), `OnFailure=trader-health-fail@%n.service`, sandbox (8.2) |
| `trader-health.timer` | `OnBootSec=2min`, `OnUnitActiveSec=5min`, `AccuracySec=15s`, `Persistent=false` |
| `trader-backup.service` / `.timer` | Bölüm 6; `Nice=19`, `IOSchedulingClass=idle`, `ReadWritePaths=/var/backups/trader`, `SuccessExitStatus=20`, `OnFailure=` aynı şablon; `OnCalendar=*-*-* 03:10:00 UTC`, `Persistent=true`, `RandomizedDelaySec=300` |
| `trader-health-fail@.service` | 1L3A `1l3a-bildirim@` ve CT `alarm.sh` deseni: `scripts/health_fail.sh %i` çalışır; yalnız `logger` + (varsa) `HEARTBEAT_FAIL_URL`'e `curl`; Telegram madde 18'e bağlanana dek sınırlı kalır; yapılandırma yoksa "atlandı" yazıp 0 ile çıkar (alarm zinciri ikinci hata üretmesin) |
| `trader-health.env.example` | 8.3 anahtarları, değersiz |
| `README` yok | Kurulum adımları madde 19 (dağıtım) belgesinde; burada yalnız dosya listesi |

Çıkış kodları (`health_run.py`): 0 = sağlıklı (OK/WARN) ve nabız gitti; 10 = CRIT/UNKNOWN (nabız yok, uyarı üretildi); 11 = sağlıklı ama nabız gönderilemedi; 12 = uyarı iletilemedi; 1 = beklenmedik hata.

## 9. Bakım penceresi
`HEALTH_MAINTENANCE_FILE` varsa ve içindeki ISO UTC zaman damgası gelecekteyse (en çok 4 saat ilerisi; fazlası yok sayılır) yalnız **içeriden uyarılar** bastırılır (`plan_alerts` listeyi boş döndürür). **Nabız bastırılmaz ve zorla gönderilmez**: bozuk sistem bakımdayken de sağlıklı sayılmaz; dış servis tarafında bakım için duraklatma kullanıcı işidir. Dosya yok/bozuk/süresi geçmiş → bakım yok (fail-closed: şüphede uyarı).

## 10. Fail-closed özeti
- Ölçüm istisnası, zaman aşımı, ayrıştırma hatası, negatif yaş, bozuk durum dosyası → `UNKNOWN` ve nabız yok.
- Zorunlu kontrol eksik → `UNKNOWN`. Tüm kontroller `SKIPPED`/boş → `UNKNOWN`.
- Runner çökerse nabız gönderilmez (nabız son adımdır) ve `OnFailure` çalışır.
- Timer/systemd/droplet ölürse nabız kesilir → **dış servis** alarmı (içeriden uyarı gerekmez).
- Notifier başarısızlığı nabzı ne açar ne kapatır; yalnız `12` çıkış kodu ve günlük.
- Sağlık modülü yalnız okur ve rapor eder: `forceenter`, `start`, `reload_config`, defter yazma, spool boşaltma, yedeği geri yükleme, kapıyı açma **yoktur**. (İsteğe bağlı sonraki sürüm: `CRIT` iken `/api/v1/stopentry` ile **kapatıcı** eylem; varsayılan kapalı, ayrı onay.)
- Yedek: başarısız yedek eski yedekleri silmez; boş alan < 1 GiB iken yedek başlamaz.

## 11. Sonraki adım için compose ve yapılandırma değişiklik listesi (bu iş paketinde YAPILMAZ)
1. `docker-compose.yml`: her servise `mem_limit` (öneri başlangıcı: learner 700m, twin 500m; paylaşımlı 2 GB'ta diğer proje ve swap payı için; gerçek RSS ölçümünden sonra ayarlanır) ve `memswap_limit`; `oom_kill_disable` **kullanılmaz**.
2. `docker-compose.yml`: `healthcheck` (python `urllib` ile `/api/v1/ping`; imajda `curl` olup olmadığı doğrulanacak), `interval: 60s`, `retries: 3`; `docker inspect .State.Health` ek kontrol olarak okunabilir.
3. `docker-compose.yml`: `stop_grace_period: 60s` (temiz kapanış, spool/defter yazımı bitsin).
4. `config/base.json` `api_server`: `listen_ip_address` `0.0.0.0` (konteyner içi; ana makineye yalnız `127.0.0.1` yayımlanıyor, doğru) ve **boş** `username/password/jwt_secret_key` — sağlık runner'ının `/api/v1/health`, `status`, `pair_candles` çağrıları için dolu kimlik bilgisi gerekir; değerler `.env`'den gelmeli (depoya girmez).
5. `ledger.py`: `Ledger.gate_status_readonly()` (Bölüm 3.2) ve isteğe bağlı `Ledger.last_write_at()`; sağlık betiğinin ham SQL yazmaması için.
6. Strateji: açılışta ve her mumda `health_probes` yazımı zaten `entries_allowed` ile; ek iş yok.
7. Yedek dizini compose'a girmez (ana makine yolu); `./user_data/<bot>` dizinleri ana makineden okunabilir olmalı (konteyner kullanıcı kimliği 1000 → root okur, sorun yok).

## 12. Belirsizlikler ve çözümleri
| # | Soru | Bu belgedeki çözüm |
|---|---|---|
| 1 | Dış nabız sağlayıcısı | Seçilmedi; `HttpsHeartbeat` yalnız URL ister. Sağlayıcı kullanıcı kararı (ölçütler Bölüm 4) |
| 2 | Botun bellekteki `degraded` bayrağı dışarıdan görünmez | Salt okunur türetim (3.2) + `gate_status_readonly` önerisi (11.5); bu arada `ledger_write_age` ve `spool_pending` yeterli ikinci sinyaldir |
| 3 | Droplet kaybına karşı uzak yedek | v1 kapsamı dışı; DO anlık görüntüsü ya da `rclone` sonraki adım. Kullanıcıya sorulacak |
| 4 | Gerçek veritabanı boyutları | Bilinmiyor (0 işlem); 20 MiB/gün varsayımı. İlk haftada manifestlerden ölçülüp `BACKUP_KEEP_DAYS` ve disk eşiği gözden geçirilir |
| 5 | Runner kullanıcısı (root + sandbox mı, `docker` grubu mu) | Root + sandbox önerilir; kullanıcı onayı |
| 6 | Bayat mum eşiği 2T/3T | `1h` zaman diliminde mum kapanışı sonrası ≤ 2 saat OK. Zaman dilimi değişirse formül `T`'ye bağlıdır; strateji spesifikasyonu daha sık zaman dilimi seçerse eşikler yeniden değerlendirilir |
| 7 | Veto dosyası ve bütçe yer tutucuları | Bölüm 3 satır 11–12: kapalıyken `SKIPPED`; ilgili madde tamamlanınca `HealthConfig` bayrağı ile açılır, `evaluate` imzası değişmez |
| 8 | `dry_run` iken "açık işlem" semantiği | freqtrade dry-run'da da `/status` döner; R5 aynı çalışır |

## 13. Elle doğrulanabilir örnekler (test yazarı için)

Hepsinde `now = 2026-11-16T12:30:00Z`, `timeframe_s = 3600`, `DEFAULT_CFG`.

### 13.1 Her şey sağlıklı
`ping_ok=True`; `last_process_at=12:29:30` (30 sn); son mum açılışı `12:00:00` (yaş 1800 sn ≤ 7320); defter son yazma `12:00:02` (1798 sn ≤ 3900); `spool_lines=0`, `unledgered_ids=()`, `orphan_ids=()`, `schema_ok=True`, `has_active_params=True`; disk 20 GiB boş; `MemAvailable` 900 MiB; swap 10 %; restart delta 0, `running`; `last_backup_at=03:10 bugün` (9 sa 20 dk); veto/bütçe kapalı. ⇒ `overall=OK`, `healthy=True`; satır 11 ve 12 `SKIPPED`; nabız gider.

### 13.2 Bayat mum eşikleri (T = 3600 ⇒ WARN > 7320, CRIT > 10920)
Son mum açılışı `10:30:00` (yaş 7200) ⇒ OK. `10:29:00` (7260) ⇒ OK. `10:27:00` (7380) ⇒ WARN. `09:27:00` (10980) ⇒ CRIT, `code="stale_candle"`. `09:30:00` (10800) ⇒ WARN (CRIT eşiği 10920 aşılmadı). Tam sınır: yaş = 7320 ⇒ OK (eşitlik iyi taraf).

### 13.3 Fail-closed: API okunamadı
`api["learner"]` tamamen `None` alanlı (zaman aşımı) ⇒ `api_reachable:learner` UNKNOWN, `bot_loop_age` UNKNOWN, `candle_age` UNKNOWN; diğer her şey OK ⇒ `overall=UNKNOWN`, `healthy=False` ⇒ nabız **yok**; `fail()` varsa çağrılır; uyarı ardışık 2. turda (≈ 10 dk); dış servis 15 dk sonra alarm verir.

### 13.4 Disk ve bellek
Disk boş 2,5 GiB ⇒ WARN; 0,9 GiB ⇒ CRIT `disk_low` (`IMMEDIATE`, ilk turda uyarı); tam 3 GiB ⇒ OK. `MemAvailable` 250 MiB ⇒ OK, 249 ⇒ WARN, 119 ⇒ CRIT. Swap: toplam 2048 MiB, kullanılan 1100 MiB (0,537) ⇒ WARN; 1700 MiB (0,83) ⇒ CRIT; `swap_total=0` ⇒ `SKIPPED`.

### 13.5 Konteyner restart
`prev={"trader-learner":4}`, şimdi `restart_count=4`, `running` ⇒ OK. Şimdi 5 ⇒ WARN (delta 1). Şimdi 7 ⇒ CRIT (delta 3). `restart_count=4` ama `state="restarting"` ⇒ CRIT. `oom_killed=True` ⇒ CRIT `oom_killed` (`IMMEDIATE`). `started_at=12:25:00` (5 dk önce) ve `candle_age` CRIT ⇒ ısınma içinde: WARN `stale_candle_warmup`; `api_reachable=False` ⇒ yine CRIT (3.3).

### 13.6 Defter kapısı
`spool_lines=1` ⇒ `ledger_gate` CRIT `spool_pending` (kapı kapalı olurdu), `overall=CRIT`, nabız yok. `unledgered_ids=(9,)` (freqtrade açık `[7,8,9]`, defterde 7,8) ⇒ CRIT `unledgered_trades`. `orphan_ids=(31,)` ve diğerleri temiz ⇒ WARN `orphan_decisions`, nabız gider. `spool_lines=None` ⇒ UNKNOWN. İki bot: biri OK biri CRIT ⇒ `overall=CRIT`.

### 13.7 Birleştirme ve yer tutucular
Sonuçlar: OK, OK, `SKIPPED`, WARN ⇒ `overall=WARN`, `healthy=True`. OK + UNKNOWN + WARN ⇒ UNKNOWN. Yalnız `SKIPPED`'lar ⇒ UNKNOWN. Z-işaretli bir kontrol `results`'ta yok ⇒ `missing_check` UNKNOWN eklenir. Negatif yaş (`last_process_at = 12:31`) ⇒ UNKNOWN `clock_skew`. `veto_max_age_s=900`, mtime yaşı 1000 sn ⇒ WARN; 2800 sn ⇒ CRIT; `veto_max_age_s=None` ⇒ `SKIPPED placeholder`. `budget_check_enabled=True`, `budget_state="exhausted"` ⇒ CRIT; `"weird"` ⇒ UNKNOWN.

### 13.8 Uyarı bastırma zaman çizelgesi (5 dk'lık turlar, `stale_candle` CRIT, `IMMEDIATE` değil)
t=0 CRIT (ardışık 1): uyarı yok. t=5 (ardışık 2): **uyarı 1**. t=10…175: yok. t=185 (5+180): hatırlatma. t=200 kontrol düzelir ⇒ bir "düzeldi" (`level=OK`). t=0'da `disk_low` (`IMMEDIATE`) ⇒ uyarı t=0'da. Aynı turda 5 farklı fingerprint CRIT ⇒ tek `multiple` uyarısı, `body`'de ilk 5 ad. `Notifier.send`=False ⇒ ertesi turda yeniden denenir.

### 13.9 Nabız kararı
Raporlar: OK ⇒ `ok()` çağrılır. WARN ⇒ `ok()` + uyarı. CRIT ⇒ `ok()` çağrılmaz, `fail()` varsa çağrılır. `HEARTBEAT_URL=http://x` ⇒ açılışta `ValueError` (https zorunlu). Gönderim: 1. deneme zaman aşımı, 2. deneme (2 sn sonra) 200 ⇒ başarı; üçü de hata ⇒ çıkış 11, `heartbeat_send_failed` uyarısı. Dış servis: son başarılı ping 12:00, ping'ler 12:05'te beklenir, 15 dk tolerans ⇒ 12:20'ye kadar ping yoksa alarm.

### 13.10 Yedek ve rotation
`BACKUP_KEEP_DAYS=14`, `BACKUP_DIR` içinde 16 gün dizini (11-01 … 11-16), hepsi `ok=true`; 11-16 yedeği az önce doğrulandı ⇒ en eski 2 dizin (11-01, 11-02) silinir, 14 kalır. Aynı durumda 11-16 manifesti `ok=false` ⇒ **hiçbir şey silinmez**. 11-16 `ok=true` ama eski 15 dizinin 12'si `ok=false` ⇒ silme sonrası `ok=true` sayısı ≥ 3 kuralı: kalanlarda `ok=true` en az 3 ise silinir, değilse hiçbir şey silinmez. `BACKUP_KEEP_DAYS=2` ⇒ `ValueError`. Dizin adı `notes` ⇒ asla silinmez. Boş alan 0,8 GiB ⇒ yedek başlamaz, `failed(disk_low)`, çıkış 20.
Doğrulama: kopyada `integrity_check` = `ok`, `user_version` 1 = kaynak 1, `meta.bot="learner"`, tetikleyici sayısı kaynakla eşit ⇒ `ok`. Kopya baytı elle bozulup `integrity_check` "ok" dışı dönerse ⇒ dosya `.corrupt`, `MANIFEST.ok=false`, `backup_age` eski yedekten hesaplanır (bugün başarısız ⇒ 26 sa sonra WARN). `backup_age`: 25 sa ⇒ OK, 27 sa ⇒ WARN, 51 sa ⇒ CRIT.
Aynı gün ikinci çalışma ve manifest `ok=true` ⇒ atlanır (çıkış 0).

### 13.11 Kurtarma listesi
Konteyner kill -9 sonrası: R1 `RestartCount` +1, R4 `spool_lines=2` ⇒ FAIL (kapı kapalı); bot açılışta `drain_spool()` 2 döner, spool boşalır ⇒ sonraki çalışmada R4 PASS. R5: freqtrade açık `[7,8,9]`, defterde 7, 8 ⇒ FAIL `[9]`; rapor "elle karar: geriye dönük giriş ya da kapat" der; betik hiçbir şey yazmaz. R8: `dry_run=false` ⇒ FAIL ve acil uyarı.

## 14. Test planı (kod bu belgede yok; `tests/test_health_spec.py`, `tests/test_health_backup_spec.py`)
`evaluate` için 13.1–13.7'nin her satırı; `plan_alerts` için 13.8; `HttpsHeartbeat` için sahte HTTP sunucusu (13.9, yönlendirme izlenmez, adres günlüğe girmez); yedek için geçici dizinde gerçek `sqlite3` dosyaları: WAL modunda açık yazar bağlantısı varken yedek yazarı **bloklamaz** (yazar `busy_timeout` içinde commit eder), bozuk kaynak ve bozuk kopya, rotation (13.10), idempotentlik, `.partial` kalıntısı; durum dosyası atomik yazma ve bozuk dosyada boş durum; ortam dosyası ayrıştırma (satır sonu `#`, boşluk, tırnak). `health.py` içe aktarımının `pandas`/`numpy`/`freqtrade` yüklemediği (`sys.modules` denetimi) ve `trader_core/__init__.py`'nin yalnız docstring içerdiği doğrulanır. Ağ, `docker` ve gerçek saat testlerde kullanılmaz (hepsi enjekte).


## 14. Motor uyarlaması

freqtrade kaldırıldı; girdi kaynağı kendi motorumuzun `status.json` dosyasıdır (`docs/motor/05-engine-runner.md` §8.2, şema `engine-status/1`). **Bu belgede geçen freqtrade API, `docker inspect`, `tradesv3.sqlite`, `FREQTRADE_*`, `LEARNER_API/TWIN_API`, `LEDGER_DIR` ifadeleri bu bölümle değiştirilmiştir.** `health.evaluate` ve 12 kontrolün adları/eşikleri/fail-closed davranışı aynıdır; yalnızca ölçüm toplayıcı (`scripts/health_run.py`) değişti. `ApiProbe` adı tarihsel kaldı.

**Yollar** (tek ortam anahtarı `ENGINE_VAR_DIR` = motor `var_dir`): `<var>/<bot>/status.json`, `<var>/<bot>/ledger.sqlite`, `<var>/<bot>/state.sqlite` (`bot` ∈ learner, twin). Yedek dosya adları: `ledger_<bot>.sqlite`, `state_<bot>.sqlite` (doğrulama: `positions` tablosu, manifestte `positions` sayısı).

**status.json okuma kuralları (fail-closed):** dosya yok → `ping_ok=False` (CRIT `api_unreachable`; döngü/mum UNKNOWN); okunamaz, bozuk JSON, `schema != engine-status/1`, `bot` uyuşmaz, 2 MB üstü → tüm alanlar `None` (UNKNOWN); `loop_at` 120 sn'den eskiyse `ping_ok=False`; `loop_at` gelecekteyse (saat uyumsuz) `ping_ok=None`. Twin dosyası yoksa twin bazlı kontroller CRIT/UNKNOWN olur ve `overall` sağlıksızdır (iki bot zorunlu).

| # | Kontrol | Motor kaynağı |
|---|---|---|
| 1 | `api_reachable` | `loop_at` yaşı ≤ 120 sn ve dosya geçerli |
| 2 | `bot_loop_age` | `loop_at` |
| 3 | `candle_age` | `last_candle_open`; periyot `trigger_tf` |
| 4 | `ledger_write_age` | `<var>/<bot>/ledger.sqlite` (salt okunur; değişmedi) |
| 5 | `ledger_gate` | defter yoklaması (spool, unledgered, şema, etkin param) + `gate.code` (ok/kill dışı → CRIT `engine_gate_closed`); `kill`/`gate.code=="kill"` → WARN `engine_kill`; `counters.ledger_errors > 0` → WARN `ledger_errors`; `open_trade_ids` `find_unledgered_trades` girdisi |
| 6 | `disk_free` | `ENGINE_VAR_DIR` + `BACKUP_DIR` (değişmedi) |
| 7 | `memory` / `swap` | `/proc/meminfo` (değişmedi) |
| 8 | `container_restarts` | `status.started_at` değişimi → kalıcı sayaç (+1; `state.json` `restart_counts`/`engine_started_at`); `state="running"` ⇔ `loop_at` ≤ 300 sn, aksi `not_running` (CRIT); `started_at` ısınma için kullanılır; `oom_killed` her zaman `None` |
| 9 | `backup_age` | değişmedi (`health_backup.py`: iki defter + iki motor state) |
| 10 | `veto_file_age` | değişmedi |
| 11 | `budget_status` | değişmedi |

Kurtarma (§7): R5 `open_trade_ids`; R7 `open_positions[].stop` boş/≤0 → FAIL (paper'da borsa stop'u yok, motorun stop'u var); R8 `dry_run`; R1 status tazeliği.

**Motor tarafında eksikler (rapor edildi, motor değiştirilmedi):** (a) `oom_killed`/süreç çıkış nedeni status'ta yok → `None`; (b) yeniden başlatma sayacı status'ta yok → `started_at` değişiminden türetilir (iki çalışma arasında 2 restart tek sayılır); (c) status'ta `ledger_errors` kümülatiftir (süreç başından), zaman penceresi yok; (d) status'ta son defter yazma zamanı yok → defter sqlite'ından okunur; (e) temiz kapanış (`kalp_atisi.json` `stopped`) okunmuyor.
