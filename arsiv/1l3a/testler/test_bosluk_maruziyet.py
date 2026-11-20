"""Boşluk maruziyeti: %20 kayıp hesabı, eşik aşımında WARN, 6 saat dedup, düzeldi INFO, gizli ad yok, kripto hariç, limit/emir değişmez."""
import copy
import json
from decimal import Decimal
from types import SimpleNamespace

import pandas as pd

from motor.canli import bosluk_maruziyet as bm
from motor.canli import gunluk_ozet as go
from motor.canli import pano
from motor.canli import telegram as tg
from motor.canli.borsa.canli_limitler import CANLI_LIMITLER
from motor.risk.limitler import SERT_LIMITLER

PENCERE = pd.Timestamp("2026-11-19 20:45", tz="UTC")       # Perşembe 15:45 NY: kapanışa 15 dk
GUN_ICI = pd.Timestamp("2026-11-19 16:00", tz="UTC")       # 11:00 NY: kapanışa uzak
GIZLI_KIMLIK = "gizliAD__sirli|DK_NVDA|4h"
GORUNUR_KIMLIK = "gauss__strateji|DK_AAPL|1d"


def _hesap(kasa, pozlar):
    acik = {i: SimpleNamespace(sembol=s, miktar=Decimal(str(q)), yon=1) for i, (s, q) in enumerate(pozlar)}
    fiyat = {s: Decimal(100) for s, _ in pozlar}
    return SimpleNamespace(motor=SimpleNamespace(acik=acik, son_kap=fiyat, ozsermaye=lambda: Decimal(str(kasa))))


def _p(gorunur_poz, gizli_poz=None, kasa=10000):
    hs = {GORUNUR_KIMLIK: _hesap(kasa, gorunur_poz)}
    if gizli_poz is not None:
        hs[GIZLI_KIMLIK] = _hesap(kasa, gizli_poz)
    return SimpleNamespace(hesaplar=hs, gorunur_adlar={GORUNUR_KIMLIK})


class Bld:
    def __init__(self):
        self.t = [1_000_000.0]
        self.gonderilen = []
        self.b = tg.Bildirimci(gonder_fn=lambda m: self.gonderilen.append(m) or True, saat=lambda: self.t[0], ortak=tg.OrtakDurum(None))


def test_formul_nominal_kere_g_ve_tarihsel_en_kotu(tmp_path):
    # nominal = 100 x 150 = 15000; %20 -> 3000 / 10000 = %30; tarihsel hisse %37,58 -> %56,4
    o = bm.hesapla(bm.hesaplari_cikar(_p([("DK_AAPL", 150)])), PENCERE, esik=0.20)
    r = o["hesaplar"][0]
    assert abs(r["kayip_yuzde"] - 0.30) < 1e-9 and abs(r["tarihsel_yuzde"] - 0.5637) < 1e-4 and r["ihlal"]
    e = bm.hesapla(bm.hesaplari_cikar(_p([("DK_XAU", 100)])), PENCERE, esik=0.5)["hesaplar"][0]
    assert abs(e["tarihsel_yuzde"] - 0.3525) < 1e-9 and not e["ihlal"]


def test_esik_koddan_okunur():
    assert bm.esik_oran() == min(CANLI_LIMITLER.strateji_kill_oran, CANLI_LIMITLER.hesap_kill_oran, SERT_LIMITLER.kill_switch_dusus_yuzde / 100)


def test_esik_asiminda_warn_gizli_ad_yok(tmp_path):
    b = Bld()
    p = _p([("DK_AAPL", 150)], gizli_poz=[("DK_NVDA", 400)])
    o = bm.tur_kancasi(p, PENCERE, tmp_path, b.b)
    assert o["pencerede"] and len(b.gonderilen) == 1
    m = b.gonderilen[0]
    assert m.startswith("[1L3A] ⚠️") and "Kapanış öncesi boşluk riski" in m and "%20 boşlukta kasanın %30,0'ini" in m and "kill eşiği %20,0" in m
    assert "Diğer hesaplar (1)" in m and "gizliAD" not in m and "sirli" not in m and "DK_NVDA" not in m
    kayit = json.dumps(bm.oku(tmp_path), ensure_ascii=False)
    assert "gizliAD" not in kayit and "Diğer hesaplar (1)" in kayit


