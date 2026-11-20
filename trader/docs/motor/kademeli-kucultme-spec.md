# Kademeli boyut küçültme (kâğıt) — spec

Tarih: 20 Kasım 2026. Kapsam: yalnız `mode="paper"`. Bu karar, 19 Kasım "ders yalnız rapor eder" kararının **boyut** yönünü değiştirir
(kol kapatma hâlâ yoktur; `arms_off` yalnız karne bilgisidir).

## 1. Kural

Her kol (`arm_id`, örn. `R1@1h`) için kolun **kapanmış kâğıt işlemlerinin net R** değerleri (`r_multiple`: komisyon, kayma ve funding
düşülmüş; R = gerçekleşen K/Z ÷ planlanan risk, yani boyuttan bağımsız) en yeniden eskiye dizilir (`exit_ts`, `trade_id` azalan).
`n` = kapanmış işlem sayısı (en çok 10 okunur), `s5` = en yeni 5'in toplamı, `s10` = en yeni 10'un toplamı.

| Koşul (sırayla) | Çarpan |
|---|---|
| `n >= 10` ve `s10 < 0` | **0,3** (asgari boyut) |
| `n >= 5` ve `s5 < 0` | **0,5** |
| aksi | **1,0** |

* `n < 5` ⇒ değişiklik yok. Toplam tam 0 ise negatif değildir (küçültme yok).
* Kol **asla kapatılmaz**: en düşük çarpan 0,3'tür; giriş her zaman denenir.
* Geri yükselme otomatiktir ve **durumsuzdur** (her girişte defterden yeniden hesaplanır): `s10 >= 0` olunca 0,3 → 0,5 (ya da `s5 >= 0` ise 1,0),
  `s5 >= 0` olunca 0,5 → 1,0. Not: `s10 < 0` iken son 5 işlem kârlı olsa bile çarpan 0,3 kalır; yükselme için 10'lu pencerenin de toplamı
  negatif olmamalıdır (kasıtlı: tek kâr serisi hemen tam boyuta dönmez; zarar serisi pencereden düştükçe adım adım döner).
* Çarpan boyutu **yalnız küçültür**: etkin hedef risk = `yapılandırma hedef riski × çarpan` (kâğıtta %1 → %0,5 / %0,3). `RiskConfig`
  sınırları ve risk kademesi (RK-1, `ladder`) anlamı değişmez; kademe de riski düşürmüşse iki küçültme çarpılır.
* Stop mesafesi, kaldıraç tavanı, günlük zarar limiti, toplam açık risk ve aynı yön limitleri aynen geçerlidir (küçük boyut yalnız onlara daha
  çok pay bırakır). Çıkış kipleri (başabaş/kısmi) ve kümelerin/kolun pozisyon tavanı etkilenmez.
* Asgari emir değeri: küçültülmüş boyut borsanın en küçük emir değerinin altında kalıp risk kapısı reddederse, kol kapanmasın diye aynı giriş
  **yapılandırma boyutuyla** (çarpan 1,0) bir kez daha denenir; kayıtta `kol_boyut_geri = 1`.

## 2. Nereye bağlanır

`trader_engine/gates.py` `EntryGate.decide`, kâğıt dalı: `check_entry` çağrısından hemen önce `_kol_karari(arm_id)` defterden
`Ledger.arm_recent_results(arm_id, 10)` okur; saf kural `trader_core/kol_kucultme.py` (`karar`). Çarpan < 1 ise `risk.tightened(cfg, target_trade_risk=…×çarpan)`
ile `check_entry` çağrılır; `size_position` boyutu doğal olarak küçültür (`size_qty`, `size_notional`, `size_margin`, `size_risk_amount`).
Testnet/canlı/geri test (`cfg.mode != "paper"`) bu yola girmez; davranış ve kayıtlar bit bit aynıdır. Defter okunamazsa çarpan uygulanmaz
(yalnız küçültme atlanır; hiçbir şey büyütülmez, giriş engellenmez).

## 3. Kayıt (karar satırı `features`)

`kol_boyut_carpani` (0,3 / 0,5 / 1,0), `kol_n` (okunan kapanmış işlem, ≤ 10), `kol_net_r_5` (n ≥ 5 ise), `kol_net_r_10` (n ≥ 10 ise), gerekirse
`kol_boyut_geri`. Yalnız kayıttır; ML ve diğer kapılar bu anahtarları kullanmaz.

## 4. Görünürlük

* Panel ÖĞRENME sekmesi: "Kademeli küçültme" kartı (yalnız küçültülen kol varsa): kol, boyut yüzdesi, son 5/10 net R.
* Telegram günlük özet: tek satır, yalnız küçültülen kol varsa ("Boyutu küçültülen kollar …"); yeni mesaj türü yoktur.

## 5. Testler

`tests/engine/test_kademeli_kucultme.py`: eşikler (4 işlem değişmez, 5 zararlı 0,5, 10 zararlı 0,3), basamaklı geri yükselme, boyutun gerçekten
yarılanması/0,3'e inmesi (qty, risk tutarı), kayıt anahtarları, yalnız kâğıt, defter sorgusu, asgari emir değeri geri dönüşü, panel kartı, rapor satırı.
