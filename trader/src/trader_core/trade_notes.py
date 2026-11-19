"""DD-12 WP-09: islem notu (KODLA yazilir) ve aday ders yasam dongusu.

Spec 6.2 + 18 Kasim 2026 eki: not = sabit sablon + sayisal alanlar + sabit sozlukten etiketler;
`trade_notes.model = "code"`, `cost_usd = 0`; LLM cagrisi YOK. Her kapanan islem (esiksiz) gece notu alir;
notun ders onerisi ertesi gun "aday ders" olur; etkisi <= 0 olan aday emekli olur (kayit kalir).
Etiketler ML egitim verisidir (WP-10): islem SONRASI etiketlerdir => hedef/olcum tarafi, ozellik DEGIL.
Ag yok, rastgelelik yok: ayni defter => ayni notlar.
"""
from __future__ import annotations

import json
import math
import os
import tempfile
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

NOTE_MODEL = "code"
NOTE_COST_USD = 0.0

# Sabit etiket sozlugu: kategori -> izinli degerler. Etiket metni `kategori:deger`.
TAG_VOCAB: dict[str, tuple[str, ...]] = {
    "giris": ("iyi", "kotu_dolum"),
    "stop": ("dar", "normal", "genis"),
    "seans": ("open", "closed", "weekend", "yok"),
    "rejim": ("trend_up", "trend_down", "range", "volatile", "unclear"),
    "olay": ("bilinmiyor",),                       # kod haber/olay bilemez; sabit
    "uyum": ("uyumlu", "uyumsuz"),
    "kacinilabilir": ("evet", "hayir"),
    "sonuc": ("kazanc", "kayip", "basabas"),
}
LESSON_CODES = ("seans_kapali", "yuksek_vol", "dusuk_rr")
LESSON_PREFIX = "ders:"
TAG_CATEGORIES = tuple(TAG_VOCAB) + ("ders",)

HIGH_VOL_ATR_RATIO = 1.3            # sabit kovalar (belirlenimci)
LOW_RR = 2.0
DEFAULT_SHRINK_N = 10
_FIT = {"R1": ("range",), "T1": ("trend_up", "trend_down")}   # kurulum -> uyumlu rejimler (bilinmeyen kurulum: uyumlu)
EPS = 1e-9


def _num(x) -> bool:
    return isinstance(x, (int, float)) and not isinstance(x, bool) and math.isfinite(x)


# ---------------------------------------------------------------------------
# Etiket sozlugu
# ---------------------------------------------------------------------------

def lesson_id(code: str, setup: str) -> str:
    return f"{code}:{setup}"


def valid_tag(tag: Any) -> bool:
    if not isinstance(tag, str) or ":" not in tag:
        return False
    cat, val = tag.split(":", 1)
    if cat == "ders":
        code, _, setup = val.partition(":")
        return code in LESSON_CODES and bool(setup) and setup.replace("_", "").isalnum()
    return cat in TAG_VOCAB and val in TAG_VOCAB[cat]


def validate_tags(tags: Sequence[str]) -> list[str]:
    """Sozluk disi etiket => ValueError (not yazilmaz)."""
    if isinstance(tags, (str, bytes)):
        raise ValueError("tags liste olmali")
    bad = [t for t in tags if not valid_tag(t)]
    if bad:
        raise ValueError(f"sozluk disi etiket: {bad}")
    return list(tags)


# ---------------------------------------------------------------------------
# Not uretimi (saf fonksiyon)
# ---------------------------------------------------------------------------

def _f(d, key):
    v = (d.features or {}).get(key) if d is not None else None
    return float(v) if _num(v) else None


def lesson_matches(code: str, setup: str, dec) -> bool:
    """Karar kaydi (aday) dersin kosuluna uyar mi? Yalniz karar aninda bilinen alanlar."""
    if getattr(dec, "setup", None) != setup:
        return False
    if code == "seans_kapali":
        return getattr(dec, "session_tag", None) in ("closed", "weekend")
    if code == "yuksek_vol":
        ar = getattr(dec, "atr_ratio", None)
        return _num(ar) and ar >= HIGH_VOL_ATR_RATIO
    if code == "dusuk_rr":
        rr = _f(dec, "rr")
        return rr is not None and rr < LOW_RR
    return False


