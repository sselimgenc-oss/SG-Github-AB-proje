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
5. Yalniz calisma bagimliliklarini kurar (requests, websockets, pandas, numpy, pyarrow, anthropic, ccxt); freqtrade ve test paketleri yok.
6. Dizinleri ve ayar dosyalarini (`/etc/trader-*.env`, yoksa) olusturur; var olan ayar dosyasini asla ezmez.
7. systemd birimlerini kurar. **Veri akisi** (`trader-feed.service`, en fazla 350 MB; Binance herkese acik REST -> `var/market.sqlite`) motordan once acilir. **Ogrenen motor** (`trader-engine@learner`, en fazla 350 MB), saglik kontrolu ve gunluk yedek acilir. Ikiz motor (`--with-twin`, en fazla 350 MB) bellek kontrol edildikten sonra ayrica acilir.
8. Gecmis fiyat verisi yoksa Binance'in acik arsivinden indirir.
9. Veto, ders ve Telegram **anahtarlar doldurulana kadar kapali** kalir; sonda Turkce bir "yapilacaklar" listesi basar. Anahtarlari sohbete yazmayin: `nano /etc/trader-telegram.env` ile dosyayi acip degeri yapistirin, sonra `bash /home/trader/SG-Github-AB-proje/trader/deploy/install.sh` komutunu yeniden calistirin.

## Ilk baslatma sirasi (feed -> kurallar 10/10 -> motor)

`install.sh` birimleri bu sirayla acar; motor birimi `After=/Wants=trader-feed.service` ile feed'e baglidir.

1. **Feed baslar**: ilk acilista borsa kurallarini (`exchangeInfo`) ceker (basarisizsa sinirli yeniden dener; olmazsa sifirdan farkli kodla cikar, HTTP 451 icin ayri kod/mesaj: bu sunucudan Binance vadeli erisimi yok), sonra gecmis mumlari doldurur (`backfill`, ilk seferde birkac dakika).
2. **Kurallar 10/10**: `config/engine.base.json` icindeki 10 ciftin hepsinin kurali `var/market.sqlite` icinde olmali. Elle denetim: `sqlite3 var/market.sqlite 'select pair, fetched_ms from rules'` (10 satir).
3. **Motor baslar** ve acilis kapisini calistirir: tum ciftlerde gecerli kural **ve** taze 1m last+mark verisi yoksa en fazla `startup_wait_s` (varsayilan 600 sn) bekler, sonra tek bir CRITICAL satiriyla cikis kodu 7 ile durur; birim `failed` olur ve `OnFailure` Telegram CRIT uyarisi gonderir (kod 7 icin otomatik yeniden baslatma yoktur: once feed'i duzeltin, sonra `systemctl start trader-engine@learner`). 10/10 degilse hicbir sey acilmaz.

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
