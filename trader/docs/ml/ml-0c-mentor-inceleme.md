# ML-0c mentor incelemesi

Kapsam: `src/trader_ml/`, `scripts/ml_gate.py`, `tests/ml/`, `requirements-ml.txt`. Yollar `trader/` köküne göredir.
Bu belge incelemeyi özetle olduğu gibi kaydeder; her maddenin altındaki "Durum" satırı yapılan düzeltmeyi gösterir.

## A — Düzeltilmesi zorunlu

1. **Platt kalibrasyonu ve Brier karşılaştırması aynı satırlarda** (`pipeline.py:78`, `gate.py:195-198`).
   Platt, tüm OOF satırlarına uyduruluyor; kapı Brier'i aynı satırlarda ölçüyor ve eğitim taban oranıyla
   kıyaslıyor. Taban oranı zamanla kayarsa becerisiz bir model, kalibrasyon sayesinde eğitim taban oranını
   yener. Düzeltme: Platt ve eşik yalnız ileri yönlü (k. dilim için yalnız dilim < k ve etiketi/çıkışı o
   dilimin başlangıcından önce bilinen satırlarla) uydurulur; ya da Brier OOF taban oranıyla kıyaslanır.
   Tercih: ileri yönlü uydurma.
2. **Atlanan dilimler "4 dilimin 3'ü" kuralını gevşetiyor** (`pipeline.py:48`, `gate.py:187`). Eğitim satırı
   < 100 olan dilim sessizce atlanıyor, `need` küçülüyor. Düzeltme: kapı yalnız tam 4 dilim
   değerlendirildiyse ve >= 3'ü pozitifse geçer.
3. **RED ya da eşiksiz paket yüklenebilir kaydediliyor** (`pipeline.py:101-105`, `package.py:88`).
   Düzeltme: meta'ya `gate_passed` yazılır; `load_package` `gate_passed` false/null ise açık hatayla reddeder.
4. **`exit_ts` yok; `f_bars_since_exit` canlıda görünmeyen bilgiye dayanıyor** (`schema.py:33`,
   `features.py:126`). Alınmayan adayların bariyer bitişini canlı görmez. Düzeltme: şemaya `exit_ts`
   (gerçek çıkış) eklenir, kilitli dönem için doğrulanır; `f_bars_since_exit` yalnız alınan işlemlerin
   gerçek çıkışlarından, aday anında bilinenlerle hesaplanır.
5. **IC t-istatistiği ve DSR aynı mumdaki çiftleri bağımsız sayıyor** (`gate.py:132-134,182,210`).
   Düzeltme: hesap öncesi zaman kümesine (gün) göre toplulaştırma.
6. **`n_trials` varsayılanı** (`pipeline.py:64,148`). Zorunlu olmalı; kural: n_trials = kayıtlı tarif sayısı
   x 2 model, küçük bir kayıt dosyasından (`research/ml_trial_registry.csv`) okunur.

### Hükümler (karar verildi)
- Stres maliyeti "+5 bp" TARAF BAŞINADIR (tur başına 10 bp); `gate.py:75` buna göre düzeltilir.
- `requirements-ml.txt` kalır; numpy dahil tüm geçişli bağımlılıklar hash'le sabitlenir
  (`pip install --require-hashes -r requirements-ml.txt` çalışmalı).
- Eşik bulunamazsa (null) model reddedilir; bu kural aynen kalır.

## B — Ucuzsa şimdi, değilse listele
- `models.py:84`: erken durdurma eğitim/doğrulama ayrımında arındırma (purge) yok.
- `gate.py:74`: `cost_r` şemada yalnız komisyon+kayma olarak tanımlanmalı (stres hesabı buna dayanıyor).
- `resources.py:19`: thread ortam değişkenleri numpy içe aktarılmadan önce ayarlanmalı; `--research`
  verilmedikçe `--limits` varsayılan olmalı.
- `guards.py:26` pencere kuralı: SONRAYA bırakıldı (not).

## Uygulama durumu
Hepsi uygulandı; testler `tests/ml/test_review_fixes.py` içinde.
- A1: `pipeline.forward_calibrate` — Platt ve eşik ileri yönlü (önceki dilimler, bilgisi test başlangıcından önce
  bilinenler). İlk dilim: özdeşlik + sabit 0,50 eşik. Paket Platt/eşiği tüm OOF'a uydurulur, kapıda skorlanmaz.
- A2: kapı yalnız tam 4 dilim ve >= 3 pozitif IC ile geçer (`GATE.required_folds/ic_min_pos_folds`).
- A3: `meta.gate_passed`; `load_package(require_gate=True)` false/null ve eşiksiz paketi `PackageError` ile reddeder.
- A4: şemada `exit_ts` (alınan satırlarda zorunlu, kilitli dönem doğrulaması); `f_bars_since_exit` yalnız alınan
  işlemlerin gerçek çıkışlarından.
- A5: IC t ve DSR günlük (UTC) toplulaştırmayla (DSR: günlük PnL serisi, n = gün sayısı).
- A6: `n_trials` zorunlu; `research/ml_trial_registry.csv` x 2 model (`trader_ml/registry.py`). CLI `--n-trials`
  yalnız defterden büyük değer kabul eder.
- Hükümler: stres +5 bp/taraf; `requirements-ml.txt` numpy dahil hash'li (geçici venv'de `--require-hashes` ile doğrulandı).
- B: erken durdurma purge'ü (`fit_lgbm(ts=, label_end=)`), `cost_r` tanımı (şema), thread env `_threads.preset_threads`
  (scripts/ml_gate.py, numpy'dan önce), CLI'da limitler varsayılan, `--research` ile kapanır.
- Sonraya: `guards.py:26` pencere kuralı.

