# DD-12: Kâğıt bot ana planı — 44 enstrüman, bütün kurulum aileleri, ML ve ders etkin

Tarih: 18 Kasım 2026 (mentor). Sürüm 3 (önceki taslakların yerine geçer; dosya adı tarihseldir). Dayanak: kullanıcı kararları, 18 Kasım 2026 (`tasarim-kararlari.md`). Bu belge kod, test ve commit içermez.

## 0. Kararlar (kullanıcı) ve bu planın sınırı

- **Tek, düz kâğıt bot:** mevcut `learner` kâğıt motoru. Ayrı bot, ayrı kol, ayrı etiket yok.
- **Gölge kip kâğıtta hiçbir yerde yok.** ML işlemleri gerçekten etkiler; dersler kendiliğinden uygulanır; gölge karar satırları (`shadow_blocks`) kapatılır.
- **İçinde her şey:** 44 enstrüman (20 kripto + 20 ABD hissesi + altın, gümüş, Brent, bakır), bütün kurulum aileleri (trend takip, geri çekilme, kırılım, yatay piyasa) × 15dk / 1s / 4s / 1g, ML (aday eler ve kendi adayını üretir), ders.
- **İkiz bot yok, silinir.**
- **Sunucu büyütülmez;** plan 2 GB'a sığacak biçimde boyutlanır (§8).
- **Değişmeyenler:** testnet ve canlı yolu; gerçek para kapısı (CANLI-K1; para ve canlı anahtar yok); S2 ön kaydı; kilitli dönem (2026-05-01 → 2026-11-01).

Teslim: **Faz 1 ≤ 21 Kasım** (44 enstrüman, mevcut iki kurulum 1 saatlikte, ML etkin, ikiz kaldırılır, ders ikizsiz çalışır) · **Faz 2 ≤ 2 Aralık** (bütün kurulum aileleri, dört zaman dilimi, defter v5) · **Faz 3 ≤ 16 Aralık** (kendi adayını üreten ML, kurulum bazlı ML süzgeci, kurulum aç/kapa dersi).

## 1. Enstrümanlar (44)

Kaynak: `data.binance.vision` USDⓈ-M arşiv dizini (18 Kasım; yalnız dizin/dosya adları listelendi, veri indirilmedi). Parantez = arşivdeki ilk ay. Piyasa değeri sıralaması mentorun bilgisine dayanır, **doğrulanmadı**; liste kullanıcı onayıyla sabitlenir, kendiliğinden güncellenmez.

**Kripto (20)** — stabil (USDT, USDC, DAI, FDUSD, USDe, USDS) ve sarılı/stake kopyalar (WBTC, WETH, stETH, wstETH, WBETH) hariç; LEO Binance vadelide yok: BTC, ETH, XRP, BNB, SOL, DOGE, TRX, ADA, HYPE (2025-05), LINK, BCH, XLM, SUI, AVAX, HBAR, LTC, TON (2024-03), SHIB (`1000SHIBUSDT`), DOT, XMR. Mevcut 10 çiftin hepsi içindedir.

**ABD hisseleri (20):** NVDA (2026-03), MSFT (04), AAPL (04), GOOGL (03), AMZN (02), META (03), AVGO (04), TSLA (01), BRKB (05), JPM (05), LLY (06), WMT (05), V (05), ORCL (05), XOM (09), NFLX (06), PLTR (02), COST (06), AMD (05), HD (05). Mastercard ve Johnson & Johnson Binance'te listeli değil; kullanıcı kararıyla AMD ve Home Depot eklendi.

**Emtia (4):** XAU altın (2025-12), XAG gümüş (2026-01), BZ Brent (2026-04), COPPER bakır (2026-03).

**Sunucuda doğrulanacak (adım 0; bu ortamdan Binance API 451 döndü):** 44 sembol `exchangeInfo`'da `TRADING` mi, hisse/emtia `contractType` değeri (beklenen `TRADIFI_PERPETUAL`), filtreler, kapalı seansta 1 dk mum geliyor mu. `TRADING` olmayan sembol çıkarılır ve kullanıcıya bildirilir.

## 2. Yapı

- Tek motor (`trader-engine@learner`), tek feed, tek `var/market.sqlite`, tek defter (`var/learner/ledger.sqlite`). Mevcut açık pozisyonlar ve defter sürer (yeni liste eskisinin üst kümesi).
- `config/engine.base.json` **değişmez** (10 çift, v1b): testnet, canlı, S2, derlem ve geri test varsayılanı onu okur. Kâğıt botun ayarı tek katmandadır: `config/engine.paper.json`. Birim: `run --bot learner --env paper`.
- Kurallar gerçek `exchangeInfo`'dan gelir (feed saatte bir yeniler). `--synthetic-rules` yalnız geri testtedir.
- Hisse/emtia sembolleri feed'de "isteğe bağlı"dır: birinin kuralı ya da verisi gelmezse yalnız o çift bekler; feed ve motor düşmez. Açılış kapısı: 20 kripto için kural + taze veri şart; hisse/emtia için yalnız kural (kapalı seansta bayat çift giriş yapmaz, motor çalışır).
- Isınma ≈ 50 gün (1s 1200, 15dk 4800, 4s 300 bar). En yeni sembol XOM (2026-09) sınırdadır; yetmezse yalnız o çift bekler.

