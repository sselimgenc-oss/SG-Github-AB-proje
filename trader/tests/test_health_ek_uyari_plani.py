"""Ek saglik uyarilari (CT verisi, M1 paketi, tutarlilik): bir kez gider, en fazla 6 saatte bir hatirlatilir, kapaninca
tek 'Duzeldi'; metin sade Turkce, dosya/servis adi yok (19 Kasim: CT uyarisi her turda tekrarlaniyordu)."""
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT / "src"))

import health_run as HR  # noqa: E402
from trader_core import health as H  # noqa: E402

T0 = datetime(2026, 11, 19, 17, 20, tzinfo=timezone.utc)


def _ct(now):
    return H.Alert(H.Status.WARN, "ct_kadro_bayat", "CT verisi bayat",
                   "CT verisi bayat; trader-ct-kadro.timer ve var/ct/durum.json'a bakin.", "ct_kadro|bayat", now)


def test_bir_kez_sonra_6_saatte_bir_sonra_tek_duzeldi():
    gonderilen, durum = [], None
    for dk in range(0, 7 * 60, 5):                       # 7 saat boyunca her 5 dk'da bir saglik turu
        now = T0 + timedelta(minutes=dk)
        out, durum = HR.ek_uyari_plani([_ct(now)], durum, now)
        gonderilen += out
    assert len(gonderilen) == 2                          # ilk + 6. saatte hatirlatma
    assert gonderilen[1].created_at - gonderilen[0].created_at == timedelta(hours=6)
    m = gonderilen[0]
    assert m.title == "⚠️ Dikkat: Kopya-işlem (CT) verisi gelmiyor"
    for yasak in ("timer", "var/", ".json", "trader-", "durum.json"):
        assert yasak not in m.title and yasak not in m.body
    assert gonderilen[0].fingerprint != gonderilen[1].fingerprint     # hatirlatma Outbox tekrar onleyicisine takilmaz
    now = T0 + timedelta(hours=7, minutes=5)
    out, durum = HR.ek_uyari_plani([], durum, now)       # sorun kapandi
    assert [a.title for a in out] == ["✅ Düzeldi: CT verisi yeniden geliyor"] and out[0].level is H.Status.OK
    out, durum = HR.ek_uyari_plani([], durum, now + timedelta(minutes=5))
    assert out == [] and durum == {}                     # duzeldi yalniz bir kez


def test_tum_ek_uyarilarin_sade_metni_var():
    for fp in ("ct_kadro|bayat", "pa_proposer|stale", "pa_proposer|missing", "tutarlilik|sapma"):
        baslik, anlam, duzeldi = HR.EK_METIN[fp]
        for t in (baslik, anlam, duzeldi):
            assert "/" not in t.replace("C1", "") and ".py" not in t and "timer" not in t and t.strip()


# ---- disk doluluk uyarisi (var/ dosya sistemi >= %80 WARN, >= %95 ayrica CRIT) ----
from collections import namedtuple  # noqa: E402

_U = namedtuple("U", "total used free")


def _disk(pct):
    return lambda _p: _U(1000, pct * 10, 1000 - pct * 10)


def test_disk_esikleri_sabit():
    assert HR.DISK_UYARI_ORAN == 0.80 and HR.DISK_KRITIK_ORAN == 0.95 and HR.EK_HATIRLATMA_SAAT == 6


def test_disk_plan_durumlari():
    f = lambda pct: HR.disk_alerts({}, T0, "/x", usage_fn=_disk(pct))  # noqa: E731
    assert f(0) == [] and f(79) == []
    w = f(80)
    assert [(a.level, a.fingerprint) for a in w] == [(H.Status.WARN, "disk|dolu")] and w[0].title == "Disk dolmak üzere (%80)"
    both = f(96)
    assert [(a.level, a.fingerprint) for a in both] == [(H.Status.WARN, "disk|dolu"), (H.Status.CRIT, "disk|kritik")]
    assert [a.level for a in f(95)] == [H.Status.WARN, H.Status.CRIT]
    assert HR.disk_alerts({}, T0, "/x", usage_fn=lambda p: (_ for _ in ()).throw(OSError())) == []
    assert HR.disk_alerts({}, T0, "/x", usage_fn=lambda p: _U(0, 0, 0)) == []


def test_disk_bir_kez_6_saatte_bir_tek_duzeldi_ve_crit_ayri():
    gonderilen, durum = [], None
    for dk in range(0, 7 * 60, 5):
        now = T0 + timedelta(minutes=dk)
        out, durum = HR.ek_uyari_plani(HR.disk_alerts({}, now, "/x", usage_fn=_disk(83)), durum, now)
        gonderilen += out
    assert len(gonderilen) == 2 and gonderilen[1].created_at - gonderilen[0].created_at == timedelta(hours=6)
    assert gonderilen[0].title == "⚠️ Dikkat: Disk dolmak üzere (%83)"
    assert "/" not in gonderilen[0].body and "var" not in gonderilen[0].body
    now = T0 + timedelta(hours=7, minutes=5)
    out, durum = HR.ek_uyari_plani(HR.disk_alerts({}, now, "/x", usage_fn=_disk(96)), durum, now)   # 83 -> 96: yalniz CRIT yeni
    assert [(a.level, a.title) for a in out] == [(H.Status.CRIT, "🚨 Sorun: Disk neredeyse dolu (%96)")]
    now += timedelta(minutes=5)
    out, durum = HR.ek_uyari_plani(HR.disk_alerts({}, now, "/x", usage_fn=_disk(96)), durum, now)
    assert out == []                                     # dedup: CRIT de ikinci kez gitmez
    now += timedelta(minutes=5)
    out, durum = HR.ek_uyari_plani([], durum, now)       # kapandi: her biri icin tek Duzeldi
    assert sorted(a.title for a in out) == ["✅ Düzeldi: Disk doluluğu kritik seviyeden indi", "✅ Düzeldi: Disk doluluğu yeniden normal"]
    out, durum = HR.ek_uyari_plani([], durum, now + timedelta(minutes=5))
    assert out == [] and durum == {}
