# Trader - freqtrade tabanli vadeli islem botu (iskelet)

Binance global USDT-M vadeli islemler icin, once dry-run (acik veri, API anahtari yok) calisan
freqtrade tabanli bot. Iki ornek calisir:

- **learner (L)**: derslerin uygulandigi bot.
- **twin (T)**: dondurulmus kopya; parametreleri asla degismez.

## Durum

Iskelet; strateji yok, islem acmaz. (`PlaceholderStrategy` hic sinyal uretmez.)
Sonraki parcalar: risk kilidi, rejim etiketi, strateji, veto servisi, ders servisi, Telegram, saglik izleyici.

## Klasor yapisi

```
docker-compose.yml        learner + twin servisleri (freqtrade 2026.10)
config/base.json          ortak ayarlar
config/learner.json       learner'a ozel (bot_name)
config/twin.json          twin'e ozel (bot_name)
.env.example              API kimlik bilgisi sablonu (yalnizca yer tutucu)
shared/                   salt-okunur ortak baglama (ileride veto dosyasi)
user_data/strategies/     stratejiler (iki bota salt-okunur baglanir)
user_data/learner|twin/   bota ozel veri/db/log (ayri dizinler)
src/trader_core/          freqtrade'den bagimsiz kendi kodumuz (config_loader)
tests/                    pytest testleri
scripts/                  download_data.sh, smoke_binance.sh
```

## Sunucuda calistirma (DigitalOcean Frankfurt)

Binance ABD IP'lerini HTTP 451 ile engeller; sunucu Frankfurt'ta olmali.

```bash
cp .env.example .env          # degerleri doldur (API kullanici/sifre/JWT)
./scripts/smoke_binance.sh    # iki satirda da HTTP 200 beklenir
./scripts/download_data.sh    # ~2 yillik veri (15m 1h 4h 1d)
docker compose up -d
```

API yalnizca sunucuda 127.0.0.1'dedir: learner 8080, twin 8081 (uzaktan SSH tuneli ile).

## Notlar

- Pair listesi (BTC, ETH, BNB, SOL, XRP, DOGE, ADA, TRX, LINK, AVAX) **sunucuda guncel piyasa
  degerine gore dogrulanmalidir**; sabit `StaticPairList` kullanilir.
- `max_open_trades: -1`: sinirlamayi ileride risk kilidi yapacak.
- Degismezler (`config_loader`): dry_run true (acik LIVE bayragi olmadikca), isolated margin,
  futures, dosyalarda anahtar/sir yok.
- Bu yapi build ortaminda (ABD) Binance'e erisilemedigi icin calistirilarak dogrulanmadi.

## Backtest (Binance'e erisimi olmayan ortam)

`api.binance.com` / `fapi.binance.com` erisilemiyorsa veri `data.binance.vision` arsivinden gelir.

```bash
python3.12 -m venv .venv-ft && .venv-ft/bin/pip install freqtrade==2026.10   # bir kez
.venv-ft/bin/python scripts/fetch_binance_vision.py      # veri yenile (idempotent, checksum dogrular)
F="--config config/base.json --config config/backtest.json --userdir user_data --datadir user_data/data/binance"
.venv-ft/bin/python scripts/freqtrade_offline.py list-data $F --trading-mode futures --show-timerange
.venv-ft/bin/python scripts/freqtrade_offline.py backtesting $F --strategy PlaceholderStrategy \
  --strategy-path user_data/strategies --timerange 20261001-20261101 --export none
```

- Veri `user_data/data/binance/futures/` altina (feather) yazilir; ham zip onbellegi `user_data/data/_vision_raw/` (gitignore'da).
- `config/backtest.json`: base.json'a ek (API sunucusu kapali, gecerli JWT yer tutucusu).
- `freqtrade_offline.py`: market listesini yerel veriden sentetik uretir (exchangeInfo erisilemez); precision/min-notional yaklasiktir.
- Funding verisi ayin sonunda yayinlanir; icinde bulunulan ayin funding'i eksiktir (ayri `futures_funding_rate` ile doldurulabilir).

## Test

```bash
python -m venv .venv && .venv/bin/pip install -e '.[dev]' && .venv/bin/pytest
```
