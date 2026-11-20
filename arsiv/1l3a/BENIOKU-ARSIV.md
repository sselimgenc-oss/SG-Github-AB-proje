# 1L3A arşivi (salt başvuru) — 20 Kasım 2026

Kullanıcı kararıyla 1L3A projesi kapatıldı ve deposu silinecek; ML Otonom ana proje oldu. Bu klasör, 1L3A deposunun
(`sselimgenc-oss/1L3A-Proje`, dal `claude/adoring-maxwell-q7t60g`, commit `0754deca95d92314942114619ab2760fb4cdecc8`)
kod ve belgelerinin **çalıştırılmayan** kopyasıdır: ML'e taşınan özelliklerin kaynağı ve ileride gerekebilecek her şey için.

- Kapsam: `araclar/`, `deploy/`, `docs/` (taşıma notları: `docs/ml-tasima-notlari.md`), `motor/`, `stratejiler/`, `testler/`,
  `raporlar/`, `sonuclar/**/*.md` (ön kayıt/mühür belgeleri), `DURUM.md`, `README.md`, `requirements.txt`.
  1L3A'nın `CLAUDE.md` ve `AGENTS.md` dosyaları `KURALLAR-1l3a.md` ve `AGENTS-1l3a.md` adıyla (talimat olarak yüklenmesinler diye) saklandı.
- Dışarıda bırakılanlar: `veri/` (piyasa verisi), `arsiv/` ve `sonuclar/` altındaki büyük CSV/JSON sonuç dosyaları (yeniden üretilebilir;
  ML holdout kuralı gereği dönem verisi bu depoya alınmaz).
- Bu klasör ML'in testlerine, CI'ına ve sunucu kurulumuna girmez (`trader/` dışında). Kod buradan içe aktarılmaz; taşınan parçalar
  `trader/` altında ML kurallarıyla yeniden yazılır. ML karşılık eşlemesi: `ESLEME.md`.
- `testler/test_paper_denetim.py` içindeki Telegram belirteci sahte test değeridir.
