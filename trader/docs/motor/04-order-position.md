# 04 — state.sqlite, OrderManager, PositionManager (spesifikasyon v1, 16 Kasım 2026)

Kaynak kararlar: `motor-tasarimi.md` §2.2 (`order_manager`, `position_manager`, `state`), §2.4 (idempotent client id), §2.6 (stop yönetimi, mutabakat ilkeleri), §2.8 (TraderV1 karşılık tablosu), §3.1 (P3: `state` + `order_manager`), §4.3 madde 1 (`traderv1-bekleyen-degisiklikler.md` içeriği bu belgeye taşınır). TraderV1 davranışı: `custom_stoploss` (`trail_stop_path`), `custom_exit` (target/time_stop/regime_flip/trail_stop/force_exit), `order_filled` (`_on_entry_fill`/`_on_exit_fill`), `_ledger_exit_reason`, `_exit_state`/`_rebuild_state`. Bağımlılıklar: `02-clock-bars.md`, `03-paper-broker.md` (Broker arayüzü), `trader_core.signals` (`trail_stop_path`, `time_stop_due`, `target_reached`, `regime_flip_exit`), `trader_core.ledger` (`TradeEntry`, `TradeExit` veri sınıfları). Bu belge kod, test ve commit içermez.

## 1. Kararlar (özet)

| Konu | Karar |
|---|---|
| Kalıcılık | `state.sqlite` motorun **tek** yerel durumudur; paper'da `PaperBroker.snapshot()` de aynı işlemde yazılır → çökme-tutarlı yeniden oynatma (05) |
| Tek yazar | Süreç başına dosya kilidi (`flock`); ikinci motor reddedilir |
| Emir günlüğü | Her emir POST'tan **önce** `pending` yazılır (commit); belirsizlikte kimlikle sorgu, yalnız "emir yok" ise **tek** yeniden gönderim |
| Client id | `tr<L veya T><e/s/t/x>-<sha1(bot, pair, side, signal_bar_close_ts, role_letter, seq; dikey çizgiyle birleşik)[:24]>`; giriş ve çıkış (`e`,`x`) için `seq = 0` **sabit**, yeniden gönderim aynı kimlikle (aşağıda "tasarımla fark") |
| Stop | Hep miktar bazlı reduceOnly; yalnız **sıkılaşır**; yeni stop **önce**, eski iptal **sonra** |
| Çıkış önceliği | R1: `target` → `time_stop`; T1: `regime_flip` → `trail_stop` (stop fiyatın ötesine geçtiyse) — TraderV1 `custom_exit` ile aynı sıra. Çıkışlar hiçbir kapıya bağlı değildir |
| Ledger yazımı | `ledger_outbox` tablosu: giriş/çıkış kaydı state işlemiyle **aynı işlemde** kuyruğa alınır, sonra defter yazılır, başarıyla `done`; yeniden başlatmada kalanlar yeniden yazılır (defter idempotent) |
| MFE/MAE | Doğal olarak 1 dk **last** barlarından (kaba kipte 15 dk), `excursion_tf` ile; ledger `mfe_r/mae_r/bars_held`'i kendisi hesaplar |

**Tasarımla fark (mentor onayı gerekir):** tasarım §2.4 "belirsizlik sonrası yeniden gönderimde deneme sayacı seq'e girer" der. Burada `e` ve `x` kimlikleri yeniden gönderimde **aynı** kalır (çift giriş yalnızca kimlik tekrarıyla borsa tarafında matematiksel olarak engellenir; sayaçlı yeni kimlik, ilk POST geç ulaşırsa çift emre yol açar). Deneme sayacı **yalnız `s` (stop)** için kullanılır: iptal edilmiş eski stopun kimliği yeniden kullanılamaz (1l3a test `r2_yeniden_kurulumda_kimlik_deneme_sayaciyla_degisir`), bu yüzden `seq` stop sürüm sayacıdır (her trail güncellemesi ve her yeniden kurulum yeni kimlik). Mentor incelemesi §5 madde 3 bu noktayı satır satır gözden geçirir.

## 2. DOSYA SAHİPLİĞİ

Bu birim yalnızca şunlara dokunur:

- `src/trader_engine/state.py`, `order_manager.py`, `position_manager.py`
- `tests/engine/test_engine_state_spec.py`, `test_engine_order_manager_spec.py`, `test_engine_position_manager_spec.py` (bağımsız test ajanı); `test_engine_order_position_impl_smoke.py` (gerçekleme ajanı)

Dokunulmaz: `types.py`/`errors.py`/`numeric.py` (02), `brokers/*` (03), `engine.py`/`gates.py`/`strategy_runner.py`/`reconcile.py` (05). `trader_core` içindeki hiçbir dosya.

