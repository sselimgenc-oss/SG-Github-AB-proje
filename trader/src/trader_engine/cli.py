"""Komut satiri (05 §9). Ince sarmalayici: agir moduller alt komut icinde tembel import edilir."""
from __future__ import annotations

import argparse
import dataclasses
import json
import logging
import signal
import sys
from pathlib import Path

EXIT_OK, EXIT_REPEATED, EXIT_FAZ_B, EXIT_ENGINE, EXIT_FINDINGS = 0, 3, 2, 4, 5
EXIT_PERMISSION = 8   # 11 §3.3: borsa yetki/izin/bolge reddi (RestartPreventExitStatus=7 8)

# 11 §3.4 acilis denetimi icin enjekte edilebilir kabuk: callable(cfg, api_key, api_secret) -> None;
# reddederse EngineExit(8, kod) firlatir. Gercek denetim LiveBroker.startup_check() (B3/B7) ile baglanir.
STARTUP_CHECKER = None


def _load_cfg(a):
    from .config import load_engine_config
    d = Path(a.config_dir)
    env = getattr(a, "env", None)
    overlay = d / f"engine.{env}.json" if env else None
    bot = getattr(a, "bot", None) or "learner"
    return load_engine_config(d / "engine.base.json", d / f"engine.{bot}.json", overlay_path=overlay)


def _live_startup(cfg, checker) -> int | None:
    """testnet/live on kosullari (11 §3.1-3.4). None => devam; aksi cikis kodu.
    Sira: anahtarlar (keys_missing, kod 2) -> acilis denetimi (ret: kod 8) -> broker yok (faz_b, kod 2).
    LIVE_CONFIRM burada denetlenir (yalniz kosu yolu; kill/pause/init-ledger/reconcile/backtest istemez).
    B3: startup_check icinde ExchangeBan/yetki -> kod 8, ulasilamaz -> kod 5 eslemesi yapilir (11 §3.4); burada
    yalniz EngineExit.code aynen iletilir."""
    import os

    from .config import check_live_confirm, load_keys
    from .engine import EngineExit
    from .errors import ConfigError
    try:
        check_live_confirm(cfg, os.environ)
        key, secret = load_keys(os.environ)
    except ConfigError as e:
        print(f"hata: {e}", file=sys.stderr)
        return EXIT_FAZ_B
    checker = checker if checker is not None else STARTUP_CHECKER
    if checker is not None:
        try:
            checker(cfg, key, secret)
        except EngineExit as e:
            print(f"acilis denetimi reddetti: {e}", file=sys.stderr)
            return e.code
    print("faz_b: testnet/live LiveBroker henuz uygulanmadi (Faz B: B3/B4)", file=sys.stderr)
    return EXIT_FAZ_B


def _cmd_run(a, *, checker=None) -> int:
    from .engine import EngineExit, build_engine
    from .errors import ConfigError, EngineError
    from .strategies.registry import StrategyError
    try:
        cfg = _load_cfg(a)
    except ConfigError as e:
        print(f"yapilandirma hatasi: {e}", file=sys.stderr)
        return EXIT_FAZ_B
    if cfg.mode in ("testnet", "live"):
        return _live_startup(cfg, checker)
    try:
        eng = build_engine(cfg)
    except StrategyError as e:
        print(f"strateji hatasi: {e.code}: {e}", file=sys.stderr)
        return EXIT_ENGINE
    except EngineError as e:
        print(f"hata: {e}", file=sys.stderr)
        return EXIT_REPEATED
    for sig in (signal.SIGTERM, signal.SIGINT):
        signal.signal(sig, lambda *_: eng.stop())
    try:
        eng.run_forever()
    except StrategyError as e:
        print(f"strateji hatasi: {e.code}: {e}", file=sys.stderr)
        return EXIT_ENGINE
    except EngineExit as e:
        return e.code
    except EngineError as e:
        print(f"hata: {e}", file=sys.stderr)
        return EXIT_REPEATED
    return EXIT_OK


