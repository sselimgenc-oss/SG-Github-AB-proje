"""WP-B7 yardimcilari: guvenlik korkuluklari + rapor yazimi (scripts/smoke_testnet.py kullanir).

Hicbir ag cagrisi yapmaz. Anahtar/gizli yalniz `mask()` ile maskelenmis halde yazilabilir.
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from decimal import ROUND_CEILING, Decimal
from pathlib import Path
from typing import Any, Mapping

# Sabit izin listesi: yalniz Binance vadeli TESTNET. Yapilandirmadan/komut satirindan eklenemez.
ALLOWED_BASES = frozenset({"https://testnet.binancefuture.com"})
KEY_VARS = ("BINANCE_API_KEY", "BINANCE_API_SECRET")
STATUSES = ("GECTI", "KALDI", "FARKLI", "ATLANDI", "BEKLEMEDE", "KISMI", "GOZLEM")
_HEX = re.compile(r"[0-9a-fA-F]{32,}")


class SafetyError(Exception):
    """Guvenlik korkuluguna takildi: hicbir emir gonderilmez."""


def mask(text: Any, secrets: tuple[str, ...] = ()) -> str:
    s = str(text)
    for sec in secrets:
        if sec:
            s = s.replace(sec, "***")
    s = re.sub(r"signature=[0-9a-fA-F]+", "signature=***", s, flags=re.I)
    return _HEX.sub("***", s)


def mask_key(k: str) -> str:
    return "***" if len(k) < 12 else f"{k[:2]}***{k[-2:]}"


def guard_env(env: str | None) -> None:
    if env == "live":
        raise SafetyError("--env live reddedildi: bu betik yalniz testnet icindir")
    if env != "testnet":
        raise SafetyError("--env testnet zorunlu")


def guard_base_url(url: str) -> None:
    if str(url).rstrip("/") not in ALLOWED_BASES:
        raise SafetyError("taban adres izin listesinde degil (yalniz Binance vadeli testnet)")


def guard_rest(rest: Any) -> None:
    """Istemcinin kipi ve taban adresi testnet olmali (izin listesi sabit kodlu)."""
    if getattr(rest, "env", None) != "testnet":
        raise SafetyError("istemci kipi testnet degil")
    guard_base_url(getattr(rest, "_base", ""))


def guard_config(cfg: Any) -> None:
    """Testnet kipi + testnet var dizini + paylasimli testnet KILL/PAUSE yollari."""
    if cfg.mode != "testnet":
        raise SafetyError(f"yapilandirma kipi testnet degil: {cfg.mode}")
    if "testnet" not in str(cfg.var_dir):
        raise SafetyError("var_dir testnet dizini degil")
    for name in ("kill_file", "pause_file"):
        if "testnet" not in str(getattr(cfg, name)):
            raise SafetyError(f"{name} shared/testnet altinda degil")


def read_keys(environ: Mapping[str, str]) -> tuple[str, str]:
    out = []
    for n in KEY_VARS:
        v = environ.get(n)
        if not isinstance(v, str) or len(v) < 32 or any(c.isspace() for c in v):
            raise SafetyError(f"anahtar eksik/gecersiz: {n}")
        out.append(v)
    return out[0], out[1]


def check_withdrawals(restrictions: Mapping[str, Any] | None, *, ack_no_withdraw: bool) -> str:
    """Para cekme acik anahtar reddedilir. Testnette SAPI apiRestrictions yok (None): operator --ack-no-withdraw ile
    'anahtarin cekme izni yok' diye acikca onaylamali; onay yoksa reddedilir."""
    if restrictions is None:
        if not ack_no_withdraw:
            raise SafetyError("cekme izni dogrulanamadi (testnette apiRestrictions yok): --ack-no-withdraw gerekir")
        return "operator_ack"
    if str(restrictions.get("enableWithdrawals", True)).lower() != "false":
        raise SafetyError("anahtarda para cekme izni acik: reddedildi")
    return "verified"


def min_order_qty(min_qty: float, step: float, min_notional: float, price: float, headroom: float = 1.2) -> Decimal:
    """En kucuk guvenli miktar: max(min_qty, min_notional*headroom/price) adima yukari yuvarlanir."""
    st = Decimal(str(step))
    want = max(Decimal(str(min_qty)), Decimal(str(min_notional)) * Decimal(str(headroom)) / Decimal(str(price)))
    return (want / st).to_integral_value(rounding=ROUND_CEILING) * st


@dataclass
class StepResult:
    name: str
    ref: str
    status: str = "BEKLEMEDE"
    notes: list[str] = field(default_factory=list)
    data: dict[str, Any] = field(default_factory=dict)
    seconds: float = 0.0


class Report:
    def __init__(self, started: str, secrets: tuple[str, ...] = ()) -> None:
        self.started, self.secrets = started, secrets
        self.results: list[StepResult] = []
        self.cleanup: list[str] = []
        self.meta: dict[str, Any] = {}

    def to_dict(self) -> dict:
        d = {"started": self.started, "meta": self.meta, "cleanup": self.cleanup,
             "results": [vars(r) for r in self.results]}
        return json.loads(mask(json.dumps(d, default=str, ensure_ascii=False), self.secrets))

    def to_markdown(self) -> str:
        d = self.to_dict()
        L = [f"# Testnet duman/tatbikat raporu {d['started']}", "",
             f"Meta: `{json.dumps(d['meta'], ensure_ascii=False)}`", "",
             "| Adim | Ref | Durum | sn | Not |", "|---|---|---|---|---|"]
        for r in d["results"]:
            L.append(f"| {r['name']} | {r['ref']} | {r['status']} | {r['seconds']:.1f} | {'; '.join(r['notes'])[:300]} |")
        L += ["", "## Temizlik", *(f"- {c}" for c in d["cleanup"]), ""]
        return "\n".join(L)

    def write(self, root: Path, stamp: str) -> Path:
        out = Path(root) / "smoke" / stamp
        out.mkdir(parents=True, exist_ok=True)
        (out / "result.json").write_text(json.dumps(self.to_dict(), indent=2, ensure_ascii=False), encoding="utf-8")
        (out / "result.md").write_text(self.to_markdown(), encoding="utf-8")
        return out
