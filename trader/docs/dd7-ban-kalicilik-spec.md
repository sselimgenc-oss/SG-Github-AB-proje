# DD-7 — Yasak (ban) kalıcılığı (uygulama şartnamesi v1, 18 Kasım 2026)

**Hazırlayan:** mentor · **Taban:** `claude/charming-hawking-ab5w5q` @ `6071ce3` (DD-2 ve DD-8 birleşmiş)
**Kaynak:** `otonom-trading-arastirma/dis-denetim/triyaj-2026-11-18.md` — O2 (triyajın DD-7'ye atadığı tek madde; dört alt başlık: kalıcı dosya, CRIT + elle yol, OI toplayıcı kısma, ağırlık eşiğinde giriş reddi).
**Hedef:** canlıdan önce birleşmiş olmak. Canlı çalışmıyor; bu paket para riski taşımaz.

Bu belge davranışı tanımlar. Test yazan ajan uygulamayı görmeden yalnız bu belgedeki adlara (dosya adı, alan, sabit, sayaç, çıkış kodu, hata kodu, işlev imzası) dayanır; bu adlar **sözleşmedir**.

---

## 0. Kapsam, kısıtlar, ilke

**İlke (triyaj, mentor kararı).** Yasak penceresinde koruyucu istek dahil **hiçbir** istek gitmez; bu davranış değişmez (418 sırasında her istek yasağı uzatır). DD-7 yalnız şunu ekler: pencere diske yazılır, aynı IP'yi paylaşan üç süreç (motor, feed, OI toplayıcı) onu açılışta **ve çalışırken** okur; kullanıcı uyarılır; yasağa yaklaşırken yük azaltılır.

**Kapsam içi:** P (ban dosyası), M (imzalı istemci + motor açılışı), F (feed), T (OI toplayıcı), G (ağırlık eşiğinde giriş reddi), S (sağlık alarmı + elle yol belgesi).

**Kapsam dışı:** pencere içinde koruyucu emir gönderme (reddedildi); dolum–stop arası ≈ 1 sn'ye yasak denk gelmesi (kalan risk, kabul); `_startup_ban`in 451/403 → çıkış 8 eşlemesi (değişmez); bozuk mum istek fırtınası (DD-1); testnette bilinçli 418 tetikleme (yapılmaz; hepsi sahte borsa ile).

**Sert kısıtlar (ihlali = paket reddi):**
1. Dondurulmuş dosyalara dokunulmaz: `scripts/build_corpus_v2.py`, `research/ml_build_candidates.py`, `src/trader_ml/{features,features_v2,labels,guards,config}.py`, `src/trader_core/{ml_features,ml_features_v2,signals,regime,indicators}.py`, `src/trader_engine/holdout.py`.
2. `mode ∈ {paper, backtest}` bit-özdeş: bu modlarda `BanGuard` **kurulmaz**, ban dosyası okunmaz/yazılmaz; altın geri test (`tests/test_wp3_golden.py`) değişmeden geçer.
3. Holdout (2026-05-01 … 2026-11-01) okunmaz; OI toplayıcının `in_holdout` / `clip_windows` mantığına dokunulmaz. freqtrade / ccxt / python-binance eklenmez; yeni modül yalnız stdlib kullanır.
4. Hiçbir kapı gevşetilmez. Mevcut istisna sınıfları, `last_ban`, `exchange_bans` sayım kuralı, F8–F11 davranışı ve çıkış kodları aynen kalır.

**Yeni adlar:** `EngineExit(5, "exchange_ban_persisted")`; sayaçlar `ban_persist_failed`, `ban_file_seeded` (`SignedRestClient.counters`), `entry_weight_rejects` (`LiveBroker` sayaçları); emir reddi `weight_high`; sağlık kodları `exchange_ban_open_positions`, `exchange_ban`, `exchange_ban_file_corrupt`.

---

## 1. P — Ban dosyası: `src/trader_core/ban_store.py` (yeni, yalnız stdlib)

**Sorun.** Pencere yalnız bellekte (`binance_rest.py:174`); yeniden başlatma unutuyor ve açılış isteği yasağı uzatabiliyor. Feed ve OI toplayıcı motorun yasağını, motor onlarınkini hiç görmüyor (aynı IP).

**Dosya.** Host başına bir dosya: `<ban_dir>/ban.<host>.json` (ör. `var/ban.fapi.binance.com.json`, `var/ban.testnet.binancefuture.com.json`). Triyajdaki tek `var/ban.json` yerine host başına dosya: testnet gölge motoru ile gerçek adres ayrı yasaklanır ve eşzamanlı yazarlar birbirini ezmez *(mentor kararı)*. `ban_dir` = sürecin **fiilen açtığı** piyasa veritabanının dizini.

```python
PERSIST_MIN_S = 10          # kalan süresi bundan kısa pencere diske yazılmaz
MAX_HORIZON_S = 259_200     # 3 gün: kayıt en çok written_ms + bu kadar geçerli sayılır
CORRUPT_HOLD_S = 900        # bozuk dosya: mtime + 15 dk boyunca yasak varsayılır
REFRESH_MIN_S = 1.0         # BanGuard dosyayı en sık bu aralıkla yeniden okur

def ban_dir_for(market_db_path: str) -> str            # dirname(abspath(path))
def ban_path(ban_dir: str, base_url: str) -> str       # f"{ban_dir}/ban.{host}.json"; host = URL'nin küçük harfli host adı

@dataclass(frozen=True)
class BanRecord:
    host: str; until_ms: int; http: int | None; source: str | None; written_ms: int | None; corrupt: bool = False

def read_ban(path: str, now_ms: int) -> BanRecord | None
def write_ban(path: str, *, until_ms: int, http: int | None, source: str, now_ms: int) -> bool

class BanGuard:
    def __init__(self, path: str, source: str, now_ms: Callable[[], int]): ...
    path: str
    def active(self) -> BanRecord | None               # etkin kayıt ya da None
    def note(self, until_ms: int, http: int | None) -> bool
```

**Dosya içeriği** (tek JSON nesnesi, UTF-8): `{"v": 1, "host": str, "until_ms": int, "http": int|null, "source": str, "written_ms": int}`. Zamanlar UTC epoch ms. `source` ∈ `engine:<bot>`, `feed`, `oi`, `smoke_testnet`, `smoke_live`.

**`read_ban` kuralları.**
1. Dosya yok → `None`.
2. Geçerli kayıt: nesne, `v == 1`, `until_ms` ve `written_ms` `int` (bool değil) ve `> 0`, `http` `null` ya da `int`, `host` dosya adındaki host ile aynı, `written_ms <= now_ms + 60_000`. Etkin bitiş `eff = min(until_ms, written_ms + MAX_HORIZON_S*1000)`. `eff > now_ms` → `BanRecord(until_ms=eff, …)`; değilse `None`.
3. Dosya var ama 2'ye uymuyor (bozuk JSON, eksik/yanlış tür, gelecekteki `written_ms`, yanlış host) → **bozuk**: `until = min(mtime_ms, now_ms) + CORRUPT_HOLD_S*1000`; `until > now_ms` ise `BanRecord(host=<dosya adındaki>, until_ms=until, http=None, source=None, written_ms=None, corrupt=True)`, değilse `None`. Her iki durumda `WARNING`.
4. Dosya var ama açılamıyor/`stat` edilemiyor (`FileNotFoundError` dışı `OSError`) → `None` + `ERROR` (izin sorunu yasak kanıtı değildir; sağlık bunu `exchange_ban_file_corrupt` ile gösterir, §6).
5. `read_ban` hiçbir koşulda istisna sızdırmaz, dosyayı değiştirmez/silmez.

**`write_ban` kuralları.**
1. `until_ms - now_ms < PERSIST_MIN_S*1000` → yazmaz, `True`.
2. `<path>.lock` üzerinde engelleyen `flock(LOCK_EX)` altında: mevcut dosya geçerli ve `eff >= until_ms` ise yazmaz, `True` (**pencere asla kısaltılmaz**; bozuk mevcut dosyanın üstüne yazılır). Aksi halde aynı dizinde geçici dosya → `fsync` → `os.replace` (atomik), kip `0644`.
3. Her `OSError` → `False` (istisna sızmaz). Dizin yoksa oluşturulmaz → `False`.
4. Süresi dolan dosya **silinmez** (zararsız). Elle temizleme = dosyayı silmek; belgeye yazılır (§6).

**`BanGuard`.** `active()`: son okumadan bu yana `now_ms()` farkı `< REFRESH_MIN_S*1000` ise önbellekteki sonucu döner (süresi dolduysa `None`); değilse `read_ban` ile yeniler. İlk çağrı her zaman okur. `note()`: `write_ban(…, source=self.source, now_ms=self.now_ms())`; başarılıysa önbelleği hemen günceller. Zamanlama **yalnız** enjekte `now_ms` ile ölçülür (monotonik saat yok; testler sahte saati ilerletir).

**Fail-closed.** Bozuk taze dosya = yasak var. Yazılamayan pencere = süreç bellekteki pencereyle (bugünkü davranış) devam eder, sayaç + `ERROR`; süreç bu yüzden çıkmaz.

**Kabul testleri.**
- **P-1** `write_ban(until=now+120 s, http=418, source="feed")` → `True`; dosya yukarıdaki altı alanı taşır; `read_ban(now)` aynı `until_ms`, `http=418`, `source="feed"`, `corrupt=False`; `read_ban(now+121 s)` → `None`; dosya yerinde.
- **P-2** Kalan 9 s → `True`, dosya oluşmaz. Kalan 10 s → dosya oluşur.
- **P-3** Mevcut `until=now+600 s` iken `write_ban(until=now+60 s)` → `True`, dosya bayt-özdeş kalır. `write_ban(until=now+900 s, http=429)` → dosya yeni değerleri taşır.
- **P-4** İçerik `{` / `[]` / `until_ms: "x"` / `until_ms: true` / `v: 2` / `host` farklı / `written_ms = now+5 dk`: `mtime = now` iken `read_ban` → `corrupt=True`, `http is None`, `until_ms == now + 900_000`; `mtime = now − 901 s` iken → `None`. Yedi durumda da istisna yok.
- **P-5** `until_ms = written_ms + 10 gün` → dönen `until_ms == written_ms + 259_200_000`.
- **P-6** Yol bir dizinse (açılamaz) → `read_ban` `None`; `write_ban` olmayan dizine → `False`; ikisi de istisnasız.
- **P-7** Bozuk dosya varken `write_ban(until=now+120 s)` → dosya geçerli kayıtla değişir.
- **P-8** `ban_path("/x/var", "https://FAPI.binance.com")` → `/x/var/ban.fapi.binance.com.json`; `ban_dir_for("var/market.sqlite")` mutlak ve `var` ile biter.
- **P-9** `BanGuard`: `active()` → `None`; başka bir `BanGuard` (aynı yol) `note(now+120 s, 418)`; sahte saat 0,5 s ilerler → ilk guard hâlâ `None`; 1,0 s ilerler → kayıt döner. `note` çağıran guard'ın kendi `active()`i hemen kayıt döner.
- **P-10** Ortak dizin: depo `config/` dizini ve çalışma dizini depo kökü iken `feed_config_from_base(config_dir).db_path`, `scripts/oi_collect.load_pairs_and_db(config_dir)[1]` ve `load_cli_config` ile yüklenen testnet yapılandırmasının `market_db`si için `os.path.realpath(ban_dir_for(...))` üçü de **aynı**.
- **P-11** Modül yalnız stdlib içe aktarır (`trader_engine`, `requests` yok).

---

## 2. M — İmzalı istemci ve motor açılışı

**Sorun.** §1 ile aynı; ayrıca `startup_check` ilk isteği (`GET /fapi/v1/time`) yasak sürerken atıyor (`binance_futures.py:386-404`).

**Gerekli davranış — `SignedRestClient`** (`exchange/binance_rest.py`):
1. Kurucuya `ban_guard: BanGuard | None = None` (anahtar sözcük; `None` = bugünkü davranış, bayt-özdeş).
2. Kurucuda `rec = ban_guard.active()` varsa `_ban_until_ms, _ban_http = rec.until_ms, rec.http` ve `_bump("ban_file_seeded")`.
3. `_send` 1. adımından hemen önce ve `health()` içinde **benimseme**: `rec = ban_guard.active()`; `rec.until_ms > self._ban_until_ms` ise pencere ve `_ban_http` kayda eşitlenir (bellekteki pencere asla kısalmaz). Sonra mevcut pencere denetimi aynen çalışır (istek gitmez, `ExchangeBan(http=_ban_http, retry_after_s=kalan)`).
4. 429, 418 ve 403 dallarında `_ban_until_ms` atandıktan hemen sonra `ban_guard.note(self._ban_until_ms, <429|418|403>)`; `False` dönerse `_bump("ban_persist_failed")` + `ERROR`. Yükseltilen istisnalar, satır içi kısa 429 bekleme ve 403 katlama kuralı **değişmez**. 451 yazılmaz (pencere değildir).
5. `SAPI_BASE` (`apiRestrictions`) çağrısındaki yasak da istemcinin ana host dosyasına yazılır (istemcide tek pencere var; ayrıştırılmaz).

**Kurulum.** `engine.py` canlı broker kurucusu (`SignedRestClient(` çağrısı, ≈ satır 1788): `BanGuard(ban_path(ban_dir_for(cfg.market_db), BASES[cfg.mode]), source=f"engine:{cfg.bot}", now_ms=<istemciyle aynı saat>)`. `scripts/smoke_testnet.py` ve `scripts/smoke_live.py` aynı biçimde (`source` = betik adı); yasak sürerken betik istek atmadan `ExchangeBan` ile başarısız olur.

**Gerekli davranış — `LiveBroker.startup_check`** (`brokers/binance_futures.py`): ilk satır, saat eşitlemesinden **önce**: `rest.health()["ban_until_ms"] > rest.now_ms()` ise `wait = min(kalan_sn + 2, STARTUP_BAN_SLEEP_MAX_S)`; `CRITICAL` günlük (`exchange_ban_persisted` sözcüğü, host, kalan sn); `clock.sleep(wait)`; `EngineExit(5, "exchange_ban_persisted")`. Kayıttaki `http` ne olursa olsun (403 ve bozuk kayıt dahil) kod **5**'tir: kalıcı ret (8) kararını bayat dosya değil, pencere bitince atılan gerçek istek verir. DD-8 açılış sırası değişmez: 1–4. adımlar (yapılandırma, anahtar, kilit, damga) önce ve ağsız çalışır; bu denetim 5. adımın başıdır.

**Çalışırken.** Ek kod yok: başka sürecin yazdığı kayıt 3. maddeyle benimsenir → `ExchangeBan` → mevcut `_note_ban` / `_sync_bans` / `_apply_ban` zinciri (429 → `exchange_rate_limited` engeli; 418/403 → `pause.add("exchange_ban")`; `ban_skipped_exits`). `status.json.exchange.ban_until_ms` benimsenen değeri gösterir.

**Fail-closed.** Guard okunamazsa (§1-4) pencere yok sayılır ve bugünkü yol işler; yazılamazsa bellekteki pencere korunur. Paper/backtest: `SignedRestClient` hiç kurulmaz.

**Dosyalar.** `exchange/binance_rest.py`, `brokers/binance_futures.py` (`startup_check`), `engine.py` (yalnız kurucu çağrısı), `scripts/smoke_testnet.py`, `scripts/smoke_live.py`, `docs/motor/11-canli-broker.md` §3.3, §3.4-1, §4, §10 (F8–F10).

**Kabul testleri** (istek sayısı `tests/engine/fake_exchange.py` kayıt listesinden).
- **M-1** Sahte borsa 418 + `Retry-After: 120` döner → `ExchangeBan(http=418)`; dosyada `until_ms == now_ms + 120_000`, `http == 418`, `source == "engine:learner"`. Aynı şey 429 + `Retry-After: 60` (okuma) için `http == 429`; 403 için `until_ms == now + 300_000`, `http == 403`.
- **M-2** 429 + `Retry-After: 2` → dosya oluşmaz (P-2), davranış bugünküyle aynı (satır içi bekleme + yeniden deneme).
- **M-3** 451 → dosya oluşmaz.
- **M-4** Dosyada `now+120 s` kaydı varken **yeni** `SignedRestClient` kurulur: `health()["ban_until_ms"]` kayıtla aynı; `counters["ban_file_seeded"] == 1`; her `kind` ve `protective=True` dahil ilk çağrı `ExchangeBan` verir, sahte borsaya giden istek **0**.
- **M-5** Açılış: `mode=testnet`, geçerli damga, dosyada `now+120 s` (`http=418`) → `build_engine` `EngineExit` kod 5, ileti `exchange_ban_persisted`; istek 0 (`/fapi/v1/time` dahil); `clock.sleep` tam bir kez `122` ile çağrılmış. Kalan 1000 s → uyku `300`.
- **M-6** M-5, kayıt `http=403` ve bozuk dosya (`mtime = now`) ile → yine kod 5, istek 0.
- **M-7** Dosyada süresi dolmuş kayıt → açılış bugünkü gibi tamamlanır; dosya silinmemiştir.
- **M-8** Yabancı damgalı state + gelecekte ban kaydı → kod 8 `state_stamp_mismatch` (damga önce), istek 0.
- **M-9** Çalışırken: motor açık, bir açık pozisyon; ayrı bir `BanGuard(source="feed")` aynı dosyaya `note(now+120 s, 418)`. Saat ≥ 1 s ilerletilip `live_tick` çağrılır: bu andan pencere sonuna kadar sahte borsaya istek **0**; `pause.holds()` içinde `exchange_ban`; `status.json.exchange.ban_until_ms` kayıtla aynı. Aynı senaryo `http=429` ile → tutuş yok, giriş engeli `exchange_rate_limited`.
- **M-10** Ban dizini yazılamazken 418 → `ExchangeBan` aynen yükselir, `counters["ban_persist_failed"] == 1`, bellekteki pencere etkin (sonraki çağrı istek atmaz).
- **M-11** `ban_guard=None` → `tests/engine/test_binance_rest_spec.py` değişmeden geçer.
- **M-12** `mode=paper` motor kurulumu ve bir adım: ban dizininde hiçbir dosya oluşmaz/okunmaz (dizinde gelecekte ban kaydı olsa da davranış aynı); altın geri test bit-özdeş.

---

## 3. F — Feed (`marketdata/rest_public.py`, `marketdata/feed.py`)

**Gerekli davranış.**
1. `PublicRestClient` kurucusuna `ban_guard: BanGuard | None = None`; öznitelik `ban_guard`. `get()` her denemede, `_wait_for_weight`ten ve istekten **önce** `rec = ban_guard.active()`: varsa istek atmadan `ExchangeBan(http=rec.http if rec.http is not None else 418, retry_after_s=<kalan sn, yukarı yuvarlı>)`.
2. 429 yanıtında (her biri) `note(now + wait*1000, 429)`; 418'de `note(now + ra*1000, 418)` (`ra` mevcut kuralla, okunamazsa 120). 451 yazılmaz. Yazma hatası yalnız `ERROR` günlüğüdür.
3. `Feed.start()`: kilit alındıktan sonra, `_measure_offset`ten **önce** `guard = getattr(rest, "ban_guard", None)`; `rec = guard.active()` varsa: kalan `> BAN_MAX_WAIT_S` → `CRITICAL` + `SystemExit(EXIT_BAN)` (DD-1 kuralı: birim yeniden başlatmaz); değilse `CRITICAL` (`ban_persisted`), `bans` sayacı +1, `clock.sleep(kalan + BAN_MARGIN_S)`, sonra olağan açılış. `--startup-retry` değerinden bağımsızdır.
4. `feed.py` içinde `PublicRestClient` kuran her giriş noktası (`_make_rest` kullanıcıları) guard'ı `ban_dir_for(cfg.db_path)` ve istemcinin `base_url`i ile, `source="feed"` olarak verir.
5. Çalışma yolundaki mevcut yasak işleme (`_ban_wait_s`, `MAX_CONSEC_BANS`, çıkış 3/6) değişmez; ön-gönderim retleri aynı yoldan geçer.

**Fail-closed.** Bozuk taze kayıt 418 sayılır. `ban_guard=None` → bugünkü davranış.

**Kabul testleri** (sahte oturumun `get` çağrı sayısı).
- **F-1** Dosyada `now+120 s` (`http=418`) → `Feed.start()` sonrası: ilk HTTP isteğinden önce `clock.sleep(125)` çağrılmış; uyku öncesi istek 0; uyku sonrası açılış tamamlanır.
- **F-2** Kalan 3601 s → `SystemExit` kod 3, istek 0, uyku yok. `main(...)` dönüşü 3.
- **F-3** Çalışırken 418 + `Retry-After: 300` → dosyada `http=418`, `until_ms == now + 300_000`, `source == "feed"`. 429 + `Retry-After: 30` → `http=429`.
- **F-4** Çalışırken başka kaynak (`engine:learner`) `note(now+60 s, 429)`; saat 1 s ilerler; `run_once()` → HTTP isteği 0, `FeedTick.banned is True`, uyku ≥ kalan süre.
- **F-5** Bozuk dosya (`mtime = now`) → `get()` `ExchangeBan(http=418)`, istek 0.
- **F-6** `ban_guard=None` ile `tests/engine/test_engine_rest_public_spec.py` ve `test_dd1_feed_impl.py` değişmeden geçer.

---

## 4. T — OI toplayıcı (`marketdata/oi_collector.py`, `scripts/oi_collect.py`)

**Sorun.** Toplayıcı yasağı görmüyor, yazmıyor ve IP ağırlığını ölçmüyor; canlıda motorla aynı IP'den çalışacak.

**Gerekli davranış.**
1. `HttpClient` alanları: `ban_guard: BanGuard | None = None`, `now_ms: Callable[[], int]` (varsayılan sistem saati), `last_used_weight: int | None = None`.
2. `get_json` her denemede, aralık uykusundan ve `requests_made` artışından **önce**: `ban_guard.active()` varsa istek atmadan `BanError`.
3. 418 → `note(now + ra*1000, 418)` (`Retry-After` sayı değil/yok/negatif → 120) sonra mevcut `BanError`. Her 429 → `note(now + ra*1000, 429)` (mevcut yeniden deneme mantığı değişmez).
4. Başarılı yanıtta `X-MBX-USED-WEIGHT-1M` başlığı tam sayıya çevrilebiliyorsa `last_used_weight`e yazılır; başlık yok/bozuk → değer değişmez.
5. `OI_WEIGHT_CEILING = 1200` (dakikalık IP sınırı 2400'ün %50'si). `collect(..., weight_ceiling: int = OI_WEIGHT_CEILING)`: her (çift, uç) öncesinde ve `fetch_window` içinde ilk sayfadan sonraki her sayfa öncesinde `getattr(client, "last_used_weight", None)` `>= weight_ceiling` ise koşu **durur**: `Stats.budget_hit = True`, yeni alan `Stats.weight_stop = True`; hata sayılmaz; yarım kalan pencerenin satırları yazılmaz (sonraki koşu son satırdan sürdürür). Kip ayrımı yoktur (her ortamda geçerli; yalnız sıkılaştırma).
6. `scripts/oi_collect.py main`: guard `ban_dir_for(<market_db>)` + `C.BASE_URL`, `source="oi"`; `--ban-dir` ile geçersiz kılınabilir. İlk HTTP isteğinden önce `active()` varsa: `WARNING` `event=ban_skip host=… left_s=…`, istek 0, dönüş `EXIT_OK` (alarmı §6 üretir; 5 dakikada bir `OnFailure` gürültüsü istenmez). Koşu içinde alınan yasakta dönüş `EXIT_BAN` (değişmez). Kapanış günlüğüne `used_weight=<son değer|None> weight_stop=<bool>` eklenir (triyaj: "ağırlık bütçesi ölçülsün").
7. Enjekte edilen `client` (testler) için de 6. maddedeki açılış denetimi `main` içinde yapılır.

**Fail-closed.** Başlık hiç gelmiyorsa kısma devreye girmez; mevcut `--max-requests` (900) ve `min_interval_s` sınırları geçerli kalır ve günlükte `used_weight=None` görünür. Bu uçların başlığı döndürdüğü DD-5 "canlı-yalnız" listesinde bir kez doğrulanır (bkz. §7).

**Kabul testleri** (`urllib.request.urlopen` yaması ya da enjekte `client`).
- **T-1** Dosyada `now+120 s` kaydı → `main([...], client=sahte)` dönüş 0; `sahte.get_json` hiç çağrılmamış.
- **T-2** `HttpClient(ban_guard=…)` + etkin kayıt → `get_json` `BanError`, `urlopen` çağrısı 0, `requests_made == 0`.
- **T-3** `urlopen` 418 + `Retry-After: 300` → `BanError`; dosyada `http=418`, `until_ms == now + 300_000`, `source == "oi"`. `Retry-After` yok → `now + 120_000`. `main` dönüşü `EXIT_BAN`.
- **T-4** `urlopen` 429 + `Retry-After: 30` → dosyada `http=429`.
- **T-5** Yanıt başlığı `X-MBX-USED-WEIGHT-1M: 1234` → `last_used_weight == 1234`; başlıksız yanıt sonrası değer 1234 kalır.
- **T-6** Sahte istemci 3. istekten sonra `last_used_weight = 1200` yapar → `collect` toplam 3 istekle biter; `budget_hit` ve `weight_stop` `True`; `errors == 0`; `main` dönüşü 0. `1199` → durmaz.
- **T-7** `last_used_weight` özniteliği olmayan sahte istemci → `tests/test_oi_collector.py` değişmeden geçer.
- **T-8** Holdout: `in_holdout` / `clip_windows` çıktıları ve bu aralığa hiç istek gitmemesi DD-7 öncesiyle aynı.

---

## 5. G — Ağırlık eşiğinde giriş reddi (`brokers/binance_futures.py`)

**Sorun.** Kullanılan ağırlık yüksekken yeni pozisyon açmak, dolumdan hemen sonra stop isteğinin yasağa takılma olasılığını büyütür. Bugün `weight_soft` üstünde giriş yalnız dolaylı olarak (DD-8 D2 okuması reddedildiği için `account_mode_unverified` → `not_prepared`) engelleniyor; neden yanlış etiketleniyor.

**Gerekli davranış.** `market_order`, yalnız `role == "entry"`, yerel denetimlerden sonra ve DD-8 D2 `position_risk` okumasından **önce**: `env != "testnet"` ve `rest.health()["used_weight"] >= rest.weight_soft` (1200) ise emir gönderilmez → `OrderResult` reddi `reason="weight_high"`; sayaç `entry_weight_rejects` +1; `WARNING`. Hiçbir istek gitmez (`position_risk` de POST da). Mandal, tutuş ve `on_ban` tetiklenmez; `account_mode_unverified` artmaz; bir sonraki sinyal olağan yoldan denenir. Testnette atlanır (ağırlık başlığı paylaşımlı/gürültülü; mevcut mentor kararıyla tutarlı). Çıkış, stop, hedef, iptal yolları etkilenmez. Yasak penceresi etkinken giriş zaten `exchange_ban` ile reddedilir (değişmez; ban denetimi önce gelir).

**Fail-closed.** `health()` istisna verirse ya da `used_weight` sayı değilse giriş `weight_high` ile reddedilir.

**Kabul testleri.**
- **G-1** `env=live`, sahte borsa `X-MBX-USED-WEIGHT-1M: 1200` döndürdükten sonra giriş → ret `weight_high`; bu çağrı için sahte borsaya giden istek 0; `counters()["entry_weight_rejects"] == 1`; `account_mode_unverified == 0`; `entries_blocked_reasons` boş.
- **G-2** `1199` → giriş olağan (D2 okuması + POST).
- **G-3** `1200` iken reduceOnly piyasa çıkışı ve stop kurma gönderilir.
- **G-4** `env=testnet`, `1500` → giriş gönderilir.
- **G-5** Başlık zamanı 60 sn'den eskiyse (`used_weight` 0'a döner) giriş yeniden olağan.
- **G-6** Motor düzeyi: G-1 koşulunda geçerli sinyal → emir satırı `rejected`, `detail="weight_high"`; pozisyon açılmaz; duraklatma tutuşu eklenmez.