## 3. Kurulumlar ve zaman dilimleri

Kimlik `arm_id` = `<kurulum>@<zaman dilimi>`. Katalog: `price-action-kural-katalogu.md`.

| Kurulum | Aile (katalog) | Zaman dilimleri | Faz |
|---|---|---|---|
| `T1` trend içi geri çekilme | geri çekilme (PA-TRD-01/05; mevcut) | 1s (mevcut), 15dk, 4s | 1 / 2 |
| `R1` yatay piyasa kenarı | yatay piyasa (PA-YTY-02; mevcut) | 1s (mevcut), 4s | 1 / 2 |
| `TF1` yapı kırılımı yönünde devam | trend takip (PA-YAP-03, PA-FLT-01) | 4s, 1g | 2 |
| `B1` kırılım + yeniden test | kırılım (PA-KIR-01/02) | 1s, 4s | 2 |
| `F1` sahte kırılım | kırılım (PA-KIR-03) | 15dk, 1s | 2 |
| `S1` sıkışma kırılımı (iç bar / NR7) | kırılım (PA-MUM-05, PA-TRD-04) | 1s, 1g | 2 |
| `M1` ML'in kendi adayı | §5.2 | 1s; sonra 15dk, 4s | 3 |

- Her yeni kurulumun kesin tanımı (giriş, stop, hedef, sabitler) kodlanmadan önce bu belgeye tarihli ek olarak yazılır; sabitler katalogdan alınır.
- `signals.py` donuktur: `T1`/`R1` onu çağırır; `T1@4h` beklemedeki `price_action_v1_4h.py` dosyasını kullanır. Yeni kurulumlar yeni dosyalardadır.
- 1 günlük bar feed'e eklenmez; 4 saatlik barlardan (6 × 4s, UTC gün) motor içinde toplanır. `market.sqlite` şeması değişmez.
- Çift başına tek pozisyon kuralı aynen. Aynı çiftte aynı anda birden çok kurulum sinyal verirse büyük zaman dilimi önceliklidir; alınmayanlar deftere `arm_conflict` ile yazılır.
- Her kurulumun karnesi bütün adaylarından çıkar: alınanlar gerçek kâğıt sonucuyla, alınmayanlar gece işinin hesapladığı "alınsaydı ne olurdu" sonucuyla (mevcut `counterfactual` servisi).
- Kurulum başına en çok 3 açık pozisyon; `M1` için 2.

## 4. Risk

İşlem başı risk **%0,5 aynen**; `risk.py` sınırları aynen (toplam açık risk %6, aynı yön %4, günlük zarar). Üstüne, yalnız kâğıt katmanında:

| Sınır | Kapsam | Tavan | Giriş seansı |
|---|---|---|---|
| hesap geneli | 44 | 10 pozisyon (≤ %5) | — |
| `kripto_buyuk` | BTC, ETH, XRP, BNB, SOL | 3 | — |
| `kripto_diger` | kalan 15 | 4 | — |
| `hisse` | 20 hisse | 3 | New York 09:30–16:00, Pzt–Cum |
| `hisse_teknoloji` | NVDA, MSFT, AAPL, GOOGL, AMZN, META, AVGO, TSLA, ORCL, NFLX, PLTR, AMD | 2 | (aynı) |
| `metal` | XAU, XAG | 1 | Paz 23:00 → Cum 21:00 UTC |
| `enerji_sanayi` | BZ, COPPER | 1 | Paz 23:00 → Cum 21:00 UTC |

Bir çift birden çok kümede olabilir; hepsinde yer olmalıdır. Sayım açık ve açılmakta olan pozisyonları kapsar. Hisse/emtiada iki giriş koruması: seans dışında giriş yok; son kapanmış tetik barı `volume == 0` ya da `high == low` ise giriş yok (tatil). Açık pozisyonun stop/hedef yönetimi her zaman sürer; hafta sonuna taşınan pozisyon kapatılmaz. Hisse/emtia kayması tabanın iki katı sayılır (giriş 4, çıkış 4, stop 10 bp; tahmin).

**Veto (LLM):** 20 kripto için açık (40 karar; `max_tokens` üst sınırı 2000 → 4000). Hisse/emtia vetosuz başlar: veto bağlamı BTC'ye dayalı ve 44 enstrümanda API maliyeti kabaca 4 katına çıkar. Kullanıcı isterse 44'e yayılır (§14).

## 5. ML — etkin

Model puanı boyutu değiştirmez; risk kilidi son sözü söyler. Kâğıtta kapı şartı aranmaz. Testnet/canlıya kapıdan geçmemiş model yüklenemez (mevcut kural, aynen).

