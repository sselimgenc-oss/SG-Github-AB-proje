# Kopyalandı: 1l3a-proje/motor/canli/borsa/kurallar.py (kullanıcının kendi kodu; lisans engeli yok)
# Kopya tarihi: 2026-11-16   Kaynak commit: 2dd2dce
# Çalışma zamanında kaynak depo import edilmez/mount edilmez. Değişiklikler: kimlikler İngilizceye çevrildi; emir boyut hesabı ve limit bağımlılığı kesildi; to_symbol_rules, spec_to_json/spec_from_json, extract_all_rules, TRADING/PERPETUAL denetimi eklendi; eksik min-notional varsayılan 5 yerine RulesError("min_notional_missing") (07 §4.3).
"""Borsa filtreleri (exchangeInfo): sembol kuralları ve tick/adım yuvarlama (kural ve sayılar tek risk kaynağında, burada risk sayısı yoktur).

KURAL: miktar HER ZAMAN aşağı yuvarlanır. Eksik/bozuk filtre = RulesError (tahmin yok; min-notional için varsayılan da yok).
"""
from __future__ import annotations

import json
from collections.abc import Iterable
from dataclasses import dataclass
from decimal import ROUND_CEILING, ROUND_FLOOR, Decimal, InvalidOperation

from trader_engine.types import SymbolRules

D = Decimal


class RulesError(KeyError):
    def __str__(self) -> str:  # KeyError repr'ini değil düz iletiyi göster
        return str(self.args[0]) if self.args else ""


@dataclass(frozen=True)
class SymbolRuleSpec:
    symbol: str
    tick: Decimal
    step: Decimal            # LOT_SIZE
    min_qty: Decimal
    max_qty: Decimal
    market_step: Decimal     # MARKET_LOT_SIZE (yoksa LOT_SIZE)
    market_min: Decimal
    market_max: Decimal
    min_notional: Decimal


def _dec(v, sembol: str, ad: str) -> Decimal:
    try:
        d = D(str(v))
    except (InvalidOperation, ValueError) as e:
        raise RulesError(f"{sembol}: {ad} sayı değil") from e
    if not d.is_finite():
        raise RulesError(f"{sembol}: {ad} sonlu değil")
    return d


def extract_rules(info: dict, symbol: str) -> SymbolRuleSpec:
    """exchangeInfo -> tek sembol kuralı (Decimal). Eksik/bozuk filtre = RulesError (tahmin yok)."""
    for s in info.get("symbols", []):
        if s.get("symbol") != symbol:
            continue
        if s.get("status") != "TRADING" or s.get("contractType") != "PERPETUAL":
            raise RulesError(f"{symbol}: not_trading")
        f = {x["filterType"]: x for x in s.get("filters", [])}
        if "PRICE_FILTER" not in f or "LOT_SIZE" not in f:
            raise RulesError(f"{symbol}: PRICE_FILTER/LOT_SIZE yok")
        lot = f["LOT_SIZE"]
        ml = f.get("MARKET_LOT_SIZE") or lot
        mstep = _dec(ml.get("stepSize", "0"), symbol, "MARKET_LOT_SIZE.stepSize")
        if mstep == 0:
            ml, mstep = lot, _dec(lot["stepSize"], symbol, "LOT_SIZE.stepSize")
        mn = f.get("MIN_NOTIONAL") or f.get("NOTIONAL")
        if not mn or ("notional" not in mn and "minNotional" not in mn):
            raise RulesError(f"{symbol}: min_notional_missing")
        notional = _dec(mn.get("notional", mn.get("minNotional")), symbol, "min_notional")
        try:
            k = SymbolRuleSpec(symbol, _dec(f["PRICE_FILTER"]["tickSize"], symbol, "tickSize"),
                               _dec(lot["stepSize"], symbol, "stepSize"), _dec(lot["minQty"], symbol, "minQty"),
                               _dec(lot.get("maxQty", "1e12"), symbol, "maxQty"), mstep,
                               _dec(ml["minQty"], symbol, "market minQty"), _dec(ml.get("maxQty", "1e12"), symbol, "market maxQty"),
                               notional)
        except KeyError as e:
            raise RulesError(f"{symbol}: filtre alanı yok: {e.args[0]}") from e
        if k.tick <= 0 or k.step <= 0 or k.market_step <= 0:
            raise RulesError(f"{symbol}: tick/step sıfır")
        return k
    raise RulesError(f"{symbol}: exchangeInfo'da yok")


def extract_all_rules(info: dict, symbols: Iterable[str]) -> dict[str, SymbolRuleSpec | RulesError]:
    """Tek çiftin hatası diğerlerini bozmaz: hata değer olarak döner."""
    out: dict[str, SymbolRuleSpec | RulesError] = {}
    for s in symbols:
        try:
            out[s] = extract_rules(info, s)
        except RulesError as e:
            out[s] = e
    return out


def floor_to_step(x: Decimal, step: Decimal) -> Decimal:
    return (D(x) / step).to_integral_value(rounding=ROUND_FLOOR) * step


def ceil_to_step(x: Decimal, step: Decimal) -> Decimal:
    return (D(x) / step).to_integral_value(rounding=ROUND_CEILING) * step


def round_market_qty(qty: Decimal, rules: SymbolRuleSpec) -> Decimal:
    """Piyasa emri miktarı: MARKET_LOT_SIZE adımına AŞAĞI, üst sınıra kırp."""
    return floor_to_step(min(D(qty), rules.market_max), rules.market_step)


def round_stop_tight(stop: Decimal, direction: int, rules: SymbolRuleSpec) -> Decimal:
    """Koruyucu stop tick'e girişe DOĞRU (sıkı) yuvarlanır: long'da (1) yukarı, short'ta (-1) aşağı (risk asla artmaz)."""
    return ceil_to_step(stop, rules.tick) if direction == 1 else floor_to_step(stop, rules.tick)


def round_target_easy(target: Decimal, direction: int, rules: SymbolRuleSpec) -> Decimal:
    """Hedef tick'e girişe doğru (kolay dolum yönü): long'da aşağı, short'ta yukarı."""
    return floor_to_step(target, rules.tick) if direction == 1 else ceil_to_step(target, rules.tick)


def to_symbol_rules(pair: str, spec: SymbolRuleSpec) -> SymbolRules:
    """Float görünüm (motor içi): piyasa emri adım/min/max değerleri kullanılır."""
    return SymbolRules(pair=pair, symbol=spec.symbol, tick=float(spec.tick), step=float(spec.market_step),
                       min_qty=float(spec.market_min), max_qty=float(spec.market_max), min_notional=float(spec.min_notional))


def spec_to_json(spec: SymbolRuleSpec) -> str:
    d = {k: (str(v) if isinstance(v, Decimal) else v) for k, v in spec.__dict__.items()}
    return json.dumps(d, ensure_ascii=False, sort_keys=True, allow_nan=False)


def spec_from_json(s: str) -> SymbolRuleSpec:
    try:
        d = json.loads(s)
        return SymbolRuleSpec(symbol=str(d["symbol"]), **{k: _dec(d[k], d["symbol"], k) for k in
                              ("tick", "step", "min_qty", "max_qty", "market_step", "market_min", "market_max", "min_notional")})
    except (KeyError, TypeError, ValueError) as e:
        if isinstance(e, RulesError):
            raise
        raise RulesError(f"kural JSON'u geçersiz: {e!r}") from e
