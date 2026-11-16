"""Kucuk saf sayisal yardimcilar (02 §5). Decimal(repr(x)) ile calisir."""
from __future__ import annotations

import math
from decimal import ROUND_CEILING, ROUND_FLOOR, Decimal

from .types import OrderSide, Side


def _chk(x: float, step: float) -> tuple[Decimal, Decimal]:
    for v in (x, step):
        if isinstance(v, bool) or not isinstance(v, (int, float)) or not math.isfinite(v):
            raise ValueError(f"sonlu sayi olmali: {v!r}")
    if step <= 0:
        raise ValueError(f"step > 0 olmali: {step!r}")
    if x < 0:
        raise ValueError(f"x >= 0 olmali: {x!r}")
    return Decimal(repr(float(x))), Decimal(repr(float(step)))


def _snap(x: float, step: float, rounding: str) -> float:
    dx, ds = _chk(x, step)
    n = (dx / ds).to_integral_value(rounding=rounding)
    return float(n * ds)


def floor_step(x: float, step: float) -> float:
    return _snap(x, step, ROUND_FLOOR)


def ceil_step(x: float, step: float) -> float:
    return _snap(x, step, ROUND_CEILING)


def is_multiple(x: float, step: float, rel_tol: float = 1e-9) -> bool:
    dx, ds = _chk(x, step)
    q = dx / ds
    return abs(q - q.to_integral_value()) <= Decimal(repr(float(rel_tol))) * max(Decimal(1), abs(q))


def round_tight(price: float, side: Side, tick: float) -> float:
    if side == "long":
        return ceil_step(price, tick)
    if side == "short":
        return floor_step(price, tick)
    raise ValueError(f"gecersiz side: {side!r}")


def round_adverse(price: float, order_side: OrderSide, tick: float) -> float:
    if order_side == "buy":
        return ceil_step(price, tick)
    if order_side == "sell":
        return floor_step(price, tick)
    raise ValueError(f"gecersiz order_side: {order_side!r}")


def bps(x: float) -> float:
    return x / 1e4
