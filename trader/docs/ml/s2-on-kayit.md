# S2 ön kayıt: strateji araştırma turu (mentor)

Tarih: 18 Kasım 2026. Dayanak: `otonom-trading-arastirma/karar-notu-strateji-2026-11-18.md` (K6 = CANLI-K1, K8 = S2 bütçesi), kullanıcı kararı A (`tasarim-kararlari.md`, `f9c0d0b`), `docs/ml/s2-maliyet-denetimi.md` (`5274d23`). Bu belge yazılırken yeni geri test koşulmadı. Kilitli dönem (2026-05-01 → 2026-11-01) okunmadı ve bu turda hiçbir adımda okunmaz.

Bu belge commit'lendiği anda §1, §2, §5, §6, §7 **dondurulmuştur**. Sonradan yalnız tarihli ek not eklenir; var olan satır değiştirilmez. Bir deneme tanımında koşudan sonra yapılan her değişiklik yeni deneme hakkı harcar.

## 0. Özet

- Denetim sonucu: v1b tüm maliyetlerden önce +0,095 R / işlem kazanıyor, maliyet 0,121 R / işlem. Komisyon tek başına tur başına 10,0 bp; başa baş için toplam tur maliyeti ≤ 11,05 bp olmalı, bugün 18,8 bp. 2022 maliyet öncesi de ekside.
- S2'nin hedefi bu yüzden "kaymayı azaltmak" değildir. İki kol vardır: **(a) işlem başı brüt R'yi artırmak ya da maliyetin R karşılığını küçültmek** (stop mesafesi büyürse aynı bp maliyet daha az R eder), **(b) tur maliyetini bp olarak düşürmek** (komisyon + kayma bugün 17,6 bp; başa baş ≈ 9,9 bp, yani taraf başına ≈ 4,9 bp).
- Deneme bütçesi 6. İlk iki deneme bu belgede tam tanımlıdır: **S2-1** 4 saatlik tetik (kol a), **S2-2** limit (maker) giriş, tutucu dolum modeli (kol b). S2-3 … S2-6 için yer ayrılmıştır (§7).
- Sıra: önce `metrics.py` `fee_only` düzeltmesi ve ölçüm aracı (deneme değil), sonra S2-1, sonra S2-2.
- Geçme ölçütü CANLI-K1 madde 1–3'tür ve değiştirilmedi. Madde 3 (DSR ≥ 0,95, 10 deneme) yaklaşık olarak günlük Sharpe ≥ 0,082 (yıllık ≈ 1,6) ister; bu yüksek bir çıtadır ve hiçbir denemenin geçmemesi olası bir sonuçtur.

## 1. Kurallar (K8)

1. Kilitli dönem öncesinde en fazla **6 deneme**. Deneme = bu belgede (ya da tarihli ekinde) tanımı yazılmış bir strateji sürümünün **tam dönemde** (2021-01-01 → 2026-05-01, bitiş dışlayıcı) **tek** koşusu.
2. Her denemenin tanımı ve `research/trial_registry.csv` ön kayıt satırı, tam dönem koşusundan **önce** commit'lenir. S2-1 ve S2-2 satırları bu belgeyle birlikte eklendi.
3. Tam dönem koşusu temiz çalışma ağacında, kayıtlı commit'te, §5/§6'daki komutla bir kez yapılır. Teknik kesinti (çökme, disk, süre) ve `summary.json` yazılmamışsa aynı commit'te bir kez daha başlatılabilir; kesinti rapora yazılır. `summary.json` yazıldıktan sonra sonuç kesindir.
4. **Keşif bölgesi 2021-01-01 → 2024-01-01** (bitiş dışlayıcı). Bu aralıkta kalan koşular (teknik doğrulama, ileriye bakma denetimi, belirlenimcilik, sayım) serbesttir, deneme sayılmaz, `research/s2_run.py --explore` ile yapılır ve sonuçları geçme kararında kullanılmaz. Keşifte görülen sonuca göre §5/§6 tanımı değiştirilirse bu yeni deneme hakkı harcar.
5. Tam dönem çıktısı üzerinde yalnız §2'deki sabit tablo üretilir. Bunun dışındaki her dilimleme (yıl, ay, çift, saat, rejim kırılımı) yalnız girişi 2024-01-01'den önce olan işlemlerle yapılır.
6. Başarısız denemeler silinmez; rapor ve defter satırı kalır.
7. Kilitli dönem bu turda açılmaz. Yalnız §2'yi geçen tek dondurulmuş aday için, kullanıcı onayıyla, bir kez açılır (CANLI-K1 madde 4).
8. Dondurulmuş dosyalara dokunulmaz: `scripts/build_corpus_v2.py`, `research/ml_build_candidates.py`, `src/trader_ml/{features,features_v2,labels,guards,config}.py`, `src/trader_core/{ml_features,ml_features_v2,signals,regime,indicators}.py`, `src/trader_engine/holdout.py`. freqtrade, ccxt, python-binance kullanılmaz.
9. v1b'nin kâğıt/testnet/canlı davranışı değişmez. Her S2 kod commit'inde §8'deki tarafsızlık testleri geçmelidir.

## 2. Geçme ölçütü (CANLI-K1 madde 1–3; hesap tanımları)

CANLI-K1 metni değişmedi. Aşağısı yalnız hesabın nasıl yapılacağını sabitler; iki okuması olan yerde sıkı olan seçildi.

**Ortak tanımlar**

- Koşu: asıl motor (`trader_engine.backtest`), 10 çift (taban yapılandırmadaki liste), `--fill-model native`, 1 dakikalık adım, tetik kaynağı mark, `--synthetic-rules`, `--target-trade-risk 0.005`, başlangıç 1000. **Ana maliyet kolu:** taker 5 bp / taraf, piyasa girişi kayması 2 bp, stop çıkışı kayması 5 bp, fonlama gerçek oranlarla. S2-2 yalnız girişi değiştirir (§6).
- İşlem kümesi: `trades.csv` içinde `exit_ts` dolu satırlar.
- R: `realized_pnl / loss_at_stop(qty, entry_price, planned_stop)` (`trader_engine.metrics.loss_at_stop`; `summary.json` ile aynı payda).
- **Sınav penceresi:** `entry_ts` ∈ [2022-01-06 00:00, 2026-05-01 00:00) UTC. **Dört dilim** (r02/r03 ile aynı sınırlar): [2022-01-06, 2023-02-04), [2023-02-04, 2024-03-04), [2024-03-04, 2025-04-02), [2025-04-02, 2026-05-01).
- Günlük seri: sınav penceresindeki her takvim günü (UTC, `entry_ts` gününe göre) için o gün girilen işlemlerin R toplamı `s_g` ve sayısı `n_g`; işlemsiz gün 0.

**Kontroller (hepsi sınav penceresinde)**

