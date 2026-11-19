"""WP-2 gunluk sapma izleyicisi: kabul testleri (spec: docs/kagit-degerlendirme-plani.md §4 + §8, docs/saglik-spec.md §16.6).

Bagimsiz test yazari: uygulama kodu OKUNMADI. Yalniz spec + commit edilmis defter semasi (trader_core.ledger) kullanildi.

VARSAYIMLAR (spec'te adi/biçimi belirtilmeyen yerler; hepsi tek yerde, asagidaki sabit/yardimcilarda toplanmistir)
  * Kara kutu CLI: `scripts/drift_run.py --bot <learner|twin> --var-dir <VAR_DIR> [--once]` (bayraklar `--help` ciktisindan
    yoklanir; `--now` varsa kullanilir, yoksa GERCEK saat: her test kendi NOW'unu `datetime.now()`'dan alir ve sinir testleri
    +-2 dk pay birakir); cikti
    `<VAR_DIR>/<bot>/drift.json` (spec §4.6). Defter `<VAR_DIR>/<bot>/ledger.sqlite`, motor durumu `<VAR_DIR>/<bot>/status.json`
    (kip `status.json["mode"]`'dan okunur). CLI bayraklari farkliysa yalniz `run_drift()` degisir.
  * Kural kimlikleri `rules` anahtarlari: S1 S2 S3 M1 M3 F1 F2 P1 C1; M2 uc alt kural icerir, anahtar adlari belirtilmedigi icin
    `m2_rule()` "M2" ile baslayan anahtarlari ad ipuclarina (entry/giris, stop, piyasa/market/diger) gore ya da bulunamazsa
    giris, stop, piyasa sirasina gore secer.
  * `rules[k]["value"]`: S1 saat, S2/S3 aday sayisi, M3 oran, F1 oran, P1 C(n) (R), C1 S degeri. M1/M2 `value` (bp varsayimi)
    ASSERT EDILMEZ; yalniz duzey.
  * `window` = {"key", "start", "n"}; `n` pencere ici kapanmis islem sayisi. `next_checkpoint` = {"n", "remaining"}.
  * Gunluk rapor satirlari: CLI stdout'unda "📐" ile baslayan satirlar (yoksa drift.json'da report_lines/lines/summary_lines
    anahtarlarindan biri). Hicbiri yoksa test 18 BASARISIZ olur (gizlenmez).
  * Sentetik defter: semayi gercek `Ledger` yaratir; satirlar ham sqlite INSERT ile yazilir (r_multiple, kayma vb. dogrudan
    kontrol icin; tetikleyiciler yalniz UPDATE/DELETE'i engeller).
"""
from __future__ import annotations

import hashlib
import json
import math
import os
import random
import re
import sqlite3
import subprocess
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "tests"))

pytest.importorskip("trader_core.drift_monitor")

from panel_support import PARAMS  # noqa: E402
from trader_core import ledger as L  # noqa: E402

UTC = timezone.utc
SCRIPT = ROOT / "scripts" / "drift_run.py"
NOW = datetime.now(UTC).replace(microsecond=0)      # her test icin autouse fixture ile yenilenir (CLI'da --now yoksa gercek saat)
LEVELS = {"OK", "IZLE", "UYARI", "YETERSIZ"}
H = timedelta(hours=1)
D = timedelta(days=1)


@pytest.fixture(autouse=True)
def _fresh_now():
    global NOW
    NOW = datetime.now(UTC).replace(microsecond=0)
    yield


_HELP: dict = {}


def _cli_flags() -> str:
    if "t" not in _HELP:
        cp = subprocess.run([sys.executable, str(SCRIPT), "--help"], capture_output=True, text=True, timeout=60, env=_env(),
                            cwd=str(ROOT))
        _HELP["t"] = cp.stdout + cp.stderr
    return _HELP["t"]


def z(dt: datetime) -> str:
    return dt.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%S.000Z")