### 5.1 Süzgeç (aday eler)
- **Faz 1:** r03, `ml_mode="active"`. r03 taban 10 çiftle eğitildi ve 200 günlük geçmiş ister; bağlamı o 10 çiftle sabit tutulur (`ml_pairs`), puanları bugünküyle aynı kalır. Bu 10 çiftin eşik altı adayları **elenir**. Diğer 34 enstrümanın adayları elenmeden geçer (kayıt: `out_of_universe`); bugünkü "puanlanamayan aday elenir" davranışı onlara uygulanırsa hisseler hiç işlem yapamaz. Not: r03 kapıda başarısızdı (AUC 0,50); elemesi rastgeleye yakın olabilir, etkisi §7'deki ölçümle görülür.
- **Faz 3:** kurulum bazlı süzgeçler, 44 enstrümanı kapsar; eğitim verisi kâğıtta biriken aday + sonuç kayıtlarıdır. Kurulum başına ≥ 300 etiketli aday dolana kadar o kurulum süzgeçsiz çalışır.

### 5.2 ML'in kendi adayı (price action'ı kendisi öğrenir) — Faz 3
- Girdi: son 64 barın ATR'ye ölçekli mum dizisi (gövde, fitiller, kapanış konumu, getiri) + yapı özellikleri (son salınım tepe/dibine uzaklık, aralık içi konum, ortalama eğimleri, sıkışma ölçüsü, üst zaman dilimi yönü). Enstrüman kimliği özelliği yok.
- Etiket: üçlü bariyer (stop 1,5 ATR, hedef 3 ATR, süre 48 bar), uzun ve kısa ayrı.
- Model: LightGBM, üç sınıf (uzun / kısa / yok); eşik, eğitim dışı dilimde barların en yüksek puanlı ≈ %2'sini seçecek biçimde sabitlenir.
- Eğitim: sunucu dışında, 20 kripto, 2021-01 → 2026-04-30; **kilitli dönem eğitime ve değerlendirmeye girmez**; 2026-11-01 sonrası canlı veri biriktikçe eklenir. Hisse/emtiada kilit öncesi geçmiş neredeyse yok; model onlara kripto eğitimiyle uygulanır.
- Çalışma: `M1@1h` kurulumu olarak; giriş bar kapanışında piyasa emri; küme/seans/risk kapılarının hepsinden geçer. 14 günde bir yeniden eğitim.
- Kod yeni pakettedir (`src/trader_ml/pa_proposer/`); dondurulmuş dosyalara dokunulmaz.

### 5.3 Kayıt
Kâğıtta çalışan her model `research/paper_models.csv`'ye yazılır (ad, tarif, veri penceresi, commit, sha256, tarih). Bu modellerden biri ileride kapıya ya da CANLI-K1'e aday olursa, buradaki tarif sayısı deneme sayısına eklenir.

## 6. Ders — etkin, ikizsiz

İkiz kalktığı için "iyileşti mi" sorusu botun kendi kayıtlarından yanıtlanır. Dayanak: defter her adayı özellikleriyle yazar ve gece işi alınmayan adayların "alınsaydı" sonucunu hesaplar.

- **Referans sürüm:** kullanıcının son onayladığı (başlangıçta bugünkü) ayar sürümü.
- **Ders etkisi (R):** aynı dönemde, bugünkü ayarlarla referans ayarların **farklı karar verdiği** adaylar üzerinden ölçülür: `etki = Σ R(bugünkü ayarın aldığı, referansın almayacağı işlemler; gerçek sonuç) − Σ R(referansın alacağı, bugünkü ayarın elediği adaylar; "alınsaydı" sonucu)`. İki taraf aynı piyasa döneminden geldiği için "önce/sonra" kıyasındaki dönem farkı karışmaz. Tavan ve sıra etkileşimleri hesaba girmez (yaklaşık ölçüdür).
- **Tek değişikliğin geri alınması:** bir değişiklikten sonra farklı karar verilen ≥ 30 adayda o değişikliğin etkisi ≤ −3 R ise değişiklik geri alınır (bugünkü otomatik geri almanın ikizsiz karşılığı).
- **10 R freni (yeni tanım):** referans sürümden beri toplam ders etkisi ≤ −10 R ise referans sürüme dönülür, otomatik uygulama durur, Telegram'a haber gider.
- **"İkizden en çok 2 adım"** → "referans sürümden en çok 2 adım".
- Otomatik uygulama ilk günden açık: sıkılaştırma ve gevşetme onaysız uygulanır, Telegram'a bilgi gider. Eşik kalibrasyonu (`lesson_calibrate.py`) bilgi içindir, ön şart değildir. Kalan korumalar: tek ayar, tek adım, haftada en çok bir değişiklik, sınırlar.
- **Faz 1–2:** mevcut ders ayarları `T1` ve `R1` kanıtıyla çalışır.
- **Faz 3 — kurulum dersi:** bir kurulum, alınan + "alınsaydı" ≥ 40 adayda ortalama ≤ −0,15 R ise kapatılır (aday ve sonuç kaydı sürer); son 40 adayda ≥ +0,05 R'ye dönerse yeniden açılır.
- **ML etkisi** aynı yolla ölçülür: `−Σ R(ML'nin elediği adaylar; "alınsaydı" sonucu)` ve `M1` işlemlerinin gerçek R toplamı.

