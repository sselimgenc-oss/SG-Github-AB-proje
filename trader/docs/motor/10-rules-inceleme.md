# 10 - Borsa kurallari (rules) incelemesi: "snapshot kurallari kararlarin cogunu atladi" iddiasi

Tarih: 17 Kasim 2026. Yalniz inceleme; src/ ve tests/ degismedi. HOLDOUT'a dokunulmadi (tum kosular <= 2026-05-01).

## 1. Kurallar nereden gelir

| Kip | Kaynak | Yer | Yaratan | Var mi |
|---|---|---|---|---|
| native/compat backtest, `--source history` (varsayilan) | `history_dir/rules.json` = `{pair: spec_json}` | `HistoricalSource.rules`, `src/trader_engine/marketdata/sources.py:378-399` | **Hicbir betik/komut yok.** `feed.snapshot_rules(..., out_json_path=...)` (`marketdata/feed.py:104-123`) dosyayi yazabilir ama cagiran hicbir yer `out_json_path` vermiyor; `trader_engine rules-snapshot` (`cli.py:127-132`) `feed.rules_snapshot_main`'i arar, o fonksiyon **yok** -> "01 islevi bu surumde yok", cikis EXIT_FAZ_B | **Hayir**: `user_data/data/binance/futures/rules.json` yok; repo ve `var/` altinda hicbir rules.json yok (`find`), yalniz test gecici dizinleri |
| backtest `--synthetic-rules` | son 2000 1h barin ondaliklari | `sources.py:414-420` (tick, step=min_qty=hacim ondaligi, min_notional=5, max_qty=1e12) | kod | evet (gercek kural degil; meta.json `rules_source: "synthetic"`) |
| backtest `--source store` ve paper/live | `market.sqlite` `rules` tablosu (`StoreSource.rules`, `sources.py:192-200`) | `engine.build_engine` `engine.py:830-841`: `view=StoreSource(cfg.market_db)`, `PaperBroker(..., view.rules, ...)` | `Feed.start()` ve saatlik `_refresh_rules` -> `snapshot_rules` -> `PublicRestClient.exchange_info` (`feed.py:186-191, 369-371, 443-445`; `rules_refresh_s=3600`) -> `store.put_rules` | `var/market.sqlite` **yok** (henuz feed calismamis) |

Ek bulgular:
- `trader_engine feed` komutu `feed.main`'i arar (`cli.py:118-124`); `feed.py`'de `main` / `__main__` **yok**. Yani bugun feed'i (ve dolayisiyla kural cekmeyi) baslatan bir giris noktasi yok; bu baska bir ajanin eliyle ekleniyor olabilir, ama paper baslangicindan once mutlaka kapanmali.
- Bu ortamda Binance REST HTTP 451 ("restricted location"): `curl https://fapi.binance.com/fapi/v1/exchangeInfo` -> 451 (denendi, bu oturumda). Gercek exchangeInfo bu makineden alinamaz; `docs/motor/00-index.md` madde 16 ayni seyi kaydeder. Repoda gercek kayit yok, yalniz **sahte** parca `tests/engine/fixtures/binance/exchange_info_sample.json` (BTC min notional 100, ETH 20).

## 2. Iddianin dogrulanmasi ("snapshot rules most decisions'i atladi")

