# Paper'ı 20 hesaptan 10 hesaba indirme (odak listesi) — sunucu adımları

**Başlamadan önce:** önce `sudo -i` ile root olun (DigitalOcean konsolunda zaten root iseniz gerek yok; satırın başında `#` görürsünüz). Aşağıdaki **tüm komutlar root kabuğunda** yazılır, başına `sudo` koymanız gerekmez.

**Ne oluyor?** Paper'daki hesap sayısı **20'den 10'a** iner (sizin 14 Kasım kararınız, DURUM.md "ODAK LİSTESİ"):

- **7 hesap panoda görünür:** dis__gauss-stoch-eth, HAM:X005:664#v1, dis__hma-atr-rider (swing); dis__ewo-ema-ofset, dis__e0v1en, HAM:B001:670#v1 (gün içi);
  HAM:X005:705 (**yedek**: yalnız 664 ya da hma tek başına bozulursa devreye girer; panoda "yedek" işaretiyle).
- **3 hesap gizli çalışır:** dis__lube, HAM:B001:574#v1, HAM:X005:730#v2. Paper'da koşmaya devam eder, ama **panoda, toplam kasada ve Telegram özetinde yoktur**.
- **10 hesap durdurulur:** jt-awesome-osilator, uc-ortalama-boga-sma60, voltarget-trend, haftalik-macd-gunluk-ma, pf__sabit_sepet, HAM:X005:301#v1, HAM:X005:138#v3,
  HAM:X005:259#v1, HAM:X005:793#v1, HAM:B001:538#v1. Kayıtları **silinmez**: `/var/lib/1l3a-paper/durum/arsiv_durdurulan_20261114/` klasörüne taşınır.

**Kalan 10 hesaba ne olur?** Hiçbir şey: açık pozisyon, işlem geçmişi, kasa aynen yüklenir. Pano toplamı artık **7 görünür hesabın** toplamıdır (başlangıç 70.000 USD).
Risk limitleri ve canlı kapıları (kapanış adayları canlıya alınamaz) değişmedi.

**Telegram:** gizli 3 hesabın olayları (kill switch dahil) Telegram'a **gitmez**; yalnız kayıtta ve günlükte (`journalctl`) görünür. Telegram özeti ve işlem bildirimleri yalnız 7 görünür hesabı anlatır.

**Güvenlik:** Motor yalnız "20'li set" imzalı (be84a61831ca9bbc) durumu 10'a indirir. Başka imza görürse **açık hatayla başlamaz** (durum bozulmaz).
Sunucu hâlâ 10 ya da 16 hesaplıysa önce eski `deploy/v2_kapanis_ekle.sh` ile 20'ye çıkılmalıdır (o betik yalnız eski sürümde çalışır; bu sürümde zaten 10'lu sette durur).

## Adımlar (sunucuda; her kutuyu sırayla kopyala-yapıştır, bir sonrakine geçmeden çıktıyı kontrol edin)