## 7. Telegram ve pano

Sade başlıklar: "Kâğıt bot". Özel etiket yok.

- Günlük rapor: net R (bugün / toplam), açık pozisyonlar (küme adıyla), **ders etkisi** ve **ML etkisi** (§6), atlama sayıları (seans, tatil barı, küme tavanı, hesap tavanı, kurulum çakışması, ML elemesi).
- Kurulum karnesi (Faz 2; haftalık rapor ve `/kurulumlar`): kurulum başına aday, alınan, ortalama R (alınan), ortalama R (alınan + alınsaydı), varlık sınıfı kırılımı, açık/kapalı.
- Ders: her otomatik uygulama ve geri almada bildirim.
- İkizle ilgili bütün satır, komut ve pano alanları kaldırılır.
- Sağlık: hisse/emtiada kapalı seans bayatlığı alarm üretmez; beklenen bot listesi yalnız `learner`.

## 8. Kapasite — 2 GB'da kalınır

Bellek ve işlemci sayıları **tahmindir**; dağıtımda ölçülür.

- **REST ağırlığı** (sınır 2400/dk, istemci eşiği 1800): sürekli 88/dk; saat başı tepe ≈ 270/dk; ilk geri doldurma ≈ 4100 (istemci kendini kısar, 3–4 dk). Sorun değil.
- **Disk:** 1 dk barlar (14 gün) ≈ 200 MB; uzun barlar ≈ 180 MB/yıl; defter yılda < 1 GB. Sorun değil.
- **Bellek (tahmini RSS, MB):**

| Birim | Bugün | Faz 1 | Faz 2–3 |
|---|---|---|---|
| feed (44) | 55 | 85 | 85 |
| öğrenen | 200 | 320 | 450–520 |
| ikiz | 160 | **0 (kaldırıldı)** | 0 |
| testnet (14 Aralık) | — | — | 180 |
| pano + telegram | 110 | 110 | 120 |
| işletim sistemi | 230 | 230 | 230 |
| geçici işler (pano yayını, ders, veto, gece işi) | 300 | 300 | 350 |
| **En kötü an** | 1055 | **1045** | **1415–1485 / 1960** |

İkizin kalkması Faz 1'i bugünkü düzeyde tutar; Faz 2–3 ≈ 500 MB payla sığar. `trader.slice` aynen (1100M / 1300M). Birim tavanları: öğrenen `MemoryHigh=600M`, `MemoryMax=750M`; feed 200M/260M; testnet aynen (250M/320M). Yumuşak tavan toplamı 200 + 600 + 250 = 1050 ≤ 1100.

- **Boyutlama kuralları (öğrenen ≤ 550 MB hedefi):** çift × zaman dilimi başına yalnız son pencere tutulur (15dk 5000, 1s 1500, 4s 1500 bar); gösterge tabloları adımlar arası saklanmaz; 1 günlük bar anında türetilir; ML özellik tamponu son 64 bar; aynı türden tek model bellekte.
- **İşlemci:** yalnız kapanan zaman diliminin kurulumları hesaplanır (15 dakikalık adımda 2 kurulum, saat başında 7, 4 saatte 11, gün başında 13). Hedef: karar adımı < 120 sn; `CPUQuota=90%`. Kâğıtta stoplar 1 dk barlardan sonradan değerlendirildiği için gecikme sonucu değiştirmez.
- **Sığmazsa (sessizce kısılmaz, kullanıcıya sorulur):** ölçümde öğrenen > 550 MB ya da saat başı adımı > 120 sn çıkarsa en küçük kısıntı önerisi şudur: **15 dakikalık kurulumlar (`T1@15m`, `F1@15m`) yalnız 20 kriptoda çalışır**, hisse/emtiada 1s/4s/1g kalır (en büyük pencere 15 dakikalıktır; ≈ 100 MB ve 15 dakikalık hesabın yarısından fazlası kazanılır). İkinci basamak: 14 Aralık'ta testnet başlarken pano yayınını 5 dakikadan 15 dakikaya seyreltmek.
- **İzlenecek:** `systemctl show trader-engine@learner trader-feed -p MemoryCurrent -p MemoryPeak`; `free -m`; `journalctl -k | grep -i oom`; karar adımı süresi (`status.json`); feed `used_weight`.

## 9. Dosya dosya değişiklikler

