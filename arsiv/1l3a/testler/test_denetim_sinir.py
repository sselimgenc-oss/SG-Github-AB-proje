"""Denetim: mutasyon testinde hayatta kalan sınırları kilitler (alınsaydı gevşetme: kalıcı kilit + pencere sınırları; etiket kuralları eşikleri)."""
from types import SimpleNamespace as NS

import pandas as pd
import pytest

from motor.canli import alinsaydi_gevsetme as ag
from motor.canli import etiket_kurallari as ek

T0 = pd.Timestamp("2026-11-01T00:00:00Z")
SIMDI = pd.Timestamp("2026-11-20T00:00:00Z")
S = pd.Timedelta(seconds=1)


def _servis(tmp_path, islemler):
    """islemler: {neden: [R,...]}; her işlem için bir geçiş + 1 saat sonra açılan işlem (3 gün arayla). Nedenler aktif yapılır."""
    g = ag.AlinsaydiGevsetme(tmp_path, gonder=lambda m: None, saat=lambda: SIMDI, kapali_=False)
    isl, gec = {}, []
    for n, rs in islemler.items():
        g.durum["aktif"][n] = {"zaman": T0.isoformat(), "kanit": {}}
        k = ag._kh(n)
        for i, r in enumerate(rs):
            t = T0 + pd.Timedelta(days=3 * i + 1)
            gec.append({"neden": n, "k": k, "t": t.isoformat()})
            isl.setdefault(k, []).append((t + pd.Timedelta(hours=1), r))
    g.durum["gecisler"] = gec
    g._islemler = lambda: isl
    return g


# ---------------------------------------------------------------------------------------------- ikinci fren = kalıcı kilit
def test_ikinci_frende_kalici_kilit(tmp_path):
    nedenler = {"etiket:rejim_karsiti": [-0.5] * 5, "etiket:takvim_olayi": [-0.5] * 5, "etiket:kalabalik": [-0.5] * 5}   # her biri -2.5 (<10 işlem: geri alma yok), toplam -7.5
    g = _servis(tmp_path, nedenler)
    assert g.izle(SIMDI) == []
    assert g.durum["fren"]["sayac"] == 1 and g.durum["fren"]["kalici"] is False and not g.aktif
    for n in nedenler:                                       # fren sonrası yeniden aktif (elle) -> ikinci fren
        g.durum["aktif"][n] = g.durum["askida"].pop(n)
    g.izle(SIMDI + pd.Timedelta(days=8))
    assert g.durum["fren"]["sayac"] == 2 and g.durum["fren"]["kalici"] is True


def test_fren_ve_geri_al_esikleri_tam_sinirda():
    assert ag.fren_gerekli(-5.0) and not ag.fren_gerekli(-4.99)
    assert ag.geri_al_gerekli([-0.2] * 10) and not ag.geri_al_gerekli([-0.2] * 9) and not ag.geri_al_gerekli([-0.19] * 10)


# ---------------------------------------------------------------------------------------------- geçiş -> işlem eşleme penceresi (t <= gz <= t + 2 gün)
@pytest.mark.parametrize("sapma,eslesir", [(-S, False), (pd.Timedelta(0), True), (pd.Timedelta(days=ag.GECIS_ESLEME_GUN), True),
                                           (pd.Timedelta(days=ag.GECIS_ESLEME_GUN) + S, False)])
def test_gecis_esleme_pencere_sinirlari(tmp_path, sapma, eslesir):
    g = ag.AlinsaydiGevsetme(tmp_path, gonder=lambda m: None, saat=lambda: SIMDI, kapali_=False)
    n = "etiket:takvim_olayi"
    g.durum["aktif"][n] = {"zaman": T0.isoformat(), "kanit": {}}
    t = T0 + pd.Timedelta(days=1)
    k = ag._kh(n)
    g.durum["gecisler"] = [{"neden": n, "k": k, "t": t.isoformat()}]
    g._islemler = lambda: {k: [(t + sapma, -0.7)]}
    assert g.izleme_sonucu()[n] == ([-0.7] if eslesir else [])


# ---------------------------------------------------------------------------------------------- kanıt penceresi (sinir <= zaman <= simdi)
def _kanit_sayi(tmp_path, monkeypatch, zaman) -> int:
    from araclar import alinmayan_sonuc as asn
    (tmp_path / asn.DOSYA).write_text("", encoding="utf-8")
    satir = {"zaman": zaman.isoformat(), "hesap": "h", "kol": "k", "sembol": "XUSDT", "yon": "long", "fiyat": "100", "stop": "95", "hedef": "110",
             "tf": "1d", "neden": "etiket:takvim_olayi"}
    monkeypatch.setattr(asn, "satirlari_oku", lambda d: [satir])
    monkeypatch.setattr(asn, "simule", lambda s, m: {"r": 1.0})
    g = ag.AlinsaydiGevsetme(tmp_path, gonder=lambda m: None, saat=lambda: SIMDI, kapali_=False)
    kaynak = NS(gecmis=lambda s, tf, t: pd.DataFrame({"x": [1]}))
    g._hesaplar = lambda: [NS(kaynak=kaynak)]
    return g.kanit(SIMDI).get("etiket:takvim_olayi", {}).get("sinyal", 0)


@pytest.mark.parametrize("sapma,sayilir", [(-S, False), (pd.Timedelta(0), True)])
def test_kanit_pencere_alt_sinir(tmp_path, monkeypatch, sapma, sayilir):
    assert _kanit_sayi(tmp_path, monkeypatch, SIMDI - pd.Timedelta(days=ag.PENCERE_GUN) + sapma) == (1 if sayilir else 0)


@pytest.mark.parametrize("sapma,sayilir", [(pd.Timedelta(0), True), (S, False)])
def test_kanit_pencere_ust_sinir(tmp_path, monkeypatch, sapma, sayilir):
    assert _kanit_sayi(tmp_path, monkeypatch, SIMDI + sapma) == (1 if sayilir else 0)


# ---------------------------------------------------------------------------------------------- etiket_kurallari: haber_ters
@pytest.mark.parametrize("yon,ton,sayi,beklenen", [
    ("long", -0.2, 2, None), ("long", -0.21, 2, "etiket:haber_ters"), ("long", -0.21, 1, None), ("long", 0.9, 5, None),
    ("short", 0.2, 2, None), ("short", 0.21, 2, "etiket:haber_ters"), ("short", 0.21, 1, None), ("short", -0.9, 5, None)])
def test_haber_ters_yon_ve_esik_sinirlari(yon, ton, sayi, beklenen):
    assert ek.degerlendir(yon, {"haber_tonu": ton, "haber_sayisi": sayi}) == beklenen


# ---------------------------------------------------------------------------------------------- etiket_kurallari: korku/açgözlülük 75 / 25
@pytest.mark.parametrize("yon,kg,beklenen", [
    ("long", 75, "etiket:korku_acgozluluk"), ("long", 74, None), ("long", 25, None),
    ("short", 25, "etiket:korku_acgozluluk"), ("short", 26, None), ("short", 75, None)])
def test_korku_acgozluluk_sinirlari(yon, kg, beklenen):
    assert ek.degerlendir(yon, {"korku_acgozluluk": kg}) == beklenen