Mentorun okumasi kismen dogru, kismen eksik:
- `rules.json` yoksa `HistoricalSource.rules` gercekten `DataError` verir (`sources.py:384-385`), ama `EntryGate.decide` bunu yakalar (`gates.py:214-219`, "fail-closed") ve karari **atlama** olarak yazar: `skip_reason="other"`, `veto_reason="gate:rules_missing"`. Yani "DataError atar, atlamaz" yanlis: atlar.
- Ucuz yeniden uretim (Ocak 2026, BTC/DOGE/LINK, `python -m trader_engine.backtest --period 20260101-20260201 --pairs BTC/USDT,DOGE/USDT,LINK/USDT ...`, cikti scratchpad'de):
  - `--synthetic-rules`: 18 giris; 2 risk_denied; 21 stop_width on-filtre; n=18.
  - kuralsiz (`rules.json` yok): **38/38 sinyalli karar** `skipped / other / gate:rules_missing`; n=0. (Yani "snapshot yok -> kararlarin tamami atlanir" dogrulandi; "cogu" degil, hepsi.)
- Builder'in kendi loguna/kodunda gerekce yorumu yok (`ml_build_candidates.py:44` yalniz `BT_ARGS`'a `--synthetic-rules` koyar; `ml_build.log` yalniz manifest JSON'u, `ml_cand_bt.log` tek satir sonuc). Iddianin kaynagi budur: rules.json olmadigi icin sentetik kural zorunluydu. Bu, `tasarim-kararlari.md:81` (b) ile celisir: "asil modda spec disi; gercek anlik goruntu ya da kilitli donem oncesi mumlardan hesaplanan sentetik kural + kayitli istisna". Sentetik kural, pre-holdout mumlardan (son 2000 1h bar) turetildigi icin icerik olarak (b)'nin ikinci secenegine uyar ama **kayitli istisna** yoktur; ayrica `HistoricalSource._synthetic_rules` "son 2000 bar" = dosyanin SONU (2026-11-15'e kadar, holdout dahil!) kullanir: `sources.py:415-416` `len(s.ms)-2000` -> son barlar holdout donemi icinde. Yalniz tick/step ondaligi ve hacim ondaligini etkiler (olculen: guvenlik riski degil, ama "kilitli donem oncesi" ifadesine uymaz). Rapora yazilmali.

ml_cand_v1b_native (tum 10 cift, 20241101-20260501) ledger'inda atlama nedenleri (`v_decisions`, sorgu: group by final_action, skip_reason, risk_reason):

| final_action / skip_reason | n |
|---|---|
| skipped / stop_width (on-filtre, kural ile ilgisiz) | 1379 |
| entered | 819 (builder 817 alinan + 2 sonda acik) |
| skipped / risk_denied | 620: ayni yon risk limiti 386 (short 279 + long 107), gunluk zarar butcesi 178, toplam teminat 49, gunluk sinir 7 |
| skipped / order_failed | 39 |

- **min_notional / "miktar sifir veya en kucuk emir degerinin altinda" nedeniyle hic bir risk_denied yok** (reason metinleri `risk.py:223-224` ile aranir; 0 eslesme). `rules_missing`: 0.
- Giris notional'u: tum girislerde en kucuk 218 USD, medyan ~900 USD (backtest `target_trade_risk=0.014`), yani min_notional=5 hic baglayici olmadi.
- order_failed (39): tum cikis yolu `paper._reject_at_fill` (`paper.py:436-451`): `min_notional` (notional<5: imkansiz, min 218) ya da `insufficient_margin` (margin+fee > wallet - kullanilan teminat; `wallet` gerceklesmemis PnL icermez, risk kapisi ise equity kullanir). Dogrulama: 20250401-20250701 tum cift sentetik kosusu `_reject_at_fill` sarmalanarak yeniden calistirildi (scratchpad betigi, src degismedi): 3 ret, hepsi `insufficient_margin`, 0 `min_notional`. Yani order_failed = marj/wallet, kural degil. Cift dagilimi SOL 6, XRP 5, TRX 5, BTC 4, ADA 4, DOGE 4, ETH 4, AVAX 3, LINK 3, BNB 1.
- Builder manifestindeki "skipped 659" = 620 risk_denied + 39 order_failed. Bunlarin hicbiri kural kaynakli degil; hepsi portfoy risk tavani / marjin. Yani "snapshot rules skipped most decisions" ifadesi builder'in sentetik kurala gecis gerekcesidir (rules.json yok -> %100 atlama), sentetik kuralla elde edilen atlamalarin nedeni **degildir**.

## 3. Gercekci Binance USDT-M kurallariyla paper (1000 USD, %0,5 risk, kaldirac 3): giris engellenir mi?

Hayir. Hesap: `risk.size_position(equity=1000, entry, stop, side, lev=3, cfg=build_risk_config(0.005), qty_step, min_notional)` — 858 gercek karar (ledger'daki planned_entry/planned_stop, boyutlanmis tum kararlar). Risk 5 USD, notional tavani 1000 USD (`max_notional_ratio=1`), kaldirac `entry_leverage()=min_leverage=3` (`gates.py:83-85`; `engine.base.json`'da kaldirac alani yok).

Kurallar: BTC min notional 100 ve ETH 20 repo fixture'indan (`exchange_info_sample.json`; sahte ama gercege uygun); diger 8 cift icin min notional 5 USDT ve adimlar **hafizadan, dogrulanmamis** (gercek exchangeInfo erisilemedi, HTTP 451): BNB 0.01, SOL 0.01, XRP 0.1, DOGE 1, ADA 1, TRX 1, LINK 0.01, AVAX 1; BTC/ETH 0.001.

| Cift | n | engellenen | qty medyan (min) | notional medyan (min / maks) USD | min_notional | step |
|---|---|---|---|---|---|---|
| BTC | 102 | 0 | 0.005 (0.002) | 475 (140 / 951) | 100 | 0.001 |
| ETH | 79 | 0 | 0.125 (0.04) | 324 (182 / 806) | 20 | 0.001 |
| BNB | 112 | 0 | 0.515 (0.15) | 384 (166 / 999) | 5 | 0.01 |
| SOL | 63 | 0 | 1.66 (0.72) | 284 (111 / 624) | 5 | 0.01 |
| XRP | 100 | 0 | 150.6 (47.9) | 343 (120 / 909) | 5 | 0.1 |
| DOGE | 74 | 0 | 1455 (234) | 265 (94 / 539) | 5 | 1 |
| ADA | 94 | 0 | 444.5 (125) | 263 (130 / 550) | 5 | 1 |
| TRX | 119 | 0 | 2000 (918) | 607 (218 / 1000) | 5 | 1 |
| LINK | 64 | 0 | 18.31 (3.66) | 270 (77 / 527) | 5 | 0.01 |
| AVAX | 51 | 0 | 14 (3) | 258 (108 / 569) | 5 | 1 |
| Toplam | 858 | **0** | | | | |

Marj: notional/3 <= 333 USD tek pozisyon; ayni anda cok pozisyon `insufficient_margin`/teminat limiti dogurabilir ama bu kural degil sermaye etkisi. En dar marj payi: BTC (min notional 100'e en yakin 140 USD = 1,4x); BTC icin %0,5 riskle notional 100'u kirmak icin stop genisligi ~ %4,9'u gecmeli (5/(w+~0,15%)); gozlenen BTC maksimum stop %2,19.
Not: 1000 USD'de %0,5 risk (5 USD) ile on-filtre `stop_width` zaten genis/dar stopları eler; min_notional bunun disinda ek eleme yapmaz.

Sentetik kural gercekle karsilastirma (10 cift, `HistoricalSource(synthetic_rules=True)`): tick BTC 0.1/ETH 0.01/BNB 0.01/SOL 0.01/XRP 1e-4/DOGE 1e-5/ADA 1e-4/TRX 1e-5/LINK 1e-3/AVAX 1e-3 (gercekle uyumlu gorunuyor); step DOGE/ADA/XRP/TRX/AVAX 0.1 (gercek 1 veya 0.1 -> sentetik daha ince: nicelleme riski hafif **hafif alt-tahmin**, min_notional=5 BTC/ETH icin gercekten dusuk (100/20) ama baglayici degil). Sonuc: sentetik kural bu sermaye ve riskte sonuclari anlamli bicimde bozmaz; bozulabilecek tek yer step inceligi (qty yuvarlama farki <= %1 mertebesi).

## 4. Paper/live yapilandirmasinda kural kaynagi calisiyor mu?

- `config/engine.base.json`: `mode=paper`, `market_db=var/market.sqlite`, `history_dir=user_data/data/binance/futures`; **kural kaynagi alani yok**. Paper `StoreSource(market_db)` kullanir; kural `market.sqlite.rules` tablosundan okunur.
- Kural tabloyu yalniz `Feed.start()` (`feed.py:186-191`: acilista `_refresh_rules`, hata olursa yalnizca uyari + devam) ve saatlik yenileme doldurur. Acilista cekilemezse tablo bos kalir: `StoreSource.rules` -> `DataError("kural yok")` -> gate `rules_missing` ile **her giris atlanir** (fail-closed, sessiz, pozisyon acilmaz). Bu kendi basina guvenli ama paper "calisiyor gibi gorunup hic islem acmaz".
- Eksikler: (1) `trader_engine feed` ve `rules-snapshot` komutlari bu surumde calismiyor (`feed.main`, `feed.rules_snapshot_main` yok); (2) `var/market.sqlite` yok; (3) bu ortamda REST 451 — paper'in kosacagi makinede `https://fapi.binance.com/fapi/v1/exchangeInfo` erisilebilir olmali; (4) `status`/gate'te rules_missing sayaci acik bir alarm uretmiyor mu kontrol edilmedi.

## 5. Oneri (uygulama yok)

1. 30 Kasim oncesi: paper'in kosacagi makinede keysiz public `exchangeInfo` erisimini dogrula; `feed` giris noktasini (main) ve `rules-snapshot` komutunu tamamla; `var/market.sqlite` icinde 10 cifte kural ve BTC=100/ETH=20/digerleri 5 notional'unu **olagan kontrol (smoke)** olarak assert et. Ayrica `status` ciktisina "rules_missing sayisi > 0 ve acik pozisyon yok" alarmi.
2. `rules-snapshot` ile gercek anlik goruntuyu `user_data/data/binance/futures/rules.json`'a yaz ve repoya/anlik-goruntu olarak (tarih, sha256) kaydet; backtest/ML derlemi bunu kullansin (`--synthetic-rules` asil modda kullanilmasin; mentor karari (b)).
3. Gercek erisim mumkun olmayacaksa gecici yedek: `rules.json`'u elle uretilmis ve **"gercek degil" etiketli** olarak tut (BTC 100, ETH 20, digerleri 5; adimlar 07 fixture'i + hafizadan), ya da `_synthetic_rules`'u yalniz kilitli donem oncesi barlardan (<= 2026-05-01) turetecek sekilde sinirla ve istisnayi kayda gec. Yeniden kurulum (19b) bu sebeple gercek kural ya da pre-holdout sentetikle, %0,5 riskle (`target_trade_risk=0.005`) yapilmali; mevcut derlem %1,4 riskle ve holdout sonu barlarindan turetilmis ondaliklarla kurulmustu.
4. Karar: kural problemi paper 1000 USD / %0,5 icin **giris engeli degildir** (0/858 engellenir); asil risk kural kaynaginin hic dolmamasi (feed/komut yok, ortamda 451) -> %100 `rules_missing` atlama. Bu giderilmeden paper baslamamali.
