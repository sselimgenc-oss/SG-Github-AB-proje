"""Turkce kapi raporu (markdown)."""
from __future__ import annotations

import numpy as np

from .config import GATE, TRAIN_MEM_CAP_MB
from . import diagnostics as _diag
from . import prechecks as _pre
from .gate import GateResult


def _fmt(v, nd=4):
    return "-" if v is None or (isinstance(v, float) and not np.isfinite(v)) else (f"{v:.{nd}f}" if isinstance(v, float) else str(v))


def run_info_lines(info: dict | None) -> list[str]:
    """Koşu tablosu sayımları (r02/r03): açık kalan / çözülmemiş alınan işlemler ayrı satırlarda (sessizce atılmaz)."""
    if not info:
        return []
    g = lambda k: info.get(k, "-")
    return ["", "## Koşu tablosu sayımları (tablodan atılanlar)", "",
            f"- Dönem sonunda AÇIK kalan alınmış işlem (çıkışı yok, atıldı): {g('dropped_taken_open_at_end')}",
            f"- Etiketi çözülmemiş (son 72 mum) satır: {g('dropped_unresolved')}; bunlardan ALINMIŞ olup atılan: {g('dropped_unresolved_taken')}",
            f"- Tablo: {g('rows')} satır, alınan {g('taken')}, alınmayan {g('not_taken')}; katmanda derlemle eşleşmeyen alınmış işlem: {g('overlay_unmatched_entered')}"]


