#!/usr/bin/env python3
"""research/runs/*.json + trades_enriched.csv -> Turkce rapor (backtest-raporu-v1.md)."""
import json
from pathlib import Path

import numpy as np
import pandas as pd

R = Path(__file__).resolve().parent
ROOT = R.parent
OUT = ROOT.parent / "otonom-trading-arastirma" / "backtest-raporu-v1.md"
runs = {p.stem: json.loads(p.read_text()) for p in sorted((R / "runs").glob("*.json"))}


def enr(i):
    return pd.read_csv(ROOT / "user_data/backtest_results" / i / "trades_enriched.csv", parse_dates=["open_date", "close_date"])


def f(x, n=2, pct=False):
    if x is None or (isinstance(x, float) and (x != x)):
        return "–"
    if isinstance(x, float) and np.isinf(x):
        return "∞"
    return f"{x:.{n}f}".replace(".", ",") + ("%" if pct else "")


def ci(i):
    r = enr(i)["R"].dropna()
    se = r.std() / np.sqrt(len(r))
    return r.mean() - 1.96 * se, r.mean() + 1.96 * se, r.std()


def cost_r(i):
    t = enr(i)
    return float(((t["fee_paid"] - t["funding"]) / t["risk_amt"]).mean())


MAIN = ["1h_IS_f2_s2", "1h_WF_f2_s2", "15m_IS_f2_s2", "15m_WF_f2_s2"]
ARMS = [(1, 0), (1, 2), (1, 5), (2, 0), (2, 2), (2, 5)]
L = []
A = L.append

# ---------------------------------------------------------------- baslik/ozet
m = {i: runs[i] for i in MAIN}
A("# TraderV1 backtest değerlendirmesi (plan madde 14) — rapor v1\n")
A("_Tarih: 16 Kasım 2026 · Strateji: `TraderV1` (kural mantığı, risk/rejim/defter modülleri ve parametre varsayılanları DEĞİŞTİRİLMEDİ) · HOLDOUT (20260501–20261101) ve Kasım 2026 BU RAPORDA ÇALIŞTIRILMADI._\n")
A("## 0. Sade dilde özet\n")
a, b, c, d = (m[i] for i in MAIN)
A(f"""* **Geleceği görme (lookahead) / özyinelemeli (recursive) hata yok.** Göstergelerde hiçbir sızıntı bulunmadı (en büyük özyineleme sapması %0,003). Çiftler birlikte koşulunca freqtrade tek bir "biased entry" işaretledi; bunun nedeni portföy bağlaşımı (çiftler arası risk kilidi), gerçek sızıntı değil — çift başına koşularda 313 işlem sinyalinde (1h: 193, 15m: 120) sıfır sorun çıktı. Ayrıntı §2. Bu yüzden durdurma koşulu tetiklenmedi.
* **Ana karar kolunda (komisyon ×2 + 2 bp kayma, funding açık) strateji para kazandırmıyor.**
  * **1h tetik:** IS {a['n_trades']} işlem, beklenti **{f(a['expectancy_R'],3)} R** (%95 GA {f(ci(MAIN[0])[0],2)} … {f(ci(MAIN[0])[1],2)}), PF {f(a['profit_factor'])}, maks. düşüş %{f(a['max_dd_pct'],1)}; WF {b['n_trades']} işlem, **{f(b['expectancy_R'],3)} R** (GA {f(ci(MAIN[1])[0],2)} … {f(ci(MAIN[1])[1],2)}), PF {f(b['profit_factor'])}, maks. düşüş %{f(b['max_dd_pct'],1)}. Güven aralıkları sıfırı içeriyor: "kesin zararlı" da "kârlı" da denemez; ancak tahmin noktası iki dönemde de negatif.
  * **15m tetik:** IS {c['n_trades']} işlem, **{f(c['expectancy_R'],3)} R** (GA {f(ci(MAIN[2])[0],2)} … {f(ci(MAIN[2])[1],2)}), PF {f(c['profit_factor'])}; WF {d['n_trades']} işlem, **{f(d['expectancy_R'],3)} R**, PF {f(d['profit_factor'])}. Hesabın ~%90'ı eriyor. 15m kolu **her maliyet varsayımında negatif** (en ucuz kolda bile IS −0,07 R, WF −0,19 R) → 15m tetik bu haliyle elenmeli.
* **Maliyet belirleyici.** 1h kolunda brüt (maliyet öncesi) PnL pozitif ama komisyon+kayma+funding onu eritiyor: ana kolda maliyet/brüt IS {f(a['costs_over_gross'],1)}×, WF {f(b['costs_over_gross'],1)}×. En ucuz kolda (×1 komisyon, 0 bp) 1h beklentisi IS +{f(runs['1h_IS_f1_s0']['expectancy_R'],3)} R, WF +{f(runs['1h_WF_f1_s0']['expectancy_R'],3)} R (PF {f(runs['1h_IS_f1_s0']['profit_factor'])} / {f(runs['1h_WF_f1_s0']['profit_factor'])}) — başabaş civarı, gerçek kenar kanıtı değil. Kayma varsayımı (0/2/5 bp) sonucu işaret değiştirecek kadar etkili.
* **Risk kilidi ihlali yok:** hiçbir işlemin gerçekleşen zararı giriş anındaki özsermayenin %2'sini aşmadı (tüm koşularda en yüksek ≈ %1,5; hedef %1,4). Ancak zararların çoğu planlanan riskin biraz üstünde (medyan R ≈ −1,01…−1,03; maliyet + boşluk) — bu ihlal değil, bilgi (§7.2).
* **Defter ↔ freqtrade tutarlı** (eşleşen işlemlerde brüt PnL ve komisyon birebir; fark yalnız funding anlık görüntüsünden, ≤ 0,15 USDT/işlem). Tek tutarsızlık: 1h koşusunda aynı mum içinde stop sonrası yeniden girişlerin (IS'te 1, WF'de 3 işlem) deftere yazılamaması (§7.1).
* **Parametre taraması (yalnız IS, 1h, ana kol): varsayılanlar korundu.** `stop_buffer_atr` {{0,2; 0,3; 0,4}} ve `trail_atr` {{2,5; 3,0; 3,5}} denendi; komşu değerler kararsız/gürültü içinde (en iyi fark ≈ +0,07 R ≈ 1 standart hata; stop_buffer'da eğri monoton değil) ve hiçbiri pozitif beklenti üretmedi (§6).
* **Teknik bulgular (önemli):** (1) 15m tetik **canlıda başlayamaz**: startup 4800 mum, freqtrade Binance 15m için ≤2494 mumu kabul ediyor (ConfigurationError). (2) `lookahead-analysis`/`recursive-analysis` `RunMode.UTIL_NO_EXCHANGE` ile çalışır ve TraderV1 bunu "canlı" sayıp girişleri kapatır (0 işlem) — analiz için yalnız çalışma modunu eşleyen bir alt sınıf kullanıldı. (3) IS fiilen **2024-12-21**'de başlıyor (1200/4800 mum ısınma). (4) Kayma freqtrade'de yok; komisyona eklenerek yaklaşıklandı.
""")

