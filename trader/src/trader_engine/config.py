"""Motor yapilandirmasi (02 §8). Risk kaynagi trader_core.risk.LOCKED_CFG; tek ayar `target_trade_risk` yalniz
LOCKED_CFG'den SIKI olabilir (gevsek/gecersiz => ConfigError, fail-closed)."""
from __future__ import annotations

import dataclasses
import json
import math
import os
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal, Mapping

from trader_core.config_loader import deep_merge
from trader_core.risk import LOCKED_CFG, RiskConfig, tightened

from .errors import ConfigError
from .types import canon_pair

SCHEMA = "engine/1"


@dataclass(frozen=True)
class CostModel:
    fill_model: Literal["native", "legacy_compat"] = "native"
    taker_fee: float = 0.0005
    slip_entry_bps: float = 2.0
    slip_exit_bps: float = 2.0
    slip_stop_bps: float = 5.0
    trigger_source: Literal["mark", "last"] = "mark"
    granularity: Literal["1m", "15m"] = "1m"


_TAG_RE = re.compile(r"[a-z0-9-]{3,32}")
_KEY_VARS = ("BINANCE_API_KEY", "BINANCE_API_SECRET")


@dataclass(frozen=True)
class LiveSettings:
    """11 §3.1: testnet/live ayarlari. Taban adresleri burada YOK (binance_rest.py'de sabit)."""
    account_tag: str
    expected_wallet_max: float
    conditional_mode: Literal["algo", "classic"] = "algo"
    recv_window_ms: int = 5000
    poll_open_s: float = 5.0
    poll_flat_s: float = 30.0
    stop_deadline_s: float = 10.0
    entry_resolve_window_s: float = 60.0
    max_attempts: int = 1


@dataclass(frozen=True)
class EngineConfig:
    schema: str
    mode: Literal["paper", "backtest", "testnet", "live"]
    bot: Literal["learner", "twin"]
    pairs: tuple[str, ...]
    wallet_start: float
    cost: CostModel
    target_mode: Literal["bar_close"]
    veto_mode: Literal["required", "off"]
    record_filtered_candidates: bool
    stale_factor: float
    loop_sleep_s: float
    bar_wait_s: float
    minute_wait_s: float
    reconcile_open_s: float
    reconcile_flat_s: float
    start_delay_s: float
    var_dir: str
    market_db: str
    history_dir: str
    veto_config: str
    kill_file: str
    strategy: str = "price_action_v1"
    target_trade_risk: float = LOCKED_CFG.target_trade_risk
    ml_mode: Literal["off", "shadow", "active"] = "off"      # 05 §13.4a; yalniz price_action_v1_ml okur
    ml_model_path: str | None = None                          # model paketi (JSON); off iken okunmaz
    pause_file: str = "shared/PAUSE"                          # 11 §3.1: gercek yol f"{pause_file}.{bot}"
    startup_wait_s: float = 600.0                             # paper acilis kapisi: kural+taze 1m veri icin azami bekleme
    leverage: int = LOCKED_CFG.min_leverage                   # 11 §3.1: [min_leverage, max_leverage]
    live: LiveSettings | None = None                          # 11 §3.1: testnet/live icin ZORUNLU, digerlerinde yasak

    @property
    def risk_config(self) -> RiskConfig:
        """Boyutlama/kapi icin tek RiskConfig (twin ve learner ayni degeri okur)."""
        return build_risk_config(self.target_trade_risk)

    def _bot_path(self, name: str) -> str:
        return f"{self.var_dir.rstrip('/')}/{self.bot}/{name}"

    def path(self, name: str) -> str:
        return self._bot_path(name)

    @property
    def ledger_path(self) -> str:
        return self._bot_path("ledger.sqlite")

    @property
    def state_path(self) -> str:
        return self._bot_path("state.sqlite")

    @property
    def status_path(self) -> str:
        return self._bot_path("status.json")


_COST_KEYS = {f.name for f in dataclasses.fields(CostModel)}
_TOP_KEYS = {f.name for f in dataclasses.fields(EngineConfig)}
_NUM = ("wallet_start", "stale_factor", "loop_sleep_s", "bar_wait_s", "minute_wait_s",
        "reconcile_open_s", "reconcile_flat_s", "start_delay_s")
_STR = ("var_dir", "market_db", "history_dir", "veto_config", "kill_file")
_OPTIONAL_KEYS = {"strategy", "target_trade_risk", "ml_mode", "ml_model_path", "startup_wait_s", "pause_file",
                  "leverage", "live"}
_LIVE_KEYS = {f.name for f in dataclasses.fields(LiveSettings)}
_STRATEGY_RE = re.compile(r"[a-z][a-z0-9_]{0,39}")


