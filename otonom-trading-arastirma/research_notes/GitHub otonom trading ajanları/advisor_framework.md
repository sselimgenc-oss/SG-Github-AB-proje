# Advisor Framework: Evaluating Self-Directed Trading Agents on GitHub

Scope: bots that decide *what* to trade and *when* on their own, as opposed to bots that execute a strategy the user wrote. Written from domain knowledge, not fresh web research; verify repo-specific facts before relying on them.

## 1. Autonomy taxonomy

Classify by one question: **who authored the decision that led to the order?**

| Level | Name | What the software decides | Typical examples |
|---|---|---|---|
| L0 | Rule executor | Nothing. Executes user-defined rules/parameters. | Freqtrade, Hummingbot, grid/DCA bots, Jesse |
| L1 | Optimized executor | Parameters only (hyperopt, ML signal inside a user-chosen strategy template). | FreqAI, most "ML strategy" repos |
| L2 | Analyst / advisor | Researches and outputs a buy/sell/hold opinion; no order placement, or simulated only. | TradingAgents, ai-hedge-fund, FinRobot (default use) |
| L3 | Closed-loop agent | Gathers data, decides, sizes, and places/closes real orders on a schedule with no human approval per trade. Strategy logic is a fixed prompt or fixed policy. | NoFx, Alpha Arena replicas, a FinRL policy wired to a broker |
| L4 | Adaptive agent | L3 plus it changes its own behaviour from results: memory/reflection, prompt or strategy rewriting, online retraining, asset-universe selection. | Reflection-based LLM agents, RD-Agent-style factor loops wired to execution |
| L5 | Fully autonomous fund | L4 plus self-directed research of new strategies, capital allocation across them, and self-governed risk, running unattended for months. | No credible open-source example; treat claims as marketing |

Classification criteria (check in code, not README):

1. **Decision origin**: does the user supply entry/exit logic (L0-L1) or only a goal/universe/risk budget (L3+)?
2. **Loop closure**: is there a real order call (`create_order`, broker SDK) reachable without a human click? No means L2 at most.
3. **Information gathering**: does it pull its own inputs (prices, news, on-chain, filings), or consume a user-prepared dataset?
4. **Exit ownership**: does it manage and close positions itself, including stops?
5. **Adaptation**: does anything persistent change after outcomes (memory store, weights, prompts, generated code)?
6. **Scope freedom**: can it choose instruments, direction, leverage, and holding period?

Notes for the catalogers:
- Many repos are **L2 by default, L3 by fork**. Record both "as shipped" and "with documented integration".
- RL agents (FinRL) are autonomous in *policy* but usually stop at backtest; without a live loop they are L2-equivalent.
- "Multi-agent" is an architecture, not an autonomy level. A five-agent debate that prints a report is still L2.
- The user's target is **L3-L4**.

## 2. Evaluation checklist

**A. Closed-loop execution**
- Real exchange/broker adapter (CCXT, Alpaca, IBKR, Hyperliquid, Binance) with order, cancel, and position reconciliation.
- Handles partial fills, rejects, rate limits, restarts (state persisted, not in-memory).
- Scheduler/daemon mode, not a notebook cell.
- Structured LLM output with validation; a malformed response must result in *no trade*, not a default trade.

**B. Risk controls (must be hard-coded outside the LLM)**
- Max position size, max leverage, max daily loss, max open positions, per-trade stop.
- Kill switch and "close all" path.
- Limits enforced in code after the model's decision; a prompt saying "risk at most 2%" is not a control.
- Instrument whitelist.

**C. Paper / testnet mode**
- First-class paper mode using the same code path as live (exchange testnet, Alpaca paper, or internal simulator with fees and slippage).
- Live requires an explicit flag; default is safe.

**D. Backtest integrity**
- **LLM look-ahead leakage**: any backtest period before the model's training cutoff is contaminated; the model may "remember" what the price or news did. Only results after the cutoff, or live/paper forward results, count.
- News/fundamental data timestamped by publication time, not event time; no restated financials.
- Fees, funding, slippage, and spread modelled; fills not assumed at close of the signal bar.
- Sample size: weeks of results on a handful of tickers is noise. Look for a benchmark (buy-and-hold, equal weight) and drawdown, not just return.
- Non-determinism: results from one LLM run are one sample; look for multiple seeds/runs.
- For RL: train/validation/test split by time, no hyperparameter tuning on the test window.

