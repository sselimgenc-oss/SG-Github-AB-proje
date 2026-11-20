"""Pano yeni kartlar: CT konsensüs hesabı, Aday stratejiler, Öğrenme (motor/canli/kurulum_ozeti.py ortak okuyucu). Veri yoksa "henüz veri yok"; pano asla düşmez."""
import json
from datetime import datetime, timezone

import pytest

from motor.canli import kurulum_ozeti as ko
from motor.canli import pano
from motor.canli import paper_v2 as v2
from testler.test_canli_durum import yaz

SIMDI = datetime(2026, 1, 5, 12, 10, tzinfo=timezone.utc)
SET = json.loads(v2.SET_YOLU.read_text(encoding="utf-8"))
KAYITLAR = [(v2.hesap_adi(k), v2.hesap_dizin_adi(v2.hesap_adi(k)), v2.gorunur_mu(k)) for k in SET["stratejiler"]]
GIZLI_PARCA = ["lube", "670", "574", "730"]


def _yaz(yol, veri):
    yol.parent.mkdir(parents=True, exist_ok=True)
    yol.write_text(json.dumps(veri) if not isinstance(veri, str) else veri, encoding="utf-8")


def _hesap(dizin, ozs, toplam, acik=1):
    _yaz(dizin / "ozet.json", {"ozsermaye": str(ozs), "toplam_pnl": str(toplam), "sayaclar": {"acik_pozisyon": acik, "kapanan_islem": 4}})
    _yaz(dizin / "islemler.jsonl", json.dumps({"cikis_zamani": "2026-01-05T11:00:00Z", "net_pnl_yerel": "1"}) + "\n")


def _html(dizin):
    veri, sorun = pano.yukle(dizin)
    return pano.html_olustur(veri, sorun, SIMDI)


@pytest.fixture
def ortam(tmp_path, monkeypatch):
    ct, aday = tmp_path / "ct", tmp_path / "aday"
    monkeypatch.setenv("L3A_CT_DURUM", str(ct))
    monkeypatch.setenv("L3A_ADAY_DURUM", str(aday))
    return tmp_path / "durum", ct, aday








def test_okuyucu_ders_emekli_son_7_gun():
    og = {"ders": {"a:x": {"status": "retired", "retired_day": "2026-01-03"}, "b:x": {"status": "retired", "retired_day": "2025-12-01"},
                   "c:y": {"status": "candidate"}}}
    d = ko.dersler(og, {"y"}, SIMDI)
    assert [k for k, _ in d["emekli"]] == ["a:x"] and d["aktif"] == [] and d["gizli_adet"] == 1
