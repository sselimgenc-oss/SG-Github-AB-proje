"""Hazirlik 8: bellek butcesi. Tum MemoryMax toplamlari 2 GB RAM + 4 GB takas (install.sh) ve baska projenin payi ile karsilastirilir."""
from __future__ import annotations

import re

from readiness_support import DEPLOY, install_text, unit_kv

RAM_MB, SWAP_MB = 2048, 4096
DAEMONS = ["trader-feed.service", "trader-engine@.service", "trader-panel.service", "trader-telegram.service"]
ONESHOTS = ["trader-health.service", "trader-backup.service", "trader-veto.service", "trader-lesson.service", "trader-panel-publish.service"]


def _mem(name: str):
    for k, v in unit_kv((DEPLOY / name).read_text(encoding="utf-8")):
        if k == "MemoryMax":
            m = re.fullmatch(r"(\d+)M", v)
            assert m, (name, v)
            return int(m.group(1))
    return None


def test_every_long_running_and_heavy_unit_has_memory_max():
    for n in DAEMONS + ONESHOTS:
        assert _mem(n) is not None, n
    # sinirsiz kalanlar yalniz kisa omurlu, hafif tek seferlik birimler
    assert _mem("trader-counterfactual@.service") is not None
    unlimited = {p.name for p in DEPLOY.glob("trader-*.service") if _mem(p.name) is None}
    assert unlimited == {"trader-health-fail@.service", "trader-telegram-report.service"}, unlimited


def test_memory_budget_sums():
    always = _mem("trader-feed.service") + 2 * _mem("trader-engine@.service") + _mem("trader-panel.service") + _mem("trader-telegram.service")
    transient = sum(_mem(n) for n in ONESHOTS)
    cf = 2 * _mem("trader-counterfactual@.service")      # gece isi: ogrenen + ikiz ayni anda (RandomizedDelaySec ile kayabilir ama en kotu durum ust uste)
    worst = always + transient + cf
    assert always == 350 + 2 * 350 + 64 + 96 == 1210
    assert _mem("trader-counterfactual@.service") == 128
    assert worst == 1210 + 64 + 96 + 256 + 256 + 400 + 2 * 128 == 2538
    # her zaman acik birimlerin SERT tavan toplami RAM'in %60'ini gecmez; boylece baska proje icin >= 800 MB kalir (OS ~150 MB dahil degil)
    assert always <= 0.6 * RAM_MB
    # en kotu ust uste binme bile RAM + takas icinde (OOM yerine takas); RAM'i asar -> swappiness=10 ve takas 4 GB sart
    assert worst < RAM_MB + SWAP_MB
    assert worst > RAM_MB          # belgelenen risk: tum tavanlar ayni anda dolarsa takasa girilir (denetim raporu OPEN-9)
    t = install_text()
    assert 'SWAP_SIZE="4G"' in t and "vm.swappiness=10" in t


def test_soft_cap_below_hard_cap_and_swap_not_unbounded():
    for n in ("trader-feed.service", "trader-engine@.service"):
        kv = dict(unit_kv((DEPLOY / n).read_text(encoding="utf-8")))
        assert int(kv["MemoryHigh"][:-1]) < int(kv["MemoryMax"][:-1])
        assert kv["CPUQuota"] == "60%"


def test_budget_assumes_twin_default_on_and_installed_units_unchanged():
    """OPEN-4: ikiz varsayilan acik -> 2 motor tavani her zaman acik toplama zaten dahil (yukaridaki 1210 MB)."""
    t = install_text()
    assert re.search(r"^WITH_TWIN=1$", t, re.M) and "--no-twin) WITH_TWIN=0" in t
    assert "enable_now trader-engine@twin.service" in t
    # yeni birimler (veto-hmac env) bellek tavanlarini degistirmez; telegram-report hala sinirsiz hafif tek seferlik
    assert _mem("trader-telegram.service") == 96


def test_engine_retry_oneshot_is_bounded():
    assert _mem("trader-engine-retry@.service") == 64   # kisa omurlu, saglik birimiyle ayni tavan (toplam butceye eklenmez: saglikla ayni anda nadiren)


# ---- WP-D: trader.slice + OOM onceligi ----
def _kv(name: str) -> dict[str, str]:
    return dict(unit_kv((DEPLOY / name).read_text(encoding="utf-8")))


def test_trader_slice_exists_with_provisional_caps():
    p = DEPLOY / "trader.slice"
    assert p.exists()
    txt = p.read_text(encoding="utf-8")
    kv = _kv("trader.slice")
    assert kv["MemoryHigh"] == "1100M" and kv["MemoryMax"] == "1300M"
    assert "[Slice]" in txt
    assert "GECICI" in txt and "48" in txt          # sayilar gecici; 48 saatlik olcumle kesinlesir
    assert int(kv["MemoryHigh"][:-1]) < int(kv["MemoryMax"][:-1]) < RAM_MB * 0.7


def test_every_service_in_trader_slice():
    units = sorted(DEPLOY.glob("trader-*.service"))
    assert units
    for p in units:
        assert _kv(p.name).get("Slice") == "trader.slice", p.name


def test_oom_score_adjust_policy():
    assert _kv("trader-panel-publish.service")["OOMScoreAdjust"] == "500"
    # motor ve feed son oldurulur (negatif deger root yonetici tarafindan uygulanir; sandbox engellemez)
    for n in ("trader-engine@.service", "trader-feed.service"):
        assert int(_kv(n)["OOMScoreAdjust"]) < 0, n
    # baska hicbir birim pozitif/negatif ayar almaz
    others = {p.name for p in DEPLOY.glob("trader-*.service") if "OOMScoreAdjust" in _kv(p.name)}
    assert others == {"trader-panel-publish.service", "trader-engine@.service", "trader-feed.service"}


def test_install_uninstall_handle_slice_and_publish_stays_gated():
    t = install_text()
    assert "deploy/trader.slice" in t and "/trader.slice" in t
    assert t.index("trader.slice\"") < t.index("systemctl daemon-reload")
    u = (DEPLOY / "uninstall.sh").read_text(encoding="utf-8")
    assert "trader.slice" in u
    # yayin zamanlayicisi Cloudflare anahtarlari dolmadan acilmaz (bellek verisi oncesi kapali kalir)
    assert not re.search(r"^enable_now trader-panel-publish\.timer", t, re.M)
    assert "has_value /etc/trader-panel-cf.env CLOUDFLARE_API_TOKEN" in t
    doc = (DEPLOY.parent / "docs" / "sunucu-kurulum.md").read_text(encoding="utf-8")
    assert "Bellek ölçümü" in doc and "systemd-cgtop" in doc and "MemoryCurrent" in doc and "900 MB" in doc
