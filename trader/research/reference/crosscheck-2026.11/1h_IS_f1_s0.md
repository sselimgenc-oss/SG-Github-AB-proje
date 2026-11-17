# Capraz dogrulama: 1h_IS_f1_s0

Sonuc: **RED** (aciklanamayan: 0)

| Duzey | Olcut | Deger | Kabul |
|---|---|---|---|
| A kararlar | ortak anahtarda esit | 884/884 (100.00%); yalniz ref 11, yalniz motor 110 | evet |
| B girisler | eslesen/ref (anahtar+fiyat+boyut) | 78/630 (12.38%); yalniz anahtar 90.32%, anahtar+fiyat 90.32% | hayir |
| C cikislar | eslesen girislerde | 547/569 (96.13%; kesin 96.13%, trail +-1: 0) | hayir |
| D sum_R | ref 10.8805 / motor 0.83323 (fark -10.05, tol 0.2176) | | hayir |
| D fees | ref 422.606 / motor 411.029 (fark -11.58, tol 8.452) | | hayir |
| D funding | ref 13.2036 / motor 14.2614 (fark 1.058, tol 0.6602) | | hayir |
| D n_trades | ref 630 / motor 598 (fark -32, tol 6.3) | | hayir |

Sinif sayilari: aggregate=4, chained_after_first=1194, exit_before_entry=9, funding_boundary=80, gap_fill=19, margin_accounting=11, open_at_end=1, price_rounding=2, qty_rounding=1
unexplained: 0

## Ilk sapma
B ('XRP/USDT', 'short', '2024-12-22T12:00:00.000Z') qty: ref=289.8 motor=289.9 sinif=exit_before_entry | karar boyutu ref=289.8 motor=289.9: ozsermaye/risk durumu farki; ayni adimda cikan referans islem(ler) [('SOL/USDT', 'short', '2024-12-21T09:00:00.000Z')]: referans cikisi gerceklestirir (realized), motor son mark'ta tutar (cikis-giristen-once modeli)

## Farklar

