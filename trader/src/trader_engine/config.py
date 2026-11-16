"""Motor yapilandirmasi (02 §8). Risk kaynagi trader_core.risk.LOCKED_CFG; tek ayar `target_trade_risk` yalniz
LOCKED_CFG'den SIKI olabilir (gevsek/gecersiz => ConfigError, fail-closed)."""
from __future__ import annotations

import dataclasses
import json
import math
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


@dataclass(frozen=True)
class EngineConfig:
    schema: str
    mode: Literal["paper", "backtest"]
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

    @property
    def risk_config(self) -> RiskConfig:
        """Boyutlama/kapi icin tek RiskConfig (twin ve learner ayni degeri okur)."""
        return build_risk_config(self.target_trade_risk)

    def _bot_path(self, name: str) -> str:
        return f"{self.var_dir.rstrip('/')}/{self.bot}/{name}"

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
_OPTIONAL_KEYS = {"strategy", "target_trade_risk"}
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
    if mode in ("testnet", "live"):
        raise ConfigError("faz_b")
    _choice("mode", mode, ("paper", "backtest"))
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
    ttr = raw.get("target_trade_risk", LOCKED_CFG.target_trade_risk)
    build_risk_config(ttr)
    cost = raw["cost"] if isinstance(raw["cost"], CostModel) else None
    cost = _build_cost(dataclasses.asdict(cost) if cost else raw["cost"])
    return EngineConfig(
        schema=SCHEMA, mode=mode, bot=bot, pairs=pairs,  # type: ignore[arg-type]
        wallet_start=nums["wallet_start"], cost=cost, target_mode="bar_close",
        veto_mode=veto_mode,  # type: ignore[arg-type]
        record_filtered_candidates=raw["record_filtered_candidates"],
        stale_factor=nums["stale_factor"], loop_sleep_s=nums["loop_sleep_s"],
        bar_wait_s=nums["bar_wait_s"], minute_wait_s=nums["minute_wait_s"],
        reconcile_open_s=nums["reconcile_open_s"], reconcile_flat_s=nums["reconcile_flat_s"],
        start_delay_s=nums["start_delay_s"], strategy=strategy,
        target_trade_risk=float(ttr),
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
                       env: Mapping[str, str] | None = None) -> EngineConfig:
    """base (+ bot) JSON birlestirir ve dogrular. `env` Faz A'da kullanilmaz (ayrilmis)."""
    merged = _read(base_path)
    if bot_path is not None:
        merged = deep_merge(merged, _read(bot_path))
    return _validate(merged)


def apply_overrides(cfg: EngineConfig, **kw: Any) -> EngineConfig:
    if "cost" in kw and isinstance(kw["cost"], Mapping):
        if not set(kw["cost"]) <= _COST_KEYS:
            raise ConfigError("cost bilinmeyen anahtar")
        kw["cost"] = dataclasses.replace(cfg.cost, **kw["cost"])
    unknown = set(kw) - _TOP_KEYS
    if unknown:
        raise ConfigError(f"bilinmeyen anahtar: {sorted(unknown)}")
    d = {f.name: getattr(cfg, f.name) for f in dataclasses.fields(cfg)}
    d.update(kw)
    return _validate(d)
