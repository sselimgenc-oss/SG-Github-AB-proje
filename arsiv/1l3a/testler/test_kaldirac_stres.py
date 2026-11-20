"""araclar/kaldirac_stres.py: boşluk kaybı formülü ve geçici limit gevşetmenin geri alınması."""
from araclar import kaldirac_stres as ks
from motor.portfoy import motor as pm
from motor.risk.limitler import SERT_LIMITLER


def test_bosluk_kaybi_brut_carpi_bosluk():
    assert abs(ks.boslukla_kayip(3.0, 0.05) - 15.0) < 1e-9
    assert abs(ks.boslukla_kayip(5.0, 0.15) - 75.0) < 1e-9


def test_limit_gevset_geri_alir_ve_dosyayi_degistirmez():
    once = pm.SERT_LIMITLER
    with ks.limit_gevset(5, ks.PROFILLER["canli"]):
        assert pm.SERT_LIMITLER.max_kaldirac == 5.0
        assert pm.SERT_LIMITLER.islem_basi_max_risk_yuzde == 1.5
    assert pm.SERT_LIMITLER is once
    assert SERT_LIMITLER.max_kaldirac == 3.0 and SERT_LIMITLER.kill_switch_dusus_yuzde == 20.0