# --------------------------------------------------------------------------------------------- sentetik dunya
class World:
    def __init__(self, tmp: Path, bot: str = "learner", mode: str = "paper", funding_missing: int = 0, pv: int = 1):
        self.bot, self.mode, self.pv = bot, mode, pv
        self.var = tmp / "var"
        self.dir = self.var / bot
        self.dir.mkdir(parents=True)
        self.db = self.dir / "ledger.sqlite"
        led = L.open_ledger(self.db, bot, clock=lambda: NOW - 60 * D)
        led.init_params(PARAMS, reason="x")
        led.close()
        self._did = 0
        self._tid = 0
        self._k = 0                      # islem sirasi -> cikis zamani
        self.base = NOW - 25 * D
        self.status_extra = {"funding_missing": funding_missing}
        self.write_status()

    # -- status.json
    def write_status(self, **over):
        doc = {"schema": "engine-status/1", "bot": self.bot, "mode": self.mode, "pid": 1,
               "started_at": z(NOW - 70 * D), "loop_at": z(NOW - timedelta(seconds=5)), "trigger_tf": "1h",
               "param_version_id": self.pv, "strategy": {"name": "price_action_v1", "version": "1b.0"},
               "ml": {"mode": "off", "model_id": None}, "counters": {"funding_missing": self.status_extra["funding_missing"]}}
        doc.update(over)
        (self.dir / "status.json").write_text(json.dumps(doc), encoding="utf-8")

    def _c(self):
        c = sqlite3.connect(self.db)
        c.execute("PRAGMA foreign_keys=OFF")
        return c

    # -- kararlar
    def decision(self, ts: datetime, final="entered", skip=None, pv=1, pair="ETH/USDT"):
        veto, risk_allowed = "allowed", 1
        if final == "skipped":
            veto = {"veto_blocked": "blocked", "veto_missing": "missing", "veto_stale": "stale"}.get(skip, "allowed")
            if skip in ("stop_width", "rr_below_min", "other", "entry_gate_closed", "ml_filter"):
                veto, risk_allowed = "not_evaluated", None
            elif skip == "risk_denied":
                risk_allowed = 0
            elif veto in ("blocked", "missing", "stale"):
                risk_allowed = 1
        sized = (0.3, 600.0, 200.0, 13.0, 3) if final == "entered" else (None,) * 5
        c = self._c()
        with c:
            cur = c.execute(
                "INSERT INTO decision_events (bot,bar_close_ts,trigger_tf,pair,side,setup,regime,atr_ratio,rh,rl,rh_touches,"
                "rl_touches,features,planned_entry,planned_stop,planned_target,param_version_id,veto_status,veto_reason,"
                "risk_allowed,risk_reason,size_qty,size_notional,size_margin,size_risk_amount,leverage,final_action,"
                "skip_reason,recorded_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (self.bot, z(ts), "1h", pair, "long", "T1", "unclear", None, None, None, 0, 0, "{}", 2000.0, 1960.0, 2100.0,
                 pv, veto, None, risk_allowed, None, *sized, final, skip, z(ts)))
            did = cur.lastrowid
        c.close()
        self._did += 1
        return did

    def candidates(self, n: int, span_days: float = 13.0, newest_h: float = 1.0):
        """n adet veto oncesi aday (`entered`), son `span_days` gune esit aralikla (hepsi 14 gun icinde)."""
        step = span_days * 24.0 / max(n, 1)
        for i in range(n):
            self.decision(NOW - timedelta(hours=newest_h + i * step) , "entered")

    # -- islemler
    def trade(self, r=-1.0, *, exit_ts=None, pv=None, fee_entry_bp=5.0, fee_exit_bp=5.0, slip_entry_bp=2.2,
              slip_exit_bp=5.2, reason="stop", risk=10.0, funding=0.0, qty=1.0, entry_price=1000.0, exit_price=1000.0,
              planned_entry=None, planned_exit=None, entry_ts=None, closed=True):
        pv = self.pv if pv is None else pv
        if exit_ts is None:
            exit_ts = self.base + self._k * H
        self._k += 1
        entry_ts = entry_ts or (exit_ts - H)
        did = self.decision(entry_ts, "entered", pv=pv)
        self._tid += 1
        tid = self._tid
        pe = entry_price if planned_entry is None else planned_entry
        pnl_risk = risk if (math.isfinite(risk) and risk > 0) else 10.0
        c = self._c()
        with c:
            c.execute(
                "INSERT INTO trade_entries (bot,trade_id,decision_id,param_version_id,pair,side,setup,entry_ts,entry_price,"
                "planned_entry,planned_stop,planned_target,qty,leverage,planned_risk,fee_entry,slippage_entry,recorded_at)"
                " VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (self.bot, tid, did, pv, "ETH/USDT", "long", "T1", z(entry_ts), entry_price, pe, pe * 0.98, pe * 1.05, qty, 3,
                 risk, fee_entry_bp * 1e-4 * qty * entry_price, slip_entry_bp * 1e-4, z(entry_ts)))
            if closed:
                c.execute(
                    "INSERT INTO trade_exits (bot,trade_id,exit_ts,exit_price,exit_reason,planned_exit,fee_exit,funding_paid,"
                    "gross_pnl,realized_pnl,r_multiple,slippage_exit,recorded_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
                    (self.bot, tid, z(exit_ts), exit_price, reason, planned_exit, fee_exit_bp * 1e-4 * qty * exit_price,
                     funding, r * pnl_risk, r * pnl_risk, r, None if slip_exit_bp is None else slip_exit_bp * 1e-4, z(exit_ts)))
        c.close()
        return tid

    def trades(self, n: int, rs=None, **kw):
        for i in range(n):
            self.trade(-1.0 if rs is None else (rs[i] if hasattr(rs, "__getitem__") else rs), **kw)

    def activation(self, at: datetime, kind="apply", version_id=2):
        c = self._c()
        with c:
            if version_id != 1:
                have = c.execute("SELECT 1 FROM param_versions WHERE id=?", (version_id,)).fetchone()
                if not have:
                    row = c.execute("SELECT params, params_hash, lesson_bounds FROM param_versions WHERE id=1").fetchone()
                    c.execute("INSERT INTO param_versions (id,bot,params,params_hash,lesson_bounds,parent_version_id,author,"
                              "reason,created_at) VALUES (?,?,?,?,?,?,?,?,?)",
                              (version_id, self.bot, row[0], hashlib.sha256(f"v{version_id}".encode()).hexdigest(), row[2], 1,
                               "user", "y", z(at)))
            c.execute("INSERT INTO param_activations (bot,version_id,prev_version_id,kind,actor,reason,activated_at)"
                      " VALUES (?,?,?,?,?,?,?)", (self.bot, version_id, 1, kind, "user", "y", z(at)))
        c.close()

    def run(self, now: datetime | None = None, check=True) -> "Result":
        return run_drift(self, now, check=check)


class Result:
    def __init__(self, cp, path: Path):
        self.rc, self.out, self.err = cp.returncode, cp.stdout, cp.stderr
        self.path = path
        self.doc = json.loads(path.read_text(encoding="utf-8")) if path.exists() else None

    def rule(self, rid: str) -> dict:
        assert self.doc is not None, f"drift.json yok; stderr={self.err[-500:]}"
        return self.doc["rules"][rid]

    def level(self, rid: str) -> str:
        return self.rule(rid)["level"]


def _env():
    e = dict(os.environ)
    e["PYTHONPATH"] = os.pathsep.join([str(ROOT / "src"), e.get("PYTHONPATH", "")])
    return e


def _argv(var, bot, now=None):
    flags = _cli_flags()
    a = ["--bot", bot, "--var-dir", str(var)]
    if "--once" in flags:
        a.append("--once")
    if now is not None and "--now" in flags:
        a += ["--now", now.isoformat()]
    return a


def run_drift(w: World, now: datetime | None = None, check=True, var: Path | None = None, bot: str | None = None) -> Result:
    var = var or w.var
    bot = bot or w.bot
    assert SCRIPT.exists(), "scripts/drift_run.py yok"
    cp = subprocess.run([sys.executable, str(SCRIPT), *_argv(var, bot, now or NOW)],
                        capture_output=True, text=True, timeout=120, env=_env(), cwd=str(ROOT))
    res = Result(cp, var / bot / "drift.json")
    if check:
        assert res.rc == 0, f"drift_run cikis kodu {res.rc}\nstdout={res.out[-800:]}\nstderr={res.err[-1500:]}"
        assert res.doc is not None, "drift.json yazilmadi"
    return res


