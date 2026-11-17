# Capraz dogrulama: 1h_IS_f2_s5

Sonuc: **RED** (aciklanamayan: 0)

| Duzey | Olcut | Deger | Kabul |
|---|---|---|---|
| A kararlar | ortak anahtarda esit | 877/877 (100.00%); yalniz ref 16, yalniz motor 118 | evet |
| B girisler | eslesen/ref (anahtar+fiyat+boyut) | 48/614 (7.82%); yalniz anahtar 87.62%, anahtar+fiyat 87.62% | hayir |
| C cikislar | eslesen girislerde | 517/538 (96.10%; kesin 96.10%, trail +-1: 0) | hayir |
| D sum_R | ref -96.8919 / motor -72.3589 (fark 24.53, tol 1.938) | | hayir |
| D fees | ref 762.587 / motor 775.927 (fark 13.34, tol 15.25) | | evet |
| D funding | ref 6.80994 / motor 8.43922 (fark 1.629, tol 0.3405) | | hayir |
| D n_trades | ref 614 / motor 575 (fark -39, tol 6.14) | | hayir |

Sinif sayilari: aggregate=3, chained_after_first=1211, exit_before_entry=10, funding_boundary=78, gap_fill=18, margin_accounting=7, open_at_end=1, price_rounding=2, qty_rounding=2
unexplained: 0

## Ilk sapma
B ('XRP/USDT', 'short', '2024-12-22T12:00:00.000Z') qty: ref=289.3 motor=289.5 sinif=exit_before_entry | karar boyutu ref=289.3 motor=289.5: ozsermaye/risk durumu farki; ayni adimda cikan referans islem(ler) [('SOL/USDT', 'short', '2024-12-21T09:00:00.000Z')]: referans cikisi gerceklestirir (realized), motor son mark'ta tutar (cikis-giristen-once modeli)

## Farklar

