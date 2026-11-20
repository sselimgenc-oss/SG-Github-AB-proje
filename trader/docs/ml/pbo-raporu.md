# PBO raporu (holdout oncesi, yalniz rapor)

Bu rapor **bilgi amaclidir**: karar kapisi degildir, hicbir islemi ya da kurulumu engellemez. Yalniz `2026-05-01` oncesi veri kullanildi; holdout satirlarina dokunulmadi. Uretim: `python research/pbo_rapor.py` (seed 0, sabit).

## 1. Tablo

| Aile | Yapilandirma (kullanilan) | T (gun) | PBO | Medyan OOS goreli sira | En iyi IS yapilandirma | Yillik SR | DSR | Yorum |
|---|---|---|---|---|---|---|---|---|
| ML 19c | 12 (3) | 240 | 0,323 | 0,750 | `p_lgbm@0.45` | 0,80 | 0,024 | asiri uyum riski dusuk-orta |
| ML r02 | 12 (9) | 1574 | 0,581 | 0,500 | `p_logistic@0.70` | -0,12 | 0,085 | asiri uyum riski yuksek |
| ML r03 | 12 (8) | 1574 | 0,664 | 0,333 | `p_logistic@0.70` | 0,21 | 0,304 | asiri uyum riski yuksek |
| Kural B1 (harness) | 112 (112) | 1946 | 0,007 | 0,929 | `B1@4h/BRK_ATR=0.3/f1/s0` | 0,11 | 0,000 | asiri uyum riski dusuk-orta |
| Kural F1 (harness) | 112 (112) | 1946 | 0,000 | 0,664 | `F1@1d/REJ_MIN=0.7/f1/s0` | 0,06 | 0,000 | asiri uyum riski dusuk-orta |
| Kural H2 (harness) | 112 (112) | 1946 | 0,068 | 0,717 | `H2@4h/trail_atr=2.5/f1/s0` | 0,41 | 0,000 | asiri uyum riski dusuk-orta |
| ML M1@1h (egitim-disi) | 12 (12) | 1110 | 0,004 | 0,846 | `M1@1h/thr_x1/f1/s0` | -0,26 | 0,001 | asiri uyum riski dusuk-orta |
| Kural R1 (harness) | 56 (52) | 1946 | 0,388 | 0,528 | `R1@1d/range_target_frac=0.6/f2/s0` | -0,43 | 0,000 | asiri uyum riski dusuk-orta |
| Kural S1 (harness) | 112 (112) | 1946 | 0,177 | 0,655 | `S1@1d/trail_atr=3.5/f1/s0` | 0,13 | 0,000 | asiri uyum riski dusuk-orta |
| Kural T1 (harness) | 48 (48) | 1946 | 0,514 | 0,490 | `T1@1d/trail_atr=2.5/f1/s0` | 0,95 | 0,592 | asiri uyum riski yuksek |
| Kural TF1 (harness) | 112 (112) | 1946 | 0,033 | 0,832 | `TF1@1d/trail_atr=3.5/f1/s0` | 1,06 | 0,000 | asiri uyum riski dusuk-orta |
| TUM KUME | 712 (692) | 1946 | 0,085 | 0,886 | `h:TF1@1d/trail_atr=3.5/f1/s0` | 1,06 | 0,000 | asiri uyum riski dusuk-orta |

PBO < 0,5 ise "asiri uyum riski dusuk-orta", aksi "yuksek" yazilir; esik bilgi amaclidir. DSR, en iyi (tam orneklem Sharpe) yapilandirma icin, o ailedeki tum yapilandirma sayisiyla (elenenler ve sabit sutunlar dahil) hesaplanir. Yillik SR = gunluk SR x sqrt(365).

## 2. Yontem