def m2_rule(res: Result, kind: str) -> dict:
    keys = sorted(k for k in res.doc["rules"] if k.upper().startswith("M2"))
    assert len(keys) >= 3, f"M2 icin uc alt kural bekleniyor: {keys}"
    hints = {"entry": ("entry", "giris", "giriş"), "stop": ("stop",), "market": ("market", "piyasa", "diger", "diğer", "other")}
    for k in keys:
        if any(h in k.lower() for h in hints[kind]):
            return res.doc["rules"][k]
    return res.doc["rules"][keys[["entry", "stop", "market"].index(kind)]]


def approx(a, b, tol=1e-6):
    return a is not None and abs(float(a) - float(b)) <= tol


@pytest.fixture
def w(tmp_path):
    return World(tmp_path)


def quiet_first(w: World, days: float):
    """Defterdeki ilk karar satiri `days` gun once (aday sayilmaz)."""
    w.decision(NOW - timedelta(days=days), "skipped", "stop_width")


# ------------------------------------------------------------------------------------------ 1. S2 sinirlari
@pytest.mark.parametrize("n,exp", [(21, "OK"), (20, "IZLE"), (16, "IZLE"), (15, "UYARI"), (54, "OK"), (55, "IZLE"),
                                   (61, "IZLE"), (62, "UYARI")])
def test_01_s2_boundaries(w, n, exp):
    quiet_first(w, 20)
    w.candidates(n)
    r = w.run()
    assert r.level("S2") == exp
    assert approx(r.rule("S2")["value"], n)


@pytest.mark.parametrize("n,exp", [(75, "OK"), (52, "OK"), (51, "IZLE"), (45, "IZLE"), (44, "UYARI"), (98, "OK"),
                                   (99, "IZLE"), (107, "IZLE"), (108, "UYARI")])
def test_01b_s3_boundaries(w, n, exp):
    quiet_first(w, 40)
    w.candidates(n, span_days=28.0)
    assert w.run().level("S3") == exp


# ------------------------------------------------------------------------------------------ 2. S2 isinma
@pytest.mark.parametrize("n", [0, 3, 35, 70])
def test_02_s2_warmup_13_days_is_yetersiz(w, n):
    quiet_first(w, 13)
    w.candidates(n, span_days=12.0)
    assert w.run().level("S2") == "YETERSIZ"


def test_02_s2_exactly_14_days_is_evaluated(w):
    quiet_first(w, 14 + 2 / 1440)
    w.candidates(30, span_days=13.0)
    assert w.run().level("S2") == "OK"


def test_02_s3_warmup_under_30_days(w):
    quiet_first(w, 25)
    w.candidates(70, span_days=24.0)
    assert w.run().level("S3") == "YETERSIZ"


# ------------------------------------------------------------------------------------------ 3. aday tanimi
def test_03_candidate_definition(w):
    quiet_first(w, 20)
    for sr, cnt in (("stop_width", 15), ("rr_below_min", 10), ("risk_denied", 8), ("other", 7)):
        for i in range(cnt):
            w.decision(NOW - timedelta(hours=3 + 7 * i + len(sr) % 5), "skipped", sr, pair=f"P{i}/{sr}")
    for sr, cnt in (("veto_blocked", 3), ("entry_gate_closed", 2), ("veto_missing", 1), ("veto_stale", 1),
                    ("order_failed", 1), ("ml_filter", 1)):
        for i in range(cnt):
            w.decision(NOW - timedelta(hours=2 + 11 * i + len(sr)), "skipped", sr, pair=f"Q{i}/{sr}")
    w.candidates(10, span_days=10.0)
    r = w.run()
    assert approx(r.rule("S2")["value"], 19), r.rule("S2")     # 10 entered + 9 sayilan skipped
    assert r.level("S2") == "IZLE"                              # stop_width vb. sayilsaydi 59+ olur


def test_03_only_excluded_skips_give_zero_candidates(w):
    quiet_first(w, 20)
    for i in range(30):
        w.decision(NOW - timedelta(hours=2 + i), "skipped", ("stop_width", "rr_below_min", "risk_denied", "other")[i % 4],
                   pair=f"Z{i}/USDT")
    assert approx(w.run().rule("S2")["value"], 0)


# ------------------------------------------------------------------------------------------ 4. S1
@pytest.mark.parametrize("hours,off_min,exp", [(96, -2, "OK"), (96, 2, "IZLE"), (97, 0, "IZLE"), (120, -2, "IZLE"),
                                                (120, 2, "UYARI"), (121, 0, "UYARI")])
def test_04_s1_silence(w, hours, off_min, exp):
    # gercek saat kullanildigi icin tam sinir (96,0 / 120,0) yerine +-2 dk pay; `value` saat cinsinden
    w.decision(NOW - hours * H - timedelta(minutes=off_min), "entered")
    r = w.run()
    assert r.level("S1") == exp
    assert approx(r.rule("S1")["value"], hours + off_min / 60, 0.1)


def test_04_s1_no_decisions_is_yetersiz(w):
    assert w.run().level("S1") == "YETERSIZ"


def test_04_s1_without_any_candidate_uses_first_decision(w):
    w.decision(NOW - 100 * H, "skipped", "stop_width")
    assert w.run().level("S1") == "IZLE"


# ------------------------------------------------------------------------------------------ 5. ayar degisikligi indirimi
def test_05_param_change_downgrades_s2_not_s1(w):
    quiet_first(w, 20)
    w.candidates(15, span_days=8.5, newest_h=121.0)          # en yeni aday 121 sa once -> S1 UYARI
    # S1 icin son aday 121 sa once; S2 15 aday -> UYARI kosulu
    w.activation(NOW - 3 * D, "apply", 2)
    w.pv = 2
    w.write_status()
    r = w.run()
    assert r.level("S1") == "UYARI"                              # S1 indirilmez
    assert r.level("S2") == "IZLE"
    assert str(r.rule("S2").get("note") or "").strip() != ""


