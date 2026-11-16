# 05 — Engine, StrategyRunner, giriş kapısı, mutabakat, kill, status (spesifikasyon v1, 16 Kasım 2026)

Kaynak kararlar: `motor-tasarimi.md` §2.1 (veri akışı), §2.2 (`strategy_runner`, `gates`, `engine`, `reconcile`, `killswitch`, `status`, `cli`), §2.6 (mutabakat tablosu), §2.7 (ana döngü), §2.8 (TraderV1 karşılık tablosu — **hiçbir davranış kaybolmamalı**), §3.1 (P4, P7). TraderV1 davranışı (referans): `populate_indicators`, `_gate`, `_stale`, `_bar_final`/`_decided`, `veto_check` (stub), `leverage`, `custom_stake_amount` + `confirm_trade_entry`, `_account_state`, `_event`/`_features`, `_write_once`, `_record_gate_closed`/`_record_skipped_last`/`_write_risk_denied`/`_record_veto`, `order_filled`, `bot_loop_start`. Bağımlılıklar: `02` (tipler, saat, config), `01` (`MarketView`), `03` (`Broker`/`SimBroker`/`PaperBroker`), `04` (`StateStore`, `OrderManager`, `PositionManager`), `trader_core` (`signals`, `regime`, `risk`, `ledger`, `veto`). Bu belge kod, test ve commit içermez.

## 1. Kararlar (özet) ve tasarımla çakışmalar

| Konu | Karar |
|---|---|
| Tek döngü | Senkron, tek iş parçacığı; dakikalık adımlar zaman sırasıyla, tf kapanışında karar adımı |
| Sıra (§2.7) | Her karar adımında: parametre yenile → **çıkışlar** → **stop güncelle** → **girişler** |
| Aynı kod | `Engine` paper, backtest ve (Faz B) canlıda **aynı** sınıftır; fark `Broker`, `MarketView`, `Clock`, `SignalSource` enjeksiyonudur |
| Tek risk kaynağı | `risk.check_entry(..., LOCKED_CFG)`; engine hiçbir risk sayısı tanımlamaz |
| Kapı sırası | §4.1 tablosu (TraderV1 sırasıyla birebir; §2.2 sırası ile fark gerekçeli) |
| Çıkışlar kapısız | Defter/veto/kill/bayatlık hiçbir çıkışı engellemez |
| Atomiklik | Paper/backtest'te her adım (dakika ya da karar) **tek** `state.tx()`; `broker.snapshot()` aynı işlemde yazılır |
| Kalıcı "mum başına tek karar" | `state.decided(pair, bar_close_ts)` |
| Kaba kip / uyum kipi | Aynı `Engine`, yalnız `CostModel`/`MarketView` farkı (06) |

**Tasarım ↔ mevcut kod çakışmaları ve çözümleri (mentor kararı gerekebilir):**

