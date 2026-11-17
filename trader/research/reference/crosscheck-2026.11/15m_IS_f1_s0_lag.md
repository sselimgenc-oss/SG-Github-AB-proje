# Capraz dogrulama: 15m_IS_f1_s0

Sonuc: **RED** (aciklanamayan: 24)

| Duzey | Olcut | Deger | Kabul |
|---|---|---|---|
| A kararlar | ortak anahtarda esit | 2801/2801 (100.00%); yalniz ref 48, yalniz motor 1261 | evet |
| B girisler | eslesen/ref (anahtar+fiyat+boyut) | 36/2195 (1.64%); yalniz anahtar 85.06%, anahtar+fiyat 85.06% | hayir |
| C cikislar | eslesen girislerde | 1829/1867 (97.96%; kesin 94.75%, trail +-1: 60) | evet |
| D sum_R | ref -160.564 / motor -126.932 (fark 33.63, tol 3.211) | | hayir |
| D fees | ref 892.965 / motor 1026.39 (fark 133.4, tol 17.86) | | hayir |
| D funding | ref 8.53273 / motor 9.20959 (fark 0.6769, tol 0.4266) | | hayir |
| D n_trades | ref 2195 / motor 2135 (fark -60, tol 21.95) | | hayir |

Sinif sayilari: aggregate=4, chained_after_first=5300, exit_before_entry=88, funding_boundary=108, gap_fill=4, margin_accounting=161, price_rounding=7, same_bar_order=3, trail_timing=60, unexplained=24
unexplained: 24

## Ilk sapma
C ('BNB/USDT', 'short', '2024-12-21T10:45:00.000Z') exit_ts: ref=2024-12-21T13:45:00.000Z trail_stop 666.83 motor=2024-12-21T14:00:00.000Z trail_stop 666.83 sinif=trail_timing | iz stop bir bar sonra: ref 2024-12-21T13:45:00.000Z eng 2024-12-21T14:00:00.000Z

## Farklar

