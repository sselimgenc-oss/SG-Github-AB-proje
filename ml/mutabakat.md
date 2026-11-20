# İşlem mutabakatı

Son kontrol: 2026-11-20 18:04 (TSİ). İşlem: 25 (kapanan 17, açık 8). Uyuşmazlık: 0.

## Kontroller

| Kontrol | Sonuç | Ayrıntı |
|---|---|---|
| Kasa = başlangıç + Σ net K/Z | geçti | Kasa 1.030,86 $ tutuyor |
| Net K/Z: SQL toplamı = motor toplamı = brüt - komisyon - fonlama | geçti | Defter toplamları tutuyor (+29,44 $) |
| Long toplamı (motor = panel) | geçti | Long işlemler panelle aynı (5 işlem) |
| Short toplamı (motor = panel) | geçti | Short işlemler panelle aynı (12 işlem) |
| Toplam kapanan (motor = panel 'tümü') | geçti | Kapanan işlemlerin toplamı panelle aynı (17 işlem) |
| Açık pozisyon sayısı (motor = panel = şerit = durum) | geçti | 8 açık işlem, hepsi aynı |
| Açık K/Z fiyat kaynağı (panel = motor mark) | geçti | Açık işlemlerin kâr/zararı panelle aynı; fiyat bekleniyor (piyasa kapalı/veri yok): #15, #17, #20, #22, #24, #27, #28, #30 |
| Günlük zarar limiti oranı (panel = kâğıt ayarı) | geçti | Günlük zarar limiti %8,00 (panelle aynı) |

## Bilgi

- Fiyatı gelmeyen açık işlemler: #15, #17, #20, #22, #24, #27, #28, #30 · fiyat bekleniyor (piyasa kapalı/veri yok); uyuşmazlık sayılmaz

## Telegram kaynağı

Telegram geçmişine erişim yok; motorun gönderdi kaydı (imleç) kullanıldı. Sıra: (1) gönderim kaydı islem_gonderildi.jsonl (ts, işlem no, tür, yön, K/Z; kayıt başlangıcından itibaren), (2) outbox 'sent' işaretleri (teslim edilmiş mesajın anahtarı; mesaj metni yok), (3) islem_imleci.json (duyurulmuş işlem numaraları). Gönderim kaydından önceki işlemlerde imleç yalnız 'duyuruldu' sayıldığını gösterir, mesaj metnini kanıtlamaz; mesaj sisteminden önceki işlemler 'Telegram öncesi' sayılır, uyuşmazlık değildir.

## Uyuşmazlıklar

Yok.

## İşlemler

