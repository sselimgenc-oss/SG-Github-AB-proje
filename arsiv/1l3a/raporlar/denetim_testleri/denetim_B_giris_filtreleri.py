"""Denetim B (giriş filtreleri / otomatik değişiklikler): her test bir bulguya karşılık gelir; hepsi KIRMIZI olmalı (hata var)."""
import inspect

import pandas as pd
import pytest

from motor.canli import alinsaydi_gevsetme as ag
from motor.canli import cikis_karsi_olgu as cko
from motor.canli import haber_etiketi as he

T0 = pd.Timestamp("2026-11-01T00:00:00Z")
SIMDI = pd.Timestamp("2026-11-20T00:00:00Z")


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


# B1 (orta): fren toplamına, aynı gecede GERİ ALINAN filtrenin R'si de giriyor
def test_fren_toplami_geri_alinan_filtreyi_saymaz(tmp_path):
    g = _servis(tmp_path, {"etiket:rejim_karsiti": [-0.4] * 10,      # toplam -4.0 -> geri al
                           "etiket:takvim_olayi": [-0.15] * 10})     # toplam -1.5 -> kalır
    geri = g.izle(SIMDI)
    assert geri == ["etiket:rejim_karsiti"]
    assert "etiket:takvim_olayi" in g.aktif            # kalan aktif toplam -1.5 > -5: fren YOK, filtre aktif kalmalı
    assert not (g.durum["fren"] or {}).get("aktif")


# B2 (düşük): fren en az örnek istemiyor (5 stop = -5R; geri-al için 10 işlem gerekirken tüm gevşetmeler askıya alınır)
def test_fren_asgari_ornek_ister(tmp_path):
    g = _servis(tmp_path, {"etiket:takvim_olayi": [-1.0] * 5})
    g.izle(SIMDI)
    assert not (g.durum["fren"] or {}).get("aktif")


# B3 (orta): askıya alınan filtre, fren bitince AYNI brüt kanıtla geri açılabiliyor (gerçekleşen net kötüydü)
def test_askidaki_filtre_ayni_kanitla_geri_acilmaz(tmp_path, monkeypatch):
    g = ag.AlinsaydiGevsetme(tmp_path, gonder=lambda m: None, saat=lambda: SIMDI, kapali_=False)
    g.durum["askida"]["etiket:kalabalik"] = {"zaman": T0.isoformat(), "kanit": {}}
    monkeypatch.setattr(g, "kanit", lambda s: {"etiket:kalabalik": {"sinyal": 12, "cozulen": 12, "toplam_r": 3.0, "ort_r": 0.25, "r": [0.25] * 12}})
    g.gevset(SIMDI)
    assert "etiket:kalabalik" not in g.aktif


# B4 (orta): pano 'Otomatik değişiklikler' kartı alinsaydi_gevsetme.json şemasını ham döküyor
def test_pano_gevsetme_durumunu_ham_dokmez():
    from motor.canli import pano
    durum = {"aktif": {"etiket:kalabalik": {"zaman": "2026-11-19T22:30:00+00:00", "kanit": {"cozulen": 12, "toplam_r": 3.0, "ort_r": 0.25, "pencere_gun": 30}}},
             "askida": {}, "kara_liste": ["etiket:rejim_karsiti"], "fren": {},
             "gecisler": [{"neden": "etiket:kalabalik", "k": "abcdef012345", "t": "2026-11-19T10:00:00+00:00"}], "son_gun": "2026-11-20"}
    html = pano._degisiklikler_karti({"alinsaydi_gevsetme": durum})
    assert "abcdef012345" not in html and "son_gun" not in html and "kara_liste" not in html
    assert "kalabalık" in html                               # aktif gevşetme okunur Türkçe satır olarak görünmeli


# B5 (orta): haber tonu alt-dize eşleşmesi: "ban" in "bank", "sue" in "issue", "rise" in "enterprise"
@pytest.mark.parametrize("baslik", ["Bank of America opens bitcoin trading desk", "Bitcoin issue tracker released by developers", "Enterprise firm unveils bitcoin custody"])
def test_haber_tonu_kelime_sinirina_uyar(baslik):
    assert he.ton(baslik) == 0


# B6 (düşük): doc "bayat veri -> null"; tüm kaynaklar düşünce eski önbellek saatlerce kullanılıyor
def test_haber_bayat_onbellek_null():
    saat = [1_800_000_000.0]
    now = pd.Timestamp(saat[0], unit="s", tz="UTC")
    tarih = (now - pd.Timedelta(minutes=5)).strftime("%a, %d %b %Y %H:%M:%S +0000")
    xml = "<rss><channel>" + "".join(f"<item><title>Bitcoin crash hack</title><pubDate>{tarih}</pubDate></item>" for _ in range(3)) + "</channel></rss>"
    ok = [True]

    def http(url):
        if not ok[0]:
            raise OSError("ag yok")
        return xml.encode()
    h = he.HaberEtiketi(http=http, saat=lambda: saat[0], kaynaklar=("a",))
    assert h.etiket("BTCUSDT", now) == (-1.0, 3)
    ok[0] = False
    saat[0] += 10 * 3600
    t2 = pd.Timestamp(saat[0], unit="s", tz="UTC")
    assert h.etiket("BTCUSDT", t2) is None                   # 10 saattir veri alınamıyor: bayat -> null


# B7 (orta/şüphe): çıkış karşı-olgusu canlı yürütücüde de bağlanıyor (alinsaydi'daki gibi canli koruması yok)
def test_cikis_karsi_olgu_canliyi_ayirir():
    assert "canli" in inspect.signature(cko.bagla).parameters
