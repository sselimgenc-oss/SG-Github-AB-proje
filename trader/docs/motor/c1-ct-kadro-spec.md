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
