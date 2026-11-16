# 07 — 1l3a'dan kopyalanan dosyalar (spesifikasyon v1, 16 Kasım 2026)

Kaynak kararlar: `motor-tasarimi.md` §1.0 (bağlayıcı kullanıcı ilkesi: iki yoldan biri — **(a) kopyala** ya da **(b) yalnız fikir**; dış çerçevenin üstüne inşa yok), §1.2 (hangi dosya hangi yoldan), §1.3 (ham `requests`, ccxt/python-binance yok), §2.10 (hedef yollar), §3.1 (Faz A yok listesi), §5 risk 7/11/12. Kaynak kök: `/home/user/sselimgenc-oss/1l3a-proje/` (**yalnız okunur; hiçbir dosya çalıştırılmaz, içe aktarılmaz, mount edilmez, bağımlılık olarak kurulmaz**). Kopyadan sonra 1l3a deposu silinse de sistem çalışır. Bu belge kod, test ve commit içermez.

## 1. Kurallar (her kopya için bağlayıcı)

1. **Başlık (zorunlu, dosyanın en üstü):**
   ```
   # Kopyalandı: 1l3a-proje/<kaynak yol> (kullanıcının kendi kodu; lisans engeli yok)
   # Kopya tarihi: <YYYY-MM-DD>   Kaynak commit: <kısa kimlik ya da "unknown">
   # Çalışma zamanında kaynak depo import edilmez/mount edilmez. Değişiklikler: <kısa liste>.
   ```
   (`1l3a-proje` deposu şu an kısa kimlik `2dd2dce` raporlar; kopyalayan ajan kopya anındaki değeri yazar.)
2. **Mantık değişmez.** Yalnız bu belgede listelenen kesinti/ek/yeniden adlandırma yapılır. Her sapma bu belgedeki "Değişiklikler" listesinde olmalıdır; listede olmayan değişiklik hatadır (inceleme `diff` ile yapılır).
3. **Tanımlayıcılar İngilizceye çevrilir** (§4 tabloları). Türkçe yorumlar ve hata iletileri **kalır** (repo üslubu: Türkçe düzyazı, İngilizce tanımlayıcı), yalnız kimlikler değişir.
4. **Saat disiplini:** kopyalarda `time.time`, `time.sleep`, `datetime.now`, `pandas.Timestamp.now` **yoktur**; saat/uyku **zorunlu enjekte** parametredir (varsayılan değer yok). `08` testi bunu kilitler.
5. **Bağımlılık disiplini:** yalnız standart kütüphane + `requests` (kurucuda tembel import, 1l3a gibi). Kopyalar `pandas`/`numpy`/`motor.*` import **etmez** (feed süreci pandas yüklemez; `01-feed.md`).
6. **1l3a testleri** (b) yoldur: test kodu kopyalanmaz; senaryo listesi (§4) bağımsız test ajanı tarafından **bizim arayüze** yazılır.
7. **Faz A / Faz B ayrımı:** Faz A'da yalnız §4.1–§4.3 kopyalanır. §4.4 satırları **Faz B**'dir; burada kopyalama kuralları önceden dondurulur ama dosyalar şimdi oluşturulmaz (§3.1 "yok" listesi: imzalı istemci, `BinanceFuturesBroker`, algo emirleri, emir hız sınırı).
8. Bırakılanlar (hiç alınmaz): `motor/portfoy/motor.py`, `motor/backtest/motor.py`, `motor/canli/paper*.py` motor/çok hesap kısımları, `motor/strateji/*`, `motor/risk/limitler.py`, `canli_kayit.py`, `motor_kopru.py`, `calistir.py`, `pano.py`, `telegram.py`, `risk_adim_kontrol.py`, tüm `arastirma/`, `paper_takvim.py`, `paper_kaynak.py`, `motor/veri/*`.

## 2. DOSYA SAHİPLİĞİ

Bu birim yalnızca şunlara dokunur (Faz A):

- `src/trader_engine/exchange/__init__.py` (boş), `exchange/rules.py`
- `src/trader_engine/marketdata/rest_public.py`
- `src/trader_engine/fileio.py`
- `tests/engine/test_engine_rest_public_spec.py`, `test_engine_rules_spec.py`, `test_engine_fileio_spec.py` (bağımsız test ajanı); `test_engine_copied_impl_smoke.py` (gerçekleme ajanı); `tests/engine/fixtures/binance/exchange_info_*.json` (kayıtlı **sahte** exchangeInfo parçaları; gerçek kayıt Faz B)

