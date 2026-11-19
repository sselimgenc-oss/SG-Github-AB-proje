# Haber/duygu x sonuç raporu — belirtim (19 Kasım 2026)

**Yalnız bilgi.** Motor, karar, kol ayarları ve ML özellikleri değişmez. Şema `ml.haber_sonuc.v1`; biçim CT `ct.rejim_sonuc.v1` (`copytrade/canli/rejim_sonuc.py`) ile aynıdır (orkestratör iki projeyi yan yana koyar).

## Veri
Kâğıt karar kaydı `decision_events.features` içindeki `duygu` (`{deger, sinif}`) ve `haber` (`{<coin>: {adet_24s, ton}}`) etiketi (`docs/haber-etiketi-spec.md`). Bağlama: kapanan işlem (`v_closed_trades`) -> `decision_id` -> karar satırı (defterin mevcut ilişkisi; yeni sütun/tablo yok). Etiketsiz işlem "etiket yok" (duygu) / "haber yok" (ton) kovasına düşer.

## Kırılımlar
- `duygu`: Aşırı Korku, Korku, Nötr, Açgözlülük, Aşırı Açgözlülük, etiket yok (boş kovalar yazılmaz).
- `haber_ton`: pozitif, negatif, notr, haber yok (coin = çiftin baz varlığı).

## Satır ve birim (CT ile aynı)
`{etiket, n, kazanan, isabet_yuzde, toplam_pnl, ortalama_pnl}`; PnL = gerçekleşen K/Z, USD (`realized_pnl`; CT de USD). R ayrı gösterilmez. Başlık: `<Kırılım> | İşlem | Kazanan | İsabet % | Toplam PnL $ | Ort. PnL $`. Kazanan = PnL > 0.

## Dosya
`var/durum/haber_sonuc_v1.json` (atomik): `{sema, proje:"ML", uretim, pencere_gun:7, tablolar:{duygu,haber_ton} (son 7 gün, kapanış zamanına göre), tum_zamanlar:{duygu,haber_ton}, notlar}`.

## Üretim ve gösterim
- Haftalık özet koşusu (`scripts/weekly_summary_run.py`, `trader-weekly-summary.service`; yeni birim yok, `var/durum` yazılabilir yola eklendi) JSON'u LLM anahtarından bağımsız yazar; özet dosyasının sonuna 1 satır eklenir: `Haber×sonuç (7g) — Duygu: en iyi …, en kötü …; Haber tonu: …`; işlem yoksa `Haber×sonuç: henüz veri yok`. Hata özeti/LLM'i asla engellemez.
- Pano Doğrulama sekmesi "Haber ve duygu × sonuç" kartı (`/api/habersonuc`, `docs/panel-spec.md` §14.1).