| Kod | Kontrol | Eşik |
|---|---|---|
| K1-1a | Ortalama net R | > 0 |
| K1-1b | Ortalama net R'nin tek taraflı %90 alt sınırı: günlük seri üzerinde durağan bootstrap (`trader_core.stats.stationary_bootstrap_indices`, `n_boot = 2000`, `seed = 0`, ortalama blok = max(1, `optimal_block_length(s_g)["stationary"]`)), istatistik Σs_g / Σn_g, **%10 yüzdelik** (r02/r03 kapısındaki 3b ile aynı kural). %5 yüzdelik yalnız bilgi olarak yazılır | > 0 |
| K1-1c | Kâr faktörü (`realized_pnl` üzerinden) | > 1 |
| K1-1d | Dört dilimden ortalama net R'si > 0 olanların sayısı | ≥ 3 |
| K1-1e | `entry_ts` ≥ 2024-01-01 işlemlerin ortalama net R'si | > 0 |
| K1-1f | İşlem sayısı | ≥ 800 |
| K1-1g | On çiftin her biri tek tek çıkarıldığında kalan işlemlerin ortalama net R'si | on durumda da > 0 |
| K1-2 | Maliyet stresi: aynı işlemler, `R_stres = (realized_pnl − ek) / loss_at_stop`; `ek = (fee_entry + fee_exit) + 0,0005 × qty × (entry_price + exit_price)`. Yani ödenen komisyon iki katına çıkar ve **taraf başına** 5 bp eklenir (r02/r03 kapısındaki kolla aynı; "5 bp"nin tur başına okunması daha gevşektir, kullanılmaz). Ortalama `R_stres` | ≥ −0,05 |
| K1-3 | DSR: günlük seri `s_g`; `sr = ortalama / std(ddof=1)`, `n` = gün sayısı, çarpıklık ve basıklık `return_moments(s_g)`; `deflated_sharpe(sr, n, skew, kurt, n_trials = N)` (deneme varyansı varsayılan 1/(n−1)); `N = max(10, 1 + o ana kadar ön kayıtlı S2 deneme sayısı)` | ≥ 0,95 |

Sonuç: dokuz kontrolün hepsi geçerse deneme **GEÇTİ**, biri kalırsa **KALDI**. İlk kalan kontrol rapora yazılır; hepsi yine de hesaplanır.

**Güç ön hesabı (sonuca bakılmadan):** n = 1576 gün, N = 10 için K1-3 yaklaşık günlük `sr ≥ 0,082` ister (yıllık ≈ 1,57). K1-1b, 4 saatlik tetikte beklenen ~900 işlemde kabaca +0,08 R ister. K1-1f, 4 saatlik tetikte sınırdadır (beklenen 800–950 işlem); 800'ün altı KALDI'dır.

**Sabit rapor tablosu** (her deneme için, fazlası §1 madde 5'e tabidir): tam dönem işlem sayısı, ortalama ve medyan net R, kâr faktörü, net sonuç, en büyük düşüş (gerçekleşmiş ve anlık değerli); dokuz kontrolün değeri ve sonucu; tam dönem maliyet dökümü (komisyon, kayma, fonlama; USD, tur başına bp, R / işlem; kayma öncesi brüt R); atlanan aday sayıları (nedenine göre); taban (v1b, §4) ile aynı satırlar yan yana.

## 3. Adım 0a: `metrics.py` `fee_only` düzeltmesi (karar: ŞİMDİ, ayrı commit)

**Karar.** Düzeltme S2'nin ilk işidir; taban yeniden üretiminden ve her S2 koşusundan önce, tek başına bir commit olarak yapılır.

Gerekçe: (1) S2'nin konusu maliyet dökümüdür; her yeni `summary.json` bilinen yanlış bir komisyon rakamı taşır ve bu rakam bir karar notunu zaten yanılttı. (2) Etki dardır: `summary.json` içinde tek alanın değeri değişir; `trades.csv`, `open_at_end.json`, defter, `meta.json`, metrik anahtar kümesi, R, beklenti, kâr faktörü, `fees_total`, `slip_approx`, `costs_total` aynı kalır. (3) Hiçbir kod `fee_only` okumuyor (`src/`, `scripts/`, `research/*.py` tarandı; ML kapısı `cost_r` kullanır). (4) Ertelemek, altın özet karmasını S2 kod değişiklikleriyle aynı anda oynatır ve "v1b değişmedi" kanıtını bulandırır.

**Değişiklik (tek dosya: `src/trader_engine/metrics.py`, `compute_metrics`).** Bugün:

```python
    if slip_bps is not None:
        t["slip_paid"] = t["qty"] * (t["entry_price"] + t["exit_price"]) * (slip_bps / 1e4)
    else:
        t["slip_paid"] = t["slip_cost"] if "slip_cost" in t else 0.0
    t["fee_only"] = t["fee_paid"] - t["slip_paid"]
```

Olacak:

```python
    if slip_bps is not None:        # legacy_compat: kayma komisyon oranina katilmistir
        t["slip_paid"] = t["qty"] * (t["entry_price"] + t["exit_price"]) * (slip_bps / 1e4)
        t["fee_only"] = t["fee_paid"] - t["slip_paid"]
    else:                           # native: fee_paid saf komisyondur, kayma dolum fiyatindadir
        t["slip_paid"] = t["slip_cost"] if "slip_cost" in t else 0.0
        t["fee_only"] = t["fee_paid"]
```

Başka satır değişmez. Yeni anahtar eklenmez (`METRIC_KEYS` aynı kalır; `tests/engine/test_engine_06_spec.py` anahtar kümesi testi dokunulmadan geçer). `costs_total` tanımı (komisyon + fonlama, kayma hariç) değişmez; kayma dahil toplam `research/s2_eval.py` içinde `trades.csv`'den hesaplanır. İşlev belge dizgisine bir cümle eklenir: native kipte `fee_only == fees_total`, kayma `gross_pnl` içindedir. `ENGINE_VERSION` artırılmaz (`meta.json` aynı kalmalı).

Belge: `docs/motor/06-backtester.md` satır 84'te `fee_only = fee_paid − slip_paid` ifadesi "uyum kipinde `fee_only = fee_paid − slip_paid`; native kipte `fee_only = fee_paid` (kayma dolum fiyatındadır, `costs_total`'a girmez)" olarak düzeltilir.

**Testler (bağımsız test yazarı; yeni dosya `tests/engine/test_metrics_fee_only.py`).**

