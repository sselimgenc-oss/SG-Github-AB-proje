"""Ortak test duzenegi. Paper acilis kapisi (Engine._startup_gate; kural + taze 1m veri 10/10) gercek davranista
zorunludur; sahte/eski veri kullanan mevcut paper testleri (modul/oturum kapsamli fixture'lar dahil) icin varsayilan
olarak etkisiz kilinir. Kapiyi gercekten sinayan modul `REAL_STARTUP_GATE = True` tanimlar."""
import pytest

_REAL = {"on": False}


@pytest.fixture(scope="session", autouse=True)
def _neutral_startup_gate_session():
    try:
        from trader_engine.engine import Engine
    except Exception:  # noqa: BLE001 - motor import edilemiyorsa kapi yok
        yield
        return
    orig = Engine._startup_gate

    def gate(self):
        if _REAL["on"]:
            return orig(self)
        return None

    Engine._startup_gate = gate
    try:
        yield
    finally:
        Engine._startup_gate = orig


@pytest.fixture(autouse=True)
def _real_gate_for_marked_modules(request):
    _REAL["on"] = bool(getattr(request.module, "REAL_STARTUP_GATE", False))
    yield
    _REAL["on"] = False
