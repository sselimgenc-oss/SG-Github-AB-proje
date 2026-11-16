"""python -m trader_panel --config config/panel.json"""
from __future__ import annotations

import argparse
import signal
import sys
import threading

from .data import ConfigError, PanelData, load_config
from .server import make_server


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="trader_panel")
    ap.add_argument("--config", default="config/panel.json")
    a = ap.parse_args(argv)
    try:
        cfg = load_config(a.config)
        srv = make_server(cfg, PanelData(cfg))
    except (ConfigError, OSError, RuntimeError) as e:
        print(f"trader_panel: baslatilamadi: {e}", file=sys.stderr)
        return 2
    host, port = srv.server_address[:2]
    print(f"trader_panel: http://{host}:{port} dinliyor (salt okunur)", file=sys.stderr, flush=True)
    signal.signal(signal.SIGTERM, lambda *_: threading.Thread(target=srv.shutdown, daemon=True).start())
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        srv.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
