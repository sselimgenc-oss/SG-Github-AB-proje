"""İşlem mutabakatı Telegram uyarısı: yalnız sorun varsa (kasa tutmuyor / uyuşmazlık > 0); temiz durumda ve düzelince mesaj yok; tekrar yok; biçim; bozuk dosya."""
import json

from motor.canli import mutabakat_telegram as mt

T0 = 1_800_000_000.0


class Toplayici:
    def __init__(self):
        self.m = []

    def __call__(self, metin, **kw):
        assert kw.get("seviye") == "WARN"
        self.m.append(metin)
        return True


def _dosya(dizin, uyus=(), kasa_ok=True, ct_kasa_ok=True):
    satirlar = [{"islem_no": i, "hesap": "Aday hesabı" if i < 3 else "CT konsensüs hesabı", "coin": "BTC", "yon": "long" if i % 2 else "short",
                 "durum": "kapali"} for i in range(1, 6)]
    c = {"uretim": "2026-11-20T10:00:00Z",
         "ozet": {"islem_sayisi": 1234, "kapanan_islem": 1200, "acik_pozisyon": 34, "uyusmazlik_sayisi": len(uyus), "uyusmazliklar": list(uyus),
                  "short": {"sayi": 2}, "kasa_kontrolleri": [{"hesap": "Toplam (görünür hesaplar)", "tamam": kasa_ok},
                                                               {"hesap": "CT konsensüs hesabı", "tamam": ct_kasa_ok}]},
         "satirlar": satirlar}
    (dizin / "mutabakat_v1.json").write_text(json.dumps(c, ensure_ascii=False), encoding="utf-8")


def _u(no, hesap="Diğer hesap", tur="kasa", mesaj="x"):
    return {"islem_no": no, "hesap": hesap, "tur": tur, "mesaj": mesaj}


def test_temiz_durumda_hic_mesaj_yok(tmp_path):
    g = Toplayici()
    _dosya(tmp_path)
    assert mt.tick(tmp_path, g, T0) is False
    assert mt.tick(tmp_path, g, T0 + 7 * 3600) is False
    assert g.m == [] and mt.metin_uret(mt._oku(tmp_path / "mutabakat_v1.json")) == ""


def test_sorun_tek_gonderim_tekrar_yok_duzelince_mesaj_yok(tmp_path):
    g = Toplayici()
    _dosya(tmp_path, uyus=[_u(1, tur="kasa")])
    assert mt.tick(tmp_path, g, T0) is True
    assert mt.tick(tmp_path, g, T0 + 7 * 3600) is False       # aynı sorun: tekrar yok
    _dosya(tmp_path)                                         # düzeldi: "Düzeldi" dahil hiçbir mesaj yok
    assert mt.tick(tmp_path, g, T0 + 8 * 3600) is False
    assert len(g.m) == 1
    _dosya(tmp_path, uyus=[_u(1, tur="kasa")])               # aynı sorun yeniden çıktı: yeniden haber verilir
    assert mt.tick(tmp_path, g, T0 + 9 * 3600) is True
    assert len(g.m) == 2


def test_kasa_tutmuyorsa_uyusmazlik_olmasa_da_gider(tmp_path):
    g = Toplayici()
    _dosya(tmp_path, kasa_ok=False)
    assert mt.tick(tmp_path, g, T0) is True
    assert g.m[0].startswith("[1L3A] ⚠️ İşlem kontrolü: ") and "Kasa tutmuyor" in g.m[0]


def test_uyusmazlik_degisince_yeniden(tmp_path):
    g = Toplayici()
    _dosya(tmp_path, uyus=[_u(1)])
    assert mt.tick(tmp_path, g, T0) is True
    _dosya(tmp_path, uyus=[_u(1), _u(2)])
    assert mt.tick(tmp_path, g, T0 + 60) is True
    assert mt.tick(tmp_path, g, T0 + 120) is False
    assert len(g.m) == 2


def test_bicim(tmp_path):
    g = Toplayici()
    k = {"islem_no": 1, "hesap": "Diğer hesap", "tur": "kasa", "beklenen": "10250", "kayit": "10180", "fark": "70"}
    _dosya(tmp_path, uyus=[_u(2, "Aday hesabı", "kapanan", "kapanış panoda yok"), k, _u(3), _u(4)])
    mt.tick(tmp_path, g, T0)
    t = g.m[0]
    print(t)
    s = t.split("\n")
    assert len(s) <= 4 and "_" not in t and "Ayrıntı" not in t
    assert s[0] == "[1L3A] ⚠️ İşlem kontrolü: BTC short kapanış panoda yok"
    assert s[1] == "Kasa 10.250,00 $ olmalı, kayıtta 10.180,00 $ · fark 70,00 $"
    assert "gizli" not in t.lower() and ".json" not in t


def test_dosya_yok_veya_bozuk(tmp_path):
    g = Toplayici()
    assert mt.tick(tmp_path, g, T0) is False
    (tmp_path / "mutabakat_v1.json").write_text("{bozuk", encoding="utf-8")
    assert mt.tick(tmp_path, g, T0) is False
    (tmp_path / "mutabakat_v1.json").write_text(json.dumps({"ozet": 5}), encoding="utf-8")
    assert mt.tick(tmp_path, g, T0) is False
    assert g.m == []


def test_gonderim_basarisizsa_tekrar_denenir(tmp_path):
    _dosya(tmp_path, uyus=[_u(1)])
    assert mt.tick(tmp_path, lambda m, **k: False, T0) is False
    g = Toplayici()
    assert mt.tick(tmp_path, g, T0 + 600) is True
