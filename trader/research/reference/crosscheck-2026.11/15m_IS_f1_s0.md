# Capraz dogrulama: 15m_IS_f1_s0

Sonuc: **RED** (aciklanamayan: 0)

| Duzey | Olcut | Deger | Kabul |
|---|---|---|---|
| A kararlar | ortak anahtarda esit | 2800/2800 (100.00%); yalniz ref 49, yalniz motor 1274 | evet |
| B girisler | eslesen/ref (anahtar+fiyat+boyut) | 14/2195 (0.64%); yalniz anahtar 85.56%, anahtar+fiyat 85.56% | hayir |
| C cikislar | eslesen girislerde | 1607/1878 (85.57%; kesin 85.57%, trail +-1: 0) | hayir |
| D sum_R | ref -160.564 / motor -130.43 (fark 30.13, tol 3.211) | | hayir |
| D fees | ref 892.965 / motor 1133.75 (fark 240.8, tol 17.86) | | hayir |
| D funding | ref 8.53273 / motor 10.2676 (fark 1.735, tol 0.4266) | | hayir |
| D n_trades | ref 2195 / motor 2143 (fark -52, tol 21.95) | | hayir |

Sinif sayilari: aggregate=4, chained_after_first=5382, exit_before_entry=90, funding_boundary=111, gap_fill=191, margin_accounting=155, price_rounding=80
unexplained: 0

## Ilk sapma
C ('BTC/USDT', 'short', '2024-12-21T12:15:00.000Z') exit_price: ref=2024-12-21T14:15:00.000Z trail_stop 97710.5 motor=2024-12-21T14:15:00.000Z trail_stop 97687.6 sinif=gap_fill | cikis fiyati ref=97710.5 eng=97687.6 rel=2.34e-04

## Farklar

