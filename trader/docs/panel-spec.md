# Panel (pano) spesifikasyonu v1 — salt okunur, tek süreç

Kaynak: 1L3A panosu (`/home/user/sselimgenc-oss/1l3a-proje`, **güvenilmez kopya: yalnız okunur, hiçbir şey kurulmaz/çalıştırılmaz**). Analiz: `otonom-trading-arastirma/research_notes/kullanici-projeleri/1l3a_analiz.md` §2, `1l3a_motor_derin_inceleme.md`. Bu belge kod ve commit içermez.

## 1. Değişmez kurallar

1. Yalnız `127.0.0.1` dinler (`0.0.0.0`/`::` yasak; başlangıçta bind adresi doğrulanır, farklıysa süreç çıkar). Erişim SSH tüneliyle: `ssh -L 8080:127.0.0.1:8080 <kullanici>@<droplet>`.
2. Panelde API anahtarı, Telegram token'ı, Binance anahtarı **yok**: `EnvironmentFile` yok, süreç bu değişkenleri görmez. `trader-telegram.env` vb. okunmaz.
3. v1 salt okunur: yalnız `GET`/`HEAD`; `POST/PUT/DELETE` → 405. İşlem, kill, onay/ret yok; bunlar Telegram'dan (`/onayla`, kill dosyası) yapılır. Panel kill dosyasını **okur** ama yazmaz.
4. Çalışma anında dış ağ yok: CDN, font, analitik, `fetch` ile dış URL yasak. Her varlık depoda (vendored) ve `Content-Security-Policy: default-src 'self'` ile zorlanır. Panel dışarı bağlantı da açmaz.
5. Bellek tavanı ≈ 60 MB (systemd `MemoryMax=64M`), 2 GB paylaşımlı droplet; botları/sağlık/ders süreçlerini aç bırakmaz (`Nice=10`).
6. Tüm okumalar `mode=ro` SQLite URI veya salt okunur dosya; panel hiçbir veri dosyasına yazmaz, ikinci yazar olmaz (defter-spec §9).
7. Panel yeni hesap yapmaz (1L3A ilkesi korunur): sayılar motor/defter/bütçe/ders/sağlık çıktısından aynen gösterilir; yalnız biçimleme, sıralama, ilk-N kesme, zaman farkı (bayatlık) ve çizim ölçeklemesi yapılır. Okunamayan kaynak "veri yok: <kod>" gösterilir, değer uydurulmaz (fail-closed gösterim).

## 2. 1L3A'dan neyin alınacağı (kaynak yol: `1l3a-proje/` altında)

1L3A panosu = `motor/canli/pano.py` (2065 satır, tek dosyalık statik HTML üreticisi; CSS 172–328, JS 329–~388) + 15 JSON/JSONL durum dosyası (`motor/canli/durum.py::DOSYALAR/EK_DOSYALAR`, sözleşme `motor/canli/DURUM_SOZLESMESI.md`). Üretici o JSON şemasına sıkı bağlı; bizim veri (status.json + SQLite defter + bütçe + ders + sağlık) farklı olduğundan **üretici doğrudan monte edilmez**. Karar tablosu:

