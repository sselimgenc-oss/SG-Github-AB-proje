"""Pano ölçüm kartları: sıralama, "veri birikiyor", gizli hesap adı, CT konsensüs işlemleri, 390 px (telefon) genişlikte yatay kaydırma yok."""
import json
import shutil
import subprocess
from datetime import datetime, timezone
from pathlib import Path

import pytest

from motor.canli import durum as d
from motor.canli import pano
from testler.test_pano import POZ, genis_durum
from testler.test_canli_durum import _isl

SIMDI = datetime(2026, 1, 5, 12, 10, tzinfo=timezone.utc)
GIZLI_PARCA = ["lube", "670", "574", "730"]
KART_SIRASI = ["Öğrenme", "Alınmayan sinyaller", "Etiket × sonuç", "Çıkış kanıtı", "Boşluk riski", "Karantina", "Disk", "Sembol durumu"]


def _yaz(yol, veri):
    yol.parent.mkdir(parents=True, exist_ok=True)
    yol.write_text(veri if isinstance(veri, str) else json.dumps(veri), encoding="utf-8")


def ornek_kur(kok: Path, monkeypatch, tam: bool = True) -> Path:
    """Örnek durum dizini (ana set + CT konsensüs + ölçüm dosyaları). tam=False: yalnız zorunlu dosyalar."""
    durum, ct = kok / "durum", kok / "ct"
    monkeypatch.setenv("L3A_CT_DURUM", str(ct))
    monkeypatch.setenv("L3A_ADAY_DURUM", str(kok / "aday"))
    monkeypatch.setenv("L3A_DISK_KOK", str(kok / "diskkok"))
    p = genis_durum()
    p["saglik"]["karantina"] = {"gorunur": ["dis__gauss-stoch-eth"], "gizli": 1} if tam else {"gorunur": [], "gizli": 0}
    p["islemler"].append({**_isl("2026-01-05T09:00:00Z", "dis__lube|BTCUSDT|1h")})
    if tam:
        p["ekstra"]["olaylar"] += [{"zaman": "2026-01-05T08:00:00Z", "tur": "sembol_islem_disi", "mesaj": "LUNAUSDT borsada işleme kapandı, açık pozisyon var; yeni giriş yok"}]
    d.yaz_hepsi(durum, **p, yazildi=d.zaman_oku("2026-01-05T12:05:00Z"))
    if not tam:
        return durum
    _yaz(durum / "ogrenme_karne.json", {"zaman": "x", "karne": {"dis_ewo_ema_ofset": {"aday": 12, "alinan": 9, "ort_r_alinan": 0.31},
                                                                  "dis_lube": {"aday": 5, "alinan": 5, "ort_r_alinan": 0.5}}})
    _yaz(durum / "ogrenme_ders.json", {"a:dis_ewo_ema_ofset": {"status": "alive", "born": "2026-01-01", "effect": 0.1, "n": 5},
                                       "b:dis_lube": {"status": "alive", "born": "2026-01-01", "effect": 0.1, "n": 5}})
    _yaz(durum / "ogrenme_durum.json", {"drift_uyari": ["dis_ewo_ema_ofset"]})
    _yaz(durum / "ogrenme_modeller" / "dis_ewo_ema_ofset.json", {"x": 1})
    _yaz(durum / "alinmayan_sinyaller.jsonl", "".join(json.dumps({"neden": n}) + "\n" for n in ("ml_filtre", "ml_filtre", "ders:a", "etiket:x")))
    _yaz(durum / "alinmayan_sonuc.json", {"pencere_gun": 90, "atlanan": 4, "cozulen": 3, "toplam_r": 1.5, "ort_r": 0.5,
                                          "nedenler": [{"neden": "ml_filtre", "sinyal": 2, "cozulen": 2, "toplam_r": 2.0}, {"neden": "ders:b:dis_lube", "sinyal": 1, "cozulen": 1, "toplam_r": -0.5},
                                                       {"neden": "etiket:x", "sinyal": 1, "cozulen": 0, "toplam_r": 0.0}]})
    _yaz(durum / "etiket_sonuc_v1.json", {"sema": "etiket_sonuc.v1", "birim": "R", "islem_sayisi": 3, "olculemeyen": 0,
                                          "etiketler": {"rejim_ml_1d": [{"deger": "trend_up", "islem": 2, "kazanan": 1, "isabet_yuzde": 50.0, "toplam": 1.0, "ort": 0.5}]}})
    alt = {"farley": {"n": 12, "fark_r": 3.2, "olcut_gecti": True}, "atr_iz_3": {"n": 12, "fark_r": 1.1, "olcut_gecti": False}}
    _yaz(durum / "cikis_karsi_olgu.json", {"pencere_gun": 90, "stratejiler": {"dis__gauss-stoch-eth": {"islem": 12, "alternatifler": alt},
                                                                              "dis__lube": {"islem": 9, "alternatifler": alt}}})
    _yaz(durum / "cikis_override.json", {"dis__gauss-stoch-eth": {"alternatif": "farley"}})
    _yaz(durum / "cikis_yasak.json", [["dis__lube", "atr_iz_3"]])
    _yaz(durum / "bosluk_maruziyet_v1.json", "{}")
    _yaz(kok / "diskkok" / "disk_bakim.json", {"alarm": False, "son_dondurme": 1767600000})
    ct_poz = {**POZ, "kimlik": "ct_konsensus|HYPEUSDT|15m", "sembol": "HYPEUSDT", "yon": "short", "kz": "-1.50", "kz_oran": -0.03}
    _yaz(ct / "ozet.json", {"ozsermaye": "10250.25", "toplam_pnl": "250.25", "sayaclar": {"acik_pozisyon": 1, "kapanan_islem": 1}})
    _yaz(ct / "maruziyet.json", {"pozisyonlar": [ct_poz]})
    ct_isl = {**_isl("2026-01-05T11:30:00Z", "ct_konsensus|BTCUSDT|15m"), "yon": "short", "net_pnl_yerel": "-2.40", "set_katki_usd": None, "r": -1.0}
    _yaz(ct / "islemler.jsonl", json.dumps(ct_isl) + "\n" + "{bozuk\n")
    return durum


def _html(durum) -> str:
    veri, sorun = pano.yukle(durum)
    return pano.html_olustur(veri, sorun, SIMDI)














def _node_hazir() -> bool:
    return shutil.which("node") is not None and Path("/opt/node22/lib/node_modules/playwright").exists()


@pytest.mark.skipif(not _node_hazir(), reason="playwright (node) yok")
@pytest.mark.parametrize("genislik", [390, 1280])
def test_yatay_tasma_yok(tmp_path, monkeypatch, genislik):
    html = tmp_path / "pano.html"
    html.write_text(_html(ornek_kur(tmp_path, monkeypatch)), encoding="utf-8")
    betik = (f"const {{chromium}}=require('/opt/node22/lib/node_modules/playwright');(async()=>{{const b=await chromium.launch();"
             f"const s=await b.newPage({{viewport:{{width:{genislik},height:900}},deviceScaleFactor:2}});await s.goto('file://{html}');"
             "const w=await s.evaluate(()=>document.documentElement.scrollWidth);console.log(w);await b.close()})()")
    cikti = subprocess.run(["node", "-e", betik], capture_output=True, text=True, timeout=120)
    assert cikti.returncode == 0, cikti.stderr
    assert int(cikti.stdout.strip()) <= genislik
