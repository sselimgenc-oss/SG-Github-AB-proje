# Kendi işlem motorumuz — tasarım (mentor, 16 Kasım 2026)

Kullanıcı kararı: freqtrade yerine kendi motorumuz ("1l3a'yı uyarla ya da sıfırdan yaz, ama şimdi başla").
Girdi: `research_notes/kullanici-projeleri/1l3a_motor_derin_inceleme.md`, `faz-plani.md`, `tasarim-kararlari.md`,
`trader/src/trader_core/*`, `trader/user_data/strategies/TraderV1.py`.
Bu belge karar + mimari + takvimdir; modül bazlı ayrıntılı şartnameler `trader/docs/motor/` (00-index … 08) altındadır. Ayrıntıda çelişki olursa `00-index.md` §5'te "Karar verildi" işaretli satırlar geçerlidir.
Hiçbir kod çalıştırılmadı; Binance uç adları ve davranışları "doğrulanacak" işaretlidir.

---

## 1. Karar

### 1.1 Melez: çekirdek sıfırdan, borsa/yürütme katmanı 1l3a'dan uyarlanır

| Seçenek | Karar | Neden |
|---|---|---|
| 1l3a `_Motor`'u uyarla | Hayır | Boyutlandırma `_istenen_qty` + `SERT_LIMITLER`/`CANLI_LIMITLER` ikilisine kablolu; iki ayrı risk seti; çıkışlar (`CikisAyarlari`) bizim `signals.py` ile çift tanım; kullanmayacağımız portföy/kısmi/çok hesap kodu ~%70. |
| Tamamen sıfırdan | Hayır | Emir POST'unda tekrar yok + kimlikle sorgu, stop-önce/eski-iptal-sonra, stop kurulamazsa kapat, mutabakat, yuvarlama kuralları 1l3a'da 66 testle yazılmış; yeniden keşfetmek canlı para riskidir. |
| **Melez** | **Evet** | Çekirdek küçük kalır (tek bar döngüsü + `Broker` arayüzü), tek risk kaynağı `trader_core.risk.LOCKED_CFG`, çıkışların tek kaynağı `trader_core.signals`. 1l3a'dan yalnız sertleştirilmiş yürütme ve test senaryoları gelir. |

### 1.0 Bağlayıcı kullanıcı ilkesi: dış çerçeveye yaslanmak yok

Başka depolardan gelen her parça iki yoldan biriyle girer, üçüncü yol yoktur:
- **(a) Kopyala:** olduğu gibi uyuyorsa dosya **bizim ağacımıza kopyalanır** (`trader/src/trader_engine/` altına), bizim kodumuz olarak çalışır, bizim testlerimizle korunur. Kaynak depo çalışma zamanında import edilmez, mount edilmez, bağımlılık olarak kurulmaz; kopyadan sonra 1l3a deposu silinse de sistem çalışır.
- **(b) Yalnız fikir:** uymuyorsa yalnız fikir/kural alınır, kod bizde sıfırdan yazılır.

Yasak: freqtrade'de yaptığımız gibi bir dış çerçevenin **üstüne** inşa etmek (onun döngüsüne, geri çağrılarına, veri modeline, veritabanına bağlanmak). Buna göre:
- **freqtrade çalışma zamanından ve backtest'ten tamamen çıkar** (kendi backtester'ımız, §4). Kaldırma adımı §4.3'te tarihli ve kapılıdır.
- İzinli bağımlılıklar yalnız düz yardımcı kütüphaneler: `pandas`, `numpy`, `pyarrow` (feather okuma), `requests`, `websockets` (Faz B), standart kütüphane (`sqlite3`, `hmac`, `decimal`).
- Yasak bağımlılıklar: işlem çerçeveleri ve borsa SDK'ları (`freqtrade`, `ccxt`, `python-binance`, `backtrader`, `vectorbt` vb.). `trader_engine` ve `trader_core` içinde bunların import edilmediği bir testle kilitlenir (`tests/engine/test_no_framework_imports.py`: kaynak ağacı taranır, `pyproject.toml` bağımlılık listesi denetlenir).
- Borsa G/Ç: 1l3a'nın ham REST (ve sonra WS) yürütme katmanı ağacımıza kopyalanır (§1.2, §1.3).

Değişmez ilkeler:
1. `trader_core` saf kalır; motor ayrı paket (`trader_engine`), `trader_core`'u çağırır, tersi yok.
2. Paper, backtest, canlı **aynı** `Engine` + aynı `check_entry` + aynı çıkış fonksiyonları. Fark yalnız `Broker` ve veri kaynağıdır.
3. Borsa doğruluk kaynağıdır (canlıda); motor durumu ondan türetilebilir olmalı.
4. Her belirsizlikte fail-closed: giriş yok, açık pozisyon stop ile korunur, çıkışlar hiçbir kapıya bağlı değildir.

### 1.2 1l3a'dan alınacaklar / bırakılacaklar

Kök: `/home/user/sselimgenc-oss/1l3a-proje/`. Her satır §1.0'daki iki yoldan biridir: **(a) kopyala** = dosya ağacımıza alınır, tanımlayıcılar İngilizceye çevrilir, yalnız belirtilen ekler/kesintiler yapılır, mantık değişmez ve 1l3a test senaryoları bizde yeniden koşar; **(b) fikir** = kod alınmaz. Hiçbiri import/mount edilmez; kopyalanan dosyanın başlığına kaynak yolu ve kopyalama tarihi yazılır (kullanıcının kendi kodu, lisans engeli yok).

