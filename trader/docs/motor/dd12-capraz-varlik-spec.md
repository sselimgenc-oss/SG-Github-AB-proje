# DD-12: Yeni kâğıt evreni (20 kripto + ABD hisseleri + 4 emtia) — belirtim

Tarih: 18 Kasım 2026 (mentor). Sürüm 2: kullanıcının aynı günkü güncellemesiyle 11 sembollük ilk liste yerine geçti. Dayanak: `tasarim-kararlari.md` "Mag7 + emtia şimdi ekleniyor" ve "kâğıtta deneyerek öğrenme tutumu" (`1694322`); kullanıcı: "Enstrümanları değiştiriyorum: stabil coin hariç piyasa değeri en yüksek 20 coin, piyasa değeri en yüksek 20 ABD hissesi, altın, gümüş, Brent, bakır." Bu belge kod, test ve commit içermez.

**Çalışma tutumu.** Kâğıtta deneyip canlı gözlemle öğrenilir; istatistik kesinlik beklenmez ve eksikliği bu işi durdurma gerekçesi değildir. Değişmeyenler: gerçek para kapısı (CANLI-K1; para ve canlı anahtar yok), S2 ön kaydı, kilitli dönem. Hisse/emtia kolu **DENEY** etiketlidir; sonuçları CANLI-K1, ML kapısı ya da S2 kanıtı sayılmaz.

## 0. Özet

| Kim | Evren | Not |
|---|---|---|
| Kâğıt öğrenen + ikiz | 20 kripto (aynı liste) | Bugünkü 10 çiftin üst kümesi; açık pozisyon ve defter sürer |
| Kâğıt `cross` kolu (yeni, 3. motor) | 18 hisse + 4 emtia = 22 | DENEY; veto, ML, ders yok; kendi feed'i ve dizini |
| Testnet (14 Aralık), canlı | 10 çift (taban) | Değişmez |
| Araştırma (S2, derlem, ML yeniden eğitim) | 10 çift (taban) | Değişmez; ön kayıt donuk |

- `config/engine.base.json` **değişmez**: araştırma, testnet ve canlı çift listesini oradan okur. Kâğıt evrenleri katmanla gelir: `engine.paper.json` (20 kripto), `engine.cross.json` (22).
- Yeni bot adı yok. Cross kolu testnet kalıbıyla çalışır: `run --bot learner --env cross`, ayrı `var-cross/`. Defter şemasına (`CHECK (bot IN ('learner','twin'))`, 10+ tablo) dokunulmaz.
- İstenen 44 enstrümandan 42'si var: MA (Mastercard) ve JNJ (Johnson & Johnson) Binance USDⓈ-M'de listeli değil, atlandı.
- Sunucu: A aşaması (20 kripto) 2 GB'a sığar. B aşaması (cross) ölçümle açılır; 14 Aralık testnet koşusuyla birlikte 2 GB dardır. **Öneri: sunucuyu 4 GB'a büyütmek** (kullanıcı işi).

## 1. Evren

Kaynak: `data.binance.vision` USDⓈ-M arşiv dizini (18 Kasım 2026; yalnız dizin ve dosya adları listelendi, veri indirilmedi). "İlk ay" = arşivdeki ilk aylık dosya. Piyasa değeri sıralaması mentorun bilgisine dayanır, **doğrulanmadı**; liste kullanıcı onayıyla sabitlenir ve kendiliğinden güncellenmez (yeniden sıralama = yeni karar).

**Kripto (20)** — stabil (USDT, USDC, DAI, FDUSD, USDe, USDS) ve sarılı/stake kopyalar (WBTC, stETH, wstETH, WETH, WBETH) hariç; LEO Binance vadelide yok.

BTC, ETH, XRP, BNB, SOL, DOGE, TRX, ADA, HYPE (2025-05), LINK, BCH, XLM, SUI (2023-05), AVAX, HBAR, LTC, TON (2024-03), SHIB (sözleşme adı `1000SHIBUSDT`, çift `1000SHIB/USDT`), DOT, XMR.

Mevcut 10 çiftin hepsi listededir. Yedek (sıra değişmişse): ZEC, UNI.

**ABD hisseleri (20'den 18'i listeli)**

| # | Hisse | Sembol | İlk ay | # | Hisse | Sembol | İlk ay |
|---|---|---|---|---|---|---|---|
| 1 | Nvidia | NVDAUSDT | 2026-03 | 11 | Eli Lilly | LLYUSDT | 2026-06 |
| 2 | Microsoft | MSFTUSDT | 2026-04 | 12 | Walmart | WMTUSDT | 2026-05 |
| 3 | Apple | AAPLUSDT | 2026-04 | 13 | Visa | VUSDT | 2026-05 |
| 4 | Alphabet | GOOGLUSDT | 2026-03 | 14 | Oracle | ORCLUSDT | 2026-05 |
| 5 | Amazon | AMZNUSDT | 2026-02 | 15 | Mastercard | — | **yok** |
| 6 | Meta | METAUSDT | 2026-03 | 16 | Exxon Mobil | XOMUSDT | 2026-09 |
| 7 | Broadcom | AVGOUSDT | 2026-04 | 17 | Netflix | NFLXUSDT | 2026-06 |
| 8 | Tesla | TSLAUSDT | 2026-01 | 18 | Johnson & Johnson | — | **yok** |
| 9 | Berkshire B | BRKBUSDT | 2026-05 | 19 | Palantir | PLTRUSDT | 2026-02 |
| 10 | JPMorgan | JPMUSDT | 2026-05 | 20 | Costco | COSTUSDT | 2026-06 |

