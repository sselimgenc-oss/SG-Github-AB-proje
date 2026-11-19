# DD-12: Sunucuda yapılacaklar (adım adım)

Bu belge sunucu sahibi için. Her adımı sırayla yapın. Her adımın sonunda **"Kontrol"** satırındaki sonucu görmeden bir sonrakine geçmeyin. Komutlar sunucuda **root** olarak çalışır (DigitalOcean > droplet > **Access > Launch Droplet Console**).

**Bu adımlar gerçek para değildir.** Canlı (gerçek para) birimi kurulmaz, açılmaz. Testnet motoru bu adımlarda yalnız durdurulur ve tekrar başlatılır.

Yollar (kurulum betiğindeki gibi): kod `/home/trader/SG-Github-AB-proje/trader`, yapılandırma `config`, sanal ortam `.venv`.

---

## Adım 1: Kodu GitHub'a gönderin (sizin bilgisayarınızda)

1. Depoda DD-12 değişikliklerini commit edin. Commit mesajı örneği: `DD-12 WP-18: kapasite olcumu, M1 gece egitimi, evrenden cikan ciftler, kurulum`.
2. Commit'i GitHub'a gönderin (`git push`). Dal: `claude/charming-hawking-ab5w5q`.
3. Commit kodunu kopyalayın (40 karakter). Komut: `git rev-parse HEAD`. Bu kodu aşağıda `<KOD>` yerine yazacaksınız.

**Kontrol:** GitHub'da commit görünüyor ve kodu 40 karakter.

---

## Adım 2: Mevcut sürümü görün

Sunucuda:

```
cat /etc/trader-release
```

**Kontrol:** `COMMIT=...` satırı görünüyor. Bu, şu anki sürümdür (kurulumdan sonra değişecek).

---

## Adım 3: Kurulumu çalıştırın (yeni birimleri kurar)

```
COMMIT=<KOD> bash /usr/local/lib/trader-root/current/deploy/install.sh
```

`<KOD>` yerine Adım 1'deki 40 karakteri yazın. Betik kendini yeni sürümün kopyasıyla yeniden başlatır. Bitince ekrandaki **"DD-12 zamanlayıcı denetimi"** bölümüne bakın:

- `etkin: ...` satırları olmalı (notes, weekly-summary, ml-retrain, universe, counterfactual).
- `UYARI: ... etkin değil` görürseniz: `systemctl enable --now <birim-adi>` yazın.
- `UYARI: eski birim duruyor` görürseniz: install.sh'i bir kez daha çalıştırın.

**Kontrol:** `cat /etc/trader-release` çıktısı `COMMIT=<KOD>` gösteriyor.

**Not:** Betik testnet motorunu, anahtar dolu ise, kendisi başlatabilir. Bir sonraki adım bunu durdurur.

---

## Adım 4: Testnet motorunu durdurun (dolaşan çıkış kuyruğu için)

```
systemctl stop trader-engine-env-retry@testnet.timer
systemctl stop trader-engine-testnet.service
systemctl is-active trader-engine-testnet.service
```

**Kontrol:** son satır `inactive` (ya da `failed`) olmalı. `active` ise yukarıdaki stop komutunu tekrar yazın.

---

## Adım 5: DD-11 çıkış kuyruğu (outbox) için kuru koşu

Motor durdu. Önce yalnız rapor alın, hiçbir şey değişmez:

```
cd /home/trader/SG-Github-AB-proje/trader
sudo -u trader env PYTHONPATH=src .venv/bin/python -m trader_engine outbox-quarantine --bot learner --env testnet --config-dir config --dry-run
```

**Kontrol:** Çıktıda taşınacak satır sayısı yazar. Bu sayıyı not alın.
- Sayı **0** ise Adım 6'yı atlayın.
- Sayı **0'dan büyük** ise Adım 6'ya geçin.

---

## Adım 6: Çıkış kuyruğunu uygulayın (yalnız Adım 5 sayı > 0 ise)

Motor hâlâ durmuş olmalı (Adım 4).

```
cd /home/trader/SG-Github-AB-proje/trader
sudo -u trader env PYTHONPATH=src .venv/bin/python -m trader_engine outbox-quarantine --bot learner --env testnet --config-dir config --apply
```

