# Rejim etiketi yayını — belirtim (Faz 1, 19 Kasım 2026)

ML Otonom her enstrümanın piyasa rejimini (trend yukarı/aşağı, yatay, oynak, belirsiz) salt-okunur bir JSON olarak yayınlar. 1L3A ve CT okur ve **yalnız etiket/kayıt** olarak kullanır; hiçbir işlemi engellemez.

## Yayın adresi
- Mevcut pano Worker'ı (`trader-pano`) üzerinden: `https://<worker-adresi>/rejim.json`.
- **Bu tek yol parolasızdır** (içerik yalnız rejim etiketi; bakiye, pozisyon, anahtar yok). Yanıt başlıkları: `Content-Type: application/json`, `Cache-Control: no-store`, `Access-Control-Allow-Origin: *`. Yalnız `GET`/`HEAD`; diğer tüm yollar eskisi gibi parolalı.
- Panoyla aynı zamanlayıcıyla (trader-panel-publish) yenilenir.

## JSON biçimi (sürüm 1)
```json
{
  "surum": 1,
  "kaynak": "ML",
  "uretim_ts": "2026-11-19T12:00:00Z",
  "gecerlilik_dk": 90,
  "rejimler": ["trend_up", "trend_down", "range", "volatile", "unclear"],
  "varliklar": {
    "BTC/USDT": {"baz": "BTC", "varlik_sinifi": "kripto",
                 "4h": {"rejim": "trend_up", "bar_ts": "2026-11-19T08:00:00Z"},
                 "1d": {"rejim": "range", "bar_ts": "2026-11-18T00:00:00Z"}}
  }
}
```
- `baz`: çiftin `/` öncesi kısmı (Hyperliquid eşlemesi için; `1000SHIB` gibi önekler olduğu gibi kalır).
- `varlik_sinifi`: `kripto` | `hisse` | `emtia` (motorun `arm_guard.asset_class` ile aynı kural, paper yapılandırmasının kümelerinden).
- `bar_ts`: rejimin hesaplandığı son **kapanmış** mumun açılış zamanı (UTC, `Z`).
- Veri yetersiz ya da çift için mum yoksa o zaman dilimi `{"rejim": "unclear", "bar_ts": null}`.
- `uretim_ts + gecerlilik_dk` geçmişse okuyucu veriyi bayat sayar (okuyucunun işi).

## Hesaplama
- Yeni modül `src/trader_core/rejim_yayini.py`: `uret(store, pairs, clusters, now) -> dict` (saf; ağ yok). Çiftler paper yapılandırmasının `pairs` listesidir (isteğe bağlı ve emekli çiftler dahil, verisi olmayan `unclear`).
- 4h: market deposundan son kapanmış 4h mumlar (en az 200 mum istenir; eksikse elde olanla), `trader_core.regime.classify_series` (donuk modül, yalnız çağrılır; `DEFAULT_PARAMS`) ve son satırın rejimi.
- 1d: aynı 4h mumlardan UTC gün sınırında 6×4h birleştirilerek (eksik günü atla) üretilen günlük mumlar üzerinde aynı sınıflama.
- Rejim değeri `classify_series` çıktısındaki etiketin küçük harf adı; sözlük dışıysa `unclear`.
- CLI: `python -m trader_core.rejim_yayini --config-dir config --env paper --out <yol>`; çıktı atomik yazılır. Hata olursa sıfır olmayan çıkış ve dosya yazılmaz.

## Yayına bağlama
- `deploy/panel_yayinla.sh`: anlık görüntüden sonra `rejim.json`'u `$gecici/site/rejim.json`'a üretir; üretim başarısızsa uyarı yazar ama pano yayını sürer (rejim dosyası o turda olmaz).
- `deploy/panel_worker.js`: `GET`/`HEAD /rejim.json` parolasız, yukarıdaki başlıklarla `ASSETS`'ten; diğer her şey değişmez.

## Sınırlar
- Donuk dosyalara dokunulmaz (`trader_core/regime.py` dahil; yalnız içe aktarılır). Motor/kapı davranışı değişmez. Yeni bağımlılık yok.
