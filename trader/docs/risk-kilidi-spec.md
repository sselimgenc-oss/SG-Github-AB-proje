# Risk kilidi — arayüz ve kurallar (spesifikasyon v2, 16 Kasım 2026)

v2 değişiklikleri: mentor incelemesi (A1–A6) ve kullanıcı kararları — pozisyon değeri en fazla bakiye kadar; günlük bütçe kuralı (bugünkü kayıp + açık risk + yeni risk ≤ %5).

Modül: `src/trader_core/risk.py` (saf Python, freqtrade'e bağımlı değil). Hata durumunda her zaman kapalı (fail-closed).

## Kilitli üst sınırlar (modül sabiti `HARD_LIMITS`, dict)
`max_trade_risk ≤ 0.02`, `target_trade_risk ≤ 0.014`, `daily_max_loss ≤ 0.05`, `max_open_risk ≤ 0.06`, `max_same_dir_risk ≤ 0.04`, `max_leverage ≤ 5`, `min_leverage ≥ 1`, `max_notional_ratio ≤ 1.0`.
`RiskConfig` bu sınırlardan daha gevşek bir değerle oluşturulursa `ValueError`. Daha sıkı değerler serbest. Modül ayrıca `LOCKED_CFG = RiskConfig()` sağlar; bot bunu kullanır.

## `RiskConfig` (frozen dataclass)
| Alan | Varsayılan | Anlam |
|---|---|---|
| `max_trade_risk` | 0.02 | İşlem başı gerçekleşen kayıp üst sınırı (özsermayeye oran) |
| `target_trade_risk` | 0.014 | Boyutlandırmada kullanılan hedef kayıp (komisyon+kayma dahil) |
| `fee_rate` | 0.0005 | Taraf başı komisyon |
| `slippage_rate` | 0.0005 | Taraf başı kayma varsayımı |
| `daily_max_loss` | 0.05 | Gün başı özsermayesine göre günlük zarar bütçesi |
| `max_open_risk` | 0.06 | Açık işlemlerin toplam riski |
| `max_same_dir_risk` | 0.04 | Aynı yöndeki toplam risk |
| `min_leverage` / `max_leverage` | 3 / 5 | Kaldıraç aralığı (tam sayı) |
| `maint_margin_rate` | 0.004 | Likidasyon yaklaşığı için bakım teminatı oranı |
| `liq_safety_factor` | 1.5 | Giriş–likidasyon mesafesi ≥ 1.5 × giriş–stop mesafesi |
| `max_notional_ratio` | 1.0 | Pozisyon değeri ≤ bu oran × özsermaye |

Geçersiz değerler (sonlu olmayan, negatif, target > max, min_leverage > max_leverage, mmr ≥ 1) veya `HARD_LIMITS` ihlali → `ValueError`.

## Sayı kabulü
Sayısal alanlar `int`/`float` veya `numbers.Real` (numpy dahil) olabilir; `float()` ile dönüştürülür. `bool`, `None`, metin, NaN, inf → geçersiz.

## Normalleştirme
- `side`: boşluk kırpılır, küçük harfe çevrilir; sonuç "long" veya "short" değilse geçersiz.
- Çift (pair): büyük harfe çevrilir, boşluk kırpılır, `:` sonrası (ör. `:USDT`) atılır. `"btc/usdt"` == `"BTC/USDT:USDT"`.

## Veri yapıları
- `OpenPosition(pair, side, risk_amount, margin)` — `risk_amount` ve `margin` sonlu ve ≥ 0 olmalı.
- `AccountState(equity, day_start_equity, open_positions=[])` — `equity` gerçekleşmemiş kâr/zarar dahil.
- `Candidate(pair, side, entry, stop, leverage, qty_step=None, min_notional=0.0)` — `qty_step` borsanın miktar adımı (None ise yuvarlama yok), `min_notional` borsanın en küçük emir değeri.
- `SizeResult(qty, notional, margin, risk_amount)`; `Decision(allowed, reason, size=None)`.

## Fonksiyonlar
- `liquidation_price(entry, side, leverage, mmr)`: long `entry*(1-1/L+mmr)`, short `entry*(1+1/L-mmr)`.
- `loss_at_stop(qty, entry, stop, cfg)`: `qty*|entry-stop| + qty*entry*(fee+slip) + qty*stop*(fee+slip)`.
- `size_position(equity, entry, stop, side, leverage, cfg, qty_step=None, min_notional=0.0) -> SizeResult`:
  1. `qty_risk` = `loss_at_stop(qty)=target_trade_risk*equity` çözümü.
  2. `qty_cap` = `max_notional_ratio*equity/entry`.
  3. `qty = min(qty_risk, qty_cap)`; `qty_step` verilmişse **aşağı** yuvarlanır (`floor(qty/qty_step)*qty_step`, kayan nokta hatasına karşı güvenli).
  4. `qty ≤ 0` veya `qty*entry < min_notional` → `ValueError`.
  5. `risk_amount = loss_at_stop(qty)` yeniden hesaplanır; `risk_amount > max_trade_risk*equity` → `ValueError` (savunma).
  6. `margin = notional/leverage`; `margin > equity` → `ValueError`.

## `check_entry(state, cand, cfg=LOCKED_CFG) -> Decision` kuralları (sırayla; ilk ihlal red)
1. Girdi geçersiz (sayılar, side, pair boş, equity ≤ 0, day_start_equity ≤ 0, herhangi bir açık pozisyon geçersiz) → red.
2. Stop yanlış tarafta → red.
3. Kaldıraç aralık dışı veya tam sayı değil → red.
4. Günlük sınır zaten dolmuş: `(equity - day_start)/day_start ≤ -daily_max_loss` → red.
5. Aynı çift (normalleştirilmiş) zaten açık → red.
6. Boyut (`size_position`) hata verirse → red.
7. Likidasyon güvenliği: `|entry - liq| < liq_safety_factor*|entry - stop|` → red.
8. Toplam açık risk + yeni risk `> max_open_risk*equity` → red.
9. Aynı yön açık risk + yeni risk `> max_same_dir_risk*equity` → red.
10. **Günlük bütçe:** `bugünkü_kayıp + toplam açık risk + yeni risk > daily_max_loss*day_start_equity` → red; `bugünkü_kayıp = max(0, day_start_equity - equity)`.
11. **Teminat:** açık pozisyon teminatları toplamı + yeni teminat `> equity` → red.
12. Hepsi geçerse `allowed=True`, `size` dolu.

Beklenmeyen her istisna `allowed=False, reason="iç hata: ..."`; istisna dışarı sızmaz.