Kullanıcı 20'ye tamamlamak isterse listeli sıradaki adaylar: AMD (2026-05), Home Depot (2026-05). Varsayılan: tamamlanmaz, 18 ile gidilir.

**Emtia (4):** XAUUSDT altın (2025-12), XAGUSDT gümüş (2026-01), BZUSDT Brent (2026-04), COPPERUSDT bakır (2026-03).

**Doğrulanacak (adım 0, sunucuda; bu ortamdan Binance API 451 döndü):** 42 sembolün `exchangeInfo`'da `status=TRADING` olduğu, hisse/emtia için `contractType` değeri (beklenen `TRADIFI_PERPETUAL`), filtreler, kapalı seansta 1 dk mum gelip gelmediği. `TRADING` olmayan sembol listeden çıkarılır ve bildirilir; kalanlarla devam edilir.

## 2. Kararlar ve gerekçeleri

**K1 — Öğrenen ve ikiz 20 kriptoya geçer, 42'ye değil.** Hisse ve emtiayı öğrenen/ikize koymak dört şeyi aynı anda bozar: veto (belge 84 karar olur, bağlam BTC'ye dayalı), ders servisi (kripto ve hisse işlemleri tek kanıt havuzunda karışır), ML gölgesi (eğitim evreni dışı) ve açılış kapısı (kapalı seanstaki tek hisse iki çekirdek botu durdurur). 20 kripto ise aynı türdür, 7/24 açıktır, mevcut 10'un üst kümesidir. Kıyas korunur: iki bot aynı anda, aynı listeye geçer; defterler ve 10 R freni sürer; raporlarda "evren 10 → 20" tarihi işaretlenir. Kâğıt yeni başladığı için maliyeti düşüktür.

**K2 — Hisse + emtia ayrı `cross` kolunda.** Ayrı süreç, ayrı feed, ayrı veritabanı (`var-cross/market.sqlite`), ayrı defter, ayrı KILL/PAUSE (`shared/cross/`). Yeni sembollerdeki kural/veri arızası çekirdek feed'i ve öğrenen/ikizi düşüremez. Strateji aynı (v1b), ML `off`, ders/karşı-olgu/sapma zamanlayıcıları kurulmaz, `shadow_blocks` boş.

**K3 — Taban dosya donuk; kâğıt evreni katmanla.** `--env` virgüllü liste kabul eder, katmanlar sırayla birleşir: ikiz `--env paper`, öğrenen `--env paper,paper-ml`, cross `--env cross`. Testnet/canlı birimleri değişmez ve 10 çiftte kalır. Böylece S2 koşuları, `build_corpus_v2.py`, ML yeniden eğitimi, OI toplayıcı ve geri test varsayılanı aynı 10 çifti okumayı sürdürür.

**K4 — ML gölgesi (r03) yalnız eğitim evreninde puanlar.** r03 10 çiftle eğitildi; bağlam özellikleri (genişlik, BTC/ETH) o 10 çift üzerinden tanımlı. Bağlamı 20 çifte genişletmek eski 10 çiftin puanlarını da kaydırır. Bu yüzden: ML bağlam evreni sabit 10 çifttir (`ml_pairs`, `engine.paper-ml.json`); bu 10 çiftin adayları bugünkü gibi puanlanır ve "ML açık olsaydı" kolu aynı tanımla sürer. Yeni 10 çiftin adayları puanlanmaz, `ml_status="out_of_universe"` olarak kaydedilir. Gölge hiçbir adayı elemediği için işlemler etkilenmez. 14 günlük yeniden eğitim aynı tarifle 10 çiftte kalır. 20 çiftli model = yeni tarif = yeni ön kayıt (şimdi değil).

**K5 — Veto: öğrenen/ikizde 20 çift için açık, cross'ta kapalı.** `veto.json` `pairs_from` → `config/engine.paper.json:pairs`; belge 40 karar taşır. Çıktı sınırı yetmeyebilir: `max_tokens` üst sınırı 2000 → 4000, değer 3600. Cross için `veto_mode="off"` (yalnız `paper` + `experimental`); defterde neden `not_evaluated:experimental`.

**K6 — Testnet 10 çiftte kalır.** Yeni sembollerin testnette varlığı doğrulanmadı; testnetin amacı emir yolunu sınamaktır, evren genişliği değil. Kâğıt–testnet karşılaştırması yalnız ortak 10 çift üzerinden yapılır.