| duzey | anahtar | alan | ref | motor | sinif | kanit |
|---|---|---|---|---|---|---|
| C | ('BTC/USDT', 'short', '2024-12-21T12:15:00.000Z') | exit_price | 2024-12-21T14:15:00.000Z trail_stop 97710.5 | 2024-12-21T14:15:00.000Z trail_stop 97687.6 | gap_fill | cikis fiyati ref=97710.5 eng=97687.6 rel=2.34e-04 |
| B | ('XRP/USDT', 'short', '2024-12-22T01:30:00.000Z') | qty | 476.2 | 476.8 | chained_after_first | karar boyutu ref=476.3 motor=476.8: ozsermaye/risk durumu farki |
| A | ('BNB/USDT', 'short', 'T1', '15m', '2024-12-22T01:45:00.000Z') | decision_only_in_engine | None | None | chained_after_first | yalniz motorda karar; genelde onceki islem sapmasi yuzunden pozisyon durumu farkli |
| A | ('TRX/USDT', 'short', 'T1', '15m', '2024-12-22T01:45:00.000Z') | decision_only_in_engine | None | None | chained_after_first | yalniz motorda karar; genelde onceki islem sapmasi yuzunden pozisyon durumu farkli |
| A | ('BNB/USDT', 'short', 'T1', '15m', '2024-12-22T02:45:00.000Z') | decision_only_in_engine | None | None | chained_after_first | yalniz motorda karar; genelde onceki islem sapmasi yuzunden pozisyon durumu farkli |
| A | ('TRX/USDT', 'short', 'T1', '15m', '2024-12-22T02:45:00.000Z') | decision_only_in_engine | None | None | chained_after_first | yalniz motorda karar; genelde onceki islem sapmasi yuzunden pozisyon durumu farkli |
| A | ('BNB/USDT', 'short', 'T1', '15m', '2024-12-22T04:15:00.000Z') | decision_only_in_engine | None | None | chained_after_first | yalniz motorda karar; genelde onceki islem sapmasi yuzunden pozisyon durumu farkli |
| A | ('TRX/USDT', 'short', 'T1', '15m', '2024-12-22T04:45:00.000Z') | decision_only_in_engine | None | None | chained_after_first | yalniz motorda karar; genelde onceki islem sapmasi yuzunden pozisyon durumu farkli |
| B | ('XRP/USDT', 'short', '2024-12-22T07:30:00.000Z') | qty | 481.6 | 482.1 | chained_after_first | karar boyutu ref=481.6 motor=482.1: ozsermaye/risk durumu farki |
| D | ('XRP/USDT', 'short', '2024-12-22T07:30:00.000Z') | funding_paid | -0.21466929615040004 | -0.10744608354870003 | funding_boundary | sinir noktalari (giris/cikis anindaki 00/08/16): referans giris x0, cikis x2; motor giris x0, cikis x1 (veriden yeniden hesapla birebir uyumlu; 03 §5 `opened_ts |
| B | ('TRX/USDT', 'short', '2024-12-22T07:45:00.000Z') | entry_missing_in_engine | 0.24488 | None | margin_accounting | motor karari var ama giris dolumunda `order_failed` (PaperBroker: margin+fee > cuzdan-kullanilan marjin = `insufficient_margin`); freqtrade serbest bakiyeden ac |
| B | ('LINK/USDT', 'short', '2024-12-22T18:00:00.000Z') | size_ratio | 13.366883978259622 | 13.453955506590374 | chained_after_first | planned_risk ref=13.3669 eng=13.454 (rel 6.51e-03); ozsermaye tahmini ref=1053.93190508 motor(karar ani)=1060.9360976447833 |
| B | ('LINK/USDT', 'short', '2024-12-22T18:00:00.000Z') | qty | 47.59 | 47.9 | chained_after_first | karar boyutu ref=47.59 motor=47.9: ozsermaye/risk durumu farki |
| B | ('XRP/USDT', 'short', '2024-12-22T18:15:00.000Z') | entry_missing_in_engine | 2.2272 | None | margin_accounting | motor karari var ama giris dolumunda `order_failed` (PaperBroker: margin+fee > cuzdan-kullanilan marjin = `insufficient_margin`); freqtrade serbest bakiyeden ac |
| B | ('TRX/USDT', 'short', '2024-12-22T18:15:00.000Z') | size_ratio | 9.74437281217983 | 9.823879770503751 | chained_after_first | planned_risk ref=9.74437 eng=9.82388 (rel 8.16e-03); ozsermaye tahmini ref=1053.93190508 motor(karar ani)=1064.3335009447833 |
| B | ('TRX/USDT', 'short', '2024-12-22T18:15:00.000Z') | qty | 4157.6 | 4324.6 | chained_after_first | karar boyutu ref=4289.6 motor=4324.6: ozsermaye/risk durumu farki |
| B | ('SOL/USDT', 'short', '2024-12-22T19:00:00.000Z') | entry_missing_in_engine | 181.8 | None | chained_after_first | motor karari: skipped/risk_denied (günlük zarar bütçesi aşılır) |
| B | ('SOL/USDT', 'short', '2024-12-22T21:45:00.000Z') | size_ratio | 9.092916194955416 | 9.269011402956313 | chained_after_first | planned_risk ref=9.09292 eng=9.26901 (rel 1.94e-02); ozsermaye tahmini ref=1032.31863738 motor(karar ani)=1052.6930394987835 |
| B | ('SOL/USDT', 'short', '2024-12-22T21:45:00.000Z') | qty | 5.68 | 5.79 | chained_after_first | karar boyutu ref=5.68 motor=5.79: ozsermaye/risk durumu farki |
| B | ('DOGE/USDT', 'short', '2024-12-22T21:45:00.000Z') | size_ratio | 11.175753873597332 | 11.40775169063497 | chained_after_first | planned_risk ref=11.1758 eng=11.4078 (rel 2.08e-02); ozsermaye tahmini ref=1032.31863738 motor(karar ani)=1052.6930394987835 |
| B | ('DOGE/USDT', 'short', '2024-12-22T21:45:00.000Z') | qty | 3280.5 | 3348.6 | chained_after_first | karar boyutu ref=3280.5 motor=3348.6: ozsermaye/risk durumu farki |
| B | ('ADA/USDT', 'short', '2024-12-22T22:00:00.000Z') | size_ratio | 14.557076543955185 | 14.858980237591908 | chained_after_first | planned_risk ref=14.5571 eng=14.859 (rel 2.07e-02); ozsermaye tahmini ref=1041.8984923799997 motor(karar ani)=1061.4126011007834 |
| B | ('ADA/USDT', 'short', '2024-12-22T22:00:00.000Z') | qty | 930.5 | 949.9 | chained_after_first | karar boyutu ref=930.6 motor=949.9: ozsermaye/risk durumu farki |
| A | ('LINK/USDT', 'short', 'T1', '15m', '2024-12-22T23:45:00.000Z') | decision_only_in_engine | None | None | chained_after_first | yalniz motorda karar; genelde onceki islem sapmasi yuzunden pozisyon durumu farkli |
| B | ('DOGE/USDT', 'short', '2024-12-23T02:00:00.000Z') | size_ratio | 14.650587336344797 | 14.946233554320985 | chained_after_first | planned_risk ref=14.6506 eng=14.9462 (rel 2.02e-02); ozsermaye tahmini ref=1047.25855532 motor(karar ani)=1067.6086382178153 |
| B | ('DOGE/USDT', 'short', '2024-12-23T02:00:00.000Z') | qty | 2002.0 | 2042.4 | chained_after_first | karar boyutu ref=2002.0 motor=2042.4: ozsermaye/risk durumu farki |
| B | ('TRX/USDT', 'short', '2024-12-23T02:00:00.000Z') | size_ratio | 9.816118529913673 | 10.020035850201504 | chained_after_first | planned_risk ref=9.81612 eng=10.02 (rel 2.08e-02); ozsermaye tahmini ref=1047.25855532 motor(karar ani)=1067.6086382178153 |
| B | ('TRX/USDT', 'short', '2024-12-23T02:00:00.000Z') | qty | 4298.7 | 4388.0 | chained_after_first | karar boyutu ref=4298.7 motor=4388.0: ozsermaye/risk durumu farki |
| B | ('XRP/USDT', 'short', '2024-12-23T05:15:00.000Z') | entry_missing_in_engine | 2.1968 | None | chained_after_first | motor karari: skipped/risk_denied (günlük zarar bütçesi aşılır) |
| B | ('SOL/USDT', 'short', '2024-12-23T14:45:00.000Z') | entry_missing_in_engine | 182.57 | None | chained_after_first | motor karari: skipped/risk_denied (günlük zarar bütçesi aşılır) |
| C | ('BTC/USDT', 'short', '2024-12-24T01:45:00.000Z') | exit_price | 2024-12-24T05:15:00.000Z trail_stop 94587.1 | 2024-12-24T05:15:00.000Z trail_stop 94552.1 | gap_fill | cikis fiyati ref=94587.1 eng=94552.1 rel=3.70e-04 |
| B | ('ADA/USDT', 'short', '2024-12-24T06:15:00.000Z') | size_ratio | 13.694299075632197 | 14.144952659559456 | chained_after_first | planned_risk ref=13.6943 eng=14.145 (rel 3.29e-02); ozsermaye tahmini ref=982.28416854 motor(karar ani)=1014.6587106598151 |
| B | ('ADA/USDT', 'short', '2024-12-24T06:15:00.000Z') | qty | 1081.8 | 1117.4 | chained_after_first | karar boyutu ref=1081.8 motor=1117.4: ozsermaye/risk durumu farki |
| A | ('DOGE/USDT', 'short', 'T1', '15m', '2024-12-24T09:15:00.000Z') | decision_only_in_engine | None | None | chained_after_first | yalniz motorda karar; genelde onceki islem sapmasi yuzunden pozisyon durumu farkli |
| B | ('ETH/USDT', 'short', '2024-12-24T09:15:00.000Z') | size_ratio | 10.859577704543428 | 11.231481050589437 | chained_after_first | planned_risk ref=10.8596 eng=11.2315 (rel 3.42e-02); ozsermaye tahmini ref=982.64730854 motor(karar ani)=1025.7939015458153 |
| B | ('ETH/USDT', 'short', '2024-12-24T09:15:00.000Z') | qty | 0.292 | 0.302 | chained_after_first | karar boyutu ref=0.292 motor=0.302: ozsermaye/risk durumu farki |
| A | ('XRP/USDT', 'short', 'T1', '15m', '2024-12-24T10:30:00.000Z') | decision_only_in_engine | None | None | chained_after_first | yalniz motorda karar; genelde onceki islem sapmasi yuzunden pozisyon durumu farkli |
| A | ('DOGE/USDT', 'short', 'T1', '15m', '2024-12-24T12:15:00.000Z') | decision_only_in_engine | None | None | chained_after_first | yalniz motorda karar; genelde onceki islem sapmasi yuzunden pozisyon durumu farkli |
| A | ('XRP/USDT', 'short', 'T1', '15m', '2024-12-24T12:15:00.000Z') | decision_only_in_engine | None | None | chained_after_first | yalniz motorda karar; genelde onceki islem sapmasi yuzunden pozisyon durumu farkli |
| B | ('SOL/USDT', 'short', '2024-12-24T16:30:00.000Z') | size_ratio | 11.548099578710548 | 11.924412395939406 | chained_after_first | planned_risk ref=11.5481 eng=11.9244 (rel 3.26e-02); ozsermaye tahmini ref=967.63791352 motor(karar ani)=999.6455790758151 |
| B | ('SOL/USDT', 'short', '2024-12-24T16:30:00.000Z') | qty | 4.91 | 5.07 | chained_after_first | karar boyutu ref=4.91 motor=5.07: ozsermaye/risk durumu farki |
| B | ('LINK/USDT', 'short', '2024-12-24T18:45:00.000Z') | size_ratio | 9.53820442927413 | 9.85897971199112 | chained_after_first | planned_risk ref=9.5382 eng=9.85898 (rel 3.36e-02); ozsermaye tahmini ref=960.8072336399999 motor(karar ani)=1002.7966347758152 |
| B | ('LINK/USDT', 'short', '2024-12-24T18:45:00.000Z') | qty | 39.25 | 40.57 | chained_after_first | karar boyutu ref=39.25 motor=40.57: ozsermaye/risk durumu farki |
| B | ('DOGE/USDT', 'short', '2024-12-25T03:15:00.000Z') | size_ratio | 12.320084225271923 | 12.727882086764108 | chained_after_first | planned_risk ref=12.3201 eng=12.7279 (rel 3.31e-02); ozsermaye tahmini ref=948.50281737 motor(karar ani)=979.8780105358951 |
| B | ('DOGE/USDT', 'short', '2024-12-25T03:15:00.000Z') | qty | 2845.9 | 2940.1 | chained_after_first | karar boyutu ref=2845.9 motor=2940.1: ozsermaye/risk durumu farki |
| B | ('SOL/USDT', 'short', '2024-12-25T07:45:00.000Z') | size_ratio | 11.216192402039967 | 11.589288199197222 | chained_after_first | planned_risk ref=11.2162 eng=11.5893 (rel 3.33e-02); ozsermaye tahmini ref=952.0601923700001 motor(karar ani)=985.0624652718952 |
| B | ('SOL/USDT', 'short', '2024-12-25T07:45:00.000Z') | qty | 4.8 | 4.97 | chained_after_first | karar boyutu ref=4.81 motor=4.97: ozsermaye/risk durumu farki |
| B | ('ETH/USDT', 'short', '2024-12-25T15:15:00.000Z') | entry_extra_in_engine | None | 3475.65 | chained_after_first | motorda fazla giris |
| B | ('BNB/USDT', 'long', '2024-12-25T20:00:00.000Z') | size_ratio | 6.608135768669018 | 6.811463023089603 | chained_after_first | planned_risk ref=6.60814 eng=6.81146 (rel 3.08e-02); ozsermaye tahmini ref=920.19135195 motor(karar ani)=949.3711118212685 |
| B | ('BNB/USDT', 'long', '2024-12-25T20:00:00.000Z') | qty | 1.29 | 1.33 | chained_after_first | karar boyutu ref=1.3 motor=1.34: ozsermaye/risk durumu farki |
| B | ('BNB/USDT', 'long', '2024-12-26T00:15:00.000Z') | size_ratio | 6.428213015004475 | 6.626004184696922 | chained_after_first | planned_risk ref=6.42821 eng=6.626 (rel 3.08e-02); ozsermaye tahmini ref=914.5506528 motor(karar ani)=943.5555072712684 |
| B | ('BNB/USDT', 'long', '2024-12-26T00:15:00.000Z') | qty | 1.3 | 1.34 | chained_after_first | karar boyutu ref=1.3 motor=1.34: ozsermaye/risk durumu farki |
| B | ('TRX/USDT', 'short', '2024-12-26T01:45:00.000Z') | size_ratio | 6.405081060637797 | 6.611556847759348 | chained_after_first | planned_risk ref=6.40508 eng=6.61156 (rel 3.22e-02); ozsermaye tahmini ref=912.8736528000001 motor(karar ani)=941.2618158712684 |
| B | ('TRX/USDT', 'short', '2024-12-26T01:45:00.000Z') | qty | 3548.8 | 3663.2 | chained_after_first | karar boyutu ref=3548.8 motor=3663.2: ozsermaye/risk durumu farki |
| B | ('ETH/USDT', 'short', '2024-12-26T02:45:00.000Z') | size_ratio | 5.992322630759952 | 6.175294314141936 | chained_after_first | planned_risk ref=5.99232 eng=6.17529 (rel 3.05e-02); ozsermaye tahmini ref=915.5412193 motor(karar ani)=941.8116422512685 |
| B | ('ETH/USDT', 'short', '2024-12-26T02:45:00.000Z') | qty | 0.262 | 0.27 | exit_before_entry | karar boyutu ref=0.262 motor=0.27: ozsermaye/risk durumu farki; ayni adimda cikan referans islem(ler) [('BNB/USDT', 'long', '2024-12-26T00:15:00.000Z')]: refera |
| B | ('SOL/USDT', 'short', '2024-12-26T03:00:00.000Z') | size_ratio | 12.450190672043513 | 12.8518097259804 | chained_after_first | planned_risk ref=12.4502 eng=12.8518 (rel 3.23e-02); ozsermaye tahmini ref=918.9681552999999 motor(karar ani)=947.1701673512683 |
| B | ('SOL/USDT', 'short', '2024-12-26T03:00:00.000Z') | qty | 4.56 | 4.8 | chained_after_first | karar boyutu ref=4.65 motor=4.8: ozsermaye/risk durumu farki |
| A | ('BNB/USDT', 'long', 'T1', '15m', '2024-12-26T03:45:00.000Z') | decision_only_in_engine | None | None | chained_after_first | yalniz motorda karar; genelde onceki islem sapmasi yuzunden pozisyon durumu farkli |
| A | ('BNB/USDT', 'long', 'T1', '15m', '2024-12-26T04:30:00.000Z') | decision_only_in_engine | None | None | chained_after_first | yalniz motorda karar; genelde onceki islem sapmasi yuzunden pozisyon durumu farkli |
... 5953 fark daha (json'da)
