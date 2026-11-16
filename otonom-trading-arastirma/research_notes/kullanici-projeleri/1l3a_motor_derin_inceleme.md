# 1L3A işlem MOTORU — derin teknik inceleme (salt okunur)

Kaynak: `/home/user/sselimgenc-oss/1l3a-proje` (tek commit; `veri/`, `sonuclar/`, `arsiv/` okunmadı). Tarih: 2026-11-16.
Hiçbir şey çalıştırılmadı/içe aktarılmadı; dosya içerikleri veri olarak okundu. Önceki yüzeysel analiz: `1l3a_analiz.md`.
Karşılaştırma tarafı: `/home/user/SG-Github-AB-proje/trader/src/trader_core/` (signals, risk, regime, ledger, veto, budget, health).

Kısa sonuç: 1l3a'nın **borsa/yürütme katmanı** (REST istemcisi, filtre/boyut, mutabakat, idempotensi, kill) gerçekten iyi ve bizim için
değerli. Ama **çekirdek motor** (`portfoy/motor.py` + `canli/paper_motor.py`) bir araştırma platformunun içine gömülü, portföy ağırlıkları,
kısmi çıkış, grup payı, çok hesaplı paper gibi bizim ihtiyacımız olmayan karmaşıklık taşıyor ve boyutlandırması kendi risk kuralına
kablolanmış. Öneri: **motor çekirdeğini sıfırdan yaz (küçük, tek bar-döngüsü + takılabilir Broker), 1l3a'dan borsa katmanını ve test
senaryolarını uyarlayarak al.** Ayrıntı §6.

---

## 1. Mimari

### 1.1 Katmanlar ve dosyalar (çekirdek ≈ 6 bin satır; repo toplamı ≈ 115 bin satır, çoğu strateji/araştırma)

| Katman | Dosya (satır) | Rol |
|---|---|---|
| Strateji arayüzü | `motor/strateji/temel.py` (`Strateji.sinyaller(mumlar)` VEKTÖREL, DataFrame döner: yon, stop, hedef, cikis, cikis_long/short, zaman_cikisi_mum); `motor/strateji/cikislar.py` (`CikisAyarlari`: ATR iz süren, zaman çıkışı, sabit R hedefi, başabaş, kısmi, ≥12 ek modül) | Strateji = saf fonksiyon + deklaratif çıkış ayarları |
| Tek sembol backtest | `motor/backtest/motor.py` (538) | Olay güdümlü, 1 sembol/1 pozisyon, Decimal |
| Portföy/çoklu kol motoru (asıl çekirdek) | `motor/portfoy/motor.py` (992): `_Motor.calistir` (660), `_emirleri_yurut` (516), `_mum_ici` (846), `_karar_sinyal` (939), `_funding_ode` (339) | Backtest + paper AYNI sınıf; sinyal kolu ve ağırlık kolu |
| Paper motoru | `motor/canli/paper_motor.py` (961, `PaperMotor(_Motor)`), `paper.py` (846, döngü + `canli_calistir` 494), `paper_v2.py` (962, çok hesap), `paper_sinyal.py`, `paper_kaynak.py` (`TekrarKaynagi`), `paper_canli.py` (`CanliKaynak`, WS) | Aynı `_Motor`'u canlı veriyle sürer; tekrar (replay) kaynağı ile backtest eşlemesi (`paper_esleme.py`) |
| Borsa katmanı | `motor/canli/borsa/binance_futures.py` (316), `kurallar.py` (111), `canli_limitler.py` (177), `canli_yurutucu.py` (746), `canli_kayit.py` (188), `canli_ayar.py` (151), `kuru.py` (84), `motor_kopru.py` (71), `calistir.py` (165) | Paper motorunun "niyet"lerini gerçek emre çevirir |
| Risk (araştırma/paper) | `motor/risk/limitler.py` (`SERT_LIMITLER`, `maliyetli_risk_birim`) | %1/%3/3x/%20/%5 |
| Durum/pano | `canli/durum.py` (`atomik_yaz_json` 94-112), `pano.py` (2065), `telegram.py` | JSON/JSONL, statik HTML |

