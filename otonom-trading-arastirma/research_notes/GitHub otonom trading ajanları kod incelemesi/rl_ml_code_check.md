# RL/ML autonomous trading repos: live-execution code check (as of 2026-11-15)

Method: shallow clones (`--depth 1`, LFS skipped) under `/home/claude/repos/`, read-only. Nothing was installed, imported or executed. Paths below are repo-relative; line numbers are from the cloned HEAD. Commit dates are from `git log -1 --format=%ci` on the clone. Levels use `advisor_framework.md` (L0-L5).

Summary table

| Repo | Live order path in code | Who decides trades | Hard risk limits in code | Last commit | License | Level (as shipped) |
|---|---|---|---|---|---|---|
| AI4Finance-Foundation/FinRL-Trading (FinRL-X) | Yes, Alpaca REST via `requests` (paper by default) | Fixed rules (adaptive rotation) on the `deploy.sh --mode paper` path | Partial: order-value cap, turnover scaling, -5%/-10% stops | 2026-09-18 | Apache-2.0 | L3 |
| AI4Finance-Foundation/FinRL | Yes, Alpaca `alpaca_trade_api` (`tradeapi.REST`), no paper guard | Learned PPO policy (fixed during a run) | Weak: share cap per action, turbulence sell-all, close-out before market close | 2026-10-25 | MIT | L3 |
| microsoft/RD-Agent | No (no broker or order code found) | N/A (research loop) | N/A | 2026-09-23 | MIT | N/A (research loop, no orders) |
| microsoft/qlib | No live broker. Online module is simulation only | N/A (simulated) | N/A | 2026-10-08 | MIT | L2 (simulated only) |
| freqtrade/freqtrade (FreqAI RL) | Yes, ccxt `create_order` on real exchanges; dry-run by default in example config | RL agent chooses entry/exit/direction; retrains on rolling data | Config-level: stoploss -5%, max_open_trades 5, stake caps; reward is user-defined | 2026-11-12 | GPL-3.0 | L3 as shipped; L4 if live retraining is on |
| tensortrade-org/tensortrade | None. Live adapters (ccxt, IB, Robinhood) are empty files | Learned DQN/A2C in a simulator | None live | 2026-02-09 | Apache-2.0 | N/A (simulation only) |
| TradingGPT (arXiv 2309.03736) | No code found | LLM agents with layered memory (simulated) | N/A | N/A | N/A | L2 (paper only) |
| FinAgent (KDD 2024, arXiv 2402.18485) | No official code found | LLM with reflection and memory (backtest) | N/A | N/A | N/A | L2 (paper only) |

---

## 1. AI4Finance-Foundation/FinRL-Trading (the repo the user called "FinRL-Trading")

Repo identity: the name is correct. The README calls the framework "FinRL-X" (arXiv 2603.21330). The old `FinRL` README points users to this repo for "live trading deployment, and production-focused development" (FinRL `README.md:29`). Base: https://github.com/AI4Finance-Foundation/FinRL-Trading

### Takeaway
It has a real Alpaca order path that runs without per-trade human approval, and it defaults to paper. Decisions come from fixed rules (regime switching plus stop-losses), not from a learned policy, on the `deploy.sh --mode paper` route. The `python src/main.py trade` route is broken as shipped, and the paper-only check exists only in `deploy.sh`.