| duzey | anahtar | alan | ref | motor | sinif | kanit |
|---|---|---|---|---|---|---|
| B | ('XRP/USDT', 'short', '2024-12-22T12:00:00.000Z') | qty | 289.3 | 289.5 | exit_before_entry | karar boyutu ref=289.3 motor=289.5: ozsermaye/risk durumu farki; ayni adimda cikan referans islem(ler) [('SOL/USDT', 'short', '2024-12-21T09:00:00.000Z')]: refe |
| B | ('TRX/USDT', 'short', '2024-12-22T12:00:00.000Z') | entry_missing_in_engine | 0.24788 | None | chained_after_first | motor karari: skipped/risk_denied (günlük zarar bütçesi aşılır) |
| B | ('ETH/USDT', 'short', '2024-12-23T05:00:00.000Z') | size_ratio | 14.454788770229273 | 14.636991990022079 | chained_after_first | planned_risk ref=14.4548 eng=14.637 (rel 1.26e-02); ozsermaye tahmini ref=1038.12577573 motor(karar ani)=1049.4333183989888 |
| B | ('ETH/USDT', 'short', '2024-12-23T05:00:00.000Z') | qty | 0.238 | 0.241 | chained_after_first | karar boyutu ref=0.238 motor=0.241: ozsermaye/risk durumu farki |
| B | ('BTC/USDT', 'short', '2024-12-23T12:00:00.000Z') | entry_missing_in_engine | 95899.4 | None | chained_after_first | motor karari: skipped/risk_denied (günlük zarar bütçesi aşılır) |
| B | ('ETH/USDT', 'short', '2024-12-23T18:00:00.000Z') | size_ratio | 14.749142123700365 | 14.608674103474646 | chained_after_first | planned_risk ref=14.7491 eng=14.6087 (rel 9.52e-03); ozsermaye tahmini ref=1059.05531937 motor(karar ani)=1047.228824033394 |
| B | ('ETH/USDT', 'short', '2024-12-23T18:00:00.000Z') | qty | 0.209 | 0.208 | chained_after_first | karar boyutu ref=0.21 motor=0.208: ozsermaye/risk durumu farki |
| B | ('ADA/USDT', 'short', '2024-12-24T07:00:00.000Z') | qty | 541.4 | 539.6 | chained_after_first | karar boyutu ref=541.5 motor=539.6: ozsermaye/risk durumu farki |
| B | ('LINK/USDT', 'short', '2024-12-24T16:00:00.000Z') | qty | 29.24 | 29.32 | chained_after_first | karar boyutu ref=29.24 motor=29.32: ozsermaye/risk durumu farki |
| D | ('LINK/USDT', 'short', '2024-12-24T16:00:00.000Z') | funding_paid | -0.072041512 | 0.0 | funding_boundary | sinir noktalari (giris/cikis anindaki 00/08/16): referans giris x1, cikis x1; motor giris x0, cikis x1 (veriden yeniden hesapla birebir uyumlu; 03 §5 `opened_ts |
| B | ('LINK/USDT', 'short', '2024-12-24T19:00:00.000Z') | entry_missing_in_engine | 24.873 | None | chained_after_first | motor karari: skipped/risk_denied (günlük zarar bütçesi aşılır) |
| B | ('ADA/USDT', 'long', '2024-12-26T14:00:00.000Z') | size_ratio | 12.615256501650036 | 12.841787905619196 | chained_after_first | planned_risk ref=12.6153 eng=12.8418 (rel 1.80e-02); ozsermaye tahmini ref=948.8095828 motor(karar ani)=965.8199677080203 |
| B | ('ADA/USDT', 'long', '2024-12-26T14:00:00.000Z') | qty | 1091.5 | 1111.1 | chained_after_first | karar boyutu ref=1091.5 motor=1111.1: ozsermaye/risk durumu farki |
| B | ('SOL/USDT', 'short', '2024-12-27T13:00:00.000Z') | size_ratio | 13.090775022623102 | 13.327926744047433 | chained_after_first | planned_risk ref=13.0908 eng=13.3279 (rel 1.81e-02); ozsermaye tahmini ref=935.29890922 motor(karar ani)=952.0666837777907 |
| B | ('SOL/USDT', 'short', '2024-12-27T13:00:00.000Z') | qty | 2.75 | 2.81 | chained_after_first | karar boyutu ref=2.76 motor=2.81: ozsermaye/risk durumu farki |
| B | ('XRP/USDT', 'short', '2024-12-27T13:00:00.000Z') | size_ratio | 13.068204465590865 | 13.324350760016236 | chained_after_first | planned_risk ref=13.0682 eng=13.3244 (rel 1.96e-02); ozsermaye tahmini ref=935.29890922 motor(karar ani)=952.0666837777907 |
| B | ('XRP/USDT', 'short', '2024-12-27T13:00:00.000Z') | qty | 275.5 | 280.9 | chained_after_first | karar boyutu ref=275.5 motor=280.9: ozsermaye/risk durumu farki |
| C | ('XRP/USDT', 'short', '2024-12-27T13:00:00.000Z') | exit_price | 2024-12-28T14:00:00.000Z trail_stop 2.1735 | 2024-12-28T14:00:00.000Z trail_stop 2.1717 | gap_fill | cikis fiyati ref=2.1735 eng=2.1717 rel=8.28e-04 |
| B | ('DOGE/USDT', 'long', '2024-12-28T00:00:00.000Z') | size_ratio | 11.981907955698416 | 12.217431225500892 | chained_after_first | planned_risk ref=11.9819 eng=12.2174 (rel 1.97e-02); ozsermaye tahmini ref=969.12525922 motor(karar ani)=984.8818310091694 |
| B | ('DOGE/USDT', 'long', '2024-12-28T00:00:00.000Z') | qty | 3098.1 | 3159.1 | chained_after_first | karar boyutu ref=3098.2 motor=3159.1: ozsermaye/risk durumu farki |
| D | ('DOGE/USDT', 'long', '2024-12-28T00:00:00.000Z') | funding_paid | 0.48171652744252 | 0.42318842173608745 | funding_boundary | sinir noktalari (giris/cikis anindaki 00/08/16): referans giris x1, cikis x2; motor giris x0, cikis x1 (veriden yeniden hesapla birebir uyumlu; 03 §5 `opened_ts |
| B | ('TRX/USDT', 'short', '2024-12-28T19:00:00.000Z') | size_ratio | 12.476026858814583 | 12.727047598577133 | chained_after_first | planned_risk ref=12.476 eng=12.727 (rel 2.01e-02); ozsermaye tahmini ref=977.49195836 motor(karar ani)=994.0336898212282 |
| B | ('TRX/USDT', 'short', '2024-12-28T19:00:00.000Z') | qty | 3792.2 | 3868.4 | chained_after_first | karar boyutu ref=3792.2 motor=3868.5: ozsermaye/risk durumu farki |
| B | ('LINK/USDT', 'short', '2024-12-28T19:00:00.000Z') | size_ratio | 13.59783867443243 | 13.913252458117718 | chained_after_first | planned_risk ref=13.5978 eng=13.9133 (rel 2.32e-02); ozsermaye tahmini ref=977.49195836 motor(karar ani)=994.0336898212282 |
| B | ('LINK/USDT', 'short', '2024-12-28T19:00:00.000Z') | qty | 23.28 | 23.82 | chained_after_first | karar boyutu ref=23.28 motor=23.82: ozsermaye/risk durumu farki |
| B | ('LINK/USDT', 'short', '2024-12-29T00:00:00.000Z') | size_ratio | 13.468263105748035 | 13.761283070469608 | chained_after_first | planned_risk ref=13.4683 eng=13.7613 (rel 2.18e-02); ozsermaye tahmini ref=968.1788861600003 motor(karar ani)=982.9948694512284 |
| B | ('LINK/USDT', 'short', '2024-12-29T00:00:00.000Z') | qty | 25.28 | 25.83 | chained_after_first | karar boyutu ref=25.28 motor=25.83: ozsermaye/risk durumu farki |
| D | ('LINK/USDT', 'short', '2024-12-29T00:00:00.000Z') | funding_paid | -0.19386926014251343 | -0.16613033125940999 | funding_boundary | sinir noktalari (giris/cikis anindaki 00/08/16): referans giris x1, cikis x1; motor giris x0, cikis x1 (veriden yeniden hesapla birebir uyumlu; 03 §5 `opened_ts |
| B | ('AVAX/USDT', 'short', '2024-12-29T05:00:00.000Z') | size_ratio | 13.386770325960267 | 13.716493733003624 | chained_after_first | planned_risk ref=13.3868 eng=13.7165 (rel 2.46e-02); ozsermaye tahmini ref=964.8068578600002 motor(karar ani)=980.1027542953417 |
| B | ('AVAX/USDT', 'short', '2024-12-29T05:00:00.000Z') | qty | 20.3 | 20.8 | chained_after_first | karar boyutu ref=20.3 motor=20.8: ozsermaye/risk durumu farki |
| B | ('AVAX/USDT', 'short', '2024-12-30T04:00:00.000Z') | size_ratio | 13.20691125416729 | 13.467573976289014 | chained_after_first | planned_risk ref=13.2069 eng=13.4676 (rel 1.97e-02); ozsermaye tahmini ref=946.57452014 motor(karar ani)=964.122667815869 |
| B | ('AVAX/USDT', 'short', '2024-12-30T04:00:00.000Z') | qty | 15.2 | 15.4 | chained_after_first | karar boyutu ref=15.2 motor=15.5: ozsermaye/risk durumu farki |
| B | ('DOGE/USDT', 'short', '2024-12-30T05:00:00.000Z') | entry_missing_in_engine | 0.31678 | None | chained_after_first | motor karari: skipped/risk_denied (günlük zarar bütçesi aşılır) |
| A | ('DOGE/USDT', 'short', 'T1', '1h', '2024-12-30T11:00:00.000Z') | decision_only_in_engine | None | None | chained_after_first | yalniz motorda karar; genelde onceki islem sapmasi yuzunden pozisyon durumu farkli |
| B | ('BNB/USDT', 'long', '2024-12-30T23:00:00.000Z') | entry_missing_in_engine | 704.05 | None | chained_after_first | motor karari: skipped/risk_denied (günlük zarar bütçesi aşılır) |
| A | ('BNB/USDT', 'long', 'T1', '1h', '2024-12-31T10:00:00.000Z') | decision_only_in_engine | None | None | chained_after_first | yalniz motorda karar; genelde onceki islem sapmasi yuzunden pozisyon durumu farkli |
| B | ('BNB/USDT', 'long', '2024-12-31T10:00:00.000Z') | entry_extra_in_engine | None | 706.13 | chained_after_first | motorda fazla giris |
| B | ('BTC/USDT', 'short', '2024-12-31T23:00:00.000Z') | size_ratio | 11.99807320047332 | 13.331192444970355 | chained_after_first | planned_risk ref=11.9981 eng=13.3312 (rel 1.11e-01); ozsermaye tahmini ref=934.81080018 motor(karar ani)=953.6738352476938 |
| B | ('XRP/USDT', 'short', '2024-12-31T23:00:00.000Z') | size_ratio | 13.018799826763512 | 13.351211357335727 | chained_after_first | planned_risk ref=13.0188 eng=13.3512 (rel 2.55e-02); ozsermaye tahmini ref=934.81080018 motor(karar ani)=953.6738352476938 |
| B | ('XRP/USDT', 'short', '2024-12-31T23:00:00.000Z') | qty | 332.9 | 341.4 | chained_after_first | karar boyutu ref=332.9 motor=341.4: ozsermaye/risk durumu farki |
| B | ('TRX/USDT', 'short', '2025-01-01T08:00:00.000Z') | entry_extra_in_engine | None | 0.25542 | chained_after_first | motorda fazla giris |
| A | ('BNB/USDT', 'long', 'R1', '1h', '2025-01-03T09:00:00.000Z') | decision_only_in_reference | None | None | chained_after_first | yalniz referansta karar; genelde onceki islem sapmasi yuzunden pozisyon durumu farkli |
| B | ('BNB/USDT', 'long', '2025-01-03T09:00:00.000Z') | entry_missing_in_engine | 698.9 | None | chained_after_first | referans girisi motorda yok (motorda karar kaydi da yok: pozisyon durumu farki) |
| A | ('BNB/USDT', 'short', 'R1', '1h', '2025-01-03T19:00:00.000Z') | decision_only_in_reference | None | None | chained_after_first | yalniz referansta karar; genelde onceki islem sapmasi yuzunden pozisyon durumu farkli |
| B | ('BNB/USDT', 'short', '2025-01-03T19:00:00.000Z') | entry_missing_in_engine | 712.35 | None | chained_after_first | referans girisi motorda yok (motorda karar kaydi da yok: pozisyon durumu farki) |
| B | ('BNB/USDT', 'long', '2025-01-04T18:00:00.000Z') | size_ratio | 9.74270121417265 | 9.97104577387982 | chained_after_first | planned_risk ref=9.7427 eng=9.97105 (rel 2.34e-02); ozsermaye tahmini ref=918.78431463 motor(karar ani)=935.2249049610725 |
| B | ('BNB/USDT', 'long', '2025-01-04T18:00:00.000Z') | qty | 1.28 | 1.31 | chained_after_first | karar boyutu ref=1.28 motor=1.31: ozsermaye/risk durumu farki |
| B | ('XRP/USDT', 'long', '2025-01-05T23:00:00.000Z') | size_ratio | 12.712598912455096 | 12.938319773826812 | chained_after_first | planned_risk ref=12.7126 eng=12.9383 (rel 1.78e-02); ozsermaye tahmini ref=908.13607783 motor(karar ani)=924.3271001110725 |
| B | ('XRP/USDT', 'long', '2025-01-05T23:00:00.000Z') | qty | 281.6 | 286.6 | chained_after_first | karar boyutu ref=281.6 motor=286.6: ozsermaye/risk durumu farki |
| B | ('LINK/USDT', 'long', '2025-01-07T02:00:00.000Z') | size_ratio | 12.34285594120987 | 12.569932195238668 | chained_after_first | planned_risk ref=12.3429 eng=12.5699 (rel 1.84e-02); ozsermaye tahmini ref=881.9731457 motor(karar ani)=898.0069266047553 |
| B | ('LINK/USDT', 'long', '2025-01-07T02:00:00.000Z') | qty | 24.45 | 24.91 | chained_after_first | karar boyutu ref=24.46 motor=24.91: ozsermaye/risk durumu farki |
| B | ('SOL/USDT', 'long', '2025-01-07T04:00:00.000Z') | size_ratio | 8.744128346400121 | 8.91857479720112 | chained_after_first | planned_risk ref=8.74413 eng=8.91857 (rel 2.00e-02); ozsermaye tahmini ref=874.5403457000001 motor(karar ani)=889.5445885897553 |
| B | ('SOL/USDT', 'long', '2025-01-07T04:00:00.000Z') | qty | 4.01 | 4.09 | chained_after_first | karar boyutu ref=4.01 motor=4.09: ozsermaye/risk durumu farki |
| B | ('LINK/USDT', 'long', '2025-01-07T07:00:00.000Z') | size_ratio | 12.06946416318401 | 12.308378971645768 | chained_after_first | planned_risk ref=12.0695 eng=12.3084 (rel 1.98e-02); ozsermaye tahmini ref=864.8993193299999 motor(karar ani)=879.2741849297552 |
| B | ('LINK/USDT', 'long', '2025-01-07T07:00:00.000Z') | qty | 28.29 | 28.85 | chained_after_first | karar boyutu ref=28.29 motor=28.85: ozsermaye/risk durumu farki |
| B | ('ETH/USDT', 'short', '2025-01-10T19:00:00.000Z') | size_ratio | 11.835035489673833 | 12.063731827638545 | chained_after_first | planned_risk ref=11.835 eng=12.0637 (rel 1.93e-02); ozsermaye tahmini ref=846.68385499 motor(karar ani)=862.0302535613091 |
| B | ('ETH/USDT', 'short', '2025-01-10T19:00:00.000Z') | qty | 0.206 | 0.211 | chained_after_first | karar boyutu ref=0.207 motor=0.211: ozsermaye/risk durumu farki |
| B | ('SOL/USDT', 'short', '2025-01-10T19:00:00.000Z') | size_ratio | 11.810947440593996 | 12.052691978851769 | chained_after_first | planned_risk ref=11.8109 eng=12.0527 (rel 2.05e-02); ozsermaye tahmini ref=846.68385499 motor(karar ani)=862.0302535613091 |
| B | ('SOL/USDT', 'short', '2025-01-10T19:00:00.000Z') | qty | 3.42 | 3.49 | chained_after_first | karar boyutu ref=3.42 motor=3.49: ozsermaye/risk durumu farki |
| B | ('TRX/USDT', 'short', '2025-01-11T02:00:00.000Z') | size_ratio | 7.466460537674651 | 7.6195722608747385 | chained_after_first | planned_risk ref=7.46646 eng=7.61957 (rel 2.05e-02); ozsermaye tahmini ref=867.38005499 motor(karar ani)=881.1997756778053 |
... 1272 fark daha (json'da)
