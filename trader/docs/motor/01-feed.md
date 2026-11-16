# 01 — Piyasa verisi: feed, market.sqlite, veri kaynakları (spesifikasyon v1, 16 Kasım 2026)

Kaynak kararlar: `motor-tasarimi.md` §1.3 (ham REST, senkron), §2.1 (veri akışı), §2.2 (`marketdata/*`), §2.9 (süreç modeli: feed ~60 MB, pandas yok), §3.1 (Faz A: yalnız REST yoklama), §4.1 (HistoricalSource, 1m veri). Bağımlılıklar: `02-clock-bars.md` (tipler, `bars.py`, `Clock`), `07-copied-1l3a.md` (`marketdata/rest_public.py`, `exchange/rules.py`, `fileio.py` bu birimin dışında kopyalanır; imzaları 07'de donmuştur). Bu belge kod, test ve commit içermez.

## 1. Kararlar (özet)

| Konu | Karar |
|---|---|
| Süreçler | `trader-feed` **tek yazar**; her bot motoru `market.sqlite`'ı **salt okunur** açar. L ve T aynı barları görür |
| Yalnız kapanmış bar | Barın kapanışı **sunucu saatine** göre geçmişse yazılır. Yerel saat ileri/geri olabilir; bu yüzden açılışta `server_time` ile fark ölçülür, `now_server = clock.now() + offset` |
| REST doğruluk kaynağıdır | tf barları REST'ten (1m'den toplanmaz); 1m toplamı tf REST barıyla karşılaştırılır, fark uyarıdır (bar builder görevi, §6) |
| Ölü bar yok | Eksik bar `gaps` tablosuna işaretlenir; bar uydurulmaz, doldurulmaz |
| Değişmezlik | Kapanmış bar bir kez yazılır; sonradan farklı değerle gelirse **eski değer korunur**, çakışma sayılır ve loglanır (determinizm: paper = backtest) |
| pandas | `store.py`, `feed.py` **pandas/numpy import etmez**. `sources.py` (motor tarafı) pandas kullanır ve feed tarafından import edilmez |
| Saat | Hiçbir yerde `time.*`/`datetime.now`; `Clock` ve `rest_public`'in enjekte edilen `now_s`/`sleep` işlevleri |

## 2. DOSYA SAHİPLİĞİ

Bu birim yalnızca şunlara dokunur:

