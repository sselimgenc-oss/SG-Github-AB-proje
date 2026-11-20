# C1: CT kadro uzlaşısı kurulumu + CT okuyucu — belirtim (19 Kasım 2026)

Kaynak: CT projesinin yayını `ct.kadro_yon.v1` — `https://raw.githubusercontent.com/sselimgenc-oss/CT-Proje/canli-durum/durum/paylasim/kadro_yon_v1.json`.
Kullanıcı kararı: ML bu veriyle **işlem açabilir** (kendi risk limitleri ve kapıları içinde, kâğıtta).

## 1. Okuyucu (`scripts/ct_kadro_cek.py` + `deploy/trader-ct-kadro.{service,timer}`)
- Her 5 dakikada bir (timer `OnUnitActiveSec=5min`, `OnBootSec=3min`) adresi `urllib` ile çeker: zaman aşımı 20 sn, en fazla 1 MB; HTTP 200 dışı → hata.
- Doğrulama: `sema == "ct.kadro_yon.v1"`, `uretildi_utc` ISO-8601 `Z`, `coinler` liste; her öğede `coin` (str), `long_trader`, `short_trader` (≥0 int), `net_yon` ∈ {long, short, notr}; `net_nominal_usd` sayı ya da null. Geçersiz öğe atlanır (sayılır); şema/üst alan hatası → dosya yazılmaz.
- Başarıda `var/ct/kadro_yon.json` (aynen gelen JSON) atomik yazılır; her koşuda `var/ct/durum.json` = `{"son_deneme": ISO, "son_basari": ISO|null, "son_hata": str|null, "gecersiz_oge": n}`.
- Birim: kullanıcı `trader`, `ReadWritePaths=<TRADER_DIR>/var/ct`, ağ yalnız HTTPS çıkışı, `MemoryMax=100M`; diğer birimlerle aynı sertleştirme. `install.sh` dizini (`safe_tree_path` ile) oluşturur ve timer'ı etkinleştirir.
- Anahtar/parola yok (herkese açık adres).

## 2. Okuma ve eşleme (`src/trader_core/ct_kadro.py`, saf)
- `oku(yol, simdi, *, azami_yas_dk=45) -> dict | None`: dosya yok/bozuk/şema farklı ya da `simdi - uretildi_utc > 45 dk` (ya da `uretildi_utc` gelecekte > 5 dk) → `None`. Aksi `{cift: kayit}` sözlüğü (aşağıdaki eşlemeyle) + `"_uretildi"`.
- `hl_to_binance(coin, evren) -> str | None`: `"dex:COIN"` → `COIN`; küçük `k` + büyük harfle başlayan (`kPEPE`, `kSHIB`) → `1000` + kalan (`1000PEPE`, `1000SHIB`); sonra `f"{taban}/USDT"`; `evren` (çift kümesi) içinde değilse `None`.
- Kayıt: `{"long": int, "short": int, "net_yon": str, "net_nominal_usd": float|None, "veri_yasi_sn": float|None}`.

