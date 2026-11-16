"""Risk kilidi: saf Python (stdlib) risk kuralları. Bkz. docs/risk-kilidi-spec.md.

Sabitler `RiskConfig` varsayılanlarındadır; bot ve ders servisi bunları değiştiremez.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field

_SIDES = ("long", "short")
_TOL = 1e-9


def _finite(x) -> bool:
    return isinstance(x, (int, float)) and not isinstance(x, bool) and math.isfinite(x)


@dataclass(frozen=True)
class RiskConfig:
    max_trade_risk: float = 0.02
    target_trade_risk: float = 0.014
    fee_rate: float = 0.0005
    slippage_rate: float = 0.0005
    daily_max_loss: float = 0.05
    max_open_risk: float = 0.06
    max_same_dir_risk: float = 0.04
    min_leverage: int = 3
    max_leverage: int = 5
    maint_margin_rate: float = 0.004
    liq_safety_factor: float = 1.5

    def __post_init__(self) -> None:
        pos = ("max_trade_risk", "target_trade_risk", "daily_max_loss", "max_open_risk",
               "max_same_dir_risk", "liq_safety_factor")
        nonneg = ("fee_rate", "slippage_rate", "maint_margin_rate")
        for n in pos + nonneg + ("min_leverage", "max_leverage"):
            if not _finite(getattr(self, n)):
                raise ValueError(f"{n} sonlu bir sayı olmalı")
        for n in pos:
            if getattr(self, n) <= 0:
                raise ValueError(f"{n} > 0 olmalı")
        for n in nonneg:
            if getattr(self, n) < 0:
                raise ValueError(f"{n} negatif olamaz")
        if self.target_trade_risk > self.max_trade_risk:
            raise ValueError("target_trade_risk, max_trade_risk değerini aşamaz")
        if self.min_leverage < 1 or self.min_leverage > self.max_leverage:
            raise ValueError("kaldıraç aralığı geçersiz")
        if self.maint_margin_rate >= 1 or self.daily_max_loss > 1:
            raise ValueError("oran değerleri geçersiz")


@dataclass(frozen=True)
class SizeResult:
    qty: float
    notional: float
    margin: float
    risk_amount: float


@dataclass(frozen=True)
class OpenPosition:
    pair: str
    side: str
    risk_amount: float


@dataclass(frozen=True)
class AccountState:
    equity: float
    day_start_equity: float
    open_positions: list = field(default_factory=list)


@dataclass(frozen=True)
class Candidate:
    pair: str
    side: str
    entry: float
    stop: float
    leverage: float


@dataclass(frozen=True)
class Decision:
    allowed: bool
    reason: str
    size: SizeResult | None = None


def liquidation_price(entry: float, side: str, leverage: float, mmr: float) -> float:
    """İzole teminat likidasyon fiyatı yaklaşığı."""
    if side == "long":
        return entry * (1 - 1 / leverage + mmr)
    if side == "short":
        return entry * (1 + 1 / leverage - mmr)
    raise ValueError(f"geçersiz yön: {side!r}")


def loss_at_stop(qty: float, entry: float, stop: float, cfg: RiskConfig) -> float:
    """Stop'ta gerçekleşen kayıp, her iki taraf komisyon+kayma dahil."""
    cost = cfg.fee_rate + cfg.slippage_rate
    return qty * abs(entry - stop) + qty * entry * cost + qty * stop * cost


