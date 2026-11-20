# Ortak öğrenme paketi (`ortak_ogrenme`) — belirtim, parça 1: kayıt şeması + işlem notu + ders döngüsü

Kaynak proje: ML Otonom. Alan projeler (1L3A, CT) paketi **kopyalar** (kaynak yol + commit notuyla) ve kendi **adaptörünü** yazar.
Konum: `trader/paket/ortak_ogrenme/` (bağımsız; `trader_core`/`trader_engine`'i içe aktarmaz). Bağımlılık: yalnız Python 3.11+ standart kütüphane.
İlke: paket **yalnız puan/rapor/etiket** üretir; hiçbir işlemi engellemez, kurulum kapatmaz. Adaptörün bunu nasıl kullandığı projenin kararıdır.

## 1. `kayit.py` — ortak aday kaydı
```python
@dataclass(frozen=True)
class Aday:
    id: str                 # projede benzersiz
    proje: str              # "ML" | "1L3A" | "CT"
    kurulum: str            # ML: "T1@1h"; 1L3A: strateji kartı adı; CT: kopyalanan trader kimliği
    enstruman: str          # "BTC/USDT" vb.
    varlik_sinifi: str      # "kripto" | "hisse" | "emtia"
    yon: str                # "long" | "short"
    ts: datetime            # karar anı, UTC, tz'li
    alindi: bool            # işleme girildi mi
    r: float | None         # alındıysa gerçek net R; alınmadıysa "alınsaydı" R; bilinmiyorsa None
    seans: str | None = None            # "open" | "closed" | "weekend" | None
    rejim: str | None = None            # "trend_up" | "trend_down" | "range" | "volatile" | "unclear" | None
    ozellikler: Mapping[str, float] = {}  # karar anında bilinen sayısal özellikler (ör. "atr_ratio", "rr", "stop_dist_atr")
    etiketler: tuple[str, ...] = ()     # serbest etiketler (ör. "ct:ayni_yon")
    cikis: Mapping[str, Any] = {}       # kapanmış işlem ayrıntısı (isteğe bağlı): entry_price, planned_entry, planned_stop, exit_reason, bars_held, mfe_r, mae_r
```
- `aday_from_dict(d) -> Aday` ve `aday_to_dict(a) -> dict` (JSON uyumlu; `ts` ISO-8601 `Z`). Gidiş-dönüş kayıpsız.
- Doğrulama: zorunlu alan eksik / `yon`, `varlik_sinifi` sözlük dışı / `ts` tz'siz → `ValueError`.
- `oku_jsonl(path) -> list[Aday]`, `yaz_jsonl(path, adaylar)` (atomik: geçici dosya + replace).

## 2. `notlar.py` — kodla yazılan işlem notu
ML'deki `trader_core/trade_notes.py` mantığının `Aday` üzerinde çalışan hâli. Sabitler aynı: `TAG_VOCAB`, `LESSON_CODES = ("seans_kapali", "yuksek_vol", "dusuk_rr")`, `HIGH_VOL_ATR_RATIO = 1.3`, `LOW_RR = 2.0`, uyum tablosu `{"R1": ("range",), "T1": ("trend_up","trend_down")}` (kurulum adının `@` öncesi kısmıyla eşlenir; bilinmeyen kurulum uyumlu sayılır).
- `ders_kimligi(kod, kurulum) -> str` = `f"{kod}:{kurulum}"`. Kurulum harf/rakam/`_`/`@` içerebilir (ör. `T1@1h`); ders kimliği her zaman adayın kendi kurulumuyla üretilir.
- `ders_uyar_mi(kod, kurulum, aday) -> bool`: `aday.kurulum == kurulum` ve: `seans_kapali` → seans `closed`/`weekend`; `yuksek_vol` → `ozellikler["atr_ratio"] >= 1.3`; `dusuk_rr` → `ozellikler["rr"] < 2.0`. Özellik yok/sayı değil → False.
- `not_yaz(aday) -> tuple[list[str], str]`: yalnız `alindi` ve `r is not None` adaylar için (aksi `ValueError`). Etiketler ML ile aynı sıra ve kurallarla üretilir: giriş (kayma `|entry_price-planned_entry|/|planned_entry-planned_stop| > 0.10` → `giris:kotu_dolum`; bilgi yoksa `giris:iyi`), stop (`stop_dist_atr` <1 dar, >3 geniş, aksi normal), seans, rejim, `olay:bilinmiyor`, uyum, kaçınılabilir, sonuç, `ders:<kimlik>` (yalnız kayıpta uyan ders kodları). Metin tek satır, sayılar 2 ondalık, bilinmeyen `yok`.
- Etiketler sözlük dışıysa `ValueError` (ML'deki `validate_tags` ile aynı).

## 3. `ders.py` — aday ders yaşam döngüsü
Durum dosyası JSON: `{ders_kimligi: {"status": "candidate"|"alive"|"retired", "born": "YYYY-MM-DD", "effect": float|None, "n": int, "retired_day"?: str}}`.
- `ders_etkisi(adaylar, kimlik, dogum_gunu, as_of, shrink_n=0) -> (etki, n)`: doğum gününün ertesi günü 00:00 UTC ≤ `ts` < `as_of` aralığındaki, `alindi` ve `r is not None` olup derse uyan adaylar; `etki = -fsum(r) * n/(n+shrink_n)`; n=0 → `(0.0, 0)`. (ML kâğıt kararı: `shrink_n = 0`.)
- `gece_adimi(adaylar, notlar, durum_yolu, gun, shrink_n=0) -> dict`: (1) `notlar` içindeki `ders:` etiketlerinden yeni kimlikler `candidate` olur (`born` = notun günü); (2) emekli olmayan her ders ölçülür: n=0 bekler; etki > 0 → `alive`; etki ≤ 0 → `retired` (+`retired_day`); emekli geri dönmez. Dönüş `{"born": [...], "alive": [...], "retired": [...]}` (sıralı). `notlar`: `[{"note_date": "YYYY-MM-DD", "tags": [...]}]`.
- `etkin_dersler(durum_yolu, limit=8) -> list[str]`: candidate+alive; alive önce, sonra etki azalan, sonra kimlik.
- `uyan_dersler(etkin, aday) -> list[str]`: karar anında adaya uyan ders kimlikleri (etiket olarak yazılır, işlemi engellemez).
- Fren ve geri alma (rapor): `fren_durumu(adaylar, etkin_kimlikler, baslangic, as_of, esik_r=10.0, geri_alma_r=3.0) -> dict` (`baslangic`: tz'li datetime ise o andan itibaren dahil; "YYYY-MM-DD" ise ertesi gün 00:00 UTC; toplam = tek tek etkilerin toplamı, shrink 0) → `{"toplam_etki": float, "fren": bool (toplam ≤ -10), "geri_al": [tek tek etkisi ≤ -3 olan kimlikler]}`. Paket yalnız bildirir; uygulamak adaptörün işi.
- Durum dosyası atomik yazılır; bozuk/eksik dosya boş durum sayılır.

## 4. Eşdeğerlik (ML ile)
- Aynı veriyle `notlar.not_yaz` ML'deki `trade_notes.build_note` ile **aynı etiket listesini** üretir (test: ML'den örnek TradeRecord/DecisionRecord → `Aday`'a çevrilip karşılaştırılır).
- `ders.ders_etkisi` ML'deki `trade_notes.lesson_effect` ile aynı sonucu verir (aynı adaylar, aynı `shrink_n`).

## 5. Yayın
- Paket kökünde `SURUM = "1.0.0"` ve `README.md` (kopyalama ve adaptör örneği: kendi işlem kayıtlarını `Aday`'a çeviren 20 satırlık örnek).
- Parça 2 (sonra): karne + sanal kasa, karşı-olgu, drift, ridge-lojistik filtre + paket (hash/süre), Telegram çekirdeği.
