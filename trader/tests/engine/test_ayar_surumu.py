"""6c: etkin yapilandirma hash'i (ayar_surumu): kararli, degisiklikte degisir; status.json'da (karar defterine yazilmaz: denklik testleri bit bit ayni kalir)."""
from __future__ import annotations

from pathlib import Path

from trader_core import giris_izi as GI
from trader_engine.config import apply_overrides, load_engine_config

CFG = Path(__file__).resolve().parents[2] / "config"


def _c(**kw):
    return apply_overrides(load_engine_config(CFG / "engine.base.json", CFG / "engine.learner.json"), **kw)


def test_hash_kararli_ve_degisiklige_duyarli():
    a, b = _c(), _c()
    assert GI.ayar_sha256(a) == GI.ayar_sha256(b) and len(GI.ayar_sha256(a)) == 64
    assert GI.ayar_kisa(a) == GI.ayar_sha256(a)[:12]
    assert GI.ayar_sha256(_c(leverage=4)) != GI.ayar_sha256(a)


def test_status_tam_hash_ve_karar_defterine_yazilmaz(tmp_path):
    from trader_engine import gates
    from trader_engine.status import StatusWriter
    cfg = _c()
    import datetime as dt

    class Saat:
        def now(self):
            return dt.datetime(2026, 1, 1, tzinfo=dt.timezone.utc)
    sw = StatusWriter(str(tmp_path / "status.json"), clock=Saat(), cfg=cfg)
    assert sw._ayar_sha() == GI.ayar_sha256(cfg)
    # karar defterine yazilmaz: ml kapali/golge ve kagit denklik testleri bit bit ayni kalmali
    assert "ayar_surumu" not in open(gates.__file__, encoding="utf-8").read()
