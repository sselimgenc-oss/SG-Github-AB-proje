# Kâğıt–geri test tutarlılık raporu (haftalık) — belirtim (19 Kasım 2026, Faz 2a)

Amaç: aynı dönem ve aynı kurulumlar için kâğıt defteri ile geri test motorunun o döneme ait çıktısını karşılaştırmak. Rapor **yalnız bilgi verir**: işlemi engellemez, kurulum kapatmaz, kapı değildir.

Temel: `docs/motor/06-backtester.md` §8. `backtest --from-paper-ledger` ve `backtest.equality_report` zaten var. Bu iş onları haftalık, kurulum başına özetleyen bir sarmalayıcıdır. Motor davranışı değişmez.

## Dönem
- Son 7 tam UTC günü (`[pazartesi 00:00Z − 7g, pazartesi 00:00Z)`). Pazartesi 03:30 TSİ'de çalışır.
- Dönemin `2026-11-01` öncesine düşen kısmı **kesilir**. Holdout (2026-05-01 → 2026-11-01) asla okunmaz. Holdout kilidi motor tarafında da zaten var; ona güvenilir ve ek olarak burada da kontrol edilir.
- Dönemde parametre/sürüm değişimi varsa (`param_activation_changed`), ilgili alt dönem dışarıda bırakılır ve rapora yazılır.

## Koşu
- `scripts/tutarlilik_run.py`: geri testi kâğıt yapılandırmasıyla (`--env paper`, aynı `market.sqlite`, aynı kurallar, aynı maliyet), `--from-paper-ledger <kâğıt defteri>` ve `--fill-model native --granularity 1m` ile çalıştırır, ardından özeti üretir.
  - Geri test çok kollu kâğıt stratejisini (`price_action_lab_ml`, overlay dahil) desteklemiyorsa bu açıkça raporlanır ve TIKANDI olarak bildirilir. Sessizce başka strateji kullanılmaz.
- Birim: `deploy/trader-tutarlilik.service` (oneshot, kullanıcı `trader`, `Slice=trader.slice`, `MemoryMax` ölçülerek konur, `Nice=10`) ve `.timer` (`OnCalendar=Mon *-*-* 00:30:00 UTC`, `Persistent=true`). Diğer birimlerle aynı sertleştirme ve render kalıbı kullanılır. `install.sh` timer'ı etkinleştirir. Bellek bütçesi testleri (`tests/readiness/test_readiness_memory.py`) güncellenir.

## Kurulum başına ölçüler (setup, ör. PA1, M1, C1)
- **Sinyal eşleşmesi**, anahtar `(pair, side, entry_ts)`. Üç sayı tutulur: ikisinde birden olan, yalnız kâğıtta olan ve yalnız geri testte olan. Eşleşme oranı = ikisinde / (ikisinde + yalnız kâğıt + yalnız geri test).
- **Fiyat farkı (kayma)**: eşleşenlerde giriş ve çıkış fiyatı farkının ortalaması ve en kötüsü, bps cinsinden. Kâğıt, geri teste göre ölçülür; işaret kâğıt aleyhine pozitif olur.
- **İşlem sayısı, kazanma oranı, toplam R ve toplam PnL**: kâğıt ve geri test için yan yana, ayrıca fark.
- **Fark nedenleri**: `equality_report` sınıfları (`paper_gap`, `no_paper_record`, `data_conflict`) ve şu sınıflar:
  - `maliyet`: komisyon/funding farkı.
  - `gecikme`: kâğıtta giriş ya da çıkış geri testten sonraki barda.
  - `veri`: feed çakışması ya da eksik mum.
  - `aciklanamayan`: hiçbir sınıfa uymayan fark.

## Eşik (WARN) — öneri
Herhangi bir kurulumda, o kurulumun en az 5 işlemi varsa ve aşağıdakilerden biri tutuyorsa WARN `tutarlilik_sapma` verilir:
- `aciklanamayan > 0`;
- eşleşme oranı < %90;
- |toplam R farkı| > max(1,0 R, kâğıt toplam |R|'nin %20'si);
- eşleşenlerde ortalama giriş kayması > 10 bps.

## Çıktılar
- Markdown rapor: `var/rapor/tutarlilik/<YYYY-AA-GG>.md`. Sunucu GitHub'a yazamaz, bu yüzden rapor sunucuda kalır. Haftalık bir örnek ve yöntem `docs/motor/tutarlilik-raporu-ornek.md` olarak repoya elle eklenir.
- Makine özeti: `var/durum/tutarlilik_v1.json` (atomik yazılır):
  `{"sema":"ml.tutarlilik.v1","uretim":ISO,"donem":{"bas":ISO,"bit":ISO},"kurulumlar":[{"ad","kagit_islem","bt_islem","eslesme_orani","yalniz_kagit","yalniz_bt","giris_kayma_bps_ort","cikis_kayma_bps_ort","kagit_R","bt_R","kagit_pnl","bt_pnl","kagit_kazanma","bt_kazanma","nedenler":{...}}],"uyari":bool,"uyari_nedenleri":[...],"not":str|null}`.
  Pano yayınına bağlama ayrı bir iştir (orkestratör: "panoya sonra bağlarız").
- Telegram haftalık raporuna (`scripts/weekly_summary_run.py`) 1–2 satır eklenir. Örnek: `Tutarlılık: eşleşme %96, ΣR farkı +0,4R; uyarı yok`. Dosya yoksa ya da bayatsa (8 günden eski) `Tutarlılık: rapor yok`.
- Sağlık: `tutarlilik_v1.json` içinde `uyari=true` ise `scripts/health_run.py` WARN `tutarlilik_sapma` verir. Motor etkilenmez.

## Sınırlar
- Donuk dosyalara dokunulmaz. `backtest.py`'de değişiklik gerekiyorsa en küçük ve geriye uyumlu biçimde yapılır, testleriyle birlikte.
- Yeni bağımlılık eklenmez. Testler sentetik verilerle yazılır; holdout tarihi ve `var/history` geçmez (`tests/engine/test_no_holdout_in_tests.py`).
