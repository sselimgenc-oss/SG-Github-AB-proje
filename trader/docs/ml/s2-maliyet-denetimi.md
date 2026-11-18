# S2 adım 0: maliyet dökümü denetimi

Tarih: 2026-11-18. Kapsam: salt okuma, analiz. Strateji, motor ve dondurulmuş dosyalara dokunulmadı. Veri: `var/backtests/corpus_v2_taken_v1b_native/` (v1b, 2021-01 → 2026-04, 10 çift, native dolum, 1h tetik). Okunan en geç işlem çıkışı 2026-04-30; kilitli dönem (2026-05-01 → 2026-11-01) okunmadı. Defter ve `trades.csv` aynı toplamları veriyor (4695 çıkışlı işlem; `trades.csv`'de çıkışsız 3 ek satır var, tüm rakamlar 4695 üzerinden).

## 1. Sonuç (özet)

1. **Gözlenen "kayma ≈ komisyonun 3 katı" oranı bir raporlama (etiket) hatasıdır, motor hatası değil.** `metrics.py:107` native kipte de `fee_only = fee_paid − slip_paid` hesaplıyor. Native'de `fee_paid` zaten saf taker komisyonudur (kayma içermez); çıkarma yanlış. Gerçek komisyon **780,1** (kayma düşülmüş 186,8 değil). Gerçek kayma/komisyon oranı **0,76** (kayma 593,3), yani 3 değil.
2. **Kayma, `costs_total`'a dahil değildir.** `costs_total` 872,9 = komisyon 780,1 + fonlama 92,8. Kayma dolum fiyatlarına zaten işlenmiştir ve **brüt PnL (+269,2) kaymadan sonraki** rakamdır. r02 §6'daki "komisyon 186,8 + kayma 593,3 + fonlama 92,8 = 872,9" ayrıştırması toplamı tutturur ama bileşenleri yanlış etiketler (aşağıda §2, §5).
3. **Kayma modeli kendi tasarım değerlerini üretiyor:** giriş ort. 2,4 bp (model 2), çıkış ort. 5,2 bp (model 5; tüm çıkışlar stop emri olduğu için hepsi 5 bp). Aşırı değer yok; 18 çıkışta > 10 bp.
4. **Gerçek tablo:** kayma öncesi brüt (planlı seviyelerde fiyat PnL'i) **+862,4 USD = +0,095 R / işlem**; komisyon 780,1 + kayma 593,3 + fonlama 92,8 = **1466,2 USD = 0,121 R / işlem**. Net = 862,4 − 1466,2 = −603,8 (rapor edilenle aynı). Başa baş için toplam tur maliyeti 11,05 bp olmalı; bugün 18,8 bp.
5. Memo'nun ana çıkarımı geçerli, hatta güçlenir: **komisyon tek başına (10,0 bp tur) başa baş eşiğinin (11,05 bp) neredeyse tamamı**; kayma sıfır olsa net ≈ −10,5 USD ≈ 0. Brüt kazancın artması gerekiyor; maliyet düşürmek tek başına yetmez.

## 2. Soru 1: toplam maliyetin dökümü

Kaynak: `trades.csv` (4695 işlem). Kayma bileşenleri `metrics.py:70` formülüyle (`qty·planned_entry·slippage_entry + qty·planned_exit·slippage_exit`; `planned_exit` boşsa çıkış fiyatı) yeniden hesaplandı ve `slip_cost` sütunuyla birebir eşleşti (fark 0). Ayrıca doğrudan fiyat farkından (`qty·|dolum − plan|`, aleyhte yönde) hesap aynı sonucu verdi.

| Bileşen | USD | Tur başına bp (giriş notional'ı üzerinden) | Not |
|---|---:|---:|---|
| Komisyon, giriş | 390,26 | 5,00 | taker 5 bp, dolum notional'ı üzerinden |
| Komisyon, çıkış | 390,00 | 5,00 | aynı |
| **Komisyon toplam** | **780,09** | **10,00** | `summary.fees_total` ile aynı |
| Kayma, giriş (piyasa emri) | 186,97 | 2,39 | model 2 bp |
| Kayma, çıkış: stop | 210,78 | (2454 işlem) | çıkış notional'ı üzerinden 5,05 bp |
| Kayma, çıkış: trail_stop | 195,65 | (2235 işlem) | çıkış notional'ı üzerinden 5,40 bp |
| Kayma, çıkış: hedef | 0 | | strateji hedef emri kullanmıyor (n = 0) |
| Kayma, çıkış: diğer (`regime_flip` 5, `other` 1) | 0 | | defterde `slippage_exit` boş, `planned_exit` boş: kayma 0 yazılıyor, bkz. not |
| **Kayma toplam** | **593,26** | **7,60** (giriş 2,39 + çıkış 5,21) | `summary.slip_approx` ile aynı (csv'deki 593,39, çıkışsız 3 satırdan) |
| Fonlama (ödenen, net) | 92,84 | 1,19 | uzun +111,4, kısa −18,6 |
| **Komisyon + fonlama (= `costs_total`)** | **872,93** | **11,19** | kayma DAHİL DEĞİL |
| Kayma dahil tüm maliyet | 1466,19 | 18,79 | |
| Brüt PnL (`gross_pnl`, kayma sonrası) | +269,17 | 3,45 | dolum fiyatlarından |
| Kayma öncesi brüt (planlı seviyelerde) | +862,43 | 11,05 | = 269,17 + 593,26 |
| Net PnL | −603,76 | | 862,43 − 1466,19; `realized_pnl` toplamı ile birebir |

Toplam kontrolü: `realized = gross − fee_entry − fee_exit − funding` en fazla 7e-15 farkla tüm satırlarda tutuyor. Kayma, `gross_pnl = qty·(çıkış_dolumu − giriş_dolumu)` içinde olduğu için ayrıca düşülmez.

Not: `regime_flip` / `other` 6 çıkışta `planned_exit` yok ve `slippage_exit` boş (`slip_cost` bu satırlarda yalnız giriş kaymasını sayıyor); 6 işlemin (≈ 4 USD) kayması çıkışta eksik sayılmış, önemsiz.

Çıkış türüne göre:

| Çıkış | n | Giriş kayması USD | Çıkış kayması USD | Çıkış kayması bp (çıkış notional'ı) | Komisyon USD | Ort. net R |
|---|---:|---:|---:|---:|---:|---:|
| stop | 2454 | 99,40 | 210,78 | 5,05 | 416,86 | −0,984 |
| trail_stop | 2235 | 87,22 | 195,65 | 5,40 | 362,32 | +1,027 |
| regime_flip | 5 | 0,15 | 0 | | 0,59 | −0,301 |
| other | 1 | 0,06 | 0 | | 0,31 | −1,227 |

## 3. Soru 2: native dolum modeli kaymayı nasıl hesaplıyor

Konfigürasyon (koşunun `meta.json` → `cost`): `taker_fee 0,0005`, `slip_entry_bps 2`, `slip_exit_bps 2`, `slip_stop_bps 5`, `trigger_source mark`, `granularity 1m` (varsayılanlar `backtest.py:134`, `config.py:28-30`).

- **Birim: fiyatın bp'si, sabit.** `paper.py:438-449` `_slipped`: `d = slip_bps/10000`; alışta `base·(1+d)`, satışta `base·(1−d)`, ardından `round_adverse` ile tick'e aleyhte yuvarlama (`numeric.py:49`). ATR, mum aralığı, hacim, spread, emir büyüklüğü hiçbir şekilde girdi değil. Tick (TRX 1e-5 gibi) ek bir kuruş-altı aleyhte sıçrama ekler; bu yüzden TRX/DOGE/ADA/SOL kayması BTC'den ~1 bp yüksek (§4).
- **Giriş (piyasa emri):** `paper.py:462` `_fill_entry`: baz = giriş 1m mumunun açılışı (`bar.last_o`), yön aleyhte 2 bp. Ledger'daki `slippage_entry` bu dolumun **planlanan girişe** (`planned_entry` = 1h sinyal mumunun kapanışı) göre sapmasıdır; yani 2 bp'ye bir de "kapanıştan sonraki açılışa" kayması eklenir. Ortalama 2,41 bp, medyan 2,15, P99 6,3 bp, %0,8'i lehte.
- **Çıkış, piyasa emri:** `paper.py:490` `_fill_exit` 1m açılış ± 2 bp. v1b'de piyasa çıkışı yok denecek kadar az (6 işlem).
- **Stop çıkışı:** `paper.py:545-553`. Tetik: mark fiyatı low/high'ı stop'u geçince. Baz = boşluk yoksa stop fiyatı, boşluk varsa (mum açılışı stop'u aşmışsa) `bar.last_o`; sonra **5 bp** aleyhte kayma + tick yuvarlama (`paper.py:552`). Mum ucuna (extreme) kadar değil: **kayma sabit 5 bp'dir, mum aralığıyla sınırlanmaz** ve ona bağlı da değildir (dolum, mumun low/high'ının ötesine bile düşebilir; muhafazakâr yön).
- **Hedef çıkışı:** `paper.py:557-564`, 2 bp; v1b hedef emri kullanmıyor.
- **Trail stop de stop emridir.** `trail_stop` çıkışı güncellenen stop emrinin tetiklenmesidir (`paper.py` aynı `stop` kolu), bu yüzden ledger'da `exit_reason='trail_stop'` olsa da kayma 5 bp'dir. Bu strateji için **her çıkış 5 bp'dir**; "çıkış 2 bp" kolu fiilen hiç kullanılmıyor.
- **Tek taraf başına bir kez uygulanır** (girişte bir, çıkışta bir). İki kez uygulanma yok: giriş 2,39 bp + çıkış 5,21 bp = 7,60 bp tur, model değerleriyle (2 + 5 = 7) uyumlu.
- **Komisyon kayma üstüne biner:** komisyon, kaymalı dolum fiyatı × qty × 5 bp (`paper.py:466`, `491`, `553`); kayma komisyonun içine katılmaz. Bu iki kalemi birbirine karıştırmak §5'teki hatanın kaynağıdır.

## 4. Soru 3: R cinsinden ve bp cinsinden maliyet

R paydası: `summary.json`'ın kullandığı `loss_at_stop` (`metrics.py:37`, `risk.py:177`) = `qty·|giriş−stop| + qty·giriş·(fee+slip_oranı) + qty·stop·(fee+slip_oranı)`; yani saf stop mesafesinin medyan ~1,13 katı. Bu payda ile ortalama net R = −0,02558 (summary ile birebir). Hedef işlem riski 0,005·özsermaye, planlanan risk ≈ 5 USD'lik başlangıç riskine karşılık gelir.

Tüm işlemler (n = 4695), R / işlem:

| Kalem | Ortalama R | Medyan R |
|---|---:|---:|
| Kayma öncesi brüt (planlı seviyelerde) | +0,0952 | −0,7122 |
| Brüt (kayma sonrası, `gross_pnl`) | +0,0455 | −0,8036 |
| Komisyon | 0,0656 | 0,0575 |
| Kayma | 0,0497 | 0,0434 |
| Fonlama | 0,0055 | 0,0000 |
| **Toplam maliyet** | **0,1208** | **0,1059** |
| Net | −0,0256 | −0,9267 |

Kayma öncesi brüt ortalama R için standart hata 0,024 (gün bloklu bootstrap %90 aralığı +0,039 … +0,153). Net R'nin aynı yöntemle %90 aralığı −0,080 … +0,034.

bp cinsinden (tur toplamı / giriş notional'ı): işlem başına dağılım: komisyon medyan 10,00 (ortalama 10,00); kayma medyan 7,25 (ort. 7,63; %5-%95: 5,8-10,5); fonlama medyan 0, ort. 1,37 (şiddetli kuyruk: −61 … +149 bp); toplam medyan **17,5**, ort. 19,0, %5-%95: 13,5-27,2. Notional ağırlıklı toplam 18,79 bp.

Çifte göre:

| Çift | n | Komisyon bp | Kayma bp (giriş+çıkış) | Fonlama bp | Toplam bp (medyan / ort.) | Maliyet R (ort. / medyan) | Kayma öncesi brüt R | Net R | Medyan stop mesafesi bp |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| ADA | 502 | 10,00 | 7,89 (2,54+5,35) | 1,02 | 18,3 / 19,2 | 0,103 / 0,093 | +0,073 | −0,030 | 179 |
| AVAX | 471 | 9,98 | 7,15 (2,11+5,04) | 1,98 | 17,7 / 19,6 | 0,091 / 0,083 | +0,181 | +0,090 | 205 |
| BNB | 522 | 10,00 | 7,15 (2,13+5,03) | 0,77 | 17,2 / 17,8 | 0,136 / 0,127 | +0,128 | −0,008 | 122 |
| BTC | 356 | 9,99 | 7,00 (1,99+5,01) | 0,69 | 17,0 / 18,0 | **0,165** / 0,160 | +0,095 | −0,070 | 95 |
| DOGE | 476 | 9,99 | 7,88 (2,51+5,38) | 1,11 | 17,6 / 19,2 | 0,104 / 0,093 | +0,105 | +0,001 | 177 |
| ETH | 441 | 10,00 | 7,09 (2,01+5,08) | 1,37 | 17,1 / 18,2 | 0,126 / 0,116 | +0,109 | −0,017 | 136 |
| LINK | 485 | 10,00 | 7,56 (2,36+5,20) | 1,02 | 17,5 / 18,6 | 0,095 / 0,089 | +0,022 | −0,073 | 186 |
| SOL | 462 | 10,00 | 8,49 (3,04+5,45) | 1,59 | 18,4 / 20,2 | 0,094 / 0,086 | +0,028 | −0,066 | 204 |
| TRX | 487 | 10,01 | 8,06 (2,71+5,35) | 1,60 | 18,3 / 19,9 | **0,183** / 0,178 | +0,048 | **−0,135** | 88 |
| XRP | 493 | 10,00 | 7,83 (2,59+5,24) | 0,99 | 17,9 / 19,0 | 0,121 / 0,112 | +0,161 | +0,040 | 148 |

Yıla göre (çıkış yılı):

| Yıl | n | Komisyon bp | Kayma bp | Fonlama bp | Toplam bp (medyan / ort.) | Maliyet R | Kayma öncesi brüt R | Net R | Medyan stop mesafesi bp |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| 2021 | 804 | 10,00 | 7,49 | **3,56** | 17,8 / 22,2 | 0,088 | +0,133 | +0,045 | 243 |
| 2022 | 876 | 10,00 | 7,74 | 0,47 | 17,7 / 18,5 | 0,107 | **−0,072** | **−0,178** | 169 |
| 2023 | 952 | 10,00 | 7,79 | 0,38 | 17,9 / 18,7 | **0,149** | +0,060 | −0,089 | 110 |
| 2024 | 895 | 10,01 | 7,56 | 0,55 | 17,4 / 18,5 | 0,123 | +0,109 | −0,014 | 147 |
| 2025 | 871 | 9,99 | 7,33 | 0,39 | 17,3 / 17,7 | 0,122 | +0,213 | +0,091 | 153 |
| 2026 (-04) | 297 | 10,00 | 7,44 | 0,59 | 17,6 / 18,2 | 0,148 | +0,209 | +0,061 | 115 |

Aykırılar ve okuma:

- **Bp cinsinden maliyet çiftler/yıllar arasında neredeyse sabit** (toplam 17-20 bp); komisyon bire bir 10,0 bp, kayma 7,0-8,5 bp. Maliyetin R cinsinden değişimini belirleyen şey **stop mesafesidir**: dar stoplu çiftler (TRX 88 bp, BTC 95 bp, BNB 122 bp) 0,14-0,18 R öderken geniş stoplu çiftler (AVAX, SOL, LINK) 0,09-0,095 R öder. Yıllarda da aynı: 2023 stopları dar (110 bp) → 0,149 R.
- **TRX** hem en yüksek maliyet R'ye (0,183; stop 88 bp) hem en kötü net R'ye (−0,135) sahip; kayma öncesi brüt +0,048 maliyeti karşılamıyor. **BTC** maliyeti yüksek (0,165) ama bunun nedeni dar stop. SOL, DOGE, TRX, ADA'da kayma 7,9-8,5 bp ile diğerlerinden ~1 bp yüksek: tick yuvarlaması + model girişi (ortalama giriş kayması 2,5-3,0 bp).
- **2021'de fonlama** (3,56 bp, 65,7 USD ≈ toplamın %71'i) aykırıdır; diğer yıllarda 0,4-0,6 bp. Fonlamanın uzun taraf yükü (111,4 USD) kısa tarafta kısmen karşılanıyor (−18,6).
- **2022** kayma öncesi bile negatif (−0,072 R): maliyeti sıfırlasanız bile o yılı kurtaramazsınız; kayıp o yıl strateji sinyalinden geliyor.
- Kuyruk kayma: en kötü 8 işlemde tur kayma 19-60 bp (DOGE 2024-01-15: çıkış 58 bp; ETH 2025-07-12: 55 bp), hepsi boşluklu stop dolumları ve trail stop; 18 çıkış > 10 bp. Toplam etkisi küçük (toplam kaymanın birkaç %'si).

## 5. Soru 4: 3:1 oranı, bir model artefaktı mı?

**Hüküm: Hayır, motorda hata yok; oran bir raporlama etiketi hatasından doğuyor ve gerçek oran 0,76.** Kayma modeli kendi değerlerini üretiyor, fakat "komisyon 187" rakamı komisyon değil.

Kanıt zinciri:

1. **Saf komisyon doğrudan ölçülür:** `fee_entry + fee_exit` toplamı 780,09; giriş notional'ına oranı 10,00 bp (= 2 × 5 bp taker). Bu `summary.fees_total` ile aynı. Komisyon 187 olsaydı oran 2,4 bp olurdu; 5 bp taker ile imkansız.
2. **`fee_only` = 186,83 türetilmiş bir sayıdır:** `metrics.py:107`: `t["fee_only"] = t["fee_paid"] - t["slip_paid"]`, 780,09 − 593,26 = 186,83. Bu formül `legacy_compat` kipinde doğrudur (orada kayma komisyon oranına katılmıştır, `backtest.py:100`, `docs/motor/06-backtester.md:84`). Native kipte `fee_paid` saf komisyondur (`paper.py:466,491,553`: kayma ayrı fiyat düzeltmesidir), dolayısıyla çıkarma kayma kadar komisyon siler. Aynı satırın `docs/motor/06-backtester.md:84` açıklaması "native'de slip_paid gerçek dolum−ham fiyat farkından" diyor ama `fee_only` için native ayrımını yapmıyor.
3. **`costs_total` zaten kaymasızdır:** `metrics.py:120`: `costs = fee_paid.sum() − funding.sum()` = 780,09 + 92,84 = 872,93. r02 §6'nın satırı `komisyon 186,8 + kayma ≈ 593,3 + fonlama 92,8 = 872,9` toplamı tesadüfen tutturur çünkü `186,8 = 780,1 − 593,3`; yani kayma bir kez toplamdan çıkarılıp bir kez geri ekleniyor. Bileşenlerin hiçbiri doğru ayrıştırma değil.
4. **Brüt rakam kayma sonrasıdır:** `gross_pnl` = `qty·(çıkış_dolumu − giriş_dolumu)` (ör. işlem 1: 1,5·(37,254 − 40,33) = −4,614); kaymalı fiyatlarla. Memo'daki "brüt +269 < komisyon + fonlama" karşılaştırması bu yüzden kaymayı **bir kez** zaten içeriyor, ama "maliyet 873" ifadesi içermiyor; iki rakam farklı bazdadır.
5. **Model, bp olarak makul ve kendi parametreleriyle tutarlı:** giriş 2,39 bp (model 2 + tick/açılış farkı), çıkış 5,21 bp (model 5 + boşluk kuyruğu). Kayma/komisyon = 7,60 / 10,00 = 0,76. 3:1 olması için kaymanın ~30 bp olması gerekirdi.

Minimal yeniden üretim (geçici betik; `src/` değiştirilmedi, yalnızca içe aktarıldı). Tek bir long işlem: planlı giriş 100, dolum 100,02 (2 bp), planlı stop 99, dolum 98,9505 (5 bp), qty 10, taker 5 bp:

```
saf komisyon (fee_entry+fee_exit) = 0.9949
fees_total = 0.9949  slip_approx = 0.695  fee_only = 0.2999  costs_total = 0.9949
fee_only = fees_total - slip_approx -> 0.2999
```

Komisyon 0,9949 iken `fee_only` 0,2999 raporlanıyor: komisyon, kaymanın payı kadar eksik. Betik: `/tmp/claude-0/-home-user-SG-Github-AB-proje/e7a4ca7f-2079-5069-8ada-ea4ed3c50c7b/scratchpad/repro.py` (`trader_engine.metrics.compute_metrics` + `enrich_trades` çağırır).

Düzeltme önerisi (YAPILMADI; kullanıcı ve mühendislik kararı): native kipte `fee_only` = `fee_paid`, ve rapor satırı "komisyon / kayma (brüt içinde) / fonlama" olarak ayrılmalı; `costs_total` yanına `costs_total_incl_slip` eklenmeli. Eski r02/r03 raporlarındaki "komisyon 186,8" ifadesi düzeltme notu almalı; sonuç sayıları (beklenti, PF) etkilenmiyor.

Gerçekçilik değerlendirmesi (sonuçtan bağımsız): Kayma gerçeğe kıyasla **muhafazakâr**. Tüm çıkışlar stop emri olduğu için çıkışa tek tip 5 bp uygulanıyor; BTC/ETH/BNB gibi derin çiftlerde Binance USDT-M stop-market kaymasının tipik değeri bunun altındadır (tahmin, bu çalışmada doğrulanmadı; gerçek dolum verisi gelince ölçülmeli: kâğıt/testnet `slip_exec_*` sütunları). Dolum fiyatı mum ucuyla sınırlanmadığı için model dolumu mumun dışına itebilir (ek muhafazakârlık). Giriş için 2 bp makul. Model çiftler arası farklılaşmıyor (spread/derinlik yok); bu yüzden maliyetin gerçekte alt çiftlerde (TRX, DOGE) daha yüksek, BTC'de daha düşük olması beklenir; sonuçlar bu yönde sapmalı olabilir.

## 6. Soru 5: kayma ve komisyon öncesi brüt E[R], başa baş maliyet

- **Brüt E[R], tüm maliyetlerden önce** (planlı giriş/stop/trail seviyelerinde fiyat PnL'i, komisyon, kayma ve fonlama yok): **+0,095 R / işlem** (SE 0,024; gün bloklu bootstrap %90: +0,039 … +0,153). USD: +862,4; giriş notional'ının +11,05 bp'si.
- Yalnız fonlama düşülürse (komisyon ve kayma hariç): +0,090 R.
- **Maliyet: 0,1208 R / işlem** (komisyon 0,066 + kayma 0,050 + fonlama 0,006); net −0,0256 R.
- **Başa baş maliyet düzeyi:** toplam tur maliyeti ≤ **11,05 bp** (giriş notional'ı). Fonlamayı (1,19 bp) sabit tutarsak komisyon + kayma ≤ **9,86 bp tur** = **~4,9 bp / taraf**. Bugün 17,6 bp tur (8,8 bp / taraf). Maliyetlerin hepsini birlikte çarpanla ölçeklersek başa baş çarpan **0,59** (maliyeti %41 düşürmek gerekir).
- **Senaryolar (aynı işlemler, aynı çıkışlar; yaklaşık):**

| Senaryo | Net USD | Not |
|---|---:|---|
| Bugünkü model (taker 5 bp, kayma 2/5) | −603,8 | |
| Kayma 0, komisyon taker | −10,5 | memo'nun "≈ 0" iddiası doğrulandı |
| Kayma 0, komisyon 0 (fonlama kalır) | +769,6 | tavan |
| CANLI-K1 stres (komisyon ×2 + 5 bp), kaba hesap (ek komisyon + 5 bp giriş notional'ı üzerinden) | beklenti ≈ −0,124 R | eşik ≥ −0,05 R; mevcut brüt ile geçilemez |

- **Yorum:** Kayma modeli kendi tasarımına uygun; sorun komisyonun kendisi: tur başına 10 bp komisyon, kayma öncesi brüt 11 bp'nin %90'ı. S2-1 (4s tetik) stopu genişletip R başına maliyeti düşürür, ama brüt R'nin de değişeceği için etki koşuyla sınanmalı. S2-2 (limit giriş) giriş komisyonunu ve giriş kaymasını birlikte düşürür; yalnız giriş tarafı makerlaşsa bile tur maliyeti başa baş eşiğinin (≈ 9,9 bp) altına inmez, dolum yanlılığı da riski olduğundan ölçüm S2-2'de yapılacak.
- İki eşik: (a) 0 ≤ E[R] için maliyet 0,095 R'nin altına inmeli (≈ −%21); (b) CANLI-K1'in %90 alt sınır > 0 koşulu için ek olarak ~+0,08 R marj gerekir (§2 madde 1 çıtası); yani brüt ≳ +0,2 R veya maliyet ≲ 0,05 R.

## 7. Doğrulanan / doğrulanamayan, öneriler

Doğrulanan: toplamlar (komisyon, kayma, fonlama, brüt, net), modelin birim ve uygulama yeri, kayma tutarlılığı, kayma sonrası brüt ile kayma öncesi brüt arasındaki ilişki. Doğrulanamayan: gerçek borsa kaymasının model değeriyle ilişkisi (dolum verisi yok); mum ucu dışına dolum sıklığı (1m veri açılmadı).

Öneriler (karar sizin):
1. r02 §6 ve gelecekteki raporlarda komisyon = **780,1** (kayma ayrı, brüt içinde); `fee_only` etiketini native'de kullanmayın.
2. S2 hedefini "maliyet" yerine "kayma öncesi brüt R'yi artırmak veya tur komisyonunu < ~5 bp'ye indirmek" olarak koyun; yalnız kayma azaltımı en fazla +0,050 R verir (başa baş için yetersiz: net ≈ 0).
3. Stop mesafesi dar çiftler (TRX, BTC, BNB) maliyetin R karşılığı yüksek; "daha az çift" yapılmaz kuralı (memo) korunsa da S2-1 (4s) en çok bunlara yarayacak.

Ekler (kalıcı olmayan, geçici dizin): `/tmp/claude-0/-home-user-SG-Github-AB-proje/e7a4ca7f-2079-5069-8ada-ea4ed3c50c7b/scratchpad/a1.py`, `a2.py`, `a3.py`, `repro.py`.
