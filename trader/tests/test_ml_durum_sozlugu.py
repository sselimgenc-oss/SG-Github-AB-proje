"""ML/Ders/Etiket ortak durum sozlugu + sahipsiz karar duzeltmesi + OZET'te iki ogrenme karti."""
from __future__ import annotations

import sys
from pathlib import Path
from types import SimpleNamespace

from trader_core import panel_pano as PP
from trader_engine.engine import Engine

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tests"))
import test_ledger_spec as T  # noqa: E402
from test_ledger_spec import clock, dbpath, led, lp  # noqa: E402,F401  (fikstürler)


def test_vocabulary_strings_and_colours():
    assert PP.ogrenme_durumu(True, True) == ("Açık, işlemleri etkiliyor", "yesil")
    assert PP.ogrenme_durumu(True, True, kol=(2, 34)) == ("Açık, işlemleri etkiliyor · 2/34 kol", "yesil")
    assert PP.ogrenme_durumu(True, False, 6, 10) == ("Açık, veri birikiyor (6/10)", "sari")
    assert PP.ogrenme_durumu(True, False, 10, 10, model_bekliyor=True) == ("Açık, model bekleniyor", "sari")
    assert PP.ogrenme_durumu(False, False, 6, 10) == ("Kapalı", "gri")


def test_ml_running_without_packages_is_not_kapali():
    ctx = SimpleNamespace(decisions=[], closed=[], dec={})
    ml = PP.ml_view("/nonexistent/x/ledger.sqlite", ctx, T.BASE, {"calisiyor": True, "aktif_kurulum": 0})
    assert ml["durum"].startswith("Açık, veri birikiyor (0/10)") and ml["renk"] == "sari"
    kapali = PP.ml_view("/nonexistent/x/ledger.sqlite", ctx, T.BASE, {"calisiyor": False, "aktif_kurulum": 0})
    assert kapali["durum"] == "Kapalı" and kapali["renk"] == "gri"


def test_kismi_durum_uses_vocabulary_when_no_arm_active():
    ml = {"durum": "Açık, veri birikiyor (6/10)", "kapsam": {"aktif": 0, "toplam": 34, "en_az": 10, "eksik": []}}
    assert PP.kismi_durum(None, ml) == ["Makine öğrenmesi: Açık, veri birikiyor (6/10)"]


def test_ozet_always_has_ders_then_ml_cards():
    js = (ROOT / "src/trader_panel/static/panel.js").read_text(encoding="utf-8")
    ozet = js.split("function tabOzet")[1].split("function isikKart")[0]
    assert ozet.index("'Ders öğrenmesi'") < ozet.index("'Makine öğrenmesi'")
    assert "if (p.ders)" not in ozet and "if (p.ml)" not in ozet
    assert "Henüz ders yok" in ozet and "Son 7 günde değiştirdiği işlem" in ozet


def _eng(led, in_flight=()):
    st = SimpleNamespace(decision_ids_in_flight=lambda: set(in_flight))
    return SimpleNamespace(ledger=led, state=st)


def test_orphan_entered_decision_is_superseded_on_start(lp, clock):
    d1 = lp.record_decision(T.dec())
    clock.advance(hours=2)
    assert lp.find_orphan_decisions(older_than_s=3600) == [d1]
    assert Engine._reconcile_orphan_decisions(_eng(lp)) == 1
    assert lp.find_orphan_decisions(older_than_s=3600) == []
    cur = [d for d in lp.list_decisions() if d.supersedes_id == d1]
    assert cur and cur[0].final_action == "skipped" and cur[0].skip_reason == "order_failed"


def test_orphan_with_live_position_is_left_alone(lp, clock):
    d1 = lp.record_decision(T.dec())
    clock.advance(hours=2)
    assert Engine._reconcile_orphan_decisions(_eng(lp, {d1})) == 0
    assert lp.find_orphan_decisions(older_than_s=3600) == [d1]


def test_health_and_telegram_text_plain_turkish():
    from trader_core import tg_sade
    assert "işlemleri etkilemez" in tg_sade.__dict__.get("SAGLIK_KODLARI", {}).get("orphan_decisions", ("",))[0] \
        or "işlemleri etkilemez" in Path(tg_sade.__file__).read_text(encoding="utf-8")