- `src/trader_engine/marketdata/__init__.py` (boş)
- `src/trader_engine/marketdata/store.py`, `feed.py`, `sources.py`
- `tests/engine/test_engine_store_spec.py`, `test_engine_feed_spec.py`, `test_engine_sources_spec.py` (bağımsız test ajanı); `test_engine_feed_impl_smoke.py` (gerçekleme ajanı); `tests/engine/fixtures/binance/klines_*.json`, `mark_klines_*.json`, `funding_*.json` (kayıtlı **sahte** yanıtlar; gerçek yanıt kaydı Faz B'dir)

Dokunulmaz: `marketdata/rest_public.py` (07), `fileio.py` (07), `exchange/*` (07), `bars.py`/`types.py` (02), `scripts/fetch_binance_vision.py` (06).

`feed.py`'nin 1l3a `paper_canli.py::CanliKaynak` (`baslat`/`guncelle`/`funding_guncelle`) kaynaklı kısımları bu birimde, **07'deki kopyalama kurallarına** göre uygulanır (bkz. `07-copied-1l3a.md` §4 tablosu, "uygulayan: 01").

## 3. `market.sqlite` şeması (`PRAGMA user_version = 1`)

WAL, `busy_timeout=5000`, `synchronous=NORMAL` (veri yeniden çekilebilir). Zamanlar epoch ms (`INTEGER`).

```sql
CREATE TABLE bars(
  kind TEXT NOT NULL CHECK(kind IN ('last','mark')),
  pair TEXT NOT NULL,                       -- kanonik "BTC/USDT"
  tf   TEXT NOT NULL CHECK(tf IN ('1m','15m','1h','4h')),
  open_ms INTEGER NOT NULL,
  o REAL NOT NULL, h REAL NOT NULL, l REAL NOT NULL, c REAL NOT NULL,
  v REAL NOT NULL DEFAULT 0,
  written_ms INTEGER NOT NULL,
  PRIMARY KEY(kind, pair, tf, open_ms)) WITHOUT ROWID;
CREATE TABLE funding(
  pair TEXT NOT NULL, ts_ms INTEGER NOT NULL, rate REAL NOT NULL, mark REAL,
  PRIMARY KEY(pair, ts_ms)) WITHOUT ROWID;
CREATE TABLE rules(pair TEXT PRIMARY KEY, json TEXT NOT NULL, fetched_ms INTEGER NOT NULL);
CREATE TABLE gaps(
  kind TEXT NOT NULL, pair TEXT NOT NULL, tf TEXT NOT NULL, open_ms INTEGER NOT NULL,
  reason TEXT NOT NULL,                     -- 'missing' | 'minute_missing' | 'agg_mismatch' | 'conflict' | 'abnormal_close'
  detected_ms INTEGER NOT NULL, PRIMARY KEY(kind, pair, tf, open_ms, reason)) WITHOUT ROWID;
CREATE TABLE feed_meta(k TEXT PRIMARY KEY, v TEXT NOT NULL);   -- 'started_ms','last_ok:<pair>:<tf>:<kind>','server_offset_ms','counters'
```
`rules.json` = `exchange.rules.spec_to_json(SymbolRuleSpec)` çıktısı (07; Decimal metin alanları: `tick, step, min_qty, max_qty, market_step, market_min, market_max, min_notional`). `StoreSource.rules` bunu `spec_from_json` → `to_symbol_rules` ile `types.SymbolRules`'a çevirir (piyasa emri adımı/min/max kullanılır).

Saklama: 1m barlar 14 gün (`retention_1m_days=14`; saatte bir `DELETE`), 15m/1h/4h barlar süresiz, `gaps` 90 gün.

## 4. `store.py`

```python
class MarketStore:
    def __init__(self, path, *, read_only: bool = False)      # read_only: file:...?mode=ro URI; yazma çağrısı -> StateError değil DataError
    def close(self) -> None
    # yazma (yalnız feed)
    def put_bars(self, bars: Sequence[Bar], *, now_ms: int) -> PutResult    # PutResult(inserted, duplicates_equal, conflicts)
    def put_funding(self, points: Sequence[FundingPoint]) -> int
    def put_rules(self, pair: str, rules_json: str, now_ms: int) -> None
    def mark_gap(self, kind, pair, tf, open_ms, reason, now_ms) -> None
    def prune(self, now_ms: int, retention_1m_days: int = 14) -> int
    def meta_set(self, k, v) -> None ; def meta_get(self, k) -> str | None
    # okuma
    def last_open_ms(self, kind, pair, tf) -> int | None
    def query_bars(self, kind, pair, tf, until_ms: int, n: int | None) -> list[Bar]       # close_ms <= until_ms, artan sırada, son n
    def query_range(self, kind, pair, tf, start_ms: int, end_ms: int) -> list[Bar]       # open_ms ∈ [start_ms, end_ms)
    def query_funding(self, pair, start_ms, end_ms) -> list[FundingPoint]                 # ts ∈ (start_ms, end_ms]
    def get_rules(self, pair) -> tuple[str, int] | None
    def gaps_in(self, pair, tf, start_ms, end_ms) -> list[tuple[int,str]]
```
Kurallar:
- `put_bars`: `INSERT ... ON CONFLICT DO NOTHING`; çakışmada mevcut satır ile yeni karşılaştırılır: `o,h,l,c` göreli fark > 1e-9 ya da `v` göreli fark > 1e-6 ise `conflicts += 1`, `gaps(reason='conflict')`, eski değer kalır.
- Bar doğrulaması (yazmadan önce, ihlalde yazılmaz + `DataError` listesi döner, tüm toplu işi bozmaz): `o,h,l,c` sonlu ve `> 0`, `h ≥ max(o,c,l)`, `l ≤ min(o,c,h)`, `open_ms` tf'ye hizalı. **mark barlarında `v` yok sayılır (0)**.
- Tüm yazmalar tek `BEGIN IMMEDIATE` işleminde; işlem içi hata → geri al, `DataError`.
- Süreç kilidi: `feed` başlarken `var/market.lock` dosyasına `fcntl.flock(LOCK_EX|LOCK_NB)`; ikinci feed süreci "locked" ile çıkar (tek yazar; risk 10).

## 5. `feed.py`

```python
@dataclass(frozen=True)
class FeedConfig:
    pairs: tuple[str, ...]; db_path: str; lock_path: str; status_path: str
    grace_s: float = 3.0                      # kapanıştan sonra REST yayını için bekleme
    minute_fetch_limit: int = 5               # dakikalık turda son K bar (kendini iyileştirme)
    backfill_bars: Mapping[str,int] = {"1m": 4320, "15m": 5000, "1h": 1500, "4h": 1500}
    funding_refresh_s: float = 3600.0; rules_refresh_s: float = 3600.0
    retention_1m_days: int = 14

class Feed:
    def __init__(self, cfg: FeedConfig, rest: PublicRestClient, store: MarketStore, clock: Clock)
    def start(self) -> None          # kilit al, server offset ölç, rules çek, backfill
    def backfill(self) -> BackfillReport
    def run_once(self) -> FeedTick   # zamanı gelen her şeyi yapar; hata bir çifti/seriyi atlar, döngüyü öldürmez
    def run_forever(self) -> None    # while: run_once(); clock.sleep(1.0)

def snapshot_rules(rest: PublicRestClient, pairs: Sequence[str], clock: Clock, *, store: MarketStore | None = None,
                   out_json_path: str | None = None) -> dict[str, str]
        # exchangeInfo -> extract_all_rules -> {pair: spec_json}; store verilirse put_rules, out_json_path verilirse
        # history_dir/rules.json (atomic_write_json). Çiftlerden biri RulesError verirse o çift atlanır ve sonuçta hata kodu döner. 05 `rules-snapshot` komutu bunu çağırır.
    def stats(self) -> dict          # sayaçlar: requests, errors, gaps, conflicts, agg_mismatch, last_ok
```

### 5.1 Zamanlama (`run_once`, `now_s = clock.now() + offset`)

1. **Dakikalık tur:** her çift için son kapanmış dakika `m = last_closed_open(now_s, "1m")`; `store.last_open_ms(...) < m` ise `klines(symbol,"1m", limit=minute_fetch_limit)` ve `mark_price_klines(symbol,"1m", limit=minute_fetch_limit)`; yalnız `now_s ≥ close_ts + grace_s` olduktan sonra denenir. Kapanmamış (son) satır atılır (§5.3).
2. **tf kapanışı:** `closing_tfs(floor_tf(now_s,"1m"))` içindeki `15m`/`1h`/`4h` için her çift `klines(symbol, tf, limit=2)` (+ `grace_s`). `4h` ve `1h` mark barı yazılmaz (mark yalnız 1m).
3. **Saatlik:** `exchange_info()` → her çift `extract_rules` → `put_rules`; `funding_rates(symbol, start_ms=son_ts+1)` → `put_funding`; funding noktasının `mark`'ı o anki 1m mark barının `o`'sundan doldurulur (yoksa NULL; sonradan `run_once` boş mark'ı doldurmayı dener).
4. **Temizlik:** saatte bir `prune`.
5. **Durum:** her `run_once` sonunda `fileio.atomic_write_json(status_path, {...})`: çift × seri son başarı zamanı, sayaçlar, `server_offset_ms`.

İstek bütçesi: 10 çift × 2 istek/dk + tf kapanışları ≈ 25 istek/dk (§2.9). Hız sınırı `PublicRestClient` içindedir (07).

### 5.2 Açılış ve boşluk doldurma

- `start()`: offset = `server_time_ms() - clock_ms`; `|offset| > 60 sn` ise `WARNING` (feed çalışır; barlar sunucu saatine göre süzülür).
- `backfill()`: her (çift, tf, kind) için gereken aralık `[son_yazılı+1, now_server)`; hiç yoksa `backfill_bars[tf]` bar geriye. Sayfalama 1500; sayfalar arası `startTime = son_open+1`. Eksik açılış anları (`expected_opens` − yazılı) `gaps(reason='missing')` olarak işaretlenir; borsa o barı vermediyse (REST boşluk) **işaret kalır**, bar yazılmaz.
- Yeniden başlatma: aynı `backfill` her açılışta çalışır; yazılı barlar çakışma sayılmaz (`duplicates_equal`).

### 5.3 Kapanmış bar süzgeci (`rows_to_bars` kuralı, 07'den çağrılır)

`closeTime(ms) + 1 ≤ now_server_ms` ve `closeTime == open + tf_ms − 1` (aksi `gaps(reason='abnormal_close')` + yazma yok). Son satır genellikle açık bardır ve atılır. `klines` satır alanları (`[openTime, o, h, l, c, v, closeTime, quoteVol, trades, ...]`) ve `markPriceKlines` aynı dizi biçimindedir (hacim 0): *Binance uç adları ve yanıt biçimi "doğrulanacak" (Faz A'da yalnız kayıtlı sahte fixture ile test; gerçek yanıt kaydı ilk canlı veri çekmede alınır ve fixture olarak eklenir).*

### 5.4 Bar builder denetimi

Bir tf barı (15m/1h/4h) yazıldıktan sonra, aralığındaki **tüm** 1m last barları store'daysa `bars.aggregate_minutes` ile toplanır ve REST barıyla karşılaştırılır: `o,h,l,c` göreli fark > 1e-9 ya da `v` > 1e-6 → `gaps(reason='agg_mismatch')`, `WARNING`; bir dakika eksikse `gaps(reason='minute_missing')` (uyarı, hata değil). **REST tf barı geçerli kalır; toplama yalnız tanı amaçlıdır.**

### 5.5 Hata yönetimi (fail-closed)

- Bir çift/seri için REST hatası: o tur o seri atlanır, `errors` sayacı artar; veri eskiyse motor `stale_data` ile giriş yapmaz (05). Feed kendiliğinden bir şey uydurmaz.
- 418/451/429 `PublicRestClient` istisnası (`ExchangeBan`): feed `Retry-After`'e kadar uyur (`clock.sleep`), motorlar bayat veri görür → giriş yok. İstisna feed'i düşürmez; tekrarlayan ban 6 kez üst üste ise süreç `exit code 3` ile çıkar (systemd `Restart=always` yeniden başlatır).
- `store` yazma hatası (disk dolu, kilit): `DataError`; tur atlanır; `errors` sayacı; 3 ardışık tur → süreç çıkar.
- Yerel saat ile sunucu farkı > 5 dk: feed **hiç bar yazmaz** (`ClockError` günlüğe), çünkü kapanmışlık süzgeci güvenilmez.

## 6. `sources.py` — motor tarafı okuyucular (pandas burada serbest)

```python
class MarketView(Protocol):
    def bars(self, pair: str, tf: str, until: datetime, n: int | None = None, kind: Kind = "last") -> pd.DataFrame
        # until ZORUNLU: yalnız close_ts <= until olan barlar. Sütunlar: open, high, low, close, volume; indeks:
        # tz-aware UTC DatetimeIndex adı "date" = bar AÇILIŞI (freqtrade `date` ile aynı). Gelecek bar asla dönmez.
    def contiguous_tail(self, pair: str, tf: str, until: datetime, max_n: int = 5000) -> int
        # sondan geriye kesintisiz (beklenen açılışların hepsi var) bar sayısı
    def minute_steps(self, pairs: Sequence[str], start: datetime, end: datetime) -> Iterator[MinuteStep]
        # açılışı [start, end) içindeki adım barları, zaman sırasıyla; her MinuteStep(ts, bars: Mapping[pair, MinuteBar]).
        # Yalnız o adımda barı bulunan çiftler map'te yer alır. Tembel (parça parça) okur.
    def funding(self, pair: str, start: datetime, end: datetime) -> list[FundingPoint]   # ts ∈ (start, end]
    def rules(self, pair: str) -> SymbolRules                                             # yoksa DataError
    def last_closed_minute(self, pair: str) -> datetime | None                            # son kapanmış 1m'in AÇILIŞI
    def data_range(self, pair: str, tf: str) -> tuple[datetime, datetime] | None          # (ilk açılış, son açılış)
    def step_seconds(self) -> int                                                         # 60 | 900 (kaba mod)

@dataclass(frozen=True)
class MinuteStep: ts: datetime; bars: Mapping[str, MinuteBar]
```
Ortak değişmezler (iki uygulama için de):
- **İleriye bakma yok:** `bars(until=U)` hiçbir zaman `open_ts + tf > U` bar dönmez; `minute_steps` açılışı `end`'den büyük adım dönmez.
- `MinuteBar` birleştirmesi: aynı `open_ts`'li last ve mark 1m barı çift olarak; mark yoksa `mark_* = None` (`step_s=60`).
- `bars()` mark barı yalnız `1m` için tutulur; `kind="mark"` ve `tf != "1m"` → `DataError` (HistoricalSource 1h mark dosyasını **yalnız** funding mark değeri için okur).

### 6.1 `StoreSource(db_path)` — canlı

`MarketStore(read_only=True)` üzerinden. `bars()`: `query_bars` → DataFrame (float64). Delik varsa (`contiguous_tail < n`) DataFrame döner ama `df.attrs["gaps"] = [open_ms,...]` ile işaretlenir; karar (giriş yok) `strategy_runner`'a aittir (05). `rules(pair)`: `rules` tablosu → `SymbolRules`; yoksa `DataError`. `minute_steps`: `query_range("last",…,"1m")` ve `("mark",…)` birleşimi; gün gün parçalar. Her çağrı yeni okuma işlemi (WAL tutarlı anlık görüntü).

### 6.2 `HistoricalSource(history_dir, *, granularity="1m", synthetic_rules=False)` — backtest ve testler

- **Dosyalar** (freqtrade adlandırması; `types.pair_stem`): `{stem}-{tf}-futures.feather` (last; `tf ∈ {1m,15m,1h,4h}`), `{stem}-1h-mark.feather` (mark, 1 saatlik; yalnız funding'e işaret için), `{stem}-1m-mark.feather` (1 dk mark; native kip), `{stem}-1h-funding_rate.feather` (`date`, `funding_rate`, 8 saatte bir). Sütunlar: `date, open, high, low, close, volume` (mevcut dosyalarda doğrulandı: `BTC_USDT_USDT-1h-futures.feather` 17880 satır, `2024-11-01T00:00Z … 2026-11-15T23:00Z`; mark aynı biçim, `volume=0`; funding 2190 satır, son `2026-10-31T16:00Z`).
- Okuma yalnızca `pyarrow` ile (`pyarrow.feather.read_table`, sütun alt kümesi); dosya adlandırması artık **bizim sözleşmemizdir** (§4.3 sonrası `var/history/`).
- **Bellek:** 1m dosyaları büyüktür (≈1,05 M satır/çift/yıl-2). `fetch_binance_vision.py` 1m dosyalarını `compression='uncompressed'` yazar (06 sahibi); `HistoricalSource` bunları `memory_map=True` ile okur ve `searchsorted` ile dilimler; sıkıştırılmış dosya bulursa tam okur ve `WARNING` verir. `minute_steps` gün gün (1440 satır × çift) tembel üretir.
- **Kaba kip** (`granularity="15m"`): `minute_steps` 15 dk **last** barlarını adım barı olarak üretir (`step_s=900`, `mark_* = None`); `step_seconds()==900`. 1m verisi olmayan çalışmada otomatik değil, **config ile açıkça** (`cost.granularity`); 1m isteyip dosya yoksa `DataError` (sessiz düşüş yok).
- **Funding:** `funding(pair,a,b)` dosyadan; `FundingPoint.mark` = o `ts` anındaki **1m mark açılışı** (1m mark yoksa 1h mark açılışı: freqtrade ile aynı, çünkü 1h mark barının açılışı saatin ilk dakikasının açılışıdır). Dosya aralığı dışındaki `ts` (ör. içinde bulunulan ayın eksik funding'i) → boş liste; kullanım yerinde `funding_missing` sayılır (03).
- **Kurallar:** `synthetic_rules=False`: `history_dir/rules.json` (anlık görüntü; `{pair: spec_json}` — `MarketStore.rules` ile aynı 8 alanlı biçim) okunur; yoksa `DataError`. `synthetic_rules=True` (yalnız `freqtrade_compat` çapraz doğrulama): `scripts/freqtrade_offline.py::synthetic_markets` ile **aynı kuralla** üretilir — `tick`/`step` son 2000 1h barın fiyat/hacim ondalıklarından en büyük ondalık sayısı (`10**-min(dec,8)`), `min_notional=5.0`, `min_qty=step`, `max_qty=1e12` — fakat `freqtrade_offline.py` §4.3'te silineceğinden **bu türetme `sources.py` içinde yeniden yazılır** (bizim kodumuz; freqtrade import edilmez). Sonuç gerçek borsa kurallarıyla birebir değildir; raporda "sentetik kurallar" etiketi zorunludur.
- `bars(pair, tf, until, n)`: tf dosyasından, `date + tf ≤ until`; önbellek (çift,tf) başına bir DataFrame; `until` küçük olanda dilim `view` (kopya değil). `contiguous_tail` beklenen aralıkla karşılaştırır.
- `last_closed_minute` → `data_range(pair,"1m")` son açılış (kaba kipte 15m).
- `open_at(pair: str, ts: datetime) -> float`: yalnız `HistoricalSource`'ta; adım barının (kaba kipte 15 dk) `last` **açılışı** (`ts` bar açılışına hizalı olmalı, aksi `DataError`). Yalnız uyum kipi giriş referansı için 06'nın `GuardedView` izniyle kullanılır (`MarketView` protokolünün parçası **değildir**).
- Hiçbir yöntem dosyanın bittiği yerden sonrası için veri uydurmaz.

## 7. Değişmezler

1. `StoreSource.bars(until=U)`: dönen son barın `open_ts + tf ≤ U` ve **kapanmış** olması; `U` bar kapanışından önceyse o bar dönmez.
2. Aynı `(kind,pair,tf,open_ms)` için tek değer: `put_bars` ikinci kez çağrılırsa mevcut satır değişmez.
3. `HistoricalSource` ve `StoreSource` aynı veriden aynı DataFrame döndürür (`pandas.testing.assert_frame_equal`): ortak test, store'a feather içeriği yazılarak yapılır.
4. Feed hiçbir koşulda bar silmez (yalnız `prune` 1m, 14 gün); `gaps` bilgi içindir.
5. Feed süreci `import pandas` yapmaz (alt süreçte denetlenir).

## 8. Uç durumlar

| Durum | Davranış |
|---|---|
| REST, açık (kapanmamış) barı döndürür | Atılır; yalnız `closeTime < now_server` |
| Aynı bar iki kez gelir | İkincisi `duplicates_equal`; farklıysa `conflict`, eski kalır |
| Borsa bir dakikayı hiç vermez | `gaps(missing)`; `minute_steps` o dakikayı atlar; motor bu çift için o adımı işlemez (03: stop denetimi o dakikada yapılamaz → `minute_gap` sayacı) |
| Sunucu saati yerelden > 60 sn farklı | Uyarı; süzgeç sunucu saatine göre |
| `rules` hiç çekilemedi | `StoreSource.rules` → `DataError`; motor o çift için giriş yapmaz (05); açık pozisyon yönetimi etkilenmez |
| Funding `mark` NULL | `put_funding` ile yazılır; 03 NULL mark'ta son 1m mark açılışını kullanır, bulamazsa `funding_missing` sayar |
| Çift hiç veri yok (yeni liste) | `backfill` o çifti `WARNING` ile atlar; motor `no_history` (05) |

## 9. Elle doğrulanabilir örnekler

1. `now_server = 2026-12-01T09:00:02Z`: 08:59 açılışlı 1m barı 09:00:00'da kapanmıştır (`closeTime = 08:59:59.999`), ama `close_ts + grace_s = 09:00:03 > 09:00:02` olduğundan dakikalık tur bu barı **henüz denemez**; bir sonraki `run_once` (`now_server ≥ 09:00:03`) isteği atar. Yanıtın son satırı `09:00` açılışlı (`closeTime 09:00:59.999 ≥ now_server`) açık bardır ve atılır; `08:59` satırı yazılır.
2. 1h bar `08:00` aralığı 60 adet 1m barla tam: `o = 08:00 1m açılışı`, `c = 08:59 1m kapanışı`, `h = max(h_i)`, `l = min(l_i)`, `v = Σ v_i`; REST barı `h` değeri `100.05` iken toplam `100.04` ise `agg_mismatch` işaretlenir, store'a REST barı (`100.05`) yazılır.
3. `bars("BTC/USDT","4h", until=2026-12-01T11:59:59Z)`: son bar `2026-12-01T04:00Z` açılışlı olur (08:00 barı 12:00'de kapanır → dönmez). `until=12:00:00Z` → son bar `08:00Z`.
4. `HistoricalSource.funding("BTC/USDT", 2026-10-31T08:00Z, 2026-10-31T16:00Z)` → yalnız `16:00Z` noktası (aralık `(start, end]`).

## 10. Kabul senaryoları (test ajanı için)

`put_bars` idempotent/çakışma/geçersiz bar ret; `query_bars(until)` gelecek bar vermez (sınır değerler: kapanıştan 1 ms önce/tam kapanış); `rows_to_bars` açık bar atar, `abnormal_close`; `Feed.backfill` kesintiden sonra (REST sahte yanıtla) boşluğu doldurur, borsa vermediği dakikayı `gaps`'e yazar; `run_once` bir çiftin hatasında diğerlerini yazar; ban/saat farkı/disk hatası yolları; bar builder `agg_mismatch`; iki yazar kilidi; `StoreSource` ≡ `HistoricalSource` ortak içerik testi; `HistoricalSource` kaba kip `step_s=900`; `synthetic_rules` mevcut 1h feather üzerinde `tick/step` değerlerinin `freqtrade_offline._step` ile **aynı** çıkması (referans değerleri sabit liste olarak testte); feed süreci `pandas` yüklemez; mevcut gerçek dosya duman testi (`BTC_USDT_USDT-1h-futures.feather` satır sayısı ve son tarih, `pyarrow` kuruluysa).

## 11. Belirsizlikler ve çözümleri

- **1m mark/last Vision verisi mevcut değil** (şu an yalnız 15m/1h/4h last + 1h mark var). Çözüm: `HistoricalSource` native kipte 1m dosyası bulamazsa `DataError`; `06-backtester.md` önce `fetch_binance_vision.py` genişletmesini ister. Kaba kip bu yokluk için vardır ve raporda işaretlenir.
- **`pyarrow` ortamda kurulu değil** (bu çalışma ortamında `import pyarrow` başarısız): bağımlılık `pyproject.toml`'a 08 tarafından eklenir; testler `pytest.importorskip("pyarrow")` kullanır.
- **Aynı barın REST tarafından sonradan düzeltilmesi** (Binance nadiren): eski değer kalır, `conflict` sayılır; paper ↔ backtest eşitliği için bilinçli seçim. Haftalık kontrolde `conflicts > 0` açık madde olur.
- **Feed gecikmesi kararı:** motor, karar anında tf barının store'da olmasını bekler (`bar_wait_s`, 05); feed `grace_s=3` ile tipik olarak ~5 sn içinde yazar.
