# 11 — Testnet sonuçları (B0 + B7)

Kaynak: `trader/docs/motor/11-canli-broker.md` §11. Betik: `scripts/smoke_testnet.py` (rapor: `var-testnet/smoke/<zaman>/result.{json,md}`).
Durumlar: **GEÇTİ / KALDI / FARKLI** (+ `KISMI`, `BEKLEMEDE`, `GOZLEM`; bunlar GEÇTİ sayılmaz — T-12 hariç, o engelleyici değil).
Gerçek yanıtlar `tests/engine/fixtures/binance/testnet/<madde>_<ad>.json` altına (anahtar, imza, hesap kimliği silinerek) kaydedilir.

**Shadow başlangıç kapıları:** düzeltme turu 1–2 içeride; B8 testnet birim + ortam testleri var; **T-04, T-07, T-08 ve tam T-13 (GEÇTİ)** gerçek testnette kaydedilmiş.

## 1. Sonuç tablosu (doldurulacak)

| # | Madde | Adım | Durum | Ölçüm / not | Rapor dosyası | Tarih |
|---|---|---|---|---|---|---|
| T-01 | Koşullu emir ucu | `b0-t01` | | | | |
| T-02 | Hesap hazırlığı | `b0-t02` | | | | |
| T-03 | MARK_PRICE tetik | `b0-t03` | | alan doğrulandı; tetik anı gözlemi T-13'te | | |
| T-04 | İki stop | `b0-t04` | | iki stop kabul? gevşek stopun akıbeti | | |
| T-05 | reduceOnly | `b0-t05` | | (a), (b) betikte; (c), (d) elle | | |
| T-06 | Hemen tetiklenecek stop | `b0-t06` | | | | |
| T-07 | stop ↔ userTrades | `b0-t07` | | çocuk `clientOrderId` modu (same/auto); likidasyon sorgulanabilirliği testnette gözlenemez | | |
| T-08 | Kimlik / belirsizlik | `b0-t08` | | | | |
| T-09 | Ret kodları | `b0-t09` | | | | |
| T-10 | Piyasa emri yanıtı | `b0-t10` | | | | |
| T-11 | Hız başlıkları | `b0-t11` | | | | |
| T-12 | Funding (yalnız gözlem) | `b0-t12` | | engelleyici değil | | |
| T-13 | Tam yaşam döngüsü | `t13` | | mark ve son fiyat tetik anında; **GEÇTİ şart** | | |
| T-14 | Kısmi dolum | `t14` | | | | |
| T-15 | KILL (≥ 2 pozisyon) | `t15` | | `kill_oncesi_pozisyon` ≥ 2 değilse `KISMI` | | |
| T-16 | Duraklatma | `t16` | | | | |
| D-1…D-8 | Tatbikatlar | `d1`…`d8` | | D-4: mark/son fiyat kaydı | | |

## 2. Elle defter denetimleri (betik defteri okumaz)

Motor testnette çalışırken (`trader-engine@learner`) betik adımından hemen sonra, `trader/` dizininde çalıştırın. Defter: `var-testnet/learner/ledger.sqlite`; durum: `var-testnet/learner/state.sqlite`.

| Madde | Ne doğrulanır | Tam komut | Beklenen |
|---|---|---|---|
| T-13 | Çıkış kaydı ve nedeni | `sqlite3 var-testnet/learner/ledger.sqlite "SELECT trade_id, exit_reason, exit_price, fee_exit, realized_pnl FROM trade_exits WHERE supersedes_id IS NULL ORDER BY id DESC LIMIT 3;"` | son satır `exit_reason='trail_stop'` (iz süren stop tetiklendi) |
| T-13 | Girişe karşılık çıkış var, yetim giriş yok | `sqlite3 var-testnet/learner/ledger.sqlite "SELECT e.trade_id FROM trade_entries e LEFT JOIN trade_exits x ON x.trade_id=e.trade_id AND x.bot=e.bot AND x.supersedes_id IS NULL WHERE e.supersedes_id IS NULL AND x.id IS NULL;"` | boş (açık pozisyon yok) |
| T-13 / D-4 | Komisyon ve funding gerçek mi | `sqlite3 var-testnet/learner/ledger.sqlite "SELECT trade_id, fee_entry FROM trade_entries ORDER BY id DESC LIMIT 3;"` ve `sqlite3 var-testnet/learner/state.sqlite "SELECT k, v FROM kv WHERE k LIKE 'entry_fee_estimated:%';"` | gerçek komisyon; `entry_fee_estimated` yalnız benimsenen girişlerde |
| T-15 | KILL sonrası çıkış nedeni | `sqlite3 var-testnet/learner/ledger.sqlite "SELECT trade_id, exit_reason FROM trade_exits WHERE supersedes_id IS NULL ORDER BY id DESC LIMIT 4;"` | KILL ile kapananlarda `force_exit` |
| T-16 | Duraklatmada atlanan sinyal | `sqlite3 var-testnet/learner/ledger.sqlite "SELECT final_action, skip_reason FROM decision_events ORDER BY id DESC LIMIT 5;"` | duraklatma süresince `skipped` / `gate:paused` |
| D-4 | L3 çıkışı doğru neden/fiyat/komisyonla | `sqlite3 var-testnet/learner/ledger.sqlite "SELECT trade_id, exit_reason, exit_price, fee_exit FROM trade_exits WHERE supersedes_id IS NULL ORDER BY id DESC LIMIT 1;"` | neden `stop`/`trail_stop`; fiyat userTrades ile eşleşir; yetim emir yok (`b0-t…` raporunda `yetim=0`) |
| D-2/D-3/D-5 | Yeniden kurulan stop kaydı | `sqlite3 var-testnet/learner/state.sqlite "SELECT role, status, detail FROM orders ORDER BY created_ts DESC LIMIT 6;"` | stop satırı `accepted`; eski stop `canceled` |

Not: tablo/sütun adları değişirse komutlar `src/trader_core/ledger.py` ve `src/trader_engine/state.py` şemasına göre güncellenir; komutlar salt okuma (`SELECT`) olmalıdır.

## 3. FARKLI / KALDI kayıtları ve mentor kararları

(boş)
