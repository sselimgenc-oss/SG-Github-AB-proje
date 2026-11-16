# TraderV1 bekleyen degisiklikler (defter sema 2: mfe_r / mae_r / bars_held)

`user_data/strategies/TraderV1.py` bir backtest calisirken degistirilmedi. Backtest bitince asagidaki degisiklik uygulanir. Defter tarafi (`ledger.py`, sema 2) hazirdir; `TradeExit`'in yeni alanlari varsayilan `None` oldugundan mevcut cagri da calismaya devam eder (yalnizca `bars_held` dolar, `mfe_r`/`mae_r` NULL kalir). Bkz. `defter-spec.md` 3.4.1.

## Degisiklik: `_on_exit_fill` icinde uc fiyatlari ver

Defter `mfe_r`, `mae_r`, `bars_held` degerlerini kendisi hesaplar; stratejinin vermesi gereken yalnizca ham uc fiyatlar ve mum dilimidir:

- long: `max_favorable_price` = islem suresince (entry_ts ile exit_ts ile kesisen mumlar) en yuksek `high`, `max_adverse_price` = en dusuk `low`.
- short: `max_favorable_price` = en dusuk `low`, `max_adverse_price` = en yuksek `high`.
- `excursion_tf`: ayrinti varsa `"1m"`, yoksa `"5m"`, yoksa `"15m"` (ilk bulunan; verinin kendisi hangi dilimdeyse o).
- Mum verisi alinamazsa uclusu birlikte `None` (islem yine kaydedilir).
- Defter dogrulamasi: long icin `max_favorable_price >= max(entry, exit)` ve `max_adverse_price <= min(entry, exit)` (short icin ters). Bunu saglamak icin uclar gerceklesen giris/cikis fiyatlariyla **genisletilir** (asagidaki `max`/`min`).

```python
_EXC_TFS = ("1m", "5m", "15m")   # modul sabiti (ince -> kalin)

def _excursion(self, pair, trade, entry_ts, exit_ts, entry_price, exit_price):
    """(max_favorable_price, max_adverse_price, tf) ya da (None, None, None)."""
    for tf in _EXC_TFS:
        try:
            df = self.dp.get_pair_dataframe(pair, tf)   # backtest: informative_pairs'e (pair, tf) eklenmeli
        except Exception:
            continue
        if df is None or len(df) == 0:
            continue
        step = pd.Timedelta(tf.replace("m", "min"))
        # mum acilis zamani 'date'; [entry_ts, exit_ts] ile kesisen mumlar
        m = df[(df["date"] + step > pd.Timestamp(entry_ts)) & (df["date"] <= pd.Timestamp(exit_ts))]
        if m.empty:
            continue
        hi, lo = float(m["high"].max()), float(m["low"].min())
        if trade.is_short:
            return min(lo, entry_price, exit_price), max(hi, entry_price, exit_price), tf
        return max(hi, entry_price, exit_price), min(lo, entry_price, exit_price), tf
    return None, None, None
```

`_on_exit_fill` icinde `L.TradeExit(...)` cagrisi:

```python
        entry_ts = _utc(trade.open_date_utc)          # dolum zamani (giris kaydindaki entry_ts ile ayni olmali)
        exit_ts = _utc(current_time)
        mfp, map_, etf = self._excursion(pair, trade, entry_ts, exit_ts,
                                         float(trade.open_rate), float(price))
        try:
            self._ledger.record_trade_exit(L.TradeExit(
                trade_id=trade.id, exit_ts=exit_ts, exit_price=float(price), exit_reason=reason,
                planned_exit=planned, fee_exit=float(fee), funding_paid=funding_paid,
                max_favorable_price=mfp, max_adverse_price=map_, excursion_tf=etf))
```

Notlar:

- `_excursion` kendi icinde istisnayi yutar (`None` doner); cikis kaydi asla engellenmemeli (spec 8.2).
- `entry_price` olarak `trade.open_rate` kullanilir; defterdeki `entry_price` (giris dolumunun `order.safe_price`) ile ayni olmasi gerekir. Farkli ise `self._ledger.get_trade(trade.id).entry_price` okunup o kullanilmali (genisletme `max`/`min` icin).
- Backtest'te 1m/5m verisi yoksa `informative_pairs()` icine `(pair, "1m")` eklenmeli ve 1m veri indirilmelidir; yoksa `15m` (sapma hafif abartilir, `excursion_tf="15m"` olarak kaydedilir) ya da `None`.
- `ledger.py` sema 2 oldugu icin mevcut sema 1 defter dosyalari bir kez `migrate=True` ile acilmalidir (`open_ledger(..., migrate=True)`, varsayilan salt-okunur degilse zaten `True`); `<db>.premigrate-v1` yedegi otomatik alinir. Bot durmusken yapin; ogrenen ve ikiz dosyalari ayni gun goc ettirin (spec 10.2).