@pytest.mark.parametrize("age_d,kind,expected", [(20, "apply", "UYARI"), (3, "initial", "UYARI"), (3, "rollback", "IZLE")])
def test_05b_only_in_window_non_initial_activation_downgrades(w, age_d, kind, expected):
    quiet_first(w, 25)
    w.candidates(15, span_days=10.0)
    w.activation(NOW - age_d * D, kind, 1 if kind == "initial" else 2)
    r = w.run()
    # spec §4.1: `initial` disi etkinlestirme, pencere (son 14 gun) icinde ise indirim; rollback de etkinlestirmedir (§2)
    assert r.level("S2") == expected


# ------------------------------------------------------------------------------------------ 6. M1
@pytest.mark.parametrize("bp,exp", [(5.00, "OK"), (5.30, "IZLE"), (5.60, "UYARI"), (4.70, "IZLE"), (4.40, "UYARI")])
def test_06_m1_commission(w, bp, exp):
    w.trades(10, rs=-0.5, fee_entry_bp=9.0, fee_exit_bp=9.0)       # eski 10 islem: yalniz son 20 sayilir
    w.trades(20, rs=-0.5, fee_entry_bp=bp, fee_exit_bp=bp)
    assert w.run().level("M1") == exp


def test_06_m1_nine_trades_yetersiz(w):
    w.trades(9, rs=-0.5, fee_entry_bp=9.0, fee_exit_bp=9.0)
    assert w.run().level("M1") == "YETERSIZ"


def test_06_m1_ten_trades_is_enough(w):
    w.trades(10, rs=-0.5, fee_entry_bp=5.6, fee_exit_bp=5.6)
    assert w.run().level("M1") == "UYARI"


# ------------------------------------------------------------------------------------------ 7. M2
@pytest.mark.parametrize("bp,exp", [(4.3, "OK"), (4.4, "IZLE"), (6.4, "IZLE"), (6.5, "UYARI")])
def test_07_m2_entry(w, bp, exp):
    w.trades(60, rs=-0.5, slip_entry_bp=2.2)
    w.trades(50, rs=-0.5, slip_entry_bp=bp)                       # son 50 giris
    assert m2_rule(w.run(), "entry")["level"] == exp


def test_07_m2_entry_paper_lower_bound(tmp_path):
    w = World(tmp_path, mode="paper")
    w.trades(20, rs=-0.5, slip_entry_bp=1.4, slip_exit_bp=5.2)
    r = w.run()
    assert m2_rule(r, "entry")["level"] == "UYARI"
    blob = json.dumps(m2_rule(r, "entry"), ensure_ascii=False).lower()
    assert "kağıt" in blob or "kagit" in blob or "benzetim" in blob       # "kağıt: benzetim tutarlılığı"


def test_07_m2_entry_lower_bound_is_paper_only(tmp_path):
    w = World(tmp_path, mode="testnet")
    w.trades(20, rs=-0.5, slip_entry_bp=1.4)
    assert m2_rule(w.run(), "entry")["level"] == "OK"


def test_07_m2_paper_stop_lower_bound(tmp_path):
    w = World(tmp_path, mode="paper")
    w.trades(20, rs=-0.5, reason="stop", slip_exit_bp=4.4)
    assert m2_rule(w.run(), "stop")["level"] == "UYARI"


@pytest.mark.parametrize("bp,exp", [(8.8, "OK"), (8.9, "IZLE"), (12.4, "IZLE"), (12.5, "UYARI")])
@pytest.mark.parametrize("reason", ["stop", "trail_stop", "liquidation"])
def test_07_m2_stop(tmp_path, bp, exp, reason):
    w = World(tmp_path, mode="testnet")
    w.trades(20, rs=-0.5, reason=reason, slip_exit_bp=bp)
    assert m2_rule(w.run(), "stop")["level"] == exp


@pytest.mark.parametrize("bp,exp", [(4.0, "OK"), (4.1, "IZLE"), (6.0, "IZLE"), (6.1, "UYARI")])
def test_07_m2_market_exit(tmp_path, bp, exp):
    w = World(tmp_path, mode="testnet")
    w.trades(20, rs=0.5, reason="target", slip_exit_bp=bp)
    assert m2_rule(w.run(), "market")["level"] == exp


def test_07_m2_null_exit_slippage_excluded_from_mean(tmp_path):
    w = World(tmp_path, mode="testnet")
    w.trades(10, rs=-0.5, reason="stop", slip_exit_bp=9.0)      # ortalama 9.0 -> IZLE
    w.trades(20, rs=-0.5, reason="stop", slip_exit_bp=None)     # bos kayma: 0 sayilirsa 3.0 -> OK olurdu
    assert m2_rule(w.run(), "stop")["level"] == "IZLE"


def test_07_m2_fewer_than_10_fills_yetersiz(tmp_path):
    w = World(tmp_path, mode="testnet")
    w.trades(9, rs=-0.5, reason="stop", slip_exit_bp=20.0)
    w.trades(20, rs=-0.5, reason="stop", slip_exit_bp=None)
    r = w.run()
    assert m2_rule(r, "stop")["level"] == "YETERSIZ"


# ------------------------------------------------------------------------------------------ 8. M3
def _m3_hand(trades):
    tot = 0.0
    for t in trades:
        slip = t["qty"] * t["pe"] * t["se"] + t["qty"] * (t["px"] if t["px"] is not None else t["xp"]) * (t["sx"] or 0.0)
        tot += (t["fe"] + t["fx"] + slip) / t["risk"]
    return tot / len(trades)