| 1l3a dosyası | Ne yapılır | Bizdeki hedef |
|---|---|---|
| `motor/canli/borsa/binance_futures.py` | **(a)** Kopyala: imza, tekrar politikası (`tekrar_guvenli=False`, `belirsiz` → sorgula), -1021, 429/418, ağırlık bekleme. Ekle: `X-MBX-ORDER-COUNT-10S/1M`, `PERCENT_PRICE`, mark kline/premiumIndex uçları | `exchange/binance_rest.py` |
| `motor/canli/borsa/kurallar.py` | **(a)** Kopyala; uydurma varsayılan `min_notional=5` **kaldırılır** (filtre eksik → hata, o çifte giriş yok) (`kural_cikar`, `miktar_yuvarla`, `stop_yuvarla`, `hedef_yuvarla`); `boyutlandir` atılır | `exchange/rules.py` |
| `motor/canli/borsa/canli_yurutucu.py` | **(a)** Kopyala, sonra kes: `_giris_gonder`, `_koru`/`_stop_kur`, `_stop_yukselt`, `_mutabakat`, `_dolum_sonrasi_risk`, `client_id`. `Niyet/MotorGorunumu` ve `_kayit_*` atılır | `brokers/binance_futures.py`, `reconcile.py`, `order_manager.py` |
| `motor/canli/borsa/canli_limitler.py` | **(b)** Yalnız kill durum makinesi fikri; **sayıların hiçbiri alınmaz** | `killswitch.py` |
| `motor/canli/borsa/canli_ayar.py` | **(b)** Fikir: mod, `CANLI_ONAY` çift onay, anahtarlar yalnız env | `config.py` |
| `motor/canli/borsa/kuru.py` | **(a)** Kopyala; reddetme, gecikme, kısmi dolum, belirsiz yanıt ekle | `tests/engine/fake_exchange.py` (yalnız test) |
| `motor/canli/paper_veri.py` | **(a)** Kopyala: klines/funding istemcisi | `marketdata/rest_public.py` |
| `motor/canli/paper_canli.py` | **(b)** Yalnız fikir (kopya listesinde olmayan modüllere bağlı; kopyalanamaz): grace, boşluk doldurma, artımlı funding. `feed.py` sıfırdan. WS `ws_dongu` kalıbı Faz B'de yine fikir olarak | `marketdata/feed.py` |
| `motor/canli/durum.py::atomik_yaz_json`, `kalp_atisi.py` | **(a)** Kopyala | `status.py` |
| `testler/test_canli_borsa.py`, `test_canli_limitler.py`, `test_lookahead_tum_stratejiler.py` | **(b)** Senaryo listesi kabul testi şartnamesi olur (test kodu bağımsız ajan tarafından bizim arayüze yazılır) | `tests/engine/` |
| Stop/hedef aynı mumda → STOP, gap dolumu, funding imleci (`backtest/motor.py`, `portfoy/motor.py::_mum_ici`, `_funding_ode`) | **(b)** Yalnız kural | `brokers/paper.py` |

Bırakılanlar: `motor/portfoy/motor.py`, `motor/backtest/motor.py`, `motor/canli/paper*.py` (motor/çok hesap), `motor/strateji/*`, `motor/risk/limitler.py`, `canli_kayit.py` (yerine `ledger.py`), `motor_kopru.py`, `calistir.py`, `pano.py`, `telegram.py`, tüm `arastirma/`.

### 1.3 Borsa G/Ç kütüphanesi: ham `requests` (+ Faz B'de `websockets`), ccxt / python-binance yok

§1.0 gereği borsa SDK'sı kullanılmaz; 1l3a'nın ham istemcisi ağacımıza kopyalanır. Teknik gerekçeler de aynı yönü gösteriyor:

- Emir yolunda ihtiyacımız 12 kadar uç; 1l3a istemcisi 316 satır ve testli. ccxt bu yüzeyin üstüne sürüm kayması ve gizli tekrar/normalizasyon davranışı ekler; en riskli noktamız (koşullu emirlerin algo uçlarına taşınması) tam da soyutlamanın en geç ve en opak güncellendiği yerdir. Ham istekte gönderdiğimiz parametre ile kaydettiğimiz fixture birebir aynıdır.
- "Emir POST'u asla otomatik tekrarlanmaz" kuralını kütüphaneye emanet edemeyiz; kendi istemcimizde tek satırla garanti edilir ve test edilir.
- Bellek: 1 vCPU / 2 GB'de iki motor süreci; ccxt yükü gereksiz.
- Bedeli: Binance değişikliklerini kendimiz izleriz. Karşılığı: kaydedilmiş gerçek yanıt fixture'ları + haftalık testnet duman testi (§5).
- Emir yolu **senkron** `requests.Session` (1l3a gibi). Faz A'da asyncio ve WebSocket yok: strateji 15m/1h bar kapanışlı, REST yoklama yeterli ve en basit. WS yalnız "bar kapandı" tetiği olarak Faz B'de eklenebilir; doğruluk yolu her zaman REST.
- Kullanıcı veri akışı (listenKey) v1'de **yok**: pozisyon açıkken 15 sn'lik REST mutabakat yoklaması. Gerekçe: düşük frekans, borsada duran stop; listenKey keepalive/yeniden bağlanma ek hata yüzeyi.

---

## 2. Mimari

### 2.1 Bileşenler ve veri akışı

```
Binance public REST ──> feed (tek süreç) ──> market.sqlite (kapalı barlar: last 1m/15m/1h/4h, mark 1m, funding)
                                                   │ (salt okunur)
                              ┌────────────────────┴────────────────────┐
                        engine[learner]                            engine[twin]
   MarketView → StrategyRunner → EntryGate(ledger, params, stale, veto, risk) → OrderManager → Broker
                      │                                                             │
                 PositionManager (stop/trail/target/time/regime çıkışları) <── Fill/BrokerEvent
                      │
        ledger.sqlite (trader_core.ledger)   state.sqlite (motor durumu)   status.json (kalp atışı)
```

Backtest: aynı `Engine`, veri kaynağı `HistoricalSource` (feather), saat `SimClock`, broker `PaperBroker`.

### 2.2 Modüller (`trader/src/trader_engine/`)

