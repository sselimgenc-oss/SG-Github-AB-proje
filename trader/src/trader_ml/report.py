"""Turkce kapi raporu (markdown)."""
from __future__ import annotations

import numpy as np

from .config import GATE, TRAIN_MEM_CAP_MB
from .gate import GateResult


def _fmt(v, nd=4):
    return "-" if v is None or (isinstance(v, float) and not np.isfinite(v)) else (f"{v:.{nd}f}" if isinstance(v, float) else str(v))


def render_report(res: GateResult, *, meta: dict, folds: list[dict], peak_rss_mb: float, synthetic: bool,
                  selected_reason: str) -> str:
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
          f"- Tepe bellek: {peak_rss_mb:.0f} MB (sunucu tavanı {TRAIN_MEM_CAP_MB} MB"
          + (" — AŞILDI: haftalık eğitim sunucu dışına alınmalı" if peak_rss_mb > TRAIN_MEM_CAP_MB else "") + ")", ""]
    L += ["## Kapı adımları (sırayla; biri kalırsa model reddedilir)", "",
          "| Adım | Sonuç | Değer | Kural |", "|---|---|---|---|"]
    for c in res.checks:
        s = "ATLANDI" if c.ok is None else ("GEÇTİ" if c.ok else "KALDI")
        L.append(f"| {c.name} | {s} | {c.value} | {c.rule} |")
    ff = res.first_failure
    L += ["", f"**Sonuç:** {'Tüm adımlar geçti.' if res.passed else 'İlk kalan adım: ' + ff.name + '.'}", ""]
    for c in res.checks:
        if c.detail:
            L.append(f"- {c.name}: {c.detail}")
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
          "- IC ve DSR hesabında adaylar bağımsız sayıldı; ardışık aday bağımlılığı bootstrap blok uzunluğuyla yalnız fark testinde hesaba katıldı.",
          f"- Eşikler önceden yazılıdır ve gevşetilmez: {GATE}.",
          "- Kapıyı geçse bile geçmiş kapı yalnız gölgeye girişe yeter (§7 notları); paraya dokunma kararı ML-3'tedir.", ""]
    return "\n".join(L)
