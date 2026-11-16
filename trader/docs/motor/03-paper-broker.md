# 03 — Broker arayüzü, PaperBroker, funding (spesifikasyon v1, 16 Kasım 2026)

Kaynak kararlar: `motor-tasarimi.md` §2.3 (Broker arayüzü), §2.5 (dolum modeli; paper = backtest), §2.6 (stop yönetimi — paper'da aynı akış), §4.2 (uyum kipi `legacy_compat`), §5 risk 2/5 (mark vs last, gerçekçi olmayan dolum). 1l3a'dan **yalnız kural** alınır (§1.2 satırı: stop/hedef aynı mumda → STOP, gap dolumu, funding imleci; kod kopyalanmaz). Bağımlılıklar: `02-clock-bars.md` (tipler, `numeric.py`, `CostModel`, `Clock`), `trader_core.risk` (`liquidation_price`, `LOCKED_CFG.maint_margin_rate` okunur). Bu belge kod, test ve commit içermez.

## 1. Kararlar (özet)

| Konu | Karar |
|---|---|
| Piyasa emri | Emir verildiği anı **izleyen** ilk adım barının (`step`) `last` açılışında dolar; aleyhte kayma + tick yuvarlama. Hemen dolum yok: `market_order` `accepted` döner, dolum `poll`'da olay olarak gelir (canlı yolla aynı akış) |
| Stop/hedef tetik | **mark** barının high/low'u (`trigger_source="mark"`); uyum kipinde last |
| Aynı adımda stop + hedef | **STOP** kazanır |
| Gap | Adım açılışı (mark) stopun ötesindeyse o adımın **last açılışı**; aksi hâlde stop fiyatı; ikisinde de stop kayması |
| Giriş adımında stop | Giriş dolumundan sonra **aynı adımın** mark aralığına karşı hemen denetlenir (iki aşamalı adım, §4) |
| Likidasyon | `risk.liquidation_price`; likidasyon stoptan önce değerse çıkış `liquidation`, kayıp = tüm izole teminat |
| Funding | 00/08/16 UTC'de, pozisyon o ana **önce** açıksa: `qty × mark × rate` (long öder, rate>0) |
| Kısmi dolum | Yok |
| Durum | Tamamı `snapshot()`/`restore()` ile JSON; motor her adımda `state.sqlite` işlemine yazar (04/05) |
| Belirlilik | Rastgelelik, duvar saati, ağ yok; aynı girdi → aynı çıktı |
| Hata enjeksiyonu | `FaultPlan` ile belirsiz/ret yanıtları üretilebilir (OrderManager belirsizlik yolu testleri için) |

## 2. DOSYA SAHİPLİĞİ

Bu birim yalnızca şunlara dokunur:

- `src/trader_engine/brokers/__init__.py` (boş), `brokers/base.py`, `brokers/paper.py`
- `src/trader_engine/funding.py`
- `tests/engine/test_engine_broker_base_spec.py`, `test_engine_paper_broker_spec.py`, `test_engine_funding_spec.py` (bağımsız test ajanı); `test_engine_paper_broker_impl_smoke.py` (gerçekleme ajanı)

Dokunulmaz: `types.py`, `numeric.py`, `clock.py` (02); `brokers/binance_futures.py` (Faz B, hiç oluşturulmaz); `order_manager.py`, `position_manager.py`, `state.py` (04); `engine.py` (05).

## 3. `brokers/base.py` — arayüz

```python
class Broker(Protocol):
    is_simulated: bool                                             # PaperBroker True; canlı broker False (Faz B)
    def rules(self, pair: str) -> SymbolRules
    def account(self) -> BrokerAccount
    def positions(self) -> list[BrokerPosition]                    # pair sırasıyla
    def open_orders(self, pair: str | None = None) -> list[BrokerOrder]    # status=="new" olanlar
    def prepare(self, pair: str, leverage: int) -> None            # izole + one-way + kaldıraç; idempotent
    def market_order(self, req: OrderRequest) -> OrderResult       # role ∈ {entry, exit}
    def place_stop(self, req: OrderRequest) -> OrderResult         # role=="stop": STOP_MARKET reduceOnly
    def place_target(self, req: OrderRequest) -> OrderResult       # role=="target": TAKE_PROFIT_MARKET reduceOnly
    def cancel(self, pair: str, client_id: str) -> None            # yoksa/zaten kapalıysa sessiz no-op
    def query(self, pair: str, client_id: str) -> BrokerOrder | None   # belirsizlik çözümü
    def poll(self, now: datetime) -> list[BrokerEvent]             # kuyruğu boşaltır, zaman sırasıyla

class SimBroker(Broker, Protocol):                                 # PaperBroker uygular; canlı broker uygulamaz
    def advance(self, bars: Mapping[str, MinuteBar], phase: Literal["fills","triggers"]) -> None
    def snapshot(self) -> dict
    def restore(self, snap: dict) -> None
```
Uyum kuralları: `OrderResult.status ∈ {filled, accepted, rejected, unknown}`; `unknown` **yalnız** ağ belirsizliğinde (paper'da yalnız `FaultPlan` ile); motor asla körlemesine tekrar göndermez (04). `poll` olayları `(ts, sıra numarası)` sırasıyla verir ve her olayı bir kez teslim eder.

## 4. `brokers/paper.py`

```python
@dataclass(frozen=True)
class PaperConfig:
    cost: CostModel                       # 02
    mmr: float                            # bakım teminat oranı; motor LOCKED_CFG.maint_margin_rate'i geçer
    wallet_start: float = 1000.0

class PaperBroker:
    def __init__(self, cfg: PaperConfig, rules_fn: Callable[[str], SymbolRules],
                 funding_fn: Callable[[str, datetime, datetime], list[FundingPoint]],   # (pair, start_excl, end_incl)
                 clock: Clock, fault_plan: FaultPlan | None = None)
    # Broker + SimBroker (§3)
    def counters(self) -> dict    # mark_fallbacks, minute_gaps, funding_missing, rejects, duplicates
```

### 4.1 İç durum (snapshot/restore ile birebir)

`wallet: float`; `leverage: dict[pair,int]` (prepare ile); `positions: dict[pair, _Pos]` (one-way: çift başına en fazla bir; `_Pos`: side, qty, entry_price, leverage, margin, liq_price, funding_paid, fee_paid_entry, opened_ts); `orders: dict[client_id, _Order]` (tüm durumlar, yinelenen kimlik denetimi için; `status ∈ new|filled|canceled|rejected|expired`); `order_seq: int`; `events: deque`; `last_funding_ts: dict[pair, datetime|None]`; `last_mark: dict[pair, float]`; `last_step_ts`; sayaçlar. `snapshot()` JSON-uyumlu `dict` (datetime'lar ISO-Z metin, float'lar `repr` hassasiyetiyle) döner; `restore(snapshot())` sonrası davranış **bit-bit aynıdır** (test).

### 4.2 Piyasa emri (`market_order`)

1. Doğrulama (ret → `OrderResult(status="rejected", reason=…)`; durum değişmez): `qty` sonlu `> 0`; `qty` `rules.step`'in tam katı (`numeric.is_multiple`); `qty ≤ rules.max_qty`; entry için `req.leverage == leverage[pair]` (`prepare` çağrılmamış → `"not_prepared"`, farklı → `"leverage_mismatch"`); entry için çiftte açık pozisyon varsa `"position_exists"`; reduceOnly `exit` için pozisyon yoksa `"no_position"`, yön ters değilse `"wrong_side"`, `qty > pozisyon qty` → `"reduce_only_exceeds"`; `client_id` zaten varsa **`rejected`, reason `"duplicate_client_id"`** (borsa davranışının benzetimi; `query` özgün emri döner) — kimlik bu kural gereği idempotenttir.
2. Kabul: `orders[cid]=new`, `OrderResult(status="accepted", order_id=f"P{seq}")`. Dolum **sonraki `advance(...,"fills")`** çağrısında olur (bir adım bekler).
3. `FaultPlan` (§6) varsa önce o uygulanır.

### 4.3 `advance(bars, phase)` — iki aşamalı adım

Motor her adım için sırayla çağırır: `advance(bars,"fills")` → `poll` → motor olayları işler (ör. giriş dolumunun ardından `place_stop` verir) → `advance(bars,"triggers")` → `poll`. `bars` yalnız o adımda barı olan çiftleri içerir. Adım süresi `step_s` (60 veya 900) ve `ts = bar.open_ts` olarak alınır.

**Aşama `"fills"`** (çift sırasıyla, `pair` alfabetik):
1. **Funding** (`ts` bir funding anı ya da aşılmışsa): `funding_fn(pair, last_funding_ts[pair], ts)` her `FundingPoint p` için, `p.ts ≤ ts` ve pozisyon `opened_ts < p.ts` ise: `mark = p.mark` ya da yoksa `bar.mark_o` ya da `bar.last_o` (sırayla; son ikisi `funding_missing`'e değil `mark_fallbacks`'a sayılır); `payment = qty × mark × rate × (+1 long | −1 short)`; `wallet −= payment`; `pos.funding_paid += payment`; olay `BrokerEvent(kind="funding", funding_paid=payment, rate, mark)`. `funding_fn` o aralık için **hiç** nokta dönmedi ve aralıkta bir funding anı vardıysa `funding_missing += 1` (ödeme 0 sayılır; uyarı). `last_funding_ts[pair] = ts`. İmleç `None` ise ya da çiftte pozisyon yoksa ilk adımda doğrudan `ts`'ye alınır (geçmiş funding sorgulanmaz); pozisyon açılırken imleç `max(imleç, dolum_ts)` olur (bayat imleçle büyük aralık sorgusu yapılmaz).
   Yeni pozisyon (bu adımda dolacak giriş) bu adımın funding'ini **ödemez** (funding anı dolumdan önce işlenir).
2. **Bekleyen piyasa emirleri** (`orders` içinde `role ∈ {entry, exit}`, `status=="new"`, oluşturma sırasıyla): dolum fiyatı `p0 = bar.last_o`; `fill_price = round_adverse(p0 × (1 ± slip_bps/1e4), order_side, tick)` (buy `+`, sell `−`; entry `slip_entry_bps`, exit `slip_exit_bps`). Giriş için: `qty × fill_price < min_notional` → emir `rejected`, olay `order_rejected` (reason `"min_notional"`); `margin = qty × fill_price / leverage`, `fee = qty × fill_price × taker_fee`; `margin + fee > available` → `rejected` (`"insufficient_margin"`). Aksi: dolum → `wallet −= fee`; pozisyon oluşturulur (`liq_price = risk.liquidation_price(fill_price, side, leverage, mmr)`) ya da (exit) kapatılır: `gross = qty × (fill − entry)` (long) / `qty × (entry − fill)` (short); `wallet += gross − fee`; çiftin bekleyen/duran tüm reduceOnly emirleri (`stop`/`target`) `canceled` olur, olay `order_canceled`; `BrokerEvent(kind="fill", fill=Fill(reason="market"))`.
3. `last_mark[pair] = bar.mark_c ?? bar.last_c`.

**Aşama `"triggers"`** (çift sırasıyla; yalnız açık pozisyon ve duran koruyucu emir varsa):
Tetik fiyat aralığı `(lo, hi)`: `trigger_source=="mark"` ise `(mark_l, mark_h)` (mark `None` ise last'a düş + `mark_fallbacks += 1`), `"last"` ise `(last_l, last_h)`. Açılış `op` benzer şekilde `mark_o`/`last_o`.
1. **Likidasyon önceliği:** long için `op ≤ liq` (adım açılışı zaten likidasyon ötesinde) → hemen likidasyon. Aksi hâlde sırayla: stop tetiklendi mi (`lo ≤ stop` long / `hi ≥ stop` short; **en sıkı** duran stop geçerlidir — iki stop varsa girişe en yakın olan), değilse likidasyon fiyatına değdi mi (`lo ≤ liq` / `hi ≥ liq`). Normal durumda `stop` likidasyon ile giriş arasındadır, bu yüzden stop önce tetiklenir; stop likidasyon ötesindeyse likidasyon önce (risk kilidi bunu imkânsız kılmalıdır, görülürse `BrokerEvent.detail="liquidation_before_stop"` + sayaç `anomalies`).
2. **Stop dolumu:** `gap = (op ≤ stop)` long / `(op ≥ stop)` short. `base = last_o` (gap) ya da `stop` (gap değil); `fill_price = round_adverse(base × (1 ∓ slip_stop_bps/1e4), order_side, tick)`; `fee = qty × fill_price × taker_fee`; `wallet += gross − fee`; pozisyon kapanır; çiftin kalan reduceOnly emirleri iptal; `Fill(reason="stop")`.
3. **Hedef** (`place_target` kullanıldıysa; Faz A motoru kullanmaz, bkz. 05 §1): long için `hi ≥ target`; aynı adımda stop da tetikliyse **stop** kazanır (hedef hiç işlenmez). Gap (`op ≥ target`) → `base = last_o`, aksi `target`; `slip_exit_bps` aleyhte.
4. **Likidasyon dolumu:** `fill_price = liq_price` (kayma yok); `Fill(reason="liquidation")`, `BrokerEvent(kind="liquidation")`; `fee = qty × entry_price × mmr` (bakım teminatı payı); toplam kayıp (giriş komisyonu/funding hariç) **tam olarak izole teminattır**: `gross + (−fee) = −margin` (aşağıdaki örnek 5). `wallet += gross − fee`.
5. `last_mark[pair]` güncellenir; dolumdan sonra `unrealized` hesabı son mark ile.

**Kural:** `"fills"` aşamasında doldurulan bir **giriş** için motor aynı adımın `"triggers"` aşamasından önce `place_stop` çağırabilir; `place_stop` bu adımın mark aralığına karşı `triggers` aşamasında denetlenir → giriş barında stop denetlenmiş olur. `place_stop`, çağrıldığı anda duran son mark'a göre **hemen tetiklenecek** konumdaysa (long: `stop ≥ last_mark`; short: `stop ≤ last_mark`) `rejected`, reason `"would_trigger"` (Binance "-2021" davranışı) — motor bunu "stop kurulamadı" yolu olarak ele alır (04).

### 4.4 `place_stop` / `place_target` / `cancel` / `query`

- `place_stop`: doğrulama: pozisyon var, `qty ≤ pozisyon qty` (reduceOnly), `req.reduce_only is True`, `trigger_price` tick'in tam katı (`is_multiple`; değilse `"tick"` ret), yinelenen kimlik → `duplicate_client_id`. Stopun girişe göre tarafı **denetlenmez** (iz süren stop girişin kâr tarafında olabilir); yalnız aşağıdaki `would_trigger` kuralı geçerlidir. Kabul → `accepted`; aynı çifte birden fazla duran stop **izinlidir** (yeni-önce-sonra-eski sırası, §2.6); tetiklendiğinde en sıkısı geçerlidir.
- `place_target`: aynı doğrulamalar; long hedefi `> last_mark`, short hedefi `< last_mark` değilse `"would_trigger"`.
- `cancel`: `status=="new"` ise `canceled` (olay `order_canceled`); yoksa/kapalıysa no-op (hata yok).
- `query(pair, cid)`: kayıtlı emri `BrokerOrder` olarak döner (her durum); bilinmeyen kimlik → `None`.
- `prepare(pair, lev)`: `lev` tam sayı `≥ 1`; çiftte açık pozisyon varken **farklı** kaldıraç → `BrokerError`; aynı değer no-op.
- `account()`: `unrealized = Σ pozisyon (mark−entry)×qty×işaret` (mark = `last_mark`; yoksa giriş fiyatı); `used_margin = Σ margin`; `equity = wallet + unrealized`; `available = wallet − used_margin`.
- `positions()`: `liq_price`, `margin` kayıtlı; `mark_price = last_mark`.

### 4.5 Uyum kipi (`cost.fill_model == "legacy_compat"`)

`granularity` zaten `"15m"`, `trigger_source="last"` (02 doğrulaması). Farklar: (i) kayma yok (`slip_*` yok sayılır); (ii) **tarihsel aylık tick** (freqtrade backtest piyasa hassasiyetini yok sayar; `get_tick_size_over_time`/`get_pair_precision` ile geçmişten tick türetir): çift başına ve takvim ayı başına (UTC) tick = 10^−(o ayki ana-zaman-dilimi mumlarının OHLC değerlerindeki en büyük ondalık hane sayısı); hane sayısı değer 10 ondalığa yuvarlanıp (float repr'ine dayanıklı) sayılır, sondaki sıfırlar sayılmaz. Bir işlem **giriş ayının** tick'ini alır ve ömrü boyunca korur; giriş ve çıkış (piyasa, stop, hedef) dolumları o tick'e **en yakına** yuvarlanır; ilk stop ve iz süren stop seviyeleri `round_tight` ile (long yukarı, short aşağı — freqtrade ile aynı yön) **aynı giriş-ayı tick'ine** yuvarlanır. Ayda veri yoksa sentetik (kural) tick'e dönülür. Uygulama: `HistoricalSource.tick_at` + `PaperBroker(tick_fn=…)` + `OrderManager.tick_fn` (yalnız `legacy_compat`; native kip borsa tick'i ve `round_adverse` ile aynen kalır; `GuardedView.tick_at` native'de `LookaheadError`). Not: SOL'da ara sıra 3 haneli mumlar olduğundan referans 0,001, sentetik kural 0,01 kullanır; bu 06 çapraz doğrulamasındaki tüm `price_rounding` farklarının nedeniydi; (iii) stop dolum fiyatı: adım açılışı stopun ötesindeyse açılış, değilse stop fiyatı (freqtrade ile aynı — *doğrulanacak*); (iv) `taker_fee = fee_eff = 0.0005 × fee_mult + slip_bps/1e4` (kaymanın komisyona katılması, `run_bt.py` ile aynı; değeri backtest çalıştırıcısı verir, 06); (v) funding: `qty × mark_1h_open(ts) × rate` — `FundingPoint.mark` 1h mark açılışıdır (01); (vi) likidasyon denetimi açık kalır (uyum kipinde de `liquidation` kaydı olursa çapraz doğrulama raporunda ayrı sınıflanır).

## 5. `funding.py`

```python
def funding_payment(side: Side, qty: float, mark: float, rate: float) -> float
        # +qty*mark*rate (long) / -qty*mark*rate (short). POZİTİF = ödenen (ledger işareti)
def due_funding_times(last_ts: datetime | None, upto: datetime) -> list[datetime]
        # (last_ts, upto] içindeki 00/08/16 UTC anları; last_ts None ise yalnız (upto-8sa, upto] içinde en fazla 1
def accrue(position_opened_ts: datetime, points: Sequence[FundingPoint], side: Side, qty: float, mark_fallback: float) -> tuple[float, int]
        # (toplam ödenen, kullanılan nokta sayısı); opened_ts >= p.ts olan noktalar atlanır
```
Kenarlar: `rate` sonlu; `mark ≤ 0` → `ValueError`; `qty ≤ 0` → `ValueError`; negatif `rate` long'a **alacak** (negatif ödeme) yazar.

## 6. `FaultPlan`

```python
@dataclass
class FaultRule:
    method: Literal["market_order","place_stop","place_target","cancel","query"]
    nth: int                       # o yöntemin n'inci çağrısı (1 tabanlı)
    effect: Literal["unknown_executed","unknown_not_executed","rejected","raise_uncertain"]
    reason: str | None = None
@dataclass
class FaultPlan: rules: list[FaultRule]
```
- `unknown_executed`: emir **kabul edilir** (durum değişir) ama sonuç `OrderResult(status="unknown")` döner. `unknown_not_executed`: durum değişmez, sonuç `unknown`. `rejected`: durum değişmez, `rejected(reason)`. `raise_uncertain`: `BrokerUncertain` fırlatır (04 bunu `unknown` sayar). Belirlenimli; rastgelelik yok.

## 7. Değişmezler

1. `wallet` yalnızca: giriş/çıkış komisyonu, gerçekleşmiş kâr/zarar ve funding ile değişir; her değişiklik bir olaya karşılık gelir.
2. `equity = wallet + unrealized`; `available = wallet − Σ margin`; paper'da `margin + fee ≤ available` olmadan giriş dolmaz.
3. Her adımda hiçbir pozisyon `qty ≤ 0`; kapanan pozisyonun tüm reduceOnly emirleri iptal edilmiştir.
4. `Fill.price` her zaman tick'in katıdır (native kip); alış dolumu `≥` ham fiyat, satış `≤` ham fiyat (aleyhte).
5. Aynı girdi dizisi (`advance`/`market_order`/…) iki kez uygulanınca bit-bit aynı olay ve `snapshot` üretir; `restore` ara noktadan devam ettirince tam çalışmayla aynı sonuç verir.
6. `poll` her olayı bir kez teslim eder; `restore` sonrası teslim edilmemiş olaylar yeniden verilmez (olay kuyruğu snapshot'a **dahildir**, ardından motor tarafından işlenmiş sayılır — motor `poll` sonucunu aynı işlemde state'e yazar, 05).

## 8. Uç durumlar

| Durum | Davranış |
|---|---|
| Adım barında mark yok | last'a düş, `mark_fallbacks` sayacı; sessiz değil |
| Bir çiftin adım barı o dakikada yok (borsa boşluğu) | O çift için o adım işlenmez (`minute_gaps` sayacı); stop denetimi bir sonraki barda yapılır (gap kuralı yakalar) |
| Stop tetik ve aynı adımda bekleyen piyasa **çıkış** emri | Önce `"fills"`: çıkış adım açılışında dolar, pozisyon kapanır, stop iptal; `"triggers"` aşamasında pozisyon yok |
| Giriş dolumu, aynı adımda mark aralığı stopu aşıyor | `place_stop` (dolum olayından sonra) → `"triggers"`'da tetiklenir; giriş adımında stop çalışmış olur |
| `qty × fill < min_notional` | `order_rejected` (`min_notional`); motor giriş yok sayar (04: `order_failed`) |
| Likidasyon, aynı adımda hedef/stop da değiyor | Stop likidasyondan uzaksa likidasyon (fiyat yolunda önce likidasyona varılır); aksi stop; ikisinde de bir kez dolum |
| Funding anında pozisyon yok | Ödeme yok, `funding_missing` artmaz (yok demek hata değil) |
| `rate` NaN (bozuk veri) | `ValueError`; ödeme uygulanmaz; sayaç `funding_missing`; engine `CRITICAL` (05) |
| `restore` geçersiz/eksik anahtar | `BrokerError`; motor başlamaz (fail-closed) |

## 9. Elle doğrulanabilir örnekler

Ortak ayarlar: native kip, `taker_fee=0.0005`, `slip_entry_bps=slip_exit_bps=2`, `slip_stop_bps=5`, `mmr=0.004`, `tick=0.01`, `step=0.001`, `min_notional=5`, kaldıraç 3, cüzdan 1000. `risk.size_position(1000, entry=100, stop=98, long, 3, LOCKED_CFG, 0.001, 5)` ⇒ `qty = 6.369`, `risk_amount = 13.999062` (risk-kilidi-spec).

1. **Long giriş (örnek A):** karar anı `D = 2026-12-01T09:00Z`; `market_order(buy, 6.369)` → `accepted`. 09:00 adımı: `last_o = 100.00` ⇒ ham `100.00 × 1.0002 = 100.02` ⇒ `fill = 100.02` (zaten tick katı). `fee = 6.369 × 100.02 × 0.0005 = 0.31851369`; `margin = 6.369 × 100.02 / 3 = 212.34246`; `wallet = 1000 − 0.31851369 = 999.68148631`; `liq_price = 100.02 × (1 − 1/3 + 0.004) = 67.08008` (`risk.liquidation_price`).
2. **Stop tetik (aynı pozisyon):** `place_stop(sell, 6.369, trigger=98.00)`. Bir sonraki adımda `mark_l = 97.90 ≤ 98.00`, `mark_o = 99.20 > 98.00` (gap yok) ⇒ ham `98.00 × (1 − 0.0005) = 97.951` ⇒ satış için aşağı tick `97.95`. `fee = 6.369 × 97.95 × 0.0005 = 0.311921775`; `gross = 6.369 × (97.95 − 100.02) = −13.18383`; `wallet = 999.68148631 − 13.18383 − 0.311921775 = 986.185734535`. Ledger R: `(−13.18383 − 0.31851369 − 0.311921775) / 13.999062 = −0.98678…` (funding yok) — `risk_amount` risk-kilidi `loss_at_stop` değeridir.
3. **Gap stop:** aynı kurulum, adım: `mark_o = 97.50 ≤ 98.00`, `last_o = 97.60` ⇒ ham `97.60 × 0.9995 = 97.5512` ⇒ aşağı tick `97.55`.
4. **Funding:** pozisyon 00:00'dan önce açık; 08:00'da `rate = 0.0001`, `mark = 101`: `payment = 6.369 × 101 × 0.0001 = 0.0643269` (long öder) ⇒ `wallet −= 0.0643269`; `BrokerEvent.funding_paid = +0.0643269`. Aynı koşulda **short**, qty 6.357 ⇒ `−0.0642057` (alır, cüzdan artar).
5. **Likidasyon (aynı long, stop yok / stop likidasyon ötesinde):** `liq = 67.08008`; adım `mark_l = 66.00`, `mark_o = 70` (gap yok) ⇒ `fill = 67.08008` (kayma yok); `fee = qty × entry × mmr = 6.369 × 100.02 × 0.004 = 2.54810952`; fiyat kaybı `6.369 × (100.02 − 67.08008) = 209.79435…`; toplam `212.34246 = margin` ✓.
6. **Aynı adımda stop+hedef (long, stop 98, hedef 104):** adım `mark_l = 97.9`, `mark_h = 105` ⇒ yalnız **stop** dolumu (`97.95`); hedef emri iptal.
7. **Duplicate:** aynı `client_id` ile ikinci `market_order` ⇒ `rejected / duplicate_client_id`; `query(cid)` özgün emri `filled` olarak döner.
8. **would_trigger:** `last_mark = 100.0`; long için `place_stop(trigger=100.5)` ⇒ `rejected / would_trigger`.
9. **Uyum kipi** (`fee_eff = 0.0005`, kayma yok): entry adım açılışı `100.00` ⇒ `fill = 100.00` (giriş-ayı tick'ine en yakın yuvarlama, §4.5 ii); stop `98.00` last aralığı `97.9` değdi ⇒ `fill = 98.00`; komisyon `6.369 × 100 × 0.0005 + 6.369 × 98 × 0.0005`.

## 10. Kabul senaryoları (test ajanı için)

Yukarıdaki 9 örnek (kuru sayılarla); tüm `rejected` nedenleri (`not_prepared`, `leverage_mismatch`, `position_exists`, `no_position`, `wrong_side`, `reduce_only_exceeds`, `step`, `tick`, `min_notional`, `insufficient_margin`, `duplicate_client_id`, `would_trigger`); iki duran stop (yeni-önce-sonra-eski): yeni daha sıkı olunca en sıkısı tetiklenir, eski stop iptal edilince tek kalır; funding işareti ve "giriş adımında funding yok"; `snapshot`/`restore` ortasından devam ≡ kesintisiz çalışma (rastgele ama sabit tohumlu bar dizisiyle 1000 adım, bit eşitliği); `FaultPlan` her `effect`; mark yok → `mark_fallbacks`; adım barı yok → `minute_gaps`; `wallet` muhasebe değişmezi (Σ olaylar = Δwallet); likidasyon toplam kayıp = teminat; kaba kip (`step_s=900`) ve uyum kipi dolum kuralları; aynı girdi iki kez → aynı olay dizisi.

## 11. Belirsizlikler ve çözümleri

- **Tasarım §2.5 madde 2 ile bu belge:** tasarım "mark açılışı stopun ötesindeyse o dakikanın last açılışı" der; burada aynen uygulanır. Mark ve last farklı olduğu için, **mark açılışı stopu aşmış, last açılışı aşmamış** olabilir (fiyat last'ta stopun üstünde dolar): bu kasıtlı (borsa mark ile tetikler, last ile dolar).
- **İki eşzamanlı reduceOnly stop** (§3.3 madde 3 testnet): paper izin verir. Testnet "izin vermiyor" derse `OrderManager.replace_stop` akışı (iptal → hemen yeni, arada bekçilik) paper'da da **aynen** modellenmelidir; PaperBroker'a `allow_dual_stops: bool = True` bayrağı eklenir (False iken ikinci duran stop `rejected / dual_stop_not_allowed`). Faz A'da varsayılan True.
- **Mark/last kapanış değeri ile hesap değerlemesi:** `equity` son `mark_c` ile; tasarım §2.5(7) ile uyumlu.
- **Likidasyon komisyonu:** gerçek borsada "likidasyon ücreti" vardır ve bakım teminatından farklı olabilir; burada `mmr × giriş değeri` olarak basitleştirilir ve "tutucu varsayım" etiketlidir (kayıp = teminat).
