# CT/ML ayrılığı — C1 kolunun ve tüm CT bağlantısının kaldırılması (20 Kasım 2026)

**Kullanıcı kararı (kesin):** ML ve CT tamamen ayrıdır. CT'den gelen hiçbir şey ML'i (karar, özellik, etiket, rapor, panel) etkilemez.
Eski belgeler `docs/motor/c1-ct-kadro-spec.md` (C1 kolu) ve CT bölümleri **kaldırılmıştır**; bu belge tek kayıttır.

## 1. Kaldırılanlar (kod)
- C1 kolu: `strategies/arms/c1.py`, `config/engine.paper.json` `arms` içinde `C1@1h`, `C1@4h`, `arm_max_positions` içinde `"C1"`.
  Başka hiçbir risk sayısı değişmedi (max_positions 24, açık risk 0,24, aynı yön 0,16, kümeler, günlük 0,08, kaldıraç, sert limitler).
- CT okuma: `scripts/ct_kadro_cek.py`, `deploy/trader-ct-kadro.service|.timer`, `trader_core/ct_kadro.py`, motorun CT okuyucusu.
- Kapı: `_ct_blok`/`_ct_yon` ve `features.ct_*` (ct_long, ct_short, ct_baskinlik, ct_net_yon, ct_yon, ct_yas_dk, ct_durum) artık yazılmaz.
- ML: `f_ct_trader_sayisi` ve her `f_ct_*` özelliği kaldırıldı; `ml_live_v2.setup_feature_dict` eski kayıtlardaki `ct_*` alanlarını
  özellik yapmaz (eğitim de puanlama da aynı fonksiyon). Eski model paketi `f_ct_*` bekliyorsa eksik özellik NaN olur, modelin `fill`
  değeri doldurur; **giriş engellenmez**.
