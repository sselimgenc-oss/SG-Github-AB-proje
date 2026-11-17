# Capraz dogrulama: 1h_IS_f1_s0

Sonuc: **RED** (aciklanamayan: 39)

| Duzey | Olcut | Deger | Kabul |
|---|---|---|---|
| A kararlar | ortak anahtarda esit | 883/883 (100.00%); yalniz ref 12, yalniz motor 116 | evet |
| B girisler | eslesen/ref (anahtar+fiyat+boyut) | 114/630 (18.10%); yalniz anahtar 89.68%, anahtar+fiyat 89.68% | hayir |
| C cikislar | eslesen girislerde | 460/565 (81.42%; kesin 80.53%, trail +-1: 5) | hayir |
| D sum_R | ref 10.8805 / motor -2.88344 (fark -13.76, tol 0.2176) | | hayir |
| D fees | ref 422.606 / motor 395.327 (fark -27.28, tol 8.452) | | hayir |
| D funding | ref 13.2036 / motor 13.2308 (fark 0.02721, tol 0.6602) | | evet |
| D n_trades | ref 630 / motor 596 (fark -34, tol 6.3) | | hayir |

Sinif sayilari: aggregate=3, chained_after_first=1155, exit_before_entry=8, funding_boundary=76, gap_fill=44, margin_accounting=9, open_at_end=1, price_rounding=19, qty_rounding=1, same_bar_order=2, trail_timing=5, unexplained=39
unexplained: 39

## Ilk sapma
C ('SOL/USDT', 'short', '2024-12-21T09:00:00.000Z') exit_ts: ref=2024-12-22T12:00:00.000Z trail_stop 186.741 motor=2024-12-22T12:30:00.000Z trail_stop 187.069 sinif=unexplained | exit_ts ref=2024-12-22T12:00:00.000Z eng=2024-12-22T12:30:00.000Z reason ref=trail_stop eng=trail_stop | bars=[{'open': '2024-12-22 11:00:00+00:00', 'o': np.float64(185.5), 'h': np.float64(186.86), 'l': np.float64(185.26), 'c': np.float64(186.56)}, {'open': '2024-12-22 12:00:00+00:00', 'o': np.float64(186.55), 'h': np.float64(187.77), 'l': np.float64(185.43), 'c': np.float64(185.8)}, {'open': '2024-12-22 13:00:00+00:00', 'o': np.float64(185.8), 'h': np.float64(186.75), 'l': np.float64(184.37), 'c': np.float64(184.71)}]

## Farklar