**K7 — Kurallar gerçek `exchangeInfo`'dan** (feed saatte bir yeniler, `rules` tablosu). `--synthetic-rules` yalnız geri testtedir. `extract_rules` bugün `contractType != "PERPETUAL"` olanı reddeder; kabul listesi parametreye çevrilir, yalnız cross genişletir.

**K8 — Isınma ve kısa geçmiş.** v1b ısınması ≈ 50 gün (1h 1200, 15m 4800, 4h 300 bar; kesintisizlik tetik 20, 4h 150). Feed geri doldurması bunu karşılar. En yeni sembol XOM (2026-09): sınırda; yetmezse yalnız o çift `no_history` ile bekler, motor durmaz. Yeni 10 kriptonun hepsi yeterli geçmişe sahip.

**K9 — Seans ve ince piyasa (yalnız cross, yalnız yeni giriş).** Kapalı seansta fiyat düz/ince olur, ATR küçülür, miktar büyür, açılış boşluğu stopu aşar. İki koruma: (a) küme seans penceresi dışında giriş yok; (b) son kapanmış tetik barında `volume == 0` ya da `high == low` ise giriş yok (tatilleri de yakalar). Açık pozisyonun stop/hedef yönetimi her zaman sürer; hafta sonuna taşınan pozisyon kapatılmaz, boşluk zararı kâğıtta görülür. Göstergeler (`signals.py`, donuk) 7/24 dizide aynen hesaplanır; düz barların etkisi düzeltilmez, izlenir.

**K10 — Açılış kapısı.** Öğrenen/ikiz: 20/20, aynen. Cross: adım 0'da kapalı seansta da 1 dk mum geldiği görülürse 22/22 aynen. Gelmiyorsa cross için `startup_gate="rules_only"` (yalnız `experimental`): kural 22/22 + en az bir çiftte taze veri yeter; bayat çift çalışma anında zaten `stale_data` ile giriş yapmaz. Cross çıkış 7'de 5 dakikada bir yeniden dener, saatte 6 denemeden sonra `failed` + Telegram alarmı.

**K11 — Ortak IP, ortak ban.** İki feed aynı IP'den çıkar. Cross feed çekirdeğin ban dosyasını (`var/`) salt okunur ek kaynak olarak dikkate alır; kendi kaydını `var-cross/`a yazar.

**K12 — Cross maliyet modeli (tahmin).** Komisyon 5 bp; kayma tabanın iki katı (giriş 4, çıkış 4, stop 10 bp). İki hafta sonra `bookTicker` yayılımına bakılıp bir kez ayarlanabilir.

## 3. Risk

İşlem başı risk **%0,5 aynen**. Hesap sınırları aynen (`risk.py`: toplam açık risk %6, aynı yön %4, günlük zarar). Üstüne iki yeni, yalnız kâğıt katmanlarında tanımlı sınır: hesap geneli `max_positions` ve küme tavanları. Bir çift birden çok kümede olabilir; hepsinde yer olmalıdır. Sayım açık ve açılmakta olan pozisyonları kapsar; aynı barda sıra `pairs` sırasıdır.

| Bot | Küme | Çiftler | Tavan | Seans (giriş) |
|---|---|---|---|---|
| öğrenen/ikiz | `kripto_buyuk` | BTC, ETH, XRP, BNB, SOL | 3 | — |
| | `kripto_diger` | kalan 15 | 5 | — |
| | hesap geneli | 20 | **8** (≤ %4 açık risk) | — |
| cross | `hisse` | 18 hisse | 3 | New York 09:30–16:00, Pzt–Cum |
| | `hisse_teknoloji` | NVDA, MSFT, AAPL, GOOGL, AMZN, META, AVGO, TSLA, ORCL, NFLX, PLTR | 2 | (aynı) |
| | `metal` | XAU, XAG | 1 | Paz 23:00 → Cum 21:00 UTC |
| | `enerji_sanayi` | BZ, COPPER | 1 | Paz 23:00 → Cum 21:00 UTC |
| | hesap geneli | 22 | **5** (≤ %2,5 açık risk) | — |

Öğrenen ve ikiz aynı küme tanımını okur (aynı katman dosyası). Testnet/canlıda `clusters`/`max_positions` verilemez (yapılandırma hatası); oraya taşınması ayrı karardır.

## 4. Yapılandırma

`config/engine.paper.json` (yeni; öğrenen ve ikiz):
```json
{"pairs": ["BTC/USDT","ETH/USDT","XRP/USDT","BNB/USDT","SOL/USDT","DOGE/USDT","TRX/USDT","ADA/USDT","HYPE/USDT","LINK/USDT",
           "BCH/USDT","XLM/USDT","SUI/USDT","AVAX/USDT","HBAR/USDT","LTC/USDT","TON/USDT","1000SHIB/USDT","DOT/USDT","XMR/USDT"],
 "max_positions": 8,
 "clusters": {"kripto_buyuk": {"pairs": ["BTC/USDT","ETH/USDT","XRP/USDT","BNB/USDT","SOL/USDT"], "max_positions": 3},
              "kripto_diger": {"pairs": ["…kalan 15…"], "max_positions": 5}}}
```
`config/engine.paper-ml.json` (ek anahtar): `"ml_pairs": [taban 10 çift]`.