### Cited Findings
- Broker SDK: no `alpaca_trade_api`/`alpaca-py` import. Orders go through raw HTTP with `requests`: `src/trading/alpaca_manager.py:19` (`import requests`), `:758` (`requests.request`), `:241` (`POST /v2/orders`), `:308` and `:327` (`DELETE` order and cancel-all), `:130` (`GET /v2/positions`). Credentials and base URL come from env: `src/config/settings.py:31-36` (`base_url` default `https://paper-api.alpaca.markets/v2`, `use_paper_trading: bool = True`), `:255-259`.
- Paper vs live: `alpaca_manager.py:42-44` defines `is_paper` as `"paper" in self.base_url`, a string test. The only enforcing check I found is `deploy.sh` paper branch (~L426-427: `if not account.is_paper: ... ERROR: Account is NOT paper trading!`). `src/trading/alpaca_manager.py` and `src/trading/trade_executor.py` contain no `is_paper` guard (`grep is_paper` matches only the definition).
- Live entry point is broken: `src/main.py:81-83` runs `from trading.trade_executor import main` for the `trade` command. `src/trading/trade_executor.py` defines no `main` (its only entry is the `if __name__ == "__main__":` block at `:461`). As shipped, `python src/main.py trade` should fail with ImportError. I did not execute this.
- `__main__` block of `src/trading/trade_executor.py:461-529`: reads `data/ml_weights.csv`, plans a dry run, then submits during market hours (or OPG if `USE_OPG=true`). No paper guard.
- Paper-mode decision source: `deploy.sh` (paper branch, ~L350-460) runs `AdaptiveRotationEngine.run(...)` (~L382), then `manager.execute_portfolio_rebalance(...)` (~L454). The engine is rule-based: regime detection, group strength, asset ranking, stops (`src/strategies/adaptive_rotation/adaptive_rotation_engine.py:158` `RiskManager.from_config`, `:243` `_check_stops`).
- Stop-loss parameters: `src/strategies/AdaptiveRotationConf_v1.2.2.yaml:198-204` (absolute `-0.05`, trailing `-0.10`, both enabled). Regime group caps and cash floors are in the same file (`:105-130`).
- ML path (not the paper path): `src/strategies/ml_bucket_selection.py:110-120` builds sklearn RandomForest, HistGradientBoosting, Ridge (and XGB/LGBM if installed). `src/strategies/ml_strategy.py:1314` writes `ml_weights.csv` using a Windows path (`r'.\data\ml_weights.csv'`), so it is not portable as written. This CSV is what the `trade` `__main__` block consumes.
- Hard limits in code, execution side (`src/trading/trade_executor.py`): `ExecutionConfig` defaults `max_order_value=100000.0`, `max_portfolio_turnover=0.5`, `min_order_size=100.0` (`:42-44`). `_apply_risk_checks` (`:280-316`) drops orders above the value cap and scales all orders down when turnover exceeds the limit. It does not reject the whole plan.
- Limits defined but not used in execution: `src/config/settings.py:103-105` (`max_weight_per_stock=0.1`, `max_sector_weight=0.3`, `max_turnover=0.5`). Weight caps are applied only in research weight construction (`src/strategies/ml_strategy.py:88-146`), not in `trade_executor.py`.
- Market-hours handling: `alpaca_manager.py:414` detects market state; orders are `day` TIF, or `opg` only when `market_closed_action='opg'`. Default is `skip` when closed.
- Dashboard button: `src/web/app.py:455-471` "Execute Sample Strategy" builds an `EqualWeightStrategy` on AAPL, MSFT, GOOGL and calls `executor.execute_strategy(...)`, with no paper check in that block.
- Position sizing in the README: "Execution | Live/paper trading | Alpaca multi-account integration with pre-trade risk checks" (README table). The README "live" claim is mostly the `trade` path, which is broken.
- Performance claim: README reports paper results "Oct 2025 – Mar 2026" (image `figs/Paper_Trading.png`). I did not verify these from logs in the repo.
- Maintenance: last commit 2026-09-18 09:13 +0800 (`git log -1`). `gh` metadata shows a later `updatedAt` (2026-11-14), which is not a code commit date. License Apache-2.0 (`LICENSE`).
- Scheduling: no daemon or cron in code. `deploy.sh` is run manually (`deploy.sh:122-124`). The `trade` command is the only in-code "run" path and it is broken.

