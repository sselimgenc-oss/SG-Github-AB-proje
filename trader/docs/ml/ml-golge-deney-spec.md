# ML gölge deneyi (learner paper) — belirtim

Tarih: 18 Kasım 2026. Dayanak: `otonom-trading-arastirma/tasarim-kararlari.md` "18 Kasım 2026 — Paper'da ders ve makine öğrenmesi açık" (kullanıcı onayı + mentor notu).

## Amaç
Öğrenen (learner) paper botta, kapıdan geçmemiş r03 modeli **yalnız gölge kipte** (`ml_mode: shadow`) yüklenir: her aday puanlanır (`ml:p=` gerekçe satırı), hiçbir aday elenmez. Testnet, canlı, ikiz ve geri test davranışı değişmez.

## G-1 Yapılandırma: `ml_experimental`
- `src/trader_engine/config.py`: yeni isteğe bağlı anahtar `ml_experimental: bool = False` (`_OPTIONAL_KEYS`'e eklenir; bool değilse ConfigError).
- Kilit: `ml_experimental: true` yalnız `mode == "paper"` **ve** `ml_mode == "shadow"` iken geçerli. Aksi her durumda (`testnet`, `live`, `ml_mode` off/active) `ConfigError` ("ml_experimental yalniz paper+shadow").

## G-2 Paket yükleme
- `src/trader_core/ml_package.py` `load_model_view(...)` ve `src/trader_engine/strategies/price_action_v1_ml.py` `load_engine_model(...)`: yeni anahtar kelime argümanı `experimental: bool = False`.
- `experimental=True` yalnız `ml_mode == "shadow"` ile kabul edilir (aksi `ValueError`); bu durumda kapı denetimi (`gate_passed`, `threshold` null) atlanır (`load_package(..., require_gate=False)`). **Hash denetimleri ve süre (21 gün) denetimi aynen kalır.** Eşik null ise gölge puanlama yine yapılır; `threshold` görünümde `0.5` yerine paketteki değer, null ise `0.5`.
- `MlModelView`'a `experimental: bool` alanı (varsayılan False) eklenir; gerekçe/log satırlarında `ml_exp=1` görünür.
- `experimental=False` iken mevcut davranış bit bit aynıdır (kapı reddi dahil).

## G-3 Motor aktarımı
- `src/trader_engine/engine.py` (~1995–2010): `load_engine_model(..., experimental=cfg.ml_experimental)`. Başka değişiklik yok.
- Model yüklenemezse ya da süresi dolarsa: gölgede mevcut davranış (uyarı + sayaç, bot ML'siz sürer). Sağlık uyarısı için mevcut sayaç yeterli; yeni alarm ayrı iş.

## G-4 Learner yapılandırması
- `config/engine.learner.json`: `{"bot": "learner", "strategy": "price_action_v1_ml", "ml_mode": "shadow", "ml_features": <r03 tarifi>, "ml_model_path": "models/ml1-r03.json", "ml_experimental": true}`. `ml_features` değeri r03 paketinin `meta.features` listesiyle eşleşen `RECIPE_NAMES` anahtarıdır (uygulayıcı bulur, belgeler).
- Model dosyası `research/ml/r03/model_candidate.json`'dan `models/ml1-r03.json`'a kopyalanır (kaynak değişmez). `config/engine.base.json`, `engine.twin.json`, `engine.testnet.json`, `engine.live.json` değişmez.

## G-5 Tarafsızlık
- `ml_mode: off` iken `price_action_v1_ml` çıktısı v1b ile birebir aynı (mevcut test). Altın geri test (`tests/test_wp3_golden.py`, `tests/engine/test_risk_ladder_impl.py::test_t28_backtest_digest_unchanged`) değişmez.
- Gölge kipte learner'ın işlem/karar kümesi, aynı veriyle `ml_mode: off`'takiyle aynıdır (yalnız gerekçe satırına `ml:p=` eklenir).

## Testler (bağımsız yazar)
| Kod | Davranış |
|---|---|
| G-T1 | `ml_experimental` true + paper + shadow → yüklenir; testnet/live/off/active ile → ConfigError. Bool olmayan değer → ConfigError. |
| G-T2 | Kapıdan geçmemiş paket: `experimental=False` → yüklenmez (mevcut ret); `experimental=True` + shadow → yüklenir, `view.experimental is True`. |
| G-T3 | `experimental=True` + `ml_mode="active"` → ValueError. |
| G-T4 | Hash bozuk ya da süresi dolmuş paket `experimental=True` iken de reddedilir. |
| G-T5 | `config/engine.learner.json` yüklenir; diğer dört yapılandırma `ml_experimental` içermez; base `ml_mode` "off". |
| G-T6 | `models/ml1-r03.json` içeriği `research/ml/r03/model_candidate.json` ile bayt bayt aynı. |

## Uygulama notu (18 Kasım 2026)
- `models/` dizini `.gitignore` kapsamında DEĞİL (izlenen konum); `models/ml1-r03.json` `research/ml/r03/model_candidate.json`'ın bayt kopyasıdır.
- `ml_features` anahtarı `"r03"`: `RECIPE_NAMES["r03"]` r03 paketinin `meta.features` listesiyle (8 öznitelik) birebir eşleşir (`r02` eşleşmez).
- r03 paketi: `created_at` 2026-11-18T15:27Z, süre sınırı 2026-12-09T15:27Z (21 gün); `gate_passed=false`, `threshold=0.5`. Süre dolunca gölgede model yüklenmez (uyarı + sayaç), bot ML'siz sürer.
- `ml_model_path` göreli (`models/...`) ve çalışma dizinine göre çözülür (diğer paper yolları gibi); servis kökü depo kökü olmalıdır.
- Gerekçe etiketi: deneysel modelde `ml:p=0.xxxxxx|ml_exp=1|...`.

## Düzeltme notu (18 Kasım 2026, G-4 / G-T5)
`config/engine.learner.json` testnet ve canlı hizmetler (`--bot learner --env testnet|live`) ile geri testler/altın testler tarafından da yüklenir; ML anahtarları orada `ml_experimental` kilidini kırar ve ML'yi testnet/canlıya sızdırır. Bu yüzden:
- `config/engine.learner.json` aynen `{"bot": "learner"}` kalır.
- ML anahtarları yalnız kâğıt katmanı `config/engine.paper-ml.json` içindedir (`strategy`, `ml_mode: shadow`, `ml_features: r03`, `ml_model_path`, `ml_experimental: true`); CLI `--env paper-ml` kabul eder.
- Dağıtım: `deploy/trader-engine@learner.service.d/ml-shadow.conf` yalnız `trader-engine@learner` birimine `--env paper-ml` ekler (`install.sh` kopyalar); ikiz, testnet, canlı, base değişmez.
- G-T5 böyle okunur: `engine.learner.json == {"bot":"learner"}`; `engine.paper-ml.json` ML anahtarlarını taşır ve yüklenir (`load_cli_config(..., "learner", "paper-ml")`); diğer dört yapılandırma `ml_experimental` içermez; base `ml_mode` "off".
- Mevcut öğrenen defteri `price_action_v1` etiketliyse motor `strategy_mismatch` verir; defter `init-ledger ... --reason strategy_update` ile ya da yeni defterle taşınmalıdır (aynı params ile `create_user_version` "no_change" verebilir; bkz. rapor).