def _cmd_init_ledger(a) -> int:
    from trader_core import ledger as L
    from trader_core.signals import DEFAULT_SIGNAL_PARAMS

    from .strategies.registry import StrategyError, get_strategy, make_label
    from .errors import ConfigError
    try:
        cfg = _load_cfg(a)
    except ConfigError as e:
        print(f"yapilandirma hatasi: {e}", file=sys.stderr)
        return EXIT_FAZ_B
    try:
        strat = get_strategy(a.strategy or cfg.strategy)
    except StrategyError as e:
        print(f"strateji hatasi: {e.code}: {e}", file=sys.stderr)
        return EXIT_ENGINE
    label = make_label(strat.info.name, strat.info.version)
    Path(cfg.ledger_path).parent.mkdir(parents=True, exist_ok=True)
    params = {k: getattr(DEFAULT_SIGNAL_PARAMS, k) for k in L.PARAM_KEYS}
    led = L.open_ledger(cfg.ledger_path, cfg.bot, create=True)
    try:
        try:
            led.get_active_params()
            exists = True
        except L.LedgerError:
            exists = False
        if exists and a.reason != "strategy_update":
            print("etkin parametre var: dokunulmadi")
        elif not exists:
            led.init_params(params, reason=f"{label} {a.reason}")
        else:
            vid = led.create_user_version(params, reason=f"{label} {a.reason}")
            led.activate_version(vid, actor="user", reason=f"{label} {a.reason}")
        if cfg.bot == "twin":
            lp = Path(cfg.var_dir) / "learner" / "ledger.sqlite"
            if lp.exists():
                ref = L.open_ledger(str(lp), "learner", create=False, read_only=True)
                try:
                    if ref.get_active_params().params_hash != led.get_active_params().params_hash:
                        print("twin params_hash ogrenen defterle uyusmuyor", file=sys.stderr)
                        return EXIT_ENGINE
                finally:
                    ref.close()
    finally:
        led.close()
    return EXIT_OK


def _cmd_reconcile(a) -> int:
    from .engine import build_engine
    from .engine import EngineExit
    from .errors import ConfigError
    try:
        cfg = _load_cfg(a)
    except ConfigError as e:
        print(f"yapilandirma hatasi: {e}", file=sys.stderr)
        return EXIT_FAZ_B
    if cfg.mode in ("testnet", "live"):
        print("faz_b: testnet/live reconcile henuz uygulanmadi", file=sys.stderr)
        return EXIT_FAZ_B
    eng = build_engine(cfg)
    try:
        eng.start()
    except EngineExit as e:
        return e.code
    rep = eng.reconciler.run(eng.clock.now())
    print(json.dumps({"ok": rep.ok, "fatal": rep.fatal, "actions": rep.actions, "findings": rep.findings}))
    return EXIT_OK if rep.ok else EXIT_FINDINGS


def _cmd_kill(a) -> int:
    from .clock import SystemClock
    cfg = _load_cfg(a)
    from .killswitch import Killswitch
    k = Killswitch(cfg.kill_file, SystemClock())
    if a.clear:
        k.clear()
    else:
        k.set(a.by, a.reason)
    return EXIT_OK


def _cmd_pause(a) -> int:
    """11 §9.5: duraklatma tutuslari. `remove` motor kodunda yalniz burada cagrilir (AST korumasi)."""
    from .clock import SystemClock
    from .pause import EntryPause
    cfg = _load_cfg(a)
    p = EntryPause(f"{cfg.pause_file}.{cfg.bot}", SystemClock(), audit_path=cfg.path("pause_audit.jsonl"), bot=cfg.bot)
    try:
        if a.list:
            print(json.dumps({"bot": cfg.bot, "active": p.active(),
                              "holds": [dataclasses.asdict(h) for h in p.holds()]}, ensure_ascii=False))
            return EXIT_OK
        if a.clear:
            if not a.reason or not a.by:
                print("hata: --clear icin --reason ve --by zorunlu (ornek: --reason manual --by ad)", file=sys.stderr)
                return EXIT_FAZ_B
            ok = p.remove(a.reason, a.by)
            print("kaldirildi" if ok else "tutus yok / kaldirilamadi")
            return EXIT_OK if ok else EXIT_FINDINGS
        ok = p.add(a.reason or "manual", a.by or "cli", a.note)
        print("eklendi" if ok else "zaten var / eklenemedi")
        return EXIT_OK
    except ValueError as e:
        print(f"hata: {e}", file=sys.stderr)
        return EXIT_FAZ_B