| Kod | Davranış |
|---|---|
| M-1 | Native (`slip_bps=None`), `slip_cost` > 0 olan sentetik işlemler: `fee_only == fees_total` (tam eşitlik) ve `slip_approx == Σ slip_cost`. |
| M-2 | Denetimdeki tek işlem örneği (long; planlı giriş 100, dolum 100,02; planlı stop 99, dolum 98,9505; qty 10; taker 5 bp): `fees_total ≈ 0,9949`, `fee_only ≈ 0,9949` (eski değer 0,2999 değil), `slip_approx ≈ 0,695`, `costs_total ≈ 0,9949` (fonlama 0). |
| M-3 | Uyum kipi (`slip_bps=5`): `fee_only == fees_total − qty × (entry_price + exit_price) × 5e-4` (eski davranış korunur). |
| M-4 | Native, `slip_cost` sütunu yok: `slip_approx == 0` ve `fee_only == fees_total`. |
| M-5 | Aynı girdide `fee_only` dışındaki bütün anahtarlar düzeltme öncesi kodla aynıdır (öncesi kod `git show <taban>:src/trader_engine/metrics.py` ile yüklenir; `tests/test_wp3_spec.py` içindeki `load_base_module` kalıbı). Boş işlem tablosu davranışı değişmez. |

**Altın özet karması ve eski raporlar.**

| Yer | Durum | Yapılacak |
|---|---|---|
| `tests/test_wp3_golden.py` (K1/K2; taban `d75a70e` ile yeni kodun çıktısını karşılaştırır) | `summary.json` karması artık tutmaz | `trades.csv` ve `open_at_end.json` bayt karşılaştırması aynen kalır. `summary.json` için: iki dosya JSON olarak okunur, `fee_only` anahtarı ikisinden çıkarılır, kalan sözlükler **tam eşit** olmalı; ayrıca `yeni["fee_only"] == yeni["fees_total"]` ve `taban["fee_only"] ≈ taban["fees_total"] − taban["slip_approx"]`. Başka gevşetme yok. |
| `tests/engine/test_risk_ladder_impl.py` T-28 (`summary.json` karma öneki `5ee22e24485e`) | önek değişir | Düzeltmeden **önce** T-28 komutu çalıştırılıp `summary.json` saklanır; düzeltmeden sonra yeniden çalıştırılır; iki JSON'un yalnız `fee_only` alanında ayrıştığı doğrulanır; önek yeni değerle değiştirilir ve commit mesajına eski/yeni önek yazılır. `trades.csv` öneki (`89e530326f59`) değişmemelidir. |
| `tests/engine/test_engine_compat_equity.py` (`NATIVE_GOLDEN`) | etkilenmez (`trades.csv` + defter özeti) | değişmeden geçmeli |
| `src/trader_core/drift_monitor.py` `REF_SUMMARY_SHA256`, `tests/test_drift_monitor_impl.py` | etkilenmez: diskteki dondurulmuş dosyanın karmasıdır, yeniden hesaplanmaz | dokunulmaz |
| `docs/ml/r02-r03-on-kayit.md` §10 (`summary.json` `6d61844c…`), katman ve derlem karmaları | tarihsel kayıt; o commit'lerin çıktısıdır. Katman `trades.csv`/defterden kurulur, `summary.json`'dan değil | dokunulmaz. Aynı koşu bugünkü kodla yeniden üretilirse `trades.csv` ve `open_at_end.json` karması tutar, `summary.json` yalnız `fee_only` alanında ayrışır |
| Dondurulmuş koşu dizinleri (`research/ml/frozen/…`, `var/backtests/corpus_v2_taken_v1b_native/`) | eski `fee_only` değerini taşır | yeniden üretilmez, üzerine yazılmaz. Bu dosyalardan komisyon okunacaksa `fees_total` okunur |
| `docs/ml/r02-kapi-raporu.md` §6 | yanlış etiketli ayrıştırma | tarihli düzeltme notu eklendi (bu commit) |
| `docs/ml/r03-kapi-raporu.md`, 19c raporu, kapı sonuçları | `fee_only` kullanmıyor | değişiklik yok |
| `research/make_report.py` ("Komisyon+kayma toplamı" satırı) | uyum kipi raporu için yazılmış etiket; native koşuda `fees_total` saf komisyondur | bu turda dokunulmaz; S2 raporları `research/s2_eval.py` çıktısını kullanır |
| Karar notu (18 Kasım) §3 sıra 0'daki "komisyonun (187) üç katı" | denetimin cevapladığı soru | not değiştirilmez; düzeltme `s2-maliyet-denetimi.md` ve r02 notundadır |

Kabul: M-1 … M-5 geçer; `WP3_GOLDEN=1 pytest tests/test_wp3_golden.py` geçer; T-28 yeni önekle geçer; `pytest tests/engine tests/reports tests/test_drift_monitor_impl.py` geçer.

## 4. Adım 0b–0c: ölçüm aracı ve taban (deneme değil)

**0b. `research/s2_eval.py`** (yeni; saf işlevler + CLI). Girdi: bir koşu dizini (`trades.csv`, `summary.json`, `meta.json`). Çıktı: aynı dizine `s2_eval.json` ve ekrana §2 tablosu.

- `python research/s2_eval.py <koşu_dizini> --n-registered <k>`; `N = max(10, 1 + k)`.
- `meta.json` dönemi tam dönem (2021-01-01 → 2026-05-01) değilse dokuz kontrol hesaplanmaz; yalnız girişi 2024-01-01'den önceki işlemlerin sayım ve maliyet dökümü yazılır (`"mode": "explore"`).
- Dönem bitişi 2026-05-01'den sonraysa hata ile çıkar (ikinci kilit; motor zaten reddeder).
- `s2_eval.json`: `{"schema": "s2-eval/1", "run_id", "git_commit", "n_trials", "window", "checks": [{"code", "value", "threshold", "ok"}], "passed", "first_failure", "costs": {...}, "full_period": {...}}`.
- Maliyet dökümü: komisyon = `fee_entry + fee_exit`; kayma = `slip_cost`; fonlama = `funding_paid`; kayma öncesi brüt = `gross_pnl + slip_cost`; bp paydası `qty × entry_price`; R paydası `loss_at_stop`.

**0b. `research/s2_run.py`** (yeni). Denemeleri sabit bayraklarla başlatır; serbest parametre almaz.

- `python research/s2_run.py --trial {BASE,S2-1,S2-2}`: çalışma ağacı temiz değilse (izlenen dosyada değişiklik) çıkar; `research/trial_registry.csv` içinde o denemenin ön kayıt satırı yoksa çıkar; `var/backtests/<id>/` varsa çıkar; S2-1 için stratejiyi kayıt defterine çalışma anında ekler (§5); `trader_engine.backtest.main(argv)` çağırır; ardından `s2_eval` çalıştırır; `research/run_bt_engine.append_registry` ile sonuç satırı ekler (`id = <deneme>_sonuc`, notta GEÇTİ/KALDI ve ilk kalan kontrol).
- `--explore YYYYMMDD-YYYYMMDD`: aralık [20210101, 20240101] içinde değilse çıkar; çıktı `var/backtests/s2_explore/<id>/`; deftere satır eklemez; `--paranoid` gibi ek motor bayrakları yalnız bu kipte geçirilebilir.

Testler (`tests/research/test_s2_eval.py`, sentetik `trades.csv` ile; gerçek veri okumaz):

