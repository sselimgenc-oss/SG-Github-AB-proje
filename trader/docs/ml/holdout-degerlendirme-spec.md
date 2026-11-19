# Holdout degerlendirme -- on kayitli yontem (19 Kasim 2026)

Bu belge **sonuc gorulmeden** yazildi. Holdout (2026-05-01 -> 2026-11-01) bu isle OKUNMADI; `research/holdout/muhur.json` `acildi: false` ve degismedi. Betik: `research/holdout_degerlendir.py` (hazir, calistirilmadi). Karar kapisi degildir; gecme olcutu bolum 4 **ONERIDIR, kullanici onayi gerekir** (CANLI-K1 ve adaylik olcutleri kullanici tarafindan askiya alinmistir, `docs/motor/dd12-capraz-varlik-spec.md`).

## 1. Kilit nasil korunur
- `trader_engine/holdout.py` (donuk) degismedi. `check_holdout` motor, backtest, `arm_harness`, egitim ve arastirma yollarinda aynen reddeder; bu is onlara yetki vermez.
- Holdout satirlarini yalniz `holdout_degerlendir.py` icindeki `_oku` okur; baska modul bu betigi iceri alamaz (statik test: `tests/research/test_holdout_degerlendir.py`). Muhur betigi de baska betige iceri alinamaz (`test_holdout_muhur_guard.py`); bu yuzden hash dogrulamasi bagimsiz yeniden yazildi ve referans modulle bayt-esitligi testle sabit.
- Kapilar, sirayla: (1) `muhur.json` var, `acildi is True`, acilis kaydi var; (2) acilis kaydindaki aday kumesi == `--aday-kumesi` (kume olarak); (3) muhur hash dogrulamasi ESIT. 1 ve 2 hicbir veri okumaz; 3 yalniz hash icin okur. Biri tutmazsa sifirdan farkli cikis (2), degerlendirme okumasi yok.
- Gercek `var/history` yalniz gercek `muhur.json` ile kabul edilir. Cikti varsa reddeder (tek seferlik).
- Acma: `research/holdout_muhur.py ac --aday-kumesi "<kume>" --gerekce "..."` (kullanici karari, bir kez). Bu is onu CAGIRMAZ.

## 2. Aday kumesi gosterimi
Virgullu oge listesi: `KURULUM@TF` ya da `KURULUM@TF|varyant` (varsayilan `def`), ornegin `T1@4h,R1@4h`. Gecerli ogeler `arm_harness.GRID` kurulum, zaman dilimi ve on-kayitli varyantlaridir. M1 (paket gerektirir) ve C1 (tarihsel veri yok) bu surumde YOK. Kume sirasiz karsilastirilir.

## 3. Olculer (aday kumesi basina; ayrica oge basina)
- **Seri:** `arm_harness` ile ayni simulator (`simulate`, `Bars`, `candidate_rows`) ve ayni maliyet izgarasi (`COSTS`: ucret x1/x2, kayma 0/5 bp; sutun anahtari `f1|s5`). Oge ve cift toplami, gunluk R (cikis gunune gore), tum takvim gunleri (islemsiz gun = 0). Holdout islemleri holdout baslangicindan sonra GIRILEN islemlerdir (oncesinden tasinan pozisyon yok); veri sonuna kadar bitmeyenler dusulur.
- **Olculer:** toplam R; gunluk Sharpe = ort/std(ddof=1), yillik = x sqrt(365); max drawdown (kumulatif R, tepeden dibe); isabet = R > 0 islem orani; islem sayisi.
- **Holdout oncesi kiyas:** ayni hat, `[2021-01-01, holdout baslangici)`; dusus orani = 1 - holdout/once (Sharpe ve ort. R/gun); once <= 0 ise tanimsiz (`null`).
- **DSR:** `trader_core.stats.deflated_sharpe(sr_gun, n_gun, skew, kurt, n_trials)`; `return_moments`; deneme varyansi varsayilan 1/(n-1). **n_trials = `research/holdout/pbo_ozet.json` "TUM KUME" n_yapilandirma** (betik okur; bu belgenin yazildigi anda 712). Holdout n_gun = 184.
- **Ana maliyet hucresi** `f1|s5`, **stres hucresi** `f2|s5` (sonuctan once sabit; digerleri bilgi).

## 4. Gecme olcutu (ONERI; kullanici onayi gerekir)
Hepsi ana hucre `f1|s5` uzerinde aday kumesi serisi icin:
- H1: holdout gunluk Sharpe > 0;
- H2: DSR >= 0,95 (CANLI-K1 madde 3 ve r02/r03 kapisindaki mevcut cita; 712 deneme ile cok sert, gecmemesi olasi sonuctur; DSR > 0,5 yalniz bilgi olarak raporda gorunur);
- H3: stres hucresi `f2|s5` toplam R > 0.
Uc kontrol de gecerse oneri "GECTI", aksi "KALDI". Dusus orani raporlanir, kapiya girmez. Esik degisikligi sonuctan sonra yapilamaz.

## 5. Cikti
`research/holdout/degerlendirme_<aday>.json` (tum sayilar) ve `.md` (ozet). `<aday>` = ogeler `+` ile birlestirilmis, harf/rakam disi `_`. `research/trial_registry.csv`: on-kayit satiri `holdout-deger-v1_onkayit`.

## 6. Sinirlar
Donuk dosyalar ve `build_registry.py` dokunulmaz; yeni bagimlilik yok; testler sentetik. Holdout bu islerde okunmadi.
