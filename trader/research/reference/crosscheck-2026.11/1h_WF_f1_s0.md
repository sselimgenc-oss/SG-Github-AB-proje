# Capraz dogrulama: 1h_WF_f1_s0

Sonuc: **RED** (aciklanamayan: 0)

| Duzey | Olcut | Deger | Kabul |
|---|---|---|---|
| A kararlar | ortak anahtarda esit | 571/571 (100.00%); yalniz ref 4, yalniz motor 80 | evet |
| B girisler | eslesen/ref (anahtar+fiyat+boyut) | 27/376 (7.18%); yalniz anahtar 87.23%, anahtar+fiyat 87.23% | hayir |
| C cikislar | eslesen girislerde | 314/328 (95.73%; kesin 95.73%, trail +-1: 0) | hayir |
| D sum_R | ref 23.6566 / motor 36.8618 (fark 13.21, tol 0.4731) | | hayir |
| D fees | ref 393.158 / motor 378.104 (fark -15.05, tol 7.863) | | hayir |
| D funding | ref 9.04324 / motor 9.30402 (fark 0.2608, tol 0.4522) | | evet |
| D n_trades | ref 376 / motor 343 (fark -33, tol 3.76) | | hayir |

Sinif sayilari: aggregate=3, chained_after_first=727, decision_only=1, exit_before_entry=4, funding_boundary=34, gap_fill=10, margin_accounting=23, open_at_end=2, price_rounding=2
unexplained: 0

## Ilk sapma
A ('DOGE/USDT', 'short', 'T1', '1h', '2025-11-01T06:00:00.000Z') decision_only_in_engine: ref=None motor=None sinif=decision_only | yalniz motorda karar; genelde onceki islem sapmasi yuzunden pozisyon durumu farkli

## Farklar