| Kod | Davranış |
|---|---|
| E-1 | Pencere ve dilim ataması `entry_ts` ile; sınır anları (2022-01-06 00:00 dahil, 2026-05-01 00:00 hariç; dilim sınırları sol kapalı). |
| E-2 | R paydası `metrics.loss_at_stop`; `summary.json` `expectancy_R` ile tam dönemde 1e-12 içinde aynı. |
| E-3 | K1-1b: aynı girdi iki kez aynı sonucu verir (seed 0); bütün günleri pozitif seride alt sınır > 0, simetrik gürültüde ≤ 0. |
| E-4 | K1-1g: tek çift bütün kârı taşıyorsa kontrol kalır. |
| E-5 | K1-2: elle hesaplanan örnek (`ek` formülü); maker girişli işlemde ödenen komisyonun iki katı uygulanır. |
| E-6 | K1-3: `deflated_sharpe` çağrısı `n_trials = max(10, 1 + k)` ile; k = 12 için N = 13. |
| E-7 | Keşif dönemi koşusunda `passed` alanı yok, `mode == "explore"`; 2024-01-01 ve sonrası girişler dökümlere girmez. |
| E-8 | Maliyet dökümü: denetim §2'deki özdeşlik `net = kayma öncesi brüt − komisyon − kayma − fonlama` 1e-9 içinde. |
| E-9 | `s2_run --explore 20230101-20240201` reddedilir; `--trial S2-1` ön kayıt satırı yokken reddedilir; kirli ağaçta reddedilir. |

**0c. Taban yeniden üretimi.** `python research/s2_run.py --trial BASE` (id `s2_base_v1b`; bayraklar: `--period 20210101-20260501 --tf 1h --fill-model native --strategy price_action_v1 --synthetic-rules --target-trade-risk 0.005`). Bu, dondurulmuş katman koşusunun aynısıdır; sonucu bilinir, deneme sayılmaz. Doğrulama: 4695 işlem; ortalama net R −0,0256; komisyon 780,09; kayma 593,26; fonlama 92,84; kayma öncesi brüt +0,095 R; sınav penceresinde 3861 işlem, −0,043 R. Sapma varsa S2 koşuları başlamaz, mentora dönülür. Taban satırı her deneme raporunda karşılaştırma sütunudur.

## 5. S2-1: 4 saatlik tetik (kol a)

**Hipotez.** Maliyet bp olarak sabittir (tur ≈ 18–19 bp); R karşılığını stop mesafesi belirler (denetim §4: dar stoplu çiftler 0,14–0,18 R, geniş stoplular 0,09 R öder). Aynı kurallar 4 saatlik mumda uygulanırsa stop mesafesi kabaca iki katına çıkar ve maliyet ≈ 0,06 R'ye iner. İşlem başı brüt R korunursa net artıya geçer. Yanlışlanma: brüt R 4 saatte düşerse ya da işlem sayısı 800'ün altında kalırsa.

**Tanım (dondurulmuş).** v1b ile aynı kurallar ve aynı dokuz parametre (varsayılan değerler; ayar yok), tek fark tetik mumunun 4 saatlik olması:

