# Sunucu kurulumu (DigitalOcean, Ubuntu)

Hedef: mevcut droplet (FRA1, 1 vCPU, 2 GB RAM). Sunucuda calisan **baska proje bozulmaz**: yalniz `trader` kullanicisina, `/home/trader` dizinine ve `trader-*` adli systemd birimlerine dokunulur. Guvenlik duvari degistirilmez, disariya acik port acilmaz. Kendi bilgisayarinize hicbir sey kurulmaz.

## Tek komut

DigitalOcean paneli > droplet > **Access > Launch Droplet Console** ile konsolu acin, su satirlari yapistirip Enter'a basin:

```
apt-get install -y -qq git && git clone --branch claude/charming-hawking-ab5w5q https://github.com/sselimgenc-oss/SG-Github-AB-proje.git /root/trader-kurulum && bash /root/trader-kurulum/trader/deploy/install.sh
```

Depo **ozel** (private) olursa bu komut sifre sorar ve olmaz. O durumda bir "deploy anahtari" eklenir; bunu birlikte, adim adim yapariz (anahtar sunucuda uretilir, GitHub'da depoya yalniz okuma izniyle eklenir, sunucudaki yeri `/home/trader/.ssh/deploy_key`). Sonra ayni komutun ssh surumu calisir.

## Ne yapar

1. Takas (swap) yoksa 4 GB takas dosyasi kurar (varsa dokunmaz), `swappiness=10`.
2. `trader` kullanicisi (giris yapamaz) ve `trader-tg` grubunu olusturur.
3. Yalniz `python3-venv`, `git`, `sqlite3` paketlerini kurar. Python 3.11'den eskiyse (ornegin Ubuntu 22.04) hicbir sey degistirmeden durur ve bunu soyler.
4. Kodu `/home/trader/SG-Github-AB-proje` icine indirir (tekrar calistirinca gunceller).
5. Yalniz calisma bagimliliklarini kurar (requests, pandas, numpy, pyarrow, anthropic); ccxt, websockets, freqtrade, ML paketleri (lightgbm/scipy) ve test paketleri yok (`ml_mode=off` iken gerekmez).
6. Dizinleri ve ayar dosyalarini (`/etc/trader-*.env`, yoksa) olusturur; var olan ayar dosyasini asla ezmez.
7. systemd birimlerini kurar. **Veri akisi** (`trader-feed.service`, en fazla 350 MB; Binance herkese acik REST -> `var/market.sqlite`) motordan once acilir. **Ogrenen motor** (`trader-engine@learner`, en fazla 350 MB), saglik kontrolu ve gunluk yedek acilir. Ikiz motor (`--with-twin`, en fazla 350 MB) bellek kontrol edildikten sonra ayrica acilir.
8. Gecmis fiyat verisi yoksa Binance'in acik arsivinden indirir.
9. Veto, ders ve Telegram **anahtarlar doldurulana kadar kapali** kalir; sonda Turkce bir "yapilacaklar" listesi basar. Anahtarlari sohbete yazmayin: `nano /etc/trader-telegram.env` ile dosyayi acip degeri yapistirin, sonra `bash /home/trader/SG-Github-AB-proje/trader/deploy/install.sh` komutunu yeniden calistirin.

## Ilk baslatma sirasi (feed -> kurallar 10/10 -> motor)

`install.sh` birimleri bu sirayla acar; motor birimi `After=/Wants=trader-feed.service` ile feed'e baglidir.

1. **Feed baslar**: ilk acilista borsa kurallarini (`exchangeInfo`) ceker (basarisizsa sinirli yeniden dener; olmazsa sifirdan farkli kodla cikar, HTTP 451 icin ayri kod/mesaj: bu sunucudan Binance vadeli erisimi yok), sonra gecmis mumlari doldurur (`backfill`, ilk seferde birkac dakika).
2. **Kurallar 10/10**: `config/engine.base.json` icindeki 10 ciftin hepsinin kurali `var/market.sqlite` icinde olmali. Elle denetim: `sqlite3 var/market.sqlite 'select pair, fetched_ms from rules'` (10 satir).
3. **Motor baslar** ve acilis kapisini calistirir: tum ciftlerde gecerli kural **ve** taze 1m last+mark verisi yoksa en fazla `startup_wait_s` (varsayilan 600 sn) bekler, sonra tek bir CRITICAL satiriyla cikis kodu 7 ile durur; birim `failed` olur ve `OnFailure` Telegram CRIT uyarisi gonderir (Telegram anahtarlari doldurulmamissa yalniz journal'a `trader-health-fail` CRIT satiri + varsa `HEARTBEAT_FAIL_URL`; kod 7 icin otomatik yeniden baslatma yoktur: once feed'i duzeltin, sonra `systemctl start trader-engine@learner`). 10/10 degilse hicbir sey acilmaz.

Komutlar: `python -m trader_engine feed --config-dir config` (feed), `python -m trader_engine rules-snapshot --config-dir config [--out yol]` (kurallari `rules.json` + `rules.json.meta.json` olarak yazar: zaman, sha256, kaynak adresi). Durum: `status.json` icindeki `counters.rules_missing` ve `counters.data_stale` sifir olmali.

## Durum kontrolu

```
systemctl status trader-feed trader-engine@learner
journalctl -u trader-feed -n 50 --no-pager
journalctl -u trader-engine@learner -n 50 --no-pager
systemctl list-timers 'trader-*'
free -m
```

Ikiz motoru sonradan acmak: `bash /home/trader/SG-Github-AB-proje/trader/deploy/install.sh --with-twin`

## Pano (salt okunur)

`install.sh` panoyu da kurar ve baslatir (`trader-panel.service`, en fazla 64 MB, yalniz `127.0.0.1:8787`, anahtar gerekmez). Disariya acik port yoktur; erisim SSH tuneli ile:

```
ssh -L 8787:127.0.0.1:8787 <kullanici>@<sunucu>     # sonra tarayicida http://127.0.0.1:8787
journalctl -u trader-panel -n 50 --no-pager
systemctl disable --now trader-panel                  # geri alma
```

## Telefondan/bilgisayardan pano (Cloudflare Worker, Basic Auth)

Sunucu her 5 dakikada panonun tek dosyalik anlik goruntusunu Cloudflare Worker'a yukler (`trader-panel-publish.timer`); sayfada "Olusturulma: ..." damgasi ve 10 dk'dan eskiyse kirmizi bayat seridi vardir. Cihazlariniza kurulum gerekmez. Canli pano yine yalniz `127.0.0.1:8787`'de kalir.

Sizin yapacaklariniz:
1. Cloudflare'da bir API token olusturun ("Edit Cloudflare Workers" sablonu). Token'i sohbete YAZMAYIN; size verecegimiz guvenli yolla (ya da sunucuda `nano /etc/trader-panel-cf.env`) girin. Hesap kimligini (Account ID) de ayni dosyaya yazin.
2. En az 32 karakterlik rastgele bir parola uretin (parola yoneticisi) ve `install.sh` ozetindeki `wrangler secret put PANEL_SIFRE` adimiyla Worker sirri olarak girin. Kullanici adi: `trader`. Parola Worker'da saklanir, depoda/sunucu dosyasinda durmaz. Parola yoksa Worker her istege 401 doner (kapali-guvenli).
3. `https://trader-pano.<hesap>.workers.dev` adresini yer imine ekleyin (telefon + bilgisayar). Hiz siniri yoktur; bu yuzden parola uzun ve rastgele olmali.

RISK (karariniz): Workers duzenleme token'i tek Worker'a daraltilamaz, hesap capindadir. Sunucu ele gecirilirse ayni hesaptaki diger Worker'lariniz (1L3A, CT) da uzerine yazilabilir. Oneri: bu pano icin AYRI bir Cloudflare hesabi acin; ya da riski bilerek kabul edin. Karar sizindir.

Geri alma: `systemctl disable --now trader-panel-publish.timer`; Worker'i Cloudflare panelinden silin.

## Kaldirma

```
bash /home/trader/SG-Github-AB-proje/trader/deploy/uninstall.sh
```

Yalniz `trader-*` birimlerini durdurur ve siler; veri, ayar dosyalari ve kullanici kalir. Her seyi silmek icin `uninstall.sh --purge` (veri, `/etc/trader-*.env`, `trader` kullanicisi gider; `/swapfile` kalir).

## Notlar (16 Kasım 2026)
- Veto ayarlanmadan öğrenen bot işlem açmaz (`veto_mode: required`, güvenli taraf). Bu beklenen davranıştır.
- Veto artık piyasa verisini motorun ortak `var/market.sqlite` deposundan okur (ağ yok, ccxt yok).
- Sunucuya geçmiş veri olarak 15m/1h/4h/1d indirilir; 1m verisi yalnız geçmiş test aracı için gerekir, sunucuda gerekmez.

## Ilk gun runbook (bos sunucu; 30 Kasim paper baslangici)

Sira onemlidir; her adim bir sonrakinin on kosuludur. Ayrintili denetim ve acik maddeler: `docs/hazirlik-denetimi.md`. Komutlar root olarak calistirilir.

```
T=/home/trader/SG-Github-AB-proje/trader ; cd $T
run_as_trader() { runuser -u trader -- sh -c "cd $T && PYTHONPATH=$T/src $*"; }     # trader olarak, depo dizininde
```

**0. Onceden hazirla** (degerleri sohbete degil, sunucuda `nano` ile yazin): dis nabiz adresi `HEARTBEAT_URL` (https://, ornegin healthchecks.io; saglik birimi bu OLMADAN her 5 dk basarisiz olur), Telegram bot token + chat id, veto icin Anthropic anahtari + `TRADER_VETO_HMAC_KEY` (>=32 karakter). **Ders anahtarini (`/etc/trader-lesson.env`) simdilik BOS birakin**: ders servisi su haliyle her saat basarisiz olur (denetim OPEN-6). Ikiz motor ve yedek ikiz defterini bekler: **`--with-twin` ile kurun** (aksi halde saglik surekli CRIT, yedek her gun `source_missing`; denetim OPEN-4).

**1. Kurulum**
```
bash /root/trader-kurulum/trader/deploy/install.sh --with-twin
nano /etc/trader-health.env  /etc/trader-telegram.env  /etc/trader-veto.env      # anahtarlari doldur (ders env'i bos kalsin)
bash $T/deploy/install.sh --with-twin          # yeniden: zamanlayicilari acar
systemctl list-units 'trader-*' --no-pager ; systemctl list-timers 'trader-*' --no-pager ; free -m
```
Beklenen: ozetin sonundaki "YAPILACAKLAR" listesi bos (ya da yalniz bilerek ertelediklerin); `trader-feed`, `trader-engine@learner`, `trader-engine@twin`, `trader-panel` active.

**2. Feed: baslat + backfill** (ilk seferde birkac dk)
```
systemctl is-active trader-feed ; journalctl -u trader-feed -n 40 --no-pager
sqlite3 -readonly $T/var/market.sqlite "select kind,tf,count(*),datetime(max(open_ms)/1000,'unixepoch') from bars group by 1,2"
date -u ; ls -l $T/var/feed-status.json
```
Beklenen: `last/1m` ve `mark/1m` icin en yeni mum `date -u`'dan en fazla ~2 dk geride; `15m/1h/4h` dolu. Hata: `systemctl show trader-feed -p Result -p ExecMainStatus`: **6** = HTTP 451 (bu sunucudan Binance vadeli yok; baska bolge gerekir), **5** = kurallar alinamadi (ag/Binance), **1** = ag yok (traceback). Hepsinde birim `failed` olur ve OnFailure alarmi calisir.

**3. Kurallar 10/10**
```
sqlite3 -readonly $T/var/market.sqlite "select count(*) from rules"                  # 10
sqlite3 -readonly $T/var/market.sqlite "select pair,datetime(fetched_ms/1000,'unixepoch') from rules order by 1"
sqlite3 -readonly $T/var/market.sqlite "select k,v from feed_meta where k in ('rules_fetched_at','rules_last_error')"   # last_error bos
```

**4. init-ledger** (motor birimi ExecStartPre ile kendisi yapar; elle dogrulama)
```
run_as_trader $T/.venv/bin/python -m trader_engine init-ledger --bot learner --config-dir config     # "etkin parametre var: dokunulmadi" (ikinci kez)
run_as_trader $T/.venv/bin/python -m trader_engine init-ledger --bot twin    --config-dir config
sqlite3 -readonly $T/var/learner/ledger.sqlite "select count(*) from param_versions; select count(*) from param_activations"   # 1 ve 1
```

**5. Motor acilis kapisi**
```
systemctl restart trader-engine@learner trader-engine@twin
journalctl -u trader-engine@learner -n 30 --no-pager | grep -E "acilis kapisi|CRITICAL"
systemctl show trader-engine@learner -p ActiveState -p Result -p ExecMainStatus
```
Beklenen: `engine acilis kapisi tamam: 10/10 cift kural+taze veri`, `ActiveState=active`. Cikis **7** = kapi gecmedi (CRITICAL satiri hangi cift/ne eksik oldugunu yazar); oto-yeniden baslatma YOK: feed'i duzelt, sonra `systemctl reset-failed trader-engine@learner && systemctl start trader-engine@learner`.

**6. status.json**
```
python3 - <<'PY'
import json,datetime
for b in ("learner","twin"):
    s=json.load(open("/home/trader/SG-Github-AB-proje/trader/var/%s/status.json"%b))
    print(b, s["mode"], "loop_at",s["loop_at"], "gate",s["gate"], "kill",s["kill"], "counters",{k:s["counters"][k] for k in ("rules_missing","data_stale")})
PY
date -u
```
Beklenen: `mode=paper`, `loop_at` `date -u`'dan <2 dk, `gate={'ok': True, 'code': 'ok'}`, `rules_missing=0 data_stale=0`, `kill False`. NOT: `entries_open` veto'yu kapsamaz (adim 9).

**7. Saglik**
```
systemctl start trader-health.service ; journalctl -u trader-health -n 5 --no-pager ; echo "cikis=$(systemctl show trader-health -p ExecMainStatus --value)"
cat /var/lib/trader-health/state.json | head -c 600 ; ls -l /var/backups/trader
```
Beklenen: son JSON satirinda `"overall": "OK"` (ilk saat `WARN` + `ledger_write_stale_warmup` olabilir), `"heartbeat": true`. `health_run: beklenmeyen hata: ValueError` = `HEARTBEAT_URL` bos/https degil. Dis nabiz panelinde (healthchecks vb.) ilk ping gorunmeli.

**8. Telegram test mesaji**
```
set -a ; . /etc/trader-telegram.env ; set +a
runuser -u trader -g trader-tg -- env TELEGRAM_BOT_TOKEN="$TELEGRAM_BOT_TOKEN" TELEGRAM_CHAT_ID="$TELEGRAM_CHAT_ID" TELEGRAM_VAR_DIR="$TELEGRAM_VAR_DIR" \
  $T/.venv/bin/python -I $T/scripts/telegram_run.py send --severity INFO --dedup-key kurulum-testi-$(date +%s) "Kurulum testi"     # "sent" (ya da "spooled")
systemctl status trader-telegram --no-pager | head -5
systemctl start trader-health-fail@deneme.service ; journalctl -t trader-health-fail -n 3 --no-pager      # CRIT zinciri: Telegram "Birim basarisiz: deneme.service" + journal
```
Telefonda `/durum` yaz: `kip=paper kill=False ... entries_open=True`. `spooled` = mesaj kuyruga yazildi, daemon gonderecek (`ls $T/var/telegram/outbox`). Anahtarlar bossa Telegram timer/daemon hic acilmaz; CRIT yalniz journal + `HEARTBEAT_FAIL_URL`'e gider (sessiz degil ama telefona dusmez).

**9. Veto belgesi var + taze**
```
systemctl start trader-veto.service ; journalctl -u trader-veto -n 20 --no-pager ; systemctl show trader-veto -p ExecMainStatus   # 0 (belge yazildi), 10/11 (bu tur karar yok / butce) beklenen
python3 -c "import json,datetime as d;x=json.load(open('$T/shared/veto/veto.json'));print(x['status'],x['reason'],x['generated_at'],x['expires_at'],len(x['decisions']),'karar')"
stat -c '%y %U %a' $T/shared/veto/veto.json ; date -u ; systemctl list-timers trader-veto.timer --no-pager
sqlite3 -readonly $T/var/learner/ledger.sqlite "select veto_status,veto_reason,count(*) from decision_events group by 1,2"     # ilk adaylardan sonra
```
Beklenen: `status=ok`, `expires_at` simdiden en fazla 45 dk ileride (ttl 2700 sn), dosya 30 dk'da bir yenilenir; 20 karar = 10 cift x long/short. Defterde `veto_status=missing/key_missing` goruluyorsa motor HMAC anahtarini gormuyor (denetim OPEN-1) ve **hicbir giris acilmaz**; `stale/file_expired` = veto zamanlayicisi durmus; `missing/file_missing` = veto hic calismamis. Veto durumu henuz saglik/panel alarmi DEGILDIR (OPEN-5): bu sorguyu gunde en az bir kez calistirin.

**10. Pano okuyor mu**
```
curl -s http://127.0.0.1:8787/api/status | python3 -m json.tool | head -40        # bots.learner.state ve bots.twin.state = "live"; kill_file_exists=false
curl -s "http://127.0.0.1:8787/api/ledger?bot=learner" | head -c 400 ; echo ; curl -s http://127.0.0.1:8787/api/health | head -c 300
journalctl -u trader-panel -n 10 --no-pager
```
Tarayici icin: `ssh -L 8787:127.0.0.1:8787 <kullanici>@<sunucu>`. `ok:false,code:status_bayat` = motor 120 sn'dir yazmiyor.

**11. Kill anahtari tatbikati** (yol: `$T/shared/KILL`; motor, Telegram `/hepsini_kapat` ve pano ayni dosyayi kullanir)
```
run_as_trader $T/.venv/bin/python -m trader_engine kill --by runbook --reason deneme
ls -l $T/shared/KILL ; curl -s http://127.0.0.1:8787/api/status | grep -o '"kill_file_exists": *[a-z]*'      # true
journalctl -u trader-engine@learner -n 5 --no-pager
run_as_trader $T/.venv/bin/python -m trader_engine kill --clear
```

**12. Yedek**
```
systemctl start trader-backup.service ; ls -l /var/backups/trader/$(date -u +%F)/ ; cat /var/backups/trader/$(date -u +%F)/MANIFEST.json | head -c 500
```
Beklenen: 4 dosya (`ledger_*`, `state_*` x learner/twin), `"ok": true`.

**Hizli ariza tablosu**

| Belirti | Anlami | Ne yapilir |
|---|---|---|
| `trader-feed` failed, ExecMainStatus 6 | HTTP 451 | Binance vadeli bu bolgeden yok; sunucu bolgesi degisir |
| `trader-engine@*` failed, ExecMainStatus 7 | acilis kapisi: kural/veri eksik | adim 2-3, sonra `reset-failed` + `start` |
| health CRIT `market_bars_stale` | feed durdu / yavas | `journalctl -u trader-feed`; `systemctl restart trader-feed` |
| health CRIT `api_unreachable:twin` | ikiz kurulu degil | `install.sh --with-twin` |
| veto `missing/key_missing` | motor HMAC anahtarini gormuyor | denetim OPEN-1 |
| Telefona alarm gelmiyor | Telegram anahtari bos ya da `NOTIFIER=log` | adim 8; `/etc/trader-health.env` (denetim OPEN-3) |

