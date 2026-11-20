"""Aday paper hesapları (motor/canli/aday_paper.py): gözetmen, hesap dizinleri, başlık, imza, oto_guncelle yeni birim kurma. AĞ YOK."""
import json

import pytest

from motor.canli import aday_paper as ap
from motor.canli import oto_guncelle as og
from motor.canli import paper_v2 as v2
from testler.test_oto_guncelle import Sahte, kur_g


class SahteSurec:
    def __init__(self):
        self.canli = True

    def poll(self):
        return None if self.canli else 1

    def terminate(self):
        self.canli = False


def liste_yaz(yol, *idler):
    yol.write_text(json.dumps([{"id": i, "kart_yolu": f"x/{i}.json", "eklenme_tarihi": "2026-11-19"} for i in idler]), encoding="utf-8")


def gozetle_bir(tmp_path, liste, baslatilan):
    def baslat(k, dizin, liste_yolu):
        baslatilan.append((k["id"], dizin))
        return SahteSurec()
    return ap.gozetle(tmp_path / "taban", liste, baslat=baslat, uyku=lambda s: None, tek_sefer=True)


def test_bos_liste_ve_dosya_yok_bosta(tmp_path):
    b = []
    liste = tmp_path / "l.json"
    assert gozetle_bir(tmp_path, liste, b) == 0 and b == []          # dosya yok
    liste.write_text("[]")
    assert gozetle_bir(tmp_path, liste, b) == 0 and b == []
    assert ap.liste_yukle(ap.VARSAYILAN_LISTE) == []                  # depodaki liste boş


def test_iki_aday_iki_ayri_hesap_dizini(tmp_path):
    liste, b = tmp_path / "l.json", []
    liste_yaz(liste, "swing__a-b__kaynak", "swing__c-d__kaynak")
    gozetle_bir(tmp_path, liste, b)
    dizinler = [d for _, d in b]
    assert len(b) == 2 and len(set(dizinler)) == 2 and all(d.parent == tmp_path / "taban" for d in dizinler)


def test_liste_buyuyunce_eski_hesap_durumu_korunur(tmp_path):
    liste, b = tmp_path / "l.json", []
    liste_yaz(liste, "swing__a-b__kaynak")
    gozetle_bir(tmp_path, liste, b)
    eski = b[0][1]
    eski.mkdir(parents=True)
    (eski / "paper_state.json").write_text('{"x": 1}')
    liste_yaz(liste, "swing__a-b__kaynak", "swing__c-d__kaynak")
    b2 = []
    gozetle_bir(tmp_path, liste, b2)
    assert [i for i, _ in b2] == ["swing__a-b__kaynak", "swing__c-d__kaynak"]
    assert (eski / "paper_state.json").read_text() == '{"x": 1}' and b2[0][1] == eski      # aynı dizin, dokunulmadı


def test_calisan_alt_surec_tekrar_baslatilmaz_dusen_yeniden(tmp_path):
    liste, b, s = tmp_path / "l.json", [], []
    liste_yaz(liste, "swing__a-b__kaynak")
    t, tur = [0.0], [0]

    def baslat(k, d, l):
        b.append(k["id"])
        s.append(SahteSurec())
        return s[-1]

    def uyku(_):
        tur[0] += 1
        if tur[0] == 2:
            s[0].canli = False              # alt süreç düştü
        if tur[0] == 4:
            t[0] += 10_000                  # geri çekilme süresi doldu

    ap.gozetle(tmp_path / "t", liste, baslat=baslat, uyku=uyku, simdi=lambda: t[0], dur=lambda: tur[0] >= 5)
    assert b == ["swing__a-b__kaynak"] * 2   # 1 ilk başlatma + yalnız süre dolunca 1 yeniden


def test_bozuk_liste_hata_vermez(tmp_path):
    liste = tmp_path / "l.json"
    liste.write_text("{bozuk")
    assert gozetle_bir(tmp_path, liste, []) == 0
    with pytest.raises(ap.AdayHatasi):
        ap.liste_yukle(liste)


def test_10lu_set_imzasi_degismedi():
    assert v2.set_imzasi(v2.set_yukle()) == "fffbc6624416634e"
    assert not any("aday_paper" in json.dumps(k) for k in v2.set_yukle()["stratejiler"])


def test_telegram_basligi():
    g = []
    f = ap.baslikli(lambda m, *a, **k: g.append(m) or True, "swing__korelasyon-ivmesi-spy-hedge__quantpedia")
    f("[1L3A] ✅ islem acildi")
    f("duz metin")
    assert g[0] == "[1L3A] ✅ islem acildi · Aday hesabı"
    assert g[1] == "[1L3A] Aday hesabı\nduz metin"


def test_kodlanmamis_kart_fail_closed(tmp_path):
    kart = tmp_path / "k.json"
    kart.write_text('[{"kart_id": "x"}]')
    with pytest.raises(ap.AdayHatasi):
        ap.tanim_kur({"id": "x", "kart_yolu": str(kart)})


def test_aday_modulu_yama_uygulamaz():
    from motor.canli import paper as pp
    assert pp.PaperMotor.__name__ == "PaperMotor" and pp.paper_ayarlari().baslangic_sermaye == 10000.0
    assert ap.cp.ct_ayarlari().baslangic_sermaye == 10000.0


# ------------------------------------------------------------------------------------------------ oto_guncelle
def test_oto_guncelle_yeni_birimi_yalniz_listedeyse_kurar(tmp_path):
    g, s, _, _ = kur_g(tmp_path, Sahte(degisen=("deploy/1l3a-aday-paper.service", "deploy/1l3a-baska.service")))
    kok, sd = tmp_path / "kok" / "deploy", tmp_path / "sd"
    (kok / "1l3a-aday-paper.service").write_text("YENI")
    (kok / "1l3a-baska.service").write_text("YENI")
    g.calistir()
    assert (sd / "1l3a-aday-paper.service").read_text() == "YENI" and not (sd / "1l3a-baska.service").exists()
    k = s.komutlar()
    assert any("systemctl enable --now" in c and "1l3a-aday-paper.service" in " ".join(x) for c, x in zip(k, s.cagrilar))
    assert not any("1l3a-baska" in " ".join(x) for x in s.cagrilar if x[0] == "systemctl")
    assert "1l3a-aday-paper.service" in og.OTOMATIK_KURULACAK