def test_pencere_disinda_uyari_yok_ama_olcum_yazilir(tmp_path):
    b = Bld()
    o = bm.tur_kancasi(_p([("DK_AAPL", 150)]), GUN_ICI, tmp_path, b.b)
    assert not o["pencerede"] and b.gonderilen == [] and bm.oku(tmp_path)["hesaplar"][0]["ihlal"]


def test_alti_saat_dedup_sonra_tekrar(tmp_path):
    b = Bld()
    p = _p([("DK_AAPL", 150)])
    bm.tur_kancasi(p, PENCERE, tmp_path, b.b)
    b.t[0] += 5 * 3600
    bm.tur_kancasi(p, PENCERE, tmp_path, b.b)
    assert len(b.gonderilen) == 1
    b.t[0] += 1.1 * 3600
    bm.tur_kancasi(p, PENCERE, tmp_path, b.b)
    assert len(b.gonderilen) == 2


def test_duzeldi_tek_info(tmp_path):
    b = Bld()
    bm.tur_kancasi(_p([("DK_AAPL", 150)]), PENCERE, tmp_path, b.b)
    kucuk = _p([("DK_AAPL", 10)])
    bm.tur_kancasi(kucuk, PENCERE, tmp_path, b.b)
    bm.tur_kancasi(kucuk, PENCERE, tmp_path, b.b)
    assert len(b.gonderilen) == 2 and b.gonderilen[1] == "[1L3A] Boşluk riski düzeldi"
    b2 = Bld()                                                  # hiç uyarı yoksa düzeldi de yok
    bos = tmp_path / "bos"
    bos.mkdir()
    bm.tur_kancasi(kucuk, PENCERE, bos, b2.b)
    assert b2.gonderilen == []


def test_kripto_hesaba_katilmaz_ayri_satir(tmp_path):
    o = bm.tur_kancasi(_p([("BTCUSDT", 500), ("DK_AAPL", 1)]), PENCERE, tmp_path, Bld().b)
    r = o["hesaplar"][0]
    assert r["hisse_emtia_nominal"] == 100 and not r["ihlal"]
    assert o["kripto"]["nominal"] == 50000 and "7/24" in o["kripto"]["not"] and "yok sayıldı" in o["kripto"]["not"]
    b = Bld()
    bm.tur_kancasi(_p([("BTCUSDT", 500)]), PENCERE, tmp_path, b.b)
    assert b.gonderilen == []


def test_limit_ve_emir_degismez(tmp_path):
    p = _p([("DK_AAPL", 150)])
    acik = copy.deepcopy({k: vars(v) for k, v in p.hesaplar[GORUNUR_KIMLIK].motor.acik.items()})
    canli, sert = copy.deepcopy(CANLI_LIMITLER), copy.deepcopy(SERT_LIMITLER)
    bm.tur_kancasi(p, PENCERE, tmp_path, Bld().b)
    assert CANLI_LIMITLER == canli and SERT_LIMITLER == sert
    assert {k: vars(v) for k, v in p.hesaplar[GORUNUR_KIMLIK].motor.acik.items()} == acik


def test_hata_paperi_dusurmez(tmp_path):
    assert bm.tur_kancasi(SimpleNamespace(), PENCERE, tmp_path, Bld().b) is None


def test_pano_karti_ve_gunluk_ozet_alani(tmp_path):
    bm.tur_kancasi(_p([("DK_AAPL", 150)], gizli_poz=[("DK_NVDA", 400)]), PENCERE, tmp_path, Bld().b)
    html = pano._bosluk_karti(bm.oku(tmp_path))
    assert "Boşluk riski" in html and "%30,0" in html and "Diğer hesaplar (1)" in html and "gizliAD" not in html
    assert "veri birikiyor" in pano._bosluk_karti(None)
    a = bm.ozet_alani(tmp_path)
    assert a["en_kotu_kayip_yuzde"] == 80.0 and a["esik_asan_hesap"] == 2 and "bosluk_riski" in go.SEMA_ALANLARI
    assert bm.ozet_alani(tmp_path / "yok") is None