### 1.2 Veri akışı (canlı/testnet)
1. `canli/paper.py::canli_calistir` (494): `FapiIstemci` (REST, `paper_veri.py`) ile sunucu zamanı + exchangeInfo, `CanliKaynak.baslat` mum geçmişi (yerel parquet tohum + REST) ve funding geçmişi.
2. WebSocket (`paper_canli.py::ws_dongu` 200) YALNIZ "kline kapandı" tetiği. Asıl bar REST'ten okunur (WS ile `ws_dogrula` karşılaştırır). Yoklama 30 sn + 3 sn grace (`paper_canli.py` 28-33).
3. `tur()` (paper.py 569): `kaynak.guncelle` → `p.adim` (paper motoru karar + sanal dolum) → `tur_kancasi` = `calistir.py::kanca` → `motor_kopru.gorunum` paper motorunun `giris_emri`/`cikis_emri`/stop durumunu `Niyet`e çevirir → `Yurutucu.adim` (canli_yurutucu.py 167).
4. `Yurutucu._adim` (185): kasa oku → günlük/kill → `_mutabakat` → kapat niyetleri → aç niyetleri → `_stop_yukselt`.

Yani **canlı karar yolu = paper motorunun kararı**; borsa katmanı "bir sonraki bar açılışı" yerine "bar kapandıktan hemen sonra piyasa emri" verir (`giris_gecikme_max_sn=900` bayatlık sınırı, `canli_yurutucu.py` 80).

### 1.3 Eşzamanlılık
- Tek süreç, `asyncio` ana döngü; WS ayrı task'ta, tur işi `loop.run_in_executor(None, koruyucu.calistir, tur)` ile tek iş parçacığında senkron (paper.py 620-640). Emirler SENKRON `requests.Session` (bloklayıcı). Kilit/yarış yok çünkü tur seri.
- Bir Binance hesabı = bir strateji; birden çok strateji için birden çok `Yurutucu` aynı turda sırayla çalışır (`calistir.py::kanca`).

### 1.4 Durum kalıcılığı
- Paper: `paper_state.json` (her satırda `kaydet`, `paper.py::kaydet/yukle`, atomik yazma). Hata sonrası `TurKoruyucu` (paper.py 658) son tutarlı kayıttan geri yükler.
- Canlı: `canli/yurutucu_<hash>.json` (`canli_yurutucu.py::_kaydet` 137; emirden ÖNCE yazılır, 293+) ve `hesap_durumu.json`; denetim kayıtları append-only JSONL (`canli_kayit.py`).
- Veritabanı yok; hepsi JSON. Bizim ledger.py (sqlite, append-only, şema sürümlü, spool) bunun net üstünde.

---

## 2. Gereksinim gereksinim değerlendirme

Simge: EVET / KISMEN / HAYIR. "Vadeli" = USDT-M perpetual.