# ---------------------------------------------------------------- 1 kapsam
A("## 1. Kapsam, yöntem ve koşu kurulumu\n")
A("""| Konu | Uygulama |
|---|---|
| Strateji / parametre | `TraderV1`, `trader_v1.params` varsayılanları (range_width_atr 4.0, vol_ratio_max 1.5, edge_zone_atr 0.25, pullback_ema 50, stop_buffer_atr 0.3, trail_atr 3.0, range_target_frac 0.75, rr_min 1.5); yalnız `trigger_tf` (1h/15m) ve sweep'teki parametre config üst-katmanıyla (`research/…/overlay.json`) değiştirildi |
| Evren | `config/base.json` beyaz listesi: BTC, ETH, BNB, SOL, XRP, DOGE, ADA, TRX, LINK, AVAX (USDT-M perpetual), kaldıraç 3×, izole, cüzdan 1000 USDT |
| Dönemler | **IS** 20241101–20251101, **WF** 20251101–20260501. **HOLDOUT 20260501–20261101 çalıştırılmadı**; Kasım 2026 hariç. (Koşucu, 20260501 sonrası zaman aralığını reddeder.) |
| Maliyet kolları | Komisyon ×1 (%0,05/taraf) ve ×2 (%0,10/taraf) × kayma 0/2/5 bp/taraf. **freqtrade backtest'te kayma seçeneği yoktur** → kayma, `--fee`'ye eklenerek yaklaşıklandı: `fee_eff = 0,0005×çarpan + kayma_bp/1e4` (giriş ve çıkışta ayrı uygulanır). Funding açık (Binance 8 saatlik funding + mark verisi; IS/WF aralığında boşluk yok). **Ana karar kolu: ×2 + 2 bp (`fee_eff` %0,12/taraf).** (×1+5bp ile ×2+0bp aynı `fee_eff`=%0,10 → koşular birebir aynı çıktı; bu bir determinizm doğrulamasıdır.) |
| Tetik kolları | 1h (`--timeframe-detail 15m` ile) ve 15m (**5m detay verisi yok** → mum-içi sıra belirsizliği 15m kolunda daha kaba; bkz. §8) |
| Çıktı | Ham sonuçlar `user_data/backtest_results/<id>/` (gitignore'da; git'e girmez); özet JSON `research/runs/<id>.json`; deneme kaydı `research/trial_registry.csv` |
| R tanımı | R = `profit_abs / risk_tutarı`; risk tutarı = **fiilen açılan miktar** için `loss_at_stop(miktar, giriş, planlanan_stop)` (risk modülünün maliyet varsayımıyla: %0,05 komisyon + %0,05 kayma/taraf). Defter `planned_risk` değeri işlemlerin ≈%2'sinde (çoğunlukla BTC/DOGE/XRP; %2–20) fiilî miktarın riskinden yüksek çıktı (miktar yuvarlama/kısma olası neden; §8, madde 1) → birincil R olarak fiilî miktar kullanıldı; defter R'si de karşılaştırıldı (ortalama mutlak fark < 0,01 R) |
| Maliyetler | `komisyon+kayma` = `miktar×(giriş×fee_open + çıkış×fee_close)`; `funding` = freqtrade `funding_fees` (işaret: + alınan, − ödenen); `brüt PnL` = `profit_abs + komisyon+kayma − funding` |
| Eniyileme yasağı | Toplam getiri, kazanma oranı ve Sharpe üzerinde seçim yapılmadı; karar ölçütleri: beklenti (R), PF, maks. düşüş, işlem sayısı ve kararlılık |
""")
A("""**Araç/yöntem notları:** `research/run_bt.py` (koşucu + metrik), `research/queue.sh` (4 paralel), `research/ft_offline_15m.py` (yalnız 15m: startup-mum korumasını atlayan yama), `research/strategies/TraderV1Analysis.py` (yalnız lookahead/recursive için çalışma-modu eşlemesi), `research/build_registry.py`, `research/make_report.py`. Tüm koşularda defter (`ledger_path`) **her koşu için yeni geçici dosya** olarak açıldı; aynı ayda defterli/deftersiz koşunun birebir aynı 81 işlemi verdiği doğrulandı (defter alım-satım davranışını değiştirmiyor). Bu sayede rejim, planlanan stop ve defter R'si her işleme bağlanabildi.
""")

