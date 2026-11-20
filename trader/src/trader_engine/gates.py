"""Giris kapisi (05 §4): kapi zinciri, veto kaynaklari, hesap durumu ve risk. Risk sayisi yoktur: tek kaynak
trader_core.risk.LOCKED_CFG (cfg.risk_config: yalniz daha siki target_trade_risk). Strateji yalniz SignalRow verir; kapi kararini ve boyutu etkileyemez."""
from __future__ import annotations

import logging
import math
from collections import Counter
from collections.abc import Callable, Collection, Mapping
from dataclasses import dataclass
from datetime import datetime
from typing import Literal, Protocol

from trader_core import etiket_kurallari as EK
from trader_core import ledger as L
from trader_core import risk as K
from trader_core import veto

from . import arm_guard as AG
from .bars import tf_delta
from .brokers.base import Broker
from .clock import Clock
from .config import EngineConfig
from .errors import DataError
from .killswitch import Killswitch
from .pause import EntryPause
from .state import StateStore, parse_iso_z
from .strategies import arms as AR
from .strategy_runner import SignalFrame, SignalRow
from .types import SymbolRules

log = logging.getLogger("engine.gates")

_FILTERED_SKIPS = ("stop_width", "rr_below_min", "ml_filter")


class VetoSource(Protocol):
    def begin_step(self, now: datetime) -> None: ...

    def lookup(self, pair: str, side: str, now: datetime) -> veto.VetoLookup: ...


class FileVeto:
    """paper/canli: veto_mode="required". Anahtar yok/dosya bozuk/bayat -> lookup missing|stale (giris yok)."""

    def __init__(self, vcfg: veto.VetoConfig, env: Mapping[str, str]) -> None:
        self.cfg = vcfg
        self._key = env.get(vcfg.hmac_key_env)
        self._state: veto.VetoState | None = None

    def begin_step(self, now: datetime) -> None:
        self._state = veto.read_veto_file(self.cfg.veto_path, self._key, now, self.cfg)

    def lookup(self, pair: str, side: str, now: datetime) -> veto.VetoLookup:
        if self._state is None:
            return veto.VetoLookup("missing", "not_loaded", True)
        return veto.lookup(self._state, pair, side, now)


class NoVeto:
    """Yalniz backtest (veto_mode="off")."""

    def begin_step(self, now: datetime) -> None:
        return None

    def lookup(self, pair: str, side: str, now: datetime) -> veto.VetoLookup:
        return veto.VetoLookup("allowed", "not_evaluated:backtest", False)


@dataclass(frozen=True)
class GateVerdict:
    ok: bool
    code: str
    skip_reason: str | None   # "entry_gate_closed" | "other" | None


@dataclass(frozen=True)
class EntryOutcome:
    action: Literal["enter", "skip", "ignore"]
    event: L.DecisionEvent | None
    size: K.SizeResult | None
    leverage: int | None
    code: str
    mandatory_record: bool
    mark_decided: bool = True


def entry_leverage(cfg=None) -> int:
    """11 §3.1: cfg.leverage (varsayilan 3 = risk kilidi alt siniri => kagit sonuclari ayni). cfg yoksa alt sinir."""
    if cfg is None:
        return int(max(1, K.LOCKED_CFG.min_leverage))
    return int(max(1, cfg.leverage))


def _fin(x) -> bool:
    return isinstance(x, (int, float)) and not isinstance(x, bool) and math.isfinite(float(x))


_INT_CARRIERS = ("pullback_ema", "rh_touches", "rl_touches")


def _features(row: SignalRow) -> dict:
    """Defter ozellikleri: ortak anahtarlar + kurulumun `FEATURES` eslemesi (DD-12 WP-12a, K-7 madde 2). Tasiyici sutun
    adi tamsayiysa (pullback_ema) defterde tamsayi yazilir. T1/R1 eslemesi eski anahtar kumesiyle ayni sirada."""
    out: dict = {}

    def put(key: str, carrier: str) -> None:
        v = getattr(row, carrier)
        if _fin(v):
            out[key] = int(v) if carrier in _INT_CARRIERS else float(v)

    for k in ("atr_tf", "stop_dist_atr", "atr_4h"):
        put(k, k)
    for key, carrier in AR.features_of(row.setup).items():
        put(key, carrier)
    for k in ("rh_touches", "rl_touches"):
        put(k, k)
    return out


