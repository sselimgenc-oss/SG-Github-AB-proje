"""TraderV1: freqtrade IStrategy bagdastirici (docs/strateji-spec.md Bolum 4-6).

Kural mantigi trader_core.signals'tadir; burada sayi/esik/kosul yoktur: yalnizca cagirir,
boyutlandirir (trader_core.risk) ve kaydeder (trader_core.ledger).
"""

import logging
import math
import os
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

import numpy as np
import pandas as pd
from pandas import DataFrame

from freqtrade.enums import RunMode
from freqtrade.exceptions import OperationalException
from freqtrade.persistence import Trade
from freqtrade.strategy import IStrategy, stoploss_from_absolute

from trader_core import ledger as L
from trader_core import regime as R
from trader_core import risk as K
from trader_core import signals as S

logger = logging.getLogger(__name__)

_TF_TD = {"1h": timedelta(hours=1), "15m": timedelta(minutes=15)}
_TF_PD = {"1h": "1h", "15m": "15min"}
_TF_HOURS = {"1h": 1.0, "15m": 0.25}
_BACKTEST_MODES = (RunMode.BACKTEST, RunMode.HYPEROPT)
_TRADE_MODES = (RunMode.LIVE, RunMode.DRY_RUN)
_STUB_REASON = "not_evaluated:v1_stub"


@dataclass(frozen=True)
class VetoVerdict:
    status: str
    reason: str | None
    blocks: bool


def _utc(dt: datetime) -> datetime:
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def _fin(x) -> bool:
    try:
        return x is not None and math.isfinite(float(x))
    except (TypeError, ValueError):
        return False


def _opt(x):
    return float(x) if _fin(x) else None


