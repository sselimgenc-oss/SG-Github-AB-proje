#!/usr/bin/env python3
"""C1 kaldirma gocu (defter + state + kasa): tek seferlik, idempotent, yedekli. Mantik `trader_core/kol_kaldirma.py`'dadir.

Motor DURMUS olmali (install.sh durdurur; `--motor-birimi` verilirse `systemctl is-active` ile de denetlenir). Cikis kodlari:
0 = tamam / zaten yapilmis; 3 = onkosul yok (motor calisiyor ya da acik C1 pozisyonu; hicbir sey degismedi, sonra yeniden denenir);
1 = goc basarisiz (yedekten geri yuklendi; isaret yazilmadi; CRIT gunluk + Telegram). Basariliysa yedek silinir ve
var/durum/c1_goc_raporu.json yazilir (eski_kasa, yeni_kasa, silinen kayit sayilari, tetikler_dogrulandi, zaman)."""
from __future__ import annotations

import argparse
import logging
import os
import subprocess
import sys
from pathlib import Path

_HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(_HERE.parent / "src"))

from trader_core import kol_kaldirma as K  # noqa: E402
from trader_core import telegram as T  # noqa: E402

log = logging.getLogger("trader.c1_goc")


def _bildirici():
    cfg = T.TelegramConfig.from_env(os.environ)
    if cfg is None:
        return None
    client = T.TelegramClient(cfg.token)
    return lambda text: client.send_message(cfg.chat_id, text, disable_notification=False)


def _motor_aktif(birim: str):
    def f() -> bool:
        r = subprocess.run(["systemctl", "is-active", "--quiet", birim], check=False)
        return r.returncode == 0
    return f


def _wallet_start(config_dir: Path) -> float:
    from trader_engine.config import load_cli_config
    return float(load_cli_config(config_dir, "learner", "paper").wallet_start)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--var-dir", required=True)
    ap.add_argument("--config-dir", default=str(_HERE.parent / "config"))
    ap.add_argument("--motor-birimi", default=None, help="calisiyorsa goc reddedilir (orn. trader-engine@learner.service)")
    ap.add_argument("--wallet-start", type=float, default=None)
    a = ap.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
    var = Path(a.var_dir)
    try:
        ws = a.wallet_start if a.wallet_start is not None else _wallet_start(Path(a.config_dir))
        sonuc = K.calistir(var, wallet_start=ws, bildir=_bildirici(),
                           motor_aktif_fn=_motor_aktif(a.motor_birimi) if a.motor_birimi else None)
    except K.GocReddedildi as e:
        print(f"C1 gocu ertelendi: {e}", file=sys.stderr)
        return 3
    except K.GocHatasi as e:
        log.critical("C1 gocu basarisiz: %s", e)
        return 1
    except Exception as e:  # noqa: BLE001
        log.critical("C1 gocu beklenmeyen hata: %s: %s", type(e).__name__, e)
        return 1
    print(f"C1 gocu: {sonuc.get('durum')}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
