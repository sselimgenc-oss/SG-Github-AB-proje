# PBO raporu + holdout mührü — belirtim (19 Kasım 2026, Faz 2b)

Bu iş **yalnız rapordur**. Sunucuda çalışmaz, karar kapısı değildir, hiçbir işlemi ya da kurulumu engellemez. Araştırma ortamında (bu repo, `var/history`) çalışır.

## 1. Holdout mührü
Holdout dönemi `2026-05-01 → 2026-11-01`, `trader_engine.holdout.HOLDOUT` (donuk dosya; yalnız içe aktarılır).

`research/holdout_muhur.py muhurle` komutu:
- `var/history/*.feather` dosyalarının her birinde yalnız holdout aralığındaki satırları seçer.
- Her dosya için şunları hesaplar: satır sayısı, ilk ve son zaman damgası, satırların kanonik baytlarının (sütun sırası sabit, `to_numpy().tobytes()` + sütun adları + dtype) sha256 değeri.
- Bu değerler dışında **hiçbir içerik okunmaz, yazdırılmaz, istatistiği alınmaz**. Fiyat, getiri, ortalama yoktur.
- Sonucu `research/holdout/muhur.json` dosyasına yazar. İçerik:
  - mühür tarihi,
  - holdout aralığı,
  - dosya başına `{dosya, satir, ilk_ts, son_ts, sha256}`,
  - tüm dosyaların birleşik sha256 değeri,
  - `acildi: false`.
- Mühür bir kez basılır. Dosya varsa komut reddeder; `--yeniden` bayrağı yoktur.

`research/holdout_muhur.py dogrula` komutu aynı hesabı yeniden yapar ve mühürle karşılaştırır. Çıktısı yalnız eşit/farklı ve farklı olan dosya adlarıdır. Bu komut, holdout verisinin sonradan değişmediğini gösterir.

`research/holdout_muhur.py ac --aday-kumesi <ad> --gerekce "<metin>"`:
- Yalnız bir aday kümesi "yayına hazır" denince **bir kez** kullanılır.
- `muhur.json` içinde `acildi: true` yapar ve açılış kaydını (zaman, aday kümesi, gerekçe, birleşik sha256) ekler. İkinci çağrıda reddeder.
- Komut değerlendirme yapmaz; yalnız kaydı tutar. Holdout değerlendirmesi ayrı bir iştir, bu belirtimin dışındadır.

Günlük iş, eğitim ve araştırma kodu holdout satırlarını okumaz. Bu zaten `holdout.check_holdout` ve kilit testleriyle korunuyor. Bu iş ek olarak bir test ekler: `muhurle` ve `dogrula` dışında hiçbir research betiği `holdout_muhur` ile holdout verisi okumaz.

## 2. PBO raporu
**Aday kümesi:**
- Şu an kâğıtta aktif kural ailesi kurulumları: `config/engine.paper.json` içindeki `arms`.
- M1/LightGBM önerici aday sürümleri: `research/paper_models.csv`, `research/pa_proposer_build.py` çıktıları ve ilgili kayıtlar.

**Denemeler:** bu kümenin walk-forward / CSCV denemeleri. Kaynaklar:
- `research/trial_registry.csv`, `research/ml_trial_registry.csv`, `research/runs/*.json`;
- gerekirse yalnız holdout öncesi veriyle yeniden üretilen günlük getiri serileri.

Aynı deneme ailesindeki tüm konfigürasyonlar sayılır; elenenler dahil, çünkü PBO deneme sayısına duyarlıdır.

**Hesap:**
- `trader_core.stats.pbo_cscv` kullanılır. `n_splits=16`; yerleşik `trader_ml.gate.pbo_for` deseni izlenir.
- Kurulum ailesi başına bir PBO hesaplanır, bir de tüm küme için.
- Her biri için:
  - konfigürasyon sayısı ve T (gün sayısı),
  - en iyi IS konfigürasyonunun OOS sıralaması,
  - Deflated Sharpe (`deflated_sharpe`, deneme sayısıyla),
  - kısa yorum: PBO < 0,5 ise "aşırı uyum riski düşük-orta", aksi "yüksek". Eşik bilgi amaçlıdır, karar değildir.

**Veri sınırı:** yalnız `2026-05-01` öncesi. `check_holdout` her veri okumasında çağrılır.

**Çıktı:** `docs/ml/pbo-raporu.md`. İçerik:
- tablo,
- yöntem,
- deneme kaynakları,
- eksik kalan aileler ve nedeni (ör. "deneme kaydı yok").

Makine özeti `research/holdout/pbo_ozet.json` dosyasına yazılır.

**Yeniden üretilebilirlik:** `research/pbo_rapor.py` tek komutla raporu yeniden yazar (seed sabit).

## 3. Sınırlar
- Donuk dosyalara dokunulmaz: `trader_engine/holdout.py`, `trader_ml/{features,features_v2,labels,guards,config}.py`, `trader_core/{ml_features,ml_features_v2,signals,regime,indicators}.py`, `scripts/build_corpus_v2.py`, `research/ml_build_candidates.py`. `research/build_registry.py` çalıştırılmaz.
- Yeni bağımlılık eklenmez.
- Testler sentetik veriyle yazılır. Holdout tarihleri ve `var/history` yazımı yalnız `test_no_holdout_in_tests.py` kurallarına uygun dosyalarda geçer. Mühür testleri `tmp_path` altındaki sentetik dosyalarla yapılır.
- Sunucu birimi, Telegram ya da pano işi yoktur.

## Ek: strateji/ayar/kod hash'i, on kayit gunlugu, budama (1L3A'dan uyarlandi)

- `holdout_muhur.py` `kayit_olustur` / `on_kayit_yaz` / `gunluk_dogrula` / `kayit_dogrula`: strateji listesi, ayar ve kod dosyalarinin sha256'si ile git commit'i, hash zincirli yalniz-ekleme JSONL gunlugune (`research/holdout/on_kayit_gunlugu.jsonl`) holdout degerlendirmesinden ONCE yazilir. `muhurle(..., kayit=...)` istege bagli "kayit" anahtari ekler; `dogrula` bu alanlari okumaz, mevcut muhur ESIT kalir.
- Budama (kapi gecerse zayif stratejiyi setten cikarma) UYGULANMADI: holdout sonucunu okuyup muhurlu seti degistirir, muhurun "icerige dokunma" anlamiyla celisir. Karar insana ve yeni on kayda birakilir.
- Yalniz rapor/kayit araci; canli/paper motoruna etkisi yoktur.
