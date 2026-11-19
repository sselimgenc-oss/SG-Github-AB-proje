# PBO raporu (holdout oncesi, yalniz rapor)

Bu rapor **bilgi amaclidir**: karar kapisi degildir, hicbir islemi ya da kurulumu engellemez. Yalniz `2026-05-01` oncesi veri kullanildi; holdout satirlarina dokunulmadi. Uretim: `python research/pbo_rapor.py` (seed 0, sabit).

## 1. Tablo

| Aile | Yapilandirma (kullanilan) | T (gun) | PBO | Medyan OOS goreli sira | En iyi IS yapilandirma | Yillik SR | DSR | Yorum |
|---|---|---|---|---|---|---|---|---|
| Kural R1 | 5 (5) | 365 | 0,516 | 0,500 | `R1:15m_IS_f1_s0_compat` | 0,06 | 0,209 | asiri uyum riski yuksek |
| Kural T1 | 7 (7) | 365 | 0,251 | 0,750 | `T1:s2_base_v1b` | 0,83 | 0,312 | asiri uyum riski dusuk-orta |
| ML 19c | 12 (3) | 240 | 0,323 | 0,750 | `p_lgbm@0.45` | 0,80 | 0,024 | asiri uyum riski dusuk-orta |
| ML r02 | 12 (9) | 1574 | 0,581 | 0,500 | `p_logistic@0.70` | -0,12 | 0,085 | asiri uyum riski yuksek |
| ML r03 | 12 (8) | 1574 | 0,664 | 0,333 | `p_logistic@0.70` | 0,21 | 0,304 | asiri uyum riski yuksek |
| Kural B1 (harness) | 112 (112) | 1946 | 0,095 | 0,717 | `B1@4h/TARGET_R=2.5/f1/s0` | 0,20 | 0,000 | asiri uyum riski dusuk-orta |
| Kural F1 (harness) | 112 (112) | 1946 | 0,003 | 0,673 | `F1@1d/REJ_MIN=0.5/f1/s0` | 0,31 | 0,000 | asiri uyum riski dusuk-orta |
| Kural H2 (harness) | 112 (112) | 1946 | 0,051 | 0,717 | `H2@1d/trail_atr=3.5/f1/s0` | 0,78 | 0,000 | asiri uyum riski dusuk-orta |
| ML M1@1h (egitim-disi) | 12 (12) | 1110 | 0,003 | 0,769 | `M1@1h/thr_x1/f1/s0` | 0,03 | 0,004 | asiri uyum riski dusuk-orta |
| Kural R1 (harness) | 56 (52) | 1946 | 0,107 | 0,849 | `R1@4h/stop_buffer_atr=0.5/f1/s0` | 0,07 | 0,065 | asiri uyum riski dusuk-orta |
| Kural S1 (harness) | 112 (112) | 1946 | 0,153 | 0,681 | `S1@4h/trail_atr=3.5/f1/s0` | 0,41 | 0,000 | asiri uyum riski dusuk-orta |
| Kural T1 (harness) | 48 (48) | 1946 | 0,325 | 0,765 | `T1@1d/trail_atr=2.5/f1/s0` | 1,06 | 0,756 | asiri uyum riski dusuk-orta |
| Kural TF1 (harness) | 112 (112) | 1946 | 0,020 | 0,805 | `TF1@1d/trail_atr=3.5/f1/s0` | 1,19 | 0,000 | asiri uyum riski dusuk-orta |
| TUM KUME | 724 (704) | 1946 | 0,111 | 0,913 | `h:TF1@1d/trail_atr=3.5/f1/s0` | 1,19 | 0,000 | asiri uyum riski dusuk-orta |

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
| Kural R1 | var/backtests/*/trades.csv (5 defter, IS 2024-11-01..2025-10-31) |
| Kural T1 | var/backtests/*/trades.csv (7 defter, IS 2024-11-01..2025-10-31) |
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

- `config/engine.paper.json` `arms` icinde motor defteri olan kurulumlar (kurulum duzeyinde): T1@15m, T1@1h, R1@15m, R1@1h.
- Hafif donanim serisi olan kurulumlar (25): T1@4h, T1@1d, R1@4h, R1@1d, TF1@15m, TF1@1h, TF1@4h, TF1@1d, B1@15m, B1@1h, B1@4h, B1@1d, H2@15m, H2@1h, H2@4h, H2@1d, S1@15m, S1@1h, S1@4h, S1@1d, F1@15m, F1@1h, F1@4h, F1@1d, M1@1h.
- Seri / defter **olmayan** 3 kurulum: M1@4h, C1@1h, C1@4h. Bunlar icin PBO hesaplanmadi; deneme uydurulmadi.
  - `M1@4h`: gonderilen paket egitim penceresi {'end': '2026-04-22T20:00:00+00:00', 'start': '2021-01-11T12:00:00+00:00'} tum holdout oncesi tarihsel veriyi kapsar; egitim-disi donem yok (sizinti olurdu)
  - `C1@1h`: CT kadro verisi yalniz canli (var/ct/kadro_yon.json yok, tarihsel kayit yok); seri uretilemez, uydurulmadi
  - `C1@4h`: ayni neden