def build_note(trade, dec) -> tuple[list[str], str]:
    """(etiketler, metin). `trade`: TradeRecord (kapanmis), `dec`: DecisionRecord (None olabilir)."""
    r = trade.r_multiple
    tags: list[str] = []
    risk = abs(trade.planned_entry - trade.planned_stop)
    slip_frac = abs(trade.entry_price - trade.planned_entry) / risk if risk > 0 else 0.0
    tags.append("giris:kotu_dolum" if slip_frac > 0.10 else "giris:iyi")
    sd = _f(dec, "stop_dist_atr")
    tags.append("stop:dar" if sd is not None and sd < 1.0 else "stop:genis" if sd is not None and sd > 3.0
                else "stop:normal")
    st = getattr(dec, "session_tag", None)
    tags.append(f"seans:{st if st in ('open', 'closed', 'weekend') else 'yok'}")
    reg = trade.regime if trade.regime in TAG_VOCAB["rejim"] else "unclear"
    tags.append(f"rejim:{reg}")
    tags.append("olay:bilinmiyor")
    fit = _FIT.get(trade.setup)
    tags.append("uyum:uyumsuz" if fit is not None and trade.regime not in fit else "uyum:uyumlu")
    mfe = trade.mfe_r
    loss = r is not None and r < -EPS
    tags.append("sonuc:kayip" if loss else "sonuc:kazanc" if (r is not None and r > EPS) else "sonuc:basabas")
    lessons: list[str] = []
    if loss and dec is not None:
        lessons = [lesson_id(c, trade.setup) for c in LESSON_CODES if lesson_matches(c, trade.setup, dec)]
    avoidable = loss and (bool(lessons) or "giris:kotu_dolum" in tags or "uyum:uyumsuz" in tags)
    tags.insert(tags.index("sonuc:kayip") if loss else len(tags), f"kacinilabilir:{'evet' if avoidable else 'hayir'}")
    tags.extend(LESSON_PREFIX + lid for lid in lessons)
    validate_tags(tags)

    def fmt(x, nd=2):
        return "yok" if x is None else f"{x:.{nd}f}"

    text = (f"{trade.pair} {trade.side} {trade.setup} ({trade.regime}): R={fmt(r)}, cikis={trade.exit_reason}, "
            f"tutulan_bar={trade.bars_held if trade.bars_held is not None else 'yok'}, MFE={fmt(mfe)} R, "
            f"MAE={fmt(trade.mae_r)} R, giris_kaymasi={slip_frac:.2f} risk, stop_mesafesi={fmt(sd)} ATR, "
            f"seans={st or 'yok'}, atr_orani={fmt(getattr(dec, 'atr_ratio', None))}, rr={fmt(_f(dec, 'rr'))}. "
            f"Ders onerisi: {', '.join(lessons) if lessons else 'yok'}.")
    return tags, text


def _day_start(day: str) -> datetime:
    return datetime.strptime(day, "%Y-%m-%d").replace(tzinfo=timezone.utc)


def write_nightly_notes(ledger, run_day: str) -> dict:
    """Notu olmayan her kapanan islem icin bir not satiri yazar (esik yok; idempotent). `ledger`: yazilabilir.
    Gun siniri yok: kapanmis ve notsuz her islem (gec kapananlar sonraki kosuda) not alir; acik islem almaz."""
    have = {n["trade_id"] for n in ledger.list_trade_notes()}
    closed = ledger.list_closed_trades(limit=ledger.LIST_CLOSED_MAX)
    n_new = 0
    for t in sorted(closed, key=lambda x: x.trade_id):
        if t.trade_id in have:
            continue
        try:
            dec = ledger.get_decision(t.decision_id)
        except Exception:  # noqa: BLE001
            dec = None
        tags, text = build_note(t, dec)
        ledger.record_trade_note(t.trade_id, run_day, tags, text, model=NOTE_MODEL, cost_usd=NOTE_COST_USD)
        n_new += 1
    return {"written": n_new, "already": len(have), "closed": len(closed)}


# ---------------------------------------------------------------------------
# Aday ders yasam dongusu
# ---------------------------------------------------------------------------

