# 1L3A -> ML Otonom: özellik taşıma notları

**Amaç.** Bu belge, 1L3A (kripto/hisse/emtia kâğıt-trading botu) deposundaki seçili özelliklerin ML Otonom projesine taşınması için bir haritadır. Her bölüm: nerede, ne yapar, hangi veriyi alır/üretir, neye bağlı, hangi sabitler, hangi testler, kâğıtta çalışıyor mu, taşırken nelere dikkat. ML Otonom tarafı kendi kodunda karşılığını arayıp aynısını yazmaz; önce var olanı bulur, eksiği taşır.

**Kaynak commit:** `201a59b` (`git -C /home/user/1L3A-Proje rev-parse --short HEAD`). Satır sayıları bu commit'e göredir. Belge 2026-11-20 tarihlidir.

**Önemli not (kanıt düzeyi).** Kâr katkısı hiçbir özellik için ölçülmedi. Yalnız v2 araştırma hattı gerçek koşuda kullanıldı (holdout 2025-11-08 -> 2026-11-06 geçti: DURUM.md "yalnız gauss ve ewo ön kayıtlı holdout'u geçti"). Diğer özellikler (nabız, oto-güncelleme, karantina, mutabakat, risk kancaları, etiketler) "çalışıyor ve testli" düzeyindedir; "kazandırıyor" iddiası yoktur. Taşıyan kişi bunları risk/operasyon sigortası olarak değerlendirmeli, getiri artıran özellik olarak değil.

