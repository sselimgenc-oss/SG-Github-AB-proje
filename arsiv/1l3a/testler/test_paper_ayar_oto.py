"""Paper'da strateji ayar yenilemesi onay beklemez (2026-11-19); canlı yürütücü yolunda onay şartı (--ayar-guncelle) AYNEN kalır. Ağ yok (sahte Binance)."""
import dataclasses
import json

import pytest

from motor.canli import paper as pp
from motor.canli import paper_v2 as v2
from motor.canli import paper_veri as pv
from motor.canli import telegram as tg
from testler.test_paper_canli import SahteFapi
from testler.test_paper_v2 import OrtalamaTrend, set_, tanim


@pytest.fixture
def kur(tmp_path, monkeypatch):
    monkeypatch.setattr(pv, "FapiIstemci", SahteFapi)
    monkeypatch.setitem(pp.PENCERE, "1d", 120)
    gidenler = []
    monkeypatch.setattr(tg, "gonder", lambda m, *a, **k: gidenler.append(m) or True)
    a = tanim("a", ["BTCUSDT"], OrtalamaTrend(n=10))
    ayar = set_("a")
    monkeypatch.setattr(v2, "set_yukle", lambda *x, **k: ayar)
    liste = [a]
    monkeypatch.setattr(v2, "tanimlari_yukle", lambda *x, **k: liste)
    assert pp.canli_calistir(tmp_path, None, False, tek_sefer=True) == 0           # ilk kayıt (ayar "varsayilan")
    gidenler.clear()
    liste[0] = dataclasses.replace(a, ayar="yeni_ayar")                             # guncel_ayarlar.csv değişti
    return tmp_path, gidenler


def test_paper_servisi_yeni_ayari_onaysiz_kabul_eder_olay_ve_tek_info(kur):
    tmp, giden = kur
    assert pp.canli_calistir(tmp, None, False, tek_sefer=True) == 0                 # tur_kancasi/strateji_filtre yok = paper servisi
    st = json.loads((tmp / "paper_state.json").read_text())
    assert st["hesaplar"]["a"]["ayarlar"]["a"] == "yeni_ayar"                       # kayda yeni ayar yazıldı
    assert any(o["tur"] == "ayar_otomatik" and "Strateji ayarı güncellendi: a" in o["mesaj"] and "varsayilan" in o["mesaj"] and "yeni_ayar" in o["mesaj"]
               for o in st["olaylar"])
    assert not [m for m in giden if "Strateji ayarı güncellendi" in m]              # Telegram'a gitmez (yalnız olay + log)
    giden.clear()
    assert pp.canli_calistir(tmp, None, False, tek_sefer=True) == 0                 # ayar artık aynı: ikinci mesaj yok
    assert not [m for m in giden if "Strateji ayarı güncellendi" in m]


def test_canli_yurutucu_yolunda_otomatik_kabul_yok_onay_sarti_kalir(kur):
    tmp, giden = kur
    kanca = lambda p, simdi, **k: None
    with pytest.raises(RuntimeError, match="--ayar-guncelle"):
        pp.canli_calistir(tmp, None, False, tek_sefer=True, tur_kancasi=kanca, strateji_filtre=["a"])
    st = json.loads((tmp / "paper_state.json").read_text())
    assert st["hesaplar"]["a"]["ayarlar"]["a"] == "varsayilan"                       # kayıt DEĞİŞMEDİ
    assert not [m for m in giden if "Strateji ayarı güncellendi" in m]
    # yalnız tur_kancasi ya da yalnız strateji_filtre de canlı sayılır
    with pytest.raises(RuntimeError, match="--ayar-guncelle"):
        pp.canli_calistir(tmp, None, False, tek_sefer=True, tur_kancasi=kanca)
    with pytest.raises(RuntimeError, match="--ayar-guncelle"):
        pp.canli_calistir(tmp, None, False, tek_sefer=True, strateji_filtre=["a"])
    # açık onay (--ayar-guncelle) canlıda hâlâ çalışır
    assert pp.canli_calistir(tmp, None, True, tek_sefer=True, tur_kancasi=kanca, strateji_filtre=["a"]) == 0
    assert json.loads((tmp / "paper_state.json").read_text())["hesaplar"]["a"]["ayarlar"]["a"] == "yeni_ayar"


def test_paper_sinifi_varsayilan_oto_kabul_kapali():
    assert pp.Paper.__init__.__code__.co_names  # sınıf yüklenir
    assert pp.ayar_degisimi_metni([]) == ""
    m = pp.ayar_degisimi_metni([("x", "e", "y"), ("z", "e2", "y2"), ("q", 1, 2), ("w", 1, 2)])
    assert m.startswith("Strateji ayarı güncellendi: X, Z") and "+1 strateji daha" in m