- `trader_core.stats.pbo_cscv`, `n_splits=16`, `max_combinations=2000`, `seed=0`, olcut Sharpe; `trader_ml.gate.pbo_for` deseni (ML ailelerinde yapilandirma = model x esik, satir = gun, deger = alinan islemlerin gunluk net R toplami).
- Kural ailelerinde yapilandirma = bir deneme kosusundaki kurulumun (T1, R1) gunluk R toplami (cikis gunune gore); kosular maliyet kolu, dolum modeli ve tetik zaman dilimi bakimindan farklidir. Ortak pencere IS 2024-11-01..2025-10-31 (365 gun, islemsiz gun = 0).
- Hafif donanim aileleri (`Kural X (harness)`, `ML M1@1h (egitim-disi)`): yapilandirma = zaman dilimi x on-kayitli parametre varyanti x maliyet (bolum 5); gun izgarasi 2021-01-01..holdout oncesi son gun (islemsiz gun = 0 R). Kolonlar yuksek olcude iliskilidir (ayni sinyal akisi, farkli maliyet/parametre); PBO bu yuzden zaman-dilimi secimine ve parametre komsuluguna duyarlidir. Dusuk PBO SECIM KARARLILIGIDIR (IS kazananin OOS'ta da iyi sirada kalmasi), kârlilik degildir: harness ailelerinde 15m/1h kolonlari tutarli bicimde en kotu, 4s/1g kolonlari en iyi siradadir; DSR ~0 ve kucuk yillik SR, hicbir yapilandirmanin deneme sayisi duzeltmesinden sonra pozitif beklenti gostermedigini belirtir (T1 harness istisnasi: DSR 0,76, 4s+1g yalniz 48 kolon).
- Sabit (std = 0) sutunlar CSCV'den cikarilir ama deneme sayisinda kalir.
- Medyan OOS goreli sira: IS'te en iyi yapilandirmanin OOS goreli sirasinin (rank/(N+1)) kombinasyonlar uzerindeki medyani; 0,5 = medyan.
- TUM KUME: ortak gun izgarasi (en erken..en gec gun); bir ailenin etkin olmadigi gunler 0 R'dir. Bu, pencereleri farkli aileleri tek matriste karistirir; sonuc yalniz kaba bir ust-kume gostergesidir.

## 3. Deneme kaynaklari

| Aile | Kaynak |
|---|---|
| ML 19c | research/ml/19c/oof_predictions.parquet (ml1-r01-v1b-native33 (19c); model x esik) |
| ML r02 | research/ml/r02/oof_predictions.parquet (ml1-r02-long-ctx-1r; model x esik) |
| ML r03 | research/ml/r03/oof_predictions.parquet (ml1-r03-long-regime8; model x esik) |
| Kural B1 (harness) | research/arm_series/B1.parquet (112 kolon: tf x parametre varyanti x maliyet; 2021-01-01..2026-04-30) |
| Kural F1 (harness) | research/arm_series/F1.parquet (112 kolon: tf x parametre varyanti x maliyet; 2021-01-01..2026-04-30) |
| Kural H2 (harness) | research/arm_series/H2.parquet (112 kolon: tf x parametre varyanti x maliyet; 2021-01-01..2026-04-30) |
| ML M1@1h (egitim-disi) | research/arm_series/M1.parquet (12 kolon: esik carpani x maliyet; 2021-01-01..2024-01-15) |
| Kural R1 (harness) | research/arm_series/R1.parquet (56 kolon: tf x parametre varyanti x maliyet; 2021-01-01..2026-04-30) |
| Kural S1 (harness) | research/arm_series/S1.parquet (112 kolon: tf x parametre varyanti x maliyet; 2021-01-01..2026-04-30) |
| Kural T1 (harness) | research/arm_series/T1.parquet (48 kolon: tf x parametre varyanti x maliyet; 2021-01-01..2026-04-30) |
| Kural TF1 (harness) | research/arm_series/TF1.parquet (112 kolon: tf x parametre varyanti x maliyet; 2021-01-01..2026-04-30) |
| TUM KUME | yukaridaki tum yapilandirmalar, ortak gun izgarasinda (etkin olmayan gun = 0 R) |

Kayit dosyalari (`research/trial_registry.csv`, `research/ml_trial_registry.csv`, `research/runs/*.json`) yalniz toplu istatistik tasir (gunluk getiri serisi yok); gunluk seriler `var/backtests/*/trades.csv` defterlerinden, ML `oof_predictions.parquet` dosyalarindan ve (defteri olmayan kurulumlar icin) `research/arm_harness.py` hafif donanim serilerinden (`research/arm_series/`) uretildi. Tam motor backtesti (`backtest --env paper`) kosulmadi.

## 4. Eksik kalan aileler

- `config/engine.paper.json` `arms` icinde motor defteri olan kurulumlar (kurulum duzeyinde): -.
- Hafif donanim serisi olan kurulumlar (25): T1@4h, T1@1d, R1@4h, R1@1d, TF1@15m, TF1@1h, TF1@4h, TF1@1d, B1@15m, B1@1h, B1@4h, B1@1d, H2@15m, H2@1h, H2@4h, H2@1d, S1@15m, S1@1h, S1@4h, S1@1d, F1@15m, F1@1h, F1@4h, F1@1d, M1@1h.
- Seri / defter **olmayan** 5 kurulum: T1@15m, T1@1h, R1@15m, R1@1h, M1@4h. Bunlar icin PBO hesaplanmadi; deneme uydurulmadi.
  - `M1@4h`: gonderilen paket egitim penceresi {'end': '2026-04-22T20:00:00+00:00', 'start': '2021-01-11T12:00:00+00:00'} tum holdout oncesi tarihsel veriyi kapsar; egitim-disi donem yok (sizinti olurdu)
- M1 (LightGBM/ridge onerici) adaylari: `research/paper_models.csv` ve `research/pa_proposer_build.py` yalniz egitim kaydi tutar (model sha256, satir sayisi); gonderilen paketin kendi egitim penceresi icinde degerlendirme sizinti olur, bu yuzden yalniz egitim-disi donem kullanilir (asagida bolum 5).
- Defter ailelerinde yalniz `T1` ve `R1` var; `T1` defterlerinin bir kismi (`ml_cand_v1b_native`, `s2_base_v1b`) farkli strateji surumu (`price_action_v1`) ve 10 ciftlik evrenle kosulmustur.

## 5. Hafif donanim serileri (`research/arm_harness.py`)

Amac: tam kagit backtest (~15 sn / 15 dk adim) cok yillik kosuya uygun degil; her kurulumun KENDI `compute()` fonksiyonu holdout oncesi tarihsel barlarda bir kez cagrilir, adaylar muhafazakar bir bar-yolu simulatoruyle cozulur, gunluk R toplami (cikis gunune gore, cift toplami) yazilir. Sinyal mantigi yeniden yazilmadi; simulator `trader_core.signals` yardimcilarini (`regime_flip_exit`, `TRAIL_START_R`, `TIME_STOP_BARS`) kullanir, hedef modu `trader_core.counterfactual.replay` ile (maliyetsiz) ve iz-stop `signals.trail_stop_path` ile testte karsilastirilir.

- Veri: `var/history` feather, okuma aninda `date < 2026-05-01` suzgeci; gun izgarasi 2021-01-01..2026-04-30; 33 cift (BTC/USDT, ETH/USDT, BNB/USDT, SOL/USDT, XRP/USDT, DOGE/USDT, ADA/USDT, TRX/USDT, LINK/USDT, AVAX/USDT, HYPE/USDT, BCH/USDT, XLM/USDT, SUI/USDT, HBAR/USDT, LTC/USDT, TON/USDT, 1000SHIB/USDT, DOT/USDT, XMR/USDT, NVDA/USDT, MSFT/USDT, AAPL/USDT, GOOGL/USDT, AMZN/USDT, META/USDT, AVGO/USDT, TSLA/USDT, PLTR/USDT, XAU/USDT, XAG/USDT, BZ/USDT, COPPER/USDT); `var/history` (muhurlu) disindaki ciftler `var/history_pre`den (`research/pbo_veri_indir.py`, data.binance.vision, holdout satiri yok). `config/engine.paper.json` icindeki 11 cift icin tarihsel mum bulunamadi ve kapsam disidir (BRKB/USDT, JPM/USDT, LLY/USDT, WMT/USDT, V/USDT, ORCL/USDT, XOM/USDT, NFLX/USDT, COST/USDT, AMD/USDT, HD/USDT; neden: data.binance.vision USDS-M arsivinde sembol yok).
- Simulator: giris = karar mumunu izleyen mumun acilisi (taraf aleyhine kayma); ayni barda stop ve hedef ikisi de degerse STOP once; acilis stop'u asmissa dolum acilista; `target` kipi: hedef + 48 mum zaman durdurma; `trail` kipi: 1R'de silahlanan iz-stop (`trail_atr` x ATR), rejim donusu ve iz-stop capraz cikisi sonraki barin acilisinda; kurulum+cift basina tek pozisyon, ayni-mum yeniden giris yasagi; cozulmemis islemler dusurulur.
- Maliyet: taraf basina taker 5 bp x ucret carpani + kayma (giris = cikis = stop). Fonlama, `cost_overrides`, kapasite/risk tavanlari, dakika cozunurlugu yok; bu nedenle seri motor defterinin birebir kopyasi degil, ham aday akisinin muhafazakar bir tahminidir.
- Deneme sayisi = her (kurulum, tf, parametre varyanti, maliyet) kolonu; sabit/bos kolonlar dahil DSR'ye girer.

### On-kayitli izgara (sonuclara bakilmadan once `research/arm_series/grid_declared.json` olarak yazildi)

sha256: `d81ca1e66ae65c5e8fc3a4d722c25246a7da1151167912ed12866673614bfd99`. Maliyet izgarasi (ucret carpani, kayma bp): (1x, 0 bp), (1x, 5 bp), (2x, 0 bp), (2x, 5 bp).

| Kurulum | Zaman dilimleri | Parametre varyantlari (OAT: varsayilan + dusuk/yuksek) | Kolon sayisi |
|---|---|---|---|
| B1 | 15m, 1h, 4h, 1d | def, BRK_ATR=0.1, BRK_ATR=0.3, TARGET_R=1.5, TARGET_R=2.5, stop_buffer_atr=0.2, stop_buffer_atr=0.5 | 112 |
| F1 | 15m, 1h, 4h, 1d | def, SWEEP_ATR=0.05, SWEEP_ATR=0.2, REJ_MIN=0.5, REJ_MIN=0.7, rr_min=1.25, rr_min=1.75 | 112 |
| H2 | 15m, 1h, 4h, 1d | def, PB_MIN_ATR=0.75, PB_MIN_ATR=1.5, LEG_GAP_MAX=6, LEG_GAP_MAX=14, trail_atr=2.5, trail_atr=3.5 | 112 |
| R1 | 4h, 1d | def, range_target_frac=0.6, range_target_frac=0.9, rr_min=1.25, rr_min=1.75, stop_buffer_atr=0.2, stop_buffer_atr=0.5 | 56 |
| S1 | 15m, 1h, 4h, 1d | def, BOX_W_ATR=2.5, BOX_W_ATR=3.5, BRK_ATR=0.05, BRK_ATR=0.2, trail_atr=2.5, trail_atr=3.5 | 112 |
| T1 | 4h, 1d | def, pullback_ema=20, stop_buffer_atr=0.2, stop_buffer_atr=0.5, trail_atr=2.5, trail_atr=3.5 | 48 |
| TF1 | 15m, 1h, 4h, 1d | def, BRK_ATR=0.1, BRK_ATR=0.3, BODY_MIN=0.4, BODY_MIN=0.6, trail_atr=2.5, trail_atr=3.5 | 112 |
| M1 | 1h | esik carpani 0.95, 1, 1.05 (paket esigi x carpan) | 12 |

### Referans: varsayilan varyant, config maliyetiyle (kayma 2/2/5 bp, ucret 1x; deneme sayilmaz)

| Kurulum@tf | Islem | Toplam R | Ort. R / islem |
|---|---|---|---|
| B1@15m | 6751 | -2207,6 | -0,327 |
| B1@1d | 177 | -34,1 | -0,193 |
| B1@1h | 2068 | -331,2 | -0,160 |
| B1@4h | 687 | -8,2 | -0,012 |
| F1@15m | 30480 | -9999,9 | -0,328 |
| F1@1d | 43 | -3,0 | -0,071 |
| F1@1h | 6618 | -1495,2 | -0,226 |
| F1@4h | 472 | -13,3 | -0,028 |
| H2@15m | 18208 | -3464,3 | -0,190 |
| H2@1d | 371 | 14,8 | 0,040 |
| H2@1h | 6197 | -616,1 | -0,099 |
| H2@4h | 1998 | 18,6 | 0,009 |
| R1@1d | 4 | -4,2 | -1,055 |
| R1@4h | 466 | -89,7 | -0,193 |
| S1@15m | 34190 | -5513,6 | -0,161 |
| S1@1d | 569 | 4,8 | 0,009 |
| S1@1h | 8217 | -338,2 | -0,041 |
| S1@4h | 2330 | -153,6 | -0,066 |
| T1@1d | 214 | 59,1 | 0,276 |
| T1@4h | 1871 | 109,3 | 0,058 |
| TF1@15m | 19763 | -4444,0 | -0,225 |
| TF1@1d | 750 | 127,9 | 0,171 |
| TF1@1h | 5242 | -273,6 | -0,052 |
| TF1@4h | 2304 | -78,8 | -0,034 |

### M1 (egitim-disi donem)

Gonderilen `M1@1h` paketinin egitim penceresi 2024-01-16T15:00:00+00:00..2026-04-28T23:00:00+00:00 (egitim satiri `max_rows`=400000 ile yalniz EN SON satirlara kirpilmis); bu pencereden ONCEKI tarihsel veri paketin gormedigi donemdir. Degerlendirme gunleri 2021-01-01..2024-01-15; son sinyal mumu 2024-01-11 21:00:00+00:00 (egitim baslangicindan pencere + ufuk + 2 bar once: etiket/ozellik ortusmesi yok). Paket esigi 0,3700. Uyari: ozellik/etiket tasarimi (1,5 ATR stop, 3 ATR hedef, 48 bar) ve esik niceligi tum tarihsel veri goruldukten sonra secilmis olabilir; bu donem model-uyumu acisindan temizdir, tasarim-secimi acisindan tam bagimsiz sayilmaz.

### Kapsam genisletmesi: onceki (10 cift) ve yeni (33 cift) yan yana

| Aile | Onceki PBO | Yeni PBO | Onceki DSR | Yeni DSR | Onceki T | Yeni T | Yeni en iyi yapilandirma |
|---|---|---|---|---|---|---|---|
| Kural B1 (harness) | 0,095 | 0,007 | 0,000 | 0,000 | 1946 | 1946 | `B1@4h/BRK_ATR=0.3/f1/s0` |
| Kural F1 (harness) | 0,003 | 0,000 | 0,000 | 0,000 | 1946 | 1946 | `F1@1d/REJ_MIN=0.7/f1/s0` |
| Kural H2 (harness) | 0,051 | 0,068 | 0,000 | 0,000 | 1946 | 1946 | `H2@4h/trail_atr=2.5/f1/s0` |
| ML M1@1h (egitim-disi) | 0,003 | 0,004 | 0,004 | 0,001 | 1110 | 1110 | `M1@1h/thr_x1/f1/s0` |
| Kural R1 (harness) | 0,107 | 0,388 | 0,065 | 0,000 | 1946 | 1946 | `R1@1d/range_target_frac=0.6/f2/s0` |
| Kural S1 (harness) | 0,153 | 0,177 | 0,000 | 0,000 | 1946 | 1946 | `S1@1d/trail_atr=3.5/f1/s0` |
| Kural T1 (harness) | 0,325 | 0,514 | 0,756 | 0,592 | 1946 | 1946 | `T1@1d/trail_atr=2.5/f1/s0` |
| Kural TF1 (harness) | 0,020 | 0,033 | 0,000 | 0,000 | 1946 | 1946 | `TF1@1d/trail_atr=3.5/f1/s0` |
| TUM KUME | 0,111 | 0,085 | 0,000 | 0,000 | 1946 | 1946 | `h:TF1@1d/trail_atr=3.5/f1/s0` |

### Disarida birakilanlar

- `M1@4h`: gonderilen paket egitim penceresi {'end': '2026-04-22T20:00:00+00:00', 'start': '2021-01-11T12:00:00+00:00'} tum holdout oncesi tarihsel veriyi kapsar; egitim-disi donem yok (sizinti olurdu)

Calisma suresi: toplam 488.2 sn (4 cekirdek; kurulum basina: B1 88.2 sn, F1 128.2 sn, H2 97.2 sn, M1 12.3 sn, R1 12.8 sn, S1 51.5 sn, T1 8.8 sn, TF1 89.3 sn).

## Varlik sinifi dokumu — 23.11 degerlendirmesi icin

Yalniz olcum: kol ayari, agirlik, config ve motor degismedi; karar kapisi degildir. Uretim: `python research/pbo_sinif.py` (`pbo_rapor.py` dosyayi bastan yazar; bu komut ondan SONRA kosulur) (seed 0, tek komut; holdout 2026-05-01 oncesi). Kural ve sinif tablosu asagida; hepsi sonuc gorulmeden once betiğe yazildi.

**Ne olduklari.** `T1` / `R1`: kagit kural ailesi kurulumlari (trend / aralik). `r02` ve `r03`: R1 ailesi degil, ML-1 uzun-yon filtre tarifleri — `ml1-r02-long-ctx-1r` (lojistik + LightGBM, 40 ozellik, 1R/72 mum etiketi) ve `ml1-r03-long-regime8` (ayni, 8 ozellik, sig LightGBM); `docs/ml/r02-r03-on-kayit.md`, `research/ml/{r02,r03}/`, `research/ml_trial_registry.csv`. Ikisi de kapida RED (r02: IC rho -0,034).

**Sinif kaynagi** (`config/engine.paper.json` `clusters`): kripto 20 cift (BTC, ETH, XRP, BNB, SOL, DOGE, ADA, TRX, LINK, AVAX, HYPE, BCH, XLM, SUI, HBAR, LTC, TON, 1000SHIB, DOT, XMR); hisse 20 cift (NVDA, MSFT, AAPL, GOOGL, AMZN, META, AVGO, TSLA, BRKB, JPM, LLY, WMT, V, ORCL, XOM, NFLX, PLTR, COST, AMD, HD); emtia 4 cift (XAU, XAG, BZ, COPPER).
Tarihsel mumu olmayan 11 hisse cifti kapsam disi: BRKB, JPM, LLY, WMT, V, ORCL, XOM, NFLX, COST, AMD, HD.

**Onceden yazili kural.** T >= 128 gun -> n_splits 16; 64 <= T < 128 -> n_splits 8; T < 64 -> hesaplanmadi. T = sinifin ilk sifirdan farkli R'li gunu..2026-04-30; pencere oncesi sifir gunler dahil degil. Sabit sutunlar CSCV'den cikar, deneme sayisinda kalir; max_combinations 2000, olcut Sharpe, DSR en iyi tam-pencere Sharpe'li yapilandirma icin sinifin tum yapilandirma sayisiyla. Pencere kirpmasi nedeniyle kripto T'si, mevcut §1 tablosundaki (2021-01-01..) T'den kisa olabilir; mevcut tablodaki aile-ustu degerlerle birebir karsilastirilmaz.

| Kurulum | Sinif | Cift (verisi olan) | Yapilandirma (kullanilan) | T (gun) | n_splits | PBO | Medyan OOS goreli sira | En iyi IS yapilandirma (islem) | Yillik SR | DSR | Not |
|---|---|---|---|---|---|---|---|---|---|---|---|
| T1 | kripto | 20 | 48 (48) | 1896 | 16 | 0,525 | 0,490 | `T1@1d/trail_atr=2.5/f1/s0` (223) | 0,97 | 0,591 | asiri uyum riski yuksek |
| T1 | hisse | 9 | 24 | 38 | - | - | - | - | - | - | hesaplanmadi: T=38 < 64 (kural) |
| T1 | emtia | 4 | 24 (24) | 64 | 8 | 0,514 | 0,480 | `T1@4h/pullback_ema=20/f1/s0` (10) | 2,89 | 0,337 | asiri uyum riski yuksek |
| R1 | kripto | 20 | 56 (52) | 1888 | 16 | 0,321 | 0,585 | `R1@1d/range_target_frac=0.6/f1/s0` (1) | -0,44 | 0,000 | asiri uyum riski dusuk-orta |
| R1 | hisse | 9 | 28 | 0 | - | - | - | - | - | - | hesaplanmadi: hic islem yok |
| R1 | emtia | 4 | 28 | 0 | - | - | - | - | - | - | hesaplanmadi: hic islem yok |
| ML r02 | kripto | 10 | 12 (9) | 1574 | 16 | 0,581 | 0,500 | `p_logistic@0.70` | -0,12 | 0,085 | asiri uyum riski yuksek |
| ML r02 | hisse | 0 | 0 | 0 | - | - | - | - | - | - | uretilemedi: OOF yalniz 10 kripto cift icerir; bu sinifta cift/alinan satir yok (ML-1 egitim korpusu bu sinifi kapsamadi) |
| ML r02 | emtia | 0 | 0 | 0 | - | - | - | - | - | - | uretilemedi: OOF yalniz 10 kripto cift icerir; bu sinifta cift/alinan satir yok (ML-1 egitim korpusu bu sinifi kapsamadi) |
| ML r03 | kripto | 10 | 12 (8) | 1574 | 16 | 0,664 | 0,333 | `p_logistic@0.70` | 0,21 | 0,304 | asiri uyum riski yuksek |
| ML r03 | hisse | 0 | 0 | 0 | - | - | - | - | - | - | uretilemedi: OOF yalniz 10 kripto cift icerir; bu sinifta cift/alinan satir yok (ML-1 egitim korpusu bu sinifi kapsamadi) |
| ML r03 | emtia | 0 | 0 | 0 | - | - | - | - | - | - | uretilemedi: OOF yalniz 10 kripto cift icerir; bu sinifta cift/alinan satir yok (ML-1 egitim korpusu bu sinifi kapsamadi) |

PBO < 0,5 ise "dusuk-orta", aksi "yuksek" yazilir (bilgi amacli). Dusuk PBO secim kararliligidir, karlilik degildir; DSR ~0 deneme sayisi duzeltmesinden sonra pozitif beklenti gorunmedigini belirtir. Hisse/emtia kolonlari ayni sinyal akisinin maliyet/parametre kopyalari oldugundan yuksek olcude iliskilidir ve sinif basina islem sayisi azdir (kisa pencere): PBO/DSR bu siniflarda dusuk gucle okunmali, kesin hukum degil.

**Tutarlilik:** siniflarin toplami `research/arm_series/{T1,R1}.parquet` ile T1: maks fark 1.88e-06, R1: maks fark 2.37e-07 (float32 yuvarlamasi).

