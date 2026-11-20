# ML botu genel denetim raporu (20 Kasım 2026)

Plan: sg-orkestra-sefi/DENETIM_PLANI.md. Kapsam: son 48 saatin değişikliği (108 Python dosyası) ve para yolu (giriş/risk, kâğıt borsa, çıkış/kısmi/başa-baş, kademe, mutabakat, ders otomatiği, gece eğitimi). Denetim sırasında hiçbir düzeltme yapılmadı.

## Özet

| | Sayı |
|---|---|
| Doğrulanmış bulgu (kırmızı test + çürütme denemesinden geçti) | 4 — kritik 0, orta 1, düşük 3 |
| Şüphe (testsiz) | 8 |
| Güven sınaması | **5/5** (habersiz inceleyici, geçmişsiz kopya; 5 hatanın 5'i kırmızı testle bulundu) |
| İşlemlere etki eden doğrulanmış bulgu | **0** |

## Doğrulanmış bulgular (önem sırasıyla)

1. **ORTA — kısmi çıkışlı işlemde `slippage_exit` karma fiyatla hesaplanıyor.** `engine.py:1645-1652` (`_blend_closed`), `ledger.py:1946-1948`, `position_manager.py:185-212`. Testte −144 bp kaydediliyor, gerçek +5,9 bp. `drift_monitor.py:290-318` bunu okuyor → sahte "benzetim az maliyet" uyarısı, maliyet kayması maskeleniyor. Kâğıtta açık: evet (kısmi tüm kollarda açık). İşleme etkili: **hayır** (yalnız izleme).
2. **DÜŞÜK — M1 gece eğitiminde zaman dilimi başına hata yalıtımı yok.** `scripts/ml_retrain_run.py:112-150`. Bir dilim hata verirse sonrakiler o gece eğitilmez; `main()` yakalar, çıkış 3 (sağlık görür), motor eski modelle sürer. Kâğıtta açık: evet. İşleme etkili: hayır (bir gece model yenilenmez).
3. **DÜŞÜK — %12 açık risk ve %8 aynı yön tavanı fiilen işlemiyor.** `risk.py:350-352` günlük bütçe (zarar + açık risk + yeni ≤ %8) önce bağlar. `docs/risk-kilidi-spec.md:63`'te yazılı, tasarım gereği; ayar değeri yanıltıcı. İşleme etkili: evet ama temkinli yönde (fazla red, fazla işlem değil). Karar gerekir: ayar 0,08'e mi çekilsin, kural mı değişsin (Fable/kullanıcı).
4. **DÜŞÜK (gizli) — kısmi çıkış emri `orders` tablosuna yazılmıyor.** `engine.py:1590-1602`. Aynı kısmi dolum iki kez gelirse tam kapanış sayılır. Kâğıtta oluşamaz (paper değişmezi 6). Canlı/testnet'e geçmeden düzeltilmeli.

## Şüpheler (testsiz)

- `risk.py:314/350`: gerçekleşmemiş kâr gün içi zararı maskeleyebilir; gerçekleşmemiş zarar iki kez sayılır (tasarım, temkinli).
- `gates.py:295-298`: etiket durum dosyası okunamazsa kanıta göre kapanmış kural yeniden engeller (belgeyle tutarlı).
- `gates.py:301`: `etiket_atlardi` sayacı risk reddinden önce artar (yalnız durum sayısı).
- `panel_data.py:273-277`: pano kâğıtta açık risk/yön limitini kilitli değerle (%6/%4) gösteriyor; gerçek %12/%8 (yalnız gösterim).
- `pa_proposer/package.py:44-48`: paket kaydı iki adımlı; milisaniyelik pencerede güncel dosya yok.
- `scripts/mutabakat_run.py:117-131`: kurulum günü "İşlem kontrolü" iki mesaj olabilir.
- `lesson.py:4531-4541`: geri alma tek adım (tasarım).
- `ladder.py:367-382`: kâğıt gözlem kipinde yanıltıcı CRITICAL "giriş kapalı" günlüğü.

## Çürüyen şüpheler

Emir kimliği çakışması yok (seq 0/1); likidasyon boşluğu `liq_price`'ta kasıtlı (03-paper-broker §4.3); kısmili işlemde `realized_pnl` cüzdanla 1e-6 içinde eşit; mypy'nin `float|None` uyarıları çalışma zamanında None olamaz.

## Temiz çıkanlar

Risk işaret/yönleri, fail-closed; kâğıda özel özellikler canlıya sızmıyor (`config.py:526-539`); ML filtresi ve etiket kuralları yalnız "hayır" der; kademe kâğıtta girişi engelleyemez; stop asla gevşemez; kısmi sonrası stop adedi; fonlama işareti; ders otomatiği sert sınır dışına çıkamaz, canlıya geçmez; kilitli dönem üç katmanda eğitimden dışlanıyor; kasa formülü; defter salt okunur. Çıkış/muhasebe: 40+ tohumlu rastgele senaryo testinde cüzdan = defter tuttu.

## Araç taraması (adım 0)

- ruff (F/B, 108 dosya): F401 24, F841 7, B905 17, B007 13, B904 2, B023 1.
- vulture: 5 ölü kod (`exit_counterfactual.py:662`, `ledger.py:1481`, `panel_pano.py:346`, `gates.py:353`, `marketdata/feed.py:880`).
- bandit (orta+): 59, çoğu SQL metin birleştirme (B608); dışarıdan girdi yok, düşük.
- pytest-randomly: 2 tohum, 736 geçti; sıra bağımlılığı yok.
- diff-cover: yapılamadı (pytest-cov yok).
- Mükerrer kod (pylint, 42 blok): en çok `exit_counterfactual` ↔ `counterfactual` (9). Öneri: ortak yardımcılar `counterfactual.py`'de kalsın, `exit_counterfactual` onları çağırsın.

## Mutasyon testi (adım 1)

risk.py + exit_modes.py: 379 mutant, 282 öldü, 6 zaman aşımı (yakalandı), 91 hayatta → skor %76. Gerçek test boşlukları: `check_entry` sınırlarının tam eşitlik durumları; `exit_modes` bayrak varsayılanı (L136/138), `partial_due` kapalıyken True (L189), `reached_r(best=None)` (L155), NaN süzgeci (L145/146). Ayrıntı: `raporlar/denetim-ml-mutasyon.md`.

## Güven sınaması

Ayrı yerel dalda para yoluna 5 bilinçli hata (aynı yön riski işareti, günlük bütçe işareti, fonlama işareti, kısmi sonrası teminat, short başa-baş seviyesi). Habersiz Sonnet, git geçmişi olmayan kopyada 5/5 buldu, hepsine kırmızı test yazdı. Dal ve kopya silindi; hiç push edilmedi.

## Önerilen düzeltme sırası (orkestratör karar verir)

1. Bulgu 1 (izleme yanlış uyarı) — `slippage_exit` son bacak fiyatıyla.
2. Bulgu 4 — canlıya geçmeden kısmi emri `orders` tablosuna yaz.
3. Bulgu 2 — zaman dilimi başına try/except.
4. Mutasyon boşlukları için sınır testleri (`exit_modes` öncelikli).
5. Bulgu 3 — karar konusu (Fable/kullanıcı).