| duzey | anahtar | alan | ref | motor | sinif | kanit |
|---|---|---|---|---|---|---|
| A | ('DOGE/USDT', 'short', 'T1', '1h', '2025-11-01T06:00:00.000Z') | decision_only_in_engine | None | None | decision_only | yalniz motorda karar; genelde onceki islem sapmasi yuzunden pozisyon durumu farkli |
| A | ('LINK/USDT', 'short', 'T1', '1h', '2025-11-01T06:00:00.000Z') | decision_only_in_engine | None | None | chained_after_first | yalniz motorda karar; genelde onceki islem sapmasi yuzunden pozisyon durumu farkli |
| A | ('TRX/USDT', 'short', 'T1', '1h', '2025-11-01T06:00:00.000Z') | decision_only_in_engine | None | None | chained_after_first | yalniz motorda karar; genelde onceki islem sapmasi yuzunden pozisyon durumu farkli |
| B | ('XRP/USDT', 'short', '2025-11-01T06:00:00.000Z') | qty | 392.6 | 398.4 | chained_after_first | karar boyutu ref=397.9 motor=398.5: ozsermaye/risk durumu farki |
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
| B | ('ADA/USDT', 'short', '2025-11-02T09:00:00.000Z') | qty | 1568.4 | 1565.6 | chained_after_first | karar boyutu ref=1568.4 motor=1565.6: ozsermaye/risk durumu farki |
| B | ('TRX/USDT', 'short', '2025-11-02T10:00:00.000Z') | entry_missing_in_engine | 0.29592 | None | margin_accounting | motor karari var ama giris dolumunda `order_failed` (PaperBroker: margin+fee > cuzdan-kullanilan marjin = `insufficient_margin`); freqtrade serbest bakiyeden ac |
| A | ('DOGE/USDT', 'short', 'T1', '1h', '2025-11-02T13:00:00.000Z') | decision_only_in_engine | None | None | chained_after_first | yalniz motorda karar; genelde onceki islem sapmasi yuzunden pozisyon durumu farkli |
| A | ('TRX/USDT', 'short', 'T1', '1h', '2025-11-02T20:00:00.000Z') | decision_only_in_engine | None | None | chained_after_first | yalniz motorda karar; genelde onceki islem sapmasi yuzunden pozisyon durumu farkli |
| B | ('XRP/USDT', 'short', '2025-11-02T23:00:00.000Z') | entry_missing_in_engine | 2.4975 | None | margin_accounting | motor karari var ama giris dolumunda `order_failed` (PaperBroker: margin+fee > cuzdan-kullanilan marjin = `insufficient_margin`); freqtrade serbest bakiyeden ac |
| B | ('XRP/USDT', 'short', '2025-11-03T01:00:00.000Z') | size_ratio | 13.315244872964774 | 13.556357643065292 | chained_after_first | planned_risk ref=13.3152 eng=13.5564 (rel 1.81e-02); ozsermaye tahmini ref=951.1053313 motor(karar ani)=968.4487160864376 |
| B | ('XRP/USDT', 'short', '2025-11-03T01:00:00.000Z') | qty | 320.3 | 326.1 | chained_after_first | karar boyutu ref=320.3 motor=326.1: ozsermaye/risk durumu farki |
| B | ('ADA/USDT', 'short', '2025-11-03T01:00:00.000Z') | size_ratio | 13.30347490244943 | 13.557436340039574 | chained_after_first | planned_risk ref=13.3035 eng=13.5574 (rel 1.91e-02); ozsermaye tahmini ref=951.1053313 motor(karar ani)=968.4487160864376 |
| B | ('ADA/USDT', 'short', '2025-11-03T01:00:00.000Z') | qty | 1037.2 | 1057.0 | chained_after_first | karar boyutu ref=1037.2 motor=1057.0: ozsermaye/risk durumu farki |
| D | ('ADA/USDT', 'short', '2025-11-03T01:00:00.000Z') | funding_paid | -0.05253202765784277 | -0.025910690069938104 | funding_boundary | sinir noktalari (giris/cikis anindaki 00/08/16): referans giris x0, cikis x2; motor giris x0, cikis x1 (veriden yeniden hesapla birebir uyumlu; 03 §5 `opened_ts |
| B | ('LINK/USDT', 'long', '2025-11-03T05:00:00.000Z') | size_ratio | 13.908097000904583 | 14.172887043758548 | chained_after_first | planned_risk ref=13.9081 eng=14.1729 (rel 1.90e-02); ozsermaye tahmini ref=995.0361912999999 motor(karar ani)=1012.4745179464376 |
| B | ('LINK/USDT', 'long', '2025-11-03T05:00:00.000Z') | qty | 42.02 | 42.82 | chained_after_first | karar boyutu ref=42.02 motor=42.82: ozsermaye/risk durumu farki |
| B | ('TRX/USDT', 'short', '2025-11-05T11:00:00.000Z') | size_ratio | 10.681816753641382 | 10.876960731375487 | chained_after_first | planned_risk ref=10.6818 eng=10.877 (rel 1.83e-02); ozsermaye tahmini ref=1020.00965041 motor(karar ani)=1038.6339334610288 |
| B | ('TRX/USDT', 'short', '2025-11-05T11:00:00.000Z') | qty | 3574.4 | 3639.7 | chained_after_first | karar boyutu ref=3574.4 motor=3639.7: ozsermaye/risk durumu farki |
| B | ('ADA/USDT', 'short', '2025-11-05T20:00:00.000Z') | size_ratio | 14.144272841707231 | 14.402781566704828 | chained_after_first | planned_risk ref=14.1443 eng=14.4028 (rel 1.83e-02); ozsermaye tahmini ref=1010.37104847 motor(karar ani)=1028.8192458305286 |
| B | ('ADA/USDT', 'short', '2025-11-05T20:00:00.000Z') | qty | 1324.1 | 1348.3 | chained_after_first | karar boyutu ref=1324.1 motor=1348.3: ozsermaye/risk durumu farki |
| B | ('ETH/USDT', 'short', '2025-11-05T23:00:00.000Z') | size_ratio | 14.004375526442711 | 14.315583871474772 | chained_after_first | planned_risk ref=14.0044 eng=14.3156 (rel 2.22e-02); ozsermaye tahmini ref=1004.8098284700001 motor(karar ani)=1022.7901875505287 |
| B | ('ETH/USDT', 'short', '2025-11-05T23:00:00.000Z') | qty | 0.18 | 0.184 | chained_after_first | karar boyutu ref=0.18 motor=0.184: ozsermaye/risk durumu farki |
| B | ('TRX/USDT', 'short', '2025-11-06T12:00:00.000Z') | size_ratio | 5.966348869716627 | 6.079223935090199 | chained_after_first | planned_risk ref=5.96635 eng=6.07922 (rel 1.89e-02); ozsermaye tahmini ref=1025.87907847 motor(karar ani)=1044.0868700506403 |
| B | ('TRX/USDT', 'short', '2025-11-06T12:00:00.000Z') | qty | 3573.2 | 3640.8 | chained_after_first | karar boyutu ref=3573.2 motor=3640.8: ozsermaye/risk durumu farki |
| B | ('BNB/USDT', 'short', '2025-11-07T10:00:00.000Z') | size_ratio | 14.464143099219353 | 14.662282045784 | chained_after_first | planned_risk ref=14.4641 eng=14.6623 (rel 1.37e-02); ozsermaye tahmini ref=1039.0734392699999 motor(karar ani)=1057.9586452417 |
| B | ('BNB/USDT', 'short', '2025-11-07T10:00:00.000Z') | qty | 0.73 | 0.74 | chained_after_first | karar boyutu ref=0.73 motor=0.74: ozsermaye/risk durumu farki |
| B | ('TRX/USDT', 'short', '2025-11-07T11:00:00.000Z') | size_ratio | 11.17743909061296 | 11.389643896707726 | chained_after_first | planned_risk ref=11.1774 eng=11.3896 (rel 1.90e-02); ozsermaye tahmini ref=1047.69373927 motor(karar ani)=1066.3747524417001 |
| B | ('TRX/USDT', 'short', '2025-11-07T11:00:00.000Z') | qty | 3671.3 | 3741.0 | chained_after_first | karar boyutu ref=3671.3 motor=3741.0: ozsermaye/risk durumu farki |
| B | ('SOL/USDT', 'short', '2025-11-08T12:00:00.000Z') | size_ratio | 14.319270122122635 | 14.593886261451015 | chained_after_first | planned_risk ref=14.3193 eng=14.5939 (rel 1.92e-02); ozsermaye tahmini ref=1023.91677886 motor(karar ani)=1042.687340459663 |
| B | ('SOL/USDT', 'short', '2025-11-08T12:00:00.000Z') | qty | 3.65 | 3.72 | chained_after_first | karar boyutu ref=3.65 motor=3.72: ozsermaye/risk durumu farki |
| C | ('SOL/USDT', 'short', '2025-11-08T12:00:00.000Z') | exit_price | 2025-11-09T09:00:00.000Z trail_stop 159.673 | 2025-11-09T09:00:00.000Z trail_stop 159.58 | gap_fill | cikis fiyati ref=159.673 eng=159.58 rel=5.82e-04 |
| B | ('ETH/USDT', 'short', '2025-11-09T01:00:00.000Z') | size_ratio | 14.325429696311307 | 14.608168440317453 | chained_after_first | planned_risk ref=14.3254 eng=14.6082 (rel 1.97e-02); ozsermaye tahmini ref=1033.2242788600001 motor(karar ani)=1051.824042431123 |
| B | ('ETH/USDT', 'short', '2025-11-09T01:00:00.000Z') | qty | 0.304 | 0.309 | chained_after_first | karar boyutu ref=0.304 motor=0.31: ozsermaye/risk durumu farki |
| B | ('ADA/USDT', 'short', '2025-11-09T09:00:00.000Z') | size_ratio | 14.084072498115557 | 14.354935188301262 | chained_after_first | planned_risk ref=14.0841 eng=14.3549 (rel 1.92e-02); ozsermaye tahmini ref=1006.9197197599999 motor(karar ani)=1026.4749924321368 |
| B | ('ADA/USDT', 'short', '2025-11-09T09:00:00.000Z') | qty | 1788.7 | 1823.1 | exit_before_entry | karar boyutu ref=1788.7 motor=1823.1: ozsermaye/risk durumu farki; ayni adimda cikan referans islem(ler) [('SOL/USDT', 'short', '2025-11-08T12:00:00.000Z')]: re |
| A | ('XRP/USDT', 'short', 'T1', '1h', '2025-11-09T10:00:00.000Z') | decision_only_in_engine | None | None | chained_after_first | yalniz motorda karar; genelde onceki islem sapmasi yuzunden pozisyon durumu farkli |
| B | ('SOL/USDT', 'short', '2025-11-09T10:00:00.000Z') | size_ratio | 14.240832895160024 | 14.532454046596747 | chained_after_first | planned_risk ref=14.2408 eng=14.5325 (rel 2.05e-02); ozsermaye tahmini ref=1020.31907976 motor(karar ani)=1038.449097182137 |
| B | ('SOL/USDT', 'short', '2025-11-09T10:00:00.000Z') | qty | 5.86 | 5.98 | chained_after_first | karar boyutu ref=5.86 motor=5.98: ozsermaye/risk durumu farki |
| B | ('BNB/USDT', 'short', '2025-11-10T00:00:00.000Z') | size_ratio | 12.196542295859505 | 12.448017394743205 | chained_after_first | planned_risk ref=12.1965 eng=12.448 (rel 2.06e-02); ozsermaye tahmini ref=973.76524448 motor(karar ani)=992.1025227071369 |
| B | ('BNB/USDT', 'short', '2025-11-10T00:00:00.000Z') | qty | 0.97 | 0.98 | chained_after_first | karar boyutu ref=0.97 motor=0.99: ozsermaye/risk durumu farki |
| B | ('BNB/USDT', 'short', '2025-11-11T00:00:00.000Z') | size_ratio | 8.616717789198761 | 8.70554993135545 | chained_after_first | planned_risk ref=8.61672 eng=8.70555 (rel 1.03e-02); ozsermaye tahmini ref=962.54099133 motor(karar ani)=980.7625556071371 |
| B | ('BNB/USDT', 'short', '2025-11-11T00:00:00.000Z') | qty | 0.97 | 0.98 | chained_after_first | karar boyutu ref=0.97 motor=0.98: ozsermaye/risk durumu farki |
| D | ('BNB/USDT', 'short', '2025-11-11T00:00:00.000Z') | funding_paid | 0.147653095032 | 0.0 | funding_boundary | sinir noktalari (giris/cikis anindaki 00/08/16): referans giris x1, cikis x1; motor giris x0, cikis x1 (veriden yeniden hesapla birebir uyumlu; 03 §5 `opened_ts |
| B | ('AVAX/USDT', 'short', '2025-11-11T04:00:00.000Z') | size_ratio | 13.363878045118799 | 13.610849097287318 | chained_after_first | planned_risk ref=13.3639 eng=13.6108 (rel 1.85e-02); ozsermaye tahmini ref=954.74489308 motor(karar ani)=973.0352605071371 |
| B | ('AVAX/USDT', 'short', '2025-11-11T04:00:00.000Z') | qty | 48.7 | 49.5 | chained_after_first | karar boyutu ref=48.7 motor=49.6: ozsermaye/risk durumu farki |
| B | ('XRP/USDT', 'long', '2025-11-11T15:00:00.000Z') | size_ratio | 13.672594811189251 | 13.945167440865692 | chained_after_first | planned_risk ref=13.6726 eng=13.9452 (rel 1.99e-02); ozsermaye tahmini ref=978.6415930799999 motor(karar ani)=996.345445385542 |
| B | ('XRP/USDT', 'long', '2025-11-11T15:00:00.000Z') | qty | 311.0 | 317.2 | chained_after_first | karar boyutu ref=311.0 motor=317.2: ozsermaye/risk durumu farki |
| B | ('BNB/USDT', 'short', '2025-11-12T15:00:00.000Z') | size_ratio | 13.884356086357993 | 14.227179693428557 | chained_after_first | planned_risk ref=13.8844 eng=14.2272 (rel 2.47e-02); ozsermaye tahmini ref=1001.74068518 motor(karar ani)=1020.7162189825582 |
| B | ('BNB/USDT', 'short', '2025-11-12T15:00:00.000Z') | qty | 0.81 | 0.83 | chained_after_first | karar boyutu ref=0.81 motor=0.83: ozsermaye/risk durumu farki |
... 746 fark daha (json'da)