def render_report(res: GateResult, *, meta: dict, folds: list[dict], peak_rss_mb: float, synthetic: bool,
                  selected_reason: str, n_trials: int | None = None, lightgbm_version: str | None = None,
                  corpus_sha256: str | None = None, overlay_sha256: str | None = None, diagnostics: dict | None = None,
                  health: dict | None = None, power: dict | None = None,
                  calibration: dict | None = None, run_info: dict | None = None, mem_cap_mb: int = TRAIN_MEM_CAP_MB) -> str:
    L = []
    verdict = "KABUL (gölgeye girişe uygun)" if res.passed else "RED"
    L += [f"# ML terfi kapısı raporu — {verdict}", ""]
    if synthetic:
        L += ["> **UYARI:** Bu koşu SENTETİK aday tablosuyla yapıldı (19b henüz yok). Sonuçlar boru hattının "
              "çalıştığını gösterir; terfi kanıtı DEĞİLDİR.", ""]
    L += ["## Özet", "",
          f"- Seçilen model: **{res.model}** ({selected_reason})",
          f"- Eşik (dondurulmuş, eğitim dışı dilimlerde seçildi): {_fmt(res.threshold, 2) if res.threshold is not None else 'bulunamadı'}",
          f"- Tarif: `{meta['version']}` | model türü: {meta['kind']} | eğitim örneği: {meta['n_train']}",
          f"- Eğitim penceresi: {meta['train_window']['start']} → {meta['train_window']['end']}",
          f"- Kilitli dönem (2026-05 → 2026-10) okunmadı (kod korumalı).",
          f"- Model oluşturma: {meta['created_at']} | son kullanma: {meta['expires_at']} ({meta['expiry_days']} gün)",
          f"- Veri özeti: `{meta['data_hash'][:16]}…` | kod özeti: `{meta['code_hash'][:16]}…` | model özeti: `{meta['model_hash'][:16]}…`",
          f"- Özellik listesi özeti: `{meta['feature_list_hash'][:16]}…` ({len(meta['features'])} özellik)",
          f"- Korpus sha256 (aday dosyası): `{corpus_sha256 or 'yok (sentetik / dosyasız)'}`",
          *([f"- Katman (alınan işlem) sha256: `{overlay_sha256}`"] if overlay_sha256 else []),
          f"- Tarif kimliği: `{meta['version']}` | deneme sayısı (n_trials): {n_trials if n_trials is not None else '-'} | "
          f"lightgbm sürümü: {lightgbm_version or 'YOK'}",
          f"- Tepe bellek: {peak_rss_mb:.0f} MB (sunucu tavanı {mem_cap_mb} MB"
          + (" — AŞILDI: haftalık eğitim sunucu dışına alınmalı" if peak_rss_mb > mem_cap_mb else "") + ")", ""]
    L += ["## Kapı adımları (sırayla; biri kalırsa model reddedilir)", "",
          "| Adım | Sonuç | Değer | Kural |", "|---|---|---|---|"]
    for c in res.checks:
        s = "ATLANDI" if c.ok is None else ("GEÇTİ" if c.ok else "KALDI")
        L.append(f"| {c.name} | {s} | {c.value} | {c.rule} |")
    ic, ica = res.metrics.get("ic"), res.metrics.get("ic_all_rows")
    if ic:
        L += ["", f"- IC (BAĞLAYICI, yalnız alınan işlemler): rho={_fmt(ic['rho'])}, n={ic.get('n_rows', '-')} satır / {ic['n_days']} gün"]
    if ica:
        L += [f"- IC (TANI, tüm satırlar; geçti/kaldı rolü yok): rho={_fmt(ica['rho'])}, t={_fmt(ica['t'], 2)}, "
              f"n={ica['n_rows']} satır / {ica['n_days']} gün, pozitif dilim {ica['pos_folds']}/{len(ica['fold_rho'])}"]
    ff = res.first_failure
    L += ["", f"**Sonuç:** {'Tüm adımlar geçti.' if res.passed else 'İlk kalan adım: ' + ff.name + '.'}", ""]
    for c in res.checks:
        if c.detail:
            L.append(f"- {c.name}: {c.detail}")
    if health is not None:
        L += ["", "## Koşu öncesi korumalar (geçti/kaldı rolü yok; ham ihlal gerçek koşuyu reddeder)", "",
              f"- Özellik sağlığı: {health['n_features']} özellik; boş={health['all_nan'] or '-'}; sabit={health['constant'] or '-'}; "
              f"kopya={[f'{a}=={b}' for a, b in health['duplicate']] or '-'} -> {'TEMİZ' if health['ok'] else 'SAĞLIKSIZ ÖZELLİK VAR (sentetik koşuda yalnız uyarı)'}"]
        if power is not None:
            L += ["- " + power_line.strip() if i == 0 else "  " + power_line.strip() for i, power_line in enumerate(_pre.power_lines(power))]
    L += run_info_lines(run_info)
    if calibration is not None:
        cf = calibration["clamped_folds"]
        L += ["", "## Kalibrasyon (yalnız bilgi)", "",
              f"- Ağırlık şeması: `{calibration['weight_scheme']}` | Platt eğimi a>=0 kısıtı: {'AÇIK' if calibration['nonneg_slope'] else 'kapalı'}",
              "- Eğimi kısıtlanan (a<0 -> sabit p = taban oran) ileri yönlü dilim sayısı: "
              + (", ".join(f"{k}={v}/{calibration['n_folds']}" for k, v in cf.items()) or "-")]
    if diagnostics is not None:
        L += ["", "## Tanı satırları (yalnız bilgi; geçti/kaldı rolü yok)", ""] + _diag.lines(diagnostics)
    L += ["", "## Test dilimleri (genişleyen pencere, 72 mum arındırma + 24 mum ambargo)", "",
          "| Dilim | Eğitim satırı | Test satırı | Test başlangıcı | Test sonu |", "|---|---|---|---|---|"]
    for f in folds:
        L.append(f"| {f['fold']} | {len(f['train_rows'])} | {len(f['test_rows'])} | {f['test_start']:%Y-%m-%d} | {f['test_end']:%Y-%m-%d} |")
    L += ["", "## Model karşılaştırması (aynı kapı ölçüleri, yalnız bilgi)", "",
          "| Model | Eşik | Alınan oran | Filtreli net R | Filtresiz net R | Fark | Boot alt sınır |", "|---|---|---|---|---|---|---|"]
    for k, m in res.metrics["per_model"].items():
        L.append(f"| {k} | {_fmt(m['threshold'], 2) if m['feasible'] else 'yok (rapor ' + _fmt(m['threshold_used'], 3) + ')'} | "
                 f"{m['taken_frac']:.1%} | {_fmt(m['mean_filtered'])} | {_fmt(m['mean_all'])} | {_fmt(m['delta'])} | {_fmt(m['lower'])} |")
    L += ["", "## Notlar ve sınırlar", "",
          "- Evren: stratejinin aldığı adaylar (`taken`); filtresiz temel = hepsi. Örtüşen pozisyonlar ve risk payı etkileşimi modellenmedi (§3.5 yaklaşıklığı).",
          "- IC t-istatistiği ve DSR günlük (UTC) toplulaştırılmış gözlemlerle hesaplandı (aynı mum/gün adayları bağımsız sayılmaz); fark testinde ayrıca bootstrap blok uzunluğu kullanıldı.",
          "- Platt kalibrasyonu ve eşik İLERİ YÖNLÜ uyduruldu (k. dilim için yalnız önceki dilimler; ilk dilimde özdeşlik + sabit 0,50 eşik). Paketteki Platt/eşik tüm OOF'a uydurulur ve kapıda skorlanmaz.",
          "- Maliyet stresi: komisyon ×2 + 5 bp TARAF başına (tur başına 10 bp).",
          f"- Eşikler önceden yazılıdır ve gevşetilmez: {GATE}.",
          "- Kapıyı geçse bile geçmiş kapı yalnız gölgeye girişe yeter (§7 notları); paraya dokunma kararı ML-3'tedir.", ""]
    return "\n".join(L)
