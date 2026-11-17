# Üçüncü taraf bildirimleri

## regime-trading-bot (MIT)
- Kaynak: github.com/danny123-sudo/regime-trading-bot @ 508d7d9
- Uyarlanan dosyalar: `src/trader_core/indicators.py`, `src/trader_core/regime.py` (gösterge hesapları ve etiket arayüzü iskeleti; sınıflandırma koşulları bize ait).
- Copyright (c) 2026 danny123-sudo. MIT lisans metni ilgili dosyaların başında yer alır.

## freqtrade (GPL-3.0) — kaldırıldı (17 Kas 2026)
- Artık çalıştırılmaz ve kodu bu depoda yoktur; kendi motorumuz (`trader_engine`) kullanılır. Yalnız dondurulmuş sonuç dosyaları salt veri olarak `research/reference/freqtrade-2026.10/` altında saklanır (kod değil). Son referans commit: `bfe5185`.

## 1L3A panosu (kullanıcının kendi projesi)
- Kaynak: `1l3a-proje/motor/canli/pano.py` (kullanıcının kendi deposu; yalnız okunarak kopyalandı, çalıştırılmadı), 2026-11-16.
- Kopyalanan/uyarlanan: `src/trader_panel/static/panel.css` (CSS dizgisi, satır 172-327, değiştirilmeden) ve `src/trader_panel/static/panel.js` içindeki tema düğmesi ile tablo sıralama çekirdeği (JS dizgisi, satır 329-380).

## 1L3A pano Worker'ı ve yayın betiği (kullanıcının kendi projesi)
- Kaynak: `1l3a-proje/deploy/pano_worker.js` ve `deploy/pano_yayinla.sh` (kullanıcının kendi deposu; yalnız okunarak uyarlandı, çalıştırılmadı), 2026-11-16.
- Uyarlanan: `deploy/panel_worker.js` (Basic Auth, fail-closed, sabit zamanlı karşılaştırma; kullanıcı adı/secret adı değişti, kilitsiz yayın bayrağı çıkarıldı) ve `deploy/panel_yayinla.sh` (yayın akışı; kilitsiz kip ve parola-hash dosyası çıkarıldı).

## Aurum v2 (MIT)
- Kaynak: Aurum v2 `aurum/research/stats.py` ve `aurum/research/splits.py`, commit 49f073dfdb2f8831e2fcb39b321c1a02bc4bba5f (yerel klon `sselimgenc-oss/inceleme/tradingbot`; yalnız okunarak kopyalandı, çalıştırılmadı/kurulmadı), 2026-11-16.
- Kopyalanan: `src/trader_core/stats/stats.py` (PSR/DSR, MinTRL, Holm/BH düzeltmeleri, PBO/CSCV, durağan bootstrap) ve `src/trader_core/stats/splits.py` (purged/anchored walk-forward, purged K-fold, CPCV). Değişiklik: `scipy` kaldırıldı (normal dağılım cdf/sf/ppf/isf ve çarpıklık/basıklık `math`/`numpy` ile yeniden yazıldı); yeni bağımlılık eklenmedi. Dosya başlarında MIT başlığı vardır.
- Copyright (c) 2025 zero-was-here. MIT lisans metni ilgili dosyaların başındaki başlıkta atıf olarak yer alır.
- ML-G2 (17 Kas 2026): `aurum/labels/triple_barrier.py` satır 618-687 (aynı commit 49f073d, MIT; yalnız okunarak uyarlandı, çalıştırılmadı) -> `src/trader_ml/weights.py`: `average_uniqueness`, `uniqueness_weights`, `time_decay_weights` (AFML 4.4/4.5). Değişiklik: aralıklar 1 saatlik ızgarada zaman damgası, mean=1 normalizasyonu, `oldest` parametresi; yeni bağımlılık yok.

## LightGBM (MIT) — yalnız ML eğitim/araştırma tarafı
- Kod kopyalanmadı; `requirements-ml.txt` içinde tam sürüm (4.6.0) + hash sabitli isteğe bağlı bağımlılık. Motor ve bot süreci yüklemez; motor tarafı kendi ağaç okuyucumuzu (`src/trader_ml/treeeval.py`) kullanır. scipy yalnız lightgbm'in dolaylı bağımlılığıdır.
