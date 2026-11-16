# Risk kilidi — arayüz ve kurallar (spesifikasyon)

Modül: `src/trader_core/risk.py` (saf Python, freqtrade'e bağımlı değil). Strateji bu modülü çağırır; bot ve ders servisi sınırları değiştiremez (sabitler kodda, `RiskConfig` varsayılanları; ders servisi bu dosyaya yazamaz).

## Sabitler (`RiskConfig`, frozen dataclass)
| Alan | Varsayılan | Anlam |
|---|---|---|
| `max_trade_risk` | 0.02 | İşlem başı gerçekleşen kayıp üst sınırı (özsermayeye oran) |
| `target_trade_risk` | 0.014 | Boyutlandırmada kullanılan hedef kayıp (komisyon+kayma dahil) |
| `fee_rate` | 0.0005 | Taraf başı komisyon (taker) |
| `slippage_rate` | 0.0005 | Taraf başı kayma varsayımı |
| `daily_max_loss` | 0.05 | Gün başı özsermayesine göre günlük zarar sınırı |
| `max_open_risk` | 0.06 | Açık işlemlerin toplam riski |
| `max_same_dir_risk` | 0.04 | Aynı yöndeki (long ya da short) toplam risk |
| `min_leverage` / `max_leverage` | 3 / 5 | İzin verilen kaldıraç aralığı (tam sayı) |
| `maint_margin_rate` | 0.004 | Likidasyon hesabı için bakım teminatı oranı |
| `liq_safety_factor` | 1.5 | Giriş–likidasyon mesafesi ≥ 1.5 × giriş–stop mesafesi olmalı |

`RiskConfig(...)` geçersiz değerlerle (negatif, target > max, min_leverage > max_leverage vb.) `ValueError` fırlatır.

## Fonksiyonlar
- `liquidation_price(entry: float, side: str, leverage: float, mmr: float) -> float`
  İzole teminat yaklaşığı: long `entry * (1 - 1/leverage + mmr)`, short `entry * (1 + 1/leverage - mmr)`.
- `loss_at_stop(qty, entry, stop, cfg) -> float`
  `qty*|entry-stop| + qty*entry*(fee+slip) + qty*stop*(fee+slip)` (her iki taraf maliyeti dahil).
- `size_position(equity, entry, stop, side, leverage, cfg) -> SizeResult`
  `SizeResult(qty, notional, margin, risk_amount)`; `risk_amount = loss_at_stop(qty,...)` ve `risk_amount <= target_trade_risk*equity` (kayan nokta toleransı 1e-9 göreli). `margin = notional/leverage`. `margin > equity` ise reddedilir.
- `check_entry(state: AccountState, cand: Candidate, cfg) -> Decision`
  `AccountState(equity, day_start_equity, open_positions: list[OpenPosition])`,
  `OpenPosition(pair, side, risk_amount)`, `Candidate(pair, side, entry, stop, leverage)`,
  `Decision(allowed: bool, reason: str, size: SizeResult | None)`.

## `check_entry` kuralları (sırayla; ilk ihlal `allowed=False` ve açıklayıcı `reason` döner)
1. Girdi geçersiz (NaN/inf/≤0 fiyat, equity ≤ 0, `side` "long"/"short" değil) → red.
2. Stop yanlış tarafta (long'da stop ≥ entry, short'ta stop ≤ entry) → red.
3. Kaldıraç aralık dışı → red.
4. Günlük zarar: `(equity - day_start_equity)/day_start_equity <= -daily_max_loss` → red ("günlük sınır").
5. Aynı çift için zaten açık pozisyon var → red.
6. Boyut hesaplanır (`size_position`); hata/ret → red.
7. Likidasyon güvenliği: `|entry - liq| < liq_safety_factor * |entry - stop|` → red.
8. Toplam açık risk: `sum(open risk) + yeni risk > max_open_risk*equity` → red.
9. Aynı yön riski: aynı yöndeki açık risk + yeni risk `> max_same_dir_risk*equity` → red.
10. Hepsi geçerse `allowed=True`, `size` dolu.

**Hata durumunda kapalı (fail-closed):** `check_entry` içinde beklenmeyen herhangi bir istisna `allowed=False, reason="iç hata: ..."` döner; asla istisna dışarı sızmaz ve asla izin vermez.