# ---------------------------------------------------------------- 2 lookahead
A("## 2. Adım 1 — Lookahead ve recursive analiz\n")
A("""| Test | Komut özeti | Sonuç |
|---|---|---|
| lookahead, TraderV1 doğrudan | `lookahead-analysis --timerange 20250501-20250801` | **Teknik bulgu:** 0/10 işlem; "too few trades". Neden: komut `RunMode.UTIL_NO_EXCHANGE` ile çalışır; `TraderV1._is_bt` yalnız BACKTEST/HYPEROPT'ta doğrudur → "canlı yol" → `_gate()` → `ledger_unconfigured` → giriş yok |
| lookahead, `TraderV1Analysis` (yalnız `_BACKTEST_MODES`'a UTIL_NO_EXCHANGE eklenir; sinyal/risk/çıkış kodu aynı) — 10 çift birlikte | 208 işlem, ilk 20 analiz | `has_bias: Yes` — **1 biased entry** (ADA/USDT 2025-05-03 13:00→17:00), 0 biased exit, **0 biased indicator** |
| aynı, her çift ayrı (1h) | 10 koşu, 193 işlem analiz | **0 biased** (entry/exit/indicator) |
| aynı, 15m tetik, her çift ayrı | 10 koşu, 120 işlem analiz | **0 biased** |
| recursive, 1h, 10 çift ayrı | `--startup-candle 200 400 800` (strateji 1200) | "No variance … found due to recursive formula"; en büyük sapma `atr_ratio` %0,003 (200 mum), 400/800/1200'de %0,000; "No lookahead bias on indicators" |
| recursive, 15m (BTC, SOL) | aynı | en büyük sapma %0,003; lookahead yok |
""")
A("""**Tek işaretin açıklaması (yanlış pozitif — portföy bağlaşımı):** freqtrade'in testi tam koşudaki işlemi, veriyi o işlemin mumuna kadar kesip **yalnız o çiftle** yeniden koşarak arar. TraderV1'in risk kilidi çiftler arası bağlıdır (aynı yön risk sınırı %4, toplam açık risk %6, özsermaye). Tam koşuda ADA'nın 05:00 sinyali "aynı yön (long) risk sınırı aşılır" ile reddedildi (DOGE/ETH/XRP long açıktı), ADA ancak 13:00'te girdi; kesilmiş tek-çift koşuda 05:00 girişi serbest kaldı ve pozisyon 13:00'te zaten açıktı → 13:00 girişi "kayboldu". Doğrulama: ADA tek-çift tam koşuda 05:00 girişi var; çoklu koşuda `risk reddi ADA … aynı yön (long)` günlüğü var; **gösterge sütunlarının hiçbiri** (`biased_indicators` boş) kesik/tam veride farklı değil; çift başına koşularda (bağlaşım yok) tüm sinyaller tutarlı. Sonuç: gerçek lookahead bulgusu yok. (Not: bu durum aracın varsayımını — çiftlerin bağımsızlığı — bozduğu için çoklu-çift lookahead sonucu bu strateji için hep gürültü içerebilir; çift başına koşu doğru ölçüttür.)
""")

# ---------------------------------------------------------------- 3 ana sonuclar
A("## 3. Ana karar kolu (komisyon ×2 + 2 bp, funding açık)\n")
A("| Metrik | 1h IS | 1h WF | 15m IS | 15m WF |\n|---|---:|---:|---:|---:|")


def row(name, fn):
    A("| " + name + " | " + " | ".join(fn(runs[i]) for i in MAIN) + " |")