**Dokunulmaz:** `s2-on-kayit.md` §1.8 listesi (`scripts/build_corpus_v2.py`, `research/ml_build_candidates.py`, `trader_ml/{features,features_v2,labels,guards,config}.py`, `trader_core/{ml_features,ml_features_v2,signals,regime,indicators}.py`, `trader_engine/holdout.py`); `engine.base.json`, `engine.learner.json`, `engine.testnet.json`, `engine.live.json`; `risk.py`, `brokers/*`, `order_manager.py`; `research/s2_run.py`; testnet/canlı birimleri. freqtrade/ccxt/python-binance yok. Yeni yapılandırma anahtarları verilmediğinde (taban, testnet, canlı, geri test) davranış bit bit aynıdır.

### Faz 1 (≤ 21 Kasım)

| Dosya | Değişiklik |
|---|---|
| `config/engine.paper.json` (yeni) | `pairs` (44), `optional_pairs` (24), `strategy: "price_action_v1_full_ml"`, `ml_mode: "active"`, `ml_pairs` (taban 10), `ml_features: "r03"`, `ml_model_path`, `ml_experimental: true` (iç anahtar adı; kullanıcıya görünmez), `shadow_blocks: []`, `max_positions: 10`, `clusters` (§4, seanslarıyla), `flat_bar_guard`, `contract_types`, `veto_exempt_pairs` (24), `cost_overrides`. |
| `config/engine.paper-ml.json`, `config/engine.twin.json` | **Silinir.** |
| `config/veto.json` | `pairs_from` → kâğıt listesi eksi muaflar; `max_tokens` 3600. |
| `config/lesson.json` | İkizsiz ölçüm (§6); gevşetme onaysız; kalibrasyon şartı kapalı. |
| `src/trader_engine/config.py` | İsteğe bağlı anahtarlar: `max_positions`, `clusters` (+`session`), `flat_bar_guard`, `optional_pairs`, `veto_exempt_pairs`, `contract_types`, `cost_overrides`, `ml_pairs`; yalnız `mode="paper"` (testler için `backtest`), testnet/canlıda `ConfigError`. `ml_experimental`: `paper` + `active` de geçerli. `bot` yalnız `learner`; `ladder_follow` kaldırılır. |
| `src/trader_engine/cli.py` | `--env paper` eklenir; `--bot twin` ve ikiz parametre karması denetimi kaldırılır. |
| `src/trader_engine/exchange/rules.py` | `extract_rules(..., *, contract_types=("PERPETUAL",))`; canlı/testnet çağrıları parametre vermez. |
| `src/trader_engine/marketdata/feed.py` | `feed` ve `rules-snapshot` için `--env`; isteğe bağlı çiftin kural/veri hatası ölümcül değil. pandas yüklenmez. |
| `src/trader_engine/arm_guard.py` (yeni, saf) | Küme üyeliği, seans, tavan sayımı, tatil barı. |
| `src/trader_engine/gates.py` | Kural adımından sonra, vetodan önce: seans → tatil barı → küme tavanı → hesap tavanı. Faz 1'de defter şeması değişmez: red satırı `skip_reason="risk_denied"`, `risk_reason` ∈ {`session_closed:<küme>`, `flat_bar`, `cluster_cap:<küme>`, `max_positions`}. Vetodan muaf çift: `allowed`, neden `exempt`. |
| `src/trader_engine/engine.py` | Açılış kapısı (§2); `ml_pairs` bağlamı; çift bazlı kayma; ikize özel başlatma gecikmesi kaldırılır; `status.json`'a küme sayıları. |
| `src/trader_engine/strategies/price_action_v1_ml.py`, `registry.py` | Yeni kayıt `price_action_v1_full_ml` (T1 + R1'i sarar); evren dışı aday puanlanmaz ve elenmez. |
| `src/trader_core/veto.py` | `max_tokens` üst sınırı 4000; muaf çiftler belge kümesinden çıkar. |
| `src/trader_core/lesson.py`, `scripts/lesson_run.py`, `lesson_calibrate.py`, `lesson_stats_check.py` | İkiz okuması kaldırılır; §6 ölçümü (farklı-karar kümesi, tek değişiklik geri alma, 10 R freni, referanstan 2 adım). |
| `src/trader_core/ledger.py` | Şema değişmez. `_require_learner` ve ikiz dalları sadeleşir; `bot` CHECK'i olduğu gibi kalır (eski satırlar için). |
| `src/trader_core/{telegram,health,panel_data,live_paths}.py`, `src/trader_panel/*`, `scripts/{telegram_run,health_run,report_run,drift_run,counterfactual_run,health_backup,engine_retry}.py`, `config/panel.json` | İkiz yolları, satırları, komutları ve fark hesabı kaldırılır; §7'nin Faz 1 kısmı. Sağlık `require_bots = ("learner",)`. |
| `deploy/` | `trader-engine@.service`: `--env paper`, tavanlar §8. `trader-engine@learner.service.d/ml-shadow.conf` **silinir**. `trader-feed.service`: `--env paper`, 200M/260M. `install.sh`: ikiz birimi ve zamanlayıcıları (`trader-engine@twin`, `trader-engine-retry@twin`, `trader-counterfactual@twin`, `trader-drift@twin`) durdurur, devre dışı bırakır; `--with-twin`/`--no-twin` kaldırılır; `HEALTH_BOTS=learner`; `var/twin/` **silinmez**, `var/arsiv/twin-<tarih>/` altına taşınır. `uninstall.sh` aynı. |
| `tests/` | İkize dayanan testler bağımsız yazarca güncellenir/kaldırılır (liste iş emrinde). |

### Faz 2 (≤ 2 Aralık)

| Dosya | Değişiklik |
|---|---|
| `src/trader_core/ledger.py` | **Şema 4 → 5** (tablo yeniden kurma; `_FK_OFF_MIGRATIONS`'a 4 eklenir; göç öncesi otomatik yedek mevcut). Karar, süzülmüş aday ve gölge karar tablolarında: `trigger_tf IN ('15m','1h','4h','1d')`; `setup` sabit listesi yerine `length(setup) BETWEEN 2 AND 8` (geçerli kodlar kodda kayıtlı; yeni kurulum göç istemez); yeni sütun `arm_id TEXT` (eski satırlar `setup || '@' || trigger_tf`); `skip_reason` listesine `arm_conflict`, `arm_disabled`, `session_closed`, `flat_bar`, `cluster_cap`, `max_positions` (`veto_status='not_evaluated'`, `risk_allowed IS NULL` grubunda). `trade_entries`'e `arm_id`. |
| `src/trader_engine/strategies/lab.py` (yeni) | Bileşik strateji `price_action_lab_ml`: kayıtlı kurulumları tutar; her adımda kapanan zaman dilimlerinin kurulumlarını çalıştırır; çift başına öncelikli adayı ve diğerlerini (`arm_conflict`) döndürür; ML süzgecini uygular. |
| `src/trader_engine/strategies/arms/{t1,r1,tf1,b1,f1,s1}.py` (yeni) | Kurulum başına bir dosya; saf; tarihli ekteki tanım. |
| `src/trader_engine/strategy_runner.py`, `bars.py` | Çok zaman dilimli pencere; 1g barın 4s'ten toplanması; kurulum bazlı ısınma. |
| `src/trader_engine/engine.py` | Karar adımı 15 dakika; bir adımda çift başına birden çok karar satırı; kurulum başına pozisyon tavanı; `arm_id`. Taban yapılandırmada (tek kurulum, 1s) yol ve çıktı aynen. |
| `src/trader_engine/gates.py` | Faz 1 redleri kendi `skip_reason` değerleriyle. |
| `src/trader_core/counterfactual.py`, `scripts/counterfactual_run.py` | Yeni kurulum/zaman dilimleri; sonuçlar `arm_id` ile. |
| `src/trader_core/lesson.py` | Kanıt süzgeci `arm_id`. |
| Rapor, Telegram, pano | Kurulum karnesi (§7). |
| `config/engine.paper.json` | `strategy: "price_action_lab_ml"`, `arms`, `arm_max_positions`. |

### Faz 3 (≤ 16 Aralık)

| Dosya | Değişiklik |
|---|---|
| `src/trader_ml/pa_proposer/{features,labels,train,package}.py` (yeni) | §5.2; eğitim girdisi kilitli dönemi yapısal olarak reddeder. |
| `research/pa_proposer_build.py`, `research/paper_models.csv` (yeni) | Sunucu dışı eğitim; model kaydı. |
| `src/trader_engine/strategies/arms/m1.py` (yeni) | Paket yok/süresi dolmuş → aday üretmez (motor durmaz). |
| `src/trader_core/ml_package.py`, `ml_live_v2.py` | Birden çok paket; kurulum bazlı süzgeç eşlemesi. |
| `src/trader_core/lesson.py`, `ledger.py` | Kurulum aç/kapa dersi; `param_versions` içinde `arms_enabled` (JSON alanı, şema değişmez). |
| `scripts/health_run.py` | Paket tazeliği alarmı birden çok paket için. |

## 10. S2, kilitli dönem, araştırma kuralları (değişmedi)

- S2 ön kaydı donuktur (10 çift, taban dosya, 6 hak, CANLI-K1 hesap tanımları). S2-1 beklemede; bu plan onu koşmaz ve tanımını değiştirmez. S2 §8 tarafsızlık testleri ve altın testler her kod commit'inde geçer.
- Kilitli dönem: canlı feed'in ısınma geri doldurması o döneme ait barları `market.sqlite`'a yazar (bugün de öyle; canlı karar için gerekli). Yasak olan o döneme değen geri test, eğitim, tarama, dilimlemedir. `backtest`/`run_range` ve `fetch_binance_vision.py` yapısal olarak engeller; `pa_proposer` eğitimi aynı sınırı uygular. `market.sqlite` araştırma betiğiyle okunmaz.
- Kurulumlar geçmişte başarıma göre seçilmez; doğrudan kâğıtta denenir. Yeni kurulum için geçmiş koşu yalnız teknik doğrulamadır (ileriye bakma, belirlenimcilik), 2021-01 → 2024-01 aralığında. Bir kurulumun tam dönem geri testi ön kayıtlı denemedir.
- Kâğıtta iyi görünen kurulum/model gerçek paraya ancak dondurulup ön kayıtla CANLI-K1'den geçerek gider.
- Hisse/emtiada kilit öncesi geçmiş neredeyse yok; yalnız ileriye dönük gözlemdir.

## 11. Dağıtım

**Adım 0:** sunucuda `exchangeInfo` ve 1m `klines`/`markPriceKlines` yoklaması 44 sembol için, bir kez de hafta sonu saatinde; bellek ön ölçümü. Sonuç bu belgeye tarihli ek.

**Faz 1**
1. Kod + testler birleşir (mentor incelemesi zorunlu; altın ve S2 tarafsızlık testleri değişmeden geçer).
2. İkiz durdurulur, birimleri devre dışı bırakılır, `var/twin/` arşive taşınır.
3. `install.sh`; `rules-snapshot --env paper` → 44/44 (eksik bildirilir).
4. `systemctl restart trader-feed`; geri doldurma biter.
5. Öğrenen yeniden başlar; açık pozisyonlar ve defter sürer.
6. Denetim: açılış kapısı tamam; veto 40 kararla geçti; `ml_filter` satırları oluşuyor; ders servisi ikizsiz tur attı; bellek ve adım süresi ölçümü.
7. `tasarim-kararlari.md`'ye geçiş tarihi (ayrı commit).

**Faz 2:** motor durur → defter yedeği → kod → ilk açılışta 4 → 5 göçü → `ledger verify` → başlat; gece işi, ders, pano, Telegram aynı sürümle. Ölçüm §8 eşiklerini aşarsa kullanıcıya §8'deki kısıntı sorulur.

**Faz 3:** paket sunucu dışında eğitilir, `models/` altına sha256 ile konur, `paper_models.csv` satırı commit'lenir, motor yeniden başlar.

**Geri alma:** birim `--env` eki olmadan taban yapılandırmaya döner (10 çift, v1b); önce `pause` ile yeni giriş kapatılır, taban dışı kâğıt pozisyonlar kapanınca dönülür. Defter v5 geri alınmaz (taban davranış v5 defterle aynen çalışır); gerekirse göç öncesi yedekten dönülür. İkiz arşivden geri getirilebilir.

## 12. Testler (bağımsız yazar)

| Kod | Faz | Davranış |
|---|---|---|
| D-T1 | 1 | Katmansız yükleme (`learner`, `testnet`, `live`) önceki `EngineConfig` ile eşit; `engine.base.json` sabit karma ile korunur; `bot="twin"` reddedilir. |
| D-T2 | 1 | `--env paper`: 44 çift (taban 10'un üst kümesi), kümeler, ML etkin, `shadow_blocks` boş. Yeni anahtarlar testnet/canlıda `ConfigError`; küme çifti / `ml_pairs` / `optional_pairs` `pairs` dışında → hata. |
| D-T3 | 1 | `extract_rules`: `TRADIFI_PERPETUAL` varsayılanla reddedilir, kabul listesiyle döner; `PERPETUAL` iki durumda aynı. |
| D-T4 | 1 | Feed: isteğe bağlı çiftin hatası süreci düşürmez; zorunlu çiftin hatası bugünkü çıkış koduyla; `--env` yokken çıktı aynı; pandas yüklenmez. |
| D-T5 | 1 | Açılış kapısı: kripto çifti bayat → çıkış 7; hisse bayat → geçer, o çift giriş yapmaz; hissede kural yok → yalnız o çift bekler. |
| D-T6 | 1 | Tavanlar: küme, çok üyelik (teknoloji 2 doluyken teknoloji dışı hisse girer; hisse 3 doluyken girmez), hesap 10; aynı barda sıra `pairs` sırası. |
| D-T7 | 1 | Seans: hisse için Cumartesi, Pzt 09:29 ve 16:00 New York atlanır, 09:30 geçer; yaz/kış saati haftaları; metal için Cuma 21:00 ve Pazar 22:59 UTC atlanır, 23:00 geçer; seans dışında stop/hedef çıkışı çalışır. Tatil barı koruması. |
| D-T8 | 1 | ML etkin: evren içi çiftin puanı `pairs` 10 iken ve 44 iken **bit bit aynı**; eşik altı aday `ml_filter` ile elenir; evren dışı aday elenmez. Kâğıt yapılandırmasında hiçbir gölge yolu çalışmaz (gölge satır sayısı 0). |
| D-T9 | 1 | Veto: 40 kararlı belge; muaf çift `allowed`/`exempt`; muaf olmayan eksik çift kapalı. |
| D-T10 | 1 | Ders ikizsiz: farklı-karar kümesi doğru kurulur (sıkılaştırmada elenenlerin "alınsaydı" sonucu, gevşetmede eklenenlerin gerçek sonucu); ≥ 30 adayda ≤ −3 R → o değişiklik geri alınır; toplam ≤ −10 R → referans sürüme dönüş, otomatik uygulama durur, bildirim; referanstan en çok 2 adım; haftada en çok bir değişiklik; ikiz defteri yokken hata yok. |
| D-T11 | 1 | İkiz kaldırma: `install.sh` ikiz birimlerini durdurur/devre dışı bırakır, `var/twin` arşive taşınır (silinmez); sağlık, Telegram, pano, yedek ikiz olmadan temiz çalışır; hiçbir çıktıda ikiz satırı yok. |
| D-T12 | 1 | Geçiş: 10 çiftli, açık pozisyonlu durum/defter 44 çiftle açılır; pozisyon, imleç, parametre sürümü korunur. |
| D-T13 | 1–3 | Tarafsızlık: yeni anahtarlar boşken altın testler (`tests/test_wp3_golden.py`, `test_t28_backtest_digest_unchanged`, `test_engine_compat_equity.py`) ve S2 §8 testleri aynen; testnet/canlı birim dosyaları değişmedi. |
| D-T14 | 1 | Bellek bütçe testi yeni birim tavanlarıyla (200 + 600 + 250 ≤ 1100; slice aynı); her servis `trader.slice`'ta. |
| D-T15 | 2 | Defter göçü 4 → 5: satır sayıları ve içerik korunur, `arm_id` eski satırlarda dolu, yabancı anahtar denetimi temiz, yedek oluştu; yeni zaman dilimi, kurulum kodu ve atlama nedenleri kabul edilir, geçersizler reddedilir; yarıda kesilen göç defteri v4'te bırakır. |
| D-T16 | 2 | Bileşik strateji: yalnız kapanan zaman diliminin kurulumları çalışır; 1g bar = 6 × 4s (UTC), eksik 4s barla 1g bar üretilmez; öncelik büyük zaman dilimi; kaybedenler `arm_conflict`; kurulum başına tavan. |
| D-T17 | 2 | Her kurulum: ileriye bakma yok, belirlenimci, ısınma eksikken yalnız o kurulum bekler. |
| D-T18 | 2 | Eşdeğerlik: bileşik strateji yalnız `T1@1h` + `R1@1h` ile, aynı veride `price_action_v1_full` ile aynı girişleri üretir. |
| D-T19 | 2 | Gece işi: `arm_conflict`, tavan, seans ve ML redleri etiketlenir; kurulum karnesi alınan + alınsaydı toplamını doğru verir. |
| D-T20 | 2 | Boyutlama: 44 çift × 13 kurulumla motor tepe RSS ve saat başı adım süresi ölçülür ve raporlanır (eşik 550 MB / 120 sn; aşım testi kırmaz, uyarı ve rapor üretir). |
| D-T21 | 3 | `pa_proposer`: eğitim girdisinde kilitli döneme ait tek satır varsa hata; özellikler yalnız kapanmış barlardan; aynı girdi → aynı paket sha256; canlı özellik = eğitim özelliği (bit bit). |
| D-T22 | 3 | `M1`: paket yok/süresi dolmuş → aday yok, motor çalışır; aday bütün kapılardan geçer. Kurulum dersi: eşik altı kurulum kapanır, kaydı sürer, toparlanınca açılır. |
| D-T23 | 1–3 | Telegram/pano: sade başlıklar; ders ve ML etkisi sayıları defterle tutarlı; hisse kapalı seansında bayatlık alarmı yok. |
| D-T24 | 1–3 | Yasak içe aktarma taraması (freqtrade, ccxt, python-binance); dondurulmuş dosyaların sha256'ları değişmedi. |

## 13. Bilinen sınırlar

- v1b uzun dönem geri testte zarardaydı ve r03 kapıdan geçmedi; ikisi de kâğıtta bilerek çalışır. Sonuç neyse görülür.
- İkiz olmadığı için ders ve ML etkisi §6'daki yaklaşık ölçüyle izlenir; tavan ve sıra etkileşimlerini içermez.
- Piyasa değeri sıralaması doğrulanmadı. Kâğıt dolumlar benzetimdir; ince seans kayması ve hisse vadelilerinin fonlaması ölçülmedi. Kazanç açıklaması boşlukları ve yarım gün seansları için koruma yok.
- ML'in kendi adayı hisse/emtiaya kripto eğitimiyle uygulanır.
- Bellek ve işlemci sayıları tahmindir; §8'deki eşikler aşılırsa kısıntı kullanıcıya sorulur.

## 14. Kullanıcıya kalanlar

1. 44 enstrüman listesinin onayı (§1; kripto sıralaması doğrulanmadı).
2. Veto hisse/emtiada kapalı başlıyor (API maliyeti ≈ 4 kat). 44'e yayılsın isterseniz söyleyin.
3. Bilgi: kripto vetosu 20 → 40 karara çıktığı için API maliyeti kabaca iki katına çıkar.
