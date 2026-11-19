"""Canli yollar: tek kaynak (DD-9 §6.1). Yalniz stdlib; `trader_engine` ice aktarilmaz.

Canli bot (`LIVE_BOTS`) icin Telegram, saglik ve yedek `LIVE_VAR_DIR` / `LIVE_PAUSE_FILE` yollarini kullanir; kagit bot
`ENGINE_VAR_DIR` / `PAUSE_FILE` yollarinda kalir. `check_against_config` env dosyalarini `config/engine.live.json` ile
karsilastirir (yanlis dosyaya KILL/duraklatma yazilmasin). `LIVE_BOTS` bos iken hicbir islev davranis degistirmez."""
from __future__ import annotations

import json
import os
from pathlib import Path


class LivePathError(ValueError):
    def __init__(self, code: str, message: str | None = None):
        super().__init__(message or code)
        self.code = code


def _get(env, key: str) -> str:
    v = env.get(key)
    return v.strip() if isinstance(v, str) else ""


def live_bots(env) -> tuple[str, ...]:
    """LIVE_BOTS (virgullu); bos/yok -> ()."""
    raw = _get(env, "LIVE_BOTS")
    return tuple(dict.fromkeys(b for b in (x.strip() for x in raw.split(",")) if b))


def _parts(p: str) -> tuple[str, ...]:
    return tuple(x for x in os.path.normpath(p).split(os.sep) if x)


def validate_live_env(env) -> None:
    """LIVE_BOTS bos -> hicbir sey; degilse kurallar (ilk ihlalin kodu)."""
    bots = live_bots(env)
    if not bots:
        return
    if bots != ("learner",):
        raise LivePathError("live_bots_invalid")
    var = _get(env, "LIVE_VAR_DIR")
    if not var:
        raise LivePathError("live_var_dir_missing")
    if not os.path.isabs(var):
        raise LivePathError("live_var_dir_relative")
    if _parts(var)[-1:] == ("var",):
        raise LivePathError("live_var_dir_paper")
    pause = _get(env, "LIVE_PAUSE_FILE")
    if not pause:
        raise LivePathError("live_pause_missing")
    if not os.path.isabs(pause):
        raise LivePathError("live_pause_relative")
    if _parts(pause)[-2:] == ("shared", "PAUSE"):
        raise LivePathError("live_pause_paper")


def bot_var_dir(env, bot: str, default_var: str) -> str:
    """Bot canliysa LIVE_VAR_DIR, degilse default_var."""
    if bot in live_bots(env):
        validate_live_env(env)
        return _get(env, "LIVE_VAR_DIR")
    return default_var


def bot_pause_base(env, bot: str, default_base: str) -> str:
    """Bot canliysa LIVE_PAUSE_FILE, degilse default_base."""
    if bot in live_bots(env):
        validate_live_env(env)
        return _get(env, "LIVE_PAUSE_FILE")
    return default_base


def expected_from_config(config_dir) -> dict:
    """`<config_dir>/engine.live.json` -> {"var_dir","kill_file","pause_file","account_tag"} (yollar mutlak).
    Kok kurali `config.absolutize_paths` ile ayni: dizin adi `config` ise ustu, degilse kendisi."""
    cdir = Path(config_dir).resolve()
    root = cdir.parent if cdir.name == "config" else cdir
    try:
        with open(cdir / "engine.live.json", encoding="utf-8") as f:
            d = json.load(f)
        live = d["live"]
        out = {}
        for k in ("var_dir", "kill_file", "pause_file"):
            v = d[k]
            if not isinstance(v, str) or not v.strip():
                raise ValueError(k)
            out[k] = v if os.path.isabs(v) else str(root / v)
        tag = live["account_tag"]
        if not isinstance(tag, str) or not tag.strip():
            raise ValueError("account_tag")
        out["account_tag"] = tag
        return out
    except (OSError, ValueError, KeyError, TypeError, AttributeError) as e:
        raise LivePathError("live_config_missing") from e


def _norm(p: str) -> str:
    return os.path.normpath(p)


def check_against_config(env, config_dir) -> tuple[str, ...]:
    """Uyusmazlik kodlari (bos demet = tutarli). Ortamda BULUNMAYAN anahtar denetlenmez. LIVE_BOTS bos -> ()."""
    if not live_bots(env):
        return ()
    try:
        validate_live_env(env)
    except LivePathError as e:
        return (e.code,)
    try:
        exp = expected_from_config(config_dir)
    except LivePathError as e:
        return (e.code,)
    out: list[str] = []
    var_dir = exp["var_dir"]
    if _norm(_get(env, "LIVE_VAR_DIR")) != _norm(var_dir):
        out.append("var_dir_mismatch")
    if _norm(_get(env, "LIVE_PAUSE_FILE")) != _norm(exp["pause_file"]):
        out.append("pause_file_mismatch")
    if "KILL_FILE" in env and _norm(_get(env, "KILL_FILE")) != _norm(exp["kill_file"]):
        out.append("kill_file_mismatch")
    if "ENGINE_STATUS_PATH" in env and _norm(_get(env, "ENGINE_STATUS_PATH")) != _norm(
            os.path.join(var_dir, "learner", "status.json")):
        out.append("status_path_mismatch")
    if "LEDGER_PATH" in env and _norm(_get(env, "LEDGER_PATH")) != _norm(os.path.join(var_dir, "learner", "ledger.sqlite")):
        out.append("ledger_path_mismatch")
    if "LADDER_BOTS" in env:
        lad = {b.strip() for b in _get(env, "LADDER_BOTS").split(",") if b.strip()}
        if lad != set(live_bots(env)):
            out.append("ladder_bots_mismatch")
    return tuple(out)