- M1 (LightGBM/ridge onerici) adaylari: `research/paper_models.csv` ve `research/pa_proposer_build.py` yalniz egitim kaydi tutar (model sha256, satir sayisi); gonderilen paketin kendi egitim penceresi icinde degerlendirme sizinti olur, bu yuzden yalniz egitim-disi donem kullanilir (asagida bolum 5).
- Defter ailelerinde yalniz `T1` ve `R1` var; `T1` defterlerinin bir kismi (`ml_cand_v1b_native`, `s2_base_v1b`) farkli strateji surumu (`price_action_v1`) ve 10 ciftlik evrenle kosulmustur.

## 5. Hafif donanim serileri (`research/arm_harness.py`)

Amac: tam kagit backtest (~15 sn / 15 dk adim) cok yillik kosuya uygun degil; her kurulumun KENDI `compute()` fonksiyonu holdout oncesi tarihsel barlarda bir kez cagrilir, adaylar muhafazakar bir bar-yolu simulatoruyle cozulur, gunluk R toplami (cikis gunune gore, cift toplami) yazilir. Sinyal mantigi yeniden yazilmadi; simulator `trader_core.signals` yardimcilarini (`regime_flip_exit`, `TRAIL_START_R`, `TIME_STOP_BARS`) kullanir, hedef modu `trader_core.counterfactual.replay` ile (maliyetsiz) ve iz-stop `signals.trail_stop_path` ile testte karsilastirilir.

- Veri: `var/history` feather, okuma aninda `date < 2026-05-01` suzgeci; gun izgarasi 2021-01-01..2026-04-30; 10 cift (BTC/USDT, ETH/USDT, BNB/USDT, SOL/USDT, XRP/USDT, DOGE/USDT, ADA/USDT, TRX/USDT, LINK/USDT, AVAX/USDT). `config/engine.paper.json` icindeki 34 cift icin tarihsel mum dosyasi yok (hisse/emtia/diger kripto) ve kapsam disidir.
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
| B1@15m | 3760 | -1277,5 | -0,340 |
| B1@1d | 98 | -14,4 | -0,147 |
| B1@1h | 1109 | -168,2 | -0,152 |
| B1@4h | 373 | -0,1 | -0,000 |
| F1@15m | 16312 | -5808,5 | -0,356 |
| F1@1d | 19 | 3,0 | 0,156 |
| F1@1h | 3538 | -782,5 | -0,221 |
| F1@4h | 243 | -4,7 | -0,019 |
| H2@15m | 10262 | -1943,6 | -0,189 |
| H2@1d | 211 | 39,8 | 0,189 |
| H2@1h | 3446 | -324,4 | -0,094 |
| H2@4h | 1164 | 35,2 | 0,030 |
| R1@1d | 3 | -3,1 | -1,043 |
| R1@4h | 227 | -41,3 | -0,182 |
| S1@15m | 18745 | -2959,0 | -0,158 |
| S1@1d | 342 | 17,0 | 0,050 |
| S1@1h | 4563 | -190,3 | -0,042 |
| S1@4h | 1313 | -49,8 | -0,038 |
| T1@1d | 129 | 59,1 | 0,458 |
| T1@4h | 1054 | 66,7 | 0,063 |
| TF1@15m | 10582 | -2131,4 | -0,201 |
| TF1@1d | 482 | 135,2 | 0,280 |
| TF1@1h | 2748 | -160,4 | -0,058 |
| TF1@4h | 1222 | -9,8 | -0,008 |

### M1 (egitim-disi donem)

Gonderilen `M1@1h` paketinin egitim penceresi 2024-01-16T15:00:00+00:00..2026-04-28T23:00:00+00:00 (egitim satiri `max_rows`=400000 ile yalniz EN SON satirlara kirpilmis); bu pencereden ONCEKI tarihsel veri paketin gormedigi donemdir. Degerlendirme gunleri 2021-01-01..2024-01-15; son sinyal mumu 2024-01-11 21:00:00+00:00 (egitim baslangicindan pencere + ufuk + 2 bar once: etiket/ozellik ortusmesi yok). Paket esigi 0,3700. Uyari: ozellik/etiket tasarimi (1,5 ATR stop, 3 ATR hedef, 48 bar) ve esik niceligi tum tarihsel veri goruldukten sonra secilmis olabilir; bu donem model-uyumu acisindan temizdir, tasarim-secimi acisindan tam bagimsiz sayilmaz.

### Disarida birakilanlar

- `C1@1h`: CT kadro verisi yalniz canli (var/ct/kadro_yon.json yok, tarihsel kayit yok); seri uretilemez, uydurulmadi
- `C1@4h`: ayni neden
- `M1@4h`: gonderilen paket egitim penceresi {'end': '2026-04-22T20:00:00+00:00', 'start': '2021-01-11T12:00:00+00:00'} tum holdout oncesi tarihsel veriyi kapsar; egitim-disi donem yok (sizinti olurdu)

Calisma suresi: toplam 292.4 sn (4 cekirdek; kurulum basina: B1 53.5 sn, F1 72.9 sn, H2 57.9 sn, M1 7.1 sn, R1 7.6 sn, S1 32.9 sn, T1 6.0 sn, TF1 54.5 sn).

Atlanan defterler:
- `1h_WF_f1_s0_compat`: donem 2025-11-01..2026-05-01 ortak IS penceresini kapsamiyor
- `s2_explore_tmp`: trades.csv/meta.json yok
