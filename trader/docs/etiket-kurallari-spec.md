# Etiket kuralları — belirtim (20 Kasım 2026)

**Karar (kullanıcı):** kâğıtta etiketler girişi etkiler. Kural yalnız "hayır" diyebilir; boyut, kaldıraç, limit, stop/hedef değişmez; yeni giriş açılmaz. Sert limitler, holdout mührü ve risk kademesi aynı. **Canlı/testnet davranışı değişmez**: `etiket_kurallari` yalnız `config/engine.paper.json`'da bulunur; `live`/`testnet`/`base` yapılandırmasında verilirse `ConfigError`, yoksa boştur. Desen: 1L3A `etiket_kurallari`.

## Yer ve sıra
`EntryGate.decide` kâğıt dalı: ... küme/hesap tavanı -> **ML filtresi** (`ml_filter`) -> **etiket kuralları** -> risk kontrolü. Kod: `src/trader_core/etiket_kurallari.py` (saf), `gates.EntryGate._etiket_karari`.

## Kurallar (eşikler `engine.paper.json` `etiket_kurallari`)
| Kural | Atlama kodu | Veri | Koşul |
|---|---|---|---|
| rejim karşıtı | `etiket_rejim` | sinyal satırının rejimi (`regime.py` sınıflaması) | long + `trend_down`, short + `trend_up` |
| uç duygu karşıtı | `etiket_duygu` | haber/duygu etiketi `duygu.deger` (0-100, 26 saatten taze) | long + değer ≤ `asiri_korku_max` (20), short + değer ≥ `asiri_acgozluluk_min` (80) |

Her kural `acik: false` ile yapılandırmadan kapatılabilir.

**Fail-open:** etiket/veri yok, bayat veya bozuksa kural engellemez; `etiket_veri_yok:<kod>` sayacı ve `status.json` `etiket_kurallari.kurallar.<kod>.veri_yok` bunu gösterir. Kural hatası girişi engellemez (log).

## Kayıt
Atlanan işlem karar satırı olarak yazılır (`skip_reason` = kural kodu, `veto_reason` = `gate:<kod>:<ayrıntı>`); mevcut karşı-olgu ("alınsaydı", `cf_outcomes`/`alinmayan_sonuc`) bunu otomatik kapsar. Defter şeması **7**: `skip_reason` sözlüğüne üç kod eklendi (üçüncüsü `etiket_kalabalik`, kural sonradan kaldırıldı; şema uyumu için sözlükte kalır, yeni karar üretmez) (6→7 geçişi; satırlar/id'ler korunur; raporlar 2..7 kabul eder).

## Otomatik kapat / izle / yeniden aç (histerezis)
Gece işi (`scripts/counterfactual_run.py`) `var/durum/etiket_kurallari_v1.json` dosyasını günceller; motor dosyayı okur (mtime önbellekli; yok/bozuk = hepsi açık).
- **Açıkken:** kuralın atladığı, sonuçlanmış son `pencere` (10) işlemin karşı-olgu net R toplamı **> +1R** (`kapat_esik_r`) ise kural kapanır ("atladığı işlemler kâr ederdi").
- **Kapalıyken izleme:** kural tetiklense bile giriş yapılır; karar `features.etiket_atlardi` taşır. Bu işlemlerin gerçek `r_multiple` değerleri izlenir.
- **Yeniden açma:** son 10 sonuçlanmış "atlardı" işlemin gerçek toplamı **< −1R** (`ac_esik_r`) ise kural yeniden açılır ("atlamak kazandırırdı").
- Yalnız son olaydan **sonraki** sonuçlar sayılır (eski kanıt aynı olayı tekrar tetiklemez); ±1R bandı gidip gelmeyi önler. Her olay (tarih, kapandı/açıldı, adet, toplam R, gerekçe) `gecmis` listesinde saklanır.
- Bildirim tek satır: günlük özet notu ve Telegram durum raporu — "Etiket kuralı kapatıldı: <sade ad> (atladığı işlemler kâr ederdi)" / "Etiket kuralı yeniden açıldı: <sade ad> (atlamak kazandırırdı)".

## Panel
ÖĞRENME sekmesi "Etiket kuralları" kartı: kural başına **Açık** / **Kanıta göre kapandı (tarih)** / **Kanıta göre yeniden açıldı (tarih)**, son 7 günde atladığı işlem sayısı, "alınsaydı" sonucu (R) ya da "Henüz ölçülemedi". Durum dosyası ve atlanan işlem yoksa kart gizlenir. Kaynak: `etiket_kurallari_v1.json` + `alinmayan_sonuc_v1.json`.

## Testler
`tests/test_etiket_kurallari.py` (kural mantığı, yapılandırma, kapat→izle→aç, histerezis, panel kartı, çeviriler), `tests/engine/test_etiket_kurallari_gate.py` (kapı entegrasyonu).


> **Kaldırıldı (CT/ML ayrılığı):** "kalabalık yönü" kuralı ve CT verisi bağlantısı tamamen çıkarıldı; bkz. `docs/motor/ct-ayrilik-spec.md`.
