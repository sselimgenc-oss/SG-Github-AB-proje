# Haber / duygu etiketi — belirtim (19 Kasım 2026)

**Yalnız kayıt.** Etiket hiçbir işlemi engellemez; sinyali, riski, boyutu, sıralamayı ve kapı zincirini değiştirmez. Kâğıtta deneme süresi ya da gölge koşu yoktur: doğrudan devrededir. Sözleşme kullanıcının CT projesiyle **aynıdır** (`copytrade/canli/haber.py`, `docs/VERI_SOZLESMESI.md` "Haber / duygu etiketi"; salt okunur kopyadan uyarlandı, çalıştırılmadı; `THIRD_PARTY_NOTICES.md`).

## Kaynaklar (anahtarsız, yeni bağımlılık yok)
- Duygu: alternative.me Crypto Fear & Greed, `https://api.alternative.me/fng/?limit=1`.
- Haber: CoinDesk (`https://www.coindesk.com/arc/outboundfeeds/rss/`) ve Cointelegraph (`https://cointelegraph.com/rss`) RSS.
- Yalnız https okuma; stdlib `urllib` + `xml.etree` (DTD/ENTITY içeren belge reddedilir). Zaman aşımı 5 sn, toplam bütçe 12 sn, yanıt en fazla 1 MB.

## Alanlar (CT ile birebir)
- `duygu` = `{deger: 0-100 tam sayı, sinif: metin}` ya da `null`. Okuma 26 saatten eskiyse yazılmaz (`null`).
- `haber` = `{<coin>: {adet_24s: tam sayı, ton: "pozitif"|"negatif"|"notr"|null}}`; yalnız o çiftin coini. Coin = çiftin baz varlığı (`BTC/USDT` → `BTC`).
- Zaman damgaları UTC milisaniye; pencere 24 saat. `adet_24s` = o coini anan başlık sayısı; `ton` = pozitif/negatif başlık sayısının çoğunluğu (eşitse `notr`, başlık yoksa `null`).
- Ton **kaba** anahtar kelime sayımıdır (CT'deki `POZITIF`/`NEGATIF` listeleri aynen; İngilizce başlık, olumsuzlama/bağlam anlaşılmaz). Eşleşme: sembol büyük harfle tam kelime ya da bilinen isim (`ISIMLER`: bitcoin, ethereum/ether, solana; CT ile aynı başlangıç).

## Toplayıcı
- `scripts/haber_run.py` (saf çözücüler `src/trader_core/haber.py`). Saatlik oneshot: `deploy/trader-haber.service` + `.timer` (`OnCalendar=hourly`, `Persistent=true`). `Slice=trader.slice`, `MemoryMax=100M` (ölçülen tepe ~16 MB), `Nice=15`; yazılabilir yalnız `/opt/trader/var/durum`.
- Önbellek: `var/durum/haber_v1.json`, atomik yazılır: `{"sema":"ml.haber.v1","uretim":ISO,"duygu":{deger,sinif,ms}|null,"basliklar":[{t,b,ton}...],"haber_ms":ms|null}` (en fazla 150 başlık, 25 saatten eskiler atılır).
- Her hata yutulur; kaynak okunamazsa son önbellek korunur, hiçbir kaynak okunamazsa dosya yeniden yazılmaz. Birim hatayla düşmez (çıkış 2 yalnız yerel yazma hatası).

## Etiketin yazıldığı yer
- Kâğıt motoru (`cfg.mode == "paper"`) karar kaydının mevcut `features` JSON sütununa (`decision_events.features`) iki anahtar ekler: `duygu` ve `haber`. Kaydı alınan giriş de, alınmayan sinyal/aday da (counterfactual bu kayıttan beslenir) aynı karar satırını kullanır; **şema değişmez**, yeni sütun/tablo yoktur.
- Önbellek yok, bozuk ya da bayatsa (haber 6 saatten eski, duygu 26 saatten eski, ileri tarihli) ilgili alan `null`; ikisi de `null` ise anahtar hiç yazılmaz (okuyucu yok alanı `null` sayar; geri test ve eski kayıtlar bayt bayt aynı kalır).
- Defter, `features` içinde yalnız bu iki anahtar için iç içe sözlüğe izin verir; ayrıca aynı kararın yeniden yazımında (idempotans karşılaştırması) bu iki anahtar sayılmaz, böylece etiket hiçbir kayıt sonucunu değiştirmez.
- Motor etiketi **yazar, karar yolunda okumaz**; ML özellik vektörüne girmez (`f_*` tarifi değişmez).

## Günlük özet
`gunluk_ozet_v1` `notlar` içine en fazla 1 madde: `Duygu: Korku (28)` (sınıf Türkçeleştirilir). Şema alanı eklenmez; duygu yok/bayatsa madde yazılmaz.

## Testler
Sentetik veri, ağ yok (getirici enjekte). Etiketli ile etiketsiz motorun kararlarının aynı olduğu kanıtlanır; kilitli dönem tarihleri ve `var/history` yazımı yoktur.