| İşlem no | Kol | Coin | Yön | Durum | Açılış (TSİ) | Kapanış (TSİ) | Giriş | Çıkış | Brüt $ | Komisyon $ | Fonlama $ | Net K/Z $ | Panel | Telegram açıldı | Telegram kapandı |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 1 | Trend geri çekilmesi · 1 saat | ADA | short | kapalı | 2026-11-18 08:00 | 2026-11-19 07:46 | 0,152900 | 0,153300 | -0,6144 | 0,2352 | -0,0396 | -0,8100 | aynı | Telegram öncesi (mesaj sistemi yoktu) | Telegram öncesi (mesaj sistemi yoktu) |
| 2 | Trend geri çekilmesi · 1 saat | AVAX | short | kapalı | 2026-11-18 10:00 | 2026-11-19 07:46 | 7,147000 | 7,099000 | 2,4000 | 0,3562 | 0,0004 | 2,0434 | aynı | Telegram öncesi (mesaj sistemi yoktu) | Telegram öncesi (mesaj sistemi yoktu) |
| 3 | Trend geri çekilmesi · 1 saat | BTC | short | kapalı | 2026-11-18 12:00 | 2026-11-19 07:46 | 64.644,400000 | 63.634,100000 | 9,0927 | 0,5773 | -0,0873 | 8,6027 | aynı | Telegram öncesi (mesaj sistemi yoktu) | Telegram öncesi (mesaj sistemi yoktu) |
| 4 | Trend geri çekilmesi · 1 saat | ETH | short | kapalı | 2026-11-18 12:00 | 2026-11-19 04:04 | 1.810,700000 | 1.788,890000 | 6,4994 | 0,5363 | -0,0460 | 6,0090 | aynı | Telegram öncesi (mesaj sistemi yoktu) | Telegram öncesi (mesaj sistemi yoktu) |
| 5 | Trend geri çekilmesi · 1 saat | BNB | short | kapalı | 2026-11-18 12:00 | 2026-11-19 07:45 | 591,970000 | 588,020000 | 3,9500 | 0,5900 | 0,0000 | 3,3600 | aynı | Telegram öncesi (mesaj sistemi yoktu) | Telegram öncesi (mesaj sistemi yoktu) |
| 6 | Trend geri çekilmesi · 1 saat | SOL | short | kapalı | 2026-11-18 23:00 | 2026-11-19 07:34 | 73,060000 | 74,680000 | -4,9572 | 0,2260 | -0,0017 | -5,1816 | aynı | Telegram öncesi (mesaj sistemi yoktu) | Telegram öncesi (mesaj sistemi yoktu) |
| 7 | Sahte kırılım dönüşü · 15 dakika | BTC | short | kapalı | 2026-11-19 14:00 | 2026-11-19 14:33 | 63.747,600000 | 64.018,400000 | -4,0620 | 0,9582 | 0,0000 | -5,0202 | aynı | Telegram öncesi (mesaj sistemi yoktu) | Telegram öncesi (mesaj sistemi yoktu) |
| 8 | Sıkışma kırılımı · 15 dakika | HBAR | short | kapalı | 2026-11-19 14:00 | 2026-11-19 14:45 | 0,055340 | 0,056030 | -9,2957 | 0,7502 | 0,0000 | -10,0459 | aynı | Telegram öncesi (mesaj sistemi yoktu) | Telegram öncesi (mesaj sistemi yoktu) |
| 9 | Yapay zekâ adayı · 1 saat | NVDA | long | kapalı | 2026-11-19 14:00 | 2026-11-19 18:00 | 154,090000 | 155,200000 | 5,6499 | 0,7871 | 0,0000 | 4,8628 | aynı | Telegram öncesi (mesaj sistemi yoktu) | Telegram öncesi (mesaj sistemi yoktu) |
| 10 | Sıkışma kırılımı · 15 dakika | HYPE | long | kapalı | 2026-11-19 14:45 | 2026-11-19 15:25 | 68,917000 | 68,146000 | -8,9976 | 0,7998 | 0,0000 | -9,7973 | aynı | Telegram öncesi (mesaj sistemi yoktu) | Telegram öncesi (mesaj sistemi yoktu) |
| 11 | Sıkışma kırılımı · 15 dakika | AMD | long | kapalı | 2026-11-19 14:45 | 2026-11-19 16:30 | 550,750000 | 538,300000 | -13,0725 | 0,5718 | 0,0000 | -13,6443 | aynı | Telegram öncesi (mesaj sistemi yoktu) | Telegram öncesi (mesaj sistemi yoktu) |
| 12 | Sahte kırılım dönüşü · 15 dakika | WMT | long | kapalı | 2026-11-19 17:45 | 2026-11-20 05:45 | 125,030000 | 127,200000 | 8,7017 | 0,5057 | 0,0000 | 8,1960 | aynı | Telegram öncesi (mesaj sistemi yoktu) | Telegram öncesi (mesaj sistemi yoktu) |
| 13 | Kırılım yeniden testi · 15 dakika | BRKB | short | kapalı | 2026-11-19 18:15 | 2026-11-19 20:15 | 570,350000 | 567,810000 | 4,3688 | 0,9788 | 0,0000 | 3,3900 | aynı | Telegram öncesi (mesaj sistemi yoktu) | Telegram öncesi (mesaj sistemi yoktu) |
| 14 | Trend geri çekilmesi · 15 dakika | XAG | short | kapalı | 2026-11-19 18:15 | 2026-11-20 03:15 | 45,280000 | 43,150000 | 42,1122 | 0,8742 | -0,2922 | 41,5303 | aynı | Telegram öncesi (mesaj sistemi yoktu) | Telegram öncesi (mesaj sistemi yoktu) |
| 15 | Kadro uzlaşısı · 4 saat | XRP | short | açık | 2026-11-19 19:00 | — | 0,968700 | — | — | 0,1319 | 0,0000 | — | aynı | Telegram öncesi (mesaj sistemi yoktu) | — |
| 16 | Sahte kırılım dönüşü · 15 dakika | HBAR | long | kapalı | 2026-11-19 20:30 | 2026-11-19 23:27 | 0,055240 | 0,054300 | -9,3135 | 0,5427 | 0,0000 | -9,8562 | aynı | Telegram öncesi (mesaj sistemi yoktu) | Telegram öncesi (mesaj sistemi yoktu) |
| 17 | Sıkışma kırılımı · 15 dakika | TRX | short | açık | 2026-11-19 23:30 | — | 0,309870 | — | — | 0,5001 | 0,0000 | — | aynı | Telegram öncesi (mesaj sistemi yoktu) | — |
| 20 | Trend kırılımı · 1 gün | ORCL | short | açık | 2026-11-20 03:00 | — | 109,860000 | — | — | 0,0505 | 0,0000 | — | aynı | Telegram öncesi (mesaj sistemi yoktu) | — |
| 21 | İki bacaklı geri çekilme · 15 dakika | NVDA | short | kapalı | 2026-11-20 03:30 | 2026-11-20 11:21 | 145,870000 | 144,590963 | 6,5103 | 0,7392 | -0,0282 | 5,7993 | aynı | Telegram öncesi (mesaj sistemi yoktu) | gönderildi (kayıt) |
| 22 | Sıkışma kırılımı · 1 saat | ADA | short | açık | 2026-11-20 05:00 | — | 0,149000 | — | — | 0,1266 | 0,0000 | — | aynı | Telegram öncesi (mesaj sistemi yoktu) | — |
| 23 | Kadro uzlaşısı · 1 saat | BTC | short | kapalı | 2026-11-20 06:00 | 2026-11-20 17:28 | 62.235,100000 | 62.172,800000 | 0,5607 | 0,5598 | -0,0039 | 0,0048 | aynı | Telegram öncesi (mesaj sistemi yoktu) | gönderildi (kayıt) |
| 24 | Yapay zekâ adayı · 4 saat | BNB | short | açık | 2026-11-20 07:00 | — | 575,090000 | — | — | 0,2128 | 0,0000 | — | aynı | gönderildi (kayıt) | — |
| 27 | Sıkışma kırılımı · 1 saat | AMD | short | açık | 2026-11-20 13:00 | — | 462,660000 | — | — | 0,1157 | 0,0000 | — | aynı | gönderildi (kayıt) | — |
| 28 | Kadro uzlaşısı · 1 saat | LINK | short | açık | 2026-11-20 14:00 | — | 8,872000 | — | — | 0,2595 | 0,0000 | — | aynı | gönderildi (kayıt) | — |
| 30 | Kırılım yeniden testi · 1 saat | SOL | short | açık | 2026-11-20 18:00 | — | 71,000000 | — | — | 0,3401 | 0,0000 | — | aynı | gönderildi (kayıt) | — |