def _cmd_feed(a) -> int:
    from .marketdata import feed as F  # noqa: F401
    runner = getattr(F, "main", None)
    if runner is None:
        print("feed komutu bu surumde 01 modulunden calistirilir", file=sys.stderr)
        return EXIT_FAZ_B
    return int(runner(a.rest) or 0)


def _cmd_backtest(a) -> int:
    from . import backtest as B
    return int(B.main(a.rest) or 0)


def _cmd_rules(a) -> int:
    from .marketdata import feed as F  # noqa: F401
    runner = getattr(F, "rules_snapshot_main", None)
    if runner is None:
        print("rules-snapshot: 01 islevi bu surumde yok", file=sys.stderr)
        return EXIT_FAZ_B
    return int(runner(a.rest) or 0)


def _cmd_smoke(a) -> int:
    print("faz_b")
    return EXIT_FAZ_B


_PASSTHROUGH = {"feed": _cmd_feed, "backtest": _cmd_backtest, "rules-snapshot": _cmd_rules}


def build_parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(prog="trader_engine")
    sub = ap.add_subparsers(dest="cmd", required=True)

    def env_arg(p):
        p.add_argument("--env", default=None, choices=("testnet", "live"),
                       help="config/engine.<env>.json katmani (kip + live blogu + env'e ozgu kill/pause yolu)")

    def bot_args(p, need_bot=True):
        p.add_argument("--bot", required=need_bot, choices=("learner", "twin"))
        p.add_argument("--config-dir", default="config")

    p = sub.add_parser("run")
    bot_args(p)
    env_arg(p)
    p.set_defaults(fn=_cmd_run)
    p = sub.add_parser("init-ledger")
    bot_args(p)
    p.add_argument("--reason", default="paper_start")
    p.add_argument("--strategy", default=None)
    env_arg(p)
    p.set_defaults(fn=_cmd_init_ledger)
    p = sub.add_parser("reconcile")
    bot_args(p)
    env_arg(p)
    p.set_defaults(fn=_cmd_reconcile)
    p = sub.add_parser("kill")
    p.add_argument("--clear", action="store_true")
    p.add_argument("--by", default="cli")
    p.add_argument("--reason", default="manual")
    p.add_argument("--config-dir", default="config")
    env_arg(p)
    p.set_defaults(fn=_cmd_kill)
    p = sub.add_parser("pause")
    bot_args(p)
    p.add_argument("--clear", action="store_true")
    p.add_argument("--list", action="store_true")
    p.add_argument("--reason", default=None)
    p.add_argument("--by", default=None)
    p.add_argument("--note", default="")
    env_arg(p)
    p.set_defaults(fn=_cmd_pause)
    for name, fn in (("feed", _cmd_feed), ("backtest", _cmd_backtest), ("rules-snapshot", _cmd_rules)):
        p = sub.add_parser(name)
        p.add_argument("rest", nargs=argparse.REMAINDER)
        p.set_defaults(fn=fn)
    p = sub.add_parser("smoke")
    p.set_defaults(fn=_cmd_smoke)
    return ap


def main(argv: list[str] | None = None) -> int:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
    argv = list(sys.argv[1:] if argv is None else argv)
    if argv and argv[0] in _PASSTHROUGH:
        # argparse.REMAINDER `--secenek` ile baslayan kalani (ornegin `feed --config-dir config`) reddeder: dogrudan ilet
        return int(_PASSTHROUGH[argv[0]](argparse.Namespace(cmd=argv[0], rest=argv[1:])))
    a = build_parser().parse_args(argv)
    return int(a.fn(a))
