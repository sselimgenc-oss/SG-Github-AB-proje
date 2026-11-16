# Motor — mentor incelemesi (16 Kasım 2026, HEAD c0bb622)

Mark tetikli stop dolumu: hata değil (`brokers/paper.py:512` stop seviyesi − 5 bps; gap'te last açılışı). 575 stop çıkışının 565'inde last aralığı stopu içeriyor; last-açılış yedeği ΣR'yi −0.11 değiştirir. +35.8 yol gürültüsü (iki TRX iz süren stop ≈ +14.6R, en iyi dört işlem +21R). Avantaj olarak okunmaz.

## A — kağıttan (30 Kasım) önce zorunlu
1. **Funding canlı kağıtta pratikte hiç kesilmiyor.** `paper.py:377-380` funding noktası yokken imleci ilerletiyor; `marketdata/feed.py:360-363` funding'i saatlik rastgele fazda çekiyor; ham `fundingTime` saat başını birkaç ms geçerse `paper.py:383` atıyor. Düzeltme: nokta gelene kadar imleç bekler (sınırlı), çekim 00/08/16 + saniyeler, zaman tabana yuvarlanır; `funding_missing` uyarısı.
   **YAPILDI:** `paper.py` imleç noktayı bekler (`PaperConfig.funding_max_wait_s`=900 sn; sonra `funding_missing` sayacı ve ilerler); `funding.floor_funding_time` + `feed._floor_funding_ms` ham zamanı 8 saatlik ızgaraya yuvarlar; feed 00/08/16 UTC + `funding_boundary_delay_s` (5 sn) çeker, saatlik çekim yedek.
2. **Sessiz defter kaybı.** `engine.py:412` `DrainResult.failed`'i atıyor; kalıcı geçersiz outbox satırı kuyruğu tıkıyor (`state.py:458-459`), işlem kapanınca girişler yeniden açılıyor. Düzeltme: say ve `entries_blocked_reason="outbox_stuck"`.
   **YAPILDI:** `engine._outbox_health` `DrainResult.failed`'i `outbox_failed` sayacına yazar ve `outbox_stuck` bloğunu koyar (status.json'da görünür); işlem kapanınca açılmaz, yalnız outbox boşalınca kalkar.

## B — kağıt döneminde
3. `engine.py:170-184`, `status.py:45`: veto eksik/bayat ya da besleme durmuşken `entries_open` true kalıyor → kapı koduna veto durumu ve dakika yaşı.
4. `engine.py:712-719`: 20 sn sonra eksik dakika işleniyor, geç barlar tekrar oynatılmıyor → pozisyon/emir olan çiftler için daha uzun bekle; `minute_gaps` uyarısı.
5. `config/engine.base.json`'da `target_trade_risk` yok: kağıt %1.4, canlı %0.5 → şimdi 0.005. **YAPILDI:** `config/engine.base.json` `target_trade_risk: 0.005` (EngineConfig/`risk_config` zaten kullanıyor; testler kilitli 0.014 ile pinli).
6. `engine.py:232` gün başını cüzdan olarak saklıyor, `gates.py:183` özsermayeyle kıyaslıyor → özsermaye saklanır. **YAPILDI:** `ensure_day_start` `account().equity` saklar.
7. `engine.py:442-449`: kill yalnız adım içinde çalışıyor; besleme durunca etkisiz ve bekleyen girişlerin dolmasına izin veriyor → `opening` emirleri iptal; canlıda veriden bağımsız yol.
8. İki bot veto dosyasını bar kapanışında okuyor, farklı nesiller görebilir → sınır dışında yenile; `generated_at` kayıtla kıyasla.

## C — notlar
- `engine.py:668-675`: `insert_position` sonrası istisna kalıcı `opening` satırı bırakır; `reconcile.py:84` görmez.
- `engine.py:487-490`: risk ihlali çıkışı stopsuz `closing` pozisyon bırakır; `reconcile.py:94` atlar (canlıda önemli).
- Kapı zincirinde fail-open yok. Kağıtta yeniden başlatmadan sonra çift emir ya da stopsuz pozisyon yok. Funding işareti, komisyon, likidasyon doğru.

**freqtrade silme:** yalnız compat-tick çapraz doğrulamasını bekler. A maddeleri kağıt başlangıcını bekletir.
