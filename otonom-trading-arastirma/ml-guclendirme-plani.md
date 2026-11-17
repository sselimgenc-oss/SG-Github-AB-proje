# ML güçlendirme planı (17 Kasım 2026 — mentor)

Kullanıcı talimatı (17 Kasım): *"Makina öğrenmesi kapanmayacak, fable makina öğrenmesi konusunda beğendiği repoların makina öğrenmesi bölümünü iyice araştırıp didik didik etsin, makina öğrenmesini canlıya kadar iyice geliştirip güçlendirmek asli görevi."*

Bu belge kod içermez; kodda hiçbir şey değiştirilmedi. `tasarim-kararlari.md` ile çelişirse o belge geçerlidir. İncelenen repolar çalıştırılmadı, kurulmadı; yalnız okundu. Kapı (19c) yeniden koşulmadı; kilitli dönem (2026-05 → 2026-10) okunmadı.

---

## A. Sade özet (teknik olmayan okuyucu için)

**"ML kapanmayacak" talimatını şöyle uyguluyorum:**

1. ML çalışması hiçbir aşamada bırakılmaz. Eski tasarımdaki "hiçbir tarif kapıyı geçemezse ML durur" cümlesi kalkar; yerine "tur biter, rapor yazılır, sonraki tur açılır" gelir.
2. Bir model kapıyı geçtiği gün kağıt hesabında gölge puanlama başlar (model her karara puan yazar, hiçbir kararı değiştirmez).
3. Paranızı koruyan kurallar aynen kalır, çünkü kaldırılmalarını istemediniz: kapı eşikleri sonuç görüldükten sonra gevşetilmez; her deneme koşudan önce deftere yazılır; kilitli dönem ML'ye açılmaz; ML yalnız işlem çıkarabilir (ekleyemez, boyut/stop değiştiremez); gerçek paraya dokunması için kapı + en az 6 hafta gölge + sizin Telegram onayınız gerekir.

**İlk denemenin (19c) neden kaldığı — dört neden, önem sırasıyla:**

1. **Veri çok az.** Modelin sınandığı dönem 240 gün, 624 işlem. Bu kadar veriyle kapıyı geçmek için filtrenin stratejinin başarısını yaklaşık üç katına çıkarması gerekiyordu. Gerçekçi bir iyileşme bu kadar kısa dönemde istatistiksel olarak kanıtlanamaz.
2. **Modele verilen bilgi zayıftı.** 33 özelliğin 11'i boştu ya da hep aynı değerdeydi (yatay piyasa özellikleri; strateji o dönemde yalnız trend kurulumu üretmiş). Kalanlar yalnız o coinin kendi oynaklığı, eğimi ve saat bilgisiydi. Piyasanın geneli (BTC/ETH durumu, fonlama, hacim, diğer coinlerin durumu) hiç yoktu.
3. **Soru yanlış soruluyordu.** Model "bu işlem 2R kazanır mı?" sorusunu öğreniyordu. Bu sorunun doğal cevabı %35 "evet". Kapı ise modelin adayların en az %30'una "%45 ve üstü" demesini istiyor. Bu, model çok iyi olsa bile neredeyse imkansız bir kombinasyondu. Ayrıca stratejinin kârının tamamı az sayıda çok büyük kazançtan geliyor (işlemlerin en iyi %5'i toplam kârın dört katını üretiyor, geri kalanı zararda); "2R oldu/olmadı" etiketi 2R ile 17R'ı ayıramıyor.
4. **Stratejinin girişinde yön bilgisi neredeyse yok.** 2R hedefi için şans oranı %33,3; strateji %35,3 yapıyor. Kâr girişten değil, kazananı uzun tutan çıkış kuralından geliyor. Filtre ancak "hangi piyasa koşulunda trend sürmez" bilgisini bulursa işe yarar.

**Ne yapacağız:**

- En büyük kaldıraç tarif değil, **veri**: geçmişi 2021'e kadar uzatmak (aynı 10 coin). Sınav dönemi 240 günden ~1500 güne çıkar; o zaman gerçekçi büyüklükte bir iyileşme kapıdan geçebilir.
- Modele piyasa bağlamı vermek: BTC/ETH durumu, fonlama, hacim, coinler arası görece güç, aynı anda kaç coinde sinyal çıktığı.
- Soruyu düzeltmek: "1R'a stoptan önce ulaşır mı?" (doğal cevap ~%45–50; kapının ızgarasıyla uyumlu).
- 8 tariflik bütçeyi bir kerede harcamamak: önce 5 tarif, 3'ü yedek. Her tarif kapıyı biraz daha zorlaştırır (deneme sayısı cezası), bu yüzden az ve iyi düşünülmüş tarif.

**Dürüst beklenti:** Canlıya kadar (aralık sonu) bir modelin dondurulmuş kapının tamamını geçme olasılığını %15–25 görüyorum. Geçerse gölge aralık ortasında başlar; etkin filtre en erken ocak sonu–şubat. Geçemezse canlı yine ML'siz (ya da gölgede) başlar, takvim etkilenmez ve ML çalışması ikinci turla sürer. ML, zayıf bir stratejiyi kurtaramaz; yalnız kötü koşulları ayıklayabilir.

**Sizden beklenen kararlar** Bölüm 6'da; en önemlisi geçmiş verinin 2021'e uzatılması.

---

## 1. Repo incelemesi (ML bölümleri)

Klonlar: `/home/user/sselimgenc-oss/inceleme/<ad>/` (`git clone --depth 1`, salt okuma). "Kod" = lisansı uygun; bizim koda monte edilir, kendi testimizle doğrulanır, `THIRD_PARTY_NOTICES.md`'ye yazılır. "Fikir" = kaynak satırı alınmaz, kendi kodumuz yazılır.

