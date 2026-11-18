# DD-11: sıfır fiyat/miktar dolumu (testnet olayı, 18 Kasım 2026) — belirtim

## Olay
Testnet motoru bir giriş emrinin yanıtında `status=FILLED` ama `avgPrice "0.00"` (ve/veya `executedQty "0"`) aldı. `BinanceFuturesBroker._settle` (`src/trader_engine/brokers/binance_futures.py` ~935–956) bunu tam dolum saydı ve `Fill(qty, 0.0)` üretti. Motor `_on_entry_fill` (`engine.py` ~1032–1064) pozisyonu `open` yaptı ve `outbox_add("entry", ...)` ile deftere giriş satırı kuyrukladı. Defter `entry_price ve qty > 0 olmali` (`ledger.py` ~1526) diye reddetti. `drain_outbox` ilk hatada durduğu için ardından gelen çıkış satırı da takıldı ("2 satir"), `outbox_stuck` engeli kalıcı oldu, testnet hiç işlem kaydedemedi. Takılı satırlar `state.sqlite` `ledger_outbox` tablosunda kaldığı için yeniden başlatmada da engel sürer.

## Düzeltmeler
**Z-1 Broker (`_settle` giriş dalı ve ~912 `OrderResult("filled")` öncesi).**
- `executedQty ≤ 0` → dolum yok sayılır, emir "pending" kalır (`_pending_market` içinde her yoklamada yeniden sorgulanır). Dolum olayı üretilmez.
- `avgPrice ≤ 0` → fiyat `cumQuote / executedQty`; o da ≤ 0 ise emrin `userTrades` kayıtlarından ağırlıklı ortalama (VWAP; `_try_close` ~1270/1336'daki yöntem). Hâlâ bilinmiyorsa "pending".
- Fiyatı ya da miktarı ≤ 0 veya sonlu olmayan bir `Fill` asla üretilmez.

**Z-2 Motor emniyet ağı (`_on_entry_fill`, işlem bloğundan önce).** `fill.price` ya da `fill.qty` ≤ 0 veya sonlu değilse: CRITICAL log, sayaç `bad_fill`, pozisyon `opening`'de bırakılır (mutabakat L2b benimseyebilir), outbox'a hiçbir şey eklenmez, `outbox_stuck` oluşmaz.

**Z-3 Diğer kuyruklama yolları.** `bp.entry_price` geri düşüşleri yalnız > 0 iken kullanılır: `reconcile_live.py` ~289 (`_late_fill`), ~341 (`_adopt_opening`), `engine.py` ~1712 (`_on_adopted_entry`; bugün yalnız `None` reddediliyor, 0 da reddedilmeli). Geçersizse benimseme/kuyruklama yapılmaz, sayaç + uyarı.

**Z-4 Kurtarma: outbox karantinası.** Yeni CLI alt komutu `outbox-quarantine` (`src/trader_engine/cli.py`): motor çalışmıyorken (kilit dosyası alınabiliyorsa) `ledger_outbox`'taki teslim edilemeyen satırları (defter doğrulama hatası veren) ayrı `ledger_outbox_quarantine` tablosuna (ya da `done=2` + gerekçe) taşır, gerekçe ve zaman damgasıyla; `--dry-run` varsayılan, `--apply` ile uygular; yalnız `LedgerValidationError` veren satırlar taşınır, geçerli satırlar dokunulmaz. Uygulandıktan sonra `outbox_stuck` engeli bir sonraki başarılı boşaltmada kendiliğinden kalkar. Karantinaya alınan her satır stdout'a özetlenir (pair, side, qty, price, client id).

## Tarafsızlık
Paper broker ve geri test yolu değişmez: altın testler (`tests/test_wp3_golden.py`, `tests/engine/test_risk_ladder_impl.py::test_t28_backtest_digest_unchanged`, `tests/engine/test_engine_compat_equity.py`) aynen geçer.

## Testler (bağımsız yazar)
| Kod | Davranış |
|---|---|
| Z-T1 | FILLED, avgPrice "0.00", geçerli cumQuote → dolum fiyatı cumQuote/executedQty. |
| Z-T2 | FILLED, avgPrice ve cumQuote 0 → userTrades VWAP; userTrades boşsa pending, dolum olayı yok; sonraki sorguda geçerli yanıt gelince dolum. |
| Z-T3 | FILLED, executedQty "0" → pending, dolum olayı yok. |
| Z-T4 | Motora fiyatı 0 ya da miktarı 0 olan dolum verilir → outbox satırı yok, `outbox_stuck` yok, pozisyon `opening`, `bad_fill` sayacı 1. |
| Z-T5 | Mutabakat: `bp.entry_price == 0` ve `avg_price` None → benimseme/kuyruklama yok. `_on_adopted_entry` fiyat 0 → reddedilir. |
| Z-T6 | `outbox-quarantine`: geçersiz giriş + arkasında geçerli çıkış satırı; `--dry-run` hiçbir şey değiştirmez; `--apply` yalnız geçersiz satırı taşır, sonra `drain_outbox` geçerli satırı… (geçerli çıkış satırı girişi olmadığı için defterde reddedilirse o da doğrulama hatasıdır ve taşınır). Sonuçta outbox boş, defter tutarlı, engel kalkar. Motor çalışırken (kilit tutulu) komut reddeder. |

## Mentor incelemesi (18 Kasım 2026)
Karar: KABUL (düzeltmelerle). Uygulanan düzeltmeler:
- **D1** Sıfır-dolum bekleme sayacı (`_zero_fill[cid]=(ilk_ts, n)`): `userTrades` sorgusu en fazla `poll_open_s`'de bir; ≥3 deneme VE ≥30 sn sonra emir `_pending_market`'ten düşer, `zero_fill_unresolved:{cid}` bulgusu + CRITICAL + giriş engeli. `order_rejected` basılmaz (gerçek pozisyon `_close_unopened` ile kapanmasın); periyodik saat eşitleme de serbest kalır.
- **D2** `register_position`: benimsenen pair'in bekleyen giriş kayıtları `_pending_market`'ten silinir (geç çözülen emir `_open_pairs/_last_pos/_pos_since`'i ezmesin).
- **D3** `_l3b`: `accepted` giriş satırı pencere dolunca sorgulanır; `filled` ise `_l3b_filled`; fiyat hâlâ bilinmiyorsa `opening_unpriced:{tid}` bulgusu + duraklatma.
- **D4** `outbox-quarantine`: `--dry-run`/`--apply` karşılıklı dışlayan; bozuk yük (KeyError/TypeError/ValueError) -> "hicbir sey tasinmadi", EXIT_ENGINE; `--apply`'da tek WARNING denetim satırı (sayı + outbox id'leri).
- **D5** `_recover_entry_price`: `ExchangeBan` için `_note_ban` çağrılır.