Bu birim `Engine`'i, `StrategyRunner`'ı ve defteri **import etmez**; `ledger` yalnızca `TradeEntry`/`TradeExit` veri sınıfları için (outbox yükü) ve `Ledger` tipi parametre olarak (yazma 05'te `drain_outbox(ledger)` işleviyle çağrılır; bu işlev `state.py` içindedir ve defteri argüman olarak alır).

## 3. `state.py`

```python
class StateStore:
    def __init__(self, path: str, *, bot: str, durability: Literal["full","off"] = "full", lock: bool = True)
        # full: WAL + synchronous=FULL; off (yalnız backtest): ":memory:" ya da geçici dosya, commit'ler sentetik (fsync yok)
    def close(self) -> None
    @contextmanager
    def tx(self) -> Iterator[None]            # BEGIN IMMEDIATE ... COMMIT; istisna -> ROLLBACK; iç içe çağrı: aynı işleme katılır (derinlik sayacı)
    def integrity_check(self) -> bool         # PRAGMA integrity_check == "ok"
    def in_tx(self) -> bool
    def barrier(self, *, allow_outer: bool) -> None   # POST-öncesi commit çiti: tx dışındaysa no-op; dış tx içindeyse allow_outer=False ise StateError (canlı broker için dış tx yasak)
    # --- pozisyonlar
    def next_trade_id(self) -> int            # kv 'next_trade_id' (1'den başlar); tx içinde artırılır
    def insert_position(self, p: Position) -> None
    def update_position(self, trade_id: int, **fields) -> None   # yalnız Position alanları; bilinmeyen alan ValueError
    def get_position(self, trade_id: int) -> Position | None
    def position_for_pair(self, pair: str) -> Position | None    # status != "closed" olan (en fazla bir)
    def open_positions(self) -> list[Position]                   # status in (opening, open, closing), trade_id sırasıyla
    def closed_positions_since(self, since: datetime) -> list[Position]
    # --- emirler
    def insert_order(self, o: OrderRow) -> None               # status="pending"
    def update_order(self, client_id: str, **fields) -> None
    def get_order(self, client_id: str) -> OrderRow | None
    def orders_for_trade(self, trade_id: int) -> list[OrderRow]
    def unresolved_orders(self) -> list[OrderRow]             # status in (pending, unknown)
    # --- mum başına tek karar
    def mark_decided(self, pair: str, bar_close_ts: datetime, outcome: str) -> bool   # True: yeni, False: zaten vardı
    def is_decided(self, pair: str, bar_close_ts: datetime) -> bool
    # --- imleçler
    def get_cursor(self, pair: str, kind: Literal["minute","decision"]) -> datetime | None
    def set_cursor(self, pair: str, kind: str, ts: datetime) -> None   # geri gitmez; ts < mevcut -> StateError
    # --- genel
    def kv_get(self, k: str, default=None); def kv_set(self, k: str, v) -> None      # JSON-serileştirilebilir
    # --- ledger kuyruğu
    def outbox_add(self, kind: Literal["entry","exit"], trade_id: int, payload: dict) -> int
    def outbox_pending(self) -> list[OutboxRow]
    def outbox_done(self, outbox_id: int) -> None
    def drain_outbox(self, ledger) -> DrainResult      # kayıtları sırayla yazar; LedgerError'da durur, kalanlar kuyruğa kalır; DrainResult(written, failed, first_error)
```

### 3.1 Şema (`PRAGMA user_version = 1`)

```sql
CREATE TABLE positions(
  trade_id INTEGER PRIMARY KEY, bot TEXT NOT NULL, pair TEXT NOT NULL, side TEXT NOT NULL, setup TEXT NOT NULL,
  status TEXT NOT NULL CHECK(status IN('opening','open','closing','closed')),
  decision_id INTEGER NOT NULL, signal_bar_close_ms INTEGER NOT NULL,
  entry_ms INTEGER, entry_bar_open_ms INTEGER, entry_price REAL, qty REAL, leverage INTEGER NOT NULL,
  initial_stop REAL NOT NULL, current_stop REAL NOT NULL, stop_seq INTEGER NOT NULL DEFAULT 0, stop_client_id TEXT,
  planned_target REAL, trail_atr REAL NOT NULL, param_version_id INTEGER NOT NULL, trigger_tf TEXT NOT NULL,
  risk_amount REAL NOT NULL, margin REAL NOT NULL, rh REAL, rl REAL,
  fee_entry REAL NOT NULL DEFAULT 0, funding_paid REAL NOT NULL DEFAULT 0,
  mfe_price REAL, mae_price REAL, exit_reason TEXT, exit_client_id TEXT, closed_ms INTEGER);
CREATE UNIQUE INDEX ux_pos_pair_live ON positions(pair) WHERE status != 'closed';   -- çift başına en fazla bir canlı kayıt
CREATE TABLE orders(
  client_id TEXT PRIMARY KEY, pair TEXT NOT NULL, role TEXT NOT NULL, order_side TEXT NOT NULL, qty REAL NOT NULL,
  trigger_price REAL, reduce_only INTEGER NOT NULL,
  status TEXT NOT NULL CHECK(status IN('pending','accepted','filled','rejected','unknown','failed','canceled','expired')),
  signal_bar_close_ms INTEGER NOT NULL, seq INTEGER NOT NULL, attempts INTEGER NOT NULL DEFAULT 0,
  trade_id INTEGER, broker_order_id TEXT, detail TEXT, created_ms INTEGER NOT NULL, updated_ms INTEGER NOT NULL);
CREATE TABLE decided(pair TEXT NOT NULL, bar_close_ms INTEGER NOT NULL, outcome TEXT NOT NULL, PRIMARY KEY(pair, bar_close_ms)) WITHOUT ROWID;
CREATE TABLE cursors(pair TEXT NOT NULL, kind TEXT NOT NULL, ts_ms INTEGER NOT NULL, PRIMARY KEY(pair, kind)) WITHOUT ROWID;
CREATE TABLE kv(k TEXT PRIMARY KEY, v TEXT NOT NULL);
CREATE TABLE ledger_outbox(
  id INTEGER PRIMARY KEY AUTOINCREMENT, kind TEXT NOT NULL, trade_id INTEGER NOT NULL,
  payload TEXT NOT NULL, done INTEGER NOT NULL DEFAULT 0, created_ms INTEGER NOT NULL);
```
Ayrılmış `kv` anahtarları: `initialized_at`, `next_trade_id`, `day_start:<YYYY-MM-DD>` (UTC gün başı cüzdan), `broker_snapshot` (paper; JSON), `entries_blocked_reason` (metin ya da yok), `kill_seen_at`, `engine_version`, `trigger_tf`.

### 3.2 Değişmezler

1. `(pair)` için `status != 'closed'` en fazla bir satır (kısmi benzersiz indeks).
2. `decided` satırı bir kez yazılır (`mark_decided` ikinci çağrıda `False`); satırlar silinmez.
3. `set_cursor` geri gitmez.
4. `tx()` dışında yazma çağrısı `StateError`.
5. `outbox` yükü JSON'dur ve `TradeEntry`/`TradeExit` alanlarına birebir karşılık gelir (`datetime` → ISO-Z metin); `drain_outbox` aynı yükle `record_trade_entry/exit` çağırır (defter aynı içerikle tekrarı idempotent kabul eder).
6. Açılış: dosya yok → şema kurulur, `initialized_at` yazılır; var ve `user_version != 1` → `StateError` (göç yok); `integrity_check` başarısız → `StateError` (motor başlamaz).
7. `durability="off"` yalnız `mode=="backtest"` ile kullanılır; engine `paper` modunda `full` zorunlu.

## 4. `order_manager.py`

```python
def make_client_id(bot: str, role: Role, pair: str, side: Side, signal_bar_close_ts: datetime, seq: int) -> str
        # "tr" + ("L" if bot=="learner" else "T") + {"entry":"e","stop":"s","target":"t","exit":"x"}[role] + "-" + sha1(f"{bot}|{pair}|{side}|{ts_iso}|{role_letter}|{seq}")[:24]
        # role_letter ∈ {e,s,t,x}; ts_iso = "YYYY-MM-DDTHH:MM:SSZ"; uzunluk 5+24 = 29 ≤ 36

@dataclass(frozen=True)
class OrderRow: client_id, pair, role, order_side, qty, trigger_price, reduce_only, status, signal_bar_close_ts, seq,
                attempts, trade_id, broker_order_id, detail, created_ts, updated_ts

@dataclass(frozen=True)
class SubmitOutcome:
    ok: bool                                  # emir kabul edildi/doldu (accepted | filled)
    status: Literal["filled","accepted","rejected","failed"]
    order: OrderRow
    result: OrderResult | None
    note: str | None                          # "adopted_after_unknown" | "resent_once" | "duplicate_adopted" | …

class OrderManager:
    def __init__(self, bot: str, broker: Broker, state: StateStore, clock: Clock, rules_fn: Callable[[str], SymbolRules],
                 unknown_grace_s: float = 2.0, max_attempts: int = 2)
        # her POST'tan önce state.barrier(allow_outer=broker.is_simulated); simüle broker'da motor adımı tek dış tx'tir (05 §1: commit-öncesi-POST kuralı yalnız gerçek broker için ayrı işlemdir)
    def submit_entry(self, intent: Intent, trade_id: int) -> SubmitOutcome        # role "entry", seq 0; broker.prepare önce çağrılır
    def submit_exit(self, pos: Position, reason: str, at: datetime) -> SubmitOutcome     # role "exit" reduceOnly market, signal_bar_close_ts=at (karar anı D), seq 0
    def place_initial_stop(self, pos: Position) -> SubmitOutcome                  # stop_seq 0, fiyat pos.initial_stop (tick sıkı yuvarlı)
    def replace_stop(self, pos: Position, new_stop: float) -> SubmitOutcome       # §4.3
    def cancel_resting(self, pos: Position) -> None                               # duran stop/target emirlerini iptal (çıkış sonrası tidy)
    def resolve_unresolved(self) -> list[SubmitOutcome]                           # başlangıçta ve her döngüde pending/unknown emirleri çözer
```

### 4.1 Gönderim protokolü (her rol için ortak)

1. `row = OrderRow(status="pending", attempts=0, …)`; `with state.tx(): state.insert_order(row)` → **commit** (POST'tan önce).
2. `broker.<call>(req)` çağrılır. `BrokerUncertain` fırlarsa ya da `result.status == "unknown"` ise `unknown` yolu (§4.2).
3. `result.status`: `filled` → `update_order(status="filled", broker_order_id…)`; `accepted` → `accepted`; `rejected` → `rejected` (`detail=reason`). `rejected` ve `reason == "duplicate_client_id"`: kimlik zaten borsada var demektir → `broker.query` ile özgün emir **benimsenir** (`note="duplicate_adopted"`), durum sorgunun durumuna eşlenir.
4. Her durum geçişi ayrı `tx()` ile commit edilir.

### 4.2 Belirsizlik yolu (en kritik; mentor satır satır inceler)

`unknown` olunca: satır `status="unknown"`, `attempts` değişmez; ardından **hemen** `broker.query(pair, cid)`:
- **Bulundu** (`BrokerOrder` döndü): durum sorgudan alınır (`filled`/`new→accepted`/`canceled`/`rejected`); `note="adopted_after_unknown"`. Yeniden gönderim **yok**.
- **Bulunamadı (`None`)** ve `attempts == 0`: `unknown_grace_s` kadar `clock.sleep`; ikinci kez `query`; hâlâ `None` ise `attempts=1` ve **aynı kimlikle** tek yeniden gönderim (`note="resent_once"`). Yeniden gönderim yine `unknown` olursa `status="failed"`.
- **Bulunamadı** ve `attempts ≥ max_attempts − 1`: `status="failed"`.
- `failed` sonuçları: **giriş** → pozisyon kaydı (varsa `opening`) silinir/`closed` (`exit_reason="other"`, giriş yapılmadı), ledger'da karar `order_failed` ile düzeltilir (05 `supersedes_id`), `kv["entries_blocked_reason"]="order_unknown"` yazılır (girişler kapanır, mutabakat/kullanıcı temizleyene kadar); **çıkış** → pozisyon `closing` olarak kalır, her döngüde `resolve_unresolved` yeniden dener (sınırsız deneme değil: 3 döngü sonra `kv["entries_blocked_reason"]="exit_unknown"` + `CRITICAL`; açık pozisyonu **stop korur**); **stop** → pozisyon korumasız sayılır: bir kez daha dene, olmazsa pozisyon piyasa ile kapatılır (§5.2).
- Yeniden başlatmada `unresolved_orders()` (`pending`/`unknown`) aynı yolla çözülür; `pending` satır için de önce `query` yapılır (POST gitmiş olabilir). Hiçbir koşulda "emir yok" teyidi olmadan ikinci gönderim yapılmaz.

### 4.3 `replace_stop` (önce yeni, sonra eski iptal)

1. `new_stop` tick'e **sıkı** yuvarlanır (`numeric.round_tight`). Sıkılaşma denetimi: long için `new > pos.current_stop`, short için `new < pos.current_stop`; değilse **no-op** (`ok=True`, `note="not_tighter"`); gevşetme asla yapılmaz.
2. `seq' = pos.stop_seq + 1`; `cid' = make_client_id(…, "stop", …, pos.signal_bar_close_ts, seq')`. `with state.tx(): update_position(stop_seq=seq')` (kimlik **POST'tan önce** kalıcıdır).
3. `place_stop` (yeni) gönderilir (§4.1). **Başarısız** (`rejected` / `failed`):
   - `rejected` + `would_trigger` (yeni stop fiyatın ötesinde): stop güncellenmez; çağıran (05) bunu `trail_stop` **piyasa çıkışı** olarak ele alır (`SubmitOutcome.note="would_trigger"`).
   - diğer ret/failed: eski stop duruyor, güncelleme sonraki bar kapanışında yeniden denenir; `CRITICAL` değil `WARNING` (pozisyon korumalı).
4. **Başarılı** (`accepted`): `with state.tx(): update_position(current_stop=new, stop_client_id=cid')`; **sonra** eski stop (`pos.stop_client_id`) `broker.cancel`; iptal hatası pozisyonu etkilemez (eski stop yetim kalır → mutabakat temizler; yeni stop daha sıkı olduğundan zarar yok).
5. Bar kapanışında en fazla bir kez (çağıran garanti eder: aynı `D` için ikinci çağrı aynı `seq'` hesaplar ve `duplicate` yolundan benimser).

### 4.4 Diğer kurallar

- `submit_entry`: `broker.prepare(pair, intent.leverage)` her seferinde (idempotent); `qty` `rules.step`'e **aşağı** yuvarlı gelir (risk kilidi `size_position` zaten böyle üretir; burada `is_multiple` denetimi, değilse `ValueError` → giriş yok). `OrderRequest.reduce_only=False`, `working_type` varsayılan.
- `submit_exit`: `qty = pos.qty` (kısmi çıkış yok); `trade_id` bağlanır; çıkış emri kabul edilince pozisyon `status="closing"`, `exit_client_id` kaydedilir (aynı işlemde).
- Çıkış emri verilmeden önce duran stoplar **iptal edilmez** (korumasız an yaratmaz); dolumdan sonra `cancel_resting`.
- `OrderRow.status="failed"` terminal; `canceled`/`expired` yalnız broker olaylarından.
- Her hata yolunda istisna dışarı sızmaz: `SubmitOutcome(ok=False, status="failed", note=<kod>)`; yalnız `StateError` (disk/ kilit) fırlatılır ve motor durur (durumu yazamıyorsa çalışmaz).

## 5. `position_manager.py`

```python
@dataclass(frozen=True)
class ExitContext:                         # 05 StrategyRunner'dan kurar; entry_bar_open ... son kapanmış bar dahil
    bar_close_ts: datetime                 # D
    highs: np.ndarray; lows: np.ndarray; atrs: np.ndarray       # tetik tf; E..son kapanmış bar (E dahil); atrs = atr_tf
    regime_last: str | None                # son kapanmış barın hizalı rejim etiketi
    last_close: float                      # son kapanmış barın kapanışı (TraderV1 current_rate)
    n_closed: int                          # = len(highs)

@dataclass(frozen=True)
class ExitDecision:
    kind: Literal["none","exit","stop_update"]
    reason: str | None                     # kind=="exit": ExitReason ("target","time_stop","regime_flip","trail_stop","force_exit")
    new_stop: float | None                 # kind=="stop_update"
    planned_exit: float | None             # ledger planned_exit (target: hedef; trail_stop çıkışı: None)

def evaluate_exit(pos: Position, ctx: ExitContext | None) -> ExitDecision          # SAF
def trail_stop_value(pos: Position, ctx: ExitContext) -> tuple[float, bool]        # (stop, armed); R1: (initial_stop, False)
def apply_entry_fill(pos_or_intent_ctx, fill: Fill, bar: MinuteBar, now: datetime) -> Position
def apply_exit_fill(pos: Position, fill: Fill, bar: MinuteBar | None, now: datetime) -> ClosedTrade
def apply_funding(pos: Position, event: BrokerEvent) -> Position
def update_excursion(pos: Position, bar: MinuteBar) -> Position                   # last high/low ile uçları genişletir
def exit_reason_for_stop_fill(pos: Position) -> str                               # current_stop != initial_stop -> "trail_stop" else "stop"
def build_trade_exit(pos: Position, closed: ClosedTrade, excursion_tf: str) -> dict   # TradeExit alan sözlüğü (outbox yükü)
def build_trade_entry(pos: Position) -> dict
```
`ClosedTrade(trade_id, exit_ts, exit_price, exit_reason, planned_exit, fee_exit, funding_paid, max_favorable_price, max_adverse_price, excursion_tf)`.

### 5.1 `evaluate_exit` (TraderV1.`custom_exit` + `custom_stoploss` karşılığı; saf)

Girdi `ctx is None` ya da çıkış verisi eksik (`pos.setup` yok / `initial_stop` sonlu değil / `entry_bar_open` yok) → `ExitDecision("exit","force_exit")` **(fail-closed: korumasız/belirsiz pozisyon tutulmaz; TraderV1 `force_exit` ile aynı)**. `ctx.n_closed == 0` (giriş barı henüz kapanmadı) → `"none"`.

1. **R1:** `planned_target` sonluysa `ctx.highs/lows` boyunca herhangi bir `k` için `signals.target_reached(side, target, high_k, low_k)` ise → `exit "target"`, `planned_exit = planned_target`. Değilse `signals.time_stop_due(ctx.n_closed)` ise → `exit "time_stop"`. Aksi `none` (R1'de iz süren stop yok, `regime_flip` yok).
2. **T1:** `signals.regime_flip_exit(side, ctx.regime_last)` ise → `exit "regime_flip"` (`planned_exit=None`). Aksi `stop, armed = trail_stop_value(pos, ctx)`; `armed` ve (`long: stop ≥ ctx.last_close` | `short: stop ≤ ctx.last_close`) ise → `exit "trail_stop"` (`planned_exit=None`). Aksi `stop` mevcut stoptan **daha sıkı** ise (long `stop > pos.current_stop + EPS`, short `stop < pos.current_stop − EPS`, `EPS=1e-9`) → `stop_update(new_stop=stop)`; değilse `none`.
3. `trail_stop_value`: `signals.trail_stop_path(side, pos.entry_price, pos.initial_stop, highs, lows, atrs, pos.trail_atr)` son eleman; `armed = (stop != pos.initial_stop)`. `pos.trail_atr`, `pos.initial_stop`, `pos.planned_target`, `pos.setup` giriş anında **dondurulmuş** değerlerdir (sonradan ders servisi parametre değiştirse etkilenmez; strateji-spec §4.2).
4. Aynı çağrı iki kez aynı sonucu verir (saflık); `ctx` tek kaynaktır, `datetime.now` yoktur.

### 5.2 Giriş dolumu (`apply_entry_fill`) ve stopsuzluk koruması

- Dolum olayı geldiğinde: `Position` `opening → open`; `entry_ts = fill.ts` (adım barı açılışı), `entry_price = fill.price`, `qty = fill.qty`, `fee_entry = fill.fee`, `entry_bar_open = floor_tf(entry_ts, trigger_tf)`, `mfe_price = mae_price = entry_price` sonra adım barının last high/low'u ile `update_excursion` (**giriş dakikasının tamamı dahil**, eski `_excursion` kuralı: `entry_ts` ile kesişen mumlar).
- **Dolum sonrası risk doğrulaması (§2.2):** `risk.loss_at_stop(qty, fill_price, initial_stop, LOCKED_CFG) ≤ LOCKED_CFG.max_trade_risk × equity_at_decision` (`equity_at_decision` karar anındaki `AccountState.equity`, 05 geçer) ve stop doğru tarafta (long: `initial_stop < fill`; short: `initial_stop > fill`). İhlal → **tam kapatma** (`submit_exit(reason="other")`, `exit_reason="other"`; Faz A'da kısmi küçültme yok — canlıda reduceOnly küçültme Faz B). Sonuç ledger'da giriş + çıkış olarak görünür (giriş kaydı yazılmadan çıkış yazılamaz).
- Ardından `place_initial_stop` hemen çağrılır. Başarısızsa **bir** yeniden deneme (aynı `seq=0` kimliği değil: `rejected` ise yeni deneme `seq=1`, `unknown` ise §4.2); yine başarısızsa `submit_exit(reason="other")` (**"stop kurulamazsa kapat", §2.6**), `CRITICAL` günlük, `kv["entries_blocked_reason"]="stop_failed"`.

### 5.3 Çıkış dolumu (`apply_exit_fill`)

- `reason = fill.reason`: `"stop"` → `exit_reason_for_stop_fill(pos)` (`trail_stop` ya da `stop`; T1'de iz devredeyse `trail_stop`), `planned_exit = pos.current_stop`; `"target"` → `"target"`, `planned_exit = pos.planned_target` (Faz A'da yalnız `place_target` kullanılırsa; `bar_close` kipinde hedef çıkışı `market` dolumlu `exit` emridir ve neden `pos.exit_reason`'dan gelir); `"liquidation"` → `"liquidation"`, `planned_exit=None`; `"market"` → `pos.exit_reason` (karar anında yazılmış: `target`/`time_stop`/`regime_flip`/`trail_stop`/`force_exit`/`manual`/`other`), `planned_exit` yalnız `target` için hedef, diğerleri `None`.
- `fee_exit = fill.fee`; `funding_paid = pos.funding_paid` (pozitif = ödenen).
- `max_favorable_price`/`max_adverse_price`: `update_excursion(adım barı)` ile çıkış dakikasının tamamı dahil edilir, sonra **gerçekleşen giriş/çıkış fiyatlarıyla genişletilir** (long: `mfp = max(mfp, entry, exit)`, `map = min(map, entry, exit)`; short ters) — ledger doğrulaması (`max_favorable_price ≥ max(entry, exit)` …) bunu şart koşar. `excursion_tf = "1m"` (`step_s==60`) ya da `"15m"` (kaba kip). Uç fiyatlar `> 0` olmalı; aksi üçlü **birlikte** `None` (işlem yine kaydedilir: eski `_excursion` hata kuralı).
- Ledger'a yük: `TradeExit(trade_id, exit_ts, exit_price, exit_reason, planned_exit, fee_exit, funding_paid, max_favorable_price, max_adverse_price, excursion_tf)`; outbox'a **aynı `tx()` içinde** eklenir. `bars_held`/`mfe_r`/`mae_r` defter tarafından hesaplanır; **`bars_held` birimi 15 dakikadır** (tetik tf 1s olsa bile; defter-spec §3.4.1) — time-stop sayacı ise `ctx.n_closed` (tetik tf barı).

### 5.4 `update_excursion`

Long: `mfe_price = max(mfe_price, bar.last_h)`, `mae_price = min(mae_price, bar.last_l)`; short: `mfe_price = min(…, last_l)`, `mae_price = max(…, last_h)`. Her adımda **açık pozisyonu olan çiftler için** çağrılır (giriş dolumunu izleyen dahil, çıkışın gerçekleştiği adım dahil). Mark değil **last** (eski bekleyen-değişiklik şartı: mum verisi `high/low`).

## 6. Fail-closed kuralları

- `StateStore` açılamaz/bozuk/kilitli → motor başlamaz.
- Çıkış verisi eksik pozisyon → `force_exit` (TraderV1 `force_exit`).
- Hiçbir `evaluate_exit` yolu defter, veto, kill veya bayatlık kapısına bağlı değildir.
- Ledger yazılamazsa çıkış **yine yapılır** (outbox'ta bekler; `degraded` defter kendi spool'unu yönetir, defter-spec §8.2); giriş kaydı yazılamazsa giriş yapılmış pozisyon geri alınmaz, stop ile yönetilir ve girişler kapanır (defter kapısı kapanır; `ledger.entries_allowed` zaten bunu bildirir).
- `submit_*` çağrıları istisna sızdırmaz (yalnız `StateError`).

## 7. Elle doğrulanabilir örnekler

1. **Kimlik:** `make_client_id("learner","entry","BTC/USDT","long",2026-12-01T09:00:00Z,0) == "trLe-078ebfcdd4a5354100a0c4fe"`; `role="stop", seq=0 → "trLs-922b299d97c813c28fdda499"`; `seq=1 → "trLs-aa09899007fc9705496b85e4"`; `"exit" → "trLx-9de262c42db2e08b0098b1c6"`; `"target" → "trLt-d6a7eb9d18daedc978d108c1"`; `bot="twin","entry" → "trTe-b299042c99b76bbc1d2e36be"` (SHA-1 girdisi `learner|BTC/USDT|long|2026-12-01T09:00:00Z|e|0` biçimindedir: **rol tam adıyla değil harfiyle** yazılır, `e`/`s`/`t`/`x`; hesaplar bu girdiyle yapılmıştır). Aynı sinyal barı için ikinci giriş aynı kimliği üretir → çift giriş yok.
2. **Örnek A giriş → trail (T1 long, `trail_atr=3.0`):** `fill = 100.02`, `initial_stop = 98.00` ⇒ `R = 2.02`; eşik `100.02 + 2.02 = 102.04`. Giriş barından sonraki 4 kapanmış bar: `highs=[101, 102.5, 103.0, 102.0]`, `lows=[99.5, 100.5, 101.5, 100.8]`, `atrs=[1,1,1,1]`. `trail_stop_path` = `[98.0, 99.5, 100.0, 100.0]` (bar 2'de `hh=102.5 ≥ 102.04` ⇒ `cand = 102.5 − 3 = 99.5`; bar 3 `hh=103 ⇒ 100.0`; bar 4 `hh` değişmez ⇒ `100.0`). `evaluate_exit` bar 1: `stop=98.0`, `armed=False`, `98.0 > current_stop(98.0)` değil ⇒ `none`; bar 2: `stop_update(99.5)`; bar 4 (`last_close=100.5`, `stop=100.0 < 100.5`) ⇒ `stop_update` yok (zaten `current_stop=100.0`) ⇒ `none`. Aynı seriyle `last_close = 99.9` olsaydı: `armed` ve `stop(100.0) ≥ 99.9` ⇒ `exit "trail_stop"`.
3. **R1 hedef + zaman durdurma (long, hedef 104):** bar yüksekleri `…, 104.2` ⇒ `exit "target"`, `planned_exit=104`; hedefe hiç varılmadan `n_closed = 48` ⇒ `exit "time_stop"`; ikisi birden ⇒ `target` (hedef önce, TraderV1 sırası); `n_closed = 47` ⇒ `none`.
4. **T1 rejim dönüşü:** long + `regime_last="trend_down"` ⇒ `exit "regime_flip"`; `"range"`/`"volatile"`/`"unclear"` ⇒ çıkış yok (yalnız karşıt trend).
5. **Stop çıkışı eşlemesi:** `current_stop == initial_stop (98.0)` ve borsa stopu tetiklendi ⇒ `exit_reason="stop"`, `planned_exit=98.0`; `current_stop=100.0 ≠ initial` ⇒ `"trail_stop"`, `planned_exit=100.0`.
6. **MFE/MAE uçları:** long giriş `100.02`, çıkış `97.95`; dakika high/low'ları arasında `max high = 100.80`, `min low = 97.90` ⇒ `max_favorable_price = max(100.80, 100.02, 97.95) = 100.80`, `max_adverse_price = min(97.90, 100.02, 97.95) = 97.90`; `excursion_tf="1m"`. Defter: `mfe_r = max(0, (100.80−100.02)×6.369 / 13.999062) = 0.3549`, `mae_r = (100.02−97.90)×6.369/13.999062 = 0.9645` (hesap defter işidir; test yalnız ham uçları doğrular).
7. **Belirsiz giriş (FaultPlan `unknown_not_executed`, 1. çağrı):** `pending` commit → `market_order` `unknown` → `query → None` → `unknown_grace_s` bekle → `query → None` → **aynı kimlikle** tek yeniden gönderim (kabul) ⇒ `attempts=1`, `note="resent_once"`. `unknown_executed` ⇒ `query` emri bulur ⇒ `note="adopted_after_unknown"`, yeniden gönderim **yok** (broker'da tek emir).
8. **Çökme:** `pending` commit'ten sonra, `market_order`'dan önce süreç ölür ⇒ yeniden başlatmada `unresolved_orders()=[row]`; `query → None` ⇒ tek gönderim; `market_order` çağrılmışsa `query` onu bulur ⇒ gönderim yok.
9. **replace_stop sırası:** `current_stop=98.0, stop_client_id=cidS0` ⇒ yeni `99.5`: sıra = (a) `stop_seq=1` commit, (b) `place_stop(cidS1, 99.5)` kabul, (c) `current_stop=99.5, stop_client_id=cidS1` commit, (d) `cancel(cidS0)`. (b) `would_trigger` ile ret ⇒ `current_stop` değişmez, çağıran `trail_stop` piyasa çıkışı verir. `new_stop=97.0` (gevşetme) ⇒ no-op.

## 8. Kabul senaryoları (test ajanı için)

`state`: şema/`user_version`/kilit/`integrity`, `tx` geri alma, kısmi benzersiz indeks, `mark_decided` tek seferlik, imleç geri gitmez, kv JSON gidiş-dönüş, `outbox` yaz-boşalt-tekrarla (defter idempotent: iki kez drain aynı sonucu verir), çökme simülasyonu (tx ortasında süreç öldürme: ya hep ya hiç), `durability="off"` yalnız backtest. `order_manager`: §7 örnek 1, 7, 8, 9; tüm `FaultPlan` etkileri; `duplicate_client_id` → benimseme; `failed` yolları (giriş/çıkış/stop); stop `rejected` iki ardışık ⇒ pozisyon piyasada kapanır; `replace_stop` gevşetme no-op; kimlikler 29 karakter, yalnız `[A-Za-z0-9-]`. `position_manager`: §7 örnek 2–6; saflık (iki çağrı eşit); eksik veri ⇒ `force_exit`; `n_closed=0` ⇒ `none`; kısa pozisyon aynaları; `exit_reason` listesi `ledger._EXIT_REASONS` içinde; uç fiyatlar ledger doğrulamasını geçer (gerçek `Ledger` ile geçici dosyada `record_trade_exit`); dolum sonrası risk ihlali ve yanlış taraf stop ⇒ tam kapatma.

## 9. Belirsizlikler ve çözümleri

- **`bars_held` birimi:** ledger 15 dk sayar; zaman durdurma `n_closed` ile tetik tf barı sayar. İkisi birbirinin yerine kullanılmaz (rapor yazarları için not).
- **Hedef çıkışı (`target_mode="bar_close"`)** `custom_exit` ile aynıdır: kapanmış barın high/low'u hedefe değdiyse bir sonraki adımın açılışında piyasa çıkışı; borsada `TAKE_PROFIT_MARKET` Faz A'da **kurulmaz** (05 §1 çakışma notu).
- **Stop fiyatı yuvarlama:** `round_tight` stop'u girişe doğru yuvarlar → risk asla artmaz ama bazen birkaç tick daha sıkı stop doğar (1l3a kuralı); `risk.loss_at_stop` planlı (yuvarlanmamış) stopla hesaplandığından fark (bir iki tick) **risk dışında** kalır ve dolum sonrası doğrulama yuvarlanmış stopla yapılır.