def _tf_of(row: SignalRow) -> str:
    if row.tf:                                               # DD-12 WP-11: bilesik strateji satiri zaman dilimini kendisi tasir
        return row.tf
    secs = int((row.bar_close_ts - row.bar_open_ts).total_seconds())
    for name, v in (("15m", 900), ("1h", 3600), ("4h", 14400), ("1d", 86400)):
        if secs == v:
            return name
    raise ValueError(f"tetik tf cozulemedi: {secs}s")


def build_decision_event(row: SignalRow, tf: str, **override) -> L.DecisionEvent:
    is_range = row.regime == "range"
    base = dict(
        bar_close_ts=row.bar_close_ts, trigger_tf=tf, pair=row.pair, side=row.side, setup=row.setup,
        regime=row.regime, atr_ratio=row.atr_ratio, rh=row.rh if is_range else None, rl=row.rl if is_range else None,
        rh_touches=int(row.rh_touches), rl_touches=int(row.rl_touches), features=_features(row),
        planned_entry=float(row.planned_entry), planned_stop=float(row.planned_stop),
        planned_target=row.planned_target, param_version_id=int(row.param_version_id),
        veto_status="not_evaluated", veto_reason=None, risk_allowed=None, risk_reason=None,
        size_qty=None, size_notional=None, size_margin=None, size_risk_amount=None, leverage=None,
        final_action="skipped", skip_reason=None, ml_score=row.ml_score, arm_id=row.arm_id)
    base.update(override)
    return L.DecisionEvent(**base)