- Etiket kuralı "kalabalık yönü" tamamen kaldırıldı (kod, config bloğu, gate'teki C1 istisnası). `rejim` ve `duygu` kuralları aynen.
  `etiket_kalabalik` kodu yalnız defter şeması ve eski karar satırlarının okunur adı için kalır (şema CHECK'i değişmez).
- Sağlık: `ct_kadro_bayat` uyarısı. Telegram: "Kadro uzlaşısı" adı. Strateji verisi: "CT bilgisi" bölümü. Tutarlılık: C1 için `veri` özel durumu.
- `drift_monitor` içindeki `C1` bir **kural kimliğidir** (CUSUM; "C1" = 5. kural) ve bu kolla ilgisizdir; dokunulmadı.

## 2. Açık C1 pozisyonlarının zorla kapatılması
`Engine.start()` içinde, mutabakattan sonra tek seferlik ve idempotent adım `_kaldirilan_kollari_kapat` (`KALDIRILAN_KOLLAR = ("C1",)`):
- Kurulumu `C1` olan **açık** (`open`) pozisyonlar stop/hedef beklenmeden piyasadan kapatılır; normal `_submit_exit` yolu kullanılır
  (kâğıtta kâğıt broker piyasa çıkışı; testnet/canlıda yalnız reduce-only çıkış, ban penceresi ve poll dahil). Gerçekleşen K/Z, komisyon,
  kayma her zamanki gibi yazılır. Çıkış nedeni defterin kabul ettiği `force_exit`; günlükte `kol_kaldirildi`.
- İkinci çalışma: pozisyon `closing`/kapalı olduğundan hiçbir şey yapılmaz. Çıkış gönderilemezse veya pozisyon henüz `opening` ise
  **CRIT** günlük + sayaç (`kaldirilan_kol_hata`, `kaldirilan_kol_bekliyor`); sessiz bırakılmaz, sonraki başlangıçta yeniden denenir.
- Yeni C1 girişi zaten mümkün değildir (kol yok).

## 3. Kurulum (install.sh)
`trader-ct-kadro.timer/.service` sunucuda durdurulur, devre dışı bırakılır ve birim dosyaları silinir (her kurulumda, idempotent).
`var/c1_temizle.done` yoksa `scripts/c1_temizle.py` bir kez çalışır; işaret yalnız dosya adımları hatasız bitince yazılır.

## 4. Veri temizliği (scripts/c1_temizle.py) — dosya düzeyi
Silinen/ayıklanan: `var/ct/`; `…/models/ortak_filtre/aile_C1.json` ve `eski_kol/` altındaki C1 dosyaları; `paper_models.csv` C1 satırları;
`arms_off.json` C1 anahtarları; `var/durum/etiket_kurallari_v1.json` içinden `etiket_kalabalik`; sağlık durum dosyasından `ct_kadro|bayat`.
Yeniden üretilebilir çıktılar (özet, strateji verisi, mutabakat) silinmez: defter değişmediği sürece yeniden üretildiklerinde yine C1 içerir;
bu yüzden temizlenmeleri bölüm 5'teki karara bağlıdır.

## 5. AÇIK SORUN: defter satırlarının silinmesi (karar bekliyor, YAPILMADI)
Kullanıcı kararı C1 geçmişinin defterden de silinmesini ve kasanın "C1 hiç olmamış gibi" yeniden hesaplanmasını ister.
Bu, defterin bütünlük mekanizmasıyla çelişir; görev kuralı gereği mekanizma devre dışı bırakılmadı, çelişki raporlandı:
1. `trade_entries`, `trade_exits`, `decision_events`, `equity_marks`, `shadow_decisions` vb. tablolarda `trg_<tablo>_no_update/no_delete`
   tetikleyicileri (`RAISE(ABORT,'append-only')`) vardır. `Ledger._verify` her açılışta bu tetikleyicilerin tamamını arar; eksikse
   `LedgerSchemaError` ile motor açılmaz (fail-closed). `trader-bakim` defterlere bilerek dokunmaz.
   (`tests/test_c1_temizle.py::test_defter_yalnizca_ekleme_tetikleyicisi_silmeyi_reddeder` bunu belgeler.)
2. Kasa/mutabakat işlem toplamlarından türetilir: `kasa = wallet_start + Σ realized_pnl` (`mutabakat.kontrol_kasa`, `kontrol_bagimsiz_toplam`),
   paper broker cüzdanı `state.sqlite` `broker_snapshot` içindedir. C1 satırları silinirse cüzdan ve türevleri (gün başı özsermaye
   `day_start:*`, tepe özsermaye/kademe durumu `risk_ladder`, `equity_marks`, günlük özet sanal kasası) birlikte yeniden hesaplanmalıdır.
3. C1 gerçekleşen K/Z'si bu hesapta **çıkarılacaktır** (kullanıcı güncellemesi: bakiye de "C1 hiç olmamış gibi"); nötr taşıma kaydı yok.
   Betik bugün yalnız salt okunur rapor üretir: `c1_karar`, `c1_islem`, `c1_kapanan`, `c1_net_kz`, `c1_giris_komisyon`,
   `c1_cikis_komisyon`, `c1_fonlama` (sunucuda `--defter` ile).
Önerilen yetkili yol (onay gerekir): şema sürümü artıran, defterin kendi göç mekanizmasıyla (göçler zaten tetikleyicileri bırakıp
yeniden kurar) çalışan tek seferlik "C1 kaldırma göçü"; `_verify` tetikleyici kontrolü aynen kalır. Göç, yedeği
`var/yedek/ledger-<zaman>.sqlite` olarak alır (yedek C1 içerir), C1'e ait `decision_events`/`trade_entries`/`trade_exits`/`trade_notes`/
`equity_marks`/`shadow_decisions` satırlarını siler, `state.sqlite` `gecikme:<trade_id>` anahtarlarını ve `broker_snapshot` cüzdanını
(`wallet -= Σ C1 realized_pnl`, açık C1 marjı zaten §2 ile kapandı) düzeltir, `day_start`/tepe özsermaye/kademe durumunu yeniden kurar
ve ardından mutabakat/tutarlılık/özet çıktıları yeniden üretilir.

## 6. Mühür / eşdeğerlik
Holdout mührü (`research/holdout/muhur.json`) yalnız `var/history` holdout dilimi baytlarının özetidir; C1 veri içermez (C1 19 Kasım 2026'da
başladı, holdout 2026-05-01..2026-11-01). Mühür/özetler değişmedi. `research/holdout/pbo_ozet*.json`, `research/arm_series/meta.json`
ve `docs/ml/pbo-raporu.md` içindeki "C1 için seri yok" dışlama notları kaldırıldı (mühür girdisi değildir).