def _load_state(path) -> dict:
    p = Path(path)
    if not p.exists():
        return {}
    try:
        d = json.loads(p.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return d if isinstance(d, dict) else {}


def _save_state(path, state: Mapping) -> None:
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=str(p.parent), prefix=".lc-", suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            json.dump(state, fh, sort_keys=True, indent=1)
            fh.flush()
            os.fsync(fh.fileno())
        os.replace(tmp, p)
    finally:
        if os.path.exists(tmp):
            os.unlink(tmp)


def lesson_effect(ledger, lid: str, born_day: str, as_of: datetime, shrink_n: int = DEFAULT_SHRINK_N):
    """Dersin sonumlu etkisi (spec 6.1/6.3): ertesi gunden (`born_day`+1) `as_of`a kadar dersin kosuluna uyan ve
    ALINAN adaylarin gercek net R'sinin eksi toplami (ders alinmamasini onerir; kacinilan zarar = +). n = uyan kapanmis
    islem sayisi; etki = -SumR * n/(n+shrink_n). n = 0 => (0.0, 0)."""
    code, _, setup = lid.partition(":")
    since = _day_start(born_day) + timedelta(days=1)
    closed = {t.decision_id: t for t in ledger.list_closed_trades(limit=ledger.LIST_CLOSED_MAX)
              if t.exit_ts is not None and t.exit_ts < as_of and t.r_multiple is not None}
    rs = []
    for d in ledger.list_decisions(since_ts=since, until_ts=as_of, final_action="entered"):
        t = closed.get(d.id)
        if t is not None and lesson_matches(code, setup, d):
            rs.append(float(t.r_multiple))
    n = len(rs)
    if n == 0:
        return 0.0, 0
    return -math.fsum(rs) * n / (n + max(0, int(shrink_n))), n


def lifecycle_tick(ledger, state_path, run_day: str, shrink_n: int = DEFAULT_SHRINK_N) -> dict:
    """Gece: (1) notlardaki yeni ders onerileri aday olur (dogum = not tarihi; ertesi gun kullanilir);
    (2) her aday/yasayan ders olculur: etki > 0 yasar, <= 0 emekli (kayit kalir; emekli geri donmez);
    olcum yoksa (n = 0) aday olarak bekler. Donus: ozet (born/alive/retired kimlikleri)."""
    state = _load_state(state_path)
    old = set(state)
    for n in ledger.list_trade_notes():
        for t in n["tags"]:
            if t.startswith(LESSON_PREFIX) and valid_tag(t):
                lid = t[len(LESSON_PREFIX):]
                if lid not in state:
                    state[lid] = {"status": "candidate", "born": n["note_date"], "effect": None, "n": 0}
    as_of = _day_start(run_day)                            # notlarla ayni sinir: run_day 00:00 UTC oncesi
    out = {"born": sorted(set(state) - old), "alive": [], "retired": []}
    for lid, st in sorted(state.items()):
        if st.get("status") == "retired":
            continue
        eff, n = lesson_effect(ledger, lid, st["born"], as_of, shrink_n)
        st["effect"], st["n"] = round(eff, 6), n
        if n == 0:
            continue
        if eff > 0:
            if st["status"] != "alive":
                out["alive"].append(lid)
            st["status"] = "alive"
        else:
            st["status"], st["retired_day"] = "retired", run_day
            out["retired"].append(lid)
    _save_state(state_path, state)
    return out


def active_lessons(state_path, limit: int = 8) -> list[str]:
    """Istemde/ders servisinde kullanilacak aday+yasayan dersler (emekliler cikar); yasayanlar once, etkiye gore."""
    st = _load_state(state_path)
    live = [(lid, v) for lid, v in st.items() if v.get("status") in ("candidate", "alive")]
    live.sort(key=lambda kv: (kv[1]["status"] != "alive", -(kv[1].get("effect") or 0.0), kv[0]))
    return [lid for lid, _ in live[:max(0, int(limit))]]


def match_lessons(active: Iterable[str], dec) -> list[str]:
    """Karar aninda aday ders kimlikleri (`lesson_ids` icin)."""
    out = []
    for lid in active:
        code, _, setup = lid.partition(":")
        if lesson_matches(code, setup, dec):
            out.append(lid)
    return out


# ---------------------------------------------------------------------------
# ML disa aktarimi (WP-10): yapisal etiketler
# ---------------------------------------------------------------------------

def export_ml_rows(ledger) -> list[dict]:
    """Her not icin yapisal satir: trade_id, note_date, kategori->deger, ders kimlikleri, R. ETIKETLER islem SONRASIDIR:
    `role: "label"` (ozellik olarak kullanilmaz)."""
    rt = {t.trade_id: t.r_multiple for t in ledger.list_closed_trades(limit=ledger.LIST_CLOSED_MAX)}
    rows = []
    for n in ledger.list_trade_notes():
        cats: dict[str, str] = {}
        lessons: list[str] = []
        for t in n["tags"]:
            c, _, v = t.partition(":")
            if c == "ders":
                lessons.append(v)
            else:
                cats[c] = v
        rows.append({"trade_id": n["trade_id"], "note_date": n["note_date"], "tags": cats, "lesson_ids": lessons,
                     "r": rt.get(n["trade_id"]), "role": "label"})
    return rows