### Inferences
- Autonomy: order placement is closed-loop (no human click), but the decision logic is a fixed rule set. This is L3 as shipped, not L4. No code adapts behaviour from outcomes.
- Paper-by-default is a config default plus a deploy-script check. A user who sets `APCA_BASE_URL` to the live endpoint and uses the `trade` route would bypass the only guard, once the `trade` route is fixed.
- Risk limits are mostly value and turnover caps in the executor. There is no max-drawdown kill switch, no daily-loss limit and no "close all" command in execution code (I grepped `kill`, `circuit`, `max_drawdown` and found only backtest metrics).

### Gaps
- I did not run the `trade` command, so the ImportError is from static reading. Confirm with a run in a sandbox.
- Live Alpaca fill and reconciliation behaviour (partial fills, restarts) was not verified. `wait_for_order_fill` exists (`trade_executor.py:331`), but restart state handling was not found.

---

## 2. AI4Finance-Foundation/FinRL (classic framework, Alpaca paper support)

Base: https://github.com/AI4Finance-Foundation/FinRL

### Takeaway
Paper trading is implemented for a learned PPO policy. It is a closed loop that submits market orders through `alpaca_trade_api`. It has no paper-only check, and its risk controls are a share cap per action, a turbulence sell-all, and a close-out before the market closes.

### Cited Findings
- SDK: `finrl/meta/paper_trading/alpaca.py:9` (`import alpaca_trade_api as tradeapi`); `:97` (`self.alpaca = tradeapi.REST(API_KEY, API_SECRET, API_BASE_URL, "v2")`). The same pattern is in `finrl/meta/env_stock_trading/env_stock_papertrading.py:7,101`.
- Order submit: `finrl/meta/paper_trading/alpaca.py:366-369` (`self.alpaca.submit_order(stock, qty, side, "market", "day")`), dispatched in threads.
- Loop: `alpaca.py:147-170` cancels open orders at start, waits for open, then in a `while True` loop closes all positions when fewer than 2 minutes remain before close.
- Decision: `alpaca.py:217-240` `trade()`. The policy is the loaded DRL model (`elegantrl` `act`, `rllib` `compute_single_action`, or SB3 `model.predict`). Action scaling: `action = (action * self.max_stock).astype(int)` (`:230`). `max_stock=1e2` is set in the constructor (`:32`). Actions below `-min_action` (10) trigger sells (`:240-243`).
- Turbulence rule: `alpaca.py:323-328` sets `turbulence_bool = 1 if turbulence >= self.turbulence_thresh` (default 30, `:34`). `:293` "sell all when turbulence".
- Stochastic sampling exists in the codebase: `finrl/meta/paper_trading/common.py:31-36` (`get_action` calls `dist.sample()`, used for exploration in training). The run-time SB3 call is `self.model.predict(state)[0]` (`alpaca.py:232`) with no `deterministic=True`, so SB3's own default applies. I did not trace which mode the elegantrl branch (`alpaca.py:221-226`) uses at run time.
- Entry point: `finrl/trade.py:40-72` `trade_mode == "paper_trading"` builds `AlpacaPaperTrading(...)` and calls `run()`. The only modes accepted are `backtesting` and `paper_trading` (`:77`). `API_BASE_URL` comes from the caller with no URL check.
- Dependencies: `requirements.txt:1-2` (`alpaca-py`, `alpaca_trade_api>=2.1.0`). `pyproject.toml:32` (`alpaca-trade-api = "^3"`). Two Alpaca SDKs are pinned together.
- Demo: `examples/FinRL_PaperTrading_Demo_refactored.py:141-158` builds `PaperTradingAlpaca` with `API_BASE_URL=TRADING_API_BASE_URL` taken from a CLI argument.
- Tests: `unit_tests/paper_trading/test_alpaca_orders.py` is an AST-based regression test on `submitOrder` dispatch, not a live test.
- Disclaimer: `README.md:381` "We are sharing codes for academic purposes under the MIT license... NOT a recommendation to trade real money." `README.md:55` table says "Live Trading | Basic Alpaca support".
- Maintenance: last commit 2026-10-25 21:49 +0800. License MIT (`LICENSE`).

