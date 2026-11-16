# Üçüncü taraf bildirimleri

## regime-trading-bot (MIT)
- Kaynak: github.com/danny123-sudo/regime-trading-bot @ 508d7d9
- Uyarlanan dosyalar: `src/trader_core/indicators.py`, `src/trader_core/regime.py` (gösterge hesapları ve etiket arayüzü iskeleti; sınıflandırma koşulları bize ait).
- Copyright (c) 2026 danny123-sudo. MIT lisans metni ilgili dosyaların başında yer alır.

## freqtrade (GPL-3.0)
- Docker imajı olarak kullanılır (`freqtradeorg/freqtrade:2026.10`); kodu bu depoya kopyalanmamıştır.

## 1L3A panosu (kullanıcının kendi projesi)
- Kaynak: `1l3a-proje/motor/canli/pano.py` (kullanıcının kendi deposu; yalnız okunarak kopyalandı, çalıştırılmadı), 2026-11-16.
- Kopyalanan/uyarlanan: `src/trader_panel/static/panel.css` (CSS dizgisi, satır 172-327, değiştirilmeden) ve `src/trader_panel/static/panel.js` içindeki tema düğmesi ile tablo sıralama çekirdeği (JS dizgisi, satır 329-380).

## 1L3A pano Worker'ı ve yayın betiği (kullanıcının kendi projesi)
- Kaynak: `1l3a-proje/deploy/pano_worker.js` ve `deploy/pano_yayinla.sh` (kullanıcının kendi deposu; yalnız okunarak uyarlandı, çalıştırılmadı), 2026-11-16.
- Uyarlanan: `deploy/panel_worker.js` (Basic Auth, fail-closed, sabit zamanlı karşılaştırma; kullanıcı adı/secret adı değişti, kilitsiz yayın bayrağı çıkarıldı) ve `deploy/panel_yayinla.sh` (yayın akışı; kilitsiz kip ve parola-hash dosyası çıkarıldı).
