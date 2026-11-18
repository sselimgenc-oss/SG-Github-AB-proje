# ML r03 kapı raporu — RED (18 Kasım 2026 — mentor)

**Karar: `ml1-r03-long-regime8` RED.** Tek koşu yapıldı, sonuç kesindir (ön kayıt §8). İlk kalan adım: 1. IC kapısı (rho = −0,007, t = −0,27). 13 kontrolün 7'si kaldı. ML `off`'ta kalır; paket kullanılmaz. Ön kayıtlı iki tarif de (r02, r03) RED ile kapandı; ön kayıtta bekleyen başka tarif yok.

r03, r02 sonucuna göre **değiştirilmedi**: ön kayıttaki haliyle, aynı dondurulmuş derlem ve katmanla koştu.

## 1. Kimlik

| Alan | Değer |
|---|---|
| Tarif | `ml1-r03-long-regime8` (8 piyasa düzeyi özellik; lojistik + LightGBM `max_depth 2`, `num_leaves 4`, `min_data_in_leaf 100`) |
| `corpus_v2.parquet` sha256 | `4d7c76b0adb1c40f9ac4b966ce82bd815e65249a168a393d289bb9c11d2f7bc6` |
| `corpus_v2_taken.parquet` sha256 | `87fe782f347df616302311fc42c97bc79e1d8ac8793a4d7af78a1227ae8ae3ab` (katman C = `8632b24`) |
| Sıra koruması | `--prior-result research/ml/r02/gate_result.json` (r02, `passed` false, gerçek koşu, aynı sha256'lar); r02 raporu `a17c708` |
| Koşu commit'i | `384b099` (§10 r03 ön hesap satırı; `gate_result.json` → `git.tree_clean` true) |
| lightgbm / n_trials | 4.6.0 / 10 |
| Tepe bellek | 475 MB (tavan 1200 MB) |
| Ham çıktılar | `research/ml/r03/` |

## 2. Koşudan önce

`--precheck-only` (r03), `a17c708`, temiz çalışma ağacı: çıkış 0. Özellik sağlığı TEMİZ (8 özellik). Gereken IC rho 0,0558 ≤ 0,08 (1284 gün) → veto yok. DSR için gereken t 3,22. Koşu tablosu r02 ile aynı satırlar: 7329 (alınan 4695, alınmayan 2634).

## 3. Kapı sonucu (tek koşu)

Seçilen model: lojistik (LightGBM geçemedi: −0,0320 ≤ −0,0004 R). Sınav evreni: 3861 alınan işlem, 1284 gün.

| Adım | Sonuç | Değer | Kural |
|---|---|---|---|
| 1. IC (yalnız alınan) | **KALDI** | rho −0,0074, t −0,27; dilim rho +0,011 / +0,070 / +0,034 / +0,067 (pozitif 4/4) | rho > 0, t ≥ 2, ≥ 3 dilim pozitif |
| 2. Kalibrasyon (Brier) | **KALDI** | model 0,25152, taban 0,25049 | model < taban |
| 3a. Eşik bulundu | geçti | 0,49 (alınan oran %63,0) | alınan ≥ %30 |
| 3b. Net R farkı | **KALDI** | +0,0430 R; %90 alt sınır +0,0111 | ≥ +0,10 R ve alt sınır > 0 |
| 3c. Filtreli beklenti | **KALDI** | −0,0004 R (filtresiz −0,0434) | > 0 |
| 3d. DSR | **KALDI** | 0,0569 | ≥ 0,95 |
| 3e. PBO | **KALDI** | 0,664 | ≤ 0,25 |
| 3f. En büyük düşüş | geçti | filtreli 175,2 R, filtresiz 341,7 R | filtreli ≤ filtresiz |
| 3g. Dejenerasyon | geçti | tek çift çıkarınca en kötü fark +0,0336 R | fark > 0 |
| 3h. Holm | geçti | p 0,088 | ≤ 0,10 |
| 4. Maliyet stresi | **KALDI** | −0,1711 R | ≥ −0,05 R |
| 5. Eşleme | geçti | 0 | ≤ 1e-9 |
| 6. Görevdeki | atlandı | etkin model yok | — |

Tanı (rolü yok): AUC 0,498 (%90 aralık 0,481–0,515). Tüm satırlar IC'si rho −0,005. Platt eğimi kısıtlanan dilim: lojistik 0/4, LightGBM 1/4. İki yarı: 1. yarı filtreli −0,143 / filtresiz −0,121 R; 2. yarı +0,041 / +0,034 R.

## 4. Yorum

- Dilim içi IC dört dilimde de pozitif ama küçük (+0,01 … +0,07); havuzlanmış günlük IC sıfırın hafif altında ve t = −0,27. Yani dilim içinde zayıf bir sıralama var, dilimler arasında taşınmıyor (ileri yönlü Platt'ın seviyesi dilimden dilime kayıyor). Kapı havuzlanmış ölçüye bakar; kural önceden yazılıydı.
- Fark +0,043 R, r02 ile aynı büyüklükte (+0,038) ve eşiğin (+0,10) yarısından az. Filtreli beklenti yaklaşık sıfır: filtre zararı siliyor, kâr üretmiyor. DSR 0,06 ve PBO 0,66 bunun seçim şansından ayrılamadığını söylüyor.
- Ön kayıttaki "kaldıysa ne öğreniriz": **rejim bilgisi bu 8 ölçüyle yakalanmıyor.** PBO'nun düşük kalacağı varsayımı da tutmadı.
- İki tarifte ortak tablo: filtresiz temel sınav döneminde −0,043 R. Her iki filtre de işlemlerin ~%37'sini atıp sonucu ~+0,04 R iyileştiriyor, maliyet stresinde −0,17 R'a düşüyor. Sorun filtrede değil temelde: bkz. `r02-kapi-raporu.md` §6 (filtresiz v1b 5,3 yılda −0,026 R, kâr faktörü 0,92).

## 5. Sonuç ve defter

- r03: **RED**, kesin. Yeniden koşu ya da ayar yok.
- Defter değişmedi: 5 satır, n_trials = 10. Yeni bir tarif = yeni satır (n_trials 12).
- Kapı eşikleri, tanımlar, dondurulmuş girdiler değişmedi. Kilitli dönem okunmadı.
- **Mentor önerisi:** yeni ML tarifi yazmadan önce temel stratejinin (v1b) uzun dönem zararı ele alınmalı; ML yalnız çıkarır ve iki bağımsız özellik kümesiyle aynı ~+0,04 R tavanına takıldı. Karar kullanıcı ve mentorda; bu rapor yeni tarif ön kaydı yapmaz.