### Inferences
- This is L3 as shipped: a learned policy with a closed-loop order path, and no per-trade approval. The policy does not change during a run. Retraining in the demo is offline (`examples/FinRL_PaperTrading_Demo_refactored.py`, `papertrading_erl_retrain` cwd).
- Limits in code are weak for an unattended run: no dollar cap per order, no drawdown or daily-loss stop, no paper-only guard. The turbulence rule is a market-wide volatility proxy, not a position limit.

### Gaps
- Not verified: whether the SB3 path and the elegantrl path produce the same behaviour in practice.
- Not verified: `fetch_latest_data` (AlpacaProcessor) data quality and failure handling.

---

## 3. microsoft/RD-Agent

Base: https://github.com/microsoft/RD-Agent

### Takeaway
No code places orders. Its loop proposes, codes, runs and scores research experiments (factors and models, including Qlib-based quant research). It is not an execution agent, so it has no trading level on the L0-L5 scale.

### Cited Findings
- Loop structure: `rdagent/components/workflow/rd_loop.py:199-245` defines `direct_exp_gen` (propose, then generate experiment), `coding` (CoSTEER developer), `running` (runner), `feedback` (summarizer), `record` (trace). The loop ends in a feedback and trace record, not a trade.
- Qlib integration is research only: `rdagent/scenarios/qlib/experiment/factor_template/read_exp_res.py:11` and `model_template/read_exp_res.py:11` use `from qlib.workflow import R` to read experiment results.
- Broker search: a grep over `*.py`, `*.yaml`, `*.toml`, `*.txt`, `*.md` for `alpaca|ccxt|binance|ibkr|interactive_brokers|submit_order|create_order|place_order|broker|live_trad|brokerage` found no trading-broker code. The only "Alpaca" hits are the Alpaca instruction-tuning dataset format (`rdagent/components/coder/finetune/__init__.py:65`).
- README describes RD-Agent(Q) as "automate the full-stack research and development of quantitative strategies via coordinated factor-model co-optimization" (`README.md:88`). It reports backtest-style results, not live trades.
- Maintenance: last commit 2026-09-23 19:05 +0800. License MIT (`LICENSE`).

### Inferences
- This is not an autonomous trader. It is an LLM-driven research loop that writes factor and model code. Any path from its output to orders would need a separate integration, which the repo does not contain.
- The framework's L4 criteria ("adaptation: memory/reflection") do apply to its research loop, but there is no order placement, so the level does not apply.

### Gaps
- I did not inspect the Qlib runner in detail (docker execution, `running` internals), so I cannot confirm how experiment code is sandboxed beyond the README.

---

## 4. microsoft/qlib (online/serving module)

Base: https://github.com/microsoft/qlib

### Takeaway
The "online" module is a simulated pipeline (retrain, generate orders, execute in a simulator, update account). The "serving" piece is a separate repo (qlib-server) for data and is not a broker. No broker SDK is in qlib.

### Cited Findings
- Broker search: grep of `qlib/` for `alpaca|ccxt|binance|ibkr|interactive_brokers|submit_order|create_order|place_order|broker|live_trad|robinhood` returned no hits.
- Online manager: `qlib/workflow/online/manager.py:101` `OnlineManager`, `:184` `routine(...)`. It handles training and signal preparation (`prepare_signals`, `:258`), with `simulate(...)` at `:302`. No order call.
- Contrib online operator: `qlib/contrib/online/operator.py:138-170` `execute(...)` uses `SimulatorExecutor` (`:153`, `:164`). `update(...)` (`:172-195`) accepts `type` "SIM" or "YC" in its check, but only "SIM" builds an executor. Any other value raises `"not found executor"`.
- Import defect: `qlib/contrib/online/operator.py:22` does `from .executor import SimulatorExecutor`, but `qlib/contrib/online/` contains no `executor.py` (files: `__init__.py manager.py online_model.py operator.py user.py utils.py`). `SimulatorExecutor` actually lives in `qlib/backtest/executor.py:513`. As shipped, the module import appears to fail. Not executed.
- Docs: `docs/hidden/online.rst:14-22` describe the flow "Generate the order list (pre_date) / Execute the order list (trade_date) / Update account (trade_date)" as a simulation of user accounts.
- Serving: `docs/advanced/server.rst:23-29` says Qlib-Server is a data-serving system with cache and a separate repo, not an execution system.
- Maintenance: last commit 2026-10-08 18:15 +0800. License MIT (`LICENSE`).