`config/engine.cross.json` (yeni):
```json
{"experimental": true,
 "pairs": ["NVDA/USDT","MSFT/USDT","AAPL/USDT","GOOGL/USDT","AMZN/USDT","META/USDT","AVGO/USDT","TSLA/USDT","BRKB/USDT","JPM/USDT",
           "LLY/USDT","WMT/USDT","V/USDT","ORCL/USDT","XOM/USDT","NFLX/USDT","PLTR/USDT","COST/USDT",
           "XAU/USDT","XAG/USDT","BZ/USDT","COPPER/USDT"],
 "var_dir": "var-cross", "market_db": "var-cross/market.sqlite", "history_dir": "var-cross/history",
 "kill_file": "shared/cross/KILL", "pause_file": "shared/cross/PAUSE",
 "veto_mode": "off", "ml_mode": "off", "shadow_blocks": [],
 "cost": {"slip_entry_bps": 4.0, "slip_exit_bps": 4.0, "slip_stop_bps": 10.0},
 "contract_types": ["PERPETUAL", "TRADIFI_PERPETUAL"],
 "max_positions": 5, "flat_bar_guard": true,
 "clusters": {
   "hisse": {"pairs": ["…18…"], "max_positions": 3,
             "session": {"tz": "America/New_York", "days": [0,1,2,3,4], "open": "09:30", "close": "16:00"}},
   "hisse_teknoloji": {"pairs": ["…11…"], "max_positions": 2},
   "metal": {"pairs": ["XAU/USDT","XAG/USDT"], "max_positions": 1,
             "session": {"tz": "UTC", "week_open": "Sun 23:00", "week_close": "Fri 21:00"}},
   "enerji_sanayi": {"pairs": ["BZ/USDT","COPPER/USDT"], "max_positions": 1,
                     "session": {"tz": "UTC", "week_open": "Sun 23:00", "week_close": "Fri 21:00"}}}}
```
`config/veto.json`: `pairs_from` → `config/engine.paper.json:pairs`, `max_tokens` 3600.

## 5. Dosya dosya değişiklikler

**Dokunulmaz:** `s2-on-kayit.md` §1.8 listesi (`scripts/build_corpus_v2.py`, `research/ml_build_candidates.py`, `trader_ml/{features,features_v2,labels,guards,config}.py`, `trader_core/{ml_features,ml_features_v2,signals,regime,indicators}.py`, `trader_engine/holdout.py`); ayrıca `ledger.py` (şema sürümü 4, göç yok), `engine.base.json`, `engine.learner.json`, `engine.twin.json`, `engine.testnet.json`, `engine.live.json`, `risk.py`, `brokers/paper.py`, `order_manager.py`, `research/*`. freqtrade/ccxt/python-binance yok.