**Uygulayan ≠ sahip kuralı:** `marketdata/feed.py` bu belgedeki §4.2 "feed.py" kuralına göre kopyalanır **ama dosyanın sahibi ve uygulayanı 01'dir**; 07'nin ajanı `feed.py`'ye dokunmaz.

Dokunulmaz: `marketdata/store.py`, `feed.py`, `sources.py` (01); `status.py` (05; `fileio.py`'yi çağırır); `types.py`, `numeric.py` (02; `rules.py` bunları import eder); `pyproject.toml` (08).

## 3. Neden bu iki yoldan biri (özet tablo; §1.2 ile aynı)

| 1l3a dosyası | Yol | Faz | Bizdeki hedef | Uygulayan |
|---|---|---|---|---|
| `motor/canli/paper_veri.py` | (a) kes+uyarla | A | `marketdata/rest_public.py` | 07 |
| `motor/canli/borsa/kurallar.py` | (a) kes+uyarla | A | `exchange/rules.py` | 07 |
| `motor/canli/durum.py::atomik_yaz_*`, `motor/canli/kalp_atisi.py` | (a) kes+uyarla | A | `fileio.py` | 07 |
| `motor/canli/paper_canli.py` (`CanliKaynak.baslat/guncelle/funding_guncelle`) | (a) ağır kes | A | `marketdata/feed.py` | **01** |
| `motor/canli/borsa/binance_futures.py` | (a) | B | `exchange/binance_rest.py` | (Faz B) |
| `motor/canli/borsa/canli_yurutucu.py` | (a) kes | B | `brokers/binance_futures.py`, `reconcile.py` (canlı kısım), `order_manager.py` canlı yolu | (Faz B) |
| `motor/canli/borsa/kuru.py` | (a) + ek | B | `tests/engine/fake_exchange.py` | (Faz B) |
| `motor/canli/borsa/canli_limitler.py`, `canli_ayar.py` | (b) fikir | A/B | `killswitch.py` (durum makinesi fikri), `config.py` (mod, çift onay, anahtarlar yalnız env) | 05/02 |
| `testler/test_canli_borsa.py`, `test_canli_limitler.py`, `test_lookahead_tum_stratejiler.py` | (b) senaryo | A/B | `tests/engine/` (aşağıdaki senaryo listeleri) | test ajanları |
| Stop/hedef aynı mumda → STOP, gap dolumu, funding imleci (`backtest/motor.py`, `portfoy/motor.py::_mum_ici`, `_funding_ode`) | (b) kural | A | `brokers/paper.py` (03) | 03 |

## 4. Kopyalama şartnameleri

### 4.1 `paper_veri.py` → `src/trader_engine/marketdata/rest_public.py`

**Tutulan (kaynak satırları):** sabitler (`FAPI`, `AGIRLIK_ESIGI=1800`, `ISTEK_ZAMAN_ASIMI=20`); `FapiIstemci.__init__` (`requests` tembel import, ağırlık sayaçları, `max_deneme=5`); `_agirlik_bekle`; `get` (ağ hatası/5xx üstel geri çekilme tekrarı, `X-MBX-USED-WEIGHT-1M` okuma, 429 `Retry-After` bekleme+tekrar, **418 tekrarsız hata**, 451 konum kısıtı hatası, diğer kodlar hata); `sunucu_zamani`; `exchange_info`; `klines` (1500'lük sayfalama, `startTime = son açılış + 1`); `funding` (1000'lik sayfalama, `startTime = fundingTime + 1`, çift kayıt süzme); `klines_df` kapanmış-bar süzgeci kuralı (`closeTime < şimdi`).

**Kesilen:** `ESLEME`, `binance_sembol` (TradFi `DK_` eşlemesi — kullanılmaz; sembol dönüşümü `types.pair_symbol`); `WS_TABAN`; `BinanceHata` yerine yeni sınıflar (aşağıda); `kurallar_cikar` (`motor.backtest.motor.SembolKurallari` import'u — yerine `exchange/rules.py`); `SUREKLI_TURLER`, `TRADFI_TURU`, `tradfi_mi`, `tradfi_sinif_uyusmazliklari`, `esleme_dogrula`, `mumlar` (`paper_takvim`, `motor.veri.*`), `BEKLENEN_REFERANS`, `beklenen_mum_sayisi`, `kova_bekleniyor`; `functools`, `numpy`, `pandas` import'ları; `FapiIstemci.klines/funding` içindeki DataFrame üretimi.

**Eklenen:** (i) `mark_price_klines` (+ `_all`) ve `premium_index` uçları; *Binance uç adları `GET /fapi/v1/markPriceKlines`, `GET /fapi/v1/premiumIndex`, `GET /fapi/v1/fundingRate`, `GET /fapi/v1/klines`, `GET /fapi/v1/exchangeInfo`, `GET /fapi/v1/time` ve parametre adları "doğrulanacak" (Faz A'da yalnız kayıtlı sahte fixture; ilk gerçek yanıtlar 01'de fixture olarak kaydedilir)*; (ii) `X-MBX-USED-WEIGHT-1M` başlığına ek olarak `Retry-After` güvenli ayrıştırma (sayı değilse 60); (iii) toplam 429 bekleme tavanı `max_total_wait_s = 300` (aşılırsa `ExchangeBan`); (iv) saat/uyku enjeksiyonu zorunlu; (v) `rows_to_bars`.

**Yeni çerçeve (donmuş imza):**
```python
FAPI_BASE = "https://fapi.binance.com"
class ExchangeError(Exception)
class ExchangeBan(ExchangeError):                 # 418, 429 tavanı aşıldı, 451
    http: int | None; retry_after_s: int | None
class PublicRestClient:
    def __init__(self, *, base_url: str = FAPI_BASE, session=None, now_s: Callable[[], float],
                 sleep: Callable[[float], None], max_attempts: int = 5, weight_threshold: int = 1800,
                 timeout_s: float = 20.0, max_total_wait_s: float = 300.0)
    def get(self, path: str, params: dict | None = None) -> Any
    def used_weight(self) -> int
    def server_time_ms(self) -> int
    def exchange_info(self) -> dict
    def klines(self, symbol, interval, start_ms=None, end_ms=None, limit=1500) -> list[list]
    def klines_all(self, symbol, interval, start_ms, end_ms=None, *, page=1500, max_pages=200) -> list[list]
    def mark_price_klines(...) / mark_price_klines_all(...)           # klines ile aynı imza
    def funding_rates(self, symbol, start_ms=None, end_ms=None, limit=1000) -> list[dict]
    def funding_rates_all(self, symbol, start_ms, end_ms=None, *, max_pages=100) -> list[dict]
    def premium_index(self, symbol: str | None = None) -> dict | list
@dataclass(frozen=True)
class AbnormalRow: open_ms: int; reason: str          # "bad_close_time" | "bad_values"
def rows_to_bars(pair: str, kind: Kind, tf: str, rows: Sequence[Sequence], now_server_ms: int) -> tuple[list[Bar], list[AbnormalRow]]
        # kapanış süzgeci: closeTime+1 <= now_server_ms; closeTime == open+tf_ms-1; o,h,l,c sonlu >0; mark'ta v=0
```
**İstemci kuralları (değişmez):** yalnız `GET` (emir yok); ağ hatası/5xx en çok `max_attempts` kez, bekleme `min(2**deneme, 60)`; 418 ve 451 **hiç tekrarlanmaz** (`ExchangeBan`); hata iletisi imza/anahtar taşımaz (anahtar zaten yok) ve **URL/parametre sızdırmaz** (yalnız yol + HTTP kodu + kısaltılmış gövde); `max_attempts` bitince `ExchangeError`.

**Yeniden adlandırma:** `FapiIstemci → PublicRestClient`, `get → get`, `sunucu_zamani → server_time_ms`, `exchange_info → exchange_info`, `klines → klines`, `funding → funding_rates`, `klines_df → rows_to_bars`, `_agirlik_bekle → _wait_for_weight`, `kullanilan_agirlik → _used_weight`, `agirlik_zamani → _weight_ts`, `uyku → sleep`, `saat → now_s`, `taban → base_url`, `oturum → session`, `max_deneme → max_attempts`, `bas/bit → start_ms/end_ms`, `BinanceHata → ExchangeError`.

**Test senaryoları (b), 1l3a `test_canli_borsa.py` karşılıklarından:** `5xx` tekrar denenir ve sonunda başarılı (satır 87); ağ hatası tekrar, **hata metni URL içermez** (93); `429` `Retry-After` kadar bekler (126'nın genel hâli: ağırlık eşiği bekletir); 418 tekrarsız (116'nın GET karşılığı); sayfalama (1500/1000 sınırı, son satır tekrarı yok); kapanmış-bar süzgeci (kapanış 1 ms önce/tam); `abnormal_close`; `X-MBX-USED-WEIGHT-1M` eşik bekleme; toplam bekleme tavanı; saat/uyku enjeksiyonu (gerçek `time` çağrılmaz — `monkeypatch` ile `time.sleep` yasaklanıp test geçer).

### 4.2 `paper_canli.py` (`CanliKaynak`) → `marketdata/feed.py` (uygulayan: **01**)

**Tutulan fikir/kod:** `GRACE_SN` (kapanıştan sonra REST'in yayımlaması için bekleme; bizde `grace_s=3`); `baslat`'ın "son yazılı barın ardından REST'ten tamamla" döngüsü; `guncelle`'nin "`son + 2·aralık + grace` geçmediyse sorma" ve eksik mum sayma/`veri_bosluk` olayı mantığı (`bos = (ix[k]-ix[k-1])/a - 1`); `funding_guncelle` artımlı başlangıç (`son.index[-1] + 1 ms`, ilk seferde 40 gün geriye); `ws_dogrula`'nın "REST geçerli, uyuşmazlık günlüğe" ilkesi → bizde bar builder `agg_mismatch` (01 §5.4).

**Kesilen:** `TekrarKaynagi` mirası ve `paper_kaynak.MUM_SUTUNLARI`; `satirlar`, `gec_barlar`, `BIRIM_BEKLEME_SN` (çok sembollü birim mantığı); `_tohum`/`tohum_dizin` (`motor.veri.yeniden_ornekle`, Dukascopy tohumu); `tk_acik`, `paper_takvim` kullanımı (TradFi seansları); `ws_url`, `akislar`, `ws_dongu` (WS **Faz B'ye**, ilke notu olarak kalır); `SEANS_KONTROL_SN`; DataFrame tabanlı bellek modeli (`self.mumlar`, `self.fundingler`) — yerine `MarketStore` (SQLite).

**Ek:** SQLite yazımı, sunucu saati ofseti, kilit, durum dosyası, `gaps` tablosu (01'in kapsamı).

### 4.3 `kurallar.py` → `src/trader_engine/exchange/rules.py`

**Tutulan:** `SembolKurali` alanları (`tick, step, min_qty, max_qty, market_step, market_min, market_max, min_notional`; hepsi `Decimal`); `kural_cikar` mantığı (PRICE_FILTER/LOT_SIZE zorunlu, MARKET_LOT_SIZE yoksa LOT_SIZE, `MIN_NOTIONAL` ya da `NOTIONAL` filtresi, `tick/step/market_step ≤ 0` ise hata, sembol yoksa hata); `asagi`/`yukari`; `miktar_yuvarla` (piyasa emri: `MARKET_LOT_SIZE` adımına **aşağı**, üst sınıra kırp); `stop_yuvarla` (long: yukarı, short: aşağı — **sıkı**); `hedef_yuvarla` (long: aşağı, short: yukarı — kolay dolum).

**Kesilen:** `boyutlandir`, `Boyut`, `from motor.canli.borsa import canli_limitler as cl` (boyut hesabı `trader_core.risk.size_position`'dadır; **tek risk kaynağı**), `dataclasses` yardımcıları yalnızca `boyutlandir` içindi.

**Eklenen:** (i) `to_symbol_rules(pair: str, spec: SymbolRuleSpec) -> types.SymbolRules` (float görünüm: `tick=float(spec.tick)`, `step=float(spec.market_step)`, `min_qty=float(spec.market_min)`, `max_qty=float(spec.market_max)`, `min_notional=float(spec.min_notional)`); (ii) `spec_to_json(spec) -> str` / `spec_from_json(s) -> SymbolRuleSpec` (Decimal'ler metin; `market.sqlite.rules.json` ve `history_dir/rules.json` biçimi); (iii) `extract_all_rules(info: dict, symbols: Iterable[str]) -> dict[str, SymbolRuleSpec | RulesError]` (tek çiftin hatası diğerlerini bozmaz); (iv) **`extract_rules` ek denetimleri:** sembolün `status == "TRADING"` ve `contractType == "PERPETUAL"` olması (değilse `RulesError("not_trading")`).

**Fail-closed düzeltmesi (1l3a'daki tutarsızlık):** kaynak docstring "eksik/bozuk filtre = hata (tahmin yok)" der ama kod `MIN_NOTIONAL`/`NOTIONAL` filtresi yoksa **varsayılan 5** uydurur. Kopyada eksik min-notional filtresi `RulesError("min_notional_missing")` olur (tahmin yok). Bu, §1 madde 2'nin **bilinçli** istisnasıdır ve burada listelenmiştir.

**Yeniden adlandırma:** `SembolKurali → SymbolRuleSpec` (`sembol → symbol`), `KuralHatasi → RulesError`, `kural_cikar → extract_rules`, `asagi → floor_to_step`, `yukari → ceil_to_step`, `miktar_yuvarla → round_market_qty`, `stop_yuvarla → round_stop_tight(stop, direction: int, rules)` (`direction`: long `1`, short `-1`), `hedef_yuvarla → round_target_easy(target, direction, rules)`.

**Not:** motor içi float tabanlı yuvarlama `numeric.py` (02) içindedir ve **aynı** kuralı uygular (`round_tight`); iki uygulama arasında eşitlik testi zorunludur (aynı tick'te aynı girdi aynı sonuç, Decimal ↔ float sınırı; risk 7).

**Test senaryoları (b), `test_canli_borsa.py::test_kural_cikar_ve_yuvarlama` (satır 173) karşılığı:** `tick=0.10, step=0.001, market_step=0.01, min_notional=100, market_max=100`; `round_market_qty(0.0199) == 0.01`; `round_market_qty(500) == 100`; `round_stop_tight(49000.07, 1) == 49000.1`; `round_stop_tight(51000.07, -1) == 51000.0`; `round_target_easy(52000.07, 1) == 52000.0`; bilinmeyen sembol → `RulesError`; **ek (bizde):** MARKET_LOT_SIZE yok → LOT_SIZE; `stepSize=0` → hata; `MIN_NOTIONAL` yok → `min_notional_missing`; `status != TRADING` → `not_trading`; JSON gidiş-dönüş; `to_symbol_rules` float eşlemesi.

### 4.4 `durum.py` + `kalp_atisi.py` → `src/trader_engine/fileio.py`

**Tutulan:** `_gecici` (aynı dizinde `.<ad>.tmp-<pid>`), `atomik_yaz_metin` (geçici dosya + `flush` + `fsync` + `os.replace`; hata olursa geçici silinir), `atomik_yaz_json` (`ensure_ascii=False, indent=1, allow_nan=False`, sonda `\n`), `atomik_yaz_jsonl`; `zaman_str`/`zaman_oku` (`YYYY-MM-DDTHH:MM:SSZ`); `kalp_atisi.yaz`/`oku` (şema, `aralik_sn`), `kesinti` ve `olay_mesaji` (yeniden başlatma kesintisi ölçümü).

**Kesilen:** `durum.py`'nin geri kalanı (şema sabitleri, pano durum dosyaları, doğrulayıcılar, `para`, `konum`, `bant_bul`, `DURUM_DIZINI`, `DOSYALAR`/`EK_DOSYALAR` sözlükleri); `kalp_atisi.py`'de `pandas` kullanımı (`pd.Timestamp` → `datetime`), `en_yeni` yalnızca `datetime` ile; `DOSYA`, `SEMA` sabitleri yeni adla.

**Yeni çerçeve (donmuş imza):**
```python
def atomic_write_text(path, text: str) -> Path
def atomic_write_json(path, data: dict) -> Path
def atomic_write_jsonl(path, rows: Iterable[dict]) -> Path
def fmt_ts(t: datetime) -> str                         # tz-aware şart; tz-naive ValueError
def parse_ts(s: str) -> datetime
def heartbeat_write(directory, now: datetime, started_at: datetime, prev: str | None = None, stopped: bool = False) -> Path   # kalp_atisi.json, şema "engine/heartbeat/1", aralik_s=60
def heartbeat_read(directory) -> dict | None            # yoksa None; bozuksa FileIoError
def interruption(prev: str | None, started_at: datetime) -> dict   # {prev, started_at, seconds|None, reason|None}
class FileIoError(Exception)
```
**Yeniden adlandırma:** `atomik_yaz_* → atomic_write_*`, `zaman_str → fmt_ts`, `zaman_oku → parse_ts`, `kalp_atisi.yaz → heartbeat_write`, `kalp_atisi.oku → heartbeat_read`, `kesinti → interruption` (`sn → seconds`, `neden → reason`), `DurumHatasi → FileIoError`, `onceki → prev`, `baslangic → started_at`, `durdu → stopped`.

**Test senaryoları (b), `test_canli_durum.py` (satır 81, 87):** atomik yazma sonrası geçici dosya kalmaz; yazma hatasında eski dosya korunur ve geçici silinir; okuyucu yarım dosya görmez (iki iş parçacığı yaz/oku döngüsü); tz-naive zaman reddi; `allow_nan=False` (NaN → hata); `interruption`: önceki yok → `seconds=None`, saat geri gitti → `seconds=None` + neden, normal → saniye farkı.

### 4.5 Faz B kopyaları (şimdi oluşturulmaz; kurallar dondurulmuş)

- **`binance_futures.py → exchange/binance_rest.py`:** tutulan: `temizle`, `imzala` (HMAC-SHA256), `duz`, `BorsaHata/EmirReddi/BorsaYasagi`, `_ham` (**`tekrar_guvenli=False` ile emir POST'u asla otomatik tekrarlanmaz; ağ hatası/5xx `belirsiz=True`**), `-1021` saat eşitleme+tek tekrar, 429/418 yasak penceresi, ağırlık bekleme, uç sarmalayıcıları (`bakiye`, `pozisyonlar`, `emirler`, `hazirla` + `-4046/-4059` idempotent, `piyasa`, `kosullu`, `sorgula`, `iptal`, `hepsini_iptal`, `kullanici_islemleri`, `funding_gecmisi`). Eklenecek: `X-MBX-ORDER-COUNT-10S/1M` sayaçları, `PERCENT_PRICE`, `markPriceKlines`/`premiumIndex` (public istemciyle birleşir). **Saat disiplini:** `uyku=time.sleep`, `saat=time.time` varsayılanları kaldırılır (zorunlu enjeksiyon). Koşullu emir uçları (`/fapi/v1/algoOrder`, `clientAlgoId`, `triggerPrice`) 1l3a'da **varsayımdır**; testnet doğrulaması (§3.3 madde 1) olmadan canlıya çıkmaz.
- **`canli_yurutucu.py`:** yalnız şu işlevlerin **mantığı** alınır: `_giris_gonder` (POST öncesi kayıt, belirsiz yanıtta sorgu, yalnız "emir yok" ise tek yeniden gönderim), `_koru`/`_stop_kur` (stop kurulamazsa kapat; iptal edilmiş eski stop kimliği yeniden kullanılmaz), `_stop_yukselt` (önce yeni, sonra eski iptal; gevşetme yok), `_mutabakat` (§2.6 tablosu), `_dolum_sonrasi_risk`. `client_id`'nin 1l3a biçimi (`ONEK-rol-sha1[:24]`) **kullanılmaz**; yerine bizim `make_client_id` (04). Atılan: `Niyet`, `MotorGorunumu`, `_kayit_*` (`canli_kayit.py`), `canli_limitler` bağımlılıkları, `Ayar` (yerine `EngineConfig`), Telegram.
- **`kuru.py → tests/engine/fake_exchange.py`:** `KuruBorsa` korunur; **eklenir:** emir reddi, gecikme, kısmi dolum, belirsiz yanıt (POST öncesi/sonrası çökme noktaları). Yalnız test kodudur.
- **(b) senaryo listesi** (`test_canli_borsa.py` isimleri **başlık** olarak, bağımsız test ajanı Faz B'de yazar): `r1` (POST ağda tekrar edilmez; belirsiz giriş dolduysa tekrar yok / yoksa tek yeniden gönderim), `r2` (iptal edilmiş eski stop kurulu sayılmaz; yeniden kurulumda kimlik sayaçlı), `r3` (kill: önce kapat sonra iptal; kapatma başarısızsa stop kalır), `r4/r5` (belirsiz giriş sonra pozisyon görününce hemen stop), `r6` (dolum kayması riski aşarsa reduceOnly küçült), `r7` (paper stopu fiyatın ötesinde → piyasada kapat), `r8` (stop miktarı uyuşmazlığı: yeni stopu iptal etme), `r9` (iptal başarısızsa kayıt silinmez), `r10` (bayat sinyal), `r12` (sıfır özsermaye sıfıra bölme yok); `test_canli_limitler.py` yalnız **durum makinesi** senaryoları (sayılar yok); `test_lookahead_tum_stratejiler.py` fikri (tam seri çıktısı kesilmiş seriyle aynı; iki tohum × iki kesim, 7/24 ve boşluklu veri) → bizde 06 `--truncate-check` ve `--paranoid`.

## 5. Elle doğrulanabilir örnekler

1. **Kapanmış bar süzgeci:** `now_server_ms = 1796115603000` (2026-12-01T09:00:03Z), 1m satırı `open=1796115540000` (08:59:00Z), `closeTime=1796115599999` ⇒ kapanış+1 = `1796115600000 ≤ now` ⇒ **kapanmış**; `open=1796115600000` (09:00), `closeTime=1796115659999` ⇒ `1796115660000 > now` ⇒ atılır.
2. **Sayfalama:** `klines_all` 3200 bar isterken sayfalar `[1500, 1500, 200]`; ikinci sayfa `startTime = ilk_sayfa_son_open + 1`; 200'lük son sayfa `< page` olduğu için durur.
3. **429:** yanıt `Retry-After: 7` ⇒ `sleep(7)`, aynı istek tekrarlanır; toplam bekleme `> 300` ⇒ `ExchangeBan`.
4. **Kurallar:** yukarıdaki §4.3 senaryosu. Ek: `SymbolRuleSpec(tick=0.01, step=0.001, market_step=0.001, min_notional=5)` ⇒ `to_symbol_rules` `SymbolRules(tick=0.01, step=0.001, min_qty=0.001, min_notional=5.0)`; `min_notional` filtresi yoksa `RulesError`.
5. **Atomik yazma:** `atomic_write_json(p, {"a": 1})` ⇒ içerik `{\n "a": 1\n}\n`; `os.replace` sırasında hata ⇒ `p` eski içerikte kalır, `.p.tmp-<pid>` yok.

## 6. Kabul ölçütleri

- Her kopya dosyanın başlığı §1 madde 1 biçiminde ve kaynak yolu gerçektir (test: ilk üç satır deseni).
- `grep -r "motor\.\(canli\|backtest\|veri\|portfoy\)" src/trader_engine` **boş**; `import 1l3a` yolları, `sys.path` eklemeleri, mount/submodule yok (08 testi).
- Kopyalar `pandas`/`numpy` import etmez (`rest_public.py`, `rules.py`, `fileio.py`); alt süreçte `import trader_engine.marketdata.rest_public` sonrası `pandas` `sys.modules`'ta **yok**.
- §4 "Kesilen" listesindeki hiçbir tanımlayıcı kopyada kalmaz (`grep`: `ESLEME`, `tradfi`, `boyutlandir`, `canli_limitler`, `paper_takvim`, `TekrarKaynagi`).
- Kopya mantığı bu belgedeki değişiklik listesiyle sınırlıdır (inceleme: kaynakla `diff`; tek tek açıklanmış).
- 1l3a deposu yokken (yol `mv` ile gizlenmiş) tüm Faz A testleri geçer (mentor incelemesi §5 madde 8 ile uyumlu).

## 7. Belirsizlikler ve çözümleri

- **Tasarım §1.2 `paper_canli.py` "(a) kopyala" der**, fakat dosya `TekrarKaynagi` (`paper_kaynak.py`), `motor.veri.*`, `paper_takvim` ve çok sembollü TradFi mantığına bağlıdır (bunlar kopya listesinde **yok**). Mantık değişmeden olduğu gibi kopyalanamaz; çözüm §4.2: yalnız boşluk doldurma/artımlı funding iskeleti alınır, depolama ve zamanlama yeniden yazılır — pratikte (a)'nın "yalnız belirtilen kesintiler" kuralını aşar; bu yüzden **mentor onayı** ister (kopyalama yerine "(b) fikir" olarak sınıflanması da kabul edilebilir; davranış aynı kalır).
- **`paper_veri.py` iki ayrı istemci mantığı** (`FapiIstemci` ağırlık bekleme ve `BinanceFutures` ağırlık bekleme) kopyalar arasında yinelenir; Faz B'de `binance_rest.py` ile `rest_public.py` ortak taban sınıfa birleştirilebilir (şimdilik ayrı: Faz A kapsamı kilidi).
- **Lisans:** kaynak kullanıcının kendi kodu; `THIRD_PARTY_NOTICES.md`'ye ekleme gerekmez (yalnız başlık).
- **Binance uç adları** kopyada olduğu gibi kullanılır; doğrulama testnet/gerçek hesap adımlarındadır (§3.3).