row("Fiilî test başı (ısınma sonrası)", lambda d: d["backtest_start"][:10])
row("İşlem sayısı", lambda d: str(d["n_trades"]))
row("Beklenti (R/işlem)", lambda d: f(d["expectancy_R"], 3))
row("Beklenti %95 GA (R)", lambda d: "")
A("| " + "Beklenti %95 GA (R)" + " | " + " | ".join(f"{f(ci(i)[0],2)} … {f(ci(i)[1],2)}" for i in MAIN) + " |")
L.pop(-2)  # bos satiri at
row("Medyan R", lambda d: f(d["median_R"], 3))
row("Profit factor (net)", lambda d: f(d["profit_factor"]))
row("Maks. düşüş (hesap, %)", lambda d: f(d["max_dd_pct"], 1))
row("Toplam getiri (bilgi; ölçüt değil)", lambda d: f(d["profit_pct"], 1, True))
row("Ort. süre", lambda d: d["avg_duration"])
row("Brüt PnL (USDT)", lambda d: f(d["gross_pnl"], 0))
row("Komisyon+kayma toplamı (USDT)", lambda d: f(d["fees_total"], 0))
row("  – bunun kayma payı (yaklaşık)", lambda d: f(d["slip_approx"], 0))
row("Funding (ödenen +, alınan −; USDT)", lambda d: f(d["funding_paid"], 1))
row("Toplam maliyet (USDT)", lambda d: f(d["costs_total"], 0))
row("Maliyet / brüt PnL", lambda d: f(d["costs_over_gross"], 2) if d["costs_over_gross"] else "brüt ≤ 0")
row("Maliyet / brüt KAZANAN işlemler", lambda d: f(d["costs_over_gross_winners"], 2))
A("| Maliyet / işlem (R) | " + " | ".join(f(cost_r(i), 3) for i in MAIN) + " |")
row("Kazanma oranı (bilgi)", lambda d: f(d["win_rate"], 2))
A("")
A("""Yorum: Stop-loss çıkışları işlemlerin %54–57'si ve ortalama ≈ −1,03 R; kârlı çıkışlar (iz süren stop, hedef) büyük R getiriyor (aşağıda §5). Komisyon, pozisyon büyüklüğü risk-temelli (stop mesafesi dar → notional büyük) olduğundan işlem başına tablodaki "Maliyet / işlem (R)" satırı kadar (R cinsinden) tutuyor; bu, brüt kenarın büyük bölümünü yiyor. 15m'de brüt PnL bile negatif. Hesap düşüşü ve toplam getiri, bileşik büyüklük ve 5% günlük zarar kilidi nedeniyle (işlem sayısı maliyetle azalıyor: günlük zarar bütçesi reddi) R-metriklerinden daha az güvenilir.
""")

# ---------------------------------------------------------------- 4 tum kollar
A("## 4. Tüm maliyet kolları (24 koşu)\n")
A("Beklenti R cinsinden, işlem başına; T1/R1 sütunları `n / beklenti(R)`. R1 (menzil dönüşü) örneklemi küçük → **yalnız rapor, yorum yok**.\n")
A("| Tetik | Dönem | Komisyon × | Kayma bp | n | E[R] | PF | Maks. DD % | Ort. süre | Komisyon+kayma | Funding | Brüt PnL | Maliyet/brüt | T1 n / E[R] | R1 n / E[R] | Koşu |")
A("|---|---|---:|---:|---:|---:|---:|---:|---|---:|---:|---:|---:|---|---|---|")
for tf in ["1h", "15m"]:
    for per in ["IS", "WF"]:
        for fm, sl in ARMS:
            i = f"{tf}_{per}_f{fm}_s{sl}"
            d = runs[i]
            bs = {x["key"]: x for x in d["by_setup"]}
            t1, r1 = bs.get("T1"), bs.get("R1")
            main = "**" if (fm, sl) == (2, 2) else ""
            A(f"| {tf} | {per} | {fm} | {sl} | {d['n_trades']} | {main}{f(d['expectancy_R'],3)}{main} | {f(d['profit_factor'])} | {f(d['max_dd_pct'],1)} | {d['avg_duration']} | {f(d['fees_total'],0)} | {f(d['funding_paid'],1)} | {f(d['gross_pnl'],0)} | {f(d['costs_over_gross'],2) if d['costs_over_gross'] else 'brüt≤0'} | "
              f"{t1['n'] if t1 else 0} / {f(t1['exp_R'],3) if t1 else '–'} | {r1['n'] if r1 else 0} / {f(r1['exp_R'],3) if r1 else '–'} | `{i}` |")
A("")
A("""Gözlemler: (a) 1h'de maliyet arttıkça beklenti monoton düşer; başabaş yaklaşık %0,05–0,08/taraf toplam maliyet (komisyon+kayma) civarındadır — yani gerçekçi (taker + kayma) maliyette kenar yok. (b) 15m'de işlem sayısı maliyetle azalır çünkü hesap küçüldükçe/günlük zarar bütçesi dolunca yeni işlemler reddedilir; 15m'de hesap düşüşü %86–91'e doyar. (c) 15m'de iz süren stop çıkışları kârlı ama stop-out'lar baskın; brüt toplam negatif.
""")

# ---------------------------------------------------------------- 5 kirilimlar
A("## 5. Kırılımlar (ana kol: ×2 + 2 bp)\n")
A("Hücre: `n / E[R] / PF`. n < 30 olan hücreler yalnız bilgi içindir (özellikle R1 ve tek çift/yön hücreleri); bu kırılımlardan parametre veya çift seçimi yapılmadı.\n")


def cell(x):
    return f"{x['n']} / {f(x['exp_R'],2)} / {f(x['pf'],2)}"


def table(title, key, order=None, rename=None):
    A(f"### {title}\n")
    A("| Grup | 1h IS | 1h WF | 15m IS | 15m WF |\n|---|---|---|---|---|")
    keys = []
    for i in MAIN:
        for x in runs[i][key]:
            if x["key"] not in keys:
                keys.append(x["key"])
    if order:
        keys = [k for k in order if k in keys] + [k for k in keys if k not in order]
    for k in keys:
        cells = []
        for i in MAIN:
            xs = {x["key"]: x for x in runs[i][key]}
            cells.append(cell(xs[k]) if k in xs else "–")
        nm = (rename or {}).get(k, k)
        A(f"| {nm} | " + " | ".join(cells) + " |")
    A("")


