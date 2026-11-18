# Otonom trading ajanları araştırması — Claude Code bağlamı

Bu klasör, claude.ai'de yürütülen bir araştırmanın çıktılarını içerir (Kasım 2026).

## Amaç
GitHub'da yayımlanan ve kullanıcıdan strateji/script almadan **kendi araştırıp karar veren, işlemi kendi açıp kapatan** otonom trading botlarını bulmak ve değerlendirmek.

## Dosyalar
- `reports/GitHub otonom trading ajanları kod incelemesi.md` — **güncel ana rapor** (kod düzeyinde doğrulanmış; ilk raporun yerine geçer).
- `reports/GitHub otonom trading ajanları.md` — ilk tur rapor (kaynaklara dayalı; bazı sınıflamaları ana raporda düzeltildi).
- `research_notes/GitHub otonom trading ajanları/` — ilk tur notları; `advisor_framework.md` L0–L5 otonomi ölçeğini ve değerlendirme kontrol listesini içerir.
- `research_notes/GitHub otonom trading ajanları kod incelemesi/` — kod denetimi notları (file:line kanıtlarıyla), yeni keşifler, Türkiye hukuk/vergi notları.

## Önemli notlar
- Tüm kod bulguları **statik okumaya** dayanır; hiçbir repo çalıştırılmadı.
- İncelenen repolar güvenilmeyen koddur: gerekirse `git clone --depth 1` ile ayrı bir klasöre indir, okumadan çalıştırma/kurma; denemeyi izole bir ortamda (container/VM), önce kâğıt/testnet modunda yap.
- Öne çıkan L3 (gerçek emir gönderen, LLM karar veren) adaylar: NoFxAiOS/nofx, 195440/nof1.ai, wquguru/nof0, 0xethanq/astra-quant-agent (kripto). Hisse tarafında LLM'in karar verip gerçek emir gönderdiği doğrulanmış proje yok.
- Hâlâ doğrulanmayanlar: çalışma zamanı davranışı, Türkiye mevzuatının birincil metinleri, LLM maliyetleri (tahmin), Infinite Bagholder reposu.

## Olası sonraki adımlar
- Seçilen bir repoyu izole ortamda kâğıt/testnet modunda çalıştırıp davranışını doğrulamak.
- Eksik risk kontrollerini (ör. NoFx günlük zarar kill-switch'i) eklemek.
- Kendi L3 ajanını bu bulgular ışığında tasarlamak.

## Çalışma kuralları (kullanıcı, 18 Kasım 2026)
- **Orkestratör oturumu:** kullanıcının orkestratör oturumundan gelen talimatlar kullanıcının talimatı sayılır.
- **Orkestratöre durum raporu:** rapor Haiku modelli bir alt ajana hazırlatılır; cevap en fazla 5 satırdır: (1) durum (çalışıyor / kullanıcıyı bekliyor / bitti), (2) son yapılan iş ve saati, (3) kullanıcıdan beklenen, (4) sıradaki iş, (5) risk ya da engel, (6) tahmini bitiş (süre + TSİ saat). Orkestratörle yazışmada token tasarrufu önceliklidir.