| Dosya | Değişiklik |
|---|---|
| `src/trader_engine/config.py` | Yeni isteğe bağlı anahtarlar, verilmezse davranış bit bit aynı: `max_positions: int \| None`, `clusters` (çiftler `pairs` içinde; `max_positions ≥ 1`; isteğe bağlı `session`), `ml_pairs: tuple \| None` (hepsi `pairs` içinde), `experimental: bool`, `contract_types` (varsayılan `("PERPETUAL",)`), `flat_bar_guard: bool`, `startup_gate: "all" \| "rules_only"`. Kurallar: `clusters`/`max_positions` yalnız `paper`/`backtest`; `experimental` yalnız `paper`; `veto_mode="off"` yalnız `backtest` ya da `paper`+`experimental`; `session`, `flat_bar_guard`, `startup_gate≠all`, genişletilmiş `contract_types` yalnız `experimental`. `experimental` iken: `var_dir` son bileşeni `var` olamaz, `market_db` `var_dir` altında, `kill_file`/`pause_file` `shared/KILL`/`shared/PAUSE` olamaz, `ml_mode="off"`, `ladder_follow` yok; `var_dir` mutlaklaştırılır. `load_cli_config`: `env` virgüllü liste, katmanlar sırayla. |
| `src/trader_engine/cli.py` | `--env` seçenek listesi yerine ad kalıbı (`^[a-z][a-z0-9-]{0,19}$`, virgüllü); dosyası olmayan ad hata. |
| `src/trader_engine/exchange/rules.py` | `extract_rules(..., *, contract_types=("PERPETUAL",))`, `extract_all_rules` aynı parametre. Canlı/testnet çağrıları parametre vermez. |
| `src/trader_engine/marketdata/feed.py` | `feed` ve `rules-snapshot` için `--env` (taban üstüne katman; yalnız `pairs`, `var_dir`, `market_db`, `history_dir`, `contract_types` okunur; pandas yüklenmez). `--also-ban-dir <dizin>` (salt okunur ek ban kaynağı). `--env` yokken çıktı aynı. |
| `src/trader_core/ban_store.py` | `BanGuard(..., extra_paths=())`: ek dosyalar yalnız okunur. |
| `src/trader_engine/cross_guard.py` (yeni, saf) | `clusters_of`, `session_open(cluster, now)` (`zoneinfo`), `caps_full(cfg, pair, open_pairs) -> str \| None`, `flat_bar(bar)`. |
| `src/trader_engine/gates.py` | `decide`: kural adımından (9) sonra, vetodan (10) önce; yalnız ilgili anahtar doluysa: seans → düz bar → küme tavanı → hesap `max_positions`. Reddedilen aday mevcut defter değerleriyle yazılır: `skip_reason="risk_denied"`, `risk_allowed=False`, `veto_status="allowed"`, `risk_reason` ∈ {`session_closed:<küme>`, `flat_bar`, `cluster_cap:<küme>`, `max_positions`}; sayaçlar `skip:<kod>`. |
| `src/trader_engine/engine.py` | `NoVeto` nedeni `experimental` iken `not_evaluated:experimental`; `startup_gate="rules_only"` dalı; `LiveContextV2` `ml_pairs` (yoksa `pairs`) ile kurulur, evren dışı aday puanlanmaz (`out_of_universe`); `status.json`'a `env`, `experimental`, küme başına açık sayı. |
| `src/trader_engine/strategies/price_action_v1_ml.py` | Evren dışı çiftte puanlama atlanır, kayıt `out_of_universe`; gölge kipte eleme yok (bugünkü gibi). |
| `src/trader_core/veto.py` | `max_tokens` üst sınırı 4000. Başka değişiklik yok. |
| `config/` | §4. |
| `deploy/trader-engine@.service` | `--env paper` (init-ledger ve run). `trader-engine@learner.service.d/ml-shadow.conf`: `--env paper,paper-ml`. `trader-feed.service`: `--env paper`. |
| `deploy/trader-cross.slice` (yeni) | `MemoryHigh=360M`, `MemoryMax=450M`. |
| `deploy/trader-feed-cross.service` (yeni) | `trader-feed.service` kalıbı; `Slice=trader-cross.slice`; `feed --config-dir config --env cross --startup-retry forever --also-ban-dir /opt/trader/var`; `MemoryHigh=100M`, `MemoryMax=140M`; `OOMScoreAdjust=300`; `ReadWritePaths=/opt/trader/var-cross`. |
| `deploy/trader-engine-cross.service` (yeni) | `trader-engine-testnet.service` kalıbı, **anahtar dosyası yok**; `Slice=trader-cross.slice`; `After/Wants=trader-feed-cross.service`; `run --bot learner --env cross --config-dir config --ensure-ledger`; `RestartSec=300`, `RestartPreventExitStatus=2 8`, `StartLimitIntervalSec=3600`, `StartLimitBurst=6`; `OnFailure=trader-health-fail@%n.service`; `MemoryHigh=260M`, `MemoryMax=330M`; `OOMScoreAdjust=300`; `CPUQuota=40%`; `ReadWritePaths=/opt/trader/var-cross /opt/trader/shared/cross`. |
| `deploy/install.sh`, `uninstall.sh` | `--with-cross` (varsayılan kapalı) / `--no-cross`; dizinler `var-cross/`, `var-cross/history/`, `shared/cross/`; sağlık ortamına `MARKET_PAIRS` = `engine.paper.json` listesi; `CROSS_*` yolları (§8). |
| `scripts/health_backup.py` | `var-cross/learner/ledger.sqlite` yedeğe eklenir (varsa). |
| `src/trader_core/{telegram,health}.py`, `scripts/report_run.py`, `src/trader_panel/*`, `config/panel.json` | §8. |
| `docs/` | `00-index.md` DD-12 satırı; `sunucu-kurulum.md` "Yeni kâğıt evreni" bölümü. |

OI toplayıcı (`oi_collect.py`) ve `fetch_binance_vision.py` tabandaki 10 çiftte kalır.

## 6. S2, kilitli dönem, kirlenme

- **S2 değişmez.** Ön kayıt 10 çiftle donuk ("taban yapılandırmadaki liste"); taban dosya değişmediği için S2 koşuları, derlem ve ML yeniden eğitimi aynı girdiyi okur. S2 §8 tarafsızlık testleri ve altın testler bu belgenin her kod commit'inde geçmelidir.
- **Kilitli dönem (2026-05-01 → 2026-11-01) araştırma kuralıdır, aynen.** Canlı feed'in ısınma geri doldurması bu döneme ait barları `market.sqlite`'a yazar; çekirdek feed bugün de bunu yapıyor, canlı karar için gereklidir. Yasak olan: bu döneme değen geri test, tarama, dilimleme. `backtest`/`run_range` `check_holdout` ile, `fetch_binance_vision.py` URL üretmeyerek zaten engeller. `market.sqlite` dosyaları araştırma betiğiyle okunmaz.
- **Hisse ve emtiada kilit öncesi geçmiş neredeyse yok** (çoğu 2026-03 sonrası listelendi, sekizi kilit döneminin içinde). Bu sembollerde anlamlı geri test yapılamaz; kol yalnız ileriye dönük kâğıt gözlemdir. İleride geri test = ayrı ön kayıt, S2'nin 6 hakkından bağımsız.
- **Yeni 10 kriptoda** uzun geçmiş var; onlarla geri test ya da evren genişletme araştırması yine ayrı ön kayıt ister. Şimdi yapılmaz.
- **Gözleme dayalı ayar:** 18 Kasım sonrası kâğıt sonuçlarına bakıp küme tavanı, seans, kayma gibi DD-12 ayarlarını değiştirmek serbesttir (tarihli not). Aynı gözlemle v1b parametresi ya da S2 tanımı değiştirilmez.
- **Ders servisi:** öğrenen kanıt havuzu 20 çifte genişler; işlem sıklığı kabaca iki katına çıkar, 30 işlem eşiğine daha çabuk ulaşılır. Korumalar aynen. Cross defterini ders servisi açmaz.

