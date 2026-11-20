"""Çalışırken sembol izleme: TRADING dışına düşen sembolde yeni giriş yok; WARN/CRIT/INFO; hata sessiz; saatte bir. Ağ yok (sahte)."""
import pandas as pd

from motor.canli import sembol_izleme as si
from motor.canli.telegram import Bildirimci, OrtakDurum
from testler.test_kayit_etiketleri import _paper, satirlar

T0 = pd.Timestamp("2025-03-10 12:00", tz="UTC")


class Ist:
    def __init__(self, durum="TRADING", hata=False, bos=False):
        self.durum, self.hata, self.bos, self.cagri = durum, hata, bos, 0

    def exchange_info(self):
        self.cagri += 1
        if self.hata:
            raise RuntimeError("ağ")
        if self.bos:
            return {}
        return {"symbols": [{"symbol": "XUSDT", "contractType": "PERPETUAL", "status": self.durum}]}


def _izleyici(tmp_path, ist, ad="a"):
    p, mum, bas = _paper(tmp_path / ad)
    gidenler = []
    bld = Bildirimci(gonder_fn=lambda m, *a, **k: gidenler.append(m) or True, ortak=OrtakDurum(tmp_path / ad / "ortak.json"), servis="paper")
    return p, mum, si.kur(p, ist, ["XUSDT"], bld=bld), gidenler


def _kos(p, mum):
    p.adim(mum[("XUSDT", "1d")].index[8])


def test_trading_disi_yeni_giris_yok_ve_warn(tmp_path):
    p, mum, iz, giden = _izleyici(tmp_path, Ist("SETTLING"))
    assert iz.kontrol(T0) is True
    iz.uygula()
    _kos(p, mum)
    assert not p.motor.acik and not p.motor.islemler
    assert "sembol_islem_disi" in [s["neden"] for s in satirlar(tmp_path / "a")]
    assert len(giden) == 1 and giden[0].startswith("[1L3A] ⚠️") and "XUSDT borsada işleme kapandı, yeni giriş yok" in giden[0]
    assert "XUSDT" in p.motor.engelli_semboller


def test_trading_iken_giris_normal(tmp_path):
    p, mum, iz, giden = _izleyici(tmp_path, Ist("TRADING"))
    assert iz.kontrol(T0) is False
    iz.uygula()
    _kos(p, mum)
    assert p.motor.acik and not giden


def test_acik_pozisyon_varsa_crit_zorla_kapatma_yok(tmp_path):
    p, mum, iz, giden = _izleyici(tmp_path, Ist("BREAK"))
    _kos(p, mum)
    assert p.motor.acik
    iz.kontrol(T0)
    assert len(giden) == 1 and giden[0].startswith("[1L3A] 🔴") and "açık pozisyon var" in giden[0]
    assert p.motor.acik and not p.motor.islemler                  # zorla kapatılmadı


def test_warn_6_saat_dedup(tmp_path):
    ist = Ist("BREAK")
    p, mum, iz, giden = _izleyici(tmp_path, ist)
    iz.kontrol(T0)
    ist.durum = "TRADING"
    iz.kontrol(T0 + pd.Timedelta(hours=1))                          # geri geldi: INFO
    ist.durum = "BREAK"
    iz.kontrol(T0 + pd.Timedelta(hours=2))                          # tekrar düştü: WARN 6 saat içinde bastırılır (Bildirimci saati gerçek zaman)
    assert len(giden) == 1 and giden[0].startswith("[1L3A] ⚠️")


def test_yeniden_trading_girisler_acilir_log_tan_kalir(tmp_path):
    ist = Ist("SETTLING")
    p, mum, iz, giden = _izleyici(tmp_path, ist)
    iz.kontrol(T0)
    ist.durum = "TRADING"
    assert iz.kontrol(T0 + pd.Timedelta(hours=1)) is True
    iz.kontrol(T0 + pd.Timedelta(hours=2))
    assert len(giden) == 1 and giden[0].startswith("[1L3A] ⚠️")
    iz.uygula()
    _kos(p, mum)
    assert p.motor.acik


def test_saatte_bir_ve_hata_sessiz(tmp_path):
    ist = Ist(hata=True)
    p, mum, iz, giden = _izleyici(tmp_path, ist)
    assert iz.kontrol(T0) is False and ist.cagri == 1              # hata yutulur
    iz.kontrol(T0 + pd.Timedelta(minutes=59))
    assert ist.cagri == 1                                         # saat dolmadı
    ist.hata = False
    iz.kontrol(T0 + pd.Timedelta(hours=1))
    assert ist.cagri == 2 and not giden
    ist.bos = True                                                # bozuk/boş yanıt: durum değişmez
    iz.kontrol(T0 + pd.Timedelta(hours=2))
    assert not iz.engelli and not giden


def test_listede_olmayan_sembol_delist_sayilir_ve_gizli_ad_yok(tmp_path):
    class Bos(Ist):
        def exchange_info(self):
            return {"symbols": [{"symbol": "YUSDT", "contractType": "PERPETUAL", "status": "TRADING"}]}
    p, mum, iz, giden = _izleyici(tmp_path, Bos())
    _kos(p, mum)
    iz.kontrol(T0)
    assert "XUSDT" in iz.engelli and len(giden) == 1
    assert p.tanimlar[0].kimlik not in giden[0]


def test_sessiz_modda_gonderim_yok(tmp_path):
    p, mum, _, _ = _izleyici(tmp_path, Ist("BREAK"))
    giden = []
    iz = si.kur(p, Ist("BREAK"), ["XUSDT"], bld=Bildirimci(gonder_fn=lambda m: giden.append(m) or True, ortak=OrtakDurum(tmp_path / "o.json")), sessiz=True)
    iz.kontrol(T0)
    assert not giden and "XUSDT" in iz.engelli