def test_08_m3_hand_computed_20_trades(w):
    random.seed(8)
    specs = []
    for i in range(20):
        qty = 0.5 + 0.1 * i
        ep = 1000.0 + 13 * i
        xp = ep * (1 + 0.003 * ((-1) ** i))
        t = dict(qty=qty, pe=ep * 1.0004, se=(1.0 + 0.3 * (i % 5)) * 1e-4, xp=xp,
                 px=(xp * 1.0002 if i % 3 else None), sx=((2.0 + i % 4) * 1e-4 if i % 6 else None),
                 fe=0.2 + 0.01 * i, fx=0.25 + 0.02 * (i % 7), risk=8.0 + i)
        specs.append(t)
        w.trade(-1.0, entry_price=ep, exit_price=xp, planned_entry=t["pe"], planned_exit=t["px"], qty=qty,
                slip_entry_bp=t["se"] * 1e4, slip_exit_bp=None if t["sx"] is None else t["sx"] * 1e4, risk=t["risk"],
                reason="stop")
        # fee kolonlari bp'den uretilir; elle hesapta ayni degerleri kullan
    c = sqlite3.connect(w.db)
    rows = c.execute("SELECT qty, planned_entry, slippage_entry, fee_entry, planned_risk, exit_price, planned_exit, "
                     "slippage_exit, fee_exit FROM v_closed_trades ORDER BY trade_id").fetchall()
    c.close()
    exp = _m3_hand([dict(qty=q, pe=pe, se=se, fe=fe, fx=fx, risk=rk, xp=xpx, px=pxx, sx=sx)
                    for q, pe, se, fe, rk, xpx, pxx, sx, fx in rows])
    assert approx(w.run().rule("M3")["value"], exp, 1e-9)


@pytest.mark.parametrize("ratio,exp", [(0.18, "OK"), (0.19, "IZLE"), (0.21, "IZLE"), (0.22, "UYARI")])
def test_08_m3_levels(w, ratio, exp):
    # kayma yok (slip_entry 0, slip_exit bos): oran = (fee_entry + fee_exit) / risk; risk=100, fee_entry=fee_exit=ratio*50
    w.trades(20, rs=-0.5, risk=100.0, qty=1.0, entry_price=1000.0, exit_price=1000.0, slip_entry_bp=0.0, slip_exit_bp=None,
             fee_entry_bp=ratio * 50 / 0.1, fee_exit_bp=ratio * 50 / 0.1)
    r = w.run()
    assert r.level("M3") == exp
    assert approx(r.rule("M3")["value"], ratio, 1e-9)


def test_08_m3_needs_20_trades(w):
    w.trades(19, rs=-0.5, risk=100.0, fee_entry_bp=500.0, fee_exit_bp=500.0)
    assert w.run().level("M3") == "YETERSIZ"


# ------------------------------------------------------------------------------------------ 9. F1 / F2
@pytest.mark.parametrize("ratio,exp", [(0.020, "OK"), (0.021, "IZLE"), (0.030, "IZLE"), (0.031, "UYARI"), (-0.020, "OK"),
                                       (-0.021, "IZLE"), (-0.05, "IZLE"), (-0.5, "IZLE")])
def test_09_f1(w, ratio, exp):
    w.trades(20, rs=-0.5, risk=10.0, funding=ratio * 10.0)
    assert w.run().level("F1") == exp


def test_09_f1_needs_20_trades(w):
    w.trades(19, rs=-0.5, risk=10.0, funding=5.0)
    assert w.run().level("F1") == "YETERSIZ"


@pytest.mark.parametrize("missing,exp", [(0, "OK"), (1, "UYARI"), (7, "UYARI")])
def test_09_f2_funding_missing(tmp_path, missing, exp):
    w = World(tmp_path, funding_missing=missing)
    w.trades(3, rs=-0.5)
    assert w.run().level("F2") == exp


# ------------------------------------------------------------------------------------------ 10. P1
def _p1_world(w, n, c):
    w.trades(n - 1, rs=0.0)
    w.trade(c)


@pytest.mark.parametrize("c,exp", [(-19.6, "OK"), (-19.8, "IZLE"), (-28.0, "IZLE"), (-28.3, "UYARI"), (30.0, "OK")])
def test_10_p1_interpolated_n60(w, c, exp):
    _p1_world(w, 60, c)
    r = w.run()
    assert r.level("P1") == exp
    assert approx(r.rule("P1")["value"], c, 1e-6)


@pytest.mark.parametrize("c,exp", [(-18.2, "OK"), (-18.3, "IZLE"), (-25.6, "IZLE"), (-25.7, "UYARI")])
def test_10_p1_table_row_n50(w, c, exp):
    _p1_world(w, 50, c)
    assert w.run().level("P1") == exp


@pytest.mark.parametrize("c,exp", [(-11.0, "OK"), (-11.2, "IZLE"), (-14.6, "UYARI")])
def test_10_p1_table_first_row_n20(w, c, exp):
    _p1_world(w, 20, c)
    assert w.run().level("P1") == exp


def test_10_p1_n19_yetersiz(w):
    _p1_world(w, 19, -100.0)
    assert w.run().level("P1") == "YETERSIZ"


def test_10_p1_n301_yetersiz_with_extend_note(w):
    _p1_world(w, 301, -500.0)
    r = w.run()
    assert r.level("P1") == "YETERSIZ"
    assert "tablo" in str(r.rule("P1").get("note") or "").lower()


def test_10_p1_n300_still_evaluated(w):
    _p1_world(w, 300, -62.0)                                      # %2,5 sutunu -61,0
    assert w.run().level("P1") == "UYARI"


# ------------------------------------------------------------------------------------------ 11. CUSUM
MU0, SIG0, K = -0.111, 1.224, 0.5


def cusum_ref(rs):
    s = 0.0
    for r in rs:
        x = min(max(r, -1.5), 3.0)
        s = max(0.0, s - (x - MU0) / SIG0 - K)
    return s


def test_11_cusum_per_loss_increment():
    assert approx(cusum_ref([-1.0]), 0.2263, 1e-3)               # spec sabiti (oracle kendi kendini dogrular)


def test_11_cusum_consecutive_losses_sequence_and_cooldown(w):
    seen = {}
    for n in range(1, 21):
        w.trade(-1.0)
        if n in (1, 13, 14, 17, 18, 19, 20):
            r = w.run()
            seen[n] = (r.level("C1"), r.rule("C1")["value"])
    assert approx(seen[1][1], 0.2263, 1e-3)
    assert approx(seen[13][1], 2.94, 0.01) and seen[13][0] == "YETERSIZ"
    for n in (14, 17, 18, 19):
        assert seen[n][0] == "YETERSIZ", (n, seen[n])           # S >= 3,0 ama n < 20
    assert approx(seen[18][1], 4.07, 0.01)
    assert seen[20][0] == "UYARI"
    # UYARI aninda S sifirlanir: raporlanan value tetikleyen S (4,53) ya da sifirlanmis 0 olabilir (spec belirsiz)
    assert approx(seen[20][1], 4.53, 0.01) or approx(seen[20][1], 0.0, 1e-9), seen[20]
    for n in range(21, 51):                                      # sonraki 30 islem: yeni UYARI yok
        w.trade(-1.0)
        assert w.run().level("C1") != "UYARI", f"{n}. islemde cooldown ihlali"