## 7. Kapasite (2 GB sunucu)

Aşağıdaki bellek sayıları **tahmindir**; sunucuda bugünkü `MemoryCurrent`/`MemoryPeak` ölçülmeden kesinleşmez.

**REST ağırlığı (sınır 2400/dk, istemci eşiği 1800):** sürekli 2 istek/çift/dk → çekirdek 40 + cross 44 = 84/dk. Saat başı tepe (15m + 1h + 4h kapanışı + fonlama + kurallar) ≈ 260/dk. Geri doldurma bir kerelik: çift başına ≈ 120 ağırlık → yeni 10 kripto ≈ 1200, cross 22 çift ≈ 2600 (istemci kendini kısar, 2–3 dk). Cross feed, çekirdek geri doldurması bittikten sonra başlatılır. Sıralı tur süresi ≈ 6–8 sn/dk; tazelik sınırı 5 dk.

**Disk:** 1 dk barlar 14 gün tutulur, çift başına ≈ 4,5 MB → çekirdek ≈ 90 MB, cross ≈ 100 MB. 15m/1h/4h süresiz: 42 çift ≈ 170 MB/yıl. Sorun değil.

**Bellek (tahmini RSS, MB):**

| Birim | Bugün (10 çift) | Yeni |
|---|---|---|
| trader-feed | ~55 | ~65 (20 çift) |
| öğrenen (ML gölge) | ~200 | ~230 |
| ikiz | ~160 | ~190 |
| pano + telegram | ~110 | ~110 |
| **A aşaması toplamı** | ~525 | **~595** |
| cross motor (22 çift) | — | ~190 |
| cross feed | — | ~65 |
| **A + B** | | **~850** |
| testnet gölge (14 Aralık) | — | ~180 |
| **A + B + testnet** | | **~1030** |
| işletim sistemi | | ~230 |
| geçici işler (pano yayını node ~250, ders, veto, sağlık) | | ~300 tepe |
| **En kötü an** | | **~1560 / 1960** |

Değerlendirme: A aşaması 2 GB'a rahat sığar; çekirdek birim tavanları (280M/350M) ve `trader.slice` (1100M/1300M) aynen kalır. A + B testnet yokken sığar. A + B + testnet + pano yayını anında boş bellek ≈ 300–400 MB'a iner; motor tahminleri %20 saparsa takasa girilir. Çalışır ama pay dardır.

**Öneri (kullanıcı işi): sunucuyu 4 GB'a büyütmek**, en geç 14 Aralık'tan önce. Yalnız CPU/RAM büyütmesi; birkaç dakikalık kapalı kalma, IP değişmez, geri alınabilir; aylık ücret yaklaşık iki katına çıkar. LON1'de büyütmenin açık olduğu doğrulanmadı. 4 GB'da tavanlar değişmez, yalnız pay açılır.

**Büyütülmezse (en küçük değişiklik):** A hemen; B yalnız ölçüm geçerse (`free -m` available ≥ 500 MB, `trader.slice` MemoryPeak ≤ 850 MB); 14 Aralık'ta testnet önceliklidir, available < 300 MB ise cross durdurulur.

**Koruma:** cross ayrı slice'ta (360M/450M) ve `OOMScoreAdjust=300`: baskıda pano yayınından (+500) sonra, çekirdekten (−200) önce ölür. `test_readiness_memory` çekirdek değerleri değişmez.

**İzlenecek (ilk 48 saat, sonra haftalık):** `systemctl show trader-engine@learner trader-engine@twin trader-feed trader-engine-cross trader-feed-cross -p MemoryCurrent -p MemoryPeak`; `free -m` available ve takas; `journalctl -k | grep -i oom`; öğrenenin `MemoryCurrent`'ı 250 MB'ı geçiyorsa (yumuşak tavana yakın) bildirilir; motor döngü gecikmesi (`status.json`); feed `used_weight`.

## 8. Telegram ve pano

