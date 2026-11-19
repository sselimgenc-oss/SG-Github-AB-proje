# Kurulum başına sanal kasa raporu — belirtim (Faz 1, 19 Kasım 2026)

Amaç: Her kurulumun (arm, örn. `T1@1h`) tek başına işlem yapsaydı kasasının ne olacağını göstermek. **Yalnız rapor**; hiçbir işlemi engellemez, hiçbir kurulumu kapatmaz, motoru etkilemez.

## API (`src/trader_core/counterfactual.py`)
`arm_virtual_bankroll(candidates, *, start=1000.0, risk=0.01) -> dict[str, dict]`
- `candidates`: `arm_candidates(...)` çıktısıyla aynı biçim: her öğe `{"arm_id", "asset_class", "taken": bool, "ts", "r": float|None, ...}`.
- Her `arm_id` için iki seri hesaplanır:
  - `taken`: yalnız `taken is True` ve `r is not None` adaylar.
  - `cf`: `r is not None` olan tüm adaylar (alınan + "alınsaydı").
- Seri `ts`'ye göre artan sıralanır (eşitlikte girdi sırası korunur). Kasa bileşik büyür: her adımda `eq = eq * (1 + risk * r)`; `eq` 0'ın altına inmez (0'da kalır).
- Her seri için çıktı: `{"n": adet, "equity": son kasa (2 ondalığa yuvarlanmış), "return_pct": (equity/start-1)*100 (2 ondalık), "max_dd_pct": en derin tepe-dip düşüş yüzdesi, pozitif sayı (2 ondalık; düşüş yoksa 0.0)}`. Tepe başlangıç kasasıyla başlar.
- Hiç adayı olmayan seri: `{"n": 0, "equity": start, "return_pct": 0.0, "max_dd_pct": 0.0}`.
- Dönüş: `{arm_id: {"taken": {...}, "cf": {...}}}`. `arm_scorecard(..., arms=...)` gibi `arms=()` anahtar kelime argümanı da alır; listedeki ama adayı olmayan kurulumlar da çıktıda yer alır.
- `start <= 0` ya da `risk <= 0` ise `ValueError`.

## Karneye bağlama
- `arm_scorecard` çıktısındaki her kurulum bloğuna `"kasa"` anahtarı eklenir: `arm_virtual_bankroll` sonucunun o kuruluma ait değeri (varsayılan start=1000, risk=0.01). Mevcut alanlar değişmez.

## Telegram `/kurulumlar` (`src/trader_core/telegram.py`, `_karne_satirlari`)
- Her kurulum satırının sonuna: ` · kasa 1012.40 $ (en derin -1.20%)` (alınan seriden). `kasa` anahtarı yoksa satır eskisi gibi kalır.

## Pano (`src/trader_core/panel_data.py` + pano HTML'i)
- Öğrenme sekmesindeki kurulum karnesi tablosuna iki sütun: "Sanal kasa ($)" ve "En derin düşüş (%)" (alınan seri). Veri yoksa "—".

## Sınırlar
- Donuk dosyalara dokunulmaz. Ağ, yeni bağımlılık yok. Yalnız standart kütüphane + mevcut modüller.