def test_11_cusum_after_wins_then_losses(w):
    w.trades(20, rs=0.5)
    r = w.run()
    assert approx(r.rule("C1")["value"], 0.0, 1e-9)
    for k in range(1, 19):
        w.trade(-1.0)
        if k in (14, 18):
            r = w.run()
            if k == 14:
                assert approx(r.rule("C1")["value"], 3.17, 0.01) and r.level("C1") == "IZLE"
            else:
                assert r.level("C1") == "UYARI"
                assert approx(r.rule("C1")["value"], 4.07, 0.01) or approx(r.rule("C1")["value"], 0.0, 1e-9)


def test_11_cusum_clipping(tmp_path):
    base = [-1.0] * 14
    for big, label in ((10.0, "a"), (3.0, "b")):
        w = World(tmp_path / label)
        w.trades(14, rs=-1.0)
        w.trade(big)
        v = w.run().rule("C1")["value"]
        assert approx(v, cusum_ref(base + [3.0]), 1e-6), (big, v)   # +10 R, x=3,0 olarak kirpilir (S'yi 0'a cekmez: ~0,127)
    w = World(tmp_path / "c")
    w.trade(-5.0)
    assert approx(w.run().rule("C1")["value"], cusum_ref([-1.5]), 1e-6)  # alt kirpma -1,5


# ------------------------------------------------------------------------------------------ 12. kacirilan gunler
def test_12_missed_days_all_trades_processed_in_order(tmp_path):
    seq = [-1.0, -1.0, 2.0, -1.0, -1.0, -1.0, 8.0, -1.0, -1.0, -1.0, -1.0, -1.0,
           -1.0, -1.0, -1.0, -1.0, -1.0, 0.3, -1.0, -1.0, -1.0, -1.0, -1.0, -1.0]
    wa, wb = World(tmp_path / "a"), World(tmp_path / "b")
    for i, r in enumerate(seq):                                  # b: her islemden sonra calistir
        wb.trade(r)
        res_b = wb.run()
    for i, r in enumerate(seq):                                  # a: 12 islem, sonra kalan 12 islem tek calistirmada
        wa.trade(r)
        if i == 11:
            wa.run()
    res_a = wa.run()
    assert approx(res_a.rule("C1")["value"], cusum_ref(seq), 1e-6)
    assert approx(res_b.rule("C1")["value"], cusum_ref(seq), 1e-6)
    assert res_a.level("C1") == res_b.level("C1")


def test_12_state_file_missing_recomputes_deterministically(tmp_path):
    seq = [-1.0] * 10 + [0.5, -1.0, -1.0, 3.0] + [-1.0] * 12
    w = World(tmp_path / "a")
    for r in seq:
        w.trade(r)
    a = w.run()
    for p in list(w.dir.iterdir()):                               # izleyicinin durum dosyasini sil (drift.json dahil)
        if "drift" in p.name.lower():
            p.unlink()
    b = w.run()
    assert a.rule("C1")["value"] == b.rule("C1")["value"] and a.level("C1") == b.level("C1")


# ------------------------------------------------------------------------------------------ 13. pencere sifirlama
def test_13_window_reset_on_activation(w):
    w.trades(25, rs=-1.0)                                         # pencere 1 (pv=1)
    act = NOW - 30 * H
    w.activation(act, "apply", 2)
    w.pv = 2
    w.write_status()
    w.base = NOW - 28 * H
    w._k = 0
    w.trades(22, rs=0.1, pv=2)                                    # pencere 2
    # pv1'de acilmis, aktivasyondan SONRA kapanan islem: eski pencereye yazilir
    w.trade(-7.0, pv=1, entry_ts=act - 5 * H, exit_ts=NOW - timedelta(minutes=30))
    r = w.run()
    assert r.doc["window"]["n"] == 22
    assert approx(r.rule("P1")["value"], 22 * 0.1, 1e-6)          # C(n) yalniz yeni pencere
    assert approx(r.rule("C1")["value"], cusum_ref([0.1] * 22), 1e-6)   # S sifirdan


def test_13_trades_belong_to_window_where_opened(w):
    w.trades(5, rs=-1.0, pv=1)
    w.activation(NOW - 10 * H, "apply", 2)
    w.pv = 2
    w.write_status()
    w.trade(-1.0, pv=1, entry_ts=NOW - 12 * H, exit_ts=NOW - 2 * H)
    assert w.run().doc["window"]["n"] == 0


# ------------------------------------------------------------------------------------------ 14. bozuk satir
@pytest.mark.parametrize("bad_risk", [0.0, -1.0, float("inf")])
def test_14_bad_row_skipped_and_rules_at_best_izle(w, bad_risk):
    w.trades(30, rs=0.0, risk=10.0, fee_entry_bp=0.0, fee_exit_bp=0.0, slip_entry_bp=0.0, slip_exit_bp=None)
    w.trade(0.0, risk=bad_risk)
    r = w.run()
    assert r.doc["skipped_rows"] == 1
    for rid in ("M3", "F1", "P1", "C1"):
        assert r.level(rid) != "OK", rid
    assert approx(r.rule("M3")["value"], 0.0, 1e-12)              # bozuk satir hesaba girmedi
    assert r.doc["window"]["n"] in (30, 31)


def test_14_clean_ledger_reports_zero_skipped(w):
    w.trades(30, rs=0.0, risk=10.0, fee_entry_bp=0.0, fee_exit_bp=0.0, slip_entry_bp=0.0, slip_exit_bp=None)
    r = w.run()
    assert r.doc["skipped_rows"] == 0


# ------------------------------------------------------------------------------------------ 15. salt okunurluk
def _tree(root: Path):
    return {str(p.relative_to(root)): hashlib.sha256(p.read_bytes()).hexdigest() for p in root.rglob("*") if p.is_file()}