table("Setup (T1 = trend pullback, R1 = menzil dönüşü)", "by_setup")
table("Giriş anındaki rejim", "by_regime", order=["trend_up", "trend_down", "range", "volatile", "unclear"],
      rename={"nan": "defterde karşılığı yok (aynı mumda yeniden giriş; §7.1)"})
table("Yön", "by_side")
table("Çift", "by_pair")
table("Çıkış nedeni (freqtrade etiketi)", "by_exit")
A("""Notlar: (1) **Long taraf 1h'de iki dönemde de negatif** (IS −0,17 R n=299; WF −0,19 R n=143), **short ≈ 0** (−0,02 / +0,03). Rejim kırılımı aynı resmi verir: `trend_up` her iki dönemde negatif (−0,14 / −0,24), `trend_down` ≈ 0/+0,06. Bu, örneklem dönemindeki piyasa sürüşünden (düşüş eğilimi) kaynaklanıyor olabilir; bu raporda bir karar/parametre değişikliğine **dönüştürülmedi**, yalnız gözlem olarak kayda geçti. (2) **Çift sıralaması dönemler arasında kararsız** (ör. ADA IS +0,31 → WF −0,34; SOL +0,25 → −0,48; XRP −0,28 → +0,33): çift seçimi için dayanak yok. (3) "range / R1" IS'te −0,33 R (n=73), WF'de −0,09 R (n=40) — küçük örneklem, yalnız rapor.
""")

# ---------------------------------------------------------------- 6 jeneral
# ---------------------------------------------------------------- 7 sweep
A("## 6. Parametre taraması (yalnız IS, 1h, ana kol ×2 + 2 bp)\n")
A("""**Seçim gerekçesi:** ders-ayarlanabilir 5 parametreden (vol_ratio_max, stop_buffer_atr, trail_atr, range_target_frac, rr_min) ikisi seçildi: **`stop_buffer_atr`** — her iki kurulumda stop mesafesini belirler; stop mesafesi hem pozisyon büyüklüğünü (dar stop → büyük notional → komisyon/R yüksek) hem stop-out sıklığını (işlemlerin ≈%55'i −1R stop) belirler; **`trail_atr`** — işlemlerin ≈%88'ini oluşturan T1'in kârlı çıkışını (iz süren stop) kontrol eder ve brüt kenarın taşıyıcısıdır. `range_target_frac` ve `rr_min` yalnız R1'i etkiler (n≈73, anlamlı sonuç çıkmaz); `vol_ratio_max` bir filtre (işlem sayısını değiştirir, kenar değil). Değerler ders adımı (step) ve sınırları içinde, bir seferde bir parametre (ızgara değil): stop_buffer {0,2; **0,3**; 0,4}, trail {2,5; **3,0**; 3,5}. Toplam 4 ek koşu (varsayılan koşu yeniden kullanıldı).
""")
sw = [("stop_buffer_atr", "0,2", "1h_IS_f2_s2_sb0.2"), ("stop_buffer_atr", "0,3 (varsayılan)", "1h_IS_f2_s2"), ("stop_buffer_atr", "0,4", "1h_IS_f2_s2_sb0.4"),
      ("trail_atr", "2,5", "1h_IS_f2_s2_tr2.5"), ("trail_atr", "3,0 (varsayılan)", "1h_IS_f2_s2"), ("trail_atr", "3,5", "1h_IS_f2_s2_tr3.5")]
A("| Parametre | Değer | n | E[R] | %95 GA | PF | Maks. DD % | Brüt PnL | Komisyon+kayma | T1 E[R] | R1 E[R] (n) |\n|---|---|---:|---:|---|---:|---:|---:|---:|---:|---|")
for p, v, i in sw:
    d = runs[i]
    bs = {x["key"]: x for x in d["by_setup"]}
    lo, hi, sd = ci(i)
    A(f"| {p} | {v} | {d['n_trades']} | {f(d['expectancy_R'],3)} | {f(lo,2)} … {f(hi,2)} | {f(d['profit_factor'])} | {f(d['max_dd_pct'],1)} | {f(d['gross_pnl'],0)} | {f(d['fees_total'],0)} | {f(bs['T1']['exp_R'],3)} | {f(bs['R1']['exp_R'],3)} ({bs['R1']['n']}) |")
lo, hi, sd = ci("1h_IS_f2_s2")
A(f"""
**Sonuç: varsayılanlar korunuyor.** (i) Tek işlem R'sinin standart sapması ≈ {f(sd,2)}, n≈600 → beklentinin standart hatası ≈ 0,075 R; tüm komşu farkları (≤ 0,07 R) ≈ 1 SE içinde, yani gürültü. (ii) `stop_buffer_atr` eğrisi monoton değil (0,2: −0,065; 0,3: −0,091; 0,4: −0,020) → komşular kararsız. (iii) `trail_atr` eğrisi monoton (2,5 < 3,0 < 3,5) ama iyileşme (+0,064 R) anlamsız ve işlem sayısı düşerken (655 → 581) oluyor; 3,5 bile pozitif beklenti vermiyor (−0,027). (iv) Hiçbir kombinasyonda beklenti pozitif değil; yönlendirme olarak "daha geniş stop / daha geniş iz" hipotezi (stop_buffer 0,4, trail 3,5) ileride **bağımsız veriyle** sınanabilir; bu rapor onu WF'de denemedi (WF'yi seçimle kirletmemek için). Bu hipotezler tek gözlemden gelir; seçilmiş değil, not edilmiştir.
""")