def _num(name: str, v: Any, lo: float | None = None, hi: float | None = None) -> float:
    if isinstance(v, bool) or not isinstance(v, (int, float)):
        raise ConfigError(f"{name} sayi olmali: {v!r}")
    if not math.isfinite(v):
        raise ConfigError(f"{name} sonlu olmali: {v!r}")
    if (lo is not None and v < lo) or (hi is not None and v > hi):
        raise ConfigError(f"{name} aralik disi [{lo}, {hi}]: {v!r}")
    return float(v)


def build_risk_config(target_trade_risk: Any) -> RiskConfig:
    """LOCKED_CFG'nin yalniz `target_trade_risk`i daha sikilastirilmis kopyasi. Gevsek (> kilitli hedef), <= 0,
    sonlu olmayan ya da sayi olmayan deger => ConfigError."""
    v = _num("target_trade_risk", target_trade_risk)
    try:
        return tightened(LOCKED_CFG, target_trade_risk=v)
    except ValueError as e:
        raise ConfigError(f"target_trade_risk: {e}") from e


def _choice(name: str, v: Any, allowed: tuple[str, ...]) -> str:
    if not isinstance(v, str) or v not in allowed:
        raise ConfigError(f"{name} gecersiz: {v!r} (izinli: {allowed})")
    return v


def _build_cost(raw: Any) -> CostModel:
    if not isinstance(raw, Mapping):
        raise ConfigError("cost sozluk olmali")
    unknown = set(raw) - _COST_KEYS
    if unknown:
        raise ConfigError(f"cost bilinmeyen anahtar: {sorted(unknown)}")
    d = CostModel()
    fm = _choice("cost.fill_model", raw.get("fill_model", d.fill_model), ("native", "legacy_compat"))
    ts = _choice("cost.trigger_source", raw.get("trigger_source", d.trigger_source), ("mark", "last"))
    gr = _choice("cost.granularity", raw.get("granularity", d.granularity), ("1m", "15m"))
    cm = CostModel(
        fill_model=fm,  # type: ignore[arg-type]
        taker_fee=_num("cost.taker_fee", raw.get("taker_fee", d.taker_fee), 0, 0.005),
        slip_entry_bps=_num("cost.slip_entry_bps", raw.get("slip_entry_bps", d.slip_entry_bps), 0, 100),
        slip_exit_bps=_num("cost.slip_exit_bps", raw.get("slip_exit_bps", d.slip_exit_bps), 0, 100),
        slip_stop_bps=_num("cost.slip_stop_bps", raw.get("slip_stop_bps", d.slip_stop_bps), 0, 100),
        trigger_source=ts,  # type: ignore[arg-type]
        granularity=gr,  # type: ignore[arg-type]
    )
    if fm == "legacy_compat" and (ts != "last" or gr != "15m"):
        raise ConfigError("legacy_compat: trigger_source=last ve granularity=15m zorunlu")
    if gr == "15m" and ts != "last":
        raise ConfigError("granularity=15m: trigger_source=last zorunlu")
    return cm


def _int(name: str, v: Any, lo: int, hi: int) -> int:
    if isinstance(v, bool) or not isinstance(v, int):
        raise ConfigError(f"{name} tam sayi olmali: {v!r}")
    if v < lo or v > hi:
        raise ConfigError(f"{name} aralik disi [{lo}, {hi}]: {v!r}")
    return v


def _build_live(raw: Any) -> LiveSettings:
    if isinstance(raw, LiveSettings):
        raw = dataclasses.asdict(raw)
    if not isinstance(raw, Mapping):
        raise ConfigError("live sozluk olmali")
    unknown = set(raw) - _LIVE_KEYS
    if unknown:
        raise ConfigError(f"live bilinmeyen anahtar: {sorted(unknown)}")
    for req in ("account_tag", "expected_wallet_max"):
        if req not in raw:
            raise ConfigError(f"live eksik anahtar: {req}")
    d = LiveSettings(account_tag="x", expected_wallet_max=1.0)
    tag = raw["account_tag"]
    if not isinstance(tag, str) or not _TAG_RE.fullmatch(tag):
        raise ConfigError("live.account_tag ^[a-z0-9-]{3,32}$ olmali")
    wmax = _num("live.expected_wallet_max", raw["expected_wallet_max"])
    if wmax <= 0:
        raise ConfigError("live.expected_wallet_max > 0 olmali")
    cm = _choice("live.conditional_mode", raw.get("conditional_mode", d.conditional_mode), ("algo", "classic"))
    return LiveSettings(
        account_tag=tag, expected_wallet_max=wmax, conditional_mode=cm,  # type: ignore[arg-type]
        recv_window_ms=_int("live.recv_window_ms", raw.get("recv_window_ms", d.recv_window_ms), 1000, 10000),
        poll_open_s=_num("live.poll_open_s", raw.get("poll_open_s", d.poll_open_s), 1, 15),
        poll_flat_s=_num("live.poll_flat_s", raw.get("poll_flat_s", d.poll_flat_s), 5, 120),
        stop_deadline_s=_num("live.stop_deadline_s", raw.get("stop_deadline_s", d.stop_deadline_s), 5, 15),
        entry_resolve_window_s=_num("live.entry_resolve_window_s",
                                    raw.get("entry_resolve_window_s", d.entry_resolve_window_s), 0, 3600),
        max_attempts=_int("live.max_attempts", raw.get("max_attempts", d.max_attempts), 1, 2))