### Inferences
- As shipped, qlib cannot place live orders. Its "online" name refers to periodic retraining and simulated execution. The L2 label is for simulated decisions only.
- Any live use would need a new broker executor. The module structure suggests where it would plug in, but the repo does not contain one.

### Gaps
- Did not verify that the `qlib/contrib/online` import error would occur under a real Python run. Static reading only.

---

## 5. freqtrade/freqtrade (FreqAI RL)

Base: https://github.com/freqtrade/freqtrade

### Takeaway
Live trading is real: `freqtrade trade` sends orders to an exchange through ccxt. Dry-run is the default in the example config. The RL agent picks entries and exits itself (via integer actions mapped to `enter_long`/`enter_short`/`exit_*` signals). Stop-loss, ROI and position caps are set in the strategy config, not by the agent. Live retraining is configurable, which is why this repo sits at L3 as shipped and reaches L4 with retraining turned on.

### Cited Findings
- Live vs dry: `freqtrade/freqai/freqai_interface.py:140` `self.live = strategy.dp.runmode in (RunMode.DRY_RUN, RunMode.LIVE)`. `:431` `start_live(...)`.
- Order placement: `freqtrade/exchange/exchange.py:1522` `create_order(...)`; `:1535` `if self._config["dry_run"]:` builds a simulated order (`create_dry_run_order`, `:1230`); otherwise `:1552` `order = self._api.create_order(pair, ...)`, where `_api` is ccxt. Entry path: `freqtrade/freqtradebot.py:1066` `execute_entry`, `:1134` `self.exchange.create_order(...)`. Exit path: `:2258` `execute_trade_exit`, `:2350` `self.exchange.create_order(...)`.
- Decision source: signals come from `freqtrade/templates/FreqaiExampleStrategy.py:237-270` (`populate_entry_trend` with `&-s_close`; `populate_exit_trend` with `do_predict`). The RL model outputs an integer action; `freqtrade/freqai/RL/Base5ActionRLEnv.py:32-75` maps it to Neutral, Long enter/exit, Short enter/exit, and `:118-133` (`is_tradesignal`) filters invalid transitions. Docs: "the agent is 'making its own' entry and exit decisions" (`docs/freqai-reinforcement-learning.md:73`).
- Reward: `freqtrade/freqai/prediction_models/ReinforcementLearner.py:112` `calculate_reward`. Docs say the shipped reward is "a benchmark, it is *not* for live production" and users "*must* create their own" (`docs/freqai-reinforcement-learning.md:140-142`).
- Risk controls (config and strategy, not the model): `config_examples/config_freqai.example.json:5` `max_open_trades: 5`, `:7` `stake_amount: 200`, `:10` `dry_run: true`, `:12` `dry_run_wallet: 1000`. `templates/FreqaiExampleStrategy.py:41` `stoploss = -0.05`, `:42` `use_exit_signal = True`, `:28` `minimal_roi = {"0": 0.1, "240": -1}`. RL env drawdown (`freqtrade/freqai/RL/BaseEnvironment.py:82`, `max_training_drawdown_pct`) is a training-env cut, not a live limit.
- Retraining: `config_examples/config_freqai.example.json:56` `live_retrain_hours: 0` (retrain as often as possible). `docs/freqai-running.md:15` says FreqAI "will always use the most recently trained model" and retrains on a schedule. This is the online-adaptation criterion in the framework.
- Exchange adapters: `freqtrade/exchange/hyperliquid.py:29` `class Hyperliquid(Exchange)` (DEX adapter, same ccxt-based layer).
- Caveat in docs: "Improperly trained RL agents may find 'cheats' and 'tricks' to maximize reward without actually winning any trades" (`docs/freqai-reinforcement-learning.md:15`).
- Dependencies: `requirements-freqai-rl.txt` pins torch, gymnasium 1.4.0, stable-baselines3 2.9.2.
- Maintenance: last commit 2026-11-12 06:41 +0100. License GPL-3.0 (`LICENSE`). Reuse note: GPL-3.0 applies to derivative code.