| # | Gereksinim | Durum | Nasıl (dosya:satır) | Kalite / risk |
|---|---|---|---|---|
| 1 | Binance USDT-M perp (spot değil) | EVET (yalnız vadeli) | `binance_futures.py` 30-31, yollar `/fapi/...`. Spot yalnız geçmiş veri vekili (`motor/veri/spot_vekil.py`) | Spot yok, gerekmiyor |
| 2 | İzole marj | EVET | `hazirla` 229-238: `marginType=ISOLATED`, one-way, leverage; -4046/-4059 idempotent | Sembol başına her girişte çağrı; açık pozisyonda kaldıraç değişimi riski (`_hazirla` önbelleği 272) |
| 3 | Kaldıraç 3-5x | KISMEN | `canli_limitler.py` 148-150: yakın stop 3x, uzak stop 2x; kaldıraç stop mesafesinden SEÇİLİR (`kaldirac_sec` 167). Paper/backtest `SERT_LIMITLER.max_kaldirac=3.0` (nominal/özsermaye) | 5x desteklemek için sabitler değişmeli; kaldıraç mantığı bizim `risk.py` (3-5, likidasyon mesafesi) ile farklı |
| 4 | Long + short | EVET (one-way) | yön ±1 her yerde; `hazirla` `dualSidePosition=false` | Aynı sembolde aynı anda long+short YOK (net pozisyon). Bizim için yeterli |
| 5 | Piyasa girişi | EVET | `piyasa` 241-246 (`MARKET`, `newOrderRespType=RESULT`) | Giriş boyutu `mark_fiyat` ile hesaplanır (`_ac_niyeti` ~318), gerçek dolum sonrası `_dolum_sonrasi_risk` (355) limiti yeniden doğrular, ihlalde reduceOnly küçültür/kapatır: iyi tasarım |
| 6 | Borsa tarafı koruyucu stop, girişten hemen sonra | EVET | `_koru` 408 → `_stop_kur` 423 → `kosullu` 248-261 (`STOP_MARKET`, reduceOnly, `quantity`, `workingType=MARK_PRICE`). Stop kurulamazsa pozisyon hemen kapatılır (410-418) | `closePosition=true` KULLANILMIYOR; miktar bazlı stop, kısmi dolumda/azaltmada miktar uyuşmazlığı mutabakatta (`_mutabakat` 509-) düzeltilir. **Algo-order uçları (`/fapi/v1/algoOrder`, `clientAlgoId`) testnet'te DOĞRULANMADI** (dosya başlığı 13-15, DURUM "algo emir uçlarının testnet'te doğrulanması" bekliyor) — en büyük canlı risk |
| 7 | Trailing stop güncelleme | EVET (client-side trail) | Paper motoru stopu hesaplar (ATR iz/başabaş/basamak: `cikislar.py`), `_stop_yukselt` 475-507: ÖNCE yeni stop kur, sonra eskiyi iptal, gevşetme yok; fiyat yeni stopu geçtiyse piyasada kapat | Borsa `TRAILING_STOP_MARKET` kullanılmıyor; güncelleme bar kapanışında (tur sıklığı 30 sn+bar) — bar içi trail yok. Her stop güncellemesi yeni `clientAlgoId` (deneme sayacı + stop değeri hash'i, 423-430) |
| 8 | Hedef (TP) çıkışı | EVET | `_hedef_kur` 445 (`TAKE_PROFIT_MARKET`, reduceOnly); sabit R hedefi gerçek dolumdan hesaplanır (`_ac_niyeti` ~351) | Hedef hatası ölümcül sayılmaz (stop yeter) |
| 9 | Zaman çıkışı | EVET (motor tarafında) | `zaman_cikisi_mum` / `CikisAyarlari.zaman_cikisi_mum` (`cikislar.py` 15); paper motoru `cikis_emri` üretir → `motor_kopru.py` "kapat" niyeti → `_kapat_niyeti` 469 reduceOnly piyasa | Borsa tarafında zamanlayıcı yok; servis ölürse zaman çıkışı çalışmaz (stop korur) |
| 10 | Paper mod, canlı kamuya açık veri | EVET | `paper_canli.py`, `paper_motor.py`; anahtar gerekmez. `kuru.py` borsa arayüzünü bellekte taklit eder | Dolum modeli BAR TABANLI (aşağıda) |
| 10a | – taker komisyon | EVET | `PortfoyAyarlari.komisyon_taker_yuzde=0.05` (portfoy/motor.py 75-85), sembol bazlı `maliyet_sembol` | OK |
| 10b | – slipaj | KISMEN | sabit bps: `kayma_bps=2`, `stop_kayma_bps=5`, `_piyasa` 335 (tick'e yuvarlı). Defter/spread/hacimle ilişkisiz | Gerçekçi değil (likit olmayan sembollerde iyimser), ama tutarlı ve maliyet-dahil risk tanımına bağlı |
| 10c | – funding (8 sa) | EVET | `_funding_ode` 339-357: tarihsel/anlık funding kayıtları, pozisyon açıkken `miktar × açılış fiyatı × oran × yön`; geç gelen kayıt bir kez ödenir; TradFi short sıfırı (`paper_motor.py` 227) | Nominal MARK değil mum AÇILIŞ fiyatıyla; sembol başına 4 sa/8 sa aralığı kayıt bazlı olduğundan doğru |
| 10d | – kısmi dolum (paper'da gerekmez) | — | Paper hep tam dolum | OK |
| 11 | Canlı yolda kısmi dolum | KISMEN | `_giris_gonder` 379-406: `dolan` (executedQty) okunur; 0 ise iptal. Dolan miktar `rec["qty"]`'a yazılır, stop dolan miktara kurulur | MARKET emri pratikte tam dolar; `LIMIT` girişte kısmi dolum yönetimi YOK (yalnız market). Kısmi stop dolumu → mutabakat miktar uyuşmazlığı onarır |
| 12 | Yeniden başlatma kurtarma + mutabakat | EVET (güçlü) | `_mutabakat` 509-598: borsa doğruluk kaynağı; stopsuz poz → stop kur; bilinmeyen poz → yalnız uyarı (otomatik işlem YOK); 'gonderildi' kaydı borsa pozisyonuyla doğrulanır; kayıtlı ama borsada olmayan → emirleri iptal + kayıt sil; yetim reduceOnly emir iptali | Testle kapsanmış (test_canli_borsa r1-r12). Eksik: açık emir/pozisyon için **kullanıcı veri akışı (listenKey) yok**, yalnız REST yoklama; tur aralığı 30 sn+ |
| 13 | Idempotent emir (client id) | EVET | `client_id()` 85-88: sha1(strateji, kol, sinyal zamanı, ek) → `1l3a-<rol>-<24 hex>` (≤36). `binance_futures.py` 8-11: emir POST'u AĞ HATASINDA ASLA otomatik tekrarlanmaz (`tekrar_guvenli=False`), `belirsiz=True` → kimlikle SORGULA, yalnız "emir yok" derse tek kez yeniden gönder (`_giris_gonder` 379) | Çok iyi düşünülmüş. Dikkat: `newClientOrderId` yalnız AÇIK emirlerde benzersiz; kodun kendi yorumu bunu belirtiyor ve sorgu ile telafi ediyor |
| 14 | Rate limit | KISMEN | Yalnız dakikalık AĞIRLIK (`X-MBX-USED-WEIGHT-1M`, eşik 1800/2400, `_agirlik_bekle` 105); 429/418 → `BorsaYasagi`, Retry-After saygı. -1021 zaman eşitleme (162) | **Emir sayısı limitleri (`X-MBX-ORDER-COUNT-10S/1M`) izlenmiyor** (grep: yok). Düşük frekanslı strateji için sorun değil; çok sembolde risk |
| 15 | Yeniden bağlanma | KISMEN | WS: üstel geri çekilme, 23 sa proaktif yenileme, 180 sn sessizlik (`ws_dongu` 200-240). REST: ağ/5xx üstel tekrar (okumalarda) | Kullanıcı veri akışı yok; REST yoklama tek doğruluk yolu (iyi, basit) |
| 16 | exchangeInfo: min notional / step / tick | EVET | `kural_cikar` 36-56 (PRICE_FILTER, LOT_SIZE, MARKET_LOT_SIZE, MIN_NOTIONAL/NOTIONAL → Decimal), `miktar_yuvarla` 67 aşağı, `stop_yuvarla` 72 (sıkı yön), `hedef_yuvarla` 77; min altı → ATLA, yukarı yuvarlama YOK (`canli_limitler.py` 217) | Çok temiz. Eksik: `PERCENT_PRICE` filtresi ve `MAX_NUM_ORDERS` kontrol edilmiyor; exchangeInfo yalnız başlangıçta alınıyor (`calistir.py::borsa_kur`), canlıda yenilenmiyor |
| 17 | Aynı strateji kodu backtest + canlı, lookahead yok | KISMEN-EVET | `Strateji.sinyaller` vektörel; canlıda aynı fonksiyon `mumlar <= t` üzerinde çalışır ve son satır alınır (`paper_sinyal.py::tek_karar` 133-160). Backtest ve paper AYNI `_Motor`. Eşdeğerlik testleri: `paper_esleme.py` + `test_paper_esleme_gercek.py`, `test_canli_oynatma_300.py`; lookahead: `test_lookahead_tum_stratejiler.py` (tam seri vs kesilmiş seri çıktısı) | Güvence "kesme testi" ile, API ile değil: vektörel arayüz lookahead'e izin verir, test yakalar. Bizim `signals.compute_signals` de vektörel+kesme testli, uyumlu. Stop/hedef değerlendirme: mum içi H/L, aynı mumda ikisi → STOP (`backtest/motor.py` başlık, `_mum_ici` 846-) — tutucu, iyi |
| 18 | Backtest: funding + MARK fiyat | KISMEN | Funding EVET (yukarıda). **Mark fiyat HAYIR**: backtest/paper son-işlem fiyatı mumlarını (OHLC) kullanır; canlı stop `workingType=MARK_PRICE` tetiklenir. Grepte backtest/paper'da mark mumu yok (`mark` yalnız `mark_fiyat` borsa çağrısı ve `veri/indir.py`'de alakasız) | Stop tetik semantiği backtest ile canlıda farklı (mark vs last), likidasyon simülasyonu da yok (liq fiyatı modellenmiyor; izole marj + %50 marj tavanı ile dolaylı) |
| 19 | Entegrasyon: signals/risk/regime/ledger/veto/budget/health | HAYIR (doğal arayüz yok) | Aşağıdaki §2.1 |

### 2.1 trader_core ile entegrasyon noktaları (kamusal API'lere göre)

1l3a'da bizim modüllere karşılık gelen kancalar yok; şu eşleşmeler doğal:
- **signals.py** (`compute_signals(df, regime_df, params)` vektörel; `evaluate_t1/evaluate_r1` tek bar; `trail_stop_path`, `time_stop_due`, `target_reached`, `regime_flip_exit`): 1l3a `Strateji.sinyaller` DataFrame sözleşmesine ince bir sarmalayıcı ile oturur (yon/stop/hedef/cikis sütunları). Ancak `trail_stop_path` ve `time_stop_due` bizde zaten var; 1l3a'nın `CikisAyarlari` modülleri ile çift tanım olur → bizim durumda çıkışları motorda tekrar yazmak yerine bizim fonksiyonları bar döngüsünde çağırmak daha temiz (sıfırdan yazımı destekler).
- **risk.py** (`check_entry(AccountState, Candidate, cfg)` → `Decision(allowed, reason, size)`; `size_position`; `liquidation_price`; float, %2 tavan, 3-5x, günlük %5, açık risk %6, aynı yön %4): 1l3a'da boyutlandırma `_Motor._istenen_qty` (portfoy/motor.py 420) ve `canli_limitler.miktar_hesapla` içine gömülü (Decimal). `check_entry`'yi 1l3a motoruna sokmak = `_istenen_qty` + `canli_yurutucu._ac_niyeti` + `kurallar.boyutlandir` üç yerde değişiklik. Bizim `risk.py` float; 1l3a Decimal. Adım yuvarlama için `Candidate.qty_step/min_notional` var — 1l3a `SembolKurali` buna beslenebilir.
- **regime.py** (`classify_last/classify_series`, `align_to_base`): 1l3a'da rejim kavramı yok; strateji içinde hesaplanıyor. Bizde `compute_signals` zaten `regime_df` alıyor → çok zaman dilimli veri (5m/1h/4h) besleme gerekir; 1l3a `htf.py` var ama bizim `align_to_base` ile uyuşması test edilmeli.
- **ledger.py** (`record_decision`, `record_trade_entry(TradeEntry)`, `record_trade_exit(TradeExit)`, `find_unledgered_trades(freqtrade_open_trade_ids)`, `entries_allowed()`): 1l3a'nın `canli_kayit.py` JSONL'si yerine bizim sqlite defteri yazılır. Eşleme: `Yurutucu._kayit_acilis/_kayit_dolum/_kayit_kapanislar` (canli_yurutucu.py 633-740) → `TradeEntry/TradeExit` (fee_exit, funding_paid = `userTrades`/`income` uçlarından, 1l3a zaten çekiyor: `kullanici_islemleri` 294, `funding_gecmisi` 312). `find_unledgered_trades` freqtrade'e özgü adlandırma → motorun kendi açık işlem kimliklerini versin.
- **veto.py** (`read_veto_file`, `lookup(state, pair, side, now)` → `blocks`): giriş yolunda tek satırlık kapı: `_ac_niyeti`'nin başında (gecikme kontrolünden önce). 1l3a'da bu kancanın yeri yok ama ekleme kolay.
- **budget.py** (Claude harcama koruması: `authorize/record`): motorla doğrudan ilgisi yok; yalnız LLM çağıran üst katmanda.
- **health.py** (`HealthSnapshot`, `evaluate`): motor kalp atışı (`paper.py::kalp_at`, `kalp_atisi.py`) ve `ApiProbe/LedgerProbe` ölçümlerini besleyebilir; 1l3a'da kalp atışı dosyası var (`canli/kalp_atisi.py`) → snapshot'a eşlenebilir.

---

## 3. Test kapsamı ve kalitesi

- Toplam ≈ 2 184 test fonksiyonu, 165 dosya; CI `.github/workflows/testler.yml` (Python 3.13, `pytest testler -q`, ağ/anahtar yok; gerçek veri gerektirenler atlanır). Raporlardaki tam paket sayısı DURUM.md'de 4 043 (parametrik) geçti olarak kayıtlı (satır 264) — ben koşturmadım, doğrulanmadı.
- **Borsa katmanı (en değerli kısım):** `testler/test_canli_borsa.py` 66 test, sahte HTTP ile: imza (Binance dokümantasyon örneği), 5xx/ağ tekrarı, emir POST'unda tekrar YOK (r1), -1021, 429/418 yasak, ağırlık eşiği, algo/klasik parametreler, filtre/yuvarlama, boyutlandırma, stop zorunluluğu, çökme sonrası yeniden başlatma, mutabakat (stopsuz/bilinmeyen/kayıp), kill-switch, günlük limit, idempotensi, stop yükseltme sırası, log'da gizli sızmaması. Bu testler bizim için hazır **şartname** niteliğinde.
- `test_canli_limitler.py` (19), `test_canli_islem_risk.py`, `test_mutasyon_sert_limitler.py` (5), `test_mutasyon_portfoy_boyut_kaldirac.py`, `test_mutasyon_stop_esitlik.py`: mutasyon tarzı sınır testleri (iyi pratik).
- **Motor/backtest:** `test_bt_motor.py` (19), `test_portfoy_motor.py` (22), `test_paper_motor.py` (12), `test_paper_v2*.py`, `test_canli_oynatma_300.py`, `test_canli_birlesik_oynatma.py`, `test_paper_esleme_gercek.py` (3, gerçek veri), `test_y5_kaldirac_komisyon_dolum_stres.py`, `test_maliyet_dahil_risk.py`.
- **Lookahead:** `test_lookahead_tum_stratejiler.py` (kesme testi, iki tohum, 7/24 + seanslı).
- Kalite notu: testler `unittest.mock`/sahte borsa ile hızlı ve deterministik; ancak **gerçek Binance'e karşı entegrasyon testi YOK** (algo uçları dahil) ve `kuru.py` sahte borsası kısmi dolum/gecikme/reddetme modellemiyor (hep tam dolum, `kuru.py` 56-70). Sahte HTTP yanıtları el yazımı → gerçek yanıt şeması ile uyuşmama riski (özellikle algo uçları).
- Sürekli zaman dayanıklılığı (soak/chaos) testi yok; WS yeniden bağlanma `test_paper_canli.py` (4 test) ile ince kapsanmış.

---

## 4. Bilinen hatalar, TODO'lar, risk tanımı tutarsızlığı

### 4.1 Risk tanımı tutarsızlığı (%1/%3 vs %3/%6) — İKİ AYRI KURAL SETİ
| Boyut | Paper / backtest / araştırma | Canlı yürütücü |
|---|---|---|
| Kaynak | `motor/risk/limitler.py` `SERT_LIMITLER` (1-37, "kullanıcı onaylı 2026-11-06") | `motor/canli/borsa/canli_limitler.py` `CANLI_LIMITLER` (138-154, kullanıcı kararı 2026-11-11) |
| İşlem başı stop kaybı | %1 (maliyet dahil, 27) | %3 tavan (140); strateji `islem_risk` ∈ {0,5; 1; 1,5}% (`canli_ayar.py` 11-17, DURUM 2026-11-14), varsayılan %1,5 |
| Toplam açık stop riski | %5 (`portfoy_toplam_risk_yuzde`, 34) | %6 (143) |
| Günlük kayıp | %3 UTC günü; dolunca AÇIK POZİSYON DA kapanır (DURUM karar 14) | %6; yalnız yeni giriş durur, açık pozisyonlar KAPANMAZ (canli_limitler.py 122, `_adim` 197) |
| Kill | %20 zirveden | strateji %30, hesap toplamı %20 |
| Kaldıraç | nominal/özsermaye ≤ 3 | stop ≤ %15 → 3x, değilse 2x; marj ≤ %50, nominal ≤ 1,5x |
Dosya başlığı bunu bilinçli ayrım olarak belgeliyor (canli_limitler.py 1-4: "paper, backtest ve araştırma SERT_LIMITLER'i kullanmaya DEVAM EDER") ve testler değerlerin değişmediğini kilitliyor. DURUM.md'de ayrıca: "%3 fikri iptal: %6 toplam risk tavanında yalnız 2 pozisyon sığar" (satır 143) ile "CANLI_LIMITLER'de %3" (488) birlikte duruyor, sonra 2026-11-14 kararıyla {0,5; 1; 1,5}%.
**Sonuç:** Paper sonuçları (%1 boyut, 3x, günlük-kapatma) canlı davranışı (%1,5 boyut, farklı kaldıraç, günlük-kapatmama) temsil ETMİYOR. DURUM.md'de "CANLI_LIMITLER ile geçmiş oynatma, paper yanına canlı limitli gölge hesap" planı var (satır 148) ama ayrı işler. Ek tutarsızlık: `Niyet.risk_oran` (canli_yurutucu.py 51) "CANLIDA KULLANILMAZ" diye işaretli ölü alan.

Bizim motorda bunu önlemek için: TEK `RiskConfig` (bizim `risk.py` `LOCKED_CFG`), paper/backtest/live aynı `check_entry`'yi çağırmalı.

### 4.2 Bilinen sınırlamalar / açıklar (koddan ve DURUM'dan)
1. **Algo emir uçları testnet'te doğrulanmadı** (`binance_futures.py` 13-15; DURUM 191 "algo emir uçları ilk kez testnet'te doğrulanır"). `clientAlgoId`, `triggerPrice`, `algoType=CONDITIONAL`, `openAlgoOrders`, `algoOpenOrders` adları varsayım. Canlıya almadan önce şart.
2. Backtest/paper last-price OHLC; canlı stop MARK_PRICE tetikli → stop tetik farkı (özellikle fitil/flash).
3. Slipaj sabit bps; derinlik/spread yok.
4. Kısmi çıkış ve portföy (ağırlık) kolları canlıda desteklenmiyor, açıkça reddediliyor (`motor_kopru.py::uygunluk_kontrol` 28-40, `calistir.py::onkontrol`). Fail-closed iyi.
5. Bar-kapanış tetikli: stop ve trail güncelleme tur frekansında; bar içi trailing ve ani boşluk yönetimi borsadaki sabit stopa bırakılmış.
6. Emir sayısı rate limiti yok; kullanıcı veri akışı yok; exchangeInfo yenilenmiyor.
7. Hesap = strateji (ayrı alt hesap/API anahtarı); aynı hesapta birden çok strateji (netleştirme) desteklenmiyor (`canli_ayar.py` 17).
8. `kayit` yazım hataları olayı sessiz geçmiyor ama işlemi sürdürüyor (tasarım gereği).
9. Tek commit, geçmiş yok; DURUM.md "doğrulanmamış bulgular" notları (satır 331: DSR kapısı/holdout mühür kapsamı) araştırma hattı için.
10. Kod TODO/FIXME işaretçisi motor çekirdeğinde bulunmadı (grep, `arastirma/` ve `strateji/` hariç).
11. `canli_yurutucu.py::_kayit_kapanislar` içinde yeniden başlatmada türetilen kayıt sabit `model_taker=0.0005` kullanıyor (688-700 civarı) — model/gerçek komisyon karşılaştırması bu durumda gerçeği yansıtmayabilir (küçük).

---

## 5. Bağımlılıklar ve lisans
- `requirements.txt`: pymupdf, pandas (>=2.2,<4), numpy, pyarrow, **requests**, **websockets**, pytest. Python 3.13 (CI).
- Borsa: **ham REST** (`requests.Session`, el yapımı HMAC-SHA256 imza `binance_futures.py` 46-48); WS ham `websockets`. **ccxt / python-binance kullanılmıyor.** Bu bizim için avantaj: sürüm kayması ve gizli davranış yok, ama Binance değişikliklerini (algo order geçişi gibi) kendimiz takip etmeliyiz.
- Asenkron yalnız WS ve ana döngüde; emir yolu senkron.
- Muhasebe: Decimal (iyi); mum verisi float pandas. Bizim `risk.py` float → birleştirirken yuvarlama sınırında dikkat.
- Lisans: repoda LICENSE dosyası yok. Kullanıcının kendi kodu → bizim için serbest. (Not: `arsiv/` ve strateji kodlarında üçüncü taraf kaynaklı parçalar olabilir; motor çekirdeğinde bulunmadı. `trader_core/regime.py` başlığında MIT atfı zaten var — iki tarafı karıştırırsak atıf korunmalı.)

---

## 6. Karar tablosu

Çaba gün cinsinden, tek geliştirici (Claude + gözden geçirme), test dahil, makul tahmin.

| Bileşen | Olduğu gibi al | Uyarla | Yeniden yaz | Gün | Not |
|---|---|---|---|---|---|
| `binance_futures.py` (REST, imza, tekrar politikası, algo/klasik) | | X | | 2-3 | Order-count limiti, `closePosition`, `PERCENT_PRICE`, listenKey (isteğe bağlı) ekle; algo uçlarını testnet'te doğrula (+1-2 gün) |
| `kurallar.py` (exchangeInfo → kural, yuvarlama) | X (küçük değişiklik) | | | 0.5 | Sadece `boyutlandir` kısmı kendi risk.py'mize bağlanacak; `kural_cikar`, `asagi/yukari`, `stop_yuvarla` aynen |
| `canli_limitler.py` (kill/günlük mantığı) | | X | | 1 | Sayılar bizim `RiskConfig`'e taşınır; `gunluk_kill_guncelle`, `hesap_kill_guncelle` durum mantığı kalır |
| `canli_yurutucu.py` (niyet→emir, stop-önce, mutabakat, idempotensi) | | X | | 4-6 | Mantığı ve test senaryolarını koru; `Niyet/MotorGorunumu` arayüzünü bizim sade `Intent`'e indir; `_kayit_*` yerine ledger.py |
| `kuru.py` (sahte borsa) | | X | | 1-2 | Kısmi dolum, reddetme, gecikme, funding ekleyerek simülatör Broker'a dönüştür |
| `canli_ayar.py` (mod, CANLI_ONAY, anahtar env) | X | | | 0.5 | Fikir aynen (anahtar env adları, çift onay) |
| `canli_kayit.py` | | | X | 1 | ledger.py ile değiştirilir |
| `paper_canli.py` (WS tetik + REST doğruluk + boşluk doldurma) | | X | | 2 | WS yeniden bağlanma kalıbı aynen; mark fiyat/funding akışı ekle |
| `paper_veri.py` (FapiIstemci, klines, funding) | | X | | 1 | |
| Backtest/paper çekirdeği (`portfoy/motor.py` + `paper_motor.py` + `backtest/motor.py`) | | | X | 6-9 | Yeni: tek bar-döngülü `Engine` + `Broker` arayüzü (SimBroker/BinanceBroker). Mark fiyat, funding, likidasyon, slipaj modeli bizim istediğimiz gibi. 1l3a'dan: mum içi stop/hedef sırası (stop önce), gap dolumu, funding imleci mantığı |
| `strateji/temel.py` + `cikislar.py` | | X | | 1-2 | Sadece sinyal DataFrame sözleşmesi; çıkışları bizim `signals.py` fonksiyonlarına bağla (çift tanım olmasın) |
| `durum.py::atomik_yaz_*` | X | | | 0.25 | |
| Test paketi (özellikle `test_canli_borsa.py` senaryoları, lookahead kesme testi) | | X | | 2-3 | Senaryo listesi → yeni motorun kabul testleri |
| `telegram.py`, `pano.py`, araştırma (WF, PBO, DSR…) | | | | — | Kapsam dışı; DSR/PBO/WF ileride ayrıca incelenebilir |
| trader_core entegrasyonu (signals/risk/regime/ledger/veto/health) | | | X | 3-4 | Yeni motorda doğal kancalar, 1l3a'da yok |

Toplam: **sıfırdan çekirdek + 1l3a borsa katmanı uyarlaması ≈ 25-32 gün**; 1l3a'yı olduğu gibi uyarlayıp `_Motor`'a bizim risk/sinyal/ledger'ımızı sokmak ≈ 18-24 gün görünür ama bakım borcu (araştırma kodu ile iç içe, `_Motor` üç ayrı yerde sınıf miras, 2 ayrı risk kuralı, çok sayıda kapanış/strateji modülü bağımlılığı) yüksek.

### Genel öneri
**Melez: çekirdeği sıfırdan yaz, 1l3a'dan borsa katmanını ve test şartnamesini al.**

Gerekçe:
1. Gereksinimlerimizin merkezi (tek `check_entry` ile boyut/risk, 3-5x kaldıraç, mark fiyat + likidasyon, funding, trail, ledger, veto, rejim) 1l3a `_Motor`'un en az kablolanabilir yerinde: `_istenen_qty` (portfoy/motor.py 420), `SERT_LIMITLER` ve `CANLI_LIMITLER` ikilisi, ağırlık/kısmi/grup mantığı ve `PaperMotor` mirası. Uyarlamak, kullanmayacağımız ~%70 koduyla yaşamak ve iki risk kuralını birleştirmek demek.
2. Bizim `signals.py` ve `risk.py` zaten saf/test edilmiş ve 1l3a'nın `Strateji`/`CikisAyarlari` çıkış sistemiyle ÇAKIŞIYOR (trail, zaman çıkışı, hedef iki yerde). Tek doğru kaynak bizde olmalı.
3. 1l3a'nın değerli kısmı motor değil, **yürütme sertleştirmesi**: emir POST'unda otomatik tekrar yok + kimlikle sorgu, stop-önce/eski-iptal-sonra, stop kurulamazsa hemen kapat, borsa doğruluk kaynağı mutabakatı, yetim reduceOnly temizliği, kill'de önce kapat sonra iptal, dolum sonrası limit yeniden doğrulama, step/tick yuvarlama kuralları (aşağı, sıkı stop). Bunlar tam olarak "stop-önce + mutabakat + idempotensi" gereksinimlerimiz ve testli. Tekrar keşfetmek pahalı ve hataya açık.
4. Bar-tabanlı mimari (kline kapanışı + REST doğruluk) zaten bizim "12+ dk karar, LLM ≥15 dk" tarzı düşük frekanslı yaklaşıma uygun; bu tasarımı koru, mikro-yapı sorunlarına girme.

Her iki yolda da KORUNACAKLAR: `binance_futures.py` tekrar politikası, `kurallar.py`, `canli_yurutucu.py` mutabakat/stop/kill mantığı ve testleri, `canli_ayar.py` çift onay, `atomik_yaz_json`, `ws_dongu` kalıbı, lookahead kesme testi, "paper = canlı karar yolu" ilkesi (ama bizde Broker arayüzü ile).

Canlıya almadan ZORUNLU ön koşullar: (a) algo emir uçlarının testnet'te doğrulanması, (b) mark-fiyat tetikli stop ile backtest fill modelinin hizalanması veya farkın ölçülmesi, (c) tek risk kuralı, (d) emir-sayısı rate limiti ve exchangeInfo yenileme, (e) gerçek borsa yanıt şemasıyla kaydedilmiş fixture testleri.