class TraderV1(IStrategy):
    INTERFACE_VERSION = 3

    can_short = True
    timeframe = "1h"
    startup_candle_count = 1200
    process_only_new_candles = True
    position_adjustment_enable = False

    use_custom_stoploss = True
    stoploss = -0.99
    minimal_roi = {"0": 100}
    use_exit_signal = True
    exit_profit_only = False
    ignore_roi_if_entry_signal = False

    order_types = {
        "entry": "market",
        "exit": "market",
        "stoploss": "market",
        "stoploss_on_exchange": True,
        "stoploss_on_exchange_interval": 60,
    }

    # ------------------------------------------------------------------ kurulum

    def __init__(self, config: dict) -> None:
        super().__init__(config)
        cfg = dict(config.get("trader_v1") or {})
        self._cfg = cfg
        self._runmode = config.get("runmode")
        self._is_bt = self._runmode in _BACKTEST_MODES
        self._now: datetime | None = None
        self._ledger: L.Ledger | None = None
        self._ledger_path = cfg.get("ledger_path")
        self._bot = cfg.get("bot") or config.get("bot_name") or "learner"
        self._versions: dict[int, S.SignalParams] = {}
        self._active: tuple[int, S.SignalParams, str | None] | None = None
        self._act_id: int | None = None
        self._params_ok = True
        self._gate_code: str | None = None
        self._decided: dict[tuple, object] = {}
        self._bar_final: dict[tuple[str, str], tuple[str, int | None]] = {}
        self._entry_ctx: dict[str, dict] = {}
        self._callback_errors = 0

        overrides = dict(cfg.get("params") or {})
        base = {k: getattr(S.DEFAULT_SIGNAL_PARAMS, k) for k in L.PARAM_KEYS}
        if not set(overrides) <= set(base):
            raise OperationalException(f"trader_v1.params bilinmeyen anahtar: {sorted(set(overrides) - set(base))}")
        base.update(overrides)
        try:
            cfg_params = S.SignalParams.from_mapping(base)
        except ValueError as e:
            raise OperationalException(f"trader_v1.params gecersiz: {e}") from e

        trigger_tf = cfg_params.trigger_tf
        self._open_ledger_if_configured(cfg_params)
        if self._ledger is not None and not self._is_bt:
            try:
                ap = self._ledger.get_active_params()
                trigger_tf = ap.params["trigger_tf"]
                params = S.SignalParams.from_mapping(ap.params)
                self._versions[ap.version_id] = params
                self._active = (ap.version_id, params, ap.params_hash)
                self._act_id = ap.activation_id
            except Exception as e:  # noqa: BLE001
                self._params_ok = False
                logger.critical("trader_v1: etkin parametre okunamadi (%s); girisler kapali", e)
        if self._active is None:
            vid = 0
            if self._ledger is not None and self._is_bt:
                ap = self._ledger.get_active_params()
                vid, self._act_id = ap.version_id, ap.activation_id
                self._active = (vid, cfg_params, ap.params_hash)
            else:
                self._active = (0, cfg_params, None)
            self._versions[vid] = cfg_params
        self._trigger_tf = trigger_tf
        self.timeframe = trigger_tf
        self.startup_candle_count = int(300 * 4 / _TF_HOURS[trigger_tf])

    def _open_ledger_if_configured(self, cfg_params: S.SignalParams) -> None:
        if not self._ledger_path or self._runmode not in _BACKTEST_MODES + _TRADE_MODES:
            return
        path = os.fspath(self._ledger_path)
        if self._is_bt:
            if os.path.exists(path):
                raise OperationalException(f"backtest defteri zaten var (yeni dosya zorunlu): {path}")
            led = L.open_ledger(path, "learner" if self._bot == "twin" else self._bot, create=True,
                                clock=self._clock)
            led.init_params({k: getattr(cfg_params, k) for k in L.PARAM_KEYS}, reason="backtest")
        else:
            led = L.open_ledger(path, self._bot, create=True)
        self._ledger = led

    def _clock(self) -> datetime:
        return self._now or datetime.now(timezone.utc)

    def bot_start(self, **kwargs) -> None:
        if self.timeframe != self._trigger_tf:
            raise OperationalException(
                f"timeframe uyusmazligi: config/CLI '{self.timeframe}' != trigger_tf '{self._trigger_tf}'")
        if self._runmode in _TRADE_MODES and not self.order_types.get("stoploss_on_exchange"):
            raise OperationalException("stoploss_on_exchange dry-run/canlida zorunlu")

    def informative_pairs(self):
        try:
            pairs = self.dp.current_whitelist()
        except Exception:  # noqa: BLE001
            pairs = (self.config.get("exchange") or {}).get("pair_whitelist") or []
        return [(p, "4h") for p in pairs]

    # ------------------------------------------------------------- parametre/kapi

    def bot_loop_start(self, current_time: datetime | None = None, **kwargs) -> None:
        if current_time is not None:
            self._now = _utc(current_time)
        if self._ledger is None or self._is_bt:
            return
        try:
            ap = self._ledger.get_active_params()
            if ap.activation_id != self._act_id:
                params = S.SignalParams.from_mapping(ap.params)
                self._versions[ap.version_id] = params
                self._active = (ap.version_id, params, ap.params_hash)
                self._act_id = ap.activation_id
                logger.info("trader_v1: parametre surumu %s etkin", ap.version_id)
            self._params_ok = True
        except Exception as e:  # noqa: BLE001
            self._params_ok = False
            logger.critical("trader_v1: parametre okunamadi (%s); girisler kapali (params_unavailable)", e)
        try:
            ids = [t.id for t in Trade.get_trades_proxy(is_open=True)]
            self._ledger.find_unledgered_trades(ids)
        except Exception as e:  # noqa: BLE001
            logger.error("trader_v1: unledgered denetimi basarisiz: %s", e)

    def _gate(self) -> tuple[bool, str]:
        """Yeni giris kapisi. Cikislar asla bu kapiya bagli degildir."""
        if self._trigger_tf != self.timeframe:
            return False, "trigger_tf_changed"
        if not self._params_ok:
            return False, "params_unavailable"
        if self._ledger is None:
            if self._is_bt:
                return True, "ok"
            return False, "ledger_unconfigured"
        if self._active is not None and self._active[2] is not None and not self._is_bt:
            try:
                if self._active[1].trigger_tf != self._trigger_tf:
                    return False, "trigger_tf_changed"
            except Exception:  # noqa: BLE001
                pass
        h = self._ledger.entries_allowed()
        return (bool(h.ok), h.code)

    def veto_check(self, pair, side, setup, bar_close_ts, planned_entry, planned_stop, planned_target) -> VetoVerdict:
        return VetoVerdict("not_evaluated", None, False)

    # ------------------------------------------------------------------ sinyal

    def _params_for(self) -> tuple[int, S.SignalParams]:
        vid, params, _ = self._active
        return vid, params

    def populate_indicators(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        pair = metadata["pair"]
        try:
            vid, params = self._params_for()
            df_4h = self.dp.get_pair_dataframe(pair, "4h")
            if df_4h is None or df_4h.empty:
                reg = pd.DataFrame(columns=["regime", "rh", "rl", "rh_touches", "rl_touches", "atr", "atr_ratio"])
                reg.index = pd.DatetimeIndex([], tz="UTC")
            else:
                reg = R.classify_series(df_4h.set_index("date")[["open", "high", "low", "close"]],
                                        params.regime_params())
            base = dataframe[["date", "open", "high", "low", "close"]].set_index("date")
            aligned = R.align_to_base(reg, base.index, 4)
            sig = S.compute_signals(base, aligned, params)
            for col in S.SIGNAL_COLUMNS:
                dataframe[col] = sig[col].to_numpy()
            dataframe["param_version_id"] = vid
            return dataframe
        except Exception:
            if self._is_bt:
                raise
            logger.critical("trader_v1: sinyal hesabi basarisiz (%s); giris yok", pair, exc_info=True)
            for col in S.SIGNAL_COLUMNS:
                dataframe[col] = False if col == "signal" else None
            dataframe["param_version_id"] = 0
            return dataframe

    def populate_entry_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        pair = metadata["pair"]
        if len(dataframe) == 0:
            return dataframe
        sig = dataframe["signal"].fillna(False).astype(bool) if "signal" in dataframe else None
        if sig is None:
            return dataframe
        live = not self._is_bt
        if live:
            ok, code = self._gate()
            if not ok:
                self._record_gate_closed(pair, dataframe, code)
                return dataframe
            if self._stale(dataframe):
                logger.warning("trader_v1: entries blocked: stale_data (%s)", pair)
                return dataframe
        long_m = sig & (dataframe["side"] == "long")
        short_m = sig & (dataframe["side"] == "short")
        dataframe.loc[long_m, "enter_long"] = 1
        dataframe.loc[short_m, "enter_short"] = 1
        dataframe.loc[long_m | short_m, "enter_tag"] = dataframe.loc[long_m | short_m, "setup"]
        if live:
            self._record_skipped_last(pair, dataframe)
        return dataframe

    def populate_exit_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        return dataframe

    def _stale(self, dataframe: DataFrame) -> bool:
        tf = _TF_TD[self.timeframe]
        last = pd.Timestamp(dataframe["date"].iloc[-1]).to_pydatetime()
        now = _utc(self._clock())
        expected = pd.Timestamp(now).floor(_TF_PD[self.timeframe]).to_pydatetime() - tf
        return _utc(last) < expected - tf

    # ---------------------------------------------------------- karar kaydi (canli)

    @staticmethod
    def _features(row) -> dict:
        keys = ["atr_tf", "stop_dist_atr", "atr_4h"]
        keys += (["pullback_ema", "ema_value", "body_ratio"] if row["setup"] == "T1"
                 else ["wick_ratio", "rr", "edge_dist_atr"])
        keys += ["rh_touches", "rl_touches"]
        return {k: (int(row[k]) if k in ("pullback_ema", "rh_touches", "rl_touches") else float(row[k]))
                for k in keys if _fin(row[k])}

    def _event(self, row, pair: str, **kw) -> L.DecisionEvent:
        tf = self.timeframe
        regime = row["regime"]
        is_range = regime == "range"
        base = dict(
            bar_close_ts=pd.Timestamp(row["date"]).to_pydatetime() + _TF_TD[tf], trigger_tf=tf, pair=pair,
            side=row["side"], setup=row["setup"], regime=regime, atr_ratio=_opt(row["atr_ratio"]),
            rh=_opt(row["rh"]) if is_range else None, rl=_opt(row["rl"]) if is_range else None,
            rh_touches=int(row["rh_touches"]), rl_touches=int(row["rl_touches"]),
            features=self._features(row), planned_entry=float(row["planned_entry"]),
            planned_stop=float(row["planned_stop"]), planned_target=_opt(row["planned_target"]),
            param_version_id=int(row["param_version_id"]),
            veto_status="not_evaluated", veto_reason=None, risk_allowed=None, risk_reason=None,
            size_qty=None, size_notional=None, size_margin=None, size_risk_amount=None, leverage=None,
            final_action="skipped", skip_reason=None)
        base.update(kw)
        return L.DecisionEvent(**base)

    def _write_once(self, key, ev: L.DecisionEvent):
        if key in self._decided:
            return self._decided[key]
        did = self._ledger.record_decision(ev)
        self._decided[key] = did
        return did

    def _record_gate_closed(self, pair: str, df: DataFrame, code: str) -> None:
        logger.warning("trader_v1: giris kapisi kapali (%s): %s", pair, code)
        try:
            row = df.iloc[-1]
            if self._ledger is None or not bool(row["signal"]) or int(row["param_version_id"]) < 1:
                return
            key = (pair, str(row["date"]), "gate")
            self._write_once(key, self._event(row, pair, skip_reason="entry_gate_closed"))
        except Exception as e:  # noqa: BLE001
            logger.error("trader_v1: entry_gate_closed karari yazilamadi: %s", e)

    def _record_skipped_last(self, pair: str, df: DataFrame) -> None:
        if self._ledger is None:
            return
        try:
            row = df.iloc[-1]
            if row["setup"] is None or row["side"] is None or row["skip_reason"] not in ("stop_width", "rr_below_min"):
                return
            if int(row["param_version_id"]) < 1:
                return
            self._write_once((pair, str(row["date"]), "skip"), self._event(row, pair, skip_reason=row["skip_reason"]))
        except Exception as e:  # noqa: BLE001
            logger.error("trader_v1: elenen aday kaydi yazilamadi: %s", e)

    # --------------------------------------------------------- hesap / boyutlandirma

    def _day_start(self, now: datetime) -> datetime:
        return _utc(now).replace(hour=0, minute=0, second=0, microsecond=0)

    def _last_price(self, pair: str, default: float) -> float:
        try:
            df, _ = self.dp.get_analyzed_dataframe(pair, self.timeframe)
            if len(df):
                return float(df["close"].iloc[-1])
        except Exception:  # noqa: BLE001
            pass
        return default

    def _account_state(self, now: datetime) -> K.AccountState:
        cur = self.config["stake_currency"]
        wallet = float(self.wallets.get_total(cur))
        opens = Trade.get_trades_proxy(is_open=True)
        unreal = 0.0
        positions = []
        for t in opens:
            rate = self._last_price(t.pair, t.open_rate)
            try:
                unreal += float(t.calc_profit(rate))
            except Exception:  # noqa: BLE001
                pass
            ra = t.get_custom_data("risk_amount")
            if not _fin(ra):
                ra = K.LOCKED_CFG.max_trade_risk * max(wallet, 0.0)  # fail-closed varsayim
            positions.append(K.OpenPosition(t.pair, "short" if t.is_short else "long", float(ra),
                                            float(t.stake_amount)))
        ds = self._day_start(now)
        realized_today = 0.0
        for t in Trade.get_trades_proxy(is_open=False):
            cd = t.close_date_utc
            if cd is not None and cd >= ds:
                realized_today += float(t.close_profit_abs or 0.0)
        return K.AccountState(equity=wallet + unreal, day_start_equity=wallet - realized_today,
                              open_positions=positions)

    def _market_limits(self, pair: str) -> tuple[float | None, float]:
        step, min_notional = None, 0.0
        try:
            m = self.dp.market(pair) or {}
            p = (m.get("precision") or {}).get("amount")
            if _fin(p) and float(p) > 0:
                step = float(p)
            c = ((m.get("limits") or {}).get("cost") or {}).get("min")
            if _fin(c):
                min_notional = float(c)
        except Exception:  # noqa: BLE001
            pass
        return step, min_notional

    def _signal_ctx(self, pair: str, side: str, current_time: datetime, tag) -> dict | None:
        df, _ = self.dp.get_analyzed_dataframe(pair, self.timeframe)
        if df is None or len(df) == 0:
            return None
        row = df.iloc[-1]
        tf = _TF_TD[self.timeframe]
        age = _utc(current_time) - _utc(pd.Timestamp(row["date"]).to_pydatetime())
        if not (tf <= age < 2 * tf):
            return None
        if not bool(row["signal"]) or row["side"] != side or (tag is not None and row["setup"] != tag):
            return None
        vid = int(row["param_version_id"])
        return {"row": row, "pair": pair, "side": side, "setup": row["setup"], "version_id": vid,
                "params": self._versions.get(vid) or self._active[1],
                "bar_close": pd.Timestamp(row["date"]).to_pydatetime() + tf}

    def _risk(self, ctx: dict, rate: float, leverage: float, now: datetime) -> K.Decision:
        row = ctx["row"]
        step, min_notional = self._market_limits(ctx["pair"])
        cand = K.Candidate(ctx["pair"], ctx["side"], float(rate), float(row["planned_stop"]), float(leverage),
                           step, min_notional)
        return K.check_entry(self._account_state(now), cand, K.LOCKED_CFG)

    def leverage(self, pair: str, current_time: datetime, current_rate: float, proposed_leverage: float,
                 max_leverage: float, entry_tag: str | None, side: str, **kwargs) -> float:
        return float(max(1, min(K.LOCKED_CFG.min_leverage, max_leverage)))

    def custom_stake_amount(self, pair: str, current_time: datetime, current_rate: float,
                            proposed_stake: float, min_stake: float | None, max_stake: float,
                            leverage: float, entry_tag: str | None, side: str, **kwargs) -> float:
        try:
            self._now = _utc(current_time)
            ctx = self._signal_ctx(pair, side, current_time, entry_tag)
            if ctx is None:
                return 0.0
            bkey = (pair, ctx["bar_close"].isoformat())
            if self._bar_final.get(bkey, ("",))[0] == "denied":
                return 0.0  # mum basina tek karar: ret kesindir
            dec = self._risk(ctx, current_rate, leverage, current_time)
            if dec.allowed:
                return float(dec.size.margin)
            logger.info("trader_v1: risk reddi %s: %s", pair, dec.reason)
            self._bar_final[bkey] = ("denied", None)
            self._write_risk_denied(ctx, dec, leverage)
            return 0.0
        except Exception:
            self._callback_errors += 1
            logger.exception("trader_v1: custom_stake_amount hatasi (%s); giris yok", pair)
            if self._is_bt:
                raise
            return 0.0

    def _write_risk_denied(self, ctx: dict, dec: K.Decision, leverage: float) -> None:
        if self._ledger is None:
            return
        try:
            ev = self._event(ctx["row"], ctx["pair"], veto_status="allowed", veto_reason=_STUB_REASON,
                             risk_allowed=False, risk_reason=dec.reason, skip_reason="risk_denied")
            self._write_once((ctx["pair"], ctx["bar_close"].isoformat(), "decision"), ev)
        except L.LedgerError as e:
            logger.error("trader_v1: risk_denied karari yazilamadi: %s", e)
        except Exception as e:  # noqa: BLE001
            logger.error("trader_v1: risk_denied karari yazilamadi: %s", e)

    def confirm_trade_entry(self, pair: str, order_type: str, amount: float, rate: float, time_in_force: str,
                            current_time: datetime, entry_tag: str | None, side: str, **kwargs) -> bool:
        # NOT: freqtrade bu geri cagrinin istisnasini True sayar; burada kendimiz kapatiriz.
        try:
            self._now = _utc(current_time)
            ok, code = self._gate()
            ctx = self._signal_ctx(pair, side, current_time, entry_tag)
            if ctx is None:
                return False
            bkey = (pair, ctx["bar_close"].isoformat())
            if self._bar_final.get(bkey, ("",))[0] == "denied":
                return False
            if not ok:
                logger.warning("trader_v1: giris kapali (%s): %s", pair, code)
                self._record_gate_skip(ctx)
                return False
            row = ctx["row"]
            verdict = self.veto_check(pair, side, ctx["setup"], ctx["bar_close"], float(row["planned_entry"]),
                                      float(row["planned_stop"]), _opt(row["planned_target"]))
            if verdict.blocks:
                self._bar_final[bkey] = ("denied", None)
                self._record_veto(ctx, verdict)
                return False
            lev = float(self.leverage(pair, current_time, rate, 1.0, 125.0, entry_tag, side))
            dec = self._risk(ctx, rate, lev, current_time)
            if (not dec.allowed) or amount > dec.size.qty * (1 + 1e-6):
                reason = dec.reason if not dec.allowed else "miktar boyutu asiyor"
                logger.info("trader_v1: confirm risk reddi %s: %s", pair, reason)
                self._bar_final[bkey] = ("denied", None)
                self._write_risk_denied(ctx, K.Decision(False, reason, None), lev)
                return False
            key = (pair, ctx["bar_close"].isoformat(), "decision")
            did = None
            if self._ledger is not None:
                size = dec.size
                ev = self._event(row, pair, veto_status="allowed", veto_reason=_STUB_REASON, risk_allowed=True,
                                 risk_reason=dec.reason, size_qty=size.qty, size_notional=size.notional,
                                 size_margin=size.margin, size_risk_amount=size.risk_amount,
                                 leverage=int(lev), final_action="entered", skip_reason=None)
                did = self._write_once(key, ev)
            self._bar_final[bkey] = ("entered", did)
            ctx.update(decision_id=did, risk_amount=float(dec.size.risk_amount))
            self._entry_ctx[pair] = ctx
            return True
        except Exception:
            self._callback_errors += 1
            logger.critical("trader_v1: confirm_trade_entry hatasi (%s); giris yok", pair, exc_info=True)
            return False

    def _record_gate_skip(self, ctx: dict) -> None:
        if self._ledger is None or ctx["version_id"] < 1:
            return
        try:
            self._write_once((ctx["pair"], ctx["bar_close"].isoformat(), "gate"),
                             self._event(ctx["row"], ctx["pair"], skip_reason="entry_gate_closed"))
        except Exception as e:  # noqa: BLE001
            logger.error("trader_v1: entry_gate_closed karari yazilamadi: %s", e)

    def _record_veto(self, ctx: dict, v: VetoVerdict) -> None:
        if self._ledger is None:
            return
        try:
            self._write_once((ctx["pair"], ctx["bar_close"].isoformat(), "decision"),
                             self._event(ctx["row"], ctx["pair"], veto_status=v.status, veto_reason=v.reason,
                                         skip_reason=f"veto_{v.status}"))
        except Exception as e:  # noqa: BLE001
            logger.error("trader_v1: veto karari yazilamadi: %s", e)

    # -------------------------------------------------------------- doldurma/kayit

    def order_filled(self, pair: str, trade, order, current_time: datetime, **kwargs) -> None:
        try:
            self._now = _utc(current_time)
            if order.ft_order_side == trade.entry_side:
                self._on_entry_fill(pair, trade, order, current_time)
            elif order.ft_order_side == trade.exit_side:
                self._on_exit_fill(pair, trade, order, current_time)
        except Exception:
            self._callback_errors += 1
            logger.exception("trader_v1: order_filled hatasi (%s)", pair)

    def _on_entry_fill(self, pair, trade, order, current_time) -> None:
        ctx = self._entry_ctx.pop(pair, None)
        if ctx is None:
            logger.error("trader_v1: giris baglami yok (%s); cikis verisi eksik kalacak", pair)
            return
        row, params = ctx["row"], ctx["params"]
        tf = self.timeframe
        rh, rl = _opt(row["rh"]), _opt(row["rl"])
        data = {
            "decision_id": ctx.get("decision_id"), "risk_amount": ctx["risk_amount"],
            "initial_stop": float(row["planned_stop"]), "planned_target": _opt(row["planned_target"]),
            "rh": rh, "rl": rl, "setup": ctx["setup"], "trail_atr": float(params.trail_atr),
            "stop_buffer_atr": float(params.stop_buffer_atr), "param_version_id": ctx["version_id"],
            "trigger_tf": tf,
            "entry_bar_open": pd.Timestamp(_utc(trade.open_date_utc)).floor(_TF_PD[tf]).isoformat(),
        }
        for k, v in data.items():
            trade.set_custom_data(k, v)
        if self._ledger is not None and ctx.get("decision_id") is not None:
            qty = order.safe_filled or order.safe_amount
            price = order.safe_price
            fee = abs(qty * price * (trade.fee_open or 0.0))
            try:
                self._ledger.record_trade_entry(L.TradeEntry(
                    trade_id=trade.id, decision_id=ctx["decision_id"], entry_ts=_utc(current_time),
                    entry_price=float(price), qty=float(qty), leverage=int(trade.leverage or 1),
                    fee_entry=float(fee)))
            except L.LedgerError as e:
                logger.critical("trader_v1: giris kaydi yazilamadi (%s): %s", pair, e)

    def _on_exit_fill(self, pair, trade, order, current_time) -> None:
        if self._ledger is None:
            return
        st = self._exit_state(trade, pair)
        reason, planned = self._ledger_exit_reason(trade, order, st, pair)
        qty = order.safe_filled or order.safe_amount
        price = order.safe_price
        fee = abs(qty * price * (trade.fee_close or 0.0))
        funding_paid = -float(trade.funding_fees or 0.0)
        try:
            self._ledger.record_trade_exit(L.TradeExit(
                trade_id=trade.id, exit_ts=_utc(current_time), exit_price=float(price), exit_reason=reason,
                planned_exit=planned, fee_exit=float(fee), funding_paid=funding_paid))
        except L.LedgerError as e:
            logger.error("trader_v1: cikis kaydi yazilamadi (%s): %s (spool)", pair, e)

    def _ledger_exit_reason(self, trade, order, st, pair) -> tuple[str, float | None]:
        tag = order.ft_order_tag or trade.exit_reason or ""
        if tag in ("stop_loss", "trailing_stop_loss", "stoploss_on_exchange"):
            armed = False
            if st and st["setup"] == "T1":
                armed = self._trail_stop(trade, st, pair)[1]
            return ("trail_stop" if armed else "stop"), _opt(trade.stop_loss)
        if tag == "target":
            return "target", _opt(st["planned_target"]) if st else None
        if tag in ("time_stop", "regime_flip", "trail_stop"):
            return tag, None
        if tag == "force_exit":
            if self._is_bt:
                return "other", None
            return ("force_exit" if trade.get_custom_data("force_exit_requested") else "manual"), None
        if tag == "liquidation":
            return "liquidation", None
        return "other", None

    # --------------------------------------------------------------- cikis durumu

    def _exit_state(self, trade, pair: str) -> dict | None:
        keys = ("setup", "initial_stop", "planned_target", "trail_atr", "entry_bar_open")
        st = {k: trade.get_custom_data(k) for k in keys}
        if st["setup"] is None or not _fin(st["initial_stop"]) or st["entry_bar_open"] is None:
            return self._rebuild_state(trade, pair)
        return st

    def _rebuild_state(self, trade, pair: str) -> dict | None:
        """custom_data yoksa: giris mumundan onceki sinyal satirindan yeniden kur."""
        try:
            df, _ = self.dp.get_analyzed_dataframe(pair, self.timeframe)
            tf = self.timeframe
            e = pd.Timestamp(_utc(trade.open_date_utc)).floor(_TF_PD[tf])
            sig_t = e - pd.Timedelta(_TF_TD[tf])
            rows = df[df["date"] == sig_t]
            if rows.empty:
                return None
            row = rows.iloc[-1]
            side = "short" if trade.is_short else "long"
            if not bool(row["signal"]) or row["side"] != side:
                return None
            params = self._versions.get(int(row["param_version_id"])) or self._active[1]
            return {"setup": row["setup"], "initial_stop": float(row["planned_stop"]),
                    "planned_target": _opt(row["planned_target"]), "trail_atr": float(params.trail_atr),
                    "entry_bar_open": e.isoformat()}
        except Exception:  # noqa: BLE001
            return None

    def _bars_since_entry(self, st: dict, pair: str):
        df, _ = self.dp.get_analyzed_dataframe(pair, self.timeframe)
        if df is None or len(df) == 0:
            return None
        e = pd.Timestamp(st["entry_bar_open"])
        return df[df["date"] >= e]

    def _trail_stop(self, trade, st: dict, pair: str, bars=None) -> tuple[float, bool]:
        """(stop_fiyati, devrede_mi). T1'de iz suren; R1'de sabit initial_stop."""
        init = float(st["initial_stop"])
        if st["setup"] != "T1":
            return init, False
        if bars is None:
            bars = self._bars_since_entry(st, pair)
        if bars is None or len(bars) == 0:
            return init, False
        side = "short" if trade.is_short else "long"
        path = S.trail_stop_path(side, float(trade.open_rate), init, bars["high"].to_numpy(),
                                 bars["low"].to_numpy(), bars["atr_tf"].to_numpy(), float(st["trail_atr"]))
        stop = float(path.iloc[-1])
        return stop, stop != init

    def custom_stoploss(self, pair: str, trade, current_time: datetime, current_rate: float,
                        current_profit: float, after_fill: bool, **kwargs) -> float | None:
        st = self._exit_state(trade, pair)
        if st is None:
            return None
        stop, _ = self._trail_stop(trade, st, pair)
        return stoploss_from_absolute(stop, current_rate, is_short=trade.is_short,
                                      leverage=trade.leverage or 1.0)

    def custom_exit(self, pair: str, trade, current_time: datetime, current_rate: float,
                    current_profit: float, **kwargs) -> str | None:
        st = self._exit_state(trade, pair)
        if st is None:
            trade.set_custom_data("force_exit_requested", True)
            return "force_exit"
        bars = self._bars_since_entry(st, pair)
        if bars is None or len(bars) == 0:
            return None
        side = "short" if trade.is_short else "long"
        if st["setup"] == "R1":
            tgt = st["planned_target"]
            if _fin(tgt):
                for hi, lo in zip(bars["high"].to_numpy(), bars["low"].to_numpy()):
                    if S.target_reached(side, float(tgt), float(hi), float(lo)):
                        return "target"
            if S.time_stop_due(len(bars)):
                return "time_stop"
            return None
        if S.regime_flip_exit(side, bars["regime"].iloc[-1]):
            return "regime_flip"
        stop, armed = self._trail_stop(trade, st, pair, bars)
        if armed and ((stop >= current_rate) if side == "long" else (stop <= current_rate)):
            return "trail_stop"
        return None
