# Capraz dogrulama: 1h_IS_f2_s5

Sonuc: **RED** (aciklanamayan: 37)

| Duzey | Olcut | Deger | Kabul |
|---|---|---|---|
| A kararlar | ortak anahtarda esit | 876/876 (100.00%); yalniz ref 17, yalniz motor 120 | evet |
| B girisler | eslesen/ref (anahtar+fiyat+boyut) | 37/614 (6.03%); yalniz anahtar 86.97%, anahtar+fiyat 86.97% | hayir |
| C cikislar | eslesen girislerde | 434/534 (81.27%; kesin 80.34%, trail +-1: 5) | hayir |
| D sum_R | ref -96.8919 / motor -69.7263 (fark 27.17, tol 1.938) | | hayir |
| D fees | ref 762.587 / motor 809.051 (fark 46.46, tol 15.25) | | hayir |
| D funding | ref 6.80994 / motor 8.70257 (fark 1.893, tol 0.3405) | | hayir |
| D n_trades | ref 614 / motor 573 (fark -41, tol 6.14) | | hayir |

Sinif sayilari: aggregate=4, chained_after_first=1232, exit_before_entry=10, funding_boundary=72, gap_fill=42, margin_accounting=7, open_at_end=1, price_rounding=19, same_bar_order=1, trail_timing=5, unexplained=37
unexplained: 37

## Ilk sapma
C ('SOL/USDT', 'short', '2024-12-21T09:00:00.000Z') exit_ts: ref=2024-12-22T12:00:00.000Z trail_stop 186.741 motor=2024-12-22T12:30:00.000Z trail_stop 187.069 sinif=unexplained | exit_ts ref=2024-12-22T12:00:00.000Z eng=2024-12-22T12:30:00.000Z reason ref=trail_stop eng=trail_stop | bars=[{'open': '2024-12-22 11:00:00+00:00', 'o': np.float64(185.5), 'h': np.float64(186.86), 'l': np.float64(185.26), 'c': np.float64(186.56)}, {'open': '2024-12-22 12:00:00+00:00', 'o': np.float64(186.55), 'h': np.float64(187.77), 'l': np.float64(185.43), 'c': np.float64(185.8)}, {'open': '2024-12-22 13:00:00+00:00', 'o': np.float64(185.8), 'h': np.float64(186.75), 'l': np.float64(184.37), 'c': np.float64(184.71)}]

## Farklar

