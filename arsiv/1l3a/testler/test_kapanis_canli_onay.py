"""Kapanış adayı canlı kapısı: gerçek para (mod=canli) yalnız kapanis_canli_onay ile; testnet/kuru serbest (uyarı). Ağ yok."""
import logging

import pytest

from motor.canli.borsa import calistir as cal
from motor.canli.borsa import canli_ayar as ca
from motor.canli.borsa.motor_kopru import CanliDesteklemiyorHatasi

KID = "HAM:X005:664#v1"
S = {"id": KID, "api_key_env": "K1", "api_secret_env": "S1", "tahsis_usd": 60}
ONAY = {"id": KID, "tarih": "2027-02-01", "onay": "evet"}


def _ayar(mod, onay=None):
    h = {"mod": mod, "stratejiler": [S]}
    if onay is not None:
        h["kapanis_canli_onay"] = onay
    return ca.coz(h, {"CANLI_ONAY": "evet"})


@pytest.mark.parametrize("mod", ["testnet", "kuru"])
def test_testnet_ve_kuru_onaysiz_gecer_uyari_loglar(mod, caplog):
    caplog.set_level(logging.WARNING, logger="canli")
    cal.onkontrol(_ayar(mod))
    assert any(KID in r.getMessage() and mod in r.getMessage() for r in caplog.records)


def test_canli_onaysiz_reddedilir():
    with pytest.raises(CanliDesteklemiyorHatasi, match="kapanis_canli_onay"):
        cal.onkontrol(_ayar("canli"))
    with pytest.raises(CanliDesteklemiyorHatasi):
        cal.onkontrol(_ayar("canli", [{**ONAY, "id": "HAM:X005:705"}]))      # başka strateji için onay yetmez


def test_canli_onayli_gecer():
    cal.onkontrol(_ayar("canli", [ONAY]))


def test_canli_onay_env_sarti_degismedi():
    with pytest.raises(ca.CanliOnayHatasi):
        ca.coz({"mod": "canli", "stratejiler": [S], "kapanis_canli_onay": [ONAY]}, {})


def test_varsayilan_bos_liste():
    assert _ayar("testnet").kapanis_canli_onay == ()
    assert _ayar("canli", [ONAY]).kapanis_canli_onay == ((KID, "2027-02-01"),)


@pytest.mark.parametrize("bozuk", [
    "evet", {"id": KID}, [("id",)], [{"id": KID, "tarih": "2027-02-01"}],
    [{**ONAY, "onay": "hayir"}], [{**ONAY, "onay": True}], [{**ONAY, "ek": 1}],
    [{**ONAY, "tarih": "2027-13-01"}], [{**ONAY, "tarih": "01.02.2027"}], [{**ONAY, "tarih": 20270201}],
    [{**ONAY, "id": ""}], [{**ONAY, "id": 5}], [ONAY, ONAY],
])
def test_bozuk_liste_reddedilir(bozuk):
    with pytest.raises(ca.CanliAyarHatasi, match="kapanis_canli_onay"):
        ca.coz({"mod": "testnet", "stratejiler": [S], "kapanis_canli_onay": bozuk}, {})