def load_keys(env: Mapping[str, str]) -> tuple[str, str]:
    """11 §3.2: (BINANCE_API_KEY, BINANCE_API_SECRET). Eksik/bos/bosluklu/<32 karakter => ConfigError('keys_missing').
    Iletide yalniz degisken adi vardir, deger asla."""
    out = []
    for name in _KEY_VARS:
        v = env.get(name)
        if not isinstance(v, str) or len(v) < 32 or any(c.isspace() for c in v):
            raise ConfigError(f"keys_missing: {name}")
        out.append(v)
    return out[0], out[1]


def check_live_confirm(cfg: "EngineConfig", env: Mapping[str, str] | None = None) -> None:
    """11 §3.1 cift onay: yalniz mode='live'. LIVE_CONFIRM != live.account_tag => ConfigError('live_confirm')."""
    if cfg.mode != "live":
        return
    env = os.environ if env is None else env
    got = env.get("LIVE_CONFIRM")
    if cfg.live is None or not isinstance(got, str) or got != cfg.live.account_tag:
        raise ConfigError("live_confirm")  # deger iletiye/gunluge yazilmaz


def _validate(raw: Mapping[str, Any]) -> EngineConfig:
    if not isinstance(raw, Mapping):
        raise ConfigError("yapilandirma sozluk olmali")
    unknown = set(raw) - _TOP_KEYS
    if unknown:
        raise ConfigError(f"bilinmeyen anahtar: {sorted(unknown)}")
    missing = _TOP_KEYS - _OPTIONAL_KEYS - set(raw)
    if missing:
        raise ConfigError(f"eksik anahtar: {sorted(missing)}")
    if raw["schema"] != SCHEMA:
        raise ConfigError(f"schema {SCHEMA!r} olmali: {raw['schema']!r}")
    mode = raw["mode"]
    _choice("mode", mode, ("paper", "backtest", "testnet", "live"))
    bot = _choice("bot", raw["bot"], ("learner", "twin"))
    pairs_raw = raw["pairs"]
    if isinstance(pairs_raw, (str, bytes)) or not isinstance(pairs_raw, (list, tuple)) or not pairs_raw:
        raise ConfigError("pairs bos olmayan liste olmali")
    try:
        pairs = tuple(canon_pair(p) for p in pairs_raw)
    except ValueError as e:
        raise ConfigError(f"pairs: {e}") from e
    if len(set(pairs)) != len(pairs):
        raise ConfigError("pairs yinelenen oge iceriyor")
    nums = {n: _num(n, raw[n]) for n in _NUM}
    if nums["wallet_start"] <= 0:
        raise ConfigError("wallet_start > 0 olmali")
    if not 1.0 <= nums["stale_factor"] <= 3.0:
        raise ConfigError("stale_factor [1, 3] araliginda olmali")
    for n in _NUM[2:]:
        if nums[n] < 0:
            raise ConfigError(f"{n} >= 0 olmali")
    if raw["target_mode"] != "bar_close":
        raise ConfigError(f"target_mode yalniz 'bar_close': {raw['target_mode']!r}")
    veto_mode = _choice("veto_mode", raw["veto_mode"], ("required", "off"))
    if veto_mode == "off" and mode != "backtest":
        raise ConfigError("veto_mode='off' yalniz mode='backtest' ile gecerli")
    if not isinstance(raw["record_filtered_candidates"], bool):
        raise ConfigError("record_filtered_candidates bool olmali")
    for n in _STR:
        if not isinstance(raw[n], str) or not raw[n]:
            raise ConfigError(f"{n} bos olmayan str olmali")
    strategy = raw.get("strategy", "price_action_v1")
    if not isinstance(strategy, str) or not _STRATEGY_RE.fullmatch(strategy):
        raise ConfigError(f"strategy gecersiz (^[a-z][a-z0-9_]{{0,39}}$): {strategy!r}")
    ml_mode = _choice("ml_mode", raw.get("ml_mode", "off"), ("off", "shadow", "active"))
    ml_path = raw.get("ml_model_path")
    if ml_path is not None and (not isinstance(ml_path, str) or not ml_path):
        raise ConfigError("ml_model_path bos olmayan str ya da null olmali")
    pause_file = raw.get("pause_file", "shared/PAUSE")
    if not isinstance(pause_file, str) or not pause_file:
        raise ConfigError("pause_file bos olmayan str olmali")
    startup_wait = _num("startup_wait_s", raw.get("startup_wait_s", 600.0), 0.0, 86_400.0)
    lev = _int("leverage", raw.get("leverage", LOCKED_CFG.min_leverage),
               LOCKED_CFG.min_leverage, LOCKED_CFG.max_leverage)
    live_raw = raw.get("live")
    if mode in ("testnet", "live"):
        if live_raw is None:
            raise ConfigError(f"live blogu mode={mode} icin zorunlu")
        live = _build_live(live_raw)
    else:
        if live_raw is not None:
            raise ConfigError(f"live blogu mode={mode} ile verilemez")
        live = None
    ttr = raw.get("target_trade_risk", LOCKED_CFG.target_trade_risk)
    build_risk_config(ttr)
    cost = raw["cost"] if isinstance(raw["cost"], CostModel) else None
    cost = _build_cost(dataclasses.asdict(cost) if cost else raw["cost"])
    if mode in ("testnet", "live"):
        if bot != "learner":
            raise ConfigError(f"mode={mode!r} yalniz bot='learner' ile gecerli (ikiz kagitta kalir)")
        if cost.trigger_source != "mark":
            raise ConfigError(f"mode={mode!r}: cost.trigger_source='mark' zorunlu")
    if mode == "live" and veto_mode != "required":
        raise ConfigError("mode='live': veto_mode='required' zorunlu")
    return EngineConfig(
        schema=SCHEMA, mode=mode, bot=bot, pairs=pairs,  # type: ignore[arg-type]
        wallet_start=nums["wallet_start"], cost=cost, target_mode="bar_close",
        veto_mode=veto_mode,  # type: ignore[arg-type]
        record_filtered_candidates=raw["record_filtered_candidates"],
        stale_factor=nums["stale_factor"], loop_sleep_s=nums["loop_sleep_s"],
        bar_wait_s=nums["bar_wait_s"], minute_wait_s=nums["minute_wait_s"],
        reconcile_open_s=nums["reconcile_open_s"], reconcile_flat_s=nums["reconcile_flat_s"],
        start_delay_s=nums["start_delay_s"], strategy=strategy,
        target_trade_risk=float(ttr), ml_mode=ml_mode, ml_model_path=ml_path,  # type: ignore[arg-type]
        startup_wait_s=startup_wait, pause_file=pause_file, leverage=lev, live=live,
        **{n: raw[n] for n in _STR},
    )