| duzey | anahtar | alan | ref | motor | sinif | kanit |
|---|---|---|---|---|---|---|
| C | ('BNB/USDT', 'short', '2024-12-21T10:45:00.000Z') | exit_ts | 2024-12-21T13:45:00.000Z trail_stop 666.83 | 2024-12-21T14:00:00.000Z trail_stop 666.83 | trail_timing | iz stop bir bar sonra: ref 2024-12-21T13:45:00.000Z eng 2024-12-21T14:00:00.000Z |
| C | ('BTC/USDT', 'short', '2024-12-21T20:45:00.000Z') | exit_ts | 2024-12-22T07:00:00.000Z trail_stop 96797.5 | 2024-12-22T09:15:00.000Z trail_stop 96759.6 | unexplained | exit_ts ref=2024-12-22T07:00:00.000Z eng=2024-12-22T09:15:00.000Z reason ref=trail_stop eng=trail_stop | bars=[{'open': '2024-12-22 06:45:00+00:00', 'o': np.flo |
| B | ('XRP/USDT', 'short', '2024-12-22T01:30:00.000Z') | qty | 476.2 | 476.6 | chained_after_first | karar boyutu ref=476.3 motor=476.7: ozsermaye/risk durumu farki |
| C | ('XRP/USDT', 'short', '2024-12-22T01:30:00.000Z') | exit_ts | 2024-12-22T06:45:00.000Z trail_stop 2.2325 | 2024-12-22T07:00:00.000Z trail_stop 2.2325 | trail_timing | iz stop bir bar sonra: ref 2024-12-22T06:45:00.000Z eng 2024-12-22T07:00:00.000Z |
| A | ('BNB/USDT', 'short', 'T1', '15m', '2024-12-22T01:45:00.000Z') | decision_only_in_engine | None | None | chained_after_first | yalniz motorda karar; genelde onceki islem sapmasi yuzunden pozisyon durumu farkli |
| A | ('TRX/USDT', 'short', 'T1', '15m', '2024-12-22T01:45:00.000Z') | decision_only_in_engine | None | None | chained_after_first | yalniz motorda karar; genelde onceki islem sapmasi yuzunden pozisyon durumu farkli |
| A | ('BNB/USDT', 'short', 'T1', '15m', '2024-12-22T02:45:00.000Z') | decision_only_in_engine | None | None | chained_after_first | yalniz motorda karar; genelde onceki islem sapmasi yuzunden pozisyon durumu farkli |
| A | ('TRX/USDT', 'short', 'T1', '15m', '2024-12-22T02:45:00.000Z') | decision_only_in_engine | None | None | chained_after_first | yalniz motorda karar; genelde onceki islem sapmasi yuzunden pozisyon durumu farkli |
| A | ('BNB/USDT', 'short', 'T1', '15m', '2024-12-22T04:15:00.000Z') | decision_only_in_engine | None | None | chained_after_first | yalniz motorda karar; genelde onceki islem sapmasi yuzunden pozisyon durumu farkli |
| A | ('TRX/USDT', 'short', 'T1', '15m', '2024-12-22T04:45:00.000Z') | decision_only_in_engine | None | None | chained_after_first | yalniz motorda karar; genelde onceki islem sapmasi yuzunden pozisyon durumu farkli |
| B | ('BNB/USDT', 'short', '2024-12-22T07:30:00.000Z') | size_ratio | 7.379709527995315 | 7.425263290513804 | chained_after_first | planned_risk ref=7.37971 eng=7.42526 (rel 6.17e-03); ozsermaye tahmini ref=1075.59593157 motor(karar ani)=1078.6458051812347 |
| B | ('BNB/USDT', 'short', '2024-12-22T07:30:00.000Z') | qty | 1.62 | 1.63 | chained_after_first | karar boyutu ref=1.62 motor=1.63: ozsermaye/risk durumu farki |
| B | ('XRP/USDT', 'short', '2024-12-22T07:30:00.000Z') | qty | 481.6 | 483.4 | chained_after_first | karar boyutu ref=481.6 motor=483.4: ozsermaye/risk durumu farki |
| D | ('XRP/USDT', 'short', '2024-12-22T07:30:00.000Z') | funding_paid | -0.21466929615040004 | -0.10773581577980001 | funding_boundary | sinir noktalari (giris/cikis anindaki 00/08/16): referans giris x0, cikis x2; motor giris x0, cikis x1 (veriden yeniden hesapla birebir uyumlu; 03 §5 `opened_ts |
| B | ('TRX/USDT', 'short', '2024-12-22T07:45:00.000Z') | entry_missing_in_engine | 0.24488 | None | chained_after_first | motor karari: skipped/risk_denied (toplam teminat özsermayeyi aşar) |
| B | ('LINK/USDT', 'short', '2024-12-22T18:00:00.000Z') | size_ratio | 13.366883978259622 | 13.456764265568784 | chained_after_first | planned_risk ref=13.3669 eng=13.4568 (rel 6.72e-03); ozsermaye tahmini ref=1053.93190508 motor(karar ani)=1061.0710542370146 |
| B | ('LINK/USDT', 'short', '2024-12-22T18:00:00.000Z') | qty | 47.59 | 47.91 | chained_after_first | karar boyutu ref=47.59 motor=47.91: ozsermaye/risk durumu farki |
| B | ('XRP/USDT', 'short', '2024-12-22T18:15:00.000Z') | entry_missing_in_engine | 2.2272 | None | margin_accounting | motor karari var ama giris dolumunda `order_failed` (PaperBroker: margin+fee > cuzdan-kullanilan marjin = `insufficient_margin`); freqtrade serbest bakiyeden ac |
| B | ('TRX/USDT', 'short', '2024-12-22T18:15:00.000Z') | size_ratio | 9.74437281217983 | 9.825015584194093 | chained_after_first | planned_risk ref=9.74437 eng=9.82502 (rel 8.28e-03); ozsermaye tahmini ref=1053.93190508 motor(karar ani)=1064.4691668070147 |
| B | ('TRX/USDT', 'short', '2024-12-22T18:15:00.000Z') | qty | 4157.6 | 4325.1 | chained_after_first | karar boyutu ref=4289.6 motor=4325.1: ozsermaye/risk durumu farki |
| B | ('SOL/USDT', 'short', '2024-12-22T19:00:00.000Z') | entry_missing_in_engine | 181.8 | None | chained_after_first | motor karari: skipped/risk_denied (günlük zarar bütçesi aşılır) |
| B | ('SOL/USDT', 'short', '2024-12-22T21:45:00.000Z') | size_ratio | 9.092916194955416 | 9.285020058229122 | chained_after_first | planned_risk ref=9.09292 eng=9.28502 (rel 2.11e-02); ozsermaye tahmini ref=1032.31863738 motor(karar ani)=1052.8258906960145 |
| B | ('SOL/USDT', 'short', '2024-12-22T21:45:00.000Z') | qty | 5.68 | 5.79 | chained_after_first | karar boyutu ref=5.68 motor=5.8: ozsermaye/risk durumu farki |
| B | ('DOGE/USDT', 'short', '2024-12-22T21:45:00.000Z') | size_ratio | 11.175753873597332 | 11.409455051993543 | chained_after_first | planned_risk ref=11.1758 eng=11.4095 (rel 2.09e-02); ozsermaye tahmini ref=1032.31863738 motor(karar ani)=1052.8258906960145 |
| B | ('DOGE/USDT', 'short', '2024-12-22T21:45:00.000Z') | qty | 3280.5 | 3349.0 | chained_after_first | karar boyutu ref=3280.5 motor=3349.1: ozsermaye/risk durumu farki |
| C | ('SOL/USDT', 'short', '2024-12-22T21:45:00.000Z') | exit_ts | 2024-12-23T01:30:00.000Z trail_stop 181.571 | 2024-12-23T03:00:00.000Z trail_stop 181.571 | unexplained | exit_ts ref=2024-12-23T01:30:00.000Z eng=2024-12-23T03:00:00.000Z reason ref=trail_stop eng=trail_stop | bars=[{'open': '2024-12-23 01:15:00+00:00', 'o': np.flo |
| C | ('DOGE/USDT', 'short', '2024-12-22T21:45:00.000Z') | exit_ts | 2024-12-23T01:30:00.000Z trail_stop 0.31319 | 2024-12-23T03:00:00.000Z trail_stop 0.31319 | unexplained | exit_ts ref=2024-12-23T01:30:00.000Z eng=2024-12-23T03:00:00.000Z reason ref=trail_stop eng=trail_stop | bars=[{'open': '2024-12-23 01:15:00+00:00', 'o': np.flo |
| B | ('ADA/USDT', 'short', '2024-12-22T22:00:00.000Z') | size_ratio | 14.557076543955185 | 14.860544505434584 | chained_after_first | planned_risk ref=14.5571 eng=14.8605 (rel 2.08e-02); ozsermaye tahmini ref=1041.8984923799997 motor(karar ani)=1061.5459134260143 |
| B | ('ADA/USDT', 'short', '2024-12-22T22:00:00.000Z') | qty | 930.5 | 950.0 | chained_after_first | karar boyutu ref=930.6 motor=950.0: ozsermaye/risk durumu farki |
| A | ('LINK/USDT', 'short', 'T1', '15m', '2024-12-22T23:45:00.000Z') | decision_only_in_engine | None | None | chained_after_first | yalniz motorda karar; genelde onceki islem sapmasi yuzunden pozisyon durumu farkli |
| A | ('DOGE/USDT', 'short', 'T1', '15m', '2024-12-23T02:00:00.000Z') | decision_only_in_reference | None | None | chained_after_first | yalniz referansta karar; genelde onceki islem sapmasi yuzunden pozisyon durumu farkli |
| B | ('DOGE/USDT', 'short', '2024-12-23T02:00:00.000Z') | entry_missing_in_engine | 0.30895 | None | chained_after_first | referans girisi motorda yok (motorda karar kaydi da yok: pozisyon durumu farki) |
| B | ('TRX/USDT', 'short', '2024-12-23T02:00:00.000Z') | entry_missing_in_engine | 0.2433 | None | chained_after_first | motor karari: skipped/risk_denied (aynı yön (short) risk sınırı aşılır) |
| B | ('XRP/USDT', 'short', '2024-12-23T05:15:00.000Z') | size_ratio | 14.079472670063879 | 14.685510577694041 | chained_after_first | planned_risk ref=14.0795 eng=14.6855 (rel 4.30e-02); ozsermaye tahmini ref=1005.88408629 motor(karar ani)=1049.0794592186057 |
| B | ('XRP/USDT', 'short', '2024-12-23T05:15:00.000Z') | qty | 290.4 | 302.9 | chained_after_first | karar boyutu ref=290.4 motor=302.9: ozsermaye/risk durumu farki |
| B | ('BTC/USDT', 'short', '2024-12-23T08:30:00.000Z') | size_ratio | 8.021847335577498 | 8.824032069135246 | chained_after_first | planned_risk ref=8.02185 eng=8.82403 (rel 1.00e-01); ozsermaye tahmini ref=1011.43072629 motor(karar ani)=1055.1106998101013 |
| B | ('BTC/USDT', 'short', '2024-12-23T08:30:00.000Z') | qty | 0.009 | 0.011 | chained_after_first | karar boyutu ref=0.01 motor=0.011: ozsermaye/risk durumu farki |
| B | ('ETH/USDT', 'short', '2024-12-23T08:30:00.000Z') | entry_extra_in_engine | None | 3294.25 | chained_after_first | motorda fazla giris |
| B | ('SOL/USDT', 'short', '2024-12-23T14:45:00.000Z') | size_ratio | 14.14258702727731 | 14.596706794208233 | chained_after_first | planned_risk ref=14.1426 eng=14.5967 (rel 3.21e-02); ozsermaye tahmini ref=1004.83748709 motor(karar ani)=1044.4939898101013 |
| B | ('SOL/USDT', 'short', '2024-12-23T14:45:00.000Z') | qty | 4.36 | 4.49 | chained_after_first | karar boyutu ref=4.36 motor=4.5: ozsermaye/risk durumu farki |
| B | ('ADA/USDT', 'short', '2024-12-24T06:15:00.000Z') | size_ratio | 13.694299075632197 | 14.156345587243006 | chained_after_first | planned_risk ref=13.6943 eng=14.1563 (rel 3.37e-02); ozsermaye tahmini ref=982.28416854 motor(karar ani)=1015.4535882566612 |
| B | ('ADA/USDT', 'short', '2024-12-24T06:15:00.000Z') | qty | 1081.8 | 1118.3 | chained_after_first | karar boyutu ref=1081.8 motor=1118.3: ozsermaye/risk durumu farki |
| A | ('DOGE/USDT', 'short', 'T1', '15m', '2024-12-24T09:15:00.000Z') | decision_only_in_engine | None | None | chained_after_first | yalniz motorda karar; genelde onceki islem sapmasi yuzunden pozisyon durumu farkli |
| B | ('ETH/USDT', 'short', '2024-12-24T09:15:00.000Z') | size_ratio | 10.859577704543428 | 11.231481050589437 | chained_after_first | planned_risk ref=10.8596 eng=11.2315 (rel 3.42e-02); ozsermaye tahmini ref=982.64730854 motor(karar ani)=1026.5963714436612 |
| B | ('ETH/USDT', 'short', '2024-12-24T09:15:00.000Z') | qty | 0.292 | 0.302 | chained_after_first | karar boyutu ref=0.292 motor=0.302: ozsermaye/risk durumu farki |
| A | ('XRP/USDT', 'short', 'T1', '15m', '2024-12-24T10:30:00.000Z') | decision_only_in_engine | None | None | chained_after_first | yalniz motorda karar; genelde onceki islem sapmasi yuzunden pozisyon durumu farkli |
| A | ('DOGE/USDT', 'short', 'T1', '15m', '2024-12-24T12:15:00.000Z') | decision_only_in_engine | None | None | chained_after_first | yalniz motorda karar; genelde onceki islem sapmasi yuzunden pozisyon durumu farkli |
| A | ('XRP/USDT', 'short', 'T1', '15m', '2024-12-24T12:15:00.000Z') | decision_only_in_engine | None | None | chained_after_first | yalniz motorda karar; genelde onceki islem sapmasi yuzunden pozisyon durumu farkli |
| B | ('SOL/USDT', 'short', '2024-12-24T16:30:00.000Z') | size_ratio | 11.548099578710548 | 11.924412395939406 | chained_after_first | planned_risk ref=11.5481 eng=11.9244 (rel 3.26e-02); ozsermaye tahmini ref=967.63791352 motor(karar ani)=1000.4397203736611 |
| B | ('SOL/USDT', 'short', '2024-12-24T16:30:00.000Z') | qty | 4.91 | 5.07 | chained_after_first | karar boyutu ref=4.91 motor=5.07: ozsermaye/risk durumu farki |
| B | ('LINK/USDT', 'short', '2024-12-24T18:45:00.000Z') | size_ratio | 9.53820442927413 | 9.866270059325597 | chained_after_first | planned_risk ref=9.5382 eng=9.86627 (rel 3.44e-02); ozsermaye tahmini ref=960.8072336399999 motor(karar ani)=1003.5907760736611 |
| B | ('LINK/USDT', 'short', '2024-12-24T18:45:00.000Z') | qty | 39.25 | 40.6 | chained_after_first | karar boyutu ref=39.25 motor=40.6: ozsermaye/risk durumu farki |
| B | ('DOGE/USDT', 'short', '2024-12-25T03:15:00.000Z') | size_ratio | 12.320084225271923 | 12.737838934762324 | chained_after_first | planned_risk ref=12.3201 eng=12.7378 (rel 3.39e-02); ozsermaye tahmini ref=948.50281737 motor(karar ani)=980.6656174287411 |
| B | ('DOGE/USDT', 'short', '2024-12-25T03:15:00.000Z') | qty | 2845.9 | 2942.4 | chained_after_first | karar boyutu ref=2845.9 motor=2942.4: ozsermaye/risk durumu farki |
| B | ('SOL/USDT', 'short', '2024-12-25T07:45:00.000Z') | size_ratio | 11.216192402039967 | 11.589288199197222 | chained_after_first | planned_risk ref=11.2162 eng=11.5893 (rel 3.33e-02); ozsermaye tahmini ref=952.0601923700001 motor(karar ani)=985.8541278927413 |
| B | ('SOL/USDT', 'short', '2024-12-25T07:45:00.000Z') | qty | 4.8 | 4.97 | chained_after_first | karar boyutu ref=4.81 motor=4.97: ozsermaye/risk durumu farki |
| B | ('ETH/USDT', 'short', '2024-12-25T15:15:00.000Z') | entry_extra_in_engine | None | 3475.65 | chained_after_first | motorda fazla giris |
| B | ('BNB/USDT', 'long', '2024-12-25T20:00:00.000Z') | size_ratio | 6.608135768669018 | 6.811463023089603 | chained_after_first | planned_risk ref=6.60814 eng=6.81146 (rel 3.08e-02); ozsermaye tahmini ref=920.19135195 motor(karar ani)=949.8163022351094 |
| B | ('BNB/USDT', 'long', '2024-12-25T20:00:00.000Z') | qty | 1.29 | 1.33 | chained_after_first | karar boyutu ref=1.3 motor=1.34: ozsermaye/risk durumu farki |
| B | ('BNB/USDT', 'long', '2024-12-26T00:15:00.000Z') | size_ratio | 6.428213015004475 | 6.626004184696922 | chained_after_first | planned_risk ref=6.42821 eng=6.626 (rel 3.08e-02); ozsermaye tahmini ref=914.5506528 motor(karar ani)=944.0006976851093 |
... 5699 fark daha (json'da)
