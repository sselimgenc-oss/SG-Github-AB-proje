"""3c: journald boyut siniri drop-in'i install.sh ile idempotent kurulur."""
from pathlib import Path

DEPLOY = Path(__file__).resolve().parents[1] / "deploy"


def test_journald_dropin_degerler_ve_idempotent_kurulum():
    conf = (DEPLOY / "trader-journald.conf").read_text(encoding="utf-8")
    for satir in ("SystemMaxUse=300M", "SystemKeepFree=1G", "MaxRetentionSec=30day"):
        assert satir in conf
    inst = (DEPLOY / "install.sh").read_text(encoding="utf-8")
    assert "/etc/systemd/journald.conf.d/trader.conf" in inst
    cmp_i = inst.index('cmp -s "$REL_DIR/deploy/trader-journald.conf" "$JD_DST"')
    assert cmp_i < inst.index("systemctl restart systemd-journald")      # yalniz degistiyse yeniden baslat