def test_15_read_only(w):
    w.trades(40, rs=-0.3)
    w.candidates(30)
    before_db = hashlib.sha256(w.db.read_bytes()).hexdigest()
    before = _tree(w.var)
    r = w.run()
    assert hashlib.sha256(w.db.read_bytes()).hexdigest() == before_db
    after = _tree(w.var)
    for name, h in before.items():
        if not name.startswith(f"{w.bot}/ledger.sqlite-"):
            assert after.get(name) == h, f"degisti/silindi: {name}"
    new = set(after) - set(before)
    for name in new:
        base = Path(name).name.lower()
        assert "drift" in base or base.startswith("ledger.sqlite-"), f"izin disi yeni dosya: {name}"
        assert not any(t in base for t in ("kill", "pause"))
    assert not list(w.var.rglob("KILL*")) and not list(w.var.rglob("PAUSE*"))
    assert r.rc == 0


def test_15_ledger_row_counts_unchanged(w):
    w.trades(25)
    c = sqlite3.connect(w.db)
    n0 = [c.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0] for t in
          ("decision_events", "trade_entries", "trade_exits", "param_versions", "param_activations")]
    c.close()
    w.run()
    c = sqlite3.connect(w.db)
    n1 = [c.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0] for t in
          ("decision_events", "trade_entries", "trade_exits", "param_versions", "param_activations")]
    c.close()
    assert n0 == n1


# ------------------------------------------------------------------------------------------ 16. duzey tavani
def _all_levels(doc):
    lv = [v["level"] for v in doc["rules"].values()]
    return lv + [doc["overall"]]


@pytest.mark.parametrize("seed", range(12))
def test_16_level_ceiling_random_worlds(tmp_path, seed):
    rnd = random.Random(seed)
    w = World(tmp_path, mode=rnd.choice(["paper", "testnet"]), funding_missing=rnd.choice([0, 0, 3]))
    if rnd.random() < 0.8:
        w.decision(NOW - rnd.uniform(1, 90) * D, "skipped", "stop_width")
    for _ in range(rnd.randint(0, 80)):
        w.decision(NOW - rnd.uniform(0, 40) * D, "entered")
    for _ in range(rnd.randint(0, 120)):
        w.trade(rnd.choice([-1.0, -1.0, 0.5, 4.0, -9.0, 25.0]), fee_entry_bp=rnd.uniform(0, 20), fee_exit_bp=rnd.uniform(0, 20),
                slip_entry_bp=rnd.uniform(-5, 30), slip_exit_bp=rnd.choice([None, rnd.uniform(-5, 40)]),
                funding=rnd.uniform(-5, 5), risk=rnd.choice([10.0, 10.0, 0.0, -2.0]),
                reason=rnd.choice(["stop", "target", "trail_stop", "regime_flip", "time_stop", "manual", "force_exit", "liquidation", "other"]))
    r = w.run()
    assert set(_all_levels(r.doc)) <= LEVELS
    assert "CRIT" not in json.dumps(r.doc)
    assert r.rc != 10                                              # nabzi kesen/CRIT cikis kodu yok


def test_16_empty_ledger_all_yetersiz_or_ok(w):
    r = w.run()
    assert set(_all_levels(r.doc)) <= LEVELS
    assert r.level("S2") == "YETERSIZ" and r.level("P1") == "YETERSIZ" and r.level("C1") == "YETERSIZ"


@pytest.mark.parametrize("breakage", ["missing_ledger", "garbage_ledger", "bad_status_json", "no_status"])
def test_16_unreadable_inputs_stay_within_levels(tmp_path, breakage):
    w = World(tmp_path)
    w.trades(5)
    if breakage == "missing_ledger":
        w.db.unlink()
    elif breakage == "garbage_ledger":
        w.db.write_bytes(b"this is not sqlite" * 50)
    elif breakage == "bad_status_json":
        (w.dir / "status.json").write_text("{not json", encoding="utf-8")
    else:
        (w.dir / "status.json").unlink()
    r = w.run(check=False)
    assert r.doc is not None, f"drift.json yok (rc={r.rc}): {r.err[-400:]}"
    assert set(_all_levels(r.doc)) <= LEVELS
    assert "CRIT" not in json.dumps(r.doc)
    if breakage in ("missing_ledger", "garbage_ledger"):
        assert r.doc["overall"] == "YETERSIZ"                       # "girdi okunamadi" (§4 duzey tablosu)
    assert r.rc != 10


# ------------------------------------------------------------------------------------------ 17. kilitli donem
def test_17_holdout_not_read_and_no_backtest(tmp_path):
    w = World(tmp_path)
    w.trades(30, rs=-0.2)
    w.candidates(30)
    hist = w.var / "history"
    hist.mkdir()
    for name in ("ETHUSDT_1m_2026-05.parquet", "ETHUSDT_1m_2026-08.csv", "BTCUSDT_1h_2026-10.parquet"):
        (hist / name).write_bytes(b"decoy")
    (w.dir / "history").mkdir()
    (w.dir / "history" / "ETHUSDT_1m_2026-06.csv").write_bytes(b"decoy")
    real_hist = ROOT / "var" / "history"
    log = tmp_path / "audit.json"
    wrapper = tmp_path / "wrap.py"
    wrapper.write_text(
        "import sys, runpy, json, os\n"
        "ev=[]\n"
        "def hook(e,a):\n"
        "    try:\n"
        "        if e=='open': ev.append(['open', os.fsdecode(a[0]) if isinstance(a[0],(str,bytes,os.PathLike)) else str(a[0])])\n"
        "        elif e=='import': ev.append(['import', a[0]])\n"
        "        elif e in ('subprocess.Popen','os.system','os.exec','os.spawn','os.posix_spawn'): ev.append([e, str(a[0])])\n"
        "    except Exception: pass\n"
        "sys.addaudithook(hook)\n"
        "script, out = sys.argv[1], sys.argv[2]\n"
        "sys.argv=[script]+sys.argv[3:]\n"
        "code=0\n"
        "try:\n"
        "    runpy.run_path(script, run_name='__main__')\n"
        "except SystemExit as e:\n"
        "    code=e.code or 0\n"
        "open(out,'w').write(json.dumps({'ev':ev,'code':code if isinstance(code,int) else 1}))\n", encoding="utf-8")
    cp = subprocess.run([sys.executable, str(wrapper), str(SCRIPT), str(log), *_argv(w.var, w.bot, NOW)], capture_output=True, text=True, timeout=120, env=_env(), cwd=str(ROOT))
    assert log.exists(), cp.stderr[-1500:]
    data = json.loads(log.read_text())
    assert data["code"] == 0, cp.stderr[-1500:]
    opened = [p for k, p in data["ev"] if k == "open"]
    bad = [p for p in opened if str(hist) in p or str(w.dir / "history") in p or str(real_hist) in p
           ]
    assert not bad, f"var/history okundu: {bad}"
    imports = [p for k, p in data["ev"] if k == "import"]
    assert not [m for m in imports if m.startswith("trader_engine.backtest") or m.endswith(".backtest")], "geri test modulu ice aktarildi"
    assert not [e for e in data["ev"] if e[0].startswith(("subprocess", "os.system", "os.exec", "os.spawn", "os.posix_spawn"))], \
        "izleyici alt surec baslatti (geri test?)"