- **Öğrenen/ikiz:** raporlar ve pano çift listesini durum dosyasından alır; 20 çift kendiliğinden görünür. Günlük raporda bir kez "Evren 10 → 20 çift: <tarih>" satırı; ML satırında "puanlanan / evren dışı" aday sayısı. Küme atlamaları mevcut "risk reddi" sayımına nedenleriyle girer.
- **Cross (ortam anahtarları boşsa kapalı):** `CROSS_STATUS_PATH`, `CROSS_LEDGER_PATH`, `CROSS_FEED_STATUS`.
  - Telegram günlük raporda ayrı blok, başlık "Hisse + emtia (DENEY, kâğıt)": bugün kapanan işlem ve net R, açık pozisyonlar (küme adıyla), başlangıçtan toplam, atlama sayıları (`session_closed`, `flat_bar`, `cluster_cap`, `max_positions`). Komut `/capraz`. Öğrenen–ikiz farkı, ders ve ML satırlarına girmez. `/durdur` ve `/kademe` cross'a dokunmaz.
  - Sağlık: motor durumu > 15 dk eski, feed durumu > 10 dk eski → en çok WARN. Birim `failed` → mevcut `trader-health-fail@` alarmı (ek kod yok).
  - Pano: `cross_status_path`, `cross_ledger_path` doluysa ayrı kart "Hisse + emtia — DENEY" (öz varlık, açık pozisyonlar, son 20 işlem, küme sayıları). `BOTS` ve `diff_pnl` değişmez.

## 9. Dağıtım

**Adım 0 (yoklama, sunucuda):** `exchangeInfo`'da 42 sembol; her biri için `klines` ve `markPriceKlines` 1m; bir hafta sonu saatinde yineleme. Sonuç bu belgeye tarihli ek; listeler ve K10 seçimi kesinleşir.

**A aşaması — öğrenen/ikiz 20 kripto**
1. Kod + testler birleşir (mentor incelemesi zorunlu; altın ve S2 tarafsızlık testleri değişmeden geçer).
2. `install.sh`; `rules-snapshot --env paper` → 20/20.
3. `systemctl restart trader-feed`; geri doldurma bitene kadar beklenir.
4. Öğrenen ve ikiz **aynı dakikada** yeniden başlatılır; günlükte "acilis kapisi tamam: 20/20". Açık pozisyonlar sürer.
5. Veto turu 40 kararla geçti mi; sağlık temiz mi; bellek ölçümü.
6. `tasarim-kararlari.md`'ye geçiş tarihi (ayrı commit, belge sahibi).

**B aşaması — cross** (bellek ön ölçümü ya da 4 GB sonrası)
1. `install.sh --with-cross`; `rules-snapshot --env cross` → 22/22.
2. `trader-feed-cross` geri doldurma; `trader-engine-cross` "acilis kapisi tamam".
3. Yan etki denetimi: öğrenen/ikiz durum damgaları ilerliyor, çekirdek feed'de yeni hata yok.
4. 48 saat bellek izleme.

**Geri alma:** A için birimler `--env` eki olmadan önceki sürüme döner; taban 10 çift yerindedir. Yeni 10 çiftte açık kâğıt pozisyon varsa önce `pause` ile yeni giriş kapatılır, pozisyonlar stop/hedefle kapanınca dönülür. B için `install.sh --no-cross`; `var-cross/` silinmez.

## 10. Testler (bağımsız yazar)