1. **Hedef çıkışı (§2.6 vs `strateji-spec` §5.4).** Tasarım §2.6 R1 hedefini borsada `TAKE_PROFIT_MARKET` olarak kurmayı söyler; `strateji-spec` §5.4 ve `TraderV1.custom_exit` hedefi **kapanmış barın high/low'u** ile değerlendirip bir sonraki adımda piyasa çıkışı verir ("v1 sadeliği; backtest ve canlı aynı"). İkisi davranışça farklıdır (bar içi tetik vs bar kapanışı) ve çapraz doğrulama (§4.2 düzey C) freqtrade kuralını ister. **Faz A kararı (MENTOR ONAYLADI, 16 Kasım 2026; tasarım §2.6 düzeltildi):** `target_mode="bar_close"` (tek geçerli değer; `place_target` Broker arayüzünde ve PaperBroker'da vardır ama motor çağırmaz). Borsada hedef emri strateji davranışını değiştirir; Faz B/sonrası için ayrı strateji-spec revizyonu ve mentor onayı gerekir.
2. **Kapı sırası.** Tasarım §2.2: `params_ok → ledger → stale → kill → tek karar → veto → check_entry`. TraderV1: `_gate`(trigger_tf, params_ok, ledger) → stale → bar_final → veto → risk. Burada **TraderV1 sırası** korunur (kill ve `entries_blocked_reason` ledger kapısının hemen arkasına, `stale`'den önce eklenir; "tek karar" kontrolü en başa alınır çünkü kayıt yazmaz). Gerekçe: aynı mumda ikinci kez kayıt/log üretmemek.
3. **Ledger `skip_reason` sözlüğü** (`stop_width, rr_below_min, veto_blocked, veto_missing, veto_stale, risk_denied, entry_gate_closed, order_failed, other`) `stale_data`, `kill`, `rules_missing`, `order_unknown` gibi motor kodlarını içermez. Eşleme §4.2: bu kodlar `entry_gate_closed` (kapı) ya da `other` (veri) olarak yazılır, gerçek kod `veto_reason` alanında `gate:<kod>` biçimiyle taşınır (`not_evaluated` kararlarında serbest metin geçerlidir).
4. **`Ledger.find_unledgered_trades(freqtrade_open_trade_ids)`:** parametre adı freqtrade'e özgüdür; engine **konumsal** çağırır (`ledger.find_unledgered_trades(ids)`), yeniden adlandırma ayrı iştir (§4.3 madde 5).
5. **`health.ApiProbe`** freqtrade API alanları (`ping_ok`, `last_process_at`, `last_candle_open`, `open_trade_ids`, `dry_run`) içerir. `status.json` aynı bilgileri taşır (§8) ve `health_run.py` uyarlaması (ayrı iş; `health.evaluate` değişmez) bunlardan `ApiProbe` kurar.
6. **`bars_held` birimi** 15 dakikadır (ledger), zaman durdurma sayacı tetik tf barıdır (04 §9).
7. **`veto.json.pairs_from`** `config/base.json`'u gösterir; §4.3'te `base.json` silinecektir. Engine yapılandırması `config/engine.base.json:pairs` taşır; `pairs_from` yeniden işaretlenmesi silme adımının parçasıdır (veto kodu `dosya:nokta.yolu` serbest olduğundan kod değişmez).
8. **`pyproject.toml`** yalnız `pandas`, `numpy` içeriyor; `pyarrow`, `requests` eklenmesi 08'dedir.
9. **`ledger.Ledger` `clock` parametresi** "yalnızca test içindir" der; backtest için `SimClock.now` geçmek `strateji-spec` §6 ile aynı kullanımdır (ve `bar_close_ts ≤ now+5 sn` denetimi için **zorunludur**).

## 2. DOSYA SAHİPLİĞİ

Bu birim yalnızca şunlara dokunur:

- `src/trader_engine/strategy_runner.py`, `gates.py`, `engine.py`, `reconcile.py`, `killswitch.py`, `status.py`, `cli.py`, `__main__.py`
- `tests/engine/test_engine_strategy_runner_spec.py`, `test_engine_gates_spec.py`, `test_engine_engine_spec.py`, `test_engine_reconcile_spec.py`, `test_engine_killswitch_status_spec.py` (bağımsız test ajanı); `test_engine_runner_impl_smoke.py` (gerçekleme ajanı)

Dokunulmaz: tüm `trader_core`, `02`/`01`/`03`/`04`/`06`/`07` dosyaları. `backtest.py` ve `metrics.py` (06), `fileio.py` (07), `marketdata/*` (01). `scripts/health_run.py` uyarlaması bu işin **dışındadır** (ayrı iş; status.json sözleşmesi §8'de verilir).

`cli.py` alt komutlarından `backtest` `trader_engine.backtest.main(argv)`'ı, `feed` `trader_engine.marketdata.feed`'i, `rules-snapshot` 01'in işlevini **çağırır** (ince sarmalayıcı; mantık orada). `cli.py` içe aktarma anında ağır modül yüklemez (alt komut içinde tembel import).

## 3. `strategy_runner.py`

```python
@dataclass(frozen=True)
class SignalRow:                          # son kapanmış tetik barının sinyal satırı
    pair: str; bar_open_ts: datetime; bar_close_ts: datetime
    signal: bool; setup: str | None; side: str | None; skip_reason: str | None
    planned_entry: float; planned_stop: float; planned_target: float | None   # NaN -> None dönüşümü yapılır
    rr: float | None; stop_dist_atr: float | None
    atr_tf: float | None; atr_4h: float | None; atr_ratio: float | None
    regime: str; rh: float | None; rl: float | None; rh_touches: int; rl_touches: int
    ema_value: float | None; body_ratio: float | None; wick_ratio: float | None; edge_dist_atr: float | None
    pullback_ema: int; reasons: str
    param_version_id: int

@dataclass(frozen=True)
class SignalFrame:
    pair: str; status: Literal["ok","no_history","data_gap","error"]; detail: str | None
    last: SignalRow | None
    table: pd.DataFrame | None            # SIGNAL_COLUMNS + open/high/low/close; indeks = bar AÇILIŞI (UTC)

class SignalSource(Protocol):
    def frame(self, pair: str, D: datetime, params: SignalParams, version_id: int) -> SignalFrame
    def exit_context(self, pair: str, pos: Position, D: datetime) -> ExitContext | None
        # ok kareden E..son bar dilimi; frame status != "ok" ise None DEĞİL, çağıran 'veri yok' dalına gider (§6.3)

class WindowedSignalSource:
    def __init__(self, view: MarketView, *, strict: bool = False)        # strict=True: hatalar yayılır (backtest/test)
```

### 3.1 `WindowedSignalSource.frame` (TraderV1.`populate_indicators` karşılığı; referans uygulama)

1. `tf = params.trigger_tf`; `trig = view.bars(pair, tf, D, WINDOW_TRIGGER[tf])`, `h4 = view.bars(pair, "4h", D, WINDOW_4H)`. (`until=D` zorunlu; D'den sonra bar yok.)
2. Kontroller (sırayla; ihlal → `SignalFrame(status=…, last=None)` ve `strict` değilse sayaç+log): `len(trig) < STARTUP_BARS[tf]` ya da `len(h4) < STARTUP_BARS_4H` → `no_history`; son tetik barının açılışı `≠ D − tf` → `data_gap` (`detail="trigger_bar_missing"`); `view.contiguous_tail(pair, tf, D) < 20` ya da `contiguous_tail(pair, "4h", D) < 150` → `data_gap` (`detail="hole"`).
3. `reg = regime.classify_series(h4[["open","high","low","close"]], params.regime_params())`; `aligned = regime.align_to_base(reg, trig.index, 4)`; `sig = signals.compute_signals(trig[["open","high","low","close"]], aligned, params)`. `table = sig.join(trig[ohlc])`. `last` = son satır → `SignalRow` (NaN → `None`; `param_version_id = version_id`).
4. Hata (herhangi bir istisna): `strict` ise yayılır; değilse `SignalFrame(status="error")`, `callback_errors += 1`, `CRITICAL` log → **o çift için giriş yok** (TraderV1 `populate_indicators` hata kolu). Çıkışlar etkilenmez (§6.3).
5. Aynı `(pair, D, version_id)` için sonuç bellek içinde **tek tur** önbelleklenir (aynı karar adımında girişler ve çıkışlar tek hesaplamayı paylaşır).
6. `exit_context(pair, pos, D)`: `table`'dan `index ≥ pos.entry_bar_open` dilimi → `ExitContext(highs, lows, atrs=atr_tf, regime_last=table.regime.iloc[-1], last_close=table.close.iloc[-1], n_closed=len(dilim))`. `pos.entry_bar_open` yoksa/`table` yoksa `None` (04 `evaluate_exit` `force_exit` verir **yalnız** pozisyon verisi eksikse; veri boşluğunda motor bu yola girmez, §6.3).

**Geçmiş uzunluğu bağımlılığı (açık nokta):** EMA/ATR özyinelemeli (tohum ilk gözlem; `indicators.py`); 4h EMA100 için 300 bar sonrası tohum etkisi ≈ `0.98^300 ≈ 0.2 %` olduğundan **pencere uzunluğu** (`WINDOW_4H = 1500`) paper ile backtest (tüm geçmiş) arasında sınırda kararları değiştirebilir (`0.98^1500 ≈ 1e-13`, ihmal edilir). Kabul: paper ↔ backtest eşitlik testi 06'da `WindowedSignalSource` ile `PrecomputedSignalSource` farkını gerçek veride ölçer; ayrık sütunlar (`signal, setup, side, skip_reason, regime`) **eşit**, sürekli sütunlar `|Δ| ≤ 1e-9·max(1,|x|)` olmalıdır; aksi açıklanamayan fark = hata.

## 4. `gates.py` — giriş kapısı

```python
class VetoSource(Protocol):
    def begin_step(self, now: datetime) -> None            # dosya burada bir kez okunur
    def lookup(self, pair: str, side: str, now: datetime) -> veto.VetoLookup

class FileVeto:                                            # paper/canlı; veto_mode="required"
    def __init__(self, vcfg: veto.VetoConfig, env: Mapping[str,str])   # key = env[vcfg.hmac_key_env]; yoksa key_missing -> lookup missing
class NoVeto:                                              # yalnız backtest; veto_mode="off"
    # lookup -> VetoLookup("allowed", "not_evaluated:backtest", False); begin_step no-op

@dataclass(frozen=True)
class EntryOutcome:
    action: Literal["enter","skip","ignore"]
    event: L.DecisionEvent | None          # skip/enter için yazılacak karar
    size: K.SizeResult | None
    leverage: int | None
    code: str                              # ayrıntılı kod (günlük/sayaç)
    mandatory_record: bool                 # enter: True (yazılamazsa giriş yok); skip: best-effort

class EntryGate:
    def __init__(self, cfg: EngineConfig, ledger: L.Ledger, state: StateStore, kill: Killswitch,
                 veto: VetoSource, clock: Clock, broker: Broker, rules_fn: Callable[[str], SymbolRules],
                 entry_ref_fn: Callable[[str, datetime, SignalRow], float] | None = None)
    def pre(self, D: datetime, tf: str, params_ok: bool, active_tf: str) -> GateVerdict       # çift-bağımsız kapılar, adım başına bir kez
    def decide(self, frame: SignalFrame, D: datetime, pre: GateVerdict, active_version: int) -> EntryOutcome
```
`build_decision_event(row: SignalRow, tf: str, **override) -> L.DecisionEvent` (TraderV1 `_event`/`_features` birebir): `bar_close_ts = row.bar_close_ts`; `rh`/`rl` yalnız `regime=="range"`; `features` = `atr_tf, stop_dist_atr, atr_4h` + (T1: `pullback_ema, ema_value, body_ratio` | R1: `wick_ratio, rr, edge_dist_atr`) + `rh_touches, rl_touches`; yalnız sonlu değerler (`pullback_ema`, `*_touches` `int`, diğerleri `float`); varsayılanlar `veto_status="not_evaluated"`, `risk_allowed=None`, `final_action="skipped"`, `size_*=None`, `leverage=None`.

### 4.1 Kapı zinciri (`decide`; ilk eşleşen sonuç)

Her satırda "kayıt" ledger `record_decision`'dır; **skip** kayıtları best-effort (`LedgerError` yutulur, log), **entered** kaydı zorunludur.

| # | Koşul | Sonuç | `skip_reason` | `veto_status` / diğer alanlar |
|---|---|---|---|---|
| 0 | `frame.status != "ok"` ya da `last is None` | `ignore` (log; sayaç `data_gap`/`no_history`/`errors`) | — | kayıt yok |
| 1 | `row.signal == False`: `setup` dolu ve `skip_reason ∈ {stop_width, rr_below_min}` ve `record_filtered_candidates` ve `param_version_id ≥ 1` | `skip` (kayıt) | `row.skip_reason` | `not_evaluated`, `risk_allowed=None`, `veto_reason=None` |
| 1b | `row.signal == False`, diğer | `ignore` | — | kayıt yok |
| 2 | `state.is_decided(pair, D)` | `ignore` | — | kayıt yok (mum başına tek karar) |
| 3 | çiftte açık/bekleyen pozisyon (`state.position_for_pair`) | `ignore` (log) | — | kayıt yok (freqtrade aynı çiftte giriş denemez; `check_entry` kural 5 yine savunma) |
| 4 | `not params_ok` (`ledger.get_active_params()` hata) ya da `active_tf != engine tetik tf` | `skip`, `mark_decided` | `entry_gate_closed` | `not_evaluated`, `veto_reason="gate:params_unavailable"` / `"gate:trigger_tf_changed"` |
| 5 | `ledger.entries_allowed().ok == False` | `skip`, `mark_decided` | `entry_gate_closed` | `veto_reason="gate:<health.code>"` (`degraded`, `spool_pending`, `schema`, `no_active_params`, `unledgered_trades`) |
| 6 | `state.kv_get("entries_blocked_reason")` dolu | `skip`, `mark_decided` | `entry_gate_closed` | `veto_reason="gate:<neden>"` (`order_unknown`, `exit_unknown`, `stop_failed`, `reconcile_unknown_position`, `day_start_missing`) |
| 7 | kill etkin (`kill.active()`) | `skip`, `mark_decided` | `entry_gate_closed` | `veto_reason="gate:kill"` |
| 8 | **bayat:** `clock.now() − D > stale_factor × tf` | `skip`, `mark_decided` | `other` | `veto_reason="gate:stale_data"` |
| 9 | `rules_fn(pair)` `DataError` | `skip`, `mark_decided` | `other` | `veto_reason="gate:rules_missing"` |
| 10 | `veto.lookup(pair, side, now).blocks` | `skip`, `mark_decided` | `f"veto_{lookup.status}"` | `veto_status=lookup.status` (`blocked`/`missing`/`stale`), `veto_reason=lookup.reason` |
| 11 | `risk.check_entry(account_state, candidate, LOCKED_CFG)` `allowed == False` | `skip`, `mark_decided` | `risk_denied` | `veto_status="allowed"`, `veto_reason=lookup.reason`, `risk_allowed=False`, `risk_reason=dec.reason` |
| 12 | hepsi geçti | `enter` | `None` | `veto_status="allowed"`, `veto_reason=lookup.reason`, `risk_allowed=True`, `risk_reason=dec.reason`, `size_qty/notional/margin/risk_amount`, `leverage` |

Notlar:
- **Sıra: kurulum süzgeçleri (1) → … → veto (10) → risk (11)** (defter-spec ve TraderV1 ile aynı; "veto yalnızca girişi azaltabilir").
- `NoVeto` (backtest) `lookup.reason="not_evaluated:backtest"`, `status="allowed"` döner; ledger `entered` kuralı (`veto allowed`) bu sayede sağlanır (TraderV1 stub çözümünün karşılığı).
- Satır 4–9'da `row.signal == True` ve `setup`/`side` dolu olduğundan `DecisionEvent` kurulabilir; `param_version_id` `row`'dan gelir (`ledger` `param_version_id ≥ 1` şartı; `< 1` ise kayıt yazılmaz, `ignore`).
- **Adaya özgü kayıt (satır 4–9) yalnız `signal == True` satırlar için** yazılır; bayat veri/kill/kapı kapalıyken her çift için gürültü kaydı üretilmez.
- `veto.lookup` `blocks=False` yalnız taze belgede süresi dolmamış `allow` için döner (veto-spec); başka her şey `skip`.

### 4.2 Hesap durumu ve aday (TraderV1 `_account_state`, `_risk`)

`AccountState(equity, day_start_equity, open_positions)`:
- `equity = broker.account().equity` (paper: `wallet + unrealized`, mark ile).
- `day_start_equity = state.kv_get("day_start:<UTC YYYY-MM-DD>")` = o UTC gününün **ilk işlenen adımından önceki gerçekleşmiş cüzdan** (`Engine.ensure_day_start(ts)`, §6.2). Değer yoksa: `kv["initialized_at"]` bugünden önce ise (state var ama o günün anlık görüntüsü kayıp) → `entries_blocked_reason="day_start_missing"` (kapı 6) ve `ensure_day_start` cüzdanı o güne yazar (yarın açılır); taze kurulumda (`initialized_at` bugün) `wallet_start` kullanılır. Not: TraderV1 formülü (`cüzdan − bugün kapanan işlemlerin kâr/zararı`) ile **tanım olarak aynıdır**; farklı olan, açık pozisyonun funding'inin gün içinde cüzdana işlenmesidir (freqtrade işlem kapanınca işler) — bu mikro fark çapraz doğrulamada "gün başı tanımı" sınıfıdır.
- `open_positions = [OpenPosition(p.pair, p.side, p.risk_amount, p.margin) for p in state.open_positions()]` — `opening`, `open`, `closing` **hepsi** (aynı karar adımında ilk girişin riski ikinci çifte rezerve görünür; çıkış emri verilmiş ama dolmamış pozisyon da sayılır: tutucu).

`Candidate(pair, side, entry=entry_ref, stop=row.planned_stop, leverage=lev, qty_step=rules.step, min_notional=rules.min_notional)`:
- `lev = int(max(1, LOCKED_CFG.min_leverage))` (= 3; TraderV1 `leverage()` ile aynı kural).
- `entry_ref`: native/paper'da `row.planned_entry` (= tetik barı kapanışı = son 1 dk last kapanışı; fark yok). Uyum kipinde `entry_ref_fn` (06) sonraki adım **açılışını** verir (freqtrade `current_rate`); bu hile yalnız `fill_model="legacy_compat"` backtest'inde vardır, paper/canlıda `entry_ref_fn=None`.

## 5. `engine.py`

```python
@dataclass(frozen=True)
class RecoveryReport: replayed_minutes: int; replayed_decisions: int; unresolved_orders: int; reconcile: ReconcileReport

@dataclass(frozen=True)
class RunSummary: steps: int; decisions: int; trades_opened: int; trades_closed: int; open_at_end: tuple[int, ...]; counters: dict

class Engine:
    def __init__(self, cfg: EngineConfig, *, clock: Clock, view: MarketView, broker: Broker, ledger: L.Ledger,
                 state: StateStore, signals: SignalSource, veto: VetoSource, kill: Killswitch,
                 status: StatusWriter | None, orders: OrderManager | None = None,
                 entry_ref_fn=None, strict: bool = False)
    def start(self) -> RecoveryReport
    def advance_to(self, now: datetime) -> int                 # canlı/paper: now'a kadar kapanmış dakikaları ve karar adımlarını işler
    def run_forever(self) -> None                              # while: advance_to(clock.now()); reconcile; status; clock.sleep(cfg.loop_sleep_s)
    def run_range(self, start: datetime, end: datetime) -> RunSummary    # backtest sürücüsü (span tabanlı, §5.4)
    def process_step(self, step: MinuteStep) -> None           # §5.2
    def decision_step(self, D: datetime) -> None               # §5.3
    def ensure_day_start(self, ts: datetime) -> None
    def shutdown(self, reason: str) -> None
    # gözlem: counters(), summary()

def build_engine(cfg: EngineConfig, *, clock: Clock | None = None, view: MarketView | None = None,
                 broker: Broker | None = None, env: Mapping[str,str] | None = None) -> Engine
        # paper: StoreSource(cfg.market_db) + PaperBroker + SystemClock + FileVeto + gerçek ledger/state; backtest sürücüsü (06) kendi bileşenleriyle çağırır
```

### 5.1 Başlatma (`start`)

1. Twin ise `clock.sleep(cfg.start_delay_s)`.
2. `StateStore` açılır/kilitlenir (04); `integrity_check`; `kv["engine_version"]`/`trigger_tf` doğrulanır.
3. Defter açılır (`L.open_ledger(cfg.ledger_path, cfg.bot, create=True, clock=<paper: None, backtest: clock.now>)`). `ledger.drain_spool()`; `state.drain_outbox(ledger)`.
4. Paper broker: `state.kv_get("broker_snapshot")` varsa `broker.restore(...)`; yoksa taze (`wallet_start`). `broker.prepare(pair, lev)` her çift için (idempotent).
5. `orders.resolve_unresolved()` (04 §4.2).
6. **Mutabakat** (§7) ilk kez çalışır; `ReconcileReport.fatal` ise motor **girişleri kapalı** başlar (`entries_blocked_reason`), çıkışlar çalışır.
7. İmleçler: `cursors(*, "minute")` yoksa (ilk kurulum) son kapanmış dakikaya ayarlanır, geçmiş oynatılmaz; varsa **oynatma** (§5.5).
8. Boş etkin parametre (`ledger.get_active_params()` hatası): motor başlar ama `params_ok=False` (kapı 4) — otomatik `init_params` **yapılmaz**; `python -m trader_engine init-ledger --bot X` açık işlemdir (§9).

### 5.2 `process_step(step)` — bir dakika (ya da kaba kipte 15 dk) adımı

Girdi `step.ts` = adım barı açılışı, `end = ts + step_s`. Tüm gövde **tek** `with state.tx():` (simüle broker); `Clock` backtest'te `SimClock.set_time(end)`, canlıda gerçek saat.

1. `ensure_day_start(ts)`.
2. `broker.advance(step.bars, "fills")`; `ev = broker.poll(now)`; `handle_events(ev, step)`:
   - `fill` (giriş): 04 `apply_entry_fill` (+ `update_excursion` adım barıyla), `outbox_add("entry", …)`, **dolum sonrası risk doğrulaması** (04 §5.2) → ihlalse çıkış; değilse `place_initial_stop`.
   - `fill` (çıkış/`stop`/`target`/`liquidation`): `apply_exit_fill`, `outbox_add("exit", …)`, `cancel_resting`, pozisyon `closed`.
   - `funding`: `apply_funding` (pozisyon `funding_paid` birikir).
   - `order_rejected`/`order_canceled`: giriş reddi → pozisyon `closed` (hiç açılmadı), ledger karar düzeltmesi `order_failed` (supersedes) **best-effort**; stop reddi → 04 §5.2.
3. `broker.advance(step.bars, "triggers")`; `ev = broker.poll(now)`; `handle_events`.
4. Hâlâ açık her pozisyon için (adım barı olan çiftlerde): `update_excursion(pos, bar)` (giriş/çıkış adımında zaten uygulandıysa çift sayılmaz: `update_excursion` genişletme olduğundan idempotenttir).
5. İmleçler: her çift `set_cursor(pair, "minute", ts)`; `state.kv_set("broker_snapshot", json(broker.snapshot()))` (paper). Commit.
6. Tx dışı: `state.drain_outbox(ledger)` (başarısızlık adımı geri almaz; ledger kendi spool/degraded kapısını yönetir).
7. `end` tetik tf'nin kapanışıysa (`bars.is_tf_close(end, trigger_tf)`) çağıran `decision_step(end)` çağırır (canlıda `advance_to`, backtest'te `run_range` sürücüsü).

### 5.3 `decision_step(D)`

Tek `with state.tx():` (simüle broker).
1. **Parametre yenile:** `ap = ledger.get_active_params()`; `activation_id` değiştiyse `SignalParams.from_mapping(ap.params)` kurulur; hata → `params_ok=False` (girişler kapalı, kapı 4; açık pozisyonlar dondurulmuş parametreleriyle sürer). `ap.params["trigger_tf"] != engine tf` → `trigger_tf_changed` (girişler kapalı, `CRITICAL`; yeniden başlatma gerekir).
2. `veto.begin_step(now)` (dosya tek kez okunur).
3. **Çerçeveler:** her çift için `signals.frame(pair, D, params, ap.version_id)`.
4. **Çıkışlar (kapısız):** `state.open_positions()` içinde `status == "open"` her pozisyon için (çift sırasıyla):
   - Çerçeve `ok` değilse: serbest çıkışlar bu bar için **atlanır** (§6.3); koruyucu stop borsada/PaperBroker'da duruyor. Sayaç `exit_data_gap`.
   - Aksi `ctx = signals.exit_context(...)`; `dec = evaluate_exit(pos, ctx)`:
     - `exit` → `orders.submit_exit(pos, dec.reason, D)`; pozisyon `closing`; `exit_reason` pozisyona yazılır (dolumda 04 §5.3 kullanır).
     - `stop_update` → `orders.replace_stop(pos, dec.new_stop)`; `would_trigger` notu gelirse `trail_stop` piyasa çıkışı verilir.
     - `none` → hiçbir şey.
5. **Girişler:** `pre = gate.pre(D, tf, params_ok, ap.params["trigger_tf"])`; `cfg.pairs` sırasıyla her çift için `out = gate.decide(frame, D, pre, ap.version_id)`:
   - `ignore` → devam.
   - `skip` → `ledger.record_decision(out.event)` (best-effort) ve `state.mark_decided(pair, D, "skipped:" + out.code)`.
   - `enter` → `trade_id = state.next_trade_id()`; `did = ledger.record_decision(out.event)` (**zorunlu**; `LedgerError`/herhangi bir istisna → giriş yok, `CRITICAL`, `mark_decided` **yazılmaz** (yeniden başlatmada aynı bar tekrar denenebilir; içerik farklıysa `LedgerConflictError` → giriş yok, TraderV1 ile aynı)); başarılıysa `Position(status="opening", …)` ve `Intent` kurulur: `insert_position` + `mark_decided(pair, D, "entered")` aynı tx; `orders.submit_entry(intent, trade_id)`. Sonuç `failed`/`rejected` ise pozisyon silinir/`closed`, `record_decision(supersedes_id=did, final_action="skipped", skip_reason="order_failed")` **best-effort**.
6. `state.set_cursor(pair, "decision", D)` (her çift); `kv["broker_snapshot"]`; commit; `outbox` boşalt; `status.write()`.

**Pozisyon dondurulmuş alanlar** (giriş anında, TraderV1 `_on_entry_fill` `data` sözlüğü): `initial_stop = row.planned_stop`, `planned_target = row.planned_target`, `rh/rl`, `setup`, `trail_atr = params.trail_atr`, `param_version_id`, `trigger_tf`, `risk_amount = size.risk_amount`, `decision_id = did`, `signal_bar_close_ts = row.bar_close_ts`.

### 5.4 `run_range(start, end)` — backtest ve çevrimdışı sürücü

Span tabanlı (flat optimizasyonu): `D_k` = `(start, end]` içindeki tetik tf kapanışları. Her `D_k` için: (a) `view.minute_steps(active_pairs, cursor, D_k)` ile **yalnız** açık/bekleyen emri olan çiftlerin adımları `process_step` edilir (aktif çift yoksa adım atlanır; flat dönemde cüzdan değişmez, funding yok); (b) `SimClock.set_time(D_k)`; (c) `decision_step(D_k)`. Aktif küme `decision_step` sonrası belirlenir (girişler yeni çift ekler; çıkışlar `closed` olana dek tutar). `end` sonunda açık pozisyonlar **kapatılmaz**, `RunSummary.open_at_end` listelenir. Bu optimizasyonun tam adım adım çalışmayla **eşdeğerliği** testle kanıtlanır (06): aynı veri, `active_only=False` ile tüm çiftlerin her dakikası işlenir, ledger eşit olmalı.

### 5.5 `advance_to(now)` (canlı) ve yeniden oynatma

```
horizon = son kapanmış dakika sınırı: tüm çiftlerde o dakika barı varsa ya da now ≥ dakika_kapanış + cfg.minute_wait_s
cursor  = en küçük cursors(*,"minute")
for ts in dakikalar (cursor, horizon):                 # sırayla
    process_step(step(ts))
    if is_tf_close(ts+60s, trigger_tf) and son karar imleci < ts+60s:
        bekle: tüm çiftlerin tetik barı store'da ya da now ≥ D + cfg.bar_wait_s   (aksi dön, bir sonraki döngüde devam)
        decision_step(D)
```
- Karar adımı `D` için **dakikalar `< D` işlendikten sonra, `≥ D` işlenmeden önce** çalışır (emirler D'deki adımda dolsun diye).
- **Yeniden başlatma oynatması:** imleç → `horizon` arasındaki **tüm** dakikalar ve tf kapanışları sırayla işlenir. Oynatılan karar adımlarında girişler `stale` kapısıyla (satır 8) kendiliğinden engellenir; çıkışlar o anın verisiyle `until=D` hesaplanır (deterministik). Kaçan stop/funding PaperBroker'da aynı kodla yakalanır.
- Saat geri giderse (ardışık iki `clock.now()` negatif fark) → `ClockError`, adım işlenmez, `entries_blocked_reason="clock_skew"`.
- Feed/veri bayatsa dakika adımı ilerlemez (horizon geride kalır); girişler `stale_data` ile durur; stoplar PaperBroker'da son bilinen veriyle beklemede (feed dönünce oynatılır).

## 6. Fail-closed kuralları

### 6.1 Genel
- Her çift için hata o çifte özgüdür (`SignalFrame.status="error"`); motor çökmez, döngü sürer. Beklenmeyen istisna `process_step`/`decision_step` içinde `state.tx` geri alınır, `callback_errors` artar, `CRITICAL`; ardışık 3 hata → girişler kapanır (`entries_blocked_reason="engine_errors"`), çıkış yolu denenmeye devam eder; 10 ardışık hata → süreç çıkış kodu 3 (systemd yeniden başlatır).
- `StateError` (kilit/disk): süreç **çıkar** (durumu yazamayan motor çalışmaz; paper stopları feed dönünce yeniden oynatılır).

### 6.2 Gün başı (`ensure_day_start(ts)`)
`date(ts)` ≠ `kv["day_start_date"]` ise: `kv["day_start:<yeni>"] = broker.account().wallet` ve `kv["day_start_date"] = yeni`. Her adımın başında çağrılır (funding/komisyon o adımda işlenmeden önce).

### 6.3 Çıkış güvenliği
- Çıkışlar `ledger`, `veto`, `kill`, `stale`, `entries_blocked_reason` kapılarına **bağlı değildir**.
- Veri boşluğunda (çerçeve `ok` değil) discretionary çıkışlar atlanır **ama** `evaluate_exit` her ok çerçevede tüm `E..son` barları yeniden değerlendirdiğinden kaçan `target`/`time_stop` bir sonraki ok çerçevede yakalanır; `force_exit` **yalnızca** pozisyon çıkış verisi (setup/initial_stop/entry_bar_open) eksikse verilir (TraderV1 aynı ayrım).
- Koruyucu stop her açık pozisyonda duruyor olmalıdır: mutabakat (§7) aksini bulursa kurar, kuramazsa kapatır.

## 7. `reconcile.py` — paper alt kümesi

```python
@dataclass(frozen=True)
class ReconcileReport: ok: bool; fatal: bool; actions: tuple[str, ...]; findings: tuple[str, ...]
class Reconciler:
    def __init__(self, cfg, broker, state, ledger, orders, clock)
    def run(self, now: datetime) -> ReconcileReport
```
Çalışma: başlangıçta, her karar adımında, canlı döngüde pozisyon açıkken `reconcile_open_s` (15 sn), değilken `reconcile_flat_s` (60 sn). Backtest'te yalnız başlangıçta ve sonda.

| Durum (paper) | Eylem |
|---|---|
| Broker'da pozisyon var, state'te kayıt yok | İşlem **yapma**; `entries_blocked_reason="reconcile_unknown_position"`; `CRITICAL`; `fatal` |
| State'te `open` pozisyon var, broker'da yok | Olay türetilemez (paper'da kuyruk state ile aynı tx) → `entries_blocked_reason="reconcile_state_orphan"`; `CRITICAL`; `fatal` (paper'da bu bir **hata** sayılır) |
| Pozisyon var, duran stop yok | `place_initial_stop`/`replace_stop` ile kur; olmazsa piyasada kapat |
| Pozisyon qty ≠ stop qty | Stop miktarını pozisyona eşitle (yeni stop + eski iptal), uyarı |
| Yetim reduceOnly emir (pozisyon yok) | İptal |
| `pending`/`unknown` emir | `orders.resolve_unresolved()` |
| Ledger'da açık işlem (`list_open_trades`) var, state'te yok | `entries_blocked_reason="reconcile_ledger_orphan"`; uyarı |
| State'te açık, ledger'da giriş yok (outbox boş değil) | `drain_outbox`; başarısızsa kapı `unledgered_trades` (defter kendi bayrağı) |
| `ledger.find_unledgered_trades([state açık trade_id'ler])` | Her çalışmada çağrılır (sonuç defter kapısını günceller, §1 madde 4) |

`entries_blocked_reason` temizleme: otomatik **yok**; mutabakat bir sonraki çalışmada nedeni artık görmüyorsa (`ok`) ve neden `reconcile_*` ya da `stop_failed`/`order_unknown`/`exit_unknown` ise temizler ve `INFO` yazar; `day_start_missing` UTC gün sonunda; `clock_skew` saat düzelince.

## 8. `killswitch.py` ve `status.py`

### 8.1 Kill
```python
class Killswitch:
    def __init__(self, path: str, clock: Clock)
    def active(self) -> bool                  # dosya var mı (içerik önemsiz); okuma hatası -> True (fail-closed)
    def info(self) -> dict | None             # {"at","by","reason"} serbest JSON; bozuksa {"raw": ...}
    def set(self, by: str, reason: str) -> None     # fileio.atomic_write_json (CLI `kill`)
    def clear(self) -> None
```
Engine davranışı: `kill.active()` ilk gözlemde `kv["kill_seen_at"]` yazılır; **her karar adımı ve her dakika adımı başında** denetlenir. Etkin iken: (1) tüm yeni girişler kapalı (kapı 7); (2) `open` her pozisyon için `submit_exit(pos, "force_exit")` (bir kez; `closing` olanlara dokunulmaz); (3) çıkış doldukça `cancel_resting`; (4) düz kalınca `status.kill_state="flat"`. Kill dosyası kalkınca girişler bir sonraki karar adımında yeniden açılır (`kill_seen_at` temizlenir). İdempotent: kill sürerken yeniden başlatma aynı sonucu verir. Dosya okunamazsa `active() = True`.

### 8.2 `status.json` (atomik; `fileio.atomic_write_json`)

```json
{"schema":"engine-status/1","bot":"learner","mode":"paper","pid":1234,"started_at":"...Z","loop_at":"...Z",
 "last_minute_ts":"...Z","last_decision_bar_close":"...Z","last_candle_open":"...Z","trigger_tf":"1h",
 "param_version_id":1,"entries_open":true,"gate":{"ok":true,"code":"ok"},"kill":false,"kill_state":null,
 "entries_blocked_reason":null,"dry_run":true,
 "wallet":1000.0,"equity":1000.0,"day_start_equity":1000.0,
 "open_positions":[{"trade_id":1,"pair":"BTC/USDT","side":"long","qty":6.369,"entry_price":100.02,"stop":98.0}],
 "open_trade_ids":[1],
 "counters":{"callback_errors":0,"data_gaps":0,"ledger_errors":0,"unknown_orders":0,"mark_fallbacks":0,"minute_gaps":0,"funding_missing":0,"exit_data_gap":0}}
```
`StatusWriter(path, clock, cfg)`: `write(engine)` döngüde en çok `loop_sleep_s` aralıkla; yazma hatası döngüyü bozmaz (`WARNING`). `last_candle_open` = son kapanmış tetik barı açılışı (veri kaynağından). `loop_at` her döngüde güncellenir (kalp atışı). `health_run` eşlemesi (ayrı iş): `ApiProbe(ping_ok = (şimdi − loop_at) ≤ 120 sn, last_process_at = loop_at, last_candle_open, open_trade_ids, dry_run)`. Ayrıca `fileio.heartbeat_write` ile `kalp_atisi.json` (başlangıç/önceki kesinti bilgisi; 07) aynı dizine yazılır.

## 9. `cli.py` / `__main__.py`

`python -m trader_engine <komut>`:

| Komut | İş | Çıkış kodu |
|---|---|---|
| `feed [--config]` | 01 `Feed.run_forever` | 0, 3 (tekrarlayan hata) |
| `run --bot <learner veya twin> [--config-dir config]` | `build_engine` + `start` + `run_forever` | 0, 3 |
| `init-ledger --bot X [--reason paper_start]` | Defter yoksa oluşturur, `init_params(DEFAULT_SIGNAL_PARAMS)`; `twin` için öğrenen defterinin **aynı** `params_hash`'i doğrulanır (uyuşmazlık → çıkış 4); var olan etkin parametreye dokunmaz | 0, 4 |
| `backtest …` | 06 | 06'da |
| `reconcile --bot X` | tek seferlik mutabakat raporu (salt okunur broker durumu) | 0, 5 (bulgu var) |
| `kill [--clear] [--by X] [--reason Y]` | `Killswitch.set/clear` | 0 |
| `rules-snapshot` | 01 işlevi: exchangeInfo → `rules` tablosu (+ `history_dir/rules.json`) | 0 |
| `smoke` | Faz B; "faz_b" mesajı | 2 |

## 10. Elle doğrulanabilir örnekler

1. **Giriş (örnek A, `D = 2026-12-01T09:00Z`, 1h, BTC/USDT long T1):** `planned_entry=100.00`, `planned_stop=98.00`; kapılar 0–10 geçti; `check_entry`: `equity=1000`, `day_start=1000`, açık pozisyon yok ⇒ `qty=6.369`, `notional=636.9`, `margin=212.3` (`size_position` çıktısı `212.29999999999998`), `risk_amount=13.999062`; likidasyon güvenliği: `|100−67.0667| = 32.93 ≥ 1.5×2` ✓. `DecisionEvent`: `final_action="entered"`, `veto_status="allowed"`, `veto_reason="ok:2026-12-01T08:50:03.120Z"`, `risk_allowed=True`, `size_qty=6.369`, `leverage=3`, `bar_close_ts=09:00Z`. Sıra: `record_decision` → state tx (`positions` `opening`, `decided`, `orders` `pending`) → `market_order`. 09:00 adımında dolum `100.02`; `place_initial_stop(98.00)`; ledger `TradeEntry(entry_price=100.02, qty=6.369, leverage=3, fee_entry=0.31851369)`.
2. **Aynı mum ikinci kez:** `decision_step(09:00Z)` yeniden çalışırsa (yeniden başlatma) `state.is_decided` ⇒ `ignore`; `decided` yazılmamış ama ledger'da karar varsa (çökme) ⇒ aynı içerikle idempotent id, farklı içerikle `LedgerConflictError` ⇒ giriş yok (TraderV1 ile aynı).
3. **Risk reddi (günlük bütçe):** `day_start=1000`, `equity=960` (bugünkü kayıp 40), açık risk 0, yeni risk 13.999 ⇒ `40 + 0 + 13.999 > 0.05×1000 = 50`? `53.999 > 50` ⇒ `check_entry` reddeder (`risk_reason` günlük bütçe) ⇒ `skip`, `skip_reason="risk_denied"`, `veto_status="allowed"`, `risk_allowed=False`.
4. **Veto engeli:** `lookup.status="blocked"`, `reason="funding asiri negatif"` ⇒ `skip_reason="veto_blocked"`, `veto_status="blocked"`, `risk_allowed=None`; `risk.check_entry` **çağrılmaz**.
5. **Bayat veri:** `D = 09:00Z`, `clock.now() = 10:30Z` (`1.5h > 1×1h`) ⇒ satır 8: `skip_reason="other"`, `veto_reason="gate:stale_data"`; aynı anda açık pozisyonun çıkış değerlendirmesi **yapılır**.
6. **Kill:** `shared/KILL` var ⇒ girişler `entry_gate_closed / gate:kill`; açık long `force_exit` piyasa çıkışı; ledger `exit_reason="force_exit"`.
7. **Çıkış önceliği (aynı adımda):** T1 long, `regime_last="trend_down"` ve iz-stop yükselişi birlikte ⇒ yalnız `regime_flip` çıkışı (stop güncellemesi **yapılmaz**).
8. **Çökme sonrası oynatma (1h tf):** (a) imleç `10:00Z`, `now=10:07Z` ⇒ dakikalar `10:01…10:06` işlenir, tf kapanışı olmadığından karar adımı yok. (b) imleç `10:58Z`, `now=11:03Z` ⇒ `10:59` dakikası işlenir, sonra `decision_step(11:00Z)` (bayat değil: `11:03 − 11:00 = 3 dk ≤ 1 sa`), ardından `11:00…11:02` dakikaları işlenir (D'de verilen emirler `11:00` adımında dolar). (c) imleç `10:58Z`, `now=13:05Z` ⇒ `11:00`, `12:00`, `13:00` karar adımları sırayla oynatılır; `11:00` ve `12:00` için girişler `stale_data` ile engellenir (çıkışlar o `D`'nin verisiyle değerlendirilir), `13:00` bayat değildir.
9. **Eş zamanlı iki giriş:** aynı karar adımında BTC ve ETH sinyali; BTC önce `enter` (risk 13.999, teminat 212.3) ⇒ ETH `check_entry` açık risk toplamını (`13.999 + yeni`) ve teminatı görür; `max_open_risk 60`, `max_same_dir_risk 40` içinde ⇒ ikisi de girer; üçüncü long için aynı yön riski `3×14 = 42 > 40` ⇒ `risk_denied`.

## 11. Kabul senaryoları (test ajanı için)

Kapı zinciri: §4.1 tablosunun **her satırı** için bir test (kayıt alanları ve `mark_decided` davranışı dahil); `entered` kaydı yazılamazsa emir yok; `LedgerConflictError` yolu; çıkış kapıdan bağımsızlığı (ledger `degraded`, veto yok, kill, bayat iken çıkış çalışır); karar adımı sırası (exit → stop_update → entry) ve aynı adımda rezerve risk; `FileVeto` bayat/imzasız/anahtarsız ⇒ giriş yok; `SignalFrame` durumları (`no_history`, `data_gap`, `error`; backtest `strict` yayılır); `WindowedSignalSource` ≡ doğrudan `compute_signals` (kesilmiş veriyle: aynı satır); `run_range` flat optimizasyonu ≡ tam adım adım (06 ile ortak); `process_step` iki aşama sırası (giriş dolumu → stop → aynı adımda tetik); yeniden başlatma oynatması (her adımda öldürme: dakika ortası, karar ortası, `orders.pending` sonrası — kod yolları `FaultPlan` ve state tx geri alma ile; sonuç kesintisiz çalışmayla **bit-bit aynı** ledger+state); tek karar anahtarı kalıcılığı; kill (set, idempotent yeniden başlatma, clear, okunamayan dosya ⇒ aktif); mutabakat tablosunun her satırı; `status.json` şeması ve atomikliği (yarım dosya okunmaz); `ensure_day_start` (gün sınırı, yeniden başlatma, `day_start_missing`); TraderV1 §2.8 eşleme tablosunun her satırı için "karşılık var" testi (eksik davranış listesi).

## 12. Belirsizlikler ve çözümleri

- **Giriş fiyatı referansı (`entry_ref`)** native'de `planned_entry`; gerçek dolum bir adım sonra olduğundan boyut dolum sonrası doğrulanır (04 §5.2). Fark ≤ 2 bp kayma + bir dakikalık hareket; hedef risk 1,4 % ile tavan 2 % arasında 0,6 puanlık tampon vardır.
- **Karar anı gecikmesi:** feed `grace_s=3` + yoklama; tipik karar `D + ~5 sn`. `stale_factor=1` ⇒ 1 tf tolerans (TraderV1 `_stale` ile eşdeğer).
- **Twin:** aynı süreç türü, farklı `--bot`; her zaman `PaperBroker`; gecikmeli başlar (`start_delay_s`). Ledger/state/status ayrı dosyalar; `market.sqlite` ortak salt okunur.
- **`minute_wait_s`** yeni yapılandırma alanıdır (varsayılan 20 sn; 02 `EngineConfig`).