---

## 6. S — Sağlık alarmı ve elle yol

**Sorun.** Yasak sırasında bot susar; kullanıcı açık pozisyonu olduğunu ve elle kapatabileceğini bilmelidir. Motor açılışta çıkış 5 döngüsündeyken `status.json` bayattır; bu yüzden kaynak ban dosyasıdır.

**Gerekli davranış.**
1. `H.BanProbe(host: str, until: datetime | None, http: int | None, source: str | None, corrupt: bool = False)`; `H.HealthSnapshot.bans: tuple[BanProbe, ...] | None = None` (sona, varsayılanlı; `None` = yoklanmadı → denetim üretilmez).
2. `scripts/health_run.py: probe_bans(ban_dir: str) -> tuple[H.BanProbe, ...]`: dizindeki her `ban.*.json` için bir satır (süresi dolmuş olanlar dahil; karar çekirdekte). §1-2'ye uymayan ya da okunamayan dosya → `corrupt=True, until=None`. Dizin yok → `()`. `collect`: `HEALTH_BAN_DIR` ortam değişkeni, yoksa sağlığın kullandığı piyasa veritabanının dizini.
3. Yeni denetim `exchange_ban` (bot ekli değil, tek satır). "Açık pozisyon var" = `snap.api` içinde `has_exchange=True` olan herhangi bir yoklamada `open_trade_ids` boş değil **ya da `None`** (bilinmiyor = var say). Öncelik sırasıyla:
   - `until > snap.now` olan kayıt var **ve** açık pozisyon var → `CRIT`, kod `exchange_ban_open_positions`, değer = kalan sn (en uzun);
   - `until > snap.now` olan kayıt var → `WARN`, kod `exchange_ban`;
   - `corrupt` kayıt var → `WARN`, kod `exchange_ban_file_corrupt`;
   - aksi → `OK`.