def size_position(equity: float, entry: float, stop: float, side: str,
                  leverage: float, cfg: RiskConfig) -> SizeResult:
    """loss_at_stop(qty) = target_trade_risk*equity denklemini qty için çözer."""
    if side not in _SIDES:
        raise ValueError(f"geçersiz yön: {side!r}")
    if not all(_finite(v) for v in (equity, entry, stop, leverage)):
        raise ValueError("sonlu olmayan girdi")
    if equity <= 0 or entry <= 0 or stop <= 0 or leverage <= 0:
        raise ValueError("equity, fiyat ve kaldıraç pozitif olmalı")
    if entry == stop:
        raise ValueError("stop mesafesi sıfır")
    per_qty = loss_at_stop(1.0, entry, stop, cfg)
    if not per_qty > 0:
        raise ValueError("birim kayıp hesaplanamadı")
    limit = cfg.target_trade_risk * equity
    qty = limit / per_qty
    risk = loss_at_stop(qty, entry, stop, cfg)
    if risk > limit * (1 + _TOL):  # savunma amaçlı
        qty = math.nextafter(qty, 0.0)
        risk = loss_at_stop(qty, entry, stop, cfg)
    notional = qty * entry
    margin = notional / leverage
    if margin > equity:
        raise ValueError("gereken teminat özsermayeyi aşıyor")
    return SizeResult(qty=qty, notional=notional, margin=margin, risk_amount=risk)


def _deny(reason: str) -> Decision:
    return Decision(False, reason, None)


def _check_entry(state: AccountState, cand: Candidate, cfg: RiskConfig) -> Decision:
    # 1. Girdi geçerliliği
    if cand.side not in _SIDES:
        return _deny("geçersiz girdi: yön 'long' veya 'short' olmalı")
    if not all(_finite(v) for v in (state.equity, state.day_start_equity,
                                    cand.entry, cand.stop, cand.leverage)):
        return _deny("geçersiz girdi: sonlu olmayan değer")
    if state.equity <= 0 or state.day_start_equity <= 0:
        return _deny("geçersiz girdi: equity > 0 olmalı")
    if cand.entry <= 0 or cand.stop <= 0:
        return _deny("geçersiz girdi: fiyat > 0 olmalı")
    # 2. Stop tarafı
    if cand.side == "long" and cand.stop >= cand.entry:
        return _deny("stop yanlış tarafta: long için stop < entry olmalı")
    if cand.side == "short" and cand.stop <= cand.entry:
        return _deny("stop yanlış tarafta: short için stop > entry olmalı")
    # 3. Kaldıraç
    lev = cand.leverage
    if lev != int(lev) or lev < cfg.min_leverage or lev > cfg.max_leverage:
        return _deny(f"kaldıraç aralık dışı: {cfg.min_leverage}-{cfg.max_leverage} tam sayı olmalı")
    # 4. Günlük zarar
    if (state.equity - state.day_start_equity) / state.day_start_equity <= -cfg.daily_max_loss:
        return _deny("günlük sınır aşıldı: yeni işlem açılamaz")
    # 5. Aynı çift
    for p in state.open_positions:
        if p.pair == cand.pair:
            return _deny(f"{cand.pair} için zaten açık pozisyon var")
    # 6. Boyut
    try:
        size = size_position(state.equity, cand.entry, cand.stop, cand.side, lev, cfg)
    except ValueError as exc:
        return _deny(f"boyutlandırma reddedildi: {exc}")
    # 7. Likidasyon güvenliği
    liq = liquidation_price(cand.entry, cand.side, lev, cfg.maint_margin_rate)
    if abs(cand.entry - liq) < cfg.liq_safety_factor * abs(cand.entry - cand.stop):
        return _deny("likidasyon çok yakın: giriş-likidasyon mesafesi yetersiz")
    # 8. Toplam açık risk
    total_open = sum(p.risk_amount for p in state.open_positions)
    if total_open + size.risk_amount > cfg.max_open_risk * state.equity:
        return _deny("toplam açık risk sınırı aşılır")
    # 9. Aynı yön riski
    same = sum(p.risk_amount for p in state.open_positions if p.side == cand.side)
    if same + size.risk_amount > cfg.max_same_dir_risk * state.equity:
        return _deny(f"aynı yön ({cand.side}) risk sınırı aşılır")
    # 10.
    return Decision(True, "izin verildi", size)


def check_entry(state: AccountState, cand: Candidate, cfg: RiskConfig) -> Decision:
    """Giriş kurallarını sırayla uygular; beklenmeyen hatada kapalı (fail-closed)."""
    try:
        return _check_entry(state, cand, cfg)
    except Exception as exc:  # noqa: BLE001
        return Decision(False, f"iç hata: {exc!r}", None)