### Inferences
- Live path: yes, with a real exchange via ccxt. dry_run is opt-out (the example sets `true`). This is the only repo here with a mature live exchange path.
- What decides trades: the RL policy decides entry, exit and direction. The user's code decides reward and features, and the core engine enforces stoploss, ROI and position caps. This is more than the framework's L1 example ("FreqAI... parameters only"), so I classify it as L3, since the agent chooses the entries and exits itself.
- L4 criterion met by configuration: with automatic live retraining on rolling windows, the deployed model changes over time from new data (framework criterion 5, "online retraining"). No outcome-based reflection or prompt rewriting exists.

### Gaps
- Did not verify the live exchange behaviour (order reconciliation, partial fills) from code alone. `freqtradebot.py` has the logic, but I did not trace each branch.
- The repo ships no profitable RL reward; any live result depends on a user-written reward, which I did not find here.

---

## 6. tensortrade-org/tensortrade

Base: https://github.com/tensortrade-org/tensortrade

### Takeaway
Simulation-only RL framework. The live adapters are empty placeholders and are commented out, so nothing in this repo can place a real order.

### Cited Findings
- Adapters are stubs: `tensortrade/oms/services/execution/__init__.py` imports only `simulated`. `ccxt`, `robinhood`, `interactive_brokers` are commented out. The three files (`ccxt.py`, `robinhood.py`, `interactive_brokers.py`) are 0 bytes.
- Simulated fills: `tensortrade/oms/services/execution/simulated.py:155` `execute_order(...)`; `tensortrade/oms/orders/broker.py:23` `class Broker(OrderListener, TimeIndexed)` (submit/cancel/update/on_fill in a backtest-style broker).
- Risk: the only stopper class is `tensortrade/env/default/stoppers.py:5` `MaxLossStopper` (training-episode stop). No live limits.
- Agent: `tensortrade/agents/dqn_agent.py:29` `class DQNAgent(Agent)`, `:242` `get_action(...)`. A2C also exists (`tensortrade/agents/a2c_agent.py`).
- README: "Train RL agents to trade. Can they beat Buy-and-Hold?" (`README.md`, top of file). Quick start is training scripts (`examples/training/train_simple.py`).
- Maintenance: last commit 2026-02-09 18:06 +0100 (oldest of the set, about 9 months). License Apache-2.0 (`LICENSE`).

### Inferences
- No live level. Learned policy in a simulator only. Not a candidate for the user's target (L3-L4 live).

### Gaps
- None relevant to the live question.

---

## 7. TradingGPT (paper code search)

### Takeaway
I found no official code for the TradingGPT paper. The GitHub repo named TradingGPT that matched the search (KevinMyDing/TradingGPT) is FinGPT code, not the paper's system.