| duzey | anahtar | alan | ref | motor | sinif | kanit |
|---|---|---|---|---|---|---|
| C | ('SOL/USDT', 'short', '2024-12-21T09:00:00.000Z') | exit_ts | 2024-12-22T12:00:00.000Z trail_stop 186.741 | 2024-12-22T12:30:00.000Z trail_stop 187.069 | unexplained | exit_ts ref=2024-12-22T12:00:00.000Z eng=2024-12-22T12:30:00.000Z reason ref=trail_stop eng=trail_stop | bars=[{'open': '2024-12-22 11:00:00+00:00', 'o': np.flo |
| B | ('XRP/USDT', 'short', '2024-12-22T12:00:00.000Z') | entry_missing_in_engine | 2.2596 | None | chained_after_first | motor karari: skipped/risk_denied (aynı yön (short) risk sınırı aşılır) |
| B | ('TRX/USDT', 'short', '2024-12-22T12:00:00.000Z') | entry_missing_in_engine | 0.24788 | None | chained_after_first | motor karari: skipped/risk_denied (günlük zarar bütçesi aşılır) |
| B | ('DOGE/USDT', 'short', '2024-12-23T05:00:00.000Z') | entry_extra_in_engine | None | 0.31716 | chained_after_first | motorda fazla giris |
| A | ('DOGE/USDT', 'short', 'T1', '1h', '2024-12-23T12:00:00.000Z') | decision_only_in_reference | None | None | chained_after_first | yalniz referansta karar; genelde onceki islem sapmasi yuzunden pozisyon durumu farkli |
| C | ('BTC/USDT', 'short', '2024-12-23T12:00:00.000Z') | exit_price | 2024-12-24T13:15:00.000Z trail_stop 94604.2 | 2024-12-24T13:15:00.000Z trail_stop 94689.3 | gap_fill | cikis fiyati ref=94604.2 eng=94689.3 rel=9.00e-04 |
| B | ('ETH/USDT', 'short', '2024-12-23T18:00:00.000Z') | qty | 0.209 | 0.208 | chained_after_first | karar boyutu ref=0.21 motor=0.209: ozsermaye/risk durumu farki |
| B | ('ADA/USDT', 'short', '2024-12-24T07:00:00.000Z') | qty | 541.4 | 539.8 | chained_after_first | karar boyutu ref=541.5 motor=539.8: ozsermaye/risk durumu farki |
| B | ('LINK/USDT', 'short', '2024-12-24T16:00:00.000Z') | size_ratio | 13.887567876090777 | 13.81632522282766 | chained_after_first | planned_risk ref=13.8876 eng=13.8163 (rel 5.13e-03); ozsermaye tahmini ref=992.1602501 motor(karar ani)=986.9908520396725 |
| B | ('LINK/USDT', 'short', '2024-12-24T16:00:00.000Z') | qty | 29.24 | 29.08 | chained_after_first | karar boyutu ref=29.24 motor=29.09: ozsermaye/risk durumu farki |
| D | ('LINK/USDT', 'short', '2024-12-24T16:00:00.000Z') | funding_paid | -0.072041512 | 0.0 | funding_boundary | sinir noktalari (giris/cikis anindaki 00/08/16): referans giris x1, cikis x1; motor giris x0, cikis x1 (veriden yeniden hesapla birebir uyumlu; 03 §5 `opened_ts |
| B | ('SOL/USDT', 'short', '2024-12-24T19:00:00.000Z') | qty | 4.05 | 4.03 | chained_after_first | karar boyutu ref=4.05 motor=4.03: ozsermaye/risk durumu farki |
| B | ('LINK/USDT', 'short', '2024-12-24T19:00:00.000Z') | entry_missing_in_engine | 24.873 | None | chained_after_first | motor karari: skipped/risk_denied (günlük zarar bütçesi aşılır) |
| B | ('ADA/USDT', 'long', '2024-12-26T14:00:00.000Z') | size_ratio | 12.615256501650036 | 12.73892415585769 | chained_after_first | planned_risk ref=12.6153 eng=12.7389 (rel 9.80e-03); ozsermaye tahmini ref=948.8095828 motor(karar ani)=958.0701969321722 |
| B | ('ADA/USDT', 'long', '2024-12-26T14:00:00.000Z') | qty | 1091.5 | 1102.2 | chained_after_first | karar boyutu ref=1091.5 motor=1102.2: ozsermaye/risk durumu farki |
| B | ('SOL/USDT', 'short', '2024-12-27T13:00:00.000Z') | size_ratio | 13.090775022623102 | 13.185635711192834 | chained_after_first | planned_risk ref=13.0908 eng=13.1856 (rel 7.25e-03); ozsermaye tahmini ref=935.29890922 motor(karar ani)=944.4270779078728 |
| B | ('SOL/USDT', 'short', '2024-12-27T13:00:00.000Z') | qty | 2.75 | 2.78 | chained_after_first | karar boyutu ref=2.76 motor=2.78: ozsermaye/risk durumu farki |
| B | ('XRP/USDT', 'short', '2024-12-27T13:00:00.000Z') | size_ratio | 13.068204465590865 | 13.21999486228738 | chained_after_first | planned_risk ref=13.0682 eng=13.22 (rel 1.16e-02); ozsermaye tahmini ref=935.29890922 motor(karar ani)=944.4270779078728 |
| B | ('XRP/USDT', 'short', '2024-12-27T13:00:00.000Z') | qty | 275.5 | 278.7 | chained_after_first | karar boyutu ref=275.5 motor=278.7: ozsermaye/risk durumu farki |
| C | ('SOL/USDT', 'short', '2024-12-27T13:00:00.000Z') | exit_ts | 2024-12-28T13:15:00.000Z trail_stop 187.801 | 2024-12-28T13:30:00.000Z trail_stop 187.924 | unexplained | exit_ts ref=2024-12-28T13:15:00.000Z eng=2024-12-28T13:30:00.000Z reason ref=trail_stop eng=trail_stop | bars=[{'open': '2024-12-28 13:00:00+00:00', 'o': np.flo |
| B | ('DOGE/USDT', 'long', '2024-12-28T00:00:00.000Z') | size_ratio | 11.981907955698416 | 12.118813107603305 | chained_after_first | planned_risk ref=11.9819 eng=12.1188 (rel 1.14e-02); ozsermaye tahmini ref=969.12525922 motor(karar ani)=976.9355149469236 |
| B | ('DOGE/USDT', 'long', '2024-12-28T00:00:00.000Z') | qty | 3098.1 | 3133.6 | chained_after_first | karar boyutu ref=3098.2 motor=3133.6: ozsermaye/risk durumu farki |
| D | ('DOGE/USDT', 'long', '2024-12-28T00:00:00.000Z') | funding_paid | 0.48171652744252 | 0.4197724789820531 | funding_boundary | sinir noktalari (giris/cikis anindaki 00/08/16): referans giris x1, cikis x2; motor giris x0, cikis x1 (veriden yeniden hesapla birebir uyumlu; 03 §5 `opened_ts |
| B | ('TRX/USDT', 'short', '2024-12-28T19:00:00.000Z') | size_ratio | 12.476026858814583 | 12.613874421017083 | chained_after_first | planned_risk ref=12.476 eng=12.6139 (rel 1.10e-02); ozsermaye tahmini ref=977.49195836 motor(karar ani)=985.1950892781083 |
| B | ('TRX/USDT', 'short', '2024-12-28T19:00:00.000Z') | qty | 3792.2 | 3834.1 | chained_after_first | karar boyutu ref=3792.2 motor=3834.1: ozsermaye/risk durumu farki |
| B | ('LINK/USDT', 'short', '2024-12-28T19:00:00.000Z') | size_ratio | 13.59783867443243 | 13.790591542240104 | chained_after_first | planned_risk ref=13.5978 eng=13.7906 (rel 1.42e-02); ozsermaye tahmini ref=977.49195836 motor(karar ani)=985.1950892781083 |
| B | ('LINK/USDT', 'short', '2024-12-28T19:00:00.000Z') | qty | 23.28 | 23.61 | chained_after_first | karar boyutu ref=23.28 motor=23.61: ozsermaye/risk durumu farki |
| B | ('LINK/USDT', 'short', '2024-12-29T00:00:00.000Z') | size_ratio | 13.468263105748035 | 13.638747448858771 | chained_after_first | planned_risk ref=13.4683 eng=13.6387 (rel 1.27e-02); ozsermaye tahmini ref=968.1788861600003 motor(karar ani)=974.2611751356086 |
| B | ('LINK/USDT', 'short', '2024-12-29T00:00:00.000Z') | qty | 25.28 | 25.6 | chained_after_first | karar boyutu ref=25.28 motor=25.6: ozsermaye/risk durumu farki |
| D | ('LINK/USDT', 'short', '2024-12-29T00:00:00.000Z') | funding_paid | -0.19386926014251343 | -0.16465104453120002 | funding_boundary | sinir noktalari (giris/cikis anindaki 00/08/16): referans giris x1, cikis x1; motor giris x0, cikis x1 (veriden yeniden hesapla birebir uyumlu; 03 §5 `opened_ts |
| B | ('AVAX/USDT', 'short', '2024-12-29T05:00:00.000Z') | size_ratio | 13.386770325960267 | 13.58460437018628 | chained_after_first | planned_risk ref=13.3868 eng=13.5846 (rel 1.48e-02); ozsermaye tahmini ref=964.8068578600002 motor(karar ani)=971.3937157379379 |
| B | ('AVAX/USDT', 'short', '2024-12-29T05:00:00.000Z') | qty | 20.3 | 20.6 | chained_after_first | karar boyutu ref=20.3 motor=20.6: ozsermaye/risk durumu farki |
| B | ('AVAX/USDT', 'short', '2024-12-30T04:00:00.000Z') | size_ratio | 13.20691125416729 | 13.293798828207867 | chained_after_first | planned_risk ref=13.2069 eng=13.2938 (rel 6.58e-03); ozsermaye tahmini ref=946.57452014 motor(karar ani)=955.5199478349423 |
| C | ('AVAX/USDT', 'short', '2024-12-30T04:00:00.000Z') | exit_price | 2024-12-30T17:30:00.000Z trail_stop 36.48 | 2024-12-30T17:30:00.000Z trail_stop 36.49 | gap_fill | cikis fiyati ref=36.48 eng=36.49 rel=2.74e-04 |
| B | ('DOGE/USDT', 'short', '2024-12-30T05:00:00.000Z') | entry_missing_in_engine | 0.31678 | None | chained_after_first | motor karari: skipped/risk_denied (günlük zarar bütçesi aşılır) |
| A | ('DOGE/USDT', 'short', 'T1', '1h', '2024-12-30T11:00:00.000Z') | decision_only_in_engine | None | None | chained_after_first | yalniz motorda karar; genelde onceki islem sapmasi yuzunden pozisyon durumu farkli |
| B | ('BNB/USDT', 'long', '2024-12-30T23:00:00.000Z') | entry_missing_in_engine | 704.05 | None | chained_after_first | motor karari: skipped/risk_denied (günlük zarar bütçesi aşılır) |
| A | ('BNB/USDT', 'long', 'T1', '1h', '2024-12-31T10:00:00.000Z') | decision_only_in_engine | None | None | chained_after_first | yalniz motorda karar; genelde onceki islem sapmasi yuzunden pozisyon durumu farkli |
| B | ('BNB/USDT', 'long', '2024-12-31T10:00:00.000Z') | entry_extra_in_engine | None | 706.13 | chained_after_first | motorda fazla giris |
| B | ('XRP/USDT', 'short', '2024-12-31T23:00:00.000Z') | size_ratio | 13.018799826763512 | 13.229978916774096 | chained_after_first | planned_risk ref=13.0188 eng=13.23 (rel 1.62e-02); ozsermaye tahmini ref=934.81080018 motor(karar ani)=945.0200422189711 |
| B | ('XRP/USDT', 'short', '2024-12-31T23:00:00.000Z') | qty | 332.9 | 338.3 | chained_after_first | karar boyutu ref=332.9 motor=338.3: ozsermaye/risk durumu farki |
| B | ('TRX/USDT', 'short', '2025-01-01T08:00:00.000Z') | entry_extra_in_engine | None | 0.25542 | chained_after_first | motorda fazla giris |
| A | ('BNB/USDT', 'long', 'R1', '1h', '2025-01-03T09:00:00.000Z') | decision_only_in_reference | None | None | chained_after_first | yalniz referansta karar; genelde onceki islem sapmasi yuzunden pozisyon durumu farkli |
| B | ('BNB/USDT', 'long', '2025-01-03T09:00:00.000Z') | entry_missing_in_engine | 698.9 | None | chained_after_first | referans girisi motorda yok (motorda karar kaydi da yok: pozisyon durumu farki) |
| A | ('BNB/USDT', 'short', 'R1', '1h', '2025-01-03T19:00:00.000Z') | decision_only_in_reference | None | None | chained_after_first | yalniz referansta karar; genelde onceki islem sapmasi yuzunden pozisyon durumu farkli |
| B | ('BNB/USDT', 'short', '2025-01-03T19:00:00.000Z') | entry_missing_in_engine | 712.35 | None | chained_after_first | referans girisi motorda yok (motorda karar kaydi da yok: pozisyon durumu farki) |
| B | ('BNB/USDT', 'long', '2025-01-04T18:00:00.000Z') | size_ratio | 9.74270121417265 | 9.818816067408374 | chained_after_first | planned_risk ref=9.7427 eng=9.81882 (rel 7.81e-03); ozsermaye tahmini ref=918.78431463 motor(karar ani)=926.4325124615839 |
| B | ('BNB/USDT', 'long', '2025-01-04T18:00:00.000Z') | qty | 1.28 | 1.29 | chained_after_first | karar boyutu ref=1.28 motor=1.29: ozsermaye/risk durumu farki |
| B | ('XRP/USDT', 'long', '2025-01-05T23:00:00.000Z') | size_ratio | 12.712598912455096 | 12.816430508686084 | chained_after_first | planned_risk ref=12.7126 eng=12.8164 (rel 8.17e-03); ozsermaye tahmini ref=908.13607783 motor(karar ani)=915.7010863115838 |
| B | ('XRP/USDT', 'long', '2025-01-05T23:00:00.000Z') | qty | 281.6 | 283.9 | chained_after_first | karar boyutu ref=281.6 motor=283.9: ozsermaye/risk durumu farki |
| C | ('XRP/USDT', 'long', '2025-01-05T23:00:00.000Z') | exit_price | 2025-01-06T14:15:00.000Z trail_stop 2.3778 | 2025-01-06T14:15:00.000Z trail_stop 2.3776 | price_rounding | cikis fiyati ref=2.3778 eng=2.3776 rel=8.41e-05 |
| B | ('LINK/USDT', 'long', '2025-01-07T02:00:00.000Z') | size_ratio | 12.34285594120987 | 12.448824859756641 | chained_after_first | planned_risk ref=12.3429 eng=12.4488 (rel 8.59e-03); ozsermaye tahmini ref=881.9731457 motor(karar ani)=889.40912832004 |
| B | ('LINK/USDT', 'long', '2025-01-07T02:00:00.000Z') | qty | 24.45 | 24.66 | chained_after_first | karar boyutu ref=24.46 motor=24.67: ozsermaye/risk durumu farki |
| B | ('SOL/USDT', 'long', '2025-01-07T04:00:00.000Z') | size_ratio | 8.744128346400121 | 8.83135157180062 | chained_after_first | planned_risk ref=8.74413 eng=8.83135 (rel 9.98e-03); ozsermaye tahmini ref=874.5403457000001 motor(karar ani)=881.0317194300401 |
| B | ('SOL/USDT', 'long', '2025-01-07T04:00:00.000Z') | qty | 4.01 | 4.05 | chained_after_first | karar boyutu ref=4.01 motor=4.05: ozsermaye/risk durumu farki |
| B | ('LINK/USDT', 'long', '2025-01-07T07:00:00.000Z') | size_ratio | 12.06946416318401 | 12.188921567414889 | chained_after_first | planned_risk ref=12.0695 eng=12.1889 (rel 9.90e-03); ozsermaye tahmini ref=864.8993193299999 motor(karar ani)=870.86295972004 |
| B | ('LINK/USDT', 'long', '2025-01-07T07:00:00.000Z') | qty | 28.29 | 28.57 | chained_after_first | karar boyutu ref=28.29 motor=28.57: ozsermaye/risk durumu farki |
| B | ('ETH/USDT', 'short', '2025-01-10T19:00:00.000Z') | size_ratio | 11.835035489673833 | 11.949383658656188 | chained_after_first | planned_risk ref=11.835 eng=11.9494 (rel 9.66e-03); ozsermaye tahmini ref=846.68385499 motor(karar ani)=853.7867013944627 |
| B | ('ETH/USDT', 'short', '2025-01-10T19:00:00.000Z') | qty | 0.206 | 0.209 | chained_after_first | karar boyutu ref=0.207 motor=0.209: ozsermaye/risk durumu farki |
| B | ('SOL/USDT', 'short', '2025-01-10T19:00:00.000Z') | size_ratio | 11.810947440593996 | 11.949087176741296 | chained_after_first | planned_risk ref=11.8109 eng=11.9491 (rel 1.17e-02); ozsermaye tahmini ref=846.68385499 motor(karar ani)=853.7867013944627 |
... 1370 fark daha (json'da)
