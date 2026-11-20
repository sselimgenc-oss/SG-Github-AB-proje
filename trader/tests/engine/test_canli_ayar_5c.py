"""5c (1L3A canli_ayar.py uyarlamasi): API anahtar carpisma denetimi (sha256; deger sizmaz)."""
from __future__ import annotations

import pytest

from trader_engine.config import DIGER_ANAHTAR_ENV, anahtar_ozeti, load_keys
from trader_engine.errors import ConfigError

K, S = "K" * 32, "S" * 40


def test_anahtar_carpismasi_reddedilir_ve_deger_sizmaz():
    env = {"BINANCE_API_KEY": K, "BINANCE_API_SECRET": S}
    assert load_keys(env) == (K, S)                                              # kume yok: davranis ayni
    env[DIGER_ANAHTAR_ENV] = f"baska-bot:{anahtar_ozeti(K)},x:{'0' * 64}"
    with pytest.raises(ConfigError) as e:
        load_keys(env)
    assert "baska-bot" in str(e.value) and K not in str(e.value) and "key_collision" in str(e.value)
    env[DIGER_ANAHTAR_ENV] = f"testnet:{anahtar_ozeti(S).upper()}"                # secret cakismasi, buyuk harf hex
    with pytest.raises(ConfigError) as e2:
        load_keys(env)
    assert S not in str(e2.value)
    env[DIGER_ANAHTAR_ENV] = f"diger:{anahtar_ozeti('Z' * 32)}"                   # cakismayan ozet gecer
    assert load_keys(env) == (K, S)


def test_bozuk_ozet_listesi_fail_closed():
    for kotu in ("x", "x:123", ":" + "a" * 64, "a" * 64):
        with pytest.raises(ConfigError):
            load_keys({"BINANCE_API_KEY": K, "BINANCE_API_SECRET": S, DIGER_ANAHTAR_ENV: kotu})