# ---------------------------------------------------------------- 8 tutarlilik
A("## 7. Tutarlılık kontrolleri\n")
A("### 7.1 Defter ↔ freqtrade işlem listesi\n")
A("Her koşuda yeni geçici defter dosyası (`ledger.sqlite`) açıldı; `v_trades` ile freqtrade işlem listesi `(çift, giriş zamanı)` anahtarıyla eşlendi.\n")
A("| Koşu | freqtrade işlem | defter işlem | defterde karşılığı olmayan ft işlemi | Eşleşenlerde brüt PnL maks. fark | komisyon maks. fark | PnL maks. mutlak fark | PnL toplam fark (defter−ft) | Defter E[R] | Fiilî-risk E[R] |")
A("|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|")
for i in MAIN:
    lc = runs[i]["ledger_check"]
    A(f"| `{i}` | {lc['ft_trades']} | {lc['ledger_entries']} | {lc['unmatched_ft']} | ≤5e-9 | 0 | {f(lc['max_abs_pnl_diff'],3)} USDT | {f(lc['pnl_total_diff'],3)} USDT | {f(lc['ledger_exp_R'],3)} | {f(lc['actual_exp_R'],3)} |")
allu = {i: runs[i]["ledger_check"] for i in runs}
mx = max(v["max_abs_pnl_diff"] for v in allu.values())
A(f"""
Tüm {len(runs)} koşu için: eşleşen işlemlerde brüt PnL ve komisyon birebir (≤ 5e-9); PnL farkı yalnız **funding** satırından: defter `funding_paid`'i çıkış emri dolduğu anda `trade.funding_fees`'ten okur, freqtrade'in kapanışta nihai hesapladığı funding ile farklı olabilir (en büyük işlem farkı {mx:.2f} USDT; ≥ 0,10 USDT olan işlem sayısı koşu başına 0–3). **Toplam PnL farkı** (tablo) 1h koşularında esas olarak defterde hiç olmayan işlemlerden gelir (WF: üç işlemin toplamı ≈ −13,4 USDT). **Sayı farkı:** 15m koşularında defter = freqtrade (tam eşleşme). 1h koşularında defterde olmayan işlemler (IS 1, WF 3, diğer 1h kollarında benzer) **aynı sinyal mumu içinde stop sonrası yeniden girişlerdir** (`--timeframe-detail 15m` ile işlem mumun 15 dakikalık alt-mumlarında yeniden tetiklenebiliyor); defter bir karara tek `trade_id` bağlar → günlükte `giris kaydi yazilamadi: karar baska bir trade_id'ye bagli` (CRITICAL) ve çıkış kaydı da yazılamıyor. Bu yeniden girişler 1h koşusunda 7 adettir ve toplam ≈ −4…−5 R yapar (backtest'e yansıyor, deftere yansımıyor). Canlıda aynı mum içinde yeniden giriş mantığı (freqtrade sinyali aynı mumda yeniden görür) ve defterin bunu işleyememesi **ayrı bir tasarım sorunu**; bu rapor strateji kodunu değiştirmez, yalnız bildirir.
""")
A("### 7.2 Risk kilidi (işlem başına en çok %2 özsermaye) kontrolü\n")
A("Yöntem: giriş anında özsermaye tahmini = başlangıç bakiyesi + o ana kadar kapanan işlemlerin PnL'si + açık işlemlerin son 1h kapanışla gerçekleşmemiş PnL'si (strateji de `wallet + unrealized` kullanır; bu bir **tahmin**dir, komisyon/funding açık pozisyonlar için dahil değil). İhlal = `gerçekleşen zarar (komisyon+funding dahil) > %2 × özsermaye`.\n")
A("| Koşu grubu | koşu | işlem | İhlal (>%2) | En yüksek zarar/özsermaye | R < −1 olan işlem | R < −1,1 olan işlem | En kötü R |\n|---|---:|---:|---:|---:|---:|---:|---:|")
groups = {}
for i, d in runs.items():
    g = i.split("_")[0] + " " + i.split("_")[1]
    if "sb" in i or "tr" in i.split("_")[-1] and i.endswith(("2.5", "3.5")):
        g = "1h IS sweep"
    if i.endswith("rerun"):
        g = "tekrar koşuları"
    groups.setdefault(g, []).append(d)
for g, ds in groups.items():
    A(f"| {g} | {len(ds)} | {sum(x['n_trades'] for x in ds)} | {sum(x['riskcheck']['n_viol_2pct'] for x in ds)} | {max(x['riskcheck']['max_loss_pct_eq'] for x in ds)*100:.2f}% | {sum(x['riskcheck']['n_R_lt_minus1'] for x in ds)} | {sum(x['riskcheck']['n_loss_gt_1p1x_actual_risk'] for x in ds)} | {f(min(x['riskcheck']['min_R'] for x in ds),3)} |")