**Kontrol:** Çıktı taşınan satır sayısını gösterir (Adım 5'teki sayı ile aynı olmalı). Hata yoksa devam edin.

Testnet motorunu yeniden başlatın:

```
systemctl start trader-engine-testnet.service
systemctl start trader-engine-env-retry@testnet.timer
systemctl is-active trader-engine-testnet.service
```

**Kontrol:** `active`.

---

## Adım 7: Kâğıt öğrenenin strateji etiketini değiştirin (price_action_lab_ml)

Kâğıt öğrenen (learner) motorunu kısa süre durdurup defterdeki etiketi günceller. Parametreler aynı kalır, yalnız strateji adı değişir.

```
systemctl stop trader-engine@learner.service
cd /home/trader/SG-Github-AB-proje/trader
sudo -u trader env PYTHONPATH=src .venv/bin/python -m trader_engine init-ledger --bot learner --env paper --config-dir config --reason strategy_update
systemctl start trader-engine@learner.service
```

**Kontrol:**
- `init-ledger` çıktısı `strateji etiketi guncellendi: ... -> price_action_lab_ml ...` demeli. (`etkin surum zaten price_action_lab_ml: dokunulmadi` de kabul: etiket zaten doğru.)
- `systemctl is-active trader-engine@learner.service` → `active`.
- Hata: `ledger_stamp_mismatch` görürseniz durun ve çıktıyı bana bildirin (anahtar veya parola yapıştırmayın).

---

## Adım 8: Birimleri ve zamanlayıcıları kontrol edin

Etkin birimler:

```
systemctl is-active trader-feed trader-engine@learner trader-panel trader-health.timer
```

**Kontrol:** dört satır da `active`.

Zamanlayıcılar (sonraki çalışma zamanları):

```
systemctl list-timers 'trader-*' --all --no-pager
```

**Kontrol:** şu zamanlayıcılar listede: `trader-lesson` (her saat :17), `trader-notes` (her gün 02:55 UTC), `trader-ml-retrain` (her gün 03:10 UTC), `trader-counterfactual@learner` (her gün 23:10 UTC), `trader-universe` (ayın 1'i 00:30 UTC), `trader-weekly-summary` (Pazar 18:10 UTC).

Bellek sınırları:

```
systemctl show trader-ml-retrain.service -p MemoryHigh -p MemoryMax
systemctl show trader.slice -p MemoryMax
```

**Kontrol:** ml-retrain `MemoryHigh=250M` ve `MemoryMax=350M`; slice `MemoryMax=1300M`.

Eski veto ve ikiz birimler kalmamış olmalı:

```
systemctl list-units 'trader-veto*' 'trader-*twin*' --all --no-pager
```

**Kontrol:** liste boş ya da yalnız `not-found` / `inactive` satırları var.

---

## Adım 9: Gece eğitimini (ML) ilk kez görün

Gece 03:10 UTC'de eğitim çalışır: kurulum süzgeci ve M1 (kendi adayı). İlk çalıştırmayı sonraki sabah kontrol edin:

```
systemctl status trader-ml-retrain.service --no-pager | head -12
journalctl -u trader-ml-retrain.service -n 30 --no-pager
ls -la /home/trader/SG-Github-AB-proje/trader/models/pa_proposer
```

**Kontrol:** son çalıştırma `status=0/SUCCESS` (ya da `m1_error` yoksa başarılı) ve `M1@1h.json`, `M1@4h.json` dosyaları var. Hata varsa `journalctl` çıktısını bana bildirin.

---

## Adım 10: Pano (salt okunur) kontrolü

Pano sunucuda yalnız `127.0.0.1:8787` adresinde çalışır. Kendi bilgisayarınızdan SSH tüneliyle açın:

1. Kendi bilgisayarınızda bir terminal açın:
   ```
   ssh -L 8787:127.0.0.1:8787 root@<sunucu-adresi>
   ```
2. Tarayıcıda `http://127.0.0.1:8787` adresini açın.
3. Sunucuda kontrol: `curl -s -o /dev/null -w "%{http_code}\n" http://127.0.0.1:8787/` → `200`.

**Kontrol:** pano açılıyor; kâğıt botta 44 çift görünüyor; veto satırı yok; ML satırları (M1) listeleniyor. Pano için şifre ya da anahtar gerekmez.

---

## Sorun olursa

- Herhangi bir adımda beklenmeyen hata: çıktıyı kopyalayın, **anahtar, token ya da parola yapıştırmayın**, bana bildirin.
- Öğrenen motoru geri almak için: `systemctl stop trader-engine@learner.service` (kâğıt; gerçek para etkilenmez).
- Telegram ve ders servislerinin anahtarları `nano /etc/trader-*.env` ile doldurulur; sohbete yazılmaz.