class EntryGate:
    def __init__(self, cfg: EngineConfig, ledger: L.Ledger, state: StateStore, kill: Killswitch, veto: VetoSource,
                 clock: Clock, broker: Broker, rules_fn: Callable[[str], SymbolRules],
                 entry_ref_fn: Callable[[str, datetime, SignalRow], float] | None = None,
                 pause: EntryPause | None = None, ladder=None) -> None:
        self.cfg = cfg
        self.pause = pause
        self.ladder = ladder                                       # 12 §8.3: RiskLadder | None (backtest: hep None)
        self.ledger = ledger
        self.state = state
        self.kill = kill
        self.veto = veto
        self.clock = clock
        self.broker = broker
        self.rules_fn = rules_fn
        self.entry_ref_fn = entry_ref_fn
        self.counters: Counter = Counter()
        self.session_off: Mapping[str, Collection[str]] | Callable[[], Mapping[str, Collection[str]]] | None = None  # DD-12 D-T7: dersin kapattigi seanslar (sinif|cift -> etiketler); yok = hepsi acik
        # 19 Kasim: CT kadro uzlasisi (cift -> kayit) ya da None (yok/bayat). Yalniz ETIKET: features["ct_yon"] (+1 ayni yon,
        # -1 ters yon, 0 uzlasi yok); hicbir adayi engellemez. Motor kagitta baglar.
        self.ct_kadro: Callable[[], Mapping | None] | None = None
        # Haber/duygu etiketi (docs/haber-etiketi-spec.md): (cift, now_ms) -> {"duygu","haber"} ya da None (onbellek yok/bozuk/bayat).
        # Yalniz KAYIT: features["duygu"], features["haber"]; hicbir adayi engellemez, karar/boyut/risk yoluna girmez.
        self.haber_etiket: Callable[[str, int], Mapping | None] | None = None
        # 19.11 kullanici karari: kagitta ML filtresi AKTIF (ogrenme_filtre.FiltreDeposu ya da None). YALNIZ bir girisi atlatabilir
        # (`ml_filter`); boyut/kaldirac/limit/risk yoluna girmez. Hata/paket yok => serbest.
        self.ml_filtre = None
        # 20 Kasim kullanici karari: kagitta etiketler (rejim/duygu/CT kalabalik) girisi YALNIZ atlatabilir (docs/etiket-kurallari-spec.md).
        # etiket_cfg = dogrulanmis cfg.etiket_kurallari ({} = kapali); etiket_durum() -> {kural: acik} (kanita gore kapanmis kurallar False).
        self.etiket_cfg: Mapping | None = None
        self.etiket_durum: Callable[[], Mapping[str, bool]] | None = None
        self.arms_off: Collection[str] | Callable[[], Collection[str]] | None = None  # DD-12 WP-13: ders kapattigi kurulumlar (arm_id); yok = hepsi acik
        self.memory_lock: str | None = None       # DD-8 O4: dosya tutusu yazilamadiysa bellek kilidi (kapi kodu); None = yok

    # ------------------------------------------------------------------ cift-bagimsiz kapilar (4-8)
    def pre(self, D: datetime, tf: str, params_ok: bool, active_tf: str) -> GateVerdict:
        closed = "entry_gate_closed"
        if not params_ok:
            return GateVerdict(False, "params_unavailable", closed)
        if active_tf != tf:
            return GateVerdict(False, "trigger_tf_changed", closed)
        try:
            h = self.ledger.entries_allowed()
            if not h.ok:
                return GateVerdict(False, h.code, closed)
        except Exception as e:  # noqa: BLE001 - fail-closed
            log.error("entries_allowed hatasi: %s", e)
            return GateVerdict(False, "degraded", closed)
        reason = self.state.kv_get("entries_blocked_reason")
        if reason:
            return GateVerdict(False, str(reason), closed)
        if self.kill.active():
            return GateVerdict(False, "kill", closed)
        if self.pause is not None and self.pause.active():          # 11 §9.3: kill'den sonra, stale_data'dan once
            return GateVerdict(False, self.pause.code() or "paused", closed)
        if self.memory_lock:                                        # DD-8 O4 (fail-closed): tutus dosyaya yazilamadi
            return GateVerdict(False, self.memory_lock, closed)
        if self.ladder is not None:                                 # 12 §8.3: duraklatmadan sonra, stale_data'dan once
            gc = self.ladder.gate_code()
            if gc:
                return GateVerdict(False, gc, closed)
        if self.clock.now() - D > self.cfg.stale_factor * tf_delta(tf):
            return GateVerdict(False, "stale_data", "other")
        return GateVerdict(True, "ok", None)

    # ------------------------------------------------------------------ hesap durumu (§4.2)
    def account_state(self, D: datetime) -> K.AccountState | None:
        day = D.strftime("%Y-%m-%d")
        ds = self.state.kv_get(f"day_start:{day}")
        if ds is None:
            init = self.state.kv_get("initialized_at")
            fresh = True
            if isinstance(init, str) and init != "unset":
                try:
                    fresh = parse_iso_z(init).strftime("%Y-%m-%d") >= day
                except ValueError:
                    fresh = False
            if not fresh:
                return None
            ds = self.cfg.wallet_start
        positions = [K.OpenPosition(p.pair, p.side, float(p.risk_amount), float(p.margin))
                     for p in self.state.open_positions()]
        return K.AccountState(equity=float(self.broker.account().equity), day_start_equity=float(ds),
                              open_positions=positions)

    # ------------------------------------------------------------------ karar
    def _ignore(self, code: str) -> EntryOutcome:
        self.counters["ignore:" + code] += 1
        return EntryOutcome("ignore", None, None, None, code, False, False)

    def _skip(self, row: SignalRow, tf: str, code: str, *, mark: bool = True, **ev) -> EntryOutcome:
        self.counters["skip:" + code] += 1
        return EntryOutcome("skip", build_decision_event(row, tf, **ev), None, None, code, False, mark)

    def _session_off(self) -> Mapping[str, Collection[str]] | None:
        so = self.session_off
        return so() if callable(so) else so

    def _ct_yon(self, pair: str, side) -> int | None:
        """CT uzlasisina gore yon etiketi: +1 ayni, -1 ters, 0 uzlasi yok/notr; veri yok ya da bayatsa None (etiket yazilmaz).
        Okuma hatasi asla karari etkilemez."""
        fn = self.ct_kadro
        if fn is None or side not in ("long", "short"):
            return None
        try:
            kadro = fn()
        except Exception:  # noqa: BLE001 - etiket istege bagli; hata karari etkilemez
            return None
        if not kadro:
            return None
        rec = kadro.get(pair)
        yon = rec.get("net_yon") if isinstance(rec, Mapping) else None
        if yon not in ("long", "short"):
            return 0
        return 1 if yon == side else -1

    def _haber_etiketi(self, pair: str) -> dict:
        """Haber/duygu etiketi alanlari ({} = yazilmaz). Okuma hatasi asla karari etkilemez."""
        fn = self.haber_etiket
        if fn is None:
            return {}
        try:
            e = fn(pair, int(self.clock.now().timestamp() * 1000))
            return dict(e) if e else {}
        except Exception:  # noqa: BLE001 - etiket istege bagli; hata karari etkilemez
            return {}

    def _etiket_karari(self, row: SignalRow, tf: str, tk: dict) -> EntryOutcome | None:
        """Etiket kurallari (kagit): acik kural tetiklenirse `etiket_*` kodu ile atla (karar satiri; karsi-olgu mevcut yoldan).
        Kanita gore KAPANMIS kural girisi engellemez; atlayacagi islem `features.etiket_atlardi` ile not edilir (gercek sonucu izlenir).
        Veri yok/bayat -> engellemez (sayilir). Hata -> serbest. Boyut/kaldirac/limit'e hic girmez."""
        cfg = self.etiket_cfg
        if not cfg:
            return None
        try:
            feats = tk.get("features") or {}
            duygu = feats.get("duygu")
            ct = None
            if self.ct_kadro is not None:
                try:
                    kadro = self.ct_kadro()
                    ct = kadro.get(row.pair) if kadro else None
                except Exception:  # noqa: BLE001
                    ct = None
            tetik, veri_yok = EK.degerlendir(row.side, row.regime, duygu, ct, cfg)
            for k in veri_yok:
                self.counters["etiket_veri_yok:" + k] += 1
            if not tetik:
                return None
            try:
                acik = dict(self.etiket_durum()) if self.etiket_durum is not None else {}
            except Exception:  # noqa: BLE001
                acik = {}
            engel = [k for k, _ in tetik if acik.get(k, True)]
            kapali = [k for k, _ in tetik if not acik.get(k, True)]
            if kapali:
                self.counters["etiket_atlardi:" + kapali[0]] += 1
                tk["features"] = {**(tk.get("features") or _features(row)), EK.FEATURE_ANAHTAR: ",".join(kapali)}
            if not engel:
                return None
            kod = engel[0]
            detay = dict(tetik)[kod]
            self.counters["etiket_atladi:" + kod] += 1
            return self._skip(row, tf, kod, skip_reason=kod, veto_reason=f"gate:{kod}:{detay}", **tk)
        except Exception as e:  # noqa: BLE001 - etiket hatasi giris engellemez
            log.warning("etiket kurallari hatasi, giris serbest: %s: %s", type(e).__name__, e)
            return None

    def _ml_filtre_karari(self, row: SignalRow, tf: str, D: datetime, tk: dict) -> EntryOutcome | None:
        """ML filtresi (kagit): esik alti puan => `ml_filter` ile atla (karar satiri + puan; karsi-olgu mevcut atlama yolundan).
        Baska her durum (filtre yok/paket yok/hata) => None (giris serbest). Asla istisna yaymaz."""
        flt = self.ml_filtre
        if flt is None:
            return None
        try:
            from .ogrenme_filtre import ozellikler
            aid = row.arm_id or AG.arm_id_of(row.setup, tf)
            feats = tk.get("features") or _features(row)
            oz = ozellikler(side=row.side, regime=row.regime, atr_ratio=row.atr_ratio, session_tag=tk.get("session_tag"),
                            pair=row.pair, planned_entry=row.planned_entry, planned_stop=row.planned_stop,
                            planned_target=row.planned_target, rh_touches=int(row.rh_touches), rl_touches=int(row.rl_touches),
                            features=feats)
            k = flt.karar(aid, oz, self.clock.now())
            if k.neden == "ok":
                self.counters["ml_filtre_gecti"] += 1
            if k.izin:
                return None
            self.counters["ml_filtre_atladi"] += 1
            return self._skip(row, tf, "ml_filter", skip_reason="ml_filter", veto_reason="gate:ml_filter",
                              ml_score=k.puan, **tk)
        except Exception as e:  # noqa: BLE001 - filtre hatasi giris engellemez
            log.warning("ML filtre kapisi hatasi, giris serbest: %s: %s", type(e).__name__, e)
            return None

    def _arms_off(self) -> Collection[str]:
        ao = self.arms_off
        return (ao() if callable(ao) else ao) or ()

    def conflict(self, frame: SignalFrame, winner: SignalRow) -> EntryOutcome:
        """DD-12 WP-11 (D-T16): ayni cift/adimda birden cok kurulum sinyal verdi; buyuk zaman dilimi kazandi, kaybeden
        `arm_conflict` ile yazilir (kagit; veto yok; `mark_decided` yok - kazananin karari isaretler)."""
        row = frame.last
        tk: dict = {}
        if self.cfg.mode == "paper":
            tk = {"session_tag": AG.session_tag(AG.asset_class(row.pair, self.cfg.clusters), frame.last.bar_close_ts)}
        return self._skip(row, _tf_of(row), "arm_conflict", mark=False, skip_reason="arm_conflict",
                          veto_reason=f"gate:arm_conflict:{winner.arm_id or winner.setup}", **tk)

    def decide(self, frame: SignalFrame, D: datetime, pre: GateVerdict, active_version: int) -> EntryOutcome:
        if frame.status != "ok" or frame.last is None:                                  # 0
            return self._ignore(frame.status if frame.status != "ok" else "no_arm_closed")
        row = frame.last
        pair = row.pair
        tf = _tf_of(row)
        paper = self.cfg.mode == "paper"                                                # DD-12 WP-04: yalniz kagit
        tk: dict = {}
        cls = ""
        if paper:
            cls = AG.asset_class(pair, self.cfg.clusters)
            tk = {"session_tag": AG.session_tag(cls, D)}                                # etiket yasak degil, kayit
            ct = self._ct_yon(pair, row.side)
            if ct is not None:                                                          # CT yon etiketi (engellemez)
                tk["features"] = {**_features(row), "ct_yon": ct}
            hb = self._haber_etiketi(pair)
            if hb:                                                                      # haber/duygu etiketi (yalniz kayit; engellemez)
                tk["features"] = {**tk.get("features", _features(row)), **hb}
        if not row.signal:                                                              # 1 / 1b
            if (row.setup and row.side and row.skip_reason in _FILTERED_SKIPS
                    and self.cfg.record_filtered_candidates and row.param_version_id >= 1):
                return self._skip(row, tf, row.skip_reason, mark=False, skip_reason=row.skip_reason, **tk)
            return self._ignore("no_signal")
        if self.state.is_decided(pair, D):                                              # 2
            return self._ignore("already_decided")
        if self.state.position_for_pair(pair) is not None:                              # 3
            return self._ignore("position_exists")
        if row.param_version_id < 1:
            return self._ignore("no_param_version")
        if not pre.ok:                                                                  # 4-8
            return self._skip(row, tf, pre.code, skip_reason=pre.skip_reason, veto_reason="gate:" + pre.code, **tk)
        try:                                                                            # 9
            rules = self.rules_fn(pair)
        except Exception as e:  # noqa: BLE001 - DataError/RulesError/baska: fail-closed
            if not isinstance(e, DataError):
                log.error("rules_fn beklenmeyen hata %s: %r", pair, e)
            return self._skip(row, tf, "rules_missing", skip_reason="other", veto_reason="gate:rules_missing", **tk)
        now = self.clock.now()
        if paper:                                                                       # 9a-9c (DD-12 WP-04); veto adimi YOK
            aid = row.arm_id or AG.arm_id_of(row.setup, tf)
            # 19 Kasim (sahip karari): ders kurulum KAPATMAZ; arms_off yalniz karne/rapor bilgisidir, giris engellenmez.
            if aid in self._arms_off():
                self.counters["arm_would_close"] += 1
            if pair in self.cfg.retired_pairs:                                           # WP-18: evrenden cikmis, yeni giris yok
                return self._skip(row, tf, "arm_disabled", skip_reason="arm_disabled",
                                  veto_reason=f"gate:universe_retired:{pair}", **tk)
            if self.cfg.flat_bar_guard and frame.trigger_bar is not None and AG.is_flat_bar(
                    frame.trigger_bar[0], frame.trigger_bar[1], frame.trigger_bar[2]):
                return self._skip(row, tf, "flat_bar", skip_reason="flat_bar", veto_reason="gate:flat_bar", **tk)
            if AG.session_closed_by_lesson(self._session_off(), cls, pair, tk["session_tag"]):
                return self._skip(row, tf, "session_closed", skip_reason="session_closed",
                                  veto_reason="gate:session_closed", **tk)
            held = [p.pair for p in self.state.open_positions()]
            cname = AG.full_cluster(pair, held, self.cfg.clusters)
            if cname is not None:
                return self._skip(row, tf, "cluster_cap", skip_reason="cluster_cap",
                                  veto_reason=f"gate:cluster_cap:{cname}", **tk)
            if self.cfg.arm_max_positions:                                               # WP-11: kurulum basina tavan
                aid = row.arm_id or AG.arm_id_of(row.setup, tf)
                cap = AG.arm_cap(self.cfg.arm_max_positions, aid, row.setup)
                held_arms = [AG.arm_id_of(p.setup, p.trigger_tf) for p in self.state.open_positions()
                             if getattr(p, "setup", None) and getattr(p, "trigger_tf", None)]
                if AG.arm_full(held_arms, aid, cap):
                    return self._skip(row, tf, "max_positions", skip_reason="max_positions",
                                      veto_reason=f"gate:arm_cap:{aid}", **tk)
            if AG.account_full(len(held), self.cfg.max_positions):
                return self._skip(row, tf, "max_positions", skip_reason="max_positions",
                                  veto_reason="gate:max_positions", **tk)
            ml_skip = self._ml_filtre_karari(row, tf, D, tk)
            if ml_skip is not None:
                return ml_skip
            et_skip = self._etiket_karari(row, tf, tk)                                   # 20 Kasim: etiket kurallari (ML'den sonra, risk'ten once)
            if et_skip is not None:
                return et_skip
            lk = veto.VetoLookup("allowed", "not_evaluated:paper", False)
        else:
            lk = self.veto.lookup(pair, row.side, now)                                  # 10
        vs = "not_evaluated" if paper else "allowed"                                    # DD-12 WP-06a: kagitta veto yok
        if lk.blocks:
            return self._skip(row, tf, f"veto_{lk.status}", skip_reason=f"veto_{lk.status}",
                              veto_status=lk.status, veto_reason=lk.reason)
        acct = self.account_state(D)                                                    # 11
        if acct is None:
            return self._skip(row, tf, "day_start_missing", skip_reason="entry_gate_closed",
                              veto_reason="gate:day_start_missing", **tk)
        lev = entry_leverage(self.cfg)
        ref = self.entry_ref_fn(pair, D, row) if self.entry_ref_fn is not None else row.planned_entry
        cand = K.Candidate(pair, row.side, float(ref), float(row.planned_stop), float(lev),
                           rules.step, rules.min_notional)
        src = self.ladder if self.ladder is not None else self.cfg
        dec = K.check_entry(acct, cand, src.risk_config)
        if not dec.allowed:
            return self._skip(row, tf, "risk_denied", skip_reason="risk_denied", veto_status=vs,
                              veto_reason=lk.reason, risk_allowed=False, risk_reason=dec.reason, **tk)
        size = dec.size                                                                 # 12
        self.counters["enter"] += 1
        ev = build_decision_event(
            row, tf, veto_status=vs, veto_reason=lk.reason, risk_allowed=True, risk_reason=dec.reason,
            size_qty=size.qty, size_notional=size.notional, size_margin=size.margin,
            size_risk_amount=size.risk_amount, leverage=lev, final_action="entered", skip_reason=None, **tk)
        return EntryOutcome("enter", ev, size, lev, "entered", True)