A("""
**İhlal listesi: boş** (hiçbir koşuda, hiçbir işlemde gerçekleşen zarar giriş özsermayesinin %2'sini aşmadı; en yüksek ≈ %1,5 — hedef %1,4, kilit %2). Bilgi amaçlı: zarar planlanan riski (R = −1) birkaç yüzde (uç durumda %35'e kadar, 15m) aşabiliyor çünkü (i) ana kolda gerçek maliyet (%0,12/taraf) risk modülünün varsayımından (%0,10/taraf) yüksek, (ii) stop dolumu mum açılışındaki boşluklarda stop fiyatının ötesinde olabilir, (iii) funding. R < −1,1 olan işlemler az (ana kolda 1h: IS 2/627, WF 1/374; 15m: IS 12/904, WF 30/745); en kötü tek işlem R = −1,35 (15m; boşluk/stop-market dolumu). Bu, kilidin işlevini bozmaz çünkü sınır %2 iken hedef %1,4'tür (≈ %43 pay); ancak **15m ×2 + 5 bp kolunda en kötü zarar ≈ %1,55'e** çıkıyor — daha yüksek maliyet/boşlukta payın azaldığını gösterir.
""")
A("### 7.3 Determinizm / yeniden üretilebilirlik\n")
rr = [i for i in runs if i.endswith("rerun")]
if rr:
    A("| Koşu | işlem | E[R] | PF | Maks. DD % | Orijinal ile işlem listesi |\n|---|---:|---:|---:|---:|---|")
    for i in rr:
        o = i.replace("_rerun", "")
        a1, a2 = enr(i), enr(o)
        k = ["pair", "open_date", "close_date", "profit_abs", "amount"]
        same = a1[k].reset_index(drop=True).equals(a2[k].reset_index(drop=True))
        A(f"| `{i}` | {runs[i]['n_trades']} | {f(runs[i]['expectancy_R'],3)} | {f(runs[i]['profit_factor'])} | {f(runs[i]['max_dd_pct'],1)} | {'birebir aynı' if same else 'FARKLI'} |")
A("""
Ek: ×1+5 bp ve ×2+0 bp koşuları (aynı `fee_eff`) birebir aynı sonucu verdi. Çalışma sırasında depodaki `ledger.py` başka bir oturumca değiştirildi (şema v2, commit 78d4b04; ana koşular v1 ile, sweep/tekrar koşuları sonrasıyla yapıldı) → tekrar koşuları işlem listesinin değişmediğini gösterir.
""")

# ---------------------------------------------------------------- 9 caveats
A("## 8. Teknik bulgular ve uyarılar (caveat)\n")
A("""1. **Piyasa meta verisi yaklaşıktır.** `scripts/freqtrade_offline.py` market listesini yerelden sentetik üretir: min. notional **5 USDT**, miktar/fiyat adımı son mumlardan türetilmiş, kaldıraç kademeleri paket içi tablodan. Gerçek borsa filtreleri (min. notional ≈ 5–100 USDT, lot adımı, fiyat adımı) farklıdır; sonuçlar bire bir değildir. Özellikle büyük adımlı çiftlerde (BTC) küçük pozisyonların reddi/yuvarlaması gerçekte farklı olur. Defterin `planned_risk`'i işlemlerin ≈%2'sinde (çoğunlukla BTC/DOGE/XRP) fiilî miktarın riskinden %2–20 yüksek çıktı; olası neden türetilmiş adıma göre miktar yuvarlama (nedeni ayrıca araştırılmadı).
2. **15m kolunda 5m detay verisi yok.** Veri seti 15m/1h/4h/1d içeriyor; 15m koşularında `--timeframe-detail` kullanılamadı → mum içinde stop ile hedef/iz stop aynı mumda ise sıra varsayımı (freqtrade'in standart kötümser kuralı) belirleyici. 1h kolu 15m detay ile koştu (daha doğru).
3. **Kayma modellenmedi, komisyona eklendi.** Gerçek kayma işlem büyüklüğü, volatilite ve stop dolumuna bağlıdır (stop-market çıkışlarda boşluk kaymaları 2–5 bp'den büyük olabilir). Komisyon ×2 taker için ihtiyatlı bir üst varsayımdır; gerçekte maker/BNB indirimi farklıdır. Bu yüzden maliyet kolları bir **duyarlılık aralığı** olarak okunmalı.
4. **Funding boşlukları.** Funding verisi 2026-10-31 16:00'a kadar (ay sonu yayımı; Kasım 2026 eksik). IS ve WF aralıklarında 8 saatlik funding kesintisiz (2190 satır/çift, boşluk yok); dolayısıyla bu raporun sonuçları bundan etkilenmez, ancak HOLDOUT'un son ayı (Ekim 2026'nın sonu) ve Kasım için funding eksik olacaktır. Funding etkisi küçük: 1h'de toplam ≈ 7–13 USDT (komisyon ≈ 400–800 USDT).
5. **IS fiilen 2024-12-21'de başlıyor** (veri 2024-11-01'de başlıyor; strateji 1200 mum (1h) / 4800 mum (15m) ısınma ve 4h rejim verisi ister) → IS ≈ 10,3 ay; kullanıcıya "12 ay" olarak sunulmamalı.
6. **15m tetik canlıda başlayamaz:** `startup_candle_count = 300·4/0,25 = 4800`; freqtrade `validate_required_startup_candles` Binance 15m için en fazla 5 çağrı × 499 = 2494 mumu kabul eder (`ConfigurationError: This strategy requires 4800 candles to start, which is more than 5x (2494 candles)`). Backtest'te yalnız `research/ft_offline_15m.py` ile (kontrolü atlayarak) koşabildi. 1h için 1200 mum (3 çağrı) uyarı verir ama geçer.
7. **`lookahead/recursive` araçları ve çalışma modu:** bu araçlar `UTIL_NO_EXCHANGE` ile koşar; TraderV1 bunu canlı sayıp girişleri kapatır. Araç uyumluluğu için `_BACKTEST_MODES` eşlemesi gerekir (alt sınıf yöntemi kullanıldı; strateji dosyası değişmedi). Çoklu çift lookahead testi portföy bağlaşımı nedeniyle yanlış pozitif verir (§2).
8. **Aynı mumda yeniden giriş (1h + detay):** stop sonrası aynı sinyal mumunda 15 dakikalık alt-mumlarda yeniden giriş mümkün (IS'te 7, WF'de 7 mum-ortası giriş; çoğu −1 R civarı zarar; defter 1–3'ünü yazamıyor). Canlıda freqtrade sinyali aynı mumda yeniden gördüğü için benzer davranış beklenir. Soğuma süresi/koruma yok.
9. **Hesap metrikleri bileşik ve doygun.** %5 günlük zarar kilidi, %6 açık risk ve min. notional nedeniyle kötü kollarda işlem sayısı maliyetle azalır ve hesap düşüşü %90 civarında doyar (15m); toplam getiri/DD bu yüzden ölçüt olarak kullanılmadı, R-bazlı beklenti ve PF kullanıldı. Maks. DD freqtrade'in kapanmış-işlem bakiyesi üzerinden hesabıdır.
10. **Çift evreni** bugünün büyük USDT-M perpetual'leri (hayatta kalanlar); evren seçimi geçmişe bakarak yapıldığı için ileriye dönük bir hayatta kalma yanlılığı olabilir (10 çiftin tamamı veri döneminde mevcuttu).
11. **Pipeline testi sırasında** WF'nin son ayı (20260401–20260501) iki kez yalnız altyapıyı doğrulamak için koşuldu (karar/parametre seçiminde kullanılmadı; kayıt defterinde `tani_*` olarak işaretli). HOLDOUT'a hiç dokunulmadı.
12. **Çalışma süresi:** 1h IS (detaylı) ≈ 9 dk, 15m IS ≈ 7 dk; strateji geri çağrıları her mumda tüm kapanmış işlemleri tarar (O(n²)), bu yüzden yıl boyu koşular dakikalar sürer.
13. **Depo eşzamanlı değişti:** çalışma boyunca başka oturumlar (veto, bütçe, ders servisi, defter şema v2) commit attı; strateji/risk/rejim/sinyal dosyaları değişmedi (yalnız `ledger.py` v2). Kayıt defterindeki `git_commit` sütunu = strateji koduna dokunan son commit (+ HEAD).
""")