**Gizlilik kuralı (1L3A'ya özgü, taşımada önemli).** `stratejiler/paper_v2_seti.json` içinde `gorunur:false` işaretli kâğıt hesaplar vardır. Bu hesapların adı hiçbir çıktıda (Telegram, pano, günlük özet, mutabakat, log) yazılmaz; toplu "Diğer hesaplar" olarak görünür. Tek kaynak: `motor/canli/hesap_adlari.py`. Bu belgede hesap adı yoktur ve ML Otonom'a aktarılan örneklerde de olmamalıdır.

## Özet tablo

| # | Özellik | Ana dosya(lar) | Zorluk | Kâğıtta etkin |
|---|---|---|---|---|
| 1 | Sert risk limitleri + maliyetli boyutlandırma | `motor/risk/limitler.py`, `paper_motor.py` | Düşük (sabitler) / Orta (kancalar) | Evet |
| 2 | Araştırma istatistik araçları | `motor/arastirma/v2/{holdout,test,spa,maliyet}.py`, `pbo.py`, `evren_maliyet.py` | Orta-Yüksek (veri/sözleşme bağı) | Evet (v2 koşusu yapıldı) |
| 3 | Nabız + oto-güncelleme/geri al + disk bakımı | `nabiz.py`, `kalp_atisi.py`, `oto_guncelle.py`, `disk_bakim.py`, `deploy/*` | Orta (sunucu/systemd bağı) | Evet (kod+karar; sunucu aktifliği repodan doğrulanamaz) |
| 4 | Hata dayanıklılığı | `karantina.py`, `paper_veri.py`, `paper.py`, `paper_canli.py`, `sembol_izleme.py` | Orta | Evet |
| 5 | Borsa kuralları, kuru mod, canlı ayar, canlı kayıt | `borsa/{kurallar,kuru,canli_ayar,canli_kayit}.py` | Düşük-Orta | Yalnız canlı (kâğıtta yok) |
| 6 | Mutabakat + durum ilkesi + giriş izi | `araclar/islem_mutabakat.py`, `mutabakat_telegram.py`, `durum.py`, `paper_durum.py`, `giris_izi.py` | Orta (kavram taşınır) | Evet |
| 7 | Denetim/mutasyon yöntemi | `raporlar/denetim-1l3a.md`, `raporlar/denetim_testleri/` | Düşük (yöntem) | Evet (2026-11-20'de koşuldu) |
| a | Ders katmanı adaptörü | `ogrenme_adaptor.py`, `motor/ortak_ogrenme/ders.py` | Yüksek (ortak paket bağı) | Evet (bağlı; etkin ders yok) |
| b | Binance imzalı istemci | `borsa/binance_futures.py` | Düşük | Yalnız canlı |
| c | Kayıt etiketleri | `kayit_etiketleri.py`, `etiket_sonuc.py` | Düşük-Orta | Evet |
| d | Kill-switch / belirsiz emir mantığı | `borsa/canli_yurutucu.py` | Yüksek (fikir düzeyi) | Yalnız canlı |
| e | Telegram komutları + günlük özet | `telegram_komut.py`, `gunluk_ozet.py` | Orta | Evet |
| f | Canlı limitler | `borsa/canli_limitler.py` | Düşük (yapı) | Yalnız canlı |

Yol kısaltması: aksi belirtilmedikçe `motor/canli/...` ve `testler/...` depo köküne göredir.

---

## 1) Sert risk limitleri + maliyetli risk boyutlandırma

**Dosya(lar).** `motor/risk/limitler.py` (~46 satır, asıl sabitler 26-45, `maliyetli_risk_birim` 40-). Uygulandığı yerler: `motor/backtest/motor.py` (161 limitler, 346 miktar), `motor/portfoy/motor.py` (210, 434-442, 676), `motor/canli/paper_motor.py` (`_istenen_qty` 520-; toplam risk tavanı 678-690; kaldıraç tavanı ~691-700; `_acilis_limit_kontrol` ~866-895; bar kapanışı kill/günlük kayıp ~901-965), `motor/arastirma/secim.py::yeniden_oyna`.

**Ne yapar.** Dört sert sınır (işlem başı risk, günlük kayıp, kaldıraç, zirveden düşüş kill'i) ve portföy toplam stop riski tek bir donmuş dataclass'ta tutulur; strateji/ajan bunları aşamaz, aşan değer tavana kırpılır. "İşlem başı %1" maliyet dahil ölçülür: stopta toplam kayıp = fiyat riski + stop kayması + giriş/çıkış komisyonu; miktar buna göre hesaplanır.

**Giriş / çıkış.**
- `SertLimitler` (frozen dataclass), tekil örnek `SERT_LIMITLER`.
- `maliyetli_risk_birim(giris, stop, stop_kayma_oran, taker_oran)` -> `abs(giris-stop) + max(giris,stop)*(stop_kayma_oran + 2*taker_oran)`. Decimal veya float; oranlar kesir (0.0005 = %0.05). Miktar = `nakit*risk_oran / maliyetli_risk_birim(...)`.
- Paper motorunda: `_istenen_qty(kol, E, px, stop, w_abs, i) -> Decimal` = `min(qty_w, qty_r)`; sinyal kolunda `risk_oran`, ağırlık kolunda `top_risk` kullanılır. Toplam risk bütçesi: `min(top_risk*E*kol.grup_payi - acik_risk_kol_grubu, top_risk*E - acik_risk_hesap)`, `kisit = max(butce,0)/|px-stop|`; hedef miktar bunun altına kırpılır (olay `toplam_risk`), kırpma sonrası mevcut miktarın altındaysa `toplam_risk_tavani` reddi. Sonra kaldıraç/brüt tavan (`kaldirac`, `kaldirac_tavani`). Miktar her zaman `_step_asagi` ile aşağı yuvarlanır.
- Günlük kayıp / kill: `gunluk_pct = (E - gun_basi)/gun_basi*100 <= -gunluk_max_kayip_yuzde` -> `gunluk_blok=True` (o gün yeni giriş yok; açık pozisyon kapatma emri `gunluk_limit` nedeniyle verilir); `dusus = (zirve-E)/zirve*100 >= kill_switch_dusus_yuzde` -> `self.kill=True`, tüm kollarda hedef/giriş emri silinir, pozisyonlar `kill_switch` nedeniyle kapatılır. Olaylar `limit_olaylari` listesine `{"tur": "kill_switch"|"gunluk_kayip", "zaman", "ozsermaye", "dusus_yuzde", "mod", "evre"}` yazılır. Açılış boşluğu için ayrı kontrol (`_acilis_limit_kontrol`) girişlerden ÖNCE bayrak kurar.

**Bağımlılıklar.** İç: yalnız `dataclasses`; kancalar için `paper_motor.py` yapısı (Birim/Kol/Niyet, `_ozs`, `zirve`, `gun_basi`). Dış kütüphane yok (Decimal, stdlib). Ağ/dosya yok.

**Yapılandırma değerleri (aynen).**
```
islem_basi_max_risk_yuzde = 1.0     # özsermayenin %1'i, maliyet dahil
gunluk_max_kayip_yuzde    = 5.0     # UTC günü; kullanıcı kararı 2026-11-19 (önceden 3.0)
max_kaldirac              = 3.0     # nominal / özsermaye
kill_switch_dusus_yuzde   = 20.0    # zirveden
portfoy_toplam_risk_yuzde = 5.0     # hedef-ağırlık stratejilerinde toplam stop riski (karar 25, 2026-11-07)
```
Değişiklik kullanıcı kararıdır (dosya başlığında yazılı). Gün sınırı bilerek UTC; pano/rapor gün gruplaması TSİ (bölüm 6).

**İlgili testler.** `test_mutasyon_sert_limitler.py` (5), `test_maliyet_dahil_risk.py` (14), `test_paper_limit_denetim_2026_11_10.py` (15), `test_canli_islem_risk.py` (20), ayrıca `test_paper_motor.py`, `test_bt_motor.py`, `test_portfoy_motor.py` içinde limit senaryoları.

**Kâğıtta etkin mi.** Evet. Kanıt: `paper_motor.py:43` `from motor.risk.limitler import SERT_LIMITLER`, kullanım 869-965; DURUM.md "günlük %5 (canlı+paper)" ve "Sert risk limitleri ve kill eşikleri ... aynen kalır". Paper v2 10 hesapla 2026-11-10'dan beri koşuyor (DURUM.md:240).

**Taşımada dikkat.**
- Sayılar 1L3A'nın kullanıcı kararlarıdır; ML Otonom kendi risk iştahına göre yeniden kararlaştırmalı. Yapı (donmuş dataclass + "aşan tavana kırpılır" + tek kaynak) taşınır.
- `maliyetli_risk_birim` içindeki `max(giris, stop)` seçimi short için tutucu olsun diye bilinçli (çıkış maliyeti stop fiyatı üzerinden). Kopyalarken bu satırı "basitleştirmeyin".
- Kapsam dışı bırakılanlar belgeli: gap'li stop dolumu ve funding bu sınırı aşabilir.
- Paper motoru kancaları (kasa başına grup payı `kol.grup_payi`, `acik_risk_k`, v2'de her strateji ayrı sanal kasa) 1L3A mimarisine özgü; ML Otonom'da tek kasa varsa yalnız ilk iki fonksiyon + günlük/kill karşılaştırması yeterli.
- Gün başı (`gun_basi`) ve zirve (`zirve`) kalıcı durumda saklanmalı; yeniden başlatmada sıfırlanırsa kill/gün limiti kaybolur.

---

## 2) Araştırma istatistik araçları

### 2a) Holdout mührü
**Dosya.** `motor/arastirma/v2/holdout.py` (457 satır); sabitler `motor/arastirma/v2/sabit.py` (122 satır).
**Ne yapar.** Set aşaması sonunda strateji listesi, ayarlar, ölçek `s` ve tüm ilgili dosyaların/kodun sha256'sı "mühür" dosyasına yazılır. Holdout verisini okuyan TEK modüldür; mühür bir bayt bile uyuşmazsa `HoldoutHatasi` ile durur. Holdout bir kez koşulur: günlük kaydı veri okunmadan önce yazılır, ikinci deneme `HoldoutTekrarHatasi`.
**Giriş / çıkış.** `muhur_yaz(cikti: Path, havuz_yolu=None, ozet=None) -> dict`, `muhur_kontrol(cikti, havuz_yolu=None) -> dict`, `baslamis_mi`, `baslangic_isaretle`, `gunluge_yaz`, `holdout_asamasi(cikti=None, saglayici=None, havuz_yolu=None) -> dict`, `set_kapisi(net_set, p_set, hatalar=None) -> bool`, `budama(olcumler) -> tuple`, soyut `HoldoutSaglayici` (testlerde sentetik, gerçekte `GercekSaglayici` yalnız mühür+günlük sonrası kurulur). Mühür içeriği: `surum, zaman, sonuc, set[], s, s_tablo, dosyalar{ad: sha256}, maliyet_tablosu_v2_sha256, on_kayit_v2_sha256, git_commit, ortak_modul_hash, v2_modul_hash, strateji_hash, evren`. Çıktılar `sonuclar/evren/v2/` altına (set_muhru, günlük, holdout raporu).
**Kapı mantığı.** Set net getirisi > 0 VE havuzlanmış rastgele-giriş testi `p_set <= HOLDOUT_P_SET`; kapı geçerse budama: holdout neti <= 0 veya kendi K2 p'si > `HOLDOUT_BUDAMA_P` olan strateji çıkar, yerine yenisi alınmaz. Kapı kalırsa paper girdisi ÜRETİLMEZ.
**Bağımlılıklar.** İç: `evren_maliyet`, `secim`, `wf_evren`, `eleme`, `kasa`, `ham`, `maliyet`, `sabit`, v1 hash yardımcıları (`git_commit`, `ortak_modul_hashleri`, `evren_imzasi`). Dış: numpy, pandas, git (commit atalık kontrolü). Dosya: mühür/günlük JSON, ON_KAYIT_V2.md hash'i.
**Yapılandırma (sabit.py, aynen).** `HOLDOUT_BAS = 2025-11-08 UTC`, `TOHUM = 20261109`, `HOLDOUT_B_SET = 5000`, `HOLDOUT_B_STRATEJI = 2000`, `MUHUR_SURUM = 1`, `S_IZGARA = (1.0, 0.9, ..., 0.1)`, `ISLEM_RISK = 0.01`, `TOPLAM_RISK = 0.05`. `HOLDOUT_P_SET = 0.05`, `HOLDOUT_BUDAMA_P = 0.25` (ön kayıt metni ON_KAYIT_V2.md).
**Testler.** `test_v2_test_set_holdout.py` (57), `test_y4_muhur_v3.py` (7).
**Kâğıtta etkin mi.** Evet: gerçek koşu yapıldı, holdout 2025-11-08 -> 2026-11-06 geçti (DURUM.md, v2 bölümü; paper v2 başlangıcı 2026-11-10).
**Taşımada dikkat.** Kavram taşınır (ön kayıt + mühür + tek kullanım). Mührün doğrulattığı dosya listesi 1L3A'ya özgü (v1 ortak modül hash'leri, ON_KAYIT_V2.md, evren imzası); ML Otonom kendi "değişmemesi gereken" dosya kümesini tanımlamalı. Git atalık kontrolü deponun git geçmişine bağlıdır. Holdout dönemi bir kez harcandı; ML Otonom aynı tarihleri "temiz" saymamalı (kendi projesinde zaten görülmüşse yeni holdout gerekir).

### 2b) K2 rastgele-giriş p + Benjamini-Hochberg
**Dosya.** `motor/arastirma/v2/test.py` (551 satır); `motor/arastirma/evren_k2.py` (tek işlem simülasyonu `tek_islem_r`).
**Ne yapar.** Her gerçek işlem için enstrüman, yön, stop/ATR katı ve stratejinin kendi çıkış kuralları korunarak giriş mumu aynı UTC takvim çeyreği içinden tekdüze rastgele çekilir; sınama büyüklüğü T = toplam R. p = (1 + #{sim >= gerçek})/(B+1). İki aşama: B1 = 500, p <= 0.02 ise yeni tohumla B2 (1d/4h: 10000, 15m: 5000), nihai p yalnız 2. aşamadan. BH ile çoklu test düzeltmesi (m = havuz mührü).
**Giriş / çıkış.** `p_degeri(gercek, sim) -> float`; `bh_kesif(p: dict, m: int, q=BH_Q) -> {"k_yildiz","kesif","sira","esik"}` (eşitlikte anahtar alfabetik, eksik hipotez p=1 sayılır); `by_kesif` (Benjamini-Yekutieli, rapor); `ceyrek_sinirlari`, `cakisma_suz` (enstrüman başı çakışma süzgeci), `toplam_r`, `k2_simule(islemler, veri_al, cikis_al, n_sim, tohum, alt_sinir=None, kismi_dizin=None)`, `satir_test(row, cikti, tablo_yolu, tablo_hash, ...)`, `test_asamasi(cikti=None, surec=..., butce_sn=None, havuz_yolu=None, ...)`. Portföy için rastgele-ağırlık testi (`pf_k2_simule`, büyüklük günlük Sharpe). Satır tohumu `crc32(f"{strateji}|{tf}|{asama}") XOR TOHUM`. Kalıcılık: `test_kismi/*.npy`, `test_satir/*.json`; kesilirse kaldığı yerden sürer; çıktı `test.csv` + `test_ozet.json`.
**Bağımlılıklar.** İç: `evren_k2, evren_maliyet, saglamlik, wf_evren, eleme, ham, kasa, sabit`. Dış: numpy, pandas. Dosya: yoğun disk önbelleği, çok süreçli (`SUREC_VARSAYILAN = 4`).
**Yapılandırma.** `K2_B1=500`, `K2_B2={"1d":10000,"4h":10000,"15m":5000}`, `K2_GECIS_P=0.02`, `BH_Q=0.10`, `M_TABAN=939`, `K2_YENIDEN_CEKIM=10`, `PF_KAYIT_BLOK=25`.
**Testler.** `test_v2_test_set_holdout.py` (57, test+set+holdout birlikte), `test_v2_ham_eleme.py` (42), `test_evren_k2_esdeger.py` (7: hızlı sürüm naif döngüyle birebir).
**Kâğıtta etkin mi.** Evet (v2 koşusunda kullanıldı).
**Taşımada dikkat.** `p_degeri` + `bh_kesif` saf fonksiyonlar, doğrudan taşınır. Asıl rastgele-giriş simülasyonu 1L3A'nın motor/çıkış-modülü/çeyrek mantığına gömülü; ML Otonom'da "kendi işlem listesi + kendi çıkış kuralıyla giriş zamanını rastgeleleştir" olarak yeniden yazılmalı. "Test koşulmayan/hata/desteklenmeyen çıkış modüllü satır p=1" kuralı (reddedilemez) korunmalı.

### 2c) SPA (Hansen 2005) + durağan blok bootstrap
**Dosya.** `motor/arastirma/v2/spa.py` (64 satır).
**Ne yapar.** Havuzun bütününde "sıfırdan farklılık" var mı: studentize T = max(0, max_k sqrt(n)·d̄_k/ω̂_k); ω̂ durağan bootstrap'tan; üç null-ortalama (alt / tutarlı / üst), raporlanan p tutarlı olandır. YALNIZ RAPOR, kapı değil. Varyansı 0 olan satır dışlanır ve sayılır; serilerde olmayan günler 0 getiri.
**Giriş / çıkış.** `hansen_spa(seriler: dict[str, pd.Series], tohum: int, ort_blok=BOOT_BLOK_GUN, n_cekim=BOOT_CEKIM) -> {"p","p_alt","p_ust","T","n_gun","n_model","n_sabit","en_iyi"}`; `durgan_indeks(n, ort_blok, n_cekim, rng, parca=None)` indeks matrisi üreteci. Girdi: günlük getiri Series'leri (UTC gün indeksli).
**Bağımlılıklar.** numpy, pandas, `v2.sabit`.
**Yapılandırma.** `BOOT_BLOK_GUN = 20`, `BOOT_CEKIM = 2000`, `BOOT_PARCA = 250`, `SPA_RAPOR_ESIK_P = 0.10`, `SPA_RAPOR_METNI = "havuzun bütününde sıfırdan farklılık kanıtı yok"`.
**Testler.** Ayrı dosya yok; `test_v2_test_set_holdout.py` içinde kapsanır.
**Kâğıtta etkin mi.** Evet (v2 rapor adımı `spa_asamasi`).
**Taşımada dikkat.** Bağımsız, kolay taşınır; yalnız `sabit` importunu yerel sabitlerle değiştirin. Kıyas "sıfır" (d = günlük MTM getirisi); ML Otonom başka kıyas (ör. al-tut) isterse burada değişir.

### 2d) PBO (CSCV)
**Dosya.** `motor/arastirma/pbo.py` (102 satır).
**Ne yapar.** Bailey-López de Prado CSCV: T x N getiri matrisi `n_blok` ardışık bloğa bölünür, tüm C(S,S/2) (çoksa rastgele örnek) eğitim/sınama bölünmesinde IS'te en iyi Sharpe'lı sütunun OOS göreli sırası ve logit lambda hesaplanır; PBO = P(lambda <= 0).
**Giriş / çıkış.** `pbo_cscv(getiri: np.ndarray (T,N), n_blok=16, max_kombinasyon=20000, tohum=0, parca=500) -> {"pbo","n_aday","n_kombinasyon","T","n_blok","lambda_medyan","oos_ort_secilen","tam_enumerasyon"}`. `pbo=nan`: N<2 veya T<2*n_blok. Deterministik. Std'si 0 olan sütun atılır.
**Bağımlılıklar.** numpy, itertools, math. Hiç iç modül yok.
**Yapılandırma.** Varsayılanlar imzada (16 blok, 20000 kombinasyon, tohum 0).
**Testler.** `test_pbo.py` (7).
**Kâğıtta etkin mi.** Evet, v1 evren araştırma hattında (`wf_evren.py` aşama sırası ham -> wf -> pbo -> saglamlik -> secim -> holdout; stil x tf başına tüm aday, 16 blok); v2 kapılarında (`v2/test.py`, `v2/holdout.py`) PBO yok.
**Taşımada dikkat.** Tek dosya, bağımsız; doğrudan kopyalanır.

### 2e) Maliyet tablosu
**Dosya.** `motor/arastirma/evren_maliyet.py` (133), `motor/arastirma/v2/maliyet.py` (57). Tablo verisi `sonuclar/evren/maliyet_tablosu.csv` (+ `.sha256`) ve `sonuclar/evren/v2/maliyet_tablosu_v2.csv`.
**Ne yapar.** Enstrüman başına komisyon, spread+kayma, stop kayması, funding durumu, BSMV (BIST'e özgü komisyon vergisi) tek tabloda; koşulardan ÖNCE yazılıp sabitlenir, sha256'sı her çıktıya yazılır. Tabloda olmayan sembol açık hata verir (sessiz varsayılan yok). v2 tablosu = v1 + `funding_long_8s_oran`; hisse/emtia (DK_ sembolleri) için long işleme tutulan her 8 saat başına nominal x oran funding ödenir (takvim süresi), short'a gelir yazılmaz, maliyet çarpanı funding'i çarpmaz.
**Giriş / çıkış.** `tablo_hash(yol=None)`, `yukle(yol=None) -> DataFrame`, `satir(sembol)`, `sembol_maliyeti(sembol, carpan=1.0, yol=None) -> tuple`, `funding_long_8s_oran(sembol)`, `maliyet_ayarlari(sembol, kurallar, carpan=1.0, yol=None) -> MotorAyarlari`, `tabloyu_yaz`; v2: `tablo_yolu`, `v2_tablosu_uret`, `tabloyu_hazirla`, `funding_maliyeti_usd(yon, miktar, giris_fiyati, giris_zamani, cikis_zamani, oran_8s) -> np.ndarray`. Sütunlar: `sembol, sinif, komisyon_oran, spread_kayma_oran, stop_kayma_oran, funding, bsmv_oran, efektif_komisyon_oran (= komisyon*(1+bsmv)), tutucu, kaynak`.
**Bağımlılıklar.** İç: `motor.backtest.motor.MotorAyarlari` (dönüş tipi), `v2.sabit`. Dış: pandas, numpy, hashlib.
**Yapılandırma.** `FUNDING_LONG_8S_ORAN = 0.0001`, `FUNDING_PERIYOT_SAAT = 8.0`, `MALIYET_CARPANLARI = (1.0, 2.0)`, `TABLO_V2_AD = "maliyet_tablosu_v2.csv"`. Motor eşlemesi: `komisyon_taker_yuzde = efektif_komisyon*100`, `kayma_bps = spread_kayma*1e4`, `stop_kayma_bps = stop_kayma*1e4`.
**Testler.** `test_sag_dsr_maliyet_payi.py` (2), `test_b16_damga_kapsam.py`, `test_funding_sutunu.py`, `test_seans_maliyet.py`; maliyetli risk için bölüm 1 testleri.
**Kâğıtta etkin mi.** Evet (backtest/holdout maliyetleri bu tablodan; paper `maliyet.json` ayrı).
**Taşımada dikkat.** Tablo içeriği (BIST damga, TradFi funding, "tutucu" işaretleri) 1L3A evrenine özgü; yalnız yapı + "hash'le sabitle + eksik sembolde hata ver" ilkesi taşınır. `maliyet_ayarlari` doğrudan 1L3A backtest `MotorAyarlari`'na bağlı; ML Otonom kendi maliyet nesnesine eşlemeli.

### 2f) Lookahead testi
**Dosya.** `testler/test_lookahead_tum_stratejiler.py` (2 test fonksiyonu, parametreli).
**Ne yapar.** Kayıtlı her strateji için tam seri çıktısı, aynı serinin iki farklı noktada (0.45 ve 0.75) kesilmiş çıktısıyla karşılaştırılır; kesilen veride geçmiş değerler değişirse gelecek sızıntısı vardır. Veri iki modda üretilir: 7/24 (5 dk) ve seanslı (hafta içi, boşluklu).
**Giriş / çıkış.** `motor.portfoy.stratejiler.tum_portfoy_stratejileri`, `motor.strateji.kayit` üzerinden strateji listesi; çıktı pytest geçti/kaldı. Tohumlar `(17, 43)`, kesimler `(0.45, 0.75)`.
**Bağımlılıklar.** pytest, numpy, pandas; 1L3A strateji kayıt defteri.
**Testler.** Kendisi test; ayrıca aday stratejiler için kapı: `stratejiler/aday_paper_listesi.json`'a ekleme şartı "`kart_dogrula` + lookahead testi geçer" (DURUM.md:574).
**Kâğıtta etkin mi.** Evet (CI testleri içinde, her commit).
**Taşımada dikkat.** Fikir evrenseldir ("ileri kesip aynı geçmiş çıktıyı ver"). Kayıt defteri bağını ML Otonom'un strateji/özellik arayüzüne uyarlayın. ML modelleri için aynı sınama özellik üretimine uygulanmalı.

---

## 3) Nabız + oto-güncelleme/geri al + disk bakımı

### 3a) Dış nabız (dead-man)
**Dosya(lar).** `motor/canli/nabiz.py` (96), `motor/canli/kalp_atisi.py` (76), `deploy/nabiz_worker.js` (91, Cloudflare Worker), `deploy/nabiz_yayinla.sh` (62), `deploy/1l3a-nabiz.service` (19), `deploy/1l3a-nabiz.timer` (10), `deploy/1l3a-nabiz.env.ornek` (7).
**Ne yapar.** Sunucu 5 dakikada bir sağlık gövdesini sunucu DIŞINDAKİ bir Worker'a POST eder; Worker son nabzı KV'ye yazar, cron (*/10) son nabız çok eskiyse Telegram'a uyarı yollar ("sunucu sustu"). Böylece sunucunun kendisi ölse de alarm gelir. Kalp atışı: motor her turda en çok 60 sn'de bir `durum/kalp_atisi.json` yazar; yeniden başlatmada kesinti süresi bundan ölçülür.
**Giriş / çıkış.**
- `govde_uret(simdi: datetime, paper_aktif: bool, canli_aktif: bool, durum_dizin=DURUM_DIZIN) -> dict`: `{"proje":"1l3a","zaman":"...Z","durum":"iyi"|"paper_sorunlu","neden"?:str,"canli"?:"aktif"}`. "iyi" = paper servisi aktif VE kalp atışı <= 600 sn taze.
- `gonder(govde, url, anahtar, acici=None) -> bool`: POST `{url}/nabiz`, başlıklar `X-Nabiz-Anahtar`, `User-Agent: 1l3a-nabiz/1.0` (Cloudflare varsayılan Python UA'sını engelliyor), zaman aşımı 20 sn. Hata loglanır (URL/anahtar yazılmaz), `main` her durumda 0 döner.
- `servis_aktif_mi(ad)`: `systemctl is-active --quiet`.
- `kalp_atisi`: `yaz(dizin, zaman, baslangic, onceki=None, durdu=False)`, `oku(dizin)`, `kesinti(onceki, baslangic)`, `olay_mesaji(k)`; şema `1l3a.durum.kalp_atisi`.
- Worker: `POST /nabiz` (anahtar yoksa 401, fail-closed, sabit zamanlı karşılaştırma), diğer her şey 404.
**Bağımlılıklar.** Python stdlib + `kalp_atisi`; systemd; Cloudflare Workers + KV + wrangler (yayın betiği); Telegram Bot API (Worker'dan).
**Yapılandırma (aynen).** `BAYAT_SN = 600`, `DURUM_DIZIN = "/var/lib/1l3a-paper/durum"`, `KALP_SN = 60`; Worker `ESIK_DK = 20`, `TEKRAR_DK = 120` (aynı uyarı en çok 2 saatte bir), cron `*/10`; timer `OnBootSec=2min`, `OnUnitActiveSec=5min`, `Persistent=true`. Ortam: `NABIZ_URL`, `NABIZ_ANAHTAR` (>=32 karakter, `openssl rand -hex 32`), `NABIZ_AD` (varsayılan `1l3a-nabiz`), `NABIZ_DURUM_DIZIN`, `NABIZ_EV`; yayın betiği için `CLOUDFLARE_API_TOKEN`, `CLOUDFLARE_ACCOUNT_ID`, `TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_ID`. Servis kullanıcısı `l3a`, `NoNewPrivileges`, `ProtectSystem=full`.
**Testler.** `test_nabiz.py` (16), `test_pano_worker.py` (Worker benzeri).
**Kâğıtta etkin mi.** Evet (kod + kullanıcı kararı 2026-11-19, DURUM.md:22; sunucu zamanlayıcısının aktifliği depodan doğrulanamaz).
**Taşımada dikkat.** Sırlar yalnız `/etc/1l3a-*.env` içinde (chmod 600), repoya girmez; Cloudflare token'ı nabız servisinden ayrı tutulur (ayrı env dosyası). Hesaplar/Telegram bağı 1L3A'ya özgü; `govde_uret` içindeki "paper servisi + kalp atışı" ölçütü ML Otonom'un kendi ana servis/döngüsüne uyarlanmalı. Cloudflare hesabı ML Otonom'da yoksa Worker yerine başka bir dış izleyici (healthchecks benzeri) aynı sözleşmeyle konabilir.

### 3b) Oto-güncelleme + geri al
**Dosya(lar).** `motor/canli/oto_guncelle.py` (400), `deploy/1l3a-guncelle.service` (18), `deploy/1l3a-guncelle.timer` (11), `deploy/1l3a-guncelle-istek.path` (10), `deploy/1l3a-guncelle-istek.service` (15), `deploy/oto_guncelle_kur.sh` (23).
**Ne yapar.** Sunucu saatte bir izlenen daldaki yeni commit'i kendisi kurar, yalnız ileri sarma: `git fetch` -> uzak uç yerelin torunu değilse KURMAZ -> GitHub'da "testler" iş akışı check-run'ı success değilse kurmaz -> `git merge --ff-only` -> requirements değiştiyse pip -> duman testi (import) -> değişen systemd birimlerini kopyala + daemon-reload -> aktif servisleri yeniden başlat -> 60 sn sonra hepsi `active` değilse geri al + CRIT. Geri alma: `--geri-al` veya Telegram `/geri_al` iki adımlı onaydan sonra `GERI_AL` istek dosyası (kullanıcı `l3a` root işini yapamadığı için dosya yazar; root `.path` birimi uygular ve siler). Geri alınan sha bir daha kurulmaz.
**Giriş / çıkış.** `Ayar` dataclass (alanlar `kok, dal, durum, geri_al_dosya, systemd, python, bekleme, servisler`), `Guncelleyici` sınıfı, `guncelleme_cumlesi(baslik) -> str` (commit başlığından Türkçe Telegram cümlesi), `main(argv=None) -> int`. Tüm dış etkiler (komut, ağ, telegram, uyku) enjekte edilebilir. Kayıt: `/var/lib/1l3a-guncelle/gecmis.jsonl` + `son_iyi_sha`; kilit `fcntl`.
**Bağımlılıklar.** stdlib + `telegram.gonder` (bildirim); git, systemd, pip, GitHub genel REST API (check-run okuma).
**Yapılandırma (aynen).** `REPO = "sselimgenc-oss/1L3A-Proje"`, `CI_ISIMLERI = ("testler","pytest")`, `SERVISLER = ("1l3a-paper","1l3a-ct-paper","1l3a-aday-paper","1l3a-telegram","1l3a-canli")`, `OTOMATIK_KURULACAK = ["1l3a-aday-paper.service"]`, `SYSTEMD = "/etc/systemd/system"`, `DUMAN = "import motor.canli.paper, motor.canli.telegram_komut, motor.canli.ct_paper, motor.canli.aday_paper, motor.canli.nabiz, motor.canli.borsa.calistir"`, `BEKLEME_SN = 60`, `MAKS_MESAJ = 3500`, `CUMLE_MAKS = 100`. Ortam: `L3A_GUNCELLE_KOK` (varsayılan `/opt/1l3a`), `L3A_GUNCELLE_DAL`, `L3A_GUNCELLE_DIZIN` (`/var/lib/1l3a-guncelle`), `L3A_GERI_AL_DOSYA` (`/var/lib/1l3a-paper/durum/GERI_AL`). Timer: `OnBootSec=10min`, `OnUnitActiveSec=1h`, `RandomizedDelaySec=5min`, `Persistent=true`. Servis `TimeoutStartSec=1800`, `User=root`, `StateDirectoryMode=0755`.
**Testler.** `test_oto_guncelle.py` (20; sahte komut/ağ ile).
**Kâğıtta etkin mi.** Evet (kullanıcı kararı 2026-11-19, DURUM.md:25; `/durum` "kod: <sha>" satırı gösterir; sunucu aktifliği repodan doğrulanamaz).
**Taşımada dikkat.** En büyük 1L3A-özgü bağlar: depo adı, CI iş akışı/iş adı, servis adları, yol düzeni (`/opt/1l3a`, kullanıcı `l3a`), duman testi import listesi, "`1l3a-aday-paper` otomatik kurulur" listesi. İlke taşınır: yalnız ileri sarma + CI yeşil şartı + duman testi + sağlık kontrolü + geri alma + "geri alınan sha tekrar denenmez". Root ile otomatik kod çalıştırmak güvenlik kararıdır; ML Otonom'da bunu açıkça onaylayın. GitHub check-run sorgusu yalnız genel depo ile anahtarsız çalışır; özel depoda token gerekir.

### 3c) Disk bakımı
**Dosya.** `motor/canli/disk_bakim.py` (248).
**Ne yapar.** Komut servisi ana döngüsünden 5 dakikada bir çağrılır: kök (`/`) ve durum kökü için disk doluluk yüzdesi (df Use% formülü); %80'de WARN, %90'da CRIT ("kayıtlar duracak") Telegram; aynı uyarı en çok 6 saatte bir; eşik altına inince tek "Disk düzeldi". Günde bir kez kayıt döndürme: kök altındaki `*.jsonl`/`*.log` dosyalarından 50 MB'ı aşanlar tarih damgalı `.gz` olarak `arsiv/`'e kopyalanır, asıl dosya boşaltılır (copytruncate), 90 günden eski `arsiv/*.gz` silinir. `calistir` asla istisna fırlatmaz.
**Giriş / çıkış.** `kullanim_yuzdesi(yol, disk_usage) -> Optional[float]`, `olc(yollar, disk_usage) -> dict`, `satir() -> str` (/durum için), `degerlendir(pct, alarm_acik, ortak: tg.OrtakDurum, gonder, simdi) -> bool`, `arsivle(yol, arsiv, simdi) -> Path`, `dondur(kok, simdi, sinir) -> dict`, `calistir(kok=KOK_DIZIN, simdi=None, ortak=None, ...)`. Durum dosyası `disk_bakim.json` (jsonl değil, döndürme kapsamı dışında).
**Bağımlılıklar.** stdlib (`shutil`, `gzip`); iç: `telegram` (OrtakDurum, gonder).
**Yapılandırma (aynen).** `KOK_DIZIN="/var/lib/1l3a-paper"`, `OLCULEN_YOLLAR=("/", KOK_DIZIN)`, `TEKRAR_SN=21600`, `DONDURME_ARALIK_SN=86400`, `DOSYA_SINIR_BAYT=50*1024*1024`, `ARSIV_SAKLAMA_GUN=90`, `ARSIV_DIZIN="arsiv"`, `KAYIT_UZANTILARI=(".jsonl",".log")`, `KORUNAN_DIZINLER=("sonuclar","arsiv")`, `KORUNAN_IZLER=("ON_KAYIT","butunluk","kilit")`. Eşikler %80/%90. Ortam `L3A_DISK_KOK`; komut servisinde `DISK_ARALIK_SN=300`.
**Testler.** `test_disk_bakim.py` (20).
**Kâğıtta etkin mi.** Evet (komut servisinden çağrılıyor: `telegram_komut._disk_tick`, ~satır 491).
**Taşımada dikkat.** "Mühürlü/ön kayıt dosyalarına dokunma" listesi 1L3A'ya özgü; ML Otonom'da model/özellik arşivlerini ve denetim kayıtlarını bu koruma listesine ekleyin. Copytruncate'in milisaniyelik satır kaybı penceresi vardır (yazıcılar "a" kipinde açıyorsa boşluk oluşmaz). Silme yalnız `arsiv/*.gz` içindir; bunu değiştirmeyin.

---

## 4) Hata dayanıklılığı

### 4a) Hata sınıflandırması
**Dosya.** `motor/canli/paper_veri.py` (336; 49-71).
**Ne yapar.** Programlama hatası ile geçici ağ/veri hatasını ayırır: kod hatası "geçici" diye gizlenmez, ağ hatası da stratejiyi suçlamaz.
**Giriş / çıkış.** `BinanceHata(Exception)`; `KOD_HATALARI = (TypeError, AttributeError, KeyError, IndexError, NameError, ImportError, AssertionError, NotImplementedError, ZeroDivisionError, ArithmeticError)`; `GECICI_HATALAR = (BinanceHata, OSError, json.JSONDecodeError, UnicodeError)`; `STRATEJI_HATALARI = KOD_HATALARI + (ValueError,)`; `kod_hatasi_mi(e) -> bool` (kod hatası ve geçici değil); `strateji_hatasi_mi(e) -> bool` (STRATEJI_HATALARI ve geçici değil). Kural: strateji KARAR kodunda ValueError de kod hatasıdır (kullanıcı kararı 2026-11-20); veri çekme ve `sonsuz_dene` yolunda ValueError geçici kalır.
**Testler.** `test_paper_veri.py` (19), `test_canli_sertlestirme.py` (15), `test_denetim_sinir.py`.
**Kâğıtta etkin mi.** Evet.
**Taşımada dikkat.** `BinanceHata` borsaya özgü; ML Otonom kendi veri kaynağı istisnasını `GECICI_HATALAR`'a koymalı. JSON/Unicode hataları ValueError alt sınıfı olduğundan sıralama (geçici önce kontrol) kritik. 2026-11-20 denetiminde `ZeroDivisionError`'ın kod hatası sayılmaması D2 bulgusuydu; bu sürümde eklenmiştir.

### 4b) Karantina
**Dosya.** `motor/canli/karantina.py` (63, yardımcılar); mantık `motor/canli/paper.py` (`_karar_guvenli`, `_karantinaya_al_ya_da_yukselt`, `_karantinaya_al`, `_karantina_duzeldi`, `karantina_kaldir`, ~148-200) ve `motor/canli/paper_motor.py` (`karantina` kümesi 143, giriş reddi 267-268 ve 294-295, gün sonu 905-912, `_karantina_yonet` 978).
**Ne yapar.** Bir stratejinin karar kodu programlama hatası verirse yalnız o strateji karantinaya girer; tur düşmez. Karantinada strateji kodu çağrılmaz, yeni giriş yok (bekleyen giriş emirleri silinir), açık pozisyon motorun stop/hedef/zaman/kill/günlük limit yönetimiyle sürer. Kod SHA'sı değişince (oto-güncelleme) bir kez yeniden denenir; ilk başarılı karardan sonra kayıt silinir ve "düzeldi" bildirilir. Elle kaldırma Telegram `/karantina_kaldir <strateji>` (iki adımlı).
**Giriş / çıkış.** Kalıcı kayıt `Paper.karantina[kimlik] = {"zaman","sha","hata","durum":"aktif"|"deneme"}` (`paper_state.json` içinde); `karantina_bildirim[kimlik]` son CRIT zamanı. İstek dosyası `KARANTINA_KALDIR` (ack `karantina_kaldir_islendi.json`). Yardımcılar: `kod_sha() -> Optional[str]`, `istek_dosyasi(durdur_dizini, env=None) -> Path`, `satir(ozet) -> Optional[str]`, `hedef_eslesir(hedef, kimlik, gorunur) -> bool`.
**Bağımlılıklar.** stdlib (`subprocess` ile git sha); iç: paper/paper_motor, `paper_veri.strateji_hatasi_mi`, Telegram bildirimi.
**Yapılandırma.** `BILDIRIM_ARALIK_SN = 21600` (aynı strateji için 6 saatte bir), `ISTEK_AD = "KARANTINA_KALDIR"`, `ISTEK_ACK = "karantina_kaldir_islendi.json"`, `GIZLI_AD = "Diğer hesaplar"`. Mesaj: "<ad> stratejisi hata verdi, yeni işlem açmıyor; açık pozisyonlar stop/hedefle sürüyor".
**Testler.** `test_karantina.py` (16), `test_denetim_karantina.py` (17). Mutasyon öldürme oranı %46,8 (zayıf; bölüm 7'ye bakın: gizli/görünür kaldırma koşulu testlenmemişti).
**Kâğıtta etkin mi.** Evet.
**Taşımada dikkat.** Gizli hesap kısıtı: karantina mesajında gizli hesabın adı asla yazılmaz (`kq.GIZLI_AD`); `/karantina_kaldir hepsi/gizli` hedefleri bu yüzden var. Denetim şüphesi: canlı serviste `telegram_sessiz=True` ise karantina CRIT'i gitmeyebilir. Kimlik = strateji (birim) adı; ML Otonom'da "model/strateji kimliği" ile eşleyin. Gün içi (gsk) stratejilerin gün sonu kapanışı karantinada da korunur (D3).

### 4c) `sonsuz_dene` ve `TurKoruyucu`
**Dosya.** `motor/canli/paper.py` (1352): `sonsuz_dene` 674-, `TurKoruyucu` 1011-, sabitler 671 ve 1008.
**Ne yapar.** `sonsuz_dene(fn, ad, uyku, kalici, bildir, ilk_bekle=10, en_cok_bekle=300, uyari_aralik_sn=1800, saat, kod_hatasi_siniri)`: geçici hatada sınırsız yeniden dener (ilk 10 sn, ikiye katlanır, en çok 300 sn) ki servis çıkıp systemd StartLimit'e takılmasın; `kalici(e)` True ise yükselir; programlama hatası geçici sayılmaz: traceback'li loglanır, hemen bildirilir, AYNI hata TÜRÜ art arda `KOD_HATASI_SINIRI` kez olursa yükselir. `TurKoruyucu(p, geri_yukle, kalici_yaz=None, sinir=HATA_TEKRAR_SINIRI, binance_hata=None).calistir(tur_fn) -> bool`: servis turunu sarar; `BinanceHata` geçici (olay + log, tekrar); diğer her istisna: bellekteki durum son tutarlı kayda geri döner (yarım işlenmiş satır iki kez uygulanmasın), olay + Telegram; aynı hata art arda `sinir` kez olursa kontrollü durur (`calistir` False, `cikis_kodu=1`, systemd yeniden başlatır). Geri yükleme de başarısızsa hemen durur. Mesajlar `maskele` ile token'dan arındırılır.
**Yapılandırma.** `KOD_HATASI_SINIRI = 5`, `HATA_TEKRAR_SINIRI = 5`.
**Bağımlılıklar.** iç: `paper_veri`, `telegram.maskele`, paper durum kaydı; stdlib.
**Testler.** `test_canli_sertlestirme.py` (15), `test_paper_denetim.py`, `test_paper_v2_butunluk.py`.
**Kâğıtta etkin mi.** Evet.
**Taşımada dikkat.** "Son tutarlı kayda geri dön" paper durumunun anlık görüntü/geri yükleme yeteneğine bağlı; ML Otonom'da turun yan etkileri (dosya/pozisyon) kısmi uygulanıyorsa aynı idempotans düşünülmeli. Bilinen açık: D6 başlangıç yeniden deneme sayacı mesajı değişen hatada sonsuz döngüye girebiliyordu (kısmen düzeltildi: tür bazlı sayaç).

### 4d) Binance 429/418 yasak yönetimi
**Dosya.** `motor/canli/paper_veri.py` `FapiIstemci` (73-148: `__init__` 74, `_yasak_koy` 90, `_agirlik_bekle` 95, `get` 105); ortak yasak deposu `motor/canli/borsa/binance_futures.py` (`yasak_yukle/yasak_ayarla/yasak_oku/yasak_sifirla` 55-90, `_retry_after` 104).
**Ne yapar.** Yanıt başlığı `X-MBX-USED-WEIGHT-1M` izlenir; %75'i aşılırsa dakika sonuna kadar beklenir. 429: `Retry-After` okunur, yasak işaretlenir ve istek İÇİNDE uyunmaz (hata yükselir, bu süre istek gitmez). 418 (IP yasağı): yasak işaretlenir, otomatik tekrar YOK. 451 (konum kısıtı) açık hata. 5xx/ağ hatası üstel geri çekilmeyle (en çok 60 sn) `max_deneme` kez denenir. Yasak (host bazlı epoch) süreçler arası `yasak.json` dosyasıyla paylaşılır (gerçek saatli örnek paylaşır; sahte saatli test örneği paylaşmaz).
**Yapılandırma.** `AGIRLIK_ESIGI = 1800`, `ISTEK_ZAMAN_ASIMI = 20`, varsayılan `max_deneme = 5`, 429 varsayılan bekleme 60 sn, 418 varsayılan 300 sn; `FAPI = "https://fapi.binance.com"`.
**Testler.** `test_paper_veri.py` (19), `test_canli_borsa.py` (72).
**Kâğıtta etkin mi.** Evet.
**Taşımada dikkat.** Binance'e özgü ağırlık başlığı ve sınır; başka borsada uyarlanır. Paylaşılan yasak dosyası ilkesi (aynı IP'den çalışan tüm servisler birbirini yasağa sokmasın) taşınır. Süreç-özel yasak dosyası denetimde şüphe olarak not edildi.

### 4e) Veri hatası izolasyonu ("izole seri" kuralı)
**Dosya.** `motor/canli/paper_canli.py` (282): `CanliKaynak.guncelle` 146-, `_veri_hatasi` 204.
**Ne yapar.** Bir serinin/sembolün geçici veri hatası (ağ, 5xx, ayrıştırma) diğer serileri ENGELLEMEZ: hata loglanır, olay yazılır (seri başına en çok saatte bir), diğer seriler sürer, hatalı seri sonraki turda yeniden denenir; satır bekleme süresi (`BIRIM_BEKLEME_SN`) dolunca mumsuz işlenir. "İzole seri kuralı": bu turda DENENEN tüm seriler hatalıysa (genel kesinti) ilk hata yükselir (TurKoruyucu devralır); yalnız önceden izole bilinen seriler hatalıysa kesinti sayılmaz. Programlama hataları izole EDİLMEZ, yükselir. Funding çekimi 30 dakikada bir, hatalı sembol atlanır.
**Yapılandırma.** `WS_YENIDEN_SN = 23*3600`, `WS_SESSIZ_SN = 180`, `YOKLAMA_SN = 30`, `SEANS_KONTROL_SN = 300`, `GRACE_SN = 3`, `BIRIM_BEKLEME_SN = 900`.
**Testler.** `test_veri_hata_izolasyonu.py` (5), `test_paper_canli.py` (4).
**Kâğıtta etkin mi.** Evet.
**Taşımada dikkat.** Denetim notu D7: "genel kesinti" paydası, sırası gelmeyen/atlanan serileri de saymıyor (hatalar loglanıyor, kısmen düzeltildi). Seanslı (hisse/emtia) serilerde 300 sn yoklama ve takvim bağı 1L3A'ya özgü. REST her zaman doğru, WS yalnız tetikleyici ilkesi (kapanmış mum REST'ten okunur, uyuşmazlık olay yazılır) taşınmaya değer.

### 4f) Sembol izleme
**Dosya.** `motor/canli/sembol_izleme.py` (134).
**Ne yapar.** Saatte bir Binance `exchangeInfo` okunur (anahtarsız). Bir strateji sembolü TRADING dışına düşerse (SETTLING, BREAK, delist): o sembolde YENİ giriş açılmaz (`PaperMotor.engelli_semboller` + bekleyen giriş emirleri silinir), açık pozisyona dokunulmaz (zorla kapatma yok); açık pozisyon yoksa WARN, varsa CRIT; yeniden TRADING olunca bir INFO ve giriş açılır. exchangeInfo hatası sessizce sonraki saate kalır.
**Giriş / çıkış.** `SembolIzleyici(p, ist, semboller, bld=None, gonder=None, sessiz=False)` (`kontrol(simdi) -> bool`, `uygula_durum(tradingde, simdi)`, `uygula()`), `kur(p, ist, semboller, bld=None, sessiz=False)`, `acik_pozisyon_var(p, sembol)`. Yardımcı `_motorlar(p)` çok hesaplı (`p.hesaplar`) ve tek motorlu yapıyı destekler.
**Yapılandırma.** `ARALIK = pd.Timedelta(hours=1)`.
**Bağımlılıklar.** iç: `paper_veri` (FapiIstemci), paper motoru kancaları; pandas.
**Testler.** `test_sembol_izleme.py` (8).
**Kâğıtta etkin mi.** Evet (ct_paper/aday_paper de `paper.canli_calistir` üzerinden alır).
**Taşımada dikkat.** Gizli hesap adı mesajlarda yok (yalnız sembol yazılır). "Evrenden düşürme" başlangıç mantığı (`paper._tanimlara_veri_yok_isle`) ayrı; ikisi birlikte düşünülmeli. TradFi sembol eşleme (`ESLEME`, `esleme_dogrula`, `TRADIFI_PERPETUAL`) paper_veri'dedir ve hisse/emtia özel durumudur; ML Otonom yalnız kripto ise taşımayın.

---

## 5) Borsa kuralları, kuru mod, canlı ayar, canlı kayıt

### 5a) Borsa kuralları
**Dosya.** `motor/canli/borsa/kurallar.py` (116).
**Ne yapar.** `exchangeInfo`'dan tek sembol kuralı çıkarır ve emir miktarını borsa filtrelerine uydurur. KURAL: miktar HER ZAMAN aşağı yuvarlanır; minimumun altında kalırsa YUKARI YUVARLANMAZ (kayıp sınırı aşılırdı), işlem atlanır (`min_tutar_alti`). Nihai emir, yuvarlanmış miktar ve güncel kasayla yeniden doğrulanır. Koruyucu stop tick'e girişe DOĞRU (sıkı) yuvarlanır (long yukarı, short aşağı; risk artmaz), hedef kolay dolum yönüne.
**Giriş / çıkış.** `SembolKurali` (frozen: `sembol, tick, step, min_qty, max_qty, market_step, market_min, market_max, min_notional`, hepsi Decimal); `kural_cikar(bilgi: dict, sembol) -> SembolKurali` (eksik/bozuk filtre veya TRADING dışı = `KuralHatasi`, tahmin yok; MIN_NOTIONAL yoksa "varsayılan 5 tahmin edilmez"); `asagi(x, adim)`, `yukari(x, adim)`, `miktar_yuvarla(qty, k)` (MARKET_LOT_SIZE adımına aşağı + üst sınıra kırp), `stop_yuvarla(stop, yon, k)`, `hedef_yuvarla(hedef, yon, k)`; `Boyut` (`qty, neden, ayrinti, risk_yuzde, brut_kat, kaldirac, baglayan`); `boyutlandir(*, ozsermaye, tahsis, yon, giris, stop, kural, stop_kayma, taker, diger_brut=0, diger_stop_riski=0, kaldirac_ust=None, limitler=CANLI_LIMITLER, islem_risk=None, strateji_kaldirac=None) -> Boyut`; kasa = `min(özsermaye, tahsis)`.
**Bağımlılıklar.** stdlib Decimal; iç: `canli_limitler` (`miktar_hesapla`, `limit_ihlalleri`, `birim_maliyet`).
**Yapılandırma.** Sayı yok (sayılar `canli_limitler.py`'de, bölüm f). Kâğıt tarafında aynı kural `paper_motor._step_asagi`, `min_qty[s]` ile uygulanır; `paper_veri.kurallar_cikar(bilgi)` kâğıt için kural üretir.
**Testler.** `test_canli_borsa.py` (72), `test_canli_limitler.py` (28), `test_canli_denetim2.py` (25).
**Kâğıtta etkin mi.** Yalnız canlı (canlı yürütücü kullanır); kâğıtta eşdeğeri `paper_motor` içinde aşağı yuvarlama + `min_qty` ile etkin.
**Taşımada dikkat.** Decimal kullanımı bilinçli (float yuvarlama hatası emir reddettirir). `market_step` ve `min_notional` filtre adları Binance USDⓈ-M'e göredir.

### 5b) Kuru mod
**Dosya.** `motor/canli/borsa/kuru.py` (84).
**Ne yapar.** `KuruBorsa(mark_fn, tahsis)`: gerçek `BinanceFutures` ile AYNI arayüzü bellekte taklit eder, hiçbir şey borsaya gitmez; emirler loglanır; dolum = verilen mark fiyat. Anahtar/imzalı uç gerekmez.
**Giriş / çıkış.** Metotlar: `mark_fiyat, bakiye, pozisyonlar, emirler, hazirla, piyasa(sembol, yon, miktar, client_id, reduce_only=False), kosullu(sembol, tur, yon, miktar, tetik, client_id, working_type="MARK_PRICE"), sorgula, iptal, hepsini_iptal`; durum alanları `poz`, `acik`, `gonderilen`, `cuzdan`.
**Bağımlılıklar.** `binance_futures.BorsaHata`; stdlib.
**Testler.** `test_canli_borsa.py` içinde.
**Kâğıtta etkin mi.** Hayır (canlı yürütücü modu; canlı servis kurulu değil, DURUM/denetim: "Canlı servis kurulu/aktif değil").
**Taşımada dikkat.** Değer burada "arayüz aynı, davranış sahte" kalıbında; ML Otonom'un borsa arayüzü farklıysa yalnız kalıp alınır.

### 5c) Canlı ayar
**Dosya.** `motor/canli/borsa/canli_ayar.py` (173); örnek `stratejiler/canli_ayar.ornek.json`; env örneği `deploy/1l3a-canli.env.ornek`.
**Ne yapar.** Canlı yürütme yapılandırması. Anahtarlar DOSYADA yoktur, yalnız ortam değişkeni ADLARI yazılır. Mod: `kuru | testnet | canli` (varsayılan `testnet`); `canli` için ayrıca ortamda `CANLI_ONAY=evet` şart, yoksa `CanliOnayHatasi` ve başlamaz. Strateji başına `islem_risk` YALNIZ {0.005, 0.01, 0.015} (Decimal tam eşleşme; yoksa 0.015; 0.0150001, NaN, >0.015, sayı olmayan reddedilir). Strateji başına `kaldirac` YALNIZ int {3,4,5} (yoksa 3; 2, 6, "5", 5.0, True, None reddedilir). `kapanis_canli_onay` listesi: kapanış-aday etiketli strateji gerçek parayla yalnız burada kimliğiyle listeliyse başlar. Bir Binance hesabı (anahtar çifti) = bir strateji; aynı anahtar adı veya aynı anahtar DEĞERİ (sha256 özetiyle karşılaştırılır, değer loglanmaz) iki stratejide kullanılamaz.
**Giriş / çıkış.** `yukle(yol=None, env=None) -> CanliAyar` (yol: argüman, `CANLI_AYAR` env, ya da `stratejiler/canli_ayar.json`), `coz(h: dict, env: dict) -> CanliAyar`, `anahtarlar(s: StratejiAyar, env=None) -> (anahtar, gizli)`; `StratejiAyar(id, api_key_env, api_secret_env, tahsis_usd, islem_risk, kaldirac)`; hatalar `CanliAyarHatasi(ValueError)`, `CanliOnayHatasi`. JSON alanları: `mod`, `stratejiler[] {id, api_key_env, api_secret_env, tahsis_usd, islem_risk?, kaldirac?}`, `kapanis_canli_onay[] {id, tarih, onay:"evet"}`.
**Yapılandırma (aynen).** `MODLAR=("kuru","testnet","canli")`, `ONAY_ENV, ONAY_DEGER = "CANLI_ONAY", "evet"`, `IZINLI_ISLEM_RISK_KUMESI = (0.005, 0.01, 0.015)`, `IZINLI_ISLEM_RISK = 0.015`, `IZINLI_KALDIRACLAR = (3,4,5)`, `VARSAYILAN_KALDIRAC = 3`. Env adları: `CANLI_AYAR`, `CANLI_ONAY`, `BINANCE_API_KEY_S1/BINANCE_API_SECRET_S1` (örnekteki adlar; asıl adlar ayar dosyasındaki `api_key_env/api_secret_env`), `TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_ID`, `L3A_SIFIRDAN_IZIN` (bilerek sıfırdan başlatma izni: durum dosyası yokken dizinde başka kayıt varsa yürütücü başlamaz; format "id1,id2,hesap"). Dosya modu: `/etc/1l3a-canli.env` root, chmod 600.
**Testler.** `test_canli_borsa.py` (72), `test_canli_denetim2.py` (25), `test_dis_ayarlari.py`.
**Kâğıtta etkin mi.** Yalnız canlı.
**Taşımada dikkat.** "Küçük izinli küme + tam eşleşme + onay ortam değişkeni + bir hesap bir strateji" ilkesi taşınmaya değer. Değerler (0.5-1.5% risk, 3-5x) 1L3A kullanıcı kararıdır ve 5x test edilmiş sınırın dışında olduğu açıkça uyarılmıştır (backtestler brüt 3x). API anahtarında çekim KAPALI + IP kısıtı AÇIK olmalı (canlı modda `apiRestrictions` kontrolü için api.binance.com erişimi gerekir).

### 5d) Canlı kayıt
**Dosya.** `motor/canli/borsa/canli_kayit.py` (198).
**Ne yapar.** Canlı yürütücünün denetim kayıtları; YALNIZ kayıt, işlem mantığına dokunmaz. Hepsi append-only, durum dizini altında `canli/`, satır başına bir JSON, her satır fsync'lenir: `islemler.jsonl` (gerçek kapanan her pozisyon için bir satır), `ozsermaye_gunluk.jsonl` (servis başlangıcı + her UTC günü strateji başına özsermaye/tahsis/kasa/açık K/Z; tahsis değişimi ayrı `sermaye_hareketi` satırı ki 60 -> 250 geçişi kâr sayılmasın; hesap toplamı + ortak zirve `hesap` satırı), `olaylar_arsiv.jsonl` (yürütücünün her olayı).
**Giriş / çıkış.** `satir_ekle(yol: Path, satir: dict) -> None` (`O_APPEND` + flush + `os.fsync`; önceki yarım yazımın kesik son satırı yeni satırı bozmasın diye gerekirse başa `\n` ekler; hata YÜKSELİR, sessiz yutulmaz), `kapat_nedeni_cikar(mesaj)`, `cikis_sinifla(kapat_neden, cikis_fiyat, stop, hedef) -> tuple`, `yasam_dongusu(fills, yon, giris_emir_id, t0_ms)`, `islem_satiri(kay, fills, fills_neden, funding, funding_neden, ...)`, `HesapKaydi.yaz(h, simdi)`. `islemler.jsonl` şeması `1l3a.canli.islem` (alanlar: `sema, surum, zaman, strateji, kol, sembol, yon, giris_zamani, cikis_zamani, giris_fiyati, cikis_fiyati (VWAP, metin), miktar, stop_giris, stop_mesafesi_oran, planlanan_risk_usd, komisyon_usd, funding_usd, brut_pnl_usd, net_pnl_usd, r (= net/planlanan risk), cikis_nedeni (stop|hedef|strateji|kill|sistem|bilinmiyor), cikis_ayrinti, niyet_id, sinyal_zamani, model_maliyet_bps, gercek_maliyet_bps, giris_kayma_bps, cikis_kayma_bps, kismi_cikis_sayisi, notlar[]`). Bir pozisyonun yaşam döngüsü (sıfırdan sıfıra) TEK satırdır. Komisyon/funding alınamazsa `null` + `*_neden` alanı, `net_funding_dahil=false`.
**Yapılandırma.** `SEMA_ISLEM="1l3a.canli.islem"`, `STABIL=("USDT","USDC","BUSD","FDUSD")`, `YAKIN_ORAN = 0.01` (kapanış fiyatı stop/hedefe %1'den yakınsa o çıkış), `DENEME_SINIRI = 5` (dolum geçmişi alınamazsa en çok 5 tur; sonra boş alanlı satır).
**Bağımlılıklar.** stdlib; iç: yürütücü (`canli_yurutucu` `_kayit_*`).
**Testler.** `test_canli_kayit.py` (17).
**Kâğıtta etkin mi.** Yalnız canlı (kâğıt tarafında ayrı `islemler.jsonl` durum sözleşmesi, bölüm 6).
**Taşımada dikkat.** `satir_ekle` (kesik satır onarımı + fsync) bağımsız ve her projede işe yarar. Model maliyeti ile gerçek maliyeti bps cinsinden yan yana yazma fikri ("model_maliyet_bps vs gercek_maliyet_bps") ML Otonom için tahmin-gerçek kıyası verir.

---

## 6) İşlem mutabakatı + "sayıyı motor hesaplar, pano gösterir" ilkesi + giriş izi

### 6a) İşlem mutabakatı
**Dosya(lar).** `araclar/islem_mutabakat.py` (~620), `motor/canli/mutabakat_telegram.py` (122).
**Ne yapar.** Aynı işlem için üç kaynağı karşılaştırır: (1) MOTOR ham kaydı (`paper_state.json`; yoksa `islemler.jsonl` + `maruziyet.json`), (2) PANO (pano'nun AÇIK/KAPANAN satırlarını üreten aynı fonksiyonların HTML çıktısı ayrıştırılır: coin, yön, hesap adı, K/Z), (3) TELEGRAM (geçmişe erişim yok; motorun mesaj üretim yolu `islem_acildi_metni/islem_kapandi_metni` yeniden üretilip metindeki yön/coin/hesap/K-Z karşılaştırılır; `telegram_gonderim.jsonl` varsa gerçek gönderimle de). Sonuç `mutabakat_v1.json` (+ md). `mutabakat_telegram.tick` yalnız SORUN varsa uyarı yollar (kasa tutmuyor / uyuşmazlık > 0), sorun yoksa hiç mesaj yok.
**Giriş / çıkış.** CLI: `python -m araclar.islem_mutabakat --durum DIZIN [--ct DIZIN] [--aday DIZIN] [--cikti mutabakat_v1.json] [--md mutabakat_v1.md]`. İşlevler: `hesapla(durum, ct=None, aday=None, simdi=None) -> dict`, `ham_motor(dizin, gizli=None)`, `pano_kapanan_ayristir`, `pano_acik_ayristir`, `mesaj_ayristir(metin)` (regex `^\[1L3A\]\s*(?:\S+\s+)?(?P<coin>\S+)\s+(?P<yon>long|short)\s+(?P<olay>açıldı|kapandı)\s+·\s+(?P<hesap>.+)$`), `markdown(c)`, `yaz(...)`, `main(argv)`. Şema `1l3a.mutabakat.v1`. Uyuşmazlık `tur` değerleri: `kasa`, `acik_sayisi`, `serit` (şerit kasası), `telegram_gonderim`, `pano_okuma` (+ kapanan/açık alan farkları). Telegram tarafı: `tick(durum_dizin, gonder=None, simdi=None) -> bool`, `sorun_var(c)`, `metin_uret(c)`, `uyusmazlik_satiri(u, s)`; durum `mutabakat_telegram.json`.
**Kontrol listesi (mutabakatın baktıkları).** (1) Kasa tutuyor mu: başlangıç + kapanan net + açık K/Z = özsermaye (tolerans `KASA_TOL = 0.01` USD). (2) Açık pozisyon sayısı motor = pano. (3) Her kapanan işlem için motor net = pano K/Z = Telegram K/Z. (4) Yön işareti: fiyat hareketi giriş tutarının %1'inden (`YON_ESIK = 0.01`) büyük ve net işareti ters ise "işaret uyuşmazlığı" (komisyon/funding payı tolerans). (5) Açık pozisyon için giriş/mark/K-Z işaret tutarlılığı. (6) Şerit (ct/aday) kasaları ayrı. (7) Gizli hesaplar dahil mi (aşağı bkz.).
**Bağımlılıklar.** iç: `durum`, `gunluk_ozet` (`_dec/_json/_jsonl`), `hesap_adlari`, `pano`, `telegram`. Dış: stdlib.
**Yapılandırma.** `TELEGRAM_NOTU`, `KASA_TOL = Decimal("0.01")`, `YON_ESIK = Decimal("0.01")`, `TSI_FMT = "%Y-%m-%d %H:%M"`; Telegram: `DOSYA="mutabakat_v1.json"`, `BAYRAK_DOSYA="mutabakat_telegram.json"`, `ARALIK_SN=600`, `TEKRAR_SN=21600`, `ORNEK_MAKS=3`. Komut servisi her 600 sn `_mutabakat_tick` çağırır; pano servisi dosyayı üretir.
**Testler.** `test_islem_mutabakat.py` (13), `test_mutabakat_telegram.py` (7).
**Kâğıtta etkin mi.** Evet (sunucuda 0 uyuşmazlık, denetim 2026-11-20).
**Taşımada dikkat.** KAVRAM taşınır: "tek işlem, üç yüzey (motor kaydı / görsel pano / bildirim), aynı rakam" + yalnız sorunda uyar. 1L3A'ya özgü: pano HTML ayrıştırma, `paper_state.json` ham yapısı, hesap grupları (ana/ct/aday), TSİ gösterimi. Gizli hesap kısıtı: mutabakat çıktısında gizli hesap adı/kimliği/coin-zaman izi yazılmaz; denetim A1: kapanan işlemlerde gizli hesaplar dahil sayılıp sahte uyuşmazlık ve izli yayın riski vardı (ilk gizli kapanışta tetiklenir, düzeltme ayrı iş). A4: kasa kontrolü hiç yapılmadıysa "tutuyor ✅" yazma hatası. Aynı sayıda farklı uyuşmazlık tekrar bildirilmez (bilinen sınır).

### 6b) Durum ilkesi: atomik yazım ve tek formül
**Dosya(lar).** `motor/canli/durum.py` (431), `motor/canli/DURUM_SOZLESMESI.md`, `motor/canli/paper_durum.py` (622; `_acik_pnl` 59, `_net_formul` 64).
**Ne yapar.** İLKE: bütün sayıları MOTOR hesaplar ve yazar; pano yalnız okuyup biçimler; motor ile pano asla farklı sayı göstermez. Atomik yazım: aynı dizinde geçici dosya + `flush` + `os.fsync` + `os.replace` (+ dizin girdisi fsync) -> okuyucu ya eski ya yeni TAM dosyayı görür. Para metin (`"10720.00"`, Decimal 2 hane, `ROUND_HALF_EVEN`), oran JSON sayısı (0.072 = %7.2), ölçülmeyen değer `null` (NaN/Infinity yasak), okuma hatası (dosya yok / bozuk JSON / şema uyumsuz) `DurumHatasi` ile YÜKSELİR, değer uydurulmaz. Açık net K/Z formülünün TEK kaynağı: `_net_formul(fiyat, giris, miktar, yon, giris_kom, cikis_kom, funding, brut_toplam) = (fiyat - giris) * miktar * yon - giris_kom - cikis_kom - funding + brut_toplam`; `_acik_pnl(m, pos)` ve `askida_net` ikisi de bunu çağırır; `strateji_pnl = kapanan(net_pnl) + açık(_acik_pnl)`; Σ hücre katkısı = Σ strateji toplamı (aynı formül).
**Giriş / çıkış.** `atomik_yaz_metin(yol, metin) -> Path`, `atomik_yaz_json(yol, veri)`, `atomik_yaz_jsonl(yol, satirlar)`, `yaz_json_sirali`, `oku_json_varsayilan(yol, varsayilan)`, `yaz_hepsi(dizin, *, ozet, stratejiler, islemler, saglik, gecmis, ...)`, `islem_ekle`, `oku_hepsi(dizin) -> tuple`, `dogrula_*` (şema doğrulayıcılar), `para`, `zaman_str`, `zaman_oku`. Şema adı kalıbı `1l3a.durum.<ad>`, zarf `sema, surum, zaman, kaynak (backtest|paper|canli)`. Yazım sırası: `islemler`, `ozsermaye_gecmisi`, `stratejiler`, `saglik`, **`ozet` en son** (okuyucu ozet'i gördüğünde diğerleri hazır).
**Dosyalar (durum dizini, `DOSYALAR`).** `ozet.json, stratejiler.json, islemler.jsonl, saglik.json, ozsermaye_gecmisi.json`; eklemeli `EK_DOSYALAR`: `maruziyet, maliyet, reddedilen, olaylar.jsonl, icgoruler, dersler, aylik_rapor, veri_guveni, butunluk, koni, kiyas, korelasyon, yogunlasma, karne, koc`. Sürüm `SURUM = 1`; varsayılan dizin `durum/` (.gitignore'da); sunucuda `/var/lib/1l3a-paper/durum`.
**Zaman kuralı.** Dosyada UTC (`YYYY-MM-DDTHH:MM:SSZ`). Gün gruplaması (günlük K/Z, düşüş serisi, özsermaye geçmişi, hafta/ay) TSİ'ye (`Europe/Istanbul`, gün 00:00 TSİ'de biter; hafta ISO pazartesi). BİLEREK UTC kalanlar: sert günlük kayıp limiti günü (`motor.gun`, risk kodu) ve beklenti aralığı pencereleri (28/56 gün). `ozet.gun_kesimi` hangi kesimin kullanıldığını söyler.
**Bağımlılıklar.** stdlib; (paper_durum) iç: paper motoru nesneleri, Decimal.
**Testler.** `test_canli_durum.py` (19), `test_paper_durum.py` (13), `test_durum_ek.py`.
**Kâğıtta etkin mi.** Evet (kâğıt motoru bu dosyaları yazıyor, pano okuyor).
**Taşımada dikkat.** Atomik yazım fonksiyonu bağımsız, aynen alınır. "Tek formül, iki çağıran" ilkesi: açık K/Z formülünün kopyalarının sapması denetimde mükerrer kod olarak bulundu; kalan kopya (`askida_net`) `_acik_pnl`'den çağırılmalı. Şema dosyaları 1L3A'nın `durum/` sözleşmesine özgü; ML Otonom kendi panosu varsa yalnız ilke + atomik yazıcı + zarf alanları alınır. Para-metin, oran-sayı ayrımı pano tarafı biçim hatalarını önler.

### 6c) Giriş / sürüm izi
**Dosya.** `motor/canli/giris_izi.py` (133).
**Ne yapar.** Her paper işlem kaydına (`islemler.jsonl`) iki alan ekler: `ayar_surumu` (kullanılan parametre setinin kısa hash'i) ve `giris_gerekcesi` (sinyal anında bilinen değerlerden kurallı açıklama). Hash = `sha256("strateji_adı|ayar_etiketi")[:12]`; ayar yenilemesi (180/90 gün) etiketi, dolayısıyla hash'i değiştirir, eski/yeni ayarın işlemleri karışmaz. Gerekçe genel şablon `genel/1`: strateji adı + yön + sinyal mumu zamanı + kapanış fiyatı + stop/hedef mesafesi + sinyal tablosundaki ek sütunlar (göstergeler, en çok 12) + çıkış kuralları; hepsi karar anındaki satırdan (mumlar <= t): LOOKAHEAD YOK, giriş dolumu gerekçeye girmez. Eski kayıtlarda alanlar `null`.
**Giriş / çıkış.** `ayar_surumu(strateji_ad, ayar_etiketi, set_dosyasi) -> {"hash","set_dosyasi","ayar","strateji"}`; `gerekce_tek(t, mumlar, sig, yon, stop, hedef) -> dict`; `gerekce_agirlik(t, sembol, acilis, kapanis_fiyati, w, stop) -> dict` (ağırlık/portföy kolu); yardımcı `_gostergeler`, `_cikis_kurallari`, `_metin`.
**Bağımlılıklar.** pandas, `durum`.
**Yapılandırma.** `SABLON = "genel/1"`, `STANDART_SUTUNLAR = ("yon","stop","hedef","cikis","cikis_long","cikis_short","zaman_cikisi_mum")`, `MAX_GOSTERGE = 12`.
**Testler.** `test_pano_oncelik4.py` (kapsar; ayrı `test_giris_izi` dosyası yok).
**Kâğıtta etkin mi.** Evet (paper motoru `karar_meta/giris_meta` ile pozisyona bağlıyor).
**Taşımada dikkat.** Fikir doğrudan ML için değerli: "bu işlem hangi model/ayar sürümüyle, hangi özellik değerleriyle açıldı" izi. Karar anı verisi dışında alan eklemeyin (lookahead). Ayar etiketi 1L3A'nın `guncel_ayarlar.csv`/`final_set.json` düzenine bağlı; ML Otonom'da model sürüm kimliği (hash) ile eşleyin.

---

## 7) Denetim / mutasyon yöntemi

**Dosya(lar).** `raporlar/denetim-1l3a.md` (100 satır), `raporlar/denetim_testleri/` (6 dosya: `denetim_A_muhasebe.py` 74, `denetim_B_giris_filtreleri.py` 96, `denetim_C_ogrenme.py` 93, `denetim_D_test.py` 131, `denetim_E_canli_yurutucu.py` 167, `denetim_E_ct_maxpoz.py` 28 satır). Ek: depo içi mutasyon testleri `testler/test_mutasyon_{sert_limitler,portfoy_boyut_kaldirac,stop_esitlik}.py`.
**Ne yapar.** Yöntem (2026-11-20 genel denetimi; taban `458cda6..92e6ca4`, son 48 saat, 58 Python dosyası; denetim boyunca kod DEĞİŞTİRİLMEDİ, düzeltmeler ayrı iş):

1. **Araç taraması**: ruff, mypy, vulture, bandit (sonuç: ruff 80, mypy 393 [para yolunda 94], vulture 5, bandit 19; çoğu gürültü).
2. **Modül başına inceleme** (5 grup: A muhasebe/mutabakat, B giriş filtreleri/otomatik değişiklikler, C ders+ML öğrenmesi, D emir/boyut/stop/kill/karantina, E canlı yürütücü + CT). Her bulgu bir **kırmızı testle** kanıtlanır: test, hata VARKEN kırmızı olmalıdır; dosya adı `test_` ile başlamaz (toplu koşuya girmez), tek tek: `python -m pytest raporlar/denetim_testleri/<dosya> -q -p no:cacheprovider`.
3. **Çürütme turu**: temiz bağlamlı ikinci inceleyici her bulguyu çürütmeye çalışır (sonuç: 30 bulgu, 0 çürütüldü; 21 doğrulandı, 9 kısmen).
4. **Önem + "kâğıtta" sınıflaması**: AÇIK (bugün işlemleri etkiliyor) / UYKUDA (koşul gelince) / ETKİSİZ (rapor/görüntü) / CANLI (canlıya geçince). Bugün kâğıtta açık ve işleme etkili olan yalnız 3 bulgu (E1, B1, B5).
5. **Mutasyon testi** (para yolu): `mutmut 2.5.1`, 4 modül, yalnız ilgili test dosyalarıyla; hayatta kalan sayısı string/log mutantlarını da içerir.
6. **Güven sınaması**: ayrı yerel kopyada para yoluna 5 bilinçli hata eklenir (hiç commitlenmez; kopya ve dal silinir), habersiz inceleyici bunları bulmaya çalışır; skor 4/5 (eşik 4/5 tuttu). Kaçan hata (`paper.py` canlı/kâğıt ayrımında VE/VEYA) yüzünden o grup ayrıca daha güçlü modelle (Opus) tekrar incelendi.
7. Ek ölçümler: rastgele sıralı test koşusu (pytest-randomly, 7826 geçti), `diff-cover` değişen satır kapsamı %89 (düşük: `ct_paper.py` %45, `paper_durum.py` %71, `islem_mutabakat.py` %79, `paper.py` %82), mükerrer kod listesi (hangisi kalsın), kullanıcı kararı gerekenler listesi.

**Mutasyon sonuçları (aynen).**

| Modül | Toplam | Öldürülen | Hayatta | Öldürme oranı |
|---|---|---|---|---|
| alinsaydi_gevsetme | 466 | 333 | 133 | %71,5 |
| karantina | 62 | 29 | 33 | %46,8 |
| bosluk_maruziyet | 222 | 166 | 56 | %74,8 |
| etiket_kurallari | 125 | 83 | 42 | %66,4 |

Testle kilitlenmemiş anlamlı noktalar: karantina.py ~60 (gizli/görünür kaldırma koşulunun ters çevrilmesi; güven sınamasındaki hata da buradaydı), alinsaydi_gevsetme.py ~373 (ikinci frende kalıcı kilit eşiği `>= 2`; ~32/340/401 30 günlük pencere sınırları), bosluk_maruziyet.py ~69-70 (eşik `>`/`>=`), etiket_kurallari.py ~52 (`haber_ters` yön/eşik sınırları). Sonuç: düzeltmeler sınır testleriyle gelmeli.

**Giriş / çıkış.** Girdi: son N saatin git farkı + testler. Çıktı: tek markdown rapor (özet, bulgu tablosu [numara, önem, yer, bulgu, kâğıtta], kısmen doğrulananlar, şüpheler [testle doğrulanmayan], araç taraması, mutasyon, güven sınaması, mükerrer kod, karar gerekenler) + kırmızı test dosyaları.
**Bağımlılıklar.** pytest, pytest-randomly, mutmut 2.5.1, ruff, mypy, vulture, bandit, diff-cover. (Bu araçlar `requirements.txt`'te olmayabilir, denetim ortamında kuruldu.)
**Yapılandırma.** Eşikler: güven sınaması 4/5; mutasyon hedefi yazılı değil (rapor "karantina %47 zayıf" der). Kırmızı testlerin kendi koşusu: tohum yok, `-p no:cacheprovider`.
**Testler.** Kırmızı testler bulgu başına bir; toplam 6 dosya, yaklaşık 30 test.
**Kâğıtta etkin mi.** Evet (yöntem koşuldu). Not: test koşusu `raporlar/pano3/pano3_ozet_390_{acik,koyu}.png` dosyalarını her seferinde yeniden yazıyor (repo kirleniyor).
**Taşımada dikkat.** Taşınan şey YÖNTEMdir, dosyalar değil. Özellikle: (i) "denetim kodu değiştirmez; bulgu = kırmızı test" kuralı, (ii) çürütücü ikinci göz, (iii) güven sınaması (bilerek hata enjekte edip yakalama oranını ölçmek) denetimin kendisini ölçer, (iv) "kâğıtta etkin mi" sütunu bulguları gerçek etkiye göre sıralar. Kırmızı testler 1L3A fonksiyonlarına bağlı olduğundan taşınmaz. Mutasyon öldürme oranı satır kapsamından farklı bir kaliteyi ölçer (kapsam %89 iken karantina öldürme %47).

---

## KOŞULLU a) Ders katmanı adaptör eklemeleri

**Dosya(lar).** `motor/canli/ogrenme_adaptor.py` (654 satır); arayüz tarafı `motor/ortak_ogrenme/` (1303 satır toplam: `ders.py` 135, `drift.py` 59, `filtre.py` 268, `karne.py` 95, `kayit.py` 103, `notlar.py` 131, `telegram_cekirdek.py` 503). Paket `ortak_ogrenme 1.2.0` ortak (1L3A ile CT projesi vb.) ve 1L3A bunu DEĞİŞTİRMEZ; adaptör eklemeleri ML Otonom'a taşınacak katmandır.
**Ne yapar.** ML filtre ve ders (aday + aktif) paper girişini doğrudan ATLATABİLİR (gölge mod YOK; kullanıcı kararı 2026-11-19: "gölgesiz otomatik"). Sınır kod düzeyindedir: öğrenme parçası yalnız bir YENİ girişe "hayır" diyebilir; boyut, stop, hedef, limit, kaldıraç, risk tavanı ve SERT_LIMITLER'e dokunamaz, yeni işlem açtıramaz (kanca motorda emir verilmeden hemen önce reddeder: `paper_motor._giris_izni`). Hata -> giriş SERBEST (fail-open). Ders freni + geri alma gece adımında: etkin derslerin toplam etkisi <= -`FREN_ESIK_R` ise tüm etkin dersler askıya alınır ve ölçülmeye devam eder (askıdan sonra etki > 0 olunca kendiliğinden döner, Telegram "Düzeldi"); tek ders <= -`GERI_ALMA_R` ise emekli edilir. Etki, engellenen sinyallerin simüle R'siyle (kontrafaktüel "alınmış" sayılır) hesaplanır. Drift (CUSUM uyarısı) eylemi: kurulumun ML filtresi hemen yeniden eğitilir, dersin girişi atlatması yarıya iner (çarpan 0,5), durum JSON'una `drift` yazılır.
**Giriş / çıkış.**
- `bagla(p, dizin, gonder=None, env=None) -> Optional[Ogrenme]` (kapalıysa None; kancayı paper'a takar), `kapali(env=None) -> bool`.
- `Ogrenme(dizin, gonder=None, saat=None, kapali_=None)`: `giris_suzgeci(strateji, sembol, yon, oz) -> tuple` (izin + neden), `ozellik_uret(h, t, e) -> dict`, `tur(simdi)`, `gunluk(simdi) -> bool` (gece adımı, TSİ 00:30), `engellenenler(simdi) -> list` (ders yüzünden atlanan sinyaller, son `FREN_PENCERE_GUN` gün), `aday_karsi_olgu(engel, simdi) -> dict` (C3: engelleyen aday dersin engellenen sinyallerini sonraki mumlarla simüle edip n/R'yi aday dersin kimliğine yazar), `fren_adimi(simdi, engellenen=None) -> dict`, `alinmayanlar() -> list`, `egitim_adaylari(ad, karar_ts)`, `ders_carpani(ad) -> float`.
- Yardımcılar: `islem_adayi(satir, ozellik, esleme, id_=None) -> ok.Aday` (kapanan işlemden), `alinmayan_adayi(satir, esleme) -> ok.Aday` (`alinmayan_sinyaller.jsonl` satırı -> `alindi=False, r=None`; özellikler satırdaki fiyat/stop/hedef + kayıt etiketlerinden), `ozellik_sozlugu(yon, px, stop, hedef=None, atr14=None, atr_ratio=None, seans_kapali=None, etiketler=None)`, `etiket_ozellik(et)`, `atr_ozellikleri(df)`, `temiz_ad(sk)`, `Esleme` (strateji kimliği <-> kurulum adı, kalıcı).
- Ortak paket arayüzü: `ders.ders_etkisi(adaylar, kimlik, dogum_gunu, as_of, ...)`, `ders.gece_adimi(adaylar, notlar, durum_yolu, ...)`, `ders.etkin_dersler(durum_yolu, limit=8)`, `ders.uyan_dersler(etkin, aday)`, `ders.fren_durumu(adaylar, etkin_kimlikler, baslangic, as_of, esik_r=10.0, geri_alma_r=3.0) -> {"toplam_etki","fren","geri_al"}` (rapor; uygulamak adaptörün işidir), `drift`, `karne`, `filtre` (numpy yoksa filtre YOK, ders/drift/karne çalışır), `kayit.Aday`, `notlar.not_yaz`.
- Durum dizini dosyaları: `ogrenme_adaylar.jsonl` (kapanan işlemler), `ogrenme_ders.json` (ders yaşam döngüsü), `ogrenme_modeller/` (filtre paketleri), `ogrenme_durum.json` (eğitim/drift/ders günü), `ogrenme_esleme.json`, `ogrenme_karne.json` (pano okur), `ogrenme_fren.json` (`{"askida": {kimlik: {"zaman","neden"}}}`), `alinmayan_sinyaller.jsonl`.
**Bağımlılıklar.** iç: `durum` (atomik JSON), `kayit_etiketleri._utc`, `araclar.alinmayan_sonuc`, `motor.ortak_ogrenme.*`, paper/paper_motor kancaları, Telegram (Bildirimci 6 saat kuralı). Dış: numpy, pandas, scikit-türevi yok (filtre numpy).
**Yapılandırma (aynen).**
```
ENV_KAPALI = "L3A_OGRENME_KAPALI"        # =1 tamamen kapanır (kanca bağlanmaz)
MIN_EGITIM = 10          # altında filtre kurulmaz (2026-11-19: 30 -> 10)
YENIDEN_GUN = 20         # paket ömrü 21 gün; bir gün erken yenile
YENIDEN_ISLEM = 10
DERS_SAAT_TSI = (0, 30)
FREN_DOSYASI = "ogrenme_fren.json"
EGITIM_HATA_BEKLEME_SAAT = 1
DRIFT_DERS_CARPANI = 0.5
REJIMLER = ("trend_up","trend_down","range","volatile","unclear")
FREN_ESIK_R, GERI_ALMA_R, FREN_PENCERE_GUN = 10.0, 3.0, 30
```
**Testler.** `test_ogrenme_adaptor.py` (16), `test_ogrenme_drift.py` (4), `test_ogrenme_fren.py` (10), `test_denetim_ogrenme.py` (11), ayrıca `test_dersler_rapor.py`.
**Kâğıtta etkin mi.** Evet, bağlı (`paper.py:817-818`: `ogrenme_adaptor.bagla`); denetim: "ders yok" (C2 UYKUDA), yani bağlı ama henüz etkin ders doğmadı; ML filtre için `MIN_EGITIM=10` aşırı uyum riski şüphesi var.
**Taşımada dikkat.** Önce ML Otonom'da `ortak_ogrenme` paketi (veya eşdeğeri) var mı bakılmalı; adaptör onun üstüne oturur. Taşınacak eklemeler: gece fren adımı, geri alma, CUSUM drift eylemi, aday karşı-olgu (C3), alınmayan sinyali aday yapma, `L3A_OGRENME_KAPALI` anahtarı, fail-open ilkesi. Bilinen açıklar (denetim): C1 geri alma/fren/drift Telegram mesajında gizli hesap adı açık yazılıyor (kullanıcı şartı: yazılmamalı); C2 fren/geri alma penceresi dersin doğumundan önceki işlemleri de sayıyor (kötü ders maskelenebilir / iyi ders hemen geri alınabilir); C3 girişi engelleyen aday ders n=0 kaldığı için süresiz engelleyebilir (düzeltme: `aday_karsi_olgu`); C5-C7 gece adımı hatası günün drift/karnesini atlatır, kayıt dosyasında tek bozuk satır geçmişi sildirebilir, eğitim hatası her turda yeniden denenir. Kurulum adı yalnız harf/rakam/_ (README `@` yasak): `dis__ewo-ema-ofset` -> `dis_ewo_ema_ofset`, çakışırsa kısa hash. TSİ 00:30 gece adımı saati 1L3A'ya özgü.

---

## KOŞULLU b) Binance imzalı istemci

**Dosya.** `motor/canli/borsa/binance_futures.py` (456).
**Ne yapar.** Minimal imzalı Binance USDⓈ-M vadeli REST istemcisi (HMAC-SHA256). Anahtar/gizli yalnız ortam değişkeninden; imzalı sorgu (`signature=...`) hiçbir log/hata metninde görünmez (`temizle`); ağ hata metinleri loglanmaz, yalnız istisna türü adı. Yeniden deneme: okuma/iptal/ayar istekleri ağ hatası, 5xx ve -1021'de (üstel geri çekilme) tekrar denenir; EMİR VEREN POST'lar (`/fapi/v1/order`, `/fapi/v1/algoOrder`) ağ hatası/zaman aşımı/5xx'te ASLA OTOMATİK TEKRAR EDİLMEZ (aynı `newClientOrderId` ile dolmuş piyasa emri ikinci kez dolar = çift pozisyon); belirsiz sonuç `belirsiz=True` `BorsaHata` olarak yükselir, çağıran emri kimlikle SORGULAR ve yalnız borsa "böyle emir yok" derse yeniden gönderir; emir POST'unda yalnız -1021 güvenle tekrar denenir. Koşullu emirler (STOP_MARKET/TAKE_PROFIT_MARKET) Algo Order uçlarında (`kosullu_modu="algo"` varsayılan; `"klasik"` eski uç).
**Giriş / çıkış.** `BinanceFutures(ortam="testnet", anahtar="", gizli="", oturum=None, uyku=time.sleep, ...)`; metotlar `zaman_esitle, sunucu_zamani, exchange_info, mark_fiyat(sembol)->Decimal, bakiye, pozisyonlar, emirler(sembol=None), hazirla(sembol, kaldirac), piyasa(sembol, yon, miktar, client_id, reduce_only=False), kosullu(sembol, tur, yon, miktar, tetik, client_id, ...), sorgula(sembol, client_id) -> Optional[dict], iptal(sembol, client_id, kosullu=True), hepsini_iptal(sembol), kullanici_islemleri(sembol, bas_ms, bit_ms=None), funding_gecmisi(...)`. Hatalar `BorsaHata(mesaj, kod, http, belirsiz)`, `EmirReddi`, `BorsaYasagi`. Yardımcılar: `imzala(sorgu, gizli)`, `temizle(metin)`, `duz(x)`, `host_al`, yasak deposu (bölüm 4d). `__repr__` anahtarı göstermez. Normalize emir dict: `durum`, `dolan` vb.
**Yapılandırma (aynen).** `TESTNET="https://testnet.binancefuture.com"`, `CANLI="https://fapi.binance.com"`, `AGIRLIK_ESIGI=1800`, `ISTEK_ZAMAN_ASIMI=20`, `IDEMPOTENT_KODLAR={-4046,-4059}`, `YOK_KODLARI={-2013,-2011}`, `BELIRSIZ_KODLARI={-1006,-1007,-1008}` (+ HTTP 408), `SAYFA=1000`, `VARSAYILAN_HOST="fapi.binance.com"`.
**Bağımlılıklar.** stdlib + `requests` (oturum). Ağ: Binance REST.
**Testler.** `test_canli_borsa.py` (72, sahte HTTP; gerçek Binance'e erişim yok).
**Kâğıtta etkin mi.** Yalnız canlı (kâğıt yalnız herkese açık uçları `FapiIstemci` ile okur). Uç/parametre adları TESTNET'te doğrulanmamıştır ("bu geliştirme ortamından Binance'e erişim yoktur").
**Taşımada dikkat.** Emir POST'unu otomatik tekrar etmeme + kimlikle sorgulama kalıbı en değerli kısımdır. Algo Order uç adları (2025-12 geçişi) testnet'te doğrulanmadan gerçek paraya konmamalı. Denetim şüphesi: emir POST'unda 429 belirsiz sayılıyor (kod `r.status_code in (429, 418)` dalı `belirsiz=(kod in BELIRSIZ_KODLARI) or not tekrar_guvenli` ile; 429 aslında "işlenmedi" demektir, ama burada emir POST'unda belirsiz sayılabilir; ML Otonom bunu bilerek karar versin). Marj tipi doğrulanmıyor; `exchangeInfo` canlıda yenilenmiyor.

---

## KOŞULLU c) Kayıt etiketleri (yalnız veri toplama)

**Dosya(lar).** `motor/canli/kayit_etiketleri.py` (224), `motor/canli/etiket_sonuc.py` (211); yardımcı `oi_istemci.py` (87), `haber_etiketi.py` (174, haber taşınmayacak listede), takvim `stratejiler/ekonomik_takvim.json`.
**Ne yapar.** YALNIZ KAYIT (2026-11-19): alınmayan sinyaller ve işlem/sinyal etiketleri; işleme/emre/boyuta/risk kararına SIFIR etki. Motor yalnız kanca çağırır; buradaki her hata yutulur ve loglanır, ağ istekleri kısa zaman aşımlıdır (hata sonrası 3600 sn yeniden denenmez). Etiketler: fonlama oranı (karar anından ÖNCE en son funding, paper'ın zaten taşıdığı veriden; yalnız kripto), açık pozisyon (OI) USD + 24 saatlik değişim (yalnız kripto), korku/açgözlülük endeksi, takvim bayrağı (ekonomik takvim, olaydan ±2 saat), rejim (`rejim_ml_4h`, `rejim_ml_1d`, harici rejim servisinden). `etiket_sonuc.py` kapanan işlemleri bu etiketlere göre kırar (R veya net USD) ve `etiket_sonuc_v1.json` (şema `etiket_sonuc.v1`) yazar; yalnız okur.
**Giriş / çıkış.**
- `Kayit(dizin, fng_fn=None, saat=time.time, takvim_yolu=TAKVIM_YOLU, rejim_dosya=None, rejim_url=None, rejim_http=_http_json, oi_fn=None, rejim_kapali=None, haber_fn=None)`; `Kayit.fonlama(sembol, t, funding_df) -> Optional[float]` ve diğer etiket metotları. Çıktı `alinmayan_sinyaller.jsonl` (durum dizini; ekleme; 50 MB'ı geçince `.1`'e taşınır): satır alanları `zaman (UTC karar anı), hesap, strateji, kol, sembol, tf, yon, fiyat (metin), stop, hedef, zaman_cikisi_mum, neden` + etiketler (`fonlama_orani, oi_usd, oi_degisim_24s, korku_acgozluluk, takvim_bayragi, rejim_ml_4h, rejim_ml_1d, haber_tonu, haber_sayisi`).
- `etiket_sonuc`: `etiket_tablosu(islemler) -> dict`, `birim_sec(islemler)` (hepsinde `r` varsa R, yoksa `net_pnl_yerel`), `kart(islemler, simdi_iso, gun)`, `yaz(durum_dizini, simdi, set_yolu=None) -> Optional[dict]`, `haftalik_satir(e)`, `rejim_karsit_sayisi(islemler)`. Etiket adları `ETIKET_ADLARI = ("rejim_ml_4h","rejim_ml_1d","takvim_bayragi","kalabalik","korku_acgozluluk","seans_dilimi")`; etiketsiz işlem "bilinmiyor" grubuna girer.
**Bağımlılıklar.** pandas, stdlib `urllib`; iç: `etiket_kurallari` (kalabalık eşikleri), `oi_istemci`. Ağ: `api.alternative.me/fng` (korku/açgözlülük), Binance OI (herkese açık), rejim JSON adresi.
**Yapılandırma (aynen).** `DOSYA_ADI="alinmayan_sinyaller.jsonl"`, `MAX_BAYT=50*1024*1024`, `FNG_URL="https://api.alternative.me/fng/?limit=30&format=json"`, `ZAMAN_ASIMI_SN=3.0`, `HATA_BEKLEME_SN=3600.0`, `FNG_TAZELIK=48 saat`, `TAKVIM_PENCERE=2 saat`. Rejim adresleri (1L3A'ya özgü Worker URL'leri; ESKI `trader-pano...` Access arkasına alındı, YENI `trader-pano-acik...workers.dev/rejim.json`). Ortam: `L3A_KAYIT_KAPALI=1` (tüm kaydı kapatır; `paper.py:809`), `L3A_REJIM_KAPALI=1`, `L3A_REJIM_URL`, `L3A_REJIM_DOSYA`, `L3A_HABER_KAPALI=1`.
**Testler.** `test_kayit_etiketleri.py` (18), `test_etiket_sonuc.py` (17), `test_etiket_kurallari.py`, `test_bosluk_olcum.py` (ilgili).
**Kâğıtta etkin mi.** Evet (varsayılan açık: `paper.py:809`'da `L3A_KAYIT_KAPALI != "1"` ise kanca açılır).
**Taşımada dikkat.** Yalnız veri toplama kısmı taşınır; "etiket kuralı" (giriş atlatma) taşınmayacaklar listesinde. Gizli hesaplarda işlemler toplamlara girer ama adı hiçbir çıktıda yazılmaz. Etiketin değeri karar anından ÖNCE bilinen veriden olmalı (lookahead yok). Etiket × sonuç kartının kanıt gücü sınırlı: ölçüm bilgi amaçlıdır, kâr katkısı gösterilmedi. Seans dilimi etiketi yalnız hisse/emtia için anlamlı; kriptoda "bilinmiyor". 1L3A kayıtları UTC, rapor TSİ.

---

## KOŞULLU d) Kill-switch / belirsiz emir mantığı (fikir düzeyi)

**Dosya.** `motor/canli/borsa/canli_yurutucu.py` (930; `Yurutucu` sınıfı 131-; `_koruma_pasi` 238, `_adim` 289, `_risk_izle` 338, `hesap_kill_ver` 346, `_hepsini_kapat` 356, `_piyasa_kapat` 380, `_ac_niyeti` 425, `_giris_gonder` 539, `_belirsiz_sorgu` 527, `_mutabakat` 685, `_kayit_*` 784-); `motor/canli/borsa/calistir.py` (313; hesap kill'i toplam kasa üzerinden), `motor_kopru.py` (93), `risk_adim_kontrol.py` (123, salt okunur `--durum DIR` denetimi).
**Ne yapar.** (i) Kill-switch: strateji kasası zirveden -%30 veya TÜM canlı stratejilerin kasa toplamı ortak zirveden -%20 düşerse hepsini kapat + KALICI dur (yeniden başlatmada da; durum dosyasında `kill`, `kill_neden`). Kalıcı kill, özsermaye okumasından ÖNCE denetlenir; özsermaye okunamazsa "yalnız koruma" turu (giriş yok). Günlük -%5'te yeni giriş bloklanır, açık pozisyon KAPATILMAZ (borsa stopu + strateji çıkışı sürer). (ii) Kapatma sırası: ÖNCE `reduceOnly` piyasa emriyle kapat; stoplar YALNIZ pozisyonun sıfırlandığı borsada doğrulanınca iptal edilir; kapatma başarısızsa stoplar yerinde kalır, her turda yeniden denenir, mutabakat stopları korur ve "ELLE KONTROL EDİN" uyarısı gider. (iii) Belirsiz emir: giriş POST'u belirsizse kısa aralıklarla kimlikle sorgulanır; hâlâ bilinmiyorsa durum `belirsiz` döner, kayıt `gonderildi` kalır (emirden ÖNCE yazılır: çökme olursa mutabakat stopu buradaki kayıttan kurar), borsada pozisyon görününce stop HEMEN kurulur; emir yeniden gönderilmez. (iv) E3 tam dolum şartı: belirsiz kapatmada emir sorguda `FILLED` ya da `dolan >= |miktar|` ise "kapandı" sayılır; sadece emir bulundu diye değil.
**Giriş / çıkış (fikir düzeyi).** `Niyet` (paper'ın niyeti: kol, sembol, yön, stop, hedef, ...), `MotorGorunumu`, `PozGorunum`, `Ayar`; `Yurutucu.adim(g: MotorGorunumu, yalniz_koruma=False)`; client_id kalıbı `client_id(rol, strateji, kol, zaman, ek="")`; kayıt satırları (bölüm 5d). `SifirdanBaslamaHatasi`/`sifirdan_kontrol`: durum dosyası yokken dizinde başka kayıt varsa başlamaz (kayıp zirve/kill kaybı olmasın; `L3A_SIFIRDAN_IZIN` ile bilerek aşılır).
**Bağımlılıklar.** iç: `binance_futures`, `kurallar`, `canli_limitler`, `canli_kayit`, `canli_ayar`, paper motor köprüsü; pandas.
**Yapılandırma.** Eşikler `canli_limitler` (bölüm f). `risk_adim_kontrol` salt okunur.
**Testler.** `test_canli_borsa.py` (72), `test_canli_denetim2.py` (25), `test_canli_islem_risk.py` (20), `test_canli_sertlestirme.py`, kırmızı testler `raporlar/denetim_testleri/denetim_E_canli_yurutucu.py`.
**Kâğıtta etkin mi.** Yalnız canlı (canlı servis kurulu/aktif değil).
**Taşımada dikkat.** FİKİR düzeyinde alınmalı; kod 1L3A'nın paper->niyet->köprü mimarisine sıkı bağlıdır. AÇIK ŞÜPHELER (testle doğrulanmadı veya bulgu): (1) kill "bilinmeyen" (kayıtta olmayan) pozisyonu da kapatıyor (`poz` borsadaki tüm pozisyonlar; teyit gerekir: aynı hesaba elle açılan pozisyon da kapanır); (2) emir POST'unda 429 belirsiz sayılıyor (doğrusu "işlenmedi"); (3) E2 (KRİTİK, canlıya geçişte): kâğıdın reddettiği giriş (ML/etiket/karantina/risk kırpma) canlı niyete aktarılmıyor, canlı önce girer bir mum sonra kapatır, DURUM.md:12'deki "atlanan paper girişi canlıda da açılmaz" iddiası yanlış; (4) E3 (ORTA-DÜŞÜK): belirsiz kapatmada dolmamış emir "kapandı" sayılıp stop iptal olur, bir tur korumasız kalır (kodda şimdi tam dolum şartı var, ama bulgu bu düzeltmeyle kapandı mı teyit edin); (5) D1: çıkış karşı-olgusu canlı yolda da bağlanıyor, "canlıda kendini değiştiren kod yok" kararıyla çelişir. İlke olarak alınacaklar: kalıcı kill + yalnız-koruma turu, emirden önce kayıt yaz, tekrar gönderme yerine sorgula, stopu pozisyon sıfırlanmadan iptal etme.

---

## KOŞULLU e) Telegram komutları + günlük özet

### e1) Telegram komutları
**Dosya(lar).** `motor/canli/telegram_komut.py` (564), `motor/canli/telegram.py` (804, gönderim standardı), `motor/ortak_ogrenme/telegram_cekirdek.py` (503, istemci çekirdeği).
**Ne yapar.** Telegram komut servisi (`KomutServisi`, `1l3a-telegram.service`): yalnız `TELEGRAM_CHAT_ID`'e yanıt verir; riskli komutlar iki adımlıdır (komut -> 4 haneli kod -> 120 sn içinde kodu yaz). Durum bayrağı dosyaları aracılığıyla paper/ct/aday süreçleriyle konuşur (`l3a` kullanıcısı root işi yapamaz).
**Komut listesi.**
- `/durum`: bot, hesaplar, sunucu (kalp atışı bayat eşiği `KALP_BAYAT_SN=600`, "kod: <sha>, son güncelleme", disk satırı, canlı mod).
- `/rapor`: günlük özet (`gunluk_ozet.topla` verisi). `/kurulumlar`: hesap/ct/aday listesi (açık pozisyon, toplam K/Z, son işlem, ML filtre, drift). `/ders`: aktif/aday + son 7 gün emekli.
- `/durdur` (RİSKLİ): bayrak `DURDUR` yazar; paper ve ct_konsensus YENİ giriş açmaz, bekleyen giriş emri silinir, açık pozisyonlar kendi stop/hedefiyle sürer. `/devam` (RİSKLİ): bayrağı kaldırır.
- `/hepsini_kapat` (RİSKLİ): DURDUR + istek dosyası `HEPSINI_KAPAT`; paper/ct/aday süreçleri sonraki turda açık pozisyonları motorun acil kapatma yoluyla piyasa fiyatından kapatır, WARN bildirir, dosya 120 sn sonra silinir. Canlı mod açıkken uyarı: canlı gerçek para pozisyonları bu komutla kapanmaz/borsadan kontrol edin (`CANLI_UYARI`).
- `/geri_al` (RİSKLİ): `GERI_AL` istek dosyası (bölüm 3b). `/cikis_geri_al` (RİSKLİ): `CIKIS_GERI_AL` dosyası, son otomatik çıkış değişikliğini geri alır.
- `/karantina_kaldir <strateji>` (iki adımlı; `gizli`, `hepsi` hedefleri) -> `KARANTINA_KALDIR` dosyası (bölüm 4b).
- `/kademe`, `/kademe_devam`, `/onayla`, `/reddet`: 1L3A'da kullanılmaz, bilgi yanıtı (ortak paketten gelen komutlar). `/yardim`, `/start`: liste.
**Giriş / çıkış.** `KomutServisi(istemci, chat_id, durum_dizin, *, now_fn, bayrak, ct_dizin, canli_dizin, canli_ayar, rng, sleep, guncelle_dizin, sha_fn, geri_al_dosya, aday_dizin, set_yolu, hepsini_kapat_dosya, cikis_geri_al_dosya, disk_kok, disk_fn, mut_gonder, sv_gonder)`; `isle(guncelleme: dict)`, `durum_metni() -> (onem, govde)`, `rapor_metni()`, `kurulumlar_metni()`, `ders_metni()`, `tur(bekleme=30) -> int`, `calistir(max_tur=None)`, `durdur`; ana döngü her turda `_disk_tick` (300 sn), `_mutabakat_tick` (600 sn), `_strateji_verisi_tick` çağırır. Kod deseni `^(?:/onay\s+)?(\d{4})$`. `RISKLI = ("/durdur","/devam","/geri_al","/hepsini_kapat","/cikis_geri_al")`. Denetim kaydı `_denetim`.
**Telegram standardı (docs/standart/telegram-standardi.md).** İlk satır `[1L3A] INFO|WARN|CRIT` (INFO emojisiz sessiz, WARN ⚠️, CRIT 🔴), mesaj en çok 3500 karakter (`MAKS`), dakikada en çok 15 (`DAKIKA_SINIRI`, aşan INFO atılır), tekrar önleme penceresi 600 sn, aynı uyarı anahtarı 6 saatte bir (`TEKRAR_UYARI_SN`, CRIT bastırılmaz), iki mesaj arası en az 1 sn, başlangıç mesajları 60 sn'de birleşir, bilgi satırları saatte bir tek mesaj. `maskele` token kalıbını siler. `OrtakDurum` servisler arası tekrar/oran sınırı kalıcı durumu (`L3A_ORTAK_BILDIRIM`, varsayılan `/var/lib/1l3a-paper/ortak_bildirim`).
**Bağımlılıklar.** iç: `telegram`, `telegram_cekirdek` (TelegramClient), `disk_bakim`, `karantina`, `gunluk_ozet`, `mutabakat_telegram`, `strateji_verisi`, `hesap_adlari`; Telegram Bot API (`getUpdates` uzun yoklama).
**Yapılandırma (aynen).** `VARSAYILAN_DURUM="/var/lib/1l3a-paper/durum"`, `VARSAYILAN_CT="/var/lib/1l3a-ct-paper/durum/ct_konsensus"`, `VARSAYILAN_ADAY="/var/lib/1l3a-paper/durum/adaylar"`, `VARSAYILAN_CANLI="/var/lib/1l3a-canli/durum"`, `VARSAYILAN_CANLI_AYAR="/etc/1l3a-canli.json"`, `VARSAYILAN_GUNCELLE="/var/lib/1l3a-guncelle"`, `VARSAYILAN_KOK="/opt/1l3a"`, `DISK_ARALIK_SN=300`, `KALP_BAYAT_SN=600`. Ortam: `L3A_DURDUR_DOSYA`, `L3A_CT_DURUM_DIZIN`, `L3A_CANLI_DURUM_DIZIN`, `L3A_CANLI_AYAR`, `L3A_GUNCELLE_DIZIN`, `L3A_GERI_AL_DOSYA`, `L3A_ADAY_DURUM`, `L3A_HEPSINI_KAPAT_DOSYA`, `L3A_CIKIS_GERI_AL_DOSYA`, `L3A_DISK_KOK`, `TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_ID`.
**Testler.** `test_telegram_komut.py` (27), `test_telegram.py` (43), `test_mutabakat_telegram.py` (7).
**Kâğıtta etkin mi.** Evet (DURUM.md:26-27, kullanıcı onaylı 2026-11-19).
**Taşımada dikkat.** Komutları "bayrak/istek dosyası" ile süreçlere iletme ve iki adımlı onay kalıbı taşınır. 1L3A'ya özgü: hesap/ct/aday ayrımı, gizli hesabın hiçbir çıktıda adıyla görünmemesi ("gizli_hesaplar (N)"), `/kademe`/`/onayla` ölü komutları (taşımayın), TSİ saatleri. `/hepsini_kapat` kâğıt pozisyonları kapatır, canlı gerçek para pozisyonlarını kapatmaz: ML Otonom'da bu ayrımı açık yazın.

### e2) Günlük özet
**Dosya.** `motor/canli/gunluk_ozet.py` (413).
**Ne yapar.** Ortak günlük özet (şema `ortak.gunluk_ozet.v1`) + haftalık Telegram özeti; ikisi AYNI `topla` fonksiyonunu kullanır. `topla` SAF: yalnız durum dosyalarını OKUR (hesap yapmaz, uydurmaz; ölçülemeyen alan `null`, alan atlanmaz). Gün = TSİ günü. "Kasa" = 10 sanal paper hesabının toplamı (ct_konsensus HARİÇ); 6 görünür hesap kısa adıyla, 4 gizli hesap tek satır toplu ("gizli_hesaplar (4)"), ct_konsensus ayrı satır. Para USD ondalık (sayı), zaman ISO-8601 UTC; anahtar/e-posta/hesap numarası yazılmaz. `hesaplar[].islem` = hesabın toplam kapanan işlem sayısı.
**Giriş / çıkış.** `topla(durum_dizini, simdi, ct_dizin=None, set_yolu=None, env=None) -> dict`; `yaz(durum_dizini, simdi, ...) -> dict` (`gunluk_ozet_v1.json` atomik + `gunluk_ozet_gecmis.jsonl`'e günde BİR satır ekler/günceller); `gunluk_metin(o)`, `gecmis_oku`, `haftalik_ozet(satirlar, gun)`, `haftalik_metin(h, etiket=None)`, `haftalik_zamani(son_haftalik, simdi)`, `paper_kancasi(p, durum_dizini, simdi, gunluk_zamani, gonder, ...)` (paper tur döngüsünün tek çağrısı: saatlik güncelleme, 21:00 TSİ günlük özetle aynı anda yazım, Pazar 21:10 TSİ haftalık Telegram). Şema üst alanları: `SEMA_ALANLARI = ("sema","proje","uretim","gun","mod","kasa","islem","hesaplar","ogrenme","rejim","drift_uyari","limitler","saglik","notlar","bosluk_riski")`.
**Yapılandırma (aynen).** `SEMA="ortak.gunluk_ozet.v1"`, `DOSYA="gunluk_ozet_v1.json"`, `GECMIS="gunluk_ozet_gecmis.jsonl"`, `GECMIS_EN_COK=400`, `SAATLIK_SN=3600`, `HAFTALIK_SAAT_TSI=(21,10)` (Pazar), `CT_VARSAYILAN="/var/lib/1l3a-ct-paper/durum/ct_konsensus"`; günlük özet saati 21:00 TSİ ("21:00 itibarıyla").
**Bağımlılıklar.** pandas, stdlib; iç: `etiket_sonuc`, `hesap_adlari`, `durum` dosyaları.
**Testler.** `test_gunluk_ozet.py` (11), `test_etiket_sonuc.py`.
**Kâğıtta etkin mi.** Evet.
**Taşımada dikkat.** Şema adı `ortak.*` olduğu için başka projelerle (CT) paylaşılan ortak sözleşmedir: alan adlarını değiştirmeyin. Denetim A3: günün son saati günlük tarihçeye girmiyor (≤1 saat, ETKİSİZ). Gizli hesap toplulaştırması ve "10 hesap, ct hariç" kuralı 1L3A'ya özgü; ML Otonom'da hesap kavramı farklıysa `hesaplar` yapısını uyarlayın.

---

## KOŞULLU f) Canlı limitler (yapı)

**Dosya.** `motor/canli/borsa/canli_limitler.py` (200).
**Ne yapar.** Canlı (gerçek para/testnet) yürütücünün risk kuralının TEK kaynağı (kullanıcı kararı 2026-11-11). Kapsam yalnız canlı yürütücü; paper/backtest/araştırma `SERT_LIMITLER`'i kullanır (testler iki değer setinin ayrı kaldığını kontrol eder). Kasa = `min(borsa özsermayesi, tahsis)`. Miktar = `min(K·kasa/fiyat, 0.03·kasa/(stop mesafesi + birim maliyet))` + marj tavanı + toplam risk/brüt bütçesi, stepSize'a AŞAĞI; min tutar/min miktarın altında kalırsa işlem ATLANIR (asla yukarı yuvarlanmaz, olay `min_tutar_alti`). Izole marj. Kaldıraç: stop mesafesi <= %15 ise K (strateji kaldıracı 3/4/5, varsayılan 3), > %15 ise 2x (girişten önce sembole ayarlanır). Stop mesafesi > %25 ise işlem atlanır.
**Giriş / çıkış.** `CanliLimitleri` (frozen dataclass), `CANLI_LIMITLER`; `birim_maliyet(giris, stop, stop_kayma, taker)`, `kaldirac_sec(stop_uzaklik_oran, limitler, strateji_kaldirac=None) -> int`, `nominal_kat(limitler, strateji_kaldirac=None) -> Decimal`, `MiktarSonucu(qty, neden, ayrinti, kaldirac, baglayan, ham)` (`baglayan`: kayip | nominal | marj | toplam_risk | brut), `miktar_hesapla(*, kasa, yon, giris, stop, stop_kayma, taker, adim, min_qty=0, min_tutar=0, max_qty=None, diger_brut=0, diger_stop_riski=0, kaldirac_ust=None, limitler, strateji_kaldirac=None)`, `limit_ihlalleri(...) -> list[str]` (yuvarlanmış miktarı yeniden doğrular), `gunluk_kill_guncelle(d, kasa, gun, limitler, tahsis=None) -> list`, `hesap_kill_guncelle(h, kasalar, limitler, tahsisler=None) -> Optional[str]`. Saf fonksiyonlar (Decimal), borsa filtreleri parametre.
**Yapılandırma (aynen; 1L3A kararı, yeniden kararlaştırılmalı).**
```
islem_basi_max_kayip_oran   = 0.03   # stopta (maliyet dahil) kasanın %3'ü
islem_basi_max_marj_oran    = 0.50   # işlem başı marj / kasa
islem_basi_max_nominal_kat  = 3.0    # varsayılan kaldıraçta; K ile ölçeklenir
toplam_stop_riski_oran      = 0.06   # tüm açık pozisyonların stopa kadar toplam riski / kasa
brut_nominal_kat            = 3.0    # K ile ölçeklenir
gunluk_max_kayip_oran       = 0.05   # UTC günü, gün başı kasadan (önceden 0.06)
strateji_kill_oran          = 0.30   # strateji kasası zirveden
hesap_kill_oran             = 0.20   # tüm stratejilerin kasa toplamı ortak zirveden
stop_yakin_siniri_oran      = 0.15
kaldirac_yakin              = 3
izinli_kaldiraclar          = (3, 4, 5)
kaldirac_uzak               = 2
stop_uzaklik_maks_oran      = 0.25
TOL = 1e-9 (Decimal)
```
Not: marj tavanı kasa x %50 olduğundan fiili nominal 0.5·K (3x -> 1.5x kasa, 5x -> 2.5x kasa, uzak stopta 1.0x kasa).
**Bağımlılıklar.** stdlib Decimal.
**Testler.** `test_canli_limitler.py` (28), `test_canli_islem_risk.py` (20), `test_canli_borsa.py`.
**Kâğıtta etkin mi.** Yalnız canlı.
**Taşımada dikkat.** Değerler 1L3A kullanıcı kararlarıdır (%3 işlem başı; kâğıt %1 ile bile farklı), ML Otonom yeniden kararlaştırmalı. Taşınacak yapı: tek frozen sınıf, saf Decimal fonksiyonlar, "yuvarlama sonrası yeniden doğrula", kill durumları için ayrı `*_guncelle` fonksiyonları. Denetim "kaldıraç tavanı 5 vs 3 gösterimi" şüphesi ve 5x'in test edilmiş sınırın dışında olduğu uyarısı geçerli. Kâğıt/canlı iki ayrı limit kümesinin (SERT_LIMITLER vs CANLI_LIMITLER) bulunması tutarsızlık riskidir; ML Otonom tek kaynak yapabilir.

---

## Taşınmayacaklar

- **Kâğıt (paper) motoru, backtest ve portföy motoru** (`paper_motor.py`, `paper.py` çekirdek, `motor/backtest/`, `motor/portfoy/`): 1L3A strateji/kasa/grup yapısına gömülü; ML Otonom'un kendi motoru var, yalnız bölüm 1'deki limit kancaları örnek alınır.
- **Canlı yürütücü + köprü** (`canli_yurutucu.py`, `motor_kopru.py`, `calistir.py`): paper->niyet mimarisine bağlı ve açık E2/E3/D1 bulguları var; yalnız bölüm d'deki fikirler alınır.
- **Pano + analitik** (`pano.py` 2300 satır, `pano_worker.js`, `pano_acik_worker.js`, karne/koni/kıyas/korelasyon/koç/yoğunlaşma modülleri): 1L3A'ya özgü görsel katman; "motor hesaplar, pano gösterir" ilkesi (bölüm 6b) yeterli.
- **Çıkış karşı-olgusu** (`cikis_karsi_olgu.py`, 808 satır; 8 alternatif çıkış yeniden oynatma, otomatik uygulama + geri alma): ön kayıt ölçütleri 1L3A stratejilerine göre, yeniden oynatma önyargısı şüphesi, canlıda "kendini değiştiren kod" kararıyla çelişiyor (D1).
- **Alınsaydı gevşetme** (`alinsaydi_gevsetme.py`): filtre gevşetmeyi otomatik uygular, B1 bulgusu (kaçan fırsat) ve mutasyon %71,5; ML Otonom'da otomatik gevşetme riski kullanıcı kararı gerektirir.
- **ML filtre/eğitim** (`motor/ortak_ogrenme/filtre.py` ve adaptördeki eğitim kısmı): `MIN_EGITIM=10` aşırı uyum riski, ML Otonom'un kendi ML hattı var; yalnız ders/fren/drift adaptörü (bölüm a) koşullu taşınır.
- **Haber etiketi** (`haber_etiketi.py`): alt-dize eşleşme hatası (B5), eski önbellek (B6), RSS kaynaklarına bağlı; yalnız veri toplama etiketi olarak istenirse yeniden yazılmalı.
- **CT konsensüs** (`ct_kadro.py`, `ct_paper.py`): başka bir projenin (CT) trader verisine bağımlı, `MAX_POZ` hatası (E1), ML Otonom ile ilgisi yok.
- **Aday paper** (`aday_paper.py`, `aday_paper_listesi.json`): 1L3A'nın aday strateji süreç hattı; kart/lookahead kapısı fikri bölüm 2f'de.
- **Etiket kuralları** (`etiket_kurallari.py`): etiketlere göre girişi atlatan kural motoru; etiket toplama (bölüm c) alınır, kural uygulaması alınmaz (kâr katkısı gösterilmedi, mutasyon %66,4).
- **Boşluk maruziyeti** (`bosluk_maruziyet.py`, `araclar/bosluk_olcum.py`): hisse/emtia hafta sonu boşluk uyarısı, yalnız bildirim; D4/D5 bulguları; yalnız TradFi evreni için anlamlı.
- **Seans takvimi** (`paper_takvim.py`, `seans_maliyet.py`, TradFi `ESLEME`, DK_ sembolleri, BIST damga/BSMV): hisse/emtia ve Binance TradFi perpetual'e özgü; ML Otonom yalnız kripto ise gereksiz.
