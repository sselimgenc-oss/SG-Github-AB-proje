# Mimari taslak — İlk sürüm (MVP)

> Güncellendi: 16 Kasım 2026 (mentor doğrulaması işlendi)

Tarih: 15 Kasım 2026 · Durum: **taslak, kullanıcı onayı bekliyor** · Dayanak: `tasarim-kararlari.md`, `parca-plani-denetim.md`, `research_notes/diger-hesap/gorev1-10`.

## 1. Tek cümlede

freqtrade üzerinde, kurallarla fırsat bulan, Claude'un veto edebildiği, risk kuralları kilitli, kapanan işlemlerinden her gün ders önerisi çıkaran ve bunu yanındaki "dondurulmuş ikiz" ile kıyaslayarak ölçen bir kripto vadeli işlem botu. İlk sürüm yalnızca sahte parayla (dry-run) çalışır.

## 2. Çalışma ortamı

- **Sunucu:** DigitalOcean droplet, **Frankfurt (FRA1)**. ABD bölgeleri Binance'ten HTTP 451 alır (Görev 6); Hollanda, İngiltere, Kanada, Avustralya Binance vadeli için kısıtlı ülkeler listesinde (Görev 2). İlk iş: sunucudan `api.binance.com` ve `fapi.binance.com` erişim testi.
- **Boyut:** 2 vCPU / 4 GB RAM (~24 $/ay). Öğrenen bot + ikiz + yardımcı servisler için; FreqAI ileride eklenirse yeterli pay bırakır (Görev 6: backtest ~0,75 GB, FreqAI ~1,4 GB).
- **Kurulum:** Docker Compose. Her bot ayrı konteyner, ayrı veritabanı, ayrı port. API/panel yalnızca `127.0.0.1`'e bağlı; erişim SSH tüneliyle.
- **Anahtarlar:** dry-run aşamasında borsa anahtarı yok. Claude anahtarı ayrı Anthropic workspace'inde, aylık limitli.
- **Kod yeri:** yeni bot `trader/` klasöründe.

## 3. Parçalar ve veri akışı

```mermaid
flowchart LR
  subgraph Veri
    BX[Binance açık veri<br/>mum, funding, açık pozisyon]
  end
  subgraph Analist["Analist servisi (ayrı konteyner)"]
    RJ[Piyasa durumu etiketi<br/>trend / yatay / oynak]
    CL[Claude Haiku 5.5<br/>veto kararı JSON]
  end
  VD[(veto.json<br/>TTL'li, imzalı)]
  subgraph Botlar["freqtrade (dry-run)"]
    L[Öğrenen bot L]
    T[Dondurulmuş ikiz T]
  end
  RK[[Kilitli risk kuralları<br/>%2 / %5 / 3-5x / SL < likidasyon]]
  DF[(Kayıt defteri<br/>işlemler, dersler, değişiklikler)]
  DR[Ders servisi<br/>günlük, Claude Sonnet 5.5 Batch]
  AY[(Canlı ayar dosyası<br/>yalnız izinli sınırlar)]
  KN[Kontroller<br/>al-tut, rastgele giriş, DSR]
  TG[Telegram + günlük rapor + panel]

  BX --> RJ --> CL --> VD
  BX --> L & T
  VD --> L & T
  RK --- L & T
  L & T --> DF
  DF --> DR -->|aday ders| DF
  DR -.->|≥20-30 işlem kanıtı,<br/>kapıdan geçerse| AY --> L
  DF --> KN --> TG
  L --> TG
```

