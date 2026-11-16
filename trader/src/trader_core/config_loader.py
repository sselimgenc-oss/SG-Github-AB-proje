"""Taban + bot-ozel JSON yapilandirmalarini birlestirir ve degismezleri dogrular."""
from __future__ import annotations

import copy
import json
from pathlib import Path
from typing import Any


class ConfigError(ValueError):
    """Yapilandirma degismezlerinden biri ihlal edildi."""


def deep_merge(base: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
    """override'i base uzerine ozyinelemeli birlestirir (yeni sozluk dondurur).

    Sozluklerde alan alan birlestirilir; listeler ve diger degerler override ile degisir.
    """
    result = copy.deepcopy(base)
    for key, value in override.items():
        if isinstance(value, dict) and isinstance(result.get(key), dict):
            result[key] = deep_merge(result[key], value)
        else:
            result[key] = copy.deepcopy(value)
    return result


def validate(config: dict[str, Any], allow_live: bool = False) -> None:
    """Degismezleri dogrular; ihlalde ConfigError firlatir."""
    if config.get("trading_mode") != "futures":
        raise ConfigError("trading_mode 'futures' olmali")
    if config.get("margin_mode") != "isolated":
        raise ConfigError("margin_mode 'isolated' olmali")
    if config.get("dry_run") is not True and not allow_live:
        raise ConfigError("dry_run true olmali (canli mod icin acik LIVE bayragi gerekir)")
    exchange = config.get("exchange") or {}
    for field in ("key", "secret", "password", "uid"):
        if exchange.get(field):
            raise ConfigError(f"exchange.{field} dosyada bos olmali (sirlar dosyaya yazilmaz)")


def load_config(
    base_path: str | Path,
    override_path: str | Path | None = None,
    allow_live: bool = False,
) -> dict[str, Any]:
    """Dosyalari okur, birlestirir, dogrular ve sonucu dondurur."""
    config = json.loads(Path(base_path).read_text(encoding="utf-8"))
    if override_path is not None:
        override = json.loads(Path(override_path).read_text(encoding="utf-8"))
        config = deep_merge(config, override)
    validate(config, allow_live=allow_live)
    return config