## 3. C1 kurulumu (`src/trader_engine/strategies/arms/c1.py`)
- Sözleşme diğer kollarla aynı (`SETUP="C1"`, `TIMEFRAMES=("1h","4h")`, `CORE=False`, `ML_SCORED=False`, `EXIT_MODE="target"`, `PRIORITY=80`, `FEATURES`).
- Dosya yolu: `TRADER_CT_KADRO` ortam değişkeni ya da `<repo>/var/ct/kadro_yon.json` (M1'deki model dizini çözümüyle aynı kalıp). Dosya `mtime` değişmedikçe yeniden okunmaz.
- Sinyal (son kapanmış mum, karar anı `D`): `oku(..., simdi=D)` geçerli ve çift için kayıt var; `net_yon` long ya da short; `toplam = long+short >= 3`; `baskinlik = max(long,short)/toplam >= 0.70`; baskın taraf `net_yon` ile aynı; `net_nominal_usd` null değilse işareti yönle uyumlu (long → >0). Hepsi sağlanırsa o yönde aday.
- Giriş = mum kapanışı; stop = giriş ∓ 1,5 × ATR(14) (o zaman diliminde, diğer kollardaki ATR yardımcısıyla); hedef = giriş ± 2R; zaman durdurma diğer `target` kollarıyla aynı.
- Aynı çift + yön için yeni CT dosyası gelene kadar (aynı `uretildi_utc`) tek aday.
- Özellikler (defter `features`): `ct_long`, `ct_short`, `ct_baskinlik`, `ct_net_nominal_usd`, `ct_veri_yasi_sn`, `rr`.
- Geri testte dosya ya yoktur ya da bayattır → aday üretmez (geleceği görme yok).

## 4. Yapılandırma ve izleme
- `config/engine.paper.json`: `arms` listesine `C1@1h`, `C1@4h`; `arm_max_positions` içine `"C1": 3`. Testnet/canlı değişmez.
- Sağlık (`scripts/health_run.py`): `var/ct/durum.json`'da `son_basari` 45 dakikadan eskiyse `WARN ct_kadro_bayat` ("CT verisi bayat; C1 aday üretmiyor"). Motor etkilenmez.
- Pano/Telegram ek iş yok (C1 karnede diğer kurulumlar gibi görünür).

## 5. Sonraki parça (bu işte yok)
Tüm adaylara `ct:ayni_yon` / `ct:ters_yon` / `ct:yok` etiketi (ML özelliği olarak; engellemez).

## 6. CT bilgisi: tek tip kayıt, ML özelliği, C1 fiyat teyidi (20 Kasım 2026; kullanıcı onaylı, yalnız kâğıt)
Veri yolu aynı (okuyucu, 45 dk bayatlık). Testnet/canlı yapılandırması, risk sınırları, merdiven, kilitli dönem mührü değişmez.

- **Kayıt**: kâğıtta her karar (alınan ya da atlanan) ve dolayısıyla her işlemin `features` alanına tek tip blok (`EntryGate._ct_blok`; `_ct_yon` bunun `ct_yon` alanıdır):
  `ct_long`, `ct_short`, `ct_baskinlik` (max/toplam), `ct_net_yon` (long/short/notr), `ct_yon` (+1 işlem yönüyle aynı, -1 ters, 0 uzlaşı yok/nötr; çift dosyada yoksa sayımlar 0 ve 0),
  `ct_yas_dk` (veri yaşı, dakika). Veri yok/bayat → yalnız `ct_durum: "yok"` (başka `ct_` anahtarı yazılmaz). Okuma hatası kararı etkilemez. Şema değişmedi (features sözlüğü).
- **Rapor**: strateji verisi belgesinde "CT bilgisi" bölümü: kapanan işlemler `ct_yon` grubuna göre (aynı / ters / uzlaşı yok / yok): adet, kazanma oranı, ort. R. Panelde ayrı satır eklenmedi (işlem ayrıntı listesi için doğal bir yer yok).
- **ML özelliği (filtre değil)**: kâğıt filtreleri (`ortak_ogrenme.filtre`, kurulum süzgeci) özellik adlarını eğitim satırlarından alır ve paketin `meta.ozellikler` listesinde saklar; puanlama paketin KENDİ listesiyle yapılır, eksik özellik `fill` (ortalama) ile doldurulur.
  `features` içindeki `ct_yon`, `ct_baskinlik` zaten `f_ct_yon`, `f_ct_baskinlik` olarak; `setup_feature_dict` ayrıca `f_ct_trader_sayisi = log1p(ct_long + ct_short)` türetir (CT yoksa üçü de yok). Yeniden eğitilene kadar eski paket eski listesiyle puanlar (uyumsuzluk/kayma yok; testli).
  Araştırma hattındaki LightGBM sabit-liste modelleri (`trader_core/ml_features.py`, r02/r03 külliyatı) DEĞİŞMEDİ: CT tarihsel verisi yok, liste/hash eşitlik denetimleri var.
- **Tetik**: C1 yalnız CT ile işlem açmaz. CT adayına ek olarak kendi zaman diliminde son kapanmış mum için: long → kapanış > EMA50 ve kapanış > açılış; short → kapanış < EMA50 ve kapanış < açılış. Teyitsiz bar aday vermez ve CT dosyasını "tüketmez" (aynı dosya sonraki barda teyitlenirse aday olur).
  Teyitli aday diğer kollarla aynı kapı zincirinden geçer (kurulum başı `arm_id` ile ML filtresi ≥10 kapanmış işlemle, ardından etiket/ders kuralları, sonra risk). `ML_SCORED` alanı yalnızca testnet r03 süzgecini ilgilendirir; kâğıt filtresi bayraktan bağımsızdır.
- **Bayat**: CT özellikleri boş (`ct_durum: "yok"`), C1 aday yok, "kalabalık" kuralı engellemez (fail-open, sayılır), sağlık `WARN ct_kadro_bayat`. Başka bir şey değişmez.