| # | Parça | Görevi | Kaynak | İş |
|---|---|---|---|---|
| 1 | freqtrade (×2) | Emir, dry-run, SL/TP, Telegram, panel | freqtrade 2026.10 | Hazır |
| 2 | Strateji | Kurallarla giriş/çıkış; piyasa durumuna göre gün içi/swing ayarı; stop mesafesine göre pozisyon büyüklüğü | Kendimiz | Yaz |
| 3 | Kilitli risk kuralları | %2 işlem riski, %5 günlük zarar, 3-5x kaldıraç, "SL likidasyondan önce" kontrolü; alt sınıf değiştiremez | agent-to-earn `guarded_strategy.py` (MIT); sınırlar bizim kararlara göre değiştirilir; "zarar durdur likidasyondan önce" kontrolünü biz yazarız | Uyarla |
| 4 | Piyasa durumu (rejim) etiketi | Tek tanım; strateji, veto ve ders servisi aynı etiketi kullanır | regime-trading-bot `core/regime.py` + `indicators.py` (MIT; telif notu korunur) | Uyarla |
| 5 | Analist + veto | Claude ayrı süreçte çalışır, kararı dosyaya yazar; strateji yalnız dosyayı okur. Dosya yok/bayat/limit dolu → giriş yok | Kodu sıfırdan biz yazıyoruz; regime-trading-bot'tan yalnızca JSON dosya sözleşmesi/deseni alınır; testleri biz yazarız (kaynakta %0 test) | Yaz |
| 6 | Funding / açık pozisyon verisi | Binance açık uçlarından | Kendimiz | Yaz (küçük) |
| 7 | Kayıt defteri | Her işlem, gerekçe, ders önerisi, değişiklik; yalnız ekleme | guarded-trader `registry.py` (Apache) | Uyarla |
| 8 | Ders servisi | Günlük: kapanan işlemler → istatistik → Claude → **aday ders** (ilk günden açık; değişiklik için ≥20–30 işlem kanıtı, değişiklik günlüğü ve geri alma) | Kendimiz (fikir: astra, cryptobot, HydraQuant, TEMPEST (rgg81/crypto-trade-claude-code; yalnız fikir, lisans yok), qrak/LLM_trader) | Yaz |
| 9 | Sınır anayasası | Öğrenmenin değiştirebileceği ayarlar ve aralıkları; risk ayarları listede yok | regime-trading-bot `levers.py` (MIT) | Al |
| 10 | Kontroller ve ölçüm | İkiz kıyası, al-tut, rastgele giriş, Deflated Sharpe | guarded-trader `dsr.py`, `null.py` (Apache); trialgate yalnız README düzeyinde bilgi; `null.py`'yi freqtrade'e bağlayan kodu biz yazarız | Al; bağlantı kodu yaz |
| 11 | Rapor | Telegram anlık + günlük özet (işlemler, dersler, maliyet) + onay sorusu | freqtrade + kendimiz | Kısmen yaz |
| 12 | Harcama koruması | Anthropic aylık limit + uygulama içi günlük tavan; limit hatasında dur ve haber ver | Kendimiz | Yaz (küçük) |

**Sonraki sürümlere kalanlar:** bağımsız risk bekçisi, haberler, FreqAI/Kronos, gerçek para, Faz 2 (ABD hisse, emtia).

## 4. Yol haritası

| Adım | İçerik | Bitti sayılır |
|---|---|---|
| 0 | Sunucu kurulumu, Binance erişim testi, freqtrade dry-run vadeli işlem uçtan uca | Kaldıraçlı long/short açıp kapatıyor; SL likidasyondan önce |
| 1 | Strateji + kilitli risk + piyasa durumu etiketi; backtest + lookahead/recursive analiz | Testler geçiyor, sızıntı yok |
| 2 | Analist + veto + harcama koruması | Dosya yok/bayatken giriş reddediliyor |
| 3 | İkiz + kayıt defteri + rapor | İki özdeş kopya ≥ %95 aynı işlem |
| 4 | Ders servisi (ilk günden açık; ≥20–30 işlem kanıtı, değişiklik günlüğü ve geri alma) | Her gün aday dersler deftere düşüyor |
| 5 | 4-8 hafta dry-run deneyi (Görev 5 planı) | "Elendi" / "elemeyi geçti" kararı |
| 6 | Test-et-terfi kapısı + geri alma | ≥20–30 işlem kanıtıyla açılır; geri alma her değişiklikte var |

## 5. Açık riskler

- **Gürültüden ders çıkarma** (en büyük risk): dar sınırlar, haftada en fazla bir değişiklik, ikizle kıyas.
- **Hiçbir şey henüz uçtan uca çalıştırılmadı;** parçaların çoğu yıldızsız, yeni repolardan. Eksik testleri (özellikle veto) biz yazacağız.
- **Binance erişimi ve hukuki durum:** Türk KYC'li hesapla yabancı IP'den API kullanımı ve vadeli işlem gri alan (Görev 2). Gerçek paradan önce netleştirilmeli.
- **Dry-run iyimser** (Görev 8): limit emir dokununca dolar, kısmi dolum yok, likidasyon ücreti yok. Sonuçlar 2x maliyetle de değerlendirilecek.
