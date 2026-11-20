"""Drift eylemi (ogrenme_adaptor._drift_bildir): ML filtre HEMEN yeniden eğitilir, ders çarpanı 0,5, durum JSON `drift`, tek INFO (6 saat kuralı)."""
import json
from datetime import datetime, timezone

import pandas as pd

from motor.canli import ogrenme_adaptor as oa
from motor.canli import telegram as tg
from motor.ortak_ogrenme import kayit as ok

NOW = pd.Timestamp("2026-11-19 12:00", tz="UTC")
SK = "dis__ewo"
AD = oa.temiz_ad(SK)


def _adaylar(ad, n=25, r=-3.0):
    return [ok.Aday(id=f"{ad}{i}", proje="1L3A", kurulum=ad, enstruman="XUSDT", varlik_sinifi="kripto", yon="long",
                    ts=datetime(2026, 1, 1, tzinfo=timezone.utc) + pd.Timedelta(days=i), alindi=True, r=r if i % 2 else r * 0.5,
                    ozellikler={"atr_ratio": 1.0 + i / 10}, cikis={"cikis_zamani": (datetime(2026, 1, 2, tzinfo=timezone.utc) + pd.Timedelta(days=i)).isoformat()})
            for i in range(n)]


def _og(tmp_path, giden):
    og = oa.Ogrenme(tmp_path, gonder=lambda m: True, saat=lambda: NOW)
    og.bildirimci = tg.Bildirimci(gonder_fn=lambda m: giden.append(m) or True, ortak=tg.OrtakDurum(), servis="paper")
    og.esleme.ileri(SK)
    og.kapananlar = _adaylar(AD)
    return og


def test_drift_filtreyi_hemen_egitir_carpan_yarim_durum_ve_tek_info(tmp_path, monkeypatch):
    giden, egitilen = [], []
    og = _og(tmp_path, giden)
    monkeypatch.setattr(og, "_egit_bir", lambda ad, simdi, n: egitilen.append((ad, n)) or "egitildi")
    assert og.ders_carpani(AD) == 1.0
    og._drift_bildir(og.kapananlar)
    assert egitilen == [(AD, 25)]                                              # gece adımı beklenmedi
    assert og.ders_carpani(AD) == 0.5
    d = json.loads((tmp_path / oa.DURUM_DOSYASI).read_text())["drift"]
    k = d["kurulumlar"][AD]
    assert d["uyari_sayisi"] == 1 and k["strateji"] == SK and k["ders_carpani"] == 0.5 and k["yeniden_egitim"] == "egitildi" and k["durum"] == "uyari"
    assert giden == []                                                         # "Beklenenden kötü gidiyor" Telegram'a gitmez (yalnız log)
    og._drift_bildir(og.kapananlar)                                            # aynı uyarı: tekrar eğitim yok
    assert len(egitilen) == 1 and giden == []


def test_drift_gercek_egitim_cagrilir(tmp_path):
    giden = []
    og = _og(tmp_path, giden)
    og._drift_bildir(og.kapananlar)
    k = og.durum["drift"]["kurulumlar"][AD]
    assert k["yeniden_egitim"] in ("egitildi", "model_yok") and og.durum["egitim"][AD]["n"] == 25      # gerçek filtre.egit çalıştı, durum yazıldı
    assert giden == []


def test_drift_yetersiz_veri_ve_uyari_bitince_carpan_normale(tmp_path, monkeypatch):
    giden = []
    og = _og(tmp_path, giden)
    monkeypatch.setattr(oa, "MIN_EGITIM", 1000)
    og._drift_bildir(og.kapananlar)
    assert og.durum["drift"]["kurulumlar"][AD]["yeniden_egitim"] == "yetersiz_veri"
    og.kapananlar = _adaylar(AD, 25, 3.0)                                      # iyi giden seri: uyarı yok
    og._drift_bildir(og.kapananlar)
    assert og.ders_carpani(AD) == 1.0 and og.durum["drift"]["uyari_sayisi"] == 0 and og.durum["drift"]["kurulumlar"] == {}


def test_ders_carpani_eslesen_sinyallerin_yarisinda_ders_atlatmaz(tmp_path):
    giden = []
    og = _og(tmp_path, giden)
    kimlik = "yuksek_vol:" + AD
    (tmp_path / oa.DERS_DOSYASI).write_text(json.dumps({kimlik: {"status": "alive", "born": "2026-11-01", "effect": 1.0, "n": 5}}))
    oz = {"atr_ratio": 2.0}
    normal = [og.giris_suzgeci(SK, "XUSDT", "long", oz) for _ in range(4)]
    assert normal == [(False, "ders:yuksek_vol")] * 4                           # drift yok: her eşleşmede atlatır
    og.durum["drift_uyari"] = [AD]
    sonuc = [og.giris_suzgeci(SK, "XUSDT", "long", oz) for _ in range(4)]
    assert sonuc.count((False, "ders:yuksek_vol")) == 2 and sonuc.count((True, "")) == 2   # etki yarıya indi
    assert sonuc[0] == (True, "") and sonuc[1] == (False, "ders:yuksek_vol")      # deterministik