| duzey | anahtar | alan | ref | motor | sinif | kanit |
|---|---|---|---|---|---|---|
| C | ('SOL/USDT', 'short', '2024-12-21T09:00:00.000Z') | exit_ts | 2024-12-22T12:00:00.000Z trail_stop 186.741 | 2024-12-22T12:30:00.000Z trail_stop 187.069 | unexplained | exit_ts ref=2024-12-22T12:00:00.000Z eng=2024-12-22T12:30:00.000Z reason ref=trail_stop eng=trail_stop | bars=[{'open': '2024-12-22 11:00:00+00:00', 'o': np.flo |
| B | ('XRP/USDT', 'short', '2024-12-22T12:00:00.000Z') | entry_missing_in_engine | 2.2596 | None | chained_after_first | motor karari: skipped/risk_denied (aynı yön (short) risk sınırı aşılır) |
| B | ('TRX/USDT', 'short', '2024-12-22T12:00:00.000Z') | entry_missing_in_engine | 0.24788 | None | chained_after_first | motor karari: skipped/risk_denied (günlük zarar bütçesi aşılır) |
| B | ('ETH/USDT', 'short', '2024-12-23T05:00:00.000Z') | qty | 0.24 | 0.238 | chained_after_first | karar boyutu ref=0.24 motor=0.239: ozsermaye/risk durumu farki |
| B | ('DOGE/USDT', 'short', '2024-12-23T05:00:00.000Z') | entry_extra_in_engine | None | 0.31716 | chained_after_first | motorda fazla giris |
| A | ('DOGE/USDT', 'short', 'T1', '1h', '2024-12-23T12:00:00.000Z') | decision_only_in_reference | None | None | chained_after_first | yalniz referansta karar; genelde onceki islem sapmasi yuzunden pozisyon durumu farkli |
| C | ('BTC/USDT', 'short', '2024-12-23T12:00:00.000Z') | exit_price | 2024-12-24T13:15:00.000Z trail_stop 94604.2 | 2024-12-24T13:15:00.000Z trail_stop 94689.3 | gap_fill | cikis fiyati ref=94604.2 eng=94689.3 rel=9.00e-04 |
| B | ('ETH/USDT', 'short', '2024-12-23T18:00:00.000Z') | qty | 0.211 | 0.209 | chained_after_first | karar boyutu ref=0.211 motor=0.21: ozsermaye/risk durumu farki |
| B | ('ADA/USDT', 'short', '2024-12-24T07:00:00.000Z') | size_ratio | 14.31724680844089 | 14.230824795512675 | chained_after_first | planned_risk ref=14.3172 eng=14.2308 (rel 6.04e-03); ozsermaye tahmini ref=1023.4023359500001 motor(karar ani)=1016.6369691022326 |
| B | ('ADA/USDT', 'short', '2024-12-24T07:00:00.000Z') | qty | 546.7 | 543.4 | chained_after_first | karar boyutu ref=546.7 motor=543.4: ozsermaye/risk durumu farki |
| B | ('LINK/USDT', 'short', '2024-12-24T16:00:00.000Z') | size_ratio | 14.034802692834559 | 13.93506297826619 | chained_after_first | planned_risk ref=14.0348 eng=13.9351 (rel 7.11e-03); ozsermaye tahmini ref=1002.6287347 motor(karar ani)=995.4508065582324 |
| B | ('LINK/USDT', 'short', '2024-12-24T16:00:00.000Z') | qty | 29.54 | 29.33 | chained_after_first | karar boyutu ref=29.55 motor=29.34: ozsermaye/risk durumu farki |
| D | ('LINK/USDT', 'short', '2024-12-24T16:00:00.000Z') | funding_paid | -0.07278065200000002 | 0.0 | funding_boundary | sinir noktalari (giris/cikis anindaki 00/08/16): referans giris x1, cikis x1; motor giris x0, cikis x1 (veriden yeniden hesapla birebir uyumlu; 03 §5 `opened_ts |
| B | ('SOL/USDT', 'short', '2024-12-24T19:00:00.000Z') | size_ratio | 13.826084917686394 | 13.724918442678934 | chained_after_first | planned_risk ref=13.8261 eng=13.7249 (rel 7.32e-03); ozsermaye tahmini ref=989.41293158 motor(karar ani)=982.2566913932326 |
| B | ('SOL/USDT', 'short', '2024-12-24T19:00:00.000Z') | qty | 4.1 | 4.07 | chained_after_first | karar boyutu ref=4.1 motor=4.07: ozsermaye/risk durumu farki |
| B | ('LINK/USDT', 'short', '2024-12-24T19:00:00.000Z') | entry_missing_in_engine | 24.873 | None | chained_after_first | motor karari: skipped/risk_denied (günlük zarar bütçesi aşılır) |
| B | ('ADA/USDT', 'long', '2024-12-26T14:00:00.000Z') | size_ratio | 12.808270504011517 | 12.888018804388413 | chained_after_first | planned_risk ref=12.8083 eng=12.888 (rel 6.23e-03); ozsermaye tahmini ref=963.30558842 motor(karar ani)=969.3307739419852 |
| B | ('ADA/USDT', 'long', '2024-12-26T14:00:00.000Z') | qty | 1108.1 | 1115.1 | chained_after_first | karar boyutu ref=1108.2 motor=1115.1: ozsermaye/risk durumu farki |
| B | ('SOL/USDT', 'short', '2024-12-27T13:00:00.000Z') | size_ratio | 13.280496399762567 | 13.3753570883323 | chained_after_first | planned_risk ref=13.2805 eng=13.3754 (rel 7.14e-03); ozsermaye tahmini ref=951.50490039 motor(karar ani)=957.4555395544835 |
| B | ('SOL/USDT', 'short', '2024-12-27T13:00:00.000Z') | qty | 2.8 | 2.81 | chained_after_first | karar boyutu ref=2.8 motor=2.82: ozsermaye/risk durumu farki |
| B | ('XRP/USDT', 'short', '2024-12-27T13:00:00.000Z') | size_ratio | 13.31012041032594 | 13.400245958364497 | chained_after_first | planned_risk ref=13.3101 eng=13.4002 (rel 6.77e-03); ozsermaye tahmini ref=951.50490039 motor(karar ani)=957.4555395544835 |
| B | ('XRP/USDT', 'short', '2024-12-27T13:00:00.000Z') | qty | 280.6 | 282.5 | chained_after_first | karar boyutu ref=280.6 motor=282.5: ozsermaye/risk durumu farki |
| C | ('SOL/USDT', 'short', '2024-12-27T13:00:00.000Z') | exit_ts | 2024-12-28T13:15:00.000Z trail_stop 187.801 | 2024-12-28T13:30:00.000Z trail_stop 187.924 | unexplained | exit_ts ref=2024-12-28T13:15:00.000Z eng=2024-12-28T13:30:00.000Z reason ref=trail_stop eng=trail_stop | bars=[{'open': '2024-12-28 13:00:00+00:00', 'o': np.flo |
| B | ('DOGE/USDT', 'long', '2024-12-28T00:00:00.000Z') | size_ratio | 12.217817963218138 | 12.299419621556929 | chained_after_first | planned_risk ref=12.2178 eng=12.2994 (rel 6.68e-03); ozsermaye tahmini ref=985.9515203899999 motor(karar ani)=991.5163050558622 |
| B | ('DOGE/USDT', 'long', '2024-12-28T00:00:00.000Z') | qty | 3159.2 | 3180.3 | chained_after_first | karar boyutu ref=3159.2 motor=3180.3: ozsermaye/risk durumu farki |
| D | ('DOGE/USDT', 'long', '2024-12-28T00:00:00.000Z') | funding_paid | 0.49121682757057855 | 0.42602834277081425 | funding_boundary | sinir noktalari (giris/cikis anindaki 00/08/16): referans giris x1, cikis x2; motor giris x0, cikis x1 (veriden yeniden hesapla birebir uyumlu; 03 §5 `opened_ts |
| B | ('TRX/USDT', 'short', '2024-12-28T19:00:00.000Z') | size_ratio | 12.747774081676795 | 12.830351022280205 | chained_after_first | planned_risk ref=12.7478 eng=12.8304 (rel 6.48e-03); ozsermaye tahmini ref=996.80016272 motor(karar ani)=1002.0892695238812 |
| B | ('TRX/USDT', 'short', '2024-12-28T19:00:00.000Z') | qty | 3874.8 | 3899.9 | chained_after_first | karar boyutu ref=3874.8 motor=3899.9: ozsermaye/risk durumu farki |
| B | ('LINK/USDT', 'short', '2024-12-28T19:00:00.000Z') | size_ratio | 13.924934450106061 | 14.024231382006986 | chained_after_first | planned_risk ref=13.9249 eng=14.0242 (rel 7.13e-03); ozsermaye tahmini ref=996.80016272 motor(karar ani)=1002.0892695238812 |
| B | ('LINK/USDT', 'short', '2024-12-28T19:00:00.000Z') | qty | 23.83 | 24.01 | chained_after_first | karar boyutu ref=23.84 motor=24.01: ozsermaye/risk durumu farki |
| B | ('LINK/USDT', 'short', '2024-12-29T00:00:00.000Z') | size_ratio | 13.803904156247295 | 13.899801599247082 | chained_after_first | planned_risk ref=13.8039 eng=13.8998 (rel 6.95e-03); ozsermaye tahmini ref=988.2872635700002 motor(karar ani)=993.0077428213815 |
| B | ('LINK/USDT', 'short', '2024-12-29T00:00:00.000Z') | qty | 25.91 | 26.08 | chained_after_first | karar boyutu ref=25.91 motor=26.09: ozsermaye/risk durumu farki |
| D | ('LINK/USDT', 'short', '2024-12-29T00:00:00.000Z') | funding_paid | -0.19870065388815358 | -0.16773825161616 | funding_boundary | sinir noktalari (giris/cikis anindaki 00/08/16): referans giris x1, cikis x1; motor giris x0, cikis x1 (veriden yeniden hesapla birebir uyumlu; 03 §5 `opened_ts |
| B | ('AVAX/USDT', 'short', '2024-12-29T05:00:00.000Z') | qty | 20.8 | 21.0 | chained_after_first | karar boyutu ref=20.9 motor=21.0: ozsermaye/risk durumu farki |
| B | ('AVAX/USDT', 'short', '2024-12-30T04:00:00.000Z') | size_ratio | 13.554461550329588 | 13.64134912437016 | chained_after_first | planned_risk ref=13.5545 eng=13.6413 (rel 6.41e-03); ozsermaye tahmini ref=972.99342004 motor(karar ani)=978.7632483257971 |
| C | ('AVAX/USDT', 'short', '2024-12-30T04:00:00.000Z') | exit_price | 2024-12-30T17:30:00.000Z trail_stop 36.48 | 2024-12-30T17:30:00.000Z trail_stop 36.49 | gap_fill | cikis fiyati ref=36.48 eng=36.49 rel=2.74e-04 |
| B | ('DOGE/USDT', 'short', '2024-12-30T05:00:00.000Z') | entry_missing_in_engine | 0.31678 | None | chained_after_first | motor karari: skipped/risk_denied (günlük zarar bütçesi aşılır) |
| A | ('DOGE/USDT', 'short', 'T1', '1h', '2024-12-30T11:00:00.000Z') | decision_only_in_engine | None | None | chained_after_first | yalniz motorda karar; genelde onceki islem sapmasi yuzunden pozisyon durumu farkli |
| B | ('BNB/USDT', 'long', '2024-12-30T23:00:00.000Z') | size_ratio | 13.505176320977204 | 13.629077021169655 | chained_after_first | planned_risk ref=13.5052 eng=13.6291 (rel 9.17e-03); ozsermaye tahmini ref=966.65348844 motor(karar ani)=976.7937194581376 |
| B | ('BNB/USDT', 'long', '2024-12-30T23:00:00.000Z') | qty | 1.09 | 1.1 | chained_after_first | karar boyutu ref=1.09 motor=1.1: ozsermaye/risk durumu farki |
| B | ('XRP/USDT', 'short', '2024-12-31T23:00:00.000Z') | size_ratio | 13.460711626230102 | 13.617140581793498 | chained_after_first | planned_risk ref=13.4607 eng=13.6171 (rel 1.16e-02); ozsermaye tahmini ref=963.1436884400001 motor(karar ani)=972.9040858925177 |
| B | ('XRP/USDT', 'short', '2024-12-31T23:00:00.000Z') | qty | 344.1 | 348.2 | chained_after_first | karar boyutu ref=344.2 motor=348.2: ozsermaye/risk durumu farki |
| B | ('TRX/USDT', 'short', '2025-01-01T05:00:00.000Z') | entry_missing_in_engine | 0.25532 | None | chained_after_first | motor karari: skipped/risk_denied (günlük zarar bütçesi aşılır) |
| A | ('ADA/USDT', 'short', 'T1', '1h', '2025-01-01T08:00:00.000Z') | decision_only_in_engine | None | None | chained_after_first | yalniz motorda karar; genelde onceki islem sapmasi yuzunden pozisyon durumu farkli |
| A | ('DOGE/USDT', 'short', 'T1', '1h', '2025-01-01T08:00:00.000Z') | decision_only_in_engine | None | None | chained_after_first | yalniz motorda karar; genelde onceki islem sapmasi yuzunden pozisyon durumu farkli |
| A | ('TRX/USDT', 'short', 'T1', '1h', '2025-01-01T08:00:00.000Z') | decision_only_in_engine | None | None | chained_after_first | yalniz motorda karar; genelde onceki islem sapmasi yuzunden pozisyon durumu farkli |
| B | ('TRX/USDT', 'short', '2025-01-01T08:00:00.000Z') | entry_extra_in_engine | None | 0.25542 | chained_after_first | motorda fazla giris |
| B | ('BNB/USDT', 'long', '2025-01-03T09:00:00.000Z') | size_ratio | 6.5925289000501754 | 6.641726876916222 | chained_after_first | planned_risk ref=6.59253 eng=6.64173 (rel 7.46e-03); ozsermaye tahmini ref=940.08236772 motor(karar ani)=950.3254074967161 |
| B | ('BNB/USDT', 'long', '2025-01-03T09:00:00.000Z') | qty | 1.34 | 1.35 | chained_after_first | karar boyutu ref=1.34 motor=1.35: ozsermaye/risk durumu farki |
| B | ('BNB/USDT', 'short', '2025-01-03T19:00:00.000Z') | size_ratio | 6.253083415466114 | 6.29974821707407 | chained_after_first | planned_risk ref=6.25308 eng=6.29975 (rel 7.46e-03); ozsermaye tahmini ref=957.95003492 motor(karar ani)=968.3264154967163 |
| B | ('BNB/USDT', 'short', '2025-01-03T19:00:00.000Z') | qty | 1.34 | 1.35 | chained_after_first | karar boyutu ref=1.34 motor=1.35: ozsermaye/risk durumu farki |
| B | ('BNB/USDT', 'long', '2025-01-04T18:00:00.000Z') | size_ratio | 10.12327548035127 | 10.275505186822718 | chained_after_first | planned_risk ref=10.1233 eng=10.2755 (rel 1.50e-02); ozsermaye tahmini ref=952.66512182 motor(karar ani)=963.0020627467162 |
| B | ('BNB/USDT', 'long', '2025-01-04T18:00:00.000Z') | qty | 1.33 | 1.35 | chained_after_first | karar boyutu ref=1.33 motor=1.35: ozsermaye/risk durumu farki |
| B | ('XRP/USDT', 'long', '2025-01-05T23:00:00.000Z') | size_ratio | 13.204670390245438 | 13.349131741523337 | chained_after_first | planned_risk ref=13.2047 eng=13.3491 (rel 1.09e-02); ozsermaye tahmini ref=943.48859397 motor(karar ani)=953.687541996716 |
| B | ('XRP/USDT', 'long', '2025-01-05T23:00:00.000Z') | qty | 292.5 | 295.7 | chained_after_first | karar boyutu ref=292.5 motor=295.7: ozsermaye/risk durumu farki |
| C | ('XRP/USDT', 'long', '2025-01-05T23:00:00.000Z') | exit_price | 2025-01-06T14:15:00.000Z trail_stop 2.3778 | 2025-01-06T14:15:00.000Z trail_stop 2.3776 | price_rounding | cikis fiyati ref=2.3778 eng=2.3776 rel=8.41e-05 |
| B | ('LINK/USDT', 'long', '2025-01-07T02:00:00.000Z') | size_ratio | 12.90297736781424 | 13.044269259209937 | chained_after_first | planned_risk ref=12.903 eng=13.0443 (rel 1.10e-02); ozsermaye tahmini ref=921.9383152400001 motor(karar ani)=931.9928124302369 |
| B | ('LINK/USDT', 'long', '2025-01-07T02:00:00.000Z') | qty | 25.57 | 25.85 | chained_after_first | karar boyutu ref=25.57 motor=25.85: ozsermaye/risk durumu farki |
| B | ('SOL/USDT', 'long', '2025-01-07T04:00:00.000Z') | size_ratio | 9.158438667052499 | 9.267467698803122 | chained_after_first | planned_risk ref=9.15844 eng=9.26747 (rel 1.19e-02); ozsermaye tahmini ref=914.1650352400001 motor(karar ani)=923.8266552552369 |
| B | ('SOL/USDT', 'long', '2025-01-07T04:00:00.000Z') | qty | 4.2 | 4.25 | chained_after_first | karar boyutu ref=4.2 motor=4.25: ozsermaye/risk durumu farki |
... 1302 fark daha (json'da)
