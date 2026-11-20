# Telegram standardı (ML Otonom referansı) — sürüm 1, 19 Kasım 2026

Bu belge ML Otonom'un Telegram düzenini üç proje (ML, 1L3A, CT) için ortak standart olarak tanımlar. Kaynak: `trader/src/trader_core/telegram.py`.
Alan projeler kendi reposuna uyarlar; bu belgeyi değiştirmez. Değişiklik önerisi orkestratör üzerinden gelir.

## 1. Genel kurallar
| Kural | Değer |
|---|---|
| Mesajın ilk satırı | Proje etiketi: `[ML]`, `[1L3A]`, `[CT]` (ortak sohbette karışmasın). Yeni kural: ML'de de henüz yok, eklenecek |
| Dil | Sade Türkçe, kısa; sayılar ondalık virgül değil nokta ile yazılabilir, tutar `$` ile |
| Önem düzeyleri | `INFO` (sessiz bildirim), `WARN`, `CRIT` |
| Gönderim | Kuyruk (outbox) üzerinden; ağ hatasında kaybolmaz, yeniden dener |
| Hız sınırı | Dakikada en fazla 15 mesaj; INFO mesajı 24 saatten eskiyse atılır |
| Tekrar önleme | Aynı uyarı anahtarı (dedup key) kısa sürede bir kez gönderilir |
| Uzunluk | Mesaj başına en fazla 3500 karakter; sığmazsa kısaltılır, kritik satır sabit kalır |
| Gizlilik | Anahtar/token/parola asla mesajda yok; token maskelenir |
| Yetki | Yalnız tanımlı sohbet (chat_id) ve kullanıcıdan gelen komut işlenir |

## 2. Bildirim türleri
| Tür | Ne zaman | Önem |
|---|---|---|
| İşleme giriş / çıkış | Her dolumda (çift, yön, fiyat, stop/hedef, R) | INFO |
| Sağlık uyarısı | Sağlık kontrolü her 5 dakikada; sorun çıkınca (veri akışı, motor, bellek, model paketi vb.) | WARN / CRIT |
| Sorun düzeldi | Aynı uyarı kapanınca ("Düzeldi: ...") | INFO |
| Giriş kilidi / durdurma | Motor girişleri kapatınca ya da açınca (neden ile) | WARN / CRIT |
| Günlük rapor | Her gün **21:00 TSİ** | INFO |
| Haftalık özet | Her **Pazar 18:10 UTC** (21:10 TSİ); yapay zekâ bütçesi bitmişse sayısal özet | INFO |
| Ders bildirimi | Ders uygulandı / geri alındı / fren devrede | INFO / WARN |

## 3. Komutlar
| Komut | İş | Onay |
|---|---|---|
| `/durum` | Bot durumu: equity, açık pozisyon, giriş açık/kapalı (neden), duraklatmalar | yok |
| `/rapor` | Günlük raporu hemen gönderir | yok |
| `/kurulumlar` | Kurulum (strateji) karnesi: aday, alınan, ort. R, alınsaydı R | yok |
| `/ders` | Ders durumu: uygulanan, geri alınan, fren | yok |
| `/durdur` | Yeni girişleri durdurur; açık pozisyonlar kalır | **iki adımlı** |
| `/devam` | Durdurmayı kaldırır | **iki adımlı** |
| `/hepsini_kapat` | Tüm pozisyonları kapatır, girişleri durdurur (acil) | **iki adımlı** |
| `/kademe` | Risk kademesi durumu | yok |
| `/kademe_devam` | Risk kademesini sürdürür | **iki adımlı** |
| `/onayla <id>` / `/reddet <id>` | Bekleyen öneriyi onaylar / reddeder | — |
| `/yardim`, `/start` | Komut listesi | yok |

Proje kendi işine özgü komut ekleyebilir; ortak adlar yukarıdaki gibi kalır. Bilinmeyen komuta komut listesiyle cevap verilir.

## 4. İki adımlı onay
1. Riskli komut gelince bot ne olacağını tek satırda yazar ve **120 saniye** geçerli 4 haneli bir kod ister (ya da "Evet, onayla" düğmesi).
2. Kod doğru ve süre içindeyse uygulanır; aksi halde hiçbir şey olmaz ve bot bunu söyler.
3. Her onay/ret denetim kaydına yazılır (kim, ne zaman, ne).

## 5. Projeye göre notlar
- **CT:** sürekli çalışmıyorsa (vardiya zinciri) komutlara gecikmeli cevap verir; bu gecikme `/yardim` metninde açıkça yazılmalı.
- **1L3A:** önce `/durum` ve `/durdur` (iki adımlı) yeterli; diğerleri sırayla eklenir.
- Kâğıt modda da aynı düzen kullanılır; gerçek para ile ilgili komutların davranışı yalnız kullanıcı kararıyla değişir.