| Repo (commit) | Lisans | Karar |
|---|---|---|
| zero-was-here/tradingbot — Aurum v2 (`49f073d`) | MIT | **Kod** (seçili fonksiyonlar) |
| masterputra169/polymarket-btc-15-minutes (`7d668dc`) | MIT | Fikir (kodu sklearn'e bağlı; küçük parçalar kendi kodumuzla) |
| Dahshan228/FTMO-TradingBot (`8d1ecdf`) | MIT | Fikir |
| microsoft/qlib (`5435523`) | MIT | Fikir (çatı bağımlılığı yüzünden kod alınmaz) |
| asavinov/intelligent-trading-bot (`e5ef1bc`) | MIT | Fikir |
| MooreSi/forex-gold (`7c93c6e`) | **AGPL-3.0** | Yalnız fikir |
| freqtrade/freqtrade — FreqAI (`56a3326`) | **GPL-3.0** | Yalnız fikir |
| jerome-benoit/freqai-strategies (`ee79231`) | Lisans dosyası yok | Yalnız fikir |
| clawinfra/alphastrike (`4d08653`) | Lisans dosyası yok | Yalnız fikir |
| RayanBatada/autonomous-equity-trading-system (`099563c`) | "All Rights Reserved" | Yalnız fikir |
| stefanoviana/deepalpha (`b31d0a1`) | MIT | Fikir (HMM'i Aurum'dan alırız) |
| wyc-dev/MATS (`d76d633`) | Apache-2.0 | Fikir |
| garagesteve1155/PowerTrader_AI (`edb64c2`) | Apache-2.0 | Fikir (zaten kayıtlı) |
| khovala/moex-ml-trading (`9003eaf`), Netanelshoshan/freqAI-LSTM (`0a3a23a`), sleeyax/ml-crypto-trading-bot (`ab316f2`) | MIT / MIT / yok | Alınacak bir şey yok (aşağıda) |

Klonlanmayanlar (yalnız rapordan biliniyor, bu turda incelenmedi): stefan-jansen/machine-learning-for-trading (çok büyük; yöntem kaynağı olarak AFML zaten Aurum üzerinden geliyor), Marigold/universal-portfolios (ML değil; fikri ders servisine kayıtlı), RL repoları (FinRL, TensorTrade, PGPortfolio — tasarım §8 gereği kapsam dışı).

### 1.1 Aurum v2 (MIT) — ana kaynak

Zaten monte edilenler: istatistikler (`aurum/research/stats.py`), bölmeler (`research/splits.py`), üçlü bariyer. Bu turda **ek olarak** alınmaya değer bulduklarım:

| Ne | Dosya:satır | Neden | Alış |
|---|---|---|---|
| Ortalama teklik ağırlığı (`average_uniqueness`, `uniqueness_weights`) | `aurum/labels/triple_barrier.py:618-643` | Aynı mumda 2–6 coinde aday var (1234 işlemin 467'si kümeli); etiket pencereleri 72 mum örtüşüyor. Örtüşen örnekler bağımsız sayılmamalı. Bizde ağırlık yalnız kaynak × yaş (`trader_ml/models.py:16`). | Kod |
| Eşzamanlılık sayacı (`num_concurrent_events`) | `triple_barrier.py:607-615` | Yukarıdakinin yardımcısı; ayrıca "aynı anda kaç aday açık" özelliği için | Kod |
| Getiri-atıf ağırlığı (`return_attribution_weights`) | `triple_barrier.py:646-665` | Büyük hareket taşıyan örneklere daha çok ağırlık; kârımızın kuyrukta olması yüzünden denemeye değer (tarif r05) | Kod |
| Teklik üzerinden zaman azalması (`time_decay_weights`) | `triple_barrier.py:668-687` | Bizdeki 270 gün yarı ömrün AFML karşılığı; uzun derlemde eski yılları kontrollü zayıflatır | Kod |
| Meta-etikette süre dolunca "getiri işareti" seçeneği | `triple_barrier.py:538-558` | Bizde süre dolan = 0. Alternatif etiket tanımı | Fikir (etiket üreticimiz ayrı) |
| Platt eğimi `a ≥ 0` kısıtı | `aurum/strategies/ml.py:399-423` | Bizim `fit_platt` (`trader_ml/models.py:52-66`) kısıtsız; sinyalsiz bir önceki dilimde eğim negatif çıkarsa sıralamayı **tersine çevirir**. 19c'de lojistik puanın en düşük %20'si en yüksek %20'sinden iyi çıkmış olabilir (Bölüm 2.6). | Fikir + kendi kodumuz (yeni tarif tanımının parçası) |
| Beceri kapısı: doğrulama AUC'sinin z değeri, etkin örnek sayısı = teklik toplamı | `ml.py:810-837` | Rapora tanı satırı: "model yazı-turadan iyi mi", örtüşmeye göre düzeltilmiş | Fikir (rapor satırı; geçti/kaldı rolü yok) |
| Verimlilik oranı, varyans oranı | `aurum/features/regime.py:113-134` | Trend mi gürültü mü ölçüsü; trend takipçisi stratejinin asıl ihtiyacı | Kod |
| Parkinson / Garman-Klass / Rogers-Satchell / Yang-Zhang oynaklık | `aurum/features/volatility.py:208-264` | Kapanış-kapanış oynaklığından daha az gürültülü; hepsi OHLC'den | Kod |
| HAR-RV oynaklık tahmini | `aurum/models/volatility.py:522-692` | "Beklenen oynaklığa göre şimdiki oynaklık" özelliği | Kod (yalnız tarif r04'te) |
| Gauss HMM, **yalnız ileri süzme** (`filter`) | `aurum/models/regime.py:40-435`, `:374` | Rejim olasılığı özelliği; geriye dönük yumuşatma (smoothing) geleceği sızdırır, yalnız `filter` kullanılır | Kod (yalnız tarif r04'te; her dilimde yalnız eğitim verisiyle uydurulur) |
| Çok zaman dilimli hizalı yeniden örnekleme | `aurum/features/multi_timeframe.py:104-170` | Bizim `_htf` ile çapraz kontrol | Fikir |

**Alınmayanlar:** `CalibratedGBM` (`ml.py:219`) sklearn `HistGradientBoosting` kullanır — bağımlılık kararımıza aykırı. `bet_size_from_probability` (`ml.py:182`) ve Carver ölçekleme — model boyut belirleyemez (tasarım §4). RL (`aurum/rl/`) — §8.

### 1.2 polymarket-btc-15-minutes (MIT) — küçük veriyle meta-etiket disiplini

`backtest/ml_training/mltrain/` altı. Bizimkiyle aynı problem: birkaç yüz çözülmüş bahis, al/alma kararı.

| Ne | Dosya:satır | Bizde |
|---|---|---|
| Çıkarım kodu elle yazılır, kütüphaneye karşı testle sabitlenir | `meta_eval.py:76-104` | Zaten var (ağaç okuyucu + eşleme testi) |
| Sınıf ağırlığı **kullanılmaz** (kalibrasyonu bozar) | `meta_eval.py:107-121` | Tarif kuralı olarak yazılır |
| Sabit sütun koruması (std ≈ 0 → ölçek 1) | `meta_eval.py:128-135` | Bizde var; ek olarak **koşu öncesi ölü özellik reddi** gerekir (aşağıda) |
| AUC için bootstrap güven aralığı | `meta_eval.py:172-204` | Rapora tanı satırı (kendi kodumuz, durağan bootstrap ile) |
| Sözlü hüküm: "EDGE / MIXED / NO EDGE", boş sonuç meşru | `meta_eval.py:394-431` | Rapor dili |
| Çıkarımda sabit olan özelliği aramadan **önce** sıfırlamak | `weights.py:168` (`build_feature_weights`) | **Koşu öncesi özellik sağlık kontrolü**: boş/sabit/canlıda üretilemeyen özellik varsa koşu başlamaz. 19c'de 11 ölü özellik bu yüzden fark edilmedi. |
| Yakınlık ağırlığı (yarı ömür) + seans ağırlığı, ortalaması 1'e normalize | `weights.py:69-166` | Normalizasyon fikri (etkin örnek sayısı sabit kalsın) |
| Karar zamanına göre sıralı, ambargolu, sınırı aşan piyasayı test tarafından tamamen atan bölme | `meta_labeling.py:343-412`, `cv.py:25` | Zaten var |
| Platt + evre bazlı kalibrasyon | `calibration.py:64-181`, `:264` | Evre bazlı kalibrasyon alınmaz (az veri) |

### 1.3 MooreSi/forex-gold (AGPL-3.0 — yalnız fikir, satır alınmaz)

`backend/src/services/reversal_engine/`. Bizim 19c sonucunu en iyi açıklayan repo.

- **"Hiçbir şey alma"ya yakınsayan kapı filtre değildir, üreticiye dair hükümdür** (`meta_label.py:1-30` belge notu). Onların R-regresyon kapısı her yeniden eğitimde daha çok engelleyip %11'e inmiş. Bizim 19c de %0,2'ye indi. Dersi: yön kararı stratejide kalır, model yalnız "almaya değer mi" der ve etiket ikili olur.
- **Etiket = "işlem kendi yürütme maliyetini aştı mı"** (`meta_label.py:62-76`), "kazandı mı" değil. Maliyet ölçülmemişse etiket yok (sıfır varsayılmaz).
- **Şans kıyası (kumarbazın iflası):** yönsüz rastgele yürüyüş, stop SL ve hedef TP uzaklığında hedefe `SL/(SL+TP)` olasılıkla önce varır (`chance_benchmark.py:1-30`). Bizde 2R hedef için şans %33,3. Rapora tanı satırı olarak eklenecek (Bölüm 2.4).
- **Kanıt çıtası:** modelin alacağı işlemlerin ileri dönem ortalaması için **küme-dayanıklı t** (aynı harekete binen işlemler tek kanıt), en az işlem ve küme sayısı, zamanın iki yarısında da pozitif (`edge_model.py:105-146`). Bizim kapıda günlük toplulaştırma aynı işi görüyor; "iki yarı pozitif" tanı satırı olarak eklenebilir.
- **Gürültü olduğu ölçülen özellikler atılır:** son 20 sonucun kazanma oranı, hesap düşüşü, başka modelin çıktısı (`edge_model.py:59-76`). Dersi: **sonuca dayalı defter tutma özellikleri (son işlemler kazandı mı, hesap durumu) özellik listemize girmez**; piyasaya dair olgular girer.
- Teklik ağırlığı + arındırılmış/ambargolu dilimler + "yazı-turayı geçemiyorsa silahlanmaz, görüş bildirmez" (`meta_label.py:112-131`).

### 1.4 FTMO-TradingBot (MIT) — yeniden eğitim ve terfi mekaniği

- Zamanlanmış yeniden eğitim → hazırlık dizini → kapı → **bozulma tavanı** (yeni model görevdekinden %10'dan fazla kötüyse, kapıyı geçse bile reddedilir) → nöbetçi dosyalı atomik terfi → canlıya yeniden yükleme sinyali: `scripts/retrain_scheduler.py:59`, `:149-182`, `:188-220`, `:229-250`. Bizde ML-4'ün tasarımı aynı; "bozulma tavanı" §3.4 adım 6'yı ("görevdekinden kötü değil") zaten karşılıyor. Kilit dosyası ve atomik taşıma fikirleri ML-4 iş paketine not edildi.
- CPCV + PBO + DSR ile ayrı sağlamlık hükmü (ROBUST / CAUTION / FRAGILE): `scripts/cpcv_validation.py:397-520`, kapıya bağlanışı `src/model/validate.py:60-120`. Bizde var.
- Oynaklığa uyarlanan etiket ölü bölgesi, normalleştirici **genişleyen medyan** (ileriden sızıntı yok): `src/features/labels.py:10-50`. Dersi: bir eşik veriye göre ölçekleniyorsa yalnız o ana kadarki veriyle.

### 1.5 microsoft/qlib (MIT) — fikir kaynağı

- **Alpha158 özellik ailesi** (`qlib/contrib/data/loader.py:96-275`): mum gövdesi/fitil oranları (KMID, KLEN, KUP, KLOW), ROC, pencere içi konum (QTLU/QTLD, RSV), en yüksek/en düşüğün kaç mum önce olduğu (IMAX/IMIN), yükselen mum payı (CNTP/SUMP), fiyat-hacim korelasyonu (CORR/CORD), hacim oynaklığı (VSTD/WVMA). Hepsi OHLCV'den, ölçek bağımsız. Bizim 33 özellikte **hacim ve mum yapısı hiç yok**; küçük bir alt küme (8–10 tane) kendi kodumuzla yazılacak.
- **IC ölçümü** (`qlib/contrib/eva/alpha.py:160-184`): günlük kesitsel IC ve sıra IC. Bizim günlük toplulaştırılmış Spearman ile aynı aile.
- **DoubleEnsemble** (`qlib/contrib/model/double_ensemble.py:140-220`): kayıp eğrisine göre örnek yeniden ağırlıklama + karıştırmaya dayalı özellik seçimi, alt modellerin ortalaması. Tam hali bizim veriye fazla; **alt model ortalaması** fikri tarif r06'da.
- **AverageEnsemble / RollingEnsemble** (`qlib/model/ens/ensemble.py:65-125`): standardize edip ortalama.
- **DDG-DA** (`qlib/contrib/rolling/ddgda.py:100-433`): dağılım kaymasına göre eğitim örneklerini yeniden ağırlıklayan meta-model. Bizim ölçekte aşırı; yaş ağırlığı yeterli. Kayıt: ileride.
- **Çevrimiçi model yönetimi** (`qlib/workflow/online/`): ML-4 ile aynı desen.

### 1.6 intelligent-trading-bot (MIT)

- "İlk hangisi kesildi" etiketleri (`src/itb/common/gen_labels_highlow.py:126-160`): ufuk içinde üst eşiğe mi alt eşiğe mi önce dokundu — bizim bariyer etiketinin eşdeğeri, birden çok eşik düzeyiyle. Dersi: **aynı adaya birden çok hedef düzeyi (1R, 1,5R, 2R) etiketi derlemde saklanır** (ucuz), tarif hangisini kullanacağını önceden yazar.
- Tepe/dip etiketleri (`gen_labels_topbot.py:70-176`): kendi aday üreten ML-5 için; şimdi değil.
- Özellik/etiket/eğitim/sinyal aşamalarının ayrı betik ve tek yapılandırma ile yürütülmesi: bizde var.

### 1.7 FreqAI (GPL-3.0 — yalnız fikir)

- Yakın veriye üstel ağırlık (`freqtrade/freqai/data_kitchen.py:408-415`): bizde var.
- DI eşiği (`freqai_interface.py:574`, `:710`): eğitim dağılımı dışındaki adayı reddet — ML-2 işi, kendi kodumuz.
- Tasarım §2'deki fikirler (çok zaman dilimi, bağlı çiftler, kaydırılmış mumlar) aynen geçerli; "bağlı çiftler" 19c'de **uygulanamadı** (motor bağlamı yok) — Bölüm 2.2.

### 1.8 Diğerleri

- **freqai-strategies / QuickAdapter** (lisans yok — fikir): uç nokta (zigzag) etiketleri ve etiket dönüştürücü (`quickadapter/user_data/strategies/LabelTransformer.py:205-235`), Optuna ile sürekli arama. Bizde sürekli hiperparametre araması bilerek yok (deneme sayısını sınırsız büyütür). Alınacak fikir yok.
- **alphastrike** (lisans yok — fikir): fonlama, açık pozisyon (OI) ve long/short oranından **karşıt** sinyaller (`src/features/alternative_signals.py:390-415`, `:417-460`, `:462-500`): "fiyat yükselirken OI artıyor = yeni para giriyor", "aşırı fonlama = kalabalık taraf". Özellik fikri olarak tarif r07'de. Model başına canlı isabet izleyici ve rejime göre ağırlık (`src/ml/quality_tracker.py:302-470`): kayma alarmı (ML-2) için fikir.
- **autonomous-equity-trading-system** (tüm hakları saklı — fikir): tohum topluluğu — aynı tarif farklı tohumlarla, ham tahminlerin aritmetik ortalaması, deterministik (`src/sma/model/ensemble.py:66-120`). Tarif r06.
- **deepalpha** (MIT): saf numpy HMM (`regime_detector.py:28-272`) ve gözlem kurucu (`:295`). Aurum HMM'i daha titiz; oradan alınır. TFT/GNN/Transformer modelleri 2 GB sunucu ve veri hacmimiz için uygun değil.
- **MATS** (Apache-2.0): aynı örneklem üzerinde "temel özellikler" ile "temel + yeni özellikler"in ileri dönem ρ kıyası (`scripts/verify-shadow-trainability.py:1-40`); farklı örneklem kümelerinin sahte başarısızlık üretmesine karşı. Dersi: yeni özellik bloğunun katkısı **aynı satırlarda** ölçülür.
- **PowerTrader_AI** (Apache-2.0): desen belleği + ağırlıkların sonuca göre güncellenmesi (`pt_trainer.py:114-176`). Fikri (kanıtı tutmayan zayıflar) zaten kayıtlı.
- **moex-ml-trading, freqAI-LSTM, ml-crypto-trading-bot:** onlarca "optimize edilmiş" backtest betiği / tek LSTM / Python kodu yok. Alınacak bir şey yok; aşırı uyum örneği.

---

## 2. Tanı: 19c neden kaldı

Kaynak: `trader/docs/ml/19c-kapi-raporu.md`, `trader/research/ml/19c/oof_predictions.parquet`, `trader/research/ml/candidates_v1b_native.parquet` (salt okuma; en geç aday 2026-04-29, kilitli dönem yok). Kapı yeniden koşulmadı; aşağıdakiler betimleyici tablolardır.

**Açıklama yükümlülüğü:** Bu tanıda derlemin tamamında (sınav dilimleri dahil) tek tek özelliklerin sonuçla korelasyonuna baktım. Bu, kayıtsız bir bakıştır ve aşağıdaki tarifleri etkiler. Dürüst muhasebe için deneme defterine `diag-19c-univariate` satırı eklenmesini öneriyorum (deneme sayısı 4 → 6). Bu bir sıkılaştırmadır.

### 2.1 Örneklem ve güç (en ağır neden)

| Ölçü | Değer |
|---|---|
| Sınav dönemi (OOF) | 240 gün, 624 alınan işlem, 197 işlem günü |
| Filtresiz stratejinin sınav dönemindeki günlük kâr serisi | ortalama 0,32 R/gün, std 4,13, t = **1,20** |
| IC kapısında t ≥ 2 için gereken günlük sıra korelasyonu | ρ ≥ **0,14** (197 gün) |
| Net R farkının standart hatası (adayların %50'si tutulursa) | ≈ 0,08 R; +0,10 R fark ancak ~1,3 sigma |
| DSR ≥ 0,95 için filtreli serinin gereken t değeri | n_trials=4: ≈ 2,8 · n_trials=12: ≈ 3,2 · n_trials=20: ≈ 3,5 |

Sonuç: mevcut derlemde kapıyı geçmek için filtrenin, işlem sayısını azaltırken stratejinin t değerini 1,2'den ~3'e çıkarması gerekir. İşlem başı gerçekçi bir IC (0,05–0,08) bunu 240 günde gösteremez. Aynı strateji gücüyle 1500 günlük sınav döneminde filtresiz taban tek başına t ≈ 3,0 verir ve ρ ≥ 0,05 IC kapısı için yeter. **Kapı doğru çalışıyor; veri kısa.** Ayrıca her yeni tarif (2 model) DSR çıtasını yükseltir: 8 tarifin hepsini harcamak çıtayı 2,8'den 3,5'e taşır.

### 2.2 Özellikler

- 33 özelliğin **11'i ölü**: `f_rr`, `f_edge_dist_atr`, `f_range_width_atr`, `f_entry_to_rh_atr`, `f_entry_to_rl_atr` tamamen boş; `f_is_t1`, `f_reg_range`, `f_reg_volatile`, `f_rh_touches`, `f_rl_touches` sabit. Neden: derlemde yalnız T1 (trend) kurulumu var (1261/1261); yatay piyasa özellikleri hiç dolmuyor.
- `f_side_sign`, `f_reg_trend_up`, `f_reg_trend_down` aynı bilginin üç kopyası (long yalnız yükselen trendde, short yalnız düşen trendde).
- Kalan ~20 özellik: çiftin kendi oynaklığı (4 ölçü + 4 `atr_ratio` gecikmesi), eğimler, saat/gün, 3 gecikmeli getiri. **Piyasa bağlamı yok:** BTC/ETH, fonlama ve `bars_since_exit` motor canlıda sağlayamadığı için listeden çıkarılmıştı (tasarım §11 karar 2a). Hacim, mum yapısı, coinler arası görece güç, aynı mumdaki sinyal sayısı hiç tanımlı değil.
- Tek tek bakıldığında hiçbir özelliğin etiketle sıra korelasyonu |0,08|'i geçmiyor. Oynaklık özelliklerinin net R ile −0,16 korelasyonu **yapaydır**: stop olan işlemlerin kendi içinde −0,66, kazananlarda −0,06; oynaklığın "kazandı mı" ile korelasyonu 0,00. Yani bu, zarar eden işlemlerin −0,94 R ile −0,98 R arasındaki maliyet kaynaklı sıralamasıdır; ekonomik değeri yok. Not: net R'a doğrudan regresyon yapan tarif bu mekanik ilişkiyi "öğrenir"; IC'yi şişirebilir ama net R farkı üretmez (Bölüm 3, r05 riski).

### 2.3 Etiket ve eşik ızgarası uyumsuzluğu (yapısal)

- Etiket: 2R'a stoptan önce, 72 mum içinde. Taban oranı %35,3 (sınav dilimlerinde %38).
- Kapı: eşik [0,45 – 0,70] ızgarasında, adayların ≥ %30'u alınacak. Yani kalibre olasılığın 70. yüzdeliği ≥ 0,45 olmalı. Taban %35 iken bu, en iyi %30'luk dilimin sınırında bile 1,25 kat isabet demek (AUC ≈ 0,65 düzeyi) — işlem filtresi için gerçekçi değil. 19c'de olasılıkların %99'u 0,45'in altındaydı (lojistik: medyan 0,366, %99'luk 0,449).
- Ek yapısal yük: ilk dilimde (satırların %25'i) Platt = özdeşlik ve eşik sabit 0,50. Taban %35 iken ham olasılık 0,50'yi neredeyse hiç geçmez; ilk dilim fiilen "hiç alma" olur.
- Bu bir eşik gevşetme gerekçesi **değildir**. Çözüm tarif tarafındadır: taban oranı ızgaranın içine düşen bir etiket (1R'a stoptan önce; şans oranı %50, maliyet sonrası beklenen ~%45–50). O etiketle sinyalsiz bir model herkese ~0,47 der, hepsi alınır, fark 0 çıkar ve model 3b'de (net R farkı ≥ +0,10) **yine kalır** — kapının koruması bozulmaz; yalnız dejenerasyon ortadan kalkar.

### 2.4 Hedef: kâr kuyrukta, etiket kuyruğu görmüyor

| Ölçü (1234 alınan işlem) | Değer |
|---|---|
| Ortalama / medyan net R | +0,076 / −0,94 |
| net R > 0 oranı | %32,7 |
| Çıkış: ilk stop / iz süren stop | 621 (ort. −0,98 R) / 611 (ort. +1,15 R, medyan +0,42 R) |
| Toplam kâr | +94 R |
| En iyi %5 işlemin toplamı | **+412 R** (kalan %95: −318 R) |
| 5 R'da kırpılmış ortalama | **−0,03 R** |
| 72 saatten uzun tutulan işlemler | %0,8 (10 işlem), toplam **+74 R** |
| Etiket=1 iken ortalama net R / etiket=0 iken | +1,70 / −0,81 |
| 2R etiket oranı / şans oranı (1/3) | %35,3 / %33,3 (z = 1,5) |
| Long / short ortalama net R | −0,05 (490) / +0,16 (744) |
| Aylık ortalama | −0,32 ile +0,52 arasında, işaret sık değişiyor |

Okuma: (a) Girişin yön becerisi şansa çok yakın; kâr, çıkış kuralının yakaladığı seyrek büyük trendlerden geliyor. (b) İkili 2R etiketi 2R ile 17R'ı aynı sayıyor; kârı belirleyen şeyi öğrenemiyor. (c) Kârın 10 işlemde toplanması, her model için "o 10 işlemi atma" riskini büyütür: adayların yarısını rastgele atan bir filtre bile kuyruğu kaybedip stratejiyi zarara çevirebilir. Bu, filtrenin işlem başı değil **rejim düzeyinde** (trendin sürdüğü haftalar / sürmediği haftalar) çalışması gerektiğine işaret eder. (d) Aylık sonuçlar piyasa geneli rejimle sallanıyor; rejim bilgisi (BTC trend kalitesi, genişlik) en makul eksik bilgidir.

### 2.5 Rejim ve dilim kararsızlığı

Dilim IC'leri −0,10 / +0,08 / +0,05 / +0,01: işaret tutarlı değil, büyüklükler gürültü düzeyinde. Tek özelliklerin çeyrek bazlı korelasyonları da işaret değiştiriyor (ör. `f_slope_4h`: +0,06 / −0,11 / −0,17 / +0,01). 16 aylık tek bir piyasa döneminde öğrenilen ilişki sonraki döneme taşınmıyor. Daha uzun ve çeşitli geçmiş (2021 boğa, 2022 ayı, 2023 yatay) hem güç hem rejim çeşitliliği için gerekli.

### 2.6 Küçük teknik bulgular

- **Platt eğimi kısıtsız** (`trader_ml/models.py:52-66`). Lojistik puanın beşte birlik dilimlerinde en düşük iki dilim en iyi net R'ı vermiş (+0,06 / +0,58 / −0,06 / +0,01 / +0,03): sinyal yok, ama negatif eğimli bir kalibrasyon böyle bir sıralamayı tersine de çevirebilirdi. Yeni tariflerde `a ≥ 0`.
- LightGBM ham puanının yayılımı çok dar (std 0,057): erken durdurma birkaç ağaçta kesmiş; model fiilen sabit.
- Yalnız 27 atlanan aday var (25 `risk_denied`, 2 `order_failed`). "Alınmayan sinyalden öğrenme" bu derlemde yok hükmünde; stratejinin kendi iç elemeleri aday olarak yazılmıyor.
- Örnek ağırlıkları eşzamanlılığı hesaba katmıyor (aynı mumda 2–6 aday).
- Koşu öncesi "ölü özellik" kontrolü yok.

### 2.7 Hüküm

Önem sırası: **(1) örneklem/güç** — tek başına yeterli neden; **(2) bilgi eksikliği** — bağlam özellikleri yok, 11 özellik ölü; **(3) etiket–ızgara uyumsuzluğu** — iyi bir modelde bile 3a/3g'yi düşürürdü; **(4) hedefin kuyruk yapısı ve girişte yön bilgisinin azlığı** — filtrenin kazanabileceği payı küçültür; **(5) rejim kararsızlığı**. Model ailesi (lojistik / LightGBM) neden değil.

---

## 3. Ne yapılacak

### 3.0 Deneme bütçesi politikası

- Tur 1: en fazla 8 tarif hakkı var; **5'i koşulur, 3'ü yedek kalır.** Tarifler sırayla, her biri koşudan önce `research/ml_trial_registry.csv`'ye yazılır. Deneme sayısı asla sıfırlanmaz.
- Her tarifin kaydında: özellik listesi (ad ad) ve kod özeti, etiket, ağırlık kuralı, model ayarları, kalibrasyon kuralı, derlem sha256, yürüyen pencere tanımı. Kayıttan sonra hiçbiri değişmez.
- Kayıttan önce **güç ön hesabı** yazılır: o derlem ve deneme sayısıyla kapıyı geçmek için gereken t ve IC. Gereken etki gerçek dışıysa tarif koşulmaz (deneme harcanmaz).
- Bir tarif geçerse sonraki tarifler durur; geçen model gölgeye gider. Geçen modelin üstüne "daha iyisini arama" yeni turdur.
- Tur biterse rapor yazılır, ML **durmaz**: Tur 2 biriken kağıt/canlı kayıtları, karşı-olgusal derlem ve yeni veri kaynaklarıyla açılır.

### 3.1 Önce derlem v2 (tarif değil, ön koşul)

`v1b-native-long`: aynı 10 çift, aynı strateji sürümü, aynı asıl mod ve kağıt riski; dönem **2021-01-01 → 2026-04-30**. Tahmini ~4.500 alınan işlem, sınav dönemi ~1.500 gün.

- Yürüyen pencere yeniden yazılır (tasarım §3.3 buna izin veriyor; yeni deneme sayılır): genişleyen pencere, ilk eğitim ≥ 12 ay, **tam 4 sınav dilimi** (kapıdaki "tam 4 dilim, ≥ 3 pozitif" şartı aynen), her dilim ~13 ay; arındırma 72 mum, ambargo 24 mum.
- Derlemde her adaya 1R / 1,5R / 2R bariyer sonuçlarının üçü de yazılır (tarif hangisini kullanacağını önceden seçer).
- Risk: 2021–2024'te v1b'nin filtresiz tabanı negatif çıkabilir. Bu da bilgidir (strateji planı için de); ML açısından filtreli beklenti > 0 şartı o zaman daha zor olur.
- Uzatma mümkün olmazsa (veri indirilemezse) tarifler mevcut derlemde koşulur ama Bölüm 2.1 gereği geçme olasılığı çok düşüktür; bu durumda yalnız r02 ve r03 koşulur, bütçe korunur.

### 3.2 Sıralı tarif listesi (ön kayda hazır)

Hepsinde ortak: yalnız filtre (çıkarır); model çifti lojistik + sığ LightGBM (`LGBM_PARAMS` aynen, aksi yazılmadıkça); ileri yönlü Platt, **eğim a ≥ 0**; sınıf ağırlığı yok; koşu öncesi özellik sağlık kontrolü (boş/sabit özellik varsa koşu başlamaz); en fazla 40 özellik; sonuca dayalı defter özellikleri (son işlemler kazandı mı, hesap durumu) yasak; kapı ve eşikler aynen.

| # | Kimlik | Varsayım | Özellikler | Etiket / ağırlık | Model | Neden geçebilir | Maliyet |
|---|---|---|---|---|---|---|---|
| 1 | `ml1-r02-long-ctx-1r` | Eksik olan piyasa bağlamı ve doğru soru; uzun veriyle ölçülebilir | **Tam olarak `trader_core.ml_features_v2.R02_FEATURE_NAMES` (40 özellik; fazlası/eksiği yok).** **Çekirdek (15):** `f_atr_ratio`, `f_stop_dist_atr` (= \|planlanan giriş − planlanan stop\| / ATR14 1s), `f_side_sign`, `f_slope_1h/4h/1d`, `f_slope_4h_aligned`, `f_vol_1h/4h/1d`, `f_atr_pct_1h`, `f_hour_sin/cos`, `f_dow_sin/cos`. **Bağlam (25):** `f_btc_slope_4h/1d`, `f_btc_vol_4h/1d`, `f_eth_slope_4h/1d`, `f_eth_vol_4h`, `f_btc_er_24/96`, `f_breadth`, `f_rank_ret_24h/7d`, `f_corr_btc_7d`, `f_funding_last`, `f_funding_sum3`, `f_same_bar_signals`, `f_vol_z_24/168`, `f_range_atr`, `f_body_ratio`, `f_close_pos`, `f_dist_hi20/lo20/hi50/lo50_atr`. **Dışarıda bırakılanlar:** ETH 1g oynaklık (`f_eth_vol_1d`, 40 sınırı + BTC ile yüksek korelasyon), açık aday sayısı ve son çıkıştan bu yana mum sayısı (motor defter durumu; ön kayıtta yok) | **1R / 72 mum**; ağırlık = kaynak × teklik × zaman azalması (en eski 0,3) | Sabit çift | Taban oranı ızgaranın içinde; bağlam bilgisi ilk kez veriliyor; güç 6 kat | Derlem v2 + özellik kodu + motor bağlamı (gölge için): 4–5 iş günü |
| 2 | `ml1-r03-long-regime8` | Filtre işlem değil rejim düzeyinde çalışmalı; az özellik = az aşırı uyum (PBO) | Yalnız 8 piyasa düzeyi özellik: BTC 4s/1g eğim, BTC verimlilik oranı (96), BTC varyans oranı, BTC 1g oynaklığının 90 günlük yüzdeliği, genişlik, aynı mumdaki sinyal sayısı, `side_sign` × BTC 1g eğim | 1R / 72 mum; r02 ağırlıkları | Sabit çift (LightGBM derinlik 2, yaprak 100 — kayıtta yazılır) | 2.4(c)-(d): kâr/zarar rejimle sallanıyor; 8 özellik 4 dilimde kararlı kalabilir | r02'nin koduyla +0,5 gün |
| 3 | `ml1-r04-long-volmodel` | Oynaklık rejimi ve trend kalitesi daha iyi ölçülürse sinyal güçlenir | r02 listesi; gecikmeli getiri/`atr_ratio` kopyaları yerine: Yang-Zhang ve Parkinson oynaklık (24/96), HAR-RV tahmini ÷ gerçekleşen oynaklık, çiftin verimlilik ve varyans oranı, 2 durumlu HMM'in süzülmüş "sakin trend" olasılığı (BTC ve çift) | 1R / 72 mum; r02 ağırlıkları | Sabit çift | Aurum'un hazır, test edilmiş hesapları; trend takibi için doğrudan ilgili ölçüler | Aurum montajı + test: 2–3 gün. HMM her dilimde yalnız eğitim verisiyle uydurulur |
| 4 | `ml1-r05-long-tail` | Kârı kuyruk belirliyor; büyüklüğü gören hedef daha iyi sıralar | r02 listesi | Hedef: 5 R'da kırpılmış gerçek net R'ın **sıra dönüşümü** (regresyon); ağırlık = teklik × getiri-atıf. Olasılık: puan → 1R etiketine ileri Platt | Ridge (lojistik yerine) + LightGBM regresyon (Huber) | 2R/17R ayrımını görür | Hat'a regresyon model türü + paket/okuyucu desteği + eşleme testi: 2 gün. **Risk:** 2.2'deki maliyet kaynaklı mekanik sıralamayı öğrenip IC'yi şişirebilir; bu yüzden 4. sırada |
| 5 | `ml1-r06-long-bag` | Küçük veride tek ağaç modeli kararsız; ortalama varyansı düşürür | r02 listesi (birebir) | r02 ile aynı | Lojistik + **5 tohumlu LightGBM torbası** (`feature_fraction` 0,5, `bagging_fraction` 0,8; ham puanların ortalaması; yaprak değerleri 1/5 ile ölçeklenip tek ağaç listesinde paketlenir, motor okuyucusu değişmez) | r02 "kıl payı" kaldıysa kararlılık farkı kapatabilir | 1 gün. r02 hiç sinyal göstermediyse **koşulmaz** (kural önceden yazılı: r02 bağlayıcı IC ≤ 0 ise atlanır) |
| 6 (yedek) | `ml1-r07-long-positioning` | Kalabalık taraf ve yeni para akışı trendin sürüp sürmeyeceğini söyler | r02 listesi + açık pozisyon (OI) 24s değişimi, OI değişimi × fiyat değişimi işareti, long/short hesap oranı, fonlamanın 30 günlük yüzdeliği | r02 ile aynı | Sabit çift | Fiyat dışı, bağımsız bilgi kaynağı | Yeni veri kaynağı (Bölüm 3.3-C); arşiv 2021'e uzanmıyorsa derlem kısalır → güç düşer; veri doğrulanmadan kayda geçmez |
| 7 (yedek) | `ml1-r08-long-side-split` | Long ve short adayların başarı koşulları farklı (2.4: long −0,05, short +0,16) | r02 listesi | r02 ile aynı | Yön başına ayrı model (lojistik + LightGBM), tek puan sütununda birleşir | Etkileşimleri ağaç derinliği 4 yakalayamıyorsa | 1 gün; örneklem ikiye bölünür — düşük öncelik |
| 8 (yedek) | — (ayrılmış) | Strateji v1.1 çıkarsa modelin yeni adaylarla yeniden eğitimi (tasarım §7 notu: yeni deneme sayılır) ya da Tur 1'de en iyi tarifin kağıt + karşı-olgusal kayıtlarla genişletilmiş derlemde tekrarı | — | — | — | — | — |

Sıra gerekçesi: r02 en yüksek ön olasılıklı ana bahis (üç ana nedeni birden giderir). r03 farklı bir düzlemde (rejim kapısı) ve en az aşırı uyum riskli; r02 ile aynı kodu kullanır. r04 aynı bilgi ailesinin daha iyi ölçümü. r05 hedefi değiştirir ama bilinen bir tuzağı var. r06 koşullu.

Etki yönü için gerçekçi hedef: işlem başı IC 0,06–0,08 → adayların ~%50–60'ı tutulduğunda +0,08–0,12 R fark. Kapı +0,10 R istiyor; marj dar. Bu yüzden beklenti %15–25.

### 3.2.1 r02/r03 ön kayıt tanımları (mentor, 17 Kas)

Bu bölüm r02 ve r03 için belirsiz bırakılabilecek her tanımı önceden sabitler; koşu sonucu görüldükten sonra değiştirilmez. Kod karşılığı: `trader_core/ml_features_v2.py`, `trader_ml/weights.py`, `trader_ml/models.py`, `trader_ml/pipeline.py`.

1. **Özellik listeleri.** r02 = tam olarak `R02_FEATURE_NAMES` (40). `f_eth_vol_1d`, açık aday sayısı ve son çıkıştan bu yana mum sayısı dışarıdadır. r03 = `R03_FEATURE_NAMES` (8).
2. **Evren.** Yalnızca derlemin 10 çifti; genişlik, sıra ve aynı mum sayımı bu 10 çift üzerinden hesaplanır. Geçerli çift sayısı 5'ten azsa genişlik ve sıra NaN'dır.
3. **Genişlik.** Son kapanmış 4s mumun kapanışı EMA20(4s)'in üstünde olan çiftlerin oranı (payda: geçerli bayrağı olan çift sayısı).
4. **Sıra.** 24s ve 168s kapanıştan kapanışa getirinin 10 çift içindeki yüzdelik sırası; short adaylarda `1 − sıra`.
5. **`f_same_bar_signals`.** Aynı `ts`'de yerel v1b adayı olan **ayrı çift** sayısı: alınmış ya da alınmamış, iki yön dahil; karşı-olgusal (counterfactual) ya da artırılmış satır yok. Motorda bu, iki geçişli değerlendirme gerektirir (bkz. G5).
6. **Fonlama.** `ts`'den kesinlikle önceki olaylar (`side="left"`); `f_funding_last` = son olay, `f_funding_sum3` = (ts−24s, ts) aralığındaki olayların toplamı; ikisi de yönle işaretli; olay zamanları G3'ün yaptığı gibi saate yuvarlanır. Giriş sütunu `funding_rate` (ya da `rate`), yoksa hata.
7. **1g bağlam.** Sabit 200 günlük geri bakış (yalnız kapanmış 1g mumlar; daha eski geçmiş sonucu değiştirmez): BTC/ETH/çift 1g eğim ve oynaklık ile BTC 1g oynaklık yüzdeliği (son 90 gün, en az 30 geçerli değer, payda = NaN olmayan değer sayısı). BTC varyans oranı q=4, pencere 96; verimlilik oranı 24 ve 96.
8. **Etiket.** `label_1r`, 72 mum; `label_end_ts_1r` arındırma, ambargo ve teklik aralıklarında kullanılır; çözülmemiş satırlar atılır.
9. **Ağırlık.** kaynak × teklik (tüm çiftlerde havuzlanmış, ortalama 1) × doğrusal azalma (en eski 0,3; aynı `ts`'li olaylar eşit, satır sırasından bağımsız); **her dilimin arındırma sonrası eğitim satırlarında** hesaplanır, tüm tabloda değil. Tarif anahtarı: `WEIGHT_SCHEME = "uniq_decay"` (r01 varsayılanı `age_decay` değişmedi).
10. **Platt.** `a ≥ 0` (`PLATT_NONNEG_SLOPE = True`). Eğimi kısıtlanan dilimde p = önceki satırların taban oranı (sabit); kısıtlanan dilim sayısı sayılır ve raporda yazılır. Paket düzeyi kalibrasyon kısıtlanırsa **paket üretilmez** (`CalibrationClamped`).

**G5 zorunlulukları (bu tanımların motor/sarmalayıcı karşılığı; kodda henüz yok):**

- Motor 1g bağlam için **en az 200 günlük 1s (veya 1g) geçmiş** sağlamalıdır (bugünkü 1500 saatlik ≈ 62 gün pencere yetmez); aksi hâlde canlı özellikler eğitimdekilerle aynı olmaz.
- `trader_ml` sarmalayıcısı her çift çerçevesinde ve fonlamada `assert_pre_holdout` çağırır (kilitli dönem koruması).
- `f_same_bar_signals` için **iki geçişli** değerlendirme: önce tüm çiftlerde aynı mum sinyalleri sayılır, sonra özellikler hesaplanır.

### 3.3 Tarif dışı iyileştirmeler ve gereken altyapı

| # | İyileştirme | Ne kazandırır | Gereken motor/altyapı işi | Ne zaman |
|---|---|---|---|---|
| A | **Geçmiş verinin 2021'e uzatılması** (1m + mark + fonlama, 10 çift) | Güç 6 kat; rejim çeşitliliği | Binance'in herkese açık arşivinden, sağlama toplamı doğrulamalı toplu indirme aracı (feed tarafı); bu ortam Binance'ten 451 alıyor → sunucuda ya da erişimi olan makinede çalışır. Disk: birkaç GB. Sonra 19b derlem oluşturucusu aynı kodla uzun dönemde koşar; 50 etiket elle kontrol | İndirme aracı 27 Kasım'dan önce; indirme sunucu açılınca |
| B | **Motor bağlam özellikleri** (tasarım §11 karar 2b) | Bağlam özellikleri canlıda da üretilebilir; gölgenin ön koşulu | `StrategyContext`'e salt okunur: BTC/ETH mumları, 10 çiftin rejim durumu (genişlik ve kesitsel sıra için), fonlama, son çıkış zamanı, aynı mumdaki aday sayısı. Eğitim/canlı eşitlik testi (aynı mum → aynı özellik, 1e-9). `precomputed.py`'ye `model=` geçişi (karar 3) | Kağıt 1.–2. hafta; **gölgeden önce zorunlu** |
| C | **OI ve long/short oranı verisi** | Fiyat dışı bağımsız bilgi (r07) | Feed'e yeni toplayıcı (5 dk'lık OI ve oran; yalnız okuma uçları) + `market.sqlite`'ta yeni tablo; geçmiş için herkese açık arşivin kapsamı önce doğrulanır (ezberden varsayılmaz) | Kağıt 2.–3. hafta; canlı toplama hemen başlarsa Tur 2 için veri birikir |
| D | **Karşı-olgusal derlem (gece işi, 25a)** | Atlanan kararların varsayımsal sonucu; modelin kendi seçimiyle körleşmesini önler | Planlandığı gibi. Ek: stratejinin **kendi iç elemelerinde kıl payı kalan adayları** ("yakın ıska") planlanan giriş/stop ile karar olayı olarak yazması; eğitimde 0,3–0,5 ağırlık, sınavda **kullanılmaz** (bağlayıcı evren yalnız alınanlar) | 25a kağıt 1. hafta; yakın ıska Tur 2 |
| E | **Meta-etiket hijyeni** | Örtüşen örnekler bağımsız sayılmaz | Aurum teklik/zaman azalması montajı (`trader_ml`), testler makale örneklerine karşı | 27 Kasım'dan önce (küçük) |
| F | **Rejim koşullaması** | 2.4(d) | r03 ve r04 özellikleri; kapı raporuna rejim bazlı döküm tablosu (yalnız tanı) | Tariflerle birlikte |
| G | **Kalibrasyon** | Sıralama tersinmez; olasılıklar ızgarayla uyumlu | Platt `a ≥ 0` (tarif tanımı); rapora güvenilirlik tablosu (5 dilim: tahmin / gerçekleşen); izotonik alınmaz (az veride basamaklanır) | Tariflerle birlikte |
| H | **Topluluk** | Varyans azaltma | r06 (tohum torbası). Lojistik + LightGBM sıra ortalaması Tur 2 adayı | Kağıt 3. hafta |
| I | **Haftalık yeniden eğitim** | "Kendi kendine öğrenme" | Canlıda her mumda ağırlık güncellemesi yok (tasarım §8 aynen). Kapıyı geçen tarif için: kağıt döneminde **sunucu dışı, elle, haftalık** yeniden eğitim provası (aynı tarif → deneme sayılmaz), her seferinde kapı + görevdekine karşı kontrol. Sunucuda otomatik hali ML-4 (kilit dosyası, hazırlık dizini, atomik terfi — FTMO fikirleri) | Model geçtikten sonra |
| J | **Koşu öncesi korumalar** | 19c'deki 11 ölü özellik tekrarlanmaz | `trader_ml`: özellik sağlık kontrolü (boş/sabit/kopya → koşu reddi); güç ön hesabı betiği (`min_track_record_length` zaten `trader_core.stats`'ta) | 27 Kasım'dan önce (küçük) |
| K | **Rapor tanı satırları** (geçti/kaldı rolü yok) | Sonucu okumayı kolaylaştırır | Şans kıyası (1/(1+hedef R)); AUC + bootstrap aralığı; iki yarı ortalaması; kuyruk payı (en iyi %5); "filtre en iyi 10 işlemden kaçını attı" | 27 Kasım'dan önce (küçük) |
| L | **Kayma alarmı + DI** (ML-2) | Gölgede modelin bozulduğunu görmek | PSI, DI, son 30 puanlı adayın IC'si; kendi kodumuz | Gölge başlamadan |
| M | **Telegram `/onayla`** (paket özetine bağlı) | Etkinleştirmenin ön koşulu | Tasarım §11 karar 1 | Kağıt haftaları, ML-2 çıkışından önce |

---

## 4. İş takvimi (bugün 17 Kasım Salı → canlı 28 Aralık – 4 Ocak)

Kurallar: ana yapı (faz planı 13–20) her zaman önce. Aynı anda en fazla 2 Sonnet uygulayıcı; 30 Kasım'a kadar ML'ye **en fazla bir şerit**, o da ana yapı işi beklemiyorsa. ML işleri 27 Kasım akşamı kesilir; bitmeyen kağıt dönemine kayar. ML hiçbir tarihte kağıdı ya da canlıyı bekletmez.

### 4.1 30 Kasım'dan önce (17–27 Kasım) — yalnız boş şerit varsa

| Paket | İçerik | Dokunduğu yer | Süre | Bağımlılık |
|---|---|---|---|---|
| **ML-G1** Korumalar ve tanı | J + K: özellik sağlık kontrolü, güç ön hesabı, rapor tanı satırları. Kapı eşikleri ve geçti/kaldı mantığı **değişmez** (testle sabitlenir) | `trader_ml/` (gate rapor kısmı, pipeline ön kontrol), testler | 1 gün | Yok |
| **ML-G2** Ağırlıklar ve etiket seçenekleri | E: Aurum teklik + zaman azalması montajı; etiket üreticide 1R/1,5R/2R sütunları; Platt `a ≥ 0` seçeneği (varsayılan kapalı, tarif açar); `THIRD_PARTY_NOTICES.md` | `trader_ml/labels.py`, `models.py`, testler | 1,5 gün | Yok |
| **ML-G3** Geçmiş indirme aracı | A'nın aracı: arşivden indirme, sağlama toplamı, mevcut biçime dönüştürme, boşluk raporu; kilitli dönem dosyalarına dokunmaz | `trader_engine/feed` (ya da `scripts/`), testler (ağsız, örnek dosyayla) | 1,5 gün | Sunucu/erişim: indirme sonra |
| **ML-G4** Özellik üretici v2 (araştırma tarafı) | r02/r03 özellikleri bayrak arkasında; her özellik için "yalnız kapanmış mum" testi; motor tarafı henüz yok | `trader_core/ml_features.py` (bayraklı), testler | 2 gün | ML-G2 ile paralel olabilir |

Öncelik: G1 → G3 → G2 → G4. 27 Kasım'a yalnız G1 ve G3 yetişirse yeterli.

### 4.2 Kağıt dönemi

| Hafta | Şerit 1 | Şerit 2 | Çıktı |
|---|---|---|---|
| **1. hafta (30 Kas – 6 Ara)** | **ML-G5** Motor bağlamı (B) + eğitim/canlı eşitlik testi + `precomputed.py` `model=` | **25a** gece işi (D) · kalan G2/G4 · geçmiş indirme (sunucuda) | Derlem v2 girdileri hazır; gece işi çalışıyor |
| **2. hafta (7 – 13 Ara)** | **ML-G6** Derlem v2 kurulumu (19b aynı kod, uzun dönem; manifest, sha256, 50 etiket elle kontrol) → mentor: yürüyen pencere + r02 ön kaydı → **r02 tek koşu** | **ML-G7** OI/oran toplayıcı (C), canlı toplama başlar · Telegram `/onayla` (M) | r02 kapı raporu; r03 ön kaydı ve koşusu (aynı hafta, r02 raporundan sonra) |
| **3. hafta (14 – 20 Ara)** | r04 için Aurum oynaklık/HMM montajı → ön kayıt → koşu | Kayma alarmı + DI (L); r05 için regresyon desteği (yalnız r02–r04 kaldıysa) | r04 (ve varsa r05) raporu. **Bir tarif geçtiyse:** paket → `shadow` (en erken bu hafta) |
| **4. hafta (21 – 27 Ara)** | r06 (koşullu) · Tur 1 raporu | Haftalık yeniden eğitim provası (I), model varsa · canlı geçiş kontrol listesinde ML satırı | Tur 1 raporu; canlıya `off` ya da `shadow` ile giriş kararı |
| **Canlı (28 Ara – 4 Oca)** | ML'de kod değişikliği yok; gölge varsa sürer | — | Canlı filtre etkin olmadan başlar |
| **Ocak** | Gölge 6 haftasını doldurur (en erken ocak sonu) → ML-2 çıkış ölçütü → kullanıcı Telegram onayı → `active` | Tur 2 hazırlığı: karşı-olgusal + kağıt/canlı kayıtları, OI verisi, yakın ıska adayları | En erken etkin filtre: ocak sonu – şubat |

Her tarif adımında sıra sabit: güç ön hesabı → deftere kayıt (commit) → tek koşu → rapor → `tasarim-kararlari.md` satırı. Yeniden koşu yok.

Sonnet paketleri için ortak kabul ölçütleri: `ml_mode=off` kararları v1b ile birebir (mevcut test yeşil); kilitli dönem koruması testleri yeşil; kapı eşik sabitleri (`trader_ml/config.py` `GATE`, `THRESHOLD_GRID`, `MIN_TAKEN_FRAC`, `BURN_IN_THRESHOLD`) diff'te **değişmemiş**; yeni bağımlılık yok (scikit-learn, scipy motora girmez).

---

## 5. Değişmeyen kurallar (kayıt için)

1. Kapı eşikleri (§1, §3.4) sonuç görüldükten sonra gevşetilmez; yalnız sıkılaştırılabilir. Bu planda hiçbir eşik değişikliği önerilmiyor.
2. Her tarif koşudan önce `research/ml_trial_registry.csv`'de. Başarısız denemeler silinmez; deneme sayısı sıfırlanmaz.
3. Kilitli dönem 2026-05-01 → 2026-11-01 ML tarafından okunmaz (geçmişi 2021'e uzatmak buna dokunmaz).
4. ML yalnız çıkarır. Boyut, kaldıraç, stop, hedef belirlemez; risk kilidini gevşetemez.
5. `active` = mevcut kapı + ≥ 6 hafta gölge (≥ 150 puanlı aday, ≥ 50'si alınmış, ileri dönemde fark > 0 ve IC > 0) + kullanıcının Telegram onayı + canlının ilk 2 haftası geçmiş.
6. Üçüncü taraf kod: MIT/Apache ise seçili parça, kendi testimizle; GPL/AGPL/lisanssız/"tüm hakları saklı" ise yalnız fikir. Hiçbir repo çalıştırılmaz, bağımlılıkları kurulmaz.
7. Canlıda RL yok, LLM model eğitmez, her mumda ağırlık güncellemesi yok.

Güncellenmesi gereken belgeler (bu işte dokunulmadı): `ml-faz-tasarimi.md` §0 madde 4 ve §7 ML-1 satırındaki "geçemezse faz durur" → "tur raporu yazılır, sonraki tur açılır"; §3.3 yürüyen pencere (derlem v2); `faz-plani.md` 25b; `tasarim-kararlari.md`'ye bu talimatın ve yorumunun kaydı.

---

## 6. Kullanıcı kararı gerekenler

| # | Karar | Mentor önerisi | Neden size soruluyor |
|---|---|---|---|
| 1 | "ML kapanmayacak" yorumu: ML çalışması durmaz, turlar halinde sürer; ama koruma kuralları (Bölüm 5) aynen kalır ve canlı, kapıyı geçmiş model yoksa ML'siz başlar | Onay | Yazılı "faz durur" kuralını değiştiriyor; talimatınızı doğru anladığımı teyit için |
| 2 | Geçmiş verinin 2021-01'e uzatılması (Binance'in herkese açık arşivinden, sunucuda indirme; birkaç GB) | **Evet** — planın en önemli adımı | Yeni veri indirme; ayrıca v1b'nin 2021–2024 sonucu da görünür olur (kötü çıkabilir; strateji planını da ilgilendirir) |
| 3 | Etiketin "2R" yerine "1R'a stoptan önce" olması | Evet | Eşik değişmiyor ama tasarımda "etiket tanımı sabittir" yazıyordu. Şeffaflık: bu değişiklik kapının [0,45–0,70] ızgarasıyla uyumu sağlar; sinyalsiz model yine kalır |
| 4 | Tanı sırasında derlemin tamamına baktığım için deneme defterine `diag-19c-univariate` satırı (deneme sayısı 4 → 6) | Evet (sıkılaştırma) | Kapıyı biraz zorlaştırır; dürüst muhasebe |
| 5 | OI / long-short oranı için yeni veri toplayıcı (yalnız okuma) | Evet, kağıt 2. haftada | Yeni dış veri kaynağı |
| 6 | Tur 1'de 8 yerine 5 tarif koşup 3'ünü yedekte tutmak | Evet | Onaylı "en fazla 8" bütçesinin kullanımı |

Karar 2 "hayır" olursa: Tur 1 mevcut 16 aylık derlemde yalnız r02 ve r03 ile koşar; geçme olasılığı %5'in altına iner ve asıl ilerleme kağıt/canlı kayıtları biriktikçe Tur 2'de olur.