4. `exchange_ban_open_positions` ve `exchange_ban` ilk görüşte alarm üretir (tekrar beklenmez). Sağlık 5 dakikada bir koşar; alarm gecikmesi en çok ≈ 5 dk'dır *(mentor kararı: motorun kendisi Telegram'a yazmaz; yasaklı süreç ek ağ işi yapmaz)*.
5. Türkçe metin (`health.py` metin tablosu). CRIT başlık: "Borsa geçici engel koydu, açık pozisyon var"; gövde host, kalan dakika ve şu cümleyi içerir: "Bot engel bitene kadar emir gönderemez. Borsadaki zarar-kes emirleri yerinde durur. Gerekirse pozisyonu Binance uygulamasından elle kapatın." Düzelme: "Borsa engeli kalktı".
6. **Elle yol belgesi:** `docs/motor/11-canli-broker.md` §10'a F9 altına "Yasak sırasında elle kapatma" paragrafı (Binance uygulaması → Vadeli → Pozisyonlar → Piyasadan kapat; bot yasak bitince kapanışı mutabakatta `manual` olarak kaydeder; `exchange_ban` tutuşu sunucuda `pause --clear` ile kalkar; ban dosyası yalnız yanlış kayıt kesinse elle silinir) ve §12 geçiş listesine tek satır. `docs/saglik-spec.md`ye denetim satırı.