| Modül | Sorumluluk | Not |
|---|---|---|
| `types.py` | `Bar`, `Intent`, `OrderRequest`, `Fill`, `Position`, `BrokerPosition`, `SymbolRules` (frozen dataclass) | Motor içi float; borsa sınırında `Decimal` (`rules.py`) |
| `clock.py` | `Clock` protokolü: `SystemClock`, `SimClock` | Kodda `datetime.now()` yasak (test ile kilitlenir) |
| `config.py` | `EngineConfig`: `mode` (`paper`/`testnet`/`live`), `bot`, çiftler, yollar, maliyet modeli; canlı için `LIVE_CONFIRM` env + config çift onayı | Risk sayıları burada **yok**; yalnız `LOCKED_CFG` |
| `marketdata/rest_public.py` | klines, markPriceKlines, fundingRate, premiumIndex, exchangeInfo, serverTime | Anahtar gerektirmez |
| `marketdata/store.py` | `market.sqlite` (WAL): `bars(kind, pair, tf, open_ts, o,h,l,c,v)` PK ile upsert; `funding(pair, ts, rate, mark)`; `rules(pair, json, fetched_at)` | Yalnız **kapanmış** barlar yazılır |
| `marketdata/feed.py` | Süreç: dakikada bir (kapanış + 3 sn) her çift için 1m last + 1m mark; tf kapanışında 15m/1h/4h; saatte bir exchangeInfo ve funding; açılışta boşluk doldurma | Bar builder görevi: 1m → tf toplamı REST barıyla karşılaştırılır, fark uyarıdır; boşluk varsa bar "eksik" işaretlenir |
| `marketdata/sources.py` | `StoreSource` (canlı), `HistoricalSource` (feather; backtest) — aynı `MarketView` arayüzü: `bars(pair, tf, until)`, `minute_bars(pair, a, b)`, `funding(pair, a, b)` | `until` zorunlu: gelecek bar verilemez |
| `strategy_runner.py` | tf bar kapanışında: `regime.classify_series(4h)` → `align_to_base` → `signals.compute_signals` → son satır. Parametre: `ledger.get_active_params()` (her turda sürüm kontrolü) | `TraderV1.populate_indicators` karşılığı; hata → o çift için giriş yok |
| `gates.py` | Giriş kapısı, sırayla: params_ok → `ledger.entries_allowed()` → stale_data → kill → mum başına tek karar → `veto.read_veto_file`+`lookup` (yok/eski/blocked → giriş yok) → `risk.check_entry` | Her ret `record_decision` ile yazılır (`skip_reason` ledger sözlüğünden) |
| `order_manager.py` | `Intent` → `OrderRequest`; idempotent client id; emir günlüğü (state.sqlite `orders`: POST'tan **önce** `pending` yazılır) ; belirsiz yanıtta kimlikle sorgu, yalnız "emir yok" ise tek yeniden gönderim | §2.4 |
| `brokers/base.py` | `Broker` protokolü (§2.3) | |
| `brokers/paper.py` | `PaperBroker`: dolum modeli (§2.5), sanal cüzdan, funding, likidasyon | Paper ve backtest ortak |
| `brokers/binance_futures.py` | `BinanceFuturesBroker`: hazırlık (izole, one-way, kaldıraç), MARKET giriş, algo STOP_MARKET/TAKE_PROFIT_MARKET reduceOnly `workingType=MARK_PRICE`, stop değiştir, kapat, `userTrades`/`income` | Faz B |
| `exchange/binance_rest.py`, `exchange/rules.py` | İmzalı istemci, hız sınırı sayaçları (ağırlık + emir sayısı), filtre/yuvarlama | 1l3a uyarlaması |
| `position_manager.py` | Açık pozisyon defteri; her tf barında: `regime_flip_exit`, `time_stop_due`, `target_reached` (R1), `trail_stop_path` (T1) → stop yalnız sıkılaşır; MFE/MAE takibi (1m); `TradeExit` üretimi | `custom_stoploss` + `custom_exit` + bekleyen `_excursion` değişikliğinin karşılığı |
| `funding.py` | Funding zamanlarında `qty × mark × rate × yön`; pozisyon başına birikir → `TradeExit.funding_paid` (pozitif = ödenen) | Paper/backtest; canlıda `income` ucundan |
| `reconcile.py` | Borsa pozisyon/emir ↔ state.sqlite ↔ ledger; kurallar §2.6 | Paper'da tutarlılık denetimi olarak çalışır |
| `state.py` | `state.sqlite`: `positions`, `orders`, `cursors` (çift başına son işlenen 1m ve son karar barı), `wallet` (paper), `kv` | Tek yazar: kendi motor süreci |
| `killswitch.py` | `shared/KILL` dosyası veya CLI: girişleri kapat, tüm pozisyonları reduceOnly piyasa ile kapat, sonra emirleri iptal et | Telegram "hepsini kapat" bunu tetikler |
| `status.py` | `status.json` atomik: loop zamanı, son bar zamanı, açık pozisyon, kapı durumu, hata sayaçları | `health_run.py` toplayıcısı buna uyarlanır (ayrı iş; `health.evaluate` değişmez) |
| `engine.py` | Ana döngü (§2.7) | |
| `backtest.py` | `Engine` + `HistoricalSource` + `SimClock` + `PaperBroker`; çıktı: ledger.sqlite + trades.csv | §4 |
| `cli.py` | `python -m trader_engine feed | run --bot learner | backtest | reconcile | kill | smoke` | |

### 2.3 Broker arayüzü

```python
class Broker(Protocol):
    def rules(self, pair) -> SymbolRules
    def account(self) -> BrokerAccount                 # wallet, equity (mark ile), available
    def positions(self) -> list[BrokerPosition]
    def open_orders(self, pair=None) -> list[BrokerOrder]
    def prepare(self, pair, leverage) -> None           # isolated, one-way, leverage (idempotent)
    def market_order(self, req: OrderRequest) -> OrderResult       # entry veya reduceOnly exit
    def place_stop(self, req: OrderRequest) -> OrderResult         # STOP_MARKET reduceOnly, MARK_PRICE
    def place_target(self, req: OrderRequest) -> OrderResult       # TAKE_PROFIT_MARKET reduceOnly
    def cancel(self, pair, client_id) -> None
    def query(self, pair, client_id) -> BrokerOrder | None          # belirsizlik çözümü
    def poll(self, now) -> list[BrokerEvent]             # dolumlar, funding, likidasyon
```

`OrderResult.status ∈ {filled, accepted, rejected, unknown}`. `unknown` yalnız ağ belirsizliğinde; motor asla körlemesine tekrar göndermez.

### 2.4 Idempotent client id

`tr{L|T}{e|s|t|x}-<sha1(bot|pair|side|signal_bar_close_ts|role|seq)[:24]>` (≤ 36 karakter). `seq`: giriş ve çıkış için **sabit 0** (yeniden gönderim aynı kimlikle; sayaçlı yeni kimlik, ilk POST geç ulaşırsa çift emre yol açardı); stop için sürüm sayacı (her trail güncellemesi ve yeniden kurulum yeni kimlik). Yeniden gönderim yalnız iki sorgunun da "emir yok" demesinden sonra, tek kez. Yetkili ayrıntı: `trader/docs/motor/04-order-position.md` §1/§4. Aynı sinyal barı için ikinci giriş matematiksel olarak aynı kimliği üretir → çift giriş olamaz. Kimlik state.sqlite'a POST'tan önce yazılır; yeniden başlatmada `pending` satırlar `query` ile çözülür.

### 2.5 PaperBroker dolum modeli (paper = backtest)

Girdi her zaman kapanmış 1m barlardır (last + mark); backtest'te 1m veri yoksa tf barı ile `granularity=tf` (kaba mod, raporda işaretli).

1. **Piyasa girişi/çıkışı:** emir zamanında ya da sonrasında başlayan ilk 1m **last** barının açılışı ± `slip_bps` (aleyhte), tick'e yuvarlı. Varsayılan 2 bps giriş/çıkış, 5 bps stop (1l3a değerleri; çift bazında ayarlanabilir).
2. **Stop / hedef tetik:** **mark** barının high/low'u ile (canlıdaki `workingType=MARK_PRICE` ile aynı semantik). Dolum fiyatı: mark açılışı zaten stopun ötesindeyse (gap) o dakikanın last açılışı, değilse stop fiyatı; ikisine de stop kayması eklenir. Aynı barda stop ve hedef → STOP. Giriş barında da stop denetlenir.
3. **Likidasyon:** `risk.liquidation_price`; mark, stoptan önce likidasyona değerse çıkış `liquidation`, kayıp = teminat. (Risk kilidi bunu imkânsız kılmalı; görülürse hata sayılır.)
4. **Komisyon:** taker 0,05 % (config; backtest matrisinde ×2).
5. **Funding:** §2.2 `funding.py`.
6. **Kısmi dolum yok** (market, küçük boyut). Canlı yolda `executedQty` okunur.
7. Sanal cüzdan: bot başına 1000 USDT; `equity = wallet + mark ile gerçekleşmemiş`; `day_start_equity` UTC gün başında sabitlenir (`AccountState`).

### 2.6 Stop yönetimi ve mutabakat (canlı; kurallar 1l3a'dan)

- Giriş dolumu → hemen `place_stop` (dolan miktar, `stop_yuvarla` sıkı yön). Kurulamazsa 1 yeniden deneme, sonra pozisyon reduceOnly piyasa ile kapatılır.
- Dolum sonrası gerçek fiyatla risk yeniden hesaplanır; `max_trade_risk` aşıldıysa reduceOnly küçült/kapat.
- Trail güncelleme: **önce yeni stop, sonra eski iptal**; gevşetme yok; fiyat yeni stopu geçmişse piyasada kapat. Bar kapanışında, en fazla tf başına bir kez.
- `closePosition=true` kullanılmaz (aynı anda iki stop gerekir); miktar bazlı reduceOnly. Bu varsayım testnet doğrulama listesinde (§3.3).
- Hedef (R1): **bar kapanışı kuralı** (`strateji-spec` §5.4 ile aynı: kapanmış barın high/low'u hedefe değdiyse sonraki adımda piyasa çıkışı; `target_mode="bar_close"`). Borsada `TAKE_PROFIT_MARKET` Faz A'da ve canlı v1'de **kurulmaz** (`place_target` yalnız arayüzde); strateji davranışını değiştirdiği için ancak strateji-spec revizyonu + yeniden backtest ile gelir. Zaman/rejim/hedef çıkışı motor tarafında (servis ölürse stop korur).
- Mutabakat (açılışta + pozisyon açıkken 15 sn, değilken 60 sn):

| Durum | Eylem |
|---|---|
| Borsada pozisyon var, stop yok | Stop kur; olmazsa kapat |
| Borsada pozisyon var, motor kaydı yok | İşlem yapma; girişleri kapat; kritik uyarı |
| Motor kaydı var, borsada pozisyon yok | `userTrades`/`income` ile çıkışı türet → `record_trade_exit` (stop/hedef/likidasyon); artık emirleri iptal |
| Miktar uyuşmuyor | Stop miktarını borsa pozisyonuna eşitle; uyarı |
| Yetim reduceOnly emir | İptal |
| `orders.pending` satırı | `query` ile çöz |
| Ledger'da açık, motor kaydı yok (`find_unledgered_trades` karşılığı ters yön dahil) | Girişleri kapat; uyarı |

Paper'da aynı tablo `PaperBroker` durumuna karşı çalışır; ayrıca yeniden başlatmada işlenmemiş 1m barlar `cursors`'tan itibaren sırayla **yeniden oynatılır** (kaçan stop/funding deterministik biçimde yakalanır).

### 2.7 Ana döngü (tek iş parçacığı, senkron)

Her 5 sn uyan; iş varsa yap:
1. `KILL` denetimi.
2. Yeni 1m barlar (zaman sırasıyla, çift çift): `broker.poll` → dolum/funding/likidasyon olayları → `position_manager` → ledger çıkış kaydı; MFE/MAE güncelle.
3. Tetik tf barı kapandıysa (ve 4h verisi güncelse): aktif parametreyi yenile → **önce çıkışlar** (rejim, zaman, hedef, trail kesişimi) → **stop güncelle** → **sonra girişler** (kapı zinciri → `Intent` → emir → dolum → `record_decision(entered)` + `record_trade_entry` → stop).
4. Mutabakat (zamanı geldiyse).
5. `status.json`.

Bayatlık: karar anı bar kapanışından > 1 tf geçtiyse giriş yapılmaz (`stale_data`); çıkışlar yine çalışır.

### 2.8 TraderV1 → motor karşılıkları (hiçbir davranış kaybolmamalı)

| TraderV1 (freqtrade) | Motor |
|---|---|
| `populate_indicators` | `strategy_runner` |
| `_gate`, `_stale`, `_bar_final`/`_decided` (mum başına tek karar) | `gates.py`; tek karar anahtarı state.sqlite'ta kalıcı |
| `veto_check` (şu an stub: `not_evaluated`) | Gerçek `veto.lookup`; fail-closed |
| `leverage` (= `LOCKED_CFG.min_leverage`) | Aynı kural |
| `custom_stake_amount` + `confirm_trade_entry` (iki kez risk) | Tek `check_entry` + dolum sonrası doğrulama |
| `order_filled` → `record_trade_entry/exit`; `trade.id` | Motor `trade_id` üretir (state.sqlite sayaç) |
| `set_custom_data` (initial_stop, target, trail_atr, entry_bar_open…) | `positions` tablosu |
| `custom_stoploss` (`trail_stop_path`) + `stoploss_on_exchange` | `position_manager` + `Broker.place_stop` |
| `custom_exit` (target, time_stop, regime_flip, trail_stop) | `position_manager` |
| `_ledger_exit_reason` | Çıkışı motor başlattığı için neden doğrudan bilinir; borsa stopunda trail devrede mi bilgisi `positions.current_stop != initial_stop` |
| `bot_loop_start` parametre yenileme + unledgered denetimi | Döngü adım 3 + mutabakat |
| Bekleyen `_excursion` (mfe/mae) | Doğal olarak 1m'den (`excursion_tf="1m"`) |

Not: `Ledger.find_unledgered_trades(freqtrade_open_trade_ids)` parametre adı freqtrade'e özgü; davranış uygunsa yalnız ad düzeltilir (defter-spec revizyonu, ayrı iş).

### 2.9 Süreç modeli (1 vCPU / 2 GB, paylaşımlı droplet)

| Süreç | Bellek (tahmin) | Not |
|---|---|---|
| `trader-feed` | ~60 MB (pandas yok) | Tek hız sınırı bütçesi; L ve T **aynı barları** görür |
| `trader-engine@learner` | ~180 MB | pandas/numpy |
| `trader-engine@twin` | ~180 MB | 3 sn gecikmeli başlar; her zaman `PaperBroker` |
| veto / health / backup zamanlayıcıları | geçici | Mevcut |

- systemd birimleri (`Restart=always`, `MemoryMax=400M`), 1 GB swap. Docker'a gerek yok (freqtrade imajı kalkıyor); istenirse tek `python:3.13-slim` imajı.
- Feed ölürse: motorlar bayat veri görür → giriş yok; paper stopları feed dönünce yeniden oynatmayla işlenir; canlıda stop borsada.
- Canlıda tek hesap = tek net pozisyon → **yalnız learner canlıya geçer**, twin paper kalır.
- İstek yükü: 10 çift × 2 istek/dk + tf kapanışları ≈ 25 istek/dk, ağırlık sınırının çok altında.

### 2.10 Dosya düzeni (`trader/` altında)

```
src/trader_core/                 (değişmez)
src/trader_engine/
  __init__.py  types.py  clock.py  config.py  engine.py  strategy_runner.py  gates.py
  order_manager.py  position_manager.py  funding.py  reconcile.py  state.py
  killswitch.py  status.py  backtest.py  cli.py
  marketdata/  rest_public.py  store.py  feed.py  sources.py
  brokers/     base.py  paper.py  binance_futures.py
  exchange/    binance_rest.py  rules.py
tests/engine/  test_<modul>_spec.py (bağımsız)  test_<modul>_impl_smoke.py  fake_exchange.py  fixtures/binance/*.json
docs/motor-spec.md  docs/motor-dolum-modeli.md  docs/motor-canli-kontrol-listesi.md
config/engine.base.json  engine.learner.json  engine.twin.json
deploy/trader-feed.service  trader-engine@.service
research/bt_crosscheck.py        (freqtrade ↔ motor karşılaştırması)
scripts/smoke_testnet.py  scripts/smoke_live.py
var/<bot>/ledger.sqlite  state.sqlite  status.json ;  var/market.sqlite   (gitignore)
```

`trader_engine` kendi kendine yeter: 1l3a'dan gelen her şey bu ağacın içindedir (`exchange/`, `marketdata/rest_public.py`, `status.py`, `tests/engine/fake_exchange.py`); depo dışına yol, alt modül ya da mount yoktur. `pyproject.toml` bağımlılıkları: `pandas`, `numpy`, `pyarrow`, `requests` (+ Faz B `websockets`), test için `pytest`.

Freqtrade kalıntıları çapraz doğrulama geçene kadar **yalnız dondurulmuş referans** olarak durur (çalıştırılmaz, motor onlardan hiçbir şey import etmez), sonra §4.3'teki adımla **silinir**.

---

## 3. Fazlama ve takvim

Bugün 16 Kasım (Pzt). İnsan tahmini 25–32 gün; ajanlarla (şartname → gerçekleme + bağımsız test → mentor incelemesi, paketler paralel) sıkışır ama **inceleme ve gerçek saatli deneme sıkışmaz**.

### 3.1 Faz A — paper başlangıcı için asgari (hedef 30 Kasım)

Gerekenler: `types/clock/config`, `marketdata/*` (REST yoklama), `strategy_runner`, `gates` (veto + risk + ledger dahil), `order_manager` (kimlik + günlük), `PaperBroker` (mark tetik, funding, komisyon, kayma), `position_manager`, `state` + yeniden başlatmada yeniden oynatma, mutabakatın paper alt kümesi, `killswitch`, `status` + health toplayıcı uyarlaması, `backtest` + freqtrade çapraz doğrulaması, systemd dağıtımı.

Faz A'da **yok**: imzalı istemci, `BinanceFuturesBroker`, algo emirleri, emir hız sınırı, WS, listenKey, 1d zaman dilimi, exchangeInfo'nun emir yolunda kullanımı (paper yalnız step/tick/minNotional okur).

| Gün | İş (paralel ajan paketleri) |
|---|---|
| 16–17 Kas | `motor-spec.md` + `motor-dolum-modeli.md` (arayüzler, durum şeması, dolum kuralları, kabul testleri listesi). Mentor onayı olmadan kod yok. |
| 18–20 Kas | P1 `marketdata` + feed · P2 `PaperBroker` + `funding` · P3 `state` + `order_manager` (üçü paralel; her biri: gerçekleme ajanı + bağımsız test ajanı) |
| 20–23 Kas | P4 `strategy_runner` + `gates` + `position_manager` + `engine` · P5 `backtest` |
| 23–25 Kas | P6 çapraz doğrulama (§4) + lookahead kesme testi motor düzeyinde · P7 dağıtım, kill, status/health |
| 26–27 Kas | Mentor incelemesi, düzeltmeler; **freqtrade kaldırma (§4.3)**; droplette kurulum (sunucuda freqtrade imajı/konteyneri yok) |
| 28–29 Kas | 48 saat kesintisiz deneme: yeniden başlatma, feed kesintisi, kill, sunucu reboot |
| 30 Kas | Paper başlar (L + T) |

Dürüst değerlendirme: bu takvimde **tampon yok**. 30 Kasım'ı tutturma olasılığını ~%55–60 görüyorum; gerçekçi aralık **30 Kasım – 4 Aralık**. Kayma olursa en olası sebepler: çapraz doğrulamada açıklanamayan farklar, yeniden başlatma/yeniden oynatma hataları, health toplayıcısının uyarlanması.

Kayan / ertelenenler:
- Faz 2'nin motor dışı işleri (ders servisi, Telegram raporu) aynı inceleme kapasitesini kullanır. Öncelik: motor > veto bağlantısı > kill komutu > günlük rapor > ders. Ders servisi paper'ın ilk haftasına kayabilir (zaten gölge dönemde, otomatik uygulama yok — kayıp küçük).
- 1d zaman dilimi ve aylık coin güncellemesi: paper 1. haftadan 2. haftaya.
- Paper 4 Aralık'ta başlarsa: ya paper 3,5 haftaya iner (canlı 28 Aralık kalır) ya da 4 hafta korunur ve duman testi 2–3 Ocak, canlı ~5 Ocak olur. İkisi de "aralık sonu–ocak başı" içinde; **kullanıcı kararı**. Önerim: 4 haftayı koru.

### 3.2 Faz B — canlı öncesi zorunlular (30 Kasım – 27 Aralık, paper sürerken)

| Tarih | İş |
|---|---|
| 30 Kas – 6 Ara | `exchange/binance_rest.py`, `rules.py` (uyarlama + ağırlık ve emir sayısı sınırı, exchangeInfo saatlik yenileme + filtre hatasında anında yenileme) |
| 7 – 13 Ara | `BinanceFuturesBroker`, canlı `reconcile`, `fake_exchange` ile 1l3a senaryolarının tamamı (çökme noktaları: POST öncesi/sonrası, stop öncesi, trail ortası) |
| 7 – 13 Ara | **Testnet doğrulaması** (§3.3) — testnet anahtarı kullanıcıdan en geç 4 Aralık |
| 14 – 27 Ara | Üçüncü süreç: learner kararlarını testnet'te `BinanceFuturesBroker` ile gölge yürütme (paper ile yan yana; fark raporu günlük) |
| 21 – 27 Ara | Canlı kontrol listesi, alt hesap anahtarı (çekim kapalı, IP kısıtlı), `LIVE_CONFIRM` |
| 28 – 29 Ara | Gerçek hesap duman testi (§3.4) |

### 3.3 Testnet doğrulama listesi (her madde için gerçek yanıt `fixtures/` altına kaydedilir)

1. Koşullu emirlerin doğru ucu ve parametre adları (`/fapi/v1/algoOrder`, `clientAlgoId`, `triggerPrice`, açık algo emir sorgusu/iptali) — 1l3a'da varsayım.
2. `STOP_MARKET` reduceOnly + `workingType=MARK_PRICE` kabulü; tetiklenince oluşan emrin kimliği ve `userTrades` eşlemesi.
3. Aynı pozisyon için iki reduceOnly stop aynı anda durabiliyor mu (önce-yeni-sonra-eski sırası için şart). Durmuyorsa: iptal → hemen yeni, arada motor bekçiliği; tasarım değişikliği mentor onayına gelir.
4. Belirsiz yanıt: zaman aşımından sonra kimlikle sorgu; yinelenen kimlikte hata kodu.
5. `marginType=ISOLATED`, one-way, kaldıraç 3; açık pozisyon varken tekrar çağrı kodları (-4046/-4059).
6. MIN_NOTIONAL / LOT_SIZE / PERCENT_PRICE ret kodları; min altı emir atlanıyor.
7. Emir sayısı başlıkları ve 429 davranışı.
8. Funding ve komisyonun `income`/`userTrades`'ten ledger'a eşlenmesi (işaretler).
9. Testnet ile gerçek ortam farkları not edilir; emin olunamayan her şey §3.4'te gerçek hesapta tekrar edilir.

### 3.4 Gerçek hesap duman testi (28–29 Aralık, en küçük tutar)

`scripts/smoke_live.py`, adım adım ve her adımda insan onayı: 1 long + 1 short (ayrı çiftler, min notional) → izole/kaldıraç doğrula → stop borsada görünüyor ve mark tetikli → stop bir kez sıkılaştır (yeni-önce) → motoru öldür/yeniden başlat, mutabakat temiz → hedef kur/iptal → reduceOnly kapat → komisyon/funding ledger'da → kill komutu. Geçmezse canlı başlamaz.

---

## 4. Backtest'in freqtrade'den çıkışı ve doğrulama

### 4.1 Kendi backtester'ımız
`backtest.py` = canlıdaki `Engine` + `HistoricalSource` + `SimClock` + `PaperBroker`. Ayrı bir strateji ya da dolum kodu yoktur. Çıktı: çalışma başına taze `ledger.sqlite` (bugünkü düzenle aynı) + `trades.csv`; `research/run_bt.py`'nin metrik kısmı aynen kullanılır, freqtrade çağrısı yerine `python -m trader_engine backtest` gelir. Sinyaller vektörel bir kez hesaplanır; `--paranoid` örneklem modunda her bar kesilmiş veriyle yeniden hesaplanıp eşitlik denetlenir (lookahead kilidi).

Veri: mevcut feather'lar (15m/1h/4h last, 1h mark, funding) + Binance Vision'dan 1m last ve 1m mark (`scripts/fetch_binance_vision.py` genişletilir). Dönemler aynı: IS 20241101–20251101, WF 20251101–20260501. **HOLDOUT (20260501–20261101) çapraz doğrulamada ve ayarlamada kullanılmaz.**

**Yapısal HOLDOUT kilidi:** `src/trader_engine/holdout.py` (`HOLDOUT`, `check_holdout`) tek kaynaktır; `backtest.py` yeniden dışa aktarır ve `Engine.run_range` `mode=="backtest"` iken hiçbir bar okumadan önce `holdout_locked` fırlatır (kilidi aşan anahtar yoktur; paper/canlı etkilenmez). `tests/engine/test_no_holdout_in_tests.py` gerçek-veri testlerinde 2026-05..10 tarihlerini yasaklar.

### 4.2 Freqtrade sonuçlarıyla çapraz doğrulama
Referans: `trader/user_data/backtest_results/<id>/` (`ledger.sqlite`, `trades_enriched.csv`, `overlay.json`). Araç: `research/bt_crosscheck.py`.

Önce motor **uyum kipinde** koşar (`fill_model=legacy_compat`; ad bilerek nötr: §4.3 madde 7 grep'i istisnasız boş kalır): tf barı ayrıntısı, stop tetik = last fiyat, giriş = sonraki bar açılışı, kayma komisyona katılmış (`fee_eff`, `run_bt.py` ile aynı), funding freqtrade yöntemiyle.

| Düzey | Karşılaştırılan | Kabul |
|---|---|---|
| A — kararlar | `decision_events` (bar_close_ts, pair, side, setup, planned_entry/stop/target, skip_reason) | Risk durumundan bağımsız alanlarda %100 eşit |
| B — girişler | giriş barı, giriş fiyatı; boyut `risk_amount/equity` oranı olarak | ≥ %99; her fark tek tek açıklanmış |
| C — çıkışlar | çıkış barı, `exit_reason`, çıkış fiyatı | ≥ %97; farklar sınıflandırılmış (trail zamanlaması, aynı-bar sırası, zaman stopu sayımı) |
| D — toplamlar | toplam R, komisyon, funding, işlem sayısı | R farkı ≤ %2, açıklanmış |

Yöntem notları: ilk sapmadan sonra özsermaye farklılaşır ve sapma zincirlenir; bu yüzden karşılaştırma mutlak miktar yerine R ve zaman üzerinden, çalışma başına **ilk sapma** kök nedeniyle incelenir. En az 4 çalışma: `1h_IS_f1_s0`, `1h_WF_f1_s0`, `15m_IS_f1_s0`, `1h_IS_f2_s5`. Açıklanamayan fark = hata (bizde ya da freqtrade bağdaştırıcısında); hangisi olduğu yazılır.

Sonra **yerel kip** (mark tetik, 1m ayrıntı, ayrı kayma) aynı dönemlerde koşar ve "model farkı raporu" üretilir: mark-vs-last yüzünden değişen stop sayısı, R farkı. Bu rapor mark/last riskinin ölçümüdür. Bundan sonra tek backtester bizimkidir; freqtrade kodu §4.3 ile silinir, yalnız ürettiği sonuç dosyaları salt veri olarak saklanır.

### 4.3 Freqtrade'in silinmesi (kapı: §4.2 kabul tablosu geçti + mentor onayı; hedef 26–27 Kasım, paper başlamadan)

Çapraz doğrulama için freqtrade **yeniden çalıştırılmaz**; karşılaştırma zaten üretilmiş çıktılarla yapılır. Kapı geçince tek bir commit ile:

1. Sil: `trader/user_data/strategies/TraderV1.py`, `PlaceholderStrategy.py`, `trader/research/strategies/TraderV1Analysis.py`, `trader/research/ft_offline_15m.py`, `trader/scripts/freqtrade_offline.py`, `trader/config/base.json`, `learner.json`, `twin.json`, `backtest.json` (yerlerine `engine.*.json`), `trader/docs/traderv1-bekleyen-degisiklikler.md` (içeriği `position_manager` şartnamesine taşındı).
2. `trader/docker-compose.yml`: freqtrade servisleri kaldırılır; dosya ya silinir (systemd) ya da yalnız kendi imajımızı içerir. `tests/test_compose.py` buna göre yeniden yazılır/silinir.
3. `research/run_bt.py`, `queue.sh`, `jobs_*.txt`: freqtrade çağrısı `python -m trader_engine backtest` ile değiştirilir; `.venv-ft` kaldırılır.
4. `scripts/download_data.sh`, `smoke_binance.sh`: freqtrade komutları kendi `feed`/`fetch_binance_vision.py` karşılıklarıyla değiştirilir. Veri dosyaları kalır ama `user_data/data/binance/futures/` → `var/history/` altına taşınır; feather yalnız `pyarrow` ile okunur, dosya adlandırması artık bizim sözleşmemizdir.
5. `trader_core` içindeki freqtrade izleri: `Ledger.find_unledgered_trades(freqtrade_open_trade_ids)` parametre adı `open_trade_ids` olur; `health` içindeki freqtrade API yoklaması (`ApiProbe` kaynağı) `status.json` okuyucusuyla değiştirilir; `strateji-spec.md` Bölüm 4–6 (IStrategy bağdaştırıcı) "kaldırıldı, bkz. motor-spec.md" olarak işaretlenir. Bunlar şartname revizyonu + bağımsız test güncellemesiyle yapılır.
6. Saklanan tek şey: `user_data/backtest_results/` altındaki dondurulmuş sonuçlar → `research/reference/freqtrade-2026.10/` (salt veri, kod değil) ve çapraz doğrulama raporu.
7. Kabul: `grep -ri freqtrade trader/src trader/scripts trader/config trader/deploy` boş; `test_no_framework_imports.py` yeşil; tüm testler freqtrade kurulu olmayan temiz bir ortamda geçer; sunucuda freqtrade imajı yok.

Kapı 27 Kasım'a kadar geçmezse: paper yine **yalnız kendi motorumuzla** başlar (freqtrade çalışma zamanına hiçbir koşulda dönülmez); silme, açık farklar kapanana kadar bekler ve bu durum haftalık kontrolde açık madde olarak izlenir.

Paper ↔ backtest eşlemesi (paper'ın 1. haftası sonunda ve haftalık): paper döneminin verisi backtester'dan geçirilir; işlem listesi paper ledger'ı ile **birebir** aynı olmalı (aynı kod, aynı barlar). Fark = motor hatası.

---

## 5. Riskler ve mentor incelemesi

| # | Risk | Etki | Önlem |
|---|---|---|---|
| 1 | Algo emir uçları doğrulanmamış; iki eşzamanlı reduceOnly stop varsayımı | Canlıda stopsuz pozisyon | §3.3 testnet + §3.4 gerçek duman testi; stop kurulamazsa kapat kuralı; fixture'lar |
| 2 | Mark vs last | Backtest/paper iyimser ya da kötümser stop | PaperBroker mark tetikli; model farkı raporu; 1m mark verisi |
| 3 | Takvim: Faz A'da tampon yok | Paper 1–4 gün kayar | Kapsam kilidi (§3.1 "yok" listesi); öncelik sırası; kayma kararı kullanıcıda |
| 4 | Yeni motorun kendi hataları (freqtrade'in yılların sertleşmesi yok) | Yanlış paper sonuçları, canlıda kayıp | Çapraz doğrulama, paper↔backtest birebir eşleme, 48 saat deneme, 2 hafta testnet gölgesi, mutabakat fail-closed |
| 5 | Paper dolumları gerçek değil (kayma sabit bps, derinlik yok) | Canlıda beklenenden kötü | Testnet gölge farkı; canlının ilk haftası gerçek/model kayma ölçümü; kayma varsayımı tutucu |
| 6 | Tek risk seti bozulması | 1l3a'daki tutarsızlığın tekrarı | `trader_engine` içinde risk sabiti tanımlamak testle yasak (grep testi); yalnız `LOCKED_CFG` |
| 7 | float ↔ Decimal sınırı | Min notional / step ihlali, ret | Yuvarlama yalnız `rules.py`'de; dolum sonrası risk doğrulaması; sınır değer testleri |
| 8 | Hız sınırı, exchangeInfo, listenKey yok | Yasak / ret / geç fark edilen dolum | Emir sayacı + saatlik yenileme (Faz B); 15 sn mutabakat; borsada stop |
| 9 | Feed tek hata noktası | Giriş durur, paper stopları gecikir | systemd yeniden başlatma, bayatlık kapısı, yeniden oynatma, health `candle_age` |
| 10 | sqlite çoklu süreç | Kilitlenme | WAL, tek yazar kuralı (feed→market, motor→kendi state/ledger), `busy_timeout` |
| 11 | Binance API değişikliği (ham istemci) | Sessiz bozulma | Haftalık testnet duman testi, bilinmeyen hata kodunda girişleri kapat |
| 12 | Ajan gerçeklemesi ile testlerin aynı yanlış varsayımı paylaşması | Yeşil ama yanlış | Testleri şartnameden bağımsız ajan yazar; gerçek veriyle çapraz doğrulama; kaydedilmiş gerçek yanıtlar |

Mentorun inceleyeceği (sırayla, her biri bir kapıdır):
1. `motor-spec.md` ve `motor-dolum-modeli.md` — kod başlamadan.
2. `Broker` arayüzü ve `PaperBroker` dolum kuralları (mark tetik, gap, aynı-bar sırası, funding işareti).
3. `order_manager` belirsizlik yolu ve client id — satır satır.
4. `gates.py` zinciri: her ret yolunun ledger kaydı ve fail-closed davranışı; TraderV1 karşılık tablosunda (§2.8) eksik kalmadığı.
5. Yeniden başlatma/yeniden oynatma ve mutabakat tablosu — çökme noktası testleriyle.
6. Çapraz doğrulama raporu: açıklanamayan fark kalmadığı; model farkı raporu.
7. 48 saat deneme kayıtları → paper başlatma onayı.
8. Freqtrade silme commit'i (§4.3 kabul maddeleri) ve dış çerçeve yasağı testi.
9. Faz B: `binance_rest.py` tekrar politikası, testnet fixture'ları, stop değiştirme sırası, canlı kontrol listesi, duman testi betiği ve sonucu → canlı onayı.

Kullanıcıdan gerekenler: (a) paper kayarsa 4 hafta mı 28 Aralık mı kararı; (b) Binance vadeli **testnet** API anahtarı, en geç 4 Aralık; (c) canlı alt hesap anahtarı takvimi değişmedi (paper 2. hafta).