1. Sinyal yalnız 4 saatlik mum kapanışlarında (00, 04, 08, 12, 16, 20 UTC) aranır. Tetik mumu = o anda kapanan 4 saatlik mum. EMA, ATR, son dip/tepe, gövde oranı ve stop tamponu 4 saatlik mumlardan hesaplanır (`trader_core.signals.compute_signals`, girdi 4 saatlik mumlar).
2. Rejim: 4 saatlik sınıflama aynen; tetik mumuna, o mumun **açılışında** bilinen rejim hizalanır (`regime.align_to_base(reg, h4.index, 4)`; v1b'nin 4 saatlik sınırdaki kararında kullandığı rejimle aynı).
3. Yalnız T1 kurulumu (R1 kapalı, v1b gibi). Aynı mumda yeniden giriş engeli 4 saatlik pencereyle: son çıkış nedeni `stop` ya da `trail_stop` ise ve çıkış anı [D − 4s, D) içindeyse D'deki sinyal alınmaz.
4. Giriş: piyasa emri, D'den sonraki ilk 1 dakikalık mumun açılışı (motorun bugünkü yolu). Başlangıç stopu = planlı stop.
5. İz süren stop ve rejim dönüşü çıkışı yalnız 4 saatlik kapanışlarda değerlendirilir; iz süren stop girişten sonraki 4 saatlik mumların en yüksek/en düşüğü ve o mumların 4 saatlik ATR'siyle (`trail_atr` × ATR) hesaplanır. Mum içi stop tetiklemesi motorun bugünkü yoludur (dakikalık, mark).
6. Risk, kaldıraç, boyut, kapılar, maliyet kolu: §2 "ortak tanımlar".

**Kod (dosyalar).** Motorun karar adımı 1 saatlik kalır; 4 saatlik mantık stratejinin içindedir. Böylece `trader_core/signals.py` (dondurulmuş; `trigger_tf` yalnız `1h`/`15m` kabul eder) ve defter şeması (`trigger_tf` CHECK kısıtı) değişmez. Defterdeki `trigger_tf = "1h"` bu denemede motorun adım aralığıdır; sinyal aralığını strateji adı ve sürümü taşır.

| Dosya | Değişiklik |
|---|---|
| `src/trader_engine/strategies/price_action_v1_4h.py` | **yeni** |
| `tests/engine/test_engine_module_inventory.py` | `ALLOWED_MODULES_B`'ye `"strategies/price_action_v1_4h.py"` eklenir (mentor onayı: bu belge) |
| `research/s2_run.py` | stratejiyi çalışma anında kaydeder: `trader_engine.strategies.registry._FACTORIES["price_action_v1_4h"] = make_v1b_4h` |
| `tests/engine/test_s2_1_4h_strategy.py` | **yeni** (bağımsız test yazarı) |

Dokunulmayanlar: `strategies/registry.py` (statik kayıtta yeni ad yok; `list_strategies()` testleri aynen geçer; kâğıt/testnet/canlı süreçleri bu stratejiyi yükleyemez), `engine.py`, `backtest.py`, `precomputed.py`, `strategy_runner.py`, `position_manager.py`, `bars.py`, `trader_core/*`.

**`price_action_v1_4h.py` belirtimi.**

- `make_v1b_4h()` → `PriceActionV1H4`. `info`: `name="price_action_v1_4h"`, `version="s2-1.0"`, `setups=("T1",)`, `timeframes=("trigger","4h")`, `allowed_trigger_tfs=("1h",)`, `warmup_bars`, `window_bars`, `min_contiguous`, `param_specs` v1b ile aynı (`price_action_v1._param_specs()`), `paper_allowed=False`. `label()` v1b kalıbı.
- `validate_params(m)`: `SignalParams.from_mapping(m)`; `trigger_tf != "1h"` ise `ValueError`.
- `compute(ctx)`:
  1. `params = SignalParams.from_mapping(ctx.params)`; `trig = ctx.bars[ctx.tf]` (1 saatlik); `h4 = ctx.bars["4h"]`.
  2. `reg = regime.classify_series(h4[OHLC], params.regime_params())`; `al = regime.align_to_base(reg, h4.index, 4)`; `sig4 = signals.compute_signals(h4[OHLC], al, params)`.
  3. v1b nötrlemesi `sig4` üzerinde aynen: `setup` dolu ve `setups` dışında olan satırlarda `signal=False`, `skip_reason=None`, `reasons = "v1b:r1_disabled|" + reasons`.
  4. Çıktı tablosu `trig.index` üzerinde, sütunlar `SIGNAL_COLUMNS`. 4 saatlik mumun açılışı T ise satırı, açılışı T + 3 saat olan 1 saatlik satıra **aynen** kopyalanır (o satırın kapanışı = 4 saatlik mumun kapanışı). O 1 saatlik mum yoksa satır düşer.
  5. Diğer bütün 1 saatlik satırlar "boş"tur: `signal=False`; `setup`, `side`, `skip_reason`, `regime` = `None`; bütün sayısal sütunlar NaN (`rh_touches`, `rl_touches`, `pullback_ema` dahil); `reasons = "s2_1:off_grid"`.
  6. Çıktı nedenseldir: herhangi bir `D` için geçmişi `D`'de kesip hesaplamak, tam geçmişle hesaplanan tablonun `D`'ye kadarki kısmıyla aynı satırları verir (ön hesaplı kaynak `compute`'u çift başına bir kez, tüm geçmişle çağırır).
- `post_filter(row, ctx)`: v1b ile aynı mantık, pencere `bar_open = ctx.D − 4 saat`; etiket `"v1b:same_bar_reentry|"`.
- `exit_policy()` → `H4ExitPolicy()`; `evaluate(pos, ctx)`:
  1. `ctx is None` → `position_manager.evaluate_exit(pos, None)` (varsayılanla aynı: `force_exit`).
  2. `len(ctx.atrs) == 0` ya da `ctx.atrs[-1]` sonlu değil → `ExitDecision("none")` (bu kapanış 4 saatlik kapanış değil ya da 4 saatlik mum eksik).
  3. Gruplama: `ctx.highs`, `ctx.lows`, `ctx.atrs` baştan sona gezilir; koşan en yüksek ve en düşük (NaN atlanır) tutulur; `atrs[k]` sonlu olan her satırda bir 4 saatlik grup kapanır: `(grup_en_yüksek, grup_en_düşük, atrs[k])` eklenir, koşan değerler sıfırlanır. (Tabloda `atr_tf` yalnız 4 saatlik kapanış satırlarında sonlu olduğu için grup sınırı zaman damgası gerekmeden bulunur; ilk grup, giriş 4 saatlik sınırda değilse eksik gruptur.)
  4. `ctx4 = ExitContext(bar_close_ts=ctx.bar_close_ts, highs, lows, atrs = grup dizileri, regime_last=ctx.regime_last, last_close=ctx.last_close, n_closed=grup sayısı)`; dönüş `position_manager.evaluate_exit(pos, ctx4)`. İz süren stop formülü, rejim dönüşü ve "gevşetme yok" kuralı böylece motorun kendi kodudur.

**Testler (`tests/engine/test_s2_1_4h_strategy.py`; sentetik mumlar, gerçek veri yok).**

| Kod | Davranış |
|---|---|
| H-1 | `compute` çıktısı `validate_table(sig, info, trig.index)` geçer; sütun kümesi `SIGNAL_COLUMNS`. |
| H-2 | `signal=True` satırların hepsinin açılışı saat ≡ 3 (mod 4) UTC'dir; diğer satırlar madde 5'teki boş satırdır (`reasons == "s2_1:off_grid"`). |
| H-3 | Eşleme: her 4 saatlik sinyal satırı için (T) 1 saatlik T + 3s satırındaki `planned_entry`, `planned_stop`, `side`, `setup`, `atr_tf`, `regime`, `reasons` 4 saatlik hesapla (`compute_signals(h4, align_to_base(reg, h4.index, 4), params)`) aynıdır; `planned_entry` = 4 saatlik mumun kapanışı. |
| H-4 | Nedensellik: rastgele seçilmiş 20 kesim noktasında kesilmiş geçmişle hesaplanan tablo, tam tablonun ön ekiyle aynıdır (NaN = NaN). |
| H-5 | R1 kurulumu üreten bir 4 saatlik seride `signal=False` ve `reasons` `"v1b:r1_disabled|"` ile başlar. |
| H-6 | `post_filter`: son çıkış `stop`, çıkış anı D − 3s30dk → sinyal düşer (`"v1b:same_bar_reentry|"`); çıkış anı D − 4s01dk → kalır; neden `regime_flip` → kalır. |
| H-7 | `validate_params`: `trigger_tf="15m"` ve `"4h"` reddedilir; `"1h"` geçer. `info.paper_allowed is False`. |
| H-8 | Çıkış: 4 saatlik kapanış olmayan saatte (`atrs[-1]` NaN) `kind == "none"`; `ctx=None` → `force_exit`. |
| H-9 | Çıkış eşdeğerliği: 12 saatlik (3 grup) sentetik yol için `H4ExitPolicy.evaluate` sonucu, aynı yolun elle 4 saatliğe toplanmış dizileriyle `evaluate_exit` sonucuna eşittir (`stop_update` değeri dahil); rejim dönüşünde `exit/regime_flip`; iz süren stop son kapanışı geçmişse `exit/trail_stop`. |
| H-10 | Eksik ilk grup: giriş D + 2s'de ise ilk grup 2 satırdan oluşur ve sonuç elle hesapla aynıdır. Aradaki 1 saatlik satır eksikse (dizi kısa) gruplama yine `atrs` sonlu satırlarda kapanır. |
| H-11 | Uçtan uca duman: mevcut sentetik geçmiş fikstürüyle (`tests/engine/test_engine_06_impl_smoke.py` kalıbı), strateji `monkeypatch.setitem(REG._FACTORIES, …)` ile kaydedilip kısa bir geri test koşulur: çıkış 0; bütün girişlerin `signal_bar_close_ts` saati 4'ün katı; `meta.json` `strategy == "price_action_v1_4h"`. |
| H-12 | Statik kayıt değişmedi: `list_strategies() == ("price_action_v1", "price_action_v1_full", "price_action_v1_ml")`; `get_strategy("price_action_v1_4h")` kayıt yapılmadan `unknown_strategy` verir. |

**Koşudan önce (keşif bölgesinde, deneme değil).** `python research/s2_run.py --trial S2-1 --explore 20230101-20230701 --paranoid 200` (ileriye bakma denetimi: pencereli ve ön hesaplı kaynak aynı satırları vermeli); aynı komut iki kez → `trades.csv` bayt bayt aynı (belirlenimcilik). Bu koşuların beklenti/kâr rakamı rapora yazılmaz.

**Tek koşu.** `python research/s2_run.py --trial S2-1` (id `s2_1_4h`; motor bayrakları: `--period 20210101-20260501 --tf 1h --fill-model native --strategy price_action_v1_4h --synthetic-rules --target-trade-risk 0.005`). Rapor: `docs/ml/s2-1-raporu.md` (§2 sabit tablo + taban sütunu).

## 6. S2-2: limit (maker) giriş, tutucu dolum modeli (kol b)

**Hipotez.** Girişte taker 5 bp + kayma 2,4 bp yerine maker 2 bp ödenir: tur maliyeti 18,8 → ≈ 13,4 bp (0,121 → ≈ 0,086 R). Bedeli ters seçimdir: fiyat limite geri gelmeden kaçan işlemler (çoğu kazanan) alınamaz, geri gelenler (çoğu kaybeden) dolar. Deneme bu bedeli tutucu varsayımla ölçer. Denetimin öngörüsü: tek başına başa başı geçmesi beklenmez; asıl değeri S2-1 ile birleşimdedir (§7). Yanlışlanma: dolan işlemlerin brüt R'si, kazanılan maliyetten fazla düşerse.

**Tanım (dondurulmuş).** v1b (1 saatlik tetik, `price_action_v1@1b.0`) aynen; yalnız giriş emri değişir. Long için (short ayna):

1. Karar anı D'de (sinyal mumunun kapanışı) limit alış emri verilir; fiyat `L` = `planned_entry` (sinyal mumunun kapanışı), tick'e pasif yönde yuvarlanır (long aşağı, short yukarı). Miktar, kaldıraç, stop bugünkü hesapla aynı (`planned_entry` ve `planned_stop` üzerinden).
2. Emir, açılışı [D, D + 1 tetik mumu) içinde olan 1 dakikalık mumlarda geçerlidir (1 saatlik tetikte 60 mum). Fiyat kaynağı son işlem fiyatıdır (mark değil).
3. **Dolum koşulu (tutucu):** mumun en düşüğü `≤ L − 1 tick` ise emir dolmuş sayılır. Fiyatın `L`'ye yalnız değmesi dolum değildir. Dolum fiyatı her zaman `L`'dir (fiyat iyileşmesi yok, kayma yok).
4. **Komisyon:** maker 2 bp (`0.0002`). İstisna, **boşluk kuralı:** açılışı tam D olan ilk mumun açılış fiyatı zaten `≤ L − 1 tick` ise (emir verildiği anda fiyat limitin ötesinde) dolum yine `L` fiyatından ama **taker 5 bp** ile yazılır. (Gerçekte bu durumda emir ya daha iyi fiyattan taker olarak dolar ya da "yalnız maker" ise reddedilir; model ikisinden de kötüsünü yazar.)
5. Süre sonunda dolmamış emir iptal edilir; aday alınmamış sayılır, yeniden denenmez, piyasa emrine çevrilmez. Defterde kararın düzeltme satırı `final_action="skipped"`, `skip_reason="order_failed"` olur (mevcut yol); broker sayacı `limit_expired` artar.
6. Dolumdan sonra stop bugünkü yolla konur. Dolumun gerçekleştiği dakikanın en düşüğü stopu da geçiyorsa işlem aynı dakikada stop olur (mum içi sıra bilinmez; kötü olan varsayılır).
7. Çıkışlar aynen: stop ve iz süren stop, taker 5 bp + 5 bp kayma. Dakikalık mumu eksik olan dakikada dolum olmaz.
8. Emir beklerken çift "açılıyor" durumundadır; aynı çifte yeni giriş yapılmaz ve bekleyen emrin riski portföy kapılarında sayılır (bugünkü 1 dakikalık bekleme davranışının 60 dakikaya uzamış hali). Süre, bir sonraki karar adımından **önce** dolar.

Parametreler sabittir: fiyat = sinyal kapanışı, süre = 1 tetik mumu, tick eşiği = 1, maker = 2 bp. Bunlardan birini değiştirmek yeni denemedir.

**Kod (dosyalar).**

| Dosya | Değişiklik |
|---|---|
| `src/trader_engine/brokers/paper_limit.py` | **yeni**: `LimitEntryPaperBroker(PaperBroker)` |
| `src/trader_engine/precomputed.py` | `PrecomputedSignalSource`'a salt okunur `planned_entry_at(pair, D) -> float \| None` eklenir (yalnız ekleme) |
| `src/trader_engine/backtest.py` | `BacktestSpec` alanları `entry_mode: str = "market"`, `maker_fee: float = 0.0002`, `limit_ttl_bars: int = 1`; CLI `--entry-mode {market,limit}`, `--maker-fee`, `--limit-ttl-bars`; `run_once` içinde broker seçimi; `meta.json`'a koşullu anahtar |
| `tests/engine/test_engine_module_inventory.py` | `ALLOWED_MODULES_B`'ye `"brokers/paper_limit.py"` |
| `tests/engine/test_s2_2_limit_entry.py` | **yeni** (bağımsız test yazarı) |

Dokunulmayanlar: `engine.py`, `order_manager.py`, `brokers/paper.py`, `brokers/binance_futures.py`, `config.py` (`CostModel` aynı kalır; `meta.json`'daki `cost` sözlüğü değişmez), `position_manager.py`, `state.py`, `trader_core/*`. Limit giriş yalnız geri test kipinde, yalnız `--entry-mode limit` verilince devreye girer; kâğıt/testnet/canlı süreçlerinin kod yolu aynıdır.

**`backtest.py` belirtimi.**

- `spec_from_args`: `entry_mode == "limit"` ve `fill_model != "native"` → `BacktestArgError("bad_args")`. `maker_fee` ∉ [0, 0.001] ya da `limit_ttl_bars < 1` → `bad_args`.
- `run_once`: `entry_mode == "market"` iken bugünkü satırlar **karakter karakter aynı yoldan** çalışır (broker sınıfı, `PaperConfig`, `meta`). `entry_mode == "limit"` iken: `broker = LimitEntryPaperBroker(PaperConfig(...aynı...), view.rules, view.funding, clock, tick_fn=None, limit_price_fn=signals.planned_entry_at, maker_fee=s.maker_fee, ttl=tf_delta(tf) * s.limit_ttl_bars)`.
- `meta.json`: yalnız `entry_mode != "market"` iken `entry_model = {"mode": "limit", "maker_fee": …, "ttl_bars": …, "fill_rule": "trade_through_1tick", "gap_rule": "taker_at_limit"}` anahtarı eklenir. Piyasa kipinde anahtar **yoktur** (altın `meta` eşitliği).
- `summary.json`: limit kipinde `engine.counters` içine broker sayaçları `limit_filled_maker`, `limit_filled_gap_taker`, `limit_expired` girer (mevcut sayaç aktarım yolu; yoksa `meta.entry_model.counters`).

**`precomputed.py` belirtimi.** `planned_entry_at(pair, D)`: `_locate` ile aynı indeks hesabı ama **yan etkisiz** (sayaç artırmaz, `post_filter` çağırmaz): çift tablosu yoksa ya da D'de kapanan tetik mumu yoksa `None`; aksi halde `recs[i]["planned_entry"]` (sonlu değilse `None`).

**`paper_limit.py` belirtimi.**

- Kurucu: `PaperBroker` argümanları + `limit_price_fn`, `maker_fee`, `ttl` (timedelta). İç sözlük `_limit: dict[client_id, (L, placed_ts, valid_until)]`.
- `_new_order(req)`: `req.role == "entry"` ise önce `L0 = limit_price_fn(req.pair, req.signal_bar_close_ts)`; `None` ise üst sınıf çağrılmadan `self._reject(req.client_id, "limit_no_price")` döner. `L` = `L0`'ın tick'e pasif yuvarlanmışı (`numeric.floor_step` / `ceil_step`). Sonra üst sınıf çağrılır ve `_limit[cid] = (L, req.signal_bar_close_ts, req.signal_bar_close_ts + ttl)` yazılır. Diğer roller üst sınıfa aynen gider.
- `_fill_entry(o, bar, rules)`: `o` `_limit` içinde değilse üst sınıf. İçindeyse: `bar.open_ts ≥ valid_until` → dokunma (iptal adım sonunda). Alışta `gap = bar.open_ts == placed_ts and bar.last_o ≤ L − tick·(1 − 1e-9)`; `through = bar.last_l ≤ L − tick·(1 − 1e-9)` (satışta `last_o`/`last_h` ile `≥ L + tick`). İkisi de değilse emir `new` kalır. Dolumda: fiyat `L`, komisyon oranı `gap` ise `cost.taker_fee`, değilse `maker_fee`; üst sınıfın `_fill_entry` gövdesindeki denetimler ve kayıtlar **aynı sırayla** uygulanır (`position_exists`, `min_notional`, kaldıraç/teminat, `insufficient_margin`, cüzdan, `_Pos`, likidasyon fiyatı, `_last_funding`, `Fill(reason="market", ref_price=L, ts=bar.open_ts)`). Üst sınıf gövdesi kopyalandığı için kopya eşliği testle sabitlenir (L-12).
- `advance(bars, phase)`: üst sınıfı çağırır; `phase == "triggers"` sonunda, `status == "new"` olan her limit giriş emri için `self._last_step_ts + 60 sn ≥ valid_until` ise `_reject_at_fill(o, self._last_step_ts + 60 sn, "limit_expired")` ve `_limit` kaydı silinir. (Motor bu olayı adımın ikinci olay işlemesinde alır ve pozisyonu `_close_unopened` ile kapatır; bir sonraki karar adımı bundan sonra gelir.)
- `snapshot()`: `_limit` boş değilken `RuntimeError` (geri testte kullanılmaz; kâğıt kalıcılık biçimi değişmez).
- Sayaçlar: `limit_filled_maker`, `limit_filled_gap_taker`, `limit_expired`.

**Testler (`tests/engine/test_s2_2_limit_entry.py`; sentetik dakikalık mumlar; long ve short ayrı).**

| Kod | Davranış |
|---|---|
| L-1 | Değme yetmez: en düşük == `L` olan mumlarda dolum yok; en düşük == `L − tick` → dolum; dolum fiyatı tam `L`; komisyon `qty × L × 0,0002`. |
| L-2 | Boşluk kuralı: D mumunun açılışı `L − tick` → dolum `L`, komisyon `qty × L × 0,0005`, sayaç `limit_filled_gap_taker`. Aynı açılış D + 1 dk mumunda → maker. |
| L-3 | Süre: D + 59 dk mumunda geçiş → dolar; hiç geçiş yok → D + 60 dk'dan önce `order_rejected(limit_expired)`; D + 60 dk mumundaki geçiş doldurmaz. |
| L-4 | Yuvarlama: `planned_entry` tick katı değilken long `L` aşağı, short `L` yukarı yuvarlanır; dolum koşulu yuvarlanmış `L`'ye göredir. |
| L-5 | Motor bütünleşmesi (sentetik geçmiş fikstürü + sahte strateji): süresi dolan emirde pozisyon `closed`, defterde düzeltme satırı `skipped/order_failed`, `trades.csv`'de satır yok; D + 1 saat'teki yeni sinyal aynı çiftte alınabilir. |
| L-6 | Aynı dakikada stop: dolum mumunun en düşüğü stopu da geçiyorsa işlem o dakikada `stop` ile kapanır; R ≈ −1 − maliyet. |
| L-7 | Eksik dakika: mumu olmayan dakikada dolum olmaz; süre yine D + ttl'de biter. |
| L-8 | Defter alanları: dolan işlemde `slippage_entry` ≤ 0 + yuvarlama (kayma yok), `fee_entry / (qty × entry_price)` ∈ {0,0002; 0,0005}; `entry_ts` = dolum mumunun açılışı. |
| L-9 | Emir beklerken `skip_flat` adımları atlamaz (çift "açılıyor" sayılır); `--no-skip-flat` ile aynı `trades.csv`. |
| L-10 | Bayrak denetimi: `--entry-mode limit --fill-model legacy_compat` → çıkış kodu `EXIT_ARG`; `--maker-fee 0.01` → `EXIT_ARG`. |
| L-11 | **Tarafsızlık:** `--entry-mode` verilmeyen ve `--entry-mode market` verilen iki koşu ile değişiklik öncesi kod (taban commit, `git archive` kalıbı) aynı `trades.csv`, `summary.json`, `open_at_end.json` baytlarını ve aynı `meta` sözlüğünü üretir (`git_commit`, `duration_s`, `argv` hariç); `meta`'da `entry_model` anahtarı yoktur. |
| L-12 | Kopya eşliği: `hashlib.sha256(inspect.getsource(PaperBroker._fill_entry))` sabitlenmiş değere eşit (üst sınıf gövdesi değişirse test kalır ve kopyanın eşlenmesini ister). Ayrıca `L` = piyasa dolum fiyatı ve oran = taker verildiğinde alt sınıfın açtığı pozisyon (`_Pos`, cüzdan, olay) üst sınıfınkiyle alan alan aynıdır. |
| L-13 | `planned_entry_at`: sayaçları değiştirmez; `frame(pair, D).last.planned_entry` ile aynı değeri verir; eksik mumda `None`. |

**Koşudan önce (keşif bölgesinde).** `python research/s2_run.py --trial S2-2 --explore 20230101-20230401` iki kez → bayt bayt aynı; sayaç toplamı = giriş denemesi sayısı.

**Tek koşu.** `python research/s2_run.py --trial S2-2` (id `s2_2_limit`; motor bayrakları: `--period 20210101-20260501 --tf 1h --fill-model native --strategy price_action_v1 --synthetic-rules --target-trade-risk 0.005 --entry-mode limit --maker-fee 0.0002 --limit-ttl-bars 1`). Rapor: `docs/ml/s2-2-raporu.md`; sabit tabloya ek olarak dolum oranı (dolan / denenen), boşluk dolumlarının payı ve süresi dolan emir sayısı (tam dönem, tek sayı) yazılır.

## 7. Kalan haklar ve birleşim kuralı

| Hak | Deneme | Durum |
|---|---|---|
| 1 | S2-1: 4 saatlik tetik | tanımlı (§5) |
| 2 | S2-2: limit giriş | tanımlı (§6) |
| 3 | S2-3: 1 günlük yön filtresi (parametresiz) | tanım eki bekliyor. Ek, S2-3 koşusundan önce bu belgeye tarihli not olarak yazılır; filtre kuralı yalnız 2024-01-01 öncesi veriye bakılarak seçilebilir; ayarlanabilir eşik içeremez. 2022'nin maliyet öncesi de ekside olması (denetim §4) bu denemenin gerekçesidir |
| 4 | S2-4: birleşim | kural aşağıda; ek tanım koşudan önce yazılır |
| 5–6 | S2-5/6: ikinci strateji ailesi (yedek) | S2-1 … S2-4 sonuçlarından sonra, tek tanım, koşudan önce ek |

**Birleşim kuralı (şimdiden sabit).** Bir bileşen (S2-1, S2-2, S2-3) S2-4'e ancak kendi denemesinde sınav penceresi ortalama net R'si tabanın sınav penceresi değerinden (v1b: −0,043 R; 0c'de doğrulanan rakam) en az **+0,03 R** yüksekse girer. S2-4 = kabul edilen bileşenlerin hepsi birlikte, tek sürüm, tek koşu. Kabul edilen bileşen yoksa S2-4 koşulmaz, hak yedeklere geçer. Tek bileşen kabul edilmişse S2-4 koşulmaz (o deneme zaten koşuldu).

**Kilitli döneme aday.** §2'yi geçen deneme yoksa aday yoktur: tur raporu yazılır, kilitli dönem açılmaz, yeni aileyle S3 ön kaydı yapılır (deneme sayısı birikerek artar). Birden fazla deneme geçerse aday, DSR'si en yüksek olandır; eşitlikte bileşeni az olan. Aday tektir ve kilitli dönem sorusu kullanıcıya gider.

## 8. Tarafsızlık: v1b ve canlı yol değişmez

Her S2 kod commit'inde (0a hariç; onun kuralı §3'te) şunlar geçmelidir:

1. `WP3_GOLDEN=1 pytest tests/test_wp3_golden.py` (K1, K2): `trades.csv`, `open_at_end.json`, `meta`, defter satırları tabanla aynı; `summary.json` §3'teki kuralla.
2. `pytest tests/engine/test_engine_compat_equity.py` (`NATIVE_GOLDEN`), `tests/engine/test_risk_ladder_impl.py::test_t28_backtest_digest_unchanged`.
3. `pytest tests/engine/test_engine_module_inventory.py tests/engine/test_engine_dependency_direction.py tests/engine/test_engine_05_spec.py tests/engine/test_engine_05_impl_smoke.py tests/engine/test_no_holdout_in_tests.py tests/engine/test_engine_holdout_lock.py`.
4. `git diff <önceki commit> --stat` çıktısında §5/§6 tablolarında sayılmayan `src/` dosyası yoktur; dondurulmuş dosyaların (§1 madde 8) hiçbiri yoktur.
5. `config/*.json` değişmez; `engine.py`, `order_manager.py`, `brokers/paper.py`, `brokers/binance_futures.py` S2 commit'lerinde değişmez.

Not: `engine.py`, `status.py`, `panel_data.py` üzerinde başka bir ekibin commit'lenmemiş pano işi var. S2 işleri bu dosyalara dokunmadığı için çakışma beklenmez; S2 commit'leri yalnız kendi dosyalarını yol adıyla ekler.

## 9. Sıra ve sorumluluk

| # | İş | Kim | Çıktı | Deneme hakkı |
|---|---|---|---|---|
| 0a | `fee_only` düzeltmesi + M testleri + altın test uyarlaması (§3) | uygulayıcı + bağımsız test yazarı | 1 commit | 0 |
| 0b | `research/s2_eval.py`, `research/s2_run.py` + E testleri (§4) | uygulayıcı + bağımsız test yazarı | 1 commit | 0 |
| 0c | Taban yeniden üretimi ve doğrulama (§4) | uygulayıcı | `var/backtests/s2_base_v1b/s2_eval.json`; rakamlar mentora | 0 |
| 1a | S2-1 kodu + H testleri + §8 | uygulayıcı + bağımsız test yazarı | 1 commit | 0 |
| 1b | S2-1 keşif denetimleri (paranoid, belirlenimcilik) | uygulayıcı | not | 0 |
| 1c | S2-1 tek koşu + rapor | uygulayıcı; yorum mentor | `docs/ml/s2-1-raporu.md` | 1 |
| 2a | S2-2 kodu + L testleri + §8 (1b–1c ile koşut yürüyebilir; tanım S2-1 sonucundan bağımsızdır) | uygulayıcı + bağımsız test yazarı | 1 commit | 0 |
| 2b | S2-2 keşif denetimleri | uygulayıcı | not | 0 |
| 2c | S2-2 tek koşu + rapor | uygulayıcı; yorum mentor | `docs/ml/s2-2-raporu.md` | 1 |
| 3 | S2-3 tanım eki → kod → tek koşu | mentor (tanım), uygulayıcı | ek + rapor | 1 |
| 4 | Birleşim kuralına göre S2-4 | mentor (ek), uygulayıcı | rapor | 0 ya da 1 |
| 5 | Tur değerlendirmesi: aday var mı; yoksa S2-5/6 ya da S3 | mentor | karar notu; aday varsa kullanıcıya kilitli dönem sorusu | — |

Uygulayıcı ve test yazarı ayrı ajanlardır; test yazarı yalnız bu belgeyi okur, uygulamayı okumadan testleri yazar. Belirsiz kalan her nokta koşudan önce mentora sorulur ve cevabı bu belgeye tarihli not olarak eklenir; uygulayıcı tanımı kendi yorumuyla tamamlamaz.

## 10. Dondurma kaydı

- Ön kayıt commit'i: bu belgeyi ekleyen commit (karması deneme raporlarına yazılır).
- `research/trial_registry.csv`: `S2-1_onkayit` ve `S2-2_onkayit` satırları bu commit'te eklendi (sonuç alanları boş). `research/build_registry.py` bu turda çalıştırılmaz (dosyayı `runs/` üzerinden yeniden üretir, elle eklenen satırları siler).
- Bu belge yazılırken görülen tek sonuç tabanın (v1b) dondurulmuş koşusudur; S2-1 ve S2-2 için hiçbir dönemde koşu yapılmadı.
