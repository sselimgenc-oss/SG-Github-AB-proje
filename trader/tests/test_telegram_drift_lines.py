"""Gunluk Telegram raporuna sapma izleyicisi satirlari (docs/kagit-degerlendirme-plani.md 4.6)."""
from __future__ import annotations

import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from trader_core import telegram as T  # noqa: E402

NOW = datetime(2026, 12, 20, 18, 0, tzinfo=timezone.utc)


def z(d):
    return d.strftime("%Y-%m-%dT%H:%M:%SZ")


class Cfg:
    def __init__(self, base: Path):
        self.status_path = str(base / "status.json")
        self.ledger_path = str(base / "ledger.sqlite")
        self.health_state = ""
        self.var_dir = str(base)


def put(d: Path, age_h=1, lines=("📐 Bot beklendiği gibi davranıyor",), schema="drift/1"):
    d.mkdir(parents=True, exist_ok=True)
    (d / "drift.json").write_text(json.dumps({"schema": schema, "generated_at": z(NOW - timedelta(hours=age_h)),
                                              "report_lines": list(lines)}), encoding="utf-8")


def test_lines_learner_only_even_if_twin_dir_exists(tmp_path):
    put(tmp_path / "learner", lines=["📐 A", "📐 B"])
    put(tmp_path / "twin", lines=["📐 C"])               # DD-12: eski ikiz dizini yok sayilir
    out = T.rapor_davranis(Cfg(tmp_path / "learner"), NOW)
    assert out.splitlines() == ["📐 A", "📐 B"]


def test_missing_stale_or_bad_file_gives_single_line(tmp_path):
    (tmp_path / "learner").mkdir()
    cfg = Cfg(tmp_path / "learner")
    assert T.rapor_davranis(cfg, NOW) == "📐 Davranış değerlendirmesi henüz yok"
    put(tmp_path / "learner", age_h=36.1)
    assert T.rapor_davranis(cfg, NOW) == "📐 Davranış değerlendirmesi henüz yok"
    put(tmp_path / "learner", age_h=36)
    assert T.rapor_davranis(cfg, NOW).startswith("📐 Bot")
    (tmp_path / "learner" / "drift.json").write_text("{bozuk")
    assert T.rapor_davranis(cfg, NOW) == "📐 Davranış değerlendirmesi henüz yok"
    put(tmp_path / "learner", schema="x/1")
    assert T.rapor_davranis(cfg, NOW) == "📐 Davranış değerlendirmesi henüz yok"
    assert T.rapor_davranis(Cfg(tmp_path / "yok"), NOW) == "📐 Davranış değerlendirmesi henüz yok"


def test_twin_absent_adds_nothing(tmp_path):
    put(tmp_path / "learner", lines=["📐 A"])
    assert T.rapor_davranis(Cfg(tmp_path / "learner"), NOW) == "📐 A"


def test_default_sections_and_build_report_include_it(tmp_path):
    put(tmp_path / "learner", lines=["📐 Bot beklendiği gibi davranıyor (sıklık, maliyet, fonlama normal)"])
    cfg = Cfg(tmp_path / "learner")
    secs = T.default_sections(cfg, NOW, "2026-12-20")
    assert "Davranış" in secs
    text = T.build_report(cfg, NOW, "2026-12-20", {"Davranış": secs["Davranış"]})
    assert "📐 Bot beklendiği gibi davranıyor" in text
    # bolum patlasa bile rapor uretilir
    def boom():
        raise RuntimeError("x")
    assert "Günlük rapor" in T.build_report(cfg, NOW, "2026-12-20", {"Davranış": boom})
