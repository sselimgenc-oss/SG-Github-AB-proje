"""Short işaret kontrolü (motor -> pano -> Telegram): fiyat yükselince short zarar (eksi), düşünce kâr (artı). Gerçek paper_durum yolundan."""
from datetime import datetime, timezone
from decimal import Decimal
from types import SimpleNamespace

from motor.canli import pano
from motor.canli import paper_durum as pd_
from motor.canli import telegram as tg

SIMDI = datetime(2026, 1, 5, 12, 10, tzinfo=timezone.utc)


def _hesap(mark, yon=-1):
    pos = SimpleNamespace(kol=SimpleNamespace(sk="a|HYPEUSDT|15m"), sembol="HYPEUSDT", yon=yon, miktar=Decimal("1"), giris=Decimal("100"),
                          zaman=datetime(2026, 1, 5, 9, 0, tzinfo=timezone.utc), stop=Decimal("105"),
                          giris_kom=Decimal(0), cikis_kom=Decimal(0), funding=Decimal(0), brut_toplam=Decimal(0))
    m = SimpleNamespace(acik={0: pos}, son_kap={"HYPEUSDT": Decimal(str(mark))}, ozsermaye=lambda: Decimal("10000"))
    return SimpleNamespace(motor=m)


def test_acik_short_fiyat_artinca_zarar():
    (poz,) = pd_.acik_pozisyonlar(_hesap(103))
    assert poz["yon"] == "short" and Decimal(poz["kz"]) < 0 and poz["kz_oran"] == -0.03
    satir = pano._acik_satiri({**poz}, SIMDI)
    assert "−3,00 $" in satir and "−%3,00" in satir and 'class="kotu"' in satir and "+3,00" not in satir


def test_acik_short_fiyat_dusunce_kar():
    (poz,) = pd_.acik_pozisyonlar(_hesap(97))
    assert Decimal(poz["kz"]) > 0 and poz["kz_oran"] == 0.03
    satir = pano._acik_satiri({**poz}, SIMDI)
    assert "+3,00 $" in satir and "+%3,00" in satir and 'class="iyi"' in satir


def test_acik_long_kontrol():
    (poz,) = pd_.acik_pozisyonlar(_hesap(103, yon=1))
    assert Decimal(poz["kz"]) > 0 and poz["yon"] == "long"


def _kapanan(cikis, yon_s="short"):
    kol = SimpleNamespace(kimlik="k1", sk="a|HYPEUSDT|15m")
    p = SimpleNamespace(motor=SimpleNamespace(tum_kollar=[kol]))
    yon = -1 if yon_s == "short" else 1
    net = (Decimal(str(cikis)) - 100) * 1 * yon
    x = {"kol": "k1", "sembol": "HYPEUSDT", "yon": yon, "giris_zamani": datetime(2026, 1, 5, 9, 0, tzinfo=timezone.utc),
         "cikis_zamani": datetime(2026, 1, 5, 10, 0, tzinfo=timezone.utc), "giris_fiyati": 100.0, "cikis_fiyati": float(cikis), "miktar": 1.0,
         "r": float(net) / 5, "net_pnl": float(net), "funding": 0.0, "cikis_nedeni": "stop"}
    return pd_._islem_satiri(p, x)


def test_kapanan_short_zarar_pano_ve_telegram():
    s = _kapanan(103)
    assert Decimal(s["net_pnl_yerel"]) < 0 and s["yon"] == "short"
    h = pano._kapanan_satiri(s)
    assert "−3,00 $" in h and "−%3,00" in h and 'class="kotu"' in h
    t = tg.islem_kapandi_metni(s)
    assert "🔻" in t and "−3,00 $" in t and "short" in t


def test_kapanan_short_kar_pano_ve_telegram():
    s = _kapanan(97)
    assert Decimal(s["net_pnl_yerel"]) > 0
    h = pano._kapanan_satiri(s)
    assert "+3,00 $" in h and "+%3,00" in h
    assert "✅" in tg.islem_kapandi_metni(s)