**Dosyalar.** `src/trader_core/health.py`, `scripts/health_run.py`, `docs/saglik-spec.md`, `docs/motor/11-canli-broker.md`.

**Kabul testleri.**
- **S-1** `bans=(BanProbe("fapi.binance.com", now+120 s, 418, "feed"),)` + `ApiProbe(has_exchange=True, open_trade_ids=(7,))` → `exchange_ban` `CRIT`, kod `exchange_ban_open_positions`; birleşik durum `CRIT`.
- **S-2** Aynı, `open_trade_ids=()` → `WARN` `exchange_ban`. `open_trade_ids=None` → `CRIT`. `has_exchange=True` yoklama hiç yok → `WARN`.
- **S-3** `until = now − 1 s` → `OK`. `bans=()` → `OK`. `bans=None` → raporda `exchange_ban` denetimi yok.
- **S-4** Yalnız `corrupt=True` kayıt → `WARN` `exchange_ban_file_corrupt`; etkin kayıtla birlikte → etkin kaydın kodu.
- **S-5** `plan_alerts` her iki kodda ilk koşuda alarm üretir; kayıt süresi dolduktan sonraki koşuda düzelme iletisi.
- **S-6** CRIT iletisi "elle kapatın" ifadesini ve host adını içerir; metin tablosunda üç kodun da Türkçe karşılığı var.
- **S-7** `probe_bans`: geçerli dosya → alanlar doğru; `{` içerikli dosya → `corrupt=True`; dizin yok → `()`; `ban.x.json.lock` ve geçici dosyalar satır üretmez.
- **S-8** Var olan `HealthSnapshot(...)` kurucuları bozulmadan çalışır.