| Kod | Davranış |
|---|---|
| X-T1 | Katmansız yükleme (`learner`, `twin`, `testnet`, `live`) bu değişiklikten önceki `EngineConfig` ile eşit; yeni alanlar varsayılanda; 10 çift. |
| X-T2 | `--env paper` (ikiz) ve `--env paper,paper-ml` (öğrenen): çift listeleri ve küme tanımları **özdeş**, 20 çift, taban 10 çiftin üst kümesi; öğrenende `ml_pairs` = taban 10. `engine.base.json` içeriği sabit karma ile korunur. |
| X-T3 | `--env cross`: 22 çift, `var-cross` yolları mutlak, veto `off`, ML `off`, `experimental`. |
| X-T4 | Reddedilen yapılandırmalar: `experimental`/`clusters`/`max_positions` + testnet/canlı; `veto_mode=off` + paper + `experimental=false`; `experimental` + `var_dir="var"` / `kill_file="shared/KILL"` / `ml_mode="shadow"`; küme çifti `pairs` dışında; `ml_pairs` `pairs` dışında; `contract_types` boş; `session` + `experimental=false`; olmayan `--env` adı. |
| X-T5 | `extract_rules`: `TRADIFI_PERPETUAL` varsayılanla `not_trading`, kabul listesiyle kural döner; `PERPETUAL` iki durumda aynı. |
| X-T6 | Feed `--env paper`: 20 çift, yollar `var/`. `--env cross`: yollar `var-cross/`, `var/market.sqlite`'a yazma yok. `--env` yokken `feed_config_from_base` çıktısı aynı. Feed her iki katmanla pandas yüklemez. |
| X-T7 | Ban: `var/` altında etkin ban varken cross feed istek atmaz ve `var/` altına yazmaz; `--also-ban-dir` yokken davranış aynı. |
| X-T8 | Küme tavanı (kripto): 3 `kripto_buyuk` açıkken dördüncü `cluster_cap:kripto_buyuk`; 8 açık pozisyonda dokuzuncu `max_positions`; aynı barda tavanı aşan adaylar `pairs` sırasıyla alınır. |
| X-T9 | Küme tavanı (cross): 2 teknoloji açıkken üçüncü teknoloji atlanır, teknoloji dışı hisse girebilir; 3 hisse açıkken dördüncü `cluster_cap:hisse`; XAU açıkken XAG atlanır; hesap geneli 5. |
| X-T10 | Seans: hisse için Cumartesi, Pazartesi 09:29 ve 16:00 New York atlanır, 09:30 geçer; yaz/kış saati haftalarında doğru UTC. Metal için Cuma 21:00 ve Pazar 22:59 UTC atlanır, Pazar 23:00 geçer. Pencere dışında açık pozisyonun stop/hedef çıkışı çalışır. |
| X-T11 | Düz bar: `volume=0` ya da `high==low` → `flat_bar`; `flat_bar_guard=false` iken geçer. |
| X-T12 | Atlanan adayların karar satırı defter CHECK'lerinden geçer (şema 4, göç yok). |
| X-T13 | ML: evren içi çiftin puanı ve özellik vektörü, `pairs` 10 iken ve 20 iken **bit bit aynı**; evren dışı aday `out_of_universe`, puan yok, gölgede eleme yok; ML açık değilken hiçbir fark yok. |
| X-T14 | Veto: 40 kararlı belge üretilir, ayrıştırılır, imzalanır, motor 20 çiftin her yönünü bulur; `max_tokens` 4001 reddedilir. |
| X-T15 | Tarafsızlık: yeni anahtarlar boşken altın testler (`tests/test_wp3_golden.py`, `test_t28_backtest_digest_unchanged`, `test_engine_compat_equity.py`) ve S2 §8 testleri aynen. |
| X-T16 | Yalıtım: cross motoru bir tur koşar; `var/`, `user_data/`, `shared/KILL`, `shared/PAUSE*`, `shared/veto/` altında değişiklik yok. `shared/KILL` cross'u, `shared/cross/KILL` öğrenen/ikizi etkilemez. Ders servisi cross defterini açmaz. |
| X-T17 | Kısa geçmiş: bir çiftte 1h 600 bar → o çift `no_history`, diğerleri karar üretir, motor çıkmaz. |
| X-T18 | Açılış kapısı: `all` kipte bir çift bayat → çıkış 7; `rules_only` kipte kural tam + bir çift taze → geçer, bayat çift `stale_data` ile giriş yapmaz; kural eksikse iki kipte de çıkış 7. |
| X-T19 | Geçiş: 10 çiftli durum/defterle (açık pozisyonlu) kapanan motor 20 çiftle açılır; pozisyon, imleçler ve parametre sürümü korunur; yeni çiftler imleçsiz başlar. |
| X-T20 | Dağıtım: cross birimleri `Slice=trader-cross.slice`, tavanlar slice içinde, `OOMScoreAdjust=300`, anahtar `EnvironmentFile` yok, `ReadWritePaths` `var` içermez; şablon birim `--env paper`, öğrenen drop-in `--env paper,paper-ml`, testnet/canlı birimleri değişmedi; `install.sh` varsayılanda cross kurmaz. `test_readiness_memory` çekirdek değerleri aynı (`test_every_service_in_trader_slice` yalnız `*-cross.service` için `trader-cross.slice` kabul eder). |
| X-T21 | Telegram/pano: `CROSS_*` boşken çıktı bayt bayt eski; doluyken "DENEY" başlıklı ayrı blok/kart; öğrenen–ikiz fark sayıları değişmez. |
| X-T22 | Yasak içe aktarma taraması: freqtrade, ccxt, python-binance yok. |

## 11. Bilinen sınırlar (gözlemin parçası)

- v1b parametreleri 10 kripto çiftiyle ayarlandı; yeni 10 kriptoda ve özellikle hisse/emtiada sınanmadı. v1b'nin uzun dönem geri testi zaten zarardaydı; evreni genişletmek bunu düzeltmez, yalnız daha çok gözlem üretir.
- Piyasa değeri sıralaması doğrulanmadı; liste kullanıcı onayıyla sabittir.
- Kâğıt dolumlar benzetimdir; ince seans kayması ve hisse vadelilerinin fonlama davranışı ölçülmedi.
- Yarım gün seansları ve kazanç açıklaması boşlukları için koruma yok.
- Cross sonuçları öğrenen/ikizle karşılaştırılmaz (farklı evren, maliyet, veto yok).

## 12. Sonraki adımlar (ayrı karar)

20 çiftli ML tarifi (yeni ön kayıt); cross için veto ve varlık sınıfına özel parametre; bu sembollerde geri test (ayrı ön kayıt); testnet evreninin genişletilmesi; küme tavanlarının testnet/canlıya taşınması; gerçek para (yalnız CANLI-K1'i geçen dondurulmuş aday).