**E. Cost**
- Tokens per decision cycle × cycles per day × symbols. Multi-agent debate on a frontier model at 5-minute cadence can exceed any plausible edge on a small account.
- Data subscriptions, VPS, exchange fees, funding.
- Rule of thumb: if monthly running cost exceeds 1-2% of account size, the experiment is educational, not economic.

**F. API key and operational security**
- Keys in env/secret store, never committed; encrypted at rest if a web UI stores them.
- Supports trade-only keys; **withdrawal permission never required**; IP whitelisting possible.
- No wallet private key or seed phrase requested for CEX trading. For DEX/on-chain, use a dedicated hot wallet with limited funds.
- Web dashboard not exposed without auth; no telemetry posting to unknown hosts.
- Dependencies pinned; no obfuscated code, binary blobs, or `curl | bash` installers.
- Prompt injection: an agent that reads news/social text and can place orders is attackable through that text. Hard limits in B are the mitigation.

**G. Maintenance and credibility**
- Recent commits, issue responsiveness, multiple contributors, tests, tagged releases.
- Licence (AGPL and non-commercial terms matter for reuse).
- Stars are weak evidence; star growth with no issues or forks activity suggests purchased stars.
- A linked token, paid "pro" signal group, or referral-link-first README shifts the project's incentives.

## 3. Pitfalls and red flags

**Malicious repos (a real, recurring pattern, especially crypto/Solana/MEV "bots")**
- Asks for a private key or seed phrase in `.env` or a config file.
- Obfuscated or minified source, base64 strings, `eval`/`exec`, encoded URLs, post-install scripts.
- New account, few commits, many stars, README full of profit screenshots, issues disabled.
- Typosquatted dependencies or a requirement to download a prebuilt executable.
- "Just paste this contract into Remix and fund it" MEV/arbitrage bots: essentially always theft.
- Clones of popular repos with one changed file. Always install from the canonical org.

**Overstated performance**
- Returns reported over the LLM's training period, or on a few cherry-picked tickers (NVDA/TSLA in a bull run).
- No costs, no benchmark, no drawdown, a single run.
- Annualizing a few weeks of results.
- Leveraged crypto perps results presented without liquidation risk.
- Papers and READMEs showing Sharpe ratios far above what professional funds achieve.

**Structural realities**
- Public live benchmarks of LLM traders (Alpha Arena-style contests) have shown high variance, frequent losses, and heavy fee drag from over-trading. Treat current LLM agents as unproven, not as an edge.
- LLMs are inconsistent: same input, different trade. They also tend to over-trade and rationalize.
- Any edge published in a popular open repo is, at best, shared with everyone who cloned it.
- Unattended failure modes: API outage mid-position, duplicated orders after restart, model provider deprecating a model.
- Legal/tax: automated trading creates many taxable events; some exchanges and leverage products are restricted by jurisdiction.

## 4. Practical path for an individual

1. **Shortlist 2-3 repos at L3-L4** from the catalog that pass sections 2F and 2G. Prefer ones with a testnet/paper mode and an active community.
2. **Read before running.** Skim the order-placement and config code, grep for network calls and key handling. Run in a container or VM, not on a machine holding wallets.
3. **Run L2 first.** Let it produce decisions without execution for one to two weeks; log them and compare against buy-and-hold. This costs only tokens.
4. **Paper/testnet for at least 4-8 weeks**, covering different market conditions. Track return versus benchmark, max drawdown, trade count, fees, LLM cost, and every malfunction.
5. **Prepare the account.** Separate sub-account or new exchange account; trade-only key, IP whitelisted, no withdrawals; spot or low leverage (3x or less) only.
6. **Go live tiny.** An amount you would spend on a course and are prepared to lose entirely. Set hard limits in code and on the exchange side where possible.
7. **Supervise.** Alerts (Telegram/email) on every order and error; daily review at first; a tested kill switch.
8. **Scale only on evidence**: several months of live results net of all costs beating the benchmark, and no unexplained behaviour. Otherwise keep it as a learning tool.
9. **Stay current safely.** Pin a version, read diffs before updating, rotate keys periodically.

Honest expectation to set: the realistic near-term value of these projects is education and research assistance (L2), not unattended profit. Nothing here is financial advice.