# ---------------------------------------------------------------- 10 sonuc
A("## 9. Sonuç ve öneri\n")
A("""* **Teknik doğrulama:** lookahead/recursive temiz; risk kilidi ihlali yok; defter ↔ freqtrade tutarlı (aynı-mum yeniden giriş istisnası hariç).
* **Strateji değerlendirmesi:** Gerçekçi maliyette (×2 + 2 bp) 1h tetikte beklenti hem IS hem WF'de hafif negatif (GA sıfırı içeriyor), PF 0,79/0,93; 15m tetikte net negatif ve elenmeli. Brüt kenar küçük ve maliyet duyarlı; en ucuz maliyet kolunda bile kanıtlanmış bir kenar yok.
* **HOLDOUT:** açılmadı. Mevcut kanıt, holdout'un "tek seferlik" hakkını bu yapılandırmayla harcamayı desteklemiyor (ana kolda pozitif beklenti yok); karar kullanıcıda. Açılacaksa önce açık onay ve donmuş parametre/maliyet kolu gerekir.
* **Olası sonraki adımlar (kod değişikliği gerektirir, bu işin kapsamı dışında):** aynı mum içinde yeniden girişe soğuma süresi; komisyon/işlem-başına-R'yi düşürecek (daha geniş stop / daha az işlem) hipotezlerinin bağımsız veriyle testi; 15m için startup gereksiniminin düşürülmesi (aksi halde canlı başlamaz); gerçek `exchangeInfo` ile market meta verisinin doğrulanması; ledger'a aynı mumda ikinci giriş için karar-başına-çoklu işlem desteği; `lookahead-analysis` için portföy-bağımsız doğrulama modu.
""")

A("## 10. Dosyalar ve yeniden üretim\n")
A("""* Deneme kaydı: `trader/research/trial_registry.csv` (her koşu + lookahead/recursive + tanı koşuları).
* Koşu özetleri (kırılımlar dahil): `trader/research/runs/*.json`; ham sonuçlar `trader/user_data/backtest_results/<id>/` (git'te yok).
* Günlükler: `trader/research/logs/` (lookahead/recursive çıktıları, kuyruk günlüğü).
* Yeniden üretim: `PYTHONPATH=src .venv-ft/bin/python research/run_bt.py --id 1h_IS_f2_s2 --period IS --fee-mult 2 --slip-bps 2 --tf 1h` ; kuyruk: `research/queue.sh research/jobs_arms.txt`; kayıt: `research/build_registry.py`; rapor: `research/make_report.py`.
* Lookahead: `lookahead-analysis --config config/base.json --config config/backtest.json --userdir user_data --datadir user_data/data/binance --strategy TraderV1Analysis --strategy-path research/strategies --timerange 20250501-20250801 -p <çift>`.
""")
OUT.write_text("\n".join(L))
print("yazildi", OUT, len("\n".join(L)))