| duzey | anahtar | alan | ref | motor | sinif | kanit |
|---|---|---|---|---|---|---|
| B | ('XRP/USDT', 'short', '2024-12-22T12:00:00.000Z') | qty | 289.8 | 289.9 | exit_before_entry | karar boyutu ref=289.8 motor=289.9: ozsermaye/risk durumu farki; ayni adimda cikan referans islem(ler) [('SOL/USDT', 'short', '2024-12-21T09:00:00.000Z')]: refe |
| B | ('TRX/USDT', 'short', '2024-12-22T12:00:00.000Z') | entry_missing_in_engine | 0.24788 | None | chained_after_first | motor karari: skipped/risk_denied (günlük zarar bütçesi aşılır) |
| B | ('ETH/USDT', 'short', '2024-12-23T05:00:00.000Z') | size_ratio | 14.576257583424477 | 14.697726396619682 | chained_after_first | planned_risk ref=14.5763 eng=14.6977 (rel 8.33e-03); ozsermaye tahmini ref=1041.98657358 motor(karar ani)=1051.9035006128568 |
| B | ('ETH/USDT', 'short', '2024-12-23T05:00:00.000Z') | qty | 0.24 | 0.242 | chained_after_first | karar boyutu ref=0.24 motor=0.242: ozsermaye/risk durumu farki |
| B | ('BTC/USDT', 'short', '2024-12-23T12:00:00.000Z') | entry_missing_in_engine | 95899.4 | None | chained_after_first | motor karari: skipped/risk_denied (günlük zarar bütçesi aşılır) |
| B | ('ETH/USDT', 'short', '2024-12-23T18:00:00.000Z') | size_ratio | 14.819376133813224 | 14.678908113587504 | chained_after_first | planned_risk ref=14.8194 eng=14.6789 (rel 9.48e-03); ozsermaye tahmini ref=1064.41991336 motor(karar ani)=1051.2754159104902 |
| B | ('ETH/USDT', 'short', '2024-12-23T18:00:00.000Z') | qty | 0.211 | 0.208 | chained_after_first | karar boyutu ref=0.211 motor=0.209: ozsermaye/risk durumu farki |
| B | ('ADA/USDT', 'short', '2024-12-24T07:00:00.000Z') | size_ratio | 14.31724680844089 | 14.215111702253 | chained_after_first | planned_risk ref=14.3172 eng=14.2151 (rel 7.13e-03); ozsermaye tahmini ref=1023.4023359500001 motor(karar ani)=1015.5340502504902 |
| B | ('ADA/USDT', 'short', '2024-12-24T07:00:00.000Z') | qty | 546.7 | 542.8 | chained_after_first | karar boyutu ref=546.7 motor=542.8: ozsermaye/risk durumu farki |
| B | ('LINK/USDT', 'short', '2024-12-24T16:00:00.000Z') | qty | 29.54 | 29.53 | chained_after_first | karar boyutu ref=29.55 motor=29.53: ozsermaye/risk durumu farki |
| D | ('LINK/USDT', 'short', '2024-12-24T16:00:00.000Z') | funding_paid | -0.07278065200000002 | 0.0 | funding_boundary | sinir noktalari (giris/cikis anindaki 00/08/16): referans giris x1, cikis x1; motor giris x0, cikis x1 (veriden yeniden hesapla birebir uyumlu; 03 §5 `opened_ts |
| B | ('LINK/USDT', 'short', '2024-12-24T19:00:00.000Z') | entry_missing_in_engine | 24.873 | None | chained_after_first | motor karari: skipped/risk_denied (günlük zarar bütçesi aşılır) |
| B | ('ADA/USDT', 'long', '2024-12-26T14:00:00.000Z') | size_ratio | 12.808270504011517 | 12.972390194642237 | chained_after_first | planned_risk ref=12.8083 eng=12.9724 (rel 1.28e-02); ozsermaye tahmini ref=963.30558842 motor(karar ani)=975.5936019334328 |
| B | ('ADA/USDT', 'long', '2024-12-26T14:00:00.000Z') | qty | 1108.1 | 1122.4 | chained_after_first | karar boyutu ref=1108.2 motor=1122.4: ozsermaye/risk durumu farki |
| B | ('SOL/USDT', 'short', '2024-12-27T13:00:00.000Z') | size_ratio | 13.280496399762567 | 13.47021777690203 | chained_after_first | planned_risk ref=13.2805 eng=13.4702 (rel 1.43e-02); ozsermaye tahmini ref=951.50490039 motor(karar ani)=963.6406263469097 |
| B | ('SOL/USDT', 'short', '2024-12-27T13:00:00.000Z') | qty | 2.8 | 2.84 | chained_after_first | karar boyutu ref=2.8 motor=2.84: ozsermaye/risk durumu farki |
| B | ('XRP/USDT', 'short', '2024-12-27T13:00:00.000Z') | size_ratio | 13.31012041032594 | 13.490371506403054 | chained_after_first | planned_risk ref=13.3101 eng=13.4904 (rel 1.35e-02); ozsermaye tahmini ref=951.50490039 motor(karar ani)=963.6406263469097 |
| B | ('XRP/USDT', 'short', '2024-12-27T13:00:00.000Z') | qty | 280.6 | 284.4 | chained_after_first | karar boyutu ref=280.6 motor=284.4: ozsermaye/risk durumu farki |
| C | ('XRP/USDT', 'short', '2024-12-27T13:00:00.000Z') | exit_price | 2024-12-28T14:00:00.000Z trail_stop 2.1735 | 2024-12-28T14:00:00.000Z trail_stop 2.1717 | gap_fill | cikis fiyati ref=2.1735 eng=2.1717 rel=8.28e-04 |
| B | ('DOGE/USDT', 'long', '2024-12-28T00:00:00.000Z') | size_ratio | 12.217817963218138 | 12.379861066743981 | chained_after_first | planned_risk ref=12.2178 eng=12.3799 (rel 1.33e-02); ozsermaye tahmini ref=985.9515203899999 motor(karar ani)=998.0016260206162 |
| B | ('DOGE/USDT', 'long', '2024-12-28T00:00:00.000Z') | qty | 3159.2 | 3201.1 | chained_after_first | karar boyutu ref=3159.2 motor=3201.1: ozsermaye/risk durumu farki |
| D | ('DOGE/USDT', 'long', '2024-12-28T00:00:00.000Z') | funding_paid | 0.49121682757057855 | 0.4288146803897913 | funding_boundary | sinir noktalari (giris/cikis anindaki 00/08/16): referans giris x1, cikis x2; motor giris x0, cikis x1 (veriden yeniden hesapla birebir uyumlu; 03 §5 `opened_ts |
| B | ('TRX/USDT', 'short', '2024-12-28T19:00:00.000Z') | size_ratio | 12.747774081676795 | 12.92477166751199 | chained_after_first | planned_risk ref=12.7478 eng=12.9248 (rel 1.39e-02); ozsermaye tahmini ref=996.80016272 motor(karar ani)=1009.459526813491 |
| B | ('TRX/USDT', 'short', '2024-12-28T19:00:00.000Z') | qty | 3874.8 | 3928.6 | chained_after_first | karar boyutu ref=3874.8 motor=3928.6: ozsermaye/risk durumu farki |
| B | ('LINK/USDT', 'short', '2024-12-28T19:00:00.000Z') | size_ratio | 13.924934450106061 | 14.129369309902085 | chained_after_first | planned_risk ref=13.9249 eng=14.1294 (rel 1.47e-02); ozsermaye tahmini ref=996.80016272 motor(karar ani)=1009.459526813491 |
| B | ('LINK/USDT', 'short', '2024-12-28T19:00:00.000Z') | qty | 23.83 | 24.19 | chained_after_first | karar boyutu ref=23.84 motor=24.19: ozsermaye/risk durumu farki |
| B | ('LINK/USDT', 'short', '2024-12-29T00:00:00.000Z') | size_ratio | 13.803904156247295 | 14.00102667796908 | chained_after_first | planned_risk ref=13.8039 eng=14.001 (rel 1.43e-02); ozsermaye tahmini ref=988.2872635700002 motor(karar ani)=1000.3012619784912 |
| B | ('LINK/USDT', 'short', '2024-12-29T00:00:00.000Z') | qty | 25.91 | 26.28 | chained_after_first | karar boyutu ref=25.91 motor=26.28: ozsermaye/risk durumu farki |
| D | ('LINK/USDT', 'short', '2024-12-29T00:00:00.000Z') | funding_paid | -0.19870065388815358 | -0.16902458790156002 | funding_boundary | sinir noktalari (giris/cikis anindaki 00/08/16): referans giris x1, cikis x1; motor giris x0, cikis x1 (veriden yeniden hesapla birebir uyumlu; 03 §5 `opened_ts |
| B | ('AVAX/USDT', 'short', '2024-12-29T05:00:00.000Z') | size_ratio | 13.782438414412292 | 13.980272458638307 | chained_after_first | planned_risk ref=13.7824 eng=13.9803 (rel 1.44e-02); ozsermaye tahmini ref=986.8647726700001 motor(karar ani)=998.9742309884498 |
| B | ('AVAX/USDT', 'short', '2024-12-29T05:00:00.000Z') | qty | 20.8 | 21.2 | chained_after_first | karar boyutu ref=20.9 motor=21.2: ozsermaye/risk durumu farki |
| B | ('AVAX/USDT', 'short', '2024-12-30T04:00:00.000Z') | size_ratio | 13.554461550329588 | 13.728236698410738 | chained_after_first | planned_risk ref=13.5545 eng=13.7282 (rel 1.28e-02); ozsermaye tahmini ref=972.99342004 motor(karar ani)=986.0125076731215 |
| B | ('AVAX/USDT', 'short', '2024-12-30T04:00:00.000Z') | qty | 15.6 | 15.8 | chained_after_first | karar boyutu ref=15.6 motor=15.8: ozsermaye/risk durumu farki |
| B | ('DOGE/USDT', 'short', '2024-12-30T05:00:00.000Z') | entry_missing_in_engine | 0.31678 | None | chained_after_first | motor karari: skipped/risk_denied (günlük zarar bütçesi aşılır) |
| A | ('DOGE/USDT', 'short', 'T1', '1h', '2024-12-30T11:00:00.000Z') | decision_only_in_engine | None | None | chained_after_first | yalniz motorda karar; genelde onceki islem sapmasi yuzunden pozisyon durumu farkli |
| B | ('BNB/USDT', 'long', '2024-12-30T23:00:00.000Z') | size_ratio | 13.505176320977204 | 13.752977721362107 | chained_after_first | planned_risk ref=13.5052 eng=13.753 (rel 1.83e-02); ozsermaye tahmini ref=966.65348844 motor(karar ani)=984.1758074353637 |
| B | ('BNB/USDT', 'long', '2024-12-30T23:00:00.000Z') | qty | 1.09 | 1.1 | chained_after_first | karar boyutu ref=1.09 motor=1.11: ozsermaye/risk durumu farki |
| B | ('XRP/USDT', 'short', '2024-12-31T23:00:00.000Z') | size_ratio | 13.460711626230102 | 13.722730126798787 | chained_after_first | planned_risk ref=13.4607 eng=13.7227 (rel 1.95e-02); ozsermaye tahmini ref=963.1436884400001 motor(karar ani)=980.2861738697438 |
| B | ('XRP/USDT', 'short', '2024-12-31T23:00:00.000Z') | qty | 344.1 | 350.9 | chained_after_first | karar boyutu ref=344.2 motor=350.9: ozsermaye/risk durumu farki |
| B | ('TRX/USDT', 'short', '2025-01-01T05:00:00.000Z') | entry_missing_in_engine | 0.25532 | None | chained_after_first | motor karari: skipped/risk_denied (günlük zarar bütçesi aşılır) |
| A | ('ADA/USDT', 'short', 'T1', '1h', '2025-01-01T08:00:00.000Z') | decision_only_in_engine | None | None | chained_after_first | yalniz motorda karar; genelde onceki islem sapmasi yuzunden pozisyon durumu farkli |
| A | ('DOGE/USDT', 'short', 'T1', '1h', '2025-01-01T08:00:00.000Z') | decision_only_in_engine | None | None | chained_after_first | yalniz motorda karar; genelde onceki islem sapmasi yuzunden pozisyon durumu farkli |
| A | ('TRX/USDT', 'short', 'T1', '1h', '2025-01-01T08:00:00.000Z') | decision_only_in_engine | None | None | chained_after_first | yalniz motorda karar; genelde onceki islem sapmasi yuzunden pozisyon durumu farkli |
| B | ('TRX/USDT', 'short', '2025-01-01T08:00:00.000Z') | entry_extra_in_engine | None | 0.25542 | chained_after_first | motorda fazla giris |
| B | ('BNB/USDT', 'long', '2025-01-03T09:00:00.000Z') | size_ratio | 6.5925289000501754 | 6.740122830648316 | chained_after_first | planned_risk ref=6.59253 eng=6.74012 (rel 2.24e-02); ozsermaye tahmini ref=940.08236772 motor(karar ani)=957.589484071349 |
| B | ('BNB/USDT', 'long', '2025-01-03T09:00:00.000Z') | qty | 1.34 | 1.37 | chained_after_first | karar boyutu ref=1.34 motor=1.37: ozsermaye/risk durumu farki |
| B | ('BNB/USDT', 'short', '2025-01-03T19:00:00.000Z') | size_ratio | 6.253083415466114 | 6.346413018682027 | chained_after_first | planned_risk ref=6.25308 eng=6.34641 (rel 1.49e-02); ozsermaye tahmini ref=957.95003492 motor(karar ani)=975.8571736713491 |
| B | ('BNB/USDT', 'short', '2025-01-03T19:00:00.000Z') | qty | 1.34 | 1.36 | chained_after_first | karar boyutu ref=1.34 motor=1.36: ozsermaye/risk durumu farki |
| B | ('BNB/USDT', 'long', '2025-01-04T18:00:00.000Z') | size_ratio | 10.12327548035127 | 10.35162004005844 | chained_after_first | planned_risk ref=10.1233 eng=10.3516 (rel 2.26e-02); ozsermaye tahmini ref=952.66512182 motor(karar ani)=970.493381271349 |
| B | ('BNB/USDT', 'long', '2025-01-04T18:00:00.000Z') | qty | 1.33 | 1.36 | chained_after_first | karar boyutu ref=1.33 motor=1.36: ozsermaye/risk durumu farki |
| B | ('XRP/USDT', 'long', '2025-01-05T23:00:00.000Z') | size_ratio | 13.204670390245438 | 13.452963337754328 | chained_after_first | planned_risk ref=13.2047 eng=13.453 (rel 1.88e-02); ozsermaye tahmini ref=943.48859397 motor(karar ani)=961.109864071349 |
| B | ('XRP/USDT', 'long', '2025-01-05T23:00:00.000Z') | qty | 292.5 | 298.0 | chained_after_first | karar boyutu ref=292.5 motor=298.0: ozsermaye/risk durumu farki |
| B | ('LINK/USDT', 'long', '2025-01-07T02:00:00.000Z') | size_ratio | 12.90297736781424 | 13.150238177756709 | chained_after_first | planned_risk ref=12.903 eng=13.1502 (rel 1.92e-02); ozsermaye tahmini ref=921.9383152400001 motor(karar ani)=939.4129065204331 |
| B | ('LINK/USDT', 'long', '2025-01-07T02:00:00.000Z') | qty | 25.57 | 26.05 | chained_after_first | karar boyutu ref=25.57 motor=26.06: ozsermaye/risk durumu farki |
| B | ('SOL/USDT', 'long', '2025-01-07T04:00:00.000Z') | size_ratio | 9.158438667052499 | 9.332885117853497 | chained_after_first | planned_risk ref=9.15844 eng=9.33289 (rel 1.90e-02); ozsermaye tahmini ref=914.1650352400001 motor(karar ani)=931.1835682454332 |
| B | ('SOL/USDT', 'long', '2025-01-07T04:00:00.000Z') | qty | 4.2 | 4.28 | chained_after_first | karar boyutu ref=4.2 motor=4.28: ozsermaye/risk durumu farki |
| B | ('LINK/USDT', 'long', '2025-01-07T07:00:00.000Z') | size_ratio | 12.658218512607622 | 12.905665992800154 | chained_after_first | planned_risk ref=12.6582 eng=12.9057 (rel 1.95e-02); ozsermaye tahmini ref=905.2818207099999 motor(karar ani)=921.9775745954331 |
| B | ('LINK/USDT', 'long', '2025-01-07T07:00:00.000Z') | qty | 29.67 | 30.25 | chained_after_first | karar boyutu ref=29.67 motor=30.25: ozsermaye/risk durumu farki |
| B | ('XRP/USDT', 'long', '2025-01-07T14:00:00.000Z') | size_ratio | 11.482850523945094 | 11.702108444478691 | chained_after_first | planned_risk ref=11.4829 eng=11.7021 (rel 1.91e-02); ozsermaye tahmini ref=889.39385754 motor(karar ani)=906.2459275476431 |
| B | ('XRP/USDT', 'long', '2025-01-07T14:00:00.000Z') | qty | 366.6 | 373.6 | chained_after_first | karar boyutu ref=366.6 motor=373.6: ozsermaye/risk durumu farki |
... 1261 fark daha (json'da)