| Parça | 1L3A kaynağı | Karar | Not |
|---|---|---|---|
| CSS (koyu/açık tema, kutu/tablo/chip/uyarı bandı) | `pano.py` `CSS` (satır 172–328) | **Monte (kopya, tek dosya `static/panel.css`)** | Dış font/URL yok (doğrulandı: `pano.py`'de `http(s)://` yok). Kopyadan önce satır satır okunur. |
| JS: tema düğmesi, yenile/yazdır, bayatlık bandı (`data-zaman`/`data-esik-dk`), tablo sıralama, süzgeç | `pano.py` `JS` (329–) | **Monte (uyarlama)** | `fetch('/api/…')` ile kısmi yenileme eklenir (§5). Bağımlılık yok. |
| Sekme iskeleti (radyo+label, CSS-yalnız sekmeler; JS'siz çalışır) | `html_olustur` (1993–2035), `SEKMELER` | **Fikir, yeniden yaz** | Bizim sekmeler §3. |
| Kutu/tablo/kullanım çubuğu yardımcıları | `_kutu`, `_tablo`, `_kullanim_cubugu`, `_p`, `_h`(escape) (399–520) | **Fikir, yeniden yaz** (JS'te; her metin `textContent` ile, `innerHTML` yok) | Python string HTML yerine JSON+JS render: sunucu küçük kalır. |
| Özsermaye eğrisi / düşüş grafiği (satır içi SVG) | `_egri`, `_dusus_grafigi`, `_mini_egri`, `_eksen` (528–720) | **Fikir** (kendi SVG'miz, ~60 satır JS) | Chart.js alınmaz (vendored 200 KB gereksiz; `arsiv/sg-pano/vendor/` kullanılmaz). |
| Kill-switch/uyarı şeridi (üstte, her sekmede görünür), `uyarilar()` | `pano.py` 60–104, `_serit` (817) | **Fikir** | Bizim uyarı kaynağı health raporu + status. |
| Açık pozisyon tablosu + stop riski | `_poz_tablosu`, `_stop_riski` (1275, 1380) | **Fikir** | Veri: `status.json.open_positions` (+ defter açık işlemler). |
| İşlem satırı çekmecesi (neden/MFE-MAE) | `_cekmece*` (1896–1940) | **Fikir (v1.1)** | Bizde defter karar olayı `features`/`skip_reason` var; v1'de yalnız satır, çekmece sonra. |
| Sağlık/kalp atışı kutuları | `_sekme_saglik`, `_kalp_atisi_kutulari` (1681–1720) | **Fikir** | Bizim kaynak: `health` raporu §3. |
| Dersler / koç / öneri kartı | `_dersler_html`, `_koc_html` (1733–1866) | **Fikir** | Veri: `lesson.py` deposu (§3). |
| Karne radarı, koni (Monte Carlo), kıyas, korelasyon, yoğunlaşma, aylık rapor | `_karne*`, `_koni_html`, `_kiyas_html`, `_korelasyon_html`, `_yogunlasma_html`, `_sekme_rapor` | **Alınmaz (v1)** | Bizde bu veriyi üreten motor yok; strateji sayısı az (learner+twin). Gerekirse v2. |
| Telegram metni üreticisi | `telegram_metni`, `terminal_ozet` (124–388) | **Alınmaz** | Bizde `trader_core/telegram.py` var. |
| Yerel sunum | `deploy/1l3a-pano-sunucu.service` (`http.server 8080 --bind 127.0.0.1`) | **Fikir (aynı model)**, kendi unit'imiz | Statik `http.server` yerine küçük API sunucusu gerekir (§4). |
| Üretim zamanlayıcısı (5 dk `oneshot`) | `deploy/1l3a-pano.{service,timer}` | **Alınmaz** | Biz isteğe bağlı canlı okuruz; zamanlayıcı yok. |
| Cloudflare Worker, Basic Auth, `pano_yayinla.sh`, `PANO_KILITSIZ` | `deploy/pano_worker.js`, `pano_yayinla.sh` | **Alınmaz (v1)** | Dış yayın kapsam dışı (kural 1,2). `PANO_KILITSIZ` yolu kesinlikle yok. Telefon erişimi SSH tüneliyle. |
| `atomik_yaz_json` | `motor/canli/durum.py` 94–112 | **Gerekmez** | Panel yazmaz; bizim `trader_engine/fileio.py` zaten var. |
| Eski paneller | `arsiv/sg-pano`, `arsiv/strateji-test-pano`, `arsiv/swing-sg/…/panel`, `arsiv/codex-algo/dashboard.py` | **Alınmaz** | Dış API/GitHub raw'dan veri çeker (kural 4'e aykırı); yalnız ekran düzeni fikri. |

Özet: **doğrudan monte = CSS + istemci JS çekirdeği (tema, bayatlık bandı, sıralama)**; geri kalan tüm ekranlar fikir olarak alınıp bizim veri kaynaklarımıza göre yeniden yazılır. `pano.py` hiçbir hâliyle içe aktarılmaz. Kopyalanan her dosyanın başına kaynak yol + tarih yorumu konur, `THIRD_PARTY_NOTICES.md`'ye eklenir (1L3A kullanıcının kendi projesi; yine de not düşülür).

## 3. Ekranlar ve veri eşlemesi

Bot adları: `learner`, `twin`. Yol ayarları `config/panel.json` (yeni, §6); telegram `TelegramConfig` ile aynı alan adları (`status_path`, `ledger_path`, `twin_ledger_path`, `budget_config`, `lesson_store`, `health_state`, `kill_file`).

| Sekme / widget | Kaynak (salt okunur) | Alanlar / çağrı | Not |
|---|---|---|---|
| **Üst şerit** (her sekmede): kill, kapı, bayatlık | `status.json` (her bot) | `kill`, `kill_state`, `gate.code`, `entries_open`, `entries_blocked_reason`, `loop_at`, `mode`, `dry_run` | `now − loop_at > 120 sn` → bayat bandı (05 §8.2 `health_run` eşlemesi ile aynı eşik). Dosya yok/bozuk → kırmızı "veri yok". |
| **Özet**: equity, gün başı equity, günlük zarar/bütçe %5, açık poz sayısı, sürüm | `status.json` | `equity`, `day_start_equity`, `wallet`, `counters`, `param_version_id`, `strategy`, `trigger_tf` | Günlük bütçe çubuğu: `0.05×day_start_equity` (telegram `section_ledger` ile aynı formül; paylaşılan sabit). |
| **Özet**: learner ↔ twin yan yana | iki `status.json` + iki defter | gün PnL/R, kapanan, kazanan/kaybeden, fark | Telegram `section_ledger` satırının yapısal hâli. |
| **Pozisyonlar** | `status.json.open_positions` + `Ledger.list_open_trades()` | `pair, side, qty, entry_price, stop`; defterden `leverage`, giriş zamanı | İkisi uyuşmazsa uyarı rozeti (mutabakat göstergesi). |
| **İşlemler**: son kapanan işlemler, süzgeç (bot/sembol/yön) | `Ledger._trades(...)` kapalı; ya da kamusal sorgu varsa o | `exit_ts, pair, side, realized_pnl, r_multiple, fee*` | Sayfalama: son 200. "Bugün" sınırı TSİ (`_istanbul_day_bounds_utc`). |
| **İşlemler**: karar olayları (girdi/atlanan, `skip_reason`) | `Ledger.list_decisions(since_ts, until_ts)` | `final_action, skip_reason, veto_status, risk_allowed` | 1L3A "reddedilen" kartı fikri (stop-uzaklık filtresi sessiz engelliyor dersi, analiz §180-182): atlama nedenleri sayılarla görünür. |
| **Eğri**: günlük kümülatif R / PnL (SVG) | Defter kapanan işlemler | `exit_ts`, `realized_pnl`, `r_multiple` | Hesap = toplama; "yeni hesap" sayılmaz, ama kaynak ve formül ipucuna yazılır. |
| **Bütçe** | `budget.BudgetGuard(cfg).status()` | `month_used_usd/monthly_cap_usd/month_state`, `services[k].used_usd/cap_usd/state`, `prices_verified`, `config_ok/store_ok` | `telegram.section_budget` içindeki yapılandırma çözümü (db yolu göreli → mutlak) ortak yardımcıya taşınır. |
| **Ders**: bekleyen öneriler, gölge dönem, son çalışma | `LessonStore(path, read_only=True, create=False)` | `open_requests()`, `get_state("shadow_start_day"/"shadow_end_day")`, `lesson_runs` son satır + `run_events` | Öneri kartında "Onay Telegram'dan: `/onayla <id>`" yazar; düğme yok. Defter `list_proposals(status=…, limit=…)` de okunur. |
| **Sağlık** | `health` durum dosyası (`/var/lib/trader-health/state.json`, saglik-spec §5.3) + her botun defterinden son yazma zamanı (§4 `last_write_at`) | `last_overall`, `last_run_at`, `fingerprints` (açık uyarılar), `restart_counts` | Panel `health.evaluate` çalıştırmaz (ölçüm toplamak `scripts/health_run.py` işi); yalnız son raporu/durumu gösterir. `last_run_at` eskiyse "sağlık denetimi çalışmıyor" uyarısı. |
| **Süreç/kaynak** (küçük kutu) | `/proc/meminfo`, `os.statvfs` | boş bellek, swap, disk | Sağlık spec'indeki eşiklerle renk; ek ölçüm yok. |

Telegram yeniden kullanımı: `section_ledger/budget/lesson` **metin** döndürür (panele uygun değil); bu yüzden altındaki yapısal yardımcılar (`_ledger_day`, `_istanbul_day_bounds_utc`, bütçe yapılandırma çözümü, ders deposu okuma) `trader_core`'da küçük bir `panel_data.py` altında paylaşılır ve **telegram.py bu dosyayı kullanacak şekilde sonradan** (ayrı iş, davranış değişmeden) yeniden düzenlenir; v1'de panel, `telegram` modülünün özel (`_`) adlarını doğrudan çağırmaz, kopya yerine ince saran fonksiyon yazılır ve eşdeğerlik testi (§8) eklenir. Telegram'ın `SectionError` kodları ("defter_yok", "depo_okunamadi"…) panelde "veri yok: <kod>" olarak aynen gösterilir.

## 4. Süreç düzeni

- **Tek Python süreci**, yalnız standart kütüphane: `http.server.ThreadingHTTPServer` (en çok 8 iş parçacığı), `sqlite3` `mode=ro`, `json`. Starlette/uvicorn bu makinede kurulu ama droplet'te garanti değil ve ~+25 MB bellek getirir; v1 **kullanmaz**. Bağımlılık eklenmez; `pyproject.toml`'a dokunulmaz.
- Dosyalar: `src/trader_panel/{server.py, data.py, __main__.py}`, `src/trader_panel/static/{index.html, panel.css, panel.js}`, `config/panel.json`, `deploy/trader-panel.service`, `tests/test_panel_*.py`. Derleme/bundle yok; statik dosyalar belleğe bir kez okunur.
- Uç noktalar (hepsi `GET`, JSON, `Cache-Control: no-store`): `/` ve `/static/*`; `/api/status` (iki bot status + kill + bayatlık), `/api/ledger?bot=&day=` (kapanan/açık/karar özeti), `/api/curve?bot=`, `/api/budget`, `/api/lesson`, `/api/health`, `/api/system`, `/healthz` (süreç canlı). Bilinmeyen yol 404; yol gezintisi (`..`) yok (statik harita sabit liste).
- Her istekte kaynak başına bağlantı açılıp kapatılır (`sqlite3` `timeout=2`); sonuç 5 sn bellek önbelleği (aynı anda çok sekme DB'yi yormasın). Kaynak okuma hatası o uç noktada `{"ok":false,"code":"..."}` döner, süreç çökmez. İstek başına üst süre 3 sn; yanıt boyutu üst sınırı (≈ 512 KB; işlem listeleri sayfalı).
- **Bellek bütçesi**: CPython + dilimler ≈ 25–35 MB; önbellek ≲ 5 MB; hedef RSS ≤ 45 MB, `MemoryMax=64M`. Pandas/numpy import edilmez (`08-no-framework-guard.md` ile uyumlu).
- systemd (`deploy/trader-panel.service`, özet): `Type=simple`, `User=trader` (botlarla aynı, yalnız okuma izinli grup), `ExecStart=<venv>/bin/python -m trader_panel --config config/panel.json`, `Restart=on-failure`, `RestartSec=5`, `MemoryMax=64M`, `Nice=10`, `NoNewPrivileges=true`, `PrivateTmp=true`, `ProtectSystem=strict`, `ProtectHome=true`, `ReadOnlyPaths=` veri dizinleri, `RestrictAddressFamilies=AF_INET AF_UNIX`, `IPAddressAllow=localhost` + `IPAddressDeny=any`, `EnvironmentFile` yok, `After=` botlardan bağımsız (botlar kapalıyken de açılır, "veri yok" gösterir).

## 5. Yenileme modeli

- Sayfa bir kez yüklenir; `panel.js` her **10 sn** görünür sekmenin uç noktasını `fetch` eder (üst şerit her 10 sn; diğerleri sekme açılınca + 30 sn). Sekme gizliyken (`document.hidden`) yenileme durur. Elle "Yenile" düğmesi.
- Her yanıt `generated_at` taşır; istemci kendi saatine güvenmez: bayatlık = sunucu `now` − kaynağın `loop_at`/`probed_at`. Sunucuya ulaşılamazsa üstte kırmızı "panel bağlantısı yok" bandı (1L3A bayat bandı mantığı).
- Saatler TSİ gösterilir, API UTC `...Z` döner (defter/status biçimi).
- Sunucu tarafı olay akışı (SSE/WebSocket) yok: iş parçacığı/bellek maliyeti gereksiz.

## 6. Güvenlik

- Bind doğrulaması (§1.1); `config/panel.json` yalnız `host` (sabit `127.0.0.1`, değiştirilebilir değil), `port` (öntanımlı 8080), veri yolları. Yollar doğrulanır; yazma izni olan dizin gösterilirse uyarı.
- Kimlik doğrulama v1'de yok (tünel + loopback = erişim kontrolü; 1L3A yerel modeliyle aynı). Soru 3'e bakın.
- Yanıt başlıkları: `Content-Security-Policy: default-src 'self'; connect-src 'self'; img-src 'self' data:; frame-ancestors 'none'`, `X-Content-Type-Options: nosniff`, `Referrer-Policy: no-referrer`, `Cache-Control: no-store`. `Host` başlığı `127.0.0.1:<port>`/`localhost:<port>` dışındaysa 400 (DNS rebinding savunması).
- İstemcide veri `textContent` ile basılır (XSS yok; defter/ders alanlarındaki serbest metin `telegram.neutralize` gibi düz metin). Log'lara sır/yol ayrıntısı yazılmaz; `Authorization` gibi başlık yok zaten.
- Hata mesajlarında yığın izi yok; yalnız kısa kod (`defter_yok`, `depo_okunamadi`, `status_bozuk`).
- Panel hesabı veri dosyalarına yalnız okuma izni taşır; kill dosyası dizini dahil yazma izni yok.

## 7. Dağıtım

`deploy/trader-panel.service` + `deploy/trader-panel.env.example` **yok** (env gerekmiyor). Kurulum adımları belgesi: unit kopyala → `daemon-reload` → `enable --now`; SSH tüneli komutu; `journalctl -u trader-panel`. Geri alma: `systemctl disable --now trader-panel` (başka hiçbir bileşene bağımlılık yok).

## 8. Test planı (tests/test_panel_*.py, `pytest`, ağ yok)

1. **Değişmezler**: sunucu `0.0.0.0` bind isteğine açılmaz; `POST/PUT/DELETE` → 405; `Host` sahte → 400; bilinmeyen/`..` yol → 404; yanıt başlıkları (CSP vb.) var.
2. **Ağ yasağı**: `static/*` içinde `http://`, `https://`, `//cdn`, `@import url(`, `<link href=http` taraması (regex testi); CSP `default-src 'self'`.
3. **Salt okunur**: geçici defter/bütçe/ders deposu fikstürü ile uç nokta çağrıları sonrası dosyaların sha256 ve `mtime` değeri değişmemiş; `mode=ro` ile yazma girişimi `OperationalError` (veri katmanında doğrudan test).
4. **Veri eşlemesi**: örnek `status.json` (05 §8.2 örneği) → `/api/status` alanları birebir; defter fikstüründe bilinen işlemler → `/api/ledger` PnL/R toplamı = `telegram._sum` sonucu (eşdeğerlik testi, `section_ledger` metnindeki sayılarla karşılaştırma); bütçe `status()` ↔ `/api/budget`; ders `open_requests` ↔ `/api/lesson`.
5. **Fail-closed gösterim**: status.json yok/bozuk/eski, defter yok, depo kilitli → `{"ok":false,"code":…}` ve süreç ayakta; `loop_at` 121 sn eski → bayat işareti, 120 sn → yok.
6. **Telegram eşdeğerliği**: aynı fikstürde paylaşılan yardımcılar `telegram.section_*` ile aynı sayıları verir (yeniden düzenleme sonrası da).
7. **Bellek/yük**: 200 işlemli defter + 8 eşzamanlı istemci × 60 sn döngüsü; RSS ≤ 60 MB (`resource`/`/proc/self/status`); 3 sn zaman aşımı sınanır.
8. **Kaynak tarama**: `trader_panel` hiçbir sır değişkeni okumaz (`TELEGRAM_*`, `*_KEY`, `*_TOKEN` için `os.environ` erişimi yok — statik grep testi); `trader_core.telegram`'dan yalnız sabitleri/yardımcıları içe aktarır, istemci/gönderici sınıflarını değil.
9. **İstemci JS** (v1.1): Node varsa render fonksiyonları için küçük birim test (XSS dizgisi `<img onerror>` düz metin kalır); yoksa tarayıcıda elle kontrol listesi: 4 sekme, tema, bayat bandı, JS kapalıyken ilk sayfa.
10. **systemd**: `systemd-analyze verify deploy/trader-panel.service`; droplet'te `ss -ltnp` yalnız `127.0.0.1:8080`, `curl` dışarıdan reddedilir.

## 9. Mentora açık sorular

1. 1L3A `pano.py` üreticisi doğrudan monte edilmeyip yalnız CSS/JS çekirdeği alınıyor, kalan ekranlar yeniden yazılıyor. Uygun mu, yoksa 1L3A'nın karne/koni/kıyas/aylık rapor sekmeleri (bizde veri kaynağı yok) v2'de zorunlu mu?
2. Bağımlılık: stdlib `ThreadingHTTPServer` ile devam edelim mi (daha az bellek, sade) yoksa droplet'e Starlette+uvicorn kurulumu kabul mü (SSE ve daha rahat yönlendirme)?
3. Kimlik doğrulama: SSH tüneli + loopback yeterli mi, yoksa ek parola (Basic Auth, panelde sır tutmak kuralıyla çelişir; hash'lenmiş parola yapılandırması gerekir) istenir mi? Telefondan erişim yalnız SSH uygulaması üzerinden olabilir mi?
4. Telegram bölüm üreticilerinin yapısal yardımcılara ayrılması (`panel_data.py` + `telegram.py` yeniden düzenleme) şimdi mi, panel v1 sonrası mı yapılsın (telegram testlerini bozmama riski)?
5. Defter API'sinin kamusal sorgu yüzeyi: panelin `Ledger._trades` gibi özel adı çağırması yerine `list_closed_trades(since, until)` gibi kamusal bir salt okunur metot eklensin mi (`ledger.py` bu iş paketinin dışında)?
6. Sağlık durumu: panel yalnız `state.json`'u okuyor; "bot defteri yazabiliyor mu" için `health_probes.probed_at` ham okunsun mu, yoksa `gate_status_readonly()` (saglik-spec §12 Soru 2) beklensin mi?
7. Günlük bütçe çubuğu ve diğer sabitler (%5, 120 sn bayatlık) panelde sabit kodlanmak yerine `risk.py`/`engine.*.json` yapılandırmasından mı okunsun (tek doğruluk kaynağı)?
8. Gizli/kapalı süre için "panel açık bırakılırsa tarayıcı 10 sn'de bir çeker" yükü kabul mü; yoksa yenileme varsayılan 30 sn mi olsun?