# ------------------------------------------------------------------------------------------ 18. rapor dili
ID_RE = re.compile(r"\b(S[123]|M[123]|F[12]|P1|C1)\b")
RAW_RE = re.compile(r"\b(OK|IZLE|UYARI|YETERSIZ)\b|skipped_rows|next_checkpoint|funding_missing|threshold|overall|"
                    r"drift\.json|\blevel\b|param_version|_ts\b|CRIT")
CONF = ("Henüz çok az işlem var", "Erken gösterge", "hâlâ kesin kanıt değil")


def report_lines(res: Result) -> list[str]:
    lines = [ln for ln in res.out.splitlines() if "📐" in ln]
    if not lines and res.doc:
        for k in ("report_lines", "lines", "summary_lines", "daily_lines"):
            v = res.doc.get(k)
            if isinstance(v, list) and v:
                lines = [str(x) for x in v]
                break
    return lines


def test_18_report_language_no_codes(w):
    w.trades(62, rs=[-0.15] * 62, risk=10.0)
    w.candidates(30)
    r = w.run()
    lines = report_lines(r)
    assert lines, "gunluk rapor satiri bulunamadi (stdout '📐' satirlari ya da drift.json report_lines)"
    for ln in lines:
        assert not ID_RE.search(ln), f"kural kimligi sizdi: {ln}"
        assert not RAW_RE.search(ln), f"ham kod/ingilizce alan adi sizdi: {ln}"


@pytest.mark.parametrize("n,conf", [(62, "Henüz çok az işlem var"), (99, "Henüz çok az işlem var"), (100, "Erken gösterge"),
                                    (299, "Erken gösterge"), (300, "hâlâ kesin kanıt değil")])
def test_18_every_pnl_line_has_confidence_line(w, n, conf):
    w.trades(n, rs=[(-0.1 if i % 2 else 0.05) for i in range(n)])
    lines = report_lines(w.run())
    pnl = [ln for ln in lines if re.search(r"k[âa]r\s*/\s*zarar", ln, re.I)]
    assert pnl, f"K/Z satiri yok: {lines}"
    text = "\n".join(lines)
    assert conf in text, f"guven satiri ({conf!r}) yok: {lines}"


# ------------------------------------------------------------------------------------------ cikti sozlesmesi (§4.6, saglik §16.6)
def test_contract_drift_json_shape(w):
    w.trades(62, rs=-0.15)
    w.candidates(30)
    r = w.run()
    d = r.doc
    assert d.get("schema", "drift/1") == "drift/1"
    assert d["bot"] == "learner" and d["mode"] == "paper"
    assert d["plan_version"] == "kdp-v1"
    for k in ("generated_at", "window", "rules", "overall", "skipped_rows", "next_checkpoint"):
        assert k in d, k
    ts = datetime.fromisoformat(d["generated_at"].replace("Z", "+00:00"))
    assert ts.tzinfo is not None and abs((ts - NOW).total_seconds()) < 86400 * 2
    for rid in ("S1", "S2", "S3", "M1", "M3", "F1", "F2", "P1", "C1"):
        assert rid in d["rules"], rid
        assert {"level", "value", "threshold", "n", "note"} <= set(d["rules"][rid]), rid
    assert len([k for k in d["rules"] if k.upper().startswith("M2")]) >= 3
    assert d["window"]["n"] == 62
    assert d["next_checkpoint"]["n"] == 100 and d["next_checkpoint"]["remaining"] == 38
    if any(v["level"] == "UYARI" for v in d["rules"].values()):
        assert d["overall"] == "UYARI"
    assert not list(w.dir.glob("*.tmp")) and not list(w.dir.glob("drift.json.*"))     # atomik yazim: artik gecici dosya yok


def test_contract_overall_uyari_when_any_rule_uyari(w):
    w.trades(20, rs=-0.5, funding=10.0 * 0.5)                      # F1 UYARI
    r = w.run()
    assert r.level("F1") == "UYARI" and r.doc["overall"] == "UYARI"


def test_contract_twin_bot_rejected(tmp_path):
    """DD-12: ikiz kaldirildi; `--bot twin` kabul edilmez (argparse cikis kodu 2)."""
    w = World(tmp_path, bot="twin")
    w.trades(3)
    r = w.run(check=False)
    assert r.rc == 2 and not (w.var / "twin" / "drift.json").exists()


@pytest.mark.parametrize("n,nxt,rem", [(5, 30, 25), (30, 100, 70), (120, 150, 30), (200, 300, 100)])
def test_contract_next_checkpoint(w, n, nxt, rem):
    w.trades(n, rs=0.0)
    r = w.run()
    assert r.doc["next_checkpoint"]["n"] == nxt and r.doc["next_checkpoint"]["remaining"] == rem


def test_contract_idempotent_rerun_same_levels(w):
    w.trades(40, rs=-0.4)
    w.candidates(30)
    a = w.run()
    b = w.run()
    assert {k: v["level"] for k, v in a.doc["rules"].items()} == {k: v["level"] for k, v in b.doc["rules"].items()}
    assert a.rule("C1")["value"] == b.rule("C1")["value"]