def _read(path: Any) -> dict[str, Any]:
    try:
        with open(Path(path), encoding="utf-8") as fh:
            data = json.load(fh)
    except (OSError, ValueError) as e:
        raise ConfigError(f"yapilandirma okunamadi: {path}: {e}") from e
    if not isinstance(data, dict):
        raise ConfigError(f"yapilandirma nesne olmali: {path}")
    return data


def load_engine_config(base_path: Any, bot_path: Any = None, *,
                       env: Mapping[str, str] | None = None, overlay_path: Any = None) -> EngineConfig:
    """base (+ bot) (+ overlay) JSON birlestirir ve dogrular. LIVE_CONFIRM (11 §3.1) burada YALNIZ `env=` acikca
    verildiyse denetlenir; kosu yolu (cli run / build_engine) check_live_confirm'i kendisi cagirir
    (kill/pause/init-ledger/reconcile/backtest live yapilandirmada LIVE_CONFIRM istemez)."""
    merged = _read(base_path)
    if bot_path is not None:
        merged = deep_merge(merged, _read(bot_path))
    if overlay_path is not None:
        merged = deep_merge(merged, _read(overlay_path))
    cfg = _validate(merged)
    if env is not None:
        check_live_confirm(cfg, env)
    return cfg


def apply_overrides(cfg: EngineConfig, **kw: Any) -> EngineConfig:
    if "cost" in kw and isinstance(kw["cost"], Mapping):
        if not set(kw["cost"]) <= _COST_KEYS:
            raise ConfigError("cost bilinmeyen anahtar")
        kw["cost"] = dataclasses.replace(cfg.cost, **kw["cost"])
    unknown = set(kw) - _TOP_KEYS
    if unknown:
        raise ConfigError(f"bilinmeyen anahtar: {sorted(unknown)}")
    if kw.get("mode") in ("backtest", "paper") and "live" not in kw:
        kw["live"] = None                        # testnet/live yapilandirmasindan backtest/paper'a gecis live blogunu birakir
    d = {f.name: getattr(cfg, f.name) for f in dataclasses.fields(cfg)}
    d.update(kw)
    return _validate(d)