### Cited Findings
- Paper: "TradingGPT: Multi-Agent System with Layered Memory and Distinct Characters for Enhanced Financial Trading Performance", authors Yang Li, Yangyang Yu, Haohang Li, Zhi Chen, Khaldoun Khashanah (Stevens Institute of Technology) per https://arxiv.org/abs/2309.03736. The arXiv abstract page has no GitHub link.
- Decisions: per https://arxiv.org/pdf/2309.03736, "LLM agents make the decisions, using layered memory (short, middle, and long-term) and trader characters. The backbone is GPT-3.5 turbo." The paper does not describe fixed rules or RL as the decision mechanism.
- Execution: the paper's trades are simulated. It back-tests "using ARK funds' historical trading records." Training runs from 2020-08-15 to 2023-02-15 and testing to 2023-08-15 (same source). The paper describes its work as still in a prompt-design stage.
- `gh search repos "TradingGPT"` returned about 10 repos, none linked to the paper. `KevinMyDing/TradingGPT` (MIT, last commit 2023-07-06 20:44 +0800) has a README titled "Data-Centric FinGPT: Open-source for Open Finance", so the name does not match the content. `masaichig0/tradingGPT`, `siddumoni/tradinggpt` and `Phichleng/TradingGPT` were not checked.

### Inferences
- Level L2 (LLM advisor, simulated). It has layered memory, which is an L4 feature if wired to live execution, but no execution exists in the paper or the search results.

### Gaps
- No verified official code repository. If the user has one from the paper authors, it should be checked separately.

---

## 8. FinAgent (KDD 2024 paper, arXiv 2402.18485)

### Takeaway
I found no official code for the FinAgent paper. A GitHub repo named FinAgent (DVampire/FinAgent, MIT) is a backtest framework with a simulated trading environment and no broker code. Whether it implements the paper is not stated in its README.

### Cited Findings
- Paper: decisions are made by LLM prompts, not RL. Its modules cover market intelligence, low- and high-level reflection, memory and tool-augmented decisions with GPT-4 (per https://arxiv.org/html/2402.18485v3). RL methods (SAC, PPO, DQN) are baselines only.
- Evaluation: backtest only. "all benchmarks are conducted within the same RL environment for both training and evaluation" (same source). Test window 2023-06-01 to 2024-01-01, six assets (five US stocks and Ethereum). Metrics: ARR, Sharpe, maximum drawdown.
- Search result: the official ar5iv/arXiv pages carry no code link. The paper's KDD page was in search results but was not fetched (not on the allowlist).
- DVampire/FinAgent (`/home/claude/repos/DVampire__FinAgent`): last commit 2024-08-31 20:13 +0200; MIT. README has install steps and API-key setup (OpenAI, etc.) but no paper link. `finagent/environment/trading.py:100-105` defines an action space of buy, hold and sell in an environment class. A grep for `alpaca|ccxt|binance|ibkr|submit_order|create_order|place_order|broker|live` over `*.py` returned no hits.

### Inferences
- Level L2 (advisor, simulated). The paper's reflection and memory design would be L4 if wired to execution, but it is not.

### Gaps
- No verified official code for the paper. DVampire/FinAgent is not confirmed as an implementation of it.
- Did not run the environment or check its data sources (news and price downloaders in `configs/downloader/` reference FMP, Polygon and Yahoo, all unverified).

---

## Cross-cutting notes for the report writer

1. Only two repos here (FinRL-Trading, FinRL) place real broker orders from code, and both use Alpaca. freqtrade is the only one with a live crypto exchange path in the default code. (Hyperliquid is an adapter in the same layer.)
2. Paper-only enforcement is weak. FinRL-Trading checks paper mode only in `deploy.sh`, and FinRL has no check at all. The base URL decides which account receives orders.
3. Hard risk limits in code are thin across the board: order-value and turnover caps (FinRL-Trading), share caps and turbulence sell-all (FinRL), stoploss/ROI/stake caps (freqtrade). None has a kill switch or drawdown stop wired to execution.
4. Two defects found by static reading, not run: FinRL-Trading `python src/main.py trade` (missing `main`), and qlib `contrib/online/operator.py` (missing `executor.py`).
5. Maintenance: freqtrade (3 days) and FinRL (3 weeks) are the most recent. tensortrade (9 months) and the two 2023-2024 paper repos are the stalest.
