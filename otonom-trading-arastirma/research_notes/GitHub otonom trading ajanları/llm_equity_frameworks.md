# Open-source LLM-based (multi-)agent equity trading frameworks on GitHub (state as of Nov 2026)

Method caveat: direct GitHub access (gh CLI / WebFetch on github.com, except HKUDS/AI-Trader) was blocked in this session. Stars/last-commit/license figures come from third-party mirrors/trackers (sourcepulse, ossinsight, oosmetrics) whose snapshot dates are often unstated and mutually inconsistent. Treat star counts as order-of-magnitude. Repo-by-repo verification of README details (esp. broker integrations) is a gap.

## Which projects truly close the loop (research -> decision -> order -> exit) vs only produce recommendations?

### Takeaway
The big-name research frameworks (TradingAgents, virattt/ai-hedge-fund, FinRobot, FinMem, FinCon, StockAgent, ContestTrade) do NOT natively route orders to a real broker: they output decisions into a simulated exchange/backtester. Closed-loop paper/live execution on Alpaca exists mainly in newer, smaller or community projects (Infinite Bagholder, NightWatcher-V2, AgenticTrading's Alpaca paper mode, an unmerged TradingAgents PR adding AlpacaBroker) and in HKUDS/AI-Trader's simulated-account "arena".

### Cited Findings
- TradingAgents (TauricResearch): approved trades go to a "simulated exchange for execution"; no live broker integration described; "designed for research purposes" — [PyShine, Apr 2026](https://pyshine.com/TradingAgents-Multi-Agent-Financial-Trading/); DigitalOcean's explainer likewise describes no broker APIs/live routing and says it does not endorse it for day-to-day decisions — [DigitalOcean](https://www.digitalocean.com/resources/articles/tradingagents-llm-framework)
- TradingAgents community PR #281 (author jackspace, commits ~Nov 14-19 2025) adds an `AlpacaBroker` (market/limit/stop/stop-limit orders, position tracking, P&L), paper only; PR was open/unmerged at time of the snapshot and its "production-ready, 174 tests pass" claim is the author's — [PR mirror](https://backiee.wasmer.app/https_git_codeproxy_net/TauricResearch/TradingAgents/pull/281)
- virattt/ai-hedge-fund: "does not execute real trades"; educational proof of concept with backtester — [SourcePulse](https://www.sourcepulse.org/projects/1797841); [The Menon Lab](https://themenonlab.blog/blog/ai-finance-github-repos-march-2026)
- FinRobot (AI4Finance): generates research reports, not trade signals/orders; no broker integration — [Pinggy](https://pinggy.io/blog/best_ai_trading_agents/)
- FinMem (pipiku915): profiling/layered-memory/decision module; page does not mention brokerage integration — [SourcePulse](https://www.sourcepulse.org/projects/2179367)
- FinCon: results are backtests on historical data; no live trading stated — [arXiv 2407.06567](https://arxiv.org/html/2407.06567v3)
- ContestTrade: historical simulation only, A-share; no live orders; US equities listed as future work — [arXiv 2508.00554](https://arxiv.org/html/2508.00554v2)
- StockAgent: simulation of trading in a simulated environment (four phases), research-stage preprint — [SourcePulse](https://www.sourcepulse.org/projects/1839457)
- Infinite Bagholder (rickyispresent/infinite-bagholder, AGPLv3, announced Jul 14 2026 on Alpaca forum): autonomous worker loops (agent loop + news loop from SEC EDGAR, Alpaca News, Reddit WSB; indicator engine), Alpaca paper AND live support plus mock broker, hard-coded Python guardrails (penny-stock block, stop-loss, max allocation); no benchmarks/results given; author's promotional post — [Alpaca forum](https://forum.alpaca.markets/t/show-alpaca-infinite-bagholder-an-open-source-pluggable-agentic-ai-harness-for-llm-powered-trading/19313)
- NightWatcher-V2 (Alpaca Learn article, Jun 25 2026; repo link ambiguous: LNSTT369/NightWatcher-V2 vs ygwyg/NIGHTWATCHER-V2): Node.js agent using StockTwits signals + LLM catalyst validation (default gpt-4o-mini), decides buy/hold/sell, monitors positions; Cloudflare-Workers MCP server enforces policy, issues approval tokens, submits orders to Alpaca; paper-first (`ALPACA_PAPER=true`), kill switch, daily loss limit, no margin/shorting; no performance reported — [Alpaca Learn](https://alpaca.markets/learn/building-nightwatcher-v2-a-multi-agent-trading-system-with-alpaca)
- AgenticTrading (Open-Finance-Lab): research platform with backtests and paper trading via Alpaca API, decision logs, integrates FinAgent for orchestration/memory/planning; "experimental playground", ~333 stars, license OpenMDW-1.0 — [SourcePulse](https://www.sourcepulse.org/projects/31940407); paper describes planner/orchestrator/alpha/risk/portfolio/backtest/execution/audit/memory agents over MCP + A2A; execution agents convert weights to orders, but reported results are backtest/simulated-or-paper, not live — [arXiv 2512.02227](https://arxiv.org/html/2512.02227v1); "early-stage, not ready for production" — [Pinggy](https://pinggy.io/blog/best_ai_trading_agents/)
- HKUDS/AI-Trader: agent-native platform where agents register via a skill file (ai4trade.ai), publish signals and trade a $100K paper account; also Polymarket paper trading (added 2026-03-03); mentions trade sync with Binance/Coinbase/IBKR but without detail; page does not clearly state real orders are placed — [GitHub README](https://github.com/HKUDS/AI-Trader)
- FinRL-X / FinRL-Trading (AI4Finance): Alpaca live API with multi-account support, but it is a weight-centric quant/RL pipeline, not an LLM research agent; advised to paper trade first — [Pinggy](https://pinggy.io/blog/best_ai_trading_agents/)
- Other community forks/repos surfaced in search but NOT verified: KylinMountain/TradingAgents-AShare (Docker, A-share variant), IBKR-AIHedge (AristidesAI), tradermonty/claude-trading-skills, alpacahq/alpaca-mcp-server (MCP brokerage connector) — [SourcePulse awesome-trading-agents](https://www.sourcepulse.org/projects/31514299); [search results](https://backiee.wasmer.app/https_github_com/AristidesAI/IBKR-AIHedge)

### Inferences
- A "closed-loop" LLM stock agent today typically = (LLM agent loop) + (Alpaca MCP/API) + (hard-coded risk guardrails). The famous academic-style multi-agent frameworks stop at a decision string (BUY/HOLD/SELL) and need a user-written bridge to a broker, which is the thing the user-brief wants to avoid; Infinite Bagholder and NightWatcher-V2 are the closest found to autonomous research->order->exit, but both are very new, single-author, and have no published performance.
- Exit logic in the closed-loop projects appears to be partly rule-based (stop-loss, position limits) rather than purely LLM-driven.

### Gaps
- Could not read READMEs directly; whether TradingAgents main branch has since merged any official broker/Alpaca integration by Nov 2026 is unverified (only the open PR #281 from late 2025 found).
- No verification of IBKR-based LLM agents beyond a repo name.
- FinAgent (Open-Finance-Lab, "multimodal foundation agent") repo specifics not retrieved beyond its being integrated into AgenticTrading; TradingGPT repo not found.

## Catalog: stars, activity, license, architecture, data, LLMs

### Takeaway
TradingAgents (~tens of thousands to >100k stars depending on snapshot) and virattt/ai-hedge-fund (~50-65k) dominate attention; both are research/education tools with simulated execution. HKUDS/AI-Trader (~20-23k) is a benchmark/arena. Older academic repos (FinMem, StockAgent) are low-activity.

### Cited Findings
- TradingAgents (https://github.com/TauricResearch/TradingAgents): stars reported inconsistently — ~24.8k (paper snapshot, ~Dec 2025, [arXiv 2512.02227](https://arxiv.org/html/2512.02227v1)); 31,553 stars/6,061 forks as of 2026-03-08 ([oosmetrics](https://oosmetrics.com/repo/TauricResearch/TradingAgents)); 85,174, last commit "1 week ago", undated snapshot ([SourcePulse](https://www.sourcepulse.org/projects/2368224)); ~112,106 stars/21,664 forks, Apache-2.0, undated ([ossinsight](https://ossinsight.io/analyze/TauricResearch/TradingAgents)); a +9.3k-stars-in-a-week spike attributed to full open-sourcing in a March 2026 blog ([Menon Lab](https://themenonlab.blog/blog/ai-finance-github-repos-march-2026)). License: Apache-2.0 per ossinsight; SourcePulse says "not specified in README" (conflict).
  - Architecture: analysts (fundamentals, sentiment, news, technical) -> bull/bear researcher debate -> trader -> risk team -> portfolio manager; LangGraph; ReAct — [Pinggy](https://pinggy.io/blog/best_ai_trading_agents/), [DigitalOcean](https://www.digitalocean.com/resources/articles/tradingagents-llm-framework). Paper: arXiv 2412.20138 (AAAI 2025 MARW workshop per SourcePulse).
  - Data: Alpha Vantage and yfinance (default fallback); categories market/news/fundamentals/social — [PyShine](https://pyshine.com/TradingAgents-Multi-Agent-Financial-Trading/). LLMs: OpenAI GPT-5.x, Gemini 3.x, Claude 4.x, Grok 4.x, OpenRouter, Ollama — same source. Original paper used GPT-4o-mini/GPT-4o/o1-preview.
  - Cost/limits: est. $0.30-0.50 per single-ticker analysis at GPT-5 rates; Alpha Vantage free tier 25 calls/day — [Pinggy](https://pinggy.io/blog/best_ai_trading_agents/)
- virattt/ai-hedge-fund (https://github.com/virattt/ai-hedge-fund): 64,652 stars, last commit "5 days ago", MIT (undated tracker snapshot) — [SourcePulse](https://www.sourcepulse.org/projects/1797841); earlier snapshots 42.3k ([arXiv 2512.02227](https://arxiv.org/html/2512.02227v1)), 49.6k (Mar 2026). ~19 agents: 14 investor personas (Buffett, Munger, Burry, Wood, Druckenmiller, Lynch...), valuation/sentiment/fundamentals/technicals/risk agents, portfolio manager; CLI + web UI + backtester; cloud LLMs and Ollama — [Pinggy](https://pinggy.io/blog/best_ai_trading_agents/). No performance claimed; personas are approximations; thin for international stocks.
- FinRobot (https://github.com/AI4Finance-Foundation/FinRobot): 8,274 stars, last commit ~3 weeks before snapshot, Apache-2.0; four-layer architecture (financial AI agents, financial LLM algorithms, LLMOps, multi-source foundation models); needs OpenAI, Finnhub, SEC keys — [SourcePulse](https://www.sourcepulse.org/projects/1844779). Equity research-report oriented.
- HKUDS/AI-Trader (https://github.com/HKUDS/AI-Trader): 22.9k stars, 3.5k forks, MIT, 388 commits, newest changelog entry 2026-06-11 (monthly challenges/live scoring; yfinance fallback 06-08; Alpha Vantage primary for US prices) — [GitHub](https://github.com/HKUDS/AI-Trader); another tracker says last commit "4 months ago" (undated) — [SourcePulse](https://www.sourcepulse.org/projects/17524338). Original version: NASDAQ-100 arena using MCP tools, identical starting capital, replayable historical data with look-ahead controls; needs OpenAI, Alpha Vantage, Jina keys.
- FinMem (https://github.com/pipiku915/FinMem-LLM-StockTrading): 963 stars, last commit ~2 years before snapshot (inactive), license unspecified by tracker; three modules (profiling, layered memory, decision-making) — [SourcePulse](https://www.sourcepulse.org/projects/2179367)
- FinCon (code announced at https://github.com/The-FinAI/FinCon): manager-analyst hierarchy, 7 analyst types incl. Whisper on earnings calls, manager decides, CVaR risk alerts + conceptual verbal reinforcement; GPT-4-Turbo; stocks TSLA/AMZN/NIO/MSFT/AAPL/GOOG/NFLX/COIN — [arXiv](https://arxiv.org/html/2407.06567v3). Repo activity/stars not retrieved.
- ContestTrade (https://github.com/FinStep-AI/ContestTrade): 465 stars at ~Dec 2025 snapshot ([arXiv 2512.02227](https://arxiv.org/html/2512.02227v1)); Data Team + Research Team with internal contest, DeepSeek-V3/R1, A-share; LightGBM + knapsack allocation — [arXiv 2508.00554](https://arxiv.org/html/2508.00554v2)
- StockAgent (https://github.com/MingyuJ666/Stockagent): 709 stars, last commit ~3 months before snapshot, license not stated; OpenAI/Google API; simulation — [SourcePulse](https://www.sourcepulse.org/projects/1839457). (402 stars in the Dec 2025 snapshot.)
- Other small projects in the Dec 2025 comparison: Quant Agent (306 stars), Alpha Arena (549 stars) — [arXiv 2512.02227](https://arxiv.org/html/2512.02227v1). Nof1's "Alpha Arena" is a separate live competition (see next section).
- LLMQuant/awesome-trading-agents: 338 stars, recent commit; curated list — [SourcePulse](https://www.sourcepulse.org/projects/31514299)

### Inferences
- Tracker numbers for the same repo differ by 3-4x; the writer should cite ranges and snapshot dates, or re-verify on GitHub.
- Late 2026 maintenance: TradingAgents, ai-hedge-fund, AI-Trader and AgenticTrading show recent commits in trackers (undated); FinMem is effectively dormant; StockAgent near-dormant.

### Gaps
- Exact current (Nov 2026) stars/last commits unverified. TradingGPT, FinAgent repo stats, TradingAgents-CN and other 2026 newcomers (beyond Infinite Bagholder, NightWatcher-V2) not catalogued due to blocked GitHub access and tool budget. LLM-support list for FinMem/FinCon repos not retrieved.

## Reported performance and credibility

### Takeaway
Published returns are mostly short backtests in simulation and are likely inflated; independent reproduction and live arenas show much weaker results.

### Cited Findings
- TradingAgents paper: simulation Jan 1-Mar 29 2024 vs Buy&Hold/MACD/KDJ-RSI/SMA baselines, claims superior CR/Sharpe — [DigitalOcean](https://www.digitalocean.com/resources/articles/tradingagents-llm-framework); a community 30-day run ~7% vs S&P 4.5% with 22% drawdowns (anecdotal) — [Pinggy](https://pinggy.io/blog/best_ai_trading_agents/)
- Independent reproduction (arXiv 2605.16895, "Landscape of LLM Trading Agents", May 2026; via AI-generated alphaXiv overview, not the paper itself): TradingAgents Sharpe fell 0.43 -> 0.22 after costs and trailed buy-and-hold on 4 of 5 stocks; FinMem and QuantAgent drop >50% in some cases when tested after LLM training cutoffs (temporal contamination); most papers ignore costs/slippage; short windows give Sharpe standard errors as large as returns — [alphaXiv](https://www.alphaxiv.org/overview/2605.16895)
- FinCon: CR 82.9% TSLA, 113.8% Portfolio 1 (Sharpe 3.27) on Oct 2022-Jun 2023 test; GPT-4-Turbo — [arXiv](https://arxiv.org/html/2407.06567v3). Single ~8-month window, contamination risk (GPT-4 knowledge overlaps).
- ContestTrade: CR 52.80%, Sharpe 3.12, MDD 12.41% on Jan-Jun 2025 A-shares vs CSI All Share 4.42% — [arXiv](https://arxiv.org/html/2508.00554v2). Single six-month window, single market, no live orders.
- AI-Trader benchmark (arXiv 2512.10971, HKU): US Nasdaq-100 hourly Oct 1-Nov 7 2025: MiniMax-M2 +9.56% vs QQQ +1.87%, DeepSeek-v3.1 +8.39%, several models trailed/lost; A-shares: no agent beat SSE-50 (1.65%); crypto: only DeepSeek beat the index by holding cash. Conclusion: general reasoning did not reliably give trading skill; risk control mattered most — [arXiv](https://www.arxiv.org/pdf/2512.10971)
- Nof1 Alpha Arena (live, $10k per model, US tech stocks, 2 weeks, four competitions): overall lost about a third of capital; a model profitable in only 6 of 32 result sets — Bloomberg via [Business Standard, May 7 2026](https://www.business-standard.com/markets/news/ai-bots-auditioning-for-wall-street-trading-are-mostly-losing-money-126050701793_1.html). (Alpha Arena is a competition, not necessarily an open-source framework.)
- Infinite Bagholder, NightWatcher-V2, AgenticTrading, AI-Trader platform: no performance numbers published in the sources found.

### Inferences
- Most-credible evidence is negative: independent reproduction and live arenas show little durable edge. Treat paper numbers (Sharpe >3, CR >50%) as non-deployment evidence.

### Gaps
- No audited multi-month live/paper track record for any open-source framework was found. HKUDS AI-Trader live leaderboard results after Nov 2025 not retrieved.

## Which are actively maintained as of late 2026, and paper/live integrations incl. forks

### Takeaway
Active (per tracker snapshots and changelogs): TradingAgents, virattt/ai-hedge-fund, HKUDS/AI-Trader (changelog through Jun 2026), AgenticTrading, FinRobot, plus new 2026 single-author Alpaca projects. Dormant: FinMem, StockAgent (slow).

### Cited Findings
- See catalog for last-commit data; AgenticTrading "last commit 4 hours ago" at snapshot — [SourcePulse](https://www.sourcepulse.org/projects/31940407)
- Alpaca paper integrations: AgenticTrading (paper via Alpaca API), TradingAgents PR #281 (AlpacaBroker, unmerged at snapshot), Infinite Bagholder (paper+live), NightWatcher-V2 (paper-first via MCP). IBKR: AI-Trader mentions trade sync; IBKR-AIHedge fork exists (unverified).
- Alpaca MCP server (alpacahq/alpaca-mcp-server) is the common bridge for Claude-/LLM-driven trading — [SourcePulse](https://www.sourcepulse.org/projects/31514299)

### Inferences
- Expect Alpaca (free paper endpoint) to remain the de facto paper-trading target for LLM agents.

### Gaps
- No snapshot dated Nov 2026 was obtainable; verify "last commit" directly before asserting maintenance status.
