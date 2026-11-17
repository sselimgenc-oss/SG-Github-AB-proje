# Capraz dogrulama: 1h_WF_f1_s0

Sonuc: **RED** (aciklanamayan: 17)

| Duzey | Olcut | Deger | Kabul |
|---|---|---|---|
| A kararlar | ortak anahtarda esit | 571/571 (100.00%); yalniz ref 4, yalniz motor 80 | evet |
| B girisler | eslesen/ref (anahtar+fiyat+boyut) | 18/376 (4.79%); yalniz anahtar 86.70%, anahtar+fiyat 86.70% | hayir |
| C cikislar | eslesen girislerde | 274/326 (84.05%; kesin 82.52%, trail +-1: 5) | hayir |
| D sum_R | ref 23.6566 / motor 35.7112 (fark 12.05, tol 0.4731) | | hayir |
| D fees | ref 393.158 / motor 367.909 (fark -25.25, tol 7.863) | | hayir |
| D funding | ref 9.04324 / motor 9.6275 (fark 0.5843, tol 0.4522) | | hayir |
| D n_trades | ref 376 / motor 342 (fark -34, tol 3.76) | | hayir |

Sinif sayilari: aggregate=4, chained_after_first=736, decision_only=1, exit_before_entry=4, funding_boundary=32, gap_fill=25, margin_accounting=24, open_at_end=2, price_rounding=8, trail_timing=5, unexplained=17
unexplained: 17

## Ilk sapma
A ('DOGE/USDT', 'short', 'T1', '1h', '2025-11-01T06:00:00.000Z') decision_only_in_engine: ref=None motor=None sinif=decision_only | yalniz motorda karar; genelde onceki islem sapmasi yuzunden pozisyon durumu farkli

## Farklar

