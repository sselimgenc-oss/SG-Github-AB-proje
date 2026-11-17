# research/reference — degismez referans kanit (freqtrade silinmeden once korundu)

Bu dizin, freqtrade'in kaldirilmasindan once korunan iki kanit agacini icerir. **Degismezdir**: dosyalar duzenlenmez,
yeniden uretilmez, silinmez. Yeni calisma ciktilari `research/crosscheck/` (gitignore'lu) altina yazilir.

## freqtrade-2026.10/
`user_data/backtest_results/` altindaki 30 referans kosunun kopyasi (kosu basina dizin; ID = `<tf>_<IS|WF>_f<k>_s<n>[_ek]`).
Her dizin: `backtest-result-*.zip` (freqtrade sonuc json'u, `_config.json`, `_TraderV1.py` kopyasi, wallet/market_change feather),
`*.meta.json`, `.last_result.json`, `overlay.json` (kosuya ozel config katmani), `trades_enriched.csv`, `run.log`,
`ledger.sqlite` (konsolide defter).
- `ledger.sqlite` dosyalari bare kopya degil: kaynak `file:...?mode=ro` ile acilip `sqlite3` backup API ile kopyalandi,
  `-wal`/`-shm` kopyalanmadi, hedefte `journal_mode=delete`, `integrity_check=ok`.
- Donem: IS = 2024-12-21 (backtest_start; timerange 20241101-20251101) -> 2025-11-01; WF = 2025-11-01 -> 2026-05-01.
  **Holdout (2026-05-01 -> 2026-11-01) kosusu yoktur** (30 kosunun zip'lerindeki backtest_start/end/timerange taranarak dogrulandi).
- 1h_IS_f2_s2 ve 1h_WF_f2_s2 dizinlerinde iki zip vardir (ilk kosu + tekrar); `*_rerun` dizinleri ayrica vardir.

### Surum ve config kokeni
- freqtrade **2026.10** (`run.log` ilk satiri `freqtrade 2026.10`; `docker-compose.yml` imaji `freqtradeorg/freqtrade:2026.10`).
- Strateji: `user_data/strategies/TraderV1.py`, git'e ilk giris `fa26f45` (2026-11-16); zip icindeki `_TraderV1.py`
  kopyasi calisma agacindaki dosyayla ayni (sha256 6078693414adb9c3...). Ortam/imaj `bb8d7c7`.
- Config katmanlari (run.log "Using config"): `config/base.json` + `config/backtest.json` + kosuya ozel `overlay.json`
  (timeframe, `trader_v1.params.trigger_tf`, `ledger_path`; `overlay.json` icindeki `ledger_path` eski `user_data/backtest_results/...`
  konumunu gosterir, tarihsel kayittir). Birlesik config zip'te `*_config.json` olarak saklidir
  (futures/isolated, dry_run, 10 USDT-vadeli cift, stake 100, dry_run_wallet 1000, price_side=other; jwt/api anahtarlari bos veya sahte).

## crosscheck-2026.11/
`research/crosscheck/` kopyasi: capraz dogrulama kapisi kaniti (freqtrade referansi <-> motor `legacy_compat`):
`<ID>.json/.md`, `*_lag*`, `*_chainfree*`, `1h_IS_f1_s0_model_diff.json`, `gate_{fee,funding,stakecut,closing_native_*}.json`,
`trail_lag_diag.json`. Uretici commit'ler: **9cafc86** (exit_before_entry, qty_rounding truncation, zincirsiz tani),
**5cd072b** (kanit turu: kesin-cuzdan zincirsiz tani, kapi a-d, trail-lag bayragi), **3303079** (1h iz-stop gecikme tanisi 51/51
aciklandi + mentor onayi). Karar kaydi: `docs/motor/06-crosscheck-sonuc.md`, `otonom-trading-arastirma/tasarim-kararlari.md` (17 Kasim).

## Dogrulama
```
cd trader/research/reference
sha256sum -c MANIFEST.sha256 --quiet && echo OK      # 246 dosya; MANIFEST.sha256 ve README.md kapsam disi
```
Yollar `freqtrade-2026.10/...` ve `crosscheck-2026.11/...` seklinde goreli. Bir satir basarisiz olursa agac bozulmustur:
git'ten geri yukleyin.

## Araclar
`research/bt_crosscheck.py`, `bt_chainfree_diag.py`, `bt_gate_checks.py`, `bt_trail_lag_diag.py` varsayilan referans yollarini
buradan okur (`bt_crosscheck.REF_ROOT`, `XC_REF_DIR`); `--ref`/`--xc-dir`/`--out` ile degistirilebilir. Ciktilar varsayilan olarak
`research/crosscheck/` altina yazilir, bu agaca asla.