---

## 7. Notlar ve teslim koşulları

- **DD-5'e eklenecek "canlı-yalnız" satırı:** `/futures/data/openInterestHist` ve long/short oranı uçları `X-MBX-USED-WEIGHT-1M` başlığını döndürüyor mu (T-5'in gerçek kanıtı). Döndürmüyorsa OI kısması ölçüsüz kalır; konu o zaman mentora döner.
- **Yeniden başlatma döngüsü:** çıkış 5 + en çok 300 sn uyku, `StartLimit` (10 dk'da 5) sınırına takılmaz; kalan süre çok kısaysa da her tur en az `kalan + 2 sn` uyur.
- **Test dosyaları.** Şartname testleri `tests/engine/test_dd7_spec.py` (bağımsız ajan), uygulama testleri `tests/engine/test_dd7_impl.py`; sağlık `tests/test_health_dd7.py`; OI `tests/test_oi_dd7.py`.
- **Teslim.** Tüm test paketi yeşil; altın geri test bit-özdeş; dondurulmuş dosyalarda `git diff` boş; `tests/engine/test_engine_module_inventory.py` değişmeden geçer (yeni modül `trader_core` altındadır); yeni bağımlılık yok.

## 8. Kullanıcıya gidecek kararlar

Bu paket için kullanıcı kararı **gerekmiyor**; bütün seçimler sıkılaştırma yönünde mentor kararıdır. Bilgi: borsa geçici engel koyarsa bot engel bitene kadar hiç emir göndermez (göndermesi engeli uzatır); borsadaki zarar-kes emirleri yerinde kalır; açık pozisyon varsa en geç 5 dakika içinde Telegram'a acil uyarı gelir ve pozisyon istenirse telefondan elle kapatılabilir.

---

## DD-9 için devredilenler

DD-8 incelemesinde açılan, DD-7 kapsamına girmeyen maddeler (kaybolmasın diye buraya yazıldı):

1. **`ExecStartPre` yeniden başlatma döngüsü.** `init-ledger` çıkış 8 verdiğinde birim sonsuz yeniden başlıyor: `RestartPreventExitStatus` yalnız ana süreci kapsar. Çözüm DD-9 birim dosyalarında (damga denetimini ana sürece taşımak ya da sarmalayıcı).
2. **`account_mode_unverified` sayacı sağlık alarmına bağlanmalı** (bugün yalnız günlükte; DD-7 §5 sonrası bu sayaç artık ağırlık yüzünden artmaz, alarm anlamlı olur).
3. **`health_backup._copy_corrupt`** yalnız `FileNotFoundError` yakalamalı (başka `OSError` yedeği başarısız saymalı).
4. **`smoke_live` `guard_config`:** canlı koruma denetimindeki yol-kuyruğu eşleştirmesi yeniden gözden geçirilmeli.
5. **`open_ledger(create=True)`** yabancı ve eski şemalı bir defteri damga reddinden **önce** göç ettiriyor; sıra tersine çevrilmeli (önce damga, sonra göç).
6. **DD-8 şartnamesi §2.3 ifade düzeltmesi:** `ledger_path` yalnız paper kipinde geçiriliyor; metin buna göre düzeltilmeli.
7. **`config/engine.live.json`** `expected_wallet_max: 1500` ile yazılacak (kullanıcı kararı; kayıt: commit `89d7ad1`).
8. **Sunucu:** 14 Aralık gölge koşusundan önce `var-testnet/learner` → `var-testnet/learner.pre-dd8-<tarih>` adına taşınacak (silinmez).