**1. Paper'ı durdurun**
```bash
systemctl stop 1l3a-paper
systemctl is-active 1l3a-paper        # "inactive" yazmalı
```
**2. Durumu yedekleyin** (kopya; asıl dizin yerinde kalır) ve şu anki kod sürümünü not edin
```bash
cp -a /var/lib/1l3a-paper/durum /var/lib/1l3a-paper/yedek_10_oncesi_$(date +%Y%m%d_%H%M)
cd /opt/1l3a
git rev-parse HEAD                    # çıkan uzun kodu bir yere NOT EDİN (geri dönüş için)
git branch --show-current             # dal adını da not edin
```
**3. Yeni kodu çekin**
```bash
cd /opt/1l3a
git pull --ff-only                    # root kabuğunda (GitHub anahtarı root'tadır)
chown -R l3a:l3a /opt/1l3a            # dosyaların sahibi yine l3a olsun (paper yazabilsin)
```
**4. Betiği çalıştırın** (durum imzasını kontrol eder, ön kontrol yapar, paper'ı başlatır, 3 dk sonra kontrol çıktısı yazar)
```bash
cd /opt/1l3a
bash deploy/v2_odak_10.sh
```
Betik hata verirse ekrana "HATA ... durdu" ve ne yapacağınızı yazar; çıktının tamamını bana yapıştırın. **Başarılıysa da çıktının tamamını bana yapıştırın.**
(Kilit günlüğü ayarı — `L3A_KILIT_LOG` drop-in'i — servis tanımında zaten durur; dokunmanız gerekmez.)

## Doğrulama (3-5 dakika sonra)
```bash
systemctl is-active 1l3a-paper                                                    # active
ls /var/lib/1l3a-paper/durum/hesaplar | wc -l                                      # 10
find /var/lib/1l3a-paper/durum/arsiv_durdurulan_20261114 -mindepth 1 -maxdepth 1 -type d | wc -l   # 10
python3 -c "import json;d=json.load(open('/var/lib/1l3a-paper/durum/paper_state.json'));print(len(d['hesaplar']),d['set_imza'])"   # 10 fffbc6624416634e
journalctl -u 1l3a-paper -n 80 --no-pager | grep -i -E "arşiv|hata|error|BAŞLAMAZ"
```
Beklenen: "durdurulan hesaplar arşivlendi" satırı; panoda **7 strateji**, "Özsermaye" kartında başlangıç **70.000 USD**, 705'te "yedek" işareti; gizli 3 hesap panoda **görünmez**.
Telegram günlük özeti de yalnız 7 stratejiyi anlatır. Pano "Bütünlük" bandı **eşleşti** göstermeli (yeni kayıt: `stratejiler/butunluk_kayit_v2_10.json`).
Normal uyarılar: mevcut `DK_JNJ`/`DK_MA` notları (kripto stratejilerini etkilemez).

## Hata durumunda
- `kayıtlı set imzası ... != şimdiki ...` ya da betikte "imzası 20'li setinki değil": durum dosyası beklenen sete ait değil. **Dokunmayın**, çıktıyı bana yapıştırın (yedek zaten alındı).
- `20'li set kaydı beklenen 10 + 10 hesaptan oluşmuyor`: kayıtta fazla/eksik hesap var; motor bilerek durur. Çıktıyı yapıştırın.
- Canlı/kuru yürütücünün **ayrı** durum dizini varsa (strateji süzgeçli gölge paper durumu, ör. yalnız ewo + e0v1en): 20'li imzalı kayıt, yalnız süzülen hesaplar yeni 10'lu sette ise otomatik 10'lu imzaya geçer;
  aksi halde açık hatayla durur. Bu dizin bu betiğin kapsamında değildir; hata görürseniz çıktıyı bana yapıştırın.
- `paper v2 seti BAŞLAMAZ ...`: bir strateji paper'ın uygulamadığı çıkış ayarı taşıyor; bilerek durur. Çıktıyı yapıştırın.

## Geri dönüş (gerekirse; root kabuğunda)
**Hangi yedek?** 2. adımda aldığınız **`yedek_10_oncesi_<tarih>`** (20'li durum). Betiğin kendi aldığı `yedek_20li_betik_*` da 20'li durumdur ama **adım 2'dekini** kullanın.
Eski bir 10'lu yedek yoktur; 10'lu durumu geri yüklemeyin.
```bash
systemctl stop 1l3a-paper
cd /var/lib/1l3a-paper && mv durum durum_10luk_deneme && cp -a yedek_10_oncesi_<tarih> durum     # 2. adımdaki 20'li yedeği geri koy
cd /opt/1l3a && git checkout <2. adımda not ettiğiniz sürüm>
chown -R l3a:l3a /opt/1l3a
systemctl start 1l3a-paper
# sonra ileride tekrar güncellemek için dala dönün: git checkout <2. adımdaki dal adı>
```
**Dikkat:** geçişten geri dönüşe kadar paper'ın yaptığı sanal işlemler **kaybolur** (yedek geçiş anındaki durumdur). Eski kod 20'li yedeği sorunsuz yükler; 10'lu kayıt eski koda yüklenmez.
Durdurulan hesapların arşivi `durum_10luk_deneme` içinde kalır, silinmez.
