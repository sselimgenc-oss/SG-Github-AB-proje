# Etiket kuralları — belirtim (20 Kasım 2026; 21 Kasım 2026 sadeleştirme: SİLME kararı)

**Karar (kullanıcı):** kâğıtta rejim etiketi girişi etkiler. Kural yalnız "hayır" diyebilir; boyut, kaldıraç, limit, stop/hedef değişmez; yeni giriş açılmaz. Sert limitler, holdout mührü ve risk kademesi aynı. **Canlı/testnet davranışı değişmez**: `etiket_kurallari` yalnız `config/engine.paper.json`'da bulunur; `live`/`testnet`/`base` yapılandırmasında verilirse `ConfigError`, yoksa boştur.

## 21 Kasım 2026: silinenler (kullanıcı kararı)
- **Duygu / haber etiketi** (Fear & Greed, haber tonu): toplayıcı (`haber.py`, `scripts/haber_run.py`, `trader-haber` birimleri), haber×sonuç raporu, panel/günlük özet satırları, kapı kancası (`haber_etiket`), `features.duygu` / `features.haber` yazımı **tamamen silindi**. Duygu/haber değerleri hiçbir karar girdisi değildir: kapı, atlama kuralı, not **ve ML özelliği** (`ml_live_v2.setup_feature_dict` `duygu*`/`haber*`/`fng*`/`fear*`/`greed*` alanlarını eğitimde ve puanlamada atlar).
- **`etiket_duygu` kuralı silindi.** Kanıtla açılmamıştı: durum dosyasında `gecmis` boştu (hiç kapanma/açılma olayı yok); kural, tanıtıldığı işlemde (b6b5152) `acik: true` olarak yapılandırmadan/varsayılandan açıldı.
- **Otomatik kapat/aç mekanizması silindi** (`otomatik` yapılandırma bloğu, değerlendirici `guncelle`, `features.etiket_atlardi` notu, `var/durum/etiket_kurallari_v1.json` yazımı/okuması, ÖĞRENME "Etiket kuralları" kartı, günlük özet/Telegram olay satırı, gece işi çağrısı). Kural artık **sabit**: yapılandırmada `acik: true` ise hep açık.
- Defter şeması **değişmedi**: eski satırlarda `skip_reason = etiket_duygu` / `etiket_kalabalik` kalabilir; yalnız okunur (gösterim sözlükleri adı korur). Sunucuda kalan eski `etiket_kurallari_v1.json` zararsızdır (kimse okumaz).

## Yer ve sıra
`EntryGate.decide` kâğıt dalı: ... küme/hesap tavanı -> **ML filtresi** (`ml_filter`) -> **rejim etiketi kuralı** -> risk kontrolü. Kod: `src/trader_core/etiket_kurallari.py` (saf), `gates.EntryGate._etiket_karari`.

## Kural (`engine.paper.json` `etiket_kurallari`: `{"rejim": {"acik": true}}`)
| Kural | Atlama kodu | Veri | Koşul |
|---|---|---|---|
| rejim karşıtı | `etiket_rejim` | sinyal satırının rejimi (`regime.py` sınıflaması) | long + `trend_down`, short + `trend_up` |

`acik: false` ile yapılandırmadan kapatılabilir. Bilinmeyen anahtar (`duygu`, `otomatik`, `kalabalik`...) `ConfigError`.

**Fail-open:** rejim yoksa kural engellemez; `etiket_veri_yok:<kod>` sayacı ve `status.json` `etiket_kurallari.kurallar.<kod>.veri_yok` bunu gösterir. Kural hatası girişi engellemez (log).

## Kayıt
Atlanan işlem karar satırı olarak yazılır (`skip_reason` = `etiket_rejim`, `veto_reason` = `gate:etiket_rejim:<yön>/<rejim>`); mevcut karşı-olgu ("alınsaydı", `cf_outcomes`/`alinmayan_sonuc`) bunu otomatik kapsar. Defter şeması 7 `skip_reason` sözlüğü (eski `etiket_duygu`, `etiket_kalabalik` dahil) aynen kalır.

## Testler
`tests/test_etiket_kurallari.py` (kural mantığı, yapılandırma, silinenlerin yokluğu, ML özelliklerinde duygu/haber yok), `tests/engine/test_etiket_kurallari_gate.py` (kapı: duygu/haber kapısı yok, `etiket_atlardi` notu yok, rejim kuralı aynen atlar).
