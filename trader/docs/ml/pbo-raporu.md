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
| TUM KUME | 48 (32) | 1574 | 0,608 | 0,424 | `T1:s2_base_v1b` | 0,40 | 0,100 | asiri uyum riski yuksek |

PBO < 0,5 ise "asiri uyum riski dusuk-orta", aksi "yuksek" yazilir; esik bilgi amaclidir. DSR, en iyi (tam orneklem Sharpe) yapilandirma icin, o ailedeki tum yapilandirma sayisiyla (elenenler ve sabit sutunlar dahil) hesaplanir. Yillik SR = gunluk SR x sqrt(365).

## 2. Yontem

- `trader_core.stats.pbo_cscv`, `n_splits=16`, `max_combinations=2000`, `seed=0`, olcut Sharpe; `trader_ml.gate.pbo_for` deseni (ML ailelerinde yapilandirma = model x esik, satir = gun, deger = alinan islemlerin gunluk net R toplami).
- Kural ailelerinde yapilandirma = bir deneme kosusundaki kurulumun (T1, R1) gunluk R toplami (cikis gunune gore); kosular maliyet kolu, dolum modeli ve tetik zaman dilimi bakimindan farklidir. Ortak pencere IS 2024-11-01..2025-10-31 (365 gun, islemsiz gun = 0).
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
| TUM KUME | yukaridaki tum yapilandirmalar, ortak gun izgarasinda (etkin olmayan gun = 0 R) |

Kayit dosyalari (`research/trial_registry.csv`, `research/ml_trial_registry.csv`, `research/runs/*.json`) yalniz toplu istatistik tasir (gunluk getiri serisi yok); gunluk seriler `var/backtests/*/trades.csv` defterlerinden ve ML `oof_predictions.parquet` dosyalarindan uretildi. Yeni backtest kosulmadi.

## 4. Eksik kalan aileler

- `config/engine.paper.json` `arms` icinde defteri olan kurulumlar (kurulum duzeyinde): T1@15m, T1@1h, R1@15m, R1@1h.
- Deneme kaydi / defteri **olmayan** 28 kurulum: T1@4h, T1@1d, R1@4h, R1@1d, TF1@15m, TF1@1h, TF1@4h, TF1@1d, B1@15m, B1@1h, B1@4h, B1@1d, H2@15m, H2@1h, H2@4h, H2@1d, S1@15m, S1@1h, S1@4h, S1@1d, F1@15m, F1@1h, F1@4h, F1@1d, M1@1h, M1@4h, C1@1h, C1@4h. Bunlar icin PBO hesaplanmadi; deneme uydurulmadi. Yeniden uretim, uzun donemli motor kosulari gerektirir (ucuz degil).
- M1 (LightGBM/ridge onerici) adaylari: `research/paper_models.csv` ve `research/pa_proposer_build.py` yalniz egitim kaydi tutar (model sha256, satir sayisi); walk-forward getiri serisi ya da deneme kaydi yok -> PBO hesaplanmadi.
- Defter ailelerinde yalniz `T1` ve `R1` var; `T1` defterlerinin bir kismi (`ml_cand_v1b_native`, `s2_base_v1b`) farkli strateji surumu (`price_action_v1`) ve 10 ciftlik evrenle kosulmustur.

Atlanan defterler:
- `1h_WF_f1_s0_compat`: donem 2025-11-01..2026-05-01 ortak IS penceresini kapsamiyor
- `s2_explore_tmp`: trades.csv/meta.json yok