| duzey | anahtar | alan | ref | motor | sinif | kanit |
|---|---|---|---|---|---|---|
| A | ('DOGE/USDT', 'short', 'T1', '1h', '2025-11-01T06:00:00.000Z') | decision_only_in_engine | None | None | decision_only | yalniz motorda karar; genelde onceki islem sapmasi yuzunden pozisyon durumu farkli |
| A | ('LINK/USDT', 'short', 'T1', '1h', '2025-11-01T06:00:00.000Z') | decision_only_in_engine | None | None | chained_after_first | yalniz motorda karar; genelde onceki islem sapmasi yuzunden pozisyon durumu farkli |
| A | ('TRX/USDT', 'short', 'T1', '1h', '2025-11-01T06:00:00.000Z') | decision_only_in_engine | None | None | chained_after_first | yalniz motorda karar; genelde onceki islem sapmasi yuzunden pozisyon durumu farkli |
| B | ('XRP/USDT', 'short', '2025-11-01T06:00:00.000Z') | qty | 392.6 | 398.4 | chained_after_first | karar boyutu ref=397.9 motor=398.5: ozsermaye/risk durumu farki |
| C | ('XRP/USDT', 'short', '2025-11-01T06:00:00.000Z') | exit_price | 2025-11-02T04:30:00.000Z trail_stop 2.5179 | 2025-11-02T04:30:00.000Z trail_stop 2.5189 | gap_fill | cikis fiyati ref=2.5179 eng=2.5189 rel=3.97e-04 |
| B | ('ADA/USDT', 'short', '2025-11-01T10:00:00.000Z') | entry_missing_in_engine | 0.6133 | None | chained_after_first | motor karari: skipped/risk_denied (toplam teminat özsermayeyi aşar) |
| A | ('DOGE/USDT', 'short', 'T1', '1h', '2025-11-01T18:00:00.000Z') | decision_only_in_engine | None | None | chained_after_first | yalniz motorda karar; genelde onceki islem sapmasi yuzunden pozisyon durumu farkli |
| A | ('ADA/USDT', 'short', 'T1', '1h', '2025-11-01T22:00:00.000Z') | decision_only_in_engine | None | None | chained_after_first | yalniz motorda karar; genelde onceki islem sapmasi yuzunden pozisyon durumu farkli |
| A | ('AVAX/USDT', 'short', 'T1', '1h', '2025-11-01T22:00:00.000Z') | decision_only_in_engine | None | None | chained_after_first | yalniz motorda karar; genelde onceki islem sapmasi yuzunden pozisyon durumu farkli |
| A | ('BNB/USDT', 'short', 'T1', '1h', '2025-11-01T22:00:00.000Z') | decision_only_in_engine | None | None | chained_after_first | yalniz motorda karar; genelde onceki islem sapmasi yuzunden pozisyon durumu farkli |
| A | ('DOGE/USDT', 'short', 'T1', '1h', '2025-11-01T22:00:00.000Z') | decision_only_in_engine | None | None | chained_after_first | yalniz motorda karar; genelde onceki islem sapmasi yuzunden pozisyon durumu farkli |
| A | ('ETH/USDT', 'short', 'T1', '1h', '2025-11-01T22:00:00.000Z') | decision_only_in_engine | None | None | chained_after_first | yalniz motorda karar; genelde onceki islem sapmasi yuzunden pozisyon durumu farkli |
| B | ('BTC/USDT', 'short', '2025-11-01T22:00:00.000Z') | size_ratio | 9.150549757877691 | 8.133822007002392 | chained_after_first | planned_risk ref=9.15055 eng=8.13382 (rel 1.11e-01); ozsermaye tahmini ref=996.58030837 motor(karar ani)=987.3762904943684 |
| B | ('ETH/USDT', 'short', '2025-11-01T22:00:00.000Z') | entry_extra_in_engine | None | 3865.81 | chained_after_first | motorda fazla giris |
| A | ('DOGE/USDT', 'short', 'T1', '1h', '2025-11-02T01:00:00.000Z') | decision_only_in_engine | None | None | chained_after_first | yalniz motorda karar; genelde onceki islem sapmasi yuzunden pozisyon durumu farkli |
| A | ('DOGE/USDT', 'short', 'T1', '1h', '2025-11-02T02:00:00.000Z') | decision_only_in_engine | None | None | chained_after_first | yalniz motorda karar; genelde onceki islem sapmasi yuzunden pozisyon durumu farkli |
| B | ('ADA/USDT', 'short', '2025-11-02T09:00:00.000Z') | qty | 1568.4 | 1564.9 | chained_after_first | karar boyutu ref=1568.4 motor=1564.9: ozsermaye/risk durumu farki |
| B | ('TRX/USDT', 'short', '2025-11-02T10:00:00.000Z') | entry_missing_in_engine | 0.29592 | None | margin_accounting | motor karari var ama giris dolumunda `order_failed` (PaperBroker: margin+fee > cuzdan-kullanilan marjin = `insufficient_margin`); freqtrade serbest bakiyeden ac |
| A | ('DOGE/USDT', 'short', 'T1', '1h', '2025-11-02T13:00:00.000Z') | decision_only_in_engine | None | None | chained_after_first | yalniz motorda karar; genelde onceki islem sapmasi yuzunden pozisyon durumu farkli |
| A | ('TRX/USDT', 'short', 'T1', '1h', '2025-11-02T20:00:00.000Z') | decision_only_in_engine | None | None | chained_after_first | yalniz motorda karar; genelde onceki islem sapmasi yuzunden pozisyon durumu farkli |
| B | ('XRP/USDT', 'short', '2025-11-02T23:00:00.000Z') | entry_missing_in_engine | 2.4975 | None | margin_accounting | motor karari var ama giris dolumunda `order_failed` (PaperBroker: margin+fee > cuzdan-kullanilan marjin = `insufficient_margin`); freqtrade serbest bakiyeden ac |
| B | ('XRP/USDT', 'short', '2025-11-03T01:00:00.000Z') | size_ratio | 13.315244872964774 | 13.552200526339423 | chained_after_first | planned_risk ref=13.3152 eng=13.5522 (rel 1.78e-02); ozsermaye tahmini ref=951.1053313 motor(karar ani)=968.0465762233201 |
| B | ('XRP/USDT', 'short', '2025-11-03T01:00:00.000Z') | qty | 320.3 | 326.0 | chained_after_first | karar boyutu ref=320.3 motor=326.0: ozsermaye/risk durumu farki |
| B | ('ADA/USDT', 'short', '2025-11-03T01:00:00.000Z') | size_ratio | 13.30347490244943 | 13.552305805946842 | chained_after_first | planned_risk ref=13.3035 eng=13.5523 (rel 1.87e-02); ozsermaye tahmini ref=951.1053313 motor(karar ani)=968.0465762233201 |
| B | ('ADA/USDT', 'short', '2025-11-03T01:00:00.000Z') | qty | 1037.2 | 1056.6 | chained_after_first | karar boyutu ref=1037.2 motor=1056.6: ozsermaye/risk durumu farki |
| C | ('ADA/USDT', 'short', '2025-11-03T01:00:00.000Z') | exit_ts | 2025-11-03T16:00:00.000Z trail_stop 0.557 | 2025-11-03T17:00:00.000Z trail_stop 0.5594 | trail_timing | iz stop bir bar sonra: ref 2025-11-03T16:00:00.000Z eng 2025-11-03T17:00:00.000Z |
| B | ('LINK/USDT', 'long', '2025-11-03T05:00:00.000Z') | size_ratio | 13.908097000904583 | 14.166267292687198 | chained_after_first | planned_risk ref=13.9081 eng=14.1663 (rel 1.86e-02); ozsermaye tahmini ref=995.0361912999999 motor(karar ani)=1012.0570035633201 |
| B | ('LINK/USDT', 'long', '2025-11-03T05:00:00.000Z') | qty | 42.02 | 42.79 | chained_after_first | karar boyutu ref=42.02 motor=42.8: ozsermaye/risk durumu farki |
| B | ('TRX/USDT', 'short', '2025-11-05T11:00:00.000Z') | size_ratio | 10.681816753641382 | 10.845881139209567 | chained_after_first | planned_risk ref=10.6818 eng=10.8459 (rel 1.54e-02); ozsermaye tahmini ref=1020.00965041 motor(karar ani)=1035.6750770619976 |
| B | ('TRX/USDT', 'short', '2025-11-05T11:00:00.000Z') | qty | 3574.4 | 3629.3 | chained_after_first | karar boyutu ref=3574.4 motor=3629.3: ozsermaye/risk durumu farki |
| B | ('ADA/USDT', 'short', '2025-11-05T20:00:00.000Z') | size_ratio | 14.144272841707231 | 14.362189287572974 | chained_after_first | planned_risk ref=14.1443 eng=14.3622 (rel 1.54e-02); ozsermaye tahmini ref=1010.37104847 motor(karar ani)=1025.8884337074976 |
| B | ('ADA/USDT', 'short', '2025-11-05T20:00:00.000Z') | qty | 1324.1 | 1344.5 | chained_after_first | karar boyutu ref=1324.1 motor=1344.5: ozsermaye/risk durumu farki |
| B | ('ETH/USDT', 'short', '2025-11-05T23:00:00.000Z') | size_ratio | 14.004375526442711 | 14.237781785216757 | chained_after_first | planned_risk ref=14.0044 eng=14.2378 (rel 1.67e-02); ozsermaye tahmini ref=1004.8098284700001 motor(karar ani)=1019.8763675074977 |
| B | ('ETH/USDT', 'short', '2025-11-05T23:00:00.000Z') | qty | 0.18 | 0.182 | chained_after_first | karar boyutu ref=0.18 motor=0.183: ozsermaye/risk durumu farki |
| B | ('TRX/USDT', 'short', '2025-11-06T12:00:00.000Z') | size_ratio | 5.966348869716627 | 6.061691565468564 | chained_after_first | planned_risk ref=5.96635 eng=6.06169 (rel 1.60e-02); ozsermaye tahmini ref=1025.87907847 motor(karar ani)=1041.077880907996 |
| B | ('TRX/USDT', 'short', '2025-11-06T12:00:00.000Z') | qty | 3573.2 | 3630.3 | chained_after_first | karar boyutu ref=3573.2 motor=3630.3: ozsermaye/risk durumu farki |
| B | ('BNB/USDT', 'short', '2025-11-07T10:00:00.000Z') | size_ratio | 14.464143099219353 | 14.662282045784 | chained_after_first | planned_risk ref=14.4641 eng=14.6623 (rel 1.37e-02); ozsermaye tahmini ref=1039.0734392699999 motor(karar ani)=1054.7645727296645 |
| B | ('BNB/USDT', 'short', '2025-11-07T10:00:00.000Z') | qty | 0.73 | 0.74 | chained_after_first | karar boyutu ref=0.73 motor=0.74: ozsermaye/risk durumu farki |
| B | ('TRX/USDT', 'short', '2025-11-07T11:00:00.000Z') | size_ratio | 11.17743909061296 | 11.354936080502844 | chained_after_first | planned_risk ref=11.1774 eng=11.3549 (rel 1.59e-02); ozsermaye tahmini ref=1047.69373927 motor(karar ani)=1063.1389999296646 |
| B | ('TRX/USDT', 'short', '2025-11-07T11:00:00.000Z') | qty | 3671.3 | 3729.6 | chained_after_first | karar boyutu ref=3671.3 motor=3729.6: ozsermaye/risk durumu farki |
| B | ('SOL/USDT', 'short', '2025-11-08T12:00:00.000Z') | size_ratio | 14.319270122122635 | 14.515424507357194 | chained_after_first | planned_risk ref=14.3193 eng=14.5154 (rel 1.37e-02); ozsermaye tahmini ref=1023.91677886 motor(karar ani)=1039.5744552092908 |
| B | ('SOL/USDT', 'short', '2025-11-08T12:00:00.000Z') | qty | 3.65 | 3.7 | chained_after_first | karar boyutu ref=3.65 motor=3.7: ozsermaye/risk durumu farki |
| B | ('ETH/USDT', 'short', '2025-11-09T01:00:00.000Z') | size_ratio | 14.325429696311307 | 14.561045316316429 | chained_after_first | planned_risk ref=14.3254 eng=14.561 (rel 1.64e-02); ozsermaye tahmini ref=1033.2242788600001 motor(karar ani)=1048.6620351271408 |
| B | ('ETH/USDT', 'short', '2025-11-09T01:00:00.000Z') | qty | 0.304 | 0.309 | chained_after_first | karar boyutu ref=0.304 motor=0.309: ozsermaye/risk durumu farki |
| B | ('ADA/USDT', 'short', '2025-11-09T09:00:00.000Z') | size_ratio | 14.084072498115557 | 14.306116912744537 | chained_after_first | planned_risk ref=14.0841 eng=14.3061 (rel 1.58e-02); ozsermaye tahmini ref=1006.9197197599999 motor(karar ani)=1023.3652781592983 |
| B | ('ADA/USDT', 'short', '2025-11-09T09:00:00.000Z') | qty | 1788.7 | 1816.9 | exit_before_entry | karar boyutu ref=1788.7 motor=1816.9: ozsermaye/risk durumu farki; ayni adimda cikan referans islem(ler) [('SOL/USDT', 'short', '2025-11-08T12:00:00.000Z')]: re |
| A | ('XRP/USDT', 'short', 'T1', '1h', '2025-11-09T10:00:00.000Z') | decision_only_in_engine | None | None | chained_after_first | yalniz motorda karar; genelde onceki islem sapmasi yuzunden pozisyon durumu farkli |
| B | ('SOL/USDT', 'short', '2025-11-09T10:00:00.000Z') | size_ratio | 14.240832895160024 | 14.483850521357292 | chained_after_first | planned_risk ref=14.2408 eng=14.4839 (rel 1.71e-02); ozsermaye tahmini ref=1020.31907976 motor(karar ani)=1034.9668795592984 |
| B | ('SOL/USDT', 'short', '2025-11-09T10:00:00.000Z') | qty | 5.86 | 5.96 | chained_after_first | karar boyutu ref=5.86 motor=5.96: ozsermaye/risk durumu farki |
| B | ('BNB/USDT', 'short', '2025-11-10T00:00:00.000Z') | size_ratio | 12.196542295859505 | 12.448017394743205 | chained_after_first | planned_risk ref=12.1965 eng=12.448 (rel 2.06e-02); ozsermaye tahmini ref=973.76524448 motor(karar ani)=988.7449632642985 |
| B | ('BNB/USDT', 'short', '2025-11-10T00:00:00.000Z') | qty | 0.97 | 0.98 | chained_after_first | karar boyutu ref=0.97 motor=0.99: ozsermaye/risk durumu farki |
| B | ('BNB/USDT', 'short', '2025-11-11T00:00:00.000Z') | size_ratio | 8.616717789198761 | 8.70554993135545 | chained_after_first | planned_risk ref=8.61672 eng=8.70555 (rel 1.03e-02); ozsermaye tahmini ref=962.54099133 motor(karar ani)=977.4049961642986 |
| B | ('BNB/USDT', 'short', '2025-11-11T00:00:00.000Z') | qty | 0.97 | 0.98 | chained_after_first | karar boyutu ref=0.97 motor=0.98: ozsermaye/risk durumu farki |
| D | ('BNB/USDT', 'short', '2025-11-11T00:00:00.000Z') | funding_paid | 0.147653095032 | 0.0 | funding_boundary | sinir noktalari (giris/cikis anindaki 00/08/16): referans giris x1, cikis x1; motor giris x0, cikis x1 (veriden yeniden hesapla birebir uyumlu; 03 §5 `opened_ts |
| B | ('AVAX/USDT', 'short', '2025-11-11T04:00:00.000Z') | size_ratio | 13.363878045118799 | 13.555966641249869 | chained_after_first | planned_risk ref=13.3639 eng=13.556 (rel 1.44e-02); ozsermaye tahmini ref=954.74489308 motor(karar ani)=969.6777010642986 |
| B | ('AVAX/USDT', 'short', '2025-11-11T04:00:00.000Z') | qty | 48.7 | 49.3 | chained_after_first | karar boyutu ref=48.7 motor=49.4: ozsermaye/risk durumu farki |
| C | ('BTC/USDT', 'short', '2025-11-11T13:00:00.000Z') | exit_price | 2025-11-12T08:30:00.000Z trail_stop 104123.5 | 2025-11-12T08:30:00.000Z trail_stop 104141.6 | gap_fill | cikis fiyati ref=104123.5 eng=104141.6 rel=1.74e-04 |
| B | ('XRP/USDT', 'long', '2025-11-11T15:00:00.000Z') | size_ratio | 13.672594811189251 | 13.896807780761808 | chained_after_first | planned_risk ref=13.6726 eng=13.8968 (rel 1.64e-02); ozsermaye tahmini ref=978.6415930799999 motor(karar ani)=992.8911524702656 |
| B | ('XRP/USDT', 'long', '2025-11-11T15:00:00.000Z') | qty | 311.0 | 316.1 | chained_after_first | karar boyutu ref=311.0 motor=316.1: ozsermaye/risk durumu farki |
| B | ('BNB/USDT', 'short', '2025-11-12T15:00:00.000Z') | size_ratio | 13.884356086357993 | 14.227179693428557 | chained_after_first | planned_risk ref=13.8844 eng=14.2272 (rel 2.47e-02); ozsermaye tahmini ref=1001.74068518 motor(karar ani)=1017.0057287053862 |
... 798 fark daha (json'da)
